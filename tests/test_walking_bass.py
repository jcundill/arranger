"""The walking-bass line, **integrated**: what `arrange_progression` does with it.

The pure pass - which note the thumb plays - is `test_bass.py`, deliberately
unintegrated. This file pins the decisions that could only be settled by looking at
output: decision B, the **union** (the step list grows past the progression it was given,
and a held melody sounds one soprano note over four thumb notes); decision C, a **fill is
the melody alone**, and so is a target no shell can sound; decision E, a mid-bar change
**re-anchors** the thumb on the same slot the left hand states the new chord; decision F,
the second bar of a held chord, where the thumb re-anchors either way and the left hand
restates the shell only where the melody moves onto that downbeat.

Where the thumb's note is fretted is `test_bass_placement.py`, and what the renderers
draw is `test_walking_bass_rendering.py`. This file also holds the two claims that the
feature is *contained*: the fields are inert under a texture that does not ask for them,
and a bar with no chord has no bass part.

No test here is `skipUnless`-guarded: this is engine work, with no optional dependency and
no database.
"""

from __future__ import annotations

import unittest
from typing import List, Optional, Tuple

from musthe import Note

import arranger
from arranger import TimeSignature, VoiceLeadingEngine, beat_offset
from arranger.annotation import step_annotation

# The precedence rule `bass._melody_in_force` implements. The two private helpers are
# imported from where they live rather than through the package facade, because
# re-exporting them would put internals into the public surface for the benefit of one
# test file. `test_bass.py` covers them directly for the same reason. `beat_offset` is
# not private any more: `headxml` reads the same rule for a note held across a barline,
# so it is public in `grid` and reached through the facade above.
from arranger.bass import (
    _melody_in_force,
    _melody_timeline,
    walking_slots,
)
from arranger.bass_rules import (
    BASS_ALL_RULES,
    BASS_ROLE_APPROACH,
    BASS_RULES,
    BASS_STYLE_ANCHORS,
    parse_bass_style,
)
from arranger.options import ArrangeOptions, Request
from arranger.tuning import NO_CHORD, ROLE_FILL, ROLE_TARGET
from tests.support import (
    MAJOR_CADENCE,
    MINOR_CADENCE,
    bass_name,
    major_cadence_tabs,
    minor_cadence_tabs,
    upper_pitches,
    walk,
)


class TestValidation(unittest.TestCase):
    """The walk is a **bass style** over a texture, and it is validated like one."""

    def test_the_walk_is_an_accepted_bass_style(self):
        """The style is a list of `BASS_RULES`, and the pair it is spelled with arranges.

        It used to be a texture of its own (`texture="walking_bass"`), which made one
        name cover two claims - what the thumb states, and how many notes the chord
        part states. `docs/history/parts.md` §6 splits them, so what "accepted" means here is that
        `bass_notes="root,5th,approach,nearest"` parses and the arrangement it makes is one bar of four
        beats.
        """
        self.assertEqual(set(parse_bass_style(BASS_ALL_RULES)), set(BASS_RULES))
        self.assertEqual(len(walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])), 4)

    def test_an_unknown_texture_is_still_rejected_before_any_voicing(self):
        """
        The validation happens first, so a typo costs a message rather than a whole
        arrangement. Asserted through the public call because the *ordering* is the
        property: the walk must not be computed for a texture that does not exist.
        """
        with self.assertRaises(ValueError) as caught:
            VoiceLeadingEngine.arrange_progression(
                [("F5", "maj7", "Fmaj7")], options=ArrangeOptions(request=Request(chord_notes="sorcery"))
            )
        self.assertIn("sorcery", str(caught.exception))


class TestTheUnion(unittest.TestCase):
    """Decision B: the bass grid is finer than the melody grid."""

    def test_a_held_whole_note_yields_one_soprano_note_and_four_bass_notes(self):
        """
        The plan's own worked example, bar 1.

        One melody slot - a whole note - becomes **four** steps: the first carries the
        melody and the shell, and the other three exist only for the thumb. This is
        the assertion that fails if the bass grid is assumed to be the melody grid, and
        it is why `arrange_progression` may now return more steps than it was given.
        """
        steps = walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])
        self.assertEqual(len(steps), 4)
        self.assertEqual([step.beat for step in steps], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual([step.bass is not None for step in steps], [True] * 4)
        # Exactly one of them strikes a string above the bass.
        self.assertEqual(
            [step.bass_only for step in steps], [False, True, True, True]
        )

    def test_the_step_list_grows_past_the_progression(self):
        """
        The contract change, asserted as a fact rather than tolerated.

        A caller that zips its progression against the steps, or counts bars from
        `len(steps)`, is wrong under this texture and only this one. The second half
        is the control: with a melody slot on every walked beat there is nothing to
        add, so the two counts agree - the growth is the union doing its job, not a
        constant offset.
        """
        self.assertEqual(len(walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])), 4)
        eighths = [(0, 1.0 + 0.5 * n) for n in range(8)]
        self.assertEqual(len(walk([("F5", "maj7", "Fmaj7")] * 8, eighths)), 8)

    def test_a_sparser_skeleton_still_walks_every_beat(self):
        """
        Four melody slots on the beats give four walked beats and four steps, so the
        walk is on the **beat grid** rather than on whatever the melody happened to
        supply.

        Asserted as the *anchor* rather than as the notes: a walk is not four copies
        of the root, and pinning the exact line here would duplicate what
        `test_bass.py` already owns.
        """
        on_beats = [(0, float(beat)) for beat in (1, 2, 3, 4)]
        steps = walk([("F5", "maj7", "Fmaj7")] * 4, on_beats)
        self.assertEqual(len(steps), 4)
        self.assertEqual([bass_name(step) for step in steps], ["F", "E", "F", "E"])
        self.assertEqual(steps[0].bass_role, "anchor")
        # All four are *melody* slots here, so none of them is a bass-only step: the
        # union only invents slots when the beat grid is finer than the melody's.
        self.assertEqual([step.bass_only for step in steps], [False] * 4)

    def test_a_bass_only_step_still_carries_the_harmony(self):
        """
        The extra slot is a place the thumb plays, not a hole in the tune.

        It carries the previous melody pitch and the harmony in force, so a renderer
        printing the chord name above it is not claiming a chord that stopped.
        """
        for step in walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])[1:]:
            self.assertEqual(step.chord, "Fmaj7")
            self.assertEqual(step.melody, "F5")

    def test_the_thumb_anchors_the_root_on_every_downbeat(self):
        """
        The anchor rule, over a real two-bar progression rather than a fixture of the
        pure pass.

        A chord lasting two bars is re-anchored on **each** downbeat, because the
        anchor is a metric event: re-striking the root is what marks the bar. This is
        deliberately a different assertion from "one shell per chord", which is about
        the left hand and is the *opposite* rhythm.
        """


