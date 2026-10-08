# Fingering: research notes

**Status: step 1 of §5 is built; step 2's §4.3 measurement has landed on both hands, and it
gave `arranger/fingers.py` its first engine caller.** §4.3's *string* budget needed the right
hand (`grips.thumb_safe_grips`) and no code from this module; its *fret* budget needed the
module itself (`fingers.can_fret`, read by `bass._place_bass`), so the module is **not inert**
and `voicing_cost` is still untouched. One step in the committed heads changed. This document
records what is known about how the four fretting fingers can be arranged on the fretboard,
how confident each claim is, and what each one would change in the current implementation. The
plan agreed in session is: build the assignment and its feasibility tests first, *then* measure
whether finger-level information deserves a place in `voicing_cost`, and only then touch the
tuple. This document is the "before" state for that work — when a claim below is tested or
refuted, the measurement lands here, beside the claim.

**Both hands are here, and the title says so.** The document began as the left
hand's — which finger frets which string — but two of its measurements have been
about the *right* hand: §4.3 (four digits, so at most four strings may sound at once)
and §4.4 (the same four digits, and the string *gaps* the fingers reach across). The
left hand owns §1–§3 and the module; the right hand owns no module, because in both
cases the answer turned out to be either a rule in `grips.py` or nothing at all.

**§4.3 has since been measured, and it was real — on both hands, and only the second one needed
this module.** A merged step could sound five strings, one more than the right hand has digits;
that fix is a budget on the *palette* (`grips.thumb_safe_grips`, read by
`decisions.resolve_texture_grips`) and needs nothing from `fingers`. A `bass_only` step could
also need five *frets* from four fingers, and that one is `fingers.can_fret`, read by
`bass._place_bass` — the module's only engine caller. `voicing_cost` is untouched by both. The
measurements and the fixes are in §4.3 below, and in [docs/open-issues.md](open-issues.md)
items 11 and 12.

Nothing in the routing table sends you here to change behaviour. Read it before
writing `arranger/fingers.py`, before adding any criterion to `voicing_cost`
that mentions fingers, and before anyone claims a shape is "unplayable" for a
reason the span cap does not already catch.

**Next step: step 3 of §5, and nothing measured so far argues for it.** Step 2's *§4.3*
half found a real defect and fixed it (the five-finger check; see §4.3 and §5 step 2). Its
*movement* half is measured — where finger-level movement disagrees with `position` and
`movement`, over every struck transition of the committed heads — and it came back nearly
empty. Its **right-hand half is measured too** (§4.4: which strings `p-i-m-a` pluck,
whether a skip between the fingers costs anything the engine could avoid, and how far the
thumb reaches — the low four strings, which it sweeps for the bottom of a two- or three-note
shape whether or not a bass voice is marked), and it comes back the same way: the skip is real
and common, but every lever that would remove it trades away something a *higher* criterion is
paying for, and narrowing the exemption to the thumb's actual reach moves the count by **0**.
The re-ranking experiment that would
decide **step 3** has still not run, and the numbers as they stand argue against a tuple
slot rather than for one. Until it runs, `voicing_cost` stays untouched and this document is
the state of record.

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

### 2.5 The right hand: `p-i-m-a`, and which gaps between plucks matter

§2.1 item 5 gives the right hand four digits — thumb, index, middle, ring, `p-i-m-a` —
and used them for one budget: a step may sound at most four strings. There is a second
question the same four digits raise, and this section is it: **which strings they land
on, and whether an unplucked string between two of them costs anything.**

Take the strings a step actually plucks, sorted low to high, and hand them out in that
order — **provided the lowest of them lies on the low four strings**: the thumb takes the
lowest, the next the **index**, then **middle**, then **ring** — `p-i-m-a` ascending, which
is what a four-note shape on four neighbouring strings already is. A shape whose bottom note
sits on the B or the high E has **no thumb in it at all**; its lowest is the index and the
three fingers fan above from there. The strings a step plucks are `tabgp._sounding_frets`'
answer rather than the fret vector's, because a `repeated` or `bass_only` step is not
re-striking its whole shape.

