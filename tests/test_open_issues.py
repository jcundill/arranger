"""The behaviour `docs/open-issues.md`'s items describe, asserted against the tree.

The items are *behaviour claims* first and figures second: a `bass:` grid row that changes no
note, a position the default grid generates under a held note, an `NC` bar that keeps its place
in the comping part, a release instant that counts as a hold. Those hold whether or not the
prose around them is up to date, so they live here and the gate runs them.

What is **not** here any more is the other half - re-measuring the numbers the document states
and comparing them with the sentences. That was this module's original job, and it is a
different kind of check: the figures belong to the document, and the recipes beside each item
are how they are re-taken. Deleting the comparison is what makes the figures the document's own
business; `tests/test_docs.py` still fails on a stale version, module count, link or fence.
"""

from __future__ import annotations

import glob
import unittest
from pathlib import Path
from typing import Any, List, Tuple

import headxml
from arranger import (
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_LENGTH,
    HARMONY_SHELL_ROOT,
    VoiceLeadingEngine,
)
from tests.support import arranged, sweep_head_paths

ROOT = Path(__file__).resolve().parent.parent

#: Every committed head. `sweep_head_paths()` is the narrower list a *rule* sweep uses; this
#: module's one head-scoped fact (`tenor_madness`'s release instant) names its head directly.
HEADS: List[str] = (
    sorted(glob.glob(str(ROOT / "tests" / "data" / "*.musicxml")))
    + sorted(glob.glob(str(ROOT / "tests" / "data" / "*.mxl")))
)

#: Item 3's progression, spelled as the document says it was measured on, arranged through
#: `parts="chord"` - the comping route, which is the one that reads `harmony=`.
ITEM_THREE_PROGRESSION: List[Tuple[str, str, str]] = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
]


def _generated_but_silent() -> List[Tuple[str, int, float]]:
    """Positions the default grid generates that the arrangement does **not** sound.

    A position the grid names that is not a written note, and not one the tune is still
    **holding** (§9.2 - the note was harmonised where it began), has to be a step. `[]` is the
    assertion, which is why this returns the offenders rather than a count: a count would have
    to be re-pinned by whoever broke it.

    Swept over `sweep_head_paths()` rather than the whole corpus: it is a rule about the union,
    and an empty complement is not more empty for having eight heads.
    """
    missing: List[Tuple[str, int, float]] = []
    for path in sweep_head_paths():
        head = headxml.load_musicxml(path, None)
        written = {
            (bar, round(beat, 6))
            for _triple, bar, beat, _dur in headxml.head_skeleton(head, None)
        }
        sounded = {
            (step.bar or 0, round(step.beat or 0.0, 6))
            for step in arranged(path)[0]
        }
        for slot in headxml.chord_slots(head, None, "chord:every_note"):
            bar, beat = slot[3], slot[4]
            key = (bar, round(beat, 6))
            if key in written or key in sounded:
                continue
            if headxml.melody_state(head.notes, bar, beat) != "silent":
                continue
            missing.append((Path(path).stem, bar, beat))
    return missing


