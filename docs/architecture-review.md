# Architecture Review — jazz-arranger

**Status:** working document. Updated as each stage lands.  
**Author:** Cline (AI coding agent), acting as software architect.  
**Gate:** `make check` (lint + typecheck + test) must stay green after every stage.

## Source of the review

Based on reading the repository layout, AGENTS.md, docs/engine.md,
docs/renderers.md, docs/dependency-dag.md, and the engine modules listed in the
routing table, plus the structural tests (`test_package_dag.py`,
`test_structure.py`, `test_front_end_dag.py`).

The strongest asset is the Phase 5 package refactor: a 4,290-line monolith is now
~30 modules in a strict dependency DAG, enforced mechanically by an AST test.
Immutability (frozen dataclasses), the lexicographic cost tuple, lazy optional
dependencies, and structural budgets are all sound.

The findings below concern coupling, cohesion, and SOLID at the value-object
and function level — where module-level layering is good but internal boundaries
are weaker.


## Findings

### F1 — Fat parameter objects / data clumps (SRP, ISP)

Three value objects carry far more than any single consumer needs:

- **`SlotContext`** (`arranger/context.py`) — ~17 fields. `harmonised_step` and
  `comping_step` "differ only in the three or four that name their own policy,"
  yet both receive the whole object. A route that only needs `(bar, beat,
  texture)` is coupled to `slash_bass_cost_for`, `bass_pcs`,
  `fret_min/fret_max`, etc.
- **`SlotInputs`** (`arranger/slot_plan.py`) — ~20 fields of "arrangement-level
  facts" passed to every slot's plan.
- **`ArrangeOptions`** (`arranger/options.py`) — ~20 fields, the knobs as one
  value. Frozen (good), but still a parameter-object god object.

**Consequence:** every function taking one of these is transitively coupled to
every field. A change to an unrelated field forces re-examination of every
caller.

### F2 — Bloated facade (ISP)

`arranger/__init__.py` is ~695 lines with ~130 names in `__all__`, re-exporting
individual constants *and* whole modules (`annotation`, `bass`, `cost`, `grips`,
`render`, `texture`, etc.). A client who only wants `Voicing` or
`VoiceLeadingEngine` receives the entire surface including renderers, CLI, and
the MusicXML importer. There is no `arranger.engine` / `arranger.request` /
`arranger.render` subdivision.

### F3 — "Orthogonal" axes are entangled (DIP, SRP)

`resolution.py`'s `_resolve_policies` resolves all six axes together with dense
implicit interdependencies:

- `texture → parts`, `texture → grouping`
- `harmony → parts`
- `grid → grouping`, `grid → parts`
- `bass → grid`

`harmony=` cannot be tested or reasoned about in isolation — resolving it
requires `parts`, `texture`, `grid`, and metre context.

### F4 — Hidden runtime circularity (DIP)

`arranger.__init__` lazily resolves `tabstaff` via `__getattr__` (PEP 562)
because `tabstaff` imports `arranger.tuning`. The AST DAG test passes (the

### F5 — `movement.py` is a central orchestrator with high fan-in (SRP)

`movement.py` imports from `bass`, `bass_merge`, `decisions`, `grips`,
`grouping`, `harmonised_route`, `options`, `resolution`, `routes`, `slot_plan`,
and `tuning`. It owns the slot loop, route dispatch, timing construction, and
bass merge. Routes are largely procedural functions; movement decides which one
runs.

### F6 — Tests coupled to private implementation details (encapsulation)

AGENTS.md states tests import from `arranger.bass`, `arranger.grips`,
`arranger.render`, `arranger.texture` rather than through `arranger`. The
structure test enforces this for library modules but *allows* tests to reach
privates. Refactoring a private helper's name/signature breaks tests even when
behavior is preserved — the suite is coupled to implementation, not contract.

### F7 — `steps.py` VoiceLeadingEngine is an anemic facade

Every method is a one-line forwarder to `grips`, `cost`, `chords`, `bass_merge`,
`movement`, or `step_prepare`. It holds no state. It exists purely to preserve
the `VoiceLeadingEngine.get_drop2_voicings(...)` spelling — a namespace dressed
as an object.

### F8 — Explanation invariant couples step fields to annotation/render contract

`ArrangementStep` fields (palette, role, weight, silence, chord_attack, etc.)
are read by `arranger/annotation.py` (804 lines) to compose trailing clauses.
Adding a field to the step potentially changes the rendered explanation. The
step is simultaneously a data record and part of the public text contract.

### F9 — Fossilized cost tuple (OCP)

`voicing_cost` returns a 7-element tuple asserted *positionally* in
`tests/test_grip_selection.py::TestVoicingCost`. A `SelectionCriteria` dataclass
exists but `voicing_cost` still takes 7 positional arguments and returns a
positional tuple. Extending/reordering the selection rule requires touching both
the function and positional tests.

### F10 — `grips.py` is a large hub (SRP)

1,468 lines: builders, candidate generators, layout-vs-search partitioning
(`_LAYOUT_GRIPS` / `_SEARCHED_GRIPS`), and the `CompingRequest` value object.
Many modules import `grips`, making it a fan-in hub.

import is function-local), but at runtime there is a cycle `arranger ↔ tabstaff`.
Documented in `dependency-dag.md` but not visible to a reader scanning imports.


