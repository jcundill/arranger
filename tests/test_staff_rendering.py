"""The ASCII tab staff: metres, note values, rhythm rows and barline alignment.

The staff draws the same steps as the compact line at a fixed number of columns per beat,
so these tests are about the arithmetic that puts a note in a column - and about the module
boundary that keeps the renderer out of the engine.
"""

import io
import re
import unittest
from contextlib import redirect_stdout
from typing import List

from arranger import (
    ArrangementStep,
    VoiceLeadingEngine,
    format_tab_html,
    format_tab_staff,
)
from tabstaff import _NOTE_VALUES, _staff_columns, _staff_rhythm
from tests.support import make_voicing


def _timed(chords, beats=None, durations=None, frets=None):
    """Hand-built timed steps, one per chord, for the timing tests.

    Hand-built rather than arranged: these tests are about how a *given* rhythm is
    drawn, and an arrangement would bring the selector's own choices along with it.
    Each chord becomes a step on the beat given, defaulting to one per bar.

    `frets` gives each step its own shape. The default is the same shape for every
    step, which `collapse` then treats as a hold - correct for the tie tests and
    wrong for any test about note values, where two consecutive chords have to be
    two attacks rather than one held note.
    """
    built = []
    for index, chord in enumerate(chords):
        bar = index if beats is None else beats[index][0]
        beat = 1.0 if beats is None else beats[index][1]
        duration = None if durations is None else durations[index]
        voicing = make_voicing(
            [-1, -1, 10, 10, 10, 10] if frets is None else frets[index]
        )
        built.append(
            ArrangementStep(
                chord=chord, melody="D5", voicing=voicing,
                bar=bar, beat=beat, duration=duration,
            )
        )
    return built


#: Two distinct shapes, for a test that needs two consecutive chords to be two
#: attacks rather than one held note. `collapse` compares sounding pitches, so the
#: same voicing twice would print the second as a tie.
_TWO_SHAPES = [[-1, -1, 10, 10, 10, 10], [-1, -1, 9, 9, 8, 8]]


