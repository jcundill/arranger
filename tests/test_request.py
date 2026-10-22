"""The arrangement request: six questions resolved into the engine's axes.

`Request` is the public spelling, `head`'s flags are the other, and
`resolve_request` is the **derivation** that turns either into `parts`, `texture`,
`harmony` and the bass policy. What is verified:

- **the defaults are the shipped arrangement**: the guitar sings, the chord states
  the full harmonisation under each written melody note, and nothing else sounds;
- **the two rhythms decide the parts**, so `bass_on` is what makes the bass part
  exist rather than a `parts=` spelling beside it;
- **content maps to the implementation**: `chord_notes` to the texture,
  `bass_notes` to the note rules, and `full` to the *derivation* rather than to a
  number;
- **every refusal happens before any voicing work**, naming what would work;
- **the canonical spelling round trips**, so the run header is a request a reader
  can copy back;
- **the library's own front door answers the same six questions**, asserted on the
  tab rather than on the axes, so a request built in Python is the request the
  flags build;
- **the two spellings are one vocabulary**, held together by `cli.REQUEST_DESTS`
  rather than by convention.

The step loop's behaviour is elsewhere; this is the request's own arithmetic and
its refusals.
"""

from __future__ import annotations

import argparse
import unittest

from arranger import (
    BASS_NOTES_ROOT_FIFTH,
    BASS_NOTES_WALK,
    CHORD_FILLS_HOLD,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    Note,
    Request,
    VoiceLeadingEngine,
    format_request,
    parse_rhythm,
    resolve_request,
)
from arranger.bass_rules import (
    BASS_RULE_APPROACH,
    BASS_RULE_ROOT,
    BASS_STYLE_NONE,
)
from arranger.cli import HEAD_HELP, REQUEST_DESTS, add_common_arguments
from arranger.harmony import HARMONY_AUTO
from arranger.options import ArrangeOptions


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

    def test_no_melody_reads_the_melody_s_rhythm_as_every_beat(self):
        """The default cannot attach to a tune this guitar does not play.

        It is a **derivation** rather than a refusal: `--no-melody` on its own is a
        complete request, and the header prints the positions it resolved to. The
        refusal this replaces told the caller to name positions such as `every-beat`,
        which is the answer the metre has anyway.
        """
        for spelling in ("melody", ""):
            request = Request(melody=False, **({"chord_on": spelling} if spelling else {}))
            resolved = resolve_request(request, 4)
            self.assertEqual(resolved.chord_on, "1,2,3,4", spelling)

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
            (Request(chord_on="1and"), 4),
            (Request(chord_on="melody,1and", bass_on="every-beat", bass_notes="walk"), 4),
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
        for text in ("melody", "none", "1and", "lastand", "every-beat"):
            with self.subTest(text=text):
                resolved = resolve_request(Request(chord_on=text), 4)
                self.assertEqual(str(parse_rhythm(text, 4)), resolved.chord_on)


