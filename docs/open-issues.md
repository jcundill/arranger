# Open issues

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it. A fixed issue is **removed** from this file rather than kept as history —
its record lives in the commit that fixed it and in the document it belongs to. Three are open,
one of them partly fixed:

1. **A chord in force is stored per melody note, so a bar the melody skips is silent** — the
   **bar-level** half is fixed and only generated slots are owed, at the level below the bar.
2. **A refused thumb note is usually not the shape being unplayable** — measured, decision left
   open: the selector's lever recovers nothing harmlessly any more, and the walk's own pitch,
   which costs the tuple nothing, reaches 93 of the 161 refusals but only 64 of them by a chord
   tone.
3. **`harmony=full` is accepted on the comping route and answered with a different family** — the
   one axis value refused by nothing that resolves to something other than itself.

Reproduce the measurements with the commands in [Reproducing](#reproducing).

---

## 1. A chord in force is stored per melody note, so a bar the melody skips is silent

**Status: the bar-level defect is fixed; the beat-level one is deferred by decision.** A bar
the melody never enters is now arranged under every route that voices chords, including the
default grid. What is still owed is **generated slots** — beats *inside* a bar the melody
does occupy, and rests as time rather than skipped elements.

**The issue.** Harmony is stored *per melody note*, not per time position. There is no
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
- **Still open: a beat the melody skips *inside* a bar it occupies — under `every_note`
  only.** The union's exception is the **bar**, so a *named* grid already generates
  inside a bar the tune occupies: `All_the_Things_You_Are` bar 4 (onsets 1, 2, 4) yields
  7 steps under `joe_pass`, sounding 1.5, 2.5 and 3.5 — none of them written onsets — and
  bar 3 (onsets 1, 2, 3, 4) yields 8 under the same grid on both routes. What is still
  owed is the **default**, whose exception excludes every position of a melody-bearing
  bar: the same bar 4 yields 3 steps under `every_note` and beat 3 is absent. Closing it
  needs **generated slots**. The size of the change is measured rather than guessed: the
  positions `every_note` names inside melody bars across the eight heads total **347**,
  of which **192** fall where a note is still *held* — and §9.2 forbids reharmonising
  under a hold, because the note was already harmonised where it began — leaving **155**
  silent positions that generating would actually add. That 155 is the number the
  fifth `melody_alone_case` kind has to be designed against.
- **Still open: a stab's duration on the comping route.** `chord_slots` computes a length from
  the following grid position and `head_skeleton` from the melody note, but no axis decides
  which a *comping* step obeys. It is `docs/comping-styles.md` §9.4's business, and it is the
  fifth `melody_alone_case` kind that item predicts.

**Why the rest exists.** Closing it means slots a grid position can *create*, which changes
three things: `head_skeleton` (rests become time rather than skipped elements, and it must emit
chord slots as well as note slots), `ArrangementStep.melody` (`None` where no note sounds — the
field half is done), and `decisions.melody_alone_case` (an invented slot has no note to be alone
*with*, so its `kind` vocabulary needs a fifth value). That is a different order of change: a
harmonisation engine whose input is a **chord timeline**, not a list of melody notes.

**Landed.** `Head.chords` / `HeadChange` record the timeline as the document is walked;
`headxml.chord_at` queries it by forward fill; `headxml.chord_slots` yields one slot per position
the grid names; and `arrange_xml_head` unions them with `head_skeleton`'s for any selection that
voices chords (`comps+freddie`: `but_not_for_me` 80 → 102, `heres_that_rainy_day` 180 → 206,
`i_was_doing_all_right` 224 → 246 — the first is the figure this paragraph has always carried,
and the other two lengthened when the repeats started being played), **plus the bar-level
`every_note` exception** that closes the silence. A stab's duration is now the grid's, capped at
the barline. Still owed: generated slots, and the `melody_alone_case` kind.

**The rule it suggests.** A rhythm needs a source of its own. Where a grid's positions are
filtered out of the melody rather than generated from the metre, they vanish silently and no
warning can be issued, because the question was never asked. The bar is the largest unit for
which that silence was a defect; below it, deferring to the melody is the documented decision.

---

## 2. A refused thumb note is usually not the shape being unplayable

**Status: diagnosed, not fixed — the decision is left open.** This is the question
[docs/fingering.md](fingering.md) §4.3 leaves hanging: whether the **selector** should have
left room for the thumb in the first place.

**The issue.** `_place_bass` refuses a candidate and the step keeps its upper voicing.
`ArrangementStep.bass_refused` records the wanted pitch class and `render._bass_refusal_clause`
phrases it on the tab line, so the omission is reported on the part rather than in a collector.

**The problem.** Over the eight committed heads × the four rows that place a thumb note under a
texture that has one (`targets`/`walking_bass` × `root`/`root,5th,approach,nearest`; 2,624 `_place_bass` calls)
refusals number **161** today. The chain, every step re-measured on that same row set: **53** at
`d9403e5` (seven heads, 1,500 calls), **39** at `246ff69`, **131** at `5f4a5e1` (the eighth
fixture arrives), and **161** from `574d666` on — playing the repeats (`6cdcbaa`) lengthened the
heads, which is where most of the last jump comes from. Attributed by cause:

| cause | refusals |
|---|---|
| no free string | **0** |
| **no octave of the walk's pitch below the shape** | **160** |
| five frets for four fingers | **1** |

The middle row is the common case, and it is the one the clause names — but note it is a
*replica* of `_place_bass`'s three filters that names it, not the engine, because the field
carries the wanted pitch and not the reason it could not be placed. 92 of the 161 are a
*doubling*: the walk's pitch class is the shape's own bottom class an octave up, so the thumb
would restate what the chord already sounds. The other 69 are a pitch the shape has no octave of
beneath it.

**Why the levers do not pay.** All three filters are right, and dropping the note is deliberate
policy — a step is never dropped because the thumb could not reach it.

- **the walk's own pitch** is the fourth lever and costs the tuple nothing — it re-states the
  bass under the shape already chosen — but reaches **93 of the 161**, and only **64** of those
  by a chord tone (`Cm7` 22, `Dm7` 20, `Db9` 12, `D7` 4, `G7` 2, `Eb7` 2, `C7` 2 — seven chords
  across six heads, not the one chord and one bar this used to say). **68 of the 161** cannot be
  helped by any pitch at all.
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
`harmony=full` under `melody=alto,tenor` gives guide tones — byte-identical to the same
arrangement with no `harmony=` at all. It is the one value refused by nothing that resolves to
something other than itself, which is the failure `resolve_harmony`'s own docstring names.

**Why it exists / not fixed.** The fix is undecided and both directions are live: **refuse it**,
which weakens `harmony_allowed`'s "derived from arity" property (it would be the first entry not
derived), or **build it**, which is [docs/comping-styles.md](comping-styles.md) §9.4's four-note
comping chord — new string sets, deliberately not done. Recorded rather than fixed because it is
a behaviour change on an axis whose document still lists four-note comping as a proposal. The
*record* is now correct: `HARMONY_BUILT` names `guide`, `shell_root` and `root`, and `full` is
not among them.

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
steps, _head, _notes = arrange_xml_head('tests/data/lead_sheet_chords_only.musicxml', melody='soprano')
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
    added = [s for s in H.chord_slots(head, None, 'every_note') if s[3] not in melody_bars]
    total += len(added)
    print('%-32s added=%d' % (os.path.basename(path), len(added)))