class TestStaffTab(unittest.TestCase):
    """Tests the six-line staff renderer, format_tab_staff()."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # Dm7 -> G7 -> Cmaj7 on the high E block, for the reason `TestFormatProgression`
        # gives: this fixture is a *renderer* subject, so only the string set is fixed.
        self.steps = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
        )

    def staff_lines(self, steps, **kwargs):
        """The six string lines of a staff, with the chord line stripped off."""
        return format_tab_staff(steps, **kwargs).split("\n")[-6:]

    def chord_line(self, steps=None, **kwargs):
        """
        The row of chord names, found by content rather than by position.

        An index would not do: `show_timing` puts the metre and the note values above the
        chord row, so taking the first line would find the metre - and a test that
        silently changed subject would still pass, which is worse than failing. Naming the
        row by what is in it keeps the assertion about the chord names.

        `show_chords` is forced on, since the chord row is off by default with the
        rest of the annotation - the default staff is the tab and nothing else.
        """
        kwargs.setdefault("show_chords", True)
        staff = format_tab_staff(steps if steps is not None else self.steps, **kwargs)
        for row in staff.split("\n"):
            if "Dm7" in row:
                return row
        raise AssertionError(f"no chord row in:\n{staff}")

    def test_staff_has_six_strings_in_reading_order(self):
        """
        The staff is ordered high E (string 1) down to low E (string 6), which is
        how tab is read - the reverse of tab_string()'s low-E-first order.
        """
        lines = self.staff_lines(self.steps)
        self.assertEqual([line[0] for line in lines], ["e", "B", "G", "D", "A", "E"])

    def test_staff_places_frets_on_the_right_strings(self):
        """
        Each voicing's frets appear on the line for their own string, so the staff
        is a faithful picture of the voicing rather than a restatement of tab_string.
        """
        lines = self.staff_lines(self.steps)
        for step, _row in zip(self.steps, lines):
            # Dm7 is x-x-10-10-10-10, so the top four staff lines all carry a 10.
            for string_index in (5, 4, 3, 2):
                self.assertIn(str(step.voicing.frets[string_index]), lines[5 - string_index])

    def test_chord_line_names_every_chord(self):
        """The chord-name line sits above the staff and names each chord once."""
        top = self.chord_line()
        for chord in ("Dm7", "G7", "Cmaj7"):
            self.assertIn(chord, top)

    def test_melody_line_is_off_by_default(self):
        """Melody note names are opt-in, so the default staff is chords only."""
        self.assertNotIn("D5", format_tab_staff(self.steps))
        self.assertIn("D5", format_tab_staff(self.steps, show_melody=True))

    def test_every_staff_line_is_the_same_width(self):
        """
        The six string lines share one column grid, so a fret sits in the same
        column on every string and the shape reads as a shape.
        """
        lines = self.staff_lines(self.steps)
        self.assertEqual({len(line) for line in lines}, {len(lines[0])})

    def test_chord_names_start_at_the_column_of_their_frets(self):
        """
        A chord name is printed at the column where its shape is struck, so the
        label and the frets line up even though the name is wider than a cell.
        """
        top = self.chord_line()
        first_string = format_tab_staff(self.steps, show_chords=True).split("\n")[-6]
        self.assertEqual(top.index("Dm7"), first_string.index("10"))

    def test_the_chord_row_is_off_by_default(self):
        """
        The tab is the six string rows; a chord name is a lead sheet's annotation.

        The counterpart to the chord-row tests above, and the reason they all pass
        `show_chords` explicitly: the default staff carries no chord names at all.
        """
        self.assertNotIn("Dm7", format_tab_staff(self.steps))
        self.assertIn("Dm7", format_tab_staff(self.steps, show_chords=True))

    def test_two_digit_frets_do_not_collide(self):
        """
        A two-digit fret occupies a two-character cell, so consecutive frets are
        still separate numbers rather than running together.
        """
        # Frets 9 and 10 on adjacent strings, the case that collides at width 1.
        wide = make_voicing([-1, -1, 9, 9, 10, 10])
        step = ArrangementStep(chord="Cmaj7", melody="E4", voicing=wide)
        line = self.staff_lines([step])[0]
        self.assertIn("10", line)
        self.assertNotIn("1010", line.replace(" ", "").replace("-", ""))

    def test_barlines_fall_on_bar_changes(self):
        """
        With timing, a barline is drawn where the bar changes: a step in bar 1 is
        followed by one in bar 2, and the barline sits between them.

        **Every bar is ruled**, not every `measures_per_line`th one: the barline is the
        mark that says where the metre falls, and a staff that drew one only every fourth
        bar could not show a two-bar phrase apart from a four-bar one. What is
        load-bearing here is *where* it falls relative to the shape, so that is what the
        test states.
        """
        timed = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("C5", "maj7", "Cmaj7")]
        )
        timed[0].bar, timed[0].beat = 0, 1.0
        timed[1].bar, timed[1].beat = 1, 1.0
        # measures_per_line=4 keeps both bars on one system, which is what puts the
        # barline *between* the two shapes where this test can see it. At one bar
        # per line they are separate systems and there is nothing between them.
        # The three dashed columns between the shapes are the rest of bar 0.
        staff = format_tab_staff(timed, measures_per_line=4)
        self.assertEqual(len(_systems(staff)), 1, staff)
        line = next(row for row in staff.split("\n") if row.startswith("e"))
        # The staff opens with its own '|', so the barline opened by partition is
        # that one; the next '|' is the real barline between bar 0 and bar 1.
        head, _, tail = line.partition("|")
        head, _, tail = tail.partition("|")
        self.assertNotIn("|", head)               # nothing but the staff's own bar
        self.assertIn("10", head)                 # bar 0's shape
        # A barline opens bar 1, and bar 0's three remaining beats are the rests
        # written just before it - so the barline sits after them, not before.
        self.assertTrue(tail.rstrip("-| ").endswith("8"))
        # The three remaining beats of bar 0 are drawn as dashes between the two
        # shapes, so there is a run of them before bar 1's barline. Stated as a run
        # rather than a fixed count because the cell width is per system now.
        self.assertRegex(head, r"10-.*-{3,}")
        self.assertNotIn("10", tail)              # and bar 1 is a fresh shape

    def test_every_bar_is_ruled_not_every_fourth(self):
        """
        Four bars in a row produce four barlines, which is the whole point of the
        change: the metre is legible bar by bar rather than once per line of music.
        """
        steps = _timed(["Dm7", "G7", "Cmaj7", "Fm7"])
        staff = format_tab_staff(steps, measures_per_line=4)
        line = staff.split("\n")[0]
        # One for the staff's own opening, one closing each of the four bars.
        self.assertEqual(line.count("|"), 5, line)

    def test_a_sub_beat_rest_is_drawn(self):
        """
        A silence shorter than a beat gets a column, which it used not to.

        `_staff_columns` advanced by a whole beat and assumed every step was a beat
        long. It is not: `duration` is in whole notes and the default `eighths` skeleton
        puts steps half a beat apart, so every gap shorter than a beat was stepped over.
        Bar 11 of the synthetic cut-time head lost its downbeat column that way, and with it the tie
        into the bar's early beat.

        Two eighth notes a *half* beat apart in 2/2 leave half a beat of silence, and
        that silence has to be on the grid.
        """
        a = ArrangementStep(chord="Dm7", melody="D5", bar=0, beat=1.0, duration=0.125,
                            voicing=make_voicing([-1, -1, 10, 10, 10, 10]))
        b = ArrangementStep(chord="G7", melody="B4", bar=0, beat=1.5, duration=0.125,
                            voicing=make_voicing([-1, -1, 9, 9, 8, 8]))
        onsets = [onset for onset, _step, _strikes
                  in _staff_columns([a, b], 2, 2, True, True)]
        # The rests before the first note are a quarter of a beat apart, which is the
        # grain the progression writes at. Before the fix the grid stepped a whole beat
        # at a time, so a sub-beat gap produced no columns at all and bar 11 of But Not
        # For Me lost its downbeat - and with it the tie into the bar's early beat.
        rests = [o for o in onsets if o < 1.0]
        self.assertGreater(len(rests), 1, onsets)
        self.assertEqual({round(b - a_, 3) for a_, b in zip(rests, rests[1:])}, {0.25})

    def test_a_bar_of_a_quarter_rest_and_three_quarters_is_seventeen_wide(self):
        """
        The measurement the grid is built to reproduce.

        `jon6.tab` bar 1 - a quarter rest and three quarter notes in 2/2 - is seventeen
        characters: one lead-in dash and sixteen of grid, which is eight slots of two
        characters, one slot to the quarter. Getting this exactly right is what
        confirms the whole model - the lead-in, the cell width and the slot count all
        have to land on the same number independently.
        """
        steps = _timed(
            ["Dm7", "G7", "Cmaj7"],
            beats=[(0, 1.5), (0, 2.5), (0, 3.5)],
            durations=[0.25, 0.25, 0.25],
            frets=[[-1, -1, 10, 10, 10, 10], [-1, -1, 7, 7, 6, 6],
                   [-1, -1, 5, 5, 4, 4]],
        )
        bar = format_tab_staff(steps).split("\n")[0].split("|")[1]
        self.assertEqual(len(bar), 17, bar)

    def test_a_pickup_leaves_its_rest_visible(self):
        """
        A head that enters part-way through its first bar shows the rest before it.

        The grid starts at the bar, not at the first *onset*, so a leading rest inside that
        bar is not silently dropped: a pickup otherwise comes out with its first fret hard
        against the opening barline and reads as a downbeat. The synthetic cut-time head bar
        1 is written that
        way - a quarter rest and then three notes - and TuxGuitar's export draws the
        rest as dashes and puts the fret where it falls. The start is now rounded down
        to the bar containing the first onset, which keeps the rest without inventing
        whole empty bars ahead of it.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.5), (0, 2.5)], durations=[0.25, 0.25],
                       frets=[[-1, -1, 10, 10, 10, 10]] * 2)
        bar = format_tab_staff(steps).split("\n")[0].split("|")[1]
        # The lead-in is one dash plus the half beat of rest before the note, which is
        # one slot of two characters. The fret is *not* at the head of the bar, which is
        # the whole point: a pickup that starts on the barline reads as a downbeat.
        self.assertRegex(bar, r"^-{3,}10", bar)
        self.assertGreater(bar.index("10"), 1, bar)

    def test_only_the_first_bar_is_padded_with_its_leading_rest(self):
        """
        The rounding is to the *bar*, not to the whole progression: a head selected
        from bar 12 is still not preceded by twelve empty bars.
        """
        steps = _timed(["Dm7", "G7"], beats=[(12, 1.5), (12, 2.5)],
                       durations=[0.25, 0.25],
                       frets=[[-1, -1, 10, 10, 10, 10]] * 2)
        staff = format_tab_staff(steps)
        self.assertEqual(len(_systems(staff)), 1, staff)
        bar = staff.split("\n")[0].split("|")[1]
        self.assertRegex(bar, r"^-{3,}10", bar)

    def test_a_longer_note_is_drawn_wider(self):
        """
        Duration is drawn as horizontal space, which is how ASCII tab says it.

        **A column is as wide as the note is worth**, so a quarter and a half note do not
        come out identical: a note occupies as many *slots* as it is worth, one slot being
        one fret cell, so a half note is drawn twice as wide as a quarter. That is what
        makes the tab say how long anything sounds.

        `duration` is in **whole notes**, and reading it as beats is what made every
        note in the piece come out one slot wide. At the floor of eight slots to the
        whole note, a quarter is two slots and a half note four - so `quarter, half`
        is six slots, one of each being the fret itself.
        """
        steps = _timed(
            ["Dm7", "G7", "C7", "F7"],
            beats=[(0, 1.0), (0, 2.0), (1, 1.0), (1, 2.0)],
            # 0.25 whole notes is a quarter, 0.5 a half. **Whole notes, not beats.**
            durations=[0.25, 0.5, 0.25, 0.5],
            frets=[[-1, -1, 10, 10, 10, 10], [-1, -1, 7, 7, 6, 6],
                   [-1, -1, 5, 5, 4, 4], [-1, -1, 3, 3, 2, 2]],
        )
        staff = format_tab_staff(steps)
        # The low E row is struck on nothing, so its bar is the pure grid. The first
        # bar's music stops after the half note, so it is a pickup and is drawn short:
        # a quarter's two slots and the half's two, plus the one lead-in dash every
        # bar opens with. The `||` closing it is the anacrusis's own bar line.
        self.assertEqual(staff.split("\n")[-1].split("|")[1], "-" * 9)
        self.assertIn("||", staff.split("\n")[-1])
        # The frets sit on that grid: the first one slot in, the second two slots
        # later - a quarter note's worth, which is twice the width of the fret cell.
        bar = staff.split("\n")[0].split("|")[1]
        self.assertEqual(bar.index("10"), 1, bar)
        self.assertEqual(bar.index("6") - bar.index("10"), 4, bar)

    def test_an_untimed_progression_is_not_subdivided(self):
        """
        Without a written rhythm there are no durations to show, so every column stays
        one slot wide - the uniform grid the renderer has always fallen back to.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (0, 2.0)], durations=[0.25, 0.5],
                       frets=[[-1, -1, 10, 10, 10, 10]] * 2)
        for step in steps:
            del step.bar, step.beat
        bar = format_tab_staff(steps).split("\n")[0].split("|")[1]
        # Both notes are drawn one slot wide - the two-character cell and nothing more -
        # so the half note is *not* twice the quarter's width as it is above. What is
        # asserted is the uniformity, not the total: the bar is still filled out to its
        # metre, because the rest after the last note is time either way.
        self.assertEqual(bar.count("1"), 1, bar)
        self.assertEqual(len(bar) % 2, 1, bar)  # lead-in plus whole two-char cells

    def test_every_measure_is_closed(self):
        """
        Each measure ends with a barline rather than running into the next one, which
        is what TuxGuitar, Guitar Pro and printed tab all do.
        """
        steps = _timed(["Dm7", "G7", "Cmaj7"])
        staff = format_tab_staff(steps, measures_per_line=4)
        line = staff.split("\n")[0]
        # Opening barline, one per bar, and a fourth: the last bar is padded out to its
        # own length with rests, because the rest after the final note is still time.
        self.assertEqual(line.count("|"), 5, line)
        self.assertTrue(line.endswith("|"), line)

    def test_the_last_bar_is_padded_out_to_its_own_length(self):
        """
        A head whose last note ends early still fills its bar.

        The grid filled the holes *between* onsets but stopped at the last one, so the
        closing barline arrived mid-bar and the bar read shorter than the metre says.
        TuxGuitar draws the rest after the final note as dashes out to the barline.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (0, 2.0)], durations=[1.0, 0.5],
                       frets=[[-1, -1, 10, 10, 10, 10], [-1, -1, 7, 7, 6, 6]])
        line = format_tab_staff(steps).split("\n")[0]
        bar = line.split("|")[1]
        # The bar is 4/4, which is four beats of four slots each. Every row of the
        # system is the same length whatever the cell width happens to be, and the
        # low E row is struck on nothing, so its bar is the whole grid and nothing else.
        low_e = format_tab_staff(steps).split("\n")[-1].split("|")[1]
        self.assertEqual(len(bar), len(low_e), bar)
        # And the note ends before the barline, so there are dashes after it: the rest
        # is still time and has to be drawn as time.
        self.assertIn("6-------", bar, bar)

    def test_the_staff_wraps_at_measures_per_line(self):
        """
        `measures_per_line` is bars per *line of music*, and the flag's name has
        always claimed that. It did not: the staff was drawn as one long line and
        the flag only spaced the barlines. Three bars at two per line is two systems,
        the second holding the remaining bar.
        """
        steps = _timed(["Dm7", "G7", "Cmaj7"])
        staff = format_tab_staff(steps, measures_per_line=2)
        self.assertEqual(len(_systems(staff)), 2, staff)
        # A blank line separates them, or two systems read as one long one.
        self.assertIn("\n\n", staff)

    def test_a_barline_is_followed_by_a_dash_before_the_first_fret(self):
        """
        No fret sits hard against a barline; there is always a dash between them.

        TuxGuitar writes one, and measured over `jon6.tab` all 26 of its bars have one
        and the shortest lead-in in the file is a single dash. It is a small thing that
        stops a beat-1 fret reading as glued to the barline it follows.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (0, 3.0), (1, 1.0), (1, 3.0)],
                    frets=[[-1, -1, 10, 10, 10, 10], [-1, -1, 9, 9, 8, 8],
                           [-1, -1, 7, 7, 6, 6], [-1, -1, 5, 5, 4, 4]])
        for system in _systems(format_tab_staff(steps, show_melody=True)):
            for line in system:
                # Every bar segment of a *string* row opens with a dash - the run
                # between two barlines. [1:-1] drops the string label before the first
                # barline and the empty tail after the closing one. The text rows
                # above are excluded deliberately: they carry the same one-character
                # lead-in but as a space, since a dash through a chord name would be a
                # line through the word.
                if line[:1] not in ("e", "B", "G", "D", "A", "E"):
                    continue
                # Four distinct shapes, so every column is a fresh attack: with one
                # repeated shape `collapse` holds the second bar and prints no fret
                # there at all, which would make this test pass for the wrong reason.
                for segment in line.split("|")[1:-1]:
                    self.assertTrue(segment.startswith("-"), repr(segment))

    def test_a_wide_label_does_not_widen_another_system(self):
        """
        The cell width is per system, so one bar's long label does not stretch the rest.

        The width was computed once over every column, so a single wide label anywhere
        in the arrangement set the grid for the whole piece: `Cmaj7` in bar 1 drew
        every other bar five characters per cell it did not need. TuxGuitar sizes its
        bars independently (7, 14, 17 and 19 characters across `jon6.tab`); per system
        is the finest split that keeps two bars on one line sharing a grid.

        The long label is a *chord name*, not a fret, and that is deliberate: a fret
        cell has a floor of two characters (`STAFF_CELL_WIDTH`, which covers frets
        0-18), so a two-digit fret widens nothing on its own. What varies a bar's width
        in practice is the text above it.
        """
        steps = _timed(
            # `Cmaj7` is the only wide label in the piece.
            ["Cmaj7", "G7", "C7", "F7"],
            beats=[(0, 1.0), (1, 1.0), (2, 1.0), (3, 1.0)],
            frets=[[-1, -1, 7, 7, 6, 6]] * 4,
        )
        systems = _systems(
            format_tab_staff(steps, show_chords=True, measures_per_line=1)
        )
        # Four written bars, plus a fifth of padded rests closing the last one.
        self.assertEqual(len(systems), 5)
        wide = max(len(row) for row in systems[0])
        narrow = [max(len(row) for row in system) for system in systems[1:]]
        # Bar 1 is wider than bars 2 and 3, which hold the same columns as it does.
        self.assertGreater(wide, narrow[0])
        self.assertEqual(narrow[0], narrow[1], systems[1:3])
        # Bars 2 and 3 are drawn at the fret floor, not at `Cmaj7`'s five, and they
        # agree with each other. The cell width itself is `system_width`, already
        # covered by the shared-width test below; what is unique to this test is that
        # one wide label widens its own bar *only*.
        low_e = [row for row in systems[1] if row.startswith("E")][0]
        # Every row of a system is the same length - a cell of the same width throughout.
        self.assertEqual({len(row) for row in systems[1]}, {len(low_e)}, systems[1])
        # And the chord row above carries `G7` in the same grid.
        self.assertEqual(len(systems[1][0]), len(low_e), systems[1])
        self.assertGreater(wide, narrow[0])

    def test_bars_on_one_system_still_share_one_width(self):
        """
        The counterpart to the test above, and the reason for the limit: two bars drawn
        on the same system must keep a shared grid, or a fret stops lining up across
        the six strings.
        """
        steps = _timed(["Dm7", "G7"], frets=[[-1, -1, 10, 10, 10, 10], [-1, -1, 7, 7, 6, 6]])
        staff = format_tab_staff(steps, measures_per_line=4)
        self.assertEqual(len(_systems(staff)), 1)
        for system in _systems(staff):
            self.assertEqual(len({len(line) for line in system}), 1, system)

    def test_every_string_row_is_a_continuous_line_of_dashes(self):
        """
        The change that makes the staff read as tab rather than as a chord list: each
        string is drawn as one unbroken run of dashes with the frets sitting in it.

        Asserted on the string rows only. The chord, melody, metre and note-value
        rows are *text* and must stay unruled - a dash through a chord name would be
        a line through the word - which is why the fill is applied in `string_line`
        rather than in the shared `line` builder.
        """
        steps = _timed(["Dm7", "G7"], frets=_TWO_SHAPES)
        for system in _systems(format_tab_staff(steps)):
            strings = [line for line in system if line[:1] in ("e", "B", "G", "D", "A", "E")]
            self.assertEqual(len(strings), 6, system)
            for line in strings:
                # Only the leading string label, the barlines and the frets are not
                # dashes; nothing else may be a space, or the string has a gap in it.
                body = line[3:]
                self.assertNotIn(" ", body, line)
                self.assertTrue(set(body) <= set("-|0123456789x"), line)

    def test_rhythm_leaves_a_gap_for_a_held_chord(self):
        """
        A gap in the timing is rendered as empty columns, so a chord held for two
        beats is not drawn jammed up against the next one.
        """
        timed = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("C5", "maj7", "Cmaj7")]
        )
        timed[0].bar, timed[0].beat = 0, 1.0
        timed[1].bar, timed[1].beat = 0, 3.0  # two beats later, same bar
        line = self.staff_lines(timed)[0]
        # The rest on beat 2 is a blank column between the two shapes, so the
        # second fret sits at least one cell further along than the first. Stated in
        # cells rather than in characters, because the cell width is now per system
        # and a hard-coded character count would be asserting the grid's width rather
        # than the gap it is meant to show.
        gap = line.index("8") - line.index("10")
        self.assertGreaterEqual(gap, 6, line)
        # And the column between them holds no fret, only the cell separators.
        between = line[line.index("10") + 2: line.index("8")]
        self.assertFalse(any(ch.isdigit() for ch in between), between)

    def test_repeated_shape_is_struck_once_and_held(self):
        """
        Two consecutive steps sounding the same pitches are one attack, not two:
        the second column carries no frets, because the shape is still ringing.
        """
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
        ]
        line = self.staff_lines(steps)[0]
        self.assertEqual(line.count("10"), 1)

    def test_collapse_off_restrikes_every_step(self):
        """With collapse=False the same repeated shape is struck on every step."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
        ]
        self.assertEqual(self.staff_lines(steps, collapse=False)[0].count("10"), 2)

    def test_a_rest_breaks_the_hold(self):
        """
        A rest stops the ringing, so the same shape after a rest is struck again.
        Without this the tab would imply a sustain across silence.
        """
        held = make_voicing([-1, -1, 10, 10, 10, 10])
        other = make_voicing([-1, -1, 8, 8, 8, 8])
        step_a = ArrangementStep(chord="Dm7", melody="D5", voicing=held)
        step_b = ArrangementStep(chord="Dm7", melody="D5", voicing=held)
        step_c = ArrangementStep(chord="Cmaj7", melody="C5", voicing=held)
        # A gap in the timing between b and c: bar 0 beat 1, then bar 1 beat 1.
        step_a.bar, step_a.beat = 0, 1.0
        step_b.bar, step_b.beat = 0, 2.0
        step_c.bar, step_c.beat = 1, 1.0
        del other
        line = self.staff_lines([step_a, step_b, step_c])[0]
        # a is struck, b is held, and c restrikes because the rest broke the ring.
        self.assertEqual(line.count("10"), 2)

    def test_melody_only_step_spells_its_mutes(self):
        """
        A no-chord step is a single note on a silent instrument, so its unsounded
        strings show x even when show_mutes is off.
        """
        solo_voicing = make_voicing([-1, -1, -1, -1, 5, -1])
        step = ArrangementStep(
            chord="NC", melody="E4", voicing=solo_voicing, melody_only=True
        )
        lines = self.staff_lines([step])
        self.assertIn("x", "".join(lines))

    def test_unsounded_strings_are_blank_by_default(self):
        """
        In chord-melody a voice that is still ringing is not restruck, so a muted
        string is left blank rather than marked x on every chord.
        """
        self.assertNotIn("x", "".join(self.staff_lines(self.steps)))

    def test_show_mutes_marks_unsounded_strings(self):
        """show_mutes spells the mutes out, as an all-x low E and A."""
        rendered = "".join(self.staff_lines(self.steps, show_mutes=True))
        self.assertIn("x", rendered)

    def test_melody_string_is_starred(self):
        """
        The string carrying the melody is flagged with a '*', so the reader can see
        at a glance where the tune sits.
        """
        self.assertTrue(self.staff_lines(self.steps)[0].startswith("e*"))
        self.assertTrue(self.staff_lines(self.steps)[1].startswith("B "))

    def test_empty_progression_renders_empty_string(self):
        """No steps means an empty string, not a stray staff."""
        self.assertEqual(format_tab_staff([]), "")

    def test_staff_print_nothing(self):
        """The staff renderer is pure, like every other renderer in this library."""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            format_tab_staff(self.steps, show_melody=True, show_mutes=True)
        self.assertEqual(buffer.getvalue(), "")

    def test_rejects_a_nonsensical_bar_length(self):
        """A bar of zero beats cannot be laid out, so it is a usage error."""
        with self.assertRaises(ValueError):
            format_tab_staff(self.steps, beats_per_bar=0)
        with self.assertRaises(ValueError):
            format_tab_staff(self.steps, measures_per_line=0)
        with self.assertRaises(ValueError):
            format_tab_staff(self.steps, beat_type=0)


