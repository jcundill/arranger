# jazz-arranger

`jazz-arranger` is an algorithmic engine that generates playable, idiomatic **jazz guitar chord-melody arrangements** and **comping accompaniments** from standard lead sheets and chord progressions.

Designed for guitarists and developers alike, it bridges formal voice-leading constraints with real-world fretboard mechanics — drop voicings, soprano melody pinned to the high E, B or G string, non-chord tone extensions, walking bass lines, and complex song structures (repeats, 1st/2nd endings, D.C., D.S., Coda, Fine).

---

## What It Does on the Fretboard

* **Idiomatic grip families.** Seven families — `drop2`, `closed`, `drop3`, `drop24`, `drop2_6432`, `shell` and `duo` — four notes down to two-note guide-tone pairs (3rd and 7th). Every shape is built from the chord's own tones, so a shell never guesses a note the chord does not contain.
* **Soprano melody pinned.** The lead line stays on the high E, B or G string while rich accompaniment is voiced underneath, within a playable neck window (frets 0–18, max span 5 frets; 4 for duos).
* **Lead sheet ingestion.** Reads MusicXML (`.musicxml` or `.mxl`) scores — written melody plus chord symbols — honouring rhythm, repeats, 1st/2nd endings, D.C. / D.S. jumps, Coda, Fine and pickup bars.
* **Flexible arrangement roles.**
  * *Solo guitar:* melody harmonized with full chords.
  * *Comping mode* (`--no-melody`): accompaniment chords for backing a horn player; the guitar states the guide tones and stays out of the way.
  * *Thumb independence* (`--bass-on`, `--bass-notes`): walking bass lines or root-5th patterns beneath the tune.

---

## A First Arrangement

Input — a few `(melody note, chord name)` pairs:

```text
D5  Dm7
B4  G7
C5  Cmaj7
```

Output — tablature, low E → high E, `x` = muted, with each step's analysis:

```text
Dm7      D5  Root x-x-10-10-10-10   (harmony under Root - 4 voices -
                                     sounding: C b7, F b3, A 5, D Root)
G7       B4  3    13-x-12-12-12-x   (harmony under 3 - 4 voices - sounding: F b7, D 5, G Root, B 3)
Cmaj7    C5  Root x-x-9-9-8-8       (harmony under Root - 4 voices -
                                     sounding: B 7, E 3, G 5, C Root)
```

That same engine reads a MusicXML lead sheet — see the CLI quick start below.

---

## Installation

Not yet on PyPI — run from the repository root:

```bash
pip install -e .
```

That pulls the one runtime dependency, `musthe`. Two optional extras, each behind a lazy import so a GP5 run never needs music21 and vice versa:

```bash
pip install -e '.[xml]'   # MusicXML export (music21)
pip install -e '.[gp]'    # Guitar Pro 5 export (PyGuitarPro)
pip install -e '.[dev]'   # pyright + ruff (contributing only)
```

**Name split:** the *distribution* is `jazz-arranger` (the PyPI name `arranger` is taken by an unrelated project); the *import* name is `arranger`. There is no console script without an install — run `python -m arranger` from the repo, or `jazz-arranger` once installed.

Or skip install and hear the built-in demonstration:

```bash
python -m arranger
```

---

## Quick Start: CLI (The Main Event)

Most guitarists will process a `.mxl` / `.musicxml` lead sheet:

```bash
python -m arranger head tests/data/synthetic_cut_time.mxl --bars 1-3
```

Both bare `.musicxml` and zipped `.mxl` are accepted. The run header echoes the request so you can paste it back as `Request(...)`:

