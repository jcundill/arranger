"""The drop-2 tables are generated, and this is what holds the rule to them.

`TONE_PRIORITY` says which of a chord's tones a shape states, in what order, one row per
quality; `grips._priority_drop2_templates` turns a row into the drop-2 templates and
`DROP2_TEMPLATES` is the live table the engine reads. `DROP2_INTERVAL_SETS` is the
hand-written table that generation reproduces, and it is kept as the witness: the
assertion below compares the two rather than trusting either.

The rule is not a refactor of the table, and these tests are shaped to say so. The table
is 119 numbers that encode a musical decision - which tone a four-voice shape gives up
when the chord has five tones - and the decision is a *different* one per quality, which
is why the row order is the rule and there is no single global order that reproduces
them. `TestTheOmissionDecision` pins that per quality and by name, so a row edited into a
tidier shared pattern fails here and says which quality moved.

This file is the only place the two tables meet. If it is ever deleted, the rule becomes
unverified and the hand table becomes decorative.
"""

import unittest

from arranger import SHELL_DEGREES, ChordParser, VoiceLeadingEngine
from arranger.grips import DROP2_TEMPLATES, TONE_PRIORITY, stated_tones

#: The acceptance gate's denominator. `docs/engine.md` had said "109 hand-authored
#: templates" while the table held 119, which is why the count is asserted rather than
#: described in prose: a table that shrank, or a quality whose row stopped generating,
#: cannot pass quietly.
QUALITY_COUNT = 29
TEMPLATE_COUNT = 119


class TestTheRuleReproducesTheTables(unittest.TestCase):
    """The generated templates are the hand-written ones, for every quality."""

    def test_every_quality_with_a_table_has_a_priority_row(self):
        """A quality the drop-2 generator is expected to voice names its tones somewhere."""
        for quality in VoiceLeadingEngine.DROP2_INTERVAL_SETS:
            canonical = ChordParser.canonical_quality(quality)
            self.assertIn(
                canonical, TONE_PRIORITY, f"{quality} canonicalises to {canonical}"
            )

    def test_the_generated_templates_are_the_hand_written_table(self):
        """Every one of the 119 templates, to the semitone and in the same order.

        This is the assertion the arrangement rests on: it is what lets
        `_interval_set_for_grip` read the rule and leave the table as its witness.
        """
        checked = 0
        for quality, degrees in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.items():
            table = VoiceLeadingEngine.DROP2_INTERVAL_SETS[quality]
            generated = DROP2_TEMPLATES[quality]
            self.assertEqual(len(generated), len(degrees), quality)
            for degree, want, got in zip(degrees, table, generated):
                checked += 1
                self.assertEqual(
                    got, want,
                    f"{quality} with degree {degree} in the melody: "
                    f"generated {got}, table says {want}",
                )
        self.assertEqual(checked, TEMPLATE_COUNT)
        self.assertEqual(len(TONE_PRIORITY), QUALITY_COUNT)

    def test_a_degree_rows_content_is_a_prefix_of_the_rule(self):
        """What a row *says* is the rule's; only the order it says it in is its own.

        `DEGREE_OFFSETS_FROM_ROOT` is what the melodic route indexes the templates by, and it
        is the table Step 3 of `docs/generated-grips.md` retires. Measured over all 29 rows:
        every row holds the **prefix** of that quality's `TONE_PRIORITY` row, cut to the length
        of the template list, and not one of them holds it in the rule's order - so the row
        carries an order and nothing else, which is exactly what a retirement has left to
        decide.

        That is worth asserting because `test_the_generated_templates_are_the_hand_written_table`
        cannot see it: it compares generated templates to the table's in the row's own order, so
        any permutation of a row's degrees agrees with itself. A row given a tone its quality
        does not have fails here and says which quality moved. The five rows *shorter* than
        their priority row are the qualities with more tones than a template list covers
        (`13`, `7#11`, `7b13`, `maj7#11`, and `7alt` two tones over), and this rule is what
        makes that a property of the rule rather than a number someone typed.

        Nothing here asserts the order, and a row later reordered *into* the rule's order would
        pass: that would be the simplification, not a defect.
        """
        for quality, degrees in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.items():
            canonical = ChordParser.canonical_quality(quality)
            priority = TONE_PRIORITY[canonical]
            self.assertEqual(
                set(degrees),
                set(priority[: len(degrees)]),
                f"{quality}: {degrees} is not the first {len(degrees)} of {priority}",
            )

    def test_every_alias_reaches_the_same_templates(self):
        """A quality spelled another way gets the same shapes, through the same row.

        The table carries 13 alias keys (`min7`, `dom7`, `min7b5`, `mmaj7` and the rest)
        that the generator has no row for. They work because `stated_tones` canonicalises
        first, and this is what says so.
        """
        aliases = [
            name for name in VoiceLeadingEngine.DROP2_INTERVAL_SETS
            if name not in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT
        ]
        self.assertTrue(aliases, "the alias keys are the point of this test")
        for name in aliases:
            canonical = ChordParser.canonical_quality(name)
            self.assertEqual(
                VoiceLeadingEngine.DROP2_INTERVAL_SETS[name],
                DROP2_TEMPLATES.get(canonical),
                name,
            )

    def test_the_first_two_tone_priorities_are_the_shell_table(self):
        """A shell and a drop-2 state the same guide tones, and this is where they agree.

        `SHELL_DEGREES` is read by `_shell_request` and `_duo_offsets`; the priority row is
        read by the drop-2 generator. Two answers to one question would be free to drift,
        so the shell pair is asserted to be the row's head, in order.
        """
        self.assertEqual(len(SHELL_DEGREES), QUALITY_COUNT)
        for quality, pair in SHELL_DEGREES.items():
            self.assertEqual(
                TONE_PRIORITY[quality][:2], tuple(pair),
                f"{quality}: shell says {pair}, the priority row starts "
                f"{TONE_PRIORITY[quality][:2]}",
            )

    def test_a_priority_row_is_the_qualitys_own_tones(self):
        """No row invents a tone or loses one: it is a permutation of the chord's set."""
        for quality, row in TONE_PRIORITY.items():
            tones = ChordParser.CHORD_TONES_FROM_ROOT[quality]
            self.assertEqual(
                sorted(t % 12 for t in row), sorted({t % 12 for t in tones}), quality
            )


