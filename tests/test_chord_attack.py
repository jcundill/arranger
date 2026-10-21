"""A position the chord's rhythm names is a new attack, not a shape still ringing.

The renderers decide "strike or hold" by comparing sounding pitches with the step
before, and on the comping route identical pitches are **ambiguous**: a comp on
`--chord-on every-beat` repeats one shape four times a bar, and so does a shape the tune
merely sustains through. The pitches cannot say which is which, so the engine records the
answer - `ArrangementStep.chord_attack` - and this file holds both halves: the rule that
sets it, and the renderers reading it.

The rule must not disturb the hold the collapse exists for. A slot the eighth-note
skeleton invented, where the tune is **sustaining** a note, is still a hold:
`test_the_melody_route_is_left_to_repeated_and_the_pitches` pins the engine's half of
that, and the unflagged pair in `TestTheRenderersAgree` pins the renderers'.
"""

import re
import unittest

from arranger import Request
from headxml import arrange_xml_head
from tabxml import format_musicxml
from tests.support import BUT_NOT_FOR_ME, COMMON_8, make_step


class TestTheEngineRule(unittest.TestCase):
    """`chord_attack` is set where the chord part was asked to strike."""

    def test_a_comp_strikes_every_position_the_rhythm_names(self):
        """`--no-melody` derives `every-beat`, so a 4/4 comp is four attacks a bar."""
        steps, _head, _notes = arrange_xml_head(
            COMMON_8, section=(1, 3), request=Request(melody=False)
        )
        bar_one = [step for step in steps if step.bar == 1 and step.voicing.active_frets()]
        self.assertEqual([step.beat for step in bar_one], [1.0, 2.0, 3.0, 4.0])
        self.assertTrue(all(step.chord_attack for step in bar_one))

    def test_a_repeated_shape_is_flagged_while_the_pitches_are_equal(self):
        """The one case the pitches cannot decide: same shape, asked for twice.

        A bar of `synthetic_cut_time` under `--chord-on 1,2` states one shape on both of
        its felt beats, so the two steps are indistinguishable by pitch - and before the
        flag existed the second was folded into the first and never sounded.
        """
        steps, _head, _notes = arrange_xml_head(
            BUT_NOT_FOR_ME, section=(2, 4), request=Request(melody=False, chord_on="1,2")
        )
        bar_two = [step for step in steps if step.bar == 2 and step.voicing.active_frets()]
        self.assertEqual([step.beat for step in bar_two], [1.0, 2.0])
        self.assertEqual(
            sorted(bar_two[0].voicing.midi_notes()),
            sorted(bar_two[1].voicing.midi_notes()),
            "the fixture has to repeat the shape for this test to mean anything",
        )
        self.assertTrue(all(step.chord_attack for step in bar_two))

    def test_an_added_stab_under_the_tune_is_flagged(self):
        """`--chord-on melody,1&` adds an attack at 1&, which the tune is not starting on."""
        steps, _head, _notes = arrange_xml_head(
            COMMON_8, section=(1, 3), request=Request(chord_on="melody,1&")
        )
        stabs = [
            step for step in steps if step.beat == 1.5 and step.voicing.active_frets()
        ]
        self.assertTrue(stabs)
        self.assertTrue(all(step.chord_attack for step in stabs))

    def test_the_melody_route_is_left_to_repeated_and_the_pitches(self):
        """The default request names no positions, so the skeleton's holds are untouched.

        A written onset there re-strikes through `repeated` or by carrying a different
        soprano, and a slot the tune merely sustains keeps its hold. Setting the flag
        everywhere would turn the collapse off for chord-melody, which is what the
        pinned tabs in the suite would have caught.
        """
        steps, _head, _notes = arrange_xml_head(COMMON_8, section=(1, 3), request=Request())
        self.assertTrue(steps)
        self.assertFalse(any(step.chord_attack for step in steps))


class TestTheRenderersAgree(unittest.TestCase):
    """One shape, twice: flagged it is two attacks, unflagged it is one."""

    def _pair(self, attack: bool):
        """Two identical comping shapes on consecutive beats, the second flagged or not."""
        first = make_step([-1, 3, 2, 0, 1, -1], bar=1, beat=1.0, melody_voiced=False)
        second = make_step(
            [-1, 3, 2, 0, 1, -1],
            bar=1,
            beat=2.0,
            melody_voiced=False,
            chord_attack=attack,
        )
        return [first, second]

    def test_the_staff_marks_the_second_column_a_strike(self):
        from tabstaff import _staff_columns

        held = _staff_columns(self._pair(False), 4, 4, rhythm=True)
        struck = _staff_columns(self._pair(True), 4, 4, rhythm=True)
        self.assertEqual([c[2] for c in held if c[1] is not None], [True, False])
        self.assertEqual([c[2] for c in struck if c[1] is not None], [True, True])

    def test_the_writers_see_two_events(self):
        """`score_events` is what the MusicXML and GP5 writers both read."""
        from tabscore import score_events

        held, _pickup = score_events(self._pair(False), 4, True)
        struck, _pickup = score_events(self._pair(True), 4, True)
        self.assertEqual(len([e for e in held if e[0] is not None]), 1)
        self.assertEqual(len([e for e in struck if e[0] is not None]), 2)

    def test_the_score_writes_the_comp_as_separate_attacks(self):
        """Two three-voice chords in bar 2, and no tie between them."""
        steps, _head, _notes = arrange_xml_head(
            BUT_NOT_FOR_ME, request=Request(melody=False, chord_on="1,2")
        )
        document = format_musicxml(steps, beats_per_bar=2, beat_type=2)
        measures = re.findall(r"<measure[^>]*>(.*?)</measure>", document, re.S)
        pitched = [
            note
            for note in re.findall(r"<note.*?</note>", measures[1], re.S)
            if "<rest" not in note
        ]
        self.assertEqual(len(pitched), 6, "two three-voice attacks, not one long chord")
        self.assertEqual([note for note in pitched if "<tie" in note], [])

    def test_the_pinned_staff_shows_both_stabs(self):
        """The user-facing half: bar 2 of the cut-time head, drawn twice."""
        from tabstaff import format_tab_staff

        steps, _head, _notes = arrange_xml_head(
            BUT_NOT_FOR_ME, section=(2, 3), request=Request(melody=False, chord_on="1,2")
        )
        staff = format_tab_staff(steps, show_chords=False)
        b_row = [line for line in staff.splitlines() if line.startswith("B ")][0]
        self.assertEqual(b_row.count("8"), 2, staff)


if __name__ == "__main__":
    unittest.main()
