"""The `sustain` chord-on token: chord only at sustained melody onsets.

A note running at least one felt beat is harmonised at its onset; a shorter note
stays a single melody note. Positions the figure names (a `1and` stab) are still
honoured. With `--no-melody` the guitar comps but does not sing: the written onsets
and their durations still drive `sustain`, so sustained onsets comp while short ones
rest, just as `chord-on=melody --no-melody` comps to the written onsets.
"""

from __future__ import annotations

import unittest

from arranger import ArrangeOptions, Note, VoiceLeadingEngine
from arranger.grid import parse_rhythm
from arranger.options import Request

_PROGRESSION = (
    ("C5", "Cmaj7"),
    ("D4", "Cmaj7"),
    ("E4", "Cmaj7"),
    ("F4", "Cmaj7"),
)

#: One whole note per slot (4 beats in 4/4): every onset is sustained.
_WHOLE = (
    (1, 1.0, 1.0),
    (1, 2.0, 1.0),
    (1, 3.0, 1.0),
    (1, 4.0, 1.0),
)

#: A long first note, then short eighth-notes: only the first onset is sustained.
_MIXED = (
    (1, 1.0, 1.0),
    (1, 2.0, 0.125),
    (1, 3.0, 0.125),
    (1, 4.0, 0.125),
)


def _arrange(progression=_PROGRESSION, timings=_WHOLE, **kwargs):
    """The library's own front door, with the request passed as one value."""
    return VoiceLeadingEngine.arrange_progression(
        progression, timings=timings, options=ArrangeOptions(**kwargs)
    )


def _sounded(step) -> int:
    """How many strings a step plucks; the tune alone is one."""
    return sum(1 for fret in step.voicing.frets if fret >= 0)


class TestSustainChordsOnlyLongOnsets(unittest.TestCase):
    """`chord-on=sustain` states the chord only where the tune outlasts a beat."""

    def test_every_whole_note_is_harmonised(self):
        """Every note outlasts a beat, so every onset gets a chord (more than one string)."""
        steps = _arrange(request=Request(chord_on="sustain"))
        self.assertEqual(len(steps), 4)
        for step in steps:
            with self.subTest(beat=step.beat):
                self.assertGreater(_sounded(step), 1)

    def test_a_short_note_stays_a_single_note(self):
        """Only the long first note is harmonised; the short eighth-notes sound alone."""
        steps = _arrange(timings=_MIXED, request=Request(chord_on="sustain"))
        self.assertEqual(len(steps), 4)
        self.assertGreater(_sounded(steps[0]), 1)
        for index in (1, 2, 3):
            with self.subTest(index=index):
                self.assertEqual(_sounded(steps[index]), 1)

    def test_melody_is_still_the_top_voice_when_alone(self):
        """A short note sounds alone but the written pitch is still on the soprano."""
        steps = _arrange(timings=_MIXED, request=Request(chord_on="sustain"))
        for index, step in enumerate(steps):
            with self.subTest(index=index):
                self.assertEqual(
                    max(step.voicing.midi_notes()),
                    Note(_PROGRESSION[index][0]).midi_note(),
                )


class TestSustainPositionStab(unittest.TestCase):
    """A position the figure names (such as `1and`) is still attacked."""

    def test_sustain_prints_and_parses_back(self):
        self.assertEqual(str(parse_rhythm("sustain", 4)), "sustain")
        self.assertEqual(str(parse_rhythm("sustain,1and", 4)), "sustain,1and")
        self.assertEqual(str(parse_rhythm("melody,sustain", 4)), "melody")

    def test_sustain_stab_attacks_its_position_without_the_tune(self):
        """`sustain,1and --no-melody` stabs on 1and even though the note there is short.

        A slot at the stab position (beat 1.5) comps because the figure names that
        position, regardless of the note's duration.
        """
        timings = (
            (1, 1.0, 0.125),   # short: not sustained, no stab here -> rest
            (1, 1.5, 0.125),   # short, but on the stab position -> comps
            (1, 2.0, 1.0),     # sustained -> comps
            (1, 3.0, 0.125),   # short: rest
        )
        steps = _arrange(
            timings=timings,
            request=Request(melody=False, chord_on="sustain,1and"),
        )
        self.assertEqual(len(steps), 4)
        self.assertEqual(_sounded(steps[0]), 0)   # short, no stab
        self.assertGreater(_sounded(steps[1]), 1) # stab position comps
        self.assertGreater(_sounded(steps[2]), 1) # sustained comps
        self.assertEqual(_sounded(steps[3]), 0)   # short, no stab


class TestSustainDurationTest(unittest.TestCase):
    """The duration test that decides whether a sustained onset is struck."""

    def test_sustained_onset_comps_without_the_tune(self):
        """`sustain --no-melody` comps at sustained onsets from written durations."""
        steps = _arrange(
            timings=_MIXED,
            request=Request(melody=False, chord_on="sustain"),
        )
        self.assertEqual(len(steps), 4)
        # The first note is a whole note (1.0 * 4 = 4 beats): it comps.
        self.assertGreater(_sounded(steps[0]), 1)
        # The short eighth-notes (0.125 * 4 = 0.5 beat) rest: nothing above the thumb.
        for index in (1, 2, 3):
            with self.subTest(index=index):
                self.assertEqual(_sounded(steps[index]), 0)


class TestSustainRefusals(unittest.TestCase):
    """`sustain` refuses nothing it can measure."""

    def test_sustain_is_accepted_without_the_tune(self):
        """`chord-on=sustain --no-melody` is not refused: written durations still
        exist, so sustained onsets comp just like `chord-on=melody --no-melody`
        comps to the written onsets."""

        # No exception: the request is honoured, not refused.
        _arrange(
            timings=_WHOLE,
            request=Request(melody=False, chord_on="sustain"),
        )
        _arrange(
            timings=_WHOLE,
            request=Request(melody=False, chord_on="sustain,1and"),
        )
