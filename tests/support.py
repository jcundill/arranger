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
* `capture_diagnostics`, which needs the `Diagnostics` collector the engine does
  not have yet. It arrives with that work, not before.

Every fixture here builds a value by hand rather than by running the engine, which
is the point: a test that arranges a progression and then asserts on the result is
testing the engine against itself.
"""

from __future__ import annotations

from typing import Any, List, Optional

from arranger import PITCH_CLASS_NAMES, ArrangementStep, Voicing


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
