"""The request's rhythm: when each part sounds in the bar.

`Rhythm` is the public request - direct positions in felt beats - and the rest of
this module is the metre's arithmetic under it: `felt_beat` and `rhythm_beats`
convert between a position and a bar-relative beat, and `beat_offset` puts two
bars' beats on one line. `grid.py` imports `group_starts` from `grouping`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .grouping import group_starts

TICKS_PER_BEAT = 24


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
RHYTHM_NONE = "none"
RHYTHM_EVERY_BEAT = "every-beat"
_RHYTHM_LAST = "last"

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
class Rhythm:
    """When a layer attacks, as direct positions in the bar's felt beats.

    `positions` are **felt-beat numbers**: felt beat 1 is `1.0`, the midpoint of its
    group is `1.5`, and the second felt beat is `2.0` whatever the group's length.
    That is what makes one rhythm the same request in 2/2, 4/4 and 6/8, where an
    absolute beat number is not. `melody` is not a position: it names the written
    melody's own onsets, and a list may name it *and* positions - the harmonisation
    plus a stab.
    """

    melody: bool = False
    positions: Tuple[float, ...] = ()
    none: bool = False

    def __post_init__(self) -> None:
        if self.none and (self.melody or self.positions):
            raise ValueError(
                "a rhythm that says 'none' cannot name 'melody' or a position"
            )
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
    def wants_melody(self) -> bool:
        """Whether the layer attacks at every written melody onset."""
        return self.melody

    @property
    def is_none(self) -> bool:
        """Whether the layer never sounds."""
        return self.none or not (self.melody or self.positions)

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
        tokens = [RHYTHM_MELODY] if self.melody else []
        tokens.extend(_format_position(position) for position in self.positions)
        return ",".join(tokens)


def parse_rhythm(
    argument: str,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> Rhythm:
    """A `Rhythm` from the grammar: `melody`, `none`, `every-beat` or positions.

    A list **replaces** the default rather than adding to it, so `1and` is only the
    stab and `melody,1and` is the harmonisation plus the stab. `none` is the one
    token that cannot be combined, and a position the metre lacks is refused
    rather than dropped: `3` in a 2/2 bar is a question about the metre.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    group_starts(beats_per_bar, lengths)  # validates that the groups partition the bar
    text = argument.strip().lower()
    if not text:
        return Rhythm(none=True)
    tokens = [part.strip() for part in text.split(",")]
    return Rhythm(
        melody=RHYTHM_MELODY in tokens,
        positions=_rhythm_positions(tokens, len(lengths)),
        none=RHYTHM_NONE in tokens,
    )


def _rhythm_positions(tokens: Sequence[str], felt_beats: int) -> Tuple[float, ...]:
    """Every position the tokens name, in token order; `melody`/`none` name none."""
    return tuple(
        position
        for token in tokens
        if token not in (RHYTHM_MELODY, RHYTHM_NONE)
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
    rhythm: Rhythm,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> Tuple[float, ...]:
    """The bar-relative beats a rhythm names, on this metre's grid.

    The inverse of `felt_beat`: a position is a felt-beat number, and the beat it
    falls on is its group's start plus the fraction of that group's length. So
    `1and` is beat 1.5 of a 4/4 bar and beat 2.5 of a 6/8 one - one request, and
    the metre decides where it lands. A position naming a felt beat this bar does
    not have is dropped rather than clamped; `parse_rhythm` refuses it at the door,
    so this is the read-back of an already-validated value.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    starts = group_starts(beats_per_bar, lengths)
    beats: List[float] = []
    for position in rhythm.positions:
        index = int(position) - 1
        if index >= len(starts):
            continue
        beats.append(starts[index] + (position - index - 1) * lengths[index])
    return tuple(sorted(set(beats)))

