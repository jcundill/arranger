"""The step loop: one progression in, one arrangement out.

`arrange_progression` is the entry point. It turns `(melody, quality, name)`
triples into `ArrangementStep`s, dispatching each slot to one of five routes -
a rest, a texture fill, a no-chord melody-alone step, a comping shape, or a
harmonised melody step - and merging the walking bass in afterwards.

One step's candidates are built in `step_prepare`; the melody-bearing route is
in `harmonised_route`; the route dispatch itself (`_route_slot`) lives here so
the loop stays one module. `VoiceLeadingEngine` is a facade of one-line
delegates onto this module and `step_prepare`. The engine imports `grips`,
`cost`, `chords` and the rest directly and does not import `steps` at all.
`slots.arrange_slots` delegates through the class, so the imported-head path and
the hand-built one still run one loop rather than two.
"""

from __future__ import annotations

from typing import Container, List, Optional, Sequence, Tuple

from .bass import Slot
from .bass_rules import BASS_STYLE_AUTO
from .decisions import (
    MELODY_ALONE_NO_CHORD,
    MELODY_ALONE_REST,
    MELODY_ALONE_TEXTURE,
)
from .grid import GRID_DEFAULT
from .grips import MELODY_STRING_CHOICES_FULL
from .grouping import COMMON_TIME, TimeSignature
from .harmonised_route import harmonised_step
from .harmony import HARMONY_AUTO
from .options import ArrangeOptions
from .parts import PARTS_AUTO
from .resolution import resolve_knobs, resolve_policies
from .routes import (
    comping_step,
    no_chord_step,
    previous_shape,
    rest_step,
    texture_fill_step,
)
from .slot_plan import Carried, SlotInputs, SlotPlan, slot_state
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    ArrangementStep,
)

__all__ = ["arrange_progression"]


def _route_slot(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
) -> None:
    """Send one planned slot to exactly one route, which appends its step.

    The order is the contract: rest, fill, `NC`, comping, melody-bearing. A fill that
    cannot be filled falls through rather than returning, because the chord of the
    tune must not be lost to a texture - `texture_fill_step`'s own answer.

    The route reads the plan's `context` and `inputs`, so the slot facts and the
    arrangement facts keep the values the plan decided.
    """
    context = plan.context
    inputs = plan.inputs

    if plan.melody_alone == MELODY_ALONE_REST:
        rest_step(
            arrangements, slot, context,
            sings_here=plan.sings_here, silence=plan.silence,
        )
        return
    if plan.melody_alone == MELODY_ALONE_TEXTURE:
        if texture_fill_step(
            arrangements, slot, context,
            top_strings=inputs.top_strings,
            previous=previous_shape(arrangements),
        ):
            return
    if plan.melody_alone == MELODY_ALONE_NO_CHORD:
        no_chord_step(
            arrangements, slot, context,
            top_strings=inputs.top_strings,
            previous=previous_shape(arrangements),
        )
        return
    # --- The comping route: the guitar harmonises, somebody else sings ---
    # See `comping_step`: taken before `prepare_step` because there is no melody for
    # the guitar here, and only after the NC and melody-alone branches, which are the
    # cases with no harmony to state.
    if not plan.sings_here and not inputs.melody_only:
        if comping_step(
            arrangements, slot, context,
            chord_type=context.chord_type,
            melody_onsets=inputs.melody_onsets,
            parts=inputs.parts,
            harmony_family=inputs.harmony_family,
        ):
            return

    # Every melody-bearing route below pins a note, and a slot with none has left the
    # loop by now: the guard at the top refuses one the guitar is asked to sing, and
    # the comping block above always steps or returns.
    harmonised_step(arrangements, slot, plan)


