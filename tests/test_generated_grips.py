"""The drop-2 shapes are the tone-priority rule's output, held to the hand table it
replaced.

`TONE_PRIORITY` says which of a chord's tones a shape states, in what order, one row per
quality; `grips.drop2_template_for` turns one degree into the shape for it, and
`_drop2_palette` is that rule read at every degree the chord has. The 119 hand-written
templates live in `tests/support.py` now - the engine stopped carrying them - re-keyed by
the degree their top voice states (`WITNESS`), and the assertion below compares the rule
with those numbers rather than trusting either.

The rule is not a refactor of the table, and these tests are shaped to say so. The table
is 119 numbers that encode a musical decision - which tone a four-voice shape gives up
when the chord has five tones - and the decision is a *different* one per quality, which
is why the priority row is the rule and there is no single global order that reproduces
them. `TestTheOmissionDecision` pins that per quality and by name, so a row edited into a
tidier shared pattern fails here and says which quality moved.

This file is where the rule and those numbers meet. If it is ever deleted, the rule
becomes unverified and the hand table becomes decorative.
"""

from __future__ import annotations

import unittest

from musthe import Note

from arranger import SHELL_DEGREES, ChordParser, VoiceLeadingEngine
from arranger.grip_tables import (
    TONE_PRIORITY,
    stated_tones,
)
from arranger.grips import (
    _drop2_palette,
    drop2_template_for,
)
from tests.support import WITNESS

#: The acceptance gate's denominator. `docs/engine.md` had said "109 hand-authored
#: templates" while the table held 119, which is why the count is asserted rather than
#: described in prose: a table that shrank, or a quality whose row stopped generating,
#: cannot pass quietly.
QUALITY_COUNT = 29
TEMPLATE_COUNT = 119

#: Every degree the palette is read at: all the chord tones of all 29 qualities, in the
#: rule's own order. Six more than the hand table named - the 9th of a `13`, the #9 and
#: #11 of a `7alt`, and the natural 5th of `7#11`, `7b13` and `maj7#11` - which is what
#: making the palette "the rule at every degree" adds.
PALETTE_COUNT = 125


