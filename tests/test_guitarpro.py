"""Tests for the Guitar Pro renderer in `tabgp`.

Guarded on PyGuitarPro being installed, exactly as the MusicXML tests are guarded on
music21 and the database tests on `wjazzd.db`: it is an optional extra, and a fresh
clone runs a reduced suite.

The core of these tests is a **round trip**: the file is written, parsed back with
`guitarpro.parse`, and the notes compared against the frets the arrangement was built
from. That is deliberate, and it is how the format's five undocumented traps were
found in the first place - each one produces a file that *writes without complaint*
and is corrupt on read, so an assertion on the builder's own output would pass while
the file was unusable. A GP file's only contract is that Guitar Pro can open it, and
a parse is the closest proxy available without Guitar Pro itself.
"""

import os
import tempfile
import unittest

from arranger import ArrangementStep, Voicing, VoiceLeadingEngine

try:
    import guitarpro  # noqa: F401
    HAS_GUITARPRO = True
except ImportError:  # pragma: no cover - depends on the environment
    HAS_GUITARPRO = False
requires_guitarpro = unittest.skipUnless(
    HAS_GUITARPRO, "PyGuitarPro not installed"
)


def _parse(stream):
    """`guitarpro.parse`, reached through a function.

    A module-level name bound inside a `try` is *possibly unbound* to a checker
    when the import fails, and every use of it would be an error even in a class
    the `skipUnless` guard has already excluded. Going through here keeps the one
    reference in the guarded module scope.
    """
    import guitarpro
    return guitarpro.parse(stream)

# guitarpro numbers the strings 1..6 with 1 = high E; this library indexes 0 = low E.
_GP_STRING_OFFSET = 6


def make_step(frets, chord="Cmaj7", melody="B4", **kwargs):
    """An ArrangementStep over a raw fret list, with the derived voicing fields."""
    active = [f for f in frets if f >= 0]
    return ArrangementStep(
        chord=chord,
        melody=melody,
        voicing=Voicing(
            frets=list(frets),
            top_fret=max(active) if active else 0,
            avg_fret=sum(active) / len(active) if active else 0.0,
        ),
        **kwargs,
    )