class TestTheWalkFollowsTheFeltBeats(unittest.TestCase):
    """A grouped metre walks its **pulses**, not every denominator unit.

    The union is unchanged: a held melody still sounds one soprano note over several
    thumb notes. What moves is how many notes the metre asks for - four in 12/8, not
    twelve - and where the approach falls.
    """

    @staticmethod
    def walked(
        beats_per_bar: int,
        beat_type: int,
        grouping: Optional[str] = None,
    ) -> List[arranger.ArrangementStep]:
        timings: List[Tuple[int, float, Optional[float]]] = [(0, 1.0, None)]
        return VoiceLeadingEngine.arrange_progression(
            [("F5", "maj7", "Fmaj7")],
            timings=timings,
            options=ArrangeOptions(
                request=Request(
                    chord_notes="targets", bass_on="every-beat", bass_notes="walk"
                ),
            ),
            time_signature=TimeSignature(
                beats_per_bar, beat_type, grouping if grouping is not None else "auto"
            ),
        )

    def test_a_twelve_eight_bar_walks_its_four_pulses(self):
        steps = self.walked(12, 8)
        self.assertEqual([step.beat for step in steps], [1.0, 4.0, 7.0, 10.0])
        self.assertEqual([step.bass is not None for step in steps], [True] * 4)
        self.assertEqual([step.bass_only for step in steps], [False, True, True, True])

    def test_a_nine_eight_bar_walks_three(self):
        self.assertEqual(
            [step.beat for step in self.walked(9, 8)], [1.0, 4.0, 7.0]
        )

    def test_a_six_eight_bar_walks_two(self):
        self.assertEqual([step.beat for step in self.walked(6, 8)], [1.0, 4.0])

    def test_a_simple_five_four_bar_still_walks_every_beat(self):
        """`auto` does not guess a grouping for 5/4, so it stays five beats."""
        self.assertEqual(
            [step.beat for step in self.walked(5, 4)],
            [1.0, 2.0, 3.0, 4.0, 5.0],
        )

    def test_a_five_four_bar_named_three_plus_two_walks_two(self):
        self.assertEqual(
            [step.beat for step in self.walked(5, 4, "3+2")], [1.0, 4.0]
        )

    def test_the_approach_lands_on_the_last_felt_beat(self):
        """12/8's approach is on beat 10, not on the twelfth eighth."""
        timings: List[Tuple[int, float, Optional[float]]] = [
            (0, 1.0, None),
            (1, 1.0, None),
        ]
        steps = VoiceLeadingEngine.arrange_progression(
            [("F5", "maj7", "Fmaj7"), ("F5", "maj7", "Fmaj7")],
            timings=timings,
            options=ArrangeOptions(
                request=Request(
                    chord_notes="targets", bass_on="every-beat", bass_notes="walk"
                ),
            ),
            time_signature=TimeSignature(12, 8),
        )
        last_of_first = next(
            step
            for step in steps
            if step.bar == 0 and abs((step.beat or 0.0) - 10.0) < 1e-9
        )
        self.assertEqual(last_of_first.bass_role, BASS_ROLE_APPROACH)


class TestFillsAreTheMelodyAlone(unittest.TestCase):
    """Decision C, and the two ways it can be undone."""

    def test_a_fill_sounds_the_melody_and_the_thumb_and_nothing_else(self):
        """
        The assertion that would catch a fill silently reverting to a duo or an
        interval: the upper voices are exactly `{melody}`.

        Spelled as a property rather than an exact string, because the note and its
        fret depend on the position - it is the *count* that is the design.
        """
        for step in walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])[1:]:
            self.assertEqual(step.role, ROLE_FILL)
            self.assertEqual(upper_pitches(step), [Note("F5").midi_note()])
            self.assertIsNotNone(step.bass)

    def test_a_fill_is_not_annotated_as_a_missing_chord(self):
        """
        A fill *has* a harmony, it is simply not spelled out.

        `melody_only` is the flag that says "there is no chord here", so a fill must
        not set it: the annotation would claim a lie, and the `repeated` hold keys off
        it.
        """
        for step in walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])[1:]:
            self.assertFalse(step.melody_only)
            self.assertNotIn("no chord", step_annotation(step))

    def test_an_off_beat_change_is_a_fill_under_the_new_chord(self):
        """
        The off-beat-change rule, and the test that fails if the empty fill tuple is
        left to the generic "no candidates" path.

        A chord arriving on the 4-and is voiced under the **new** chord - the harmony
        timeline is not this feature's business - but stays thin, because a passing
        slot under a shell would send the melody through the non-chord-tone
        strategies. So the step's only upper pitch is the melody.
        """
        steps = walk([("D5", "m7", "Dm7"), ("B4", "7", "G7")], [(0, 1.0), (0, 4.5)])
        change = steps[-1]
        self.assertEqual(change.chord, "G7")
        self.assertEqual(change.role, ROLE_FILL)
        self.assertEqual(upper_pitches(change), [Note("B4").midi_note()])

    def test_a_fill_is_never_promoted_to_a_target(self):
        """
        The generic rule - "a fill that cannot be filled becomes a target" - is
        disabled for this texture, and the target fallback is the melody alone rather
        than a shell.

        Asserted as an absence of shells on every fill, so it holds whatever the
        melody is: the fallback must not quietly acquire a chord, because the texture
        would get busier precisely where it is meant to get lighter.
        """
        steps = walk(
            [("D5", "m7", "Dm7"), ("E5", "7", "G7"), ("F#5", "maj7", "Cmaj7")],
            [(0, 1.0), (0, 2.0), (0, 3.0)],
        )
        fills = [step for step in steps if step.role == ROLE_FILL]
        self.assertTrue(fills)
        for step in fills:
            self.assertNotEqual(step.voicing.grip, "shell")

    def test_a_target_that_cannot_be_a_shell_does_not_vanish(self):
        """
        `grips=("shell",)` is the whole target tuple, so this is the failure the plan
        names: D over Bbm7 - the major 3rd over a minor chord - has no
        `NON_CHORD_TONE_EXTENSIONS` route and no shell can sound it, so the step would
        be dropped with only a warning.

        The assertion is on the step's **presence**, not on the warning: the warning is
        easy to miss in a long run and says nothing about what a reader would have
        played instead.
        """
        steps = walk([("D5", "m7", "Bbm7")], [(0, 1.0)])
        self.assertEqual(len(steps), 4)
        self.assertEqual(steps[0].melody, "D5")
        self.assertEqual(upper_pitches(steps[0]), [Note("D5").midi_note()])
        self.assertIsNotNone(steps[0].bass)


