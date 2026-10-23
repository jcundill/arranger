"""The arrangement request: six questions resolved into the engine's axes.

`Request` is the public spelling, `head`'s flags are the other, and
`resolve_request` is the **derivation** that turns either into `parts`, `texture`,
`harmony` and the bass policy. What is verified:

- **the defaults are the shipped arrangement**: the guitar sings, the chord states
  the full harmonisation under each written melody note, and nothing else sounds;
- **the two rhythms decide the parts**, so `bass_on` is what makes the bass part
  exist rather than a `parts` spelling beside it;
- **content maps to the implementation**: `chord_notes` to the texture,
  `bass_notes` to the note rules, and `full` to the *derivation* rather than to a
  number;
- **every refusal happens before any voicing work**, naming what would work;
- **the canonical spelling round trips**, so the run header is a request a reader
  can copy back;
- **the library's own front door answers the same six questions**, asserted on the
  tab rather than on the axes, so a request built in Python is the request the
  flags build;
- **the two spellings are one vocabulary**, held together by `cli._REQUEST_DESTS`
  rather than by convention.

The step loop's behaviour is elsewhere; this is the request's own arithmetic and
its refusals.
"""

from __future__ import annotations

import argparse
import os
import unittest

from arranger import (
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
from arranger.cli import _REQUEST_DESTS, HEAD_HELP, add_common_arguments
from arranger.options import (
    _BASS_NOTES_ROOT_FIFTH,
    _CHORD_FILLS_HOLD,
    BASS_NOTES_WALK,
    CHORD_NOTES,
    ArrangeOptions,
)
from arranger.parts import PART_BASS, PART_CHORD, PART_MELODY, PART_NAMES
from arranger.resolution import resolve_axes
from arranger.texture import TEXTURE_STYLES
from tests.support import arranged, sweep_head_paths


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
            Request(bass_on="1", bass_notes=_BASS_NOTES_ROOT_FIFTH), 4
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
            Request(chord_on="none", chord_fills=_CHORD_FILLS_HOLD), 4
        )
        self.assertIn(PART_CHORD, resolved.parts)
        self.assertEqual(resolved.chord_fills, _CHORD_FILLS_HOLD)

    def test_a_rule_list_is_the_axis_s_own_spelling(self):
        """`root,approach` is the rules themselves: a subset the three names do not offer.

        The names are sugar over one vocabulary - `walk` is the four rules in their
        resolution order - so a caller who wants part of that chain asks for the rules.
        The order **is** the request: `approach,root` is a different line.
        """
        resolved = resolve_request(
            Request(bass_on="every-beat", bass_notes="root,approach"), 4
        )
        self.assertEqual(resolved.bass, f"{BASS_RULE_ROOT},{BASS_RULE_APPROACH}")
        self.assertEqual(resolved.bass_notes, "root,approach")
        self.assertEqual(
            resolve_request(
                Request(bass_on="every-beat", bass_notes="approach,root"), 4
            ).bass,
            f"{BASS_RULE_APPROACH},{BASS_RULE_ROOT}",
            "the order is the resolution order, not formatting",
        )

    def test_a_rule_list_is_reported_the_way_it_parses_back(self):
        """`ROOT, approach` is one request with one canonical header line."""
        resolved = resolve_request(
            Request(bass_on="every-beat", bass_notes=" ROOT , approach "), 4
        )
        self.assertEqual(resolved.bass_notes, "root,approach")
        self.assertIn("bass-notes=root,approach", format_request(resolved))

    def test_a_silent_bass_refuses_a_rule_list_too(self):
        """The content question is answered the same way whichever spelling asks it."""
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(bass_on="none", bass_notes="root,approach"), 4)
        self.assertIn("bass-notes=root,approach", str(caught.exception))

    def test_the_parts_are_canonicalised(self):
        """A derived selection is written in `PART_NAMES` order, as `parse_parts` is."""
        resolved = resolve_request(Request(bass_on="1", chord_on="none"), 4)
        self.assertEqual(
            resolved.parts,
            tuple(name for name in PART_NAMES if name in resolved.parts),
        )


