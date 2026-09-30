# Open issues: playability of held shapes, and one GP5 discrepancy

Written at the end of the 2026-09-29 session, after the `GRIP_MAX_SPAN` /
`voicing_cost` / `grips`-intersection work. **Nothing in here is fixed.** The
three items below are open, with the measurements that produced them, so the
work can be picked up without re-deriving anything.

Reproduce all of it with the commands in [Reproducing](#reproducing).

---

## 1. The thumb is placed against the wrong reference point (walking bass)

**Status:** diagnosed, not fixed. This is the item worth doing first.

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

---

## 2. GP5 bar 5 contains notes the engine never produced

**Status:** unexplained. Treat the walking-bass GP5 export as untrustworthy
until this is resolved, independently of item 1.

The file's bar 5 beat 0 is `(2,8) (3,8) (4,1) (5,5)` — B8, G8, D1, A5.
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

So the file's beat 0 is not a faithful rendering of any single engine step:
one note is unexplained and one is missing. **Worth checking whether the tie
writer in `tabgp` is dropping the melody note of a tied step and borrowing a
fret from the wrong voice**, but that is a hypothesis, not a finding.

The two items may well be one bug. The A5 looks like the bar-4 A-string voice
displaced by a fret, and a displaced voice is exactly what a tie/split that
writes the wrong `Note` would produce.

---

## 3. `--grips` with a texture whose palette is legitimately empty

**Status:** regression I introduced on 2026-09-29, known, unfixed.

`--grips shell --texture walking_bass` prints **30+ copies** of:

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
genuinely never uses. Both copies of the rule need it:

- `arranger/steps.py`, in `arrange_progression`
- `wjazzd.py`, in `arrange_slots`

`tests/test_texture.py::test_an_empty_intersection_falls_back_and_says_so`
asserts the warning is printed, so it will need a companion case asserting it
is *not* printed for an empty palette.

Output that unusable on a legitimate flag combination is a defect in its own
right, independent of the playability work.

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
