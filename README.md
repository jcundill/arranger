# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Given a progression of `(melody note, chord quality, chord name)` triples, `arranger`
builds voicings in several grip families, pins the melody to the soprano string, and
picks among them with one position-aware cost function.

- **Six grip families**, drop-2 first: `drop2`, `drop3`, `drop24`, `drop2_6432`,
  `shell` and `duo` — four-note voicings down to two-note guide-tone pairs. Every
  one sounds the chord's **3rd and 7th**, the two notes that decide whether the ear
  hears a major or a minor chord; a `duo` sounds one of them, under any chord tone,
  since two notes is the floor this library will play ([grips](#grips)).
- **Melody pinned to the soprano**, on the high E, B or G string, so a low melody can
  still be harmonised in position.
- **Playable or absent.** Every voicing sits in frets 0–18 within a 5-fret span on a
  real string set. The neck window is a *preference, not a filter* — losing a chord of
  the tune is worse than being a fret out of position.
- **Non-chord melody notes** are reharmonised as an extension, via the Barry Harris
  6/dim7 substitution, or by holding the chord shape under a passing tone.
- **Three textures**, not one: every note in full, chords on the strong beats with
  thinner fills between, or a walking bass line under the melody ([texture](#texture)).
- **Heads from real sources** — a MusicXML score, read as the harmony *timeline* it
  is rather than as a chord attribute on each note.
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
  2/2, Eb major, 80 melody note(s), bars 1-32; neck window: frets 2-13; grips: drop2, shell, duo
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
| `--non-chord-tone` | `extension` | how to harmonise a melody note outside the chord |
| `--fallback` | off | `diminished` — see [the trade-off](#the-fallback-trade-off) |
| `--texture` | `uniform` | `uniform`, `targets`, `walking_bass` — see [texture](#texture) |
| `--bass` | follows `--texture` | `none`, `anchors`, `walk` — see [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| `--voices` | `auto` (all four) | any subset of `soprano,alto,tenor,bass` — see [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| `--harmony` | `auto` (= `guide`) | `full`, `guide`, `shell_root`, `root` — which degrees the part states when it is *not* singing; see [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| `--grid` | `every_note` | `every_note`, `freddie`, `charleston`, `joe_pass`, `final_and` — where a chord *falls* in the bar; see [where a chord falls](#where-a-chord-falls-the-grid-axis) |
| `--fret-min` / `--fret-max` | `2` / `13` | the neck window to aim for |
| `--grips` | all six | which grip families to consider, **most preferred first** |
| `--tab` | `line` | `staff` lays the head on one six-line staff, spaced on its real rhythm |
| `--melody` / `--mutes` | off | with `--tab staff`: add a melody row / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write the head to a file — see [rendering](#rendering) |

**Every written note sounds.** There is no reduction: `arranger head` plays the tune as
written, one step per note, each on the beat it was written on. That was not always true.
`--skeleton` used to name a grid — one step per chord change, beat, eighth, sixteenth or
note — and every note was quantised onto it, so two notes closer together than the grid
shared a step and one was **silently dropped**. On a 32-bar head with triplets it lost
24 of 110 notes, and only 11 were in the triplet bars: 13 were in the straight ones. A
note of the tune going missing without a word is worse than a busy tab, so the flag and
its companion `--pick` are gone from `head`.

**`--grips` is ordered.** It is a preference list, not a set: putting `shell` first
will displace a four-note drop-2 whenever the two cost the same. Leave it alone unless
you want a thinner arrangement.

**The fret window is an aim, not a filter.** A step with no voicing inside your window
is still played, outside it, and the run header echoes your window whether or not it was
met — losing a chord of the tune is worse than being a fret out of position.

### Five things a score does that a database does not

**The harmony is a timeline.** A `<harmony>` precedes the note it governs, several can
share a bar, and a bar can carry none at all — so a chord is *held* from the note it is
declared before until the next one replaces it. Reading the chord off the note that
follows it would drop the harmony from every bar that does not change.

**The metre is the notated one.** `beat` is the beat *within* the bar in notated beats,
so a 2/2 head is two beats to the bar rather than four — which is how most standards are
written, and how three of the four scores in this repository are.

**The key signature is read, and written back.** `Head` carries the score's `<fifths>`
and `<mode>`, and the MusicXML and GP5 writers state them — so a tune in three flats
exports as a tune in three flats instead of an unlabelled C-major score carrying a
flat on every note of its own scale. A score that omits `<key>` is C major, which is
what a file with no signature already means, so nothing changes for one.

**The melody is the top line.** A `<chord>` group reduces to its *highest* note, because
MusicXML does not order a group by pitch and in a chord-melody part the first member is
the lowest note. Everything else is counted and reported in `skipped`, not dropped.

**A chord this library cannot voice is counted, not guessed.** `Neapolitan` is a real
MusicXML kind and a real chord; it is not one this library holds under a melody, so it
is listed in `Head.unmapped` and the run says so.

### It is the same arrangement code

A head read from a score is voiced by `arranger.slots.arrange_slots` — the engine's own
slot layer, and the only step loop in the project. The non-chord-tone strategies, the
opt-in diminished retry, the repeated-melody hold and the walking bass are therefore the
engine's rather than the importer's; only the *selection* is the importer's business.

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

print(format_tab_staff(steps))
```

```text
e*|-10-7--8-|
B |-10-6--8-|
G |-10-7--9-|
D |-10-5--9-|
A |---------|
E |---------|
```

**The default output is the tab and nothing else** — six string rows, the fret numbers
sitting in a drawn line of dashes, and a `|` closing every bar. That is what a tab file
*is*, and what TuxGuitar's, Guitar Pro's and every other ASCII export produce. Each
string is one continuous line with the frets *in* it, no fret ever sits hard against a
barline, and **`e*` marks the string carrying the melody**.

**Width is duration.** A bar is divided into a sixteenth-note grid, and a note occupies
as much of it as it sounds for — a half note is drawn twice as wide as a quarter, and the
dashes after a fret are the note still ringing:

```text
e*|-------3----|----------|----3----|
B*|----6--3--6-|-8--------|-6--3--6-|
G*|----7--3--7-|-8------8-|----7--3--7-|
```

So the tab says how long everything sounds without a rhythm row. A pickup keeps the rest
in front of it (`|----6--|` starts a beat and a half late, because the head enters there),
and the last bar is filled out to its own length, because the rest after the final note is
still time. `show_timing` adds the explicit `q`/`w` row anyway, for a reader who would
rather be told than infer.

Four flags add the annotation a score carries and a tab does not, all off by default:

- **`show_chords`** draws the chord names on a line above, each starting in the column
  where its shape is struck.
- **`show_melody`** draws a line of melody note names.
- **`show_timing`** adds the **metre** (`4/4`) over the first bar and the **note value**
  of every column (`w` whole, `r` rest, `~` held). Without that row a whole note and a
  quarter are drawn identically, since on this grid both were one column of frets. Pass
  `beat_type` to state the metre properly — 2/2 is 2/2, not 2/4.

```python
print(format_tab_staff(steps, show_chords=True, show_melody=True, show_timing=True))
```

```
  | 4/4        |
  | q   r   q  |
  | Dm7   G7   |
  | D5    B4   |
e*|-10-7--8-|
B |-10-6--8-|
G |-10-7--9-|
D |-10-5--9-|
A |---------|
E |---------|
```

The rows share one column grid with the strings beneath them, and each **system** of
music is ruled to its own width — a long chord name widens the bar it is in and no
other, so one `Cmaj7` cannot stretch a whole arrangement. `measures_per_line` sets how
many bars go on one line before the staff wraps; the last line may be shorter.

Three more options do most of the work:

- **`collapse=True` (the default)** strikes a shape once and lets it ring while the melody
  moves over the same pitches, instead of restriking it on every step. The skeleton voices
  one step per eighth; a player holds the shape rather than hitting it eight times a bar.
  A rest breaks the ring, so the next shape is struck again.
- **`rhythm=True` (the default)** spaces the chords on their real beats, so a held chord
  is drawn with room around it rather than jammed against the next one. This needs each
  step to carry `bar` and `beat`, which `arrange_xml_head` supplies from the score; a
  hand-written progression has no timing and falls back to one chord per beat.
- **`show_mutes=False` (the default)** leaves unsounded strings as plain dashes, because
  in chord-melody a voice that is still ringing is not restruck. Pass `True` to spell them
  out as `x`.

`docs/renderers.md` covers the full set and the ASCII/HTML forms.

From the command line, the same renderer is `--tab staff`:

```bash
python -m arranger head but_not_for_me.mxl --tab staff --melody --bars-per-line 4
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
python -m arranger head but_not_for_me.mxl --musicxml head.musicxml
```

A chord name music21 cannot classify — some published notation produces several — is
written as text with the root still parsed out, rather than dropped.

### Guitar Pro 5, for a tabber

`write_gp5` writes the same arrangement as a **Guitar Pro 5 file**, to open in Guitar
Pro alongside your own tab. It needs its own extra (`pip install '.[gp]'`):

```python
from arranger import write_gp5

write_gp5(steps, "head.gp5", title="Blue Train", subtitle="John Coltrane")
```

```bash
python -m arranger head but_not_for_me.mxl --gp5 head.gp5
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
| `duo` | 2 | the chord's guide tone — the 3rd, or the 4th on a sus chord — under any chord tone |
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

**5. Duos** — `--grips duo` leaves two notes: the melody and the chord's **guide tone**,
the 3rd or the 4th on a suspended chord (or the 7th, when the melody is already the 3rd):

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips duo
```

```text
Gmaj9    D4   (duo - melody + b3, partial) x-x-x-4-3-x
Gmaj9    D4   (melody repeated - single note) ----3-
Gmaj9/F# D4   (duo - melody + b3, partial) x-x-x-4-3-x
```

*Expect the sparsest thing this library will play — the harmony implied rather than
stated, for a solo voice or for leaving room over a band.*

**5b. The tune on its own** — `--voices soprano` plays the melody and nothing else, so
a lead sheet in gives you the line out. The chord names are still printed above it as
context; nothing under them is being voiced. (This used to be `--texture melody`;
"which voices the guitar plays" is the question `voices=` answers, and it took the
fact over from the texture axis.)

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --voices soprano
```

```text
Gmaj9    D4   x-x-x-x-3-x
Gmaj9    D4   x-x-x-x-3-x
Gmaj9/F# D4   x-x-x-x-3-x
```

`--voices soprano,bass` is the same line with a walking thumb under it, and still
nothing harmonising it — a bass voice and the tune, with no chords anywhere:

```text
Gmaj9    D4   (bass: G2, anchor) 3-x-x-x-3-x
Gmaj9    D4   x-x-x-x-3-x
Gmaj9    D4   (bass: F#2, connect) 2-----
Gmaj9/F# D4   x-x-x-x-3-x
```

*Expect a single melodic line, played where the hand can play it. `--texture
walking_bass` is the other end of this: a shell stating the harmony on the strong
beats, this line between them.*

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

Every voicing is confined to frets 0–18 and a span of at most 5 (4 for a duo and an
interval), on a real
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
missing. Measured over six Weimar transcriptions this takes the mean sounding notes per
melody note from **3.86 to 3.39** and four-voice steps from **87% to 51%**, with no head
losing a step. (That measurement was taken before the database path was removed; the
finding stands and the corpus that produced it no longer ships.)

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

`docs/open-issues.md` records the three defects this texture has had — two fixed, and
**one open**: a walk-invented beat takes the wrong melody where a note is held across a
barline, which costs the tune that note in cut time. It carries the measurements and
the candidate fixes.

## Who plays which voice: `bass` and `voices`

`texture` and `bass` answer two separate questions — *where do notes fall* and *who plays
the bottom* — and `voices` adds a third: **who plays the tune**. All three are orthogonal,
so a band setting is a combination rather than a mode:

| axis | question it answers | values |
|---|---|---|
| `texture=` | where notes fall, how thick the left hand is | `uniform`, `targets`, `walking_bass` |
| `bass=` | the bass voice | `none`, `anchors`, `walk` |
| `voices=` | which voices the guitar plays | any subset of `soprano`, `alto`, `tenor`, `bass`; `soprano` alone is the tune and nothing else |
| `harmony=` | **which degrees** the part states, when it is not singing | `full`, `guide`, `shell_root`, `root` |

**`harmony=` is read only when the guitar has no tune of its own**, so it composes with
`--voices` rather than competing with it: `voices` says *how many* notes and whether the
soprano is ours, `harmony` says *which degrees those notes are*.

| `harmony=` | the part sounds | needs |
|---|---|---|
| `guide` (the default) | the 3rd and the 7th — the notes that say major or minor | two notes |
| `shell_root` | both guide tones **and** a root or 5th underneath them | three notes |
| `root` | a root, or a 5th where the root is out of reach — a bass note on its own | `--voices bass` alone |
| `full` | the whole chord | the ordinary chord-melody route |

`--harmony shell_root --voices alto,tenor,bass` is a horn on the tune with the guitar
stating quality *and* root underneath; it needs the three notes, and asking for it with
two is refused with a warning rather than quietly thinned. On an arrangement where the
guitar *is* singing, `--harmony` does nothing at all — for that, a chord-melody on shells
is `--grips shell`, which is a grip choice rather than a degree family and keeps the
melody pinned to the top string.

`--bass none` and `--voices alto,tenor` together are the ensemble this library was asked
for: a bassist on the root, a sax on the melody, and the guitar comping the two middle
voices. Each is chosen separately because each is a different decision — "I'm next to a
bass player so I want none of the 1s and 5s and none of the walking motion" is `bass=none`,
"and the melody isn't mine either" is dropping `soprano` from `voices`, and leaving either
alone keeps that voice the guitarist's job.

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

**Naming one voice says *which* one, and `bass` is not the same request as `alto`.**
`alto` and `tenor` alone are a guide tone under somebody else's melody — the 3rd, on a
high string, which is where a player puts one. `bass` alone is the bottom of the band:
it sounds the **root, or the 5th where the root is unreachable**, on the low E, A or D.
Both are one note, so the arity cannot tell them apart, and for a while it did not:
`--voices bass`, `alto` and `tenor` produced identical arrangements, with the bass voice
sounding a 3rd in the middle of the neck. `--voices bass` is a bass *line* and states
nothing about the chord's quality; name an inner voice as well if you want the quality
said.

```bash
python -m arranger head tests/data/but_not_for_me.mxl --voices bass
```

```text
Bb7      F4   (shell - 3rd & 7th, partial) x-x-3-x-x-x
Bb7      G4   (shell - 3rd & 7th, partial) x-x-3-x-x-x
Ebmaj    G4   (shell - 3rd & 7th, partial) 6-x-x-x-x-x
```

One note per step, on the low E, A or D, sounding the chord's root — `Bb7` gives `Bb`, not
the `D` a guide-tone shape would. The third column is the *written* melody, which this
guitar is not playing (`melody_voiced` is `False`); it is still on the step so the band can
line up against it. The `(shell - 3rd & 7th, partial)` annotation is stale wording for this
selection — the shape is a single bass note, not a shell — and is left as-is rather than
special-cased, because the grip label is shared with the shapes that genuinely are shells.

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
Gmaj9    D4   (shell - 3rd & 7th, partial) x-x-x-x-7-7
Gmaj9    D4   (shell - 3rd & 7th, partial) x-x-x-x-7-7
Gmaj9/F# D4   (shell - 3rd & 7th, partial) x-x-x-x-7-7
```

*Expect **two** notes per step — one per voice you named. `--voices alto` gives one and
`--voices alto,tenor,bass` gives three; the arity follows the selection rather than a
constant, because a part sounding more notes than the caller named is a voice somebody
else was supposed to have. `step.melody` still carries the note the horn is playing, and
`step.melody_voiced` is `False` because the guitar is not the one playing it — that is what
makes the two flags different things: the first is the written tune, the second is who sounds
it.*

**The shape is chosen from the chord alone.** `get_comping_voicings` takes no melody
argument, and asking it for `D5` and `G3` under the same chord returns the *identical*
candidate set — a generator that read the melody could not do that. What it does mean is
that a chord tone in the shell may land on the same pitch class as the melody: measured over
three Weimar transcriptions, **409 of 2,069 steps contain the melody's exact pitch**. That is
unremarkable — it is the guide tone the ear needs anyway — and it is not the guitar singing.

Every quality the engine can voice has a comping shape in some playable position — checked
over `CHORD_TONES_FROM_ROOT` rather than a hand-picked list, so a quality added later cannot
join the engine without being measured. A quality with no readable root still gets nothing,
on the same rule as every other guide-tone generator: a shell is a claim about *this* chord's
3rd and 7th, and guessing them without a root is how a wrong note gets in.

**`texture` still decides where the chords go.** The axes are independent, not one mode
between them: `--texture targets --voices none` gives a shell on beats 1 and 3 and a thinner
shell between, with the horn's line untouched throughout.

**A repeated melody holds the whole shape.** Normally a repeat is a soprano-only
re-strike with the inner voices held — but there is no soprano to re-strike when the guitar
isn't singing, so the shape is held instead. Measured over 2,243 Weimar steps, 152 carry
`repeated`; without this the guitar part would have played a moving melody line on exactly
the beats where the arrangement handed the tune away.

**The tune, on its own or with a thumb.** `voices=soprano` is the melodic voice and
nothing else — every slot is the melody alone, and `soprano,bass` is the same line
with a walking thumb under it. A selection without the soprano comps under the horn
on every texture. An `NC` bar under `voices=none`
is likewise reported rather than quietly dropped: there is no chord, so there are no guide
tones, and the guitar is genuinely silent while the horn is not.

**Nothing changes until you ask.** `voices` defaults to `auto`, which resolves to `guitar`:
the melody pinned to the soprano string, exactly as before. All 883 existing tests pass
unchanged, and no published arrangement moves.

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

**The positions are bar-relative, which is what lets one name work in any metre.**
"the upbeat of the final beat" is 4.5 in 4/4, 2.5 in 2/2 and 3.5 in 3/4 — the same musical
idea at three different beat numbers. Spelling the pattern as a literal beat (`beat 4`)
would make it look, on a 2/2 head, like a pattern naming a beat that does not exist.

**What happens to a note with no chord on it depends on who is singing**, which is the
one place this axis needs two answers rather than one:

- **guitar singing** — the note of the tune still sounds, on its own. No note is ever
  dropped: a chord-melody under `--grid joe_pass` plays the melody throughout and places
  chords only on the ands.
- **guitar comping** (`--voices alto,tenor`) — the guitar is **silent** on that beat,
  because the melody belongs to the horn and there is nothing for the guitar to add. The
  step is still emitted, so the part keeps its position in the bar and lines up against
  the tune; it draws as an empty column.

**The bass line is not affected.** A grid removes *chords*, never the thumb: measured on
`but_not_for_me` with `--texture targets --bass walk`, the walked notes are identical
under `--grid every_note` and `--grid freddie`. The two axes are orthogonal, which is the point
of having both.

**Nothing changes until you ask.** `--grid` defaults to `every_note` — one chord per
written melody note, which is what the library already did.
Every published arrangement is byte-identical.

A **free-form grid** — naming positions directly, rather than choosing a row — is not
built yet. See [docs/comping-styles.md §4.2](docs/comping-styles.md) for the design and
what remains.

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
- **The decision is per step and the melody only.** It does not transpose a phrase as a
  unit, so a melody that leaps across the limit can arrive an octave apart from its
  neighbour. That is the intended
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
so the guarded tests are not silently skipped. That is the whole gate in one job: there
is nothing a clean clone cannot run, so a green check means the entire suite ran. (There
used to be a second, manual-dispatch job for the 42 MB Weimar Jazz Database, and a green
check here did *not* mean the corpus path had been exercised. The database is gone, and
so is that caveat.)

The engine lives in the `arranger` package, thirteen modules in a strict dependency order
that `tests/test_package_dag.py` asserts from the AST. See `AGENTS.md` for the module map
and the conventions, and [docs/](docs/) for the reasoning behind the engine and the
renderers.

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
- A slash bass is honoured as a preference rather than a hard constraint: the selector
  narrows the candidates by it and then applies the engine's own rule within that set, so
  a voicing that cannot honour the bass is still playable.
- No release has been published to PyPI.

## License

MIT. See [LICENSE](LICENSE) for the full text.

The optional `gp` extra pulls in [PyGuitarPro](https://pypi.org/project/PyGuitarPro/),
which is LGPL-3.0. That is deliberately kept out of the runtime dependencies and
behind a lazy import, so this project is not a combined work of PyGuitarPro and
stays permissively licensed. `tabgp` also writes no PyGuitarPro code into this
repository.
