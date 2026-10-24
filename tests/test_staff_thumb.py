"""A held column with a **new thumb** is not an empty column.

`tabstaff._collapse_holds` compares the *upper* voices, and has to: a walking bass moves
the lowest pitch on every beat, so including it would mark every column a strike and
turn the arrangement back into the chord list. The cost of that choice is that a column
whose shape is held and whose thumb moves was drawn as a hold - and a hold draws
nothing - so the new bass note vanished from the ASCII staff and from the HTML while the
one-line tab and the MusicXML both had it.

The tests below record that asymmetry rather than assuming it: they assert the note is
in the other two renderers **and** in the staff, so the staff is what was the outlier.
The last class pins the other half of the same comparison - a *carried* thumb
(`ArrangementStep.bass_held`) has not moved, so it is not drawn twice.
"""

import unittest

from arranger import Request
from arranger.render import format_progression
from headxml import arrange_xml_head
from tabscore import score_events
from tabstaff import (
    _moved_thumb,
    _staff_columns,
    format_tab_html,
    format_tab_staff,
)
from tabxml import format_musicxml
from tests.support import COMMON_8, make_step


def _cut_time_case():
    """The committed case: bar 7 of `synthetic_common_8`, held shape, moving thumb.

    Measured over every committed head and three requests; two steps in the corpus are
    this shape, and this is the one whose thumb is unambiguous on the row it is drawn
    on. The plan guessed the cut-time head's bar 3 beat 1; the real cases are bars 2, 4
    and 8 beat 1.5 there, with `--chord-on 1,1and --bass-on 1and`.

    **The thumb lands on the A string at fret 7, under a melody held on the high E.**
    The comp line moves the upper shape between positions, so a column that is a *hold*
    is now one where the tune itself is held and only the thumb moved - which is
    exactly the asymmetry the renderers have to agree about.
    """
    steps, head, _notes = arrange_xml_head(
        COMMON_8, section=(7, 8), request=Request(chord_on="1,1and", bass_on="every-beat")
    )
    return steps, head


class TestAHeldColumnDrawsAMovedThumb(unittest.TestCase):
    """The bug, in the one place it was invisible."""

    def test_the_column_really_is_a_hold_with_a_new_thumb(self):
        """The premise: the upper shape is unchanged and the thumb has moved.

        Asserted rather than assumed, because a fix that only fired on a strike column
        would pass every other test here while leaving the report broken.
        """
        steps, head = _cut_time_case()
        columns = _staff_columns(steps, head.beats_per_bar, int(head.beat_type), True)
        holds = [
            (step, columns[index - 1][1])
            for index, (_onset, step, strikes) in enumerate(columns)
            if step is not None and not strikes and index
        ]
        moved = [(step, previous) for step, previous in holds if _moved_thumb(step, previous)]
        self.assertTrue(moved, "no held column in this fixture moves its thumb")
        step, previous = moved[0]
        self.assertEqual(step.voicing.bass_string, 1)
        self.assertEqual(step.voicing.frets[1], 7)

    def test_the_ascii_staff_draws_it(self):
        steps, _head = _cut_time_case()
        staff = format_tab_staff(steps, show_chords=False, show_melody=False)
        a_row = [line for line in staff.splitlines() if line.startswith("A ")][0]
        self.assertEqual(a_row.count("7"), 1, staff)

    def test_the_html_draws_it(self):
        steps, _head = _cut_time_case()
        page = format_tab_html(steps, show_melody=False)
        # The A string's row, with the moved thumb in the column the melody is held in.
        self.assertIn(
            '<td></td><td></td><td class="bass"></td>'
            '<td class="bass">7</td><td class="bass"></td>',
            page,
        )

    def test_the_other_two_renderers_already_had_it(self):
        """The asymmetry: these two never lost the note, which is what made it a bug.

        The one-line tab prints every cell of a strike column, and the score reads the
        *pitches* of the step rather than a column flag - so both had the note while the
        staff did not. Asserting it here is what keeps the staff's fix from being read
        as a change to the arrangement.
        """
        from tabxml import _sounding

        steps, _head = _cut_time_case()
        step = [s for s in steps if s.bar == 7 and s.beat == 3.0][0]
        # The one-line tab prints every cell of a strike column, so the note is there.
        self.assertIn("x-7-x-x-x-5", format_progression(steps).replace(" ", ""))
        # The score never read a column flag at all: it reads the step's **pitches**,
        # and the thumb's is one of them.
        self.assertIn(step.voicing.bass_midi, _sounding(step))
        events, _pickup = score_events(steps, 4, True, 4)
        self.assertIn(step, [event[0] for event in events])
        format_musicxml(steps, beats_per_bar=4, beat_type=4)


class TestACarriedThumbIsNotDrawnAgain(unittest.TestCase):
    """The comparison is by `(midi, string)`, so a ringing note has not moved."""

    def test_the_same_note_compares_equal(self):
        struck = make_step([12, -1, -1, -1, -1, -1], bar=1, beat=1.0)
        struck.voicing.bass_midi = 52
        struck.voicing.bass_string = 0
        carried = make_step([12, -1, -1, -1, -1, -1], bar=1, beat=2.0)
        carried.voicing.bass_midi = 52
        carried.voicing.bass_string = 0
        carried.bass_held = True
        self.assertFalse(_moved_thumb(carried, struck))

    def test_a_new_octave_is_a_new_note(self):
        struck = make_step([12, -1, -1, -1, -1, -1], bar=1, beat=1.0)
        struck.voicing.bass_midi = 52
        struck.voicing.bass_string = 0
        moved = make_step([-1, 3, -1, -1, -1, -1], bar=1, beat=2.0)
        moved.voicing.bass_midi = 40
        moved.voicing.bass_string = 1
        self.assertTrue(_moved_thumb(moved, struck))

    def test_no_thumb_at_all_is_not_moved(self):
        struck = make_step([12, -1, -1, -1, -1, -1], bar=1, beat=1.0)
        struck.voicing.bass_midi = 52
        struck.voicing.bass_string = 0
        shaped = make_step([-1, -1, 9, 9, 8, -1], bar=1, beat=2.0)
        self.assertFalse(_moved_thumb(shaped, struck))


if __name__ == "__main__":
    unittest.main()