class TestTheGeneratedSlotsRemainder(unittest.TestCase):
    """Item 1's default-grid half, **closed** - the two refusals, asserted bar by bar.

    The split is §9.2's: a position a note still *holds* must not become a slot, so only the
    positions the tune is genuinely silent at are ones generating would add - and every one of
    those must be a sounded step rather than a position the grid names and nothing plays. The
    measurements that sized the change are the document's own business; the rule is here, and
    `_generated_but_silent` is what checks it.
    """

    #: The head the worked bars below are read from: its bar 16 enters on beat 2, so its
    #: downbeat is the "skipped inside a bar the tune occupies" case in one bar.
    PATH = "tests/data/All_the_Things_You_Are.musicxml"

    @classmethod
    def setUpClass(cls) -> None:
        cls.head = headxml.load_musicxml(cls.PATH, None)

    def _bar(self, grid: str, parts: str, bar: int) -> List[Any]:
        """One bar of an arrangement, keyed by the grid row and the parts selection.

        `grid` is a row spelling, and `parts` is the selection - `auto` for a head whose
        tune the guitar takes, `chord` for the melody-less route another instrument plays.
        `tests.support.arranged` remembers the arrangement, so the four bars below are one
        arrangement each rather than one per assertion.
        """
        steps, _head, _notes = arranged(self.PATH, grid=grid, parts=parts)
        return [step for step in steps if step.bar == bar]

    def test_a_named_grid_already_generates_inside_a_melody_bar(self) -> None:
        """`joe_pass` sounds the beats the tune skips — so the old claim could not stand.

        Bar 3's onsets are exactly 1, 2, 3, 4: every written note sits on the beat, which
        is the case the stale prose said was silent. It yields 8 steps under `joe_pass` on
        both routes, and bar 4's skipped beats 1.5, 2.5 and 3.5 sound too.
        """
        for parts in ("auto", "chord"):
            bar3 = self._bar("chord:joe_pass", parts, 3)
            self.assertEqual(len(bar3), 8, [(s.beat, s.silence) for s in bar3])
        bar4 = self._bar("chord:joe_pass", "auto", 4)
        sounded = {round(s.beat, 2) for s in bar4}
        self.assertEqual(len(bar4), 7)
        for skipped in (1.5, 2.5, 3.5):
            self.assertIn(skipped, sounded)
        # None of them is a written onset, which is the whole of the claim.
        written = {round(n.beat, 2) for n in self.head.notes if n.bar == 4}
        self.assertTrue({1.5, 2.5, 3.5}.isdisjoint(written), written)

    def test_the_default_grid_sounds_a_beat_the_tune_skips_in_a_bar_it_enters(self) -> None:
        """Bar 16 enters on beat 2, so its downbeat was silent — and is now a step.

        This is the closure in one bar of the fixture the rest of this class uses: the tune
        occupies bar 16 (onsets 2, 3 and 4) and skips beat 1, which the old bar-level
        exception excluded along with the rest of the bar and the union now fills.
        """
        self.assertEqual(
            sorted(n.beat for n in self.head.notes if n.bar == 16), [2.0, 3.0, 4.0]
        )
        bar16 = self._bar("chord:every_note", "auto", 16)
        self.assertEqual(sorted(round(s.beat, 2) for s in bar16), [1.0, 2.0, 3.0, 4.0])
        downbeat = next(s for s in bar16 if round(s.beat, 2) == 1.0)
        self.assertIsNone(downbeat.melody, "the tune is silent on beat 1 of bar 16")
        self.assertTrue(downbeat.voicing.active_frets(), downbeat.tab_line())

    def test_a_position_the_tune_is_holding_is_still_not_a_slot(self) -> None:
        """Bar 4's beat 3 is a held `C5`, so it stays absent — §9.2, not the old exception.

        The two refusals are different claims and this is the second one: the tune *does*
        occupy bar 4, and beat 3 is inside the note that began on beat 2. Re-stating a chord
        under it would re-decide a harmony already chosen under that very note.
        """
        bar4 = self._bar("chord:every_note", "auto", 4)
        self.assertEqual(sorted(round(s.beat, 2) for s in bar4), [1.0, 2.0, 4.0])
        self.assertEqual(headxml.melody_state(self.head.notes, 4, 3.0), "held")

    def test_a_position_the_grid_names_is_always_a_sounded_step(self) -> None:
        """The closure itself: no position is generated-but-unsilent anywhere in the sweep.

        The complement of the two refusals, and the claim item 1 was filed about - a slot the
        grid names and nothing plays, so the tab is short of the chord the reader was promised.
        Asserted as `[]` over the same four heads the sweep uses rather than a count, because a
        count would have to be re-pinned by whoever broke it.
        """
        self.assertEqual(_generated_but_silent(), [])


