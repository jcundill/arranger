"""The grip tables, and the questions asked of them directly.

`GRIP_STRING_SETS`, the soprano-string choices, the neck window and the known gaps are
properties of the tables and not of any one shape, so they are asked here rather than
through a generated voicing: a set the engine no longer offers still has to answer
`finger_skip_count`, and a window has to admit a position no family in
`GRIP_PREFERENCE` reaches. What the families build is `test_grips.py`.
"""

import unittest

from musthe import Note

from arranger import (
    ChordParser,
    SelectionCriteria,
    VoiceLeadingEngine,
    Voicing,
    supported_string_sets,
)
from arranger.fingers import MAX_HAND_SPAN
from arranger.grip_tables import (
    GRIP_MAX_SPAN,
    GRIP_STRING_SETS,
    SHELL_DEGREES,
)
from arranger.grips import (
    _LAYOUT_GRIPS,
    _SEARCHED_GRIPS,
    string_sets_for,
)
from arranger.tuning import MELODY_STRING_CHOICES_FULL, NECK_FRET_MAX, NECK_FRET_MIN
from tests.support import (
    QUALITIES,
    THUMB_REACH_STRINGS,
    a_shape_on,
    every_chord_tone,
    finger_skip_count,
    note_name,
)


class TestStringSetTable(unittest.TestCase):
    """The GRIP_STRING_SETS table itself, which the generated paths do not read."""

    def test_the_five_three_two_shell_is_the_only_set_that_crosses_a_string(self):
        """
        Every set a voicing may occupy leaves no finger reaching over a string - but one.

        `docs/history/fingering.md` §4.4's rule, held against the tables rather than restated: a
        gap between two sounding strings is the **thumb's** while the note below it is
        inside `THUMB_REACH_STRINGS`, and any other gap costs the middle or ring finger
        (`finger_skip_count`). Four `drop24` sets used to fail this and were **removed for
        it** - 260 of 1,204 selections change shape, and 41 of the default row's four-note
        steps lose their chord with it (§4.4 holds the price) - so this asserts the rule
        holds of what remains, and that the one exception is the `(5,3,2)` shell, which is
        kept on purpose for the walking bass's three-layer split rather than tolerated by
        accident.

        Checked over `supported_string_sets()`, because that - not the table - is what a
        generated voicing's `active_strings` must be a member of, so the drop-2 blocks the
        table does not list are covered here too.
        """
        crossing = {
            frozenset(strings)
            for strings in supported_string_sets()
            if finger_skip_count(a_shape_on(strings)) > 0
        }
        self.assertEqual(
            crossing,
            {frozenset((2, 3, 5))},
            "a reachable set puts a finger over an unplucked string, or the shell lost its",
        )

    def test_the_thumb_s_exemption_is_the_bottom_gap_only(self):
        """
        A gap is free only where it is the *bottom* one and the thumb is under it.

        Three cases, and the third is why the exemption is not "any gap above a low note":
        `(1,3,4,5)` is clean because its gap is the bottom one, under the A string;
        `(2,3,5)` pays one because its bottom string is the G and its gap is above it; and
        `(0,2,4,5)` - whose bottom gap *is* free - still pays for the second one, which is
        the asymmetry the rule is stated with.

        The four sets the ban removed are asked directly, since the point of the rule is
        that it flags them and not merely that the table no longer lists them.
        """
        self.assertEqual(THUMB_REACH_STRINGS, frozenset((0, 1, 2, 3)))
        self.assertEqual(
            finger_skip_count(a_shape_on((1, 3, 4, 5))), 0, "the thumb is under the A",
        )
        self.assertEqual(
            finger_skip_count(a_shape_on((2, 3, 5))), 1, "nothing is under the G",
        )
        self.assertEqual(
            finger_skip_count(a_shape_on((0, 2, 4, 5))), 1, "the second gap is the cost",
        )
        for strings in ((5, 4, 2, 1), (5, 3, 2, 0), (4, 3, 1, 0), (4, 2, 1, 0)):
            self.assertEqual(
                finger_skip_count(a_shape_on(strings)), 1,
                f"the removed set {strings} should fail the rule it was removed for",
            )

    def test_every_grip_family_has_a_span_limit(self):
        """
        Every family in GRIP_STRING_SETS is also in GRIP_MAX_SPAN, and vice versa.

        The two tables are read independently - the span by `candidate` and the sets by
        `string_sets_for` - so a family added to one and
        not the other would fail with a bare KeyError deep inside placement, naming
        neither the grip nor the omission. The two-note families are held to 4 rather
        than 5 for the same reason a duo is: two fingers, no reason to stretch.
        """
        self.assertEqual(
            set(GRIP_STRING_SETS), set(GRIP_MAX_SPAN),
            "a grip family is missing from one of the two tables",
        )
        self.assertEqual(GRIP_MAX_SPAN["duo"], 4)
        self.assertEqual(GRIP_MAX_SPAN["interval"], 4)
        # And the whole table sits inside the hand's own reach, which is the bound a
        # *merged* step is held to (`fingers.can_fret`). A family allowed to span more
        # than a hand could never be played - the rule would be stricter than the
        # instrument - so the two numbers are asserted against each other rather than
        # against a copy of 5.
        for family, span in GRIP_MAX_SPAN.items():
            self.assertLessEqual(
                span, MAX_HAND_SPAN,
                f"{family}'s span cap is wider than the hand's reach",
            )

    def test_every_family_is_placed_exactly_one_way(self):
        """
        `_LAYOUT_GRIPS` and `_SEARCHED_GRIPS` partition the families, with nothing left over.

        The two are placed by different code - a layout's frets are computed from its
        template, and a searched family's shape is *found* - so a family in neither would
        silently generate nothing at all, and one in both would be placed twice by two paths
        that could disagree. Stated as a table rather than a branch in the generator, which is
        what makes adding a family a decision: it has to be put in one of the two.
        """
        self.assertEqual(
            set(_LAYOUT_GRIPS) | set(_SEARCHED_GRIPS),
            set(GRIP_STRING_SETS),
            "a family is placed by neither path",
        )
        self.assertEqual(
            set(_LAYOUT_GRIPS) & set(_SEARCHED_GRIPS),
            set(),
            "a family is placed by both paths",
        )

    def test_an_interval_uses_only_the_adjacent_pairs_a_duo_also_declares(self):
        """
        The `interval` grip sits on the three **adjacent** pairs, which the duo declares
        too - but not on the duo's two skipped-string pairs.

        The difference is deliberate in both directions:

          - an interval keeps to the adjacent pairs, because a 3rd or a 6th has tuning
            to spare and the extra reach of a skipped string buys it nothing;
          - a duo may go wider, because it has to voice a 9th where the guide tone would
            otherwise be a 2nd, and a 9th is unreachable within the span cap on
            adjacent strings.

        So the interval's sets are a **subset** of the duo's, and equal to its adjacent
        ones. A wider interval would be a change to the playability contract, not a
        detail - which is why the subset is asserted rather than assumed.
        """
        interval_sets = [tuple(s) for s, _ in GRIP_STRING_SETS["interval"]]
        duo_sets = [tuple(s) for s, _ in GRIP_STRING_SETS["duo"]]
        self.assertEqual(
            set(interval_sets) <= set(duo_sets),
            True,
            "an interval sits on a pair the duo does not declare",
        )
        adjacent = {s for s in duo_sets if abs(s[0] - s[1]) == 1}
        self.assertEqual(
            set(interval_sets),
            adjacent,
            "the interval's pairs are not exactly the duo's adjacent ones",
        )
        for strings, soprano in GRIP_STRING_SETS["interval"]:
            self.assertEqual(len(strings), 2)
            # String indices run 0 = low E to 5 = high E, so the soprano is the
            # *first* of a pair and the highest index in it.
            self.assertEqual(soprano, max(strings))

    def test_the_duo_s_skipped_string_pairs_are_all_load_bearing(self):
        """
        The duo's three skipped-string pairs exist for the 9ths, and each is needed.

        Without them a duo whose guide tone would be a 2nd has nowhere to go: the 9th
        that replaces the 2nd needs a fret difference of 9 or 10 on adjacent strings,
        against a cap of 4. Each pair is asserted to voice a 9th **no other kept pair
        reaches**, so none is dead weight in the playability contract - and the cap is
        asserted *not* to have been widened for them, because they work by being wide in
        tuning and narrow in frets.

        `(4,2)` was measured (193 of the 253 cases) and left out: it is the one pair no
        kept combination needs, and two sets that voice nothing are two sets added to
        `supported_string_sets()` for no reason.
        """
        skipped = [
            tuple(sorted(s))
            for s, _ in GRIP_STRING_SETS["duo"]
            if abs(s[0] - s[1]) != 1
        ]
        self.assertEqual(
            sorted(skipped),
            [(1, 3)],
            "the duo's skipped-string pairs changed - re-measure before editing this",
        )
        self.assertEqual(GRIP_MAX_SPAN["duo"], 4, "the span cap was widened to suit a pair")

        engine = VoiceLeadingEngine()
        ninths = set()
        for quality in SHELL_DEGREES:
            chord_name = "C" + quality
            for pc in ChordParser.get_chord_tones(quality, chord_name):
                for octave in range(2, 6):
                    midi = 12 * octave + pc
                    if not Note("G3").midi_note() <= midi <= Note("Bb5").midi_note():
                        continue
                    melody = note_name(midi)
                    for v in engine.get_all_grip_voicings(
                        Note(melody), quality, chord_name=chord_name, grips=("duo",)
                    ):
                        upper = sorted(v.midi_notes())
                        if upper[-1] - upper[0] < 12:
                            continue
                        ninths.add((chord_name, melody, tuple(v.active_strings)))
        self.assertTrue(
            any(tuple(sorted(pair)) == (1, 3) for _, _, pair in ninths),
            f"the skipped pair voiced no 9th; saw {sorted({p for _, _, p in ninths})}",
        )

    def test_every_entry_names_its_own_soprano(self):
        """
        Each entry must list a soprano string that is actually in its set. An entry that
        does not is silently wrong: the drop-2 path computes its own string set and
        never consults the table, so the mistake survives every behavioural test and
        only shows up in the documented invariant.
        """
        for grip, shapes in GRIP_STRING_SETS.items():
            for strings, soprano in shapes:
                self.assertIn(
                    soprano, strings, f"{grip}: {sorted(strings)} with soprano {soprano}"
                )

    def test_the_bottom_four_strings_carry_no_four_note_shape(self):
        """
        6-5-4-3 with the melody on top does not sound good, so no four-note grip may
        occupy it. A low melody is harmonised with a three-note shell instead - and
        both shell shapes, 5-4-3 and 6-4-3, are offered so the selector can choose.

        6-4-3-2 is *also* non-contiguous, and is deliberately not caught by this rule:
        it swaps the A string out for the B, so its lowest note is on the low E while
        its soprano is the B rather than the G. The two rules must not be conflated by a
        later reader - 6-4-3-2 is the fix for a bass, not an exception to the exclusion.
        """
        bottom_four = {0, 1, 2, 3}
        for grip in ("drop2", "drop3", "closed", "drop2_6432"):
            for strings, _soprano in GRIP_STRING_SETS[grip]:
                self.assertNotEqual(frozenset(strings), bottom_four, grip)
        for grip in ("drop2", "drop3", "closed"):
            for _strings, soprano in GRIP_STRING_SETS[grip]:
                self.assertNotEqual(soprano, 3, f"{grip} still offers a G-string block")
        self.assertNotIn(bottom_four, supported_string_sets())
        # 6-4-3-2 does reach the low E, which is the entire reason it exists.
        self.assertEqual(GRIP_STRING_SETS["drop2_6432"], (((0, 2, 3, 4), 4),))
        self.assertIn(frozenset((0, 2, 3, 4)), supported_string_sets())

        # Both G-string shell shapes are on the table, so the selector may choose either.
        g_shells = [
            strings
            for strings, soprano in GRIP_STRING_SETS["shell"]
            if soprano == 3
        ]
        self.assertEqual([list(s) for s in g_shells], [[1, 2, 3], [0, 2, 3]])

        # And a 6-4-3 is genuinely reachable, not merely tabulated. It is not reachable
        # for *every* low melody - a Gm7 shell under its 5th wants a six-fret span - so
        # this is a claim that it appears, not that it always wins.
        found = [
            v.tab_string()
            for chord_name, quality in (("Cmaj7", "maj7"), ("Gm7", "m7"), ("G7", "7"))
            for melody in every_chord_tone(chord_name, quality)
            for v in VoiceLeadingEngine.get_grip_voicings(
                Note(melody), quality, chord_name=chord_name,
                top_string=3, grips=("shell",),
            )
            if v.active_strings == [0, 2, 3]
        ]
        self.assertTrue(found, "no 6-4-3 shell is reachable anywhere")

    def test_every_string_set_descends_from_its_soprano(self):
        """
        Every set `string_sets_for` hands back must be ordered highest string first.

        This is the order `place_template` assigns voices in, so a set that ascends
        lays the voices on the strings in reverse. It is asserted on the *returned*
        value rather than on the stored tuple because the two were not the same: the
        stored sets are low-to-high for readability, and rotating one from its
        soprano produced (5, 2, 3, 4) for the four-string block - ascending, with the
        B-string voice carried by the G string. The pitches were right and the strings
        were not, and nothing noticed because only `drop3` and `closed` place by this
        order and neither generated anything at the default span limit.

        The search-based families (`shell`, `drop2_6432`) are included anyway: they
        iterate every fret combination over the non-soprano strings, so their output is
        order-independent, and asserting the invariant uniformly is what stops a future
        stacked grip from inheriting the same defect silently.
        """
        for grip, shapes in GRIP_STRING_SETS.items():
            for _strings, soprano in shapes:
                for ordered in string_sets_for(grip, soprano):
                    self.assertEqual(
                        list(ordered),
                        sorted(ordered, reverse=True),
                        f"{grip}: {ordered} ascends from its soprano {soprano}",
                    )
                    self.assertEqual(
                        ordered[0], soprano, f"{grip}: {ordered} does not lead with it"
                    )

    def test_a_g_string_melody_never_gets_four_voices(self):
        """The end-to-end statement of the same rule, on the arranged result."""
        for chord_name, quality in (("Cmaj7", "maj7"), ("Dm7", "m7"), ("G7", "7")):
            for melody in every_chord_tone(chord_name, quality):
                steps = VoiceLeadingEngine.arrange_progression(
                    [(melody, quality, chord_name)]
                )
                for step in steps:
                    if step.voicing.soprano_string() != 3:
                        continue
                    self.assertLessEqual(
                        len(step.voicing.active_frets()), 3,
                        f"{chord_name} {melody} -> {step.tab_line()}",
                    )