#: A four-slot progression, one quality per melody note, so a question about the
#: chord part has something to change and a walk has a next chord to move toward.
#: The timings are `(bar, beat, duration)`: bar 1, one felt beat per slot.
_PROGRESSION = (
    ("C5", "maj7", "Cmaj7"),
    ("B4", "m7", "Cm7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
)
_TIMINGS = ((1, 1.0, 1.0), (1, 2.0, 1.0), (1, 3.0, 1.0), (1, 4.0, 1.0))

#: One chord held across the whole bar, which is what gives a walk somewhere to go:
#: with a chord per beat there is one attack per chord, so a line can only reach
#: toward the next chord rather than move inside this one.
_HELD = (
    ("C5", "maj7", "Cmaj7"),
    ("B4", "maj7", "Cmaj7"),
    ("A4", "maj7", "Cmaj7"),
    ("G4", "maj7", "Cmaj7"),
)


def _arrange(progression=_PROGRESSION, timings=_TIMINGS, **kwargs):
    """The library's own front door, with the request passed as one value."""
    return VoiceLeadingEngine.arrange_progression(
        progression, timings=timings, options=ArrangeOptions(**kwargs)
    )


def _sounded(step) -> int:
    """How many strings a step plucks; the tune alone is one."""
    return sum(1 for fret in step.voicing.frets if fret >= 0)


def _thumb_pitches(steps):
    """The thumb notes of an arrangement, in order."""
    return [step.bass for step in steps]


def _tune_midi(index: int) -> int:
    """The written pitch of the slot at `index`, read off the progression."""
    return Note(_PROGRESSION[index][0]).midi_note()


class TestTheLibrarySpelling(unittest.TestCase):
    """The six questions asked of `arrange_progression`, not of a score.

    Every other `request=` in the suite goes through `arrange_xml_head`, so the
    library's own front door had no witness of its own. Each of the six is asserted
    on the tab it produces rather than on the axis it resolves to: the resolution is
    `resolve_request`'s business, and it is verified above.
    """

    def test_no_melody_leaves_the_tune_to_somebody_else(self):
        """The tune's pitch is never the top voice, so this guitar is not singing it.

        The strongest form of the claim, because the soprano *is* the melody on every
        arrangement that has one: a step whose highest note is not the written pitch
        is one where the guitar stopped playing the tune.
        """
        steps = _arrange(request=Request(melody=False, chord_on="every-beat"))
        self.assertEqual([step.beat for step in steps], [1.0, 2.0, 3.0, 4.0])
        for index, step in enumerate(steps):
            with self.subTest(beat=step.beat):
                self.assertNotEqual(
                    max(step.voicing.midi_notes()), _tune_midi(index)
                )

    def test_chord_on_names_when_the_chord_attacks(self):
        """`1,3` is a chord under the tune at 1 and 3, and the tune alone at 2 and 4.

        Asserted on the plucked strings, which is the difference between "the chord
        part is silent here" and "the chord part states nothing here". The slots come
        back in the timings' order, so the position in the list is the beat.
        """
        steps = _arrange(request=Request(chord_on="1,3"))
        sounded = [_sounded(step) for step in steps]
        self.assertEqual(len(sounded), 4)
        self.assertGreater(sounded[0], 1)
        self.assertEqual(sounded[1], 1)
        self.assertGreater(sounded[2], 1)
        self.assertEqual(sounded[3], 1)

    def test_chord_notes_is_a_ceiling_on_what_the_chord_states(self):
        """`2` states the guide pair where the derivation states three strings."""
        derived = _arrange(request=Request(melody=False, chord_on="every-beat"))
        pair = _arrange(
            request=Request(melody=False, chord_on="every-beat", chord_notes="2")
        )
        self.assertTrue(all(_sounded(step) > 2 for step in derived))
        self.assertTrue(all(_sounded(step) == 2 for step in pair))

    def test_chord_fills_states_the_chord_in_a_rest_the_tune_left(self):
        """A slot with no melody note is silent by default, and sounds with `hold`."""
        rests = (("C5", "maj7", "Cmaj7"), (None, "m7", "Cm7"))
        timings = ((1, 1.0, 1.0), (1, 2.0, 1.0))
        silent = _arrange(rests, timings, request=Request(chord_on="none"))
        filled = _arrange(
            rests, timings, request=Request(chord_on="none", chord_fills="hold")
        )
        self.assertEqual(_sounded(silent[-1]), 0)
        self.assertGreater(_sounded(filled[-1]), 1)

    def test_bass_on_places_the_thumb(self):
        """Nothing sounds under the tune by default; `every-beat` is a thumb per beat."""
        self.assertTrue(all(step.bass is None for step in _arrange()))
        steps = _arrange(request=Request(bass_on="every-beat"))
        self.assertEqual(len(steps), 4)
        self.assertTrue(all(step.bass is not None for step in steps))

    def test_bass_notes_changes_what_each_thumb_note_states(self):
        """`root` is a pedal on one pitch; `walk` is a line through the bar.

        Asked of a chord held across the bar, because that is the unit the line is
        written for: with a chord per beat there is one attack per chord, and the
        only movement a walk can make is toward the next chord.
        """
        pedal = _thumb_pitches(
            _arrange(_HELD, request=Request(bass_on="every-beat"))
        )
        walk = _thumb_pitches(
            _arrange(_HELD, request=Request(bass_on="every-beat", bass_notes="walk"))
        )
        self.assertEqual(len(pedal), 4)
        self.assertEqual(len(set(pedal)), 1)
        self.assertGreater(len(set(walk)), 1)


    def test_the_request_and_an_axis_override_compose(self):
        """The two doors are not alternatives: an axis rides beside the request.

        `request=` is *what to play* and `options=ArrangeOptions(...)` carries the
        implementation axes that answer *how*, so one call may name both. The axis
        wins where it speaks - that is what "the implementation" means - and every
        other answer still comes from the request.
        """
        composed = VoiceLeadingEngine.arrange_progression(
            _PROGRESSION,
            timings=_TIMINGS,
            request=Request(melody=False, chord_on="every-beat"),
            options=ArrangeOptions(texture="targets"),
        )
        self.assertEqual([step.beat for step in composed], [1.0, 2.0, 3.0, 4.0])
        # `melody=False` is the request's answer, and it survived the axis beside it.
        self.assertTrue(all(not step.melody_voiced for step in composed))
        self.assertEqual(
            [step.role for step in composed], ["target", "fill", "target", "fill"]
        )


class TestTheTwoSpellingsAreOneVocabulary(unittest.TestCase):
    """`head`'s flags and `Request`'s fields are the same six questions.

    The request is spelled twice - once for a command line and once for a library
    caller - and the two are held together by `cli.REQUEST_DESTS` rather than by
    convention. A seventh question added to one spelling and not the other is a
    question one of the two front ends cannot ask, and nothing else would notice:
    the flag would parse and be ignored, or the field would be unreachable from a
    command line.
    """

    def test_the_list_names_every_field_exactly_once(self):
        """One entry per `Request` field, and no two questions sharing a flag."""
        fields = [field for field, _ in REQUEST_DESTS]
        dests = [dest for _, dest in REQUEST_DESTS]
        self.assertEqual(sorted(fields), sorted(Request.__dataclass_fields__))
        self.assertEqual(len(dests), len(set(dests)))

    def test_every_dest_is_a_flag_the_parser_registers(self):
        """A flag renamed without its entry moves the dest, and shows up here."""
        parser = argparse.ArgumentParser()
        add_common_arguments(parser, HEAD_HELP)
        namespace = parser.parse_args([])
        for field, dest in REQUEST_DESTS:
            with self.subTest(field=field):
                self.assertIn(dest, vars(namespace))


if __name__ == "__main__":
    unittest.main()
