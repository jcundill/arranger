# Open issues

Each item states the **issue**, the **problem it produces**, and **why it exists**, with the
measurement behind it. A fixed issue is **removed** from this file rather than kept as history —
its record lives in the commit that fixed it and in the document it belongs to. Three are open:

1. **A chord in force is stored per melody note, so a bar the melody skips is silent** — the
   largest: a quarter of a named grid's positions produce no chord, and the importer cannot even
   represent the case.
2. **A refused thumb note is usually not the shape being unplayable** — measured, decision left
   open: the selector's lever recovers nothing harmlessly, and the walk's own pitch reaches only
   twelve events in one head.
3. **`harmony=full` is accepted on the comping route and answered with a different family** — the
   one axis value refused by nothing that resolves to something other than itself.

Reproduce the measurements with the commands in [Reproducing](#reproducing).

---

## 1. A chord in force is stored per melody note, so a bar the melody skips is silent

**Status: open — the timeline is recorded, queryable, and unioned on the comping route; the
defect is only partly fixed.**

**The issue.** Harmony is stored *per melody note*, not per time position. There is no
chord-in-force structure a position without a note can read, so the step loop — which iterates
melody slots — can only *keep* or *drop* a slot and can never *create* one.

**The problem.**

- On the comping route a bar whose melody is entirely rests produces **no part at all** — not
  quiet, absent. Measured over the three committed 2/2 fixtures: **49 of 190** beat positions
  (25%) have a chord in force and no melody note, and `freddie` emits only 41/44/56 stabs.
- On a beat the melody skips, a stab has to borrow the *previous* note's chord, and it lasts that
  note's duration rather than the grid's next position.
- The case is **structurally inexpressible**, not merely quiet: `headxml` counts rests in
  `skipped`, and a skipped rest contributes no slot and no bar number. Nothing raises and no
  warning is emitted, so every assertion that counts steps passes.
- The walking bass shares the limit one level down: `_walking_slots` walks the bars the melody
  *touches*, so a melody-less bar yields no beats. The walk needs the chord timeline too, and
  cannot copy a rhythm the timeline has nothing to supply.

**Why it exists.** Fixing it means slots a grid position can *create*, which changes three
things: `head_skeleton` (rests become time rather than skipped elements, and it must emit chord
slots as well as note slots), `ArrangementStep.melody` (`None` where no note sounds — the field
half is done), and `decisions.melody_alone_case` (an invented slot has no note to be alone
*with*, so its `kind` vocabulary needs a fifth value). That is a different order of change: a
harmonisation engine whose input is a **chord timeline**, not a list of melody notes.

**Landed so far.** `Head.chords` / `HeadChange` record the timeline as the document is walked;
`headxml.chord_at` queries it by forward fill (the last change at a position wins, `None` before
the first); `headxml.chord_slots` yields one slot per position the grid names, and
`arrange_xml_head` unions them with `head_skeleton`'s on the **comping route only**
(`comps+freddie`: 80/81/110 → 102/103/124). `every_note` is excluded from the union — it names
every beat, so merging would *thin* the part — and a stab's duration is now the grid's, capped
at the barline. Still owed: generated slots, and the `melody_alone_case` kind.

**The rule it suggests.** A rhythm needs a source of its own. Where a grid's positions are
filtered out of the melody rather than generated from the metre, a quarter of them vanish
silently and no warning can be issued, because the question was never asked.

---

## 2. A refused thumb note is usually not the shape being unplayable

**Status: diagnosed, not fixed — the decision is left open.** This is the question
[docs/fingering.md](fingering.md) §4.3 leaves hanging: whether the **selector** should have
left room for the thumb in the first place.

**The issue.** `_place_bass` refuses a candidate and the step keeps its upper voicing.

**The problem.** Over the seven committed heads × the four bass rows (1,500 `_place_bass`
calls) refusals number **39** today — 53 on the tree the measurement was first taken on
(`d9403e5`); two commits since moved it, neither aimed at this. Attributed by cause:

| cause | refusals |
|---|---|
| no free string | **0** |
| **no octave of the walk's pitch below the shape** | **38** |
| five frets for four fingers | **1** |

The middle row is the common case, and it is the one the message did not use to name (it does
now). 24 of the 38 are a *doubling*: the walk's pitch class is the shape's own bottom class an
octave up, so the thumb would restate what the chord already sounds. The other 14 are a pitch
the shape has no octave of beneath it.

**Why the levers do not pay.** All three filters are right, and dropping the note is deliberate
policy — a step is never dropped because the thumb could not reach it. The candidate-level
lever exists but recovers nothing harmlessly on the current tree:

- **the identical-notes retry** (re-select over hosting shapes that sound the same notes)
  recovers **0 of 34** today, where it recovered 10 of 53 on its own tree: those hosts were the
  removed `drop24` sets. Every remaining recovery changes the harmony and pays the span bucket;
- **the bare retry** (48 of 53) costs span on 26 of them and can drop the root;
- **the walk's own pitch** is the fourth lever and costs the tuple nothing — it re-states the
  bass under the shape already chosen — but reaches only **12 events, all one head and one
  chord** ("But Not For Me" `Cm7` bars 3, 19 and 23), where the substitute is the 5th or 7th.
  **14 of 38** cannot be helped by any pitch at all.

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
the route that does, with no warning on either. Measured on
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
# 1. the chord timeline: a bar the melody does not enter
# Three bars of melody where bar 2 carries only a chord symbol in force.
# Cmaj7 begins at bar 1 beat 2 and governs all of bar 2.
.venv/bin/python -c "
from arranger import Diagnostics, VoiceLeadingEngine
prog = [('D5','m7','Dm7'), ('C5','maj7','Cmaj7'), ('E4','7','A7')]
timings = [(1,1.0,1.0), (1,2.0,1.0), (3,1.0,1.0), (3,2.0,1.0)]   # no slot in bar 2
steps = VoiceLeadingEngine.arrange_progression(
    prog, timings=timings, melody='alto,tenor', grid='freddie',
    diagnostics=Diagnostics())
for s in steps:
    print('bar', s.bar, 'beat', s.beat, s.chord, s.voicing.frets)
print('bar 2 present:', any(s.bar == 2 for s in steps))
print('Cmaj7 duration:', [s.duration for s in steps if s.chord == 'Cmaj7'])
"
# bar 2 is absent, and Cmaj7 is voiced once, at bar 1 beat 2, for that melody note's
# own duration - so it cannot be heard sounding under the bar it governs.

# the walking bass has the same limit ('every bar the melody touches')
.venv/bin/python -c "
from arranger.bass import bass_line_for
from arranger.chords import ChordParser
chords = [(ChordParser.parse_chord_name(n)[0], ChordParser.parse_chord_name(n)[1] or '', n)
          for _m, _q, n in [('D5','m7','Dm7'), ('C5','maj7','Cmaj7'), ('E4','7','A7')]]
line = bass_line_for('walk', chords, [(1,1.0), (1,2.0), (3,1.0), (3,2.0)], 4)
print('bars walked:', sorted({n.bar for n in line}))
"
# bars walked: [1, 3]   <- bar 2 has no beats to walk
```

Item 2's counts come from a throwaway script (not committed — `AGENTS.md` trap 8): wrap
`steps.select_step_voicing` and `steps._place_bass` (snapshotting the shape **before** the
call), load each `tests/data/` head over the four bass rows, and for every refusal replicate
`_place_bass`'s candidate loop to name the cause and run the real `_place_bass` over the
captured pool to find the hosts.
