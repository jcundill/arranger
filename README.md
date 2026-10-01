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
- **Dependency-light**: Python 3.10+ and [musthe](https://pypi.org/project/musthe/) only. The
  optional [Weimar Jazz Database](#rendering-a-head-from-the-weimar-jazz-database)
  integration adds no dependencies at all — it is stdlib `sqlite3`.
- **Heads from real transcriptions**: render the head of any of the 456 Weimar
  Jazz Database solos as chord-melody.

> The **distribution** is named `jazz-arranger` (the PyPI name `arranger` is already
> taken by an unrelated project). The **import** name is simply `arranger`.

## Installation

```bash
pip install -e .        # or: make install
```

MusicXML export is the one thing the library cannot do with the standard library, so
it lives in an **optional extra**. A plain install pulls in `musthe` alone:

```bash
pip install -e '.[xml]' # adds music21, for format_musicxml / write_musicxml
pip install -e '.[gp]'  # adds PyGuitarPro, for format_gp5 / write_gp5
```

Nothing else in the package needs it: the renderer imports `music21` when it is
called, not when it is imported.

Or, without installing, just run everything from the repository root — the module
imports directly:

```bash
python -m arranger      # built-in demonstration arrangements
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

| flag | default | |
|---|---|---|
| `--part` | the melody part | a `<score-part>` id, when a score has several |
| `--bars` | the whole head | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--skeleton` | `eighths` | `chords`, `beats`, `eighths`, `sixteenths`, `notes` |
| `--pick` | `first` | `first` or `longest`, for slots holding several notes |
| `--non-chord-tone` | `extension` | `extension`, `diminished`, `sustain`, `legacy` |
| `--fallback` | off | `diminished` — see the trade-off below |
| `--tab` | `line` | `staff` lays the head on one six-line staff, spaced on its real rhythm |
| `--melody` / `--mutes` | off | as for `corpus` |
| `--html` / `--musicxml` / `--gp5` | off | the same renderers `corpus` offers |

### Four things a score does that a database does not

**The harmony is a timeline.** A `<harmony>` precedes the note it governs, several
can share a bar, and a bar can carry none at all — so a chord is *held* from the
note it is declared before until the next one replaces it. Reading the chord off
the note that follows it would drop the harmony from every bar that does not
change, which on a slow head is most of them.

**The metre is the notated one.** `beat` is the beat *within* the bar in notated
beats, so a 2/2 head is two beats to the bar rather than four — which is how most
standards are written, and how three of the four scores in this repository are.

**The melody is the top line.** A `<chord>` group reduces to its *highest* note,
because MusicXML does not order a group by pitch and in a chord-melody part the
first member is the lowest note of the shape. Everything else is counted and
reported in `skipped`, not dropped in silence.

**A chord this library cannot voice is counted, not guessed.** `Neapolitan` is a
real MusicXML kind and a real chord; it is not one this library holds under a
melody, so it is listed in `Head.unmapped` and the run says so. The same rule
`wjazzd` follows for an untranslatable Weimar suffix.

### It is the same arrangement code

A head read from a score is voiced by `wjazzd.arrange_slots` — the corpus path's
own step loop. The non-chord-tone strategies, the opt-in diminished retry, the
repeated-melody hold and the slash-bass preference are therefore identical
whichever source a head was read from; only the *selection* differs. That is
deliberate: the corpus path once had a second, weaker implementation of the same
rule, and it shipped unnoticed until a transcribing analyst measured it.

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
  note: lifted an octave: 51 -> 60 of 62 steps voiced
  note: 13 unresolved tension(s) could be rescued with --fallback diminished, which replaces the written chord

Eb7      F5   x-x-12-12-12-13
Ab7      Eb5  x-x-10-11-9-11
Ab7      F5   x-x-12-12-12-13
Ab7      Db5  x-x-9-10-9-9
Ab7      Eb5  x-x-10-11-9-11
Ab7      F5   x-x-12-12-12-13
Eb7      E5   x-x-12-13-12-12
```

This needs `wjazzd.db` (42 MB) from [jazzomat.hfm-weimar.de](http://jazzomat.hfm-weimar.de/),
placed beside the package or pointed at by `WJAZZD_DB`. It is not committed, and
nothing in the library requires it.

```bash
python -m arranger corpus --list                        # the 456 transcriptions
python -m arranger corpus --melid 342 --tab staff       # "All the Things You Are", Metheny
python -m arranger corpus --melid 266 --bars -4-1       # the pickups, below bar 0
python -m arranger corpus --melid 218 --section chorus:1  # a solo chorus instead
```

| flag | default | |
|---|---|---|
| `--section` | the head | `form:A1`, `chorus:1`, `phrase:2`, `idea:lick`; `*` globs |
| `--bars` | the whole span | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--skeleton` | `eighths` | `chords`, `beats`, `eighths`, `sixteenths`, `notes` |
| `--pick` | `first` | `first` or `longest`, for slots holding several notes |
| `--lift` | `auto` | `auto`, `none`, `always`, `per-note` |
| `--non-chord-tone` | `extension` | `extension`, `diminished`, `sustain`, `legacy` |
| `--fallback` | off | `diminished` — see the trade-off below |
| `--tab` | `line` | `staff` lays the head on one six-line staff, spaced on its real rhythm |
| `--melody` | off | with `--tab staff`, add a line of melody note names |
| `--mutes` | off | with `--tab staff`, spell out the unsounded strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`, bars per staff line |

### How the head is found

Not from the form label. On all four "All the Things You Are" transcriptions,
`FORM A1` starts at the *second* statement and the real 8-bar head sits in the
preceding intro block, so a label-based selector misses it entirely. The head is
found on the **chord progression**: seed from the first A-block extended back over
any intro, anchor on its progression, then trim to the first span that recurs —
matched modulo transposition, since the same progression returns in a new key.

The command reports the bars and the anchor chords it chose, so you can see the
selection and override it with `--bars`.

This is a heuristic and does not land on the head every time: it is right on
melids 266 and 342, returns a short fragment on 328, and falls back to the whole
A-block on 451. Across the corpus 434 of 456 transcriptions yield a head, and the
median head is 8 bars.

### Three things to know before you rely on it

**Heads are not harmonically simpler than solos.** This is the most common
surprise. The chord-tone rate for a head is 58.7% at best, statistically
indistinguishable from the solo material, and only 48.6–64.5% on real standard
melodies — *worse* than the bebop lines it was compared against. A standard tune is
built from passing tones between widely spaced chord tones, so it is more
non-chordal, not less. Roughly half the steps need the non-chord-tone strategy,
and some need more than the library's extension table can reach.

**`--lift auto` may transpose the head an octave.** It builds the head twice, as
transcribed and an octave up, and keeps whichever voices more steps; ties go to
the original. It is threshold-free, so a head whose median sits one or two
semitones above an arbitrary cut-off cannot defeat it. Transposing the *whole*
head at once cannot distort any interval, but it does move the music — Blue
Train's head is lifted, because it dips to E♭3. The decision is printed on every
run; `--lift none` or `always` overrides it.

**`--fallback diminished` replaces the written chord.** It rescues the tensions
nothing else can resolve — 13 steps on Blue Train's head — by substituting a
Barry Harris dim7 a semitone below the resolution target. It works
mechanically, but harmonically it rewrites the tune, and on a 12-bar blues most
of the substitutions land on the tonic, so the tonic bar stops being a plain
dominant. A head is supposed to be the written tune, so it is **off by default**
and the count of steps it *would* rescue is always reported. Pass it only when you
want that colour.

A bar marked `NC` in the database is melody with no harmony; it is played alone on
a single fret rather than harmonised, which is why such a step does not obey the
four-string rule.

## Rendering tab

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
G7       B4   x-x-5-7-6-7
Cmaj7    C5   x-x-9-9-8-8
```

This is the compact one-line form, and it is the only shape
`format_progression` has. (It also took `vertical=True` for a six-line block per
chord, and the `--vertical` flag existed to reach it; both are gone, because
`format_tab_staff` below renders a whole progression as real six-line tab — with
the chords on their real beats, which the block never could.)

Steps whose melody is a non-chord tone are annotated with the substitution that
was applied, so a reharmonised passing tone is never silent about itself.

### A whole progression on one staff

`format_progression` gives one line *per chord*. For something
you could read off a page, `format_tab_staff` lays the entire progression along a
single six-line staff, in reading order:

```python
from arranger import format_tab_staff

print(format_tab_staff(steps, show_melody=True))
```

```text
  |4/4                    |                       |     |
  |w     r     r     r    |w     r     r     r    |w    |
  |Dm7                    |G7                     |Cmaj7|
  |D5                     |B4                     |C5   |
e*|10   -     -     -     |     -     -     -     |8    |
B*|10   -     -     -     |12   -     -     -     |8    |
G |10   -     -     -     |10   -     -     -     |9    |
D |10   -     -     -     |12   -     -     -     |9    |
A |     -     -     -     |10   -     -     -     |     |
E |     -     -     -     |     -     -     -     |     |
```

The chord names sit on a line above, each starting in the column where its shape is
struck, and `e*` marks the string carrying the melody.

Above the chords are two more rows. The **metre** (`4/4`) is written over the first
bar and nowhere else — a time signature holds until it changes. Under it, the **note
value** of every column: `w` for a whole note, `r` for a rest, `~` for a shape still
held from an earlier column. Without that row a whole note and a quarter were drawn
identically, since on this grid both were one column of frets; it is what makes the
staff a score rather than a chord list. Pass `show_timing=False` for the staff
without them, and `beat_type` to state the metre properly — 2/2 is 2/2, not 2/4, and
its beat is a half note rather than a quarter.

Two options do most of the work:

- **`collapse=True` (the default)** strikes a shape once and lets it ring while the
  melody moves over the same pitches, instead of restriking it on every step. The
  skeleton voices one step per eighth; a player holds the shape rather than hitting
  it eight times a bar. A rest breaks the ring, so the next shape is struck again.
  Pass `collapse=False` to see every voicing.
- **`rhythm=True` (the default)** spaces the chords on their real beats, drawing a
  barline every `measures_per_line` bars. This needs each step to carry `bar` and
  `beat`, which the corpus loader supplies; a hand-written progression has no timing
  and falls back to one chord per beat.

Muted strings are left blank by default, because in chord-melody a voice that is
still ringing is not restruck. Pass `show_mutes=True` to spell them out as `x`; a
melody-only (no chord) step always shows its `x`s, since there the other strings
really are silent.

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

Melodies below the high E string's open pitch (`E4`) cannot be voiced on that block.
By default the melody may also be pinned to the B string (voicing on A-D-G-B) and to
the **G string** (voicing on the bottom four strings), which drops the reachable floor
to `G3`:

```python
low = [("D4", "m7", "Dm7"), ("D4", "7", "G7"), ("C4", "maj7", "Cmaj7")]
for step in engine.arrange_progression(low):
    print(step.chord, step.voicing.tab_string(), "melody string",
          6 - step.voicing.soprano_string())
```

```text
Dm7 8-8-7-7-x-x melody string 3
G7 ---7--       melody string 3
Cmaj7 7-7-5-5-x-x melody string 3
```

All three sit in one position on the bottom four strings. The same phrase under the
library's original settings — `top_strings=(5, 4), grips=("drop2",)` — lands an octave
higher:

```python
for step in engine.arrange_progression(low, top_strings=(5, 4), grips=("drop2",)):
    print(step.chord, step.voicing.tab_string())
```

```text
Dm7 x-3-3-2-3-x
G7 ----3-
Cmaj7 x-2-2-0-1-x
```

The same four pitches, a different position on the neck. Pass `top_strings=(5,)` to
`arrange_progression` (or `get_all_drop2_voicings`) to restrict voicings to the
traditional high-E block.

## Grips: more than drop-2, and where they are played

The engine offers three grip families, and the one it picks is decided by where the
hand already is rather than by preference:

| grip | voices | what it is |
|---|---|---|
| `drop2` | 4 | the hand-authored drop-2 tables, on strings 4-3-2-1 or 5-4-3-2 |
| `drop2_6432` | 4 | **6-4-3-2** — low E, D, G and B, so the bass can be a root |
| `shell` | 3 | the 3rd and 7th plus one more: 1-2-3, 2-3-4, 5-4-3, **6-4-3** or **5-3-2** |
| `duo` | 2 | the root or 5th in the melody plus the 3rd |
| `interval` | 2 | a 3rd, 6th or 10th below the melody — a *fill*, not a harmony |

`GRIP_PREFERENCE` lists the first three in tie-break order, so a four-note drop-2 is
never displaced by a shell when the two cost the same. `interval` is not in it: it is
offered only by the `targets` texture below, because a two-note fill is never the
right answer to "state this chord".

**A shell is searched for, never stacked.** A shell's notes are not in descending pitch
order down the strings, because the tuning is not monotonic in the useful direction: the
A string is tuned five semitones *above* the D string, and the D string five above the G.
A G7 shell under G3 is `2-3-0-x-x-x` — B2 on the A string, F3 on the D string, G3 on the
G — where the A string carries the *lower* note while being the higher string. Gm7 in
6-4-3 is `3-x-3-3-x-x`, with G3 on the D string below A2 on the low E. Any model that
lays the voices on strings from the top down by pitch gets both of these backwards and
finds nothing, so `_place_shell` holds the melody and searches every combination of frets
inside the span limit. Because the search window *is* the span limit, the search is
exhaustive within the playability invariant: if a playable shell exists in that position,
it is found.

**5-3-2 is the other shape that skips a string**, this time the D, putting ten semitones
of tuning between the A and the G. F7 with its seventh in the melody is `x-3-x-2-4-x`:
frets 3, 2 and 4, nowhere near monotonic in the pitch order, which is the same reason it
needs the search. It adds no new coverage — it is never the only shape available for a
melody — but it does put the melody lower more often than the other four shapes do,
which is what lets a note hold its place by changing strings.

**A four-note voicing on the four lowest strings is not offered.** With the melody on the
G string a four-note shape would have to occupy all of 6-5-4-3, and that does not sound
good — four voices in the bottom fourth of the compass, where the low E and the A string
crowd each other. A low melody is harmonised with a three-note shell instead, dropping the
5th degree that the fourth voice was contributing there.

**Duos are a hard rule, not a preference.** A two-note grip is only ever generated when
the melody is the chord's root or its 5th (`DUO_DEGREES`), because there the ear
supplies the missing guide tones. Under a 3rd or a 7th they *are* the chord's function,
and a bare duo there is the voicing that sounds wrong — so nothing is generated, and
the selector has to find a shell or a complete shape instead.

### The neck window

`arrange_progression` aims to keep the arrangement between frets 2 and 13
(`NECK_FRET_MIN`, `NECK_FRET_MAX`). This is a strong preference and **not** a filter: a
step with no voicing inside the window is still played, just outside it, because losing
a chord of the tune is worse than being a fret out of position. Pass `fret_min` and
`fret_max` to change it.

### How a voicing is chosen

`VoiceLeadingEngine.voicing_cost` is the whole selection rule as one comparable tuple,
lowest wins. It is a tuple rather than a weighted sum because these are real priorities
that must not be traded against each other:

1. **notes outside the chord** — a wrong note is not playable at all;
2. **frets outside the window** — a preference, as above;
3. **missing voices** — a partial harmonisation is a fallback, not a style;
4. **neck position** — how far the average fret is from the previous chord;
5. **pitch movement** of the voices, the classic voice-leading measure;
6. **fret span**, then **grip preference** as the final tie-break.

Criterion 4 is what keeps the hand from jumping, and it is measured in *absolute
fret numbers* rather than in pitches, because fret 8 means the same place on the neck
whichever string it is on. That is what lets a melody hold its position by moving to a
different string — a much smaller gesture than moving the hand.

Criterion 3 is what a `targets` texture exists to change, and it is worth being precise
about why it cannot be changed from inside the cost tuple.

## Texture: chords on the strong beats, fills between

The selection rule above has no idea where in the bar a note falls, and it ranks
**completeness above position**. So a bar of running eighths comes out as eight
re-struck four-note chords — a chord list, not an arrangement. The staff renderer's
`collapse` hides that in the *drawing*, but the selection never made the decision.

`texture="targets"` makes it. Pass each slot's `(bar, beat, duration)` as `timings` and
the engine states a full four-note chord on beats 1 and 3, filling everything else with
a shell, a 3rd/6th interval, or the melody alone:

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
2.0 fill x-x-10-9-10-x
3.0 target x-7-7-5-6-x
```

**Timing changes which grips are on the table, not the cost.** That is the whole design.
"Play fewer notes here" is not a preference competing against "stay in position" — it is
a change of what may be chosen at all, and a term in the cost tuple would let a
four-fret position outbid an entire texture. Generation and selection therefore stay
separate exactly as they already were, and the metric rule lives in one function,
`_roles_for_slot`.

**Nothing changes until you ask.** `timings` defaults to `None`, which means *we were
never told where these notes fall* — not *these notes are weak*. Every slot is then a
target and the output is byte-identical to what it has always been. That is pinned by
`tests/test_texture.py::TestBackwardCompatibility`, which asserts the exact tab of the
library's own demo cadences.

**The metre is read, not assumed.** `TARGET_BEATS` names *beats*, and `beats_per_bar`
decides which of them exist: a 3/4 head states its harmony on 1 and 3, while a 2/2
(cut-time) head has only two beats, so only the downbeat is a target. Three of the four
committed test scores are in cut time, and `arrange_xml_head` passes
`head.beats_per_bar` through for exactly this reason.

**A fill never costs the tune a chord.** If a fill slot has nothing thin to play, the
step is re-prepared as a principal note before anything is skipped. The texture is a
lighter *texture*, never a missing harmony — the same reasoning that makes the neck
window a penalty rather than a filter.

Over six corpus heads this takes the mean number of sounding notes per melody note from
**3.86 to 3.39**, and the share of steps voiced in four voices from **87% to 51%** —
which is about what beats 1 and 3 of a bar would predict. No head lost a step.

Both front ends expose it:

```bash
python -m arranger corpus --melid 218 --texture targets --tab staff
python -m arranger head tests/data/but_not_for_me.mxl --texture targets
```

`interval` is deliberately **not** gated on `DUO_DEGREES`, so a 3rd or a 6th can sit
under a melody that is itself the chord's 3rd or 7th — the case a duo refuses and a
passing tone constantly needs. When the melody is not a chord tone the walk may reach
for a note of the prevailing *key*, never a chromatic one, so a fill cannot quietly
reharmonise the bar.

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
Dm7 A4 x-8-10-7-10-x from A5
```

The step's `melody` is the pitch that actually sounds; `original_melody` keeps the
written one, and `format_progression` annotates the step with it:

```text
Dm7      A4   (transposed down an octave from A5) x-8-10-7-10-x
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
framework (there is no pytest dependency). Type checking uses
[pyright](https://pypi.org/project/pyright/), which is a dev-only tool — install it
with `.venv/bin/pip install pyright` (it is deliberately not a package dependency).

```bash
make test       # .venv/bin/python -m unittest discover -s tests -t . -v
make typecheck  # pyright over the modules and tests (must report 0 errors)
make demo       # run the built-in demonstration
make build      # build a wheel into dist/
make clean      # remove caches and build artefacts
```

`make` prefers the repository's `.venv/bin/python`; override it with
`make test PYTHON=python3`. The equivalent long form is
`.venv/bin/python -m unittest discover -s tests -t . -v` run from the repository
root (`-t .` is what lets `tests.support` import as a package module).

The engine lives in the `arranger` package, twelve modules in a strict dependency
order. `wjazzd.py` is separate, optional glue over the Weimar Jazz Database that
nothing in the package imports, so the library still works with no database present.
See `AGENTS.md` for the module map and the gate, and [docs/](docs/) for the reasoning
behind the engine and the renderers.

## Known limitations

- Voicings use two to four strings, never all six. The melody may be on the high E, B
  or G string; the A string and low E are inner voices only, so no grip puts the
  soprano on either. There are no barres, and a full six-string voicing is not
  modelled. One grip — the 6-4-3 shell — deliberately skips the A string.
- Melodies are confined to `G3`–`Bb5`.
- A fixed maximum fret span of 5 and fret range 0–18 are assumed. That span limit is
  what makes drop-2 the natural four-note grip, and it also rules out close position
  and drop-3 entirely: a close-position chord under a melody spans a seventh or more,
  while the four strings below the high E are only five semitones apart in tuning. The
  `drop3` and `closed` generators still exist for a caller who widens
  `GRIP_MAX_SPAN`, but they are not offered by default because they could never be
  played.
- Non-chord melody notes are handled only for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths and the
  half-diminished 9th) plus dim7; anything else keeps the legacy quality-only
  fallback.
- A chord tone with no matching inversion in the hand-authored drop-2 tables — a 9th
  in the melody of a 13 chord, for instance — falls through to the quality-only
  fallback, which can sound a note the chord does not contain. The selector rejects
  such a shape whenever a correct one exists, so an *arrangement* only hears it when
  nothing else is playable, but `get_drop2_voicings` still offers it. The shells, duos
  and 6-4-3 grip are unaffected: they build themselves from the chord's tones.
- The `sustain` strategy is structural — the API takes only `(note, quality, name)`
  triples, so rhythm and duration cannot be used to spot a brief passing tone.
- From the corpus side: the head selector is a heuristic and misses the head on some
  transcriptions (328 and 451 of the four "All the Things You Are" entries);
  `wjazzd.db` is a 42 MB download that must be supplied separately; and a slash bass
  is honoured as a preference rather than a hard constraint. See
  [How the head is found](#how-the-head-is-found).
- No CI and no release has been published to PyPI.

## License

MIT. See [LICENSE](LICENSE) for the full text.

The optional `gp` extra pulls in [PyGuitarPro](https://pypi.org/project/PyGuitarPro/),
which is LGPL-3.0. That is deliberately kept out of the runtime dependencies and
behind a lazy import, so this project is not a combined work of PyGuitarPro and
stays permissively licensed. `tabgp` also writes no PyGuitarPro code into this
repository.
