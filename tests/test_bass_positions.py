"""The bass at the **positions a request names**, rather than the metre's felt beats.

`--bass-on` is a rhythm: `every-beat` resolves against the metre's grouping, and a
list such as `1,3` is exactly those positions. The line itself is `bass.py`'s
(`test_bass.py` covers its note choices); what is pinned here is that a sparse
rhythm neither invents beats the caller did not name nor leaves a bar unmarked, and
that `root`/`root-5th` state a note at every requested position - which is the one
thing the walk's filtered vocabulary cannot do.

The `bass=` axis is the engine's own spelling and keeps its documented
anchors-only meaning until Stage 8 retires it, so one test holds the two apart.
"""

import unittest

from arranger import (
    BASS_ROLE_ANCHOR,
    BASS_ROLE_FIFTH,
    BASS_ROLE_PEDAL,
    Request,
)
from arranger.bass import bass_line_for
from arranger.options import resolve_request
from tests.support import arranged


def _attacks(step) -> bool:
    """Whether this step *plucks* the thumb, rather than letting it ring on."""
    return step.bass is not None and not step.bass_held

CHORDS = [("C", "maj7", "Cmaj7")]

#: The vocabulary a walking note may carry. A sparse walk still has to choose from
#: these - it may not fall back to a role that only makes sense on the full grid.
WALK_ROLES = {"anchor", "connect", "approach", "enclosure", "hold"}


def line(
    bass_on: str = "every-beat",
    bass_notes: str = "root",
    beats_per_bar: int = 4,
    grouping=None,
    bars=(1,),
    chords=CHORDS,
):
    """The thumb line for one request, over `bars` of a held chord.

    Built through `resolve_request` rather than by calling `bass_line_for` with a
    hand-made style, because the mapping *is* the request: `bass-notes root` means
    the root rule, and `bass-on every-beat` means the metre's felt beats.
    """
    request = Request(chord_on="none", bass_on=bass_on, bass_notes=bass_notes)
    resolved = resolve_request(
        request, beats_per_bar, grouping or (1,) * beats_per_bar
    )
    onsets = [(bar, 1.0) for bar in bars]
    return bass_line_for(
        resolved.bass,
        chords,
        onsets,
        beats_per_bar,
        grouping,
        resolved.bass_rhythm,
    )


class TestEveryBeatIsTheMetre(unittest.TestCase):
    """`every-beat` is as many notes as the bar is felt in, never a constant four."""

    def test_four_four_is_four(self):
        self.assertEqual(
            [note.beat for note in line(beats_per_bar=4)], [1.0, 2.0, 3.0, 4.0]
        )

    def test_two_two_is_two(self):
        """A cut-time bar is two beats wide, so a bar of `every-beat` is two notes."""
        self.assertEqual([note.beat for note in line(beats_per_bar=2)], [1.0, 2.0])

    def test_three_four_is_three(self):
        self.assertEqual([note.beat for note in line(beats_per_bar=3)], [1.0, 2.0, 3.0])

    def test_the_grouping_decides_a_compound_metres_pulses(self):
        """12/8 in four dotted-quarter pulses is four positions, not twelve eighths."""
        notes = line(beats_per_bar=12, grouping=(3, 3, 3, 3))
        self.assertEqual([note.beat for note in notes], [1.0, 4.0, 7.0, 10.0])


class TestSparsePositions(unittest.TestCase):
    """A rhythm names positions; the line may not fill the gaps itself."""

    def test_only_the_requested_positions_sound(self):
        self.assertEqual([note.beat for note in line(bass_on="1,3")], [1.0, 3.0])

    def test_an_offbeat_position_is_the_only_place_it_sounds(self):
        """`1&` is a real position, and the line states one note there per bar."""
        self.assertEqual([note.beat for note in line(bass_on="1&")], [1.5])

    def test_a_rhythm_the_metre_does_not_have_is_still_refused(self):
        """The metre's own refusal survives: `3` is not a position in 2/2.

        This is the one refusal the redesign *keeps*: it is about the bar, not about
        the old "the root only sounds where the harmony anchors" rule Stage 3 removes.
        """
        with self.assertRaises(ValueError) as error:
            line(bass_on="3", beats_per_bar=2)
        self.assertIn("beat 3", str(error.exception))

    def test_the_first_position_of_a_bar_anchors_even_off_the_downbeat(self):
        """`--bass-on 2,4` still needs a root to mark the bar.

        Beat 1 is not a position the caller named, so a `downbeat` test would leave
        the line with no anchor at all - every note connective, and no target for the
        previous bar's approach.
        """
        notes = line(bass_on="2,4")
        self.assertEqual([note.beat for note in notes], [2.0, 4.0])
        self.assertEqual(notes[0].role, BASS_ROLE_ANCHOR)

    def test_a_sparse_walk_states_a_note_at_each_position_and_no_more(self):
        """The walk's own vocabulary, at two positions instead of four."""
        notes = line(bass_on="2,4", bass_notes="walk")
        self.assertEqual([note.beat for note in notes], [2.0, 4.0])
        for note in notes:
            self.assertIn(note.role, WALK_ROLES)

    def test_the_sparse_walk_keeps_its_anchor_per_bar(self):
        """Two bars of two positions have two anchors, one each - not four or none."""
        notes = line(bass_on="1,3", bass_notes="walk", bars=(1, 2))
        anchors = [
            (note.bar, note.beat) for note in notes if note.role == BASS_ROLE_ANCHOR
        ]
        self.assertEqual(anchors, [(1, 1.0), (2, 1.0)])


