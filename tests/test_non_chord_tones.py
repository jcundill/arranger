import contextlib
import io
import unittest

from musthe import Note

from arranger import (
    NO_CHORD,
    ArrangementStep,
    ChordParser,
    VoiceLeadingEngine,
    Voicing,
    _print_step,
    _step_annotation,
    format_progression,
)


class TestMelodyOnlyVoicing(unittest.TestCase):
    """get_melody_only_voicing plays one note on one string, for NC bars."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_high_e_string_is_preferred(self):
        """F4 sits on the high E string at fret 1."""
        voicing = self.engine.get_melody_only_voicing(Note("F4"))
        self.assertIsNotNone(voicing)
        assert voicing is not None
        self.assertEqual(voicing.tab_string(), "x-x-x-x-x-1")
        self.assertEqual(voicing.fret_span(), 0)
        self.assertEqual(voicing.midi_notes(), [65])

    def test_below_the_high_e_open_pitch_falls_to_the_b_string(self):
        """Eb4 cannot be played on the high E, so it drops to the B string."""
        voicing = self.engine.get_melody_only_voicing(Note("Eb4"))
        self.assertIsNotNone(voicing)
        assert voicing is not None
        self.assertEqual(voicing.tab_string(), "x-x-x-x-4-x")
        self.assertEqual(voicing.soprano_string(), 4)

    def test_low_melody_uses_a_string_outside_the_melody_choices(self):
        """G3 is unreachable on both melody strings and sounds on the open G."""
        voicing = self.engine.get_melody_only_voicing(Note("G3"))
        self.assertIsNotNone(voicing)
        assert voicing is not None
        self.assertEqual(voicing.tab_string(), "x-x-x-0-x-x")
        self.assertEqual(voicing.soprano_string(), 3)

    def test_exactly_one_active_fret(self):
        """Whatever string is chosen, a melody-only step is a single fret."""
        for name in ("F5", "Eb5", "Db5", "Bb4", "G3", "Bb3", "B3"):
            voicing = self.engine.get_melody_only_voicing(Note(name))
            self.assertIsNotNone(voicing, name)
            assert voicing is not None
            self.assertEqual(len(voicing.active_frets()), 1, name)

    def test_top_fret_and_avg_fret_describe_the_single_fret(self):
        """top_fret/avg_fret are consistent for a one-fret voicing."""
        voicing = self.engine.get_melody_only_voicing(Note("Bb3"))
        self.assertIsNotNone(voicing)
        assert voicing is not None
        self.assertEqual(voicing.top_fret, 3)
        self.assertEqual(voicing.avg_fret, 3.0)

    def test_unreachable_note_returns_none(self):
        """Below the low E open there is nothing to play."""
        self.assertIsNone(self.engine.get_melody_only_voicing(Note("D2")))

    def test_notes_above_the_18th_fret_return_none(self):
        """B5 and C6 are the only NC pitches the database has that cannot sound."""
        for name in ("B5", "C6"):
            self.assertIsNone(self.engine.get_melody_only_voicing(Note(name)), name)

    def test_prefer_order_is_honoured(self):
        """A caller may pin the melody to a specific string."""
        voicing = self.engine.get_melody_only_voicing(Note("G3"), prefer=(3,))
        self.assertIsNotNone(voicing)
        assert voicing is not None
        self.assertEqual(voicing.soprano_string(), 3)

    def test_out_of_range_prefer_indices_are_ignored(self):
        """A bad index in `prefer` must not raise or index off the fretboard."""
        voicing = self.engine.get_melody_only_voicing(Note("F4"), prefer=(99, -1))
        self.assertIsNotNone(voicing)
        assert voicing is not None
        self.assertEqual(voicing.soprano_string(), 5)


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

    def test_legacy_strategy_is_gone_from_the_vocabulary(self):
        """`legacy` named an era, not a behaviour, and is removed rather than aliased.

        Its one real instruction - substitute nothing - survives where it has a
        comping meaning (`sustain`) and as the quality-only fallback the extension
        table's own gaps leave in place. A deprecated alias kept working would be
        the same fact stated twice; see AGENTS.md trap 5.
        """
        self.assertNotIn("legacy", VoiceLeadingEngine.NON_CHORD_TONE_STRATEGIES)
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(
                [("D5", "maj7", "Cmaj7")], non_chord_tone="legacy"
            )


class TestThePaletteRescue(unittest.TestCase):
    """A chord no shape in the palette can carry leaves the tune alone, and says so.

    The alternative - and what the engine did - was to drop the step, which takes the
    melody note with it. The claim such a step makes is not "this is a chord" but
    "this is the tune and nothing under it", so it is recorded on the step
    (`chord_unvoiced`) and reported by the renderers rather than inferred from the
    shape, which a deliberate melody-alone **fill** shares.
    """

    def test_the_step_survives_the_chord_it_cannot_voice(self):
        steps = VoiceLeadingEngine.arrange_progression(
            [("Bb4", "dim7", "F#dim7")], grips=("shell",)
        )
        self.assertEqual(len(steps), 1, "the note went missing with the chord")
        step = steps[0]
        self.assertEqual(step.chord, "F#dim7")
        self.assertEqual(step.melody, "Bb4")
        self.assertTrue(step.chord_unvoiced)
        # Not the `NC` case: there *is* a chord here, it just is not sounding.
        self.assertFalse(step.melody_only)
        self.assertEqual(len(step.voicing.active_frets()), 1)

    def test_the_renderer_says_the_chord_is_not_sounding(self):
        """A bare note under a chord symbol is the thing this label exists to prevent."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("Bb4", "dim7", "F#dim7")], grips=("shell",)
        )
        self.assertEqual(
            _step_annotation(steps[0]), " (melody alone - no voicing for this chord)"
        )

    def test_a_step_that_is_also_transposed_reports_both_facts(self):
        """The rescue drops a high note an octave *and* leaves the chord unstated.

        G5 is fret 15 on the high E string, past `HIGH_FRET_LIMIT`, so the melody-alone
        shape sounds G4 - and both facts have to reach the reader. Measured on "The
        Jitterbug Waltz" bars 1 and 9; this is the unit form of it.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("G5", "6", "Eb6")], grips=("shell",)
        )
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertTrue(step.chord_unvoiced)
        self.assertEqual(step.original_melody, "G5")
        self.assertEqual(step.melody, "G4")
        self.assertIn("transposed down an octave from G5", _step_annotation(step))
        self.assertIn("no voicing for this chord", _step_annotation(step))


class TestExtendedExtensionMappings(unittest.TestCase):
    """The widened NON_CHORD_TONE_EXTENSIONS routing: 11ths, #11s, b13s and the
    half-diminished ninth now have somewhere to go instead of the
    quality-only fallback, and the 9th over a plain triad has a row at all."""

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
            # The plain triads. This is the case that reached no family at all
            # under `--grips shell`: a 9th is not a chord tone of a triad, the
            # table had no row to absorb it, and a shell may not sound a note
            # outside the chord, so the step was dropped rather than thinned.
            (Note("F4"), "maj", "Ebmaj", ("add9", "Ebadd9")),      # 9th over a major triad
            (Note("D5"), "m", "Cm", ("madd9", "Cmadd9")),          # 9th over a minor triad
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
            (Note("F4"), "maj", "Ebmaj"),
        ):
            self.assertFalse(self.engine.is_chord_tone(melody, quality, name))

    def test_the_shell_family_can_voice_a_ninth_over_a_triad_now(self):
        """The row is worth nothing if the family the failure came from cannot use it.

        A shell states the chord's 3rd and 7th and may sound **nothing** outside
        the chord, so `Ebmaj` under `F4` had no shell at all - and unlike the
        four-note families it has no quality-only fallback to thin, which is why
        the step was dropped rather than played. `Ebadd9` has four shells, every
        one of them the 3rd, the 5th and the 9th.
        """
        self.assertEqual(
            self.engine.get_all_grip_voicings(
                Note("F4"), "maj", chord_name="Ebmaj", grips=("shell",)
            ),
            [],
        )
        voicings = self.engine.get_all_grip_voicings(
            Note("F4"), "add9", chord_name="Ebadd9", grips=("shell",)
        )
        self.assertEqual(len(voicings), 4)
        allowed = {pc % 12 for pc in ChordParser.get_chord_tones("add9", "Ebadd9")}
        for voicing in voicings:
            self.assertEqual(voicing.grip, "shell")
            sounding = {midi % 12 for midi in voicing.midi_notes()}
            self.assertEqual(sounding, {5, 7, 10}, voicing.frets)
            self.assertTrue(sounding <= allowed, voicing.frets)

    def test_a_dominant_b9_reaches_the_altered_dominant(self):
        """The b9 over a plain dominant is the one route with nowhere else to go.

        It is also the note a tritone substitution exists to absorb: the b9 of G7
        is the 3rd of Db7, so both routes make the melody a chord tone. The
        table route keeps the written root, which is the narrower claim - see
        docs/history/reharmonisation-proposals.md.
        """
        self.assertEqual(
            self.engine.resolve_non_chord_tone(Note("Ab5"), "7", "G7", "extension"),
            ("7b9", "G7b9"),
        )

    def test_the_b9_route_is_the_narrowest_quality_that_contains_it(self):
        """`7b9` rather than `7alt`: the substitute adds the one tone the melody
        states, and does not also claim the #9, #5 and b13 that `7alt` would."""
        substituted = self.engine.resolve_non_chord_tone(
            Note("Ab5"), "7", "G7", "extension"
        )
        # A bare `assert` rather than `assertIsNotNone`: pyright does not narrow
        # through the unittest helper, and this is the trap `test_docs.py`'s
        # `_layout_block` already had to work around. Resolving the Optional where
        # the type is still known is the house answer.
        assert substituted is not None
        quality, name = substituted
        self.assertEqual(quality, "7b9")
        # The b9 is a chord tone of the substitute, and is the only addition: every
        # tone the source chord had is still there.
        source = {t % 12 for t in ChordParser.get_chord_tones("7", "G7")}
        target = {t % 12 for t in ChordParser.get_chord_tones(quality, name)}
        self.assertTrue(target - source == {8}, "G7 -> G7b9 adds exactly the b9")

    def test_the_b9_of_a_dominant_is_not_a_chord_tone_before_substitution(self):
        """The route must only fire for a genuine non-chord tone.

        Ab is a chord tone of Db7 but not of G7, so the degree key is read against
        the *written* root. A b3 over G7 is degree 3 and must stay unresolved -
        mapping it would assert a chord the melody never implied.
        """
        self.assertFalse(self.engine.is_chord_tone(Note("Ab5"), "7", "G7"))
        self.assertIsNone(
            self.engine.resolve_non_chord_tone(Note("Bb4"), "7", "G7", "extension")
        )

    def test_end_to_end_a_b9_over_a_dominant_is_harmonised_as_the_altered_dominant(self):
        """End to end: the step names its substitute and sounds only its tones."""
        result = self.engine.arrange_progression([("Ab4", "7", "G7")])
        self.assertEqual(len(result), 1)
        step = result[0]
        self.assertEqual(step.chord, "G7", "the written chord is still reported")
        self.assertEqual(step.harmonized_as, "G7b9")
        self.assertEqual(step.strategy, "extension")
        self.assertTrue(step.non_chord_tone)
        tones = set(ChordParser.get_chord_tones("7b9", "G7b9"))
        self.assertTrue(
            set(step.voicing.pitch_classes()) <= tones, step.voicing.tab_string()
        )
        self.assertLessEqual(step.voicing.fret_span(), 5)

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
        # Still a complete four-note Bdim7, not a shell. It briefly was one while
        # criterion 0 was scoring the *substituted* voicing against the *written*
        # Cmaj7: every Bdim7 candidate was then three foreign notes, so purity could not
        # separate them and `missing` picked a three-note shell. Purity is now asked
        # about the chord that is sounding - see steps.py, where `allowed_tones` comes
        # from `harmonized_as` when a strategy substituted one.
        self.assertEqual(result[1].grip, "drop2")
        self.assertEqual(len(result[1].voicing.active_frets()), 4)
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


