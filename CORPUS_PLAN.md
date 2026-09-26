# Corpus integration plan — Weimar Jazz Database

Status: **planned, not implemented.** This document is the spec to build against
and revise. Decisions below were made from measurements against the real
database, not guesses; each records the evidence it rests on.

- Target transcription: **John Coltrane, "Blue Train" (`melid` 218)**
- Scope: chorus 1 (bars 1–12) plus the `NC` intro at bar 0
- Library version at time of writing: `0.3.0` (this work would become `0.4.0`)

---

## 1. The database

`wjazzd.db` (42 MB, from jazzomat.hfm-weimar.de), **not committed** — ignored via
`.gitignore` and located at runtime.

### 1.1 The real schema differs from the commonly published description

There is **no** `melopy_notes` or `composition_annotations` table, and notes
carry **no chord column**. The actual tables:

| table | rows | role |
|---|---|---|
| `solo_info` | 456 | `melid, performer, title, key, signature, avgtempo, style, chord_changes, chorus_count` |
| `beats` | 132,329 | one row per beat: `melid, onset, bar, beat, chord, form, chorus_id, signature` — **`chord` is non-empty only on the beat a chord *starts*** (101,781 empty rows) |
| `melody` | 200,809 | `melid, onset, pitch, duration, bar, beat, tatum, subtatum, division` |
| `sections` | 58,560 | `PHRASE` / `CHORUS` / `PART` spans by bar |
| `melody_type` | 456 | `SOLO` or `THEME` |
| `composition_info`, `record_info`, `track_info`, `transcription_info`, `esac_info`, `popsong_info`, `db_info` | | metadata |

### 1.2 The chord binding must be reconstructed

Because notes have no chord, each note's active chord is a **forward fill**: the
last `beats` row for the same `melid` with a non-empty `chord` and
`(bar, beat) <= (note.bar, note.beat)`.

Verified ground truth:

| melid | bar | beat | expected chord |
|---|---|---|---|
| 1 | 0 | 1 | `Bb6` |
| 1 | 3 | 3 | `G-7` |
| 1 | 4 | 3 | `F7` |
| 218 | 0 | 1 | `NC` |
| 218 | 1 | 1 | `Eb7` |
| 218 | 8 | 1 | `C7` |

### 1.3 Register

Melody range is MIDI 36–97 overall; **199,910 of 200,809 notes (99.6%)** fall
inside the library's `B3`–`Bb5` window (MIDI 59–94). Out-of-range notes are
already skipped by `arrange_progression`, so the loss is negligible.

---

## 2. Chord notation

The database uses **Weimar notation**, which `ChordParser` does not understand.
There are **419 distinct chord symbols** and **47 distinct suffixes** across the
corpus.

### 2.1 The suffix table (derived from data, not guessed)

`WEIMAR_QUALITY_ALIASES` maps each suffix to a library quality. Unmapped
suffixes return `None` and are **counted and reported — never guessed**, so a bad
translation can never silently produce a wrong chord.

| Weimar | library | | Weimar | library |
|---|---|---|---|---|
| `""` | `maj` | | `7911` | `7sus4` |
| `-` | `m` | | `7911#` | `7#11` |
| `-6` | `m6` | | `7913` | `13` |
| `-7` | `m7` | | `7913b` | `7b13` |
| `-79` | `m9` | | `79b` | `7b9` |
| `-j7` | `mMaj7` | | `79#` | `7#11` |
| `6` | `6` | | `79b13` | `7b13` |
| `7` | `7` | | `79#13` | `7#13` |
| `9` | `9` | | `7alt` | `7alt` |
| `13` | `13` | | `+` | `aug` |
| `j7` | `maj7` | | `+7` | `7#5` |
| `j9` | `maj9` | | `+j7` | `maj7#11` |
| `69` | `6/9` | | `o` | `dim` |
| `-69` | `m6` | | `o7` | `dim7` |
| `sus` | `sus4` | | `m7b5` | `m7b5` |
| `sus7` | `7sus4` | | `NC` | *(no chord)* |

Compound suffixes are resolved before lookup: `+79#` → `7#5`, `-7911` → `m9`,
`j7911#` → `maj7#11`, `-j7911#` → `m9b5`, `j79#` → `maj7#11`, and so on.

### 2.2 Slash chords — rules B and C

**95 distinct slash chords across 62 of 456 transcriptions. Blue Train has
zero**, so this does not block the primary target, but it must be handled for the
loader to be correct.

