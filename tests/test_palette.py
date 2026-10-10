"""The palette a step records, and the shape clause the renderer writes from it.

A chord name above a step describes the harmony rather than every note sounding under it,
so a thin shape needs its *reason*: how many voices the palette offered, and - where a
fuller shape existed - which criterion of `cost.voicing_cost` turned it away. These tests
hold the recorded fact to the sentence, and both to the general claims, because the
sentence is the whole point of recording anything.
"""

import glob
import unittest

from arranger import VoiceLeadingEngine
from arranger.cost import PARTITION_CRITERION, SPAN_CRITERION, VOICING_COST_CRITERIA
from arranger.render import _criterion_phrase, _step_annotation
from tests.support import make_voicing

#: The voice-count criterion of the cost tuple, which a *fuller* shape can never lose on:
#: its own voice count is a smaller `missing` term, so the two tuples cannot be equal.
#: Read from the same table the renderer reads rather than hardcoded, because the index is
#: the tuple's order and that table is where the order is spelled.
VOICES_CRITERION = VOICING_COST_CRITERIA.index("leaves a voice out")

#: Six steps that put every shape of palette fact on one screen. In order: a melody the
#: tables cannot voice four-deep (B4 over F#m7 - the only complete shape needs a 5-fret
#: stretch, so the demotion rule plays the tune alone), a complete shape, a hold, a melody
#: with no complete *or* three-voice shape at all (Bb3 is foreign to B7 and no strategy
#: substitutes the chord), a shell that beat the complete shape out of the neck window,
#: and another complete shape.
STRUGGLING = (
    ("B4", "m7", "F#m7"), ("A4", "m7", "F#m7"), ("A4", "m7", "F#m7"),
    ("Bb3", "7", "B7"), ("B3", "7", "B7"), ("A4", "7", "B7"),
)

#: Three ordinary steps, where the palette has four voices and the shape states them.
COMPLETE = (("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7"))


