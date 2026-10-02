"""
The walking-bass texture, **integrated**: `texture="walking_bass"` end to end.

`test_bass.py` covers the pure pass - which note the thumb plays - and is
deliberately unintegrated. This file covers what `arrange_progression` does with
that line, and it is where the decisions that could only be settled by looking at
output are pinned:

  - decision B, the **union**: the step list grows past the progression it was given,
    and a held melody sounds one soprano note over four thumb notes;
  - decision C, a **fill is the melody alone**, and so is a target no shell can sound;
  - decision E, a mid-bar change **re-anchors** the thumb on the same slot the left
    hand states the new chord;
  - decision F, the second bar of a held chord - the thumb re-anchors either way, the
    left hand restates the shell only where the melody moves onto that downbeat.

The two rules the placement step obeys are asserted on `_place_bass` directly rather
than through an arrangement, because they are about a fret distance and a sounding
order, and an arrangement only reaches them by accident. The `hand_fret` measurement
the pure pass could not make is made here, where an upper voicing exists.

No test here is `skipUnless`-guarded: this is engine work, with no optional
dependency and no database.
"""

from __future__ import annotations

import re
import unittest
from typing import List, Optional, Tuple

from musthe import Note

import arranger
from arranger import (
    BASS_STRING_INDICES,
    GRIP_MAX_SPAN,
    PITCH_CLASS_NAMES,
    ROLE_FILL,
    ROLE_TARGET,
    STANDARD_TUNING,
    ArrangementStep,
    VoiceLeadingEngine,
    _place_bass,
    _step_annotation,
    format_progression,
    format_tab_html,
    format_tab_staff,
    supported_string_sets,
)
from tabgp import _sounding_frets
from tabstaff import _strikes_here
from tests.support import bass_string, make_voicing, pc, upper_shape

# A staff string row, as opposed to the chord-name or melody line above it. Anchored
# on the label and the barline the renderer puts right after it (`e*|`, `B |`, ...),
# which is what separates it from a chord row: a chord called "Dm7" also starts with
# a `D`, so matching on the letter alone picks up the wrong line.
#
# Both cases of the high E are in the class because the renderer prints it either way:
# the top row is labelled lowercase `e` (the usual tab convention, so the two E rows
# stay distinct) while the bottom row keeps the uppercase `E` of `STRING_NAMES`.
_STRING_ROW = re.compile(r"^[eBGDAE][* ]?\|")


def walk(
    progression: List[Tuple[str, str, str]],
    onsets: Optional[List[Tuple[int, float]]] = None,
) -> List[arranger.ArrangementStep]:
    """A walking-bass arrangement of `progression`, with or without a beat grid."""
    # Annotated rather than inferred, because `Tuple` is invariant: a list of
    # `(int, float, None)` triples is not a `List[Tuple[int, float, Optional[float]]]`,
    # and pyright rejects it for exactly that reason. Same trap, same spelling, as
    # `BUT_NOT_FOR_ME_TIMINGS` in test_texture.py.
    timings: Optional[List[Tuple[int, float, Optional[float]]]] = (
        None if onsets is None else [(bar, beat, None) for bar, beat in onsets]
    )
    return VoiceLeadingEngine.arrange_progression(
        progression, timings=timings, texture="walking_bass"
    )


def upper_pitches(step: arranger.ArrangementStep) -> List[int]:
    """The upper voices alone: every sounding pitch except the thumb's.

    Walked from the fret vector rather than by comparing string indices, because the
    two hands do not have to agree about which string is lower - a 5-3-2 shell's
    A-string note sounds below its G-string note, which is the whole reason the
    sounding-order filter in `_place_bass` cannot be a tie-break. The thumb's string
    is dropped by **fret-vector index**, never by position in a filtered list, which
    is the mistake that would silently compare a string number against a list offset.
    """
    voicing = step.voicing
    bass_string = voicing.bass_string
    return sorted(
        STANDARD_TUNING[index].midi_note() + fret
        for index, fret in enumerate(voicing.frets)
        if fret >= 0 and index != bass_string
    )


def names(step: arranger.ArrangementStep) -> str:
    """The thumb's pitch class by name, or '-' when the step carries no bass."""
    if step.bass is None:
        return "-"
    return PITCH_CLASS_NAMES[step.bass % 12]


