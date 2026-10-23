"""Tests for the MusicXML importer in `headxml`: reading a document, not arranging one.

Nothing here is `skipUnless`-guarded, and that is the point: unlike the exporter,
the importer needs no optional dependency, so its whole suite runs on a fresh
clone - and the four real scores it reads are committed in `tests/data/`, so
nothing is skipped for want of a file either. A missing fixture is a broken
checkout, not a reason to pass quietly.

The tests build their own scores where a specific structure is what is under
test, and read the committed ones where a real score is what is under test - a
hand-written document proves the parser agrees with itself, not that it reads
what MuseScore and music21 actually write.

This file is the document itself: chord symbols, the key signature, the
instrument's transposition, and the note walk with its tie merge. Where a chord is
in force is `test_headxml_timeline.py`, arranging the result is
`test_headxml_arrangement.py`, repeats are `test_headxml_repeats.py`, and the head
CLI is `test_headxml_cli.py`.
"""

import os
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree

from arranger import ChordParser
from arranger.options import ArrangeOptions, Request
from arranger.tuning import NO_CHORD
from headxml import (
    Head,
    _key_label,
    _part_is_tab,
    arrange_xml_head,
    load_musicxml,
    parse_musicxml_chord,
)
from tests.support import (
    BUT_NOT_FOR_ME,
    CHORDS_ONLY,
    I_WAS_DOING_ALL_RIGHT,
    RAINY_DAY,
    TENOR_MADNESS,
    TROUBLE_IN_MIND,
    degree,
    harmony,
    note,
    rest,
    score,
    write_score,
)


class TestChordParsing(unittest.TestCase):
    """MusicXML's own chord notation translated into the library's qualities."""

    def parse(self, xml: str):
        return parse_musicxml_chord(ElementTree.fromstring(xml))

    def test_plain_kinds(self):
        """A kind with no alteration resolves to the library quality."""
        self.assertEqual(self.parse(harmony("C", "major")), ("C", "maj", None))
        self.assertEqual(self.parse(harmony("A", "minor")), ("A", "m", None))
        self.assertEqual(self.parse(harmony("G", "dominant")), ("G", "7", None))
        self.assertEqual(self.parse(harmony("F", "major-seventh")), ("F", "maj7", None))
        self.assertEqual(self.parse(harmony("D", "minor-ninth")), ("D", "m9", None))

    def test_the_root_alteration_makes_the_accidental(self):
        """`root-step` B with `root-alter` -1 is Bb, which the library can read."""
        self.assertEqual(self.parse(harmony("Bb", "dominant")), ("Bb", "7", None))
        self.assertEqual(self.parse(harmony("F#", "major")), ("F#", "maj", None))

    def test_a_slash_bass_is_split_out_not_glued_on(self):
        """The bass is returned separately, so the quality stays a bare '7'.

        Glued onto the quality it would be '7/F', which matches no table - the
        same trap `arranger.chords.slash_bass` documents for a slash chord.
        """
        self.assertEqual(self.parse(harmony("G", "major-ninth", bass="F#")), ("G", "maj9", "F#"))
        self.assertEqual(self.parse(harmony("D", "dominant", bass="C")), ("D", "7", "C"))

    def test_a_degree_turns_a_kind_into_an_altered_chord(self):
        """A dominant with a flat 5th is a 7b5, not a plain 7.

        This is how MuseScore writes one, and "Synthetic Repeat Slash" is full of
        them: an E7b5 under an F melody line.
        """
        self.assertEqual(
            self.parse(harmony("E", "dominant", degrees=degree(5, -1))), ("E", "7b5", None)
        )
        self.assertEqual(
            self.parse(harmony("E", "dominant", degrees=degree(9, -1, "add"))), ("E", "7b9", None)
        )
        self.assertEqual(
            self.parse(harmony("E", "dominant", degrees=degree(13, 0, "add"))), ("E", "13", None)
        )

    def test_several_degrees_are_applied_in_order(self):
        """Each degree refines the last, so a chord with two alterations lands
        on the quality the writer meant rather than on whichever matched first."""
        self.assertEqual(
            self.parse(
                harmony("D", "dominant", degrees=degree(5, -1) + degree(9, -1, "add"))
            ),
            ("D", "7b9", None),
        )

    def test_the_text_attribute_rescues_an_unclassifiable_kind(self):
        """`<kind text="Bb7sus4">other</kind>` is how this library writes a chord
        music21 cannot classify, so reading it is what makes the round trip work."""
        self.assertEqual(self.parse(harmony("Bb", "other", text="Bb7sus4")), ("Bb", "7sus4", None))

    def test_the_text_attribute_rescues_a_musicscore_3_1_only_kind(self):
        """The 4.0 sus kinds are in the table directly, not only via `text`."""
        self.assertEqual(
            self.parse(harmony("C", "suspended-fourth-seventh")), ("C", "7sus4", None)
        )

    def test_a_chord_this_library_cannot_voice_is_reported_not_guessed(self):
        """An untranslatable kind yields None, which the caller counts.

        `Neapolitan` is a real MusicXML kind and a real chord; it is simply not
        one this library holds under a melody, so it is reported rather than
        folded into a near neighbour.
        """
        for kind in ("Neapolitan", "Italian", "French", "German", "pedal", "power", "Tristan", "none"):
            with self.subTest(kind=kind):
                root, quality, _ = self.parse(harmony("C", kind))
                self.assertEqual(root, "C")
                self.assertIsNone(quality)

    def test_every_kind_the_table_names_is_voiceable(self):
        """A table entry naming a quality the voicing tables do not hold would
        fail silently at voicing time, so it fails here instead."""
        from headxml import MUSICXML_KIND_QUALITIES

        for kind, quality in MUSICXML_KIND_QUALITIES.items():
            with self.subTest(kind=kind):
                self.assertIn(quality, ChordParser.CHORD_TONES_FROM_ROOT)


