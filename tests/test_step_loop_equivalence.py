"""The two step loops must produce the same arrangement.

`VoiceLeadingEngine.arrange_progression` and `arrange_slots` are two loops
over the same slots. They used to hold two copies of six decisions, kept in step
by a comment reading *"Both copies must agree"* - which is not a mechanism, and the
project had already paid for that once: a second caller was built separately,
drifted, and voiced an `Am7` under a written `Bbm7` for twenty-five transcriptions
before anyone noticed.

Phase 3 moved five of those decisions into `decisions`, so each had one
implementation. Phase 4 then removed the second loop outright: `arrange_slots` is
now a pre-pass plus a call.

**What this file tests changed with that, and it is worth being explicit about.**
"Both entry points produce the same arrangement" is now true *by construction* -
there is one implementation - so as a statement about the engine it is close to
vacuous. It is not vacuous as a statement about the **adapter**: `arrange_slots`
still has to pass the right texture, the right grips, the right metre, the right
timings and the right slash bass, and a wrong request produces a wrong arrangement
while every unit test inside the engine still passes. That is what the matrix below
catches, and it is a real failure mode rather than a formality.

The second class guards the *structure* instead: that each decision still has one
definition, that the engine still calls it, and that `slots` has not grown a loop
of its own. That is the check that would catch a well-meaning future "small
optimisation" that reintroduces a second copy.

**`slots` is where `wjazzd.arrange_slots` moved when the database was removed.**
The assertions below were re-pointed at it rather than deleted, which is trap 5's
rule again: the claim "this module does not contain a step loop" is still a claim
about a file that exists, and the file is now named `arranger.slots`.

No `skipUnless` here. These are hand-built fixtures with no database and no optional
dependency, so this file always runs - which is the property that makes it worth
having as the guard on a structural refactor.
"""

import importlib
import unittest
from typing import List, Optional, Tuple

from arranger import Diagnostics, VoiceLeadingEngine, slots

# (melody, quality, name) triples chosen to cover the decision points rather than to
# be a tune: a chord tone, a 9th the extension strategy absorbs, a note with no route
# at all, a low melody that can only be a shell, and an NC bar.
TRIPLES: List[Tuple[str, str, str]] = [
    ("C5", "maj7", "Cmaj7"),   # root
    ("B4", "maj7", "Cmaj7"),   # leading tone - a chord tone
    ("D5", "maj7", "Cmaj7"),   # 9th, absorbed by the extension strategy
    ("A4", "7", "G7"),         # 9th over a dominant
    ("F4", "m7", "Dm7"),       # low, likely a shell
    ("C4", "m7b5", "Dm7b5"),   # lowest register in the suite
    ("G#4", "m7b5", "Dm7b5"),  # no extension route: the fallback warns
    ("Eb5", "m7", "Cm7"),      # minor 3rd
    ("B4", "NC", "NC"),        # no harmony at all
]

TEXTURES = ("uniform", "targets", "walking_bass")

# The five decisions Phase 3 gave one implementation each.
DECISIONS = (
    "resolve_texture_grips",
    "melody_alone_case",
    "should_promote_fill",
    "should_demote_to_melody_alone",
    "is_repeated_step",
)


