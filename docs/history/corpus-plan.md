# Corpus integration plan — Weimar Jazz Database

Status: **planned, not implemented.** This document is the spec to build against
and revise. Decisions below were made from measurements against the real
database, not guesses; each records the evidence it rests on.

- Worked examples: **John Coltrane, "Blue Train" (`melid` 218)** and
  **"All the Things You Are" (266, 328, 342, 451)** — the latter is the
  validation case that invalidated three earlier decisions (§2.7)
- **Primary purpose: generate voicings for the HEAD, not to harmonise the
  transcribed solos.** See §2.
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
| `sections` | 58,560 | `melid, type, start, end, value` — see below |
| `melody_type` | 456 | see below |
| `composition_info`, `record_info`, `track_info`, `transcription_info`, `esac_info`, `popsong_info`, `db_info` | | metadata |

**`melody_type` is SOLO-only.** The column is `type` (not `melody_type`), and
`SELECT DISTINCT type FROM melody_type` returns exactly one row: `'SOLO'`, 456
rows. There is **no `THEME` value in this table**, contrary to the commonly
published description of the schema. See §3.3 for where "theme" *does* appear
and why it is not used.

**`sections` has two categorical columns, not one.** The full column list is
`(melid, type, start, end, value)`, where `type` is the *kind of span* and
`value` is *what the span is*:

| `type` | rows | `value` looks like |
|---|---|---|
| `CHORD` | 27,102 | `Eb7`, `C-7`, `NC`, … (a chord symbol) |
| `IDEA` | 15,414 | `lick`, `line_w`, `theme:t1`, `*theme:t1-4`, `#theme:t9-12`, … |
| `PHRASE` | 11,082 | `1`, `2`, `-1`, … (a phrase number) |
| `FORM` | 3,292 | `A1`, `A2`, `B1`, `I1`, `C1`, … (a form label) |
| `CHORUS` | 1,670 | `-1`, `1`, `2`, … (a chorus number) |

Spans are half-open: `start <= bar < end`. **A-form detection is
`type='FORM' AND value LIKE 'A%'`** — the A section of an AABA form, of which
`A1` is the first block.

### 1.2 Bars can be negative — the forward fill must tolerate it

**1,335 `beats` rows and 1,353 `melody` notes across 149 transcriptions have
`bar < 0`**, with a minimum of **bar −31**. `melid 266` alone has 48 such beats
reaching back to bar −12.

This is the anacrusis: the pickup is numbered with negative bars. It is
invisible to any code that assumes `bar >= 0`, and it breaks two things if
unhandled:

- the **forward fill** below, because the last chord at or before a negative-bar
  note may itself be at a negative bar;
- **`--bars` range parsing**, which must accept negative bounds
  (`--bars -4-8`) and must not treat a negative `LO` as malformed input.

Decision: `bar` is a signed integer everywhere in the loader. Ranges are
half-open and may be negative; the default range for a selected section is
`[section.start, section.end)`, which inherits its sign from the data.

### 1.3 The chord binding must be reconstructed

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

The comparison is on the `(bar, beat)` tuple, so negative bars order correctly
with no special case. Verified on the ATTYA pickups in §2.7, where the fill
resolves chords at bars −12 through −1.

### 1.4 Register

Melody range is MIDI 36–97 overall; **199,910 of 200,809 notes (99.6%)** fall
inside the library's `B3`–`Bb5` window (MIDI 59–94). Out-of-range notes are
already skipped by `arrange_progression`, so the loss is negligible.

---

## 2. Head selection — the primary purpose

**Decision: this integration generates voicings for the HEAD of a piece. It is
not a tool for harmonising transcribed solos.** Every other section is written
subordinate to that goal; the solo-oriented material that survives is retained
only where it is needed to *find* the head.

### 2.1 Why heads, and what a head is here

A transcribed solo is a poor input for chord-melody: it is fast, harmonically
unusual, and the melody fights the changes. A head is the opposite — slower,
more conjunct, and written to sit against the harmony. Voicing heads is the
actual use case; solo harmonisation was a means of getting there.

**Early definition (superseded — see §2.7):** "the head is the first A-form
block", `sections WHERE type='FORM' AND value LIKE 'A%' ORDER BY start LIMIT 1`.
This is **wrong**, and §2.7 shows it fails on a canonical case. The A-form label
is a useful *starting hint*, not a definition.

### 2.2 The A-block is the head *form*, not the bare theme statement

This matters for naming and for expectations. A-forms are AABA, so `A1` is
usually the theme *plus* its repeats and often the first chorus:

| first A-block length | transcriptions |
|---|---|
| minimum | 0 bars |
| p25 | 41 bars |
| **median** | **61 bars** |
| p75 | 88 bars |
| maximum | 1,352 bars |
| 4–32 bars (i.e. plausibly a bare theme) | **54 of 455** |

