import unittest
from arranger import VoiceLeadingEngine, ArrangementStep


class TestProgressions(unittest.TestCase):
    """End-to-end tests for arranging harmonic progressions in minor and major keys."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_minor_ii_v_i_progression(self):
        """
        Verify the staple minor ii-V-i progression in C Minor:
        Dm7b5 -> G7b9 -> Cm7
        Melody: F5 -> F5 -> Eb5
        """
        progression = [
            ("F5", "m7b5", "Dm7b5"),
            ("F5", "7b9", "G7b9"),
            ("Eb5", "m7", "Cm7")
        ]
        result = self.engine.arrange_progression(progression)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].chord, "Dm7b5")
        self.assertEqual(result[1].chord, "G7b9")
        self.assertEqual(result[2].chord, "Cm7")

        # Verify smooth physical voice leading: movements between chords should be small
        dist_1_to_2 = self.engine.calculate_voice_leading_distance(result[0].voicing, result[1].voicing)
        dist_2_to_3 = self.engine.calculate_voice_leading_distance(result[1].voicing, result[2].voicing)

        # In this cadence, G7b9 is only 1 fret shift from Dm7b5 (dist = 1)
        self.assertLessEqual(dist_1_to_2, 4)
        # Resolution to Cm7 is within 5 frets of total finger movement
        self.assertLessEqual(dist_2_to_3, 6)

        # Verify tabs match expected smooth shapes
        self.assertEqual(result[0].voicing.tab_string(), "x-x-12-13-13-13")
        self.assertEqual(result[1].voicing.tab_string(), "x-x-12-13-12-13")
        self.assertEqual(result[2].voicing.tab_string(), "x-x-10-12-11-11")

    def test_autumn_leaves_minor_cadence(self):
        """
        Verify Autumn Leaves minor cadence:
        Am7b5 -> D7b9 -> Gm6
        Melody: C5 -> C5 -> Bb4
        """
        progression = [
            ("C5", "m7b5", "Am7b5"),
            ("C5", "7b9", "D7b9"),
            ("Bb4", "m6", "Gm6"),
        ]
        result = self.engine.arrange_progression(progression)
        self.assertEqual(len(result), 3)
        
        # Check tabs
        self.assertEqual(result[0].voicing.tab_string(), "x-x-7-8-8-8")
        self.assertEqual(result[1].voicing.tab_string(), "x-x-7-8-7-8")
        self.assertEqual(result[2].voicing.tab_string(), "x-x-5-7-5-6")

    def test_major_ii_v_i_progression(self):
        """
        Verify standard major ii-V-I in C Major:
        Dm7 -> G7 -> Cmaj7
        Melody: D5 -> B4 -> C5
        """
        progression = [
            ("D5", "m7", "Dm7"),
            ("B4", "7", "G7"),
            ("C5", "maj7", "Cmaj7")
        ]
        result = self.engine.arrange_progression(progression)
        self.assertEqual(len(result), 3)
        
        # Verify dictionary indexing works on ArrangementStep
        self.assertEqual(result[0]["chord"], "Dm7")
        self.assertEqual(result[0]["voicing"]["frets"], [-1, -1, 10, 10, 10, 10])

    def test_empty_progression(self):
        """An empty progression should return an empty list gracefully."""
        self.assertEqual(self.engine.arrange_progression([]), [])

    def test_low_register_cadence_falls_back_to_the_b_string(self):
        """
        D4 and C4 sit below the high E string's open pitch, so these steps used to be
        skipped with a warning. With the default soprano choices the melody moves to the
        B string and the whole cadence sits in low position.
        """
        progression = [
            ("D4", "m7", "Dm7"),
            ("D4", "7", "G7"),
            ("C4", "maj7", "Cmaj7"),
        ]
        result = self.engine.arrange_progression(progression)

        self.assertEqual(
            [(step.chord, step.voicing.tab_string()) for step in result],
            [("Dm7", "x-3-3-2-3-x"), ("G7", "x-2-3-0-3-x"), ("Cmaj7", "x-2-2-0-1-x")],
        )
        for step in result:
            self.assertEqual(step.voicing.soprano_string(), 4)  # B string carries the melody
            self.assertEqual(step.voicing.frets[0], -1)         # Low E muted
            self.assertEqual(step.voicing.frets[5], -1)         # High E muted

    def test_high_e_only_top_strings_still_skips_low_melodies(self):
        """top_strings=(5,) restores the pre-existing behaviour of skipping these steps."""
        progression = [
            ("D4", "m7", "Dm7"),
            ("D4", "7", "G7"),
            ("C4", "maj7", "Cmaj7"),
        ]
        self.assertEqual(self.engine.arrange_progression(progression, top_strings=(5,)), [])

    def test_unplayable_first_chord_does_not_break_the_next_step(self):
        """
        A skipped step must not leave the position-choosing logic with an empty
        arrangement to measure against.
        """
        progression = [
            ("B5", "m7", "Dm7"),  # Above fret 18 on both the high E and B strings
            ("D5", "m7", "Dm7"),
        ]
        result = self.engine.arrange_progression(progression)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].melody, "D5")
        self.assertEqual(result[0].voicing.tab_string(), "x-x-10-10-10-10")


if __name__ == "__main__":
    unittest.main()
