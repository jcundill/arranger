# Open issues

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it. A fixed issue is **removed** from this file rather than kept as history —
its record lives in the commit that fixed it and in the document it belongs to. Six are open, and
each figure is stated **once**, in its own item: a summary here would be a second source for it,
which is how the numbers in this paragraph rotted three times before the *recipes* below were
made explicit. **Every figure in this file is re-measured by hand from the recipe beside it**:
they are this document's own business, and nothing in the test suite compares them with these
sentences. What the gate does run is the *behaviour* each item describes, in
`tests/test_open_issues.py`.

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
   holding; measured, and nothing pins the boundary.

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
  `head_skeleton` never touched, so `lead_sheet_chords_only` now arranges **16 steps** under
  every grid, and **87 steps** were added across six of the eight committed heads. Per head:
  `All_the_Things_You_Are` 12, `The_Jitterbug_Waltz` 21, `Trouble_in_Mind_Blues` 12,
  `heres_that_rainy_day` 20, `lead_sheet_chords_only` 16, `i_was_doing_all_right` 6. The two
  with no melody-less bar (`tenor_madness`, `but_not_for_me`) are untouched, which is what
  keeps the change a fix rather than a behaviour change.
- ~~A chords-only lead sheet is silent on every export path~~ — **fixed.** It arranges all
  four bars under the default grid and 16 under `freddie`. The one route still silent is a
  **melody-only selection** (`soprano`, `soprano,bass`), which is a different claim: it plays
  the tune and nothing else, and there is no tune.
- ~~The walking bass shares the limit one level down~~ — **was already fixed wherever a named
  grid ran**, and the default grid's silence was the only thing withholding the bar from it.
  `_walking_slots` walks the bars the *timings* touch, and the union writes its added slots
  into those timings, so the default now reaches **exactly** the bars `freddie` reaches.
- ~~The case is structurally inexpressible~~ — **the field half was already done** before this
  item was last measured: `(None, quality, name)` is a legal triple, and `chord_slots` emits
  exactly that shape.
- **Landed: a beat the melody skips *inside* a bar it occupies.** The union's exception used
  to be the **bar**, so a *named* grid already generated inside a bar the tune occupies:
  `All_the_Things_You_Are` bar 4 (onsets 1, 2, 4) yields
  7 steps under `joe_pass`, sounding 1.5, 2.5 and 3.5 — none of them written onsets — and
  bar 3 (onsets 1, 2, 3, 4) yields 8 under the same grid on both routes. What the default
  lacked was positions of its own, and it has them now: **each bar is generated at its own
  subdivision** (`textures.grid_resolutions`, converted through the metre so no bar is
  generated finer than the sixteenth this library floors at), and the union takes those
  positions wherever the tune is **silent**. §9.2 still refuses a position the tune is
  *holding*, and that is why bar 4 of that head is unchanged under `every_note`: its beat 3
  is a held `C5` rather than a gap, so the absence there is a different claim from the one
  this item made. **bar 16** of the same head is the case the old exception excluded and the
  new rule fills — the tune enters on beat 2, so its downbeat is silent and now carries a
  chord.
  The change is measured rather than guessed: **88 steps** across the eight heads
  (`All_the_Things_You_Are` +4, `The_Jitterbug_Waltz` +11, `Trouble_in_Mind_Blues` +31,
  `tenor_madness` +28, `but_not_for_me` +14, and nothing on `heres_that_rainy_day`,
  `i_was_doing_all_right` or `lead_sheet_chords_only`, whose tunes are continuous and so
  hold every position inside their own bars). The sizing this bullet used to carry read
  **347** positions named / **192** held / **155** owed; restricted to the melody-bearing
  bars its own sentence claimed it is **260** / **192** / **68**, and the difference is the
  87 positions the bar-level fix above had *already* added — counted a second time.
- **Partly open: a stab's duration belongs to the producer that made the step, not to the
  grid.** `chord_slots` sets a length from the following **grid** position, capped at the
  barline, and `head_skeleton` from the **melody note**, and the union merges the two — so a
  *generated* position lasts until the next grid position while a *written* onset keeps the
  note's own length, shorter than that distance where the tune's own notes overlap and longer
  where the grid subdivides finer than the note. Measured with `parts=chord` under the default
  grid: all **16** of `lead_sheet_chords_only`'s steps match their own grid gap, while
  `heres_that_rainy_day` has **104** steps whose length differs from the distance to the next
  step, every one of them a written onset. `docs/comping-styles.md` §9.6's "the grid owns the
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
voices chords (`comps+freddie`: `but_not_for_me` 80 → 102, `heres_that_rainy_day` 180 → 206,
`i_was_doing_all_right` 224 → 246 — the first is the figure this paragraph has always carried,
and the other two lengthened when the repeats started being played), plus the bar-level
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
[docs/fingering.md](fingering.md) §4.3 leaves hanging: whether the **selector** should have
left room for the thumb in the first place.