class TestStaffMetre(unittest.TestCase):
    """Tests the metre row: a count and a denominator, on both renderers."""

    def setUp(self):
        self.steps = _timed(["Dm7", "G7", "Cmaj7"])

    def staff(self, steps=None, **kwargs):
        """The staff with the rows this class is about explicitly switched on.

        The metre, the rhythm row and the chord names are all **off by default** now -
        the default output is the tab itself, six string rows and nothing else. So
        every test here asks for what it is testing, rather than relying on a default
        that now means the opposite.
        """
        kwargs.setdefault("show_timing", True)
        kwargs.setdefault("show_chords", True)
        return format_tab_staff(self.steps if steps is None else steps, **kwargs)

    def test_the_metre_is_printed_over_the_first_bar(self):
        """`4/4` sits in the first column of its own row, above the chords."""
        staff = self.staff()
        self.assertIn("4/4", staff)
        self.assertTrue(any("4/4" in row for row in staff.split("\n")))

    def test_the_metre_is_off_unless_asked_for(self):
        """
        The counterpart, and the reason this class passes the flags explicitly: the
        default staff is the tab, so it carries no time signature at all.
        """
        self.assertNotIn("4/4", format_tab_staff(self.steps))

    def test_the_metre_is_written_once_not_over_every_bar(self):
        """A signature holds until it changes, so one is enough.

        The same reasoning as `tabxml` writing `<time>` into the first measure only.
        A signature over every bar reads as a new one at each, and the bar stops
        reading as a continuation of the one before.
        """
        staff = self.staff(_timed(["Dm7"] * 5))
        self.assertEqual(staff.count("4/4"), 1)

    def test_cut_time_reads_two_two_and_not_two_four(self):
        """
        A count without a denominator is not a metre - the assertion 4/4 cannot make.

        2/2 and 2/4 are both two beats to the bar, so a test in common time passes
        either way. Three of the four committed test scores are 2/2, so this is the
        case that actually occurs.
        """
        staff = self.staff(beats_per_bar=2, beat_type=2)
        self.assertIn("2/2", staff)
        self.assertNotIn("2/4", staff)

    def test_the_html_page_carries_the_metre_too(self):
        """The page shows it in a row and in the meta line."""
        page = format_tab_html(self.steps)
        self.assertIn('<tr class="meter">', page)
        self.assertIn("<td>4/4</td>", page)
        self.assertIn("4/4", page.split('<p class="meta">')[1])

    def test_only_the_first_html_measure_states_it(self):
        """A page with three bars must not print three time signatures."""
        page = format_tab_html(self.steps, beats_per_bar=2, beat_type=2)
        self.assertEqual(page.count('<tr class="meter">'), 1)


