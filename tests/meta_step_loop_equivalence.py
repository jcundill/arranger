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

from arranger import VoiceLeadingEngine, slots
from arranger.options import ArrangeOptions, Request

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

CHORD_CONTENTS = ("full", "targets", "2")

# The decisions the step loop makes: one implementation each, all of them called from
# `arranger.movement` rather than re-derived there.
DECISIONS = (
    "resolve_texture_grips",
    "melody_alone_case",
    "should_promote_fill",
    "should_demote_to_melody_alone",
    "holds_the_shape",
    "hold_the_melody_string",
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


def through_library(triples, timings, request, **kwargs):
    steps = VoiceLeadingEngine.arrange_progression(
        triples,
        timings=timings,
        options=ArrangeOptions(request=request, **kwargs),
    )
    return steps


def through_slots(triples, timings, request, **kwargs):
    steps, _rescued, notes = slots.arrange_slots(
        triples,
        timings=timings,
        options=ArrangeOptions(request=request, **kwargs),
    )
    return steps, notes


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

    def assert_same_arrangement(self, triples, request, label, **kwargs):
        timings = timings_for(len(triples))
        mine = through_library(triples, timings, request, **kwargs)
        theirs, their_notes = through_slots(triples, timings, request, **kwargs)

        self.assertEqual(
            [step.tab_line() for step in mine],
            [step.tab_line() for step in theirs],
            f"{label}: the two entry points voiced one slot differently",
        )
        for field in ("grip", "partial", "repeated", "role", "metric_weight", "melody_only"):
            self.assertEqual(
                [getattr(step, field) for step in mine],
                [getattr(step, field) for step in theirs],
                f"{label}: the two entry points disagree about {field!r}",
            )
        self.assertEqual(
            their_notes,
            [],
            f"{label}: the slot wrapper added notes of its own",
        )
        return mine

    def test_every_chord_content_over_the_shared_fixtures(self):
        for content in CHORD_CONTENTS:
            with self.subTest(chord_notes=content):
                self.assert_same_arrangement(TRIPLES, Request(chord_notes=content), content)

    def test_each_pair_of_adjacent_triples(self):
        """Every *transition* in the fixture, because most of the decisions compare a
        step with the one before it: the repeated-melody hold, the fill promotion,
        and the NC route all read the previous step."""
        for content in CHORD_CONTENTS:
            for first in range(len(TRIPLES) - 1):
                pair = TRIPLES[first: first + 2]
                with self.subTest(chord_notes=content, pair=pair):
                    self.assert_same_arrangement(
                        pair, Request(chord_notes=content), content
                    )

    def test_a_melody_alone_walk_agrees(self):
        """A single melody over one bar, the shape the walking-bass tests use."""
        for content in CHORD_CONTENTS:
            with self.subTest(chord_notes=content):
                self.assert_same_arrangement(
                    [("F5", "maj7", "Fmaj7")], Request(chord_notes=content), content
                )

    def assert_same_refusal(self, triples, request, label, **kwargs):
        """Both entry points refuse one request identically.

        **Rewritten from `test_a_grip_the_texture_never_uses_agrees`.** That test
        compared the *warnings* the two loops formatted for a grip the texture never
        uses, which was the remaining half of a check written when `wjazzd.arrange_slots`
        held a near-verbatim second copy of the loop. The copy is long gone - `arrange_slots`
        delegates - and the refusal is a `ValueError` now, so what remains to compare is
        that both spellings raise the same message rather than that they print the same
        line. That is a stronger claim: one entry point silently accepting a request the
        other refuses would fail here.
        """
        timings = timings_for(len(triples))
        with self.assertRaises(ValueError) as from_library:
            through_library(triples, timings, request, **kwargs)
        with self.assertRaises(ValueError) as from_slots:
            through_slots(triples, timings, request, **kwargs)
        self.assertEqual(
            str(from_library.exception),
            str(from_slots.exception),
            f"{label}: the two entry points refuse one request differently",
        )

    def test_a_request_the_axes_refuse_agrees(self):
        """Both loops refuse one request with one message.

        **Rewritten from `test_a_grip_the_texture_never_uses_agrees`.** The request used to
        be a `grips=` narrowing; the family axis is deleted, so what is compared here is the
        bass refusal - a bass *content* beside a layer the request leaves silent. One entry
        point silently accepting what the other refuses is what this catches.
        """
        for label, request in (
            ("chord", Request(melody=False, bass_notes="walk")),
            ("melody", Request(chord_on="none", bass_notes="walk")),
        ):
            with self.subTest(selection=label):
                self.assert_same_refusal(TRIPLES[:4], request, label)

    def test_a_narrowed_palette_agrees(self):
        """A narrowed palette is the texture's now, and the thumb line is where it bites.

        **Rewritten from `test_a_grip_the_role_does_use_agrees`.** What a caller narrowed
        was a `grips=` list, and the family axis is deleted; the chord content owns the
        arity, so `test_every_chord_content_over_the_shared_fixtures` above sweeps every
        narrowing there is. What is left here is the path a walk needs - a rule that merges
        a thumb note into a shape the hand is holding, which no other test in this file
        asks for.
        """
        for content in ("targets", "full"):
            with self.subTest(chord_notes=content):
                self.assert_same_arrangement(
                    TRIPLES[:4],
                    Request(
                        chord_notes=content, bass_on="every-beat", bass_notes="walk"
                    ),
                    content,
                )


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
        for module_name in (
            "arranger",
            "arranger.steps",
            "arranger.movement",
            "arranger.route_dispatch",
            "arranger.slots",
        ):
            source = source_of(module_name)
            for snippet in snippets:
                with self.subTest(module=module_name, snippet=snippet):
                    self.assertNotIn(
                        snippet,
                        source,
                        f"{module_name} reimplements a decision that lives in `decisions`",
                    )

    def test_the_engine_is_the_only_step_loop(self):
        """There is one step loop, and it is the engine's.

        The decisions are called from the engine, and `slots` must not have a loop of
        its own: it delegates rather than looping.

        The loop is `arranger.movement` rather than `arranger`, because
        `__init__.py` is a facade, so reading *its* source would pass on a package
        whose step loop had been deleted outright. `arranger.steps` was the loop's
        home until the loop moved to `movement`; `steps` is a facade now too, so
        this is re-pointed a second time rather than dropped.

        It is re-pointed a third time here, to the **set** of modules the engine is
        made of. The per-slot plan was extracted to `slot_plan`, the axis
        resolvers to `resolution`, and the melody-bearing route to
        `harmonised_route`, so decisions the loop calls are now one or two
        modules away from `movement` itself. Reading `movement` alone would have
        asserted that those are *not* called - the opposite of what this test
        exists to protect - and dropping them from `DECISIONS` would have retired
        the check for the busiest decision in the engine.
        """
        engine = " ".join(
            source_of(name)
            for name in (
                "arranger.movement",
                "arranger.harmonised_route",
                "arranger.slot_plan",
                "arranger.resolution",
            )
        )
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
