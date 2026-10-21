"""One slot's request, as a value both step routes can share.

`harmonised_step` and `comping_step` take the same facts about a slot and
differ only in the ones that name their own policy. This module holds the small,
focused value objects each fact group becomes, plus `SlotContext` as their
composition.

It sits at the bottom of the dependency order because it holds only stdlib and
`musthe` types: the accumulator (`arrangements`) stays a parameter, because that
is the route's output rather than its input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

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
    """What the caller asked for: chord name, quality, melody note.

    `name`, `chord_type`, `note_str` and `melody_note` are what the caller
    asked for, not what a non-chord-tone strategy decided: a route may report a
    substituted harmony, and a context that carried the substitution would make
    the request unreadable. Every route reads harmony.
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

    progression: Sequence[Tuple[Optional[str], str, str]]
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
class SlotContext:
    """Everything one route needs to know about the slot it is deciding.

    Composed of small, focused value objects so each route reads only the fact
    groups it actually uses:

    - `timing`, `harmony`, `identity`, `state` — every route
    - `fret_min`, `fret_max` — comping, harmonised, melody-alone
    - `texture`, `has_thumb`, `non_chord_tone` — harmonised
    - `bass_pcs`, `slash_bass_cost_for` — comping only
    """

    timing: SlotTiming
    harmony: SlotHarmony
    identity: SlotIdentity
    state: SlotState
    fret_min: int
    fret_max: int
    texture: str
    has_thumb: bool
    non_chord_tone: str
    bass_pcs: Optional[Mapping[int, Optional[int]]] = None
    slash_bass_cost_for: Optional[Callable[[Sequence[int], Optional[int]], int]] = None
