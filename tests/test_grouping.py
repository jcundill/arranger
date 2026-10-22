"""The grouping axis: the metre's third fact, and its derivations.

`beats_per_bar` says how many denominator units a bar has, `beat_type` how long one
lasts, and `grouping` which of them the player feels as a beat. These are the
questions asked of the axis itself; the metric layer, the grid and the walk are
tested where they live.
"""

from __future__ import annotations

import unittest

from arranger import BASS_STYLE_WALK, VoiceLeadingEngine
from arranger.grouping import (
    COMMON_TIME,
    GROUPING_AUTO,
    TimeSignature,
    default_grouping,
    format_grouping,
    group_starts,
    grouping_allowed,
    parse_grouping,
    resolve_grouping,
)
from arranger.options import ArrangeOptions, Request


class TestTheVocabulary(unittest.TestCase):
    """`auto` plus the algebra `N+N+…`; there is no list to enumerate."""

    def test_auto_is_the_sentinel(self):
        self.assertEqual(parse_grouping("auto"), GROUPING_AUTO)
        self.assertEqual(parse_grouping("  AUTO "), GROUPING_AUTO)

    def test_a_grouping_parses_to_its_lengths(self):
        self.assertEqual(parse_grouping("3+3+3+3"), (3, 3, 3, 3))
        self.assertEqual(parse_grouping("3+2"), (3, 2))
        self.assertEqual(parse_grouping(" 2 + 2 + 3 "), (2, 2, 3))

    def test_the_written_spelling_round_trips(self):
        for text in ("3+3+3+3", "3+2", "2+2+3", "1+1+1+1"):
            parsed = parse_grouping(text)
            assert isinstance(parsed, tuple)
            self.assertEqual(format_grouping(parsed), text)

    def test_an_unknown_spelling_is_a_question(self):
        for text in ("", "3+", "+3", "a+3", "3,2", "3++3", "0+3", "-1+4"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_grouping(text)

    def test_zero_is_not_a_group_length(self):
        with self.assertRaises(ValueError):
            parse_grouping("0+4")


class TestAutoDerivesAConvention(unittest.TestCase):
    """Threes for a compound metre; one per beat for everything else."""

    def test_compound_metres_are_groups_of_three(self):
        self.assertEqual(default_grouping(6, 8), (3, 3))
        self.assertEqual(default_grouping(9, 8), (3, 3, 3))
        self.assertEqual(default_grouping(12, 8), (3, 3, 3, 3))
        self.assertEqual(default_grouping(15, 8), (3, 3, 3, 3, 3))
        self.assertEqual(default_grouping(3, 8), (3,))

    def test_simple_metres_keep_one_group_per_beat(self):
        for beats, beat_type in ((4, 4), (2, 2), (3, 4), (5, 4), (7, 4), (4, 8), (2, 8)):
            with self.subTest(metre=f"{beats}/{beat_type}"):
                self.assertEqual(default_grouping(beats, beat_type), (1,) * beats)

    def test_an_asymmetric_metre_is_not_guessed(self):
        """5/8 is usually 3+2 or 2+3, and the file does not say which."""
        self.assertEqual(default_grouping(5, 8), (1, 1, 1, 1, 1))

    def test_resolve_derives_from_the_metre(self):
        self.assertEqual(resolve_grouping(GROUPING_AUTO, 12, 8), (3, 3, 3, 3))
        self.assertEqual(resolve_grouping(GROUPING_AUTO, 4, 4), (1, 1, 1, 1))


class TestValidation(unittest.TestCase):
    """A grouping is a partition of the bar, and nothing else is allowed."""

    def test_a_partition_is_allowed(self):
        self.assertEqual(grouping_allowed((3, 3, 3, 3), 12), (True, ""))
        self.assertEqual(grouping_allowed((3, 2), 5), (True, ""))
        self.assertEqual(grouping_allowed((2, 2, 3), 7), (True, ""))

    def test_a_grouping_that_does_not_fill_the_bar_is_refused(self):
        allowed, reason = grouping_allowed((3, 3), 7)
        self.assertFalse(allowed)
        self.assertIn("spans 6", reason)
        self.assertIn("7", reason)

    def test_a_grouping_past_the_bar_is_refused(self):
        allowed, reason = grouping_allowed((3, 3, 3), 8)
        self.assertFalse(allowed)
        self.assertIn("spans 9", reason)

    def test_resolve_refuses_the_same_shapes(self):
        for grouping, beats in (((3, 3), 7), ((4, 4), 5), ((), 4)):
            with self.subTest(grouping=grouping):
                with self.assertRaises(ValueError):
                    resolve_grouping(grouping, beats, 4)


class TestTheFeltBeats(unittest.TestCase):
    """Where the groups start, and where their offbeat falls."""

    def test_group_starts_are_cumulative(self):
        self.assertEqual(group_starts(12, (3, 3, 3, 3)), (1.0, 4.0, 7.0, 10.0))
        self.assertEqual(group_starts(5, (3, 2)), (1.0, 4.0))
        self.assertEqual(group_starts(7, (2, 2, 3)), (1.0, 3.0, 5.0))

    def test_no_grouping_is_one_group_per_beat(self):
        self.assertEqual(group_starts(4), (1.0, 2.0, 3.0, 4.0))

    def test_a_grouping_that_does_not_partition_the_bar_raises(self):
        with self.assertRaises(ValueError):
            group_starts(7, (3, 3))


class TestTimeSignature(unittest.TestCase):
    """The one value a hand-built arrangement declares, and its validation."""

    def test_common_time_is_four_four_and_resolves_to_four_beats(self):
        self.assertEqual(COMMON_TIME, TimeSignature(4, 4))
        self.assertEqual(COMMON_TIME.grouping, GROUPING_AUTO)
        self.assertEqual(COMMON_TIME.resolved_grouping, (1, 1, 1, 1))
        self.assertEqual(str(COMMON_TIME), "4/4")

    def test_a_compound_metre_derives_its_groups_of_three(self):
        self.assertEqual(TimeSignature(12, 8).resolved_grouping, (3, 3, 3, 3))
        self.assertEqual(TimeSignature(5, 8).resolved_grouping, (1, 1, 1, 1, 1))

    def test_a_written_grouping_is_canonicalised_and_must_fit_the_bar(self):
        signature = TimeSignature(5, 4, " 3 + 2 ")
        self.assertEqual(signature.grouping, "3+2")
        self.assertEqual(signature.resolved_grouping, (3, 2))
        with self.assertRaises(ValueError):
            TimeSignature(4, 4, "3+2")

    def test_the_count_and_the_denominator_are_both_required(self):
        for beats, beat_type in ((0, 4), (4, 0), (-1, 4), (4, -1)):
            with self.subTest(metre=f"{beats}/{beat_type}"):
                with self.assertRaises(ValueError):
                    TimeSignature(beats, beat_type)


class TestTheHandBuiltMetre(unittest.TestCase):
    """A hand-built progression declares one metre, and omitting it is 4/4."""

    PROGRESSION = [("F5", "maj7", "Fmaj7")]

    def test_omitting_the_signature_is_common_time(self):
        """The default is a real declaration, not half of one."""
        self.assertEqual(ArrangeOptions().time_signature, COMMON_TIME)
        steps = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION,
            timings=[(0, 1.0, None)],
            options=ArrangeOptions(
                texture="targets",
                bass=BASS_STYLE_WALK,
            ),
        )
        self.assertEqual([step.beat for step in steps], [1.0, 2.0, 3.0, 4.0])

    def test_a_seven_four_signature_moves_every_part_with_its_groups(self):
        """2+2+3 is three felt beats, so the targets, the walk and `freddie` agree."""
        steps = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION,
            timings=[(0, 1.0, None)],
            options=ArrangeOptions(
                texture="targets",
                bass=BASS_STYLE_WALK,
                request=Request(chord_on="every-beat"),
            ),
            time_signature=TimeSignature(7, 4, "2+2+3"),
        )
        self.assertEqual([step.beat for step in steps], [1.0, 3.0, 5.0])
        self.assertEqual([step.bass is not None for step in steps], [True] * 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
