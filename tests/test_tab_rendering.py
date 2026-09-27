import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser

from arranger import (
    ArrangementStep,
    Voicing,
    VoiceLeadingEngine,
    format_progression,
    format_tab_staff,
    format_tab_html,
    write_tab_html,
)


def make_voicing(frets):
    """Builds a Voicing from raw frets, deriving top_fret/avg_fret as the engine does."""
    active = [f for f in frets if f >= 0]
    return Voicing(
        frets=list(frets),
        top_fret=max(active) if active else 0,
        avg_fret=sum(active) / len(active) if active else 0.0,
    )


class TestVoicingTabBlock(unittest.TestCase):
    """Tests the six-line vertical tab renderer on a Voicing."""

    def setUp(self):
        # Dm7 in the traditional high-E block: strings D-G-B-E carry 10-10-10-10.
        self.high_e = make_voicing([-1, -1, 10, 10, 10, 10])
        # Same inversion voiced on the B string instead (strings A-D-G-B).
        self.b_string = make_voicing([-1, 3, 3, 2, 3, -1])

    def test_block_has_six_lines_in_reading_order(self):
        """One line per string, ordered high E (string 1) down to low E (string 6)."""
        lines = self.high_e.tab_block()
        self.assertEqual(len(lines), 6)
        self.assertEqual([line[0] for line in lines], ["e", "B", "G", "D", "A", "E"])

    def test_block_renders_frets_and_mutes(self):
        """Played strings show their fret; muted strings show 'x'."""
        lines = self.high_e.tab_block()
        for line in lines[:4]:
            self.assertIn("10", line)
        for line in lines[4:]:
            self.assertIn("x", line)

    def test_block_places_b_string_melody_on_second_line(self):
        """
        A B-string voicing mutes the high E and plays the A, so the topmost
        rendered line (high E) is 'x' and the melody appears one line lower.
        """
        # frets [-1, 3, 3, 2, 3, -1] low E -> high E, so rendering high E first
        # gives: high E x, B 3, G 2, D 3, A 3, low E x.
        cells = [line[2:4].strip() for line in self.b_string.tab_block()]
        self.assertEqual(cells, ["x", "3", "2", "3", "3", "x"])

    def test_block_columns_align_for_single_and_double_digit_frets(self):
        """
        Every fret cell is right-aligned to two characters, so the closing '|'
        of each line lands in the same column whether frets are 1 or 2 digits.
        This is what keeps a low B-string voicing visually aligned.
        """
        for voicing in (self.high_e, self.b_string):
            for line in voicing.tab_block():
                self.assertEqual(len(line), 6, line)
                self.assertTrue(line.endswith("-|"), line)

    def test_block_matches_the_one_line_tab(self):
        """Each rendered cell equals the corresponding entry of tab_string()."""
        expected = self.b_string.tab_string().split("-")
        # tab_string runs low E -> high E; tab_block renders high E -> low E.
        cells = [line[2:4].strip() for line in self.b_string.tab_block()]
        self.assertEqual(cells, list(reversed(expected)))

    def test_fully_muted_voicing_renders_without_raising(self):
        """An all-muted voicing still renders six lines rather than raising."""
        muted = make_voicing([-1] * 6)
        lines = muted.tab_block()
        self.assertEqual(len(lines), 6)
        self.assertTrue(all("x" in line for line in lines))

    def test_tab_joins_block_with_newlines(self):
        """tab() is exactly tab_block() joined by newlines."""
        self.assertEqual(self.high_e.tab(), "\n".join(self.high_e.tab_block()))


class TestArrangementStepTab(unittest.TestCase):
    """Tests that ArrangementStep delegates its tab rendering to its Voicing."""

    def setUp(self):
        self.voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        self.step = ArrangementStep(chord="Dm7", melody="D5", voicing=self.voicing)

    def test_tab_line_delegates_to_voicing(self):
        """tab_line() is the one-line form and equals voicing.tab_string()."""
        self.assertEqual(self.step.tab_line(), "x-x-10-10-10-10")
        self.assertEqual(self.step.tab_line(), self.voicing.tab_string())

    def test_tab_block_delegates_to_voicing(self):
        """tab_block() equals voicing.tab_block() line for line."""
        self.assertEqual(self.step.tab_block(), self.voicing.tab_block())