**Problem 1 — the parser breaks.** `parse_chord_name` glues the bass onto the
quality, so every slash chord silently falls through to the quality-only
fallback:

```
'A-/G'   -> root='A'  quality='-/G'   in CHORD_TONES_FROM_ROOT=False  tones=()
'C7/E'   -> root='C'  quality='7/E'   in CHORD_TONES_FROM_ROOT=False  tones=()
'F-7/Ab' -> root='F'  quality='-7/Ab' in CHORD_TONES_FROM_ROOT=False  tones=()
```

The loader must strip the bass before handing anything to the engine.

**Problem 2 — the engine has no concept of a bass note.** Voicing inversion is
chosen purely from the melody's degree above the root, via
`DEGREE_OFFSETS_FROM_ROOT`. For a dominant 7th all four inversions exist and the
lowest voice is whatever the template yields. **The slash bass is structurally
out of scope**, so any handling is a policy decision, not a bug fix.

Of the 95 slash chords, **51 have a plain chord-tone bass** and 41 do not:

| degree | example chords | reading |
|---|---|---|
| 10 (7th) | `A-/G`, `C-/Bb`, `D/C` | the slash *implies* a 7th on a triad |
| 5 (11th) | `C/F`, `A-7/D`, `Eb-/Ab` | pedal point / sus colour |
| 3 (3rd) | `A/C`, `B/C`, `E/G` | first-inversion triad |
| 2 (9th) | `E7/F#`, `F7/G`, `A/B` | 9th in the bass |
| 6 (♭13) | `Ab7/D`, `F7/B` | ♭13 in the bass |

Three further chords have qualities outside the library: `Ab+j7/C`,
`Aj7911#/Ab`, `Dbj7911#/C`.

**Rule B — quality promotion.** If the quality is a triad (`maj` or `m`) and the
bass is degree 10, the source is implying the 7th:

```
A-/G -> Am7/G   C-/Bb -> Cm7/Bb   D/C -> Dm7/C   G-/F -> Gm7/F
```

This recovers the largest group of "impossible" basses with a principled rule.
Remaining non-chord-tone basses (pedal 11ths, 9ths, ♭13s) are ignored by B and
honoured by C instead.

**Rule C — bass preference.** Among the engine's candidate voicings, prefer the
one whose lowest pitch is closest to the slash bass:

```python
bass_pc = Note(bass + "3").midi_note() % 12
cost = lambda v: min(abs(p % 12 - bass_pc) for p in [v.midi_notes()[0] % 12])
```

This is expressible with the **existing** candidate list — no engine change. It
is not a no-op: across 460 slash-chord × melody combinations sampled from the
corpus, **288 (63%)** have candidates with differing lowest pitches, and in
**288 (63%)** the preference changes which voicing is chosen.

Example — `E5` over `Eb7` with a `D` bass, 8 candidates:

```
x-x-11-11-11-12   lowest=61 (pc 1)  cost=1
x-x-12-13-12-12   lowest=62 (pc 2)  cost=0   <- chosen by the bass rule
x-x-10-12-11-12   lowest=60 (pc 0)  cost=2
...
```

**Composition with voice leading (important).** Rule C and the engine's existing
voice-leading minimisation both select among the same candidates, so they must be
**combined, not sequenced** — otherwise one would always override the other.
Implement as a composite sort key: restrict to the bass-matching candidates, then
let the engine's normal rule decide within that set. When the bass is
satisfiable it is honoured; when it is not, behaviour is exactly as today. Both B
and C live entirely in the loader, so the engine stays frozen and the 394
transcriptions without slash chords behave as if the symbols were simply stripped.

---

## 3. The reduction problem

**A drop-2 voicing is a per-beat object, but Coltrane plays ~10 notes per bar.**
"Blue Train" chorus 1 has 80 notes across 12 bars, with up to 4 notes in a single
beat slot. Voicing all 80 is musically meaningless, so the line must be reduced
to a playable skeleton.

### 3.1 Strategies and measured density (chorus 1, transposed +12)

| strategy | steps | per bar | voiced | non-chord tones | warnings |
|---|---|---|---|---|---|
| per chord change | 12 | 1.0 | 10 | 6 | 6 |
| per beat | 36 | 3.0 | 36 (100%) | 20 | 16 |
| **per eighth** | **57** | **4.8** | **56 (98%)** | **29** | 12 |
| per sixteenth | 80 | 6.7 | 77 (96%) | 37 | 16 |
| every note | 80 | 6.7 | 77 (96%) | 37 | 16 |