So the honest description of what this feature produces is *"the head (A1
section)"*, not *"the theme"*. Isolating the bare theme statement is **not
possible from this database**: the only theme markers are the sparse analyst
annotations rejected in §2.3, and they do not align with A-block boundaries.
**Decision: ship A1 as-is, and call it the head everywhere in code, CLI, docs
and tests.** Do not use the word "theme" for it.

### 2.3 The `theme` IDEA annotations are rejected

`theme` does appear in the database — but only as an `IDEA` annotation, and it is
far too sparse to build on:

| property | value |
|---|---|
| `IDEA` rows with `value LIKE '%theme%'` | **231** |
| transcriptions with any theme idea | **77 of 456** (17%) |
| note content inside theme spans | **18,605 of 200,809 (9.3%)** |
| bar coverage within a transcription | median **10%**, mean 23% |
| spans that start at bar 0 | 31 of 77 |
| spans labelled `theme:?` (analyst did not say which) | **19** |

Three further problems:

- **Blue Train has zero theme ideas**, so this would not apply to the target.
- The `t1`…`t32` numbering is a per-transcription bar counter into the *original
  composition*, not a stable identifier, so annotations are not comparable across
  transcriptions.
- The annotation carries an intensity prefix: `*theme:t1` (20×), `#theme:t1`
  (10×), `~theme:…`. Only a minority are a bare `theme:tN`, so a naive
  `LIKE '%theme%'` silently mixes strong and tentative labels.

Honouring them is possible but is a separate opt-in flag, never the main path.

### 2.4 What heads look like — measurements

Across 455 transcriptions with an A-form, using each first A-block:

| property | head | comparison |
|---|---|---|
| A-form exists | **455 / 456** | — |
| first A-block with ≥8 bars and ≥8 notes | **441 / 455** | usable |
| note content in all A-forms | 183,123 (91.2% of all notes) | — |
| notes/bar, median | **4.1** | 5.8 in the last 16 bars of the same transcriptions |
| mean note duration | 0.152 | 0.157 |
| chord changes/bar, median | **0.71** | — |
| distinct chords in the head, median | **10** (p90 19) | — |
| head starts at bar 0 | 199 (bar ≤5: 336, bar ≤10: 388) | — |

**The negative result: heads are not more chord-tone-rich than solos — and on
real standard melodies they are *worse*.**

| | chord-tone rate (median) |
|---|---|
| head (first A-block) | **58.7%** |
| later material (last 16 bars) | **58.8%** |

That corpus-wide equality is the *optimistic* reading. Validated against ATTYA
(§2.7), whose head is a chromatic standard melody rather than a bebop solo line
and measures far worse:

| melid | head chord-tone rate | non-chord tones |
|---|---|---|
| 266 (Konitz) | **48.6%** | 46% |
| 328 (Jackson) | 64.5% | 48% |
| 342 (Metheny) | **54.8%** | 55% |
| 451 (Sims) | 56.1% | 24% |

The likely reason the corpus figure hides this: a standard melody is built from
passing tones between *widely spaced* chord tones, so it is more non-chordal
than the bebop line it was compared against. **The earlier measurement used a
permissive tone-set that probably over-counted chord tones** — so treat 58.7%
as an upper bound, not a central estimate.

The honest statement: re-targeting to heads buys **playability, not simpler
harmony — and on standard melodies possibly the opposite of it.** `extension`
remains the default strategy, and the `diminished` retry in §7 is a routine path
rather than an edge case. See §4.2 and §7.1.

**What the head does buy is density.** 0.71 chord changes/bar is close to one
chord per bar, which is what makes the `chords` skeleton (§4) a natural default
here rather than the `eighths` default that fit the solo.

### 2.5 Degenerate cases the selector must handle

The A-form is not uniformly well-formed. The loader must detect and report, not
crash on:

- **2 transcriptions** with a first A-block shorter than 4 bars (one is
  `melid 44`, a zero-length `(114, 114)` span — `start == end` selects nothing).
- **130 transcriptions** with a first A-block longer than 80 bars — legal, but
  the user should be told the head is 100+ bars before rendering it.
- **Head start bars scattered far from 0** (199 at bar 0, 388 by bar 10) — a
  head does not imply a pickup, so the loader must not assume bar 0.

### 2.6 Solos remain reachable, but are not the point

`--section` accepts any `type:value` (§8.3), so a solo is still one flag away
(`--section chorus:1`). It is simply no longer the default, and the worked
example throughout this document is a head.

### 2.7 Validation case: "All the Things You Are" breaks the selector

The head definition was tested against **"All the Things You Are"**, which is
close to a worst case: a 36-bar form that **modulates in every section**, whose A
section is a canonical 8 bars. Four transcriptions are in the database:

