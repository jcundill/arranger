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

The entire library lives in a single module: `arranger.py`.

## Repository Layout

```
arranger/
├── arranger.py            # The whole library + a main() demonstration entry point
├── pyproject.toml         # PEP 621 metadata (setuptools backend)
├── README.md              # User-facing overview and usage
├── Makefile               # install / test / demo / build / clean targets
├── tests/                 # unittest test suite (one file per concern)
│   ├── test_chord_parser.py
│   ├── test_fretboard.py
│   ├── test_progressions.py
│   ├── test_voice_leading.py
│   └── test_voicings.py
└── .venv/                 # Local virtualenv (not committed)
```

There is **no** `setup.py`, `setup.cfg`, `requirements.txt`, or CI config, and none
is needed. Packaging metadata lives solely in `pyproject.toml`, which uses the
setuptools backend, declares `musthe` as its only runtime dependency, and reads the
version dynamically from `arranger.__version__`.

## Requirements

- Python **3.10+** (the code uses `X | Y` type unions at runtime in signatures,
  e.g. `Voicing | dict`). The local dev virtualenv runs **Python 3.14**.
- One third-party runtime dependency: **[musthe](https://pypi.org/project/musthe/)**
  (music theory primitives: `Note`, `Chord`, `Interval`).

## Setup

A virtualenv already exists at `.venv/`. Prefer invoking its interpreter
directly (`.venv/bin/python`) so you do not depend on shell activation.

Recreate it from scratch if needed:

```bash
python3 -m venv .venv
.venv/bin/pip install musthe
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

## Architecture / Key Types (`arranger.py`)

- `STANDARD_TUNING` — six open-string `Note`s, index `0` = low E (string 6)
  through index `5` = high E (string 1). `STRING_NAMES` mirrors these.
- `MELODY_STRING_CHOICES` — `(5, 4)`: the soprano string indices a voicing may be
  pinned to (`5` → D-G-B-E, `4` → A-D-G-B). Index `0` = low E ... `5` = high E, so
  the conventional guitar string number is `6 - index` (index `5` = string 1).
- `Voicing` — a dataclass for one fretboard shape: `frets` (6 entries,
  `-1` = muted), `top_fret`, `avg_fret`. Helpers: `tab_string()`,
  `active_frets()`, `fret_span()`, `midi_notes()`, `pitch_classes()`,
  `soprano_string()` (index of the highest sounding string; `-1` if all muted).
  Supports legacy dict-style access (`v["frets"]`).
- `ArrangementStep` — a dataclass of `chord`, `melody`, `voicing`. Also
  supports legacy dict-style access (`step["chord"]`).
- `GuitarFretboard` — static helpers `note_to_fret(string_index, note)` and
  `fret_to_midi(string_index, fret)`. Out-of-range inputs return `-1`.
- `ChordParser` — `parse_chord_name(name) -> (root, quality)` and
  `get_melody_degree(root, melody_note) -> 0..11`.
- `VoiceLeadingEngine` — the core engine:
  - `DROP2_INTERVAL_SETS`: semitone offsets from the soprano voice for each
    supported chord quality (major, minor, dominant families) plus aliases.
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
  - `arrange_progression(progression, top_strings=MELODY_STRING_CHOICES)`.
- `__version__` — the library version string (currently `0.1.0`). `pyproject.toml`
  reads it as the dynamic project version, so it is the single source of truth.
- `main()` — prints the built-in demonstration arrangements; exposed as the
  `jazz-arranger` console script via `[project.scripts]`.

### Adding a new chord quality

1. Add a template list to `DROP2_INTERVAL_SETS` (four inversion templates, each
   `[0, offset2, offset3, offset4]` in semitones below the soprano).
2. Add the matching entry to `DEGREE_OFFSETS_FROM_ROOT` so the melody note is
   matched to the correct inversion.
3. Add any aliases in the `DROP2_INTERVAL_SETS[...] = ...` block.
4. Add a test in `tests/test_voicings.py` verifying pitch classes and
   `fret_span() <= 5`.

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
5. Run the demo (`.venv/bin/python arranger.py`) when touching voicing or
   voice-leading logic and sanity-check the printed tabs.
6. Keep commits focused; note that this directory is **not currently a git
   repository**, so initialize one only if the user asks.

## Known Limitations

- Only four strings are modeled at a time (the high-E block or the B block); no
  full six-string voicings or barres. Fret `0` does appear when a voice happens to
  land on an open string (e.g. `x-2-3-0-3-x`).
- Melodies are still confined to `B3`–`Bb5`: `B3` is the lowest pitch reachable on
  the B string, `Bb5` the highest on the high E string. Adding the third block
  (melody on the G string, strings G-D-A-low E) is a one-tuple addition to
  `MELODY_STRING_CHOICES`.
- A fixed max fret span of 5 and fret range 0–18 is assumed.
- If no voicing matches a melody/chord, `arrange_progression` prints a warning
  and **skips** that step (rather than raising).
- The public API is packaged as `jazz-arranger` and versioned through
  `arranger.__version__` (currently `0.1.0`), but there is no CI and nothing has
  been published to PyPI.

