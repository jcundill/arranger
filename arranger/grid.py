"""The request's rhythm: when each part sounds, bar by bar.

`BarRhythm` is one bar's request - direct positions in felt beats - and `Rhythm`
is a repeating cycle of those bars. The rest of this module is the metre's
arithmetic under them: `felt_beat` and `rhythm_beats` convert between a position
and a bar-relative beat, and `beat_offset` puts two bars' beats on one line.
`grid.py` imports `group_starts` from `grouping`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .grouping import group_starts

TICKS_PER_BEAT = 24

#: A felt beat divided into this many equal parts: thirds land on index 4 and 8,
#: quarters on index 3, 6 and 9 - LCM(3,4) = 12 is the smallest grid holding both.
#: Every grid point is exact on the `TICKS_PER_BEAT` lattice because a felt beat is
#: always a whole number of raw beats, so `1/12` of one is `group_length/12` raw beats
#: = `2 * group_length` ticks, always an integer.
SUBDIVISIONS_PER_FELT_BEAT = 12


BEAT_EPSILON = 1e-6


def beat_offset(bar: int, beat: float, beats_per_bar: int) -> float:
    """One position on a single absolute beat line, so two bars' beats can be compared.

    A `(bar, beat)` pair orders correctly against another pair, but a *duration*
    cannot be compared against one: a note running past a barline ends at
    `(bar, 3.5)` in a 2/2 bar, which is before `(bar + 1, 1.0)` and after `(bar, 2.0)`,
    and no amount of tuple comparison says so. One number in beats-from-the-start does,
    and signed bars fall out of the arithmetic rather than needing a case.

    `beats_per_bar` is the *count* - how many beats a bar has - and not how long one
    lasts. A caller converting a duration in whole notes needs `beat_type` as well;
    the two are different numbers in every metre but 4/4.
    """
    return (bar - 1) * beats_per_bar + (beat - 1.0)


def grid_resolutions(beat_type: int) -> Tuple[int, ...]:
    quarter = 6 * beat_type
    candidates = {
        TICKS_PER_BEAT,
        2 * quarter,
        quarter,
        (2 * quarter) // 3,
        quarter // 2,
        quarter // 3,
        quarter // 4,
    }
    return tuple(
        resolution
        for resolution in sorted(candidates, reverse=True)
        if resolution > 0 and TICKS_PER_BEAT % resolution == 0
    )


# --- the request: direct positions in felt beats -----------------------------

RHYTHM_MELODY = "melody"
RHYTHM_SUSTAIN = "sustain"
RHYTHM_NONE = "none"
RHYTHM_EVERY_BEAT = "every-beat"
_RHYTHM_LAST = "last"

#: The separator between the bars of a rhythm longer than one bar: `1,3:none` is a
#: two-bar figure. `:` is unused by every other vocabulary the request has, so it
#: reads as a barline rather than as a token, and it is argv-safe for the same reason
#: `and` is - a shell does not interpret it.
RHYTHM_BAR_SEPARATOR = ":"

#: The subdivisions the grammar names, and the fraction of a felt beat each is.
#: Ordered so a position's one canonical spelling sorts as `1`, `1e`, `1and`, `1a`
#: - the musical order rather than the alphabet's.
#:
#: The midpoint is spelled `and`, not the musical `&`, because a position is a
#: command-line argument: an unquoted `&` is a shell's background operator, so
#: `--chord-on 1&` would never reach this parser. `e` and `a` are ordinary
#: characters and need no such spelling.
_SUBDIVISIONS: Tuple[Tuple[str, float], ...] = (
    ("", 0.0),
    ("e", 0.25),
    ("and", 0.5),
    ("a", 0.75),
)

#: A position token: a felt-beat number or `last`, optionally followed by one of
#: the subdivisions. A decimal such as `1.5` is deliberately not accepted: it
#: names a time rather than a place on the metre's grid and cannot express
#: `lastand`. The alternatives are ordered longest-first so `1and` is read as the
#: midpoint rather than as `1a` followed by a stray `nd`.
_RHYTHM_POSITION = re.compile(r"^(?P<beat>last|\d+)(?P<subdivision>(?:and|e|a))?$")


@dataclass(frozen=True)
class BarRhythm:
    """When a layer attacks in **one bar**: positions, the tune's onsets, or both.

    `positions` are **felt-beat numbers**: felt beat 1 is `1.0`, the midpoint of its
    group is `1.5`, and the second felt beat is `2.0` whatever the group's length.
    That is what makes one rhythm the same request in 2/2, 4/4 and 6/8, where an
    absolute beat number is not. `melody` is not a position: it names the written
    melody's own onsets, and a bar may name it *and* positions - the harmonisation
    plus a stab. A bar that names neither is silent.
    """

    melody: bool = False
    sustain: bool = False
    positions: Tuple[float, ...] = ()

    def __post_init__(self) -> None:
        for position in self.positions:
            whole = int(position)
            offset = round(position - whole, 6)
            if whole < 1 or all(
                abs(offset - value) > BEAT_EPSILON for _token, value in _SUBDIVISIONS
            ):
                raise ValueError(
                    f"rhythm position {position!r} is not a felt beat or one of "
                    f"its e/and/a subdivisions"
                )
        object.__setattr__(self, "positions", tuple(sorted(set(self.positions))))

    @property
    def is_none(self) -> bool:
        """Whether the layer never sounds in this bar."""
        return not (self.melody or self.sustain or self.positions)

    def includes(
        self,
        beat: Optional[float],
        beats_per_bar: int,
        grouping: Optional[Sequence[int]] = None,
    ) -> bool:
        """Whether `beat` - a bar-relative beat number - is one of the positions.

        The comparison is in felt beats, so the midpoint of a group is that group's
        `and` rather than half a denominator unit. `None` is not a position: it is a
        note whose rhythm the caller did not supply.
        """
        if beat is None or not self.positions:
            return False
        felt = felt_beat(beat, beats_per_bar, grouping)
        return any(
            abs(felt - position) <= BEAT_EPSILON for position in self.positions
        )

    def __str__(self) -> str:
        if self.is_none:
            return RHYTHM_NONE
        tokens = [RHYTHM_SUSTAIN] if self.sustain else ([RHYTHM_MELODY] if self.melody else [])
        tokens.extend(_format_position(position) for position in self.positions)
        return ",".join(tokens)


@dataclass(frozen=True)
class Rhythm:
    """When a layer attacks, as one `BarRhythm` per bar of a repeating cycle.

    A one-bar figure - `1,3` - has `bars` of length one and repeats in every bar. A
    longer figure is written with `RHYTHM_BAR_SEPARATOR` between its bars
    (`1,3:none:1,4and`) and its **first bar lands on the form's first complete bar**
    (`at`), so an anacrusis consumes no part of it. The cycle is reduced to its
    shortest period, because `1,3:1,3` and `1,3` are one request.
    """

    bars: Tuple[BarRhythm, ...] = (BarRhythm(),)

    def __post_init__(self) -> None:
        if not self.bars:
            raise ValueError(
                "a rhythm has at least one bar; spell a silent bar 'none'"
            )
        object.__setattr__(self, "bars", tuple(self.bars)[: _period(self.bars)])

    @property
    def is_none(self) -> bool:
        """Whether the layer never sounds, in any bar of the cycle."""
        return all(bar.is_none for bar in self.bars)

    @property
    def is_melody_only(self) -> bool:
        """Whether every bar of the cycle attacks only at the written melody's onsets."""
        return all(bar.melody and not bar.positions for bar in self.bars)

    @property
    def sustain(self) -> bool:
        """Whether the chord's rhythm states sustained melody onsets only."""
        return any(bar.sustain for bar in self.bars)

    def at(
        self, bar: Optional[int] = None, first_bar: Optional[int] = None
    ) -> BarRhythm:
        """The cycle's segment for `bar`, and the tune for a bar before the cycle.

        `bar` is the number the position falls in and `first_bar` the **first complete
        bar** of the form - where segment 1 lands. A bar before it is not a bar of the
        cycle: it takes the tune's own onsets, so an accompaniment begins with the form
        rather than with the pickup. A **silent** figure is silent there too: `none`
        asks that the layer never attack, so it has no bar of the form to begin in.
        `bar=None` takes the first segment, and `first_bar=None` is a figure placed on
        no form, which runs on absolute phase from bar 1 because nobody said where the
        form is.
        """
        if bar is None:
            return self.bars[0]
        if self.is_none:
            return BarRhythm()
        if first_bar is not None and bar < first_bar:
            return BarRhythm(melody=True)
        origin = 1 if first_bar is None else first_bar
        return self.bars[(bar - origin) % len(self.bars)]

    def __str__(self) -> str:
        return RHYTHM_BAR_SEPARATOR.join(str(bar) for bar in self.bars)


