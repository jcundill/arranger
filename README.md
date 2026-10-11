# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Takes `(melody note, chord quality, chord name)` triples, builds voicings in several grip families, pins the melody to the soprano string, picks with one position-aware cost function. Also reads a written head from MusicXML and arranges that.

- **Seven grip families**, drop-2 first: `drop2`, `closed`, `drop3`, `drop24`, `drop2_6432`, `shell` and `duo` — four-note down to two-note guide-tone pairs. Every one sounds the chord's **3rd and 7th** (major vs minor); a `duo` sounds one of them under any chord tone — two notes is the floor ([grips](#grips)).
- **Melody pinned to soprano**, on high E, B or G string — low melody still harmonised in position.
- **Playable or absent.** Frets 0–18, span ≤5 (4 for duos), real string set, ≤4 fingers, no fifth fret from a held shape. Neck window is *preference, not filter* — losing a chord of the tune beats a fret out of position.
- **Non-chord melody notes**: extension, Barry Harris 6/dim7 substitution, or chord held under a passing tone ([non-chord melody notes](#non-chord-melody-notes)).
- **Five orthogonal axes**: where notes fall, who plays the bottom, which voices the guitar plays, which degrees a non-singing part states, where in the bar a chord lands ([the five axes](#the-five-axes)).
- **Heads from real sources** — MusicXML score, read as harmony *timeline*.
- **Dependency-light**: Python 3.11+ and [musthe](https://pypi.org/project/musthe/) only. MusicXML head *reading* needs no extra; MusicXML export and Guitar Pro export each behind own optional extra.

> The **distribution** is `jazz-arranger` (PyPI name `arranger` taken by unrelated project). **Import** name is `arranger`.

Why lives in [`docs/`](docs/): [engine.md](docs/engine.md) (selector, texture, cost tuple), [generated-grips.md](docs/generated-grips.md) (which chord tones a shape states), [renderers.md](docs/renderers.md) (tab, MusicXML, GP5), [comping-styles.md](docs/comping-styles.md) and [voices-axis.md](docs/voices-axis.md) (comping axes), [fingering.md](docs/fingering.md), [open-issues.md](docs/open-issues.md).

## Installation

```bash
pip install -e .        # or: make install
```

Plain install pulls `musthe` alone. Two optional extras add the writers, each behind a lazy import:

```bash
pip install -e '.[xml]' # adds music21,        for format_musicxml / write_musicxml
pip install -e '.[gp]'  # adds PyGuitarPro,    for format_gp5 / write_gp5
```

Nothing else needs them: `tabxml` imports `music21` when *called*, not imported — a GP5 run needs no music21, and vice versa. Or skip install and run from repo root:

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

Each step is an `ArrangementStep` (`chord`, `melody`, `voicing`, plus `non_chord_tone`, `strategy`, `harmonized_as`); `voicing` is a `Voicing` with `frets` (six entries, `-1` = muted), `top_fret`, `avg_fret` and helpers `tab_string()`, `fret_span()`, `midi_notes()`, `pitch_classes()`, `soprano_string()`.

Tab runs low E → high E, `x` = muted — `x-x-12-13-13-13` is a voicing on D-G-B-E with melody on high E.

## Reading a head from a MusicXML file

`arranger head` does the same job from **written melody + chord symbols** — a lead sheet, a melody-only score, anything MusicXML:

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

Both forms read: bare `.musicxml` and zipped `.mxl`.

**Repeats and endings honoured.** A backward repeat plays its section again, 1st/2nd ending taken in turn — `heres_that_rainy_day`, written 36 bars, arranged as the **66** a player hears (`1-30, 31-32, 1-30, 33-36`). The repeat lands in output: `--musicxml`, `--gp5`, `--html` and `--tab staff` write the **written** 36 bars with `|:` / `:|` signs and `1.` / `2.` brackets. (Plain `--tab line` still shows every played bar.)

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --tab staff --melody
python -m arranger head tests/data/i_was_doing_all_right.mxl --bars 1-3 --html head.html
```

### The flags

| flag | default | what it does |
|---|---|---|
| `--part` | the melody part | a `<score-part>` id, when score has several |
| `--bars` | whole head | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--non-chord-tone` | `extension` | how to harmonise melody note outside chord |
| `--fallback` | off | `diminished` — see [non-chord melody notes](#non-chord-melody-notes) |
| `--texture` | `uniform` | `uniform`, `targets`, `walking_bass` — see [texture](#texture) |
| `--bass` | follows `--texture` | `none`, `anchors`, `walk` — see [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| `--voices` | `auto` (all four) | any subset of `soprano,alto,tenor,bass` |
| `--harmony` | `auto` (= `guide`) | `full`, `guide`, `shell_root`, `root` |
| `--grid` | `every_note` | `every_note`, `freddie`, `charleston`, `joe_pass`, `final_and` — see [the grid](#where-a-chord-falls-the-grid-axis) |
| `--fret-min` / `--fret-max` | `2` / `13` | neck window to aim for |
| `--grips` | all seven | comma-separated grip families, **most preferred first** — `--grips shell,duo` |
| `--tab` | `line` | `staff` lays head on one six-line staff, spaced on real rhythm |
| `--melody` / `--mutes` | off | with `--tab staff`: add melody row / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write head to file — see [rendering](#rendering) |

Five of those flags are the library's own axes — `--texture`, `--bass`, `--voices`, `--harmony` and `--grid` — described once in [the five axes](#the-five-axes).

**Every written note sounds.** No reduction: `arranger head` plays tune as written, one step per note, each on written beat. Where *chords* fall is separate — the `grid=` axis — a note never quantised onto grid and dropped for sharing a slot.

**`--grips` is ordered.** Preference list, not a set: `shell` first displaces a four-note drop-2 whenever equal cost. Spell comma-separated, as flag's own default does — `--grips drop2,drop3` is two families, `--grips drop3,drop2` is same two other order, not same request.

### Five things reading a score requires

**Harmony is a timeline.** `<harmony>` precedes the note it governs, several can share a bar, a bar can carry none — chord *held* until next replaces it.

**Metre is the notated one.** `beat` is the beat *within* the bar in notated beats; both signature numbers needed — count says which beats exist, denominator how long one lasts. A 3/4 bar's eighths fall on 1.0, 1.5, 2.0, 2.5, 3.0 and 3.5; reading count as denominator puts every note of a 3/4 head a quarter of a beat early.

**Key signature read and written back** — tune in three flats exports in three flats. Score omitting `<key>` is C major.

**Tune is the top note of a chord.** MusicXML does not order group by pitch; in chord-melody part first member is lowest note. Everything else counted in `skipped`, not dropped.

**A chord this library cannot voice is counted, not guessed.** `Neapolitan` is real kind and real chord, but not one held under a melody — listed in `Head.unmapped`, run says so.

[docs/renderers.md](docs/renderers.md) has the importer's traps.

### It is the same arrangement code

Head from a score voiced by `arranger.slots.arrange_slots` — engine's own slot layer. Non-chord-tone strategies, opt-in diminished retry, repeated-melody hold and walking bass are engine's, not importer's; only *selection* is importer's business.

```python
from headxml import load_musicxml, head_skeleton

head = load_musicxml("tests/data/but_not_for_me.mxl")   # melody, timing, chords
print(head.title, head.beats_per_bar, len(head))
for triple, bar, beat, duration in head_skeleton(head):
    print(bar, beat, triple)
```

## Rendering

`arrange_progression` returns data; every tab renderer is a **pure function returning a string, printing nothing** — you decide how it displays.

Whole progression: `format_progression`:

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

Compact one-line analysis form; only shape `format_progression` has. For real six-line tab with chords on real beats, use `format_tab_staff` below.

Every step annotated: chord-tone melody names its degree (`(harmony under b7)`), a non-chord tone names the substitution applied, etc.

`format_progression` gives one line *per chord*. `format_tab_staff` lays a whole part along a single six-line staff, in reading order — here first bar of a committed score, metre passed by caller:

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

**Default output is tab and nothing else** — six string rows, frets in drawn dashes, `|` closing every bar, `*` on melody's string (B string whenever shape puts it there rather than high E).

**Width is duration.** Bar is a sixteenth-note grid; a note occupies as much of it as it sounds — half note drawn twice as wide as quarter, dashes after a fret are note still ringing. Pickup keeps rest in front. **Metre is the caller's**: pass `beats_per_bar` and `beat_type`, or a 2/2 head draws in 4/4.

Four flags add the annotation a score carries and a tab does not, all off by default: `show_chords` (chord names above, each starting where shape struck), `show_melody` (melody note names), `show_timing` (**metre** over first bar and **note value** of every column — `w` whole, `r` rest, `~` held; needs `step.duration` so appears for a head rather than a hand-written progression, and without it whole note and quarter draw identically), `show_mutes` (unsound strings as `x` — a voice still ringing is not restruck).

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

So tab carries metre, pickup rest before first chord, note values, and the one `Bb7` shape sounding same pitches while tune steps away and back over it.

Each **system** ruled to own width — long chord name widens its bar only — and `measures_per_line` sets bars per line before staff wraps.

From CLI the same renderer is `--tab staff`:

```bash
python -m arranger head but_not_for_me.mxl --tab staff --melody --bars-per-line 4
```

[docs/renderers.md](docs/renderers.md) covers full set and ASCII/HTML forms.

### MusicXML, for a notation program

`format_musicxml` writes same arrangement as a real score, to MuseScore, Sibelius or Final without retyping. Needs optional extra (`pip install '.[xml]'`):

```python
from arranger import write_musicxml

write_musicxml(steps, "head.musicxml", title="Blue Train", subtitle="John Coltrane")
```

Document is a **notation staff** — one staff, treble clef a chord-melody part is written in — carrying **chord symbols** on each change.

**No TAB staff in MusicXML**, deliberately: `music21` cannot write one a notation program renders correctly. For fingering use [Guitar Pro 5 export](#guitar-pro-5-for-a-tabber), which stores fret and string per note natively.

From CLI it is `--musicxml PATH`:

```bash
python -m arranger head but_not_for_me.mxl --musicxml head.musicxml
```

Chord name music21 cannot classify written as text with root still parsed out, not dropped.

### Guitar Pro 5, for TABs

`write_gp5` writes same arrangement as a **Guitar Pro 5 file** — Guitar Pro, TuxGuitar, any GP5 reader. Own extra (`pip install '.[gp]'`):

```python
from arranger import write_gp5

write_gp5(steps, "head.gp5", title="Blue Train", subtitle="John Coltrane")
```

```bash
python -m arranger head but_not_for_me.mxl --gp5 head.gp5
```

GP5 is a *tab* format, so every note carries own fret and string. Each step written on real beat, chord name above beat where chord changes, held shape one longer note rather than re-strike.

## One head, seven ways

Every run on committed score in `tests/data/`, each one flag changed. Output shown in linked section:

| ask | flag | output shown in |
|---|---|---|
| every note in full — default | *(nothing to pass)* | [quick start](#quick-start) |
| chords on strong beats | `--texture targets` | [texture](#texture) |
| walking bass under melody | `--texture walking_bass` | [texture](#texture) |
| shells only | `--grips shell` | [grips](#grips) |
| guide-tone duos | `--grips duo` | [grips](#grips) |
| tune on its own | `--voices soprano` | [who plays which voice](#who-plays-which-voice-bass-and-voices) |
| reduced chord where nothing else fits | `--fallback diminished` | [non-chord melody notes](#non-chord-melody-notes) |

## The five axes

`texture=`, `bass=`, `voices=`, `harmony=` and `grid=` answer five different questions, **orthogonal** — a band setting is a combination, not a mode: `--bass none --voices none` is a bassist on the root, a horn on the melody, guitar comping guide tones between them.

| axis | the question it answers | values |
|---|---|---|
| `texture=` | where notes fall — how thick the left hand is | `uniform`, `targets`, `walking_bass` |
| `bass=` | who plays the bottom | `none`, `anchors`, `walk` |
| `voices=` | which voices the guitar plays | any subset of `soprano`, `alto`, `tenor`, `bass` |
| `harmony=` | which **degrees** a part states when not singing | `full`, `guide`, `shell_root`, `root` |
| `grid=` | where in bar a chord falls | `every_note`, `freddie`, `charleston`, `joe_pass`, `final_and` |

**Each inert until asked.** `texture` defaults `uniform`, `bass` follows what texture implies, `voices` `auto` (all four — historical chord-melody), `harmony` `auto` (= `guide`), `grid` `every_note` — all what library already did. Nothing moves until named.

Two need a caveat. `harmony=full` is whole-chord chord-melody, which ordinary grip route voices; comping route has no implementation — asking there answered with `guide` today ([open issue 3](docs/open-issues.md)). And `texture=` changes which grips are on the table, not their cost: "play fewer notes here" does not compete against "stay in position", so it changes what may be chosen at all, not a term in the cost tuple.

## Texture

`texture` decides **what a slot is for** before any voicing chosen; the one knob that changes shape of an arrangement rather than detail. Three values:

| texture | what a step is |
|---|---|
| `uniform` *(default)* | every melody note gets full chord |
| `targets` | full chord on strong beats, thinner fills between |
| `walking_bass` | shell under melody, thumb line underneath |

### `targets` — chords on the strong beats

Selector ranks **completeness above position**, so bar of running eighths = eight re-struck four-note chords — chord list, not arrangement. Pass each slot's `(bar, beat, duration)` as `timings`: full chord on beats 1 and 3, rest filled with shell, interval, or melody alone:

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

Expect lighter arrangement stating harmony on beats, ringing between. Each step carries `role` — `target` or `fill` — and `metric_weight` (2 on beat 1, 1 on beat 3, 0 elsewhere, −1 when no timing supplied).

**A fill never costs the tune a chord.** Fill slot with nothing thin to play → step re-prepared as principal note, not skipped — texture is lighter, never missing. Measured effect in [docs/engine.md](docs/engine.md).

### `walking_bass` — a thumb line under the melody

Walking bass adds non-melody notes: on each beat a note from low E, A or D string, moving from tonic toward next chord as line rather than grid.

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --texture walking_bass
```

```text
Gmaj9    D4  5    3-x-4-4-3-x        (shell - 3rd & 7th, partial - 3 voices, the most this palette offers) (bass: G2, anchor)
Gmaj9    D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most a fill's palette offers)
Gmaj9    D4  5    2-x-x-x-x-x        (harmony under 5 - melody alone, the most a fill's palette offers - the shape above is held) (bass: F#2, connect)
Gmaj9/F# D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most a fill's palette offers - the written bass F# is not sounded - the lowest voice (D4) is 4 semitones from it)
```

Expect **more steps than melody had** — four here for three notes, bass grid finer than melody grid. Step marked `bass_only=True`: thumb only, previous shape held, melody not re-attacked.

Each bass note says purpose in `step.bass_role`: `anchor` (tonic), `connect` (passing note between chords), `approach` (semitone from next root), `enclosure`, `hold` (repeat). Thumb placed against **shape the hand holds**, not melody: adjacent bass strings five semitones apart — "prefer lowest string" and "stay where hand is" in permanent opposition; placement takes nearest fret to upper voicing.

Step with unplayable bass note keeps upper voicing and says so rather than writing unplayable tab (`no playable bass note for bass ... - no free string below the melody, no octave of that pitch below the shape, or the hand would need a fifth fret`). Commonest case middle one; counts over committed heads in [docs/open-issues.md](docs/open-issues.md) item 2, item 1 for melody-skipped bar.

## Who plays which voice: `bass` and `voices`

`texture` and `bass` answer separate questions — *where notes fall* and *who plays bottom*; `voices` adds third: **who plays tune**.

`bass` has `none`, `anchors` (root or 5th on strong beats), `walk` (note on every beat). Default follows request: `walking_bass` walks, melody-only selection naming bass voice walks (`--voices soprano,bass`), everything else none. Unknown spelling raises; combination left hand cannot accommodate **refused with warning**, arrangement proceeding without thumb line — walking line with gaps worse than none, losing bass costs less than losing tune.

### Which degrees a non-singing part states: `harmony=`

`harmony` read only when guitar has no tune of own — composes with `--voices`, does not compete: `voices` says *how many* notes and whether soprano ours, `harmony` says *which degrees* those notes are.

| `harmony=` | the part sounds | needs |
|---|---|---|
| `guide` (default) | 3rd and 7th — notes that say major or minor | two notes |
| `shell_root` | both guide tones **and** root or 5th underneath | three notes |
| `root` | root, or 5th where root unreachable — bass note alone | `--voices bass` alone |
| `full` | whole chord | ordinary chord-melody route — see [the five axes](#the-five-axes) |

`--harmony shell_root --voices alto,tenor,bass` = horn on tune, guitar stating quality *and* root underneath; needs three notes, asking with two refused with warning, not quietly thinned. Where guitar *is* singing, `--harmony` does nothing — shell chord-melody is `--grips shell`, a grip choice not degree family, melody stays pinned to top string.

`--bass none` + `--voices alto,tenor` together are the ensemble: bassist on root, sax on melody, guitar comping two middle voices. Chosen separately because separate decisions — "next to a bass player, none of the 1s and 5s, no walking motion" is `bass=none`; "melody isn't mine either" drops `soprano` from `voices`.

### Which voices the guitar plays

`--voices` = **comma-separated SATB list** — question a player asks is never "how many notes" but *which voices am I playing*:

| `--voices` | notes | the part |
|---|---|---|
| `auto` *(default)* | 4 | all four voices — historical chord-melody |
| `none` | 2 | shorthand for `alto,tenor` |
| `alto,tenor` | 2 | two middle voices |
| `alto` | 1 | one guide tone, high on neck |
| `bass` | 1 | one note in **bass register**, root or 5th |

Order irrelevant (`tenor,alto` = `alto,tenor`); capitals and stray spaces fine. Unknown voice name errors rather than silently dropping a voice.

**Naming one voice says *which*; `bass` is not same request as `alto`.** `alto`/`tenor` alone = guide tone under somebody else's melody — the 3rd, high on neck, where player puts one. `bass` alone = bottom of band: sounds **root, or 5th where root unreachable**, on low E, A or D. Both one note — arity cannot tell apart. `--voices bass` is bass *line*, states nothing about chord quality; name an inner voice too if quality wanted.

```bash
python -m arranger head tests/data/but_not_for_me.mxl --voices bass
```

```text
Bb7      F4  5    x-x-3-x-x-x        (comping - 5; the guitar does not play the tune)
Bb7      G4  13   x-x-3-x-x-x        (comping - 5; the guitar does not play the tune - non-chord tone -> Bb13 via extension)
Ebmaj    G4  3    6-x-x-x-x-x        (comping - 5; the guitar does not play the tune)
```

One note per step, on low E, A or D: **lowest voice of shape**, taken from whatever reaches it — root where convenient (`Bb7` gives `Bb`, not `D` a guide-tone shape would), 5th where not (every `Ebmaj` above). Annotation names degrees sounding, so line reads for itself. Melody column is *written* melody, which guitar not playing (`melody_voiced` False); still on step so band lines up against it.

Guitar comps under *written* melody, so melody note outside chord makes part restate its chord rather than ignore it; each such chord reported — `--voices bass` prints one `comping Bb7 as Bb13 (extension) to accommodate the melody note G4`-style warning per substituted chord.

`bass` treated this way only when named **alone**. `--voices tenor,bass` and `--voices alto,tenor,bass` are duo and shell, their lowest note belongs to shape's own string set.

### `voices=none` — guide-tone comping

Guitar stops singing, states chord instead. Shape is **shell**: 3rd and 7th, plus one more — the two notes deciding major vs minor; with no melody to support them nothing to add — fourth voice would be root or 5th, which carry no quality information.

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 \
    --texture targets --voices alto,tenor --bass none
```

```text
Gmaj9    D4  5    x-x-x-x-7-7        (comping - 3 & 7; the guitar does not play the tune)
Gmaj9    D4  5    x-x-x-x-7-7        (comping - 3 & 7; the guitar does not play the tune)
Gmaj9/F# D4  5    x-x-x-x-7-7        (comping - 3 & 7; the guitar does not play the tune)
```

Expect **two** notes per step — one per voice named. `--voices alto` one, `--voices alto,tenor,bass` three; arity follows selection rather than constant — part sounding more notes than caller named is a voice somebody else was to have. `step.melody` still carries horn's note, `step.melody_voiced` False — first is written tune, second is who sounds it.

**Shape chosen from chord alone.** `get_comping_voicings` takes no melody argument; `D5` and `G3` under same chord return *identical* candidate set. Chord tone in shell may land on same pitch class as melody — unremarkable, guide tone ear needs anyway. Every voiceable quality has comping shape in some playable position, checked over `CHORD_TONES_FROM_ROOT`. Quality with no readable root gets nothing: shell is claim about *this* chord's 3rd and 7th, guessing without root is how wrong notes get in.

**`texture` still decides where chords go.** Axes independent, not one mode: `--texture targets --voices none` gives shell on beats 1 and 3, thinner shell between, horn's line untouched throughout.

**Repeated melody holds whole shape.** Normally repeat is soprano-only re-strike with rest muted — no soprano to re-strike when guitar not singing, so shape held instead, guitar not playing moving line on exactly the beats arrangement handed tune away.

### The tune on its own

`voices=soprano` = melodic voice alone; every slot melody alone. `soprano,bass` = same line with walking thumb under it:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --voices soprano
```

```text
Gmaj9    D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most this palette offers)
Gmaj9    D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most this palette offers)
Gmaj9/F# D4  5    x-x-x-x-3-x        (harmony under 5 - melody alone, the most this palette offers - the written bass F# is not sounded - the lowest voice (D4) is 4 semitones from it)
```

Chord name still printed above each step as context; nothing under it voiced. `NC` bar under comping selection printed as empty bar (`silence="nc_comping"`), not dropped: no chord, so no guide tones, guitar genuinely silent while horn is not. Tab keeps bar count, lines up against tune.

## Where a chord falls: the `grid` axis

`--harmony` = *which degrees* a stab states, `--voices` = *whether guitar is singing*, `--grid` = **where in bar chord lands**.

| `--grid` | a chord falls on |
|---|---|
| `every_note` (default) | every written melody note |
| `freddie` | every beat of notated bar |
| `charleston` | beat 1, and upbeat of beat 2 |
| `joe_pass` | upbeat of every beat |
| `final_and` | upbeat of bar's **final** beat |

**Positions bar-relative — one name works in any metre.** "Upbeat of final beat" is 4.5 in 4/4, 2.5 in 2/2, 3.5 in 3/4 — same musical idea, three beat numbers. Spelling pattern as literal beat (`beat 4`) would name, on a 2/2 head, a beat that does not exist.

**What happens to a note with no chord on it depends who sings** — the one place axis needs two answers:

- **guitar singing** — note of tune still sounds, alone. No note dropped: chord-melody under `--grid joe_pass` plays melody throughout, places chords only on ands.
- **guitar comping** (`--voices alto,tenor`) — guitar **silent** that beat: melody belongs to horn, nothing for guitar to add. Step still emitted, so part keeps position and lines up against tune; draws as empty column.

**Grid places chords, not thumb.** Walked-beat grid thumb reads is own, so thumb sounds on beats where guitar strikes no chord at all — `bass_only` steps above are exactly that. Grid *does* change shape thumb is placed against: different chord above can move note or refuse it — measured on `but_not_for_me` with `--texture targets --bass walk`, `--grid freddie` walks three more beats than `--grid every_note`, all downbeats melody skips.

**Free-form grid** — naming positions directly, not choosing a row — not built yet. [docs/comping-styles.md §4.2](docs/comping-styles.md) has design.

## Grips

`arrange_progression` builds **several voicings per step** — every grip carrying melody inside neck window — picks with one cost function: chord can stay where previous left hand.

| grip | voices | what it is |
|---|---|---|
| `drop2` | 4 | four-note drop-2 on four strings below soprano, or bass moved to lower string (skipping D, or A) |
| `closed` | 4 | **close position** — chord tones stacked tightest under melody, no voice dropped (e.g. `x-x-5-4-3-2`) |
| `drop3` | 4 | **drop-3** — third voice down an octave; every other voice still chord tone |
| `drop24` | 4 | **drop-2 & 4** — second *and* fourth voices an octave down |
| `drop2_6432` | 4 | **6-4-3-2** — low E, D, G and B, so bass can be root |
| `shell` | 3 | 3rd and 7th plus one more: 1-2-3, 2-3-4, 5-4-3, **6-4-3**, **5-3-2**, **1-3-4** |
| `duo` | 2 | chord's guide tone — 3rd, or 4th on sus — under any chord tone |
| `interval` | 2 | 3rd, 6th or 10th below melody — a *fill*, not a harmony |

First seven are `GRIP_PREFERENCE`: the order families are tried in **and** order an exact tie between equal-cost shapes breaks in — no separate grip term in cost function. Cannot reorder complete chord against partial though: note count is own criterion, so four-note shape always beats shell that costs same. `interval` excluded — interval is texture not harmony — `targets` offers it for fills only.

`closed` sits **second**, right after `drop2`: tightest shape there is, so where melody can fret it at all it beats other four-note families on a tie. Most melodies cannot — close-position chord under melody is seventh or more of pitch on four strings only 4–5 semitones apart in tuning — usually never generated rather than generated and rejected.

`drop3` and `drop24` derive from close-position stack under melody, keeping every *other* voice chord tone — measured over every quality and every melody, zero wrong notes where drop-2's quality-only fallback produces hundreds. [docs/engine.md](docs/engine.md) has derivation and cost tuple; [docs/generated-grips.md](docs/generated-grips.md) the rule deciding which chord tones a shape states.

Two families thin by design, run says so:

**Shells** — `--grips shell` reduces every chord to three notes:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips shell
```

```text
Gmaj9    D4  5    x-x-4-4-3-x        (shell - 3rd & 7th, partial - 3 voices, the most this palette offers)
Gmaj9    D4  5    x-x-x-x-3-x        (melody repeated - single note)
Gmaj9/F# D4  5    x-x-4-4-3-x        (shell - 3rd & 7th, partial - 3 voices, the most this palette offers)
```

Open, unlabelled sound: 3rd and 7th make chord major or minor; no root lets player imply it.

**Duos** — `--grips duo` leaves two notes: melody + chord's **guide tone** — 3rd, or 4th on suspended chord (7th when melody already 3rd):

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml --bars 1-2 --grips duo
```

```text
Gmaj9    D4  5    x-x-x-4-3-x        (duo - melody + b3, partial - 2 voices, the most this palette offers)
Gmaj9    D4  5    x-x-x-x-3-x        (melody repeated - single note)
Gmaj9/F# D4  5    x-x-x-4-3-x        (duo - melody + b3, partial - 2 voices, the most this palette offers - the written bass F# is not sounded - the lowest voice (B3) is 5 semitones from it)
```

Sparsest thing library plays — harmony implied not stated, for solo voice or leaving room over a band.

`common_grips.md` is chart of drop-2 shapes, **generated** from these tables by `grip_chart.py`, checked by `make chart-audit`. Never hand-edit.

## Low-register melodies

Melodies below high E open pitch (`E4`) cannot be voiced on that block. By default melody may also pin to B string (voicing on A-D-G-B) and **G string** (bottom four strings) — floor drops to `G3`:

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

All three sit in one position on bottom four strings. Restricting melody to high E and B — `top_strings=(5, 4), grips=("drop2",)` — three four-note shapes in lower position:

```python
for step in engine.arrange_progression(low, top_strings=(5, 4), grips=("drop2",)):
    print(step.chord, step.voicing.tab_string())
```

```text
Dm7 x-3-3-2-3-x
G7  x-2-3-0-3-x
Cmaj7 x-2-2-0-1-x
```

`Cmaj7` is interesting one: `x-2-2-5-x-x` is three-note **6-4-3 shell** on D and G strings, because four-note 6-5-4-3 with melody on top does not sound good. Deliberately no four-note block for G-string soprano — G string carries shells, not chords. `top_strings=(5,)` restricts to traditional high-E block.

## High melodies, and the neck window

Every voicing confined frets 0–18, span ≤5 (4 for duo and interval), on real string set. `NECK_FRET_MIN`/`NECK_FRET_MAX` — frets 2–13 — range selector *aims* for, not hard filter: step with no voicing inside window still played, just outside it, because losing chord of tune beats fret out of position. Run header echoes window whether or not met.

Cost function ranks shape's **correctness first**: out-of-chord notes, then frets outside window, then missing voices, then span, then neck position, then inner voices' movement, finally bass function. Tight shape beats shape nearer middle of neck; complete chord beats partial at any position. Spans of 0 and 1 frets equal — one fret stretch not worth moving hand — why order puts span above position but not last fret of reach. That order is library's central invariant; measurement in [docs/engine.md](docs/engine.md).

Melody whose only position sits above `HIGH_FRET_LIMIT` (13) voiced an octave down.

```python
high = [("A5", "m7", "Dm7")]
for step in engine.arrange_progression(high):
    print(step.chord, step.melody, step.voicing.tab_string(),
          "from", step.original_melody)
```

```text
Dm7 A4 10-x-10-10-10-x from A5
```

Step's `melody` is pitch that sounds, `original_melody` keeps written one; `format_progression` annotates:

```text
Dm7      A4  5    10-x-10-10-10-x    (harmony under 5 - transposed down an octave from A5 - 4 voices)
```

Two deliberate limits:

- **Only repositions a voicing that exists.** Melody unreachable at written pitch (`B5` fret 19, `C6` fret 20 — past end of board) not silently respelled. Position emitted empty, warning names problem, `silence="out_of_reach"` on step.
- **Per step, and melody only.** No phrase transposition, so melody leaping across limit can arrive octave apart from neighbour: no step ever unplayable, cost is one melodic interval.

`get_all_drop2_voicings` deliberately *not* filtered by fret — pure candidate generation; `get_octave_down_candidates` is separate, explicitly opt-in entry for transposed form.

## Non-chord melody notes

Melodies do not always land on chord tones. Bar 2 of "All of Me" moves `C5 → D5 → C5` over `Cmaj7`, `D5` being the 9th. Pass `non_chord_tone=` to `arrange_progression` (or call `is_chord_tone` / `resolve_non_chord_tone` directly) to choose how such notes are harmonised:

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

- `extension` (default) — absorb note as extension: `D5` over `Cmaj7` becomes `Cmaj9`, `D` chord tone again, shape sounds only `Cmaj7`-family pitches. Mapping in `VoiceLeadingEngine.NON_CHORD_TONE_EXTENSIONS`: 9ths, 6/9ths, #11 (`Cmaj7#11`), 11th (`G7sus4`), #11/b13 over dominants, 13th, half-diminished 9th (`Am9b5`), 9th over plain triad (`Ebmaj` under `F4` becomes `Ebadd9`).
- `diminished` — Barry Harris 6/dim7 substitution: passing `D5` voiced inside `Bdim7` (dim7 semitone below note line resolves to), smooth chromatic resolution.
- `sustain` — hold previous chord's three inner voices, move only melody — shape held under passing tone, `harmonized_as` reporting chord still sounding under it.

Every `ArrangementStep` records what happened: `non_chord_tone`, `strategy`, `harmonized_as` (e.g. `"Cmaj9"`). Melodies already chord tones arranged exactly as before, whichever strategy selected.

**`--fallback diminished` is opt-in retry.** When *no* strategy leaves playable shape, written chord genuinely replaced by dim7 substitution; run says how many steps. Same two bars without flag, and with:

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

Expect tune changed: written `Am7` gone, fallback states full `Bdim7` where default gave up with two voices. Colour to opt into, not default — why run counts steps it touched.

On **comping** selection (`voices=` with no soprano — guitar states chord while somebody else sings) same flag moves chord guitar *states*, never anything it sings. Non-chord note at an **onset** reharmonises guitar's chord: `D5` over `Cmaj7` under `voices="alto,tenor"` gives `Cmaj9` (`extension`) or `Bdim7` (`diminished`) in guide-tone voices, `harmonized_as` reports, diagnostic naming forcing note. Held note and silent grid position state written chord unchanged; `sustain` leaves comping part's harmony exactly as chord symbol writes it.

## Supported chord qualities

Seventh: `maj7`, `6`, `m7`, `m7b5`, `dim7`, `m6`, `mMaj7`, `7`, `7b9`, `7alt`. Extensions: `maj9`, `m9`, `9`, `6/9`, `13`. Triads: `maj`, `m`, `aug`. Suspended: `sus4`, `sus2`, `7sus4`. Added-note and altered: `add9`, `madd9`, `7b5`, `7#5`, `7#11`, `7b13`, `maj7#11`, `m9b5`.

Aliases resolve case-sensitively: `M7` major seventh, `m7` minor seventh, `M` major triad. Aliases: `min7`, `min7b5`, `ø7`, `ø`, `half-dim`, `°7`, `°`, `dim`, `min6`, `minMaj7`, `mmaj7`, `min9`, `dom7`, `dom9`, `dom13`, `M7`, `M9`, `69`, `min`, `-`, `+`, `sus`, `7sus`. Two conventions: `dim` means `dim7` (diminished triad not voiced); bare `C` not assumed major — spell `Cmaj` or `CM`.

Drop-2 shape has four voices, so triad templates double root octave below stack:

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

Unsupported qualities return no voicings; `arrange_progression` warns and skips step, no raise.

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

`make check` is the gate. Tests stdlib `unittest` (no pytest); type check [pyright](https://pypi.org/project/pyright/), lint [ruff](https://pypi.org/project/ruff/), both dev-only, deliberately not package dependencies (`make install-dev`).

`make` prefers repo's `.venv/bin/python`; override with `make test PYTHON=python3`. Long form: `.venv/bin/python -m unittest discover -s tests -t . -v` from repo root (`-t .` is what lets `tests.support` import as package module).

**CI runs `make check` on Python 3.11 through 3.14**, both optional extras installed so guarded tests not silently skipped. Whole gate in one job: nothing a clean clone cannot run, so green check means entire suite ran.

Engine lives in `arranger` package, fifteen modules in strict dependency order that `tests/test_package_dag.py` asserts from AST. `AGENTS.md` has module map and conventions; [docs/](docs/) the reasoning behind engine and renderers.

## Known limitations

- Voicings 2–4 strings, never all six. Melody on high E, B or G; A and low E inner voices only, no grip puts soprano on either. No barré chord — fret `0` when voice lands on open string — no full six-string voicing modelled. `fingers.py` assigns finger per string and marks barre where two strings share fret, but no renderer prints fingering: tab is what you read. One grip — 6-4-3 shell — deliberately skips A string.
- Melodies confined `G3`–`Bb5`.
- Fixed max fret span 5 (4 for duo and interval), fret range 0–18, no step may need fifth fret from hand already holding shape. `close` offered, second in preference order, usually unreachable: most melodies cannot fret it inside that budget, wins only where it does.
- Non-chord melody notes handled only for `NON_CHORD_TONE_EXTENSIONS` mappings (9ths, 6/9s, 11ths, #11s, b13s, 13ths, half-diminished 9th, 9th over plain triad) plus dim7; anything else keeps quality-only fallback — and melody-only palette (`shell`, `duo`, `interval`) has no fallback to keep, note sounds alone under its chord, step says `(melody alone - no voicing for this chord)`.
- Chord-tone drop-2 with no inversion for — 9th in melody of 13 chord — falls to quality-only fallback, which can sound note chord does not contain. Selector rejects such shape whenever correct one exists, so *arrangement* only hears it when nothing else playable, but `get_drop2_voicings` still offers it. Shells, duos, 6-4-3 grip unaffected: build from chord's tones.
- `sustain` strategy structural — API takes only `(note, quality, name)` triples, rhythm and duration cannot spot brief passing tone.
- Neck window preference not filter, so `--fret-min`/`--fret-max` may not be honoured where nothing playable inside. Header echoes window either way.
- Slash bass honoured as preference not hard constraint: selector narrows candidates by it, engine's own rule within that set — voicing that cannot honour bass still playable.
- Beat melody skips *inside* a bar it occupies has no chord of its own, chord in force stored per melody note. Bar-level half built — bar melody never enters arranged under every route — rest is [open issue 1](docs/open-issues.md).
- No release published to PyPI.

## License

MIT. [LICENSE](LICENSE) full text.

Optional `gp` extra pulls in [PyGuitarPro](https://pypi.org/project/PyGuitarPro/), LGPL-3.0. Deliberately kept out of runtime dependencies and behind lazy import, so project is not a combined work of PyGuitarPro and stays permissively licensed. `tabgp` writes no PyGuitarPro code into this repository.
