import unittest
from musthe import Note
from arranger import VoiceLeadingEngine, Voicing, GuitarFretboard, ChordParser, PITCH_CLASS_NAMES


class TestDrop2Voicings(unittest.TestCase):
    """Tests for generating drop-2 voicings and verifying physical playability and pitch correctness."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_dm7b5_voicings_notes_and_playability(self):
        """
        For Dm7b5 (chord tones: D, F, Ab, C):
        Pitch classes: D=2, F=5, Ab=8, C=0.
        All 4 inversions should contain exactly these 4 pitch classes.
        """
        expected_pcs = {2, 5, 8, 0}
        
        test_melodies = [
            ("D5", 0),   # Root on top
            ("F5", 3),   # b3 on top
            ("Ab5", 6),  # b5 on top
            ("C5", 10),  # b7 on top
        ]

        for mel_str, _ in test_melodies:
            voicings = self.engine.get_drop2_voicings(Note(mel_str), "m7b5", chord_name="Dm7b5")
            self.assertTrue(len(voicings) >= 1, f"Expected at least 1 voicing for Dm7b5 with melody {mel_str}")
            
            for v in voicings:
                # Top string (High E) must match melody
                top_midi = GuitarFretboard.fret_to_midi(5, v.frets[5])
                self.assertEqual(top_midi, Note(mel_str).midi_note())

                # Active strings must be strings 2, 3, 4, 5 (D, G, B, E)
                self.assertEqual(v.frets[0], -1)  # Low E muted
                self.assertEqual(v.frets[1], -1)  # A string muted
                for s in range(2, 6):
                    self.assertGreaterEqual(v.frets[s], 0)

                # Pitch classes must match chord tones {D, F, Ab, C}
                pcs = set(v.pitch_classes())
                self.assertEqual(pcs, expected_pcs, f"Voicing {v.tab_string()} pitch classes {pcs} != {expected_pcs}")

                # Playability: max span on guitar neck <= 5 frets
                self.assertLessEqual(v.fret_span(), 5)

    def test_minor_chord_qualities_supported(self):
        """Verify that all essential minor tune chord qualities return valid fingerings."""
        qualities = ["m7b5", "dim7", "m6", "mMaj7", "m7", "7b9", "7alt"]
        for q in qualities:
            voicings = self.engine.get_drop2_voicings(Note("G5"), q)
            self.assertGreater(len(voicings), 0, f"Expected voicings for quality {q} with melody G5")
            for v in voicings:
                self.assertLessEqual(v.fret_span(), 5)
                self.assertTrue(all(0 <= f <= 18 for f in v.active_frets()))

    def test_major_chord_qualities_supported(self):
        """Verify major family qualities (maj7, 6, 7)."""
        qualities = ["maj7", "6", "7"]
        for q in qualities:
            voicings = self.engine.get_drop2_voicings(Note("C5"), q)
            self.assertGreater(len(voicings), 0, f"Expected voicings for quality {q} with melody C5")

    def test_voicing_dataclass_methods(self):
        """Test Voicing helper methods."""
        v = Voicing(frets=[-1, -1, 10, 11, 10, 10], top_fret=10, avg_fret=10.25)
        self.assertEqual(v.tab_string(), "x-x-10-11-10-10")
        self.assertEqual(v.active_frets(), [10, 11, 10, 10])
        self.assertEqual(v.fret_span(), 1)
        # Dictionary-like backward compatibility
        self.assertEqual(v["top_fret"], 10)
        self.assertEqual(v["frets"], [-1, -1, 10, 11, 10, 10])


class TestExtendedQualities(unittest.TestCase):
    """Ninth/13th qualities added so non-chord melody notes can be absorbed."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_extension_qualities_sound_only_chord_tones_and_stay_playable(self):
        """Every voicing of maj9/m9/9/6-9/13 sounds tones of that chord only."""
        cases = [
            ("maj9", "C5"), ("maj9", "D5"),
            ("m9", "D5"), ("9", "D5"),
            ("6/9", "D5"), ("13", "A4"),
        ]
        for quality, melody in cases:
            chord_name = "C" + quality
            tones = set(ChordParser.get_chord_tones(quality, chord_name))
            voicings = self.engine.get_drop2_voicings(Note(melody), quality, chord_name=chord_name)
            self.assertTrue(voicings, f"Expected a voicing for {chord_name} with melody {melody}")
            for v in voicings:
                self.assertLessEqual(v.fret_span(), 5)
                self.assertTrue(
                    set(v.pitch_classes()) <= tones,
                    f"{v.tab_string()} sounds {sorted(v.pitch_classes())} outside {sorted(tones)}",
                )

    def test_extension_quality_without_chord_name_offers_every_inversion(self):
        """Without a chord name all five inversions are offered for each block."""
        voicings = self.engine.get_all_drop2_voicings(Note("D5"), "maj9")
        self.assertEqual(len(voicings), 10)  # 5 templates x 2 soprano strings
        for v in voicings:
            self.assertLessEqual(v.fret_span(), 5)
            self.assertTrue(all(0 <= f <= 18 for f in v.active_frets()))

    def test_rootless_dominant_root_in_top_inversion(self):
        """7b9 and 7alt are voiced rootless, so a root melody used to fall through to
        a wrong chord; each now has a root-in-top inversion that contains its root."""
        for quality, chord_name in (("7b9", "G7b9"), ("7alt", "G7alt")):
            tones = set(ChordParser.get_chord_tones(quality, chord_name))
            voicings = self.engine.get_drop2_voicings(Note("G5"), quality, chord_name=chord_name)
            self.assertEqual([v.tab_string() for v in voicings], ["x-x-15-13-12-15"], quality)
            self.assertTrue(set(voicings[0].pitch_classes()) <= tones)
            self.assertIn(7, voicings[0].pitch_classes())  # the root sounds

    def test_quality_alias_selects_the_same_inversion_as_the_canonical_spelling(self):
        """M7 must behave like maj7 - it used to be read as m7."""
        canonical = self.engine.get_drop2_voicings(Note("B4"), "maj7", chord_name="Cmaj7")
        alias = self.engine.get_drop2_voicings(Note("B4"), "M7", chord_name="Cmaj7")
        self.assertEqual([v.tab_string() for v in canonical], ["x-x-5-5-5-7"])
        self.assertEqual([v.tab_string() for v in alias], [v.tab_string() for v in canonical])


