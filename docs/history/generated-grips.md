# Generated grips: one rule for the tones, a search for the placement

**Retired into `docs/history/` — the record of a completed plan.** All three steps landed: the
tone rule is the *source* rather than a generator checked against one, one placement rule and one
place a fret becomes a shape, and the clause the tab owed for a tone a shape leaves out. The live
statement of the rule is [docs/engine.md](../engine.md) §"Adding a new chord quality", and the
placement, the memo and the three levers measured-and-not-taken are in
[docs/engine.md](../engine.md) §"Grips, and the position-aware selector". What is still here is
the *measurement*: what each step cost, and the order it turned out not to need.

**Status: all three steps landed.** The tone-priority rule is in `arranger/grips.py`, and it
is now the *source* rather than a generator checked against one: `_drop2_template_for` builds
the shape for a degree on demand and `_drop2_palette` is that rule read at every chord tone,
so the hand-written tables left the engine in step 3 and live on in `tests/support.py` as the
witness the rule is asserted against. Step 2 — one placement rule, and one place a fret
becomes a shape — is landed as well, measured at **0 of 1,103 steps**, and so is the
clause the tab owed for a tone a shape leaves out. §4 describes
both; §3 records what step 3 measured — the order it turned out not to need, and, in §3a, the
altered-5th rank it since adopted. The
label the placement would derive, and the levers that price it, are **not** built.

This document exists because the reasoning behind the change did not fit in a docstring
and would otherwise live only in a conversation. `docs/history/one-fact.md` records why that is a
failure mode rather than a style point: a plan off disk is not a plan the next session
can read.

Measured at plan time, on the default arrangement (`uniform`, `every_note`, auto voices) of all
eight committed heads: **1,103 steps**, which is every step of that sweep that sounds anything.
Three counts come out of that one sweep, and every table below says which it uses, so a count
of steps and a count of *melodies* cannot be confused:

| count | the predicate | why it is the one asked for |
|---|---|---|
| **1,103** | the step sounds | every step of the sweep, and the denominator the fingerprints are taken over |
| **1,016** | it carries a melody | the other 87 are comping slots the grid places where the tune is silent |
| **967** | the melody sounds with at least one other voice | what the plan-time tables call *melody-bearing*: the comparisons there are about shapes, and a melody alone has no shape to compare |

## 1. What was measured

The claim the rule had to earn was *not* "a rule can be written" — it was that the 119
hand-written templates are that rule's output rather than a set of decisions a rule
cannot express. Two measurements settle it.

**The templates.** Generating every template from a per-quality tone order (`melody first,
then the next three tones by priority`, laid out as a textbook drop-2) reproduces the hand
table **exactly, 119 of 119**, for all 29 qualities — compared by degree, since step 3, so
the claim is that the *pairing* is the rule's rather than a position in a list. The
same rule at arity 3 reproduces `SHELL_DEGREES` — the pair a shell states — for all 29,
**in order**, which is what the duo reads. That was checked by brute force over every
permutation of each quality's tones, not by assuming an order:

- every quality admits at least one order consistent with all of its own templates;
- 18 of the 29 have four or fewer tones, so their order is only pinned by the shell pair
  and is otherwise free — a useful thing to know before "tidying" one;
- the 11 with more tones than voices are the ones whose order is a real decision, and
  each admits between 6 and 36 consistent orders. So the tables are *consistent with* a
  rule and do not determine one: the rows in `TONE_PRIORITY` are a choice among them,
  held to the tables by the equivalence test — and that is also why step 3 could not
  derive an *order* from the tables, and did not need one: a degree is the question now,
  so no list is read in any order.

**The arrangement.** With the rule live and the engine reading it, **0 of 1,103 steps
move** over all eight committed heads, compared line by line against the same sweep on a
clean worktree of the commit before the change (`git worktree add /tmp/pre HEAD`, per
AGENTS.md trap 8). `make demo` is byte-identical apart from the command `make` echoes.
That is the assertion that matters: not that two tables agree, but that the music does.

## 2. The rule

`TONE_PRIORITY` is one row per quality: that chord's own tones, most defining first. A
shape of `voices` voices states the melody's tone and the next `voices - 1` of the row, so
a four-note drop-2, a three-note shell and a two-note duo are one rule at three arities.
`stated_tones()` is the accessor; `_drop2_template_for()` turns one degree into a shape and
`_drop2_palette()` is that rule read at every degree.