## Recommendations (staged)

| Stage | ID | Change | Principle | Risk |
|---|---|---|---|---|
| 1 | P1 | Split fat parameter objects into small role-specific value objects | SRP, ISP | Low |
| 2 | P5 | Make test-to-private coupling explicit (TEST_SEAMS list) | Encapsulation | Low |
| 3 | P3 | Decouple axes in resolution (independent resolvers + explicit deps) | DIP, SRP | Medium |
| 4 | P2 | Subdivide facade into domain surfaces (`engine`, `request`, `render`) | ISP | Medium |
| 5 | P4 | Extract route dispatch from `movement.py` into a dispatcher | SRP | Medium |
| 6 | P6 | Document / eliminate the `arranger ↔ tabstaff` runtime cycle | DIP | Low |
| 7 | P7 | Make selection criteria extensible via `SelectionCriteria` | OCP | Medium |

Each stage: make change → add/update tests → run `make check` → demo if voicing
or voice-leading logic touched → commit separately.

---

## Stage log

| Stage | ID | Status | Notes |
|---|---|---|---|
| 1 | P1 | done | Split `SlotContext` into `SlotTiming`, `SlotHarmony`, `SlotIdentity`, `SlotState` + composed `SlotContext`. All route consumers updated. |
| 2 | P5 | done | TEST_SEAMS list in `tests/test_structure.py` — 25 private test-to-arranger reaches documented. New `TestTheTestSeams` test class asserts all reaches are recorded and no stale entries remain. |
| 3 | P3 | done | Each axis answered by one resolver in the module owning its vocabulary: `resolve_bass` moved to `bass_rules`, `texture.parse_texture` added, `TestTheAxisResolvers` holds the signatures to the dependency table. |
| 4 | P2 | planned | Facade surfaces |
| 5 | P4 | planned | Route dispatcher |
| 6 | P6 | planned | Runtime cycle |
| 7 | P7 | planned | Criteria extensibility |

---

## P1 — Complete: Split `SlotContext` (done)

**What changed:**

`SlotContext` went from 17 flat fields to 4 composed value objects + 7 route-specific fields:

| Before (flat) | After (composed) | Routes that read it |
|---|---|---|
| `bar`, `beat`, `duration` | `SlotTiming(bar, beat, duration)` | all |
| `name`, `chord_type`, `note_str`, `melody_note` | `SlotHarmony(name, chord_type, note_str, melody_note)` | all |
| `progression`, `index` | `SlotIdentity(progression, index)` | all |
| `role`, `weight`, `chord_attack` | `SlotState(role, weight, chord_attack)` | all |
| `fret_min`, `fret_max`, `texture`, `has_thumb`, `non_chord_tone`, `bass_pcs`, `slash_bass_cost_for` | kept on `SlotContext` | subset (comping / harmonised / melody-alone) |

**Files touched:**