class TestFormatProgression(unittest.TestCase):
    """Tests the progression-level renderer returned by format_progression()."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # Pinned to drop-2 on the high E block, so the expected tabs below describe a
        # known arrangement rather than whatever the selector currently prefers.
        self.major = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
            grips=("drop2",),
        )
        self.all_of_me = self.engine.arrange_progression(
            [("C5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7"), ("C5", "maj7", "Cmaj7")]
        )

    def test_one_line_per_step_by_default(self):
        """Default rendering gives one line per step, carrying chord, melody and tab."""
        rendered = format_progression(self.major)
        lines = rendered.split("\n")
        self.assertEqual(len(lines), len(self.major))
        self.assertIn("Dm7", lines[0])
        self.assertIn("D5", lines[0])
        self.assertIn("x-x-10-10-10-10", lines[0])
        self.assertIn("x-x-9-9-8-8", lines[2])

    def test_vertical_rendering_gives_seven_lines_per_step(self):
        """
        Vertical mode emits a header line plus the six tab lines for each step,
        with a blank line between steps.
        """
        rendered = format_progression(self.major, vertical=True)
        blocks = rendered.split("\n\n")
        self.assertEqual(len(blocks), len(self.major))
        for block in blocks:
            lines = block.split("\n")
            self.assertEqual(len(lines), 7)
            self.assertEqual(
                [line[0] for line in lines[1:]], ["e", "B", "G", "D", "A", "E"]
            )

    def test_non_chord_tone_step_is_annotated(self):
        """
        The D5 in 'All of Me' bar 2 is the 9th over Cmaj7, so the default
        strategy reharmonises it and the rendered line must say so.
        """
        rendered = format_progression(self.all_of_me)
        self.assertIn("non-chord tone", rendered)
        self.assertIn("Cmaj9", rendered)
        # The two chord-tone steps carry no annotation.
        self.assertEqual(rendered.count("non-chord tone"), 1)

    def test_chord_tone_progression_has_no_annotation(self):
        """A progression of plain chord tones renders without any annotation."""
        self.assertNotIn("non-chord", format_progression(self.major))

    def test_empty_progression_renders_empty_string(self):
        """No steps means an empty string, not a stray newline."""
        self.assertEqual(format_progression([]), "")

    def test_renderers_print_nothing(self):
        """
        format_progression() and the Voicing/ArrangementStep tab helpers are pure
        renderers: they return a string and write nothing to stdout, leaving the
        caller in control of how tab is displayed.
        """
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            format_progression(self.major)
            format_progression(self.major, vertical=True)
            self.major[0].tab_line()
            self.major[0].tab_block()
            self.major[0].voicing.tab()
            self.major[0].voicing.tab_block()
        self.assertEqual(buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()



class TestStaffTab(unittest.TestCase):
    """Tests the six-line staff renderer, format_tab_staff()."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # Dm7 -> G7 -> Cmaj7, pinned to drop-2 on the high E block. These tests are
        # about the *renderer*, so the arrangement is fixed rather than left to the
        # selector, which would otherwise choose a different string set or a shell.
        self.steps = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
            grips=("drop2",),
        )

    def staff_lines(self, steps, **kwargs):
        """The six string lines of a staff, with the chord line stripped off."""
        return format_tab_staff(steps, **kwargs).split("\n")[-6:]

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
        for step, row in zip(self.steps, lines):
            # Dm7 is x-x-10-10-10-10, so the top four staff lines all carry a 10.
            for string_index in (5, 4, 3, 2):
                self.assertIn(str(step.voicing.frets[string_index]), lines[5 - string_index])

    def test_chord_line_names_every_chord(self):
        """The chord-name line sits above the staff and names each chord once."""
        rendered = format_tab_staff(self.steps)
        top = rendered.split("\n")[0]
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
        top, first_string = format_tab_staff(self.steps).split("\n")[:2]
        self.assertEqual(top.index("Dm7"), first_string.index("10"))

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
        """
        timed = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("C5", "maj7", "Cmaj7")]
        )
        timed[0].bar, timed[0].beat = 0, 1.0
        timed[1].bar, timed[1].beat = 1, 1.0
        # measures_per_line=1 draws a barline at every bar change. The three blank
        # columns between the two shapes are the rest of bar 0, and the barline
        # falls after them, so the second bar's shape sits beyond it.
        line = self.staff_lines(timed, measures_per_line=1)[0]
        # The staff opens with its own '|', so the barline opened by partition is
        # that one; the next '|' is the real barline between bar 0 and bar 1.
        head, _, tail = line.partition("|")
        head, _, tail = tail.partition("|")
        self.assertNotIn("|", head)               # nothing but the staff's own bar
        self.assertIn("10", head)                 # bar 0's shape
        # A barline opens bar 1, and bar 0's three remaining beats are the rests
        # written just before it - so the barline sits after them, not before.
        self.assertTrue(tail.rstrip("-| ").endswith("8"))
        # The three remaining beats of bar 0 are blank columns between the two
        # shapes, so there is a run of space before bar 1's barline.
        self.assertIn("   ", tail)
        self.assertNotIn("10", tail)              # and bar 1 is a fresh shape

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
        # second fret sits several columns along from the first.
        gap = line.index("8") - line.index("10")
        self.assertGreater(gap, 6, line)
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


class _TagBalance(HTMLParser):
    """Minimal well-formedness checker: collects unbalanced and unclosed tags."""

    VOID = {"meta", "br", "img", "link", "hr", "input"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.mismatched = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.mismatched.append(tag)


class TestHtmlTab(unittest.TestCase):
    """Tests the HTML page renderer, format_tab_html()."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.steps = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
            grips=("drop2",),
        )
        self.html = format_tab_html(self.steps, title="Test", subtitle="A subtitle")

    def parse(self, html=None):
        """Feeds the page to a tag-balance checker and returns it."""
        checker = _TagBalance()
        checker.feed(html if html is not None else self.html)
        return checker

    def test_page_is_a_complete_html_document(self):
        """The output opens with a doctype and carries the lang and charset."""
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="en">', self.html)
        self.assertIn('<meta charset="utf-8">', self.html)
        self.assertTrue(self.html.rstrip().endswith("</html>"))

    def test_page_is_well_formed(self):
        """Every tag opened is closed, in order, so a browser parses it as written."""
        checker = self.parse()
        self.assertEqual(checker.mismatched, [])
        self.assertEqual(checker.stack, [])

    def test_page_is_self_contained(self):
        """
        No external stylesheet, script or image: the file can be opened from disk
        or emailed with nothing else. This is why the stylesheet is inlined.
        """
        for external in ("<link", "<script", "src=", "http://", "https://"):
            self.assertNotIn(external, self.html, external)

    def test_viewport_meta_lets_a_phone_size_it(self):
        """Without the viewport the page renders zoomed-out on a phone."""
        self.assertIn('name="viewport"', self.html)

    def test_title_and_subtitle_are_shown(self):
        """The heading carries the title, and the subtitle line when given."""
        self.assertIn("<title>Test</title>", self.html)
        self.assertIn("<h1>Test</h1>", self.html)
        self.assertIn('<p class="sub">A subtitle</p>', self.html)

    def test_subtitle_is_omitted_when_empty(self):
        """No subtitle means no empty element left behind."""
        self.assertNotIn('class="sub"', format_tab_html(self.steps))

    def test_each_measure_has_six_string_rows_high_e_first(self):
        """
        Six string rows per measure, ordered high E (string 1) down to low E, which
        is the reading order of the ASCII staff.
        """
        measure = re.search(r'<div class="measure"><table>(.*?)</table>', self.html, re.S)
        self.assertIsNotNone(measure)
        assert measure is not None  # pyright does not narrow through assertIsNotNone
        rows = re.findall(r'<tr class="string">.*?</tr>', measure.group(1), re.S)
        self.assertEqual(len(rows), 6)
        starred = [i for i, row in enumerate(rows) if 'class="soprano"' in row]
        self.assertEqual(starred, [0])  # the melody is on the high E string

    def test_every_row_of_a_measure_has_the_same_cell_count(self):
        """
        A column is one cell on every row, which is what keeps the chord names,
        the melody notes and the six string rows vertically aligned - the whole
        reason for rendering a table rather than a block of text.
        """
        measure = re.search(r'<div class="measure"><table>(.*?)</table>', self.html, re.S)
        self.assertIsNotNone(measure)
        assert measure is not None  # pyright does not narrow through assertIsNotNone
        counts = {
            row.count("<td>") + row.count('<th')
            for row in re.findall(r'<tr class="[^"]+">.*?</tr>', measure.group(1), re.S)
        }
        self.assertEqual(len(counts), 1, counts)

    def test_frets_from_the_voicing_appear(self):
        """The Dm7 shape's frets are on the page, on their own strings."""
        self.assertIn("<td>10</td>", self.html)
        self.assertIn("Dm7", self.html)

    def test_chord_name_is_printed_once_per_change(self):
        """
        A chord held across several slots is named once, the way a lead sheet
        spells it, rather than repeated in every column.
        """
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        held = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
        ]
        self.assertEqual(format_tab_html(held).count("Dm7"), 1)

    def test_repeated_shape_is_struck_once(self):
        """With collapse on, the held column carries no frets."""
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        held = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
            ArrangementStep(chord="Dm7", melody="D5", voicing=voicing),
        ]
        self.assertEqual(format_tab_html(held).count("<td>10</td>"), 4)
        self.assertEqual(
            format_tab_html(held, collapse=False).count("<td>10</td>"), 8
        )

    def test_chord_in_force_is_not_restarted_between_measures(self):
        """
        The chord being held is tracked across the whole page, so a chord spanning
        a barline is named once rather than at the top of each bar.
        """
        voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        first = ArrangementStep(chord="Dm7", melody="D5", voicing=voicing, bar=0, beat=1.0)
        second = ArrangementStep(chord="Dm7", melody="D5", voicing=voicing, bar=1, beat=1.0)
        page = format_tab_html([first, second], measures_per_line=1)
        # Once in the page, and once as the row that carries the name.
        self.assertEqual(page.count("Dm7"), 1)

    def test_two_renders_do_not_influence_each_other(self):
        """
        The chord in force is threaded through a call, not held in module state, so
        rendering the same progression twice gives the same page both times.
        """
        self.assertEqual(format_tab_html(self.steps), format_tab_html(self.steps))

    def test_bar_numbers_count_from_the_first_bar(self):
        """
        A head selected from bar 1 is numbered from 1, not padded out by the bars
        before it, and the numbering advances by measures_per_line per system.
        """
        # Eight bars of one chord per bar, laid out four bars to a system, so the
        # page has two systems and the second is numbered 5.
        timed = self.engine.arrange_progression(
            [("D5", "m7", "Dm7")] * 16 + [("C5", "maj7", "Cmaj7")] * 16
        )
        for index, step in enumerate(timed):
            step.bar, step.beat = index // 4, 1.0
        page = format_tab_html(timed, measures_per_line=4)
        numbers = re.findall(r'<span class="barnum">(\d+)</span>', page)
        self.assertEqual(numbers, ["1", "5"])

    def test_melody_line_is_shown_by_default_and_can_be_turned_off(self):
        """Note names are on by default in the page, unlike the ASCII staff."""
        self.assertIn("D5", self.html)
        self.assertNotIn("D5", format_tab_html(self.steps, show_melody=False))

    def test_mutes_are_blank_unless_asked_for(self):
        """
        A ringing voice is not restruck, so a muted string is an empty cell; only
        show_mutes spells the x out.
        """
        self.assertNotIn('class="mute"', self.html)
        self.assertIn('class="mute"', format_tab_html(self.steps, show_mutes=True))

    def test_melody_only_step_always_shows_its_mutes(self):
        """
        A no-chord step is one note on a silent instrument, so its other strings
        show x whatever show_mutes says.
        """
        solo_voicing = make_voicing([-1, -1, -1, -1, 5, -1])
        step = ArrangementStep(
            chord="NC", melody="E4", voicing=solo_voicing, melody_only=True
        )
        self.assertIn('class="mute">x<', format_tab_html([step]))

    def test_notes_are_rendered_as_a_list(self):
        """The provenance notes reach the page as list items."""
        page = format_tab_html(self.steps, notes=["lifted an octave", "held in register"])
        self.assertIn("<li>lifted an octave</li>", page)
        self.assertIn("<li>held in register</li>", page)

    def test_escapes_markup_in_a_chord_name(self):
        """
        Chord names can come from the corpus database, so markup in one is escaped
        rather than injected into the page.
        """
        nasty = ArrangementStep(
            chord="<script>alert(1)</script>", melody="D5",
            voicing=make_voicing([-1, -1, 10, 10, 10, 10]),
        )
        page = format_tab_html([nasty])
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        # And the escaped text must not unbalance the document.
        self.assertEqual(self.parse(page).stack, [])

    def test_escapes_an_ampersand_in_a_chord_name(self):
        """A bare & is the classic unescaped-markup failure; it is escaped first."""
        step = ArrangementStep(
            chord="C&F", melody="C5", voicing=make_voicing([-1, -1, 10, 10, 10, 10])
        )
        self.assertIn("C&amp;F", format_tab_html([step]))

    def test_empty_progression_renders_empty_string(self):
        """No steps means no page, not a document with an empty staff in it."""
        self.assertEqual(format_tab_html([]), "")

    def test_rejects_a_nonsensical_bar_length(self):
        """A bar of zero beats cannot be laid out, so it is a usage error."""
        with self.assertRaises(ValueError):
            format_tab_html(self.steps, beats_per_bar=0)
        with self.assertRaises(ValueError):
            format_tab_html(self.steps, measures_per_line=0)

    def test_renderer_prints_nothing_and_writes_no_file(self):
        """
        format_tab_html is a pure renderer like the rest: it returns a string, and
        only write_tab_html touches the filesystem.
        """
        before = set(os.listdir("."))
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            format_tab_html(self.steps, show_melody=True, show_mutes=True)
        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(set(os.listdir(".")), before)

    def test_write_tab_html_writes_the_page_and_returns_the_path(self):
        """The writing helper is the only function that creates a file."""
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "tab.html")
            returned = write_tab_html(self.steps, target, title="Written")
            self.assertEqual(returned, target)
            with open(target, encoding="utf-8") as handle:
                written = handle.read()
        self.assertEqual(written, format_tab_html(self.steps, title="Written"))

    def test_html_agrees_with_the_text_staff_on_the_frets(self):
        """
        The two renderings place a chord in the same column by construction, since
        they share _staff_columns. This checks they agree on what was struck.
        """
        text = format_tab_staff(self.steps)
        page = self.html
        for step in self.steps:
            for string_index in range(6):
                fret = step.voicing.frets[string_index]
                if fret < 0:
                    continue
                self.assertIn(str(fret), text)
                self.assertIn(f"<td>{fret}</td>", page)




