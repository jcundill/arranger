> **Retired into `docs/history/` — the record of a ledger, every item closed.** The six issues
> this project filed are all closed, so the ledger itself is the record and **nothing here is
> live**: the rule each item closed on is stated where it is read from — the engine's behaviour
> in [docs/engine.md](../engine.md), the importer's and the renderers' in
> [docs/renderers.md](../renderers.md) — and the tests each item names pin it. A **new** issue is
> filed in the live ledger, [docs/open-issues.md](../open-issues.md), which indexes these six and
> points back here. This file is frozen like the rest of `docs/history/`: the paths in it are as
> they were when each item closed, and the numbers are the ones the tree cites.

# Open issues (retired)

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it, and each figure is stated **once**, in its own item: a summary would be a
second source for it, which is how the numbers in the old header rotted three times before the
*recipes* below were made explicit. **Every figure in this file is re-measured by hand from the
recipe beside it** — the figures are this document's own business, and the gate is not keyed to
these items. A closed item says how it closed and **keeps the measurement that closed it**, which
is why the six are here rather than removed one by one as they closed.

The index, for a reader arriving from one of the tree's citations of an item by number:

1. *(closed)* **The library facade takes its harmony per melody note** — closed by the
   rhythm-first request; see below.
2. *(closed)* **A refused thumb note is usually not the shape being unplayable** — closed by the
   palette narrow: a requested bass note moves the harmony instead of being dropped; see below.
3. *(closed)* **`harmony=full` is accepted on the comping route and answered with a different family** —
   closed by the axis being removed; see below.
4. *(closed)* **A `bass:` grid row is accepted and changes nothing** — closed by the request, and
   then made unreachable: the row itself went with the `grid` axis.
5. *(closed)* **A lone note the hand holds can leave the walk below the shape's reach** — closed by
   the hand's reach being bounded and the palette making room for the note; see below.
6. *(closed)* **A position falling on a note's release is read as held** — closed by reading the note
   as sounding over `[onset, end)`: the tune has stopped there, so the union states the chord;
   see below.

