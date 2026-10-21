> **Retired: implemented in full.** This was the plan for the rhythm-first request, and
> every stage of it landed - the notes under each stage say what landed and where it
> differed. Its **live half** is now stated elsewhere and this document is the record:
> the flags are [README.md](../../README.md), the request-to-axes mapping and the engine's
> reasoning are [docs/engine.md](../engine.md) §"The request, and the six axes under it",
> and the four renderers' agreement is [docs/renderers.md](../renderers.md) §"What the
> four renderers must agree about". Where this document and those disagree, they are
> right: it was written first.

# The arrangement request: a rhythm-first redesign

**Status: implemented**, one commit per stage with `make check` green. The notes under
each stage record what landed and where it differed from the plan.

**Progress: every stage has landed.** Stage 0 is the `Rhythm` grammar; Stage 1 is the
`Request` value, `resolve_request`, the CLI flags and the run header; Stage 2 is the
slot union; Stage 2b is `--chord-fills`, the chord's policy in a notated melody rest;
Stage 3 is the bass line at the requested positions; Stage 4 is the bass-only route;
Stage 5 is a stab's length and the carried thumb; Stage 6 is the staff's moved thumb;
Stage 7 is `--no-melody` as a complete request; Stage 8 is the documentation, and it
closed open-issues items 1 and 4.

`arranger head` offers `--no-melody`, `--chord-on`, `--chord-notes`, `--chord-fills`,
`--bass-on` and `--bass-notes`, and the five old flags are gone; the staff flag is
`--note-names`. The internal axes remain in the **Python API** as the engine's
implementation - design principle 9 - and no CLI flag spells one.

What that means for the rest of this document: `head FILE` adds nothing - one chord
per written melody note and no position invented in the tune's rests. `--chord-on
POSITIONS` both **thins** the harmonisation where a slot is off the grid and **adds**
an attack at its positions, under a held note included. `--chord-fills hold|comp`
states the written harmony where the tune is *silent*: one chord per rest, or one per
felt beat inside it, split at a chord change and at a target, with the fill stopping
at the rest's end. A rest under `NC` gets nothing, `--no-melody` refuses the flag, and
a file with no melody notes is answered as a chord chart (rhythm `every-beat`, the
substitution reported in the loader's notes).

Stage 3 is the bass at the requested positions: `bass_on` reaches the line as a
rhythm, the first position of a bar is the anchor (not the downbeat, which a sparse
rhythm may not name), the last position of a bar is what an approach is measured
against, and `root`/`root-5th` state a note at **every** requested position - the
root as an `anchor` where it marks the bar and a `pedal` elsewhere, the 5th as
`fifth` when the style alternates. The `bass=` axis keeps its anchors-only meaning
until Stage 8 retires it.

Stage 4 is the bass part's own slots: a position the chord part leaves - a rhythm
that does not name it, or a selection with no chord part - is played as the thumb
alone when the guitar has no melody to sing there, instead of being a rest. A shape
still ringing is held under it; nothing ringing and the line says "the thumb alone".

Stage 5 is when a request's rhythms become **lengths**: a chord attack rings its felt
beat and no further, and a thumb note rings until something replaces it - carried into
the steps that follow as `bass_held`, so the tab, the staff, the score and the GP5 file
all say the string sounds without being plucked.

Stage 6 fixed a renderer's outlier: a **held column whose thumb moves** is a hold for the
shape and a new attack for the bass, and the ASCII staff and the HTML drew neither.

Stage 7 made `--no-melody` a complete request - the chord defaults to the metre's felt
beats - and measured the lone bass line across five metres, which found two renderers
that had been folding a repeated thumb into a hold.

Stage 8 landed as documentation plus one consequence in code: the phrase a reader sees at
a position nobody asked to sound now names the **request** rather than "the grid", because
the flag that exposed a grid is gone. The rest of that stage's list - the README's axis
sections, `docs/engine.md`'s request table, `docs/renderers.md`'s four-renderer rule and
open-issues items 1 and 4 - is written, and each command the README prints was re-run.

## The problem in one paragraph

`head FILE` should mean "harmonise the melody notes and add no other rhythm".
Today it very nearly does, but the flags that add rhythm are five overlapping
vocabularies (`--parts`, `--texture`, `--harmony`, `--bass-style`, `--grid`),
and there is no clean way to ask for the two things a player actually says:

- "play the melody, but add a bass note on every downbeat";
- "play the melody, but add a chord stab on the and of 1".

The closest spellings today are `--grid chord:joe_pass` (a stab on **every**
offbeat), `--grid chord:charleston` (beat 1 and the and of 2) or
`--parts melody,bass --bass-style root` (a bass note only where the harmony
anchors). None of them says "the and of 1", and two of the five flags are inert
exactly where a reader expects them to work.

## What is confusing today

| flag | sounds like it says | what it actually does |
|---|---|---|
| `--parts` | which layers play | `melody,bass` **removes the chord**; `auto` names the bass part while `bass=auto` writes no line; a policy named for a part the selection drops is refused |
| `--texture` | how thick the chord part is | also a **rhythm**: `targets` = a full chord on the bar's first and third felt beats, a thinner shape or the melody alone between |
| `--harmony` | which degrees the chord states | read only on the **comping** route. On a melody-bearing arrangement it is inert: `--harmony guide` is byte-identical to the default full 4-voice chord |
| `--bass-style` | which bass notes sound | also a **rhythm**: `root` only sounds on anchor beats; the full list walks every beat |
| `--grid` | when each part sounds | fixed `PART:PATTERN` presets, no direct positions; the `bass:` rows have no reader: `--grid melody:every_note,bass:walk` is byte-identical to the default |

Measured on `examples/But_Not_for_Me.mxl`:

```bash
.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3
# one full 4-voice chord under each melody note:
#   Bb Root, Ab b7, D 3, F 5

.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-2 --harmony guide
# identical to the default: the flag did nothing

.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3 \
  --grid melody:every_note,bass:walk
# identical to the default: the bass row did nothing

.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3 \
  --grid chord:joe_pass
# melody notes elsewhere alone; one chord stab on *every* offbeat

.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-2 \
  --texture targets
