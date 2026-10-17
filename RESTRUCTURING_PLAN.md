# Restructuring plan — jazz-arranger

Living document. Updated at the end of every phase; each phase keeps
`make check` green (baseline after Phase 7: 1107 tests OK, skipped=2, ruff 0,
pyright 0 errors 0 warnings). Measured invariants are never changed.

## Goal

Restructure for coupling/cohesion/SOLID quality without changing any
measured behaviour. The package DAG is the strongest asset; keep it,
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
9. `tests/test_structure.py`: budgets only shrink, and every library module has
   one. A new module states its ceiling; it does not inherit one.
10. The five front ends (`tabstaff`, `tabxml`, `tabgp`, `headxml`, `grip_chart`)
    stay **flat modules** with those names, and `py-modules` ships exactly the
    four renderer/importer names. `grip_chart` is a repository tool.
11. `tabgp` imports `guitarpro` **inside a function** and nowhere else. This is
    the LGPL-3.0 boundary, not a style choice: a package `__init__` or a
    module-scope import would make PyGuitarPro a runtime dependency of the
    library. `tests/test_optional_extras.py` holds both halves.

## Phase 1 — Shrink the facade (DONE, committed 903694b)

Removed the 8 private-name re-exports from `arranger/__init__.py`:
`_bass_harmony`, `_comping_no_room_reason`, `_place_bass`,
`_walking_bass_line`, `_interval_offsets`, `metric_weight`,
`roles_for_slot`, `_step_annotation`. Privates now imported from home
modules by tests; facade re-exports public surface only.

Files changed: `arranger/__init__.py`, `tests/test_bass.py`,
`tests/test_texture.py`, `tests/test_non_chord_tones.py`,
`tests/test_tab_rendering.py`, `tests/test_walking_bass.py`.

Validation: 1098 OK (skipped=2), ruff 0, pyright 0/0. No `arranger._<private>`
accesses remain.

## Phase 2 — Split `textures.py` by axis (DONE, committed c6ed08a)

`textures.py` (1129 lines) has been replaced by four focused modules. Each
imports only what sits above it in the DAG.

| New module | Contents |
|---|---|
| `arranger/parts.py` | `PARTS_AUTO`, `PART_*`, `PART_NAMES`, `parse_parts`, `resolve_parts`, `parts_have_*`, `parts_has_melody_only` |
| `arranger/harmony.py` | `HARMONY_*`, `parse_harmony`, `resolve_harmony`, `harmony_allowed`, `HARMONY_AUTO_POLICIES` |
| `arranger/grid.py` | `GRID_*`, `GridPattern`, `grid_resolutions`, `parse_grid`, `resolve_grid`, `on_grid`, `grid_allowed`, `grid_defers_to_melody`, `TICKS_PER_BEAT`, `SUB`, `LAST`, `ALL` |
| `arranger/texture.py` | `TEXTURE_STYLES`, `TEXTURE_ARITY`, `TARGET_BEATS`, `FILL_THINNING`, `THIN_ENTRIES`, `FILL_ONLY_EXCLUDED`, `families_*`, `texture_arity`, `derived_arity`, `comping_arity`, `texture_palette`, `metric_weight`, `roles_for_slot` |

Consumers repointed: `options`, `movement`, `bass`, `slots`, `cli`, `steps`,
`__init__`, plus `tests/test_texture.py` and `tests/test_walking_bass.py`.
`arranger/textures.py` deleted. DAG `ORDER` updated; `ALLOWED_EDGES` reduced to
the one edge that genuinely points down (`decisions`).

Validation: 1098 tests OK (skipped=2), ruff 0, pyright 0/0.

## Phase 3 — Split `movement.py` by route (DONE, committed 2c5198e)

`movement.py` (2526 lines) was the step loop plus every route handler. Two modules
split out, plus one helper whose home was the wrong file:

- **`arranger/bass_merge.py`** (committed cb86f65) — `_attach_bass`,
  `_next_resolution_melody`.
- **`arranger/melody_alone.py`** — `_sounding_melody`, `_melody_alone_shape`,
  `_rescue_melody_alone`, `_demoted_to_melody_alone`: every route that sounds the tune
  by itself picks its position here.
- **`arranger/routes.py`** — `_last_sounding_step`, `_rest_step`,
  `_texture_fill_step`, `_no_chord_step`, `_comping_step`. `_harmonised_step` stays in
  `movement` because it is the orchestrating route and retries through `prepare_step`;
  moving it beside the handlers would need `routes` -> `movement`, a cycle.
- **`_resolve_substitute_harmony`** moved to `chords.py` as the public
  `resolve_substitute_harmony`: it composes `is_chord_tone` and
  `resolve_non_chord_tone`, so its home is the module that owns them, and both the
  melody route and the comping route import it from there.

`movement.py` is 1762 lines (from 2526). The five routes, `melody_alone_case` kinds,
`SLASH_BASS_SATISFIED`, `_attach_bass` semantics and `Palette`/`inside_window`
recording are unchanged — the moved bodies are byte-for-byte slices of the original.

