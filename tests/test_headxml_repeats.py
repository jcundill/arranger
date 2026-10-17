"""An imported head's repeats: how long it is, and the signs the writers draw.

The importer expands a written head into the order it is played, so a file's measure
count and its step count differ wherever there are repeats or volta endings. That is
`_expand_play_order`'s business here, and each writer's `markers=` parameter is what
puts the `|:` / `:|` / `1.` / `2.` back on the page.
"""

import os
import unittest

import arranger
from headxml import (
    Head,
    load_musicxml,
)
from tabstaff import format_tab_staff
from tests.support import (
    BUT_NOT_FOR_ME,
    RAINY_DAY,
    arranged,
    write_score,
)


def _bar(number: int, pitch: str, inner: str = "", barline: str = "") -> str:
    """One whole-note measure with an optional harmony and barline, for repeat tests.

    `divisions=4` and a 4/4 bar, so a whole note is `duration` 16 and every measure is
    full. The synthetic counterpart to the committed scores: a real file cannot be
    edited to add the ending or the `times` a case needs.
    """
    return (
        f'<measure number="{number}">'
        + barline
        + inner
        + "<note><pitch>"
        + f"<step>{pitch[0]}</step><octave>{pitch[1]}</octave>"
        + "</pitch><duration>16</duration><type>whole</type></note>"
        + "</measure>"
    )


