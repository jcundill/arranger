# Comping styles: a design proposal

**Status: partly built.** Stage C of [§8](#8-staged-approach) has landed the *harmony*
axis (`harmony=full|guide|shell_root|root`), so `shell_root` exists and the degree-family
table in §4.1 is no longer a proposal in its entirety. The rhythm grid (§4.2) is still
**not** built, §6 still holds open questions, and `--voices` is still `--voices`. This
records a design and the measurements that forced it, so the decision can be reviewed
rather than re-derived. It follows
[reharmonisation-proposals.md](reharmonisation-proposals.md), which is the precedent: a
proposal that says what was measured, what is proposed and what is deliberately
not built.

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

1. **`--voices soprano` is a no-op.** It is byte-identical to `--voices auto`, because the
   soprano's only remaining job is to switch the engine onto the melody-bearing route:
   `melody_voiced = voices_have_soprano(voices)` in `steps.py`.
2. **The flags can contradict, so one must be refused.** `melody_allowed` refuses
   `--texture melody --voices alto` with a warning, because `melody` *already* means
   "nothing but the tune". **That refusal is the seam showing.**
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
| `melody` | — | — | none | yes |
| `melody_bass` | — | — | none | yes + thumb |

**`walking_bass` is a comping style that also keeps the melody on top**, and the table says
so directly: its only target grip is `shell`, with no melody-bearing grip involved. Yet
measured, **80/80 steps** carry the written melody as the highest sounding note, with
`melody_voiced=True`.

| texture | notes/step | melody is the top note (`auto`) | (`alto,tenor`) |
|---|---|---|---|
| `uniform` | 4 | 80/80 | 11/80 |
| `targets` | 4 | 80/80 | 11/80 |
| `walking_bass` | 2, 3, 4 | 80/80 | 11/80 |
| `melody` | 1 | 80/80 | refused |
| `melody_bass` | 2 | 80/80 | refused |

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
freddie     [(1,0), (2,0), (3,0), (4,0)]              # every quarter note
charleston  [(1,0), (2,SUB)] or [(1,SUB), (3,0)]      # 1 + and-of-2, or and-of-1 + 3
joe_pass    comp stabs on the ANDs; thumb on 1,2,3,4
and_of_4    [(4,SUB)]                                  # harmony on the and-of-4
```

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

#### The metre trap

A count without a denominator is not a metre (AGENTS.md trap 9). A beat grid **must** be
metric-aware or it will invent beats that do not exist:

| metre | `freddie` (every quarter) | does and-of-4 exist? |
|---|---|---|
| 4/4 | beats 1, 2, 3, 4 | yes |
| 2/2 | beats 1, 2 | **no** |
| 3/4 | beats 1, 2, 3 | **no** |

`But Not For Me` is **2/2**, so `freddie` on this head is **two** notes per bar, not four.
This is the same trap `TARGET_BEATS` already documents ("in 2/2 (two notated beats) beat 3
does not exist and only the downbeat is a target").

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

**Recommendation: (2), as Stage C of [§8](#8-staged-approach).** This reverses an earlier
recommendation, and it reverses because a constraint has been withdrawn: option (1) was
picked because it "breaks nothing", and the project is pre-1.0 (`0.9.0`, no CHANGELOG, no
deprecation policy, no stability classifier) with **compatibility of shipped flags
explicitly not a constraint**. Re-documenting a flag that is about to be replaced is work
done twice.

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

1. **How does a placement grid sit on `--skeleton`'s lattice?** These are different
   things and they do not collide, which took a measurement to establish.
   `--skeleton` is a **resolution**: `_slot_key` derives `(bar, beat, subdivision)` from a
   *uniform* quantisation — `beats` forces subdivision 0, `eighths` pairs tatums,
   `sixteenths` takes every tatum — so it answers "how finely do I read the melody?", and
   it exists because a raw head runs to 10.7 notes per bar. The §4.2 grid is a
   **placement**: a selected subset of positions, which no strategy above can express. So
   a grid selects points *from* the lattice `--skeleton` produced, and two consequences
   follow: a style naming and-of-4 needs a lattice fine enough to contain one (`eighths` at
   minimum), and in 2/2 there is no and-of-4 at all. Both are design inputs to Stage D
   rather than open questions about ownership.
2. **Does `harmony=guide` with `sings=yes` reach the melody through the shell grip or
   through `get_comping_voicings`?** (§4.1) The degrees are the same either way, so this
   is decided entirely by machinery, and the two answers are not equivalent: the shell grip
   pins the melody to the soprano string, the comping generator never sees it. Measured
   today, `--grips shell` gives 3 notes with the melody on top in 4/4 steps and
   `melody=none` gives the same 2 guide tones without it. **Stage C cannot pick a name for
   the axis until this is settled**, because the two routes would answer to one setting
   with different voicings.
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
   main tension in the whole proposal.
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

`AGENTS.md`'s stated counts moved with it: **939 tests OK (skipped=2)**, and
`tests/test_docs.py` is 12 of those. The old line also said "11 of those 926" while the
line above it said 938, so it was already internally inconsistent.

### Stage C — Rename and consolidate the axis — **partly done**

**Landed: the `harmony=` axis and the `shell_root` family.** `HARMONY_STYLES`,
`HARMONY_POLICIES`, `HARMONY_AUTO` and `harmony_allowed` are in `textures.py`;
`get_comping_voicings` and `_shell_voicing` take `shell_root`; the keyword threads
through `arrange_progression`, `ArrangeOptions`, `arrange_slots`, `_corpus_options` and
both CLIs. Inert twice over — `auto` resolves to the shipped `guide`, and the axis is read
only by the comping route — and all six published arrangements are byte-identical.

**Not done: the rename.** `--voices` is still `--voices`, and `melody=` still carries a
voice list. Both were left deliberately: the rename is only worth making once the flag it
renames *means* something, and §6 Q2 (whether `harmony=guide` + `sings=yes` reaches the
melody through the shell grip or the comping generator) is still open. The vocabulary
exists and the awkward name is now the only thing wrong, which is a better state to leave
it in than either half of a rename.

**`MELODY_STYLES` — the table that does not exist.** `options.py` cited it in a comment;
the real one is `MELODY_POLICIES`, keyed `auto` / `none`. **Fixed**: the comment now names
the table that exists.

### Stage D — The rhythm grid (not started)

With flag compatibility off the table this is one coherent change rather than a
migration, and it is the natural moment for it because the vocabulary is still small.

Order *within* the stage: `full` and `guide` first — both already reachable, being what
`walking_bass` and `--voices bass` do today — then `shell_root`, the one case §4.1
measured at 11/11 on the **existing** `(5,4,3)` sets, so still no new grip families.

**One question has to be answered before the name is chosen, not after: §6 Q2.** Whether
`harmony=guide` with `sings=yes` reaches the melody through the shell grip or through
`get_comping_voicings` decides what the setting *means*, and the two are not equivalent —
the shell grip pins the melody to the soprano string, the comping generator never sees
it. Naming the axis before answering it is how `--grips shell` ends up silently redundant
or silently different (§4.1).

Acceptance: `walking_bass` output byte-identical; `MELODY_STYLES` cited nowhere; the
`melody=` keyword that carries a voice list is gone or renamed to say what it carries; and
`--grips shell` either still works as written or is *deliberately* re-expressed as
`harmony=guide` + `sings=yes`, with the difference recorded rather than discovered.

The largest genuinely new work, and the only stage that adds a concept rather than
renaming one. `joe_pass` and `charleston` are the payoff.

Two things must be settled **inside** this stage, not discovered by it:

- **The lattice relationship** (§6 Q1). The grid selects positions from `--skeleton`'s
  output, so it needs a lattice fine enough to hold the positions it names.
- **`--non-chord-tone`'s existing inertness** on the comping route (§2 oddity 4). The
  grid puts stabs on weak beats, which is exactly where the strategies are already a
  no-op — so "does a stab get the tension treatment?" needs an answer before the first
  stab is placed, not after.

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
| `--skeleton` | changes (`chords`, `beats`; the rest collapse to one) | changes |
| `--grips` | changes — see §2 oddity 3 | changes |
| `--non-chord-tone` | **inert** | changes |
| `--fallback` | changes | changes |
| `--fret-min` / `--fret-max` | changes | — |
| `--bass none` | inert (already the default) | — |
| `--pick longest` | inert | — |
| `--bars`, `--part` | input scope | input scope |
| `--tab`, `--melody`, `--mutes`, `--bars-per-line` | render only | render only |
| `--html`, `--musicxml`, `--gp5` | output format | output format |

Only `--non-chord-tone` goes inert on the comping route for a reason a user could act on.
`--bass none` and `--pick longest` are inert because they name the default, not because
of the route. Everything else is either live and orthogonal, or already spoken for by a
stage above.
