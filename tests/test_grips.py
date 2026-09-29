"""Tests for the grip families and the position-aware selector.

These cover the machinery the drop-2 tests cannot: shells, duos, drop-3, close
position, the 6-4-3 shape, the neck window, and the continuity of the chosen position.

The drop-2 path itself stays pinned by tests/test_voicings.py, which must keep passing
unmodified - that is what proves the general generator is a faithful superset of the
hand-authored tables rather than a replacement for them.
"""

import unittest

from musthe import Note

from arranger import (
    BASS_DEGREES_6432,
    DUO_DEGREES,
    GRIP_MAX_SPAN,
    GRIP_STRING_SETS,
    GRIP_PREFERENCE,
    supported_string_sets,
    MELODY_STRING_CHOICES_FULL,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    PITCH_CLASS_NAMES,
    SHELL_DEGREES,
    ChordParser,
    GuitarFretboard,
    Voicing,
    VoiceLeadingEngine,
    format_progression,
)

# A representative spread of the families the library voices well: sevenths, sixths,
# ninths, a half-diminished and a plain triad.
QUALITIES = [
    ("Cmaj7", "maj7"),
    ("Cm7", "m7"),
    ("C6", "6"),
    ("Cm6", "m6"),
    ("C7", "7"),
    ("Cm7b5", "m7b5"),
    ("Cdim7", "dim7"),
    ("Cm9", "m9"),
    ("C13", "13"),
    ("Cmaj", "maj"),
    ("C7sus4", "7sus4"),
]


def note_name(midi):
    """Spells a MIDI number the way the library spells its own transpositions."""
    return f"{PITCH_CLASS_NAMES[midi % 12]}{midi // 12 - 1}"


def root_midi_of(chord_name):
    root, _ = ChordParser.parse_chord_name(chord_name)
    return Note(f"{root}4").midi_note()


def every_chord_tone(chord_name, quality):
    """Every tone of the chord, in the register around middle C."""
    return [
        note_name(root_midi_of(chord_name) + pc)
        for pc in ChordParser.get_chord_tones(quality, chord_name)
    ]





def tones_with_an_inversion(chord_name, quality):
    """
    The chord's tones that DROP2_INTERVAL_SETS actually has an inversion for.

    Several of the extended qualities have no template for every one of their chord
    tones - a 9th-in-top inversion of a 13 chord, for instance - and a melody in one of
    those falls through to the quality-only fallback, which is free to sound a note the
    chord does not contain. That is pre-existing behaviour, and TestKnownTableGaps
    below pins it explicitly so it stays visible instead of being quietly excluded.
    """
    root_pc = root_midi_of(chord_name) % 12
    degrees = VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.get(quality, ())
    return [
        melody
        for melody in every_chord_tone(chord_name, quality)
        if (Note(melody).midi_note() - root_pc) % 12 in degrees
    ]


class TestGripGeneration(unittest.TestCase):
    """Every candidate is a playable shape sounding only chord tones."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_every_grip_obeys_the_playability_invariants(self):
        """Chord tones only, a known string set, the melody on top, a hand's span."""
        seen = set()
        for chord_name, quality in QUALITIES:
            for melody in tones_with_an_inversion(chord_name, quality):
                candidates = self.engine.get_all_grip_voicings(
                    Note(melody), quality, chord_name=chord_name
                )
                self.assertTrue(candidates, f"{chord_name} {melody}")
                tones = set(ChordParser.get_chord_tones(quality, chord_name))
                for v in candidates:
                    where = f"{chord_name} {melody} {v.grip} {v.tab_string()}"
                    self.assertTrue(set(v.pitch_classes()) <= tones, where)
                    self.assertLessEqual(v.fret_span(), 5, where)
                    self.assertTrue(all(0 <= f <= 18 for f in v.active_frets()), where)
                    self.assertEqual(max(v.midi_notes()), Note(melody).midi_note(), where)
                    self.assertEqual(v.soprano_string(), max(v.active_strings), where)
                    self.assertIn(frozenset(v.active_strings), supported_string_sets(), where)
                    seen.add(v.grip)

        # Every family the selector prefers has to be reachable, or a preference entry
        # would be dead weight that silently never applies.
        for grip in GRIP_PREFERENCE:
            self.assertIn(grip, seen, f"no {grip} candidate is ever generated")

    def test_candidate_generation_does_not_filter_by_position(self):
        """No window, no repositioning: generation is pure and selection comes later.

        This is what keeps the grip families and the octave-down rescue independent of
        each other, and it is asserted rather than assumed because a generator that
        filtered here would break that rescue without any visible failure.
        """
        # G5 is fret 15 and A5 fret 17: playable, but above the comfortable window, so
        # they are generated and the *selector* decides what to do with them.
        for melody in ("G5", "A5"):
            self.assertTrue(
                self.engine.get_all_grip_voicings(
                    Note(melody), "m7", chord_name="Dm7"
                ),
                melody,
            )

    def test_a_voicing_carries_its_grip_and_its_lowest_sounding_pitch(self):
        for v in self.engine.get_grip_voicings(
            Note("Bb3"), "m7", chord_name="Gm7", top_string=3
        ):
            self.assertIn(v.grip, GRIP_PREFERENCE)
            self.assertEqual(v.bass_pc, min(v.midi_notes()) % 12)