class TestTheRecordedPalette(unittest.TestCase):
    """The fact on the step, before any wording."""

    def test_a_complete_shape_records_the_palette_that_offered_it(self):
        """Four voices, nothing fuller, and so no criterion to report."""
        steps = VoiceLeadingEngine.arrange_progression(COMPLETE)
        self.assertEqual(len(steps), 3)
        for step in steps:
            self.assertEqual(len(step.voicing.upper_midi_notes()), 4, step.tab_line())
            palette = step.palette
            assert palette is not None, step.tab_line()
            self.assertEqual(palette.available, 4, step.tab_line())
            self.assertIsNone(palette.alternative, step.tab_line())
            self.assertIsNone(palette.decided_by, step.tab_line())

    def test_a_thin_palette_records_no_alternative(self):
        """A foreign melody note with no substitution: two voices, and that is all."""
        step = VoiceLeadingEngine.arrange_progression(STRUGGLING)[3]
        self.assertTrue(step.non_chord_tone)
        self.assertIsNone(step.harmonized_as)
        palette = step.palette
        assert palette is not None
        self.assertEqual(palette.available, 2)
        self.assertIsNone(palette.alternative)
        self.assertIsNone(palette.decided_by)

    def test_the_shell_records_the_complete_voicing_it_lost_to(self):
        """The alternative is the chord that is *not* being played, not the runner-up."""
        step = VoiceLeadingEngine.arrange_progression(STRUGGLING)[4]
        self.assertEqual(len(step.voicing.upper_midi_notes()), 3)
        palette = step.palette
        assert palette is not None
        self.assertEqual(palette.available, 4)
        alternative = palette.alternative
        assert alternative is not None
        self.assertEqual(len(alternative.active_frets()), 4)
        self.assertEqual(alternative.tab_string(), "2-x-1-2-0-x")
        self.assertEqual(
            palette.decided_by,
            VOICING_COST_CRITERIA.index("lies outside the neck window"),
        )

    def test_the_demoted_melody_records_the_shape_it_turned_away(self):
        """The span budget turned a complete shape away, and the step says which one."""
        step = VoiceLeadingEngine.arrange_progression(STRUGGLING)[0]
        self.assertEqual(len(step.voicing.upper_midi_notes()), 1)
        palette = step.palette
        assert palette is not None
        self.assertEqual(palette.available, 4)
        alternative = palette.alternative
        assert alternative is not None
        self.assertEqual(alternative.tab_string(), "x-7-7-11-12-x")
        self.assertEqual(palette.decided_by, SPAN_CRITERION)

    def test_a_comping_shape_records_no_palette(self):
        """`--voices none` is guide tones by construction, so nothing is claimed.

        `palette` states "fewer voices than the palette could offer", and a comping shape
        makes no such claim: its arity follows the voices the caller named, and the line
        says which degrees sound instead (`render._comping_clause`).
        """
        steps = VoiceLeadingEngine.arrange_progression(COMPLETE, melody="none")
        self.assertEqual(len(steps), 3)
        for step in steps:
            self.assertFalse(step.melody_voiced)
            self.assertIsNone(step.palette, step.tab_line())

    def test_a_fill_records_the_only_palette_it_has(self):
        """The tune alone *is* the palette there, so the one voice is its limit.

        `--voices soprano` and a texture thinning a slot to a fill both take the same
        route, and in both the palette that route consults holds the melody alone - which
        is why the count is recorded rather than left to read like a decision between
        shapes.
        """
        steps = VoiceLeadingEngine.arrange_progression(COMPLETE, melody="soprano")
        self.assertEqual(len(steps), 3)
        for step in steps:
            palette = step.palette
            assert palette is not None, step.tab_line()
            self.assertEqual(palette.available, 1, step.tab_line())
            self.assertEqual(len(step.voicing.upper_midi_notes()), 1, step.tab_line())

    def test_a_fuller_shape_never_loses_on_voice_count(self):
        """The general claim, over the committed heads rather than one worked case.

        A shape with more voices than the chosen one cannot be ranked lower *for* its
        voice count, so the recorded criterion is always correctness, the neck window or
        the hand's travel - which is what makes the sentence worth printing. Asserted on
        the whole because the alternative is picked out of a palette per step, and a rule
        stated over one hand-built example says nothing about the steps the engine builds
        for itself.
        """
        from headxml import arrange_xml_head

        paths = sorted(
            glob.glob("tests/data/*.mxl") + glob.glob("tests/data/*.musicxml")
        )
        self.assertGreaterEqual(len(paths), 6, "the committed heads went missing")
        checked = 0
        for path in paths:
            for texture in ("uniform", "targets"):
                steps, _head, _notes = arrange_xml_head(path, texture=texture)
                for step in steps:
                    palette = step.palette
                    if palette is None or palette.alternative is None:
                        continue
                    checked += 1
                    fuller = len(palette.alternative.active_frets())
                    voices = len(step.voicing.upper_midi_notes())
                    self.assertGreater(
                        fuller, voices,
                        f"{path}: the alternative is not fuller than the shape",
                    )
                    self.assertGreaterEqual(
                        palette.available, fuller,
                        f"{path}: the alternative is fuller than the palette",
                    )
                    self.assertIsNotNone(
                        palette.decided_by,
                        f"{path}: a fuller shape lost on an exact tie?",
                    )
                    self.assertNotEqual(
                        palette.decided_by, VOICES_CRITERION,
                        f"{path}: the voice count is reported as the reason",
                    )
                    if palette.decided_by == PARTITION_CRITERION:
                        # The only thing that can remove a shape before the tuple ran is
                        # the written bass, which only a slash chord asks for.
                        self.assertIn(
                            "/", step.chord,
                            f"{path}: a bass partition with no written bass?",
                        )
        self.assertGreater(checked, 20, "no step recorded an alternative at all")


