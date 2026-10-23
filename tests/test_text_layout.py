"""The pure string layout an annotation is broken into.

`annotation` composes the words a step's explanation is made of; `text_layout`
decides where those words break. Nothing here reads a step or a chord - the input is
a string and a column count - so the layout is pinned on its own, which is what makes
"a line ends where a clause does" a statement about the breaker rather than a claim
about one arrangement's tabs.
"""

import unittest

from arranger.text_layout import annotation_lines


class TestTheLineBreaker(unittest.TestCase):
    """Where a line ends, and what happens to text too wide for the room."""

    def test_an_annotation_that_fits_is_one_line(self):
        """Room to spare means no break at all: the text comes back whole."""
        self.assertEqual(
            annotation_lines("(harmony under b7)", 100), ["(harmony under b7)"]
        )

    def test_a_clause_boundary_is_the_break_point(self):
        """The ` - ` separator ends the line it was on rather than being dropped.

        A break stands in for the space it removes, so the marker moves to the end of
        the line and the next clause begins the following one - which is what stops a
        line ending on the last word of a list.
        """
        self.assertEqual(
            annotation_lines(
                "(harmony under b7 - the chord tone it leaves out is Root)", 30
            ),
            ["(harmony under b7 -", "the chord tone it leaves out", "is Root)"],
        )

    def test_a_clause_wider_than_a_line_wraps_at_its_own_spaces(self):
        """A clause with no line of its own is broken between whole words."""
        self.assertEqual(
            annotation_lines(
                "(harmony under b7 - sounding: C b7, Eb b3, G 5, Bb Root)", 24
            ),
            ["(harmony under b7 -", "sounding: C b7, Eb b3, G", "5, Bb Root)"],
        )

    def test_a_word_wider_than_the_room_overflows_rather_than_being_cut(self):
        """Cutting a word would put a syllable on each line, so it is left whole."""
        word = "(verylongwordthatcannotbebroken)"
        self.assertEqual(annotation_lines(word, 10), [word])

    def test_the_bass_parenthetical_opens_the_next_line_with_its_bracket(self):
        """A second parenthetical starts a line rather than closing the first one."""
        self.assertEqual(
            annotation_lines("(no chord - melody alone) (bass: C, root)", 20),
            ["(no chord -", "melody alone)", "(bass: C, root)"],
        )

    def test_the_break_marker_opens_the_next_line_at_the_margin(self):
        """A line already at the margin cannot carry the `-` too.

        The same three characters are printed, one newline later, so no line runs
        past the width the caller asked for.
        """
        self.assertEqual(
            annotation_lines("(aaaaaaaaaa - bbb)", 12), ["(aaaaaaaaaa", "- bbb)"]
        )


if __name__ == "__main__":
    unittest.main()
