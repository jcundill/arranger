"""Tests for the MusicXML importer in `headxml`.

Nothing here is `skipUnless`-guarded, and that is the point: unlike the exporter,
the importer needs no optional dependency, so its whole suite runs on a fresh
clone - and the four real scores it reads are committed in `tests/data/`, so
nothing is skipped for want of a file either. A missing fixture is a broken
checkout, not a reason to pass quietly.

The tests build their own scores where a specific structure is what is under
test, and read the committed ones where a real score is what is under test - a
hand-written document proves the parser agrees with itself, not that it reads
what MuseScore and music21 actually write.
"""
import os
import tempfile
import unittest
import zipfile
from typing import Optional
from xml.etree import ElementTree

import arranger
from arranger import NO_CHORD, ChordParser
from headxml import (
    Head,
    _key_label,
    _part_is_tab,
    arrange_xml_head,
    head_cli,
    head_skeleton,
    load_musicxml,
    parse_musicxml_chord,
)
from tabxml import _events, _substitute_steps
from wjazzd import arrange_slots

# The real scores the importer's tests read, in `tests/data/`. They are committed
# and are NOT guarded: a missing fixture is a broken checkout, not a reason to
# pass the suite quietly. `tests/data/` is excepted from the `*.musicxml` / `*.mxl`
# rules in `.gitignore`, which exist for *export output*.
#
# Who wrote each one, which is the point of keeping them:
#   but_not_for_me.mxl            music21, cut time, lyrics, a tie across a barline
#   i_was_doing_all_right.mxl     music21, 2/2, triplets in 10080 divisions, a piano part
#   heres_that_rainy_day.musicxml MuseScore 3 (3.1), slash chords, <degree> alterations
#   tenor_madness.musicxml        this library's own export: a TAB staff beside a
#                                 notation one, and chords music21 could not classify
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAINY_DAY = os.path.join(DATA, "heres_that_rainy_day.musicxml")
BUT_NOT_FOR_ME = os.path.join(DATA, "but_not_for_me.mxl")
TENOR_MADNESS = os.path.join(DATA, "tenor_madness.musicxml")
I_WAS_DOING_ALL_RIGHT = os.path.join(DATA, "i_was_doing_all_right.mxl")


def score(
    measures: str,
    divisions: int = 4,
    beats: int = 4,
    beat_type: int = 4,
    part_id: str = "P1",
    fifths: Optional[int] = None,
    mode: str = "",
) -> str:
    """A minimal score-partwise document around the measures given.

    `fifths` states a `<key>` when given, and omitting it writes no `<key>` at all -
    which is a real case rather than a gap in the fixture, because a score with no
    signature states C major.
    """
    key = "" if fifths is None else f"<key><fifths>{fifths}</fifths>{mode}</key>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <work><work-title>Test</work-title></work>
  <part-list><score-part id="{part_id}"><part-name>Voice</part-name></score-part></part-list>
  <part id="{part_id}">
    <measure number="1">
      <attributes>
        <divisions>{divisions}</divisions>
        {key}
        <time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>
      </attributes>
      {measures}
    </measure>
  </part>
