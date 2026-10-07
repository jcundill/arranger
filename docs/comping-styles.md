# Comping styles: a design proposal

**Status: partly built.** Stage C of [§8](#8-staged-approach) has landed the *harmony*
axis (`harmony=full|guide|shell_root|root`), so `shell_root` exists and the degree-family
table in §4.1 is no longer a proposal in its entirety. Stage D has landed the **first half
of the rhythm grid** — `grid=every_note|freddie|charleston|joe_pass|final_and` — so §4.2's
table is built as a closed set of named rows, with the free-form spelling (§6 Q6) still to
come. **`hold=` is withdrawn** — see Stage D — and a measured defect stood between the grid
and the styles it was built for: [open-issues.md](open-issues.md) item 10, where a quarter
of the beat positions a grid names produced no chord at all, because a grid could only
*filter* melody slots and harmony was stored per melody note. **Its stage 3 landed**: on the
comping route the grid now *generates* positions rather than filtering them, so the union is
live and `charleston` and `joe_pass` are no longer silent on a 2/2 head — the silence was
never the metre, as §4.2 below originally supposed. §6 still holds open questions, and
`--voices`
is still `--voices`. This
records a design and the measurements that forced it, so the decision can be reviewed
rather than re-derived. It follows
[reharmonisation-proposals.md](reharmonisation-proposals.md), which is the precedent: a
proposal that says what was measured, what is proposed and what is deliberately
not built.

**§9 is the next stage of the same work**, and it is the one that turns "comping" from a
voice selection into a route with its own behaviour: what was measured about the melody's
actual influence on a comping part, the rule that follows from it, and six steps in
dependency order. Steps 0, B, A, A', C, D and E have landed; §9.4's four-note comping
chord is the remaining item, and it is still a proposal.

It is deliberately **not** in `docs/history/`, which is for completed plans and is never
extended. The shipped `voices=` axis is described in [voices-axis.md](voices-axis.md); this
document is about the **other two axes**, and about the fact that all three overlap.

Measurements are over `tests/data/but_not_for_me.mxl` (2/2, Eb major, 80 melody notes),
`texture=targets`, all 80 steps, unless stated otherwise.

---

## 1. What prompted this

A bass-voice request surfaced a defect — `--voices bass` produced a **3rd** in the middle
of the neck. Fixing it correctly meant asking *what the flag means*, and the honest answer
is that **`--voices` does not allocate voices at all.**

| selection | sounds exactly the two guide tones |
|---|---|
| `--voices alto` | **0 / 80** |
| `--voices tenor` | **0 / 80** |
| `--voices alto,tenor` | **80 / 80** |

And for the 2-note shape, *which* guide tone lands on top:

| top note is | steps |
|---|---|
| the b7 | **47** |
| the 3rd | **33** |

If `alto` and `tenor` were being placed as SATB voices, that 47/33 split would be a
musical fact. It is not. `get_comping_voicings` builds `midis = sorted(...)` and applies
`SHELL_DEGREES` as a **set** — `needed <= pcs` in `_shell_voicing`. The shape is a sorted
**set of chord tones**, and the voice names are decoration on top of a cardinality.

**So the comping route is already a second arranging mode** — one that states harmony
without pinning the melody — and the flag meant to select voices is not what selects it.
It selects *how many* chord tones.

That defect is fixed and documented in [voices-axis.md](voices-axis.md); what follows is
the larger thing it exposed.

---

## 2. The overlap, stated as a table

Three shipped flags. **Two of them answer the same question.**

| flag | question it claims | also answers "does the guitar sing?" |
|---|---|---|
| `--voices` | which voices the guitar plays | **yes** — via `voices_have_soprano` |
| `--texture` | where notes fall, how thick | **yes** — via an empty grip palette |
| `--bass` | who plays the bottom | no |
| `--grips` | which shapes may be chosen | no |

The overlap is not theoretical. It produces three observable oddities:

1. **`--voices soprano` was a no-op.** It was byte-identical to `--voices auto`, because
   the soprano's only remaining job was to switch the engine onto the melody-bearing
   route: `melody_voiced = voices_have_soprano(voices)` in `steps.py`. **Stage 2 closed
   this**: soprano alone is the melody and nothing else now — see `docs/one-fact.md`.
2. **The flags could contradict, so one had to be refused.** `melody_allowed` refused
   `--texture melody --voices alto` with a warning, because `melody` *already* meant
   "nothing but the tune". **That refusal was the seam showing, and Stage 2 closed it**:
   the melody-only claim is keyed on the voice selection, the two textures are gone,
   and a soprano-less selection comps on every texture.
3. **`--grips` is _not_ inert on a comping selection. An earlier draft of this document
   claimed it was, and the claim was wrong.** The route calls `get_comping_voicings`
   directly and never consults `slot_grips`, so `--grips duo`, `--grips shell`,
   `--grips drop2` and no `--grips` at all *ought* to agree. Measured over `--bars 0-2`
   they do not: four distinct arrangements. **Why is not established**, and it should be
   before anything is designed on the assumption either way — an unexplained measurement
   is not a licence to build on it.
4. **`--non-chord-tone` is already inert on the comping route.** `extension`, `diminished`
   and `sustain` come out byte-identical to one another across all 32 bars under
   `--voices alto,tenor`, and all three differ from the default when the guitar sings.
   This predates the proposal, and §4.2 would place stabs on off-beats — exactly where
   `textures.py` says those strategies produce "mud rather than colour". The grid and the
   strategies already disagree about weak beats; Stage D settles that rather than
   discovering it.

---

## 3. `--texture` is a 2-D space enumerated as a list

`TEXTURE_GRIPS` in `textures.py` shows the five values are really **two independent
questions**: what is stated × does the guitar sing.

| texture | target grips | fill grips | states harmony | sings |
|---|---|---|---|---|
| `uniform` | 6 grips | 6 grips | full chord | yes |
| `targets` | drop2, drop3 | shell, interval, melody | full chord | yes |
| `walking_bass` | **shell** | — | **comping** | **yes** |

(The table also carried `melody` and `melody_bass` rows — empty on both roles — until
Stage 2 keyed "the tune and nothing else" on the voice selection and deleted the two
textures; see `docs/one-fact.md`.)

**`walking_bass` is a comping style that also keeps the melody on top**, and the table says
so directly: its only target grip is `shell`, with no melody-bearing grip involved. Yet
measured, **80/80 steps** carry the written melody as the highest sounding note, with
`melody_voiced=True`.

| texture | notes/step | melody is the top note (`auto`) | (`alto,tenor`) |
|---|---|---|---|
| `uniform` | 4 | 80/80 | 11/80 |
| `targets` | 4 | 80/80 | 11/80 |
| `walking_bass` | 2, 3, 4 | 80/80 | 11/80 |

So `walking_bass` is a point in a 2-D space that the enumeration flattens into a
list. That is the design problem: **the three axes are not orthogonal, and the fix is to
make them so.**

---

## 4. Proposal: three orthogonal axes

### 4.1 What is stated — the *harmony* axis

Replaces the degree-family behaviour now implicit in `get_comping_voicings`. Each value is
a **degree family**, read from a table that already exists rather than re-derived:

| value | degrees | source table | status |
|---|---|---|---|
| `full` | root, 3rd, 5th, 7th | `CHORD_TONES_FROM_ROOT` | shipped default |
| `guide` | 3rd + 7th | `SHELL_DEGREES` | shipped (2-note comping) |
| `shell_root` | 3rd + 7th, lowest = root or 5th | `SHELL_DEGREES` + `BASS_DEGREES_6432` | **built** (Stage C) |
| `root` | root, else 5th | `BASS_DEGREES_6432` | shipped (`--voices bass`) |

**A shell chord-melody is already reachable, and it is not in this table.** `--grips shell`
produces a thin chord-melody today, and measured over `Ebmaj`/`Bb7`/`Cm7` it is *the same
degree family as `guide` with the melody pinned above it*:

| request | notes/step | melody on top | midis (`Ebmaj`, melody G4) |
|---|---|---|---|
| default (full chord-melody) | 4 | 4/4 | 50, 58, 63, 67 |
| `--grips shell` | 3 | 4/4 | 58, 62, 67 |
| `melody=none` (comping) | 2 | 1/4 | 62, 67 |

`--grips shell` and `melody=none` return **the same two guide tones**; the only difference
is the melody above them. So the degrees are not the question on this route — **whether
the melody is pinned is**, and that is §4.3's axis. Two consequences, both easy to get
wrong:

- **`harmony=guide` must not be assumed to subsume `--grips shell`.** They name the same
  degrees and reach them by different machinery: the shell chord-melody goes through the
  grip generators, which pin the melody to the soprano string; the comping route goes
  through `get_comping_voicings`, which takes no melody at all. If `harmony=guide` with
  `sings=yes` is routed through the comping generator, the melody is no longer pinned and
  the output changes. Whether it is, or whether it routes through the shell grip, is §6 Q2
  — and getting it wrong makes `--grips shell` either silently redundant or silently
  different.
- **The table's rows are all *degree families*, which is the comping route's vocabulary.**
  A shell chord-melody is a **grip** choice layered on a degree family, so no value in this
  table names it. That is a gap in the table, not a contradiction of it.

**`shell_root` is the case that was missing, and it is measured reachable: 11 of 11
chords.** Both guide tones present *and* the lowest note a root or 5th, at span ≤
`GRIP_MAX_SPAN["shell"]`, finds a shape for every chord in the head — all on the
**existing** `(5,4,3)` shell set. **No new string sets are required**, which is the single
most useful fact in this document, and Stage C confirmed it by building it.

**The implementation found something this section did not say, and it is the whole
difference between the family and a synonym for `guide`.** The rule has to be *the lowest
note is a root or 5th*, not *some root or 5th is sounding*: on an `Ebmaj` whose guide
tones are D and G, the plain three-note guide shape is `D G Bb`, which already **contains**
the 5th. An implementation asking the second question is satisfied by the guide-tone shape
itself, returns identical output to `guide`, and passes every other assertion in §4.1 —
which is precisely what the first one did. `shell_root` filters those candidates out
rather than the `guide` ones in, and
`tests/test_comping.py::test_shell_root_is_not_merely_a_shape_that_contains_a_bass_degree`
now exists to keep that from regressing.

Two honest costs, both already true of the shipped one-voice case:

- The lowest note is a root **or a 5th**, because that is what `BASS_DEGREES_6432` says a
  bass may be. The root is preferred; the 5th is a fallback.
- A degree family is a **set**, so the claim is thinner at arity 2 than at arity 3. Stated
  rather than hidden.

### 4.2 Where it falls — the *rhythm grid*

**A grid, not a rhythm name.** A grid is a set of `(beat, subdivision)` positions, and
it is what lets a user state a pattern the library has never heard of **without new code**:

```text
freddie     [(1,0), (2,0), (3,0), ...]     # every beat the metre has
charleston  [(1,0), (2,SUB)]              # 1 + and-of-2   -- a 4/4 figure
joe_pass    stabs on the ANDs; thumb on the beats
final_and   [(LAST, SUB)]                 # the upbeat of the bar's final beat
```

**Positions are bar-relative, and `LAST` is what makes that work.** `LAST` is the metre's
final beat, so `final_and` is 4.5 in 4/4, 2.5 in 2/2 and 3.5 in 3/4 — the same musical
idea at three different beat numbers. Spelling a position as a literal beat
(`and_of_4 = [(4, SUB)]`) makes a 2/2 or 3/4 head look as though the position does not
exist, which it does: measured on this 2/2 head the final upbeat is 2.5 and it is
selectable under `--skeleton eighths`. A grid that cannot be written in one metre and
played in another is not a rhythmic idea, it is a spelling.

**But `charleston` is a 4/4 figure and is *not* bar-relative** — and the reason it came out
silent on this 2/2 head was **not the metre at all**. This paragraph originally said it was
"a 4/4 idiom asked of a 2/2 bar… the mismatch is the arranger's, not the library's". That
was a misdiagnosis, reached from a measurement that was right and an inference that was not,
and the same two failure modes as [open-issues.md](open-issues.md) item 4 and item 10.

The measurement was correct — `charleston` **was** silent — and the cause was that a grid
could only *filter* melody slots, so a position with no written note was unreachable
whatever the pattern said. Only 41 of the 80 notes on this head fall on a beat, and the
Charleston names the and of beat 2, which almost none of them does. `joe_pass`, which
names the *ands*, was silent on all three committed fixtures for the same reason.

Stage 3 of item 10 landed the fix: on the comping route the grid now **generates** its
positions from the timeline rather than filtering the melody's. Measured on this 2/2 head,
every named grid now places something — `every_note` 63, `charleston` 63, `joe_pass` 64,
`final_and` 32 — and a Charleston is playable in 2/2.

**So the distinction below survives, but its consequence does not.** The spelling still
differs — a metre-relative figure is written against beat numbers and a bar-relative one
against `LAST` — and that is worth recording. What no longer holds is the conclusion that a
metre-relative figure *cannot* be played in another metre.

Which means a pattern table has to say which is which, because the two spell differently:

| | what it means |
|---|---|
| **`freddie`, `final_and`** | **bar-relative.** Playable in any metre; `LAST` resolves against it. |
| **`charleston`, `joe_pass`** | **metre-relative.** A named figure of a particular metre, and it is either right or it is a 4/4 figure in a 2/2 bar. |

Recording that as a property of the pattern rather than leaving it implicit is what stops
"the pattern silently did nothing" being read as a defect in the engine — the same failure
`TARGET_BEATS` avoids by naming *beats* rather than counting.

#### The grid is a *chord* selection, and the melody is separate

**These are two different questions and the flag was answering both.** What melody notes
sound, and where a chord falls under them, are independent — and the user has settled the
split:

- **Every written melody note sounds, down to a 16th.** The floor is on note *value*; two
  notes at or above it are never merged, whatever the grid does. Measured: both committed
  fixtures are ≥16th throughout (0 notes at 32nd or smaller in either), so the floor
  excludes nothing from either today. **This is now what the code does** — `--skeleton` no
  longer quantises at all, and every written note keeps the beat it was written on:

  | head | notes | `beats` | `eighths` | `sixteenths` | `notes` |
  |---|---|---|---|---|---|
  | `but_not_for_me` | 80 | 80 | 80 | 80 | 80 |
  | `i_was_doing_all_right` | 110 | **110** | **110** | **110** | **110** |

  `i_was_doing_all_right` used to keep 61 / 86 / 105 — **`eighths` dropped 24 of 110**,
  and only 11 of those were in the 5 tuplet bars: 13 were in the *straight* bars, because
  any two notes closer together than the grid shared a slot and the `pick` rule dropped
  one. **A note of the tune went missing, silently.** Quantisation was answering the chord
  question in the melody's name.

  All six `but_not_for_me` arrangements are byte-identical to their pre-change output, so
  the cost of this is paid entirely by the head that had the problem.

   **`--skeleton` and `--pick` are gone from `arranger head`**, and the flag table with
   them: the reduction they configured no longer exists, so keeping four names for one
   behaviour would be a lie. They had already stopped being flags — they were parameters
   of `add_common_arguments`, gated on a vocabulary belonging to `wjazzd`, which
   `head_cli` never passed — and the Weimar path has since been removed as well, so there
   is no second reducer left to converge. `arranger/slots.py` is what remains of the slot
   layer, and it is the engine's own rather than a loader's.

   **Passages elsewhere in this document still discuss `--skeleton` as if it were live** —
   §4.2's worked examples and §6 Q1 among them. They are left in place rather than
   rewritten because they record *why* the grid was built the way it was, and deleting the
   reasoning would lose the constraint that produced it. They describe a flag the tree no
   longer has; §9 is where the grid's behaviour now actually lives.

  The four table rows above (`beats`, `eighths`, `sixteenths`, `notes`) are therefore a
  record of a decision that has been *acted on*, not a live menu. The chord axis that
  they were holding a place for is Stage D, and when it lands it is a new flag rather than
  a revival of this one.

  **Two bugs were found on the way, both latent.** Triplet *durations* were being divided
  twice — the file writes them already reduced (`3 x 6720 = 2 x 10080`, a whole 2/2 bar) and
  the importer divided again, so a triplet quarter was **4/9** of a quarter where it is
  **2/3**; three of them spanned 4/3 of a quarter where the figure must fill two. Nothing
  noticed, because onsets are re-based per bar and tablature ignores `duration` — only the
  MusicXML writer reads it, and music21 refused the result, which is what finally surfaced
  a number that had been wrong the whole time. The two conventions are not separable
  arithmetically (6720 divides both ways) or per measure (24 of 36 measures come out whole
  under both); only `<normal-type>` distinguishes them.
- **A melody note with no chord position on it sounds alone.** The machinery is already
  built and already correct for this: `melody_alone_case` returns `MELODY_ALONE_TEXTURE`,
  which routes through `get_melody_only_voicing` and leaves `melody_only=False`. It is
  deliberately **not** the `NC` case, because the step *does* have a harmony — it is
  simply not spelled out under that note, and the flag would make the annotation read
  "(no chord - melody alone)" and claim a lie. That is AGENTS.md trap 6's shape, already
  handled by returning a *kind* rather than a bool.
- **The grid selection is a chord placement, not a melody reduction.** It has four rows:

| grid selection | a chord lands on |
|---|---|
| `beats` | every beat |
| `eighths` | every eighth |
| `sixteenths` | every sixteenth |
| `notes` | **every written melody note** — 110 of 110 measured |

**So `--skeleton` stops being one flag doing two jobs.** Today it decides both, by
*geometry*: a note is quantised to the nearest grid position and **ties are silently
dropped**. Measured on `i_was_doing_all_right`, `eighths` keeps 86 of 110 notes — and the
24 lost are not all triplets: 11 in the 5 triplet bars, **13 in the 29 straight bars**.
Any two notes closer together than the grid collide, in either kind of bar. That is why
splitting the two questions is not tidiness: the melody loss is an artefact of the grid,
and the grid should have no opinion about it.

#### A silent pattern has two causes, and only one is an error

A pattern can place no chords at all, for two entirely different reasons, and they need
different answers:

| cause | measured example | the right response |
|---|---|---|
| **the grid is too coarse** | `final_and` (2.5) under `--skeleton beats`, which offers only 1.0 and 2.0 | warn — the user asked for something the grid cannot express |
| **no melody note there** | a bar whose notes are all on the beat, under any grid | **nothing** — a chord cannot go where there is no note, and the melody-alone route handles it |

Warning on the second would be noise: "you asked for comping on the ands, there are no
notes on the ands" is not an error, it is the answer. Only the first deserves a message,
and it must name the grid that is too coarse. The test is therefore one-directional —
**the grid must be at least as fine as the pattern** — rather than the two-way
"resolution versus placement" an earlier draft of this section described.

`joe_pass` is not invented here: it is
[history/Arranging_Guide.md](history/Arranging_Guide.md) §"Joe Pass" Walking Bass & Comp
Style, which specifies the bass on beats 1–4 and "the melody and chord pops live primarily
on the **and** of beats".

**The seam already exists**, which is why this is cheap rather than greenfield:

| mechanism | what it already does |
|---|---|
| `_metric_weight` | "how strong is this beat" — 2 on beat 1, 1 on beat 3, and **-1 when there is no timing**, which is what keeps default output byte-identical |
| `_roles_for_slot` | target/fill allocation, already a **table** |
| **`_walking_slots`** | already **unions a rhythm grid with the melody grid** before the step loop, for exactly this reason: "a bar whose melody is one whole note still carries four bass notes" |

A comping style is therefore **a degree family + a grid**, which is precisely the pair
`_walking_slots` already demonstrates. [voices-axis.md §7](voices-axis.md) reserved this:
"a row in `MELODY_POLICIES` … the table and the seam exist, the rows do not."

**Corrected 2026-10-04 — that inference overreaches, and by a measured margin.** The
union is a seam for **beat-level** gaps inside a bar the melody *enters*; the quoted
claim is about such a bar, and it is accurate. It is not a seam for bars the melody
**abandons**, because `_walking_slots` walks "every bar **the melody touches**"
(`bass.py:835`). Measured on a three-bar head whose melody occupies bars 1 and 3:

| | bars walked |
|---|---|
| melody in bars 1 and 3 | **1, 3** — bar 2 has no beats to walk |
| melody in bars 1, 2 and 3 | 1, 2, 3 |

And a bar the melody abandons entirely is **not representable at all**: `headxml` counts
rests in `skipped`, so it contributes no slot and no bar number. A named grid therefore
loses **49 of 190 beat positions (25%)** across the three committed fixtures — a quarter
of the positions it names — and `hold=` cannot be the answer, because the missing thing is
not a sustain policy but the *chord timeline the grid would be written against*. That is
[open-issues.md](open-issues.md) item 10, and it is what makes the harmonisation engine
in this document's place rather than a rename of the flags.

#### The metre trap

A count without a denominator is not a metre (AGENTS.md trap 9). A beat grid **must** be
metric-aware or it will invent beats that do not exist:

| metre | `freddie` (every quarter) | the upbeat of the **final** beat |
|---|---|---|
| 4/4 | beats 1, 2, 3, 4 | 4-and — beat 4.5 |
| 2/2 | beats 1, 2 | 2-and — beat 2.5 |
| 3/4 | beats 1, 2, 3 | 3-and — beat 3.5 |

`But Not For Me` is **2/2**, so `freddie` on this head is **two** notes per bar, not four.
This is the same trap `TARGET_BEATS` already documents ("in 2/2 (two notated beats) beat 3
does not exist and only the downbeat is a target").

**The position is bar-relative, and an earlier draft of this table got that wrong.** It
read `and_of_4` as the literal *beat 4* and concluded there is "no and-of-4" in 2/2 or 3/4.
That is a statement about a beat *number* in a metre that does not have that beat, not
about a *musical position*: **the upbeat of the bar's last beat exists in every metre**,
and what changes is which beat number it falls on. Measured on this 2/2 head, bar 2's
final-beat upbeat is **2.5**, and it is present in the lattice under `--skeleton eighths`
and finer.

**So the grid must be written bar-relative** — "the and after the last beat", never "beat
4" — and it is still gated on the lattice, which is a *separate* and real constraint:

| `--skeleton` | bar 2 of this 2/2 head offers | final upbeat (2.5) present? |
|---|---|---|
| `beats` | 1.0, 2.0 | **no** — no subdivision to put it on |
| `eighths` | 1.0, 2.0, 2.5 | **yes** |
| `sixteenths` | 1.0, 2.0, 2.5 | **yes** |

Two different reasons a position can be unavailable, and only the first is about the
metre: **the metre decides which beat the position sits on**, and **the lattice decides
whether that position has a slot to sit in**. A grid naming the final upbeat therefore
needs `--skeleton eighths` or finer, and a warning when it is asked for under `beats` is
the honest answer — not silence, and not an invented beat.

### 4.3 Does the guitar sing

Asked **once**, rather than by `--voices`' soprano test *and* `--texture`'s empty palette
simultaneously. One flag; the property that the contradiction goes away and
`melody_allowed`'s refusal becomes unnecessary rather than load-bearing.

---

## 5. Naming: the part that needs a decision

`--voices` promises SATB allocation and delivers a cardinality. Three options:

1. **Re-document it honestly** — say it selects *how many chord tones and which
   degree family*, and stop implying voices are placed. **Recommended now.** Removes the
   over-promise, breaks nothing.
2. **Rename it** to something degree-shaped (`--harmony=guide|shell_root|root`). Clearer,
   but a breaking change to a shipped flag and to `MELODY_POLICIES`.
3. **Implement real voice allocation** — a shape that places a named voice on a specific
   degree. Much larger, and it fights `_shell_voicing`'s set semantics.

**Recommendation: (2) — but deferred, and Stage C landed the *vocabulary* instead.** This
reverses an earlier recommendation, and it reverses because a constraint has been
withdrawn: option (1) was picked because it "breaks nothing", and the project is pre-1.0
(no CHANGELOG, no deprecation policy, no stability classifier) with **compatibility of
shipped flags explicitly not a constraint** — a claim the corpus-removal release then
acted on, by removing the `corpus` subcommand and two flags outright, and Stage 2 acted
on again by deleting the `melody` and `melody_bass` textures. Re-documenting a flag that
is about to be replaced is work done twice.

**The rename did not happen in Stage C, and that was the plan rather than an omission.**
§6 Q2 settled as (C) — `harmony=` covers the melody-free comping route only — which means
`harmony=` **cannot express `soprano`**. Renaming `--voices` to `harmony=` in that state
would drop the axis's own headline case, so the two would have to land together: route
`harmony=guide` + `sings=yes` through the shell grip (option (A) in §6 Q2), deprecate
`--grips shell` as the redundant spelling, and rename in one commit. What exists now is the
harder half of that work — the degree families, `shell_root` at 11/11, and a name that
means what it says — with the spelling to follow.

What does *not* go away is the sequencing. A rename still wants the grid to land with it,
so that `harmony=guide` arrives with something for a grid to place, rather than a
replacement flag born with the emptiness option (1) was chosen to avoid.

Two live facts in the tree that this section did not know about, both settled in Stage C:

- `ArrangeOptions` carries **`melody: str = MELODY_AUTO`** (`options.py`), and
  `arrange_progression` takes a **`melody=`** keyword that is fed straight into
  `parse_voices`. A keyword named `melody` that takes `soprano,alto` reads as the melody
  *note* and is actively misleading; the rename is the moment to fix the name rather than
  inherit it.
- `options.py` cites **`MELODY_STYLES`** in `textures.py`. **No such table exists.** The
  real one is `MELODY_POLICIES`, keyed `auto` / `none` only. A live documentation error,
  independent of anything else in this document.

---

## 6. Open questions

**Read this before the list.** Several of these were answered by work recorded in §9, and a
reader who stops here will think they are still open when they are not. The list is kept
rather than pruned because the reasoning behind each answer is the useful part.

| | status now |
|---|---|
| Q1 grid vs `--skeleton`'s lattice | **moot.** `--skeleton` is gone (§4.2), and stage 3 of open-issues item 10 settled the substance: the grid *generates* positions rather than selecting from a lattice. |
| Q2 `harmony=guide` under `sings=yes` | settled as **(C)** — `harmony=` is scoped to the melody-free comping route. |
| Q3 rename `--voices` to `harmony=` | still deferred, and **§9.4 argues it should stay deferred longer than planned.** |
| Q4 does `--texture` survive? | **partly answered by Stage 2**: it lost `melody` and `melody_bass` to the voices axis (`docs/one-fact.md`), and §9.6 still argues against removing the rest. |
| Q5 where does the style table live? | open; gated on the DAG test. |
| Q6 free-form grid spelling | open, and still the main tension in the proposal. |
| Q7 `walking_bass`'s fate | open. |
| Q8 integer eighths or float? | **settled by implementation** — `SUB` is an integer and has been all along. |
| `melody_alone_case`'s fifth kind | **specified in §9.2** and scheduled as part of step B. |
| stab duration | **open, and not covered by §9.** It is not `hold=` (withdrawn); the claim is that the grid owns the rhythm, so a stab lasts until the next grid position. Worth deciding with Q6, since a free-form spelling would have to say it too. |
| the input's shape | **open, and the thing §9 is about** — a harmonisation engine whose input is a chord timeline rather than a list of melody notes. §9.4 finds it again from the arity side. |

**Q8 deserves a note, because the document still calls it unresolved.** `SUB` is `1` in
`textures.py` and is documented as *"the subdivision of a beat, in whole eighths. Integer on
purpose"*. The integer won by implementation and the question was never revisited.

1. **How does a placement grid sit on `--skeleton`'s lattice?** These are different
   things and they do not collide, which took a measurement to establish.
   `--skeleton` is a **resolution**: `_slot_key` derives `(bar, beat, subdivision)` from a
   *uniform* quantisation — `beats` forces subdivision 0, `eighths` pairs tatums,
   `sixteenths` takes every tatum — so it answers "how finely do I read the melody?", and
   it exists because a raw head runs to 10.7 notes per bar. The §4.2 grid is a
   **placement**: a selected subset of positions, which no strategy above can express. So
   a grid selects points *from* the lattice `--skeleton` produced, and two consequences
   follow: a style naming the final upbeat needs a lattice fine enough to contain one
   (`eighths` at minimum, since `beats` has no subdivision to put it on). The metre and
   the lattice are **separate** constraints and both are real. These are design inputs to
   Stage D rather than open questions about ownership.
2. **Does `harmony=guide` with `sings=yes` reach the melody through the shell grip or
   through `get_comping_voicings`?** — **settled as (C), deliberately, and the rename waits
   on revisiting it.** The degrees are the same either way, so this is decided entirely by
   machinery, and the two answers are not equivalent: the shell grip pins the melody to the
   soprano string, the comping generator never sees it.

   **(C) — `harmony=` is scoped to the melody-free comping route, and `--grips shell` stays
   a separate grip choice.** That is what Stage C built. `harmony=` therefore does nothing
   on any arrangement the guitar sings, which `test_the_axis_is_inert_when_the_guitar_is_singing`
   locks in rather than leaving to chance.

   The cost is accepted rather than argued away: **`harmony=` cannot express `soprano`, so
   on its own it is a strictly weaker `--voices`.** That is precisely why the rename is
   *deferred* instead of done — under (C) there is nothing for the new name to replace, and
   renaming `--voices` to `harmony=` would lose the axis's own headline case. Two flags
   reach adjacent territory (`--grips shell` and `--harmony guide`), and §4.1 says so
   rather than leaving a reader to discover it.

   **(A) is the follow-up, and it is what the rename waits for**: route `harmony=guide` +
   `sings=yes` through the shell grip, deprecate `--grips shell` as the redundant spelling,
   and only then rename. (A)'s output is byte-identical to today's `--grips shell` by
   construction, so it is a spelling change rather than a musical one — which is why it is
   worth doing as one commit.

   **(B) — extending the comping generator to state the melody as a separate voice — is not
   recommended at all.** It is new behaviour rather than a rename, and it is where
   AGENTS.md trap 6 lives: unifying two branches on a shared predicate is how a step ends
   up annotated as having a harmony it does not have.
3. **Does `--voices` get renamed, re-documented, or made real?** (§5 — settled: renamed,
   Stage C)
4. **Does `--texture` survive?** If the harmony axis takes over its degree behaviour,
   `texture` may reduce to the rhythm grid plus a role policy — a smaller flag doing a
   bigger job.
5. **Where does the style table live?** A `COMPATING_STYLES` table in `textures.py`
   beside `MELODY_POLICIES`, or its own module. The DAG in `tests_package_dag.py` decides:
   `textures` sits above `grips`, so a table that *names grips* has to live at or above
   `textures`.
6. **Can a user pass a grid on the command line?** "Harmony on the and of 4" is a
   legitimate request, but a free-form rhythm argument is a parsing surface with no
   natural syntax. A row **name** is safer; a closed set of names is limiting. This is the
   main tension in the whole proposal. **Partly settled:** Stage D shipped the **named
   rows** first, as `--grid`, and deferred the free-form spelling to a second commit in the
   same stage. So the closed set is what exists today, and the question is now "what does
   the free-form surface look like" rather than "names or grammar" — a strictly smaller
   question, and one the shipped table can inform.
7. **What happens to `walking_bass`?** It is currently a `texture` and is really *comp +
   sings + thumb*. Under the proposal it becomes `harmony=guide`, sings=yes, `bass=walk` —
   and **its shipped output must stay byte-identical**, which is the acceptance test for
   the whole refactor.
8. **Is the subdivision an integer count of eighths, or a float?** Proposed: **integer
   eighths**, because it avoids float comparison for a notated position — the same
   reasoning `_BEAT_EPSILON` exists for. Unresolved.

---

## 7. What is deliberately **not** proposed

- **No change to `voicing_cost`.** Its 8-element tuple is the library's central
  invariant (AGENTS.md). A register or density preference belongs in the
  *generator's* degree rule, not in the selector's cost.
- **No new grip families.** `shell_root` is reachable on the existing shell sets (11/11).
- **No change to the drop-2 tables**, and no touching the 54 hardcoded tab strings.
- **No default change.** Every existing arrangement must come out byte-identical, which is
  the acceptance criterion for any part of this that gets built.

---

## 8. Staged approach

The proposal is four separable changes of very different size and risk. This is the
order, the reason for each, and what "done" means for that stage. **No stage starts
before the one above it is green**, because each acceptance test below is only
meaningful against the tree the previous stage left.

### Stage A — Correct this document

The §2 corrections above, plus anything else the implementation turns up. It goes first
because **a proposal whose stated evidence contains a wrong measurement is worse than no
proposal**: it is an implementation target that cannot be trusted, and the `--grips` claim
had already survived unchallenged in the document.

Acceptance: every measurement in §2 and §6 reproduces on the committed tree, and the
unexplained `--grips` result is either explained or explicitly marked open.

### Stage B — Close the doc-test gap

`tests/test_docs.py` holds an explicit `DOCUMENTS` list, and **neither this document nor
`voices-axis.md` is on it**; `AGENTS.md` links neither. So the link-resolution and
reachability checks pass *vacuously* for both.

That is not hypothetical. This document was found on disk with its body **duplicated**,
its §7 bullet list spliced mid-word, and 37 U+FFFD replacement characters in it, while
`make check` reported **938 tests OK, pyright 0 errors, ruff clean**. The gate was green
because it was not looking. That is the AGENTS.md "a quiet run is not evidence" case in
its purest form: a check that enumerates its inputs by hand silently skips whatever was
added last (trap 1), applied to documentation.

**Done.** All three documents are in `DOCUMENTS` and linked from `AGENTS.md`, and a
twelfth test now derives the expected list from the filesystem:

```
test_every_document_on_disk_is_in_the_list
```

so a document that exists and is not registered fails the suite rather than quietly
escaping every check that reads `DOCUMENTS`. **That test paid for itself immediately**:
adding it surfaced a third unregistered file, `docs/reharmonisation-proposals.md`, which
was linked from `AGENTS.md` but whose links no check had ever resolved. Three documents
were unverified, not two.

Verified by mutation rather than by assertion — each of these was introduced, observed to
fail, and reverted:

| mutation | caught by |
|---|---|
| a broken relative link added to `comping-styles.md` | `test_the_relative_links_between_documents_resolve` |
| a wrong version stated in `voices-axis.md` | `test_the_stated_version_is_the_packages_version` |
| **both** `AGENTS.md` links to `comping-styles.md` removed | `test_the_routing_table_reaches_every_document` |
| a new unregistered `docs/brand-new.md` created | `test_every_document_on_disk_is_in_the_list` |

The first row of this table was, briefly, a live failure. Writing it up here put the
literal three-part version number into this document as the example of a wrong version,
and `test_the_stated_version_is_the_packages_version` reads **every** `\d+\.\d+\.\d+`
as a version claim wherever it appears — so registering this document made the suite fail
on prose describing its own mutation. That is the check working as designed on a document
that had just come under it, and the fix was to stop writing a version-shaped literal in
a document that is now version-checked. It bit twice, because the first fix described the
string it had just removed. Worth knowing before quoting any version number here.

The third row carries a caveat worth keeping. Removing *one* of the two `AGENTS.md` links
to this document — the routing table and the index table each name it — leaves the suite
**green**, because the test asks "is it reachable?" and it still is. That is the test
behaving correctly rather than a hole in it, but it means reachability is a weaker signal
than it looks: a document linked once, in one place, is fully protected by that one link.

`AGENTS.md`'s stated counts moved with it, and have moved again since — the tree is at
**883 tests OK (skipped=2)**, with `tests/test_docs.py` still 12 of those.
The old line said "11 of those 926" while the line above it said 938, so it was already
internally inconsistent before Stage B touched it.

### Stage C — Rename and consolidate the axis — **partly done**

**Landed: the `harmony=` axis and the `shell_root` family.** `HARMONY_STYLES`,
`HARMONY_POLICIES`, `HARMONY_AUTO` and `harmony_allowed` are in `textures.py`;
`get_comping_voicings` and `_shell_voicing` take `shell_root`; the keyword threads
through `arrange_progression`, `ArrangeOptions`, `arrange_slots`, `_corpus_options` and
both CLIs. Inert twice over — `auto` resolves to the shipped `guide`, and the axis is read
only by the comping route — and all six published arrangements are byte-identical.

**Not done: the rename, and §6 Q2 is now settled as (C)** — `harmony=` covers the
melody-free comping route and `--grips shell` stays a separate grip choice. That settles
*why* the rename did not happen: `harmony=` cannot express `soprano`, so under (C) it is a
strictly weaker `--voices` and renaming would drop the axis's headline case. `--voices` is
still `--voices`, and `melody=` still carries a voice list.

The follow-up is §6 Q2 option (A) as **one commit**: route `harmony=guide` + `sings=yes`
through the shell grip, deprecate `--grips shell`, rename. Its output is byte-identical to
today's `--grips shell` by construction, so it is a spelling change rather than a musical
one — which is what makes it safe to do all at once. The vocabulary and the honest name are
the part that was worth landing first.

**`MELODY_STYLES` — the table that does not exist.** `options.py` cited it in a comment;
the real one is `MELODY_POLICIES`, keyed `auto` / `none`. **Fixed**: the comment now names
the table that exists.

### Stage D — The rhythm grid (**partly built**: `grid=`; `hold=` withdrawn; blocked on open-issues item 10)

The largest genuinely new work, and the only stage that adds a concept rather than
renaming one. `joe_pass` and `charleston` are the payoff.

**Landed: the `grid=` axis.** `GRID_STYLES`, `GRID_PATTERNS`, `grid_allowed`, `parse_grid`
and `resolve_grid` are in `textures.py`; the keyword threads through
`arrange_progression`, `ArrangeOptions`, `arrange_slots`, `arrange_xml_head`, `arrange_head`
and both CLIs as `--grid`. Inert by default — the default is `every_note`, and every
published arrangement is byte-identical. (This stage shipped a `GRID_AUTO` sentinel that
resolved to `every_note` unconditionally; §9.3 step A later **withdrew** it, and
`GRID_DEFERS_TO_MELODY` in `textures.py` is what the call sites read now.)

Three things the implementation settled that this section did not say:

- **`every_note` is not a pattern with positions; it is the absence of one.** Reading
  its "does it place anything?" off `grid_positions` reports it as placing nothing in
  every metre, which made the *default* warn everywhere. Caught by
  `test_a_bar_relative_pattern_is_allowed_in_every_metre`. "Places nothing" and "has no
  positions to place" are different claims, and only the first is a mismatch.
- **The refusal is unreachable through the shipped vocabulary.** Measured over every
  metre-relative row against every metre from 1 up: none is ever refused, because
  `charleston` keeps its beat 1 (which exists everywhere) and `joe_pass` is built on
  `ALL`. The two warning messages are therefore exercised against a *temporary* row
  (`_temporary_pattern`), and `test_no_shipped_row_is_a_mismatch_in_any_metre` exists
  to keep that fact from being quietly forgotten — a check no input can fail proves
  nothing about the axis.
- **An off-grid slot is a melody-alone note on one route and a rest on the other**, so
  it needed a **fourth kind**, `MELODY_ALONE_REST`, not a bool. The guard ordering in
  `decisions.melody_alone_case` then cost 12 tests across two attempts, because each
  ordering fixes one route and breaks the other — see `AGENTS.md` trap 12. Measured on
  `but_not_for_me`, all 80 steps: with the guitar singing, `freddie` sends 39 to
  melody-alone and `joe_pass` 41, with **no note lost**; with it comping, the same 39
  and 41 become rests.

**What the grid did *not* turn out to touch: the bass line.** Measured on
`texture=targets, melody=alto,tenor, bass=walk`, `bass` is `[51, None, 52, None]` both
at `grid=auto` and under `grid=freddie`. The walk visits whole beats only and a grid
only removes *chords*, so the two axes are orthogonal — which is the orthogonality
claim of §4 tested rather than asserted. An earlier reading of that measurement as a
`bass=walk` bug was wrong: `bass=walk` with `texture=uniform` is **refused by design**
(`bass_allowed`, with a warning naming `texture='targets'`), and the diagnostic was
missed only because no `Diagnostics` collector was passed.

**Not done, and deliberately:**

- **The free-form grid spelling** (§6 Q6). Deferred to a second commit in this stage,
  on the agreed basis that the named table lands first and is measured. This is the
  one question §6 called "the main tension in the whole proposal", and it stays open.
- **`hold=` — the sustained baseline. Withdrawn, 2026-10-04, on measurement.** This entry
  originally read: a style is a *bundle*, `grid` says where the stabs fall and `hold`
  what sustains underneath, and "there is **no sustain concept anywhere in the step
  model**". Two measurements dissolve it:

  1. **A stab already lasts as long as the note under it.** `step.duration` *is* the
     melody note's duration, and it carries the full set the score writes — 0.25, 0.375,
     0.5 and 1.0 across the three fixtures, identical on the steps and on the source
     slots. `tabstaff` already draws it as width and `tabxml` already caps a span by it.
     So a chord tied to the note — across a barline or otherwise — needs no new machinery,
     and "no sustain concept" is literally true and materially misleading.
  2. **The two cases were conflated.** Under chord-melody (`every_note`) the chord *should*
     be tied to the note. Under a comp grid (`freddie`, `charleston`) it should be struck
     short. Bar 4 of `but_not_for_me` is a whole note, and `every_note`, `freddie` and
     `charleston` all emit `dur=1.0` there — so a stab is a whole note. **Duration is
     inherited rather than chosen**, and that is a real gap — but it is the *inverse* of
     what this entry proposed: the chord needs to stop *outlasting* the note, not to
     outlast it.

  The gap is real and it is still in Stage D's scope, but it is not a `hold=` flag: it is
  the grid owning the rhythm, so a stab's duration is the distance to the next grid
  position. That change cannot be made until the grid can *place* a stab at all — see
  [open-issues.md](open-issues.md) item 10, where a quarter of the positions a grid names
  produce nothing. **Withdrawn rather than deferred**, because as worded it is a no-op and
  leaving it in the document invites someone to build it.

  §6 Q5's question about where the style table lives survives the withdrawal, and the
  answer is now a row of `{grid, harmony}` — composition rather than fusion — with stab
  duration falling out of the grid once item 10 is fixed.

Two things must be settled **inside** this stage, not discovered by it. The first is now
settled and the second remains a design decision:

- **The lattice relationship** (§6 Q1). The grid selects positions from `--skeleton`'s
  output, so it needs a lattice fine enough to hold the positions it names: a style
  naming the final upbeat needs `--skeleton eighths` or finer, because `beats` has no
  subdivision to put it on — measured on this 2/2 head, whose final upbeat is **2.5** and
  which offers it under `eighths` but not under `beats`. That is what keeps `--skeleton`
  and the grid complementary: **a resolution and a placement, not two owners of one
  thing.** The metre decides which beat the position lands on; the lattice decides whether
  it has a slot to land in, and an earlier draft of this document confused the two.

- **`--non-chord-tone`'s inertness on the comping route** (§2 oddity 4) — **measured, and
  the concern dissolves.** A guide-tone comp is the same pair of notes whether the melody
  above it is a chord tone or a 9th, and the same on beat 1 as on beat 2: `Ebmaj` with the
  9th `D5` over it returns `[2, 7]` in every case, with `non_chord_tone=False`, no strategy
  consulted and no warning. The strategies are not "a no-op on weak beats" — they are
  **structurally unreachable** from this route, because `get_comping_voicings` is never
  handed a beat and never sees the melody pitch that a tension strategy would resolve.
  The guitar states the chord; the tune is somebody else's, so there is no tension of ours
  to treat.

  That control is **not vacuous**, which is worth saying because a measurement that cannot
  fail proves nothing. On the melody-bearing route the same progression *does* change with
  the beat, and under `texture=targets` it changes sharply: a four-note chord on beat 1, a
  three-note shell on beat 2. The beat is consulted exactly where it should be, and the
  comping route is beat-independent by construction rather than by accident.

  **So the grid can place a stab anywhere the lattice offers**, on a strong beat or a
  weak one, without opening a question about tension treatment — there is none to apply.
  One fewer decision to make, and one fewer place for a future bug to hide.

### What is *not* a compatibility constraint

"Shipped flags may change" governs **flag names and CLI spelling**. It does not govern
the acceptance criterion in §7: an arrangement produced with **no flags passed** must
still come out byte-identical. That is about not changing the music under people who
never opted in, and it holds however freely the flags are renamed.

### The flag survey this rests on

Every `head` flag, measured on `tests/data/but_not_for_me.mxl` (2/2, Eb, 32 bars) against
a comping baseline of `--voices alto,tenor`. "—" means not separately measured.

| flag | under a comping selection | when the guitar sings |
|---|---|---|
| `--texture` | changes | changes |
| `--grips` | changes — see §2 oddity 3 | changes |
| `--non-chord-tone` | **inert** — see §9 | changes |
| `--fallback` | changes | changes |
| `--fret-min` / `--fret-max` | changes | — |
| `--bass none` | inert (already the default) | — |
| `--bars`, `--part` | input scope | input scope |
| `--tab`, `--melody`, `--mutes`, `--bars-per-line` | render only | render only |
| `--html`, `--musicxml`, `--gp5` | output format | output format |

Only `--non-chord-tone` goes inert on the comping route for a reason a user could act on,
and §9 is that reason: it is not inert by policy but because the code path that implements
the three strategies is only reached from the melody-bearing branch. `--bass none` is inert
because it names the default, not because of the route. Everything else is either live and
orthogonal, or already spoken for by a stage above.

`--skeleton` and `--pick` were in this table until the Weimar path was removed; they had
become unreachable parameters rather than flags, and both are gone. `--melody` is proposed
for removal in §9 as well.

---

## 9. The comping route, measured — a staged plan

**Steps 0, B, A, A', C, D and E of this section are built**; §9.4's four-note comping
chord is the one remaining proposal. It records what
was measured while answering "what does a pure comping part need?", and the order the
work has to happen in. Every number below was measured on the committed fixtures; none is
predicted.

**Where the work stands, for whoever picks this up cold:**

- **Steps 0, B, A, A', C and D are implemented.** Step 0 pinned melody independence as a
  test, step B made a slot's melody `Optional`, step A declared `every_note` a property
  rather than a sentinel, step A' made a **chords-only lead sheet** loadable (`Head.bars`
  is now the file's measure extent rather than the melody's span), step C made
  `--non-chord-tone` reach the comping route at harmony level with the §9.2 onset guard,
  and step D made the soprano **per slot** so a soprano-named selection comps the grid
  positions its tune does not articulate at, and step E — `--voices soprano` giving the
  melody and nothing else — landed ahead of the others as Stage 2 (`docs/one-fact.md`).
  §9.4 is the one item still a proposal; each description below carries its own **Landed**
  marker where it has one.
- **Every decision in §9 is settled.** The questions that shaped it — what `every_note` means
  on a head with no melody, whether the melody-less file warns or is silent, what an unknown
  grid does, whether `--fallback` reaches this route — are all answered below and marked as
  decisions rather than left open.
- **Read §9.1 and §9.2 first** for what is true of the code today, then §9.3 for the order.
  §9.4 is the one item that reorders the plan if adopted, and §9.5 has the commands and the
  fixture needed to re-measure any of it.
- **Two traps are load-bearing and easy to undo.** Step 0 must land before step C, or C's
  intended change to the *harmony* is indistinguishable from a regression in *placement*.
  And the chords-only fixture does not exist in the tree — §9.5 carries its content, because
  `/tmp` does not survive.

The intent this serves: the project makes **chord-melody** arrangements, and should also be
able to comp a lead sheet for a band where a horn takes the tune and a bass player takes
the root. That is not an extension of the current entry point — it is a different question
about the same chords — and §8's stages do not reach it.

### 9.1 Five measurements

**The comping route is already melody-independent, and structurally so.** Every melody pitch
in `but_not_for_me.mxl` was replaced with a wild high non-chord tone (F♯5–F6), keeping every
chord, bar, beat and duration:

| selection | steps | melody scrambled |
|---|---|---|
| `alto,tenor` | 102 | **identical** |
| `bass` | 102 | **identical** |
| `tenor` / `alto` | 102 | **identical** |
| `alto,tenor,bass` | 102 | **identical** |

Not one fret moves, and the same holds on hand-written input. Two independent points
enforce it: `get_comping_voicings` takes no melody argument at all, and `steps.py` passes
`melody_pc=None` into `voicing_cost` deliberately — *"there is no melody on the guitar for
the wrong-note count to excuse."* `melody_pc` is the only melody input to the cost tuple,
so with it absent no melody can reach selection.

**But the melody still decides how many comps, and when.** `every_note` yields one slot per
written note (80 of 80); `freddie` yields 102, because stage 3 unions the grid's own
positions in. So a horn player's phrasing determines the guitar's *rhythm* even though it
cannot touch its *shapes*. That split is right for a comping part — the grid choosing when to
stab is the whole point of the axis — and it is the reason `every_note` is the shipped
default rather than a bug.

**`--non-chord-tone` is inert on the comping route, and the table above predicted it.**
Measured on this document's own example, a passing D over Cmaj7:

| | `--non-chord-tone extension` | `diminished` |
|---|---|---|
| `voices=auto` | `harmonized_as=Cmaj9` | `harmonized_as=Bdim7` |
| `voices=alto,tenor` | `None` | `None` |
| `voices=alto,tenor,bass` | `None` | `None` |

The cause is structural rather than a policy decision: all three strategies live in
`prepare_step`, and `prepare_step` is called only from the melody-bearing branch. The
comping branch calls `get_comping_voicings` directly. **`--non-chord-tone` is not a
melody-route option that leaks; it is unimplemented on half the engine.**

**Naming the soprano and the grid are coupled exactly where they should be free.** The two
examples that motivated this section:

| | steps | notes/step |
|---|---|---|
| `grid=freddie --voices alto,tenor` | 102 | 2 — **the guide tones, as asked** |
| `grid=joe_pass --voices soprano,alto,tenor,bass` | **80** | 4 — **the grid is ignored** |

`joe_pass` lands on offbeats, and `voices_have_soprano` routed the whole arrangement to the
melody-bearing branch, whose slots come from `head_skeleton` — one per *written note*. A
grid could only filter there, never add, because adding a position with no melody note means
inventing a top note and the melody route's contract is that the melody pins the voicing.
So one predicate decided both *how the harmony is built* and *whether the guitar sings the
tune*, and naming a soprano quietly moved every slot to the branch where grids could not
create anything.

**Step D fixed this — that panel is the "before" measurement.** The same command now yields
**105** steps: the 80 written onsets still sing, and the 25 grid positions the tune does not
*articulate* at carry a comping shape instead — a three-note shell, because a silent soprano
is not one of the sounding voices. The grid **adds** now; it no longer merely filters. (A
position the tune merely *sustains* through is not an onset either, so it comps too; that is
§9.3 step D below, and it is why the count is 105 rather than 80 plus only the silent
positions.)

**A chords-only file is refused, and two separate melody dependencies hide behind that
one error.** Measured on a synthetic four-bar lead sheet — six `<harmony>` elements, zero
pitched notes:

```
$ python -m arranger head leadsheet.musicxml --voices alto,tenor
arranger head: error: leadsheet.musicxml has no readable melody part
```

Bypassing the loader does not get further. `Head.bars` is derived from `head.notes` and
returns `(1, 1)` when there are none, and `chord_slots` iterates `range(lo, hi)` from it —
so **every** grid produces nothing, not just the melody-anchored one:

```
notes = 0    chords(timeline) = 6    head.bars = (1, 1)
grid=every_note  chord_slots= 0
grid=freddie     chord_slots= 0     <- a real pattern, silently inert
grid=joe_pass    chord_slots= 0
```

Supplying the bar range from the timeline instead makes the grids work immediately, and
`joe_pass` lands on the offbeats as it should — the pattern was never the problem:

```
grid=freddie    16 slots   bar 1 beat 1.0 Dm7, bar 1 beat 2.0 Dm7, ...
grid=joe_pass   16 slots   bar 1 beat 1.5 Dm7, bar 1 beat 2.5 Dm7, ...
grid=final_and   4 slots   bar 1 beat 4.5 Dm7, bar 2 beat 4.5 Cmaj7, ...
```

**Every one of those slots carried the placeholder melody**, so this route is 100% sentinel —
which is what makes step B blocking rather than cosmetic.
### 9.2 The rule this gives

> Where the guitar sings, a grid position carries the melody plus whatever chord voices the
> slot warrants. Where it does not, the grid position is the chord's own voices. Where no
> melody note is sounding, the slot is harmony-only and the melody is not consulted — except
> for reharmonisation, and **only at an onset**.

Three states, not two, and the middle one is not a rare edge case. Every `chord_slots`
position across the six fixtures and two grids:

| | onset | **held** | silent |
|---|---|---|---|
| `The_Jitterbug_Waltz` | 56 | **122** | 42 |
| `Trouble_in_Mind_Blues` | 54 | 16 | 42 |
| `but_not_for_me` | 82 | 16 | 28 |
| `heres_that_rainy_day` | 88 | 28 | 16 |
| `i_was_doing_all_right` | 112 | 24 | 4 |
| `tenor_madness` | 304 | 68 | 44 |
| **total** | **696** | **274** | **176** |

**A quarter of all positions carry a note held across rather than articulated.**
`melody_at` returns those happily — "last onset at or before" is the right rule for
*alignment*, so a stab under a held note is labelled with the note actually sounding — which
is why they have to be distinguished explicitly rather than left to a two-way answer. A held
note was **already harmonised at its onset**; substituting the chord beneath it now would
re-decide a decision already made, under the very note that motivated the original one.

| state | the slot is | reharmonise? |
|---|---|---|
| **onset** here | melody articulates on it | **yes** — the anticipation a comping player makes |
| **held** across | a note already sounding | **no** — decided at its onset |
| **silent** | nothing sounding | **no** — the chord symbol stands |

### 9.3 The steps, in dependency order

**Step B moved ahead of step A, and step A' was added.** B is blocking rather than cosmetic:
a chords-only head is *100% placeholder melody*, so `melody: Optional[str]` has to land
before that route can exist at all. A' is the chords-only entry the measurements above
called for, and it depends on both.

**Step 0 — pin melody independence as a test.** Scramble every melody pitch; assert no fret
moves on any non-soprano selection. **This lands before step C deliberately**: C makes the
melody affect the *harmony* on this route for the first time, and this test is the only way
to tell "the harmony changed, as intended" from "placement regressed". Nothing may re-tune
the comping selector to consider the melody.

**Step B — report the melody state instead of inventing one.** `melody_at` keeps its two-way
answer for callers that only need "is a note sounding" (the staff renderer, the bass walker);
a sibling returns **onset / held / silent**. `chord_slots` stops inventing a melody for a slot
that has none, `ArrangementStep.melody` becomes `Optional[str]`, and `_PLACEHOLDER_MELODY` is
**deleted rather than hidden**. It exists only because a harmony-only step needed *a* melody
string to satisfy `melody: str`, and under §9.2 it has no reason to exist.

It is also the visible half of item 10's deferral: `Cmaj7  C4  (shell - 3rd & 7th, partial)`
is printed by the default line tab today, 14 times on `but_not_for_me` under
`--voices alto,tenor --grid freddie`, and reads as a claim that the guitar played C4. It did
not. The sentinel is indistinguishable from a real note by equality — all 30 `"C4"` slots
across the fixtures sit on genuinely written C4s — so any test asserting
`melody == _PLACEHOLDER_MELODY` can pass for the wrong reason, including the one that
currently documents the deferral.

**Landed.** `headxml.melody_state` is the sibling, `chord_slots` emits `None` for a slot
no note occupies, `ArrangementStep.melody` is `Optional[str]`, `_PLACEHOLDER_MELODY` is
deleted, and the renderers print the absence blank — the sentinel-equality test became
`assertIsNone`. Held slots still carry the note in force (Option A above), so the
three-state split is exposed by `melody_state` rather than by the field; the fifth
`melody_alone_case` kind is still not in this step.

**Step A — `every_note` as a declared property.** It is not a rhythm pattern but the *absence*
of one: `GridPattern(positions=())`, `on_grid` true for every beat, `grid_allowed` true
unconditionally because reading it off `grid_positions` would report "places nothing in every
metre" — the false reading that check exists to avoid. Four sites compare
`== GRID_EVERY_NOTE` by name (`textures.py` twice, `headxml.py` twice) and a fifth returns
it as `resolve_grid`'s fallback. Replace them with a `GRID_DEFERS_TO_MELODY` table read, so a
second melody-anchored grid later is a table entry rather than five more branches. **Stays
the default.** Gate: all 96 arrangements across the six fixtures byte-identical.

**And `grid=auto` goes with it.** The sentinel is a pure alias, which is the one axis-wide
convention it can safely break:

```
GRID_POLICIES = {'auto': 'every_note'}
grid=auto         2/4 -> every_note   warnings=0
grid=every_note   2/4 -> every_note   warnings=0
voices=alto,tenor   auto == every_note: True    (identical voicings)
voices=auto         auto == every_note: True
```

Every other axis's `auto` **decides something** — `bass=auto` walks under a thumb texture and
stops otherwise, `voices=auto` is a sentinel that must be resolved before use and skipping
that step has already been one bug in this codebase. `grid=auto` resolves to `every_note`
unconditionally and is then never read again: five sites define or pass it, none branches on
it. Its only remaining job would be to name the default, and `every_note` is already a
selectable member of `GRID_STYLES` that the CLI help already calls the default.

**This was nearly withdrawn, and the reason it was is worth recording.** An earlier draft of
this plan made `auto` resolve against the head — `every_note` when there is a melody,
`freddie` when there is not — so that a chords-only file would harmonise without a named grid.
The measurement above is why that was a bad idea rather than a good one: **`auto` resolving by
melody presence looks correct on all six committed fixtures, every one of which has a
melody**, so the context-sensitivity would be invisible to the entire suite. It was also
rejected on its merits — the default arrangement of a chords-only file is empty, and that is
the decision, not an oversight (step A').

So the departure from the house rule that every axis carries a `*_AUTO` sentinel stands, and
is recorded here so a later reader does not "restore" it. The sentinel's purpose is to let an
axis defer to context; on this one there is no context to defer to.

`resolve_grid`'s metre-mismatch fallback stays, because it is not `auto`'s: it fires for an
explicitly named metre-relative figure such as `charleston` asked of a 2/2 bar. It can never
fire for `auto`, because `every_note` is allowed in every metre by construction.

**Three tests encode the reason rather than the spelling, and are inverted rather than
deleted.** `test_auto_resolves_to_every_note` and `test_a_resolved_auto_never_warns` state
that the default is inert; both properties survive under `every_note` and are worth keeping
in that spelling. `test_a_pattern_may_be_named_on_the_command_line` asserted
`parse_grid(GRID_AUTO) == GRID_AUTO`; the inverse is that `auto` is no longer vocabulary and
is now refused like any other unknown name.

**One line here is a behaviour change rather than a rename, and it is decided.**
`headxml.py` currently coerces anything unrecognised before parsing:

```python
resolved = grid if grid in GRID_STYLES else GRID_AUTO
```

That line is what makes `grid=auto` reach `parse_grid` at all, and it also means a library
caller passing `grid="half-time"` is **silently given `every_note`** — the exact guess
`parse_grid`'s own docstring refuses (*"a pattern name is a musical claim about where a chord
lands, so guessing one would return a part that comps somewhere the caller did not ask for"*).
The CLI is unaffected, because `argparse` choices reject it first.

**Decided: delete the coercion and let `parse_grid` raise.** The library and the CLI should
answer an unknown grid the same way, and the rule the codebase already states — *"a spelling
nobody recognises is a question, and answering it by dropping the voice would hand back a part
missing something nobody asked it to drop"* — says the answer is to refuse. `auto` was the
only thing that ever made this line reachable, so removing the sentinel removes the guess with
it rather than relocating it.

**This is a behaviour change for library callers, not a rename**, and it belongs in the commit
message as one: `arrange_xml_head(..., grid="half-time")` returned `every_note`'s arrangement
and will raise `ValueError` instead. Nothing in the committed fixtures or the CLI is affected,
so it is observable only from library code — which is also why nothing in the suite will
catch its absence, and why it needs its own test rather than being left to the gate.

**Landed.** `GRID_DEFERS_TO_MELODY` — **derived** from `GRID_PATTERNS` (`positions == ()`), so a
grid cannot be emptied without becoming melody-anchored — and its `grid_defers_to_melody` read
replace the five `== GRID_EVERY_NOTE` sites (`on_grid`, `grid_allowed`, `resolve_grid`, and
`chord_slots` and `_merge_chord_slots` in `headxml`). `GRID_AUTO` and `GRID_POLICIES` are
**withdrawn**: the default is `every_note` outright, `parse_grid("auto")` raises like any
unknown name, and `headxml._merge_chord_slots` no longer coerces an unrecognised grid to
`every_note`. Three tests encode the reason and were **inverted rather than deleted**:
`parse_grid(GRID_AUTO) == GRID_AUTO` became "`auto` is refused", `test_auto_resolves_to_every_note`
was re-spelled as the default naming `every_note` (`ArrangeOptions().grid`), and
`test_a_resolved_auto_never_warns` became `test_the_default_grid_never_warns`. A new
`tests/test_headxml.py::TestAnUnknownGridIsRefused` covers the library-only behaviour change.
Gate: all six fixtures byte-identical, plus the new tests.

**Step A' — a chords-only head is a valid input.** Three settled decisions:

1. **The loader records the measure count**, and `Head.bars` reports it. `bars` becomes a
   fact about the file rather than about the melody, so a head with no parseable `<harmony>`
   still knows how long it is, and a head whose changes span bars 1 and 20 with nothing
   between is 20 bars rather than a span of the same two numbers by accident.
   `_choose_part` stops requiring `_part_note_count(p) > 0`.
2. **`every_note` defers to the melody, so a chords-only head produces nothing — by default
   as well as when named.** `auto` resolves to `every_note`, so
   `arranger head leadsheet.musicxml --voices alto,tenor` on a chords-only file arranges
   **nothing at all**. That is the decision, and it is the honest reading: `every_note` is
   "the absence of a rhythm restriction", so something else has to supply the positions, and
   here there is no melody to supply them. *Decided against a warning* — naming
   `--grid freddie` was considered and rejected, on the grounds that an empty arrangement is
   the flag's own instruction rather than a hole to report.

   **What "works fine" means for a chords-only file is therefore narrower than it first
   sounds, and the distinction is the whole point of this step.** Today such a file is
   *refused* — `arranger head: error: leadsheet.musicxml has no readable melody part` — and
   that is a hard failure a user cannot act on without reading the source. After this step the
   file **loads, reports its bars and metre, and arranges to the rhythm the grid names**:
   `--grid freddie`, `--grid joe_pass` and the rest all produce a part, measured in §9.1. So
   the chords-only route works; what it does not do is guess a rhythm for itself. The user
   names one, exactly as they already must for any head whose melody does not sit on a beat.

   The cost is recorded because it is real: the most natural command returns an empty
   arrangement with no output and no explanation, and silence is indistinguishable from a bug
   on first run. A clause in `--grid`'s help — *"'every_note' needs a melody"* — would reach
   exactly the user who would be stuck, at no runtime cost. Offered, not assumed.
3. **A soprano-only selection on a chords-only head produces nothing**, for the same reason
   and by the same decision. This is not a special case to be caught — it falls out of
   `every_note`-style deference once "the guitar sings" is separated from "the guitar has
   voices". Today it is the worst outcome of the three: measured, it takes the melody-bearing
   route, tries to voice the sentinel against every chord, and warns sixteen times —
   `melody C4 is not a chord tone of Emaj7 and the 'extension' strategy found no voicing`.

Gate: a committed chords-only fixture, and the six existing fixtures byte-identical.

**Landed.** `Head` carries a `measure_range`, set by `_read_notes` from the measures it
walks, and `bars` reports it — falling back to the note span only for a `Head` built by
hand, which has no file behind it to state a range. `_choose_part` now scores on
`(notes, chords)` through a new `_part_harmony_count`, so a part carrying changes but no
melody is chosen instead of returning `None`: the file that used to raise
`has no readable melody part` now loads. The fixture is committed as
`tests/data/lead_sheet_chords_only.musicxml`, exactly the document §9.5 prints. Measured:
it reports `(1, 5)`, six chords, zero notes, 4/4; the default grid and a soprano-only
selection each arrange **nothing**, while `--grid freddie` places 16 chords, `joe_pass` 16
and `final_and` 4 — §9.1's numbers, now reproducible on the committed tree.

**One measurement this section did not have, and it reshapes the gate.** Making `bars` the
file's extent is not free. Three fixtures — `Trouble_in_Mind_Blues`,
`heres_that_rainy_day`, `i_was_doing_all_right` — have changes that outlast their last note,
so on the **comping route with a named grid** their parts now run to the file's end:
`freddie` 79→87, 103→109, 124→126 and `joe_pass` 83→91, 114→120, 159→161. The other three
fixtures, and **every default arrangement**, are byte-identical. So "the six fixtures
byte-identical" holds for the acceptance criterion §8 actually states — *an arrangement
with no flags passed* — and the comping-route counts are **re-baselined rather than kept**,
because the change *is* the fix: a chord still in force in a trailing bar was being dropped.
`TestChordSlots`'s pinned counts move with it, and
`TestAHeldNoteIsOneNoteAcrossABarline.test_the_held_note_outlasts_the_last_note_and_bars_reports_the_file`
is **inverted** from `(1, 16)` to `(1, 18)` rather than deleted (AGENTS.md trap 5).

**Step C — `--non-chord-tone` reaches the comping route.** Extract the strategy block from
`prepare_step` so the comping generator honours the flag **at harmony level**, with
`melody_pc` still `None`. `--non-chord-tone diminished` under `--voices alto,tenor` then gives
`D5 over Cmaj7 → Bdim7`, and the guide-tone voices play the dim7. The onset guard from §9.2
lives here, and `next_melody` for the diminished strategy's resolution target is the horn's
next note, available from `head_skeleton` even when the current slot has none.

**Landed.** `_resolve_substitute_harmony` is the extracted block, and both `prepare_step`
and the comping branch call it. The comping branch reharmonises at the harmony level with
`melody_pc` still `None`, so a comping shape is held to the substituted chord's full tone
set; `chord` stays the written symbol and `harmonized_as`/`strategy`/`non_chord_tone` report
what was actually stated, exactly as the melody route reports it.

The §9.2 onset guard is a **threaded signal, not a re-derived one**:
`ArrangeOptions.melody_onsets` / `arrange_slots(onsets=...)` /
`arrange_progression(melody_onsets=...)` carry the indexes whose melody articulates,
`headxml.arrange_xml_head` computes them from `melody_state`, and `None` means every slot
is an onset — the honest default for a hand-built progression, which is why a bare
`arrange_progression(..., melody="alto,tenor")` honours the flag too. `_next_resolution_melody`
and the slot layer's `unresolved_steps` / `_next_chord_tone_melody` take the same set, so
`--fallback diminished` fires at onsets only.

Measured on the committed fixtures: on the comping route `--non-chord-tone legacy` is
byte-identical to the pre-step tree, while every fixture changes under the default
`extension`; every **default (no-flags) arrangement is byte-identical**, which is §7's
acceptance criterion. `TestCompingMelodyIndependence` (step 0) is **re-scoped rather than
deleted** (AGENTS.md trap 5): its placement invariant survives under `legacy`, and the
melody's new reach into the *harmony* is asserted separately. The strategy is on by default
because `--non-chord-tone` already defaults to `extension`; a user who wants the written
chord stated as-is passes `legacy`.

**`--fallback diminished` is the same concern, and comes with it.** It is a *harmony-only*
change: the retry replaces the written chord in the triple (`working[index] = (note,
resolved[0], resolved[1])`) and the melody note is untouched. That is why it belongs with
step C rather than needing machinery of its own — it answers the same question, at the same
level, one step later. Leaving it on the melody route only would mean `--non-chord-tone` means
one thing on this route and the flag that rescues it means another.

**What it is not is a harmony-*only-slot* concern, and that distinction is the load-bearing
one.** The retry is driven by `unresolved_steps`, which asks whether a *melody note* is a
chord tone that no strategy could resolve — so it needs a melody note to fire at all. On a
harmony-only slot there is nothing to rescue: the chord is whatever the symbol says, it gets
voiced, and no failure occurs. The rule is therefore the same §9.2 rule rather than a
separate one: `--fallback` fires **at an onset**, where a melody note articulates and can be
unresolvable, and not under a held note or a silent position.

Its `next_melody` argument makes the dependency explicit. `_next_chord_tone_melody` scans
forward for the next note that is a chord tone of its own chord, because *"a substituted chord
is easier to sing and easier to voice when there is a following note the ear can move to"* —
so the rescue is a claim about the tune's motion, not about the chord in isolation. On the
comping route that scan still has an answer: the horn's next note is in `head_skeleton` even
when the current slot has none. A chords-only head has no notes to scan, so `--fallback` never
fires there, which is correct rather than a gap.

No new flag. `--non-chord-tone` already states the user's intent about non-chord tones, and a
second flag meaning "also do something about non-chord tones" would split one intent across
two — the shape `harmony=` was built to avoid. The tension worth naming: this is the first
step in which the melody affects the comping output at all. It is opt-in, already flagged,
and confined to the harmony — the placement invariant of step 0 still holds — but a
guitarist reading `Cmaj7 → Bdim7` with no melody on their part needs a diagnostic saying why.

**Step D — the soprano is per slot, not per route.** `voices_have_soprano` decided the
branch for every slot at once. Separate "how the harmony is built" (from the grid) from
"does the guitar sing" (from the voices): a grid position with no note sounding and a named
soprano takes the chord's voices at the requested arity, with no top note. **One new case** —
the other three cells of the table are today's behaviour — and it is what makes
`grid=joe_pass --voices soprano,alto,tenor,bass` place chords on the offbeats.

**Landed.** The route is now the per-slot predicate `sings_here`, and the grid union is gated
on `melody_only_selection` rather than on the soprano, so a soprano-named selection receives
the grid positions it does not sing. Four things the implementation settled that this text
did not say, each measured on `but_not_for_me`:

- **"No note sounding" means "no melody *onset*, and it is read from §9.2's signal rather
  than re-derived.** A `chord_slots` position under a *held* note carries that note in force
  (`melody_at`), not `None`, so the deciding split is `melody_onsets` — the same set step C's
  reharmonise guard reads. A position the tune merely *sustains* through is therefore not an
  onset, and the guitar comps it too. Measured: `grid=joe_pass --voices
  soprano,alto,tenor,bass` gives **105** steps — 80 written onsets singing and **25** comps
  (0 silent, 25 held); `grid=freddie` gives **102** — 80 singing and **22** comps (8 held, 14
  silent). `None` for `melody_onsets` still means "every slot is an onset", so a bare
  `arrange_progression` is unchanged.
- **The comping arity is the voices that will actually *sound*, so a silent soprano is not
  one of them.** `soprano,alto,tenor,bass` states a **three-note shell** on the offbeats, not
  a four-voice shape with a redundant root — the four-note comping shape is §9.4 and needs
  new string sets, deliberately not this step. On the comping route (no soprano) the arity is
  `len(voices)` exactly as before, so nothing there moved.
- **A *melody-only* selection is the one case that is not merged.** `soprano` and
  `soprano,bass` play the tune and nothing else, so a grid position with no tune has nothing
  for them to play; they are left unmerged and unchanged. This is why the union is gated on
  `melody_only_selection` and not on `voices_have_soprano`.
- **The default is still inert.** `every_note` names no positions of its own, so
  `_merge_chord_slots` returns the slots untouched and every no-flags arrangement on all
  seven fixtures is byte-identical — the acceptance criterion of §7, and the property that
  makes the change safe to ship.

The one behaviour change beyond the axis itself is at the library surface: a hand-built
`None` melody under a *singing* selection used to be refused with a warning and a skipped
slot, and is now **comped** — the note-less slot the grid union produces on that route is a
real case now, and dropping the bar is worse than stating its chord. `TestSilentSlotsCarry
NoMelody`'s assertion was inverted rather than deleted (AGENTS.md trap 5).

**Step E — `--voices soprano` = the melody alone. Landed, and ahead of the others.**

The plan made this the last step, on the assumption that soprano alone still arranged like
`auto`: `notes=len(voices)` is passed *only* when `melody_voiced` is False, and the
melody-bearing route has no arity concept, so the soprano's only remaining job was to switch
the engine onto that route. **Stage 2 (`docs/one-fact.md`) closed it first**, by keying "the
tune and nothing else" on the voice selection — `melody_only_selection` in `textures.py` —
rather than on a texture. That also deleted the `melody` and `melody_bass` textures the plan
referred to, so the "measure `texture=melody`" step no longer exists to run.

Measured on `tests/data/but_not_for_me.mxl`, all 80 steps: `--voices soprano` gives **one
note per step** — the written melody, no left hand under it — while `--voices auto` (all four
voices) still gives **four**. They are no longer the same arrangement, which is the whole of
this step.

**Landed as Stage 2 and released with the one-fact collapse** (`docs/one-fact.md`), not with
the later §9 steps. The plan had bundled this with two other breaking changes — `melody`
becoming `Optional[str]` (step B) and the loader accepting a chords-only file (step A') —
under "the next minor release"; the soprano change shipped earlier, and B and A' followed it
on `comping` with no release of their own. The number is deliberately not written here:
`tests/test_docs.py` asserts that every version a document states equals
`arranger.__version__`, so a plan cannot name the version it will ship as until it ships.

### 9.4 A four-note comping chord, and the inversion that would allow one

**There is no way to ask for this today, and the reason is an assumption that does not
always hold.** Measured on `Dm7`:

```
get_comping_voicings(notes=1) -> 4 candidates
get_comping_voicings(notes=2) -> 4 candidates
get_comping_voicings(notes=3) -> 6 candidates
get_comping_voicings(notes=4) -> 0 candidates          <- nothing at all

voices=alto,tenor,bass          notes/step=[3]  melody_is_top=0/3
voices=soprano,alto,tenor,bass  notes/step=[4]  melody_is_top=3/3
voices=alto,tenor              notes/step=[2]  melody_is_top=0/3
```

**Four notes is reachable only by naming soprano, and naming soprano always pins the melody
to the top** — `melody_is_top=3/3` in every case. The arity and the pin are welded together,
because arity is `len(voices)` and soprano is the bit that selects the melody route.

`get_comping_voicings` refuses arity 4 deliberately: *"with no melody to support, a fourth
voice would be the root or the 5th — the two notes that carry no information about the chord's
quality"*, and every `shell` string set is three strings. **But that reasoning holds only
while the melody cannot supply the fourth voice.** When the melody note *is* a chord tone —
which it often is — a fourth voice can be **the melody itself, placed anywhere in the shape
rather than on top of it**. That note carries information; the root does not. It is also
exactly what a comping player does under a horn.

**The inversion: the degree family should own the arity, not the voice count.** Measured,
`harmony_allowed` *already derives* an arity from the degree family and refuses
incompatible selections:

| family | declared arity | behaviour |
|---|---|---|
| `root` | 1 | refuses anything but `voices=bass`, naming the required count |
| `shell_root` | 3 | refuses a two-voice selection, naming the required count |
| `guide` | 2 | always allowed |
| **`full`** | **none** | **never refused, and silently capped by `len(voices)`** |

`full` is the odd one out. Its docstring says *"the chord in full: every tone the quality
defines"* — four for a 7th chord, three for a triad — and that is precisely why it declares no
fixed count: **its arity comes from the quality, not from a constant.** It is then quietly
limited to whatever the selection happens to ask for, so `voices=alto,tenor,bass
--harmony=full` sounds three of Dm7's four tones while claiming to sound the chord in full.

So the design is not a new `harmony=` value. It is the other way round:

- **`harmony=` owns how many notes sound**, because a degree family is a claim about degrees
  and a 7th chord's full tone set is four notes. Three of the four families already enforce
  this; `full` is the one that has not been given the rule.
- **`voices=` owns whether the tune is among them, and where** — soprano on top (chord-melody),
  or present in the shape but not pinned (comping).

That inverts the current wiring, where `notes=len(voices)` is computed in `arrange_progression`
and passed down, and the degree family is squeezed into whatever room is left. It also means
the "melody available in any voice" claim lands where it belongs: not as a fifth
`HARMONY_*` value, but as a distinction between *the tune is the top voice* and *the tune is
one of the voices* — a `voices` question, because it is a question about who is playing.

**Two pieces of real work sit behind it, and neither is a policy change.** Every `shell`
string set is three strings, so a four-note comping shape needs new string sets in `grips.py`
— this is the substantive part. And `get_comping_voicings` takes no melody argument at all
today, which is what has kept it melody-free; permitting the melody note as a *candidate
degree* is a deliberate loosening of exactly the invariant step 0 pins, and it needs to be
opt-in rather than a consequence of asking for four notes.

**Not built, and not yet a step.** It is recorded here because it is the sharpest thing this
discussion found, and because it reorders the plan if it is adopted. The plan once called it a
**prerequisite for step E** — `--voices soprano` meaning "the melody alone" could not be stated
while soprano also silently meant "four notes, melody pinned on top". **That constraint has
since gone**: Stage 2 made soprano alone the melody and nothing else (step E, above), so §9.4
now stands on its own rather than gating anything. It is the one item in this section still a
proposal.

### 9.5 Reproducing §9, and the fixture it needs

**Every number in this section came from the commands below, and none of them will survive a
fresh checkout on their own** — in particular the chords-only lead sheet exists only as
`/tmp/leadsheet.musicxml`, which is not in the tree. Step A' needs it committed, and the
content is here so it can be written rather than reconstructed.

`tests/support.py` already has `write_score`, which is the helper the committed MusicXML
fixtures are built with; this one is written out longhand because its point is that it
contains **no pitched notes at all**.

```python
DIV = 4   # divisions per quarter, so one beat is 4

def bar(i, changes):
    out = [f'  <measure number="{i}">']
    for root, kind in changes:
        out.append('    <harmony print-frame="no">'
                   f'<root><root-step>{root}</root-step></root>'
                   f'<kind text="">{kind}</kind></harmony>')
        # A rest, not a pitched note: _choose_part counts pitches, and this is the
        # whole reason the file is refused today.
        out.append(f'    <note><rest/><duration>{DIV}</duration><voice>1</voice></note>')
    out.append('  </measure>')
    return "\n".join(out)

BARS = [bar(1, [('D', 'minor-seventh'), ('G', 'dominant')]),
        bar(2, [('C', 'major-seventh')]),
        bar(3, [('F', 'major-seventh'), ('B', 'dominant')]),
        bar(4, [('E', 'major-seventh')])]

XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<score-partwise version="3.1">'
       '<part-list><score-part id="P1">'
       '<part-name>Lead Sheet</part-name></score-part></part-list>\n'
       '<part id="P1">\n' + "\n".join(BARS) + '\n</part></score-partwise>')
```

Four bars, six `<harmony>` elements, **zero pitched notes**. The timeline spans bars 1–4,
which is what made it a useful probe: `Head.bars` returned `(1, 1)` for it, and the loader
refused it outright. It is now committed as
`tests/data/lead_sheet_chords_only.musicxml` (§9.3 step A'), where it loads and reports
`(1, 5)`.

**The refusal, and the two dependencies behind it — fixed by step A':**

```bash
python -m arranger head tests/data/lead_sheet_chords_only.musicxml --voices alto,tenor --grid freddie
# 4/4, C major, 0 melody note(s), bars 1-4   -- a part, once a grid names the rhythm
python -m arranger head tests/data/lead_sheet_chords_only.musicxml --voices alto,tenor
# nothing: every_note defers to a melody that is not there
```

**The melody-independence measurement** (step 0's test, in miniature) — every melody pitch in
a real fixture replaced with a high non-chord tone, keeping chords, bars, beats and durations:

```bash
python - <<'PY'
import copy, hashlib
from headxml import load_musicxml, head_skeleton, _merge_chord_slots
from arranger.slots import arrange_slots
from arranger.textures import parse_voices, resolve_voices, voices_have_soprano
from arranger import Diagnostics

def run(head, vox, grid):
    slots = head_skeleton(head, None)
    if not voices_have_soprano(resolve_voices(parse_voices(vox), 'uniform', Diagnostics())):
        slots = _merge_chord_slots(slots, head, None, grid) or slots
    steps, _, _ = arrange_slots(
        [s[0] for s in slots], [(s[1], s[2], s[3]) for s in slots],
        melody=vox, grid=grid, beats_per_bar=head.beats_per_bar)
    return tuple((s.bar, s.beat, s.chord, tuple(s.voicing.frets)) for s in steps)

for vox in ('alto,tenor', 'bass', 'tenor', 'alto', 'alto,tenor,bass'):
    h = load_musicxml('tests/data/but_not_for_me.mxl')
    before = run(h, vox, 'freddie')
    h2 = copy.deepcopy(h)
    for i, n in enumerate(h2.notes):
        n.pitch = 81 + (i * 3) % 14        # F#5-F6, mostly outside every chord
    h2.notes.sort(key=lambda n: (n.bar, n.beat))
    print(vox, 'identical:', run(h2, vox, 'freddie') == before)
PY
# every voice: identical: True
```

`HeadNote.note_name` is a property derived from `pitch`, so assigning `pitch` alone is enough
— assigning `note_name` raises.

**The three-state split** (§9.2), which is the measurement step B exists to make expressible:

```bash
python - <<'PY'
import glob, os
from headxml import load_musicxml, chord_slots, melody_at

def state(head, bar, beat):
    if melody_at(head.notes, bar, beat) is None:
        return 'silent'
    onset = [n for n in head.notes if n.bar == bar and abs(n.beat - beat) < 1e-9]
    return 'onset' if onset else 'held'

for path in sorted(glob.glob('tests/data/*.mxl') + glob.glob('tests/data/*.musicxml')):
    head = load_musicxml(path)
    counts = {'onset': 0, 'held': 0, 'silent': 0}
    for grid in ('freddie', 'every_note'):
        for slot in chord_slots(head, grid=grid):
            counts[state(head, slot[3], slot[4])] += 1
    print(os.path.basename(path), counts)
PY
```

**The four-note gap** (§9.4):

```bash
python -c "
from arranger.grips import get_comping_voicings
for n in (1, 2, 3, 4):
    print(n, len(get_comping_voicings('m7', 'Dm7', notes=n)), 'candidates')"
# 4 -> 0 candidates
```

### 9.6 What is deliberately not in this plan

**A melody-less lead sheet is in scope for *loading*, and not for guessing.** It was
measured and refused — `_choose_part` filters on `_part_note_count(p) > 0` — and step A'
makes it load and arrange to a named grid. What it does not do is supply a rhythm the user
did not ask for: with the default grid it is empty, because `every_note` has nothing to defer
to. That is the decision, and the distinction between *the file is accepted* and *the file
guesses* is the one worth keeping from this step.

**`texture` is not proposed for removal.** Its overlap with `grid` is real — `targets` already
means "full on strong beats, thin between", and a grid position carrying a content hint
(`freddie: beat 1 full, offbeat guide tones`) is a coherent next idea. Two things stop it being
a merge. **One of the two things that used to stop it moved off the axis entirely:**
the `melody` and `melody_bass` textures — **empty grip tuples on both roles**,
"harmonise nothing, ever" — were not a rhythm, and Stage 2 keyed that fact on the voice
selection (`docs/one-fact.md`), so nothing of it sits on the texture axis any more.
What still stops the merge is that `metric_roles` decides targets by
harmonic and melodic *change*, not only position: a slot is a target only when it is metrically
strong **and** something new happens there, because a passing slot is exactly where the
non-chord-tone strategies would rewrite the harmony. `grid_positions` returns positions and
has no access to the timeline, so a pattern that carried content would have to stop being a
rhythm table. If a grid gains a content hint it defers to the texture; it does not replace it.

**Step A is not a default change.** `every_note` stays the default — `GRID_AUTO` is withdrawn
entirely (step A), and repointing the default at a real pattern is the comping-first question,
which belongs after step D, when `grid` means the same thing on both routes.

**Stab duration is not in this plan.** It is a real gap rather than a deferral: nothing
currently says how long a comp lasts, and the natural answer — that the grid owns the rhythm,
so a stab sounds until the next grid position — is not implemented anywhere. `chord_slots`
computes a `length` from the following position and `head_skeleton` from the melody note, but
no axis decides which of the two a *comping* step obeys. It was not `hold=`, which is
withdrawn, and it belongs with §6 Q6 rather than here: a free-form grid spelling would have to
say it as well, so designing one without settling it would mean designing the grammar twice.
This is the fifth kind `open-issues.md` item 10 predicts for `melody_alone_case`: an invented
slot has no melody note to be alone *with*, so it cannot be reached by the existing four.