# Open issues

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it. A fixed issue is **removed** from this file rather than kept as history —
its record lives in the commit that fixed it and in the document it belongs to. Six are open, and
each figure is stated **once**, in its own item: a summary here would be a second source for it,
which is how the numbers in this paragraph rotted three times before the *recipes* below were
made explicit. **Every figure in this file is re-measured by hand from the recipe beside it**:
they are this document's own business, and the gate is not keyed to these items.

1. **The library facade takes its harmony per melody note, so a hand-built timing cannot place a
   chord where the tune is silent** — the importer's half is fixed in full, at the bar and at the
   position; what is left is the entry point a caller supplying its own timings reaches.
2. **A refused thumb note is usually not the shape being unplayable** — measured, decision left
   open: the selector's lever recovers nothing harmlessly any more, and the walk's own pitch,
   which costs the tuple nothing, reaches most of the refusals but only a fraction of them by a
   chord tone.
3. **`harmony=full` is accepted on the comping route and answered with a different family** — the
   one axis value refused by nothing that resolves to something other than itself.
4. **A `bass:` grid row is accepted and changes nothing** — the walk's beats come from the bass
   part, so the row is inert rather than wrong.
5. **A lone note the hand holds can leave the walk below the shape's reach** — the reach is as
   near as the walk's own note allows, so it is the register and not the placement; measured,
   with the selector-side lever left unbuilt.
6. **A position falling on a note's release is not generated** — `melody_at` keeps a note in
   force through its end instant, so §9.2 declines a position the tune has already stopped
   holding; measured, and the boundary is pinned by a test while the reading stays open.

Reproduce the measurements with the commands in [Reproducing](#reproducing).

---

## 1. The library facade takes its harmony per melody note, so a hand-built timing cannot place a chord where the tune is silent

**Status: the importer path is fixed in full; the facade's input shape is what is left.** A bar
the melody never enters, and a beat *inside* a bar it does occupy, are both arranged under every
route that voices chords, including the default grid. What remains is the **entry point**: a
caller supplying its own timings gives one harmony *per melody note*, so a position no note
occupies cannot carry a chord.

**The issue.** Harmony reaches the facade *per melody note*, not per time position. There is no
chord-in-force structure a position without a note can read, so the step loop — which iterates
melody slots — can only *keep* or *drop* a slot and can never *create* one.

**The problem, and what of it is closed.**

- ~~A bar whose melody is entirely rests produces **no part at all**~~ — **fixed at the level
  of the bar.** `_merge_chord_slots` unions a melody-anchored grid's positions for a bar
  `head_skeleton` never touched, so `synthetic_chords_only` now arranges **16 steps** under
  every grid. The scale of the addition over all ten heads is the candidate count below.
- ~~A chords-only lead sheet is silent on every export path~~ — **fixed.** It arranges all
  four bars under the default grid and 16 under `freddie`. The one route still silent is a
  **melody-only selection** (`soprano`, `soprano,bass`), which is a different claim: it plays
  the tune and nothing else, and there is no tune.
- ~~The walking bass shares the limit one level down~~ — **was already fixed wherever a named
  grid ran**, and the default grid's silence was the only thing withholding the bar from it.
  `walking_slots` walks the bars the *timings* touch, and the union writes its added slots
  into those timings. The default now reaches every bar `freddie` reaches **where the tune is
  silent**; a bar whose every position is *held* is withheld by §9.2, and a named grid still
  comps it (`synthetic_repeat_slash` bar 12 is the case).
- ~~The case is structurally inexpressible~~ — **the field half was already done** before this
  item was last measured: `(None, quality, name)` is a legal triple, and `chord_slots` emits
  exactly that shape.
- **Landed: a beat the melody skips *inside* a bar it occupies.** The union's exception used
  to be the **bar**, so a *named* grid already generated inside a bar the tune occupies:
  `synthetic_common_8` bar 4 (written onsets 1 and 3) yields **6** steps under `joe_pass`,
  sounding 1.5, 2.5, 3.5 and 4.5 — none of them written onsets — and bar 3 (onsets 1, 2, 3,
  4) yields **8** under the same grid on both routes. What the default lacked was positions
  of its own, and it has them now: **each bar is generated at its own subdivision**
  (`grid.grid_resolutions`, converted through the metre so no bar is generated finer than
  the sixteenth this library floors at), and the union takes those positions wherever the
  tune is **silent**. §9.2 still refuses a position the tune is *holding*, so a bar whose
  silence is a held note rather than a gap is a different claim.
  The candidates are measured rather than guessed: **153 positions** where no note is
  written are named by the default grid across the ten committed heads. Per head:
  `Trouble_in_Mind_Blues` 66, `synthetic_chords_only` 16, `synthetic_waltz` 20,
  `synthetic_repeat_slash` 12, `synthetic_common_8` 10, `synthetic_tab_export` 9,
  `synthetic_pickup_common` 8, `synthetic_cut_time` 7, `synthetic_pickup_cut` 3,
  `synthetic_triplets` 2. **25** of them become steps once §9.2 and the chord-in-force rule
  have spoken: `synthetic_chords_only` 16, `Trouble_in_Mind_Blues` 4,
  `synthetic_common_8` 3, `synthetic_repeat_slash` 1, `synthetic_waltz` 1, and nothing on
  the other five. The rest are a position the tune is still holding (the majority), one
  with no chord in force, or a position in a pickup bar.
- **Partly open: a stab's duration belongs to the producer that made the step, not to the
  grid.** `chord_slots` sets a length from the following **grid** position, capped at the
  barline, and `head_skeleton` from the **melody note**, and the union merges the two — so a
  *generated* position lasts until the next grid position while a *written* onset keeps the
  note's own length, shorter than that distance where the tune's own notes overlap and longer
  where the grid subdivides finer than the note. Measured with `parts=chord` under the default
  grid: all **16** of `synthetic_chords_only`'s steps match their own grid gap, while
  `synthetic_repeat_slash` has **1** of its 27 steps whose length differs from the distance
  to the next step: bar 5's G4, a written onset held across the following bar. (Bar 11's
  F4 is the last step, so it has no following gap to differ from.) `docs/history/comping-styles.md` §9.6's "the grid owns the
  rhythm" would give a written onset the grid's answer; nothing implements that for it, and
  §9.4 is where the axis that would own it is proposed.

