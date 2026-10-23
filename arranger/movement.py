"""The step loop: one progression in, one arrangement out.

`arrange_progression` is the entry point. It turns `(melody, quality, name)`
triples into `ArrangementStep`s by asking `route_dispatch` which of the five routes
takes each slot - a rest, a texture fill, a no-chord melody-alone step, a comping
shape, or a harmonised melody step - and merging the walking bass in afterwards.

This module owns the **sequencing**: the knobs resolved once, the slot list, the
loop, and the bass merge. The branch table is `route_dispatch`; one step's
candidates are built in `step_prepare`; the melody-bearing route is in
`harmonised_route`. `VoiceLeadingEngine` is a facade of one-line delegates onto this
module and `step_prepare`. The engine imports `grips`, `cost`, `chords` and the
rest directly and does not import `steps` at all. `slots.arrange_slots` delegates
through the class, so the imported-head path and the hand-built one still run one
loop rather than two.
"""

from __future__ import annotations

from typing import Container, List, Optional, Sequence, Tuple

from .bass import Slot
from .bass_merge import carry_bass
from .context import SlotArrangementFacts, SlotBassFacts, SlotNeckFacts
from .grips import MELODY_STRING_CHOICES_FULL
from .grouping import COMMON_TIME, TimeSignature
from .options import DEFAULT_REQUEST, ArrangeOptions, Request
from .resolution import felt_beat_timings, resolve_knobs, resolve_policies
from .route_dispatch import dispatch_step
from .slot_plan import Carried, SlotInputs, SlotRhythmFacts, slot_state
from .step_types import ArrangementStep
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
)

__all__ = ["arrange_progression"]


def _stated(
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    index: int,
) -> Optional[Tuple[Optional[int], Optional[float], Optional[float]]]:
    """The entry at `index`, or `None` where there is none: a short list, or a stated absence."""
    if timings is None or index >= len(timings):
        return None
    return timings[index]


def _placed(
    entry: Optional[Tuple[Optional[int], Optional[float], Optional[float]]],
) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    """The slot's timing: the entry's own, with a float beat - or `(None, None, None)`.

    An absent entry and a `(None, None, None)` entry mean the same thing to the metric
    layer, "this position is not on the metre", which it reports as `-1` rather than as a
    weak beat.
    """
    if entry is None:
        return (None, None, None)
    bar, beat, duration = entry
    return (bar, None if beat is None else float(beat), duration)


def _loop_slots(
    progression: Sequence[Tuple[Optional[str], str, str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    slots: Optional[List[Slot]],
) -> List[Slot]:
    """One slot per triple, carrying that triple's own timing or None for an unplaced one.

    Read defensively at both ends: a short `timings` leaves the trailing steps unlocated,
    and a *present* entry may still be `(None, None, None)` - the importer pads with one
    where the tune is silent, and a caller may say so deliberately. Both mean the same
    thing here, "this position is not on the metre", which is what `metric_weight`
    reports as `-1` rather than as a weak beat.
    """
    if slots is not None:
        return slots

    return [
        Slot(index=index, bar=bar, beat=beat, duration=duration)
        for index, (bar, beat, duration) in enumerate(
            _placed(_stated(timings, i)) for i in range(len(progression))
        )
    ]


def _timeline(
    progression: Sequence[Tuple[Optional[str], str, str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    beats_per_bar: int,
) -> Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]:
    """What the caller supplied, or the metre's own layout for a progression that did not.

    Decided once, because two consumers read it and they must agree: the walk's union
    (inside `resolve_policies`) and the slot loop. A supplied timeline - the importer's, or
    a caller's, including stated absences - is used exactly as given.
    """
    if timings is not None:
        return timings
    return felt_beat_timings(len(progression), beats_per_bar)


def arrange_progression(
    progression: Sequence[Tuple[Optional[str], str, str]],
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    non_chord_tone: str = "extension",
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
    request: Request = DEFAULT_REQUEST,
    time_signature: TimeSignature = COMMON_TIME,
    melody_onsets: Optional[Container[int]] = None,
    options: Optional[ArrangeOptions] = None,
) -> List[ArrangementStep]:
    """
    Takes a progression of (Melody Note, Chord Quality, Name) tuples
    and computes the optimal voice-led arrangement.

    What to play is asked as a `request=` - the six questions - and the
    implementation axes (`texture`, `bass`, `parts`) are
    spelled through `options=ArrangeOptions(...)`, which is the one door to them.
    A keyword given beside `options=` raises rather than being silently ignored.

    `timings=` says where each entry falls. Omitted, the progression is laid out on the
    metre's own felt beats - one entry per beat of the bar - so a hand-built progression
    is arranged as the bars it names. A *supplied* timeline is used as given, including
    a `(None, None, None)` entry, which states that a position is deliberately unplaced.
    """
    _k = resolve_knobs(
        options,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        request=request,
        time_signature=time_signature,
        melody_onsets=melody_onsets,
        timings=timings,
    )
    timeline = _timeline(progression, _k.timings, _k.beats_per_bar)
    arrangements: List[ArrangementStep] = []

    _p = resolve_policies(
        progression,
        parts_arg=_k.parts,
        texture=_k.texture,
        bass=_k.bass,
        chord_rhythm=_k.request.chord_rhythm,
        bass_rhythm=_k.request.bass_rhythm,
        chord_fills=_k.request.chord_fills,
        beats_per_bar=_k.beats_per_bar,
        beat_type=_k.beat_type,
        grouping=_k.grouping,
        timings=timeline,
    )
    carried = Carried()
    loop = _loop_slots(progression, timeline, _p.slots)
    slot_inputs = SlotInputs(
        arrangement=SlotArrangementFacts(
            progression=progression, texture=_k.texture, parts=_p.parts,
            melody_only=_p.melody_only, melody_voiced=_p.melody_voiced,
            non_chord_tone=_k.non_chord_tone, has_thumb=_p.has_thumb,
        ),
        rhythm=SlotRhythmFacts(
            beats_per_bar=_k.beats_per_bar, grouping=_k.grouping,
            chord_rhythm=_p.chord_rhythm, chord_fills=_p.chord_fills,
            melody_onsets=_k.melody_onsets,
        ),
        neck=SlotNeckFacts(
            fret_min=_k.fret_min, fret_max=_k.fret_max, top_strings=_k.top_strings
        ),
        bass=SlotBassFacts(bass_pcs=_k.bass_pcs),
    )
    for slot in loop:
        plan = slot_state(carried, slot, slot_inputs)
        if plan is None:
            continue
        dispatch_step(arrangements, slot, plan)

    # The thumb's notes ring until something replaces them. Last, because it reads the
    # steps the routes emitted rather than deciding anything about them - and after
    # selection, so the held note cannot enter the cost tuple.
    carry_bass(arrangements)
    return arrangements
