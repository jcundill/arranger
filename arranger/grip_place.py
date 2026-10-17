"""Where a shape sits on the neck: the placement search and its memo.

A family states what its shape must sound (`Placement`), and this module answers
where it can be fretted - the shared search over span-legal fret combinations
(`search_shape`), the layout that lays a template on its strings
(`place_template`), and the memo that makes a repeated request free. It sits
below `grips`, which builds the requests and calls both placers.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, Iterable, List, Optional, Tuple

from .grip_tables import GRIP_MAX_SPAN, supported_string_sets
from .tuning import STANDARD_TUNING, GuitarFretboard, Voicing


def frets_in_span(
    strings: Tuple[int, ...], lo: int, hi: int, limit: int
) -> Iterable[Tuple[int, ...]]:
    """Every fret tuple on `strings` inside `lo`..`hi` whose span is at most `limit`.

    Written as a recursive generator rather than one nested loop per arity, because
    `notes` is a parameter and the alternative is a separate copy of this search for
    every arity - which is exactly how the melody-bearing shell and this one drifted
    apart the first time they were written separately.

    The window narrows as it recurses (`first - limit` .. `first + limit`), so the
    search is still exhaustive over span-legal combinations and never materialises the
    ones the span rule would reject.
    """
    if not strings:
        yield ()
        return
    rest = strings[1:]
    for first in range(lo, hi + 1):
        window_lo = max(lo, first - limit)
        window_hi = min(hi, first + limit)
        for tail in frets_in_span(rest, window_lo, window_hi, limit):
            yield (first,) + tail


@dataclass(frozen=True)
class Placement:
    """
    One family's request of the placement search: where to sit, and what must sound.

    A *value*, so a caller states the request and the search answers it - which is what
    lets the non-contiguous families share one placement instead of each owning a nest of
    loops. `strings` is ordered from the soprano downwards, as `_string_sets_for` returns
    it, so `strings[0]` is the string the melody is pinned to and `melody_midi` is that
    pin's pitch.

    `required` is the family's claim about which of the chord's tones have to be present,
    as pitch classes; **empty means the family makes no claim** and any subset of the
    chord's own tones will do, which is the drop-2 & 4 rule - it states four chord tones
    and leaves which ones to the string set. `lowest_pc_allowed` is the separate claim about
    the **bottom** voice, for the families whose shape is defined by its bass (a 6-4-3-2
    states the chord's function, so its lowest note is a root or a 5th); None asks nothing.

    `voices` is how many of `strings` the shape sounds, counting down from the soprano, and
    None means all of them. It exists because a template may be shorter than the set it sits
    on - a two-note pair on a three-string shell set - and the shape then has to leave the
    rest of the set **muted** rather than placing a voice there.
    """

    grip: str
    strings: Tuple[int, ...]
    melody_midi: int
    top_fret: int
    required: FrozenSet[int]
    lowest_pc_allowed: Optional[FrozenSet[int]] = None
    voices: Optional[int] = None


#: The string sets a candidate may sound, as one set for the membership test `candidate`
#: makes. Built from `supported_string_sets()`, which is the playability invariant stated
#: from the shape's side, so no producer can put a shape on strings the tables never
#: offered - a set is a musical decision, and this is what makes it one rather than an
#: accident of which strings a producer happened to fill in.
_SUPPORTED_STRING_SETS = frozenset(supported_string_sets())


def candidate(
    placement: Placement, frets: List[int], allowed: Optional[FrozenSet[int]]
) -> Optional[Voicing]:
    """
    The one place a set of frets becomes a candidate voicing, or None when it is not one.

    Every rule a candidate has to satisfy is here, so no family can be placed by a path that
    skips one: the melody sounds and is the **highest** sounding note, every fret is on the
    board, the fret span is within `GRIP_MAX_SPAN[placement.grip]`, the family's tone claim
    (`required`) and bass claim (`lowest_pc_allowed`) hold, nothing outside `allowed`
    sounds - `allowed` being None when the family makes no claim about the chord's tones at
    all, which is what a template-laid shape is: the template *is* the claim, and the
    interval family is free to sound a key tone under a passing note - and the sounding
    strings are one `supported_string_sets()` entry.

    Both proposers call it: the search (`search_shape`, reached through the memo
    `place_shape`), which enumerates frets, and the layouts (`place_template`), which
    compute them from an interval template. One producer per shape, one rule set for all of
    them - a rule stated in a producer reaches only the families that producer serves.

    `frets` is a full board vector, and only its entries for `placement.strings` are read.
    The `voices` strings from the soprano down are the shape and must each carry a fret
    between 0 and 18; **the rest of the set must be muted**. Both halves matter: a computed
    -1 is a note below its string's open pitch rather than a mute, and reading that as
    unused thins the shape into strings the tables never offered.
    """
    strings = placement.strings
    top_fret = placement.top_fret
    limit = GRIP_MAX_SPAN[placement.grip]

    set_frets = [frets[string] for string in strings]
    voices = len(strings) if placement.voices is None else placement.voices
    used, unused = set_frets[:voices], set_frets[voices:]
    if any(fret < 0 or fret > 18 for fret in used):
        return None
    if any(fret != -1 for fret in unused):
        return None
    if frozenset(strings[:voices]) not in _SUPPORTED_STRING_SETS:
        return None
    if not used or max(used) - min(used) > limit:
        return None
    sounded = strings[:voices]
    active = used
    midis = sorted(
        GuitarFretboard.fret_to_midi(string, fret)
        for string, fret in zip(sounded, active)
    )
    if midis[-1] != GuitarFretboard.fret_to_midi(strings[0], top_fret):
        return None
    pcs = {midi % 12 for midi in midis}
    if not placement.required <= pcs:
        return None
    if allowed is not None and not pcs <= allowed:
        return None
    if (
        placement.lowest_pc_allowed is not None
        and midis[0] % 12 not in placement.lowest_pc_allowed
    ):
        return None
    return Voicing(
        frets=list(frets),
        top_fret=top_fret,
        avg_fret=sum(active) / len(active),
        grip=placement.grip,
        bass_pc=midis[0] % 12,
    )


def place_template(
    template: List[int],
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
    grip: str,
) -> Optional[Voicing]:
    """
    Fits an interval template onto a string set, or returns None if it will not play.

    The voices go on the strings from the top down, so the template's order is the
    order they are heard - which is what makes this a *layout*: the shape is the template,
    not a claim about which of the chord's tones sound. A family placed this way asks
    nothing of the tone set, and that is deliberate rather than lax: the template is the
    whole claim, and `interval` is free to sound a key tone under a passing note.

    The frets are computed rather than searched, because the template and the string set
    fix each one. What they are then held to is `candidate`, the same rules every searched
    shape is held to, so the melody-on-top rule reaches the template families too.

    The span is checked on the frets actually placed, not as "within N of the soprano".
    Those are not the same condition: bounding each finger to five frets either side of
    the soprano permits a span of ten. That is reachable in practice - the low E and D
    strings are five semitones apart in tuning, so a 6-4-3 shell that sounds correctly
    on them can sit at frets 8 and 0.

    Strings in the set the template does not use are left muted, which is how a
    three-note shell sits inside a four-string set and how 6-4-3 leaves the A string
    alone without saying anything special about it.
    """
    if len(template) > len(strings):
        return None

    frets = [-1] * len(STANDARD_TUNING)
    frets[strings[0]] = top_fret
    for position, offset in enumerate(template[1:], start=1):
        string_idx = strings[position]
        frets[string_idx] = (
            melody_midi + offset - STANDARD_TUNING[string_idx].midi_note()
        )

    return candidate(
        Placement(
            grip=grip,
            strings=strings,
            melody_midi=melody_midi,
            top_fret=top_fret,
            required=frozenset(),
            # The template's own voices, which may be fewer than the set offers - the rest
            # of the set is muted.
            voices=len(template),
        ),
        frets,
        # No claim about the chord's tones - the template is the claim.
        None,
    )


def search_shape(
    placement: Placement, allowed: Optional[FrozenSet[int]] = None
) -> Optional[Voicing]:
    """
    The one shape `placement` asks for on its string set, or None when it will not play.

    `place_shape` is what the generators call; this is the search they are answered with.

    An enumerator over `frets_in_span`, and `candidate` is what decides: the melody is
    held at its own fret and every combination of the other frets within
    `GRIP_MAX_SPAN[placement.grip]` of it is tried, so if a playable shape exists in this
    position this finds it, and "found nothing" means there is none.

    A window that runs off the end of the board yields nothing, which is the melody being
    too high to voice here rather than a shape being refused: `get_octave_down_candidates`
    is what covers a melody above the neck window.

    **Ties are broken by fret spread, then by position**, so the shape a player would pick
    wins over the first one the search reaches; and of two still equal the earlier one
    survives, which is the enumeration order `frets_in_span` yields in. Ranking the
    survivors is not cosmetic: an unranked search returns whatever comes first, so a family
    can look as though it is never selected when it is merely ranked last.
    """
    strings = placement.strings
    top_fret = placement.top_fret
    limit = GRIP_MAX_SPAN[placement.grip]

    lo = max(0, top_fret - limit)
    hi = top_fret + limit
    if hi > 18:
        return None

    best: Optional[Tuple[Tuple[int, float], Voicing]] = None
    for tail in frets_in_span(strings[1:], lo, hi, limit):
        frets = [-1] * len(STANDARD_TUNING)
        for string, fret in zip(strings, (top_fret,) + tail):
            frets[string] = fret
        voicing = candidate(placement, frets, allowed)
        if voicing is None:
            continue
        key = (voicing.fret_span(), voicing.avg_fret)
        if best is None or key < best[0]:
            best = (key, voicing)
    return best[1] if best else None


#: Everything a `Voicing` carries, with the fret vector as a tuple: what `_searched_shape`
#: and `_comping_palette` store. A result is snapshotted rather than stored as a `Voicing`
#: so that no caller can write through a memo - `bass_merge.attach_bass` merges the walking
#: bass by writing into the chosen shape's fret vector and `bass_pc`.
ShapeSnapshot = Tuple[
    Tuple[int, ...], int, float, str, Optional[int], str, Optional[int], Optional[int]
]


def snapshot(voicing: Voicing) -> ShapeSnapshot:
    """One `Voicing` as the tuple the memos store, so the object cannot be written to."""
    return (
        tuple(voicing.frets),
        voicing.top_fret,
        voicing.avg_fret,
        voicing.grip,
        voicing.bass_pc,
        voicing.role,
        voicing.bass_midi,
        voicing.bass_string,
    )


def voicing_from_snapshot(snapshot: ShapeSnapshot) -> Voicing:
    """A **fresh** `Voicing` with a **fresh** fret vector, rebuilt from `snapshot`."""
    frets, top_fret, avg_fret, grip, bass_pc, role, bass_midi, bass_string = snapshot
    return Voicing(
        frets=list(frets),
        top_fret=top_fret,
        avg_fret=avg_fret,
        grip=grip,
        bass_pc=bass_pc,
        role=role,
        bass_midi=bass_midi,
        bass_string=bass_string,
    )


@lru_cache(maxsize=None)
def _searched_shape(
    placement: Placement, allowed: Optional[FrozenSet[int]]
) -> Optional[ShapeSnapshot]:
    """
    `search_shape` remembered: one request searched once, and read back after that.

    The search is a **pure function of the request**. `placement` and `allowed` carry
    everything it reads, and the rest - `GRIP_MAX_SPAN`, `STANDARD_TUNING`,
    `supported_string_sets()` - is fixed when this module is imported. That is what makes
    the key sufficient and the memo need no invalidation, and it is why those tables must
    not be reassigned at runtime.

    The same request is asked over and over: a repeated melody degree, a repeated bar, and
    the target, fill and retry paths each asking again for what was answered already. The
    counts are in `docs/history/generated-grips.md` §4.
    """
    found = search_shape(placement, allowed)
    if found is None:
        return None
    return snapshot(found)


def place_shape(
    placement: Placement, allowed: Optional[FrozenSet[int]] = None
) -> Optional[Voicing]:
    """
    The one shape `placement` asks for, answered through the memo.

    **A fresh `Voicing` with a fresh fret vector on every call.** The engine writes into
    the shape it chose - `bass_merge.attach_bass` sets `frets[string]` and `bass_pc` for the
    walking bass - so returning the stored object would let one step's thumb line rewrite
    the shape the next step is handed.

    The rules, the ranking and the enumeration order are `search_shape`'s docstring; the
    memo changes nothing but how often the search runs, which `tests/test_placement.py`
    holds it to.
    """
    snapshot = _searched_shape(placement, allowed)
    if snapshot is None:
        return None
    return voicing_from_snapshot(snapshot)
