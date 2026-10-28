"""The chord timeline: where a chord is in force, and where the tune is silent.

`chord_at` answers for one beat and `chord_slots` for a bar, and the recording they do
is what lets the union generate a chord at a position the written symbols did not mark.
The measurement this layer exists for is `docs/history/open-issues.md` item 1; the classes here
do not restate its numbers, they pin the behaviour it describes.

`chord_or_fail` lives here rather than in `support` because it is an assertion, not a
fixture: a test that asks for a chord and gets nothing has found a defect.
"""

import os
import tempfile
import unittest

from arranger import format_progression, parse_rhythm
from arranger.options import ArrangeOptions, Request
from arranger.slots import arrange_slots
from arranger.tuning import SILENCE_TUNE_SILENT
from headxml import (
    Head,
    HeadChange,
    arrange_xml_head,
    chord_at,
    chord_slots,
    first_complete_bar,
    head_skeleton,
    load_musicxml,
    melody_at,
    melody_state,
    rhythm_slots,
)
from tabstaff import format_tab_staff, write_tab_html
from tests.support import (
    BUT_NOT_FOR_ME,
    I_WAS_DOING_ALL_RIGHT,
    MISTY,
    RAINY_DAY,
    TENOR_MADNESS,
    arranged,
    harmony,
    note,
    rest,
    score,
    score_bars,
    sweep_head_paths,
    write_score,
)


def chord_or_fail(changes, bar: int, beat: float) -> HeadChange:
    """`chord_at`, raising rather than returning `None`.

    **`Optional` is the right return type for the library and the wrong one for a test.**
    A position with no chord in force is a legitimate answer the function must be able to
    give, so it cannot raise; but a test that asks for a chord and gets nothing has found
    a defect, and should stop rather than compare against `None`. Pyright does not narrow
    through `assertIsNotNone` either, so every assertion would otherwise need a cast or a
    second `assert` — twelve of them, for one rule.

    The same reasoning as `guide_pcs` in `test_comping.py`.
    """
    change = chord_at(changes, bar, beat)
    if change is None:
        raise AssertionError(
            f"bar {bar} beat {beat}: no chord is in force, so the query cannot be checked"
        )
    return change


class TestChordTimeline(unittest.TestCase):
    """`Head.chords`: the harmony as a timeline, independent of the melody.

    **Phase 1 of open-issues item 1**, and this class tests only the *recording* — the
    timeline is built and nothing consumes it yet, so every arrangement is
    byte-identical. The arrangement-level tests belong to the phase that fixes the
    defect, and writing them now would be testing a fix that does not exist.

    The loss it records is real and is in the committed scores: 6 of their 154
    `<harmony>` elements precede no note at all, so the chord they declare is in force
    over material no note describes.

    The load-bearing test is `test_the_timeline_reproduces_every_notes_own_chord`. It
    states that the timeline, built independently, **agrees with the shipped note path
    on all 158 notes** — so a change that disagrees with the notes is a change that is
    wrong, not a second opinion. That is the only check that makes the others mean
    anything.
    """

    def _chords_in_bar(self, head: Head, bar: int):
        return [(round(c.beat, 6), c.chord) for c in head.chords if c.bar == bar]

    def _notes_in_bar(self, head: Head, bar: int):
        return [(round(n.beat, 6), n.chord) for n in head.notes if n.bar == bar]

    def load(self, measures: str, **kwargs) -> Head:
        """A score written to a temp file and read back, as `TestKeySignature` does."""
        path = write_score(score(measures, **kwargs))
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    def test_a_chord_no_note_follows_is_still_recorded(self):
        """The defect itself, on a committed score: bar 2 of `synthetic_triplets`.

        Written as three `Am7` notes, then `HARMONY(7)` and a rest - so the `D7`
        governs the rest of the bar and no note follows it.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertEqual(
            self._notes_in_bar(head, 2),
            [(1.0, "Am7"), (1.5, "Am7"), (2.0, "Am7")],
        )
        self.assertEqual(self._chords_in_bar(head, 2), [(1.0, "Am7"), (2.5, "D7")])

    def test_a_bar_of_nothing_but_rests_still_has_its_chords(self):
        """Bar 6 of `synthetic_repeat_slash` has **no notes at all** and two changes.

        This is the case that cannot even be asked of the note path — there is no note to
        ask with — so it is the strongest of the three.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(self._notes_in_bar(head, 6), [])
        self.assertEqual(self._chords_in_bar(head, 6), [(1.0, "Am7"), (2.0, "D9")])

    def test_the_timeline_reproduces_every_notes_own_chord(self):
        """The cross-check: 158 of 158, on all three fixtures.

        `notes[i].chord` is the shipped fact and `head.chords` is the new one; the
        timeline is forward-filled to a note's own `(bar, beat)` and must agree. A
        disagreement would mean one of the two is wrong, and `notes` is the one with
        every published arrangement behind it.

        Notes whose chord the loader could not translate are skipped, because they are
        counted in `Head.unmapped` and never recorded — the same rule as on the note
        path, and asserting otherwise would be asserting a guess.
        """
        checked = 0
        for path in (BUT_NOT_FOR_ME, RAINY_DAY, I_WAS_DOING_ALL_RIGHT):
            head = load_musicxml(path)
            for written in head.notes:
                if written.quality is None:
                    continue
                checked += 1
                in_force = chord_or_fail(head.chords, written.bar, written.beat).chord
                self.assertEqual(
                    in_force, written.chord,
                    f"{path}: bar {written.bar} beat {written.beat} - the timeline says "
                    f"{in_force!r} and the note says {written.chord!r}",
                )
        # A count as well as an agreement, so an empty fixture cannot make this vacuous.
        #
        # **158, not 158, because three of these scores carry a repeat.** `heres_that_
        # rainy_day` (bars 1-4, then 5-6 and 7-8) and `synthetic_triplets` (bars
        # 1-34, then 7) now expand to the bars a player actually plays, so their repeated
        # sections - and the notes and `<harmony>` in them - are stated on every pass. The
        # cross-check is over the expanded head, and the count is the expanded note count.
        self.assertEqual(checked, 158)

    def test_a_hand_built_case_isolates_it(self):
        """One note, then a chord that only rests follow.

        The synthetic counterpart to the two fixtures above: it says the rule without
        depending on a particular score's contents, and it is the shape a test of the
        *fix* should be written against.
        """
        body = (
            harmony("D", "minor") + note("D", 5)
            + harmony("A", "dominant") + rest() + rest()
        )
        head = self.load(body, divisions=4, beats=4)
        self.assertEqual([n.chord for n in head.notes], ["Dm"])
        self.assertEqual(
            [(c.beat, c.chord) for c in head.chords], [(1.0, "Dm"), (2.0, "A7")]
        )

    def test_the_timeline_is_empty_for_a_head_with_no_harmony(self):
        """Defaulted, so a `Head` built by hand or by a test is unaffected.

        A new field that had to be populated to be safe would be a breaking change to
        every construction site; an empty default is what keeps phase 1 additive.
        """
        self.assertEqual(Head().chords, [])
        self.assertEqual(len(Head().notes), 0)

    def test_a_change_is_a_head_change_carrying_its_position(self):
        """The record's own shape, which is what a consumer will read.

        `quality` and `bass` are carried rather than re-derived: `bass` is a slash bass
        the file spells separately from the quality, and re-parsing the chord name to
        recover it would lose a spelling the loader already resolved. `key` rounds the
        beat to six places, because the timeline is compared against `HeadNote.beat` and
        two floats that differ only in the seventh decimal are the same position.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        # **The second** change in the bar, not the first: bar 2 is
        # `Am7` under a written note and `D7` under a rest, and the `D7` is the one
        # no note would ever record.
        change = next(c for c in head.chords if c.bar == 2 and c.chord == "D7")
        self.assertIsInstance(change, HeadChange)
        self.assertEqual((change.bar, change.chord), (2, "D7"))
        self.assertEqual(change.quality, "7")
        self.assertIsNone(change.bass)
        self.assertEqual(change.key, (2, round(change.beat, 6)))
        # And `key` names the beat the change takes effect on, which is the beat the
        # rest begins - the note path has no step here to compare against.
        self.assertEqual(change.key, (2, 2.5))

    def test_an_untranslatable_chord_is_still_counted_and_not_recorded(self):
        """Never guessed, on the timeline exactly as on the note path.

        A `<harmony>` this library cannot voice is appended to `unmapped` and skipped. If
        it were also recorded, a later fix to the alias table would silently start
        emitting a chord nobody asked for.
        """
        unvoiceable = (
            "<harmony><root><root-step>G</root-step></root>"
            "<kind>not-a-real-kind</kind></harmony>"
        )
        body = harmony("C", "major") + note("C", 5) + unvoiceable
        head = self.load(body, divisions=4, beats=4)
        self.assertEqual(len(head.unmapped), 1)
        # `harmony("C", "major")` spells a major triad `Cmaj`, and the unvoiceable
        # element must not appear - so this is one entry, not two.
        self.assertEqual([c.chord for c in head.chords], ["Cmaj"])

    def test_the_beat_of_a_change_is_where_its_note_would_have_been(self):
        """The `<harmony>` position and the note it precedes agree, in a 2/2 bar.

        Trap 9's denominator: a 2/2 bar and a 4/4 bar are both four quarters long, so
        reading a raw division count as a beat number is right in one and wrong in the
        other. Every fixture here is 2/2, which is exactly the metre that catches it —
        a quarter note is on beat 1.5, not beat 3.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        changes = self._chords_in_bar(head, 2)
        notes = self._notes_in_bar(head, 2)
        self.assertTrue(changes and notes)
        # A change and the note it governs must name the same beat and the same chord,
        # or the timeline is describing a different music from the notes.
        self.assertEqual(changes[0], notes[0])

    def test_nothing_consumes_the_timeline_yet(self):
        """Phase 1 is additive: `head_skeleton` still reads `notes` alone.

        Asserted rather than assumed, because it is the property that makes this phase
        safe to land on its own — and it will start failing when the fix arrives, at
        which point this test should be **replaced**, not deleted (AGENTS.md trap 5).
        """
        head = load_musicxml(RAINY_DAY)
        skeleton = head_skeleton(head)
        self.assertEqual(len(skeleton), len(head.notes))
        self.assertTrue(head.chords, "the fixture must actually carry harmony")