class TestShellVoicings(unittest.TestCase):
    """A shell states the chord's guide tones and nothing that could contradict them."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_a_seventh_chord_shell_sounds_its_third_and_seventh(self):
        # Each chord is asked for with a melody that is a genuine chord tone of it: a
        # shell cannot be built under a note that is not in the chord.
        for chord_name, quality in (
            ("Cmaj7", "maj7"), ("Am7", "m7"), ("G7", "7"),
        ):
            root_pc = root_midi_of(chord_name) % 12
            third, seventh = SHELL_DEGREES[quality]
            wanted = {(root_pc + third) % 12, (root_pc + seventh) % 12}
            melody = note_name(root_midi_of(chord_name) + third)
            shells = [
                v
                for v in self.engine.get_all_grip_voicings(
                    Note(melody), quality, chord_name=chord_name
                )
                if v.grip == "shell"
            ]
            self.assertTrue(shells, chord_name)
            for v in shells:
                self.assertEqual(len(v.active_frets()), 3, v.tab_string())
                self.assertTrue(wanted <= set(v.pitch_classes()), v.tab_string())

    def test_a_shell_is_never_four_notes(self):
        """The point of a shell is that it stops short of the complete chord."""
        for chord_name, quality in QUALITIES:
            for melody in every_chord_tone(chord_name, quality):
                for v in self.engine.get_all_grip_voicings(
                    Note(melody), quality, chord_name=chord_name
                ):
                    if v.grip != "shell":
                        continue
                    self.assertEqual(len(v.active_frets()), 3, v.tab_string())

    def test_a_quality_with_no_shell_gets_none(self):
        """An unlisted quality has no shell rather than a guessed one."""
        self.assertNotIn("unknown-quality", SHELL_DEGREES)
        self.assertEqual(
            self.engine.get_grip_voicings(
                Note("C5"), "unknown-quality", chord_name="Cunknown-quality",
                grips=("shell",),
            ),
            [],
        )


class TestDuoHardRule(unittest.TestCase):
    """A duo is only ever voiced under a root or a 5th.

    This is a hard rule, with no cost preference behind it. It is also the test that
    would fail if a bare 3rd-and-7th duo ever became reachable: the pitch-class subset
    che
    ck in TestGripGeneration would *not* catch that, because a 3/7 duo consists of
    genuine chord tones - it would simply sound wrong.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_a_duo_is_generated_under_a_root_or_a_fifth(self):
        for chord_name, quality in (("Cmaj7", "maj7"), ("G7", "7"), ("Dm7", "m7")):
            tones = set(ChordParser.get_chord_tones(quality, chord_name))
            for degree in DUO_DEGREES:
                melody = note_name(root_midi_of(chord_name) + degree)
                duos = self.engine.get_all_grip_voicings(
                    Note(melody), quality, chord_name=chord_name, grips=("duo",)
                )
                self.assertTrue(duos, f"{chord_name} {melody} should admit a duo")
                for v in duos:
                    self.assertEqual(len(v.active_frets()), 2, v.tab_string())
                    self.assertTrue(set(v.pitch_classes()) <= tones, v.tab_string())

    def test_no_duo_under_a_third_or_a_seventh(self):
        """A 3rd or 7th in the melody is never answered with two notes."""
        for chord_name, quality in (("Cmaj7", "maj7"), ("G7", "7"), ("Am7", "m7")):
            for degree in SHELL_DEGREES[quality]:
                if degree in DUO_DEGREES:
                    continue
                melody = note_name(root_midi_of(chord_name) + degree)
                self.assertEqual(
                    self.engine.get_all_grip_voicings(
                        Note(melody), quality, chord_name=chord_name, grips=("duo",)
                    ),
                    [],
                    f"{chord_name} {melody} must not admit a duo",
                )

    def test_a_duo_still_carries_the_third(self):
        """
        The second voice is the 3rd, so the pair is never an empty fifth - which would
        leave the chord's quality genuinely unstated.
        """
        for v in self.engine.get_all_grip_voicings(
            Note("C5"), "maj7", chord_name="Cmaj7", grips=("duo",)
        ):
            pcs = set(v.pitch_classes())
            self.assertIn(0, pcs, v.tab_string())   # the root, which is the melody
            self.assertIn(4, pcs, f"{v.tab_string()} is missing the 3rd")


class TestFiveThreeTwoShell(unittest.TestCase):
    """The 5-3-2 grip: A, G and B, with the D string deliberately skipped."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def five_three_two(self, melody, quality, chord_name):
        return [
            v
            for v in self.engine.get_grip_voicings(
                Note(melody), quality, chord_name=chord_name, top_string=4,
                grips=("shell",),
            )
            if v.active_strings == [1, 3, 4]
        ]

    def test_it_produces_the_textbook_shape(self):
        """
        F7 with its seventh in the melody is x-3-x-2-4-x in 5-3-2. The D string is
        skipped, which puts ten semitones of tuning between the A and the G - so the
        frets are nowhere near monotonic in the pitch order (3, 2, 4), and a model
        that assigns the voices by descending pitch across the skipped string gets
        the shape wrong. That is why the placement is a search and not a stack.
        """
        found = self.five_three_two("Eb4", "7", "F7")
        self.assertTrue(found, "F7 should have a 5-3-2 shell under Eb4")
        v = found[0]
        self.assertEqual(v.tab_string(), "x-3-x-2-4-x")
        self.assertEqual(v.active_strings, [1, 3, 4])
        # The D string is left alone, which is what makes this a 5-3-2 and not a 5-4-3.
        self.assertEqual(v.frets[2], -1)
        self.assertEqual(sorted(v.pitch_classes()), [0, 3, 9])
        self.assertEqual(max(v.midi_notes()), Note("Eb4").midi_note())
        self.assertLessEqual(v.fret_span(), 5)

    def test_the_melody_rides_no_higher_than_the_alternatives(self):
        """
        The grip's value is melodic position. Every candidate here carries the melody
        on the B string, and 5-3-2 puts it as low as any of them - the same chord, an
        octave-position further down the neck. It ties the 4-3-2 shell on this
        example; the selector breaks the tie on the remaining cost terms, so the
        point of the assertion is that it is never *worse* on position.
        """
        shells = self.engine.get_grip_voicings(
            Note("Eb4"), "7", chord_name="F7", top_string=4, grips=("shell",)
        )
        by_set = {tuple(v.active_strings): v for v in shells}
        self.assertIn((1, 3, 4), by_set)
        chosen = by_set[(1, 3, 4)]
        self.assertEqual(chosen.soprano_string(), 4)
        self.assertEqual(chosen.frets[4], 4)
        for strings, v in by_set.items():
            if strings == (1, 3, 4):
                continue
            self.assertLessEqual(
                v.frets[4], chosen.frets[4] + 1,
                f"{v.tab_string()} puts the melody far lower than the 5-3-2 does",
            )

    def test_it_is_offered_for_a_b_string_melody(self):
        """A B-string soprano now has five shell shapes available, not four."""
        shells = self.engine.get_grip_voicings(
            Note("G4"), "maj7", chord_name="Cmaj7", top_string=4, grips=("shell",)
        )
        self.assertTrue(shells)
        self.assertTrue(
            any(v.active_strings == [1, 3, 4] for v in shells), "no 5-3-2 offered"
        )
        for v in shells:
            self.assertLessEqual(v.fret_span(), 5, v.tab_string())

    def test_it_is_never_offered_under_a_non_chord_melody(self):
        """
        A shell states this chord's guide tones, so a melody that is not a chord tone
        cannot be voiced in one. Db4 over F7 is a b9 and belongs to an altered
        substitution, not to a shell carrying a b9.
        """
        self.assertEqual(self.five_three_two("Db4", "7", "F7"), [])


class TestSixFourThreeShell(unittest.TestCase):
    """The 6-4-3 grip: low E, D and G, with the A string deliberately skipped."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def six_four_three(self, melody, quality, chord_name):
        return [
            v
            for v in self.engine.get_grip_voicings(
                Note(melody), quality, chord_name=chord_name, top_string=3,
                grips=("shell",),
            )
            if v.active_strings == [0, 2, 3]
        ]

    def test_it_produces_the_textbook_shape(self):
        """
        Gm7 in 6-4-3 is 3-x-3-3-x-x: the fingers line up, and the low E plays a
        *higher* note than the D string beside it. That inversion is the whole reason
        this grip needs its own placement - a model that stacks the voices by pitch gets
        it backwards and lands the fingers eight frets apart.
        """
        found = self.six_four_three("Bb3", "m7", "Gm7")
        self.assertTrue(found, "Gm7 should have a 6-4-3 shell")
        v = found[0]
        self.assertEqual(v.tab_string(), "3-x-3-3-x-x")
        self.assertEqual(v.active_strings, [0, 2, 3])
        # The A string is left alone, which is what makes this a 6-4-3 and not a 6-5-4.
        self.assertEqual(v.frets[1], -1)
        self.assertEqual(sorted(v.pitch_classes()), [5, 7, 10])
        self.assertEqual(max(v.midi_notes()), Note("Bb3").midi_note())

    def test_a_g_string_shell_can_sound_either_shape(self):
        """5-4-3 and 6-4-3 are different grips, and both are offered when they fit."""
        shells = self.engine.get_grip_voicings(
            Note("C4"), "maj7", chord_name="Cmaj7", top_string=3, grips=("shell",)
        )
        self.assertTrue(shells)
        self.assertTrue(any(v.active_strings == [0, 2, 3] for v in shells), "no 6-4-3")
        for v in shells:
            self.assertLessEqual(v.fret_span(), 5, v.tab_string())

    def test_it_is_never_offered_under_a_non_chord_melody(self):
        """
        A shell states this chord's guide tones, so a melody that is not a chord tone
        cannot be voiced in one. G4 over Dm7 is an 11th and belongs to a 7sus4
        substitution, not to a shell with an 11th in it.
        """
        self.assertEqual(self.six_four_three("G4", "m7", "Dm7"), [])


