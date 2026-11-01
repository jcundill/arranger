"""`--chord-fills`: what the chord states in a **notated melody rest**.

The policy is not a rhythm - a rest has no melody note to attach a position to - so
it is tested on its own timeline: `melody_rests` finds the gaps and `fill_slots`
turns a gap into attacks. Most cases below are built by hand rather than read from a
score, because the interesting shapes (a rest longer than a beat, a rest that runs
into a chord change, a rest under `NC`) are ones the committed fixtures do not happen
to contain. The two end-to-end cases use a real head, because a `Head` built by hand
never reaches `arrange_xml_head`.
"""

import unittest
from typing import Any

import headxml
from arranger import Request
from arranger.options import _CHORD_FILLS_HOLD, CHORD_FILLS_COMP, CHORD_FILLS_NONE, resolve_request
from headxml import Head, HeadChange, HeadNote, melody_rests
from tests.support import arranged, quality_of

SLASH = "tests/data/synthetic_repeat_slash.musicxml"


def hand_head() -> Head:
    """Four 4/4 bars holding the three shapes of rest the policy has to tell apart.

    bar 1: a quarter note, then **two beats of silence** under one chord - the case
           `comp` and `hold` answer differently;
    bar 2: a note held for the whole bar - no rest, because a hold is not silence;
    bar 3: a half note, then one beat of silence;
    bar 4: no notes at all, under `NC` - a rest with nothing to state.
    """
    notes = [
        HeadNote(bar=1, beat=1.0, pitch=60, duration=0.25),
        HeadNote(bar=2, beat=1.0, pitch=64, duration=1.0),
        HeadNote(bar=3, beat=1.0, pitch=67, duration=0.5),
    ]
    chords = [
        HeadChange(bar=1, beat=1.0, chord="C", quality="maj"),
        HeadChange(bar=2, beat=1.0, chord="G7", quality="7"),
        HeadChange(bar=3, beat=1.0, chord="Cmaj7", quality="maj7"),
        HeadChange(bar=4, beat=1.0, chord="NC"),
    ]
    return Head(
        notes=notes,
        chords=chords,
        beats_per_bar=4,
        beat_type=4,
        measure_range=(1, 4),
    )


def fills(head: Head, **request: Any):
    """The fill slots for `request`, resolved against the head's own 4/4 metre."""
    filled = resolve_request(Request(**request), head.beats_per_bar, (1, 1, 1, 1))
    return headxml.fill_slots(head, filled)


class TestTheRestTimeline(unittest.TestCase):
    """`melody_rests`: a rest is the silence between notes, not a bar with no chord."""

    def test_a_rest_is_the_gap_between_sounding_notes(self):
        """Bar 1's quarter note covers beat 1, so beats 2, 3 and 4 are silence."""
        head = hand_head()
        rests = melody_rests(head, (1, 2))
        self.assertEqual(rests, [headxml.MelodyRest(bar=1, beat=2.0, beats=3.0)])

    def test_a_held_note_is_not_a_rest(self):
        """Bar 2 is a whole note: nothing is silent, so nothing is a rest.

        This is the distinction the policy rests on - `melody_state` calls the far
        side of the note "held", and a chord under a held note is `--chord-on`'s
        business rather than a fill's.
        """
        head = hand_head()
        for rest in melody_rests(head, (2, 3)):
            self.fail(f"a whole note produced a rest: {rest}")

    def test_a_rest_stops_where_the_next_note_begins(self):
        """Bar 3 is a half note, so its rest starts on beat 3 and runs two beats."""
        head = hand_head()
        self.assertEqual(
            melody_rests(head, (3, 4)), [headxml.MelodyRest(bar=3, beat=3.0, beats=2.0)]
        )

    def test_a_note_held_over_a_barline_covers_the_far_side(self):
        """The end is on the absolute beat line, so a bar line does not cut a note.

        A note of six beats fills bar 2 and the first half of bar 3, so it covers the
        bar line. The rest after it starts where the sound stopped - beat 3 of bar 3 -
        which a bar-by-bar scan could not say.
        """
        head = Head(
            notes=[
                HeadNote(bar=1, beat=1.0, pitch=60, duration=1.0),
                HeadNote(bar=2, beat=1.0, pitch=62, duration=1.5),
                HeadNote(bar=4, beat=1.0, pitch=64, duration=1.0),
            ],
            chords=[HeadChange(bar=1, beat=1.0, chord="C", quality="maj")],
            beats_per_bar=4,
            beat_type=4,
            measure_range=(1, 4),
        )
        self.assertEqual(
            melody_rests(head, (1, 4)), [headxml.MelodyRest(bar=3, beat=3.0, beats=2.0)]
        )

    def test_the_section_bounds_are_rest_bounds(self):
        """A section is a window on the timeline: silence outside it is not filled."""
        head = hand_head()
        self.assertEqual(melody_rests(head, (4, 5))[0].bar, 4)
        # Bar 1's rest is measured to the bar line, not to the next note in bar 2.
        self.assertEqual(melody_rests(head, (1, 2))[0].beats, 3.0)