class TestTheOmissionDecision(unittest.TestCase):
    """Which tone a four-voice shape gives up, pinned per quality and by name."""

    #: (quality, the degree in the melody, the degrees that must NOT sound). Read off
    #: the hand tables, and the reason a single global order cannot replace the rows:
    #: `9` gives up its root and `7#11` gives up its natural 5th. Each is a forced case -
    #: the chord has more tones than the shape has voices.
    OMISSIONS = (
        ("9", 4, {0}),        # 3rd in the melody: the root goes, the 5th stays
        ("9", 0, {7}),        # root in the melody: the 5th goes instead
        ("maj9", 4, {0}),
        ("m9", 3, {0}),
        ("6/9", 4, {0}),
        ("7b9", 4, {0}),
        ("7b9", 0, {7}),
        ("13", 4, {0, 2}),    # the root and the 9th - a 13 does not promise its 9th
        ("7#11", 4, {7}),     # the #11 replaces the natural 5th
        ("7b13", 0, {7}),
        ("maj7#11", 0, {7}),
    )

    #: The altered 5th behaves as a guide tone does: `m9b5` keeps its b5 in every
    #: inversion but the one whose melody *is* the root, where the 9th takes the voice.
    ALTERED_FIFTH = (
        ("m9b5", 3, 6), ("m9b5", 6, 6), ("m9b5", 2, 6), ("m9b5", 0, -1),
    )

    def _sounding(self, quality, degree):
        """The degrees the generated shape for `degree` sounds, measured from the root."""
        templates = DROP2_TEMPLATES[quality]
        index = VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT[quality].index(degree)
        return {(degree + offset) % 12 for offset in templates[index]}

    def test_the_shape_gives_up_the_tone_the_row_says_it_does(self):
        """Each named quality drops the tone the hand table drops, in that inversion."""
        for quality, degree, omitted in self.OMISSIONS:
            with self.subTest(quality=quality, degree=degree):
                sounding = self._sounding(quality, degree)
                for tone in omitted:
                    self.assertNotIn(
                        tone, sounding,
                        f"{quality} with degree {degree} in the melody still sounds "
                        f"degree {tone}",
                    )

    def test_an_altered_fifth_is_kept_as_a_guide_tone(self):
        """A b5 sounds in every inversion except the one under a root melody."""
        for quality, degree, altered in self.ALTERED_FIFTH:
            with self.subTest(quality=quality, degree=degree):
                sounding = self._sounding(quality, degree)
                if altered < 0:
                    self.assertNotIn(6, sounding)
                else:
                    self.assertIn(altered, sounding)

    def test_a_four_tone_quality_gives_up_nothing(self):
        """With four voices and four tones the decision does not arise."""
        for quality, degrees in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.items():
            tones = {t % 12 for t in ChordParser.CHORD_TONES_FROM_ROOT[quality]}
            if len(tones) > 4:
                continue
            for degree in degrees:
                self.assertEqual(self._sounding(quality, degree), tones, quality)