class TestTheAxesMeetTheRequest(unittest.TestCase):
    """`resolve_axes` is where a caller's axis override and the request meet.

    The two are **coupled** there: a spelled bass policy takes the bass part with
    it, because a line with no part to play it is not a line. The selection it
    hands back is still a *set*, so a request that already named that part does not
    get it a second time.
    """

    def test_a_spelled_bass_policy_takes_the_bass_part(self):
        """The axis-only spelling: the request named no bass, the policy does."""
        axes = resolve_axes(Request(), None, BASS_RULE_ROOT, None)
        self.assertEqual(axes.parts, ",".join(PART_NAMES))

    def test_a_bass_policy_beside_a_named_bass_part_adds_nothing(self):
        """`bass_on=` already took the part, so the selection is rebuilt, not appended.

        A name written twice is two spellings of one part, and `parts` is a set:
        `melody,bass,chord,bass` is not a selection the engine can mean.
        """
        axes = resolve_axes(Request(bass_on="every-beat"), None, BASS_RULE_ROOT, None)
        self.assertEqual(axes.parts, ",".join(PART_NAMES))

    def test_a_narrower_selection_is_not_widened_by_the_policy(self):
        """The duplicate is loudest where the request's own selection is a subset.

        `chord_on=none` with a bass line is the tune and the thumb; spelling the
        policy as well must not add a second `bass` to that pair.
        """
        axes = resolve_axes(
            Request(chord_on="none", bass_on="every-beat"), None, BASS_RULE_ROOT, None
        )
        self.assertEqual(axes.parts, f"{PART_MELODY},{PART_BASS}")


class TestTheContentQuestions(unittest.TestCase):
    """What each layer states, mapped to the axis that states it."""

    def test_each_chord_arity_is_a_texture(self):
        for notes, texture in (("3", "chord3"), ("2", "chord2"), ("1", "chord1")):
            with self.subTest(notes=notes):
                self.assertEqual(
                    resolve_request(Request(chord_notes=notes), 4).texture, texture
                )

    def test_targets_is_the_arity_that_varies_by_position(self):
        """`targets` is a content answer, so it belongs on this question.

        It is the one spelling whose answer depends on *where* the chord falls - the
        same maximum as `full` on a strong beat and a thinner shape between them - and
        it is not a `chord_on` value: that says *when* a chord attacks, this says how
        much of it sounds there. Where the strong beats are is the metre's and the
        grouping's business rather than the caller's, which is why the request names
        the policy and not the positions.
        """
        self.assertEqual(
            resolve_request(Request(chord_notes="targets"), 4).texture, "targets"
        )

    def test_the_request_vocabulary_reaches_every_texture(self):
        """Every `TEXTURE_STYLES` entry has a request spelling, so none is API-only.

        A style the request cannot name is a style the command line cannot ask for, and
        nothing would report the gap: the flag would simply not offer it.
        """
        self.assertEqual(set(CHORD_NOTES.values()), set(TEXTURE_STYLES))

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

    def test_the_bass_refusal_names_both_spellings_of_the_vocabulary(self):
        """A name the request does not know is answered with the names *and* the rules.

        The two are one vocabulary - `walk` is `root,5th,approach,nearest` - so a
        caller who wrote something else is told both rather than being handed a list of
        the three names it already rejected.
        """
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(bass_on="every-beat", bass_notes="swing"), 4)
        message = str(caught.exception)
        self.assertIn("root-5th", message)
        self.assertIn("approach", message)

    def test_a_bad_position_names_the_metre(self):
        """`3` in a 2/2 bar is refused by the metre, not clamped or dropped."""
        with self.assertRaises(ValueError) as caught:
            resolve_request(Request(chord_on="3"), 2)
        self.assertIn("felt beat 3", str(caught.exception))