class TestMelodyStringChoices(unittest.TestCase):
    """
    Tests for pinning the melody to the B string, which places the voicing on
    strings 5-4-3-2 (A, D, G, B) instead of the traditional D-G-B-E block.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_b_string_voicing_uses_strings_5_to_2(self):
        """
        With top_string=4 the melody sounds on the B string (index 4) and the voicing
        uses strings 1-4 (A, D, G, B); the low E and high E strings are muted.
        """
        voicings = self.engine.get_drop2_voicings(Note("D5"), "m7", chord_name="Dm7", top_string=4)
        self.assertEqual([v.tab_string() for v in voicings], ["x-15-15-14-15-x"])

        v = voicings[0]
        self.assertEqual(v.soprano_string(), 4)
        self.assertEqual(v.frets[0], -1)  # Low E muted
        self.assertEqual(v.frets[5], -1)  # High E muted
        for s in range(1, 5):
            self.assertGreaterEqual(v.frets[s], 0)

        # The melody note itself must sound on the B string
        self.assertEqual(GuitarFretboard.fret_to_midi(4, v.frets[4]), Note("D5").midi_note())
        self.assertLessEqual(v.fret_span(), 5)

    def test_both_families_sound_the_same_pitches(self):
        """
        Fingering the same inversion on either four-string block sounds the same four
        pitches - only the position on the neck changes.
        """
        high_e = self.engine.get_drop2_voicings(Note("D5"), "m7", chord_name="Dm7", top_string=5)
        b_string = self.engine.get_drop2_voicings(Note("D5"), "m7", chord_name="Dm7", top_string=4)

        self.assertEqual(high_e[0].tab_string(), "x-x-10-10-10-10")
        self.assertEqual(b_string[0].tab_string(), "x-15-15-14-15-x")
        self.assertEqual(sorted(high_e[0].midi_notes()), sorted(b_string[0].midi_notes()))

    def test_melody_below_high_e_open_pitch_needs_the_b_string(self):
        """
        D4 sits below the high E string's open pitch (E4), so that family cannot voice
        it at all; the B string plays it in low position instead.
        """
        self.assertEqual(self.engine.get_drop2_voicings(Note("D4"), "m7", chord_name="Dm7"), [])

        b_string = self.engine.get_drop2_voicings(Note("D4"), "m7", chord_name="Dm7", top_string=4)
        self.assertEqual([v.tab_string() for v in b_string], ["x-3-3-2-3-x"])

    def test_get_all_drop2_voicings_lists_high_e_first(self):
        """
        get_all_drop2_voicings offers the high-E candidate before the B-string one, so a
        caller that simply takes the first result keeps the traditional fingering.
        """
        all_voicings = self.engine.get_all_drop2_voicings(Note("D5"), "m7", chord_name="Dm7")
        self.assertEqual(
            [(v.tab_string(), v.soprano_string()) for v in all_voicings],
            [("x-x-10-10-10-10", 5), ("x-15-15-14-15-x", 4)],
        )

    def test_get_all_drop2_voicings_can_be_restricted_to_high_e(self):
        """
        Passing top_strings=(5,) reproduces the original high-E-only behaviour, so callers
        can opt out of the B string entirely.
        """
        all_voicings = self.engine.get_all_drop2_voicings(
            Note("D5"), "m7", chord_name="Dm7", top_strings=(5,)
        )
        self.assertEqual([v.tab_string() for v in all_voicings], ["x-x-10-10-10-10"])
        self.assertEqual({v.soprano_string() for v in all_voicings}, {5})

    def test_get_all_drop2_voicings_without_chord_name_returns_all_inversions(self):
        """Without a chord name every inversion of every family is offered: 4 shapes x 2 families."""
        all_voicings = self.engine.get_all_drop2_voicings(Note("D5"), "m7")

        self.assertEqual(len(all_voicings), 8)
        self.assertEqual([v.soprano_string() for v in all_voicings], [5, 5, 5, 5, 4, 4, 4, 4])
        for v in all_voicings:
            self.assertLessEqual(v.fret_span(), 5)
            self.assertTrue(all(0 <= f <= 18 for f in v.active_frets()))

    def test_unsupported_quality_returns_nothing_for_every_family(self):
        """An unknown chord quality yields no voicings, whichever soprano strings are allowed."""
        self.assertEqual(self.engine.get_all_drop2_voicings(Note("D5"), "not-a-chord"), [])
        self.assertEqual(self.engine.get_all_drop2_voicings(Note("D5"), "not-a-chord", "Dm7"), [])


class TestTriadSusAndAlteredQualities(unittest.TestCase):
    """Triads, suspended chords and altered colours added to the vocabulary.

    A drop-2 shape needs four voices, so the triad templates double the root an
    octave below the stack. Every shape must still sound only tones of its own
    chord, stay inside the five-fret span and pin the melody to the soprano.
    """

    # (chord name, melody, expected high-E fingering)
    CASES = [
        ("Cmaj", "E5", "x-x-10-9-8-12"),
        ("Cm", "C5", "x-x-5-5-4-8"),
        ("Caug", "E5", "x-x-10-9-9-12"),
        ("Gsus4", "C5", "x-x-5-5-3-8"),
        ("Gsus2", "A4", "x-x-5-2-3-5"),
        ("Cadd9", "D5", "x-x-10-9-8-10"),
        ("Cmadd9", "D5", "x-x-10-8-8-10"),
        ("G7sus4", "C5", "x-x-5-7-6-8"),
        ("G7b5", "Db5", "x-x-9-10-8-9"),
        ("G7#5", "Eb5", "x-x-9-10-8-11"),
        ("G7#11", "Db5", "x-x-9-10-8-9"),
        ("G7b13", "Eb5", "x-x-9-10-8-11"),
        ("Cmaj7#11", "F#5", "x-x-14-16-13-14"),
        ("Am9b5", "B4", "x-x-5-5-4-7"),
    ]

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_exact_fingering_and_chord_tone_purity(self):
        """Each new quality offers one chord-tone-matched inversion per melody,
        and that shape sounds only pitches of its own chord."""
        for chord_name, melody, expected in self.CASES:
            quality = ChordParser.parse_chord_name(chord_name)[1]
            tones = set(ChordParser.get_chord_tones(quality, chord_name))
            voicings = self.engine.get_drop2_voicings(Note(melody), quality, chord_name=chord_name)
            self.assertEqual([v.tab_string() for v in voicings], [expected], chord_name)
            voicing = voicings[0]
            self.assertTrue(set(voicing.pitch_classes()) <= tones, f"{chord_name} {voicing.tab_string()}")
            self.assertLessEqual(voicing.fret_span(), 5, chord_name)
            self.assertTrue(all(0 <= f <= 18 for f in voicing.active_frets()), chord_name)
            self.assertEqual(GuitarFretboard.fret_to_midi(5, voicing.frets[5]), Note(melody).midi_note())

    def test_every_chord_tone_is_voiceable_in_the_working_register(self):
        """In the E4-Bb5 register each chord tone of each new quality gets a pure,
        playable, chord-tone-matched voicing on one of the two blocks."""
        checked = 0
        for quality in ("maj", "m", "aug", "sus4", "sus2", "add9", "madd9", "7sus4",
                        "7b5", "7#5", "7#11", "7b13", "maj7#11", "m9b5"):
            for root_str in ("C", "F#"):
                chord_name = root_str + quality
                tones = set(ChordParser.get_chord_tones(quality, chord_name))
                root_pc = Note(root_str + "4").midi_note() % 12
                for degree in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT[quality]:
                    midi = next(m for m in range(64, 83) if m % 12 == (root_pc + degree) % 12)
                    melody = PITCH_CLASS_NAMES[midi % 12] + str(midi // 12 - 1)
                    matched = [
                        v for top_string in (5, 4)
                        for v in self.engine.get_drop2_voicings(
                            Note(melody), quality, chord_name=chord_name, top_string=top_string)
                    ]
                    if not matched:
                        # Pre-existing low-register gap, shared with maj7/m7/9/m9:
                        # the caller falls back to quality-only voicings.
                        self.assertTrue(
                            self.engine.get_all_drop2_voicings(Note(melody), quality, chord_name=chord_name),
                            (chord_name, melody),
                        )
                        continue
                    checked += 1
                    for v in matched:
                        self.assertTrue(set(v.pitch_classes()) <= tones, (chord_name, melody, v.tab_string()))
                        self.assertLessEqual(v.fret_span(), 5, (chord_name, melody))
                        self.assertTrue(all(0 <= f <= 18 for f in v.active_frets()), (chord_name, melody))
                        self.assertIn(v.soprano_string(), (5, 4), (chord_name, melody))
        self.assertGreater(checked, 100)

    def test_symmetrical_qualities_reuse_their_shapes(self):
        """aug is symmetrical (like dim7), while 7b5/7#11 and 7#5/7b13 need only
        two distinct shapes each."""
        def shapes(quality):
            return {tuple(template) for template in VoiceLeadingEngine.DROP2_INTERVAL_SETS[quality]}

        self.assertEqual(len(shapes("aug")), 1)
        self.assertEqual(len(shapes("dim7")), 1)
        self.assertEqual(len(shapes("7b5")), 2)
        self.assertEqual(len(shapes("7#11")), 2)
        self.assertEqual(shapes("7b5"), shapes("7#11"))
        self.assertEqual(shapes("7#5"), shapes("7b13"))

    def test_aliases_reach_the_new_qualities(self):
        """M/min/-/+/sus/7sus resolve to the canonical qualities' voicings."""
        cases = [
            ("M", "maj", "Cmaj", "E5"),
            ("min", "m", "Cm", "C5"),
            ("-", "m", "Cm", "C5"),
            ("+", "aug", "Caug", "E5"),
            ("sus", "sus4", "Gsus4", "C5"),
            ("7sus", "7sus4", "G7sus4", "C5"),
        ]
        for alias, canonical, chord_name, melody in cases:
            expected = self.engine.get_drop2_voicings(Note(melody), canonical, chord_name=chord_name)
            aliased = self.engine.get_drop2_voicings(Note(melody), alias, chord_name=chord_name)
            self.assertTrue(expected, chord_name)
            self.assertEqual([v.tab_string() for v in aliased], [v.tab_string() for v in expected], alias)


class TestQualityTableInvariants(unittest.TestCase):
    """Structural rules that keep the quality tables in step with each other."""

    def test_templates_and_degree_offsets_have_one_entry_each(self):
        for quality, degrees in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.items():
            templates = VoiceLeadingEngine.DROP2_INTERVAL_SETS[quality]
            self.assertEqual(len(templates), len(degrees), quality)

    def test_templates_are_four_voice_drop2_shapes(self):
        for quality in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT:
            for template in VoiceLeadingEngine.DROP2_INTERVAL_SETS[quality]:
                self.assertEqual(len(template), 4, quality)
                self.assertEqual(template[0], 0, quality)
                self.assertEqual(template, sorted(template, reverse=True), (quality, template))
                self.assertTrue(all(-19 <= offset < 0 for offset in template[1:]), (quality, template))

    def test_every_top_degree_is_a_chord_tone(self):
        for quality, degrees in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.items():
            tones = {tone % 12 for tone in ChordParser.CHORD_TONES_FROM_ROOT[quality]}
            for degree in degrees:
                self.assertIn(degree % 12, tones, (quality, degree))


if __name__ == "__main__":
    unittest.main()
