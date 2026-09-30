# Implementation Plan

**Status:** Phases 0–3 **done** (commits `1ae20af`, `b4cadc7`, `b4d51f4`, `9d3c7a1`).
Phase 4 next.
**Supersedes:** `docs/history/texture-plan.md` (the completed `texture="targets"` plan, 0.7.0).

| phase | what | state |
|---|---|---|
| 0 | baseline + lint gate | **done** — 677 tests OK, pyright 0/0, ruff 0/0 |
| 1 | `tests/support.py` + `tests/__init__.py` | **done** — 6 helpers de-duplicated, −101 lines |
| 2 | `Diagnostics`, delete `print` from the library | **done** — 8 print sites → a collector; 694 tests |
| 3 | extract the duplicated decisions | **done** — 5 decisions, one implementation each; 702 tests |
| 4 | `ArrangeOptions` + `arrange_slots` delegates | next |
| 5 | split `arranger.py` into a package | pending |
| 6 | delete the import cycle | pending |
| 7 | CLI de-duplication | pending |
| 8 | docs | pending |
| 9 | CI and cleanup | pending |

**Phase 3 note — what shipped, and what moved to Phase 4.** Five of the six
decisions moved to `decisions.py` and are now called from both loops. The sixth,
`select_step_voicing` (the corpus's slash-bass partition), did **not**: it is not a
*duplicated* decision — only the corpus has it — and folding it in here would mean
reaching back into `wjazzd` for `bass_cost`, closing an import cycle. It lands in
Phase 4, when `arrange_slots` is rewritten to delegate and `_arrange_step_with_bass`
(84 lines) is deleted.

**The two loops had not drifted on behaviour.** The divergences flagged while
planning (`wjazzd`'s `or slot_grips == ()`) turned out to be unreachable in the
fixtures. `tests/test_step_loop_equivalence.py` now compares the two entry points
over a texture × fixture matrix, and a second class asserts the *mechanism* — each
decision defined once, called by both loops, and neither loop's source containing
the old inline code. Without that second class the first could be coincidence on
the fixtures chosen.

**A bug this phase nearly shipped, recorded because the shape will recur.**
`melody_alone_case` first returned a `bool`, and merging the `NC` branch into the
walking-bass branch on that boolean would have set `melody_only=False` on an `NC`
bar — making the renderer annotate a step *"(no chord - melody alone)"* that
claims to have a chord. The two routes call the same function but build different
steps, so the predicate returns a **kind**. The general rule: when consolidating
two branches, check whether their *outputs* differ before unifying their
*predicates*.

---

# Overview

**Restructure `jazz-arranger` so its structure carries the invariants its comments
currently carry in prose** — because the primary maintainers are LLM agents, which edit
what they can find and cannot infer that a decision documented in one place is duplicated
in another.

The codebase is *behaviourally* healthy: 678 tests pass, the type discipline is real, and
the comment density is exceptional. It is *structurally* strained in six measurable ways,
each of which has already caused, or could cause, an agent to make a correct-looking change
that silently breaks something:

| # | Defect | Measurement | Why it hurts an LLM agent specifically |
|---|---|---|---|
| 1 | **The step loop exists twice** | `arranger.arrange_progression` L3223–3736 (514 lines) and `wjazzd.arrange_slots` L1790–2151 (362 lines) | Six decisions are re-implemented, and the code says so: *"Both copies must agree"*, *"mirrors the one in `arrange_progression`"*. An agent fixing one has **no signal** it must fix the other. This is the exact failure the repo already documents having suffered once (ATTYA bar 62). |
| 2 | **One 4251-line module** | `arranger.py` holds tuning, chord tables, grips, cost, textures, bass, step loop, renderers, CLI and a 143-line demo | An agent searching for "where does the cost tuple live" must page through 4000 lines of unrelated music theory. The stated "single-module" convention has outlived its rationale. |
| 3 | **The library prints to stdout** | 6 warning sites inside the engine (L3196, 3437, 3489, 3587, 3659, 3772) + 2 in `wjazzd` | Diagnostics are untestable except by `redirect_stdout` (10 sites in tests) and un-composable for a caller embedding the library. |
| 4 | **Two hand-copied argparse blocks** | `corpus_cli` (280 lines), `head_cli` (221 lines) — ~25 identical `add_argument` calls + duplicated renderer-dispatch tails | A flag added to one CLI is silently missing from the other. |
| 5 | **Test helpers copy-pasted** | `make_step` ×2, `make_voicing` ×2, `bass_string` ×2, `names` ×2; no `tests/support.py` | Divergent fixtures; a test can pass for the wrong reason. |
| 6 | **Docs are large, stale, and unenforced** | `AGENTS.md` = 1710 lines; says version `0.8.0` (L604) *and* `0.7.0` (L1708) while `__version__` is `0.9.0`; **zero** mentions of "walking" despite walking bass shipping in 0.9.0; layout omits `grip_chart.py`, `test_bass.py`, `test_walking_bass.py`, `test_grip_chart.py`. 6 markdown files = 6265 lines / 353 KB. | An agent reads AGENTS.md as ground truth and acts on stale facts. This is the highest-severity item for an LLM-maintained repo, and the cheapest to fix. |

Plus: **no CI, no linter, no formatter** (max line length 122), and **`lead_sheet.py` is
dead** — 208 lines querying tables that do not exist, which `AGENTS.md` L1704 already
declares stale.

**Approach.** Behaviour-preserving at every step, with one deliberate exception the user has
approved: an `ArrangeOptions` object and a `Diagnostics` collector replace the growing
keyword lists and `print()`. Each phase lands green on its own. The centrepiece is
**defect #1**: collapse the two step loops into one, with the corpus path's slash-bass rule
expressed as *data* (a per-index bass pitch class) rather than as a parallel copy of the
loop.

A deliberate, high-value side effect: once `tabstaff`/`tabxml`/`tabgp` import real
submodules instead of `arranger`, the import cycle disappears — and with it the PEP 562
`__getattr__`, the hand-maintained `__all__`, the `TYPE_CHECKING` re-import, and the
`test_dunder_all_matches_the_public_surface` test. **Four pieces of complexity that exist
only to work around a self-inflicted cycle get deleted rather than maintained.**

---


# Types

All new types are **additive and defaulted**. No existing signature is narrowed. `Voicing`
and `ArrangementStep` keep their `__getitem__` shims and every existing field, so all 678
tests' construction sites keep working.

## New: `arranger/options.py`

```python
@dataclass(frozen=True)
class ArrangeOptions:
    """Every knob arrange_progression(ArrangeOptions) reads. Frozen and defaulted so
    an existing caller passing keywords is unaffected."""
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL
    non_chord_tone: str = "extension"
    fret_min: int = NECK_FRET_MIN
    fret_max: int = NECK_FRET_MAX
    grips: Tuple[str, ...] = GRIP_PREFERENCE
    texture: str = "uniform"
    beats_per_bar: int = 4
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None
    # --- new, and the reason the two step loops can be merged ---
    # Per-progression-index bass pitch class for the slash-chord preference (rule C).
    # None / absent => no restriction, i.e. exactly today's library behaviour.
    bass_pcs: Optional[Mapping[int, Optional[int]]] = None
```

**Why `Sequence` and not `List` for `timings`** — this is load-bearing, not stylistic. The
library and the corpus hold *different* timing types (`Tuple[int, float, ...]` vs
`Tuple[Optional[int], ...]` placeholders). `List` is invariant so neither is assignable to
the other; `Sequence` is covariant so both are accepted. `_walking_slots` L746–755
documents this as "the third time list invariance in a signature has cost this library
something". The new type must not become the fourth.

**Why `bass_pcs` is data, not a hook** — this is the load-bearing design decision of the
whole refactor. The corpus path's only step-selection difference from the library is:
*partition candidates by `bass_cost`, then let the engine's own `_best_voicing` choose
within the best group*. That is a filter over a list, not a control-flow fork. Encoding it
as a mapping means `wjazzd.arrange_slots` needs **no step loop at all** — it becomes a
pre-pass (dim7 rewrite) plus a call. See Functions.

## New: `arranger/diagnostics.py`

```python
@dataclass
class Diagnostics:
    """Collector for engine warnings. Replaces print() inside the library.

    `emit` is the escape hatch that preserves today's behaviour: a Diagnostics
    created with emit=print writes each warning to stdout as it happens, so the
    default path is byte-identical to the six print() calls it replaces. Tests
    construct Diagnostics() and read `.warnings`.
    """
    warnings: List[str] = field(default_factory=list)
    emit: Optional[Callable[[str], None]] = None

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        if self.emit is not None:
            self.emit(message)
```

Chosen over a logging module because the existing messages are *user-facing prose* already
tuned for a terminal reader ("`Warning: {name} with melody {melody} needs a 5-fret stretch
(…); playing the melody alone`"). Routing them through `logging` would reformat text that
tests and the demo print verbatim, for no gain — the library has no other logging and one
consumer.

```python
def default_diagnostics() -> Diagnostics:
    """A collector that prints, which is what a caller who passes nothing gets."""
    return Diagnostics(emit=print)
```

## Modified: `ArrangementStep` — **no field changes**

All 18 fields stay exactly as they are, including `role`, `metric_weight`, `bass`,
`bass_role`, `bass_only`. They are correct and well-documented. The only change is that
construction sites move into the unified loop.

# Files

## New modules (the split of `arranger.py`)

| Path | Contents | Lines (approx) |
|---|---|---|
| `/home/jon/sda4/code/arranger/arranger/__init__.py` | **Facade.** Re-exports every current public name, holds `__version__`, `main()`. No engine logic. | ~150 |
| `arranger/tuning.py` | `STANDARD_TUNING`, `STRING_NAMES`, `PITCH_CLASS_NAMES`, `NO_CHORD`, `GuitarFretboard`, `_note_name` | ~60 |
| `arranger/chords.py` | `ChordParser` + its three tables, `normalised_harmony`, `sounding_harmony` | ~230 |
| `arranger/grips.py` | `GRIP_PREFERENCE`, `GRIP_MAX_SPAN`, `GRIP_STRING_SETS`, `SHELL_DEGREES`, `DUO_DEGREES`, `BASS_DEGREES_6432`, `MELODY_STRING_CHOICES*`, `HIGH_FRET_LIMIT`, `supported_string_sets`, the `_place_*` / `_close_stack_offsets` / `_duo_offsets` / `_interval_offsets` builders, and the generators | ~700 |
| `arranger/cost.py` | `voicing_cost`, `_best_voicing`, `_window_penalty`, `calculate_*_distance`, `bass_cost` | ~260 |
| `arranger/textures.py` | `ROLE_TARGET`, `ROLE_FILL`, `TEXTURE_STYLES`, `TARGET_BEATS`, `TEXTURE_GRIPS`, `_BEAT_EPSILON`, `_metric_weight`, `_roles_for_slot` | ~130 |
| `arranger/bass.py` | `BassNote`, `BASS_ROLE_*`, `BASS_STRING_INDICES`, `_Slot`, `_walking_slots`, `_bass_slots`, `_walking_bass_line`, `_place_bass`, `_previous_bass`, `_bass_harmony`, `_bass_distance` | ~450 |
| `arranger/steps.py` | `ArrangementStep`, `StepPreparation`, **`VoiceLeadingEngine`**, `arrange_progression`, the single step loop | ~900 |
| `arranger/render.py` | `_step_annotation`, `_bass_annotation`, `_MUTED_CELL`, `_STAFF_CELL_WIDTH`, `_BLANK_CELL`, `_cells_from_frets`, `_tab_block_from_cells`, `_step_cells`, `format_progression`, `_print_step` | ~200 |
| `arranger/options.py` | `ArrangeOptions` | ~50 |
| `arranger/diagnostics.py` | `Diagnostics`, `default_diagnostics` | ~45 |
| `arranger/cli.py` | `add_common_arguments`, `render_and_write` (shared argparse + renderer dispatch) | ~180 |

**Naming note.** Converting `arranger.py` to a package `arranger/` while keeping the import
name `arranger` preserves `from arranger import VoiceLeadingEngine` and the `jazz-arranger`
console script unchanged. `pyproject.toml` switches `py-modules = [...]` to
`packages = ["arranger"]`. The flat `tabstaff`/`tabxml`/`tabgp`/`wjazzd`/`headxml` modules
stay flat and import from the package.

**Dependency direction is strictly one-way, forming a DAG:**

```
tuning ← chords ← grips ← cost
                    ↑        ↑
                 textures  bass
                    ↑        ↑
                 options ────┘
                    ↑
                  steps → render → (facade)
```

No module imports `steps` except `arranger/__init__.py` and `arranger/cli.py`. This is what
makes defect #2 fixable without cycles.



---



## Modified files

| Path | Change |
|---|---|
| `/home/jon/sda4/code/arranger/arranger.py` | **Becomes** `arranger/__init__.py` (content moved per the table above). `git mv` then extract, so history follows. |
| `/home/jon/sda4/code/arranger/tabstaff.py` | `from arranger import STRING_NAMES, ArrangementStep, _MUTED_CELL` → `from arranger.render import _MUTED_CELL`, `from arranger.tuning import STRING_NAMES`, `from arranger.steps import ArrangementStep`. **Delete** the local `_STAFF_CELL_WIDTH` (L29) and import it from `arranger.render` — it is currently defined twice, identically, in both files. |
| `/home/jon/sda4/code/arranger/tabxml.py` | Imports repointed at the submodules. No logic change. |
| `/home/jon/sda4/code/arranger/tabgp.py` | Imports repointed. No logic change. |
| `/home/jon/sda4/code/arranger/wjazzd.py` | **`arrange_slots` (362 lines) reduced to ~90.** `corpus_cli` (280) reduced to ~120. `_MUTED_CELL`/renderer imports repointed. |
| `/home/jon/sda4/code/arranger/headxml.py` | `head_cli` (221 lines) reduced to ~140. `from wjazzd import parse_bar_range` retained. |
| `/home/jon/sda4/code/arranger/lead_sheet.py` | **Deleted**, with `tests/test_lead_sheet.py`. `AGENTS.md` L1704 already declares it stale: it queries `melopy_notes`, `chord_type`, `rel_pitch_class`, `solo_info.tempo` — none exist. Nothing in the package imports it (`pyproject.toml` does not list it). |
| `/home/jon/sda4/code/arranger/grip_chart.py` | Unchanged logic. Left as a flat top-level dev tool (documented as such at L33–36). |
| `/home/jon/sda4/code/arranger/pyproject.toml` | `py-modules` → `packages = ["arranger"]`; add `[project.optional-dependencies] dev = ["pyright", "ruff"]`; add `[tool.ruff]` with `line-length = 100`. |
| `/home/jon/sda4/code/arranger/Makefile` | Add `lint`, `format`, `check` (test+typecheck+lint) targets; add `ruff` to the "not installed" hint pattern already used for pyright. |
| `/home/jon/sda4/code/arranger/AGENTS.md` | **Reduced 1710 → ~400 lines** and made accurate. See Phase 8. |
| `/home/jon/sda4/code/arranger/.gitignore` | Add `.ruff_cache/`, `docs/history/`. |
| `/home/jon/sda4/code/arranger/.github/workflows/ci.yml` | **New.** See Testing. |

## Files moved (not deleted — history and content preserved)

| From | To | Why |
|---|---|---|
| `walking_bass.md` (1621 lines) | `docs/history/walking_bass.md` | A completed design record. Useful provenance, but an agent scanning the root for "how does walking bass work" should not wade through 1621 lines of decision archaeology to find the 8 lines that are current behaviour. |
| `CORPUS_PLAN.md` (966 lines) | `docs/history/CORPUS_PLAN.md` | Same. Contains ~30 open questions, several since closed. |
| `bass_lines.md` (198) | `docs/history/bass_lines.md` | Same. |
| `implementation_plan.md` (321, completed texture plan) | `docs/history/texture-plan.md` | **Done in Phase 0.** Superseded by this plan. |
| `Arranging_Guide.md` (260) | `docs/arranging_guide.md` | Current and useful — stays in `docs/`, not archived. |
| `common_grips.md` (99) | stays at root | Generated artifact of `make chart`. |

**Root after the refactor**: 6 Python modules + 1 package, `tests/`, `docs/`, `README.md`,
`AGENTS.md`, `LICENSE`, `Makefile`, `pyproject.toml`, `.gitignore`. That is a directory an
agent can enumerate in one screen.


# Functions

## Removed from the public surface

**None.** Every name in the current `__all__` (L4205–4252, 45 names) continues to resolve
from `arranger`. This is a hard constraint of the whole plan.

## Deleted as *complexity*, not as capability

These exist **only** because `tabstaff` imports `arranger` while `arranger` re-exports
`tabstaff`'s names. Once the cycle is gone, all four are unnecessary:

| Removed | File / lines | Replaced by |
|---|---|---|
| `arranger.__getattr__` | `arranger.py` L3978–3982 | Direct `from arranger.render import format_progression` in the facade. |
| `arranger.__dir__` | L3985–3987 | Removed (stdlib default is correct once names are real). |
| `_TABSTAFF_EXPORTS` | L3964–3975 | Removed. |
| The `if TYPE_CHECKING:` re-import block | L4190–4199 | Removed — the names are now real. |
| `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface` | `tests/test_tab_rendering.py` L1075 | **Replaced** by a stronger test (Testing). |

## Modified functions

| Function | File | Required change |
|---|---|---|
| `VoiceLeadingEngine.arrange_progression` | `arranger/steps.py` | 514 lines → **~200**. Body becomes: validate options → validate texture/non_chord_tone → build the slot loop → delegate each slot to the six extracted decision functions → attach bass → append. **No decision logic remains in the loop body.** |
| `VoiceLeadingEngine._attach_bass` | `arranger/steps.py` | Unchanged logic; takes a `Diagnostics` instead of printing. |
| `VoiceLeadingEngine.voicing_cost` | `arranger/cost.py` | **Unchanged** — the 8-element tuple is the library's core invariant and `tests/test_grips.py::TestVoicingCost` asserts on it positionally. Moved verbatim. |
| `VoiceLeadingEngine.prepare_step` | `arranger/steps.py` | Unchanged logic; takes `Diagnostics`. |
| `VoiceLeadingEngine.get_grip_voicings` and siblings | `arranger/grips.py` | Unchanged logic, moved verbatim. |
| `wjazzd.arrange_slots` | `wjazzd.py` | **362 → ~90 lines.** New body: (1) validate texture/fallback; (2) build `typed_timings`; (3) if `fallback == "diminished"`, do the `resolve_non_chord_tone` rewrite as a **pre-pass** over a copy of `triples` (it already works on a copy — L1861) and collect `rescued`; (4) build `bass_pcs: Dict[int, Optional[int]]` by calling the existing `promote_slash_chord` / `bass_pitch_class` rules per index; (5) build `loop_slots` via the already-shared `_walking_slots`; (6) call `arrange_progression(triples, options=ArrangeOptions(..., bass_pcs=bass_pcs), diagnostics=...)`; (7) return `(steps, rescued, notes)`. **The step loop is gone from this module.** |
| `wjazzd._arrange_step_with_bass` | `wjazzd.py` | **Deleted** (84 lines) — superseded by `select_step_voicing`. |
| `wjazzd.corpus_cli` | `wjazzd.py` | 280 → ~120. Argparse body → `add_common_arguments` + the 5 corpus-only flags (`--melid`, `--list`, `--section`, `--bars`, `--lift`). Tail → `render_and_write`. |
| `headxml.head_cli` | `headxml.py` | 221 → ~140. Same treatment; keeps `file`, `--part`, `--bars`. |
| `_step_annotation` / `_bass_annotation` | `arranger/render.py` | Unchanged logic, moved verbatim (they are already the shared annotation core the renderers use). |
| `arranger.main` | `arranger/__init__.py` | 143 lines of demo. **Split**: the arrangement *fixtures* move to `arranger/demo.py` as module constants; `main()` keeps only the print orchestration. The current demo prints "Example 8" three times (L4152, L4161, L4173) — a numbering bug an agent will trip over; renumber while moving. |

## Retained deliberately (and why)

`arrange_progression` keeps its `melody_only`, `repeated`, `original_melody`, `partial`,
`role`, `metric_weight` behaviour **byte-identically**.
`tests/test_texture.py::TestBackwardCompatibility` and
`tests/test_walking_bass.py::TestNoRegression` already pin exact tab strings for these, and
they are the acceptance gate for every phase.

---

# Classes

## New classes

| Class | File | Base | Key members | Purpose |
|---|---|---|---|---|
| `ArrangeOptions` | `arranger/options.py` | — | 8 defaulted fields, `frozen=True` | The keyword list, as a value. Makes "what can change per arrangement" enumerable in one place. |
| `Diagnostics` | `arranger/diagnostics.py` | — | `warnings: List[str]`, `emit: Optional[Callable]`, `warn(str)` | The `print()` replacement, with an `emit` hook that preserves today's default output. |
| `SlotPolicy` | `arranger/textures.py` | — | `role`, `metric_weight`, `grips`; `classify(weight, texture, ...)` | Encapsulates the three things derived from a slot's position, so the loop cannot get them out of order or apply one and forget another. |

## Modified classes

| Class | File | Change |
|---|---|---|
| `VoiceLeadingEngine` | `arranger/steps.py` (was `arranger.py` L2024–3800, 1776 lines) | **Split by concern.** The generation half (`DROP2_INTERVAL_SETS`, `DEGREE_OFFSETS_FROM_ROOT`, `CHORD_TONES_FROM_ROOT`, `get_grip_voicings`, `get_drop2_voicings`, `get_interval_voicings`, `get_all_grip_voicings`, `get_octave_down_candidates`, `get_melody_only_voicing`, `_place_*`, `_string_sets_for`) moves to `arranger/grips.py` as free functions. The selection half (`voicing_cost`, `_best_voicing`, `_window_penalty`, `sustain_inner_voices`, `calculate_*_distance`) to `arranger/cost.py`. What remains in `steps.py` is `NON_CHORD_TONE_*`, `resolve_non_chord_tone`, `is_chord_tone`, `prepare_step`, `arrange_progression`, `_attach_bass` — roughly 400 lines. |
| | | **Backward compatibility:** `VoiceLeadingEngine.get_drop2_voicings(...)` etc. **must keep working** as classmethods — ~40 call sites in tests use them, and `AGENTS.md` documents them as the public grip entry points. They become thin `@classmethod` delegates to the `grips` free functions. The delegate is the *only* acceptable duplication here: it is mechanical, and it is what lets the engine shrink to 400 lines. |
| `Voicing` | `arranger/grips.py` | **Unchanged** — all fields, `__getitem__` shim, and the frozen AGENTS.md-documented accessors (`tab_string`, `tab_block`, `midi_notes`, `pitch_classes`, `soprano_string`, `fret_span`, `upper_midi_notes`). |
| `ArrangementStep` | `arranger/steps.py` | **Unchanged** — all 18 fields. |
| `ChordParser` | `arranger/chords.py` | Unchanged; moved. |
| `GuitarFretboard` | `arranger/tuning.py` | Unchanged; moved. |
| `BassNote` | `arranger/bass.py` | Unchanged; moved. |
| `_Slot` | `arranger/bass.py` | Unchanged; moved. |
| `StepPreparation` | `arranger/steps.py` | Unchanged; moved. |
| `Section` / `NoteEvent` / `Solo` / `Skeleton` / `HeadSelection` / `HeadArrangement` | `wjazzd.py` | Unchanged. |
| `Head` / `HeadNote` | `headxml.py` | Unchanged. |

## Removed classes

**None.** `WeimarChord` (wjazzd L207) is `frozen=True` and near-unused outside
`parse_weimar_chord`'s own return; it is left alone rather than folded, because touching it

# Dependencies

**No new runtime dependency.** The standing rule in `AGENTS.md` ("musthe is the only
runtime dependency") is preserved and remains load-bearing for the LGPL reasoning around
PyGuitarPro.

| Change | Package | Kind | Integration |
|---|---|---|---|
| `ruff` | `ruff>=0.6` | **dev-only** | New `[project.optional-dependencies] dev` group alongside pyright. Never imported by the package. |
| `pyright` | unchanged | dev-only | Already used; its absence is currently only hinted at in the Makefile. Move both to the `dev` extra and add `make install-dev`. |

**Deliberately not added:** `pytest` (the suite is `unittest` and works), `mypy` (pyright
covers it), any formatter other than `ruff format` (one tool, not two).

**CI installs:** a venv with `pip install -e '.[dev,xml,gp]'`. Both extras in CI is
deliberate — it means the two `skipUnless` guards are exercised on every push rather than
only on the maintainer's machine, which is exactly the class of bug this repo documents
having shipped (the MusicXML 3.1 `kind` defect was invisible to `converter.parse()`).

**`wjazzd.db` is not in CI.** The 42 MB file is gitignored, so CI runs the reduced suite.
Add an optional manual-dispatch workflow job that downloads it and runs the full suite — a
label an agent can be told to check. This is stated in the CI file's own header so an agent
does not assume the database tests ran.

**`ruff` is a linter here, deliberately NOT a formatter.** This was measured, not
assumed. Running `ruff format` over the tree rewrote 24 files and **inflated the data
tables**: `SHELL_DEGREES` went from 10 lines to 31, one `(3rd, 7th)` pair per line, and
`GRIP_STRING_SETS` and `DROP2_INTERVAL_SETS` the same way. Those tables are hand-authored
music-theory data laid out in aligned columns so a human (or an agent) can compare a
quality against its 3rd and 7th at a glance. One-per-line is 3× the vertical space for
the same information and strictly harder to scan — a readability regression in a
refactor whose entire purpose is readability for an LLM-maintained codebase. So
`make format` exists for a *targeted* file when a contributor wants it, and is **not**
part of `make check`. The 100-character limit is documented as a convention; only
21 library lines exceed it, and they are the hand-aligned tables.


# Testing

## Strategy

The suite is the safety net and it is already good: 678 tests, all passing, heavily pinning
exact tab strings. The refactor's job is to **not break it**, and to **add the three tests
that would have caught the defects this refactor fixes.**

## New: `tests/support.py`

The single home for the copy-pasted fixtures. Public surface:

```python
def make_voicing(frets, *, grip="drop2", bass_midi=None, bass_string=None, **kw) -> Voicing
def make_step(frets, chord="Cmaj7", melody="B4", **kw) -> ArrangementStep
def bass_string(step) -> int
def note_name(midi: int) -> str
def pc(name: str) -> int
def names(step) -> str
def tab(step) -> str
def capture_diagnostics(fn, *a, **kw) -> Tuple[Any, List[str]]
```

`capture_diagnostics` is the important one — it removes all 10 `redirect_stdout` sites by
giving the same assertion in a readable form:

```python
# before
buffer = io.StringIO()
with redirect_stdout(buffer):
    engine.arrange_progression(prog)
self.assertIn("needs a 5-fret stretch", buffer.getvalue())

# after
steps, warnings = capture_diagnostics(engine.arrange_progression, prog)
self.assertTrue(any("needs a 5-fret stretch" in w for w in warnings))
```

Requires `tests/__init__.py` (does not currently exist) so `from tests.support import ...`
resolves. **Adding it changes discovery** — `unittest discover -s tests` currently inserts
`tests/` on `sys.path` and finds modules as top-level; with `__init__.py` it must be run as
`discover -s . -p 'test_*.py'` or `-t .`. This is a real, easy-to-miss breakage; the
Makefile and `AGENTS.md` are updated in the same commit and `make test` is verified.

## The three tests this refactor is justified by

**1. `tests/test_step_loop_equivalence.py` — the one that matters most.**
A property test over a corpus of `(melody, quality, name)` triples × every texture × both
entry points, asserting `arrange_progression(prog, texture=T, timings=tm)` and
`wjazzd.arrange_slots(prog, timings=tm, texture=T)` produce **identical** `tab_string()`
per step, identical `grip`, `partial`, `repeated`, `role`, `metric_weight`, and identical
warning text. No database required — hand-built fixtures only, so it is never skipped.

## Modified test files

| File | Change |
|---|---|
| `tests/test_tab_rendering.py` | Delete `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface` (L1075, 37 lines) → superseded by `test_public_surface.py`. Keep `test_tabstaff_shares_the_layout_core` — that invariant is real and still holds. Update the `_MUTED_CELL` import. |
| `tests/test_walking_bass.py`, `test_bass.py`, `test_grips.py`, `test_guitarpro.py`, `test_musicxml.py`, `test_texture.py`, `test_progressions.py` | Replace local `make_voicing` / `make_step` / `bass_string` / `note_name` / `pc` / `names` with `from tests.support import ...`. **No assertion changes** — this is a pure de-duplication and any assertion diff here means something moved semantically. |
| `tests/test_lead_sheet.py` | Deleted with `lead_sheet.py`. |
| `tests/test_wjazzd.py`, `test_headxml.py` | `arrange_slots` / `arrange_xml_head` call sites gain `options=` where the new API is exercised; the existing positional calls keep working via `**legacy_kwargs`, so most need no edit. |

## Unchanged (the acceptance gate)

`tests/test_texture.py::TestBackwardCompatibility`,
`tests/test_walking_bass.py::TestNoRegression`,
`tests/test_guitarpro.py::TestRoundTrip`, `tests/test_headxml.py::TestRealScores`,
`tests/test_grips.py::TestVoicingCost` — these must pass **unmodified** at every phase
boundary. Any diff in them is a bug in the refactor, not an update to the test.

## Validation per phase

```bash
make check     # lint + typecheck + test, all three
make test      # 678+ tests, must report OK
```

### Measured Phase 0 baseline

Recorded 2026-09-30, so a later phase can tell *drift* from *regression*:

| check | baseline |
|---|---|
| `python -m unittest discover -s tests` | **678 tests, OK (skipped=2)**, 49–79s |
| `pyright` over the 6 modules + `tests/` | **0 errors, 0 warnings** |
| `ruff check`, configured rule set | **0 errors** (from 51) |

The pyright figure was *asserted* in AGENTS.md but had never been verified — an earlier
invocation produced **no output at all**, which is why the baseline is now taken with
`--outputjson` rather than read off the plain run's exit code.

**pyright needs `--pythonpath`, and that is now in the Makefile.** Run bare, pyright
reported **32 errors, all of them `Import "musthe" / "music21" / "guitarpro" could not be
resolved`** — despite all three being installed and importing fine under
`.venv/bin/python`. With `--pythonpath .venv/bin/python` it is back to **0 errors**. This
is a real trap and it is worth naming: a type-checker that cannot see the virtualenv
reports import failures that look exactly like type failures, and a CI job wired the
naive way would be red from day one. `make typecheck` now pins the interpreter.

### Three real defects the linter found

These are the argument for Phase 0 existing at all. They are exactly the class of problem
a comment cannot surface:

1. **Three tests that could not fail.** All green at 678 tests — which is the point: the
   suite reported coverage it did not have.
   - `test_chord_parser.py::test_parse_simple_roots_and_qualities` built a 12-case table
     and never used it; the real assertions were four hand-copied lines below. Now driven
     through `subTest`, so a regression *names the chord that broke*.
   - `test_grip_chart.py::test_every_sounding_pitch_is_a_chord_tone` computed the chord's
     tone set and stopped — the test's name is exactly the property it never checked. Now
     checks every sounding pitch, which is the defect the hand-written chart actually had.
   - `test_headxml.py` had **two** methods of the same name for one scenario: a stub that
     loaded a score and asserted nothing, and a complete one in `TestLoadingTail`. The
     stub is deleted, the survivor kept.
2. **9 unused imports**, two a latent trap: `test_wjazzd.py` imported `format_musicxml`
   without using it, and `test_musicxml.py` imported `arranger.format_musicxml` inside a
   function — both look like a test that was meant to assert on the export and does not.
3. **5 half-used tuple unpacks** (`for strings, soprano in ...`, one half unread) — now
   `_strings` / `_soprano`, which also documents the intended shape.

# Implementation Order

Nine phases. Each lands green on its own; each is a separate commit. The order is chosen so
that **every phase that can be verified cheaply is verified before the next risky one
starts.**

**Phase 0 — Baseline and tooling (no behaviour change).**
Re-run the suite; record 678 tests / OK. Re-run pyright and **record the true error
count**. Add `ruff` config, `dev` extra, `make lint` / `make format` / `make check`. Run
`ruff format` as its **own commit** so the structural diffs that follow stay reviewable.
*Exit: 678 tests OK, pyright count recorded, lint clean.*

**Phase 1 — `tests/support.py` + `tests/__init__.py`.**
Add the shared helpers, migrate all 11 call sites, update the Makefile's `test` target and
`AGENTS.md`'s Testing section for the new discovery invocation. No library change. *Exit:
suite OK, zero duplicated helpers (verified by grep).* **This must precede the split** —
once modules move, a helper referencing `arranger.X` needs a stable home.

**Phase 2 — `Diagnostics` (delete `print` from the library).**
Add `diagnostics.py` first (flat, to avoid two moves at once). Thread `diagnostics=`
through the 8 sites. Write `test_diagnostics.py` — including the byte-identical-stdout
assertion. *Exit: 678 OK, `grep -c 'print(' arranger*.py` returns only the demo.*

**Phase 3 — Extract the six duplicated decisions into one place.**
Pure extraction: `resolve_texture_grips`, `classify_slot`, `select_step_voicing`,
`demote_to_melody_alone`, `is_repeated_step`, `is_melody_alone_case`,
`promote_fill_to_target` — each moved out of **both** copies, each with one implementation.
Both loops call the shared version. `wjazzd._arrange_step_with_bass` deleted. *Exit: 678
OK. This is the phase where `wjazzd.arrange_slots` drops from 362 to ~90 lines. Any
behaviour difference here is a bug the extraction surfaced — fix the shared function, never
re-diverged it.*

**Phase 4 — `ArrangeOptions`.**
Add the frozen dataclass; `arrange_progression` accepts `options=` alongside the legacy
keywords. Rewrite `arrange_slots` to build `bass_pcs` and delegate. Delete the
now-redundant per-keyword threading. **Add `tests/test_step_loop_equivalence.py` here** —
the first version is expected to *fail*, and the failures are the two known predicate
divergences (`slot_grips == ()` at `wjazzd.py` L2012). Fix them in the shared function.
*Exit: 678 OK + equivalence test green.*

**Phase 5 — Split `arranger.py` into the package.**
`git mv arranger.py arranger/__init__.py`, then extract the 12 submodules along the
dependency DAG above. `pyproject.toml` → `packages = ["arranger"]`. Repoint `tabstaff` /
`tabxml` / `tabgp` / `wjazzd` / `headxml`. Delete `_STAFF_CELL_WIDTH`'s duplicate

**Phase 8 — Docs.**
`docs/` split. `AGENTS.md` 1710 → ~400 lines, with: corrected version (0.9.0, from
`arranger.__version__`, not typed by hand), the full current module list, the new package
layout, a **routing table** ("changing X? read Y") at the top — the single highest-value
addition for an LLM-maintained repo, since it replaces "read 1710 lines to find the relevant
paragraph" with a lookup. Add `tests/test_docs.py::TestDocsMatchTheCode`, which asserts
AGENTS.md's stated version equals `arranger.__version__` and that every `arranger/*.py`
module appears in its layout block. **That test is the fix for defect #6**: documentation
drift now fails the suite instead of misleading the next agent. README updated for the
package layout and the two new types. *Exit: 678 OK + doc test green.*

**Phase 9 — CI and cleanup.**
`.github/workflows/ci.yml`: `make check` on push/PR across 3.10–3.14, with `xml` + `gp`
extras, plus a manual-dispatch job that downloads `wjazzd.db` and runs the full suite.
Delete `lead_sheet.py` + `tests/test_lead_sheet.py`. Remove the now-stale `lead_sheet.py`
bullet from AGENTS.md. Archive `walking_bass.md` / `CORPUS_PLAN.md` / `bass_lines.md` to
`docs/history/`. Bump `__version__` to `0.10.0` — a structural change with two new public
types justifies a minor bump, and it makes the version-drift test's first run meaningful.
*Exit: CI green on all five Python versions.*

## Rollback

Every phase is an independent commit with a green suite behind it. Phase 3 is the one with
real semantic risk (it is where the two loops' divergences surface); if it proves
intractable, it can be reverted without touching phases 0–2, which are pure additions.

---

## What I deliberately did not do

- **Did not touch `voicing_cost`'s tuple.** The 8-element lexicographic order is the
  library's central invariant and is positionally asserted in
  `tests/test_grips.py::TestVoicingCost`. Moving the code is safe; changing the order is a
  musical decision, not a refactor.
- **Did not convert the 54 hardcoded tab strings in the tests into golden files.** They are
  the acceptance gate. Replacing them with a snapshot mechanism would make a regression
  *pass* by regenerating the snapshot.
- **Did not add `pytest`, a package layout with subpackages under `tests/`, or any runtime
  dependency.**
- **Did not unify the two `head_cli`/`corpus_cli` outputs.** They legitimately differ (the
  corpus prints a performer/key subtitle, `head` prints the notated metre). Only the shared
  argparse and dispatch are unified.

definition. **Split into at least 5 commits** (constants+chords / grips+cost /
textures+bass / steps+render / facade), each green. *Exit: 678 OK, no module > 1000 lines,
dependency DAG holds (asserted by an import test).*

**Phase 6 — Delete the import cycle and its four workarounds.**
Now that `tabstaff` imports real submodules, the facade can import them eagerly. Delete
`__getattr__`, `__dir__`, `_TABSTAFF_EXPORTS`, the `TYPE_CHECKING` block. Add
`test_public_surface.py`. *Exit: 678 OK + 45 public names resolve and are identical
objects.*

**Phase 7 — CLI de-duplication.**
`cli.py`: `add_common_arguments` + `render_and_write`. Rewrite `corpus_cli` and `head_cli`
against them. *Exit: 678 OK; the `--texture` / `--grips` / `--bars` flags provably identical
between the two CLIs (asserted in `test_wjazzd.py::TestCorpusCli` and `test_headxml.py`).*

---



This test **cannot exist before the refactor** (it would fail today — the two loops are not
yet proven equivalent, and the divergences in decisions #2/#5 are real: `wjazzd.py` L2012
has `or slot_grips == ()` where `arranger.py` L3459 does not). Writing it first, seeing it
fail, then merging the loops until it passes is the correct order of operations. It is the
structural regression test for defect #1 and it is what stops the divergence from recurring.

**2. `tests/test_diagnostics.py`.** Every one of the 8 former `print` sites:
- with `Diagnostics()` (no `emit`) → **no stdout** (proves the library is silent);
- the same call with `default_diagnostics()` → stdout **byte-identical** to before (proves
  behaviour is preserved);
- `arrange_progression` accepts `diagnostics=` and messages land in `.warnings`.

**3. `tests/test_public_surface.py`.** Replaces the deleted
`test_dunder_all_matches_the_public_surface`. Asserts the 45 current `__all__` names all
resolve from `arranger`, that `from arranger import *` works, and — the new part — that
each resolves to the **same object** as its home module
(`arranger.render.format_progression is arranger.format_progression`). That last assertion
is what the deleted `__getattr__` made untestable.


---


is unrelated churn.

---



`__all__` remains, now explicit in the facade and asserted by a test that checks it against
`dir(arranger)` — cheaper than the current test because there is no `__getattr__` for it to
be confused by.

## New functions

| Function | File | Signature | Purpose |
|---|---|---|---|
| `resolve_texture_grips` | `arranger/textures.py` | `(role: str, texture: str, requested: Tuple[str, ...], diagnostics: Diagnostics) -> Tuple[str, ...]` | **Extracts duplicated decision #1** verbatim from `arranger.py` L3425–3441 and `wjazzd.py` L1953–1969. Returns the narrowed grip tuple and warns on an empty intersection. One implementation, one warning site. |
| `classify_slot` | `arranger/textures.py` | `(weight: int, texture: str, harmony_changed: bool, melody_moves: bool) -> str` | Wraps `_roles_for_slot(...)[0]` so both call sites stop discarding all but the first element. The list return is vestigial. |
| `arrange_progression` | `arranger/steps.py` | `(progression, *, options: Optional[ArrangeOptions] = None, diagnostics: Optional[Diagnostics] = None, **legacy_kwargs) -> List[ArrangementStep]` | **The single step loop.** Signature keeps every current keyword as a defaulted `**legacy_kwargs` passthrough so all existing callers and tests are untouched; when `options` is given, the legacy keywords are ignored and a `ValueError` is raised if both are supplied. |
| `select_step_voicing` | `arranger/steps.py` | `(candidates, previous, options, allowed_tones, root_pc, bass_pc) -> Optional[Voicing]` | **Folds duplicated decision #2 in.** Applies the `bass_cost` partition when `bass_pc` is not `None` (`best <= 2` guard, exactly `wjazzd.py` L1758–1766), then calls `_best_voicing` within the surviving group. This replaces `_arrange_step_with_bass` (L1704–1787, 84 lines) **entirely** — the docstring there explains the "combined, not sequenced" requirement, and this function satisfies it by construction because the partition precedes the engine's own rule. |
| `demote_to_melody_alone` | `arranger/steps.py` | `(voicing, melody_note, name, top_strings, diagnostics) -> Optional[Voicing]` | **Duplicated decision #3** (span ≥ `GRIP_MAX_SPAN["drop2"]` on a target). `arranger.py` L3651–3678 / `wjazzd.py` L2088–2107. |
| `is_repeated_step` | `arranger/steps.py` | `(previous_step: Optional[ArrangementStep], voicing: Voicing, harmony: Tuple) -> bool` | **Duplicated decision #4** (the `repeated` hold). `arranger.py` L3691–3698 / `wjazzd.py` L2114–2121. |
| `is_melody_alone_case` | `arranger/steps.py` | `(texture, role, grips, quality, name) -> bool` | **Duplicated decision #5** — the `NC` step and the walking-bass fill/target that must fall back to melody alone. Collapses the *slightly different* predicates at `arranger.py` L3459 + L3486 and `wjazzd.py` L1982 + L2012 into one table-driven predicate. |
| `promote_fill_to_target` | `arranger/steps.py` | `(prepared, role, slot_grips, requested_grips, texture, ...) -> Tuple[Optional[StepPreparation], str]` | **Duplicated decision #6** (a fill that cannot be filled is re-prepared as a target). `arranger.py` L3573–3585 / `wjazzd.py` L2033–2048, including the walking-bass exclusion at L2041. |
| `add_common_arguments` | `arranger/cli.py` | `(parser: argparse.ArgumentParser) -> None` | The ~25 `add_argument` calls duplicated between `corpus_cli` and `head_cli`. |
| `render_and_write` | `arranger/cli.py` | `(steps, args, *, title, subtitle, beats_per_bar, beat_type, notes, diagnostics) -> int` | The duplicated renderer-dispatch tail: `--tab staff` vs line, then `--html` / `--musicxml` / `--gp5`, each catching `ImportError` as a usage message and returning 1. |


---