**The thumb's reach is a *string* fact, not a voice one, and that is the second half of this
convention.** On a three- or even two-note shape the thumb sweeps whatever is lowest on the
low four strings — the E, A, D and G — *including when that note is the **alto** or the
**tenor** rather than a stated bass*. A shape does not have to be marked as carrying a bass
voice for the thumb to be the digit on its bottom string, because the right hand assigns
strings and knows nothing about the voices above them: `bass=` is an arrangement-level fact
(handed to `bass.py`, which is a *left*-hand question), and the merged bass note is written
into the fret vector only *after* selection, so no right-hand reading ever sees it. Measured
in §4.4: **54** steps of the default `uniform` arrangement are a two- or three-note shape
whose bottom note is the thumb's with **no** bass line under them at all.

Now the claim, and it is the one that makes this measurable:

- **A gap in the *lowest two* sounding strings — between the thumb and the index — is
  free**, *while the thumb is the digit on the bottom string*. The thumb strokes across the
  muted string to reach its note, so a skip under it is ordinary equipment rather than a
  reach, and this is exactly the gap the bass-skipping string sets create on purpose
  (§2.1's "6-4-3 skips the A"; `drop2`'s `(1,3,4,5)` and `(0,2,3,4)`; `drop2_6432`'s whole
  reason to exist). Measured in §4.4: **not one** shape in `drop2`, `drop3`, `drop2_6432`
  or `duo` carries a gap anywhere else, so on this rule all four families are already clean.
- **A gap between the three *fingers* — index↔middle, or middle↔ring — is the one that
  costs.** Those three play in a fan above the planted thumb, and one of them reaching
  over an unplucked string is a different hand from three on three neighbouring strings.

So the metric is a single number — **the skipped strings in gaps crossed by the middle or
ring finger** — and the thumb→index gap is the only exemption it needs. On the ascending
strings `s1 < … < sk`, the gap before `s2` is the thumb's and is free **so long as `s1` is one
of the low four**; the gaps before `s3` and `s4` are the fingers' and count. Restricting the
exemption that way costs nothing, and §4.4 measures *why* rather than asserting it: a string
set with nothing below the G can only be the B, the high E, or both — adjacent strings — so
the exempt gap never arises on a shape the thumb cannot reach.

**The trap, and it is the reason this section exists rather than a sentence.** The
obvious metric — "are the plucked strings contiguous?" — **over-reports by an order of
magnitude**. Counting *any* gap made 275 of the 307 gap-carrying `--bass walk` steps look
like defects the post-selection bass merge had *created*; counting only the fingers' gaps
makes the true figure **2**. A bass note merged under a shape lands directly beneath it,
so the gap it opens is precisely the exempt one — the same "assert the rule on the whole"
warning as [open-issues.md](open-issues.md) item 11, arriving from the other side. A
metric that models the *fretboard* is not a metric that models the *hand*.

**Confidence: a convention, adopted on the same footing as §2.2.** It is not measured
here and could not be — it is a claim about how a hand feels, and the corpus can only say
how often the shape occurs. What the corpus *can* do is size the consequence, which is
§4.4, and confirm that the exempt gap is the one the string tables deliberately create.
The **reach** half is a convention on the same footing, and it is the half the tables can
answer outright: which digit a player puts on a lone note on the B string is a hand fact,
but *how often a shape's bottom note sits above the G* is a fact about the string sets —
**3 of the 24** reachable ones, **359 of 8,789** generated shapes, and between **12%** and
**68%** of the steps of the five committed-head rows (§4.4).

## 3. The algorithm (built, and read by `bass` for one question)

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
  That step became a caller: `fingers.can_fret` is the same claim asked *before* the
  assignment, `bass._place_bass` is what asks it, and §4.3 records the one step it found.
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
inertness was the narrower one: **no engine module imports it**, asserted from the
AST by `tests/test_fingers.py::TestTheModuleIsInert`.

**That narrower claim has since been falsified, and the test was inverted rather
than deleted** (`AGENTS.md` trap 5). §4.3's left-hand half is a real engine caller, so
the class is now `TestTheEngineUsesItForOneQuestion` and what it asserts is the *set*
of callers — exactly `{bass}`. Naming the set instead of counting it is the point:
the next caller has to be considered rather than merely noticed.

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

