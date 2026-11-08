"""Techniques on voicings: the `Technique` model, `Voicing.technique`, the
`technique=` grip parameter, and the `_technique_clause` annotation.

Techniques describe *how* a fret is played, so they ride on `Voicing.technique`
rather than on `ArrangementStep`, and they are metadata: `voicing_cost` never
reads them, so they never influence selection. A neutral technique (`None`) is
the default, so every arrangement built before this existed is byte-identical.
"""

import unittest

from musthe import Note

from arranger import ArrangementStep, Voicing
from arranger.annotation import _technique_clause, step_annotation
from arranger.grips import get_drop2_voicings, get_grip_voicings
from arranger.tuning import (
    HARMONIC_NATURAL,
    LINK_PULL,
    SLIDE_IN_BELOW,
    SLIDE_LEGATO,
    STROKE_DOWN,
    Technique,
)
from headxml_model import HeadNote


class TestTechniqueDefaults(unittest.TestCase):
    """Every field is neutral by default."""

    def test_all_fields_neutral(self):
        t = Technique()
        self.assertEqual(t.bend_semitones, 0)
        self.assertFalse(t.bend_release)
        self.assertFalse(t.bend_pre)
        self.assertIsNone(t.link)
        self.assertIsNone(t.slide)
        self.assertIsNone(t.slide_in)
        self.assertIsNone(t.slide_out)
        self.assertIsNone(t.harmonic)
        self.assertFalse(t.tapped)
        self.assertFalse(t.vibrato)
        self.assertFalse(t.palm_mute)
        self.assertFalse(t.let_ring)
        self.assertFalse(t.grace)
        self.assertIsNone(t.grace_fret)
        self.assertFalse(t.grace_hammer)
        self.assertFalse(t.staccato)
        self.assertIsNone(t.stroke)
        self.assertIsNone(t.velocity)

    def test_fields_set(self):
        t = Technique(
            bend_semitones=2,
            bend_release=True,
            link=LINK_PULL,
            slide=SLIDE_LEGATO,
            slide_in=SLIDE_IN_BELOW,
            harmonic=HARMONIC_NATURAL,
            vibrato=True,
            palm_mute=True,
            let_ring=True,
            staccato=True,
            stroke=STROKE_DOWN,
            velocity=110,
        )
        self.assertEqual(t.bend_semitones, 2)
        self.assertTrue(t.bend_release)
        self.assertEqual(t.link, LINK_PULL)
        self.assertEqual(t.slide, SLIDE_LEGATO)
        self.assertEqual(t.slide_in, SLIDE_IN_BELOW)
        self.assertEqual(t.harmonic, HARMONIC_NATURAL)
        self.assertTrue(t.vibrato)
        self.assertTrue(t.palm_mute)
        self.assertTrue(t.let_ring)
        self.assertTrue(t.staccato)
        self.assertEqual(t.stroke, STROKE_DOWN)
        self.assertEqual(t.velocity, 110)


class TestVoicingTechnique(unittest.TestCase):
    """The technique lands on the voicing, last field, defaulting to None."""

    def test_technique_defaults_none(self):
        v = Voicing(frets=[0, 2, 2, 1], top_fret=1, avg_fret=1.25)
        self.assertIsNone(v.technique)

    def test_technique_round_trip(self):
        t = Technique(bend_semitones=2, vibrato=True)
        v = Voicing(frets=[0, 2, 2, 1], top_fret=1, avg_fret=1.25, technique=t)
        self.assertIs(v.technique, t)

    def test_technique_is_last_field(self):
        t = Technique(vibrato=True)
        v = Voicing(
            frets=[0, 2, 2, 1],
            top_fret=1,
            avg_fret=1.25,
            grip="drop2",
            technique=t,
        )
        self.assertIs(v.technique, t)
        self.assertEqual(v.grip, "drop2")


class TestGripTechnique(unittest.TestCase):
    """`technique=` is attached to every candidate a grip builder produces."""

    def test_drop2_attaches_technique(self):
        t = Technique(bend_semitones=2, vibrato=True)
        vs = get_drop2_voicings(Note("C5"), chord_name="Cmaj7", technique=t)
        self.assertTrue(vs, "no drop-2 candidates under C5/Cmaj7 to check")
        for v in vs:
            self.assertIs(v.technique, t, v.tab_string())

    def test_get_grip_voicings_attaches_technique(self):
        t = Technique(harmonic="natural")
        vs = get_grip_voicings(Note("E5"), chord_name="Cmaj7", top_string=5, technique=t)
        self.assertTrue(vs)
        for v in vs:
            self.assertIs(v.technique, t)

    def test_no_technique_leaves_none(self):
        vs = get_drop2_voicings(Note("C5"), chord_name="Cmaj7")
        self.assertTrue(vs)
        for v in vs:
            self.assertIsNone(v.technique)


class TestTechniqueClause(unittest.TestCase):
    """`_technique_clause` phrasing, tested directly and through `step_annotation`."""

    def step(self, technique):
        return ArrangementStep(
            chord="Cmaj7",
            melody="C5",
            voicing=Voicing(
                frets=[0, 2, 2, 1], top_fret=1, avg_fret=1.25, technique=technique
            ),
        )

    def test_bend_clause(self):
        self.assertEqual(
            _technique_clause(self.step(Technique(bend_semitones=2))),
            "technique: bend 2 semitones",
        )

    def test_pre_bend_release_clause(self):
        self.assertEqual(
            _technique_clause(
                self.step(Technique(bend_semitones=1, bend_pre=True, bend_release=True))
            ),
            "technique: pre-bend release 1 semitone",
        )

    def test_harmonic_clause(self):
        self.assertEqual(
            _technique_clause(self.step(Technique(harmonic="pinch"))),
            "technique: pinch harmonic",
        )

    def test_hammer_and_slide_clause(self):
        self.assertEqual(
            _technique_clause(
                self.step(
                    Technique(link="hammer", slide="legato", slide_in="below")
                )
            ),
            "technique: hammer on & legato slide into from below",
        )

    def test_multiple_techniques(self):
        self.assertEqual(
            _technique_clause(
                self.step(
                    Technique(palm_mute=True, let_ring=True, staccato=True, stroke="up")
                )
            ),
            "technique: palm mute, let ring, staccato & up stroke",
        )

    def test_no_technique_silent(self):
        self.assertEqual(_technique_clause(self.step(None)), "")

    def test_technique_appears_in_step_annotation(self):
        step = self.step(Technique(bend_semitones=2))
        self.assertIn("bend 2 semitones", step_annotation(step))


class TestHeadNoteTechnique(unittest.TestCase):
    """A head-built note carries no technique by default."""

    def test_default_none(self):
        self.assertIsNone(HeadNote(bar=1, beat=1.0, pitch=60, duration=1.0).technique)


if __name__ == "__main__":
    unittest.main()