def timings_for(count: int, beats_per_bar: int = 4):
    """One slot per triple, walking the bar so every texture gets a beat grid.

    The walking bass needs a grid to place four quarters on; without one it
    degrades to a single note per slot, which would not exercise the decisions this
    file exists to compare.
    """
    out: List[Tuple[int, float, Optional[float]]] = []
    for index in range(count):
        beat = float(index % beats_per_bar) + 1.0
        out.append((index // beats_per_bar, beat, None))
    return out


def through_library(triples, timings, texture, **kwargs):
    diagnostics = Diagnostics()
    steps = VoiceLeadingEngine.arrange_progression(
        triples, timings=timings, texture=texture, diagnostics=diagnostics, **kwargs
    )
    return steps, diagnostics.warnings


def through_slots(triples, timings, texture, **kwargs):
    diagnostics = Diagnostics()
    steps, _rescued, _notes = slots.arrange_slots(
        triples, timings=timings, texture=texture, diagnostics=diagnostics, **kwargs
    )
    return steps, diagnostics.warnings


def source_of(module_name: str) -> str:
    """A module's source, for the tests that assert on *where* a decision lives.

    Closed explicitly: the suite is run with ResourceWarnings visible, and an
    unclosed handle here would be the only leak in it. `__file__` is Optional
    only for a namespace package, and a `None` here would be a broken checkout
    rather than something to handle.
    """
    path = importlib.import_module(module_name).__file__
    assert path is not None, f"{module_name} has no source file"
    with open(path) as handle:
        return handle.read()


class TestTheTwoLoopsAgree(unittest.TestCase):
    """The property Phase 3 exists to establish."""

    def assert_same_arrangement(self, triples, texture, **kwargs):
        timings = timings_for(len(triples))
        mine, my_warnings = through_library(triples, timings, texture, **kwargs)
        theirs, their_warnings = through_slots(triples, timings, texture, **kwargs)

        self.assertEqual(
            [step.tab_line() for step in mine],
            [step.tab_line() for step in theirs],
            f"{texture}: the two entry points voiced one slot differently",
        )
        for field in ("grip", "partial", "repeated", "role", "metric_weight", "melody_only"):
            self.assertEqual(
                [getattr(step, field) for step in mine],
                [getattr(step, field) for step in theirs],
                f"{texture}: the two entry points disagree about {field!r}",
            )
        self.assertEqual(
            my_warnings,
            their_warnings,
            f"{texture}: the two entry points report different warnings",
        )
        return mine

    def test_every_texture_over_the_shared_fixtures(self):
        for texture in TEXTURES:
            with self.subTest(texture=texture):
                self.assert_same_arrangement(TRIPLES, texture)

    def test_each_pair_of_adjacent_triples(self):
        """Every *transition* in the fixture, because most of the decisions compare a
        step with the one before it: the repeated-melody hold, the fill promotion,
        and the NC route all read the previous step."""
        for texture in TEXTURES:
            for first in range(len(TRIPLES) - 1):
                pair = TRIPLES[first: first + 2]
                with self.subTest(texture=texture, pair=pair):
                    self.assert_same_arrangement(pair, texture)

    def test_a_melody_alone_walk_agrees(self):
        """A single melody over one bar, the shape the walking-bass tests use."""
        for texture in TEXTURES:
            with self.subTest(texture=texture):
                self.assert_same_arrangement([("F5", "maj7", "Fmaj7")], texture)

    def test_a_grip_the_texture_never_uses_agrees(self):
        """The empty-intersection warning path, which both loops used to format
        separately."""
        for texture in ("targets", "walking_bass"):
            with self.subTest(texture=texture):
                self.assert_same_arrangement(TRIPLES[:4], texture, grips=("duo",))

    def test_a_grip_the_role_does_use_agrees(self):
        """The narrowing path, which is not the empty-intersection warning."""
        for texture in TEXTURES:
            with self.subTest(texture=texture):
                self.assert_same_arrangement(TRIPLES[:4], texture, grips=("shell",))


class TestTheDecisionsAreActuallyShared(unittest.TestCase):
    """Guards the *mechanism*, not just the outcome.

    Two functions can agree by accident - on the fixtures chosen here - and drift
    later. These assert that each decision has exactly one definition and is called
    from both loops, so the agreement above is structural rather than lucky.
    """

    def test_each_decision_is_defined_once_in_decisions(self):
        import arranger.decisions as decisions

        source = source_of("arranger.decisions")
        for name in DECISIONS:
            with self.subTest(decision=name):
                self.assertEqual(
                    source.count(f"def {name}("),
                    1,
                    f"{name} has more than one definition",
                )
                self.assertTrue(callable(getattr(decisions, name)))

    def test_neither_loop_reimplements_a_decision(self):
        """The old failure mode, stated as a test: the decision's own text appearing
        in a loop body is the signature of a copy that has come back."""
        snippets = (
            "role_grips = texture_grips[role]",
            "narrowed = tuple(g for g in",
            'fret_span() >= GRIP_MAX_SPAN["drop2"]',
            "sounding_harmony(previous_step)",
        )
        for module_name in ("arranger", "arranger.steps", "arranger.movement", "arranger.slots"):
            source = source_of(module_name)
            for snippet in snippets:
                with self.subTest(module=module_name, snippet=snippet):
                    self.assertNotIn(
                        snippet,
                        source,
                        f"{module_name} reimplements a decision that lives in `decisions`",
                    )

    def test_the_engine_is_the_only_step_loop(self):
        """Since Phase 4 there is one loop, and it is the engine's.

        This class used to assert that *both* loops called each decision. That
        premise is now false by design - `slots` delegates rather than looping -
        so the assertion is inverted: the decisions are called from the engine, and
        `slots` must not have grown a loop of its own. A test that keeps asserting
        the old shape would be a test resisting the refactor it exists to protect.

        The loop is `arranger.movement` rather than `arranger`: Phase 5 made
        `__init__.py` a facade, so reading *its* source would pass on a package
        whose step loop had been deleted outright. `arranger.steps` was the loop's
        home until the loop moved to `movement`; `steps` is a facade now too, so
        this is re-pointed a second time rather than dropped.
        """
        engine = source_of("arranger.movement")
        for name in DECISIONS:
            with self.subTest(decision=name):
                self.assertIn(f"{name}(", engine, f"the engine does not call {name}")

    def test_the_slot_layer_does_not_contain_a_step_loop(self):
        """`slots` asks the engine for an arrangement; it does not build one.

        This was `test_the_corpus_does_not_contain_a_step_loop`, reading
        `wjazzd`, and it is re-pointed rather than dropped: `arrange_slots` now
        lives in `arranger.slots`, and a second loop creeping back into it would
        be exactly the defect the original test was written to catch. Inverted
        twice over, in the sense trap 5 describes - the premise changed twice
        (a second loop, then a second module) and the assertion against a copy
        has not.
        """
        slot_source = source_of("arranger.slots")
        for snippet in (
            "prepare_step(",
            "_best_voicing(",
            "ArrangementStep(",
        ):
            with self.subTest(snippet=snippet):
                self.assertNotIn(
                    snippet,
                    slot_source,
                    "arranger.slots has grown a step loop again; it should delegate",
                )
