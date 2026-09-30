import unittest

from musthe import Note

from arranger import ChordParser


class TestChordParser(unittest.TestCase):
    """Tests for parsing chord names and mapping melodic degrees."""

    def test_parse_simple_roots_and_qualities(self):
        """Should parse natural, sharp, and flat roots with standard jazz qualities."""
        # Each case is (name, (root, quality)) as parse_chord_name should read it.
        # The Cm6 row is the interesting one: "Cm" could be read as a C minor triad
        # whose root is spelled "Cm", but the regex takes the letter as the root and
        # leaves "m6" as the quality, which is how the library spells it.
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
            ("Bb7b9", ("Bb", "7b9")),
            ("Cm6", ("C", "m6")),
        ]
        for name, expected in cases:
            with self.subTest(chord=name):
                self.assertEqual(ChordParser.parse_chord_name(name), expected)

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


class TestChordToneSets(unittest.TestCase):
    """Tests for quality normalisation and the full chord-tone oracle."""

    def test_canonical_quality_resolves_aliases_case_sensitively(self):
        """Aliases map to their canonical key, and M7 must not be folded into m7."""
        cases = [
            ("M7", "maj7"),
            ("m7", "m7"),
            ("min7", "m7"),
            ("dom7", "7"),
            ("half-dim", "m7b5"),
            ("ø7", "m7b5"),
            ("°7", "dim7"),
            ("dim", "dim7"),
            ("min6", "m6"),
            ("mmaj7", "mMaj7"),
            ("minMaj7", "mMaj7"),
            ("M9", "maj9"),
            ("69", "6/9"),
            ("  m7  ", "m7"),
            # triads and suspended chords ("dim" deliberately still means dim7)
            ("M", "maj"),
            ("min", "m"),
            ("-", "m"),
            ("+", "aug"),
            ("sus", "sus4"),
            ("7sus", "7sus4"),
        ]
        for alias, expected in cases:
            self.assertEqual(ChordParser.canonical_quality(alias), expected, alias)

    def test_canonical_quality_passes_unknown_qualities_through(self):
        """Unknown qualities are returned unchanged so callers can report them."""
        self.assertEqual(ChordParser.canonical_quality("not-a-chord"), "not-a-chord")
        self.assertEqual(ChordParser.canonical_quality(""), "")
        self.assertEqual(ChordParser.canonical_quality(None), "")

    def test_get_chord_tones_relative_to_root(self):
        """Without a chord name the tones are pitch classes relative to the root."""
        self.assertEqual(ChordParser.get_chord_tones("maj7"), (0, 4, 7, 11))
        self.assertEqual(ChordParser.get_chord_tones("m7"), (0, 3, 7, 10))

    def test_get_chord_tones_absolute_with_chord_name(self):
        """With a chord name the pitch classes are absolute."""
        self.assertEqual(ChordParser.get_chord_tones("maj7", "Cmaj7"), (0, 4, 7, 11))
        self.assertEqual(ChordParser.get_chord_tones("maj7", "Dmaj7"), (2, 6, 9, 1))
        # The root is included even though a 7b9 is voiced rootless
        self.assertEqual(ChordParser.get_chord_tones("7b9", "G7b9"), (7, 8, 11, 2, 5))

    def test_get_chord_tones_unknown_quality_is_empty(self):
        """An unsupported quality has no known tones."""
        self.assertEqual(ChordParser.get_chord_tones("not-a-chord"), ())
        self.assertEqual(ChordParser.get_chord_tones("not-a-chord", "Cnot-a-chord"), ())


class TestWidenedQualityVocabulary(unittest.TestCase):
    """Tone sets for the triads, sus, added-note and altered qualities."""

    NEW_QUALITIES = [
        ("maj", (0, 4, 7)),
        ("m", (0, 3, 7)),
        ("aug", (0, 4, 8)),
        ("sus4", (0, 5, 7)),
        ("sus2", (0, 2, 7)),
        ("add9", (0, 2, 4, 7)),
        ("madd9", (0, 2, 3, 7)),
        ("7sus4", (0, 5, 7, 10)),
        ("7b5", (0, 4, 6, 10)),
        ("7#5", (0, 4, 8, 10)),
        ("7#11", (0, 4, 6, 7, 10)),
        ("7b13", (0, 4, 7, 8, 10)),
        ("maj7#11", (0, 4, 6, 7, 11)),
        ("m9b5", (0, 2, 3, 6, 10)),
    ]

    def test_relative_tone_sets(self):
        for quality, tones in self.NEW_QUALITIES:
            self.assertEqual(ChordParser.get_chord_tones(quality), tones, quality)

    def test_absolute_tone_sets(self):
        self.assertEqual(ChordParser.get_chord_tones("7sus4", "G7sus4"), (7, 0, 2, 5))
        self.assertEqual(ChordParser.get_chord_tones("m9b5", "Am9b5"), (9, 11, 0, 3, 7))
        self.assertEqual(ChordParser.get_chord_tones("aug", "Caug"), (0, 4, 8))

    def test_bare_major_chord_symbol_is_not_assumed(self):
        """A name with no written quality ('C') is not guessed to be a major
        triad; the caller spells it, e.g. 'Cmaj' or 'M'."""
        self.assertEqual(ChordParser.parse_chord_name("C"), ("C", ""))
        self.assertEqual(ChordParser.get_chord_tones(""), ())
        self.assertEqual(ChordParser.get_chord_tones("", "C"), ())


if __name__ == "__main__":
    unittest.main()
