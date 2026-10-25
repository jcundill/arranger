"""The rhythm grammar: direct positions in felt beats.

`Rhythm` is the request the arrangement is asked with. Its positions are **felt
beats**, not denominator units, so `1and` is the midpoint of the bar's first felt
beat in 2/2, 4/4 and 6/8 alike - a quarter-note offbeat in the first, an eighth-note
offbeat in the second, and the midpoint of a dotted-quarter pulse in the third.

The midpoint is spelled `and` rather than the musical `&`, because a position is a
command-line argument and an unquoted `&` is a shell's background operator: a token
the shell eats never reaches the parser. What is verified, in order:

- **the simple metres**: `every-beat` follows the denominator count (2, 3 and 4),
  and `1and` / `3and` land halfway through their felt beat;
- **the compound metre**: `every-beat` follows the grouping, so 6/8 has two felt
  beats and its second one is the bar's fourth eighth - and `and` is the midpoint of
  the dotted-quarter pulse rather than a fixed half-beat;
- **the list**: a list replaces the default, `melody` may stand beside positions,
  order and duplicates are not part of the request, and `none` is the one token
  that cannot be combined;
- **the cycle**: `:` separates the bars of a figure longer than one bar, its first
  segment lands on the form's **first complete bar** - so an anacrusis takes the
  tune rather than consuming a bar of the figure - and it repeats from there;
- **the refusals**: a position the metre does not have, an unknown token, a decimal,
  an empty entry, an empty *bar* and the shell-unsafe `&` all raise, because each is
  a question rather than silence;
- **the canonical spelling**: one position has one token, the run header's spelling
  parses back to the same value and contains no shell metacharacter, and the round
  trip is asserted over every metre.

No arrangement is built here. This is the grammar's own test; the step loop reads
it in the stages that follow.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from arranger import BarRhythm, Rhythm, TimeSignature, felt_beat, parse_rhythm

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
                    rhythm.at(1).positions, tuple(float(n) for n in range(1, beats + 1))
                )
                for beat in range(1, beats + 1):
                    self.assertTrue(rhythm.at(1).includes(float(beat), beats, None))

    def test_the_and_is_halfway_through_its_felt_beat(self):
        """`1and` is 1.5 and `3and` is 3.5 where those beats exist."""
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertTrue(parse_rhythm("1and", beats).at(1).includes(1.5, beats))
                self.assertFalse(parse_rhythm("1and", beats).at(1).includes(1.0, beats))
        self.assertTrue(parse_rhythm("3and", 3).at(1).includes(3.5, 3))
        self.assertTrue(parse_rhythm("lastand", 2).at(1).includes(2.5, 2))

    def test_the_quarter_and_three_quarter_points_are_named(self):
        """`e` and `a` are 0.25 and 0.75 into the felt beat."""
        rhythm = parse_rhythm("1e,1a", 4)
        self.assertTrue(rhythm.at(1).includes(1.25, 4))
        self.assertTrue(rhythm.at(1).includes(1.75, 4))
        self.assertFalse(rhythm.at(1).includes(1.5, 4))

    def test_a_bar_relative_position_is_not_an_absolute_one(self):
        """The same token is the same place in every bar, not the same time."""
        rhythm = parse_rhythm("1and", 4)
        self.assertTrue(rhythm.at(1).includes(1.5, 4))
        self.assertFalse(rhythm.at(1).includes(2.5, 4))
        self.assertFalse(rhythm.at(1).includes(4.5, 4))



class TestTheCompoundMetre(unittest.TestCase):
    """6/8 is felt in two, and `every-beat` must follow the grouping."""

    def test_every_beat_is_one_attack_per_felt_beat(self):
        """Two dotted-quarter pulses, not six eighth-note units."""
        grouping = _six_eight()
        self.assertEqual(grouping, (3, 3))
        rhythm = parse_rhythm("every-beat", 6, grouping)
        self.assertEqual(rhythm.at(1).positions, (1.0, 2.0))
        self.assertTrue(rhythm.at(1).includes(1.0, 6, grouping))
        self.assertTrue(rhythm.at(1).includes(4.0, 6, grouping))
        self.assertFalse(rhythm.at(1).includes(2.0, 6, grouping))

    def test_the_and_is_the_midpoint_of_the_dotted_quarter(self):
        """`1and` is 2.5 beats into the bar, not 1.5 and not the third eighth."""
        grouping = _six_eight()
        self.assertTrue(parse_rhythm("1and", 6, grouping).at(1).includes(2.5, 6, grouping))
        self.assertFalse(parse_rhythm("1and", 6, grouping).at(1).includes(1.5, 6, grouping))
        self.assertTrue(parse_rhythm("2and", 6, grouping).at(1).includes(5.5, 6, grouping))

    def test_the_quarter_points_scale_with_the_group(self):
        """`e` and `a` are a quarter and three quarters of a three-beat group."""
        grouping = _six_eight()
        self.assertTrue(parse_rhythm("1e", 6, grouping).at(1).includes(1.75, 6, grouping))
        self.assertTrue(parse_rhythm("1a", 6, grouping).at(1).includes(3.25, 6, grouping))

    def test_the_last_felt_beat_is_the_second_one(self):
        """`last` names the second pulse, whose start is the bar's fourth eighth."""
        grouping = _six_eight()
        rhythm = parse_rhythm("last", 6, grouping)
        self.assertEqual(rhythm.at(1).positions, (2.0,))
        self.assertTrue(rhythm.at(1).includes(4.0, 6, grouping))
        self.assertFalse(rhythm.at(1).includes(1.0, 6, grouping))

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
        rhythm = parse_rhythm("melody,1and", 4)
        self.assertTrue(rhythm.at(1).melody)
        self.assertEqual(rhythm.at(1).positions, (1.5,))
        self.assertTrue(rhythm.at(1).includes(1.5, 4))
        self.assertFalse(rhythm.is_none)

    def test_order_and_duplicates_are_not_part_of_the_request(self):
        """`3,1,1,2and` and `1,2and,3` are one value, and one canonical string."""
        self.assertEqual(parse_rhythm("3,1,1,2and", 4), parse_rhythm("1,2and,3", 4))
        self.assertEqual(str(parse_rhythm("3,1,1,2and", 4)), "1,2and,3")

    def test_none_is_the_one_token_that_cannot_be_combined(self):
        """`none,1and` and `none,melody` are refused rather than resolved."""
        for text in ("none,1and", "none,melody", "1and,none"):
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
        self.assertTrue(rhythm.at(1).melody)
        self.assertFalse(rhythm.is_none)
        self.assertFalse(rhythm.at(1).includes(1.0, 4))

    def test_case_and_whitespace_are_not_part_of_the_request(self):
        self.assertEqual(parse_rhythm(" MELODY , 1and ", 4), parse_rhythm("melody,1and", 4))

    def test_the_value_is_frozen(self):
        """A request written halfway through arranging is worse than a refused one."""
        rhythm = parse_rhythm("1and", 4)
        with self.assertRaises(FrozenInstanceError):
            rhythm.bars = ()  # type: ignore[misc]


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
        self.assertIn("lastand", message)

    def test_the_musical_ampersand_is_refused_and_names_its_spelling(self):
        """`1&` cannot be a token: a shell backgrounds the command at the `&`."""
        for text, spelling in (("1&", "1and"), ("last&", "lastand"), ("melody,2&", "2and")):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as caught:
                    parse_rhythm(text, 4)
                message = str(caught.exception)
                self.assertIn(spelling, message)
                self.assertIn("background operator", message)

    def test_an_empty_entry_is_refused(self):
        with self.assertRaises(ValueError):
            parse_rhythm("1,,2", 4)

    def test_a_doubled_subdivision_is_refused(self):
        with self.assertRaises(ValueError):
            parse_rhythm("1andand", 4)

    def test_a_position_off_the_named_subdivisions_is_refused(self):
        """A programmatic value cannot smuggle in a position the grammar lacks."""
        with self.assertRaises(ValueError):
            BarRhythm(positions=(1.1,))