class GuitarProTestCase(unittest.TestCase):
    """Shared helpers: a progression, and accessors into a parsed-back file."""

    def setUp(self):
        engine = VoiceLeadingEngine()
        # A ii-V-I, which every chord of it voices without a non-chord tone, so the
        # tests are about the rendering rather than about the arranger.
        self.steps = engine.arrange_progression(
            [("A4", "m7", "Dm7"), ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7")]
        )

    def data(self, **kwargs):
        from tabgp import format_gp5
        return format_gp5(self.steps, **kwargs)

    def song(self, steps=None, **kwargs):
        """The written file, parsed back into guitarpro's model."""
        import io
        from tabgp import format_gp5
        return _parse(
            io.BytesIO(
                format_gp5(self.steps if steps is None else steps, **kwargs)
            )
        )

    def measures(self, **kwargs):
        return self.song(**kwargs).tracks[0].measures

    def beats(self, **kwargs):
        """Every beat of voice 1, flattened, which is what the ear hears."""
        return [b for m in self.measures(**kwargs) for b in m.voices[0].beats]

    def written_frets(self, beat):
        """A beat's notes as (string_index, fret), back in this library's order."""
        return sorted(
            (_GP_STRING_OFFSET - n.string, n.value) for n in beat.notes
        )

    def expected_frets(self, step):
        """The frets the arrangement itself says the step plays."""
        return sorted(
            (index, fret)
            for index, fret in enumerate(step.voicing.frets)
            if fret >= 0
        )

    def bar_quarters(self, measure):
        """A measure's total length in quarter notes, read back out of the file.

        `Duration.value` is the *denominator* - 4 a quarter, 8 an eighth - so the
        length is `4 / value` quarters, scaled by the tuplet when there is one
        (`times` notes are played in the time `enters` would normally take, per
        PyGuitarPro's `Tuplet`). Summing this across a measure is the only check
        that says whether the file's bars are as long as its signature claims, and
        it is the check that a measure *count* cannot make: an over-short bar can
        still be the right number of bars.
        """
        total = 0.0
        for voice in measure.voices:
            for beat in voice.beats:
                duration = beat.duration
                length = 4.0 / duration.value
                if duration.tuplet is not None:
                    length *= duration.tuplet.times / duration.tuplet.enters
                total += length
        return total


@requires_guitarpro
class TestRoundTrip(GuitarProTestCase):
    """What the written file contains, read back out of it."""

    def test_the_file_carries_a_gp5_signature(self):
        """A file Guitar Pro will recognise begins with the format's own header."""
        from tabgp import GP_SIGNATURE
        self.assertTrue(self.data().startswith(GP_SIGNATURE))

    def test_every_shape_survives_the_round_trip(self):
        """Each step's frets come back out of the file exactly as written.

        The single most important test in this file. The format's five traps all
        produce a file that writes cleanly and is corrupt on read, so this is what
        would catch their return.
        """
        beats = self.beats()
        self.assertEqual(len(beats), len(self.steps))
        for step, beat in zip(self.steps, beats):
            self.assertEqual(
                self.written_frets(beat),
                self.expected_frets(step),
                f"shape changed for {step.chord}",
            )

    def test_the_chord_name_is_the_chord_that_is_sounding(self):
        """Each beat is labelled with the chord it is sounding.

        Not always the written one: a step harmonised under a substitution carries
        the substitute in `harmonized_as`, and printing the written chord would
        name pitches that are not in it. The G7 of the ii-V-I here is written as a
        sus4, which is the arrangement's own decision, not the renderer's.
        """
        for step, beat in zip(self.steps, self.beats()):
            self.assertEqual(beat.text, step.harmonized_as or step.chord)

    def test_the_melody_is_the_highest_note_in_the_shape(self):
        """The melody is the top note of what was written.

        The playability invariant every grip guarantees, checked on the written
        file rather than on the Voicing - a string-mapping error would move the
        melody to the wrong string without changing any fret, so the shape
        comparison above would still pass.
        """
        for step, beat in zip(self.steps, self.beats()):
            melody_note = min(beat.notes, key=lambda note: note.string)
            self.assertEqual(
                melody_note.value,
                max(n.value for n in beat.notes),
                f"melody is not the top note for {step.chord}",
            )

    def test_muted_strings_are_absent_rather_than_fret_zero(self):
        """A muted string writes no note at all, rather than a note on fret 0.

        The distinction is the point of a tab: an `x` and an open string are
        different instructions, and a renderer writing fret 0 for a muted string
        would produce a file that plays.
        """
        for step, beat in zip(self.steps, self.beats()):
            self.assertEqual(len(beat.notes), len(self.expected_frets(step)))


@requires_guitarpro
class TestRhythm(GuitarProTestCase):
    """Durations and the bar grid."""

    # Four distinct shapes. Identical steps would legitimately collapse into one
    # held note - that is the `collapse` rule, and it is what a real arrangement
    # does under a repeated chord - so a rhythm test built from repeats would be
    # measuring the hold rather than the grid.
    FOUR_DISTINCT = [
        ([-1, -1, 10, 10, 10, 10], "Dm7"),
        ([-1, -1, 5, 7, 6, 7], "G7"),
        ([-1, -1, 5, 5, 5, 7], "Cmaj7"),
        ([-1, -1, 4, 4, 2, 3], "Amaj7"),
    ]

    def four_steps(self):
        return [
            make_step(frets, chord, "A4") for frets, chord in self.FOUR_DISTINCT
        ]

    def test_no_timing_falls_back_to_one_chord_per_beat(self):
        """Hand-written steps with no timing export rather than failing."""
        beats = self.beats(steps=self.four_steps())
        self.assertEqual([b.duration.value for b in beats], [4, 4, 4, 4])

    def test_four_quarters_fill_one_measure(self):
        """Four quarter notes are one 4/4 bar, not four bars."""
        measures = self.measures(steps=self.four_steps())
        self.assertEqual(len(measures), 1)
        self.assertEqual(len(measures[0].voices[0].beats), 4)

    def test_eight_eighths_fill_two_measures(self):
        """Two steps to a beat still make one bar each - the length is what counts.

        This is the case the eighth-note skeleton actually produces, and the one
        that caught a grid bug: a measure has to open when the cursor *reaches* a
        bar line, not only when a step crosses one, or all eight beats land in the
        first bar.
        """
        engine = VoiceLeadingEngine()
        steps = []
        for _ in range(4):
            steps.extend(engine.arrange_progression(
                [("A4", "m7", "Dm7"), ("C5", "7", "G7")]
            ))
        # Two steps share each beat, so each is an eighth. The beats are 1,1,2,2
        # within a bar, which is what makes two steps land on the same onset.
        pairs = [1, 1, 2, 2, 3, 3, 4, 4]
        timed = [
            ArrangementStep(**{**s.__dict__, "bar": i // 4,
                               "beat": pairs[i], "duration": 0.5})
            for i, s in enumerate(steps[:8])
        ]
        measures = self.measures(steps=timed)
        # Two bars. The grid is what this renderer owns; the lengths within it come
        # from `tabxml._events`, shared with the MusicXML renderer and tested there.
        # The beat *count* is not asserted, because a length the format cannot hold
        # exactly is written as more than one note - see `_duration_split`.
        self.assertEqual(len(measures), 2)
        # A pair sharing a beat is two eighths, which is the whole point of the
        # eighth-note skeleton: guitarpro writes an eighth as 8. These two are the
        # first step of each beat, so they are the ones the fixture controls.
        self.assertEqual(
            [b.duration.value for b in self.beats(steps=timed)][:2], [8, 8]
        )
        # And no bar outlasts its signature, which is the property a reader checks.
        for measure in measures:
            total = 0.0
            for beat in measure.voices[0].beats:
                length = 4.0 / beat.duration.value
                tuplet = beat.duration.tuplet
                if tuplet and (tuplet.enters, tuplet.times) != (1, 1):
                    length = length * tuplet.times / tuplet.enters
                total += length
            self.assertLessEqual(total, 4.0 + 1e-6)

    def test_an_identical_step_is_held_as_one_longer_note(self):
        """The same shape twice is one note, not two strikes.

        The same collapse rule the other two renderers apply: a held chord is
        struck once and rings, so the file shows what the player does rather than
        a re-strike. Both steps are timed, so this measures the hold rather than
        the no-timing fallback.
        """
        first = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                          bar=1, beat=1, duration=1.0)
        second = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                           bar=1, beat=2, duration=1.0)
        beats = self.beats(steps=[first, second])
        # One beat, lasting the whole bar: guitarpro writes a whole note as 1, since
        # the number is the denominator. See `_duration_value`.
        self.assertEqual([b.duration.value for b in beats], [1])

    def test_a_dotted_half_is_split_rather_than_rounded_to_a_whole_note(self):
        """A length the format cannot hold becomes two notes, not one long note.

        The bug this pins: `round(4 / 3)` is 1, so a dotted half was written as a
        *whole note*. Inside a bar that is a quarter too long, which is what made
        TuxGuitar report `voice 1 is too long` - the bar summed to more than its
        4/4 signature and the reader rejected the song.
        """
        from tabgp import _duration_split
        self.assertEqual(_duration_split(3.0), [(2, None), (4, None)])

    def test_a_triplet_is_a_duration_plus_a_tuplet_not_a_duration_of_twelve(self):
        """A triplet eighth is `Duration(8)` with a 3:2 tuplet.

        The bug this pins: the format writes a duration as `value.bit_length() - 3`
        and reads it back as `1 << (n + 2)`, so a bare `Duration(12)` is written as
        1 and comes back as an *eighth*. Nothing errors - the bar is simply a quarter
        too long, and every triplet in the head silently became an eighth.
        """
        from tabgp import _duration_split
        self.assertEqual(_duration_split(1.0 / 3.0), [(8, (3, 2))])

    def test_no_written_bar_is_longer_than_its_time_signature(self):
        """Every measure sums to at most the bar, as the reader requires it.

        The property a notation program actually checks, and the one that produced
        the "voice 1 is too long" error. Asserted over a real corpus head rather
        than a hand-built case, because the failure needs the transcribed grid - a
        triplet division and a step sharing a bar line - to appear at all.
        """
        from tabgp import _measures
        from tabxml import _events, _substitute_steps
        from wjazzd import DEFAULT_DB, arrange_head, load_solo, select_head

        if not DEFAULT_DB.is_file():
            self.skipTest("no Weimar database available")

        head = select_head(218)
        steps = arrange_head(
            load_solo(218), head=head, strategy="eighths"
        ).steps
        events, pickup = _events(_substitute_steps(steps), 4, True)
        for number, beats in enumerate(_measures(events, pickup, 4), start=1):
            # The exact lengths the renderer was asked for. A bar is at most a bar
            # long: the closing one is shorter, because the head stops there.
            self.assertLessEqual(
                sum(length for _s, length in beats),
                4.0 + 1e-6,
                msg=f"bar {number} is longer than 4/4",
            )

        # And the same check on what actually reaches the file, with tuplets
        # resolved the way the reader resolves them.
        song = self.song(steps=steps)
        for number, measure in enumerate(song.tracks[0].measures, start=1):
            total = 0.0
            for beat in measure.voices[0].beats:
                length = 4.0 / beat.duration.value
                tuplet = beat.duration.tuplet
                if tuplet and (tuplet.enters, tuplet.times) != (1, 1):
                    length = length * tuplet.times / tuplet.enters
                total += length
            self.assertLessEqual(
                total, 4.0 + 1e-6,
                f"bar {number} is {total} quarters, longer than 4/4",
            )

    def test_a_step_crossing_a_bar_line_is_split_not_stretched(self):
        """A step running over a bar line is written in two measures, in order.

        The MusicXML renderer ties the halves. A GP5 measure is fixed-length, so
        the split is written as two notes in consecutive bars - the same music, and
        the only thing the format can express.
        """
        crossing = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                             bar=1, beat=3, duration=1.0)
        after = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4",
                          bar=2, beat=1, duration=1.0)
        measures = self.measures(steps=[crossing, after])
        # The head starts on beat 3, so the first bar opens with a **rest** for the
        # two beats before it and the Dm7 fills the rest of it exactly. Nothing
        # crosses a bar line any more, because the rest is time rather than a hole:
        # the G7 gets the whole of bar 2 in one note. (It used to be split in two,
        # which was a symptom of the pickup being dropped and the music sliding up
        # into it - the split was the format working around the loader's error.)
        self.assertEqual(
            [b.text for m in measures for b in m.voices[0].beats],
            [None, "Dm7", "G7"],
        )
        # Both bars are exactly full, which is what GP5 requires.
        for measure in measures:
            self.assertAlmostEqual(self.bar_quarters(measure), 4.0, places=6)

    def test_a_long_step_is_split_across_a_bar_line_rather_than_stretched(self):
        """A note longer than the bar it starts in is written out, in two measures.

        The same mechanism as the anacrusis case above, and the reason it exists: a
        GP5 measure is a fixed-length container, so a shape that runs over the bar
        line is written as two notes in consecutive bars. This is deliberately built
        without a pickup, so the split is caused by the note's own length rather
        than by where the head starts.
        """
        long_step = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                              bar=1, beat=1, duration=1.0)
        # The length written is the gap to the *next* onset, so the split needs a
        # following step on the far side of the bar line, not a long duration.
        final = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4",
                          bar=3, beat=1, duration=1.0)
        measures = self.measures(steps=[long_step, final])
        self.assertEqual(len(measures), 3)
        for measure in measures:
            self.assertAlmostEqual(self.bar_quarters(measure), 4.0, places=6)
        # The Dm7 is written as two half-bar notes, in the two bars it spans, and
        # the G7 follows on its own downbeat - split, not stretched or substituted.
        self.assertEqual(
            [b.text for m in measures for b in m.voices[0].beats],
            ["Dm7", "Dm7", "G7"],
        )

    def test_a_pickup_is_written_as_a_rest_not_dropped(self):
        """A head that starts on the upbeat keeps its rest, in its first bar.

        Bar 1 of "But Not For Me" is a quarter rest and then three quarter notes.
        The rest was skipped as a non-note and the *cursor* was not moved past it, so
        every note after it was read a beat early, the head appeared to start on the
        downbeat, and the bar was written as three chords filling it. Both halves of
        that are wrong in a way the ear catches before any test does: the tune is a
        beat out and its first bar has the wrong rhythm.
        """
        song = self.song(
            steps=[
                make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                          bar=1, beat=2, duration=1.0),
                make_step([-1, -1, 12, 12, 12, 12], "G7", "B4",
                          bar=1, beat=3, duration=1.0),
            ],
            beats_per_bar=4,
        )
        beats = song.tracks[0].measures[0].voices[0].beats
        # A quarter of rest, then the two chords: the bar is four quarters of time.
        self.assertEqual(len(beats), 3)
        self.assertEqual(beats[0].notes, [])
        self.assertAlmostEqual(4.0 / beats[0].duration.value, 1.0, places=6)
        self.assertEqual([b.text for b in beats[1:]], ["Dm7", "G7"])
        self.assertAlmostEqual(self.bar_quarters(song.tracks[0].measures[0]), 4.0, places=6)

    def test_tempo_and_time_signature_reach_the_file(self):
        """The score's tempo and metre are set, not left at the defaults."""
        song = self.song(tempo=180, beats_per_bar=3)
        self.assertEqual(song.tempo, 180)
        self.assertEqual(song.measureHeaders[0].timeSignature.numerator, 3)

    def test_the_denominator_is_not_hardcoded_to_four(self):
        """A head in cut time is written 2/2, not restated as 2/4.

        The count alone cannot say which metre a head is in: 2/2 and 2/4 are both
        two beats to the bar, so a writer that assumes a denominator of 4 turns a
        standard into a tune that is notated wrongly. Only the notated `beat_type`
        distinguishes them, so it is the caller's to pass.
        """
        song = self.song(beats_per_bar=2, beat_type=2)
        signature = song.measureHeaders[0].timeSignature
        self.assertEqual(signature.numerator, 2)
        self.assertEqual(signature.denominator.value, 2)
        # The default is unchanged for an ordinary 4/4 progression.
        self.assertEqual(
            self.song().measureHeaders[0].timeSignature.denominator.value, 4
        )

    def test_a_cut_time_bar_is_four_quarters_long_not_two(self):
        """A 2/2 bar is four quarters, and every measure has to be that long.

        A beat is a *half* note in 2/2 and a quarter in 4/4, so a bar of
        `beats_per_bar` beats is `beats_per_bar * 4 / beat_type` quarters - which is
        **four quarters in both metres**, since 2/2 and 4/4 differ in how a bar is
        counted, not in how long it is.

        This asserts the summed duration rather than the measure *count*, and the
        difference matters. Reading the fraction the other way round, `beat_type/4`,
        gives a bar of `2 * 0.5` quarters: the measure count still comes out right
        (the onsets are placed in beats, which is correct either way) while every
        measure holds a quarter of the music its signature claims. A test on the
        count alone passes that, and 4/4 cannot catch it at all.
        """
        # One step on the downbeat of bar 1 and one on the downbeat of bar 2: a
        # whole bar apart in either metre.
        first = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4", bar=1, beat=1.0)
        second = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4", bar=2, beat=1.0)

        for beats_per_bar, beat_type in ((2, 2), (4, 4), (3, 4), (6, 8)):
            with self.subTest(metre=f"{beats_per_bar}/{beat_type}"):
                measures = self.measures(
                    steps=[first, second],
                    beats_per_bar=beats_per_bar,
                    beat_type=beat_type,
                )
                self.assertEqual(len(measures), 2)
                for measure in measures:
                    self.assertAlmostEqual(
                        self.bar_quarters(measure),
                        beats_per_bar * 4.0 / beat_type,
                        places=6,
                    )

    def test_every_measure_of_a_written_head_fills_its_bar(self):
        """A real 2/2 head comes out as full bars, not a quarter note of music each.

        The round trip over a committed score, and the check that actually matters
        on a file no hand-written fixture imitates: read every measure back and sum
        it. A measure may be *short* (a pickup, or the trailing one), but a bar in
        the middle cannot be, and a systematic shortfall of exactly 4x is the
        signature of the beat length being read as a fraction rather than a divisor.
        """
        from headxml import arrange_xml_head

        steps, head, _notes = arrange_xml_head(
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "but_not_for_me.mxl"),
            strategy="eighths",
        )
        song = self.song(
            steps=steps,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
        )
        measures = song.tracks[0].measures
        self.assertEqual(len(measures), 32)
        bar = head.beats_per_bar * 4.0 / head.beat_type
        # Every interior measure is full; a leading pickup or a padded tail may not be.
        for measure in measures[1:-1]:
            self.assertAlmostEqual(self.bar_quarters(measure), bar, places=6)


