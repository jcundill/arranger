"""The knobs an arrangement is made with, as one value.

`arrange_progression` grew to nine parameters, and the two entry points that call
it had grown their own near-copies of the same list. Every one of them is defaulted,
so no existing caller is affected; this is here because a keyword list that has to
be threaded through three layers is a list someone will forget to update in the
fourth.

Frozen, because an options object that can be mutated halfway through arranging is
worse than the keyword list it replaces - the failure would depend on *when* it was
written. Build a second one instead.

Every field's default is the value that call has always used, so
`ArrangeOptions()` is the historical arrangement. `arrange_progression` still
accepts the same keywords directly; see its docstring for how the two interact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

from .grips import GRIP_PREFERENCE
from .tuning import MELODY_STRING_CHOICES_FULL, NECK_FRET_MAX, NECK_FRET_MIN

# `(bar, beat, duration)` for one slot. `bar` is signed - a pickup is negative -
# `beat` is within the bar, and both are Optional because a caller may simply not
# know where its notes fall. `None` throughout is "no rhythm supplied", which the
# texture rules read as "every slot is a principal note".
Timing = Tuple[Optional[int], Optional[float], Optional[float]]


@dataclass(frozen=True)
class ArrangeOptions:
    """Every knob `VoiceLeadingEngine.arrange_progression` reads."""

    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL
    non_chord_tone: str = "extension"
    fret_min: int = NECK_FRET_MIN
    fret_max: int = NECK_FRET_MAX
    grips: Tuple[str, ...] = GRIP_PREFERENCE
    texture: str = "uniform"
    beats_per_bar: int = 4
    # `Sequence`, not `List`, and that is load-bearing rather than stylistic: the
    # library and the corpus hold *different* timing types - `Tuple[int, float, ...]`
    # against `Tuple[Optional[int], ...]` placeholders for slots it could not place.
    # `List` is invariant so neither is assignable to the other and the two paths
    # could not share one signature; `Sequence` is covariant so both are accepted.
    # This is the third time list invariance in a signature has cost this library
    # something, and the fourth would not have been a surprise.
    timings: Optional[Sequence[Timing]] = None
    # Per-progression-index bass pitch class, for the Weimar slash-chord preference
    # (rule C). This is the field that lets `wjazzd.arrange_slots` delegate instead of
    # running a second step loop: the corpus's only selection difference from the
    # library is *which candidates are considered*, and that is data, not control
    # flow. Absent or None for an index means no restriction, which is exactly the
    # library's own behaviour.
    bass_pcs: Optional[Mapping[int, Optional[int]]] = None
    # The ranking used to honour `bass_pcs`, passed in rather than imported:
    # `bass_cost` lives in `wjazzd` and `wjazzd` imports `decisions`, so a
    # module-level import either way would be a cycle. It is a field rather than a
    # module global because the *only* caller that supplies one is the corpus, and
    # making that visible at the call site is the point.
    #
    # Both halves are needed: `bass_pcs` says which pitch the caller wants, and this
    # says how near a candidate is to it. Neither alone narrows anything.
    bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]] = None