Reproduce the measurements with the commands in [Reproducing](#reproducing).

---

## 1. The library facade takes its harmony per melody note (closed)

**Closed by the rhythm-first request** ([docs/history/rhythm-request.md](rhythm-request.md)).
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
a position nobody asked for. What the engine's own union still generates, it generates for a
selection that **comps** — a chord part with no tune to play, which is what a bar the tune never
enters needs — and never for one that sings the tune, so a request and its axis spelling are one
arrangement.

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
[docs/history/fingering.md](fingering.md) §4.3's "should the selector have left room for
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

## 3. `harmony` set to `full` is accepted on the comping route and answered with a different family (closed)

**Closed by the axis being removed.** The item's subject was a value on an axis nobody could
reach: `harmony` had no request spelling and no flag, its only Python caller was its own test
module, and one of its three values was this one — measured inert on **0 of 13** committed
heads, where `shell_root` differed from the guide pair on **12 of 13**. Deleting the axis
removes the value with it, so the failure it named (a value refused by nothing that resolves
to something other than itself) cannot recur: the comping part states the guide pair, and
nothing spells a degree family at all.

**The measurement**, re-taken against the commit before the axis was removed — a worktree of
it, because the tree under test must be the one that still has the axis:

```bash
git worktree add /tmp/pre 7894c2f
cd /tmp/pre && PYTHONPATH=/tmp/pre .venv/bin/python - <<'PY'   # the repository's own interpreter
import os
from headxml import arrange_xml_head
from arranger.options import ArrangeOptions
DATA = "tests/data"
heads = sorted(n for n in os.listdir(DATA) if n.endswith((".musicxml", ".mxl")))
differ = {}
for value in ("full", "guide", "shell_root"):
    differ[value] = 0
    for head in heads:
        path = os.path.join(DATA, head)
        base = [s.voicing.frets for s in arrange_xml_head(path, options=ArrangeOptions(parts="chord"))[0]]
        tried = [s.voicing.frets for s in arrange_xml_head(path, options=ArrangeOptions(parts="chord", harmony=value))[0]]
        differ[value] += tried != base
print(len(heads), differ)   # 13 {'full': 0, 'guide': 0, 'shell_root': 12}
PY
```

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

## 6. A position falling on a note's release is read as held (closed)

**Closed by reading the note as sounding over `[onset, end)`.** `melody_at` returned the note at
its own release instant, so `melody_state` answered `held` there and §9.2 declined the position:
the chord part stayed silent at the instant the tune stopped. The reading is now the other one —
the tune has stopped, so the chord part states the chord — and it is the one the module's own rest
arithmetic already read, since `melody_rests` begins the rest after a note where that note ended.

**What it moved, measured.** The **union row** is where the rule had anything to decline: a
selection that comps and names no rhythm (`Request(melody=False)`, `parts="chord"`) gains **26**
comps over the fifteen committed heads — `But_Not_for_Me` +10, `I_Was_Doing_All_Right` +7,
`Trouble_in_Mind_Blues` +3, `synthetic_cut_time` +2, `synthetic_triplets` +2,
`synthetic_common_8` +1, `synthetic_waltz` +1, the other eight heads +0 — one for each of the 26
positions where a note releases exactly on a position the bar resolution generates.

Two rows do **not** move:

- the melody-anchored default (`head FILE`) is byte-identical, 685 steps before and after: a
  selection that sings the tune reaches neither the union nor a position on a release, so the note
  path is untouched;
- a requested rhythm keeps its step count **and its voicings**: `--chord-on 1`, `every-beat` and
  `1,2,1and,2and` change 13, 20 and 36 steps, and **every one of those keeps its exact frets**. What
  changes is the column and the clause — the released pitch leaves the melody column, and the line
  says "the tune is silent here" where it said "the guitar does not play the tune" — which is the
  true claim at a position the tune has left. `--chord-fills` is unchanged (0 changed): a fill is
  built with `melody=None` already.

**The figures this item used to quote were taken where the rule cannot fire.** Its "every current
row adds 0 steps" (685 under the default, 823 under `--chord-on every-beat`, 1,012 under
`--chord-on 1,2,1and,2and`) reproduces exactly — and all three are melody-bearing rows, which never
take the union path, so the figure that made this look costless never exercised the code the item
describes. Its "27 positions" is **26** on the same corpus.

**The walk does not move with it.** `bass._melody_in_force` reads its own timeline by onset *and*
duration, so the thumb still has the released pitch to approach from: measured on the walked row,
the 36 changed steps are the same text-only changes and **no bass fret moves**. Two layers reading
the edge differently is deliberate — the walk needs *some* pitch to approach, the chord part needs
to know whether the tune is sounding.

**Why the reading went this way.** Both were defensible, and two things already in the tree decided
it. `melody_rests` began a rest at `onset + duration`, so the inclusive reading had `melody_at`
answering `held` at the very position the module's own rest arithmetic calls the start of silence.
And `ArrangementStep.melody`'s contract is that a comp where the tune is silent "says so plainly
rather than borrowing a pitch", which the inclusive reading broke: a requested comp on a release
carried the note that had just stopped. It is a **reading, not a repair**, which is why it is
recorded here as well as in the commit.

**What it cost in the tree.** Three tests in `tests/test_headxml_timeline.py::TestMelodyState` were
**inverted** rather than deleted (trap 5) — the release instant's own pin, the tie that ends on its
release, and bar 6 of `synthetic_repeat_slash` — and two were **added** for the rule at the step
level (`TestTheUnionAdmitsTheReleaseInstant`: a held position withheld, the release comped and
carrying no melody). `tests/meta_explanations.py`'s comping-line count moved **1455 → 1475**, its 20
being exactly the new comps that name their voices.

---

## Reproducing