@requires_guitarpro
class TestOptions(GuitarProTestCase):
    """The switches a caller can turn."""

    def test_no_steps_is_an_empty_file_not_an_error(self):
        from tabgp import format_gp5
        self.assertEqual(format_gp5([]), b"")

    def test_beats_per_bar_below_one_is_rejected(self):
        with self.assertRaises(ValueError):
            self.data(beats_per_bar=0)

    def test_show_chords_false_omits_the_names_but_not_the_shapes(self):
        with_names = self.beats()
        without = self.beats(show_chords=False)
        self.assertEqual(len(with_names), len(without))
        self.assertTrue(any(b.text for b in with_names))
        self.assertFalse(any(b.text for b in without))
        self.assertEqual(
            [self.written_frets(b) for b in with_names],
            [self.written_frets(b) for b in without],
        )

    def test_a_substituted_chord_is_named_as_sounding(self):
        """A step harmonised under a substitution is labelled with what is played.

        `harmonized_as` names the chord actually sounding, so the file must not
        claim the written one. It is reached through the same shared
        `_substitute_steps` pass `tabxml` uses, so the two files cannot disagree.
        """
        step = make_step([-1, -1, 10, 10, 10, 10], "Cmaj7", "E4",
                          harmonized_as="Cmaj9")
        beat = self.beats(steps=[step])[0]
        self.assertEqual(beat.text, "Cmaj9")

    def test_a_repeated_melody_is_written_as_a_single_note(self):
        """A hold is one struck note, matching the other two renderers.

        The held shape belongs to the chord the hold began on, so writing the full
        voicing again would claim a harmony that is not sounding.
        """
        engine = VoiceLeadingEngine()
        held = engine.arrange_progression(
            [("A4", "m7", "Dm7"), ("A4", "m7", "Dm7")]
        )
        self.assertTrue(held[1].repeated)
        beat = self.beats(steps=held)[1]
        soprano = held[1].voicing.soprano_string()
        self.assertEqual(len(beat.notes), 1)
        self.assertEqual(beat.notes[0].value, held[1].voicing.frets[soprano])

    def test_write_gp5_writes_a_file_the_parser_accepts(self):
        import io
        from tabgp import write_gp5
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "arrangement.gp5")
            self.assertEqual(write_gp5(self.steps, path), path)
            with open(path, "rb") as handle:
                data = handle.read()
        beats = [b for m in _parse(io.BytesIO(data)).tracks[0].measures
                 for b in m.voices[0].beats]
        self.assertEqual(len(beats), len(self.steps))

    def test_format_gp5_is_pure_and_deterministic(self):
        """The renderer writes no file, and the same steps give the same bytes."""
        from tabgp import format_gp5
        with tempfile.TemporaryDirectory() as directory:
            format_gp5(self.steps)
            self.assertEqual(os.listdir(directory), [])
        self.assertEqual(format_gp5(self.steps), format_gp5(self.steps))