**The issue.** `_place_bass` refuses a candidate and the step keeps its upper voicing.
`ArrangementStep.bass_refused` records the wanted pitch class and `render._bass_refusal_clause`
phrases it on the tab line, so the omission is reported on the part rather than in a collector.

**The problem.** Over the eight committed heads × the four rows that place a thumb note under a
texture that has one (`targets`/`uniform` × `root`/`root,5th,approach,nearest`; 2,624
`_place_bass` calls) refusals number **220** today. `targets` and `uniform` are the two textures
that carry a thumb line; the walk itself is the bass part's grid row rather than a texture, which
is why the rows are two textures × two rule sets rather than the old `targets`/`walking_bass` pair.
The chain's earlier points were taken over that old pair, so they are not comparable with today's
figure: **53** at `d9403e5` (seven heads, 1,500 calls), **39** at `246ff69`, **131** at `5f4a5e1`
(the eighth fixture arrives), **161** from `574d666` on — playing the repeats (`6cdcbaa`)
lengthened the heads, which is where most of that jump came from — and **222** once the lone-note
placement landed (below), which moved every shape a lone note sits under. **220** is the current
figure, and item 1's generated positions moved it: they add steps, which changes which shape a
lone note sits under again. Attributed by cause:

| cause | refusals |
|---|---|
| no free string | **0** |
| **no octave of the walk's pitch below the shape** | **220** |
| five frets for four fingers | **0** |

The middle row is the common case, and it is the one the clause names — but note it is a
*replica* of `_place_bass`'s three filters that names it, not the engine, because the field
carries the wanted pitch and not the reason it could not be placed. 98 of the 220 are a
*doubling*: the walk's pitch class is the shape's own bottom class an octave up, so the thumb
would restate what the chord already sounds. The other 122 are a pitch the shape has no octave of
beneath it.

**Why the levers do not pay.** All three filters are right, and dropping the note is deliberate
policy — a step is never dropped because the thumb could not reach it.

- **the walk's own pitch** is the fourth lever and costs the tuple nothing — it re-states the
  bass under the shape already chosen — but reaches **144 of the 220**, and only **105** of those
  by a chord tone (`Eb7` 22, `Cm7` 20, `Dm7` 20, `Abmaj7` 9, `D7` 6, `Am7` 6, `Eb6` 4,
  `Gm7` 4, `G7` 4, `Ebmaj7` 4, `Cmaj7` 2, `Bb7` 2, `Db9` 2 — thirteen chords, not the one chord
  and one bar this used to say). **76 of the 220** cannot be helped by any pitch at all.
- **the shape-level retries** (re-select over hosting shapes, identical notes or any) are the
  other lever, and their numbers — 0 of 34 for the identical-notes retry, 10 of 53 on the tree
  it was first asked on, 48 of 53 for the bare one — are **not re-measured here**: the script
  was a throwaway (AGENTS.md trap 8), so those counts are about the trees they were taken on.
  What they established is why the lever is not built, and that part is independent of the
  count: **the harmless recovery is gone.** The ten hosts that sounded the chosen shape's own
  notes were the four inner-skip `drop24` sets, and §4.4 removed them for the right-hand reason,
  so every remaining recovery changes the harmony and pays the span bucket.

Not built, for the reason [docs/fingering.md](fingering.md) §4.4 reached for the finger skip:
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
derived), or **build it**, which is [docs/comping-styles.md](comping-styles.md) §9.4's four-note
comping chord — new string sets, deliberately not done. Recorded rather than fixed because it is
a behaviour change on an axis whose document still lists four-note comping as a proposal. The
*record* is now correct: `HARMONY_LENGTH` in `textures.py` names the two families with a fixed
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

**The problem.** Measured over all eight committed heads, `texture=targets` with
`--bass-style root,5th,approach,nearest`: the default row and each of the three `bass:` rows give
**byte-identical steps**, same count and same tab lines on every head — 150, 297, 90, 206, 16,
256, 102, 246. So a caller who writes `--grid bass:walk` is handed exactly what a caller who wrote
nothing got, and nothing on the line says so. That is the failure this document exists for: a
spelling stating a choice the library did not make.

**Why it exists / not fixed.** The rows are part of the axis's vocabulary —
[docs/parts.md](parts.md) §7 step 5 fixes `grid=` as positions × parts — and `parse_grid`
validates them, so refusing them would be the axis rejecting a spelling it documents. What is
missing is the *reader*: building it moves the walk's positions off `bass.py`'s timeline and onto
the row, which changes the walked-beat union that item 2's figures are taken over. That is a
measured cost rather than an oversight, so the row is documented as inert
([README.md](../README.md)). No test re-takes the equality: item 4 is a **deferral** rather than
a behaviour worth asserting, and when the reader lands, the item and its row go together.