**The left-hand half closed too, one release later, and the answer was the one this section
rejected as a fix for the other half.** Measured on the tree the string fix left behind — the
seven committed heads × five `texture`/`bass` rows, 3,697 steps — exactly **one** step
violated the fret budget: "Tenor Madness" bar 40 under `--texture targets --bass anchors`,
where the hand holds `x-9-x-8-12-10` and the walk's `B` has a single candidate, the low E at
fret 7. The A string is spoken for by the held shape, and a `B` on the D at fret 9 would
sound above the shape's F#3, which `_place_bass` forbids. Five frets from four fingers, and
there is no placement to prefer: a *filter* is the only thing that can answer it. Dropping
the note is defensible here precisely because it is not defensible as a general rule — a bass
note no player can finger is not a bass note, and the step keeps its upper voicing exactly as
it does when no string is free, with the omission reported. `fingers.can_fret` is the check
and `bass._place_bass` is its only caller, so `arranger/fingers.py` is no longer inert.
After: **0**. [docs/open-issues.md](open-issues.md) item 12 has the measurement, the two
counting decisions below, and the alternatives.

**One of those counting decisions moves the number by a factor of ten**, and both are about
which hand the check is stated over:

- counting `sounding_frets` — the vector `_place_bass` already maintains — **over-counts**.
  Under a `bass_only` step nothing above the thumb strikes, so a melody carried on a string
  the held shape does not use is a note the hand is not holding; it is already sounding
  elsewhere. That is item 4's mistake made backwards, and it reads **10** where the answer is
  **1**.
- dropping the previous thumb note from the hand, the way `bass._held_shape`'s `structure`
  does for harmonic reasons, **makes no difference on the committed heads** — measured, both
  readings give the same answer. `can_fret` is called on the held vector itself plus the
  candidate rather than on `structure`, which is chosen on the physics: that string is still
  ringing, so it is still fretted. The alternative is right for harmony and wrong for fingers,
  and it is recorded here as agreeing rather than as differing.

`tests/test_walking_bass.py::TestTheInvariant` now sweeps the fret budget over every committed
head beside the string budget, and the two are stated over different parts of the step on
purpose: one counts *plucks*, the other counts the *hand*. Keeping them apart is what makes
either one able to fail.

### 4.4 The right-hand finger skip: measured, and left alone

§2.5's convention, sized on what the corpus and the committed heads can say. Throwaway
scripts under `/tmp` (not committed — `AGENTS.md` trap 8), reading each step's plucks from
`tabgp._sounding_frets` and counting only the gaps crossed by the middle or ring finger.

**It is a two-family problem.** Finger skips by grip over the 8,789-shape corpus:

| grip | shapes | clean | one finger skip |
|---|---|---|---|
| `drop2` | 3812 | **3812 (100%)** | 0 |
| `drop3` | 1098 | **1098 (100%)** | 0 |
| `drop2_6432` | 150 | **150 (100%)** | 0 |
| `duo` | 1310 | **1310 (100%)** | 0 |
| `shell` | 865 | 721 (83%) | 144 (17%) |
| `drop24` | 1554 | 444 (29%) | **1110 (71%)** |

Every gap in the first four families is the thumb's, so they are already clean — those are
precisely the sets §2.1's bass-skipping rule *created*. **Exactly five string sets** carry a
finger skip, four of them `drop24`'s:

```
drop24 (5, 4, 2, 1)  strings 1-2-4-5  skips the G  crossed by the middle
drop24 (5, 3, 2, 0)  strings 1-3-4-6  skips the B  crossed by the ring
drop24 (4, 3, 1, 0)  strings 2-3-5-6  skips the D  crossed by the middle
drop24 (4, 2, 1, 0)  strings 2-4-5-6  skips the G  crossed by the ring
shell  (5, 3, 2)     strings 1-3-4    skips the B  crossed by the middle
```

The sets `drop24`'s own comment calls its measured winners — strings 1-2-4-5 and 2-3-5-6,
the first and third above — are both here, which is the whole tension in one line: the
drop-2 & 4 shapes that fit the neck best are the ones whose fingers straddle an unplucked
string.

