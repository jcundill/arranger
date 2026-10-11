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

**Step 2 — one placement rule, and one place a fret becomes a shape.** A candidate is now
*proposed* one of two ways and *validated* one way. `_candidate` (`arranger/grips.py`) is the
only place a set of frets becomes a voicing: the melody sounds and is the highest note, every
fret is on the board and inside `GRIP_MAX_SPAN`, the family's tone claim (`required`) and bass
claim (`lowest_pc_allowed`) hold, nothing outside the chord sounds when the family makes that
claim at all, and the sounding strings are one `supported_string_sets()` entry — a set is a
musical decision, so a shape cannot invent one. The proposers are the search (`_place_shape`,
which enumerates with `_frets_in_span`) and the **layouts** (`_place_template`, which computes
the frets from an interval template — the template and the string set fix each one).

Across the eight committed heads this moved **0 of 1,103 steps** and **0** of the 300
diagnostics, byte for byte, and the head sweep's wall time is unchanged. Two things it
*states* rather than inherits from one producer:

- **The melody is the highest sounding note.** Pinning it to the top *string* does not put it
  on top in *pitch* — the B and G strings are four semitones apart — and nine (quality, root,
  set, fret) configurations reach a shape whose inner voice sounds above the melody. Am9 with
  a B3 melody on the B string is the pinned case, its `(4,3,2)` shape reaching C4 a semitone
  above. `_place_shell` had never asked, and no committed head reaches one, which is why the
  sweep is unchanged.
- **A computed fret of -1 is a refusal, not a mute.** -1 is how a producer mutes a string it
  does not use, and a note one semitone below a string's open pitch computes to the very
  same number: C7 under E4 reaches it on the B string, a tritone below the melody. Read as a
  mute, that shape thins to three of a four-string set and sounds G, A and the high E — a set
  no table offers. `voices` on the request is what tells the two apart.

**What remains is the *proposal*, not the rules.** Every template is monotone — its voices
descend down the strings — and on a fixed string set a monotone fretting of a given pitch list
is *forced*, up to a duplicated pitch. Measured over the committed heads: **2 alternative
frettings of a winner's own note set are monotone, and neither would win**. So making the
layout families *search* for tones rather than compute a layout is behaviour-preserving by
construction, and the family name stays what it is today — the layout that was asked for.

**A derived label needs one more step, and the numbers say which.** `closed` and `drop2`
state the *same* four pitch classes on a four-tone chord and differ only in whether the
second voice sits an octave down, so a search told only ``these pitch classes must sound''
cannot name what it produced. What it *can* do is find shapes no family names, and there are
three levers for that, each measured separately:

| lever | what it would change | measured |
|---|---|---|
| **Admit crossings** (a string carrying a pitch above the string above it) | 1,441 alternative frettings exist on 794 of 967 melody-bearing steps; **47 would win** — 8 on the *foreign-note* criterion (a better choice of which tone to double, all `drop2_6432`), 35 on span and 4 on neck position | a real change, and it needs a name for a shape that is not one of the four transformations |
| **Offer 6-5-4-3** (a G-string melody with four voices) | **104 of 967 steps** would gain 2–4 shapes, and criterion 2 (`missing = 4 - len(active)`) ranks them above the three-note shell that wins there today | the `_BOTTOM_FOUR` exclusion is load-bearing for ~11% of steps, not a set nobody happens to generate |
| **One shape per set from the rule** (a non-chord melody stating `stated_tones` rather than being offered the whole template list) | **476 of 967 steps** are on the routes that bypass the degree index — 297 non-chord-tone, 179 chord-tone with no named inversion | the largest lever, and the least understood: 29 of the 65 moves in §3 came through it |

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
fails until the clause is registered. **Owed, and not built.** It became due when the
omission stopped being a number someone typed and became a rule (`TONE_PRIORITY`'s tail);
registering it is a change to `render` and that table, not to the placement.

## 5. Where the rule lives, and what holds it

| what | where |
|---|---|
| the rows | `arranger/grips.py` — `TONE_PRIORITY` |
| the accessor | `arranger/grips.py` — `stated_tones()` |
| the generator and the live table | `arranger/grips.py` — `_priority_drop2_templates()`, `DROP2_TEMPLATES` |
| the witness | `DROP2_INTERVAL_SETS`, unchanged, asserted by `tests/test_generated_grips.py` |
| the placement rule, and the one place frets become a voicing | `arranger/grips.py` — `_Placement`, `_candidate`, proposed by `_place_shape` and `_place_template`; held by `tests/test_placement.py` |
| the decision behind the rows | this document, §3 |
