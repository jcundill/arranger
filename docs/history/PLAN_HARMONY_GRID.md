# Plan: Harmony-only 1/12-felt-beat grid (lighter version)

**Status:** IMPLEMENTED — all tests pass.

## Goal

Converge the harmony-position producers in `headxml.py` onto a single placement grid: **12 equal subdivisions of each felt beat**. This is the smallest grid that expresses both thirds (triplets) and quarters (`e`/`and`/`a`) exactly.

Melody stays exact — `head_skeleton` and `arrange_progression` are untouched. Only the harmony layer in `arrange_xml_head` is grid-converged.

## Why 12 subdivisions per felt beat

- Thirds: a triplet eighth is `1/3` of a felt beat → grid index 4 of 12.
- Quarters: `e`=`1/4`→index 3, `and`=`1/2`→index 6, `a`=`3/4`→index 9.
- LCM(3,4)=12 is the minimal grid containing both vocabularies exactly.

`TICKS_PER_BEAT = 24` (ticks per raw beat) is already exact for grid points: `1/12 of a felt beat = group_length/12 raw beats = 2 × group_length ticks`, always an integer. So `_tick_key` (24 ticks/beat dedup key) stays exact with no new rounding error. Mixed groupings (e.g. `3+2` in 5/4) keep alternating spacing because the grid is generated per felt beat, not as a uniform raw-beat stride.

## Scope — files to touch

**`arranger/grid.py`** — add only:

- `SUBDIVISIONS_PER_FELT_BEAT = 12`
- `snap_to_felt_grid(beat, beats_per_bar, grouping=None, subdivisions=12) -> float`
  - Converts raw beat → felt beat via existing `felt_beat()`
  - Rounds to nearest subdivision
  - Converts back to raw beat via inverse of `felt_beat` (same arithmetic as `rhythm_beats` for a single position, using `group_starts`)
  - Handles mixed groupings correctly

No existing function modified or removed. `TICKS_PER_BEAT`, `_SUBDIVISIONS`, `felt_beat`, `rhythm_beats` all stay.

**`headxml.py`** — converge harmony producers onto the grid:

| Function | Change |
|---|---|
| `chord_slots` / `_generated_beats` | Generate candidates at every `1/12` of a felt beat instead of `_bar_resolution`'s adaptive stride |
| `rhythm_slots` | Snap each requested position (felt-beat space) to the grid before returning |
| `fill_slots` / `_felt_starts` | Snap felt-starts inside rests to grid positions |
| `_comp_only_timeline` | Uses `rhythm_slots`, follows automatically |
| `_tick_key` | Unchanged — already exact |
| `head_skeleton` | Unchanged — melody stays exact |
| `_merge_chord_slots`, `_unioned`, `chord_at`, `melody_at` | No structural change; comparisons become exact on the shared lattice |

`_bar_resolution` and `grid_resolutions` remain for backwards compatibility but `chord_slots` no longer calls them.

## Scope — files NOT touched

- `arranger/movement.py` — `_loop_slots`, `arrange_progression` unchanged; caller-supplied timings respected exactly
- `arranger/slot_plan.py` — `_chord_here`, `_chord_attacks`, `slot_state` unchanged
- `arranger/decisions.py` — `melody_alone_case` unchanged; `on_grid` still means "does the chord rhythm attack here?"
- `arranger/routes.py`, `arranger/harmonised_route.py`, `arranger/comp_line_route.py` — route dispatch unchanged
- `arranger/cost.py`, `arranger/grips.py`, `arranger/step_prepare.py` — voicing cost and selection unchanged
- `arranger/bass.py`, `arranger/bass_merge.py`, `arranger/bass_place.py` — walking bass unchanged
- `arranger/options.py` — axes derivation unchanged

## What this simplifies

- Harmony has **one placement rule** instead of four (`chord_slots` adaptive, `rhythm_slots` felt, `fill_slots` felt-starts, `_comp_only_timeline` rhythm_slots).
- `_tick_key` becomes an honest placement coordinate rather than just a dedup rounding key.
- `_merge_chord_slots` / `_unioned` compare positions guaranteed on the same lattice — exact integer equality.

## What this does NOT fix

- The axes tangle (texture/bass/parts/grouping/chord_on/bass_on/chord_fills) is entirely untouched — that lives in `options.py`, `route_dispatch.py`, `routes.py`, `cost.py`.
- Melody remains exact and off-grid, so the union still exists between melody slots and grid slots.
- `arrange_progression` callers passing off-grid timings still get off-grid melody slots; only `arrange_xml_head` is grid-converged.

## Tests expected to be affected

- `tests/test_headxml_timeline.py`
- `tests/test_chord_attack.py`
- `tests/test_comping.py`
- `tests/test_headxml_arrangement.py`
- `tests/test_bass_hold.py`
- `tests/test_walking_bass.py`
- Pinned-tab tests across `test_*.py` (harmony attack positions will move)
- `tests/test_rhythm.py` — expected unaffected (grammar unchanged)

## Verification

After implementation:
1. `make test-features` — both halves must pass; pinned tabs regenerated where harmony attacks moved.
2. `make check` — lint + typecheck + test, all OK.
3. `make demo` — read printed tabs for sanity.

## Changes made

### `arranger/grid.py`
- Added `SUBDIVISIONS_PER_FELT_BEAT = 12` constant
- Added `snap_to_felt_grid(beat, beats_per_bar, grouping=None, subdivisions=12) -> float` — snaps a raw beat to the nearest 1/12 of its felt beat, handling mixed groupings correctly. Every grid point is exact on the `TICKS_PER_BEAT` lattice.

### `headxml.py`
- Updated imports: added `SUBDIVISIONS_PER_FELT_BEAT`, `snap_to_felt_grid`
- `_generated_beats()`: now generates positions at every 1/12 of a felt beat instead of `_bar_resolution`'s adaptive stride
- `rhythm_slots()`: snaps each requested beat to the grid before use
- `_felt_starts()`: snaps each felt beat to the grid before use
- `_tick_key`, `head_skeleton`, `_bar_resolution`, `grid_resolutions` unchanged (backwards compatibility)

### Test updates (expectations moved due to finer grid)
- `tests/test_headxml_arrangement.py`: `test_the_generated_grid_is_the_four_pulses` — checks felt beats are on grid, 48 positions per bar
- `tests/test_headxml_timeline.py`: 4 tests updated for finer grid positions
- `tests/test_tab_rendering.py`: wrapped step count 107 → 112
- `tests/meta_structure.py`: `grid.py` budget (8, 23, 3) → (8, 29, 4)
- `tests/meta_explanations.py`: comping voice count 1271 → 2815

### Not changed (by design)
- `arrange_progression`, `head_skeleton`, melody timing — melody stays exact
- Axes logic (texture/bass/parts/grouping) — untouched
- Route dispatch, cost tuple, voicing selection — untouched

## Test results
- 1403 feature tests: OK (skipped=2)
- 91 meta tests: OK
- Ruff lint: All checks passed
- Pyright: No errors in modified files (pre-existing `musthe` import issues only)
- Demo: runs cleanly

## Open question (resolved: lighter version)

Melody quantization was considered and **rejected** for this change. `head_skeleton` keeps its explicit anti-quantization stance; every written note keeps its exact `(bar, beat)`.
