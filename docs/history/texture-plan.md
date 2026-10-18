# Implementation Plan

## Overview
Give the arranging engine **metric and textural awareness** — so a chord lands on the strong beats of the bar and the notes in between are filled with a single note, a 3rd/6th interval or a shell rather than a re-struck four-note chord — which is the core method the arranging guide describes and the one thing the current engine structurally cannot express.

Scope is one phase in `arranger.py`, plumbed through the corpus and MusicXML front ends, plus tests and docs. It is deliberately **additive and opt-in**: `arrange_progression`'s existing signature and output stay byte-identical unless the caller supplies timing, and the corpus/head CLIs keep their current default texture. Later phases (chromatic approach chords, tritone substitution, dim7 as a deliberate passing chord, relaxing `GRIP_MAX_SPAN` to admit drop-3) are named here and left out, so the phase-1 diff stays reviewable.

### Why this is the gap

The engine's whole selection rule is `voicing_cost`: chord-tone purity, then the neck window, then **completeness** (`missing = 4 - len(active)`), then position, then movement. Nothing in it knows where in the bar a note falls. Three consequences follow directly from the guide's point of view:

- **Completeness is ranked above position**, so a step the guide would fill with two notes gets a full four-note drop-2 chord whenever one is playable. Bars of running eighths come out as eight re-struck chords — a chord list, not an arrangement. `tabstaff`'s `collapse` hides this in the *rendering*, which is a presentation patch over a selection that never made the decision.
- **There is no weaker grip to fall back on for a passing note.** `GRIP_PREFERENCE = ("drop2", "shell", "duo")` and `DUO_DEGREES = (0, 7)` mean a duo is only generated under a root or a 5th. The guide's "2-note intervals (3rds or 6ths)" under *any* melody is not representable at all.
- **`arrange_progression` takes `(note, quality, name)` triples**, so the beat a note falls on is not even an argument. `ArrangementStep` already carries `bar`/`beat`/`duration`; the timing exists downstream and is simply never fed *in*.

### The approach

Generation and selection stay separate, as they already are. Timing changes **which grip families are offered for a step**, before `_best_voicing` runs — it does not add a new term to the cost tuple, because "play fewer notes here" is not a preference competing against "stay in position", it is a change of what is on the table. That keeps `voicing_cost` a total order over shapes, keeps the engine deterministic, and means the metric rules can be stated once, in one place, as a mapping from a slot's position to the roles it may take.

Two new roles, matching the guide's "Identify Target Notes" / "Fill the Gaps":