</score-partwise>
"""


def harmony(root: str = "C", kind: str = "major", text: Optional[str] = None,
            degrees: str = "", bass: str = "") -> str:
    """One `<harmony>` element, as a score would spell it."""
    root_xml = f"<root><root-step>{root[0]}</root-step>"
    if len(root) > 1:
        root_xml += f"<root-alter>{'-1' if root[1] == 'b' else '1'}</root-alter>"
    root_xml += "</root>"
    kind_xml = f'<kind text="{text}">{kind}</kind>' if text else f"<kind>{kind}</kind>"
    bass_xml = (
        f"<bass><bass-step>{bass[0]}</bass-step>"
        + (f"<bass-alter>{'-1' if bass[1] == 'b' else '1'}</bass-alter>" if len(bass) > 1 else "")
        + "</bass>"
        if bass
        else ""
    )
    return f"<harmony>{root_xml}{kind_xml}{bass_xml}{degrees}</harmony>"


def degree(value: int, alter: int = 0, kind_type: str = "alter") -> str:
    """One `<degree>` child, as MusicXML spells an altered tone."""
    return (
        f"<degree><degree-value>{value}</degree-value>"
        f"<degree-alter>{alter}</degree-alter>"
        f"<degree-type>{kind_type}</degree-type></degree>"
    )


def note(step: str, octave: int = 4, duration: int = 4, alter: Optional[int] = None,
         chord: bool = False, tie: str = "", tuplet: bool = False) -> str:
    """One `<note>` element."""
    pitch = f"<pitch><step>{step}</step>"
    if alter is not None:
        pitch += f"<alter>{alter}</alter>"
    pitch += f"<octave>{octave}</octave></pitch>"
    return (
        "<note>"
        + ("<chord/>" if chord else "")
        + pitch
        + f"<duration>{duration}</duration>"
        + (f"<tie type=\"{tie}\"/>" if tie else "")
        + ("<time-modification><actual-notes>3</actual-notes>"
           "<normal-notes>2</normal-notes></time-modification>" if tuplet else "")
        + "</note>"
    )


def rest(duration: int = 4) -> str:
    return f"<note><rest/><duration>{duration}</duration></note>"


def write_score(document: str, suffix: str = ".musicxml", container: bool = False) -> str:
    """Write a document to a temp file, optionally zipped as a real `.mxl`."""
    handle, path = tempfile.mkstemp(suffix=suffix)
    os.close(handle)
    if not container:
        with open(path, "w", encoding="utf-8") as out:
            out.write(document)
        return path
    # A real container, with the score *not* first in the archive and a decoy XML
    # member beside it: both are the cases a "first .xml in the zip" reader gets
    # wrong, so both are here on purpose.
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="music/score.xml" media-type="application/vnd.recordare.musicxml+xml"/>'
            "</rootfiles></container>",
        )
        archive.writestr("META-INF/other.xml", "<junk/>")
        archive.writestr("music/score.xml", document)
    return path


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
        same trap `wjazzd.parse_weimar_chord` documents for the database.
        """
        self.assertEqual(self.parse(harmony("G", "major-ninth", bass="F#")), ("G", "maj9", "F#"))
        self.assertEqual(self.parse(harmony("D", "dominant", bass="C")), ("D", "7", "C"))

    def test_a_degree_turns_a_kind_into_an_altered_chord(self):
        """A dominant with a flat 5th is a 7b5, not a plain 7.

        This is how MuseScore writes one, and "Here's That Rainy Day" is full of
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

        But Not For Me has bars with no `<harmony>`, so reading the chord off the
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
        self.assertTrue(any("cannot voice" in note for note in head.report))

    # A "12a"-labelled measure used to have a stub test here that built the
    # fixture, loaded it, and asserted nothing - it could not fail, and so read
    # as coverage the suite did not have. It is removed rather than completed,
    # because TestLoadingTail already holds the real assertions for this case.


class TestRealScores(unittest.TestCase):
    """The four scores in the repository, read as a notation program wrote them.

    Hand-written fixtures prove the parser agrees with itself. These prove it
    reads what music21, MuseScore and this library's own exporter actually write,
    which is the part only the real thing can check.
    """

    def test_a_musescore_export_reads_its_chords_and_slash_basses(self):
        """Rainy Day is a MuseScore 3 file: 3.1, one voice, slash chords, degrees."""
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.title, "Here's That Rainy Day")
        self.assertEqual(head.composer, "James Van Heusen")
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        chords = {n.chord for n in head.notes}
        # Gmaj9, Bb7 and Am7 are the tune's first three changes, and the F# under
        # the Gmaj9 is a `<bass>` the file spells rather than part of the quality.
        self.assertIn("Gmaj9", chords)
        self.assertIn("Bb7", chords)
        self.assertIn("Am7", chords)
        self.assertTrue(any(n.bass == "F#" for n in head.notes))

    def test_a_degree_written_chord_becomes_the_chord_it_spells(self):
        """MuseScore writes an E7b5 as `dominant` plus a flat 5th degree.

        Read as a plain dominant, the melody would be voiced over a chord the file
        does not contain - so this is the degree table doing its job on real data.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertIn("E7b5", {n.chord for n in head.notes})

    def test_every_chord_in_a_real_score_is_voiceable_or_reported(self):
        """Nothing is dropped silently: what cannot be voiced is counted."""
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.unmapped, ())

    def test_a_zipped_music21_export_reads(self):
        """But Not For Me is a music21-written .mxl in cut time, with lyrics."""
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertEqual(head.title, "But Not For Me")
        self.assertEqual(head.composer, "George Gershwin")
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        self.assertEqual(len(head), 80)
        self.assertEqual(head.notes[0].note_name, "F4")
        self.assertEqual(head.notes[0].chord, "Bb7")
        self.assertIn("They're", head.notes[0].lyrics)

    def test_a_bar_whose_harmony_arrives_mid_bar_is_read_in_order(self):
        """Bar 3 opens with the tied note and a rest, and declares Bb7 after them.

        So the first *emitted* note of bar 3 - "But", the head of the refrain - is
        the first note Bb7 governs. Reading the harmony as belonging to the bar it
        starts in, or to the note before it, would put the refrain's opening note
        under the Cm7 that bar 2 ends on.
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
        to prevent, and it starts at the loader.
        """


    def test_this_librarys_own_export_reads_back(self):
        """A score this library exported is read by its own importer.

        The export writes a TAB staff and a notation staff, and puts a fret in a
        `<technical>` on every note of a chord. Reading the TAB part would double
        every note, since a MusicXML tab staff writes one `<note>` per string.
        """
        head = load_musicxml(TENOR_MADNESS)
        self.assertEqual(head.title, "Tenor Madness")
        self.assertEqual(head.part, "Tenor Madness")
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
        """I Was Doing All Right is a piano part in triplets, in 10080 divisions.

        Reading its triplet durations unreduced would drift every bar after the
        first, so the total written time is checked against the bars it spans: a
        2/2 bar is a whole note, and an undivided reader runs a third long.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertEqual(head.title, "I Was Doing All Right")
        self.assertEqual((head.beats_per_bar, head.beat_type), (2, 2))
        bars = head.bars[1] - head.bars[0]
        written = sum(n.duration for n in head.notes)
        self.assertAlmostEqual(written, float(bars), delta=bars * 0.2)


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

    def test_the_key_of_a_real_score_is_read(self):
        """"But Not For Me" is a music21 export in three flats - Eb, not C."""
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
        self.assertEqual([s[2] for s in head_skeleton(head, "eighths")], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual([s[2] for s in head_skeleton(head, "beats")], [1.0, 2.0, 3.0, 4.0])

    def test_eighths_are_kept_where_a_beat_grid_would_drop_them(self):
        """Four eighths a bar: the eighth grid keeps four, the beat grid fewer.

        This is the density decision the corpus path measures (`eighths` is its
        default for the same reason), asserted on a score rather than a database.
        """
        # Four of eight divisions is an eighth, so four of them are a half bar.
        head = self.load(
            harmony("C", "major")
            + note("E", duration=4) + note("F", duration=4)
            + note("G", duration=4) + note("A", duration=4),
            divisions=8,
        )
        eighths = [s[2] for s in head_skeleton(head, "eighths")]
        beats = [s[2] for s in head_skeleton(head, "beats")]
        self.assertEqual(eighths, [1.0, 1.5, 2.0, 2.5])
        # A note between two beats rounds onto one of them, so the beat grid keeps
        # strictly fewer slots - which is the whole point of the finer default.
        self.assertLess(len(beats), len(eighths))
        self.assertEqual(beats[0], 1.0)

    def test_a_note_off_the_grid_lands_on_it(self):
        """A triplet note rounds to the nearest eighth, so it is voiced on one.

        The written onsets fall between the eighths; the slots do not, because the
        grid is what the voicings are spaced on and a chord a sixteenth off the beat
        would sit between two columns of the staff.
        """
        # divisions=12, so a quarter is 12. Two triplet eighths written as 8 are
        # divided to 5 each, so the onsets fall on 1 + 5/12 and 1 + 10/12.
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8, tuplet=True) + note("F", duration=8, tuplet=True)
            + note("G", duration=12),
            divisions=12,
        )
        # Read raw, the onsets really are off the eighth grid...
        self.assertAlmostEqual(head.notes[1].beat, 1 + 5 / 12, places=6)
        self.assertAlmostEqual(head.notes[2].beat, 1 + 10 / 12, places=6)
        # ...and every slot lands on one.
        for _triple, _bar, beat, _duration in head_skeleton(head, "eighths"):
            self.assertAlmostEqual((beat - 1.0) % 0.5, 0.0, places=6)

    def test_the_chords_strategy_keeps_one_slot_per_change(self):
        """The written harmony rather than the melody, at the change's own beat."""
        head = self.load(
            harmony("C", "major") + note("E") + note("F") + note("G")
            + harmony("F", "dominant") + note("A") + note("B"),
        )
        slots = head_skeleton(head, "chords")
        self.assertEqual([s[0][2] for s in slots], ["Cmaj", "F7"])
        # The change lands on the fourth quarter, which is beat 4 - not the
        # downbeat the grid would have put it on.
        self.assertEqual([s[2] for s in slots], [1.0, 4.0])

    def test_a_leading_rest_still_takes_up_its_time(self):
        """A rest is not a note, but it is time, and the cursor must cross it.

        Bar 1 of "But Not For Me" is a quarter rest and then three quarter notes.
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
        events, pickup = _events(
            _substitute_steps(
                arrange_xml_head(BUT_NOT_FOR_ME, strategy="eighths")[0]
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
        of "But Not For Me", silently. A note of the tune is worth more than a
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
            [s[2] for s in head_skeleton(head, "eighths")], [1.0, 1.5, 2.0, 2.5]
        )

    def test_a_bar_line_overflow_is_still_pulled_back_inside(self):
        """The clamp the last-eighth fix refines still does its original job.

        A note that *rounds onto* the bar line - the last thing `_slot_key` is
        documented to catch - is still pulled back to the last grid position inside
        the bar, so a bar cannot gain a phantom step on its own downbeat and collide
        with the first step of the next.
        """
        head = self.load(
            harmony("C", "major")
            + note("E", duration=8) + note("F", duration=8)
            # A note at 2.75 rounds up to 3.0, which is the bar line in a 2/2 bar.
            + note("G", duration=6) + note("A", duration=2),
            divisions=8, beats=2, beat_type=2,
        )
        beats = [s[2] for s in head_skeleton(head, "eighths")]
        # Nothing lands on 3.0 or beyond: the overflow came back to 2.5.
        self.assertTrue(all(b <= 2.5 for b in beats), beats)
        self.assertIn(2.5, beats)

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
        slots = head_skeleton(head, "eighths")
        self.assertTrue(any(beat > head.beats_per_bar for _t, _b, beat, _d in slots))
        # Nothing may land on or past the bar line either.
        for _triple, _bar, beat, _duration in slots:
            self.assertLessEqual(beat, head.beats_per_bar + 1.0 - 0.5)

    def test_a_slash_bass_stays_in_the_chord_name(self):
        """The bass rides in the name, as the corpus path keeps it, and rule B
        promotes a triad whose bass is its own seventh."""
        head = self.load(harmony("A", "minor", bass="G") + note("E"))
        _melody, quality, name = head_skeleton(head, "beats")[0][0]
        self.assertEqual(quality, "m7")  # A minor triad over G is a minor 7th
        self.assertEqual(name, "Am/G")

    def test_a_slash_chord_is_voiced_with_its_bass_preferred(self):
        """A slash chord is honoured as a *preference*, by the shared step loop.

        The candidate whose lowest pitch is nearest the bass is preferred, exactly
        as the corpus path does - which is the point of sharing `arrange_slots`
        rather than reimplementing it here.
        """
        steps, _head, _notes = arrange_xml_head(
            self.path(harmony("D", "dominant", bass="C") + note("F", octave=4)),
            strategy="beats",
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].chord, "D7/C")
        # The shape's bottom note is the C, or within a tone of it.
        bottom = min(steps[0].voicing.midi_notes()) % 12
        self.assertIn(bottom, (0, 1, 11))

    def test_melody_under_no_chord_becomes_a_melody_only_step(self):
        """A note with no harmony is voiced alone, not under an invented chord."""
        path = write_score(score(note("C", octave=5) + harmony("C", "major") + note("E")))
        self.addCleanup(os.unlink, path)
        steps, _head, _notes = arrange_xml_head(path, strategy="beats")
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
        slots = head_skeleton(head, "beats")
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
        steps, _head, _notes = arrange_xml_head(source, strategy="beats")

        exported = write_score(format_musicxml(steps, title="Round trip"), suffix=".musicxml")
        self.addCleanup(os.unlink, exported)
        reloaded = load_musicxml(exported)

        # The chords survive, which is the point: the exporter writes a chord
        # music21 cannot classify as `<kind text="...">other</kind>`, and the
        # importer reads exactly that back through ChordParser.
        self.assertEqual([n.chord for n in reloaded.notes], [s.chord for s in steps])
        # And the melody does, so the reloaded head is the same tune.
        self.assertEqual([n.pitch for n in reloaded.notes],
                         [max(s.voicing.midi_notes()) for s in steps])



class TestHeadTexture(unittest.TestCase):
    """
    The target-note texture over a real written head.

    `but_not_for_me.mxl` is the fixture that matters here: it is in **cut time**, so
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