class TestLoading(unittest.TestCase):
    """Reading a score into a Head: timing, harmony, ties and part selection."""

    def load(self, measures: str, **kwargs) -> Head:
        path = write_score(score(measures, **kwargs))
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    def test_a_plain_document_reads(self):
        """A bare .musicxml file needs no container and no optional dependency."""
        head = self.load(harmony("C", "major") + note("E"))
        self.assertEqual(len(head), 1)
        self.assertEqual(head.notes[0].note_name, "E4")
        self.assertEqual(head.notes[0].chord, "Cmaj")

    def test_a_zipped_container_is_read_through_its_rootfile(self):
        """The score is read through META-INF/container.xml, not by position.

        The archive this builds puts a decoy XML member *before* the score and
        names the real one in the container, which is exactly the case a
        "first .xml in the zip" reader gets wrong - and it fails silently rather
        than raising, which is the worst way to fail.
        """
        path = write_score(
            score(harmony("C", "major") + note("E")), suffix=".mxl", container=True
        )
        self.addCleanup(os.unlink, path)
        head = load_musicxml(path)
        self.assertEqual([n.note_name for n in head.notes], ["E4"])

    def test_a_zip_without_a_container_falls_back_to_the_largest_member(self):
        """A container that is merely a zip still reads rather than raising."""
        handle, path = tempfile.mkstemp(suffix=".mxl")
        os.close(handle)
        self.addCleanup(os.unlink, path)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("small.xml", "<x/>")
            archive.writestr("score.xml", score(harmony("C", "major") + note("E")))
        self.assertEqual([n.note_name for n in load_musicxml(path).notes], ["E4"])

    def test_a_malformed_container_falls_back_to_the_largest_member(self):
        """A container that is not well-formed XML still reads rather than raising.

        93 of the 502 scores in the OpenEWLD corpus carry a `META-INF/container.xml`
        that is not well-formed, because the writer emitted the score's filename
        into a single-quoted attribute without escaping it - `Core 'ngrato.xml`
        becomes `<rootfile full-path='Core 'ngrato.xml'/>`, which no parser will
        accept. Every one of those archives holds a perfectly readable score, so a
        `ParseError` propagating out of the container read loses a head that is
        sitting right there, and it is exactly the failure the largest-member
        fallback exists to prevent.

        The document is built to look like the real thing: a decoy member beside the
        score, so a reader that just takes the first `.xml` still gets it wrong.
        """
        handle, path = tempfile.mkstemp(suffix=".mxl")
        os.close(handle)
        self.addCleanup(os.unlink, path)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/container.xml",
                "<?xml version='1.0' encoding='UTF-8'?><container><rootfiles>"
                "<rootfile full-path='Core 'ngrato.xml'/></rootfiles></container>",
            )
            archive.writestr("META-INF/other.xml", "<junk/>")
            archive.writestr("Core 'ngrato.xml", score(harmony("C", "major") + note("E")))
        self.assertEqual([n.note_name for n in load_musicxml(path).notes], ["E4"])

    def test_a_harmony_holds_until_the_next_one(self):
        """A bar with no harmony at all is ordinary, and the chord carries on.

        the synthetic cut-time head has bars with no `<harmony>`, so reading the chord off the
        note that follows it would drop the harmony from those bars entirely.
        """
        head = self.load(
            harmony("C", "major") + note("E") + harmony("F", "dominant") + note("F")
        )
        self.assertEqual([n.chord for n in head.notes], ["Cmaj", "F7"])

    def test_several_chords_in_one_bar_are_taken_at_their_own_notes(self):
        """A chord change part way through a bar governs only what follows it."""
        head = self.load(
            harmony("G", "major-ninth", bass="F#") + note("D")
            + harmony("Bb", "dominant", bass="F") + note("D")
        )
        self.assertEqual([(n.chord, n.bass) for n in head.notes], [("Gmaj9", "F#"), ("Bb7", "F")])

    def test_a_note_before_any_chord_has_none(self):
        """Melody under no harmony is melody alone, not a guessed chord."""
        head = self.load(note("E") + harmony("C", "major") + note("G"))
        self.assertEqual(head.notes[0].chord, NO_CHORD)
        self.assertTrue(head.notes[0].is_no_chord)
        self.assertEqual(head.notes[1].chord, "Cmaj")

    def test_cut_time_places_beats_in_the_notated_beat(self):
        """A 2/2 bar is two beats wide, so a quarter note is on beat 1.5.

        Three of the four real scores here are in cut time. Dividing by the beat
        type is what stops a 2/2 bar being read as four beats wide, which would
        put every chord on the wrong beat of the bar.
        """
        # divisions=8, so a quarter is 8 and a 2/2 bar is 32 of them.
        head = self.load(
            note("E", duration=8) + note("F", duration=8) + note("G", duration=16),
            divisions=8, beats=2, beat_type=2,
        )
        self.assertEqual([n.beat for n in head.notes], [1.0, 1.5, 2.0])
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))

    def test_a_tuplet_note_is_divided_down(self):
        """A triplet's written duration is unreduced, and dividing it keeps the
        bar in time.

        Three eighth-note triplets are written as 6 divisions each here, which is
        18 unreduced; they occupy a quarter (12 divisions), not one and a half
        quarters. Without the division every bar after the first drifts a third
        long and the whole head slides out of time.
        """
        # divisions=12, so a quarter is 12 and a triplet eighth is 4.
        head = self.load(
            note("E", duration=6, tuplet=True)
            + note("F", duration=6, tuplet=True)
            + note("G", duration=6, tuplet=True),
            divisions=12,
        )
        self.assertEqual([n.duration for n in head.notes], [1 / 12, 1 / 12, 1 / 12])
        # And they land a third of a beat apart, ending on beat 2 - a full bar.
        self.assertEqual([round(n.beat, 6) for n in head.notes], [1.0, 1.333333, 1.666667])

    def test_a_tie_across_a_bar_line_is_one_note(self):
        """A held note is one slot of the summed length, not two notes.

        This is the whole point of the renderers' `repeated` hold: a note tied
        across a bar line is one sound, and voicing it twice would put a chord
        change in the middle of it.
        """
        # divisions=4 per quarter: each half note is 8, and the two halves tied
        # across the bar line make one whole note.
        document = f"""<?xml version="1.0"?>
<score-partwise version="3.1"><part-list><score-part id="P1"/></part-list><part id="P1">
<measure number="1"><attributes><divisions>4</divisions></attributes>
  {harmony("C", "major")}{note("E", duration=8, tie="start")}{rest(8)}
</measure>
<measure number="2">{note("E", duration=8, tie="stop")}</measure>
</part></score-partwise>"""
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        head = load_musicxml(path)
        self.assertEqual(len(head), 1)
        self.assertEqual(head.notes[0].duration, 1.0)
        self.assertEqual(head.notes[0].bar, 1)

    def test_a_lyric_is_read_without_a_committed_fixture_carrying_one(self):
        """The importer still reads `<lyric>`, on a score made for this question.

        The synthetic corpus carries no lyrics. Keeping the branch covered here
        means the fixtures can stay free of text nobody's tests read.
        """
        head = self.load(harmony("C", "major") + note("E", lyric="la"))
        self.assertEqual(head.notes[0].lyrics, ("la",))

    def test_rests_and_unpitched_notes_are_skipped_and_counted(self):
        """A rest is not a melody note, and dropping it silently would hide it."""
        head = self.load(harmony("C", "major") + rest(4) + note("E"))
        self.assertEqual(len(head), 1)
        self.assertTrue(any("rests" in s for s in head.skipped))

    def test_the_melody_is_the_top_line_of_a_chord_group(self):
        """A chord group reduces to its highest note.

        Only the *first* member of a `<chord>` group is unmarked, and MusicXML does
        not order the group by pitch - so reading the unmarked note would take the
        lowest of a descending shape, which is the bass, not the tune. The notes
        below are written out of pitch order on purpose.
        """
        head = self.load(
            harmony("C", "major")
            + note("C") + note("E", chord=True) + note("G", chord=True)
        )
        self.assertEqual([n.note_name for n in head.notes], ["G4"])
        self.assertTrue(any("chord group" in s for s in head.skipped))

    def test_a_chord_the_library_cannot_voice_is_counted_not_guessed(self):
        """It is reported in `unmapped` and the note keeps the previous chord.

        Guessing a near neighbour would sound a chord the score did not write;
        counting it is the same rule the Weimar table follows.
        """
        head = self.load(
            harmony("C", "major") + note("E")
            + harmony("C", "Neapolitan") + note("F")
        )
        self.assertIn("Neapolitan", " ".join(head.unmapped))
        self.assertTrue(any("cannot voice" in written for written in head.report))