- **target** — a full four-note chord. Reserved for the principal melody notes: beat 1 and beat 3 of the bar (the guide's rule verbatim), which in 4/4 are the two half-note pulses.
- **fill** — a shell, a diatonic interval, or the melody alone.

A step with no timing is a **target** under every texture, which is what keeps every hand-written progression and every existing test exactly as it is.

## Types

No existing type changes shape. Three additive, defaulted members keep every construction site, the `__getitem__` shims and `arranger.__all__` valid.

`arranger.py` module level:

```python
# Metric roles a slot may take. See the texture rules in _roles_for_slot.
ROLE_TARGET = "target"
ROLE_FILL = "fill"

# Texture styles, in the order that breaks a tie.
TEXTURE_STYLES: Tuple[str, ...] = ("uniform", "targets")

# The beats of a bar that carry a full chord under the "targets" texture, counted
# from 1. Beat 1 and beat 3 are the guide's target-note rule: the two half-note
# pulses in 4/4. Expressed as beats rather than as an absolute onset so a 2/2 bar
# (two beats) still yields beat 1 only, and a 3/4 bar yields 1 and 3.
TARGET_BEATS: Tuple[int, ...] = (1, 3)

# The grip families each role may use, by texture. `uniform` is today's behaviour:
# every slot may use every grip in GRIP_PREFERENCE and the cost tuple's
# completeness criterion decides, exactly as before. `targets` is the new mode.
TEXTURE_GRIPS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "uniform":  {"target": GRIP_PREFERENCE, "fill": GRIP_PREFERENCE},
    "targets":  {"target": ("drop2", "drop3"), "fill": ("shell", "interval", "melody")},
}
```

`ArrangementStep`, two new defaulted fields after `partial`:

- `role: str = ROLE_TARGET` — which role this step was given by the texture rules.
- `metric_weight: int = 0` — 2 on beat 1, 1 on beat 3, 0 elsewhere; `-1` when the step carries no timing, so "unknown" is distinguishable from "weak".

`Voicing`, one new defaulted field after `bass_pc`:

- `role: str = ROLE_TARGET` — mirrors the step, so a caller inspecting a candidate
  directly can see which texture produced it. Kept as a plain string rather than an
  enum for the same reason `grip` is: the file has no `enum` import and pyright must
  stay clean without one.

`GRIP_MAX_SPAN` gains one entry, `"interval": 4` — same reasoning as `duo`: two
fingers, held to a tighter span than a shell's three.

`GRIP_STRING_SETS` gains an `"interval"` family, reusing the three adjacent pairs
`duo` already declares: `(((5, 4), 5), ((4, 3), 4), ((3, 2), 3))`.

## Files

- **Modify `arranger.py`** — the whole phase. New module constants above; the two
  `ArrangementStep` fields; the `Voicing.role` field; `"interval"` in `GRIP_MAX_SPAN`
  and `GRIP_STRING_SETS`; `_interval_offsets()`; `supported_string_sets()` picks the
  new sets up for free (it already iterates `GRIP_STRING_SETS.values()`);
  `_metric_weight()` and `_roles_for_slot()`; `grips` parameter threading through
  `get_grip_voicings` → `get_all_grip_voicings` → `get_octave_down_candidates` →
  `prepare_step` → `arrange_progression`; the `timings` parameter on
  `arrange_progression`; `role`/`metric_weight` stamped onto each step; the
  `"interval"` branch in `_step_annotation`.
- **Modify `wjazzd.py`** — `arrange_slots` gains a `texture` parameter that it
  forwards as `timings` + `texture` (it already has the timings in hand as
  `Skeleton.timings`; they are simply not passed down). `arrange_head` gains the same
  parameter and threads it through `build_skeleton`. `corpus_cli` gains
  `--texture {uniform,targets}`, default `uniform`.
- **Modify `headxml.py`** — `arrange_xml_head` and `head_cli` gain the same
  `--texture` flag, forwarded to `arrange_slots`. `Head` already carries
  `beats_per_bar`, which `arrange_slots` needs to evaluate `TARGET_BEATS`.
- **No new modules.** `arranger.py` stays the single engine module, per the
  standing convention in AGENTS.md; the renderers in `tabstaff.py`/`tabxml.py`/
  `tabgp.py` need no change because they already read `ArrangementStep` fields
  defensively and the new fields are defaulted.
- **No files deleted or moved.**

## Functions

### New, in `arranger.py`

- `_metric_weight(bar: Optional[int], beat: Optional[float], beats_per_bar: int) -> int`
  — 2 when `beat == 1`, 1 when `beat == 3` and `beats_per_bar >= 4`, else 0;
  `-1` when `bar is None or beat is None`. A float beat is compared with a small
  epsilon (1e-6) so a 2/2 eighth at 1.5 is not read as beat 1.
- `_roles_for_slot(weight: int, texture: str) -> List[str]` — the whole metric
  policy in one function. `texture == "uniform"` → `[ROLE_TARGET]`. `weight < 0`
  (no timing) → `[ROLE_TARGET]`. `weight > 0` → `[ROLE_TARGET]`. `weight == 0` →
  `[ROLE_FILL]`. A single place to change when the target-note rule changes.
- `_interval_offsets(tones, melody_midi, root_pc) -> List[List[int]]`
  — the guide's "2-note intervals (3rds or 6ths)": for each interval class in
  `(3, 8, 9)` — minor 3rd, minor 6th, major 6th — the nearest pitch of that class
  *below* the melody is looked for among the chord's tones **and**, when the melody
  is a non-chord tone, among the diatonic tones of the prevailing key. Returns one
  template `[0, offset]` per interval class that has a pitch, most specific first.
  Unlike `_duo_offsets` this is **not** gated on `DUO_DEGREES`: a 3rd/6th under a
  melody that is itself the 3rd or 7th is a legitimate passing texture, which is
  exactly why it is confined to fill slots and never offered as a harmony on its
  own. Must return `[]` when the chord has no root, on the same argument as the
  shell.
- `VoiceLeadingEngine.get_interval_voicings(melody_note, chord_type, chord_name=None, top_string=5)`
  — thin wrapper over `_interval_offsets` + `_place_template`, matching the shape of
  the existing per-grip entry points. Kept public because the AGENTS.md convention is
  that every grip family is reachable from the public surface.
- `VoiceLeadingEngine.get_melody_voicing_at(melody_note, prefer)` — the existing
  `get_melody_only_voicing` reused rather than rewritten. **No new function**: the
  fill role's "single note" case is the melody-only voicing, and it is already
  exempt from the string-set invariant and already sets `melody_only=True`.

### Modified, in `arranger.py`

- `get_grip_voicings(melody_note, chord_type, chord_name=None, top_string=5, grips=GRIP_PREFERENCE)`
  — unchanged signature. The new `"interval"` grip is handled inside the existing
  `for grip in grips` loop beside `shell`/`duo`: it needs `root_pc` (so it is skipped
  when `root_pc is None`, like `shell`) and produces templates rather than a search.
- `get_all_grip_voicings(...)`, `get_octave_down_candidates(...)` — signature and
  behaviour unchanged; they already forward `grips`.
- `_string_sets_for(grip, top_string)` — unchanged; `GRIP_STRING_SETS["interval"]`
  is found by the existing lookup.
- `prepare_step(..., grips=GRIP_PREFERENCE)` — unchanged signature. It already takes
  `grips`, so the texture rules need no change here at all; `arrange_progression`
  simply passes the role's grip tuple instead of the caller's.
- `arrange_progression(progression, top_strings=..., non_chord_tone="extension", fret_min=..., fret_max=..., grips=GRIP_PREFERENCE)`
  — **additive keyword parameters, all defaulted**:
  - `timings: Optional[List[Tuple[int, float, Optional[float]]]] = None` — the
    `(bar, beat, duration)` of each slot, in the caller's own units. `None` (the
    default) means "no rhythm supplied", every slot weighs `-1`, and behaviour is
    identical to today. The list is indexed defensively (`index < len(timings)`), the
    same guard `wjazzd.arrange_slots` uses, so a short list cannot shift a step's role.
  - `texture: str = "uniform"` — raises `ValueError` for an unknown value, alongside
    the existing `non_chord_tone` check and before any voicing work.
  - `beats_per_bar: int = 4` — needed to evaluate `TARGET_BEATS`; the corpus and
    `headxml` paths pass their own, so a 3/4 head is not read as 4/4.
  - `key: Optional[str] = None` — for `_interval_offsets`' diatonic fallback.
