import io
import unittest
from contextlib import redirect_stdout

from arranger import (
    ArrangementStep,
    Voicing,
    VoiceLeadingEngine,
    format_progression,
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
        self.major = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")]
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

