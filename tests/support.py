"""Shared fixtures for the test suite.

Every helper here was, at some point, copy-pasted between two test files with a
docstring saying roughly *"written here rather than imported so this file stays
independent"*. That is a reasonable instinct for a test that genuinely needs its
own fixture, and the wrong one for a fixture whose whole content is "derive
`top_fret` and `avg_fret` the way the engine does" - four files had that, and they
had already begun to drift.

What is **not** here, deliberately:

* a helper two files both want but which reads better in one of them - the walked
  line's `names(chords, onsets)` in `test_bass` and a step's thumb note in
  `test_walking_bass` share a name and nothing else, so both stay local;

Every fixture here builds a value by hand rather than by running the engine, which
is the point: a test that arranges a progression and then asserts on the result is
testing the engine against itself.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from arranger import PITCH_CLASS_NAMES, ArrangementStep, Voicing

#: The 119 hand-written drop-2 templates, keyed by the degree their top voice states.
#: This is `grips.DROP2_INTERVAL_SETS` moved out of the engine, where it was paired
#: positionally with `grips.DEGREE_OFFSETS_FROM_ROOT`: it is a *witness*, so it belongs
#: beside the assertion that reads it rather than shipping in the library. Each entry is
#: `[0, offset2, offset3, offset4]`, semitones below the soprano.
#:
#: The degrees are written lowest first for readability, and that carries no claim - the
#: witness is keyed, so only the degree-to-shape pairing is asserted anywhere.
WITNESS: Dict[str, Dict[int, List[int]]] = {
    "maj7": {
        0: [0, -5, -8, -13],
        4: [0, -5, -9, -16],
        7: [0, -7, -8, -15],
        11: [0, -7, -11, -16],
    },
    "6": {
        0: [0, -5, -8, -15],
        4: [0, -7, -9, -16],
        7: [0, -7, -10, -15],
        9: [0, -5, -9, -14],
    },
    "m7": {
        0: [0, -5, -9, -14],
        3: [0, -5, -8, -15],
        7: [0, -7, -9, -16],
        10: [0, -7, -10, -15],
    },
    "m7b5": {
        0: [0, -6, -9, -14],
        3: [0, -5, -9, -15],
        6: [0, -6, -8, -15],
        10: [0, -7, -10, -16],
    },
    "dim7": {
        0: [0, -6, -9, -15],
        3: [0, -6, -9, -15],
        6: [0, -6, -9, -15],
        9: [0, -6, -9, -15],
    },
    "m6": {
        0: [0, -5, -9, -15],
        3: [0, -6, -8, -15],
        7: [0, -7, -10, -16],
        9: [0, -6, -9, -14],
    },
    "mMaj7": {
        0: [0, -5, -9, -13],
        3: [0, -4, -8, -15],
        7: [0, -7, -8, -16],
        11: [0, -8, -11, -16],
    },
    "7": {
        0: [0, -5, -8, -14],
        4: [0, -6, -9, -16],
        7: [0, -7, -9, -15],
        10: [0, -6, -10, -15],
    },
    "7b9": {
        0: [0, -8, -11, -14],
        1: [0, -6, -9, -15],
        4: [0, -6, -9, -15],
        7: [0, -6, -9, -15],
        10: [0, -6, -9, -15],
    },
    "7alt": {
        0: [0, -8, -11, -14],
        1: [0, -5, -9, -15],
        4: [0, -6, -8, -15],
        8: [0, -7, -10, -16],
        10: [0, -6, -9, -14],
    },
    "maj9": {
        0: [0, -8, -10, -13],
        2: [0, -7, -10, -15],
        4: [0, -5, -9, -14],
        7: [0, -5, -8, -15],
        11: [0, -7, -9, -16],
    },
    "m9": {
        0: [0, -9, -10, -14],
        2: [0, -7, -11, -16],
        3: [0, -5, -8, -13],
        7: [0, -5, -9, -16],
        10: [0, -7, -8, -15],
    },
    "9": {
        0: [0, -8, -10, -14],
        2: [0, -7, -10, -16],
        4: [0, -6, -9, -14],
        7: [0, -5, -9, -15],
        10: [0, -6, -8, -15],
    },
    "6/9": {
        0: [0, -8, -10, -15],
        2: [0, -7, -10, -17],
        4: [0, -7, -9, -14],
        7: [0, -5, -10, -15],
        9: [0, -5, -7, -14],
    },
    "13": {
        0: [0, -3, -8, -14],
        4: [0, -7, -9, -18],
        7: [0, -9, -10, -15],
        9: [0, -5, -11, -14],
        10: [0, -3, -6, -13],
    },
    "maj": {
        0: [0, -8, -12, -17],
        4: [0, -9, -12, -16],
        7: [0, -7, -12, -15],
    },
    "m": {
        0: [0, -9, -12, -17],
        3: [0, -8, -12, -15],
        7: [0, -7, -12, -16],
    },
    "aug": {
        0: [0, -8, -12, -16],
        4: [0, -8, -12, -16],
        8: [0, -8, -12, -16],
    },
    "sus4": {
        0: [0, -7, -12, -17],
        5: [0, -10, -12, -17],
        7: [0, -7, -12, -14],
    },
    "sus2": {
        0: [0, -10, -12, -17],
        2: [0, -7, -12, -14],
        7: [0, -7, -12, -17],
    },
    "add9": {
        0: [0, -8, -10, -17],
        2: [0, -7, -10, -14],
        4: [0, -4, -9, -14],
        7: [0, -5, -7, -15],
    },
    "madd9": {
        0: [0, -9, -10, -17],
        2: [0, -7, -11, -14],
        3: [0, -3, -8, -13],
        7: [0, -5, -7, -16],
    },
    "7sus4": {
        0: [0, -5, -7, -14],
        5: [0, -7, -10, -17],
        7: [0, -7, -9, -14],
        10: [0, -5, -10, -15],
    },
    "7b5": {
        0: [0, -6, -8, -14],
        4: [0, -6, -10, -16],
        6: [0, -6, -8, -14],
        10: [0, -6, -10, -16],
    },
    "7#5": {
        0: [0, -4, -8, -14],
        4: [0, -6, -8, -16],
        8: [0, -8, -10, -16],
        10: [0, -6, -10, -14],
    },
    "7#11": {
        0: [0, -6, -8, -14],
        4: [0, -6, -10, -16],
        6: [0, -6, -8, -14],
        10: [0, -6, -10, -16],
    },
    "7b13": {
        0: [0, -4, -8, -14],
        4: [0, -6, -8, -16],
        8: [0, -8, -10, -16],
        10: [0, -6, -10, -14],
    },
    "maj7#11": {
        0: [0, -6, -8, -13],
        4: [0, -5, -10, -16],
        6: [0, -6, -7, -14],
        11: [0, -7, -11, -17],
    },
    "m9b5": {
        0: [0, -9, -10, -14],
        2: [0, -8, -11, -16],
        3: [0, -5, -9, -13],
        6: [0, -4, -8, -15],
        10: [0, -7, -8, -16],
    },
}


def make_voicing(
    frets: List[int],
    grip: str = "drop2",
    bass_midi: Optional[int] = None,
    bass_string: Optional[int] = None,
) -> Voicing:
    """A `Voicing` over a raw fret list, with the derived fields filled in.

    `top_fret` and `avg_fret` are computed the way `VoiceLeadingEngine` computes
    them, because a hand-built fixture that leaves them at their defaults is a
    fixture whose `fret_span()` and voice-leading costs do not mean anything.

    Frets of -1 are muted. An all-muted list is legal and yields 0 / 0.0.
    """
    active = [f for f in frets if f >= 0]
    return Voicing(
        frets=list(frets),
        top_fret=max(active) if active else 0,
        avg_fret=sum(active) / len(active) if active else 0.0,
        grip=grip,
        bass_midi=bass_midi,
        bass_string=bass_string,
    )


def make_step(
    frets: List[int],
    chord: str = "Cmaj7",
    melody: str = "B4",
    **kwargs: Any,
) -> ArrangementStep:
    """An `ArrangementStep` over a raw fret list, with the derived voicing fields.

    Extra keyword arguments go straight to `ArrangementStep`, which is how a
    renderer test asks for `melody_only=True` or a `bass_only` slot.
    """
    return ArrangementStep(
        chord=chord,
        melody=melody,
        voicing=make_voicing(frets),
        **kwargs,
    )


def bass_string(step: ArrangementStep) -> int:
    """The string carrying the walking thumb, narrowed from `Optional[int]`.

    A plain `int(...)` at the call site satisfies pyright only if it can see the
    value is not None, and it cannot see it through a `self.assertIsNotNone` - a
    checker narrows through a bare `assert`, not through unittest's. Going through
    one function keeps that narrowing in a single place instead of scattering a
    cast across every renderer test.
    """
    value = step.voicing.bass_string
    assert value is not None, "this step carries no bass"
    return value


def note_name(midi: int) -> str:
    """Spells a MIDI number the way the library spells its own transpositions."""
    return f"{PITCH_CLASS_NAMES[midi % 12]}{midi // 12 - 1}"


def pc(name: str) -> int:
    """A pitch class by name, so a test can read as the chord rather than as numbers."""
    return PITCH_CLASS_NAMES.index(name)


def upper_shape(frets: List[int], grip: str = "shell") -> Voicing:
    """A hand-built upper shape, which is what the placement rules are stated against."""
    return make_voicing(frets, grip=grip)


def nearest_reach_for_note(
    held_frets: List[int], held_thumb: Optional[int], midi: int
) -> Optional[int]:
    """How near the hand the walk could have placed *this note*, or None if nowhere.

    The answer to "was this wide reach the placement's doing, or the note's?" - and a
    **replica**, deliberately: it writes out `bass._place_bass`'s filters - the string must
    be free in what the hand is holding, the note must sound below all of it, and the merged
    step must fit the four-fret budget (`fingers.can_fret`) - and then returns the
    proximity the engine ranks on, so a test can ask the question without asking the engine
    that produced the answer. `test_open_issues._cause` is the same kind of helper for the
    refusal filters, and says so in the same words.

    `held_frets` is the shape still ringing and `held_thumb` its bass string, because the
    walking line reuses its own string: that string is fretted but does **not** reserve the
    string for the next note (`bass._place_bass` spells the same rule out), while
    `can_fret` is asked about the whole ringing hand, which is what the engine does.

    The **note**, not the pitch class: this asks where the engine could have put the note it
    decided to play, not whether another octave would have been nearer. Which octave the
    walk wants is its register decision - documented in `bass`, measured in
    `docs/open-issues.md` item 5 - and re-deciding it here would be the replica choosing
    for the engine.

    Returns the smallest `abs(fret - hand_fret)` over those candidates, where `hand_fret` is
    the lowest active fret of `held_frets` - the reference `_place_bass` itself uses. None
    means the note has no position the filters allow, which cannot happen for a note the
    engine placed; a test asserts that it did not.
    """
    from arranger.fingers import can_fret
    from arranger.tuning import STANDARD_TUNING

    active = [fret for fret in held_frets if fret >= 0]
    if not active:
        return None
    hand_fret = float(min(active))
    structure = [
        -1 if index == held_thumb else fret
        for index, fret in enumerate(held_frets)
    ]
    structure_midis = [
        STANDARD_TUNING[index].midi_note() + fret
        for index, fret in enumerate(structure)
        if fret >= 0
    ]
    if not structure_midis:
        return None
    lowest_note = min(structure_midis)
    if midi >= lowest_note:
        return None
    best: Optional[int] = None
    for index, fret in enumerate(structure):
        if fret >= 0:
            continue
        candidate_fret = midi - STANDARD_TUNING[index].midi_note()
        if not 0 <= candidate_fret <= 18:
            continue
        hand = list(held_frets)
        hand[index] = candidate_fret
        if not can_fret(hand):
            continue
        proximity = abs(float(candidate_fret) - hand_fret)
        if best is None or proximity < best:
            best = int(proximity)
    return best