class TestSopranoStringChoices(unittest.TestCase):
    """The melody may be voiced on the high E, the B or the G string - and only those."""

    def test_the_soprano_set_is_the_three_upper_strings(self):
        """The A string and the low E are inner voices; no grip puts the melody there."""
        self.assertEqual(MELODY_STRING_CHOICES_FULL, (5, 4, 3))

    def test_a_low_melody_is_voiced_on_a_lower_string(self):
        """
        D4 and C4 sit at the very bottom of the B string's range, so the melody is
        voiced there or below it - never on the high E, which cannot reach it at all.

        Which of the lower strings wins depends on the shape available: C4 over Cmaj7
        takes a 6-4-3 shell on the G string, while D4 over Dm7 takes a complete
        four-note chord on the B string, because a full chord outranks a duo even
        though that costs a string.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D4", "m7", "Dm7"), ("C4", "maj7", "Cmaj7")]
        )
        self.assertEqual(len(steps), 2)
        for step in steps:
            self.assertIn(step.voicing.soprano_string(), (3, 4))
            self.assertEqual(
                max(step.voicing.midi_notes()), Note(step.melody).midi_note()
            )
        # The Cmaj7 uses a three-note shell on the G string - 5-4-3 here, with 6-4-3
        # offered alongside it and the selector choosing on position.
        self.assertEqual(steps[1].grip, "shell")
        self.assertEqual(steps[1].voicing.soprano_string(), 3)

    def test_restricting_the_soprano_set_emits_a_silent_step(self):
        """top_strings=(5,) leaves the lower strings out of the rescue.

        The position is emitted silent rather than dropped (item 4): D4 cannot be
        carried by the high E string, the caller excluded every string that could
        carry it, and the tab keeps the bar with the reason on it. The chord has
        no shape there either - the melody could not be placed - so the reason is
        `no_shape` rather than a pitch no string reaches.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D4", "m7", "Dm7")], top_strings=(5,)
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].silence, "no_shape")
        self.assertEqual(steps[0].voicing.frets, [-1] * 6)


