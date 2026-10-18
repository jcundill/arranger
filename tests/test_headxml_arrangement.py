"""Arranging an imported head: the reduction, the metre, the texture and the palette.

These are the end-to-end claims, made with `arrange_xml_head` over the committed heads
as well as over written scores: they are what makes an imported tune a tab rather than a
parsed document. Reading the document is `test_headxml.py`.
"""

import os
import tempfile
import unittest

import arranger
from arranger import NO_CHORD
from arranger.options import ArrangeOptions
from arranger.slots import arrange_slots
from headxml import (
    Head,
    arrange_xml_head,
    head_skeleton,
    load_musicxml,
    melody_at,
)
from tabscore import score_events, substitute_steps
from tests.support import (
    BUT_NOT_FOR_ME,
    I_WAS_DOING_ALL_RIGHT,
    RAINY_DAY,
    TENOR_MADNESS,
    TROUBLE_IN_MIND,
    WALTZ,
    harmony,
    note,
    rest,
    score,
    write_score,
)


class TestReductionAndArranging(unittest.TestCase):
    """Slots, voicings, and the round trip back out through the exporter."""

    def load(self, measures: str, **kwargs) -> Head:
        return load_musicxml(self.path(measures, **kwargs))

    def path(self, measures: str, **kwargs) -> str:
        """A temp file holding the score, cleaned up when the test ends."""
        path = write_score(score(measures, **kwargs))
        self.addCleanup(os.unlink, path)
        return path

    def test_the_eighth_grid_thins_the_line(self):
        """A slot's beat is quantised to the grid, and the grid is what the
        voicings are spaced on."""
        # divisions=8, so a quarter is 8 and a 4/4 bar is 32 of them.
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8) + note("F", duration=8)
            + note("G", duration=8) + note("A", duration=8),
            divisions=8,
        )
        # Four quarter notes fill the bar: beats 1, 2, 3, 4, which both grids keep.
        self.assertEqual([s[2] for s in head_skeleton(head)], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual([s[2] for s in head_skeleton(head)], [1.0, 2.0, 3.0, 4.0])

    def test_the_strategy_no_longer_changes_which_notes_are_played(self):
        """Four eighths a bar sound once under **every** setting, not just `eighths`.

        **This inverts the density test that stood here**, which asserted that a coarser
        grid kept strictly fewer slots - `beats` dropping the notes between the beats.
        That was the grid doing a melody reduction, which is what cost 24 notes on the
        committed triplet head, and it is gone: `--skeleton` is a melody-*selection* flag
        and no setting of it removes a note of the tune.

        The density decision that this test used to make is not lost, it **moved**: where
        chords fall is now the rhythm axis's question rather than this flag's, and it is
        not built yet. Until it is, every setting plays the tune and differs only in
        nothing at all - which is the honest state of the flag and the reason it wants a
        floor (`beats` / `eighths` / `sixteenths` are placeholders for that axis) rather
        than five live densities.
        """
        # Four of eight divisions is an eighth, so four of them are a half bar.
        head = self.load(
            harmony("C", "major")
            + note("E", duration=4) + note("F", duration=4)
            + note("G", duration=4) + note("A", duration=4),
            divisions=8,
        )
        self.assertEqual([s[2] for s in head_skeleton(head)], [1.0, 1.5, 2.0, 2.5])

    def test_every_written_note_keeps_the_beat_it_was_written_on(self):
        """No note of the tune is moved, merged, or dropped by the reduction.

        **This is the model, stated in one assertion.** `--skeleton` is a
        *melody-selection* flag: it says which notes the soprano is asked to sound, and
        the answer is every one of them, down to the floor. It is **not** a spacing
        rule, and where chords fall is a separate axis with its own question.

        The previous behaviour quantised every note to a grid, which cost 24 of 110 notes
        on the committed triplet head - 11 in the tuplet bars and **13 in the straight
        ones** - because two notes closer together than the grid shared a slot and the
        `pick` rule silently dropped one. A note of the tune going missing is worse than
        a chord sitting slightly off a column of the staff, and the loss was invisible.
        """
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8, tuplet=True) + note("F", duration=8, tuplet=True)
            + note("G", duration=12),
            divisions=12,
        )
        # The tuplets are marked as written, and they are a third of a beat apart.
        self.assertEqual([n.tuplet for n in head.notes], [True, True, False])
        beats = [beat for _t, _bar, beat, _d in head_skeleton(head)]
        # **The slot carries the note's own float, and this assertion was inverted to
        # say so.** It used to compare against `round(n.beat, 6)`, because the slot
        # stored the rounded beat: `head_skeleton` grouped notes by a six-place key
        # and then emitted that key as the position. A triplet is where that costs
        # something - `1/3` has no exact binary form, so rounding the first note of
        # a triplet DOWN and the next UP made the gap between them longer than the
        # note itself, and the surplus was written as a rest. Measured on the
        # committed triplet head: 13 such rests, and none since. See
        # `test_a_triplet_head_writes_no_rest_it_cannot_express`, which asserts that
        # on the real score rather than on this fixture's hand-written durations.
        self.assertEqual(beats, [n.beat for n in head.notes])

    def test_a_triplet_head_writes_no_rest_it_cannot_express(self):
        """The end-to-end consequence, on the committed triplet score.

        The defect was invisible in the tab and glaring in the score. `head_skeleton`
        emitted six-place-rounded beats, which made the gap between two triplet notes
        longer than the notes in it; `tabscore.score_events` caps a note at the length the
        file wrote, so the surplus became a **rest of about 1e-06 quarters** - a
        length MusicXML cannot express, and which music21 inflates to a whole
        triplet note. Measured on `synthetic_triplets.mxl`: **13 such rests and
        133 events before, 0 and 120 after.** Each one put an extra note inside a
        `3` bracket and stretched the bar, so "Trouble in Mind" bar 1 came out two
        beats long instead of one.

        Asserted on the events rather than on the XML, because that is where the rest
        is born and it needs no optional dependency to see it.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        # The fixture must actually be a triplet head, or this proves nothing.
        tuplets = sum(1 for n in head.notes if n.tuplet)
        self.assertGreater(tuplets, 0, "this fixture must contain triplets")

        slots = head_skeleton(head)
        steps, _rescued, _notes = arrange_slots(
            [s[0] for s in slots], [(s[1], s[2], s[3]) for s in slots]
        )
        events, _pickup = score_events(substitute_steps(steps), head.beats_per_bar, True,
                                  head.beat_type)
        # Every rest is a real one: at least a sixteenth. The sixteenth is the
        # shortest event `score_events` will write (`_MIN_EVENT_LENGTH`), so anything
        # shorter is a rounding artefact rather than silence the score contains.
        unexpressible = [
            length for step, _strikes, length in events
            if step is None and length < 0.25 - 1e-9
        ]
        self.assertEqual(unexpressible, [])

    def test_a_tuplet_head_keeps_every_note_on_every_grid(self):
        """The end-to-end claim, on the committed score rather than a hand-built one.

        A hand-built fixture is fine for a rule but not for a count: the point here is
        that the reduction does not *lose notes of the tune*, and the only honest way
        to say that is against a committed score's note count. `synthetic_triplets.mxl`
        carries 96 tuplets among the 108 notes the repeat plays, and the equality below
        asserts that the reduction keeps every one of them.

        The written body is four bars and ending 1 is two more, so the tuplet-bearing
        bars in the body are played twice; the endings are played once each.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertEqual(len(head_skeleton(head)), len(head.notes))
        self.assertEqual(sum(1 for n in head.notes if n.tuplet), 96)

    def test_a_chord_change_sounds_under_every_note_it_governs(self):
        """Two chords in the bar, six notes, and the harmony changes part-way through.

        **This inverts the test that stood here**, which asserted the `chords` strategy
        gave one slot per chord change - two slots for these six notes. That was a
        reduction of the melody, which is the thing this module no longer does: the
        soprano plays the tune. What survives is the part of it that was not about
        reduction at all - **the harmony in force is right on every note**, and the
        change lands where the file put it rather than on a downbeat.
        """
        head = self.load(
            harmony("C", "major") + note("E") + note("F") + note("G")
            + harmony("F", "dominant") + note("A") + note("B"),
        )
        slots = head_skeleton(head)
        # Five written notes, five slots - none of them merged away.
        self.assertEqual(len(slots), len(head.notes))
        # The first three are under Cmaj and the last two under F7.
        self.assertEqual([s[0][2] for s in slots],
                         ["Cmaj", "Cmaj", "Cmaj", "F7", "F7"])
        # And each note keeps the beat it was written on, so the change is heard at the
        # fourth quarter (beat 4) rather than being snapped to a grid position.
        self.assertEqual([s[2] for s in slots], [1.0, 2.0, 3.0, 4.0, 5.0])

    def test_a_leading_rest_still_takes_up_its_time(self):
        """A rest is not a note, but it is time, and the cursor must cross it.

        Bar 1 of "the synthetic cut-time head" is a quarter rest and then three quarter notes.
        The rest is skipped - it is not melody - but its *length* still has to be
        added to the cursor, or every note after it is read a beat early. That put
        the F4 on beat 1.0 instead of 1.5, which moved the whole head up a beat and
        wrote the bar as three chords instead of a rest and three.

        The distinction is between a note that carries no time (a grace note, which
        borrows the length of the note it decorates and must not be added or it
        would be counted twice) and one that does.
        """
        head = self.load(
            rest(duration=8)
            + harmony("C", "major")
            + note("E", duration=8) + note("F", duration=8) + note("G", duration=8),
            divisions=8,
        )
        # A 4/4 bar: the rest is one quarter, so the E is on beat 2.
        self.assertEqual([n.beat for n in head.notes], [2.0, 3.0, 4.0])
        # And it is counted as skipped rather than dropped in silence. The counts
        # are per reason and phrased as a tally, so this matches on the words.
        self.assertTrue(
            any("rests and unpitched notes" in entry for entry in head.skipped),
            head.skipped,
        )

    def test_a_rest_mid_bar_does_not_move_the_notes_after_it(self):
        """A rest in the middle of a bar holds its place like any other duration."""
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8) + rest(duration=8) + note("F", duration=8),
            divisions=8,
        )
        # E on beat 1, the rest occupies beat 2, F on beat 3.
        self.assertEqual([n.beat for n in head.notes], [1.0, 3.0])

    def test_a_cut_time_head_opens_on_the_beat_its_first_note_is_written_on(self):
        """The real 2/2 head begins after a rest, and the loader must say so.

        Read on the committed music21 score rather than a hand-built one, because
        the leading quarter rest is what a notation program actually writes for this
        head and a synthetic fixture is the only way to miss it.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        first = head.notes[0]
        self.assertEqual((first.bar, first.beat), (1, 1.5))
        # A head that starts part-way into its first bar has a pickup, which is what
        # makes the renderers write that bar short rather than inventing a downbeat.
        events, pickup = score_events(
            substitute_steps(
                arrange_xml_head(BUT_NOT_FOR_ME)[0]
            ),
            head.beats_per_bar,
            True,
            head.beat_type,
        )
        self.assertAlmostEqual(pickup, 1.0, places=6)

    def test_the_last_eighth_of_a_cut_time_bar_is_not_folded_onto_the_second_beat(self):
        """A 2/2 bar's eighths run to 2.5, and every one of them is kept.

        This is the regression for the clamp in `_slot_key`, which limited a slot
        to `beats_per_bar`. In cut time the bar is two beats wide but four quarters
        long, so the fourth quarter sits at beat **2.5** - half a beat past the
        count. Every one of those notes was folded onto beat 2.0, collided with the
        note already there, and was dropped by the `pick` rule: 13 of the 80 notes
        of "the synthetic cut-time head", silently. A note of the tune is worth more than a
        tidy beat number.
        """
        # divisions=8, so a quarter is 8 and a 2/2 bar is 32 of them - four quarters.
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8) + note("F", duration=8)
            + note("G", duration=8) + note("A", duration=8),
            divisions=8, beats=2, beat_type=2,
        )
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        # Read raw, the fourth quarter really is past the beat count...
        self.assertEqual([n.beat for n in head.notes], [1.0, 1.5, 2.0, 2.5])
        # ...and the eighth grid keeps all four rather than folding the last onto 2.0.
        self.assertEqual(
            [s[2] for s in head_skeleton(head)], [1.0, 1.5, 2.0, 2.5]
        )

    def test_a_note_past_the_bar_line_is_still_pulled_back_inside(self):
        """The clamp still does its job, which is now a narrower one.

        **The job changed with the model, and the assertion had to change with it.**
        This used to be about a note that *rounded onto* the bar line: `eighths` put the
        grid at 0.5, a note at 2.75 rounded to 3.0, and 3.0 is the bar line of a 2/2 bar,
        so it was pulled back to the last eighth inside - 2.5.

        There is no grid now, so nothing rounds: every note keeps the beat it was
        written on, and a note written past the bar line is simply **over the line**
        rather than rounding onto it. The clamp is still what stops that, and it is still
        load-bearing - but what it pulls back to is the bar line approached from inside,
        not the last grid step.
        """
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8) + note("F", duration=8)
            + note("G", duration=6) + note("A", duration=2),
            divisions=8, beats=2, beat_type=2,
        )
        beats = [s[2] for s in head_skeleton(head)]
        # The bar is two beats wide, so its last eighth is 2.375 and the bar line 3.0.
        # Every note is where the file put it, none of them on the line, and the last
        # one is still there rather than folded onto an earlier slot.
        self.assertEqual(beats, [n.beat for n in head.notes])
        self.assertTrue(all(b < head.beats_per_bar + 1.0 for b in beats), beats)
        self.assertEqual(max(beats), 2.375)

    def test_a_cut_time_head_keeps_every_note_of_the_tune(self):
        """No note of a real 2/2 head is lost to the reduction.

        Pinned on the committed music21 score rather than a hand-built one, because
        the bug only appears on a file whose quarters land past the beat count - the
        first three of the 80 notes are enough to see the meter, and all 80 are what
        the arrangement is supposed to carry.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        # The last quarter of a 2/2 bar is beat 2.5, so these exist in the file...
        self.assertTrue(any(n.beat > head.beats_per_bar for n in head.notes))
        # ...and the eighth grid must not have folded them onto the second beat.
        slots = head_skeleton(head)
        self.assertTrue(any(beat > head.beats_per_bar for _t, _b, beat, _d in slots))
        # Nothing may land on or past the bar line either.
        for _triple, _bar, beat, _duration in slots:
            self.assertLessEqual(beat, head.beats_per_bar + 1.0 - 0.5)

    def test_a_slash_bass_stays_in_the_chord_name(self):
        """The bass rides in the name, as the corpus path keeps it, and rule B
        promotes a triad whose bass is its own seventh."""
        head = self.load(harmony("A", "minor", bass="G") + note("E"))
        _melody, quality, name = head_skeleton(head)[0][0]
        self.assertEqual(quality, "m7")  # A minor triad over G is a minor 7th
        self.assertEqual(name, "Am/G")

    def test_a_slash_chord_is_voiced_with_its_bass_preferred(self):
        """A slash chord is honoured as a *preference*, by the shared step loop.

        The candidate whose lowest pitch is nearest the bass is preferred, exactly
        as the corpus path does - which is the point of sharing `arrange_slots`
        rather than reimplementing it here.

        The melody-bearing step is the one the claim is about; the note-less positions
        the default grid generates in the same bar are comps of the same chord, so they
        are held to the same preference rather than excepted from it.
        """
        steps, _head, _notes = arrange_xml_head(
            self.path(harmony("D", "dominant", bass="C") + note("F", octave=4)),
        )
        sung = [s for s in steps if s.melody]
        self.assertEqual(len(sung), 1)
        for step in steps:
            self.assertEqual(step.chord, "D7/C")
            # The shape's bottom note is the C, or within a tone of it.
            bottom = min(step.voicing.midi_notes()) % 12
            self.assertIn(bottom, (0, 1, 11), step.tab_line())

    def test_melody_under_no_chord_becomes_a_melody_only_step(self):
        """A note with no harmony is voiced alone, not under an invented chord."""
        path = write_score(score(note("C", octave=5) + harmony("C", "major") + note("E")))
        self.addCleanup(os.unlink, path)
        steps, _head, _notes = arrange_xml_head(path)
        self.assertTrue(steps[0].melody_only)
        self.assertEqual(steps[0].chord, NO_CHORD)
        self.assertFalse(steps[1].melody_only)

    def test_every_step_obeys_the_playability_invariant(self):
        """An imported head is voiced by the same engine, so it obeys the same
        rules as any other arrangement: playable frets, and the melody on top."""
        head = self.load(
            harmony("D", "minor-seventh") + note("A", octave=5)
            + harmony("G", "dominant") + note("B", octave=4)
            + harmony("C", "major-seventh") + note("B", octave=4)
        )
        slots = head_skeleton(head)
        steps, _rescued, _notes = arrange_slots(
            [s[0] for s in slots], [(s[1], s[2], s[3]) for s in slots]
        )
        self.assertEqual(len(steps), 3)
        for step in steps:
            frets = [f for f in step.voicing.frets if f >= 0]
            self.assertTrue(frets)
            self.assertLessEqual(max(frets), 18)
            # The melody is the highest pitch the shape sounds.
            self.assertEqual(max(step.voicing.midi_notes()), step.voicing.midi_notes()[-1])

    def test_an_arrangement_round_trips_through_the_exporter(self):
        """Export a head with `tabxml` and read it back with `headxml`.

        The two halves of the MusicXML support in this library, and the round trip
        is the only test that can catch one writing a chord the other cannot read.
        It is skipped without music21, which is the exporter's own optional extra.

        It pins the **octave** as well: the exporter writes the guitar part an octave
        above what it sounds and declares the transposition, and the assertion below
        that the reloaded melody equals the sounding pitches only holds because the
        importer undoes that shift. Break either half and this goes an octave out.
        """
        try:
            import music21  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("music21 not installed")
        from arranger import format_musicxml

        source = write_score(
            score(harmony("D", "minor-seventh") + note("A", octave=5)
                  + harmony("G", "dominant") + note("B", octave=4)
                  + harmony("C", "major-seventh") + note("B", octave=4))
        )
        self.addCleanup(os.unlink, source)
        steps, _head, _notes = arrange_xml_head(source)

        exported = write_score(format_musicxml(steps, title="Round trip"), suffix=".musicxml")
        self.addCleanup(os.unlink, exported)
        reloaded = load_musicxml(exported)

        # The chords survive, which is the point: the exporter writes a chord
        # music21 cannot classify as `<kind text="...">other</kind>`, and the
        # importer reads exactly that back through ChordParser.
        self.assertEqual([n.chord for n in reloaded.notes], [s.chord for s in steps])
        # And the melody does, so the reloaded head is the same tune. The exporter
        # wrote it an octave high and declared the transposition; the importer read
        # it back at concert pitch, which is what makes these two lists equal.
        self.assertEqual([n.pitch for n in reloaded.notes],
                         [max(s.voicing.midi_notes()) for s in steps])