class TestFiveThreeTwoHighEShell(unittest.TestCase):
    """
    The (5,3,2) shell: high E, G and D, with the B string deliberately skipped.

    The *other* 5-3-2 - TestFiveThreeTwoShell covers the (1,3,4) one, which skips the D
    string going down. This one skips the B going up, and it exists to close an
    asymmetry rather than for a grip-specific reason: counting the shell sets by soprano,
    the high E had exactly one shape while the B and the G had two each, and the high E
    is the most-used soprano of all.

    It is also the three-layer split a walking bass wants, which is why the walking-bass
    fixture asserts the upper voices really do land on {5,3,2} rather than being
    approximated with the contiguous shell.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def shells(self, melody, quality, chord_name, top_string=5):
        return [
            v
            for v in self.engine.get_grip_voicings(
                Note(melody), quality, chord_name=chord_name, top_string=top_string,
                grips=("shell",),
            )
            if v.active_strings == [2, 3, 5]
        ]

    def test_it_produces_the_textbook_shape(self):
        """
        Fmaj7 under its 5th is x-x-7-9-x-8: the 3rd (A) on the D string, the 7th (E) on
        the G, the melody (C) on the high E. Both guide tones sound and the root does
        not, which is what a shell is - so the omission of F is correct, not a gap.
        """
        found = self.shells("C5", "maj7", "Fmaj7")
        self.assertTrue(found, "Fmaj7 should have a (5,3,2) shell under C5")
        v = found[0]
        self.assertEqual(v.tab_string(), "x-x-7-9-x-8")
        self.assertEqual(v.active_strings, [2, 3, 5])
        # The B string is left alone, which is what makes this a 5-3-2 and not a 5-4-3.
        self.assertEqual(v.frets[4], -1)
        # A and E are Fmaj7's 3rd and 7th; the root is deliberately absent.
        self.assertEqual(sorted(v.pitch_classes()), [0, 4, 9])
        self.assertEqual(max(v.midi_notes()), Note("C5").midi_note())

    def test_it_is_reachable_across_the_shell_qualities(self):
        """
        A tabulated-but-unreachable set is the failure mode the other 5-3-2's own
        comment warns about, so this sweeps the qualities the library has shells for
        rather than asserting one lucky example.
        """
        found = []
        for chord_name, quality in QUALITIES:
            for melody in every_chord_tone(chord_name, quality):
                for v in self.shells(melody, quality, chord_name):
                    found.append((chord_name, melody, v.tab_string()))
        self.assertTrue(found, "no (5,3,2) shell is reachable anywhere")

    def test_every_shape_it_produces_obeys_the_invariant(self):
        """
        A non-contiguous set is held to exactly the same contract as a contiguous one:
        a supported string set, the melody on the soprano and highest, a span within
        GRIP_MAX_SPAN, and nothing sounding outside the chord.
        """
        checked = 0
        for chord_name, quality in QUALITIES:
            allowed = set(ChordParser.get_chord_tones(quality, chord_name))
            for melody in every_chord_tone(chord_name, quality):
                for v in self.shells(melody, quality, chord_name):
                    checked += 1
                    label = f"{chord_name} {melody} {v.tab_string()}"
                    self.assertEqual(len(v.active_frets()), 3, label)
                    self.assertIn(
                        frozenset(v.active_strings), supported_string_sets(), label
                    )
                    self.assertEqual(v.soprano_string(), 5, label)
                    self.assertEqual(max(v.midi_notes()), Note(melody).midi_note(), label)
                    self.assertLessEqual(v.fret_span(), GRIP_MAX_SPAN["shell"], label)
                    self.assertTrue(set(v.pitch_classes()) <= allowed, label)
        self.assertGreater(checked, 0, "the sweep proved nothing")

    def test_it_is_offered_for_a_high_e_melody(self):
        """
        The set is keyed on soprano 5, so a high-E shell now has two shapes to choose
        between instead of one.
        """
        shells = self.engine.get_grip_voicings(
            Note("C5"), "maj7", chord_name="Fmaj7", top_string=5, grips=("shell",)
        )
        self.assertTrue(shells)
        self.assertTrue(
            any(v.active_strings == [2, 3, 5] for v in shells), "no (5,3,2) offered"
        )
        for v in shells:
            self.assertLessEqual(v.fret_span(), GRIP_MAX_SPAN["shell"], v.tab_string())

    def test_it_is_not_offered_for_a_b_or_g_melody(self):
        """
        The set is keyed on soprano 5, so it must not leak onto the other two sopranos -
        otherwise a shape generated for a B-string melody would put the melody on the
        high E, which is a different grip entirely.
        """
        for top_string in (4, 3):
            for chord_name, quality in QUALITIES:
                for melody in every_chord_tone(chord_name, quality):
                    for v in self.engine.get_grip_voicings(
                        Note(melody), quality, chord_name=chord_name,
                        top_string=top_string, grips=("shell",),
                    ):
                        self.assertNotEqual(
                            v.active_strings, [2, 3, 5],
                            f"(5,3,2) offered for top_string={top_string}: "
                            f"{v.tab_string()}",
                        )

    def test_it_is_never_offered_under_a_non_chord_melody(self):
        """
        A shell states this chord's guide tones, so a melody that is not a chord tone
        cannot be voiced in one. Db5 over Fmaj7 is its b13 and belongs to an altered
        substitution, not to a shell with a b13 in it.
        """
        self.assertEqual(self.shells("Db5", "maj7", "Fmaj7"), [])

    def test_the_high_e_soprano_is_no_longer_the_only_poorly_served_one(self):
        """
        The asymmetry that motivated the set, asserted on the table so a later removal
        cannot pass unnoticed: before it, soprano 5 had one shell shape while the B and
        the G sopranos had two each.
        """
        by_soprano = {}
        for strings, soprano in GRIP_STRING_SETS["shell"]:
            by_soprano.setdefault(soprano, []).append(frozenset(strings))
        # Compared as sets: the table stores each one low-to-high, and sorting frozensets
        # would order them by size rather than by content.
        self.assertEqual(
            set(by_soprano[5]), {frozenset((2, 3, 5)), frozenset((3, 4, 5))}
        )
        self.assertIn(frozenset((2, 3, 5)), supported_string_sets())
        self.assertEqual(len(by_soprano[4]), 2)
        self.assertEqual(len(by_soprano[3]), 2)


class TestSixFourThreeTwo(unittest.TestCase):
    """
    6-4-3-2: low E, D, G and B, with the A string skipped so the bass can be a root.

    This is the one default four-note set that reaches the low E. With 5-4-3-2 the lowest
    sounding note is always on the A string, so a root bass is a consequence of the
    string set rather than a decision; here it is chosen, and BASS_DEGREES_6432 is the
    rule that chooses it.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def shapes(self, melody, quality, chord_name, grip="drop2_6432"):
        return [
            v
            for v in self.engine.get_grip_voicings(
                Note(melody), quality, chord_name=chord_name,
                top_string=4, grips=(grip,),
            )
            if v.active_strings == [0, 2, 3, 4]
        ]

    def test_it_produces_the_textbook_shape(self):
        """
        Am7 under an E4 melody on the B string is 5-x-5-5-5-x: A2, G3, C4, E4.

        The A string being absent is the whole point of the shape - it is what frees the
        low E to play the root - and the four fingers line up, so span is zero.
        """
        found = self.shapes("E4", "m7", "Am7")
        self.assertTrue(found, "Am7 should have a 6-4-3-2 under E4")
        self.assertEqual(found[0].tab_string(), "5-x-5-5-5-x")
        self.assertEqual(found[0].frets[1], -1)
        self.assertEqual(found[0].fret_span(), 0)
        self.assertEqual(
            [note_name(m) for m in found[0].midi_notes()], ["A2", "G3", "C4", "E4"]
        )

    def test_the_bass_rule_holds_everywhere(self):
        """
        The low E always carries the chord's root or its 5th, never a 3rd or a 7th.

        Swept across the qualities the library knows, in four roots so the rule is not
        pinned to one transposition. The lowest voice is what *defines* the chord, so
        this is the difference between voicing this harmony and sounding a different one.
        """
        seen = 0
        for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT):
            canonical = ChordParser.canonical_quality(quality)
            tones = ChordParser.CHORD_TONES_FROM_ROOT[canonical]
            for root in ("C", "F#", "Bb", "Eb"):
                root_pc = Note(root + "4").midi_note() % 12
                for degree in tones:
                    for midi in range(48, 76):
                        if midi % 12 != (root_pc + degree) % 12:
                            continue
                        melody = note_name(midi)
                        chord_name = root + canonical
                        for v in self.shapes(melody, canonical, chord_name):
                            seen += 1
                            bass_pc = GuitarFretboard.fret_to_midi(0, v.frets[0]) % 12
                            self.assertIn(
                                (bass_pc - root_pc) % 12, BASS_DEGREES_6432,
                                f"{chord_name} {melody} {v.tab_string()}",
                            )
        self.assertGreater(seen, 100, "the sweep found almost nothing to check")

    def test_it_obeys_every_playability_invariant(self):
        """
        The known string set, the melody on the B and on top, a hand's span, and only
        chord tones - checked over the same sweep, so no single case is special.
        """
        for chord_name, quality in QUALITIES:
            root_pc = root_midi_of(chord_name) % 12
            allowed = set(ChordParser.get_chord_tones(quality, chord_name))
            for degree in ChordParser.CHORD_TONES_FROM_ROOT[quality]:
                for midi in range(48, 76):
                    if midi % 12 != (root_pc + degree) % 12:
                        continue
                    melody = note_name(midi)
                    for v in self.shapes(melody, quality, chord_name):
                        where = f"{chord_name} {melody} {v.tab_string()}"
                        self.assertEqual(v.active_strings, [0, 2, 3, 4], where)
                        self.assertEqual(v.soprano_string(), 4, where)
                        self.assertEqual(max(v.midi_notes()), midi, where)
                        self.assertLessEqual(
                            v.fret_span(), GRIP_MAX_SPAN["drop2_6432"], where
                        )
                        self.assertTrue(set(v.pitch_classes()) <= allowed, where)
                        self.assertTrue(all(0 <= f <= 18 for f in v.active_frets()), where)
                        self.assertIn(
                            frozenset(v.active_strings), supported_string_sets(), where
                        )


    def test_the_search_picks_the_shape_a_player_would(self):
        """
        Ties are broken by fret spread, then by position - so the answer is the tightest
        hand position, not the first one the search reaches.

        This is not cosmetic. An unranked search returns the low-E-first combination it
        happens to meet, which puts the low E at fret 0-1, below the neck window; ranked
        properly the same generator answers `5-x-5-5-5-x`. The earlier "0 of 22, never
        selected" measurement was that bug, not a property of the shape.
        """
        for chord_name, quality, melody, expected in (
            ("Am7", "m7", "E4", "5-x-5-5-5-x"),
            ("Cmaj7", "maj7", "E4", "3-x-5-4-5-x"),
            ("Fm7", "m7", "Eb4", "1-x-1-1-4-x"),
        ):
            found = self.shapes(melody, quality, chord_name)
            self.assertTrue(found, chord_name)
            self.assertEqual(found[0].tab_string(), expected, chord_name)

    def test_it_reaches_melodies_the_contiguous_block_cannot(self):
        """
        A B3 melody over Cmaj7, and a C5 over Fm7, are both voicable on 6-4-3-2 and
        neither is voicable on 5-4-3-2 - the A string at the same position would have to
        sit outside the span. So the new set is not only a different bass, it is
        additional coverage.
        """
        for chord_name, quality, melody in (
            ("Cmaj7", "maj7", "B3"),
            ("Fm7", "m7", "C5"),
        ):
            self.assertTrue(self.shapes(melody, quality, chord_name), chord_name)
            self.assertEqual(
                [
                    v
                    for v in self.engine.get_grip_voicings(
                        Note(melody), quality, chord_name=chord_name,
                        top_string=4, grips=("drop2",),
                    )
                    if v.active_strings == [0, 2, 3, 4]
                ],
                [],
                chord_name,
            )

    def test_where_no_root_fits_the_contiguous_block_is_used_instead(self):
        """
        A melody the new set cannot serve must cost the step nothing.

        F#4 over Cmaj7 is neither the root nor the 5th, so no low E pitch is legal in
        any position: the placement returns None and 5-4-3-2 voices the chord as before.
        This is the negative case that keeps the grip from becoming a filter.
        """
        self.assertEqual(self.shapes("F#4", "maj7", "Cmaj7"), [])
        contig = self.engine.get_grip_voicings(
            Note("F#4"), "maj7", chord_name="Cmaj7", top_string=4, grips=("drop2",)
        )
        self.assertTrue(contig, "the contiguous block must still serve this melody")
        self.assertTrue(all(v.active_strings == [1, 2, 3, 4] for v in contig))

    def test_a_rootless_chord_gets_nothing(self):
        """
        The rule is measured from the root, so a chord with no root to measure against
        cannot place one - and guessing would be putting an arbitrary note in the bass.
        """
        self.assertEqual(
            self.engine.get_grip_voicings(
                Note("E4"), "m7", chord_name=None, top_string=4,
                grips=("drop2_6432",),
            ),
            [],
        )

    def test_it_is_reachable_through_the_public_entry_point(self):
        """
        The family needs no bespoke wrapper: `get_grip_voicings(grips=...)` is the same
        public surface every other family is reached through.
        """
        voicings = self.engine.get_all_grip_voicings(
            Note("E4"), "m7", chord_name="Am7", top_strings=(4,),
            grips=("drop2_6432",),
        )
        self.assertEqual([v.tab_string() for v in voicings], ["5-x-5-5-5-x"])
        self.assertEqual(voicings[0].grip, "drop2_6432")


