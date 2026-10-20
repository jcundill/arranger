"""The arrangement request: four questions resolved into the engine's axes.

`Request` is the public spelling, and `resolve_request` is the **derivation** that
turns it into `parts`, `texture`, `harmony` and the bass policy. What is verified:

- **the defaults are the shipped arrangement**: the guitar sings, the chord states
  the full harmonisation under each written melody note, and nothing else sounds;
- **the two rhythms decide the parts**, so `bass_on` is what makes the bass part
  exist rather than a `parts=` spelling beside it;
- **content maps to the implementation**: `chord_notes` to the texture,
  `bass_notes` to the note rules, and `full` to the *derivation* rather than to a
  number;
- **every refusal happens before any voicing work**, naming what would work;
- **the canonical spelling round trips**, so the run header is a request a reader
  can copy back.

The step loop's behaviour is elsewhere; this is the request's own arithmetic and
its refusals.
"""

from __future__ import annotations

import unittest

from arranger import (
    BASS_NOTES_ROOT_FIFTH,
    BASS_NOTES_WALK,
    CHORD_FILLS_HOLD,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    Request,
    format_request,
    parse_rhythm,
    resolve_request,
)
from arranger.bass_rules import (
    BASS_RULE_APPROACH,
    BASS_RULE_ROOT,
    BASS_STYLE_NONE,
)
from arranger.harmony import HARMONY_AUTO


class TestTheShippedRequest(unittest.TestCase):
    """`Request()` is the arrangement this library has always built."""

    def test_the_parts_are_the_tune_and_the_chord(self):
        """The melody and the chord part, and **no** bass - nothing sounds there."""
        resolved = resolve_request(Request(), 4)
        self.assertEqual(resolved.parts, (PART_MELODY, PART_CHORD))
        self.assertEqual(resolved.bass, BASS_STYLE_NONE)

    def test_the_full_harmonisation_is_the_derivation(self):
        """`chord_notes=full` is `uniform`: the most the right hand can fit."""
        self.assertEqual(resolve_request(Request(), 4).texture, "uniform")

    def test_the_degree_order_is_the_engine_s_auto(self):
        """`harmony=` is not a public question; the shipped answer is its `auto`."""
        self.assertEqual(resolve_request(Request(), 4).harmony, HARMONY_AUTO)

    def test_the_chord_attacks_at_the_written_melody(self):
        """`chord_on=melody` is the written onsets, and no bass attacks at all."""
        resolved = resolve_request(Request(), 4)
        self.assertTrue(resolved.chord_rhythm.wants_melody)
        self.assertTrue(resolved.bass_rhythm.is_none)



class TestTheRhythmsDecideTheParts(unittest.TestCase):
    """A layer exists because its rhythm asks for it, not because parts says so."""

    def test_a_bass_rhythm_takes_the_bass_part(self):
        """`bass_on=every-beat` adds the part, and the shipped rules derive from it."""
        resolved = resolve_request(
            Request(bass_on="every-beat", bass_notes="walk"), 4
        )
        self.assertIn(PART_BASS, resolved.parts)
        self.assertEqual(resolved.bass_rhythm.positions, (1.0, 2.0, 3.0, 4.0))
        self.assertIn(BASS_RULE_APPROACH, resolved.bass)

    def test_root_and_fifth_is_a_two_rule_line(self):
        """`root-5th` is the two rules, not the whole walk."""
        resolved = resolve_request(
            Request(bass_on="1", bass_notes=BASS_NOTES_ROOT_FIFTH), 4
        )
        self.assertEqual(resolved.bass, f"{BASS_RULE_ROOT},5th")

    def test_the_walk_is_the_whole_vocabulary(self):
        """`walk` is every rule the thumb line is written on."""
        resolved = resolve_request(Request(bass_on="1", bass_notes=BASS_NOTES_WALK), 4)
        self.assertEqual(len(resolved.bass.split(",")), 4)

    def test_a_silent_chord_leaves_the_chord_part_out(self):
        """`chord_on=none` is the tune alone, not a chord part with no attacks."""
        resolved = resolve_request(Request(chord_on="none"), 4)
        self.assertEqual(resolved.parts, (PART_MELODY,))
        self.assertTrue(resolved.chord_rhythm.is_none)

    def test_a_rest_policy_keeps_the_chord_part_alive(self):
        """`chord-on none` with `chord-fills hold` comps in the rests, so it exists."""
        resolved = resolve_request(
            Request(chord_on="none", chord_fills=CHORD_FILLS_HOLD), 4
        )
        self.assertIn(PART_CHORD, resolved.parts)
        self.assertEqual(resolved.chord_fills, CHORD_FILLS_HOLD)

    def test_the_parts_are_canonicalised(self):
        """A derived selection is written in `PART_NAMES` order, as `parse_parts` is."""
        resolved = resolve_request(Request(bass_on="1", chord_on="none"), 4)
        self.assertEqual(
            resolved.parts,
            tuple(name for name in PART_NAMES if name in resolved.parts),
        )


