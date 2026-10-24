"""A thumb note rings until the next attack or the bar line.

A bass line is a line, not a series of stabs: `--bass-on 1` states one note per bar,
and that note has to be heard under the melody notes that follow it. The engine says so
by **carrying** it - `bass_merge.carry_bass` writes the ringing note into the steps that
follow, marked `bass_held`, because the string sounds and is not plucked.

Three renderers read that flag and have to agree about what is a new attack: the
one-line tab draws a mute where the string sounds (it answers "what is plucked"), the
staff leaves the cell empty (the note was drawn where it was struck), and the score
ties the pitch *inside* the chord. The GP5 writer's half is
`tests/test_guitarpro.py::TestARingingThumbIsNotRestruck`. This file is the engine's
rule and the other three.
"""

import unittest
from typing import Any

from arranger import Request
from arranger.annotation import step_annotation
from arranger.options import ArrangeOptions
from headxml import arrange_xml_head
from tabxml import format_musicxml
from tests.support import COMMON_8, make_step


def _struck_bass() -> Any:
    """A struck C3 on the low E string, placed on a beat."""
    struck = make_step([8, -1, -1, -1, -1, -1], bar=1, beat=1.0)
    struck.voicing.bass_midi = 36
    struck.voicing.bass_string = 0
    return struck


class TestTheRingInTheEngine(unittest.TestCase):
    """`bass_held` says the string sounds and is not plucked; `bass` is the note."""

    def _bar(self, request: Request):
        steps, _head, _notes = arrange_xml_head(COMMON_8, section=(1, 2), request=request)
        return steps

    def test_one_bass_note_per_bar_rings_all_bar(self):
        steps = self._bar(Request(bass_on="1"))
        self.assertEqual(len(steps), 4)
        self.assertFalse(steps[0].bass_held, "the attack itself is struck")
        self.assertEqual([step.bass_held for step in steps[1:]], [True] * 3)
        self.assertTrue(all(step.bass is not None for step in steps))

    def test_the_next_attack_takes_over(self):
        """`every-beat` has an attack on every step, so nothing is carried."""
        steps = self._bar(Request(bass_on="every-beat"))
        self.assertEqual([step.bass_held for step in steps], [False] * 4)

    def test_the_ring_stops_at_the_bar_line(self):
        """A held note does not cross a bar line, so the next bar's attack is a strike."""
        steps, _head, _notes = arrange_xml_head(
            COMMON_8, section=(1, 3), request=Request(bass_on="1")
        )
        first_of_bar_two = [step for step in steps if step.bar == 2][0]
        self.assertFalse(first_of_bar_two.bass_held)

    def test_the_line_names_a_held_note_as_held(self):
        steps = self._bar(Request(bass_on="1"))
        self.assertIn("bass: C3, anchor", step_annotation(steps[0]))
        self.assertIn("bass: C3, held", step_annotation(steps[1]))