class TestTheRefusals(unittest.TestCase):
    """A request the engine cannot honour is answered before any voicing work."""

    def test_no_melody_keeps_the_tune_s_own_rhythm(self):
        """`--no-melody` reads the written onsets, as every other request does.

        **This assertion is inverted, not deleted** (AGENTS.md trap 5). The default
        used to be *derived* to `every-beat` on the grounds that "this guitar has no
        melody to attach it to"; the written onsets are a fact about the *score*, which
        is how `bass_on="melody"` has always read them, so the comp states the chord
        where the tune states a note. Every felt beat is the request that names it.
        """
        for spelling in ("melody", ""):
            request = Request(melody=False, **({"chord_on": spelling} if spelling else {}))
            resolved = resolve_request(request, 4)
            self.assertEqual(resolved.chord_on, "melody", spelling)
        self.assertEqual(
            resolve_request(Request(melody=False, chord_on="every-beat"), 4).chord_on,
            "1,2,3,4",
        )

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

    def test_the_capacity_check_reads_the_texture_and_not_the_spelling(self):
        """`targets` is a derivation too, so a thumb under it cannot over-ask.

        The check is `texture.texture_arity`'s answer rather than the request's own
        string, because a spelling that names a *number* is the only one that can
        over-ask. Written against the string it would have had to grow a branch per
        value, and `targets` would have reached it as an `int()` on a word.
        """
        resolved = resolve_request(
            Request(chord_notes="targets", bass_on="every-beat"), 4
        )
        self.assertEqual(resolved.texture, "targets")


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
            (Request(chord_notes="targets"), 4),
            (Request(chord_notes="targets", bass_on="every-beat"), 4),
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

    def test_chord_notes_targets_is_the_texture_the_request_names(self):
        """The request's `targets` and the axis's are one arrangement, not two.

        Asserted on the frets rather than on the axis, because the claim is that the
        *spelling* reaches the behaviour: a value that resolved to the right texture
        name and then arranged differently would pass an axis-level test. The second
        assertion is what keeps the first from being two spellings of the default
        agreeing with themselves.
        """
        by_request = _arrange(request=Request(chord_notes="targets"))
        by_axis = VoiceLeadingEngine.arrange_progression(
            _PROGRESSION, timings=_TIMINGS, options=ArrangeOptions(texture="targets")
        )
        self.assertEqual(
            [step.voicing.frets for step in by_request],
            [step.voicing.frets for step in by_axis],
        )
        self.assertNotEqual(
            [step.voicing.frets for step in _arrange(request=Request())],
            [step.voicing.frets for step in by_request],
            "targets arranged exactly as full, so this proves nothing",
        )

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


#: The requests the two doors must agree about - one per question the engine asks, so
#: a question whose derivation drifts is covered by its own row rather than by another
#: row's.
_REQUESTS = (
    Request(),
    Request(chord_notes="2"),
    Request(chord_notes="targets"),
    Request(chord_on="1and"),
    Request(chord_on="none"),
    Request(bass_on="every-beat"),
    Request(bass_on="every-beat", bass_notes="walk"),
    Request(bass_on="every-beat", bass_notes="root,approach"),
    Request(melody=False),
    Request(melody=False, chord_on="every-beat"),
    Request(melody=False, chord_on="none", bass_on="every-beat"),
    Request(melody=False, bass_on="every-beat", bass_notes="walk"),
    Request(chord_on="none", chord_fills="hold"),
)


def _axes_spelling(request: Request, beats_per_bar: int) -> ArrangeOptions:
    """The request's own derivation, spelled out as the three axes.

    Derived rather than written by hand, because that is what the claim is: the axes
    *are* what `resolve_request` derived, so a spelling that states each of them must
    arrange the same music. Spelling `parts` alone is deliberately **not** the same
    request - a spelled selection leaves the bass on its `auto` sentinel, which keeps no
    line - so every axis the request decided is stated here, `bass` included.
    """
    resolved = resolve_request(request, beats_per_bar)
    return ArrangeOptions(
        parts=",".join(resolved.parts),
        bass=resolved.bass,
        texture=resolved.texture,
        request=request,
    )