class TestDecisionEAMidBarChange(unittest.TestCase):
    """A change on a strong beat re-anchors the thumb and states the chord."""

    def test_the_thumb_and_the_left_hand_name_the_same_chord_on_a_mid_bar_change(self):
        """
        The B section's bar 10, and the reason decision E exists.

        `Bbm7` for two beats and `Eb7` from beat 3 is one bar. The left hand states
        `Eb7` on beat 3 (beat 3 is a `TARGET_BEAT`), so the thumb must be on `Eb`
        there too - if it were still walking through `Bbm7` the two hands would be
        naming different chords on the same beat, which is the one thing this texture
        must never do. The beat-1 anchor is the *first* chord's root, not the second's.
        """
        steps = walk([("D5", "m7", "Bbm7"), ("F4", "7", "Eb7")], [(0, 1.0), (0, 3.0)])
        on_three = [step for step in steps if step.beat == 3.0][0]
        self.assertEqual(on_three.chord, "Eb7")
        self.assertEqual(on_three.role, ROLE_TARGET)
        self.assertEqual(on_three.bass_role, "anchor")
        self.assertEqual(bass_name(on_three), "Eb")
        first = [step for step in steps if step.beat == 1.0][0]
        self.assertEqual(bass_name(first), "Bb")


class TestDecisionFTheSecondBarOfAHeldChord(unittest.TestCase):
    """
    Bar 13-14 of the B section: two bars of one `G7`.

    The two readings are asserted apart on purpose, so switching between them later
    is a one-line change to one test rather than a rewrite.
    """

    def test_the_thumb_re_anchors_the_second_downbeat_either_way(self):
        """
        The thumb's half of decision F, which no reading disputes: a chord lasting two
        bars is re-anchored on each downbeat, because the anchor is a metric event.
        """
        steps = walk([("D5", "7", "G7"), ("D5", "7", "G7")], [(0, 1.0), (1, 1.0)])
        downbeats = [step for step in steps if step.beat == 1.0]
        self.assertEqual([step.bass_role for step in downbeats], ["anchor", "anchor"])
        self.assertEqual([bass_name(step) for step in downbeats], ["G", "G"])

    def test_the_left_hand_restates_the_shell_where_the_melody_moves(self):
        """
        The working rule, option (c): bar 14's `D5` follows a `C#5`, so the melody is
        genuinely re-articulated on that downbeat and the shell is restated - which is
        what the guide's own tab does, and what the plain "harmony changed" rule
        cannot produce.
        """
        steps = walk([("C#5", "7", "G7"), ("D5", "7", "G7")], [(0, 1.0), (1, 1.0)])
        second = [step for step in steps if step.beat == 1.0][-1]
        self.assertEqual(second.role, ROLE_TARGET)
        self.assertEqual(second.voicing.grip, "shell")

    def test_the_left_hand_stays_thin_where_the_melody_is_held(self):
        """
        The other half, and the reason this is a decision rather than a rule: a slot
        where the melody is simply ringing gets no shell restated under it. Under
        decision C a fill is the melody alone, so the bar states the root in the thumb
        and nothing else - thinner than a restated shell, and never claiming a harmony
        that is not sounding.
        """
        steps = walk([("D5", "7", "G7"), ("D5", "7", "G7")], [(0, 1.0), (1, 1.0)])
        second = [step for step in steps if step.beat == 1.0][-1]
        self.assertEqual(second.role, ROLE_FILL)
        self.assertEqual(len(upper_pitches(second)), 1)
        # The chord name above it still describes the harmony, and the thumb still
        # states the root: the bar is not empty, it is light.
        self.assertEqual(second.chord, "G7")
        self.assertIsNotNone(second.bass)