class TestStaffNoteValues(unittest.TestCase):
    """Tests the rhythm row: how long each column sounds."""

    def rhythm_row(self, steps, **kwargs):
        """The rhythm row, found by its labels rather than by its position.

        `show_timing` is forced on: the row is off by default with the rest of the
        annotation, and a test about a row that is not drawn has to ask for it.
        """
        kwargs.setdefault("show_timing", True)
        staff = format_tab_staff(steps, **kwargs)
        for row in staff.split("\n"):
            if row.startswith("  |") and any(
                token in row for token in ("q", "h", "w", "e", "r", "~")
            ):
                return row
        raise AssertionError(f"no rhythm row in:\n{staff}")

    def cells(self, steps, **kwargs):
        """The rhythm row's labels, in column order, blanks dropped."""
        row = self.rhythm_row(steps, **kwargs)
        body = row[3:].replace("|", " ").replace("-", " ")
        return [cell.strip() for cell in body.split() if cell.strip()]

    def test_a_quarter_note_reads_q(self):
        """
        One beat in 4/4 is a quarter, the ordinary case.

        Four chords on four consecutive beats, so each really is one beat long. Note
        that a chord on beat 1 followed by the next chord on beat 2 is three beats of
        span - a dotted half - because the gap runs to the next sound, not to the bar
        line. That is the rule, and the whole-note test below is its other end.
        """
        steps = _timed(
            ["Dm7", "G7", "Cmaj7", "Fm7"],
            beats=[(0, 1.0), (0, 2.0), (0, 3.0), (0, 4.0)],
            # Four *distinct* shapes: `collapse` compares sounding pitches, so a
            # repeated shape would be a hold and print `~` rather than a note value.
            frets=[[-1, -1, 10, 10, 10, 10], [-1, -1, 9, 9, 8, 8],
                   [-1, -1, 7, 7, 6, 6], [-1, -1, 5, 5, 4, 4]],
        )
        self.assertEqual(self.cells(steps)[:4], ["q", "q", "q", "q"])

    def test_a_whole_note_reads_w_and_the_columns_after_it_are_rests(self):
        """
        A note that runs the bar is a whole note, and the silence after it is shown.

        This is what the row is *for*: before it, a whole note and a quarter were
        drawn identically, since both were one column of frets.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (1, 1.0)])
        cells = self.cells(steps)
        self.assertEqual(cells[0], "w")
        self.assertEqual(cells[1:4], ["r", "r", "r"])

    def test_a_cut_time_beat_is_a_half_note(self):
        """
        The beat is `4 / beat_type` quarters, so 2/2's beat is a half note.

        Both readings of that fraction are `q` in 4/4, which is why the whole suite
        passed while every other metre was wrong. `AGENTS.md` trap 9.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (0, 2.0)])
        self.assertIn("h", self.cells(steps, beats_per_bar=2, beat_type=2))

    def test_a_held_shape_is_a_tie_not_a_second_note(self):
        """
        A collapsed column is `~`, because the note began earlier.

        Without it a held chord reads as a fresh attack of the same note value, and
        the row would contradict the frets below it - which is exactly why the two
        renderers' tie and hold rules have to mean the same thing.
        """
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing,
                            bar=0, beat=1.0),
            ArrangementStep(chord="Dm7", melody="F5", voicing=voicing,
                            bar=0, beat=2.0),
        ]
        self.assertIn("~", self.cells(steps))

    def test_no_rhythm_row_without_a_written_rhythm(self):
        """
        An untimed progression gets the metre and no note-value row.

        One chord per beat would make every cell the same letter, and a row of them
        says nothing - worse, a blank row reads as a rendering failure.
        """
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        untimed = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
            ArrangementStep(chord="G7", melody="B4", voicing=voicing),
        ]
        staff = format_tab_staff(untimed, show_timing=True, show_chords=True)
        self.assertIn("4/4", staff)
        # Six string rows, the metre and the chord names - and no rhythm row.
        self.assertEqual(len(staff.split("\n")), 8, staff)

    def test_rhythm_false_suppresses_the_note_values_too(self):
        """`rhythm=False` asks for the uniform grid, so there is no rhythm to print."""
        staff = format_tab_staff(
            _timed(["Dm7", "G7"]), rhythm=False, show_timing=True, show_chords=True
        )
        self.assertIn("4/4", staff)
        self.assertEqual(len(staff.split("\n")), 8, staff)

    def test_show_timing_off_is_the_default(self):
        """
        `show_timing=False` is what you get without asking - the staff is the tab.

        The metre and the note-value rows are the two that `show_timing` governs, and the
        only way to get them, so this asserts the default and the two rows it
        withholds.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (0, 2.0)])
        without = format_tab_staff(steps, show_melody=True)
        self.assertNotIn("4/4", without)
        # Six string rows, a melody row - and no chord row either, since `show_chords`
        # went off by default at the same time.
        self.assertEqual(len(without.split("\n")), 7, without)
        # And the escape hatch still works in the other direction, on demand.
        with_rows = format_tab_staff(
            steps, show_melody=True, show_chords=True, show_timing=True
        )
        self.assertIn("4/4", with_rows)
        self.assertEqual(len(with_rows.split("\n")), 10, with_rows)

    def test_the_html_page_shows_the_same_values(self):
        """The page's rhythm row is the same data the terminal prints."""
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (1, 1.0)])
        page = format_tab_html(steps)
        row = re.search(r'<tr class="rhythm">(.*?)</tr>', page, re.S)
        self.assertIsNotNone(row)
        assert row is not None  # pyright does not narrow through assertIsNotNone
        self.assertIn("<td>w</td>", row.group(1))
        self.assertIn('<td class="rest">r</td>', row.group(1))

    def test_a_held_cell_is_marked_in_the_html_too(self):
        """The tie carries a class, so the page dims it like the staff."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing, bar=0, beat=1.0),
            ArrangementStep(chord="Dm7", melody="F5", voicing=voicing, bar=0, beat=2.0),
        ]
        self.assertIn('<td class="hold">~</td>', format_tab_html(steps))


    def test_the_transcribed_duration_caps_the_note(self):
        """
        A note is only as long as it is written: a quarter stays a quarter.

        Without the cap the note would run to the next onset and read as a half,
        which is the `tabxml` rule - `duration` caps, never stretches.
        """
        steps = _timed(["Dm7", "G7"], durations=[0.25, None])
        cells = self.cells(steps)
        self.assertEqual(cells[0], "q")
        self.assertNotIn("h", cells)

    def test_an_unnameable_length_prints_the_number_not_a_wrong_note(self):
        """
        A length nothing names falls back to its quarter count.

        Rounding it to the nearest legal value would print a note that is not being
        played, which is the one thing a rhythm row must never do.
        """
        steps = _timed(["Dm7", "G7"], durations=[0.4, None])
        cells = self.cells(steps)
        self.assertTrue(
            any(cell.endswith("q") and cell[:-1].replace(".", "").isdigit()
                for cell in cells),
            f"expected a numeric fallback, got {cells}",
        )

    def test_a_note_never_runs_past_its_own_bar(self):
        """
        A long silence must not print a longer-than-a-bar note.

        Measuring to the next sound rather than to the bar's end puts a six-quarter
        "note" in one cell, which is the defect this pins.
        """
        steps = _timed(["Dm7", "G7"], beats=[(0, 1.0), (3, 1.0)])
        for cell in self.cells(steps):
            self.assertLess(len(cell), 6, f"{cell} is longer than a bar")


class TestStaffRhythmAgreesWithTheScore(unittest.TestCase):
    """The rhythm row and the score writers must agree where their grids overlap.

    `_staff_rhythm` is computed from the column grid rather than from
    `tabscore.score_events`, because the two grids are deliberately different - the column
    grid gives a column to the first of several steps on one onset, and the score
    keeps them all. That is a real difference and it is not tested away here.

    What *is* tested is the rule they are supposed to share: a note lasts until the
    next sound, capped by its written duration. Where the grids line up the two must
    produce the same length, or the three renderers would state three different
    rhythms for one arrangement.
    """

    def test_a_lone_step_per_onset_agrees_with_the_score(self):
        """
        One step on each onset: the staff and the score must match exactly.

        Hand-built rather than from the corpus, because a Weimar head routinely puts
        two melody notes on one beat - the eighth-note skeleton does it in most bars -
        and those onsets are exactly where the two grids are *meant* to differ. A
        fixture with a note on every beat is the case where they must not.
        """
        from tabscore import score_events, substitute_steps

        steps = _timed(
            ["Dm7", "G7", "Cmaj7"],
            beats=[(0, 1.0), (0, 2.0), (1, 1.0)],
            frets=[
                [-1, -1, 10, 10, 10, 10],
                [-1, -1, 9, 9, 8, 8],
                [-1, 3, 3, 2, 3, -1],
            ],
        )
        columns = _staff_columns(steps, 4, 4, True, True)
        values = _staff_rhythm(columns, 4, 4, True)
        quarters = {label: length for length, label in _NOTE_VALUES}
        staff_lengths = [
            quarters.get(label)
            for (_onset, step, strikes), (label, _kind) in zip(columns, values)
            if step is not None and strikes
        ]
        # `score_events` returns (events, pickup); the pickup is not what is compared.
        score_events, _pickup = score_events(substitute_steps(steps), 4, True, 4)
        score_lengths = [
            length for step, _strikes, length in score_events if step is not None
        ]
        # The last column runs to the end of its bar, so it is left out rather than
        # compared against a gap to a note that is not there.
        self.assertEqual(staff_lengths[:-1], score_lengths[:-1])

    def test_the_duration_cap_is_the_same_rule_in_both(self):
        """A quarter written under a two-beat gap is a quarter in both renderings."""
        from tabscore import score_events

        steps = _timed(
            ["Dm7", "G7"], beats=[(0, 1.0), (1, 1.0)], durations=[0.25, None],
            frets=_TWO_SHAPES,
        )
        score_events, _pickup = score_events(steps, 4, True, 4)
        self.assertEqual(
            [length for step, _s, length in score_events if step][0], 1.0
        )
        self.assertIn("q", format_tab_staff(steps, show_timing=True))


class TestStaffTimingRowsStayAligned(unittest.TestCase):
    """The two new rows obey the alignment the string rows already had.

    `TestStaffBarlineAlignment` was written when the staff had two rows above the
    strings. A third and fourth would break its invariant silently if they were
    spelled out rather than routed through the same `line()` builder, so the
    invariant is restated over the rows that exist now.
    """

    def build(self, **kwargs):
        """A timed three-bar progression, so there are barlines to line up."""
        steps = _timed(["Dm7", "G7", "Cmaj7"], beats=[(0, 1.0), (1, 1.0), (2, 1.0)])
        return format_tab_staff(
            steps, show_melody=True, show_chords=True, show_timing=True,
            measures_per_line=1, **kwargs,
        )

    def test_every_row_of_a_system_is_the_same_width_with_the_timing_rows(self):
        """The metre and note-value rows are ruled like everything else.

        Per system, not per staff: the staff wraps, and a short last system is
        correct rather than a broken one. See `_systems`.
        """
        for system in _systems(self.build()):
            self.assertEqual(len({len(line) for line in system}), 1, system)

    def test_the_new_rows_share_the_string_rows_barlines(self):
        """A barline lands in the same column on every row, new ones included."""
        for system in _systems(self.build()):
            positions = [[i for i, c in enumerate(line) if c == "|"] for line in system]
            strings = next(i for i, line in enumerate(system) if line.startswith("e"))
            for index, row in enumerate(positions):
                self.assertEqual(row, positions[strings], f"row {index}: {system[index]!r}")

    def test_the_new_rows_are_end_bounded(self):
        """Every system's rows begin and end with a barline, or they read as captions."""
        for system in _systems(self.build()):
            for line in system[:2]:
                self.assertTrue(line.startswith("  |"), repr(line))
                self.assertTrue(line.endswith("|"), repr(line))
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing, bar=0, beat=1.0),
            ArrangementStep(chord="Dm7", melody="F5", voicing=voicing, bar=0, beat=2.0),
        ]
        self.assertIn('<td class="hold">~</td>', format_tab_html(steps))