class TestNoChordSteps(unittest.TestCase):
    """NC steps are voiced melody-alone: no reharmonisation, no warning."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_nc_step_is_melody_only(self):
        """An NC step is flagged melody_only with no strategy applied."""
        steps = self.engine.arrange_progression([("F4", NO_CHORD, NO_CHORD)])
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertTrue(step.melody_only)
        self.assertFalse(step.non_chord_tone)
        self.assertIsNone(step.harmonized_as)
        self.assertIsNone(step.strategy)
        self.assertEqual(step.tab_line(), "x-x-x-x-x-1")

    def test_nc_step_grip_mirrors_the_voicing(self):
        """`step.grip` says what `voicing.grip` says, not the "drop2" default.

        The two fields are one fact stated twice, and on this path they
        disagreed for the field's whole life: the voicing said "melody" (set
        in `grips.get_melody_only_voicing` precisely so a reader would not
        conclude a four-note drop-2 had been chosen) while the step rested on
        its "drop2" default. Whatever reads the step rather than its voicing
        would read the lie.
        """
        steps = self.engine.arrange_progression([("F4", NO_CHORD, NO_CHORD)])
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].grip, steps[0].voicing.grip)
        self.assertEqual(steps[0].grip, "melody")

    def test_nc_is_detected_from_chord_type_or_chord_name(self):
        """Either slot carrying "NC" marks the step as unaccompanied."""
        for progression in ([("F4", NO_CHORD, "NC")], [("F4", "NC", NO_CHORD)]):
            steps = self.engine.arrange_progression(progression)
            self.assertEqual(len(steps), 1, progression)
            self.assertTrue(steps[0].melody_only, progression)

    def test_nc_mixed_with_harmonised_steps(self):
        """NC steps sit in an arrangement alongside ordinary chords."""
        steps = self.engine.arrange_progression([
            ("C5", "maj7", "Cmaj7"),
            ("F4", NO_CHORD, NO_CHORD),
            ("C5", "maj7", "Cmaj7"),
        ])
        self.assertEqual(len(steps), 3)
        self.assertFalse(steps[0].melody_only)
        self.assertTrue(steps[1].melody_only)
        self.assertFalse(steps[2].melody_only)

    def test_nc_note_is_never_reharmonised(self):
        """An NC melody note gets no substitute chord, whatever it would be."""
        steps = self.engine.arrange_progression([("F#4", NO_CHORD, NO_CHORD)])
        self.assertEqual(len(steps), 1)
        self.assertIsNone(steps[0].harmonized_as)
        self.assertIsNone(steps[0].strategy)
        self.assertEqual(ChordParser.canonical_quality(NO_CHORD), NO_CHORD)

    def test_unreachable_nc_note_is_skipped_not_raised(self):
        """An unplayable NC note warns and is skipped rather than raising."""
        self.assertEqual(self.engine.arrange_progression([("D2", NO_CHORD, NO_CHORD)]), [])

    def test_annotation_is_shared_by_both_renderings(self):
        """format_progression and _print_step report the same text.

        The second assertion used to be the `vertical=True` block, which printed the
        same annotation over a six-line header. That renderer is gone, and the two
        consumers of `_step_annotation` that remain are `format_progression` and
        `_print_step` - the compact line and the demo's one-line summary. They share
        the function precisely so a melody-only step cannot read one way in the
        library and another in `make demo`.

        Note it is *not* `tab_line()`: that is the voicing's own cells with no room
        for an annotation, which is why the pairing is the two renderers rather than
        the renderer and its own step method.
        """
        steps = self.engine.arrange_progression([("F4", NO_CHORD, NO_CHORD)])
        expected = _step_annotation(steps[0])
        self.assertEqual(expected, " (no chord - melody alone)")
        self.assertIn(expected, format_progression(steps))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            _print_step(steps[0])
        self.assertIn(expected, printed.getvalue())

    def test_ordinary_step_annotation_names_the_degree(self):
        """A chord tone names the degree it is and how many voices state it."""
        steps = self.engine.arrange_progression([("C5", "maj7", "Cmaj7")])
        self.assertEqual(_step_annotation(steps[0]), " (harmony under Root - 4 voices)")

    def test_melody_only_defaults_to_false(self):
        """The defaulted field keeps plain construction and the shim working."""
        step = ArrangementStep(
            chord="Cmaj7",
            melody="C5",
            voicing=Voicing(frets=[-1, -1, 9, 9, 8, 8], top_fret=9, avg_fret=8.5),
        )
        self.assertFalse(step.melody_only)
        self.assertEqual(step["melody_only"], False)
        self.assertEqual(step["chord"], "Cmaj7")


if __name__ == "__main__":
    unittest.main()
