# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Given a progression of `(melody note, chord quality, chord name)` triples, `arranger`
builds voicings in several grip families, pins the melody to the soprano string, and
picks among them with one position-aware cost function. It can also read a written head
out of a MusicXML file and arrange that.

- **Seven grip families**, drop-2 first: `drop2`, `closed`, `drop3`, `drop24`,
  `drop2_6432`, `shell` and `duo` — four-note voicings down to two-note guide-tone
  pairs. Every one sounds the chord's **3rd and 7th**, the two notes that decide whether
  the ear hears a major or a minor chord; a `duo` sounds one of them, under any chord
  tone, since two notes is the floor this library will play ([grips](#grips)).
- **Melody pinned to the soprano**, on the high E, B or G string, so a low melody can
  still be harmonised in position.
- **Playable or absent.** Every voicing sits in frets 0–18 within a 5-fret span (4 for
  the two-note grips) on a real string set, and no step needs more than four fingers or
  a fifth fret. The neck window is a *preference, not a filter* — losing a chord of the
  tune is worse than being a fret out of position.
- **Non-chord melody notes** are reharmonised as an extension, via the Barry Harris
  6/dim7 substitution, or by holding the chord shape under a passing tone
  ([non-chord melody notes](#non-chord-melody-notes)).
- **Five orthogonal axes**, not one mode: where the notes fall, who plays the bottom,
  which voices the guitar plays, which degrees a non-singing part states, and where in
  the bar a chord lands ([the five axes](#the-five-axes)).
- **Heads from real sources** — a MusicXML score, read as the harmony *timeline* it is
  rather than as a chord attribute on each note.
- **Dependency-light**: Python 3.11+ and [musthe](https://pypi.org/project/musthe/) only.
  Reading a MusicXML head needs no extra at all; MusicXML *export* and Guitar Pro export
  each live behind their own optional extra.

> The **distribution** is named `jazz-arranger` (the PyPI name `arranger` is already
> taken by an unrelated project). The **import** name is simply `arranger`.

Why any of it is the way it is lives in [`docs/`](docs/): [engine.md](docs/engine.md) (the
selector, texture, the cost tuple), [generated-grips.md](docs/generated-grips.md) (which
chord tones a shape states), [renderers.md](docs/renderers.md) (tab, MusicXML, GP5),
[comping-styles.md](docs/comping-styles.md) and [voices-axis.md](docs/voices-axis.md) (the
comping axes), [fingering.md](docs/fingering.md) and [open-issues.md](docs/open-issues.md).

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

Each step is an `ArrangementStep` (`chord`, `melody`, `voicing`, plus the non-chord-tone fields
`non_chord_tone`, `strategy` and `harmonized_as`); the `voicing` is a `Voicing` with `frets`
(six entries, `-1` = muted), `top_fret`, `avg_fret` and helpers such as `tab_string()`,
`fret_span()`, `midi_notes()`, `pitch_classes()` and `soprano_string()`.

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
  2/2, Eb major, 80 melody note(s), bars 1-32; neck window: frets 2-13; grips: drop2, closed, drop3, drop24, drop2_6432, shell, duo
  note: 15 rests and unpitched notes

Bb7      F4  5    6-x-6-7-6-x        (harmony under 5 - 4 voices)
Bb7      G4  13   6-x-6-7-8-x        (non-chord tone -> Bb13 via extension - 4 voices - the chord tones it leaves out are 9 & 5)
Bb7      F4  5    6-x-6-7-6-x        (harmony under 5 - 4 voices)
Ebmaj    G4  3    6-x-8-8-8-x        (harmony under 3 - 4 voices)
Ebmaj    F4  9    6-x-8-8-6-x        (non-chord tone -> Ebadd9 via extension - 4 voices - the chord tone it leaves out is 3)
```

Both forms of the format are read: a bare `.musicxml` document and a zipped `.mxl`
container, which is resolved through its `META-INF/container.xml` rather than by
taking the first XML file out of the archive.

**It needs no optional dependency.** The exporter wants `music21`; the importer wants `zipfile`
and `xml.etree`, which are in the standard library, so a plain `pip install jazz-arranger` can
read a score. The scores `tests/test_headxml.py` reads are committed in `tests/data/` and that
module is not `skipUnless`-guarded at all, so a clone runs the whole thing.

**The score's repeats and endings are honoured.** A backward repeat plays its section
again, and a 1st/2nd ending is taken in turn — so `heres_that_rainy_day`, written as 36
bars, is arranged as the **66** a player hears (`1-30, 31-32, 1-30, 33-36`). The repeat
lands in the output too: `--musicxml`, `--gp5`, `--html` and `--tab staff` write the
**written** 36 bars with the `|:` / `:|` signs and the `1.` / `2.` brackets, so the file
is a score a player reads rather than the played bars written out with the repeat on top.
(The plain `--tab line` listing still shows every bar the arrangement plays.)

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --tab staff --melody
python -m arranger head tests/data/i_was_doing_all_right.mxl --bars 1-3 --html head.html
```

### The flags

| flag | default | what it does |
|---|---|---|
| `--part` | the melody part | a `<score-part>` id, when a score has several |
| `--bars` | the whole head | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--non-chord-tone` | `extension` | how to harmonise a melody note outside the chord |
| `--fallback` | off | `diminished` — see [non-chord melody notes](#non-chord-melody-notes) |
| `--texture` | `uniform` | `uniform`, `targets`, `walking_bass` — see [texture](#texture) |
| `--bass` | follows `--texture` | `none`, `anchors`, `walk` — see [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| `--voices` | `auto` (all four) | any subset of `soprano,alto,tenor,bass` |
| `--harmony` | `auto` (= `guide`) | `full`, `guide`, `shell_root`, `root` |
| `--grid` | `every_note` | `every_note`, `freddie`, `charleston`, `joe_pass`, `final_and` — see [the grid](#where-a-chord-falls-the-grid-axis) |
| `--fret-min` / `--fret-max` | `2` / `13` | the neck window to aim for |
| `--grips` | all seven | comma-separated grip families, **most preferred first** — `--grips shell,duo` |
| `--tab` | `line` | `staff` lays the head on one six-line staff, spaced on its real rhythm |
| `--melody` / `--mutes` | off | with `--tab staff`: add a melody row / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write the head to a file — see [rendering](#rendering) |

Five of those flags are the library's own axes — `--texture`, `--bass`, `--voices`,
`--harmony` and `--grid` — described once in [the five axes](#the-five-axes).

**Every written note sounds.** There is no reduction: `arranger head` plays the tune as
written, one step per note, each on the beat it was written on. Where the *chords* fall
is a separate question — the `grid=` axis — so a note is never quantised onto a grid and
dropped for sharing a slot with another.

**`--grips` is ordered.** It is a preference list, not a set: putting `shell` first will
displace a four-note drop-2 whenever the two cost the same. Spell the families
comma-separated, as the flag's own default does — `--grips drop2,drop3` is two families,
and `--grips drop3,drop2` is the same two in the other order, which is not the same
request.

### Five things reading a score requires

**The harmony is a timeline.** A `<harmony>` precedes the note it governs, several can share
a bar, and a bar can carry none — so a chord is *held* until the next one replaces it.

**The metre is the notated one.** `beat` is the beat *within* the bar in notated beats, and
both numbers in the signature are needed: the count says which beats exist, the denominator
how long one lasts. A 3/4 bar's eighths fall on 1.0, 1.5, 2.0, 2.5, 3.0 and 3.5; reading the
count as the denominator makes every note of a 3/4 head a quarter of a beat early.

**The key signature is read, and written back**, so a tune in three flats exports as a tune in
three flats. A score that omits `<key>` is C major.

**The tune is the top note of a chord.** MusicXML does not order a group by pitch, and in a
chord-melody part the first member is the lowest note. Everything else is counted in
`skipped`, not dropped.

**A chord this library cannot voice is counted, not guessed.** `Neapolitan` is a real kind and
a real chord, but not one this library holds under a melody, so it is listed in
`Head.unmapped` and the run says so.

[docs/renderers.md](docs/renderers.md) has the importer's own traps.

### It is the same arrangement code

A head read from a score is voiced by `arranger.slots.arrange_slots` — the engine's own slot
layer, and the only step loop in the project. The non-chord-tone strategies, the opt-in
diminished retry, the repeated-melody hold and the walking bass are therefore the engine's
rather than the importer's; only the *selection* is the importer's business.

```python
from headxml import load_musicxml, head_skeleton

head = load_musicxml("tests/data/but_not_for_me.mxl")   # melody, timing, chords
print(head.title, head.beats_per_bar, len(head))
for triple, bar, beat, duration in head_skeleton(head):
    print(bar, beat, triple)
```

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
Dm7      D5  Root x-x-10-10-10-10    (harmony under Root - 4 voices)
G7       B4  3    13-x-12-12-12-x    (harmony under 3 - 4 voices)
Cmaj7    C5  Root x-x-9-9-8-8        (harmony under Root - 4 voices)
```

This is the compact one-line form, and it is the only shape `format_progression` has.
For a whole progression as real six-line tab — with the chords on their real beats — use
`format_tab_staff` below.

Every step is annotated. A melody note that is a chord tone names the degree it is
(`(harmony under b7)`), a non-chord tone names the substitution that was applied, and the
**shape** says how many voices it states and why not more — `(shell - 3rd & 7th, partial
- 3 voices: the 4-voice voicing 2-x-1-2-0-x lies outside the neck window)` is the answer
to "where did the rest of the chord go?". A shape the engine did *not* choose carries no
such clause: a comping part and a texture fill are thin by request, not by limit. Two
more facts get said out loud where the tab cannot show them: a slash chord whose written
bass no shape reaches (`the written bass F# is not sounded - the lowest voice (D4) is 4
semitones from it`), and a step the guitar is *silent* at, which the grid sometimes asks
for (`the guitar rests here - the grid places no chord`).

### A whole progression on one staff

`format_progression` gives one line *per chord*. For something you could read off a page,
`format_tab_staff` lays a whole part along a single six-line staff, in reading order — here the
first bar of a committed score, whose metre the caller passes in:

```python
from headxml import arrange_xml_head
from arranger import format_tab_staff

steps, head, warnings = arrange_xml_head("tests/data/but_not_for_me.mxl", section=(0, 2))
print(format_tab_staff(steps, beats_per_bar=head.beats_per_bar, beat_type=head.beat_type))
```

```text
e |-----------------|---------|
B*|-----6---8---6---|---------|
G |-----7---7---7---|---------|
D |-----6---6---6---|---------|
A |-----------------|---------|
E |-----6---6---6---|---------|
```

**The default output is the tab and nothing else** — six string rows, the frets sitting in a
drawn line of dashes, a `|` closing every bar, and a `*` on the string the melody is on, which
is the B string whenever the shape puts it there rather than the high E.

**Width is duration.** A bar is a sixteenth-note grid and a note occupies as much of it as it
sounds for, so the tab says how long everything sounds without a rhythm row: a half note is
drawn twice as wide as a quarter, and the dashes after a fret are the note still ringing. A
pickup keeps the rest in front of it, and the **metre is the caller's**: pass `beats_per_bar`
and `beat_type`, or a 2/2 head is drawn in 4/4.

Four flags add the annotation a score carries and a tab does not, all off by default:
`show_chords` (chord names on a line above, each starting where its shape is struck),
`show_melody` (a line of melody note names), `show_timing` (the **metre** over the first bar and
the **note value** of every column — `w` whole, `r` rest, `~` held — which needs
`step.duration` and so appears for a head rather than a hand-written progression, and without
which a whole note and a quarter are drawn identically), and `show_mutes` (unsounded strings as
`x`, because a voice that is still ringing is not restruck).

```python
print(format_tab_staff(steps, beats_per_bar=head.beats_per_bar, beat_type=head.beat_type,
                       show_chords=True, show_melody=True, show_timing=True))
```

```text
  | 2/2                     |             |
  | r     q     q     q     | r           |
  |       Bb7               |             |
  |       F4    G4    F4    |             |
e |-------------------------|-------------|
B*|-------6-----8-----6-----|-------------|
G |-------7-----7-----7-----|-------------|
D |-------6-----6-----6-----|-------------|
A |-------------------------|-------------|
E |-------6-----6-----6-----|-------------|
```

So the tab carries the metre, the pickup rest before the first chord, the note values, and the
one `Bb7` shape that sounds the same pitches while the tune steps away and back over it.

Each **system** is ruled to its own width — a long chord name widens the bar it is in and no
other — and `measures_per_line` sets how many bars go on one line before the staff wraps.

Two more options shape the vertical form: **`collapse=True`** (the default) strikes a shape once
and lets it ring while the melody moves over the same pitches, a rest breaking the ring; and
**`rhythm=True`** (the default) spaces the chords on their real beats, which needs each step to
carry `bar` and `beat` — supplied by `arrange_xml_head` — and falls back to one chord per beat
for a hand-written progression.

From the command line the same renderer is `--tab staff`:

```bash
python -m arranger head but_not_for_me.mxl --tab staff --melody --bars-per-line 4
```

For a single voicing, `tab_string()` gives the one-line form and `tab_block()` / `tab()` the
vertical six-line one; `ArrangementStep.tab_line()` and `tab_block()` do the same for a step.
[docs/renderers.md](docs/renderers.md) covers the full set and the ASCII/HTML forms.

### MusicXML, for a notation program

`format_musicxml` writes the same arrangement as a real score, so a head can go on
to MuseScore, Sibelius or Final without being retyped. It needs the optional extra
(`pip install '.[xml]'`):

```python
from arranger import write_musicxml

write_musicxml(steps, "head.musicxml", title="Blue Train", subtitle="John Coltrane")
```

The document is a **notation staff** — one staff, in the treble clef a chord-melody part is
written in — carrying the **chord symbols** on each change. It is written **an octave above**
what it sounds, as guitar music is: the part declares the guitar's transposition, so a
notation program notates the notes up the staff and plays them back at concert pitch. The
written rhythm is preserved: each step becomes a note or chord of the length it occupies, a
shape that is *held* rather than restruck becomes one longer note, and an event running across
a bar line is tied rather than stretched. A hand-written progression with no timing falls back
to one chord per beat, as every renderer does.

There is **no TAB staff in the MusicXML**, deliberately: `music21` cannot write one that a
notation program renders correctly. For the fingering, use the [Guitar Pro 5
export](#guitar-pro-5-for-a-tabber), which stores a fret and a string per note natively.
`show_chords=True` and `collapse=True` are the defaults; from the command line it is
`--musicxml PATH`:

```bash
python -m arranger head but_not_for_me.mxl --musicxml head.musicxml
```

A chord name music21 cannot classify — some published notation produces several — is written
as text with the root still parsed out, rather than dropped.

### Guitar Pro 5, for a tabber

`write_gp5` writes the same arrangement as a **Guitar Pro 5 file**, to open in Guitar Pro,
TuxGuitar or any other GP5 reader alongside your own tab. It needs its own extra
(`pip install '.[gp]'`):

```python
from arranger import write_gp5

write_gp5(steps, "head.gp5", title="Blue Train", subtitle="John Coltrane")
```

```bash
python -m arranger head but_not_for_me.mxl --gp5 head.gp5
```

GP5 is a *tab* format, so every note carries its own fret and string and a shape survives the
round trip exactly — no re-deriving the fingering from the pitch. Each step is written on its
real beat, with the chord name above the beat where the chord changes, and a held shape is one
longer note rather than a re-strike. `tempo`, `beats_per_bar`, `collapse` and `show_chords`
work as they do for MusicXML.

**This is not a replacement for MusicXML.** A `.gp5` file opens in Guitar Pro, TuxGuitar, and
the browser and mobile tab readers that import GP5 — the format is widely read. What it carries
is tab and no notation staff, so the MusicXML export is still the way into MuseScore, Sibelius
and Final. Between them they cover what a two-staff score would have: the fingering here, the
notation there.

One difference worth knowing: GP5 has no way to write a short first bar, so a head starting on
an upbeat gets a full first measure with the leading beats empty rather than an anacrusis. A
shape that runs across a bar line is written as two tied measures, and a dotted length is
written as tied halves, the format having no note for either. Neither changes the notes.

## One head, seven ways

Every run below is on a committed score in `tests/data/`, and each is a single flag
changed. The output of each is shown in the section linked:

| ask | flag | output shown in |
|---|---|---|
| every note in full — the default | *(nothing to pass)* | [quick start](#quick-start) |
| chords on the strong beats | `--texture targets` | [texture](#texture) |
| a walking bass line under the melody | `--texture walking_bass` | [texture](#texture) |
| shells only | `--grips shell` | [grips](#grips) |
| guide-tone duos | `--grips duo` | [grips](#grips) |
| the tune on its own | `--voices soprano` | [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| a reduced chord where nothing else fits | `--fallback diminished` | [non-chord melody notes](#non-chord-melody-notes) |

## The five axes

`texture=`, `bass=`, `voices=`, `harmony=` and `grid=` answer five different questions
and are **orthogonal**, so a band setting is a combination rather than a mode:
`--bass none --voices none` is a bassist on the root, a horn on the melody, and the
guitar comping guide tones between them.

| axis | the question it answers | values |
|---|---|---|
| `texture=` | where notes fall — how thick the left hand is | `uniform`, `targets`, `walking_bass` |
| `bass=` | who plays the bottom | `none`, `anchors`, `walk` |
| `voices=` | which voices the guitar plays | any subset of `soprano`, `alto`, `tenor`, `bass` |
| `harmony=` | which **degrees** a part states when it is not singing | `full`, `guide`, `shell_root`, `root` |
| `grid=` | where in the bar a chord falls | `every_note`, `freddie`, `charleston`, `joe_pass`, `final_and` |

**Each is inert until you ask for it.** `texture` defaults to `uniform`, `bass` to
whatever the texture already implies, `voices` to `auto` (all four — the historical
chord-melody), `harmony` to `auto` (= `guide`) and `grid` to `every_note`, which is what
the library already did. Nothing moves until you name something else.

Two of them need a caveat. `harmony=full` is the whole-chord chord-melody, which the
ordinary grip route voices; the comping route has no implementation of it, so asking for
it on a comping part is answered with `guide` today
([open issue 3](docs/open-issues.md)). And `texture=` changes which grips are on the
table rather than their cost: "play fewer notes here" is not a preference competing
against "stay in position", so it is a change to what may be chosen at all, not a term in
the cost tuple.

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

Expect a lighter arrangement that states the harmony on the beats and lets it ring in
between. Each step carries a `role` — `target` or `fill` — and a `metric_weight` (2 on beat 1,
1 on beat 3, 0 elsewhere, −1 when no timing was supplied at all).

**The metre is read, not assumed.** A 3/4 head states its harmony on 1 and 3, while a 2/2
(cut-time) head has only two beats, so only the downbeat is a target. Three of the seven
committed heads are in cut time.

**A fill never costs the tune a chord.** If a fill slot has nothing thin to play, the step is
re-prepared as a principal note rather than skipped — a texture is lighter, never missing. The
measured effect is in [docs/engine.md](docs/engine.md).

### `walking_bass` — a thumb line under the melody

A walking bass adds notes that are *not* melody at all: on each beat a note from the low
E, A or D string, moving from the tonic towards the next chord as a line rather than as a
grid.

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --texture walking_bass
```

```text
Gmaj9    D4  5    3-x-4-4-3-x        (shell - 3rd & 7th, partial - 3 voices, the most this palette offers) (bass: G2, anchor)
Gmaj9    D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most a fill's palette offers)
Gmaj9    D4  5    2-x-x-x-x-x        (harmony under 5 - melody alone, the most a fill's palette offers - the shape above is held) (bass: F#2, connect)
Gmaj9/F# D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most a fill's palette offers - the written bass F# is not sounded - the lowest voice (D4) is 4 semitones from it)
```

Expect **more steps than the melody had** — four here for three melody notes, because the bass
grid is finer than the melody grid. A step marked `bass_only=True` exists for the thumb and
nothing above it strikes: the previous shape is held and the melody is not re-attacked.

Each bass note says what it is *for* in `step.bass_role`: `anchor` (the tonic), `connect` (a
passing note between two chords), `approach` (a semitone from the next root), `enclosure`, or
`hold` (a repeat). The thumb is placed against **the shape the hand is holding**, not against
the melody: adjacent bass strings are five semitones apart, so "prefer the lowest string" and
"stay where the hand already is" are in permanent opposition, and the placement step takes the
nearest fret to the upper voicing.

A step whose bass note cannot be played keeps its upper voicing and says so rather than writing
a tab nobody can finger (`no playable bass note for bass ... - no free string below the melody,
no octave of that pitch below the shape, or the hand would need a fifth fret`). The commonest
case in practice is the middle one; the counts over the committed heads are in
[docs/open-issues.md](docs/open-issues.md) item 2, with item 1 for the melody-skipped bar.

## Who plays which voice: `bass` and `voices`

`texture` and `bass` answer two separate questions — *where do notes fall* and *who plays
the bottom* — and `voices` adds a third: **who plays the tune**.

`bass` has three values: `none`, `anchors` (a root or 5th on the strong beats) and `walk`
(a note on every beat). Its default follows what you asked for rather than being a
constant: `walking_bass` walks, and so does a melody-only selection that names the bass
voice (`--voices soprano,bass`), while everything else gets none. An unknown spelling
raises, and a combination the left hand cannot accommodate is **refused with a warning**,
the arrangement proceeding without a thumb line — a walking line with gaps in it is worse
than no line, and losing the bass costs less than losing the tune.

### Which degrees a non-singing part states: `harmony=`

`harmony` is read only when the guitar has no tune of its own, so it composes with
`--voices` rather than competing with it: `voices` says *how many* notes and whether the
soprano is ours, `harmony` says *which degrees those notes are*.

| `harmony=` | the part sounds | needs |
|---|---|---|
| `guide` (the default) | the 3rd and the 7th — the notes that say major or minor | two notes |
| `shell_root` | both guide tones **and** a root or 5th underneath them | three notes |
| `root` | a root, or a 5th where the root is out of reach — a bass note on its own | `--voices bass` alone |
| `full` | the whole chord | the ordinary chord-melody route — see [the five axes](#the-five-axes) |

`--harmony shell_root --voices alto,tenor,bass` is a horn on the tune with the guitar
stating quality *and* root underneath; it needs the three notes, and asking for it with
two is refused with a warning rather than quietly thinned. On an arrangement where the
guitar *is* singing, `--harmony` does nothing at all — for that, a chord-melody on shells
is `--grips shell`, which is a grip choice rather than a degree family and keeps the melody
pinned to the top string.

`--bass none` and `--voices alto,tenor` together are the ensemble this library was asked
for: a bassist on the root, a sax on the melody, and the guitar comping the two middle
voices. Each is chosen separately because each is a different decision — "I'm next to a
bass player so I want none of the 1s and 5s and none of the walking motion" is `bass=none`,
"and the melody isn't mine either" is dropping `soprano` from `voices`.

### Which voices the guitar plays

`--voices` takes a **comma-separated list of the SATB voices**, because the question a
player asks is never "how many notes" but *which voices am I playing*:

| `--voices` | notes | the part |
|---|---|---|
| `auto` *(default)* | 4 | all four voices — the historical chord-melody |
| `none` | 2 | shorthand for `alto,tenor` |
| `alto,tenor` | 2 | the two middle voices |
| `alto` | 1 | one guide tone, high on the neck |
| `bass` | 1 | one note in a **bass register**, root or 5th |

Order does not matter (`tenor,alto` and `alto,tenor` are the same request) and neither do
capital letters or stray spaces. An unknown voice name is an error rather than a silently
dropped voice.

**Naming one voice says *which* one, and `bass` is not the same request as `alto`.** `alto`
and `tenor` alone are a guide tone under somebody else's melody — the 3rd, on a high string,
which is where a player puts one. `bass` alone is the bottom of the band: it sounds the
**root, or the 5th where the root is unreachable**, on the low E, A or D. Both are one note, so
the arity cannot tell them apart. `--voices bass` is a bass *line* and states nothing about the
chord's quality; name an inner voice as well if you want the quality said.

```bash
python -m arranger head tests/data/but_not_for_me.mxl --voices bass
```

```text
Bb7      F4  5    x-x-3-x-x-x        (comping - 5; the guitar does not play the tune)
Bb7      G4  13   x-x-3-x-x-x        (comping - 5; the guitar does not play the tune - non-chord tone -> Bb13 via extension)
Ebmaj    G4  3    6-x-x-x-x-x        (comping - 5; the guitar does not play the tune)
```

One note per step, on the low E, A or D: the **lowest voice of the shape**, taken from
whatever reaches it — the root where that is convenient (`Bb7` gives `Bb`, not the `D` a
guide-tone shape would), and the 5th where it is not (every `Ebmaj` above). The annotation
names the degrees actually sounding, so the line reads for itself. The melody column is
the *written* melody, which this guitar is not playing (`melody_voiced` is `False`); it is
still on the step so the band can line up against it.

Because the guitar comps under the *written* melody, a melody note outside the chord makes
the part restate its chord rather than ignore it, and each such chord is reported: a run
with `--voices bass` prints one `comping Bb7 as Bb13 (extension) to accommodate the melody
note G4` style warning per substituted chord.

`bass` is only treated this way when named **alone**. `--voices tenor,bass` and
`--voices alto,tenor,bass` are a duo and a shell, and their lowest note belongs to the
shape's own string set.

### `voices=none` — guide-tone comping

With `voices=none` the guitar stops singing and states the chord instead. The shape is a
**shell**: the 3rd and the 7th, plus one more. Those are the two notes that decide whether
the ear hears a major or a minor chord, and with no melody to support them there is nothing
to add — a fourth voice would be the root or the 5th, which carry no information about the
chord's quality.

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 \
    --texture targets --voices alto,tenor --bass none
```

```text
Gmaj9    D4  5    x-x-x-x-7-7        (comping - 3 & 7; the guitar does not play the tune)
Gmaj9    D4  5    x-x-x-x-7-7        (comping - 3 & 7; the guitar does not play the tune)
Gmaj9/F# D4  5    x-x-x-x-7-7        (comping - 3 & 7; the guitar does not play the tune)
```

Expect **two** notes per step — one per voice you named. `--voices alto` gives one and
`--voices alto,tenor,bass` gives three; the arity follows the selection rather than a
constant, because a part sounding more notes than the caller named is a voice somebody else
was supposed to have. `step.melody` still carries the note the horn is playing, and
`step.melody_voiced` is `False` because the guitar is not the one playing it — the first is
the written tune, the second is who sounds it.

**The shape is chosen from the chord alone.** `get_comping_voicings` takes no melody argument,
and asking it for `D5` and `G3` under the same chord returns the *identical* candidate set. A
chord tone in the shell may therefore land on the same pitch class as the melody: unremarkable,
since it is the guide tone the ear needs anyway. Every quality the engine can voice has a
comping shape in some playable position, checked over `CHORD_TONES_FROM_ROOT`. A quality with
no readable root still gets nothing: a shell is a claim about *this* chord's 3rd and 7th, and
guessing them without a root is how a wrong note gets in.

**`texture` still decides where the chords go.** The axes are independent, not one mode
between them: `--texture targets --voices none` gives a shell on beats 1 and 3 and a
thinner shell between, with the horn's line untouched throughout.

**A repeated melody holds the whole shape.** Normally a repeat is a soprano-only
re-strike with the rest muted — but there is no soprano to re-strike when the guitar isn't
singing, so the shape is held instead, rather than the guitar playing a moving line on
exactly the beats where the arrangement handed the tune away.

### The tune on its own

`voices=soprano` is the melodic voice and nothing else — every slot is the melody alone,
and `soprano,bass` is the same line with a walking thumb under it:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --voices soprano
```

```text
Gmaj9    D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most this palette offers)
Gmaj9    D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most this palette offers)
Gmaj9/F# D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most this palette offers - the written bass F# is not sounded - the lowest voice (D4) is 4 semitones from it)
```

A chord name is still printed above each step as context; nothing under it is being voiced.
An `NC` bar under a comping selection is reported rather than quietly dropped: there is no
chord, so there are no guide tones, and the guitar is genuinely silent while the horn is
not.

## Where a chord falls: the `grid` axis

`--harmony` says *which degrees* a stab states and `--voices` says *whether the guitar is
singing*. `--grid` is the third question: **where in the bar a chord lands.**

| `--grid` | a chord falls on |
|---|---|
| `every_note` (the default) | every written melody note |
| `freddie` | every beat of the notated bar |
| `charleston` | beat 1, and the upbeat of beat 2 |
| `joe_pass` | the upbeat of every beat |
| `final_and` | the upbeat of the bar's **final** beat |

**The positions are bar-relative, which is what lets one name work in any metre.** "the
upbeat of the final beat" is 4.5 in 4/4, 2.5 in 2/2 and 3.5 in 3/4 — the same musical idea
at three different beat numbers. Spelling the pattern as a literal beat (`beat 4`) would
make it look, on a 2/2 head, like a pattern naming a beat that does not exist.

**What happens to a note with no chord on it depends on who is singing**, which is the one
place this axis needs two answers rather than one:

- **guitar singing** — the note of the tune still sounds, on its own. No note is ever
  dropped: a chord-melody under `--grid joe_pass` plays the melody throughout and places
  chords only on the ands.
- **guitar comping** (`--voices alto,tenor`) — the guitar is **silent** on that beat,
  because the melody belongs to the horn and there is nothing for the guitar to add. The
  step is still emitted, so the part keeps its position in the bar and lines up against the
  tune; it draws as an empty column.

**The grid places chords, not the thumb.** The walked-beat grid the thumb reads is its
own, so a thumb sounds on beats where the guitar strikes no chord at all — the
`bass_only` steps above are exactly that. What the grid *does* change is the shape the
thumb is placed against, so a different chord above it can move the note or refuse it:
measured on `but_not_for_me` with `--texture targets --bass walk`, `--grid freddie` walks
three more beats than `--grid every_note`, all of them downbeats the melody skips.

A **free-form grid** — naming positions directly, rather than choosing a row — is not built
yet. See [docs/comping-styles.md §4.2](docs/comping-styles.md) for the design.

## Grips

`arrange_progression` builds **several voicings per step** — every grip that can carry the
melody inside the neck window — and picks between them with one cost function: a chord can
stay where the previous one left the hand.

| grip | voices | what it is |
|---|---|---|
| `drop2` | 4 | four-note drop-2 shapes on the four strings below the soprano, or with the bass moved to a lower string (skipping the D, or the A) |
| `closed` | 4 | **close position** — the chord tones stacked tightest under the melody, no voice dropped (e.g. `x-x-5-4-3-2`) |
| `drop3` | 4 | **drop-3** — the third voice down an octave; every other voice is still a chord tone |
| `drop24` | 4 | **drop-2 & 4** — the second *and* fourth voices an octave down |
| `drop2_6432` | 4 | **6-4-3-2** — low E, D, G and B, so the bass can be a root |
| `shell` | 3 | the 3rd and 7th plus one more: 1-2-3, 2-3-4, 5-4-3, **6-4-3**, **5-3-2** and **1-3-4** |
| `duo` | 2 | the chord's guide tone — the 3rd, or the 4th on a sus chord — under any chord tone |
| `interval` | 2 | a 3rd, 6th or 10th below the melody — a *fill*, not a harmony |

The first seven are `GRIP_PREFERENCE`, and that one order does both jobs: it is the order the
families are tried in **and** the order an exact tie between two equal-cost shapes is broken
in — there is no separate grip term in the cost function. It cannot reorder a complete chord
against a partial one, though: a shape's note count is a criterion of its own, so a four-note
shape always beats a shell that costs the same. `interval` is not in it, because an interval
is a texture rather than a harmony — the `targets` texture offers it for fills only.

`closed` sits **second**, right after `drop2`: it is the tightest shape there is, so where a
melody can fret it at all it beats the other four-note families on a tie. Most melodies cannot
— a close-position chord under a melody is a seventh or more of pitch on four strings only four
or five semitones apart in tuning — so it is usually simply never generated rather than
generated and rejected.

`drop3` and `drop24` derive themselves from the close-position stack under the melody, which
keeps every *other* voice a chord tone — measured over every quality and every melody, they
produce zero wrong notes where drop-2's quality-only fallback produces hundreds.
[docs/engine.md](docs/engine.md) has the derivation and the cost tuple, and
[docs/generated-grips.md](docs/generated-grips.md) the rule that decides which chord tones a
shape states.

Two of the families are thin by design, and the run says so:

**Shells** — `--grips shell` reduces every chord to three notes:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips shell
```

```text
Gmaj9    D4  5    x-x-4-4-3-x        (shell - 3rd & 7th, partial - 3 voices, the most this palette offers)
Gmaj9    D4  5    x-x-x-x-3-x        (melody repeated - single note)
Gmaj9/F# D4  5    x-x-4-4-3-x        (shell - 3rd & 7th, partial - 3 voices, the most this palette offers)
```

Expect an open, unlabelled sound: the 3rd and 7th are what make the chord major or minor,
and leaving out the root lets the player imply it.

**Duos** — `--grips duo` leaves two notes: the melody and the chord's **guide tone**, the 3rd
or the 4th on a suspended chord (or the 7th, when the melody is already the 3rd):

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips duo
```

```text
Gmaj9    D4  5    x-x-x-4-3-x        (duo - melody + b3, partial - 2 voices, the most this palette offers)
Gmaj9    D4  5    x-x-x-x-3-x        (melody repeated - single note)
Gmaj9/F# D4  5    x-x-x-4-3-x        (duo - melody + b3, partial - 2 voices, the most this palette offers - the written bass F# is not sounded - the lowest voice (B3) is 5 semitones from it)
```

Expect the sparsest thing this library will play — the harmony implied rather than stated,
for a solo voice or for leaving room over a band.

`common_grips.md` is a chart of the drop-2 shapes, **generated** from these tables by
`grip_chart.py` and checked by `make chart-audit`. Do not hand-edit it.

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

The `Cmaj7` is the interesting one: `x-2-2-5-x-x` is a three-note **6-4-3 shell** on the D and G
strings, because a four-note 6-5-4-3 with the melody on top does not sound good. There is
deliberately no four-note block for a G-string soprano — the G string earns its place by carrying
shells, not chords. Pass `top_strings=(5,)` to restrict voicings to the traditional high-E block.

## High melodies, and the neck window

Every voicing is confined to frets 0–18 and a span of at most 5 (4 for a duo and an
interval), on a real string set. `NECK_FRET_MIN`/`NECK_FRET_MAX` — frets 2 to 13 — are the
range the selector *aims* for, not a hard filter: a step with no voicing inside the window
is still played, just outside it, because losing a chord of the tune is worse than being a
fret out of position. The run header echoes the window whether or not it was met.

The cost function ranks a shape's **correctness first**: notes outside the chord, then
frets outside the window, then missing voices, then fret span, then neck position, then the
inner voices' movement, and finally the bass function. So a tight shape beats a shape nearer
the middle of the neck, and a complete chord beats a partial one at any position. Spans of 0
and 1 frets are treated as equal — one fret of stretch is not worth moving the hand for —
which is why the order puts span above position but not the last fret of a reach. That order
is the library's central invariant, and the measurement behind it is in
[docs/engine.md](docs/engine.md).

A melody whose only position sits above `HIGH_FRET_LIMIT` (13) is voiced an octave down. The B
string is five semitones *below* the high E, so the same written pitch sits five frets **higher**
on it (`D5` is fret 10 on the high E, fret 15 on the B): re-voicing onto the B string alone
pushes the shape further up the neck, so dropping the octave is the only way down. `A5` over
`Dm7` can only be voiced at fret 17, so it is arranged as `A4`:

```python
high = [("A5", "m7", "Dm7")]
for step in engine.arrange_progression(high):
    print(step.chord, step.melody, step.voicing.tab_string(),
          "from", step.original_melody)
```

```text
Dm7 A4 10-x-10-10-10-x from A5
```

The step's `melody` is the pitch that actually sounds and `original_melody` keeps the
written one; `format_progression` annotates the step with it:

```text
Dm7      A4  5    10-x-10-10-10-x    (harmony under 5 - transposed down an octave from A5 - 4 voices)
```

Two deliberate limits:

- **It only repositions a voicing that exists.** A melody unreachable at the written pitch
  (`B5` is fret 19, `C6` is fret 20 — both past the end of the board) is still skipped with a
  warning rather than silently respelled, so the real problem stays visible.
- **The decision is per step and the melody only.** It does not transpose a phrase as a unit,
  so a melody that leaps across the limit can arrive an octave apart from its neighbour: no
  step is ever left unplayable, at the cost of one melodic interval.

`get_all_drop2_voicings` is deliberately *not* filtered by fret — it stays pure candidate
generation, and `get_octave_down_candidates` is the separate, explicitly opt-in entry point
for the transposed form.

## Non-chord melody notes

Real melodies do not always land on a chord tone. Bar 2 of "All of Me" moves `C5 → D5 → C5`
over `Cmaj7`, where `D5` is the 9th. Pass `non_chord_tone=` to `arrange_progression` (or
call `is_chord_tone` / `resolve_non_chord_tone` directly) to choose how such notes are
harmonised:

```python
bar_2 = [("C5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7"), ("C5", "maj7", "Cmaj7")]

for strategy in ("extension", "diminished", "sustain"):
    steps = engine.arrange_progression(bar_2, non_chord_tone=strategy)
    print(f"{strategy:<11}", steps[1].voicing.tab_string(), steps[1].harmonized_as)
```

```text
extension   x-x-9-9-8-10  Cmaj9
diminished  x-x-9-10-9-10 Bdim7
sustain     x-x-9-9-8-10  Cmaj7
```

- `extension` (default) — absorb the note as an extension: `D5` over `Cmaj7` becomes a
  `Cmaj9`, so `D` is a chord tone again and the shape sounds only `Cmaj7`-family pitches. The
  mapping lives in `VoiceLeadingEngine.NON_CHORD_TONE_EXTENSIONS`: 9ths and 6/9ths, plus the
  #11 (`Cmaj7#11`), the 11th (`G7sus4`), the #11/b13 over dominants, the 13th, the
  half-diminished 9th (`Am9b5`) and the 9th over a plain triad (`Ebmaj` under `F4` becomes
  `Ebadd9`).
- `diminished` — the Barry Harris 6/dim7 substitution: the passing `D5` is voiced inside
  `Bdim7` (the dim7 a semitone below the note the line resolves to), giving a smooth
  chromatic resolution.
- `sustain` — hold the previous chord's three inner voices and move only the melody, the way
  a shape is held under a passing tone, with `harmonized_as` reporting the chord still
  sounding under it.

Every `ArrangementStep` records what happened: `non_chord_tone`, `strategy` and
`harmonized_as` (e.g. `"Cmaj9"`). Melodies that are already chord tones are arranged exactly
as before, whichever strategy is selected.

**`--fallback diminished` is the opt-in retry.** When *no* strategy leaves a playable shape,
the written chord is genuinely replaced by the dim7 substitution, and the run says how many
steps it did that to. The same two bars without the flag, and with it:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 4-6
```

```text
Eb6      C5  6    x-x-8-8-8-8        (harmony under 6 - 4 voices)
Am7      D4  11   x-3-x-7-x-x        (non-chord tone - the extension strategy found no voicing; the written chord stands - 2 voices: the 4-voice voicing x-3-3-2-3-x sounds a note outside the chord)
Am7      D4  11   x-x-x-7-x-x        (melody repeated - single note - non-chord tone - the extension strategy found no voicing; the written chord stands)
Am7      D4  11   x-x-x-7-x-x        (melody repeated - single note - non-chord tone - the extension strategy found no voicing; the written chord stands)
```

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 4-6 --fallback diminished
```

```text
  note: diminished fallback replaced the written chord on 3 step(s)

Eb6      C5  6    x-x-8-8-8-8        (harmony under 6 - 4 voices)
Bdim7    D4  b3   4-x-3-4-3-x        (harmony under b3 - 4 voices)
Bdim7    D4  b3   x-x-x-x-3-x        (melody repeated - single note)
Bdim7    D4  b3   x-x-x-x-3-x        (melody repeated - single note)
```

Expect the tune to change: the written `Am7` is gone, and where the default route gave up
with two voices the fallback states a full `Bdim7`. That is a colour to opt into rather than
a default, which is why the run counts the steps it touched.

On a **comping** selection (`voices=` with no soprano, where the guitar states the chord
while somebody else sings) the same flag moves the chord the guitar *states*, never anything
it sings. A non-chord note at an **onset** reharmonises the guitar's chord, so `D5` over
`Cmaj7` under `voices="alto,tenor"` gives `Cmaj9` (`extension`) or `Bdim7` (`diminished`) in
the guide-tone voices, with `harmonized_as` reporting it and a diagnostic naming the note that
forced it. A held note and a silent grid position state the written chord unchanged, and
`sustain` leaves the comping part's harmony exactly as the chord symbol writes it.

## Supported chord qualities

Seventh chords: `maj7`, `6`, `m7`, `m7b5`, `dim7`, `m6`, `mMaj7`, `7`, `7b9`, `7alt`.
Extensions: `maj9`, `m9`, `9`, `6/9`, `13`. Triads: `maj`, `m`, `aug`. Suspended: `sus4`,
`sus2`, `7sus4`. Added-note and altered colours: `add9`, `madd9`, `7b5`, `7#5`, `7#11`,
`7b13`, `maj7#11`, `m9b5`.

Aliases resolve case-sensitively, so `M7` is a major seventh while `m7` is a minor seventh and
`M` is a major triad. They include `min7`, `min7b5`, `ø7`, `ø`, `half-dim`, `°7`, `°`, `dim`,
`min6`, `minMaj7`, `mmaj7`, `min9`, `dom7`, `dom9`, `dom13`, `M7`, `M9`, `69`, `min`, `-`, `+`,
`sus` and `7sus`. Two deliberate conventions: `dim` still means `dim7` (the diminished triad is
not voiced), and a bare `C` is not assumed to be major — spell it `Cmaj` or `CM`.

A drop-2 shape has four voices, so the triad templates double the root an octave below the
stack:

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

Unsupported qualities return no voicings; `arrange_progression` prints a warning and skips
that step rather than raising.

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

`make` prefers the repository's `.venv/bin/python`; override it with `make test
PYTHON=python3`. The equivalent long form is `.venv/bin/python -m unittest discover -s tests
-t . -v` run from the repository root (`-t .` is what lets `tests.support` import as a
package module).

**CI runs `make check` on Python 3.11 through 3.14**, with both optional extras installed so
the guarded tests are not silently skipped. That is the whole gate in one job: there is
nothing a clean clone cannot run, so a green check means the entire suite ran.

The engine lives in the `arranger` package, fifteen modules in a strict dependency order
that `tests/test_package_dag.py` asserts from the AST. See `AGENTS.md` for the module map
and the conventions, and [docs/](docs/) for the reasoning behind the engine and the
renderers.

## Known limitations

- Voicings use two to four strings, never all six. The melody may be on the high E, B or G
  string; the A string and low E are inner voices only, so no grip puts the soprano on either.
  No grip is a barré chord — fret `0` appears when a voice lands on an open string — and a full
  six-string voicing is not modelled. `fingers.py` does assign a finger per string and marks a
  barre where two strings share a fret, but no renderer prints a fingering: the tab is what you
  read. One grip — the 6-4-3 shell — deliberately skips the A string.
- Melodies are confined to `G3`–`Bb5`.
- A fixed maximum fret span of 5 (4 for a duo and an interval) and a fret range of 0–18 are
  assumed, and no step may need a fifth fret from a hand already holding its shape. `closed`
  (close position) is offered and sits second in the preference order, but is usually
  unreachable: a close-position chord under a melody is a seventh or more of pitch on four
  strings only four or five semitones apart in tuning, so most melodies cannot fret it inside
  that budget and it wins only where it does.
- Non-chord melody notes are handled only for the mappings in `NON_CHORD_TONE_EXTENSIONS`
  (9ths, 6/9s, 11ths, #11s, b13s, 13ths, the half-diminished 9th and the 9th over a plain
  triad) plus dim7; anything else keeps the quality-only fallback — and a melody-only palette
  (`shell`, `duo`, `interval`) has no fallback to keep, so the note sounds alone under its
  chord and the step says `(melody alone - no voicing for this chord)`.
- A chord tone drop-2 has no inversion for — a 9th in the melody of a 13 chord, for instance —
  falls through to the quality-only fallback, which can sound a note the chord does not
  contain. The selector rejects such a shape whenever a correct one exists, so an *arrangement*
  only hears it when nothing else is playable, but `get_drop2_voicings` still offers it. The
  shells, duos and 6-4-3 grip are unaffected: they build themselves from the chord's tones.
- The `sustain` strategy is structural — the API takes only `(note, quality, name)` triples, so
  rhythm and duration cannot be used to spot a brief passing tone.
- The neck window is a preference, not a filter, so `--fret-min`/`--fret-max` may not be
  honoured where nothing playable exists inside it. The header echoes the window whether or not
  it was met.
- A slash bass is honoured as a preference rather than a hard constraint: the selector narrows
  the candidates by it and then applies the engine's own rule within that set, so a voicing
  that cannot honour the bass is still playable.
- A beat the melody skips *inside* a bar it occupies has no chord of its own, because the
  chord in force is stored per melody note. The bar-level half of that is built — a bar the
  melody never enters is arranged under every route — and the rest is
  [open issue 1](docs/open-issues.md).
- No release has been published to PyPI.

## License

MIT. See [LICENSE](LICENSE) for the full text.

The optional `gp` extra pulls in [PyGuitarPro](https://pypi.org/project/PyGuitarPro/), which
is LGPL-3.0. That is deliberately kept out of the runtime dependencies and behind a lazy
import, so this project is not a combined work of PyGuitarPro and stays permissively licensed.
`tabgp` also writes no PyGuitarPro code into this repository.