**Why it exists.** The facade's input is triples plus timings, and the harmony is attached to a
melody note, so there is no position for a chord to sit on where the tune is silent. Closing it
means one of two changes, and they are not the same size: the facade accepting a **chord
timeline** in place of per-note harmony, or the facade generating the positions itself. The
importer took the second route; the first is the different order of change this item has named
from the start. That route needed no fifth `decisions.melody_alone_case` kind, which the item
predicted and §9.3 step D had already made unnecessary: it had made "a note-less grid position a
*singing* selection receives" a real case, and the comping branch answers it with
`MELODY_ALONE_NONE` — the grid decides whether the guitar is silent *about a chord it could
state*, and there it can.

**Landed.** `Head.chords` / `HeadChange` record the timeline as the document is walked;
`headxml.chord_at` queries it by forward fill; `headxml.chord_slots` yields one slot per position
the grid names; and `arrange_xml_head` unions them with `head_skeleton`'s for any selection that
voices chords (`comps+freddie`: `synthetic_cut_time` 21 → 23, `synthetic_repeat_slash` 30 → 35,
`synthetic_triplets` 112 → 112), plus the bar-level
`every_note` exception that closes the silence, **plus generated positions inside a bar the tune
occupies** (`headxml._generated_beats` and the position-level union in `_merge_chord_slots`). The
importer's route is therefore complete: of the positions the default grid names, only the ones
§9.2 refuses — a note still holding them — produce nothing, and a stab's own length follows the
producer that made the step rather than the grid (the bullet above).

**The rule it suggests.** A rhythm needs a source of its own. Where a grid's positions are
filtered out of the melody rather than generated from the metre, they vanish silently and no
warning can be issued, because the question was never asked. The position is the smallest unit at
which that silence was a defect; the level below it is where the *boundary* of §9.2's hold rule
decides, and item 6 is what that costs — a position on a note's release is declined along with a
position inside it.

