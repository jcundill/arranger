# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

`jazz-arranger` turns a chord progression into playable **jazz guitar chord-melody**.
Given `(melody note, chord quality, chord name)` triples it generates voicings in
several grip families, pins the melody to the soprano string, and chooses among the
candidates with one position-aware cost function. It can also read a written head out
of a MusicXML file and arrange that.

Runtime dependency: `musthe`, and nothing else. Everything else is optional.

## Read this first: where to look

The reasoning behind a subsystem lives in its own document. This file is the map, the
gate and the conventions — not the explanation.

| If you are changing | Read first | Then |
|---|---|---|
| the drop-2 rule, a grip, `GRIP_MAX_SPAN`, `voicing_cost` | [docs/engine.md](docs/engine.md) | `arranger/grip_tables.py`, `arranger/grips.py`, `arranger/cost.py` |
| how a shape is placed on its strings — a family that *searches* versus one that computes a layout, `Placement`, `candidate`, the placement memo (`search_shape` / `_searched_shape` / `place_shape`) | [docs/history/generated-grips.md](docs/history/generated-grips.md) §4 | `arranger/grip_place.py`, `arranger/grips.py`, `tests/test_placement.py` |
| where a **lone note** is fretted — a fill, an `NC` bar, a rescued melody, a span demotion (`get_melody_only_voicings`, `_melody_alone_shape`) | [docs/engine.md](docs/engine.md) | `arranger/grips.py`, `arranger/melody_alone.py`, `arranger/routes.py`, `tests/test_non_chord_tones.py` |
| which chord tones a shape states — `TONE_PRIORITY`, the tone a four-voice shape gives up, the palette a melody with no degree to match is offered, or the order that was not taken | [docs/history/generated-grips.md](docs/history/generated-grips.md) | `arranger/grip_tables.py` (`TONE_PRIORITY`, `stated_tones`), `arranger/grips.py` (`drop2_template_for`, `_drop2_palette`), `tests/test_generated_grips.py`, `tests/support.py` (`WITNESS`) |
| the trailing annotation a step carries, why a shape is thin, or what **must** be explained when a choice is added (`ArrangementStep.palette`, `cost.VOICING_COST_CRITERIA`, `tests/test_explanations.py`) | [docs/engine.md](docs/engine.md) | `arranger/annotation.py`, `arranger/render.py`, `arranger/movement.py` |
| `texture=`, target/fill roles, the walking bass, a hold that moved the melody's string | [docs/engine.md](docs/engine.md) | `arranger/texture.py`, `arranger/routes.py`, `arranger/bass_rules.py`, `arranger/bass_place.py`, `arranger/bass.py`, `arranger/decisions.py` |
| non-chord melody notes, a new chord quality | [docs/engine.md](docs/engine.md#adding-a-new-chord-quality) | `arranger/chords.py` |
| the step loop, `arrange_progression` | [docs/engine.md](docs/engine.md) | `arranger/movement.py`, `arranger/harmonised_route.py`, `arranger/step_prepare.py`, `arranger/resolution.py`, `arranger/slot_plan.py` |
| a step route's arguments - `SlotContext`, one slot's request as a value rather than twenty parameters | [docs/engine.md](docs/engine.md) | `arranger/context.py`, `arranger/movement.py`, `arranger/harmonised_route.py`, `arranger/routes.py` |
| tab staff, HTML, MusicXML, GP5, or the MusicXML importer | [docs/renderers.md](docs/renderers.md) | `tabscore.py`, `tabstaff.py`, `tabxml.py`, `tabgp.py`, `headxml.py` |
| an imported head's **repeats, volta endings or jumps** — why it is longer than the file's measure count, or the `|:` / `:|` / `1.` / `2.` / `D.C.` / `D.S.` / `Coda` / `Fine` the writers draw | [docs/renderers.md](docs/renderers.md) | `headxml.py` (`_parse_barline`, `_parse_direction`, `_parse_sound`, `_expand_play_order`, `expand_repeats`, `BarInstruction`, `BarMarker`, `Head.markers`, `HeadNote.written_bar`); each writer's `markers=` parameter |
| the slot layer: triples to steps, the diminished retry, the slash bass | [docs/engine.md](docs/engine.md) | `arranger/slots.py` |
| the MusicXML **importer's chord timeline**, or a bar the melody skips | [docs/open-issues.md](docs/open-issues.md) item 1 | `headxml.py` (`chord_at`, `chord_slots`, `_merge_chord_slots`, `_generated_beats`, `_bar_resolution`, `_tick_key`) and `grid.py` (`grid_resolutions`, `TICKS_PER_BEAT`) — **built in full**: the default grid generates a chord at each bar's own subdivision, the union takes those positions wherever the tune is *silent*, and §9.2 refuses the ones it is still **holding**. The item carries the candidate and step counts. The fifth `melody_alone_case` kind the item predicted proved **not to be owed** — §9.3 step D already routes a note-less grid position through the comping branch. **Item 6 is the edge of that refusal** — the instant a note *stops* sounding counts as one it still holds, so the grid declines a position the tune has left (`headxml.melody_at`, `melody_state`; the item carries the measurement) |
| an open bug, with its measurement | [docs/open-issues.md](docs/open-issues.md) | — the figures and the behaviour are that document's own business; no test compares them with the prose or is keyed to these items |
| a **note held over a bar line**, when the melody's end is reached, or a pickup bar (`Head.first_bar_implicit`) | [docs/engine.md](docs/engine.md) | `headxml.py` (`melody_at`, `melody_state`, `_merge_chord_slots`), `arranger/grid.py` (`beat_offset`), `tests/test_headxml_timeline.py` |
| which finger frets which string, or a per-finger cost criterion; which strings the right hand's `p-i-m-a` pluck, the gaps between them, and how far the thumb reaches | [docs/history/fingering.md](docs/history/fingering.md) | `arranger/fingers.py` (not inert any more: `bass_place` reads `can_fret` for the four-fret budget — `tests/test_fingers.py` holds the caller set to exactly `{bass_place}`; no per-finger cost yet). Its §4.3 measurement landed a *right-hand* rule first (`grip_tables.thumb_safe_grips`, read by `decisions.resolve_texture_grips`) and then a *left-hand* one (`fingers.can_fret`, read by `bass_place.place_bass`); its **§4.4 finger-skip half is now built**, not recorded: the four `drop24` sets that carried the skip were removed from `GRIP_STRING_SETS` (`grip_tables.finger_skip_count` is the rule and `tests/test_grip_tables.py` holds the tables to it), at a price counted in chords, and the three rejected forms of the same lever are in §4.4 rather than here. Its thumb's-reach half still changes no count (`tests/test_texture.py::TestTheThumbReach` pins the reach), and §4.3's follow-on (should the *selector* leave room for the thumb?) is measured and unbuilt, and its numbers are in §4.3 and [docs/open-issues.md](docs/open-issues.md) item 2 rather than here: that item is where they are re-measured by hand, so a figure repeated in this table would be a second source for one fact. Its **fourth lever — the walk's own pitch — costs the tuple nothing** and is the cheapest of the four; **item 5** of that document is the same §4.3 question asked from the lone-note end, where the walk's register is what leaves the hand's reach |
| `parts=`, which of melody / bass / chord the guitar plays | [docs/engine.md](docs/engine.md) | `arranger/parts.py` (`PART_NAMES`, `parse_parts`, `parts_have_melody`, `parts_has_melody_only`) |
| the harmonisation axes (`parts=`, `texture=`, `harmony=`, `bass=`, `grid=`, the metre) — the four-string arithmetic, and what replaced `voices=` and the grip-family axis | [docs/engine.md](docs/engine.md) | `arranger/parts.py`, `arranger/harmony.py`, `arranger/grid.py`, `arranger/grouping.py`, `arranger/texture.py`, `arranger/bass.py`, `arranger/resolution.py`, `arranger/grips.py` |
| how a **compound metre is felt** — `time_signature=`, `TimeSignature`, `TARGET_BEATS` as felt beats, a walk on the pulses, grid figures in groups, the `n+n+…` refusal, and the direction / beaming / metronome channels a lead sheet states it through | [docs/engine.md](docs/engine.md) | `arranger/grouping.py` (`TimeSignature`, `COMMON_TIME`), `arranger/texture.py`, `arranger/grid.py`, `arranger/bass.py`, `headxml.py` (`Head.grouping`, `Head.grouping_source`, `_score_grouping`, `_beam_partition`, `_grouping_hint`, `_metronome_pulse`), `tests/test_grouping.py`, `tests/test_headxml_arrangement.py` |
| the step/voicing mirrored fields (`step.grip`, `step.bass`), or which selection is melody-only | [docs/engine.md](docs/engine.md), and [docs/history/one-fact.md](docs/history/one-fact.md) for why | `arranger/tuning.py`, `arranger/movement.py` |
| how something was decided, historically — `voices=`, the comping styles, the parts redesign, the generated grips, the fingering notes, the Stage-2 collapse | [docs/history/](docs/history/) | — |
| user-facing behaviour and examples | [README.md](README.md) | — |

**`docs/history/` is not extended.** It is where a completed plan or a retired document goes:
it records why a decision was made and is never revised. If the code has moved on, the history
is still true *about the past* — so read the current documents above first and treat a
contradiction between them as a bug in one of them. A retired document is added once and then
frozen like the rest; it is not a home for an open plan. Eight are retired there:
`reharmonisation-proposals.md`, whose corpus went away, and the six plan documents whose live
halves are now stated in [docs/engine.md](docs/engine.md) — `voices-axis.md`, `one-fact.md`,
`parts.md`, `generated-grips.md`, `comping-styles.md` and `fingering.md`. Each of those six
carries a retirement header saying which half of it is the record and where the live rule went,
which is the one thing to read before quoting one. The eighth, `restructuring.md`, is the
round-2 plan: its live half is the module map below and the budget table in
`tests/test_structure.py`, and its record is what each phase cost.

## The gate

```bash
make check      # lint + typecheck + test, in that order — what CI runs
```

Current measured state: **1372 tests OK (skipped=2)**, pyright **0 errors 0 warnings**,
ruff **0 errors**. If your change moves any of those numbers, that is the signal — not
the absence of an error message. A quiet run is not evidence; a moved count is.

**Six axes, not one.** `texture=` (how many chord tones the part states, `TEXTURE_STYLES`),
`bass=` (the note rules the thumb states, `BASS_RULES` in `bass_rules`), `parts=` (which of melody / bass /
chord the guitar takes, `PART_NAMES`), `harmony=` (which *degrees* the part states when it is
not singing, `HARMONY_STYLES`), `grid=` (*when each part sounds* in the bar, `GRID_STYLES`)
and the metre (`TimeSignature`: its count, denominator and felt grouping, `GROUPING_AUTO`
plus the `N+N+…` algebra in `grouping.py`) are **orthogonal**, and a band setting is a combination
rather than a mode: `bass="none", parts="melody"` is a bassist on the root, a horn on the
melody and the guitar holding the tune alone between them.
Adding an axis means a new vocabulary (`*_STYLES` / `*_POLICIES`, or a note-rule
`*_RULES` table like `bass`'s `BASS_RULE_ROLES`) and a `*_AUTO`
sentinel that is deliberately **not** in the vocabulary, plus a `*_allowed` refusal function
derived from a table rather than listed — never another branch at the call sites. The trap: a loop
variable shadowing a policy parameter (`melody`, in the since-removed `wjazzd.arrange_slots`,
did exactly this, and it only raised when a diminished retry had something to rescue).
`grouping` is the one axis whose vocabulary is an **algebra rather than a list** - any
positive lengths summing to the bar - so it has no `*_STYLES`; `grouping_allowed` derives
the refusal from "the groups partition the bar", and `auto` is the sentinel. Its default
derives threes for a compound metre and one group per beat otherwise, so every simple
metre is byte-identical to before the axis existed.

**`grouping` is the one axis a lead sheet can state for itself**, so `head` reads it from
the score - an `N+N` mark in a direction, the primary beaming, or a metronome pulse, in
that order - and exposes no flag. A progression built without a file declares the whole
metre as `time_signature=TimeSignature(beats_per_bar, beat_type, grouping)`; omitting it
means `COMMON_TIME` (4/4), and an explicit grouping is the caller's override when a score
does say. A conventional simple metre (2/4, 3/4, 4/4, 2/2) ignores its
beaming: a notation program's beam pairs restate the beat rather than group it.

**`harmony=` was added by following that rule, and the three traps below are what it cost.**
`HARMONY_STYLES` + `HARMONY_POLICIES` + `HARMONY_AUTO` + `harmony_allowed` in
`harmony.py`, resolved once per arrangement next to `_resolve_melody`, and inert twice
over: `auto` resolves to the shipped `guide`, and the axis is read only by the comping
route, so it cannot touch a melody-bearing arrangement. Three things to know before adding
a fifth:

- **A degree family is not an arity.** `guide` and `shell_root` are two different claims
  that both need three notes available, so `harmony_allowed` refuses on **how many notes
  were asked for** and not on a table of combinations. Deriving the rule is what kept it
  to two entries instead of a list to extend.
- **A family that "contains" a degree is not that family.** The first `shell_root`
  implementation asked whether *some* root or 5th was sounding, and on an `Ebmaj` whose
  guide tones are D and G the plain shape `D G Bb` already contains the 5th — so the new
  family was silently a synonym for `guide` and every other test still passed. The check
  is on the **lowest** note. `test_shell_root_is_not_merely_a_shape_that_contains_a_bass_degree`
  exists only because of that, and its docstring says so.
- **The shell chord-melody is not on this axis.** Which *grip* a chord-melody is voiced
  with is the selector's business - the melody is pinned to the soprano string and the
  family comes from `GRIP_PREFERENCE`, the caller's grip *order* having gone with the
  family axis. `harmony=guide` is the melody-free part, so `harmony=` is inert on any
  arrangement the guitar sings and cannot reach that route at all - see the `harmony=`
  section of [docs/engine.md](docs/engine.md). Option (A) in the retired
  [docs/history/comping-styles.md](docs/history/comping-styles.md) §6 Q2 - routing
  `harmony=guide` with a melody through the shell grip - would have given the axis one
  spelling for both routes, and it is **moot now**: the axis that expresses "the tune and
  nothing else" is `parts=melody`, which is what the `--voices` rename became. A
  **comping-content** axis inherits the constraint: scope it to the comping route, and do
  not let it reach the melody-bearing one by accident. The metre is the counter-example
  and is deliberately not one: `TimeSignature` is a metre fact rather than a choice about
  the chord part, so the metric layer, the walk and the grid read it on **both** routes.

**`make check` is what CI runs**, in one job (`.github/workflows/ci.yml`, Python
3.11–3.14, with the `xml` and `gp` extras so the optional-extra tests are not silently
skipped). **There is no second job and nothing a clean clone cannot run** — that used
to need stating here and in the workflow header, because the 42 MB Weimar Jazz
Database was gitignored and 85 of the suite's tests skipped on every fresh checkout.
The database **and its loader** are gone, so a green check means the whole suite ran, and
the only guards left are the optional-extra ones this job installs against. (The 42 MB
`wjazzd.db` file is gitignored, so a working copy may still have it; nothing reads it.)

**`make check` runs one interpreter, and the matrix runs four.** It is the 3.14 dev
one. A construct that is version-dependent passes here and fails on the 3.11 job —
see trap 11, where a two-argument `Enum(...)` call was a value lookup on 3.12+ and
class definition on 3.11.

Individually:

```bash
## Repository layout

```
arranger/
├── arranger/            # the engine - a package, not a module
│   ├── __init__.py      #   facade: re-exports, __version__, main()
│   ├── __main__.py      #   `python -m arranger`
│   ├── tuning.py        #   STANDARD_TUNING, Voicing, ArrangementStep
│   ├── context.py       #   one slot's request, shared by the two step routes
│   ├── fingers.py       #   which finger holds which fret; read by bass_place for the fret budget
│   ├── chords.py        #   ChordParser, non-chord-tone routing
│   ├── grip_tables.py   #   the grip tables and the questions asked of them
│   ├── grip_place.py    #   where a shape is placed on its strings, and the memo
│   ├── grips.py         #   the builders and the candidate generators
│   ├── cost.py          #   voicing_cost - the library's central invariant
│   ├── annotation.py    #   the trailing explanation, composed from the step's fields
│   ├── parts.py         #   which of melody / bass / chord the guitar takes
│   ├── harmony.py       #   which degrees the chord part states
│   ├── grouping.py      #   TimeSignature and the metre's grouping algebra
│   ├── grid.py          #   when each part sounds
│   ├── texture.py       #   how many notes the chord part states; metric roles
│   ├── bass_rules.py    #   the bass vocabulary, capacities and refusals
│   ├── bass_place.py    #   the thumb's octave and string: the cost and `place_bass`
│   ├── bass.py          #   the walking-bass thumb line
│   ├── bass_merge.py    #   merges the walk into a chosen step; the next resolution melody
│   ├── options.py       #   ArrangeOptions - the knobs as one value
│   ├── resolution.py    #   what the caller asked for, resolved once
│   ├── decisions.py     #   decisions both step loops share
│   ├── melody_alone.py  #   where a lone note is fretted: the tune alone, chord or not
│   ├── routes.py        #   the route handlers: rest, fill, NC and the comping route
│   ├── slot_plan.py     #   one slot's plan: `slot_state` and the value it returns
│   ├── step_prepare.py  #   one slot's candidates: prepare_step and its preparation
│   ├── harmonised_route.py #  the melody-bearing route: prepare, select, demote, emit
│   ├── movement.py      #   the step loop: _route_slot, _loop_slots, arrange_progression
│   ├── steps.py         #   VoiceLeadingEngine - the published facade
│   ├── slots.py         #   the slot layer: triples to steps, the one pre-pass
│   ├── render.py        #   format_progression and per-step rendering
│   └── cli.py           #   the head CLI's flags and output dispatch
├── tabscore.py          # score placement shared by the MusicXML and GP5 writers
├── tabstaff.py          # whole-progression staff renderers (ASCII + HTML)
├── tabxml.py            # MusicXML export (optional extra: music21)
├── tabgp.py             # Guitar Pro 5 export (optional extra: PyGuitarPro)
├── headxml.py           # MusicXML import: a melody + chord symbols
├── grip_chart.py        # generates common_grips.md from the engine's tables
├── tests/               # unittest, one file per concern, + support.py
│   └── data/            # committed MusicXML fixtures (music21, MuseScore, ours)
├── docs/                # the documents the routing table above points at
├── pyproject.toml       # PEP 621 + PEP 639 metadata (setuptools backend)
├── Makefile             # the gate, above
├── .github/workflows/   # CI: one job, make check on 3.11-3.14
├── AGENTS.md            # this file
├── README.md            # user-facing overview
└── .venv/               # local virtualenv (not committed)
```

There is **no** `setup.py`, `setup.cfg` or `requirements.txt`. CI *is* configured
(`.github/workflows/ci.yml`, added in Phase 9) and it runs exactly `make check`.
Packaging metadata lives solely in `pyproject.toml`, which reads the version
dynamically from `arranger.__version__` — that is the single source of truth.

### The engine is a package, and the order is enforced

The engine was one 4290-line module until Phase 5 of the package refactor. It is
now a package of focused modules in a strict dependency order:

```
tuning -> fingers -> chords -> grip_tables -> grip_place -> grips -> cost -> annotation -> parts -> harmony
                             -> grouping -> grid -> texture -> bass_rules -> bass_place -> bass -> bass_merge
                             -> options -> resolution
                                                                    |
                       melody_alone -> routes -> slot_plan -> step_prepare -> harmonised_route
                                                                                    |
                                 movement -> steps -> slots -> render -> cli
```

`fingers` — which finger holds which fret — hangs off `tuning` alone, so it is drawn
separately rather than as a branch of that chain. It is **not inert**: `bass_place` reads
`fingers.can_fret` for the four-fret budget of the playability invariants below, which is
an *upward* import and so legal. `docs/history/fingering.md` §5 step 3 — a per-finger cost
criterion — is still open.

```
tuning -> fingers   (step 1 of docs/history/fingering.md; `bass_place` reads can_fret for §4.3)
```

A module may import only what is *below* it, and
**`tests/test_package_dag.py` asserts that from the AST** — so the layering cannot
erode one "temporary" import at a time. Read its `ORDER` list before adding a module.
`ALLOWED_EDGES` in that file is the escape hatch: each entry there must justify itself
in a comment. It is **empty** now, and an entry that no longer permits an import fails,
so permission cannot outlive the code it was granted for.

The same discipline has two other checks. **`tests/test_structure.py`** fails a module
that reaches a sibling's `_`-prefixed name either by importing it or through a module
alias (`alias._helper`), and its `ALLOWED_PRIVATE_ATTRIBUTES` list is empty too -
`render` importing `annotation.step_annotation` rather than `_step_annotation` is what
kept it so. **`tests/test_front_end_dag.py`** holds the top-level modules to the same
rule, with the deliberate edges named: `tabstaff`'s re-exports of the two writers, and
each writer's use of `tabscore` for placement. `FRONT_ENDS` in `tests/support.py` is
the one list the budget table and that DAG test both read.

Three consequences worth knowing:

- **Adding a module inside `arranger/` needs no `pyproject.toml` change** — the
  package is already listed. A new *top-level* module needs a `py-modules` entry, or a
## Requirements and licence

- Python **3.11+**. The local dev virtualenv runs 3.14. 3.10 was dropped because
  `tomllib` is 3.11+.
- **One** runtime dependency: [musthe](https://pypi.org/project/musthe/).
- **Two** optional extras, each behind a lazy import so the library works without
  either: `xml` → [music21](https://pypi.org/project/music21/) (`tabxml.py`), and
  `gp` → [PyGuitarPro](https://pypi.org/project/PyGuitarPro/) (`tabgp.py`). The two
  are independent: a run asking for a GP5 file must not require music21.
- **Dev-only**, never reachable from a plain install: `pyright` and `ruff`
  (`pip install -e '.[dev]'`).

Tests are stdlib `unittest` — there is no `pytest` dependency — and the database- and
extra-dependent test modules are `skipUnless`-guarded, so the suite passes on a fresh
clone with neither.

**Licence: MIT** (see `LICENSE`), declared as PEP 639 metadata in `pyproject.toml` —
`license = "MIT"` plus `license-files = ["LICENSE"]` — which is why
`build-system.requires` is `setuptools>=77`. Do not also add the
`License :: OSI Approved :: MIT License` classifier: it is deprecated once the SPDX
expression is present, and adding both makes setuptools warn.

The permissive licence is load-bearing, and one dependency is why it has to be.
PyGuitarPro is **LGPL-3.0**, so keeping this project clearly *not* a combined work of
it matters. Two things do that, and both must stay true: it is a **runtime**
dependency of neither the package nor the test suite, and `tabgp` imports it
**lazily**. Copying PyGuitarPro code into the tree would change the analysis — don't.

## Setup

A virtualenv already exists at `.venv/`. Prefer invoking its interpreter directly
(`.venv/bin/python`) so you do not depend on shell activation. Recreate with:

```bash
python3 -m venv .venv
.venv/bin/pip install musthe
.venv/bin/pip install pyright ruff     # dev-only type checker and linter
```

No editable install is required — the tests import `arranger` from the repository
root — but `pip install -e .` provides the `jazz-arranger` console script.

Note the name split: the **distribution** is `jazz-arranger`, because the PyPI name
`arranger` is taken by an unrelated project, while the **import** name stays
`arranger`.

### If the interpreter hangs at startup

`Fatal Python error: init_import_site: Failed to import the site module` means the
editable-install finder in `site-packages` is broken. The symptom is a **hang, not an
error**: the traceback only appears once something interrupts it, so the shell looks
stuck rather than broken.

The cause seen here was a stale finder for a long-superseded early version, left
over when the project was still pre-release. It is regenerated on every
`pip install -e .`, so the stale copy is what a version bump leaves behind when the
reinstall is skipped.

```bash
.venv/bin/pip install -e . --no-deps
```

To confirm the symptom is this and not something else, run
`./.venv/bin/python -S -c 'print(1)'`: the `-S` skips site processing, so it succeeds
where the normal invocation hangs.

## Build and run

There is no build step for local development.

## Conventions

- `from __future__ import annotations` at the top of every module; use `typing`
  aliases (`List`, `Optional`, `Tuple`, `Dict`, `Any`) consistently. This is house
  style, which is why `ruff`'s `UP*` rules are off — see `pyproject.toml`.
- Dataclasses for value objects; `@staticmethod`/`@classmethod` for stateless logic.
- Preserve the dict-style `__getitem__` shims on `Voicing` and `ArrangementStep`.
- Docstrings on public classes and methods. Comments explain *music-theory intent* —
  which chord tone is in the top voice, and why a shape is unreachable — not syntax.
- **Rendering is pure.** Every renderer returns a string (or list of them) and prints
  nothing. Only `main()` and the demo write to stdout.
- **The library never prints**, and it has no warning channel either. What the engine
  used to report through a `Diagnostics` collector is now either **on the tab line** -
  read off the step's own fields and phrased by a `render` `*_clause` - or a
  `ValueError` from the axis that could not honour the request. Adding a `print()` to
  the engine is a regression, and `tests/test_explanations.py` is what keeps a choice
  from going *unexplained* rather than merely unprinted.
- **Do not add a third-party dependency** without explicit approval. `musthe` is the
  only runtime one; that is load-bearing for the LGPL reasoning above.

### Docstrings describe the present, not the past

A docstring states what a thing **is** and what a caller or an editor must know. It is
not a changelog, and it is not where the reasoning lives. Three kinds of text compete
for that space, and only the first belongs in the source:

- **The contract, and any do-not-change constraint** — keep it, in the present tense.
  "`requested` narrows the palette and must never widen it"; "do not reorder this
  tuple". The warning is what stops the next editor undoing a deliberate choice, and
  the traps below are the record of what that costs when it is missing.
- **The story of how it got here** — delete it. "This was two functions", "it used to
  be a classmethod", "Phase 5 moved this", "the database is gone", a former module
  name, a forward-looking "for now". Narrative of this kind is written against a tree
  that stops existing, and an agent that reads it acts on a fact that is no longer
  true. The reason it is *always* the wrong place is that it has no test: nothing fails
  when it goes stale, so it rots silently while the gate stays green.
- **A measurement, and its number** — move it to the document that already holds it:
  [docs/open-issues.md](docs/open-issues.md) for a diagnosed bug, the relevant
  `docs/*.md` for anything else, [docs/history/](docs/history/) for a completed plan. A
  count in a docstring is the fastest-rotting string in the repository and is stored
  where it is least likely to be re-measured. Leave a one-line pointer instead.

A module docstring is one to three sentences: what the module owns, and where it sits
in the dependency order.

### Playability invariants

Every generated voicing must satisfy all of these. They are asserted per-shape in
`tests/test_grips.py`, and they are what makes a tab playable rather than merely
correct:

- the sounding strings are exactly one `supported_string_sets()` entry — two to four
  strings, every other muted (`-1`). **Four is the right hand**: the plucks are thumb,
  index, middle and ring (`p-i-m-a`), so a step must never sound five, which is why the
  bass note a thumb line merges into a step goes *outside* the upper shape's set rather
  than onto it, and why a target under a thumb may sound at most three strings
  (`grips.thumb_safe_grips`);
- the melody is on that entry's soprano string, and is the highest sounding note;
- `0 <= fret <= 18` and `fret_span() <= GRIP_MAX_SPAN[grip]` (5, or 4 for a duo).
  The span is checked on the frets actually placed, **not** as "within N of the
  soprano": those differ, and the second admits a span of ten;
- **four fingers, four frets** — and unlike the four above, this one is stated over a
  *step* rather than a shape, because that is the only level at which it can fail. A
  generated grip sounds at most four strings and so spans at most four frets; a
  `bass_only` step, though, merges the thumb into a shape the hand is still **holding**,
  where its fret can be a fifth. `fingers.can_fret` is the check and `bass_place.place_bass`
  is its one caller: a candidate needing five frets is refused, so the step keeps its
  upper voicing and the omission is reported, exactly as when no string is free.
  Measured over the committed heads: **1** such step before the fix, **0** after.
  It is the smaller twin of the bullet above: the same
  trap, the rule asserted on the part of the whole that happened to be checked;
- every sounding pitch is a chord tone, except the melody itself when it is not one.
  Every shape the rule builds is pure — measured over every chord tone of all 29
  qualities — so what a non-chord melody carries is the caller's own note rather than
  a shape's, and the selector's first cost criterion ranks pure candidates first.

Two more that follow from the neck window, which is a **preference and never a
filter**: a step with no voicing inside frets 2–13 is still played, just outside it,
because losing a chord of the tune is worse than being a fret out of position. And a
melody whose only position sits above `HIGH_FRET_LIMIT` is voiced an octave down, so
`step.melody` may be an octave below the written note — the written pitch stays in
`step.original_melody`.

### Every choice about a voiced note is explained by the line that prints it

**A step has to account for what it did, and for the shape it did it with.** This is an
invariant of the artifact rather than a style preference: the one-line tab is what a user
reads, so a choice it cannot see is a choice the library made silently. It is also the
constraint on growth — **a new axis, grip, substitution or fallback arrives with its
explanation**, because the alternative is a knob whose effect is invisible.

The mechanism is that the explanation is **recorded on the step and composed by the
renderer**, never re-derived at a call site:

- a choice *among shapes* lives on `ArrangementStep.palette` (the most voices the palette
  offered, the best fuller candidate, the `cost.voicing_cost` element that ranked it lower,
  `inside_window`) and is phrased by `annotation._shape_clause` / `_window_clause`;
- a fact that **corrects a column** — the octave a melody was moved to, the chord a
  substitution actually states, a written slash bass no shape sounds — is a *derived clause*
  (`_transposition_clause`, `_substitution_clause`, `_slash_bass_clause`), so it reaches every
  route that can suffer it, a hold included;
- a **choice the shape embodies** that no field records is derived from the step's own fields
  too, but is suppressed on a hold like the `palette` clauses, because it accounts for the
  shape rather than for a column: `_omission_clause` names the chord tone a four-voice shape
  gives up (`TONE_PRIORITY`'s tail), and `_sounding_clause` names the voices a shape with two
  or more of them sounds, each with the degree it states. Derived rather than recorded because
  the whole fact — the
  routed chord's tones against the pitches sounding — is already on the step, and a field
  beside it would be a second source for one fact;
- a **route that chose no shape** states its own (`_comping_clause` names the voices it
  states, each by note and degree; "the tune is silent here"; "the guitar rests here"; "the
  shape above is held"; "the most a fill's palette offers" — the last is the difference
  between *the library ran out* and *the caller asked for fewer*).

`tests/test_explanations.py` is the standing check: a table of (decision, when this step is
one of those, what the line must say), swept over every committed head and working from the
step's **fields** rather than from the wording, so it cannot be satisfied by phrasing.
**Adding a decision means adding its witness to that table in the same commit**, and a new
`*_clause` helper fails a companion test until it is registered there — the enumeration is
read off the module, so a clause cannot be added and forgotten.

Two exemptions are deliberate and are named in that file rather than left implicit, because
a rule with unnamed exceptions is a rule the next editor deletes: a **hold** does not restate
the shape count (it was explained where the shape was chosen) though it does restate what
corrects a column; and the **slash bass** is pinned by its own test, because a witness that
recomputed whether the bass sounds would be the clause agreeing with itself. The third —
"a melody-alone shape with no palette" — went with the reason for it: a lone note is now
chosen from a palette of single-note shapes (one position per eligible string) by the same
cost tuple a chord goes through, so its fret **is** a choice and the window clause has a
measured `Palette.inside_window` to state rather than a defaulted one to guess with.

What the invariant does **not** cover, and should not pretend to: a *phrase* (nothing groups
steps) and the **fingerings** (`fingers.py` assigns them and no renderer prints them — a barre is
visible in the tab). Positions the guitar *declines* used to be the third exemption — dropped
from the tab with only a warning to report them — and are not any more: the four
routes that dropped them emit a rest step whose `silence` names the reason, and
`annotation._silence_clause` phrases it, which is why it carries a witness in the table above.


### The cost tuple is not being refactored

`voicing_cost`'s 7-element tuple is the library's central invariant, asserted
positionally in `tests/test_grip_selection.py::TestVoicingCost`. Moving the code is safe;
**reordering it is a musical decision, not a refactor.** Span is the one criterion
promoted above position, and that was measured rather than guessed — the reasoning
and the table of what it cost are in [docs/engine.md](docs/engine.md). Changing what
a criterion *reports* is the same decision: spans 0 and 1 are bucketed to one value
at the span index (a one-fret reach does not outrank keeping the hand in place),
measured at one moved pin, and the `0/1/2` bucket was measured at 13 and rejected.

**Deleting one is that decision too.** The tuple used to carry an eighth element, a rank
over grip families. It went because it was the *same rule* as the order candidates are
generated in, written twice: they agreed, so neither was individually necessary. With the
families generated in the same order, deleting the criterion changed **0 of 799**
committed-head steps — tabs *and* grip labels — and **0 of 120** single-step sweeps; and
reversing `GRIP_PREFERENCE` with the rank left in changed nothing either, at 0/799 and
0/120. What the number does not say is the reason it is the right shape: no criterion
names a grip family because a family is not a property of a shape. Two families can
generate the very same tab, so at that depth the tuple would be choosing a *name* rather
than a sound; and a four-note drop-2 never reaches a tie with a shell to lose, because
criterion 2 separates them on note count. A tie now falls to generation order —
`top_strings` first, then `GRIP_PREFERENCE` within one string - and with the grip-family
axis deleted that order is the engine's rather than a caller's, so "most preferred first" is
a property of the table rather than of a request.
The two live cases that order decides are in [docs/engine.md](docs/engine.md)
§"Known limitations".

Likewise the 54 hardcoded tab strings in the tests stay: they are the acceptance
gate, and a snapshot mechanism would let a regression pass by regenerating itself.

## Contributing workflow

1. Read [docs/engine.md](docs/engine.md) or [docs/renderers.md](docs/renderers.md) —
   whichever the routing table sends you to — and the relevant test file.
2. Make the smallest change that satisfies the requirement.
3. Add or update tests in `tests/`, in the existing `unittest` style: one class per
   concern, descriptive `test_*` names, docstrings stating what is verified.
4. Run `make check` from the repo root. It must report `OK`.
5. Run `make demo` when you touched voicing or voice-leading logic, and read the
   printed tabs.
6. Commit each logical change separately. **Never `git push`** — this branch is the
   user's to push.
7. **When the context is running out, stop and write the state down.** A long session
   banks what it has done, what is left, and **why each decision was made**, in a scratch
   handoff outside the tree, and then says that compaction would help rather than pressing
   on. The user is helping the task, so asking costs nothing; a session running on a
   thinning context re-litigates settled decisions and reverts deliberate ones, which is
   what every trap below is made of.
## Adding a new chord quality

1. Add the quality's tones to `TONE_PRIORITY`, most defining first. **That row is the
   drop-2 rule** — `drop2_template_for` builds each shape from it and `_drop2_palette` is
   that rule read at every degree — so there is no list of interval numbers to write down.
   Its first two entries are the quality's `SHELL_DEGREES` pair, and the tail **ranks which
   tone a four-voice shape gives up** when the chord has more tones than voices — the nearer
   the end of the row, the sooner it goes, and the ranking is per-quality rather than one
   global order (`9` gives up its root where `maj7` gives up its natural 5th). An altered 5th
   is not a 5th: it ranks above the root. A name-given extension (the 9th of a `9`, the 13th
   of a `13`) is never the tone dropped. The shape itself is the close-position stack under
   the melody with its second voice lowered an octave, and a triad's fourth voice is the
   root doubled an octave below the stack.
2. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`. This is also
   what `drop3`, `closed`, `shell` and `duo` build themselves from, so it is required
   for the new grips to reach the quality at all. If the quality should also get a
   shell, add it to `SHELL_DEGREES` — the drop-2 rule and the derived grips work
   without one.
   `tests/test_generated_grips.py` holds the rule to the hand-written 119
   (`tests/support.py::WITNESS`), so **a new quality needs no table row of its own**; the
   measurements behind it are in [docs/history/generated-grips.md](docs/history/generated-grips.md).
   A quality with a priority row
   and a tone set needs nothing else, and one with a tone set but no row is offered no
   drop-2 shapes at all rather than a guess.
3. Add aliases to `ChordParser.QUALITY_ALIASES`.
4. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
5. **If a MusicXML file should be able to spell it**, add the matching
   `kind-value` to `MUSICXML_KIND_QUALITIES` in `headxml.py`, and any `<degree>`
   alteration that reaches it to `_DEGREE_REFINEMENTS`. The same rule applies: an
   absent kind resolves to `None` and is counted in `Head.unmapped`, so a new
   quality MusicXML cannot spell stays silent until this step is done. Note the
   table is keyed on the *library* quality, so a `kind` that only a `<degree>`
   reaches (a 7b5, say) needs a degree entry rather than a kind entry.
6. Add tests to `tests/test_voicings.py` for the drop-2 fingerings and to
   `tests/test_grips.py` for the other grips: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`, and the sounding strings
   a member of `supported_string_sets()`.
   `tests/test_voicings.py::TestQualityTableInvariants` checks the priority row is a
   permutation of the tone set, and `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route.
   `tests/test_headxml.py::TestChordParsing::test_every_kind_the_table_names_is_voiceable`
   is the same assertion for `MUSICXML_KIND_QUALITIES`.


## Traps

Each of these cost real time, or nearly shipped a defect.

1. **A gate that enumerates its inputs by hand silently skips whatever was added
   last.** The Makefile named each source file in three places, so `decisions.py` and
   `options.py` were unlinted and untypechecked until noticed.
   Lint and format now share one `MODULES` list; the package is named as a directory,
   so an engine module cannot be forgotten. A new *top-level* module is still a
   two-line change, in `MODULES` and in `typecheck`.

2. **`pyright` needs `--pythonpath`.** Run bare it reported **32 errors**, all
   `Import "musthe"/"music21"/"guitarpro" could not be resolved`, for packages that
   were installed and importing fine. A checker that cannot see the venv reports
   import failures that look exactly like type failures. `make typecheck` pins it.

3. **Do not run `ruff format` across the tree.** It rewrote 24 files and inflated
   `SHELL_DEGREES` from 10 lines to 31, one pair per line. Those tables are aligned
   so they can be scanned; one-per-line is 3× the space for the same information, in a
   refactor whose purpose is readability. `make format` is for a targeted file and is
   **not** part of `make check`.

4. **`ruff B010` and pyright can be mutually unsatisfiable.** Assigning a classmethod
   to satisfy pyright trips `B010`, which wants `setattr`; `setattr` trips pyright.
   Don't add a suppression — look for a seam worth extracting instead. That is how
   `wjazzd._corpus_options` came to exist.

5. **A test's premise can be invalidated by the refactor it exists to protect.** When
   a test fails because the structure it describes is gone, **invert the assertion —
   do not delete the test.** `test_both_loops_call_the_shared_decisions` asserted both
   step loops call each decision; Phase 4 made that false by design, and it now
   asserts the opposite (the engine calls them, and `slots` must contain none of it).

6. **When consolidating two branches, check whether their *outputs* differ before
   unifying their predicates.** `melody_alone_case` nearly shipped as a `bool`, and
   unifying the `NC` branch with the walking-bass branch on it would have annotated a
   step *"(no chord - melody alone)"* that claims to have a chord. The predicate
   returns a **kind** (`none` / `texture` / `nc`) for exactly this reason.

7. **A large mechanical move must copy text, not retype it.** Phase 5 moved 4290
   lines into the package by slicing the original *by line number*, so a docstring,
   a fret number or a comment provably cannot change in the move. Generate into a
   script you keep until the suite is green — a half-applied regeneration over a good
   tree is much harder to unpick than a wrong line is to find.

8. **A stale "before" measurement will invent differences that are not there.** When
   proving a refactor changed nothing, capture the fingerprint from the commit you
   think it is, not from a file that has been sitting in the tree since
   (`git worktree add /tmp/pre HEAD`). The capture itself is a throwaway script under
   `/tmp`, kept out of the repository: `tests/test_step_loop_equivalence.py` is the
   standing check, and a measurement that only matters during one refactor has no
   business outliving it. (This trap used to have a corpus half — the gitignored
   database had to be copied across or the capture came back empty — and that half
   retired with the loader.)

9. **A count without a denominator is not a metre.** 2/2 and 2/4 are both two beats
   to the bar, and both readings of `4 / beat_type` agree in 4/4 — so the whole suite
   passed while the file was unusable for every other metre. That is why `Head`
   carries `beat_type` and it is plumbed to the file headers, and why the check that
   catches it sums each measure's durations rather than counting measures. **The
   importer then shipped the bug that fix was about**: `beat_type` was read and
   plumbed to the four *renderers*, while the importer's own onset conversion still
   used the count — so every note of the one committed 3/4 head was placed 25% early,
   its exported bars came out short, and `--musicxml` scaled every onset by another
   0.75 per round trip. Most of the committed heads are 4/4 or 2/2, where the two spellings
   are the same number, and the only test that read the odd one out derived its
   expectation from those same beats. Measured and fixed; the denominator now reaches
   the engine's arithmetic too (`headxml._beat_from_onset`, `bass._melody_timeline`).

10. **An omitted attribute is not an identity — and a default that is wrong is
    silent.** The exporter wrote no `<key>`, so every score left the library was in C
   major whatever it was in; the importer read `<time>` and not `<key>`, so the head
   arrived with nothing to write. Nothing errored, because a missing key signature is
   *legal* and means C major. It cost 201 accidentals on a 32-bar Eb head against 27.
   Two things made it cost that much rather than 155, and both were found by
   measuring rather than reading:
   - **`<harmony>` symbols mark notes through a channel the document does not use.**
     `writeAsChord = False` means the symbol's pitches are never written, yet they
     stay in the stream and music21 still counts them when deciding which notes need
     an `<accidental>`: 139 against 27 for the same music. Cleared in `_chord_symbol`.
   - **Never grep a document with a single-line pattern for a multi-line element.**
     `<key>.*?</key>` without `re.S` reports *no key* on a document that has one,
     which is exactly the shape of the bug being chased. That cost an hour of
     "music21 does not emit `<key>`" — a conclusion drawn from a regex that could not
     match. `re.findall(pattern, text, re.S)`, always.

11. **The dev interpreter is not the matrix.** `gp.KeySignature(-3, 0)` looks like a
    value lookup and is one on Python 3.12+, where `EnumType.__call__` reads a tuple in
    the `names` position as member values to match. On **3.11** the same call is the
    *functional* enum API — "define a new class" — and raises `TypeError: <enum 0>
    cannot extend <enum 'KeySignature'>` before any lookup happens. It passed on the
    3.14 dev box and on every 3.12+ runner, and failed only on the 3.11 CI job, on the
    first test that asked for a key. `_key_signature` now scans the members and compares
    `.value`, which is the same lookup written out and behaves identically everywhere.
    The general form: **a two-argument `Enum(...)` is not a value lookup, it is class
    definition**, and `make check` cannot catch this because it runs one version.
    Anything version-sensitive has to be exercised on each version CI runs.
12. **A new guard clause is not a new route — and moving one can break the case it
    did not name.** Adding `grid=` meant asking `decisions.melody_alone_case` what an
    **off-grid** slot should do, and the answer differs by route: with the guitar
    singing the note sounds alone, with it comping the guitar is *silent*. That is a
    fourth *kind*, `MELODY_ALONE_REST`, not a flag — a bool could not express both,
    which is trap 6's shape arriving again from a new direction.

    The ordering of that function's three guards is what cost the time — 12 tests over
    two attempts, because each ordering fixes one route and breaks the other:

    - placing the grid test **after** the `melody_voiced` guard makes `grid=`
      **silently inert on the comping route**: measured, all four patterns returned
      80/80 comps, byte-identical to the default, with no warning anywhere;
    - hoisting the `NO_CHORD` test **above** that guard lets an `NC` bar reach the
      comping route, where it must be *dropped with a warning*; it instead survived as
      a step — `['Dm7', 'NC', 'A7']` where it had been `['Dm7', 'A7']`;
    - fixing that by returning `NONE` for `NC` everywhere breaks the **singing**
      route, which needs `MELODY_ALONE_NO_CHORD`; the note then found no voicing and
      vanished, taking **11 tests across four files**, every one of them `NC`.

    The general form: **before reordering a decision function's guards, ask what each
    guard is load-bearing *for*, and then check the two routes separately.** Both
    routes build different steps from one function — which is the whole reason it
    returns a kind — so an ordering right for one is not thereby right for the other.
    An `NC` bar is also what proves "off the grid" is not universal: it has *no chord
    to place*, so "silent here" and "no chord here" are different claims, and only the
    first is a rest.
13. **An invariant asserted on a voicing says nothing about a step the engine builds
    *after* the check.** The merge is deliberately after selection — "the bass is written
    into the fret vector only once `best_voicing` has returned, so it cannot enter the
    cost tuple by construction" — and every `supported_string_sets()` assertion in the
    suite is on a generated *voicing*. So a four-note target plus a thumb note was five
    strings, four fingers be damned, on **281 steps** of the committed heads under
    `--texture targets --bass-style root,5th,approach,nearest|root`, and no test could see it.
    `tests/test_walking_bass.py::TestTheInvariant` *had* amended the rule for a
    bass-carrying step, and amended it correctly for the texture it was written for (a
    `walking_bass` target is a shell, so three strings plus a thumb is four) — the
    amendment was right and the palette was wrong. **The general form: when a rule is
    stated over a part of a whole, ask which producer can make the other part larger than
    the rule assumed, and assert the rule on the whole.** A count is the way to do it: the
    step count that catches this is "strings plucked at once", not "strings in the shape".

14. **An option that takes a *list* spells it the way the flags around it do — and
    `nargs` is not that spelling.** `--grips` carried `nargs="+"` with
    `choices=GRIP_PREFERENCE` while `--voices`, in the same parser, took a
    comma-separated string — so `--grips closed,shell` was refused
    (`invalid choice: 'closed,shell'`) *by a flag whose own run header prints the request
    back as `grips: closed, shell`*: the line a reader copies was the one spelling that
    did not work. The second half is silent until it is tried. `nargs="+"` consumes the
    positional written after it, so `head --grips shell FILE` fed the **filename** to
    `--grips` and reported `invalid choice: 'tests/data/...'` — the flag worked only
    after the file. Every list-valued option is one comma-separated string now, parsed by
    the module that owns the vocabulary - `parts.parse_parts` for `--parts` - so
    `head --parts melody,chord FILE` and `head FILE --parts melody,chord` are one run.
    **Two things to carry forward: a list-valued option is one string the module that
    owns the vocabulary parses, never `nargs`; and a parser's own output is
    documentation — if the run header prints a spelling, that spelling has to be
    accepted** (the round trip is asserted). Note a *selection* is canonicalised and a
    *sequence* is not: `parse_parts` re-sorts into `PART_NAMES` order because a parts
    selection is a set, and the grip order that must not be was a spelling of the deleted
    family axis.

15. **A parameter removed from the middle of a signature silently shifts every
    positional call.** `arrange_progression` took `diagnostics` at position 12 and
    `steps.arrange_progression` forwarded to it positionally, ending at `options` -
    so deleting the parameter left `options` landing in `grid`, and every bare
    `arrange_progression(prog)` call died three frames later in
    `parse_grid(None).strip()`. **266 test errors from one line**, and the traceback
    named a function that had not been touched. The same edit then deleted three
    *whole argument lines* (`role, texture, texture_grips, grips, diagnostics,` and two
    `role=role, weight=weight, diagnostics=diagnostics,`) because the strip matched
    them as text rather than as syntax - trap 7's shape arriving from a new direction.

    The general form: **a mechanical parameter removal is an AST edit, not a text
    edit**, and a facade forwarding positionally is what turns it from a type error
    into a silent mis-bind. Two things follow. Name every argument at a facade
    boundary - `steps.arrange_progression` now spells all fifteen and passes
    `options=options` as the only keyword. And when a strip script reports "lines
    removed", read the `git diff`'s removed lines rather than counting them: all four
    casualties above were visible there before any test ran.

16. **A number a document states has no test, so it rots where it is least likely to be
    re-measured.** `docs/open-issues.md` states each item **with its measurement** — that is what
    makes an item an issue rather than a complaint — and three separate commits moved those
    measurements without touching a word of the prose beside them: deleting the `Diagnostics`
    collector left six documents describing a warning that phrases a choice, when the phrasing
    had moved onto the tab line; playing the repeats (`6cdcbaa`) lengthened every head, so item
    1's "57 steps" was **87** and the `comps+freddie` triple moved with it; and `bass_refused`
    counting every refused thumb where the old warning counted one call site took item 2 from
    **39** to **161**. `make check` was green through all of it, because the doc checker
    that existed then compared only a document's *version*, *module count* and *links* — and
    nothing checked a count.

    Two things follow, though neither is enforced by the gate now. **A figure repeated in
    two documents is a second source for one fact** — AGENTS.md's own `step.bass` rule — so the
    routing rows here *point* at the document that owns a number instead of restating it; the four
    counts that lived in three places at once are what made this rot invisible. And **a stated
    figure gets a recipe**: `docs/open-issues.md` now carries the snippet that takes each of its
    numbers, so the figure is re-measurable without the suite. That re-measurement is **by hand**:
    the module that once compared the document's numbers with the tree was cut back to the
    *behaviour* those items describe, and has since been removed with the rest of the
    documentation tests, because re-taking a document's own prose from the tree is a check that
    regenerates its own expectation — the one thing the pinned tabs in the rest of the suite
    exist to avoid. A number in that document can therefore move without the gate failing,
    which is the cost of that choice and is stated where the numbers live.

    The same clean-up found an **unclosed code fence** in that file, which had rendered its
    entire tail as a shell script for four commits, so the doc checker that existed then
    counted fences too. The general form of both: **a document is code that nothing compiles,
    so the parts of it that *can* be checked mechanically must be** — and a number, a fence
    and a link are all of that.

## Where things are documented

| document | what it holds |
|---|---|
| [README.md](README.md) | user-facing overview, worked examples, limitations |
| [docs/engine.md](docs/engine.md) | the engine: grips, the selector, the cost tuple, the six axes (`parts=`, `texture=`, `harmony=`, `bass=`, `grid=`, `TimeSignature`), non-chord tones, and the recipe for adding a chord quality |
| [docs/renderers.md](docs/renderers.md) | tab staff, MusicXML import/export, GP5, and their traps |
| [docs/dependency-dag.md](docs/dependency-dag.md) | the enforced import graphs, drawn: the engine package's layers and their main dependencies, and the front ends' recorded edges |
| [docs/open-issues.md](docs/open-issues.md) | the open bugs, each stated as **issue / problem / why it exists** with its measurement; a fixed one is removed, and its record lives in git |
| [docs/history/](docs/history/) | the retired documents - the completed plans (corpus, walking bass, texture, arranging guide, `voices=`, the Stage-2 collapse, parts, generated grips, comping styles, fingering, restructuring) and the retired reharmonisation proposals. A plan that landed whole carries a header saying where its live rules went: `docs/engine.md` |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | what CI runs, and which tests it does *not* run |

`common_grips.md` is generated from the engine's own tables by `grip_chart.py` and
checked by `make chart-audit` — never edit it by hand.




```bash
make demo                            # the built-in demonstration arrangements
.venv/bin/python -m arranger         # the same thing, without make
.venv/bin/jazz-arranger              # the console script, once installed
```

`main()` also dispatches one subcommand, imported lazily inside the branch so
`import arranger` does not pull in the importer - nor, through it, the renderers it
uses - for a caller who only wants the library:

```bash
.venv/bin/python -m arranger head FILE.musicxml    # the MusicXML importer
```

`make build` wraps `pip wheel . -w dist --no-deps`; no `build` package is required.


  clean install ships without it.
- **The Makefile names the package as a directory**, so a new engine module cannot be
  forgotten by lint or typecheck. A new *top-level* module must be added to `MODULES`
  and to the `typecheck` target in the same commit that creates it.
- **`Voicing` and `ArrangementStep` live in `tuning`, not `steps`**, because `grips`
  constructs a `Voicing` and both dataclasses default `role` to `ROLE_TARGET`. That
  placement is forced by edges, not by taste.


make test        # .venv/bin/python -m unittest discover -s tests -t . -v
make typecheck   # pyright, with --pythonpath so it can see the venv
make lint        # ruff
make demo        # the built-in demonstration arrangements
```

Run everything **from the repository root**; the tests import `arranger` from the tree
and need no install.

