# Open issues

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it. A fixed issue is **removed** from this file rather than kept as history —
its record lives in the commit that fixed it and in the document it belongs to. **One exception,
stated so it is not a silent one:** items **1, 2, 4 and 5** are closed **in place** with their numbers,
because `docs/history/` is frozen and cites items by number — removing them and renumbering would
silently repoint about fifty references at a different item, which is the contradiction between
documents this project treats as a bug. A closed item says how it closed and **keeps the
measurement that closed it** — that measurement is the item's evidence, and the recipe beside it is
what keeps it re-measurable — but it states each figure once, where the item's own subject puts it.

Two are open, and each figure is stated **once**, in its own item: a summary here would be a
second source for it, which is how the numbers in this paragraph rotted three times before the
*recipes* below were made explicit. **Every figure in this file is re-measured by hand from the
recipe beside it**: they are this document's own business, and the gate is not keyed to these
items.

1. *(closed)* **The library facade takes its harmony per melody note** — closed by the
   rhythm-first request; see below.
2. *(closed)* **A refused thumb note is usually not the shape being unplayable** — closed by the
   palette narrow: a requested bass note moves the harmony instead of being dropped; see below.
3. **`harmony=full` is accepted on the comping route and answered with a different family** — the
   one axis value refused by nothing that resolves to something other than itself.
4. *(closed)* **A `bass:` grid row is accepted and changes nothing** — closed by the request, and
   then made unreachable: the row itself went with the `grid` axis.
5. *(closed)* **A lone note the hand holds can leave the walk below the shape's reach** — closed by
   the hand's reach being bounded and the palette making room for the note; see below.
6. **A position falling on a note's release is read as held** — `melody_at` keeps a note in
   force through its end instant; the boundary is pinned by a test and the reading stays open,
   but only a **requested** rhythm names such a position, and it costs no step.

