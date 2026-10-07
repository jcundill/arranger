# One fact, one home — the Stage-2 collapse plan

**Status: landed.** Commits 1–3 are on `comping` — `d3fb13a` (`step.grip`), `1f0ed54`
(`step.bass`), `12fd804` (the melody-only signal) — each gated on a green `make check`;
this document's own update is commit 4, and the version bump is commit 5. The body below
is the plan as written before implementation; §5 records where the landing differed, and
that is the only part that supersedes it.

It was committed before implementation because the Stage-1 plan lived only in a
conversation and had to be reconstructed from the tree — a plan that exists only in a
conversation is not a plan the next session can read, which is AGENTS.md trap 1 ("a
gate that enumerates its inputs by hand silently skips whatever was added last")
applied to planning itself: the plan was never on disk, so no check could look at it.

Measured state after commit 3: **866 tests OK (skipped=2)**, pyright 0 errors
0 warnings, ruff clean, on `comping` at `12fd804`. At plan time it was **860**, on
`comping` at `11f68eb`.

## 1. What Stage 1 landed, and the class of bug it exposed

Stage 1 was three QA fixes off the checklist in [docs/voices-axis.md §4](voices-axis.md),
each gated on a green `make check`:

- `4fdde0d` — the `--bass` plumbing: the `ArrangeOptions.bass` field defaulted to the
  resolved `"none"` while `arrange_progression`'s keyword defaulted to the `BASS_AUTO`
  sentinel, so the two spellings of one request could never be compared, and the flag was
  silently inert on `arranger head`.
- `ee2c7f1` — `tabstaff._carries_melody` derived "this string carries the melody" from the
  voicing shape instead of reading `step.melody_voiced`.
- `d76478a` — the NC step left `step.grip` at its `"drop2"` default while `voicing.grip`
  said `"melody"`: one fact, two disagreeing fields.
- `11f68eb` — AGENTS.md's measured state moved to the new counts.

Each fix is a symptom of one shape: **one fact stated twice, in two places that can
disagree.** Stage 2 removes the class rather than the next symptom.

## 2. The five commits

### Commit 1 — `step.grip` becomes a derived view of `voicing.grip`

`Voicing.grip` survives: every generator sets it at construction and `voicing_cost` reads
it. `ArrangementStep.grip` stops being a stored field and becomes a read-only `@property`
returning `self.voicing.grip`. Every reader's spelling stays — `render.py`'s annotations,
the test assertions, and the `__getitem__` shim, which sees properties through `hasattr` —
and the two fields *cannot* disagree any more, which is the point.

The mirror writes in `steps.py` delete (`grip="rest"` on the rest step,
`grip=solo_voicing.grip` on the NC step, `grip="melody"` on the melody-alone branches,
`grip=best_voicing.grip` on the harmonised step): each voicing already carries the value,
which is what the Stage-1 NC fix proved for one of them.

New test: assigning `step.grip` raises `AttributeError` — the single-source proof.
Stage 1's `test_nc_step_grip_mirrors_the_voicing` is **kept**, not deleted (trap 5): it
now asserts the collapse itself. Behaviour-neutral by construction; `make demo` must come
back byte-identical.

### Commit 2 — `step.bass` becomes a derived view of `voicing.bass_midi`

Same shape. `Voicing.bass_midi` survives — it is written in `_attach_bass` *together with*
`bass_string` and the fret merge, and it is what the renderers' hold-comparisons read —
and `ArrangementStep.bass` becomes a `@property` returning it. The `step.bass = midi`
line deletes; `render.py`'s bass annotation, `bass._previous_bass`, `_attach_bass`'s own
already-set guard and the walking-bass tests read on unchanged.

New tests: read-only, and `step.bass` **follows** a late `_attach_bass` merge — a stored
copy taken at construction would have missed the post-selection write, which is the bug
class being deleted.

**Measured blast radius for both commits: zero.** No constructor call site passes `grip=`
or `bass=` to an `ArrangementStep` — every grep hit is a `Voicing(...)` construction or
an arrange-function policy kwarg — so nothing outside `steps.py` changes.

### Commit 3 — the melody-only signal moves from `texture=` to `voices=`

The intention, settled with the user and recorded here: **`--voices soprano` is the signal
that the guitar plays the melody and nothing else** — not any `--texture` spelling. Today
that fact lives on the texture axis, `MELODY_ONLY_TEXTURES = ("melody", "melody_bass")` in
`arranger/textures.py`, which is the alias being collapsed.

- A new **derived** predicate beside `voices_have_soprano`: a melody-only selection is
  *soprano present, alto and tenor absent* — `(soprano,)` or `(soprano, bass)`. Derived,
  never listed, per the rule the `harmony=` axis followed.
- The route: a melody-only selection routes every singing-route slot through
  `get_melody_only_voicing` (today's `MELODY_ALONE_TEXTURE` path) whatever `texture=`
  says, so `texture=` is inert on that selection — the `harmony=` precedent ("inert twice
  over"), and silent for the same reason.
- The predicate is fed to the existing machinery **through the one channel it already
  reads, the empty palette**, rather than as a new input to `decisions.melody_alone_case`
  (§5 notes the plan as written said "fed in as an input"; landing it that way would have
  made a *second* channel for the same declaration, which is the class of bug this stage
  removes). The loop hands a melody-only selection `slot_grips = ()` without consulting
  `resolve_texture_grips`, so `texture=` and `grips=` are inert and silent there, and the
  guard ordering the plan worried about (trap 12) is untouched by construction — asserted
  anyway, with new tests for the `NC` and off-grid cases under `voices=soprano`.
- The thumb: `BASS_AUTO` resolves to walk when `texture == "walking_bass"` **or** the
  selection is melody-only with the bass voice named. `--voices soprano,bass` is today's
  `texture="melody_bass"`; `--voices soprano` alone is today's `texture="melody"` (no
  thumb). **Not** for a lone `voices=bass` comping selection: no soprano means not
  melody-only, and a thumb under a part that already is the bass line would double it
  (§8a preserved). `bass_allowed`'s capacity answer for a melody-only selection: the
  single-fret upper shape leaves every bass string free — the same capacity fix
  `docs/open-issues.md` item 10 made for the comping route.
- Deleted: `"melody"` and `"melody_bass"` from `TEXTURE_STYLES` and `TEXTURE_GRIPS`;
  `MELODY_ONLY_TEXTURES`; `melody_bass` from `THUMB_TEXTURES`; the `melody_allowed`
  no-soprano refusal (it dissolves — with melody-only keyed on the selection, a
  soprano-less selection is no longer self-contradictory anywhere; it just comps); the
  `melody_only_texture=` parameter on `should_promote_fill` (re-keyed); the stale exports.
  An unknown-texture error is the precedent the corpus removal set for removed flags.
- Tests: the ~dozen tests pinning the two textures across `tests/test_texture.py`,
  `tests/test_comping.py`, `tests/test_walking_bass.py`, `tests/test_cli.py` and
  `tests/test_grip_chart.py` are rewritten as voices-selection tests (trap 5: invert or
  re-spell, never just delete). New equivalence tests assert `voices=(soprano,)` matches
  the old `texture="melody"` output and `voices=(soprano, bass)` the old `"melody_bass"`,
  against a capture taken **fresh from HEAD before the change** (trap 8) with a throwaway
  script under `/tmp` that does not outlive the refactor.

### Commit 4 — docs

`docs/engine.md` (the texture section), `docs/comping-styles.md` §6 Q4/Q7 (a step toward
"`--texture` may reduce to the rhythm grid plus a role policy"), `docs/voices-axis.md`
§2/§3/§7 (note 6's "a selection with the soprano still in it does not change the shape" is
false for soprano-only after this and must be re-stated for `soprano,alto`), `README.md`
examples, and this document's status line. AGENTS.md's measured state moves with the
counts, per the house rule.

### Commit 5 — the version bump

A minor bump, its own commit, as the corpus removal's was: the public surface moves (two
fields become read-only properties, two textures are removed, `voices=(soprano,)` gains
meaning).

## 3. Settled decisions

| question | ruling |
|---|---|
| duplicate field: delete the name, or derive it? | **derive** — a read-only `@property` keeps every reader's spelling while making drift impossible; deleting the names would break the public surface harder than pre-1.0 needs |
| `texture="melody_bass"`'s new spelling | **`--voices soprano,bass`** — the bass voice named in the selection; `bass=auto` resolves to walk when the bass voice is named in a melody-only selection |
| are the old textures kept as warning aliases? | **no** — deleted outright; pre-1.0, "compatibility of shipped flags explicitly not a constraint" (`docs/comping-styles.md` §6 Q2), and a deprecation shim is work done twice |
| `texture=` under a soprano-only selection | **silently inert** — the selection means "the left hand plays nothing", which every texture would contradict; the same silence as `harmony=` on the singing route |
| `--voices soprano,alto` | **still arranges like `auto`** (the full chord-melody) — real voice allocation is `docs/comping-styles.md` §6 Q2 option 3, deliberately out of scope |

## 4. Traps the implementer must respect

- **Trap 12** (`melody_alone_case`'s guard ordering is load-bearing): before extending its
  inputs, ask what each existing guard is load-bearing *for*, and test both routes — an
  `NC` bar and an off-grid slot under `voices=soprano` are the two new cases that prove
  the ordering survived.
- **Trap 8** (a stale "before" invents differences): the commit-3 equivalence capture is
  taken from HEAD in a clean tree, not from the working tree mid-change, and the script
  stays under `/tmp`.
- **Trap 5** (a test's premise invalidated by the refactor it protects): invert or
  re-spell the pinned tests; `test_nc_step_grip_mirrors_the_voicing` stays.
- **Trap 7** (a mechanical move must copy text, not retype it): the deleted mirror writes
  are read twice against the diff before the commit.
- **Trap 1** is why this document exists at all, and why it is registered in
  `tests/test_docs.py` and linked from AGENTS.md in the same commit that creates it.

## 5. Build notes — what the plan's own enumeration missed

Three sites the plan's survey did not name, each caught by a gate rather than by a
re-read, and each a lesson about which gate:

- **A seventh `grip=` mirror** on the comping route's own step construction
  (`steps.py`, the `select_step_voicing(...) or candidates[0]` site), which the
  plan's grep had mis-classified as a `Voicing` construction. **pyright caught it** —
  "No parameter named `grip`" — which is what a static check is for: the failure is
  about a *name*, not a behaviour, so no test run would have described it faster.
- **`headxml.py`'s own `resolve_voices` call**, which the plan never listed because
  its caller survey grepped the engine and the tests but not the importer. The
  trap-8 equivalence capture caught it — `arranger head` raised `TypeError` before
  the gate ever reached the rewritten tests, which is why the capture is run end to
  end through the CLI and not only through the library.
- **`_roles_for_slot`'s `uniform` catch-all sat above the thumb-line strong-beat
  rule.** The old `melody_bass` was never `uniform`, so the ordering never mattered
  until the melody-only selection arrived under the *default* texture — and the
  capture showed `soprano,bass` re-striking the melody on every walk-invented beat
  instead of holding it. The fix lets a melody-only selection with a thumb reach the
  rule (`texture == "uniform" and not (has_thumb and melody_only)`), and the first
  draft of it **dropped the `weight < 0` half of the guard** — "we were never told
  where this note falls" — which no equivalence capture on a *timed* fixture would
  have caught. Caught by re-reading the diff against the original, which is trap 7's
  rule and the reason it applies to a two-line change as much as to a 4000-line one.

The equivalence itself, measured per trap 8 from a clean tree at `1f0ed54`:
`--voices soprano` is byte-identical to the old `--texture melody`, and
`--voices soprano,bass` to the old `--texture melody_bass`, on both committed heads
(`but_not_for_me.mxl` and `heres_that_rainy_day.musicxml`, bars 1-8) and on the
engine fixture with an `NC` bar. The capture scripts stayed under `/tmp` and did not
outlive the commit, by design.
