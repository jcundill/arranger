"""The left hand's budget: the finger count, the reach, and the one predicate asking both.

`arranger.fingers` owns the *step*-level question a generated grip never asks, because a
generated grip's own bounds are stricter: a shape merged with a thumb note can need a fifth
finger or reach further than the hand spans. `can_fret` is the predicate, and the two
refusals in it are separate - neither implies the other.

`TestTheEngineUsesItForOneQuestion` is what holds the module to its callers: it was
`TestTheModuleIsInert` and is inverted rather than deleted (AGENTS.md trap 5), because the
premise it asserted is exactly what the caller set answers now.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import arranger
from arranger.fingers import (
    MAX_HAND_SPAN,
    can_fret,
    fingers_needed,
    hand_span,
)


class TestTheFiveFretRefusal(unittest.TestCase):
    """The one shape four fingers cannot hold, and why refusing is a value rather than a raise."""

    def test_five_distinct_frets_are_refused(self) -> None:
        """One finger holds one fret, so five distinct frets need five fingers."""
        self.assertEqual(fingers_needed([-1, 3, 5, 6, 7, 8]), 5)
        self.assertFalse(can_fret([-1, 3, 5, 6, 7, 8]))

    def test_the_refusal_is_the_merged_walking_bass_step(self) -> None:
        """A four-note shape plus the thumb note below it is five distinct frets.

        The upper shape alone is playable; adding the thumb at fret 3 - a step below the
        shape's lowest fret, which is where a walking bass sits - makes it something the left
        hand cannot finger, because the thumb is a *right-hand* pluck and the left hand has
        only four fingers. So this is the §4.3 hook itself: the shape the measurement looks
        for.
        """
        self.assertTrue(can_fret([-1, 5, 6, 7, 8, -1]))
        self.assertFalse(can_fret([3, 5, 6, 7, 8, -1]))

    def test_five_strings_is_fine_when_two_of_them_share_a_fret(self) -> None:
        """The bound is distinct *frets*, not sounding strings, and a barre buys the fifth.

        `5-5-6-7-8-x` sounds five strings: the index bars the low E and the A at 5, leaving
        three fingers for 6, 7 and 8. Reading the refusal as "at most four strings" would call
        this shape unplayable, which is the opposite of what a player would say.
        """
        self.assertEqual(fingers_needed([5, 5, 6, 7, 8, -1]), 4)
        self.assertTrue(can_fret([5, 5, 6, 7, 8, -1]))


class TestTheFourFretBudget(unittest.TestCase):
    """§4.3's left-hand half: five distinct frets is not a hard shape, it is an impossible one.

    Asserted on a bare vector rather than on a `Voicing` because that is the level the refusal
    lives at: `bass_place.place_bass` asks *before* it picks a string, and the shape it asks about
    is one the hand is **already holding** with the candidate fret added, which is not a
    `Voicing` anyone builds.
    """

    def test_open_strings_and_muted_strings_cost_no_finger(self) -> None:
        """Fret 0 is an open string and -1 is silence: neither one asks for a finger."""
        self.assertEqual(fingers_needed([-1, 0, -1, 0, -1, -1]), 0)
        self.assertTrue(can_fret([-1, 0, -1, 0, -1, -1]))

    def test_four_distinct_frets_is_the_limit_and_five_is_refused(self) -> None:
        """One finger holds one fret, so the budget is the hand's own size, not a span."""
        self.assertEqual(fingers_needed([-1, 9, -1, 8, 12, 10]), 4)
        self.assertTrue(can_fret([-1, 9, -1, 8, 12, 10]))
        self.assertEqual(fingers_needed([7, 9, -1, 8, 12, 10]), 5)
        self.assertFalse(can_fret([7, 9, -1, 8, 12, 10]))

    def test_one_fret_shared_by_two_strings_is_one_finger(self) -> None:
        """Constraint 3, which is why the count is over frets and not over strings."""
        self.assertEqual(fingers_needed([-1, 5, 5, 5, -1, -1]), 1)
        self.assertTrue(can_fret([-1, 5, 7, 9, 5, 10]))

    def test_the_merged_hand_the_engine_had_to_refuse(self) -> None:
        """The one hand in the committed heads that needed five frets, as the engine sees it.

        "Synthetic Tab Export" in the reported bar under `--chord-notes targets --bass-notes root`
        holds a drop-3 `x-9-x-8-12-10` - four frets - and the walk's B lands on the low E at
        fret 7, off it. The low E is the *only* candidate: the A string is spoken for by the
        held shape and a B on the D string at fret 9 would sound above the shape's F#3, which
        `place_bass` forbids. So the shape is refused rather than written, and
        `tests/test_walking_bass.py` asserts the same fact on the arrangement.
        """
        held = [-1, 9, -1, 8, 12, 10]
        thumb_string, thumb_fret = 0, 7
        hand = list(held)
        hand[thumb_string] = thumb_fret
        self.assertEqual(hand, [7, 9, -1, 8, 12, 10])
        self.assertEqual(fingers_needed(hand), 5)
        self.assertFalse(can_fret(hand))