**Decision: `eighths` is the default.** It is the density a chord-melody player
actually uses, 98% of steps voice successfully, and it preserves the line's
non-chord-tone character. `chords` (one voicing per chord change, i.e. ~1/bar)
is a *lead-sheet* rendering, not a chord-melody arrangement.

All five are exposed via `--skeleton`. For Blue Train chorus 1 the note count and
the 16th grid both yield 80 — Coltrane is playing near-continuous 8ths/16ths
there — but they diverge for sparser choruses, so the grid is computed properly
from the `tatum`/`division` columns rather than assumed.

**Position within a slot:** take the **first** note. On a 16th grid this is
almost always the only note anyway. (`--pick longest` is available for the beat
grid, where it favours the sustained note.)

### 3.2 Non-chord tones are the norm, not the exception

**50% of the notes in this solo are not chord tones** (494 of 983; chorus 1: 40
of 80), with the classic bebop distribution over the root:

| degree | 2 (9th) | 5 (11th) | 9 (13th) | 3 (♭9) | 11 (maj7) | 1 | 6 (♭13) | 8 |
|---|---|---|---|---|---|---|---|---|
| count | 124 | 88 | 70 | 46 | 44 | 43 | 42 | 36 |

**Decision: `extension` is the default strategy.** The alternatives are worse
here: `diminished` abandons the blues harmony (5 substitutions over 9 chord
spans), `sustain` produces shapes that are not literally the written chord, and
`legacy` can voice a note that is not in the chord at all. The other strategies
stay available per-invocation.

---

## 4. `NC` bars — melody, no harmony

**401 `NC` beat rows across 267 of 456 transcriptions** — a common case. In Blue
Train it is exactly one bar: bar 0, the one-bar `NC` intro before chorus 1
(`form = I1`), containing 7 notes.

**Decision: an `NC` bar plays the melody note alone — no harmonisation, no
reharmonisation, no warning.**

### 4.1 Engine support (additive, minimal)

- `NO_CHORD = "NC"` module constant.
- `VoiceLeadingEngine.get_melody_only_voicing(melody_note, prefer=MELODY_STRING_CHOICES)`
  returns a **single-fret** `Voicing` on the best string, or `None` if the note is
  unreachable. It walks the preferred strings then falls back to the rest, so
  `G3` still works even though index 3 is not a melody-string choice.
- `ArrangementStep.melody_only: bool = False` — a **defaulted** field, so the
  existing `__getitem__` shim and every current test keep working unchanged.
- `arrange_progression` short-circuits `NC` steps to melody-only *before* any
  chord logic — no non-chord-tone strategy, no warning.
- `_step_annotation` gains `(no chord — melody alone)`, shared by
  `format_progression` and `_print_step` so the two renderings cannot drift.

### 4.2 The four-string invariant does not apply

The documented playability invariant (four contiguous strings, melody on the
soprano) is a property of **drop-2 voicings**. A melody-only step is explicitly
not one: it does not go through `get_all_drop2_voicings` and does not participate
in voice-leading minimisation. This must be stated in the code and the docs
rather than left implicit, and the invariant tests must exempt such steps.

### 4.3 Verified

Rendering needs **no changes** — `tab_string()` and `tab_block()` already key off
`f >= 0` per string, and `fret_span()` is 0 for a single fret.

```
F4  ->  x-x-x-x-x-1     (high E, fret 1)
Eb4 ->  x-x-x-x-4-x     (B, fret 4)
G3  ->  x-x-x-0-x-x     (G, open)
Bb3 ->  x-x-x-3-x-x
```

Across all 40 distinct `NC` pitches in the database, **38 are playable on some
string; only `B5` and `C6` are not** (above the high E's 18th fret). Those two
are documented as a skip, not a crash.

Blue Train's `NC` bar renders as four melody-only steps:
`F5 x-x-x-x-x-13`, `Eb5 x-x-x-x-x-11`, `Db5 x-x-x-x-x-9`, `Bb4 x-x-x-x-x-6`.

---

## 5. Register handling — phrase-level lift only

The library's melody window is **B3 (MIDI 59) – Bb5 (94)**.

### 5.1 "Too low" has two different shapes

| situation | transcriptions |
|---|---|
| median below B3 → the *whole line* sits too low | **24** |
| median fine, but >5% outlier notes below B3 | 267 |
| already comfortable | 165 |

A blanket transposition solves the small group with the large one. Measured on
Blue Train chorus 1:

| treatment | steps | voiced | warnings | max leap | leaps > 7 semitones |
|---|---|---|---|---|---|
| as-transcribed | 57 | 46 (81%) | 26 | 9 | 4 |
| blanket `+12` | 57 | 56 (98%) | 12 | 9 | 4 |
| per-note lift | 57 | 57 (100%) | 11 | 9 | 1 |

Blanket `+12` was solving a 12% problem by moving 88% of the music: it pushed
`F4` to `F5` and shoved shapes into the 16–18 fret box (`x-x-17-18-16-18`).

### 5.2 Decision: lift at phrase granularity, only when genuinely low

- If a **phrase's median pitch < B3** → lift the whole phrase `+12` (covers the 24
  low transcriptions, using spans from the `sections` table).