- `_step_annotation(step)` — appends `(<role>)` for a fill step, so a tab shows why
  a note is thin. Shared with `format_progression`, so the two renderings cannot drift.
- `main()` — the built-in demo gains one short progression demonstrating
  `texture="targets"`; output goes to stdout only, as today.

### Modified, in `wjazzd.py` / `headxml.py`

- `arrange_slots(triples, timings=None, ..., texture="uniform", beats_per_bar=4, key=None)`
  — forwards to `arrange_progression`. It already receives `timings`; the change is
  that they are now *used*, not just stamped onto the steps afterwards.
- `arrange_head(...)`, `build_skeleton(...)`, `arrange_xml_head(...)` — thread
  `texture` through. Defaults unchanged.
- `corpus_cli`, `head_cli` — add `--texture {uniform,targets}`, default `uniform`,
  and mention the decision in the diagnostics notes the way `--lift` does.

### Removed

None. No signature is narrowed and no public name is withdrawn, so
`test_dunder_all_matches_the_public_surface` only needs the four new public names
added to `__all__`.

## Classes

- **`ArrangementStep`** (`arranger.py`) — two new defaulted dataclass fields,
  `role: str = ROLE_TARGET` and `metric_weight: int = 0`, placed after `partial`.
  Because every field is defaulted, positional construction still works, `__getitem__`
  picks the new names up automatically via `hasattr`, and no `has_timing` change is
  needed (it deliberately reports *timing presence*, which is a different question
  from *metric role*).