# header: "a full chord on beat 1 of 2/2, a shell, a 3rd/6th or the melody
# alone elsewhere" - a rhythm and an arity in one value
```

There is a second, narrower bug behind the same complaint: with
`--parts bass,melody`, the engine arranges the bass note at the downbeat but the
ASCII staff and the HTML page drop it, because their hold rule compares only the
upper voices. The MusicXML score already contains it. That is a renderer defect,
not a reason to keep the old vocabulary; it is Stage 6 below so it is not lost.

## Design principles

1. **One flag, one question.** A flag may own a rhythm, a content choice, or a
   policy for a span the melody leaves silent, but never two of them. A flag that
   cannot affect the current route is not offered.
2. **The melody's rhythm is data.** The guitar plays the written tune on its
   written rhythm. Nothing quantises it.
3. **Rhythm and content are orthogonal.** "When a layer attacks" is separate from
   "which notes it states".
4. **The default adds nothing.** `head FILE` is the melody plus one chord per
   melody onset. No bass, no extra attacks, no chords invented in rests unless
   `--chord-fills` asks for them.
5. **Direct positions, in musical language.** `1&` is a position; `joe_pass` is a
   preset that happens to contain it.
6. **Bar-relative and metre-aware.** Positions are felt beats, so `1` is the
   downbeat in every metre and `1,3` names the first and third felt beats where a
   third exists; `every-beat` follows the grouping.
7. **Capacity is arithmetic.** Melody + bass + chord is at most four right-hand
   strings (`p-i-m-a`). "Full" means the most that fits, not an impossible ask.
8. **No inert flags.** If a value cannot reach the route it names, the request is
   refused with a reason rather than silently ignored.
9. **A public request, internal axes.** `parts`, `texture`, `harmony`, `bass` and
   the grid remain the engine's resolved implementation; the user-facing
   vocabulary is the questions below.
10. **Every renderer agrees.** A note in the arrangement is in the one-line tab,
    the staff, the HTML, MusicXML and GP5, or the arrangement does not contain
    it.

## Options considered

### A. Per-layer flags with direct positions (recommended)

```text
--no-melody
--chord-on POSITIONS
--bass-on POSITIONS
--chord-notes {full,3,2,1}
--bass-notes {root,root-5th,walk}
--chord-fills {none,hold,comp}   # optional; default none
```

Each accompaniment layer has a rhythm flag and a content flag, plus one
**rest policy** for the chord layer: what the chord states when the melody has a
notated rest. The rhythm grammar includes `melody`, `none`, `every-beat` and
direct positions such as `1&`. A list replaces the default token; `melody` may be
combined with positions to keep the harmonisation and add an attack.

- **Pros:** one question per flag; expresses "the and of 1" directly; keeps the
  walking bass and the chord arity available; the melody is the default, so the
  common case is short; the old five flags disappear.
- **Cons:** five core flags plus the optional rest policy; a small grammar to
  learn; the bass line, rest detection and slot union need real work; many tests
  and docs change.
- **Best for:** this project. The extra grammar is the position tokens and one
  rest policy, and it replaces five vocabularies.

### B. Rhythm flags only; content fixed

```text
--no-melody
--chord-on POSITIONS
--bass-on POSITIONS
# chord always the fullest that fits; bass always the root
```

- **Pros:** the fewest flags; the simplest help.
- **Cons:** no walking bass (`root` on every beat is a pedal, not a line); no way
  to thin the chord; the content defaults are invisible and cannot be changed
  without a second release. A player who wants a walk has to wait.
- **Best for:** a minimal first cut, if the content axis can wait. It is a
  subset of option A, not a different model.

### C. One combined accompaniment string

```text
--comp "chord:melody,1&,bass:1"
```

- **Pros:** one flag for the whole accompaniment; compact once learned.
- **Cons:** a new DSL; the help has to explain a rhythm grammar and a content
  grammar in one string; error messages point at a substring; discovery is poor.
  It is the current `--grid` mistake with better positions.
- **Best for:** a caller who already knows the grammar. Not for a lead-sheet CLI
  whose main job is to be readable.

### D. Keep the current five flags, add positions to `--grid`

```text
--grid "chord:1&,bass:1"
```

- **Pros:** least code churn; existing tests mostly survive.
- **Cons:** the five flags still overlap; `--harmony` is still inert when the
  guitar sings; `--bass-style root` still means "anchor beats only"; `--parts`
  and `--bass-style` still disagree about whether a bass exists; the user still
  has to learn `parts`, `texture`, `harmony`, `bass-style` and `grid` to say two
  simple things.
- **Best for:** preserving compatibility. Backwards compatibility is explicitly
  not a concern for this redesign.

### E. Named presets only

```text
--comp freddie
--comp charleston
--comp "chord on the and of 1"
```

- **Pros:** no position grammar; the names are musical.
- **Cons:** every new request is a new name; "the and of 1" is not a standard
  preset; the set grows without bound. It cannot express the motivating example
  without inventing a name for it.
- **Best for:** a fixed library of styles, not a general request.

### Comparison

| | flags | direct positions | content control | melody default | old vocabulary gone | implementation cost |
|---|---|---|---|---|---|---|
| **A. Per-layer + positions** | 5 (+1 optional) | yes | yes | yes | yes | high |
| B. Rhythm only | 3 | yes | fixed | yes | yes | high (engine), low (CLI) |
| C. One string | 1 | yes | via grammar | yes | yes | high + DSL |
| D. Keep five, extend grid | 5 | yes | yes | yes | no | medium |
| E. Presets only | 1 | no | no | yes | yes | low |

**Recommendation: A.** It is the only option that answers the questions
separately while keeping the walk, the chord arity and the rest policy
available. B is A with the content flags hidden; it can be the first
implementation slice if the content axis is deferred. C and D preserve the
confusion in a new spelling. E cannot express the motivating example.

## The recommended model

### Three questions, plus the chord's rest policy

1. **Who plays the tune?** The guitar does by default; `--no-melody` hands it to
   the horn and leaves the chord/bass layers as a comping part.
2. **When does each accompaniment layer attack?** `--chord-on POSITIONS`,
   `--bass-on POSITIONS`.
3. **What does each layer state?** `--chord-notes full|3|2|1`,
   `--bass-notes root|root-5th|walk`.
4. **What does the chord do when the melody rests?**
   `--chord-fills none|hold|comp`. This is not another layer: it is the chord
   part's policy in a **notated melody rest**. The bass is already defined by
   `--bass-on` and is not affected.

### Position grammar

Bar-relative, in **felt beats**:

| token | meaning |
|---|---|
| `melody` | at every written melody onset; the chord default |
| `none` | the layer is absent |
| `every-beat` | the start of every felt beat: 2 per bar in 2/2, 4 in 4/4, 3 in 3/4, 2 in 6/8 |
| `1`, `2`, `3`, `4` | that felt beat |
| `1&` | halfway through felt beat 1 — "the and of 1" |
| `1e`, `1a` | a quarter / three-quarters through felt beat 1 |
| `last`, `last&` | the last felt beat, and its offbeat |
| `melody,1&` | the melody-note harmonisation **plus** a stab |

Rules:

- A list **replaces** the default token. `--chord-on 1&` is only the stab;
  `--chord-on melody,1&` keeps the harmonisation and adds the stab.
- `none` cannot be combined with another token.
- A position the metre does not have is **refused** (`beat 3` in 2/2), not
  silently dropped.
- `&` is the midpoint of the felt beat: a quarter-note offbeat in 2/2, an
  eighth-note offbeat in 4/4, and the midpoint of a dotted-quarter pulse in 6/8.
  `e`/`a` are the quarter and three-quarter points.
- `every-beat` and `last` resolve against the metre's grouping, not the
  denominator count.
- The canonical spelling is printed in the run header and must parse back (the
  repository's existing round-trip rule).

### Defaults and content

- `--chord-on melody`: one chord per written melody onset, as long as that
  melody note. No extra attacks; a melody rest stays silent unless
  `--chord-fills` asks otherwise.
- `--bass-on none`: no bass.
- `--chord-fills none`: no chord in a notated melody rest. This is the default
  and preserves "harmonise the melody notes and add nothing else."
- `--chord-notes full`: the most chord notes the right hand can fit. With a bass
  present this is two chord notes under the melody, because
  melody + bass + chord <= four strings.
- `--bass-notes root`: the root at each requested bass position. `root-5th`
  alternates the root and fifth; `walk` uses the anchor/connect/approach rules.
- `--no-melody` defaults `--chord-on every-beat` (four-to-the-bar comping). An
  explicit `--chord-on melody` with `--no-melody` is refused: there is no
  melody to attach chords to.
- `--no-melody --chord-on none --bass-on every-beat` is the lone-bass selection.
- `--no-melody` refuses `--chord-fills`: the guitar is not playing the melody,
  so it has no melody rests to fill.
- `--chord-on none --chord-fills hold` is valid: the chord part exists only in
  the rests.
- The staff flag `--melody` ("show note names") is renamed `--note-names`, so
  `--no-melody` has exactly one meaning.

### Semantics

- **Default adds nothing.** The arrangement starts as the melody skeleton: one
  slot per written note, one chord under each. The old union of chord positions
  into melody rests is gone; only `--chord-on` positions and `--chord-fills`
  add a chord where the melody is silent.
- **An explicit position with no melody** sounds the layer alone; no melody is
  invented. If the melody is held through it, the layer attacks under the held
  note.
- **A notated melody rest is the one place `--chord-fills` acts.** It applies to
  the chord part only; the bass is `--bass-on`.
  - `none`: the guitar rests with the tune.
  - `hold`: one chord at the rest onset, stating the written harmony, held to
    the end of the rest. Split at a chord change or a `--chord-on` target.
  - `comp`: a chord at the rest onset and each felt beat inside the rest,
    lasting to the next fill/target/chord change or the rest end.
  A target from `--chord-on` always attacks; a fill only covers the rest of the
  time, and the two deduplicate to one step where they coincide.
- **Durations** (proposed; see the open decisions):
  - chord under a melody onset: the melody note's duration;
  - a `--chord-on` target with no melody onset: a short stab to the end of the
    felt beat it starts in (`1&` = half a beat, `1` = one beat);
  - a `--chord-fills hold`/`comp`: the rest segment / next attack, as above;
  - bass: rings to the next bass attack or the bar line, carried under
    intervening melody steps so the score can tie it.
- **Capacity:** melody + bass + chord is at most four right-hand strings.
  `--chord-notes full` means "the most that fits"; with a bass that is two chord
  notes under the melody. A four-note chord plus a bass is impossible and the
  request is refused rather than silently losing a voice.
- **The note rules choose the pitch; the rhythm chooses whether a note sounds.**
  This is the important separation. Today `bass-style root` means "root only on
  anchor beats", so `--bass-on every-beat --bass-notes root` would not do what
  it says. In the new model it does: the root on every requested beat (a pedal).
  A new `pedal` role names a root on a non-anchor position.
- **Comping mode** (`--no-melody`): the chord rhythm defaults to `every-beat`;
  off-chord positions rest; a lone bass line is
  `--no-melody --chord-on none --bass-on every-beat`.
- **Named presets** are not public. `freddie`, `charleston`, `joe_pass` and
  `final_and` are spellings of positions (`every-beat`, `1,2&`,
  `1&,2&,3&,4&`, `last&`). The internal engine may keep their tables for tests,
  but the CLI does not expose them.

### Examples

```bash
# default: melody + the full chord under each melody note, nothing added
python -m arranger head examples/But_Not_for_Me.mxl