---

## 2. A refused thumb note is usually not the shape being unplayable

**Status: diagnosed, not fixed — the decision is left open.** This is the question
[docs/history/fingering.md](history/fingering.md) §4.3 leaves hanging: whether the **selector** should have
left room for the thumb in the first place.

**The issue.** `place_bass` refuses a candidate and the step keeps its upper voicing.
`ArrangementStep.bass_refused` records the wanted pitch class and `annotation._bass_refusal_clause`
phrases it on the tab line, so the omission is reported on the part rather than in a collector.

**The problem.** Over the ten committed heads × the four rows that place a thumb note under a
texture that has one (`targets`/`uniform` × `root`/`root,5th,approach,nearest`; **674**
`place_bass` calls) refusals number **76** today. `targets` and `uniform` are the two textures
that carry a thumb line; the walk itself is the bass part's grid row rather than a texture, which
is why the rows are two textures × two rule sets. Attributed by cause:

| cause | refusals |
|---|---|
| no free string | **0** |
| **no octave of the walk's pitch below the shape** | **76** |
| five frets for four fingers | **0** |

The middle row is the common case, and it is the one the clause names — but note it is a
*replica* of `place_bass`'s three filters that names it, not the engine, because the field
carries the wanted pitch and not the reason it could not be placed. 49 of the 76 are a
*doubling*: the walk's pitch class is the shape's own bottom class an octave up, so the thumb
would restate what the chord already sounds. The other 27 are a pitch the shape has no octave of
beneath it.

**Why the levers do not pay.** All three filters are right, and dropping the note is deliberate
policy — a step is never dropped because the thumb could not reach it.

- **the walk's own pitch** is the fourth lever and costs the tuple nothing — it re-states the
  bass under the shape already chosen. Its payoff was measured on the retired corpus rather
  than re-taken here; what that measurement established is why the lever is not built: it
  recovers a fraction of the refusals, and the ones it recovers are the ones whose pitch is
  already a chord tone, which the shape sounds an octave up.
- **the shape-level retries** (re-select over hosting shapes, identical notes or any) are the
  other lever, and their numbers — 0 of 34 for the identical-notes retry, 10 of 53 on the tree
  it was first asked on, 48 of 53 for the bare one — are **not re-measured here**: the script
  was a throwaway (AGENTS.md trap 8), so those counts are about the trees they were taken on.
  What they established is why the lever is not built, and that part is independent of the
  count: **the harmless recovery is gone.** The ten hosts that sounded the chosen shape's own
  notes were the four inner-skip `drop24` sets, and §4.4 removed them for the right-hand reason,
  so every remaining recovery changes the harmony and pays the span bucket.

Not built, for the reason [docs/history/fingering.md](history/fingering.md) §4.4 reached for the finger skip:
the payoff is small, it changes what a downbeat states, and the current behaviour — drop the
note, keep the shape, report it — is defensible precisely because the chord already sounds that
pitch class an octave up.

---

## 3. `harmony=full` is accepted on the comping route and answered with a different family

**Status: open, diagnosed.**

**The issue.** `harmony=` is read only by the comping route, and `grips.get_comping_voicings`
implements the degree families it is handed through *arity* — the guide tones, or a lone bass
note. It has no implementation of `full` ("state every tone the quality defines"), because the
whole-chord chord-melody is the **grip** route's job, reached when the guitar sings. But
`harmony_allowed("full", ...)` returns True for every voice selection, so `resolve_harmony`
passes the value through and the comping generator voices guide tones anyway.

**The problem.** The same flag is *honoured* on the route that does not read it and *dropped* on
the route that does, and it is now the **only** value on this axis that does either silently:
`root` and `shell_root` **raise** `ValueError` when the voice selection has no room for them, so
a refusal on this axis is loud everywhere except here. Measured on
`[("D5","m7","Dm7"), ("C5","maj7","Cmaj7"), ("A4","7","A7"), ("G4","maj7","Gmaj7")]`,
`harmony=full` under `parts=chord` gives guide tones — byte-identical to the same
arrangement with no `harmony=` at all. It is the one value refused by nothing that resolves to
something other than itself, which is the failure `resolve_harmony`'s own docstring names.

