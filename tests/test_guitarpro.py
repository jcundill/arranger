"""Tests for the Guitar Pro renderer in `tabgp`.

Guarded on PyGuitarPro being installed, exactly as the MusicXML tests are guarded on
music21: it is an optional extra, and a fresh clone without the extras runs a reduced
suite.

The core of these tests is a **round trip**: the file is written, parsed back with
`guitarpro.parse`, and the notes compared against the frets the arrangement was built
from. That is deliberate, and it is how the format's six undocumented traps were
found in the first place - each one produces a file that *writes without complaint*
and is corrupt on read, so an assertion on the builder's own output would pass while
the file was unusable. A GP file's only contract is that Guitar Pro can open it, and
a parse is the closest proxy available without Guitar Pro itself.

The limit of that proxy is worth stating, because one trap has already got past it:
a file can be self-consistent and still be read wrongly by another program. The
unmarked-rest defect is the example - PyGuitarPro read back exactly what was written,
MuseScore 3 rendered it correctly, and TuxGuitar put the rest in the wrong place. So
the assertions check the *semantics a reader acts on* (note type, beat status),
not merely that the round trip is lossless.
"""

import contextlib
import io
import os
import tempfile
import unittest

from arranger import ArrangementStep, VoiceLeadingEngine

# The shared placement core, reached directly: these tests are about where events
# land, which is decided in `tabxml` and only turned into beats by `tabgp`.
from tabgp import format_gp5
from tabxml import _events, _substitute_steps
from tests.support import bass_string, make_step

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

    def test_the_key_survives_the_round_trip(self):
        """Three flats written as three flats, and the mode carried beside them.

        GP5's `KeySignature` is an enum keyed on `(fifths, is_minor)`, so the round
        trip is the only check that the two numbers this library is handed arrive as
        the key they name: -3 with no mode is Eb, and -3 minor is C, which is a
        different key arriving from the same count.
        """
        import guitarpro

        def written(**kwargs):
            return self.song(**kwargs).measureHeaders[0].keySignature

        self.assertEqual(written(fifths=-3, mode="major"), guitarpro.KeySignature.EMajorFlat)
        self.assertEqual(written(fifths=-3, mode="minor"), guitarpro.KeySignature.CMinor)
        self.assertEqual(written(fifths=1, mode="major"), guitarpro.KeySignature.GMajor)
        # No mode is not a guess: GP5 records the two modes only, so the signature is
        # written major - the same default the file already implied by its absence.
        self.assertEqual(written(fifths=-3), guitarpro.KeySignature.EMajorFlat)

    def test_no_key_leaves_the_file_in_c_major(self):
        """The format's own default, stated rather than assumed."""
        import guitarpro

        self.assertEqual(
            self.song().measureHeaders[0].keySignature,
            guitarpro.KeySignature.CMajor,
        )

    def test_the_key_member_is_found_without_a_two_argument_enum_call(self):
        """
        The lookup must not depend on how a given Python version reads `Enum(...)`.

        `KeySignature(-3, 0)` reads as a value lookup on 3.12+ and as the *functional*
        enum API - "define a new class" - on 3.11, where it raises
        `TypeError: <enum 0> cannot extend <enum 'KeySignature'>`. That difference is
        invisible on a 3.14 dev box and breaks the 3.11 CI job on the first test that
        asks for a key.

        So this asserts the *result* of every signature the library can ask for, and
        never the call that produces it. Running it on each version is what the
        matrix is for; this is the check that fails if the lookup is ever rewritten
        into a form only one of them accepts.
        """
        import guitarpro

        from tabgp import _key_signature

        expected = {
            (-7, "major"): guitarpro.KeySignature.CMajorFlat,
            (-3, "major"): guitarpro.KeySignature.EMajorFlat,
            (-3, "minor"): guitarpro.KeySignature.CMinor,
            (-3, ""): guitarpro.KeySignature.EMajorFlat,
            (0, ""): guitarpro.KeySignature.CMajor,
            (1, "major"): guitarpro.KeySignature.GMajor,
            (7, "minor"): guitarpro.KeySignature.AMinorSharp,
        }
        for (fifths, mode), member in expected.items():
            self.assertIs(_key_signature(guitarpro, fifths, mode), member, (fifths, mode))

    def test_every_bar_carries_the_key_not_only_the_first(self):
        """
        The key is stated on **every** bar, which is what a `MeasureHeader` per bar needs.

        `keySignature` is a per-bar field in GP5 and a fresh `MeasureHeader` defaults
        it to `CMajor`, so setting it only on bar 1 wrote a file that read as "Eb major,
        then C major" for the remaining 31 bars of "But Not For Me". Reported from a
        GP5 export of that head, and reproduced on the tree before this change.

        Asserted over **all** the headers rather than `[0]`, which is the trap: the
        three tests above all read `measureHeaders[0]`, and bar 1 was always right.
        A single-bar file cannot catch this at all, so the fixture here is three bars.
        """
        import guitarpro

        # The shared `setUp` fixture is **one** bar with no timings, which is exactly
        # the shape that cannot catch this defect - so the fixture is built here, over
        # three bars, rather than borrowed. Asserting on a single bar would have
        # passed against the broken exporter.
        steps = VoiceLeadingEngine().arrange_progression(
            [("A4", "m7", "Dm7"), ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7")],
            timings=[(1, 1.0, 1.0), (2, 1.0, 1.0), (3, 1.0, 1.0)],
        )
        song = self.song(steps=steps, fifths=-3, mode="major")
        headers = song.measureHeaders
        self.assertEqual(
            len(headers), 3, "the fixture is not three bars, so this cannot fail"
        )
        for header in headers:
            self.assertEqual(
                header.keySignature,
                guitarpro.KeySignature.EMajorFlat,
                f"bar {header.number} does not state the head's key",
            )

    def test_a_key_on_the_first_bar_alone_left_the_rest_in_c(self):
        """
        The premise of the test above, asserted as a *count*, so it stays meaningful.

        Guards the shape of the fixture rather than the fix: if a change made the
        exporter write one header for the whole file, `test_every_bar_carries_the_key`
        would pass trivially with a single bar and stop testing anything. The writer
        emits a header per bar, so the count has to follow it.
        """
        song = self.song(fifths=-3, mode="major")
        self.assertEqual(
            len(song.measureHeaders),
            len(song.tracks[0].measures),
            "the exporter no longer writes one header per bar",
        )

    def test_every_committed_head_states_its_key_on_every_bar(self):
        """
        The reported head, and the four others, end to end through the importer.

        A GP5 export is the only place the defect is visible: `MusicXML` and the ASCII
        and HTML renderers each carry the key once, because those formats state it once.
        So this goes through `arrange_xml_head` and reads the file back, rather than
        calling `format_gp5` with a hand-passed `fifths`.
        """
        import contextlib
        import io

        from headxml import arrange_xml_head

        heads = (
            ("but_not_for_me.mxl", -3),
            ("heres_that_rainy_day.musicxml", 1),
            ("The_Jitterbug_Waltz.musicxml", -3),
        )
        for name, fifths in heads:
            with self.subTest(head=name):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    steps, head, _notes = arrange_xml_head(
                        f"tests/data/{name}", grips=("shell",)
                    )
                self.assertEqual(
                    head.key_fifths, fifths, f"{name}: the fixture's own key"
                )
                song = _parse(io.BytesIO(format_gp5(steps, fifths=head.key_fifths)))
                keys = {header.keySignature for header in song.measureHeaders}
                self.assertEqual(
                    len(keys),
                    1,
                    f"{name}: the bars disagree about the key ({keys})",
                )

    def test_a_signature_gp5_cannot_name_is_not_rounded_to_one(self):
        """Nine flats is no conventional key, and the nearest would be a lie.

        The file then states C major - which is what it would have said with no
        signature at all - rather than seven flats, which is a different key the
        arrangement is not in.
        """
        import guitarpro

        self.assertEqual(
            self.song(fifths=-9).measureHeaders[0].keySignature,
            guitarpro.KeySignature.CMajor,
        )

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
        the "voice 1 is too long" error. Asserted over real committed scores rather
        than a hand-built case, because the failure needs a notated grid - a
        triplet division and a step sharing a bar line - to appear at all.

        **This was asserted over the Weimar corpus and skipped without it.** It read
        melid 218, which is where the triplet grid that triggered the bug was
        found, and it was one of the 164 tests the database's absence removed. So it
        needed a replacement rather than a deletion, and the replacement is three
        committed scores chosen for the property rather than for being a tune:

            i_was_doing_all_right.mxl    2/2   110 notes   39 triplets
            Trouble_in_Mind_Blues       4/4    53 notes    3 triplets
            tenor_madness.musicxml      4/4   200 notes    6 triplets

        `i_was_doing_all_right` is the important one: **39 triplets**, more than the
        corpus head had. Measured over all three: **0 measures over**, with the
        longest bar exactly full in each - the "at most" boundary reached rather than
        merely respected, so this is a real measurement and not a vacuous one.

        **And the limit is computed, not written as 4.** A 2/2 bar is four quarters,
        so `beats_per_bar` on its own is wrong for every metre that is not 4/4 - and
        `The_Jitterbug_Waltz` is 3/4, where it is wrong by a quarter note. This is
        trap 9 (`docs/open-issues.md`) arriving precisely where that document says it
        would, and the first version of this test made exactly that error and
        reported 32 of a 2/2 head's measures as over-long.
        """
        import headxml
        from tabgp import _measures
        from tabxml import _events, _substitute_steps

        data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        scores = ("i_was_doing_all_right.mxl", "Trouble_in_Mind_Blues.musicxml",
                  "tenor_madness.musicxml")
        for name in scores:
            with self.subTest(score=name):
                steps, head, _notes = headxml.arrange_xml_head(
                    os.path.join(data, name)
                )
                # A count without a denominator is not a metre, and this is trap 9
                # arriving exactly where the document says it would: `beats_per_bar`
                # alone is the wrong number of quarters for every metre that is not
                # 4/4. A 2/2 bar is four quarters, not two - the beat is a half note -
                # so the limit is `beats_per_bar` beats of `4 / beat_type` quarters.
                # Writing `float(head.beats_per_bar)` here reports 32 of 35 measures
                # of a 2/2 head as over-long, which is the test being wrong and
                # sounding exactly like a renderer bug.
                limit = float(head.beats_per_bar) * (4.0 / float(head.beat_type))
                events, pickup = _events(
                    _substitute_steps(steps), head.beats_per_bar, True,
                    head.beat_type,
                )
                for number, beats in enumerate(
                    _measures(events, pickup, head.beats_per_bar), start=1
                ):
                    total = sum(length for _s, length, _tie in beats)
                    self.assertLessEqual(
                        total, limit + 1e-6,
                        msg=f"{name} bar {number} is {total} quarters, "
                            f"longer than {limit}",
                    )

                # And the same check on what actually reaches the file, with
                # tuplets resolved the way the reader resolves them. The metre is
                # passed rather than defaulted: `format_gp5` writes a 4/4 measure
                # unless told otherwise, so a cut-time head read as common time
                # would produce a bar twice as long as the file claims - which is
                # this very property, failing one layer down.
                song = self.song(
                    steps=steps,
                    beats_per_bar=head.beats_per_bar,
                    beat_type=head.beat_type,
                )
                for number, measure in enumerate(
                    song.tracks[0].measures, start=1
                ):
                    total = 0.0
                    for beat in measure.voices[0].beats:
                        length = 4.0 / beat.duration.value
                        tuplet = beat.duration.tuplet
                        if tuplet and (tuplet.enters, tuplet.times) != (1, 1):
                            length = length * tuplet.times / tuplet.enters
                        total += length
                    self.assertLessEqual(
                        total, limit + 1e-6,
                        f"{name} bar {number} is {total} quarters, longer than "
                        f"{limit}",
                    )

    def test_a_step_crossing_a_bar_line_is_split_not_stretched(self):
        """A step running over a bar line is written in two measures, in order.

        The MusicXML renderer ties the halves. A GP5 measure is fixed-length, so
        the split is written as two notes in consecutive bars, joined by a GP tie -
        see `test_a_held_shape_is_tied_across_a_bar_line_not_re_struck`.
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

    def test_a_length_the_format_cannot_exact_is_written_short_never_long(self):
        """A length with no exact decomposition is truncated, not padded.

        The property the reader actually enforces, stated directly: a beat's written
        parts may sum to *less* than the length asked for, never more. A bar that
        overruns its signature is rejected outright.

        The last case is the one that was wrong. A triplet-eighth is exactly
        representable, but a **triplet-quarter** is `Duration(4)` with a `Tuplet`,
        and a length of 1/6 quarter - which is what a triplet-eighth rest resolves to
        once the skeleton divides an onset - leaves a sliver the greedy pass cannot
        cover by any single note. The old code appended a sixteenth to close it, and
        on the Weimar head that made bar 2 four and a half sixteenths long.
        """
        from tabgp import _duration_split

        def written(length):
            total = 0.0
            for value, tuplet in _duration_split(length):
                part = 4.0 / value
                if tuplet is not None:
                    part = part * tuplet[1] / tuplet[0]
                total += part
            return total

        for length in (0.25, 0.5, 0.75, 1.0, 1.5, 1.25, 1.0 / 3.0, 1.0 / 6.0):
            self.assertLessEqual(
                written(length), length + 1e-6,
                f"{length} quarters was written longer than it is",
            )
        # The exact cases are still exact - the rule is a ceiling, not a licence to
        # round.
        self.assertAlmostEqual(written(1.5), 1.5, places=6)
        self.assertAlmostEqual(written(1.0 / 3.0), 1.0 / 3.0, places=6)
        # And the inexpressible one is short rather than padded.
        self.assertLess(written(1.0 / 6.0), 1.0 / 6.0 + 1e-6)

    def test_a_gap_between_notes_is_a_rest_not_a_held_chord(self):
        """A note is not held across a rest that follows it.

        Bar 4 of "But Not For Me" is a single whole note and bar 5 opens with a
        quarter rest. The span written for a group is the gap to the *next onset*,
        which is five quarters here rather than the four the note is written for, so
        the note was held over the silence into the next bar - and since a step
        crossing a bar line is tied, bar 5 opened with a tied chord where the score
        says a rest. The eighth-note skeleton puts a rest at the head of every
        second bar, so this was not one bar but half the head.

        The fix caps the span at the melody note's own `duration` and writes the
        remainder as an explicit rest, which is what `None` already means to all
        three renderers.
        """
        # Bar 1 is a whole note, bar 2's first note is a quarter late: the quarter
        # between them is silence.
        whole = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                          bar=1, beat=1, duration=1.0)
        after = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4",
                          bar=2, beat=2, duration=1.0)
        events, _pickup = _events(_substitute_steps([whole, after]), 4, True)
        # The Dm7 fills one bar and does not run into the second; the quarter
        # before the G7 is a rest rather than more Dm7. The G7 is the *last* group,
        # so it runs to the end of its own bar - three quarters, not four - which is
        # the pre-existing rule for a closing event and is not part of this fix.
        self.assertEqual(
            [(None if s is None else s.chord, round(length, 6))
             for s, _strikes, length in events],
            [("Dm7", 4.0), (None, 1.0), ("G7", 3.0)],
        )

    def test_a_gap_that_does_not_exist_is_not_turned_into_a_rest(self):
        """A note written as long as the gap is not shortened by a cap.

        The other direction, and the one that would make the fix above a regression:
        `duration` may only ever *shorten* a span, never lengthen one, and a head
        whose notes fill their gaps exactly must come out with no rests at all.
        """
        # Both notes are a whole note and the second starts exactly where the first
        # ends, so there is no silence anywhere.
        first = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                          bar=1, beat=1, duration=1.0)
        second = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4",
                           bar=2, beat=1, duration=1.0)
        events, _pickup = _events(_substitute_steps([first, second]), 4, True)
        self.assertEqual([s is None for s, _strikes, _length in events], [False, False])
        self.assertEqual(
            [round(length, 6) for _s, _strikes, length in events], [4.0, 4.0]
        )

    def test_a_step_with_no_timing_keeps_the_gap_it_had(self):
        """The cap needs a `duration`; a step without one is untouched.

        `duration` is optional on `ArrangementStep`, and a hand-built progression has
        none, so the whole-gap behaviour has to survive its absence - otherwise the
        renderers' uniform-grid fallback would start inventing rests.
        """
        plain = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4")
        plain2 = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4")
        # No bar, beat or duration on either: this is the uniform-grid fallback.
        self.assertIsNone(plain.duration)
        events, _pickup = _events(_substitute_steps([plain, plain2]), 4, True)
        self.assertEqual([s is None for s, _strikes, _length in events], [False, False])

    def test_a_long_step_is_split_across_a_bar_line_rather_than_stretched(self):
        """A note longer than the bar it starts in is written out, in two measures.

        The same mechanism as the anacrusis case above, and the reason it exists: a
        GP5 measure is a fixed-length container, so a shape that runs over the bar
        line is written as two notes in consecutive bars. This is deliberately built
        without a pickup, so the split is caused by the note's own length rather
        than by where the head starts.
        """
        long_step = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                              bar=1, beat=1, duration=2.0)
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

    def test_a_held_shape_is_tied_across_a_bar_line_not_re_struck(self):
        """The two halves of a split step are **tied**, not struck twice.

        The bug this pins. A step that runs across a bar line is written as two
        notes, one in each bar - that much is forced by the format, since a GP5
        measure is a fixed-length container. The halves used to be written as two
        ordinary notes, so a shape held over the bar line was **re-struck** at the
        head of the next bar. In "But Not For Me" that happened in 14 of the 32
        bars, and the source score genuinely ties Eb4 across the bar line in bars
        2-3, so the file contradicted the notation it was exported from.

        The claim that caused it - that a GP tie is "a slur the player has to
        interpret rather than a hold" - is simply false: `NoteType.tie` is a real
        GP5 tie and survives a write/parse round trip in PyGuitarPro 0.11. The test
        parses the file back, because that is the only way to see what the reader
        gets; asserting on the builder's own objects would pass whether or not the
        flag reached the bytes.
        """
        import guitarpro

        crossing = make_step([-1, -1, 10, 10, 10, 10], "Dm7", "A4",
                             bar=1, beat=1, duration=2.0)
        final = make_step([-1, -1, 12, 12, 12, 12], "G7", "B4",
                          bar=3, beat=1, duration=1.0)
        song = self.song(steps=[crossing, final])
        beats = [b for m in song.tracks[0].measures for b in m.voices[0].beats]
        self.assertEqual([b.text for b in beats], ["Dm7", "Dm7", "G7"])
        # The attack is an ordinary note; only the continuation is a tie.
        self.assertEqual(
            [n.type for b in beats for n in b.notes],
            [guitarpro.NoteType.normal] * 4
            + [guitarpro.NoteType.tie] * 4
            + [guitarpro.NoteType.normal] * 4,
        )
        # The same shape on both sides of the bar line, which is what makes the
        # tie meaningful - a tie between two different shapes would be a slur.
        first = sorted((n.string, n.value) for n in beats[0].notes)
        second = sorted((n.string, n.value) for n in beats[1].notes)
        self.assertEqual(first, second)

    def test_every_split_step_in_a_written_head_is_tied(self):
        """No bar of a real head opens by re-striking the previous bar's shape.

        The same defect measured over "But Not For Me" rather than a hand-built
        case: a step crosses a bar line on most bars of this head, so a hand-built
        fixture would find it while a real export would still be full of them. A
        bar that opens with a shape identical to the one the previous bar closed on
        is a re-strike unless the second is a tie, and only the tie makes it a held
        note.
        """
        import guitarpro

        from headxml import arrange_xml_head

        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "but_not_for_me.mxl"
        )
        steps, head, _notes = arrange_xml_head(path)
        song = self.song(
            steps=steps,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
        )
        measures = song.tracks[0].measures
        self.assertEqual(len(measures), 32)

        restruck = []
        for index in range(1, len(measures)):
            last = measures[index - 1].voices[0].beats[-1]
            first = measures[index].voices[0].beats[0]
            if not last.notes or not first.notes:
                continue
            same = sorted((n.string, n.value) for n in last.notes) == sorted(
                (n.string, n.value) for n in first.notes
            )
            if same and not all(n.type == guitarpro.NoteType.tie for n in first.notes):
                restruck.append(index + 1)
        self.assertEqual(
            restruck, [],
            f"bars {restruck} re-strike the previous bar's shape untied",
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

    def test_a_rest_beat_is_marked_as_a_rest_not_as_an_empty_chord(self):
        """The pickup beat says `rest`, which is what the reader keys on.

        The bug this pins, and the only one so far that MuseScore and TuxGuitar
        disagree about - the file is self-consistent either way, so a round trip
        through PyGuitarPro passes while a notation program misplaces the rest.

        `gp3.writeBeat` only emits the status byte when the status is not `normal`:
        `if beat.status != gp.BeatStatus.normal: flags |= 0x40`. So a note-less beat
        marked `normal` goes out as an *ordinary* beat whose string-flags byte is
        empty - indistinguishable from a chord on no strings, rather than a rest.
        MuseScore 3 reads that as a rest in the right place; TuxGuitar does not, and
        puts the pickup rest on the 4th quarter instead of the 1st. `BeatStatus.rest`
        is the third member of the enum and was simply never used.

        The assertion is on the parsed-back status, because that is what the reader
        acts on; asserting that the beat has no notes is not enough, and is exactly
        what the earlier test did.
        """
        import guitarpro

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
        self.assertEqual(beats[0].status, guitarpro.BeatStatus.rest)
        # A beat that sounds is `normal`, not `rest` - the fix must not turn every
        # note into a rest, which would be a worse file than the original.
        self.assertEqual(beats[1].status, guitarpro.BeatStatus.normal)
        self.assertEqual(beats[2].status, guitarpro.BeatStatus.normal)
        # And the rest is still the *first* thing in the bar, which is the whole
        # point: TuxGuitar put it last.
        self.assertEqual(beats[0].notes, [])

    def test_every_note_less_beat_in_a_written_head_is_a_rest(self):
        """No beat in a real head is a note-less chord rather than a rest.

        The same defect over "But Not For Me" rather than a hand-built case, because
        the head opens with a quarter rest and the pickup is the only place one is
        written. A rest that is not marked as one still opens the bar here, so the
        measure count and the beat count are both right and only the *position* is
        wrong - the class of defect a length assertion cannot catch.
        """
        import guitarpro

        from headxml import arrange_xml_head

        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "but_not_for_me.mxl"
        )
        steps, head, _notes = arrange_xml_head(path)
        song = self.song(
            steps=steps,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
        )
        unmarked = []
        for index, measure in enumerate(song.tracks[0].measures, start=1):
            for position, beat in enumerate(measure.voices[0].beats):
                if beat.notes:
                    continue
                if beat.status != guitarpro.BeatStatus.rest:
                    unmarked.append((index, position))
        self.assertEqual(
            unmarked, [],
            f"note-less beats not marked as rests: {unmarked}",
        )
        # The head does open on its rest, so the fix is exercised rather than
        # vacuously true.
        first = song.tracks[0].measures[0].voices[0].beats[0]
        self.assertEqual(first.status, guitarpro.BeatStatus.rest)
        self.assertEqual(first.notes, [])

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
        """A real head comes out as full bars, not a quarter note of music each.

        The round trip over committed scores, and the check that actually matters on a
        file no hand-written fixture imitates: read every measure back and sum it. A
        measure may be *short* (a pickup, or the trailing one), but a bar in the middle
        cannot be, and a systematic shortfall is the signature of the beat length being
        read as a fraction rather than a divisor.

        **The second head is the 3/4 one, and it is here because it is the only metre
        that can see the importer's conversion being written as `beats_per_bar / 4`.**
        Measured before that fix: 21 of the waltz's 35 interior measures held 2.25, 2.5 or
        2.75 quarters of music in a bar the signature calls three wide, and after it all
        37 are exactly full. A count of measures cannot see either state - 37 is 37 - so
        this is the sum, which is what `docs/renderers.md` promises catches this family.
        """
        from headxml import arrange_xml_head

        data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        for name, expected in (("but_not_for_me.mxl", 32),
                               ("The_Jitterbug_Waltz.musicxml", 37)):
            with self.subTest(score=name):
                steps, head, _notes = arrange_xml_head(os.path.join(data, name))
                song = self.song(
                    steps=steps,
                    beats_per_bar=head.beats_per_bar,
                    beat_type=head.beat_type,
                )
                measures = song.tracks[0].measures
                self.assertEqual(len(measures), expected)
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