class TestStaffStepTiming(unittest.TestCase):
    """Tests the optional timing fields on ArrangementStep."""

    def test_timing_defaults_to_none(self):
        """A hand-built step has no timing, so it cannot be placed on a grid."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        step = ArrangementStep(chord="Dm7", melody="D5", voicing=voicing)
        self.assertIsNone(step.bar)
        self.assertIsNone(step.beat)
        self.assertIsNone(step.duration)
        self.assertFalse(step.has_timing)

    def test_bar_and_beat_make_a_step_timed(self):
        """A step carrying a bar and a beat reports itself as timed."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        step = ArrangementStep(
            chord="Dm7", melody="D5", voicing=voicing, bar=0, beat=1.0, duration=0.5
        )
        self.assertTrue(step.has_timing)
        self.assertEqual((step.bar, step.beat, step.duration), (0, 1.0, 0.5))

    def test_a_negative_bar_is_valid_timing(self):
        """Pickup bars are negative, and that is ordinary timing, not a fault."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        step = ArrangementStep(chord="Dm7", melody="D5", voicing=voicing, bar=-2, beat=3.0)
        self.assertTrue(step.has_timing)

    def test_dict_shim_exposes_the_timing(self):
        """The backward-compatible indexing reaches the new fields too."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        step = ArrangementStep(chord="Dm7", melody="D5", voicing=voicing, bar=3, beat=2.0)
        self.assertEqual(step["bar"], 3)
        self.assertEqual(step["beat"], 2.0)
        self.assertTrue(step["has_timing"])


