# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

`jazz-arranger` turns a chord progression into playable **jazz guitar chord-melody**.
Given `(melody note, chord quality, chord name)` triples it generates voicings in
several grip families, pins the melody to the soprano string, and chooses among the
candidates with one position-aware cost function. It can also read a written head out
of a MusicXML file and arrange that.

Runtime dependency: `musthe`, and nothing else. Everything else is optional.

## Read this first: where to look

The reasoning behind a subsystem lives in its own document. This file is the map, the
gate and the conventions — not the explanation.

| If you are changing | Read first | Then |
|---|---|---|
| the drop-2 rule, a grip, `GRIP_MAX_SPAN`, `voicing_cost` | [docs/engine.md](docs/engine.md) | `arranger/grip_tables.py`, `arranger/grips.py`, `arranger/cost.py` |
| how a shape is placed on its strings — a family that *searches* versus one that computes a layout, `Placement`, `candidate`, the placement memo (`search_shape` / `_searched_shape` / `place_shape`) | [docs/history/generated-grips.md](docs/history/generated-grips.md) §4 | `arranger/grip_place.py`, `arranger/grips.py`, `tests/test_placement.py` |
| where a **lone note** is fretted — a fill, an `NC` bar, a rescued melody, a span demotion (`get_melody_only_voicings`, `_melody_alone_shape`) | [docs/engine.md](docs/engine.md) | `arranger/grips.py`, `arranger/melody_alone.py`, `arranger/routes.py`, `tests/test_non_chord_tones.py` |
| which chord tones a shape states — `TONE_PRIORITY`, the tone a four-voice shape gives up, the palette a melody with no degree to match is offered, or the order that was not taken | [docs/history/generated-grips.md](docs/history/generated-grips.md) | `arranger/grip_tables.py` (`TONE_PRIORITY`, `stated_tones`), `arranger/grips.py` (`drop2_template_for`, `_drop2_palette`), `tests/test_generated_grips.py`, `tests/support.py` (`WITNESS`) |
| the trailing annotation a step carries, why a shape is thin, or what **must** be explained when a choice is added (`ArrangementStep.palette`, `cost.VOICING_COST_CRITERIA`, `tests/meta_explanations.py`) | [docs/engine.md](docs/engine.md) | `arranger/annotation.py`, `arranger/render.py`, `arranger/movement.py` |
| `ArrangeOptions(texture=…)`, target/fill roles, the walking bass, a hold that moved the melody's string | [docs/engine.md](docs/engine.md) | `arranger/texture.py`, `arranger/routes.py`, `arranger/bass_rules.py`, `arranger/bass_place.py`, `arranger/bass.py`, `arranger/decisions.py` |
| non-chord melody notes, a new chord quality | [docs/engine.md](docs/engine.md#adding-a-new-chord-quality) | `arranger/chords.py` |
| the step loop, `arrange_progression`, or **which route takes a slot** | [docs/engine.md](docs/engine.md) | `arranger/movement.py`, `arranger/route_dispatch.py`, `arranger/harmonised_route.py`, `arranger/step_prepare.py`, `arranger/resolution.py`, `arranger/slot_plan.py`, `tests/meta_route_dispatch.py` |
| a step route's arguments - `SlotContext`, one slot's request as a value rather than twenty parameters, and the `SlotInputs` groups under it (`SlotArrangementFacts`, `SlotRhythmFacts`, `SlotNeckFacts`, `SlotBassFacts`) | [docs/engine.md](docs/engine.md) | `arranger/context.py`, `arranger/slot_plan.py`, `arranger/movement.py`, `arranger/harmonised_route.py`, `arranger/routes.py` |
| tab staff, HTML, MusicXML, GP5, or the MusicXML importer — or **which module may import which**, including the `arranger ↔ tabstaff` loop and why it is inert | [docs/renderers.md](docs/renderers.md), and [docs/dependency-dag.md](docs/dependency-dag.md) | `tabscore.py`, `tabstaff.py`, `tabxml.py`, `tabgp.py`, `headxml.py`, `tests/meta_front_end_dag.py` |
| an imported head's **repeats, volta endings or jumps** — why it is longer than the file's measure count, or the `|:` / `:|` / `1.` / `2.` / `D.C.` / `D.S.` / `Coda` / `Fine` the writers draw | [docs/renderers.md](docs/renderers.md) | `headxml.py` (`_parse_barline`, `_parse_direction`, `_parse_sound`, `_expand_play_order`, `expand_repeats`, `BarInstruction`, `BarMarker`, `Head.markers`, `HeadNote.written_bar`); each writer's `markers=` parameter |
| the slot layer: triples to steps, the diminished retry, the slash bass | [docs/engine.md](docs/engine.md) | `arranger/slots.py` |
| the **request** — the six questions, spelled by `--chord-on`, `--bass-on`, `--chord-notes`, `--bass-notes`, `--chord-fills`, `--no-melody` and by `Request(...)` — or a new one, and how a request becomes the axes (`Rhythm`, `parse_rhythm`, `felt_beat`, the refusals) | [docs/engine.md](docs/engine.md) §"The request, and the axes under it" | `arranger/options.py` (`Request`, `resolve_request`, `format_request`), `arranger/grid.py` (`Rhythm`, `parse_rhythm`, `felt_beat`), `arranger/cli.py` (`REQUEST_DESTS` is the one list holding the two spellings to the same six), `tests/test_rhythm.py`, `tests/test_request.py` |
| the MusicXML **importer's chord timeline**, or a bar the melody skips | [docs/engine.md](docs/engine.md), and [docs/history/open-issues.md](docs/history/open-issues.md) item 6 for the release instant — closed by reading a note as sounding over `[onset, end)` | `headxml.py` (`chord_at`, `rhythm_slots`, `fill_slots`, `melody_rests`, `_bar_resolution`, `_tick_key`) and `grid.py` (`grid_resolutions`, `TICKS_PER_BEAT`) — **built**: a position the request names is emitted with `melody=None`, a rest policy places chords in the tune's notated silences, and §9.2 refuses a position the tune is still **holding** while admitting the instant it is released. The engine's own union - one position per subdivision of each bar's rhythm - is what a selection that **comps** gets when the request names nothing added: a chord part with no tune to play, which is how it states the chord in a bar the tune never enters. The gate reads that selection and not the *spelling*, so a request and its axis spelling are one arrangement |
| an issue — where a new one is filed, and where the closed ones are recorded | [docs/open-issues.md](docs/open-issues.md) (the live ledger; none is open) and [docs/history/open-issues.md](docs/history/open-issues.md) (the record of the six it filed) | — each item is stated as **issue / problem / why it exists** with its measurement, and the figures and the behaviour are that document's own business: no test compares them with the prose or is keyed to these items |
| a **note held over a bar line**, when the melody's end is reached, or a pickup bar (`Head.first_bar_implicit`) | [docs/engine.md](docs/engine.md) | `headxml.py` (`melody_at`, `melody_state`, `_merge_chord_slots`), `arranger/grid.py` (`beat_offset`), `tests/test_headxml_timeline.py` |
| which finger frets which string, or a per-finger cost criterion; which strings the right hand's `p-i-m-a` pluck, the gaps between them, and how far the thumb reaches | [docs/history/fingering.md](docs/history/fingering.md) | `arranger/fingers.py` (not inert: `bass_place` and `bass_merge` read `can_fret` for the four-finger budget **and the hand's five-fret reach** — `tests/test_fingers.py` holds the caller set to exactly `{bass_place, bass_merge}`; no per-finger cost yet). Its §4.3 measurement landed a *right-hand* rule first (`grip_tables.thumb_safe_grips`, read by `decisions.resolve_texture_grips`) and then a *left-hand* one (`fingers.can_fret`, read by `bass_place.place_bass`); its **§4.4 finger-skip half is now built**, not recorded: the four `drop24` sets that carried the skip were removed from `GRIP_STRING_SETS` (`grip_tables.finger_skip_count` is the rule and `tests/test_grip_tables.py` holds the tables to it), at a price counted in chords, and the three rejected forms of the same lever are in §4.4 rather than here. Its thumb's-reach half still changes no count (`tests/test_texture.py::TestTheThumbReach` pins the reach), and **§4.3's follow-on — should the *selector* leave room for the thumb? — is now built**, as a palette narrow rather than a criterion (`decisions.leaving_room_for_the_bass`), so a requested bass note moves the shape instead of being dropped; its numbers are in [docs/history/open-issues.md](docs/history/open-issues.md) item 2 rather than here, because that item is where they are re-measured by hand and a figure repeated in this table would be a second source for one fact. **Item 5** of that document, the same §4.3 question asked from the lone-note end, closed on the same change together with `MAX_HAND_SPAN` |
| `ArrangeOptions(parts=…)`, which of melody / bass / chord the guitar plays | [docs/engine.md](docs/engine.md) | `arranger/parts.py` (`PART_NAMES`, `parse_parts`, `parts_have_melody`, `parts_has_melody_only`) |
| the harmonisation axes — `ArrangeOptions(parts=…)`, `texture`, `bass`, and the metre — the four-string arithmetic, and what replaced `voices=` and the grip-family axis | [docs/engine.md](docs/engine.md) | `arranger/parts.py`, `arranger/grid.py`, `arranger/grouping.py`, `arranger/texture.py`, `arranger/bass.py`, `arranger/resolution.py`, `arranger/grips.py` |
| a **held thumb**, a **restruck chord**, a **held shape the walk invented** (`bass_only`, `is_bass_only`, `melody_is_ringing`) or a stab's length — `bass_held`, `chord_attack`, `carry_bass`, `_stab_length`, and what each renderer draws for a note that sounds and is not plucked | [docs/renderers.md](docs/renderers.md) §"What the four renderers must agree about", and [docs/engine.md](docs/engine.md) §"The other hold: a beat the thumb invented" | `arranger/decisions.py` (`is_bass_only`, `melody_is_ringing`), `arranger/bass_merge.py` (`carry_bass`), `arranger/slot_plan.py` (`_chord_attacks`), `headxml.py` (`_stab_length`), `tabscore.py` (`_is_hold`, `_capped_span`), `tabstaff.py` (`_strikes_here`, `_moved_thumb`, `_draws`), `tabxml.py` (`_sounding`, `_build_note`), `tabgp.py` (`_sounding_frets`, `_strike_notes`), `tests/test_bass_hold.py`, `tests/test_chord_attack.py`, `tests/test_staff_thumb.py`, `tests/test_bass_placement.py`, `tests/test_guitarpro.py` |
| a **lone bass line**, or a slot with nothing above the thumb (`bass_alone_step`, `lone_bass_case`, `is_shape_held`) | [docs/engine.md](docs/engine.md) | `arranger/decisions.py`, `arranger/routes.py`, `arranger/bass_place.py`, `arranger/annotation.py`, `tests/test_lone_bass.py` |

