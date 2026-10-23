"""The bass part's own slots: positions at which nothing above the thumb sounds.

A bass line runs on a finer grid than the tune, and a request may also switch the
chord part off at a position - so a position exists that is the thumb and nothing
else. Those slots were **rests** once: the melody-alone decision answered "the guitar
rests here" and the walked note was silently dropped. This file pins the route that
replaced it, and the one thing that must not change - a slot the guitar *sings* is
still the tune, with the thumb under it.

The notes themselves are `test_bass.py`'s; where they fall is `test_bass_positions.py`.
"""

import unittest

from arranger import Request
from arranger.annotation import step_annotation
from arranger.options import ArrangeOptions
from arranger.render import format_progression
from tests.support import (
    COMMON_8,
    FIVE_FOUR,
    I_WAS_DOING_ALL_RIGHT,
    TWELVE_EIGHT,
    WALTZ,
    arranged,
)


def _lone_bass(steps):
    """The steps that sound nothing above the thumb."""
    return [
        step
        for step in steps
        if step.bass is not None and not step.voicing.upper_midi_notes()
    ]


class TestTheLoneBassStep(unittest.TestCase):
    """`--chord-on none --bass-on every-beat` is a bass line, not a row of rests."""

    def test_every_requested_position_sounds(self):
        """Four steps in a 4/4 bar, each carrying a thumb note and nothing else."""
        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            request=Request(
                melody=False, chord_on="none", bass_on="every-beat"
            ),
        )
        rings = _lone_bass(steps)
        self.assertEqual([step.beat for step in rings], [1.0, 2.0, 3.0, 4.0])
        self.assertTrue(all(step.bass is not None for step in rings))

    def test_a_waltz_bar_has_three(self):
        steps, _head, _notes = arranged(
            WALTZ,
            section=(2, 3),
            request=Request(
                melody=False, chord_on="none", bass_on="every-beat"
            ),
        )
        self.assertEqual(len(_lone_bass(steps)), 3)

    def test_the_line_names_what_it_is(self):
        """The notes are the only thing in the column, so the line is the whole story.

        Five mutes and a fret look the same whether the chord ran out or was never
        asked for, which is why the annotation says which.
        """
        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            request=Request(
                melody=False, chord_on="none", bass_on="every-beat"
            ),
        )
        for step in _lone_bass(steps):
            self.assertIn("the thumb alone", step_annotation(step))
            self.assertFalse(step.bass_only)

    def test_a_shape_still_ringing_is_held(self):
        """When the chord part stops mid-bar, its last chord is still down.

        The measure is `--chord-on 1`: beat 1 states the chord, and beats 2-4 are the
        bass alone under a shape the hand has not left - so those steps are
        `bass_only`, and the line says so rather than claiming to sound a chord they
        do not.
        """
        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            request=Request(
                melody=False, chord_on="1", bass_on="every-beat"
            ),
        )
        rings = _lone_bass(steps)
        self.assertEqual([step.beat for step in rings], [2.0, 3.0, 4.0])
        for step in rings:
            self.assertTrue(step.bass_only)
            self.assertIn("the shape above is held", step_annotation(step))

    def test_the_thumb_is_never_refused(self):
        """A lone thumb has no upper shape to fight with, so nothing can refuse it.

        The refusal cases are all about a note sounding *under* a shape - no free
        string, no octave below it, a fifth fret - and none of them can apply here.
        """
        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 5),
            request=Request(
                melody=False, chord_on="none", bass_on="every-beat"
            ),
        )
        self.assertEqual([step.bass_refused for step in steps if step.bass_refused], [])


class TestTheSingingRouteIsUntouched(unittest.TestCase):
    """A slot the guitar sings is the tune, and the thumb rides along as it always did."""

    def test_an_off_chord_melody_slot_is_the_tune_plus_the_thumb(self):
        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            request=Request(chord_on="1", bass_on="every-beat"),
        )
        sung = [step for step in steps if step.melody_voiced]
        self.assertTrue(sung, [step.tab_line() for step in steps])
        for step in sung:
            self.assertTrue(step.voicing.upper_midi_notes())
        self.assertEqual(_lone_bass(steps), [])

    def test_a_melody_only_selection_sounds_its_bass_positions(self):
        """The tune and the thumb at a walk position: `bass_on="1and"`.

        Its note-less slots were *tune silent* before: the selection's early answer
        fired before the bass part's claim on the position was asked. A melody-only
        selection names no chord position, so the thumb is the only layer that attacks.
        """
        steps, _head, _notes = arranged(
            COMMON_8,
            section=(1, 2),
            options=ArrangeOptions(
                request=Request(chord_on="none", bass_on="1and", bass_notes="walk")
            ),
        )
        sounding = [
            step for step in steps if step.bass is not None and not step.bass_held
        ]
        self.assertEqual([step.beat for step in sounding], [1.5])


