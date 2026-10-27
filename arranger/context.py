"""One slot's request, as a value both step routes can share.

`harmonised_step` and `comping_step` take the same facts about a slot and
differ only in the ones that name their own policy. This module holds the small,
focused value objects each fact group becomes, plus `SlotContext` as their
composition.

It sits at the bottom of the dependency order because it holds only stdlib and
`musthe` types: the accumulator (`arrangements`) stays a parameter, because that
is the route's output rather than its input. The metre's own rhythm is the one
fact group it cannot hold - `grid.Rhythm` sits above it - so a slot's rhythm
travels on `slot_plan.SlotRhythmFacts` instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from musthe import Note


@dataclass(frozen=True)
class SlotTiming:
    """Where a slot falls in the bar: bar number, beat within it, duration.

    `bar`, `beat` and `duration` are Optional because a caller may not have
    placed the slot; the routes report that rather than inventing a position.
    Every route reads timing.
    """

    bar: Optional[int]
    beat: Optional[float]
    duration: Optional[float]


@dataclass(frozen=True)
class SlotHarmony:
    """What the caller asked for: chord name, its quality, and the melody note.

    `name`, `chord_type`, `note_str` and `melody_note` are what the caller
    asked for, not what a non-chord-tone strategy decided: a route may report a
    substituted harmony, and a context that carried the substitution would make
    the request unreadable. Every route reads harmony.

    `chord_type` is **derived** from `name` by `chords.quality_of` rather than being a
    second input, so the two cannot disagree; it stays a field because the routes ask
    "is this an `NC` slot?" of one value.
    """

    name: str
    chord_type: str
    note_str: Optional[str]
    melody_note: Optional[Note]


@dataclass(frozen=True)
class SlotIdentity:
    """Which slot in the progression: the full sequence and this slot's index.

    Every route reads identity.
    """

    progression: Sequence[Tuple[Optional[str], str]]
    index: int


@dataclass(frozen=True)
class SlotState:
    """What the plan decided for this slot: its role, metric weight, attack.

    Every route reads state.
    """

    role: str
    weight: int
    #: Whether the chord part is a **new attack** here rather than a shape still
    #: ringing. `slot_plan._chord_attacks` decides it once per slot, from the request's
    #: chord rhythm and the slot's own melody; the routes stamp it on the step so the
    #: renderers can tell a re-strike from a hold. See `ArrangementStep.chord_attack`.
    chord_attack: bool = False


@dataclass(frozen=True)
class SlotArrangementFacts:
    """Who plays, and what the tune and the request are.

    The parts selection (`parts`, `melody_only`, `melody_voiced`), the texture the
    chord part states, whether a thumb line runs anywhere in the tune (`has_thumb`),
    the non-chord-tone strategy, and the progression itself. Read by the plan, the
    grip resolution and the melody-alone decision - everything that asks *who* is
    playing rather than *where*.
    """

    progression: Sequence[Tuple[Optional[str], str]]
    texture: str
    parts: Tuple[str, ...]
    melody_only: bool
    melody_voiced: bool
    non_chord_tone: str
    has_thumb: bool


@dataclass(frozen=True)
class SlotNeckFacts:
    """Where on the neck a shape may sit, and which strings are preferred.

    The search window (`fret_min`, `fret_max`) and the string order a melody pins its
    soprano from (`top_strings`). The window is a **preference and never a filter**:
    a shape outside it is still played, and `voicing_cost` records that it was. Read
    by the comping, harmonised and melody-alone routes.
    """

    fret_min: int
    fret_max: int
    top_strings: Tuple[int, ...]


@dataclass(frozen=True)
class SlotBassFacts:
    """The written slash bass a slot must honour **before** selection.

    A requested bass pitch class per slot, keyed by slot index (`bass_pcs`). `None`
    unless the progression's symbols ask for one, and absent or `None` for an index
    means no restriction. Read by the comping and melody-bearing routes; the ranking
    that honours it is `chords.slash_bass_cost`, which `decisions` calls directly.
    """

    bass_pcs: Optional[Mapping[int, Optional[int]]] = None


@dataclass(frozen=True)
class SlotContext:
    """Everything one route needs to know about the slot it is deciding.

    Composed of small, focused value objects so each route reads only the fact
    groups it actually uses:

    - `timing`, `harmony`, `identity`, `state` — every route
    - `neck` — comping, harmonised, melody-alone
    - `arrangement` — harmonised, comping, and every plan decision
    - `bass` — comping and harmonised, where a written slash bass is honoured

    The metre's own rhythm is the one group it cannot hold (`grid.Rhythm` sits above
    this module), so that travels on `slot_plan.SlotPlan.rhythm`.
    """

    timing: SlotTiming
    harmony: SlotHarmony
    identity: SlotIdentity
    state: SlotState
    arrangement: SlotArrangementFacts
    neck: SlotNeckFacts
    bass: SlotBassFacts


@dataclass(frozen=True)
class HarmonisedRouteFacts:
    """What the melody-bearing route reads about one slot.

    A projection of `SlotContext`: only the fields `harmonised_step` and its
    helpers actually read, so the route cannot accidentally depend on a fact
    group it does not use.
    """

    timing: SlotTiming
    harmony: SlotHarmony
    identity: SlotIdentity
    state: SlotState
    neck: SlotNeckFacts
    bass: SlotBassFacts
    non_chord_tone: str
    texture: str
    has_thumb: bool
    melody_only: bool


@dataclass(frozen=True)
class CompingRouteFacts:
    """What the comping route reads about one slot.

    A projection of `SlotContext`: only the fields `comping_step` and its
    helpers actually read, so the route cannot accidentally depend on a fact
    group it does not use.
    """

    timing: SlotTiming
    harmony: SlotHarmony
    identity: SlotIdentity
    state: SlotState
    neck: SlotNeckFacts
    bass: SlotBassFacts
    texture: str
    parts: Tuple[str, ...]
    has_thumb: bool
    non_chord_tone: str
    melody_voiced: bool


def project_harmonised(context: SlotContext) -> HarmonisedRouteFacts:
    """The facts the melody-bearing route needs, projected from a full context."""
    return HarmonisedRouteFacts(
        timing=context.timing,
        harmony=context.harmony,
        identity=context.identity,
        state=context.state,
        neck=context.neck,
        bass=context.bass,
        non_chord_tone=context.arrangement.non_chord_tone,
        texture=context.arrangement.texture,
        has_thumb=context.arrangement.has_thumb,
        melody_only=context.arrangement.melody_only,
    )


def project_comping(context: SlotContext) -> CompingRouteFacts:
    """The facts the comping route needs, projected from a full context."""
    return CompingRouteFacts(
        timing=context.timing,
        harmony=context.harmony,
        identity=context.identity,
        state=context.state,
        neck=context.neck,
        bass=context.bass,
        texture=context.arrangement.texture,
        parts=context.arrangement.parts,
        has_thumb=context.arrangement.has_thumb,
        non_chord_tone=context.arrangement.non_chord_tone,
        melody_voiced=context.arrangement.melody_voiced,
    )


@dataclass(frozen=True)
class MinimalRouteFacts:
    """What a thin route (rest, bass alone, texture fill, NC) reads about a slot.

    Only `timing`, `harmony` and `state` — nothing from `arrangement`, `neck`,
    `bass` or `identity`. A route that only stamps a step's bar, beat, chord and
    role has no business reading the search window, the slash bass or the parts
    selection.
    """

    timing: SlotTiming
    harmony: SlotHarmony
    state: SlotState


def project_minimal(context: SlotContext) -> MinimalRouteFacts:
    """The facts a thin route needs, projected from a full context."""
    return MinimalRouteFacts(
        timing=context.timing,
        harmony=context.harmony,
        state=context.state,
    )
