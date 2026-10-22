"""The dispatch table: the order, and that every entry can actually fire.

`movement` walks the slots; this table decides which route takes one. The order is a
contract rather than a preference - a texture fill and a comping position that
*decline* a slot they claimed must hand it on, or the tune loses its chord to a
thinner texture - so it is pinned here instead of left in a comment. And each entry
is driven by a request a caller can actually make: an entry no request reaches is a
branch nobody can see.

The route names are read from the arrangement the loop dispatched, by wrapping
`movement.dispatch_step`, rather than by replaying the table on a plan by hand: a
replay would hand `previous_shape` an empty list, and a fill or a comp that read the
held shape would then decline a slot it accepted in the real run.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Sequence, Tuple
from unittest.mock import patch

import arranger.movement as movement
from arranger.decisions import MELODY_ALONE_BASS, MELODY_ALONE_REST
from arranger.grouping import COMMON_TIME
from arranger.options import ArrangeOptions, Request
from arranger.route_dispatch import ROUTES, dispatch_step
from arranger.slot_plan import SlotPlan

PROGRESSION: Sequence[Tuple[str, str, str]] = (
    ("E4", "maj7", "Cmaj7"),
    ("F4", "maj7", "Dm7"),
    ("G4", "7", "G7"),
)

#: One request per entry of the table, with the progression it needs and the entry
#: that must take it. `NC` has its own progression because its answer comes from the
#: chord's own name; the last two share the comping route's request and differ only
#: in where the chord attacks, which is why they are two rows and one entry.
CASES: Sequence[Tuple[str, Sequence[Tuple[str, str, str]], Dict[str, Any], Tuple[str, ...]]] = (
    # the shipped arrangement: the guitar sings under every written note
    ("shipped", PROGRESSION, {}, ("melody_bearing",)),
    # the guitar comps while somebody else sings
    ("comped", PROGRESSION, {"parts": "chord"}, ("comping",)),
    # the guitar plays the tune and nothing else
    ("melody-only", PROGRESSION, {"parts": "melody"}, ("texture_fill",)),
    # an `NC` bar, after a chord: melody and no harmony to voice
    (
        "nc",
        (("E4", "maj7", "Cmaj7"), ("E4", "NC", "NC")),
        {},
        ("melody_bearing", "no_chord"),
    ),
    # one chord position in the bar: every other slot is a rest that says so
    (
        "rested",
        PROGRESSION,
        {"request": Request(melody=False, chord_on="1")},
        ("no_upper_voices",),
    ),
    # the thumb alone: the chord part was asked for nothing, the bass for every beat
    (
        "thumb-only",
        PROGRESSION,
        {"request": Request(melody=False, chord_on="none", bass_on="every-beat")},
        ("no_upper_voices",),
    ),
)



class TestTheDispatchTable(unittest.TestCase):
    """The order is the contract, and every entry in it is reachable."""

    def _dispatch(
        self,
        progression: Sequence[Tuple[str, str, str]] = PROGRESSION,
        **kwargs: Any,
    ) -> List[Tuple[str, SlotPlan]]:
        """Every slot's `(route name, plan)`, as the loop dispatched it.

        The wrapper also asserts the property the table exists to give: a slot
        leaves the dispatcher with **exactly one** step, whichever entry took it.
        """
        seen: List[Tuple[str, SlotPlan]] = []
        real_dispatch = dispatch_step

        def recording(arrangements: List[Any], slot: Any, plan: SlotPlan) -> str:
            before = len(arrangements)
            name = real_dispatch(arrangements, slot, plan)
            self.assertEqual(
                len(arrangements),
                before + 1,
                f"the {name} route emitted more than one step for one slot",
            )
            seen.append((name, plan))
            return name

        with patch.object(movement, "dispatch_step", recording):
            movement.arrange_progression(
                progression,
                time_signature=COMMON_TIME,
                options=ArrangeOptions(**kwargs),
            )
        return seen

    def test_the_order_is_the_contract(self):
        """The sequence, and what each position in it is load-bearing for.

        `no_upper_voices` first, so the thumb's own slot is never read as a chord
        position; `texture_fill` before `melody_bearing`, so a fill is never voiced
        as a chord; `no_chord` before `comping`, so an `NC` bar is never
        reharmonised; and `melody_bearing` last, because it claims every slot still
        standing.
        """
        self.assertEqual(
            [route.name for route in ROUTES],
            [
                "no_upper_voices",
                "texture_fill",
                "no_chord",
                "comping",
                "melody_bearing",
            ],
        )

    def test_the_last_entry_claims_every_slot(self):
        """Which is what makes exactly one step per slot structural, not a check.

        A route that claims a slot may still decline it; the last one may not, so
        `dispatch_step` cannot fall off the end however the earlier claims answer.
        """
        plans = [
            plan
            for _, progression, kwargs, _ in CASES[:2]
            for _, plan in self._dispatch(progression, **kwargs)
        ]
        self.assertTrue(plans)
        for plan in plans:
            self.assertTrue(ROUTES[-1].claims(plan))

    def test_each_request_is_taken_by_the_entry_it_names(self):
        """The table is only worth having if a request lands where the table says.

        This is the half that fails when an entry is *deleted* or a claim is
        broadened: the slot then arrives at the wrong route, and the substitution is
        visible here rather than only in the tab it changes.
        """
        for label, progression, kwargs, expected in CASES:
            with self.subTest(case=label):
                names = {name for name, _ in self._dispatch(progression, **kwargs)}
                self.assertEqual(names, set(expected))

    def test_every_route_fires_on_a_request_a_caller_can_make(self):
        """An entry no request reaches is a branch nobody can see.

        The expectation is read off `ROUTES`, so this fails in the direction the
        test above cannot see: an entry **added** to the table that nothing fires.
        """
        seen = {name for _, _, _, expected in CASES for name in expected}
        self.assertEqual(sorted(seen), sorted(route.name for route in ROUTES))

    def test_the_first_entry_answers_both_the_note_and_the_rest(self):
        """Two answers, one entry: the thumb's own note, or a rest that says why.

        They are one entry because nothing above the thumb sounds in either case -
        the note is the bass line's claim on the slot, and the rest is the grid's -
        so a test that only saw one of them would leave half the entry unmeasured.
        """
        thumb = self._dispatch(**CASES[5][2])
        rested = self._dispatch(**CASES[4][2])
        self.assertEqual({plan.melody_alone for _, plan in thumb}, {MELODY_ALONE_BASS})
        self.assertEqual({plan.melody_alone for _, plan in rested}, {MELODY_ALONE_REST})
