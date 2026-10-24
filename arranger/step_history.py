"""Reading the arrangement's own history: the last sounding step and its shape.

A route appends to the arrangement it is reading, so *what the hand was still
holding* when this slot arrived is a question about the steps already emitted. The
answer lives here rather than in `routes` because the melody-bearing route and the
dispatch table read it too, and it is a fact about the arrangement rather than a way
of building a step.

It sits in the loop layer of the order - below the three modules that ask it
(`routes`, `harmonised_route`, `route_dispatch`) and above `step_types`, whose value
types it reads.
"""

from __future__ import annotations

from typing import List, Optional

from .step_types import ArrangementStep, Voicing


def last_sounding_step(
    arrangements: List[ArrangementStep],
) -> Optional[ArrangementStep]:
    """The last step whose shape the hand was actually holding.

    A position the guitar declined is emitted silent for the tab's line-up, but
    its all-muted voicing is not a shape anybody held: scoring the next shape's
    voice-leading against it would measure every candidate against fret 0,
    which is not a position the hand was ever in. While such positions were
    dropped entirely, the look-back found the last sounding step by accident;
    this is the same answer written down, so the selector's behaviour is
    unchanged by a hole appearing in the tab.
    """
    for step in reversed(arrangements):
        if step.silence is None:
            return step
    return None


def previous_shape(arrangements: List[ArrangementStep]) -> Optional[Voicing]:
    """The voicing of the last sounding step, or None.

    A rest carries an all-muted voicing, so asking the last step directly would
    hand the selector a shape nobody held; the melody may also have ended, in
    which case there is nothing to hold at all.
    """
    previous = last_sounding_step(arrangements)
    return previous.voicing if previous is not None else None

