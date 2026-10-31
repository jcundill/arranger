# jazz-arranger

Generate playable **jazz guitar chord-melody arrangements** from a chord progression.

Takes `(melody note, chord name)` pairs, builds voicings in several grip families, pins the melody to the soprano string, picks with one position-aware cost function. Also reads a written head from MusicXML and arranges that.

- **Seven grip families**, drop-2 first: `drop2`, `closed`, `drop3`, `drop24`, `drop2_6432`, `shell` and `duo` — four-note down to two-note guide-tone pairs. Every one sounds the chord's **3rd and 7th** (major vs minor); a `duo` sounds one of them under any chord tone — two notes is the floor ([grips](#grips)).
- **Melody pinned to soprano**, on high E, B or G string — low melody still harmonised in position.
- **Playable or absent.** Frets 0–18, span ≤5 (4 for duos), real string set, ≤4 fingers, no fifth fret from a held shape. Neck window is *preference, not filter* — losing a chord of the tune beats a fret out of position.
- **Non-chord melody notes**: extension, Barry Harris 6/dim7 substitution, or chord held under a passing tone ([non-chord melody notes](#non-chord-melody-notes)).
- **Four axes, two rhythms**: how thick the chord part is (`texture`), who plays the bottom (`bass`), which parts the guitar takes (`parts`), and how a compound metre is felt (`grouping`) — plus *when* the chord attacks and *when* the thumb attacks (`--chord-on` / `--bass-on`, each a `Rhythm`). None has a keyword of its own: they are derived from the [six questions](#the-request-and-the-axes-under-it) the request asks, so `--chord-notes targets` is `Request(chord_notes="targets")` and nothing more.
- **Heads from real sources** — MusicXML score, read as harmony *timeline*.
- **Dependency-light**: Python 3.11+ and [musthe](https://pypi.org/project/musthe/) only. MusicXML head *reading* needs no extra; MusicXML export and Guitar Pro export each behind own optional extra.

> The **distribution** is `jazz-arranger` (PyPI name `arranger` taken by unrelated project). **Import** name is `arranger`.

Why lives in [`docs/`](docs/): [engine.md](docs/engine.md) (the selector, the axes, the cost tuple), [renderers.md](docs/renderers.md) (tab, MusicXML, GP5), and [open-issues.md](docs/open-issues.md) (the issue ledger — **one is open**, item 7; the six it filed, each with its measurement, are the record in [docs/history/open-issues.md](docs/history/open-issues.md)). The plan documents that built this — parts, comping styles, generated grips, fingering, `voices=` — are in [`docs/history/`](docs/history/).

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

## Using the library

### Quick start

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

### Steps and voicings

Each step is an `ArrangementStep` (`chord`, `melody`, `voicing`, plus `non_chord_tone`, `strategy`, `harmonized_as`); `voicing` is a `Voicing` with `frets` (six entries, `-1` = muted), `top_fret`, `avg_fret` and helpers `tab_string()`, `fret_span()`, `midi_notes()`, `pitch_classes()`, `soprano_string()`.

Tab runs low E → high E, `x` = muted — `x-x-12-13-13-13` is a voicing on D-G-B-E with melody on high E.

### Grips

`arrange_progression` builds several voicings per step — every grip carrying melody inside neck window — picks with one cost function.

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

Seven of them are `grip_tables.GRIP_PREFERENCE`: the order the families are tried in **and** the order an exact tie between equal-cost shapes breaks in — there is no separate grip term in the cost function and no caller order to give. A complete chord that reaches a step still outranks a partial one at equal cost, because note count is its own criterion; what `--chord-notes` does is decide whether the complete chord is on the table at all. `interval` is excluded — an interval is texture, not harmony — and `targets` offers it for fills only.

`closed` sits **second**, right after `drop2`: tightest shape there is, so where melody can fret it at all it beats other four-note families on a tie. Most melodies cannot — close-position chord under melody is seventh or more of pitch on four strings only 4–5 semitones apart in tuning — usually never generated rather than generated and rejected.

`drop3` and `drop24` derive from close-position stack under melody, keeping every *other* voice chord tone — measured over every quality and every melody, zero wrong notes - and drop-2's old quality-only fallback, which could sound a note the chord does not contain, is gone. [docs/engine.md](docs/engine.md) has derivation and cost tuple; [docs/history/generated-grips.md](docs/history/generated-grips.md) the rule deciding which chord tones a shape states.

### Low-register melodies

Melodies below high E open pitch (`E4`) cannot be voiced on that block. By default melody may also pin to B string (voicing on A-D-G-B) and **G string** (bottom four strings) — floor drops to `G3`:

```python
low = [("D4", "Dm7"), ("D4", "G7"), ("C4", "Cmaj7")]
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

### High melodies, and the neck window

Every voicing confined frets 0–18, span ≤5 (4 for duo and interval), on real string set. `tuning.NECK_FRET_MIN`/`tuning.NECK_FRET_MAX` — frets 2–13 — range selector *aims* for, not hard filter: step with no voicing inside window still played, just outside it, because losing chord of tune beats fret out of position. Run header echoes window whether or not met.

Melody whose only position sits above `tuning.HIGH_FRET_LIMIT` (13) voiced an octave down:

```python
high = [("A5", "Dm7")]
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
                                    sounding: D Root, C b7, F b3, A 5)
```

### Non-chord melody notes

A chord tone above/under the melody is extended, substituted, or held. See [docs/engine.md](docs/engine.md) for the extension strategy (`NON_CHORD_TONE_EXTENSIONS`), the optional diminished retry, and what happens when nothing maps — the note sounds alone under its chord.

## Using the CLI

### Quick start

```bash
python -m arranger head tests/data/synthetic_cut_time.mxl --bars 1-3
```

Both bare `.musicxml` and zipped `.mxl` are accepted.

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

### Repeats, endings and jumps

A backward repeat plays its section again, 1st/2nd ending taken in turn — `synthetic_repeat_slash`, written 8 bars, arranged as the **12** a player hears (`1-4, 5-6, 1-4, 7-8`). A D.C. / D.S. returns to the start or the Segno, a `To Coda` diverts on the way back, and a `Fine` ends the return. The form lands in output: `--musicxml`, `--gp5`, `--html` and `--tab staff` write the **written** bars with `|:` / `:|` signs, `1.` / `2.` brackets and the Segno / Coda / Fine / D.C. / D.S. directions. (Plain `--tab line` still shows every played bar.)

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --tab staff --note-names
python -m arranger head tests/data/synthetic_triplets.mxl --bars 1-3 --html head.html
```

### Reading a head from MusicXML

`arranger head` does the same job from **written melody + chord symbols** — a lead sheet, a melody-only score, anything MusicXML. Repeats, endings and jumps honoured. (Section above.)

The head layer exposes the same selection primitives:

```python
from headxml import load_musicxml, head_skeleton

head = load_musicxml("tests/data/synthetic_cut_time.mxl")   # melody, timing, chords
print(head.title, head.beats_per_bar, len(head))
for triple, bar, beat, duration in head_skeleton(head):
    print(bar, beat, triple)
```

It is the same arrangement code: head from a score voiced by `arranger.slots.arrange_slots` — the engine's own slot layer. Non-chord-tone strategies, opt-in diminished retry, repeated-melody hold and walking bass are engine's, not importer's; only *selection* is importer's business.

### Flags

| flag | default | what it does |
|---|---|---|
| `--part` | the melody part | a `<score-part>` id, when score has several |
| `--bars` | whole head | half-open `LO-HI`; **bounds may be negative** for pickups |
| `--non-chord-tone` | `extension` | how to harmonise melody note outside chord |
| `--fallback` | off | `diminished` — see [non-chord melody notes](#non-chord-melody-notes) |
| `--no-melody` | off | the guitar does not sing: the tune belongs to somebody else, and the chord keeps the tune's own written onsets |
| `--chord-on` | `melody` | when the chord attacks: the written onsets, `sustain` only at onsets whose note runs at least one felt beat, `none`, positions such as `1and`, `every-beat`, or a `:`-joined cycle of those bars (`1,3:none`) |
| `--chord-notes` | `full` | how many chord tones it states: `full`, `targets`, `3`, `2`, `1` |
| `--chord-fills` | `none` | what it states in a notated melody rest: `hold` one chord, or `comp` a felt beat at a time |
| `--bass-on` | `none` | when the thumb attacks: positions, `every-beat`, or a `:`-joined cycle of them (`1,3:none`); `melody` is refused |
| `--bass-notes` | `root` | what each thumb note is: the root, root-then-5th, a walk, or the note rules themselves (`root,approach`) |
| `--fret-min` / `--fret-max` | `2` / `13` | neck window to aim for |
| `--tab` | `line` | `staff` lays head on one six-line staff, spaced on real rhythm |
| `--note-names` / `--mutes` | off | with `--tab staff`: name each step's melody note / spell muted strings as `x` |
| `--bars-per-line` | `4` | with `--tab staff`: bars per staff line |
| `--html` / `--musicxml` / `--gp5` | off | also write head to file — see [rendering](#rendering) |

### The request is six questions

**The six questions have a second spelling.** `Request` carries them as one value (`from arranger import Request`), so the same call asks for a walking line under the tune — `engine.arrange_progression(progression, request=Request(bass_on="every-beat", bass_notes="walk"))`. Both spellings and what each question means are in [the request and the axes under it](#the-request-and-the-axes-under-it); a band setting is a combination of them rather than a mode, and **no axis has a keyword of its own**. The metre is not an axis but an input fact like `timings=`: a score states it, and a progression built without a file declares it as one `TimeSignature`.

**Every written note sounds.** No reduction: `arranger head` plays tune as written, one step per note, each on written beat. Where *chords* fall is a separate question — `--chord-on` — and a note is never quantised onto a position and dropped for sharing a slot.

**Grip order is the engine's.** No flag names a family: the order families are tried in is `grip_tables.GRIP_PREFERENCE`, and an exact tie between equal-cost shapes breaks in that same order — see [grips](#grips). `--chord-notes` is what narrows the palette, by saying how many chord tones a step may state.

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

### When the chord attacks: `--chord-on`

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
```

### A comping pattern for a progression written in code

`Request(melody=False, chord_on=...)` is the whole of it — the same request `--no-melody --chord-on` spells:

```python
from arranger import VoiceLeadingEngine, Request

engine = VoiceLeadingEngine()

# (melody note, chord name). `None` is a position the tune does not state - which is
# every position when the guitar is comping rather than singing.
progression = [(None, "Dm7"), (None, "G7"), (None, "Cmaj7"), (None, "A7")]

steps = engine.arrange_progression(
    progression, request=Request(melody=False, chord_on="1,3")
)
```

```text
Dm7               x-8-7-5-x-x       (comping - the tune is silent here)
G7                x-x-x-x-x-x       (the guitar rests here - no part was asked)
Cmaj7             x-x-9-5-5-x       (comping - the tune is silent here)
A7                x-x-x-x-x-x       (the guitar rests here - no part was asked)
```

### `--no-melody` — the guitar stops singing

The guitar stops singing and states the chord instead, for a horn that has the tune. Its degrees are the **guide pair** by default — 3rd and 7th, the two notes that say major or minor — and `--chord-notes` says how many notes carry them:

```bash
python -m arranger head tests/data/synthetic_repeat_slash.musicxml --bars 1-2 \
    --no-melody --chord-notes 2
```

```text
Gmaj9    D4  5    x-9-x-4-x-x       (comping - B 3 & F# 7; the guitar does not play the tune -
                                    top B3 - the opening, in the band's middle)
Gmaj9    D4  5    x-x-x-4-7-x       (comping - B 3 & F# 7; the guitar does not play the tune -
                                    top F#4 - walks up)
Gmaj9/F# D4  5    x-9-x-4-x-x       (comping - B 3 & F# 7; the guitar does not play the tune -
                                    top B3 - walks down)
```

**The high E is not on the comping palette** — the same two guide tones, on the G and B strings rather than the B and high E. That string is where the tune itself is pinned first, and a comping part has no tune to put there: a chord whose top voice sits on it is heard as a melody, and heard *above* the horn playing the real one. Dropping it is a palette narrow rather than a cost criterion, so the chord is never lost — it moves.

**The top voice walks.** Two voices is a thin shape to move, but the line is there: `B3` opens where the band's middle is, `F#4` is the nearest tone above it, and the slash chord comes back to `B3` because the chord changed and a new chord starts upward again — the roles are printed so the movement is not indistinguishable from the ranking being inconsistent.

Expect **the arity** per step — two here, three under `--chord-notes 3` and one under `1` — not a count of layers. The comp falls on the **tune's own onsets**: this bar of the head states three notes (beat 1, the and of 1 and the and of 2), so there are three attacks and no rests. Ask for a rhythm of its own and the positions it does not name become **rests**, emitted rather than dropped so the part keeps its place against the tune — `--chord-on 1,2` on the same bar comps beats 1 and 2 and rests the two offbeats the tune states between them. `step.melody` still carries the horn's note and `step.melody_voiced` is False — the first is the written tune, the second is who sounds it.

**Shape chosen from the chord alone.** `get_comping_voicings` takes no melody argument; `D5` and `G3` under the same chord return *identical* candidate sets. A chord tone in the shell may land on the same pitch class as the melody — unremarkable, and the guide-tone ear needs it anyway. Every voiceable quality has a comping shape in some playable position, checked over `CHORD_TONES_FROM_ROOT`. A symbol with no readable root is refused: a shell is a claim about *this* chord's 3rd and 7th, and guessing without the root is how wrong notes get in.

**A repeated melody holds the whole shape.** Normally a repeat is a soprano-only re-strike with the rest muted; there is no soprano to re-strike when the guitar is not singing, so the shape is held instead — the guitar does not play a moving line on exactly the beats the arrangement handed the tune away.

### Thumb line under the melody

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
html
**The thumb rings until the next attack.** `(bass: G2, held)` is a note **sounding and not plucked**: it was struck on beat 1 and is still ringing under the melody at 1.5. The one-line tab draws a mute on that string — the tab answers "what is plucked" — while the staff leaves the cell empty and the MusicXML ties the pitch inside the chord, so all four renderers say the same thing about one note. The ring ends at the next attack, the bar line, a rest, or a shape the hand cannot hold — it is plucked again wherever it changes.

One note per felt beat — **two attacks a bar in 2/2, four in 4/4, three in 3/4** — and the positions the rhythm does not name are rests, which is what keeps the part lined up against the tune. `pedal` is a root on a position that is not the bar's first, so the line is not pretending to be a walk.

Each step names what it is: `the thumb alone` where the chord part is off, `the guitar rests here` where nothing was asked for. `--bass-on 1` instead of `every-beat` gives one attack a bar, and the note **rings** under the rest of it.

```text
Gmaj9    D4  5    3-x-x-x-x-x       (the thumb alone - the chord part is not stated here)
                                    (bass: G2, anchor)
Gmaj9    D4  5    x-x-x-x-x-x       (the guitar rests here -
                                    no part was asked to sound at this position)
Gmaj9    D4  5    3-x-x-x-x-x       (the thumb alone - the chord part is not stated here)
                                    (bass: G2, pedal)
Gmaj9/F# D4  5    x-x-x-x-x-x       (the guitar rests here - no part was asked to sound at this position)
```

### Fills: `--chord-fills`

In a notated melody rest, `--chord-fills hold` states the written chord once at the rest's onset; `--chord-fills comp` states it on each felt beat through the rest. A rest with no chord (`NC`) gets nothing, and `--no-melody` refuses the flag outright — a guitar that is not playing the tune has no melody rests to fill.

`--chord-notes` caps a fill's arity like any other chord, and during a rest the melody string is free, so a fill can be fuller than a chord under a melody note. `--bass-on` is independent, and a coincident fill and thumb merge into one step, subject to the four-string capacity.

### The target / fill slot plan

`arrange_progression` builds target/fill slots from `timings`:

```python
from arranger import VoiceLeadingEngine, Request

engine = VoiceLeadingEngine()

progression = [
    ("C5", "Fmaj7"),   # beat 1 - the target
    ("E5", "Fmaj7"),   # fill
    ("A4", "Fmaj7"),   # fill
    ("F4", "Fmaj7"),   # beat 3 - the target
]
timings = [(0, 1.0, None), (0, 1.5, None), (0, 2.0, None), (0, 3.0, None)]

steps = engine.arrange_progression(
    progression, timings=timings, request=Request(chord_notes="targets")
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

The same request from the command line — `--chord-notes targets` **is** `Request(chord_notes="targets")`, and the run header prints the spelling back:

```bash
python -m arranger head tests/data/synthetic_common_8.musicxml --bars 1-2 --chord-notes targets
```

```text
Cmaj7    E4  3    7-x-5-5-5-x       (harmony under 3 - 4 voices - sounding: B 7, G 5, C Root, E 3)
Cmaj7    G4  5    x-x-9-9-8-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most a fill's palette offers -
                                    sounding: B 7, E 3, G 5)
```

Expect a lighter arrangement stating the harmony on the beats and ringing between. Each step carries `role` — `target` or `fill` — and `metric_weight` (2 on beat 1, 1 on beat 3, 0 elsewhere, and −1 for a position you state as unplaced). A progression given no `timings` is laid out on the metre's own beats, one entry per beat of the bar, so a hand-built progression is arranged as the bars it names.

**A fill never costs the tune a chord.** A fill slot with nothing thin to play is re-prepared as a principal note, not skipped — the texture is lighter, never missing. Measured effect in [docs/engine.md](docs/engine.md).

## Rendering

`arrange_progression` returns data; every tab renderer is a **pure function returning a string, printing nothing** — you decide how it displays.

Whole progression: `format_progression`:

```python
from arranger import VoiceLeadingEngine, format_progression

engine = VoiceLeadingEngine()
steps = engine.arrange_progression(
    [("D5", "Dm7"), ("B4", "G7"), ("C5", "Cmaj7")]
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

Compact analysis form; only shape `format_progression` has — four columns per step, the explanation trailing them and wrapped onto the lines below when it is too long for one.

`tabstaff` lays the whole progression on one staff in reading order (`format_tab_staff`, `format_tab_html`, `write_tab_html`). `tabxml` writes MusicXML, `tabgp` writes Guitar Pro 5 — each behind its optional extra.

## Shared reference

### The request and the axes under it

| the question | the flag | `Request(...)` | the axis it resolves to |
|---|---|---|---|
| who plays the tune? | `--no-melody` | `melody=False` | `parts` — the melody part is dropped from the selection |
| when does the chord attack? | `--chord-on POSITIONS` | `chord_on="1and"` | the chord layer's `Rhythm` — where a chord falls: `melody` at every written onset, `sustain` only at onsets whose note runs at least one felt beat, positions such as `1and`, `every-beat`, `none`, or a `:`-joined cycle of them |
| what does the chord state? | `--chord-notes full\|targets\|3\|2\|1` | `chord_notes="2"` | the texture axis — `uniform`, `targets`, `chord3`, `chord2`, `chord1` |
| what does it do in a melody rest? | `--chord-fills none\|hold\|comp` | `chord_fills="hold"` | chord slots in the tune's rests, plus `parts` including the chord |
| when does the thumb attack? | `--bass-on POSITIONS` | `bass_on="every-beat"` | the bass layer's rhythm (the same grammar, without `melody`), and `bass` when it is not `none` |
| what does each thumb note state? | `--bass-notes root\|root-5th\|walk\|rules` | `bass_notes="walk"` | the bass axis — the three names, or the rules themselves as a list (`root,approach`), which is what the names are sugar over |

The values are the flags' own strings, so a request read off a run header is one a caller can paste into Python. The axes those questions resolve to are the engine's implementation and are **derived from the request, never spelled**: `options=ArrangeOptions(...)` carries the knobs that are not a question about the music (`top_strings`, `fret_min`, `fret_max`, the non-chord-tone strategy), and the request and the metre are **input facts** beside it — `request=` and `time_signature=` say what is being arranged rather than how to play it, so one call may name both.

`cli._REQUEST_DESTS` is the one list holding the two spellings together, and `tests/test_request.py` asserts it.

### Development

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
- Melodies sit from `G3` up — A and low E are inner voices only — and a melody whose only position sits above fret 13 is voiced an octave down, never refused.
- Fixed max fret span 5 (4 for duo and interval), fret range 0–18, no step may need fifth fret from hand already holding shape. `closed` offered, second in preference order, usually unreachable: most melodies cannot fret it inside that budget, wins only where it does.
- Non-chord melody notes handled only for `NON_CHORD_TONE_EXTENSIONS` mappings (9ths, 6/9s, 11ths, #11s, b13s, 13ths, half-diminished 9th, 9th over plain triad) plus dim7; anything else has nothing to state, so the note sounds alone under its chord and the step says `(melody alone - no voicing for this chord)`.
- Chord-tone drop-2 with no inversion for — 9th in melody of 13 chord — is not offered at all: the quality-only fallback that used to answer it could sound a note the chord does not contain, and it is gone with the quality field. Another family that builds from the chord's own tones answers it - shells, duos and the 6-4-3 grip are unaffected - or the step keeps the tune and loses the chord.
- `sustain` strategy structural — API takes only `(note, name)` pairs, rhythm and duration cannot spot brief passing tone.
- Neck window preference not filter, so `--fret-min`/`--fret-max` may not be honoured where nothing playable inside. Header echoes window either way.
- Slash bass honoured as preference not hard constraint: selector narrows candidates by it, engine's own rule within that set — voicing that cannot honour bass still playable.
- Beat melody skips *inside* a bar it occupies has no chord of its own — chord in force stored per melody note. Bar-level half built: a comping selection states the chord of a bar the melody never enters, and `--chord-on` names the positions a singing selection adds.
- No release published to PyPI.

## License

MIT. [LICENSE](LICENSE) full text.

Optional `gp` extra pulls in [PyGuitarPro](https://pypi.org/project/pyguitarpro/), LGPL-3.0. Deliberately kept out of runtime dependencies and behind lazy import, so project is not a combined work of PyGuitarPro and stays permissively licensed. `tabgp` writes no PyGuitarPro code into this repository.