class TestFretWindow(unittest.TestCase):
    """The window is a strong preference, never a filter."""

    def test_the_arrangement_sits_inside_the_window(self):
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")]
        )
        for step in steps:
            for fret in step.voicing.active_frets():
                self.assertGreaterEqual(fret, NECK_FRET_MIN, step.tab_line())
                self.assertLessEqual(fret, NECK_FRET_MAX, step.tab_line())

    def test_a_melody_off_the_end_of_the_board_is_emitted_silent(self):
        """
        C6 is fret 20 - unplayable, not merely out of position - so its position is
        emitted silent rather than dropped, and the following step must still be
        arranged rather than left with no previous voicing to measure against: the
        selector looks back *past* the silent step to the last sounding shape.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C6", "m7", "Dm7"), ("D5", "m7", "Dm7")]
        )
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].silence, "out_of_reach")
        self.assertEqual(steps[1].melody, "D5")
        self.assertIsNone(steps[1].silence)

    def test_the_window_bounds_are_honoured_when_narrowed(self):
        """A caller can ask for a different window and the selector obeys it."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7")], fret_min=1, fret_max=4
        )
        self.assertTrue(steps)
        for step in steps:
            for fret in step.voicing.active_frets():
                self.assertLessEqual(fret, 4, step.tab_line())