```text
Synthetic Cut Time - Fixture Generator
  part: Voice
  2/2, Eb major, 20 melody note(s), bars 1-8; neck window: frets 2-13
  note: 3 rests and unpitched notes
  request: melody=on chord-on=melody chord-notes=full bass-on=none bass-notes=root chord-fills=none

Bb7      F4  5    6-x-6-7-6-x       (harmony under 5 - 4 voices -
                                     sounding: Bb Root, Ab b7, D 3, F 5)
Bb7      G4  13   6-x-6-7-8-x       (non-chord tone -> Bb13 via extension - 4 voices -
                                     sounding: Bb Root, Ab b7, D 3, G 13 -
                                     the chord tones it leaves out are 9 & 5)
Bb7      F4  5    6-x-6-7-6-x       (harmony under 5 - 4 voices -
                                     sounding: Bb Root, Ab b7, D 3, F 5)
Ebmaj    G4  3    6-x-8-8-8-x       (harmony under 3 - 4 voices -
                                     sounding: Bb 5, Bb 5, Eb Root, G 3)
Ebmaj    F4  9    6-x-8-8-6-x       (non-chord tone -> Ebadd9 via extension - 4 voices -
                                     sounding: Bb 5, Bb 5, Eb Root, F 9 -
                                     the chord tone it leaves out is 3)
Cm7      Eb4 b3   6-x-5-5-4-x       (harmony under b3 - 4 voices -
                                     sounding: Bb b7, G 5, C Root, Eb b3)
```

`--bars 1-3` takes a half-open range of the head (bounds may be negative for pickups). `--no-melody` hands the tune to another instrument and comps instead:

```bash
python -m arranger head tests/data/synthetic_common_8.musicxml --bars 1-3 \
    --no-melody --chord-notes 3 --chord-on every-beat
```

```text
Synthetic Common Time - Fixture Generator
  part: Voice
  4/4, Eb major, 22 melody note(s), bars 1-8; neck window: frets 2-13
  note: 1 rests and unpitched notes
  request: melody=off chord-on=1,2,3,4 chord-notes=3 bass-on=none bass-notes=root chord-fills=none

Cmaj7    E4  3    x-x-9-5-5-x       (comping - C Root, E 3 & B 7; the guitar does not play the tune
                                    - top E4 - the opening, in the band's middle)
Cmaj7    G4  5    x-x-9-9-8-x       (comping - E 3, G 5 & B 7; the guitar does not play the tune -
                                    top G4 - walks up)
Cmaj7    A4  13   x-x-7-9-10-x      (comping - E 3 & A 6; the guitar does not play the tune -
                                    non-chord tone -> C6/9 via extension - top A4 - walks up)
Cmaj7    G4  5    x-x-9-5-5-x       (comping - C Root, E 3 & B 7; the guitar does not play the tune
                                    - top E4 - walks down)
Dm7      F4  b3   x-8-10-7-x-x      (comping -
                                    D Root, F b3 & C b7; the guitar does not play the tune - top D4
                                    - walks up)
Dm7      F4  b3   x-x-7-5-6-x       (comping - F b3, A 5 & C b7; the guitar does not play the tune -
                                    top F4 - walks up)
Dm7      F4  b3   x-x-10-10-10-x    (comping - F b3, A 5 & C b7; the guitar does not play the tune -
                                    top A4 - walks up)
G7       D4  5    x-x-9-10-8-x      (comping - G Root, B 3 & F b7; the guitar does not play the tune
                                    - top G4 - walks down)
```

Repeats, endings and jumps are signposted, not written out — an 8-bar head plays as 12 bars, and `--tab staff`, `--html`, `--musicxml` or `--gp5` draw the `|:` / `:|` signs, `1.` / `2.` brackets and the Segno / Coda / Fine / D.C. / D.S. directions.

---

## Quick Start: Python Library

```python
from arranger import VoiceLeadingEngine

engine = VoiceLeadingEngine()

# (melody note, chord name)
progression = [
    ("D5", "Dm7"),
    ("B4", "G7"),
    ("C5", "Cmaj7"),
]

for step in engine.arrange_progression(progression):
    print(f"{step.chord:<8} {step.melody:<3} {step.voicing.tab_string()}")
```