class TestRealScores(unittest.TestCase):
    """The committed scores, read as a notation program or the generator wrote them.

    Hand-written fixtures prove the parser agrees with itself. These prove it
    reads the structures the committed files actually use: a container, a
    cross-barline tie, a TAB part, slash basses, degrees and 10080-division
    triplets.
    """

    def test_a_musescore_style_export_reads_its_chords_and_slash_basses(self):
        """The repeat head carries slash chords and a degree-written alteration."""
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.title, "Synthetic Repeat Slash")
        self.assertEqual(head.composer, "Fixture Generator")
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        chords = {n.chord for n in head.notes}
        # Gmaj9, Bb7 and Am7 are the first three changes, and the F# under the
        # Gmaj9 is a `<bass>` the file spells rather than part of the quality.
        self.assertIn("Gmaj9", chords)
        self.assertIn("Bb7", chords)
        self.assertIn("Am7", chords)
        self.assertTrue(any(n.bass == "F#" for n in head.notes))

    def test_a_degree_written_chord_becomes_the_chord_it_spells(self):
        """An E7b5 is `dominant` plus a flat 5th degree, not a plain dominant."""
        head = load_musicxml(RAINY_DAY)
        self.assertIn("E7b5", {n.chord for n in head.notes})

    def test_every_chord_in_a_committed_score_is_voiceable_or_reported(self):
        """Nothing is dropped silently: what cannot be voiced is counted."""
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.unmapped, ())

    def test_a_zipped_export_reads(self):
        """The cut-time head is a zipped .mxl with a leading rest and a tie."""
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertEqual(head.title, "Synthetic Cut Time")
        self.assertEqual(head.composer, "Fixture Generator")
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        self.assertEqual(len(head), 20)
        self.assertEqual(head.notes[0].note_name, "F4")
        self.assertEqual(head.notes[0].chord, "Bb7")
        # No committed fixture carries a lyric; the importer's lyric branch has
        # its own tiny fixture in `TestLoading`.
        self.assertEqual(head.notes[0].lyrics, ())

    def test_a_bar_whose_harmony_arrives_mid_bar_is_read_in_order(self):
        """Bar 3 opens with a tie-stop and declares Bb7 after it.

        So the first *emitted* note of bar 3 is the first note Bb7 governs.
        Reading the harmony as belonging to the bar it starts in, or to the note
        before it, would put that note under the Cm7 that bar 2 ends on.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        bar_three = [n for n in head.notes if n.bar == 3]
        self.assertTrue(bar_three)
        self.assertEqual(bar_three[0].note_name, "F4")
        self.assertEqual(bar_three[0].chord, "Bb7")
        # And bar 2 really does end on a different chord, so the two differ.
        bar_two = [n for n in head.notes if n.bar == 2]
        self.assertEqual(bar_two[-1].chord, "Cm7")
        self.assertNotEqual(bar_two[-1].chord, bar_three[0].chord)

    def test_a_tied_note_becomes_one_voice(self):
        """The file ties a note across a bar line, and it must not become two.

        Two notes where the score has one would put a chord change in the middle
        of a held note - the exact failure the renderers' `repeated` hold exists
        to prevent, and it starts at the loader. The tie is the `Eb4` at bar 2's
        last quarter, continued into bar 3's downbeat.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        tied = [n for n in head.notes if n.note_name == "Eb4" and n.bar == 2]
        self.assertEqual(len(tied), 1)
        self.assertAlmostEqual(tied[0].duration, 0.5)
        self.assertEqual([n for n in head.notes if n.bar == 3 and n.beat == 1.0], [])

    def test_this_librarys_own_export_reads_back(self):
        """A score with a TAB staff beside a notation one is read from the notation.

        Reading the TAB part would double every note, since a MusicXML tab staff
        writes one `<note>` per string.
        """
        head = load_musicxml(TENOR_MADNESS)
        self.assertEqual(head.title, "Synthetic Tab Export")
        self.assertEqual(head.part, "Synthetic Tab Export")
        # The chord groups must have been reduced to their top line rather than
        # every string's note read as melody.
        self.assertTrue(any("chord group" in s for s in head.skipped))

    def test_a_tab_part_is_recognised_by_its_clef_not_its_name(self):
        """The six-line staff is identified by `<clef><sign>TAB</sign>`.

        Naming it in `<part-name>` would be a coincidence of one file; the clef is
        what makes it a tab staff, and it is what this library's own export writes.
        Both parts here carry the same number of notes, so the choice can only be
        made by the clef.
        """
        measures = harmony("C", "major") + note("E") * 4
        document = f"""<?xml version="1.0"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="TAB"><part-name>TAB</part-name></score-part>
    <score-part id="P2"><part-name>Lead</part-name></score-part>
  </part-list>
  <part id="TAB">
    <measure number="1">
      <attributes><divisions>4</divisions><clef><sign>TAB</sign><line>5</line></clef></attributes>
      {measures}
    </measure>
  </part>
  <part id="P2">
    <measure number="1"><attributes><divisions>4</divisions></attributes>{measures}</measure>
  </part>
</score-partwise>"""
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        root = ElementTree.fromstring(document)
        tab_part, lead_part = root.findall("part")
        self.assertTrue(_part_is_tab(tab_part))
        self.assertFalse(_part_is_tab(lead_part))
        head = load_musicxml(path)
        self.assertEqual(head.part, "Lead")
        self.assertEqual(len(head), 4)

        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertIn(65, [n.pitch for n in head.notes])  # F4, the opening note
        # A tie is merged, so no two consecutive notes share a pitch *and* a
        # position - the merged note keeps the first one's onset.
        for before, after in zip(head.notes, head.notes[1:]):
            if before.pitch == after.pitch and before.bar == after.bar:
                self.assertNotEqual(before.beat, after.beat)

    def test_a_score_with_tuplets_stays_in_time(self):
        """The triplet head is a piano part in 10080 divisions.

        Reading its triplet durations unreduced would drift every bar after the
        first, so the total written time is checked against the bars it spans: a
        2/2 bar is a whole note, and an undivided reader runs a third long.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertEqual(head.title, "Synthetic Triplets")
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        bars = head.bars[1] - head.bars[0]
        written = sum(n.duration for n in head.notes)
        self.assertAlmostEqual(written, float(bars), delta=bars * 0.2)


class TestAHeldNoteIsOneNoteAcrossABarline(unittest.TestCase):
    """`Trouble in Mind`: ties written across barlines, on a real 4/4 blues.

    **This fixture is here because of a misdiagnosis, and the reason is the point.**
    A guard was once added to `headxml._flush_group` - `and notes[-1].bar == bar` -
    on the belief that merging a tie-stop into the previous note "ate the new bar's
    downbeat" on this head. It does the opposite. A `tie type="stop"` in a new bar
    *is* the continuation the merge exists to absorb, so the guard turned every
    cross-barline tie into a second note at the same pitch: **53 notes became 63
    here**, and `synthetic_cut_time` went 80 to 84. Ten tests failed against it.

    The premise read **merged** as **lost**. Bars 8, 16 and 17 carry no note of their
    own, and the second and third tests below say why that is correct rather than
    alarming. Verified by mutation: adding the guard back fails **4 of the 5** - the
    fifth asserts the fixture's premises, which hold either way.

    The synthetic counterpart is `TestLoading.test_a_tie_across_a_bar_line_is_one_note`;
    this one is on a file a notation program wrote, which is the only thing that can
    show the rule survives real bar lengths, real divisions and real ties.
    """

    def setUp(self):
        self.head = load_musicxml(TROUBLE_IN_MIND)

    def _notes_in(self, bar):
        return [n for n in self.head.notes if n.bar == bar]

    def test_the_fixture_really_does_tie_across_barlines(self):
        """The premise, asserted on the file's own `<tie>` elements.

        Without this the rest of the class could pass on a fixture that stopped
        containing the thing it exists to check.
        """
        root = ElementTree.parse(TROUBLE_IN_MIND).getroot()
        starts = sum(
            1 for tie in root.iter("tie") if tie.get("type") == "start"
        )
        stops = sum(1 for tie in root.iter("tie") if tie.get("type") == "stop")
        self.assertGreater(starts, 0, "the fixture must contain tie starts")
        self.assertGreater(stops, 0, "the fixture must contain tie stops")
        # At least one stop is the first note of its measure, which is the only
        # arrangement that makes a tie cross a barline rather than sit inside one.
        boundaries = 0
        for measure in root.iter("measure"):
            notes = measure.findall("note")
            if notes and any(t.get("type") == "stop" for t in notes[0].findall("tie")):
                boundaries += 1
        self.assertGreater(
            boundaries, 0, "the fixture must contain a tie crossing a barline"
        )

    def test_the_two_halves_of_a_tie_are_one_note(self):
        """Bar 2's A4 eighth and bar 3's A4 half are one note of 3.5 beats.

        The merge is what makes that true, and its length is the proof it happened:
        a note that was never extended is a quarter of a whole note, not 0.875.
        """
        last = self._notes_in(2)[-1]
        self.assertEqual((last.beat, last.note_name), (4.5, "A4"))
        self.assertAlmostEqual(last.duration, 0.875, places=6)
        # And it is *one* note: bar 3 opens with no note at all, because its downbeat
        # is still sounding this one. A duplicate would sit at bar 3 beat 1.0.
        self.assertEqual([n.beat for n in self._notes_in(3) if n.beat < 2.0], [])

    def test_a_bar_covered_by_a_held_note_carries_no_note_of_its_own(self):
        """Bar 8 is empty, and the note that empties it is asserted, not assumed.

        **This is what the misdiagnosis read as data loss.** Bar 7's A4 is held for
        5.5 beats from beat 4.5: half a beat to the barline, all four beats of bar 8,
        and one more beat into bar 9. It therefore ends on bar 9 beat 2.0, which is
        exactly where bar 9's written rests begin. Bar 8 having no note is the tie
        working, and the arithmetic below is what makes that checkable rather than
        merely asserted.
        """
        self.assertEqual(self._notes_in(8), [], "bar 8 must be covered, not dropped")
        held = self._notes_in(7)[-1]
        self.assertEqual((held.beat, held.note_name), (4.5, "A4"))
        self.assertAlmostEqual(held.duration * 4.0, 5.5, places=6)
        # Quarters from the start of bar 7: the note starts 3.5 in, and bar 9 beat 1.0
        # is 8.0 in, so ending 1.0 quarter past that is bar 9 beat 2.0 - where the
        # rests in bar 9 begin.
        end = (held.beat - 1.0) + held.duration * 4.0
        self.assertAlmostEqual(end, 9.0, places=6)
        self.assertAlmostEqual(end - 8.0, 1.0, places=6)

    def test_the_held_note_outlasts_the_last_note_and_bars_reports_the_file(self):
        """`Head.bars` is a fact about the *file*, so it does not stop at the note.

        A chords-only head has no notes to measure and still knows how long it is, so the
        measure extent is the file's. This file runs to measure 17, so the range is
        `(1, 18)`: the last note begins in bar 15 and is held to bar 17 beat 2.0, and the
        range reaches that bar rather than stopping short of it.

        The note's own sound past bar 15 is still carried by its duration, and the
        arithmetic that proves it is kept - that part was never about `bars`.
        """
        self.assertEqual(self.head.bars, (1, 18))
        last = self._notes_in(15)[-1]
        self.assertEqual((last.beat, last.note_name), (4.5, "G4"))
        # Two whole bars is 8.0 quarters, so 9.0 lands inside bar 17 - which the file's
        # own last measure is, now that the range is the file's rather than the tune's.
        self.assertAlmostEqual((last.beat - 1.0) + last.duration * 4.0, 9.0, places=6)

    def test_no_note_is_duplicated_where_two_are_tied(self):
        """53 notes, and no two consecutive ones share a barline and a pitch.

        The count is the blunt check; the scan is the one that names the defect if a
        future change reintroduces it, because it fails on the *pair* rather than on a
        total that has to be re-baselined every time the fixture is re-read.
        """
        self.assertEqual(len(self.head.notes), 53)
        for before, after in zip(self.head.notes, self.head.notes[1:]):
            if before.pitch == after.pitch and before.bar != after.bar:
                self.fail(
                    f"bar {before.bar} and bar {after.bar} both sound "
                    f"{after.note_name}: a tie became two notes"
                )


class TestChordsOnlyHead(unittest.TestCase):
    """§9.3 step A': a chords-only lead sheet is a valid input.

    Four bars, six `<harmony>` elements, **zero pitched notes** — measured, the loader
    used to refuse it outright (`has no readable melody part`) because `_choose_part`
    selected on the note count alone. It now reads, reports its metre and bar count, and
    arranges **the whole head**.

    The default grid's silence here was `docs/history/open-issues.md` item 1's extreme case, and
    it is now fixed: a bar the melody never enters is added beat for beat, so a head with
    *no* melody at all gets all of its bars. A **melody-only** selection still gets
    nothing — it plays the tune and nothing else, and there is no tune — and that is the
    one refusal left, deliberately.
    """

    def setUp(self):
        self.head = load_musicxml(CHORDS_ONLY)

    def test_the_loader_accepts_it_and_reports_the_files_length(self):
        """It loads, and `bars` is the file's four measures, not `(1, 1)`.

        The measurement §9.5 records as the probe: `Head.bars` returned `(1, 1)` for
        this file because it was derived from notes that do not exist. Now it is the
        file's own measure extent, so a head with no melody still knows how long it is.
        """
        self.assertEqual(len(self.head.notes), 0)
        self.assertEqual(len(self.head.chords), 6)
        self.assertEqual(self.head.bars, (1, 5))
        self.assertEqual((self.head.beats_per_bar, self.head.beat_type), (4, 4))

    def test_the_default_grid_arranges_every_bar(self):
        """A bar the melody never enters is added, so a head with no melody gets all of it.

        The union is at the level of the **bar**, so a melody-less head is fully arranged
        and a note-bearing bar is untouched; `every_note`'s deference to the melody
        survives where it is load-bearing, which is inside a bar the tune already
        articulates. A chord in force must produce a part rather than nothing at all —
        `docs/history/open-issues.md` item 1 is that defect.

        The soprano refusal below is the one case that did not move, and it is a different
        claim: a melody-only selection has nothing to *play* here, which is not the same
        as a grid having nowhere to *place* a chord.
        """
        steps, _head, _notes = arrange_xml_head(
            CHORDS_ONLY, options=ArrangeOptions(request=Request(melody=False))
        )
        self.assertEqual(len(steps), 16, "four bars, four beats each")
        self.assertEqual((steps[0].bar, steps[0].beat), (1, 1.0))
        self.assertTrue(
            all(step.melody is None for step in steps),
            "a chords-only head has no tune to invent",
        )

    def test_a_soprano_only_selection_arranges_nothing(self):
        """A melody-only selection routes to the melody-bearing branch, where there is
        no tune.

        **This is the one refusal left, and it is not the same claim as the grid's
        deference.** `every_note` used to be silent here too, and that was the defect; a
        melody-only selection is silent because it *plays the tune and nothing else*, so a
        bar with no tune has nothing for it to play. A grid can place a chord there and a
        soprano cannot voice one without a top note. `parts_has_melody_only` gates the
        union in `arrange_xml_head`, which is why this still returns nothing while
        `alto,tenor` above now returns all four bars.
        """
        steps, _head, _notes = arrange_xml_head(
            CHORDS_ONLY, options=ArrangeOptions(request=Request(chord_on="none"))
        )
        self.assertEqual(steps, [])

    def test_a_named_rhythm_places_the_chords(self):
        """Three rhythms, three parts: the payoff, and the shape `--chord-on` asks with.

        Exactly the rhythm each names on a 4/4 bar: `every-beat` a chord on every beat
        (16 = 4 bars x 4), the *ands* on the ands (first at bar 1 beat 1.5), and
        `lastand` on the final beat's upbeat (first at bar 1 beat 4.5). Every slot
        carries `parts="None"`, because the file has no tune — the honest absence step B
        made expressible, not the deleted placeholder.

        `lastand` is the metre-relative spelling of the old `final_and` preset: the
        grammar's `last` resolves per bar, so one request is the last upbeat of every
        bar of any metre.
        """
        expected = {
            "every-beat": ((1.0, "Dm7"), 16),
            "1and,2and,3and,4and": ((1.5, "Dm7"), 16),
            "lastand": ((4.5, "Dm7"), 4),
        }
        for rhythm, (first, count) in expected.items():
            with self.subTest(rhythm=rhythm):
                steps, _head, _notes = arrange_xml_head(
                    CHORDS_ONLY,
                    request=Request(melody=False, chord_on=rhythm),
                )
                self.assertEqual(len(steps), count, f"chord_on={rhythm}")
                self.assertEqual((steps[0].beat, steps[0].chord), first)
                self.assertTrue(
                    all(step.melody is None for step in steps),
                    f"chord_on={rhythm} invented a melody for a chords-only head",
                )


class TestKeySignature(unittest.TestCase):
    """Reading a `<key>`, which is what the export needs to state the right key.

    Without this the head is C major whatever the score says, so an Eb-major tune
    exports with a flat written on every note of its own scale.
    """

    def load(self, measures: str, **kwargs) -> Head:
        path = write_score(score(measures, **kwargs))
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    def test_the_signature_reaches_the_head(self):
        """Three flats and a mode, read as the two numbers MusicXML states."""
        head = self.load(
            harmony("Eb", "major") + note("G"),
            fifths=-3, mode="<mode>major</mode>",
        )
        self.assertEqual((head.key_fifths, head.key_mode), (-3, "major"))

    def test_a_sharp_key_is_positive(self):
        """The count is signed: one sharp is 1 and is not one flat."""
        head = self.load(
            harmony("G", "major") + note("B"), fifths=1, mode="<mode>major</mode>"
        )
        self.assertEqual((head.key_fifths, head.key_mode), (1, "major"))

    def test_a_minor_key_is_carried_not_assumed(self):
        """The same three flats is Eb major or C minor, and the mode says which."""
        head = self.load(
            harmony("Cm", "minor") + note("G"), fifths=-3, mode="<mode>minor</mode>"
        )
        self.assertEqual(head.key_mode, "minor")

    def test_a_score_with_no_signature_is_c_major(self):
        """An absent `<key>` states no accidentals, which *is* C major.

        Read as "unknown" this would be a different default; reading it as C major
        is what lets such a score export exactly as it always did.
        """
        head = self.load(harmony("C", "major") + note("E"))
        self.assertEqual((head.key_fifths, head.key_mode), (0, ""))

    def test_an_absent_mode_is_not_guessed(self):
        """`<mode>` is optional, so a signature alone says which two keys it is."""
        head = self.load(harmony("Eb", "major") + note("G"), fifths=-3)
        self.assertEqual((head.key_fifths, head.key_mode), (-3, ""))


    def test_the_last_signature_wins(self):
        """A score may modulate; the head is arranged in the key it ends in.

        The same rule as the metre, and for the same reason: the first `<key>` is
        not the one in force for most of the piece.
        """
        document = f"""<?xml version="1.0"?>
