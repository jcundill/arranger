# The comp line: a voice-led top voice for the chord part

**Retired.** This was the active plan for the chord part's top voice, and it is the record of
*why* each rule is what it is: the measurements that motivated it, the six rules, the fill, the
four-bar example every rule was tuned against, and — at the end — the measurement taken when it
landed, including the three rules the four-bar figure corrected and the two things the
measurement removed. **The live rules are in
[engine.md](../engine.md) §"The comp line: the top voice moves"**; the code is
`arranger/comp_line.py` (the rules) and `arranger/routes.py` (the narrow); the rendered examples
are in [README.md](../../README.md); and the routing row is in [AGENTS.md](../../AGENTS.md).
Read that section for what the engine does now, and this file for the numbers behind it.

**The status of the plan itself: landed.** P0–P4 are done (the collapse, the line, the fill, the
default change with its measurement) and P5's renderer audit is a test
(`test_comp_line.TestTheRenderersAgree`); P6 was the documentation this header is part of. The one
thing the plan named as separable and did **not** build is the companion defect below — the
`--chord-notes targets` comp that never thins — and it is still open, as is `cost.py:218`'s
hardcoded 9 in [open-issues.md](../open-issues.md) item 7.

Related: [engine.md](../engine.md) §"`get_comping_voicings`: a chord with no melody on top" (the
generator this changes), [comping-styles.md](comping-styles.md) §9.4 (the four-note
comping chord, deliberately unbuilt), [walking-bass.md](walking-bass.md) (the
precedent for a line with roles and a lookahead),
[reharmonisation-proposals.md](reharmonisation-proposals.md) (functional
substitution, deliberately unbuilt).

## Goal

The chord part's top note stops being a plateau and becomes a **line**: the top voice voice-led
through the chord's own tones, in a register the comp owns, on both routes that state a chord with
no tune on the guitar — `--no-melody` and `--chord-fills`.

**It replaces the shipped static comp rather than being offered beside it.** There is no
`--comp-line` flag and no `Request.comp_line` field: the line is *how* the chord part plays the notes
it already states, not a seventh question about what to play, and a one-value vocabulary with an
escape hatch back to a defect is the second spelling the request surface exists without. A flag would
be earned by a **second musically distinct answer** — choosing between voice leading and functional
harmony, say — and that choice is out of scope here.

Two decisions bound it before anything else:

- **Chord tones only.** No foreign top note, no chromatic approach, no enclosure. Those belong to
  the functional-substitution decision, which is [on record as
  declined](history/reharmonisation-proposals.md) and stays declined here.
- **`voicing_cost` is not touched.** The line is a *narrowing of what may be played*, applied
  before the ranking, exactly as `decisions.leaving_room_for_the_bass` narrows for a requested bass
  note. §"Why a narrowing, and not a criterion" below carries the measurement that forces it.

## The problem, measured

Every figure below was taken on the committed fixtures with the shipped code; the recipes are in
§"Reproducing the measurements".

### 1. The comp's top voice plateaus, then leaps

`synthetic_common_8`, 8 bars, `Request(melody=False)`:

```
tops  [65,65,69,64, 65,65,70,70, 70,70,60,60, 62,62,62,62, 67,62,64,64, 62,62,58,58, 58,58]
moves [ 0, 5,-5, 1,  0, 5, 0, 0,  0,-10, 0, 2,  0, 0, 0, 5, -5, 2, 0,-2,  0,-4, 0, 0,  0]
```

