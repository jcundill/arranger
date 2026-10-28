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

from musthe import Note

from arranger import Request, format_progression
from headxml import arrange_xml_head
from tabxml import format_musicxml
from tests.support import (
    BUT_NOT_FOR_ME,
    COMMON_8,
    TROUBLE_IN_MIND,
    arranged,
    make_step,
    sweep_head_paths,
)


class TestTheEngineRule(unittest.TestCase):
    """`chord_attack` is set where the chord part was asked to strike."""

    def test_a_comp_strikes_every_position_the_rhythm_names(self):
        """`every-beat` is four attacks a bar, and `melody` the tune's own onsets.

        The written onsets are a fact about the *score*, so a comping request keeps them
        without being asked. Bar 2 of this head is where the two rhythms part company,
        because its tune holds through the middle of the bar.
        """
        every, _head, _notes = arrange_xml_head(
            COMMON_8,
            section=(1, 3),
            request=Request(melody=False, chord_on="every-beat"),
        )
        bar_two = [step for step in every if step.bar == 2 and step.voicing.active_frets()]
        self.assertEqual([step.beat for step in bar_two], [1.0, 2.0, 3.0, 4.0])
        self.assertTrue(all(step.chord_attack for step in bar_two))

        tune, _head, _notes = arrange_xml_head(
            COMMON_8, section=(1, 3), request=Request(melody=False)
        )
        bar_two = [step for step in tune if step.bar == 2 and step.voicing.active_frets()]
        self.assertEqual([step.beat for step in bar_two], [1.0, 4.0])
        self.assertTrue(all(step.chord_attack for step in bar_two))

    def test_a_repeated_shape_is_flagged_while_the_pitches_are_equal(self):
        """The one case the pitches cannot decide: same shape, asked for twice.

        A bar of `synthetic_cut_time` under `--chord-on 1,2` with **a one-note comp**
        (`--chord-notes 1`) states one shape on both of its felt beats, so the two
        steps are indistinguishable by pitch - and before the flag existed the second
        was folded into the first and never sounded.

        A one-note comp is the arity that can still repeat a shape: the comp line has
        no top voice to walk there, so the palette has one note per string set and the
        ranking answers with the same one twice. At three voices the line moves by
        construction, which is why this witness is stated at arity one.
        """
        steps, _head, _notes = arrange_xml_head(
            BUT_NOT_FOR_ME,
            section=(2, 4),
            request=Request(melody=False, chord_on="1,2", chord_notes="1"),
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
        """`--chord-on melody,1and` adds an attack at 1and, which the tune is not starting on."""
        steps, _head, _notes = arrange_xml_head(
            COMMON_8, section=(1, 3), request=Request(chord_on="melody,1and")
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
        from tabstaff_grid import _staff_columns

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
        """The user-facing half: bar 2 of the cut-time head, drawn twice.

        The one-note comp of `test_a_repeated_shape_is_flagged_while_the_pitches_are_equal`
        is the fixture, because a three-voice comp no longer repeats a shape - the comp
        line moves its top voice on every position.
        """
        from tabstaff import format_tab_staff

        steps, _head, _notes = arrange_xml_head(
            BUT_NOT_FOR_ME,
            section=(2, 3),
            request=Request(melody=False, chord_on="1,2", chord_notes="1"),
        )
        staff = format_tab_staff(steps, show_chords=False)
        b_row = [line for line in staff.splitlines() if line.startswith("B ")][0]
        self.assertEqual(b_row.count("8"), 2, staff)


class TestATieEndsAtAStab(unittest.TestCase):
    """A chord attack under the tune's tie **releases** the note, and nothing restrikes it.

    The engine holds a left-hand *budget* - four fingers and a five-fret reach, `fingers`
    - and no per-finger assignment, so it cannot prove the finger holding the tune stays
    down while the chord is formed. The recorded answer is therefore the conservative one:
    the tie is ended. A player who can keep the note is free to, because the tab does not
    claim a hold it cannot back; what it must never do is claim the note sounds when the
    arrangement has taken it.

    The chord is kept out of the tune's register by `TestTheCompStaysUnderTheTune`, which is
    the other half: the stab does not restrike the pitch it released.
    """

    def _steps(self, **kwargs):
        steps, _head, _notes = arranged(
            TROUBLE_IN_MIND, section=(1, 8), request=Request(**kwargs)
        )
        return steps

    def _slot(self, steps, bar, beat):
        found = [step for step in steps if step.bar == bar and step.beat == beat]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_the_held_note_is_released_at_the_stab(self):
        """Bar 5 of `Trouble_in_Mind_Blues`: the tied `C4` is taken by the `Cmaj` stab.

        Both the field and the line: `melody_released` is what every renderer reads, and
        the melody column is blank because the note is not sounding. The note's name
        survives only in the clause that says who took it, which is the fact a blank
        column would otherwise hide.
        """
        step = self._slot(
            self._steps(chord_on="1", chord_notes="2"), bar=5, beat=1.0
        )
        self.assertEqual(step.melody, "C4")
        self.assertEqual(step.tab_line(), "x-x-2-0-x-x")
        self.assertTrue(step.melody_released)
        lines = format_progression([step]).splitlines()
        self.assertTrue(lines[0].startswith("Cmaj"), lines[0])
        self.assertNotIn("C4", lines[0].split("x-x-2-0-x-x")[0])
        self.assertIn("the stab ends the tied C4", format_progression([step]))

    def test_a_free_string_does_not_save_the_tie(self):
        """Bar 3: the stab leaves the `A4`'s own string free, and the release is recorded.

        The deliberate over-claim, pinned so a later "optimisation" cannot quietly turn
        it into the conditional rule. The `A4` is on the high E string and `x-x-x-5-7-x`
        does not touch it, so a hand *could* hold it - but "could" is not a fact this
        engine can establish, and the tab does not assert one it cannot.
        """
        step = self._slot(
            self._steps(chord_on="1", chord_notes="2"), bar=3, beat=1.0
        )
        self.assertEqual(step.melody, "A4")
        self.assertEqual(step.tab_line(), "x-x-x-5-7-x")
        self.assertTrue(step.melody_released)
        self.assertIn("the stab ends the tied A4", format_progression([step]))

    def test_a_horn_line_is_never_released(self):
        """With the tune in the horn, a stab ends nothing and the line stays untouched.

        `melody_released` is gated on the *selection* carrying the tune, so the guitar's
        comp behind a singer is exactly the melody-blind part it always was - the
        independence `TestCompingMelodyIndependence` asserts, read at this new field.
        """
        steps = self._steps(melody=False, chord_on="every-beat")
        self.assertFalse([step for step in steps if step.melody_released])
        self.assertTrue(
            [step for step in steps if step.chord_attack and step.voicing.active_frets()],
            "the sweep stopped arranging a comp",
        )

    def test_every_release_is_a_tie_and_never_a_restrike(self):
        """Sweep: a released step follows the note's own sounding onset, and loses its pitch.

        Two facts a single pinned slot cannot hold. The **tie**: walking back from the
        stab, the first step that sang the note is the one that struck it, so a release is
        never recorded where the tune was simply not played. The **restrike**: the note's
        pitch is not in the shape, which is the ceiling's work - a stab that stated the
        pitch it released would be the note re-articulated, which is the sound the user
        reported.
        """
        released = 0
        for head in sweep_head_paths():
            for request in (
                Request(chord_on="1", chord_notes="2"),
                Request(chord_on="every-beat"),
            ):
                steps, _head, _notes = arranged(head, request=request)
                for index, step in enumerate(steps):
                    if not step.melody_released:
                        continue
                    released += 1
                    origin = None
                    for earlier in reversed(steps[:index]):
                        if step.melody not in (earlier.melody, earlier.original_melody):
                            break
                        if earlier.melody_voiced:
                            origin = earlier
                            break
                    self.assertIsNotNone(origin, f"{head} {step.bar} {step.beat}")
                    assert origin is not None
                    self.assertTrue(origin.voicing.midi_notes(), f"{head} {step.bar}")
                    self.assertNotIn(
                        Note(step.melody).midi_note(), step.voicing.midi_notes(),
                        f"{head} {step.chord} {step.melody} {step.tab_line()}",
                    )
        self.assertGreater(released, 5, "the sweep stopped arranging a stab under a tie")


if __name__ == "__main__":
    unittest.main()