class TestRepeatedMelody(unittest.TestCase):
    """
    A melody that repeats the previous step's pitch is played as a single note:
    the shape is struck once and the melody is re-articulated on its own. This
    matches what the Weimar transcription of "All the Things You Are" does at bars
    61-63, where one note is held across three chord changes. The voicing is still
    generated in full, so these tests check the *rendering* while `voicing` keeps
    the real shape available to a caller.
    """

    def setUp(self):
        # C4 on the B string at fret 1: the shape F-7 is voiced with in bar 61.
        self.voicing = make_voicing([-1, 1, 1, 0, 1, -1])
        self.steps = [
            ArrangementStep(
                chord="F-7", melody="C4", voicing=self.voicing, bar=0, beat=1.0
            ),
            ArrangementStep(
                chord="Bb-7", melody="C4", voicing=self.voicing,
                repeated=True, bar=1, beat=1.0,
            ),
            ArrangementStep(
                chord="Eb7", melody="C4", voicing=self.voicing,
                repeated=True, bar=2, beat=1.0,
            ),
        ]

    def test_engine_marks_a_repeated_melody(self):
        """arrange_progression flags every step after the first on the same pitch."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("D5", "m7", "Dm7"), ("F5", "maj7", "Fmaj7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, True, False])

    def test_engine_does_not_flag_a_moving_melody(self):
        """A step whose melody moves is not a repeat, even on the same chord."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("F5", "m7", "Dm7")]
        )
        self.assertFalse(any(step.repeated for step in steps))

    def test_a_run_of_repeats_is_all_flagged(self):
        """Four notes on the same pitch: the first is struck, the next three repeat."""
        progression = [("C4", "m7", "Dm7")] * 4
        steps = VoiceLeadingEngine.arrange_progression(progression)
        self.assertEqual([step.repeated for step in steps], [False, True, True, True])

    def test_engine_does_not_flag_a_repeat_across_a_chord_change(self):
        """
        A held note under a new chord is not a hold: the ringing voices belong to the
        chord the hold started on, so the step is re-harmonised and struck in full.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C4", "m7", "F-7"), ("C4", "m7", "Bb-7"), ("C4", "7", "Eb7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, False, False])

    def test_engine_still_holds_a_repeat_under_one_chord(self):
        """
        The flip side: a repeat that is not also a chord change is still a hold. This
        is the case that leaves the shape ringing rather than re-fingering it.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C4", "7", "Eb7"), ("C4", "7", "Eb7"), ("C4", "7", "Eb7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, True, True])

    def test_engine_compares_harmony_not_the_chord_spelling(self):
        """
        `D-7` and `Dm7` are the same chord written two ways, so a note repeating
        across that change is still a hold. Compared as (root, quality), not as text.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C4", "m7", "D-7"), ("C4", "m7", "Dm7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, True])

    def test_repeat_across_a_chord_change_is_reharmonised(self):
        """
        A melody repeating is a hold only while the harmony under it is unchanged.
        Across a chord change the ringing voices belong to the chord the hold began
        on, so the step is sounded in full and the renderers show the whole shape.
        """
        chords = ["F-7", "Bb-7", "Eb7", "Eb7"]
        steps = [
            ArrangementStep(
                chord=chord, melody="C4", voicing=self.voicing,
                # Only the second Eb7 is a hold: a repeat under the same chord.
                repeated=(index == 2),
                bar=index, beat=1.0,
            )
            for index, chord in enumerate(chords[1:])
        ]
        lines = format_progression(steps).split("\n")
        # The two chord changes are sounded in full, so the renderers show the shape.
        for line, chord in zip(lines[:2], chords[1:3]):
            self.assertNotIn("melody repeated", line, chord)
        # Only the last is a hold: the Eb7 repeating under the Eb7.
        self.assertIn("melody repeated", lines[-1])
        self.assertEqual(
            lines[-1].split()[-1].split("-"), ["", "", "", "", "1", ""]
        )

    def test_voicing_is_unchanged_so_the_shape_is_still_available(self):
        """The flag is presentational: the step keeps its full drop-2 voicing."""
        self.assertEqual(self.steps[1].tab_line(), "x-1-1-0-1-x")

    def test_one_line_tab_plays_a_single_note(self):
        """Only the melody string carries a fret; the rest are blank, not 'x'."""
        line = format_progression(self.steps).split("\n")[1]
        self.assertEqual(line.split()[-1].split("-"), ["", "", "", "", "1", ""])

    def test_annotation_says_the_note_repeats(self):
        """The chord label alone would imply a full shape, so the line is annotated."""
        self.assertIn(
            "melody repeated", format_progression(self.steps).split("\n")[1]
        )

    def test_vertical_block_leaves_every_other_string_empty(self):
        """The six-line block strikes the melody string and leaves the rest blank."""
        block = format_progression(self.steps, vertical=True).split("\n\n")[1]
        self.assertIn("B| 1-|", block)
        self.assertEqual(block.count("|  -|"), 5)
        self.assertNotIn("x", block)

    def test_staff_shows_the_soprano_only(self):
        """On the staff the other strings are left blank, as for a held voice."""
        string_lines = format_tab_staff(self.steps).split("\n")[-6:]
        # The B line carries the melody on all three steps; the G line only on the
        # first, because the repeats strike the melody alone.
        self.assertEqual(string_lines[1].count("1"), 3)
        self.assertEqual(string_lines[2].count("0"), 1)

    def test_staff_still_strikes_a_repeated_step_under_collapse(self):
        """
        Collapse would normally print nothing for an unchanged shape, but a
        repeated melody is re-articulated, so the step must still strike.
        """
        string_lines = format_tab_staff(self.steps, collapse=True).split("\n")[-6:]
        self.assertEqual(string_lines[1].count("1"), 3)

    def test_html_shows_the_soprano_only(self):
        """The HTML table leaves the other strings empty, not marked x."""
        page = format_tab_html(self.steps)
        measures = page.split('<div class="measure">')[1:]
        self.assertEqual(measures[0].count("<td>1</td>"), 3)
        self.assertEqual(measures[1].count('class="repeat">1<'), 1)
        self.assertIn('<td class="repeat"></td>', measures[1])

    def test_html_marks_a_repeated_column(self):
        """
        The muted strings are drawn faintly, so without a marker a repeated note
        would read as a mostly-empty column rather than a deliberate single note.
        """
        page = format_tab_html(self.steps)
        measures = page.split('<div class="measure">')[1:]
        self.assertNotIn("repeat", measures[0])
        self.assertIn("repeat", measures[1])

    def test_melody_only_repeat_stays_a_single_fret(self):
        """
        An NC step has no inner voices to hold, so it is never marked as a repeat
        and keeps spelling its own mutes.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "NC", "NC"), ("D5", "NC", "NC")]
        )
        self.assertFalse(any(step.repeated for step in steps))
        self.assertTrue(all(step.melody_only for step in steps))


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
        The README, the tests and wjazzd all spell these as `from arranger import`,
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
        tabstaff imports arranger, so importing it first re-enters arranger while
        it is being set up. The lazy __getattr__ is what keeps that from failing, as
        a bottom-of-file import would have.
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
        `from arranger import *` used to export every public name, before the lazy
        __getattr__ began hiding the re-exported ones. __all__ restores that, and
        this keeps it honest: every listed name must resolve, and every public name
        defined in the module must be listed.
        """
        import arranger

        for name in arranger.__all__:
            self.assertTrue(hasattr(arranger, name), f"{name} in __all__ but missing")
        defined = {n for n in vars(arranger) if not n.startswith("_")}
        # Names bound by imports rather than defined by this module - the typing
        # aliases, musthe's classes, and the stdlib modules - are not API.
        ignored = {
            "Any",
            "Chord",
            "Container",
            "Dict",
            "Interval",
            "List",
            "Note",
            "Optional",
            "Sequence",
            "Tuple",
            "TYPE_CHECKING",
            "annotations",
            "dataclass",
            "importlib",
            "re",
            "sys",
        }
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


class TestStaffBarlineAlignment(unittest.TestCase):
    """Tests that every row of the ASCII staff is ruled identically.

    The chord, melody and string rows are drawn on one shared column grid, so a
    barline is only legible if it lands in the same column on all of them. Two
    separate defects made it not: the chord and melody rows began with three
    spaces rather than a barline, and rstrip() trimmed their trailing blank
    columns so they ended short of the string rows.
    """

    def build(self, measures_per_line=1, bars=4):
        """A timed progression of `bars` one-bar chords, to force real barlines."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D", "m7", "Dm7"), ("G", "7", "G7"),
             ("C", "maj7", "Cmaj7"), ("F", "m7", "Fm7")][:bars]
        )
        for index, step in enumerate(steps):
            step.bar, step.beat, step.duration = index + 1, 1.0, 4.0
        return format_tab_staff(
            steps, show_melody=True, measures_per_line=measures_per_line
        )

    def test_every_row_is_the_same_width(self):
        """A short chord row is what made the staff look unaligned."""
        lines = self.build().split("\n")
        self.assertEqual(len({len(line) for line in lines}), 1, lines)

    def test_barlines_land_in_the_same_column_on_every_row(self):
        """The barline positions are compared against the string rows."""
        lines = self.build().split("\n")
        columns = [[i for i, c in enumerate(line) if c == "|"] for line in lines]
        for line, positions in zip(lines[1:], columns[1:]):
            self.assertEqual(positions, columns[2], f"misaligned: {line!r}")

    def test_chord_and_melody_rows_are_both_end_bounded(self):
        """
        A chord row with no leading barline reads as a caption above the staff
        rather than as part of it, so both ends must be ruled.
        """
        lines = self.build().split("\n")
        for line in lines[:2]:
            self.assertTrue(line.startswith("  |"), repr(line))
            self.assertTrue(line.endswith("|"), repr(line))

    def test_sparse_barlines_still_line_up(self):
        """The default four bars per line draws fewer barlines, not misaligned ones."""
        lines = self.build(measures_per_line=4).split("\n")
        self.assertEqual(len({len(line) for line in lines}), 1, lines)
        positions = [[i for i, c in enumerate(line) if c == "|"] for line in lines]
        for row in positions[1:]:
            self.assertEqual(row, positions[2])
