"""Where the walking bass is placed on the neck: reach, refusal, and the four-finger rule.

These are asserted on `place_bass` and on a step's fret vector rather than through a
progression wherever they can be, because they are about a fret distance and a sounding
order, and an arrangement only reaches them by accident. The `hand_fret` measurement the
pure pass in `test_bass.py` cannot make is made here, where an upper voicing exists - and
so is the one rule a generated grip cannot break but a merged step can: four fingers,
four frets.
"""

from __future__ import annotations

import unittest
from typing import List, Optional, Tuple

from musthe import Note

import arranger
from arranger import (
    BASS_ROLE_ANCHOR,
    BASS_STRING_INDICES,
    BASS_STYLE_ANCHORS,
    BASS_STYLE_WALK,
    GRIP_MAX_SPAN,
    PITCH_CLASS_NAMES,
    ROLE_FILL,
    ROLE_TARGET,
    STANDARD_TUNING,
    ArrangementStep,
    BassNote,
    ChordParser,
    VoiceLeadingEngine,
    Voicing,
    format_progression,
    supported_string_sets,
)

# The precedence rule `bass._melody_in_force` implements. Imported from where it
# lives rather than through the package facade, because these are private to
# `arranger.bass` and re-exporting them would put four internals into the public
# surface for the benefit of one test file. `test_bass.py` covers them directly for
# the same reason.
from arranger.bass import (
    place_bass,
)
from arranger.parts import PART_NAMES
from arranger.texture import texture_palette
from tabgp import _sounding_frets
from tests.support import (
    BUT_NOT_FOR_ME,
    arranged,
    bass_string,
    make_step,
    make_voicing,
    nearest_reach_for_note,
    pc,
    sweep_head_paths,
    upper_pitches,
    upper_shape,
    walk,
)