# melody + a bass note on each bar's first felt beat
python -m arranger head examples/But_Not_for_Me.mxl --bass-on 1

# melody + a note on every felt beat (2 attacks/bar in this 2/2 head)
python -m arranger head examples/But_Not_for_Me.mxl --bass-on every-beat

# melody + a walking line on those beats
python -m arranger head examples/But_Not_for_Me.mxl \
  --bass-on every-beat --bass-notes walk

# melody + a chord stab on the and of 1; other melody notes alone
python -m arranger head examples/But_Not_for_Me.mxl --chord-on 1&

# melody + the harmonisation AND the stab
python -m arranger head examples/But_Not_for_Me.mxl --chord-on melody,1&

# melody alone
python -m arranger head examples/But_Not_for_Me.mxl --chord-on none

# melody alone; when it rests, hold the written chord
python -m arranger head examples/But_Not_for_Me.mxl \
  --chord-on none --chord-fills hold

# melody harmonised; comp through long rests on each felt beat
python -m arranger head examples/But_Not_for_Me.mxl \
  --chord-on melody --chord-fills comp

# no melody: comp for a horn (2 attacks/bar in this 2/2 head)
python -m arranger head examples/But_Not_for_Me.mxl \
  --no-melody --chord-on every-beat
```

The bass is independent: add `--bass-on every-beat --bass-notes walk` to any of
these and it sounds through the rests as well.

### Old to new

| today | new |
|---|---|
| `--parts melody` | `--chord-on none` |
| `--parts melody,bass` | `--chord-on none --bass-on every-beat --bass-notes walk` |
| `--parts chord` | `--no-melody --chord-on every-beat` |
| `--parts bass` | `--no-melody --chord-on none --bass-on every-beat` |
| `--texture uniform` / `chord2` | `--chord-notes full` / `2` |
| `--texture targets` | `--chord-on 1,3` in 4/4 (or `1` in 2/2) for the rhythm; the "thin fills between" half is not carried over |
| `--harmony guide` | not public; the internal default is full under the melody, guide when comping |
| `--bass-style root` | `--bass-on 1 --bass-notes root` (or any requested positions) |
| `--bass-style root,5th,approach,nearest` | `--bass-on every-beat --bass-notes walk` |
| `--grid chord:freddie` | `--chord-on every-beat` |
| `--grid chord:charleston` | `--chord-on 1,2&` |
| `--grid chord:joe_pass` | `--chord-on 1&,2&,3&,4&` in 4/4 (or `1&,2&` in 2/2) |
| `--grid chord:final_and` | `--chord-on last&` |
| `--grid bass:walk` | `--bass-on every-beat --bass-notes walk` |
| *(new feature)* | `--chord-fills none, hold or comp` — the chord's policy in a notated melody rest; no old equivalent |

`texture=targets` is the one casualty. Its rhythm is expressible as
`--chord-on 1,3` in 4/4 (or `1` in 2/2); its automatic thinning between targets
is a separate future `--chord-between`, **not** `--chord-fills`. `--chord-fills`
is new: it is about the chord in a **notated melody rest**, not about a thin
chord under a melody note.

## Architecture

The engine's internal axes are the right implementation; the public vocabulary is
the problem. The plan keeps `parts`, `texture`, `harmony`, `bass` and the grid
machinery behind `resolution._Policies`, and puts a clean request in front.

### New `Rhythm` value

In `arranger/grid.py` (keeping the module avoids a package-DAG change):

```python
@dataclass(frozen=True)
class Rhythm:
    melody: bool = False
    positions: Tuple[float, ...] = ()   # felt-beat numbers within the bar
    none: bool = False