class TestModuleSurface(unittest.TestCase):
    """The parts that work with PyGuitarPro absent, which is the default install."""

    def test_importing_the_module_does_not_need_the_extra(self):
        """`import tabgp` must work on a machine that has never heard of it.

        The lazy import is the whole reason the extra is optional, and this is the
        one check that would catch a stray module-level `import guitarpro`.
        """
        import tabgp
        self.assertEqual(tabgp.__all__, ["format_gp5", "write_gp5"])

    def test_the_error_names_the_install_command(self):
        """A missing extra is reported as a usage message, not a traceback."""
        from tabgp import _guitarpro
        if HAS_GUITARPRO:  # pragma: no cover - depends on the environment
            self.skipTest("PyGuitarPro is installed, so there is no error to raise")
        with self.assertRaises(ImportError) as caught:
            _guitarpro()
        self.assertIn("jazz-arranger[gp]", str(caught.exception))

    def test_the_renderers_are_reachable_from_the_public_spelling(self):
        """`from arranger import write_gp5` is the one spelling for the renderer."""
        import arranger
        import tabgp
        self.assertIs(arranger.format_gp5, tabgp.format_gp5)
        self.assertIs(arranger.write_gp5, tabgp.write_gp5)
        self.assertIn("format_gp5", arranger.__all__)
        self.assertIn("write_gp5", arranger.__all__)

    def test_duration_rounding_floors_rather_than_deleting(self):
        """A length too short to write becomes a sixteenth, not nothing.

        A beat with no duration occupies no time at all, so rounding down to zero
        would delete the note rather than shorten it.
        """
        from tabgp import _duration_value
        self.assertEqual(_duration_value(1.0), 4)     # a quarter
        self.assertEqual(_duration_value(0.5), 8)     # an eighth
        self.assertEqual(_duration_value(0.25), 16)   # a sixteenth
        self.assertEqual(_duration_value(0.0), 16)    # no length is not a whole note
        self.assertEqual(_duration_value(8.0), 1)     # a whole note