- Otherwise leave it alone; individual sub-B3 notes are **skipped and counted**,
  which the engine already does.

Per-phrase was chosen over per-note and per-bar because lifting at too fine a
granularity **tears the line apart**: at step 51, `F3 → Ab3` was a descending 3rd
in the source, but lifting `F3` alone turned it into a descending 10th. Per-note
leaves 1 such artefact, per-bar leaves 1, **per-phrase leaves 0**.

**Consequence for Blue Train: no transposition at all.** Its median is 65 (F4),
comfortably in the window, so chorus 1 voices 46/57. The 11 skipped notes are the
low turnaround figures below the four-string drop-2 range, reported rather than
silently moved. The line stays in a tight 1st–6th fret box instead of the 16–18
fret clutter.

`--lift per-note` is available as an opt-in for full coverage (57/57, one 10th
artefact at step 51).


---

## 6. Unresolved non-chord tones — `diminished` retry

Some avoid notes have no extension target in the library's table. For Blue Train
chorus 1 these are 10 steps:

```
Eb7 E5, Eb7 F#5, Eb7 D5 (x2), Eb7 F#4
C7  Eb5, C7 Db5
F-7 F#5, F-7 Bb4
```

These are the hardest bebop tensions — `E5`/`D5` over `Eb7` (major 3rd clashing
with the ♭3 of the dominant), `F#5` over `Eb7`/`F-7` (augmented 9th / major 3rd
over minor), `Eb5`/`Db5` over `C7`. `extension` correctly **refuses rather than
inventing** a chord, which is the right default behaviour.

**Decision: retry with the `diminished` strategy before giving up.** Measured
recovery: **10 of 10**.

```
Eb7 E5  -> Ddim7 x-x-11-12-11-12      Eb7 F#5 -> Ddim7 x-x-13-14-13-14
Eb7 D5  -> Cdim7 x-x-9-10-9-10        C7  Eb5 -> Bdim7 x-x-10-11-10-11
C7  Db5 -> Bdim7 x-x-8-9-8-9          F-7 F#5 -> Edim7 x-x-13-14-13-14
F-7 Bb4 -> Gdim7 x-x-5-6-5-6
```

Chorus 1 goes from 57 steps / 20 warnings to **57 steps, 0 warnings**, every step
a genuine chord tone.

### 6.1 Why this is opt-in, not the default

The retry works *mechanically* — it finds the dim7 a semitone below the
resolution target — but harmonically it **replaces the written chord**. On `Eb7`
in a 12-bar blues, `Ddim7` is a lovely Coltrane-ish colour, but it is not a
blues accompaniment: **6 of the 10 substitutions land on `Eb7`**, the tonic of the
blues. The chorus-1 arrangement would read `Eb7, Ddim7, Ddim7, Ddim7, Eb7,
Bdim7, Bdim7, Edim7, Gdim7, Cdim7, Cdim7, Eb7` — the tonic bar is no longer a
plain dominant.

So `--fallback diminished` is a flag, off by default. The retry is placed
*after* `extension` fails, so it can only ever rescue a step that would otherwise
be unresolved; it never overrides a successful extension, and with the flag off it
changes nothing.

---

## 7. Module layout

`wjazzd.py` is a **separate module**, not part of `arranger.py`: it is optional
dataset glue that no existing user needs, and keeping it out preserves the frozen
`tab_string()` contract and leaves the single-module test suite untouched.
**No new dependencies** — stdlib `sqlite3` only, per the standing rule that
`musthe` is the only runtime dependency.

### 7.1 `arranger.py` changes (additive only)

- `NO_CHORD = "NC"` constant
- `VoiceLeadingEngine.get_melody_only_voicing(...)`
- `ArrangementStep.melody_only: bool = False`
- `arrange_progression`: NC short-circuit
- `_step_annotation`: the `(no chord — melody alone)` case