Reproduce the measurements with the commands in [Reproducing](#reproducing).

---

## 1. The library facade takes its harmony per melody note (closed)

**Closed by the rhythm-first request** ([docs/history/rhythm-request.md](history/rhythm-request.md)).
The item had two open halves and both now have an answer rather than a workaround.

**The entry point.** A caller *can* place a chord where the tune is silent, and always could:
`(None, quality, name)` is a legal triple, and giving it its own `(bar, beat, duration)` puts a
chord at that position with no melody above it. That is the same shape `headxml.head_skeleton`
emits for a note-less slot, so the hand-built path and the imported one are one path -
`movement.arrange_progression` needs no second input type.

**The generation.** What was genuinely missing was a *source* of positions, and it is the request
now: `--chord-on` names them (`1and`, `every-beat`, a list), `--chord-fills` places chords in the
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

## 2. A refused thumb note is usually not the shape being unplayable (closed)

**Closed by leaving room for the thumb.** The question this item left open —
[docs/history/fingering.md](history/fingering.md) §4.3's "should the selector have left room for
the thumb in the first place?" — is now answered *yes*, and the answer is a **palette narrow**
rather than a cost criterion: `decisions.leaving_room_for_the_bass` drops every candidate the
thumb cannot reach the requested note under, and the same `voicing_cost` ranks what is left. The
bass still never enters the tuple — `cost` sits below `bass_place` in the package DAG, so it
cannot ask where the thumb goes, and no candidate carries one.

**Why the lever pays now when it did not before.** The old measurement's "harmless recovery is
gone" was about recovering *after* the fact: re-selecting the shape once the note had already
failed changed the harmony and paid the span bucket anyway. Narrowing **before** the ranking is a
different trade, because the shape is then chosen for the hand it will be played with. It also
removed the `drop24` caveat: nothing is being added to the palette, so the three inner-skip sets
that were removed for the right-hand reason are not missed.

**Measured**, over the committed heads (15: `tests/data`'s 13 and `examples`' 2) × the four
rows that place a thumb note under a texture that has one (`targets`/`uniform` ×
`root`/`root,5th,approach,nearest`; 1,318 requests): refusals **130 → 22**. All 22 are on the
two `uniform` rows (7 under `root`, 15 under the walk), where a four-voice texture leaves the
thumb the least to move to; the line names the refused pitch. The same question asked of the
melody grid the report was filed under (`--bass-on 1,2,1and,2and`, 986 steps and 729 requested
notes) goes 79 → **0**. On the comping route, where the guitar does not sing, the narrow
recovers the same way — `--bass-on every-beat` over the committed heads goes 155 → **0** (the
row that *does* sing, `--bass-on every-beat` with the melody, keeps 16: a tune in the soprano
is a fifth voice the `uniform` texture cannot always make room under).

**What it costs.** Shapes move: measured over the committed heads under
`--bass-on 1,2,1and,2and`, **148 of 986** steps choose a different shape, **85** of them
stating one *more* voice and **33** stating fewer (a shape that frees a string for the thumb
tends to be the fuller one, because `missing` outranks `position` in the tuple — but not
always). Melody pitch never changes; the melody moves to another string in 54 of those 148,
about a third. Hand travel over the row rises 1606 → 1666 frets in total (mean 1.65 → 1.72 per
step), while jumps over five frets *fall* 97 → 95 because the reach bound below removes the
wide ones. `make demo` is byte-identical: the narrow is inert without a requested bass note.

**Still not recorded on the step: the cause of a refusal.** `ArrangementStep.bass_refused`
carries the wanted pitch class, not the reason, so the four causes — no free string, no octave of
the pitch below the shape, a fifth fret for four fingers, a reach wider than the hand's five —
are named together by `annotation._bass_refusal_clause`. Recording which one fired would remove
the replica the recipe below describes; that is an engine change, and with the 22 that remain
confined to one texture and no step of the reported row among them, it is not worth the field.

---

## 3. `harmony` set to `full` is accepted on the comping route and answered with a different family

**Status: open, diagnosed.**

**The issue.** `harmony` is read only by the comping route, and `grips.get_comping_voicings`
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
`ArrangeOptions(harmony="full", parts="chord")` gives guide tones — byte-identical to the same
arrangement with no `harmony` at all. It is the one value refused by nothing that resolves to
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

**Closed twice over.** The bug was never the row: it was that the CLI offered a flag whose
`bass:` half did nothing, so `--grid melody:every_note,bass:walk` printed a request back and
then wrote no bass note. That flag went with the rhythm-first request, whose two spellings of
the thumb are `--bass-on` (when) and `--bass-notes` (what).

**The row then went with the axis.** `GRID_PART_PATTERNS` / `grid_bass_pattern` named
`bass:every_note`, `bass:walk` and `bass:anchors` and had no caller outside the axis's own
parser, so the vocabulary was a name for something the engine did not do - which is the
failure this document is for. The axis, the table and the parsed-but-unread row are gone;
the thumb's positions come from `bass_on` and its notes from `bass_notes`.

**What the row was trying to say is still true, and is now stated by the code that does it**:
the walk's beats come from `bass.py`'s own timeline rather than from any chord figure, which
is why the two are separate questions in the request.

---

## 5. A lone note the hand holds can leave the walk below the shape's reach (closed)

**Closed by bounding the hand and making room for the note.** Two changes, and neither is
sufficient alone — the measurements below are why.

**The reach is bounded.** `fingers.can_fret` used to count *fingers* only (`fingers_needed <= 4`),
so a merged hand could be three fingers and eight frets: `[1, 8, -1, 8, 9, -1]`, the reported bar,
passed the check because 1, 8 and 9 are three distinct frets. It now requires
`hand_span(frets) <= fingers.MAX_HAND_SPAN` as well, where `hand_span` is max − min over frets at
1 or above (an open string takes no finger and does not widen the hand). Five is the bound because
it is the hand's own size, and every `GRIP_MAX_SPAN` entry sits at or under it — asserted in
`tests/test_grip_tables.py` rather than written as a second copy of the number. Both of
`can_fret`'s callers inherit it: `bass_place.place_bass`, which asks before it picks a string, and
`bass_merge._takes_the_ring`, which asks before it lets a struck note keep ringing under the next
shape.

**The harmony moves instead.** A refusal alone would have cost 92 of the 729 requested notes on
the row the report came from — all of them playable by a lower shape. So selection now narrows the
palette to the shapes the thumb can reach the requested note under, and the tuple ranks what is
left (`decisions.leaving_room_for_the_bass`; item 2 has the mechanism and the cost). The reported
bar, `tests/data/synthetic_cut_time.mxl` **bar 6 beat 2.5**, is the case: the ranking's first
choice is `x-8-7-8-x-x`, the walk's F is seven frets under it, and the shape now sits at frets 1–4
where the low E has the note. `tests/test_bass_placement.py::TestTheHarmonyLeavesRoomForTheBass`
pins it, including the dropped shape's tab and the clause that names it.

**Measured.** Over the committed heads × the walk row (`ArrangeOptions(texture="targets",
bass="root,5th,approach,nearest", grid="melody:every_note,bass:walk")`; 460 requested notes over 773
steps that carry a thumb): worst merged span **5**, with **0** steps over 5 — the same sweep under
`--bass-on 1,2,1and,2and` had 44 steps over 5 with a worst of 9. Over the four thumb rows item 2
uses (1,318 requests): worst **5**, **0** over 5. The narrow is what keeps the note and the bound
is what keeps the hand; room without the bound still writes 52 wide steps through `carry_bass`,
and the bound without the room refuses 92 notes that a lower shape could sound.

**What the walk's register lever would have been.** Playing the pitch class an octave up was the
item's remaining idea. It is moot: the *shape* now moves to where the line's own octave is
reachable, so the register the hand can reach is chosen by the ranking rather than imposed on the
line. The third lever — refusing the note — is what the bound now does, and it is kept as the
**fallback** rather than the policy: the palette gives up the note only when no shape in it can
carry it, which over the four thumb rows happens **22** times, every one of them under the
`uniform` texture.

---

## 6. A position falling on a note's release is read as held

**Status: open as a reading, and its measured cost is gone.** §9.2's hold rule is *inclusive* at
its edge, so the instant a note stops sounding is treated as one it still holds. The reading is a
decision, it is still what is built, and `tests/test_headxml_timeline.py` pins it; the arithmetic
that finds the edge is not a decision, and it uses the head's own metre. What has changed is that
no *figure* names such a position any more: only a requested rhythm does, and a request states
its positions whatever the tune is doing.

**The issue.** `melody_at` keeps a note in force while `position <= end`, where the position and
the end are both on one absolute beat line and the end is
`beat_offset(note.bar, note.beat, beats_per_bar) + duration * beat_type`. The test is
`if beat_offset(bar, beat, beats_per_bar) > round(end, 6): return None`, so the **end instant
itself** still returns the note. `melody_state` then answers `held` there rather than `silent`,
and §9.2's rule that a held position is not a slot declines it. A position where the tune has
*stopped* is therefore treated exactly like one where it is still sounding.

**The problem, and what became of it.** The measurement that made this an issue was taken when a
figure named its own positions in every bar, and under it 9 steps were lost across the corpus. What
replaced that figure is the request: the default names no added position, `--chord-on` names the ones
the caller wants, and the engine's own union - still built, for a spelled axis - is the only thing
that generates positions where the tune is silent, so the rule has almost nothing left to decline:
re-measured by patching the boundary alone — a `held` answer whose in-force note
ends at that exact position becomes `silent` — **every current row adds 0 steps** (685 under the
default, 823 under `--chord-on every-beat`, 1,012 under `--chord-on 1,2,1and,2and`).

**Where it still shows.** 27 positions in the corpus have a note releasing exactly on one the bar
resolution generates. A **requested** rhythm asks for those positions directly (it is not the
engine's union, so the hold filter never runs), and each becomes a step carrying the released
note: `examples/But_Not_for_Me.mxl` bar 5 beat 1 is a `Ebmaj` whose melody is the `G4` that ends
there. That is consistent with the reading rather than a second bug — a position the caller names
is placed — but it is where a change of reading would be felt now, and the reason the item stays
open rather than closing.

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
# The corpus is the committed heads: `tests/data`'s 13 and `examples`' 2, fifteen in all.
# Every glob below names all fifteen, because a figure taken over one of them is not a
# figure about "the committed heads" - the 720 and 435 this file used to quote came from
# a `tests/data`-only sweep, and mixing the two corpora is what made them disagree.
#
# Items 1, 2, 4 and 5 are closed (see above). Item 1's recipe went with the default union
# it was written against, and item 4's with the `grid` axis the rhythm-first request went on
# to delete; items 2 and 5 own their figures in their own sections.
#
# Both of the closed engine items are re-measurable in one line each, which is the form
# their fix took - no replica of `place_bass` is needed any more, because there is nothing
# left to attribute:
#
#   item 2: `bass_refused` over the four thumb rows - `targets`/`uniform` x
#           `root`/`root,5th,approach,nearest` - is 22 of 1,318 requests, and every one of
#           the 22 is on a `uniform` row;
#   item 5: `fingers.hand_span(step.voicing.frets)` over a walked row never exceeds
#           `fingers.MAX_HAND_SPAN`, and neither does the merged hand of any step that
#           carries a thumb.


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

paths = (sorted(glob.glob('tests/data/*.musicxml')) + sorted(glob.glob('tests/data/*.mxl'))
         + sorted(glob.glob('examples/*.mxl')))
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
# every head +0, and `added: 0 over 15 heads`: the melody-anchored default generates no
# position of its own, so there is nothing for the rule to decline. The +9 this item used to
# report (334 steps becoming 343, `Trouble_in_Mind_Blues` +3, `synthetic_cut_time` +2,
# `synthetic_triplets` +2, `synthetic_common_8` +1, `synthetic_waltz` +1) was measured against
# the union the `--grid` flag used to produce. The two readings of sounds here are both
# defensible; what the patch cannot say is which one the library should hold.
```


Item 2's count is re-measured the same way (no committed script — `AGENTS.md` trap 8): load each
committed head over the four rows that place a thumb note under a texture that has one
(`texture` in `targets`/`uniform` × `bass` in `root`/`root,5th,approach,nearest`) and count the
steps whose `bass_refused` is set. It reads **22** of 1,318 requests, every one of them on a
`uniform` row, which is why there is no attribution table in that item any more: with selection
leaving room for the note, the only refusals left are slots where no shape can carry it at all,
and they are counted where the report named them.

Naming the *cause* would still need a replica of `place_bass`'s four filters rather than a reading
of the step, and that limitation is unchanged: `ArrangementStep.bass_refused` carries the wanted
pitch class, not the reason it could not be placed. Rebuild the free-string set, the octaves of
the wanted pitch below the shape's own lowest note, the `fingers.can_fret` four-fret budget and
now its reach, in that order, and the first of the four that comes back empty is the cause. It is
not rebuilt here: the 22 that remain sit on one texture, and none of them is on the row the report
was filed under.