| melid | performer | key | tempo | choruses |
|---|---|---|---|---|
| 266 | Lee Konitz | `Ab-maj` | 192.5 | 3 |
| 328 | Milt Jackson | `Ab-maj` | 166.9 | 1 |
| 342 | Pat Metheny | `F-maj` | 306.7 | 6 |
| 451 | Zoot Sims | `Ab-maj` | 192.2 | 1 |

`solo_info.chord_changes` gives the ground truth. ATTYA's A section is **8 bars**:

```
A1: | F-7 | Bb-7 | Eb7 | Abj7 | Dbj7 | G7 | Cj7 | Cj7 |
A2: | C-7 | F-7  | Bb7 | Ebj7 | Abj7 | D7 | Gj7 | Gj7 |
B1: | A-7 | D7   | Gj7 | Gj7  | F#-7| B7 | Ej7 | C+7 |
C1: | F-7 | Bb-7 | Eb7 | Abj7 | Dbj7 | Db-7 | C-7 | Bo7 | Bb-7 | Eb7 | Abj7 | G7 C7 |
```

#### 2.7.1 The head is not inside `FORM A1`

Searching each transcription's `beats` for the A1 progression puts the real
8-bar head at **bars 1–8 in all four** — which lies inside `FORM I1`, *before*
`A1` begins:

| melid | `FORM I1` | `FORM A1` | A1 length | true head | head inside A1? |
|---|---|---|---|---|---|
| 266 | 0–77 | 78–113 | 35 bars | **bars 1–8** | **no** |
| 328 | 0–17 | 18–79 | 61 bars | **bars 1–8** | **no** |
| 342 | 0–14 | 15–81 | 66 bars | **bars 1–8** | **no** |
| 451 | 0–5 | 6–45 | 39 bars | **bars 1–8** | **no** |

`select_head(218)` as specified in §8.2 would return nothing usable for any of
these. The `I` label (intro) routinely *contains* the head, and the `A1` label
starts at the second statement.

This is not an ATTYA quirk. Of the 282 transcriptions carrying both form types,
**250 have an `I` form starting before the first `A` form**, and **84 of 455**
first A-blocks begin after bar 8.

Worse, the A-blocks are **35–99 bars** — for an 8-bar A section that is the
whole 36-bar form repeated several times. §2.2's "the A-block is the head form,
not the bare theme" badly understates this: the A-block is not one statement
plus repeats, it is *multiple complete form cycles*.

#### 2.7.2 Revised head selection

Decision: **select the head on chord progression, not on the form label.** The
`FORM`/`CHORUS` labels are only a hint for where to start looking.

Proposed `select_head`, in order:

1. **Seed** from the first `FORM` `A*` block, *extended backwards* to include any
   contiguous preceding `I*` block (this alone recovers all four ATTYA heads).
2. **Anchor** on the chord progression at the seed's first bar, read from
   `beats` via the forward fill.
3. **Trim** to the first bar at which that progression **repeats** — i.e. scan
   for the earliest subsequent position whose chord sequence matches the anchor
   from the top. This cuts the 35–99 bar A-block down to one statement.
4. **Report** the anchor chords and the trimmed length, so the user can see what
   was selected and override with `--bars`.

Step 3 is what makes this a *head* rather than a form cycle, and it is why
chord-progression matching is the right primitive: ATTYA's A1 progression is
unique enough to anchor on, and the trim is exact rather than heuristic.

**Open risk:** the anchor must be matched modulo transposition, since the same
progression recurs in a new key in later sections. Matching on the *sequence of
chord qualities* (ignoring roots) is more robust than matching on absolute
roots, and is what step 3 should do.

**`melid 342` also carries `#theme:t1-8` and `theme:t28-36` annotations** — an
`IDEA` span at bars 0–45 that happens to bracket the head. This is the one case
where the `theme` annotations rejected in §2.3 would have helped, and it is
*not* a reason to revisit that rejection: 1 transcription out of 456 agreeing
with an otherwise-sound rule is a coincidence, not evidence.

#### 2.7.3 What held up

The notation and voicing machinery is sound on this material:

- **Chord vocabulary is clean.** All four heads use only `m7`, `7` and `maj7`
  (melid 451 adds `D-7`). Every one maps through `WEIMAR_QUALITY_ALIASES` with
  **no `None` returns**. No `NC` inside any head, no slash chords. The Weimar
  table of §3.1 is sufficient.
- **The modulation is a non-issue.** ATTYA moves `A♭maj7 → G7 → Cmaj7` mid-head;
  the engine is pitch-relative throughout, so no key tracking is required.
- **Voicings are playable wherever register allows.** Fret spans 3–4 (limit 5),
  max melodic leap 7 semitones, **zero** leaps > 7 across all four transcriptions.

