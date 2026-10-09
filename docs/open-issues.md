# Open issues: playability of held shapes, a GP5 discrepancy, and a lost melody

Items 1-4 were written at the end of the 2026-09-29 session, after the
`GRIP_MAX_SPAN` / `voicing_cost` / `grips`-intersection work; item 5 was added on
2026-10-03, item 6 was found by fixing it, item 9 came out of a measurement of the
comping axes, and item 10 came out of asking what a comping grid should do on a bar the
melody does not enter. **Item 11 came out of the measurement
[docs/fingering.md](fingering.md) §4.3 asked for**, and it is the one whose fix needed the
*right* hand: a merged step could sound five strings, and no finger assignment was ever
going to find it. **All except items 7, 10, 13 and 17 are now fixed**; each carries the
measurement that produced it and the stage that closed it, so the work can be read rather
than re-derived. Items 1-3 were fixed in stages 1-3 the same day; item 4 needed
a corrected diagnosis first, and items 5 and 6 turned out to be two real defects of
which only one was reachable at a time - both recorded in full.

Item 5 is in the same subsystem as item 1, so read item 1's "Stage 3" before it: the
two share the notion of a held shape, though they turn out to be different bugs - item
1 was the *thumb* measured against the wrong shape, item 5 the *melody* measured over
the wrong timeline.

**Items 7, 10, 13 and 17 are open** — 7 and 10 are the large ones, 13 is a measured question
with its fix left open on purpose, and 17 is the newest and the smallest: a `harmony=` value
the comping route accepts and then answers with something else. **Item 8 is fixed and is the
one to read first if you are
here to learn from a defect**: it is a method whose comment described the correct
behaviour while the code did the opposite, and it survived a green gate because every
fixture happened to use the one input that did not trigger it. **Item 9 is the newest
fixed one and is the one to read before adding a policy function**: it is a check
reading a table that describes a different generator, and it survived a green gate
because its one test happened to name the input that worked. **Item 15 is that same
shape in the arithmetic**: a beat conversion written as `beats_per_bar / 4`, which is
right in 4/4 and 2/2 - six of the seven committed heads - so it survived a green gate
and every renderer for as long as it existed. **Item 10 is the largest
open one** - a quarter of the beat positions a named grid names produce no chord at all,
and the case cannot even be represented by the importer - and it is the reason the
harmonisation engine is worth building.

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

The **lowest active fret** rather than the shape's average or its top fret, and that was
measured rather than preferred: over the plan's own worked example, ranking to the lowest
active fret matches **26** of the 28 readable bass notes where the average matches **24**,
because a shell's low voice is the note the thumb is trying to join. `avg_fret` and
`top_fret` agree with each other on every one of those notes, so neither is contradicted by
the evidence - the average is simply dragged up by the melody, which sits an octave above
the position the hand is in.

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
listed: `wjazzd.arrange_slots` (since removed; `arranger/slots.py` is what remains)
routed through
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
  `arrange_progression` and the slot layer — one loop now, since the corpus copy
  (`arranger/slots.py`'s predecessor) was removed.
- **A `targets` beat that cannot be *played* becomes the melody alone.** A
  target is only offered `("drop2", "drop3")`, so a narrow shell was never a
  candidate and the cost tuple would not have chosen it anyway (`missing` is
  index 2, above span). Fixes `x-6-5-3-8-x` on Ebmaj/G4.

Note the parallel with item 1: that rule demotes a *target* that cannot be
played, but it only tests `role == ROLE_TARGET` and a per-step span. The
walking-bass analogue — a step that is individually fine but unplayable next to
the previous one — is not covered by anything.

---

## 9. `bass_allowed` refused a thumb line using a palette the comping route never plays

**Status: fixed.** Found while measuring whether `walking_bass` could be expressed as a
combination of the shipped axes; recorded here because the *shape* of it is the trap,
not the typo.

### The symptom

`melody="alto,tenor", bass="walk"` — a horn on the tune, the guitar comping, and a
walking bass underneath — produced **no thumb line at all** under the default texture,
with this warning:

```
Warning: uniform leaves no bass string free for a target - its grips can occupy all of
(0, 1, 2). Every bass policy needs the same string, so no policy fits here.
Try texture='targets', or drop the bass.
```

Every clause of that sentence is a misdirection. Measured on
`tests/data/but_not_for_me.mxl`:

| | steps | thumb notes | warning |
|---|---|---|---|
| `texture=uniform` | 80 | **0** | the refusal above |
| `texture=targets` | 166 | 127 | none |

So the same request produced two different parts, and the one that worked required
naming a texture that **has no effect on this route at all**.

### Why the obvious check misses it

Because the texture genuinely cannot distinguish the routes, and nothing in the
signature said so. `bass_allowed(texture, bass)` measures thumb capacity from
`TEXTURE_GRIPS[texture][role]` — the palette the *melody-bearing* route generates via
`get_all_grip_voicings`. On the comping route the shapes come from
`get_comping_voicings` instead, and the texture is inert: **all 80 comping shapes are
byte-identical under `texture=uniform` and `texture=targets`.** The function was being
asked about a table that does not describe the shapes being generated.

And the warning was false on the facts as well. Those 80 comping shapes sound like this:

```
string 0 (low E)    0 steps
string 1 (A)        0 steps
string 2 (D)        1 step
string 3 (G)       19 steps
string 4 (B)       79 steps
string 5 (high E)  61 steps
```

The thumb had the entire bottom of the neck. `uniform`'s grip palette really can occupy
`(0, 1, 2)` — `drop24`'s `(4,2,1,0)` set spans all three thumb strings at once — but
that is a fact about shapes the comping route never builds. (That set has since been
removed, with the family's other three inner-skip sets, for a right-hand reason of its
own — [fingering.md](fingering.md) §4.4 — so the same worst-case question now answers
"one string free" at every texture. The bug below was that the question was asked of the
wrong generator, which is unchanged by that.)

**The existing test passed throughout** because it spelled `texture="targets"`: the one
texture that happened to fit. A test that pins a workaround is not a test of the
behaviour.

### The general form

**A policy function that asks about a table describing the wrong generator.** This is
AGENTS.md trap 1 — a check reading an input that does not describe the thing checked —
arriving at an *axis boundary* rather than at a forgotten file. `_place_bass` is handed
the voicing and works per note; `bass_allowed` is handed a texture and reasons about a
palette, and on one of the two routes that palette is a meaningless name.

The rule it suggests: **the thing a policy asks about must be the thing that produced
the output.** A route flag (`melody_voiced`) is not the same as an axis value, and where
one is inert the other must not be asked.

### The fix

`bass.comping_capacity(notes, bass_voice)`, derived from `_comping_string_sets` the way
`harmony_allowed` derives its rule — measured from the generator, not listed, so a
future arity is covered without editing a table. Worst case free thumb strings:

| arity | free |
|---|---|
| 1 note (an inner voice) | 3 |
| 1 note (`bass_voice`) | 2 |
| 2 notes (`alto,tenor`) | 2 |
| 3 notes | 1 |
| 4 notes | 1 |

**Never zero, at any arity** — which is the finding rather than a coincidence: the
comping families are `duo` and `shell`, which live on the top half of the neck
precisely because the bottom of it belongs to the thumb. So this route cannot be
refused, and `bass_allowed` now takes the route's own arity (`notes`, `bass_voice`) and
asks the right question when it is given them.

That **forced a reordering** in `arrange_progression`: `_resolve_melody` now runs before
`_resolve_bass`, because only the first knows the route. The two resolutions are
independent, so the order carries no other meaning — but it is now load-bearing, and
reversing it silently reinstates the bug. This is trap 12's shape (a guard ordering that
looks incidental and is not) in a place with no failing test to point at it.

Measured effect: the comping route goes from **80 steps / 0 thumb notes** to **166 steps
/ 127 thumb notes** under the default texture, and both textures now agree exactly. This
is a behaviour change and is deliberate — it is the correct output, and nothing about it
is special-cased.

### Where the code is

| file | what changed |
|---|---|
| `arranger/bass.py` | `comping_capacity`, `_worst_free_capacity` (the arithmetic both capacity functions share), `bass_allowed(..., notes, bass_voice)`, `_comping_no_room_reason` |
| `arranger/movement.py` | `_resolve_bass` takes `melody_voiced`/`notes`/`bass_voice`; `_resolve_melody` now resolves **before** it |
| `arranger/__init__.py` | `comping_capacity` re-exported |
| `tests/test_bass.py` | `TestCompingCapacity` — 5 tests |
| `tests/test_comping.py` | `TestTheCompingRouteCarriesAThumb` — 4 tests |

Verified by mutation rather than by assertion: reverting the call site to
`melody_voiced=True` fails 3 of the 9, including
`test_the_texture_does_not_change_the_comping_arrangement` — which is the invariant that
actually broke, and which could not be written before the fix.

### Not fixed, and it is the same defect

`harmony_allowed` is asked about `voices`, which is load-bearing on both routes, so it
is correct — but the *pair* of functions now asks two different things in two different
ways, and `grid_allowed` is still asked about a metre rather than about the lattice.
The general fix is a single "what did the generator produce" seam, which is the boundary
the restructure proposes to draw. Until then, this item's rule is the one to apply when
adding the next policy: **name the generator, not the axis value.**

---

## 10. A chord in force is stored per melody note, so a bar the melody skips is silent

**Status: open; stages 1–3 landed (the timeline is recorded, queryable, and unioned on the
comping route), the defect is only partly fixed.** Found while asking what a comping grid
should do on a bar whose melody is all rests. It is not a grid bug and not a walking-bass
bug: it is one missing data structure, and three shipped behaviours depend on its absence.
**Read "Stage 1" through "Stage 3" before the sections below** — together they remove the
first of the four changes in "Why it is not a patch", and stage 3 fixes the comping route
while leaving two debts recorded at the end of it.

