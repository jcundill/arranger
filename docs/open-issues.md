# Open issues: playability of held shapes, and one GP5 discrepancy

Written at the end of the 2026-09-29 session, after the `GRIP_MAX_SPAN` /
`voicing_cost` / `grips`-intersection work. **Nothing in here is fixed.** The
three items below are open, with the measurements that produced them, so the
work can be picked up without re-deriving anything.

Reproduce all of it with the commands in [Reproducing](#reproducing).

---

## 1. The thumb is placed against the wrong reference point (walking bass)

**Status:** FIXED (stage 3). See "Stage 3" below.

### The symptom

`--texture walking_bass` on "But Not For Me" produces a bar that cannot be
played. Parsed back out of the GP5, bar 5 beat 0 holds notes at fret 8 and
fret 1 *in the same beat*, tied across the barline from the previous measure:

```
bar 5, beat 0:  B8  G8  D1  A5      (GP string numbers, 1 = high E)
```

A player reads that as one shape spanning seven frets. It is worse than ugly
notation: the exporter is asserting a **tie** — "hold this" — across the
barline at the exact moment the hand has to move down to the nut.

> "I can't hold the hand position and keep the tie if I need to take my hand
> off the fret board to reach the 8th fret."

The player's objection is correct, and it is a real defect rather than a
notation preference.

### Why the obvious check misses it

`fret_span()` is a **per-step** invariant, and this is a **between-steps**
defect. Measured over the whole arrangement:

```
steps=102   max fret_span over ALL steps = 3
steps with span >= 5: 0
```

Every individual step is tidy. The two consecutive steps are not playable
together:

```
bar4 b1.0  Ebmaj  target  frets [-1, 6, 8, 8, 8, -1]   A6 D8 G8 B8
bar5 b1.0  Ebmaj  fill    frets [-1, -1, 1, -1, -1, 3]  D1 + high-E 3
                       role=fill  bass_only=True  bass_midi=51 (Eb3)
```

Bar 4 puts the hand at **frets 6-8**. Bar 5 needs the D string at **fret 1**
and the high E at **fret 3**. Nothing spans seven frets; the *hand* does.

`tests/test_walking_bass.py:626` only asserts
`fret_span() <= GRIP_MAX_SPAN["shell"] + 5`. A 6-to-1 spread is 7, which
passes that bound numerically while being unplayable. The invariant checks a
number, not a hand.

### The actual root cause

`_place_bass` (in `arranger/bass.py`) ranks candidates by
`abs(fret - hand_fret)`, where `hand_fret` is the **current step's** upper
voicing's lowest active fret. That rule is correct as written. The problem is
what it is being measured against.

Bar 5 b1.0 is a `fill` with `bass_only=True`, so its upper voicing has been
thinned to the melody alone — G4 on the high E at **fret 3**. So
`hand_fret = 3`, even though the hand is physically still holding bar 4's
shell at frets 6-8.

Working the ranking by hand for Eb3 (MIDI 51) with `hand_fret = 3`:

| string | fret | `abs(fret - 3)` |
|---|---|---|
| low E (0) | 11 | 8 |
| A (1) | 6 | 3 |
| D (2) | **1** | **2** ← wins |

So `_place_bass` did exactly what it was told, and the answer is wrong
because the reference point is wrong. On a `bass_only` step there is no
fingered shape left to measure against; the hand position is the one from the
last **struck** step.

The same arithmetic with the true hand position (6-8) would put the thumb
within a couple of frets of where the hand already is, which is the whole
point of the proximity rule.

### Candidate fixes (none chosen)

- Give `_place_bass` the **held** position from the previous struck step when
  the current step is `bass_only`, instead of the thinned voicing. Smallest
  change, but the signature grows and it needs the "last struck step" plumbed
  in.
- Drop the D string from `BASS_STRING_INDICES` when a fingered shape is held
  above it. The thumb/fingers separation that makes walking bass work does
  not apply to the D string — it is inside the hand's own reach, so a thumb
  note there drags the whole hand down. Blunter, and loses the D string as a
  bass option entirely.
- Add a genuine reach invariant — "the thumb's fret is within reach of the
  hand holding the shell" — and treat a violation as a **penalty**, not a
  filter, the way `NECK_FRET_MIN` works. Most principled, largest change.

The first is a special case of the third, and the third is the one that will
keep holding when other between-step cases turn up.

### Related, and worth folding in

- `BASS_STRING_INDICES = (0, 1, 2)` includes the D string. `docs/history/walking-bass.md`
  says the thumb "takes a string that is unoccupied, can reach the pitch, and
  would sound below the upper structure". Nothing there distinguishes the D
  string from the low E and A, and that distinction is the physical point.
- `docs/history/walking-bass.md` records that "a four-tone walk over a held chord is
  playable — every thumb note in it is within the shell's span budget of
  `hand_fret`". That claim was measured with an upper voicing present. It does
  **not** hold for `bass_only` steps, which is how the bug got through.

### Stage 3 — fixed

The third candidate was the right one, and it turned out to be **the same fix as
item 2's root cause**: both were the thumb being placed against the current
step's thinned voicing instead of the shape the hand is holding. Fixing it here
removes the collision that made the GP5 tie resolve to the wrong fret, so the
two items were one bug wearing two coats.

`_place_bass` takes `held` — the last **struck** step's fret vector and which of
its strings the thumb played — and it corrects three things at once, all of which
the melody-only vector got wrong:

- **which strings are free** — one string cannot sound two frets, so a string the
  held shape occupies is not available. This was the item 2 collision;
- **what the lowest sounding note is** — the thumb must sound below the held
  structure, not merely below the melody;
- **`hand_fret`** — the proximity ranking now measures from where the fingers
  actually are, which is the original complaint.

One subtlety cost a correction mid-implementation. The held vector contains the
thumb's *own* previous note, because a target folds the thumb into its fret
vector. Treating that as structure to stay beneath forbids every repeated and
ascending walk note — and a walking bass is mostly those. An early version lost
6 of 22 thumb notes this way. It is now excluded **by string**, identified from
the held step's own `bass_string`, which is exact: the thumb moves between beats,
so the note it played two beats ago is not the one in the shape being held.

Measured over "But Not For Me", walking bass:

| | before | after |
|---|---|---|
| thumb on a finger's string, at a different fret | 6 | **0** |
| hand reach, thumb vs held shape (worst) | 8 frets | **3 frets** |
| hand reach (median) | — | **1 fret** |
| bar 5's thumb, reported as a 7-fret stretch | D string fret 1 | **A string fret 6**, where the hand already is |
| anchors with no reachable string | 1 | 1 (unchanged — pre-existing, see below) |

The one remaining gap is **not** a cost of this change: bar 15 beat 1.0 had no
reachable string before it either, because the step's own upper voicing already
sounds F3 on the low E and a thumb note must sound strictly below the structure
it supports. Verified by measurement against the pre-change tree rather than
assumed, and the test asserts that exact set so a *second* gap would fail.

- `tests/test_walking_bass.py::TestTheThumbReachesTheHandHoldingTheShape` — four
  tests, all on between-step properties: no shared string, bounded reach, the
  specific bar from the report, and the anchor set. All four fail on the
  pre-change tree and pass after.
- The weak assertion at `test_walking_bass.py:577` (`fret_span() <= shell + 5`)
  is left alone deliberately. `fret_span()` on a `bass_only` step measures
  melody-to-thumb, and those are different limbs — it rose from 3 to 11 with this
  fix and is not a playability measure. The reach test is the one that measures
  the hand.

---

## 2. GP5 bar 5 contains notes the engine never produced

**Status:** the A5 is FIXED and the cause is known. The missing melody turned out to
be a **different and much larger** defect that is shared by every renderer — see
[Stage 2](#stage-2--fixed-and-what-it-uncovered) and the new item 4 below.

The file's bar 5 beat 0 was `(2,8) (3,8) (4,1) (5,5)` — B8, G8, D1, A5.
Cross-checking against the engine's steps for that bar:

- **D1** matches. It is the thumb (Eb3, `bass_midi=51`). ✔
- **B8, G8** are bar 4's shell, correctly held across the barline. ✔
- **A5** appears **nowhere** near this bar in the engine's output. The walk
  here is D3-Eb3-E3, and the bar 4 shell's A voice is A6, not A5. ✘
- The melody of that step, **G4 on the high E at fret 3**, is **absent** from
  the beat entirely. ✘

This is not a bar-number offset: the other beats line up exactly (file beat 1 =
F4 on high E fret 1 = engine beat 1.5; file beat 2 = D2 + E3 = engine beat
2.0), and 2/2 maps `1.0 → beat0, 1.5 → beat1, 2.0 → beat2, 2.5 → beat3`.

### Stage 2 — fixed, and what it uncovered

The hypothesis recorded above ("the tie writer drops the melody note and
borrows a fret from the wrong voice") was **half right**, and the half that was
right is the interesting part.

**A GP5 tie carries no fret at all.** PyGuitarPro's writer emits
`fret = note.value if note.type != NoteType.tie else 0`, and the reader
reconstructs one in `getTiedNoteValue` by scanning backwards for the most
recent note on the same string. So a tie is not "held" in the abstract — it is
the claim *"same pitch as the last note on this string"*, and the file is
correct only while that claim is true.

Walking bass falsifies it. `_place_bass` chooses the thumb's string from the
**current step's thinned voicing**, not from the shape still ringing, so on a
`bass_only` step it can put the thumb on a string the held shape occupies —
**6 of the 22** `bass_only` steps in this head do, at a *different* fret. The
tie written for that string then resolves to the thumb's fret instead of the
shape's. Bar 5 beat 0 is the case in the file: the shape holds A6, the tie
resolved to the A5 written one beat earlier.

Isolated to a single note, the round trip is wrong even alone
(`string5 tie at fret 6` reads back as 5), and changing the in-memory fret to
5/6/7/8 changes nothing while flipping it to `NoteType.normal` writes 6
correctly. **Three beats in the file were wrong, not one** — bars 5, 17 and 21;
bar 17 turned a fret 6 into a fret 2.

The fix makes the renderer honest rather than the format: a tie is written only
where the claim holds, and the note is struck normally where it does not. A
re-struck note is a performance difference the player can hear and forgive; a
silently wrong pitch in a file read note-for-note is not. Round trip is now
lossless across all six committed heads × three textures.

- `tests/test_guitarpro.py::test_a_tie_never_asserts_a_pitch_the_string_is_not_sounding`
  — a **fret** assertion, where the existing bass-only test is a **type**
  assertion. That is precisely why this got through: the existing test says so
  in its own docstring ("Asserted on the parsed-back note *types* rather than on
  the frets"), which was a reasonable choice for the silence it guarded and left
  the fret channel untested.
- `test_the_fixture_actually_collides` asserts the premise, so the test above
  cannot go vacuous if the collision is ever fixed at the source.

**The right long-term fix is upstream**, and is item 1: if `_place_bass` measured
against the held position rather than the thinned voicing, the thumb would never
land on an occupied string and this could not arise.

---

## 3. `--grips` with a texture whose palette is legitimately empty

**Status:** FIXED. See "Stage 1" below.

`--grips shell --texture walking_bass` printed **76 copies** of:

```
Warning: walking_bass uses no grip for a fill, none of which is in the
requested ('shell',); using the texture's own set
```

`walking_bass`'s fill palette is `()` — deliberately, meaning "the left hand
plays nothing between the anchors" (`TEXTURE_GRIPS`, in `arranger/textures.py`).
So
every single fill intersects to nothing, and my new empty-intersection
warning fires on all of them.

The logic is right and the case is not a user error, so the fix is to suppress
the warning when the role's palette is **legitimately empty** (`role_grips` is
`()`), and keep it for the case where the caller asked for a grip the texture
genuinely never uses.

Output that unusable on a legitimate flag combination is a defect in its own
right, independent of the playability work.

### Stage 1 — fixed

The rule turned out to have **one** implementation, not the two this document
listed: `wjazzd.arrange_slots` routes through
`decisions.resolve_texture_grips` like `arrange_progression` does, so the
suppression is one `if` in `arranger/decisions.py` and both CLIs get it.

The distinction is between a texture that *cannot* use the grip and one that
means to *play nothing*; only the former is worth interrupting output to
mention. The now-unreachable `role_grips or 'no grip'` fallback in the message
went with it, since a palette that is empty can no longer reach the warning.

- `tests/test_texture.py::test_an_empty_palette_is_not_reported` — asserts the
  premise (the palette really is `()`), that the walking-bass run is silent,
  and that the non-empty `targets` case still warns, so this suppresses one
  case rather than the diagnostics path.
- Verified the arrangement is byte-identical before and after (step fingerprint
  `d2f53ccf47c13f80` over "But Not For Me", walking bass): the fix touches
  diagnostics and nothing else.

---

## 4. A `bass_only` melody that is not already ringing is dropped by every renderer

**Status:** found while fixing item 2 (stage 2), diagnosed, **NOT fixed**. Newly
added — it was not in the original list, and it is larger than any of the three.

### The symptom

Walking bass fills are "the melody alone plus the thumb" (decision C). When the
melody note on such a fill is **not** already sounding in the held shape, it is a
*new* note — and every renderer omits it. In "But Not For Me", **17 of the 22**
`bass_only` steps have a melody that is not held, so seventeen melody notes are
missing from the output.

All four renderers agree on the omission, which is what makes it a defect rather
than a difference of opinion. For bar 5 beat 1.0, whose frets are
`[-1,-1,1,-1,-1,3]` (thumb D1, melody G4 on the high E):

```
tabstaff._strikes_here  -> [2]          # thumb only; string 5 not drawn
tabgp._sounding_frets   -> [(2, 1)]     # thumb only
render._step_cells      -> ['','','1','','','']
tabxml._sounding        -> [51, 67]     # the odd one out: keeps both
```

`tabxml` happens to keep the melody because `_sounding` filters on `fret >= 0`
and so takes the whole vector rather than applying the `bass_only` rule at all —
which is a happy accident, not a decision, and it means the MusicXML score and
the tab disagree about which notes sound.

### Why it went unnoticed

Every committed fixture has a melody that is *already ringing*, so the rule and
the melody coincide. Measured over the single-chord fixtures and the demo
cadence, the number of affected steps is **0**. It only appears when the melody
_moves_ between melody slots, which a held-note head mostly does not do.

### Why it was not fixed here

This is a **musical and architectural** decision, not a localized patch, and it
should not be taken as a side effect of a rendering fix:

- The rule lives in `_strikes_here` (`tabstaff`), `_step_cells`
  (`arranger/render`), `_sounding_frets` (`tabgp`) and `_sounding` (`tabxml`) —
  four implementations that must agree, and the documented consequence of the
  current rule is that a `bass_only` column shows *only* the thumb.
- The likely fix — strike the melody too when it is not held — changes the
  **meaning of `bass_only`** from "the thumb alone strikes" to "the thumb and any
  new melody strike", which is a texture-level decision.
- It would move the tab strings pinned in the tests, which AGENTS.md calls the
  acceptance gate, so it needs the decision made deliberately rather than
  absorbed into stage 2.

Recommended as its own piece of work, after item 1, since item 1's fix changes
what the engine hands the renderers anyway.

---

## Recently completed, for context

These landed earlier the same day and are verified green (672 tests, 0 pyright
errors). They constrain any fix above, so they are recorded here:

- **`voicing_cost` ranks fret span above neck position** (span moved from index
  5 to index 3). `GRIP_MAX_SPAN` is unchanged at 5. Measured over all 1008
  (melody, quality) pairs: coverage identical at 960, selected span-5 shapes
  4.1% -> 0.8%, span-1 shapes 27.8% -> 44.4%. See AGENTS.md, "Span outranks
  neck position".
  - **Known trade:** a low Dm7 under D4 lost its 6-4-3-2 low bass to a span-1
    shape. Asserted explicitly in
    `test_progressions.py::test_low_register_cadence_voices_low_...` so it
    stays visible. Ranking the bass term above span was implemented and
    measured, and it brings the five-fret `8-x-8-8-13-x` back.
- **`grips` narrows the texture instead of being discarded.** An *explicit*
  `grips` intersects the role's palette; the default does **not** intersect
  (`GRIP_PREFERENCE` omits `interval`, `melody` and `drop3`, so intersecting
  with it would delete grips the texture depends on). In
  `arrange_progression` and `wjazzd.arrange_slots` — two copies of one loop.
- **A `targets` beat that cannot be *played* becomes the melody alone.** A
  target is only offered `("drop2", "drop3")`, so a narrow shell was never a
  candidate and the cost tuple would not have chosen it anyway (`missing` is
  index 2, above span). Fixes `x-6-5-3-8-x` on Ebmaj/G4.

Note the parallel with item 1: that rule demotes a *target* that cannot be
played, but it only tests `role == ROLE_TARGET` and a per-step span. The
walking-bass analogue — a step that is individually fine but unplayable next to
the previous one — is not covered by anything.

---

## Reproducing

```bash
# 1. the unplayable bar
.venv/bin/python -m arranger head tests/data/but_not_for_me.mxl \
    --grips shell --gp5 /tmp/wb.gp5 --texture walking_bass

# dump bars 4-8 out of the file (GP strings are 1..6, 1 = high E)
.venv/bin/python -c "
import guitarpro
t = guitarpro.parse('/tmp/wb.gp5').tracks[0]
for i in (3,4,5,6,7):
    print('--- bar', i+1, '---')
    for bi, b in enumerate(t.measures[i].voices[0].beats):
        print('  beat', bi, sorted((n.string, n.value) for n in b.notes))
"

# 2. the engine's own view, before any file writer touches it
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from headxml import arrange_xml_head
import tests.test_headxml as T
st,_,_ = arrange_xml_head(T.BUT_NOT_FOR_ME, grips=('shell',), texture='walking_bass')
print('max fret_span over ALL steps =', max(s.voicing.fret_span() for s in st))
for s in st:
    if s.bar in (4,5):
        print(s.bar, s.beat, s.role, 'bass_only=%s' % s.bass_only,
              s.voicing.frets, 'span=%d' % s.voicing.fret_span(),
              'bass=%s' % s.bass_midi)
"
```

(2) is the one that matters for item 1: the per-step span is fine and the
arrangement is still unplayable.
