# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project Overview

`arranger` is a small, dependency-light Python library that generates playable
**jazz guitar chord-melody arrangements**. Given a progression of
`(melody note, chord quality, chord name)` triples, it produces Drop-2 voicings
pinned to the melody note on the soprano string and voice-leads them for smooth
finger movement.

Two four-string blocks are modelled. The melody normally sits on the high E
string (voicing on strings D-G-B-E) and moves to the B string (voicing on strings
A-D-G-B) when that gives a better position, or when the melody lies below the
high E string's open pitch `E4` and cannot be voiced there at all.

The entire library lives in a single module: `arranger.py`. Melody notes that fall
outside the chord are handled by a selectable strategy (chord extension, Barry
Harris dim7 substitution, or holding the inner voices) — see
`arrange_progression(non_chord_tone=...)` below.

## Repository Layout

```
arranger/
├── arranger.py            # The whole library + a main() demonstration entry point
├── wjazzd.py              # Optional Weimar Jazz Database glue (stdlib sqlite3 only)
├── pyproject.toml         # PEP 621 metadata (setuptools backend)
├── README.md              # User-facing overview and usage
├── Makefile               # install / test / demo / build / clean targets
├── .gitignore             # Excludes .venv/, __pycache__/, build artefacts, *.db
├── tests/                 # unittest test suite (one file per concern)
│   ├── test_chord_parser.py
│   ├── test_fretboard.py
│   ├── test_non_chord_tones.py
│   ├── test_progressions.py
│   ├── test_tab_rendering.py
│   ├── test_voice_leading.py
│   ├── test_voicings.py
│   └── test_wjazzd.py
└── .venv/                 # Local virtualenv (not committed)
```

`CORPUS_PLAN.md` is the design document for the corpus integration: what was
measured, what was decided, and what is still open. Read it before changing
`wjazzd.py`.

There is **no** `setup.py`, `setup.cfg`, `requirements.txt`, or CI config, and none
is needed. Packaging metadata lives solely in `pyproject.toml`, which uses the
setuptools backend, declares `musthe` as its only runtime dependency, and reads the
version dynamically from `arranger.__version__`.

## Requirements

- Python **3.10+** (the code uses `X | Y` type unions at runtime in signatures,
  e.g. `Voicing | dict`). The local dev virtualenv runs **Python 3.14**.