class TestTheCanonicalSpelling(unittest.TestCase):
    """One request has one spelling, and the run header's spelling parses back."""

    def test_each_position_has_one_token(self):
        cases = {
            "1": "1",
            "1e": "1e",
            "1and": "1and",
            "1a": "1a",
            "last": "4",
            "lastand": "4and",
            "every-beat": "1,2,3,4",
            "melody,1and": "melody,1and",
            "3,1,2and": "1,2and,3",
        }
        for text, canonical in cases.items():
            with self.subTest(text=text):
                self.assertEqual(str(parse_rhythm(text, 4)), canonical)
        self.assertEqual(str(parse_rhythm("every-beat", 2)), "1,2")
        self.assertEqual(str(parse_rhythm("every-beat", 6, (3, 3))), "1,2")
        self.assertEqual(str(parse_rhythm("lastand", 3)), "3and")
        self.assertEqual(str(parse_rhythm("1,3:none:melody,1and", 4)), "1,3:none:melody,1and")

    def test_the_header_spelling_is_safe_to_paste_into_a_shell(self):
        """The run header prints a request; every token it prints must be argv-safe."""
        for text in (
            "1and",
            "lastand",
            "melody,1and",
            "1and,2and,3and,4and",
            "1,3:none",
            "melody:1and,3",
        ):
            with self.subTest(text=text):
                printed = str(parse_rhythm(text, 4))
                for unsafe in "&;|<>()$`*?[]{}":
                    self.assertNotIn(unsafe, printed)
                self.assertEqual(parse_rhythm(printed, 4), parse_rhythm(text, 4))

    def test_the_spelling_round_trips(self):
        """Under every metre the grammar accepts, `parse(str(x)) == x`."""
        metres = ((2, None), (3, None), (4, None), (6, (3, 3)))
        spellings = (
            "melody",
            "none",
            "every-beat",
            "1",
            "1and",
            "1e",
            "1a",
            "last",
            "lastand",
            "melody,1and",
            "1,2and,3",
            "2,1",
            "1,3:none",
            "melody:1and",
            "1:2:2",
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


class TestTheCycle(unittest.TestCase):
    """A figure longer than a bar: `:` separates its bars, and it repeats."""

    def test_one_bar_per_segment(self):
        """`1,3:none:melody` is three bars, and each keeps its own request."""
        rhythm = parse_rhythm("1,3:none:melody", 4)
        self.assertEqual(len(rhythm.bars), 3)
        self.assertEqual(rhythm.at(1).positions, (1.0, 3.0))
        self.assertTrue(rhythm.at(2).is_none)
        self.assertTrue(rhythm.at(3).melody)

    def test_the_cycle_repeats_through_the_form(self):
        """Bar 4 takes bar 1's segment again: a figure is a cycle, not a list."""
        rhythm = parse_rhythm("1,3:none:melody", 4)
        self.assertEqual(rhythm.at(4), rhythm.at(1))
        self.assertEqual(rhythm.at(5), rhythm.at(2))

    def test_the_cycle_starts_at_the_first_complete_bar(self):
        """`first_bar` is where it lands: a pickup bar takes the tune, not segment 1."""
        rhythm = parse_rhythm("1,3:none", 4)
        self.assertTrue(rhythm.at(1, first_bar=2).melody)
        self.assertEqual(rhythm.at(2, first_bar=2).positions, (1.0, 3.0))
        self.assertTrue(rhythm.at(3, first_bar=2).is_none)

    def test_an_unplaced_position_takes_the_first_segment(self):
        """A slot nobody placed cannot be before the cycle, so it is not the pickup."""
        rhythm = parse_rhythm("1,3:none", 4)
        self.assertEqual(rhythm.at(None), rhythm.at(1))

    def test_the_cycle_is_reduced_to_its_shortest_period(self):
        """`1,3:1,3` is `1,3`: a repeated period is one request, not two."""
        self.assertEqual(parse_rhythm("1,3:1,3", 4), parse_rhythm("1,3", 4))
        self.assertEqual(str(parse_rhythm("1:2:1:2", 4)), "1:2")
        self.assertEqual(len(parse_rhythm("1,3:1,4and", 4).bars), 2)

    def test_a_cycle_of_silent_bars_is_none(self):
        """`none:none` is the same request as `none`, and reduces to it."""
        rhythm = parse_rhythm("none:none", 4)
        self.assertTrue(rhythm.is_none)
        self.assertEqual(str(rhythm), "none")

    def test_melody_only_is_every_bar_of_the_cycle(self):
        """A cycle with one bar of positions is not a tune-only figure."""
        self.assertTrue(parse_rhythm("melody:melody", 4).is_melody_only)
        self.assertFalse(parse_rhythm("melody:none", 4).is_melody_only)
        self.assertFalse(parse_rhythm("melody,1and", 4).is_melody_only)

    def test_an_empty_bar_names_the_bar_and_the_fix(self):
        """`1,3::1` is a typo, not a request for silence - `none` spells silence."""
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("1,3::1", 4)
        message = str(caught.exception)
        self.assertIn("bar 2", message)
        self.assertIn("none", message)

    def test_a_refused_position_names_its_bar(self):
        """With more than one bar, 'felt beat 5' is a question about which bar."""
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("1:5", 4)
        self.assertIn("bar 2", str(caught.exception))
        # The one-bar message is unchanged: there is no second bar to name.
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("5", 4)
        self.assertNotIn("bar 1", str(caught.exception))

    def test_none_still_cannot_be_combined_inside_its_bar(self):
        """`none` is alone in *its* bar, and the refusal says which bar that is."""
        with self.assertRaises(ValueError) as caught:
            parse_rhythm("1:none,1and", 4)
        message = str(caught.exception)
        self.assertIn("bar 2", message)
        self.assertIn("none", message)

    def test_a_rhythm_is_at_least_one_bar(self):
        """Silence is spelled `none`; a value with no bars states nothing."""
        with self.assertRaises(ValueError):
            Rhythm(bars=())


if __name__ == "__main__":
    unittest.main()