Read off the tables it reproduces:

- **The first two entries are `SHELL_DEGREES`**, at every quality. A shell and a drop-2
  state the same pair, so this is one fact that was previously stated twice.
- **The tail ranks which tone goes, and it is per-quality.** The nearer the end of a row a
  tone sits, the sooner a four-voice shape gives it up. 24 templates drop the root and keep
  the natural 5th; 18 drop the natural 5th and keep the root — 6 because the melody *is* the
  root and 12 on `7#11`, `7b13` and `maj7#11`. So a row ending `..., root, 5th` gives up the
  natural 5th first (`maj7`, `m7`, `7`, `6`) and one ending `..., 5th, root` gives up the root
  first (`9`, `maj9`, `7b9`).
- **An altered 5th is not a 5th, and it outranks the root.** A b5, #5, #11 or b13 ranks above
  the root, and so above the natural 5th, which sits at or near the bottom of its row — so a
  reduced-arity shape gives the root up before its altered 5th. Of the 41 witnessed templates
  whose quality has an altered 5th, 39 state one; the two that do not are `7alt` and `m9b5`
  under a root melody, where the melody holds the root and another tone takes the voice.
- **A name-given extension is not optional, and one the name does not give is.** A `13`
  states its 13th and its b7 and drops its 9th: `(4, 9, 10, 7, 0, 2)`.

**The order is per quality, and that is the point.** `9` gives up its root and keeps its
5th; `7#11` keeps its root and gives up its natural 5th; `13` keeps its 5th and gives up
its root *and* its 9th. No single global order reproduces the tables, which is why the
decision is a table of rows rather than one sentence.

## 3. The order that was not taken

The proposal was the reverse preference: **drop the natural 5th first, then the root**, with
an altered 5th counting as a guide tone. Its **second half has since been adopted on its own**
— the rows now put an altered 5th above the root, which is the rank §2 always claimed for it
and the rows did not have — and it is measured in §3a. Its **first half was not**, and it was
measured rather than argued.

Moving the root and the natural 5th to the end of each row — the 5th last, the root
second-to-last — then regenerating and re-sweeping:

- **18 of the 119 templates change**, in the six qualities the rows constrain: `7b9` (3),
  `maj9` (3), `m9` (3), `9` (3), `6/9` (3), `13` (3). The root-on-top inversion of each is
  unchanged, because there the root sounds as the melody and the two orders already agree.
- **65 of the 1,103 steps move**, by head: `heres_that_rainy_day` 28 of 180,
  `The_Jitterbug_Waltz` 16 of 241, `tenor_madness` 8 of 200, `All_the_Things_You_Are` 4 of
  97, `but_not_for_me` 4 of 80, `Trouble_in_Mind_Blues` 3 of 65, `i_was_doing_all_right` 2
  of 224, `lead_sheet_chords_only` 0 of 16.

**They arrive by two routes, and the second was a surprise.** 36 of the 65 are steps whose
melody is a chord tone, so the degree index picks the one changed template. The other 29
are steps whose melody is **not** a chord tone of the written chord: no inversion matches,
so the engine offers *the whole template list* as a palette of positions, and changing the
list changes the palette. `Eb6/9` alone accounts for 12 of them, and `Fm9` for 4. That is
a second consumer of `DROP2_INTERVAL_SETS`, invisible from the table's name and from its
docstring, and it is the finding that would otherwise have made this change look smaller
than it is. **Step 3 made it a named function** (`_drop2_palette`) rather than a fall-through
to a table, which is the shape it should always have had.

**Attribution caveat, and it is still open.** The 36/29 split is by the step's
`non_chord_tone` flag, which marks a melody that stayed a non-chord tone. A step whose
melody was *reharmonised* into an extension (`harmonized_as` set) reaches the palette route
with the flag clear, so the true split needs a per-step record of the routed quality.