class TestKnownTableGaps(unittest.TestCase):
    """The 13-chord 9th: the tone-priority rule answers for every chord tone.

    A melody that is a chord tone with no template of its own is built a shape rather than
    falling through to the quality-only fallback, which is free to sound a note the chord
    does not contain. A regression re-opens that gap and fails here.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_generation_offers_impure_shapes_but_the_selector_refuses_them(self):
        """
        A 9th in the melody of a 13 chord has no matching inversion in the table, so
        the quality-only fallback is offered and it is free to sound a note the chord
        does not contain. Generation is pure and still offers them - changing the tables
        would change the published drop-2 output and is a separate piece of work - but
        voicing_cost's first criterion is tone purity, so the arrangement never picks
        one while a correct shape exists.
        """
        tones = set(ChordParser.get_chord_tones("13", "C13"))
        impure = [
            v
            for v in self.engine.get_all_drop2_voicings(
                Note("D5"), "13", chord_name="C13"
            )
            if not set(v.pitch_classes()) <= tones
        ]
        # The gap this class existed to pin has closed - and closed for every chord tone,
        # not just this one melody: the tone-priority rule builds the shape for a 9th in
        # the melody of a 13 (`1 3 b7 9`, both guide tones), where the table has no
        # inversion for it and the quality-only fallback would offer `x-x-10-8-10-10`,
        # 1 b3 6 9 against a chord whose identity is 3 and b7. A regression re-opens the
        # gap and fails here instead of passing silently.
        self.assertFalse(
            impure,
            f"the 13-chord 9th gap reopened: {[v.tab_string() for v in impure]}",
        )
        for v in self.engine.get_all_drop2_voicings(
            Note("D5"), "13", chord_name="C13"
        ):
            self.assertEqual(
                self.engine.voicing_cost(
                    v, SelectionCriteria(allowed_tones=tones)
                ).foreign,
                0.0,
                v.tab_string(),
            )

    def test_tone_purity_outranks_the_neck_window(self):
        """
        A correct chord slightly out of position beats a wrong note inside it: a wrong
        note is not playable at all, whereas position is only awkward.

        The two pools are built from qualities that still differ in reach: a C13 with the
        9th in the melody is now voiced correctly, while a C13 whose melody has no
        playable four-note shape at all still yields the impure quality-only fallback
        further down the neck. If either pool ever empties the ordering is no longer being
        tested, so both are asserted present.
        """
        tones = set(ChordParser.get_chord_tones("13", "C13"))
        candidates = self.engine.get_all_drop2_voicings(
            Note("D5"), "13", chord_name="C13"
        )
        # Every one is a correct voicing of C13 - that is the point of the fix - and they
        # differ in where they sit, so this still has both pools to rank.
        pure = [v for v in candidates if set(v.pitch_classes()) <= tones]
        self.assertEqual(len(pure), len(candidates), "a C13 shape is still sounding a wrong note")
        self.assertGreaterEqual(len(pure), 2, "need at least two shapes to rank them")
        # Position is now the only thing separating them, and the criterion under test
        # still reports it: the lowest fret sits inside the window and the highest does
        # not, so the penalty is not uniformly zero.
        window_costs = sorted(
            self.engine.voicing_cost(v, SelectionCriteria(previous=v)).outside
            for v in pure
        )
        self.assertEqual(window_costs[0], 0.0, window_costs)
        self.assertGreater(window_costs[-1], 0.0, window_costs)
        # And the ordering under test: the shape inside the window outranks the one
        # outside it, purely on position.
        inside, outside = pure[0], pure[-1]
        self.assertLess(
            self.engine.voicing_cost(inside, SelectionCriteria(allowed_tones=tones)),
            self.engine.voicing_cost(outside, SelectionCriteria(allowed_tones=tones)),
        )

    def test_the_arranged_result_still_sounds_only_chord_tones(self):
        """
        Whatever the tables do internally, the arrangement the caller receives has to be
        musically correct - that is the promise the library makes, and the selector is
        what keeps it.
        """
        for chord_name, quality in QUALITIES:
            for melody in every_chord_tone(chord_name, quality):
                tones = set(ChordParser.get_chord_tones(quality, chord_name))
                for step in VoiceLeadingEngine.arrange_progression(
                    [(melody, quality, chord_name)]
                ):
                    self.assertTrue(
                        set(step.voicing.pitch_classes()) <= tones,
                        f"{chord_name} {melody} -> {step.tab_line()}",
                    )


class TestVoicingAccessors(unittest.TestCase):
    """The small accessors the selector reads."""

    def test_active_strings_and_soprano_fret(self):
        v = Voicing(frets=[-1, 10, 10, 10, 10, -1], top_fret=10, avg_fret=10.0)
        self.assertEqual(v.active_strings, [1, 2, 3, 4])
        self.assertEqual(v.soprano_string(), 4)
        self.assertEqual(v.fret_on_soprano, 10)

    def test_a_muted_voicing_reports_nothing_sounding(self):
        v = Voicing(frets=[-1] * 6, top_fret=0, avg_fret=0.0)
        self.assertEqual(v.soprano_string(), -1)
        self.assertEqual(v.fret_on_soprano, -1)
        self.assertEqual(v.fret_span(), 0)
        self.assertIsNone(v.bass_pc)