## Phase 4 — Encapsulate module internals (DONE, committed 5ad9fe1)

- `cost._best_voicing` was the selector's private argmin, imported by `decisions`.
  Renamed to **`cost.best_voicing`** (public); `decisions`, `movement` and
  `steps` call the public name. `VoiceLeadingEngine._best_voicing` is kept as
  the published spelling tests use, forwarding to `cost.best_voicing`.
- `slots._slash_bass` was reached from `render`. Renamed to
  **`slots.slash_bass`** and added to `slots.__all__`; `render` imports the
  public name. The renderer's own `_slash_bass_clause` stays private.
- Live docs and comments repointed.

Selection rule (`voicing_cost` tuple order) unchanged.

## Phase 5 — Optional abstractions (not required)

`CostFunction` protocol for substituting the selector. **Judged YAGNI**: the
library has one cost rule and it is an invariant, so a protocol would add an
indirection with no caller. Revisit only when a second selector is needed.

## Phase 6 — Consolidate import style (DONE, committed 1517073)

`slots.py` was the only engine module using absolute imports. Converted to
relative imports, which also makes its dependencies visible to
`test_package_dag` (it had been invisible to the AST check). Every edge points
up, so no `ALLOWED_EDGES` entry is needed.

## Round 2 — measure, then decompose

Round 1 made the boundaries right; round 2 makes the insides right. Two
constraints shape it:

- **the five front ends stay flat files with their names**, because `tabgp`'s
  lazy PyGuitarPro import is the licensing boundary (invariants 10 and 11);
- **no new top-level modules**, so renderer work is in-file extraction, and any
  shared vocabulary moves *into* `arranger/` only where the DAG can own it.

## Phase 7 — Baseline, ratchet and licensing gate (DONE)

Two new test modules, no production change.

`tests/test_structure.py` measures every function three ways - complexity
(decision points, with nested closures measured where they are defined), length
and parameter count - and seeds a per-module ceiling at today's worst. It also
enforces encapsulation in both directions: 41 private imports across 29 names
are the recorded debt (including `render.print_step` and `tuning._MUTED_CELL`
reached from the facade), and an entry that stops being used fails too.
`arranger/options.py` has no function, which is why the table requires an entry
for every module rather than defaulting: a default is a ceiling nobody chose.

`tests/test_optional_extras.py` closes the licensing gap - the music21 laziness
test had no PyGuitarPro twin. It blocks `guitarpro` in a subprocess, asserts
`arranger`/`tabstaff`/`tabgp` still import, and scans `tabgp.py` so the one
import stays inside a function. It also pins the five front ends as flat
modules and `py-modules` to the four shipped names.

Validation: 1107 tests OK (skipped=2), ruff 0, pyright 0/0; `make demo`
untouched.

## Phase 8 — Publicise the cross-module surface (DONE)

Five commits, 41 imported private names → 0. Nothing moved and no behaviour
changed; the names said what the import graph already depended on.

- `bass`: `Slot`, `walking_slots`, `place_bass`, `held_shape`, `previous_bass`.
- `routes`/`melody_alone`/`bass_merge`: `comping_step`, `rest_step`,
  `texture_fill_step`, `no_chord_step`, `last_sounding_step`,
  `rescue_melody_alone`, `demoted_to_melody_alone`, `melody_alone_shape`,
  `sounding_melody`, `attach_bass`, `next_resolution_melody`.
- `tuning`: `note_name`, `cells_from_frets`, `MUTED_CELL`, `STAFF_CELL_WIDTH`.
  `tabstaff`'s duplicate width constant is deleted rather than renamed twice, and
  the facade's `MUTED_CELL` re-export went with it: no caller used it through
  `arranger`, and a rendering detail is not API.
- axes/grips: `metric_weight`, `roles_for_slot`, `BEAT_EPSILON`,
  `comping_string_sets`, `INTERVAL_NAMES`.
- front ends: `score_events` (**not** `events` - 46 existing identifiers would
  have been shadowed), `substitute_steps`, `drop2_template_for`, `print_step`.
  The facade imports the last one as `_print_step` so the demo does not widen the
  public surface, and `tests/test_non_chord_tones.py` now takes it from its home.

`ALLOWED_PRIVATE_IMPORTS` is empty, and the test still fails in both directions.
Validation: 1107 tests OK (skipped=2), ruff 0, pyright 0/0, `make demo`
byte-identical, `make chart-audit` clean.

## Phase 9 — Decompose the high-complexity functions (planned)

