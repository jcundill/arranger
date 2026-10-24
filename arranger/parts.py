"""The parts axis: which of melody / bass / chord the guitar takes.

`PART_MELODY`, `PART_BASS` and `PART_CHORD` are the vocabulary and `PART_NAMES`
their canonical order. The selection is **derived, never spelled**: the request's
six questions decide it (`options._request_parts`), so there is no argument to parse
here and no `auto` sentinel to expand.

`parts_have_melody`, `parts_have_bass`, `parts_have_chord` and
`parts_has_melody_only` are the one-line predicates the engine's route logic
reads, so a part question is stated once here rather than compared against
`PART_NAMES` at every call site.

No engine imports: this module is pure data and pure predicates, so it sits at
the top of the texture stack with nothing below it but `tuning`.
"""

from __future__ import annotations

from typing import Tuple

# The part names, in the order a canonical selection is written (the selection is
# a set - see the module docstring).
PART_MELODY = "melody"
PART_BASS = "bass"
PART_CHORD = "chord"

PART_NAMES: Tuple[str, ...] = (PART_MELODY, PART_BASS, PART_CHORD)


def parts_have_melody(parts: Tuple[str, ...]) -> bool:
    """Whether the guitar takes the tune.

    One predicate rather than a comparison against `PART_NAMES` at each call
    site, named for the musical question rather than the data: the engine's job
    changes completely depending on whether the tune is ours, because **the
    melody is what pins a voicing** - with no melody part there is no note to
    pin, which is why the comping generator takes none.

    **It is half of the engine's route, not the whole of it.** The route is
    asked **per slot** - `sings_here = parts_have_melody(parts) and a note
    sounds here` - so a melody-naming selection still comps the grid positions
    its tune does not articulate.
    """
    return PART_MELODY in parts


def parts_have_bass(parts: Tuple[str, ...]) -> bool:
    """Whether the guitar takes the bottom - the part the thumb realises.

    The part and the digit are different facts: a shape with no bass line still
    has its lowest note taken by the thumb (`docs/history/fingering.md` §2.5), so this
    asks about the music and not about the right hand.
    """
    return PART_BASS in parts


def parts_have_chord(parts: Tuple[str, ...]) -> bool:
    """Whether the guitar takes the harmonisation between melody and bass."""
    return PART_CHORD in parts


def parts_has_melody_only(parts: Tuple[str, ...]) -> bool:
    """Whether the selection takes the tune and no chord part.

    A melody-only request is the tune with no left hand under it; the same tune with
    a thumb under it is still melody-only. **The chord part is what this rules out,
    and the bass part is deliberately not** - the thumb has its own layer, and a line
    with a thumb under it is still one note's worth of left hand.
    """
    return PART_MELODY in parts and PART_CHORD not in parts