- `arranger/context.py` — added `SlotTiming`, `SlotHarmony`, `SlotIdentity`, `SlotState`; refactored `SlotContext` to compose them
- `arranger/slot_plan.py` — `_slot_context` builds the new composed object; imports the 4 new value objects
- `arranger/routes.py` — all `context.X` → `context.timing.X` / `context.harmony.X` / `context.identity.X` / `context.state.X`
- `arranger/melody_alone.py` — same field-access updates
- `arranger/harmonised_route.py` — same + `replace(context, role=role)` → `replace(context, state=replace(context.state, role=role))`
- `arranger/movement.py` — `context.chord_type` → `context.harmony.chord_type`
- `docs/architecture-review.md` — this document

**Verification:**
- All modules import cleanly
- 799 tests pass across `test_progressions`, `test_comping`, `test_request`, `test_lone_bass`, `test_explanations`, `test_chord_fills`, `test_non_chord_tones`, `test_chord_attack`, `test_bass_hold`, `test_durations`, `test_bass_placement`, `test_bass_positions`, `test_harmony`, `test_parts`, `test_grid`, `test_grip_selection`, `test_grips`, `test_palette`, `test_fretboard`, `test_grouping`, `test_front_end_dag`, `test_package_dag`, `test_structure`, `test_fingers`, `test_placement`, `test_generated_grips`, `test_voicings`, `test_bass`, `test_chord_parser`, `test_html_rendering`
- `ruff check`: 0 errors
- `pyright`: 0 errors, 0 warnings on changed files

---

## P5 — Complete: TEST_SEAMS list (done)

**What changed:**

Added `TEST_SEAMS: Set[str]` to `tests/test_structure.py`, documenting every
private name a test file imports from an arranger module. Each entry is
`test_module -> arranger.module._private_name`, the same shape the encapsulation
meter uses for library modules.

25 seams recorded across 14 test files:

| Test file | Private names reached |
|---|---|
| `test_palette` | `arranger.annotation._criterion_phrase` |
| `test_explanations` | `arranger.annotation._omission_clause` |
| `test_bass` | `arranger.bass._bass_harmony`, `arranger.bass._walking_bass_line`, `arranger.bass_rules._comping_no_room_reason` |
| `test_walking_bass` | `arranger.bass._melody_in_force`, `arranger.bass._melody_timeline` |
| `test_comping` | `arranger.grips._comping_palette`, `arranger.grips._search_comping_voicings` |
| `test_generated_grips` | `arranger.grips._drop2_palette`, `arranger.grips._guide_tones` |
| `test_grips` | `arranger.grips._guide_tones`, `arranger.grips._close_stack_offsets`, `arranger.grips._interval_set_for_grip` |
| `test_grip_tables` | `arranger.grips._LAYOUT_GRIPS`, `arranger.grips._SEARCHED_GRIPS` |
| `test_placement` | `arranger.grip_place._searched_shape`, `arranger.grips._drop2_6432_request`, `arranger.grips._shell_request` |
| `test_texture` | `arranger.grips._interval_offsets` |
| `test_parts` | `arranger.render._step_cells` |
| `test_bass_hold` | `arranger.render._step_cells` |
| `test_bass_placement` | `arranger.render._step_cells` |
| `test_tab_rendering` | `arranger.render._format_step` |
| `test_headxml_repeats` | `arranger.cli._as_written` |

Added `_test_files()` and `_test_private_imports()` scanner functions that
mirror the library-module encapsulation meter, scanning `tests/` for
`from arranger.<module> import <_name>` patterns.

Added `TestTheTestSeams` test class with `test_every_test_private_reach_is_recorded`,
which fails in both directions:
- A new test-private reach not in TEST_SEAMS → caught
- A TEST_SEAMS entry no longer used → caught (prevents rot)

**Files touched:**

- `tests/test_structure.py` — added `TEST_SEAMS`, `_test_files`, `_test_private_imports`, `TestTheTestSeams`

**Verification:**
- `tests.test_structure`: all 8 tests pass (including the new one)
- `ruff check`: 0 errors
- `pyright`: 0 errors, 0 warnings

---

## P3 — Complete: independent axis resolvers (done)

**What changed:**