**In the committed heads** (six melody-bearing scores, the chords-only lead sheet has no
steps), steps carrying a finger skip:

| row | steps | finger skip | …created by the merged bass |
|---|---|---|---|
| `uniform` (the default) | 643 | **223 (34.7%)** | 0 |
| `targets --bass walk` | 837 | 19 (2.3%) | 2 |
| `targets --bass anchors` | 688 | 16 (2.3%) | 1 |
| `walking_bass --bass walk` | 837 | 19 (2.3%) | 2 |
| `walking_bass --bass anchors` | 688 | 19 (2.8%) | 2 |

The bass textures are nearly clean because their target palettes are shells; the default
`uniform` arrangement carries the full palette and shows the `drop24` cost plainly. And the
merge is not the source — see §2.5's trap note for why the naive count said otherwise.

**The exemption's own reach, measured: the thumb sweeps the low four strings, and narrowing it
costs nothing.** §2.5's convention has a second half — the thumb is the digit on the bottom
note only while that note sits on the E, A, D or G string — so this is what narrowing the
exemption to that reach would do. It comes back empty, and the reason is structural rather
than lucky:

- **The tables: 3 sets of 24, and all three are contiguous.** `duo`'s 1-2 pair (the B and the
  high E) and the two one-note comping shapes, on the B and on the high E, are the only
  reachable sets whose bottom string is above the G. A set with nothing below the G can only
  contain the B, the high E, or both — **adjacent strings** — so the thumb→index gap the
  exemption exists for *cannot occur* on a shape the thumb cannot reach.
  `tests/test_texture.py::TestTheThumbReach` pins that from `supported_string_sets()`, so a
  set that breaks it fails there rather than in a paragraph nobody re-reads.
- **The generated corpus: 359 of 8,789 shapes (4.1%)**, every one a `duo` (27.4% of the 1,310
  duos), every one a two-string shape, and **0** of them carrying a gap at all.
- **The committed heads**, counting every step `arrange_xml_head` returns — the denominator
  `open-issues.md` item 11 uses. §4.4's table above reads 837 on the two `walk` rows because it
  counts only the steps that pluck at least one string, and two of those 839 steps pluck nothing:

| row | steps | …bottom note above the G | …carrying a gap at all | skips, exemption as documented | …narrowed to the thumb's reach |
|---|---|---|---|---|---|
| `uniform` (the default) | 643 | 80 (12.4%) | 0 | **223** | **223** |
| `targets --bass walk` | 839 | 288 (34.3%) | 0 | 19 | **19** |
| `targets --bass anchors` | 688 | 446 (64.8%) | 0 | 16 | **16** |
| `walking_bass --bass walk` | 839 | 288 (34.3%) | 0 | 19 | **19** |
| `walking_bass --bass anchors` | 688 | 466 (67.7%) | 0 | 19 | **19** |

The last two columns are identical on every row, which is the narrowing being free rather than
being argued to be. The sub-count column is 0 because every off-reach step is a
**single** note — a lone voice on the high E (212 of the 288 on `targets --bass walk`, 365 of
the 446 under `anchors`) or on the B (76 and 81), with `uniform` the one row that also reaches a
pair, once, on 1-2 — and one pluck has no gap in it.

Those lone notes are also where **§2.5's "a string, not a voice" half** shows up. They are the
comping shapes an alto or a tenor gets, or a fill that is the melody alone, and most have no
bass line under them at all: of the two- and three-note shapes whose bottom note is the thumb's,
**54 of 54** carry no bass note in the default `uniform` arrangement, against **228 of 241** on
the two `walk` rows and **49 of 60** (`targets`) and **49 of 68** (`walking_bass`) under
`anchors`. The thumb plays the bottom of a two- or three-note shape whether or not a bass voice
is marked — which is the fact the convention is stated from, and the one no reader of `bass=`
would guess.

