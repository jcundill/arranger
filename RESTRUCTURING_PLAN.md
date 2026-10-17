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

## Phase 9 — Decompose the high-complexity functions (in progress)

Extract-method only, with the suite and a byte-identical `make demo` as the
oracle. Ten commits landed; `bass.py` fell from **31/202 to 16/82**,
`movement.py` from **23/360 to 9/251**, `routes.py` from **13/229 to 6/97** and
`tabstaff.py` from **27/396 to 17/195**.

- `_walking_bass_line` (202) → `_located_onsets`, `_anchor_only_line`,
  `_walked_beats`, `_filled_harmony`, `_anchor_flags`, `_next_anchor_pitches`,
  `_walk_note`. The candidate order in `_walk_note` is untouched: `min` is
  first-wins and that is the walk's tie-break.
- `place_bass` (159) → `_thumb_frame` (the geometry a thumb is placed against,
  including the held-shape widening) and `_best_thumb_fret` (enumeration and
  ranking).
- `_bass_slots` (132) → `_located_slots`, `_gridless_slots`,
  `_melody_entries`, `_bass_only_entries`. The extraction found a real coupling:
  the second pass had been appending to the first pass's list.
- `_harmonised_step` (360 lines, 22 parameters) → `_prepare_or_rescue` (prepare,
  rescue, promote, rest), `_held_candidates`, `_selection_for`, `_Selection`
  (`chosen`, `palette`, `narrower_than`) and `_emit_step`. **360 → 96 lines, CC
  23 → 8, six parameters.** `_promoted_fill` lost seven keywords to the context,
  and its docstring's dangling half-sentence was completed with the rule it was
  describing (the retry uses the whole search space, not the palette that just
  failed).
- `comping_step` (229 lines, CC 13) → `_comping_harmony` (the onset-only
  substitution, as a `_CompingHarmony` value), `_comping_candidates` (the arity
  and the two derived flags), `_comping_choice` and `_emit_comping_step`:
  **229 → 97 lines, CC 13 → 6**. The `if`/`else` that fell through to the melody
  route is now an early `return False`, so the handled case reads linearly.
- `_slot_state` (197 lines, CC 14, 11 parameters) → `_SlotInputs` (the nine
  arrangement-level words, bound once by the loop), `_tune_silent_plan`,
  `_carried_role` and `_texture_grips`: **197 → 89 lines, CC 14 → 6, three
  parameters.** The module ceiling did not move, because it is a max: complexity
  is `prepare_step` and length `arrange_progression`.
- `prepare_step` (131 lines, CC 17) → `_SearchWindow` (strings, grips, frets),
  `_Voiced` (candidates, sounding pitch, what the strategy did), `_voices_for`
  (generation plus the octave-down rescue) and `_apply_non_chord_tone` (sustain,
  substitution, and the strategy that is recorded even when it settles nothing):
  **131 → 75 lines, CC 17 → 6.** The public signature is unchanged, so the
  corpus loader and the callers do not move.
- `arrange_progression` (340 lines, CC 13) → `_loop_slots` (the walk's union, or
  one slot per triple read defensively), `_context_for` (the route-facing view,
  derived from the plan and the inputs), and `_route_slot` (the five-route
  dispatch, whose `continue`s become `return`s): **340 → 251 lines, CC 13 → 3.**
  The 251 is 150 lines of contract docstring; the body is ~90. `_SlotInputs`
  gained the five knobs the context needed, so there is still one value rather
  than a second parameter object.

Phase 9's engine cuts are complete. Remaining in the round:

- 9.6, done. The ASCII staff and the HTML page, in three stages:
  - `format_tab_staff` → `_marker_columns` (repeat/ending signs keyed by the column
    a bar opens at) and `_StaffGrid` (the grid's own rules), then the two row
    builders `line` and `string_line` became methods on that value:
    **396 → 195 lines, CC 27 → 17.**
  - `_staff_columns` → `_placed_steps`, `_dedupe_onsets`, `_fill_rests`,
    `_collapse_holds`: **131 lines / CC 21 → 47 / 3**, with each stage's comment
    block moved to the stage it explains.
  - `format_tab_html` → `_html_head`, `_html_measure_spans`,
    `_html_measure_opening`: **174 → 136 lines, CC 27 → 14.**
  `tabstaff.py`'s budget falls from 27/396 to **17/195**; its parameter ceiling is
  unchanged at 13 (`format_tab_html`), which is a public signature.

Next: 9.7, the importers — three of its four targets have landed.

**9.7 done so far (three commits).**

- `headxml._read_notes` (239 / CC 29) is `_NotesWalk`, a value carrying the cursor,
  the chord in force, the `<chord>` group being assembled and the things skipped,
  with `run()` / `measure()` / `element()` / `harmony()` / `note()` / `flush()`.
  The 12-parameter `_flush_group` folded into it as `flush()` — its only caller was
  the walk, and every argument was one of its fields. `_read_notes` is four lines.
- `headxml`'s repeat rules are stated once: `_ending_membership`,
  `_repeat_start_positions`, `_repeat_target` (the jump-target rule used to be
  spelled twice, and both spellings had to agree about the no-forward-repeat case).
  `_expand_repeats` is now its four stages — `_played_bars`, `_played_markers`, and
  the identity check that keeps a repeatless score byte-identical.
- `tabgp._build_song` (223 / CC 27) is `_measure_header` (the per-bar key rule and
  its two traps) and `_strike_notes` (the beat's notes: the step's own frets, the
  ringing shape on a `bass_only` beat, and the tie-only-where-the-claim-holds rule).
  It returns the new `ringing`, so that state stops being threaded through two loops.

**Budget after 9.7 so far:** `headxml.py` 29/239/12 → **17/125/10**;
`tabgp.py` 27/223 → **19/151**.

- `tabxml.score_events` (168 / CC 24) is four named rules — `_placed_steps`,
  `_group_span`, `_capped_span`, `_group_shares` — because the loop body had been
  one paragraph where place / span / cap / divide / floor / give-the-floor-back /
  leftover-as-rest interleaved, and none could be checked against the others.

**9.7 is DONE.** Budgets after it: `headxml.py` 17/125/10, `tabgp.py` 19/151/13,
`tabxml.py` 12/176/12. `tabxml`'s ceiling is `_build_part`, `tabgp`'s is
`_apply_repeat_markers` (64 / CC 19) — both ordinary now rather than outliers, so
neither needs a 9.7-style cut. `tabxml._build_part` (176 lines, CC 12) is the
longest function left in the tree; if a later phase touches the MusicXML writer,
that is where to start.

**Then:** 9.7's `tabxml` half, and Phases 11–15 as listed below — the
`slots` → `chords` move, the `grips` split, the `bass`/`movement` splits (with
`ORDER` and the AGENTS map in the same commit), the test split (move
`BUT_NOT_FOR_ME` to `tests/support.py` **first**, it is cross-imported), and the
docs/hygiene pass (the three stale `best_voicing` references in `docs/engine.md`,
the 1107 count, `RESTRUCTURING_PLAN.md` → `docs/history/` with a retirement
header).
- 9.7: `headxml._read_notes` (239), `_expand_repeats`, `_expand_play_order`;
  `tabxml.score_events`/`_build_part`; `tabgp._build_song`.
- Then Phases 11–15 (hygiene included: `docs/engine.md` still says
  `best_voicing` in three places for a function deleted long ago; the source
  docstring is fixed, the document is not).
- `tabstaff.format_tab_staff` (396), `format_tab_html`.
- `headxml._read_notes` (239), `_expand_repeats`, `_expand_play_order`;
  `tabxml.score_events`/`_build_part`; `tabgp._build_song`.

## Phase 10 — Parameter objects (DONE, moved before 9.3)

`arranger/context.py` holds `SlotContext` - the seventeen facts both routes
receive about one slot - and sits after `tuning` in the DAG. Both routes now
take `(arrangements, slot, context, *, ...)`: `_harmonised_step` is **22 → 6**
parameters and `comping_step` **23 → 7**, with each route's own policy words
left as keywords. The bodies destructure the context at the top; that costs one
line in each, the round's only budget increase (stated in the commit), and the
9.3/9.4 splits remove the need for it.

`arranger.context` joins the submodule names in `arranger.__all__`, because the
module-boundary test counts any public name it can see in the facade.

## Phase 11 — Move the chord-symbol vocabulary to `chords` (planned)

`promote_slash_chord`, `midi_to_note_name`, `bass_pitch_class`, `slash_bass` and
`slash_bass_cost` move from `slots` to `chords`. `slash_bass_cost` is pure
integer arithmetic - verified, it does not call `voicing_cost` - and
`promote_slash_chord` already needs `chords`' tables, so both edges point up and
no `ALLOWED_EDGES` entry is needed. The payoff is the edge this deletes:
`render` stops importing `slots`, so presentation no longer depends on the
arrangement pipeline.

## Phase 12 — Split `grips` at the placement seam (the table half landed)

**Landed:** `arranger/grip_tables.py` holds the seventeen table names and the queries
over them, and `grips` imports them. Measured: `grips.py` 2286 → 1767 lines, the new
module 542 lines (526 of them sliced body), and no behaviour moved - the demo is byte-identical and the
488 tests that read the grip tables (grips, generated grips, voicings, placement,
texture, comping, bass, walking bass, explanations) pass unchanged.

Three things the move taught, worth having before the placement half:

- **`_BOTTOM_FOUR` had to become `BOTTOM_FOUR`.** It is read by `_string_sets_for` in
  `grips` and by `supported_string_sets` in `grip_tables`, so the move turned a module
  local into a cross-module import - which the encapsulation rule refuses for a private
  name. Renaming it is the fix, not an allowlist entry.
- **A closure over the module's own definitions is not the whole closure.** The script
  that verified the seam followed `Name` nodes that resolved to *top-level definitions*,
  so it could not see that `supported_string_sets` reads
  `MELODY_STRING_CHOICES_FULL`, which `grips` imports from `tuning`. Ruff found it
  immediately (`F821`), and the next split should treat free names from the import
  block as part of the closure rather than discover them at lint time.
- **The relative-import rewrite must carry `level`.** `ast.ImportFrom.module` is
  `grips` and `level` is 1 for `from .grips import x`; reading `module` alone rewrote
  package imports as `from grips import ...`. Ruff does not flag that, because a
  top-level module named `grips` could legitimately exist - only an import of the
  package catches it, which is what `tests/test_package_dag.py` and the facade test are
  for. The repair is the same script with `'.' * level + module`.

**The placement half landed too**, in `arranger/grip_place.py` (337 lines):
`frets_in_span`, `Placement`, the string-set membership table, `candidate`,
`place_template`, `search_shape`, `ShapeSnapshot` / `snapshot` / `voicing_from_snapshot`,
the `_searched_shape` memo and `place_shape`. `grips.py` is 1454 lines and imports the
seven names it calls. The seam held exactly as measured: `Placement` is constructed in
the three request builders, `frets_in_span` and the snapshot trio are read by the comping
memo as well, and no placement function calls a generation function.

Nine names became public because a module other than their own imports them -
`Placement`, `candidate`, `search_shape`, `ShapeSnapshot`, `snapshot`,
`voicing_from_snapshot`, `frets_in_span`, `place_template`, `place_shape`. Two stayed
private because nothing outside reads them: `_searched_shape` (the memo, reached through
`place_shape`) and `_SUPPORTED_STRING_SETS` (built once, read twice in the module). The
rule is the one the meter enforces, read at its narrowest.

Three things to carry into the rest of the work:

- **A substring rename is not an identifier rename.** Replacing `_candidate` with
  `candidate` also clipped `get_octave_down_candidates` into
  `get_octave_downcandidates` in three files. The suite caught it with an
  `AttributeError` on the first test that called it, but the repair cost a round trip and
  the general fix is a token-level rename (`tokenize`, exact `NAME` match), not
  `str.replace`. The same edit renamed `_voicing_from_snapshot` twice over, because
  `_snapshot` is a suffix of it - so the order of replacements is not a substitute for
  matching whole tokens either.
- **A facade test that names a home has to move with the name.**
  `test_the_facade_reexports_the_public_surface` hardcodes nine `(public name, home
  module, attribute)` rows so the identity half is testable; `supported_string_sets`
  moved home to `grip_tables`, and the row is the record of that.
- **`grips`' budget did not move because its worst function did not.** `_shell_voicing`
  is 22 / 128 / 9 and stays in `grips`; `grip_place`'s own worst is `candidate` at
  19 / 66 / 5. A split that lowers the total but leaves every ceiling where it was is
  still a success - the ceilings describe the worst function, not the file.

The demo is byte-identical and `make chart-audit` still agrees with the tables.


The seam was verified by an AST closure before any text moved, and it holds: the
closure of `supported_string_sets`, `grip_pluck_count`, `thumb_safe_grips`,
`finger_skip_count`, `stated_tones`, `comping_string_sets`, `INTERVAL_NAMES`,
`GRIP_PREFERENCE`, `GRIP_STRING_SETS`, `TONE_PRIORITY`, `SHELL_DEGREES`,
`RIGHT_HAND_STRINGS`, `THUMB_REACH_STRINGS`, `_BOTTOM_FOUR`,
`SINGLE_NOTE_STRING_SETS` and `BASS_VOICE_STRING_SETS` contains **only those
names** - not one reference reaches a template rule, a family generator or a
placement helper. So `grip_tables.py` can be lifted out whole, and the two
private string-set tables (`SINGLE_NOTE_STRING_SETS`, `BASS_VOICE_STRING_SETS`)
are theirs rather than `grips`'s.

Two findings from that measurement:

- **`_INTERVAL_CLASSES` and `INTERVAL_NAMES` were each defined twice**, identically,
  the second copy sitting after `_place_template` - so the first was dead and no
  test could see it. The duplicate is deleted, and `tests/test_structure.py` now
  carries a fourth meter (`TestTheSingleDefinition`) that fails on any top-level
  name bound twice in one module. It is the guard a *copy-instead-of-cut* split
  needs, which is why it landed before the split.
- **`best_voicing` was not deleted.** The earlier handoff said `docs/engine.md`
  named a function that no longer exists; it does exist as
  `cost.best_voicing`, which `melody_alone` calls. The stale name is
  `VoiceLeadingEngine._best_voicing`, and both `docs/engine.md` and `tuning.py`
  already say the loop no longer calls it. **Nothing to fix in Phase 15's doc
  half** - do not invent the edit.

The split itself is the next session's first task and wants a full context: it
moves ~450 lines and updates every importer of the table names
(`__init__`, `texture`, `bass`, `cost`, `decisions`, `harmony`, `render`,
`movement`, `steps`, `options`, `grip_chart`, `fingers`, twelve test files). Do
it as one commit that changes `test_package_dag.ORDER` and the AGENTS module map
in the same edit. `build/`, `dist/`, `*.egg-info/` and `wjazzd.db` were deleted
from the working copy, so a grep no longer finds stale copies of these modules
under `build/lib`.

`grip_tables.py` (string sets, spans, tone tables, `supported_string_sets`,
`thumb_safe_grips`, `comping_string_sets`, `INTERVAL_NAMES`) and
`grip_place.py` (`Placement`, `candidate`, `search_shape`, `place_shape`, the
memo, `place_template`) below `grips`, which keeps the template rules, the four
family generators and the public surface. Verified before starting:
`_place_template` takes a template as an argument and never calls
`_templates_for`, so placement does not depend on generation. `bass` imports
`comping_string_sets` from the new table module; `grip_chart` keeps importing
`grips.drop2_template_for`.

## Phase 13 — Split `bass` and `movement` (landed)

Three modules, one commit each, and every seam was measured closed before anything
moved: no part of a lifted block reads a definition that stays behind.

| module | from | to | what moved |
|---|---|---|---|
| `bass_rules.py` | `bass` 1507 | `bass` 1125 | the vocabulary, capacities and refusals |
| `resolution.py` | `movement` 2020 | `movement` 1325 | the six axis resolvers and their two result types |
| `slot_plan.py` | `movement` | (same) | `Carried`, `SlotPlan`, `SlotInputs`, `slot_state` and three helpers |

Public names are the ones another module imports: `resolve_knobs`, `resolve_policies`,
`Carried`, `SlotInputs`, `SlotPlan`, `slot_state`. `_Knobs`/`_Policies` stayed private
because only the resolver that returns them names them, as did `_tune_silent_plan`,
`_carried_role` and `_texture_grips`.

Four things this phase taught:

- **The local-import apology is a seam detector.** Two `bass` functions carried
  `from .grip_tables import ...` *inside* the function with a comment saying the
  module did not depend on the grip tables "for its own sake". In `bass_rules` that
  sentence is false - the capacity question is the module's whole job - so the imports
  became module-level and ruff deleted the redundant local ones. When an import needs
  a paragraph of apology, ask whether the function belongs somewhere else.
- **Importers moved; the vocabulary was not re-exported from `bass`.** That departs
  from this document's earlier wording, for the reason Phase 11 gives: a re-export is
  a second binding of one fact. `from arranger import BASS_RULES` is unchanged, because
  the facade already exports it.
- **A stale premise is re-pointed, never deleted** (trap 5).
  `test_the_engine_is_the_only_step_loop` read `movement`'s source to prove the engine
  calls each shared decision; two of them moved to `slot_plan`, so it now reads the
  three modules the engine is made of. Its docstring records the third re-pointing and
  why deleting the two names from `DECISIONS` would have retired the check instead.
- **A facade name needs a binding, not just membership.** `grip_place` in `__all__`
  without an import of it is a pyright `reportUnsupportedDunderAll` warning that no
  test can see, because the suite imports the package and the attribute does exist at
  runtime. Every new module is now added to `from . import (...)` as well.

`make demo` stayed byte-identical through all three, and the AST comparison of each
moved block against its original found only the intended renames and the deleted
local imports.

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
- Phase 9: DONE (seventeen commits) — 9.1–9.6 the engine and both tab
  renderers, 9.7 the three importers. No module's ceiling is an outlier any more.
- Phase 10: DONE (moved before 9.3). 1107 tests OK, ruff 0, pyright 0/0,
  demo byte-identical.
- Phase 11: DONE (one commit) — the five chord-symbol helpers moved from
  `slots` to `chords`, which **deletes the `render -> slots` edge**. `slots` now
  imports the three it still calls, and `headxml` imports the two it uses from
  `arranger.chords`. 1107 tests OK (skipped=2), ruff 0, pyright 0/0, demo
  byte-identical. The doc references naming the old home were updated in the same
  commit, including one test docstring.
- Phases 12-15: planned, in the order above.
