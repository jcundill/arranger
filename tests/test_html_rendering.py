"""The HTML tab staff: the same music as tagged columns.

`format_tab_html` and `write_tab_html` are checked here for what a reader sees - one cell
per string per column, the legend, and the tags balanced - rather than for the exact
markup, which the staff tests already cover as text.
"""

import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser

from arranger import (
    ArrangementStep,
    VoiceLeadingEngine,
    format_tab_html,
    format_tab_staff,
    write_tab_html,
)
from tests.support import make_voicing


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
        # page has three systems: two of music and a third holding the bar that
        # `_staff_columns` pads the last note out to. The numbering still counts
        # from 1 and still advances by `measures_per_line` per system.
        timed = self.engine.arrange_progression(
            [("D5", "m7", "Dm7")] * 16 + [("C5", "maj7", "Cmaj7")] * 16
        )
        for index, step in enumerate(timed):
            step.bar, step.beat = index // 4, 1.0
        page = format_tab_html(timed, measures_per_line=4)
        numbers = re.findall(r'<span class="barnum">(\d+)</span>', page)
        self.assertEqual(numbers, ["1", "5", "9"])

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

    def test_a_navigation_sign_is_labelled_on_its_measure(self):
        """A Segno, Coda or D.C. is a label on the bar, like a volta number.

        It shares `_NAVIGATION_LABELS` with the ASCII staff, so the page and the text
        cannot disagree about what a sign says.
        """
        from headxml import BarMarker

        # The staff reads a step's bar from its own onset, so a bare arrangement starts
        # at bar 0 and the marker for bar 1 would land on the second measure. A head's
        # steps always carry bar 1, so the test states it too.
        for index, step in enumerate(self.steps):
            step.bar = 1
            step.beat = 1.0 + index
            step.duration = 0.25
        page = format_tab_html(
            self.steps,
            markers=[
                BarMarker(bar=1, kind="segno", written_bar=1, name="segno"),
                BarMarker(bar=2, kind="da_segno_al_coda", written_bar=2),
            ],
        )
        self.assertIn('class="nav"', page)
        self.assertIn(">Segno<", page)
        self.assertIn(">D.S.<", page)
