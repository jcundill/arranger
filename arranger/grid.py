"""The grid axis: when each part sounds in the bar.

`grid.py` imports `PART_MELODY`, `PART_BASS`, `PART_CHORD` from `parts`.
"""

from __future__ import annotations

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