```

- `parse_rhythm(text, beats_per_bar, grouping) -> Rhythm`
- `Rhythm.includes(beat, beats_per_bar, grouping) -> bool`
- `Rhythm.wants_melody`, `Rhythm.is_none`, canonical `str()` for the run header.
- The parser expands `every-beat`, resolves `last`/`last&`, computes `&`/`e`/`a`
  from `group_starts`/`grouping`, and refuses a position the metre lacks.

This replaces the public `grid` string. The old `GRID_STYLES`/`GRID_PATTERNS`
may stay for internal tests, but `parse_grid`/`on_grid` are rewritten around
`Rhythm`.

### Request to policies

`ArrangeOptions` becomes:

```python
melody: bool = True
chord_on: str = "melody"
chord_notes: str = "full"
bass_on: str = "none"
bass_notes: str = "root"
chord_fills: str = "none"
```

`resolution._Policies` derives:

| internal | from |
|---|---|
| `parts` | `melody`, `chord_on != none or chord_fills != none`, `bass_on != none` |
| `texture` | `full` -> `uniform`; `3/2/1` -> `chord3/2/1` |
| `harmony` | `HARMONY_AUTO`: full when the melody is the guitar's, guide when comping |
| `bass` | `root` -> `root`; `root-5th` -> `root,5th`; `walk` -> all four rules |
| chord rhythm | parsed `chord_on` |
| bass rhythm | parsed `bass_on` |
| rest fill | `chord_fills` (`none`/`hold`/`comp`) |

Refusals happen before any voicing work: a content flag on an absent part, an
unknown position, `--no-melody --chord-on melody`, `--no-melody --chord-fills`
anything but `none`, and an empty selection.

### Rest fills

`--chord-fills` needs a melody-rest timeline, which only the head layer has:

- `headxml.melody_rests(head, section)` computes the gaps between the melody's
  sounding notes, plus the section start/end. A held note is not a rest. Each
  rest is split at chord changes and at `--chord-on` targets; a bar line is not
  a musical split (a renderer may split the step there and tie it).
- For `hold`, one fill slot per rest segment at the rest onset.
- For `comp`, a fill slot at the rest onset and at each felt beat inside the
  segment.
- Each fill slot carries `melody=None`, the chord in force, and the segment
  duration. It is unioned with the melody skeleton and the `--chord-on` slots,
  deduplicated on `(bar, beat)`. A `--chord-on` target wins a collision; the fill
  continues after it.
- The route is the existing comping route: `melody=None`, `chord_here=True`, so
  `comping_step` states the chord. No new voicing path is needed.
- The fill uses `comping_arity` because the melody string is free; `--chord-notes`
  caps it. `--bass-on` unions independently; a coincident bass note merges into
  the same step, subject to the four-string capacity.
- The annotation must say why the chord is there: the tune rests and the chord
  fills. `tests/test_explanations.py` gets a witness for that decision.
- `--chord-on none --chord-fills hold` keeps the chord part alive only for the
  fills. `--no-melody` refuses `--chord-fills`; an `NC` rest has no chord to
  state.

## Implementation stages

Each stage is a commit-sized slice with `make check` green at the end. The order
is chosen so the parser and the public request land before the slot and bass
behaviour changes.

### Stage 0: `Rhythm` value and parser

- `arranger/grid.py`: `Rhythm`, `parse_rhythm`, `includes`, canonical spelling.
- Tests for 4/4, 2/2, 3/4 and 6/8; `1&`, `last&`, `every-beat`, invalid
  positions, `none` combined with a position, `melody,1&`, round-trip.
- No behaviour change yet.

### Stage 1: request and CLI

- `ArrangeOptions`: replace `texture`, `parts`, `harmony`, `bass`, `grid` with
  `melody`, `chord_on`, `chord_notes`, `bass_on`, `bass_notes`, `chord_fills`.
- `resolution._Policies`: derive the internal values (the table above).
- `headxml.arrange_xml_head`, `movement.arrange_progression`,
  `steps.VoiceLeadingEngine.arrange_progression`: new keywords.
- `cli.py`: add `--no-melody`, `--chord-on`, `--chord-notes`, `--bass-on`,
  `--bass-notes`, `--chord-fills`; remove `--parts`, `--texture`, `--harmony`,
  `--bass-style`, `--grid`; rename the staff `--melody` to `--note-names`.
- `CommonHelp`: new fields; `tests/test_cli.py` still asserts every field reaches
  `add_argument`.
- Run header prints the canonical request; add the round-trip test.
- Refusals: content flag on an absent part, unknown position,
  `--no-melody --chord-on melody`, `--no-melody --chord-fills` anything but
  `none`, empty selection.

### Stage 2: slot generation

- `headxml`: always start from `head_skeleton`.
- No `_merge_chord_slots` for `chord_on == melody` or `none`; the default no
  longer invents chords in rests. The optional rest union is Stage 2b.
- Explicit positions union `chord_slots` at those positions only. The
  `_generated_beats`/bar-resolution path is removed with the old default.
- Generalize the union to the bass rhythm as well: a position gets
  `(melody in force, chord in force, name, bar, beat, duration)`.
- Explicit positions are added even when the melody is held; a stab under a held
  note is wanted.
- `onsets` stays the set of written melody onsets, so a chord-only slot is not a
  reharmonisation onset.

### Stage 2b: rest fills (`--chord-fills`)

- `headxml.melody_rests` / segment builder: gaps in the melody timeline, split at
  chord changes and `--chord-on` targets. A bar line is not a musical split; a
  renderer may split and tie.
- Fill slots for `hold` (one per rest segment) and `comp` (rest onset plus each
  felt beat inside); `melody=None`, chord in force, segment duration, and a
  `Slot.fill` flag so the route knows the slot exists because of a rest.
- Union and dedup with the melody skeleton and `--chord-on`; a target wins a
  collision and the fill continues after it.
- `parts` includes chord when `chord_fills != none`; `--chord-on none
  --chord-fills hold` is a valid mode.
- `slot_plan` / `comping_step`: a fill slot is `melody=None`, `chord_here=True`;
  the existing comping route states the chord.
- Annotation witness; an `NC` rest gets no fill; `--no-melody --chord-fills` is
  refused.
- Tests: `hold` one chord per rest segment; `comp` one per felt beat; a chord
  change splits; a target inside a rest is not duplicated; the bass is
  independent; capacity; one-line/staff/HTML/MusicXML/GP5 agree.

### Stage 3: bass line at requested positions

This is the riskiest engine change; write the tests first.

- `walking_slots(..., rhythm=...)` and `bass_line_for(..., rhythm=...)`.
- The line is built only at the requested positions. The first position in a bar
  is an anchor; the last before a change can be an approach; the middle
  positions are connect. Sparse rhythms must not assume beats 2/3/4 exist.
- `root` and `root-5th` get simple lines that state a note at every requested
  position. Add `BASS_ROLE_PEDAL` for a root on a non-anchor.
- `_bass_slots` unions melody entries and bass-only entries as now; durations use
  the new stab/ring rules.
- Tests: 2/2 `every-beat` = 2 notes/bar; 4/4 = 4; 3/4 = 3; `root` on every
  requested beat; sparse walk; no refusals from the old "root only on anchors"
  rule.

### Stage 4: per-slot chord presence and bass-only steps

- `slot_plan` computes `chord_here`:
  - `chord_rhythm.wants_melody` and the slot is a melody onset; or
  - `chord_rhythm.includes(slot.beat)`; or
  - `slot.fill` (a fill slot from Stage 2b), which is always on.
- Pass `on_grid=chord_here` to `melody_alone_case`:
  - `--chord-on 1&`: melody slots elsewhere are melody-alone when singing, rest
    when comping;
  - `--chord-on none`: melody alone.
- Add a **bass-only route** before the "rest" answer for a slot whose only job is
  the thumb: one bass note alone, or melody+bass when the melody is present and
  the chord is off.
- `comping_step`'s `standalone_bass` becomes per-slot, not
  `parts == (PART_BASS,)`.
- `is_bass_only`: a bass-only step may now be a target when the chord part is
  off; update the docstring and `TestABassOnlyStepIsNeverATarget`'s precondition.
- Re-check trap 12's guard ordering for both routes after every change.

**Landed as:** `_chord_here` and `on_grid=` were already in place from Stages 2
and 2b, so the stage was the route. `decisions.lone_bass_case` names the one
combination no other decision speaks for - a bass note, no sung melody, no chord
stated - and `routes.bass_alone_step` emits the thumb alone: an **empty** chord
vector, so no upper voice is taken from the chord part, with `bass_only` read from
`bass_place.is_shape_held` (a shape still ringing is held; a run of lone thumbs
leaves the chord before them down, which `previous_shape` gets wrong because a lone
thumb replaces the sounding vector). `bass_place.place_bass` now places a note
against an empty upper voicing, taking the hand from the previous thumb's fret. The
singing case needed no route: the melody-alone route already carries the thumb
(`--chord-on 1&` with the melody on, measured).

Two bullets are answered differently than written, and both are named here rather
than quietly dropped. `comping_step`'s `standalone_bass` stays
`parts == (PART_BASS,)`: the per-slot case that bullet wanted is a *different* step
rather than a thinner comping one - its harmony is not stated at all - and
`bass_alone_step` is it. `is_bass_only` keeps its rule (a target states a chord);
its docstring now names the one route that sets the flag itself, where a target is a
metric event and nothing above the thumb is struck, which is why the contradiction
that rule exists for cannot arise there.

### Stage 5: durations, holds and ties

- `ArrangementStep.duration` for no-melody positions:
  - a `--chord-on` target: short stab to the end of the felt beat;
  - a `--chord-fills hold`: the rest segment end (or the next target/chord change);
  - a `--chord-fills comp`: the next fill attack/target/chord change or the rest
    end;
  - bass: to the next bass attack or the bar line.
- A held bass under a moving melody: carry the bass in the intervening melody
  steps and tie it in the score.
- A fill must stop at the rest's end, so it does not ring into the returning
  melody note.
- `tabxml`: tie a held bass or fill; `tabscore._is_hold` and the one-line/staff/
  GP5 renderers must agree on what is a new attack.
- Test on a 2/2 bar with a bass on beat 1 and a melody note at 1.5.

**Landed as two halves.**

*The stab.* `headxml._stab_length` caps a requested chord attack at the end of the
**felt beat** it sits in, read from the grouping rather than the denominator (a 6/8
pulse, a half bar in 2/2), and the next requested position still caps it: two attacks
inside one beat are two stabs. `tabscore._capped_span` already treated `duration` as a
cap, so the beats a stab does not fill are written as a rest with no change there. The
fill half of the bullet was already true from Stage 2b - `_fill_segment` measures each
attack to the next one or to the rest's end - so what was missing was a test, not code:
`tests/test_durations.py` pins all four lengths and the rest the score writes after a
stab.

*The ring.* `bass_merge.carry_bass` runs at the end of the step loop and writes a
struck thumb note into the steps that follow it, marking them `bass_held`: the string
sounds and is not plucked. Five things end it - the next attack, the bar line, a rest,
a shape that uses the string, and a shape the hand cannot reach the note from
(`fingers.can_fret`) - and an **unplaced** step carries nothing, which is what keeps a
hand-built progression byte-identical. That last rule is the one to keep: a progression
with no bar line has nothing to stop the ring at.

The renderers then agree about what is a new attack: `render._step_cells` mutes the
cell (it answers "what is plucked"), `tabstaff._strikes_here` leaves it empty (the note
was drawn where it was struck), `tabxml` ties the pitch **inside** the chord (per-note
`<tie>`, patched onto the earlier note as the chain grows; a chord-level tie is what
the bar-line cut writes, so a split event carries none), and `tabgp` writes a
tie-note. `annotation` spells it in the bass parenthetical as `(bass: C3, held)`,
because the tab shows a mute there and the note is sounding.

One consequence is named rather than hidden: the ring stops at a **rest**, so a melody
that rests for a bar while the bass line runs is still the hole Stage 7's lone-bass
route fills. Nothing carried here crosses it.

### Stage 6: staff/HTML moved-thumb fix

- `tabstaff._collapse_holds`: add `_moved_thumb(step, previous)` comparing
  `(bass_midi, bass_string)`. A hold column with a new thumb draws only the bass
  string.
- Update `Staff.cell`, `Staff.line` and `_html_string_row`.
- Regression: `tests/data/synthetic_cut_time.mxl` bar 3 beat 1; a held upper +
  new thumb. Assert the MusicXML and one-line already contain the note, so the
  test records that the staff was the outlier.
- This is the old "Phase 1" bug. It is independent of the vocabulary redesign
  and can land first if desired.

**Landed as:** `_moved_thumb` compares `(bass_midi, bass_string)` - by value, not by
role, because a thumb can move to another octave of the same pitch class and that is a
note being plucked. `_draws` is the single predicate both renderers now ask: a strike
column follows `_strikes_here`, a hold column draws nothing, and a hold column whose
thumb has moved draws **that string**. `_StaffGrid.cell` gained the previous step for
it, and `_html_string_row` tints such a column with the bass class.

The comparison is also what keeps Stage 5's ring from being drawn twice: a **carried**
thumb compares equal to the note it is still ringing from, so it is not a new attack
here. The plan's guess at the fixture was wrong, and the real one is recorded instead:
swept over the committed heads, the shape occurs with `--chord-on 1,1& --bass-on
1&`/`every-beat` on the cut-time head at bars 2, 4 and 8 beat 1.5, and at bar 7 beat 3 of
`synthetic_common_8`, which is the one `tests/test_staff_thumb.py` pins because its
fret is unambiguous on the row it is drawn on.

### Stage 7: comping and lone bass

- `--no-melody`: default `--chord-on every-beat`; off-chord positions rest.
- `--chord-on none --bass-on every-beat` with `--no-melody` is a lone bass line.
- Tests: 2/2 -> 2 attacks/bar, 4/4 -> 4, 3/4 -> 3, zero `bass_refused`, all
  renderers agree.
- This is where the old "`--parts bass` is melody-slot-driven" bug is fixed for
  good.

**Landed as:** `resolve_request` **derives** the melody-less default rather than
refusing it - `chord_on=melody` names the written onsets, and a request that hands the
tune away has none, so the metre's own reading is used. The header prints the resolved
positions (`chord-on=1,2,3,4`, `1,2` in 2/2, `1,5,9` in a 12/8 bar), which is what makes
the derivation visible; the refusal it replaced already told the caller to name
`every-beat`, which is the answer the metre has anyway. Spellings are one request:
omitting the flag and writing `melody` produce the same arrangement, and the CLI test
asserts that round trip.

The lone bass line itself was Stage 4's route, so this stage is its **measurement** and
the two renderers it caught out. Measured over the committed heads with
`--no-melody --chord-on none --bass-on every-beat`: 4 attacks a bar in 4/4, 2 in 2/2, 3
in 3/4, **2 in 5/4's `3+2` and 3 in 12/8's `4+4+4`** - `every-beat` is one per felt beat,
not one per denominator unit - and **zero `bass_refused`** in every one.

Two renderers agreed with the tab only because a *hold* had never been asked to sound a
thumb and nothing else:

- `tabstaff._collapse_holds` marked a column with **no upper voices** a hold of the
  previous one, so a bar of four repeated roots drew two notes. A column with nothing
  above the thumb cannot be holding a shape; whatever it sounds is struck.
- `tabscore._is_hold` folded those same steps into one tied note, for the same reason.
  A step whose **thumb is struck** is an attack however the upper voices compare; a
  *carried* thumb is the opposite, and that is the tie.

`parts=bass` keeps its melody-anchored positions until Stage 8 removes the axis, and
that is now stated rather than implied: the request spelling above is the fix, and the
axis is the thing being retired.

### Stage 8: docs, cleanup and measurement

- Remove the five old flags from `cli.py`, README, `docs/engine.md`,
  `AGENTS.md`, and the open-issues items they resolve (item 1's default union,
  item 4's inert `bass:walk`).
- Rewrite `docs/engine.md`'s "six axes" section around the request; keep the
  internal axes as an implementation table.
- Update `AGENTS.md`'s routing table and "Six axes, not one" paragraph; update
  the measured test count after `make check`.
- `docs/renderers.md`: the held-bass tie, the staff moved-thumb rule, and the
  rest/fill drawing.
- Update every test that spells the old keywords; add the new tests.
- Re-measure the ten committed heads:
  - default steps = melody note count, no extra attacks;
  - `--bass-on every-beat` counts per metre;
  - `--chord-on 1&` one stab per bar;
  - `--chord-fills hold` one chord per rest segment; `comp` the felt-beat count;
  - no five-string steps;
  - `bass_refused` count.
- `make check`; `make demo` and read the tabs, because the voicing paths moved.

**Status: partly landed, and the remainder is this list.**

Done in this round: the README's **flag table** now lists the six request flags and
nothing else, and says in one paragraph that `texture=`, `bass=`, `parts=`, `harmony=`
and `grid=` are the **Python API** underneath them (the axes are still real; only their
CLI spelling is gone). The `--no-melody` help text no longer claims the melody's own
rhythm is refused - Stage 7 derives it - and the `--melody` row was corrected to
`--note-names`, which the flag has been called since Stage 1.

Still to do, in this order, and none of it is code:

1. **README's per-axis sections.** ~68 `--texture` / `--bass-style` / `--parts` /
   `--harmony` / `--grid` spellings remain in the prose and in the example commands,
   and the commands no longer run. Each section needs its examples expressed either as
the request flag that now says the same thing (`--chord-notes 2` for `texture=chord2`,
`--bass-notes walk` + `--bass-on every-beat` for `bass=` + `grid=bass:walk`) or as a
`VoiceLeadingEngine` snippet, and the section headings relabelled from a flag to an
axis.
2. **`docs/engine.md`'s "six axes" section**, rewritten around the request with the
   axes kept as an implementation table; and the `Adding a new chord quality` recipe's
   flag references checked against the CLI.
3. **`docs/renderers.md`**: the held-bass tie (`tabxml._build_note`'s per-note
   `<tie>`), the staff's moved-thumb rule (`tabstaff._moved_thumb` / `_draws`), and
   what a rest and a fill draw now that a stab is capped at its felt beat.
4. **`docs/open-issues.md` items 1 and 4**, both of which this redesign resolves.
5. **`AGENTS.md`**: the routing table's axis row and the "Six axes, not one"
   paragraph, pointing at the request as the caller's vocabulary and the axes as the
   engine's; plus the measured count (1372 at the point this was written).
6. **The measurement table** the bullet list above asks for. The figures taken so far,
   which are the ones to re-take rather than re-derive: the committed heads' default is
   **one step per written note** (no added attacks); `--bass-on every-beat` gives 4 a
   bar in 4/4, 2 in 2/2, 3 in 3/4, 2 in 5/4 (the `3+2` pulse) and 3 in 12/8 (`4+4+4`);
   `--chord-fills hold` states one chord per rest segment and `comp` one per felt beat
   (`tests/test_durations.py` and `tests/test_chord_fills.py` pin both); and the lone
   bass line refuses **no** note in any of the five metres.

## Acceptance criteria

1. `head FILE` = one chord per melody note, no extra attacks, no bass.
2. `--bass-on 1` = a bass note on each bar's first felt beat; the chord thins to
   fit; no five-string steps.
3. `--bass-on every-beat` = 2 attacks/bar in 2/2, 4 in 4/4, 3 in 3/4.
4. `--chord-on 1&` = one chord stab per bar at 1.5; melody notes elsewhere alone.
5. `--chord-on melody,1&` = the harmonisation plus the stab.
6. `--no-melody --chord-on none --bass-on every-beat` = a beat-wise bass line,
   zero refusals.
7. `--chord-on none --chord-fills hold` = melody alone outside the rests; one
   chord at each rest onset; no bass unless `--bass-on`.
8. `--chord-fills comp` = one chord per felt beat inside a rest; a
   `--chord-on` target inside the rest is not duplicated.
9. `--no-melody --chord-fills` is refused; an `NC` rest gets no fill.
10. One-line, staff, HTML, MusicXML and GP5 show the same attacks.
11. `make check` green; the test count in `AGENTS.md` updated if it moved.

## Open decisions

These are the points to settle before Stage 1. The recommended answer is given,
but each is a genuine musical choice.

1. **Stab duration.** Recommended: a `--chord-on` target with no melody onset
   lasts to the end of the felt beat it starts in (`1&` = half a beat).
   Alternative: it rings until the next chord attack or the bar line, which is
   the current `chord_slots` rule but is not a "stab". A `--chord-fills`
   `hold`/`comp` is governed by the rest, not by this rule.
2. **Bass ring.** Recommended: a bass note rings to the next bass attack or the
   bar line, carried under intervening melody steps. Alternative: one felt beat,
   which is shorter and more percussive.
3. **Drop `texture=targets` and public `--harmony`.** Recommended: yes. The
   rhythm half of `targets` is `--chord-on 1,3` in 4/4 (or `1` in 2/2); the
   "thin fills between" half is a separate future `--chord-between`, not
   `--chord-fills`. `--harmony` is inert on the melody-bearing route, so
   exposing it is the confusion this redesign is removing.
4. **`--no-melody` default chord rhythm.** Recommended: `every-beat`
   (four-to-the-bar comping). Alternative: require an explicit `--chord-on` so
   nothing is assumed.
5. **What does "every downbeat" mean in your example?** The grammar supports
   `1` (the bar's first felt beat), `every-beat` (all felt beats: 2 in 2/2) and
   `1,3` in 4/4 (the strong pair). Recommended help example: `--bass-on
   every-beat` for the 2/2 head, since that is the "2 attacks per bar" case.
6. **Position tokens.** Recommended: `1&`, `1e`, `1a`, `last`, `last&`,
   `every-beat`. Alternative: decimal offsets (`1.5`), which are less musical
   and ambiguous in compound metres.
7. **Content flag names.** Recommended: `--chord-notes` and `--bass-notes`.
   Alternatives: `--chord-arity`/`--bass-style` (the old word "style" conflates
   notes and rhythm) or `--chord-size`/`--bass-notes`.
8. **Staff flag rename.** Recommended: `--note-names` (currently `--melody`), so
   `--no-melody` has one meaning. Alternative: `--show-melody` for the staff.
9. **Stage order.** Recommended: Stage 0, 1, 2, 2b, 3, 4, 5, 7, 8, with Stage 6
   (the staff/HTML moved-thumb bug) first if the rendering defect is the more
   urgent user-visible issue. Stage 6 is independent.
10. **Named presets.** Recommended: not public. Alternative: keep
    `freddie`/`charleston`/`joe_pass`/`final_and` as undocumented aliases for one
    release. The user has said backwards compatibility is not a concern.

## Risks

- **The bass line's role/position refactor is the riskiest change.** The current
  `_walking_bass_line` is written around every beat and the metric roles
  (`anchor`/`connect`/`approach`). Sparse positions, a `root` on a non-anchor,
  and a rhythm that is not every beat all touch the same function. Stage 3
  should start with tests for sparse positions before the route changes.
- **Per-slot chord presence interacts with trap 12.** `melody_alone_case`'s
  guard ordering is load-bearing for the singing and comping routes. Every
  change to `chord_here` must be tested on both, including an `NC` bar and a
  note-less grid position.
- **Rest detection is a new timeline problem.** The head's notes and durations
  define rests; a held note is not a rest; a rest may cross a bar line, a chord
  change or a `--chord-on` target. The segment boundaries are the whole
  correctness of `hold`/`comp`.
- **Fill/target precedence.** A `--chord-on` target inside a rest must neither
  duplicate the fill nor be swallowed by it; the fill's duration around it is a
  per-step decision.
- **Durations and ties are the least defined part.** A held bass under a moving
  melody, a stab under a held melody, a held/comped fill around a target, and a
  bass line that re-articulates on a melody onset are different cases. Stage 5
  should be driven by rendered examples, not only by pitch assertions.
- **The test and doc churn is large.** The old five flags appear throughout the
  suite and the docs. Since backwards compatibility is not a concern, the clean
  break is right, but it is many small edits; stage them and keep `make check`
  green.
- **`texture=targets` is a real loss.** The new model expresses its rhythm but
  not its automatic thinning between targets. It is **not** replaced by
  `--chord-fills`; it needs an explicit `--chord-between` rather than being
  quietly dropped.
- **`full` plus a bass cannot both be maximal.** The help must say "the most that
  fits", and a request for four chord notes plus a bass must be refused with the
  capacity reason, not silently thinned.
- **`&` in a compound metre is a judgement.** The midpoint of a dotted-quarter
  pulse is not a standard notation value. The simple metres (2/2, 3/4, 4/4) are
  unambiguous; the compound case should be documented and tested.

## Out of scope

- The cost tuple, `voicing_cost`, the grip tables, the selector and tuning: they
  are not part of this request.
- The non-chord-tone strategies, the diminished retry and the neck window.
- New chord qualities or new grip families.
- `--chord-tones` (a degree-order choice), `--chord-between` (the old
  `texture=targets` thin-between half) and `--chord-length`/`--bass-length`
  (duration overrides) are future extensions, not part of the first cut.
  `--chord-fills` is in scope as Stage 2b.
- Backwards-compatible aliases for the removed flags. The user has explicitly
  said compatibility is not a concern; the plan is a clean break.

## Appendix: what `--chord-fills` would look like

`--chord-fills` is the chord layer's policy in a **notated melody rest**. It is
not the old `texture=targets` thin fill under a melody note; it is about the
chord that sounds when the tune stops. The bass is already defined by
`--bass-on`; this flag never adds a bass note.

```text
--chord-fills {none,hold,comp}    default: none
```

- `none`: the guitar rests with the tune. This is the default.
- `hold`: one chord at each rest onset, stating the harmony already in force,
  held to the end of the rest segment. Split at a chord change or a
  `--chord-on` target.
- `comp`: a chord at the rest onset and each felt beat inside the rest, lasting
  to the next fill/target/chord change or the rest end.

A "rest" is a **notated silence in the melody line**, not a held note. The chord
is the written harmony in force; `--chord-fills` does not reharmonise. The
voicing uses the normal comping content and `--chord-notes` caps it.

It is not a rhythm of its own: it creates no melody note and never invents a
melody. It does create chord slots in the rests, which is the point.

### Examples

```bash
# melody alone; when it rests, hold the written chord
--chord-on none --chord-fills hold

