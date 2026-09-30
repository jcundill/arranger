# Implementation Plan

**Goal.** Restructure `jazz-arranger` so its *structure* carries the invariants its
comments currently carry in prose — because the maintainers are LLM agents, which
edit what they can find and cannot infer that a decision documented in one place is
duplicated in another.

**Status: Phases 0–6 and 8 done. Phase 7 (CLI de-duplication) is next; Phase 9 (CI)
last. Phase 6 is partly done and its remainder is a *decision*, not a task — see
[Phase 6](#phase-6--the-import-cycle-cannot-be-deleted).**

| phase | what | state | tests |
|---|---|---|---|
| 0 | baseline + lint gate | **done** `1ae20af` | 677 |
| 1 | `tests/support.py`, one copy of each fixture | **done** `b4cadc7` | 677 |
| 2 | `Diagnostics`; no `print()` in the library | **done** `b4d51f4` | 694 |
| 3 | one implementation of each shared decision | **done** `9d3c7a1` | 702 |
| 4 | `ArrangeOptions`; `arrange_slots` delegates | **done** `b834cbf` | 714 |
| 5 | split `arranger.py` into a package | **done** `6aba38b` | 719 |
| 6 | import cycle | **partly done** `c289879`; rest is a decision | 719 |
| 7 | CLI de-duplication | **next** — see [Phase 7](#phase-7--cli-de-duplication-next) | — |
| 8 | docs: `AGENTS.md` was actively wrong | **done** | 724 |
| 9 | CI and cleanup | pending | — |

**Suggested order from here: 7, then 9.** Phase 8 shipped `AGENTS.md` at 402 lines with
a routing table, moved the reasoning into `docs/`, and added `tests/test_docs.py` so
drift fails the suite.

Supersedes `docs/history/texture-plan.md` (the completed `texture="targets"` plan).

---

## Read this first if you are resuming

### Working in this environment

**Long commands must be backgrounded with a completion sentinel.** A foreground
command here is frequently reported as *"Command execution aborted"* or its output
is silently truncated — the test suite takes 40–80s, `pyright` ~25s. `pgrep` is
unreliable too. The only dependable way to know a task finished is to poll for a
marker it writes itself. Recreate this helper (it is gitignored, so it will not
survive a fresh checkout):

```bash
# .bg.sh  --  bg.sh <logfile> <command...>
LOG="$1"; shift
rm -f "$LOG"
{ "$@" ; echo "__BG_DONE__ rc=$?" ; } > "$LOG" 2>&1 &
```

Then run `./.bg.sh /tmp/out.log .venv/bin/python -m unittest discover -s tests -t .`,
and read `/tmp/out.log` with the file reader. Completion is `__BG_DONE__` in that
file. **Reading the log file is the only reliable way to get output** — `cat`ing it
through a foreground command loses it.

Two corollaries learned the hard way: do **not** try to read a JSON log with a
foreground `python -c` that prints (it truncates); and when a command writes JSON,
write the sentinel to a *different* file or strip it before parsing, or the log is
no longer valid JSON.

### The gate, and the baseline you are holding

```bash
make check      # lint + typecheck + test, in that order
```

Current measured state, all green: **724 tests OK (skipped=2)**, pyright **0 errors
0 warnings**, ruff **0 errors**. If your change moves any of those numbers, that is
the signal — not the absence of an error message. (719 was the count before Phase 8;
the 5 extra are `tests/test_docs.py`.)

`make check` exists because two things were wrong before it did: a linter was
absent, and `pyright` silently failed to find the virtualenv. See "Traps" below.

### Where the code is now

`arranger.py` is **gone** — it is a package. If you are reading this cold, the two
facts that matter most:

```
arranger/tuning.py      the instrument; Voicing and ArrangementStep live here
arranger/cost.py        voicing_cost - the library's central invariant
arranger/steps.py       VoiceLeadingEngine and the one step loop
arranger/__init__.py    a facade: re-exports, __version__, main()
```

`tests/test_package_dag.py` asserts the layering, so a module that imports one
below it fails the suite. Read its `ORDER` list before adding a module.

**`AGENTS.md` is now accurate and short (402 lines).** Phase 8 rewrote it as a
*routing table* and moved the reasoning into `docs/engine.md`, `docs/renderers.md`
and `docs/corpus.md`. If you are here cold, read `AGENTS.md` first and follow the
table — do not work from this plan's layout section, which is Phase 5's *spec* and
is marked as superseded.

### The six defects this refactor is for

| # | defect | measurement | why it hurts an LLM agent |
|---|---|---|---|
| 1 | the step loop existed **twice** | `arrange_progression` 514 lines, `arrange_slots` 362 | the code said *"both copies must agree"*; an agent fixing one gets **no signal** about the other. The project had already paid for this once — the corpus path voiced `Am7` under a written `Bbm7` for 25 transcriptions |
| 2 | one 4290-line module | `arranger.py` held everything | "where is the cost tuple?" means paging through 4000 lines of music theory |
| 3 | the library **printed** to stdout | 8 warning sites | a warning could not be read by a test, silenced by a caller, or collected |
| 4 | two hand-copied argparse blocks | `corpus_cli` 280 lines, `head_cli` 221 | a flag added to one CLI is silently missing from the other |
| 5 | test fixtures copy-pasted | `make_step` ×2, `make_voicing` ×2, `bass_string` ×2 | divergent fixtures; a test passes for the wrong reason |
| 6 | docs stale and unenforced | `AGENTS.md` 1710 lines, says version `0.8.0` *and* `0.7.0` while `__version__` is `0.9.0`; **zero** mention of walking bass, which ships in 0.9.0 | an agent reads it as ground truth and acts on stale facts. **Phase 8.** |

**Defect 6 got worse in Phase 5, not better, and Phase 8 fixed it.** `AGENTS.md`
described a single 4290-line `arranger.py`, a layout with no `arranger/` directory,
and `pyright arranger.py ...` as the typecheck command — all false from `6aba38b`
onward. It is now 402 lines, routes to `docs/`, and `tests/test_docs.py` fails the
suite if it stops describing the tree.

**But the drift was not where this plan said it was.** Phase 8's own test found
**19 stale `arranger.py` invocations in `README.md`** — the user-facing document this
plan had never listed. The lesson is recorded under
[Phase 8](#phase-8--the-docs-and-a-false-premise-found-while-doing-them) and it
applies to the remaining phases: *measure which documents are stale; do not fix the
one you already suspect.*


## The target module layout (Phase 5's spec — superseded, kept for the reasoning)

> **Read this as history, not as instructions.** Phase 5 shipped a different
> layout, because three entries below cannot form a DAG. The table is left in place
> because *why* each moved is the useful part, and that is written up under
> [Phase 5](#phase-5--the-package-split). The authoritative order is the `ORDER`
> list in `tests/test_package_dag.py`, which the suite enforces.

`arranger.py` → a package named `arranger`, so `from arranger import
VoiceLeadingEngine` and the `jazz-arranger` console script are unchanged. Twelve
modules, ~3900 lines total, **no module over 1000**.

| module | contents | ~lines |
|---|---|---|
| `arranger/__init__.py` | facade: re-exports, `__version__`, `main()`, `format_progression` | 150 |
| `arranger/tuning.py` | `STANDARD_TUNING`, `STRING_NAMES`, `PITCH_CLASS_NAMES`, `NO_CHORD`, `GuitarFretboard`, `_note_name` | 60 |
| `arranger/chords.py` | `ChordParser` + its tables, `normalised_harmony`, `sounding_harmony` | 230 |
| `arranger/grips.py` | grip tables, `supported_string_sets`, the `_place_*` / `_interval_offsets` builders, and the generators currently on `VoiceLeadingEngine` | 700 |
| `arranger/cost.py` | `voicing_cost`, `_best_voicing`, `_window_penalty`, `calculate_*_distance`, `bass_cost` | 260 |
| `arranger/textures.py` | `ROLE_*`, `TEXTURE_*`, `TARGET_BEATS`, `_BEAT_EPSILON`, `_metric_weight`, `_roles_for_slot` | 130 |
| `arranger/bass.py` | `BassNote`, `BASS_ROLE_*`, `_Slot`, `_walking_slots`, `_walking_bass_line`, `_place_bass`, `_previous_bass` | 450 |
| `arranger/steps.py` | `ArrangementStep`, `StepPreparation`, `VoiceLeadingEngine`, `arrange_progression` | 700 |
| `arranger/render.py` | `_step_annotation`, `_MUTED_CELL`, `_step_cells`, `format_progression`, `_print_step` | 200 |
| `arranger/decisions.py` | **already exists** — moves into the package unchanged | 276 |
| `arranger/diagnostics.py` | **already exists** — moves unchanged | 83 |
| `arranger/options.py` | **already exists** — moves unchanged | 71 |
| `arranger/cli.py` | `add_common_arguments`, `render_and_write` (Phase 7) | 180 |

**The dependency direction is a DAG, and that is what makes the split acyclic:**

```
tuning ← chords ← grips ← cost
                    ↑        ↑
                 textures  bass
                    ↑        ↑
                 options ────┘
                    ↑
                  steps → render → (facade)
```

No module imports `steps` except `__init__.py` and `cli.py`. `decisions` and
`options` are the only two that currently use a *function-local* import to dodge a
cycle; inside the package both become ordinary top-level imports, and **Phase 6
exists to verify that**.

### Doing it in five commits, each green

`git mv arranger.py arranger/__init__.py` first so history follows the file.

1. `tuning` + `chords`
2. `grips` + `cost`  ← the big one; `VoiceLeadingEngine`'s generator methods become
   free functions here, with thin `@classmethod` delegates left behind (≈40 test
   call sites use `VoiceLeadingEngine.get_drop2_voicings` and they must keep working)
3. `textures` + `bass`
4. `steps` + `render`
5. the facade: `pyproject.toml` → `packages = ["arranger"]`, repoint `tabstaff` /
   `tabxml` / `tabgp` / `wjazzd` / `headxml` / `decisions` / `options` / `diagnostics`,
   and add every new module to `MODULES` in the Makefile **in the same commit** (see
   Traps)

Also in step 5: delete the second definition of `_STAFF_CELL_WIDTH`, which
`arranger.py` and `tabstaff.py` currently each declare identically.

**Add an import test** asserting the DAG holds — that `grips` does not import
`steps`, and so on. It is the only thing that keeps the layering from eroding one
"temporary" import at a time.

---


## What Phases 0–5 actually shipped

Read this rather than the phase descriptions: several things diverged from the
original plan, and the divergence is the interesting part.

### Phase 0 — the gate, and three tests that could not fail

`ruff` as a dev-only extra; `make lint` / `format` / `check`; `make typecheck` now
passes `--pythonpath`.

**Three tests were green while asserting nothing**, which is the finding that
justifies the phase:

- `test_chord_parser.py::test_parse_simple_roots_and_qualities` built a 12-case
  table and never used it — the assertions were four hand-copied lines below. Now
  driven through `subTest`, so a regression *names the chord*.
- `test_grip_chart.py::test_every_sounding_pitch_is_a_chord_tone` computed the
  chord's tone set and stopped. **The test's name was exactly the property it never
  checked.** It now checks every sounding pitch.
- `test_headxml.py` had **two** methods of the same name for one scenario, the
  first a stub. The stub is deleted; its twin already covered it. Hence 677, not 678.

Also found: 9 unused imports, 5 half-used tuple unpacks.

### Phase 1 — `tests/support.py`

Six fixtures consolidated (−101 lines). Two functions called `names` were
deliberately **left alone** — `test_bass`'s takes `(chords, onsets)` and
`test_walking_bass`'s takes a step. Same name, nothing else; a shared helper would
have hidden that.

`tests/__init__.py` was added so `tests.support` imports as a package module, which
changed discovery: **`make test` is now `discover -s tests -t .` and must run from
the repo root.**

### Phase 2 — `Diagnostics`

Eight `print()` sites became a collector with an `emit` hook that defaults to
`print`, so nothing a user sees changed. A collector, not `logging`: the messages
are user-facing prose tuned for a terminal, and the library has one consumer.

17 tests. The one that matters asserts stdout is **empty** when a collector is
passed — the old `redirect_stdout` tests structurally could not make that assertion.

### Phase 3 — `decisions.py`

Five decisions, one implementation, called from both loops:
`resolve_texture_grips`, `melody_alone_case`, `should_promote_fill`,
`should_demote_to_melody_alone`, `is_repeated_step`.

**The two loops had not drifted.** The divergences flagged while planning
(`wjazzd`'s `or slot_grips == ()`) turned out unreachable in the fixtures.

**A bug this nearly shipped, because the shape will recur.** `melody_alone_case`
first returned a `bool`, and unifying the `NC` branch with the walking-bass branch
on that boolean would have set `melody_only=False` on an `NC` bar — so the renderer
would annotate a step *"(no chord - melody alone)"* that claims to have a chord. The
two routes call the same function but build **different steps**, so the predicate
returns a **kind** (`none` / `texture` / `nc`). *When consolidating two branches,
check whether their outputs differ before unifying their predicates.*

### Phase 4 — `arrange_slots` delegates

366 lines of second loop → ~90. `wjazzd.py` 2225 → 1941. `_arrange_step_with_bass`
(84 lines) deleted; its body is now `decisions.select_step_voicing`.

The corpus passes what it needs as *data*: `ArrangeOptions.bass_pcs` (a pitch
class per index) and `bass_cost` (the ranking). The slash bass narrows *which
candidates are considered*; the engine's own rule then chooses within that group, so
rule C's two rules stay **combined, not sequential**.



**The one deliberate behaviour change in the whole refactor.** Measured over 40
configurations (30 hand-built: 3 textures × 4 grip settings × timed/untimed, plus 6
`fallback="diminished"` cases; and 5 real Weimar heads, 470 steps), fingerprinted on
every caller-readable field plus the tab string:

- **0 voicing differences.**
- 6 configurations gained **48 extra warnings**, all one kind: steps the engine
  cannot voice, which the old corpus loop **skipped silently**.

The music is unchanged; what changed is that *losing a note of the tune is now
visible* — which this codebase calls the worst outcome that can happen, and so the
one thing that must never happen quietly. Pinned by
`test_a_step_the_engine_cannot_voice_is_now_reported`.

`.baseline_capture.py` (committed) is what makes that claim checkable:

```bash
.venv/bin/python .baseline_capture.py /tmp/x.json   # run before and after
```

**A crash the merge exposed.** `arrange_progression` built each slot with
`float(timings[index][1])`, assuming a non-`None` beat. The corpus has *always*
passed `(None, None, None)` for a slot it could not place — the two entry points
hold genuinely different timing types — but nothing had ever called that line with
one. The first delegation crashed on it. This is the **fourth** time that difference
has cost this library something, and the first time as a runtime crash rather than a
signature pyright rejected. The parameter's type now states what it always had to
accept.

### Phase 5 — the package split

`arranger.py` (4290 lines) → eleven modules in a strict order, re-exported through
`arranger/__init__.py`, so `from arranger import X` and the `jazz-arranger` console
script are unchanged. 719 tests, pyright 0/0, ruff 0.

```
tuning -> diagnostics -> chords -> grips -> cost -> textures
                                                   |
                            bass <- options -----+----> decisions
                                                   |
                                                 steps -> render -> (facade)
```

**Every module body was moved by line range, never retyped.** A 4000-line move is
only safe if the text is copied rather than re-entered, so the split ran through a
generator that sliced the original by line number. The only hand-written parts are
the import headers, the facade, and the delegates — a docstring, a fret number or
a comment cannot change in a move that copies bytes.

**Three placements in the plan's table could not be a DAG, and each is forced by a
concrete edge:**

- `Voicing` and `ArrangementStep` are in **`tuning`**, not `steps`. `grips`
  *constructs* a `Voicing`, so it must be below `grips`; and both dataclasses
  default `role` to `ROLE_TARGET`, so the role vocabulary must be below that too.
  The tab-cell primitives follow for the same reason — `Voicing.tab_block` calls
  them. This also deleted the second `_STAFF_CELL_WIDTH` definition.
- The non-chord-tone machinery is in **`chords`**, which the plan did not mention.
  Routing a melody note to an extension is chord theory, and `bass._bass_harmony`
  needs `NON_CHORD_TONE_EXTENSIONS` — leaving it on the engine would have made
  `bass` import `steps`.
- **`bass_cost` is in `bass`, not `cost`.** It ranks over `BASS_ROLE_*` and is
  called by `_walking_bass_line`; in `cost` the two modules would need each other.

**Both function-local imports are gone**, which is the one thing Phase 5 was
certain to buy. `steps` used `from decisions import (...)` and
`from options import ArrangeOptions` *inside* `arrange_progression` to dodge
cycles that existed only because all four were one module. They are ordinary
top-level imports now, and `decisions.select_step_voicing` calls
`cost._best_voicing` directly instead of reaching through the engine.

**`X = classmethod(f)` is unsatisfiable, and the plan's trap #5 predicted it.**
Assigning a classmethod to satisfy pyright trips ruff's `B010`, which wants
`setattr`; `setattr` is invisible to a type checker. The delegates are written out
as real one-line methods instead — ~180 lines rather than ~20, and the only version
both tools accept. *This is trap #5's "look for a seam worth extracting", and the
seam was: the delegate needs a real signature anyway.*

Verified behaviour-preserving rather than merely green:

- **719 tests OK** (skipped=2) — 714 plus 5 new. The 54 hardcoded tab strings are
  untouched.
- **`.baseline_capture.py` before/after are byte-identical across all 40
  configurations** — 30 hand-built and 5 real Weimar heads, every caller-readable
  field plus the tab string. Not one voicing *or warning* changed. (Regenerate the
  "before" from `HEAD` in a worktree; the stale `/tmp/before.json` on this machine
  predates Phase 4 and shows 6 false differences.)
- A clean install of the built wheel imports and arranges outside the repo, the
  console script runs, and `import arranger` still works with music21 blocked.

Two incidental fixes, both forced by the split: `make demo` runs `-m arranger`
with a three-line `__main__.py` (a package cannot be executed directly), and the
stray paste artefact committed in `bb09831` inside the `TEXTURE_STYLES` comment is
corrected.


### Phase 6 — the import cycle cannot be deleted

**The phase as specified is not achievable, and the reason is worth more than the
work would have been.** The plan assumed that once the engine was a package, the
facade could import the renderers eagerly and the PEP 562 `__getattr__` could go.
Tried, measured, reverted:

1. Repoint `tabstaff` / `tabxml` / `tabgp` at `arranger.tuning` instead of the
   facade — they only need `_MUTED_CELL`, `STRING_NAMES`, `ArrangementStep`,
   `GuitarFretboard`, `NO_CHORD` and `PITCH_CLASS_NAMES`, all of which are in
   `tuning`. **This works**, and on its own is a genuine improvement: the
   renderers now depend on the layer below the facade rather than on the facade.
2. Make `tabstaff` import `tabxml` and `tabgp` eagerly. **This also works** — both
   import cleanly with `sys.modules['music21'] = None`, because they defer their
   extras to function-local imports.
3. Make the facade import the renderers eagerly. **This fails, and ordering cannot
   fix it.** Importing *any* submodule of a package executes that package's
   `__init__.py`, so `import tabstaff` → `arranger.tuning` → the whole facade →
   `from tabstaff import format_gp5`, against a `tabstaff` that is mid-import and
   has not defined it yet.

So the `__getattr__` is load-bearing, and the cycle is not "the engine and the
renderers importing each other" — it is **the facade re-exporting names from a
module that imports the package the facade lives in.** Steps 1 and 2 remove two of
the three lazy layers and are worth committing on their own; step 3 is impossible
while the facade re-exports.

The way out is a design decision, not a refactor:

- **Move the renderers *into* the package** (`arranger/render/`), which removes the
  cycle outright — but re-introduces why they live outside: `tabxml`/`tabgp` are
  optional-extra modules and `arranger` must import on a machine with neither.
- **Drop the facade re-export** and require `from tabstaff import format_tab_staff`.
  One line per call site, and it makes the one-way dependency honest — but it
  breaks the spelling the README, the tests and `wjazzd` all use, which is the one
  thing Phase 5 was careful to preserve.
- **Accept the `__getattr__`**, and keep what the split already bought: one
  definition per decision, a testable DAG, and a facade that is a facade rather
  than 4000 lines of music theory. Take the identity assertion Phase 6 wanted,
  which is the part with actual value.

The third is the recommendation. The assertion is worth having on its own merits
and is already written as `test_the_facade_reexports_the_public_surface`; the
`__getattr__` is ~15 lines the phase wanted deleted for tidiness, and deleting it
costs a public spelling.

### Phase 8 — the docs, and a false premise found while doing them

`AGENTS.md` was 1710 lines and had gone stale in ways an agent would act on: it
described a single 4290-line `arranger.py` (it is a package of eleven), gave
`pyright arranger.py` as the typecheck command, and stated the version as both
`0.8.0` and `0.7.0` while `__version__` was `0.9.0`.

It is now **402 lines**, opening with a routing table — *changing X? read Y* — and the
reasoning moved into three documents that own a subsystem each:

| document | what moved into it |
|---|---|
| `docs/engine.md` | the architecture, the grips and the selector, texture, the octaves |
| `docs/renderers.md` | `tabstaff` / `tabxml` / `tabgp` / `headxml` and their traps |
| `docs/corpus.md` | the Weimar integration and head selection |
| `docs/open-issues.md` | the diagnosed-but-unfixed bugs (was `walking_bass_issues.md`) |
| `docs/history/` | `walking-bass.md`, `corpus-plan.md`, `bass-lines.md`, `texture-plan.md` |

**Every relocated block was moved by line range, never retyped** — trap #8 again, for
the same reason. A fret number or a measured percentage provably cannot change in a
move that copies bytes.

**The test found drift nobody had noticed, including in a file the plan had not
listed.** `tests/test_docs.py::TestDocsMatchTheCode` asserts five things, and on its
first run three failed:

- **19 stale `arranger.py` invocations in `README.md`** — every CLI example in the
  user-facing document. The plan had flagged `AGENTS.md` as the misleading one and
  never checked the README.
- `AGENTS.md` itself named `.baseline_capture.py` nowhere in its layout, so a
  committed script was undocumented.
- The version assertions caught `0.8.0` still quoted in the relocated engine prose.

That is the phase's whole argument in one measurement: **the drift was not where the
plan said it was.** A checklist derived from the plan's own beliefs would have fixed
`AGENTS.md` and left the README telling users to run a command that no longer exists.

### The false premise: `lead_sheet.py` is not stale

The plan specified deleting `lead_sheet.py` — "208 lines querying tables that do not
exist", on `AGENTS.md`'s authority. **Checked before deleting, and it is false.** It
queries `beats`, `solo_info` and `melody`, all three of which exist, and its 12 tests
pass against the real 42 MB database:

```
Ran 12 tests in 0.309s
OK
```

The `AGENTS.md` sentence asserting it was stale was itself the stale thing. The file
is kept, its test is kept, and the false claim is deleted rather than propagated.
*The document that reports drift is not thereby authoritative about it.*

### Where the plan was wrong

Recorded because the next phase will hit the same thing:

- `select_step_voicing` was specified for `arranger/steps.py`; it went to
  `decisions.py` with `steps` as the caller, because `bass_cost` lives in `wjazzd`
  and `wjazzd` imports `decisions` — putting it in `steps` would have closed a cycle.
- `classify_slot` and a `SlotPolicy` class were specified and **not built**; the
  five extracted functions covered it.
- The equivalence test was to be added in Phase 4; it went in Phase 3, because that
  is where the shared decisions made it meaningful.
- Phase 5's module table put `Voicing`, the non-chord-tone machinery and
  `bass_cost` in places that cannot be a DAG. The table was a *shape*; the edges
  are the constraint, and three entries had to move.
- Phase 6's premise — that the split makes the import cycle deletable — is false,
  and no amount of repointing reaches it. *A cycle through a package `__init__` is
  not the same as a cycle between two modules, and only the second can be fixed by
  moving imports.*
- Phase 8's premise — that `AGENTS.md` is the document that is wrong — was **half**
  wrong. `README.md` was worse, and it is the one a user reads. *Fixing the document
  you already know about is bookkeeping; measure which documents are stale instead.*
- And `lead_sheet.py` was to be deleted for a reason that measurement refuted. *Do
  not delete working code on a document's authority; run its tests.*

---

## Open decisions — not to be taken by the next agent without asking

These are real design forks, not tasks. Each is spelled out where it arises; none has
been decided, and **picking one silently is the failure mode this plan keeps
recording.**

1. **The facade's lazy `__getattr__` stays or goes.** It is ~15 lines, and deleting it
   costs either the renderers moving into the package (which re-breaks the optional
   extras) or the public spelling `from arranger import format_tab_html` (which the
   README, the tests and `wjazzd` all use). Phase 6 measured that the cycle cannot be
   removed by moving imports. **The plan's recommendation is to keep it**; the
   assertion it wanted already exists as
   `test_the_facade_reexports_the_public_surface`.
2. **`__version__` bump to `0.10.0`** rides with Phase 9. Note `tests/test_docs.py`
   then fails until every document that states a version is updated — deliberate.
3. **The walking-bass metre gap.** A 2/2 score numbers its beats past
   `beats_per_bar` and the walker is built for four quarters. Recorded in
   `docs/open-issues.md` rather than patched, because it is the same undecided
   question 3/4 raises. Do not "fix" it incidentally.
4. **`drop3` and `closed` remain unplayable** at `GRIP_MAX_SPAN = 5`. Raising the span
   to admit them changes the library's playability contract; it is not a tuning knob.

## Traps

Each of these cost real time, or nearly shipped a defect.

1. **A gate that enumerates its inputs by hand will silently skip whatever was
   added last.** The Makefile named each source file in three places, so
   `diagnostics.py`, then `decisions.py`, then `options.py` were unlinted and
   untypechecked until noticed. `lint` and `format` now share one `MODULES` list —
   **add new modules there in the same commit that creates them.** Phase 5 creates
   twelve at once; this is where that trap is most likely to bite.

2. **`pyright` needs `--pythonpath`.** Run bare it reported **32 errors**, all
   `Import "musthe"/"music21"/"guitarpro" could not be resolved`, for packages that
   were installed and importing fine. A checker that cannot see the venv reports
   import failures that look exactly like type failures. `make typecheck` pins it.

3. **A new runtime module must be added to `pyproject.toml`.** `diagnostics` was
   missed once; `import arranger` would have failed on a clean install. Phase 5
   changed the shape of this: the engine is now `packages = ["arranger"]` and
   `py-modules` holds only the renderers and front ends. **A new module inside the
   package needs no `pyproject.toml` change**; a new *top-level* module needs a
   `py-modules` entry.

4. **Do not run `ruff format`.** It rewrote 24 files and inflated `SHELL_DEGREES`
   from 10 lines to 31, one pair per line. Those tables are aligned so they can be
   scanned; one-per-line is 3× the space for the same information, in a refactor
   whose purpose is readability. `make format` exists for a targeted file and is
   **not** part of `make check`. This is also why the lint rule set is narrow:
   `UP*` off because `AGENTS.md` mandates `typing.List` style, `E501` off because
   the formatter owns line length, `B905` off because `zip(strict=)` is a behaviour
   change rather than a lint fix.

5. **`ruff B010` and pyright can be mutually unsatisfiable.** Assigning a classmethod
   to satisfy pyright trips `B010`, which wants `setattr`; `setattr` trips pyright.
   Don't add a suppression — look for a seam worth extracting instead. That is how
   `wjazzd._corpus_options` came to exist: the corpus's remaining job is deciding
   *what to ask for*, and that became a function a test can read rather than a call
   it has to intercept.

6. **A test's premise can be invalidated by the refactor it exists to protect.**
   `test_both_loops_call_the_shared_decisions` asserted *both* loops call each
   decision. Phase 4 made that false by design. It is now inverted: the engine calls
   the decisions, and `wjazzd` must not contain `prepare_step`, `_best_voicing` or
   `ArrangementStep` at all. **When a test fails because the structure it describes
   is gone, invert the assertion — do not delete the test.**

7. **Never `git push` or otherwise touch the remote.** This repo is on branch
   `walking-bass`; the user commits and pushes.

8. **A large mechanical move must copy text, not retyping it.** Phase 5 moved 4290
   lines into eleven modules, and the thing that made it safe was generating the
   modules by *slicing the original by line number* — so a docstring, a fret number
   or a comment provably cannot change in the move. The same instinct applies to
   any bulk edit here. The corollary: **generate into a script you keep until the
   suite is green**, because a half-applied regeneration over a good tree is much
   harder to unpick than a wrong line is to find. The Phase 5 generator is
   deliberately not committed — it read from a temp copy of the original and is
   one-shot scaffolding.

9. **A stale "before" baseline will invent differences that are not there.** The
   `/tmp/before.json` on this machine predated Phase 4, and comparing against it
   showed 6 configurations differing. All 6 were artefacts of the stale file;
   regenerating the baseline from `HEAD` in a `git worktree` showed the split was
   byte-identical across all 40. **Before believing a regression, check the
   baseline is from the commit you think it is:**
   `git worktree add /tmp/pre HEAD && cd /tmp/pre && python .baseline_capture.py
   /tmp/before.json`. The database is 42 MB and gitignored, so copy `wjazzd.db`
   across or the corpus half of the capture comes back empty.
10. **Stale documentation is rarely where you were told to look.** Phase 8 was
    specified as "`AGENTS.md` is wrong". `AGENTS.md` *was* wrong — and `README.md` was
    worse, with 19 invocations of a module deleted two phases earlier, in the document
    a user actually reads. Both CLIs' `prog=` strings named the same dead module, so
    every usage message and parse error pointed at it. *Before fixing the document you
    already suspect, grep the tree for the thing it got wrong:*
    `grep -rn 'arranger\.py' --include=*.md --include=*.py`.
11. **A document's claim that code is stale is not evidence — running the tests
    settles it in under a second.** This plan said to delete `lead_sheet.py` because
    it "queries tables that do not exist", sourced entirely from a sentence in
    `AGENTS.md`. Every table it queries exists and its 12 tests pass. *Never delete
    working code on a document's authority; run its tests first.*



---

## Not doing

- **`voicing_cost`'s 8-element tuple is not being touched.** It is the library's
  central invariant, asserted positionally in `tests/test_grips.py::TestVoicingCost`.
  Moving the code is safe; reordering it is a musical decision, not a refactor.
- **The 54 hardcoded tab strings in the tests stay.** They are the acceptance gate.
  A snapshot mechanism would make a regression *pass* by regenerating the snapshot.
- **No new runtime dependency.** `musthe` stays the only one; that is load-bearing
  for the LGPL reasoning around PyGuitarPro.
- **No `pytest`**, no subpackages under `tests/`, no `mypy`.
- **The two CLIs' output is not being unified.** They legitimately differ (the corpus
  prints a performer/key subtitle, `head` prints the notated metre). Only the shared
  argparse and dispatch move, in Phase 7.
- **Phases 0–4 are behaviour-preserving except the one measured change in Phase 4.**
  That is the standard Phase 5 is held to.

## Rollback

Every phase is one commit with a green suite behind it. Phase 3 is the one with real
semantic risk; if it ever proves intractable it reverts without touching 0–2, which
are pure additions.

## Remaining phases at a glance

- **6 — import cycle. Partly done; the rest is a decision, not a task.** `c289879`
  took the two parts that work (the renderers now import `arranger.tuning` rather
  than the facade, and `tabstaff`'s own `__getattr__` is gone). The third — deleting
  the facade's `__getattr__` — **is not achievable while the facade re-exports**;
  the measurement and the three costed options are in
  [Phase 6](#phase-6--the-import-cycle-cannot-be-deleted). Do not re-attempt it
  without reading that section. The identity assertion Phase 6 wanted is already in
  as `test_the_facade_reexports_the_public_surface`. **8 is done** — see
  [Phase 8](#phase-8--the-docs-and-a-false-premise-found-while-doing-them).

The two phases still to do are written up in full below, because both have an
acceptance gate that is easy to miss.

### Phase 7 — CLI de-duplication (next)

**One bug found and fixed while preparing this brief.** Both CLIs passed
`prog="arranger.py corpus"` / `prog="arranger.py head"` to argparse, so every usage
message and every parse error told the user to run a module that has not existed
since Phase 5. It is now `arranger corpus` / `arranger head`. Worth knowing because
it is the same class as the `README.md` drift: **the split left the old name in the
one place a user is guaranteed to read it.** Nothing asserted it, so the suite was
blind to it — grep for `prog=` before assuming a CLI is clean.

The two CLIs hand-copy the same argparse block. Measured on the current tree:

| | `wjazzd.corpus_cli` | `headxml.head_cli` |
|---|---|---|
| length | 531 lines (from `wjazzd.py:1411`) | 221 lines (from `headxml.py:1059`) |
| `add_argument` calls | 21 | 18 |
| **flags in both** | **17 shared** | |

The 17 shared flags, measured: `--bars`, `--bars-per-line`, `--fallback`,
`--fret-max`, `--fret-min`, `--gp5`, `--grips`, `--html`, `--melody`,
`--musicxml`, `--mutes`, `--non-chord-tone`, `--pick`, `--skeleton`, `--tab`,
`--texture`, `--vertical`. This is defect #4 in the table above, and it is the one
defect still open — a flag added to one CLI is silently missing from the other.

**Ship `arranger/cli.py`** with `add_common_arguments(parser)` and
`render_and_write(args)`. It is a **new file in the package**, so it needs no
`pyproject.toml` change (`packages = ["arranger"]` already covers it) and no
`MODULES` change (the Makefile names the directory). It must sit **below `steps`**
in `test_package_dag.py`'s `ORDER` or be added to `ALLOWED_EDGES` with a reason —
read that file's `ORDER` before creating it.

What must **not** change, and is the acceptance gate:

- **The two CLIs' output is not being unified.** They legitimately differ: the corpus
  prints a performer/key subtitle, `head` prints the notated metre. Only the shared
  argparse and dispatch move.
- Every flag keeps its current spelling, default, and `--help` text. The parser's
  *behaviour* is already pinned — `tests/test_wjazzd.py::TestCorpusCli` asserts
  `SystemExit` for a missing `--melid` and for an unknown choice, and
  `tests/test_headxml.py` drives `head_cli` through argv — so a flag that changes
  meaning fails. **The `--help` text itself is not asserted anywhere.** Capture both
  CLIs' help output before touching them, so a changed default is visible in the diff
  rather than discovered later.
- `corpus_cli` and `head_cli` keep their signatures and their `int` return; `main()`
  calls both.
- `headxml` imports `argparse` and the renderers *lazily inside* `head_cli` so
  `load_musicxml` costs nothing. If `cli.py` makes those eager, the import cost
  moves to module import — measure it before doing that, and keep laziness if you can.

Expect `corpus_cli` 531 → ~250 and `head_cli` 221 → ~140. The remainder is
corpus-specific (`--section`, `--list`, `--lift`, `--fallback`) or importer-specific,
and is not duplication.

### Phase 9 — CI (last)

`.github/workflows/ci.yml` running `make check` on push across 3.10–3.14 with the
`xml` and `gp` extras — so the two `skipUnless` guards are exercised every push,
which is exactly the class of defect this repo documents having shipped (the MusicXML
3.1 `kind` problem was invisible to a round trip). `wjazzd.db` is 42 MB and
gitignored, so a manual-dispatch job downloads it and runs the full suite; **say so
in the workflow header** so an agent does not assume the database tests ran. Bump
`__version__` to `0.10.0` — and note that `tests/test_docs.py` will then fail until
the version is updated in any document that states one, which is the point.

There is no CI config today. Phase 9 is also the natural place to sweep the loose
`*.gp5` files in the repository root, which are export artefacts rather than source.

---