#### 2.7.4 Negative bars surface here

`melid 266` carries 48 beats and notes down to **bar −12**, and all four
transcriptions have pickup material in negative bars — the anacrusis documented
in §1.2, which the ATTYA head sits directly on top of.

---

## 3. Chord notation

The database uses **Weimar notation**, which `ChordParser` does not understand.
There are **419 distinct chord symbols** and **47 distinct suffixes** across the
corpus.

### 3.1 The suffix table (derived from data, not guessed)

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

### 3.2 Slash chords — rules B and C

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

## 4. The reduction problem

**A drop-2 voicing is a per-beat object, but the head still has 845 notes across
79 bars.** Voicing all of them is musically meaningless, so the line must be
reduced to a playable skeleton. The numbers below are measured on Blue Train's
head (`FORM` A1, bars 7–86) — **not** on chorus 1 as in earlier drafts of this
document.

### 4.1 Measured density on the head (Blue Train)

Measured on Blue Train's `FORM` A1 block, bars 7–86. **Note this span is the
*untrimmed* A-block** — the trim of §2.7.2 would cut it to a single statement, so
these counts are an upper bound on what a trimmed head contains.

| source | count | per bar |
|---|---|---|
| chord changes | 61 | **0.77** |
| beat slots occupied | 274 | 3.47 |
| 8th-grid slots | 299 | 3.78 |
| 16th-grid slots | 457 | 5.78 |
| **raw notes** | **845** | **10.70** |

845 notes in 79 bars is 10.7/bar — *denser* than the solo material this feature
replaced (4.1 notes/bar median across the corpus, §2.4), because Coltrane plays
the head with the full chorus phrasing and then some. So the reduction problem
is **larger** for heads, not smaller, and the skeleton default must be
re-derived rather than inherited.

Note the 8th and 16th grids (299 and 457) sit well below the note count (845):
Coltrane plays chords and ornaments inside single slots, so a grid does not
capture the line. The grid is computed properly from `tatum`/`division` rather
than assumed; the 16th grid is the finest useful resolution and `notes` is
retained only for diagnostics.

**Decision: `--skeleton` keeps all five strategies, and the default is
re-measured on head data before it is fixed.** The corpus-wide expectation is
that `chords` (0.77/bar) and `beats` (3.5/bar) both become plausible defaults
for a head, where `eighths` (3.8/bar) looked right for a 12-bar solo. Do not
carry the old `eighths` default over unexamined; measure all five on
`FORM:A1` across the corpus and pick from the result. This is an **open
decision**, recorded as such.

Whatever wins, the selection criteria are the same as before: playability, a
high voiced-step rate, and preserving the head's melodic character. A skeleton
so dense that voicings skip (`warnings`) is not an arrangement.

**Position within a slot:** take the **first** note. On a 16th grid this is
almost always the only note anyway. (`--pick longest` is available for the beat
grid, where it favours the sustained note.)

### 4.2 Non-chord tones remain the norm, not the exception

**Heads are not harmonically simpler than solos** (§2.4: 58.7% vs 58.8%
chord-tone rate), so the bebop tension distribution that made this a problem
for solos still applies to heads. The earlier corpus-wide distribution over the
root:

| degree | 2 (9th) | 5 (11th) | 9 (13th) | 3 (♭9) | 11 (maj7) | 1 | 6 (♭13) | 8 |
|---|---|---|---|---|---|---|---|---|
| count | 124 | 88 | 70 | 46 | 44 | 43 | 42 | 36 |

**Decision: `extension` is the default strategy, unchanged by the head
re-target.** The alternatives are no better here: `diminished` abandons the
written harmony, `sustain` produces shapes that are not literally the written
chord, and `legacy` can voice a note that is not in the chord at all. The other
strategies stay available per-invocation.

Because ~41% of head steps are non-chord tones, the `--fallback diminished`
retry (§7) matters at least as much for heads as it did for the solo, and its
"replaces the written chord" caveat (§7.1) must be stated in the head-facing
docs too.

---

## 5. `NC` bars — melody, no harmony

**401 `NC` beat rows across 267 of 456 transcriptions** — common corpus-wide, but
**rarer inside heads: only 92 of 454 first A-blocks (20.3%) contain any `NC`,
131 `NC` beat rows in total.**

**Blue Train's only `NC` bar is bar 0, which lies *outside* A1 (bars 7–86)**, so
the worked head example exercises no `NC` handling at all. The `NC` intro is
reachable only via `--section form:I1` or an explicit bar range.

**Decision: an `NC` bar plays the melody note alone — no harmonisation, no
reharmonisation, no warning.** Unchanged from the solo-oriented draft, and
still worth building: it fires for a fifth of heads, and heads do not always
begin at bar 0 (§2.5), so a head may legitimately open unaccompanied.