class TestAWalkInventedBeatTakesTheMelodyInForce(unittest.TestCase):
    """
    A beat invented for the thumb takes the melody
    **sounding** at that instant, not the melody the walk last happened to pass.

    The defect was in `_bass_slots`, which tracked `previous_melody` while iterating
    the walk's own beats. A melody slot was therefore only noticed when the walk landed
    on it, and in 2/2 the walk visits beats 1.0 and 2.0 only - so a melody moving at beat
    2.5 was invisible and the invented downbeat inherited from beat 2.0 instead. The
    file was right at every note onset and wrong in the gaps between them, which is why
    every check that compared the soprano against the melody at onsets passed.

    The tests are written so that **reverting the fix fails them**, which is asserted
    rather than assumed: see `test_the_pre_fix_rule_really_does_fail_these`.
    """

    def _bars_2_and_3(self):
        """The reported case: bar 2 beat 2.5 sustains into bar 3's invented downbeat.

        Reduced from "the synthetic cut-time head" to the six notes that matter, so a failure points at
        the rule rather than at a fixture. In 2/2 the melody slots of bar 2 are beats
        1.0, 2.0 and 2.5 and the walk visits 1.0 and 2.0 - which is the whole
        mechanism. `Eb4` runs 0.75 beats past its onset, so it is still sounding at bar
        3 beat 1.0, where the walk invents a beat.

        Bar 3 needs melody of its own: `_walking_bass_line` walks the bars the melody
        reaches, so a three-note progression ending in bar 2 produces no bar 3 at all
        and the test would pass for the wrong reason.
        """
        progression = [
            ("G4", "maj", "Ebmaj"),   # bar 2 beat 1.0
            ("F4", "maj", "Ebmaj"),   # bar 2 beat 2.0 - the note the bug inherited
            ("Eb4", "m7", "Cm7"),     # bar 2 beat 2.5 - the note that is sounding
            ("F4", "7", "Bb7"),       # bar 3 beat 1.5, after the invented downbeat
            ("G4", "7", "Bb7"),
            ("F4", "7", "Bb7"),
        ]
        timings = [
            (2, 1.0, 0.5),
            (2, 2.0, 0.25),
            (2, 2.5, 0.375),
            (3, 1.5, 0.25),
            (3, 2.0, 0.25),
            (3, 2.5, 0.25),
        ]
        return VoiceLeadingEngine.arrange_progression(
                progression, timings=timings, options=ArrangeOptions(
                                                          request=Request(
                                                              chord_notes="2", bass_on="every-beat", bass_notes="walk"
                                                          ),
                                                      ),
                time_signature=TimeSignature(2, 4)
            )

    def test_the_invented_downbeat_takes_the_sustaining_note_not_the_previous_one(self):
        """
        The symptom, in one assertion: the invented bar-3 downbeat carries `Eb4`.

        Before the fix it carried `F4` - the note at bar 2 beat 2.0 - which the score
        does play, so nothing about it was invalid, and that is precisely why the bug
        survived: it is a *plausible* note rather than a missing or impossible one.
        """
        steps = self._bars_2_and_3()
        downbeat = [step for step in steps if step.bar == 3 and step.beat == 1.0]
        self.assertEqual(len(downbeat), 1, "bar 3 beat 1.0 is not a walk-invented beat")
        self.assertEqual(
            downbeat[0].melody,
            "Eb4",
            "the invented downbeat is not carrying the note that is sounding",
        )

    def test_the_previous_note_is_not_carried_when_it_has_stopped(self):
        """
        The same rule read from the other side: `F4` ends at bar 2 beat 2.25, so bar 3
        must not inherit it.

        Pinned separately from the test above because "carries the right note" and
        "stops carrying the wrong one" fail independently - a fix that always used the
        sustaining note would pass the first and fail this only if the durations were
        also wrong.
        """
        steps = self._bars_2_and_3()
        downbeat = [step for step in steps if step.bar == 3 and step.beat == 1.0][0]
        self.assertNotEqual(downbeat.melody, "F4")

    def test_a_walk_invented_beat_before_the_first_melody_note_still_gets_one(self):
        """
        The `in_force < 0` branch, and the reason it is tested here rather than
        through an arrangement.

        A walk beat landing before the tune has started has no melody in force, and
        `_bass_slots` falls back to index 0 rather than dropping the step - the same
        "a step survives even when its bass cannot be placed" rule `attach_bass`
        follows.

        It cannot be reached from the public API, and that is worth stating rather
        than working around: `_walking_bass_line` walks **the bars the melody
        reaches**, so an invented beat can never precede the first melody note. The
        branch is defensive against a caller that supplies a `bass_line` the walk
        could not have produced. So it is asserted on the rule itself - and
        `test_the_fallback_is_reachable_only_that_way` pins the reason, so this test
        cannot quietly become vacuous if the walk is ever widened.
        """
        self.assertEqual(_melody_in_force([], 0.0), -1)
        # One note starting after the beat asked about: still nothing in force.
        timeline = _melody_timeline([(0, 2, 1.0, 1.0)], beats_per_bar=4)
        self.assertEqual(_melody_in_force(timeline, beat_offset(1, 1.0, 4)), -1)

    def test_a_durations_span_is_measured_in_beats_not_in_bars(self):
        """A slot's `duration` becomes `duration * beat_type` beats, not `* beats_per_bar`.

        A beat is `4 / beat_type` quarters, so one whole note is `beat_type` beats: four
        in 3/4, **eight** in 6/8. Asserted on both because they disagree in both
        directions - the count overstates in 6/8 and understates in 3/4 - which is the
        pair that tells the two spellings apart. Correcting the arithmetic moves no step
        of any committed head, because the walk's chord timeline is onset-driven and only
        a melody-in-force span reads a duration; it is pinned because the next
        metre-sensitive rule will read one.
        """
        # A half note in 3/4: 0.5 whole notes, two beats, in a bar three beats wide.
        self.assertEqual(
            _melody_timeline([(0, 1, 1.0, 0.5)], beats_per_bar=3, beat_type=4),
            [(0.0, 2.0, 0)],
        )
        # A quarter in 6/8: 0.25 whole notes, two beats, because a beat is an eighth.
        self.assertEqual(
            _melody_timeline([(0, 1, 1.0, 0.25)], beats_per_bar=6, beat_type=8),
            [(0.0, 2.0, 0)],
        )

    def test_the_engine_reads_the_denominator_it_is_given(self):
        """`beat_type` reaches the walk's melody timeline, and its default is 4.

        The plumbing is what makes the fix real rather than local, and one invented beat
        shows it: a whole note is four beats in 3/4 and eight in 6/8, so the same pair of
        timings has a *different note still sounding* when the walk reaches beat 3 -
        `Cmaj7` over E5 at the 3/4 reading, `Dm7` over F5 at the 6/8 one. Nothing in the
        committed material moves either way, which is why the seam is asserted here
        rather than inferred from an arrangement.
        """
        from arranger.options import ArrangeOptions

        progression = [("E5", "maj7", "Cmaj7"), ("F5", "m7", "Dm7")]
        timings = [(1, 1.0, 1.0), (1, 2.0, 0.25)]

        def invented(beat_type: int) -> List[Tuple[str, Optional[str]]]:
            steps = VoiceLeadingEngine.arrange_progression(
                progression,
                timings=timings,
                options=ArrangeOptions(
                    request=Request(
                        chord_notes="2", bass_on="every-beat", bass_notes="walk"
                    ),
                ),
                time_signature=TimeSignature(3, beat_type),
            )
            return [(step.chord, step.melody) for step in steps]

        # Three beats of a 3/4 bar: the melody notes, then the invented third beat.
        self.assertEqual(invented(4)[-1], ("Cmaj7", "E5"))
        self.assertEqual(invented(8)[-1], ("Dm7", "F5"))
        # Saying nothing is the 4 the signature defaults to, so a hand-built
        # progression - which has no notated metre to state - keeps the arithmetic it
        # always had.
        self.assertEqual(ArrangeOptions().time_signature.beat_type, 4)
        by_default = [
            (step.chord, step.melody)
            for step in VoiceLeadingEngine.arrange_progression(
                progression,
                timings=timings,
                options=ArrangeOptions(
                    request=Request(
                        chord_notes="2", bass_on="every-beat", bass_notes="walk"
                    ),
                ),
                time_signature=TimeSignature(3, 4),
            )
        ]
        self.assertEqual(by_default, invented(4))

    def test_the_fallback_is_reachable_only_that_way(self):
        """
        The premise of the test above: no arrangement can produce that state.

        Asserted so the defensive branch above stays honest. If a future change made
        the walk cover bars the melody does not reach - which is defensible - this
        test would fail and the branch would become reachable through a real
        arrangement, at which point it should be tested there too.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("G4", "maj", "Ebmaj"), ("F4", "maj", "Ebmaj")],
            timings=[(2, 1.0, 0.5), (2, 2.0, 0.5)],
            options=ArrangeOptions(
                        request=Request(chord_notes="2", bass_on="every-beat", bass_notes="walk"),
                    ),
            time_signature=TimeSignature(4, 4),
        )
        first_onset = beat_offset(2, 1.0, 4)
        for step in steps:
            if step.bass_only and step.bar is not None and step.beat is not None:
                self.assertGreater(
                    beat_offset(step.bar, float(step.beat), 4),
                    first_onset,
                    "the walk invented a beat before the melody starts",
                )

    def test_a_rest_under_the_walk_takes_the_note_the_hand_is_holding(self):
        """
        Where the score writes silence, the last note started is what the left hand is
        still holding, so that is what the invented beat names.

        This is the branch that is easy to get wrong in the other direction: reading
        "the melody in force" strictly would find nothing sounding and leave the beat
        with no melody at all. Asserted because the fallback is a decision, not an
        accident - and because on "the synthetic cut-time head" it is 5 of the 22 invented beats.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("G4", "maj", "Ebmaj"), ("G4", "maj", "Ebmaj")],
            timings=[(1, 1.0, 0.25), (1, 2.0, None)],
            options=ArrangeOptions(
                        request=Request(chord_notes="2", bass_on="every-beat", bass_notes="walk"),
                    ),
            time_signature=TimeSignature(4, 4),
        )
        held = [step for step in steps if step.melody == "G4" and step.bar == 1]
        self.assertTrue(
            any(step.beat == 3.0 for step in held),
            "no step covers the rest at beat 3.0, so the fallback was not exercised",
        )
        self.assertEqual([step.melody for step in held if step.beat == 3.0], ["G4"])

    def test_the_pre_fix_rule_really_does_fail_these(self):
        """
        The premise of everything above: the rule that was replaced is wrong.

        A test that passes both before and after a fix guards nothing. So the old rule
        is re-implemented here, in a few lines, and asserted to disagree with the
        engine on the reported bar. If a future change makes the two agree again, this
        fails and says the fixture no longer reproduces the defect.
        """
        progression = [
            ("G4", "maj", "Ebmaj"),
            ("F4", "maj", "Ebmaj"),
            ("Eb4", "m7", "Cm7"),
            ("F4", "7", "Bb7"),
            ("G4", "7", "Bb7"),
            ("F4", "7", "Bb7"),
        ]
        timings = [
            (2, 1.0, 0.5),
            (2, 2.0, 0.25),
            (2, 2.5, 0.375),
            (3, 1.5, 0.25),
            (3, 2.0, 0.25),
            (3, 2.5, 0.25),
        ]
        # The old rule, verbatim in shape: track the melody while walking the beats.
        melody_at = {
            (bar, float(beat)): index
            for index, (bar, beat, _duration) in enumerate(timings)
        }
        walked = [(2, 1.0), (2, 2.0), (3, 1.0)]
        previous_melody = -1
        old_choice = None
        for bar, beat in walked:
            key = (bar, beat)
            if key in melody_at:
                previous_melody = melody_at[key]
                continue
            old_choice = progression[previous_melody][0]
        self.assertEqual(old_choice, "F4", "the fixture no longer reproduces the bug")
        steps = VoiceLeadingEngine.arrange_progression(
                progression, timings=timings, options=ArrangeOptions(
                                                          request=Request(
                                                              chord_notes="2", bass_on="every-beat", bass_notes="walk"
                                                          ),
                                                      ),
                time_signature=TimeSignature(2, 4)
            )
        new_choice = [
            step for step in steps if step.bar == 3 and step.beat == 1.0
        ][0].melody
        self.assertEqual(new_choice, "Eb4")
        self.assertNotEqual(old_choice, new_choice)


