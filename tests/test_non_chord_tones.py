import unittest
from musthe import Note
from arranger import ChordParser, VoiceLeadingEngine


class TestNonChordToneDetection(unittest.TestCase):
    """is_chord_tone must recognise every chord tone, including tones the four-note
    drop-2 voicings cannot sound."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_cmaj7_chord_tones(self):
        """C, E, G and B belong to Cmaj7; D, F and A do not."""
        for note in ("C5", "E5", "G5", "B4"):
            self.assertTrue(self.engine.is_chord_tone(Note(note), "maj7", "Cmaj7"), note)
        for note in ("D5", "F5", "A4"):
            self.assertFalse(self.engine.is_chord_tone(Note(note), "maj7", "Cmaj7"), note)

    def test_root_counts_as_a_chord_tone_of_a_rootless_quality(self):
        """7b9 is voiced without its root, but the root is still a chord tone, so a
        root melody must not be reharmonised."""
        self.assertTrue(self.engine.is_chord_tone(Note("G5"), "7b9", "G7b9"))
        self.assertTrue(self.engine.is_chord_tone(Note("F5"), "7b9", "G7b9"))  # b7
        self.assertFalse(self.engine.is_chord_tone(Note("F#5"), "7b9", "G7b9"))

    def test_quality_aliases_are_recognised(self):
        """Alias spellings must be understood too."""
        self.assertTrue(self.engine.is_chord_tone(Note("B4"), "M7", "Cmaj7"))
        self.assertTrue(self.engine.is_chord_tone(Note("Bb4"), "min7", "Cm7"))
        self.assertTrue(self.engine.is_chord_tone(Note("Ab5"), "half-dim", "Dm7b5"))

    def test_unknown_quality_is_never_a_chord_tone(self):
        """An unsupported quality reports False so callers leave it alone."""
        self.assertFalse(self.engine.is_chord_tone(Note("C5"), "not-a-chord", "Cnot-a-chord"))


class TestNonChordToneResolution(unittest.TestCase):
    """resolve_non_chord_tone maps a melody note onto a substitute chord."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_extension_strategy_absorbs_the_note_as_an_extension(self):
        """The 9th and 6th/13th each map to a quality that contains them."""
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("D5"), "maj7", "Cmaj7", "extension"),
            ("maj9", "Cmaj9"),
        )
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("A4"), "maj7", "Cmaj7", "extension"),
            ("6/9", "C6/9"),
        )
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("A4"), "7", "G7", "extension"),
            ("9", "G9"),
        )
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("E5"), "7", "G7", "extension"),
            ("13", "G13"),
        )
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("E5"), "m7", "Dm7", "extension"),
            ("m9", "Dm9"),
        )

    def test_extension_strategy_returns_none_when_unmapped(self):
        """B is neither a chord tone of Dm7 nor a mapped extension, so nothing is
        substituted and the caller keeps its fallback."""
        self.assertIsNone(self.engine.resolve_non_chord_tone(Note("B5"), "m7", "Dm7", "extension"))

    def test_diminished_strategy_uses_the_chord_below_the_resolution(self):
        """A passing D resolving to C is voiced inside Bdim7 - the dim7 a semitone
        below the target note (Barry Harris)."""
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("D5"), "maj7", "Cmaj7", "diminished", "C5"),
            ("dim7", "Bdim7"),
        )

    def test_diminished_strategy_without_a_known_resolution(self):
        """With no following chord tone the nearest chord tone below the melody is
        used as the resolution target."""
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("D5"), "maj7", "Cmaj7", "diminished"),
            ("dim7", "Bdim7"),
        )

    def test_legacy_strategy_never_substitutes(self):
        """The legacy strategy keeps the historical behaviour untouched."""
        self.assertIsNone(self.engine.resolve_non_chord_tone(Note("D5"), "maj7", "Cmaj7", "legacy"))


