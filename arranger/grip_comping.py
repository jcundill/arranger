"""Comping shape generation: melody-free voicings for the guitar's comping part.

Everything that turns a chord quality into a set of melody-free comping voicings
is here. Unlike the melody-bearing generators, these shapes carry no tune on the
soprano string - they are the guitarist's part when somebody else sings. The
palette is memoised on the request, so a repeated request returns the same shapes
without re-enumerating them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .grip_place import frets_in_band, frets_in_span, snapshot, voicing_from_snapshot
from .grip_requests import chord_context
from .grip_tables import COMPING_MAX_SPAN, comping_string_sets
from .grip_templates import _shell_voicing
from .step_types import Voicing
from .tuning import NECK_FRET_MAX, NECK_FRET_MIN, GuitarFretboard


@dataclass(frozen=True)
class CompingRequest:
    """One melody-free comping shape request, as a value.

    The six fields are exactly what the enumeration reads - the chord, the neck
    window, the arity, the bass-voice flag and the home band - so the memo key and
    the request cannot drift apart. `frozen` also makes it hashable, which is what
    lets `_comping_palette` cache on the request itself rather than a reconstructed
    tuple.

    **`band` is the comp's register, and it changes what a palette *is*.** Absent
    (`None`) the palette keeps one shape per string set, which is the palette every
    caller got before the comp line existed. Present, it keeps one shape per **top
    tone**, because the comp line chooses which tone is on top and a palette that
    states only one of them cannot express the choice. See
    `_search_comping_voicings`.
    """

    chord_name: Optional[str] = None
    fret_min: int = NECK_FRET_MIN
    fret_max: int = NECK_FRET_MAX
    notes: int = 3
    bass_voice: bool = False
    band: Optional[Tuple[int, int]] = None


def _comping_collapse_key(
    frets: Tuple[int, ...],
    band: Tuple[int, int],
    fret_min: int,
    fret_max: int,
) -> Tuple[int, int, float, int]:
    """Which of several shapes stating one top tone a banded palette keeps.

    The key is `(outside the window, outside the band, |avg_fret - band middle|,
    span)`, most significant first:

    - **the window comes first**, so the band cannot override the caller's stated
      neck: a top tone with an in-window shape keeps that one, and the band only
      ranks the shapes the window already allows;
    - **then the band**, because the comp lives in it and a shape outside it is the
      last resort rather than the point;
    - **then the middle**, which is what makes the register the line reads back;
    - **then the span**, so two shapes equally placed keep the tighter one - the
      rule the bandless key applies alone.

    The band is a *preference* in exactly the way the window is: a tone reachable
    only outside it still enters the palette, which is what keeps the fill able to
    climb toward a melody and keeps a chord from losing a tone.

    The band test is `grip_place.frets_in_band` - **every fret, not the average** -
    the same predicate `comp_line.LineShape` reads, so the shape kept per top tone is
    one the line will actually walk.
    """
    avg = sum(frets) / len(frets)
    outside_window = 0 if all(fret_min <= fret <= fret_max for fret in frets) else 1
    outside_band = 0 if frets_in_band(frets, band) else 1
    middle = (band[0] + band[1]) / 2
    return (outside_window, outside_band, abs(avg - middle), max(frets) - min(frets))


def _search_comping_voicings(request: CompingRequest) -> List[Voicing]:
    """Guide-tone comping shapes: the chord stated **without** the melody on top.

    This is the guitarist's part when somebody else has the tune - a horn in front of
    the band - which is why it takes no melody argument at all. Every other candidate
    in this module is built around pinning the melody to the soprano string; this is
    the one that has none to pin.

    **It is the same exhaustive search with nothing held at the top.** A shell is already
    a claim about the chord's 3rd and 7th rather than about the tune, so the search needed
    no new rule: `frets_in_span` tries every fret combination on the remaining strings and
    the candidate keeps the ones where both guide tones sound and nothing outside the chord
    does. Only the top fret is searched too rather than fixed by a melody, and because the
    window is exactly `COMPING_MAX_SPAN` the search stays exhaustive within the invariant.

    The family is the arity's own, read from `comping_string_sets`: a pair is a `duo`, a
    three-voice shape is a `shell`, and a one-note inner voice takes the `duo` tops.
    `notes` is the **arity asked for**, and it is honoured rather than treated as a
    preference: `2` is the alto-and-tenor comping pair, `3` the shell.
    """
    canonical, root_pc, tones = chord_context(request.chord_name)
    if root_pc is None:
        return []

    limit = COMPING_MAX_SPAN
    hi = min(request.fret_max + limit, 18)
    lo = max(0, request.fret_min - limit)

    valid: List[Voicing] = []
    band = request.band
    by_top: Dict[int, Tuple[Tuple[Any, ...], Voicing]] = {}
    for used in comping_string_sets(request.notes, request.bass_voice):
        best: Optional[Tuple[Any, Voicing]] = None
        for frets in frets_in_span(used, lo, hi, limit):
            midis = sorted(
                GuitarFretboard.fret_to_midi(string, fret)
                for string, fret in zip(used, frets)
            )
            found = _shell_voicing(
                used,
                frets,
                midis,
                canonical,
                root_pc,
                tones,
                request.notes,
                request.bass_voice,
            )
            if found is None:
                continue
            if band is None:
                key: Tuple[Any, ...] = (
                    max(frets) - min(frets), sum(frets) / len(frets)
                )
                if best is None or key < best[0]:
                    best = (key, found)
                continue
            key = _comping_collapse_key(
                frets, band, request.fret_min, request.fret_max
            )
            held = by_top.get(midis[-1])
            if held is None or key < held[0]:
                by_top[midis[-1]] = (key, found)
        if best is not None:
            valid.append(best[1])
    if band is not None:
        valid = [
            entry[1]
            for _top, entry in sorted(
                by_top.items(), key=lambda item: (item[1][0], item[0])
            )
        ]
    return valid


@lru_cache(maxsize=None)
def _comping_palette(request: CompingRequest) -> Tuple[Any, ...]:
    """`_search_comping_voicings` remembered: one request enumerated once, read back after.

    The enumeration is a **pure function of the request**, and the request is exactly
    what it reads: the chord, the neck window, the arity, the bass-voice flag and the
    home band. A different band is a different request, so two comps in two registers
    do not read each other's palette.

    The same request is asked repeatedly: every slot of a comping bar, every head of a
    sweep, and every caller that arranges a head another caller has already arranged.
    """
    return tuple(
        snapshot(voicing)
        for voicing in _search_comping_voicings(request)
    )


def get_comping_voicings_for(request: CompingRequest) -> List[Voicing]:
    """The comping shapes for one request, answered through the memo.

    **A fresh list of fresh `Voicing`s on every call**, which is why this is a wrapper
    around the memo rather than the memoised function itself: `decisions.select_step_voicing`
    hands one of these objects back and `bass_merge.attach_bass` then writes the walked
    thumb into its fret vector and `bass_pc`. Returning the stored objects would let one
    step's bass line rewrite the palette the next step is offered.
    """
    return [
        voicing_from_snapshot(snap)
        for snap in _comping_palette(request)
    ]


def get_comping_voicings(
    chord_name: Optional[str] = None,
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    notes: int = 3,
    bass_voice: bool = False,
) -> List[Voicing]:
    """The primitive spelling of `get_comping_voicings_for`, kept for callers.

    It builds the request the object entry point takes, so the two spellings cannot
    enumerate different shapes.
    """
    return get_comping_voicings_for(CompingRequest(
        chord_name=chord_name,
        fret_min=fret_min,
        fret_max=fret_max,
        notes=notes,
        bass_voice=bass_voice,
    ))