class TestTheContentQuestions(unittest.TestCase):
    """What each layer states, mapped to the axis that states it."""

    def test_each_chord_arity_is_a_texture(self):
        for notes, texture in (("3", "chord3"), ("2", "chord2"), ("1", "chord1")):
            with self.subTest(notes=notes):
                self.assertEqual(
                    resolve_request(Request(chord_notes=notes), 4).texture, texture
                )

    def test_the_bass_names_are_note_rules(self):
        """The names say *what*, so `root` on a beat is a pedal rather than an anchor."""
        resolved = resolve_request(Request(bass_on="every-beat", bass_notes="root"), 4)
        self.assertEqual(resolved.bass, BASS_RULE_ROOT)

    def test_a_name_outside_a_vocabulary_is_refused_with_the_vocabulary(self):
        cases = (
            (Request(chord_notes="four"), "chord-notes"),
            (Request(bass_notes="swing"), "bass-notes"),
            (Request(chord_fills="sometimes"), "chord-fills"),
        )
        for request, label in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError) as caught:
                    resolve_request(request, 4)
                self.assertIn(label, str(caught.exception))

    def test_a_bad_position_names_the_metre(self):
        """`3` in a 2/2 bar is refused by the metre, not clamped or dropped."""
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(chord_on="3"), 2)
        self.assertIn("felt beat 3", str(caught.exception))



class TestTheRefusals(unittest.TestCase):
    """A request the engine cannot honour is answered before any voicing work."""

    def test_no_melody_cannot_ask_for_the_melody_s_rhythm(self):
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(melody=False, chord_on="melody"), 4)
        self.assertIn("melody=off", str(caught.exception))

    def test_no_melody_cannot_ask_for_rest_fills(self):
        with self.assertRaises(ValueError) as caught:
            resolve_request(
                Request(melody=False, chord_on="every-beat", chord_fills="hold"), 4
            )
        self.assertIn("melody rest", str(caught.exception))

    def test_a_chord_content_choice_needs_a_chord_part(self):
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(chord_on="none", chord_notes="2"), 4)
        self.assertIn("chord-notes=2", str(caught.exception))

    def test_a_bass_content_choice_needs_a_bass_part(self):
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(bass_on="none", bass_notes="walk"), 4)
        self.assertIn("bass-notes=walk", str(caught.exception))

    def test_an_empty_selection_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            resolve_request(
                Request(melody=False, chord_on="none", bass_on="none"), 4
            )
        self.assertIn("nothing to play", str(caught.exception))

    def test_five_strings_is_arithmetic_rather_than_a_silent_thinning(self):
        """Three chord notes, a melody and a bass is five right-hand strings."""
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(chord_notes="3", bass_on="every-beat"), 4)
        self.assertIn("right-hand strings", str(caught.exception))

    def test_full_plus_a_bass_is_allowed_because_it_means_the_most_that_fits(self):
        """`full` is a derivation, so it cannot ask for more than the hand has."""
        resolved = resolve_request(
            Request(chord_notes="full", bass_on="every-beat"), 4
        )
        self.assertEqual(resolved.texture, "uniform")


class TestTheCanonicalSpelling(unittest.TestCase):
    """The run header prints a request that parses back to the same value."""

    def test_the_default_spelling(self):
        self.assertEqual(
            format_request(resolve_request(Request(), 4)),
            "melody=on chord-on=melody chord-notes=full "
            "bass-on=none bass-notes=root chord-fills=none",
        )

    def test_every_beat_prints_as_the_positions_it_resolves_to(self):
        """`every-beat` is metre-dependent, so its canonical spelling is the positions."""
        self.assertIn(
            "bass-on=1,2,3,4",
            format_request(resolve_request(Request(bass_on="every-beat"), 4)),
        )

    def test_the_spelling_parses_back(self):
        """Split the line, rebuild the request, and the value is unchanged."""
        for request, beats in (
            (Request(), 4),
            (Request(chord_on="1&"), 4),
            (Request(chord_on="melody,1&", bass_on="every-beat", bass_notes="walk"), 4),
            (Request(melody=False, chord_on="every-beat"), 4),
            (Request(chord_on="none", chord_fills="hold"), 3),
            (Request(bass_on="every-beat", chord_on="none"), 2),
        ):
            with self.subTest(request=request, beats=beats):
                resolved = resolve_request(request, beats)
                fields = dict(
                    field.split("=", 1)
                    for field in format_request(resolved).split()
                )
                again = resolve_request(
                    Request(
                        melody=fields["melody"] == "on",
                        chord_on=fields["chord-on"],
                        chord_notes=fields["chord-notes"],
                        bass_on=fields["bass-on"],
                        bass_notes=fields["bass-notes"],
                        chord_fills=fields["chord-fills"],
                    ),
                    beats,
                )
                self.assertEqual(again, resolved)
                self.assertEqual(format_request(again), format_request(resolved))

    def test_the_rhythm_spellings_are_the_grammar_s(self):
        """The request does not re-spell the positions `parse_rhythm` owns."""
        for text in ("melody", "none", "1&", "last&", "every-beat"):
            with self.subTest(text=text):
                resolved = resolve_request(Request(chord_on=text), 4)
                self.assertEqual(str(parse_rhythm(text, 4)), resolved.chord_on)


if __name__ == "__main__":
    unittest.main()