# melody harmonised; the rests also get the chord
--chord-on melody --chord-fills hold

# comp through long rests on each felt beat
--chord-on melody --chord-fills comp

# the bass is independent and walks through the rest
--chord-on none --chord-fills hold --bass-on every-beat --bass-notes walk

# a target inside a rest is not duplicated (2/2; use 1,3 in 4/4)
--chord-on 1,2 --chord-fills hold
```

### What the output looks like

A bar where the melody rests and `--chord-fills hold` is on:

```text
Ebmaj  -    -   x-6-8-8-8-x   (fill - melody rest -
                               Eb Root, G 3, Bb 5)
```

The melody column is empty; the chord is the written harmony. With
`--bass-on 1`, the same step also carries the bass. With `comp`, a long rest
shows one chord per felt beat, each with the chord in force at that beat. The
columns above are illustrative; the exact wording comes from `render`.

The old `texture=targets` output — a thin chord under a **melody note** between
targets — is a different feature and is not what this flag produces.

### Interaction with the other flags

| flag | interaction |
|---|---|
| `--chord-on` | targets are absolute and always attack. A fill only covers the rest of the time; at a coincident position there is one step, and a target inside a rest re-attacks with the fill continuing after it. |
| `--chord-notes` | the fill uses the normal comping arity, capped by this. During a rest the melody string is free, so a fill can be fuller than a chord under a melody note. |
| `--bass-on` | independent. A bass note in the rest is `--bass-on`'s; a coincident fill and bass merge into one step, subject to the four-string capacity. |
| `--no-melody` | refused: the guitar is not playing the melody, so it has no melody rests to fill. |
| `NC` rest | no fill: there is no chord to state. |
| `--chord-on none` | allowed: the chord part exists only in the rests. |

### Rest segments and precedence

A fill is computed from the melody timeline, not from the chord grid:

- the rest starts where the previous melody note stops sounding and ends where
  the next one begins; the section start/end is a boundary too;
- a chord change or a `--chord-on` target splits a `hold` segment;
- a `comp` fill attacks at the rest onset and at each felt beat inside it;
- the fill stops at the rest end, so it cannot ring into the returning melody;
- a bar line is not a musical split; a renderer may split the step and tie it;
- a rest with no chord (`NC`) gets no fill.

The open duration question for a target is whether a target with no melody is a
short stab or rings; a fill is not governed by that rule. See the open decisions.

### Why a separate flag?

`--chord-fills` is not a position in the chord rhythm; it is a policy for a
different span (a rest). Folding it into `--chord-on` would require a
rest-relative modifier in the position grammar, which is not a position. The
flag keeps `--chord-on` a pure position list and makes the rest behaviour
explicit.

### Implementation notes

- `headxml.melody_rests` computes the rest segments from the melody notes and
  durations; `melody_at`/`melody_state` already distinguish "no note in force"
  from a held note.
- Fill slots are `melody=None`, the chord in force, and the segment duration.
  They are unioned with the melody skeleton and `--chord-on` slots, deduped on
  `(bar, beat)`; a target wins, and the fill continues after it.
- The route is the existing comping route: `melody=None`, `chord_here=True`;
  `comping_step` states the chord. No new voicing path.
- `parts` includes chord when `chord_fills != none`, which is what makes
  `--chord-on none --chord-fills hold` valid.
- `--bass-on` unions independently; the fill and bass merge if they coincide.
- The annotation gets a witness: "the melody rests here, so the chord fills."
- The old `texture=targets` thin fill under a melody note is a different
  feature (`--chord-between`, future); this flag does not remove or replace it.

## Evidence

All commands are read-only and were run from the repository root with
`.venv/bin/python`.

### The default is a full chord under every melody note

```bash
.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3
```

```text
Bb7      F4  5    6-x-6-7-6-x       (harmony under 5 - 4 voices -
                                    sounding: Bb Root, Ab b7, D 3, F 5)