class TestHold(unittest.TestCase):
    """`hold`: one chord per rest, split at a change and at a target."""

    def test_one_chord_per_rest_stating_the_harmony_in_force(self):
        """Bar 1's three beats of silence are one attack, not three."""
        slots = fills(hand_head(), chord_on="none", chord_fills=_CHORD_FILLS_HOLD)
        self.assertEqual(
            [(bar, beat, quality_of(name)) for _m, name, bar, beat, _d in slots],
            [(1, 2.0, "maj"), (3, 3.0, "maj7")],
        )

    def test_a_chord_change_splits_the_hold(self):
        """A rest that runs into a new chord states both, at the right beats.

        The chord stated is the one *in force*: a fill does not reharmonise, and it
        does not carry the old chord past the change.
        """
        head = hand_head()
        head.chords.insert(1, HeadChange(bar=1, beat=3.0, chord="Dm7", quality="m7"))
        slots = fills(head, chord_on="none", chord_fills=_CHORD_FILLS_HOLD)
        self.assertEqual(
            [(bar, beat, name) for _m, name, bar, beat, _d in slots],
            [(1, 2.0, "C"), (1, 3.0, "Dm7"), (3, 3.0, "Cmaj7")],
        )

    def test_a_target_inside_the_rest_does_not_duplicate_the_fill(self):
        """`--chord-on 3` attacks at beat 3, which is where the fill already was.

        Both producers mean one step: the target is stated once, and the union keeps
        it, because a target is the caller's explicit choice. The fill at beat 2 is
        still there, and the fill that would have begun at beat 3 is the target.
        """
        slots = fills(hand_head(), chord_on="3", chord_fills=_CHORD_FILLS_HOLD)
        positions = [(bar, beat) for _m, _n, bar, beat, _d in slots]
        self.assertEqual(positions, [(1, 2.0), (1, 3.0), (3, 3.0)])
        self.assertEqual(positions.count((1, 3.0)), 1)

    def test_a_rest_with_no_chord_gets_no_fill(self):
        """Bar 4 is silent under `NC`: there is no chord to state."""
        slots = fills(hand_head(), chord_on="none", chord_fills=_CHORD_FILLS_HOLD)
        self.assertEqual([bar for _m, _n, bar, _b, _d in slots], [1, 3])

    def test_the_fill_lasts_to_the_end_of_the_rest(self):
        """A held fill's duration is the rest's, so it cannot ring past it.

        Bar 1's three beats are split into one and two by the change (inserted here),
        and bar 3's is its whole two. A duration in whole notes, because that is the
        unit every renderer takes.
        """
        head = hand_head()
        head.chords.insert(1, HeadChange(bar=1, beat=3.0, chord="Dm7", quality="m7"))
        slots = fills(head, chord_on="none", chord_fills=_CHORD_FILLS_HOLD)
        self.assertEqual([round(slot[4], 6) for slot in slots], [0.25, 0.5, 0.5])

    def test_no_fill_slot_carries_a_melody(self):
        """A fill states the chord and never invents a note: the tune is resting."""
        for slot in fills(hand_head(), chord_on="none", chord_fills=_CHORD_FILLS_HOLD):
            self.assertIsNone(slot[0])


class TestComp(unittest.TestCase):
    """`comp`: the rest onset and every felt beat inside it."""

    def test_a_felt_beat_inside_a_long_rest_is_a_second_attack(self):
        """Bar 1's three-beat rest attacks on each beat; `hold` states one chord."""
        comp = fills(hand_head(), chord_on="none", chord_fills=CHORD_FILLS_COMP)
        hold = fills(hand_head(), chord_on="none", chord_fills=_CHORD_FILLS_HOLD)
        self.assertEqual(
            [(bar, beat) for _m, _n, bar, beat, _d in comp],
            [(1, 2.0), (1, 3.0), (1, 4.0), (3, 3.0), (3, 4.0)],
        )
        self.assertEqual(
            [(bar, beat) for _m, _n, bar, beat, _d in hold],
            [(1, 2.0), (3, 3.0)],
        )

    def test_each_comp_lasts_to_the_next_attack(self):
        """The attacks tile the rest: no gap, and nothing rings into the melody."""
        comp = fills(hand_head(), chord_on="none", chord_fills=CHORD_FILLS_COMP)
        self.assertEqual([round(slot[4], 6) for slot in comp], [0.25] * 5)

    def test_comp_states_every_attack_hold_does(self):
        """`comp` is `hold` plus the interior beats: the same onsets, the same chords.

        The two policies are one timeline read at two densities, so `comp` can never
        *drop* an attack - a rest whose interior is empty gives exactly `hold`'s
        answer, which is the shape of most rests in the committed heads.
        """
        comp = fills(hand_head(), chord_on="none", chord_fills=CHORD_FILLS_COMP)
        hold = fills(hand_head(), chord_on="none", chord_fills=_CHORD_FILLS_HOLD)
        by_position = {(slot[2], slot[3]): slot for slot in comp}
        for slot in hold:
            self.assertEqual(by_position[(slot[2], slot[3])][1], slot[1])

    def test_the_grouping_decides_where_a_felt_beat_is(self):
        """A 6/8 bar has two pulses, so a four-eighth rest holds one attack, not four.

        The grouping, not the denominator count, for the same reason `rhythm_beats`
        reads it: six eighths are two dotted-quarter pulses, so the only felt beat
        inside beats 2-6 is the second pulse at beat 4.
        """
        head = Head(
            notes=[HeadNote(bar=1, beat=1.0, pitch=60, duration=0.125)],
            chords=[HeadChange(bar=1, beat=1.0, chord="C", quality="maj")],
            beats_per_bar=6,
            beat_type=8,
            measure_range=(1, 1),
        )
        slots = headxml.fill_slots(
            head,
            resolve_request(
                Request(chord_on="none", chord_fills=CHORD_FILLS_COMP), 6, (3, 3)
            ),
            grouping=(3, 3),
        )
        self.assertEqual(
            [(bar, round(beat, 6)) for _m, _n, bar, beat, _d in slots],
            [(1, 2.0), (1, 4.0)],
        )