class TestStringSetTable(unittest.TestCase):
    """The GRIP_STRING_SETS table itself, which the generated paths do not read."""

    def test_every_grip_family_has_a_span_limit(self):
        """
        Every family in GRIP_STRING_SETS is also in GRIP_MAX_SPAN, and vice versa.

        The two tables are read independently - the span by `_place_template` and
        `_place_shell`, the sets by `_string_sets_for` - so a family added to one and
        not the other would fail with a bare KeyError deep inside placement, naming
        neither the grip nor the omission. The two-note families are held to 4 rather
        than 5 for the same reason a duo is: two fingers, no reason to stretch.
        """
        self.assertEqual(
            set(GRIP_STRING_SETS), set(GRIP_MAX_SPAN),
            "a grip family is missing from one of the two tables",
        )
        self.assertEqual(GRIP_MAX_SPAN["duo"], 4)
        self.assertEqual(GRIP_MAX_SPAN["interval"], 4)

    def test_an_interval_uses_the_same_sets_as_a_duo(self):
        """
        The `interval` grip sits on the three adjacent pairs, exactly as a duo does.

        Stated rather than assumed, because the two families differ in the *rule* that
        builds them and not in where they sit - see `_interval_offsets`. A wider set
        would be a change to the playability contract, not a detail.
        """
        self.assertEqual(
            [list(s) for s, _ in GRIP_STRING_SETS["interval"]],
            [list(s) for s, _ in GRIP_STRING_SETS["duo"]],
        )
        for strings, soprano in GRIP_STRING_SETS["interval"]:
            self.assertEqual(len(strings), 2)
            # String indices run 0 = low E to 5 = high E, so the soprano is the
            # *first* of a pair and the highest index in it.
            self.assertEqual(soprano, max(strings))

    def test_every_entry_names_its_own_soprano(self):
        """
        Each entry must list a soprano string that is actually in its set. An entry that
        does not is silently wrong: the drop-2 path computes its own string set and
        never consults the table, so the mistake survives every behavioural test and
        only shows up in the documented invariant.
        """
        for grip, shapes in GRIP_STRING_SETS.items():
            for strings, soprano in shapes:
                self.assertIn(
                    soprano, strings, f"{grip}: {sorted(strings)} with soprano {soprano}"
                )

    def test_the_bottom_four_strings_carry_no_four_note_shape(self):
        """
        6-5-4-3 with the melody on top does not sound good, so no four-note grip may
        occupy it. A low melody is harmonised with a three-note shell instead - and
        both shell shapes, 5-4-3 and 6-4-3, are offered so the selector can choose.

        6-4-3-2 is *also* non-contiguous, and is deliberately not caught by this rule:
        it swaps the A string out for the B, so its lowest note is on the low E while
        its soprano is the B rather than the G. The two rules must not be conflated by a
        later reader - 6-4-3-2 is the fix for a bass, not an exception to the exclusion.
        """
        bottom_four = {0, 1, 2, 3}
        for grip in ("drop2", "drop3", "closed", "drop2_6432"):
            for strings, soprano in GRIP_STRING_SETS[grip]:
                self.assertNotEqual(frozenset(strings), bottom_four, grip)
        for grip in ("drop2", "drop3", "closed"):
            for strings, soprano in GRIP_STRING_SETS[grip]:
                self.assertNotEqual(soprano, 3, f"{grip} still offers a G-string block")
        self.assertNotIn(bottom_four, supported_string_sets())
        # 6-4-3-2 does reach the low E, which is the entire reason it exists.
        self.assertEqual(GRIP_STRING_SETS["drop2_6432"], (((0, 2, 3, 4), 4),))
        self.assertIn(frozenset((0, 2, 3, 4)), supported_string_sets())

        # Both G-string shell shapes are on the table, so the selector may choose either.
        g_shells = [
            strings
            for strings, soprano in GRIP_STRING_SETS["shell"]
            if soprano == 3
        ]
        self.assertEqual([list(s) for s in g_shells], [[1, 2, 3], [0, 2, 3]])

        # And a 6-4-3 is genuinely reachable, not merely tabulated. It is not reachable
        # for *every* low melody - a Gm7 shell under its 5th wants a six-fret span - so
        # this is a claim that it appears, not that it always wins.
        found = [
            v.tab_string()
            for chord_name, quality in (("Cmaj7", "maj7"), ("Gm7", "m7"), ("G7", "7"))
            for melody in every_chord_tone(chord_name, quality)
            for v in VoiceLeadingEngine.get_grip_voicings(
                Note(melody), quality, chord_name=chord_name,
                top_string=3, grips=("shell",),
            )
            if v.active_strings == [0, 2, 3]
        ]
        self.assertTrue(found, "no 6-4-3 shell is reachable anywhere")

    def test_a_g_string_melody_never_gets_four_voices(self):
        """The end-to-end statement of the same rule, on the arranged result."""
        for chord_name, quality in (("Cmaj7", "maj7"), ("Dm7", "m7"), ("G7", "7")):
            for melody in every_chord_tone(chord_name, quality):
                steps = VoiceLeadingEngine.arrange_progression(
                    [(melody, quality, chord_name)]
                )
                for step in steps:
                    if step.voicing.soprano_string() != 3:
                        continue
                    self.assertLessEqual(
                        len(step.voicing.active_frets()), 3,
                        f"{chord_name} {melody} -> {step.tab_line()}",
                    )


