import unittest

from arranger import VoiceLeadingEngine, Voicing


class TestVoiceLeading(unittest.TestCase):
    """Tests for physical distance calculation and voice leading optimization."""

    def test_distance_identical_voicings(self):
        """Distance between identical voicings should be 0."""
        v1 = Voicing(frets=[-1, -1, 10, 10, 9, 10], top_fret=10, avg_fret=9.75)
        v2 = Voicing(frets=[-1, -1, 10, 10, 9, 10], top_fret=10, avg_fret=9.75)
        self.assertEqual(VoiceLeadingEngine.calculate_voice_leading_distance(v1, v2), 0.0)

    def test_distance_known_movement(self):
        """Moving each of the 4 voices by 1 fret should result in distance 4."""
        v1 = Voicing(frets=[-1, -1, 10, 10, 9, 10], top_fret=10, avg_fret=9.75)
        v2 = Voicing(frets=[-1, -1, 11, 11, 10, 11], top_fret=11, avg_fret=10.75)
        self.assertEqual(VoiceLeadingEngine.calculate_voice_leading_distance(v1, v2), 4.0)

    def test_distance_with_dict_backward_compatibility(self):
        """Should support distance calculation with legacy dict inputs."""
        d1 = {"frets": [-1, -1, 5, 5, 5, 7], "top_fret": 7, "avg_fret": 5.5}
        d2 = {"frets": [-1, -1, 5, 5, 5, 6], "top_fret": 6, "avg_fret": 5.25}
        self.assertEqual(VoiceLeadingEngine.calculate_voice_leading_distance(d1, d2), 1.0)

    def test_pitch_distance_matches_fret_distance_within_one_string_set(self):
        """
        Within a single four-string block a fret delta is a semitone delta, so the
        pitch-based and fret-based metrics agree exactly.
        """
        v1 = Voicing(frets=[-1, -1, 10, 12, 11, 11], top_fret=11, avg_fret=11.0)
        v2 = Voicing(frets=[-1, -1, 12, 13, 13, 13], top_fret=13, avg_fret=12.75)
        self.assertEqual(
            VoiceLeadingEngine.calculate_voice_leading_distance(v1, v2),
            VoiceLeadingEngine.calculate_pitch_leading_distance(v1, v2),
        )

    def test_pitch_distance_is_zero_when_the_same_pitches_move_string(self):
        """
        The same Dm7 voicing fingered on the B string instead of the high E string
        sounds identical, so it is a zero-distance move even though the fret numbers
        look completely different.
        """
        high_e = Voicing(frets=[-1, -1, 10, 10, 10, 10], top_fret=10, avg_fret=10.0)
        b_string = Voicing(frets=[-1, 15, 15, 14, 15, -1], top_fret=15, avg_fret=14.75)

        self.assertEqual(VoiceLeadingEngine.calculate_pitch_leading_distance(high_e, b_string), 0.0)
        # The fret-based metric cannot see this equivalence
        self.assertNotEqual(VoiceLeadingEngine.calculate_voice_leading_distance(high_e, b_string), 0.0)

    def test_pitch_distance_with_dict_backward_compatibility(self):
        """Legacy dict inputs must work with the pitch-based metric too."""
        d1 = {"frets": [-1, -1, 10, 10, 10, 10], "top_fret": 10, "avg_fret": 10.0}
        d2 = {"frets": [-1, -1, 10, 10, 9, 10], "top_fret": 10, "avg_fret": 9.75}
        self.assertEqual(VoiceLeadingEngine.calculate_pitch_leading_distance(d1, d2), 1.0)

    def test_arranged_chord_movement_is_the_same_under_both_metrics(self):
        """
        Within one string set the two movement metrics agree, and on a contiguous
        four-string block the fret deltas *are* the semitone deltas.

        The third chord is now a drop-2 & 4 on strings 5-4-2-1, so the second pair
        spans two different string sets and the metrics part company: fret-distance 5,
        pitch-distance 18. That is the documented behaviour, not a regression -
        `calculate_pitch_leading_distance` exists precisely because a skipped string
        makes a fret delta a different quantity from a semitone delta, and this
        arrangement now contains one.
        """
        progression = [
            ("F5", "m7b5", "Dm7b5"),
            ("F5", "7b9", "G7b9"),
            ("Eb5", "m7", "Cm7"),
        ]
        result = VoiceLeadingEngine().arrange_progression(progression)

        self.assertEqual(len(result), 3)
        for previous, current in zip(result, result[1:]):
            same_strings = (
                previous.voicing.active_strings == current.voicing.active_strings
            )
            fret = VoiceLeadingEngine.calculate_voice_leading_distance(
                previous.voicing, current.voicing
            )
            pitch = VoiceLeadingEngine.calculate_pitch_leading_distance(
                previous.voicing, current.voicing
            )
            if same_strings:
                self.assertEqual(fret, pitch, f"{previous.tab_line()} -> {current.tab_line()}")
            else:
                # Different string sets: the pitch metric is the meaningful one, and
                # the fret metric is only a proxy for it.
                self.assertNotEqual(
                    fret, pitch,
                    f"{previous.tab_line()} -> {current.tab_line()} spans two "
                    "string sets yet the metrics still agree - check the pitch metric",
                )


if __name__ == "__main__":
    unittest.main()
