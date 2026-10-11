# Generated grips: one rule for the tones, a search for the placement

**Status: step 1 of 3 landed.** The tone-priority rule is in `arranger/grips.py` and is
what the engine now reads; the hand-written drop-2 tables are kept as the witness that
holds it, asserted by `tests/test_generated_grips.py`. Steps 2 (one placement search
replacing the per-family template arithmetic) and 3 (retiring the tables) are below and
are **not** built.

This document exists because the reasoning behind the change did not fit in a docstring
and would otherwise live only in a conversation. `docs/one-fact.md` records why that is a
failure mode rather than a style point: a plan off disk is not a plan the next session
can read.

Measured at plan time, on the default arrangement (`uniform`, `every_note`, auto voices)
of all eight committed heads: **1,103 steps**.

## 1. What was measured

The claim the rule had to earn was *not* "a rule can be written" — it was that the 119
hand-written templates are that rule's output rather than a set of decisions a rule
cannot express. Two measurements settle it.

**The templates.** Generating every template from a per-quality tone order (`melody first,
then the next three tones by priority`, laid out as a textbook drop-2) reproduces the hand
table **exactly, 119 of 119**, for all 29 qualities in `DEGREE_OFFSETS_FROM_ROOT`. The
same rule at arity 3 reproduces `SHELL_DEGREES` — the pair a shell states — for all 29,
**in order**, which is what the duo reads. That was checked by brute force over every
permutation of each quality's tones, not by assuming an order:

- every quality admits at least one order consistent with all of its own templates;
- 18 of the 29 have four or fewer tones, so their order is only pinned by the shell pair
  and is otherwise free — a useful thing to know before "tidying" one;
- the 11 with more tones than voices are the ones whose order is a real decision, and
  each admits between 6 and 36 consistent orders. So the tables are *consistent with* a
  rule and do not determine one: the rows in `TONE_PRIORITY` are a choice among them,
  held to the tables by the equivalence test.

**The arrangement.** With the rule live and the engine reading it, **0 of 1,103 steps
move** over all eight committed heads, compared line by line against the same sweep on a
clean worktree of the commit before the change (`git worktree add /tmp/pre HEAD`, per
AGENTS.md trap 8). `make demo` is byte-identical apart from the command `make` echoes.
That is the assertion that matters: not that two tables agree, but that the music does.

## 2. The rule

`TONE_PRIORITY` is one row per quality: that chord's own tones, most defining first. A
shape of `voices` voices states the melody's tone and the next `voices - 1` of the row, so
a four-note drop-2, a three-note shell and a two-note duo are one rule at three arities.
`stated_tones()` is the accessor; `_priority_drop2_templates()` turns a row into the
templates; `DROP2_TEMPLATES` is the live table.

Read off the tables it reproduces:

- **The first two entries are `SHELL_DEGREES`**, at every quality. A shell and a drop-2
  state the same pair, so this is one fact that was previously stated twice.
- **The root goes first when something must, and the natural 5th next.** 24 templates
  drop the root and keep the natural 5th; 18 drop the 5th and keep the root, and every one
  of those 18 is either a melody that *is* the root or a chord whose 5th is altered.
- **An altered 5th is not a 5th.** 39 of the 45 altered-5th occurrences are stated. A b5,
  #5, #11 or b13 ranks near the top of its row; the natural 5th ranks near the bottom.
- **A name-given extension is not optional, and one the name does not give is.** A `13`
  states its 13th and its b7 and drops its 9th: `(4, 9, 10, 7, 0, 2)`.

**The order is per quality, and that is the point.** `9` gives up its root and keeps its
5th; `7#11` keeps its root and gives up its natural 5th; `13` keeps its 5th and gives up
its root *and* its 9th. No single global order reproduces the tables, which is why the
decision is a table of rows rather than one sentence.

## 3. The order that was not taken

The proposal was the reverse preference: **drop the natural 5th first, then the root**,
with an altered 5th counting as a guide tone. The second half of that is exactly what the
tables already do (39 of 45 altered 5ths are stated). The first half is not, and it was
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
than it is.

Attribution caveat: the 36/29 split is by the step's `non_chord_tone` flag, which marks a
melody that stayed a non-chord tone. A step whose melody was *reharmonised* into an
extension (`harmonized_as` set) reaches the palette route with the flag clear, so the true
split needs a per-step record of the routed quality — which step 2 should add rather than
guess.

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

## 4. What is not built

**Step 2 — one placement search.** Today a template becomes frets by arithmetic
(`_place_template`), while the four non-contiguous string sets already *search*
(`_place_shell`, `_place_drop2_6432`, both exhaustive through `_frets_in_span`). Unifying
them — hold the melody, enumerate inner frets inside `GRIP_MAX_SPAN`, keep the shapes whose
sounding set is the priority set — subsumes `drop2`, `drop3`, `drop24`, `closed`,
`drop2_6432` and `shell`, and makes the family name a *derived* view of the found shape
rather than the thing that selected it (`docs/one-fact.md` is the precedent). Four
decisions have to be made before it is written, and each needs a measurement:

- **The tie-break.** `voicing_cost` names no family, so an exact tie falls to generation
  order. With one search there is no family order to fall back on, so the tie-break has to
  be stated. The last time a criterion that did this work was deleted it moved 0 of 799
  steps — a count like that is what says whether the choice matters.
- **The palette route.** Should a non-chord melody be offered the whole template list, or
  should it state `stated_tones` — its own note plus the top three by priority — and be
  offered *one* shape? The rule already has an answer available; today's code does the
  other thing. This is the route 29 of the 65 moves above came through, so it is where the
  behaviour is least understood.
- **`_BOTTOM_FOUR`.** A four-note shape on 6-5-4-3 is excluded today for a musical reason
  ("four voices in the bottom fourth of the compass"), not a mechanical one. A general
  search makes it *reachable*, so the exclusion becomes a decision to re-assert rather
  than a set nobody generates.
- **A name for a shape that is not one of the four transformations.** Some legal frettings
  of a legal tone set are neither close position nor a drop of any voice.

**Step 3 — retire the tables.** `DROP2_INTERVAL_SETS` and the numbers in
`DEGREE_OFFSETS_FROM_ROOT` go once the rule is the source of the templates;
`grip_chart.py` reads the generated table instead; and `AGENTS.md`'s "Adding a new chord
quality" collapses from seven steps to a tone set plus one priority row — a quality with no
row would then get a canonical derived one and be voiceable everywhere on the day it is
added.

**The explanation the tab owes.** "Every choice about a voiced note is explained by the
line that prints it" is an invariant of the artifact rather than a style preference. A rule
that *omits* a chord tone is exactly such a choice — a reader cannot see it in the fret
numbers — so it needs a derived clause and a witness in `tests/test_explanations.py`, which
fails until the clause is registered. This is owed by step 2, not step 3: it becomes
visible the moment the omission is a rule instead of a number someone typed.

## 5. Where the rule lives, and what holds it

| what | where |
|---|---|
| the rows | `arranger/grips.py` — `TONE_PRIORITY` |
| the accessor | `arranger/grips.py` — `stated_tones()` |
| the generator and the live table | `arranger/grips.py` — `_priority_drop2_templates()`, `DROP2_TEMPLATES` |
| the witness | `DROP2_INTERVAL_SETS`, unchanged, asserted by `tests/test_generated_grips.py` |
| the decision behind the rows | this document, §3 |
