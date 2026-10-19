"""One slot's request, as a value both step routes can share.

`harmonised_step` and `comping_step` take the same seventeen facts about a slot
and differ only in the three or four that name their own policy. This is the
shared part, so a route signature says what it *adds* rather than repeating the
request - and the stage helpers each route is split into can take one context
instead of threading a dozen keywords.

It sits at the bottom of the dependency order because it holds only stdlib and
`musthe` types: the accumulator (`arrangements`) stays a parameter, because that
is the route's output rather than its input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

from musthe import Note


@dataclass(frozen=True)
class SlotContext:
    """Everything one route needs to know about the slot it is deciding.

    `name`, `chord_type`, `note_str` and `melody_note` are what the caller asked
    for, not what a non-chord-tone strategy decided: a route may report a
    substituted harmony, and a context that carried the substitution would make the
    request unreadable.

    `bar`, `beat` and `duration` are Optional because a caller may not have placed
    the slot; the routes report that rather than inventing a position.
    """

    progression: Sequence[Tuple[Optional[str], str, str]]
    index: int
    name: str
    chord_type: str
    note_str: Optional[str]
    melody_note: Optional[Note]

    fret_min: int
    fret_max: int
    texture: str
    has_thumb: bool
    non_chord_tone: str

    bass_pcs: Optional[Mapping[int, Optional[int]]]
    slash_bass_cost_for: Optional[Callable[[Sequence[int], Optional[int]], int]]

    bar: Optional[int]
    beat: Optional[float]
    duration: Optional[float]
    role: str
    weight: int