### 5.1 Engine support (additive, minimal)

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

### 5.2 The string-set invariant does not apply to a melody-only step

The documented playability invariant (the sounding strings are one
`supported_string_sets()` entry, melody on its soprano) is a property of a
*harmonised* voicing. A melody-only step is explicitly not one: it does not go
through `get_all_grip_voicings` and does not participate in selection. It has a
single active fret and `fret_span() == 0`. This must be stated in the code and the
docs rather than left implicit, and the invariant tests must exempt such steps.

Note the invariant itself has since widened: it is no longer "four contiguous
strings". Shells use three strings and duos two, and the 6-4-3 shell deliberately
skips the A string. What still holds — and what the corpus-wide test now asserts —
is membership of a supported set, the melody on its topmost string, and
`fret_span() <= 5`.

### 5.3 Verified

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

## 6. Register handling — whole-head lift, chosen by coverage

The library's melody window is **B3 (MIDI 59) – Bb5 (94)**.

### 6.1 "Too low" has two different shapes

| situation | heads (first A-block) | transcriptions (whole line) |
|---|---|---|
| median below B3 → the *whole head* sits too low | **29 (6.6%)** | 24 |
| median fine, but >5% of notes below B3 | **249 of 413 (60.3%)** | 267 |
| already comfortable | 413 of 442 (93.4%) | 165 |

The two shapes persist for heads, with a similar ratio: a small group that needs
a real transposition, and a much larger group with a handful of low outliers.

A blanket transposition solves the small group with the large one. Measured on
Blue Train chorus 1:

| treatment | steps | voiced | warnings | max leap | leaps > 7 semitones |
|---|---|---|---|---|---|
| as-transcribed | 57 | 46 (81%) | 26 | 9 | 4 |
| blanket `+12` | 57 | 56 (98%) | 12 | 9 | 4 |
| per-note lift | 57 | 57 (100%) | 11 | 9 | 1 |

Blanket `+12` was solving a 12% problem by moving 88% of the music: it pushed
`F4` to `F5` and shoved shapes into the 16–18 fret box (`x-x-17-18-16-18`).

### 6.2 The median threshold is too low — ATTYA proves it

The earlier rule lifted only when a **phrase median** fell below B3. Validated
against the ATTYA heads (§2.7), that rule fails on the most ordinary material
there is:

| melid | head median | notes below B3 | median rule fires? | voiced as-is | voiced `+12` |
|---|---|---|---|---|---|
| 266 | 65 | 0 of 35 | no | **97%** | — |
| 328 | 71 | 0 of 62 | no | **98%** | — |
| 342 | **60** | **15 of 31** | **no** | **52%** | **100%** |
| 451 | **61** | **16 of 41** | **no** | **56%** | **100%** |

Medians of 60 and 61 sit one or two semitones above the trigger, so the rule
does nothing — while **half the head is unplayable**. A whole-head `+12` recovers
**100% of the unvoiced notes in both cases**, and costs nothing musically: max
leap 3 and 5 semitones, max fret span 4.

Note the shape: this is *not* a per-note problem needing a per-note fix. The
entire head is uniformly an octave too low for the four-string drop-2 range. The
old rule's per-note fallback (skip and count) was papering over a whole-head
condition.

The blind spot is corpus-wide: **249 of 442 heads (56%)** have median ≥ B3 but
more than 5% of notes below it — exactly the shape §6.2 declines to act on.

### 6.3 Decision: lift the whole head, chosen by measured coverage

The lift is now applied at **whole-head** granularity, and the decision to apply
it is made by **measuring coverage** rather than by a pitch threshold:

1. Build the skeleton **as transcribed**.
2. Build it again at **`+12`**.
3. Count how many steps each voices successfully.
4. **Keep the `+12` version if it voices strictly more steps; otherwise keep the
   original.** Ties go to the original, so music is never moved without a gain.

This is deliberately self-correcting and threshold-free. It cannot be defeated
by a median sitting one semitone above an arbitrary cut-off, and it cannot move
music that was already fine — the Blue Train head, which voices 88% of its notes
in place, is left alone for free rather than by a special case.

Rejected alternative: raising the threshold to "median < B3 **or** >5% of notes
below B3". This is closer to the measurement but still guesses a cut-off, and
still cannot know whether a lift actually *helps*. Step 3 measures the thing we
care about.

**Open cost to check at implementation time:** the coverage comparison requires
voicing each head twice, roughly doubling skeleton time. If that proves slow on
a 61-bar head, fall back to the >5% rule, which is nearly as good and half the
work.

`--lift` gains an explicit `auto` value implementing the above, alongside:

| `--lift` | behaviour |
|---|---|
| `auto` | **default** — the coverage comparison of §6.3 |
| `none` | never lift |
| `always` | always lift `+12` |
| `per-note` | lift individual sub-B3 notes (opt-in; known to tear the line, §6.4) |

Phrasing the lift at whole-head rather than per-phrase also keeps the
anti-tearing property below: within a head, every note moves by the same amount,
so no interval is ever stretched.

### 6.4 Why not per-note or per-bar

Lifting at too fine a granularity **tears the line apart**. Measured on Blue
Train chorus 1: at step 51, `F3 → Ab3` was a descending 3rd in the source, but
lifting `F3` alone turned it into a descending 10th. Per-note leaves 1 such
artefact, per-bar leaves 1, whole-unit lifting leaves **0**.

Whole-head lifting is the coarsest useful granularity and is therefore the safest:
a uniform transposition cannot distort any interval by construction. The earlier
per-phrase rule was chosen for the same reason against per-note; it is superseded
only because its *trigger* was wrong (§6.2), not because its granularity was.

### 6.5 Consequence for the worked examples

**Blue Train (`melid` 218): not transposed.** Its median is 65 (F4) and the head's
range is MIDI 51–77, comfortably in the window. **88.3% of head notes (746 of 845)
fall inside B3–Bb5**. Under `--lift auto` the `+12` candidate does not voice more
steps, so the original wins and the line stays in a tight low-mid fret box
instead of the 16–18 fret clutter.

**ATTYA (`melid` 342, 451): transposed `+12`.** Medians of 60 and 61 with 15–16
unplayable notes each (§6.2); `auto` selects the lift and coverage goes from
52%/56% to 100%.


---

## 7. Unresolved non-chord tones — `diminished` retry

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

### 7.1 Why this is opt-in, not the default

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

**This caveat is heavier for heads than for solos, and the ATTYA data (§2.7)
strengthens the case for leaving the flag off.** Heads are not *more*
chord-tone-rich (~58.7% at best, and 48.6–64.5% on real standard melodies), so
roughly half of head steps will need resolution — but a head arrangement is meant
to be *the written tune*, and substituting dim7s under a head is exactly the
sort of thing a user would not expect from a "give me the head" command.

**Keep `--fallback diminished` off by default.** The ATTYA validation did *not*
change this decision; it confirmed it. On material where 46–55% of notes are
non-chordal, enabling the retry by default would make it a co-equal strategy
rather than a rescue path, and would mean the "head" command routinely returns
something other than the head's own harmony.

State the trade-off explicitly in the head-facing README text, and report how
many steps a `--fallback diminished` run *would* have rescued, so the user can
see what they are missing without having to opt in.

**The 10-step recovery figure above is measured on chorus 1, not on the head.**
Re-measure on the selected head before quoting a recovery rate for head work; the
head has 8× the steps and a different phrase structure, so the count will differ.

---

## 8. Module layout

`wjazzd.py` is a **separate module**, not part of `arranger.py`: it is optional
dataset glue that no existing user needs, and keeping it out preserves the frozen
`tab_string()` contract and leaves the single-module test suite untouched.
**No new dependencies** — stdlib `sqlite3` only, per the standing rule that
`musthe` is the only runtime dependency.

### 8.1 `arranger.py` changes (additive only)

- `NO_CHORD = "NC"` constant
- `VoiceLeadingEngine.get_melody_only_voicing(...)`
- `ArrangementStep.melody_only: bool = False`
- `arrange_progression`: NC short-circuit
- `_step_annotation`: the `(no chord — melody alone)` case

### 8.2 `wjazzd.py` public surface

| name | purpose |
|---|---|
| `WEIMAR_QUALITY_ALIASES` | suffix → library quality (§3.1) |
| `parse_weimar_chord(symbol)` | → `(root, quality, bass)`; strips the slash; `NC` → `(None, None)` |
| `Section` | dataclass: `melid, type, start, end, value` — one `sections` row |
| `Solo` / `NoteEvent` | dataclasses; `NoteEvent` carries `chord` + `quality` from the forward fill |
| `DEFAULT_DB` | sibling `wjazzd.db`, overridable via `WJAZZD_DB` |
| `list_solos(db_path=None)` | the 456 metadata rows |
| **`list_sections(melid, type=None, db_path=None)`** | all `sections` rows for a transcription, optionally filtered by `type` |
| **`parse_section_selector(selector)`** | `"form:A1"` → `("FORM", "A1")`; supports a `*` glob in the value (`"form:A*"`). Validates the `type` against the five known kinds and **raises on an unknown one rather than returning no rows** |
| **`select_head(melid, db_path=None)`** | → the head as a `Section`, or `None` if none can be found. **This is the default selection, and it is defined by chord progression, not by the form label** — see §2.7.2 for the four-step algorithm (seed from the first A-block extended back over any preceding I-block, anchor on the progression, trim to its first repeat, modulo transposition). Reports the anchor chords and the trimmed length, and the degenerate cases in §2.5 |
| `load_solo(melid, db_path=None)` | metadata + note events with the forward fill |
| **`load_section(melid, selector, db_path=None)`** | `load_solo` narrowed to a selected span; the head path |
| `skeleton(solo, strategy, section, pick, lift, fallback)` | → the `(note, quality, name)` triples `arrange_progression` consumes |