class TestSopranoStringChoices(unittest.TestCase):
    """The melody may be voiced on the high E, the B or the G string - and only those."""

    def test_the_soprano_set_is_the_three_upper_strings(self):
        """The A string and the low E are inner voices; no grip puts the melody there."""
        self.assertEqual(MELODY_STRING_CHOICES_FULL, (5, 4, 3))

    def test_a_low_melody_is_voiced_on_a_lower_string(self):
        """
        D4 and C4 sit at the very bottom of the B string's range, so the melody is
        voiced there or below it - never on the high E, which cannot reach it at all.

        Which of the lower strings wins depends on the shape available: C4 over Cmaj7
        takes a 6-4-3 shell on the G string, while D4 over Dm7 takes a complete
        four-note chord on the B string, because a full chord outranks a duo even
        though that costs a string.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D4", "m7", "Dm7"), ("C4", "maj7", "Cmaj7")]
        )
        self.assertEqual(len(steps), 2)
        for step in steps:
            self.assertIn(step.voicing.soprano_string(), (3, 4))
            self.assertEqual(
                max(step.voicing.midi_notes()), Note(step.melody).midi_note()
            )
        # The Cmaj7 uses a three-note shell on the G string - 5-4-3 here, with 6-4-3
        # offered alongside it and the selector choosing on position.
        self.assertEqual(steps[1].grip, "shell")
        self.assertEqual(steps[1].voicing.soprano_string(), 3)

    def test_restricting_the_soprano_set_restores_the_old_behaviour(self):
        """top_strings=(5,) skips what the lower strings used to rescue."""
        self.assertEqual(
            VoiceLeadingEngine.arrange_progression(
                [("D4", "m7", "Dm7")], top_strings=(5,)
            ),
            [],
        )


class TestFretWindow(unittest.TestCase):
    """The window is a strong preference, never a filter."""

    def test_the_arrangement_sits_inside_the_window(self):
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")]
        )
        for step in steps:
            for fret in step.voicing.active_frets():
                self.assertGreaterEqual(fret, NECK_FRET_MIN, step.tab_line())
                self.assertLessEqual(fret, NECK_FRET_MAX, step.tab_line())

    def test_a_melody_off_the_end_of_the_board_is_still_dropped(self):
        """
        C6 is fret 20 - unplayable, not merely out of position - so the step goes, and
        the following step must still be arranged rather than left with no previous
        voicing to measure against.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C6", "m7", "Dm7"), ("D5", "m7", "Dm7")]
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].melody, "D5")

    def test_the_window_bounds_are_honoured_when_narrowed(self):
        """A caller can ask for a different window and the selector obeys it."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7")], fret_min=1, fret_max=4
        )
        self.assertTrue(steps)
        for step in steps:
            for fret in step.voicing.active_frets():
                self.assertLessEqual(fret, 4, step.tab_line())


class TestPositionContinuity(unittest.TestCase):
    """The selector's first job is to keep the hand where it already was."""

    def test_no_large_jump_between_consecutive_chords(self):
        progression = [
            ("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7"),
            ("E5", "m7", "Am7"), ("D5", "7", "G7"), ("C5", "maj7", "Cmaj7"),
        ]
        steps = VoiceLeadingEngine.arrange_progression(progression)
        self.assertEqual(len(steps), len(progression))
        for previous, step in zip(steps, steps[1:]):
            jump = abs(step.voicing.avg_fret - previous.voicing.avg_fret)
            self.assertLessEqual(
                jump, 3.0, f"{previous.tab_line()} -> {step.tab_line()}"
            )

    def test_a_repeated_melody_keeps_its_fret(self):
        """A melody that repeats keeps its place rather than sliding down the neck."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("D5", "7", "G7"), ("D5", "m7b5", "Dm7b5")]
        )
        frets = [s.voicing.fret_on_soprano for s in steps]
        self.assertLessEqual(max(frets) - min(frets), 5, frets)

    def test_the_soprano_may_change_string_to_hold_its_position(self):
        """
        The point of the extra soprano string: a melodic position can be held by moving
        to a different string, which is a far smaller gesture than moving the hand, and
        it is a legitimate answer to a melody the high E cannot reach.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("A4", "m7", "Dm7"), ("A4", "7", "G7"), ("A4", "maj7", "Cmaj7")]
        )
        self.assertTrue(steps)
        for step in steps:
            self.assertEqual(max(step.voicing.midi_notes()), Note("A4").midi_note())


