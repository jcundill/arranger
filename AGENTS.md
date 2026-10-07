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
| the drop-2 tables, a grip, `GRIP_MAX_SPAN`, `voicing_cost` | [docs/engine.md](docs/engine.md) | `arranger/grips.py`, `arranger/cost.py` |
| `texture=`, target/fill roles, the walking bass | [docs/engine.md](docs/engine.md) | `arranger/textures.py`, `arranger/bass.py` |
| non-chord melody notes, a new chord quality | [docs/engine.md](docs/engine.md#adding-a-new-chord-quality) | `arranger/chords.py` |
| the step loop, `arrange_progression`, `Diagnostics` | [docs/engine.md](docs/engine.md) | `arranger/steps.py` |
| tab staff, HTML, MusicXML, GP5, or the MusicXML importer | [docs/renderers.md](docs/renderers.md) | `tabstaff.py`, `tabxml.py`, `tabgp.py`, `headxml.py` |
| the slot layer: triples to steps, the diminished retry, the slash bass | [docs/engine.md](docs/engine.md) | `arranger/slots.py` |
| a known bug, with its measurement | [docs/open-issues.md](docs/open-issues.md) | — |
| `voices=`, which voices the guitar plays | [docs/voices-axis.md](docs/voices-axis.md) | `arranger/textures.py` |
| the comping axes (`harmony=`, `grid=`, the rhythm grid) | [docs/comping-styles.md](docs/comping-styles.md) | `arranger/textures.py` |
| the step/voicing mirrored fields (`step.grip`, `step.bass`), or which voice selection is melody-only | [docs/one-fact.md](docs/one-fact.md) | `arranger/tuning.py`, `arranger/steps.py` |
| how something was decided, historically | [docs/history/](docs/history/) | — |
| user-facing behaviour and examples | [README.md](README.md) | — |

**`docs/history/` is deliberately not extended.** It is where a completed plan goes:
it records why a decision was made and is never revised. If the code has moved on, the
history is still true *about the past* — so read the current documents above first and
treat a contradiction between them as a bug in one of them.

## The gate

```bash
make check      # lint + typecheck + test, in that order — what CI runs
```

Current measured state: **889 tests OK (skipped=2)**, pyright **0 errors 0 warnings**,
ruff **0 errors**. If your change moves any of those numbers, that is the signal — not
the absence of an error message. A quiet run is not evidence; a moved count is.
(`tests/test_docs.py` is 12 of those 889, and it is the one that fails if this
document — or the CI workflow — stops describing the tree. It also fails if a document
exists that it does not know about: `DOCUMENTS` is compared against what is on disk, so a
new file cannot be added without being registered.)

**Five axes, not one.** `texture=` (where notes fall), `bass=` (who plays the bottom,
`BASS_STYLES`), `voices=` (which voices the guitar plays, `VOICE_NAMES`), `harmony=`
(which *degrees* the part states when it is not singing, `HARMONY_STYLES`) and `grid=`
(*where a chord falls* in the bar, `GRID_STYLES`) are **orthogonal**, and
a band setting is a combination rather than a mode: `bass="none", voices="none"` is a
bassist on the root, a horn on the melody and the guitar comping guide tones between them.
Adding an axis means a new `*_STYLES` / `*_POLICIES` pair and a `*_AUTO` sentinel that
is deliberately **not** in the styles list, plus a `*_allowed` refusal function derived from
a table rather than listed — never another branch at the call sites. The trap: a loop
variable shadowing a policy parameter (`melody` in `wjazzd.arrange_slots` did exactly this,
and it only raised when a diminished retry had something to rescue).

**`harmony=` was added by following that rule, and the three traps below are what it cost.**
`HARMONY_STYLES` + `HARMONY_POLICIES` + `HARMONY_AUTO` + `harmony_allowed` in
`textures.py`, resolved once per arrangement next to `_resolve_melody`, and inert twice
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
- **The shell chord-melody is not on this axis.** `--grips shell` is a *grip* choice
  layered on the same degrees, with the melody pinned to the soprano string;
  `harmony=guide` is the melody-free part. They are deliberately separate — see
  [docs/comping-styles.md §4.1](docs/comping-styles.md) — and `harmony=` is inert on any
  arrangement the guitar sings, so `--grips shell` is untouched by it. **This was a
  decision, not an oversight**: `harmony=guide` with `sings=yes` could instead have been
  routed through the shell grip, which would have made `--grips shell` redundant and given
  the axis one spelling for both routes. That is §6 Q2 option (A), and it is **deferred
  along with the `--voices` rename**, because until it lands `harmony=` cannot express
  `soprano` and so cannot replace `--voices`. A fifth axis inherits this constraint: scope
  it to the comping route, and do not let it reach the melody-bearing one by accident.

**`make check` is what CI runs**, in one job (`.github/workflows/ci.yml`, Python
3.11–3.14, with the `xml` and `gp` extras so the optional-extra tests are not silently
skipped). **There is no second job and nothing a clean clone cannot run** — that used
to need stating here and in the workflow header, because the 42 MB Weimar Jazz
Database was gitignored and 85 of the suite's tests skipped on every fresh checkout.
The database is gone, so a green check means the whole suite ran, and the only guards
left are the optional-extra ones this job installs against.

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
│   ├── diagnostics.py   #   Diagnostics - warnings are a value, not a print
│   ├── chords.py        #   ChordParser, non-chord-tone routing
│   ├── grips.py         #   grip tables and the candidate generators
│   ├── cost.py          #   voicing_cost - the library's central invariant
│   ├── textures.py      #   metric roles: what a slot is for
│   ├── bass.py          #   the walking-bass thumb line
│   ├── options.py       #   ArrangeOptions - the knobs as one value
│   ├── decisions.py     #   decisions both step loops share
│   ├── steps.py         #   VoiceLeadingEngine and the one step loop
│   ├── slots.py         #   the slot layer: triples to steps, the one pre-pass
│   ├── render.py        #   format_progression and per-step rendering
│   └── cli.py           #   the head CLI's flags and output dispatch
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
dynamically from `arranger.__version__` — that is the single source of truth, and
`tests/test_docs.py` fails if a document states a different one.

### The engine is a package, and the order is enforced

The engine was one 4290-line module until Phase 5 of the package refactor. It is
now thirteen modules in a strict dependency order:

```
tuning -> diagnostics -> chords -> grips -> cost -> textures
                                                   |
                            bass <- options -----+----> decisions
                                                   |
                                                 steps -> slots -> render -> cli
                                                            |              |
                                                          (facade) <-------+
```

A module may import only what is *below* it, and
**`tests/test_package_dag.py` asserts that from the AST** — so the layering cannot
erode one "temporary" import at a time. Read its `ORDER` list before adding a module.
`ALLOWED_EDGES` in that file is the escape hatch: each entry there must justify itself
in a comment, which is what makes a seventh edge visible.

Three consequences worth knowing:

- **Adding a module inside `arranger/` needs no `pyproject.toml` change** — the
  package is already listed. A new *top-level* module needs a `py-modules` entry, or a
## Requirements and licence

- Python **3.11+**. The local dev virtualenv runs 3.14. 3.10 was dropped because
  `tests/test_docs.py` reads the metadata with `tomllib`, which is 3.11+.
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
- **The library never prints.** Warnings go through `Diagnostics`, a collector whose
  `emit` hook defaults to `print`, so nothing a user sees changed but a test can now
  read them. Adding a `print()` to the engine is a regression, and `tests/
  test_diagnostics.py` asserts stdout is empty when a collector is passed.
- **Do not add a third-party dependency** without explicit approval. `musthe` is the
  only runtime one; that is load-bearing for the LGPL reasoning above.

### Playability invariants

Every generated voicing must satisfy all of these. They are asserted per-shape in
`tests/test_grips.py`, and they are what makes a tab playable rather than merely
correct:

- the sounding strings are exactly one `supported_string_sets()` entry — two to four
  strings, every other muted (`-1`);
- the melody is on that entry's soprano string, and is the highest sounding note;
- `0 <= fret <= 18` and `fret_span() <= GRIP_MAX_SPAN[grip]` (5, or 4 for a duo).
  The span is checked on the frets actually placed, **not** as "within N of the
  soprano": those differ, and the second admits a span of ten;
- every sounding pitch is a chord tone — except where the drop-2 tables have no
  inversion for the melody's degree and the quality-only fallback takes over. The
  selector's first cost criterion rejects such a shape whenever a correct one exists.

Two more that follow from the neck window, which is a **preference and never a
filter**: a step with no voicing inside frets 2–13 is still played, just outside it,
because losing a chord of the tune is worse than being a fret out of position. And a
melody whose only position sits above `HIGH_FRET_LIMIT` is voiced an octave down, so
`step.melody` may be an octave below the written note — the written pitch stays in
`step.original_melody`.

### The cost tuple is not being refactored

`voicing_cost`'s 8-element tuple is the library's central invariant, asserted
positionally in `tests/test_grips.py::TestVoicingCost`. Moving the code is safe;
**reordering it is a musical decision, not a refactor.** Span is the one criterion
promoted above position, and that was measured rather than guessed — the reasoning
and the table of what it cost are in [docs/engine.md](docs/engine.md).

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
## Adding a new chord quality

1. Add a template list to `DROP2_INTERVAL_SETS` (one inversion template per voiced
   tone, each `[0, offset2, offset3, offset4]` in semitones below the soprano).
   Derive each template from the close-position stack under the melody: with
   `d1 < d2 < d3` the **cumulative** semitone distances down from the top voice to
   the next three chord tones (each the nearest chord tone below), the drop-2 shape
   is `[0, -d2, -d3, -(d1 + 12)]` — the second voice from the top lowered an octave.
   A triad needs a fourth voice, so its templates double the root an octave below the
   stack; ninth/13th qualities are voiced rootless (root, or 5th when the root is on
   top, omitted) so the extra tone still fits four strings.
2. Add the matching entry to `DEGREE_OFFSETS_FROM_ROOT` **in the same order** as
   the templates, so each melody note is matched to the correct inversion.
3. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`. This is also
   what `drop3`, `closed`, `shell` and `duo` build themselves from, so it is required
   for the new grips to reach the quality at all. If the quality should also get a
   shell, add it to `SHELL_DEGREES` — the default drop-2 and the derived grips work
   without one.
4. Add aliases to `ChordParser.QUALITY_ALIASES` (and, for backward compatibility,
   optionally to the `DROP2_INTERVAL_SETS[...] = ...` block).
5. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
6. **If a MusicXML file should be able to spell it**, add the matching
   `kind-value` to `MUSICXML_KIND_QUALITIES` in `headxml.py`, and any `<degree>`
   alteration that reaches it to `_DEGREE_REFINEMENTS`. The same rule applies: an
   absent kind resolves to `None` and is counted in `Head.unmapped`, so a new
   quality MusicXML cannot spell stays silent until this step is done. Note the
   table is keyed on the *library* quality, so a `kind` that only a `<degree>`
   reaches (a 7b5, say) needs a degree entry rather than a kind entry.
7. Add tests to `tests/test_voicings.py` for the drop-2 fingerings and to
   `tests/test_grips.py` for the other grips: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`, and the sounding strings
   a member of `supported_string_sets()`.
   `TestQualityTableInvariants` checks the template and degree lists stay the same
   length, and `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route.
   `tests/test_headxml.py::TestChordParsing::test_every_kind_the_table_names_is_voiceable`
   is the same assertion for `MUSICXML_KIND_QUALITIES`.


## Traps

Each of these cost real time, or nearly shipped a defect.

1. **A gate that enumerates its inputs by hand silently skips whatever was added
   last.** The Makefile named each source file in three places, so `diagnostics.py`,
   `decisions.py` and `options.py` were unlinted and untypechecked until noticed.
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
   asserts the opposite (the engine calls them, and `wjazzd` must contain none of it).

6. **When consolidating two branches, check whether their *outputs* differ before
   unifying their predicates.** `melody_alone_case` nearly shipped as a `bool`, and
   unifying the `NC` branch with the walking-bass branch on it would have annotated a
   step *"(no chord - melody alone)"* that claims to have a chord. The predicate
   returns a **kind** (`none` / `texture` / `nc`) for exactly this reason.

7. **A large mechanical move must copy text, not retype it.** Phase 5 moved 4290
   lines into eleven modules by slicing the original *by line number*, so a docstring,
   a fret number or a comment provably cannot change in the move. Generate into a
   script you keep until the suite is green — a half-applied regeneration over a good
   tree is much harder to unpick than a wrong line is to find.

8. **A stale "before" measurement will invent differences that are not there.** When
   proving a refactor changed nothing, capture the fingerprint from the commit you
   think it is, not from a file that has been sitting in the tree since
   (`git worktree add /tmp/pre HEAD`). The 42 MB database is gitignored, so copy
   `wjazzd.db` across or the corpus half of such a capture comes back empty. The
   capture itself is a throwaway script under `/tmp`, kept out of the repository:
   `tests/test_step_loop_equivalence.py` is the standing check, and a measurement
   that only matters during one refactor has no business outliving it.

9. **A count without a denominator is not a metre.** 2/2 and 2/4 are both two beats
   to the bar, and both readings of `4 / beat_type` agree in 4/4 — so the whole suite
   passed while the file was unusable for every other metre. That is why `Head`
   carries `beat_type` and it is plumbed to the file headers, and why the check that
   catches it sums each measure's durations rather than counting measures.

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

## Where things are documented

| document | what it holds |
|---|---|
| [README.md](README.md) | user-facing overview, worked examples, limitations |
| [docs/engine.md](docs/engine.md) | grips, the selector, texture, the cost tuple, non-chord tones |
| [docs/renderers.md](docs/renderers.md) | tab staff, MusicXML import/export, GP5, and their traps |
| [docs/open-issues.md](docs/open-issues.md) | diagnosed bugs with their measurements; fixed items stay, with what the fix was |
| [docs/reharmonisation-proposals.md](docs/reharmonisation-proposals.md) | tritone substitution (shipped) and chromatic approach chords (measured, not built), with the corpus numbers behind each |
| [docs/history/](docs/history/) | completed plans: corpus, walking bass, texture, arranging guide - a record of the past, not of what exists |
| [docs/voices-axis.md](docs/voices-axis.md) | **in progress** - the `voices=` axis, awaiting QA |
| [docs/comping-styles.md](docs/comping-styles.md) | the comping axes (`harmony=`, the rhythm grid): **partly built** - Stage C shipped `harmony=`, Stage D shipped the named `grid=` rows, and §9 steps 0, B, A, A', C, D and E have landed (E, `--voices soprano` = the melody and nothing else, landed earlier as Stage 2 — `docs/one-fact.md`; A' makes a **chords-only lead sheet** loadable, `Head.bars` a fact about the file; C makes `--non-chord-tone` reach the comping route at harmony level, onset-guarded by `melody_onsets`; D makes the soprano **per slot**, so a soprano-named selection comps the grid positions its tune does not articulate at); §9.4's four-note comping chord, and §6's open questions, are still proposal |
| [docs/one-fact.md](docs/one-fact.md) | the Stage-2 collapse, **landed**: one field per fact (`step.grip`, `step.bass` as derived views), and the melody-only signal moved from `texture=` to `voices=` |
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