class TestTheAxisSpellingIsTheRequest(unittest.TestCase):
    """A request spelled as axes arranges **the same music** - one question, one answer.

    The request is the public vocabulary and the axes are the implementation, so a
    caller who spells them must get the arrangement the request gets. Asserted on the
    **tab**, over committed heads, because the disagreement this holds shut was not in
    the resolution at all: the importer's comping union was gated on whether an axis had
    been *spelled* rather than on what the selection meant, so a no-op axis spelling was
    a different arrangement (22 against 25 steps on `synthetic_common_8`, and a bar the
    tune never enters comped for one door only).

    The heads are `tests.support.sweep_head_paths()`, whose cases are the ones that
    differed: the melody-less bar, the note a comping position used to precede, and the
    note the tune is still holding.
    """

    def test_the_two_doors_are_one_arrangement(self):
        """Every request agrees with its own derivation, on every head, step for step."""
        for path in sweep_head_paths():
            for request in _REQUESTS:
                with self.subTest(head=os.path.basename(path), request=request):
                    by_request, head, _notes = arranged(
                        path, section=(1, 4), request=request
                    )
                    by_axes, _head, _notes = arranged(
                        path,
                        section=(1, 4),
                        options=_axes_spelling(request, head.beats_per_bar),
                    )
                    self.assertEqual(
                        [step.voicing.frets for step in by_request],
                        [step.voicing.frets for step in by_axes],
                    )


class TestTheTwoSpellingsAreOneVocabulary(unittest.TestCase):
    """`head`'s flags and `Request`'s fields are the same six questions.

    The request is spelled twice - once for a command line and once for a library
    caller - and the two are held together by `cli._REQUEST_DESTS` rather than by
    convention. A seventh question added to one spelling and not the other is a
    question one of the two front ends cannot ask, and nothing else would notice:
    the flag would parse and be ignored, or the field would be unreachable from a
    command line.
    """

    def test_the_list_names_every_field_exactly_once(self):
        """One entry per `Request` field, and no two questions sharing a flag."""
        fields = [field for field, _ in _REQUEST_DESTS]
        dests = [dest for _, dest in _REQUEST_DESTS]
        self.assertEqual(sorted(fields), sorted(Request.__dataclass_fields__))
        self.assertEqual(len(dests), len(set(dests)))

    def test_every_dest_is_a_flag_the_parser_registers(self):
        """A flag renamed without its entry moves the dest, and shows up here."""
        parser = argparse.ArgumentParser()
        add_common_arguments(parser, HEAD_HELP)
        namespace = parser.parse_args([])
        for field, dest in _REQUEST_DESTS:
            with self.subTest(field=field):
                self.assertIn(dest, vars(namespace))

    def test_every_chord_notes_value_is_one_the_parser_accepts(self):
        """The run header prints a spelling, so the parser has to take it back.

        `--chord-notes targets` is the line the header prints for a `targets` request,
        and a vocabulary entry the parser does not offer is a request a reader can copy
        out of the output and not paste back in.
        """
        parser = argparse.ArgumentParser()
        add_common_arguments(parser, HEAD_HELP)
        for value in CHORD_NOTES:
            with self.subTest(value=value):
                namespace = parser.parse_args(["--chord-notes", value])
                self.assertEqual(namespace.chord_notes, value)

    def test_a_bass_rule_list_is_one_the_parser_accepts(self):
        """`--bass-notes` is a vocabulary the *module* validates, so the list is one token.

        The three names and the rules are one question, and the flag takes either - the
        refusal for a value that is neither comes from `options`, which is what lets it
        name both spellings.
        """
        parser = argparse.ArgumentParser()
        add_common_arguments(parser, HEAD_HELP)
        for value in ("walk", "nearest", "root,approach", "root,5th,approach,nearest"):
            with self.subTest(value=value):
                namespace = parser.parse_args(["--bass-notes", value])
                self.assertEqual(namespace.bass_notes, value)


if __name__ == "__main__":
    unittest.main()