class TestTheShapeClause(unittest.TestCase):
    """The sentence itself - the deliverable, so it is pinned whole."""

    def test_the_annotations_of_the_six_worked_steps(self):
        """Every kind of shape clause on one screen, in the order they arise."""
        steps = VoiceLeadingEngine.arrange_progression(STRUGGLING)
        self.assertEqual([_step_annotation(step) for step in steps], [
            " (harmony under 11 - melody alone: the 4-voice voicing"
            " x-7-7-11-12-x needs a 5-fret stretch)",
            " (harmony under b3 - 4 voices)",
            " (melody repeated - single note)",
            " (non-chord tone - the extension strategy found no voicing;"
            " the written chord stands - 2 voices, the most this palette offers)",
            " (shell - 3rd & 7th, partial - 3 voices: the 4-voice voicing"
            " 2-x-1-2-0-x lies outside the neck window)",
            " (harmony under b7 - 4 voices)",
        ])

    def test_the_written_bass_is_named_when_it_removed_the_shape(self):
        """A slash chord can lose on its bass before the cost tuple is ever consulted.

        `Gmaj9/F#` is the live case: `3-x-4-4-3-x` states four voices, but its lowest note
        is the G, so `decisions.select_step_voicing` drops it in the partition and the
        shell wins. No element of the two cost tuples need differ for that, which is why
        this phrase comes from outside the tuple - see `cost.PARTITION_CRITERION`.
        """
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head(
            "tests/data/heres_that_rainy_day.musicxml", section=(1, 2)
        )
        slash = [step for step in steps if step.chord == "Gmaj9/F#"]
        self.assertTrue(slash, "the committed head lost its slash chord")
        self.assertEqual(
            _step_annotation(slash[-1]),
            " (shell - 3rd & 7th, partial - 3 voices: the 4-voice voicing"
            " 3-x-4-4-3-x does not sound the written bass)",
        )
        palette = slash[-1].palette
        assert palette is not None
        self.assertEqual(palette.decided_by, PARTITION_CRITERION)

    def test_a_complete_shape_states_its_count_and_nothing_else(self):
        """Four is every string the right hand has, so there is nothing to explain."""
        steps = VoiceLeadingEngine.arrange_progression(COMPLETE)
        for step in steps:
            annotation = _step_annotation(step)
            self.assertTrue(annotation.endswith(" - 4 voices)"), annotation)

    def test_a_hold_carries_no_shape_clause(self):
        """A hold is annotated by what is *struck*, not by the shape still ringing."""
        step = VoiceLeadingEngine.arrange_progression(STRUGGLING)[2]
        self.assertTrue(step.repeated)
        self.assertIsNotNone(step.palette, "the hold's own palette is still recorded")
        self.assertEqual(_step_annotation(step), " (melody repeated - single note)")

    def test_a_requested_one_voice_selection_says_it_is_the_palette_limit(self):
        """`--voices soprano` states the tune alone, and the line says the palette is why.

        The slot's palette is the melody grip, so `available=1` is the truth rather than a
        fallback dressed up - which is the difference between "the library had nothing
        else" and "this selection asked for one voice".
        """
        steps = VoiceLeadingEngine.arrange_progression(COMPLETE, melody="soprano")
        self.assertEqual(
            [_step_annotation(step) for step in steps],
            [
                " (harmony under Root - melody alone, the most this palette offers)",
                " (harmony under 3 - melody alone, the most this palette offers)",
                " (harmony under Root - melody alone, the most this palette offers)",
            ],
        )

    def test_every_criterion_has_a_phrase(self):
        """`_criterion_phrase` reads the tuple's own vocabulary, index for index."""
        voicing = make_voicing([-1, -1, -1, 10, 12, 10])
        for index, phrase in enumerate(VOICING_COST_CRITERIA):
            if index == SPAN_CRITERION:
                continue
            self.assertEqual(_criterion_phrase(index, voicing), phrase)
        # The span is the one phrased with its own magnitude, because the stretch can be
        # read off the tab and what a reader wants is how wide it is.
        self.assertEqual(
            _criterion_phrase(SPAN_CRITERION, voicing), "needs a 2-fret stretch"
        )