def _period(bars: Sequence[BarRhythm]) -> int:
    """The shortest cycle `bars` repeats with: `1,3:1,3` and `1,3` are one request.

    A period has to divide the count - `1:1,3` is a two-bar figure whose first bar
    differs from its second, not a one-bar one - so the search is over the divisors.
    """
    for length in range(1, len(bars)):
        if len(bars) % length:
            continue
        if all(bar == bars[index % length] for index, bar in enumerate(bars)):
            return length
    return len(bars)


def parse_rhythm(
    argument: str,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> Rhythm:
    """A `Rhythm` from the grammar: `melody`, `none`, `every-beat`, positions.

    Between bars, `RHYTHM_BAR_SEPARATOR` joins the segments into a cycle:
    `1,3:none:1,4and` is a three-bar figure. A segment **replaces** the default
    rather than adding to it, so `1and` is only the stab and `melody,1and` is the
    harmonisation plus the stab. `none` is the one token that cannot be combined,
    and a position the metre lacks is refused rather than dropped: `3` in a 2/2 bar
    is a question about the metre. An empty segment is refused too - `1,3::1` is a
    typo rather than a request for silence, and `none` is how a silent bar is
    spelled.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    group_starts(beats_per_bar, lengths)  # validates that the groups partition the bar
    text = argument.strip().lower()
    if not text:
        return Rhythm()
    return Rhythm(bars=_parse_bars(text.split(RHYTHM_BAR_SEPARATOR), len(lengths)))


def _parse_bars(segments: Sequence[str], felt_beats: int) -> Tuple[BarRhythm, ...]:
    """The cycle's bars, each read from its own segment.

    A refusal names the bar it is about whenever the figure has more than one, which
    is when "position '5' asks for felt beat 5" leaves the caller guessing which.
    """
    named = len(segments) > 1
    bars: List[BarRhythm] = []
    for number, segment in enumerate(segments, start=1):
        try:
            bars.append(_parse_bar(segment, number, felt_beats))
        except ValueError as error:
            if not named:
                raise
            raise ValueError(f"rhythm bar {number}: {error}") from None
    return tuple(bars)


def _parse_bar(segment: str, number: int, felt_beats: int) -> BarRhythm:
    """One bar of the cycle: its tokens, or why it is not a bar."""
    text = segment.strip()
    if not text:
        raise ValueError(
            f"rhythm bar {number} is empty; spell a silent bar 'none'"
        )
    return _bar_from_tokens([part.strip() for part in text.split(",")], felt_beats)


def _bar_from_tokens(tokens: Sequence[str], felt_beats: int) -> BarRhythm:
    """One bar's tokens as a `BarRhythm`: `none` alone, melody or sustain, or positions.

    `sustain` names the tune's sustained onsets - only a melody note running at least
    one felt beat is harmonised there. When `melody` is also named, `sustain` is inert
    and the bar behaves as plain `melody`.
    """
    if RHYTHM_NONE in tokens:
        if len(tokens) > 1:
            raise ValueError(
                "a rhythm that says 'none' cannot name 'melody', 'sustain' or a position"
            )
        return BarRhythm()
    melody = RHYTHM_MELODY in tokens
    sustain = RHYTHM_SUSTAIN in tokens
    if melody:
        sustain = False
    return BarRhythm(
        melody=melody,
        sustain=sustain,
        positions=_rhythm_positions(tokens, felt_beats),
    )


def _rhythm_positions(tokens: Sequence[str], felt_beats: int) -> Tuple[float, ...]:
    """Every position the tokens name, in token order; `melody`/`none` name none."""
    return tuple(
        position
        for token in tokens
        if token not in (RHYTHM_MELODY, RHYTHM_NONE, RHYTHM_SUSTAIN)
        for position in _positions_for(token, felt_beats)
    )


def _positions_for(token: str, felt_beats: int) -> Tuple[float, ...]:
    """The felt beats one token names: `every-beat` expands, a position is one."""
    if token == RHYTHM_EVERY_BEAT:
        return tuple(float(number) for number in range(1, felt_beats + 1))
    return (_parse_position(token, felt_beats),)


def _parse_position(token: str, felt_beats: int) -> float:
    """One position token as a felt-beat number, or why it is not one."""
    match = _RHYTHM_POSITION.fullmatch(token)
    if match is None:
        if "&" in token:
            raise ValueError(
                f"{token!r} is not a rhythm position: the midpoint of a felt beat is "
                f"spelled 'and' - {token.replace('&', 'and')} - because an unquoted "
                f"'&' is a shell's background operator, so the token never reaches us"
            )
        raise ValueError(
            f"Unknown rhythm token {token!r}; expected melody, none, every-beat "
            f"or a position such as 1, 1and or lastand"
        )
    named = match.group("beat")
    beat = felt_beats if named == _RHYTHM_LAST else int(named)
    if not 1 <= beat <= felt_beats:
        raise ValueError(
            f"rhythm position {token!r} asks for felt beat {beat}, but this bar "
            f"has {felt_beats}"
        )
    offset = dict(_SUBDIVISIONS)[match.group("subdivision") or ""]
    return beat + offset


def _format_position(position: float) -> str:
    """A felt-beat number as its one canonical token, e.g. `1and`."""
    whole = int(position)
    offset = round(position - whole, 6)
    for token, value in _SUBDIVISIONS:
        if abs(offset - value) <= BEAT_EPSILON:
            return f"{whole}{token}"
    raise ValueError(f"rhythm position {position!r} has no canonical spelling")


def felt_beat(
    beat: float,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> float:
    """`beat` counted in felt beats: its group's index plus one, and the fraction.

    The second eighth of a 6/8 bar is felt beat `1.333...`, the fourth eighth is
    `2.0`, and a group of three has its midpoint at `1.5` - so `and` names the
    pulse's midpoint rather than a fixed half-beat. A simple metre, whose groups
    are one beat, therefore reduces to the beat number unchanged.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    starts = group_starts(beats_per_bar, lengths)
    index = len(lengths) - 1
    for candidate, length in enumerate(lengths):
        if beat < starts[candidate] + length:
            index = candidate
            break
    return index + 1.0 + (beat - starts[index]) / lengths[index]


def rhythm_beats(
    segment: BarRhythm,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> Tuple[float, ...]:
    """The bar-relative beats one bar's rhythm names, on this metre's grid.

    `segment` is **one bar** of a rhythm - `Rhythm.at` answers which bar a cycle puts
    at a place in the form - because a position is a place in a bar, not a figure.
    The inverse of `felt_beat`: a position is a felt-beat number, so `1and` is beat
    1.5 of a 4/4 bar and beat 2.5 of a 6/8 one - one request, and the metre decides
    where it lands. A position naming a felt beat this bar does not have is dropped
    rather than clamped; `parse_rhythm` refuses it at the door.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    starts = group_starts(beats_per_bar, lengths)
    beats: List[float] = []
    for position in segment.positions:
        index = int(position) - 1
        if index >= len(starts):
            continue
        beats.append(starts[index] + (position - index - 1) * lengths[index])
    return tuple(sorted(set(beats)))


def snap_to_felt_grid(
    beat: float,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
    subdivisions: int = SUBDIVISIONS_PER_FELT_BEAT,
) -> float:
    """Snap `beat` to the nearest subdivision of its felt beat.

    The grid is per felt beat: `felt` position `1 + k/subdivisions` maps back into
    whatever raw-beat group contains it, so mixed groupings (`3+2` in 5/4) keep their
    alternating spacing. Every grid point lands exactly on the `TICKS_PER_BEAT`
    lattice, so `_tick_key` stays an exact dedup key.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    starts = group_starts(beats_per_bar, lengths)
    felt = felt_beat(beat, beats_per_bar, grouping)
    felt_int = int(felt)
    frac = felt - felt_int
    k = round(frac * subdivisions)
    index = felt_int - 1
    if k == subdivisions:
        # Rounded up to the next group's start.
        index += 1
        k = 0
    if index < 0:
        return float(starts[0])
    if index >= len(lengths):
        return float(starts[-1] + lengths[-1])
    return starts[index] + (k / subdivisions) * lengths[index]