- **`resolve_bass(bass, parts, texture)` now lives in `bass_rules`.** It owns the
  note-rule vocabulary (`BASS_RULE_ROLES`), the refusal (`bass_allowed`) and the
  capacity arithmetic (`derived_arity`, `comping_capacity`), so the axis is
  answered beside its own tables rather than in the composition module. It takes
  the resolved `parts` selection rather than the flags derived from it, so the
  route, the arity and the melody-only case are decided from one fact.
- **`texture.parse_texture(argument)` is the texture axis's validator.** The
  refusal it produces existed three times - `texture_arity`, `roles_for_slot` and
  `resolution.resolve_knobs` - which is three sentences to keep in step. There is
  now one, in the module that owns `TEXTURE_STYLES`. `texture` has no `*_AUTO`
  sentinel, because the request always names a style, so the axis is validated
  rather than resolved.
- **`resolve_policies` composes, and reads as a composition.** Each line names the
  axis it answers and the values that answer depends on.

**The dependency graph, as the code states it:**

| axis | answered by | reads |
|---|---|---|
| `parts` | `parts.resolve_parts` after `parse_parts` | nothing |
| `texture` | `texture.parse_texture` | nothing (validated, not resolved) |
| `harmony` | `harmony.resolve_harmony` | `parts` |
| `bass` | `bass_rules.resolve_bass` | `parts`, `texture` |
| `grid` | `grid.resolve_grid` | the metre: `beats_per_bar`, `grouping` |

F3 named four edges; measurement found one. What the review called entanglement
was mostly the *request's* derivation, which happens before any axis exists:

- **`bass → grid` is not an edge.** The coupling is at the request level:
  `bass_on` is a rhythm and `bass_notes` a set of note rules, and
  `options._bass_policy` turns the pair into a policy - a rhythm that never
  attacks means no line, whatever it was asked to state. Once the request is
  resolved, the policy string reads neither the grid nor any rhythm.
- **`texture → parts` and `texture → grouping` are not edges either.**
  `resolve_request` derives `parts` from the two rhythms, and `grouping` is the
  metre's; the texture's arity is read later, by the palette, and never feeds
  back into either.
- **`harmony → parts` is real**, and so is `bass → parts`; both axes are claims
  about parts the selection may not take, which is why their refusals name the
  part that would work.

So the live graph is `parts → {harmony, bass}` plus `texture → bass`: acyclic,
one source per edge, and now pinned.

**The guard:** `tests/test_structure.py` carries `AXIS_RESOLVERS` (axis → owning
module and function), `AXIS_DEPENDENCIES` (the argument names that *are* the
graph) and `TestTheAxisResolvers`, which reads both from the AST and fails in
both directions - a resolver that moves out of its module, and one that grows a
dependency its row does not name. The same class asserts that
`resolve_policies` calls `_resolve_parts` before the three axes that read it: a
step whose parts happen to be right says nothing about which resolution ran
first, while a call moved above it is silent in every tab.

**Files touched:**

- `arranger/bass_rules.py` — `resolve_bass` (moved from `resolution`), import order
- `arranger/texture.py` — `parse_texture`; `texture_arity` and `roles_for_slot` route through it
- `arranger/resolution.py` — `_resolve_bass` deleted, texture validation delegated, imports pruned, `resolve_policies` docstring corrected (the parts axis, not "the melody axis")
- `tests/test_structure.py` — `AXIS_RESOLVERS`, `AXIS_DEPENDENCIES`, `POLICY_WIRING`, `TestTheAxisResolvers`

**Verification:**
- full suite: 1386 tests OK (skipped=2)
- `ruff check`: 0 errors
- `pyright`: 0 errors, 0 warnings

---

## Next stages (P2, P4, P6, P7)

| ID | What | Why |
|---|---|---|
| P2 | Facade surfaces: `arranger.engine`, `arranger.request`, `arranger.render` | ISP |
| P4 | Route dispatcher extracted from `movement.py` | SRP |
| P6 | Document / eliminate `arranger ↔ tabstaff` runtime cycle | DIP |
| P7 | `voicing_cost` accepts `SelectionCriteria`, returns named score | OCP |