class TestEveryHeadCarriesTheMelodyInForce(unittest.TestCase):
    """
    The population this rule covers, re-measured after the fix.

    The walk-invented population is measured per head rather than copied from the
    retired transcriptions: the synthetic heads are shorter, and the rule is asserted
    on every beat the sweep finds rather than on an old total.

    The waltz is here because it is the **third metre**. A rule proved on two would not
    have caught a grid that is `beats_per_bar` wide rather than four beats wide, and
    3/4 is the metre where a beat-3 melody slot and an invented beat coincide in a way
    2/2 and 4/4 do not produce. The triplet head is played on every beat of its dense
    bars, so the walk invents nothing there; it is not part of this population.

    The comparison is against `_melody_in_force` rather than a melody name written out
    here, because that is the rule under test: a hand-written expectation would be a
    second implementation of it, and would agree with a broken one just as happily.
    """

    HEADS = (
        "synthetic_cut_time.mxl",
        "synthetic_repeat_slash.musicxml",
        "synthetic_tab_export.musicxml",
        "synthetic_waltz.musicxml",
    )

    def test_no_walk_invented_beat_carries_a_note_that_is_not_sounding(self):
        """Every invented beat in every committed head carries the melody in force."""
        from headxml import head_skeleton, load_musicxml

        checked = 0
        for name in self.HEADS:
            with self.subTest(head=name):
                head = load_musicxml(f"tests/data/{name}")
                skeleton = head_skeleton(head)
                triples = [slot[0] for slot in skeleton]
                timings = [(slot[1], slot[2], slot[3]) for slot in skeleton]
                slots = walking_slots(
                    triples, timings, head.beats_per_bar, head.beat_type
                )
                located = [
                    (index, bar, beat, duration)
                    for index, (bar, beat, duration) in enumerate(timings)
                    if bar is not None and beat is not None
                ]
                timeline = _melody_timeline(located, head.beats_per_bar, head.beat_type)
                invented = [slot for slot in slots if slot.bass_only]
                self.assertTrue(
                    invented, f"{name}: no walk-invented beats, so nothing is checked"
                )
                for slot in invented:
                    self.assertIsNotNone(
                        slot.bar, f"{name}: an invented slot has no bar"
                    )
                    self.assertIsNotNone(
                        slot.beat, f"{name}: an invented slot has no beat"
                    )
                    if slot.bar is None or slot.beat is None:
                        continue
                    at = beat_offset(slot.bar, float(slot.beat), head.beats_per_bar)
                    in_force = _melody_in_force(timeline, at)
                    self.assertGreaterEqual(
                        in_force,
                        0,
                        f"{name} bar {slot.bar} beat {slot.beat}: "
                        "the melody has not started",
                    )
                    self.assertEqual(
                        triples[slot.index][0],
                        triples[in_force][0],
                        f"{name} bar {slot.bar} beat {slot.beat}: carries "
                        f"{triples[slot.index][0]}, but "
                        f"{triples[in_force][0]} is sounding there",
                    )
                checked += len(invented)
        # The synthetic heads are shorter than the retired transcriptions, so the
        # population is smaller. The rule is asserted per beat; this only says the
        # sweep found beats to assert it on.
        self.assertGreater(checked, 20, "suspiciously few invented beats examined")

    def test_the_heads_span_three_metres(self):
        """
        The premise of the row above: these are 2/2, 4/4 and 3/4.

        Asserted rather than assumed, because a fixture silently re-notated into 4/4
        would leave this test passing while covering one metre fewer - which is exactly
        how the "four-quarter walk" claim in `arrange_progression` came to be believed.
        """
        from headxml import load_musicxml

        metres = {
            load_musicxml(f"tests/data/{name}").beats_per_bar for name in self.HEADS
        }
        self.assertEqual(metres, {2, 3, 4}, "the committed heads lost a metre")


