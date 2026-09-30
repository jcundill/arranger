# Implementation Plan

**Goal.** Restructure `jazz-arranger` so its *structure* carries the invariants its
comments currently carry in prose — because the maintainers are LLM agents, which
edit what they can find and cannot infer that a decision documented in one place is
duplicated in another.

**Status: Phases 0–4 done. Phase 5 (the package split) is next.**

| phase | what | state | tests |
|---|---|---|---|
| 0 | baseline + lint gate | **done** `1ae20af` | 677 |
| 1 | `tests/support.py`, one copy of each fixture | **done** `b4cadc7` | 677 |
| 2 | `Diagnostics`; no `print()` in the library | **done** `b4d51f4` | 694 |
| 3 | one implementation of each shared decision | **done** `9d3c7a1` | 702 |
| 4 | `ArrangeOptions`; `arrange_slots` delegates | **done** `b834cbf` | 714 |
| 5 | split `arranger.py` into a package | **next** | — |
| 6 | delete the import cycle | pending | — |
| 7 | CLI de-duplication | pending | — |
| 8 | docs (`AGENTS.md` is stale) | pending | — |
| 9 | CI and cleanup | pending | — |

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

Current measured state, all green: **714 tests OK (skipped=2)**, pyright **0 errors
0 warnings**, ruff **0 errors**. If your change moves any of those numbers, that is
the signal — not the absence of an error message.

`make check` exists because two things were wrong before it did: a linter was
absent, and `pyright` silently failed to find the virtualenv. See "Traps" below.

### The six defects this refactor is for

| # | defect | measurement | why it hurts an LLM agent |
|---|---|---|---|
| 1 | the step loop existed **twice** | `arrange_progression` 514 lines, `arrange_slots` 362 | the code said *"both copies must agree"*; an agent fixing one gets **no signal** about the other. The project had already paid for this once — the corpus path voiced `Am7` under a written `Bbm7` for 25 transcriptions |
| 2 | one 4290-line module | `arranger.py` held everything | "where is the cost tuple?" means paging through 4000 lines of music theory |
| 3 | the library **printed** to stdout | 8 warning sites | a warning could not be read by a test, silenced by a caller, or collected |
| 4 | two hand-copied argparse blocks | `corpus_cli` 280 lines, `head_cli` 221 | a flag added to one CLI is silently missing from the other |
| 5 | test fixtures copy-pasted | `make_step` ×2, `make_voicing` ×2, `bass_string` ×2 | divergent fixtures; a test passes for the wrong reason |
| 6 | docs stale and unenforced | `AGENTS.md` 1710 lines, says version `0.8.0` *and* `0.7.0` while `__version__` is `0.9.0`; **zero** mention of walking bass, which ships in 0.9.0 | an agent reads it as ground truth and acts on stale facts. **Phase 8.** |


## The target module layout (Phase 5's spec)

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


## What Phases 0–4 actually shipped

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

### Where the plan was wrong

Recorded because the next phase will hit the same thing:

- `select_step_voicing` was specified for `arranger/steps.py`; it went to
  `decisions.py` with `steps` as the caller, because `bass_cost` lives in `wjazzd`
  and `wjazzd` imports `decisions` — putting it in `steps` would have closed a cycle.
- `classify_slot` and a `SlotPolicy` class were specified and **not built**; the
  five extracted functions covered it.
- The equivalence test was to be added in Phase 4; it went in Phase 3, because that
  is where the shared decisions made it meaningful.

---

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

3. **A new runtime module must be added to `pyproject.toml`'s `py-modules`.**
   `diagnostics` was missed once; `import arranger` would have failed on a clean
   install. `decisions` and `options` are the same kind — imported *by* `arranger`,
   not optional extras.

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

## Phases 6–9, in brief

- **6 — delete the import cycle.** `tabstaff` imports `arranger` while `arranger`
  re-exports `tabstaff`'s names, which is why there is a PEP 562 `__getattr__`, a
  hand-maintained `__all__`, a `TYPE_CHECKING` re-import, and a
  `test_dunder_all_matches_the_public_surface` test. Once Phase 5 has made those
  imports ordinary, **all four are deleted** rather than maintained. Replace the
  test with `tests/test_public_surface.py`, which asserts each of the 45 public
  names resolves and is the *same object* as its home module — the assertion the
  deleted `__getattr__` made untestable.
- **7 — CLI de-duplication.** `arranger/cli.py` gets `add_common_arguments` (the ~25
  duplicated `add_argument` calls) and `render_and_write` (the duplicated
  `--html` / `--musicxml` / `--gp5` dispatch). `corpus_cli` 280 → ~120,
  `head_cli` 221 → ~140.
- **8 — docs.** `AGENTS.md` 1710 → ~400, version read from `__version__` rather than
  typed by hand, a **routing table** ("changing X? read Y") at the top, and
  `tests/test_docs.py::TestDocsMatchTheCode` asserting the stated version equals
  `arranger.__version__` and that every module appears in the layout block. That
  test *is* the fix for defect #6: documentation drift fails the suite instead of
  misleading the next agent. Also archive `walking_bass.md`, `CORPUS_PLAN.md`,
  `bass_lines.md` to `docs/history/`, and delete the stale `lead_sheet.py` (208
  lines querying tables that do not exist, which `AGENTS.md` already declares
  stale) with its test.
- **9 — CI.** `.github/workflows/ci.yml` running `make check` on push across
  3.10–3.14 with the `xml` and `gp` extras — so the two `skipUnless` guards are
  exercised every push, which is exactly the class of defect this repo documents
  having shipped (the MusicXML 3.1 `kind` problem was invisible to a round trip).
  `wjazzd.db` is 42 MB and gitignored, so a manual-dispatch job downloads it and
  runs the full suite; say so in the workflow header so an agent does not assume the
  database tests ran. Bump `__version__` to `0.10.0`.

---