class TestRepeats(unittest.TestCase):
    """A score's repeats and volta endings: the head plays what a performer plays.

    Before this the loader read every `<measure>` once in document order, so a backward
    repeat was ignored and both endings were played. The tests below are the synthetic
    cases (a real file cannot be edited to add one) plus the committed score, whose play
    order and bar count are the end-to-end pin.
    """

    def load(self, measures: str, beats: int = 4, beat_type: int = 4) -> Head:
        # The divisions and metre go in the **first** measure rather than a synthetic
        # bar 0: an extra measure would be a bar of the play order with no notes, and the
        # absolute numbering these tests read is a fact about the play order.
        attributes = (
            f"<attributes><divisions>4</divisions>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
            "</attributes>"
        )
        opening = measures.find(">") + 1
        measures = measures[:opening] + attributes + measures[opening:]
        document = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<score-partwise version="3.1">\n'
            "  <part-list><score-part id=\"P1\"><part-name>Voice</part-name>"
            "</score-part></part-list>\n"
            '  <part id="P1">\n'
            f"{measures}\n"
            "  </part>\n</score-partwise>\n"
        )
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    def test_a_backward_repeat_plays_the_section_twice(self):
        """Four written bars with a backward repeat at the last play as eight.

        The simplest expansion, and the one the count speaks for: `bar` is renumbered to
        the absolute play order (1-8) and `written_bar` keeps the score's own (1-4, twice).
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4") + _bar(3, "E4")
            + _bar(4, "F4", barline='<barline location="right">'
                                 '<repeat direction="backward"/></barline>')
        )
        head = self.load(measures)
        self.assertEqual(head.bars, (1, 9), "4 written bars played twice is 8 bars")
        self.assertEqual([n.bar for n in head.notes], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(
            [n.written_bar for n in head.notes], [1, 2, 3, 4, 1, 2, 3, 4]
        )


    def test_the_second_ending_replaces_the_first_on_the_repeat(self):
        """The 1st/2nd ending taken in turn: play the 1st, repeat, skip it, play the 2nd.

        Bars 1-2 are the body, bar 3 the 1st ending (which carries the backward repeat),
        bar 4 the 2nd. A player hears `1 2 3 | 1 2 4` - six bars, and `written_bar` shows
        exactly which pass each one came from.
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(
                3, "E4",
                barline=(
                    '<barline location="left"><ending number="1" type="start"/></barline>'
                    '<barline location="right"><ending number="1" type="stop"/>'
                    '<repeat direction="backward"/></barline>'
                ),
            )
            + _bar(
                4, "F4",
                barline=(
                    '<barline location="left"><ending number="2" type="start"/></barline>'
                    '<barline location="right"><ending number="2" type="stop"/></barline>'
                ),
            )
        )
        head = self.load(measures)
        self.assertEqual([n.written_bar for n in head.notes], [1, 2, 3, 1, 2, 4])
        self.assertEqual([n.bar for n in head.notes], [1, 2, 3, 4, 5, 6])

    def test_times_three_plays_the_section_three_times(self):
        """`times` is honoured rather than assumed to be two."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(3, "E4", barline='<barline location="right">'
                                 '<repeat direction="backward" times="3"/></barline>')
        )
        head = self.load(measures)
        self.assertEqual([n.bar for n in head.notes], [1, 2, 3, 4, 5, 6, 7, 8, 9])

    def test_a_forward_repeat_is_the_jump_back_target(self):
        """An explicit `direction="forward"` replaces the repeat-to-start default."""
        measures = (
            _bar(1, "C4")
            + _bar(2, "D4", barline='<barline location="left">'
                                  '<repeat direction="forward"/></barline>')
            + _bar(3, "E4", barline='<barline location="right">'
                                  '<repeat direction="backward"/></barline>')
        )
        head = self.load(measures)
        # Bar 1 once, then 2-3 twice: 1 2 3 2 3.
        self.assertEqual([n.written_bar for n in head.notes], [1, 2, 3, 2, 3])

    def test_a_head_with_no_repeat_is_untouched(self):
        """No barlines: nothing is renumbered and no markers are recorded.

        The contract that keeps the six non-repeating committed scores loading exactly as
        they did. `written_bar` is always the score's own number - it equals `bar` here
        because no repeat moved anything - and `markers` stays empty.
        """
        head = self.load(_bar(1, "C4") + _bar(2, "D4"))
        self.assertEqual([n.bar for n in head.notes], [1, 2])
        self.assertEqual([n.written_bar for n in head.notes], [1, 2])
        self.assertEqual(head.markers, [])


    def test_the_markers_name_the_repeat_and_both_endings(self):
        """The two-volta structure, on the bar numbers the expanded head landed on."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(
                3, "E4",
                barline=(
                    '<barline location="left"><ending number="1" type="start"/></barline>'
                    '<barline location="right"><ending number="1" type="stop"/>'
                    '<repeat direction="backward"/></barline>'
                ),
            )
            + _bar(
                4, "F4",
                barline=(
                    '<barline location="left"><ending number="2" type="start"/></barline>'
                    '<barline location="right"><ending number="2" type="stop"/></barline>'
                ),
            )
        )
        head = self.load(measures)
        marks = sorted((m.bar, m.kind) for m in head.markers)
        self.assertEqual(
            marks,
            [
                (1, "repeat_start"),
                (3, "ending_start"),
                (3, "ending_stop"),
                (3, "repeat_end"),
                (6, "ending_start"),
                (6, "ending_stop"),
            ],
        )

    def test_the_committed_rainy_day_plays_its_repeat(self):
        """The end-to-end case: 36 written bars, the 1st ending skipped on the repeat.

        `heres_that_rainy_day` is 1-30, then ending 1 (31-32) with the backward repeat,
        then ending 2 (33-36). Played, that is `1-30, 31-32, 1-30, 33-36` - 66 bars - and
        the melody note count rises from 113 written to 160 played.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.bars, (1, 67))
        self.assertEqual(len(head.notes), 160)
        # The 1st ending is written bars 31-32, but bar 32 has no note of its own: its
        # G4 is the tie-stop of bar 31's held note, so the ending contributes one written
        # bar of melody. The 2nd ending (written 33-36) is a four-bar tie chain and
        # likewise contributes one, at absolute bars 63-66.
        self.assertEqual(
            sorted({n.written_bar for n in head.notes if n.bar in (31, 32)}), [31]
        )
        self.assertEqual(
            sorted({n.written_bar for n in head.notes if n.bar in (63, 64, 65, 66)}),
            [33],
        )
        # And the repeat's own written bar - 32 - is never a melody bar at all.
        self.assertEqual([n.bar for n in head.notes if n.written_bar == 32], [])

    def test_the_play_order_maps_back_to_the_written_bars(self):
        """`Head.written_bars` is the inverse the writers need to write a written score.

        The arrangement is the 66 bars a player plays; a notation file holds the 36 the
        score writes, with the repeat signposted. `_as_written` is the fold between them,
        and it moves the markers onto the written bars at the same time.
        """
        from arranger.cli import _as_written

        steps, head, _ = arranged(RAINY_DAY)
        self.assertEqual(head.bars, (1, 67))
        written_steps, written_markers = _as_written(
            steps, head.markers, head.written_bars
        )
        bars = sorted(
            {bar for bar in (step.bar for step in written_steps) if bar is not None}
        )
        self.assertEqual(bars, list(range(1, 37)))
        self.assertEqual(
            [(m.bar, m.kind) for m in written_markers],
            [
                (1, "repeat_start"),
                (31, "ending_start"),
                (32, "ending_stop"),
                (32, "repeat_end"),
                (33, "ending_start"),
                (36, "ending_stop"),
            ],
        )

    def test_a_head_with_no_repeat_projects_to_itself(self):
        """No markers and no map: `_as_written` is the identity on the arrangement."""
        from arranger.cli import _as_written

        steps, head, _ = arranged(BUT_NOT_FOR_ME)
        self.assertEqual(head.markers, [])
        self.assertEqual(head.written_bars, {})
        written_steps, written_markers = _as_written(
            steps, head.markers, head.written_bars
        )
        self.assertEqual([s.bar for s in written_steps], [s.bar for s in steps])
        self.assertEqual(written_markers, [])


class TestRepeatSignsInTheAsciiStaff(unittest.TestCase):
    """The tab staff draws the `|:` / `:|` and the volta numbers the markers name.

    The staff is the display the head CLI prints, so a reader can see the repeat rather
    than only the extra bars it produced. The signs ride the barline of the bar they open
    - `|:` on a repeat's start, `:|` on the bar after its end - and an ending's number is
    a label row (`1.` / `2.`) above the staff.
    """

    def _arrangement(self, count: int = 8):
        engine = arranger.VoiceLeadingEngine()
        progression = [
            ("A4", "m7", "Dm7"), ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7"),
            ("A4", "m7", "Am7"), ("C5", "7", "D7"), ("B4", "maj7", "Fmaj7"),
            ("A4", "m7", "Bm7"), ("C5", "7", "E7"),
        ][:count]
        steps = engine.arrange_progression(progression)
        for index, step in enumerate(steps):
            step.bar = 1 + index // 4
            step.beat = 1.0 + index % 4
            step.duration = 0.25
        return steps

    def test_no_markers_draws_no_repeat_signs(self):
        """The default staff is unchanged - the markers are the only thing that adds signs."""
        text = format_tab_staff(self._arrangement(), measures_per_line=2)
        self.assertNotIn("|:", text)
        self.assertNotIn(":|", text)

    def test_repeat_start_and_end_ride_their_barlines(self):
        from headxml import BarMarker

        markers = [
            BarMarker(bar=1, kind="repeat_start", written_bar=1),
            BarMarker(bar=2, kind="repeat_end", written_bar=2, times=2),
        ]
        text = format_tab_staff(
            self._arrangement(), measures_per_line=2, markers=markers
        )
        self.assertIn("e*|:", text, "the opening barline of bar 1 should be a repeat")
        self.assertIn(":|", text, "bar 2's close should be a repeat")

    def test_a_volta_number_is_labelled_above_the_staff(self):
        from headxml import BarMarker

        markers = [
            BarMarker(bar=1, kind="ending_start", written_bar=1, numbers=(1,)),
            BarMarker(bar=2, kind="ending_stop", written_bar=2, numbers=(1,)),
        ]
        text = format_tab_staff(
            self._arrangement(), measures_per_line=2, markers=markers
        )
        self.assertIn("1.", text)
