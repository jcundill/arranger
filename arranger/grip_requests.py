"""Chord-symbol parsing and grip request builders.

Everything that turns a written chord symbol into the canonical quality, root
pitch class and tone set a grip builder needs, plus the `Placement` requests the
searched families (`shell`, `drop2_6432`) hand to `place_shape`. Nothing here
generates voicings - it only reads the symbol and states what a search must find.
"""

from __future__ import annotations

from typing import Optional, Tuple

from musthe import Note

from .chords import ChordParser, parse_symbol
from .grip_place import Placement
from .grip_tables import SHELL_DEGREES
from .grip_templates import _SEARCHED_GRIPS, BASS_DEGREES_6432


def parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
    """The canonical quality and the full symbol for a chord name.

    The quality is what `grip_tables` indexes (`TONE_PRIORITY`, `SHELL_DEGREES`),
    and the symbol is what a caller reads back as `chord` on the step.
    """
    symbol = parse_symbol(name)
    if symbol is None:
        return None, name
    return symbol.quality, name


def chord_context(
    chord_name: Optional[str]
) -> Tuple[str, Optional[int], Tuple[int, ...]]:
    """The canonical quality, the root's pitch class, and the chord's tones **as
    degrees from that root**.

    The degrees are deliberately not absolute. Every grip builder wants to reason
    in intervals - "the 3rd of a minor 7th is three semitones up" - and only the
    final pitch placement wants an absolute note. Keeping one frame throughout means
    there is a single place (the search for a pitch at or below the soprano) where
    degrees become pitches.

    Note this is *not* ChordParser.get_chord_tones(chord_name), which returns absolute
    pitch classes. The tones are the full set for the quality, not the four the drop-2
    tables voice, so a shell or a duo is built from every tone the chord really has.

    A symbol asking for no chord has no quality, no root and no tones, which is how a
    caller tells "no chord here" from "a chord I could not voice".
    """
    symbol = parse_symbol(chord_name)
    if symbol is None:
        return "", None, ()
    root_pc = Note(f"{symbol.root}4").midi_note() % 12
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(symbol.quality, ())
    return symbol.quality, root_pc, tones


def _shell_request(
    quality: str,
    root_pc: int,
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Optional[Placement]:
    """What a shell asks the search for on one string set: three voices, and both guide tones.

    A shell cannot come from a stack, and the reason is not specific to the 6-4-3 shape:
    **a shell's notes are not in descending pitch order down the strings.** The tuning is
    not monotonic in the useful direction. The A string is tuned five semitones *above*
    the D string, and the D string five above the G, so a note fretted on the lower string
    can easily sound higher than its neighbour. A G7 shell under G3 is `2-3-0-x-x-x` - B2 on
    the A string, F3 on the D string, G3 on the G - and the A string is carrying the *lower*
    note while being the higher string. Any model that lays the voices on strings from the
    top down by pitch gets this backwards and finds nothing.

    So the shape is found by searching: the melody is held at `top_fret` on the soprano
    string and every combination of frets within the span limit is tried on the remaining
    strings, keeping the ones where the guide tones sound and nothing outside the chord
    does. This states the *request*; `place_shape` is what answers it, so this and every
    other searched family cannot drift apart on what a candidate may sound or on how two
    equally playable ones are ranked.

    Returns None when the chord has no shell pair - a quality `SHELL_DEGREES` does not
    know, or a set too small to hold three voices.
    """
    guide = SHELL_DEGREES.get(quality)
    if guide is None or len(strings) < 3:
        return None
    return Placement(
        grip="shell",
        strings=strings[:3],
        melody_midi=melody_midi,
        top_fret=top_fret,
        required=frozenset((root_pc + g) % 12 for g in guide),
    )


def _drop2_6432_request(
    root_pc: int,
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Placement:
    """What the 6-4-3-2 family asks the search for: four voices, and a root or a 5th underneath.

    It cannot come from the interval-laid drop-2 table for the reason 6-4-3 cannot, and
    the reason is structural: **this set skips the A string, so its strings are not in
    descending pitch order.** The D string is tuned a fifth above the low E, so the low E's
    note is frequently *not* the lowest sounding pitch, and a table that lays voices down
    by interval cannot express a shape whose bottom string is not the bottom voice.

    The extra rule is BASS_DEGREES_6432: the low E carries the chord's root or its 5th.
    That is the entire point of the shape, and it is also why the family needs a root at
    all - a rootless quality has nothing to measure the low E against, and gets nothing.
    """
    return Placement(
        grip="drop2_6432",
        strings=strings,
        melody_midi=melody_midi,
        top_fret=top_fret,
        required=frozenset(),
        lowest_pc_allowed=frozenset(
            (root_pc + degree) % 12 for degree in BASS_DEGREES_6432
        ),
    )


def _searched_request(
    grip: str,
    canonical: str,
    root_pc: Optional[int],
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Optional[Placement]:
    """What a **searched** family asks for on one string set, or None when it asks nothing.

    Every claim these families make is measured *from the root* - a shell states this
    chord's 3rd and 7th, and a 6-4-3-2 states the chord's function in the bass - so a chord
    whose root cannot be found gets nothing here. That is a limitation rather than a
    fallback: a shell is a claim about *this* chord, and guessing a guide tone is how a
    wrong note gets in.

    Returns None for a family this is not about, so a family listed in neither
    `_SEARCHED_GRIPS` nor `_LAYOUT_GRIPS` generates nothing rather than something nobody
    asked for.
    """
    if root_pc is None or grip not in _SEARCHED_GRIPS:
        return None
    if grip == "shell":
        return _shell_request(canonical, root_pc, strings, melody_midi, top_fret)
    return _drop2_6432_request(root_pc, strings, melody_midi, top_fret)