class TestChordAt(unittest.TestCase):
    """`chord_at`: which chord is in force at a position, by forward fill.

    **Phase 2 of open-issues item 1** — the query, with no consumer. The next phase uses
    it for a beat no melody note describes; until then nothing calls it but tests, so
    this is a specification written before its first use, which is the only honest time
    to write one.

    The three rules it has to get right, each measured rather than assumed:

    - a chord holds until the next change replaces it, **including at its own beat**;
    - where a bar declares two chords on the same beat, **the last one wins** — bars 5
      and 7 of `synthetic_triplets` are written `Gmaj` then `Eb7`, and the note in
      each bar carries `Eb7`, so first-wins would disagree with the shipped output;
    - a position before the first change has **no** chord, and says so rather than
      guessing.
    """

    def test_a_chord_holds_until_the_next_one_replaces_it(self):
        """Bar 2 of `synthetic_triplets`: `Am7` at beat 1, `D7` at beat 2.5.

        Two positions strictly between them, and one exactly on the change.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertEqual(chord_or_fail(head.chords, 2, 1.0).chord, "Am7")
        self.assertEqual(chord_or_fail(head.chords, 2, 1.5).chord, "Am7")
        self.assertEqual(chord_or_fail(head.chords, 2, 2.0).chord, "Am7")
        # **On** the change, not before it: the note path captures the chord before a
        # note, so a change sharing a beat with the note it governs still applies.
        self.assertEqual(chord_or_fail(head.chords, 2, 2.5).chord, "D7")

    def test_it_answers_for_a_position_no_note_describes(self):
        """Bar 6 of `synthetic_repeat_slash` has no notes and two changes.

        This is the query's reason to exist, and it is the position the note path cannot
        be asked about at all.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(chord_or_fail(head.chords, 6, 1.0).chord, "Am7")
        self.assertEqual(chord_or_fail(head.chords, 6, 1.5).chord, "Am7")
        self.assertEqual(chord_or_fail(head.chords, 6, 2.0).chord, "D9")
        # Past the end of the bar it still carries the last thing declared, which is
        # what "holds until the next one replaces it" means across a barline.
        self.assertEqual(chord_or_fail(head.chords, 6, 9.0).chord, "D9")

    def test_the_last_change_at_a_position_wins(self):
        """Bars 5 and 7 declare two chords on beat 1.0, and the note carries the second.

        Not a synthetic tie: measured on the committed score. First-wins would put
        `Gmaj` and `G6` under notes that ship with `Eb7`, so this is the rule that keeps
        the query from disagreeing with the output it will one day feed.

        **Identified by `written_bar`, queried by `bar`.** `synthetic_triplets` carries
        a repeat, so the loader renumbers written bar 5 (the 1st ending's bar) to the
        absolute 5 and written bar 7 (the 2nd ending's bar) to the absolute 11; the
        rule under test is about the score's own numbering, so the bar is found by
        `written_bar` and the query is made at the absolute position it landed on.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        for written, first in ((5, "Gmaj"), (7, "G6")):
            at_bar = [
                (c.beat, c.chord) for c in head.chords if c.written_bar == written
            ]
            self.assertEqual(
                at_bar, [(1.0, first), (1.0, "Eb7")], f"written bar {written} changed"
            )
            bar = next(
                c.bar for c in head.chords if c.written_bar == written
            )
            self.assertEqual(
                chord_or_fail(head.chords, bar, 1.0).chord, "Eb7", f"bar {bar}"
            )
            # And the note in that bar agrees, which is what makes the rule measurable
            # rather than merely asserted.
            self.assertEqual(
                {n.chord for n in head.notes if n.bar == bar}, {"Eb7"}, f"bar {bar}"
            )

    def test_a_position_before_the_first_change_has_no_chord(self):
        """`None`, not the first chord — a position no chord has reached has no harmony.

        The failure this avoids is the one the rest of the module refuses everywhere: a
        chord invented where the file states none.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertIsNone(chord_at(head.chords, 0, 1.0))
        self.assertIsNone(chord_at([], 1, 1.0))
        # A bar before the head's first bar is a plausible phase-3 caller, so the
        # out-of-range case is asserted rather than assumed.
        self.assertIsNone(chord_at(head.chords, -1, 1.0))

    def test_a_pickup_bar_is_ordered_before_bar_one(self):
        """Bars are signed — a pickup is negative — so a plain integer compare is right.

        Stated because "a signed bar sorts correctly" is an assumption a reader has to
        make, and the day it is wrong is the day a pickup vanishes from a part.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        first = head.chords[0]
        if first.bar > 0:
            self.assertIsNone(chord_at(head.chords, first.bar - 1, 1.0))
        self.assertEqual(chord_at(head.chords, first.bar, first.beat), first)

    def test_it_agrees_with_the_note_path_on_every_note(self):
        """The cross-check, now over the shipped function: 158 of 158.

        `TestChordTimeline` proved the *data* reproduces the notes; this proves the
        *query* over that data does, which is a different thing and could have been wrong
        at the boundary the duplicate-position rule covers. The count is 158 rather than
        158 because the repeat-bearing fixtures (`synthetic_repeat_slash`,
        `synthetic_triplets`) now expand to the bars a player actually plays - see
        `test_the_timeline_reproduces_every_notes_own_chord`.
        """
        checked = 0
        for path in (BUT_NOT_FOR_ME, RAINY_DAY, I_WAS_DOING_ALL_RIGHT):
            head = load_musicxml(path)
            for written in head.notes:
                if written.quality is None:
                    continue
                checked += 1
                change = chord_at(head.chords, written.bar, written.beat)
                assert change is not None, (
                    f"{path}: bar {written.bar} beat {written.beat} has no chord in force"
                )
                self.assertEqual(
                    change.chord, written.chord,
                    f"{path}: bar {written.bar} beat {written.beat} - {change.chord!r} vs "
                    f"{written.chord!r}",
                )
        self.assertEqual(checked, 158)

    def test_an_unsorted_timeline_still_answers_correctly(self):
        """A hand-built `Head.chords` need not be in position order.

        The scan is not broken out of early, precisely so this works: a forward fill that
        stopped at the first entry past the target would answer `D7` here instead of
        `Am7`, and the caller would have no way to know the list was the problem.
        """
        unsorted = [
            HeadChange(bar=2, beat=1.0, chord="Am7", quality="m7"),
            HeadChange(bar=3, beat=1.0, chord="D7", quality="7"),
            HeadChange(bar=1, beat=1.0, chord="Gmaj", quality="maj"),
        ]
        self.assertEqual(chord_or_fail(unsorted, 2, 1.5).chord, "Am7")
        self.assertEqual(chord_or_fail(unsorted, 3, 1.0).chord, "D7")
        self.assertEqual(chord_or_fail(unsorted, 1, 1.0).chord, "Gmaj")
        self.assertIsNone(chord_at(unsorted, 0, 1.0))


class TestChordSlots(unittest.TestCase):
    """`chord_slots` and the union: where a generated position comes from, and how long.

    **Two producers of positions, and this class holds both to their own rule.** The
    *generated* positions (`chord_slots`) come from each bar's own subdivision, which is
    what lets a comping part state its chord in a bar the tune never enters; a
    *requested* rhythm (`rhythm_slots`) places the positions the caller named, and rings
    each one for its felt beat rather than until the next attack.

    The step count is deliberately **not** the acceptance criterion: what a generated
    union adds depends on the head's own rhythm, so the claims here are the invariants -
    no written note lost, no chord added under a note that is still sounding
    (`test_every_added_position_is_one_the_tune_is_silent_at`,
    `TestANarrowPaletteNeverLosesTheTune`) - and `docs/history/open-issues.md` item 1 owns the
    measurement.
    """

    def setUp(self):
        self.rainy = load_musicxml(RAINY_DAY)
        self.iwas = load_musicxml(I_WAS_DOING_ALL_RIGHT)

    def _melody_positions(self, head):
        return {(s[1], round(s[2], 6)) for s in head_skeleton(head)}

    def _chord_positions(self, head):
        """The `(bar, beat)` set `chord_slots` generates: one per bar's own rhythm."""
        return {(s[2], round(s[3], 6)) for s in chord_slots(head)}

    def _rhythm_positions(self, head, spelling):
        """The same set for a **requested** rhythm, which places its named positions.

        The other producer of positions, and the one a caller reaches with `--chord-on`:
        `every-beat` is every felt beat of every bar, `1and,2and` the ands of a 2/2 one.
        """
        rhythm = parse_rhythm(spelling, head.beats_per_bar, None)
        return {(s[2], round(s[3], 6)) for s in rhythm_slots(head, rhythm)}

    def test_a_bar_with_no_notes_now_gets_its_chords(self):
        """Bar 6 of `synthetic_repeat_slash`: the defect, and the reason for the phase.

        No notes at all, two changes (`Am7` then `D9`), and before this the bar produced
        nothing whatever — it was not quiet, it was absent. The grid now places a chord
        at every 1/12 of a felt beat where a harmony is in force, so the bar is no
        longer empty.
        """
        self.assertEqual([n.bar for n in self.rainy.notes if n.bar == 6], [])
        positions = sorted(
            (beat, chord) for _m, chord, bar, beat, _d in
            chord_slots(self.rainy) if bar == 6
        )
        self.assertTrue(positions, "bar 6 must no longer be absent")
        self.assertEqual(positions[0], (1.0, "Am7"))
        self.assertIn((2.0, "D9"), positions)
        chords = {chord for _beat, chord in positions}
        self.assertEqual(chords, {"Am7", "D9"})

    def test_the_default_request_adds_nothing_in_a_melody_less_bar(self):
        """`head FILE` is the melody plus one chord per note - no position invented.

        The union is a *policy* (`--chord-fills`, and positions the caller names), so the
        default request leaves a bar the tune never enters silent.

        **A comping selection is where this fixture's silent position is still
        added** - the engine's own union, which `Request(melody=False)` reaches
        because a selection with no tune to play is what asks for it. The gate reads
        the **selection** and not the spelling, so a *singing* request is the default
        arrangement and adds nothing either - which is the assertion at the top of
        this test.
        """
        head = self.rainy
        skeleton = head_skeleton(head, None)
        written = {(bar, round(beat, 6)) for _t, bar, beat, _d in skeleton}
        steps, _head, _notes = arranged(RAINY_DAY)
        self.assertEqual(
            {(s.bar, round(s.beat or 0.0, 6)) for s in steps}, written
        )
        self.assertEqual([s for s in steps if s.bar == 6], [])

        comping, _head, _notes = arranged(
            RAINY_DAY, options=ArrangeOptions(request=Request(melody=False))
        )
        silent = sorted((s.beat, s.chord) for s in comping if s.bar == 6)
        self.assertTrue(silent, "bar 6 must state a chord even when the tune never enters")
        self.assertIn((2.0, "D9"), silent)
        for step in comping:
            if step.bar == 6:
                self.assertIsNone(step.melody, step.tab_line())
                self.assertFalse(step.melody_voiced, step.tab_line())

    def test_a_bar_the_melody_does_enter_is_untouched_by_the_engine_union(self):
        """The old bar-level claim, now a fact about the **comping selection**.

        `synthetic_repeat_slash`'s tune is continuous, so the positions the union
        generates inside its note-bearing bars are all ones a note is still *holding* -
        and a held position is not a slot (§9.2). That is why the union adds positions in
        its melody-less bars only. The default request adds none at all, which the test
        above states.
        """
        skeleton = head_skeleton(self.rainy, None)
        melody_bars = {bar for _triple, bar, _beat, _duration in skeleton}
        steps, _head, _notes = arranged(
            RAINY_DAY, options=ArrangeOptions(request=Request(melody=False))
        )
        added = {(s.bar, s.beat) for s in steps} - {
            (bar, round(beat, 6)) for _t, bar, beat, _d in skeleton
        }
        self.assertTrue(added, "the fixture must have a bar the melody never enters")
        for bar, _beat in added:
            self.assertNotIn(bar, melody_bars, f"bar {bar} has notes and was added to")

    def test_every_added_position_is_one_the_tune_is_silent_at(self):
        """The rule the **engine's own union** follows: only where the tune is silent.

        Swept with a comping selection, because that is the union this rule is about -
        the default request adds no position, and a requested position (`chord-on`) is
        deliberately allowed under a held note. The heads are
        `tests.support.sweep_head_paths()`: the rule is position-level and about the
        metre, so three of them answer it, and `synthetic_cut_time` and the waltz
        between them hold the held-note and the skip cases.
        """
        checked = 0
        for path in sweep_head_paths():
            with self.subTest(head=os.path.basename(path)):
                head = load_musicxml(path)
                written = {
                    (bar, round(beat, 6))
                    for _t, bar, beat, _d in head_skeleton(head, None)
                }
                steps, _head, _notes = arranged(
                    path, options=ArrangeOptions(request=Request(melody=False))
                )
                for step in steps:
                    bar, beat = step.bar or 0, step.beat or 0.0
                    if (bar, round(beat, 6)) in written:
                        continue
                    checked += 1
                    self.assertEqual(
                        melody_state(head, bar, beat),
                        "silent",
                        f"bar {bar} beat {beat} was added under a "
                        f"sounding note: {step.tab_line()}",
                    )
        self.assertGreater(checked, 0, "no position was added anywhere")

    def test_a_requested_position_is_added_even_under_a_held_note(self):
        """`chord-on=1and` attacks at 1.5 of **every** bar, and duplicates no written slot.

        This is the request's half of the union, and the reason it is not §9.2-filtered: a
        stab under a note the tune is still holding is exactly what "the and of 1" asks
        for, and the melody-anchored axis refuses precisely that position. A written note
        keeps its own slot - the chord is the note's, not a second attack.
        """
        from arranger.options import Request

        head = load_musicxml(RAINY_DAY)
        written = {
            (bar, round(beat, 6))
            for _t, bar, beat, _d in head_skeleton(head, None)
        }
        steps, _head, _notes = arranged(RAINY_DAY, request=Request(chord_on="1and"))
        added = {
            (s.bar, round(s.beat or 0.0, 6))
            for s in steps
            if (s.bar, round(s.beat or 0.0, 6)) not in written
        }
        bars = {s.bar for s in steps if s.bar is not None}
        for bar in bars:
            self.assertTrue(
                any(
                    s.bar == bar and abs((s.beat or 0.0) - 1.5) < 1e-6
                    for s in steps
                ),
                f"bar {bar} has no attack on the and of 1",
            )
        # The bars whose and of 1 the tune does not write are the ones the request
        # had to add, and at least one of them is a held note.
        self.assertTrue(added, "every and of 1 already had a written note")
        self.assertTrue(
            any(melody_state(head, bar, 1.5) == "held" for bar, _ in added),
            "the fixture must hold a note through the and of 1 somewhere",
        )

    def test_a_melody_less_bar_with_no_harmony_behind_it_adds_nothing(self):
        """The bar-level rule never guesses a chord, which is the invariant that matters most.

        `chord_at` forward-fills, so a bar the melody never enters inherits the last change
        before it - bar 2 of `synthetic_repeat_slash` states the chord that was already in
        force. But a bar with **nothing** behind it has no chord to inherit, and
        `chord_slots` skips the position rather than inventing one: the melody-less bar
        produces no step, so the rule adds a bar the *timeline* can speak for and stays
        silent where it cannot.

        This is `Head.unmapped`'s rule and `chord_at`'s `None` doing their job through the
        union rather than beside it - the union does not have its own idea of what a bar
        sounds.
        """
        document = f"""<?xml version="1.0"?>
<score-partwise version="3.1"><part-list><score-part id="P1"/></part-list><part id="P1">
<measure number="1"><attributes><divisions>4</divisions></attributes>
  {note("C", 5)}
</measure>
<measure number="2"></measure>
</part></score-partwise>"""
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        steps, _head, _notes = arrange_xml_head(path)
        self.assertEqual([s.bar for s in steps], [1], "a bar with no harmony was guessed")

    def test_the_default_grid_adds_no_bar_a_head_does_not_have(self):
        """`synthetic_cut_time` and `synthetic_tab_export` have no melody-less bar, so no bar is added.

        **The bar half of the default grid's change, and the count is not the claim.**
        A bar the melody never enters is still the only thing the union adds *wholesale*;
        the positions it adds inside a bar the tune occupies come from the bar's own
        subdivision, so the step count is not the skeleton's. What these two fixtures
        pin is that every bar that appears is one the file wrote, and that every written
        note is still a step at its own position.
        """
        for path in (BUT_NOT_FOR_ME, TENOR_MADNESS):
            with self.subTest(head=os.path.basename(path)):
                head = load_musicxml(path)
                steps, _head, _notes = arrange_xml_head(path)
                self.assertTrue({s.bar for s in steps} <= set(range(*head.bars)))
                at = {(s.bar or 0, round(s.beat or 0.0, 6)) for s in steps}
                for _triple, bar, beat, _duration in head_skeleton(head, None):
                    self.assertIn((bar, round(beat, 6)), at)

    def test_the_walking_bass_inherits_the_added_bar(self):
        """The default grid now walks the bars the melody never entered.

        `walking_slots` walks the bars the *timings* touch, and the union writes its
        added slots into those timings - so the bass half of item 1 was already correct
        wherever a figure ran. Two spellings are compared. The **engine's own union**
        (`texture` spelled) reaches the bars the tune entered and bar 6, which the melody
        never enters. A **requested** rhythm (`chord_on="every-beat"`) states its
        positions whatever the tune is doing, so it also walks bar 12 - which the union
        withholds because bar 11's F4 is still held through it. That is §9.2, not a
        union withholding a bar it should walk.

        **Bars 6 and 7 still get no thumb note, and that is a different issue.**
        `place_bass` refuses them for the reason `docs/history/open-issues.md` **item 2** measures
        as dominant - no octave of the walk's pitch below the shape - and it refuses them
        identically under a requested rhythm, before and after this change. Asserting a
        thumb note in bar 6 would be asserting item 2's fix, which is deliberately not
        built. So the claim is about which bars the walk *visits*, not which it can place
        a note in.
        """
        def walked(**kwargs):
            steps, _head, _notes = arrange_xml_head(RAINY_DAY, **kwargs)
            return {s.bar for s in steps}

        head = load_musicxml(RAINY_DAY)
        melody_bars = {n.bar for n in head.notes}
        union = walked(
            options=ArrangeOptions(
                        request=Request(
                            melody=False, bass_on="every-beat", bass_notes="walk"
                        ),
                    )
        )
        named = walked(
            request=Request(
                chord_on="every-beat", bass_on="every-beat", bass_notes="walk"
            )
        )
        self.assertLessEqual(union, named, "the union walks a bar no rhythm reaches")
        self.assertEqual(union - melody_bars, {6})
        self.assertEqual(named - melody_bars, {6, 12})
        for bar in union - melody_bars:
            self.assertNotIn(bar, melody_bars)

    def test_the_union_adds_exactly_the_positions_without_a_note(self):
        """The two lists are disjoint where it matters, and the union is their sum.

        Stated as a count rather than eyeballed, because the claim is arithmetic: every
        generated position either already had a melody note or was added. `chord_slots`
        returns the generated positions alone and `_merge_chord_slots` does the union, so
        this measures the two separately and checks the arithmetic rather than trusting
        either.
        """
        melody = self._melody_positions(self.rainy)
        chords = self._chord_positions(self.rainy)
        added = chords - melody
        self.assertGreater(
            len(added), 0,
            "the fixture must actually have positions with no melody note",
        )
        # A position with both is one slot, not two, and the melody slot wins it — so the union
        # is exactly the two sets, and its size is the arithmetic the step loop then sees.
        self.assertEqual(len(chords), len(chords & melody) + len(added))
        self.assertEqual(len(melody | chords), len(melody) + len(added))

    def test_every_requested_rhythm_places_something(self):
        """Every spelling a caller can reach places at least one chord in this head's metre.

        The point of a requested rhythm is that a position the melody never enters is
        still reachable: a figure with no note to hang on must place its chord anyway,
        and a position the metre does not have is refused by `parse_rhythm` rather than
        quietly dropped - so what is left here is the rhythms that fit a 2/2 bar.
        """
        for spelling in ("every-beat", "1and,2and", "1,2", "lastand"):
            with self.subTest(chord_on=spelling):
                self.assertTrue(
                    self._rhythm_positions(self.rainy, spelling),
                    f"chord_on={spelling} places nothing at all",
                )

    def test_a_stab_is_never_a_whole_note(self):
        """The duration is the position's, not the melody note's — which is the point.

        A generated position's stab runs to the next one, capped at the bar line: on this
        2/2 fixture the grid is 1/12 of a felt beat, so each stab is a grid step (1/24
        of a whole note) and the bar's last is shorter still. A **requested** position
        rings for its own felt beat and no further (`_stab_length`), which is what makes
        `--chord-on 1` a stab on each downbeat rather than one chord per bar:
        `every-beat` is `{0.5}` and the ands `{0.25}`. Two producers, three numbers,
        and no whole note anywhere.
        """
        generated = {round(s[4], 6) for s in chord_slots(self.rainy)}
        self.assertNotIn(1.0, generated, "a generated stab was a whole note")
        self.assertTrue(all(d > 0 for d in generated), "a generated stab had zero length")
        for spelling, expected in (("every-beat", {0.5}), ("1and,2and", {0.25})):
            with self.subTest(chord_on=spelling):
                rhythm = parse_rhythm(spelling, self.rainy.beats_per_bar, None)
                durations = {round(s[4], 6) for s in rhythm_slots(self.rainy, rhythm)}
                self.assertEqual(durations, expected, f"chord_on={spelling}")
                self.assertNotIn(1.0, durations, f"chord_on={spelling} produced a whole note")

    def test_a_position_with_no_chord_in_force_is_skipped(self):
        """Never guessed: bar 1 beat 1 of `synthetic_cut_time` is a rest under no harmony.

        The file writes a quarter rest, and the first `<harmony>` arrives on beat 1.5, so
        beat 1.0 has neither a note nor a chord. `chord_at` returns `None` and the position
        is dropped rather than filled with the chord arriving half a beat later.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertIsNone(chord_at(head.chords, 1, 1.0))
        first = min(beat for bar, beat in self._chord_positions(head) if bar == 1)
        self.assertGreater(first, 1.0, "a position with no harmony was filled in")

    def test_the_singing_route_is_not_touched(self):
        """The default request invents no melody: a note-less position carries `None`.

        **What is asserted is the absence of an invented pitch, not the step count.** The
        default grid generates note-less positions of its own, and the honest report for
        one is `melody is None` — never a stand-in pitch.
        """
        body = harmony("C", "major") + note("C", 5)
        path = write_score(score(body, divisions=4, beats=4))
        self.addCleanup(os.unlink, path)
        singing, _head, _notes = arrange_xml_head(path)
        self.assertEqual([s.melody for s in singing if s.melody is not None], ["C5"])

    def test_a_slot_whose_melody_has_stopped_carries_no_melody(self):
        """Where no note is sounding, the slot carries `None` rather than an invention.

        Bar 6 of `synthetic_repeat_slash` follows the last melody note, so there is no tune
        under the chord. **The assertion is `assertIsNone` rather than an equality**, because
        a stand-in pitch would satisfy an equality for the wrong reason (§9.3 step B).
        """
        slots = [
            s
            for s in chord_slots(self.rainy)
            if s[2] == 6 and abs(s[3] - 2.0) < 1e-9
        ]
        self.assertTrue(slots, "bar 6 beat 2 must place its chord")
        for melody, _name, _bar, _beat, _duration in slots:
            self.assertIsNone(melody)


class TestMelodyState(unittest.TestCase):
    """`melody_state`: onset / held / silent, the split `melody_at` cannot give (§9.3 step B).

    Only an onset is a position to reharmonise under (§9.2): a held note was decided
    where it began, and a silent position has nothing to decide beneath. `melody_at`'s
    two-way answer collapses the first two, so these tests keep them apart on a real
    score rather than on a constructed tuple.
    """

    def setUp(self):
        self.head = load_musicxml(RAINY_DAY)
        self.notes = self.head.notes

    def _integer_onset(self):
        """A note beginning on an exact beat, so the rounding test cannot wobble."""
        return next(n for n in self.notes if n.beat == int(n.beat))

    def test_a_written_onset_reports_onset(self):
        """A position a note begins at is its onset - the note's own `key`."""
        note = self._integer_onset()
        self.assertEqual(melody_state(self.head, note.bar, note.beat), "onset")

    def test_a_note_written_across_a_barline_is_still_sounding_on_the_far_side(self):
        """A cut-time tie is one note, and bar 3's downbeat is inside it.

        `synthetic_cut_time.mxl` ends bar 2 with an E♭4 tied to bar 3's first eighth;
        the importer merges the halves into one `HeadNote` at bar 2 beat 2.5 with a
        duration of 0.5 whole notes. A 2/2 beat is a minim, so that note ends at bar 3
        beat 1.5 - not at bar 2 beat 4.0, which is what `duration * 4` read in the
        starting bar claimed. The old answer made bar 3's downbeat *silent*, and the
        comping union put a fresh Cm7 shape there: the re-strike this test forbids.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        self.assertEqual(melody_state(head, 2, 2.5), "onset")
        self.assertEqual(melody_state(head, 3, 1.0), "held")
        self.assertEqual(melody_state(head, 3, 1.5), "onset")

    def test_a_tie_read_as_one_note_crosses_the_barline_at_its_own_length(self):
        """The merged note ends in the bar it reaches, not in the bar it began.

        Two half notes in 2/2 tied across the bar line are one whole note: from bar 1
        beat 2.0 to bar 2 beat 2.0. Every position strictly inside it is `held`,
        including the downbeat of bar 2, and its own end instant is already `silent` -
        the note sounds over `[onset, end)`.
        """
        measures = (
            f"{rest(8)}{note('E', duration=8, tie='start')}"
            "</measure>"
            f'<measure number="2">{note("E", duration=8, tie="stop")}'
        )
        path = write_score(score(measures, divisions=4, beats=2, beat_type=2))
        self.addCleanup(os.unlink, path)
        head = load_musicxml(path)
        self.assertEqual(len(head.notes), 1)
        self.assertEqual(head.notes[0].duration, 1.0)
        for beat in (1.0, 1.5):
            with self.subTest(beat=beat):
                self.assertEqual(melody_state(head, 2, beat), "held")
        self.assertEqual(melody_state(head, 2, 2.0), "silent")
        self.assertEqual(melody_state(head, 3, 1.0), "silent")

    def test_the_release_instant_is_already_silence(self):
        """The end is exclusive: the note has stopped *at* its release instant.

        A half note in 2/2 ends at beat 2.0, where a rest begins - so beat 2.0 is the
        first position the tune has left, and `melody_at` returns `None` there rather
        than lending the released pitch to a comp. The boundary is what
        `docs/history/open-issues.md` item 6 measured, and the rest arithmetic agrees with it:
        `melody_rests` begins the rest where the note ended.
        """
        path = write_score(
            score(
                f"{harmony('C', 'major')}{note('E', duration=8)}{rest(8)}",
                divisions=4,
                beats=2,
                beat_type=2,
            )
        )
        self.addCleanup(os.unlink, path)
        head = load_musicxml(path)
        self.assertEqual(melody_state(head, 1, 1.5), "held")
        self.assertEqual(melody_state(head, 1, 2.0), "silent")
        self.assertIsNone(melody_at(head, 1, 2.0))
        self.assertEqual(melody_state(head, 1, 2.1), "silent")

    def test_a_position_inside_a_sounding_note_reports_held(self):
        """A probe between a note's onset and its end inherits that note.

        The probe is the note's own midpoint: half of `duration * beat_type` beats,
        which is half of the length `melody_at` adds. The multiplication by
        `beat_type` rather than by four is the same rule the function itself now
        follows - in 4/4 the two agree, and in 2/2 `duration * 2` is the whole note, so
        a probe written as `duration * 2` would land on the release instead of inside
        it. Asserted as *some* position on the fixture qualifying, because one
        colliding with a later onset merely drops out.
        """
        probes = [
            (written.bar, round(written.beat + written.duration * self.head.beat_type / 2.0, 6))
            for written in self.notes
            if written.duration > 0
        ]
        held = [
            (bar, beat) for bar, beat in probes
            if melody_state(self.head, bar, beat) == "held"
        ]
        self.assertTrue(held, "no position inside a sounding note reports held")

    def test_a_position_the_melody_has_left_reports_silent(self):
        """A position after a sounding note stops is silent, not a forever-hold.

        Bar 6 of `synthetic_repeat_slash` has no written note of its own, but it is
        not silent at its start: bar 5's G4 (0.75 whole notes, 1.5 beats in 2/2) is
        held through beat 1.0. That note ends at beat 1.5, and the release instant is
        the first position the tune has actually left - the tune sounds over
        `[onset, end)`, so this pins beat 1.5 and not beat 2.0.
        """
        self.assertEqual(melody_state(self.head, 6, 1.0), "held")
        self.assertEqual(melody_state(self.head, 6, 1.5), "silent")
        self.assertEqual(melody_state(self.head, 6, 2.0), "silent")

    def test_the_onset_test_rounds_the_beat_like_head_note_key(self):
        """A beat differing in the seventh decimal is the same position, not a new one.

        The rule is `HeadNote.key`'s rounding - one rule, one answer - and §9.5's
        measurement snippet (`abs(n.beat - beat) < 1e-9`) is a *different* rule that
        would call an offset of 1e-7 a separate position and report "held" here. Two
        roundings of the same beat is the disagreement `HeadNote.key`'s docstring
        exists to forbid.
        """
        note = self._integer_onset()
        self.assertEqual(melody_state(self.head, note.bar, note.beat + 1e-7), "onset")


class TestSilentSlotsCarryNoMelody(unittest.TestCase):
    """§9.3 step B at the step level: `ArrangementStep.melody` is `Optional`, honestly.

    The deletion's visible half (open-issues item 1): `Cmaj7  C4  (shell - 3rd & 7th,
    partial)` was printed by the default line tab 14 times on `synthetic_cut_time` under
    `--voices alto,tenor --grid freddie`, reading as a claim that the guitar played C4.
    It did not. What is asserted here is the replacement: a slot the tune does not
    occupy carries `None` and prints blank, while a slot it does occupy is unchanged -
    held notes still carry the note in force (Option A), so this step moves nothing
    under a sounding melody.
    """

    def _arrange(self):
        """A comping selection on every beat over `synthetic_repeat_slash`.

        A **requested** rhythm rather than the generated union, because this is the test
        about a position the tune is still *holding*: a requested position states its
        chord whatever the tune is doing (§9.2 withholds the generated ones), and the
        fixture's melody ends before bar 6, so every bar of the contrast is exercised.
        """
        return arranged(
            RAINY_DAY, request=Request(melody=False, chord_on="every-beat")
        )

    def test_a_slot_where_the_melody_stopped_carries_none(self):
        """The silent position in bar 6 sits under a chord and over no note."""
        steps, _head, _notes = self._arrange()
        silent = [
            step
            for step in steps
            if step.bar == 6 and abs((step.beat or 0.0) - 2.0) < 1e-9
        ]
        self.assertEqual(len(silent), 1, "bar 6 beat 2 must place its chord")
        for step in silent:
            self.assertIsNone(step.melody, step.tab_line())
            self.assertNotIn("C4", step.tab_line())
            self.assertNotIn("None", step.tab_line())
        # The position the tune is still holding is the contrast: it keeps the note
        # in force rather than inventing one or dropping it.
        held = [
            step
            for step in steps
            if step.bar == 6 and abs((step.beat or 0.0) - 1.0) < 1e-9
        ]
        self.assertEqual([step.melody for step in held], ["G4"])

    def test_every_step_carries_the_note_actually_in_force(self):
        """The invariant the placeholder could not state: `step.melody` *is* `melody_at`.

        Every slot - written-note position or grid position - holds exactly the note
        the tune sounds there, and `None` exactly where it sounds nothing. The
        placeholder failed this by construction: all 30 real `C4` slots across the
        fixtures sat on genuinely written C4s, so an equality against a sentinel could
        pass for the wrong reason on either side.
        """
        steps, head, _notes = self._arrange()
        self.assertTrue(steps)
        for step in steps:
            if step.bar is None or step.beat is None:
                continue
            self.assertEqual(
                step.melody,
                melody_at(head, step.bar, step.beat),
                f"bar {step.bar} beat {step.beat}: {step.tab_line()}",
            )

    def test_the_renderers_print_the_absence_blank(self):
        """No renderer says `None`, and none invents the deleted `C4`.

        The three surfaces that read `step.melody`: the line tab and the diagnostic
        line (`arranger.render`), the ASCII staff's width and melody row (`tabstaff`),
        and the HTML melody row. Each had its own formatting path, and each raised or
        lied on a `None` before step B.
        """
        steps, _head, _notes = self._arrange()
        self.assertNotIn("None", format_progression(steps))
        staff = format_tab_staff(steps, show_melody=True)
        self.assertNotIn("None", staff)
        with tempfile.TemporaryDirectory() as tmp:
            html = write_tab_html(steps, os.path.join(tmp, "silent.html"))
            self.assertNotIn("None", html)

    def test_a_no_note_slot_on_a_singing_route_is_comped(self):
        """§9.3 step D: a note-less slot on a *singing* selection is comped, not refused.

        The old rule refused it, with a warning and a skipped slot, because a note-less
        slot could arrive only through the comping union - which ran only when the
        selection had no soprano. Step D made the soprano per slot, so a note-less slot
        on a singing selection is a real case: the guitar has no tune here, so it states
        the chord instead of inventing one (the rule the deleted placeholder broke) or
        dropping the bar. The chord still sounds; only the melody is absent, which the
        renderers print blank.
        """
        steps, _rescued, _notes = arrange_slots(
            [(None, "Dm7"), ("C5", "Cmaj7")],
            [(1, 1.0, 0.5), (1, 2.0, 0.5)],
        )
        self.assertEqual([s.chord for s in steps], ["Dm7", "Cmaj7"])
        self.assertIsNone(steps[0].melody)
        self.assertFalse(steps[0].melody_voiced, "the guitar does not sing a note it has not got")
        self.assertTrue(steps[1].melody_voiced)
        # It states the chord rather than resting, and the line says which it did:
        # a slot the tune is silent at is comped, which reads differently from a
        # position the guitar declined.
        self.assertNotEqual(steps[0].silence, SILENCE_TUNE_SILENT)
        self.assertIn("comping", format_progression([steps[0]]))
        self.assertIn("the tune is silent here", format_progression([steps[0]]))


class TestTheUnionAdmitsTheReleaseInstant(unittest.TestCase):
    """§9.2's hold rule at the step level: a release is not a hold.

    `melody_at` reads a note as sounding over `[onset, end)`, so the position a note is
    released on is one the tune has left - and the union states the chord there rather than
    declining it, which is what `docs/history/open-issues.md` item 6 closed on. A position *inside*
    the note is still withheld: the chord beneath it was decided where the note began,
    under the very note that motivated it.
    """

    def _steps(self):
        """A half note then a rest in 4/4, comped by the union rather than by a rhythm.

        `Request(melody=False)` with no named rhythm is the one selection that reaches the
        union, so the generated positions are this fixture's whole subject.
        """
        path = write_score(
            score(
                f"{harmony('C', 'major')}{note('E', duration=8)}{rest(8)}",
                divisions=4,
                beats=4,
                beat_type=4,
            )
        )
        self.addCleanup(os.unlink, path)
        return arrange_xml_head(path, request=Request(melody=False))[0]

    def test_the_position_a_note_is_released_on_is_comped(self):
        """Beat 3.0 is where the half note ends, and the union states the chord there.

        The note sounds over `[1.0, 3.0)`, so positions inside it (1.0833 ... 2.9167
        on the 1/12 grid) are **held** and withheld, while beat 3.0 is its release and
        admitted, and beat 4.0 is the silence the union has always covered. The
        withheld positions are the contrast that makes this the boundary rather than a
        blanket "the union fills the bar": only the instant the tune stops is the one
        that moved.
        """
        steps = self._steps()
        beats = [(step.bar, step.beat, step.melody) for step in steps]
        self.assertIn((1, 1.0, "E4"), beats)
        self.assertIn((1, 3.0, None), beats)
        self.assertIn((1, 4.0, None), beats)
        # Positions inside the held note (between 1.0 and 3.0) are withheld.
        inside = [b for b in beats if b[0] == 1 and b[1] is not None and 1.0 < b[1] < 3.0]
        self.assertEqual(inside, [], "a held position was not withheld")

    def test_the_released_position_says_why_it_carries_no_melody(self):
        """The comp on the release prints the true claim, not a borrowed pitch.

        A line that showed the released `E4` would read as the guitar singing a note it
        has already stopped - the failure `ArrangementStep.melody`'s `None` exists to
        prevent - so the column is blank and the clause names the reason.
        """
        steps = self._steps()
        released = [step for step in steps if step.beat == 3.0]
        self.assertEqual(len(released), 1)
        line = format_progression(released)
        self.assertIn("the tune is silent here", line)
        self.assertNotIn("E4", line)


class TestAFigureLandsOnTheForm(unittest.TestCase):
    """A rhythm longer than a bar begins where the **form** does, not where the file does.

    The pickup is the whole difficulty. `synthetic_pickup_common` opens with one beat
    of tune in a short bar, so a two-bar figure beginning in bar 1 would be one bar
    early for the rest of the head - and the bar it consumed would be a bar the form
    does not have. `first_complete_bar` is the one answer, and the slot builders and
    the engine both read it.

    **The chord half of the rule has no corpus witness.** All three committed pickup
    fixtures leave the anacrusis with no `<harmony>`, so a pickup bar they could
    accompany has to be written inline (`_pickup_with_changes`) rather than borrowed:
    the tune's own onsets are what the bar takes, in *both* layers.
    """

    def setUp(self):
        self.misty = load_musicxml(MISTY)

    def _stabs(self, head, spelling, beat: float = 1.5):
        """The bars a requested rhythm puts an attack at `beat` in."""
        rhythm = parse_rhythm(spelling, head.beats_per_bar, None)
        return {
            bar
            for _melody, _name, bar, at, _length in rhythm_slots(head, rhythm)
            if abs(at - beat) <= 1e-6
        }

    def _beats_of(self, steps, beat: float = 1.5):
        """The bars a finished arrangement attacks at `beat` in."""
        return {
            step.bar
            for step in steps
            if abs((step.beat or 0.0) - beat) <= 1e-6
        }

    def test_the_form_begins_after_an_anacrusis(self):
        """One beat of pickup, so the form's first complete bar is bar 2."""
        self.assertTrue(self.misty.first_bar_implicit)
        self.assertEqual(self.misty.bars, (1, 5))
        self.assertEqual(first_complete_bar(self.misty), 2)

    def test_a_two_bar_figure_alternates_from_the_form(self):
        """`1and:none` attacks in bars 2 and 4 - not in the pickup, and not in bar 3."""
        self.assertEqual(self._stabs(self.misty, "1and:none"), {2, 4})

    def test_a_one_bar_figure_starts_after_the_pickup(self):
        """A repeated figure has no bar for the anacrusis either."""
        self.assertEqual(self._stabs(self.misty, "1and"), {2, 3, 4})

    def test_a_silent_segment_silences_its_bar(self):
        """`none:1and` leaves bar 2's beat 1.5 empty and attacks bar 3's."""
        self.assertEqual(self._stabs(self.misty, "none:1and"), {3})

    def test_a_comp_only_selection_plays_the_figure_from_the_form(self):
        """The comp-only timeline takes the same origin as the slot builders.

        A selection with no tune to play lays its timeline out from the rhythm alone,
        so this is the route where a wrong origin would be invisible in the slots and
        plain in the steps.
        """
        steps, _head, _notes = arrange_xml_head(
            MISTY, request=Request(melody=False, chord_on="1and:none")
        )
        self.assertEqual(self._beats_of(steps), {2, 4})

    def _pickup_with_changes(self) -> str:
        """A head whose anacrusis carries a `<harmony>`: the case the corpus lacks.

        Three bars: a pickup with a rest then a note, a whole note under `Dm7`, and a
        half note under `G7` followed by a half-note rest - so the *rest* rules have
        something to answer in both bar 1 and bar 3.
        """
        document = score_bars(
            [
                harmony("F", "major-seventh", text="Fmaj7") + rest(4) + note("C", 5, 4),
                harmony("D", "minor-seventh", text="Dm7") + note("F", 4, 16),
                harmony("G", "dominant", text="G7") + note("B", 4, 8) + rest(8),
            ],
            divisions=4,
            beats=4,
            beat_type=4,
        )
        # `implicit="yes"` is how a score says bar 1 is an anacrusis; the older spelling
        # is to number the measure 0, which the importer reads the same way.
        return write_score(
            document.replace(
                '<measure number="1">', '<measure number="1" implicit="yes">', 1
            )
        )

    def test_the_pickup_bar_is_accompanied_at_the_tune_s_own_onsets(self):
        """The pickup takes the tune, not segment 1 of the figure.

        `chord_on=1and:none` names one position in bar 2 and none in bar 3, and the
        anacrusis is not a bar of the figure at all - so what sounds there is the chord
        under the tune's own note rather than a stab at a position that bar has not got.
        """
        path = self._pickup_with_changes()
        try:
            head = load_musicxml(path)
            self.assertTrue(head.first_bar_implicit)
            self.assertEqual(first_complete_bar(head), 2)
            steps, _head, _notes = arrange_xml_head(
                path, request=Request(chord_on="1and:none")
            )
        finally:
            os.unlink(path)
        pickup = [step for step in steps if step.bar == 1]
        self.assertEqual(
            [(step.beat, step.melody, step.chord) for step in pickup],
            [(2.0, "C5", "Fmaj7")],
        )
        self.assertTrue(pickup[0].voicing.active_frets(), "the pickup is accompanied")
        self.assertEqual(self._beats_of(steps), {2})

    def test_a_fill_is_not_placed_in_the_pickup_bar(self):
        """`--chord-fills` fills the tune's rests, and the anacrusis is not one of them.

        Bar 1's rest is the pickup itself: a chord there would fill the short bar and
        move the head's downbeat. Bar 3's rest is a rest, and it is filled - which is
        what keeps this a rule about the pickup rather than about rests.
        """
        path = self._pickup_with_changes()
        try:
            steps, _head, _notes = arrange_xml_head(
                path, request=Request(chord_on="melody", chord_fills="comp")
            )
        finally:
            os.unlink(path)
        positions = {(step.bar, step.beat) for step in steps}
        self.assertNotIn((1, 1.0), positions)
        self.assertIn((3, 3.0), positions)