**Sized since, by instrumenting the route rather than re-deriving it.** The census is in §4.
Counting the steps whose melody is not a chord tone of the chart the part **states**
(`harmonized_as or chord` — the name the generator is actually called with) gives **268 of the
1,103 steps** of the default sweep, 24%, against the **476 of 967** recorded at plan time that
no definition tried since reproduces. Reading the same census against the **written** chord
gives 350, and 82 of that difference is steps whose melody was reharmonised into an extension
that contains it — exactly the case this caveat is about. The second branch, a chord tone with
no inversion of its own, is **0**: every quality's degree row covers as many of its tones as
its template list has entries, `13` being the one exception (5 inversions, 6 tones) and no
committed step putting a melody on the tone it omits.

Some of the moves are large and audible:

```
heres_that_rainy_day  step 65  Dm7      x-5-x-5-6-x    ->  10-x-10-10-x-x
heres_that_rainy_day  step 66  G7#5     x-x-3-4-4-x    ->  x-8-9-8-x-x
heres_that_rainy_day  step 64  Gmaj9    x-x-7-7-7-7    ->  10-x-12-11-12-x
The_Jitterbug_Waltz   step 30  Ab9      x-x-8-8-7-8    ->  11-x-13-11-13-x
```

**The tables' order was kept as the default**, for three reasons and no more: it is the
idiomatic rootless reading rather than a worse one; it costs 0 steps today, so the rule's
landing is provable; and the row order makes this a one-line decision per quality, so if
`9` wants the rooted reading it can be flipped and measured on its own. This section is
the numbers it would cost to flip all six at once. It is a live option, not a dead end.

### 3a. The second half, adopted alone

"An altered 5th counting as a guide tone" is a *rank* claim, and seven rows did not have it:
`m7b5`, `dim7`, `7b5`, `7#5`, `7#11`, `7b13` and `maj7#11` all put the **root** above the
altered 5th, so the root was the tone a reduced shape gave up first — the opposite of §2's own
bullet. Moving the altered 5th above the root in those seven rows, measured from a clean
worktree (AGENTS.md trap 8):

- **0 of the 119 templates move.** The four-tone qualities state all four tones at four voices,
  and `_close_stack_offsets` walks the *set* of stated tones, so a row's internal order cannot
  reach a four-voice shape (`m7b5`, `dim7`, `7b5`, `7#5`: none of their templates each).
- **3 of the 125 palette entries move** — the natural-5th melodies of `7#11`, `7b13` and
  `maj7#11`, three of the six degrees the palette added over the witness (§4).
- **0 of the 1,103 steps move**, and `make check` is green — not one pinned tab in the suite
  shifts. So the cost is nothing like the 65 steps the *first* half would cost.

What the rank buys is a **reduced arity**, which is where the parts model reads it
(`docs/history/parts.md` §4 and §9): a chord part at three voices gives up its 5th, at two it is the
guide pair, and on `Bbm7b5` the root goes before the `b5`.

## 4. What step 2 landed, and what is still owed

**Landed — one placement rule, and one place a fret becomes a shape.** A candidate is now
*proposed* one of two ways and *validated* one way. `_candidate` (`arranger/grips.py`) is the
only place a set of frets becomes a voicing: the melody sounds and is the highest note, every
fret is on the board and inside `GRIP_MAX_SPAN`, the family's tone claim (`required`) and bass
claim (`lowest_pc_allowed`) hold, nothing outside the chord sounds when the family makes that
claim at all, and the sounding strings are one `supported_string_sets()` entry — a set is a
musical decision, so a shape cannot invent one. The proposers are the search (`_search_shape`,
which enumerates with `_frets_in_span`, reached through the memo `_place_shape`) and the
**layouts** (`_place_template`, which computes the frets from an interval template — the
template and the string set fix each one).

Across the eight committed heads this moved **0 of 1,103 steps**, byte for byte, and the
head sweep's wall time is unchanged. Two things it
*states* rather than inherits from one producer:

- **The melody is the highest sounding note.** Pinning it to the top *string* does not put it
  on top in *pitch* — the B and G strings are four semitones apart — and nine (quality, root,
  set, fret) configurations reach a shape whose inner voice sounds above the melody. Am9 with
  a B3 melody on the B string is the pinned case, its `(4,3,2)` shape reaching C4 a semitone
  above. The shell path had never asked, and no committed head reaches one, which is why the
  sweep is unchanged.
- **A computed fret of -1 is a refusal, not a mute.** -1 is how a producer mutes a string it
  does not use, and a note one semitone below a string's open pitch computes to the very
  same number: C7 under E4 reaches it on the B string, a tritone below the melody. Read as a
  mute, that shape thins to three of a four-string set and sounds G, A and the high E — a set
  no table offers. `voices` on the request is what tells the two apart.

