# Restructuring plan — jazz-arranger

Living document. Updated at the end of every phase; each phase keeps
`make check` green (baseline: 1098 tests OK, skipped=2, ruff 0,
pyright 0 errors 0 warnings). Measured invariants are never changed.

## Goal

Restructure for coupling/cohesion/SOLID quality without changing any
measured behaviour. The DAG (Phase 5) is the strongest asset; keep it,
tighten encapsulation at the facade and module boundaries, and split
the two god modules (`textures`, `movement`) by axis and route.

## Measured invariants (never change)

1. `voicing_cost` 7-tuple order + `VOICING_COST_CRITERIA` wording/order.
2. `GRIP_PREFERENCE` order — it is the cost-tuple tie-break.
3. `TONE_PRIORITY` per-quality rows + `SHELL_DEGREES`.
4. Explanations invariant: every choice recorded on the step, composed by
   `render`; `tests/test_explanations.py` table. New clause → new table
   witness in the same commit.
5. Playability invariants in `tests/test_grips.py` (string sets,
   span ≤ `GRIP_MAX_SPAN`, ≤4 fingers, melody on soprano, no fifth fret
   from held shape).
6. DAG `ORDER` + `test_package_dag.py` — new modules inserted in the
   right layer with justified `ALLOWED_EDGES`.
7. `melody_alone_case` four kinds (`none`/`texture`/`nc`/`rest`) and
   guard ordering (trap 12).
8. Public facade spellings stable (`VoiceLeadingEngine`, `Voicing`,
   `ArrangementStep`, `ChordParser`, `format_progression`, …).

## Phase 1 — Shrink the facade (DONE, committed 903694b)

Removed the 8 private-name re-exports from `arranger/__init__.py`:
`_bass_harmony`, `_comping_no_room_reason`, `_place_bass`,
`_walking_bass_line`, `_interval_offsets`, `_metric_weight`,
`_roles_for_slot`, `_step_annotation`. Privates now imported from home
modules by tests; facade re-exports public surface only.

Files changed: `arranger/__init__.py`, `tests/test_bass.py`,
`tests/test_texture.py`, `tests/test_non_chord_tones.py`,
`tests/test_tab_rendering.py`, `tests/test_walking_bass.py`.

Validation: 1098 OK (skipped=2), ruff 0, pyright 0/0. No `arranger._<private>`
accesses remain.

## Phase 2 — Split `textures.py` by axis (DONE)

`textures.py` (1129 lines) has been replaced by four focused modules. Each
imports only what sits above it in the DAG.

| New module | Contents |
|---|---|
| `arranger/parts.py` | `PARTS_AUTO`, `PART_*`, `PART_NAMES`, `parse_parts`, `resolve_parts`, `parts_have_*`, `parts_has_melody_only` |
| `arranger/harmony.py` | `HARMONY_*`, `parse_harmony`, `resolve_harmony`, `harmony_allowed`, `HARMONY_AUTO_POLICIES` |
| `arranger/grid.py` | `GRID_*`, `GridPattern`, `grid_resolutions`, `parse_grid`, `resolve_grid`, `on_grid`, `grid_allowed`, `grid_defers_to_melody`, `TICKS_PER_BEAT`, `SUB`, `LAST`, `ALL` |
| `arranger/texture.py` | `TEXTURE_STYLES`, `TEXTURE_ARITY`, `TARGET_BEATS`, `FILL_THINNING`, `THIN_ENTRIES`, `FILL_ONLY_EXCLUDED`, `families_*`, `texture_arity`, `derived_arity`, `comping_arity`, `texture_palette`, `_metric_weight`, `_roles_for_slot` |

Consumers repointed: `options`, `movement`, `bass`, `slots`, `cli`, `steps`,
`__init__`, plus `tests/test_texture.py` and `tests/test_walking_bass.py`.
`arranger/textures.py` deleted. DAG `ORDER` updated; `ALLOWED_EDGES` reduced to
the one edge that genuinely points down (`decisions`).

Validation: 1098 tests OK (skipped=2), ruff 0, pyright 0/0.

## Phase 3 — Split `movement.py` by route (NEXT)

`movement.py` (2526 lines) = step loop + all route handlers. Extract each
route into its own module; `movement.arrange_progression` becomes a thin
dispatcher.

| New module | Contents |
|---|---|
| `arranger/comping.py` | `_comping_step` + non-chord-tone routing |
| `arranger/texture_step.py` (name TBD) | `_texture_step` / fill logic |
| `arranger/no_chord.py` | `_no_chord_step` |
| `arranger/melody_alone.py` | `_melody_alone_shape`, `_melody_alone_step` |
| `arranger/bass_merge.py` | `_attach_bass`, `_place_bass` consumers |

Each route's guards local and testable in isolation (addresses trap 12).
Five routes, `melody_alone_case` kinds, `SLASH_BASS_SATISFIED`,
`_attach_bass` semantics, `Palette`/`inside_window` recording unchanged.

## Phase 4 — Encapsulate module internals (fix private leakage)

- `cost._best_voicing`: promote to public `best_voicing` (justified edge
  `decisions`→`cost`) or move the call into `cost`.
- `render` imports `_slash_bass`/`bass_pitch_class`/`slash_bass_cost`
  from `slots`: move helpers so `render` reads from step fields rather
  than reaching into slot internals.
- `decisions.select_step_voicing` calls `cost._best_voicing` — make edge
  explicit/justified or route through a public cost selection function.

Selection rule (`voicing_cost` tuple order) unchanged.

## Phase 5 — Optional abstractions (only if demonstrated need)

`CostFunction` protocol for substituting the selector. YAGNI unless a
caller needs a different cost rule; the library has one cost rule and it
is an invariant.

## Phase 6 — Consolidate import style

Make `slots.py` use relative imports like the rest of the engine, or vice
versa, consistently. Verify no cycle introduced (`slots` is after
`steps` in `ORDER` and constructs `VoiceLeadingEngine`).

## Validation after every phase

- `make check` (lint → typecheck → test): same counts as baseline.
- `make demo`: eyeball printed tabs.
- Any moved count is the signal (per AGENTS.md).
- Commit each logical change separately; never push.

## Status

- Phase 1: DONE (committed 903694b).
- Phase 2: DONE (pending commit).
- Phase 3: next.
- Phases 4-6: not started.