```bash
# The corpus is the committed heads: `tests/data`'s 13 and `examples`' 2, fifteen in all.
# Every glob below names all fifteen, because a figure taken over one of them is not a
# figure about "the committed heads" - the 720 and 435 this file used to quote came from
# a `tests/data`-only sweep, and mixing the two corpora is what made them disagree.
#
# Items 1, 2, 3, 4, 5 and 6 are closed (see above). Item 1's recipe went with the default union
# it was written against, and item 4's with the `grid` axis the rhythm-first request went on
# to delete; items 2, 3, 5 and 6 own their figures in their own sections.
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


# 6. a position on a note's release is now generated: `melody_at` reads a note as sounding
# over `[onset, end)`, so the release instant is silent, `melody_state` answers silent there
# and §9.2 admits the position. Re-measure it by putting the **old** boundary back - a note in
# force while `position <= end` - and re-arranging every head. The row where that matters is
# the **union** one, a selection that comps and names no rhythm: a requested rhythm states its
# positions whatever the tune is doing, and a melody-bearing selection never reaches the union.
# The end is on one absolute beat line: `beat_offset` places the bar, and `beat_type` is how
# many beats a whole note spans.
.venv/bin/python -c "
import glob, os
import headxml as H
from arranger import beat_offset, format_progression
from arranger.options import Request

original = H.melody_at

def inclusive(head, bar, beat):
    position = (bar, round(beat, 6))
    found = None
    for note in head.notes:
        if note.key > position:
            continue
        if found is None or note.key >= found.key:
            found = note
    if found is None:
        return None
    end = (
        beat_offset(found.bar, found.beat, head.beats_per_bar)
        + found.duration * head.beat_type
    )
    if beat_offset(bar, beat, head.beats_per_bar) > round(end, 6):
        return None
    return found.note_name

paths = (sorted(glob.glob('tests/data/*.musicxml')) + sorted(glob.glob('tests/data/*.mxl'))
         + sorted(glob.glob('examples/*.mxl')))

def steps(request):
    return {p: len(H.arrange_xml_head(p, request=request)[0]) for p in paths}

def lines(request):
    return {
        (p, s.bar, s.beat): format_progression([s]).strip()
        for p in paths for s in H.arrange_xml_head(p, request=request)[0]
    }

def compare(label, request):
    new_steps, new_lines = steps(request), lines(request)
    H.melody_at = inclusive
    old_steps, old_lines = steps(request), lines(request)
    H.melody_at = original
    for path in paths:
        delta = new_steps[path] - old_steps[path]
        if delta:
            print('  %-38s +%d' % (os.path.basename(path), delta))
    changed = sum(1 for key, line in new_lines.items()
                  if key in old_lines and old_lines[key] != line)
    print('%s: %+d steps over %d heads, %d shared lines differ'
          % (label, sum(new_steps.values()) - sum(old_steps.values()), len(paths), changed))

compare('union (melody=False)', Request(melody=False))
compare('chord-on 1', Request(chord_on='1'))
compare('chord-on every-beat', Request(chord_on='every-beat'))
compare('chord-on 1,2,1and,2and', Request(chord_on='1,2,1and,2and'))
"
# union (melody=False): +26 steps over 15 heads - `But_Not_for_Me` +10, `I_Was_Doing_All_Right`
# +7, `Trouble_in_Mind_Blues` +3, `synthetic_cut_time` +2, `synthetic_triplets` +2,
# `synthetic_common_8` +1, `synthetic_waltz` +1, the other eight heads +0 - one comp for each of
# the 26 positions where a note releases exactly on one the bar resolution generates.
# chord-on 1 / every-beat / 1,2,1and,2and: +0 steps and 13 / 20 / 36 shared lines differ - the
# released pitch leaves the melody column and the clause becomes 'the tune is silent here'. The
# voicings do not move: `step.voicing.frets` is identical key by key on every one of those lines.
# The melody-anchored default is byte-identical (685 steps either way), which is why the old
# figure of `added: 0 over 15 heads` said nothing about this rule - it measured that row, and
# that row reaches neither the union nor a position on a release.
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