**Why it exists / not fixed.** The fix is undecided and both directions are live: **refuse it**,
which weakens `harmony_allowed`'s "derived from arity" property (it would be the first entry not
derived), or **build it**, which is [docs/history/comping-styles.md](history/comping-styles.md) §9.4's four-note
comping chord — new string sets, deliberately not done. Recorded rather than fixed because it is
a behaviour change on an axis whose document still lists four-note comping as a proposal. The
*record* is now correct: `HARMONY_LENGTH` in `harmony.py` names the two families with a fixed
arity — `guide` (2) and `shell_root` (3) — and `full` is absent from it because its length is the
chord's own tone set, which varies by quality and lives in `TONE_PRIORITY`.

---

## 4. A `bass:` grid row is accepted and changes nothing

**Status: open, diagnosed.** The row spelling is validated; the row itself has no reader.

**The issue.** `grid=` is `PART:PATTERN` rows, and `GRID_PART_PATTERNS` offers three for the bass
part: `bass:every_note`, `bass:walk` and `bass:anchors`. All three parse, all three are allowed
by `grid_allowed`, and none of them changes a note. `grid_bass_pattern` is the function written to
read the row and **nothing calls it**: the walk's beats come from the bass *part* — `bass.py`'s
own timeline and the style's rules, unioned when a thumb line sounds — which is why the walk the
help text attributes to `bass:walk` already happens without it.

**The problem.** Measured over all ten committed heads, `texture=targets` with
`--bass-style root,5th,approach,nearest`: the default row and each of the three `bass:` rows give
**byte-identical steps**, same count and same tab lines on every head — 104, 16, 32, 13, 8, 35,
29, 57, 23, 112. So a caller who writes `--grid bass:walk` is handed exactly what a caller who wrote
nothing got, and nothing on the line says so. That is the failure this document exists for: a
spelling stating a choice the library did not make.

**Why it exists / not fixed.** The rows are part of the axis's vocabulary —
[docs/history/parts.md](history/parts.md) §7 step 5 fixes `grid=` as positions × parts — and `parse_grid`
validates them, so refusing them would be the axis rejecting a spelling it documents. What is
missing is the *reader*: building it moves the walk's positions off `bass.py`'s timeline and onto
the row, which changes the walked-beat union that item 2's figures are taken over. That is a
measured cost rather than an oversight, so the row is documented as inert
([README.md](../README.md)). No test re-takes the equality: item 4 is a **deferral** rather than
a behaviour worth asserting, and when the reader lands, the item and its row go together.

---

## 5. A lone note the hand holds can leave the walk below the shape's reach

**Status: diagnosed, not fixed — the lever is [docs/history/fingering.md](history/fingering.md) §4.3's question**,
and it is the same question item 2 leaves open, seen from the other side.

**The issue.** `place_bass` ranks the thumb's candidates by proximity to the hand but never
*bounds* the reach: a pitch with no position inside the hand's span is still played, because "a
step is never dropped because the thumb could not reach it". A `bass_only` step can therefore
sound a bass note several frets away from the shape the fingers are holding, with no nearer option
to take.

**The problem.** Measured over the ten committed heads × the walk row (`texture=targets`,
`bass=root,5th,approach,nearest`, `grid=melody:every_note,bass:walk`): the worst reach is **5**
(`synthetic_waltz`) and **1** step exceeds **4** frets — `synthetic_waltz` bar 11 beat 2 — and
**it is placed as near the hand as its own note allows**, which is what
`tests/test_bass_placement.py::TestTheThumbReachesTheHandHoldingTheShape.test_the_thumb_stays_within_reach_of_the_fingers`
now asserts instead of excusing. The wide reach is therefore the **walk's register**: the note the
line decided to play has no position nearer the held shape, and the placement took the nearest one
there is (`tests.support.nearest_reach_for_note` is the replica that says so, and the engine's own
choice must equal it). The note itself is chosen by the walk's own ordering — proximity first, then
continuity with the previous bass note, then the lower pitch (`bass_place.place_bass` spells the three
out) — so a register the hand can reach is not something the placement can fix.