class TestValidation(unittest.TestCase):
    """`walking_bass` is a texture like any other, and it is validated like one."""

    def test_it_is_an_accepted_texture(self):
        """The name is in the table, so the existing check accepts it."""
        self.assertIn("walking_bass", arranger.TEXTURE_STYLES)
        self.assertEqual(len(walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])), 4)

    def test_an_unknown_texture_is_still_rejected_before_any_voicing(self):
        """
        The validation happens first, so a typo costs a message rather than a whole
        arrangement. Asserted through the public call because the *ordering* is the
        property: the walk must not be computed for a texture that does not exist.
        """
        with self.assertRaises(ValueError) as caught:
            VoiceLeadingEngine.arrange_progression(
                [("F5", "maj7", "Fmaj7")], texture="sorcery"
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
        self.assertEqual([names(step) for step in steps], ["F", "E", "F", "E"])
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
            self.assertNotIn("no chord", arranger._step_annotation(step))

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
        self.assertEqual(names(on_three), "Eb")
        first = [step for step in steps if step.beat == 1.0][0]
        self.assertEqual(names(first), "Bb")


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
        self.assertEqual([names(step) for step in downbeats], ["G", "G"])

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


class TestTheThumbReachesTheHandHoldingTheShape(unittest.TestCase):
    """
    The between-step invariant `fret_span()` cannot see, from item 1.

    Every per-step span in "But Not For Me" is at most 3, and the arrangement is still
    unplayable: one bar puts the hand at frets 6-8 and the next needs the D string at
    fret 1. Nothing spans seven frets; the *hand* does. A per-step number cannot catch
    that, so what is asserted here is a property of **consecutive** steps - the reach
    between where the thumb plays and where the fingers are holding.
    """

    def _arrangement(self):
        """The committed head that produced the defect, as a walking bass."""
        import contextlib
        import io

        from headxml import arrange_xml_head
        from tests.test_headxml import BUT_NOT_FOR_ME

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            steps, _, _ = arrange_xml_head(
                BUT_NOT_FOR_ME, grips=("shell",), texture="walking_bass"
            )
        return steps

    def test_the_thumb_never_shares_a_string_with_a_finger(self):
        """
        One string cannot sound two frets at once.

        This is the collision behind both item 1 and the item 2 GP5 corruption: the
        engine picked the thumb's string from the current step's thinned voicing rather
        than from the shape still ringing, so it could place the thumb where a finger
        already was.
        """
        steps = self._arrangement()
        held = None
        held_thumb = None
        checked = 0
        for step in steps:
            voicing = step.voicing
            if step.bass_only and held is not None and voicing.bass_string is not None:
                thumb = voicing.bass_string
                # The thumb's own previous note is not a finger: a walking bass moves
                # along one string constantly, and that string is its to reuse.
                if thumb != held_thumb:
                    checked += 1
                    self.assertLess(
                        held[thumb],
                        0,
                        f"bar {step.bar} beat {step.beat}: the thumb plays string "
                        f"{thumb} while the held shape has it at fret {held[thumb]}",
                    )
            if not step.bass_only and not step.repeated:
                held = list(voicing.frets)
                held_thumb = voicing.bass_string
        self.assertGreater(checked, 0, "no thumb was checked")

    def test_the_thumb_stays_within_reach_of_the_fingers(self):
        """
        The hand is one unit, so the thumb's fret and the held shape's fret range are
        not independent choices.

        Measured over the whole head the worst reach is 3 frets and the median 1,
        against the 7 the defect produced. The bound is deliberately loose: it guards
        against the shape of the bug returning, not a claim about how far a thumb can
        actually stretch, which is not this library's business to legislate.
        """
        steps = self._arrangement()
        held = None
        reaches = []
        for step in steps:
            voicing = step.voicing
            if step.bass_only and held is not None and step.bass is not None:
                thumb_fret = voicing.frets[bass_string(step)]
                fingers = [fret for fret in held if fret >= 0]
                if fingers:
                    low, high = min(fingers), max(fingers)
                    reaches.append(
                        low - thumb_fret if thumb_fret <= low else thumb_fret - high
                    )
            if not step.bass_only and not step.repeated:
                held = list(voicing.frets)
        self.assertGreater(len(reaches), 0, "no thumb note was checked")
        self.assertLessEqual(
            max(reaches),
            4,
            f"the thumb reaches {max(reaches)} frets from the held shape: "
            f"{sorted(reaches, reverse=True)[:5]}",
        )

    def test_the_documented_bar_no_longer_asks_for_a_seven_fret_stretch(self):
        """
        The exact pair from the report: bar 4 holds frets 6-8 and bar 5 needs the D
        string at fret 1.

        Asserted on the arrangement rather than on a summary, so that a future change
        which reintroduces it names the bar and the frets in the failure.
        """
        steps = self._arrangement()
        bars = {
            step.bar: step
            for step in steps
            if step.bar in (4, 5) and step.beat == 1.0
        }
        self.assertIn(4, bars, "the fixture no longer has the bar the report names")
        self.assertIn(5, bars)
        held_frets = [f for f in bars[4].voicing.frets if f >= 0]
        thumb_fret = bars[5].voicing.frets[bass_string(bars[5])]
        reach = (
            min(held_frets) - thumb_fret
            if thumb_fret <= min(held_frets)
            else thumb_fret - max(held_frets)
        )
        self.assertLessEqual(
            reach,
            4,
            f"bar 5's thumb at fret {thumb_fret} against bar 4's shape at "
            f"{min(held_frets)}-{max(held_frets)}",
        )

    def test_the_walk_loses_no_anchor_the_fix_did_not_already_lose(self):
        """
        The cost of the fix, asserted so it cannot be paid silently.

        Telling the thumb about the held shape removes candidate strings, so a naive
        version of this change loses thumb notes - and a walking bass with a gap in it
        is not a walking bass. **One** anchor in this head already had no reachable
        string before the fix (bar 15: the step's own upper voicing already sounds F3
        on the low E, and a thumb note must sound strictly below the structure it
        supports), so the assertion is that exact set rather than an empty one. A
        second entry here means this change cost a note.

        The anchors are selected by `bass_role` alone, and deliberately **not** by
        `bass_only` as well. They used to be filtered by both, and `docs/open-issues.md`
        item 4 is what made that wrong: a walk-invented downbeat the melody moves onto
        is a **target**, so it stopped being `bass_only` while remaining an anchor -
        and the filter quietly dropped it from this assertion, turning the test into
        one that could not fail. An anchor is an anchor whether or not the left hand
        holds across it, which is what makes `bass_role` the honest population.
        """
        steps = self._arrangement()
        anchors = [
            step
            for step in steps
            if step.bass_role == arranger.BASS_ROLE_ANCHOR
        ]
        self.assertGreater(len(anchors), 0)
        missing = [(step.bar, step.beat) for step in anchors if step.bass is None]
        self.assertEqual(
            [(15, 1.0)],
            missing,
            "the set of anchors with no thumb note changed",
        )


class TestABassOnlyStepIsNeverATarget(unittest.TestCase):
    """
    The invariant item 4 was really about, from `docs/open-issues.md`.

    `bass_only` and `role == ROLE_TARGET` are not two descriptions of one state, they
    are contradictory ones: the first means "nothing above the thumb strikes, the
    upper voices are held from the last shape", the second means "a full chord
    states the harmony here". A walk-invented downbeat the melody moves onto is
    promoted to a target by `_roles_for_slot`, so a slot could arrive carrying both,
    and the engine voiced a real `shell` or `melody` on it that every renderer then
    suppressed. The chord of the tune was in the arrangement and in none of the
    output.

    Asserted as a property of the flags rather than as a tab string, because the flag
    is what the four renderers read and the tab is four renderings of it.
    """

    def _walking_arrangement(self):
        """The committed head that produced the defect, as a walking bass."""
        import contextlib
        import io

        from headxml import arrange_xml_head
        from tests.test_headxml import BUT_NOT_FOR_ME

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            steps, _, _ = arrange_xml_head(
                BUT_NOT_FOR_ME, grips=("shell",), texture="walking_bass"
            )
        return steps

    def test_no_step_is_both_bass_only_and_a_target(self):
        """
        The contradiction itself. Nine steps in "But Not For Me" carried both flags
        before the fix, every one of them a walk-invented downbeat.
        """
        offenders = [
            (step.bar, step.beat)
            for step in self._walking_arrangement()
            if step.bass_only and step.role == ROLE_TARGET
        ]
        self.assertEqual(offenders, [], "a step is both bass-only and a target")

    def test_the_fills_are_still_bass_only(self):
        """
        The other half, and the reason the fix is a role test rather than a blanket
        one. Under decision C a fill is the melody alone and the melody it carries is
        the one already sounding, so holding it is correct and must survive.
        """
        steps = self._walking_arrangement()
        fills = [step for step in steps if step.bass_only and step.role == ROLE_FILL]
        self.assertEqual(len(fills), 13, "the held fills changed")

    def test_every_target_states_its_chord_in_every_renderer(self):
        """
        What the flags are *for*: a target's upper voices reach the output.

        Checked against all four renderers rather than one, because they disagreed -
        `tabxml` showed the chord and the other three hid it - and agreement between
        them is the property that was actually broken.
        """
        import tabxml
        from arranger.render import _step_cells

        checked = 0
        for step in self._walking_arrangement():
            if step.role != ROLE_TARGET or step.melody_only:
                continue
            checked += 1
            frets = step.voicing.frets
            upper = [i for i, f in enumerate(frets) if f >= 0 and i != step.voicing.bass_string]
            self.assertTrue(
                upper, f"bar {step.bar} beat {step.beat}: a target sounds no upper voice"
            )
            sounded = [
                i for i, cell in enumerate(_step_cells(step)) if cell.isdigit()
            ]
            self.assertEqual(
                sorted(sounded),
                sorted(i for i, f in enumerate(frets) if f >= 0),
                f"bar {step.bar} beat {step.beat}: the tab drops a target's voices",
            )
            self.assertEqual(
                sorted(i for i, _fret in _sounding_frets(step)),
                sorted(i for i, f in enumerate(frets) if f >= 0),
                f"bar {step.bar} beat {step.beat}: the GP5 drops a target's voices",
            )
            self.assertEqual(
                len(tabxml._sounding(step)),
                len([f for f in frets if f >= 0]),
                f"bar {step.bar} beat {step.beat}: the score drops a target's voices",
            )
        self.assertGreater(checked, 0, "no targets were checked")


class TestBassPlacement(unittest.TestCase):
    """
    `_place_bass`: the octave and the string, decided together against the hand.

    Asserted on the function rather than on an arrangement, because the rules below
    are about a fret distance and a sounding order, and an arrangement only reaches
    them by accident. The `hand_fret` measurement the pure pass could not make is
    made here, where an upper voicing exists.
    """

    def test_the_bass_takes_the_string_nearest_the_hand_not_the_lowest(self):
        """
        The rule, as a fret distance - which is what the rule *is*.

        D3 is fret 10 on the low E and fret 5 on the A string. Under a hand at fret 5
        the A string plays it in place; the low E would move the hand five frets for an
        identical pitch, which is the exact opposite of what this library is for.
        """
        upper = upper_shape([-1, -1, -1, 5, 5, 5])
        placed = _place_bass(upper, pc("D"))
        assert placed is not None, "D is reachable on both bass strings here"
        midi, string_index, fret = placed
        self.assertEqual(string_index, 1)
        self.assertEqual(fret, 5)
        self.assertEqual(midi, STANDARD_TUNING[1].midi_note() + 5)

    def test_the_low_string_wins_when_the_note_is_below_the_fifth_string(self):
        """
        The mirror image, so the rule cannot be satisfied by "always the A string".

        A2 is the 5th string's open pitch and E2 sits below it, so a walk descending
        into a dominant wants the 6th. The shape here occupies the 5th and the 4th,
        which is the 5-4-3 and 6-4-3 collision the three candidate strings exist to
        resolve - between them every shell in the table leaves at least one free.
        """
        upper = upper_shape([-1, 7, 7, 7, 7, 7])
        placed = _place_bass(upper, pc("E"))
        assert placed is not None
        _midi, string_index, fret = placed
        self.assertEqual(string_index, 0)
        self.assertEqual(fret, 0)

    def test_all_three_bass_strings_are_reachable(self):
        """
        Asserted in both directions, so no candidate is dead code.

        Each upper shape occupies a different pair of the three candidate strings, and
        every one of them must still leave somewhere for the thumb. The 4th string
        being free only under 1-2-3 and 5-3-2 is why it is carried at all: proximity
        ordering makes it self-limiting rather than dangerous.
        """
        shapes = {
            # 5-4-3 (1, 2, 3): the A and the D speak, so only the low E is free.
            "5-4-3": [-1, 7, 7, 7, -1, -1],
            # 6-4-3 (0, 2, 3): the low E and the D speak, so the A is free. Played high
            # enough that the shape's lowest voice is still above D3.
            "6-4-3": [12, -1, 12, 12, -1, -1],
            # (5, 3, 2): the D is the shell's lowest voice, so 6th and 5th are free.
            "5-3-2": [-1, -1, 7, 7, 7, 7],
            # 2-3-4 (4, 3, 2): the B, G and D speak. Played low, which is the only way
            # the 4th string wins - see the prediction below.
            "2-3-4": [-1, -1, 2, 2, 2, -1],
            # 1-2-3 (5, 4, 3): all three bass strings are free.
            "1-2-3": [-1, -1, -1, 7, 7, 7],
            # The same set played low, which is where the 4th string wins.
            "1-2-3 low": [-1, -1, -1, 2, 2, 2],
        }
        used = set()
        for label, frets in shapes.items():
            placed = _place_bass(upper_shape(frets), pc("D"))
            assert placed is not None, f"no bass string free under {label}"
            _midi, string_index, _fret = placed
            self.assertNotIn(
                string_index,
                {index for index, fret in enumerate(frets) if fret >= 0},
                label,
            )
            used.add(string_index)
        # All three candidates are used somewhere: the list is not dead code dressed
        # as a preference, which is the failure mode `5-3-2`'s own comment warns of.
        self.assertEqual(used, set(BASS_STRING_INDICES))

    def test_the_fourth_string_is_used_only_when_the_hand_is_low(self):
        """
        The prediction the plan makes about `BASS_STRING_INDICES`'s third entry.

        The A string is always five frets higher than the D for the same pitch, so
        proximity picks the D only when the hand is genuinely down there. Asserted as
        the *pair* of answers rather than as a fixed string, because the two halves
        are what make it a prediction: hand high and the low E wins even though the
        4th is free, and only a low hand brings the 4th into play at all.
        """
        chosen = {}
        for label, frets in (("high", [-1, -1, -1, 10, 10, 10]),
                             ("low", [-1, -1, -1, 0, 0, 0])):
            placed = _place_bass(upper_shape(frets), pc("D"))
            assert placed is not None
            _midi, string_index, _fret = placed
            chosen[label] = string_index
        # Hand at fret 10: the low E plays D3 at fret 10, in place.
        self.assertEqual(chosen["high"], 0)
        # Hand on the open strings: the 4th string plays it at fret 0, and the A
        # string would need five.
        self.assertEqual(chosen["low"], 2)

    def test_the_bass_must_sound_below_the_upper_structure(self):
        """
        A filter, not a tie-break, and the case that forces it: the tuning is not
        monotonic in the useful direction.

        The A string is five semitones *above* the D string it may neighbour, so a
        candidate can be reachable, can be at the hand, and still belong above the
        chord it is meant to support. Checked against the sounding pitches rather than
        the string indices, because the two disagree here by design.
        """
        # 5-3-2 with the A string's note as the shape's *lowest* sounding voice.
        upper = upper_shape([-1, 3, 5, 5, -1, -1])
        placed = _place_bass(upper, pc("E"))
        assert placed is not None
        midi, string_index, _fret = placed
        self.assertNotEqual(string_index, 1)
        self.assertLess(midi, min(upper.midi_notes()))

    def test_a_string_that_already_sounds_is_never_reused(self):
        """
        The other filter, and the one that keeps the collision off every shape.

        Swept rather than pinned to one fixture, because "the thumb never overwrites a
        voice" is a property of every shape rather than a fact about one of them.
        """
        shapes = ([-1, 7, 7, 7, -1, -1], [12, -1, 12, 12, -1, -1],
                  [-1, -1, 7, 7, 7, 7], [-1, -1, -1, 7, 7, 7])
        for frets in shapes:
            occupied = {index for index, fret in enumerate(frets) if fret >= 0}
            placed = _place_bass(upper_shape(frets), pc("D"))
            assert placed is not None, f"no bass string free under {frets}"
            _midi, string_index, _fret = placed
            self.assertNotIn(string_index, occupied)

    def test_the_octave_is_chosen_against_the_hand_not_the_pitch_class(self):
        """
        The regression for the whole pitch-class split, and the most valuable single
        test here.

        `C` is fret 3 on the 5th string and fret 15 an octave up - twelve frets apart
        for one note. Under a hand at fret 5, `C4` would put the thumb ten frets
        *above* the fingers, which is not one hand; `C3` does not. The pure pass
        cannot know which, which is exactly why it returns a pitch class.
        """
        upper = upper_shape([-1, -1, -1, 5, 7, 7])
        placed = _place_bass(upper, pc("C"))
        assert placed is not None
        midi, string_index, fret = placed
        self.assertEqual(string_index, 1)
        self.assertEqual(fret, 3)
        self.assertEqual(midi, STANDARD_TUNING[1].midi_note() + 3)

    def test_no_candidate_means_no_bass_rather_than_a_wrong_one(self):
        """
        The "penalty, never a filter" rule, at the level of the function.

        A shape occupying all three bass strings leaves the thumb nowhere, and the
        answer is `None` - the caller keeps the step and reports the omission. The
        alternative, placing the note somewhere it does not belong, would be a wrong
        bass rather than a missing one.
        """
        upper = upper_shape([5, 5, 5, 5, 5, 5])
        self.assertIsNone(_place_bass(upper, pc("D")))


class TestTheInvariant(unittest.TestCase):
    """
    The amended playability invariant for a step carrying a bass.

    *"The sounding strings are exactly one `supported_string_sets()` entry"*
    **cannot** hold once a thumb is merged: a 5-4-3 shell `(1,2,3)` becomes
    `{0,1,2,3}`, which is not a supported set. The rule is therefore stated over the
    **upper voices**, with the thumb required to sit outside them and below them -
    the same spirit as the melody-only `NC` exemption that already exists.
    """

    def test_the_upper_voices_are_one_supported_set_and_the_thumb_is_outside_it(self):
        """Swept over a real arrangement rather than one hand-built shape."""
        progression = [
            ("F5", "maj7", "Fmaj7"), ("D5", "m7", "Dm7"),
            ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7"),
        ]
        onsets = [(bar, 1.0 + 0.5 * n) for bar in range(4) for n in range(4)]
        checked = 0
        for step in walk(progression, onsets):
            bass_string = step.voicing.bass_string
            if step.bass is None:
                # No walk note on this slot, or none that could be placed. Either way
                # it is not a step carrying a bass, so the amendment does not apply -
                # and it must still be present, which the sweep's length asserts.
                continue
            upper_set = {
                index for index, fret in enumerate(step.voicing.frets)
                if fret >= 0 and index != bass_string
            }
            if len(upper_set) < 2:
                # A melody-alone step has no upper structure to be a member of, so it
                # is exempt in exactly the way an `NC` step already is. The bass rule is
                # the only part that applies to it, and it is checked.
                self.assertIn(bass_string, BASS_STRING_INDICES)
                self.assertLess(step.bass, min(upper_pitches(step)))
                continue
            checked += 1
            self.assertIn(
                upper_set, supported_string_sets(),
                f"{step.tab_line()} upper voices are not a supported set",
            )
            self.assertIn(bass_string, BASS_STRING_INDICES)
            self.assertNotIn(bass_string, upper_set)
            # The thumb sounds below everything it supports.
            self.assertLess(step.bass, min(upper_pitches(step)))
            # `fret_span()` still holds: the thumb shares the shell's position
            # budget, which is the whole point of placing it by proximity.
            self.assertLessEqual(step.voicing.fret_span(), GRIP_MAX_SPAN["shell"] + 5)
        self.assertGreater(checked, 0)

    def test_the_bass_is_outside_the_cost_tuple_by_construction(self):
        """
        "Select first, merge after" is the structural answer to coupling.

        The upper shape of a walking step is the one `_best_voicing` chose from a
        candidate list that never contained a thumb, so the cheapest way to assert the
        property is to show the candidates are unchanged by the texture: the shells
        `prepare_step` offers for a walking target are the shells it offers for any
        other caller asking for `("shell",)`.
        """
        triple = [("F5", "maj7", "Fmaj7")]
        walking = VoiceLeadingEngine.prepare_step(
            triple, 0, grips=arranger.TEXTURE_GRIPS["walking_bass"][ROLE_TARGET],
        )
        plain = VoiceLeadingEngine.prepare_step(triple, 0, grips=("shell",))
        assert walking is not None and plain is not None
        self.assertEqual(
            [v.tab_string() for v in walking.candidates],
            [v.tab_string() for v in plain.candidates],
        )
        # And none of them carries a bass, so `missing = 4 - len(active)` is intact.
        for candidate in walking.candidates:
            self.assertIsNone(candidate.bass_midi)
            self.assertIsNone(candidate.bass_string)


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
                progression, timings=timings, texture="targets"),
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
        now goes through `_Slot`, the union and the walking-bass role rule, and the
        guarantee is that none of that is visible unless the texture asks for it.
        """
        from tests.test_texture import (
            MAJOR_CADENCE,
            MINOR_CADENCE,
            major_cadence_tabs,
            minor_cadence_tabs,
        )

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


class TestWalkingBassRendering(unittest.TestCase):
    """Phase 6: the three renderer families draw a walking line rather than a chord list.

    The regression that matters most is the **collapse** one, because it is silent:
    `_staff_columns` decides hold-versus-strike from the sounding pitches, a thumb
    line changes the lowest of them every quarter, and nothing raises when the hold
    chain breaks - the arrangement just silently becomes the chord list the 0.7.0
    collapse behaviour exists to prevent. So the first test asserts the chain
    *survives* rather than asserting what it looks like.
    """

    def setUp(self):
        # The plan's own worked example, bar 1: one melody slot - a whole note - over
        # one chord, which the union turns into four steps. Chosen because it is the
        # case every rule here exists for: a held melody with a moving thumb.
        self.steps = walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])
        self.staff = format_tab_staff(self.steps, show_melody=True)

    def sounded(self, step: ArrangementStep) -> List[int]:
        """The string indices a renderer strikes, via the shared predicate.

        Deliberately the helper rather than the drawn cells: the ASCII staff and the
        HTML cell both call `_strikes_here`, so asserting on it states the rule once
        rather than twice - and `test_the_ascii_staff_draws_that` below is the half
        that checks the drawing actually follows it.
        """
        return [
            index for index in range(6)
            if _strikes_here(step, index) and step.voicing.frets[index] >= 0
        ]

    def test_a_walking_line_does_not_break_the_hold_chain(self):
        """
        The collapse regression, and the reason the fix is mandatory.

        The upper shape is struck once and held while the thumb walks, so only the
        first of the four steps may strike a string above the thumb. Comparing the
        full pitch set in `_staff_columns` would mark all four a strike.
        """
        self.assertEqual(len(self.steps), 4)
        above = [
            [index for index in self.sounded(step)
             if index != step.voicing.bass_string]
            for step in self.steps
        ]
        self.assertEqual(above[0], sorted(above[0]), "the first step is not a shell")
        self.assertGreater(len(above[0]), 1, "the first step strikes no upper voice")
        for index, struck in enumerate(above[1:], start=1):
            self.assertEqual(
                struck, [], f"step {index} re-struck the shape above the thumb"
            )

    def test_every_step_strikes_exactly_the_thumb_after_the_first(self):
        """
        The `bass_only` cell behaviour: the three slots the union invented draw **no**
        fret above the thumb, because the shape struck on beat 1 is still ringing.

        The opposite rule to `repeated`, which blanks the inner voices and keeps the
        soprano, so this is asserted as the *absence* of upper frets rather than as a
        particular one - which is also what catches a fill silently reverting to a
        duo.
        """
        for step in self.steps[1:]:
            self.assertTrue(step.bass_only)
            self.assertEqual(self.sounded(step), [bass_string(step)])

    def fretted_cells(self, row: str) -> List[str]:
        """The fret numbers drawn in one string row, one per non-empty cell.

        Read off the row's own fixed-width cells rather than by counting digits: a
        two-digit fret like `13` is two digits, and counting characters is how a test
        of this kind comes to disagree with the drawing for no musical reason. The
        cells are `width` characters wide and separated by a single `-`, which is what
        `format_tab_staff` writes between columns.
        """
        # Past the label, the melody marker and the opening barline.
        body = row[3:]
        cells, current = [], ""
        for char in body:
            if char == "-":
                if current:
                    cells.append(current)
                current = ""
            elif char != "|":
                current += char
        if current:
            cells.append(current)
        return [cell.strip() for cell in cells if cell.strip()]

    def test_the_ascii_staff_draws_one_strike_and_a_moving_thumb(self):
        """
        The drawing, read off the rendered staff rather than off the predicate.

        The melody's string carries exactly one fret in the whole bar - the collapse
        fix, in one number - and the thumb's carries one per column. Together those
        are the held shape and the walking line.
        """
        rows = [line for line in self.staff.splitlines() if _STRING_ROW.match(line)]
        self.assertEqual(len(rows), 6, f"could not read the string rows: {self.staff!r}")
        melody_row = rows[5 - self.steps[0].voicing.soprano_string()]
        self.assertEqual(
            self.fretted_cells(melody_row), ["13"],
            f"the held shape was re-struck: {melody_row!r}",
        )
        # The thumb **per column**, not on one row: it follows the hand, so it may sit
        # on a different string on beat 1 from the one it walks on. Reading a single
        # row would assert a fixed string, which is the one thing the placement rule
        # explicitly does not do.
        drawn = [
            self.fretted_cells(rows[5 - bass_string(step)])
            for step in self.steps
        ]
        for step, frets in zip(self.steps, drawn):
            self.assertTrue(
                frets, f"beat {step.beat} drew no thumb note: {rows[5 - bass_string(step)]!r}"
            )

    def test_the_thumb_reaches_every_walked_beat(self):
        """No walked beat is silent: each carries a placed thumb note."""
        for step in self.steps:
            self.assertIsNotNone(step.bass, "a walked beat has no bass")
            self.assertIsNotNone(step.voicing.bass_string)
            self.assertGreaterEqual(step.voicing.frets[bass_string(step)], 0)

    def test_the_thumb_may_change_string_between_beats(self):
        """
        The thumb follows the hand, so it is not pinned to one string, and the
        renderers read `bass_string` per step rather than assuming index 0.

        Not an assertion that a particular string is chosen - the placement rule is
        `test_walking_bass.py`'s to own - but that no renderer may assume it.
        """
        for step in self.steps:
            self.assertIn(step.voicing.bass_string, BASS_STRING_INDICES)

    def test_a_repeated_melody_still_strikes_the_thumb(self):
        """
        The one case where the two partial-attack rules meet.

        `repeated` holds the inner voices and `bass_only` holds everything above the
        thumb, so a step that is both must play the soprano **and** the bass and hold
        only what is between. Written as a hand-built step rather than an arrangement,
        because reaching it through the engine needs a melody that repeats under one
        harmony *and* a bass grid finer than the melody's - and the defect it guards
        against is in the renderers, not in how that state is produced.
        """
        voicing = make_voicing([8, 10, 9, 10, 10, 13], bass_midi=41, bass_string=0)
        step = ArrangementStep(
            chord="Fmaj7", melody="F5", voicing=voicing, repeated=True,
            bass=41, bass_role="connect",
        )
        self.assertEqual(
            [index for index in range(6) if _strikes_here(step, index)],
            [0, 5],
            "the thumb or the soprano went missing from a repeated+walking step",
        )
        # The same rule in the GP5 renderer's terms: the thumb is a moving voice, so a
        # repeated melody must not delete it.
        self.assertEqual(
            sorted(index for index, _fret in _sounding_frets(step)), [0, 5]
        )

    def test_the_annotation_names_the_bass_and_its_role(self):
        """
        The role is printed because the thumb is no longer uniformly chord tones, so a
        reader counting strings would wonder why the bass is not playing the chord.
        """
        rendered = format_progression(self.steps)
        self.assertIn("(bass: F3, anchor)", rendered)
        self.assertIn("(bass: E3, connect)", rendered)

    def test_the_bass_annotates_a_partial_shell_as_well_as_a_plain_one(self):
        """
        Every early return out of `_step_annotation` has to carry the bass.

        A walking step can equally be a partial shell, a melody-alone fill or a
        repeated melody, and a bass annotated on some of those and not the others is a
        worse defect than no annotation at all. The shell and its own `partial` text
        must both survive.
        """
        shell = self.steps[0]
        annotation = _step_annotation(shell)
        self.assertIn("partial", annotation)
        self.assertIn("(bass: F3, anchor)", annotation)

    def test_an_unchanged_texture_renders_identically(self):
        """
        The backward-compatibility claim of this phase, on the renderers themselves.

        Every change here is behind `step.bass`, `step.bass_only` or
        `voicing.bass_string`, so a step carrying none must render exactly as before -
        which is what keeps `uniform` and `targets` byte-identical.
        """
        from tests.test_texture import MINOR_CADENCE

        steps = VoiceLeadingEngine.arrange_progression(MINOR_CADENCE)
        rendered = format_progression(steps)
        self.assertEqual(rendered.splitlines()[0], "Dm7      D5   x-x-10-10-10-10")
        self.assertNotIn("(bass:", rendered)
        self.assertNotIn("bass:", format_tab_html(steps))

    """The documented degradation, asserted rather than left silent."""

    def test_without_a_beat_grid_the_walk_is_one_note_per_slot(self):
        """
        `timings=None` gives nothing to place four quarters on, so the texture degrades
        to one anchor per slot.

        This is the path every hand-written caller takes, which is exactly why it is
        worth a test: a silent degradation here would read as "the feature does
        nothing" rather than as a documented limit of the grid.
        """
        steps = walk([("F5", "maj7", "Fmaj7"), ("G4", "maj7", "Gmaj7")])
        self.assertEqual(len(steps), 2)
        self.assertEqual([step.bass_role for step in steps], ["anchor", "anchor"])
        self.assertEqual([names(step) for step in steps], ["F", "G"])

    def test_the_upper_voices_are_still_there_without_a_grid(self):
        """
        The degradation costs the walk, not the arrangement: with no timing every slot
        is a target, so each is a shell as it always would be.
        """
        steps = walk([("F5", "maj7", "Fmaj7")])
        self.assertEqual(steps[0].role, ROLE_TARGET)
        self.assertEqual(steps[0].voicing.grip, "shell")
        self.assertEqual(len(upper_pitches(steps[0])), 3)