class TestTheHeadRequestAsOneValue(unittest.TestCase):
    """`options=` and the keyword spellings are two spellings of one request."""

    def test_options_and_keywords_produce_the_same_arrangement(self):
        """The object entry point must not be a second arrangement path."""
        keywords = arrange_xml_head(BUT_NOT_FOR_ME, texture="chord1")[0]
        as_object = arrange_xml_head(
            BUT_NOT_FOR_ME,
            options=ArrangeOptions(texture="chord1"),
        )[0]
        self.assertEqual(
            [step.tab_line() for step in keywords],
            [step.tab_line() for step in as_object],
        )

    def test_the_two_spellings_cannot_be_combined(self):
        """A caller who passes both has a bug, and hears about it."""
        with self.assertRaises(ValueError):
            arrange_xml_head(
                BUT_NOT_FOR_ME,
                texture="chord1",
                options=ArrangeOptions(texture="targets"),
            )


class TestTheMetreHasADenominator(unittest.TestCase):
    """`beat` is a notated beat, and `beats_per_bar` is not the factor that produces one.

    `onset / divisions` is a count of **quarters** and a beat is `4 / beat_type` of them,
    so a note's beat is `1 + onset/divisions * beat_type/4`. Written as
    `beats_per_bar / 4` the factor agrees exactly when the numerator equals the
    denominator - 4/4 and 2/2 - so the
    whole suite passed while every note of the 3/4 waltz was placed a quarter of a beat
    early: its six written eighths read 1.0 … 2.875 in a bar three beats wide, and
    `--musicxml` scaled them by another 0.75 on every round trip.

    These are the tests that fail without that fix: one bar each of 3/4, 2/4 and 6/8 -
    2/4 and 6/8 being the metres where the *old* factor went the other way - and the
    fixture itself, which is the head that made it visible.
    """

    def load(self, measures: str, **kwargs) -> Head:
        path = write_score(score(measures, **kwargs))
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    @staticmethod
    def eighths(count: int) -> str:
        """`count` written eighths, in divisions of six (the waltz's own)."""
        steps = ("C", "D", "E", "F", "G", "A")
        return "".join(note(step, duration=3) for step in steps[:count])

    def test_a_three_four_bar_of_eighths_is_three_beats_wide(self):
        """Six eighths are beats 1.0 … 3.5, not 1.0 … 2.875 - and they reach the barline.

        `beats_per_bar / 4` is 0.75 here, so the old reading made the bar 2.25 beats of
        music wide while its barlines were still drawn three apart: a hole of music at
        the end of every bar, which is what the tab staff showed. The arrival of the last
        note's *end* on 4.0 asserts that in one number.
        """
        head = self.load(
            harmony("C", "major") + self.eighths(6),
            divisions=6, beats=3, beat_type=4,
        )
        self.assertEqual((head.beats_per_bar, head.beat_type), (3, 4))
        self.assertEqual([n.beat for n in head.notes], [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        last = head.notes[-1]
        self.assertAlmostEqual(
            last.beat - 1.0 + last.duration * head.beat_type,
            head.beats_per_bar,
            places=6,
        )

    def test_a_pickup_of_eighths_starts_where_the_rest_leaves_off(self):
        """An eighth rest then five eighths: 1.5 … 3.5 - bar 1 of the waltz, which read 1.375."""
        head = self.load(
            harmony("C", "major") + rest(duration=3) + self.eighths(5),
            divisions=6, beats=3, beat_type=4,
        )
        self.assertEqual([n.beat for n in head.notes], [1.5, 2.0, 2.5, 3.0, 3.5])


    def test_a_two_four_bar_keeps_one_beat_to_the_quarter(self):
        """2/4: a quarter note is one beat, not half of one.

        The old factor read the bar as two *quarters* long (`beats_per_bar / 4` = 0.5 of a
        beat per quarter), so a bar of two quarter notes came out as beats 1.0 and 1.5 -
        music in the first half of a bar whose signature says two whole beats.
        """
        head = self.load(
            harmony("C", "major") + note("E", duration=4) + note("F", duration=4),
            divisions=4, beats=2, beat_type=4,
        )
        self.assertEqual([n.beat for n in head.notes], [1.0, 2.0])

    def test_a_six_eight_bar_counts_its_beats_in_eighths(self):
        """6/8: six eighths are beats 1 … 6, and the bar is six beats wide.

        The metre where the count is *larger* than the denominator, so the old factor
        overshoots instead of undershooting: 6/4 = 1.5 beats per quarter put six eighths
        on 1.0, 1.75, 2.5, 3.25, 4.0, 4.75 - inside a bar the file calls six wide, so
        nothing looked wrong until the notes and the barlines were read together.
        """
        head = self.load(
            harmony("C", "major") + self.eighths(6),
            divisions=6, beats=6, beat_type=8,
        )
        self.assertEqual((head.beats_per_bar, head.beat_type), (6, 8))
        self.assertEqual([n.beat for n in head.notes], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    def test_the_committed_waltz_puts_its_eighths_on_the_eighth(self):
        """The fixture itself: bars 1 to 3, an eighth rest then eighths.

        Pinned on the committed score rather than a hand-built one because this is the
        head that made the defect visible, and because it is the only one of the seven
        whose metre can see it at all.
        """
        head = load_musicxml(WALTZ)
        self.assertEqual((head.beats_per_bar, head.beat_type), (3, 4))
        onsets = {bar: [n.beat for n in head.notes if n.bar == bar] for bar in (1, 2, 3)}
        self.assertEqual(onsets[1], [1.5, 2.0, 2.5, 3.0, 3.5])
        self.assertEqual(onsets[2], [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        self.assertEqual(onsets[3], [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])

    def test_no_onset_of_any_committed_head_is_pushed_past_its_bar_line(self):
        """The other direction, on all six scored fixtures.

        A factor read the wrong way up *stretches* the bar instead of squeezing it - the
        mistake `docs/renderers.md` records twice, four quarters to the bar written as
        one - so the notes leave the bar they were written in. Every onset is inside its
        own bar, whatever the metre: `1 <= beat < beats_per_bar + 1`.
        """
        for path in (BUT_NOT_FOR_ME, I_WAS_DOING_ALL_RIGHT, RAINY_DAY, TENOR_MADNESS,
                     TROUBLE_IN_MIND, WALTZ):
            with self.subTest(head=os.path.basename(path)):
                head = load_musicxml(path)
                limit = head.beats_per_bar + 1.0
                self.assertTrue(
                    all(1.0 <= n.beat < limit for n in head.notes),
                    [n.beat for n in head.notes if not 1.0 <= n.beat < limit],
                )

    def test_the_waltz_keeps_its_onsets_through_a_round_trip(self):
        """Export → read back leaves the beats where they are, bar 1 excepted.

        The compounded symptom, and the one a user meets: before the fix each cycle
        scaled every onset by another 0.75, so the file's eighths came back at 1.0,
        1.281, 1.562 … - a head that shrinks by a quarter every time it is written out
        and read in.

        **Bar 1's pickup is excluded because the exporter loses it, which is a separate
        defect and not this one.** Measured: the written bar 1 is an eighth rest then five
        eighths (1.5 … 3.5), and the exported-then-re-read bar 1 is five eighths from 1.0,
        the rest dropped rather than written. That is wrong under either spelling of the
        conversion, so it is recorded rather than encoded here.

        **The count is re-scoped, not kept** (AGENTS.md trap 5). It used to assert
        `len(again.notes) == len(head.notes)`, which was true only because the default grid
        produced no steps in a bar the melody never entered - the silence
        `docs/open-issues.md` item 1 measures. Those bars are arranged now, and the
        exporter has always written a comping step as a note: `freddie` and `joe_pass`
        already round-tripped **22 and 27** extra beats on this head before this change.
        The claim that actually matters is the one the assertion was a proxy for - every
        written beat comes back at the same beat - and that still holds exactly. What is
        asserted instead is that **every extra is a position the tune is silent at**.

        **The set is empty on this head now, and that is the corrected metre.** The one
        position the default grid added in a later bar was bar 7 beat 1.0, the release
        instant of bar 6's D4: reading the duration as `duration * 4` in the starting bar
        put the end before the bar line, so the grid called it silent. A 3/4 beat is a
        quarter, the note ends exactly at bar 7 beat 1.0, and the release instant is
        still held - so there is nothing to add. The loop remains because the *rule* is
        what the test states, not the count.
        """
        try:
            import music21  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("music21 is not installed")
        from tabxml import format_musicxml

        head = load_musicxml(WALTZ)
        steps, _head, _notes = arrange_xml_head(WALTZ)
        document = format_musicxml(
            steps,
            title=head.title,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
            fifths=head.key_fifths,
            mode=head.key_mode,
        )
        handle, out = tempfile.mkstemp(suffix=".musicxml")
        os.close(handle)
        self.addCleanup(os.unlink, out)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(document)

        again = load_musicxml(out)
        self.assertEqual((again.beats_per_bar, again.beat_type), (3, 4))
        written = [n for n in head.notes if n.bar >= 2]
        reread = [n for n in again.notes if n.bar >= 2]
        # Every beat the file wrote comes back at the same beat - the claim. A set
        # containment rather than a pairwise walk: the copy now carries the default grid's
        # generated positions too, so zipping the two lists in order would compare a written
        # note against a comping step and call the *extra* a moved note.
        original = {(n.bar, round(n.beat, 6)) for n in written}
        surviving = {(n.bar, round(n.beat, 6)) for n in reread}
        self.assertTrue(original <= surviving, sorted(original - surviving)[:5])
        # And every extra is a position the tune is silent at - the rule the default grid
        # generates by, restated through a round trip. Empty on this head is a pass: the
        # one position it used to add was a release instant, now correctly held.
        for bar, beat in sorted(surviving - original):
            self.assertIsNone(
                melody_at(head, bar, beat),
                f"bar {bar} beat {beat} gained a beat under a sounding note",
            )


class TestANoteHeldAcrossABarLine(unittest.TestCase):
    """A tie into the next bar is one note, so the next bar's downbeat holds it.

    `synthetic_cut_time.mxl` ends bar 2 with an E♭4 tied to bar 3's first eighth. The
    importer merges the halves into one `HeadNote`, but the default grid still names
    bar 3's downbeat as a position - and the comping union used to call the tune silent
    there and fill it with a fresh Cm7 shape. That is a re-strike of a note the left
    hand is still holding, which is what `But_Not_for_Me` demonstrated.
    """

    def test_the_held_note_is_not_restruck_at_the_next_downbeat(self):
        steps, head, _notes = arrange_xml_head(BUT_NOT_FOR_ME)
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        at = {
            (step.bar, round(step.beat or 0.0, 6)): step
            for step in steps
            if step.bar is not None and step.beat is not None
        }
        self.assertNotIn((3, 1.0), at, "the held note was re-struck at bar 3")
        held = at[(2, 2.5)]
        self.assertEqual(held.melody, "Eb4")
        self.assertIsNotNone(held.duration)
        # The note reaches an eighth into bar 3, so its written length is more than
        # the gap to the bar line (0.25 whole notes in cut time).
        self.assertGreater(held.duration or 0.0, 0.25)
        # The next written note is still there: the hold did not swallow the tune.
        self.assertEqual(at[(3, 1.5)].melody, "F4")


class TestHeadTexture(unittest.TestCase):
    """
    The target-note texture over a real written head.

    `synthetic_cut_time.mxl` is the fixture that matters here: it is in **cut time**, so
    a 2/2 bar has two notated beats and beat 3 does not exist. A rule that read the
    metre as 4/4 would put a full chord on a beat the score does not have - the same
    class of bug as the cut-time quarter-note errors already fixed in this module, and
    the reason `arrange_xml_head` passes `head.beats_per_bar` through rather than
    leaving the renderer to assume.
    """

    def test_the_notated_metre_decides_which_beats_are_targets(self):
        """
        In 2/2 only the downbeat is a target, and the later beats are fills.

        Asserted through the real score rather than a hand-built one, because the metre
        is the thing under test and a hand-built fixture would supply its own.
        """
        steps, head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, texture="targets")
        self.assertTrue(steps)
        self.assertEqual(head.beats_per_bar, 2, "this fixture must be in cut time")
        for step in steps:
            if step.beat is None:
                self.assertEqual(step.role, "target")
            elif abs(step.beat - 1.0) < 1e-6:
                self.assertEqual(step.metric_weight, 2)
                self.assertEqual(step.role, "target")
            else:
                self.assertEqual(step.metric_weight, 0)
                self.assertEqual(step.role, "fill")

    def test_the_texture_thins_a_cut_time_head(self):
        """
        The flag does what it says on a real head, and the chords mostly survive.

        Thinner overall, with every strong beat still stated in full - the two halves
        of the claim, since thinning the harmony too would not be an arrangement.

        A strong beat is the *exception* where the only complete shape it can be given
        needs a five-fret stretch: the `targets` target palette is the four-note grips
        only, so the narrow alternative is never offered, and the step falls back to the
        melody alone. That is a target with one voice, and it is the whole reason this
        assertion is not simply "every target has four voices" - see
        `TestGripsIntersectTheTexture::test_a_target_that_cannot_be_played_becomes_the_melody_alone`.

        So the claim is the property rather than a count: **no target is left holding a
        full-span stretch**, and every demotion is a single playable note that still
        names its harmony. The count is 5 on this head and they are all the same musical
        event - Ebmaj under G4 recurs five times - so pinning a number would be pinning
        the tune rather than the rule.
        """
        uniform, _head, _n = arrange_xml_head(BUT_NOT_FOR_ME, texture="uniform")
        targets, _head, _n = arrange_xml_head(BUT_NOT_FOR_ME, texture="targets")
        self.assertEqual(len(uniform), len(targets))

        def mean_voices(steps):
            return sum(len(s.voicing.active_frets()) for s in steps) / len(steps)

        self.assertLess(mean_voices(targets), mean_voices(uniform))
        for step in targets:
            if step.role != "target" or step.melody_only:
                continue
            if step.voicing.grip == "melody":
                # Demoted: playable, and the harmony is still named above it.
                self.assertEqual(len(step.voicing.active_frets()), 1, step.tab_line())
                self.assertTrue(step.chord, "a demoted target still names its harmony")
                continue
            if step.melody is None:
                # A generated position the tune is silent at: the guitar *comps* it, and
                # a comping part's arity is `comping_arity` - three, because the soprano
                # string carries nothing here and so is free for the chord.
                self.assertEqual(len(step.voicing.active_frets()), 3, step.tab_line())
                continue
            self.assertEqual(len(step.voicing.active_frets()), 4, step.tab_line())
            # The whole point of the fallback: a complete chord survives only while it
            # stays inside the reach.
            self.assertLess(
                step.voicing.fret_span(),
                arranger.GRIP_MAX_SPAN["drop2"],
                "a target is still holding a full-span stretch: " + step.tab_line(),
            )

    def test_the_default_is_unchanged(self):
        """No flag, no texture: every step is a principal note."""
        steps, _head, _notes = arrange_xml_head(BUT_NOT_FOR_ME)
        for step in steps:
            self.assertEqual(step.role, "target")


class TestANarrowPaletteNeverLosesTheTune(unittest.TestCase):
    """A palette with no room to state a chord must not take the melody note with it.

    `texture=chord1` is the narrowest thing the texture axis can express: a chord-melody
    is the tune plus **one** chord tone, where the default states four. A palette that
    narrow answers no candidate at all for a melody the non-chord-tone table cannot
    reharmonise, unless it reaches the non-grip `duo` - so this is where a dropped note
    would show up first. "the synthetic cut-time head" bar 2 beat 2 is the smallest case: F4 over
    Ebmaj, the 9th over a plain triad.
    """

    def test_the_ninth_over_a_triad_is_voiced_rather_than_dropped(self):
        """The `maj` row reaches the narrowest two-note shape, so the step exists.

        The row is what makes F a chord tone at all - the quality is reharmonised to
        Ebadd9 rather than the plain triad being stated - and the two strings `duo` means
        sound the melody with the 3rd under it. G is the chord tone the thinnest palette
        can put there, which is what makes this a claim about the row rather than about
        which family happened to win.
        """
        steps, _head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, texture="chord1")
        bar2 = [s for s in steps if s.bar == 2 and abs((s.beat or 0) - 2.0) < 1e-6]
        self.assertEqual(len(bar2), 1, "bar 2 beat 2 is missing")
        step = bar2[0]
        self.assertEqual(step.melody, "F4")
        self.assertEqual(step.chord, "Ebmaj")
        self.assertEqual(step.harmonized_as, "Ebadd9")
        self.assertEqual(step.strategy, "extension")
        self.assertEqual(step.grip, "duo")
        # G under F, on the two strings the grip names.
        self.assertEqual(step.voicing.frets, [-1, 10, -1, 10, -1, -1])
        self.assertEqual({m % 12 for m in step.voicing.midi_notes()}, {5, 7})

    def test_no_melody_note_is_dropped_by_the_narrowest_palette(self):
        """Every one of the 80 notes is a step, at one chord tone a step and at four.

        **Membership rather than a count.** The count stopped being the claim when the
        default grid began generating positions of its own: 80 notes are 94 steps here, and
        an equality would report the *additions* as a loss. A lost note is an absence, so
        what is asserted is that no written position is missing - which is the property the
        count was a proxy for, stated directly.
        """
        for texture in ("chord1", "uniform"):
            with self.subTest(texture=texture):
                steps, head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, texture=texture)
                at = {(s.bar or 0, round(s.beat or 0.0, 6)) for s in steps}
                for written in head.notes:
                    self.assertIn(
                        (written.bar, round(written.beat, 6)), at, f"{written.note_name} went missing"
                    )

    def test_every_step_states_its_chord_at_either_arity(self):
        """`chord_unvoiced` is False throughout: every chord has a shape under it.

        A melody note under a chord symbol with nothing under it reads as the chord being
        played quietly, and `ArrangementStep.chord_unvoiced` is the field that says
        otherwise. The positive case is `test_non_chord_tones`; what this pins is that
        thinning the part does not quietly start thinning the *harmony*.
        """
        for texture in ("chord1", "uniform"):
            with self.subTest(texture=texture):
                steps, _head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, texture=texture)
                self.assertEqual(
                    [s.bar for s in steps if s.chord_unvoiced], [],
                    f"texture={texture} left a chord unstated",
                )