The same sweep over `c5dde40` — before the lone-note placement landed, so with the tune's single
notes wherever the highest string put them — had a worst of **3** and none over 4. The reach did
not get worse on its own account: it got **visible** when a lone note started sitting where the
hand already is, because the walk's "below the shape" filter then leaves only a low octave. The
current case is `synthetic_waltz` bar 11: the held shape and the walk's note are five frets apart,
and no nearer position for that note survives the filters. The trade is stated in the same
commit's measurement: hand travel over the same row falls **3070 → 1728** frets.

**Why the levers do not pay** — the first is the *selector's* business and the second the
*walk's*, and neither is built:

- **leaving room for the thumb** is item 2's lever: re-select the upper shape so the bass can
  reach it. It changes what the step states for the walk's benefit, which is why it needed
  measuring rather than adopting (item 2's counts).
- **the walk's register** — playing the same pitch class an octave up, where the hand is — is the
  one lever that needs nothing from the selector, but it fights the line's own continuity: the
  third key of `place_bass`'s ordering only breaks a proximity tie, precisely so a walking bass
  does not leap octaves for no reason. Measured on the four cases above, every one of them is a
  register the hand would have to travel to.
- **refusing the note** would bound the reach at the cost of the note — the step above — and
  unlike the three existing filters it is not a playability *fact*: a bass note five frets below a
  held shape is playable, and it is the hand's span that suffers. Refusing it would legislate a
  stretch the library deliberately declines to define, which is the sentence that used to be the
  whole of this test's docstring.

---

## 6. A position falling on a note's release is not generated

**Status: open, diagnosed, and the boundary is pinned.** §9.2's hold rule is *inclusive* at its
edge, so the instant a note stops sounding is treated as one it still holds, and the grid declines
that position. The reading is a decision; the arithmetic that finds the edge is not, and it now
uses the head's own metre.

**The issue.** `melody_at` keeps a note in force while `position <= end`, where the position and
the end are both on one absolute beat line and the end is
`beat_offset(note.bar, note.beat, beats_per_bar) + duration * beat_type`. The test is
`if beat_offset(bar, beat, beats_per_bar) > round(end, 6): return None`, so the **end instant
itself** still returns the note. `melody_state` then answers `held` there rather than `silent`,
and §9.2's rule that a held position is not a slot declines it. A position where the tune has
*stopped* is therefore treated exactly like one where it is still sounding.

**The problem.** Positions the grid names produce nothing. Measured by patching that boundary
alone — a `held` answer whose in-force note ends at that exact position becomes `silent` — and
re-arranging all ten committed heads under the default grid: **9** steps are added, 334 → 343.
Per head: `Trouble_in_Mind_Blues` **+3**, `synthetic_cut_time` **+2**, `synthetic_triplets` **+2**,
`synthetic_common_8` **+1** and `synthetic_waltz` **+1**, with nothing on the other five.
`synthetic_common_8` bar 8 is the simplest shape of it: the last bar's downbeat is the release of
the tune's final note, so the position is reported `held` and the bar yields one step fewer than
the grid names.

**Why it exists.** Two readings of "sounds here" are both defensible and the code implements one
without recording which: a note covering `[onset, end]` sounds *through* its release, or it
sounds over `[onset, end)` and the release is already silence. The first is what is built, and
`tests/test_headxml_timeline.py::TestMelodyState::test_the_release_instant_counts_as_held_until_the_next_position`
pins it, so changing it is a decision rather than a drift. The distinction is musical rather than
clerical, because a comp on the release coincides with the note's own release — the chord beneath
it was decided where the note began, which is §9.2's own reason for declining a hold — while a
comping player reading the same bar sees a rest and strikes. Changing it is a decision, not a
repair, and it is **not** local: `bass._melody_in_force` asks the same question of the same
timeline, though it falls back to the note that most recently started where the score writes
silence, so it need not move with it.

---

## Reproducing

```bash
# 1. the bar-level rule: a bar the melody never enters, under the default grid
# `every_note` is melody-anchored and the union's exception is the BAR, so a bar the tune
# never enters is added beat for beat while every bar it does enter is untouched. Bar 6 of
# this head is the case the old behaviour got wrong: no notes at all, and two changes behind
# it. The head is written as 8 bars and *played* as 12, because the loader plays repeats.
.venv/bin/python -c "
from headxml import arrange_xml_head
steps, head, _notes = arrange_xml_head('tests/data/synthetic_repeat_slash.musicxml')
bars = sorted({s.bar for s in steps})
lo, hi = head.bars                     # (first, last + 1) - the file's measure extent
print('bars arranged:', len(bars), 'of', hi - lo)
print('bar 6 (no notes at all):', [(s.beat, s.chord) for s in steps if s.bar == 6])
"
# bars arranged: 11 of 12 - and bar 12 is not missing: bar 11's F4 is held through it,
# so a step that began in bar 11 sounds the bar. Bar 6 has no notes of its own, and its
# downbeat is held from bar 5, so the grid states only the position the tune has left:
# [(2.0, 'D9')] - it used to be absent entirely.

# the chords-only lead sheet: the extreme case, now arranged under the default grid
.venv/bin/python -c "
from headxml import arrange_xml_head
steps, _head, _notes = arrange_xml_head('tests/data/synthetic_chords_only.musicxml')
print('steps:', len(steps))   # 16 - four bars, four beats each
"
# and the one route still silent, which is a different claim:
.venv/bin/python -c "
from headxml import arrange_xml_head
steps, _head, _notes = arrange_xml_head('tests/data/synthetic_chords_only.musicxml', parts='melody')
print('steps:', len(steps))   # 0 - a melody-only selection has no tune to play
"

# the 36 candidates the bar-level rule names, over four heads: count the grid's positions
# in the bars `head_skeleton` never touched. Nothing is monkeypatched and no 'before' tree is
# needed - a bar the melody never enters contributes no melody slot, so every candidate in one
# is the union's. These are *candidates*: §9.2 and the chord-in-force rule decide how many
# become steps (the 25 in the bullet above).
.venv/bin/python -c "
import glob, os
import headxml as H
total = 0
for path in sorted(glob.glob('tests/data/*.musicxml')) + sorted(glob.glob('tests/data/*.mxl')):
    head = H.load_musicxml(path, None)
    melody_bars = {bar for _t, bar, _b, _d in H.head_skeleton(head, None)}
    added = [s for s in H.chord_slots(head, None, 'chord:every_note') if s[3] not in melody_bars]
    total += len(added)
    print('%-32s added=%d' % (os.path.basename(path), len(added)))
print('total added:', total)
"
# 12, 16, 4, 4 in the order the heads are read, and six zeros for the heads with no
# melody-less bar - 36 candidates across the corpus.

# what is still open, and now the item's whole remaining scope: the LIBRARY entry point
# takes its harmony per melody note, so a hand-built progression with no slot in bar 2
# cannot express one. The importer no longer shares this limit.
.venv/bin/python -c "
from arranger import VoiceLeadingEngine
prog = [('D5','m7','Dm7'), ('C5','maj7','Cmaj7'), ('E4','7','A7')]
timings = [(1,1.0,1.0), (1,2.0,1.0), (3,1.0,1.0), (3,2.0,1.0)]   # no slot in bar 2
steps = VoiceLeadingEngine.arrange_progression(
    prog, timings=timings, parts='chord', grid='chord:freddie',
    )
print('bar 2 present:', any(s.bar == 2 for s in steps))
print('Cmaj7 duration:', [s.duration for s in steps if s.chord == 'Cmaj7'])
"
# bar 2 present: False, and Cmaj7 is voiced once for the melody note's own duration -
# the caller supplies the slots, so this route needs generated slots to answer it.

# the walking bass: the same limit, only where the caller builds the timings by hand
.venv/bin/python -c "
from arranger.bass import bass_line_for
from arranger.chords import ChordParser
chords = [(ChordParser.parse_chord_name(n)[0], ChordParser.parse_chord_name(n)[1] or '', n)
          for _m, _q, n in [('D5','m7','Dm7'), ('C5','maj7','Cmaj7'), ('E4','7','A7')]]
line = bass_line_for('root,5th,approach,nearest', chords, [(1,1.0), (1,2.0), (3,1.0), (3,2.0)], 4)
print('bars walked:', sorted({n.bar for n in line}))
"
# bars walked: [1, 3]   <- on the head path the union supplies bar 2, so this is the
#                            library function called directly with hand-built timings.

# 4. a bass: grid row is inert: every head comes out byte-identical to the default row
.venv/bin/python -c "
import glob
import headxml as H
rows = ['melody:every_note', 'bass:every_note', 'bass:walk', 'bass:anchors']
heads = sorted(glob.glob('tests/data/*.musicxml')) + sorted(glob.glob('tests/data/*.mxl'))
same = 0
for path in heads:
    tabs = set()
    for grid in rows:
        steps, _h, _n = H.arrange_xml_head(
            path, texture='targets', bass='root,5th,approach,nearest', grid=grid)
        tabs.add(tuple(s.tab_line() for s in steps))
    same += len(tabs) == 1
print('inert rows: %d of %d heads identical' % (same, len(heads)))
"
# inert rows: 10 of 10 heads identical - and all four spellings give 83, 16, 32, 13, 8,
# 33, 28, 57, 23, 112 steps, so the row is a no-op rather than an accident of one head.

# 6. a position on a note's release is not generated: `melody_at` keeps a note in force
# through its own end instant, so `melody_state` answers held where the tune has already
# stopped and §9.2 declines the position. Patch only that boundary and re-arrange every head.
# The end is on one absolute beat line: `beat_offset` places the bar, and `beat_type` is how
# many beats a whole note spans.
.venv/bin/python -c "
import glob, os
import headxml as H
from arranger import beat_offset

original = H.melody_state

def at_release(head, bar, beat):
    state = original(head, bar, beat)
    if state != 'held':
        return state
    position = (bar, round(beat, 6))
    found = None
    for note in head.notes:
        if note.key > position:
            continue
        if found is None or note.key >= found.key:
            found = note
    if found is None:
        return state
    end = (
        beat_offset(found.bar, found.beat, head.beats_per_bar)
        + found.duration * head.beat_type
    )
    if abs(beat_offset(bar, beat, head.beats_per_bar) - end) < 1e-9:
        return 'silent'
    return state

def arrange(path):
    return H.arrange_xml_head(path)[0]

paths = sorted(glob.glob('tests/data/*.musicxml')) + sorted(glob.glob('tests/data/*.mxl'))
total = 0
for path in paths:
    before = arrange(path)
    H.melody_state = at_release
    after = arrange(path)
    H.melody_state = original
    total += len(after) - len(before)
    print('%-40s %+d' % (os.path.basename(path), len(after) - len(before)))
print('added: %d over %d heads' % (total, len(paths)))
"
# Trouble_in_Mind_Blues +3, synthetic_cut_time +2, synthetic_triplets +2,
# synthetic_common_8 +1, synthetic_waltz +1 and the other five 0 -
# and `added: 9 over 10 heads`, which is 334 steps becoming 343. The two readings of sounds
# here are both defensible; what the patch cannot say is which one the library should hold.
```


Item 2's counts are re-measured the same way (no committed script — `AGENTS.md` trap 8): wrap
`bass_place.place_bass` and `bass_merge._attach_bass`, load each `tests/data/` head over the four rows
that place a thumb note under a texture that has one (`texture` in `targets`/`uniform` ×
`bass` in `root`/`root,5th,approach,nearest`), and count a refusal wherever `place_bass` returns `None`.

Naming the *cause* needs a replica of `place_bass`'s three filters rather than a reading of the
step, and that is a limitation worth stating: `ArrangementStep.bass_refused` carries the wanted
pitch class, not the reason it could not be placed. Rebuild the free-string set, the octaves of
the wanted pitch below the shape's own lowest note, and the `fingers.can_fret` four-fret budget,
in that order, and the first of the three that comes back empty is the cause. The replica is
validated by agreement rather than by inspection — over all 674 calls it agrees with the real
`place_bass` on every outcome, which is what makes the `0 / 76 / 0` split a measurement and not
a description of the code. Recording the cause on the field would remove the replica; that is a
change to the engine, not to this document.
