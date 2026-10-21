# Open issues

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it. A fixed issue is **removed** from this file rather than kept as history —
its record lives in the commit that fixed it and in the document it belongs to. **One exception,
stated so it is not a silent one:** items 1 and 4 are closed **in place** with their numbers,
because `docs/history/` is frozen and cites items by number — removing them and renumbering would
silently repoint about fifty references at a different item, which is the contradiction between
documents this project treats as a bug. A closed item says how it closed and carries no figure of
its own.

Four are open, and each figure is stated **once**, in its own item: a summary here would be a
second source for it, which is how the numbers in this paragraph rotted three times before the
*recipes* below were made explicit. **Every figure in this file is re-measured by hand from the
recipe beside it**: they are this document's own business, and the gate is not keyed to these
items.

1. *(closed)* **The library facade takes its harmony per melody note** — closed by the
   rhythm-first request; see below.
2. **A refused thumb note is usually not the shape being unplayable** — measured, decision left
   open: the selector's lever recovers nothing harmlessly any more, and the walk's own pitch,
   which costs the tuple nothing, reaches most of the refusals but only a fraction of them by a
   chord tone.
3. **`harmony=full` is accepted on the comping route and answered with a different family** — the
   one axis value refused by nothing that resolves to something other than itself.
4. *(closed)* **A `bass:` grid row is accepted and changes nothing** — closed by the request; the
   internal row survives with its own tests.
5. **A lone note the hand holds can leave the walk below the shape's reach** — the reach is as
   near as the walk's own note allows, so it is the register and not the placement; measured,
   with the selector-side lever left unbuilt.
6. **A position falling on a note's release is not generated** — `melody_at` keeps a note in
   force through its end instant, so §9.2 declines a position the tune has already stopped
   holding; measured, and the boundary is pinned by a test while the reading stays open.

Reproduce the measurements with the commands in [Reproducing](#reproducing).

---

## 1. The library facade takes its harmony per melody note (closed)

**Closed by the rhythm-first request** ([rhythm-request-redesign.md](rhythm-request-redesign.md)).
The item had two open halves and both now have an answer rather than a workaround.

**The entry point.** A caller *can* place a chord where the tune is silent, and always could:
`(None, quality, name)` is a legal triple, and giving it its own `(bar, beat, duration)` puts a
chord at that position with no melody above it. That is the same shape `headxml.head_skeleton`
emits for a note-less slot, so the hand-built path and the imported one are one path -
`movement.arrange_progression` needs no second input type.

**The generation.** What was genuinely missing was a *source* of positions, and it is the request
now: `--chord-on` names them (`1&`, `every-beat`, a list), `--chord-fills` places chords in the
tune's notated rests, and `headxml.rhythm_slots` / `fill_slots` emit one triple per position with
`melody=None`. The default grid's union is gone with the flag that exposed it, so nothing invents
a position nobody asked for.

**The duration.** The item's last open bullet was that "a stab's duration belongs to the producer
that made the step". It has one rule now, and the rule is the request's: a position the chord
rhythm names lasts to the end of the **felt beat** it sits in (`headxml._stab_length`), and a
chord under a melody onset lasts that note. `ArrangementStep.duration` is a **cap** in the score
(`tabscore._capped_span`), so a stab shorter than the gap is written as a note and a rest rather
than a chord ringing over beats nothing asked for. `tests/test_durations.py` pins all four cases.

The importer's half remains as it was: `Head.chords` / `HeadChange` / `chord_at` are the timeline,
and every position the request names resolves through them.

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

## 4. A `bass:` grid row is accepted and changes nothing (closed)

**Closed for a caller, and kept internal on purpose.** The bug was never the row: it was that the
CLI offered a flag whose `bass:` half did nothing, so `--grid melody:every_note,bass:walk` printed
a request back and then wrote no bass note. That flag is gone. The thumb's positions are
`--bass-on` and its notes are `--bass-notes`, so the spelling that could lie to a user no longer
exists.

**The internal row survives, and is deliberately unread.** `GRID_PART_PATTERNS` still validates
`bass:every_note`, `bass:walk` and `bass:anchors`, and `grid_bass_pattern` still has no caller. It
is kept because it is the axis's own vocabulary - `parts=` / `grid=` are the Python API under the
request (design principle 9 of the plan) - and because `tests/test_grid.py` pins the property the
row exists to state: a bass row **defers to the melody**, since the walk's beats come from
`bass.py`'s own timeline rather than from a preset. A row that is parsed-but-unread *inside* the
engine, with a test saying so, is not the failure this document is for; a flag that states a choice
the library did not make is, and it is gone.

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
# Items 1 and 4 are closed (see above), and their recipes are gone with them: they
# reproduced a default union and a `--grid` flag that the rhythm-first request removed,
# so running them now measures a different arrangement. The record is the commit and
# docs/rhythm-request-redesign.md.

# the bass row is inert *inside the engine*: every head is byte-identical to the default row.
# No CLI flag can reach it any more - the thumb's positions are `--bass-on` - so this
# measures the Python-API property `tests/test_grid.py` pins.
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
# inert rows: 13 of 13 heads identical, all four spellings giving the same count and the same
# tab lines on each - so the row is a no-op rather than an accident of one head. (The corpus is
# 13 files and not the 10 this item was written against; re-measured, not remembered.)

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
