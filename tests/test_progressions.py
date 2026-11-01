import unittest

from arranger import VoiceLeadingEngine, Voicing


def _fret_distance(first: Voicing, second: Voicing) -> float:
    """Fret-based movement across the strings both voicings sound."""
    frets_a = first.frets
    frets_b = second.frets
    return sum(abs(a - b) for a, b in zip(frets_a, frets_b) if a >= 0 and b >= 0)


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
            ("F5", "Dm7b5"),
            ("F5", "G7b9"),
            ("Eb5", "Cm7")
        ]
        result = self.engine.arrange_progression(progression)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].chord, "Dm7b5")
        self.assertEqual(result[1].chord, "G7b9")
        self.assertEqual(result[2].chord, "Cm7")

        # Verify smooth physical voice leading: movements between chords should be small
        dist_1_to_2 = _fret_distance(result[0].voicing, result[1].voicing)
        dist_2_to_3 = _fret_distance(result[1].voicing, result[2].voicing)

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
        # the four inner-skip `drop24` sets, which the tables do not hold because a finger
        # would have to reach over an unplucked string to fret them
        # (`docs/history/fingering.md` §4.4; the table's
        # own comment holds the measured price). The replacement spans 2 where the old
        # shape spanned 1: that is the cost this end of the ban pays.
        self.assertEqual(result[2].voicing.grip, "drop3")
        self.assertEqual(
            sorted(m % 12 for m in result[2].voicing.midi_notes()), [0, 3, 7, 10], "still a Cm7"
        )

    def test_autumn_leaves_minor_cadence(self):
        """
        Verify Autumn Leaves minor cadence:
        Am7b5 -> D7b9 -> Gm6
        Melody: C5 -> C5 -> Bb4
        """
        progression = [
            ("C5", "Am7b5"),
            ("C5", "D7b9"),
            ("Bb4", "Gm6"),
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
        # sets, removed for the finger reason in `docs/history/fingering.md` §4.4; the replacement
        # sits at frets 11-12 against the old 5-6, so the hand arrives from the previous
        # chord rather than dropping six frets to follow the melody.
        self.assertEqual(
            [step.grip for step in result], ["drop2", "drop2", "drop3"]
        )
        self.assertEqual(
            sorted(m % 12 for m in result[2].voicing.midi_notes()), [2, 4, 7, 10], "still a Gm6"
        )
        self.assertTrue(not any(step.partial for step in result))

    def test_major_ii_v_i_progression(self):
        """
        Verify standard major ii-V-I in C Major:
        Dm7 -> G7 -> Cmaj7
        Melody: D5 -> B4 -> C5
        """
        progression = [
            ("D5", "Dm7"),
            ("B4", "G7"),
            ("C5", "Cmaj7")
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
        D4 and C4 sit below the high E string's open pitch, so they are voiced on the G
        string, one string lower again, which puts the whole cadence in low position on the
        bottom four strings.
        """
        progression = [
            ("D4", "Dm7"),
            ("D4", "G7"),
            ("C4", "Cmaj7"),
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
                [i for i, f in enumerate(step.voicing.frets) if f >= 0], [0, 1, 2, 3], step.voicing.tab_string()
            )
        # G7 is a complete chord on 6-4-3-2, the one default set that reaches the low E,
        # and Cmaj7 is a three-note shell, because a melody that low has no four-note
        # shape with a legal span at all.
        self.assertEqual(
            [step.grip for step in result],
            ["drop2", "drop2_6432", "shell"],
        )
        self.assertEqual([i for i, f in enumerate(result[1].voicing.frets) if f >= 0], [0, 2, 3, 4])  # 6-4-3-2
        self.assertEqual([i for i, f in enumerate(result[2].voicing.frets) if f >= 0], [1, 2, 3])     # 5-4-3
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
        self.assertEqual(sorted(m % 12 for m in result[0].voicing.midi_notes()), [0, 2, 5, 9])
        # G7 states its root and a fourth voice - a complete G7 with G2 underneath,
        # rather than the bare shell F3 B3 D4.
        self.assertEqual(sorted(m % 12 for m in result[1].voicing.midi_notes()), [2, 5, 7, 11])  # G B D F
        self.assertEqual(sorted(m % 12 for m in result[2].voicing.midi_notes()), [0, 4, 11])  # C E B

    def test_high_e_only_top_strings_emits_silent_steps(self):
        """top_strings=(5,) keeps the old refusal, emitted silent rather than dropped.

        The lower strings that would rescue these melodies are excluded by the
        caller, so each position is a step the guitar does not play (item 4) -
        three of them, one per note, each carrying the reason `no_shape`: the
        pitch is reachable, but not on the strings this caller named.
        """
        progression = [
            ("D4", "Dm7"),
            ("D4", "G7"),
            ("C4", "Cmaj7"),
        ]
        steps = self.engine.arrange_progression(progression, top_strings=(5,))
        self.assertEqual(len(steps), 3)
        self.assertTrue(all(step.silence == "no_shape" for step in steps))

    def test_unplayable_first_chord_does_not_break_the_next_step(self):
        """
        A silent position must not leave the position-choosing logic with an
        all-muted voicing to measure against: the selector looks back to the last
        *sounding* shape, which here is none - so the D5 after the hole is chosen
        exactly as it was when the B5 position was dropped outright.
        """
        progression = [
            ("B5", "Dm7"),  # Above fret 18 on both the high E and B strings
            ("D5", "Dm7"),
        ]
        result = self.engine.arrange_progression(progression)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].silence, "out_of_reach")
        self.assertEqual(result[1].melody, "D5")
        self.assertEqual(result[1].voicing.tab_string(), "x-x-10-10-10-10")


if __name__ == "__main__":
    unittest.main()
