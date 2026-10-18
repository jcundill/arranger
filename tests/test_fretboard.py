import unittest

from musthe import Note

from arranger import STANDARD_TUNING, GuitarFretboard


class TestGuitarFretboard(unittest.TestCase):
    """Tests for guitar physical mapping and open string tuning."""

    def test_standard_tuning_pitches(self):
        """Verify the 6 open strings correspond to E2, A2, D3, G3, B3, E4."""
        expected_pitches = ["E2", "A2", "D3", "G3", "B3", "E4"]
        actual_pitches = [n.scientific_notation() for n in STANDARD_TUNING]
        self.assertEqual(actual_pitches, expected_pitches)

    def test_open_string_frets(self):
        """Open strings should resolve to fret 0 on their respective strings."""
        for string_idx, open_note in enumerate(STANDARD_TUNING):
            fret = GuitarFretboard.note_to_fret(string_idx, open_note)
            self.assertEqual(fret, 0, f"Expected fret 0 for {open_note} on string {string_idx}")

    def test_octave_frets(self):
        """An octave above the open string should resolve to fret 12."""
        octave_notes = [
            Note("E3"), Note("A3"), Note("D4"),
            Note("G4"), Note("B4"), Note("E5")
        ]
        for string_idx, note in enumerate(octave_notes):
            fret = GuitarFretboard.note_to_fret(string_idx, note)
            self.assertEqual(fret, 12, f"Expected fret 12 for {note} on string {string_idx}")

    def test_high_e_string_frets(self):
        """Verify common melody notes on High E string (string 5)."""
        test_cases = [
            ("E4", 0),
            ("F4", 1),
            ("G4", 3),
            ("A4", 5),
            ("B4", 7),
            ("C5", 8),
            ("D5", 10),
            ("Eb5", 11),
            ("E5", 12),
            ("F5", 13),
            ("G5", 15),
        ]
        for note_str, expected_fret in test_cases:
            fret = GuitarFretboard.note_to_fret(5, Note(note_str))
            self.assertEqual(fret, expected_fret, f"Fret mismatch for {note_str} on high E string")

    def test_out_of_range_notes(self):
        """Notes below open pitch or above fret 18 should return -1."""
        # Lower than open High E (E4)
        self.assertEqual(GuitarFretboard.note_to_fret(5, Note("D4")), -1)
        self.assertEqual(GuitarFretboard.note_to_fret(5, Note("C4")), -1)
        # Higher than fret 18 (Bb5 = fret 18, B5 = fret 19)
        self.assertEqual(GuitarFretboard.note_to_fret(5, Note("B5")), -1)
        # Invalid string indices
        self.assertEqual(GuitarFretboard.note_to_fret(-1, Note("E4")), -1)
        self.assertEqual(GuitarFretboard.note_to_fret(6, Note("E4")), -1)

    def test_fret_to_midi(self):
        """Verify conversion from string and fret back to MIDI note number."""
        # Open Low E (E2) is MIDI 40
        self.assertEqual(GuitarFretboard.fret_to_midi(0, 0), 40)
        # Open High E (E4) is MIDI 64
        self.assertEqual(GuitarFretboard.fret_to_midi(5, 0), 64)
        # High E fret 12 (E5) is MIDI 76
        self.assertEqual(GuitarFretboard.fret_to_midi(5, 12), 76)
        # Invalid fret or string
        self.assertEqual(GuitarFretboard.fret_to_midi(5, -1), -1)
        self.assertEqual(GuitarFretboard.fret_to_midi(10, 5), -1)


if __name__ == "__main__":
    unittest.main()
