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
from typing import Callable, Container, Mapping, Optional, Sequence, Tuple

from .bass import BASS_AUTO
from .grips import GRIP_PREFERENCE
from .textures import GRID_EVERY_NOTE, HARMONY_AUTO, MELODY_AUTO
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
    # Which bass **policy** the thumb line is written on: "none", "anchors" or "walk".
    # An axis of its own rather than a property of the texture, because the pattern is
    # the composer's choice and the set of patterns is open - see `BASS_STYLES` in
    # `bass.py`, where a new one is a row in a table.
    #
    # The default is the **sentinel** `BASS_AUTO` ("auto"), not the resolved "none",
    # for the same reason `melody`'s and `harmony`'s defaults are sentinels: it matches
    # `arrange_progression`'s keyword default, so the two spellings can be compared
    # field-by-field, and a default that disagreed with the keyword's would make every
    # slot-path call look like a caller who had passed both. The sentinel resolves from
    # the texture, so a bare options value leaves the thumb line exactly where the
    # keyword always left it. The field said "none" for its whole life and nothing
    # measured it, because the engine never read the field back out of the options -
    # which is what made `--bass` silently inert on `arranger head`; see the unpack in
    # `steps.py`.
    bass: str = BASS_AUTO
    # Which voices the guitar plays, from `MELODY_POLICIES` in `textures.py` (which
    # resolves the `auto` sentinel). `soprano` keeps the melody pinned to the soprano
    # string - the default, and the historical arrangement - and dropping it gives the
    # tune to another instrument, leaving the guitar a guide-tone comping part.
    #
    # **Named `melody` and carrying a voice list, which reads as a mistake** and is
    # left in place deliberately: the `harmony=` axis landed beside it and this one is
    # still a rename away (`docs/comping-styles.md` §6 Q2 and §8 Stage C), and a flag
    # called `melody` taking `"soprano,alto"` will mislead the next reader. Renaming it
    # before the question it raises is settled would trade one wrong name for another.
    #
    # An axis of its own, and orthogonal to `texture` and to `bass`, because those
    # answer different questions: where notes fall, and who plays the bottom. A band
    # setting is a *combination* -- `bass="none", melody="none"` is a bassist on the
    # root and a horn on the tune with the guitar between them -- so each is chosen
    # separately rather than as one mode. The default changes nothing that worked
    # before it.
    #
    # The default is the **sentinel** `MELODY_AUTO` ("auto"), not the resolved "guitar",
    # so that it matches `arrange_progression`'s keyword default and the two spellings
    # can be compared field-by-field. That comparison is load-bearing: `arrange_slots`
    # builds an `ArrangeOptions` and passes it, so a default that disagreed with the
    # keyword's would make every corpus call look like a caller who had passed both.
    # `bass` follows the same rule now, having spent its life as the counterexample:
    # its field default was the resolved "none" while the keyword's was the sentinel,
    # so the comparison could never be made and the field was never read back at all.
    # See the note beside its own field above.
    melody: str = MELODY_AUTO
    # Which **degrees** this part states when it is not singing, from `HARMONY_STYLES`
    # in `textures.py`: "guide" is the shipped comping shape (the 3rd and the 7th).
    #
    # A fourth axis, and orthogonal to the other three rather than another way of
    # spelling one of them - and that orthogonality is why it is separate from
    # `melody`. The three existing axes answer *how many* notes (from the voice
    # selection), *where* they fall (texture, and the rhythm grid to come) and *who
    # plays the bottom* (bass). None of them answers **what the part says about the
    # chord**, which is a different question: `guide` and `shell_root` both sound a
    # 3rd and a 7th, and differ in whether a root or 5th is stated underneath them.
    #
    # The default is the sentinel `HARMONY_AUTO` ("auto") rather than the resolved
    # "guide", for the same reason `melody` is: it matches `arrange_progression`'s
    # keyword default, so the two spellings can be compared field-by-field and a
    # default that disagreed would make every corpus call look like a caller who had
    # passed both. It resolves to `guide` because that is what the comping route has
    # always said, so the axis is **inert by default** and every existing arrangement
    # is unaffected.
    harmony: str = HARMONY_AUTO
    # Where a chord **falls** inside the bar, from `GRID_STYLES` in `textures.py`:
    # `every_note` (the default) places one wherever a melody note is, and the named
    # patterns place on beats and subdivisions instead.
    #
    # The fifth axis, and the one that completes a comping style: `harmony` says what
    # degrees a stab states, this says where it lands, and `bass` says what holds
    # underneath. None of the three implies either of the others - a full chord on
    # every beat and a guide-tone shell on the ands are all four combinations, and a
    # style name is a shorthand for one of them rather than a mode.
    #
    # The default is `every_note` **outright, with no `*_AUTO` sentinel** - a
    # deliberate departure from the convention `harmony`, `melody` and `bass` follow,
    # because `grid=auto` resolved to `every_note` unconditionally and was then never
    # read again, so it named the default rather than deferring to any context. It
    # still matches `arrange_progression`'s keyword default, so the two spellings can
    # be compared field-by-field, and `every_note` is what a score-imported head
    # already produced, so the axis is inert by default.
    grid: str = GRID_EVERY_NOTE
    beats_per_bar: int = 4
    # `Sequence`, not `List`, and that is load-bearing rather than stylistic: the
    # library and the corpus hold *different* timing types - `Tuple[int, float, ...]`
    # against `Tuple[Optional[int], ...]` placeholders for slots it could not place.
    # `List` is invariant so neither is assignable to the other and the two paths
    # could not share one signature; `Sequence` is covariant so both are accepted.
    # This is the third time list invariance in a signature has cost this library
    # something, and the fourth would not have been a surprise.
    timings: Optional[Sequence[Timing]] = None
    # Per-progression-index bass pitch class, for the slash-chord preference (rule C,
    # inherited from the removed corpus path). This is the field that lets a caller
    # delegate instead of running a second step loop: the corpus's only selection
    # difference from the library was *which candidates are considered*, and that is
    # data, not control flow. Absent or None for an index means no restriction, which
    # is exactly the library's own behaviour.
    bass_pcs: Optional[Mapping[int, Optional[int]]] = None
    # The ranking used to honour `bass_pcs`, passed in rather than imported:
    # `bass_cost` lives in `arranger.slots`, which reaches `decisions` through
    # `steps`, so a module-level import either way would be a cycle. It is a field
    # rather than a module global because a slash-bass preference is the only reason
    # to supply one, and making that visible at the call site is the point.
    #
    # Both halves are needed: `bass_pcs` says which pitch the caller wants, and this
    # says how near a candidate is to it. Neither alone narrows anything.
    bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]] = None
    # The progression indexes whose melody note **articulates** (an onset), for the
    # §9.2 reharmonise rule on the comping route: a non-chord melody note is
    # substituted where it begins, not under a held note and not where the tune is
    # silent. `None` means *every* slot is an onset - the honest default for a
    # hand-built progression that carries no timeline, so a bare
    # `arrange_progression(..., melody="alto,tenor")` still honours `--non-chord-tone`.
    # The head layer computes it from `headxml.melody_state`, which is the one place
    # that knows a note is sounding rather than merely in force.
    #
    # It sits beside `bass_pcs` rather than on the harmony axis because it is per-slot
    # *data* about the input, like the timings, not a policy a caller chooses.
    melody_onsets: Optional[Container[int]] = None