---

## 5. A lone note the hand holds can leave the walk below the shape's reach

**Status: diagnosed, not fixed — the lever is [docs/fingering.md](fingering.md) §4.3's question**,
and it is the same question item 2 leaves open, seen from the other side.

**The issue.** `_place_bass` ranks the thumb's candidates by proximity to the hand but never
*bounds* the reach: a pitch with no position inside the hand's span is still played, because "a
step is never dropped because the thumb could not reach it". A `bass_only` step can therefore
sound a bass note several frets away from the shape the fingers are holding, with no nearer option
to take.

**The problem.** Measured over the eight committed heads × the walk row (`texture=targets`,
`bass=root,5th,approach,nearest`, `grid=melody:every_note,bass:walk`): the worst reach is **7**
(`i_was_doing_all_right`) and **6** steps exceed **4** frets — 2 in `i_was_doing_all_right`,
2 in `The_Jitterbug_Waltz`, 1 in `All_the_Things_You_Are`, 1 in `but_not_for_me` — and
**every one of those six is placed as near the hand as its own note allows**, which is what
`tests/test_walking_bass.py::TestTheThumbReachesTheHandHoldingTheShape.test_the_thumb_stays_within_reach_of_the_fingers`
now asserts instead of excusing. The wide reach is therefore the **walk's register**: the note the
line decided to play has no position nearer the held shape, and the placement took the nearest one
there is (`tests.support.nearest_reach_for_note` is the replica that says so, and the engine's own
choice must equal it). The note itself is chosen by the walk's own ordering — proximity first, then
continuity with the previous bass note, then the lower pitch (`bass._place_bass` spells the three
out) — so a register the hand can reach is not something the placement can fix.

The same sweep over `c5dde40` — before the lone-note placement landed, so with the tune's single
notes wherever the highest string put them — had a worst of **3** and none over 4. The reach did
not get worse on its own account: it got **visible** when a lone note started sitting where the
hand already is, because the walk's "below the shape" filter then leaves only a low octave. The
case is `but_not_for_me` bar 30: the tune holds frets 11-13 and the walk wants an A2 whose only
free string is the low E at fret 5, six frets below. The trade is stated in the same commit's
measurement: hand travel over the same row falls **3070 → 1728** frets.

**Why the levers do not pay** — the first is the *selector's* business and the second the
*walk's*, and neither is built:

- **leaving room for the thumb** is item 2's lever: re-select the upper shape so the bass can
  reach it. It changes what the step states for the walk's benefit, which is why it needed
  measuring rather than adopting (item 2's counts).
- **the walk's register** — playing the same pitch class an octave up, where the hand is — is the
  one lever that needs nothing from the selector, but it fights the line's own continuity: the
  third key of `_place_bass`'s ordering only breaks a proximity tie, precisely so a walking bass
  does not leap octaves for no reason. Measured on the four cases above, every one of them is a
  register the hand would have to travel to.
- **refusing the note** would bound the reach at the cost of the note — the 4 steps above — and
  unlike the three existing filters it is not a playability *fact*: a bass note five frets below a
  held shape is playable, and it is the hand's span that suffers. Refusing it would legislate a
  stretch the library deliberately declines to define, which is the sentence that used to be the
  whole of this test's docstring.

---

## 6. A position falling on a note's release is not generated

**Status: open, diagnosed.** §9.2's hold rule is *inclusive* at its edge, so the instant a note
stops sounding is treated as one it still holds, and the grid declines that position.

**The issue.** `melody_at` keeps a note in force while `position <= onset + duration * 4` — the
test is `if position > (found.bar, round(end_beat, 6)): return None`, so the **end instant
itself** still returns the note. `melody_state` then answers `held` there rather than `silent`,
and §9.2's rule that a held position is not a slot declines it. A position where the tune has
*stopped* is therefore treated exactly like one where it is still sounding.

**The problem.** Positions the grid names produce nothing. Measured by patching that boundary
alone — a `held` answer whose exact beat is some note's end becomes `silent` — and re-arranging
all eight committed heads under the default grid: **57** steps are added, 1191 → 1248. Per head
`i_was_doing_all_right` **+42**, `heres_that_rainy_day` **+14** and `tenor_madness` **+1**, with
nothing on the other five. `tenor_madness` bar 1 is the whole shape of it: quarter notes on
beats 1 and 2, so beat 3 is reported `held` although the second note ended there, and the bar
yields 3 steps where the grid names 4.

**Why it exists.** Two readings of "sounds here" are both defensible and the code implements one
without recording which: a note covering `[onset, end]` sounds *through* its release, or it
sounds over `[onset, end)` and the release is already silence. The first is what is built. The
distinction is musical rather than clerical, because a comp on the release coincides with the
note's own release — the chord beneath it was decided where the note began, which is §9.2's own
reason for declining a hold — while a comping player reading the same bar sees a rest and
strikes. Changing it is a decision, not a repair, and it is **not** local: `bass._melody_in_force`
asks the same question of the same timeline, though it falls back to the note that most recently
started where the score writes silence, so it need not move with it. Nothing pins the boundary
today — the tests probe a note's *midpoint* rather than its end — which is why the figure and the
test are what this item lands first.

---

## Reproducing

```bash
# 1. the bar-level rule: a bar the melody never enters, under the default grid
# `every_note` is melody-anchored and the union's exception is the BAR, so a bar the tune
# never enters is added beat for beat while every bar it does enter is untouched. Bar 32 of
# this head is the case the old behaviour got wrong: no notes at all, and two changes behind
# it. The head is written as 36 bars and *played* as 66, because the loader plays repeats.
.venv/bin/python -c "
from headxml import arrange_xml_head
steps, head, _notes = arrange_xml_head('tests/data/heres_that_rainy_day.musicxml')
bars = sorted({s.bar for s in steps})
lo, hi = head.bars                     # (first, last + 1) - the file's measure extent
print('bars arranged:', len(bars), 'of', hi - lo)
print('bar 32 (no notes at all):', [(s.beat, s.chord) for s in steps if s.bar == 32])
"
# bars arranged: 66 of 66, and bar 32 sounds Am7 then D9 - it used to be absent entirely.

# the chords-only lead sheet: the extreme case, now arranged under the default grid
.venv/bin/python -c "
from headxml import arrange_xml_head
steps, _head, _notes = arrange_xml_head('tests/data/lead_sheet_chords_only.musicxml')
print('steps:', len(steps))   # 16 - four bars, four beats each
"
# and the one route still silent, which is a different claim:
.venv/bin/python -c "
from headxml import arrange_xml_head
steps, _head, _notes = arrange_xml_head('tests/data/lead_sheet_chords_only.musicxml', parts='melody')
print('steps:', len(steps))   # 0 - a melody-only selection has no tune to play
"

# the 87 across six heads: count the slots the union adds, i.e. the grid's positions in the
# bars `head_skeleton` never touched. Nothing is monkeypatched and no 'before' tree is needed -
# a bar the melody never enters contributes no melody slot, so every slot in one is the union's.
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
# 12, 21, 12, 20, 16, 0, 0, 6 in that order - 87 across six heads, and the two zeros are the
# heads with no melody-less bar. Measured at `5f4a5e1` the same count is 73, because the
# repeats were not yet played; this figure is about this tree.

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
# inert rows: 8 of 8 heads identical - and all four spellings give 150, 297, 90, 206, 16,
# 256, 102, 246 steps, so the row is a no-op rather than an accident of one head.

# 6. a position on a note's release is not generated: `melody_at` keeps a note in force
# through its own end instant, so `melody_state` answers held where the tune has already
# stopped and §9.2 declines the position. Patch only that boundary and re-arrange every head:
.venv/bin/python -c "
import contextlib, glob, io, os
import headxml as H

original = H.melody_state

def at_release(notes, bar, beat):
    state = original(notes, bar, beat)
    if state != 'held':
        return state
    for note in notes:
        if note.bar == bar and abs(note.beat + note.duration * 4 - beat) < 1e-9:
            return 'silent'
    return state

def arrange(path):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
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
# i_was_doing_all_right +42, heres_that_rainy_day +14, tenor_madness +1 and the other five 0 -
# and `added: 57 over 8 heads`, which is 1191 steps becoming 1248. The two readings of sounds
# here are both defensible; what the patch cannot say is which one the library should hold.
```


Item 2's counts are re-measured the same way (no committed script — `AGENTS.md` trap 8): wrap
`bass._place_bass` and `movement._attach_bass`, load each `tests/data/` head over the four rows
that place a thumb note under a texture that has one (`texture` in `targets`/`uniform` ×
`bass` in `root`/`root,5th,approach,nearest`), and count a refusal wherever `_place_bass` returns `None`.

Naming the *cause* needs a replica of `_place_bass`'s three filters rather than a reading of the
step, and that is a limitation worth stating: `ArrangementStep.bass_refused` carries the wanted
pitch class, not the reason it could not be placed. Rebuild the free-string set, the octaves of
the wanted pitch below the shape's own lowest note, and the `fingers.can_fret` four-fret budget,
in that order, and the first of the three that comes back empty is the cause. The replica is
validated by agreement rather than by inspection — over all 2,624 calls it agrees with the real
`_place_bass` on every outcome, which is what makes the `0 / 220 / 0` split a measurement and not
a description of the code. Recording the cause on the field would remove the replica; that is a
change to the engine, not to this document.