class TestTheOtherRoutesExplainThemselves(unittest.TestCase):
    """The routes whose shape is *not* a palette choice, each answering for itself.

    Every one of these was a line that left the reader to guess: a silent step annotated
    with a degree, a single bass note called a "shell - 3rd & 7th", a held shape reading
    as a strike, a palette limit with no mention of the texture that asked for it, a
    shape outside the neck window with nothing said about what was inside it, and a chord
    symbol the library cannot read printing a bare count.
    """

    def test_a_silent_step_says_it_is_silent(self):
        """A grid that places no chord leaves the guitar out, and the line says so.

        Measured before this clause existed: 74 of one head's 206 `--grid freddie` steps
        are silent, and every one of them carried `(harmony under <degree>)` - the one
        annotation that was not merely thin but false.
        """
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head(
            "tests/data/heres_that_rainy_day.musicxml",
            section=(1, 2), grid="freddie", melody="none",
        )
        silent = [step for step in steps if not step.voicing.active_frets()]
        self.assertTrue(silent, "the grid stopped leaving the guitar out")
        for step in silent:
            self.assertEqual(
                _step_annotation(step),
                " (the guitar rests here - the grid places no chord)",
            )

    def test_a_comping_step_names_the_degrees_it_states(self):
        """The arity and the family are read off the shape, not off the grip label.

        The label it replaces said `shell - 3rd & 7th` for all three of these: wrong for a
        single bass note, and wrong in spelling as well - a dominant's seventh is a `b7`.
        """
        from headxml import arrange_xml_head

        head = "tests/data/heres_that_rainy_day.musicxml"
        expected = {
            "bass": " (comping - 5; the guitar does not play the tune)",
            "alto,tenor": " (comping - 3 & 7; the guitar does not play the tune)",
            "alto,tenor,bass": " (comping - 3, 5 & 7; the guitar does not play the tune)",
        }
        for voices, text in expected.items():
            steps, _head, _notes = arrange_xml_head(
                head, section=(1, 2), melody=voices, bass="none"
            )
            self.assertEqual(_step_annotation(steps[0]), text, voices)
            self.assertFalse(steps[0].melody_voiced)

    def test_a_held_step_says_the_shape_above_it_is_held(self):
        """`bass_only` is a claim about the left hand, and the tab cannot show it."""
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head(
            "tests/data/heres_that_rainy_day.musicxml", section=(1, 3),
            texture="walking_bass",
        )
        held = [step for step in steps if step.bass_only and step.palette]
        self.assertTrue(held, "no held step under the thumb in this section")
        for step in held:
            self.assertIn("the shape above is held", _step_annotation(step))

    def test_a_fill_says_whose_palette_is_the_thin_one(self):
        """A fill is thin because the texture asked, which is a different answer."""
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head(
            "tests/data/All_the_Things_You_Are.musicxml", section=(1, 8),
            texture="targets",
        )
        fills = [
            step for step in steps
            if step.role == "fill" and not step.repeated
            and step.palette is not None
            and step.palette.alternative is None
            and len(step.voicing.upper_midi_notes()) < 4
        ]
        self.assertTrue(fills, "no thin fill in this section")
        for step in fills:
            self.assertIn("the most a fill's palette offers", _step_annotation(step))

    def test_an_out_of_position_shape_says_what_was_inside_the_window(self):
        """The window is a preference, so a shape outside it has to explain itself.

        Both readings are provable from the tuple's order - window penalties (element 1)
        are consulted after correctness (0) and before voice count (2) - so an in-window
        shape that lost to an out-of-position one must have sounded a wrong note, and when
        no shape sits inside the window at all, the palette is why.
        """
        from headxml import arrange_xml_head

        head = "tests/data/All_the_Things_You_Are.musicxml"
        steps, _head, _notes = arrange_xml_head(head, texture="targets")
        stranded = [
            step for step in steps
            if step.palette is not None and not step.palette.inside_window
            and not step.repeated
        ]
        self.assertTrue(stranded, "no out-of-position shape in this head")
        self.assertIn(
            "nothing in this palette sits inside the window",
            _step_annotation(stranded[0]),
        )
        beaten = [
            step for step in steps
            if step.palette is not None and step.palette.inside_window
            and "reaches outside" in _step_annotation(step)
        ]
        self.assertTrue(beaten, "no in-window shape was beaten by an out-of-position one")
        self.assertIn(
            "the shapes inside the window sound a note outside the chord",
            _step_annotation(beaten[0]),
        )

    def test_an_unreadable_chord_says_so(self):
        """`_melody_degree_label` blanks for two reasons, and only one is worth printing.

        A slot the tune is silent at has no degree to name and needs no clause; a melody
        over a chord no table can read is a fact the reader cannot get anywhere else - the
        chord column shows the spelling, not the problem.
        """
        voiced = VoiceLeadingEngine.arrange_progression([("C5", "m7", "Dm(maj7)")])
        self.assertEqual(
            _step_annotation(voiced[0]),
            " (the chord symbol could not be read - 4 voices)",
        )
        unvoiced = VoiceLeadingEngine.arrange_progression([("C5", "zz", "Czz")])
        self.assertEqual(
            _step_annotation(unvoiced[0]),
            " (melody alone - the chord symbol could not be read)",
        )


    def test_a_written_bass_that_is_not_sounded_says_so(self):
        """A slash chord nobody can voice still prints, and the loss is reported.

        `Trouble_in_Mind_Blues` has `Am7/D` steps whose shapes state the b3, the 5 and the
        b7 and no D at all: the partition prefers the written bass and cannot reach it, so
        the reader is handed a symbol asking for a note the tab does not contain. Measured
        over the committed corpus: 53 of 127 slash-chord steps, in both the melody-bearing
        and the comping routes.
        """
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head("tests/data/Trouble_in_Mind_Blues.musicxml")
        lost = [
            step for step in steps
            if "/" in step.chord and "the written bass" in _step_annotation(step)
        ]
        self.assertTrue(lost, "the head stopped losing its slash basses")
        self.assertIn(
            "the written bass D is not sounded - the lowest voice (G3) is 5 semitones",
            _step_annotation(lost[0]),
        )
        kept = [
            step for step in steps
            if step.chord == "Gmaj/D" and "written bass" not in _step_annotation(step)
        ]
        self.assertTrue(kept, "a shape that sounds its written bass was flagged anyway")


    def test_a_strategy_that_found_nothing_says_which_one_it_was(self):
        """`non-chord tone` alone cannot tell a failed substitution from an untried one.

        Measured over the corpus: 2,713 steps keep the written chord under a melody that is
        not in it, and every one of them used to read just `(non-chord tone - 4 voices)` -
        the words a route that never attempted a substitution would also print.
        """
        steps = VoiceLeadingEngine.arrange_progression(STRUGGLING)
        third = _step_annotation(steps[3])
        self.assertIn("the extension strategy found no voicing", third)
        self.assertIn("the written chord stands", third)
        self.assertIsNone(steps[3].harmonized_as)
        self.assertEqual(steps[3].strategy, "extension")

    def test_a_comping_step_says_whether_the_tune_is_there_to_decline(self):
        """`melody_voiced` False cannot tell "not mine" from "not sounding".

        Measured over the corpus: 2,107 steps are positions the *tune* is silent at - a grid
        stab with no note under it - and each said the guitar was not playing a tune that was
        not playing either.
        """
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head(
            "tests/data/All_the_Things_You_Are.musicxml", section=(7, 9), grid="freddie",
            melody="none",
        )
        silent_slots = [step for step in steps if step.melody is None]
        self.assertTrue(silent_slots, "the grid stopped stabbing where the tune is silent")
        for step in silent_slots:
            self.assertIn("the tune is silent here", _step_annotation(step))
        sounding = [step for step in steps if step.melody is not None]
        self.assertTrue(sounding, "no position in these bars has a note under it")
        for step in sounding:
            self.assertIn("the guitar does not play the tune", _step_annotation(step))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
