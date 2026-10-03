# Open issues: playability of held shapes, one GP5 discrepancy, and a lost melody

Items 1-4 were written at the end of the 2026-09-29 session, after the
`GRIP_MAX_SPAN` / `voicing_cost` / `grips`-intersection work; item 5 was added on
2026-10-03, and item 6 was found by fixing it. **All six are now fixed**; each carries
the measurement that produced it and the stage that closed it, so the work can be read
rather than re-derived. Items 1-3 were fixed in stages 1-3 the same day; item 4 needed
a corrected diagnosis first, and items 5 and 6 turned out to be two real defects of
which only one was reachable at a time - both recorded in full.

Item 5 is in the same subsystem as item 1, so read item 1's "Stage 3" before it: the
two share the notion of a held shape, though they turn out to be different bugs - item
1 was the *thumb* measured against the wrong shape, item 5 the *melody* measured over
the wrong timeline.

The header of each section states its status, and **item 4's original diagnosis was
wrong** - it blamed the renderers and the fill rule, when the engine was emitting two
contradictory flags at once. Read its "Stage 4" before acting on the section above
it. Item 5's original diagnosis was substantially right, but its own measurements
were two counts short in the way item 4's were, so read its "Stage 5" too.

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

## 4. A target the walk invented was silenced by the `bass_only` flag

**Status:** FIXED. See "Stage 4" below.

> **The diagnosis in this section was wrong when it was written, and the fix is
> smaller than the one proposed here.** It is kept below with its original reasoning
> because that reasoning is what pointed at the right file. Read "Stage 4" for what
> the defect actually was.

### The symptom as first diagnosed

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

### Stage 4 — fixed, and the diagnosis above was wrong twice

The premise was "a fill whose melody is not held". **The affected steps were not
fills at all**, and two of the three numbers above were wrong.

**One: the count is 9 of 22, not 17.** Comparing by *string* — is this melody's
string in the held shape's? — wrongly counts a step whose melody is already
sounding *on a different string*. Bar 4 beat 2.0 re-voices a held G4 from
B-string-8 to high-E-3, which sounds identical and is not a dropped note.
Comparing by **pitch** splits the 22 three ways:

| | count | renderers correct? |
|---|---|---|
| `role == ROLE_FILL`, melody already ringing | 13 | **yes** — decision C working |
| `role == ROLE_TARGET`, melody genuinely new | **9** | **no** |

**Two: the premise "walking-bass fills are the melody alone" pointed at the wrong
third of the texture.** The 13 fills are correct by construction and were never
touched. The 9 are all `ROLE_TARGET`, and each one is:

- a **walk-invented slot** — the bass grid created a downbeat the melody grid never
  had (decision B);
- carrying **`role == ROLE_TARGET`**, because `_roles_for_slot` promotes a strong
  beat when the melody moves onto it;
- carrying a **`shell` or `melody` grip** — the engine deliberately voiced a chord.

So `bass_only=True` and `role == ROLE_TARGET` arrived **together**, and they are
contradictory states: the first means "nothing above the thumb strikes", the second
means "a full chord states the harmony here". The engine voiced the chord and then
told the renderers to suppress it. The engine was right and the flag was wrong.

**Three: the fix is not in the renderers.** `bass_only` is already documented
correctly in `arranger/tuning.py`; the engine is what violated it. So the repair is
`decisions.is_bass_only(slot.bass_only, role)`, applied where the step is built —
which needs **no renderer change at all**, and `tabxml`'s accidental correctness
becomes deliberate agreement:

```
bar 11, frets [-1, 11, 13, 13, 13, -1], before:
  tabstaff -> [1]                render -> ['', '11', '', '', '', '']
  tabgp    -> [(1, 11)]          tabxml -> [56, 63, 68, 72]
bar 11, after:
  tabstaff -> [0, 1, 2, 3, 4, 5] render -> ['x', '11', '13', '13', '13', 'x']
  tabgp    -> [(1, 11), (2, 13), (3, 13), (4, 13)]
  tabxml   -> [56, 63, 68, 72]
renderer disagreements on sounding strings: 0
```

It also composes with item 1's fix: `_attach_bass` only narrows to the held shape
`if step.bass_only`, so a target measures its thumb against its own voicing — which
is right, because a target *is* the shape being played. At bar 29 that moved the
thumb off the low E at fret 15 and onto the D at fret 5, beside the melody, so the
fix improved playability as well as correctness.