class TestTheRingEnds(unittest.TestCase):
    """The facts that stop it, each read from the step the note would ring under."""

    def test_a_shape_that_fits_carries_it(self):
        from arranger.bass_merge import carry_bass

        struck = _struck_bass()
        # A shape the hand can hold *with* the ringing note: three fingers, seven to
        # nine, so the low E at fret 8 joins frets it can reach. A shape at frets 1-3
        # would put the thumb seven frets under the hand, which `fingers.can_fret`
        # refuses (see `TestTheRingEnds.test_a_shape_beyond_the_hand_ends_it`).
        following = make_step([-1, 9, 8, 0, 7, -1], bar=1, beat=2.0)
        carry_bass([struck, following])
        self.assertTrue(following.bass_held)
        self.assertEqual(following.voicing.frets[0], 8)
        self.assertEqual(following.bass, 36)

    def test_a_shape_beyond_the_hand_ends_it(self):
        """The reach, not just the finger count: a note the hand cannot get to is not held.

        This is the pair the reach bound closed. Fret 8 on the low E with the hand on
        frets 1-3 is four distinct frets and seven of reach - a shape the budget allows
        and no hand can hold - so the note stops ringing rather than being written.
        """
        from arranger.bass_merge import carry_bass

        struck = _struck_bass()
        following = make_step([-1, 3, 2, 0, 1, -1], bar=1, beat=2.0)
        carry_bass([struck, following])
        self.assertFalse(following.bass_held)
        self.assertIsNone(following.bass)

    def test_a_shape_on_that_string_ends_it(self):
        """The hand cannot sound two notes on one string."""
        from arranger.bass_merge import carry_bass

        struck = _struck_bass()
        following = make_step([5, 3, 2, 0, 1, -1], bar=1, beat=2.0)
        carry_bass([struck, following])
        self.assertFalse(following.bass_held)
        self.assertIsNone(following.bass)

    def test_a_shape_above_the_note_ends_it(self):
        """The thumb is the lowest voice by construction; a chord below it is not the bass."""
        from arranger.bass_merge import carry_bass

        struck = make_step([12, -1, -1, -1, -1, -1], bar=1, beat=1.0)
        struck.voicing.bass_midi = 60
        struck.voicing.bass_string = 0
        following = make_step([-1, 1, 0, -1, -1, -1], bar=1, beat=2.0)
        carry_bass([struck, following])
        self.assertFalse(following.bass_held)

    def test_a_rest_ends_it(self):
        from arranger.bass_merge import carry_bass

        silence = make_step([-1] * 6, bar=1, beat=2.0)
        after = make_step([-1, 3, 2, 0, 1, -1], bar=1, beat=3.0)
        carry_bass([_struck_bass(), silence, after])
        self.assertFalse(after.bass_held, "the ring was carried across a rest")

    def test_the_bar_line_ends_it(self):
        from arranger.bass_merge import carry_bass

        following = make_step([-1, 3, 2, 0, 1, -1], bar=2, beat=1.0)
        carry_bass([_struck_bass(), following])
        self.assertFalse(following.bass_held)

    def test_the_ring_follows_the_metre(self):
        """A hand-built progression is laid out on the felt beats, so the thumb's note rings.

        Two chords in 4/4 are beats 1 and 2 of one bar, and the thumb strikes the root
        once: the second step carries that note rather than restriking it. The bar line
        that ends the ring is therefore a real distance away.
        """
        from arranger import VoiceLeadingEngine

        steps = VoiceLeadingEngine.arrange_progression(
            [("E4", "Cmaj7"), ("G4", "Cmaj7")],
            options=ArrangeOptions(request=Request(bass_on="1", bass_notes="root")),
        )
        self.assertEqual([step.bass_held for step in steps], [False, True])

    def test_an_unplaced_step_carries_nothing(self):
        """A position the caller states as unplaced has no bar line to stop at."""
        from arranger import VoiceLeadingEngine

        steps = VoiceLeadingEngine.arrange_progression(
            [("E4", "Cmaj7"), ("G4", "Cmaj7")],
            timings=[(None, None, None)] * 2,
            options=ArrangeOptions(request=Request(bass_on="1", bass_notes="root")),
        )
        self.assertEqual([step.bass_held for step in steps], [False, False])


class TestTheRenderersAgree(unittest.TestCase):
    """One note, drawn three ways: struck once, ringing under the melody."""

    def _steps(self):
        steps, _head, _notes = arrange_xml_head(
            COMMON_8, section=(1, 2), request=Request(bass_on="1")
        )
        return steps

    def test_the_one_line_tab_mutes_the_ringing_string(self):
        """The tab answers "what is plucked", so a sounding string reads as a mute."""
        from arranger.render import _step_cells

        steps = self._steps()
        self.assertEqual(_step_cells(steps[0])[0], "8", "the attack is drawn")
        self.assertEqual(_step_cells(steps[1])[0], "x", "the ring is not")
        self.assertEqual(steps[1].voicing.frets[0], 8, "the string is still sounding")

    def test_the_staff_leaves_the_held_cell_empty(self):
        from tabstaff import format_tab_staff

        staff = format_tab_staff(self._steps(), show_chords=False)
        # The low E row carries the thumb; `8` appears on the B string too, so the
        # assertion is on that one row rather than on the whole staff.
        low_e = [line for line in staff.splitlines() if line.startswith("E ")]
        self.assertEqual([line.count("8") for line in low_e], [1], staff)

    def test_the_score_ties_the_pitch_inside_the_chord(self):
        """MusicXML says a note lasts across an attack with a tie, per note."""
        document = format_musicxml(self._steps(), beats_per_bar=4, beat_type=4)
        self.assertGreaterEqual(document.count('<tie type="start"'), 1, document)
        self.assertGreaterEqual(document.count('<tie type="stop"'), 1, document)


if __name__ == "__main__":
    unittest.main()