class TestExtendedExtensionMappings(unittest.TestCase):
    """The widened NON_CHORD_TONE_EXTENSIONS routing: 11ths, #11s, b13s and the
    half-diminished ninth now have somewhere to go instead of the legacy
    quality-only fallback."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_every_mapping_target_contains_the_degree_and_can_top_it(self):
        """Table invariant: a routed substitute must contain the melody degree as
        a chord tone *and* offer an inversion that puts it on top - the two
        conditions resolve_non_chord_tone relies on. The degree must really be
        outside the source chord, otherwise no substitution is needed."""
        for quality, mapping in VoiceLeadingEngine.NON_CHORD_TONE_EXTENSIONS.items():
            source_tones = {tone % 12 for tone in ChordParser.CHORD_TONES_FROM_ROOT[quality]}
            for degree, target in mapping.items():
                self.assertNotIn(degree % 12, source_tones, (quality, degree))
                target_tones = {tone % 12 for tone in ChordParser.CHORD_TONES_FROM_ROOT[target]}
                self.assertIn(degree % 12, target_tones, (quality, degree, target))
                target_top = {d % 12 for d in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT[target]}
                self.assertIn(degree % 12, target_top, (quality, degree, target))

    def test_new_routes_resolve_to_their_extension(self):
        cases = [
            (Note("C5"), "7", "G7", ("7sus4", "G7sus4")),          # 11th over a dominant
            (Note("C#5"), "7", "G7", ("7#11", "G7#11")),           # #11
            (Note("Eb5"), "7", "G7", ("7b13", "G7b13")),           # b13
            (Note("F#5"), "maj7", "Cmaj7", ("maj7#11", "Cmaj7#11")),
            (Note("B4"), "m7b5", "Am7b5", ("m9b5", "Am9b5")),
            (Note("C5"), "7b9", "G7b9", ("7sus4", "G7sus4")),
            (Note("C#5"), "7b9", "G7b9", ("7#11", "G7#11")),
            (Note("Eb5"), "7b9", "G7b9", ("7b13", "G7b13")),
            (Note("C#5"), "9", "G9", ("7#11", "G7#11")),
            (Note("C#5"), "13", "G13", ("7#11", "G7#11")),
        ]
        for melody, quality, name, expected in cases:
            self.assertEqual(
                self.engine.resolve_non_chord_tone(melody, quality, name, "extension"),
                expected,
                (name, str(melody)),
            )

    def test_the_mapped_notes_really_are_non_chord_tones(self):
        """Guard the cases above: each melody sits outside its written chord."""
        for melody, quality, name in (
            (Note("C5"), "7", "G7"),
            (Note("F#5"), "maj7", "Cmaj7"),
            (Note("B4"), "m7b5", "Am7b5"),
        ):
            self.assertFalse(self.engine.is_chord_tone(melody, quality, name))

    def test_end_to_end_extension_steps_use_the_new_colours(self):
        """A bar that hits the new colours: each non-chord melody becomes the
        named substitute, and every sounding pitch belongs to that substitute."""
        progression = [
            ("C5", "7", "G7"),         # the 11th -> G7sus4
            ("F#5", "maj7", "Cmaj7"),  # the #11 -> Cmaj7#11
            ("B4", "m7b5", "Am7b5"),   # the 9th -> Am9b5
        ]
        result = self.engine.arrange_progression(progression)
        expected_names = ["G7sus4", "Cmaj7#11", "Am9b5"]
        self.assertEqual([step.harmonized_as for step in result], expected_names)
        self.assertTrue(all(step.non_chord_tone for step in result))
        self.assertTrue(all(step.strategy == "extension" for step in result))
        for step, quality, name in zip(result, ("7sus4", "maj7#11", "m9b5"), expected_names):
            tones = set(ChordParser.get_chord_tones(quality, name))
            self.assertTrue(set(step.voicing.pitch_classes()) <= tones, step.voicing.tab_string())


class TestSustainInnerVoices(unittest.TestCase):
    """Strategy 3 holds the previous chord shape and moves only the soprano."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.cmaj7 = VoiceLeadingEngine.get_drop2_voicings(Note("C5"), "maj7", chord_name="Cmaj7")[0]

    def test_inner_voices_are_held(self):
        """x-x-9-9-8-8 becomes x-x-9-9-8-10 for a D5 passing tone: only the melody
        string moves."""
        held = self.engine.sustain_inner_voices(self.cmaj7, Note("D5"))
        # A bare assert narrows the Optional for the type checker; the test still
        # fails hard if the shape cannot be held.
        assert held is not None
        self.assertEqual(held.tab_string(), "x-x-9-9-8-10")
        self.assertEqual(held.frets[2:5], self.cmaj7.frets[2:5])

    def test_returns_none_when_the_melody_is_unreachable_on_the_string(self):
        """D4 sits below the high E string's open pitch, so the shape cannot hold."""
        self.assertIsNone(self.engine.sustain_inner_voices(self.cmaj7, Note("D4")))

    def test_returns_none_when_holding_would_exceed_the_fret_span(self):
        """G5 (fret 15) is seven frets from the held shape, so it is rejected."""
        self.assertIsNone(self.engine.sustain_inner_voices(self.cmaj7, Note("G5")))