class TestNoRegression(unittest.TestCase):
    """The other two textures are untouched by anything above."""

    def test_uniform_and_targets_carry_no_bass_at_all(self):
        """
        The fields are inert outside the texture, which is what makes the assertions
        about them meaningful: `bass` is not populated by a melody that merely happens
        to sit on a bass string.
        """
        progression = [("D5", "m7", "Dm7"), ("C#5", "7", "A7"),
                       ("D5", "mMaj7", "Dm(maj7)")]
        onsets = [(0, 1.0), (0, 2.0), (0, 3.0)]
        timings: List[Tuple[int, float, Optional[float]]] = [
            (bar, beat, None) for bar, beat in onsets
        ]
        arrangements = [
            VoiceLeadingEngine.arrange_progression(progression),
            VoiceLeadingEngine.arrange_progression(
                progression, timings=timings, options=ArrangeOptions(request=Request(chord_notes="targets"))),
        ]
        for steps in arrangements:
            self.assertEqual(len(steps), 3)
            for step in steps:
                self.assertIsNone(step.bass)
                self.assertIsNone(step.bass_role)
                self.assertFalse(step.bass_only)
                self.assertIsNone(step.voicing.bass_midi)
                self.assertIsNone(step.voicing.bass_string)

    def test_the_same_input_gives_the_same_tabs_under_every_texture(self):
        """
        The backward-compatibility guarantee, from the other side.

        The cadences are the library's own demonstration fixtures, imported rather
        than re-typed so there is one definition of them, and the expected tabs are
        the pins `test_texture.py` already holds. Asserting them here too is
        deliberate: this is the file that could have broken them, because every slot
        now goes through `Slot`, the union and the walking-bass role rule, and the
        guarantee is that none of that is visible unless the texture asks for it.
        """
        # Imported, not re-typed. The docstring above says the point is that these tabs
        # are defined once; a second copy of the literals is a second thing to forget
        # to update, and it is how a stale pin survives a deliberate change.
        self.assertEqual(
            [s.tab_line() for s in VoiceLeadingEngine.arrange_progression(MINOR_CADENCE)],
            minor_cadence_tabs(),
        )
        self.assertEqual(
            [s.tab_line() for s in VoiceLeadingEngine.arrange_progression(MAJOR_CADENCE)],
            major_cadence_tabs(),
        )

    def test_adding_a_bass_does_not_change_the_melody(self):
        """
        The acceptance criterion stated as a test: the melody is provably unchanged.

        Every melody note of a walking arrangement is drawn from the progression it
        was given, in order - the union only ever *repeats* the previous one, never
        invents or reorders a pitch.
        """
        progression = [("F5", "maj7", "Fmaj7"), ("D5", "m7", "Dm7"),
                       ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7")]
        onsets = [(0, 1.0 + 0.5 * n) for n in range(8)]
        steps = walk(progression + progression, onsets + [(1, 1.0 + 0.5 * n)
                                                          for n in range(8)])
        written = [triple[0] for triple in (progression * 2)]
        sounded = [step.melody for step in steps if not step.bass_only]
        self.assertEqual(sounded, written)


class TestTheBassPolicyIsAnAxis(unittest.TestCase):
    """`bass` selects the pattern; the texture no longer carries it.

    `walking_bass` used to mean "a thumb line" as part of its name. Now it means "a
    thumb line, by default", and the same line is reachable from a texture that has
    never heard of walking bass. What must not change is that the default produces
    exactly what it always did - which is the whole of the equivalence below.
    """

    PROGRESSION = [
        ("F5", "maj7", "Fmaj7"),
        ("E5", "maj7", "Emaj7"),
        ("D5", "maj7", "Dmaj7"),
        ("C5", "7", "C7"),
        ("C5", "maj7", "Fmaj7"),
        ("B4", "m7", "Bm7"),
        ("A4", "maj7", "Amaj7"),
        ("G4", "7", "G7"),
    ]
    ONSETS: List[Tuple[int, float]] = [(0, 1.0 + 0.5 * i) for i in range(8)]

    def arrange(self, **request_kwargs):
        timings = [
            (bar, beat, None) for bar, beat in self.ONSETS
        ]
        return VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION,
            timings=timings,
            options=ArrangeOptions(request=Request(**request_kwargs)),
        )

    def tabs(self, steps):
        return [s.voicing.tab_string() for s in steps]

    def test_the_named_walk_is_the_pinned_line(self):
        """The walk is **named** now, and the named spelling is what the tabs are pinned to.

        `auto` used to resolve to a walk because `texture="walking_bass"` *meant* a
        thumb line, and every published walking-bass tab is pinned against that
        arrangement. With the walk on the bass axis there is no texture left that
        implies one, so the shipped answer is no line (`docs/history/parts.md` §9) - the
        equivalence this asserts is therefore the other direction: the style and the
        four rules it is spelled from are one arrangement, and the default is not it.
        """
        named = self.tabs(
            self.arrange(chord_notes="targets", bass_on="every-beat", bass_notes="walk")
        )
        spelled = self.tabs(
            self.arrange(
                chord_notes="targets",
                bass_on="every-beat",
                bass_notes=BASS_ALL_RULES,
            )
        )
        self.assertEqual(named, spelled)
        self.assertNotEqual(
            named,
            self.tabs(self.arrange(chord_notes="targets")),
            "the default produced the walk, so `bass` is not an axis",
        )

    def test_the_walk_needs_a_bass_part_to_play_it(self):
        """A walk is a claim about the bass part, and the selection is what says.

        `(soprano, bass)` walks - it is the old `melody_bass` texture under the
        new spelling, measured byte for byte in `docs/history/one-fact.md`'s build
        notes. `(soprano,)` alone keeps no thumb, because nothing named a bass part;
        a bass part on its own has no chord part to carry the line, so the thumb
        *is* the line rather than doubling it.
        """
        alone = self.arrange(chord_on="none")
        self.assertTrue(alone)
        self.assertTrue(all(s.bass is None for s in alone))
        with_thumb = self.arrange(
            chord_on="none", bass_on="every-beat", bass_notes="walk"
        )
        self.assertTrue(any(s.bass is not None for s in with_thumb))
        lone = self.arrange(
            melody=False, chord_on="none", bass_on="every-beat", bass_notes="walk"
        )
        self.assertTrue(lone)
        self.assertTrue(any(s.bass is not None for s in lone))

    def test_bass_none_drops_the_thumb_and_keeps_the_shells(self):
        """A walking bass with no bass is still a coherent texture: shells on the beats.

        Dropping the policy drops the thumb and nothing else - the texture's own claim,
        which is a shell on a strong beat and the melody alone between them, is about
        the *left* hand and is unaffected by how many notes the thumb writes.
        """
        with_thumb = self.arrange(
            chord_notes="2", bass_on="every-beat", bass_notes="walk"
        )
        without = self.arrange(chord_notes="2")
        self.assertTrue(any(s.bass is not None for s in with_thumb))
        self.assertEqual([s.bass for s in without], [None] * len(without))
        shells = [s for s in without if s.grip == "shell"]
        self.assertTrue(shells, "the strong beats lost their shell")
        self.assertTrue(
            all(s.role == ROLE_TARGET for s in shells),
            "a shell appeared on a fill",
        )
        self.assertEqual(
            len(without), len(self.PROGRESSION),
            "without a grid the slot count should be one per melody note",
        )

    def test_anchors_writes_fewer_notes_than_a_walk(self):
        """Same texture, two policies, and the line is measurably sparser."""
        walked = self.arrange(
            chord_notes="2", bass_on="every-beat", bass_notes="walk"
        )
        anchored = self.arrange(
            chord_notes="2", bass_on="1", bass_notes=BASS_STYLE_ANCHORS
        )
        # The notes actually *struck*: a carried note rings into the steps after it,
        # so counting `s.bass` would measure the bar rather than the line.
        walked_notes = sum(1 for s in walked if s.bass is not None and not s.bass_held)
        anchored_notes = sum(1 for s in anchored if s.bass is not None and not s.bass_held)
        self.assertGreater(walked_notes, anchored_notes)
        self.assertGreater(anchored_notes, 0, "anchors wrote nothing at all")
        self.assertEqual(
            {
                s.bass_role
                for s in anchored
                if s.bass is not None and not s.bass_held
            },
            {"anchor"},
            "anchors wrote a connective role",
        )

    def test_a_texture_that_never_had_a_thumb_can_carry_one(self):
        """`targets` harmonises in full, and a thumb line under it is now expressible."""
        plain = self.arrange(chord_notes="targets")
        walked = self.arrange(
            chord_notes="targets", bass_on="every-beat", bass_notes="walk"
        )
        self.assertEqual([s.bass for s in plain], [None] * len(plain))
        self.assertTrue(any(s.bass is not None for s in walked))

    def test_uniform_no_longer_refuses_the_line_because_a_string_is_free(self):
        """
        This was the tree's one refusal, and the set behind it is gone.

        `uniform`'s palette held `drop24`'s `(4,2,1,0)`, the one reachable shape spanning
        all three thumb strings, so `bass_allowed` refused every policy and the caller was
        told which texture would work instead. The four inner-skip `drop24` sets were
        removed for a *finger* reason (`docs/history/fingering.md` §4.4) and that set was among
        them, so the worst case `uniform` can reach now leaves one string free - the rule's
        threshold - and the line is written.

        **Inverted rather than deleted.** It used to demand the refusal message and no bass
        notes; it now demands the opposite, and keeps the half that made the refusal safe -
        the arrangement still sounds, one step per melody note - so a silently dropped
        chord cannot pass for a working bass line.
        """
        steps = self.arrange(
            chord_notes="full", bass_on="every-beat", bass_notes="walk"
        )
        self.assertTrue(
            any(s.bass is not None for s in steps), "the walk wrote no note at all"
        )
        # And the arrangement still sounds.
        self.assertEqual(len(steps), len(self.PROGRESSION))
        self.assertTrue(all(s.voicing.active_frets() for s in steps))

    def test_an_unknown_policy_raises(self):
        with self.assertRaises(ValueError):
            self.arrange(
                chord_notes="targets", bass_on="every-beat", bass_notes="stride"
            )