### The symptom

On the comping route, a bar whose melody is entirely rests produces **no part at all** —
not a quiet bar, not a single stab. Not even the bar exists.

Built by hand, three bars of melody where bars 1 and 3 carry notes and bar 2 carries
only a chord symbol in force (`Cmaj7`, begun at bar 1 beat 2):

```
grid=freddie, melody=alto,tenor  →  3 steps
   bar 1: [(1.0, shell, Dm7),  (2.0, shell, Cmaj7)]
   bar 3: [(1.0, shell, A7)]
   bar 2: absent
```

`Cmaj7` is in force for the whole of bar 2. It is voiced once, at bar 1 beat 2, with
**that melody note's** duration — so it cannot be heard sounding under bar 2 at all.

### Why the obvious check misses it

Because the case is **structurally inexpressible**, not merely quiet. `headxml` counts
rests in `skipped` (`skip("rests and unpitched notes")` — 15, 6 and 10 in the three
committed fixtures) and a skipped rest contributes no slot and no bar number. So "a bar
with a chord but no melody" is not a rare input; it is an input the pipeline cannot
represent. Nothing raises, no warning is emitted, and every assertion that counts steps
passes.

### The measurement

Beat positions where a chord is in force but the melody has no note — positions a comp
should stab and cannot. **All three fixtures are 2/2.**

| fixture | beats | no melody note | share | `freddie` stabs emitted |
|---|---|---|---|---|
| `but_not_for_me` | 64 | 23 | **35%** | 41 |
| `heres_that_rainy_day` | 58 | 14 | **24%** | 44 |
| `i_was_doing_all_right` | 68 | 12 | **17%** | 56 |
| **total** | **190** | **49** | **25%** | |

**A quarter of the positions a named grid names produce no chord.**

### The root cause, and a correction to how it reads

Harmony is stored **per melody note**, not per time position. Three consequences, each
measurable:

| question | needs | has |
|---|---|---|
| what sounds in a bar the melody skips | the chord in force across it | nothing — the bar is absent |
| what sounds on a beat the melody skips | the chord in force at that instant | the chord of the *previous* note |
| how long a stab lasts | the grid's next position | the melody note's duration |

**The walking bass is affected too, and this corrects an earlier reading of it.** Its
comment says "One walked beat per quarter of every bar **the melody touches**"
(`bass.py:835`), which is accurate — and the docs state the same limit correctly, as
"a bar whose melody is a single whole note still yields four bass notes"
(`docs/history/walking-bass.md`, quoted in `comping-styles.md` §4.2). Both describe a
bar the melody *enters*, verified: with a whole note in bar 1 the walk covers bar 1, and
with every bar entered it covers all three.

What does **not** hold is the inference drawn in `comping-styles.md` §4.2 — that
`_walking_slots` is the seam a comping grid wants. It is a seam for *beat-level* gaps
inside a bar the melody enters, not for bars the melody abandons:

| | bars walked |
|---|---|
| melody in bars 1 and 3 only | **1, 3** |
| melody in bars 1, 2 and 3 | 1, 2, 3 |

So the union generalises less than the document assumes, and a first reading of this
item — "the bass already does this, so the comp can copy it" — was wrong. The bass
copies a pattern the *harmony timeline* has to supply, and for a melody-less bar the
timeline has nothing to supply. That is the same missing structure, one level down.

### Stage 1 — landed: the timeline exists

The first of the four changes above is **not** needed. `Head` already carries a chord
timeline in effect — `headxml`'s module docstring says so, and `_read_notes` implements
the forward fill. The loss was at exactly one point: a `<harmony>` updates three locals
and the only place they are written out is `group_chord`, on the next note. A change no
note reaches was read, held, and discarded.

So stage 1 records it instead of discarding it:

| file | what changed |
|---|---|
| `headxml.py` | `HeadChange` (a chord becoming in force at a `(bar, beat)`), `Head.chords`, and one `append` in the `<harmony>` branch |
| `tests/test_headxml.py` | `TestChordTimeline` — 9 tests |

**Everything is byte-identical**, which is the point of landing it alone: `head_skeleton`
still reads `notes`, so all 39 arrangements across the three fixtures and the whole flag
matrix are unchanged, and `make demo` is unchanged.

**The test that makes the others mean anything** is
`test_the_timeline_reproduces_every_notes_own_chord`: the timeline, forward-filled to
each note's own position, **reproduces all 271 notes' chords across the three fixtures**.
So it is not a second opinion — where it and the note path could differ, the note path is
the one with every published arrangement behind it. Verified by mutation: making the
`append` conditional fails 8 of the 9 (the ninth asserts the *empty* default, which is
correctly true either way).

**Measured on the committed scores**, so this was not a synthetic case after all — 6 of
their 154 `<harmony>` elements precede no note:

| fixture | bars |
|---|---|
| `i_was_doing_all_right` | 2, 10, 26, 34, 36 |
| `heres_that_rainy_day` | 32 |

Bar 2 of `i_was_doing_all_right` is the issue in miniature — `HARMONY(m7), NOTE(D5),
HARMONY(7), rest`, so an `Am7` has a note and a `D7` governs the rest of the bar with
none. Bar 32 of `heres_that_rainy_day` is the strongest form: **no notes at all**, two
changes, and before this it produced nothing whatever.

