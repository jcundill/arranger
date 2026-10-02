# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Given a progression of `(melody note, chord quality, chord name)` triples, `arranger`
builds voicings in several grip families, pins the melody to the soprano string, and
picks among them with one position-aware cost function.

- **Six grip families**, drop-2 first: `drop2`, `drop3`, `drop24`, `drop2_6432`,
  `shell` and `duo` — four-note voicings down to two-note guide-tone pairs. Every
  one sounds the chord's **3rd and 7th**, the two notes that decide whether the ear
  hears a major or a minor chord ([grips](#grips)).
- **Melody pinned to the soprano**, on the high E, B or G string, so a low melody can
  still be harmonised in position.
- **Playable or absent.** Every voicing sits in frets 0–18 within a 5-fret span on a
  real string set. The neck window is a *preference, not a filter* — losing a chord of
  the tune is worse than being a fret out of position.
- **Non-chord melody notes** are reharmonised as an extension, via the Barry Harris
  6/dim7 substitution, or by holding the chord shape under a passing tone.
- **Three textures**, not one: every note in full, chords on the strong beats with
  thinner fills between, or a walking bass line under the melody ([texture](#texture)).
- **Heads from real sources** — a MusicXML score, or any of the 456 Weimar Jazz
  Database transcriptions.
- **Dependency-light**: Python 3.11+ and [musthe](https://pypi.org/project/musthe/)
  only. Reading a MusicXML head needs no extra at all; MusicXML *export* and Guitar
  Pro export each live behind their own optional extra.

> The **distribution** is named `jazz-arranger` (the PyPI name `arranger` is already
> taken by an unrelated project). The **import** name is simply `arranger`.

## Installation

```bash
pip install -e .        # or: make install
```

A plain install pulls in `musthe` alone. Two optional extras add the writers, each
behind a lazy import so the library works without either:

```bash
pip install -e '.[xml]' # adds music21,        for format_musicxml / write_musicxml
pip install -e '.[gp]'  # adds PyGuitarPro,    for format_gp5 / write_gp5
```

Nothing else in the package needs them: `tabxml` imports `music21` when it is
*called*, not when it is imported, so a run asking for a GP5 file does not require
music21 and vice versa. Or skip installing entirely and run from the repository
root — the module imports directly:

```bash
python -m arranger      # the built-in demonstration arrangements
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
G7       B4  13-x-12-12-12-x
Cmaj7    C5  x-x-9-9-8-8
```

Each step is an `ArrangementStep` (`chord`, `melody`, `voicing`, plus the non-chord-tone
fields `non_chord_tone`, `strategy` and `harmonized_as`); the `voicing` is a `Voicing`
with `frets` (six entries, `-1` = muted), `top_fret`, `avg_fret` and helpers such as
`tab_string()`, `fret_span()`, `midi_notes()`, `pitch_classes()` and `soprano_string()`.

Tab strings run from the low E string to the high E, with `x` for a muted string — so
`x-x-12-13-13-13` is a voicing on D-G-B-E with the melody on the high E.

## Reading a head from a MusicXML file

`arranger head` does the same job from a **written melody and chord symbols** —
a lead sheet, a melody-only score, or anything else in MusicXML:

```bash
python -m arranger head tests/data/but_not_for_me.mxl --bars 1-5
```

```text
But Not For Me - George Gershwin
  part: Voice
  2/2, 80 melody note(s), bars 1-32; neck window: frets 2-13; grips: drop2, shell, duo
  note: 15 rests and unpitched notes

Bb7      F4   x-5-6-3-6-x
Bb7      G4   (non-chord tone -> Bb13 via extension) x-8-6-7-8-x
Bb7      F4   x-5-6-3-6-x
Ebmaj    G4   x-6-5-3-8-x
Ebmaj    F4   (non-chord tone) x-5-3-3-6-x
```

Both forms of the format are read: a bare `.musicxml` document and a zipped `.mxl`
container, which is resolved through its `META-INF/container.xml` rather than by
taking the first XML file out of the archive.

**It needs no optional dependency.** The exporter wants `music21`; the importer
wants `zipfile` and `xml.etree`, which are in the standard library. A plain
`pip install jazz-arranger` can read a score, and `tests/test_headxml.py` is not
`skipUnless`-guarded at all — the scores it reads are committed in `tests/data/`,
so a clone runs the whole thing.

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --tab staff --melody
python -m arranger head tests/data/i_was_doing_all_right.mxl --bars 1-3 --html head.html
```

| flag | default | what it does |
|---|---|---|
| `--part` | the melody part | a `<score-part>` id, when a score has several |
| `--bars` | the whole head | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--skeleton` | `eighths` | how finely to read the melody — see below |
| `--pick` | `first` | which note to take when one slot holds several |
| `--non-chord-tone` | `extension` | how to harmonise a melody note outside the chord |
| `--fallback` | off | `diminished` — see [the trade-off](#the-fallback-trade-off) |
| `--texture` | `uniform` | `uniform`, `targets`, `walking_bass` — see [texture](#texture) |
| `--fret-min` / `--fret-max` | `2` / `13` | the neck window to aim for |
| `--grips` | all six | which grip families to consider, **most preferred first** |
| `--tab` | `line` | `staff` lays the head on one six-line staff, spaced on its real rhythm |
| `--melody` / `--mutes` | off | with `--tab staff`: add a melody row / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write the head to a file — see [rendering](#rendering) |

**`--skeleton` picks the rhythmic grid.** One step per *chord change*, per *beat*, per
*eighth*, per *sixteenth*, or per *notated note* — so `eighths` is the default because a
chord-melody line is usually eighths, and `notes` is the most literal reading of a
written melody. A denser grid means more steps and more decisions, not a different tune.

**`--pick` matters only where the score is dense.** Where several notes share one slot
(chord changes are often notated as a single melody note), `first` takes the first in
the score and `longest` takes the longest value.

**`--grips` is ordered.** It is a preference list, not a set: putting `shell` first
will displace a four-note drop-2 whenever the two cost the same. Leave it alone unless
you want a thinner arrangement.

**The fret window is an aim, not a filter.** A step with no voicing inside your window
is still played, outside it, and the run header echoes your window whether or not it was
met — losing a chord of the tune is worse than being a fret out of position.

### Four things a score does that a database does not

**The harmony is a timeline.** A `<harmony>` precedes the note it governs, several can
share a bar, and a bar can carry none at all — so a chord is *held* from the note it is
declared before until the next one replaces it. Reading the chord off the note that
follows it would drop the harmony from every bar that does not change.

**The metre is the notated one.** `beat` is the beat *within* the bar in notated beats,
so a 2/2 head is two beats to the bar rather than four — which is how most standards are
written, and how three of the four scores in this repository are.

**The melody is the top line.** A `<chord>` group reduces to its *highest* note, because
MusicXML does not order a group by pitch and in a chord-melody part the first member is
the lowest note. Everything else is counted and reported in `skipped`, not dropped.

**A chord this library cannot voice is counted, not guessed.** `Neapolitan` is a real
MusicXML kind and a real chord; it is not one this library holds under a melody, so it
is listed in `Head.unmapped` and the run says so.

### It is the same arrangement code

A head read from a score is voiced by `wjazzd.arrange_slots` — the corpus path's own
step loop. The non-chord-tone strategies, the opt-in diminished retry, the repeated-melody
hold and the walking bass are therefore identical whichever source a head was read from;
only the *selection* differs.

```python
from headxml import load_musicxml, head_skeleton

head = load_musicxml("tests/data/but_not_for_me.mxl")   # melody, timing, chords
print(head.title, head.beats_per_bar, len(head))
for triple, bar, beat, duration in head_skeleton(head, "eighths"):
    print(bar, beat, triple)
```


## Rendering a head from the Weimar Jazz Database

The database holds 456 jazz transcriptions. `arranger corpus` turns the **head**
— the tune — of any of them into a chord-melody arrangement:

```bash
python -m arranger corpus --melid 218     # Coltrane, "Blue Train"
```

```text
Blue Train - John Coltrane (melid 218, Eb-maj)
  melid 218: head at bars 1-12 (12 bars), anchored on Eb7 Ab7 Eb7 Ab7 Eb7 C7 F-7 Bb7 Eb7 [A-block is 79 bars; trimmed to one statement]
  neck window: frets 2-13 (a preference, not a constraint); grips: drop2, drop3, drop24, drop2_6432, shell, duo
  note: lifted an octave: 59 -> 60 of 62 steps voiced
  note: 13 unresolved tension(s) could be rescued with --fallback diminished, which replaces the written chord

Eb7      F5   (non-chord tone -> Eb9 via extension) x-x-11-12-11-13
Ab7      Eb5  x-x-10-11-9-11
Ab7      F5   (non-chord tone -> Ab13 via extension) x-13-13-x-13-13
Ab7      Db5  (non-chord tone -> Ab7sus4 via extension) x-9-x-8-9-9
Ab7      Eb5  x-9-10-x-9-11
Ab7      F5   (non-chord tone -> Ab13 via extension) x-13-13-x-13-13
Eb7      E5   (non-chord tone) x-13-13-x-14-12
```

Every reharmonised note says so, in the form `(non-chord tone -> Ab13 via extension)` —
this head is a good illustration of [Heads are not harmonically simpler than
solos](#three-things-to-know-before-you-rely-on-it) above.

This needs `wjazzd.db` (42 MB) from [jazzomat.hfm-weimar.de](http://jazzomat.hfm-weimar.de/),
placed beside the package or pointed at by `WJAZZD_DB`. It is not committed, and
nothing in the library requires it.

```bash
python -m arranger corpus --list                        # the 456 transcriptions
python -m arranger corpus --melid 342 --tab staff       # "All the Things You Are", Metheny
python -m arranger corpus --melid 266 --bars -4-1       # the pickups, below bar 0
python -m arranger corpus --melid 218 --section chorus:1  # a solo chorus instead
```

| flag | default | what it does |
|---|---|---|
| `--melid` | — | the transcription to read; required unless `--list` |
| `--list` | — | list all 456 transcriptions and exit |
| `--section` | the head | pick a span: `form:A1`, `chorus:1`, `phrase:2`, `idea:lick` |
| `--lift` | `auto` | `auto`, `none`, `always`, `per-note` — see below |
| `--bars` | the whole span | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--skeleton` | `eighths` | one step per chord / beat / eighth / sixteenth / note |
| `--pick` | `first` | which note to take when one slot holds several |
| `--non-chord-tone` | `extension` | how to harmonise a melody note outside the chord |
| `--fallback` | off | `diminished` — see [the trade-off](#the-fallback-trade-off) |
| `--texture` | `uniform` | `uniform`, `targets`, `walking_bass` — see [texture](#texture) |
| `--fret-min` / `--fret-max` | `2` / `13` | the neck window to aim for |
| `--grips` | all six | which grip families to consider, **most preferred first** |
| `--tab` | `line` | `staff` lays the head on one six-line staff, on its real rhythm |
| `--melody` / `--mutes` | off | with `--tab staff`: add a melody row / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write the head to a file — see [rendering](#rendering) |

**`--section` selects a span, not a form name.** The four kinds are `form:` (an A-block),
`chorus:`, `phrase:` and `idea:`; a `*` glob is allowed (`form:A*` takes every A-block),
and several can be given as one comma-separated selection. A Weimar transcription has no
notated form, so this walks the transcribed sections.

**`--lift` decides whether to transpose the whole head an octave.** `auto` builds the
head twice and keeps whichever voices more steps, ties going to the original; `always`
and `none` force it; `per-note` lifts each note on its own merits — **and it can distort
melodic intervals**, which is why it is not the default.

**`--grips` is ordered.** It is a preference list, not a set: putting `shell` first will
displace a four-note drop-2 whenever the two cost the same.

**The fret window is an aim, not a filter.** A step with no voicing inside your window is
still played, outside it, and the header echoes your window whether or not it was met.

### How the head is found

Not from the form label: on all four "All the Things You Are" transcriptions the real
8-bar head sits in a block the form label does not point at. The head is found on the
**chord progression** — matched modulo transposition, so the same progression returning
in a new key still counts. The command reports the bars and anchor chords it chose, so
you can see the selection and override it with `--bars`.

This is a heuristic and does not land on the head every time: across the corpus 434 of
456 transcriptions yield a head, and the median head is 8 bars.

### Three things to know before you rely on it

**Heads are not harmonically simpler than solos.** This is the most common surprise. A
standard tune is built from passing tones between widely spaced chord tones, so it is
*more* non-chordal, not less — the chord-tone rate for a head is statistically
indistinguishable from solo material. Roughly half the steps need the non-chord-tone
strategy. The measurements are in [docs/corpus.md](docs/corpus.md).

**`--lift auto` may transpose the head an octave.** It is threshold-free, so a head whose
median sits one or two semitones above an arbitrary cut-off cannot defeat it — but it
does move the music. Blue Train's head is lifted, because it dips to E♭3. The decision is
printed on every run.

### The fallback trade-off

**`--fallback diminished` replaces the written chord.** It works mechanically, but
harmonically it rewrites the tune, and on a blues most substitutions land on the tonic,
so the tonic bar stops being a plain dominant. A head is supposed to be the written
tune, so it is **off by default** and the count of steps it *would* rescue is always
reported. Pass it only when you want that colour.

A bar marked `NC` in the database is melody with no harmony; it is played alone on
a single fret rather than harmonised, which is why such a step does not obey the
four-string rule.

## Rendering

`arrange_progression` returns data; every tab renderer is a **pure function that
returns a string and prints nothing**, so you decide how the tab is displayed.

To render a whole progression, use `format_progression`:

```python
from arranger import VoiceLeadingEngine, format_progression

engine = VoiceLeadingEngine()
steps = engine.arrange_progression(
    [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")]
)

print(format_progression(steps))
```

```text
Dm7      D5   x-x-10-10-10-10
G7       B4   13-x-12-12-12-x
Cmaj7    C5   x-x-9-9-8-8
```

This is the compact one-line form, and it is the only shape `format_progression` has.
It also used to take `vertical=True` for a six-line block per chord; that and the
`--vertical` flag that reached it are gone, because `format_tab_staff` below renders a
whole progression as real six-line tab — with the chords on their real beats, which the
block never could.

Steps whose melody is a non-chord tone are annotated with the substitution that was
applied, so a reharmonised passing tone is never silent about itself.

### A whole progression on one staff

`format_progression` gives one line *per chord*. For something you could read off a
page, `format_tab_staff` lays the entire progression along a single six-line staff, in
reading order:

```python
from arranger import format_tab_staff

print(format_tab_staff(steps, show_melody=True))
```

```text
  |4/4              |
  |Dm7   G7    Cmaj7|
  |D5    B4    C5   |
e*|10   -     -8    |
B*|10   -12   -8    |
G |10   -12   -9    |
D |10   -12   -9    |
A |     -     -     |
E |     -13   -     |
```

The chord names sit on a line above, each starting in the column where its shape is
struck, and `e*` marks the string carrying the melody. Above them the **metre** (`4/4`),
written over the first bar only — a time signature holds until it changes — and the
**note value** of every column (`w` whole, `r` rest). Without that row a whole note and a
quarter were drawn identically, since on this grid both were one column of frets; it is
what makes the staff a score rather than a chord list. Pass `show_timing=False` to drop
them, and `beat_type` to state the metre properly — 2/2 is 2/2, not 2/4.

Three options do most of the work:

- **`collapse=True` (the default)** strikes a shape once and lets it ring while the melody
  moves over the same pitches, instead of restriking it on every step. The skeleton voices
  one step per eighth; a player holds the shape rather than hitting it eight times a bar.
  A rest breaks the ring, so the next shape is struck again.
- **`rhythm=True` (the default)** spaces the chords on their real beats, drawing a barline
  every `measures_per_line` bars. This needs each step to carry `bar` and `beat`, which
  the corpus loader supplies; a hand-written progression has no timing and falls back to
  one chord per beat.
- **`show_mutes=False` (the default)** leaves muted strings blank, because in chord-melody
  a voice that is still ringing is not restruck. Pass `True` to spell them out as `x`.

`docs/renderers.md` covers the full set and the ASCII/HTML forms.

From the command line, the same renderer is `--tab staff`:

```bash
python -m arranger corpus --melid 218 --tab staff --melody --bars-per-line 4
```

For a single voicing, `Voicing.tab_string()` gives the one-line form while
`Voicing.tab_block()` (a `List[str]`) and `Voicing.tab()` (the same joined into
one string) give the vertical six-line form. `ArrangementStep.tab_line()` and
`ArrangementStep.tab_block()` do the same for a step.

### MusicXML, for a notation program

`format_musicxml` writes the same arrangement as a real score, so a head can go on
to MuseScore, Sibelius or Final without being retyped. It needs the optional extra
(`pip install '.[xml]'`):

```python
from arranger import write_musicxml

write_musicxml(steps, "head.musicxml", title="Blue Train", subtitle="John Coltrane")
```

The document is a **notation staff** — one staff, in the treble clef a chord-melody
part is written in — carrying the **chord symbols** on each change. The written rhythm
is preserved: each step becomes a note or chord of the length it occupies, a shape that
is *held* rather than restruck becomes one longer note, and an event that runs across a
bar line is tied rather than stretched. A hand-written progression with no timing falls
back to one chord per beat, exactly as the other renderers do.

There is **no TAB staff in the MusicXML**, and that is deliberate. `music21` cannot
write one that a notation program renders correctly — it emits neither the six
`<staff-lines>` a tab staff needs nor a fret and string per note, and the document it
produced still displayed incorrectly in MuseScore 3. For the fingering, use the
[Guitar Pro 5 export](#guitar-pro-5-for-a-tabber) below, which stores a fret and a
string per note natively. The two outputs share their note placement, so a head lands on
the same beats in both.

Two options shape the output:

- **`show_chords=True` (the default)** writes the chord symbols, one per change.
- **`collapse=True` (the default)** writes a held shape once. Pass `False` to hear
  it re-struck on every step.

From the command line it is `--musicxml PATH`:

```bash
python -m arranger corpus --melid 218 --musicxml head.musicxml
```

A chord name music21 cannot classify — the Weimar notation produces several — is
written as text with the root still parsed out, rather than dropped.

### Guitar Pro 5, for a tabber

`write_gp5` writes the same arrangement as a **Guitar Pro 5 file**, to open in Guitar
Pro alongside your own tab. It needs its own extra (`pip install '.[gp]'`):

```python
from arranger import write_gp5

write_gp5(steps, "head.gp5", title="Blue Train", subtitle="John Coltrane")
```

```bash
python -m arranger corpus --melid 218 --gp5 head.gp5
```

GP5 is a *tab* format, so every note carries its own fret and string and a shape
survives the round trip exactly — no re-deriving the fingering from the pitch. Each
step is written on its real beat with the chord name it is sounding above it, a held
shape is one longer note rather than a re-strike, and a repeated melody is a single
struck note, all as in the other two renderers. `tempo`, `beats_per_bar`,
`collapse` and `show_chords` work as they do for MusicXML.

**This is not a replacement for MusicXML.** A `.gp5` file opens in Guitar Pro and
nowhere else, and it has no notation staff; the MusicXML export is still the way into
MuseScore, Sibelius and Final. Use whichever the destination needs — the two are
independent extras, the two outputs share their note placement, and between them they
cover what a two-staff score would have: the fingering here, the notation there.

One difference worth knowing: GP5 has no way to write a short first bar, so a head
starting on an upbeat gets a full first measure with the leading beats empty rather
than an anacrusis. A shape that runs across a bar line is written out in two
measures instead of being tied, because a GP tie across a bar is a slur the player
has to interpret. Neither changes the notes.

## Low-register melodies

Melodies below the high E string's open pitch (`E4`) cannot be voiced on that block. By
default the melody may also be pinned to the B string (voicing on A-D-G-B) and to the
**G string** (voicing on the bottom four strings), which drops the reachable floor to
`G3`:

```python
low = [("D4", "m7", "Dm7"), ("D4", "7", "G7"), ("C4", "maj7", "Cmaj7")]
for step in engine.arrange_progression(low):
    print(step.chord, step.voicing.tab_string(), "melody string",
          6 - step.voicing.soprano_string())
```

```text
Dm7 x-3-3-2-3-x melody string 2
G7  3-x-3-4-3-x melody string 2
Cmaj7 x-2-2-5-x-x melody string 3
```

All three sit in one position on the bottom four strings. Restricting the melody to the
high E and B strings — `top_strings=(5, 4), grips=("drop2",)` — gives three four-note
shapes in a lower position:

```python
for step in engine.arrange_progression(low, top_strings=(5, 4), grips=("drop2",)):
    print(step.chord, step.voicing.tab_string())
```

```text
Dm7 x-3-3-2-3-x
G7  x-2-3-0-3-x
Cmaj7 x-2-2-0-1-x
```

The `Cmaj7` is the interesting one: `x-2-2-5-x-x` is a three-note **6-4-3 shell** on the
D and G strings, because a four-note 6-5-4-3 with the melody on top does not sound good.
There is deliberately no four-note block for a G-string soprano — the G string earns its
place by carrying shells, not chords. Pass `top_strings=(5,)` to restrict voicings to the
traditional high-E block.


## Grips

`arrange_progression` builds **several voicings per step** — every grip that can carry
the melody inside the neck window — and picks between them with one cost function that
weighs fret span first, then position, then how far the hand must move from the previous
chord. The choice is made by the music rather than by a fixed preference list: a chord
can stay where the previous one left the hand.

| grip | voices | what it is |
|---|---|---|
| `drop2` | 4 | the hand-authored drop-2 tables, on 4-3-2-1 or 5-4-3-2, or 5-4-3-2 / 6-4-3-2 with the bass on a lower string |
| `drop3` | 4 | **drop-3** — the third voice down an octave; every other voice is still a chord tone |
| `drop24` | 4 | **drop-2 & 4** — the second *and* fourth voices an octave down |
| `drop2_6432` | 4 | **6-4-3-2** — low E, D, G and B, so the bass can be a root |
| `shell` | 3 | the 3rd and 7th plus one more: 1-2-3, 2-3-4, 5-4-3, **6-4-3** or **5-3-2** |
| `duo` | 2 | the root or 5th in the melody plus the 3rd |
| `interval` | 2 | a 3rd, 6th or 10th below the melody — a *fill*, not a harmony |

The first six are `GRIP_PREFERENCE`, the order they are tried in. `interval` is not in
it, because an interval is a texture rather than a harmony — the `targets` texture offers
it for fills only. `closed` exists as a generator but is left out, because a
close-position chord under a melody cannot be fretted inside the span budget; a caller
who widens `GRIP_MAX_SPAN` reaches it.

`drop3` and `drop24` derive themselves from the close-position stack under the melody,
which keeps every *other* voice a chord tone — measured over every quality and every
melody, they produce zero wrong notes where drop-2's quality-only fallback produces
hundreds. That is what puts a correct shape in the candidate set for the selector to
find. `docs/engine.md` has the derivation and the full cost tuple.

`common_grips.md` is a chart of the drop-2 shapes, **generated** from these tables by
`grip_chart.py` and checked by `make chart-audit`. Do not hand-edit it.

### Six arrangements from one head

Every output below is a real run of the command shown, on the committed score in
`tests/data/`. The first is the default.

**1. Every note in full** — the default `uniform` texture, four notes wherever a four-note
shape exists:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2
```

```text
Gmaj9    D4   3-x-4-4-3-x
Gmaj9    D4   (melody repeated - single note) ----3-
Gmaj9/F# D4   (shell - 3rd & 7th, partial) x-x-4-4-3-x
```

*Expect a full chord under every melody note, the melody in the top voice, and the hand
staying put where it can. A step annotated `shell` or `melody repeated` is the selector
reporting it could not do better there, not a default.*

**2. Chords on the strong beats** — `--texture targets` states a full chord on beats 1
and 3 and fills the rest with a shell, a 3rd/6th, or the melody alone:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --texture targets
```

```text
  texture: targets - a full chord on beats 1 and 3 of 2/2, a shell, a 3rd/6th or the melody alone elsewhere

Gmaj9    D4   5-x-5-4-3-x
Gmaj9    D4   (melody repeated - single note) ----3-
Gmaj9/F# D4   (shell - 3rd & 7th, partial) x-x-4-4-3-x
```

*Expect a lighter arrangement that states the harmony on the beats and lets it ring in
between — closer to how the tune is actually played than a chord on every eighth. The
header always prints the rule, so you can see which arrangement you got.*

**3. A walking bass** — `--texture walking_bass` adds a thumb line on the lowest three
strings under the shell:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --texture walking_bass
```

```text
Gmaj9    D4   (shell - 3rd & 7th, partial) (bass: G2, anchor) 3-x-4-4-3-x
Gmaj9    D4   x-x-x-x-3-x
Gmaj9    D4   (bass: F#2, connect) 2-----
Gmaj9/F# D4   x-x-x-x-3-x
```

*Expect four steps where the melody had three: the bass grid is finer than the melody
grid, so a step can exist for the thumb alone, marked `bass_only`. A bare `2-----` is the
low E and nothing else. The thumb is placed against **the shape the hand is holding**, not
against the melody, so it stays under the position rather than chasing it.*

**4. Shells only** — `--grips shell` reduces every chord to three notes:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips shell
```

```text
Gmaj9    D4   (shell - 3rd & 7th, partial) x-x-4-4-3-x
Gmaj9/F# D4   (shell - 3rd & 7th, partial) x-x-4-4-3-x
```

*Expect an open, unlabelled sound: the 3rd and 7th are what make the chord major or
minor, and leaving out the root lets the player imply it.*

**5. Duos** — `--grips duo` leaves two notes, the melody and the 3rd or 5th:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips duo
```

```text
Gmaj9    D4   (root & 5th duo - partial) x-x-x-4-3-x
Gmaj9/F# D4   (root & 5th duo - partial) x-x-x-4-3-x
```

*Expect the sparsest thing this library will play — the harmony implied rather than
stated, for a solo voice or for leaving room over a band.*

**6. Rewriting unresolved tensions** — `--fallback diminished` substitutes a Barry Harris
dim7 wherever nothing else can voice a melody note:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-4 --fallback diminished
```

```text
  note: diminished fallback replaced the written chord on 1 step(s)

Ebmaj7   D5   x-x-8-8-8-10
Ebmaj7   C5   (non-chord tone -> Eb6/9 via extension) x-8-8-x-8-8
Adim7    B4   (non-chord tone) x-6-7-x-7-7
```

*Expect the tune to change. The written chord is genuinely replaced, which is why the run
says how many — on a head, that is usually a colour you want and not always one you do.*

### The neck window, and why it is not a filter

Every voicing is confined to frets 0–18 and a span of at most 5 (4 for a duo), on a real
string set. `NECK_FRET_MIN`/`NECK_FRET_MAX` — frets 2 to 13 — are the range the selector
*aims* for, not a hard filter: a step with no voicing inside the window is still played,
just outside it, because losing a chord of the tune is worse than being a fret out of
position.

The cost function weighs **fret span above position**, so it prefers a shape the hand can
hold over one nearer the middle of the neck. That was measured, not assumed — the
reasoning and what the reordering cost are in [docs/engine.md](docs/engine.md).

A melody whose only position sits above `HIGH_FRET_LIMIT` is voiced an octave down, so
`step.melody` may be an octave below the written note; the written pitch stays in
`step.original_melody`. See [High melodies](#high-melodies-the-octave-down-move).
## Texture

`texture` decides **what a slot is for** before any voicing is chosen, and it is the one
knob that changes the shape of an arrangement rather than its detail. Three values:

| texture | what a step is |
|---|---|
| `uniform` *(default)* | every melody note gets a full chord |
| `targets` | a full chord on the strong beats, thinner fills between |
| `walking_bass` | a shell under the melody, and a thumb line underneath that |

### `targets` — chords on the strong beats

The selector ranks **completeness above position**, so a bar of running eighths comes out
as eight re-struck four-note chords: a chord list, not an arrangement. Pass each slot's
`(bar, beat, duration)` as `timings` and the engine states a full chord on beats 1 and 3,
filling the rest with a shell, an interval, or the melody alone:

```python
progression = [
    ("C5", "maj7", "Fmaj7"),   # beat 1 - the target
    ("E5", "maj7", "Fmaj7"),   # fill
    ("A4", "maj7", "Fmaj7"),   # fill
    ("F4", "maj7", "Fmaj7"),   # beat 3 - the target
]
timings = [(0, 1.0, None), (0, 1.5, None), (0, 2.0, None), (0, 3.0, None)]

steps = engine.arrange_progression(progression, timings=timings, texture="targets")
for step in steps:
    print(step.beat, step.role, step.voicing.tab_string())
```

```text
1.0 target x-x-7-9-6-8
1.5 fill x-x-x-10-10-12
2.0 fill x-x-x-5-5-5
3.0 target x-7-7-5-6-x
```

*Expect a lighter arrangement that states the harmony on the beats and lets it ring in
between. Each step carries a `role` — `target` or `fill` — and a `metric_weight` (2 on beat
1, 1 on beat 3, 0 elsewhere, −1 when no timing was supplied at all).*

**Timing changes which grips are on the table, not the cost.** That is the design: "play
fewer notes here" is not a preference competing against "stay in position" — it changes
what may be chosen at all, and a term in the cost tuple would let a four-fret position
outbid an entire texture.

**Nothing changes until you ask.** `timings` defaults to `None`, meaning *we were never
told where these notes fall* — not *these notes are weak*. Every slot is then a target and
the output is byte-identical to what it has always been.

**The metre is read, not assumed.** A 3/4 head states its harmony on 1 and 3, while a 2/2
(cut-time) head has only two beats, so only the downbeat is a target. Three of the four
committed test scores are in cut time.

**A fill never costs the tune a chord.** If a fill slot has nothing thin to play, the step
is re-prepared as a principal note rather than skipped — a texture is lighter, never
missing. Over six corpus heads this takes the mean sounding notes per melody note from
**3.86 to 3.39** and four-voice steps from **87% to 51%**, with no head losing a step.

### `walking_bass` — a thumb line under the melody

A walking bass adds notes that are *not* melody at all: on each beat a note from the
low E, A or D string, moving from the tonic towards the next chord as a line rather than
as a grid.

```bash
python -m arranger head tests/data/but_not_for_me.mxl --bars 1-3 --texture walking_bass
```

```text
Bb7      F4   x-x-x-x-x-1
Bb7      G4   (bass: D3, approach) x-5-x-x-x-3
Bb7      F4   x-x-x-x-x-1
Ebmaj    G4   (shell - 3rd & 7th, partial) (bass: Eb3, anchor) x-6-8-8-8-x
Ebmaj    F4   (bass: G2, connect) 3-x-x-x-x-1
Cm7      Eb4  x-x-x-x-4-x
```

Each bass note says what it is *for* in `step.bass_role`, one of `anchor` (the tonic),
`connect` (a passing note between two chords), `approach` (a semitone from the next root),
`enclosure` or `hold` (a repeat, repeated rather than moving).

*Expect **more steps than the melody had** — three steps here for two melody notes,
because the bass grid is finer than the melody grid. A step marked `bass_only=True` exists
for the thumb and nothing above it strikes: the previous shape is held and the melody is
not re-attacked. That is the opposite of `repeated`, not a variant of it.*

The thumb is placed against **the shape the hand is holding**, not against the melody.
Adjacent bass strings are five semitones apart, so "prefer the lowest string" and "stay
where the hand already is" are in permanent opposition; the placement step orders by fret
proximity to the upper voicing and takes the nearest, so the 4th string is used only when
the hand is genuinely low.

A step with no free bass string below the melody keeps its upper voicing and says so
(`no bass string free below the melody for bass ...`) rather than dropping the note.

`docs/open-issues.md` records the two defects this texture has already had, both fixed,
and what they were measured at.

## High melodies: the octave-down move

The B string is five semitones *below* the high E, so the same written pitch sits five
frets **higher** on it — `D5` is fret 10 on the high E but fret 15 on the B. Re-voicing
onto the B string alone therefore pushes the shape further up the neck, not down. The
only way to bring a high melody into a lower position is to drop it an octave.

So `arrange_progression` does exactly that when a melody's *only* available position
sits above `HIGH_FRET_LIMIT` (13). `A5` over `Dm7` can only be voiced at fret 17, so it
is arranged as `A4` in low position:

```python
high = [("A5", "m7", "Dm7")]
for step in engine.arrange_progression(high):
    print(step.chord, step.melody, step.voicing.tab_string(),
          "from", step.original_melody)
```

```text
Dm7 A4 10-x-10-10-10-x from A5
```

The step's `melody` is the pitch that actually sounds; `original_melody` keeps the
written one, and `format_progression` annotates the step with it:

```text
Dm7      A4   (transposed down an octave from A5) 10-x-10-10-10-x
```

Two deliberate limits:

- **It only repositions a voicing that exists.** A melody unreachable at the written
  pitch (`B5` is fret 19, `C6` is fret 20 — both past the end of the board) is still
  skipped with a warning rather than silently respelled, so the real problem stays
  visible.
- **The decision is per step and the melody only.** Unlike `--lift auto` in the corpus
  front end, this does not transpose a phrase as a unit, so a melody that leaps across
  the limit can arrive an octave apart from its neighbour. That is the intended
  trade-off: no step is ever left unplayable, at the cost of one melodic interval.

`get_all_drop2_voicings` is deliberately *not* filtered by fret — it stays pure
candidate generation, and `get_octave_down_candidates` is the separate, explicitly
opt-in entry point for the transposed form.

## Non-chord melody notes

Real melodies do not always land on a chord tone. Bar 2 of "All of Me" moves
`C5 → D5 → C5` over `Cmaj7`, where `D5` is the 9th. Pass `non_chord_tone=` to
`arrange_progression` (or call `is_chord_tone` / `resolve_non_chord_tone`
directly) to choose how such notes are harmonised:

```python
bar_2 = [("C5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7"), ("C5", "maj7", "Cmaj7")]

for strategy in ("extension", "diminished", "sustain", "legacy"):
    steps = engine.arrange_progression(bar_2, non_chord_tone=strategy)
    print(f"{strategy:<11}", steps[1].voicing.tab_string(), steps[1].harmonized_as)
```

```text
extension   x-x-9-9-8-10  Cmaj9
diminished  x-x-9-10-9-10 Bdim7
sustain     x-x-9-9-8-10  None
legacy      x-10-10-x-12-10 None
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
  it. It sounds the melody over a shape built from the chord's *quality* rather than
  its degree, so for `D5` over `Cmaj7` it gives `x-10-10-x-12-10` — `C D G B`, notes
  `Cmaj7` does not contain — and `harmonized_as` stays `None` because nothing was
  reharmonised. That is why it is no longer the default; note also that `sustain` falls
  back to it here, which is why the two rows agree.

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

```bash
make check        # lint + typecheck + test - what CI runs, and what a change must pass
make test         # .venv/bin/python -m unittest discover -s tests -t . -v
make typecheck    # pyright over the modules and tests (must report 0 errors)
make lint         # ruff
make demo         # run the built-in demonstration
make chart-audit  # check common_grips.md against the engine's own tables
make build        # build a wheel into dist/
```

`make check` is the gate. Tests use the standard-library `unittest` (there is no pytest
dependency); type checking uses [pyright](https://pypi.org/project/pyright/) and lint uses
[ruff](https://pypi.org/project/ruff/), both dev-only and deliberately not package
dependencies (`make install-dev`).

`make` prefers the repository's `.venv/bin/python`; override it with
`make test PYTHON=python3`. The equivalent long form is
`.venv/bin/python -m unittest discover -s tests -t . -v` run from the repository root
(`-t .` is what lets `tests.support` import as a package module).

**CI runs `make check` on Python 3.11 through 3.14**, with both optional extras installed
so the guarded tests are not silently skipped. One thing to know: `wjazzd.db` is 42 MB and
gitignored, so **85 of the 787 tests are skipped on a clean clone** — a green check does
not mean the Weimar path was exercised. A separate `corpus` job covers those, on manual
dispatch only.

The engine lives in the `arranger` package, twelve modules in a strict dependency order
that `tests/test_package_dag.py` asserts from the AST. `wjazzd.py` is separate, optional
glue that nothing in the package imports, so the library works with no database present.
See `AGENTS.md` for the module map and the conventions, and [docs/](docs/) for the
reasoning behind the engine, the renderers and the corpus.

## Known limitations

- Voicings use two to four strings, never all six. The melody may be on the high E, B or
  G string; the A string and low E are inner voices only, so no grip puts the soprano on
  either. There are no barres, and a full six-string voicing is not modelled. One grip —
  the 6-4-3 shell — deliberately skips the A string.
- Melodies are confined to `G3`–`Bb5`.
- A fixed maximum fret span of 5 (4 for a duo and an interval) and a fret range of 0–18
  are assumed. `closed` is generated but left out of the default grip list, because a
  close-position chord under a melody cannot be fretted inside that budget.
- Non-chord melody notes are handled only for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths and the
  half-diminished 9th) plus dim7; anything else keeps the quality-only fallback.
- A chord tone with no matching inversion in the hand-authored drop-2 tables — a 9th in
  the melody of a 13 chord, for instance — falls through to the quality-only fallback,
  which can sound a note the chord does not contain. The selector rejects such a shape
  whenever a correct one exists, so an *arrangement* only hears it when nothing else is
  playable, but `get_drop2_voicings` still offers it. The shells, duos and 6-4-3 grip are
  unaffected: they build themselves from the chord's tones.
- The `sustain` strategy is structural — the API takes only `(note, quality, name)`
  triples, so rhythm and duration cannot be used to spot a brief passing tone.
- The neck window is a preference, not a filter, so `--fret-min`/`--fret-max` may not be
  honoured where nothing playable exists inside it. The header echoes the window whether or
  not it was met.
- From the corpus side: the head selector is a heuristic and misses the head on some
  transcriptions; `wjazzd.db` is a 42 MB download that must be supplied separately; a slash
  bass is honoured as a preference rather than a hard constraint. See
  [How the head is found](#how-the-head-is-found).
- No release has been published to PyPI.

## License

MIT. See [LICENSE](LICENSE) for the full text.

The optional `gp` extra pulls in [PyGuitarPro](https://pypi.org/project/PyGuitarPro/),
which is LGPL-3.0. That is deliberately kept out of the runtime dependencies and
behind a lazy import, so this project is not a combined work of PyGuitarPro and
stays permissively licensed. `tabgp` also writes no PyGuitarPro code into this
repository.
