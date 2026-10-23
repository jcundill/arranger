"""What the selector prefers: position continuity, determinism, and the cost score.

`voicing_cost`'s seven fields are named, and their *order* is asserted once, by
`test_the_field_order_is_the_rule`, because that order is the library's central
invariant - moving the code is safe, reordering it is a musical decision. Every other
assertion reads a field by name. The criteria are read through the shape the selector
keeps wherever a choice can show them, and on the score itself where it cannot.
"""

import unittest
from dataclasses import replace

from musthe import Note

from arranger import ChordParser, SelectionCriteria, VoiceLeadingEngine, Voicing, VoicingScore
from arranger.cost import (
    PARTITION_CRITERION,
    SPAN_CRITERION,
    VOICING_COST_CRITERIA,
)
from arranger.grip_tables import GRIP_PREFERENCE
from arranger.grips import BASS_DEGREES_6432
from tests.support import (
    QUALITIES,
    every_chord_tone,
    root_midi_of,
)


class TestPositionContinuity(unittest.TestCase):
    """The selector's first job is to keep the hand where it already was."""

    def test_no_large_jump_between_consecutive_chords(self):
        """
        The hand should not travel far between consecutive chords.

        The bound is 4 rather than 3. Both voicings in the worst pair are correct -
        a drop-3 G7 at `13-x-12-12-12-x` followed by a drop-2 Cmaj7 at `x-x-9-9-8-8` -
        and the gap is not a mis-picked shape: C5 under Cmaj7 has no four-note voicing
        above fret 12 at all, the closest being a drop-3 at average 9.8, so the hand
        has to come back down the neck whatever it does. What changed is which G7 it
        came from: with `drop3` now in the palette and criterion 0 counting wrong notes
        instead of flagging them, a clean span-1 shape at fret 12 outranks a
        span-2 drop-2 at fret 5, because span (index 3) outranks position (index 4) by
        design. The tighter grip was chosen; the travel is a consequence.

        Measured worst jump over this progression: 2.5 before, 3.75 now.
        """
        progression = [
            ("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7"),
            ("E5", "m7", "Am7"), ("D5", "7", "G7"), ("C5", "maj7", "Cmaj7"),
        ]
        steps = VoiceLeadingEngine.arrange_progression(progression)
        self.assertEqual(len(steps), len(progression))
        for previous, step in zip(steps, steps[1:]):
            jump = abs(step.voicing.avg_fret - previous.voicing.avg_fret)
            self.assertLessEqual(
                jump, 4.0, f"{previous.tab_line()} -> {step.tab_line()}"
            )

    def test_a_repeated_melody_keeps_its_fret(self):
        """A melody that repeats keeps its place rather than sliding down the neck."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("D5", "7", "G7"), ("D5", "m7b5", "Dm7b5")]
        )
        frets = [s.voicing.fret_on_soprano for s in steps]
        self.assertLessEqual(max(frets) - min(frets), 5, frets)

    def test_the_soprano_may_change_string_to_hold_its_position(self):
        """
        The point of the extra soprano string: a melodic position can be held by moving
        to a different string, which is a far smaller gesture than moving the hand, and
        it is a legitimate answer to a melody the high E cannot reach.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("A4", "m7", "Dm7"), ("A4", "7", "G7"), ("A4", "maj7", "Cmaj7")]
        )
        self.assertTrue(steps)
        for step in steps:
            self.assertEqual(max(step.voicing.midi_notes()), Note("A4").midi_note())


