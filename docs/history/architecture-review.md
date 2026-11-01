> **Retired into `docs/history/` — the record of a completed review and its plan.** All seven
> stages landed (P1–P7), and the pair the review deliberately did not stage — F8 (the explanation
> invariant) and F10 (`grips.py`'s size) — are covered by the standing tests and the recipes in
> [AGENTS.md](../../AGENTS.md) rather than by a refactor. **Nothing here is live.** The structure the
> review produced is stated where it is read from: the module map and the dependency order are
> [AGENTS.md](../../AGENTS.md), asserted from the AST by `tests/meta_package_dag.py`; the per-module
> budgets and the test seams are `tests/meta_structure.py` (`BUDGETS`, `TEST_SEAMS`); the dispatch
> table is `arranger/route_dispatch.py` with `tests/meta_route_dispatch.py`; the selection rule is
> `cost.voicing_cost` and `VoicingScore`, whose field order `tests/test_grip_selection.py` pins;
> the `SlotContext` composition is `arranger/context.py`; and the `arranger ↔ tabstaff` runtime
> cycle is pinned by `tests/meta_front_end_dag.py::TestTheRuntimeCycle`. Paths below are as they
> were when each stage landed.

# Architecture Review — jazz-arranger (retired)

**Author:** Cline (AI coding agent), acting as software architect.
**Gate:** `make check` (lint + typecheck + test) stayed green after every stage.

## Source of the review

Based on reading the repository layout, AGENTS.md, docs/engine.md,
docs/renderers.md, docs/dependency-dag.md, and the engine modules listed in the
routing table, plus the structural tests (`meta_package_dag.py`,
`meta_structure.py`, `meta_front_end_dag.py`).

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
because `tabstaff` imports `arranger.tuning`, so the two name each other. The AST
DAG test passes - the facade's import is not module-scope - but the runtime graph
has a loop, and nothing measured whether either side could meet the other half
built. Closed by P6 below: measured inert in both directions, and pinned.

### F5 — `movement.py` is a central orchestrator with high fan-in (SRP)

`movement.py` imports from `bass`, `bass_merge`, `decisions`, `grips`,
`grouping`, `harmonised_route`, `options`, `resolution`, `routes`, `slot_plan`,
and `tuning`. It owns the slot loop, route dispatch, timing construction, and
bass merge. Routes are largely procedural functions; movement decides which one
runs.

Closed by P4 below for the half that was really a second job: the dispatch is
`route_dispatch`'s `ROUTES` table, and `movement` kept the loop, the knobs, the
timing and the merge. Its imports fell from eleven to nine, and the three modules
it used to reach for the dispatch - `routes`, `harmonised_route` and `decisions` -
are now one edge to `route_dispatch`.

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

Closed by P7 below: the rule takes the criteria value and returns a `VoicingScore`
whose fields are named, so the order is asserted **once** and adding a criterion is
a field, a label and a value — not a search through every call site.

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
| 2 | P5 | done | TEST_SEAMS list in `tests/meta_structure.py` — 25 private test-to-arranger reaches documented. New `TestTheTestSeams` test class asserts all reaches are recorded and no stale entries remain. |
| 3 | P3 | done | Each axis answered by one resolver in the module owning its vocabulary: `resolve_bass` moved to `bass_rules`, `texture.parse_texture` added, `TestTheAxisResolvers` holds the signatures to the dependency table. |
| 4 | P2 | done | The facade's bulk was demo code, not names: `main()` (151 lines, complexity 14) moved to `arranger.demo`, re-exported so `arranger.main`, the console script and `python -m arranger` are unchanged. Facade 695 → 543 lines, `__init__` budget 14/151 → 2/5. |
| 5 | P4 | done | The dispatch left `movement` as `route_dispatch`: a frozen `Route(name, claims, emit)` and an ordered five-entry `ROUTES`, with `dispatch_step` asking each in turn. The order is now data, pinned by `tests/meta_route_dispatch.py`, which also drives every entry from a request a caller can ask for and pins each request to the entry it must land in. `movement` 247 → 160 lines, 8 → 3 functions, 11 → 9 imports; demo output byte-identical against a worktree of the previous commit. |
| 6 | P6 | done | The `arranger ↔ tabstaff` cycle measured inert in both directions and pinned by `TestTheRuntimeCycle`; the module-scope rule widened from the facade to the package. Two docstrings and `docs/renderers.md` had claimed an eager import "would fail to find the names" - it does not, and now a test says so. |
| 7 | P7 | done | `voicing_cost` takes one `SelectionCriteria` and returns a `VoicingScore` - a `tuple` subclass with 7 named fields, so comparison and `min` are unchanged. The field order is asserted once (not twenty times), the labels and the span/partition indices are derived from `_fields`, and the public `VoiceLeadingEngine.voicing_cost` takes the criteria object. `best_voicing` is now a builder of criteria over the one argmin, `best_voicing_for`. 29 test call sites moved from positional indices to field names; suite 1393 → 1395. |

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
- 799 tests pass across `test_progressions`, `test_comping`, `test_request`, `test_lone_bass`, `meta_explanations`, `test_chord_fills`, `test_non_chord_tones`, `test_chord_attack`, `test_bass_hold`, `test_durations`, `test_bass_placement`, `test_bass_positions`, `test_harmony`, `test_parts`, `test_grid`, `test_grip_selection`, `test_grips`, `test_palette`, `test_fretboard`, `test_grouping`, `meta_front_end_dag`, `meta_package_dag`, `meta_structure`, `test_fingers`, `test_placement`, `test_generated_grips`, `test_voicings`, `test_bass`, `test_chord_parser`, `test_html_rendering`
- `ruff check`: 0 errors
- `pyright`: 0 errors, 0 warnings on changed files

---

## P5 — Complete: TEST_SEAMS list (done)

**What changed:**

Added `TEST_SEAMS: Set[str]` to `tests/meta_structure.py`, documenting every
private name a test file imports from an arranger module. Each entry is
`test_module -> arranger.module._private_name`, the same shape the encapsulation
meter uses for library modules.

25 seams recorded across 14 test files:

| Test file | Private names reached |
|---|---|
| `test_palette` | `arranger.annotation._criterion_phrase` |
| `meta_explanations` | `arranger.annotation._omission_clause` |
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

- `tests/meta_structure.py` — added `TEST_SEAMS`, `_test_files`, `_test_private_imports`, `TestTheTestSeams`

**Verification:**
- `tests.meta_structure`: all 8 tests pass (including the new one)
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

**The guard:** `tests/meta_structure.py` carries `AXIS_RESOLVERS` (axis → owning
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
- `tests/meta_structure.py` — `AXIS_RESOLVERS`, `AXIS_DEPENDENCIES`, `POLICY_WIRING`, `TestTheAxisResolvers`

**Verification:**
- full suite: 1386 tests OK (skipped=2)
- `ruff check`: 0 errors
- `pyright`: 0 errors, 0 warnings

---

## P2 — the facade subdivision, and what measuring it changed

F2 asks for `arranger.engine` / `arranger.request` / `arranger.render`. Two facts
found while planning it:

1. **`arranger.render` is taken.** It is an engine module in the layer order
   (`... -> movement -> steps -> slots -> render -> cli`) and a name in `__all__`.
   A surface module cannot use it; `arranger.rendering` can.
2. **The load-time half of F2 is not worth what it costs.** Measured:
   `python -c 'import arranger'` loads **32** `arranger` modules (and no optional
   extra), taking 0.36 s including interpreter start. The only way to make a
   client's `import arranger.engine` avoid them is a PEP 562 `__getattr__` facade
   over the whole public surface - and a module `__getattr__` returns its declared
   type, so every one of the ~130 public names would become `Any` to pyright
   unless the export table were written a second time under `TYPE_CHECKING`,
   which nothing can keep in step. **The type surface is worth more than 0.3 s.**

So P2's live half is the *names*: three surface modules that own the grouped
re-export lists, with `__init__` composed from them. That is what the finding
called "no subdivision" - and it is discoverability, not lazy loading. The
decision is recorded here rather than assumed; a later stage may still pay for
laziness, and this paragraph is the price it has to argue with.

### What was done instead: the demo left the facade

Measuring the facade for the names-only subdivision found the reason it was not
worth doing: the 695-line module held **151 lines of demonstration** (`main()`,
complexity 14) and the rest is the re-export list, which is the public API and has
to live somewhere. Moving those names into three surface modules would add three
import paths to keep in step and would not remove a line of printing; removing
`main()` takes the printing out of the API module and adds no name to learn.

So `main()` lives in **`arranger.demo`** and `__init__` re-exports it:

- `arranger.main` is still `arranger.demo.main` - *identity*, not a copy - which
  `tests/meta_package_dag.py::test_the_facade_reexports_the_public_surface` pins
  beside the other re-exports. The console script (`arranger:main`), `__main__.py`
  and the three `arranger.main()` tests in `tests/test_cli.py` are untouched;
- `demo` sits **last** in the declared order: it imports `steps` and `render` and
  nothing else, so no `ALLOWED_EDGES` entry was needed - the evidence that it was
  placed by its edges rather than appended;
- it is a **public path** (`arranger.demo` in `__all__`): importing a submodule
  binds it on the package whatever the import spelling, so leaving it out of the
  list would make the list wrong - the rule the `__all__` comment already states
  for `cli`, `render` and the rest;
- the `if __name__ == "__main__"` guard that sat under `main()` was **dropped, not
  moved**: it could never fire in `__init__.py` (relative imports) and `__main__.py`
  is the entry point.

Measured after the move: facade **695 → 543 lines**, `main` still 151 lines in its
own module, `make demo` output byte-identical (diffed against a capture from before
the change), and the budget table moved in both directions it should - `demo` states
its measured ceiling `(14, 151, 0)` and `arranger/__init__.py` falls to `(2, 5, 1)`,
its worst function now being `__getattr__`.

---

## P6 — the cycle, measured instead of assumed

F4 named a cycle: `arranger` resolves the staff renderers through a PEP 562
`__getattr__`, and `tabstaff` imports `arranger.tuning`. Two documents explained the
lazy seam by saying an eager import "would re-enter a half-initialised `arranger`
and fail to find the names". **That explanation is false**, and measuring it is what
this stage produced:

| probe | result |
|---|---|
| `import arranger`, then look in `sys.modules` | **0 of the 6** front ends loaded - the seam is lazy at runtime, not merely in the AST |
| the four renderers, with a blank `arranger` module in `sys.modules` (no `__getattr__` at all) | **all four import**, each binding the same `ArrangementStep` from `arranger.tuning` - the reverse edge is the leaf |
| a module-scope `from tabstaff import format_tab_staff` added to `arranger/__init__.py` in a scratch copy | **it imports cleanly**, and loads `tabstaff`, `tabxml`, `tabgp`, `tabscore` on every `import arranger` |
| a module-scope `import headxml` in the same scratch copy | **`ImportError: cannot import name 'CHORD_FILLS_COMP'`** |

So neither half of the loop can wait for the other, and the seam's real job is not
to break a deadlock: it keeps four rendering modules - and the write paths among
them - out of every `import arranger`. The hard failure belongs to the two front ends
that name the facade's *public surface* (`headxml`), which cannot be
imported until the facade has finished; `demo.main()`'s and `cli`'s function-local
imports are what keep them clear of that.

**What changed.** The three claims became one test class rather than prose:
`tests/meta_front_end_dag.py::TestTheRuntimeCycle` measures the facade's laziness and
the front ends' independence of it, and the module-scope rule was widened from the
facade alone to the whole package, since `cli` was the second module that could have
taken that edge. The two false docstrings were corrected - `tabstaff`'s module
document, `arranger/__init__`'s export comment, `docs/renderers.md`, and
`test_importing_tabstaff_first_does_not_crash`, whose premise was the false one.

**Elimination was declined, deliberately.** The benign edge could go by moving
`tuning` to a top-level module with `arranger/tuning.py` as a shim. That is a new
public module (four registries to add it to: `py-modules`, `MODULES`, `typecheck`,
`FRONT_ENDS`) and a second place to look for the voicing dataclasses, and it leaves
`headxml`'s failing edge untouched. The diagram would be tidier; the code would not
be safer.

---

## P4 — the dispatch, as a table instead of a chain

`movement._route_slot` was a 45-line if-chain with two fall-throughs, and it was
the only thing in the module that was not sequencing. It is now `route_dispatch`:
a frozen `Route(name, claims, emit)` value and an ordered `ROUTES` tuple

```
no_upper_voices -> texture_fill -> no_chord -> comping -> melody_bearing
```

with `dispatch_step` asking each entry in turn. Three properties came out of that
shape, and each is now a test rather than a comment:

- **the order is data.** It used to be the *position of the `if` statements*, so a
  reader had to hold five guards in their head to know that an `NC` bar beats the
  comp and a fill beats the melody. `[route.name for route in ROUTES]` is the
  contract, and `test_the_order_is_the_contract` states what each position is
  load-bearing for.
- **a decline is a value.** The fill and the comp may claim a slot and then return
  False, handing it on; that was a nested `if` before, and it is now the same
  `emit` contract for both.
- **exactly one step per slot is structural.** `_claims_always` is the last entry
  and its emit returns True, so `dispatch_step` cannot fall off the end. The test
  wrapper measures it anyway - one slot, one appended step - because a structure
  that is *supposed* to be guaranteed is exactly the one worth watching.

The reachability half is the part a table can get wrong in a way a chain cannot: an
entry whose claim no request can satisfy is a branch nobody sees. `CASES` in
`tests/meta_route_dispatch.py` is one request per entry, read from the table's own
names, so an entry **added** but never fired fails one test, and an entry
**deleted** or a claim **broadened** fails the other - the request lands in the
wrong route. Both directions were checked by mutating `ROUTES` in a scratch run:
broadening the comping claim failed two cases, deleting `no_chord` failed one.

**What stayed put, deliberately.** `previous_shape` is still in `routes` (both the
fill and the `NC` bar read it), and the route handlers keep their own docstrings and
their `arrangements`-append convention. The dispatch table is about *which* runs,
not about how; changing the handlers would be a second refactor with a different
risk.

**Measured:** `movement.py` 247 → 160 lines, 8 → 3 functions, 11 → 9 sibling
imports; its budget 8/103/15 → 4/89/15, and `route_dispatch` starts at 4/19/3.
`make demo` byte-identical against `git worktree add /tmp/pre HEAD`, and the suite
green at 1393.

---

## P7 — the rule takes its context, and says what it scored

F9's complaint had two halves, and the second was the one that mattered: the order
was asserted **twenty times**, positionally, across `TestVoicingCost` - so reordering
a criterion meant editing a test file rather than reading one line, and every call
site read `[3]` where it meant "span".

`VoicingScore` is a `NamedTuple`, and that single choice does both jobs:

- **it is still a tuple.** Comparison stays lexicographic, `min` still picks the
  winner, and `decisive_criterion` still zips two scores. Nothing about the rule
  moved - only its spelling.
- **the order is asserted once.** `test_the_field_order_is_the_rule` names the seven
  fields, the eight phrases and the two derived indices; every other assertion reads
  `score.span`.

The other half is `voicing_cost(voicing, criteria)`. `SelectionCriteria` already
existed but `voicing_cost` took seven keywords and `SelectionCriteria.cost`
re-spelled all seven when delegating - three places to keep in step for one rule.
Now the value is the whole input:

- a new *input* (as `root_pc` and `melody_pc` both were, added one at a time) is a
  defaulted field on `SelectionCriteria`, and the facade method does not change;
- `SelectionCriteria.cost` is `voicing_cost(voicing, self)`, so the selector and the
  palette record cannot be scored against arguments the other did not see;
- `best_voicing` (the keyword convenience) now **builds** the criteria and delegates
  to `best_voicing_for`, so there is one argmin rather than two that must agree.

**What the return being a named tuple buys an editor is smaller than what it buys the
next criterion.** Adding one is: a field, its phrase in `_CRITERION_LABELS` (keyed by
field name, so it cannot drift), and the value read from the criteria - because
`VOICING_COST_CRITERIA`, `SPAN_CRITERION` and `PARTITION_CRITERION` are all derived
from `_fields`, and the return is built by keyword so the field and its position
cannot drift apart. A field with no phrase raises `KeyError` at import, which no run
can miss. The one thing that is still a decision is *where* it ranks.

**Measured:** the seven-field order and the eight phrases are unchanged, so the demo
output is byte-identical and every pinned tab still says what it said. 29 test call
sites moved from positional indices to field names; `TestVoicingCost` gained two
tests (the order, and "the score is still a tuple") and lost nothing. Suite
1393 → 1395, ruff 0, pyright 0/0.

---

## The plan is complete

All seven stages landed: P1, P2, P3, P4, P5, P6, P7. What is left of the review's
findings is the pair it deliberately did **not** stage - F8 (the explanation
invariant) and F10 (`grips.py`'s size) - both of which are covered by the standing
tests and the recipes in `AGENTS.md` rather than by a refactor.

**Postscript - the structural tests are now a half of the suite you can run on its
own.** Everything this review calls structural is a `tests/meta_*.py` module, and the
music is `tests/test_*.py`: `make test-features`, `make test-meta`, and `make test`
running both. The split is by filename, so there is no list to keep in step, and
`tests/meta_structure.py::TestTheSplit` fails on a module that matches neither - the
one way a pattern-based gate could quietly stop running something. The rule for where
a new test goes is in `AGENTS.md` §"The gate".