`skeleton` takes a **section** rather than a bar range: the head is the unit, and
bar ranges are a narrowing filter within it, not the primary selector.

### 8.3 CLI

```
python arranger.py corpus --melid 218 \
    [--section form:A1] \
    [--bars LO-HI] \
    [--skeleton chords|beats|eighths|sixteenths|notes] \
    [--pick first|longest] \
    [--lift auto|none|always|per-note] \
    [--non-chord-tone extension|diminished|sustain|legacy] \
    [--fallback diminished] \
    [--vertical]
```

`--section` accepts `form:`, `chorus:`, `phrase:`, `chord:`, and `idea:` with a
`*` glob, e.g. `--section form:A*` for all A-blocks and `--section chorus:1`
for a solo chorus. `--bars` accepts **negative** bounds for pickup material
(§1.2), e.g. `--bars -4-8`.

**Defaults encode the decisions above:**

| flag | default | note |
|---|---|---|
| `--section` | **the head** (`select_head`) | primary purpose; see §2 and §2.7.2 |
| `--bars` | the whole selected span | a 12-bar default is meaningless for a 61-bar median head |
| `--skeleton` | **open — re-measure on head data** | §4.1; do not inherit `eighths` unexamined |
| `--pick` | `first` | |
| `--lift` | **`auto`** (coverage comparison) | §6.3; replaces the median threshold |
| `--non-chord-tone` | `extension` | §4.2 |
| `--fallback` | off | §7.1 |

Existing no-arg demo behaviour is unchanged.

**Naming rule:** the CLI, `--help` text, README and tests say **head** or
**A-section**, never "theme" (§2.2). The only place the word "theme" may appear
is documentation of the rejected `idea:theme` selector (§2.3).

---

## 9. Tests

`tests/test_wjazzd.py`, all guarded by `skipUnless(DEFAULT_DB.is_file(), ...)` so
the suite still passes without the 42 MB database:

**Section selection (the new primary path):**
- `select_head(218)` returns the Blue Train head; `select_head` returns `None`
  for a transcription with no findable head
- `parse_section_selector` for `form:A1`, `form:A*`, `chorus:1`, and an **invalid
  type that must raise** (not silently return nothing)
- degenerate A-forms are reported, not crashed on: `melid 44`'s zero-length
  `(114, 114)` span; a <4-bar block; a >80-bar block
- head selection is **not** assumed to start at bar 0 (199/455 do; assert on one
  that does not)

**ATTYA regression cases (§2.7) — the selector's known failure modes:**
- `select_head` on **all four** ATTYA transcriptions (266, 328, 342, 451) finds
  bars 1–8, **not** the `FORM A1` span. This is the test that would have caught
  the original `select_head` design.
- the trim step is **modulo transposition**: a progression recurring in a new key
  later in the form must be recognised as a repeat
- negative bars: the forward fill resolves chords at bars −12…−1 for `melid 266`,
  and `--bars -4-8` parses
- coverage: ATTYA heads use only `m7`/`7`/`maj7` (+`m7`), all mapping with **no
  `None`**
- register: with `--lift auto`, melids 342 and 451 reach **100%** coverage while
  266 and 328 stay untransposed

**Notation and chords (unchanged from the solo draft):**
- suffix table coverage; `parse_weimar_chord` for `NC`, slash chords, unknown
  suffixes → `None`
- rule B promotion (`A-/G` → `m7`, `C-/Bb` → `m7`) and non-promotion
- rule C changing the pick in at least one real corpus case
- forward-fill ground truth (§1.3 table)

**Skeleton and arrangement — on the head, not chorus 1:**
- step counts per strategy, pinned once the §4.1 default is chosen. For Blue
  Train's untrimmed A1 (bars 7–86) the raw slot counts to measure against are
  **61 / 274 / 299 / 457 / 845** for chords / beats / eighths / sixteenths /
  notes. **Also pin an ATTYA head** (bars 1–8, §2.7) — the trimmed, 8-bar case
  the feature will usually see
- `--lift auto` behaviour: lifts 342/451, leaves 266/328 and Blue Train alone
  (§6.3)
- every harmonised step satisfies the playability invariants
- `NC` → melody-only: exactly one active fret, `non_chord_tone is False`,
  `harmonized_as is None`