class TestSelectionDeterminism(unittest.TestCase):
    """The engine is pure, so its output is worth asserting on."""

    def test_the_same_progression_arranges_identically_twice(self):
        progression = [
            ("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7"),
        ]
        first = VoiceLeadingEngine.arrange_progression(progression)
        second = VoiceLeadingEngine.arrange_progression(progression)
        self.assertEqual([s.tab_line() for s in first], [s.tab_line() for s in second])

    def test_pinning_the_grips_reproduces_a_fixed_arrangement(self):
        """
        grips=("drop2",) with the old soprano set is this library's original behaviour,
        so a caller who needs a known arrangement rather than the best one can ask for
        it - which is also what lets the renderer tests pin their fixture.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
            grips=("drop2",),
        )
        self.assertTrue(all(s.grip == "drop2" for s in steps))
        self.assertEqual(
            [s.tab_line() for s in steps],
            ["x-x-10-10-10-10", "x-x-5-7-6-7", "x-x-9-9-8-8"],
        )


class TestPartialHarmonisation(unittest.TestCase):
    """A partial shape is reported, because the chord name alone would overstate it."""

    def test_a_partial_step_is_flagged_and_annotated(self):
        """
        F5 over F7 high on the neck has no four-note shape inside the window, so it
        resolves to a two-note duo - and the renderers say so, because the chord name
        above a duo describes a harmony that is not fully sounding.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("A5", "m7", "Dm7"), ("G5", "maj7", "Cmaj7"), ("F5", "7", "F7")]
        )
        partial = [s for s in steps if s.partial]
        self.assertTrue(partial, "expected at least one partial harmonisation")
        for step in partial:
            self.assertLess(len(step.voicing.active_frets()), 4)
            self.assertIn(step.grip, ("shell", "duo"))
        # F5 is the *root* of F7, so the hard rule permits a duo here - the ear supplies
        # the guide tones - and the second voice is the 3rd, so the chord's quality is
        # still stated rather than left as an empty fifth.
        duo = [s for s in partial if s.grip == "duo"]
        self.assertTrue(duo, [s.tab_line() for s in partial])
        for step in duo:
            pcs = set(step.voicing.pitch_classes())
            self.assertIn(5, pcs, step.tab_line())    # F, the root in the melody
            self.assertIn(9, pcs, step.tab_line())    # A, the 3rd
        self.assertIn("partial", format_progression(steps))

    def test_a_full_chord_is_preferred_wherever_one_fits(self):
        """
        A partial harmonisation is a fallback, not a style: where a complete chord can
        be played, it wins even if the shell would have held the position better.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C5", "m7b5", "Am7b5"), ("C5", "7b9", "D7b9"), ("Bb4", "m6", "Gm6")]
        )
        self.assertTrue(steps)
        self.assertFalse(any(s.partial for s in steps), [s.tab_line() for s in steps])

    def test_a_full_four_note_step_is_not_flagged(self):
        step = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7")], top_strings=(5,), grips=("drop2",)
        )[0]
        self.assertFalse(step.partial)
        self.assertEqual(step.grip, "drop2")
        self.assertEqual(len(step.voicing.active_frets()), 4)

    def test_the_grip_is_carried_onto_the_step_and_its_voicing(self):
        for step in VoiceLeadingEngine.arrange_progression(
            [("D4", "m7", "Dm7"), ("D4", "7", "G7"), ("C4", "maj7", "Cmaj7")]
        ):
            self.assertEqual(step.grip, step.voicing.grip)
            self.assertIn(step.grip, GRIP_PREFERENCE)


class TestKnownTableGaps(unittest.TestCase):
    """Pre-existing gaps in the hand-authored drop-2 tables, pinned so they stay visible.

    These are not regressions and are not fixed here - completing the tables is a
    separate piece of work, and changing them would change the published drop-2 output.
    Pinning them means the next person to touch the tables finds a failing test that
    tells them the gap closed, rather than a passing test that hid it.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_generation_offers_impure_shapes_but_the_selector_refuses_them(self):
        """
        A 9th in the melody of a 13 chord has no matching inversion in the table, so
        the quality-only fallback is offered and it is free to sound a note the chord
        does not contain. Generation is pure and still offers them - changing the tables
        would change the published drop-2 output and is a separate piece of work - but
        voicing_cost's first criterion is tone purity, so the arrangement never picks
        one while a correct shape exists.
        """
        tones = set(ChordParser.get_chord_tones("13", "C13"))
        impure = [
            v
            for v in self.engine.get_all_drop2_voicings(
                Note("D4"), "13", chord_name="C13"
            )
            if not set(v.pitch_classes()) <= tones
        ]
        self.assertTrue(impure, "the table gap closed - update this test and the tables")
        for v in impure:
            self.assertEqual(
                self.engine.voicing_cost(v, previous=None, allowed_tones=tones)[0], 1.0
            )

    def test_tone_purity_outranks_the_neck_window(self):
        """
        A correct chord slightly out of position beats a wrong note inside it: a wrong
        note is not playable at all, whereas position is only awkward.
        """
        tones = set(ChordParser.get_chord_tones("13", "C13"))
        impure = [
            v
            for v in self.engine.get_all_drop2_voicings(
                Note("D4"), "13", chord_name="C13"
            )
            if not set(v.pitch_classes()) <= tones
        ]
        pure = [
            v
            for v in self.engine.get_all_grip_voicings(
                Note("D4"), "13", chord_name="C13"
            )
            if set(v.pitch_classes()) <= tones
        ]
        self.assertTrue(impure and pure)
        for good in pure:
            for bad in impure:
                self.assertLess(
                    self.engine.voicing_cost(good, None, allowed_tones=tones),
                    self.engine.voicing_cost(bad, None, allowed_tones=tones),
                )

    def test_the_arranged_result_still_sounds_only_chord_tones(self):
        """
        Whatever the tables do internally, the arrangement the caller receives has to be
        musically correct - that is the promise the library makes, and the selector is
        what keeps it.
        """
        for chord_name, quality in QUALITIES:
            for melody in every_chord_tone(chord_name, quality):
                tones = set(ChordParser.get_chord_tones(quality, chord_name))
                for step in VoiceLeadingEngine.arrange_progression(
                    [(melody, quality, chord_name)]
                ):
                    self.assertTrue(
                        set(step.voicing.pitch_classes()) <= tones,
                        f"{chord_name} {melody} -> {step.tab_line()}",
                    )