The beat conversion is `_flush_group`'s expression, `1 + onset/divisions *
beats_per_bar/4`, spelled out rather than shared — trap 9's denominator problem, and all
three fixtures are 2/2, which is the metre that catches it.

### Stage 2 — landed: the query

`chord_at(changes, bar, beat)` answers "what is in force here" for a position no melody
note describes, which is the twin of `bass._melody_in_force` ("which melody slot is
sounding here" for a beat the thumb invented). It has **no consumer yet**, so all 39
arrangements and `make demo` are unchanged again — this is a specification written before
its first use, which is the only honest time to write one.

Three rules, each forced by a measurement rather than chosen:

- **A chord holds until the next one replaces it, including at its own beat.** Bar 2 of
  `i_was_doing_all_right` is `Am7` at beat 1 and `D7` at beat 2.5, and the note path
  captures the chord *before* a note — so a change sharing a beat with the note it
  governs applies to it.
- **The last change at a position wins.** Measured, not hypothetical: bars 33 and 35 of
  `i_was_doing_all_right` each carry **two** `<harmony>` elements on beat 1.0 (`Gmaj` then
  `Eb7`; `G6` then `Eb7`), and the note in each bar carries `Eb7`. First-wins would put a
  chord under a note that ships with a different one.
- **`None` before the first change.** A position no chord has reached has no harmony, and
  inventing one is what this module refuses everywhere else.

**A bug the tests caught, which is the reason the implementation is written the way it
is.** The obvious body — scan and overwrite, or scan and `break` at the first entry past
the target — is order-dependent, and `test_an_unsorted_timeline_still_answers_correctly`
failed it: with `[bar 2, bar 3, bar 1]` in that order, **every bar answered `Gmaj`**. A
hand-built `Head.chords` need not be in position order, and a forward fill that stops
early on one returns a stale chord with nothing to indicate it.

So the answer is *the change with the greatest key at or before the target*, which is
order-independent and still last-wins at a tie, because two changes at one position have
**equal** keys and `>=` takes the later of them. Verified: unsorted and sorted lists now
give identical answers, and mutating `>=` to `>` fails 2 of the 7, while restoring the
`break` fails 1.

`test_it_agrees_with_the_note_path_on_every_note` closes the loop at 271 of 271 — the
data agrees with the notes, and now the *query over* that data agrees too, which is a
different claim and could have failed at the duplicate-position boundary above.

### Stage 3 — landed: the comping union

`chord_slots` yields one slot per position the grid names, and `arrange_xml_head` unions
them with `head_skeleton`'s on the **comping route only**. **This is the first phase that
changes output**, and the scope is deliberately narrow:

| | steps before | steps after |
|---|---|---|
| `comps+freddie` | 80 / 81 / 110 | **102 / 103 / 124** |
| `comps+joe_pass` | 80 / 81 / 110 | **105 / 114 / 159** |

Measured over three fixtures and fourteen flag combinations: **six arrangements change,
thirty-six do not** — including all four `grid=` arrangements on the singing route, and
`make demo`. The gate was 1008 tests with every pre-existing assertion passing unchanged (841 after the corpus removal).

**`every_note` is excluded from the union, and that is load-bearing.** It names every beat
of the bar, so merging it with the notes would keep every position the note path has *and
drop the ones it does not* — the melody runs at sixteenths and the grid at beats, so the
union would thin the part. That is the one case where the two lists must not be merged.

**A stab's duration is now the grid's, not the note's** — the distance to the next grid
position, capped at the barline. Measured: `every_note` and `freddie` give 0.5 on a 2/2
fixture, `joe_pass` gives 0.25 and 0.5 because it names the *ands*, and **no grid produces
a whole note anywhere**. That is the correction the conflation above asked for, delivered
as arithmetic rather than a new flag.

**`charleston` was not a 4/4 figure asked of a 2/2 bar.** §4.2 of `comping-styles.md`
attributed its silence to the metre, and that was a misdiagnosis: the grid could only
*filter* melody slots, so a position with no note was unreachable whatever the pattern
said. Measured on the 2/2 fixtures, every named grid now places something — `every_note`
63, `charleston` 63, `joe_pass` 64, `final_and` 32 — and `joe_pass` was previously
**silent on all three**.

**Two bugs this phase's own tests caught.**

- **A skipped resolution step, and it hit the default arrangement.** The route predicate
  was `voices_have_soprano(parse_voices(melody))`, and `parse_voices("auto")` returns the
  **sentinel** `("auto",)`, which contains no soprano — so the *melody-bearing* route was
  classified as the comping one and unioned grid positions into itself. Measured: **14
  steps of a singing `grid=freddie` arrangement carried a placeholder melody.** Fixed with
  `resolve_voices`. This is AGENTS.md trap 12 arriving from a new direction: a *resolution*
  step skipped, so a policy reads as something it is not.
- **`NO_CHORD` is not usable as a placeholder melody.** The corpus pre-pass parses a slot's
  melody with `musthe.Note` (`wjazzd.unresolved_steps`) and it raised
  `ValueError: Could not parse the note 'NC'` — a crash, not a wrong note.
  `_PLACEHOLDER_MELODY = "C4"` parses, and was documented as the **cost of a deferral**
  rather than as a design: the honest field is `ArrangementStep.melody: Optional[str]`,
  which lets a slot with no tune carry no note at all. **Fixed (§9.3 step B):** the
  sentinel is deleted rather than hidden, `headxml.chord_slots` emits `None` where no
  note sounds, every renderer prints the absence blank, and the test that asserted
  equality against the placeholder — which all 30 real `C4` slots across the fixtures
  could have satisfied for the wrong reason — now asserts `IsNone`.

**A third change in the same working tree was a misdiagnosis, and it is recorded here
because it is the shape of item 8 rather than a fact about item 10.** Stage 3 also
carried an uncommitted edit to `headxml._flush_group` adding
`and notes[-1].bar == bar` to the tie merge, on the stated belief that merging into
`notes[-1]` "ate the new bar's downbeat" on a blues head.

It does the opposite, and the measurement is the finding: a `tie type="stop"` in a new
bar **is** the continuation the merge exists to absorb, so restricting the merge turns
every cross-barline tie into a second note at the same pitch. The guard **added** notes
on all six fixtures — `but_not_for_me` 80 → 84, `heres_that_rainy_day` 81 → 88,
`i_was_doing_all_right` 110 → 112, `tenor_madness` 200 → 212,
`The_Jitterbug_Waltz` 119 → 125 — and grew `heres_that_rainy_day` from 34 bars to 37 by
re-entering bars a tie had legitimately emptied. **Ten tests failed against it**,
including `test_a_tie_across_a_bar_line_is_one_note` and the two that assert note
counts per fixture.

The reported symptom was checked before the change was trusted and **does not
reproduce**: exporting the blues head gives zero notes with no `<pitch>`, with or
without the guard. The premise read *merged* as *lost* — bar 3 has no downbeat note
because its downbeat is still sounding the A4 written in bar 2, which is what a tie
means. Reverted; the comment on the function now records the measurement so the same
fix is not attempted a third time.

The fixture earned its place in the tree rather than being deleted along with the
change. `tests/test_headxml.py::TestAHeldNoteIsOneNoteAcrossABarline` — five tests —
pins the rule on the real file, and names the observation that started all of this:
**bars 8, 16 and 17 carry no note at all**, each because a note held from an earlier bar
covers it. Verified by mutation: adding the guard back fails **4 of the 5**, the fifth
being the premise assertion that the file really does tie across barlines, which holds
either way.

### Still open

**The corpus half of this is retired rather than fixed, and that is worth stating
rather than leaving as a stale debt.** `wjazzd.skeleton_slots` built its slots from
*notes* and had no timeline, so a Weimar head with a bar of rests had the same defect
and none of the three stages above applied to it — and CI could not have caught a
regression there either, because those tests only ran in the manual `corpus` job. The
database and its loader are gone (`arranger.slots` is what remains of the part that
was not corpus-specific), so the debt no longer has a subject. The 164 tests that
would have fixed it were removed with it rather than ported.

`melody_alone_case`'s fifth kind is likewise still owed: an invented slot now carries
`None` (step B deleted the placeholder), but it still reaches that function as a melody
*slot* and takes the comping route by virtue of `melody_voiced=False` rather than by its
own nature. That works, and it is a debt rather than a design — step B removed the
invention, not the missing kind.

### Why it is not a patch

The step loop iterates melody slots, so a grid can only *keep* or *drop* one. Fixing this
means slots a grid position can create, which changes:

- `head_skeleton` — rests become time rather than skipped elements, and it must emit chord
  slots as well as note slots. (`Head` no longer appears here: stages 1 and 2 built the
  timeline it would have had to carry.)
- `ArrangementStep.melody` — `None` on a slot no melody note created, and all four
  renderers assume otherwise for alignment; **the field half of this is done** (step B
  made it `Optional` and taught the renderers to print the absence blank), so only the
  `melody_alone_case` kind remains;
- `decisions.melody_alone_case` — an invented slot has no melody note to be alone *with*,
  so its `kind` vocabulary would need a fifth value or the slot would never reach it.

That is a different order of change from anything in this file so far, and it is the
same boundary the restructure draws: **a harmonisation engine whose input is a chord
timeline, not a list of melody notes.** Three independent findings now point at it —
this item, item 9's "name the generator, not the axis value", and the fact that
`harmony=` is inert on the melody-bearing route while `non_chord_tone` was inert on the
comping one (the latter **closed by §9.3 step C**).

### The rule it suggests

**A rhythm needs a source of its own.** Where the grid's positions are filtered out of
the melody rather than generated from the metre, a quarter of them vanish silently, and
no warning can be issued because the question was never asked. The same shape as item 8:
a method whose comment describes the correct behaviour while the code does the opposite,
except here the comment is *correct* and only the reader's inference was not.

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
# 10. the chord timeline: a bar the melody does not enter
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

# the walking bass has the same limit, at bass.py:835 ('every bar the melody touches')
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

---

## 8. `upper_midi_notes` dropped the melody and kept the thumb (walking bass)

**Status:** FIXED. See "The fix" below. Found while adding the `melody` and
`melody_bass` textures — since deleted in favour of the `voices=soprano` spelling
(`docs/one-fact.md`) — which are the first outputs built entirely from single-note
voicings and so the first to ask that method what it returns.

### The symptom

A walking-bass staff re-struck notes that were already ringing. The shape was
articulated, then broken into again a beat later, where it should have been held:

```
 B*|-3-----3-------------      the B string is struck twice in one bar
 B*|-3-------------------      and should sound once and ring
 e*|-8-8-8-8-------------      the same, twice more
 e*|-8-8-----------------
```

This is the exact behaviour `Voicing.upper_midi_notes` exists to prevent: its
docstring says excluding the thumb "is what lets a `bass_only` step read as a *held*
upper shape with a moving thumb", and `tabstaff._collapse` reads it for exactly that
hold-versus-strike decision.

### Why the obvious check misses it

Nothing in the arrangement is malformed. Each step's frets, span, chord tones and
playability are all correct; the fault is in which notes the renderer compares. And
the suite was green over it, because every existing walking-bass fixture puts the
thumb on the **low E**, which is the one case the defect does not affect.

### The root cause

The method filtered by **list position** while comparing against a **string index**:

```python
return [
    midi
    for index, midi in enumerate(          # index is 0, 1, 2 ... a POSITION
        GuitarFretboard.fret_to_midi(index, fret)
        for index, fret in enumerate(self.frets)
        if fret >= 0
    )
    if index != bass_string                 # bass_string is a STRING index
]
```

The comment immediately above it read *"Filtered by string index, never by position in
a filtered list: the two are different things"* - describing the correct behaviour
directly above the incorrect code. The inner generator yields bare pitches, so the
outer `enumerate` numbers them by their order in the filtered list. The two coincide
only when the thumb is the lowest-indexed sounding string.

So for any step where the thumb sat on the 5th or 4th string, the filter kept the
**thumb** and dropped the **melody**. Measured on "But Not For Me" bars 1-2 under
`walking_bass`:

```
steps                            : 151
  with a thumb off the low E     :  77
  of those, the old code returned a different set: 77   (every one)