class TestTabstaffModuleBoundary(unittest.TestCase):
    """Tests that the staff renderers live in `tabstaff` and stay importable
    from `arranger`."""

    def test_renderers_are_defined_in_tabstaff(self):
        """
        The split's whole point: the three whole-progression renderers must not be
        defined in arranger.py any more, so arranger re-exports rather than owns
        them. format_progression, which is per-step rather than per-staff, stays.
        """
        import arranger
        import tabstaff

        for name in ("format_tab_staff", "format_tab_html", "write_tab_html"):
            self.assertTrue(
                hasattr(tabstaff, name), f"tabstaff should define {name}"
            )
            self.assertNotIn(
                name, vars(arranger), f"{name} should not be defined in arranger"
            )
        self.assertIn("format_progression", vars(arranger))

    def test_arranger_re_exports_the_renderers(self):
        """
        The README and the tests all spell these as `from arranger import`,
        so the split must not move the public name even though it moved the code.
        The MusicXML renderers are included: they live in `tabxml`, which `tabstaff`
        re-exports, and all four must be reachable the same one way.
        """
        import arranger
        import tabstaff

        for name in ("format_tab_staff", "format_tab_html", "write_tab_html"):
            self.assertIs(getattr(arranger, name), getattr(tabstaff, name))
        for name in ("format_musicxml", "write_musicxml"):
            self.assertIs(getattr(arranger, name), getattr(tabstaff, name))

    def test_the_musicxml_renderers_are_lazy(self):
        """
        `tabxml` needs music21, an optional extra, and it imports `tabstaff` - so it
        must be resolved on first access rather than at import time. Importing
        `arranger` and `tabstaff` on a machine with no music21 has to keep working,
        which is the whole reason music21 is not a runtime dependency.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                # Block music21 outright, then check the package still imports and
                # that only *calling* the renderer complains.
                "import sys;"
                " sys.modules['music21'] = None;"
                " import arranger, tabstaff;"
                " print(arranger.format_tab_staff.__name__);"
                " print(arranger.format_musicxml.__name__)",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("format_musicxml", result.stdout)

    def test_importing_tabstaff_first_does_not_crash(self):
        """
        The entry order a caller controls cannot matter, and the reason is the edge
        rather than a lazy trick: `tabstaff` imports `arranger.tuning`, a leaf that
        needs nothing from the facade, so importing it first runs the facade to
        completion before the renderer reaches its own first line.
        `tests/meta_front_end_dag.py::TestTheRuntimeCycle` holds that to a blank
        package, which is the sharper form - a facade that never ran at all.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import tabstaff; from arranger import format_tab_html;"
                " print(format_tab_html.__name__)",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("format_tab_html", result.stdout)

    def test_dunder_all_matches_the_public_surface(self):
        """
        `from arranger import *` exports the facade's API, and this keeps it honest:
        every listed name must resolve, and every public name the facade *defines* must
        be listed.

        A bound **submodule** is not a name the facade defines - it is the module's own
        path, which `arranger.grips` reaches whether or not `__all__` names it - so
        module objects are excluded. Everything else is not, which is what stops the
        list from going quietly short.
        """
        import types

        import arranger

        for name in arranger.__all__:
            self.assertTrue(hasattr(arranger, name), f"{name} in __all__ but missing")
        defined = {
            name
            for name, value in vars(arranger).items()
            if not name.startswith("_") and not isinstance(value, types.ModuleType)
        }
        # Names bound by imports rather than defined by this module: the typing and
        # stdlib aliases the facade itself uses, and `__future__`'s `annotations`, which
        # is a `_Feature` rather than a module and so is not excluded by the rule above.
        ignored = {"Any", "List", "ModuleType", "TYPE_CHECKING", "annotations"}
        self.assertEqual(
            defined - set(arranger.__all__) - ignored,
            set(),
            "a public name is defined but missing from __all__",
        )

    def test_tabstaff_shares_the_layout_core(self):
        """
        Both renderings call the same _staff_columns, which is what makes them
        agree on where a chord sits and what counts as a hold. They must not drift
        into separate implementations.
        """
        import inspect

        import tabstaff

        for name in ("format_tab_staff", "format_tab_html"):
            self.assertIn(
                "_staff_columns",
                inspect.getsource(getattr(tabstaff, name)),
                f"{name} should build its columns from _staff_columns",
            )


