"""The HTML tab staff: an inline SVG score modelled on TuxGuitar's `diag.svg`.

`format_tab_html` and `write_tab_html` are checked here for what a reader sees
- one inline SVG score with measure cards, six staff lines, tab numbers on
  string lines, red bar numbers, black barlines, and fretboard chord diagrams
  above the staff - rather than for the exact markup, which is subject to
  change as the renderer evolves.
"""

import os
import tempfile
import unittest
from html.parser import HTMLParser

from arranger import (
    VoiceLeadingEngine,
    format_tab_html,
    write_tab_html,
)
from arranger.step_types import ArrangementStep
from tests.support import make_step, make_voicing

# SVG elements that are self-closing in the renderer output. The HTMLParser
# does not know SVG's `/>` syntax, so these must be treated as void tags for
# the tag-balance check to pass.
_SVG_VOID = {"rect", "path", "line", "circle", "ellipse", "polygon", "polyline"}


class _TagBalance(HTMLParser):
    """Minimal well-formedness checker: collects unbalanced and unclosed tags.

    Handles both HTML and inline SVG elements. SVG self-closing elements
    (rect, path, ...) are treated as void so they never need a closing tag.
    """

    VOID = {"meta", "br", "img", "link", "hr", "input"} | _SVG_VOID

    def __init__(self):
        super().__init__()
        self.stack = []
        self.mismatched = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        # Self-closing SVG elements (rect, path, ...) trigger endtag even
        # though no starttag was pushed; ignore them.
        if tag in self.VOID:
            return
        if not self.stack or self.stack.pop() != tag:
            self.mismatched.append(tag)