26 sounding steps, **13 of 25 moves are 0**, every other move a leap of ±5, ±6 or ±10, and only
8 distinct top pitches. There is no line — and `--chord-notes targets`, the texture whose whole
job is "full on the strong beats, thinner between", does not thin a comp at all (see §"The
companion defect").

### 2. The palette cannot state a chosen tone on top

`grips._search_comping_voicings` keeps **one shape per string set**, chosen by
`key = (max(frets) - min(frets), sum(frets) / len(frets))` (`arranger/grips.py:929`) — the
tightest, lowest shape. `Cmaj7` at three voices therefore offers four shapes and **all four put
the 3rd on top**:

```
x-x-5-4-5-x   x-10-9-9-x-x   8-x-9-9-x-x   x-3-x-4-5-x      top voice E4 (the 3rd), every one
```

Re-keyed to one shape per **(top tone, octave)** the same chord yields exactly
`root / 3rd / 5th / 7th` on top — **8 shapes instead of 4**, the same order of size, so the memo in
`_comping_palette` is unchanged:

```
top pc  0 (degree  0)  x-x-2-4-1-x
top pc  4 (degree  4)  x-x-5-4-5-x
top pc  7 (degree  7)  x-x-9-9-8-x
top pc 11 (degree 11)  x-x-2-0-0-x
```

So the static top voice is not a ranking failure alone: **the palette cannot express the
alternative.** The comping generator's collapse is tighter than the melody route's, which is why a
tune can move the top voice and a comp cannot.

### 3. Widening the palette is not enough — the ranking prefers the repeat

With the widened palette and the *existing* cost tuple, the top still plateaus:

```
67, 67, 67, 67, 69, 65, 67, 67, 67, 67, 72, 72, ...
```

because repeating the identical shape costs `movement = 0`, which is the cheapest answer available.
**`voicing_cost` prefers a static comp by construction**, so no palette widening can produce a
line. The line has to arrive before the ranking.

### 4. Today's opening is an accident

`cost.voicing_cost` scores the first shape of an arrangement with a **hardcoded 9**
(`arranger/cost.py:218`):

```python
if criteria.previous is None:
    position = abs(voicing.avg_fret - 9)     # "start near the middle of the neck"
```

For `Dm7` the two span-0 shapes at fret 10 score `position = 1.0` and win; the root-in-bass
tie-break (`criterion 6`) then picks which of them. So the comp opens at **fret 10** — `10-x-10-10-x-x`
— because a constant said "near 9", not because anything chose it. Nothing in the request, the
metre or the chord decides a comp's register today.

### 5. The collapse fights a register band

Per top tone the kept shape is the tightest, and the tightest is often the highest: `F4` under
`Dm7` exists in the palette only as `10-x-10-10-x-x` (span 0) — the span-1 shape at
**avg fret 5** (`x-5-x-5-6-x`) lost the collapse. So a line that wants `F4` must go to fret 10,
which produces a hand jump inside a bar even when the walk starts low. Any band rule has to fix the
collapse's key as well, or it cannot hold.

### 6. A fill is blind

`--chord-fills` places chords in the tune's notated rests, and those slots carry **no melody
information at all**: `headxml.fill_slots` (`headxml.py:2753`) emits `melody=None`, and the
generator behind them — `grips.get_comping_voicings` — takes no melody argument by design (it is
the melody-blind generator). Measured, `synthetic_repeat_slash` bar 6's rest with
`Request(chord_fills="comp")`:

```
bar6 1.5  Am7   x-10-10-9-x-x   avg 9.7     <- the hardcoded 9 again
bar6 2.0  D9    x-x-4-5-5-x     avg 4.7
bar7 1.0  Gmaj9 3-x-4-4-3-x     melody D4, avg 3.5
```

The fill wanders 9.7 → 4.7 and has no relation to the tune it is leading into. **"Fills to the
following harmonised melody note" is therefore not expressible today** — there is nothing in the
fill's inputs to point at.

### 7. The window is the melody's register, and cannot be narrowed

The tune in this corpus reaches **`Eb5`** (`synthetic_common_8` bar 6 beat 3 — high E string, fret
11), and its harmonised shape sits at **avg fret 12.5**. The tune's own shapes move **3.8 → 12.5**
between two consecutive notes. So `--fret-min` / `--fret-max` are the register the *tune* is
harmonised in and have to stay wide; narrowing them to the comp's register would leave the comp's
highest reachable top **nine semitones below that melody**, and would forbid the fill's approach to
it. That is why the comp's register is a **separate value** rather than the window.

## Why a narrowing, and not a criterion

`AGENTS.md` forbids "a term in the cost" for *how many notes* a part plays, and the bass's requested
note is a *narrowing* rather than a criterion — but neither reason transfers here, and the
measurement above says which design works:

- The bass's rule is **structural**: `cost` sits below `bass_place` in the DAG, so `voicing_cost`
  *cannot* ask where the thumb goes, and no candidate carries a thumb. A comping shape's top voice
  **is** part of the shape, and `SelectionCriteria` already carries `melody_pc`, `root_pc` and
  `bass_pc` — so a line value would be the same kind of thing.
- The texture's rule is about **how many notes** — a change of what may be played at all. A
  top-voice target is a preference *among* equally valid shapes, which is what a criterion is for.

A criterion was measured anyway, because it bounds the register for free: with the window ranked
*above* the line, bar 1 of the four-bar example came out `62,62,62` — the line's `C4`
(`x-x-3-2-1-x`) has a fret outside the window, so an in-window shape that did not state the line's
tone won, three times in a row, and the plateau was back. **The line must win inside its band**, so
the band is applied *by the line* when it chooses the tones it may state, and the narrowing is the
form. `voicing_cost` keeps its seven fields, its order and its meanings.

## The rules

**1. Two registers, and only the second is the comp's.**

- The **window** (`--fret-min` / `--fret-max`, default 2–13) is the register the *tune* is
  harmonised in. It stays wide, for the reason in §7, and it remains a **preference** for every
  other route.
- The **home band** is the register the *comp* lives in: `fret_min + 1`, **eight frets**, clamped to
  the window — so the shipped window gives **3–10**, and `--fret-min` moves the comp's register,
  which is what makes the flags load bearing for the comp as well as for the tune.

  The width is a **value, not a physical constant**, and the measurement is the reason: at 5 frets a
  chord has only two or three tones in the band and the line bounces (`Cmaj7` inside 3–7 has just
  `B3` and `E4`); at 8 frets it has enough to walk through (§"The four-bar example"). A hand-span is
  5 (`fingers.MAX_HAND_SPAN`), and the measurement rejects it.

**2. The palette keeps, per top tone, the shape nearest the home band's middle** — the collapse's
key becomes `(outside the band, |avg_fret − band middle|, span)` instead of
`(span, avg_fret)`. Without this the band cannot hold: `F4` exists only at fret 10 (§5).

**3. The comp's material is the chord's tones reachable inside the home band**, and only those. The
band is applied by the line, so the line always wins within it and nothing is silently overridden
(§"Why a narrowing").

**4. The walk** steps to the nearest tone in the current direction, **never retracing the last two
pitches**. Both clauses are load-bearing and both were measured:

| rule | measured result |
|---|---|
| nearest different tone alone | oscillates — bar 3 came out `67,64,67,64` |
| arpeggio in a direction alone | bounces at the band edge — bar 2 came out `E4,F4,E4,F4` |
| **direction + no-retrace** | bar 2 becomes `E4,F4,D4` — a walk |

**5. The approach** — the last position before a harmony change — takes the current chord's tone
nearest the next *landing tone*: the next chord's tone nearest the previous top, preferring its
3rd. The approach **moves**: it never repeats the previous top (a repeat is a hold, not an approach).

**6. The opening.** On `--no-melody` there is no tune of the guitar's and no neighbour to come from,
so the opening is the tone nearest the **home band's middle**. On a **fill** the opening is the
**last harmonised position** — see §"The fill".

**7. The window bounds everything.** A fill may leave the home band toward the tune, never the
window. `grip_tables.COMPING_EXCLUDED_STRINGS` keeps the high E off the comping palette at every
arity, so a fill can approach a high melody but never meet it: measured, it lands a step below
(`D5` under `Eb5`). That is the intended voicing relationship — the chord part must not be heard as a
melody above the tune.

The exclusion is a property of the **comping** palette and is independent of `top_strings`: it holds
at every arity whatever strings the melody may use. The "one step below `Eb5`" figure assumes the
default `top_strings` (high E available); under a restricted soprano set the fill still approaches
from below, but the pitch it lands on follows the melody's register, which `top_strings` governs.

**8. Bass interactions.** The line shares `routes.comping_step` with the thumb, so:

- **Narrowing order is bass, then line.** `leaving_room_for_the_bass` runs first; the comp line
  narrows what survives, and both record their own `Palette.dropped_for_*` against the palette they
  received. A narrow that changes nothing leaves its field `None`.
- **`place_bass` / `can_fret` stay the final gate.** The line never widens the hand: a top-voice
  move that would need a fifth finger or more than five frets under a requested or carried bass is
  refused, and the step keeps its upper voicing.
- **Carried bass ends the ring on a hand-span failure** — the same rule as any shape change. The
  comp line filters against `slot.bass` (the request), not against a carried fret.
- **Slash bass stays a selector input** (`bass_pc` in `SelectionCriteria`); the comp line narrows
  on top of the already-slash-honouring palette.
- **One-voice comping (`notes == 1`) is a no-op for the line** — there is no top voice to walk.

## The decisions, and what each rejected

| decision | taken | rejected alternative, and why |
|---|---|---|
| the line's material | **chord tones only** | a foreign top note (chromatic approach / enclosure) — deferred with functional substitution; it is an exemption to `voicing_cost`'s first criterion |
| whether the line is optional | **it replaces the static comp** | a `--comp-line` flag — one value plus an escape hatch is not a vocabulary, and the static comp it would restore is the defect, not a style. A choice between line *strategies* (voice leading, functional harmony, …) would earn one, and that is out of scope |
| how the line acts | **a narrowing** before the ranking | a cost criterion — measured: the window outranks it and the plateau returns (`62,62,62`) |
| the comp's register | **a separate home band, 3–10** | narrowing the window itself — measured: the tune reaches `Eb5` (avg 12.5) and must stay harmonisable |
| the band's width | **8 frets** | 5 frets (a hand-span) — measured: 5 distinct tops and two-tone bouncing; 13 (the whole window) — measured: the hand travels 2.7–10.3 |
| the walk | **direction + no-retrace** | "nearest" alone (oscillates); a carried direction alone (bounces at the edge) |
| the fill's opening | **the last harmonised position** | the band's middle — measured: it abandons the hand's register on the first fill note |
| the fill's target | **the next step's top pitch, register as the fallback** | register alone — measured: it misses the tune's own note when the tune is reachable |
| the approach's reach | **bounded by the window** | unbounded — measured: it leaves the caller's stated register |

## The four-bar example

Four bars of 4/4, comping only — `Request(melody=False)`, one chord per bar: `Dm7 | G13 | Cmaj7 | C6`,
four attacks a bar. This is the example every rule above was tuned against.

### Today

```
bar 1  Dm7    10-x-10-10-x-x   top F4 b3    bass D3 root
bar 2  G13    10-x-9-9-x-x     top E4 13    bass D3 2nd
bar 3  Cmaj7  x-10-9-9-x-x     top E4 3     bass G3 2nd
bar 4  C6     x-10-x-9-10-x    top A4 6     bass G3 2nd
tops  [65,65,65,65, 64,64,64,64, 64,64,64,64, 69,69,69,69]
moves [0,0,0,-1, 0,0,0,0, 0,0,0,5, 0,0,0]      distinct 3, zero-moves 13/15
```

One shape per bar, repeated. This is the complaint, in tab.

### With the line — band 3–10

```
bar 1  Dm7    C4 b7   (root)  x-8-7-5-x-x     avg 6.7   start
       Dm7    D4 Root (1st)   8-x-3-7-x-x     avg 6.0   walk
       Dm7    F4 b3   (root)  x-8-x-5-6-x     avg 6.3   walk
       Dm7    D4 Root (1st)   8-x-3-7-x-x     avg 6.0   approach
bar 2  G13    E4 13   (root)  x-x-9-7-5-x     avg 7.0   walk
       G13    F4 b7   (3rd)   x-7-x-4-6-x     avg 5.7   walk
       G13    G4 Root (1st)   x-7-x-4-8-x     avg 6.3   walk
       G13    E4 13   (root)  x-x-9-7-5-x     avg 7.0   approach
bar 3  Cmaj7  G4 5    (1st)   x-7-x-4-8-x     avg 6.3   walk
       Cmaj7  C4 Root (1st)   x-7-9-5-x-x     avg 7.0   walk
       Cmaj7  B3 7    (1st)   x-7-9-4-x-x     avg 6.7   walk
       Cmaj7  C4 Root (1st)   x-7-9-5-x-x     avg 7.0   approach
bar 4  C6     E4 3    (root)  5-x-5-9-x-x     avg 6.3   walk
       C6     G4 5    (3rd)   x-x-7-9-8-x     avg 8.0   walk
       C6     A4 6    (3rd)   x-7-x-5-10-x    avg 7.3   walk
       C6     E4 3    (root)  5-x-5-9-x-x     avg 6.3   walk

tops  [60,62,65,62, 64,65,67,64, 67,60,59,60, 64,67,69,64]
moves [2,3,-3, 2,1,2,-3, 3,-7,-1,1,4, 3,2,-5]
distinct 7 of 16, zero-moves 0 of 15, hand 5.7 – 8.0
```

**The tops and the moves above are still the rule; ten of the sixteen spellings have since
moved.** The palette this table was measured with reached the shell's five frets and could
skip a string, and both are refused now (`grip_tables.COMPING_MAX_SPAN`, the skip rule in
`grip_tables._fills_its_strings`): bar 1's two walks and its approach, bar 2's `F4` and `G4`
walks, bar 3's `G4` and `B3` walks and bar 4's three `E4`/`A4` columns are spelled on
neighbouring strings inside four. **Not one top and not one move changed**, which is what
makes it the same line; the live tabs are `FOUR_BAR_TABS` in `tests/test_comp_line.py`, and
the two rules and what they cost are [engine.md](../engine.md) §"`get_comping_voicings`: a
chord with no melody on top". Bar 4's two `E4` columns have been respelled once more since —
the palette now also refuses a shape that states one pitch on two strings
(`grip_place.sounds_distinct_pitches`), so `x-x-7-9-5-x` became `x-x-7-5-5-x` — and that
leaves the count at ten either way with no top moved.

Every move is a 2nd, a 3rd or a 4th (one 5th). Bar 1 walks the Dm7, bar 2 rises through the G13,
bar 3 falls through the Cmaj7, bar 4 rises through the C6 — and the **inversion changes with the
top**, because choosing the top tone is choosing the inversion (the bass follows from the search,
and `common_grips.md`'s rule — the inversion is named by the bass — still holds).

The same rules at two stabs a bar, and as the Charleston, keep the line:

```
1,3        tops F4 D4 | E4 F4 | G4 E4 | C4 A3   moves -3,2,1,2,-3,-4,-3   zero 0/7
Charleston tops F4 D4 | E4 F4 | G4 E4 | C4 A3   moves -3,2,1,2,-3,-4,-3   zero 0/7
```

### The band width is the one value worth re-tuning

Same rules, three bands, same four bars:

| band | tops | moves | distinct | zero | hand |
|---|---|---|---|---|---|
| 3–7 | `60,62,65,62, 64,65,62,64, 59,64,59,64, 60,64,60,64` | `2,3,-3, 2,1,-3,2, -5,5,-5,5, -4,4,-4,4` | 5 | 0 | 4.3 – 6.3 |
| **3–10** | `60,62,65,62, 64,65,67,64, 67,60,59,60, 64,67,69,64` | `2,3,-3, 2,1,2,-3, 3,-7,-1,1,4, 3,2,-5` | 7 | 0 | 5.7 – 8.0 |
| 2–13 | `57,60,62,60, 64,65,67,64, 71,72,67,64, 60,57,64,67` | `3,2,-2,4, 1,2,-3,7, 1,-5,-3,-4, -3,7,3` | 8 | 0 | 2.7 – 10.3 |

3–7 is a true position comp but bars 3 and 4 bounce between two tones, because `Cmaj7` and `C6`
have only two reachable tops inside five frets. 2–13 gives the longest line and a hand that crosses
the neck. **3–10** is the shipped choice: a line with the hand in the lower-middle neck.

## The fill

A `--chord-fills` slot is a chord in a notated melody rest on a selection where the **guitar sings**
— so the thing the fill has to join is the guitar's own tune, and the fill is the one place the
comp's register and the melody's register meet. The rule is a **bridge between two hand positions**:

- the fill **opens at the last harmonised position** — the register of the last sounding step
  before the rest — so it does not abandon the hand;
- the fill **closes at the next step's top pitch**, falling back to the next step's **register**
  (its `avg_fret`) when that pitch is out of the comp's reach;
- between them it **interpolates**:

```
target_avg(i) = prev_avg + (next_avg − prev_avg) · i / (n − 1)      for the fill's n positions
target_avg(0) = next_avg                                            when n = 1
```

which is "the last position only" at two positions and a gradual run at four. (The first draft used
`(i+1)/n`; that leaves the previous register on the fill's *first* note, which contradicts the
opening rule, and the measurement showed it.)

Measured on `synthetic_repeat_slash` bar 6, whose last shape before the rest is `G4` at **avg 8.0**:

```
the head's real return (D4, avg 3.5)        a high return (Eb5 harmonised, avg 12.5)
bar5   Am7    8-x-7-9-8-x    G4 avg 8.0     bar5   Am7    8-x-7-9-8-x    G4 avg  8.0
bar6 1.5 Am7  x-10-5-5-x-x   C4 avg 6.7     bar6 1.5 Am7  x-10-5-5-x-x   C4 avg  6.7
bar6 2.0 D9   x-3-4-2-x-x    A3 avg 3.0     bar6 2.0 D9   x-x-10-11-15-x  D5 avg 12.0
bar7   Gmaj9  3-x-4-4-3-x    D4 avg 3.5     bar7   ...     Eb5 harmonised

a low return (shape at avg 1.0)
bar6 1.5 Am7  x-10-5-5-x-x   C4 avg 6.7
bar6 2.0 D9   x-3-4-2-x-x    A3 avg 3.0     (target 1.0 — as low as the band reaches)
```

**The rule is symmetric**: the fill climbs into a high return, descends into a low one, and holds
the register it was handed at its opening. "Descent into a low tune" is the same rule read the other
way, and it is included.

Two consequences worth stating, because both are rules rather than accidents:

- **The comp approaches a high melody but never meets it.** `COMPING_EXCLUDED_STRINGS` keeps the
  high E off the comping palette at every arity, so the highest available top is on the B string:
  measured, the fill lands a step below (`D5` under `Eb5`, and `C5` if the approach is bounded
  strictly by the window's edge). That is the intended relationship — the chord part must not be
  heard as a melody above the tune.
- **The strict reading of "approach from above" is not built.** If it means the fill's last note
  sits a step above the target and resolves down into it, that note is frequently **not a chord
  tone** — the same foreign-note decision already deferred with functional substitution. What is
  built is the register reading, which needs chord tones only.

### The invariant boundary

The fills path is the **singing** selection, where the tune is the guitar's own. A melody-aware fill
therefore does **not** touch `tests/test_comping.py::TestCompingMelodyIndependence`, which covers
the `melody=False` selections only. But one function — `routes.comping_step` — serves both routes, so
the rule has to be conditioned on whether the guitar sings:

| selection | the approach targets | why |
|---|---|---|
| `--chord-fills` (the guitar sings) | the next **melody note** / step register | the guitar must join its own tune |
| `--no-melody` (a comp) | the next **chord** | the tune is the horn's; the comp is melody-blind by construction |

**A melody-aware comp under a horn** ("comp to the soloist") is the change that would break the
melody-blind invariant. It is musically real and it is deliberately **not** in this plan — it
belongs on its own, after this.

## The mechanism

| # | change | why this shape |
|---|---|---|
| 1 | **`arranger/comp_line.py`** — a new module | it owns the home band (`home_band(fret_min, fret_max)`) and the rules: the walk, the approach, the opening, the fill's interpolation. **No vocabulary and no sentinel**, because there is nothing for a caller to choose yet (§"Deliberately not in this plan"). It reads `chords`, `grouping` / `grid` and `fingers` only, so it sits **above** them and **below** `decisions` / `routes` / `slot_plan` — the position `texture` occupies (index ~16) |
| 2 | **`grips.CompingRequest` gains the band**, and `_search_comping_voicings`'s collapse re-keys to one shape per top tone, **home-nearest** | the collapse's key becomes `(outside the band, \|avg_fret − band middle\|, span)`. **Gated** by the band's presence, so today's palette and every shipped tab stay byte-identical until the default decision (P4). The memo (`_comping_palette`) is keyed on the request, so the band is part of that key |
| 3 | **The line runs in `routes.comping_step`** | it already reads the arrangement's own history (`last_sounding_step`), and the next chord is a forward scan with precedent (`next_resolution_melody` already scans forward on this very route). **Per-slot, not a pre-pass** — the rhythm already invents the positions, so there is no `_Slot` union and none of the walking-bass machinery |
| 4 | **`ArrangementStep.top_role`** (the `bass_role` analogue), **`Palette.dropped_for_line`**, an `annotation` clause and a witness in `tests/meta_explanations.py` | the explanation contract is part of the change, not a follow-up: a line whose role and direction are invisible on the tab line is a choice the reader cannot see. `top_role` carries the direction, and the clause phrases it ("approach from above" / "from below") |
| 5 | **The renderer audit** | a top voice moving *within* a bar changes hold-vs-strike. `tabscore._is_hold`, `tabstaff._collapse_holds` / `_strikes_here`, `tabxml._sounding`, `tabgp._sounding_frets` — the walking bass's `collapse` fix is the precedent, and it was "mandatory" there for the same reason |

Three lists name the new module, and all three are hand-enumerated gates:

- `ORDER` in `tests/meta_package_dag.py` (a module missing from it is unconstrained by the layering,
  and that test fails);
- `BUDGETS` in `tests/meta_structure.py` (complexity, length and parameter ceilings per module);
- the facade's `from . import (...)` in `arranger/__init__.py`, which is what makes
  `arranger.comp_line` resolve.

It is **not** added to `__all__`: that list is the API a caller names, and a submodule is a path
rather than a name the facade defines.

## Phases, and the gate on each

**No phase starts before the one above it is green.**

### P0 — measure, change nothing

Re-take every figure in this document against the tree as it stands, and file the findings in
[docs/open-issues.md](../open-issues.md) as **item 7** (numbering continues from the record in
[open-issues.md](open-issues.md), so a bare "item 7" citation stays unambiguous).
The item is the two defects that exist today and are *not* this feature's business to fix silently:
`cost.py:218`'s hardcoded 9, and the collapse's `(span, avg_fret)` key that hides a low shape behind
a high one. Each figure is stated **once**, with the recipe that re-measures it.

**Gate**: nothing moves. `make check` reports the same counts it does now.

### P1 — `comp_line.py`

The rules, with no caller yet: `home_band`, the walk (direction, no-retrace), the approach (landing
tone, and it moves), the opening, and the fill's interpolation. **No vocabulary and no sentinel** —
there is nothing for a caller to choose. Unit tests on the rules directly: tones in the band, the
direction reversing at the band's edges, the no-retrace, the interpolation's endpoints (`i = 0` is
the previous register, `i = n−1` the target).

**Gate**: the module is in `ORDER`, `BUDGETS` and the facade; `make check` green; nothing else moved.

### P2 — the widened palette, gated

`CompingRequest` — an internal value in `grips`, **not** a request field — gains the band, and
`_search_comping_voicings`' collapse re-keys to one shape per top tone, home-nearest **when the band
is present**. With the band absent the key is today's, so this phase changes nothing on its own.
`get_comping_voicings`' docstring, the `CompingRequest` docstring and `tests/test_comping.py`'s
invariants move with it.

**Gate**: **every existing arrangement byte-identical** — the committed heads, both routes, every
request the suite sweeps. The gate is not optional: measured, the widened palette **alone** moves the
comp's tops (`[64,64,69,64, …]` → `[72,72,72,72, …]`), so the band's presence is what keeps this phase
inert. The palette-size measurement (8 shapes instead of 4 for a 7th chord) is recorded, not assumed.

### P3 — the line, and the fill

`routes.comping_step` asks the line, narrows the palette to the chosen tone (returning the full
palette when nothing survives, so a chord is never lost), and records `top_role` and
`dropped_for_line`. The fill path takes its opening from the last harmonised position and its target
from the next step's top pitch. `annotation` gains the clause, and
`tests/meta_explanations.py` gains its witness.

**Gate**: the four-bar example and the three fill directions reproduce the figures in this document;
the melody-blind test passes **untouched**; the renderer audit passes (the four writers agree about a
top voice that moves within a bar).

### P4 — the replacement, measured

The line **becomes** the comp. Measure it against the shipped comp over every committed head and
record the diff — this is the step that answers "the automatic comp is weaker than I want", and it is
a **default change**, so it carries its measurement rather than a flag. The precedent is
`docs/history/open-issues.md` item 1's position-level half, a deliberate default change made with the
numbers on the table.

**Gate**: the pinned tab strings in the suite are updated **deliberately**, with the measurement
recorded beside them. They are the acceptance gate; a snapshot mechanism would let a regression pass
by regenerating itself.

### The companion defect, separable

`--chord-notes targets` — the texture whose documented job is "full on the strong beats, thinner
between" — **does not thin a comp**. `routes.comping_step` computes `notes = comping_arity(...)`
without reading the slot's role, so the role is recorded and the arity never changes. Measured with
`chord_on=every-beat`: the singing route gives `(4,3,4,3)` and the comping route `(3,3,3,3)`.
Same complaint as the static top voice, smaller fix, and it can land on its own.

## Acceptance criteria

1. **The plateau is gone.** Over every committed head, the comp's share of zero moves falls toward
   zero, the distinct top pitches rise, and **every move is a walk interval** (a 2nd, 3rd or 4th) or
   an approach — no leaps of a 6th or more inside a chord.
2. **No step loses its chord.** The narrowing returns the full palette when nothing survives it, and
   no shape exceeds `GRIP_MAX_SPAN`. Both are asserted, not promised.
3. **The band holds.** The hand stays inside the home band except where a fill is approaching a
   melody, and never leaves the window.
4. **A fill bridges.** Measured in all three directions: descends into a low return, climbs into a
   high one, and holds the previous register at its opening — the figures in §"The fill".
5. **The melody-blind invariant is untouched.** `TestCompingMelodyIndependence` passes **without
   edit**: a harmony-only line cannot move a fret, and a pitch-dependent one would — which is why the
   comp under a horn stays melody-blind.
6. **The four renderers agree** about a top voice that moves within a bar, as they do about a walking
   thumb.
7. **The pinned tabs move deliberately**, with the measurement recorded beside them.
8. **`make check` reports moved counts, not silence.** A quiet run is not evidence; a moved count is.

## The obligations the tree will enforce

- **The explanation contract.** A new choice arrives with its clause *and* its witness in
  `tests/meta_explanations.py`, in the same commit. A new `*_clause` helper fails a companion test
  until it is registered, because the enumeration is read off the module.
- **No new request spelling.** The band is derived from `--fret-min` / `--fret-max`, which the caller
  already has, so nothing is added to `Request`, `_REQUEST_DESTS` or the run header — and the "six
  questions" prose in `README.md`, `docs/engine.md` and `AGENTS.md` stays six.
- **The layering.** `ORDER`, `BUDGETS`, the facade import; no sibling `_`-prefixed name reached
  across a module boundary; `ALLOWED_EDGES` stays empty.
- **The docs.** `docs/engine.md` (the comping section and `get_comping_voicings`), `README.md` (the
  comping examples, and the `--fret-min` / `--fret-max` row, whose help now has to say that the window
  also governs the comp's register), and the `AGENTS.md` routing row for the comping surface.
- **This document** retires into `docs/history/` with the header the other retired plans carry, and
  its live rules move to `docs/engine.md` — the numbers stay here, because they are this document's
  own business and nothing in the gate is keyed to them.

## Deliberately not in this plan

| not built | why, and where it is recorded |
|---|---|
| **a choice between line strategies** — a `--comp-line` flag, voice leading versus functional harmony | the line **replaces** the static comp, so there is one behaviour and no vocabulary to validate; a second *musically distinct* answer is what would earn a flag, and choosing between strategies is out of scope here |
| a **foreign top note** — a chromatic approach, an enclosure, "a step above the target resolving down" | it is an exemption to `voicing_cost`'s first criterion, and it is the same decision as functional substitution — [on record as declined](history/reharmonisation-proposals.md), with the coverage measurement |
| a **melody-aware comp under a horn** ("comp to the soloist") | it breaks the melody-blind invariant; musically real, and it belongs on its own, after this |
| **per-bar rhythm patterns** (two bars on, two off) | the request's `Rhythm` is one value for a whole selection; a phrase-level pattern is a different kind of object |
| a **four-note comping chord** | `get_comping_voicings(notes=4)` returns **0 candidates**; the design that would allow it is [history/comping-styles.md](history/comping-styles.md) §9.4, unbuilt |
| **`--chord-notes targets` on the comping route** | the companion defect above; separable, and smaller |

## Appendix: Functional substitution and passing harmony (out of scope)

Passing chords and chromatic approach steps are a real technique — approach chords a half-step above
or below the target, diatonic passing chords on weak beats, tritone substitution of a dominant — but
they are out of this plan's scope: they introduce chords the progression does not name, which is an
exemption to `voicing_cost`'s first criterion (every sounding pitch a chord tone), the same decision
recorded in [docs/history/reharmonisation-proposals.md](history/reharmonisation-proposals.md).

This plan's scope is top-voice movement on a *fixed* chord, and it does not need to account for
passing harmony, for three reasons: the line is chord-agnostic (`narrow` re-voices whatever palette
it is given), the fill target is step-based rather than chord-based, and the window and hand-span
gates are properties of the player. What the design must not preclude, if the technique is ever
built:

- **Slot insertion is a separate layer.** Passing chords need new slots between the user's slots, each
  with its own chord and palette; the melody-bearing route's fill logic also assumes the next step is a
  named chord with a harmonised top pitch, which a passing chord under a melody rest does not have.
- **The walk's labels assume a target.** "approach" presumes a target chord; a passing chord is itself
  an approach, so labelling it `approach` would be misleading, and "no-retrace" across an inserted
  step could suppress a move the player actually wants.
- **The comping palette's excluded high E still applies** to any passing chord voiced on the comping
  route, so the approach stays below the tune regardless of the chord.

Recorded here so the design is checked against it, not built into it. The real work — slot insertion,
label semantics, and the first-criterion exemption — is a separate plan.

## The measurement

Every figure below was taken over the **thirteen committed heads**, on
`Request(melody=False)` and `Request(melody=False, chord_on="every-beat")` — the two
selections that comp — with the recipe at the end of this document.

| | before | after |
|---|---|---|
| sounding comp steps | 496 | 496 |
| moves between them | 474 | 474 |
| **zero moves** | **322** | **0** |
| distinct top pitches | 2–8 per head | 5–11 per head |

The plateau is gone: **not one of the 474 moves repeats the top voice**, where more than two
thirds of them did. The moves after the change, by interval:

| semitones | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| moves | 45 | 120 | 103 | 97 | 64 | 10 | 22 | 6 | 7 |

Moves of a **3rd or smaller are 365 of 474 (77%)**; a 4th or a tritone accounts for 74; and a
**5th or more for 35 (7%)**. Those 35 are not scattered - of the 109 moves of a 4th or more,
87 carry a `walk up` / `walk down` role and are the walk **reversing at the band's edge**,
where the two tones nearer the edge are inside the no-retrace window, and the other 22 are
approaches, whose whole job is to arrive on a tone both chords state. Acceptance
criterion 1's "no leaps of a 6th or more inside a chord" is therefore **too strong as
written** — the no-retrace rule and the band edge between them force a jump, and this
document's own bar 3 (`67,60,59`) contains one. What the line does remove is the *plateau*,
and that is the defect the plan was filed for.

The rest of the acceptance criteria:

2. **No step loses its chord.** `test_every_position_states_its_chord` asserts every one of
   the example's sixteen steps sounds and that no shape spans more than five frets; the
   suite's own playability invariants pass unchanged.
3. **The band holds.** Measured over the corpus: of the **496** comp steps carrying a top
   role, **0** has a fret outside the home band. A *fill* may leave the band toward the tune
   (that is its rule) and never leaves the window.
4. **A fill bridges.** `synthetic_repeat_slash` bar 6 reproduces §"The fill" exactly
   (`C4` at avg 6.33 → `A3` at avg 3.0, both `fill down`); `fill up` steps occur in
   `Trouble_in_Mind_Blues` bars 9 and 17, and `TestTheFill.test_the_rule_is_symmetric`
   pins the three directions on the rule itself.
5. **Melody-blind.** `tests/test_comping.py::TestCompingMelodyIndependence` passes
   **without edit**.
6. **The four renderers agree** — `test_comp_line.TestTheRenderersAgree` for `tabscore`,
   `tabstaff` and `tabxml`, and `test_guitarpro.TestAMovingTopVoiceIsFourStrikes` for the
   GP5 file. A top voice that moves inside a bar is four strikes, not one held chord.
7. **The pinned tabs moved deliberately**, and each move is in the commit that made it:
   `test_palette` (a comping step's voices and role), `test_chord_fills` (a fill's frets),
   `test_staff_thumb` (a moved thumb on the A string), `test_palette`'s slash-bass witness
   (`A3`, not `G3`), and `test_tab_rendering`'s wrap count (**82 → 107**), which is the
   clause the line added plus the longer degree names of the shapes it chooses.
8. **The gate moved**: 1315 → 1331 feature tests, 91 meta.

### Three rules the figure corrected, and one sentence it removed

The prose in §"The rules" was written before the measurement, and the engine is the record
where the two disagree:

- **The no-retrace window is one chord, not the last two pitches of the line.** Bar 3
  (`67,60,59,60`) needs the approach's own top (`64`) still forbidden at position 2 and
  *not* forbidden at position 1; a window that spans the change makes bar 3 climb out of
  `59` and bar 4 open by reversing into `57`. `comp_line.read_state` reads the tops of the
  current chord only, and a harmony change restarts both the window and the direction.
- **The band is tested on every fret, not on the average.** `Cmaj7`'s `x-7-x-9-12-x` has
  avg 9.3 and a fret at 12; an average test hands it to the walk in bar 3, and the hand jumps
  to fret 12 for one beat of a bar otherwise at 4–9. `comp_line.LineShape.in_band` is
  `all(...)` over the frets.
- **The approach pivots on a tone both chords state.** §5's "the next chord's tone nearest
  the previous top" gives `65` where the figure has `64` in bar 2; the three approaches in
  the example are all **common tones** (`D4` under `Dm7|G13`, `E4` under `G13|Cmaj7`, `C4`
  under `Cmaj7|C6`), which is also why no special rule is needed to make the approach move:
  the shared tone nearest the previous top *is* the previous top, so the next one is taken.

Two things the measurement **removed** rather than added:

- **A sentence for the palette's line-narrow was cut.** `Palette.dropped_for_line` records
  what the ranking would have played, and a clause for it fired on **fourteen of the
  example's sixteen steps** - with one shape per top tone the ranking and the line agree
  only by accident, so the sentence said the same thing almost everywhere. The field stays
  as the recorded fact (it is how the table above was taken); the *explanation* a reader
  needs is which tone is on top and what it is doing, which `annotation._comp_line_clause`
  prints: `top D4 - walks up`.
- **The fill's target is the tune's fret, not a harmonised average.** §"The fill" states its
  high-return case against `Eb5` harmonised at avg 12.5 and lands `D5` at avg 12.0; that
  number came from a prototype that re-voiced the next step by hand. The engine aims at the
  **fret the returning note sits at** (`comp_line.tune_register`), so the same case climbs
  to `C5` at avg 10.3 instead — still a climb, still under the tune, one step further below
  it. The direction is the rule; the exact shape is the prototype's, and this is the
  deviation, stated rather than hidden.


Every figure in this document came from the library's own front door, so it re-measures by hand:

```python
# the plateau (finding 1) and the widening (finding 3)
import headxml
from arranger.options import Request
steps, head, _ = headxml.arrange_xml_head(
    "tests/data/synthetic_common_8.musicxml", section=(1, 9),
    request=Request(melody=False))
tops = [max(s.voicing.midi_notes()) for s in steps if s.voicing.active_frets()]
print(tops, [b - a for a, b in zip(tops, tops[1:])])

# the palette's reach (finding 2), by top tone
from arranger.grips import get_comping_voicings
print([(v.tab_string(), max(v.midi_notes())) for v in get_comping_voicings("Cmaj7", notes=3)])

# the opening's constant (finding 4)
from arranger.cost import SelectionCriteria, voicing_cost
crit = SelectionCriteria(previous=None, fret_min=2, fret_max=13)
print([(v.tab_string(), voicing_cost(v, crit).position) for v in get_comping_voicings("Dm7", notes=3)])

# the fill (finding 6)
steps, head, _ = headxml.arrange_xml_head(
    "tests/data/synthetic_repeat_slash.musicxml", section=(5, 8),
    request=Request(chord_fills="comp"))
print([(s.bar, s.beat, s.chord, s.voicing.tab_string(), s.melody, s.melody_voiced)
       for s in steps if s.bar == 6])

# §"The measurement": the plateau, the intervals, and the band
import glob
for path in sorted(glob.glob("tests/data/*.music*")):
    for request in (Request(melody=False), Request(melody=False, chord_on="every-beat")):
        steps, _head, _ = headxml.arrange_xml_head(path, request=request)
        sounding = [s for s in steps if s.voicing.active_frets()]
        tops = [max(s.voicing.midi_notes()) for s in sounding]
        moves = [b - a for a, b in zip(tops, tops[1:])]
        outside = [
            s for s in sounding
            if s.top_role and any(not (3 <= f <= 10) for f in s.voicing.active_frets())
        ]
        print(path.split("/")[-1], len(moves), sum(1 for m in moves if m == 0),
              len(moves) - sum(1 for m in moves if m == 0), len(outside))
```

The band comparisons and the fill's three directions came from a scratch script that re-voices each
slot with the rules in this document — a prototype, deliberately **not** kept in the tree: it exists
to answer the design question, and `tests/meta_step_loop_equivalence.py` is the standing check for
the equivalence it was used to establish.