<score-partwise version="3.1"><part-list><score-part id="P1"/></part-list><part id="P1">
<measure number="1"><attributes><divisions>4</divisions>
  <key><fifths>0</fifths><mode>major</mode></key></attributes>
  {harmony("C", "major")}{note("E", duration=4)}
</measure>
<measure number="2"><attributes><divisions>4</divisions>
  <key><fifths>-3</fifths><mode>major</mode></key></attributes>
  {rest(4)}
</measure>
</part></score-partwise>"""
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        self.assertEqual(load_musicxml(path).key_fifths, -3)

    def test_an_unusable_signature_reads_as_no_signature(self):
        """A `<fifths>` that is not a number is not worth losing the head over.

        MusicXML allows a `<key>` with no `<fifths>` at all, and some exporters write
        a malformed one; both are treated as "states no signature" rather than
        raised on, because the key is metadata and the melody is the content.
        """
        document = f"""<?xml version="1.0"?>
<score-partwise version="3.1"><part-list><score-part id="P1"/></part-list><part id="P1">
<measure number="1"><attributes><divisions>4</divisions>
  <key><mode>major</mode></key></attributes>
  {harmony("C", "major")}{note("E")}
</measure></part></score-partwise>"""
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        self.assertEqual(load_musicxml(path).key_fifths, 0)

    def test_a_signature_wider_than_seven_is_not_claimed(self):
        """Beyond seven of either is not a conventional signature this can state."""
        head = self.load(harmony("C", "major") + note("E"), fifths=-9)
        self.assertEqual(head.key_fifths, 0)

    def test_the_key_of_a_committed_score_is_read(self):
        """The cut-time head states three flats - Eb, not C."""
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertEqual((head.key_fifths, head.key_mode), (-3, "major"))


class TestKeyLabel(unittest.TestCase):
    """The CLI header names the key, because `-3 (major)` is not one a person reads."""

    def label(self, fifths: int, mode: str) -> str:
        return _key_label(Head(key_fifths=fifths, key_mode=mode))

    def test_the_tonic_follows_the_signature(self):
        """Both halves of the circle, from seven flats to seven sharps.

        -1 is F major and not E# major: one flat's worth is a signature read from
        the flat side, not one sharp short of the *other* spelling.
        """
        self.assertEqual(self.label(0, "major"), "C major")
        self.assertEqual(self.label(1, "major"), "G major")
        self.assertEqual(self.label(-1, "major"), "F major")
        self.assertEqual(self.label(-3, "major"), "Eb major")
        self.assertEqual(self.label(-5, "major"), "Db major")
        self.assertEqual(self.label(7, "major"), "C# major")

    def test_a_minor_key_is_the_relative_minor(self):
        """Three flats is C minor, not Eb minor: the mode picks of the two.

        Getting this wrong is not a cosmetic slip - it names a different key, and
        Eb minor has six flats rather than three.
        """
        self.assertEqual(self.label(-3, "minor"), "C minor")
        self.assertEqual(self.label(0, "minor"), "A minor")
        self.assertEqual(self.label(2, "minor"), "B minor")

    def test_an_unstated_mode_names_both_keys(self):
        """No mode is not a guess: it is the two keys the signature spells."""
        self.assertEqual(self.label(-3, ""), "Eb major/C minor")
        self.assertEqual(self.label(2, ""), "D major/B minor")

    def test_no_signature_is_one_key_not_two(self):
        """Zero is C major under either mode, so it is not listed twice."""
        self.assertEqual(self.label(0, ""), "C major")


class TestLoadingTail(unittest.TestCase):
    """Two loader cases kept apart so the class above stays readable."""

    def test_a_measure_number_that_is_not_an_integer_is_kept(self):
        """A bar labelled "12a" is still a bar; losing it over the label is a
        poor trade, so it is read at its running index and reported."""
        document = f"""<?xml version="1.0"?>