print('total added:', total)
"
# 12, 21, 12, 20, 16, 0, 0, 6 in that order - 87 across six heads, and the two zeros are the
# heads with no melody-less bar. Measured at `5f4a5e1` the same count is 73, because the
# repeats were not yet played; this figure is about this tree.

# what is still open, at the level below the bar: the LIBRARY entry point takes its
# harmony per melody note, so a hand-built progression with no slot in bar 2 cannot
# express one. The importer no longer shares this limit.
.venv/bin/python -c "
from arranger import VoiceLeadingEngine
prog = [('D5','m7','Dm7'), ('C5','maj7','Cmaj7'), ('E4','7','A7')]
timings = [(1,1.0,1.0), (1,2.0,1.0), (3,1.0,1.0), (3,2.0,1.0)]   # no slot in bar 2
steps = VoiceLeadingEngine.arrange_progression(
    prog, timings=timings, melody='alto,tenor', grid='freddie',
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
```


Item 2's counts are re-measured the same way (no committed script — `AGENTS.md` trap 8): wrap
`bass._place_bass` and `movement._attach_bass`, load each `tests/data/` head over the four rows
that place a thumb note under a texture that has one (`texture` in `targets`/`walking_bass` ×
`bass` in `anchors`/`walk`), and count a refusal wherever `_place_bass` returns `None`.

Naming the *cause* needs a replica of `_place_bass`'s three filters rather than a reading of the
step, and that is a limitation worth stating: `ArrangementStep.bass_refused` carries the wanted
pitch class, not the reason it could not be placed. Rebuild the free-string set, the octaves of
the wanted pitch below the shape's own lowest note, and the `fingers.can_fret` four-fret budget,
in that order, and the first of the three that comes back empty is the cause. The replica is
validated by agreement rather than by inspection — over all 2,624 calls it agrees with the real
`_place_bass` on every outcome, which is what makes the `0 / 160 / 1` split a measurement and not
a description of the code. Recording the cause on the field would remove the replica; that is a
change to the engine, not to this document.