```text
Dm7      D5  x-x-10-10-10-10
G7       B4  13-x-12-12-12-x
Cmaj7    C5  x-x-9-9-8-8
```

Every knob after `progression` is keyword-only — the neck window, non-chord-tone strategy, timings, the request, the metre:

```python
from arranger import VoiceLeadingEngine, Request, TimeSignature

engine = VoiceLeadingEngine()

# Comping for a horn: the guitar states the chord, never the tune.
steps = engine.arrange_progression(
    [(None, "Dm7"), (None, "G7"), (None, "Cmaj7"), (None, "A7")],
    request=Request(melody=False, chord_on="1,3"),
)
```

`Request` is the one spelling of what to play — who plays the tune, when each layer attacks, what each states, and what the chord does in a melody rest. `--no-melody --chord-on 1,3` on the command line is `Request(melody=False, chord_on="1,3")`; the two spellings are identical.

---

## Guide to Arrangement Controls

The flags are grouped by musical effect, not alphabetically. Every value shown here is one the parser accepts — copy a line from the run header and it will parse.

### The Texture — `--chord-notes`

How many chord tones a step may state:

| value | meaning |
|---|---|
| `full` (default) | The most the right hand can fit — three notes under the melody, two once a bass note takes a string |
| `targets` | That same maximum on a strong beat, a thinner shape between them |
| `3` | Exactly three chord tones, everywhere |
| `2` | Exactly two (a shell: guide tones plus one more) |
| `1` | Exactly one |

`--chord-notes full` is `Request(chord_notes="full")`. Narrowing the palette never widens it — if nothing survives the narrowing, the step keeps its shape and names the refused note.

### The Rhythm — `--chord-on`

When the chord attacks, in felt beats, bar-relative:

| token | meaning |
|---|---|
| `melody` (default) | At every written melody onset; the chord default |
| `sustain` | Only at onsets whose note runs at least one felt beat |
| `none` | The layer is absent |
| `every-beat` | The start of every felt beat (4 in 4/4, 3 in 3/4, 2 in 2/2, …) |
| `1`, `2`, `3`, `4` | That felt beat |
| `1and` | Halfway through felt beat 1 — "the and of 1" |
| `1e`, `1a` | A quarter / three-quarters through felt beat 1 |
| `last`, `lastand` | The last felt beat, and its offbeat |
| `melody,1and` | The melody-note harmonisation plus a stab |
| `1,3:none` | A colon-joined cycle: beats 1 and 3 of bar 1, none of bar 2, repeating |

A list **replaces** the default, so `--chord-on 1and` is only the stab and `--chord-on melody,1and` is the harmonisation plus the stab. A position the metre does not have is **refused** (`3` in a 2/2 bar), not silently dropped. The midpoint is spelled `and`, never `&` — an unquoted `&` is the shell's background operator.

### The Bass — `--bass-on` / `--bass-notes`

When the thumb attacks (`--bass-on`), and what each attack states (`--bass-notes`):

| `--bass-on` | meaning |
|---|---|
| `none` (default) | No bass line |
| `every-beat` | One note at the start of every felt beat |
| `1`, `1and` | Named positions; a colon-joined cycle works too (`1,3:none`) |
| `melody` | Refused — the thumb has no written onsets of its own |

| `--bass-notes` | meaning |
|---|---|
| `root` (default) | The chord's root at every position; marks the bar on the anchor, a pedal elsewhere |
| `root-5th` | Root and 5th alternating |
| `walk` | Anchor / connect / approach / enclosure walking line |
| `root,approach` | The note rules themselves, in resolution order |

`--bass-on every-beat --bass-notes walk` is the classic walking thumb under the tune. `--bass-notes root` on every beat is a pedal, not a walk — `pedal` is what `root` does on a non-anchor position, not a style you ask for by name.

### The Context — `--no-melody`