- **`Voicing`** (`arranger.py`) — one new defaulted field `role: str = ROLE_TARGET`,
  set by whichever generator produced the shape. `_place_template` takes a `role`
  argument; `_place_shell` and `get_melody_only_voicing` set it at their own
  construction sites.
- **`VoiceLeadingEngine`** (`arranger.py`) — gains `get_interval_voicings`; every
  existing method keeps its signature.
- No new classes. `StepPreparation` is unchanged: `role` is decided by
  `arrange_progression` from the timing, not by `prepare_step`, so the corpus's
  slash-bass path (`_arrange_step_with_bass`) needs no change beyond forwarding the
  role's grip tuple.

## Dependencies

**None.** No new package, no version bump, no change to `pyproject.toml`. This phase
is pure engine work and uses only `musthe`, which is already a dependency.

This is a deliberate constraint, not an accident: AGENTS.md's rule is that `musthe` is
the only runtime dependency, and the renderers are already split across three modules
with two optional extras. Adding a rhythm/metre library to evaluate "is this beat 1"
would be absurd; the arithmetic is three lines.

## Testing

### New `tests/test_texture.py` (no `skipUnless` — pure engine work)

- **`TestMetricWeight`**: beat 1 → 2; beat 3 in 4/4 → 1; beat 2/4 → 0; no timing →
  `-1`; a 3/4 bar still gives beat 3 weight 1; a 2/2 bar (`beats_per_bar=2`) does
  **not** give beat 3 any weight; a float beat of 1.5 is not read as beat 1; a float
  beat of 3.0 within 1e-6 **is** read as beat 3.
- **`TestRoles`**: `_roles_for_slot` for every `(weight, texture)` pair; an unknown
  texture raises `ValueError`; a progression with `timings=None` gives every step
  `role="target"` and `metric_weight=-1`.
- **`TestBackwardCompatibility`** — the important one. `arrange_progression` called
  with no new arguments must produce **exactly** the same steps as before: same
  `tab_string()` for every step of the library's own demo progressions, same `grip`,
  same `partial`, same `repeated`. Written against the fixture strings already pinned
  in `tests/test_voicings.py` and `tests/test_progressions.py`, so a regression here
  fails loudly rather than drifting.
- **`TestTargetsTexture`**: on a hand-built 4/4 progression with timings, every
  step on beat 1 or 3 is a four-note drop-2; every step on beat 2 or 4 is a shell,
  an interval or melody-alone. Assert on `step.role` and
  `len(step.voicing.active_frets())`.
- **`TestFillNeverSoundingAWrongNote`**: for a fill step, every sounding pitch class is
  either a chord tone *or* the melody itself — the diatonic fallback in
  `_interval_offsets` must not put a foreign note under a written chord.
- **`TestTimingsDefensive`**: a `timings` list shorter than the progression arranges
  without raising and leaves the trailing steps at `role="target"`.
- **`TestIntervalGrip`**: every interval voicing has 2 active frets, `fret_span() <= 4`,
  its sounding strings are a member of `supported_string_sets()`, the melody is on its
  soprano and is the highest sounding note, and the two pitches are a 3rd, 6th or
  10th apart.

### Modified

- `tests/test_grips.py::TestStringSetTable` — assert the new `interval` sets and the
  `GRIP_MAX_SPAN` entry.
- `tests/test_grips.py` — a small class for the invariant sweep over the new grip
  (fret span, chord-tone subset, string-set membership), matching what the file
  already does per grip family.
- `tests/test_tab_rendering.py` — a fill step's annotation appears in
  `format_progression` and on the ASCII staff, and the two agree.
- `tests/test_wjazzd.py` — `--texture targets` end-to-end over a database-backed head,
  guarded by the existing `skipUnless(DEFAULT_DB.is_file())`; and one test needing no
  database asserting `arrange_slots(..., texture="targets")` on a hand-built triple
  list gives target roles.
- `tests/test_headxml.py` — the same for `arrange_xml_head` over the committed
  `but_not_for_me.mxl`, which is the only fixture whose metre is **not** 4/4 and is
  therefore the only one that can catch `TARGET_BEATS` being evaluated in quarters.