```

### `--harmony guide` is inert when the guitar sings

```bash
.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-2 \
  --harmony guide
```

Identical to the default: still `Bb Root, Ab b7, D 3, F 5`.

### The `bass:` grid row is inert

```bash
.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3 \
  --grid melody:every_note,bass:walk
```

Identical to the default: no bass note.

### The closest thing to a stab on the and of 1

```bash
.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3 \
  --grid chord:joe_pass
```

The melody notes are alone and one chord is comped at an offbeat. There is no
way to ask for only `1&`.

### A bass under the harmony thins the chord

```bash
.venv/bin/python -m arranger head examples/But_Not_for_Me.mxl --bars 1-3 \
  --bass-style root
```

```text
Bb7      F4  5    x-x-6-7-6-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most this palette offers -
                                    sounding: Ab b7, D 3, F 5)
Ebmaj    G4  3    x-6-8-8-8-x       (shell - 3rd & 7th, partial -
                                    3 voices, the most this palette offers -
                                    sounding: Bb 5, Eb Root, G 3) (bass: Eb3, anchor)
```

The four-voice chord becomes melody + two chord tones + bass. This is the
capacity rule the new `full` default describes.

### The MusicXML already has the downbeat bass note

With `--parts bass,melody`, bar 3 of the exported score starts:

```text
measure 3
  onset 0: C4 + Eb5    <- sounding C3 (the walked bass) + held Eb4
  onset 1: F5          <- melody F4
  onset 2: D4 + G5     <- sounding D3 (the walked bass) + melody G4
  onset 3: F5