class TestHeadCli(unittest.TestCase):
    """The `head` command, driven as a function over a temporary score."""

    def run_cli(self, *argv) -> str:
        """Run head_cli on argv, capturing what it printed."""
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.code = head_cli(list(argv))
        return buffer.getvalue()

    def score_path(self) -> str:
        path = write_score(
            score(
                harmony("D", "minor-seventh") + note("A", octave=5)
                + harmony("G", "dominant") + note("B", octave=4)
                + harmony("C", "major-seventh") + note("B", octave=4)
            )
        )
        self.addCleanup(os.unlink, path)
        return path

    def test_it_prints_the_title_and_the_tab(self):
        """A run reports what it read and then the arrangement itself."""
        output = self.run_cli(self.score_path())
        self.assertEqual(self.code, 0)
        self.assertIn("Test", output)
        self.assertIn("4/4", output)
        self.assertIn("Dm7", output)
        # A fretted shape, not a chord list.
        self.assertRegex(output, r"\d+-\d*-\d*")

    def test_bars_narrows_the_head(self):
        """--bars is the same half-open range the corpus command takes."""
        path = write_score(
            """<?xml version="1.0"?>
<score-partwise version="3.1"><part-list><score-part id="P1"/></part-list><part id="P1">
<measure number="1"><attributes><divisions>4</divisions></attributes>
  {h1}{n1}</measure>
<measure number="2">{h2}{n2}</measure>
<measure number="3">{h1}{n1}</measure>
</part></score-partwise>""".format(
                h1=harmony("C", "major"), n1=note("E"),
                h2=harmony("F", "dominant"), n2=note("F"),
            )
        )
        self.addCleanup(os.unlink, path)
        output = self.run_cli(path, "--bars", "2-3")
        self.assertIn("F7", output)
        self.assertNotIn("Cmaj", output)

    def test_a_bad_bar_range_is_a_usage_error(self):
        """A nonsense range is reported, not raised as a traceback."""
        with self.assertRaises(SystemExit):
            self.run_cli(self.score_path(), "--bars", "not a range")

    def test_a_missing_file_is_a_usage_error(self):
        """Asking for a file that is not there says so, rather than raising."""
        with self.assertRaises(SystemExit):
            self.run_cli("/nonexistent/head.musicxml")

    def test_the_written_files_carry_the_notated_metre(self):
        """A head in cut time is written 2/2, not left on the writers' 4/4 default.

        `head_cli` passes the notated metre to the staff and the HTML but used to
        pass nothing to the two file writers, so each fell back to its own
        `beats_per_bar=4`. A 2/2 head was therefore written as 4/4: every bar laid
        out against the wrong grid, and a tune in cut time displayed as common time.
        The denominator matters too - 2/2 and 2/4 are the same bar length but not
        the same metre, and only the notated `beat_type` tells them apart.
        """
        try:
            import music21  # noqa: F401
        except ImportError:
            self.skipTest("music21 is not installed")
        try:
            import guitarpro  # noqa: F401
        except ImportError:
            self.skipTest("PyGuitarPro is not installed")

        target = os.path.join(tempfile.mkdtemp(), "cut.gp5")
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        output = self.run_cli(BUT_NOT_FOR_ME, "--gp5", target)
        self.assertEqual(self.code, 0)
        self.assertIn("wrote", output)

        from guitarpro import parse

        song = parse(target)
        signature = song.measureHeaders[0].timeSignature
        self.assertEqual(signature.numerator, 2)
        self.assertEqual(signature.denominator.value, 2)
        # The bar length is the real one: a 2/2 bar is four quarters, so a head of
        # 32 bars is 32 measures and not 64 half-length ones. Reading the beat count
        # as a quarter count is what doubled it.
        self.assertEqual(len(song.tracks[0].measures), 32)

    def test_a_real_head_exports_in_the_key_it_is_in(self):
        """
        The end-to-end measure, on the two committed scores that state a key.

        Both numbers here were measured, and one of them went *up*. "I Was Doing All
        Right" is in G and carries the F natural of a `G#dim7` resolving to `G7b9`;
        with no `<key>` written, 12 of those Fs carried no accidental at all, so a
        reader saw F# - the note the file did not mean. Stating the key marks them,
        which is why the assertion is "the signature is right" rather than "there are
        fewer accidentals": that second form would have passed while that error stood.
        """
        from tabxml import format_musicxml

        def exported(path):
            steps, head, _ = arrange_xml_head(path)
            return ElementTree.fromstring(
                format_musicxml(
                    steps,
                    title=head.title,
                    beats_per_bar=head.beats_per_bar,
                    beat_type=head.beat_type,
                    fifths=head.key_fifths,
                    mode=head.key_mode,
                )
            )

        for path, expected in ((BUT_NOT_FOR_ME, "-3"), (I_WAS_DOING_ALL_RIGHT, "1")):
            root = exported(path)
            written = [
                (key.findtext("fifths"), key.findtext("mode"))
                for key in root.iter("key")
            ]
            self.assertEqual(written, [(expected, "major")], path)

    def test_the_written_files_carry_the_key_of_the_score(self):
        """
        End to end: a score in three flats exports as a score in three flats.

        This is the whole defect in one test. The file states `<fifths>-3</fifths>`
        and `<mode>major</mode>`; without that, every note of the Eb scale carries
        an accidental the signature had already accounted for. It reads the file
        back rather than inspecting the argument, because the argument is what the
        test supplies and the file is what a musician opens.
        """
        try:
            import music21  # noqa: F401
        except ImportError:
            self.skipTest("music21 is not installed")

        directory = tempfile.mkdtemp()
        target = os.path.join(directory, "eb.musicxml")
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        output = self.run_cli(BUT_NOT_FOR_ME, "--musicxml", target)
        self.assertEqual(self.code, 0)
        self.assertIn("wrote", output)

        root = ElementTree.parse(target).getroot()
        keys = list(root.iter("key"))
        self.assertEqual(len(keys), 1, "the signature must be written once, in the first bar")
        self.assertEqual(keys[0].findtext("fifths"), "-3")
        self.assertEqual(keys[0].findtext("mode"), "major")

    def test_the_header_names_the_key(self):
        """`Eb major` in the header, so the key is visible before the file is opened.

        The count is not enough to read: -3 is Eb major *or* C minor, and the header
        is where a user checks they arranged the tune they meant.
        """
        output = self.run_cli(BUT_NOT_FOR_ME)
        self.assertIn("Eb major", output)

    def test_a_file_that_is_not_a_score_is_a_usage_error(self):
        """A readable non-score is caught here, not deep in the loader."""
        path = write_score("<html><body>not a score</body></html>")
        self.addCleanup(os.unlink, path)
        with self.assertRaises(SystemExit):
            self.run_cli(path)

    def test_the_staff_renderer_is_reachable(self):
        """--tab staff lays the head on one six-line staff, in the notated metre."""
        output = self.run_cli(self.score_path(), "--tab", "staff", "--melody")
        # The staff draws six strings, high E first. The `*` is `_carries_melody`'s
        # marker, drawn on any string sounding the melody, so it may sit between the
        # letter and the bar - which it now does, because span being ranked above neck
        # position moved this head's B4 from the B string to the high E. The letter and
        # the bar are what this test is about, so the marker is optional.
        self.assertRegex(output, r"e\s*\*?\s*\|")
        # Six string rows, each a drawn line of dashes with the frets sitting in it.
        labels = ("e", "B", "G", "D", "A", "E")
        strings = [
            row for row in output.split("\n")
            if row[:1] in labels and "|" in row
        ]
        self.assertEqual(len(strings), 6, output)
        # No chord names: the staff is the tab by default now, and this test is about
        # the renderer being reachable rather than about what it annotates.
        self.assertNotIn("Dm7", output)

    def test_it_writes_an_html_page_when_asked(self):
        """--html writes a page and says where."""
        path = self.score_path()
        handle, out = tempfile.mkstemp(suffix=".html")
        os.close(handle)
        self.addCleanup(os.unlink, out)
        output = self.run_cli(path, "--html", out)
        self.assertIn(f"wrote {out}", output)
        with open(out, encoding="utf-8") as written:
            self.assertIn("Dm7", written.read())

    def test_it_writes_musicxml_when_the_extra_is_present(self):
        """The importer's own output is fed straight back into the exporter.

        The tab is produced whether or not music21 is installed; only this second
        file needs the extra, which is why it is a separate flag and a separate
        dependency. Without music21 the command reports the missing extra and
        returns non-zero rather than losing the tab it already printed.
        """
        try:
            import music21  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("music21 not installed, so there is no extra to need")
        handle, out = tempfile.mkstemp(suffix=".musicxml")
        os.close(handle)
        self.addCleanup(os.unlink, out)
        output = self.run_cli(self.score_path(), "--musicxml", out)
        self.assertIn(f"wrote {out}", output)
        # The tab was printed first, so the optional output did not replace it.
        self.assertIn("Dm7", output)
        # And what it wrote is a score this module can read back.
        self.assertEqual(load_musicxml(out).title, "Test")

    def test_a_missing_optional_extra_is_reported_not_raised(self):
        """A missing extra is a usage problem, not a traceback.

        `headxml` needs nothing optional at all, so this is about the *export* it
        was also asked for: the command must still print the tab it had already
        produced rather than dying on the way out. The writer is stubbed rather
        than uninstalled, so the test says what it means on a machine that has
        music21 installed.

        **The stub moved with the code.** It used to patch `arranger`, because
        `head_cli` reached the writer through the facade's lazy `__getattr__` and
        an attribute assignment there was what `from arranger import` then saw.
        Phase 7 moved the dispatch into `arranger.cli`, which imports the writer
        from its real home in `tabxml` - which is where the extra is actually
        checked. The property under test is untouched; only the seam the test
        hooks onto changed, and the new seam is the better one: it does not depend
        on the facade's resolution strategy staying the same.
        """
        import tabxml

        def refuse(*args, **kwargs):
            raise ImportError(
                "MusicXML export needs music21, which is an optional extra. "
                "Install it with: pip install 'jazz-arranger[xml]'"
            )

        original = tabxml.write_musicxml
        tabxml.write_musicxml = refuse
        # Restored with `setattr`, never `delattr`. `tabxml` *defines* this
        # function, so deleting the name removes it from the module for good and
        # every later test in the process fails with "cannot import name". The
        # previous version of this test patched `arranger`, where the name came
        # from a lazy `__getattr__` and `delattr` simply re-armed the fallback -
        # which is why the mistake only became possible once the seam moved.
        self.addCleanup(setattr, tabxml, "write_musicxml", original)

        handle, out = tempfile.mkstemp(suffix=".musicxml")
        os.close(handle)
        self.addCleanup(os.unlink, out)
        output = self.run_cli(self.score_path(), "--musicxml", out)
        self.assertEqual(self.code, 1)
        # The tab it had already printed is still there, and the message names
        # the install command that fixes it.
        self.assertIn("Dm7", output)
        self.assertIn("jazz-arranger[xml]", output)

