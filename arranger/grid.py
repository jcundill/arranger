"""The grid axis: when each part sounds in the bar.

`grid.py` imports `PART_MELODY`, `PART_BASS`, `PART_CHORD` from `parts`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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


def grid_positions(grid: str, beats_per_bar: int) -> Tuple[Tuple[int, Tuple[float, ...]], ...]:
    pattern = grid_chord_pattern(grid)
    row = GRID_PATTERNS.get(pattern)
    if row is None:
        return ()
    beats: Dict[int, List[float]] = {}
    for beat, ticks in row.positions:
        if beat == ALL:
            numbers: Tuple[int, ...] = tuple(range(1, beats_per_bar + 1))
        elif beat == LAST:
            numbers = (beats_per_bar,)
        else:
            # A literal beat the metre does not have is dropped rather than clamped:
            # clamping would silently turn `charleston` asked of a 2/2 bar into a
            # *different* figure that happens to fit.
            numbers = (beat,) if 1 <= beat <= beats_per_bar else ()
        for number in numbers:
            beats.setdefault(number, []).append(number + ticks / TICKS_PER_BEAT)
    return tuple(
        (number, tuple(sorted(set(positions))))
        for number, positions in sorted(beats.items())
    )


def on_grid(beat: Optional[float], grid: str, beats_per_bar: int) -> bool:
    if beat is None or grid_defers_to_melody(grid):
        return True
    if grid_chord_pattern(grid) in GRID_TIMELINE_PATTERNS:
        return True
    target = float(beat)
    return any(
        abs(target - position) <= BEAT_EPSILON
        for _number, positions in grid_positions(grid, beats_per_bar)
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


def grid_allowed(grid: str, beats_per_bar: int) -> Tuple[bool, str]:
    pattern = grid_chord_pattern(grid)
    if grid_defers_to_melody(grid) or pattern in GRID_TIMELINE_PATTERNS:
        return True, ""
    if grid_positions(grid, beats_per_bar):
        return True, ""
    row = GRID_PATTERNS[pattern]
    if row.bar_relative:
        return False, (
            f"grid=chord:{pattern} places no chord in a {beats_per_bar}-beat bar, and "
            f"it is a bar-relative pattern, which should resolve in any metre - so "
            f"this is a defect in the pattern rather than a mismatch with the metre"
        )
    return False, (
        f"grid=chord:{pattern} is a metre-relative figure and places no chord in "
        f"{beats_per_bar}/4: it is right, or it is a figure of another metre asked "
        f"of this one. Try a bar-relative pattern such as 'freddie' or "
        f"'final_and', or grid=melody:every_note"
    )


def resolve_grid(grid: str, beats_per_bar: int) -> str:
    parsed = parse_grid(grid)
    allowed, reason = grid_allowed(parsed, beats_per_bar)
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

