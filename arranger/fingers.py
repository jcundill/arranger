"""The left hand's budget: how many fingers a fret vector needs, and how far it reaches.

A generated grip is bounded by its family's span, but a **step** can be wider than any
grip: `bass_place.place_bass` and `bass_merge._takes_the_ring` merge a thumb note into a
shape the hand is still holding, and a merged hand can need a fifth finger or reach
further than the hand spans. `can_fret` is that check - four fingers and five frets, two
independent refusals - and it is the only thing here the engine calls.

It hangs off `tuning` alone: nothing below it decides the playability of a grip, no
selector reads it, and no renderer knows it exists.
"""

from __future__ import annotations

from typing import Iterable

# The four fingers of the left hand, in the order they are numbered on a chord diagram.
# `can_fret` bounds a merged hand by their count; no engine code asks *which* finger holds
# a fret, so the fingers are not named individually.
FINGERS = (1, 2, 3, 4)

#: The widest the hand reaches: five frets, index to pinky. Not a preference and not a grip's
#: span - it is the hand's own size, which is why it bounds a *step* as well as a shape.
#: `GRIP_MAX_SPAN` (4 or 5, per family) is a stricter bound on the shapes the engine
#: generates, and `tests/test_grip_tables.py` holds every one of them below this one.
MAX_HAND_SPAN = 5


def fingers_needed(frets: Iterable[int]) -> int:
    """How many left-hand fingers a fret vector asks for: its distinct frets at 1 or above.

    Frets are grouped exactly - one finger holds every note at one fret, so a shape with
    two notes on fret 3 costs one finger and not two - and fret 0 is an open string that
    costs none. Stated over a bare vector rather than a `Voicing` because the caller that
    needs it has two shapes merged into one hand and no single `Voicing` to point at: see
    `can_fret`.
    """
    return len({fret for fret in frets if fret >= 1})


def hand_span(frets: Iterable[int]) -> int:
    """How far apart the hand's outermost fingers are: max minus min over frets at 1 or above.

    An open string takes no finger and so does not widen the hand - a fretted note a third
    above one is still the bottom of the hand - and a muted string is not part of the shape
    at all. Stated over a bare vector for the reason `fingers_needed` gives.
    """
    fretted = [fret for fret in frets if fret >= 1]
    return max(fretted, default=0) - min(fretted, default=0)


def can_fret(frets: Iterable[int]) -> bool:
    """False when a fret vector is beyond the left hand: a fifth fret, or a sixth reach.

    Two independent refusals:

    - **one finger, one fret** bounds the *count* - `fingers_needed(frets) <= 4`;
    - **the hand's own size** bounds how far apart the outermost fingers are -
      `hand_span(frets) <= MAX_HAND_SPAN`.

    Neither implies the other, and that is the trap this predicate exists to close: a
    merged walking-bass vector can need three fingers and still put the thumb seven frets
    under the shape (`[1, 8, -1, 8, 9, -1]`), which the count passes and the hand cannot.
    `docs/history/open-issues.md` item 5 holds the figures, and
    `tests/test_fingers.py::TestTheHandsReach` holds the rule.

    `bass_place.place_bass` and `bass_merge._takes_the_ring` are the callers, and both ask
    it of a **merged** vector rather than of a shape: the first before it picks a string
    under a shape the hand is holding, the second before it lets a struck note keep
    ringing under the next shape. Nothing here reads a generated grip, whose own bounds are
    stricter.
    """
    return fingers_needed(frets) <= len(FINGERS) and hand_span(frets) <= MAX_HAND_SPAN