class TestTheRuleReproducesTheTables(unittest.TestCase):
    """The generated templates are the hand-written ones, for every quality."""

    def test_every_witnessed_quality_has_a_priority_row(self):
        """A quality the witness names is one the rule can voice: it needs a row."""
        for quality in WITNESS:
            canonical = ChordParser.canonical_quality(quality)
            self.assertIn(
                canonical, TONE_PRIORITY, f"{quality} canonicalises to {canonical}"
            )

    def test_the_rule_reproduces_the_hand_written_templates(self):
        """Every one of the 119 templates, to the semitone, by degree.

        This is the assertion the arrangement rests on: it is what lets the engine read
        the rule at all, with the hand numbers kept here as the witness rather than in
        the library.
        """
        checked = 0
        for quality, by_degree in WITNESS.items():
            for degree, want in by_degree.items():
                checked += 1
                got = drop2_template_for(quality, degree)
                self.assertEqual(
                    got, want,
                    f"{quality} with degree {degree} in the melody: "
                    f"the rule builds {got}, the table says {want}",
                )
        self.assertEqual(checked, TEMPLATE_COUNT)
        self.assertEqual(len(TONE_PRIORITY), QUALITY_COUNT)

    def test_a_witness_degree_list_is_a_prefix_of_the_rule(self):
        """The tones the hand table named are the rule's own, read from the top.

        Measured over all 29 qualities: every witness's degree list is the **prefix** of
        that quality's `TONE_PRIORITY` row, cut to the list's length - and not one of them
        is in the rule's order, which is why the rule cannot be asked for the list as a
        list and had to be asked for one degree at a time.

        That is worth asserting because `test_the_rule_reproduces_the_hand_written_templates`
        cannot see it: it compares shapes degree by degree, so any list of degrees agrees
        with itself. A witness naming a tone its quality does not have fails here and says
        which quality moved. The five lists *shorter* than their priority row are the
        qualities with more tones than the table covered (`13`, `7#11`, `7b13`, `maj7#11`,
        and `7alt` two tones over), which is what makes the rule's own degree list a
        property of the rule rather than a number someone typed.
        """
        for quality, by_degree in WITNESS.items():
            canonical = ChordParser.canonical_quality(quality)
            priority = TONE_PRIORITY[canonical]
            degrees = list(by_degree)
            self.assertEqual(
                set(degrees),
                set(priority[: len(degrees)]),
                f"{quality}: {degrees} is not the first {len(degrees)} of {priority}",
            )

    def test_every_alias_reaches_the_same_shapes(self):
        """A quality spelled another way gets the same shapes, through the same rule.

        The aliases (`min7`, `dom7`, `min7b5`, `mmaj7` and the rest) have no priority row
        of their own, so the rule itself answers nothing for them. They work because
        `chord_context` canonicalises the quality before the rule is asked, and this is
        what says so - on the route a caller takes, not on a table key.
        """
        aliases = [
            name for name in ChordParser.QUALITY_ALIASES if name not in TONE_PRIORITY
        ]
        self.assertTrue(aliases, "the alias keys are the point of this test")
        for name in aliases:
            with self.subTest(alias=name):
                canonical = ChordParser.canonical_quality(name)
                self.assertNotEqual(name, canonical)
                for melody in ("C5", "E4", "B4"):
                    self.assertEqual(
                        [
                            voicing.tab_string()
                            for voicing in VoiceLeadingEngine.get_drop2_voicings(
                                Note(melody), name
                            )
                        ],
                        [
                            voicing.tab_string()
                            for voicing in VoiceLeadingEngine.get_drop2_voicings(
                                Note(melody), canonical
                            )
                        ],
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
        """The degrees the rule's shape for `degree` sounds, measured from the root."""
        return {
            (degree + offset) % 12 for offset in drop2_template_for(quality, degree)
        }

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
        for quality, tones in ChordParser.CHORD_TONES_FROM_ROOT.items():
            tones = {t % 12 for t in tones}
            if len(tones) > 4:
                continue
            for degree in tones:
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
        self.assertEqual(drop2_template_for("not-a-quality", 0), [])

    def test_a_quality_the_rule_cannot_build_has_no_palette(self):
        """A quality with no priority row offers no shapes rather than truncated ones."""
        self.assertEqual(_drop2_palette("not-a-quality"), [])


class TestTheGeneratedShapesAreLegal(unittest.TestCase):
    """The invariants a generated template must satisfy on its own."""

    def test_a_generated_template_is_a_four_voice_drop2(self):
        """Four voices, soprano first, descending, and inside a hand's reach.

        Read over `drop2_template_for` at **every chord tone** of every quality, not just
        the degrees the hand table named: the rule is asked for one degree at a time, so
        the degrees it is legal at is whatever it answers for.
        """
        for quality, chord_tones in ChordParser.CHORD_TONES_FROM_ROOT.items():
            for degree in {t % 12 for t in chord_tones}:
                template = drop2_template_for(quality, degree)
                self.assertEqual(len(template), 4, (quality, degree))
                self.assertEqual(template[0], 0, (quality, degree))
                self.assertEqual(
                    template, sorted(template, reverse=True), (quality, degree)
                )
                self.assertTrue(
                    all(-19 <= offset < 0 for offset in template[1:]),
                    (quality, degree, template),
                )

    def test_every_generated_template_sounds_both_guide_tones(self):
        """The property the hand tables were written to keep, held on the rule.

        A four-note voicing states the chord's 3rd and 7th; where the chord has no 3rd
        it is the 4th, and where it has neither, the note standing in for them. A
        generated shape that dropped either would be a different chord rather than a
        thinner one.

        This is a **gate rather than a branch**: the rule used to be held to it at runtime,
        by a fallback that rebuilt a shape from the guide tones when the derived one lost
        them, and that fallback was measured never to fire over all 125 degrees - so the
        rule is now asserted to hold, and a quality added later that breaks it fails here.
        """
        from arranger.grips import _guide_tones

        for quality, chord_tones in ChordParser.CHORD_TONES_FROM_ROOT.items():
            guide = _guide_tones(chord_tones, 0)
            if not guide:
                continue
            for degree in {t % 12 for t in chord_tones}:
                sounding = {
                    (degree + offset) % 12
                    for offset in drop2_template_for(quality, degree)
                }
                for want in guide:
                    self.assertIn(want % 12, sounding, (quality, degree))


class TestThePalette(unittest.TestCase):
    """What a melody with no degree to match is offered: the rule at every chord tone."""

    def test_the_palette_is_the_rule_read_at_every_chord_tone(self):
        """One shape per chord tone, in the rule's order, and none of them empty."""
        total = 0
        for quality, row in TONE_PRIORITY.items():
            self.assertEqual(
                _drop2_palette(quality),
                [drop2_template_for(quality, d) for d in row],
                quality,
            )
            self.assertEqual(
                len(_drop2_palette(quality)),
                len({t % 12 for t in ChordParser.CHORD_TONES_FROM_ROOT[quality]}),
                quality,
            )
            total += len(_drop2_palette(quality))
        self.assertEqual(total, PALETTE_COUNT)

    def test_every_shape_in_the_palette_states_the_chord(self):
        """Every one of the 125 shapes is pure, which is what lets the cost choose.

        The selector's first criterion is tone purity, so a palette holding an impure shape
        is only safe while that criterion outranks the rest. Held here instead: for every
        quality and every degree, nothing in the shape sounds outside the chord.
        """
        for quality, row in TONE_PRIORITY.items():
            tones = {t % 12 for t in ChordParser.CHORD_TONES_FROM_ROOT[quality]}
            for degree, shape in zip(row, _drop2_palette(quality)):
                sounding = {(degree + offset) % 12 for offset in shape}
                self.assertTrue(
                    sounding <= tones,
                    f"{quality} on degree {degree}: {shape} sounds outside the chord",
                )


if __name__ == "__main__":
    unittest.main()