**The two ways are the two kinds of family, and which is which is a table.**
`_LAYOUT_GRIPS` and `_SEARCHED_GRIPS` name them, `tests/test_grips.py` holds the two to
partitioning the families, and the generator is one loop over (family, string set) that asks
the appropriate one: a family listed in neither would generate nothing at all, which is what
makes adding one a decision rather than a silent omission. The loop collapsed from a ladder of
per-family branches, and with it went a duplicated tone-set computation and a membership list
that mixed the two kinds (`duo` and `interval` sat in the guide-tone branch and were placed as
layouts).

**The search is answered from a memo, and the memo changes nothing but the time.** It is one
function asked the same question thousands of times: the placement search is **47.4s of the six
heaviest test modules' 127.8s**, and **77,152 of its calls are 1,969 distinct requests**. One
32-bar head at default settings asks 1,058 times for 298 distinct shapes. The repeats are
intrinsic rather than a test artifact — a repeated melody degree, a repeated bar, and the
target, fill and retry paths each asking again for what was already answered. `_search_shape` is
the enumeration; `_searched_shape` (an `lru_cache`) remembers one request's answer;
`_place_shape` — the name the generators call — rebuilds a fresh `Voicing` from the snapshot
stored. With the memo the whole suite runs **171.1s → 112.3s**, and a fingerprint of every
arrangement over the 8 committed heads and 16 settings is byte-identical across the change:
**8,173 steps, 0 lines moved.**

Three things make it safe rather than merely fast, and `tests/test_placement.py` holds each to
a witness:

- **The key is the whole request.** `_Placement` is a frozen dataclass of strings, tuples, ints
  and frozensets and `allowed` is a frozenset or None, so equal requests share an entry and
  different ones cannot — which is why nothing needs invalidating. The tables the search reads
  besides the request (`GRIP_MAX_SPAN`, `STANDARD_TUNING`, `supported_string_sets()`) are fixed
  when the module is imported: **reassigning one at runtime is the single thing that would leave
  a stale answer behind.**
- **A caller cannot write through it.** The fret vector is stored as a tuple and a fresh
  `Voicing` is built per call, because `movement._attach_bass` merges the walking bass *into the
  chosen shape* (`voicing.frets[string_index] = fret` and `voicing.bass_pc`). A memo handing out
  the stored object would let one step's thumb line rewrite the shape the next step is handed —
  silently, and only in the tab.
- **It is read.** A memo nothing hits would leave every other check in that file passing while
  the engine paid for a cache it never used, so a hit and a miss are counted.

What it does **not** do is make the search cheaper. It is still exhaustive over the span window,
so `_frets_in_span`'s cost is the floor for any request nobody has asked before.

**The comping palette is the same memo, for the same reason.** `_search_comping_voicings`
enumerates the guide-tone shapes; `_comping_palette` (an `lru_cache`) remembers one request's
answer as the same snapshot; `get_comping_voicings` — the published name, and the one
`movement._comping_step` and `steps.VoiceLeadingEngine` call — rebuilds fresh `Voicing`s for it,
because `decisions.select_step_voicing` hands one of the palette's own objects back and
`_attach_bass` writes the walked thumb into it. The repetition is *worse* there than in the
placement search: the comping route asks one request per slot per bar with no melody pinned at
the top, so on a full-corpus sweep the enumeration is the majority of the time. Its numbers are
in [docs/comping-styles.md](../comping-styles.md) §9.7, and `tests/test_comping.py` holds it to the
same three witnesses `tests/test_placement.py` holds this one to.

**Owed, and not built.** What follows is a decision the placement has *made possible* rather
than one it has taken: the label the one search would derive, and the three levers that price
a derived label (**the derived label needs one more step, and the numbers say which** below).
The one thing step 2 owed the tab — a chord tone the rule dropped, named on the line — is
**paid**, and is the last paragraph here.

**Making the layout families search is behaviour-preserving, and not needed.** Every template
is monotone — its voices descend down the strings — and on a fixed string set a monotone
fretting of a given pitch list is *forced*, up to a duplicated pitch. Measured over the
committed heads: **2 alternative frettings of a winner's own note set are monotone, and
neither would win**. So a layout could be found by the search rather than computed; what it
would not be is *named*, because the family name is the layout. That is the next decision, and
it is where the derived-label question below starts.