class TestTheThumbReachesTheHandHoldingTheShape(unittest.TestCase):
    """
    The between-step invariant `fret_span()` cannot see.

    Every per-step span in "the synthetic cut-time head" is at most 3, and the arrangement is still
    unplayable: one bar puts the hand at frets 6-8 and the next needs the D string at
    fret 1. Nothing spans seven frets; the *hand* does. A per-step number cannot catch
    that, so what is asserted here is a property of **consecutive** steps - the reach
    between where the thumb plays and where the fingers are holding.
    """

    def _arrangement(self):
        """The committed head that produced the defect, as a walking bass."""

        steps, _, _ = arranged(
            BUT_NOT_FOR_ME,
            texture="targets",
            bass=BASS_STYLE_WALK,
            grid="melody:every_note,bass:walk",
        )
        return steps

    def test_the_thumb_never_shares_a_string_with_a_finger(self):
        """
        One string cannot sound two frets at once.

        This is the collision behind the GP5 corruption: the
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

        A reach of more than 4 frets is allowed in exactly one case, and it is **asserted**
        rather than excused: the note the walk decided to play had no nearer position the
        filters allow, so the *register* is what makes the reach wide and the placement is
        not at fault. `tests.support.nearest_reach_for_note` asks that independently of the
        engine - a replica of the free-string, below-the-shape and four-fret filters - and
        the engine's own choice must equal it, so a placement that ignored a nearer position
        for the same note fails here by name of bar and beat.

        Measured over the committed heads the worst reach is 5 and the median 1, against
        the 7 the defect produced; `docs/open-issues.md` item 5 measures the case over
        every committed head, and §4.3's open question is the lever that would remove it.
        """
        steps = self._arrangement()
        held = None
        held_thumb = None
        reaches = []
        wide = []
        for step in steps:
            voicing = step.voicing
            if step.bass_only and held is not None and step.bass is not None:
                thumb_fret = voicing.frets[bass_string(step)]
                fingers = [fret for fret in held if fret >= 0]
                if fingers:
                    low, high = min(fingers), max(fingers)
                    reach = low - thumb_fret if thumb_fret <= low else thumb_fret - high
                    reaches.append(reach)
                    if reach > 4:
                        wide.append((
                            reach,
                            nearest_reach_for_note(held, held_thumb, step.bass),
                            abs(thumb_fret - min(fingers)),
                            step.bar,
                            step.beat,
                        ))
            if not step.bass_only and not step.repeated:
                held = list(voicing.frets)
                held_thumb = voicing.bass_string
        self.assertGreater(len(reaches), 0, "no thumb note was checked")
        for reach, nearest, chosen, bar, beat in wide:
            self.assertIsNotNone(
                nearest,
                f"bar {bar} beat {beat}: the thumb reaches {reach} frets from the held "
                "shape and its note had no position at all? the replica disagrees",
            )
            assert nearest is not None
            self.assertEqual(
                nearest,
                chosen,
                f"bar {bar} beat {beat}: the thumb reaches {reach} frets from the held shape "
                f"and sits {chosen} frets from the hand, while its own note had a position "
                f"{nearest} frets away",
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

    def test_no_anchor_is_left_without_its_thumb_note(self):
        """The set of anchors with no thumb note is the claim, and it has one member.

        Bar 3's downbeat is a *held* melody step whose own shell states the root C as
        its lowest voice, so the walk's root has no octave below the shape to take.
        The note is not missing from the line - it is already the bottom of the chord -
        and the annotation says so. Every other anchor carries its thumb; a new entry
        here means a change cost a note rather than moved one.

        The anchors are selected by `bass_role` alone, and deliberately **not** by
        `bass_only` as well. They used to be filtered by both, and that was wrong: a
        walk-invented downbeat the melody moves onto is a **target**, so it stopped
        being `bass_only` while remaining an anchor - and the filter quietly dropped it
        from this assertion, turning the test into one that could not fail. An anchor is
        an anchor whether or not the left hand holds across it.
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
            missing,
            [(3, 1.0)],
            "the set of anchors with no thumb note changed",
        )

    def test_every_anchor_carries_a_thumb_note_below_its_upper_shape(self):
        """Why the gap set above has one member, asserted over the **whole** population.

        A thumb note must sound strictly below the structure it supports, so an anchor
        can only fail to place when **the structure already sounds that pitch class**
        and every string below it is occupied. Bar 3 is exactly that: the held melody's
        shell states the root C as its lowest voice. It is allowed to fail *for that
        reason only*, asserted against the pitch it refused, and it is not a loop over
        nothing - every other anchor is checked here, so a future gap has to explain
        itself rather than being absorbed into a list.

        The chord's root is asserted too, because it is the pitch the thumb was reaching
        for and it is what the step has to state: `ChordParser` resolves the name rather
        than the test slicing characters out of it.
        """
        steps = self._arrangement()
        anchors = [step for step in steps if step.bass_role == arranger.BASS_ROLE_ANCHOR]
        self.assertGreater(len(anchors), 0, "no anchors were checked")
        for step in anchors:
            bass = step.bass
            sounding = {
                STANDARD_TUNING[index].midi_note() + fret
                for index, fret in enumerate(step.voicing.frets)
                if fret >= 0
            }
            self.assertTrue(sounding, f"bar {step.bar}: an anchor sounds nothing at all")
            if bass is None:
                # The one admissible refusal: the root the walk wanted is the lowest
                # voice the shape already sounds, so no thumb can be below it.
                self.assertEqual((step.bar, step.beat), (3, 1.0))
                self.assertEqual(
                    step.bass_refused,
                    PITCH_CLASS_NAMES[min(sounding) % 12],
                    f"bar {step.bar}: the refused bass is not the shape's lowest voice",
                )
                continue
            # The thumb is the bottom voice, so everything above it starts higher.
            upper = sorted(
                STANDARD_TUNING[index].midi_note() + fret
                for index, fret in enumerate(step.voicing.frets)
                if fret >= 0 and index != step.voicing.bass_string
            )
            self.assertTrue(upper, f"bar {step.bar}: the anchor states no upper voices")
            self.assertLess(
                bass,
                upper[0],
                f"bar {step.bar} beat {step.beat}: the thumb sounds {bass} and the upper "
                f"shape starts at {upper[0]}",
            )
            root_name = ChordParser.parse_chord_name(step.chord)[0]
            root = (
                None if root_name is None else Note(root_name + "4").midi_note() % 12
            )
            self.assertIsNotNone(root, f"bar {step.bar}: the chord name has no root")
            self.assertIn(
                root,
                {pitch % 12 for pitch in sounding},
                f"bar {step.bar} beat {step.beat}: the anchor note {root} is not "
                "already sounding, so the thumb had somewhere to play it",
            )


class TestABassOnlyStepIsNeverATarget(unittest.TestCase):
    """
    The invariant that a `bass_only` step is never a target.

    `bass_only` and `role == ROLE_TARGET` are not two descriptions of one state, they
    are contradictory ones: the first means "nothing above the thumb strikes, the
    upper voices are held from the last shape", the second means "a full chord
    states the harmony here". A walk-invented downbeat the melody moves onto is
    promoted to a target by `roles_for_slot`, so a slot could arrive carrying both,
    and the engine voiced a real `shell` or `melody` on it that every renderer then
    suppressed. The chord of the tune was in the arrangement and in none of the
    output.

    Asserted as a property of the flags rather than as a tab string, because the flag
    is what the four renderers read and the tab is four renderings of it.
    """

    def _walking_arrangement(self):
        """The committed head that produced the defect, as a walking bass."""

        steps, _, _ = arranged(
            BUT_NOT_FOR_ME,
            texture="targets",
            bass=BASS_STYLE_WALK,
            grid="melody:every_note,bass:walk",
        )
        return steps

    def test_no_step_is_both_bass_only_and_a_target(self):
        """
        The contradiction itself. Nine steps in "the synthetic cut-time head" carried both flags
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

        **The population moved when the default grid began generating positions of its
        own, and the movement is that change seen from here.** It was 14, and six of the
        fourteen sat on a bar's **first** beat where the tune was *silent* - `x-6-x-x-8-x`,
        the thumb alone with the upper voices held from the bar before. Those beats state a
        chord of their own now (`x-6-8-8-8-x`), so they are comps rather than fills, and the
        14 → 8 is the item-1 fix arriving from this direction rather than a loss. The eight
        that remain are held fills still, and each one still carries the note it is holding:
        that is the property, and it is asserted because the count has already moved once.
        """
        steps = self._walking_arrangement()
        fills = [step for step in steps if step.bass_only and step.role == ROLE_FILL]
        # The synthetic cut-time head is eight bars rather than thirty-two, so the
        # population is smaller than it was on the retired transcription. The
        # property below is the reason the count is here, and it holds for each.
        self.assertEqual(len(fills), 2, "the held fills changed")
        for step in fills:
            self.assertIsNotNone(
                step.melody,
                f"bar {step.bar} beat {step.beat}: a fill with no melody is not the tune "
                f"alone: {step.tab_line()}",
            )

    def test_every_target_states_its_chord_in_every_renderer(self):
        """
        What the flags are *for*: a target's upper voices reach the output.

        Checked against all four renderers rather than one, because they disagreed -
        `tabxml` showed the chord and the other three hid it - and agreement between
        them is the property that was actually broken.

        `repeated` is excluded alongside `melody_only`, and the two are excluded for
        the same reason: both mean *the left hand holds and only the soprano is
        re-struck*, so a step carrying either legitimately sounds one note in the
        tab. This is not a loophole opened for the item-5 fix - bar 3 beat 1.0 was
        already a `repeated` target before it, and asserting on it would have been
        asserting that the renderers ignore a documented flag.
        """
        import tabxml
        from arranger.render import _step_cells

        checked = 0
        for step in self._walking_arrangement():
            if step.role != ROLE_TARGET or step.melody_only or step.repeated:
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
    `place_bass`: the octave and the string, decided together against the hand.

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
        placed = place_bass(upper, pc("D"))
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
        placed = place_bass(upper, pc("E"))
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
            placed = place_bass(upper_shape(frets), pc("D"))
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
            placed = place_bass(upper_shape(frets), pc("D"))
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
        placed = place_bass(upper, pc("E"))
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
            placed = place_bass(upper_shape(frets), pc("D"))
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
        placed = place_bass(upper, pc("C"))
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
        self.assertIsNone(place_bass(upper, pc("D")))

    def test_a_hand_that_cannot_hold_the_thumb_refuses_the_note(self):
        """
        The other reason a note is refused, and it is the one `sounding_frets` cannot see.

        "Synthetic Tab Export" in the reported bar under `--texture targets --bass-style root`: the hand is holding
        `x-9-x-8-12-10`, and the walk's `B` has exactly one candidate - the low E at fret 7,
        because the A string is spoken for by the held shape and a `B` on the D at fret 9
        would sound above the shape's F#3. Fret 7 is a fret the hand is not on, so the shape
        would need five frets from four fingers. Before the budget this returned
        `(47, 0, 7)` and every renderer wrote it.
        """
        upper = upper_shape([-1, -1, -1, -1, -1, 10])
        self.assertIsNone(
            place_bass(upper, pc("B"), held=([-1, 9, -1, 8, 12, 10], None))
        )

    def test_one_fret_less_in_the_held_shape_and_the_same_thumb_is_placed(self):
        """
        The same note, the same string, the same fret - and a held shape one fret smaller.

        This is the pair that shows the *budget* is what decided the refusal and not the
        string: dropping the held shape's fret 12 leaves the hand on four frets, the low E at
        fret 7 is placed, and nothing else about the call changed.
        """
        upper = upper_shape([-1, -1, -1, -1, -1, 10])
        self.assertEqual(
            place_bass(upper, pc("B"), held=([-1, 9, -1, 8, -1, 10], None)),
            (47, 0, 7),
        )

    def test_the_fret_budget_outranks_proximity(self):
        """
        Playability beats comfort, which is the order `voicing_cost` already applies.

        The hand is on fret 5. `F#` is available on the A at fret 6 and the D at fret 4 -
        one fret of travel each - and on the low E at fret 2, three frets away. Both near
        candidates would put the hand on five frets, so both are refused and the far one is
        taken. The alternative would be the nearest *unplayable* placement, which is the
        defect rather than the fix.
        """
        upper = upper_shape([-1, -1, -1, -1, -1, 4])
        self.assertEqual(
            place_bass(upper, pc("F#"), held=([5, -1, -1, 7, 9, 11], 0)),
            (42, 0, 2),
        )

    def test_step_bass_is_one_fact_with_one_home(self):
        """
        `step.bass` is a derived view of `voicing.bass_midi`, not a second field.

        The two were written together in `attach_bass`, and a stored copy was
        another field that could disagree - the bug class `docs/history/one-fact.md`
        exists to remove. The proof is the assignment: a view that cannot be
        written cannot disagree with the fact it reads.
        """
        steps = walk(
            [("F5", "maj7", "Fmaj7"), ("A4", "7", "G7")],
            [(0, 1.0), (0, 2.0), (0, 3.0), (0, 4.0), (1, 1.0)],
        )
        self.assertTrue(any(step.bass is not None for step in steps))
        for step in steps:
            self.assertEqual(step.bass, step.voicing.bass_midi, step.tab_line())
        with self.assertRaises(AttributeError):
            steps[0].bass = 41  # type: ignore[assignment]

    def test_a_late_attach_bass_merge_is_visible_through_the_step(self):
        """
        The view follows the post-selection write rather than a copy.

        The thumb is merged into the voicing only after the upper shape has
        been chosen, so a copy taken at construction would report no bass
        forever. Writing the voicing's own field on a hand-built step and
        reading the step's is the proof that one is derived from the other.
        """
        voicing = make_voicing([-1, -1, 9, 9, 8, 8])
        step = ArrangementStep(chord="Cmaj7", melody="E5", voicing=voicing)
        self.assertIsNone(step.bass)
        voicing.bass_midi = 41
        self.assertEqual(step.bass, 41)


class TestTheRefusal(unittest.TestCase):
    """
    The three ways a thumb note is refused, and the one message that names them all.

    `place_bass` answers `None` for three different reasons, and the two *other* than
    the common one are already pinned beside it: every bass string taken
    (`test_no_candidate_means_no_bass_rather_than_a_wrong_one`) and a fifth fret for four
    fingers (`test_a_hand_that_cannot_hold_the_thumb_refuses_the_note`). What was missing
    is the case that fires almost every time - a free string exists, the note is playable,
    and there is simply **no octave of it below the shape's own lowest note** - and the
    warning text itself, which was asserted nowhere and named only the first and third of
    those causes. Measured over the committed heads: **0 / 38 / 1** of 39 refusals, so the
    clause that was missing is the one a reader actually meets
    (`docs/open-issues.md` item 2).
    """

    # Item 2's worked case: the shape's own `Ab2` (44) is the pitch class the walk wants,
    # and the only free string is the A, whose `Ab` above it is `Ab3` (56) - above the note
    # the thumb is meant to support, so the note is refused with a string to spare.
    NO_OCTAVE = ([4, -1, 4, 5, -1, -1], "Ab")

    def _refusal(self, step: ArrangementStep, name: str,
                 arrangements: Optional[List[ArrangementStep]] = None) -> Optional[str]:
        """What `attach_bass` records on the step when it cannot place one note.

        The refusal is `step.bass_refused` now rather than a warning, so this reads
        the field. Running `attach_bass` also proves the step *survives*, which is
        the other half of the trade: the upper voicing is kept.
        """
        VoiceLeadingEngine.attach_bass(
            step,
            BassNote(bar=1, beat=1.0, pitch_class=pc(name), role=BASS_ROLE_ANCHOR),
            arrangements if arrangements is not None else [step],
        )
        return step.bass_refused

    def test_the_commonest_refusal_is_the_pitch_having_no_octave_below_the_shape(self):
        """A free string, a playable pitch, and no octave of it beneath the shape."""
        frets, name = self.NO_OCTAVE
        self.assertIsNone(place_bass(upper_shape(frets), pc(name)))

    def test_the_line_names_all_three_causes_whichever_one_refused(self):
        """Every refusal says the same three things, so a reader is not left guessing.

        The clause is one string, so it cannot distinguish the causes - and that is the
        point: all three occur, so a line naming two of them says something false
        about the third. Each fixture here is refused for a different reason, one per
        cause, and all three must produce the same three clauses.

        Read off the rendered **line** rather than off `step.bass_refused`, because the
        field carries the wanted pitch class alone and the enumeration of causes is
        `annotation._bass_refusal_clause`'s. That split is deliberate: the tab cannot show
        which note went missing, so the field names it and the clause explains it.
        """
        held = make_step([-1, 9, -1, 8, 12, 10], chord="Bmaj7", melody="F#4")
        cases: List[Tuple[ArrangementStep, str, Optional[List[ArrangementStep]]]] = [
            # no octave of the wanted pitch below the shape
            (make_step(self.NO_OCTAVE[0], chord="Ab9", melody="C4"), self.NO_OCTAVE[1], None),
            # no free string: all three bass strings are already speaking
            (make_step([5, 5, 5, 5, 5, 5], chord="Cmaj7", melody="E5"), "D", None),
            # a fifth fret for four fingers, which needs the shape being *held*
            (make_step([-1, -1, -1, -1, -1, 10], chord="Bmaj7", melody="D#5",
                       bass_only=True), "B", [held]),
        ]
        for step, name, arrangements in cases:
            refused = self._refusal(step, name, arrangements)
            self.assertEqual(refused, name, step.tab_line())
            # `width=None` asks for the one-line form, which is what this asserts on: the
            # clause is longer than a line of the wrapped layout, and the question here is
            # what it *says*, not how it is laid out (`test_tab_rendering` holds that).
            line = format_progression([step], width=None)
            self.assertIn(f"bass {name}", line)
            self.assertIn("no free string below the melody", line)
            self.assertIn("no octave of that pitch below the shape", line)
            self.assertIn("the hand would need a fifth fret", line)
            self.assertIn("keeps its upper voicing", line)


class TestTheInvariant(unittest.TestCase):
    """
    The amended playability invariant for a step carrying a bass.

    *"The sounding strings are exactly one `supported_string_sets()` entry"*
    **cannot** hold once a thumb is merged: a 5-4-3 shell `(1,2,3)` becomes
    `{0,1,2,3}`, which is not a supported set. The rule is therefore stated over the
    **upper voices**, with the thumb required to sit outside them and below them -
    the same spirit as the melody-only `NC` exemption that already exists.

    **And the amendment has a second half, whose absence shipped a five-pluck tab.** The
    upper-voices rule above is satisfied by a *four*-string upper shape plus a thumb: two
    supported sets' worth of notes in one step, and one more string than the right hand
    has digits. Stating the rule over the upper voices was correct for the texture it was
    written for - a `walking_bass` target is a shell - and silently wrong for `targets`,
    whose targets were four-note drop-2s. Measured before the fix, over the six committed
    heads: `--texture targets --bass-style root,5th,approach,nearest` sounded five strings on **151** steps,
    `--bass-style root` on **130**, while `walking_bass` and `uniform` sounded none. The
    budget is now `grips.thumb_safe_grips`.
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

    def test_no_step_plucks_more_strings_than_the_right_hand_has_digits(self) -> None:
        """The budget half of the invariant, swept over the sweep heads.

        Four digits - thumb, index, middle and ring - so four strings, and a four-note
        target with a bass note merged under it is five. `_sounding_frets` is the
        renderers' own answer to "what does this step play at this instant", which is the
        right hand's question: a `bass_only` step plucks its thumb alone even though the
        shape above it is still ringing, and a `repeated` one plucks the soprano and the
        thumb. A check on the fret vector cannot tell those apart, which is how 281
        five-pluck steps shipped.

        `targets` is in the sweep because it *was* the defect. `uniform` is not, because
        its `walk` is refused outright (`bass_allowed`) and so has no thumb to budget.

        The arrangement itself comes from `tests.support.arranged`, so this test and the
        four-fret sweep below read the *same* arrangements rather than paying for the
        same twelve a second time. The heads are `tests.support.sweep_head_paths()`: the
        rule is about the right hand, and three metres answer it -
        [docs/history/fingering.md](../docs/history/fingering.md) §4.3 holds the reading.
        """
        paths = sweep_head_paths()
        checked = 0
        for path in paths:
            for texture, bass in (
                ("targets", BASS_STYLE_WALK),
                ("targets", BASS_STYLE_ANCHORS),
                ("chord2", BASS_STYLE_WALK),
                ("chord2", BASS_STYLE_ANCHORS),
            ):
                with self.subTest(head=path, texture=texture, bass=bass):
                    steps, _head, _notes = arranged(
                        path, texture=texture, bass=bass
                    )
                    for step in steps:
                        plucks = len(_sounding_frets(step))
                        self.assertLessEqual(
                            plucks,
                            4,
                            f"{texture}/{bass}: {step.tab_line()} plucks {plucks} strings",
                        )
                        if step.voicing.bass_string is not None:
                            checked += 1
        self.assertGreater(checked, 0, "no step carried a bass, so nothing was tested")

    def test_the_left_hand_never_needs_more_than_four_frets(self) -> None:
        """The **left-hand** half of the budget, swept over the sweep heads.

        The string budget above is the right hand's question; these are the other four digits.
        One finger holds one fret, so a step whose frets span five distinct positions is not a
        hard shape but an impossible one - and the only way a fifth appears in this engine is a
        `bass_only` step, where the thumb's fret joins a shape the hand is still holding. A
        generated grip cannot do it: every family sounds at most four strings, and
        `grips.thumb_safe_grips` already budgets the *strings* a target may add a thumb to.

        Two decisions about how the hand is counted, each of which moves the count by a lot:

        - it is the shape **still ringing**, not the step's own vector and not
          `_sounding_frets`. Under `bass_only` nothing above the thumb strikes at all, so a
          melody carried on a string the held shape does not use is a note the hand is not
          holding - it is already sounding elsewhere. Charging for its string counts **10**
          steps instead of 1, which is the item-4 mistake made backwards;
        - the previous thumb note **is** included: that string is still ringing, so it is
          still fretted. `bass.held_shape` drops it from `structure` for harmonic reasons,
          which is right for the three questions it answers - and on the committed heads the
          two readings give the same answer, so this one is chosen on the physics rather than
          on a count.

        Measured both ways, because a sweep that has only ever seen a clean tree proves
        nothing: **1** step violates this on the commit before the fix - "Synthetic Tab Export"
        in the reported bar under `targets`/`--bass-style root`, pinned also in
        `test_fingers.TestTheFourFretBudget` - and **0** after it.

        The arrangements are `tests.support.arranged`'s, shared with the string-budget
        sweep above: the two tests ask the same twelve questions.
        """
        paths = sweep_head_paths()
        checked = 0
        for path in paths:
            for texture, bass in (
                ("targets", BASS_STYLE_WALK),
                ("targets", BASS_STYLE_ANCHORS),
                ("chord2", BASS_STYLE_WALK),
                ("chord2", BASS_STYLE_ANCHORS),
            ):
                with self.subTest(head=path, texture=texture, bass=bass):
                    steps, _head, _notes = arranged(
                        path, texture=texture, bass=bass
                    )
                    held = None
                    for step in steps:
                        voicing = step.voicing
                        if step.bass_only and not step.melody_only and held is not None:
                            # The held shape with the thumb's own string replaced by the fret
                            # the walk placed there. One string sounds one fret, so the thumb
                            # overwrites rather than adding.
                            hand = list(held)
                            if voicing.bass_string is not None:
                                hand[voicing.bass_string] = voicing.frets[
                                    voicing.bass_string
                                ]
                            checked += 1
                        else:
                            hand = list(voicing.frets)
                        frets = {fret for fret in hand if fret >= 1}
                        self.assertLessEqual(
                            len(frets),
                            4,
                            f"{texture}/{bass}: bar {step.bar} beat {step.beat} "
                            f"{step.tab_line()} asks the left hand for {len(frets)} "
                            f"frets {sorted(frets)}",
                        )
                        if not (step.bass_only or step.repeated or step.melody_only):
                            held = list(voicing.frets)
        self.assertGreater(checked, 0, "no step held a shape, so nothing was tested")

    def test_the_bass_is_outside_the_cost_tuple_by_construction(self):
        """
        "Select first, merge after" is the structural answer to coupling.

        The upper shape of a walking step is the one `best_voicing` chose from a
        candidate list that never contained a thumb, so the cheapest way to assert the
        property is to show what that list is: exactly the palette the arity rule gave
        the slot - and not one candidate in it carries a bass note. The thumb is merged
        into the winning shape afterwards, which is why `missing = 4 - len(active)` is
        measured on the upper voices alone.
        """
        triple = [("F5", "maj7", "Fmaj7")]
        palette = texture_palette(ROLE_TARGET, "chord2", PART_NAMES)
        walking = VoiceLeadingEngine.prepare_step(triple, 0, grips=palette)
        assert walking is not None
        self.assertTrue(walking.candidates)
        for candidate in walking.candidates:
            self.assertIn(candidate.grip, palette)
            # And none of them carries a bass, so `missing = 4 - len(active)` is intact.
            self.assertIsNone(candidate.bass_midi)
            self.assertIsNone(candidate.bass_string)


class TestASingleNoteStepHasNothingToHold(unittest.TestCase):
    """
    `is_repeated_step` must not suppress a new shape's inner voices when the previous
    step played a single note.

    Found while fixing the melody-in-force rule, and **pre-existing** - verified by
    reproducing it on the commit before that fix. Bar 3 of "the synthetic cut-time head" under
    `walking_bass` put a melody-alone fill (bar 2 beat 2.5, `Eb4` alone) immediately
    before a `Cm7` target whose melody is the same still-sounding `Eb4`. The rule
    compared melody pitch and harmony, saw both unchanged, and marked the target
    `repeated` - which tells every renderer to strike the soprano and hold the rest.

    The engine had voiced `C3 Bb3 Eb4`, and the file contained `Eb4`. **The two notes
    that make it a chord rather than a melody note reached none of the four renderers.**
    A texture fill is the melody alone and carries `melody_only=False` on purpose, so
    the existing `melody_only` guard did not catch it; the test that mattered was on the
    flag rather than on what the step sounds.
    """

    def _steps(self):
        """
        The two steps, reduced from the fixture to the four notes that matter.

        Bar 2 beat 2.5 is the melody-alone fill and bar 3 beat 1.0 is the target; the
        same `Eb4` and the same `Cm7` on both sides, which is what fools the rule.
        """
        return VoiceLeadingEngine.arrange_progression(
            [
                ("G4", "maj", "Ebmaj"),   # bar 2 beat 1.0
                ("F4", "maj", "Ebmaj"),   # bar 2 beat 2.0
                ("Eb4", "m7", "Cm7"),     # bar 2 beat 2.5 - the melody-alone fill
                ("Eb4", "m7", "Cm7"),     # bar 3 beat 1.0 - the target that repeats it
                ("F4", "7", "Bb7"),
            ],
            timings=[(2, 1.0, 0.5), (2, 2.0, 0.25), (2, 2.5, 0.375), (3, 1.0, 0.375), (3, 1.5, 0.25)],
            texture="targets", bass=BASS_STYLE_WALK, grid="melody:every_note,bass:walk",
            beats_per_bar=2,
        )

    def test_a_repeat_is_not_claimed_when_the_previous_step_sounded_one_note(self):
        """
        The flag itself, and asserted as *not* set rather than as a chord name, because
        the flag is what the four renderers read.
        """
        steps = self._steps()
        target = [s for s in steps if s.bar == 3 and s.beat == 1.0][0]
        # The premise, asserted rather than assumed: the step before this one played a
        # single note, which is the whole reason the rule should not fire.
        fill = [s for s in steps if s.bar == 2 and s.beat == 2.5][0]
        self.assertEqual(
            [f for f in fill.voicing.frets if f >= 0],
            [4],
            "the premise changed: bar 2 beat 2.5 is no longer a single note",
        )
        self.assertFalse(
            target.repeated,
            "a step after a single-note step is not a re-strike of held voices",
        )

    def test_the_chord_under_that_melody_reaches_every_renderer(self):
        """
        The symptom: the two notes that make it a `Cm7` were dropped from the output.

        Checked against all four renderers, since "reached the output" is the property
        and any one of them passing would not be evidence. Before the fix this failed on
        all four with the same two notes missing.
        """
        import tabxml
        from arranger.render import _step_cells

        target = [s for s in self._steps() if s.bar == 3 and s.beat == 1.0][0]
        frets = target.voicing.frets
        sounding = {i for i, f in enumerate(frets) if f >= 0}
        self.assertGreaterEqual(len(sounding), 3, "the target is not voicing a chord")

        struck = {i for i, cell in enumerate(_step_cells(target)) if cell.isdigit()}
        self.assertEqual(
            sorted(struck),
            sorted(sounding),
            "the tab drops the inner voices of a chord under a held melody",
        )
        self.assertEqual(
            sorted(i for i, _fret in _sounding_frets(target)),
            sorted(sounding),
            "the GP5 drops the inner voices of a chord under a held melody",
        )
        self.assertEqual(
            len(tabxml._sounding(target)),
            len(sounding),
            "the score drops the inner voices of a chord under a held melody",
        )

    def test_the_committed_head_plays_the_root_below_the_held_melody(self):
        """
        The reported bar, in the committed head, and the octave.

        Bar 3 beat 1.0 states `Cm7` under a held `Eb4`. The root has to sound **below**
        the melody - on the low E at fret 8, `C3` against `Eb4` - or the bar claims a
        `Cm7` while voicing a bare `Eb`. Asserted on the pitch rather than the fret so
        the string is free to change if a better voicing appears.
        """

        steps, _head, _notes = arranged(
            BUT_NOT_FOR_ME,
            texture="targets",
            bass=BASS_STYLE_WALK,
            grid="melody:every_note,bass:walk",
        )
        target = [s for s in steps if s.bar == 3 and s.beat == 1.0][0]
        self.assertEqual(target.chord, "Cm7")
        pitches = target.voicing.midi_notes()
        # C3 root, Bb3 seventh, Eb4 melody - the pitches, not the frets, so the string
        # each lands on is free to change if a better voicing appears.
        self.assertIn(63, pitches, "the melody Eb4 does not sound there")
        self.assertIn(58, pitches, "the seventh Bb3 is missing")
        self.assertLess(
            min(pitches),
            63,
            "nothing sounds below the melody, so the Cm7 is voiced above it",
        )


class TestUpperVoicesExcludeTheThumbByStringNotPosition(unittest.TestCase):
    """`upper_midi_notes` must drop the thumb by **string**, never by list position.

    Both renderers read this to decide hold-versus-strike, and `step_annotation` reads
    it to name an interval or a duo, so getting it wrong is not cosmetic: it returns the
    wrong *notes*.

    This is a regression test for a real defect. The method used to `enumerate(...)` the
    sounding **pitches** and compare that counter - a position in the filtered list -
    against `bass_string`, which is a string index. The two coincide only when the thumb
    is the lowest-indexed active string, which for a low-E thumb under a shell they do:
    every existing walking-bass fixture put the thumb on the 6th string, so the suite was
    green over a method that returned the *thumb* and dropped the melody the moment the
    thumb moved to the 5th or 4th. The comment above the code said "filtered by string
    index, never by position in a filtered list" while doing the opposite.
    """

    def voicing(self, frets, bass_midi, bass_string):
        active = [f for f in frets if f >= 0]
        return Voicing(
            frets=frets,
            top_fret=max(active),
            avg_fret=sum(active) / len(active),
            grip="melody",
            bass_midi=bass_midi,
            bass_string=bass_string,
        )

    def test_a_thumb_on_the_a_string_keeps_the_melody(self):
        """The case the old code got backwards: melody on the high E, thumb on the A."""
        # A string fret 8 = F3, high E fret 8 = C5. The thumb is NOT the lowest-indexed
        # active string, so a positional filter keeps position 0 - the thumb - and drops
        # the melody at position 1.
        v = self.voicing([-1, 8, -1, -1, -1, 8], bass_midi=53, bass_string=1)
        self.assertEqual(sorted(v.midi_notes()), [53, 72])
        self.assertEqual(
            sorted(v.upper_midi_notes()),
            [72],
            "upper_midi_notes returned the thumb instead of the melody",
        )

    def test_every_thumb_string_gives_the_same_upper_voices(self):
        """The result must not depend on *which* string the thumb landed on.

        The same melody against a low-E, A-string and D-string thumb has to read the
        same, because `place_bass` picks the string per note by fret proximity.
        """
        cases = [
            (0, 40),   # low E, open
            (1, 45),   # A, open
            (2, 50),   # D, open
        ]
        for thumb_string, thumb_midi in cases:
            frets = [-1] * 6
            frets[thumb_string] = 0
            frets[5] = 8                       # C5 on the high E
            v = self.voicing(frets, bass_midi=thumb_midi, bass_string=thumb_string)
            self.assertEqual(
                sorted(v.upper_midi_notes()),
                [72],
                f"thumb on string {thumb_string} changed the upper voices",
            )

    def test_a_step_with_no_thumb_is_untouched(self):
        """No bass recorded means every note is an upper voice, which is the default."""
        v = self.voicing([-1, -1, -1, -1, -1, 8], bass_midi=None, bass_string=None)
        self.assertEqual(sorted(v.upper_midi_notes()), [72])

    def test_a_four_voice_shell_keeps_three_notes_over_any_thumb(self):
        """The walking-bass case the renderers actually depend on: shell plus thumb."""
        for thumb_string, thumb_midi in ((0, 40), (1, 45), (2, 50)):
            frets = [-1] * 6
            frets[thumb_string] = 0
            # G string fret 5 = C4, B string fret 5 = E4, high E fret 8 = C5.
            frets[3], frets[4], frets[5] = 5, 5, 8
            v = self.voicing(frets, bass_midi=thumb_midi, bass_string=thumb_string)
            self.assertEqual(
                sorted(v.upper_midi_notes()),
                [60, 64, 72],
                f"thumb on string {thumb_string} changed the shell",
            )