class TestSelectionDeterminism(unittest.TestCase):
    """The engine is pure, so its output is worth asserting on."""

    def test_the_same_progression_arranges_identically_twice(self):
        progression = [
            ("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7"),
        ]
        first = VoiceLeadingEngine.arrange_progression(progression)
        second = VoiceLeadingEngine.arrange_progression(progression)
        self.assertEqual([s.tab_line() for s in first], [s.tab_line() for s in second])

    def test_the_family_is_the_engines_search_space(self):
        """The family is the engine's search space, so there is nothing to pin.

        A caller chooses the *arity* (`chord_notes`) and the parts, and `TONE_PRIORITY` plus
        the neck window decide which family states those notes - so naming a family is
        naming the search space (`docs/history/parts.md` §4). The arrangement here is
        therefore the engine's own - and where it disagrees with the old pinned tabs it
        is because the wider palette found a **purer** shape: `G7` under B4 on the high
        E string is `x-8-x-7-8-7` (root, 3rd, 5th, b7) rather than `x-x-5-7-6-7`, which
        sounds an F# the chord does not contain.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
        )
        self.assertEqual(
            [s.tab_line() for s in steps],
            ["x-x-10-10-10-10", "x-8-x-7-8-7", "x-x-9-9-8-8"],
        )
        # Every one of them is four strings with the melody on top, which is what the
        # pinned `grips=("drop2",)` arrangement was chosen to show.
        self.assertTrue(all(len(s.voicing.active_frets()) == 4 for s in steps))


class TestVoicingCost(unittest.TestCase):
    """The selection rule itself, asserted rather than only through its results."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_the_field_order_is_the_rule(self):
        """The one positional assertion, and the reason the others can read names.

        The score is a tuple, so comparison is lexicographic and this order *is* the
        rule: correctness first, then the two comfort criteria (window, completeness),
        then span above position, then movement, then the bass tie-break. A field may
        be added; moving one is a musical decision with a measurement behind it, and
        `docs/engine.md` holds that measurement.

        The labels and the two derived indices are read from these fields, so this
        also holds the printable phrases to the score they describe: a field whose
        phrase is missing raises at import, and a phrase in the wrong place fails
        here.
        """
        self.assertEqual(
            VoicingScore._fields,
            ("foreign", "outside", "missing", "span", "position", "movement", "bass"),
        )
        self.assertEqual(
            VOICING_COST_CRITERIA,
            (
                "sounds a note outside the chord",
                "lies outside the neck window",
                "leaves a voice out",
                "needs a wider stretch",
                "sits further up the neck",
                "moves the inner voices more",
                "sounds a weaker bass",
                "does not sound the written bass",
            ),
        )
        self.assertEqual(SPAN_CRITERION, 3)
        self.assertEqual(PARTITION_CRITERION, len(VoicingScore._fields))

    def test_the_score_is_still_a_tuple(self):
        """A named score must stay comparable, because `min` is what picks a shape.

        The names are for the reader. `best_voicing_for` ranks with `<` on these
        values, and `decisive_criterion` zips them, so a score that stopped being a
        tuple would change the selection rather than the spelling.
        """
        v = self.engine.get_drop2_voicings(Note("C5"), "maj7", chord_name="Cmaj7")[0]
        score = self.engine.voicing_cost(v, SelectionCriteria(previous=v))
        self.assertIsInstance(score, tuple)
        self.assertEqual(tuple(score), tuple(score._asdict().values()))
        self.assertLessEqual(score, score)

    def test_a_voicing_inside_the_window_pays_no_window_penalty(self):
        v = self.engine.get_drop2_voicings(Note("C5"), "maj7", chord_name="Cmaj7")[0]
        self.assertEqual(
            self.engine.voicing_cost(v, SelectionCriteria(previous=v)).outside, 0.0
        )

    def test_a_voicing_outside_the_window_is_penalised(self):
        """F5 sits at fret 13 on the high E (inside the window) but at fret 18 on the B
        string, which is not. A candidate that far out has to be marked as such."""
        candidates = self.engine.get_drop2_voicings(
            Note("F5"), "maj7", chord_name="Cmaj7", top_string=4
        )
        self.assertTrue(candidates)
        costs = [
            self.engine.voicing_cost(v, SelectionCriteria(previous=v)).outside
            for v in candidates
        ]
        self.assertTrue(any(c > 0 for c in costs), costs)

    def test_missing_voices_come_last(self):
        """A partial harmonisation is only ever chosen when nothing fuller fits."""
        shells = self.engine.get_grip_voicings(
            Note("B4"), "maj7", chord_name="Cmaj7", grips=("shell",)
        )
        self.assertTrue(shells)
        self.assertEqual(
            self.engine.voicing_cost(shells[0], SelectionCriteria()).missing, 1.0
        )

    def test_the_selector_really_is_the_argmin_of_the_cost(self):
        candidates = self.engine.get_all_grip_voicings(
            Note("C5"), "maj7", chord_name="Cmaj7"
        )
        self.assertTrue(candidates)
        best = self.engine._best_voicing(candidates, previous=None)
        self.assertIsNotNone(best)
        assert best is not None  # pyright does not narrow through assertIsNotNone
        for v in candidates:
            self.assertLessEqual(
                self.engine.voicing_cost(best, SelectionCriteria()),
                self.engine.voicing_cost(v, SelectionCriteria()),
            )

    def test_a_root_or_fifth_bass_breaks_an_exact_tie(self):
        """
        The bass-function term scores 0 for a root or 5th and 1 otherwise.

        Dm7/F4 is the case that needed it: the contiguous 5-4-3-2 and the 6-4-3-2 tie on
        every earlier criterion, and without this term the better bass loses on the grip
        tie-break. It applies to whichever shape won, not to one family, so a contiguous
        shape with a root bass is not penalised either.
        """
        candidates = self.engine.get_grip_voicings(
            Note("F4"), "m7", chord_name="Dm7", top_string=4,
            grips=("drop2", "drop2_6432"),
        )
        self.assertTrue(candidates)
        root_pc = Note("D4").midi_note() % 12
        for v in candidates:
            # `bass_pc` is Optional on the dataclass - it is None for an all-muted
            # shape - so it is narrowed here rather than at each of the two call
            # sites that subtract from it. Every candidate this grip returns has a
            # lowest voice, which the assert states.
            assert v.bass_pc is not None, f"{v.tab_string()} has no bass"
            bass_ok = (v.bass_pc - root_pc) % 12 in BASS_DEGREES_6432
            self.assertEqual(
                self.engine.voicing_cost(
                    v, SelectionCriteria(root_pc=root_pc)
                ).bass,
                0.0 if bass_ok else 1.0,
                v.tab_string(),
            )

    def test_the_bass_term_is_consulted_last_and_only_when_it_can_be(self):
        """
        It sits at index 6, below every criterion that protects correctness, and it is
        skipped entirely without a root - an unparseable chord name gets the old
        behaviour rather than a guessed bass.
        """
        candidates = self.engine.get_grip_voicings(
            Note("F4"), "m7", chord_name="Dm7", top_string=4, grips=("drop2",)
        )
        self.assertTrue(candidates)
        v = candidates[0]
        without_root = self.engine.voicing_cost(v, SelectionCriteria())
        with_root = self.engine.voicing_cost(
            v, SelectionCriteria(root_pc=Note("D4").midi_note() % 12)
        )
        # The tuple is a fixed width whether or not a root is supplied, so `root_pc`
        # only ever changes a *value*; it never reshapes the cost or reorders the
        # criteria above it. That is what keeps `voicing_cost` a total order and the
        # engine deterministic.
        self.assertEqual(len(with_root), len(without_root))
        self.assertEqual(with_root[:-1], without_root[:-1], v.tab_string())
        self.assertNotEqual(with_root.bass, without_root.bass, v.tab_string())
        # A bass that is a 3rd or a 7th still scores 1.0. No contiguous Dm7 drop-2 has
        # one - they all put D or A underneath - so this sweeps for a chord that does,
        # pairing each shape with the chord it was actually generated for, because the
        # term reads the *root*, not the shape.
        checked = 0
        for chord, quality in QUALITIES:
            root_pc = root_midi_of(chord) % 12
            for melody in every_chord_tone(chord, quality):
                for v in self.engine.get_grip_voicings(
                    Note(melody), quality, chord_name=chord, top_string=4,
                    grips=("drop2",),
                ):
                    assert v.bass_pc is not None, f"{v.tab_string()} has no bass"
                    bass_ok = (v.bass_pc - root_pc) % 12 in BASS_DEGREES_6432
                    self.assertEqual(
                        self.engine.voicing_cost(
                            v, SelectionCriteria(root_pc=root_pc)
                        ).bass,
                        0.0 if bass_ok else 1.0,
                        f"{chord} {melody} {v.tab_string()}",
                    )
                    checked += 1
        self.assertGreater(checked, 20, "the sweep found almost nothing to check")

    def test_the_first_chord_starts_near_the_middle_of_the_neck(self):
        """With nothing to lead from, "stay in position" becomes "start somewhere sane"."""
        steps = VoiceLeadingEngine.arrange_progression([("D5", "m7", "Dm7")])
        self.assertEqual(len(steps), 1)
        self.assertLessEqual(abs(steps[0].voicing.avg_fret - 9), 4.0)

    def test_span_outranks_neck_position(self):
        """
        A tighter shape wins even when it moves the hand.

        This is the one criterion promoted across another, so it is asserted on the
        cost tuple directly rather than only through a result. Cm7b5 under C5 is the
        motivating case: with span ranked below position the engine returned
        `8-x-8-8-13-x`, index at 8 and pinky at 13, because it kept the hand where the
        previous chord was. The shape that actually gets chosen now spans one fret.
        """
        steps = VoiceLeadingEngine.arrange_progression([("C5", "m7b5", "Cm7b5")])
        self.assertEqual(len(steps), 1)
        chosen = steps[0].voicing
        self.assertEqual(chosen.tab_string(), "x-x-8-8-7-8")
        self.assertEqual(chosen.fret_span(), 1)
        # The wide shape is still *offered* - the cap is what bounds it, not the
        # ranking - and the cost tuple is what prefers the narrow one.
        candidates = self.engine.get_all_grip_voicings(
            Note("C5"), "m7b5", chord_name="Cm7b5"
        )
        self.assertTrue(candidates)
        best = self.engine._best_voicing(candidates, previous=chosen)
        assert best is not None  # pyright does not narrow through assertIsNotNone
        self.assertLessEqual(best.fret_span(), chosen.fret_span())

    def test_span_zero_and_one_tie_so_position_decides(self):
        """
        One fret of stretch does not outrank keeping the hand where it is.

        Span 0 and span 1 are bucketed to the same value at the span index, so a
        zero-span barre loses to a one-fret shape on position rather than beating it
        on span. Bb7 under F4 -> G4 is the motivating case, and it came from a
        player reading the tab: the sequence was voiced `x-x-6-7-6-x`,
        `x-x-x-3-3-3`, `x-x-6-7-6-x` - down to a fret-3 barre for one note and back.
        The alternative at frets 7-8 is span 1 against the barre's span 0, and the
        barre won only on that index. Now position decides and the hand stays put.

        Asserted on the cost tuple directly, because that is where the bucket lives;
        the arrangement below is the same fact end-to-end. Span 2 is asserted too:
        it must still outrank position, or the bucket has quietly become the swap
        that `docs/engine.md` measured and rejected.
        """
        barre = Voicing(
            frets=[-1, -1, -1, 3, 3, 3], top_fret=3, avg_fret=3.0, grip="shell"
        )
        in_position = Voicing(
            frets=[-1, 8, -1, 7, 8, -1], top_fret=8, avg_fret=7.6667, grip="shell"
        )
        wide = Voicing(
            frets=[-1, -1, 8, 9, 10, -1], top_fret=10, avg_fret=9.0, grip="shell"
        )
        # Both are tight, so span ties (0.0) and the position index decides:
        # in_position sits 1.33 frets from the previous shape, the barre 3.33.
        previous = Voicing(
            frets=[-1, -1, 6, 7, 6, -1], top_fret=6, avg_fret=6.3333, grip="shell"
        )
        self.assertEqual(
            self.engine.voicing_cost(
                barre, SelectionCriteria(previous=previous)
            ).span,
            self.engine.voicing_cost(
                in_position, SelectionCriteria(previous=previous)
            ).span,
        )
        self.assertLess(
            self.engine.voicing_cost(
                in_position, SelectionCriteria(previous=previous)
            ),
            self.engine.voicing_cost(barre, SelectionCriteria(previous=previous)),
        )
        # A span-2 shape still loses on span alone, position notwithstanding.
        self.assertGreater(
            self.engine.voicing_cost(
                wide, SelectionCriteria(previous=previous)
            ).span,
            self.engine.voicing_cost(
                barre, SelectionCriteria(previous=previous)
            ).span,
        )
        self.assertLess(
            self.engine.voicing_cost(barre, SelectionCriteria(previous=previous)),
            self.engine.voicing_cost(wide, SelectionCriteria(previous=previous)),
        )

        # End-to-end: the G4 keeps the hand at frets 6-8 instead of jumping to 3.
        # The `x-x-6-7-6-x` three-note shells were the original report, taken with
        # `grips=("shell",)`; with the palette the arity rule derives, the engine holds
        # the same position and states a fourth voice (A string 6 = F3, the b7), which
        # the tuple prefers on criterion 2 - so the claim this test makes is the one it
        # always made: the hand does not jump.
        steps = VoiceLeadingEngine.arrange_progression(
            [("F4", "7", "Bb7"), ("G4", "7", "Bb7"), ("F4", "7", "Bb7")]
        )
        self.assertEqual(
            [s.voicing.tab_string() for s in steps],
            ["6-x-6-7-6-x", "6-x-6-7-8-x", "6-x-6-7-6-x"],
        )
        self.assertEqual(
            [s.grip for s in steps], ["drop2_6432", "drop2_6432", "drop2_6432"]
        )

    def test_span_is_only_promoted_over_position_not_over_correctness(self):
        """
        The promotion is a trade between two preferences, not a licence to be wrong.

        A shape sounding a note outside the chord still loses to a correct one, however
        tight it is, and a partial harmonisation still loses to a complete chord. Both
        of those criteria sit above span, and this holds it to that.

        Criterion 0 is a **count** of the wrong notes, not a flag, so "outside" here is
        any positive count and "clean" is exactly zero.
        """
        candidates = self.engine.get_all_grip_voicings(
            Note("C5"), "m7b5", chord_name="Cm7b5"
        )
        self.assertTrue(candidates)
        tones = set(ChordParser.get_chord_tones("m7b5", "Cm7b5"))
        clean = [v for v in candidates if set(v.pitch_classes()) <= tones]
        self.assertTrue(clean)
        for v in candidates:
            cost = self.engine.voicing_cost(
                v, SelectionCriteria(allowed_tones=tones)
            )
            if set(v.pitch_classes()) <= tones:
                self.assertEqual(cost[0], 0.0, v.tab_string())
            else:
                self.assertGreater(cost[0], 0.0, v.tab_string())
                # A foreign note outranks a tighter span, never the reverse.
                for good in clean:
                    self.assertLessEqual(
                        self.engine.voicing_cost(
                            good, SelectionCriteria(allowed_tones=tones)
                        ).foreign,
                        cost[0],
                        f"{v.tab_string()} beat the clean {good.tab_string()}",
                    )

    def test_wrong_notes_are_counted_not_merely_flagged(self):
        """
        One wrong note ranks above two, and two above four.

        As a boolean they all scored 1.0, so the tie fell through to fret span - and the
        wronger shape usually won there, because a shape with more wrong notes is not
        obliged to be wider but tends to be. Counting is what lets the selector prefer
        the less wrong shape when no correct one is on offer.
        """
        tones = {t % 12 for t in ChordParser.get_chord_tones("maj7", "Cmaj7")}
        counts = {}
        for melody, quality, chord in (
            ("F#5", "7", "G7"), ("C5", "maj7", "Cmaj7"), ("A4", "7", "G7"),
        ):
            for v in self.engine.get_grip_voicings(
                Note(melody), quality, chord_name=chord, top_string=5,
                grips=("drop2",),
            ):
                others = [p for p in v.midi_notes() if p % 12 != Note(melody).midi_note() % 12]
                wrong = sum(1 for p in others if p % 12 not in tones)
                if wrong == 0:
                    continue
                cost = self.engine.voicing_cost(
                    v,
                    SelectionCriteria(
                        allowed_tones=tones,
                        melody_pc=Note(melody).midi_note() % 12,
                    ),
                )
                counts.setdefault(wrong, []).append(cost[0])
        self.assertTrue(counts, "no impure drop-2 candidate to compare")
        for wrong, values in counts.items():
            for value in values:
                self.assertEqual(
                    value, float(wrong),
                    f"{wrong} wrong notes should cost {wrong}, not {value}",
                )

    def test_the_melody_is_excluded_from_the_count_when_the_caller_says_which(self):
        """
        A melody outside the chord makes every candidate impure, so it cannot discriminate.

        The note is the caller's and is never rewritten, so counting it would leave the
        criterion unable to tell two shapes apart at all - which is what it did, and the
        reason a correct drop-2 & 4 lost to a drop-2 carrying four wrong notes. Passing
        `melody_pc` lets a shape that adds nothing wrong reach zero. Omitting it counts
        the melody like any other note, which is the previous behaviour and is what a
        caller that does not know the melody gets.
        """
        tones = {t % 12 for t in ChordParser.get_chord_tones("7", "G7")}
        melody_pc = Note("F#5").midi_note() % 12
        self.assertNotIn(melody_pc, tones, "the fixture must be a non-chord melody")
        found = False
        for v in self.engine.get_grip_voicings(
            Note("F#5"), "7", chord_name="G7", top_string=5, grips=("drop24",)
        ):
            found = True
            others = [p % 12 for p in v.midi_notes() if p % 12 != melody_pc]
            self.assertTrue(
                set(others) <= tones, f"{v.tab_string()} adds a wrong note of its own"
            )
            self.assertEqual(
                self.engine.voicing_cost(
                    v, SelectionCriteria(allowed_tones=tones, melody_pc=melody_pc)
                ).foreign,
                0.0,
                v.tab_string(),
            )
            # Without the melody excluded, the same shape is flagged instead.
            self.assertEqual(
                self.engine.voicing_cost(
                    v, SelectionCriteria(allowed_tones=tones)
                ).foreign,
                1.0,
                v.tab_string(),
            )
        self.assertTrue(found, "no drop-2 & 4 under this melody to check")

    def test_the_tuple_is_seven_wide_and_no_criterion_reads_the_grip(self):
        """
        A grip family is not a property of a shape, so nothing in the tuple ranks one.

        Two families can generate the very same tab, and a four-note drop-2 never even
        reaches a tie with a shell - criterion 2 separates them on note count - so a grip
        term could only choose a *name*, or paper over a genuine tie. The width is pinned
        because bass function must stay where it is: a term added at the end would move it.
        """
        v = self.engine.get_drop2_voicings(Note("C5"), "maj7", chord_name="Cmaj7")[0]
        self.assertEqual(
            len(self.engine.voicing_cost(v, SelectionCriteria(root_pc=0))), 7
        )
        # Relabelling the very same shape as each other family changes nothing at all, at
        # any width: `grip` is informational, and this is where that has to hold.
        chosen_cost = self.engine.voicing_cost(v, SelectionCriteria(root_pc=0))
        for grip in GRIP_PREFERENCE:
            self.assertEqual(
                self.engine.voicing_cost(
                    replace(v, grip=grip), SelectionCriteria(root_pc=0)
                ),
                chosen_cost,
                f"relabelling the shape as {grip} changed its cost",
            )