if __name__ == "__main__":
    unittest.main()


class TestAMelodylessRequest(unittest.TestCase):
    """`melody=off` is a complete request, and the chord's rhythm is the tune's.

    The chord's default is "the written onsets", and those are a fact about the
    **score** rather than about who plays it: a request that hands the tune to somebody
    else still comps the tune's own rhythm, which is how `bass_on="melody"` has always
    read them. Every felt beat is the metre's reading, and it is the one a caller asks
    for by naming it - `chord_on="every-beat"` - rather than the answer the engine
    substitutes for a request it thinks is incomplete.
    """

    def test_the_resolved_request_keeps_the_tune_s_rhythm(self):
        from arranger.options import resolve_request

        resolved = resolve_request(Request(melody=False), 4, (1, 1, 1, 1))
        self.assertEqual(resolved.chord_on, "melody")

    def test_the_metre_s_pulses_are_a_request_of_their_own(self):
        """`1,2,3` here are **felt** beats: in 12/8 they land on the 1st, 5th and 9th."""
        from arranger.options import resolve_request

        resolved = resolve_request(
            Request(melody=False, chord_on="every-beat"), 12, (4, 4, 4)
        )
        self.assertEqual(resolved.chord_on, "1,2,3")

    def test_a_sparser_request_still_wins(self):
        from arranger.options import resolve_request

        resolved = resolve_request(
            Request(melody=False, chord_on="1"), 4, (1, 1, 1, 1)
        )
        self.assertEqual(resolved.chord_on, "1")

    def test_the_guitar_states_a_chord_on_each_of_them(self):
        steps, _head, _notes = arranged(
            COMMON_8, section=(1, 2), request=Request(melody=False)
        )
        self.assertEqual([step.beat for step in steps], [1.0, 2.0, 3.0, 4.0])
        for step in steps:
            self.assertTrue(step.voicing.upper_midi_notes())
            self.assertFalse(step.melody_voiced)

    def test_fills_are_still_refused(self):
        """A fill policy needs melody rests to fill, and this request has none."""
        from arranger.options import resolve_request

        with self.assertRaises(ValueError):
            resolve_request(
                Request(melody=False, chord_fills="hold"), 4, (1, 1, 1, 1)
            )


class TestALoneBassLineAcrossTheMetres(unittest.TestCase):
    """`chord-on=none` with a bass line is the thumb and nothing else, in every metre."""

    #: head, and how many thumb attacks one full bar of it carries. `every-beat` is one
    #: per **felt** beat, so 5/4's `3+2` is two and 12/8's `4+4+4` is three.
    BARS = (
        (COMMON_8, (2, 3), 4),
        (I_WAS_DOING_ALL_RIGHT, (2, 3), 2),
        (WALTZ, (2, 3), 3),
        (FIVE_FOUR, (2, 3), 2),
        (TWELVE_EIGHT, (2, 3), 3),
    )

    def _bar(self, path, section):
        steps, head, _notes = arranged(
            path,
            section=section,
            request=Request(melody=False, chord_on="none", bass_on="every-beat"),
        )
        return steps, head

    def test_the_bar_carries_its_felt_beats(self):
        for path, section, expected in self.BARS:
            with self.subTest(head=path.split("/")[-1]):
                steps, _head = self._bar(path, section)
                attacks = [
                    step for step in steps if step.bass is not None and not step.bass_held
                ]
                self.assertEqual(len(attacks), expected)

    def test_no_thumb_note_is_refused(self):
        """A lone thumb has no upper shape to fight with, so nothing can refuse it."""
        for path, section, _expected in self.BARS:
            with self.subTest(head=path.split("/")[-1]):
                steps, _head = self._bar(path, section)
                self.assertEqual(
                    [step.bass_refused for step in steps if step.bass_refused], []
                )

    def test_every_renderer_carries_every_note(self):
        """The one-line tab, the staff and the score agree about a bar of lone thumbs."""
        from tabstaff import format_tab_staff
        from tabxml import format_musicxml

        steps, head = self._bar(COMMON_8, (2, 3))
        line = format_progression(steps)
        self.assertEqual(line.count("bass:"), 4)
        staff = format_tab_staff(steps, show_chords=False, show_melody=False)
        # One note per position and nothing else, so the six rows hold four digits
        # between them - whichever string the thumb found that bar.
        rows = [row for row in staff.splitlines() if row[:1] in "eBGDAE"]
        self.assertEqual(len(rows), 6, staff)
        self.assertEqual(sum(ch.isdigit() for row in rows for ch in row), 4, staff)
        document = format_musicxml(steps, beats_per_bar=4, beat_type=4)
        self.assertEqual(document.count("<note>"), 4, document)
        self.assertNotIn("<rest", document)
