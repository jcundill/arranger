"""The chord timeline: where a chord is in force, and where the tune is silent.

`chord_at` answers for one beat and `chord_slots` for a bar, and the recording they do
is what lets a grid generate a chord at a position the written symbols did not mark.
The measurement this layer exists for is `docs/open-issues.md` item 1; the classes here
do not restate its numbers, they pin the behaviour it describes.

`chord_or_fail` lives here rather than in `support` because it is an assertion, not a
fixture: a test that asks for a chord and gets nothing has found a defect.
"""

import os
import tempfile
import unittest

from arranger import SILENCE_TUNE_SILENT, format_progression
from arranger.options import ArrangeOptions
from arranger.slots import arrange_slots
from headxml import (
    Head,
    HeadChange,
    arrange_xml_head,
    chord_at,
    chord_slots,
    head_skeleton,
    load_musicxml,
    melody_at,
    melody_state,
)
from tabstaff import format_tab_staff, write_tab_html
from tests.support import (
    BUT_NOT_FOR_ME,
    I_WAS_DOING_ALL_RIGHT,
    RAINY_DAY,
    TENOR_MADNESS,
    arranged,
    harmony,
    note,
    rest,
    score,
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
    """`chord_slots` and the union: the comping route stops losing positions.

    **Phase 3 of open-issues item 1, and the first phase that changes output.** Phases 1
    and 2 were additive and left every arrangement byte-identical; this one adds steps.
    The scope is pinned below: **only the comping route with a named grid**, because the
    melody-bearing route's "a chord under each melody note" is the chord-melody idiom and
    a grid must not add positions to it.

    Phase 3 measured this over three fixtures and fourteen flag combinations: six
    arrangements changed and thirty-six did not.

    **The synthetic corpus is shorter, so the counts are smaller.** Current step counts
    under `parts=chord`:

        comps+freddie   cut time 23, repeat slash 35, triplets 112
        comps+joe_pass  cut time 28, repeat slash 39, triplets 114

    Still only the comping route with a named grid, and still only the heads whose
    chord timeline runs past their last note (`Trouble_in_Mind_Blues`,
    `synthetic_repeat_slash`, `synthetic_triplets`).

    **The default grid now generates too, and that is the phase after it.** `every_note`
    places a chord at each bar's own subdivision, so an arrangement with no flags passed
    is no longer byte-identical to the skeleton: measured over the ten heads it adds 150
    positions, inside bars the melody *does* enter as well as the ones it never touches. The
    step count therefore stops being the acceptance criterion; what replaces it is the
    pair of invariants in `test_every_added_position_is_one_the_tune_is_silent_at` and
    `TestANarrowPaletteNeverLosesTheTune` — no written note lost, and no chord added under
    a note that is still sounding.
    """

    def setUp(self):
        self.rainy = load_musicxml(RAINY_DAY)
        self.iwas = load_musicxml(I_WAS_DOING_ALL_RIGHT)

    def _melody_positions(self, head):
        return {(s[1], round(s[2], 6)) for s in head_skeleton(head)}

    def _chord_positions(self, head, grid):
        """The `(bar, beat)` set the **chord part's** row places.

        `grid` is a row spelling (`chord:freddie`), not a bare pattern name: `chord_slots`
        parses its argument, so an unspelled name is a `ValueError` rather than a silent
        fallback to the default grid.
        """
        return {(s[3], round(s[4], 6)) for s in chord_slots(head, grid=grid)}

    def test_a_bar_with_no_notes_now_gets_its_chords(self):
        """Bar 6 of `synthetic_repeat_slash`: the defect, and the reason for the phase.

        No notes at all, two changes (`Am7` then `D9`), and before this the bar produced
        nothing whatever — it was not quiet, it was absent.
        """
        self.assertEqual([n.bar for n in self.rainy.notes if n.bar == 6], [])
        positions = sorted(
            (beat, chord) for _m, _q, chord, bar, beat, _d in
            chord_slots(self.rainy, grid="chord:freddie") if bar == 6
        )
        self.assertEqual(positions, [(1.0, "Am7"), (2.0, "D9")])

    def test_the_default_grid_adds_a_bar_the_melody_never_enters(self):
        """**The melody-less bar, and the first half of open-issues item 1's fix.**

        A bar the melody never enters contributes no melody slot, so every slot in one is
        the union's - and `every_note` is melody-anchored, meaning it names no positions
        of its own to copy from. The unit of generation for such a bar is therefore the
        beat (`_bar_resolution` has no onsets to fit), which is the rule this test pins.

        Bar 6 is the case the old behaviour got wrong: no notes at all, two changes, and
        **no part produced** - not quiet, absent - on every export path. Under the default
        grid it now sounds both chords. Measured on a 2/2 head, so the assertion is two
        steps and not four, which is also the count-with-a-denominator rule of AGENTS.md
        trap 9.
        """
        steps, _head, _notes = arranged(RAINY_DAY)
        silent = [s for s in steps if s.bar == 6]
        silent.sort(key=lambda step: (step.bar or 0, step.beat or 0.0))
        self.assertEqual([(s.beat, s.chord) for s in silent], [(1.0, "Am7"), (2.0, "D9")])
        for step in silent:
            self.assertIsNone(step.melody, step.tab_line())
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_a_bar_the_melody_does_enter_is_untouched_by_the_default_grid(self):
        """The old bar-level claim, kept as a *fixture* fact rather than as the rule.

        `synthetic_repeat_slash`'s tune is continuous, so the positions the default grid
        generates inside its note-bearing bars are all ones a note is still *holding* -
        and a held position is not a slot (§9.2). That is why this fixture adds positions
        in its melody-less bars only. The rule itself is position-level now, and
        `test_every_added_position_is_one_the_tune_is_silent_at` is where it is stated.
        """
        skeleton = head_skeleton(self.rainy, None)
        melody_bars = {bar for _triple, bar, _beat, _duration in skeleton}
        steps, _head, _notes = arranged(RAINY_DAY)
        added = {(s.bar, s.beat) for s in steps} - {
            (bar, round(beat, 6)) for _t, bar, beat, _d in skeleton
        }
        self.assertTrue(added, "the fixture must have a bar the melody never enters")
        for bar, _beat in added:
            self.assertNotIn(bar, melody_bars, f"bar {bar} has notes and was added to")

    def test_every_added_position_is_one_the_tune_is_silent_at(self):
        """The rule the union follows **inside** a melody bar: only where the tune is silent.

        The bar-level exception was the whole of the old rule, and it was the bar because a
        beat-level union could not tell a position the tune *skips* from one it merely
        *holds*. The default grid now generates at each bar's own subdivision, so the unit
        is the position and both refusals are stated rather than implied: a position the
        tune writes is left to the note, and a position it is still holding is not a slot
        at all (§9.2).

        Swept over heads rather than argued, so a change that let a generated
        chord land under a sounding note fails here instead of moving a count. The heads are
        `tests.support.sweep_head_paths()` - the rule is position-level and about the metre,
        so three of them answer it, and `synthetic_cut_time` and the waltz between them hold the
        held-note and the skip cases.
        """
        checked = 0
        for path in sweep_head_paths():
            with self.subTest(head=os.path.basename(path)):
                head = load_musicxml(path)
                written = {
                    (bar, round(beat, 6))
                    for _t, bar, beat, _d in head_skeleton(head, None)
                }
                steps, _head, _notes = arranged(path)
                for step in steps:
                    bar, beat = step.bar or 0, step.beat or 0.0
                    if (bar, round(beat, 6)) in written:
                        continue
                    checked += 1
                    self.assertEqual(
                        melody_state(head.notes, bar, beat),
                        "silent",
                        f"bar {bar} beat {beat} was added under a "
                        f"sounding note: {step.tab_line()}",
                    )
        self.assertGreater(checked, 0, "no position was added anywhere")

    def test_a_melody_less_bar_with_no_harmony_behind_it_adds_nothing(self):
        """The bar-level rule never guesses a chord, which is the invariant that matters most.

        `chord_at` forward-fills, so a bar the melody never enters inherits the last change
        before it - bar 2 of `synthetic_repeat_slash` states the chord that was already in
        force. But a bar with **nothing** behind it has no chord to inherit, and
        `chord_slots` skips the position rather than inventing one. Measured on a head whose
        only harmony is absent: the melody-less bar produces no step, so the rule adds a bar
        the *timeline* can speak for and stays silent where it cannot.

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

        **The bar half of the default grid's change, and the count is no longer the claim.**
        A bar the melody never enters is still the only thing the union adds *wholesale*;
        the positions it adds inside a bar the tune occupies come from the bar's own
        subdivision, so the step count is no longer the skeleton's. What these two fixtures
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
        wherever a named grid ran. The default grid's silence was the only thing
        withholding the bar from it, and `freddie` is the pre-existing witness: under the
        default the walk now reaches **exactly** the bars `freddie` reaches, no more and no
        fewer.

        **Bars 6 and 7 still get no thumb note, and that is a different issue.**
        `place_bass` refuses them for the reason `docs/open-issues.md` **item 2** measures
        as dominant - no octave of the walk's pitch below the shape - and it refuses them
        identically under `chord:freddie`, before and after this change. Asserting a thumb note
        in bar 6 would be asserting item 2's fix, which is deliberately not built. So the
        claim is about which bars the walk *visits*, not which it can place a note in.
        """
        def walked(grid):
            steps, _head, _notes = arrange_xml_head(
                RAINY_DAY, texture="chord2", bass="root,5th,approach,nearest", grid=grid
            )
            return {s.bar for s in steps}

        head = load_musicxml(RAINY_DAY)
        melody_bars = {n.bar for n in head.notes}
        every = walked("chord:every_note")
        named = walked("chord:freddie")
        self.assertEqual(every, named, "the default withholds a bar the named grid walks")
        for bar in every - melody_bars:
            self.assertNotIn(bar, melody_bars)

    def test_the_union_adds_exactly_the_positions_without_a_note(self):
        """The two lists are disjoint where it matters, and the union is their sum.

        Stated as a count rather than eyeballed, because the claim is arithmetic: every
        grid position either already had a melody note or was added. `chord_slots` returns
        the grid's positions alone and `_merge_chord_slots` does the union, so this
        measures the two separately and checks the arithmetic rather than trusting either.
        """
        melody = self._melody_positions(self.rainy)
        chords = self._chord_positions(self.rainy, "chord:freddie")
        added = chords - melody
        self.assertGreater(
            len(added), 0,
            "the fixture must actually have positions with no melody note",
        )
        # A position with both is one slot, not two, and the melody slot wins it — so the union
        # is exactly the two sets, and its size is the arithmetic the step loop then sees.
        self.assertEqual(len(chords), len(chords & melody) + len(added))
        self.assertEqual(len(melody | chords), len(melody) + len(added))

    def test_every_named_grid_places_something(self):
        """Every named pattern places at least one chord in this head's own metre.

        The point of the grid is that a position the melody never enters is still
        reachable: a figure with no note to hang on must place its chord anyway, and a
        pattern that places **nothing anywhere** is refused by `grid_allowed` rather than
        quietly returning an empty part - so what is left here is the patterns that fit.
        """
        for grid in ("chord:every_note", "chord:freddie", "chord:charleston",
                     "chord:joe_pass", "chord:final_and"):
            with self.subTest(grid=grid):
                self.assertTrue(
                    self._chord_positions(self.rainy, grid),
                    f"grid={grid} places nothing at all",
                )

    def test_a_stab_is_never_a_whole_note(self):
        """The duration is the grid's, not the melody note's — which is the point.

        `chord:freddie` is 0.5 throughout — one notated beat on this 2/2 fixture. A stab
        that inherited the melody's length would be a whole note on a bar the melody
        holds, which is the confusion item 1 records.

        **The finer sets are the grid's own spacing and not a second rule.** `every_note`
        generates at each bar's own subdivision now, so a bar of eighths spaces its stabs
        a quarter of a whole note apart and a bar of sixteenths an eighth —
        `{0.5, 0.25}` on this head; and `chord:joe_pass` names the *ands*, so the
        distance to the next position is half a beat, `{0.25, 0.5}`. One rule producing
        three numbers is what makes "the grid decides" a claim rather than a coincidence.
        """
        for grid, expected in (("chord:every_note", {0.5, 0.25}),
                               ("chord:freddie", {0.5}),
                               ("chord:joe_pass", {0.25, 0.5})):
            with self.subTest(grid=grid):
                durations = {round(s[5], 6) for s in chord_slots(self.rainy, grid=grid)}
                self.assertEqual(durations, expected, f"grid={grid}")
                # And never a whole note, whichever grid asked.
                self.assertNotIn(1.0, durations, f"grid={grid} produced a whole note")

    def test_a_position_with_no_chord_in_force_is_skipped(self):
        """Never guessed: bar 1 beat 1 of `synthetic_cut_time` is a rest under no harmony.

        The file writes a quarter rest, and the first `<harmony>` arrives on beat 1.5, so
        beat 1.0 has neither a note nor a chord. `chord_at` returns `None` and the position
        is dropped rather than filled with the chord arriving half a beat later.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertIsNone(chord_at(head.chords, 1, 1.0))
        first = min(beat for bar, beat in self._chord_positions(head, "chord:freddie")
                    if bar == 1)
        self.assertGreater(first, 1.0, "a position with no harmony was filled in")

    def test_the_singing_route_is_not_touched(self):
        """`parts=auto` invents no melody: a note-less position carries `None`.

        The regression that makes this necessary, and it was measured rather than
        predicted: `parse_parts("auto")` returns the **sentinel** `("auto",)`, which has
        no soprano, so testing the route on the parsed value alone classified the *default*
        arrangement as the comping route. Fourteen steps of a singing `grid=freddie`
        arrangement carried the placeholder melody before `resolve_parts` was added.

        **What is asserted is the absence of an invented pitch, not the step count.** The
        default grid now generates note-less positions of its own, and the honest report
        for one is `melody is None` — never the sentinel's `C4`.
        """
        body = harmony("C", "major") + note("C", 5)
        path = write_score(score(body, divisions=4, beats=4))
        self.addCleanup(os.unlink, path)
        singing, _head, _notes = arrange_xml_head(path)
        self.assertEqual([s.melody for s in singing if s.melody is not None], ["C5"])

    def test_a_slot_whose_melody_has_stopped_carries_no_melody(self):
        """Where no note is sounding, the slot carries `None` rather than an invention.

        Bar 6 of `synthetic_repeat_slash` follows the last melody note, so there is no tune
        under the chord. The deleted `_PLACEHOLDER_MELODY` stood in with a pitch that
        parsed but was not playing; `None` is the honest value, and the assertion is
        `assertIsNone` rather than an equality a placeholder could have satisfied — all
        30 real `C4` slots across the fixtures sat on genuinely written C4s, which is why
        equality against a sentinel could pass for the wrong reason (§9.3 step B).
        """
        slots = [s for s in chord_slots(self.rainy, grid="chord:freddie") if s[3] == 6]
        self.assertTrue(slots, "bar 6 must place its chords")
        for melody, _quality, _name, _bar, _beat, _duration in slots:
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
        self.assertEqual(melody_state(self.notes, note.bar, note.beat), "onset")

    def test_a_position_inside_a_sounding_note_reports_held(self):
        """A probe between a note's onset and its end inherits that note.

        The probe is the note's own midpoint (`duration * 2` in beats, half of the
        `duration * 4` that `melody_at` adds), so where no other note begins and this
        one is in force the answer must be "held" - asserted as *some* position on the
        fixture qualifying, because one colliding with a later onset merely drops out.
        """
        probes = [
            (written.bar, round(written.beat + written.duration * 2.0, 6))
            for written in self.notes
            if written.duration > 0
        ]
        held = [
            (bar, beat) for bar, beat in probes
            if melody_state(self.notes, bar, beat) == "held"
        ]
        self.assertTrue(held, "no position inside a sounding note reports held")

    def test_a_bar_after_the_melody_ends_reports_silent(self):
        """Bar 6 of `synthetic_repeat_slash` has chords and no tune over them."""
        for beat in (1.0, 1.5, 2.0):
            with self.subTest(beat=beat):
                self.assertEqual(melody_state(self.notes, 6, beat), "silent")

    def test_the_onset_test_rounds_the_beat_like_head_note_key(self):
        """A beat differing in the seventh decimal is the same position, not a new one.

        The rule is `HeadNote.key`'s rounding - one rule, one answer - and §9.5's
        measurement snippet (`abs(n.beat - beat) < 1e-9`) is a *different* rule that
        would call an offset of 1e-7 a separate position and report "held" here. Two
        roundings of the same beat is the disagreement `HeadNote.key`'s docstring
        exists to forbid.
        """
        note = self._integer_onset()
        self.assertEqual(melody_state(self.notes, note.bar, note.beat + 1e-7), "onset")


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
        """The comping union over `synthetic_repeat_slash`, whose melody ends before bar 6."""
        return arranged(RAINY_DAY, parts="chord", grid="chord:freddie")

    def test_a_slot_where_the_melody_stopped_carries_none(self):
        """Bar 6 sits under a chord and over no note; the step says so plainly."""
        steps, _head, _notes = self._arrange()
        silent = [s for s in steps if s.bar == 6]
        self.assertTrue(silent, "bar 6 must place its chords")
        for step in silent:
            self.assertIsNone(step.melody, step.tab_line())
            self.assertNotIn("C4", step.tab_line())
            self.assertNotIn("None", step.tab_line())

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
                melody_at(head.notes, step.bar, step.beat),
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
        renderers print blank. This is the inversion AGENTS.md trap 5 asks for - the
        premise the old assertion rested on is gone.
        """
        steps, _rescued, _notes = arrange_slots(
            [(None, "m7", "Dm7"), ("C5", "maj7", "Cmaj7")],
            [(1, 1.0, 0.5), (1, 2.0, 0.5)],
            options=ArrangeOptions(parts="auto"),
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
