import unittest
from musthe import Note
from arranger import ChordParser


class TestChordParser(unittest.TestCase):
    """Tests for parsing chord names and mapping melodic degrees."""

    def test_parse_simple_roots_and_qualities(self):
        """Should parse natural, sharp, and flat roots with standard jazz qualities."""
        cases = [
            ("Cmaj7", ("C", "maj7")),
            ("Dm7", ("D", "m7")),
            ("G7", ("G", "7")),
            ("Am7b5", ("A", "m7b5")),
            ("F#m7b5", ("F#", "m7b5")),
            ("Bb7", ("Bb", "7")),
            ("Ebmaj7", ("Eb", "maj7")),
            ("Abdim7", ("Ab", "dim7")),
            ("C#7alt", ("C#", "7alt")),
            ("G7b9", ("G", "7b9")),
            ("Cm6", ("Cm", "6")),  # wait: "Cm" or "C" + "m6"? Let's test
        ]
        # For Cm6: Root is C, quality is m6
        root, qual = ChordParser.parse_chord_name("Cm6")
        self.assertEqual(root, "C")
        self.assertEqual(qual, "m6")

        root, qual = ChordParser.parse_chord_name("Dm7b5")
        self.assertEqual(root, "D")
        self.assertEqual(qual, "m7b5")

        root, qual = ChordParser.parse_chord_name("F#m7b5")
        self.assertEqual(root, "F#")
        self.assertEqual(qual, "m7b5")

        root, qual = ChordParser.parse_chord_name("Bb7b9")
        self.assertEqual(root, "Bb")
        self.assertEqual(qual, "7b9")

    def test_parse_empty_or_invalid(self):
        """Empty or unparseable chord names should return (None, None)."""
        self.assertEqual(ChordParser.parse_chord_name(""), (None, None))
        self.assertEqual(ChordParser.parse_chord_name("   "), (None, None))
        self.assertEqual(ChordParser.parse_chord_name(None), (None, None))
        self.assertEqual(ChordParser.parse_chord_name("X7"), (None, None))

    def test_get_melody_degree(self):
        """Should return correct pitch interval relative to root (0-11)."""
        # Over D root (D=0, Eb=1, E=2, F=3, F#=4, G=5, Ab=6, A=7, Bb=8, B=9, C=10, C#=11):
        self.assertEqual(ChordParser.get_melody_degree("D", Note("D5")), 0)   # Root
        self.assertEqual(ChordParser.get_melody_degree("D", Note("F5")), 3)   # Minor 3rd
        self.assertEqual(ChordParser.get_melody_degree("D", Note("Ab5")), 6)  # Flat 5th
        self.assertEqual(ChordParser.get_melody_degree("D", Note("C5")), 10)  # Minor 7th

        # Over G root:
        self.assertEqual(ChordParser.get_melody_degree("G", Note("B4")), 4)   # Major 3rd
        self.assertEqual(ChordParser.get_melody_degree("G", Note("F5")), 10)  # Flat 7th
        self.assertEqual(ChordParser.get_melody_degree("G", Note("Ab5")), 1)  # Flat 9th


if __name__ == "__main__":
    unittest.main()