class TestTheRequestKeepsItsShape(unittest.TestCase):
    """The fill is a request field, so the refusals and the derivation apply to it."""

    def test_fills_make_the_chord_part_exist_on_its_own(self):
        """`--chord-on none --chord-fills hold` still has a chord part to state.

        Without this the melody-only gate would return the skeleton before a fill was
        ever computed - the mode's whole premise is that the chord exists *only* in
        the rests.
        """
        resolved = resolve_request(
            Request(chord_on="none", chord_fills=_CHORD_FILLS_HOLD), 4, (1, 1, 1, 1)
        )
        self.assertIn("chord", resolved.parts)
        self.assertEqual(resolved.chord_fills, _CHORD_FILLS_HOLD)

    def test_fills_asked_for_by_a_guitar_that_does_not_sing_are_refused(self):
        """There are no melody rests on a part that has no melody."""
        with self.assertRaises(ValueError) as error:
            resolve_request(
                Request(melody=False, chord_on="every-beat", chord_fills=_CHORD_FILLS_HOLD),
                4,
                (1, 1, 1, 1),
            )
        self.assertIn("no melody rests to fill", str(error.exception))

    def test_none_is_the_default_and_adds_nothing(self):
        """The shipped request fills nothing, which is what `head FILE` promises."""
        self.assertEqual(Request().chord_fills, CHORD_FILLS_NONE)
        self.assertEqual(fills(hand_head(), chord_on="none"), [])


class TestAFillInARealHead(unittest.TestCase):
    """End to end: the fills arrive as steps, on the fixture's own rest."""

    def test_a_rest_in_a_committed_head_becomes_a_comping_step(self):
        """Bar 6 of `synthetic_repeat_slash` (2/2) rests from 1.5 to the bar line.

        The old default unioned a chord there; the request does not, and `--chord-fills`
        is how a caller asks for it back. The step carries no melody, states the chord
        in force **at the rest's onset** (Am7, which the bar changes away from on beat
        2) and says so on the line.
        """
        steps, _head, _notes = arranged(
            SLASH,
            section=(5, 7),
            request=Request(chord_on="none", chord_fills=_CHORD_FILLS_HOLD),
        )
        fill = [step for step in steps if step.melody is None]
        self.assertEqual(
            [(step.bar, step.beat, step.chord) for step in fill],
            [(6, 1.5, "Am7"), (6, 2.0, "D9")],
        )
        from arranger import format_progression

        for step in fill:
            self.assertFalse(step.melody_voiced, step.voicing.tab_string())
            self.assertIn("the tune is silent here", format_progression([step]))

    def test_the_default_run_still_invents_nothing(self):
        """The same section without the flag is the tune's own notes and no fill."""
        steps, _head, _notes = arranged(SLASH, section=(5, 7))
        self.assertTrue(all(step.melody for step in steps))
        self.assertEqual(len(steps), 3, [step.voicing.tab_string() for step in steps])

    def test_the_staff_shows_the_fill_as_a_column_of_its_own(self):
        """The whole-progression renderer agrees with the one-line tab.

        A fill is a step like any other, so the staff has to carry it: this is the
        renderer-level half of the "one arrangement, five writers" rule, on a step the
        melody column leaves empty.
        """
        from tabstaff import format_tab_staff

        steps, head, _notes = arranged(
            SLASH,
            section=(6, 7),
            request=Request(chord_on="none", chord_fills=_CHORD_FILLS_HOLD),
        )
        staff = format_tab_staff(
            steps,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
        )
        # Two fill columns, `x-x-7-5-8-x` and `x-9-7-5-x-x`. Nothing else sounds in this
        # section - the tune is silent across the two bars and no chord position is asked
        # for - so the staff's digits are exactly the frets of those two shapes.
        frets = sorted({glyph for glyph in "".join(staff) if glyph.isdigit()})
        self.assertEqual(frets, ["5", "7", "8", "9"])




if __name__ == "__main__":
    unittest.main()



