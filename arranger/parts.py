"""The parts axis: which of melody / bass / chord the guitar takes.

`PARTS_AUTO`, `PART_MELODY`, `PART_BASS`, `PART_CHORD` are the vocabulary, and
`parse_parts` / `resolve_parts` expand the `auto` sentinel and canonicalise a
named selection to `PART_NAMES` order (order carries no meaning - a parts
selection is a set, not a sequence).

`parts_have_melody`, `parts_have_bass`, `parts_have_chord` and
`parts_has_melody_only` are the one-line predicates the engine's route logic
reads, so a part question is stated once here rather than compared against
`PART_NAMES` at every call site.

No engine imports: this module is pure data and pure predicates, so it sits at
the top of the texture stack with nothing below it but `tuning`.
"""

from __future__ import annotations

from typing import List, Tuple

PARTS_AUTO = "auto"

# The part names, in the order a canonical selection is written (order carries
# no meaning - see `parse_parts`).
PART_MELODY = "melody"
PART_BASS = "bass"
PART_CHORD = "chord"

PART_NAMES: Tuple[str, ...] = (PART_MELODY, PART_BASS, PART_CHORD)


def parse_parts(argument: str) -> Tuple[str, ...]:
    """A `parts` argument as a canonical tuple of part names.

    **Order carries no meaning**, so the result is canonicalised to
    `PART_NAMES` order: `parts=chord,bass` and `parts=bass,chord` are one
    request and must not produce two arrangements.

    `auto` is the shipped default and names every part - the tune on top, the
    thumb underneath, and a chord part whose arity `texture=` states. Any other
    spelling is a comma-separated list of the names above.

    Raises `ValueError` on an unknown name, on an empty argument, and on `auto`
    combined with named parts. The rule is the library's: a spelling nobody
    recognises is a question, and answering it by dropping a part would hand
    back an arrangement missing something nobody asked it to drop. `none` is
    refused for the same reason rather than expanded: it named a voice
    selection, and a selection that names no part has no line to state.
    """
    text = argument.strip().lower()
    if text == PARTS_AUTO:
        return (PARTS_AUTO,)
    if not text:
        raise ValueError(
            f"parts is empty; expected any of {PART_NAMES}, or 'auto'"
        )
    chosen: List[str] = []
    for part in text.split(","):
        name = part.strip().lower()
        if name == PARTS_AUTO:
            raise ValueError(
                f"'auto' cannot be combined with named parts in {argument!r}; "
                f"it means all of them on its own"
            )
        if name not in PART_NAMES:
            raise ValueError(
                f"Unknown part {name!r}; expected any of {PART_NAMES}, or 'auto'"
            )
        if name not in chosen:
            chosen.append(name)
    if not chosen:
        raise ValueError(
            f"parts resolved to nothing in {argument!r}; the guitar has to "
            f"take at least one part"
        )
    return tuple(name for name in PART_NAMES if name in chosen)


def resolve_parts(parts: Tuple[str, ...]) -> Tuple[str, ...]:
    """The parts to actually take: `auto` expanded, everything else as parsed.

    `auto` expands to `PART_NAMES`, which is what keeps the axis inert: an
    arrangement naming no parts builds the tune over a full chord part, the
    arrangement this library has always built.
    """
    if parts == (PARTS_AUTO,):
        return PART_NAMES
    return parts


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

    `parts=melody` is the tune with no left hand under it, and
    `parts=melody,bass` is the same line with a thumb under it. **The chord part
    is what this rules out, and the bass part is deliberately not** - the thumb
    has its own axis (`bass_style=`), and a line with a thumb under it is still
    one note's worth of left hand.
    """
    return PART_MELODY in parts and PART_CHORD not in parts
