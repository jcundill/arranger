# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Takes `(melody note, chord quality, chord name)` triples, builds voicings in several grip families, pins the melody to the soprano string, picks with one position-aware cost function. Also reads a written head from MusicXML and arranges that.

- **Seven grip families**, drop-2 first: `drop2`, `closed`, `drop3`, `drop24`, `drop2_6432`, `shell` and `duo` — four-note down to two-note guide-tone pairs. Every one sounds the chord's **3rd and 7th** (major vs minor); a `duo` sounds one of them under any chord tone — two notes is the floor ([grips](#grips)).
- **Melody pinned to soprano**, on high E, B or G string — low melody still harmonised in position.
- **Playable or absent.** Frets 0–18, span ≤5 (4 for duos), real string set, ≤4 fingers, no fifth fret from a held shape. Neck window is *preference, not filter* — losing a chord of the tune beats a fret out of position.
- **Non-chord melody notes**: extension, Barry Harris 6/dim7 substitution, or chord held under a passing tone ([non-chord melody notes](#non-chord-melody-notes)).
- **Six orthogonal axes**: how thick the chord part is, who plays the bottom, which parts the guitar takes, which degrees a non-singing part states, when each part sounds, and how a compound metre is felt ([the request and the axes under it](#the-request-and-the-axes-under-it)).
- **Heads from real sources** — MusicXML score, read as harmony *timeline*.
- **Dependency-light**: Python 3.11+ and [musthe](https://pypi.org/project/musthe/) only. MusicXML head *reading* needs no extra; MusicXML export and Guitar Pro export each behind own optional extra.

> The **distribution** is `jazz-arranger` (PyPI name `arranger` taken by unrelated project). **Import** name is `arranger`.

Why lives in [`docs/`](docs/): [engine.md](docs/engine.md) (the selector, the axes, the cost tuple), [renderers.md](docs/renderers.md) (tab, MusicXML, GP5), and [open-issues.md](docs/open-issues.md) (the open bugs, each with its measurement). The plan documents that built this — parts, comping styles, generated grips, fingering, `voices=` — are in [`docs/history/`](docs/history/).

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

**The six questions have a second spelling.** `Request` carries them as one value (`from arranger import Request`), so the same call asks for a walking line under the tune — `engine.arrange_progression(progression, request=Request(bass_on="every-beat", bass_notes="walk"))`. Both spellings and what each question means are in [the request and the axes under it](#the-request-and-the-axes-under-it).

Each step is an `ArrangementStep` (`chord`, `melody`, `voicing`, plus `non_chord_tone`, `strategy`, `harmonized_as`); `voicing` is a `Voicing` with `frets` (six entries, `-1` = muted), `top_fret`, `avg_fret` and helpers `tab_string()`, `fret_span()`, `midi_notes()`, `pitch_classes()`, `soprano_string()`.

Tab runs low E → high E, `x` = muted — `x-x-12-13-13-13` is a voicing on D-G-B-E with melody on high E.

## Reading a head from a MusicXML file

`arranger head` does the same job from **written melody + chord symbols** — a lead sheet, a melody-only score, anything MusicXML:

```bash
python -m arranger head tests/data/synthetic_cut_time.mxl --bars 1-3
```

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

Both forms read: bare `.musicxml` and zipped `.mxl`.

**Repeats, endings and jumps honoured.** A backward repeat plays its section again, 1st/2nd ending taken in turn — `synthetic_repeat_slash`, written 8 bars, arranged as the **12** a player hears (`1-4, 5-6, 1-4, 7-8`). A D.C. / D.S. returns to the start or the Segno, a `To Coda` diverts on the way back, and a `Fine` ends the return. The form lands in output: `--musicxml`, `--gp5`, `--html` and `--tab staff` write the **written** bars with `|:` / `:|` signs, `1.` / `2.` brackets and the Segno / Coda / Fine / D.C. / D.S. directions. (Plain `--tab line` still shows every played bar.)

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --tab staff --note-names
python -m arranger head tests/data/synthetic_triplets.mxl --bars 1-3 --html head.html
```

### The flags

| flag | default | what it does |
|---|---|---|
| `--part` | the melody part | a `<score-part>` id, when score has several |
| `--bars` | whole head | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--non-chord-tone` | `extension` | how to harmonise melody note outside chord |
| `--fallback` | off | `diminished` — see [non-chord melody notes](#non-chord-melody-notes) |
| `--no-melody` | off | the guitar does not sing: the tune belongs to somebody else, and the chord defaults to every felt beat |
| `--chord-on` | `melody` | when the chord attacks: the written onsets, `none`, or positions such as `1and` or `every-beat` |
| `--chord-notes` | `full` | how many chord tones it states: `full`, `3`, `2`, `1` |
| `--chord-fills` | `none` | what it states in a notated melody rest: `hold` one chord, or `comp` a felt beat at a time |
| `--bass-on` | `none` | when the thumb attacks: positions, or `every-beat` |
| `--bass-notes` | `root` | what each thumb note is: the root, root-then-5th, or a walk |
| `--fret-min` / `--fret-max` | `2` / `13` | neck window to aim for |
| `--tab` | `line` | `staff` lays head on one six-line staff, spaced on real rhythm |
| `--note-names` / `--mutes` | off | with `--tab staff`: name each step's melody note / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write head to file — see [rendering](#rendering) |

**The request is six questions, and each has two spellings.** The flags above are one; `Request(...)` is the other, so a library caller asks the same six — `engine.arrange_progression(progression, request=Request(melody=False, chord_on="every-beat"))` is the comp for a horn. Underneath both are the engine's own axes — `texture`, `bass`, `parts` and `harmony` — which are the implementation, described in [the request and the axes under it](#the-request-and-the-axes-under-it); a band setting is a combination of them rather than a mode. **An axis is reached through `options=ArrangeOptions(...)`**, which is the one door to them, so `engine.arrange_progression(progression, request=Request(...), options=ArrangeOptions(texture="targets"))` is one call naming both. The metre is not an axis but an input fact like `timings=`: a score states it, and a progression built without a file declares it as one `TimeSignature`.

**Every written note sounds.** No reduction: `arranger head` plays tune as written, one step per note, each on written beat. Where *chords* fall is a separate question — `--chord-on` — and a note is never quantised onto a position and dropped for sharing a slot.

**Grip order is the engine's.** No flag names a family: the order families are tried in is `GRIP_PREFERENCE`, and an exact tie between equal-cost shapes breaks in that same order — see [grips](#grips). `--chord-notes` is what narrows the palette, by saying how many chord tones a step may state.

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

head = load_musicxml("tests/data/synthetic_cut_time.mxl")   # melody, timing, chords
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
Dm7      D5  Root x-x-10-10-10-10   (harmony under Root - 4 voices -
                                    sounding: C b7, F b3, A 5, D Root)
G7       B4  3    13-x-12-12-12-x   (harmony under 3 - 4 voices - sounding: F b7, D 5, G Root, B 3)
Cmaj7    C5  Root x-x-9-9-8-8       (harmony under Root - 4 voices -
                                    sounding: B 7, E 3, G 5, C Root)
```

Compact analysis form; only shape `format_progression` has — four columns per step, the explanation trailing them and wrapped onto the lines below when it is too long for one. For real six-line tab with chords on real beats, use `format_tab_staff` below.

Every step annotated: chord-tone melody names its degree (`(harmony under b7)`), a non-chord tone names the substitution applied, a shape names the voices it sounds (`sounding: Bb 5, Eb Root, G 3, C 6`) — note and degree each — etc.

`format_progression` gives one block *per chord*. `format_tab_staff` lays a whole part along a single six-line staff, in reading order — here first bar of a committed score, metre passed by caller:

```python
from headxml import arrange_xml_head
from arranger import format_tab_staff

steps, head, notes = arrange_xml_head("tests/data/synthetic_cut_time.mxl", section=(0, 2))
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
python -m arranger head tests/data/synthetic_cut_time.mxl --tab staff --note-names --bars-per-line 4
```

[docs/renderers.md](docs/renderers.md) covers full set and ASCII/HTML forms.

### MusicXML, for a notation program

`format_musicxml` writes same arrangement as a real score, to MuseScore, Sibelius or Final without retyping. Needs optional extra (`pip install '.[xml]'`):

```python
from arranger import write_musicxml

write_musicxml(steps, "head.musicxml", title="Blue Train", subtitle="John Coltrane")
```

Document is a **notation staff** — one staff, treble clef a chord-melody part is written in — carrying **chord symbols** on each change.

**No TAB staff in MusicXML**, deliberately: `music21` cannot write one a notation program renders correctly. For fingering use [Guitar Pro 5 export](#guitar-pro-5-for-tabs), which stores fret and string per note natively.

From CLI it is `--musicxml PATH`:

```bash
python -m arranger head tests/data/synthetic_cut_time.mxl --musicxml head.musicxml
```

Chord name music21 cannot classify written as text with root still parsed out, not dropped.

### Guitar Pro 5, for TABs

`write_gp5` writes same arrangement as a **Guitar Pro 5 file** — Guitar Pro, TuxGuitar, any GP5 reader. Own extra (`pip install '.[gp]'`):

```python
from arranger import write_gp5

write_gp5(steps, "head.gp5", title="Blue Train", subtitle="John Coltrane")
```

```bash
python -m arranger head tests/data/synthetic_cut_time.mxl --gp5 head.gp5
```

GP5 is a *tab* format, so every note carries own fret and string. Each step written on real beat, chord name above beat where chord changes, held shape one longer note rather than re-strike.

## One head, twelve ways

Every run on a committed score in `tests/data/`, each one request changed. Output shown in the linked section:

| ask | flag | `Request(...)` | output shown in |
|---|---|---|---|
| every note in full — the default | *(nothing to pass)* | `Request()` | [quick start](#quick-start) |
| a chord stab on the and of 1 | `--chord-on 1and` | `Request(chord_on="1and")` | [when the chord attacks](#when-the-chord-attacks---chord-on) |
| the harmonisation **and** the stab | `--chord-on melody,1and` | `Request(chord_on="melody,1and")` | [when the chord attacks](#when-the-chord-attacks---chord-on) |
| chords on the strong beats | `--chord-on 1,3` | `Request(chord_on="1,3")` | [how thick the chord part is](#how-thick-the-chord-part-is---chord-notes) |
| shells only | `--chord-notes 2` | `Request(chord_notes="2")` | [grips](#grips) |
| guide-tone duos | `--chord-notes 1` | `Request(chord_notes="1")` | [grips](#grips) |
| tune on its own | `--chord-on none` | `Request(chord_on="none")` | [the tune on its own](#the-tune-on-its-own) |
| a chord in the tune's rests | `--chord-on none --chord-fills hold` | `Request(chord_on="none", chord_fills="hold")` | [what the chord does in a rest](#what-the-chord-does-in-a-rest---chord-fills) |
| walking bass under the melody | `--bass-on every-beat --bass-notes walk` | `Request(bass_on="every-beat", bass_notes="walk")` | [a thumb line under the melody](#a-thumb-line-under-the-melody) |
| comp for a horn | `--no-melody --chord-on every-beat` | `Request(melody=False, chord_on="every-beat")` | [the chord alone](#the-chord-alone---no-melody) |
| a lone bass line | `--no-melody --chord-on none --bass-on every-beat` | `Request(melody=False, chord_on="none", bass_on="every-beat")` | [the thumb alone](#the-thumb-alone) |
| reduced chord where nothing else fits | `--fallback diminished` | *(not a request field — `fallback=`)* | [non-chord melody notes](#non-chord-melody-notes) |

## The request, and the axes under it

`head` asks **six questions**, and each has one flag: who plays the tune, when each accompaniment layer attacks, what each layer states, and what the chord does in a notated melody rest. A library caller asks the same six through `Request`, whose field names are the flags' own:

| question | flag | `Request(...)` | values |
|---|---|---|---|
| who plays the tune? | `--no-melody` | `melody=False` | the guitar does, unless this is passed |
| when does the chord attack? | `--chord-on` | `chord_on="1and"` | positions in felt beats, or `melody`, `none`, `every-beat` |
| what does the chord state? | `--chord-notes` | `chord_notes="2"` | `full`, `3`, `2`, `1` |
| what does it do in a melody rest? | `--chord-fills` | `chord_fills="hold"` | `none`, `hold`, `comp` |
| when does the thumb attack? | `--bass-on` | `bass_on="every-beat"` | positions, `every-beat`, or `none` |
| what does each thumb note state? | `--bass-notes` | `bass_notes="walk"` | `root`, `root-5th`, `walk` |

**The default adds nothing.** `head FILE` is one chord under each written melody note, held for that note — no bass, no extra attacks, no chord invented in a rest. Everything else is asked for. `Request()` is that same default, so `arrange_progression(progression)` and `arrange_progression(progression, request=Request())` are one arrangement.

**Those six are the whole request, and `Request` carries them as one value.** A library caller passes it beside the progression — `engine.arrange_progression(progression, timings=timings, request=Request(bass_on="every-beat", bass_notes="walk"))`. Underneath the request are the engine's own axes, derived from it and still the implementation. A band setting is a combination of them rather than a mode, and **`options=ArrangeOptions(...)` is the one door to them** — an axis has no keyword of its own:

| axis | the question it answers | values |
|---|---|---|
| `ArrangeOptions(texture=…)` | how many chord tones the chord part states, and where the fuller positions are | `uniform`, `targets`, `chord3`, `chord2`, `chord1` |
| `ArrangeOptions(bass=…)` | which note rules the thumb line may state | `none`, `root`, `root,5th,approach,nearest` |
| `ArrangeOptions(parts=…)` | which of melody, bass and chord the guitar takes | any subset of `melody`, `bass`, `chord` |
| `ArrangeOptions(harmony=…)` | which **degrees** a part states when not singing | `full`, `guide`, `shell_root` |

The request and the metre are the exception the other way: they are **input facts** — what is being arranged rather than how to play it — so `request=` and `time_signature=` sit beside `options=` and may be used in the same call. Every other keyword given beside `options=` raises rather than being silently ignored.

The mapping is mechanical and one-way: `--chord-notes full` is `texture="uniform"` and `3`/`2`/`1` are `chord3`/`chord2`/`chord1`; `--bass-notes root` is `bass="root"`, `root-5th` is `"root,5th"` and `walk` the full four; `--chord-on` and `--bass-on` become each layer's rhythm; and `parts` is derived from which of the three the request leaves sounding. A value of `texture` that names a **rhythm** — `targets` — has no request spelling on purpose: its rhythm is `--chord-on 1,3`, and its automatic thinning between the strong beats is the Python API's own business (see [the strong beats](#the-strong-beats)).

The metre's **third fact**, its grouping, is not an axis either. A count says how many denominator units a bar has and the denominator how long one lasts, but neither says that 12/8 is felt as four dotted-quarter beats rather than twelve eighths. **The score states it**, and the importer reads it in this order: an `N+N` direction (a 5/4 marked `3+2`), the primary beaming (a 7/4 beamed 2+2+3, a 12/8 beamed 4+4+4), then a metronome pulse (a dotted quarter in 12/8). `auto` falls back to the metre's convention — threes for 6/8, 9/8 and 12/8; one per beat otherwise — and a conventional simple metre ignores its beaming, because a notation program's beam pairs restate the beat rather than group it. **A progression built without a file declares the metre as one `TimeSignature`**: `engine.arrange_progression(progression, time_signature=TimeSignature(5, 4, grouping="3+2"))`. Omitting it means common time, and the signature validates the grouping against the bar when it is built. A caller overriding a score's grouping states the same value — `arrange_xml_head(path, time_signature=TimeSignature(12, 8, "3+3+3+3"))` — and its count and denominator must agree with the file's, because the file owns the bars the slots came from. The grouping moves the `--chord-on` positions and the walking bass together — in 12/8 `every-beat` is four stabs, not twelve.

Two need a caveat. `harmony="full"` is whole-chord chord-melody, which ordinary grip route voices; comping route has no implementation — asking there answered with `guide` today ([open issue 3](docs/open-issues.md)). And `texture` changes which shapes are on the table, not their cost: the arity is a **ceiling** the palette is built to, so "play fewer notes here" does not compete against "stay in position" — it changes what may be chosen at all, not a term in the cost tuple.

## How thick the chord part is: `--chord-notes`

**How many chord tones the chord part states.** The right hand has four digits, one string may be carrying the tune and one the thumb line, so what is left over is the chord part's arity:

| `--chord-notes` | the chord part states | the engine's axis |
|---|---|---|
| `full` *(default)* | the most the arithmetic allows — four strings, less one for the melody and one for a thumb line that sounds | `ArrangeOptions(texture="uniform")` |
| `3` | at most three chord tones | `ArrangeOptions(texture="chord3")` |
| `2` | at most two — the guide pair | `ArrangeOptions(texture="chord2")` |
| `1` | at most one | `ArrangeOptions(texture="chord1")` |

**A ceiling, not a fixed count.** The palette a step is offered is every family **up to** that arity, so a shape that can state one more does; a step that cannot state two states one rather than nothing. `--chord-notes 2` with the tune ours is the tune plus two chord tones — the shell; the same arity with `--no-melody` is a chord alone.

**`full` means "the most that fits", and a bass costs a string.** With `--bass-on` naming any position, melody + bass + chord cannot exceed four strings (`p-i-m-a`), so `full` under a bass is melody + two chord tones + the thumb. A request that could not fit is refused rather than quietly thinned.

### The strong beats

The selector ranks **completeness above position**, so a bar of running eighths is eight re-struck four-note chords — a chord list rather than an arrangement. Asking for the strong beats only is a **rhythm**: `--chord-on 1,3` in 4/4 (or `1` in 2/2), and the melody notes between are the tune alone:

```bash
python -m arranger head tests/data/synthetic_common_8.musicxml --bars 1-2 --chord-on 1,3
```

The engine's `ArrangeOptions(texture="targets")` does the same thing **and** thins the fills between the targets automatically — a shell, a third or sixth, or the melody alone. That automatic half has no request spelling: it is a Python-API value, and a `--chord-between` would be its CLI form. The rhythm half is `--chord-on`, which is why the two are no longer one flag.

```python
progression = [
    ("C5", "maj7", "Fmaj7"),   # beat 1 - the target
    ("E5", "maj7", "Fmaj7"),   # fill
    ("A4", "maj7", "Fmaj7"),   # fill
    ("F4", "maj7", "Fmaj7"),   # beat 3 - the target
]
timings = [(0, 1.0, None), (0, 1.5, None), (0, 2.0, None), (0, 3.0, None)]

steps = engine.arrange_progression(
    progression, timings=timings, options=ArrangeOptions(texture="targets")
)
for step in steps:
    print(step.beat, step.role, step.voicing.tab_string())
```

```text
1.0 target x-x-7-9-6-8
1.5 fill x-x-x-10-10-12
2.0 fill x-x-10-9-10-x
3.0 target x-7-7-5-6-x
```

Expect a lighter arrangement stating the harmony on the beats and ringing between. Each step carries `role` — `target` or `fill` — and `metric_weight` (2 on beat 1, 1 on beat 3, 0 elsewhere, −1 when no timing was supplied).

**A fill never costs the tune a chord.** A fill slot with nothing thin to play is re-prepared as a principal note, not skipped — the texture is lighter, never missing. Measured effect in [docs/engine.md](docs/engine.md).

### A thumb line under the melody

`--bass-on` says **when the thumb attacks** and `--bass-notes` **what each note is**. The full walk puts a note on every felt beat — a line moving from the tonic toward the next chord rather than a grid — and with the tune ours the chord part gives up a string to make room for it:

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 \
    --bass-on every-beat --bass-notes walk
```

```text
Gmaj9    D4  5    3-x-4-4-3-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most this palette offers -
                                    sounding: F# 7, B 3, D 5) (bass: G2, anchor)
Gmaj9    D4  5    3-x-x-x-3-x       (melody repeated - single note) (bass: G2, held)
Gmaj9    D4  5    2-x-x-x-x-x       (the shape above is held) (bass: F#2, connect)
Gmaj9/F# D4  5    x-x-4-4-3-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most this palette offers -
                                    sounding: F# 7, B 3, D 5) (bass: F#2, held)
```

Expect **more steps than the melody had** — four here for three notes, because the bass grid is finer than the melody's. A step marked `bass_only=True` is the thumb alone: the previous shape is held, and nothing above the thumb is struck — not the chord, and not the melody. That is what makes a **tied** melody stay one note under a walking line: the tune of "But Not For Me" ties across half-beats, and with `--bass-on 1,2,1and,2and` those half-beats are thumb attacks under a shape nobody re-plucks. A note the tune genuinely **re-articulates** is a different step and says so (`melody repeated - single note`: soprano alone, inner voices held).

**The thumb rings until the next attack.** `(bass: G2, held)` is a note **sounding and not plucked**: it was struck on beat 1 and is still ringing under the melody at 1.5. The one-line tab draws a mute on that string — the tab answers "what is plucked" — while the staff leaves the cell empty and the MusicXML ties the pitch inside the chord, so all four renderers say the same thing about one note. The ring ends at the next attack, the bar line, a rest, or a shape the hand cannot hold it under.

Each bass note says its purpose in `step.bass_role`: `anchor` (the chord's root where the line marks the bar), `connect` (a passing note between chords), `approach` (a semitone from the next root), `pedal` (a root on a position that is not the bar's first), `enclosure`, `hold` (a repeat). The thumb is placed against the **shape the hand holds**, not the melody: adjacent bass strings are five semitones apart, so "prefer the lowest string" and "stay where the hand is" are in permanent opposition, and placement takes the fret nearest the upper voicing — within the hand's reach. When the ranking's first shape cannot reach the requested note at all, the **harmony moves** to one that can, so the note sounds instead of going missing.

A step whose bass note cannot be played keeps its upper voicing and says so rather than writing unplayable tab (`no playable bass note for bass ... - no free string below the melody, no octave of that pitch below the shape, the hand would need a fifth fret, or the reach is wider than five frets`). **The chord moves first**: a requested note the shape cannot reach is played by re-voicing the chord where the thumb *can* reach it, and the line says so (`placed to leave room for the requested bass note`). Dropping the note is the last resort, for the slots where no shape can carry it; counts over the committed heads are in [docs/open-issues.md](docs/open-issues.md) item 2.

## Who plays what: `--no-melody` and the two layer flags

Three separate questions, one flag each: **does the guitar sing the tune**, **when does the chord attack**, **when does the thumb attack**. What each of them states is a second flag beside it, and the parts selection is derived from the three rather than spelled.

| ask | the request |
|---|---|
| the tune, a chord under each note | *(nothing — the default)* |
| the tune alone | `--chord-on none` |
| the tune with a thumb on each bar's first beat | `--bass-on 1` |
| the tune with a walking line | `--bass-on every-beat --bass-notes walk` |
| the chord alone, for a horn on the tune | `--no-melody --chord-on every-beat` |
| a bass line alone | `--no-melody --chord-on none --bass-on every-beat` |

**The tune is the guitar's unless `--no-melody` is passed**, and that flag is a complete request on its own: the chord's default names the written onsets, this guitar has none, so the metre's own reading is used — every felt beat. The run header prints the resolved positions (`chord-on=1,2,3,4`, or `1,2` in 2/2), so the derivation is visible rather than assumed.

`--bass-notes` names what each thumb note is: `root` is the chord's root, `root-5th` alternates root and fifth, and `walk` is the full `root,5th,approach,nearest` chain — a note on every requested position, moving toward the next chord rather than repeating a grid. The rhythm is `--bass-on`'s, so `--bass-on every-beat --bass-notes root` is a pedal on every felt beat, which is what it says.

**A combination the left hand cannot accommodate at all is refused outright** (`ValueError`); a single note the thumb cannot reach is dropped and named on its own step (`bass_refused`), and the arrangement proceeds without it — a walking line with gaps is worse than none, but losing the bass costs less than losing the tune.

### Which degrees a non-singing part states: `ArrangeOptions(harmony=…)` (Python API)

`harmony` is read only when the guitar has no tune of its own, and it is a **library-only** value: there is no request flag, because it changes nothing on the route the guitar sings — a chord-melody's shell is a **grip** the selector picks, not a degree family.

| `ArrangeOptions(harmony=…)` | the shapes it admits | needs |
|---|---|---|
| `guide` (default) | the guide pair — 3rd and 7th, the notes that say major or minor | two notes |
| `shell_root` | both guide tones **and** a root or 5th as the lowest note | three notes |
| `full` | the whole chord | ordinary chord-melody route — see [the request](#the-request-and-the-six-axes-under-it) |

It is a **constraint on the palette, not a shape**: `guide` and `shell_root` often choose the same voicing, because a shape whose lowest note is already a root or a 5th satisfies both. What changes is which shapes are on the table — `get_comping_voicings("m7", "Cm7", notes=3, shell_root=True)[0]` is `x-x-x-12-11-11` where the plain palette's first is `x-x-x-3-4-3`.

`harmony="shell_root"` with `parts="bass,chord"` is the ensemble: horn on the tune, guitar stating the quality *and* the root underneath — `8-x-8-8-x-x`, the root under the b7 and b3. A degree order named for a part the selection leaves out is **refused outright** (`ValueError`), not quietly thinned: `ArrangeOptions(harmony="guide", parts="melody")` says *"harmony="guide" is a degree order for the chord part, and parts="melody" does not take it - add 'chord' to parts, or drop the harmony"*.

### The thumb alone

`--no-melody --chord-on none --bass-on every-beat` is a bass line and nothing else — the request a bassist makes, played on the guitar's low strings:

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 \
    --no-melody --chord-on none --bass-on every-beat
```

```text
Gmaj9    D4  5    3-x-x-x-x-x       (the thumb alone - the chord part is not stated here)
                                    (bass: G2, anchor)
Gmaj9    D4  5    x-x-x-x-x-x       (the guitar rests here -
                                    no part was asked to sound at this position)
Gmaj9    D4  5    3-x-x-x-x-x       (the thumb alone - the chord part is not stated here)
                                    (bass: G2, pedal)
Gmaj9/F# D4  5    x-x-x-x-x-x       (the guitar rests here - no part was asked to sound at this position)
```

One note per felt beat — **two attacks a bar in 2/2, four in 4/4, three in 3/4** — and the positions the rhythm does not name are rests, which is what keeps the part lined up against the tune. `pedal` is a root on a position that is not the bar's first, so the line is not pretending to be a walk.

Each step names what it is: `the thumb alone` where the chord part is off, `the guitar rests here` where nothing was asked for. `--bass-on 1` instead of `every-beat` gives one attack a bar, and the note **rings** under the rest of it.

### The chord alone: `--no-melody`

The guitar stops singing and states the chord instead, for a horn that has the tune. Its degrees are the **guide pair** by default — 3rd and 7th, the two notes that say major or minor — and `--chord-notes` says how many notes carry them:

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 \
    --no-melody --chord-notes 2
```

```text
Gmaj9    D4  5    x-x-x-x-7-7       (comping - B 3 & F# 7; the guitar does not play the tune)
Gmaj9    D4  5    x-x-x-x-x-x       (the guitar rests here -
                                    no part was asked to sound at this position)
Gmaj9    D4  5    x-x-x-x-7-7       (comping - B 3 & F# 7; the guitar does not play the tune)
Gmaj9/F# D4  5    x-x-x-x-x-x       (the guitar rests here - no part was asked to sound at this position)
```

Expect **the arity** per step — two here, three under `--chord-notes 3` and one under `1` — not a count of layers. A position the chord rhythm does not name is a **rest**, emitted rather than dropped so the part keeps its place against the tune; that is why a 2/2 bar shows two comped positions and two rests. `step.melody` still carries the horn's note and `step.melody_voiced` is False — the first is the written tune, the second is who sounds it.

**Shape chosen from the chord alone.** `get_comping_voicings` takes no melody argument; `D5` and `G3` under the same chord return *identical* candidate sets. A chord tone in the shell may land on the same pitch class as the melody — unremarkable, and the guide-tone ear needs it anyway. Every voiceable quality has a comping shape in some playable position, checked over `CHORD_TONES_FROM_ROOT`. A quality with no readable root gets nothing: a shell is a claim about *this* chord's 3rd and 7th, and guessing without the root is how wrong notes get in.

**A repeated melody holds the whole shape.** Normally a repeat is a soprano-only re-strike with the rest muted; there is no soprano to re-strike when the guitar is not singing, so the shape is held instead — the guitar does not play a moving line on exactly the beats the arrangement handed the tune away.

### The tune on its own

`--chord-on none` is the tune and nothing else; every slot melody alone:

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 --chord-on none
```

```text
Gmaj9    D4  5    x-x-x-7-x-x       (harmony under 5 - melody alone, the most this palette offers)
Gmaj9    D4  5    x-x-x-7-x-x       (harmony under 5 - melody alone, the most this palette offers)
Gmaj9/F# D4  5    x-x-x-7-x-x       (harmony under 5 - melody alone, the most this palette offers -
                                    the written bass F# is not sounded -
                                    the lowest voice (D4) is 4 semitones from it)
```

The chord name is still printed above each step as context; nothing under it is voiced. An `NC` bar under a comping selection is printed as an empty bar (`silence="nc_comping"`), not dropped: there is no chord, so no guide tones, and the guitar is genuinely silent while the horn is not.

## When the chord attacks: `--chord-on`

**Positions, in felt beats, bar-relative.** The chord's default is `melody` — one chord under each written melody note, held for that note. A list of positions **replaces** the default, so `--chord-on 1and` is only the stab and `--chord-on melody,1and` is the harmonisation plus the stab.

| token | meaning |
|---|---|
| `melody` | at every written melody onset; the chord default |
| `none` | the layer is absent |
| `every-beat` | the start of every felt beat: 2 per bar in 2/2, 4 in 4/4, 3 in 3/4, 4 in 12/8 |
| `1`, `2`, `3`, `4` | that felt beat |
| `1and` | halfway through felt beat 1 — "the and of 1" |
| `1e`, `1a` | a quarter / three-quarters through felt beat 1 |
| `last`, `lastand` | the last felt beat, and its offbeat |
| `melody,1and` | the melody-note harmonisation **plus** a stab |

**A list replaces the default token.** `none` cannot be combined with another token, and a position the metre does not have is **refused** (`3` in a 2/2 bar), not silently dropped. `and` is the midpoint of the felt beat, so it is a quarter-note offbeat in 2/2, an eighth-note offbeat in 4/4 and the midpoint of a dotted-quarter pulse in 6/8; `e` and `a` are the quarter and three-quarter points. `every-beat` and `last` resolve against the metre's **grouping**, not its denominator count.

**The midpoint is spelled `and`, not `&`** — a position is a command-line argument, and an unquoted `&` is the shell's background operator, so `--chord-on 1&` would send the arrangement to the background and leave the token unsaid. Every token the run header prints is safe to paste back, and `1&` is refused with the spelling it should be.

**Positions are bar-relative and metre-aware — one name works in any metre.** "The upbeat of the final beat" is 4.5 in 4/4, 2.5 in 2/2 and 3.5 in 3/4: the same musical idea, three beat numbers. Spelling a pattern as a literal beat would name, on a 2/2 head, a beat that does not exist.

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 --chord-on 1and
```

```text
Gmaj9    D4  5    x-x-x-7-x-x       (harmony under 5 - melody alone, the most this palette offers)
Gmaj9    D4  5    3-x-4-4-3-x       (harmony under 5 - 4 voices - sounding: G Root, F# 7, B 3, D 5 -
                                    the chord tone it leaves out is 9)
Gmaj9/F# D4  5    x-x-x-x-3-x       (harmony under 5 - melody alone, the most this palette offers -
                                    the written bass F# is not sounded -
                                    the lowest voice (D4) is 4 semitones from it)
```

One stab, on the and of 1; the melody notes elsewhere are the tune alone. **A stab lasts its felt beat and no further** — the beats it does not fill are written as a rest — and a position the metre does not have is refused rather than clamped.

**Every position you name is a new attack**, even where the chord is the same shape as the one before it. `--no-melody --chord-on 1,2` on a 2/2 head strikes the same chord twice a bar, and the staff, the HTML, the score and the GP5 file all draw both; a comp on `--chord-on every-beat` is four attacks a bar, not one long chord. Only a position the engine *invents* — a slot the tune merely sustains through — is a hold.

**What happens to a melody note with no chord on it depends who sings** — the one place the rhythm needs two answers:

- **the guitar singing** — the tune's note still sounds, alone. No note is dropped: chord-melody under `--chord-on 1and,2and,3and,4and` plays the melody throughout and places chords only on the ands. The lone note is placed by the same position-aware selector a chord is, from the positions its strings offer, so it lands where the hand already is rather than at the high E string's nearest fret.
- **the guitar comping** (`--no-melody`) — the guitar is **silent** on that beat: the melody belongs to the horn and there is nothing for the guitar to add. The step is still emitted, so the part keeps its position and lines up against the tune, and it draws as an empty column.

**The rhythm places chords, not the thumb.** The thumb line's own positions come from `--bass-on`, so the thumb sounds on beats where the guitar strikes no chord at all — the `bass_only` steps above are exactly that. The chord rhythm *does* change the shape a thumb note is placed against: a different chord above can move the note or refuse it.

The old `--grid` figures were **presets of positions, and only of positions**: `freddie` was `--chord-on every-beat`, `charleston` `1,2and`, `joe_pass` `1and,2and,3and,4and` and `final_and` `lastand`. They were removed because they were a second spelling of the same question — and a slightly different one, since a preset also decided which union its positions were merged into, so `grid="chord:freddie"` and `--chord-on every-beat` could differ in shape while agreeing on every position. The request is the only spelling now.

### What the chord does in a rest: `--chord-fills`

A **notated silence** in the melody line is the one span the chord rhythm says nothing about, and this is its policy. It is not a rhythm of its own and it never invents a melody.

| `--chord-fills` | in a melody rest |
|---|---|
| `none` *(default)* | the guitar rests with the tune |
| `hold` | one chord at the rest's onset, stating the harmony in force, held to the end of the rest |
| `comp` | a chord at the rest's onset and on each felt beat inside it |

The sharpest case is `--chord-on none --chord-fills hold`: the tune alone outside the rests, and a chord at each rest's onset inside them — the chord part exists *only* in the rests.

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 6-7 \
    --chord-on none --chord-fills hold
```

```text
Am7               x-10-10-9-x-x     (comping - C b3, E 5 & G b7; the tune is silent here)
D9                x-x-4-5-5-x       (comping - E 9, F# 3 & C b7; the tune is silent here)
```

That is bar 6 of the head, which has no melody at all and two harmony changes: two rests, and one chord held in each. The line says why the chord is there — the tune is silent here — because a chord with no melody above it is otherwise indistinguishable from a mistake.

A rest is **split** where the harmony changes and where a `--chord-on` target falls inside it: a target always attacks, and the fill continues after it. The fill stops at the rest's end, so it cannot ring into the returning tune. A rest with **no chord** (`NC`) gets nothing, and `--no-melody` refuses the flag outright — a guitar that is not playing the tune has no melody rests to fill.

`--chord-notes` caps a fill's arity like any other chord, and during a rest the melody string is free, so a fill can be fuller than a chord under a melody note. `--bass-on` is independent, and a coincident fill and thumb merge into one step, subject to the four-string capacity.

## Grips

`arrange_progression` builds **several voicings per step** — every grip carrying melody inside neck window — picks with one cost function: chord can stay where previous left hand.

| grip | notes | what it is |
|---|---|---|
| `drop2` | 4 | four-note drop-2 on four strings below soprano, or bass moved to lower string (skipping D, or A) |
| `closed` | 4 | **close position** — chord tones stacked tightest under melody, no voice dropped (e.g. `x-x-5-4-3-2`) |
| `drop3` | 4 | **drop-3** — third voice down an octave; every other voice still chord tone |
| `drop24` | 4 | **drop-2 & 4** — second *and* fourth voices an octave down |
| `drop2_6432` | 4 | **6-4-3-2** — low E, D, G and B, so bass can be root |
| `shell` | 3 | 3rd and 7th plus one more: 1-2-3, 2-3-4, 5-4-3, **6-4-3**, **5-3-2**, **1-3-4** |
| `duo` | 2 | chord's guide tone — 3rd, or 4th on sus — under any chord tone |
| `interval` | 2 | 3rd, 6th or 10th below melody — a *fill*, not a harmony |

Seven of them are `GRIP_PREFERENCE`: the order the families are tried in **and** the order an exact tie between equal-cost shapes breaks in — there is no separate grip term in the cost function and no caller order to give. A complete chord that reaches a step still outranks a partial one at equal cost, because note count is its own criterion; what `--chord-notes` does is decide whether the complete chord is on the table at all. `interval` is excluded — an interval is texture, not harmony — and `targets` offers it for fills only.

`closed` sits **second**, right after `drop2`: tightest shape there is, so where melody can fret it at all it beats other four-note families on a tie. Most melodies cannot — close-position chord under melody is seventh or more of pitch on four strings only 4–5 semitones apart in tuning — usually never generated rather than generated and rejected.

`drop3` and `drop24` derive from close-position stack under melody, keeping every *other* voice chord tone — measured over every quality and every melody, zero wrong notes where drop-2's quality-only fallback produces hundreds. [docs/engine.md](docs/engine.md) has derivation and cost tuple; [docs/history/generated-grips.md](docs/history/generated-grips.md) the rule deciding which chord tones a shape states.

Two arities are thin by design, and the run says so:

**Three notes** — `--chord-notes 2` states the guide pair under the tune:

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 --chord-notes 2
```

```text
Gmaj9    D4  5    x-x-4-4-3-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most this palette offers -
                                    sounding: F# 7, B 3, D 5)
Gmaj9    D4  5    x-x-x-x-3-x       (melody repeated - single note)
Gmaj9/F# D4  5    x-x-4-4-3-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most this palette offers -
                                    sounding: F# 7, B 3, D 5)
```

Open, unlabelled sound: 3rd and 7th make chord major or minor; no root lets player imply it.

**Two notes** — `--chord-notes 1` leaves the tune and its **guide tone**: the 3rd, or the 4th on a suspended chord (the 7th when the melody is already the 3rd):

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 --chord-notes 1
```

```text
Gmaj9    D4  5    x-x-x-4-3-x       (duo - melody + b3, partial -
                                    2 voices, the most this palette offers - sounding: B 3, D 5)
Gmaj9    D4  5    x-x-x-x-3-x       (melody repeated - single note)
Gmaj9/F# D4  5    x-x-x-4-3-x       (duo - melody + b3, partial -
                                    2 voices, the most this palette offers - sounding: B 3, D 5 -
                                    the written bass F# is not sounded -
                                    the lowest voice (B3) is 5 semitones from it)
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

All three sit in one position on bottom four strings. Restricting the melody to the high E and B strings — `top_strings=(5, 4)` — moves the floor up with it and every step up the neck:

```python
for step in engine.arrange_progression(low, top_strings=(5, 4)):
    print(step.chord, step.voicing.tab_string())
```

```text
Dm7 x-3-3-2-3-x
G7  3-x-3-4-3-x
Cmaj7 3-x-2-4-1-x
```

The `Cmaj7` is where the restriction shows: four notes on the low E, D, G and B strings with `C4` on the B, where the unrestricted run reached for the three-note 6-4-3 shell — a G-string soprano has no four-note block to go to. `top_strings=(5,)` restricts to the traditional high-E block.

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
Dm7      A4  5    10-x-10-10-10-x   (harmony under 5 - transposed down an octave from A5 - 4 voices
                                    - sounding: D Root, C b7, F b3, A 5)
```

Two deliberate limits:

- **Only repositions a voicing that exists.** Melody unreachable at written pitch (`B5` fret 19, `C6` fret 20 — past end of board) not silently respelled. Position emitted as a rest, clause names problem, `silence="out_of_reach"` on step.
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
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 4-6
```

```text
Eb6      C5  6    x-x-8-8-8-8       (harmony under 6 - 4 voices - sounding: Bb 5, Eb Root, G 3, C 6)
Am7      D4  11   x-3-x-7-x-x       (non-chord tone -
                                    the extension strategy found no voicing; the written chord
                                    stands -
                                    2 voices: the 4-voice voicing x-3-3-2-3-x sounds a note outside
                                    the chord - sounding: C b3, D 11)
Am7      D4  11   x-x-x-7-x-x       (melody repeated - single note - non-chord tone -
                                    the extension strategy found no voicing; the written chord
                                    stands)
Am7      G4  b7   8-x-7-9-8-x       (harmony under b7 - 4 voices -
                                    sounding: C b3, A Root, E 5, G b7)
```

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 4-6 --fallback diminished
```

```text
  note: diminished fallback replaced the written chord on 2 step(s)

Eb6      C5  6    x-x-8-8-8-8       (harmony under 6 - 4 voices - sounding: Bb 5, Eb Root, G 3, C 6)
F#dim7   D4  b13  5-x-4-5-3-x       (non-chord tone -
                                    the extension strategy found no voicing; the written chord
                                    stands - 4 voices - sounding: A b3, F# Root, C b5, D b13 -
                                    the chord tone it leaves out is 13)
F#dim7   D4  b13  x-x-x-x-3-x       (melody repeated - single note - non-chord tone -
                                    the extension strategy found no voicing; the written chord
                                    stands)
Am7      G4  b7   8-x-7-9-8-x       (harmony under b7 - 4 voices -
                                    sounding: C b3, A Root, E 5, G b7)
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

Unsupported qualities return no voicings; `arrange_progression` emits a rest step carrying `silence="no_shape"` — no raise, and no dropped position.

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

Engine lives in `arranger` package, fourteen modules in strict dependency order that `tests/meta_package_dag.py` asserts from AST. `AGENTS.md` has module map and conventions; [docs/](docs/) the reasoning behind engine and renderers.

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