| how a **compound metre is felt** — `time_signature=`, `TimeSignature`, `TARGET_BEATS` as felt beats, a walk on the pulses, a requested chord rhythm's positions in groups, the `n+n+…` refusal, and the direction / beaming / metronome channels a lead sheet states it through | [docs/engine.md](docs/engine.md) | `arranger/grouping.py` (`TimeSignature`, `COMMON_TIME`), `arranger/texture.py`, `arranger/grid.py`, `arranger/bass.py`, `headxml.py` (`Head.grouping`, `Head.grouping_source`, `_score_grouping`, `_beam_partition`, `_grouping_hint`, `_metronome_pulse`), `tests/test_grouping.py`, `tests/test_headxml_arrangement.py` |
| the step/voicing mirrored fields (`step.grip`, `step.bass`), or which selection is melody-only | [docs/engine.md](docs/engine.md), and [docs/history/one-fact.md](docs/history/one-fact.md) for why | `arranger/step_types.py`, `arranger/movement.py` |
| how something was decided, historically — `voices=`, the comping styles, the parts redesign, the generated grips, the fingering notes, the Stage-2 collapse | [docs/history/](docs/history/) | — |
| user-facing behaviour and examples | [README.md](README.md) | — |

**`docs/history/` is not extended.** It is where a completed plan or a retired document goes:
it records why a decision was made and is never revised. If the code has moved on, the history
is still true *about the past* — so read the current documents above first and treat a
contradiction between them as a bug in one of them. A retired document is added once and then
frozen like the rest; it is not a home for an open plan. Eleven are retired there:
`reharmonisation-proposals.md`, whose corpus went away; the six plan documents whose live
halves are now stated in [docs/engine.md](docs/engine.md) — `voices-axis.md`, `one-fact.md`,
`parts.md`, `generated-grips.md`, `comping-styles.md` and `fingering.md`; `restructuring.md`,
the round-2 plan, whose live half is the module map below and the budget table in
`tests/meta_structure.py`; `rhythm-request.md`, the rhythm-first request, whose live
half is the flag table in [README.md](README.md), the request-to-axes mapping in
`docs/engine.md` and the four renderers' agreement in
[docs/renderers.md](docs/renderers.md); `open-issues.md`, the ledger whose six items all
closed, whose live half is the index in [docs/open-issues.md](docs/open-issues.md); and
`architecture-review.md`, the review and its seven-stage plan, whose live half is the module
map, the budgets and the dispatch table its own header names. Each of them carries a retirement
header saying which half of it is the record and where the live rule went, which is the one
thing to read before quoting one.

## The gate

```bash
make check      # lint + typecheck + test, in that order — what CI runs
```

Current measured state: **1315 feature + 84 meta tests OK (skipped=2)**, pyright
**0 errors 0 warnings**, ruff **0 errors**. If your change moves any of those numbers, that
is the signal — not the absence of an error message. A quiet run is not evidence; a moved
count is.

**The suite is two halves, and the filename is the half.** `make test` runs both, in two
`discover` invocations, because unittest filters by one basename pattern and cannot
exclude one:

```bash
make test-features   # tests/test_*.py   - the music: the inner loop
make test-meta       # tests/meta_*.py   - the tree: before committing
make test-one M=tests.test_texture       # named modules: the fastest loop
```

A test about the **music** is `test_*.py`; a test about the **tree** — the module graph,
the budgets, the private seams, the generated chart, the fixture corpus, the extras'
laziness, the explanation contract — is `meta_*.py`. **When in doubt it is `test_*.py`**,
because that half runs first, so a mis-filed test is seen early rather than never.
`tests/meta_structure.py::TestTheSplit` fails on a module matching neither pattern, which
is the only way a pattern-based gate could go quiet, and `test` running both is what keeps
the split a way *in* rather than a smaller gate. The split is a reading aid, not a speed
fix: **84 of 1399 tests are meta**, and the minutes are in the four feature modules that
sweep every quality or every committed head (`test_comping`, `test_fingers`,
`test_musicxml`, `meta_explanations`) — so `make test-one` on the module you are touching
is the loop that actually saves time.