**A derived label needs one more step, and the numbers say which.** `closed` and `drop2`
state the *same* four pitch classes on a four-tone chord and differ only in whether the
second voice sits an octave down, so a search told only ``these pitch classes must sound''
cannot name what it produced. What it *can* do is find shapes no family names, and there are
three levers for that, each measured separately:

| lever | what it would change | measured |
|---|---|---|
| **Admit crossings** (a string carrying a pitch above the string above it) | 1,441 alternative frettings exist on 794 of 967 melody-bearing steps; **47 would win** — 8 on the *foreign-note* criterion (a better choice of which tone to double, all `drop2_6432`), 35 on span and 4 on neck position | a real change, and it needs a name for a shape that is not one of the four transformations |
| **Offer 6-5-4-3** (a G-string melody with four voices) | **104 of 967 steps** would gain 2–4 shapes, and criterion 2 (`missing = 4 - len(active)`) ranks them above the three-note shell that wins there today | the `_BOTTOM_FOUR` exclusion is load-bearing for ~11% of steps, not a set nobody happens to generate |
| **One shape per set from the rule** (a non-chord melody stating `stated_tones` rather than being offered the palette) | **268 of 1,103 steps** have a melody that is not a chord tone of the chart the part states, and **99.2%** of their candidate passes take the whole-list route (3,690 of 3,719); one is offered a median of **11 candidates out of 28 templates** (max 22 out of 36, over ~20 (grip, string set) calls), where the rule would offer one shape per set | the largest lever, and the least understood: 29 of the 65 moves in §3 came through it. The 476 of 967 recorded at plan time is not reproducible — §3 states the definition that is, and the reason the route exists at all: a non-chord melody has no inversion *by definition*, so this is not a gap in a table but the shape of the question |

**Step 3 — landed, and the order it was meant to decide dissolved.** The tables had exactly
one open question: `DROP2_INTERVAL_SETS` paired *positionally* with `DEGREE_OFFSETS_FROM_ROOT`,
that pairing is an order, and `grip_chart.py` draws its rows in it. Measured before deciding
it: **no order tried reproduces the 29 rows** — the rule's own order 0 of 29, ascending from
the root 13, seventh-family-first 15, and the best of them, "the ascending order rotated" 22,
is an accident of how the table was written rather than a rule. And *reordering* changes
nothing: with the rows permuted into the rule's order the 1,103-step fingerprint is
byte-identical, because the table is an index→degree map and the pairing survives a
permutation.

So the decision was not made, it was **dissolved**. `_drop2_template_for(quality, degree)`
builds the shape for one degree on demand — the body of the loop that generated the table —
and `_templates_for` asks it with the melody's own degree, so there is no list and no index
left to order. What a melody with no degree to match is offered became `_drop2_palette`: the
same rule read at every chord tone.

| | |
|---|---|
| gone: `DROP2_INTERVAL_SETS`, `DEGREE_OFFSETS_FROM_ROOT`, `DROP2_TEMPLATES`, `_priority_drop2_templates` | the 119 numbers are `tests/support.py::WITNESS`, keyed by the degree their top voice states |
| gone: `_drop2_for_untabled_degree`, `_guide_tone_drop2`, `_duplicates_pitch`, `_REACH`, `_BLOCK_SPACING` | the rule answers for **every** chord tone of all 29 qualities (125 degrees): none empty, none impure, none missing a guide tone. The runtime fallback they formed never fired, so the invariant is a gate in `tests/test_generated_grips.py` instead of a branch |
| gone from the facade | `VoiceLeadingEngine.DROP2_INTERVAL_SETS` and `.DEGREE_OFFSETS_FROM_ROOT` — the API change this step is |
| `grip_chart` | reads `_drop2_template_for` and the quality's own tones; its rows read low-degree-first and depend on no engine-side order at all |

Measured on this tree: **0 of 1,103 steps** move and `make demo` is byte-identical. The
palette gains six shapes — the 9th of a `13`, the #9 and #11 of a `7alt`, and the natural 5th
of `7#11`, `7b13` and `maj7#11` — and **no committed step reaches any of them**: 350 steps
take the palette route and none is on one of those five qualities. So the growth is real and
unexercised, and is recorded here rather than left to be discovered.

