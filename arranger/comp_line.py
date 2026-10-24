"""The comp line: top-voice movement for the comping route.

Owns the home band and the rules that move the comp's top voice between
slots: the walk (direction + no-retrace), the approach, the opening and the
fill's interpolation. No vocabulary and no sentinel — there is nothing for a
caller to choose yet. Pure functions over pitch lists; the route that calls
them arrives in a later phase.
"""

from __future__ import annotations

from typing import List, Optional, Tuple


def home_band(fret_min: int, fret_max: int) -> Tuple[int, int]:
    """The register the comp lives in: ``fret_min + 1``, eight frets, clamped
    to the window."""
    lo = fret_min + 1
    hi = min(fret_min + 8, fret_max)
    if hi < lo:
        hi = lo
    return (lo, hi)


def band_middle(band: Tuple[int, int]) -> float:
    lo, hi = band
    return (lo + hi) / 2.0


def nearest_tone(target: int, candidates: List[int]) -> Optional[int]:
    if not candidates:
        return None
    return min(candidates, key=lambda t: (abs(t - target), t))


def _nearest_in_direction(
    pool: List[int], current: int, direction: int
) -> Optional[int]:
    if direction > 0:
        above = [t for t in pool if t > current]
        if above:
            return min(above, key=lambda t: (t - current, t))
        return None
    below = [t for t in pool if t < current]
    if below:
        return min(below, key=lambda t: (current - t, t))
    return None


def walk_step(
    current: int,
    direction: int,
    candidates: List[int],
    history: List[int],
) -> Tuple[Optional[int], int]:
    forbidden = set(history[-2:]) if history else set()
    pool = [t for t in candidates if t != current and t not in forbidden]
    chosen = _nearest_in_direction(pool, current, direction)
    new_direction = direction
    if chosen is None:
        new_direction = -direction
        chosen = _nearest_in_direction(pool, current, new_direction)
    if chosen is None and pool:
        chosen = min(pool, key=lambda t: (abs(t - current), t))
    return (chosen, new_direction)


def approach(prev_top: int, next_landing: int, candidates: List[int]) -> Optional[int]:
    """The approach tone: current chord's tone nearest ``next_landing``,
    never repeating ``prev_top``."""
    pool = [t for t in candidates if t != prev_top]
    if not pool:
        pool = list(candidates)
    return nearest_tone(next_landing, pool)


def chosen_top(
    *,
    candidates: List[int],
    band: Tuple[int, int],
    previous_top: Optional[int],
    history: List[int],
    direction: int,
    next_landing: Optional[int],
    is_opening: bool,
    is_fill: bool = False,
    fill_index: int = 0,
    fill_count: int = 1,
    target_register: Optional[int] = None,
) -> Tuple[Optional[int], int, str]:
    """Select the next comp-line top tone from candidates.

    Rules per docs/comp-line.md:
    - Opening: nearest tone to band middle
    - Walk: step from previous top in current direction, no retrace
    - Approach: nearest tone to next landing, != prev, with role "approach from above"/"from below"
    - Fill: interpolate previous register → target register over n positions, then narrow to nearest candidate
    """
    mid = (band[0] + band[1]) / 2.0
    if is_opening or previous_top is None:
        tone = min(candidates, key=lambda t: (abs(t - mid), t)) if candidates else None
        return tone, 1, "opening"
    if is_fill:
        if fill_count <= 1:
            targets = [target_register if target_register is not None else (next_landing or previous_top)]
        else:
            tgt = target_register if target_register is not None else (next_landing or previous_top)
            targets = [
                int(round(previous_top + (tgt - previous_top) * (i / (fill_count - 1))))
                for i in range(fill_count)
            ]
            targets[0] = previous_top
            targets[-1] = tgt
        target_val = targets[fill_index] if fill_index < len(targets) else targets[-1]
        tone = min(candidates, key=lambda t: (abs(t - target_val), t)) if candidates else None
        if next_landing is not None and tone is not None:
            role = "approach from above" if tone > next_landing else "approach from below"
        else:
            role = "approach"
        return tone, direction, role
    if next_landing is not None:
        pool = [t for t in candidates if t != previous_top] or list(candidates)
        tone = min(pool, key=lambda t: (abs(t - next_landing), t)) if pool else None
        if tone is not None and next_landing is not None:
            role = "approach from above" if tone > next_landing else "approach from below"
        else:
            role = "approach"
        return tone, direction, role
    # walk: step from previous top in current direction, no retrace
    forbidden = set(history[-2:]) if len(history) >= 2 else set(history)
    pool = [t for t in candidates if t != previous_top and t not in forbidden]
    chosen = None
    new_dir = direction
    if direction > 0:
        above = [t for t in pool if t > previous_top]
        if above:
            chosen = min(above, key=lambda t: (t - previous_top, t))
    else:
        below = [t for t in pool if t < previous_top]
        if below:
            chosen = min(below, key=lambda t: (previous_top - t, t))
    if chosen is None:
        new_dir = -direction
        if new_dir > 0:
            above = [t for t in pool if t > previous_top]
            if above:
                chosen = min(above, key=lambda t: (t - previous_top, t))
        else:
            below = [t for t in pool if t < previous_top]
            if below:
                chosen = min(below, key=lambda t: (previous_top - t, t))
    if chosen is None and pool:
        chosen = min(pool, key=lambda t: (abs(t - previous_top), t))
    role = "walk up" if (new_dir or 0) > 0 else "walk down"
    return chosen, new_dir, role


def opening_no_melody(candidates: List[int], band: Tuple[int, int]) -> Optional[int]:
    return nearest_tone(int(round(band_middle(band))), candidates)


def interpolate(previous_register: int, target: int, n: int) -> List[int]:
    """Fill interpolation: ``i == 0`` is the previous register, ``i == n-1``
    the target; intermediates are evenly spaced integers."""
    if n <= 1:
        return [target]
    out: List[int] = []
    for i in range(n):
        frac = i / (n - 1)
        val = previous_register + (target - previous_register) * frac
        out.append(int(round(val)))
    out[0] = previous_register
    out[-1] = target
    return out