### Validation

```bash
.venv/bin/python -m unittest discover -s tests -v     # must report OK
.venv/bin/pyright arranger.py tabstaff.py wjazzd.py headxml.py tests   # 0 errors
.venv/bin/python arranger.py                          # eyeball the new demo
```

Plus the measurement that justifies the change, run before and after on the same
corpus sample: mean number of sounding notes per melody note, and mean number of
re-struck shapes per bar. The claim to check is that a `targets` arrangement is
markedly thinner on running eighths while the count of complete chords on beats 1
and 3 is unchanged. If complete chords on the target beats drop, the texture rules
are wrong and the phase is not done.

## Implementation Order

1. **Additive types only, no behaviour.** Add `ROLE_TARGET`/`ROLE_FILL`,
   `TEXTURE_STYLES`, `TEXTURE_GRIPS`, `TARGET_BEATS`, `_metric_weight()`,
   `_roles_for_slot()`, the two `ArrangementStep` fields and `Voicing.role`. Nothing
   reads them yet. Suite must still report `OK` — this step is provably inert.
2. **`tests/test_texture.py::TestBackwardCompatibility`** before anything else that
   changes behaviour. Pin today's output for the demo progressions, so every
   subsequent step is checked against it.
3. **The `interval` grip**: `GRIP_MAX_SPAN`, `GRIP_STRING_SETS`, `_interval_offsets()`,
   the branch in `get_grip_voicings`, `get_interval_voicings`. Add
   `tests/test_texture.py::TestIntervalGrip` and update `TestStringSetTable`. Still
   unreachable from `arrange_progression` with the default `grips`.
4. **`timings` + `texture` on `arrange_progression`**, with the role→grip mapping and
   the `role`/`metric_weight` stamping. Add `TestMetricWeight`, `TestRoles`,
   `TestTargetsTexture`, `TestTimingsDefensive`.
5. **Renderers**: `_step_annotation` and the `tabstaff` tests. One-line change, but
   it has to land before the corpus path so a `targets` head is never printed without
   saying why a note is thin.
6. **Front ends**: `--texture` on `corpus_cli` and `head_cli`, threaded through
   `arrange_slots`, `arrange_head`, `build_skeleton`, `arrange_xml_head`.
   `beats_per_bar` is passed from `Head.beats_per_bar` and from the corpus default.
7. **Measure**, using step 6's output, on a fixed sample of heads. Report
   notes-per-note and re-strikes-per-bar before and after. Do not proceed to the docs
   step until the numbers justify it.
8. **Docs**: a "Texture and metric placement" section in `README.md`, the new
   constants and functions in `AGENTS.md`'s Architecture list, the `timings`
   parameter documented on `arrange_progression`, and a new bullet in Known
   Limitations for what `targets` still does not do. Bump `__version__` to `0.7.0`.

### Deliberately out of scope for this phase

Named here so they are not rediscovered as "missing", and so a later phase starts
from a measured baseline rather than a guess:

- **Chromatic approach chords** and **tritone substitution**. `diminished` exists but
  only as a *fallback* for a non-chord tone no strategy resolved, and it is opt-in
  because it replaces the written chord. Making it a deliberate passing chord between
  two chord tones, and adding approach chords and tritone subs, is a change to
  `resolve_non_chord_tone` and needs its own argument about when substitution is
  desirable at all.
- **Drop-3 as an offered default.** It is generated but excluded because
  `GRIP_MAX_SPAN = 5` cannot hold it — drop-3 spans a twelfth by construction. Lifting
  the span is a change to the library's stated playability contract, not a tuning knob,
  and it deserves its own phase and its own tests. Note that `TEXTURE_GRIPS["targets"]`
  above lists `drop3` among a target's permitted grips: with the span at 5 it simply
  generates nothing, which is the same position the library is in today, so listing it
  costs nothing and means a future span change takes effect without touching this code.
- **Walking bass, pedal tones, counterpoint and open-string textures.** These are
  arrangement *styles* that need a second simultaneous line and a bass part the engine
  does not model at all — it voices one melody at a time with the harmony below it.
  `duo` is the only two-voice grip, and it is not a bass line. These would be a
  different engine, not an extension of this one.
