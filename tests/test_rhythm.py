"""The rhythm grammar: direct positions in felt beats.

`Rhythm` is the request the arrangement is asked with. Its positions are **felt
beats**, not denominator units, so `1&` is the midpoint of the bar's first felt
beat in 2/2, 4/4 and 6/8 alike - a quarter-note offbeat in the first, an eighth-note
offbeat in the second, and the midpoint of a dotted-quarter pulse in the third.

What is verified, in order:

- **the simple metres**: `every-beat` follows the denominator count (2, 3 and 4),
  and `1&` / `3&` land halfway through their felt beat;
- **the compound metre**: `every-beat` follows the grouping, so 6/8 has two felt
  beats and its second one is the bar's fourth eighth - and `&` is the midpoint of
  the dotted-quarter pulse rather than a fixed half-beat;
- **the list**: a list replaces the default, `melody` may stand beside positions,
  order and duplicates are not part of the request, and `none` is the one token
  that cannot be combined;
- **the refusals**: a position the metre does not have, an unknown token, a decimal
  and an empty entry all raise, because each is a question rather than silence;
- **the canonical spelling**: one position has one token, the run header's spelling
  parses back to the same value, and the round trip is asserted over every metre.

No arrangement is built here. This is the grammar's own test; the step loop reads
it in the stages that follow.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from arranger import Rhythm, TimeSignature, felt_beat, parse_rhythm

SIMPLE_METRES = ((2, 2), (3, 4), (4, 4))
COMPOUND_METRE = TimeSignature(6, 8)


def _six_eight() -> tuple:
    """The 6/8 grouping the metre derives: two dotted-quarter pulses."""
    return COMPOUND_METRE.resolved_grouping


class TestTheSimpleMetres(unittest.TestCase):
    """One felt beat is one denominator unit, so the grammar reads as it looks."""

    def test_every_beat_follows_the_count(self):
        """2/2, 3/4 and 4/4 have 2, 3 and 4 attacks a bar respectively."""
        for beats, beat_type in SIMPLE_METRES:
            with self.subTest(metre=f"{beats}/{beat_type}"):
                rhythm = parse_rhythm("every-beat", beats)
                self.assertEqual(
                    rhythm.positions, tuple(float(n) for n in range(1, beats + 1))
                )
                for beat in range(1, beats + 1):
                    self.assertTrue(rhythm.includes(float(beat), beats, None))

    def test_the_and_is_halfway_through_its_felt_beat(self):
        """`1&` is 1.5 and `3&` is 3.5 where those beats exist."""
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertTrue(parse_rhythm("1&", beats).includes(1.5, beats))
                self.assertFalse(parse_rhythm("1&", beats).includes(1.0, beats))
        self.assertTrue(parse_rhythm("3&", 3).includes(3.5, 3))
        self.assertTrue(parse_rhythm("last&", 2).includes(2.5, 2))

    def test_the_quarter_and_three_quarter_points_are_named(self):
        """`e` and `a` are 0.25 and 0.75 into the felt beat."""
        rhythm = parse_rhythm("1e,1a", 4)
        self.assertTrue(rhythm.includes(1.25, 4))
        self.assertTrue(rhythm.includes(1.75, 4))
        self.assertFalse(rhythm.includes(1.5, 4))

    def test_a_bar_relative_position_is_not_an_absolute_one(self):
        """The same token is the same place in every bar, not the same time."""
        rhythm = parse_rhythm("1&", 4)
        self.assertTrue(rhythm.includes(1.5, 4))
        self.assertFalse(rhythm.includes(2.5, 4))
        self.assertFalse(rhythm.includes(4.5, 4))



class TestTheCompoundMetre(unittest.TestCase):
    """6/8 is felt in two, and `every-beat` must follow the grouping."""

    def test_every_beat_is_one_attack_per_felt_beat(self):
        """Two dotted-quarter pulses, not six eighth-note units."""
        grouping = _six_eight()
        self.assertEqual(grouping, (3, 3))
        rhythm = parse_rhythm("every-beat", 6, grouping)
        self.assertEqual(rhythm.positions, (1.0, 2.0))
        self.assertTrue(rhythm.includes(1.0, 6, grouping))
        self.assertTrue(rhythm.includes(4.0, 6, grouping))
        self.assertFalse(rhythm.includes(2.0, 6, grouping))

    def test_the_and_is_the_midpoint_of_the_dotted_quarter(self):
        """`1&` is 2.5 beats into the bar, not 1.5 and not the third eighth."""
        grouping = _six_eight()
        self.assertTrue(parse_rhythm("1&", 6, grouping).includes(2.5, 6, grouping))
        self.assertFalse(parse_rhythm("1&", 6, grouping).includes(1.5, 6, grouping))
        self.assertTrue(parse_rhythm("2&", 6, grouping).includes(5.5, 6, grouping))

    def test_the_quarter_points_scale_with_the_group(self):
        """`e` and `a` are a quarter and three quarters of a three-beat group."""
        grouping = _six_eight()
        self.assertTrue(parse_rhythm("1e", 6, grouping).includes(1.75, 6, grouping))
        self.assertTrue(parse_rhythm("1a", 6, grouping).includes(3.25, 6, grouping))

    def test_the_last_felt_beat_is_the_second_one(self):
        """`last` names the second pulse, whose start is the bar's fourth eighth."""
        grouping = _six_eight()
        rhythm = parse_rhythm("last", 6, grouping)
        self.assertEqual(rhythm.positions, (2.0,))
        self.assertTrue(rhythm.includes(4.0, 6, grouping))
        self.assertFalse(rhythm.includes(1.0, 6, grouping))

    def test_felt_beat_is_a_fraction_of_the_group(self):
        """The conversion the membership test is spelled on, stated directly."""
        self.assertEqual(felt_beat(1.0, 6, (3, 3)), 1.0)
        self.assertAlmostEqual(felt_beat(2.0, 6, (3, 3)), 1 + 1 / 3)
        self.assertEqual(felt_beat(4.0, 6, (3, 3)), 2.0)
        self.assertAlmostEqual(felt_beat(5.5, 6, (3, 3)), 2.5)
        self.assertEqual(felt_beat(7.0, 6, (3, 3)), 3.0)

    def test_a_grouping_that_does_not_partition_the_bar_is_refused(self):
        """The metre is validated before a token is read, as `TimeSignature` is."""
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("1", 6, (2, 2))
        self.assertIn("spans 4 beats", str(caught.exception))