class TestVoicingCost(unittest.TestCase):
    """The selection rule itself, asserted rather than only through its results."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_a_voicing_inside_the_window_pays_no_window_penalty(self):
        v = self.engine.get_drop2_voicings(Note("C5"), "maj7", chord_name="Cmaj7")[0]
        self.assertEqual(self.engine.voicing_cost(v, previous=v)[1], 0.0)

    def test_a_voicing_outside_the_window_is_penalised(self):
        """F5 sits at fret 13 on the high E (inside the window) but at fret 18 on the B
        string, which is not. A candidate that far out has to be marked as such."""
        candidates = self.engine.get_drop2_voicings(
            Note("F5"), "maj7", chord_name="Cmaj7", top_string=4
        )
        self.assertTrue(candidates)
        costs = [self.engine.voicing_cost(v, previous=v)[1] for v in candidates]
        self.assertTrue(any(c > 0 for c in costs), costs)

    def test_missing_voices_come_last(self):
        """A partial harmonisation is only ever chosen when nothing fuller fits."""
        shells = self.engine.get_grip_voicings(
            Note("B4"), "maj7", chord_name="Cmaj7", grips=("shell",)
        )
        self.assertTrue(shells)
        self.assertEqual(self.engine.voicing_cost(shells[0], previous=None)[2], 1.0)

    def test_the_selector_really_is_the_argmin_of_the_cost(self):
        candidates = self.engine.get_all_grip_voicings(
            Note("C5"), "maj7", chord_name="Cmaj7"
        )
        self.assertTrue(candidates)
        best = self.engine._best_voicing(candidates, previous=None)
        self.assertIsNotNone(best)
        assert best is not None  # pyright does not narrow through assertIsNotNone
        for v in candidates:
            self.assertLessEqual(
                self.engine.voicing_cost(best, None),
                self.engine.voicing_cost(v, None),
            )

    def test_a_root_or_fifth_bass_breaks_an_exact_tie(self):
        """
        The bass-function term scores 0 for a root or 5th and 1 otherwise.

        Dm7/F4 is the case that needed it: the contiguous 5-4-3-2 and the 6-4-3-2 tie on
        every earlier criterion, and without this term the better bass loses on the grip
        tie-break. It applies to whichever shape won, not to one family, so a contiguous
        shape with a root bass is not penalised either.
        """
        candidates = self.engine.get_grip_voicings(
            Note("F4"), "m7", chord_name="Dm7", top_string=4,
            grips=("drop2", "drop2_6432"),
        )
        self.assertTrue(candidates)
        root_pc = Note("D4").midi_note() % 12
        for v in candidates:
            bass_ok = (v.bass_pc - root_pc) % 12 in BASS_DEGREES_6432
            self.assertEqual(
                self.engine.voicing_cost(v, None, root_pc=root_pc)[6],
                0.0 if bass_ok else 1.0,
                v.tab_string(),
            )

    def test_the_bass_term_is_consulted_last_and_only_when_it_can_be(self):
        """
        It sits at index 6, below every criterion that protects correctness, and it is
        skipped entirely without a root - an unparseable chord name gets the old
        behaviour rather than a guessed bass.
        """
        candidates = self.engine.get_grip_voicings(
            Note("F4"), "m7", chord_name="Dm7", top_string=4, grips=("drop2",)
        )
        self.assertTrue(candidates)
        v = candidates[0]
        without_root = self.engine.voicing_cost(v, None)
        with_root = self.engine.voicing_cost(
            v, None, root_pc=Note("D4").midi_note() % 12
        )
        # The tuple is a fixed width whether or not a root is supplied, so `root_pc`
        # only ever changes a *value*; it never reshapes the cost or reorders the
        # criteria above it. That is what keeps `voicing_cost` a total order and the
        # engine deterministic.
        self.assertEqual(len(with_root), len(without_root))
        self.assertEqual(with_root[:6], without_root[:6], v.tab_string())
        self.assertNotEqual(with_root[6], without_root[6], v.tab_string())
        # A bass that is a 3rd or a 7th still scores 1.0. No contiguous Dm7 drop-2 has
        # one - they all put D or A underneath - so this sweeps for a chord that does,
        # pairing each shape with the chord it was actually generated for, because the
        # term reads the *root*, not the shape.
        checked = 0
        for chord, quality in QUALITIES:
            root_pc = root_midi_of(chord) % 12
            for melody in every_chord_tone(chord, quality):
                for v in self.engine.get_grip_voicings(
                    Note(melody), quality, chord_name=chord, top_string=4,
                    grips=("drop2",),
                ):
                    bass_ok = (v.bass_pc - root_pc) % 12 in BASS_DEGREES_6432
                    self.assertEqual(
                        self.engine.voicing_cost(v, None, root_pc=root_pc)[6],
                        0.0 if bass_ok else 1.0,
                        f"{chord} {melody} {v.tab_string()}",
                    )
                    checked += 1
        self.assertGreater(checked, 20, "the sweep found almost nothing to check")

    def test_the_first_chord_starts_near_the_middle_of_the_neck(self):
        """With nothing to lead from, "stay in position" becomes "start somewhere sane"."""
        steps = VoiceLeadingEngine.arrange_progression([("D5", "m7", "Dm7")])
        self.assertEqual(len(steps), 1)
        self.assertLessEqual(abs(steps[0].voicing.avg_fret - 9), 4.0)


class TestVoicingAccessors(unittest.TestCase):
    """The small accessors the selector reads."""

    def test_active_strings_and_soprano_fret(self):
        v = Voicing(frets=[-1, 10, 10, 10, 10, -1], top_fret=10, avg_fret=10.0)
        self.assertEqual(v.active_strings, [1, 2, 3, 4])
        self.assertEqual(v.soprano_string(), 4)
        self.assertEqual(v.fret_on_soprano, 10)

    def test_a_muted_voicing_reports_nothing_sounding(self):
        v = Voicing(frets=[-1] * 6, top_fret=0, avg_fret=0.0)
        self.assertEqual(v.soprano_string(), -1)
        self.assertEqual(v.fret_on_soprano, -1)
        self.assertEqual(v.fret_span(), 0)
        self.assertIsNone(v.bass_pc)


if __name__ == "__main__":
    unittest.main()