class TestNonChordToneStrategiesEndToEnd(unittest.TestCase):
    """Bar 2 of 'All of Me': C5 -> D5 -> C5 over Cmaj7, where D5 is the 9th."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.all_of_me = [
            ("C5", "maj7", "Cmaj7"),
            ("D5", "maj7", "Cmaj7"),
            ("C5", "maj7", "Cmaj7"),
        ]

    def test_extension_strategy(self):
        """The default strategy reharmonises D5 as Cmaj9, so every sounding note
        belongs to the harmony."""
        result = self.engine.arrange_progression(self.all_of_me)
        self.assertEqual(
            [step.voicing.tab_string() for step in result],
            ["x-x-9-9-8-8", "x-x-9-9-8-10", "x-x-9-9-8-8"],
        )
        self.assertEqual([step.non_chord_tone for step in result], [False, True, False])
        self.assertEqual(result[1].strategy, "extension")
        self.assertEqual(result[1].harmonized_as, "Cmaj9")
        self.assertEqual(sorted(result[1].voicing.pitch_classes()), [2, 4, 7, 11])
        # The old fallback produced Bb-Eb-G-D (an Ebmaj7 shape); it must now be a
        # genuine Cmaj7-family voicing.
        self.assertNotEqual(sorted(result[1].voicing.pitch_classes()), [2, 3, 7, 10])

    def test_diminished_strategy(self):
        """The Barry Harris substitution voices D5 inside Bdim7 and resolves back."""
        result = self.engine.arrange_progression(self.all_of_me, non_chord_tone="diminished")
        self.assertEqual(
            [step.voicing.tab_string() for step in result],
            ["x-x-9-9-8-8", "x-x-9-10-9-10", "x-x-9-9-8-8"],
        )
        self.assertEqual(result[1].strategy, "diminished")
        self.assertEqual(result[1].harmonized_as, "Bdim7")
        self.assertEqual(sorted(result[1].voicing.pitch_classes()), [2, 5, 8, 11])
        # Two inner voices move one fret each way: 4 semitones of total movement
        self.assertEqual(
            VoiceLeadingEngine.calculate_pitch_leading_distance(result[0].voicing, result[1].voicing),
            4.0,
        )
        self.assertEqual(
            VoiceLeadingEngine.calculate_pitch_leading_distance(result[1].voicing, result[2].voicing),
            4.0,
        )

    def test_sustain_strategy_holds_the_previous_shape(self):
        """Only the melody string moves on the passing tone."""
        result = self.engine.arrange_progression(self.all_of_me, non_chord_tone="sustain")
        self.assertEqual(result[1].strategy, "sustain")
        self.assertEqual(result[1].harmonized_as, "Cmaj7")
        self.assertEqual(result[1].voicing.frets[2:5], result[0].voicing.frets[2:5])
        self.assertNotEqual(result[1].voicing.frets[5], result[0].voicing.frets[5])

    def test_legacy_strategy_preserves_the_historical_fallback(self):
        """The legacy strategy reproduces the old wrong-chord shape, which is why it
        is opt-in rather than the default."""
        result = self.engine.arrange_progression(self.all_of_me, non_chord_tone="legacy")
        self.assertEqual(result[1].voicing.tab_string(), "x-x-8-8-8-10")
        self.assertEqual(sorted(result[1].voicing.pitch_classes()), [2, 3, 7, 10])
        self.assertIsNone(result[1].strategy)

    def test_chord_tone_steps_are_identical_under_every_strategy(self):
        """The strategy only ever affects non-chord melodies."""
        major = [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")]
        expected = [step.voicing.tab_string() for step in self.engine.arrange_progression(major)]
        for strategy in VoiceLeadingEngine.NON_CHORD_TONE_STRATEGIES:
            tabs = [
                step.voicing.tab_string()
                for step in self.engine.arrange_progression(major, non_chord_tone=strategy)
            ]
            self.assertEqual(tabs, expected, strategy)

    def test_unknown_strategy_is_rejected(self):
        """A typo in the strategy name is a programming error, not a silent skip."""
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(self.all_of_me, non_chord_tone="nonsense")


if __name__ == "__main__":
    unittest.main()