class TestTheList(unittest.TestCase):
    """A list replaces the default; `melody` may stand beside positions."""

    def test_melody_and_a_position_are_both_kept(self):
        """The motivating request: harmonise the tune and stab on the and of 1."""
        rhythm = parse_rhythm("melody,1&", 4)
        self.assertTrue(rhythm.melody)
        self.assertTrue(rhythm.wants_melody)
        self.assertEqual(rhythm.positions, (1.5,))
        self.assertTrue(rhythm.includes(1.5, 4))
        self.assertFalse(rhythm.is_none)

    def test_order_and_duplicates_are_not_part_of_the_request(self):
        """`3,1,1,2&` and `1,2&,3` are one value, and one canonical string."""
        self.assertEqual(parse_rhythm("3,1,1,2&", 4), parse_rhythm("1,2&,3", 4))
        self.assertEqual(str(parse_rhythm("3,1,1,2&", 4)), "1,2&,3")

    def test_none_is_the_one_token_that_cannot_be_combined(self):
        """`none,1&` and `none,melody` are refused rather than resolved."""
        for text in ("none,1&", "none,melody", "1&,none"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as caught:
                    parse_rhythm(text, 4)
                self.assertIn("none", str(caught.exception))

    def test_none_and_an_empty_list_both_mean_absent(self):
        """There is no rhythm to place, and the canonical spelling says so once."""
        for text in ("none", "", "   "):
            with self.subTest(text=text):
                rhythm = parse_rhythm(text, 4)
                self.assertTrue(rhythm.is_none)
                self.assertEqual(str(rhythm), "none")
        self.assertTrue(Rhythm().is_none)

    def test_a_bare_melody_rhythm_is_not_none(self):
        """`melody` is a real request even though it names no position."""
        rhythm = parse_rhythm("melody", 4)
        self.assertTrue(rhythm.wants_melody)
        self.assertFalse(rhythm.is_none)
        self.assertFalse(rhythm.includes(1.0, 4))

    def test_case_and_whitespace_are_not_part_of_the_request(self):
        self.assertEqual(parse_rhythm(" MELODY , 1& ", 4), parse_rhythm("melody,1&", 4))

    def test_the_value_is_frozen(self):
        """A request written halfway through arranging is worse than a refused one."""
        rhythm = parse_rhythm("1&", 4)
        with self.assertRaises(FrozenInstanceError):
            rhythm.positions = ()  # type: ignore[misc]


class TestTheRefusals(unittest.TestCase):
    """A token nobody recognises is a question, not a request for silence."""

    def test_a_position_the_metre_lacks_names_the_metre(self):
        """`3` in a 2/2 bar is refused, not clamped to the last beat."""
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("3", 2)
        message = str(caught.exception)
        self.assertIn("felt beat 3", message)
        self.assertIn("has 2", message)

    def test_zero_and_a_beat_past_the_bar_are_refused(self):
        for text in ("0", "5"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_rhythm(text, 4)

    def test_a_decimal_is_not_a_position(self):
        """`1.5` names a time; the grammar names a place on the metre's grid."""
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("1.5", 4)
        self.assertIn("1.5", str(caught.exception))

    def test_an_unknown_token_lists_the_vocabulary(self):
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("swing", 4)
        message = str(caught.exception)
        self.assertIn("every-beat", message)
        self.assertIn("last&", message)

    def test_an_empty_entry_is_refused(self):
        with self.assertRaises(ValueError):
            parse_rhythm("1,,2", 4)

    def test_a_doubled_subdivision_is_refused(self):
        with self.assertRaises(ValueError):
            parse_rhythm("1&&", 4)

    def test_a_position_off_the_named_subdivisions_is_refused(self):
        """A programmatic value cannot smuggle in a position the grammar lacks."""
        with self.assertRaises(ValueError):
            Rhythm(positions=(1.1,))




class TestTheCanonicalSpelling(unittest.TestCase):
    """One request has one spelling, and the run header's spelling parses back."""

    def test_each_position_has_one_token(self):
        cases = {
            "1": "1",
            "1e": "1e",
            "1&": "1&",
            "1a": "1a",
            "last": "4",
            "last&": "4&",
            "every-beat": "1,2,3,4",
            "melody,1&": "melody,1&",
            "3,1,2&": "1,2&,3",
        }
        for text, canonical in cases.items():
            with self.subTest(text=text):
                self.assertEqual(str(parse_rhythm(text, 4)), canonical)
        self.assertEqual(str(parse_rhythm("every-beat", 2)), "1,2")
        self.assertEqual(str(parse_rhythm("every-beat", 6, (3, 3))), "1,2")
        self.assertEqual(str(parse_rhythm("last&", 3)), "3&")

    def test_the_spelling_round_trips(self):
        """Under every metre the grammar accepts, `parse(str(x)) == x`."""
        metres = ((2, None), (3, None), (4, None), (6, (3, 3)))
        spellings = (
            "melody",
            "none",
            "every-beat",
            "1",
            "1&",
            "1e",
            "1a",
            "last",
            "last&",
            "melody,1&",
            "1,2&,3",
            "2,1",
        )
        for beats, grouping in metres:
            for text in spellings:
                with self.subTest(metre=beats, grouping=grouping, text=text):
                    # A spelling naming a beat this metre lacks is refused on
                    # input; the round trip is asserted on the ones it accepts.
                    try:
                        rhythm = parse_rhythm(text, beats, grouping)
                    except ValueError:
                        continue
                    again = parse_rhythm(str(rhythm), beats, grouping)
                    self.assertEqual(again, rhythm)
                    self.assertEqual(str(again), str(rhythm))


if __name__ == "__main__":
    unittest.main()
