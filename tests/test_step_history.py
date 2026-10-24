"""Reading the arrangement's own history: the last sounding step and its shape.

A route reads the arrangement it is appending to, and a position the guitar
**declined** is still emitted - silent, for the tab's line-up - so "the last step" and
"the last step whose shape the hand was holding" are different questions. These pin
the second, which is the one the selector's voice-leading term and the thumb's
placement ask.
"""

import unittest

from arranger.step_history import last_sounding_step, previous_shape
from arranger.tuning import SILENCE_GRID
from tests.support import make_step

#: An ordinary four-string shape, and the all-muted vector a declined position carries.
SOUNDING = [-1, -1, -1, 5, 5, 5]
MUTED = [-1, -1, -1, -1, -1, -1]


def _sounding_step(melody: str = "C5"):
    """A step the hand was holding."""
    return make_step(SOUNDING, melody=melody)


def _silent_step():
    """A step emitted for the tab's line-up, with nothing plucked."""
    return make_step(MUTED, melody=None, silence=SILENCE_GRID)


class TestTheLastSoundingStep(unittest.TestCase):
    """The look-back skips a declined position rather than reading its mute."""

    def test_no_steps_at_all_is_no_answer(self):
        """Nothing has sounded yet, which is the head of a tune rather than a fault."""
        self.assertIsNone(last_sounding_step([]))

    def test_the_last_step_wins_when_nothing_is_silent(self):
        first = _sounding_step("C5")
        second = _sounding_step("E5")
        self.assertIs(last_sounding_step([first, second]), second)

    def test_a_silent_step_is_not_a_shape_the_hand_held(self):
        """An all-muted vector is fret 0 everywhere: not a position the hand was in."""
        sounding = _sounding_step()
        self.assertIs(last_sounding_step([sounding, _silent_step()]), sounding)

    def test_an_arrangement_of_nothing_but_silence_has_no_answer(self):
        self.assertIsNone(last_sounding_step([_silent_step(), _silent_step()]))


class TestThePreviousShape(unittest.TestCase):
    """The voicing the selector measures the next candidate against."""

    def test_nothing_sounding_means_nothing_to_hold(self):
        self.assertIsNone(previous_shape([]))

    def test_the_last_sounding_steps_own_voicing_comes_back(self):
        step = _sounding_step()
        self.assertIs(previous_shape([step]), step.voicing)

    def test_a_silent_step_does_not_offer_its_muted_vector(self):
        """Scoring against the mute would measure every candidate against fret 0."""
        step = _sounding_step()
        self.assertIs(previous_shape([step, _silent_step()]), step.voicing)

    def test_silence_after_silence_is_still_nothing(self):
        self.assertIsNone(previous_shape([_silent_step()]))


if __name__ == "__main__":
    unittest.main()