```

and the wrong set was not merely reordered. Three of the four examples returned *only*
the thumb, so a renderer reading them saw a single bass pitch where a melody or a shell
was sounding:

```
D5  tab=x-5-x-x-x-10   old=[50]        fixed=[74]
B4  tab=x-5-x-x-x-7    old=[50]        fixed=[71]
Bb4 tab=x-x-6-x-x-6    old=[56, 70]    fixed=[70]
```

`_place_bass` picks the thumb's string per note by fret proximity, so an A- or
D-string thumb is ordinary rather than exotic - it is simply the case no fixture had.

### The fix

Enumerate the frets once, filtering on the string index in the same pass, so the value
compared is the string rather than a position:

```python
return [
    GuitarFretboard.fret_to_midi(index, fret)
    for index, fret in enumerate(self.frets)
    if fret >= 0 and index != bass_string
]
```

Measured effect on the same head: the rendered staff changes by **37 diff lines**, all
of them spurious re-strikes becoming held notes and held runs extending across the beat
they should have rung through. `tests/test_walking_bass.py::TestUpperVoicesExcludeThe
ThumbByStringNotPosition` pins it over each of the three thumb strings, and asserts the
result does not depend on which one the thumb landed on.

Worth noting for the traps: this is a defect that sat in the tree through a gate run
that reported **OK**, because the tests happened to cover only the one input that did
not trigger it. A passing suite is evidence about the cases it covers, and nothing
more.

---

## 11. A merged step could sound five strings, and no right hand can pluck five

**Status:** FIXED. Fourth of its family in this file: item 1 measured the thumb against the
wrong shape, item 4 let a contradictory flag silence a chord, item 8 dropped the melody and
kept the thumb - and this one is the **budget** none of them was checking, which is how many
strings a *step* sounds at once once a bass note has been merged into it.

### The symptom

`--texture targets --bass walk` printed tabs no right hand can play. The plucks are thumb,
index, middle and ring (`p-i-m-a`), so four strings is the maximum - and bar 1 beat 1 of
"Tenor Madness" was `7-9-x-8-12-10`: low E 7, A 9, G 8, B 12, high E 10. Five strings, five
distinct frets, and no barre reduces either.

Measured over the six committed heads, counting what each step actually plucks
(`tabgp._sounding_frets`, which already models the `repeated` and `bass_only` cases):

| arrangement | steps | pluck five strings | five distinct frets | …counting the held shape |
|---|---|---|---|---|
| `--texture targets --bass walk` | 839 | **151** | 10 | 15 |
| `--texture targets --bass anchors` | 688 | **130** | 9 | 10 |
| `--texture walking_bass --bass walk` | 839 | 0 | 0 | 0 |
| `--texture uniform --bass walk` | 643 | 0 | 0 | 0 - the axis is refused |
| `_place_bass` over the generated corpus, all 12 bass pitch classes | 86,315 placements | - | - | 8 |

**281 steps in six heads**, and the two fret columns are the smaller question
[docs/fingering.md](fingering.md) §4.3 had asked. 19 of the 281 also need five distinct
frets outright; 6 more need five once the shape still being *held* is counted, and those
hold rather than strike - only the thumb plucks, so the right hand is fine and the left one
fails. The **256** the fret count could not see are steps where a barre covers the frets and
the right hand still has only four digits.

### Why the obvious check misses it

`tests/test_walking_bass.py::TestTheInvariant` is the amended playability invariant for a
step carrying a bass, and it states the right thing about the wrong limb: the upper voices
must be one `supported_string_sets()` entry, "with the thumb required to sit outside them
and below them". A **four**-string upper shape with a thumb under it satisfies every clause -
two supported sets' worth of notes in one step - and that amendment was written for
`walking_bass`, whose targets are shells, so the fourth string was never spent. `targets`
spends it: its target palette is `("drop2", "drop3")`.

Two structural reasons it survived a green gate:

- **The merge is after selection**, deliberately ("the bass is written into the fret vector
  only once `_best_voicing` has returned, so it cannot enter the cost tuple by
  construction") - and every `supported_string_sets()` assertion in the suite is on a
  *voicing*, pre-merge. Nothing asserted the invariant on a **step**.
- **`bass_allowed` asks the wrong capacity question.** `thumb_capacity` counts free thumb
  *strings*, and `targets` has one, so the axis was allowed; "is a finger free" was never
  asked. `uniform` fails the string question and is refused, which is why the defect could
  only appear under `targets` - the very texture the refusal message recommends ("Try
  texture='targets', or drop the bass").


### The fix

A **budget**, in the place the string capacity already lives. `grips.thumb_safe_grips`
derives from `GRIP_STRING_SETS` that a grip able to sound four strings cannot be offered as
a *target* while a bass note is being placed under it, and that a palette with nothing left
falls back to the widest statement that leaves a finger free:

```
("drop2", "drop3")          -> ("shell",)   # the targets texture's targets
("shell", "interval", "melody") -> same     # its fills: already inside the budget
()                          -> ()           # walking_bass's fills: "play nothing"
```

`decisions.resolve_texture_grips` applies it to the **target** role only, and only for a slot
that `movement.py` has already decided carries a bass note (`slot.bass is not None`). That last
part is not a detail: `anchors` leaves most beats bare, and a target with nothing underneath
it may use all four strings.

Rejected alternatives, with their costs:

- **Make `_place_bass` respect a fret budget** - prefer a candidate that keeps the hand
  inside four frets. It leaves the five *plucks* intact, which is the defect; and in the
  measured case no playable candidate exists at all (the A string is occupied by the shape,
  and the only B below the chord's lowest pitch is fret 7 of the low E), so it would delete
  281 thumb notes rather than fix them. **The last number is wrong and item 12 corrects it**:
  stated over the hand rather than over `sounding_frets` the fret budget deletes exactly
  **one** note in the committed heads. The rejection still stands for *this* defect - it
  leaves the five plucks - and the budget is what item 12 ends up using for its own.
- **Refuse the axis, as `uniform` does.** Consistent - it is what `bass_allowed` does when a
  palette can never host a thumb - but it removes every thumb note under `targets` (529 of
  839 steps on the walk row), where thinning the target keeps both the harmony and the line.
- **Gate it at selection time** - drop the four-note target when a thumb will follow. That
  puts a finger rule inside `voicing_cost` and entangles it with [docs/fingering.md](fingering.md)
  §5 step 3, which is still undecided.

### Measured after

| row | before | after |
|---|---|---|
| `targets --bass walk` | 151 five-string steps | **0**, and byte-identical to `walking_bass --bass walk` |
| `targets --bass anchors` | 130 | **0**, with 9 drop-2 and 19 drop-3 targets kept where the thumb plays nothing |
| `targets --voices none` (comping) | 0 | 0 - unchanged |
| `walking_bass`, `uniform` | 0 | 0 - unchanged, arrangement fingerprints identical |

**No pinned tab moved**: the suite is green at the same count, because no test had pinned a
`targets` + thumb arrangement. What the rule costs: a target whose quality has no shell -
`Bmaj` under a `D5` melody, say - is a melody alone over the thumb rather than a four-note
shape nobody can play, which is the outcome `walking_bass` has always had.

### The tests

- `tests/test_texture.py::TestTheRightHandBudget` - the rule itself: the per-grip pluck
  counts, the empty palette, the inertness without a thumb, the caller's `grips=` still
  narrowing *after* the budget, and an arrangement-level sweep.
- `tests/test_walking_bass.py::TestTheInvariant::test_no_step_plucks_more_strings_than_the_right_hand_has_digits`
  - the invariant's second half, swept over every committed head with
  `tabgp._sounding_frets`, which is the renderers' own answer to what a step plays.
- `tests/test_texture.py::TestTheRightHandBudget::test_the_premise_that_the_targets_texture_names_four_string_grips`
  - the premise, so the rule cannot pass vacuously if `targets` ever becomes thumb-safe on
  its own.

Worth noting, for the traps: this is item 8's shape again. A green gate said nothing about a
class of step that no test built, and the class was one flag combination away from
combinations that *were* tested. The count that would have caught it - steps plucking more
strings than a hand has digits - is now asserted rather than reasoned about.

### Reproducing

The counts come from a throwaway script (not committed - `AGENTS.md` trap 8): load each
`tests/data/` head with `headxml.arrange_xml_head`, ask each step's `tabgp._sounding_frets`
for its length, and count the ones over four. To see the defect itself, run the same script
against the pre-fix tree:

```bash
git worktree add /tmp/pre d288fce
cd /tmp/pre && PYTHONPATH=/tmp/pre <repo>/.venv/bin/python /tmp/count_plucks.py
```

---

## 12. A `bass_only` step could need five frets, and no left hand has five fingers

**Status:** FIXED. Item 11's sibling: the same step, the same merge, and the *other* hand. Item
11 budgeted the strings a step **plucks**; this one budgets the frets a step **holds**, and the
two are stated over different parts of the step, which is why neither could see the other's
defect. It is also the first defect `arranger/fingers.py` was written for, and the first one it
fixes - [docs/fingering.md](fingering.md) §4.3 opened with the question.

### The symptom

"Tenor Madness" bar 40 beat 1.0, `--texture targets --bass anchors`, printed

```
x-x-x-x-x-10     <- the step's own vector: the melody D5, tied
```

on top of a shape the hand is still holding:

```
x-9-x-8-12-10    <- the previous strike, a drop-3 Bmaj: F#3, D#4, B4, D5
```

A `bass_only` step re-states nothing above the thumb, so those four notes are still ringing -
and the walk's `B` lands on the low E at **fret 7**, which is a fret none of them uses. The
hand must cover `{7, 8, 9, 10, 12}`: **five frets for four fingers.** One finger holds one fret
and no finger holds two, so the step is not hard, it is impossible.

There is no better placement to choose. The candidates for `B` under this hand are:

| string | fret | verdict |
|---|---|---|
| low E | 7 | sounds `B2`, below the shape - **the only survivor**, and five frets |
| A | - | occupied by the held shape (fret 9) |
| D | 9 | sounds `B3`, which is *above* the shape's `F#3`, so `_place_bass` forbids it |

So the choice is between an unplayable tab and a missing note.

### Why the obvious check misses it

- **Item 11's sweep counts plucks.** A `bass_only` step plucks one string, so it passes a
  four-string budget with room to spare - correctly, since the right hand really is fine. What
  fails is the left one.
- **`fret_span()` reads the step's own vector**, which for a `bass_only` step is the melody and
  the thumb - two frets. Item 1 already records that a per-step span is the wrong measure for a
  merged step at all.
- **`test_the_thumb_stays_within_reach_of_the_fingers` measures distance**, from the thumb's
  fret to the held shape's range. It is satisfied here: fret 7 is one fret below the shape's
  lowest (8). Distance is not the question; the count of frets is.
- **No test swept the fret budget over an arrangement.** `TestTheInvariant` swept the string
  budget, and said so in its own docstring.

### The two counts this measurement had to get right

The same tree, three ways of stating "the hand" (seven committed heads x five
`texture`/`bass` rows, **3,697 steps**):

| the hand is… | steps needing five frets |
|---|---|
| the ringing shape, plus the thumb (`held` + candidate) | **1** |
| `sounding_frets`, plus the thumb - what `_place_bass` already maintains | **10** |
| `structure`, plus the thumb - the previous thumb note dropped | **1** |