class TestStatedTones(unittest.TestCase):
    """The accessor the rule hands out: it narrows, and it never widens."""

    def test_the_melody_is_always_stated(self):
        """The caller's note is not the rule's to rewrite, in any inversion."""
        for quality, row in TONE_PRIORITY.items():
            for degree in row:
                self.assertEqual(stated_tones(quality, degree, 4)[0], degree, quality)

    def test_a_shape_states_only_chord_tones_beyond_the_melody(self):
        """Nothing outside the chord can enter a shape, whatever it is asked for."""
        for quality in TONE_PRIORITY:
            tones = {t % 12 for t in ChordParser.CHORD_TONES_FROM_ROOT[quality]}
            for degree in range(12):
                for voices in range(2, 7):
                    for tone in stated_tones(quality, degree, voices)[1:]:
                        self.assertIn(tone % 12, tones, (quality, degree, voices))

    def test_asking_for_more_voices_than_the_chord_has_tones_stops_at_the_chord(self):
        """The whole row, and not a repeat of it: a shape never doubles a tone to pad."""
        for quality, row in TONE_PRIORITY.items():
            self.assertEqual(stated_tones(quality, row[0], 9), tuple(row), quality)

    def test_a_melody_outside_the_chord_keeps_its_own_tone_and_borrows_the_rest(self):
        """A non-chord melody is stated, and the row fills the voices below it."""
        stated = stated_tones("9", 5, 4)       # a 4th over a C9: not a chord tone
        self.assertEqual(stated[0], 5)
        self.assertEqual(stated[1:], (4, 10, 2))

    def test_an_unknown_quality_is_offered_nothing(self):
        """The house rule: never guess a chord. A quality with no row states no tones."""
        self.assertEqual(stated_tones("not-a-quality", 0), ())
        self.assertIsNone(DROP2_TEMPLATES.get("not-a-quality"))

    def test_a_quality_the_generator_cannot_build_is_given_no_templates(self):
        """A quality with no priority row generates nothing rather than a truncated shape."""
        from arranger.grips import _priority_drop2_templates

        self.assertEqual(_priority_drop2_templates("not-a-quality"), [])


class TestTheGeneratedShapesAreLegal(unittest.TestCase):
    """The invariants a generated template must satisfy on its own."""

    def test_a_generated_template_is_a_four_voice_drop2(self):
        """Four voices, soprano first, descending, and inside a hand's reach."""
        for quality, templates in DROP2_TEMPLATES.items():
            for template in templates:
                self.assertEqual(len(template), 4, quality)
                self.assertEqual(template[0], 0, quality)
                self.assertEqual(template, sorted(template, reverse=True), quality)
                self.assertTrue(
                    all(-19 <= offset < 0 for offset in template[1:]),
                    (quality, template),
                )

    def test_every_generated_template_sounds_both_guide_tones(self):
        """The property the hand tables were written to keep, held on the generation.

        A four-note voicing states the chord's 3rd and 7th; where the chord has no 3rd
        it is the 4th, and where it has neither, the note standing in for them. A
        generated shape that dropped either would be a different chord rather than a
        thinner one.
        """
        from arranger.grips import _guide_tones

        for quality, degrees in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.items():
            tones = ChordParser.CHORD_TONES_FROM_ROOT.get(quality)
            if not tones:
                continue
            guide = _guide_tones(tones, 0)
            if not guide:
                continue
            for degree, template in zip(degrees, DROP2_TEMPLATES[quality]):
                sounding = {(degree + offset) % 12 for offset in template}
                for want in guide:
                    self.assertIn(want % 12, sounding, (quality, degree))


if __name__ == "__main__":
    unittest.main()