class TestTheHandsReach(unittest.TestCase):
    """The bound the finger count cannot see: five frets, index to pinky.

    `fingers_needed` answers *how many fingers* and `hand_span` answers *how far apart they
    are*. The merged walking-bass step can pass the first and fail the second - the reported
    hand is three fingers and eight frets - so the two are separate refusals in `can_fret`,
    and neither implies the other.

    The figures and the bar they came from are `docs/history/open-issues.md` item 5's business; what
    this class holds is the rule, at the level it is stated: a bare fret vector, which is
    what `bass_place.place_bass` and `bass_merge._takes_the_ring` ask about.
    """

    def test_the_bound_is_the_hand_and_one_fret_wider_is_refused(self) -> None:
        """Five frets apart is the reach; six is not, however few the fingers."""
        self.assertEqual(MAX_HAND_SPAN, 5)
        self.assertTrue(can_fret([-1, 5, 6, 7, 5 + MAX_HAND_SPAN, -1]))
        self.assertFalse(can_fret([-1, 5, 6, 7, 5 + MAX_HAND_SPAN + 1, -1]))

    def test_an_open_string_does_not_widen_the_hand(self) -> None:
        """Fret 0 takes no finger, so it is not the hand's bottom - as in `fingers_needed`."""
        self.assertEqual(hand_span([0, -1, 3, 4, -1, -1]), 1)
        self.assertTrue(can_fret([0, -1, 3, 4, -1, -1]))

    def test_a_shape_with_nothing_fretted_spans_nothing(self) -> None:
        self.assertEqual(hand_span([-1, -1, -1, -1, -1, -1]), 0)
        self.assertEqual(hand_span([-1, -1, 9, -1, -1, -1]), 0)

    def test_the_reported_hand_is_three_fingers_and_eight_frets(self) -> None:
        """`[1, 8, -1, 8, 9, -1]`: the thumb seven frets under a three-fret shape.

        It passes the finger budget and fails the hand, which is the whole defect: the
        count was the only test, so this vector was written and played.
        """
        hand = [1, 8, -1, 8, 9, -1]
        self.assertEqual(fingers_needed(hand), 3)
        self.assertEqual(hand_span(hand), 8)
        self.assertFalse(can_fret(hand))


class TestTheEngineUsesItForOneQuestion(unittest.TestCase):
    """§4.3's left-hand half - not inert any more, and exactly two modules read it.

    This class **was** `TestTheModuleIsInert`, and it is inverted rather than deleted for the
    reason AGENTS.md trap 5 gives: the premise it asserted ("nothing in the engine imports
    this") is what §5 step 3 was waiting on, and the §4.3 measurement falsified it. The useful
    assertion is now "exactly these do, and here is what moved", so a *second* engine
    caller is as visible as the first was - which is the whole reason to name the set rather
    than count it.
    """

    def test_the_only_engine_callers_are_the_two_thumb_questions(self) -> None:
        """`bass_place` imports `fingers` for the fret budget, `bass_merge` for the ring.

        Read from the AST rather than from `sys.modules`, for the reason
        `meta_package_dag._imports_of` gives: a function-local import shows up here, which is
        exactly what should be caught, and it does not depend on what some other test happened
        to import first.
        """
        package = Path(arranger.__file__).parent
        importers = set()
        for path in sorted(package.glob("*.py")):
            if path.stem in {"__init__", "fingers"}:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.ImportFrom):
                    continue
                names_fingers = node.module == "fingers" or any(
                    alias.name == "fingers" for alias in node.names
                )
                if names_fingers:
                    importers.add(path.stem)
        self.assertEqual(
            importers,
            {"bass_place", "bass_merge"},
            "the set of engine modules reading fingers changed: `bass_place` asks the "
            "fret budget, and `bass_merge` asks the same question of a **carried** thumb "
            "- a note that keeps ringing only if the hand holding the new shape can "
            "still reach it",
        )

    def test_the_facade_binds_it_as_a_public_path(self) -> None:
        """`arranger.fingers` is reachable, which is what the DAG check needs.

        `tests/meta_package_dag.py::test_every_module_is_imported_by_something` counts
        `__init__` as an importer, and the facade binds every engine submodule for that
        reason and so that `arranger.fingers` resolves without the caller importing it
        first. It is a **path** rather than a name the facade defines, so it is
        deliberately *absent* from `arranger.__all__` - and the name the engine reads,
        `can_fret`, is reached through it.
        """
        self.assertIs(arranger.fingers.can_fret, can_fret)
        self.assertNotIn("fingers", arranger.__all__)


if __name__ == "__main__":
    unittest.main()