class TestTheSimpleLines(unittest.TestCase):
    """`root` and `root-5th` state a note at **every** requested position."""

    def test_the_root_sounds_at_every_position(self):
        """The old rule kept the anchor beats only; a rhythm asks for all of them."""
        notes = line(bass_on="every-beat", bass_notes="root")
        self.assertEqual(len(notes), 4)
        self.assertEqual([note.pitch_class for note in notes], [0, 0, 0, 0])
        self.assertEqual(
            [note.role for note in notes],
            [BASS_ROLE_ANCHOR, BASS_ROLE_PEDAL, BASS_ROLE_PEDAL, BASS_ROLE_PEDAL],
        )

    def test_root_fifth_alternates_the_two(self):
        """Root on the bar's mark, the 5th after it, and so on through the bar."""
        notes = line(bass_on="every-beat", bass_notes="root-5th")
        self.assertEqual([note.pitch_class for note in notes], [0, 7, 0, 7])
        self.assertEqual(
            [note.role for note in notes],
            [BASS_ROLE_ANCHOR, BASS_ROLE_FIFTH, BASS_ROLE_PEDAL, BASS_ROLE_FIFTH],
        )

    def test_a_two_feel_states_root_then_fifth(self):
        """`--bass-on 1,3 --bass-notes root-5th` is the classic two-feel."""
        notes = line(bass_on="1,3", bass_notes="root-5th")
        self.assertEqual([note.pitch_class for note in notes], [0, 7])

    def test_the_fifth_is_read_from_the_chord_in_force(self):
        """A 5th is a degree of the chord under it, so a change moves the note."""
        chords = [("C", "maj7", "Cmaj7"), ("F", "maj7", "Fmaj7")]
        notes = line(
            bass_on="every-beat", bass_notes="root-5th", bars=(1, 2), chords=chords
        )
        self.assertEqual(
            [note.pitch_class for note in notes], [0, 7, 0, 7, 5, 0, 5, 0]
        )


class TestTheAxisIsStillTheAxis(unittest.TestCase):
    """The `bass=` spelling keeps its documented meaning until Stage 8 retires it."""

    def test_the_axis_root_is_anchors_only(self):
        """No rhythm named means the felt-beat walk, filtered to the anchors."""
        notes = bass_line_for("root", CHORDS, [(1, 1.0), (2, 1.0)], 4, None, None)
        self.assertEqual(
            [(note.bar, note.beat) for note in notes], [(1, 1.0), (2, 1.0)]
        )

    def test_the_request_root_is_not_that_line(self):
        """The same style with a rhythm states the root at every one of its beats."""
        self.assertEqual(len(line(bass_on="every-beat", bass_notes="root")), 4)


class TestTheStepsCarryTheLine(unittest.TestCase):
    """End to end: a requested position becomes a step, and a bar has one per beat."""

    def test_a_four_four_bar_carries_four_thumb_notes(self):
        from tests.support import COMMON_8

        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            request=Request(chord_on="none", bass_on="every-beat", bass_notes="root"),
        )
        rings = [step for step in steps if step.bass is not None]
        self.assertEqual(len(rings), 4, [step.tab_line() for step in steps])

    def test_a_waltz_bar_carries_three(self):
        from tests.support import WALTZ

        steps, _head, _notes = arranged(
            WALTZ,
            section=(2, 3),
            request=Request(chord_on="none", bass_on="every-beat", bass_notes="root"),
        )
        # Attacks, not notes: the ring carries each one forward, so counting
        # `step.bass` would count the bar rather than the line.
        self.assertEqual(len([step for step in steps if _attacks(step)]), 3)

    def test_a_sparse_position_becomes_a_step_of_its_own(self):
        """The beat the melody merely holds through still gets its thumb note.

        `1&` names one position and no other, so the step carries the melody **in
        force** under a thumb stroke - the union's documented `bass_only` slot. A
        requested position is therefore never dropped for want of a note to attach
        it to, and the downbeat is not given one either.
        """
        from tests.support import COMMON_8

        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            request=Request(chord_on="none", bass_on="1&", bass_notes="root"),
        )
        rings = [(step.bar, step.beat) for step in steps if _attacks(step)]
        self.assertEqual(rings, [(1, 1.5)])


if __name__ == "__main__":
    unittest.main()