class TestTheHarmonyFullNoOp(unittest.TestCase):
    """Item 3: `harmony=full` on the comping route is accepted and answered with guide tones.

    The claim is an **equality** - the arrangement with `harmony=full` is byte-identical to the
    one with no `harmony=` at all - so it is measured as one, on the progression the document
    named and through the selection a caller actually types. When this starts failing, `full`
    has been given an implementation on the comping route and the item is ready to be removed.
    """

    def _tabs(self, **kwargs: Any) -> Tuple[str, ...]:
        """Every step's tab line, which is how "byte-identical" is spelled here."""
        steps = VoiceLeadingEngine.arrange_progression(ITEM_THREE_PROGRESSION, **kwargs)
        return tuple(step.tab_line() for step in steps)

    def test_full_is_the_default_arrangement_on_the_comping_route(self) -> None:
        """`parts=chord` is the route that reads `harmony=`, and `full` changes nothing on it."""
        default = self._tabs(parts="chord")
        self.assertTrue(default)
        self.assertEqual(self._tabs(parts="chord", harmony=HARMONY_FULL), default)
        # `guide` is what the route ships, so the three spellings are one arrangement.
        self.assertEqual(self._tabs(parts="chord", harmony=HARMONY_GUIDE), default)
        # And the table the vocabulary is read from lists the two families the route implements,
        # not `full`: the axis is a vocabulary, and an accepted spelling with no entry is a
        # no-op rather than a missing feature.
        self.assertEqual(set(HARMONY_LENGTH), {HARMONY_GUIDE, HARMONY_SHELL_ROOT})


class TestTheReleaseInstantRemainder(unittest.TestCase):
    """Item 6: §9.2's hold rule is inclusive at its edge, so a release is not a position.

    A structural fact about one head, read directly: `tenor_madness` bar 1 writes two quarter
    notes, and the instant the second ends reports `held` rather than `silent`, which is what
    §9.2 then declines. The figure that sizes the problem is the document's own business.
    """

    #: `tenor_madness` bar 1: quarters on beats 1 and 2, so beat 3 is the second one's own end.
    BAR = 1
    ONSET = 2.0
    RELEASE = 3.0

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = next(p for p in HEADS if p.endswith("tenor_madness.musicxml"))
        cls.head = headxml.load_musicxml(cls.path, None)

    def test_the_fixture_ends_a_note_exactly_on_the_release_beat(self) -> None:
        """What the item says the bar is, before anything is concluded from it."""
        notes = [(n.beat, round(n.duration * 4, 6)) for n in self.head.notes if n.bar == self.BAR]
        self.assertEqual(notes, [(1.0, 1.0), (self.ONSET, 1.0)])

    def test_a_release_instant_is_reported_as_a_hold(self) -> None:
        """Nothing sounds at the release, and the answer is `held` anyway — the finding."""
        notes = self.head.notes
        self.assertEqual(headxml.melody_state(notes, self.BAR, self.ONSET), "onset")
        self.assertEqual(headxml.melody_state(notes, self.BAR, self.RELEASE), "held")
        self.assertEqual(headxml.melody_state(notes, self.BAR, 4.0), "silent")
        # The mechanism rather than a second opinion: the note is returned *at* its own end,
        # which is the `position > (found.bar, round(end_beat, 6))` test read from outside.
        self.assertIsNotNone(headxml.melody_at(notes, self.BAR, self.RELEASE))

    def test_the_release_beat_is_a_position_the_default_grid_would_name(self) -> None:
        """And it costs the bar a step: 3 sound where an inclusive lattice names 4."""
        steps, _head, _notes = arranged(self.path)
        # `ArrangementStep.beat` is `Optional` because a step may carry no timing; every step
        # arranged from a head has one, and the filter states that rather than asserting it.
        beats = sorted(
            round(step.beat, 2)
            for step in steps
            if step.bar == self.BAR and step.beat is not None
        )
        self.assertEqual(beats, [1.0, self.ONSET, 4.0])
