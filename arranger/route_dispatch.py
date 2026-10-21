"""Which route takes a planned slot: the branch table, apart from the loop.

`movement` walks the slots and asks this module about each one. The routes
themselves live in `routes` (the rest, the texture fill, the `NC` bar and the
comping shape) and in `harmonised_route` (the melody-bearing step); what this
module owns is **the order they are asked in**, which is a contract rather than a
preference. The entries run most specific first - nothing above the thumb, a
texture fill, an `NC` bar, the comping route - and end in the melody-bearing step,
which claims every slot that reaches it.

The two entries that can *decline* a slot they claimed are the texture fill and
the comp, and for the same reason: a texture that cannot be filled and a chord
position with nothing to state must not cost the tune its chord, so the next entry
is asked instead. That fall-through is what the order is for.

`tests/test_route_dispatch.py` holds the order, and measures that each entry fires
on a progression a caller can ask for - an entry that no request can reach is a
branch nobody can see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

from .bass import Slot
from .decisions import (
    MELODY_ALONE_BASS,
    MELODY_ALONE_NO_CHORD,
    MELODY_ALONE_REST,
    MELODY_ALONE_TEXTURE,
)
from .harmonised_route import harmonised_step
from .routes import (
    bass_alone_step,
    comping_step,
    no_chord_step,
    previous_shape,
    rest_step,
    texture_fill_step,
)
from .slot_plan import SlotPlan
from .tuning import ArrangementStep

__all__ = ["Route", "ROUTES", "dispatch_step"]


@dataclass(frozen=True)
class Route:
    """One entry in the dispatch order: when it claims a slot, and what it emits.

    `claims` is the precondition and `emit` the answer, both reading the plan the
    slot loop already built. `emit` returns False when the route claimed the slot
    but cannot honour it, and `dispatch_step` then asks the next entry.
    """

    name: str
    claims: Callable[[SlotPlan], bool]
    emit: Callable[[List[ArrangementStep], Slot, SlotPlan], bool]


def _claims_no_upper_voices(plan: SlotPlan) -> bool:
    """Nothing above the thumb sounds at this slot: a lone note, or nothing."""
    return plan.melody_alone in (MELODY_ALONE_BASS, MELODY_ALONE_REST)


def _emit_no_upper_voices(
    arrangements: List[ArrangementStep], slot: Slot, plan: SlotPlan
) -> bool:
    """The two answers for a slot with nothing above the thumb: the note, or nothing.

    They are the **same situation read by different parts**, which is why they are one
    branch rather than two: nothing above the thumb sounds here, and only the bass
    line's own claim on the slot makes it a note. A rest where the bass asked for one
    would drop the thumb, which is the one thing the bass grid exists to place - and a
    thumb where the line has no note is not a choice, it is a refusal to report.
    """
    if plan.melody_alone == MELODY_ALONE_BASS:
        bass_alone_step(arrangements, slot, plan.context)
        return True
    rest_step(
        arrangements, slot, plan.context,
        sings_here=plan.sings_here, silence=plan.silence,
    )
    return True


def _claims_texture(plan: SlotPlan) -> bool:
    """A fill, or a target no shell can sound: the tune alone, over a stated harmony."""
    return plan.melody_alone == MELODY_ALONE_TEXTURE


def _emit_texture_fill(
    arrangements: List[ArrangementStep], slot: Slot, plan: SlotPlan
) -> bool:
    """A fill that cannot be filled falls through rather than returning.

    The chord of the tune must not be lost to a texture - `texture_fill_step`'s own
    answer - so a False here hands the slot to the comping entry or to the
    melody-bearing step, which will state the harmony instead.
    """
    return texture_fill_step(
        arrangements, slot, plan.context,
        top_strings=plan.inputs.top_strings,
        previous=previous_shape(arrangements),
    )


def _claims_no_chord(plan: SlotPlan) -> bool:
    """An `NC` bar: melody and no harmony, so there is nothing to voice."""
    return plan.melody_alone == MELODY_ALONE_NO_CHORD


def _emit_no_chord(
    arrangements: List[ArrangementStep], slot: Slot, plan: SlotPlan
) -> bool:
    """The tune alone on an `NC` bar, carrying no chord clause."""
    no_chord_step(
        arrangements, slot, plan.context,
        top_strings=plan.inputs.top_strings,
        previous=previous_shape(arrangements),
    )
    return True


def _claims_comping(plan: SlotPlan) -> bool:
    """The guitar harmonises while somebody else sings.

    Taken before the melody-bearing step because there is no melody for the guitar
    here, and only after the entries above, which are the cases with no harmony to
    state at all.
    """
    return not plan.sings_here and not plan.inputs.melody_only


def _emit_comping(
    arrangements: List[ArrangementStep], slot: Slot, plan: SlotPlan
) -> bool:
    """A comp that cannot state its chord falls through to the melody-bearing step.

    See `comping_step`: a `False` means the position kept no chord, which is not a
    reason to drop the slot.
    """
    return comping_step(
        arrangements, slot, plan.context,
        chord_type=plan.context.harmony.chord_type,
        melody_onsets=plan.inputs.melody_onsets,
        parts=plan.inputs.parts,
        harmony_family=plan.inputs.harmony_family,
    )


def _claims_always(_plan: SlotPlan) -> bool:
    """The melody-bearing step takes every slot still standing.

    This is the entry that makes "exactly one route emits a step per slot"
    structural rather than a property to check: every melody-bearing route below
    pins a note, and a slot with none has left the loop by now - the plan refuses
    one the guitar is asked to sing, and the comping entry above always steps or
    returns.
    """
    return True


def _emit_melody(
    arrangements: List[ArrangementStep], slot: Slot, plan: SlotPlan
) -> bool:
    """Prepare, select, demote, emit: the route that pins the tune to the soprano."""
    harmonised_step(arrangements, slot, plan)
    return True


#: The dispatch order, most specific first. **Do not reorder.** `no_upper_voices`
#: before `comping` keeps the thumb's own slot from being read as a chord position;
#: `texture_fill` before `melody_bearing` is what stops a fill from being voiced as
#: a chord; `no_chord` before `comping` is what keeps an `NC` bar from being
#: reharmonised. `tests/test_route_dispatch.py` pins the sequence.
ROUTES: Tuple[Route, ...] = (
    Route("no_upper_voices", _claims_no_upper_voices, _emit_no_upper_voices),
    Route("texture_fill", _claims_texture, _emit_texture_fill),
    Route("no_chord", _claims_no_chord, _emit_no_chord),
    Route("comping", _claims_comping, _emit_comping),
    Route("melody_bearing", _claims_always, _emit_melody),
)


def dispatch_step(
    arrangements: List[ArrangementStep], slot: Slot, plan: SlotPlan
) -> str:
    """Send one planned slot to exactly one route, which appends its step.

    Returns the name of the route that took the slot. A route that claims the slot
    and declines it hands it on; the last entry claims unconditionally, so the loop
    below always returns and a slot always leaves here with exactly one step.

    The routes read the plan's `context` and `inputs`, so the slot facts and the
    arrangement facts keep the values the plan decided.
    """
    for route in ROUTES:
        if route.claims(plan) and route.emit(arrangements, slot, plan):
            return route.name
    # Unreachable: `_claims_always` is the last entry and its emit returns True.
    raise AssertionError("no route claimed the slot")