Extract-method only; no reordering of candidate generation (`min` is first-wins
in `bass_cost`, and generation order is the cost tuple's tie-break). Order:
`bass._walking_bass_line` (202 lines), `_place_bass`/`_bass_slots`;
`movement._harmonised_step` (359 lines, 22 parameters) and `_slot_state`;
`routes._comping_step` (228 lines, 23 parameters); `tabstaff.format_tab_staff`
(396 lines) and `format_tab_html`; `headxml._read_notes` (239),
`_expand_repeats`, `_expand_play_order`; `tabxml.score_events`/`_build_part`;
`tabgp._build_song`. Lower that module's budget in the same commit. Oracle: the
pinned tab strings, `test_step_loop_equivalence.py`, the MusicXML/GP5 round
trips, and a byte-identical `make demo`.

## Phase 10 — Parameter objects (planned)

New `arranger/context.py` after `options`: frozen `SlotContext` (the ~22 values
`_harmonised_step` and `_comping_step` both thread) and published
`ResolvedKnobs`. `prepare_step`/`arrange_progression` keep their keyword
signatures and build the context internally (trap 15: no positional reordering
at a facade). Ratchet: no function over 12 parameters.

## Phase 11 — Move the chord-symbol vocabulary to `chords` (planned)

`promote_slash_chord`, `midi_to_note_name`, `bass_pitch_class`, `slash_bass` and
`slash_bass_cost` move from `slots` to `chords`. `slash_bass_cost` is pure
integer arithmetic - verified, it does not call `voicing_cost` - and
`promote_slash_chord` already needs `chords`' tables, so both edges point up and
no `ALLOWED_EDGES` entry is needed. The payoff is the edge this deletes:
`render` stops importing `slots`, so presentation no longer depends on the
arrangement pipeline.

## Phase 12 — Split `grips` at the placement seam (planned)

`grip_tables.py` (string sets, spans, tone tables, `supported_string_sets`,
`thumb_safe_grips`, `comping_string_sets`, `INTERVAL_NAMES`) and
`grip_place.py` (`Placement`, `candidate`, `search_shape`, `place_shape`, the
memo, `place_template`) below `grips`, which keeps the template rules, the four
family generators and the public surface. Verified before starting:
`_place_template` takes a template as an argument and never calls
`_templates_for`, so placement does not depend on generation. `bass` imports
`comping_string_sets` from the new table module; `grip_chart` keeps importing
`grips.drop2_template_for`.

## Phase 13 — Split `bass` and `movement` (planned)

`bass_rules.py` (style vocabulary, capacities and refusals - pure policy, no
voicing logic) below `bass`; `resolution.py` (the six `_resolve_*` functions)
after `options`; `slot_plan.py` (`Carried`, `SlotPlan`, `slot_state`) after
`routes`. `movement` keeps `prepare_step`, `_harmonised_step` and
`arrange_progression`; `bass` keeps `BassNote`, `bass_cost`, the line, slots and
placement, and re-exports the rule vocabulary so `cli`/`__init__` spellings do
not move. `ORDER` and the AGENTS map change in the same commit.

## Phase 14 — Split the test monoliths (planned)

By the class clusters that already exist: `test_headxml` (3292 lines) →
parse / timeline / repeats / cli; `test_grips` → families / palette /
playability; `test_walking_bass` → line / placement / capacity;
`test_tab_rendering` → step / ascii / html / explanations; `test_comping` →
route / harmony / grid. `BUT_NOT_FOR_ME` moves to `tests/support.py` first: it
is imported from `tests.test_headxml` by two other test modules, which is the
test-suite form of the private-import problem Phase 8 fixes.

## Phase 15 — Documentation and hygiene (planned)

AGENTS routing rows and the module map for `context`, `grip_tables`,
`grip_place`, `bass_rules`, `resolution`, `slot_plan`, plus the new test count.
Remove the ignored local artefacts (`build/`, `dist/`, `*.egg-info/`, the 42 MB
`wjazzd.db`): invisible to the gate, visible to every search. When round 2
lands, this document moves to `docs/history/` with a retirement header pointing
at `docs/engine.md`.

## Validation after every phase

- `make check` (lint → typecheck → test): the test count moves only when a phase
  adds a test, and the budget table only shrinks.
- `make demo`: printed tabs byte-identical through Phases 8-13.
- `make chart-audit`: `common_grips.md` must not move.
- Any moved count is the signal (per AGENTS.md).
- Commit each logical change separately; never push.

## Status

Round 1:
- Phase 1: DONE (committed 903694b).
- Phase 2: DONE (committed c6ed08a).
- Phase 3: DONE — `bass_merge.py` (committed cb86f65), `melody_alone.py` and
  `routes.py` (committed 2c5198e); `resolve_substitute_harmony` moved to `chords.py`.
- Phase 4: DONE (committed 5ad9fe1).
- Phase 5: NOT REQUIRED (YAGNI).
- Phase 6: DONE (committed 1517073).
- Final gate: 1098 tests OK (skipped=2), ruff 0, pyright 0/0.

Round 2:
- Phase 7: DONE (two commits).
- Phase 8: DONE (five commits). 1107 tests OK (skipped=2), ruff 0, pyright 0/0,
  `make demo` byte-identical, `make chart-audit` clean.
- Phases 9-15: planned, in the order above.
