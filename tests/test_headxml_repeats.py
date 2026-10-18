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


class _ScoreCase(unittest.TestCase):
    """A synthetic score built from `<measure>` strings, with the editor's metre.

    The committed files are the end-to-end pins; a form with a D.C. and a Coda cannot
    be added to one of them without writing a new score, so the cases below state it.
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


def _sound(**attributes: str) -> str:
    """One `<direction>` carrying a `<sound>`: the semantic spelling of a sign.

    A keyword's underscores become hyphens, so `dacapo="yes"` and
    `tocoda="coda"` are the same attributes the format uses.
    """
    pairs = " ".join(
        f'{key.replace("_", "-")}="{value}"' for key, value in attributes.items()
    )
    return f"<direction><sound {pairs}/></direction>"


class TestRepeats(_ScoreCase):
    """A score's repeats and volta endings: the head plays what a performer plays.

    Before this the loader read every `<measure>` once in document order, so a backward
    repeat was ignored and both endings were played. The tests below are the synthetic
    cases (a real file cannot be edited to add one) plus the committed score, whose play
    order and bar count are the end-to-end pin.
    """

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

    def test_the_committed_repeat_head_plays_its_repeat(self):
        """The end-to-end case: 8 written bars, the 1st ending skipped on the repeat.

        The repeat head is 1-4, then ending 1 (5-6) with the backward repeat, then
        ending 2 (7-8). Played, that is `1-4, 5-6, 1-4, 7-8` - 12 bars - and the
        melody note count rises from 15 written to 26 played.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.bars, (1, 13))
        self.assertEqual(len(head.notes), 26)
        # The 1st ending is written bars 5-6, but bar 6 has no note of its own: its
        # G4 is the tie-stop of bar 5's held note, so the ending contributes one written
        # bar of melody. The 2nd ending (written 7-8) is a two-bar tie chain and
        # likewise contributes one, at absolute bars 11-12.
        self.assertEqual(
            sorted({n.written_bar for n in head.notes if n.bar in (5, 6)}), [5]
        )
        self.assertEqual(
            sorted({n.written_bar for n in head.notes if n.bar in (11, 12)}),
            [7],
        )
        # And the repeat's own written bar - 6 - is never a melody bar at all.
        self.assertEqual([n.bar for n in head.notes if n.written_bar == 6], [])

    def test_the_play_order_maps_back_to_the_written_bars(self):
        """`Head.written_bars` is the inverse the writers need to write a written score.

        The arrangement is the 12 bars a player plays; a notation file holds the 8 the
        score writes, with the repeat signposted. `_as_written` is the fold between them,
        and it moves the markers onto the written bars at the same time.
        """
        from arranger.cli import _as_written

        steps, head, _ = arranged(RAINY_DAY)
        self.assertEqual(head.bars, (1, 13))
        written_steps, written_markers = _as_written(
            steps, head.markers, head.written_bars
        )
        # **A bar is covered, not merely started.** The play order's last bar - written
        # bar 8 - has no step *starting* in it: the F4 at absolute bar 11 is held for
        # four beats and runs through it. The notation writer splits that step at the
        # bar line, so the written bar exists even though no step begins there; asking
        # for the set of start bars would report a missing bar the document has.
        covered = set()
        for step in steps:
            if step.bar is None or step.beat is None:
                continue
            end = step.beat + (step.duration or 0.0) * head.beat_type
            last = step.bar + int((end - 1.0 - 1e-9) // head.beats_per_bar)
            for absolute in range(step.bar, last + 1):
                written = head.written_bars.get(absolute)
                if written is not None:
                    covered.add(written)
        self.assertEqual(sorted(covered), list(range(1, 9)))
        self.assertTrue(
            all(step.bar in range(1, 9) for step in written_steps if step.bar is not None)
        )
        self.assertEqual(
            [(m.bar, m.kind) for m in written_markers],
            [
                (1, "repeat_start"),
                (5, "ending_start"),
                (6, "ending_stop"),
                (6, "repeat_end"),
                (7, "ending_start"),
                (8, "ending_stop"),
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


class TestJumps(_ScoreCase):
    """D.C. / D.S. / Coda / Fine: the form, and the four decisions it turns on.

    A jump is a second traversal of bars the head already holds, so the expansion is
    the same machinery a repeat uses, with three flags: a jump fires once, a Fine or
    To Coda is a destination only after it, and a repeat is not re-taken on the way
    back. Each case below pins one of those, because each of them is a way the tab can
    look plausible while being wrong.
    """

    def written(self, head: Head):
        """The written measure of every played note, in play order."""
        return [note.written_bar for note in head.notes]

    def test_dc_al_fine_stops_at_the_fine_on_the_return(self):
        """The Fine is passed on the way out and taken on the way back - 9 bars."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4") + _bar(3, "E4")
            + _bar(4, "F4", _sound(fine="yes"))
            + _bar(5, "G4", _sound(dacapo="yes"))
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3, 4, 5, 1, 2, 3, 4])
        self.assertEqual(head.bars, (1, 10))
        self.assertEqual(
            [(m.bar, m.kind) for m in head.markers if m.kind.startswith("da_")],
            [(5, "da_capo_al_fine")],
        )

    def test_dc_al_coda_takes_the_to_coda_only_after_the_jump(self):
        """On the first pass the To Coda is passed; on the return it is the detour."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(3, "E4", _sound(tocoda="coda"))
            + _bar(4, "F4")
            + _bar(5, "G4", _sound(dacapo="yes"))
            + _bar(6, "A4", _sound(coda="coda")) + _bar(7, "B4")
        )
        head = self.load(measures)
        self.assertEqual(
            self.written(head), [1, 2, 3, 4, 5, 1, 2, 3, 6, 7]
        )
        self.assertEqual(
            [(m.bar, m.kind) for m in head.markers if m.kind == "da_capo_al_coda"],
            [(5, "da_capo_al_coda")],
        )

    def test_ds_al_coda_returns_from_the_segno_not_the_start(self):
        """A D.S. jumps to the Segno, so the bars before it are not replayed."""
        measures = (
            _bar(1, "C4")
            + _bar(2, "D4", _sound(segno="segno"))
            + _bar(3, "E4", _sound(tocoda="coda"))
            + _bar(4, "F4")
            + _bar(5, "G4", _sound(dalsegno="segno"))
            + _bar(6, "A4", _sound(coda="coda"))
            + _bar(7, "B4")
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3, 4, 5, 2, 3, 6, 7])
        marks = sorted((m.bar, m.kind) for m in head.markers)
        self.assertIn((2, "segno"), marks)
        self.assertIn((8, "coda"), marks)

    def test_a_fine_with_no_jump_ends_the_head(self):
        """A lone Fine is the end of the piece, not a decoration to play through."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(3, "E4", _sound(fine="yes")) + _bar(4, "F4")
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3])

    def test_a_to_coda_with_no_jump_is_inert(self):
        """Nothing returns, so the To Coda never fires and the head is all played."""
        measures = (
            _bar(1, "C4")
            + _bar(2, "D4", _sound(tocoda="coda"))
            + _bar(3, "E4")
            + _bar(4, "F4", _sound(coda="coda"))
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3, 4])
        self.assertEqual(head.written_bars, {})
        self.assertTrue(any("To Coda" in note for note in head.report))

    def test_repeats_are_not_retaken_after_a_jump(self):
        """The D.C. pass plays the written section straight through.

        Re-entering the backward repeat on the return would reach the same D.C. again
        and jump forever; the guard exists for that, and this is the form that would
        have reached it.
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(
                3, "E4",
                barline=(
                    '<barline location="right">'
                    '<repeat direction="backward"/></barline>'
                ),
            )
            + _bar(4, "F4", _sound(dacapo="yes"))
            + _bar(5, "G4")
        )
        head = self.load(measures)
        self.assertEqual(
            self.written(head),
            [1, 2, 3, 1, 2, 3, 4, 1, 2, 3, 4, 5],
        )


    def test_the_earlier_destination_names_the_jump(self):
        """With a Fine and a To Coda both on the return, the Fine is reached first.

        The resolved kind must name the destination playback actually reaches: here the
        Fine at 4 ends the return, so the D.C. is "al Fine" even though a To Coda and a
        Coda are drawn later in the score.
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4") + _bar(3, "E4")
            + _bar(4, "F4", _sound(fine="yes"))
            + _bar(5, "G4", _sound(tocoda="coda"))
            + _bar(6, "A4", _sound(coda="coda"))
            + _bar(7, "B4", _sound(dacapo="yes"))
        )
        head = self.load(measures)
        self.assertEqual(
            self.written(head), [1, 2, 3, 4, 5, 6, 7, 1, 2, 3, 4]
        )
        self.assertEqual(
            [(m.bar, m.kind) for m in head.markers if m.kind.startswith("da_")],
            [(7, "da_capo_al_fine")],
        )

    def test_the_written_bars_map_back_over_a_jump(self):
        """`written_bars` is what folds the played head onto the score, coda included."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(3, "E4", _sound(tocoda="coda"))
            + _bar(4, "F4")
            + _bar(5, "G4", _sound(dacapo="yes"))
            + _bar(6, "A4", _sound(coda="coda")) + _bar(7, "B4")
        )
        head = self.load(measures)
        self.assertEqual(
            head.written_bars,
            {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 1, 7: 2, 8: 3, 9: 6, 10: 7},
        )

    def test_a_ds_naming_no_segno_is_reported_not_guessed(self):
        """A malformed jump plays the head linearly and says so."""
        measures = (
            _bar(1, "C4")
            + _bar(2, "D4", _sound(dalsegno="segno"))
            + _bar(3, "E4")
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3])
        self.assertTrue(any("Segno" in note for note in head.report))

    def test_named_segno_and_coda_pair_by_name(self):
        """Two Segnos are two destinations, and a D.S. takes the one it names."""
        measures = (
            _bar(1, "C4", _sound(segno="first"))
            + _bar(2, "D4", _sound(segno="second"))
            + _bar(3, "E4")
            + _bar(4, "F4", _sound(dalsegno="second"))
            + _bar(5, "G4")
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3, 4, 2, 3, 4, 5])

    def test_a_forward_repeat_stated_on_sound_is_read(self):
        """`<sound forward-repeat="yes">` is the same fact as a forward `<repeat>`."""
        measures = (
            _bar(1, "C4", _sound(forward_repeat="yes"))
            + _bar(
                2, "D4",
                barline=(
                    '<barline location="right">'
                    '<repeat direction="backward"/></barline>'
                ),
            )
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 1, 2])

    def test_a_lone_segno_is_still_a_sign_to_draw(self):
        """An unreferenced destination moves no bar but is recorded on its own bar."""
        measures = _bar(1, "C4", _sound(segno="segno")) + _bar(2, "D4")
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2])
        self.assertEqual(head.written_bars, {})
        self.assertEqual(
            [(m.bar, m.kind, m.name) for m in head.markers],
            [(1, "segno", "segno")],
        )

    def test_a_segno_glyph_with_no_sound_is_a_destination(self):
        """The visual sign is read when the file states no `<sound>` with it."""
        measures = (
            _bar(1, "C4")
            + _bar(
                2, "D4",
                "<direction><direction-type><segno/></direction-type></direction>",
            )
        )
        head = self.load(measures)
        self.assertEqual(
            [(m.bar, m.kind) for m in head.markers if m.kind == "segno"],
            [(2, "segno")],
        )

    def test_words_alone_are_not_a_jump(self):
        """`<words>` is prose, not the semantic channel; it is deliberately not read.

        Reading it would need a natural-language parser for every exporter's spelling
        of the same instruction. The limitation is stated in `docs/renderers.md`.
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(
                3, "E4",
                "<direction><direction-type><words>D.C. al Fine</words>"
                "</direction-type></direction>",
            )
        )
        head = self.load(measures)
        self.assertEqual(self.written(head), [1, 2, 3])
        self.assertEqual(head.markers, [])


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

    def test_navigation_signs_are_labelled_above_the_staff(self):
        """A Segno and a D.S. ride the same label row as a volta number.

        The label is the short form (`D.S.`, not `D.S. al Coda`) because the row's
        width is shared by every column of the system; the destination the jump ends
        at is labelled on its own bar, which is how a lead sheet writes it.
        """
        from headxml import BarMarker

        markers = [
            BarMarker(bar=1, kind="segno", written_bar=1, name="segno"),
            BarMarker(bar=2, kind="to_coda", written_bar=2, name="coda"),
            BarMarker(bar=2, kind="da_segno_al_coda", written_bar=2),
        ]
        text = format_tab_staff(
            self._arrangement(), measures_per_line=2, markers=markers
        )
        self.assertIn("Segno", text)
        self.assertIn("To Coda", text)
        self.assertIn("D.S.", text)