<score-partwise version="3.1"><part-list><score-part id="P1"/></part-list><part id="P1">
<measure number="12a"><attributes><divisions>4</divisions></attributes>
  {harmony("C", "major")}{note("E")}
</measure></part></score-partwise>"""
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        head = load_musicxml(path)
        self.assertEqual(len(head), 1)
        self.assertTrue(any("not numbered" in s for s in head.skipped))

    def test_a_document_that_is_not_a_score_says_so(self):
        """A readable file that is not MusicXML is a usage error, not a crash."""
        path = write_score("<html><body>not a score</body></html>")
        self.addCleanup(os.unlink, path)
        with self.assertRaises(ValueError) as caught:
            load_musicxml(path)
        self.assertIn("not a MusicXML score", str(caught.exception))


class TestTheInstrumentTranspositionIsRead(unittest.TestCase):
    """A part notated for a transposing instrument is arranged at **concert** pitch.

    MusicXML's `<transpose>` is *what is added to a written pitch to get the sounding
    pitch*, and guitar is the instrument this library itself writes: its part is
    notated an octave above it sounds, so `headxml` has to undo that or the exporter's
    own round trip comes back an octave high. A Bb instrument is the same rule with a
    different number and pins the *sign* - the reader adds the stated value rather
    than subtracting it, which an octave-only test cannot tell apart.
    """

    def load(self, measures: str, transpose: str) -> Head:
        path = write_score(score(measures, transpose=transpose))
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    def test_a_guitar_part_is_read_an_octave_below_its_notation(self):
        """`octave-change -1` is the guitar's own transposition, played back down."""
        head = self.load(
            note("E", octave=5),
            "<transpose><chromatic>0</chromatic><octave-change>-1</octave-change></transpose>",
        )
        self.assertEqual([n.note_name for n in head.notes], ["E4"])

    def test_a_bb_part_is_read_a_tone_below_its_notation(self):
        """`chromatic -2` moves a written C down to the sounding Bb."""
        head = self.load(
            note("C", octave=5),
            "<transpose><chromatic>-2</chromatic></transpose>",
        )
        self.assertEqual([n.note_name for n in head.notes], ["Bb4"])

    def test_a_part_with_no_transposition_is_concert_pitch(self):
        """The default is 0, so every committed head is read exactly as written."""
        head = self.load(note("C", octave=5), "")
        self.assertEqual([n.note_name for n in head.notes], ["C5"])