- `tests/test_walking_bass.py::TestABassOnlyStepIsNeverATarget` — three tests: the
  contradiction does not occur, the 13 fills are still held, and every target's
  voices reach all four renderers. The first and third fail on the pre-change tree
  and pass after.
- `test_the_walk_loses_no_anchor_the_fix_did_not_already_lose` selected its
  population with `bass_only and bass_role == ANCHOR`. Bar 15 stopped being
  `bass_only` while remaining an anchor, so the filter quietly dropped it and the
  test could no longer fail. It now selects by `bass_role` alone — an anchor is an
  anchor whether or not the left hand holds across it. The bar-15 gap itself is
  **unchanged**: it still has no thumb note.

---

## 5. A walk-invented beat takes the wrong melody, and the tune loses a note

**Status:** FIXED (stage 5). See "Stage 5" below. Diagnosed and measured on
2026-10-03; pre-existing, and unrelated to the key-signature work that surfaced it.

### The symptom

`--texture walking_bass` on "But Not For Me" writes a soprano line that is right at
every note the tune attacks and **wrong at nine phrase downbeats**. Bar 3 is the
smallest case:

```
score bar 3:  (Eb4 held from bar 2)  F4  G4  F4
file   bar 3:  F4                    F4  G4  F4
```

The Eb4 that should still be sounding over the barline is not written at all, and the
F4 that follows it arrives a quarter early. Nine downbeats of this head are affected:
bars 3, 7, 11, 13, 15, 19, 23, 27 and 29 - each the first beat of a phrase, and each
one where the arrangement names a note the score has not reached yet. **Not all nine
are the case above**: bar 3 is a note held across the barline, while bars 11, 13, 15,
27 and 29 are a beat the score leaves to silence. Stage 5 separates them, and the
distinction turns out to matter to the fix.

Measured over the four committed scores (`tests/data`), counting the walk-invented
beats that carry a melody other than the one the score has sounding at that instant:

| score | walk-invented beats | carrying the wrong melody |
|---|---|---|
| `but_not_for_me.mxl` | 22 | **9** |
| `heres_that_rainy_day.musicxml` | 14 | 0 |
| `i_was_doing_all_right.mxl` | 12 | 0 |
| `tenor_madness.musicxml` | 56 | **4** |

Thirteen slots in all, and **the description of them was checked during stage 5 and
was half right**: seven are a note begun in the previous bar and still sounding, which
is the bar-3 case. The other six sit over a **written rest** - bars 11, 13, 15, 27 and
29 of "But Not For Me" among them - where the melody stops at the barline and the
invented beat inherits a note two bars back. Both need the same fix under the same
rule, but they are different cases, and the rest case is the one a strict "only notes
that are sounding" reading would have broken. See "Stage 5".

### Why the obvious check misses it

**The file is right everywhere the tune has a note.** The arrangement matches the
score at all 80 melody onsets of "But Not For Me" - every attack of the tune is the
highest sounding pitch of its beat. A check that compares the soprano against the
melody at note onsets passes completely, because the wrong notes are all in the gaps
*between* onsets, at beats where the score writes no new note at all.

This is the same shape as item 1's "why the obvious check misses it": the invariant
that is easy to state is per-step, and this defect lives in what a step *inherits*.

It also survives a round-trip test, because the GP5 file is a faithful rendering of
the arrangement - the arrangement is what is wrong. Both `tabgp` and `tabxml` place
`step.melody` where the step says, so no renderer can be the place to fix it.

### The actual root cause

`arranger/bass.py::_bass_slots` decides which melody a walk-invented beat carries by
tracking `previous_melody` **while iterating the walk's own beats**:

```python
previous_melody = -1
for note in bass_line:                 # the WALK's beats, not the melody's
    key = (note.bar, float(note.beat))
    if key in melody_at:
        previous_melody = melody_at[key][0]
        continue
    entries.append((key, previous_melody if previous_melody >= 0 else 0, note, True))
```

So a melody slot is only noticed if **the walk happens to land on it**. In 2/2 the
walk visits only beats 1.0 and 2.0 of each bar - measured, `_walking_bass_line`
returns 1-2 notes per bar in cut time against 4 in 4/4 - so the melody slot at beat
2.5 is invisible, and the next walk beat inherits the melody from beat 2.0 instead of
the note that is actually sustaining. Instrumented on bars 2-3:

```
bar  beat   kind    idx  melody carried
  2  2.5    MELODY   5   Eb4
  3  1.0    WALK     4   F4     <-- idx 5 is what is sounding
```

The one-line fix is to track `previous_melody` over `located` - the melody timeline -
rather than over `bass_line`, since `located` is already in onset order and is the
thing actually being asked about. It is *not* that simple, which is why it is
recorded rather than done:

- The melody timeline is a list of **onsets**, and "the melody in force" is only well
  defined if a note's `duration` is respected. A slot whose duration runs past the
  next slot's onset - exactly the bar-3 case, where Eb4 ends at bar 3 beat 1.25 and
  the next note starts at 1.5 - has to win over any later onset until it stops
  sounding. `_bass_slots` currently reads `duration` only to pass it through, never
  to decide precedence.
- `melody_at` is keyed by `(bar, beat)` and assumes one note per key. Two notes can
  share a slot under `pick`, and a note whose onset is *not* on the walk grid is the
  normal case rather than an edge.
- The invented beat is then voiced as a real step and can be **promoted to a target**
  (documented in `arrange_progression`: "a step the walk invented can be promoted to
  a target when the melody moves onto it"). On these nine bars it is promoted, so the
  wrong note is not merely held - it is stated as the harmony. Any fix that changes
  which melody the invented beat carries changes which bars promote, which changes
  the chord written there, so the blast radius is wider than the melody line.

### Candidate fixes (none chosen)

- **Order `previous_melody` by the melody timeline, honouring `duration`.** Smallest
  and most obviously right: it makes "the note in force" mean what it says. Needs the
  precedence rule above, and the two-notes-per-key case.
- **Give the walk a grid that contains every melody onset**, so the existing
  coincidence test sees everything. This also fixes the metre problem below, but it
  changes how many thumb notes are written, which is a visible change to every
  walking-bass arrangement.
- **Do not invent a beat where the melody is sustaining** - leave the gap as a rest.
  Loses the thumb note on the downbeat, which is the one beat a walking bass most
  needs it.

### Related: the "four-quarter walk" claim is only true in 4/4

`arrange_progression`'s docstring and `docs/history/walking-bass.md` both describe
walking bass as "a four-quarter walk underneath", and `_bass_slots` says the bass
grid "may be finer than the melody grid, so a bar whose melody is a whole note still
has four beats to walk". Measured: **4 notes per bar in 4/4, 1-2 in 2/2** - every
bar of "But Not For Me" (2/2) and of "Tenor Madness" (4/4) respectively.

This is the same trap as AGENTS.md item 9, "a count without a denominator is not a
metre": the claim is true in the metre it was written in and false in the metre three
of the four committed scores are notated in. It is also load-bearing here, because the
beat 2.5 the walk misses is exactly the beat the false claim says it visits.
Correcting the wording is cheap and should happen whichever fix is chosen.

### Reproducing

The render, from [Reproducing](#reproducing):

```bash
.venv/bin/python -m arranger head tests/data/but_not_for_me.mxl \
    --grips shell --texture walking_bass --gp5 /tmp/jon.gp5
```

then compare the soprano line of `/tmp/jon.gp5` against the melody of
`tests/data/but_not_for_me.mxl`, **including the notes that run past a barline**.
Comparing only at note onsets reports no defect at all, which is the point of the
"why the obvious check misses it" section above.

### Stage 5 — fixed

**One defect was found by this fix but is not its own.** Reading the corrected output
back is what turned it up: bar 3 beat 1.0 became a *repeat* of the note sounding from
the previous bar, and the renderers then dropped the two inner voices of the `Cm7`
under it. That is `docs/open-issues.md` **item 6** below, which is pre-existing and was
reproduced on the commit before this one. The melody fix is what made it visible, by
making bar 3's melody genuinely the note that was still sounding.

The first candidate was taken: **precedence is decided over the melody timeline,
honouring `duration`.** `_melody_in_force` answers "what is sounding at this instant"
by walking the melody onsets in order and taking the latest one that has not stopped,
falling back to the latest onset started where the score writes silence.

Two things the section above flagged as "not that simple" turned out to be already
handled, which is why this was a small change:

- **The bar-3 precedence case needs no special rule.** `Eb4` starts at bar 2 beat 2.5
  and runs to bar 3 beat 1.25, so the *latest onset at or before* bar 3 beat 1.0 is
  already `Eb4`. Ordering by onset and stopping at the beat is sufficient; duration is
  what makes it correct when a later note has *ended*, which no committed head
  produces today.
- **Two notes under one key is not reachable.** `head_skeleton` reduces to one note
  per slot before `_walking_slots` sees it, so `melody_at` never collides; the
  timeline is built from the same list and inherits that.

The one thing the section above did not anticipate is that **"the note in force" is not
always "the note sounding"**, and its "all thirteen run past the barline" is only half
right. Of the 22 invented beats in "But Not For Me", **12 sit over a note still
sounding and 10 over a written rest**:

| | count | what the slot carried before |
|---|---|---|
| a note still sounding | 12 | 4 wrong, 8 already right |
| the score writes silence | 10 | 5 wrong, 5 already right |

The second row is why a strict reading of the rule would have been a regression. At
bar 5 beat 1.0 nothing is sounding at all, and the left hand is still holding the bar 4
shape, so the invented beat must name that note rather than nothing. That is nearly
half the beats, so it is asserted directly rather than left to the head to reach.

Measured over the committed heads, all five now clean:

| score | metre | walk-invented beats | wrong melody before | after |
|---|---|---|---|---|
| `but_not_for_me.mxl` | 2/2 | 22 | **9** | **0** |
| `heres_that_rainy_day.musicxml` | 2/2 | 14 | 0 | **0** |
| `i_was_doing_all_right.mxl` | 2/2 | 12 | 0 | **0** |
| `tenor_madness.musicxml` | 4/4 | 56 | **4** | **0** |
| `The_Jitterbug_Waltz.musicxml` | 3/4 | 32 | **2** | **0** |

`The_Jitterbug_Waltz.musicxml` was added with this fix and is the **third metre**, and
that is the point of including it. The "four-quarter walk" wording above was not a
harmless overstatement: it is the reason a melody slot at beat 2.5 was assumed to be
one the walk visits, and in 2/2 the walk never goes there. The same false claim is
corrected in `_walking_slots`, `arrange_progression`, `ArrangementStep.bass_only` and
the `BassNote` docstring, each now naming `beats_per_bar` rather than four. The
`BassNote` "four quarters" claim is left in `docs/history/walking-bass.md` alone, per
AGENTS.md: history records what was decided, not what is currently true.

**The blast radius was wider than the melody line**, as the section above warned, and
three of this repository's own tests moved. Each is a consequence, and each is
asserted in its new state rather than merely re-baselined:

- **Bar 3's downbeat became `Eb4` over `Cm7`**, not `F4` over `Ebmaj` - the chord is
  read from the melody slot, so correcting the melody corrected the harmony with it.
- **Bar 3's downbeat is a `repeat` of the `Eb4` still ringing from bar 2 beat 2.5.**
  That part was correct - the melody really is held - and it is what exposed item 6.
  `test_every_target_states_its_chord_in_every_renderer` excludes `repeated` alongside
  `melody_only` because both mean "the left hand holds"; it is the *decision* that was
  wrong for a melody-alone fill, not the exclusion.
- **Bar 7 beat 1.0 became a fill.** It was a *target* stating `F4`, a note the score
  does not reach until beat 1.5; carrying the sustained `Eb4` means the melody does not
  move onto that downbeat, so it is correctly thin. The fill count went **13 → 14**,
  and a fix that had left it at 13 would have kept the bug.
- **The anchors with no thumb note went from one to three** (bar 3, 19, 23), and bar
  15 lost its gap. Under the corrected `Cm7` the anchor note *is* the shell's lowest
  note, so there is no free string below it - the same reason as the original bar-15
  gap, reached by a different route. The test now also asserts **why** each gap is
  there, so the next one has to explain itself.

- `tests/test_walking_bass.py::TestAWalkInventedBeatTakesTheMelodyInForce` — six
  tests on the rule itself, including the two branches no committed head reaches (a
  beat before the melody starts, and a written rest underneath the walk).
- `TestEveryHeadCarriesTheMelodyInForce` — two tests: the table above over all five
  heads, and `test_the_heads_span_three_metres` so the 3/4 row cannot quietly become
  another 4/4 one.
- `test_the_pre_fix_rule_really_does_fail_these` re-implements the old three-line rule
  and asserts it disagrees with the engine on bar 3. **Verified by measurement**: with
  only the `_bass_slots` rule reverted and the new helpers left in place, all seven of
  these tests fail on the old rule and pass on the new one.

---

## 6. A `repeated` step after a melody-alone fill drops the chord

**Status:** FIXED. See "Stage 6" below. Found on 2026-10-03 while fixing item 5, and
**pre-existing** — reproduced on the commit before that fix.

### The symptom

`--texture walking_bass` on "But Not For Me", bar 3 beat 1.0. The engine voices a
`Cm7` under a held `Eb4`:

```
bar 3 beat 1.0   chord Cm7   melody Eb4
voicing: C3 (low E, fret 8), Bb3 (D, fret 8), Eb4 (G, fret 8)
```

and the GP5 contains **one note**:

```
bar 3, beat 0:  G string fret 8   Eb4
```

`C3` and `Bb3` — the two notes that make this a `Cm7` rather than a bare melody note —
reach **none** of the four renderers. The player sees the chord name `Cm7` printed above
a single `Eb` and an octave of empty strings below it.

### Why it happens

`decisions.is_repeated_step` decides that a step is a soprano-only re-strike by
comparing two things: the melody's **sounding pitch**, and the **harmony**. On bar 3 both
are unchanged from the previous step, so it returns `True` — and `True` instructs every
renderer to strike the soprano and hold the rest.

But the previous step, bar 2 beat 2.5, is a **fill**: under `walking_bass` decision C a
fill is the melody alone, and it sounds exactly one note. There are no inner voices
ringing to hold. So "hold the previous shape" is an instruction with nothing to act on,
and its effect is to suppress the *new* shape's inner voices instead.

The rule already knows this principle — its docstring says a melody-only step "has one
active fret and no inner voices to hold, so the flag would mean nothing" — but the
guard tests the **flag** `melody_only`, and a texture fill deliberately carries
`melody_only=False` (see the comment at the call site that builds it). So the case the
docstring describes is exactly the case the code misses.

### Why item 5 exposed it, and is not responsible

Before item 5's fix, bar 3 beat 1.0 carried `F4` — a note the score does not reach
until beat 1.5 — so its melody differed from the previous step and the rule correctly
returned `False`. Once the melody is read from the timeline, that bar carries the
`Eb4` that really *is* still ringing, the two conditions match, and the rule fires.

So the melody was wrong before and the chord was right; now the melody is right and the
rule misfires. **Both defects were real and only one was reachable at a time**, which is
why this was not found by reading the file and why the fix is in
`decisions.is_repeated_step` rather than in `_bass_slots`.

### Stage 6 — fixed

The guard now tests **what the previous step sounds** rather than which flag it carries:

```python
if len([fret for fret in previous_step.voicing.frets if fret >= 0]) < 2:
    return False
```

`melody_only` is kept as a separate named check because it reads as the intent rather
than the arithmetic, and because the two are not the same set.

Measured on the reported bar, before and after:

| | before | after |
|---|---|---|
| bar 3 beat 1.0 in the tab | `----8--` | **`8-x-8-8-x-x`** |
| bar 3 beat 1.0 in the GP5 | `G string 8` | `low E 8, D 8, G 8` |
| voices reaching the output | 1 of 3 | **3 of 3** |
| the chord's root sounds | no | **yes — C3, an octave below the melody** |

- `tests/test_walking_bass.py::TestASingleNoteStepHasNothingToHold` — three tests: the
  flag is not set, the chord reaches all four renderers, and the committed head puts the
  root below the held melody. The first two fail with the guard reverted; verified by
  measurement rather than assumed.

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
# 0. item 5 and item 6 together: the walk-invented downbeat, and the chord it drops
.venv/bin/python -m arranger head tests/data/but_not_for_me.mxl \
    --grips shell --texture walking_bass --bars 3 --tab staff

# the bar 3 beat 1.0 line should read `Cm7 Eb4 ... 8-x-8-8-x-x` - three notes, the
# root an octave below the held melody. Before stage 6 it was one note (the melody
# alone); before stage 5 it was the wrong melody (F4) with the chord right.
```

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
