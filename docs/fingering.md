# Left-hand fingering: research notes

**Status: step 1 of §5 is built and inert — `arranger/fingers.py` and
`tests/test_fingers.py` exist, no engine module imports them, and no existing
output changed.** It records what is known about how the four fretting
fingers can be arranged on the fretboard, how confident each claim is, and what
each one would change in the current implementation. The plan agreed in session
is: build the assignment and its feasibility tests first, *then* measure whether
finger-level information deserves a place in `voicing_cost`, and only then touch
the tuple. This document is the "before" state for that work — when a claim
below is tested or refuted, the measurement lands here, beside the claim.

**§4.3's defect has since been measured, and it was real — and it needed the right hand,
not this module.** A merged step could sound five strings, one more than the right hand
has digits; the fix is a budget on the *palette* (`grips.thumb_safe_grips`, read by
`decisions.resolve_texture_grips`), so `arranger/fingers.py` is still inert and
`voicing_cost` is still untouched. The measurement and the fix are in §4.3 below, and in
[docs/open-issues.md](open-issues.md) item 11.

Nothing in the routing table sends you here to change behaviour. Read it before
writing `arranger/fingers.py`, before adding any criterion to `voicing_cost`
that mentions fingers, and before anyone claims a shape is "unplayable" for a
reason the span cap does not already catch.

**Next step: step 2 of §5, and it has been measured — partly.** Its *§4.3* half is done:
the five-finger check found a real defect, and it is fixed (see §4.3 and §5 step 2). Its
*movement* half is measured too — where finger-level movement disagrees with `position`
and `movement`, over every struck transition of the committed heads — but the re-ranking
experiment that would decide **step 3** has not run, and the numbers as they stand argue
against a tuple slot rather than for one. Until that experiment runs, `voicing_cost`
stays untouched and this document is the state of record.

## 1. Why: what whole-hand measures cannot see

`voicing_cost` (see [engine.md](engine.md)) ranks candidates with whole-hand
measures:

- **`fret_span()`** (criterion 3) — `max(frets) - min(frets)`. Under monotone
  fingering this *is* the index-to-pinky reach, so the static stretch question
  is already finger-shaped, and the span-0/1 bucket (a one-fret reach does not
  outrank keeping the hand in place) is the first decision that reasoned about
  fingers even though it measured frets.
- **`position`** (criterion 4) — `|avg_fret - previous.avg_fret|`, a
  centre-of-mass proxy for the hand.
- **`movement`** (criterion 5) — `calculate_pitch_leading_distance`, summed per
  voice between two shapes.

Three things these provably cannot distinguish:

1. **Barre reuse.** `x-x-6-7-6-x` holds fret 6 on the D and B strings with
   *one* finger. If the next shape moves that barre, a per-string measure counts
   two fret deltas and the hand moved one finger. The reverse case is worse: all
   four fingers shifting one fret each looks like a small per-string sum but is
   a full re-grip of the hand.
2. **Anchor fingers.** A change where two fingers stay planted and two leap is
   identical under `avg_fret` to one where all four shuffle slightly — they do
   not feel the same at all. The Bb7 case the span bucket fixed
   (`6-7-6 → 3-3-3 → 6-7-6`) was visible at hand level; the same shape of
   error with the leap spread across fingers is not.
3. **Finger choice within a span.** A span of four frets can be held index to
   pinky (relaxed) or index to middle with the other two fingers bunched behind
   (cramped). Same span, same average, different hand.

## 2. The constraints, by confidence

### 2.1 Hard physical constraints (safe to assert)

These follow from four fingers, each pressing at one fret position at a time:

1. **One string, one note, one finger.** Two fingers cannot fret the same
   string simultaneously.
2. **One finger, one fret.** A finger cannot hold two *different* frets at
   once, so a shape with k distinct fretted positions needs k distinct fingers.
   Every shape this engine generates has at most four notes, so the finger count
   never binds — assignment always exists in the counting sense. Open strings
   (fret 0) and mutes need no finger at all.
3. **Same fret ⇒ same finger (a barre).** Two notes at the same fret are held
   by one finger laid across the strings. This is structural, not stylistic:
   it is what makes barre detection part of assignment rather than an
   ornament on it. *Known simplification:* at high frets, where spacing is
   narrow, players sometimes place two fingertips side by side on one fret.
   Rare in chord-melody shapes; explicitly out of scope for v1.
4. **A barre blocks reach below it.** If the index barres at fret 6, no other
   finger can sound fret 4 — the fingers lie *above* the barre finger. So in a
   barre shape the barre sits at (or tied for) the lowest fret. This is the
   strongest genuine biomechanical argument for "lowest fret gets the lowest
   finger", and it applies specifically to barre shapes.