def _systems(staff: str) -> List[List[str]]:
    """A rendered staff split into systems, each a list of its own lines.

    The staff wraps, so the invariant holds of one *system* at a time rather than of the
    whole output: every row the same width, every barline in the same column. Two systems
    are separated by a blank line and are free to be
    different widths, because the last one is short by definition. Asserting across
    the whole output would therefore assert something false, and would stop being
    the alignment check it was written to be.
    """
    systems: List[List[str]] = [[]]
    for line in staff.split("\n"):
        if line == "":
            systems.append([])
        else:
            systems[-1].append(line)
    return [system for system in systems if system]


class TestStaffBarlineAlignment(unittest.TestCase):
    """Tests that every row of the ASCII staff is ruled identically.

    The chord, melody and string rows are drawn on one shared column grid, so a
    barline is only legible if it lands in the same column on all of them. Two
    separate defects made it not: the chord and melody rows began with three
    spaces rather than a barline, and rstrip() trimmed their trailing blank
    columns so they ended short of the string rows.

    Every assertion here is per **system**, which is the unit the invariant now has:
    the staff wraps at `measures_per_line`, and two systems of different widths is
    correct rather than broken. Asserting over the whole output would fail on every
    arrangement whose last system is short - that is, on nearly all of them.
    """

    def build(self, measures_per_line=1, bars=4):
        """A timed progression of `bars` one-bar chords, to force real barlines."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D", "m7", "Dm7"), ("G", "7", "G7"),
             ("C", "maj7", "Cmaj7"), ("F", "m7", "Fm7")][:bars]
        )
        for index, step in enumerate(steps):
            step.bar, step.beat, step.duration = index + 1, 1.0, 4.0
        # The annotation rows are on explicitly: this class is about how the chord,
        # melody, metre and note-value rows line up with the strings, and all four are
        # off by default now that the default staff is the tab itself.
        return format_tab_staff(
            steps, show_melody=True, show_chords=True, show_timing=True,
            measures_per_line=measures_per_line,
        )

    def test_every_row_of_a_system_is_the_same_width(self):
        """A short chord row is what made the staff look unaligned.

        Per system, not per staff: a wrapped staff's systems differ in width, and
        the last is short by definition.
        """
        for system in _systems(self.build()):
            self.assertEqual(len({len(line) for line in system}), 1, system)

    def test_barlines_land_in_the_same_column_on_every_row(self):
        """The barline positions are compared against the string rows."""
        for system in _systems(self.build()):
            positions = [[i for i, c in enumerate(line) if c == "|"] for line in system]
            for line, row in zip(system[1:], positions[1:]):
                self.assertEqual(row, positions[2], f"misaligned: {line!r}")

    def test_chord_and_melody_rows_are_both_end_bounded(self):
        """
        A chord row with no leading barline reads as a caption above the staff
        rather than as part of it, so both ends must be ruled.

        Every system's rows, not the first system's: a wrapped staff would otherwise
        be checked only where the wrapping happens not to matter.
        """
        for system in _systems(self.build()):
            for line in system[:2]:
                self.assertTrue(line.startswith("  |"), repr(line))
                self.assertTrue(line.endswith("|"), repr(line))

    def test_systems_of_four_bars_still_line_up(self):
        """Fewer, wider systems are ruled just as exactly as one-bar systems.

        The default is four bars per line, so this is the shape actually rendered -
        and a wider system is the stricter case, since a barline that drifts is easier
        to miss in a short one.
        """
        systems = _systems(self.build(measures_per_line=4))
        # Four written bars fit one system; the padded closing bar wraps to a second.
        self.assertEqual(len(systems), 2, systems)
        for system in systems:
            self.assertEqual(len({len(line) for line in system}), 1, system)
            positions = [[i for i, c in enumerate(line) if c == "|"] for line in system]
            for row in positions[1:]:
                self.assertEqual(row, positions[2])


class TestStaffAnacrusis(unittest.TestCase):
    """A short first bar is drawn short and closed with the double bar line.

    The ASCII staff is a fixed grid, but unlike GP5 it can leave a measure short:
    the pickup's columns stop where its music stops, and `||` closes the bar - the
    same `light-light` the MusicXML writer puts on the measure.
    """

    def test_the_pickup_bar_is_short_and_double_ruled(self):
        import headxml
        from tests.support import BLUE_MOON

        steps, head, _report = headxml.arrange_xml_head(BLUE_MOON)
        staff = format_tab_staff(
            steps, beats_per_bar=head.beats_per_bar, beat_type=head.beat_type
        )
        line = staff.split("\n")[0]
        self.assertIn("||", line)
        pickup, rest = line.split("||", 1)
        self.assertLess(
            len(pickup.split("|")[1]),
            len(rest.split("|")[0]),
            "the pickup bar is a quarter note in a four-quarter bar, so it is narrower",
        )