The guitar stops singing and states the chord instead, for a horn that has the tune. Its degrees are the **guide pair** by default — 3rd and 7th — and `--chord-notes` says how many notes carry them. The high E is not on the comping palette: that string is where the tune is pinned first, and a comping part has no tune to put there. Dropping it is a palette narrow, so the chord is never lost — it moves.

### Supporting flags

| flag | default | what it does |
|---|---|---|
| `--part` | the melody part | A `<score-part>` id, when the score has several |
| `--bars` | whole head | Half-open `LO-HI` range; bounds may be negative for pickups |
| `--non-chord-tone` | `extension` | How to harmonise a melody note outside the chord |
| `--fallback` | off | `diminished` — the optional diminished retry |
| `--chord-fills` | `none` | What the chord states in a notated melody rest: `hold` once at the onset, or `comp` on each felt beat |
| `--fret-min` / `--fret-max` | `2` / `13` | Neck window to aim for (a preference, never a filter) |
| `--tab` | `line` | `staff` lays the head on one six-line staff, spaced on real rhythm |
| `--note-names` / `--mutes` | off | With `--tab staff`: name each melody note / spell muted strings as `x` |
| `--bars-per-line` | `4` | With `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | Also write the head to a file (each behind its optional extra) |

---

## What It Does Not Do

These are the honest edges, so you are not surprised mid-arrangement:

* **Voicings are 2–4 strings, never all six.** Melody on high E, B or G only; A and low E are inner voices. No barré chord — fret `0` when a voice lands on an open string — and no full six-string voicing is modelled.
* **Melodies sit from G3 up.** A melody whose only position sits above fret 13 is voiced an octave down, never refused — `step.melody` is what sounds, `step.original_melody` keeps the written pitch.
* **Fixed max fret span** — 5 frets (4 for duos); fret range 0–18. No step may need a fifth fret from a hand already holding a shape. `closed` is offered second in preference order but is usually unreachable — most melodies cannot fret it inside the budget; it wins only where it does.
* **Non-chord melody notes** are handled only for the extension mappings (9ths, 6/9s, 11ths, #11s, b13s, 13ths, half-diminished 9th, 9th over plain triad) plus dim7. Anything else sounds alone under its chord, and the step says so.
* **The neck window is a preference, not a filter** — a step with no voicing inside frets 2–13 is still played just outside it, because losing a chord of the tune beats a fret out of position. `--fret-min`/`--fret-max` may not be honoured where nothing playable lies inside.
* **Slash bass is a preference, not a hard constraint** — the selector narrows candidates by it, but the engine's own rule decides within that set; a voicing that cannot honour the bass is still playable.
* **No release published to PyPI** — install from the repo with `pip install -e .` (see Installation).

---

## Technical Architecture & Deep Dives

The dense implementation notes live in `docs/`, so they never get in a guitarist's way:

* [`docs/engine.md`](docs/engine.md) — the selector, the axes, the cost tuple, non-chord tones, and the recipe for adding a chord quality
* [`docs/renderers.md`](docs/renderers.md) — tab staff, MusicXML import/export, Guitar Pro 5, and what the four renderers agree about
* [`docs/open-issues.md`](docs/open-issues.md) — the issue ledger (one open, item 7; six filed, each with its measurement)

Development commands:

```bash
make check      # lint + typecheck + test — the CI gate
make test       # the full suite: test_*.py (music) then meta_*.py (tree)
make demo       # the built-in demonstration arrangements
make build      # build a wheel into dist/
```

`make check` is what CI runs (Python 3.11–3.14, both optional extras installed). Tests are stdlib `unittest` — no `pytest` dependency. `pyright` and `ruff` are dev-only and never reachable from a plain install.

Licence: MIT. [`LICENSE`](LICENSE) full text. The optional `gp` extra pulls in PyGuitarPro (LGPL-3.0), deliberately kept out of runtime dependencies and behind a lazy import, so this project stays a permissively licensed work and is not a combined work of PyGuitarPro.