def _loop_slots(
    progression: Sequence[Tuple[Optional[str], str, str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    slots: Optional[List[Slot]],
) -> List[Slot]:
    """One slot per triple, carrying that triple's own timing or None for an unplaced one.

    The walk's union wins when it exists, because its extra beats are the steps the
    thumb needs. Otherwise the list is read defensively - a short `timings` leaves
    the trailing steps unlocated - and, importantly, tolerating a *present but empty*
    entry: the corpus normalises its unplaced slots to `(None, None, None)`, so
    `float(beat)` here has to cope with None or the head path raises the moment it is
    allowed to delegate. That is the fourth time the two paths' differing timing
    types have cost something, and the first time it was a crash rather than a
    signature that would not typecheck.
    """
    if slots is not None:
        return slots

    def timing(index: int) -> Tuple[Optional[int], Optional[float], Optional[float]]:
        if timings is None or index >= len(timings):
            return (None, None, None)
        bar, beat, duration = timings[index]
        return (bar, None if beat is None else float(beat), duration)

    return [
        Slot(index=index, bar=bar, beat=beat, duration=duration)
        for index, (bar, beat, duration) in enumerate(
            timing(i) for i in range(len(progression))
        )
    ]


def arrange_progression(
    progression: Sequence[Tuple[Optional[str], str, str]],
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    non_chord_tone: str = "extension",
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
    texture: str = "uniform",
    bass: str = BASS_STYLE_AUTO,
    parts: str = PARTS_AUTO,
    harmony: str = HARMONY_AUTO,
    grid: str = GRID_DEFAULT,
    time_signature: TimeSignature = COMMON_TIME,
    melody_onsets: Optional[Container[int]] = None,
    options: Optional[ArrangeOptions] = None,
) -> List[ArrangementStep]:
    """
    Takes a progression of (Melody Note, Chord Quality, Name) tuples
    and computes the optimal voice-led arrangement.
    """
    _k = resolve_knobs(
        options,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        texture=texture,
        bass=bass,
        parts=parts,
        harmony=harmony,
        grid=grid,
        time_signature=time_signature,
        melody_onsets=melody_onsets,
        timings=timings,
    )
    top_strings = _k.top_strings
    non_chord_tone = _k.non_chord_tone
    fret_min = _k.fret_min
    fret_max = _k.fret_max
    texture = _k.texture
    bass = _k.bass
    harmony = _k.harmony
    grid = _k.grid
    beats_per_bar = _k.beats_per_bar
    beat_type = _k.beat_type
    resolved_grouping = _k.grouping
    melody_onsets = _k.melody_onsets
    timings = _k.timings
    bass_pcs = _k.bass_pcs
    slash_bass_cost_for = _k.slash_bass_cost

    arrangements: List[ArrangementStep] = []

    _p = resolve_policies(
        progression,
        parts_arg=_k.parts,
        texture=texture,
        bass=bass,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        grouping=resolved_grouping,
        timings=timings,
    )
    chosen_parts = _p.parts
    melody_voiced = _p.melody_voiced
    melody_only = _p.melody_only
    bass = _p.bass
    has_thumb = _p.has_thumb
    harmony_family = _p.harmony_family
    grid_pattern = _p.grid_pattern
    slots = _p.slots

    carried = Carried()

    loop = _loop_slots(progression, timings, slots)
    slot_inputs = SlotInputs(
        progression=progression,
        top_strings=top_strings,
        texture=texture,
        parts=chosen_parts,
        has_thumb=has_thumb,
        melody_only=melody_only,
        melody_voiced=melody_voiced,
        melody_onsets=melody_onsets,
        harmony_family=harmony_family,
        grid_pattern=grid_pattern,
        beats_per_bar=beats_per_bar,
        grouping=resolved_grouping,
        fret_min=fret_min,
        fret_max=fret_max,
        non_chord_tone=non_chord_tone,
        bass_pcs=bass_pcs,
        slash_bass_cost_for=slash_bass_cost_for,
    )
    for slot in loop:
        plan = slot_state(carried, slot, slot_inputs)
        if plan is None:
            continue
        _route_slot(arrangements, slot, plan)

    return arrangements