class TestAChordlessBarHasNoBassPart(unittest.TestCase):
    """A part whose notes come from a chord cannot state anything where there is none.

    This is `docs/history/parts.md` §4's rule, derived rather than a rule about chordless bars:
    the chord part has no event and the bass part has no event either, while the melody
    part is unaffected. It is deliberately *not* the claim an off-grid rest makes - a grid
    thins the chords and not the bass line, so a rest keeps its thumb and "no chord here"
    and "silent here" stay separate facts.

    **The gate is synthetic, and that is the point.** Measured over the committed heads
    this moves 0 steps: `NC` occurs in one head (`Trouble_in_Mind_Blues`) as its *first*
    bar, where no harmony has sounded yet, so the forward fill had nothing to carry and
    the defect was invisible. No fixture has a chordless bar **between** two chords, which
    is the only place the old behaviour - continuing the previous harmony across the gap -
    could show itself. So the reproduction below is written rather than found.
    """

    # Bar 2 is chordless and sits between Dm7 and G7, so there is a harmony to anchor on
    # either side of it. That is what makes the old forward fill wrong here and not in
    # the corpus.
    PROGRESSION = [
        ("D4", "m7", "Dm7"),
        ("E4", NO_CHORD, NO_CHORD),
        ("C5", "7", "G7"),
    ]
    TIMINGS: List[Tuple[int, float, float]] = [
        (1, 1.0, 1.0),
        (2, 1.0, 1.0),
        (3, 1.0, 1.0),
    ]

    def arrange(self, **request_kwargs) -> List[arranger.ArrangementStep]:
        return VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION,
            timings=self.TIMINGS,
            options=ArrangeOptions(request=Request(**request_kwargs)),
        )

    def test_the_walked_bar_carries_no_thumb_note(self) -> None:
        """Under a texture that puts a note on every beat, the chordless bar has none."""
        steps = self.arrange(
            chord_notes="targets", bass_on="every-beat", bass_notes="walk"
        )
        walked = [s for s in steps if s.bar == 2]
        # One step, not four: with no chord there is no beat for the walk to be written
        # on, so the bar the grid would have invented collapses to its melody slot.
        self.assertEqual(len(walked), 1, [(s.bar, s.beat, s.chord) for s in steps])
        self.assertEqual(walked[0].chord, NO_CHORD)
        self.assertIsNone(walked[0].bass)
        self.assertIsNone(walked[0].bass_role)
        # The bars either side still walk, which is what proves the refusal is about the
        # missing chord rather than about the thumb being switched off.
        for bar in (1, 3):
            basses = [s.bass for s in steps if s.bar == bar]
            self.assertTrue(
                all(note is not None for note in basses),
                f"bar {bar} lost its thumb line: {basses}",
            )

    def test_the_melody_is_unaffected(self) -> None:
        """The third part is the one part an `NC` bar still states."""
        nc = [
            s
            for s in self.arrange(
                chord_notes="2", bass_on="every-beat", bass_notes="walk"
            )
            if s.chord == NO_CHORD
        ]
        self.assertEqual(len(nc), 1)
        self.assertEqual(nc[0].melody, "E4")
        self.assertTrue(nc[0].melody_voiced)

    def test_the_comping_route_rests_with_its_own_reason(self) -> None:
        """`"no chord here"` is a rest with a reason, not a chordless thumb line."""
        nc = [
            s
            for s in self.arrange(chord_notes="full", melody=False)
            if s.chord == NO_CHORD or s.silence == "nc_comping"
        ]
        self.assertTrue(nc, "the comping route has nothing to state over an NC bar")
        self.assertEqual(nc[0].silence, "nc_comping")
        self.assertIsNone(nc[0].bass)

    def test_the_bar_before_approaches_the_next_chord_that_sounds(self) -> None:
        """The consequence of the gap, and the reason it is one rule rather than two.

        The walk's last beat is chosen *backwards* from the next anchor. With the
        chordless bar continuing Dm7's harmony, that lookahead saw a phantom Dm7 anchor
        inside bar 2 and approached **D**; with the harmony ended at the `NC` slot it
        walks on to `G7`, which is the next chord that actually sounds. An `NC` bar
        therefore changes the note *before* it as well as its own, and this pins the
        direction: a half step from G, not a half step from D.
        """
        steps = self.arrange(
            chord_notes="2", bass_on="every-beat", bass_notes="walk"
        )
        last = [s for s in steps if s.bar == 1][-1]
        self.assertEqual(last.bass_role, BASS_ROLE_APPROACH)
        note = last.bass
        if note is None:
            self.fail("the bar before the gap lost its own thumb note")
        pitch = note % 12
        distance = min(abs(pitch - 7), 12 - abs(pitch - 7))
        self.assertEqual(distance, 1, f"approached {note}, G's root is pitch class 7")
        self.assertNotEqual(pitch, 2, "still approaching D, the previous root")