@requires_guitarpro
class TestWalkingBass(GuitarProTestCase):
    """A walking line through the round trip, which is the only check that finds this.

    GP5 cannot express "held" as an empty cell: a beat either has notes or it has
    none. So a bass-only beat has to *write* the shape still ringing above the thumb,
    as ties. Omitting those strings would not raise and would not fail a comparison
    against the arrangement - it would write a clean file in which the bar reads as
    **silence above a moving bass**, which is precisely the corruption this file's
    round trip exists to find.

    The fixture is the plan's own bar 1: a held whole note under one chord, which the
    union turns into one strike and three thumb-only beats.
    """

    def setUp(self):
        super().setUp()
        # Imported locally for the same reason the rest of this file does: the
        # module-level name is bound inside a `try`, so a checker reads every use of
        # it as possibly unbound even inside a `skipUnless`-guarded class.
        import guitarpro

        self.gp = guitarpro
        self.walk_steps = VoiceLeadingEngine.arrange_progression(
            [("F5", "maj7", "Fmaj7")],
            timings=[(0, 1.0, None)],
            texture="walking_bass",
        )
        self.walk_song = _parse(io.BytesIO(format_gp5(self.walk_steps)))
        self.walk_beats = [
            beat
            for measure in self.walk_song.tracks[0].measures
            for beat in measure.voices[0].beats
        ]

    def test_every_walked_beat_reaches_the_file(self):
        """The union's four steps are four beats, not one held shape plus three rests."""
        self.assertEqual(len(self.walk_beats), 4)
        for beat in self.walk_beats:
            self.assertNotEqual(beat.status, self.gp.BeatStatus.rest)

    def test_a_bass_only_beat_carries_the_held_shape_as_ties(self):
        """
        The regression. Each thumb-only beat writes the upper voices **tied**, so the
        shape is not re-struck and is not absent.

        Asserted on the parsed-back note *types* rather than on the frets, because the
        frets are the same on every beat: only the tie flag says whether this is one
        held shape or four attacks.

        The strings come from the arrangement's own `bass_string`, never assumed to be
        the low E - the thumb follows the hand and moves between the 6th, 5th and 4th,
        so a hardcoded string 6 would silently pass on a fixture where it happened to
        be right and fail to check anything at all where it was not.
        """
        struck = self.walk_beats[0]
        upper = sorted(
            _GP_STRING_OFFSET - index
            for index in range(6)
            if self.walk_steps[0].voicing.frets[index] >= 0
            and index != self.walk_steps[0].voicing.bass_string
        )
        for step, beat in zip(self.walk_steps[1:], self.walk_beats[1:]):
            thumb = _GP_STRING_OFFSET - bass_string(step)
            self.assertEqual(
                [n.type for n in beat.notes if n.string in upper],
                [self.gp.NoteType.tie] * len(upper),
                "the held shape was not tied across a bass-only beat",
            )
            self.assertEqual(
                [n.type for n in beat.notes if n.string == thumb],
                [self.gp.NoteType.normal],
                "the thumb was tied rather than struck",
            )
            # Every string the first beat sounded is still accounted for, plus the
            # thumb. A missing one is the silence this whole branch prevents.
            self.assertEqual(
                sorted(n.string for n in beat.notes),
                sorted({thumb} | set(n.string for n in struck.notes)),
            )

    def test_the_thumb_moves_and_the_shape_does_not(self):
        """The audible claim of the texture, read out of the file."""
        thumbs = [
            [n.value for n in beat.notes
             if n.string == _GP_STRING_OFFSET - bass_string(step)]
            for step, beat in zip(self.walk_steps, self.walk_beats)
        ]
        self.assertTrue(all(thumbs), f"a beat lost its thumb note: {thumbs}")
        self.assertGreater(
            len(set(tuple(v) for v in thumbs)), 1, "the thumb never moved"
        )
        melody_string = _GP_STRING_OFFSET - self.walk_steps[0].voicing.soprano_string()
        held = [
            [n.value for n in beat.notes if n.string == melody_string]
            for beat in self.walk_beats
        ]
        self.assertEqual(len(set(tuple(v) for v in held)), 1, "the melody moved")

    def test_no_written_bar_is_longer_than_its_signature(self):
        """
        The four thumb beats plus the strike are five quarters of events in a 4/4 bar,
        so the measure machinery has to place them without overrunning - the standing
        rule for every bar this renderer writes.
        """
        for measure in self.walk_song.tracks[0].measures:
            self.assertAlmostEqual(self.bar_quarters(measure), 4.0, places=6)

    def test_a_tie_never_asserts_a_pitch_the_string_is_not_sounding(self):
        """
        The regression, and it is a **fret** assertion where the tests above are a
        **type** assertion - which is why it got through. A tie is not "held" in the
        abstract: PyGuitarPro writes no fret for one and the reader reconstructs it from
        the last note on that string, so a tie claims "same pitch as last time here".

        Walking bass falsifies that claim. The engine picks the thumb's string from the
        *current* step's thinned voicing rather than the shape still ringing, so on a
        `bass_only` step it can put the thumb on a string the held shape occupies. The
        tie then resolves to the thumb's fret, and the file states a pitch the engine
        never produced - an A5 where the arrangement holds A6, silently.

        The fixture is a committed head rather than a synthetic one because the defect
        needs the engine to actually collide, which the simple single-chord fixtures
        never do.
        """
        import tabgp
        from headxml import arrange_xml_head
        from tests.test_headxml import BUT_NOT_FOR_ME

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            steps, _, _ = arrange_xml_head(
                BUT_NOT_FOR_ME, grips=("shell",), texture="walking_bass"
            )
        song = _parse(
            io.BytesIO(format_gp5(steps, beats_per_bar=2, beat_type=2))
        )

        # Rebuild what the writer *meant* to say, from the builder's own model rather
        # than from the parsed file: that is the only way to see the corruption, since
        # the file agrees with itself either way.
        holder = {}
        real_build = tabgp._build_song

        def capture(gp_module, measures, *args, **kwargs):
            built = real_build(gp_module, measures, *args, **kwargs)
            holder["song"] = built
            return built

        tabgp._build_song = capture
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                format_gp5(steps, beats_per_bar=2, beat_type=2)
        finally:
            tabgp._build_song = real_build

        built = holder["song"].tracks[0].measures
        parsed = song.tracks[0].measures
        self.assertEqual(len(built), len(parsed))

        compared = 0
        for index, (memory_measure, file_measure) in enumerate(zip(built, parsed)):
            memory_beats = memory_measure.voices[0].beats
            file_beats = file_measure.voices[0].beats
            self.assertEqual(len(memory_beats), len(file_beats), f"bar {index + 1}")
            for memory_beat, file_beat in zip(memory_beats, file_beats):
                wanted = sorted((n.string, n.value) for n in memory_beat.notes)
                got = sorted((n.string, n.value) for n in file_beat.notes)
                compared += 1
                self.assertEqual(
                    wanted,
                    got,
                    f"bar {index + 1}: the file's pitches differ from the "
                    f"arrangement's, so a tie resolved to the wrong fret",
                )
        self.assertGreater(compared, 0, "the fixture produced no beats to compare")

    def test_the_fixture_actually_collides(self):
        """
        The premise of the test above, asserted so it cannot pass by going vacuous.

        If the engine stopped putting the thumb on a string the held shape occupies -
        which is the better fix, and is worth doing - the round trip above would pass
        trivially. This says whether the collision is still present, so the tie
        handling is known to be exercised rather than merely unexercised.
        """
        from headxml import arrange_xml_head
        from tests.test_headxml import BUT_NOT_FOR_ME

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            steps, _, _ = arrange_xml_head(
                BUT_NOT_FOR_ME, grips=("shell",), texture="walking_bass"
            )

        ringing = None
        collisions = 0
        for step in steps:
            voicing = step.voicing
            if step.bass_only and ringing is not None:
                thumb = voicing.bass_string
                if thumb is not None and ringing[thumb] >= 0:
                    collisions += 1
            if not step.bass_only and not step.repeated:
                ringing = list(voicing.frets)
        self.assertGreater(
            collisions,
            0,
            "no thumb now shares a string with the held shape, so the tie "
            "handling above is no longer being exercised",
        )


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