- diminished-retry recovery — **re-measured on the head**; the 10/10 figure in
  §7 is a chorus-1 number and must not be copied into a head assertion

Plus `NC` cases in the engine test files.

**Workflow gate** (per `AGENTS.md`): `.venv/bin/python -m unittest discover -s
tests -v` must report `OK`; `.venv/bin/pyright arranger.py tests` must report
`0 errors`; run the demo and the corpus command and sanity-check the tabs.

---

## 10. Documentation

- `AGENTS.md`: a "Corpus integration" section, the new file in the layout tree,
  and a note on the "adding a chord quality" checklist that Weimar aliases must be
  kept in sync.
- `README.md`: a usage example for the `corpus` command, **led by the head use
  case** ("render the head of All the Things You Are as chord-melody"), with the
  solo path presented as a secondary option. Must carry the §2.4 honesty note
  (heads are *not* harmonically simpler), the §6.3 note that `--lift auto` may
  transpose the head an octave, and the §7.1 dim7 trade-off.
- `__version__`: `0.3.0` → `0.4.0` (additive feature).

---

## 11. Decision summary

| decision | choice | rationale |
|---|---|---|
| **purpose** | **voicings for the HEAD** | the actual use case; a transcribed solo is fast and fights the changes |
| **head definition** | **chord progression, not form label** | `FORM A1` misses the head entirely on all four ATTYA transcriptions (§2.7.1) |
| validation case | **"All the Things You Are"** (266/328/342/451) | 8-bar head, 36-bar modulating form; breaks the form-label selector, the register rule and the NCT assumption |
| `theme` IDEA annotations | **rejected** | 77/456 coverage, 9.3% of notes, 19 unknown; the one ATTYA case that agrees is coincidence (§2.7.2) |
| `melody_type` table | **not a selector** | it is SOLO-only, 456 rows; no `THEME` value exists (§1.1) |
| negative bars | **supported, signed throughout** | 1,335 beats / 149 transcriptions go below bar 0, to bar −31; ATTYA pickups sit on them (§1.2) |
| skeletons | measured on head data; default **open** | 0.77 chord changes/bar makes `chords`/`beats` plausible; do not inherit `eighths` unexamined (§4.1) |
| slot pick | first note | on a 16th grid there is almost always only one |
| non-chord-tone strategy | **`extension`** | heads are **not** more chord-tone-rich (48.6–64.5% on ATTYA); this is a routine problem, not an edge case (§2.4) |
| unresolved NCT | `--fallback diminished`, **opt-in, confirmed** | recovers, but replaces the written chord — a heavier caveat for a head; ATTYA confirmed rather than changed the decision (§7.1) |
| `NC` bars | melody alone, no harmonisation | fires for 20% of heads; Blue Train's is bar 0, outside its head; **none of the four ATTYA heads contain one** (§5) |
| octave lift | **whole-head, chosen by coverage** | the median threshold is defeated by ATTYA medians of 60/61; `auto` takes the `+12` that voices more steps (§6.3) |
| slash chords | **B + C**, loader-only | fixes the parser breakage and honours 63% of basses; engine stays frozen |
| module | separate `wjazzd.py` | optional glue; preserves the frozen public surface |
| dependencies | none beyond stdlib | standing rule: `musthe` is the only runtime dependency |

## 12. Open questions

- **Which skeleton default?** Still the decision blocking implementation. Needs
  all five strategies measured on the *selected head* (§2.7.2) corpus-wide, then
  pinned in §4.1 and in the test expectations. §4.1's per-bar counts
  (0.77 / 3.47 / 3.78 / 5.78 / 10.70) are the raw material.
- **How aggressive should the progression trim be?** §2.7.2 step 3 cuts at the
  first repeat of the anchor. For a head that legitimately repeats a phrase
  (e.g. a 16-bar AABA head), this may cut too early. Needs checking against a few
  standards with repeating A sections before it is fixed.
- **Is the double-voicing cost of `--lift auto` acceptable?** §6.3 voices every
  head twice. Fallback is the >5% rule if a 61-bar head is slow.
- **Should the `theme` IDEA selector be shipped at all?** Leaning no (§2.3);
  ATTYA 342's `#theme:t1-8` is a curiosity, not a reason (§2.7.2).
- Should an `NC` span also collapse to one melody note in the 8th/16th
  skeletons? Currently it does, which keeps the skeleton uniform.
- A 3/4 or 6/8 transcription would need beat-position handling that assumes
  4/4. `solo_info.signature` covers this; the skeleton currently derives the grid
  from fractional beat offsets, which generalises, but no non-4/4 case has been
  tested.
- A 61-bar median head is a long arrangement. Should there be an output chunking
  or paging option for very long heads, or is a flat tab listing acceptable?