### 7.2 `wjazzd.py` public surface

| name | purpose |
|---|---|
| `WEIMAR_QUALITY_ALIASES` | suffix → library quality (§2.1) |
| `parse_weimar_chord(symbol)` | → `(root, quality, bass)`; strips the slash; `NC` → `(None, None)` |
| `Solo` / `NoteEvent` | dataclasses; `NoteEvent` carries `chord` + `quality` from the forward fill |
| `DEFAULT_DB` | sibling `wjazzd.db`, overridable via `WJAZZD_DB` |
| `load_solo(melid, db_path=None)` | metadata + note events with the forward fill |
| `list_solos(db_path=None)` | the 456 metadata rows |
| `skeleton(solo, strategy, bars, pick, lift, fallback)` | → the `(note, quality, name)` triples `arrange_progression` consumes |

### 7.3 CLI

```
python arranger.py corpus --melid 218 --bars 1-12 \
    [--skeleton chords|beats|eighths|sixteenths|notes] \
    [--pick first|longest] \
    [--lift none|phrase|per-note] \
    [--non-chord-tone extension|diminished|sustain|legacy] \
    [--fallback diminished] \
    [--vertical]
```

Defaults encode the decisions above: `eighths`, `first`, `none` (no lift),
`extension`, no fallback. Existing no-arg demo behaviour is unchanged.

---

## 8. Tests

`tests/test_wjazzd.py`, all guarded by `skipUnless(DEFAULT_DB.is_file(), ...)` so
the suite still passes without the 42 MB database:

- suffix table coverage; `parse_weimar_chord` for `NC`, slash chords, unknown
  suffixes → `None`
- rule B promotion (`A-/G` → `m7`, `C-/Bb` → `m7`) and non-promotion
- rule C changing the pick in at least one real corpus case
- forward-fill ground truth (§1.2 table)
- skeleton step counts: 12 / 36 / **57** / 80 / 80 for chorus 1
- phrase-lift threshold behaviour
- every harmonised step satisfies the playability invariants
- `NC` → melody-only: exactly one active fret, `non_chord_tone is False`,
  `harmonized_as is None`
- diminished-retry recovery (10/10)

Plus `NC` cases in the engine test files.

**Workflow gate** (per `AGENTS.md`): `.venv/bin/python -m unittest discover -s
tests -v` must report `OK`; `.venv/bin/pyright arranger.py tests` must report
`0 errors`; run the demo and the corpus command and sanity-check the tabs.

---

## 9. Documentation

- `AGENTS.md`: a "Corpus integration" section, the new file in the layout tree,
  and a note on the "adding a chord quality" checklist that Weimar aliases must be
  kept in sync.
- `README.md`: a usage example for the `corpus` command.
- `__version__`: `0.3.0` → `0.4.0` (additive feature).

---

## 10. Decision summary

| decision | choice | rationale |
|---|---|---|
| transcription | Blue Train (`melid` 218) | 8 × 12-bar choruses, 7 distinct chords, all mappable, 45 phrases, 99% in range |
| skeleton density | **`eighths`** (4.8/bar) | 98% voiced, playable, preserves the line's character |
| slot pick | first note | on an 8th grid there is almost always only one |
| non-chord-tone strategy | **`extension`** | the alternatives abandon the blues harmony |
| unresolved NCT | `--fallback diminished`, opt-in | recovers 10/10 but replaces the written chord |
| `NC` bars | melody alone, no harmonisation | unaccompanied intro; common in 267/456 transcriptions |
| octave lift | **phrase-level only** | per-note/per-bar tear the line; Blue Train is not transposed at all |
| slash chords | **B + C**, loader-only | fixes the parser breakage and honours 63% of basses; engine stays frozen |
| module | separate `wjazzd.py` | optional glue; preserves the frozen public surface |
| dependencies | none beyond stdlib | standing rule: `musthe` is the only runtime dependency |

## 11. Open questions

- `--bars 1-12` excludes the `NC` intro. It is covered by a test, and
  `--bars 0-12` renders it. Keep, or default the range to include bar 0?
- For the 8th/16th skeletons, should an `NC` span also collapse to one melody
  note? Currently it does, which keeps the skeleton uniform.
- A 3/4 or 6/8 transcription would need beat-position handling that assumes
  4/4. `solo_info.signature` covers this; the skeleton currently derives the grid
  from fractional beat offsets, which generalises, but no non-4/4 case has been
  tested.