- One third-party runtime dependency: **[musthe](https://pypi.org/project/musthe/)**
  (music theory primitives: `Note`, `Chord`, `Interval`).
- One optional, **dev-only** tool: **[pyright](https://pypi.org/project/pyright/)**
  for type checking. It is installed in `.venv/` but is deliberately absent from
  `pyproject.toml`, so it never reaches users of the package.

## Setup

A virtualenv already exists at `.venv/`. Prefer invoking its interpreter
directly (`.venv/bin/python`) so you do not depend on shell activation.

Recreate it from scratch if needed:

```bash
python3 -m venv .venv
.venv/bin/pip install musthe
.venv/bin/pip install pyright   # dev-only type checker, not a package dependency
```

No editable install is required — tests import `arranger` directly from the
repository root, so **always run commands from the repo root**. To install the
package (which also provides the `jazz-arranger` console script), use:

```bash
.venv/bin/pip install -e .     # or: make install
```

Note the name split: the **distribution** is `jazz-arranger` because the PyPI name
`arranger` is already taken by an unrelated project, while the **import** name stays
`arranger`.

## Build / Run

There is no build step for local development. Run the built-in demonstration
(minor and major ii–V–I cadences, plus a low-register cadence with the melody on the
B string) with:

```bash
.venv/bin/python arranger.py     # or: make demo
```

Once installed (`pip install -e .`), the same demo is available as the
`jazz-arranger` console script, which calls `arranger.main()`:

```bash
.venv/bin/jazz-arranger
```

The `main()` entry point also dispatches a `corpus` subcommand to the Weimar
Jazz Database front end (see [Corpus integration](#corpus-integration)), which
needs the 42 MB `wjazzd.db` beside the module or at `WJAZZD_DB`:

```bash
.venv/bin/python arranger.py corpus --melid 218
.venv/bin/python arranger.py corpus --list          # the 456 transcriptions
```

To produce distributable artefacts, run `make build`, which wraps
`pip wheel . -w dist --no-deps` — no `build` package is required.

## Testing

Tests use the standard-library `unittest` framework (there is **no pytest
dependency** in the venv). Run the full suite from the repo root:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The equivalent shortcut (prefers `.venv/bin/python`; override with
`make test PYTHON=python3`) is:

```bash
make test
```

Other useful invocations:

```bash
# One test file
.venv/bin/python -m unittest tests.test_progressions -v

# A single test case / method
.venv/bin/python -m unittest tests.test_voicings.TestDrop2Voicings.test_dm7b5_voicings_notes_and_playability -v
```

Some tests assert **exact tab strings** (e.g. `"x-x-12-13-13-13"`) and exact
voice-leading distances. If you intentionally change voicing generation, expect
to update those expected values — but only after confirming the new output is
musically correct and playable.

## Type Checking

The whole repository (`arranger.py` plus `tests/`) is kept clean under
[pyright](https://pypi.org/project/pyright/) in its default `standard` mode:

```bash
.venv/bin/pyright arranger.py wjazzd.py tests   # or: make typecheck
```

There is no `pyrightconfig.json` and none is needed — pyright resolves `musthe`
from the virtualenv it is installed in, so no `--pythonpath` flag is required.

Pyright is a **dev-only** convenience: it is not declared in `pyproject.toml` and
must never become a runtime dependency. Reproduce it in a fresh venv with
`.venv/bin/pip install pyright`; `make typecheck` prints that hint when the tool
is missing.

One recurring trap here: an optional argument written as `chord_name: str = None`
is rejected by pyright, because the default contradicts the annotation. When the
argument really may be `None` (several helpers guard it with `if not chord_name`),
annotate it `Optional[str]` instead. Note also that pyright narrows through a bare
`assert x is not None` but **not** through `self.assertIsNotNone(x)` in tests.

## Corpus integration

`wjazzd.py` reads the **Weimar Jazz Database** and turns the head of a
transcription into a chord-melody arrangement. It is a separate, optional module:
nothing in `arranger.py` imports it except the lazy `corpus` branch in `main()`,
so the library still works with no database present.

The database (`wjazzd.db`, 42 MB, from jazzomat.hfm-weimar.de) is **not
committed** — `.gitignore` excludes `*.db`. It is found beside the module by
default, overridable with the `WJAZZD_DB` environment variable or the `db_path`
argument on every entry point. `DEFAULT_DB` is the resolved `Path`.

**No new dependencies.** The module is stdlib `sqlite3` only, per the standing
rule that `musthe` is the only runtime dependency.

### Purpose: the head, not the solo

The default selection is the **head** — the tune — rather than a harmonised
transcription of someone's solo. A transcribed solo is fast, harmonically
unusual, and fights the changes; a head is the opposite. Solos remain one flag
away (`--section chorus:1`) but are not the point.

### The schema is not what the documentation claims

There is **no** `melopy_notes` or `composition_annotations` table, and notes
carry **no chord column**. The real tables are `solo_info`, `beats`, `melody`,
`sections` and `melody_type`; `melody_type` is SOLO-only with no `THEME` value at
all. `sections` has two categorical columns: `type` is the kind of span (CHORD,
IDEA, PHRASE, FORM, CHORUS) and `value` is what the span is.

**Bars can be negative.** 1,335 `beats` rows across 149 transcriptions sit below
bar 0, reaching bar −31 — that is the anacrusis. `bar` is therefore a signed
integer everywhere in the loader, spans are half-open `[start, end)`, and
`--bars` accepts negative bounds.

### Public surface

| name | purpose |
|---|---|
| `WEIMAR_QUALITY_ALIASES` | Weimar suffix → library quality, 108 entries |
| `parse_weimar_chord(symbol)` | → `(root, quality, bass)`; strips the slash; `NC` → `(None, None)` |
| `Section` / `NoteEvent` / `Solo` | the records, with **signed** bars throughout |
| `Skeleton` / `HeadSelection` / `HeadArrangement` | results, each carrying its own diagnostics |
| `list_solos` / `list_sections` / `parse_section_selector` / `matching_sections` | metadata and span selection |
| `load_solo` / `load_section` | notes with each note's chord forward-filled |
| `select_head(melid)` | the head, found on the chord progression |
| `skeleton_slots` / `skeleton` | the reduction, with and without each slot's timing |
| `build_skeleton` / `arrange_head` | reduction, register, voicings |
| `corpus_cli` / `parse_bar_range` | the `corpus` command and its `--bars` parsing |

### The chord is reconstructed by a forward fill

Notes have no chord, so each note's active chord is the last `beats` row for the
same `melid` with a non-empty chord at `(bar, beat) <= (note.bar, note.beat)`.
The comparison is on the `(bar, beat)` **tuple**, so negative bars order
correctly with no special case. Implemented as a binary search over the chord
onsets (`_forward_fill`), because it runs once per note.

Verified ground truth (`tests/test_wjazzd.py::TestChordForwardFill`): melid 1
gives `Bb6`/`G-7`/`F7` at the three checked positions, melid 218 gives `NC`,
`Eb7`, `C7`, and melid 266 resolves chords at bars −12…−1.

### The head is found on the chord progression, not the form label

`select_head` exists because the form label is unreliable. On all four "All the
Things You Are" transcriptions, `FORM A1` starts at the **second** statement and
the real 8-bar head lies inside the preceding `I` (intro) block. The algorithm:

1. **Seed** from the first `FORM` A-block, extended back over a contiguous `I`
   block (`_seed_span`).
2. **Anchor** on the chord progression at the seed's first chord bar.
3. **Trim** to the shortest span that then recurs, matched **modulo
   transposition** — earliest bar first, then shortest period (`_bar_grid`,
   `_is_transposed_repeat`).
4. **Report** the anchor chords and the trimmed length, so the caller can see
   what was chosen and override it.

Three details are load-bearing and were each forced by a measurement:

- **A per-bar grid, not a list of chord changes.** Chords routinely last two bars
  and transcriptions are inconsistent about it, so change lists never line up
  against each other. Each bar holds a *tuple* of chords, because two changes can
  share a bar (Sims's ATTYA puts `D-7` and `G7` both in bar 6).
- **A constant transposition interval is required.** Qualities alone let a blues
  — nearly all dominant sevenths — match itself at any offset; absolute roots
  fail because ATTYA's A section returns a tone higher.
- **`REPEAT_TOLERANCE = 1`.** Analysts do not enter every change a piece is
  usually written with; Konitz's ATTYA omits bar 6's `G7`, so an exact match
  fails on all four transcriptions. Two differences also match unrelated
  progressions, so the default stays at one.

**Known limitation.** The trim is a heuristic. It finds the 8-bar head on melids
266 and 342, but returns a 6-bar fragment on 328 and falls back to the whole
A-block on 451. Across the corpus 434 of 456 transcriptions yield a head and the
**median head length is 8 bars**. A user wanting a specific tune should pass an
explicit `--bars`. This is the open question in `CORPUS_PLAN.md` §12.

### Skeletons, and the register lift

One voicing is generated per *slot*; the strategy decides what a slot is:
`chords`, `beats`, `eighths`, `sixteenths`, `notes`. The grid is derived from
each note's own `tatum`/`division` rather than assumed to be 4/4, so triplet
transcriptions are handled.

`skeleton_slots` is the reduction that keeps each slot's `(bar, beat, duration)`;
`skeleton` is the same thing with the timing discarded, and is what most callers
want. `Skeleton.timings` carries the timings in step with `triples`, and
`arrange_head` stamps them onto the `ArrangementStep`s, which is the only way a
renderer can place a chord on its real beat rather than on an even grid. The two
lists stay the same length by construction — the lift transposes notes but never
drops or reorders a slot, and the diminished fallback acts per step — so
`arrange_head` still guards the index rather than trusting it.

**`eighths` is the default, by measurement.** Across 116 sampled heads the median
voiced-step rate is 85.9% for eighths against 85.6% for sixteenths and 85.7% for
beats — the extra density buys no extra playability, so there is no reason to pay
for it. `chords` voices everything but yields four steps for an eight-bar head,
which is a chord list rather than an arrangement.

`--lift auto` builds the head twice, as transcribed and an octave up, and keeps
whichever voices **strictly more** steps; ties go to the original, so music is
never moved without a gain. This is threshold-free, so a median sitting one
semitone above an arbitrary cut-off cannot defeat it. The whole head is
transposed at once, so no melodic interval can be distorted by construction.
`--lift per-note` is available and warns, because lifting single notes tears the
line apart.

### Slash chords: rules B and C, loader-only

95 distinct slash chords appear in the corpus. `parse_chord_name` glues a bass
onto the quality, so every one of them silently fails the table lookup — the
loader must strip the bass first.

- **Rule B** (`promote_slash_chord`) — a triad whose bass is its own seventh
  implies a seventh chord: `A-/G` → `m7`, `C-/Bb` → `m7`, `D/C` → `m7`.
- **Rule C** (`bass_cost`, `_arrange_step_with_bass`) — prefer the candidate
  whose lowest pitch is nearest the bass. This is **combined** with the engine's
  voice-leading rule, not applied after it: the candidates are partitioned by
  bass cost and the engine then decides within the best group, because sequencing
  them would let whichever ran last always override the other.

Both live in the loader, so `arranger.py`'s public surface stays frozen and the
394 transcriptions without slash chords behave as if the symbols were stripped.

### Non-chord tones and the dim7 retry

`extension` remains the default. Heads are **not** more chord-tone-rich than
solos — 58.7% at best corpus-wide, and 48.6–64.5% on real standard melodies — so
unresolved tensions are routine, not exceptional.

`--fallback diminished` retries them as Barry Harris dim7 substitutions. It works
mechanically, but it **replaces the written chord**, and on a 12-bar blues six of
the substitutions tend to land on the tonic. It is therefore **off by default**,
and the number of steps it *would* rescue is always reported, so the user can see
what they are missing without opting in.

### Conventions specific to `wjazzd.py`

- **Never guess a chord.** An untranslatable suffix returns `None` and is counted
  in `Solo.unmapped_suffixes`. The same applies to the engine: a quality the
  library cannot voice is left out of `WEIMAR_QUALITY_ALIASES` rather than folded
  into a near neighbour (`79#13` is a real 7♯13; the library voices 7♭13, so it
  is reported instead).
- **Bars are signed** in every signature, comparison and range parser.
- **Ranges are half-open** and may be negative. `parse_bar_range` uses a regex
  rather than splitting on a hyphen, which cannot tell a separator from a minus
  sign when both bounds are negative (`-8--1`).
- **Imports are lazy where they keep `arranger` clean** — `corpus_cli` imports
  `argparse` and `format_progression` inside the function, and `main()` imports
  `wjazzd` inside the branch.
- **Tests are guarded** by `skipUnless(DEFAULT_DB.is_file())` so the suite passes
  on a fresh clone with no 42 MB download. Tests needing no database (the
  notation table, the record types, the selector and range parsers) always run.

## Architecture / Key Types (`arranger.py`)

- `STANDARD_TUNING` — six open-string `Note`s, index `0` = low E (string 6)
  through index `5` = high E (string 1). `STRING_NAMES` mirrors these.
- `MELODY_STRING_CHOICES` — `(5, 4)`: the soprano string indices a voicing may be
  pinned to (`5` → D-G-B-E, `4` → A-D-G-B). Index `0` = low E ... `5` = high E, so
  the conventional guitar string number is `6 - index` (index `5` = string 1).
- `Voicing` — a dataclass for one fretboard shape: `frets` (6 entries,
  `-1` = muted), `top_fret`, `avg_fret`. Helpers: `tab_string()` (one-line
  `x-x-12-13-13-13`, frozen: ~40 call sites in tests and docs depend on it),
  `tab_block()` (six-line vertical tab, high E first, two-char right-aligned
  cells, highest string labelled lowercase `e`), `tab()` (`tab_block()` joined
  with newlines), `active_frets()`, `fret_span()`, `midi_notes()`,
  `pitch_classes()`, `soprano_string()` (index of the highest sounding string;
  `-1` if all muted). Supports legacy dict-style access (`v["frets"]`).
- Tab rendering is **pure**: every renderer returns a string (or list of
  strings) and prints nothing, so callers control display. Only `main()` and the
  `arrange_progression` warning paths write to stdout.
- `ArrangementStep` — a dataclass of `chord`, `melody`, `voicing` plus the
  non-chord-tone bookkeeping `non_chord_tone` (bool), `strategy` (which strategy
  handled the step) and `harmonized_as` (the substitute chord name). Also
  `tab_line()` / `tab_block()`, which delegate to the `Voicing` renderers.
  Supports legacy dict-style access (`step["chord"]`).
  The optional `bar` / `beat` / `duration` (all default `None`) carry the timing the
  staff renderer needs; `has_timing` reports whether a step can be placed on a grid.
- `format_progression(steps, vertical=False)` — module-level renderer for a
  whole arrangement: one line per step by default, six-line tab blocks when
  `vertical=True`. Non-chord-tone steps are annotated via the shared
  `_step_annotation()` helper, which `_print_step()` also uses so the two
  renderings cannot drift.
- `format_tab_staff(steps, beats_per_bar=4, rhythm=True, show_chords=True,
  show_melody=False, show_melody_string=True, show_mutes=False, collapse=True,
  measures_per_line=4)` — renders the **whole progression along one six-line
  staff** in reading order (high E on top), which is the standard tab layout and
  unlike `format_progression` is not one block per chord. Chord names go on a line
  above, each starting in the column where its shape is struck. Three decisions are
  load-bearing and were each forced by looking at the output:
  - **Fret cells are left-aligned in a fixed-width column.** A right-aligned cell
    looks tidy on its own but puts the fret at the far end of the column, so the
    chord name and its frets no longer share a column. The column width widens to
    the longest chord name rather than letting the chord line drift out of step
    with the frets under it.
  - **`collapse` compares sounding pitches, not fret numbers.** The skeleton voices
    one step per eighth, so without it a held chord is restruck eight times a bar and
    the staff is a chord list rather than a held shape. A rest clears the held
    pitches, because a rest genuinely stops the ringing.
  - **Barlines are every `measures_per_line` bars, not every bar**, and the grid
    starts at the first step's own onset so a head selected from bar 1 (or from a
    negative pickup bar) is not preceded by empty bars.
  Muted strings are blank by default (a ringing voice is not restruck);
  `show_mutes` spells them out, and a melody-only step always shows its `x`s.
  With no step timing, `rhythm=True` falls back to a uniform one-chord-per-beat
  grid rather than failing.
- `GuitarFretboard` — static helpers `note_to_fret(string_index, note)` and
  `fret_to_midi(string_index, fret)`. Out-of-range inputs return `-1`.
- `ChordParser` — `parse_chord_name(name) -> (root, quality)`,
  `get_melody_degree(root, melody_note) -> 0..11`, `canonical_quality(quality)`
  (case-sensitive alias resolution: `M7` -> `maj7`, `M` -> `maj`, `m7` stays `m7`)
  and
  `get_chord_tones(quality, chord_name=None)` -> every pitch class in the chord.
  `CHORD_TONES_FROM_ROOT` is the full tone set per quality, deliberately distinct
  from `DEGREE_OFFSETS_FROM_ROOT`, which lists only the four notes a drop-2 shape
  voices — so the root of a rootless `7b9` still counts as a chord tone.
- `VoiceLeadingEngine` — the core engine:
  - `DROP2_INTERVAL_SETS`: semitone offsets from the soprano voice for each
    supported chord quality (seventh, extended, triad, suspended and altered
    families) plus aliases.
  - `DEGREE_OFFSETS_FROM_ROOT`: which chord tone each inversion places on top.
  - `get_drop2_voicings(melody_note, chord_type, chord_name=None, top_string=5)`
    — one string block; `top_string=4` pins the melody to the B string.
  - `get_all_drop2_voicings(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES)` — candidates across every allowed soprano
    string, high-E first, applying the chord-tone match then the quality-only
    fallback.
  - `calculate_voice_leading_distance(voicing_a, voicing_b)` — per-string fret
    movement, kept for backward compatibility (only meaningful within one block).
  - `calculate_pitch_leading_distance(voicing_a, voicing_b)` — movement in
    semitones between sorted sounding pitches; identical to the fret metric within
    one block, and the metric `arrange_progression` uses across blocks.
  - `NON_CHORD_TONE_EXTENSIONS` — canonical quality → `{melody degree: extension
    quality}`, the routing used by the `extension` strategy.
  - `NON_CHORD_TONE_STRATEGIES` — the accepted `non_chord_tone` values.
  - `is_chord_tone(melody_note, chord_type, chord_name)` — chord-tone detection
    using `ChordParser.CHORD_TONES_FROM_ROOT`; `False` for unknown qualities.
  - `resolve_non_chord_tone(melody_note, chord_type, chord_name, strategy,
    next_melody=None)` -> `(quality, name)` for a substitute chord, or `None` when
    the strategy cannot help (the caller then keeps its fallback).
  - `sustain_inner_voices(previous_voicing, melody_note)` — holds the previous
    voicing's inner voices and moves only the soprano; `None` when unplayable.
  - `arrange_progression(progression, top_strings=MELODY_STRING_CHOICES,
    non_chord_tone="extension")` — voices each step and, when a melody note is not
    a chord tone, applies the selected strategy. An unknown strategy raises
    `ValueError`.
- `__version__` — the library version string (currently `0.4.0`). `pyproject.toml`
  reads it as the dynamic project version, so it is the single source of truth.
- `NO_CHORD` — the string `"NC"`, a bar carrying melody with no harmony.
- `VoiceLeadingEngine.get_melody_only_voicing(melody_note, prefer=...)` — a
  **single-fret** `Voicing` for an NC step, or `None` if unreachable. It is
  explicitly *not* a drop-2 voicing and is exempt from the four-string invariant.
- `ArrangementStep.melody_only` — defaulted flag set on NC steps.
- `main()` — with no arguments, prints the built-in demonstrations; with `corpus`
  as the first argument, delegates to `wjazzd.corpus_cli` through a **lazy**
  import, so `import arranger` never depends on the database module.
- `main()` — prints the built-in demonstration arrangements; exposed as the
  `jazz-arranger` console script via `[project.scripts]`.

### Adding a new chord quality

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
3. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`.
4. Add aliases to `ChordParser.QUALITY_ALIASES` (and, for backward compatibility,
   optionally to the `DROP2_INTERVAL_SETS[...] = ...` block).
5. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
6. **If the Weimar Jazz Database should be able to spell it**, add the matching
   suffix to `WEIMAR_QUALITY_ALIASES` in `wjazzd.py`. The database has 108
   distinct suffixes in its own notation, and one that is absent resolves to
   `None` and is *counted and reported* rather than guessed - so a new quality
   the corpus cannot reach is silent until this step is done.
7. Add tests to `tests/test_voicings.py`: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`.
   `TestQualityTableInvariants` checks the template and degree lists stay the same
   length, and `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route. `tests/test_wjazzd.py` asserts every
   `WEIMAR_QUALITY_ALIASES` entry resolves to a quality the library can voice, so
   a table entry naming an unvoiceable quality fails the suite.

## Coding Conventions

- Single-module design — keep new public behavior in `arranger.py` unless the
  user asks to split it.
- `from __future__ import annotations` at the top; use `typing` aliases
  (`List`, `Optional`, `Tuple`, `Dict`, `Any`) consistent with the file.
- Dataclasses for value objects; `@staticmethod`/`@classmethod` for stateless
  logic on `GuitarFretboard`, `ChordParser`, and `VoiceLeadingEngine`.
- Preserve the dict-style `__getitem__` backward-compatibility shims on
  `Voicing` and `ArrangementStep`.
- Docstrings on public classes/methods; keep comments meaningful (they explain
  music-theory intent, e.g. which chord tone is in the top voice).
- Playability invariants that must hold for every generated voicing:
  - exactly four contiguous strings are used — indices `2–5` (D, G, B, E) for
    `top_string=5`, or `1–4` (A, D, G, B) for `top_string=4`; every other string
    is muted (`-1`),
  - the soprano string — index `5` (high E) or `4` (B) — carries the melody note,
  - `0 <= fret <= 18` and `fret_span() <= 5`.
  - A melody below the high E string's open pitch (`E4`) produces no high-E
    candidates and is voiced on the B string instead; `top_strings=(5,)` restores
    the original high-E-only behaviour. Both families sound the same pitches for a
    given inversion — only the position on the neck differs.
- **Do not add new third-party dependencies** without explicit approval;
  `musthe` is the only one in use.

## Contributing Workflow

1. Read `arranger.py` and the relevant test file before changing behavior.
2. Make the smallest change that satisfies the requirement.
3. Add or update tests in `tests/` following the existing `unittest` style —
   one class per concern, descriptive `test_*` method names, docstrings stating
   what is verified.
4. Run the full suite from the repo root:
   `.venv/bin/python -m unittest discover -s tests -v` (must report `OK`).
5. Run the type checker (`.venv/bin/pyright arranger.py wjazzd.py tests`, or `make typecheck`)
   — it must report `0 errors`. Do not leave a new `reportArgumentType` behind,
   especially when touching a signature.
6. Run the demo (`.venv/bin/python arranger.py`) when touching voicing or
   voice-leading logic and sanity-check the printed tabs.
7. Keep commits focused. This directory is a git repository (initialized with a
   baseline commit), so commit each logical change separately.

## Known Limitations

- Only four strings are modeled at a time (the high-E block or the B block); no
  full six-string voicings or barres. Fret `0` does appear when a voice happens to
  land on an open string (e.g. `x-2-3-0-3-x`).
- Melodies are still confined to `B3`–`Bb5`: `B3` is the lowest pitch reachable on
  the B string, `Bb5` the highest on the high E string. Adding the third block
  (melody on the G string, strings G-D-A-low E) is a one-tuple addition to
  `MELODY_STRING_CHOICES`.
- A fixed max fret span of 5 and fret range 0–18 is assumed.
- Non-chord melody notes are only covered for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths and the
  half-diminished 9th) plus the dim7 substitution. An unmapped non-chord tone prints
  a warning and keeps the legacy quality-only fallback, which can sound the melody
  over a different chord's shape.
- A handful of low melodies (around `B3`–`C4`) reach no chord-tone-matched inversion
  on either block and therefore use that quality-only fallback; the rate matches the
  long-standing qualities (`maj7`, `m7`, `9`, `m9`). Triad shapes double the root, so
  their second voice can sit up to 10 semitones below the melody — the same span
  limit, not a new failure mode.
- The `sustain` strategy is structural, not rhythmic: `arrange_progression` takes
  only `(note, quality, name)` triples, so it cannot tell a brief passing note from
  an accented tension. Holding the inner voices is applied whenever the shape can
  physically stay put.
- `7b9`/`7alt` are voiced rootless apart from their new root-in-top inversion;
  other omitted tones (e.g. a root-on-top `13`) have no template yet.
- If no voicing matches a melody/chord, `arrange_progression` prints a warning
  and **skips** that step (rather than raising).
- **Corpus (`wjazzd.py`):**
  - The head selector is a heuristic. It finds the right 8-bar head on ATTYA
    melids 266 and 342, but returns a 6-bar fragment on 328 and falls back to the
    whole A-block on 451. 434 of 456 transcriptions yield a head (median 8 bars).
    Pass an explicit `--bars` when you know which bars you want.
  - `wjazzd.db` is not committed. Every database-backed test is skipped when the
    file is absent, so a fresh clone runs a reduced suite.
  - Heads are **not** harmonically simpler than solos (58.7% chord-tone rate at
    best; 48.6–64.5% on real standard melodies), so roughly half the steps need a
    non-chord-tone strategy and `--fallback diminished` is a live option — which
    replaces the written chord, so it stays opt-in.
  - `--lift auto` may transpose a head an octave, including Blue Train's. It
    reports the decision on every run. Transposing the whole head at once cannot
    distort an interval, but it does move the music.
  - A slash bass is honoured as a *preference* (rule C), not a hard constraint; a
    bass the voicings cannot supply falls back to the unslashed behaviour.
  - The corpus path assumes 4/4-style beat grids derived from `tatum`/`division`.
    Triplet divisions are handled, but no non-4/4 *time signature* has been tested.
- `lead_sheet.py` is stale: it queries `melopy_notes`, `chord_type`,
  `rel_pitch_class` and `solo_info.tempo`, none of which exist in this database.
  It is not part of the package and is not covered by the corpus work.
- The public API is packaged as `jazz-arranger` and versioned through
  `arranger.__version__` (currently `0.4.0`), but there is no CI and nothing has
  been published to PyPI.

