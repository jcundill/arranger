"""The knobs an arrangement is made with, as one value.

`arrange_progression` grew to nine parameters, and the two entry points that call
it had grown their own near-copies of the same list. Every one of them is defaulted,
so no existing caller is affected; this is here because a keyword list that has to
be threaded through three layers is a list someone will forget to update in the
fourth.

Frozen, because an options object that can be mutated halfway through arranging is
worse than the keyword list it replaces - the failure would depend on *when* it was
written. Build a second one instead.

Every field's default is the same value `arrange_progression`'s keyword defaults to, so
`ArrangeOptions()` asks for exactly what `arrange_progression(progression)` builds. That
call still
accepts the same keywords directly; see its docstring for how the two interact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Container, Mapping, Optional, Sequence, Tuple

from .bass_rules import (
    BASS_STYLE_AUTO,
)
from .grid import GRID_DEFAULT
from .grouping import COMMON_TIME, TimeSignature
from .harmony import HARMONY_AUTO
from .parts import PARTS_AUTO
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
    texture: str = "uniform"
    # Which bass **style** the thumb line is written on, as a comma-separated list of
    # note rules: "none", "root", or the full "root,5th,approach,nearest". An axis of its
    # own rather than a property of the texture, because the note rules are the
    # composer's choice and the set is open - see `BASS_RULE_ROLES` in `bass.py`, where a
    # new one is a row in a table.
    #
    # The default is the **sentinel** `BASS_STYLE_AUTO` ("auto"), not the resolved "none",
    # for the same reason `parts`'s and `harmony`'s defaults are sentinels: it matches
    # `arrange_progression`'s keyword default, so the two spellings can be compared
    # field-by-field, and a default that disagreed with the keyword's would make every
    # slot-path call look like a caller who had passed both. The sentinel resolves from
    # the texture, so a bare options value leaves the thumb line where the keyword
    # default leaves it. `steps.py` reads the field back, which is what keeps
    # `--bass-style` live on the `arranger head` path.
    bass: str = BASS_STYLE_AUTO
    # Which of melody / bass / chord the guitar takes, from `parts.py` (where
    # `parse_parts` owns the vocabulary and `resolve_parts` expands the `auto`
    # sentinel to all three). The melody is the tune on top, the bass is the bottom
    # the thumb realises, and the chord is the harmonisation between them - whose
    # **arity** `texture=` states and whose **degree order** `harmony=` states.
    #
    # The three are parts in a band, not voices in a stack, and a band setting is a
    # *combination* of axes rather than a mode: `parts=melody,chord` with
    # `bass_style=root` is a bassist on the root and a horn on the tune, with the
    # guitar comping under it. `parts=auto` - the default - names every part.
    #
    # A part the caller names is a request for it to sound, and a policy named for a
    # part the selection leaves out is refused naming the part that would work. The
    # arithmetic `melody + bass + chord <= RIGHT_HAND_STRINGS` is a precondition:
    # `parts=melody,bass` with `texture=chord3` is five strings and is refused before
    # anything is generated.
    #
    # The default is the **sentinel** `PARTS_AUTO` ("auto"), not the resolved part
    # list, so that it matches `arrange_progression`'s keyword default and the two
    # spellings can be compared field-by-field. That comparison is load-bearing:
    # `arrange_slots` builds an `ArrangeOptions` and passes it, so a default that
    # disagreed with the keyword's would make every corpus call look like a caller who
    # had passed both. `bass` and `harmony` follow the same rule. See the note beside
    # `bass` above.
    parts: str = PARTS_AUTO
    # Which **degrees** this part states when it is not singing, from `HARMONY_STYLES`
    # in `harmony.py`: "guide" is the shipped comping shape (the 3rd and the 7th).
    #
    # A fourth axis, and orthogonal to the other three rather than another way of
    # spelling one of them - and that orthogonality is why it is separate from
    # `parts`. The three existing axes answer *how many* notes (from the voice
    # selection), *where* they fall (texture, and the rhythm grid to come) and *who
    # plays the bottom* (bass). None of them answers **what the part says about the
    # chord**, which is a different question: `guide` and `shell_root` both sound a
    # 3rd and a 7th, and differ in whether a root or 5th is stated underneath them.
    #
    # The default is the sentinel `HARMONY_AUTO` ("auto") rather than the resolved
    # "guide", for the same reason `parts` is: it matches `arrange_progression`'s
    # keyword default, so the two spellings can be compared field-by-field and a
    # default that disagreed would make every corpus call look like a caller who had
    # passed both. It resolves to `guide` because that is what the comping route has
    # always said, so the axis is **inert by default** and every existing arrangement
    # is unaffected.
    harmony: str = HARMONY_AUTO
    # Where a chord **falls** inside the bar, from `GRID_STYLES` in `grid.py`:
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
    # deliberate departure from the convention `harmony`, `parts` and `bass` follow,
    # because `grid=auto` resolved to `every_note` unconditionally and was then never
    # read again, so it named the default rather than deferring to any context. It
    # still matches `arrange_progression`'s keyword default, so the two spellings can
    # be compared field-by-field, and `every_note` is what a score-imported head
    # already produced, so the axis is inert by default.
    grid: str = GRID_DEFAULT
    # The metre as one value: the count, the denominator and the grouping. The
    # denominator is not decoration - a beat is `4 / beat_type` quarters, so the
    # count alone says which beats exist but not how long one lasts. The grouping is
    # validated against the count when the signature is built, because 12/8 and 12/4
    # share a count and are different bars. A hand-built progression that declares
    # none gets `COMMON_TIME`, which is the metre every bare call had.
    time_signature: TimeSignature = COMMON_TIME
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
    # The ranking that honours `bass_pcs` is passed in rather than imported:
    # `slash_bass_cost` lives in `arranger.slots`, which reaches `decisions` through
    # `steps`, so a module-level import either way would be a cycle. It is a field
    # rather than a module global because a slash-bass preference is the only reason
    # to supply one, and making that visible at the call site is the point.
    #
    # Both halves are needed: `bass_pcs` says which pitch the caller wants, and this
    # says how near a candidate is to it. Neither alone narrows anything.
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]] = None
    # The progression indexes whose melody note **articulates** (an onset), for the
    # §9.2 reharmonise rule on the comping route: a non-chord melody note is
    # substituted where it begins, not under a held note and not where the tune is
    # silent. `None` means *every* slot is an onset - the honest default for a
    # hand-built progression that carries no timeline, so a bare
    # `arrange_progression(..., parts=chord)` still honours `--non-chord-tone`.
    # The head layer computes it from `headxml.melody_state`, which is the one place
    # that knows a note is sounding rather than merely in force.
    #
    # It sits beside `bass_pcs` rather than on the harmony axis because it is per-slot
    # *data* about the input, like the timings, not a policy a caller chooses.
    melody_onsets: Optional[Container[int]] = None
