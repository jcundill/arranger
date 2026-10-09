import unittest

from arranger import VoiceLeadingEngine


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
        self.assertEqual(result[2].voicing.tab_string(), "x-13-x-12-13-11")
        # The Cm7 is a **drop-3** where it was a drop-2 & 4 at `x-10-10-x-11-11`. The four
        # notes are the same four chord tones - Bb3 G4 C5 Eb5 is b7, 5, root and b3, the
        # same notes the drop-2 & 4 carried - but the drop-2 & 4 that fitted here was one of
        # the four inner-skip `drop24` sets, and those are gone because a finger had to
        # reach over an unplucked string to fret them (`docs/fingering.md` §4.4; the table's
        # own comment holds the measured price). The replacement spans 2 where the old
        # shape spanned 1: that is the cost this end of the ban pays.
        self.assertEqual(result[2].voicing.grip, "drop3")
        self.assertEqual(
            sorted(result[2].voicing.pitch_classes()), [0, 3, 7, 10], "still a Cm7"
        )

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

        # Check tabs. All three are complete four-note chords: the selector treats a
        # partial harmonisation as a fallback rather than a style, so a shell only wins
        # where no full shape fits. Every note still belongs to its own chord.
        self.assertEqual(
            [step.voicing.tab_string() for step in result],
            ["x-x-7-8-8-8", "x-x-7-8-7-8", "12-x-12-12-11-x"],
        )
        # The Gm6 is a **drop-3** where it was a drop-2 & 4 at `x-5-5-x-5-6`, and the notes
        # are the same four Gm6 tones (E3 D4 G4 Bb4 - 6, 5, root, b3) with the melody still
        # on top. It moved because that drop-2 & 4 was one of the four inner-skip `drop24`
        # sets, removed for the finger reason in `docs/fingering.md` §4.4; the replacement
        # sits at frets 11-12 against the old 5-6, so the hand arrives from the previous
        # chord rather than dropping six frets to follow the melody.
        self.assertEqual(
            [step.grip for step in result], ["drop2", "drop2", "drop3"]
        )
        self.assertEqual(
            sorted(result[2].voicing.pitch_classes()), [2, 4, 7, 10], "still a Gm6"
        )
        self.assertTrue(not any(step.partial for step in result))

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

    def test_low_register_cadence_voices_low_with_a_complete_chord_or_a_shell(self):
        """
        D4 and C4 sit below the high E string's open pitch, so these steps used to be
        skipped with a warning. They are now voiced on the G string, one string lower
        again, which puts the whole cadence in low position on the bottom four strings.
        """
        progression = [
            ("D4", "m7", "Dm7"),
            ("D4", "7", "G7"),
            ("C4", "maj7", "Cmaj7"),
        ]
        result = self.engine.arrange_progression(progression)

        # None of these uses 6-5-4-3: a four-note voicing on the four lowest strings
        # does not sound good, so a low melody is harmonised with a complete chord or a
        # three-note shell instead.
        self.assertEqual(
            [(step.chord, step.voicing.tab_string()) for step in result],
            [("Dm7", "x-3-3-2-3-x"), ("G7", "3-x-3-4-3-x"), ("Cmaj7", "x-2-2-5-x-x")],
        )
        for step in result:
            self.assertNotEqual(
                step.voicing.active_strings, [0, 1, 2, 3], step.tab_line()
            )
        # G7 is a complete chord on 6-4-3-2, the one default set that reaches the low E,
        # and Cmaj7 is a three-note shell, because a melody that low has no four-note
        # shape with a legal span at all.
        self.assertEqual(
            [step.grip for step in result],
            ["drop2", "drop2_6432", "shell"],
        )
        self.assertEqual(result[1].voicing.active_strings, [0, 2, 3, 4])  # 6-4-3-2
        self.assertEqual(result[2].voicing.active_strings, [1, 2, 3])     # 5-4-3
        # Dm7 is the one step that changed grip, and it is a real trade rather than a
        # pure gain. It was 6-4-3-2 (`5-x-3-5-3-x`, span 2, lowest voice A2) and is now
        # the contiguous 5-4-3-2 (`x-3-3-2-3-x`, span 1, lowest voice C3).
        #
        # Span is now ranked above neck position, and the two shapes tie on every
        # correctness criterion - same four pitch classes, both inside the window, both
        # complete - so span decides and the narrower one wins. The cost is the bass: C
        # is the 3rd of Dm7 rather than A the 5th, and 6-4-3-2 is the only default shape
        # that can put a bass on the low E at all.
        #
        # This is the case where promoting span is not free, and it is left visible
        # rather than tuned away: the bass-function term is a *tie-break* at index 6,
        # below span, so it cannot recover a shape that span has already rejected.
        # Recovering it would mean ranking the bass above span, which was measured and
        # brings back the five-fret `8-x-8-8-13-x` this change exists to remove.
        self.assertEqual(sorted(result[0].voicing.pitch_classes()), [0, 2, 5, 9])
        # G7 gained its root and a fourth voice: it used to be the bare shell F3 B3 D4,
        # and is now a complete G7 with G2 underneath.
        self.assertEqual(sorted(result[1].voicing.pitch_classes()), [2, 5, 7, 11])  # G B D F
        self.assertEqual(sorted(result[2].voicing.pitch_classes()), [0, 4, 11])  # C E B

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