**A public request in front of the axes.** `head` asks six questions - who plays the
tune, when each accompaniment layer attacks, what each states, and what the chord does in a
melody rest - and `options.resolve_request` derives the axes from them. The six are **one
value spelled twice**: by those flags and by `Request(...)` on
`arrange_progression(progression, request=Request(...))`, with `cli.REQUEST_DESTS` the one
list holding the two spellings to the same six. Both are the **user-facing vocabulary**; the
axes below are the engine's implementation, and **`options=ArrangeOptions(...)` is the one
door to them** - no entry point takes an axis as a keyword, which
`tests/meta_structure.py::TestTheAxesAreNotEntryPointKeywords` holds. `texture` (how many
chord tones the part states, `TEXTURE_STYLES`), `bass` (the note rules the thumb states,
`BASS_RULES` in `bass_rules`), `parts` (which of melody / bass /
chord the guitar takes, `PART_NAMES`) and the metre (`TimeSignature`: its count, denominator and
felt grouping, `GROUPING_AUTO` plus the `N+N+…` algebra in `grouping.py`) are
**orthogonal**, and a band setting is a combination
rather than a mode: `ArrangeOptions(bass="none", parts="melody")` is a bassist on the root,
a horn on the melody and the guitar holding the tune alone between them.
The request and the metre are the exception the other way: they are **input facts** - what is
being arranged rather than how to play it - so `request=` and `time_signature=` sit *beside*
`options=` and are reconciled by `resolution.settle_input_fact`, which is what keeps
`arrange_progression(P, request=..., options=ArrangeOptions(axis=...))` one call rather than
two mutually exclusive ones.
The request's mapping is one-way and stated in `docs/engine.md` §"The request, and the
axes under it": `--chord-notes` is `texture`, `--bass-notes` is `bass`, the two rhythms are
the layers' `Rhythm`s, and `parts` is derived from what the request leaves sounding.
**Spelling that derivation out is the same arrangement, not a second one**, and that is
held rather than asserted: `tests/test_request.py::TestTheAxisSpellingIsTheRequest` spells
each of a table of requests' own `resolve_request` result back as `parts`/`bass`/`texture`
and requires the same tabs over the committed sweep heads. A rule the engine decides
*after* the derivation - which is what the importer's comping union is, and what
`melody=False`'s chord rhythm used to be - is the way that equality breaks, and the way
it is restored is to make the rule read the **selection** rather than which door the
caller came through.
Adding an axis means a new vocabulary (`*_STYLES` / `*_POLICIES`, or a note-rule
`*_RULES` table like `bass`'s `BASS_RULE_ROLES`) and a `*_AUTO`
sentinel that is deliberately **not** in the vocabulary, plus a `*_allowed` refusal function
derived from a table rather than listed — never another branch at the call sites. **It is a
field on `ArrangeOptions` and nothing else**: a keyword for it on an entry point is the
second spelling this surface exists without, and the standing guard fails on the commit that
adds one. The trap: a loop
variable shadowing a policy parameter (`melody`, in the since-removed `wjazzd.arrange_slots`,
did exactly this, and it only raised when a diminished retry had something to rescue).
`grouping` is the one axis whose vocabulary is an **algebra rather than a list** - any
positive lengths summing to the bar - so it has no `*_STYLES`; `grouping_allowed` derives
the refusal from "the groups partition the bar", and `auto` is the sentinel. Its default
derives threes for a compound metre and one group per beat otherwise, so every simple
metre is byte-identical to before the axis existed.

**`grouping` is the one axis a lead sheet can state for itself**, so `head` reads it from
the score - an `N+N` mark in a direction, the primary beaming, or a metronome pulse, in
that order - and exposes no flag. A progression built without a file declares the whole
metre as `time_signature=TimeSignature(beats_per_bar, beat_type, grouping)`; omitting it
means `COMMON_TIME` (4/4), and an explicit grouping is the caller's override when a score
does say. A conventional simple metre (2/4, 3/4, 4/4, 2/2) ignores its
beaming: a notation program's beam pairs restate the beat rather than group it.

**A comping-content axis has to be scoped to the comping route**, and that is the shape
of the trap when one is added: the melody-bearing route pins the tune to the soprano
string and takes its family from `GRIP_PREFERENCE`, so an axis claiming to say which
*degrees* a shape states cannot reach it by accident. The metre is the counter-example
and is deliberately not one: `TimeSignature` is a metre fact rather than a choice about
the chord part, so the metric layer, the walk and the chord's rhythm read it on **both**
routes.

**`make check` is what CI runs**, in one job (`.github/workflows/ci.yml`, Python
3.11–3.14, with the `xml` and `gp` extras so the optional-extra tests are not silently
skipped). **There is no second job and nothing a clean clone cannot run** — that used
to need stating here and in the workflow header, because the 42 MB Weimar Jazz
Database was gitignored and 85 of the suite's tests skipped on every fresh checkout.
The database **and its loader** are gone, so a green check means the whole suite ran, and
the only guards left are the optional-extra ones this job installs against. (The 42 MB
`wjazzd.db` file is gitignored, so a working copy may still have it; nothing reads it.)

**`make check` runs one interpreter, and the matrix runs four.** It is the 3.14 dev
one. A construct that is version-dependent passes here and fails on the 3.11 job —
see trap 11, where a two-argument `Enum(...)` call was a value lookup on 3.12+ and
class definition on 3.11.

Individually:

```bash
make test        # both halves: test-features then test-meta
make typecheck   # pyright, with --pythonpath so it can see the venv
make lint        # ruff
make demo        # the built-in demonstration arrangements
```

## Repository layout

```
arranger/
├── arranger/            # the engine - a package, not a module
│   ├── __init__.py      #   facade: re-exports, __version__, main()
│   ├── __main__.py      #   `python -m arranger`
│   ├── tuning.py        #   STANDARD_TUNING, GuitarFretboard, the neck window
│   ├── step_types.py    #   Voicing, ArrangementStep, Palette, the tab-cell primitives
│   ├── context.py       #   one slot's request, shared by the two step routes
│   ├── fingers.py       #   which finger holds which fret; read by bass_place for the fret budget
│   ├── chords.py        #   ChordParser, non-chord-tone routing
│   ├── grip_tables.py   #   the grip tables and the questions asked of them
│   ├── grip_place.py    #   where a shape is placed on its strings, and the memo
│   ├── grips.py         #   the builders and the candidate generators
│   ├── cost.py          #   voicing_cost - the library's central invariant
│   ├── annotation.py    #   the trailing explanation, composed from the step's fields
│   ├── parts.py         #   which of melody / bass / chord the guitar takes
│   ├── grouping.py      #   TimeSignature and the metre's grouping algebra
│   ├── grid.py          #   the request's rhythm: `Rhythm`, felt beats, the lattice
│   ├── texture.py       #   how many notes the chord part states; metric roles
│   ├── bass_rules.py    #   the bass vocabulary, capacities and refusals
│   ├── bass_place.py    #   the thumb's octave and string: the cost and `place_bass`
│   ├── bass.py          #   the walking-bass thumb line
│   ├── bass_merge.py    #   merges the walk into a chosen step; the next resolution melody
│   ├── options.py       #   ArrangeOptions - the knobs as one value
│   ├── resolution.py    #   what the caller asked for, resolved once
│   ├── decisions.py     #   decisions both step loops share
│   ├── melody_alone.py  #   where a lone note is fretted: the tune alone, chord or not
│   ├── routes.py        #   the route handlers: rest, fill, NC and the comping route
│   ├── slot_plan.py     #   one slot's plan: `slot_state` and the value it returns
│   ├── step_prepare.py  #   one slot's candidates: prepare_step and its preparation
│   ├── harmonised_route.py #  the melody-bearing route: prepare, select, demote, emit
│   ├── route_dispatch.py # the branch table: which route takes a planned slot, in order
│   ├── movement.py      #   the step loop: _loop_slots, arrange_progression
│   ├── steps.py         #   VoiceLeadingEngine - the published facade
│   ├── slots.py         #   the slot layer: triples to steps, the one pre-pass
│   ├── render.py        #   format_progression and per-step rendering
│   ├── cli.py           #   the head CLI's flags and output dispatch
│   └── demo.py          #   main(): the built-in demonstration and the `head` hand-off
├── tabscore.py          # score placement shared by the MusicXML and GP5 writers
├── tabstaff.py          # whole-progression staff renderers (ASCII + HTML)
├── tabxml.py            # MusicXML export (optional extra: music21)
├── tabgp.py             # Guitar Pro 5 export (optional extra: PyGuitarPro)
├── headxml.py           # MusicXML import: a melody + chord symbols
├── grip_chart.py        # generates common_grips.md from the engine's tables
├── tests/               # unittest: `test_*.py` is the music, `meta_*.py` the tree
│   └── data/            # committed MusicXML fixtures (music21, MuseScore, ours)
├── docs/                # the documents the routing table above points at
├── pyproject.toml       # PEP 621 + PEP 639 metadata (setuptools backend)
├── Makefile             # the gate, above
├── .github/workflows/   # CI: one job, make check on 3.11-3.14
├── AGENTS.md            # this file
├── README.md            # user-facing overview
└── .venv/               # local virtualenv (not committed)
```

There is **no** `setup.py`, `setup.cfg` or `requirements.txt`. CI *is* configured
(`.github/workflows/ci.yml`, added in Phase 9) and it runs exactly `make check`.
Packaging metadata lives solely in `pyproject.toml`, which reads the version
dynamically from `arranger.__version__` — that is the single source of truth.

### The engine is a package, and the order is enforced

The engine was one 4290-line module until Phase 5 of the package refactor. It is
now a package of focused modules in a strict dependency order:

```
tuning -> step_types -> fingers -> chords -> grip_tables -> grip_place -> grips -> cost -> annotation -> parts
                             -> grouping -> grid -> texture -> bass_rules -> bass_place -> bass -> bass_merge
                             -> options -> resolution
                                                                    |
                       melody_alone -> routes -> slot_plan -> step_prepare -> harmonised_route
                                                                                    |
                                                    route_dispatch -> movement -> steps -> slots -> render -> cli
```

`demo` is the one module the chain does not show: it is the **printing front end**
(`main()`, re-exported as `arranger.main`), it imports `steps` and `render` and nothing
from `cli`, and only the facade imports it. So it sits beside the chain rather than
below `cli` - the order lists it last because nothing above it needs it, not because
`cli` feeds it.

`fingers` — which finger holds which fret — hangs off `tuning` alone, so it is drawn
separately rather than as a branch of that chain. It is **not inert**: `bass_place` reads
`fingers.can_fret` for the four-fret budget of the playability invariants below, which is
an *upward* import and so legal. `docs/history/fingering.md` §5 step 3 — a per-finger cost
criterion — is still open.

```
tuning -> fingers   (step 1 of docs/history/fingering.md; `bass_place` reads can_fret for §4.3)
```

A module may import only what is *below* it, and
**`tests/meta_package_dag.py` asserts that from the AST** — so the layering cannot
erode one "temporary" import at a time. Read its `ORDER` list before adding a module.
`ALLOWED_EDGES` in that file is the escape hatch: each entry there must justify itself
in a comment. It is **empty** now, and an entry that no longer permits an import fails,
so permission cannot outlive the code it was granted for.

The same discipline has two other checks. **`tests/meta_structure.py`** fails a module
that reaches a sibling's `_`-prefixed name either by importing it or through a module
alias (`alias._helper`), and its `ALLOWED_PRIVATE_ATTRIBUTES` list is empty too -
`render` importing `annotation.step_annotation` rather than `_step_annotation` is what
kept it so. **`tests/meta_front_end_dag.py`** holds the top-level modules to the same
rule, with the deliberate edges named: `tabstaff`'s re-exports of the two writers, and
each writer's use of `tabscore` for placement. `FRONT_ENDS` in `tests/support.py` is
the one list the budget table and that DAG test both read.

Three consequences worth knowing:

- **Adding a module inside `arranger/` needs no `pyproject.toml` change** — the
  package is already listed — but **four lists still name it**: `ORDER` in
  `tests/meta_package_dag.py`, `BUDGETS` in `tests/meta_structure.py`, and the
  facade's `from . import (...)` and `__all__`. The last two are not bookkeeping:
  a submodule the facade never imports is reported by pyright as "specified in
  `__all__` but not present in module", and one that is imported but unlisted fails
  `test_dunder_all_matches_the_public_surface`. A new *top-level* module
  additionally needs a `py-modules` entry, or a clean install ships without it.
- **The Makefile names the package as a directory**, so a new engine module cannot be
  forgotten by lint or typecheck. A new *top-level* module must be added to `MODULES`
  and to the `typecheck` target in the same commit that creates it.
- **`Voicing` and `ArrangementStep` live in `step_types`, not `tuning` or `steps`**,
  because `grips` constructs a `Voicing` and both dataclasses default `role` to
  `ROLE_TARGET`. `tuning` is the instrument alone; `step_types` is the value types and
  the tab-cell primitives they render through. That placement is forced by edges, not
  by taste.

## Requirements and licence

- Python **3.11+**. The local dev virtualenv runs 3.14. 3.10 was dropped because
  `tomllib` is 3.11+.
- **One** runtime dependency: [musthe](https://pypi.org/project/musthe/).
- **Two** optional extras, each behind a lazy import so the library works without
  either: `xml` → [music21](https://pypi.org/project/music21/) (`tabxml.py`), and
  `gp` → [PyGuitarPro](https://pypi.org/project/PyGuitarPro/) (`tabgp.py`). The two
  are independent: a run asking for a GP5 file must not require music21.
- **Dev-only**, never reachable from a plain install: `pyright` and `ruff`
  (`pip install -e '.[dev]'`).

Tests are stdlib `unittest` — there is no `pytest` dependency — and the database- and
extra-dependent test modules are `skipUnless`-guarded, so the suite passes on a fresh
clone with neither.

**Licence: MIT** (see `LICENSE`), declared as PEP 639 metadata in `pyproject.toml` —
`license = "MIT"` plus `license-files = ["LICENSE"]` — which is why
`build-system.requires` is `setuptools>=77`. Do not also add the
`License :: OSI Approved :: MIT License` classifier: it is deprecated once the SPDX
expression is present, and adding both makes setuptools warn.

The permissive licence is load-bearing, and one dependency is why it has to be.
PyGuitarPro is **LGPL-3.0**, so keeping this project clearly *not* a combined work of
it matters. Two things do that, and both must stay true: it is a **runtime**
dependency of neither the package nor the test suite, and `tabgp` imports it
**lazily**. Copying PyGuitarPro code into the tree would change the analysis — don't.

## Setup

A virtualenv already exists at `.venv/`. Prefer invoking its interpreter directly
(`.venv/bin/python`) so you do not depend on shell activation. Recreate with:

```bash
python3 -m venv .venv
.venv/bin/pip install musthe
.venv/bin/pip install pyright ruff     # dev-only type checker and linter
```

No editable install is required — the tests import `arranger` from the repository
root — but `pip install -e .` provides the `jazz-arranger` console script.

Note the name split: the **distribution** is `jazz-arranger`, because the PyPI name
`arranger` is taken by an unrelated project, while the **import** name stays
`arranger`.

### If the interpreter hangs at startup

`Fatal Python error: init_import_site: Failed to import the site module` means the
editable-install finder in `site-packages` is broken. The symptom is a **hang, not an
error**: the traceback only appears once something interrupts it, so the shell looks
stuck rather than broken.

The cause seen here was a stale finder for a long-superseded early version, left
over when the project was still pre-release. It is regenerated on every
`pip install -e .`, so the stale copy is what a version bump leaves behind when the
reinstall is skipped.

```bash
.venv/bin/pip install -e . --no-deps
```

To confirm the symptom is this and not something else, run
`./.venv/bin/python -S -c 'print(1)'`: the `-S` skips site processing, so it succeeds
where the normal invocation hangs.

## Build and run

There is no build step for local development.

## Conventions

- `from __future__ import annotations` at the top of every module; use `typing`
  aliases (`List`, `Optional`, `Tuple`, `Dict`, `Any`) consistently. This is house
  style, which is why `ruff`'s `UP*` rules are off — see `pyproject.toml`.
- Dataclasses for value objects; `@staticmethod`/`@classmethod` for stateless logic.
- Preserve the dict-style `__getitem__` shims on `Voicing` and `ArrangementStep`.
- Docstrings on public classes and methods. Comments explain *music-theory intent* —
  which chord tone is in the top voice, and why a shape is unreachable — not syntax.
- **Rendering is pure.** Every renderer returns a string (or list of them) and prints
  nothing. Only `demo.main()` and the demo it runs write to stdout.
- **The library never prints**, and it has no warning channel either. What the engine
  used to report through a `Diagnostics` collector is now either **on the tab line** -
  read off the step's own fields and phrased by a `render` `*_clause` - or a
  `ValueError` from the axis that could not honour the request. Adding a `print()` to
  the engine is a regression, and `tests/meta_explanations.py` is what keeps a choice
  from going *unexplained* rather than merely unprinted.
- **Do not add a third-party dependency** without explicit approval. `musthe` is the
  only runtime one; that is load-bearing for the LGPL reasoning above.

### Docstrings describe the present, not the past

A docstring states what a thing **is** and what a caller or an editor must know. It is
not a changelog, and it is not where the reasoning lives. Three kinds of text compete
for that space, and only the first belongs in the source:

- **The contract, and any do-not-change constraint** — keep it, in the present tense.
  "`requested` narrows the palette and must never widen it"; "do not reorder this
  tuple". The warning is what stops the next editor undoing a deliberate choice, and
  the traps below are the record of what that costs when it is missing.
- **The story of how it got here** — delete it. "This was two functions", "it used to
  be a classmethod", "Phase 5 moved this", "the database is gone", a former module
  name, a forward-looking "for now". Narrative of this kind is written against a tree
  that stops existing, and an agent that reads it acts on a fact that is no longer
  true. The reason it is *always* the wrong place is that it has no test: nothing fails
  when it goes stale, so it rots silently while the gate stays green.
- **A measurement, and its number** — move it to the document that already holds it:
  [docs/open-issues.md](docs/open-issues.md) for a diagnosed bug (the ledger; the closed items
  are the record in [docs/history/open-issues.md](docs/history/open-issues.md)), the relevant
  `docs/*.md` for anything else, [docs/history/](docs/history/) for a completed plan. A
  count in a docstring is the fastest-rotting string in the repository and is stored
  where it is least likely to be re-measured. Leave a one-line pointer instead.

A module docstring is one to three sentences: what the module owns, and where it sits
in the dependency order.

### Playability invariants

Every generated voicing must satisfy all of these. They are asserted per-shape in
`tests/test_grips.py`, and they are what makes a tab playable rather than merely
correct:

- the sounding strings are exactly one `supported_string_sets()` entry — two to four
  strings, every other muted (`-1`). **Four is the right hand**: the plucks are thumb,
  index, middle and ring (`p-i-m-a`), so a step must never sound five, which is why the
  bass note a thumb line merges into a step goes *outside* the upper shape's set rather
  than onto it, and why a target under a thumb may sound at most three strings
  (`grips.thumb_safe_grips`);
- the melody is on that entry's soprano string, and is the highest sounding note;
- `0 <= fret <= 18` and `fret_span() <= GRIP_MAX_SPAN[grip]` (5, or 4 for a duo).
  The span is checked on the frets actually placed, **not** as "within N of the
  soprano": those differ, and the second admits a span of ten;
- **four fingers and five frets** — and unlike the four above, this one is stated over a
  *step* rather than a shape, because that is the only level at which it can fail. A
  generated grip sounds at most four strings and so spans at most four frets; a
  `bass_only` step, though, merges the thumb into a shape the hand is still **holding**,
  where its fret can be a fifth, and a merged hand can be *three* fingers and *eight*
  frets. `fingers.can_fret` is the check — `fingers_needed <= 4` **and**
  `hand_span <= MAX_HAND_SPAN` (5, the hand's own size, with every `GRIP_MAX_SPAN` entry
  under it), two refusals that do not imply each other — and `bass_place.place_bass` and
  `bass_merge._takes_the_ring` are its callers: a candidate beyond the hand is refused, so
  the step keeps its upper voicing and the omission is reported, exactly as when no string
  is free. Measured over the committed heads: **1** such step before the first fix, **0**
  after; the reach half arrived with **44** steps over five frets and a worst of **9**, and
  `docs/history/open-issues.md` item 5 holds the figures and the bar. It is the smaller twin of the
  bullet above: the same trap, the rule asserted on the part of the whole that happened to
  be checked;
- **the note is not merely refused: the shape is asked to make room.** A requested bass
  note narrows the palette before the ranking
  (`decisions.leaving_room_for_the_bass`), so the harmony moves to where the thumb can reach
  the note instead of the line losing it. A *narrowing*, never a widening and never a
  criterion: no candidate carries a thumb, and a palette where nothing survives comes back
  unchanged so the step keeps its shape and names the refused note. The shape given up is
  recorded on `Palette.dropped_for_bass` and phrased by
  `annotation._bass_room_clause`, because a shape that moved for the bass is otherwise
  indistinguishable from one that merely ranked lower;
- every sounding pitch is a chord tone, except the melody itself when it is not one.
  Every shape the rule builds is pure — measured over every chord tone of all 29
  qualities — so what a non-chord melody carries is the caller's own note rather than
  a shape's, and the selector's first cost criterion ranks pure candidates first.

Two more that follow from the neck window, which is a **preference and never a
filter**: a step with no voicing inside frets 2–13 is still played, just outside it,
because losing a chord of the tune is worse than being a fret out of position. And a
melody whose only position sits above `HIGH_FRET_LIMIT` is voiced an octave down, so
`step.melody` may be an octave below the written note — the written pitch stays in
`step.original_melody`.

### Every choice about a voiced note is explained by the line that prints it

**A step has to account for what it did, and for the shape it did it with.** This is an
invariant of the artifact rather than a style preference: the one-line tab is what a user
reads, so a choice it cannot see is a choice the library made silently. It is also the
constraint on growth — **a new axis, grip, substitution or fallback arrives with its
explanation**, because the alternative is a knob whose effect is invisible.

The mechanism is that the explanation is **recorded on the step and composed by the
renderer**, never re-derived at a call site:

- a choice *among shapes* lives on `ArrangementStep.palette` (the most voices the palette
  offered, the best fuller candidate, the `cost.voicing_cost` element that ranked it lower,
  `inside_window`) and is phrased by `annotation._shape_clause` / `_window_clause`;
- a fact that **corrects a column** — the octave a melody was moved to, the chord a
  substitution actually states, a written slash bass no shape sounds — is a *derived clause*
  (`_transposition_clause`, `_substitution_clause`, `_slash_bass_clause`), so it reaches every
  route that can suffer it, a hold included;
- a **choice the shape embodies** that no field records is derived from the step's own fields
  too, but is suppressed on a hold like the `palette` clauses, because it accounts for the
  shape rather than for a column: `_omission_clause` names the chord tone a four-voice shape
  gives up (`TONE_PRIORITY`'s tail), and `_sounding_clause` names the voices a shape with two
  or more of them sounds, each with the degree it states. Derived rather than recorded because
  the whole fact — the
  routed chord's tones against the pitches sounding — is already on the step, and a field
  beside it would be a second source for one fact;
- a **route that chose no shape** states its own (`_comping_clause` names the voices it
  states, each by note and degree; "the tune is silent here"; "the guitar rests here"; "the
  shape above is held"; "the most a fill's palette offers" — the last is the difference
  between *the library ran out* and *the caller asked for fewer*).

`tests/meta_explanations.py` is the standing check: a table of (decision, when this step is
one of those, what the line must say), swept over every committed head and working from the
step's **fields** rather than from the wording, so it cannot be satisfied by phrasing.
**Adding a decision means adding its witness to that table in the same commit**, and a new
`*_clause` helper fails a companion test until it is registered there — the enumeration is
read off the module, so a clause cannot be added and forgotten.

Two exemptions are deliberate and are named in that file rather than left implicit, because
a rule with unnamed exceptions is a rule the next editor deletes: a **hold** does not restate
the shape count (it was explained where the shape was chosen) though it does restate what
corrects a column; and the **slash bass** is pinned by its own test, because a witness that
recomputed whether the bass sounds would be the clause agreeing with itself. The third —
"a melody-alone shape with no palette" — went with the reason for it: a lone note is now
chosen from a palette of single-note shapes (one position per eligible string) by the same
cost tuple a chord goes through, so its fret **is** a choice and the window clause has a
measured `Palette.inside_window` to state rather than a defaulted one to guess with.

What the invariant does **not** cover, and should not pretend to: a *phrase* (nothing groups
steps) and the **fingerings** (`fingers.py` assigns them and no renderer prints them — a barre is
visible in the tab). Positions the guitar *declines* used to be the third exemption — dropped
from the tab with only a warning to report them — and are not any more: the four
routes that dropped them emit a rest step whose `silence` names the reason, and
`annotation._silence_clause` phrases it, which is why it carries a witness in the table above.


### The cost tuple is not being refactored

`voicing_cost` returns a `VoicingScore` - a `tuple` subclass whose **7 fields are the
library's central invariant**. The order is asserted once, and positionally, by
`tests/test_grip_selection.py::TestVoicingCost::test_the_field_order_is_the_rule`; every
other assertion reads a field by name (`score.span`, not `score[3]`). Moving the code is
safe; **reordering the fields is a musical decision, not a refactor.** Span is the one
criterion promoted above position, and that was measured rather than guessed — the
reasoning and the table of what it cost are in [docs/engine.md](docs/engine.md). Changing
what a criterion *reports* is the same decision: spans 0 and 1 are bucketed to one value
at the span index (a one-fret reach does not outrank keeping the hand in place),
measured at one moved pin, and the `0/1/2` bucket was measured at 13 and rejected.

**What is cheap is adding one.** A field on the score, its phrase in
`cost._CRITERION_LABELS` (keyed by field name), and the value it reads from
`SelectionCriteria` - because the label tuple, the span index and the partition index
are all derived from the fields, and `voicing_cost` takes that one value rather than
seven keywords. The recipe is in [docs/engine.md](docs/engine.md) §"Adding a ranking
criterion".

**Deleting one is the musical decision again.** The tuple used to carry an eighth element, a rank
over grip families. It went because it was the *same rule* as the order candidates are
generated in, written twice: they agreed, so neither was individually necessary. With the
families generated in the same order, deleting the criterion changed **0 of 799**
committed-head steps — tabs *and* grip labels — and **0 of 120** single-step sweeps; and
reversing `GRIP_PREFERENCE` with the rank left in changed nothing either, at 0/799 and
0/120. What the number does not say is the reason it is the right shape: no criterion
names a grip family because a family is not a property of a shape. Two families can
generate the very same tab, so at that depth the tuple would be choosing a *name* rather
than a sound; and a four-note drop-2 never reaches a tie with a shell to lose, because
criterion 2 separates them on note count. A tie now falls to generation order —
`top_strings` first, then `GRIP_PREFERENCE` within one string - and with the grip-family
axis deleted that order is the engine's rather than a caller's, so "most preferred first" is
a property of the table rather than of a request.
The two live cases that order decides are in [docs/engine.md](docs/engine.md)
§"Known limitations".

Likewise the 54 hardcoded tab strings in the tests stay: they are the acceptance
gate, and a snapshot mechanism would let a regression pass by regenerating itself.
over grip families. It went because it was the *same rule* as the order candidates are
generated in, written twice: they agreed, so neither was individually necessary. With the
families generated in the same order, deleting the criterion changed **0 of 799**
committed-head steps — tabs *and* grip labels — and **0 of 120** single-step sweeps; and
reversing `GRIP_PREFERENCE` with the rank left in changed nothing either, at 0/799 and
0/120. What the number does not say is the reason it is the right shape: no criterion
names a grip family because a family is not a property of a shape. Two families can
generate the very same tab, so at that depth the tuple would be choosing a *name* rather
than a sound; and a four-note drop-2 never reaches a tie with a shell to lose, because
criterion 2 separates them on note count. A tie now falls to generation order —
`top_strings` first, then `GRIP_PREFERENCE` within one string - and with the grip-family
axis deleted that order is the engine's rather than a caller's, so "most preferred first" is
a property of the table rather than of a request.
The two live cases that order decides are in [docs/engine.md](docs/engine.md)
§"Known limitations".

Likewise the 54 hardcoded tab strings in the tests stay: they are the acceptance
gate, and a snapshot mechanism would let a regression pass by regenerating itself.

## Contributing workflow

1. Read [docs/engine.md](docs/engine.md) or [docs/renderers.md](docs/renderers.md) —
   whichever the routing table sends you to — and the relevant test file.
2. Make the smallest change that satisfies the requirement.
3. Add or update tests in `tests/`, in the existing `unittest` style: one class per
   concern, descriptive `test_*` names, docstrings stating what is verified. **The
   filename is the half** — a test about the music is `test_*.py`, a test about the
   tree (module graph, budgets, seams, generated docs, fixtures, the explanation
   contract) is `meta_*.py`, and when in doubt it is `test_*.py`.
4. Run `make test-features` while iterating and `make check` from the repo root before
   committing. It must report `OK` for both halves.
5. Run `make demo` when you touched voicing or voice-leading logic, and read the
   printed tabs.
6. Commit each logical change separately. **Never `git push`** — this branch is the
   user's to push.
7. **When the context is running out, stop, write the handoff, and ask the user for a
   fresh session.** A long session banks what it has done, what is left, and **why each
   decision was made**, in a scratch handoff outside the tree, and then says that
   compaction would help rather than pressing on. As part of this repository's working
   rules, **the ask is expected rather than tolerated**: the user has said they want to be
   asked whenever the agent judges that a handoff would help, and will compact on request —
   so raise it early, at the first sign that the context is thinning, rather than at the
   point where it has already gone. **Write the state down before asking**, in the same
   turn as the question, so the compaction the question invites cannot lose the state the
   question was about. Asking costs one line; being late costs a re-litigated design,
   because a session running on a thinning context re-litigates settled decisions and
   reverts deliberate ones, which is what every trap below is made of.

## Adding a new chord quality

1. Add the quality's tones to `TONE_PRIORITY`, most defining first. **That row is the
   drop-2 rule** — `drop2_template_for` builds each shape from it and `_drop2_palette` is
   that rule read at every degree — so there is no list of interval numbers to write down.
   Its first two entries are the quality's `SHELL_DEGREES` pair, and the tail **ranks which
   tone a four-voice shape gives up** when the chord has more tones than voices — the nearer
   the end of the row, the sooner it goes, and the ranking is per-quality rather than one
   global order (`9` gives up its root where `maj7` gives up its natural 5th). An altered 5th
   is not a 5th: it ranks above the root. A name-given extension (the 9th of a `9`, the 13th
   of a `13`) is never the tone dropped. The shape itself is the close-position stack under
   the melody with its second voice lowered an octave, and a triad's fourth voice is the
   root doubled an octave below the stack.
2. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`. This is also
   what `drop3`, `closed`, `shell` and `duo` build themselves from, so it is required
   for the new grips to reach the quality at all. If the quality should also get a
   shell, add it to `SHELL_DEGREES` — the drop-2 rule and the derived grips work
   without one.
   `tests/test_generated_grips.py` holds the rule to the hand-written 119
   (`tests/support.py::WITNESS`), so **a new quality needs no table row of its own**; the
   measurements behind it are in [docs/history/generated-grips.md](docs/history/generated-grips.md).
   A quality with a priority row
   and a tone set needs nothing else, and one with a tone set but no row is offered no
   drop-2 shapes at all rather than a guess.
3. Add aliases to `ChordParser.QUALITY_ALIASES`.
4. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
5. **If a MusicXML file should be able to spell it**, add the matching
   `kind-value` to `MUSICXML_KIND_QUALITIES` in `headxml.py`, and any `<degree>`
   alteration that reaches it to `_DEGREE_REFINEMENTS`. The same rule applies: an
   absent kind resolves to `None` and is counted in `Head.unmapped`, so a new
   quality MusicXML cannot spell stays silent until this step is done. Note the
   table is keyed on the *library* quality, so a `kind` that only a `<degree>`
   reaches (a 7b5, say) needs a degree entry rather than a kind entry.
6. Add tests to `tests/test_voicings.py` for the drop-2 fingerings and to
   `tests/test_grips.py` for the other grips: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`, and the sounding strings
   a member of `supported_string_sets()`.
   `tests/test_voicings.py::TestQualityTableInvariants` checks the priority row is a
   permutation of the tone set, and `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route.
   `tests/test_headxml.py::TestChordParsing::test_every_kind_the_table_names_is_voiceable`
   is the same assertion for `MUSICXML_KIND_QUALITIES`.


## Traps

Each of these cost real time, or nearly shipped a defect.

1. **A gate that enumerates its inputs by hand silently skips whatever was added
   last.** The Makefile named each source file in three places, so `decisions.py` and
   `options.py` were unlinted and untypechecked until noticed.
   Lint and format now share one `MODULES` list; the package is named as a directory,
   so an engine module cannot be forgotten. A new *top-level* module is still a
   two-line change, in `MODULES` and in `typecheck`.

2. **`pyright` needs `--pythonpath`.** Run bare it reported **32 errors**, all
   `Import "musthe"/"music21"/"guitarpro" could not be resolved`, for packages that
   were installed and importing fine. A checker that cannot see the venv reports
   import failures that look exactly like type failures. `make typecheck` pins it.

3. **Do not run `ruff format` across the tree.** It rewrote 24 files and inflated
   `SHELL_DEGREES` from 10 lines to 31, one pair per line. Those tables are aligned
   so they can be scanned; one-per-line is 3× the space for the same information, in a
   refactor whose purpose is readability. `make format` is for a targeted file and is
   **not** part of `make check`.

4. **`ruff B010` and pyright can be mutually unsatisfiable.** Assigning a classmethod
   to satisfy pyright trips `B010`, which wants `setattr`; `setattr` trips pyright.
   Don't add a suppression — look for a seam worth extracting instead. That is how
   `wjazzd._corpus_options` came to exist.

5. **A test's premise can be invalidated by the refactor it exists to protect.** When
   a test fails because the structure it describes is gone, **invert the assertion —
   do not delete the test.** `test_both_loops_call_the_shared_decisions` asserted both
   step loops call each decision; Phase 4 made that false by design, and it now
   asserts the opposite (the engine calls them, and `slots` must contain none of it).

6. **When consolidating two branches, check whether their *outputs* differ before
   unifying their predicates.** `melody_alone_case` nearly shipped as a `bool`, and
   unifying the `NC` branch with the walking-bass branch on it would have annotated a
   step *"(no chord - melody alone)"* that claims to have a chord. The predicate
   returns a **kind** (`none` / `texture` / `nc`) for exactly this reason.

7. **A large mechanical move must copy text, not retype it.** Phase 5 moved 4290
   lines into the package by slicing the original *by line number*, so a docstring,
   a fret number or a comment provably cannot change in the move. Generate into a
   script you keep until the suite is green — a half-applied regeneration over a good
   tree is much harder to unpick than a wrong line is to find.

8. **A stale "before" measurement will invent differences that are not there.** When
   proving a refactor changed nothing, capture the fingerprint from the commit you
   think it is, not from a file that has been sitting in the tree since
   (`git worktree add /tmp/pre HEAD`). The capture itself is a throwaway script under
   `/tmp`, kept out of the repository: `tests/meta_step_loop_equivalence.py` is the
   standing check, and a measurement that only matters during one refactor has no
   business outliving it. (This trap used to have a corpus half — the gitignored
   database had to be copied across or the capture came back empty — and that half
   retired with the loader.)

9. **A count without a denominator is not a metre.** 2/2 and 2/4 are both two beats
   to the bar, and both readings of `4 / beat_type` agree in 4/4 — so the whole suite
   passed while the file was unusable for every other metre. That is why `Head`
   carries `beat_type` and it is plumbed to the file headers, and why the check that
   catches it sums each measure's durations rather than counting measures. **The
   importer then shipped the bug that fix was about**: `beat_type` was read and
   plumbed to the four *renderers*, while the importer's own onset conversion still
   used the count — so every note of the one committed 3/4 head was placed 25% early,
   its exported bars came out short, and `--musicxml` scaled every onset by another
   0.75 per round trip. Most of the committed heads are 4/4 or 2/2, where the two spellings
   are the same number, and the only test that read the odd one out derived its
   expectation from those same beats. Measured and fixed; the denominator now reaches
   the engine's arithmetic too (`headxml._beat_from_onset`, `bass._melody_timeline`).

10. **An omitted attribute is not an identity — and a default that is wrong is
    silent.** The exporter wrote no `<key>`, so every score left the library was in C
   major whatever it was in; the importer read `<time>` and not `<key>`, so the head
   arrived with nothing to write. Nothing errored, because a missing key signature is
   *legal* and means C major. It cost 201 accidentals on a 32-bar Eb head against 27.
   Two things made it cost that much rather than 155, and both were found by
   measuring rather than reading:
   - **`<harmony>` symbols mark notes through a channel the document does not use.**
     `writeAsChord = False` means the symbol's pitches are never written, yet they
     stay in the stream and music21 still counts them when deciding which notes need
     an `<accidental>`: 139 against 27 for the same music. Cleared in `_chord_symbol`.
   - **Never grep a document with a single-line pattern for a multi-line element.**
     `<key>.*?</key>` without `re.S` reports *no key* on a document that has one,
     which is exactly the shape of the bug being chased. That cost an hour of
     "music21 does not emit `<key>`" — a conclusion drawn from a regex that could not
     match. `re.findall(pattern, text, re.S)`, always.

11. **The dev interpreter is not the matrix.** `gp.KeySignature(-3, 0)` looks like a
    value lookup and is one on Python 3.12+, where `EnumType.__call__` reads a tuple in
    the `names` position as member values to match. On **3.11** the same call is the
    *functional* enum API — "define a new class" — and raises `TypeError: <enum 0>
    cannot extend <enum 'KeySignature'>` before any lookup happens. It passed on the
    3.14 dev box and on every 3.12+ runner, and failed only on the 3.11 CI job, on the
    first test that asked for a key. `_key_signature` now scans the members and compares
    `.value`, which is the same lookup written out and behaves identically everywhere.
    The general form: **a two-argument `Enum(...)` is not a value lookup, it is class
    definition**, and `make check` cannot catch this because it runs one version.
    Anything version-sensitive has to be exercised on each version CI runs.
12. **A new guard clause is not a new route — and moving one can break the case it
    did not name.** Asking `decisions.melody_alone_case` what a slot the chord's rhythm
    does not name should do (`on_grid=False`) gave an answer that differs by route: with the guitar
    singing the note sounds alone, with it comping the guitar is *silent*. That is a
    fourth *kind*, `MELODY_ALONE_REST`, not a flag — a bool could not express both,
    which is trap 6's shape arriving again from a new direction.

    The ordering of that function's three guards is what cost the time — 12 tests over
    two attempts, because each ordering fixes one route and breaks the other:

    - placing the rhythm test **after** the `melody_voiced` guard makes the chord's rhythm
      **silently inert on the comping route**: measured, all four patterns returned
      80/80 comps, byte-identical to the default, with nothing said anywhere;
    - hoisting the `NO_CHORD` test **above** that guard lets an `NC` bar reach the
      comping route, where the caller emits a rest step that says why; it instead
      survived as a voiced step — `['Dm7', 'NC', 'A7']` where it had been `['Dm7', 'A7']`;
    - fixing that by returning `NONE` for `NC` everywhere breaks the **singing**
      route, which needs `MELODY_ALONE_NO_CHORD`; the note then found no voicing and
      vanished, taking **11 tests across four files**, every one of them `NC`.

    The general form: **before reordering a decision function's guards, ask what each
    guard is load-bearing *for*, and then check the two routes separately.** Both
    routes build different steps from one function — which is the whole reason it
    returns a kind — so an ordering right for one is not thereby right for the other.
    An `NC` bar is also what proves "a slot the rhythm does not name" is not universal:
    it has *no chord to place*, so "silent here" and "no chord here" are different
    claims, and only the first is a rest.
13. **An invariant asserted on a voicing says nothing about a step the engine builds
    *after* the check.** The merge is deliberately after selection — "the bass is written
    into the fret vector only once `best_voicing` has returned, so it cannot enter the
    cost tuple by construction" — and every `supported_string_sets()` assertion in the
    suite is on a generated *voicing*. So a four-note target plus a thumb note was five
    strings, four fingers be damned, on **281 steps** of the committed heads under
    `--texture targets --bass-style root,5th,approach,nearest|root`, and no test could see it.
    `tests/test_walking_bass.py::TestTheInvariant` *had* amended the rule for a
    bass-carrying step, and amended it correctly for the texture it was written for (a
    `walking_bass` target is a shell, so three strings plus a thumb is four) — the
    amendment was right and the palette was wrong. **The general form: when a rule is
    stated over a part of a whole, ask which producer can make the other part larger than
    the rule assumed, and assert the rule on the whole.** A count is the way to do it: the
    step count that catches this is "strings plucked at once", not "strings in the shape".

14. **An option that takes a *list* spells it the way the flags around it do — and
    `nargs` is not that spelling.** `--grips` carried `nargs="+"` with
    `choices=GRIP_PREFERENCE` while `--voices`, in the same parser, took a
    comma-separated string — so `--grips closed,shell` was refused
    (`invalid choice: 'closed,shell'`) *by a flag whose own run header prints the request
    back as `grips: closed, shell`*: the line a reader copies was the one spelling that
    did not work. The second half is silent until it is tried. `nargs="+"` consumes the
    positional written after it, so `head --grips shell FILE` fed the **filename** to
    `--grips` and reported `invalid choice: 'tests/data/...'` — the flag worked only
    after the file. Every list-valued option is one comma-separated string now, parsed by
    the module that owns the vocabulary - `parts.parse_parts` for `--parts` - so
    `head --chord-on 1,2and FILE` and `head FILE --chord-on 1,2and` are one run — and that
    spelling is the one **the run header prints back** (`chord-on=1,2and`), so the line a
    reader copies is the line the parser accepts.
    **Two things to carry forward: a list-valued option is one string the module that
    owns the vocabulary parses, never `nargs`; and a parser's own output is
    documentation — if the run header prints a spelling, that spelling has to be
    accepted** (the round trip is asserted). The spelling is also chosen to be
    **argv-safe**: the midpoint of a felt beat is `1and`, never `1&`, because an
    unquoted `&` is a shell's background operator and the token would never reach the
    parser — so the line the header prints is also a line a shell will deliver. Note a
    *selection* is canonicalised and a
    *sequence* is not: `parse_parts` re-sorts into `PART_NAMES` order because a parts
    selection is a set, while `--chord-on`'s positions are sorted because they are also
    a set — and the grip order that must not have been canonicalised was a spelling of
    the deleted family axis.

15. **A parameter removed from the middle of a signature silently shifts every
    positional call.** `arrange_progression` took `diagnostics` at position 12 and
    `steps.arrange_progression` forwarded to it positionally, ending at `options` -
    so deleting the parameter left `options` landing in `grid`, and every bare
    `arrange_progression(prog)` call died three frames later in
    `parse_grid(None).strip()`. **266 test errors from one line**, and the traceback
    named a function that had not been touched. The same edit then deleted three
    *whole argument lines* (`role, texture, texture_grips, grips, diagnostics,` and two
    `role=role, weight=weight, diagnostics=diagnostics,`) because the strip matched
    them as text rather than as syntax - trap 7's shape arriving from a new direction.

    The general form: **a mechanical parameter removal is an AST edit, not a text
    edit**, and a facade forwarding positionally is what turns it from a type error
    into a silent mis-bind. Two things follow. Name every argument at a facade
    boundary - `steps.arrange_progression` now spells all fifteen and passes
    `options=options` as the only keyword. And when a strip script reports "lines
    removed", read the `git diff`'s removed lines rather than counting them: all four
    casualties above were visible there before any test ran.

16. **A number a document states has no test, so it rots where it is least likely to be
    re-measured.** The issue ledger states each item **with its measurement** — that is what
    makes an item an issue rather than a complaint — and three separate commits moved those
    measurements without touching a word of the prose beside them: deleting the `Diagnostics`
    collector left six documents describing a warning that phrases a choice, when the phrasing
    had moved onto the tab line; playing the repeats (`6cdcbaa`) lengthened every head, so item
    1's "57 steps" was **87** and the `comps+freddie` triple moved with it; and `bass_refused`
    counting every refused thumb where the old warning counted one call site took item 2 from
    **39** to **161**. `make check` was green through all of it, because the doc checker
    that existed then compared only a document's *version*, *module count* and *links* — and
    nothing checked a count. That ledger is retired with all six items closed (its record is
    [docs/history/open-issues.md](docs/history/open-issues.md)) and a new issue is filed in
    [docs/open-issues.md](docs/open-issues.md), the same way: a figure with a recipe.

    Two things follow, though neither is enforced by the gate now. **A figure repeated in
    two documents is a second source for one fact** — AGENTS.md's own `step.bass` rule — so the
    routing rows here *point* at the document that owns a number instead of restating it; the four
    counts that lived in three places at once are what made this rot invisible. And **a stated
    figure gets a recipe**: the ledger carries the snippet that takes each of its
    numbers, so the figure is re-measurable without the suite. That re-measurement is **by hand**:
    the module that once compared the document's numbers with the tree was cut back to the
    *behaviour* those items describe, and has since been removed with the rest of the
    documentation tests, because re-taking a document's own prose from the tree is a check that
    regenerates its own expectation — the one thing the pinned tabs in the rest of the suite
    exist to avoid. A number in that document can therefore move without the gate failing,
    which is the cost of that choice and is stated where the numbers live.

    The same clean-up found an **unclosed code fence** in that file, which had rendered its
    entire tail as a shell script for four commits, so the doc checker that existed then
    counted fences too. The general form of both: **a document is code that nothing compiles,
    so the parts of it that *can* be checked mechanically must be** — and a number, a fence
    and a link are all of that.

## Where things are documented

| document | what it holds |
|---|---|
| [README.md](README.md) | user-facing overview, worked examples, limitations |
| [docs/engine.md](docs/engine.md) | the engine: grips, the selector, the cost tuple, the axes (`ArrangeOptions(parts=…)`, `texture`, `bass`, and `TimeSignature`), the chord's rhythm, non-chord tones, and the recipe for adding a chord quality |
| [docs/renderers.md](docs/renderers.md) | tab staff, MusicXML import/export, GP5, and their traps |
| [docs/dependency-dag.md](docs/dependency-dag.md) | the enforced import graphs, drawn: the engine package's layers and their main dependencies, and the front ends' recorded edges |
| [docs/open-issues.md](docs/open-issues.md) | the issue ledger: **none is open**, and the six it filed are indexed here by number; a new issue is filed here as **issue / problem / why it exists** with its measurement and the recipe that re-measures it |
| [docs/history/open-issues.md](docs/history/open-issues.md) | the retired ledger: the record of those six, each with the measurement that closed it, stated **once** and re-measurable by hand from the recipe beside it |
| [docs/history/](docs/history/) | the retired documents - the completed plans (corpus, walking bass, texture, arranging guide, `voices=`, the Stage-2 collapse, parts, generated grips, comping styles, fingering, restructuring, the rhythm-first request, the architecture review), the retired reharmonisation proposals, and the retired issue ledger. A plan that landed whole carries a header saying where its live rules went: `docs/engine.md` |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | what CI runs, and which tests it does *not* run |

`common_grips.md` is generated from the engine's own tables by `grip_chart.py` and
checked by `make chart-audit` — never edit it by hand.




```bash
make demo                            # the built-in demonstration arrangements
.venv/bin/python -m arranger         # the same thing, without make
.venv/bin/jazz-arranger              # the console script, once installed
```

`main()` also dispatches one subcommand, imported lazily inside the branch so
`import arranger` does not pull in the importer - nor, through it, the renderers it
uses - for a caller who only wants the library:

```bash
.venv/bin/python -m arranger head FILE.musicxml    # the MusicXML importer
```

`make build` wraps `pip wheel . -w dist --no-deps`; no `build` package is required.

Run everything **from the repository root**; the tests import `arranger` from the tree
and need no install.