5. **`bass.py`'s "thumb" is the right-hand thumb, not a left-hand technique.**
   The walking-bass note is *plucked* by the right-hand thumb; the left hand
   frets it with an ordinary finger like any other note. Thumb-over fretting —
   wrapping the left thumb around the neck onto the low string — is not
   idiomatic in jazz arranging and is assumed nowhere in this engine. Two
   consequences: the left hand has no fifth finger to spend, so the bass note
   competes for the same four (§4.3); and `voicing_cost` still never sees that
   note, because it is merged after selection, so fingering computed at
   selection time covers the upper shape only.

   *The right hand is four digits as well* — thumb, index, middle and ring,
   `p-i-m-a` — and that turned out to be the consequence that mattered: a step
   may sound four strings and never five, which is the defect §4.3 found and
   `grips.thumb_safe_grips` now enforces.

### 2.2 Strong conventions (adopt for v1, but document as assumptions)

6. **Fingers ordered by fret: index lowest, pinky highest (monotone).**
   Near-universal in practice — players shift position rather than cross
   fingers — and automatic-fingering systems use it as a constraint because it
   is so reliable. It is not a law: advanced repertoire contains stretches where
   a higher-numbered finger frets *below* the index. For chord-melody grips,
   adopt monotonicity, and make the failure mode visible: if no monotone
   assignment exists for a generated shape, a feasibility test must name it
   rather than the algorithm crashing or silently crossing fingers.
7. **One finger per fret ("classical position"): index owns f, middle f+1,
   ring f+2, pinky f+3.** The classical default, but jazz voicings routinely
   bunch (two fingers on adjacent frets, one idle) or spread across four to
   five frets. This is a *scoring* heuristic, not a feasibility rule. The
   general form to score: chosen fingers should be spread across the span, not
   bunched at one end.
8. **Barres are the index's job.** Occasionally the middle or ring finger
   covers a partial barre (the ring-finger barre under an F-shape is the
   classic). Assume index first for v1; record the exception.

### 2.3 Numbers and physics (measurement wanted before asserting)

