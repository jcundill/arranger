"""The grid axis: when each part sounds in the bar.

`Rhythm` is the public request - direct positions in felt beats - while
`GridPattern` and `GRID_PATTERNS` are the named presets the engine still runs.
`grid.py` imports `PART_MELODY`, `PART_BASS`, `PART_CHORD` from `parts`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .grouping import group_offbeat, group_starts
from .parts import PART_BASS, PART_CHORD, PART_MELODY

GRID_EVERY_NOTE = "every_note"
GRID_FREDDIE = "freddie"
GRID_CHARLESTON = "charleston"
GRID_JOE_PASS = "joe_pass"
GRID_FINAL_AND = "final_and"
GRID_WALK = "walk"
GRID_ANCHORS = "anchors"

TICKS_PER_BEAT = 24
SUB = 12
LAST = 0
ALL = -1


@dataclass(frozen=True)
class GridPattern:
    positions: Tuple[Tuple[int, int], ...]
    bar_relative: bool


GRID_PART_PATTERNS: Dict[str, Tuple[str, ...]] = {
    PART_MELODY: (GRID_EVERY_NOTE,),
    PART_CHORD: (
        GRID_EVERY_NOTE,
        GRID_FREDDIE,
        GRID_JOE_PASS,
        GRID_FINAL_AND,
        GRID_CHARLESTON,
    ),
    PART_BASS: (GRID_EVERY_NOTE, GRID_WALK, GRID_ANCHORS),
}

GRID_STYLES: Tuple[str, ...] = tuple(
    f"{part}:{pattern}"
    for part, patterns in GRID_PART_PATTERNS.items()
    for pattern in patterns
)

GRID_DEFAULT = f"{PART_MELODY}:{GRID_EVERY_NOTE}"

GRID_PATTERNS: Dict[str, GridPattern] = {
    GRID_EVERY_NOTE: GridPattern(positions=(), bar_relative=True),
    GRID_FREDDIE: GridPattern(positions=((ALL, 0),), bar_relative=True),
    GRID_FINAL_AND: GridPattern(positions=((LAST, SUB),), bar_relative=True),
    GRID_CHARLESTON: GridPattern(positions=((1, 0), (2, SUB)), bar_relative=False),
    GRID_JOE_PASS: GridPattern(positions=((ALL, SUB),), bar_relative=False),
    GRID_WALK: GridPattern(positions=((ALL, 0),), bar_relative=True),
}

GRID_TIMELINE_PATTERNS: Tuple[str, ...] = (GRID_ANCHORS,)


def grid_rows(grid: str) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    for row in grid.split(","):
        part, _sep, pattern = row.partition(":")
        rows[part.strip()] = pattern.strip()
    return rows


def grid_chord_pattern(grid: str) -> str:
    return grid_rows(grid).get(PART_CHORD, GRID_EVERY_NOTE)


def grid_bass_pattern(grid: str) -> str:
    return grid_rows(grid).get(PART_BASS, GRID_EVERY_NOTE)


def grid_defers_to_melody(grid: str) -> bool:
    pattern = grid_chord_pattern(grid)
    if pattern in GRID_TIMELINE_PATTERNS:
        return False
    row = GRID_PATTERNS.get(pattern)
    return row is None or not row.positions


def parse_grid(argument: str) -> str:
    text = argument.strip().lower()
    if not text:
        return GRID_DEFAULT
    rows: Dict[str, str] = {}
    for row in text.split(","):
        part, sep, pattern = row.partition(":")
        part, pattern = part.strip(), pattern.strip()
        if not sep or not part or not pattern:
            raise ValueError(
                f"Unknown grid row {row!r}; expected PART:PATTERN, any of "
                f"{', '.join(GRID_STYLES)}"
            )
        if part not in GRID_PART_PATTERNS:
            raise ValueError(
                f"Unknown grid part {part!r}; expected any of "
                f"{', '.join(GRID_PART_PATTERNS)}"
            )
        if pattern not in GRID_PART_PATTERNS[part]:
            raise ValueError(
                f"Unknown {part} grid {pattern!r}; expected any of "
                f"{', '.join(GRID_PART_PATTERNS[part])}"
            )
        rows[part] = pattern
    return ",".join(f"{part}:{rows[part]}" for part in sorted(rows))


def grid_positions(
    grid: str,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> Tuple[Tuple[int, Tuple[float, ...]], ...]:
    """The positions `grid` names, as `(felt beat, positions)` rows.

    The first number is a **felt beat** - a group index, not a denominator unit - and
    the positions are absolute beat numbers. With no grouping every unit is its own
    group, which is the table this library shipped with; a 12/8 bar's `freddie` is
    four stabs on beats 1, 4, 7 and 10 rather than twelve on every eighth.

    `SUB` is the group's **offbeat** (`group_offbeat`): half a beat for a one-beat
    group, the last unit for a longer one. That is what keeps `charleston`, `joe_pass`
    and `final_and` musically right in a compound metre without changing a single
    position in a simple one.
    """
    pattern = grid_chord_pattern(grid)
    row = GRID_PATTERNS.get(pattern)
    if row is None:
        return ()
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    starts = group_starts(beats_per_bar, lengths)
    return _group_positions(lengths, starts, row)


def _group_indices(group: int, count: int) -> Tuple[int, ...]:
    """The zero-based group indices one table row names."""
    if group == ALL:
        return tuple(range(count))
    if group == LAST:
        return (count - 1,)
    # A literal group the metre does not have is dropped rather than clamped:
    # clamping would silently turn `charleston` asked of a 2/2 bar into a
    # *different* figure that happens to fit.
    return (group - 1,) if 1 <= group <= count else ()


def _position_offset(ticks: int, length: int) -> float:
    """A row's second number as beats from its group's start."""
    return group_offbeat(length) if ticks == SUB else ticks / TICKS_PER_BEAT


def _group_positions(
    lengths: Tuple[int, ...],
    starts: Tuple[float, ...],
    row: "GridPattern",
) -> Tuple[Tuple[int, Tuple[float, ...]], ...]:
    """One pattern's rows, expressed on the felt-beat grid.

    Split from `grid_positions` so the rules for `ALL`, `LAST`, a literal group and
    `SUB` are three short functions rather than a branchy loop inside a public one.
    """
    beats: Dict[int, List[float]] = {}
    for group, ticks in row.positions:
        for index in _group_indices(group, len(lengths)):
            offset = _position_offset(ticks, lengths[index])
            beats.setdefault(index + 1, []).append(starts[index] + offset)
    return tuple(
        (number, tuple(sorted(set(positions))))
        for number, positions in sorted(beats.items())
    )


def on_grid(
    beat: Optional[float],
    grid: str,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> bool:
    if beat is None or grid_defers_to_melody(grid):
        return True
    if grid_chord_pattern(grid) in GRID_TIMELINE_PATTERNS:
        return True
    target = float(beat)
    return any(
        abs(target - position) <= BEAT_EPSILON
        for _number, positions in grid_positions(grid, beats_per_bar, grouping)
        for position in positions
    )


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


def grid_allowed(
    grid: str,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> Tuple[bool, str]:
    pattern = grid_chord_pattern(grid)
    if grid_defers_to_melody(grid) or pattern in GRID_TIMELINE_PATTERNS:
        return True, ""
    if grid_positions(grid, beats_per_bar, grouping):
        return True, ""
    row = GRID_PATTERNS[pattern]
    if row.bar_relative:
        return False, (
            f"grid=chord:{pattern} places no chord in a bar of {beats_per_bar} "
            f"beats, and it is a bar-relative pattern, which should resolve in any "
            f"metre - so this is a defect in the pattern rather than a mismatch with "
            f"the metre"
        )
    return False, (
        f"grid=chord:{pattern} is a metre-relative figure and places no chord in "
        f"a bar of {beats_per_bar} beats: it is right, or it is a figure of another "
        f"metre asked of this one. Try a bar-relative pattern such as 'freddie' or "
        f"'final_and', or grid=melody:every_note"
    )


def resolve_grid(
    grid: str,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> str:
    parsed = parse_grid(grid)
    allowed, reason = grid_allowed(parsed, beats_per_bar, grouping)
    if not allowed:
        raise ValueError(reason)
    return parsed


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
RHYTHM_LAST = "last"

#: The subdivisions the grammar names, and the fraction of a felt beat each is.
#: Ordered so a position's one canonical spelling sorts as `1`, `1e`, `1&`, `1a`
#: - the musical order rather than the alphabet's.
_SUBDIVISIONS: Tuple[Tuple[str, float], ...] = (
    ("", 0.0),
    ("e", 0.25),
    ("&", 0.5),
    ("a", 0.75),
)

#: A position token: a felt-beat number or `last`, optionally followed by one of
#: the subdivisions. A decimal such as `1.5` is deliberately not accepted: it
#: names a time rather than a place on the metre's grid and cannot express `last&`.
_RHYTHM_POSITION = re.compile(r"^(?P<beat>last|\d+)(?P<subdivision>[&ea])?$")


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
                    f"its e/&/a subdivisions"
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

        The comparison is in felt beats, so `&` is the midpoint of the group that
        contains `beat` rather than half a denominator unit. `None` is not a
        position: it is a note whose rhythm the caller did not supply.
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

    A list **replaces** the default rather than adding to it, so `1&` is only the
    stab and `melody,1&` is the harmonisation plus the stab. `none` is the one
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
        raise ValueError(
            f"Unknown rhythm token {token!r}; expected melody, none, every-beat "
            f"or a position such as 1, 1& or last&"
        )
    named = match.group("beat")
    beat = felt_beats if named == RHYTHM_LAST else int(named)
    if not 1 <= beat <= felt_beats:
        raise ValueError(
            f"rhythm position {token!r} asks for felt beat {beat}, but this bar "
            f"has {felt_beats}"
        )
    offset = dict(_SUBDIVISIONS)[match.group("subdivision") or ""]
    return beat + offset


def _format_position(position: float) -> str:
    """A felt-beat number as its one canonical token, e.g. `1&`."""
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
    `2.0`, and a group of three has its midpoint at `1.5` - so `&` names the
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