class TestHtmlTab(unittest.TestCase):
    """Tests the HTML page renderer, format_tab_html()."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.steps = self.engine.arrange_progression(
            [("D5", "Dm7"), ("B4", "G7"), ("C5", "Cmaj7")],
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
        """No external stylesheet, script or image: the file can be opened from disk
        or emailed with nothing else. This is why the stylesheet is inlined."""
        for external in ("<link", "<script", "src=", "https://"):
            self.assertNotIn(external, self.html, external)
        # `http://` appears only in the SVG xmlns attribute, which is fine.
        self.assertNotIn("src=", self.html)

    def test_title_and_subtitle_are_shown(self):
        """The heading carries the title, and the subtitle line when given."""
        self.assertIn("<title>Test</title>", self.html)
        self.assertIn('<p class="sub">A subtitle</p>', self.html)

    def test_subtitle_is_omitted_when_empty(self):
        """No subtitle means no empty element left behind."""
        self.assertNotIn('class="sub"', format_tab_html(self.steps))

    def test_page_has_one_inline_svg(self):
        """The page contains exactly one inline SVG score."""
        self.assertEqual(self.html.count("<svg"), 1)
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', self.html)

    def test_svg_has_white_background(self):
        """The SVG carries a white background rect."""
        self.assertIn('fill="#ffffff" stroke="none"/>', self.html)

    def test_svg_has_title_and_subtitle(self):
        """Title and subtitle text appear inside the SVG, centred."""
        self.assertIn(
            'text-anchor="middle" font-family="Default" '
            'font-size="16.0" fill="#000000">Test</text>',
            self.html,
        )
        self.assertIn(
            'text-anchor="middle" font-family="Default" '
            'font-size="12.0" fill="#000000">A subtitle</text>',
            self.html,
        )

    def test_measure_groups(self):
        """One measure group per measure, each translated to its position."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step])
        self.assertIn('<g transform="translate(20.0, 60.0)">', page)

    def test_staff_has_six_lines(self):
        """Each measure card has six staff lines at diag.svg positions."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step])
        for y in (67.0, 77.0, 87.0, 97.0, 107.0, 117.0):
            self.assertIn(f"M 0.0 {y:.1f} L 135.5 {y:.1f}", page)

    def test_bar_numbers_are_red(self):
        """Bar numbers appear in red above the staff."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step])
        self.assertIn(
            '<text x="1.0" y="62.0" text-anchor="start" font-family="Default" '
            'font-size="10.0" fill="#ff0000">1</text>',
            page,
        )

    def test_barlines_at_measure_edges(self):
        """Black barlines on the staff at each measure's left and right edge."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step])
        # Barlines cross the staff (y=67-117).
        self.assertIn(
            '<path d="M 0.0 67.0 L 0.0 117.0" fill="#000000" stroke="#000000" stroke-width="1.0"/>',
            page,
        )
        self.assertIn(
            '<path d="M 135.5 67.0 L 135.5 117.0" fill="#000000" stroke="#000000" stroke-width="1.0"/>',
            page,
        )

    def test_tab_numbers_on_string_lines(self):
        """Fretted positions show as numbers on their string line."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")  # x-x-0-2-3-1
        page = format_tab_html([step])
        # Beat 0 is clamped to half a diagram width (21.5) so the tab numbers
        # line up vertically with the diagram centre above them.
        self.assertIn('text x="21.5" y="100.8"', page)
        self.assertIn('>0</text>', page)
        self.assertIn('text x="21.5" y="90.8"', page)
        self.assertIn('>2</text>', page)
        self.assertIn('text x="21.5" y="80.8"', page)
        self.assertIn('>1</text>', page)
        # String index 5 (high E, fret 1): line_y = 117 - 50 = 67, y = 70.8
        self.assertIn('text x="21.5" y="70.8"', page)
        self.assertIn('>1</text>', page)

    def test_empty_progression_returns_empty_string(self):
        """No steps means no output."""
        self.assertEqual(format_tab_html([]), "")

    def test_write_tab_html_creates_file(self):
        """`write_tab_html` writes the HTML to a file and returns the path."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            result = write_tab_html([step], path)
            self.assertEqual(result, path)
            with open(path) as f:
                content = f.read()
            self.assertIn('<svg ', content)
            self.assertIn('<rect x="0.0" y="0.0" width="135.5"', content)
        finally:
            os.unlink(path)

    def test_beat_markers_under_staff_4_4(self):
        """Beat markers 1-4 sit under the staff at their beat positions.

        Beat 1 is clamped to half a diagram width (21.5) so it does not sit
        under the left barline but lines up with a diagram/tab number on beat 1.
        All markers are middle-anchored like the diagrams above them.
        """
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step], beats_per_bar=4)
        self.assertIn(
            '<text x="21.5" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">1</text>',
            page,
        )
        self.assertIn(
            '<text x="55.4" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">2</text>',
            page,
        )
        self.assertIn(
            '<text x="89.2" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">3</text>',
            page,
        )
        self.assertIn(
            '<text x="123.1" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">4</text>',
            page,
        )

    def test_beat_markers_2_2(self):
        """Cut time shows markers 1 and 2 under the staff."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step], beats_per_bar=2)
        self.assertIn(
            '<text x="21.5" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">1</text>',
            page,
        )
        self.assertIn(
            '<text x="61.8" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">2</text>',
            page,
        )
        self.assertNotIn('y="135.0">3</text>', page)
        self.assertNotIn('y="135.0">4</text>', page)

    def test_beat_markers_3_4(self):
        """Three-quarter time shows markers 1, 2, 3 under the staff."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = format_tab_html([step], beats_per_bar=3)
        self.assertIn(
            '<text x="21.5" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">1</text>',
            page,
        )
        self.assertIn(
            '<text x="57.5" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">2</text>',
            page,
        )
        self.assertIn(
            '<text x="93.5" y="135.0" text-anchor="middle" font-family="Default" '
            'font-size="9.0" fill="#000000">3</text>',
            page,
        )
        self.assertNotIn('y="135.0">4</text>', page)


class TestFretboardDiagram(unittest.TestCase):
    """Fretboard chord diagrams on the SVG staff."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def _page(self, steps, **kwargs):
        return format_tab_html(steps, **kwargs)

    def test_diagram_on_chord_change(self):
        """A multi-note chord step gets a fretboard diagram where it first strikes."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = self._page([step])
        # Diagram centred on beat 0, clamped to 21.5 -> x0 = 0.0.
        self.assertIn('<rect x="0.0" y="0.0" width="43.0" height="42.0"', page)

    def test_diagram_on_every_fretboard_shape_in_bar(self):
        """A bar with several different fretted shapes gets a diagram for each."""
        v1 = make_voicing([-1, -1, 0, 2, 3, 1])   # Dm7 at beat 1
        v2 = make_voicing([-1, 3, 3, 2, 3, -1])   # G7 at beat 2
        v3 = make_voicing([-1, -1, 9, 9, 8, 8])   # Cmaj7 at beat 3
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=v1, bar=0, beat=1.0),
            ArrangementStep(chord="G7", melody="B4", voicing=v2, bar=0, beat=2.0),
            ArrangementStep(chord="Cmaj7", melody="C5", voicing=v3, bar=0, beat=3.0),
        ]
        page = self._page(steps)
        # One diagram card per distinct fretted shape in the bar.
        self.assertEqual(page.count('width="43.0" height="42.0"'), 3)
        self.assertIn('fill="#000000">Dm7</text>', page)
        self.assertIn('fill="#000000">G7</text>', page)
        self.assertIn('fill="#000000">Cmaj7</text>', page)

    def test_diagram_on_same_chord_different_position(self):
        """The same chord at two neck positions gets two diagrams."""
        v1 = make_voicing([-1, -1, 0, 2, 3, 1])   # Dm7 open position
        v2 = make_voicing([-1, 5, 7, 6, 5, -1])   # Dm7 fifth position
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=v1, bar=0, beat=1.0),
            ArrangementStep(chord="Dm7", melody="A4", voicing=v2, bar=0, beat=3.0),
        ]
        page = self._page(steps)
        # Same chord, different frets -> two diagrams.
        self.assertEqual(page.count('width="43.0" height="42.0"'), 2)

    def test_measure_wider_when_more_diagrams(self):
        """A bar with three diagrams is wider than one with none."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        narrow = self._page([step])
        v1 = make_voicing([-1, -1, 0, 2, 3, 1])
        v2 = make_voicing([-1, 3, 3, 2, 3, -1])
        v3 = make_voicing([-1, -1, 9, 9, 8, 8])
        steps = [
            ArrangementStep(chord="Dm7", melody="D5", voicing=v1, bar=0, beat=1.0),
            ArrangementStep(chord="G7", melody="B4", voicing=v2, bar=0, beat=2.0),
            ArrangementStep(chord="Cmaj7", melody="C5", voicing=v3, bar=0, beat=3.0),
        ]
        wide = self._page(steps)
        # Diagrams at beats 0, 1, 2 (adjacent): width must prevent overlap even
        # with the first diagram clamped to half a card width from the left edge.
        self.assertIn('width="282.0" height="153.0"', wide)
        self.assertIn('width="135.5" height="153.0"', narrow)

    def test_no_diagram_on_held_chord(self):
        """An unchanged shape held across columns gets no second diagram."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        held = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7", repeated=True)
        page = self._page([step, held])
        # One diagram card per measure (one measure here), held step gets none.
        self.assertEqual(page.count('width="43.0" height="42.0"'), 1)

    def test_no_diagram_on_single_note(self):
        """A single-note step gets no diagram card (needs two or more strings)."""
        step = make_step([-1, -1, -1, 5, -1, -1], chord="Dm7")
        page = self._page([step])
        self.assertNotIn('width="43.0" height="42.0"', page)

    def test_no_diagram_on_nc(self):
        """An NC step gets no diagram card."""
        step = make_step([-1, -1, -1, -1, -1, -1], chord="NC", melody=None)
        page = self._page([step])
        self.assertNotIn('width="43.0" height="42.0"', page)

    def test_diagram_has_first_fret_label(self):
        """A diagram starting above fret 0 gets a black first-fret index."""
        step = make_step([-1, -1, -1, -1, 7, 8], chord="G7")  # x-x-x-x-7-8
        page = self._page([step])
        self.assertIn('font-size="8.0" fill="#000000">7</text>', page)

    def test_diagram_dots_at_correct_frets(self):
        """Dots sit at the fret matching their position."""
        step = make_step([-1, -1, -1, -1, 7, 8], chord="G7")  # x-x-x-x-7-8
        page = self._page([step])
        # Diagram x0 = 0.0; first_fret = 7; dot y = 9 + (fret - 7) * 6.
        # Fret 7 at string index 4 (x=33): M 30.5 9.0
        # Fret 8 at string index 5 (x=38): M 35.5 15.0
        self.assertIn("M 30.5 9.0", page)
        self.assertIn("M 35.5 15.0", page)

    def test_diagram_rect_background(self):
        """Each measure has a white card background."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = self._page([step])
        self.assertIn('<rect x="0.0" y="0.0" width="135.5" height="153.0"', page)

    def test_diagram_fret_lines(self):
        """Each diagram card has six horizontal fret lines."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = self._page([step])
        self.assertIn('stroke="#d6d6d6"', page)

    def test_diagram_string_lines(self):
        """Each diagram card has six vertical string lines."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = self._page([step])
        # Diagram x0 = 0.0; strings at x0 + 13+i*5 = 13, 18, ..., 38.
        self.assertIn("M 13.0 6.0 L 13.0 36.0", page)
        self.assertIn("M 38.0 6.0 L 38.0 36.0", page)

    def test_diagram_x_marks_on_muted_strings(self):
        """Muted strings get an X at the nut."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")  # x-x-0-2-3-1
        page = self._page([step])
        # Diagram x0 = 0.0; strings 0 and 1 are muted at x=13 and x=18.
        # X marks span x-2 to x+2: string 0 at 11-15, string 1 at 16-20.
        self.assertIn("M 11.0 0.0 L 15.0 4.0", page)
        self.assertIn("M 15.0 0.0 L 11.0 4.0 Z", page)
        self.assertIn("M 16.0 0.0 L 20.0 4.0", page)
        self.assertIn("M 20.0 0.0 L 16.0 4.0 Z", page)

    def test_diagram_chord_name_below_card(self):
        """The chord name appears below the diagram card."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = self._page([step])
        # Diagram x0 = 0.0; name at x0 + 2 = 2.0.
        self.assertIn(
            'text x="2.0" y="49.5" text-anchor="start" font-family="Default" '
            'font-size="10.0" fill="#000000">Dm7</text>',
            page,
        )

    def test_diagram_above_staff(self):
        """The diagram card sits above the staff lines."""
        step = make_step([-1, -1, 0, 2, 3, 1], chord="Dm7")
        page = self._page([step])
        self.assertIn('<rect x="0.0" y="0.0" width="43.0" height="42.0"', page)
        self.assertIn("M 0.0 67.0 L 135.5 67.0", page)