- **Maximum span.** The engine already claims `GRIP_MAX_SPAN = 5` (4 for a
  duo and an interval) — see [engine.md](engine.md) §"Span outranks neck
  position" for what promoting span over position cost. Independent reference
  implementations land near 4 for an intermediate player (the `mutheors` Rust
  crate's default `max_fret_span` is 4). Worth stating: fret spacing narrows up
  the neck, so a five-fret *span* is a physically smaller reach at fret 12 than
  at fret 3 — the engine counts frets, not millimetres, and that is a
  deliberate simplification nobody has measured.
- **Finger-pair asymmetry.** Fingers 3 and 4 share a tendon and extend least
  independently, so a shape opening a big ring-to-pinky gap is worse than the
  same gap between index and middle. Real, biomechanically well attested, and
  *unsuitable for v1*: it belongs in scoring, and there is no number here we
  would defend in a cost tuple.
- **Left-hand thumb position.** The model is classical throughout: thumb
  behind the neck, opposed to the index. Thumb-over is not idiomatic in jazz
  arranging and this engine never assumes it — the word "thumb" in `bass.py`
  and its tests names the *right-hand* plucking thumb (§2.1 item 5). So there
  is no left-hand thumb/finger interaction to model, and none of the
  thumb-over playability folklore carries over.

### 2.4 What the literature does and does not give us

The general framing — fingering as a constrained multi-attribute optimisation
over hand position, with biomechanical feasibility as a filter and stylistic
clichés on top — is standard (Bontempi et al., *From MIDI to rich tablatures*,
arXiv:2407.09052, is a recent readable example). Reference implementations
score with **weighted sums** — e.g. `mutheors` uses fret-span 0.15, string-span
0.10, finger-stretch 0.20, barre 0.25, position-change 0.30 — which is exactly
the design `voicing_cost`'s docstring rejects on principle: magic numbers
nobody can defend, and every criterion tradeable against every other. So the
literature is useful for *constraint lists* and useless for *rankings*; we keep
the lexicographic tuple and take only the feasibility rules from outside.

Two caveats on sourcing: several primary PDFs (Diaportal, vi.be) returned raw
binary rather than text during this session, so specific claims in §2.2–2.3
are from general knowledge and the readable sources only, and no citation here
should be treated as checked line-by-line. Ground truth that *is* available
locally: standard chord-diagram dictionaries carry author-written finger
numbers, and our own hand-authored drop-2 tables were written by a player —
both are testable against our assignment once it exists.

**The external search is exhausted, and one avenue is closed.** The common jazz
chord-chart sources do **not** carry left-hand fingerings: a representative
page (jazzguitar.be's beginner chord charts) numbers the *circles* with chord
tones — its own legend reads "the numbers in the black circles are the other
chord tones" — so the diagrams validate tone-sets and shapes, not fingerings.
That leaves two usable ground truths locally: our own hand-authored drop-2
tables (a player's written shape encodes a sensible fingering) and the
feasibility invariants in §3. The single hard external data point worth keeping
is corroborative rather than new: a jazz-guitar source treats thumb-over as
non-idiomatic ("strictly speaking this is bad technique"), which supports the
§2.1 item 5 decision.

## 3. The algorithm (built, and inert)

A small exact enumeration, not a heuristic search:

1. **Group active notes by fret.** Same fret ⇒ one finger (barre). Distinct
   frets ⇒ distinct fingers. Open strings and mutes get no finger. At
   selection time the walking-bass note does not exist yet — it is merged
   after selection (§2.1 item 5) — so candidates are assigned over the upper
   shape alone; a whole-step playability check on a merged step must add the
   bass note back as an ordinary fretted note (see §4.3).
2. **Assign monotonically** — lowest fret gets the lowest finger (convention
   6). The only real choice is *which k of fingers 1–4* serve k distinct
   frets: C(4,k) possibilities — 1, 4, 6 or 4. Trivially enumerable.
3. **Score each choice**: spread the chosen fingers across the span rather
   than bunching them (generalising convention 7); prefer the index for a
   barre (convention 8).
4. **Tie-break deterministically**, documented in the docstring. Tests pin
   tabs; the same voicing must always produce the same assignment.
5. **Between steps**, compute finger movement under the chosen mapping:
   `sum |fret_new(finger) - fret_old(finger)|` over the four fingers, plus the
   largest single-finger travel (which catches "one finger leaps while the
   others stay" — the anchor-leap case of section 1 item 2). A barre moving counts once, which
   is the whole point.

Feasibility is guaranteed in the counting sense (§2.1 constraint 2), so what
the feasibility tests check is the *conventions*: monotone assignment exists,
barre detected where the shape implies one, assignment deterministic, finger
count ≤ 4, and every shape across all grips and qualities passes.

**As built**, the three things this section left open are settled in code, and each is
pinned by a test rather than left in a docstring:

- **The score** is `Σ |offset − (finger − 1)|` over the distinct frets, `offset` being a
  fret measured up from the shape's lowest. One rule rather than the two item 3 names,
  because the misses *are* those two claims: adjacent fingers score zero on a bunched
  shape, a four-fret reach is pulled to the pinky, and the lowest fret takes the index
  unless a finger already lies below it — which is convention 8 arriving out of the score
  instead of being asserted after it.
- **The tie-break** is the lowest-numbered finger tuple, and it is not a comparison:
  `itertools.combinations` yields in lexicographic order, so the first choice to reach the
  best score *is* it. Reachable rather than theoretical — `{3, 5, 7}` ties between
  `(1,3,4)` and `(2,3,4)` and takes the first.
- **Feasibility** is `None` at five distinct frets, which is items 1 and 2's "one finger
  holds one fret" stated as a return value rather than a crash or a crossed fingering.
  **No generated shape can reach it** — every grip sounds at most four strings, measured
  over 8,789 shapes — so the refusal exists for the merged step of §4.3 and nothing else.
- **Movement's known under-report** belongs here rather than in §5, because it is a
  property of the design this section specifies and not an implementation slip: a finger
  handed a fret another finger held contributes two zeroes, so a substitution can total 0
  while the hand visibly moves. Measured on `x-x-3-4-5-x → x-x-3-4-8-x`, which is `(0, 0)`.
  §5 step 2 weighs it against real steps; it is pinned by a test so it cannot drift unseen.

## 4. Impact on the current implementation

### 4.1 Where the module lives

`arranger/fingers.py`, placed **after `tuning`** in the DAG — it only needs
`Voicing`. `tests/test_package_dag.py`'s `ORDER` gained the entry in the same
commit; the Makefile names the package as a directory, so lint and typecheck
picked it up with no change.

**One prediction here was wrong, and the check that refuted it is why stage 1
needed a facade import.** "Nothing existing imports it" is not available to an
inert engine module: `test_package_dag.test_every_module_is_imported_by_something`
asserts that *something* imports every module in `ORDER`, and it counts `__init__`
as an importer — deliberately, because reaching the facade is what a facade is
for. So the facade binds `arranger.fingers`, `"fingers"` is in `arranger.__all__`
(the star-import surface is checked against the module's own namespace, so a bound
public name missing from that list fails), and the honest form of stage 1's
inertness is the narrower one: **no engine module imports it**. That is what
`tests/test_fingers.py::TestTheModuleIsInert` asserts from the AST, and it is the
assertion a step-3 change inverts rather than deletes (AGENTS.md trap 5).

### 4.2 The cost tuple

Adding or changing a criterion is **a musical decision, not a refactor** —
`AGENTS.md` and the `voicing_cost` docstring both say so, and the span bucket
just demonstrated the protocol: implement, measure what moves, re-pin only what
the measurement exonerates, record the trade and any rejected alternatives in
[engine.md](engine.md), update the test count. A finger-level criterion would
land in the span/position region of the tuple — the region the `0/1/2` bucket
measurement showed is the most sensitive in the whole function. Measure first,
decide placement second. Candidates worth measuring, in likely order:

- **per-finger movement** as a refinement of criterion 5 (`movement`), fixing
  the barre double-count of §1.1;
- **max single-finger travel** as a new tie-break near position, catching the
  anchor-leap case of section 1 item 2;
- *not* a finger-spread term at static selection time — span already ranks
  first among the comfort criteria, and a second static comfort term would
  fight it for no measured gain.

### 4.3 The interaction to check early: the bass note, and the digits on both hands

The walking-bass note is fretted by the left hand like any other note
(§2.1 item 5), and it sits *below* the held shape on the low E, A or D
string. That makes it a fifth fretted note competing for the same four
fingers — the constraint no current test sees:

- if the upper shape already occupies **four distinct frets**, the bass note
  can only be played at a fret the shape already uses (sharing a finger's
  barre across a lower string, which constraint 4 allows only when that fret
  is the shape's lowest) or the step is not simultaneously playable;
- a bass note **below the shape's barre fret** is unreachable for the same
  reason a finger below a barre is: the barre finger lies across, and the
  remaining fingers are above it;
- `tests/test_walking_bass.py::test_the_thumb_stays_within_reach_of_the_fingers`
  measures *distance* between thumb note and held shape — it does not check
  that a spare or shareable finger exists, so it will not catch this.

**Measured, and the answer is not the one this section expected: it is the right hand, and
the corpus it asks for no longer exists.** The Weimar database was removed in commit
`2b5f10a`, so "run the corpus" now means what is in the tree — the seven committed heads in
`tests/data/`, plus the 8,789-shape generated corpus `tests/test_fingers.py` already builds.

The proximity rule does avoid a five-fret **left** hand almost everywhere. What it cannot
see is the **right** hand: the plucks are thumb, index, middle and ring (`p-i-m-a`), so a
step may sound four strings and never five — and a four-note target with a bass note merged
under it is five, whatever the frets. Counting what each step actually plucks
(`tabgp._sounding_frets`, which already models the `repeated` and `bass_only` cases):

| arrangement | steps | pluck five strings | five distinct frets | …counting the held shape |
|---|---|---|---|---|
| `--texture targets --bass walk` | 839 | **151** | 10 | 15 |
| `--texture targets --bass anchors` | 688 | **130** | 9 | 10 |
| `--texture walking_bass --bass walk` | 839 | 0 | 0 | 0 |
| `--texture uniform --bass walk` | 643 | 0 | 0 | 0 — the axis is refused (`bass_allowed`) |
| `_place_bass` over the generated corpus, all 12 bass pitch classes | 86,315 placements | — | — | 8 |

The two budgets overlap rather than nest, and both are real. `7-9-x-8-12-10`, a `Bmaj`
target in "Tenor Madness", needs five distinct frets and fails both hands;
`8-9-x-8-12-10` shares fret 8 between two strings — a barre she can hold and the right hand
still cannot pluck; and the six `bass_only` steps that need five frets *hold* the shape
instead of striking it, so only the thumb plucks and it is the left hand that fails.

**Fixed, in the engine, and not with this module.** `grips.thumb_safe_grips` derives from
`GRIP_STRING_SETS` that a four-string grip cannot be offered as a *target* on a slot that
carries a bass note, and falls back to the widest statement that leaves a finger free —
`("drop2", "drop3")` becomes `("shell",)`. `decisions.resolve_texture_grips` applies it per
slot (`steps.py` passes `slot.bass is not None`), so a target on a beat the thumb leaves
bare keeps all four strings. Measured after: **0** five-string steps anywhere; `--texture
targets --bass walk` is byte-identical to `--texture walking_bass --bass walk`; the other
rows do not move. `arranger/fingers.py` was not needed for any of it, and that is the result
this document records: the first real playability defect in this area was a *string* budget,
not a finger assignment. Full measurement, the cost, and the rejected alternatives are in
[docs/open-issues.md](open-issues.md) item 11.

The left-hand half of the question is still open at the margin, and is now stated where it
can be tested: `tests/test_walking_bass.py::TestTheInvariant` sweeps the *string* budget over
every committed head, and no test sweeps the fret budget.

### 4.4 Explicitly out of scope for now

- rendering fingerings in tab, GP5 or MusicXML (`tabgp.py` has a fingering
  field; MusicXML has `<technical>` — possible later, separable);
- crossed (non-monotone) fingerings — excluded by choice, named in a test;
- finger-pair asymmetry and position-dependent reach — scoring refinements,
  deferred until there is a measurement that needs them;
- the walking-bass note as a fifth finger — it is a right-hand *plucking*
  label, not a left-hand technique (§2.1 item 5); it stays merged after
  selection and out of the cost, though §4.3's playability check must add it
  back when that check is built.

## 5. The sequence we agreed

**Status: step 1 is done and inert; step 2's §4.3 half is measured and fixed; step 2's
movement half is measured; step 3 has not been started.** Research is done, and the
remaining unknowns are empirical (see the note at the top and §4.3), which is why step 1
had to exist before either measurement could run.

1. **Built.** `arranger/fingers.py` + `tests/test_fingers.py`: assignment,
   barre detection, movement, feasibility over the whole generated corpus.
   The gate stayed green apart from the new tests — 890 test identities before,
   918 after, and the 890 diff empty — so **no existing test moved.** The one
   correction to this plan is §4.1: the facade binds the module, so "inert" means
   *no engine module imports it* rather than *nothing imports it*.
2. **Measured** with throwaway scripts under `/tmp` (not committed — see `AGENTS.md`
   trap 8), on what is left of the corpus now that `wjazzd.py` is gone: the seven
   committed heads and the 8,789-shape generated corpus.
   - **The §4.3 check found a defect, and it is fixed** — 281 steps plucked five strings,
     of which 19 also needed five distinct frets (see §4.3 and
     [open-issues.md](open-issues.md) item 11). Note what the fix was *not*: no finger
     assignment was needed, and `voicing_cost` was not touched.
   - **The movement comparison came back nearly empty, and the two numbers that did not
     argue against a tuple slot.** Over 1,330 struck transitions (six heads × `uniform`
     and `walking_bass`):
     - `assign_fingers` is undefined on **0** of them: a candidate at selection time always
       sounds at most four strings, so a per-finger criterion would be safe by construction;
     - **4** transitions are the anchor leap of §1.2 — `largest >= 3` while
       `calculate_pitch_leading_distance` reports 2 or less. `12-x-11-13-x-11` →
       `x-7-x-6-9-9` is pitch 2 against one finger travelling 5 frets;
       `x-6-x-3-x-x` → `11-x-9-11-11-x` is pitch 1 against 6;
     - **13** transitions read pitch movement 0 while the shape changed, because that
       metric compares sorted pitch lists and so truncates at the shorter one — a step that
       adds or drops a voice is scored on the overlap alone;
     - **345 (25.9%)** read `finger_movement.total == 0` while the fingering changed,
       because a finger idle in *either* shape is skipped by design. So a per-finger `total`
       cannot simply replace `movement` at index 5: it says "nothing moved" on a quarter of
       the transitions, and the transitions where it says anything are the 4 above.
3. **Not started, and step 2's numbers are the argument for leaving it alone.** 0.3% of
   transitions separate the two metrics, the separating case is a single-finger leap that
   `span` (criterion 3) and `movement` (criterion 5) between them already bound, and the one
   candidate that would touch every step — `finger_movement.total` in `movement`'s place —
   reports "nothing moved" on a quarter of them. If it is taken up anyway, the protocol is
   the span bucket's: implement, measure which pinned tabs move, re-pin only what the
   measurement exonerates, record the rejected alternatives in [engine.md](engine.md),
   update the counts here and in `AGENTS.md`, and **invert** `TestTheModuleIsInert` rather
   than delete it (`AGENTS.md` trap 5).

The movement half of step 2 came back nearly empty, which is the outcome this document was
written to allow for: hand-level measures already agree with finger-level ones on 99.7% of
the transitions we generate, so what it records is *that*, rather than inventing a criterion
to justify the module. The §4.3 half did not come back empty, and it is worth noting which
hand found it — the left-hand question this document was written about was answered *not
playable* on 25 steps, while the right hand's four digits were being exceeded on 281.