**Recorded, not built, and there is nothing here to build.** No engine module assigns a
right-hand digit: the only right-hand code is the four-string *budget* (`RIGHT_HAND_STRINGS`,
`grip_pluck_count`, `grips.thumb_safe_grips`), which counts how many digits are spoken for
rather than choosing which. So this convention has no engine consequence to weigh, and the
metric's conclusion stands unchanged. What it does change is the *model*: a third of the `walk`
rows' steps and nearly two thirds of the `anchors` rows' steps carry **no thumb in the right
hand at all**, which is worth knowing before anyone reasons from "the thumb is on the bottom
note".

**Three levers, and none of them is free.** Over 812 (quality, melody) selections, **265**
pick a finger-skip winner, every one of them with a zero-skip candidate in the pool:

- **A `voicing_cost` criterion is inert where it could sit.** Inserted *below* `position`
  (after position, after movement, or after the bass term) it changes **0** picks; inserted
  just *after* `span` it changes **17**. And the zero-skip alternative loses first at
  **span 197**, missing 35, position 17, outside 15, foreign 1 — so the skip is
  overwhelmingly what the *span* criterion buys. Preferring adjacency over span would undo
  the deliberate promotion of span above neck position (see [engine.md](engine.md) §"Span
  outranks neck position").
- **Reordering the string-set tables is inert.** **0** of the 812 picks are decided by an
  exact full-tuple tie, so generation order — which the table order sets — cannot change a
  single selection. The apparent lever is not one.
- **Removing the five sets is precise, and still a hard filter.** It replaces **exactly
  those 265** winners and empties **0** pools, so no melody loses its only voicing — but it
  changes 265 of 812 selections (32.6%) and gives up the span and coverage those two
  `drop24` sets were kept for. That is a musical decision, not a tidy-up.

**Recorded, not built.** No engine module changed, `voicing_cost` is untouched, no test
moved — the same outcome as the movement half of §5 step 2, reached the same way. If it is
ever taken up, the cheapest honest form is the third lever with its cost measured first,
and the span trade decided on the record rather than by a tie-break nobody can see.

**Caveats.** The selection probe is `previous=None` (no voice-leading history), one root
(`C`), and the *upper* shapes only — the bass is merged after selection, so a selection-time
term cannot see it (which is why the heads table above is what covers the whole step). It
also does not model the textures' role palettes, the repeated-melody hold, or melody-only
slots. So it sizes the candidate ranking, and the arrangement-level incidence is the heads
table's number — not the probe's.

### 4.5 Explicitly out of scope for now

- rendering fingerings in tab, GP5 or MusicXML (`tabgp.py` has a fingering
  field; MusicXML has `<technical>` — possible later, separable) — and this
  covers the right hand's `p-i-m-a` too, which is the same channel;
- crossed (non-monotone) fingerings — excluded by choice, named in a test;
- finger-pair asymmetry and position-dependent reach — scoring refinements,
  deferred until there is a measurement that needs them;
- the walking-bass note as a fifth finger — it is a right-hand *plucking*
  label, not a left-hand technique (§2.1 item 5); it stays merged after
  selection and out of the cost, though §4.3's playability check must add it
  back when that check is built.
- a right-hand term in `voicing_cost`, and the removal of the five finger-skip
  string sets — both measured in §4.4 and both left alone there, so neither is
  an open question until the span trade is decided on the record.

## 5. The sequence we agreed

**Status: step 1 is done; step 2 is measured on all four of its halves — §4.3 fixed on both
hands, movement nearly empty, right-hand skip recorded; step 3 has not been started.**
Research is done, and the remaining unknowns are empirical (see the note at the top, §4.3
and §4.4), which is why step 1 had to exist before any of the measurements could run.

1. **Built.** `arranger/fingers.py` + `tests/test_fingers.py`: assignment,
   barre detection, movement, feasibility over the whole generated corpus.
   The gate stayed green apart from the new tests — 890 test identities before,
   918 after, and the 890 diff empty — so **no existing test moved.** The one
   correction to this plan is §4.1: the facade binds the module, so "inert" meant
   *no engine module imports it* rather than *nothing imports it* — and §4.3's
   left-hand half later made even that false, so the module is not inert at all now.
2. **Measured** with throwaway scripts under `/tmp` (not committed — see `AGENTS.md`
   trap 8), on what is left of the corpus now that `wjazzd.py` is gone: the seven
   committed heads and the 8,789-shape generated corpus.
   - **The §4.3 check found a defect, and it is fixed** — 281 steps plucked five strings,
     of which 19 also needed five distinct frets (see §4.3 and
     [open-issues.md](open-issues.md) item 11). Note what the fix was *not*: no finger
     assignment was needed, and `voicing_cost` was not touched.
   - **The same check's other hand was done later and it did need the assignment** — one
     `bass_only` step held a four-fret shape and the walk's thumb had nowhere to land but a
     fifth fret. `fingers.can_fret` refused it (item 12), which is the module's only engine
     caller and the reason it is not inert. Measured before and after: **1** step, then
     **0**, and no pinned tab in the suite moved.
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
   - **The right-hand half is measured too, and it comes back the same way** (§4.4). The
     plucks are `p-i-m-a`, so only a skip between the three *fingers* costs anything — the
     thumb→index gap is the one the bass-skipping sets create on purpose (§2.5). Measured:
     `drop2`, `drop3`, `drop2_6432` and `duo` are **100% clean**; the skip is confined to
     four `drop24` sets plus one shell, and to **223 of 643** steps of the default `uniform`
     arrangement (2–3% under the bass textures). It is the price the *span* criterion pays —
     the zero-skip alternative loses first at span on 197 of the 265 — so a `voicing_cost`
     term is inert below `position` (0 of 812 picks) and changes 17 above it, table reordering
     is inert (0 exact ties), and removing the five sets replaces exactly those 265 winners
     with 0 pools emptied. Recorded, not built.
     **The same question with the exemption narrowed to the thumb's real reach** — kept only
     where the bottom note is on the E, A, D or the G string — is measured beside it and moves
     **0** on every row, for a structural reason: the only reachable sets with their bottom note
     above the G are `duo`'s 1-2 pair and the two one-note comping shapes, all three contiguous,
     so the exempt gap never arises where the thumb cannot reach. It is a convention that is
     common in the arrangements (a third of the `walk` rows' steps, nearly two thirds of
     `anchors`') and free in the tables, which is why it is recorded rather than built.
3. **Not started, and step 2's numbers are the argument for leaving it alone.** 0.3% of
   transitions separate the two metrics, the separating case is a single-finger leap that
   `span` (criterion 3) and `movement` (criterion 5) between them already bound, and the one
   candidate that would touch every step — `finger_movement.total` in `movement`'s place —
   reports "nothing moved" on a quarter of them. If it is taken up anyway, the protocol is
   the span bucket's: implement, measure which pinned tabs move, re-pin only what the
   measurement exonerates, record the rejected alternatives in [engine.md](engine.md), and
   update the counts here and in `AGENTS.md`. The **inversion** that protocol named has
   already happened, for §4.3 rather than for a tuple slot: `TestTheModuleIsInert` is now
   `TestTheEngineUsesItForOneQuestion` (`AGENTS.md` trap 5), so a step-3 change inherits a
   test that already expects callers rather than one built on the absence of them.

The movement half of step 2 came back nearly empty, which is the outcome this document was
written to allow for: hand-level measures already agree with finger-level ones on 99.7% of
the transitions we generate, so what it records is *that*, rather than inventing a criterion
to justify the module. The §4.3 half did not come back empty, and it is worth noting which
hand found it — on the tree that measurement ran on, the left-hand question this document was
written about was answered *not playable* on 25 steps, while the right hand's four digits were
being exceeded on 281. The right-hand half that followed (§4.4) is the third shape of answer,
and the one it is easiest to get wrong: the defect is real and common, every lever that
removes it is either inert or trades away a higher criterion, and what gets recorded is the
**trade** rather than a fix — which is what "measure before you decide" is for.

**The left hand's own answer arrived last, and it is the one that needed the module.** The
string budget's fix took the fret count down with it — 19 steps needing five frets became 1 —
and that one could not be answered by preferring a different placement, because there was only
one candidate. So the question this document was written for was finally answered by the thing
it was written for, in the only way left: refuse the note. It is a small result beside the 281,
and it is the one that turns `fingers.py` from a research note with a test into a module with a
caller — which is also what makes §5 step 3 a decision about *where* a criterion goes rather
than about whether the module should exist at all.


