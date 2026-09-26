# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Given a progression of `(melody note, chord quality, chord name)` triples, `arranger`
builds Drop-2 voicings that pin the melody to the soprano string and voice-leads them
for smooth left-hand movement.

- **Drop-2 voicings** on two four-string blocks: strings D-G-B-E (melody on the high E
  string) and A-D-G-B (melody on the B string).
- **Melody pinned** to the soprano voice — the chord-tone inversion that matches the
  melody is selected automatically, with a quality-only fallback.
- **Non-chord melody notes** — a melody note outside the chord is reharmonised as a
  chord extension, via the Barry Harris 6/dim7 substitution, or by holding the chord
  shape under a passing tone (see [Non-chord melody notes](#non-chord-melody-notes)).
- **Voice leading** that minimises sounding-pitch movement between consecutive chords,
  so a chord can stay where the previous one left the hand.
- **Dependency-light**: Python 3.10+ and [musthe](https://pypi.org/project/musthe/) only.

> The **distribution** is named `jazz-arranger` (the PyPI name `arranger` is already
> taken by an unrelated project). The **import** name is simply `arranger`.

## Installation

```bash
pip install -e .        # or: make install
```

Or, without installing, just run everything from the repository root — the module
imports directly:

```bash
python arranger.py      # built-in demonstration arrangements
```

## Quick start

```python
from arranger import VoiceLeadingEngine

engine = VoiceLeadingEngine()

# (melody note, chord quality, chord name)
progression = [
    ("D5", "m7",  "Dm7"),
    ("B4", "7",   "G7"),
    ("C5", "maj7", "Cmaj7"),
]

for step in engine.arrange_progression(progression):
    print(f"{step.chord:<8} {step.melody:<3} {step.voicing.tab_string()}")
```

```text
Dm7      D5  x-x-10-10-10-10
G7       B4  x-x-5-7-6-7
Cmaj7    C5  x-x-9-9-8-8
```

Each step is an `ArrangementStep` (`chord`, `melody`, `voicing`, plus the
non-chord-tone fields `non_chord_tone`, `strategy` and `harmonized_as`); the
`voicing` is a `Voicing` with `frets` (six entries, `-1` = muted), `top_fret`,
`avg_fret` and helpers such as `tab_string()`, `fret_span()`, `midi_notes()`,
`pitch_classes()` and `soprano_string()`.

Tab strings run from the low E string to the high E string, with `x` for a muted
string — so `x-x-12-13-13-13` is a voicing on D-G-B-E with the melody on the high E.

## Low-register melodies

Melodies below the high E string's open pitch (`E4`) cannot be voiced on that block.
Those notes are pinned to the B string instead (voicing on A-D-G-B), which drops the
reachable floor to `B3`:

```python
low = [("D4", "m7", "Dm7"), ("D4", "7", "G7"), ("C4", "maj7", "Cmaj7")]
for step in engine.arrange_progression(low):
    print(step.chord, step.voicing.tab_string(), "melody string",
          6 - step.voicing.soprano_string())
```

```text
Dm7 x-3-3-2-3-x melody string 2
G7 x-2-3-0-3-x melody string 2
Cmaj7 x-2-2-0-1-x melody string 2
```

Both blocks sound the same four pitches for a given inversion — only the position on
the neck differs. Pass `top_strings=(5,)` to `arrange_progression` (or
`get_all_drop2_voicings`) to restrict voicings to the traditional high-E block.

## Non-chord melody notes

Real melodies do not always land on a chord tone. Bar 2 of "All of Me" moves
`C5 → D5 → C5` over `Cmaj7`, where `D5` is the 9th. Pass `non_chord_tone=` to
`arrange_progression` (or call `is_chord_tone` / `resolve_non_chord_tone`
directly) to choose how such notes are harmonised:

```python
bar_2 = [("C5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7"), ("C5", "maj7", "Cmaj7")]

for strategy in ("extension", "diminished", "sustain"):
    tabs = [s.voicing.tab_string() for s in engine.arrange_progression(bar_2, non_chord_tone=strategy)]
    print(f"{strategy:<11} {tabs}")
```

```text
extension   ['x-x-9-9-8-8', 'x-x-9-9-8-10', 'x-x-9-9-8-8']
diminished  ['x-x-9-9-8-8', 'x-x-9-10-9-10', 'x-x-9-9-8-8']
sustain     ['x-x-9-9-8-8', 'x-x-9-9-8-10', 'x-x-9-9-8-8']
```

- `extension` (default) — absorb the note as an extension: `D5` over `Cmaj7`
  becomes a `Cmaj9`, so `D` is a chord tone again and the shape sounds only
  `Cmaj7`-family pitches. The mapping lives in
  `VoiceLeadingEngine.NON_CHORD_TONE_EXTENSIONS`: 9ths and 6/9ths, plus the #11
  (`Cmaj7#11`), the 11th (`G7sus4`), the #11/b13 over dominants, the 13th and the
  half-diminished 9th (`Am9b5`).
- `diminished` — the Barry Harris 6/dim7 substitution: the passing `D5` is voiced
  inside `Bdim7` (the dim7 a semitone below the note the line resolves to), giving
  a smooth chromatic resolution.
- `sustain` — hold the previous chord's three inner voices and move only the
  melody, the way a shape is held under a passing tone.
- `legacy` — the historical quality-only fallback, kept for callers who depend on
  it. It can sound the melody over a different chord's shape (for `D5` over
  `Cmaj7` it produced `Bb-Eb-G-D`), which is why it is no longer the default.

Every `ArrangementStep` records what happened: `non_chord_tone`, `strategy` and
`harmonized_as` (e.g. `"Cmaj9"`). Melodies that are already chord tones are
arranged exactly as before, whichever strategy is selected.

## Supported chord qualities

Seventh chords: `maj7`, `6`, `m7`, `m7b5`, `dim7`, `m6`, `mMaj7`, `7`, `7b9`,
`7alt`. Extensions: `maj9`, `m9`, `9`, `6/9`, `13`. Triads: `maj`, `m`, `aug`.
Suspended: `sus4`, `sus2`, `7sus4`. Added-note and altered colours: `add9`, `madd9`,
`7b5`, `7#5`, `7#11`, `7b13`, `maj7#11`, `m9b5`.

Aliases resolve case-sensitively, so `M7` is a major seventh while `m7` is a minor
seventh and `M` is a major triad. They include `min7`, `min7b5`, `ø7`, `ø`,
`half-dim`, `°7`, `°`, `dim`, `min6`, `minMaj7`, `mmaj7`, `min9`, `dom7`, `dom9`,
`dom13`, `M7`, `M9`, `69`, `min`, `-`, `+`, `sus` and `7sus`. Two deliberate
conventions: `dim` still means `dim7` (the diminished triad is not voiced), and a
bare `C` is not assumed to be major — spell it `Cmaj` or `CM`.

A drop-2 shape has four voices, so the triad templates double the root an octave
below the stack:

```python
from musthe import Note

colours = [
    ("E5",  "maj",  "Cmaj"),         # x-x-10-9-8-12
    ("C5",  "sus4", "Gsus4"),        # x-x-5-5-3-8
    ("D5",  "add9", "Cadd9"),        # x-x-10-9-8-10
    ("Db5", "7#11", "G7#11"),        # x-x-9-10-8-9
    ("Eb5", "7b13", "G7b13"),        # x-x-9-10-8-11
    ("F#5", "maj7#11", "Cmaj7#11"),  # x-x-14-16-13-14
    ("B4",  "m9b5", "Am9b5"),        # x-x-5-5-4-7
]
for note, quality, name in colours:
    voicing = engine.get_drop2_voicings(Note(note), quality, chord_name=name)[0]
    print(f"{name:<9} {note:<3} {voicing.tab_string()}")
```

Unsupported qualities return no voicings; `arrange_progression` prints a warning and
skips that step rather than raising.

## Development

The only runtime dependency is `musthe`; tests use the standard-library `unittest`
framework (there is no pytest dependency).

```bash
make test      # .venv/bin/python -m unittest discover -s tests -v
make demo      # run the built-in demonstration
make build     # build a wheel into dist/
make clean     # remove caches and build artefacts
```

`make` prefers the repository's `.venv/bin/python`; override it with
`make test PYTHON=python3`. The equivalent long form is
`.venv/bin/python -m unittest discover -s tests -v` run from the repository root.

The whole library lives in a single module, `arranger.py`. See `AGENTS.md` for the
architecture, coding conventions, and the recipe for adding a new chord quality.

## Known limitations

- Only four strings are modelled at a time (the high-E block or the B block) — no
  full six-string voicings or barres.
- Melodies are confined to `B3`–`Bb5`.
- A fixed maximum fret span of 5 and fret range 0–18 are assumed.
- Non-chord melody notes are handled only for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths and the
  half-diminished 9th) plus dim7; anything else keeps the legacy quality-only
  fallback.
- A handful of low melodies (around `B3`–`C4`) reach no chord-tone-matched inversion
  on either four-string block and fall back to quality-only voicings. The rate is the
  same as for the long-standing qualities (`maj7`, `m7`, `9`, `m9`).
- The `sustain` strategy is structural — the API takes only `(note, quality, name)`
  triples, so rhythm and duration cannot be used to spot a brief passing tone.
- No CI and no release has been published to PyPI.

## License

No license has been chosen for this project yet.