The middle row is the trap, and it is **item 4's mistake made backwards**. `sounding_frets`
carries the step's own vector as well as the held shape, and under `bass_only` nothing above
the thumb strikes at all: a melody carried on a string the held shape does not use is a note
the hand is *not* holding, because it is already sounding elsewhere. Item 4's Stage 4 found the
mirror-image error when it compared a melody by string instead of by pitch ("wrongly counts a
step whose melody is already sounding on a different string"). Charging nine playable steps for
a note nobody plays is that mistake in the other direction, and it is a factor of ten.

The last row is recorded as **agreeing** rather than differing: on every committed step the
previous thumb note's fret is one the shape already holds, so dropping it changes no answer.
`can_fret` is called on `held` rather than on `structure` anyway, and that is a decision about
physics - the string is ringing, so it is fretted - rather than about the count.

### The fix

A **filter**, in the one place a fifth fret can appear. `fingers.can_fret` is §4.3's refusal
stated over a bare vector (`len({fret for fret in frets if fret >= 1}) <= 4`), because the
caller has two shapes merged into one hand and no `Voicing` to point at. `bass._place_bass`
calls it on the held vector with the candidate fret written in, and skips a candidate that
fails:

```python
hand = list(hand_base)          # the shape still ringing
hand[string_index] = fret       # the thumb's own string replaced, not added to
if not can_fret(hand):
    continue
```

`_attach_bass` already had the right answer for a refused note - **the step survives and the
bass is reported** - so nothing else needed to change. Three things are worth stating:

- **It is a filter and not a preference, and that was measured rather than assumed.** Item 11
  rejected a fret *preference* for its own defect, and for this one there is nothing to prefer:
  only one candidate survives `_place_bass`'s existing filters. The rejection in item 11 still
  stands for the five-string defect; its cost estimate for the filter was wrong, and that is
  corrected there and in the count above.
- **It is the fourth thing `held` decides.** `_place_bass`'s docstring lists three questions
  the held shape answers - which string is free, whether the note sounds below the structure,
  and where the hand is - and this is the fourth.
- **A refused bass note is now two different failures** sharing one message: no free string
  below the melody, or a hand that would need five frets. The warning names both, because a
  diagnostic that names the wrong cause is how item 4's diagnosis went wrong twice.

### Measured after

| row | before | after |
|---|---|---|
| `targets --bass anchors`, "Tenor Madness" bar 40 beat 1.0 | 5 frets for 4 fingers | **0** - the thumb is refused, the step keeps its upper voicing |
| every step of seven heads x five rows (3,697 steps) | **1** | **0** |
| pinned tabs, whole suite | - | **none moved**: green at the same count, plus the new tests |

What the rule costs: **one** bass note, on one beat, in the committed corpus. That is the trade
this fix takes deliberately - a bass note a player cannot finger is not a bass note, and the
alternative was a tab nobody can execute. It is also why the rule is a filter rather than a
palette change: thinning the *target one slot earlier* would have kept the note, and it would
have touched the **7** slots that hold a four-fret shape into a `bass_only` step in order to
fix one, of which 6 were already playable.

### The tests

- `tests/test_walking_bass.py::TestTheInvariant::test_the_left_hand_never_needs_more_than_four_frets`
  - the invariant's left-hand half, swept over every committed head. It reads **1** on the
  pre-fix tree and **0** after, and its docstring carries both counting decisions above.
- `tests/test_walking_bass.py::TestBassPlacement` - three cases at the function: the refusal;
  the same call with a held shape one fret smaller, so the *budget* is what decided it; and a
  pair where the two nearest candidates are refused and the far one is taken, so the budget
  outranks proximity.
- `tests/test_fingers.py::TestTheFourFretBudget` - the predicate itself: open strings and mutes
  cost nothing, four frets is the limit, one shared fret is one finger, and the merged hand the
  engine refused.
- `tests/test_fingers.py::TestTheEngineUsesItForOneQuestion` - **the inverted inertness test**
  (`AGENTS.md` trap 5): the set of engine modules importing `fingers` is asserted to be exactly
  `{bass}`. It was `TestTheModuleIsInert`, and inverting rather than deleting it is what makes a
  *second* caller visible.

### Reproducing

The counts come from throwaway scripts (not committed - `AGENTS.md` trap 8): load each
`tests/data/` head with `headxml.arrange_xml_head`, walk the steps keeping the last *struck*
one (the same rule as `bass._held_shape`), and for a `bass_only` step count the distinct frets
of the held vector with the thumb's string overwritten by its fret. Run the same script against
the pre-fix tree to see the defect:

```bash
git worktree add /tmp/pre HEAD
cd /tmp/pre && PYTHONPATH=/tmp/pre <repo>/.venv/bin/python /tmp/count_frets.py
```

## 13. A refused thumb note is usually not the shape being unplayable, and the pool recovers only ten of them

**Status:** DIAGNOSED, NOT FIXED — recorded, with the decision left open. This is the question
[docs/fingering.md](fingering.md) §4.3 leaves hanging: item 12 asked whether a *step* is playable,
and this asks whether the **selector** should have left room for the thumb in the first place. It
was measured after §2.5's right-hand reach landed, on the same seven heads and five rows item 12
counted. The refusals are **53**, not the one note item 12 priced; the dominant cause is a third one
that neither the message nor item 12 names; and the pool can recover **10** of them without changing
which notes the chord states — every one of those ten by giving up the span bucket.

**Every count in this item is a measurement of commit `d9403e5`** — the tree this item was written
in — and it refuses **39** today, because two commits since have moved it. Nothing above is wrong:
it is a "before" measurement, which is the trap `AGENTS.md` trap 8 names, and re-running the same
instrument on the current tree reproduces both figures exactly. The re-measurement, the attribution
of every difference, the pool lever's current split, and the **walk's own pitch** as a fourth lever
are in the two sections below; the corrected numbers are the ones to quote.

### The numbers are 39 now, and both moves are attributed

The instrument is the one this item describes, run against five trees rather than one: the seven
committed heads × the four bass rows, `_place_bass` wrapped with the shape snapshotted *before* the
call. `git worktree add /tmp/item13 d9403e5` is the reproduction, and no lever was guessed — each
row is the commit whose change could have moved it, measured.

| tree | change | calls | refusals | causes (string / octave / fret) | waltz | BNFM | IWDAR | TM |
|---|---|---|---|---|---|---|---|---|
| `d9403e5` | — (this item's tree) | 1500 | **53** | 0 / 52 / 1 | 30 | 12 | 8 | 3 |
| `5fcdbe3` | the four `drop24` sets banned | 1500 | 53 | 0 / 52 / 1 | 30 | 12 | 8 | 3 |
| `b0908ac` | `maj: {2: add9}`, `m: {2: madd9}` rows | 1500 | 51 | 0 / 50 / 1 | 30 | 12 | 8 | **1** |
| `ea2de78` | the palette rescue | 1500 | 51 | 0 / 50 / 1 | 30 | 12 | 8 | 1 |
| `f4f1af0` | item 15, the metre fix | 1500 | **39** | 0 / 38 / 1 | **18** | 12 | 8 | 1 |

Two of the five move nothing, and that is worth as much as the moves: **the `drop24` ban is inert for
the refusal count**, and so is the palette rescue. The two that moved it were neither of them aimed
at this item — a non-chord-tone table gaining two triads, and a beat being an eighth note too short —
which is the general form of the trap: an unrelated commit can invalidate a recorded measurement.

The per-head figures above count **every** refusal, and 5 of them are `bass_only` steps (4 of the
waltz's `Gm7` figures and TM's `Bmaj`), which is why this item's own per-head list — 26 / 12 / 8 / 2
— reads 4 and 1 lower on those two heads. Its list was the *non-`bass_only`* population, so 26 + 12
+ 8 + 2 = 48 and the 5 make the 53. On the current tree that population is **34**: the waltz 14,
BNFM 12, IWDAR 8, TM 0.

### The symptom

The message that already exists,

```
Warning: no playable bass note for bass G - no free string below the melody, no octave
of that pitch below the shape, or the hand would need a fifth fret; the step keeps its
upper voicing
```

The middle clause is **not** in the message this item was written about — it named the first and
the third only, while 52 of the 53 refusals were the second. That is fixed as part of the
re-measurement below (three clauses, one fixture per cause, `tests/test_walking_bass.py::
TestTheRefusalMessage`), and pinning it turned up a second defect on the same two lines: the warning
was routed with `(diagnostics or default_diagnostics())`, so a caller's still-empty collector was
replaced by the printing default and lost the run's first refusals — `docs/open-issues.md` item 16.

It fires **53** times over the seven committed heads under the four rows that run a bass line
(`uniform` has none) — **39** on the current tree; the table below is this item's own tree. Two independent counters agree: the engine's own warning text, and a wrapper
on `bass._place_bass` recording every call and every `None`.

| row | `_place_bass` calls | refusals (= the warnings) |
|---|---|---|
| `uniform` (the default) | 0 | 0 |
| `targets --bass walk` | 544 | **15** |
| `targets --bass anchors` | 206 | **12** |
| `walking_bass --bass walk` | 544 | **15** |
| `walking_bass --bass anchors` | 206 | **11** |

Every refusal is a beat that was *meant* to carry a bass note (`slot.bass` is not None) and does
not: the merge happens after selection, the placement is refused, and the step keeps its upper
voicing. That is **53 of the 1,500** beats that were meant to be walked (3.5%), concentrated in four
of the seven heads — and as **9 distinct figures** recurring across the rows ("The Jitterbug Waltz"
26 events, "But Not For Me" 12, "I Was Doing All Right" 8, "Tenor Madness" 2).

### Three causes, and the third is the common one

`_place_bass` survives a candidate only if a string is free, the note sounds **below** the shape,
and the hand can hold the resulting frets. Each refusal was attributed by replicating that loop,
and the replica was checked against the real function's return on **every** one of the 1,500 calls,
so a disagreement would be reported rather than believed (it was, at first — see the alias trap
below).

| cause | refusals |
|---|---|
| no free string (every `BASS_STRING_INDICES` string already sounds) | **0** |
| **no octave of the walk's pitch below the shape** | **52** |
| five frets for four fingers (item 12's own defect) | **1** |

The middle row is the one nobody had counted, and the message does not name it. Worked case: "The
Jitterbug Waltz" bar 5 beat 1, `--texture targets --bass walk`, `Ab9`, melody C4.

```
4-x-4-5-x-x   <- chosen: Ab2, F#3, C4 - root, 7th, 3rd
```

The walk wants `Ab`. Every fret for `Ab` on the free A string gives `Ab3` (54), which is *above* the
shape's own `Ab2` (44); the only `Ab` below 44 is `Ab1` (32), which is below the instrument's low E
(40). The string is free, the note is playable, and there is no octave of it beneath the shape.
**30 of the 48** selected refusals are this shape: the chord's own bottom voice is already the
walking note's pitch class, an octave up, so the thumb would double it rather than state anything
new. The other 18 are a pitch the shape does not have down there at all.

### What a retry would buy, and what it costs

The question the plan asked was: *does the pool the selector chose from contain a shape that could
have hosted the thumb?* It was answered with the real `_place_bass`, run over the pool captured from
the real `select_step_voicing` call:

| | refusals |
|---|---|
| a candidate in the same pool could host the thumb | **48** |
| none could (measured) | 0 |
| the shape was not a selection at all (`bass_only`: the melody alone) | 5 |

So 48 of the 53 are "recoverable" — but not for free. Re-running the engine's own rule over the
hosting subset (`select_step_voicing(hosts, …)`) gives a shape that is worse **by the tuple's own
ranking** in every one of the 48:

| first criterion to differ | refusals | the move |
|---|---|---|
| 3 span (bucketed) | **26** | 0.0 → 2.0: a 3-fret reach where the shape had 1 |
| 5 movement | **10** | 19.0 → 24.0 (8), 5.0 → 10.0 (2) |
| 4 position | **8** | 0.67 → 3.0 |
| 1 neck window | **4** | 0.0 → 1.0: a note lands on fret 1, outside 2–13 |

And the harmony is not always preserved:

- **10 of the 48** have a hosting shape that sounds the **identical notes** (3 per `walk` row, 2 per
  `anchors` row). Every one of those ten trades the span bucket (0.0 → 2.0) and nothing else, so it
  is the only strictly harm-free form a retry could take.
- **26 of the 48** have a host with the same pitch *classes* — the same chord, with an inner voice
  in a different octave.
- The other 22 would change which notes the chord states, and the worked case shows what that means:
  the hosting shape there is `x-3-4-5-x-x` = `C3, F#3, C4` — **the root is gone and the 3rd is
  doubled.** `voicing_cost` cannot see that: both shapes are three notes and both are all chord
  tones, so criteria 0–2 tie and span decides. A bare retry would therefore swap a root-bearing shell
  for a rootless one in order to keep a bass note.

### Why this is not a defect in `_place_bass`

All three filters are right, and dropping the note is deliberate policy — "a step is never dropped
because the thumb could not reach it". What the measurement refutes is the *hope* that the selector
could cheaply have left room: the shape-level lever exists, but it recovers **10 of 53** notes (and
**0 of 34** on the current tree — the ban took the same-notes hosts with it), it always pays the span
bucket, and its wider form changes the harmony. The *walk's* pitch does not pay the bucket and reaches
12 of 38, which is the fourth lever below. That is the same shape of answer §4.4 reached for the
finger skip, arrived at the same way — which is why nothing was built.

### The pool lever's strict form is now empty

This item's own lever, re-measured the same way (the pool captured from `select_step_voicing` and
paired to the step by object identity, the host test asked of the real `_place_bass`):

| | `d9403e5` | current tree |
|---|---|---|
| refusals checked (non-`bass_only`, with a pool) | 48 | **34** |
| a host exists | 48 | 34 |
| …sounding **identical notes** | **10** | **0** |
| …the same pitch classes, an inner voice in another octave | 26 | 12 |
| …asserting other notes | 22 | 22 |

The middle row's 26 and 10 are nested rather than disjoint in this item's prose (10 + 26 + 22 = 58
against 48), which the exclusive re-measurement settles: the 10 identical-note hosts *are* among the
26 same-class ones, leaving 16. What the table says that matters is the third row: **the only form of
this lever that changes nothing musically recovers 0 today**, where it recovered 10 on its own tree.
The ban is why — the hosts that sounded the chosen shape's own notes were its *other* `drop24` string
sets, and those are the sets that are gone. So this lever now costs a harmonic change on every
refusal it could recover, at the span bucket, and §4.4's price is being paid a second time.

### The lever nobody measured: the walk's own pitch

Both levers above change the *upper shape*. There is a fourth one, and it was not measured until the
current tree made the numbers small enough to read: the refusal is usually a note the **walk chose**,
so what if the walk had stated a different pitch on that beat? Asked of the real `_place_bass`, on the
same shape — no re-selection, so **no tuple criterion is touched at all**, unlike the identical-notes
retry above, which pays the span bucket on every recovery.

Over the 38 "no octave below" refusals of the current tree, by the role of the refused beat:

| role | outcome | count |
|---|---|---|
| anchor | **a chord tone was placeable** | **12** |
| anchor | only non-chord tones placeable | 12 |
| anchor | nothing placeable at all | 8 |
| approach | nothing placeable | 4 |
| enclosure | nothing placeable | 2 |

- **The ceiling is 24 of 38**, not 52: 12 recoverable by stating a chord tone and another 12 only by
  stating a note outside the chord — and all 12 of those are **anchor** beats, where a foreign pitch
  is least excusable. **14 of the 38 cannot be helped by any pitch at all**, and the 6
  approach/enclosure ones are chromatic by construction, so they were never recoverable this way.
- **24 of the 38 are a doubling**: the walk's pitch class *is* the shape's own bottom pitch class an
  octave up, so the thumb would restate what the chord already sounds. This item saw the same fact
  ("30 of the 48") and the re-measurement agrees in kind.
- **All 12 chord-tone recoveries are one head, one chord, three bars**: "But Not For Me" `Cm7` bar 3,
  19 and 23 beat 1, where the walk wants the root and the shape already sounds it; the placeable
  substitutes are `G3` (43) and `Bb3` (46) — the 5th and the 7th — and `Bb` is *continuous* (within
  the engine's own ≤ 4-semitone term) under both `walk` rows.
- **No pipeline change is needed, and none would pay.** The substitution happens after placement, so
  the walk does not have to see the shapes — which is what makes it cheaper than the question implied.
  Feeding shape knowledge back into `_walking_bass_line` (the pass runs before any voicing exists, so
  its beats are fixed before the shapes are) could reach no more than these 24, and could not reach
  the other 14 whatever it knew.

**Not built**, for the reason the other two are not: the recovery is 12 events in one transcription,
it changes what a downbeat states, and the current behaviour — drop the note, keep the shape, report
it — is defensible *precisely* because the chord already sounds that pitch class an octave up. If it
is ever taken up, the protocol is the span bucket's, and the narrow form to measure first is: an
anchor beat, the wanted class already the shape's bottom class, and the substitute ranked by
`_place_bass`'s own key.

### The two counting decisions

- **The shape is snapshotted before the call, not after.** `steps._attach_bass` writes the bass note
  into the very object it handed to `_place_bass` (`frets`, `bass_midi`, `bass_string`), so a wrapper
  that keeps a reference and re-reads it later is describing a *post-merge* shape. The first run
  reported that the replica "disagreed" with the function on **826 of 1,500** calls, every one of
  them a successful placement. Freezing `list(frets)` and `list(midi_notes())` before the call takes
  it to **0**. Any instrumentation of this merge has to do the same, and it is the same aliasing that
  makes `_held_shape` return a copy.
- **"A candidate could host it" is asked of `_place_bass` itself**, not of a re-derived rule, so the
  three filters cannot drift from the answer. The pool is the one `select_step_voicing` was given,
  captured before it returned and paired to its step **by object identity** — because a step whose
  shape was not selected (a `bass_only` step's melody alone) has no pool, and is reported separately
  rather than counted as unavoidable. Those 5 include item 12's five-fret case, whose shape is
  exactly the melody alone: no selector lever can reach it.

### Alternatives, recorded

- **The identical-notes retry.** Keep the rule narrow: on a refusal, re-select over the hosting
  shapes that sound the same notes. Recovers **10 of 53**, always at the span bucket. It overrides a
  *tuple criterion* on those slots, which is what makes it a decision rather than a repair.
- **A bare retry.** Recovers 48, costs span on 26 of them, and can degrade the harmony (the rootless
  shell above). Rejected as a default: it trades a ranking criterion for a note without ranking the
  note's own quality.
- **A pre-selection palette rule**, the `thumb_capacity`-style demand on the target a walk plays
  under. The same trade at family granularity, and it would thin palettes where a bass note is merely
  *planned* — including the 30 slots where the note is already sounding an octave up.
- **Name the third cause in the message.** ✅ **BUILT** — the cheapest honest improvement, and the only
  one that is not a musical decision: 52 of the 53 refusals are "no octave of that pitch below the
  shape", and the text offered the reader two causes, neither of which was it. The message now names
  all three (`steps._attach_bass`), `bass._place_bass`'s docstring carries the measured split, and
  `tests/test_walking_bass.py::TestTheRefusalMessage` pins a fixture per cause. Fixing it surfaced
  item 16 on the same two lines.

### Reproducing

Throwaway script (not committed — `AGENTS.md` trap 8): wrap `steps.select_step_voicing` and
`steps._place_bass` (snapshotting the shape *before* the call), wrap
`VoiceLeadingEngine._attach_bass` for the bar/chord context, and wrap `Diagnostics.warn` for the
independent count. Then load each `tests/data/` head with `headxml.arrange_xml_head` over the five
rows and, for every refusal, replicate `_place_bass`'s candidate loop to name the cause and run the
real `_place_bass` over the captured pool to find the hosts.

---

## 14. A palette that cannot voice a chord used to take the melody note with it

**Status:** FIXED, in two commits. Diagnosed and measured on 2026-08-10.

### The symptom

```bash
python -m arranger head tests/data/but_not_for_me.mxl --grips shell
```

Bar 2 beat 2 of "But Not For Me" is `F4` over an `Ebmaj` triad, and under `--grips shell` it is
**not in the output at all** — 76 steps for 80 melody notes. The only sign was stderr:

```text
Warning: melody F4 is not a chord tone of Ebmaj and the 'extension' strategy found no voicing; keeping the fallback
Warning: No valid drop-2 voicing found for Ebmaj with melody F4
```

A message naming a grip family the caller never asked for, and reading like a fallback that had
happened when the note in fact went missing.

### The chain, each link measured

1. `F` is not a chord tone of an `Ebmaj` triad — it is the 9th.
2. `NON_CHORD_TONE_EXTENSIONS` had rows for `maj7`, `6`, `m7`, `m7b5`, `7`, `7b9`, `9` and `13`,
   and **none for the two plain triads**, so the `extension` strategy found no route and kept the
   fallback.
3. The fallback is the quality-only candidate set, and three families have none by construction:
   `shell`, `duo` and `interval` are built from the chord's own degrees, and `_shell_voicing`
   refuses any shape sounding a note outside the chord. Measured:

   ```text
   get_all_grip_voicings(F4, 'maj', chord_name='Ebmaj', grips=('shell',))  ->  []
   ...                                                    grips=('drop2',)  ->  3
   ...                                                    grips=('drop3',)  ->  2
   ```

4. With no candidates `prepare_step` returned `None`, and the step loop warned and **dropped the
   step**. The melody-alone rescue beside it was gated on `has_thumb or melody_only`, and a plain
   `--grips shell` run is neither.

### It was not one bar

Notes dropped over the seven committed fixtures, against a default palette that loses none on any
of them:

| fixture | `--grips shell` |
|---|---|
| tenor_madness | **157** of 200 |
| The_Jitterbug_Waltz | 18 of 119 |
| i_was_doing_all_right | 18 of 110 |
| heres_that_rainy_day | 14 of 81 |
| Trouble_in_Mind_Blues | 5 of 53 |
| but_not_for_me | 4 of 80 |

Cause, over those **216** notes: **2** are chord tones the shell's geometry could not place, and
**214** are non-chord tones with no route in the table (`maj` 160, `m7` 18, `6` 12, `7` 8, `dim7`
8, `9` 3, `maj7` 2, `m` 2, `7b9` 1). **Zero** were "the route exists and the shell could not voice
it" — the wall was the table and the family, not the fingering.

### What was built

- **The two triad rows** (`maj: {2: add9}`, `m: {2: madd9}`) in `chords.py`. A 9th over a plain
  triad is the one unambiguous reading and `add9` the narrowest quality containing it, and it
  reaches every family including the shell: bar 2 is now an `Ebadd9` shell `x-10-8-10-x-x` (G, Bb,
  F — the 3rd, 5th and 9th). Measured cost: 10 of the 216 notes, and **14 steps of the default
  route change** — including bar 2, whose shape loses the 3rd. See that commit.
- **The rescue is unconditional.** `steps.arrange_progression` plays the tune alone when no
  candidate exists at all, on every melody-bearing route rather than only under a thumb texture or
  a melody-only selection — and records *why* on the step (`ArrangementStep.chord_unvoiced`), which
  `render._step_annotation` prints as `(melody alone - no voicing for this chord)`. A texture fill
  reaches the same shape deliberately and does not set it, and neither does the span demotion (a
  complete shape *did* exist there), so the label never claims something false.
- **`_sounding_melody`**, extracted: three routes build a melody-alone step and only the `NC` one
  reported the octave `get_melody_only_voicing` drops. Measured: 4 texture fills and 2 rescued notes
  on "The Jitterbug Waltz" printed the written pitch over a shape an octave lower; now 0.
- **An honest message**, naming the palette actually in use and saying the step is skipped.

### Measured after

Drops per route over the seven fixtures, before → after; a route not listed is unchanged:

| route | notes dropped | now `chord_unvoiced` |
|---|---|---|
| `--grips shell` | **216 → 0** | 206 |
| `--grips duo` | 53 → 0 | 53 |
| `--grips shell --texture targets` | 152 → 0 | 142 |
| `--texture targets` | 5 → 0 | 5 |
| `--texture walking_bass`, either palette | 0 → 0 | 68 |
| `--melody none` | 3 → 3 | — |

**Nothing else moved**: the default palette, `--grips interval` and the two melody-only selections
are byte-identical, and the walk rows change only by gaining the record. The `--melody none` three
are a different mechanism — the comping route's own `no guide-tone comping shape ... skipping the
slot` — and are **not** fixed here.

### What bounds the rescue

- **`top_strings` is still honoured.** `get_melody_only_voicing` searches *below* the set it is
  given, so D4 under `top_strings=(5,)` comes back on the B string; the rescue refuses that and the
  step is skipped, which is the documented behaviour of a restricted soprano set
  (`tests/test_progressions.py`, `tests/test_grips.py`). This was measured before it was believed:
  without the guard `arrange_progression([("D4","m7","Dm7")], top_strings=(5,))` returned one
  melody-alone step on the B string where it had returned `[]`.
- **A melody no string reaches is still skipped** — below the G3 floor, or past the end of the
  board. `get_melody_only_voicing` answers `None`, which is the documented signal.

### Alternatives, recorded

- **Leave the notes dropped.** Rejected: the loss is silent. Nothing in a tab says a note should
  have been there, and the warning named the wrong grip family.
- **Route to the default palette for that step** (treat `grips` as a preference, the way the neck
  window is). It restores tune *and* harmony — the default palette voices all 216 — but it changes
  what `--grips shell` means at those steps, so it is a decision about a documented flag rather
  than a repair.
- **Fill in the rest of the table.** The 214 no-route notes are mostly degrees whose reading is
  genuinely ambiguous, which is why the table lists only the unambiguous ones; this is not a
  table-completing job.

### Tests

- `tests/test_non_chord_tones.py::TestThePaletteRescue` — the step survives the chord it cannot
  voice, the renderer says so, and a step that is also transposed reports both facts.
- `tests/test_non_chord_tones.py::TestExtendedExtensionMappings` — the two new rows resolve, and the
  class's own table invariant covers them (degree outside the source, inside the target, top-able
  by an inversion).
- `tests/test_headxml.py::TestANarrowPaletteNeverLosesTheTune` — 80 steps for 80 notes under
  `--grips shell` on the reported head, the bar-2 note voiced as an `Ebadd9` shell, and the one
  rescued step named.
- `tests/test_diagnostics.py::test_the_no_voicing_warning` — **inverted**: the message now names the
  palette in use and says the step is skipped, and it is reached only by a melody no string reaches
  at all.


## 15. Every note of a 3/4 head was placed a quarter of a beat early

**Fixed, 2026-10-10**, in `headxml._beat_from_onset` and the two other places that spelled
the same factor by hand (`headxml.chord_slots`, `arranger/bass._melody_timeline`). Reported
by reading the staff `arranger head` prints for `tests/data/The_Jitterbug_Waltz.musicxml`
against the score: the bars were ragged and the notes sat early in every one of them.

### The symptom

The file is 3/4 with `<divisions>6`: bar 1 is an eighth rest then five eighths and bars 2+ are
six eighths, so every measure sums to exactly 18 divisions - a full bar. The head read them a
quarter of a beat early, in every bar:

| | written | read |
|---|---|---|
| bar 1 | 1.5, 2.0, 2.5, 3.0, 3.5 | 1.375, 1.75, 2.125, 2.5, 2.875 |
| bar 2 | 1.0, 1.5, 2.0, 2.5, 3.0, 3.5 | 1.0, 1.375, 1.75, 2.125, 2.5, 2.875 |

Three consequences, each measured:

- **the staff was ragged.** A bar's content is 2.25 beats of music while the barline is drawn
  at `beats_per_bar` - three - so a hole of music appeared before every barline:
  `|-----11--1013--------|` where the same bar is `|-----11--1013--|` afterwards.
- **the GP5 export wrote short bars.** 21 of the waltz's 35 interior measures held 2.25, 2.5 or
  2.75 quarters of music under a signature that calls the bar three wide. All 37 are exactly
  full after the fix - the check `docs/renderers.md` promises catches this family, and the one
  a measure *count* cannot make, because 37 is 37 either way.
- **every `--musicxml` round trip squeezed the head by a further 25%.** Exported and read back,
  the file's own eighths came out at 1.0, 1.281, 1.562 … - the same error applied again on the
  way out, since the positions written are the positions read.

### The chain

`onset / divisions` is a count of **quarters** - MusicXML defines `<divisions>` as the number
of duration units in a quarter note - and a beat is `4 / beat_type` quarters, so the
conversion is `onset/divisions * beat_type/4`. The code said:

    beat=1.0 + (onset / divisions) * (beats_per_bar / 4.0)

**The two agree exactly when the numerator equals the denominator.** 4/4 gives 1.0 either way
and 2/2 gives 0.5 either way, and six of the seven committed heads are one of those two. 3/4
gives 0.75 where it should give 1.0, which is the whole defect. The same quantity appears, as
its reciprocal, in two more places:

| where | expression | in 3/4 |
|---|---|---|
| `headxml._flush_group`, and the `<harmony>` timeline beside it | `beats_per_bar / 4` per onset | 0.75 of a beat per quarter |
| `headxml.chord_slots` - a grid slot's own length | `... / beats_per_bar` | a third too long |
| `arranger.bass._melody_timeline` - a slot's span | `duration * beats_per_bar` | a quarter too short |

The third was **latent**: correcting it moves **0 of the 186** steps of the waltz under
`--texture walking_bass`, because the walk's chord timeline is onset-driven and only a
melody-in-force span reads a duration. It is fixed rather than left, because the next
metre-sensitive rule would have inherited it.

**Why the gate could not see it.** `beats_per_bar` and `beat_type` are the same number in every
head but this one; the only test that read the waltz's beats - `test_walking_bass.py`'s
invented-beat test - derives its expectation from those same beats, so it agreed with itself;
`tests/test_headxml.py`'s "no beat is past the bar line" assertion fails the *other* way (a
stretched bar, not a squeezed one); and the measure-summing check that is supposed to catch
the family ran on the *exporters*, where the waltz was never in the fixture list.

### What was built

- **One conversion, one name.** `headxml._beat_from_onset(onset, divisions, beat_type)`, called
  by `_flush_group` and by the `<harmony>` timeline, so a chord and the note it governs cannot
  disagree about which beat they are on. The two used to spell the expression out separately.
- **`beat_type` reaches the engine.** It is a field on `ArrangeOptions`, a keyword on
  `arrange_progression` and `arrange_slots` (defaulting to 4, so a hand-built progression is
  untouched), and a parameter of `bass._walking_slots` / `_bass_slots` / `_melody_timeline`;
  `arrange_xml_head` passes `head.beat_type`. Before this the engine's only metre was a count.
- **The reciprocal direction.** `chord_slots` divides a length in beats by `beat_type` to get
  whole notes, and `_melody_timeline` multiplies a whole-note duration by `beat_type`.
- **`textures._metric_weight`'s docstring example was corrected.** It read "a 3/4 bar's second
  beat is 1.666...", which is the second beat of no metre in this library or out of it - it is
  a triplet onset mistaken for a beat number, and it survived because no fixture's timing
  depended on it.

### Measured after

- The waltz's onsets are the written ones: bar 1 at 1.5, 2.0, 2.5, 3.0, 3.5 and bar 2 at
  1.0 … 3.5.
- All 37 of its exported GP5 measures are exactly a 3/4 bar, and the staff's bars are uniform.
- A MusicXML round trip leaves every onset from bar 2 on unchanged, to six decimal places.
- **No other fixture moves at all.** The other six are 4/4 and 2/2, where the two spellings of
  the factor are the same number - which is why the whole existing suite passed unchanged
  before and after, and why every new assertion below was checked against the old arithmetic
  rather than trusted.

### Recorded, not fixed

- **The exporter loses bar 1's pickup.** Read back, the written eighth rest then five eighths
  (1.5 … 3.5) becomes five eighths from 1.0: the rest is dropped rather than written as an
  anacrusis. That is wrong under either spelling of the conversion, so it is a separate defect;
  the round-trip test excludes bar 1 and says why.
- **A waltz's beat 3 is still a target.** `textures._metric_weight` names beats 1 and 3 for any
  bar with three or more beats, deliberately ("in 3/4 beats 1 and 3 are targets exactly as they
  are in 4/4"). Before this fix that was unreachable in a 3/4 head - no note's beat landed on
  3.0 - and it is live now, so the waltz is comped on its third beat. Whether a waltz wants
  that is a musical question, not an arithmetic one, and it belongs to its own item.

### Tests

- `tests/test_headxml.py::TestTheMetreHasADenominator` - a bar each of 3/4 (six eighths, and a
  pickup behind an eighth rest), 2/4 and 6/8 - the two metres whose old factor erred the other
  way - plus the committed waltz's own onsets, every onset of every committed head inside its
  own bar, and the round trip with bar 1 excepted.
- `tests/test_walking_bass.py::TestAWalkInventedBeatTakesTheMelodyInForce` - the span unit
  (`duration * beat_type`) on 3/4 and 6/8, and that `beat_type` reaches the timeline the walk
  attributes invented beats through: one invented beat carries `Cmaj7`/E5 at the 3/4 reading and
  `Dm7`/F5 at the 6/8 one.
- `tests/test_guitarpro.py::TestRhythm::test_every_measure_of_a_written_head_fills_its_bar` -
  **extended to the waltz**: 21 of its interior measures were short before the fix, 0 after.
- **All five were run against the old arithmetic** - `headxml._beat_from_onset` monkeypatched
  back to the 0.75 factor - and every one of them fails without the fix.

---

## 16. A warning that was a run's first went to the printer, not the collector

**Fixed, 2026-10-10**, in `steps._attach_bass`. Found while pinning item 13's message.

### The symptom

A refused thumb note was reported with

```python
(diagnostics or default_diagnostics()).warn(...)
```

and `Diagnostics.__bool__` is `bool(self.warnings)` - False until something has been recorded. So a
caller who handed in a **fresh** collector had it replaced by the printing default: the warning went
to stdout and the collector never saw it. The engine's other three call sites (`steps` twice,
`slots`) already asked `is None`; this was the only `or`, and it survived because the engine's own
default path is the truthy-printer one.

### Why it hid, and what it cost

A run's first warning is usually not a bass refusal - a non-chord-tone remark comes first on most
heads - and once the collector holds anything it is truthy, so every later warning is recorded
normally. It shows up only where a **run** of refusals begins the run, because each one in turn finds
the collector still empty. Measured over the seven committed heads × the four bass rows, comparing a
handed-in collector with captured stdout: "But Not For Me" printed **3** refusals per row that the
collector never received, **12** in total, and they are exactly item 13's `Cm7` figures - the ones the
walk-pitch measurement is about. Every other head lost none.

### The fix, and the two tests

`if diagnostics is None: diagnostics = default_diagnostics()`, the form the other three sites use.
`tests/test_walking_bass.py::TestTheRefusalMessage` is what found it (a hand-built refusal and a fresh
collector, asserting one recorded warning), and
`tests/test_diagnostics.py::TestTheLibraryIsSilentWhenGivenACollector
::test_the_first_warning_of_a_run_is_collected_not_printed` pins it where the property belongs, on a
fixture that raises **exactly one** warning - `Ab9` over `C4` under `--texture targets --bass walk` -
so there is nothing to make the collector truthy first. Measured after: **0** warnings
printed-but-not-collected on the same sweep, from 12.

---

## 17. A `harmony=` family the comping route accepts and answers with something else

**Status:** OPEN, DIAGNOSED. Found while sweeping `textures.py` for the present tense: the
comment on `HARMONY_BUILT` claimed all three of the other families were names "nothing is built
on yet", and measuring which of them the comping generator actually voices turned up one that
is accepted and then silently dropped.

### The symptom

`harmony=` is read only by the comping route, and `grips.get_comping_voicings` implements the
degree families it is handed through *arity*: the guide tones, or a lone bass note. It has no
implementation of `full` — "state every tone the quality defines" — because the whole-chord
chord-melody is the **grip** route's job, reached when the guitar sings. But
`harmony_allowed("full", ...)` returns True for every voice selection, so `resolve_harmony`
passes the value through and the comping generator voices guide tones anyway.

Measured on `[("D5","m7","Dm7"), ("C5","maj7","Cmaj7"), ("A4","7","A7"), ("G4","maj7","Gmaj7")]`,
comparing `harmony=full` against the same arrangement with no `harmony` at all:

| arrangement | `harmony=full` gives | equals the default? | warns? |
|---|---|---|---|
| `melody=alto,tenor` (comping) | guide tones | yes | **no** |
| default voices (singing) | the whole chord | yes | no |

The singing row is correct and not an accident of this bug: the axis is inert there, and a
melody-bearing arrangement states the whole chord because that is the grip route's job. So the
same flag is *honoured* on the route that does not read it and *dropped* on the route that
does, with no warning on either.

### Why it matters, and what is not decided

Every other refusal in `textures` is derived and **loud**: `harmony_allowed` refuses a family
the selection has no room for, `bass_allowed` refuses a palette, `grid_allowed` refuses a metre,
and each names what would work. `full` is the one value refused by nothing that resolves to
something other than itself — which is the failure `resolve_harmony`'s own docstring names,
"an arrangement that says something other than what was asked for is worse than one that says
nothing", while doing it.

The fix is not decided, and both directions are live:

- **Refuse it**, as the module refuses everything else it cannot voice — a branch in
  `harmony_allowed`. That would be the first entry there not derived from arity, so it weakens
  the property `harmony_allowed`'s docstring asserts of itself.
- **Build it**, which is `docs/comping-styles.md` §9.4's four-note comping chord. It needs new
  string sets and is deliberately not done, so this is the larger of the two.

Recorded rather than fixed because it is a behaviour change on an axis whose document still
lists four-note comping as a proposal. What is fixed is the *record*: `HARMONY_BUILT` names the
families of `HARMONY_STYLES` the comping generator voices — `guide`, `shell_root` and `root` —
and `full` is not among them. It previously named `guide` alone, which was wrong in the other
direction, since `shell_root` reaches `get_comping_voicings(shell_root=True)` from
`movement._comping_step` and `root` is the lone-bass route.
