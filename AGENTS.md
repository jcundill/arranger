# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project Overview

`arranger` is a small, dependency-light Python library that generates playable
**jazz guitar chord-melody arrangements**. Given a progression of
`(melody note, chord quality, chord name)` triples, it produces voicings pinned to
the melody note on the soprano string, keeping the arrangement in a playable
position on the neck and moving the hand as little as possible.

Several grip families are modelled, not just drop-2: four-note drop-2 and drop-3
shapes, three-note shells (including the 6-4-3 grip on strings 6-4-3), and two-note
duos. The melody may sit on the high E, the B **or the G** string, so a melodic
position can be held by changing strings rather than by moving the hand. A
position-aware selector then chooses among the candidates, keeping the arrangement
inside a comfortable neck window (frets 2-13) and near where the hand already was;
where no complete four-note chord fits, a three-note shell is used, and a two-note
duo only when the melody is the chord's root or 5th — see
[Grips, and the position-aware selector](#grips-and-the-position-aware-selector).
A melody that cannot be voiced anywhere near the window is additionally transposed
**down an octave** — see
[High melodies move down an octave](#high-melodies-move-down-an-octave).

The entire library lives in a single module: `arranger.py`. Melody notes that fall
outside the chord are handled by a selectable strategy (chord extension, Barry
Harris dim7 substitution, or holding the inner voices) — see
`arrange_progression(non_chord_tone=...)` below.

## Repository Layout

```
arranger/
├── arranger.py            # The engine + a main() demonstration entry point
├── tabstaff.py            # Whole-progression staff renderers (ASCII + HTML)
├── tabxml.py              # MusicXML export (optional extra: music21)
├── tabgp.py               # Guitar Pro 5 export (optional extra: PyGuitarPro)
├── headxml.py             # MusicXML import: read a melody + chord-symbol score
├── wjazzd.py              # Optional Weimar Jazz Database glue (stdlib sqlite3 only)
├── pyproject.toml         # PEP 621 metadata (setuptools backend)
├── README.md              # User-facing overview and usage
├── Makefile               # install / test / demo / build / clean targets
├── .gitignore             # Excludes .venv/, __pycache__/, build artefacts, *.db
├── tests/                 # unittest test suite (one file per concern)
│   ├── test_chord_parser.py
│   ├── test_fretboard.py
│   ├── test_grips.py
│   ├── test_headxml.py
│   ├── test_musicxml.py
│   ├── test_non_chord_tones.py
│   ├── test_progressions.py
│   ├── test_tab_rendering.py
│   ├── test_voice_leading.py
│   ├── test_voicings.py
│   ├── test_wjazzd.py
│   └── data/                 # Committed MusicXML fixtures: music21, MuseScore and
│                              # this library's own export. Excepted from the
│                              # *.musicxml / *.mxl rules in .gitignore.
└── .venv/                 # Local virtualenv (not committed)
```

`CORPUS_PLAN.md` is the design document for the corpus integration: what was
measured, what was decided, and what is still open. Read it before changing
`wjazzd.py`.

There is **no** `setup.py`, `setup.cfg`, `requirements.txt`, or CI config, and none
is needed. Packaging metadata lives solely in `pyproject.toml`, which uses the
setuptools backend, declares `musthe` as its only runtime dependency, offers
`music21` as the `xml` extra, and reads the version dynamically from
`arranger.__version__`.

## Requirements

- Python **3.10+** (the code uses `X | Y` type unions at runtime in signatures,
  e.g. `Voicing | dict`). The local dev virtualenv runs **Python 3.14**.
- One third-party runtime dependency: **[musthe](https://pypi.org/project/musthe/)**
  (music theory primitives: `Note`, `Chord`, `Interval`).
- One **optional** dependency: **[music21](https://pypi.org/project/music21/)**, the
  `xml` extra, used only by `tabxml.py`. It is the single exception to the
  musthe-only rule, and it is not a soft one: the import is *inside* the functions,
  so `import arranger`, the ASCII staff and the HTML page all work on a machine
  that has never installed it, and `tests/test_musicxml.py` is `skipUnless`-guarded
  exactly as the database-backed tests are.
- A second **optional** dependency, on the same terms:
  **[PyGuitarPro](https://pypi.org/project/PyGuitarPro/)**, the `gp` extra, used only
  by `tabgp.py`. It is **LGPL-3.0** and pulls in `attrs`, which is why it is a
  separate extra and never a runtime dependency — a plain `pip install
  jazz-arranger` must not pull it in. It is imported the same lazy way, and
  `tests/test_guitarpro.py` is guarded the same way. The two extras are
  independent: a run asking for a GP5 file must not require `music21`, or the
  other way round.
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

### If the interpreter hangs at startup

`Fatal Python error: init_import_site: Failed to import the site module`, with a
traceback running through `site.addsitedir`, means the editable-install finder in
`site-packages` is broken. It is worth knowing because the symptom is a **hang, not an
error**: the traceback only appears once something interrupts it, so the shell can
look simply stuck rather than broken, and the failure gets mistaken for a slow import
or a flaky terminal.

The cause seen here was a stale finder for a long-superseded version —
`__editable___jazz_arranger_0_1_0_finder.py`, left over from when the project was at
0.1.0 and now 0.5.0. It is regenerated on every `pip install -e .`, so the stale copy
is what a version bump in `pyproject.toml` leaves behind when the reinstall is
skipped.

The fix is to reinstall rather than to hand-edit the finder:

```bash
.venv/bin/pip install -e . --no-deps
```

That replaces the stale finder and the matching `.pth` with ones for the current
version. To confirm the symptom is this and not something else, run
`./.venv/bin/python -S -c 'print(1)'`: the `-S` skips site processing, so it succeeds
where the normal invocation hangs.

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
.venv/bin/python arranger.py corpus --melid 218 --musicxml head.musicxml   # optional extra
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
.venv/bin/pyright arranger.py tabstaff.py wjazzd.py tests   # or: make typecheck
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

**The head path shares the engine's step logic.** Only the *selection* is the loader's
business. The candidates come from `VoiceLeadingEngine.prepare_step`, which is also
what `arrange_progression` uses, and the choice is still the engine's `_best_voicing`
with `allowed_tones` supplied. This was not true until it was fixed: the loader used to
build candidates itself and call `_best_voicing` with only two arguments, which skipped
the non-chord-tone strategies, the tone-purity criterion and the `HIGH_FRET_LIMIT`
octave-down rescue. Across 25 transcriptions that left **0** non-chord tones flagged
where the library flagged 2,610, and 41.6% of steps sounding an inner voice outside the
written chord against 23.0%. The clearest single case is ATTYA bar 62, where a held C4
over `Bb-7` was voiced `x-0-2-0-1-x` — A2, E3, G3, C4, an Am7 sharing no pitch class at
all with Bbm7. It is now `x-4-6-5-x-x`, flagged `harmonized_as='Bbm9'`.
`tests/test_wjazzd.py::test_head_path_agrees_with_the_library_on_a_non_chord_tone` is
the regression test; without it this shipped unnoticed.

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
  `wjazzd` inside the branch. `headxml.head_cli` does the same, importing
  `argparse` *and* every renderer, so `load_musicxml` costs nothing.
- **Tests are guarded** by `skipUnless(DEFAULT_DB.is_file())` so the suite passes
  on a fresh clone with no 42 MB download. Tests needing no database (the
  notation table, the record types, the selector and range parsers) always run.

## Architecture / Key Types (`arranger.py`)

- `STANDARD_TUNING` — six open-string `Note`s, index `0` = low E (string 6)
  through index `5` = high E (string 1). `STRING_NAMES` mirrors these.
- `MELODY_STRING_CHOICES` — `(5, 4)`: the soprano string indices the *drop-2* path may
  be pinned to (`5` → D-G-B-E, `4` → A-D-G-B). Kept as the default of
  `get_drop2_voicings` so its published output is unchanged. Index `0` = low E ...
  `5` = high E, so the conventional guitar string number is `6 - index` (index
  `5` = string 1).
- `MELODY_STRING_CHOICES_FULL = (5, 4, 3)` — the default soprano set: the high E, the
  B **and the G** string. Adding the G string is what lets a melodic position be held
  by *changing strings* rather than by moving the hand. The A string and the low E are
  inner voices only; no grip puts the soprano on either, so the melody floor is `G3`
  while the chord range extends down to `E2` as a bass voice.
- `GRIP_PREFERENCE = ("drop2", "shell", "duo")` — the grip families and their
  tie-break order. `drop3` and `closed` are generated but deliberately **not** listed:
  neither can be played within `GRIP_MAX_SPAN` (see Known Limitations).
- `GRIP_STRING_SETS` — for each grip, its supported `(active string indices, soprano
  index)` pairs: the 4-3-2-1 and 5-4-3-2 four-string blocks, the five shell shapes
  (1-2-3, 2-3-4, 5-4-3, **6-4-3** and **5-3-2**), and three duos. `6-4-3` and `5-3-2`
  are the two non-contiguous sets, each skipping one inner string.
  `supported_string_sets()` is the playability invariant stated in
  one place, and adds the drop-2 blocks for all three sopranos (drop-2 is defined
  generically, so a caller passing their own `top_string` still works).
- `SHELL_DEGREES` — the (3rd, 7th) pair per quality, explicit rather than inferred:
  a quality not listed gets no shell rather than a guessed one. `DUO_DEGREES = (0, 7)`
  — the only soprano degrees a duo is generated for, as a hard rule.
- `NECK_FRET_MIN` / `NECK_FRET_MAX` — `2` and `13`. A strong preference, never a
  filter; see the selector below.
- `HIGH_FRET_LIMIT` — `13`. A melody whose only available position sits above this
  fret is re-voiced an octave down on the B string. See
  [High melodies move down an octave](#high-melodies-move-down-an-octave).
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
  `repeated` (default `False`) marks a step whose melody repeats the previous step's
  pitch **under an unchanged harmony**: the voicing is still generated in full, but the
  renderers show only the soprano and hold the inner voices. A repeat across a chord
  change is not a hold and is not marked. See
  [Repeated melodies hold the shape](#repeated-melodies-hold-the-shape).
- `format_progression(steps, vertical=False)` — module-level renderer for a
  whole arrangement: one line per step by default, six-line tab blocks when
  `vertical=True`. Non-chord-tone steps are annotated via the shared
  `_step_annotation()` helper, which `_print_step()` also uses so the two
  renderings cannot drift.
- `format_tab_staff`, `format_tab_html` and `write_tab_html` **live in
  `tabstaff.py`**, not here, and are re-exported below. See
  [The staff renderers live in `tabstaff.py`](#the-staff-renderers-live-in-tabstaffpy).
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
  - `get_grip_voicings(melody_note, chord_type, chord_name=None, top_string=5,
    grips=GRIP_PREFERENCE)` — candidates for one soprano string across every grip
    family, the general form of `get_drop2_voicings`.
  - `get_all_grip_voicings(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES_FULL, grips=GRIP_PREFERENCE)` — candidates
    across every allowed soprano string, high-E first, applying the chord-tone match
    then the quality-only fallback. **Pure**: it neither filters by fret nor
    transposes. `get_all_drop2_voicings` is this pinned to `grips=("drop2",)`.
  - `voicing_cost(voicing, previous, fret_min, fret_max, allowed_tones)` — the whole
    selection rule as one comparable tuple: notes outside the chord, then frets
    outside the window, then missing voices, then neck position (the difference of
    average frets from the previous voicing), then pitch movement, then span, then
    grip preference. Lexicographic, not a weighted sum, because these priorities must
    not be traded against each other. `_best_voicing` is its argmin and is stable, so
    the engine is deterministic.
  - `get_octave_down_candidates(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES)` — the same for the melody an octave lower,
    on the strings below the high E. Empty when the transposed melody is unvoiceable,
    so the caller keeps its original candidates.
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
  - `arrange_progression(progression, top_strings=MELODY_STRING_CHOICES_FULL,
    non_chord_tone="extension", fret_min=NECK_FRET_MIN, fret_max=NECK_FRET_MAX,
    grips=GRIP_PREFERENCE)` — voices each step, applying the selected non-chord-tone
    strategy where needed, and chooses each shape with `_best_voicing`. An unknown
    strategy raises `ValueError`. `grips=("drop2",)` with
    `top_strings=MELODY_STRING_CHOICES` reproduces the library's original output
    exactly, which is what the renderer tests pin their fixture to.
- `__version__` — the library version string (currently `0.6.0`). `pyproject.toml`
  reads it as the dynamic project version, so it is the single source of truth.
- `NO_CHORD` — the string `"NC"`, a bar carrying melody with no harmony.
- `VoiceLeadingEngine.get_melody_only_voicing(melody_note, prefer=...)` — a
  **single-fret** `Voicing` for an NC step, or `None` if unreachable. It is
  explicitly *not* a harmonised voicing and is exempt from the string-set invariant.
- `ArrangementStep.melody_only` — defaulted flag set on NC steps.
- `main()` — with no arguments, prints the built-in demonstrations; with `corpus`
  as the first argument, delegates to `wjazzd.corpus_cli` and with `head` to
  `headxml.head_cli`, both through a **lazy** import inside the branch, so
  `import arranger` never depends on the database module or the importer.
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
3. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`. This is also
   what `drop3`, `closed`, `shell` and `duo` build themselves from, so it is required
   for the new grips to reach the quality at all. If the quality should also get a
   shell, add it to `SHELL_DEGREES` — the default drop-2 and the derived grips work
   without one.
4. Add aliases to `ChordParser.QUALITY_ALIASES` (and, for backward compatibility,
   optionally to the `DROP2_INTERVAL_SETS[...] = ...` block).
5. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
6. **If the Weimar Jazz Database should be able to spell it**, add the matching
   suffix to `WEIMAR_QUALITY_ALIASES` in `wjazzd.py`. The database has 108
   distinct suffixes in its own notation, and one that is absent resolves to
   `None` and is *counted and reported* rather than guessed - so a new quality
   the corpus cannot reach is silent until this step is done.
7. **If a MusicXML file should be able to spell it**, add the matching
   `kind-value` to `MUSICXML_KIND_QUALITIES` in `headxml.py`, and any `<degree>`
   alteration that reaches it to `_DEGREE_REFINEMENTS`. The same rule applies: an
   absent kind resolves to `None` and is counted in `Head.unmapped`, so a new
   quality MusicXML cannot spell stays silent until this step is done. Note the
   table is keyed on the *library* quality, so a `kind` that only a `<degree>`
   reaches (a 7b5, say) needs a degree entry rather than a kind entry.
8. Add tests to `tests/test_voicings.py` for the drop-2 fingerings and to
   `tests/test_grips.py` for the other grips: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`, and the sounding strings
   a member of `supported_string_sets()`.
   `TestQualityTableInvariants` checks the template and degree lists stay the same
   length, and `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route. `tests/test_wjazzd.py` asserts every
   `WEIMAR_QUALITY_ALIASES` entry resolves to a quality the library can voice, so
   a table entry naming an unvoiceable quality fails the suite.
   `tests/test_headxml.py::TestChordParsing::test_every_kind_the_table_names_is_voiceable`
   is the same assertion for `MUSICXML_KIND_QUALITIES`.

## Coding Conventions

- Single-module design — keep new **engine** behavior in `arranger.py` unless the
  user asks to split it. The one exception is the staff renderers, which live in
  `tabstaff.py` (see below).
- `from __future__ import annotations` at the top; use `typing` aliases
  (`List`, `Optional`, `Tuple`, `Dict`, `Any`) consistent with the file.
- Dataclasses for value objects; `@staticmethod`/`@classmethod` for stateless
  logic on `GuitarFretboard`, `ChordParser`, and `VoiceLeadingEngine`.
- Preserve the dict-style `__getitem__` backward-compatibility shims on
  `Voicing` and `ArrangementStep`.
- Docstrings on public classes/methods; keep comments meaningful (they explain
  music-theory intent, e.g. which chord tone is in the top voice).
- Playability invariants that must hold for every generated voicing:
  - the sounding strings are exactly one `supported_string_sets()` entry — two to
    four strings, every other string muted (`-1`),
  - the melody is on that entry's soprano string, and is the highest sounding note,
  - `0 <= fret <= 18` and `fret_span() <= GRIP_MAX_SPAN[grip]` (5, or 4 for a duo).
    The span is checked on the frets actually placed, **not** as "within N of the
    soprano": those differ, and the second admits a span of ten.
  - every sounding pitch is a chord tone, except where the drop-2 tables have no
    inversion for the melody's degree and the quality-only fallback takes over (see
    Known Limitations). The selector's first cost criterion rejects such a shape
    whenever a correct one exists.
  - A melody below the high E string's open pitch (`E4`) produces no high-E
    candidates and is voiced lower; `top_strings=(5,)` restores the original
    high-E-only behaviour.
  - A melody whose best position is outside the neck window is voiced an octave
    down, so `step.melody` may be an octave below the written note (with the written
    pitch in `step.original_melody`). This only happens when it genuinely improves the
    placement, and the other invariants hold unchanged.
- **Do not add new third-party dependencies** without explicit approval;
  `musthe` is the only one in use.

## The staff renderers live in `tabstaff.py`

`format_tab_staff`, `format_tab_html` and `write_tab_html` are the renderers that
lay an arrangement along **one staff in reading order**, and they were split out of
`arranger.py` so the engine can be read without them. `format_progression` (one
line or one block *per chord*) and the vertical `tab_block()` stay in
`arranger.py`: they are a different shape of output, and `Voicing.tab_block()` is
called from the dataclass itself.

**They are split together, never separately**, because the two renderings share
`_staff_columns` — which places each step on an absolute beat and decides what is a
strike and what is a hold. That sharing is not incidental duplication to be tidied
away: it is *why* the two grids agree on where a chord sits and what counts as a
hold. Splitting the HTML half alone would have forced that shared core to be
duplicated or imported across the boundary.
`TestTabstaffModuleBoundary::test_tabstaff_shares_the_layout_core` guards it.

| name | role |
|---|---|
| `tabstaff.format_tab_staff` | the ASCII staff, for a terminal |
| `tabstaff.format_tab_html` | a self-contained HTML page for a browser |
| `tabstaff.write_tab_html` | the only function in the module that touches the filesystem |
| `_staff_columns` / `_staff_breaks` | the shared layout core, both renderers call these |
| `_carries_melody` | which strings carry the melody, for the `*` marker |

`format_musicxml` and `write_musicxml` are the same rendering decision in a different
medium, and they live in `tabxml.py` rather than here — see
[MusicXML export](#musicxml-export). `format_gp5` and `write_gp5` are the same again
in a third medium and live in `tabgp.py` — see
[Guitar Pro 5 export](#guitar-pro-5-export). `tabstaff` re-exports all four, so
there is still one spelling for the whole staff-rendering surface.

**The dependency is one-way: `tabstaff` imports `arranger`, never the reverse.** It
takes `STRING_NAMES`, `ArrangementStep` and `_MUTED_CELL` from here; the last of
those stays put because `Voicing.tab_block()` and `format_progression` use it too.

### The re-export is lazy, and has to be

`from arranger import format_tab_html` still works — the README, the tests and
`wjazzd` all spell it that way — but `arranger` does **not** import `tabstaff` at
the top. A top-level (or even bottom-of-file) import would be a genuine cycle:
importing `tabstaff` first would re-enter a half-initialised `arranger` and fail to
find the names. So `arranger` exposes them through a **module-level `__getattr__`**
(PEP 562), which resolves each name on first access.

Two consequences worth knowing:

- **A `TYPE_CHECKING` import** in `arranger.py` gives the type checker and IDEs the
  real declarations, since a checker cannot follow `__getattr__`. Without it pyright
  reports the names as "not present in module". The same import is in `tabstaff.py`
  for the two `tabxml` names, and without it pyright flags their `__all__` entries.
- **`__all__` is an explicit list**, not computed from `globals()`. It had to be
  added: the module never had one, so `from arranger import *` used to export every
  public name, and the lazy `__getattr__` hides the re-exported ones from a star
  import. `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface`
  fails if the list and the module's public names diverge, in either direction. It is
  spelled as one literal in both modules rather than with `+=`, which a checker
  cannot follow either.

## MusicXML import

`headxml` is the counterpart to `tabxml`: it reads a written head — a melody plus
chord symbols — out of a MusicXML file and arranges it. `arranger.py head FILE`
is its front end.

**It needs no optional dependency.** `zipfile` and `xml.etree` are enough for both
forms of the format, so a plain `pip install jazz-arranger` can import a head and
`tests/test_headxml.py` needs no `skipUnless` guard at all. That asymmetry with
the exporter is deliberate and is the reason the two are separate modules rather
than two halves of one.

**Its four test scores are committed in `tests/data/`, and are not guarded.** A
hand-built fixture proves the parser agrees with itself; only a file written by
music21, MuseScore or this library's own exporter proves it reads what a notation
program actually writes. They are excepted from the `*.musicxml` / `*.mxl` rules
in `.gitignore` — which exist for *export output* — and a missing fixture is a
broken checkout, not a reason to pass quietly. `tenor_madness.musicxml` is 528 KB
and the largest of them; it earns its place by being the only two-part score,
which is what makes the TAB-staff part-selection test possible.

| name | role |
|---|---|
| `MUSICXML_KIND_QUALITIES` | `kind-value` → library quality; the inverse of `tabxml._READABLE_KINDS` |
| `_DEGREE_REFINEMENTS` | `(quality, degree, alter) → quality`, for the alterations a kind cannot name |
| `parse_musicxml_chord(harmony)` | → `(root, quality, bass)`; `None` for a chord that cannot be voiced |
| `Head` / `HeadNote` | the loaded melody, its timing, and each note's chord |
| `load_musicxml(path, part=None)` | `.mxl` or `.musicxml` → `Head` |
| `head_skeleton(head, strategy, section, pick)` | slots of `(triple, bar, beat, duration)` |
| `arrange_xml_head(path, …)` | the whole pipeline → steps, the `Head`, and diagnostics |
| `head_cli(argv)` | the `head` command |

Six decisions are load-bearing, and each was forced by a real file:

- **The harmony is a timeline, not a per-note attribute.** A `<harmony>` precedes
  the note it governs, several can share a bar, and a bar can carry none at all —
  But Not For Me bars 3 and 5 carry no harmony, and Rainy Day bar 1 changes twice
  inside the bar. So a chord is **held** from the note it is declared before until
  the next replaces it, the same forward fill `wjazzd` applies to the `beats`
  table. Reading the chord off the following note would drop the harmony from
  every bar that does not change.
- **A `.mxl` is read through `META-INF/container.xml`,** which names the root
  file. "The first `.xml` in the archive" looks equivalent and is not: a container
  may carry a `score.xml` beside a stylesheet or a thumbnail, and picking the
  wrong one is a *silent* failure. The largest XML member is the fallback when the
  container is missing; a non-zip is read as a bare document.
- **The metre is the notated one.** `beat` is the beat within the bar in notated
  beats, so `1 + onset/divisions * beats_per_bar / 4`. Dividing by four is what
  makes a 2/2 bar two beats wide — a quarter note in cut time is on beat 1.5, not
  beat 3 — and three of the four scores in the repository are in cut time. The
  `<time>` read is the **last** one stated, since a score may change metre.

### A beat is not a quarter note

Cut time is where every metre assumption in this library comes apart, and it did so
three separate times in one review of `but_not_for_me.mxl` — a music21-written
**2/2** head whose `<time symbol="cut">` is the only signature in the file. The
tune *sounds* like common time and is written with a quarter-note pulse, which is
exactly why it is easy to assume 4/4 and wrong to: the file says 2/2, and the
loader is right to read it that way. The bar is four quarters long either way; only
the *counting* differs.

**A beat is `4 / beat_type` quarters long, and a bar is `beats_per_bar` of them.**
The divisor is the load-bearing part: a 2/2 beat is a **half** note, so two
quarters, not `2/4` of one. Every renderer needs both numbers, and reading the
beat count as a quarter count is what each of the four bugs below was:

| where | was | cost |
|---|---|---|
| `headxml._slot_key` | clamped a slot to `beats_per_bar` | **13 of 80 notes lost.** A 2/2 bar's eighths run 1.0 … **2.5**; clamping to 2.0 folded the last eighth of every bar onto beat 2, where it collided and was dropped by `pick` |
| `head_cli` → the file writers | passed no metre at all | both writers used their own `beats_per_bar=4`, so a 2/2 head was written as 4/4 on the wrong grid |
| `tabxml._events`, `tabgp._measures` | `4.0 / beats_per_bar`, `bar_length = beats_per_bar` | a cut-time beat measured as half a quarter, so every bar came out half length — 32 measures written as 64 |
| the same two, *after* the fix above | `beat_type / 4` instead of `4 / beat_type` | **every bar a quarter note long.** The measure *count* stayed right, because onsets are placed in beats and that part was correct — so 32 short bars under a 2/2 signature, each holding a quarter of the music it claimed |

That last one is the instructive one, and it is worth stating as a rule of thumb:
**4/4 cannot catch it.** Both readings of the fraction give 1 quarter to the beat
in 4/4, so the whole suite passed with the file unusable for every other metre.
A test that asserts the measure *count* cannot catch it either, for the same
reason - the count was right. The check that catches it is summing each
measure's durations back to a bar length, which is what
`GuitarProTestCase.bar_quarters` and
`test_every_measure_of_a_written_head_fills_its_bar` do.

So `beat_type` is now a parameter of `format_musicxml` and `format_gp5` (and of
`_events`, `_measures`, `_build_part`, `_build_song`), it is what makes a 2/2 head
read as **2/2 rather than 2/4** in the file, and `head_cli` passes
`head.beats_per_bar` and `head.beat_type` to every renderer. `tabstaff` needs
neither: it works in *beats* throughout and never converts to a length.

### A rest is not a note, but it is time

The same review turned up a bug that has nothing to do with the metre, and it is
worth stating separately because it is the one a musician hears first.

Bar 1 of `but_not_for_me.mxl` is **a quarter rest followed by three quarter
notes**. `_read_notes` skipped the rest — correctly, it is not melody — but
skipped it with a bare `continue`, so **the cursor never moved past it**. Every
note in the file after that rest was read a beat early: the F4 landed on beat 1.0
instead of 1.5, the head appeared to begin on a downbeat, and the GP5 bar was
written as three chords filling a bar the score says is a rest and three.

The general rule is that *every* element the loader steps over has to be asked
whether it occupies time, and a rest does:

| element | advances the cursor? |
|---|---|
| a rest | **yes** — it is a `<duration>` like any other |
| a cue note | **yes** — it sounds in another part, and time passes |
| a grace note | **no** — it borrows the length of the note it decorates, so adding it would count that note twice |
| a lower voice of a `<chord>` group | no — the group's unmarked member carries the length |

This is a different failure from the metre one and a nastier one to spot, because
every bar is still exactly full afterwards: the music is simply a beat out, and
the error survives any test that only checks bar lengths. The test that catches it
is reading the *first note's own beat* off the committed file, which is
`test_a_cut_time_head_opens_on_the_beat_its_first_note_is_written_on`.

Fixing it exposed a second one, in the renderer rather than the loader. GP5 has
no anacrusis, and `tabgp._measures` represented a pickup by opening an **empty**
first measure and dropping it again at the end - which is not a representation of a
pickup, it is its deletion, and the music after it slid forward by the length of
the rest to fill the gap. It is now a **rest beat** at the head of the first
measure, with the cursor offset to follow it, so the bar is full *and* the music
sits where the score puts it. A knock-on effect worth knowing: a note that used to
be split across a bar line is often no longer split, because the rest is time
rather than a hole. `test_a_step_crossing_a_bar_line_is_split_not_stretched` pins
the new placement, and `test_a_long_step_is_split_across_a_bar_line_rather_than_stretched`
covers the split itself without a pickup in the way.

`_slot_key`'s clamp is now `beats_per_bar + 1 - grid` — the last grid position
**inside** the bar — rather than `beats_per_bar`. It still catches what it was
written to catch (a note that rounds onto the bar line is pulled back), which is
what `test_a_bar_line_overflow_is_still_pulled_back_inside` pins, because a fix
that kept those notes must not lose the protection.

The general lesson, and the one to apply to the next importer: **a count without a
denominator is not a metre.** 2/2 and 2/4 are both two beats to the bar, so
`beats_per_bar` alone cannot say which - which is why `Head` carries `beat_type`
and why it is now plumbed all the way to the file headers.

- **A `<chord>` group reduces to its highest note.** MusicXML does not order a
  group by pitch: only the first member is unmarked, and in a chord-melody part
  that member is the *lowest* note of the shape. Taking the maximum is what makes
  the reduction independent of how the writer ordered the notes, and it is what
  lets this library read back its own two-part export with the TAB staff skipped.
- **`<degree>` is how a chord its `kind` cannot name is spelled** — a `dominant`
  with a flat 5th is a 7b5, which is exactly how MuseScore writes one, and "Here's
  That Rainy Day" is a third of an E7b5 under an F melody line. The degrees are
  applied **in document order, each refining the last**, so the table keys off the
  *result* of the previous degree as well as the base kind. The `text` attribute
  is the final fallback and the inverse of `tabxml._downgrade_kinds`: that pass
  writes an unclassifiable chord as `<kind text="Bb7sus4">other</kind>`, so
  without reading `text` back a round trip of this library's own export would lose
  every chord it could not spell.
- **A tuplet's `<duration>` is unreduced** and must be divided by
  `time-modification`, or every bar after the first drifts a third long.
  "I Was Doing All Right" is written in triplets at 10080 divisions and is the
  test for it.

**Never guess a chord.** A kind the library cannot voice is absent from
`MUSICXML_KIND_QUALITIES` rather than folded into a near neighbour —
`Neapolitan`, `Italian`, `French`, `German`, `pedal`, `power`, `Tristan` and
`none` are all real MusicXML kinds and all absent — and it is counted in
`Head.unmapped` and printed, on the same principle as
`WEIMAR_QUALITY_ALIASES`. A quality naming a chord the voicing tables do not hold
is reported as untranslatable rather than failing silently later.

**The voicings are not re-implemented here.** `arrange_xml_head` hands its slots
to `wjazzd.arrange_slots`, the step loop promoted out of `wjazzd.arrange_head` for
exactly this. An imported head therefore gets the same non-chord-tone strategies,
the same opt-in dim7 retry, the same `repeated` hold and the same slash-bass rule
as one read from the database. A second implementation of the step loop is how
the corpus path came to disagree with the library once already; the whole point of
the extraction is that it cannot happen again.

**Imports are lazy where they keep the module cheap** — `argparse` inside
`head_cli`, and the renderers inside it too, so `load_musicxml` costs nothing.
`main()` imports `headxml` inside the `head` branch, as it does `wjazzd`.


`format_musicxml` / `write_musicxml` in `tabxml.py` render an arrangement as a
`score-partwise` document for a notation program. It is a **third renderer family**,
not a third column: it is the only one that needs a dependency, and the only one that
has to be post-processed before it is correct.

| name | role |
|---|---|
| `tabxml.format_musicxml` | the document, as a string. Pure, like every other renderer |
| `tabxml.write_musicxml` | the only function in the module that touches the filesystem |
| `_events` / `_is_hold` | placement, durations and the pickup; the rhythmic core |
| `_build_part` | the staff: measures, notes, ties, chord symbols |
| `_chord_symbol` | a symbol, or a text-only one for a name music21 rejects |
| `_drop_empty_inversions` | removes the meaningless `<inversion>-1</inversion>` |
| `_downgrade_kinds` | rewrites a `<kind>` value MusicXML 3.1 does not have |

**There is no TAB staff, deliberately.** This was a measured decision, not a
simplification. music21 cannot write a TAB staff a notation program renders
correctly: it emits neither the `<staff-lines>6</staff-lines>` a tab staff needs nor a
fret and string for each note *inside* a chord - it puts them all on the chord's first
note (cuthbertLab/music21#1534). Both were patched back in afterwards, and the patched
document **still did not display correctly in MuseScore 3**. A workaround that does not
work costs more than not shipping it, so `tabxml` writes a **notation staff only** and
`tabgp` writes the fretting, as a Guitar Pro 5 file. The two are divided by what each
format can do: GP5 stores a fret and a string per note natively, MusicXML reaches
Sibelius, MuseScore and Final. Everything that is genuinely *shared* - `_events`,
`_is_hold`, `_substitute_steps` - is still shared, so a head lands on the same beats in
both files.

Four decisions in here were each forced by a failure, not chosen:

- **The document is post-processed with `ElementTree` after music21 writes it** - for
  `_drop_empty_inversions` and `_downgrade_kinds`, and `_unique_instrument_ids`. The
  two passes that used to repair a tab staff are gone with it.
- **Steps are placed by `tabxml`, not by `tabstaff._staff_columns`.** The column grid
  is deliberately lossy - two steps on one onset collapse into one column, "the first
  step in a column owns that column" - which is right for a fixed-width ASCII staff
  and wrong for a score. The eighth-note skeleton puts two steps on the last beat of
  most bars, so sharing the grid would drop a chord from every bar of a head. What is
  shared is the *semantics*: absolute onsets with signed bars, and collapse on
  unchanged sounding pitches.
- **Steps sharing an onset divide their span equally**, and the transcribed
  `duration` is not used as a weight. It is the length of the *melody note* the step
  came from, which runs past the onset, and the corpus's values are arbitrary
  fractions of a whole note; scaling by them yields note values music21 refuses to
  write, and it refuses the **whole export** rather than rounding one. Two eighths on
  the last beat of a bar are two eighths.
- **Only the first measure carries the time signature.** MusicXML says a signature
  holds until it changes, so repeating it in every bar is legal but reads as a new one
  at each: MuseScore 3 draws a 4/4 over every bar of the head. This replaced a
  deliberate per-measure repetition, whose stated reason was that music21 needs a
  signature in each measure to pad and tie the bar. **That reason was measured and is
  false** - music21 resolves each measure against the signature already in force, and
  the export does not touch `makeRests` without one. Eight corpus heads, plus pickups,
  bar-line crossings and rests, all re-parse with every bar the right length.
  `tests/test_musicxml.py::test_the_time_signature_is_written_once` is the regression.

Two more are worth stating because they look like bugs otherwise:

- `Measure.padAsAnacrusis` is a **method**, not a flag. Assigning to it silently does
  nothing, and a pickup written as a full bar is a bar of wrong music.
- An event that runs across a bar line is **tied**, not stretched. A note cannot cross
  a bar line in MusicXML, and a measure holding more than its time signature is not a
  measure, so the renderer cuts it and ties the halves. The written rhythm survives
  even where the transcription's phrasing disagrees with the metre.

**Dependencies and the optional extra.** `music21` is the single exception to the
musthe-only rule, and it is opt-in: `pip install 'jazz-arranger[xml]'`. `_music21()`
imports it inside the functions and rewrites the `ImportError` into a message naming
that install command, so `import arranger`, the ASCII staff and the HTML page all work
without it, and `corpus_cli` reports the missing extra as a usage message rather than a
traceback.

**A chord name music21 cannot classify is written, not dropped.** `mMaj7`, `maj9` and
`7alt` are among the ones it rejects, and the Weimar notation produces more
(`Bb7sus4`). `_chord_symbol` falls back to `<kind text="...">other</kind>` with the
root still parsed out by `ChordParser`, which is how MusicXML spells a symbol whose
type the writer does not recognise.

**The output is valid MusicXML 3.1, not just 4.0.**

`kind-value` is a **closed enumeration**, and music21 writes MusicXML 4.0, which
extended it. `suspended-fourth-seventh` is the value that actually bites: MuseScore 3
refuses to open the file at all, with

```
Content of element kind does not match its type definition:
String content is not listed in the enumeration facet.
```

One chord costs the whole document, because the reader rejects the file rather than
the symbol.

`converter.parse()` **cannot see this** - music21 both writes the 4.0 value and reads
it back - and neither could any test asserting on the music21 objects. It is the second
consecutive defect of that shape, the first being the duplicate part-list instrument
id, so `tests/test_musicxml.py::TestMusicXML31Kinds` asserts on the **document**: every
`<kind>` value in it is in `_READABLE_KINDS`. A 3.1-legal file is also 4.0-legal, so
this costs nothing against the DOCTYPE and maximises what imports.

`_downgrade_kinds` runs last, as a compatibility filter over the finished document,
and rewrites in two steps:

- **the spec's own spelling** - `suspended-fourth-seventh` becomes `suspended-fourth`
  plus a `<degree>` adding the 7th. 3.1 has no kind for the combination, but it does
  have the `add`-degree idiom for a harmony expressed as a base kind plus alterations,
  so the chord still arrives as a classified symbol. `_SUS_KINDS` holds the mapping;
- **`other` with the analyst's text**, the same fallback `_chord_symbol` uses. This is
  the backstop for any value not in the table, and it is why the pass generalises to
  kinds nobody has hit yet.

The `<root>` is never touched, and on a document that only uses 3.1 kinds the pass is
a no-op - `test_an_ordinary_progression_is_untouched` asserts the document is
byte-identical afterwards, because a filter that degrades a working file is worse than
the bug.

**Open, and worth doing next: validate against the actual XSD.** `xmlschema` as a
**dev-only** tool (like pyright, never a runtime dependency and not in the `xml` extra)
would catch this whole class - MusicXML-level errors invisible to a round trip. It
means vendoring the 3.1 XSD into `tests/` and skipping when absent, in the same
`skipUnless` spirit as the `wjazzd.db` tests.

**Known limitations.** Durations are floored at a sixteenth, because MusicXML cannot
write less and music21 aborts rather than rounding; nothing this library generates is
shorter than an eighth. A triplet onset that does not divide the bar evenly would hit
the same wall - untested. The provenance notes the HTML page carries (`notes=`) are
not written into the score.
- **`__all__` is an explicit list**, not computed from `globals()`. It had to be
  added: the module never had one, so `from arranger import *` used to export every
  public name, and the lazy `__getattr__` hides the re-exported ones from a star
  import. `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface`
  fails if the list and the module's public names diverge, in either direction.
## Guitar Pro 5 export

`format_gp5` / `write_gp5` in `tabgp.py` render an arrangement as a **Guitar Pro 5
file**. It is a **third renderer family**, beside the ASCII/HTML staff and the
MusicXML score, and it is **not a replacement for MusicXML** — see below.

| name | role |
|---|---|
| `tabgp.format_gp5` | the file, as bytes. Pure, like every other renderer |
| `tabgp.write_gp5` | the only function in the module that touches the filesystem |
| `tabgp._guitarpro` | the lazy import, mirroring `tabxml._music21` |
| `_measures` | events to measures of beats; where GP5 and MusicXML differ |
| `_build_song` | the guitarpro `Song` |
| `_duration_split` | a quarter-length to the `Duration` + `Tuplet` that sum to it |
| `_sounding_frets` | which strings a step plays; a repeated melody is one note |
| `GP_VERSION` / `GP_SIGNATURE` | `(5, 1, 0)` and the file header it writes |

**Why a third renderer rather than a replacement.** GP5 is a *tab* format, so it
stores a fret and a string per note natively and a shape survives the round trip
exactly — which is why the mapping here is a few lines with no post-processing at
all. That is not merely tidier than the MusicXML tab staff used to be: it is the
**only** one that works, since music21 cannot write a tab staff a notation program
renders correctly (see [MusicXML export](#musicxml-export)). So the division is now
by capability, not by preference: GP5 carries the fingering, MusicXML carries the
notation, and neither renderer tries to do the other's job. But GP5 opens in Guitar
Pro and nowhere else, has no notation staff, and is a closed format. MusicXML remains
the way into Sibelius, MuseScore and Final. Both are shipped, and both are one flag
on `corpus_cli` (`--musicxml`, `--gp5`).

**What is shared, deliberately.** `tabgp` calls `tabxml._events` and
`tabxml._substitute_steps` rather than reimplementing either, so a head lands on the
same beats in both files and a substituted chord is named the same way in both.
That is the *semantics*; the bar grid is separate, for the reason below.

### Where GP5 genuinely differs from MusicXML
`tabxml._build_part` writes a **short first measure** for a head with an anacrusis,
because MusicXML has an anacrusis. A GP5 measure is a fixed-length container and the
format cannot say "this bar is only two beats long", so `_measures` writes a **full
first measure with the leading beats empty** and the music begins on the following
downbeat. That moves every onset later rather than reshaping the metre — the lesser
of the two distortions, since the notes and their order are untouched.

Two more consequences of a fixed-length measure:

- **An event crossing a bar line is split**, written as two notes in consecutive
  measures. The second half is written with `NoteType.tie`, so the two are one held
  note rather than the shape struck twice. This was wrong until it was measured:
  the code believed a GP tie was "a slur the player has to interpret" and wrote both
  halves as plain notes, which re-struck the shape at the head of every bar a step
  crossed - **14 of the 32 bars** of "But Not For Me", whose score genuinely ties
  Eb4 across the bar line in bars 2-3. `NoteType.tie` is a real GP5 tie and
  round-trips through PyGuitarPro 0.11.
  `test_a_held_shape_is_tied_across_a_bar_line_not_re_struck` and
  `test_every_split_step_in_a_written_head_is_tied` are the regressions; the second
  measures it over the real head, because a hand-built fixture finds the mechanism
  while an export can still be full of instances.
- **A measure opens when the cursor *reaches* a bar line**, not only when a step
  *crosses* one. Testing only for a crossing was a real bug found by the eighth-note
  case: beats landing exactly on the boundary all piled into the first bar, so a
  two-bar head came out as one eight-beat bar.
- **A beat with no notes must say `BeatStatus.rest`.** `gp3.writeBeat` only emits
  the status byte when the status is not `normal` (`if beat.status !=
  gp.BeatStatus.normal: flags |= 0x40`), so a note-less beat marked `normal` goes
  out as an *ordinary* beat whose string-flags byte is empty — indistinguishable
  from a chord on no strings rather than a rest. MuseScore 3 reads that as a rest
  in the right place; **TuxGuitar does not**, and puts the pickup rest on the 4th
  quarter rather than the 1st. This is the one defect so far that two readers
  disagree about, which is what made it findable: the file is self-consistent, so
  the round trip through PyGuitarPro passes while a notation program misplaces the
  rest. `BeatStatus.rest` is the third member of the enum (`empty`/`normal`/`rest`)
  and was simply never used.
  `test_a_rest_beat_is_marked_as_a_rest_not_as_an_empty_chord` and
  `test_every_note_less_beat_in_a_written_head_is_a_rest` are the regressions. The
  first asserts on the **parsed-back status** rather than on the beat having no
  notes, which is what the earlier test did and which this defect passes.

### Two things the format cannot express, found by TuxGuitar

TuxGuitar rejected a written head with `voice 1 is too long` on three measures of
*Blue Train* and one each of two *All the Things You Are* transcriptions. Both causes
are in `_duration_split`, and **both are silent** — the file writes cleanly and is
only wrong on read, so nothing in the round-trip test caught them until a real
notation program was run against the output.

- **A duration is a power of two, and there is no dotted note.** The value is
  written as `value.bit_length() - 3` and read back as `1 << (n + 2)`, so a length
  that is not a power of two has to be *split*, not rounded. A dotted half (3
  quarters) rounded to the nearest legal value is a **whole note** — a quarter too
  long, and a bar summing to more than its 4/4 signature. It is now written as a
  half plus a quarter.
- **A triplet is a `Tuplet`, not a `Duration` of 12.** `12.bit_length() - 3` is 1,
  so a bare `Duration(12)` is written as an **eighth** and reads back as one. Every
  triplet in a head silently became an eighth, and the bar went a quarter long. A
  triplet eighth is `Duration(8)` with `Tuplet(3, 2)`.

The rule is the one `test_no_written_bar_is_longer_than_its_time_signature` states:
**the parts must sum to the length asked for.** A split may leave a bar slightly
short, which a reader tolerates; it must never be long, which a reader rejects.
`_duration_split` therefore only ever takes parts that *fit*, and reaches for a
triplet only once no plain note does — so a dotted half stays a half and a quarter
rather than becoming three triplet eighths.

**A sliver the format cannot express is dropped, not padded.** The code once closed a
leftover remainder by appending the shortest legal note, reasoning that a short bar
"silently loses music". That is backwards: the music is not lost, the bar is merely
a hair long, and a bar that overruns its signature is **rejected**. It was reached
by the gap-as-rest work in the next section — a `1/6`-quarter rest, which is a
triplet-eighth divided by the onset, leaves a remainder no single note covers, and
the appended sixteenth made bar 2 of the Weimar head 4.92 quarters of 4.
`test_a_length_the_format_cannot_exact_is_written_short_never_long` is the direct
regression, asserting the ceiling over the exact and the inexpressible alike.

### A gap between two notes is a rest, not a held chord

The harmony is a timeline, not a per-note attribute. **The rhythm is
one too, and a rest is time.** Bar 4 of "But Not For Me" is a single whole note and
bar 5 opens with a quarter rest, so the gap from the note to the next onset is five
quarters while the note is written for four. The span a step is given is the gap to
the *next sound*, which is not the same as how long it *sounds* — so the note was
held over the silence into the next bar, and since a step crossing a bar line is
tied, the bar opened with a tied chord where the score says a rest. The eighth-note
skeleton puts a rest at the head of every second bar, so this was not one bar but
half the head.

`tabxml._events` therefore **caps** the span at the melody note's own `duration` and
writes the remainder as an explicit rest — a `(None, False, length)` event, which is
already what all three renderers read as "nothing here" (`tabxml` writes a
`<rest>`, `tabstaff` blanks the cell and clears the ring, `tabgp` writes
`BeatStatus.rest`). Three properties of the fix are load-bearing, and each was a
real failure:

- **It is a cap, never a substitute.** A `duration` longer than the gap is ignored,
  so no step is ever *stretched*, and a step with no `duration` at all keeps the
  whole-gap behaviour — which is what the renderers' uniform-grid fallback relies
  on. This is why the gap rule exists in the first place: `duration` is a fraction
  of a whole note that music21 cannot always write.
- **The last group is exempt.** It runs to the end of its own bar by definition, so
  there is no gap to represent and a cap would only invent a rest at the end.
- **The rest is measured after the sixteenth floor**, from what the group *wrote*
  rather than from the cap. The floor can make a group longer than the cap, and
  taking the rest from the cap would then add the two and overrun the bar.

`test_a_gap_between_notes_is_a_rest_not_a_held_chord` and its two companions — one
for the no-gap direction, one for a step with no timing — are the regressions.

### Six undocumented traps, each found by a failed round trip

None is in PyGuitarPro's documentation, all of them look innocent, and **every one
is a silent corruption rather than an exception** — the file writes without
complaint and is unreadable. They are recorded in `tabgp`'s module docstring, and
repeated here because the test that catches them is the one thing not to weaken:

- **`Song()` already contains one `MeasureHeader` and one `Track`.** Appending
  another yields a file that reads back as an extra track. Use `tracks[0]` and
  `measureHeaders[0]`.
- **`Measure.maxVoices` is 2 and the writer emits every voice.** A one-voice measure
  desyncs the byte stream; the reader fails much later with an unrelated-looking
  `count must be less than or equal than 255`.
- **`Beat.status` defaults to `BeatStatus.empty`,** which occupies *zero* duration.
  A beat that is meant to sound must say `BeatStatus.normal`.
- **Strings are numbered 1–6 with 1 = high E.** This library indexes 0 = low E, so
  the conversion is `6 - index` — the same flip `tabxml` makes.
- **`Chord` is a chord *diagram*, not a shape.** It holds a name, a root and a fret
  vector for the little box above the staff. A played shape is several `Note`s on one
  `Beat`, `Note.value` being the fret. Using `Chord` for the shape is the obvious
  mistake and writes a box rather than a chord.

### Why the test suite round-trips

`tests/test_guitarpro.py` writes the file, parses it back with `guitarpro.parse`, and
compares the notes against `step.voicing.frets`. That is the whole point: a GP file's
only contract is that Guitar Pro can open it, and every trap above produces a file
that passes any assertion on the builder's own output while being unusable. A parse
is the closest proxy available without Guitar Pro itself. `test_every_shape_survives_the_round_trip`
is the one that matters.

**Known limitation.** `PyGuitarPro` 0.11 writes GP3/GP4/GP5/TGP; GP5 is the newest it
supports. Guitar Pro 7+ `.gp` is a different, zip-based format that nothing here can
write, so a file from this renderer targets Guitar Pro 5 and 6 as well as anything
later that still reads GP5.



## Grips, and the position-aware selector

The engine generates several grip families and then chooses between them, rather than
generating one kind and voice-leading it. Generation and selection are deliberately
separate: `get_grip_voicings` and `get_all_grip_voicings` are *pure* (no position
filtering, no transposition) and `_best_voicing` does all the deciding. That split is
what stops the grip families and the octave-down rescue from having to know about each
other, and it is asserted in `tests/test_grips.py`.

| grip | voices | how it is built |
|---|---|---|
| `drop2` | 4 | `DROP2_INTERVAL_SETS`, verbatim — the tables are hand-authored |
| `drop3` / `closed` | 4 | derived from a close stack; generated, not offered by default |
| `shell` | 3 | `SHELL_DEGREES` plus one more note |
| `duo` | 2 | root or 5th in the melody plus the 3rd |

Four decisions in here were each forced by something measurable:

- **drop-2's tables are never derived.** The extended qualities are voiced *rootless*
  on purpose, so a 9 or a 13 that fits in four voices without the root is a musical
  decision. Deriving drop-3 and close position from the same chord tones gives a
  *fuller* chord — a legitimate but different voicing — which is exactly why drop-2 is
  left alone.
- **Duos are a hard rule, not a cost preference.** Under a root or 5th the ear supplies
  the guide tones, so two notes carry the harmony; under a 3rd or 7th they *are* the
  chord's function and a bare duo there is the voicing that sounds wrong. So
  `get_grip_voicings` returns nothing for those, with no escape hatch. The test that
  pins this is `TestDuoHardRule`, because a 3/7 duo consists of genuine chord tones and
  the "only chord tones" check would not catch it.
- **A shell is searched for, never stacked.** A shell's notes are not in descending pitch
  order down the strings, because the tuning is not monotonic in the useful direction: the
  A string is tuned five semitones *above* the D string. A G7 shell under G3 is
  `2-3-0-x-x-x` — B2 on the A string, F3 on the D string, G3 on the G — where the A string
  carries the *lower* note while being the higher string; Gm7 in 6-4-3 is `3-x-3-3-x-x`,
  with G3 on the D string below A2 on the low E. A model that stacks voices by pitch gets
  both backwards and finds nothing, so `_place_shell` holds the melody and searches every
  combination of frets inside the span limit. That makes the search *exhaustive within the
  playability invariant*: if a playable shell exists in that position, it is found.
- **No four-note voicing on 6-5-4-3.** A G-string soprano has no four-note block, because
  the only one available is all of the four lowest strings and that does not sound good —
  four voices in the bottom fourth of the compass. A low melody is harmonised with a
  three-note shell (5-4-3 or 6-4-3) instead, dropping the 5th degree. Stated in one
  place, `_BOTTOM_FOUR`, and asserted by `TestStringSetTable`.
- **A partial harmonisation is a fallback, not a style.** `missing` voices outranks neck
  position in the cost, so a complete chord wins even when a shell would have held the
  position better. A permitted root-or-5th duo scores zero there and competes on equal
  terms; a shell scores one; a bare 3/7 duo is not generated at all.

The window is a **penalty, not a filter**: a step with no voicing inside frets 2–13 is
still played, just outside it. A filter would silently drop every step whose melody
has no in-window shape, and losing a chord of the tune is worse than being a fret out
of position. `tests/test_grips.py::TestFretWindow` pins that.

## Repeated melodies hold the shape

When a step's melody sounds the same pitch as the step before it **and the harmony
under it is unchanged**, the step is played as a **single note**: the soprano string is
struck alone and every other string is left blank. Restriking the whole chord is harder
than the music needs, and it is how a player actually reads a held melody.

The Weimar transcription of "All the Things You Are" is the motivating case: at bars
61–63 it holds C4 across three chord changes (F-7, Bb-7, Eb7). The repeated Eb7 is a
genuine hold — one strike, then the note alone. The two *changes* underneath it are not.

The decision is deliberately **presentational, not a voicing change**:

- `arrange_progression` still generates a full `Voicing` for every step. The
  engine voice-leads from it, `midi_notes()` reports it, and a caller wanting the
  literal shape still has it via `step.tab_line()`. What changes is that
  `ArrangementStep.repeated` is set, and the renderers honour it.
- The flag is set by comparing **sounding pitches** (`max(midi_notes())`), not written
  note names, because either step may itself have been transposed down an octave by
  the `HIGH_FRET_LIMIT` rule. A run of four identical notes under one chord yields
  `[False, True, True, True]`.
- **The harmony must also be unchanged.** A note repeating across a *chord change* is
  not a hold: the ringing inner voices belong to the chord the hold began on, so
  printing the new chord's name over a single struck note claims a harmony that is not
  sounding. Those steps are harmonised against the new chord and struck in full, which
  is what the engine already does — only the rendering used to discard it.
  `normalised_harmony()` supplies the comparison: `harmonized_as` when a strategy
  substituted a chord, otherwise the written name, canonicalised to `(root, quality)`
  so `D-7` and `Dm7` are one chord rather than two. The `-7` suffix is an alias of
  `m7` for exactly this reason.
- A **melody-only (`NC`) step is never marked repeated**: it has one active fret and
  no inner voices to hold, so the flag would mean nothing.
- `collapse` in the staff renderer compares sounding pitches, so an unchanged shape
  is normally suppressed entirely as a *hold*. A repeated step overrides that and still
  strikes, because the melody is genuinely re-articulated.
- `_step_annotation()` adds `(melody repeated - single note)`, because the
  chord name printed above a single note would otherwise imply a full voicing. The
  annotation is shared with `format_progression`, so the two cannot disagree.

The other strings are **left blank**, not marked `x`. The player is not being asked
to mute anything — the strings are simply not part of this step, and five `x` say more
than the gesture does. This reuses the blank the staff and HTML already use for a voice
that is not struck. Two earlier drafts were both wrong: `~` ("let ring") across a chord
change, and then `x`, which overstates the instruction.

The HTML marks the whole column with `_CLASS_REPEAT` (`td.repeat`) and tints it. The
cells are otherwise empty, so without the tint a repeated note reads as a gap in the
music rather than as a deliberate single note. The ASCII staff needed no equivalent,
because a gap in a fixed-width cell is already legible.

## High melodies move down an octave

The user requirement was "anything over the 13th fret, play the soprano on the B
string and move the harmonisation down". The trap is that this is **not** a
re-stringing: the B string is five semitones below the high E, so the same written
pitch sits five frets *higher* on it (`D5` is fret 10 on the high E, fret 15 on the
B). Simply choosing the B string would move the voicing *up* the neck, and for
anything above `F5` the B string cannot reach the pitch at all (`B3` + 18 frets =
`F5`). Dropping the melody an octave is the only thing that actually lowers the
position — it lands a major tenth below where the note sat on the high E.

| name | role |
|---|---|
| `HIGH_FRET_LIMIT = 13` | the neck position above which the move happens |
| `get_octave_down_candidates(...)` | candidates for the melody an octave down, B string only |
| `_lower_soprano_strings(top_strings)` | the soprano strings below the high E, so the transposed note is not put straight back on the high E |
| `ArrangementStep.original_melody` | the written pitch, when the step was transposed |
| `_note_name(midi)` | spells a MIDI number (`Bb5`); `musthe.Note` parses strings only, so a transposed pitch must be spelled before it can be rebuilt as a `Note` |

Three decisions are load-bearing:

- **`get_all_drop2_voicings` stays pure.** It neither filters by fret nor
  transposes, so it and `get_octave_down_candidates` cannot recurse into each other.
  Filtering it was tried first and broke the documented "both families are offered"
  contract that `tests/test_voicings.py::TestMelodyStringChoices` asserts.
- **The guard requires candidates to exist.** This repositions a voicing that is
  playable but too high; a melody unreachable at the written pitch (`B5` is fret 19,
  `C6` is fret 20 — past the end of the board) is still skipped with a warning.
  Silently respelling it would hide a real problem behind a plausible-looking tab.
- **The transposition is reported from the sounding pitch, not the fret.** The
  octave-down note lands at a *lower* fret, so a fret comparison would read it as
  untransposed. `max(voicing.midi_notes())` is the reliable test.

**Known limitation.** The decision is per step and applies to the melody only, so a
melody leaping across the limit can arrive an octave apart from its neighbour. This
is deliberately unlike `wjazzd.py`'s `--lift auto`, which transposes a whole head at
once; `--lift auto` cannot tear the line apart, and this can. The trade is
deliberate: no step is ever left unplayable, at the cost of one melodic interval.

## Contributing Workflow

1. Read `arranger.py` and the relevant test file before changing behavior.
2. Make the smallest change that satisfies the requirement.
3. Add or update tests in `tests/` following the existing `unittest` style —
   one class per concern, descriptive `test_*` method names, docstrings stating
   what is verified.
4. Run the full suite from the repo root:
   `.venv/bin/python -m unittest discover -s tests -v` (must report `OK`).
5. Run the type checker (`.venv/bin/pyright arranger.py tabstaff.py wjazzd.py tests`, or `make typecheck`)
   — it must report `0 errors`. Do not leave a new `reportArgumentType` behind,
   especially when touching a signature.
6. Run the demo (`.venv/bin/python arranger.py`) when touching voicing or
   voice-leading logic and sanity-check the printed tabs.
7. Keep commits focused. This directory is a git repository (initialized with a
   baseline commit), so commit each logical change separately.

## Known Limitations

- Voicings use two to four strings, never all six. The melody may be on the high E, B
  or G string; the A string and low E are inner voices only, so no grip puts the
  soprano on either. There are no barres. Fret `0` does appear when a voice happens to
  land on an open string (e.g. `x-2-3-0-3-x`). 6-4-3 is the one non-contiguous set.
- Melodies are still confined to `G3`–`Bb5`: `G3` is the lowest pitch reachable on the
  G string, `Bb5` the highest on the high E string. The *chord* range reaches further
  down, to `E2` as a bass voice on the low E string in a 6-4-3 shell.
- **A fixed max fret span of 5 rules out close position and drop-3 entirely.** A
  close-position four-note chord under a melody spans a seventh or more, and the four
  strings below the high E are only five semitones apart in tuning, so the frets come
  out more than five apart (Cmaj7 close under C5 wants frets 8, 12, 12, 14); drop-3
  spans a twelfth by construction. The generators exist for a caller who widens
  `GRIP_MAX_SPAN`, but neither is offered by default because the span invariant could
  never keep the promise. Raising the span to admit them is a real change to the
  library's playability contract, not a tuning knob.
- **A chord tone with no matching inversion in the drop-2 tables falls through to the
  quality-only fallback**, which can sound a note the chord does not contain — a 9th in
  the melody of a 13 chord, for example. `voicing_cost`'s first criterion rejects such a
  shape whenever a correct one exists, so an *arrangement* only hears one when nothing
  else is playable, but `get_drop2_voicings` still offers it. Completing the tables is
  a separate piece of work and would change the published drop-2 output.
  `tests/test_grips.py::TestKnownTableGaps` pins the gap so it stays visible.
  Measured over 25 transcriptions after the head-path fix, **26.0%** of head steps still
  carry an inner voice outside the sounding chord, against **23.0%** for the same
  progressions through the library. The two are close, which is the point: the head
  path is no longer a second, weaker implementation of the same rule.
- A melody that can only be voiced above `HIGH_FRET_LIMIT` is moved down an octave,
  so `step.melody` can be an octave below the written note. The decision is per step
  and applies to the melody alone, so a leap across the limit can leave one melodic
  interval an octave wide — unlike `wjazzd.py --lift auto`, which transposes a whole
  head at once. See
  [High melodies move down an octave](#high-melodies-move-down-an-octave).
- A fixed max fret span of 5 and fret range 0–18 is assumed.
- Non-chord melody notes are only covered for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths and the
  half-diminished 9th) plus the dim7 substitution. An unmapped non-chord tone prints
  a warning and keeps the legacy quality-only fallback, which can sound the melody
  over a different chord's shape.
- A handful of low melodies (around `G3`–`C4`) reach no chord-tone-matched inversion
  and therefore use the quality-only fallback. Triad shapes double the root, so their
  second voice can sit up to 10 semitones below the melody — the same span limit, not a
  new failure mode.
- **A partial harmonisation means the printed chord name is not every note sounding.**
  Where a shell or a duo is used, the chord describes the harmony rather than the full
  voicing, and `_step_annotation` says so (`(shell - 3rd & 7th, partial)`). The full
  shape is still in `step.voicing`. This is a consequence of the user's own brief —
  "just harmonising with the 3rd and 7th is fine" — not a defect, but it is a real
  thing to know before reading a tab.
- The `sustain` strategy is structural, not rhythmic: `arrange_progression` takes
  only `(note, quality, name)` triples, so it cannot tell a brief passing note from
  an accented tension. Holding the inner voices is applied whenever the shape can
  physically stay put.
- `7b9`/`7alt` are voiced rootless apart from their new root-in-top inversion;
  other omitted tones (e.g. a root-on-top `13`) have no template yet.
- If no voicing matches a melody/chord, `arrange_progression` prints a warning
  and **skips** that step (rather than raising).
- **MusicXML import (`headxml.py`):**
  - A score that changes metre is laid out in its **prevailing** metre — the last
    `<time>` stated — rather than per bar. A head that moves from 4/4 to 3/4
    mid-way will have the wrong bar lines in its first half.
  - A `<chord>` group is reduced to its highest note, so a **piano** part read as
    a melody is the top line of the right hand with the left hand discarded. That
    is the right reading for a chord-melody part and the wrong one for a
    two-hand piano reduction; there is no staccato/hand inference.
  - A melody below the library's `G3` floor is still unvoiceable, so a very low
    lead sheet needs `--bars` or a transposition, as the corpus path does.
  - No 11th chord is voiced: a dominant 11th is read as the 9th shape and a major
    11th as `maj7#11`, which is the shape it would be played as rather than a
    refusal. A `<degree>` the table does not know is ignored rather than guessed
    at, so an unfamiliar alteration leaves the base kind standing.
  - Repeat barlines and `<ending>` markers are read as text, not expanded: a head
    written with a repeat is played once, not twice.
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
  `arranger.__version__` (currently `0.6.0`), but there is no CI and nothing has
  been published to PyPI.