**A bug went with the deleted branch, and it is worth naming.** It tested `(t - root_pc)` on
tones `_chord_context` already returns *relative to the root*, so for a root other than C it
matched melodies that were not chord tones at all and spent the derived shape on them; the
replacement tests the degree, which is the same arithmetic written once.

**What it still costs is one decision and no derivation.** Measured over the 29 degree rows:
every row's *content* is the **prefix** of that quality's `TONE_PRIORITY` row, cut to the
length of its template list — 29 of 29, so the row says nothing the rule does not, except the
order it says it in. Not one row is in the rule's order, and that order is what `grip_chart.py`
draws `common_grips.md` in. So retiring the table means **choosing an order**, or keeping the
row as an order-witness with its content asserted against the rule — which is the shape
`WITNESS` already has, and is what
`tests/test_generated_grips.py::test_a_witness_degree_list_is_a_prefix_of_the_rule` now holds.
The five rows shorter than their priority row are the qualities with more tones than a template
list covers (`13`, `7#11`, `7b13`, `maj7#11`, and `7alt` two tones over), and what they cut is
the rule's own tail — the same tone a four-voice shape gives up.

**The explanation the tab owed, and it is paid.** "Every choice about a voiced note is
explained by the line that prints it" is an invariant of the artifact rather than a style
preference, and a rule that *omits* a chord tone is exactly such a choice: a reader cannot see
it in the fret numbers. It became due when the omission stopped being a number someone typed
and became a rule (`TONE_PRIORITY`'s tail), and it was discharged where it was owed — in
`render._omission_clause`, a derived clause in `_annotate`, not in the placement.

Read from the step's own fields: the tones of the chord the part **states**
(`harmonized_as` where a substitute was found, so it composes with the substitution clause)
against the pitches of the **whole** step (`midi_notes()`, so a thumb that lands on the root
counts as stating it), named through `chords.melody_degree_name` — the vocabulary
`_comping_clause` names the voices a shape *states* with.

Measured on the default sweep: **185** of the 1,016 steps that carry a melody and a sounding
shape are a four-voice shape leaving a chord tone out — 162 leaving one, 23 leaving two, so 208
tones in all — and the tone left out is the **root in 117 of them**, then the 5th (32), the 9th
(20), the 3rd (14), the b5 (13), the 7th (4), the 13th (3), the b7 (3) and the b9 (2); by
quality `6` and `9` lead at 40 each. Before it, not one line in the corpus named an omitted
tone: the census of every annotation the eight heads print found
`(harmony under 7 - 4 voices)` and stopped there.

**Two fingerprints, because this move changes text by design.** The head-step fingerprint
(chord, melody, tab, grip) is **unchanged over all 2,145 steps** of the
`tests/test_explanations.py` sweep — the music did not move — and of the 2,145 rendered lines
exactly **98** changed, every one with its four columns byte-identical and only the annotation
longer. 98 is also the number `tests/test_explanations.py` pins for the steps owing the
clause, so the count that proves the work was done is the count that notices if it stops being
done. `make demo` is the same check on the path a reader runs: **3** of its annotated lines
gain the clause and every tab in it is byte-identical.

Only the **four-voice** shape is asked about, because that is the shape the rule is about:
fewer voices was already answered by the count or by `partial`'s `shell - 3rd & 7th`, and a
hold was answered where the shape was chosen.

## 5. Where the rule lives, and what holds it

| what | where |
|---|---|
| the rows | `arranger/grips.py` — `TONE_PRIORITY` |
| the accessor | `arranger/grips.py` — `stated_tones()` |
| the rule, one degree at a time | `arranger/grips.py` — `_drop2_template_for()` |
| the palette a melody with no degree to match is offered | `arranger/grips.py` — `_drop2_palette()` |
| the witness | `tests/support.py` — `WITNESS`, the 119 hand-written templates keyed by the degree their top voice states, asserted by `tests/test_generated_grips.py` |
| the placement rule, and the one place frets become a voicing | `arranger/grips.py` — `_Placement`, `_candidate`, proposed by `_place_shape` and `_place_template`; held by `tests/test_placement.py` |
| the decision behind the rows | this document, §3 |