```

The score writer is correct; the ASCII staff and HTML drop the note because
their hold rule compares only the upper voices. That is Stage 6.

### The lone-bass selection is melody-slot-driven

With `--parts bass`, bar 3 of the exported score starts with a tie stop (the
tail of bar 2's bass note), and the first new bass attack is at beat 1.5. The
bass line follows the melody's slots because `parts=bass` resolves
`bass=auto` to none and the comping route voices one step per melody slot. That
is the generation bug the new `--bass-on every-beat` fixes in Stage 7.

## Files likely touched

- `arranger/grid.py`: `Rhythm`, parser, `includes`, canonical spelling.
- `arranger/options.py`: the new request fields.
- `arranger/resolution.py`: request-to-policy mapping and refusals.
- `arranger/movement.py`, `arranger/headxml.py`: request plumbing, slot union,
  `melody_rests` and the fill-segment builder.
- `arranger/slot_plan.py`, `arranger/decisions.py`, `arranger/routes.py`:
  per-slot chord presence, fill slots, bass-only route, `on_grid`/`chord_here`.
- `arranger/bass.py`, `arranger/bass_rules.py`, `arranger/bass_merge.py`: bass
  positions, `root`/`root-5th`/`walk`, `pedal` role, held bass.
- `arranger/cli.py`: the new flags, removed flags, help, run header.
- `arranger/tuning.py`: duration/hold fields if needed (`bass_only` docstring).
- `tabstaff.py`, `tabscore.py`, `tabxml.py`, `tabgp.py`: moved-thumb, ties,
  held bass, rests/fills, duration.
- `tests/`: `test_grid.py`, `test_options.py`, `test_cli.py`, `test_parts.py`,
  `test_bass.py`, `test_walking_bass.py`, `test_comping.py`,
  `test_headxml_timeline.py`, `test_staff_rendering.py`, `test_html_rendering.py`,
  `test_walking_bass_rendering.py`, `test_explanations.py`, a new
  `test_rest_fills.py` (or the existing timeline/comping files), and the pinned
  tab snapshots that spell the old flags.
- `README.md`, `docs/engine.md`, `docs/open-issues.md`, `docs/renderers.md`,
  `AGENTS.md`: public vocabulary, routing table, measurements, test count.

## References

- `docs/engine.md` — the current six-axis model, the step loop and the grid.
- `docs/open-issues.md` item 1 (grid positions in melody-silent bars) and item 4
  (the inert `bass:walk` row).
- `docs/history/parts.md`, `docs/history/comping-styles.md`,
  `docs/history/voices-axis.md` — how the current axes were decided, and why
  `parts` and `bass-style` overlap.
- `docs/history/fingering.md` §4.3 — the thumb reach and the four-fret budget,
  which the bass positions must continue to respect.
- `AGENTS.md` trap 12 — the guard ordering in `melody_alone_case`, which the
  per-slot `chord_here` change must not break.







