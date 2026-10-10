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
from arranger import NO_CHORD, ChordParser, Diagnostics, format_progression
from arranger.slots import arrange_slots
from headxml import (
    Head,
    HeadChange,
    _key_label,
    _part_is_tab,
    arrange_xml_head,
    chord_at,
    chord_slots,
    head_cli,
    head_skeleton,
    load_musicxml,
    melody_at,
    melody_state,
    parse_musicxml_chord,
)
from tabstaff import format_tab_staff, write_tab_html
from tabxml import _events, _substitute_steps

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
#   Trouble_in_Mind_Blues.musicxml  a 4/4 blues with ties written across barlines, which
#                                 is the case `TestAHeldNoteIsOneNoteAcrossABarline` pins
#   lead_sheet_chords_only.musicxml  written by hand: four bars, six <harmony> symbols and
#                                 **no pitched notes** - the chords-only case (step A')
#   The_Jitterbug_Waltz.musicxml  MuseScore 3, the **only** head in the repository whose
#                                 numerator and denominator differ (3/4), and so the only one
#                                 that can see a conversion written as `beats_per_bar / 4`
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAINY_DAY = os.path.join(DATA, "heres_that_rainy_day.musicxml")
TROUBLE_IN_MIND = os.path.join(DATA, "Trouble_in_Mind_Blues.musicxml")
WALTZ = os.path.join(DATA, "The_Jitterbug_Waltz.musicxml")


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
BUT_NOT_FOR_ME = os.path.join(DATA, "but_not_for_me.mxl")
TENOR_MADNESS = os.path.join(DATA, "tenor_madness.musicxml")
I_WAS_DOING_ALL_RIGHT = os.path.join(DATA, "i_was_doing_all_right.mxl")
# A lead sheet with **no melody at all**: four bars, six `<harmony>` symbols and not
# one pitched note (§9.3 step A'). It is the fixture the loader used to refuse.
CHORDS_ONLY = os.path.join(DATA, "lead_sheet_chords_only.musicxml")


def score(
    measures: str,
    divisions: int = 4,
    beats: int = 4,
    beat_type: int = 4,
    part_id: str = "P1",
    fifths: Optional[int] = None,
    mode: str = "",
    transpose: str = "",
) -> str:
    """A minimal score-partwise document around the measures given.

    `fifths` states a `<key>` when given, and omitting it writes no `<key>` at all -
    which is a real case rather than a gap in the fixture, because a score with no
    signature states C major.

    `transpose` is raw `<transpose>` XML placed in the part's `<attributes>`, so a
    test can state a transposing instrument: a guitar notated an octave above its
    sound, or a Bb horn a tone above it.
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
        {transpose}
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
        same trap `arranger.slots._slash_bass` documents for a slash chord.
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


class TestAHeldNoteIsOneNoteAcrossABarline(unittest.TestCase):
    """`Trouble in Mind`: ties written across barlines, on a real 4/4 blues.

    **This fixture is here because of a misdiagnosis, and the reason is the point.**
    A guard was once added to `headxml._flush_group` - `and notes[-1].bar == bar` -
    on the belief that merging a tie-stop into the previous note "ate the new bar's
    downbeat" on this head. It does the opposite. A `tie type="stop"` in a new bar
    *is* the continuation the merge exists to absorb, so the guard turned every
    cross-barline tie into a second note at the same pitch: **53 notes became 63
    here**, and `but_not_for_me` went 80 to 84. Ten tests failed against it.

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
        """`Head.bars` is now a fact about the *file*, so it does not stop at the note.

        **Inverted rather than deleted** (§9.3 step A', and AGENTS.md trap 5). The old
        assertion was `(1, 16)` and its premise was *"`Head.bars` stops at the last
        note"*. Step A' made `bars` the file's measure extent, because a chords-only
        head has no notes to measure and still knows how long it is - so the premise
        is gone and the assertion would be wrong to keep. The file runs to measure 17,
        so the range is `(1, 18)`: the last note begins in bar 15 and is held to bar 17
        beat 2.0, and the range now reaches that bar rather than stopping short of it.

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
    on all 271 notes** — so a change that disagrees with the notes is a change that is
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
        """The defect itself, on a committed score: bar 2 of `i_was_doing_all_right`.

        Written as `HARMONY(m7), NOTE(D5), HARMONY(7), rest` — an `Am7` under the D5 and
        a `D7` that governs the rest of the bar. Only the first has a note.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        self.assertEqual(self._notes_in_bar(head, 2), [(1.0, "Am7")])
        self.assertEqual(self._chords_in_bar(head, 2), [(1.0, "Am7"), (2.5, "D7")])

    def test_a_bar_of_nothing_but_rests_still_has_its_chords(self):
        """Bar 32 of `heres_that_rainy_day` has **no notes at all** and two changes.

        This is the case that cannot even be asked of the note path — there is no note to
        ask with — so it is the strongest of the three.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(self._notes_in_bar(head, 32), [])
        self.assertEqual(self._chords_in_bar(head, 32), [(1.0, "Am7"), (2.0, "D9")])

    def test_the_timeline_reproduces_every_notes_own_chord(self):
        """The cross-check: 458 of 458, on all three fixtures.

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
            for note in head.notes:
                if note.quality is None:
                    continue
                checked += 1
                in_force = chord_or_fail(head.chords, note.bar, note.beat).chord
                self.assertEqual(
                    in_force, note.chord,
                    f"{path}: bar {note.bar} beat {note.beat} - the timeline says "
                    f"{in_force!r} and the note says {note.chord!r}",
                )
        # A count as well as an agreement, so an empty fixture cannot make this vacuous.
        #
        # **458, not 271, because three of these scores carry a repeat.** `heres_that_
        # rainy_day` (bars 1-30, then 31-32 and 33-36) and `i_was_doing_all_right` (bars
        # 1-34, then 35) now expand to the bars a player actually plays, so their repeated
        # sections - and the notes and `<harmony>` in them - are stated on every pass. The
        # cross-check is over the expanded head, and the count is the expanded note count.
        self.assertEqual(checked, 458)

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
    - where a bar declares two chords on the same beat, **the last one wins** — bars 33
      and 35 of `i_was_doing_all_right` are written `Gmaj` then `Eb7`, and the note in
      each bar carries `Eb7`, so first-wins would disagree with the shipped output;
    - a position before the first change has **no** chord, and says so rather than
      guessing.
    """

    def test_a_chord_holds_until_the_next_one_replaces_it(self):
        """Bar 2 of `i_was_doing_all_right`: `Am7` at beat 1, `D7` at beat 2.5.

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
        """Bar 32 of `heres_that_rainy_day` has no notes and two changes.

        This is the query's reason to exist, and it is the position the note path cannot
        be asked about at all.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(chord_or_fail(head.chords, 32, 1.0).chord, "Am7")
        self.assertEqual(chord_or_fail(head.chords, 32, 1.5).chord, "Am7")
        self.assertEqual(chord_or_fail(head.chords, 32, 2.0).chord, "D9")
        # Past the end of the bar it still carries the last thing declared, which is
        # what "holds until the next one replaces it" means across a barline.
        self.assertEqual(chord_or_fail(head.chords, 32, 9.0).chord, "D9")

    def test_the_last_change_at_a_position_wins(self):
        """Bars 33 and 35 declare two chords on beat 1.0, and the note carries the second.

        Not a synthetic tie: measured on the committed score. First-wins would put
        `Gmaj` and `G6` under notes that ship with `Eb7`, so this is the rule that keeps
        the query from disagreeing with the output it will one day feed.

        **Identified by `written_bar`, queried by `bar`.** `i_was_doing_all_right` carries
        a repeat, so the loader renumbers written bar 33 (the 1st ending's bar) to the
        absolute 33 and written bar 35 (the 2nd ending's bar) to the absolute 68; the
        rule under test is about the score's own numbering, so the bar is found by
        `written_bar` and the query is made at the absolute position it landed on.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        for written, first in ((33, "Gmaj"), (35, "G6")):
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
                [n.chord for n in head.notes if n.bar == bar], ["Eb7"], f"bar {bar}"
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
        """The cross-check, now over the shipped function: 458 of 458.

        `TestChordTimeline` proved the *data* reproduces the notes; this proves the
        *query* over that data does, which is a different thing and could have been wrong
        at the boundary the duplicate-position rule covers. The count is 458 rather than
        271 because the repeat-bearing fixtures (`heres_that_rainy_day`,
        `i_was_doing_all_right`) now expand to the bars a player actually plays - see
        `test_the_timeline_reproduces_every_notes_own_chord`.
        """
        checked = 0
        for path in (BUT_NOT_FOR_ME, RAINY_DAY, I_WAS_DOING_ALL_RIGHT):
            head = load_musicxml(path)
            for note in head.notes:
                if note.quality is None:
                    continue
                checked += 1
                change = chord_at(head.chords, note.bar, note.beat)
                assert change is not None, (
                    f"{path}: bar {note.bar} beat {note.beat} has no chord in force"
                )
                self.assertEqual(
                    change.chord, note.chord,
                    f"{path}: bar {note.bar} beat {note.beat} - {change.chord!r} vs "
                    f"{note.chord!r}",
                )
        self.assertEqual(checked, 458)

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

    **Step A' of §9 moved these numbers, for the same three fixtures.** `Head.bars` is
    now the file's measure extent, so a fixture whose changes outlast its last note
    comps to the end of the file rather than stopping at the end of the tune. Current
    counts (`--voices alto,tenor`):

        comps+freddie   80 -> 102,  81 -> 109,  110 -> 126 steps
        comps+joe_pass  80 -> 105,  81 -> 120,  110 -> 161 steps

    Still only the comping route with a named grid, and still only the fixtures whose
    chord timeline runs past their last note (`Trouble_in_Mind_Blues`,
    `heres_that_rainy_day`, `i_was_doing_all_right`) — the other three, and every
    default arrangement, are unchanged. §8's acceptance criterion holds: an arrangement
    with no flags passed is byte-identical, `grid=` on the singing route included.
    """

    def setUp(self):
        self.rainy = load_musicxml(RAINY_DAY)
        self.iwas = load_musicxml(I_WAS_DOING_ALL_RIGHT)

    def _melody_positions(self, head):
        return {(s[1], round(s[2], 6)) for s in head_skeleton(head)}

    def _chord_positions(self, head, grid):
        return {(s[3], round(s[4], 6)) for s in chord_slots(head, grid=grid)}

    def test_a_bar_with_no_notes_now_gets_its_chords(self):
        """Bar 32 of `heres_that_rainy_day`: the defect, and the reason for the phase.

        No notes at all, two changes (`Am7` then `D9`), and before this the bar produced
        nothing whatever — it was not quiet, it was absent.
        """
        self.assertEqual([n.bar for n in self.rainy.notes if n.bar == 32], [])
        positions = sorted(
            (beat, chord) for _m, _q, chord, bar, beat, _d in
            chord_slots(self.rainy, grid="freddie") if bar == 32
        )
        self.assertEqual(positions, [(1.0, "Am7"), (2.0, "D9")])

    def test_the_default_grid_adds_a_bar_the_melody_never_enters(self):
        """**The bar-level rule, and the fix for open-issues item 1's remaining defect.**

        `every_note` is melody-anchored, so merging *every* position it names would thin a
        part whose melody runs at sixteenths against a grid at beats - the reason the
        union excluded it outright. The unit of exception is therefore the **bar**: a bar
        the melody never enters is added beat for beat, and a bar it does enter is left to
        the melody exactly as before.

        Bar 32 is the case the old behaviour got wrong: no notes at all, two changes, and
        **no part produced** - not quiet, absent - on every export path. Under the default
        grid it now sounds both chords. Measured on a 2/2 head, so the assertion is two
        steps and not four, which is also the count-with-a-denominator rule of AGENTS.md
        trap 9.
        """
        steps, _head, _notes = arrange_xml_head(RAINY_DAY)
        silent = [s for s in steps if s.bar == 32]
        silent.sort(key=lambda step: (step.bar or 0, step.beat or 0.0))
        self.assertEqual([(s.beat, s.chord) for s in silent], [(1.0, "Am7"), (2.0, "D9")])
        for step in silent:
            self.assertIsNone(step.melody, step.tab_line())
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_a_bar_the_melody_does_enter_is_untouched_by_the_default_grid(self):
        """The deference survives where it was load-bearing: inside a bar the tune has.

        This is the other half of the bar-level rule and the reason it is a bar-level rule
        rather than a merge. A note-bearing bar keeps exactly the slots `head_skeleton`
        produced - so `docs/comping-styles.md` §8's acceptance criterion (an arrangement
        with no flags passed is byte-identical) holds over every note-bearing bar of every
        fixture, which a beat-level merge could not do.

        Stated as an arithmetic claim over the whole head: the union adds only positions
        in bars `head_skeleton` never touched.
        """
        skeleton = head_skeleton(self.rainy, None)
        melody_bars = {bar for _triple, bar, _beat, _duration in skeleton}
        steps, _head, _notes = arrange_xml_head(RAINY_DAY)
        added = {(s.bar, s.beat) for s in steps} - {
            (bar, round(beat, 6)) for _t, bar, beat, _d in skeleton
        }
        self.assertTrue(added, "the fixture must have a bar the melody never enters")
        for bar, _beat in added:
            self.assertNotIn(bar, melody_bars, f"bar {bar} has notes and was added to")

    def test_a_melody_less_bar_with_no_harmony_behind_it_adds_nothing(self):
        """The bar-level rule never guesses a chord, which is the invariant that matters most.

        `chord_at` forward-fills, so a bar the melody never enters inherits the last change
        before it - bar 2 of `heres_that_rainy_day` states the chord that was already in
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

    def test_the_default_grid_moves_no_count_on_a_head_with_no_gap_bar(self):
        """`but_not_for_me` and `tenor_madness` have no melody-less bar, so nothing moves.

        The byte-identical claim, measured rather than asserted by inspection: these two
        fixtures' default arrangements are the same length as their skeletons, because
        there is no bar to add. That is what makes the change a fix rather than a
        behaviour change on the whole corpus - 57 added steps across five heads, zero on
        the other two.
        """
        for path in (BUT_NOT_FOR_ME, TENOR_MADNESS):
            with self.subTest(head=os.path.basename(path)):
                head = load_musicxml(path)
                steps, _head, _notes = arrange_xml_head(path)
                self.assertEqual(len(steps), len(head_skeleton(head, None)))

    def test_the_walking_bass_inherits_the_added_bar(self):
        """The default grid now walks the bars the melody never entered.

        `_walking_slots` walks the bars the *timings* touch, and the union writes its
        added slots into those timings - so the bass half of item 1 was already correct
        wherever a named grid ran. The default grid's silence was the only thing
        withholding the bar from it, and `freddie` is the pre-existing witness: under the
        default the walk now reaches **exactly** the bars `freddie` reaches, no more and no
        fewer.

        **Bars 32 and 35 still get no thumb note, and that is a different issue.**
        `_place_bass` refuses them for the reason `docs/open-issues.md` **item 2** measures
        as dominant - no octave of the walk's pitch below the shape - and it refuses them
        identically under `freddie`, before and after this change. Asserting a thumb note
        in bar 32 would be asserting item 2's fix, which is deliberately not built. So the
        claim is about which bars the walk *visits*, not which it can place a note in.
        """
        def walked(grid):
            steps, _head, _notes = arrange_xml_head(
                RAINY_DAY, bass="walk", texture="walking_bass", grid=grid
            )
            return {s.bar for s in steps}

        head = load_musicxml(RAINY_DAY)
        melody_bars = {n.bar for n in head.notes}
        every = walked("every_note")
        named = walked("freddie")
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
        melody = self._melody_positions(self.iwas)
        chords = self._chord_positions(self.iwas, "freddie")
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
        """`joe_pass` and `charleston` were silent on all three fixtures before this.

        Stage D of `docs/comping-styles.md` records `charleston` coming out silent on a
        2/2 head and attributes it to the figure being 4/4. That was a misdiagnosis: the
        grid could only filter melody slots, so a position with no note was unreachable
        whatever the pattern said. Measured now, on a 2/2 head:

            every_note  63   charleston  63   joe_pass  64   final_and  32
        """
        for grid in ("every_note", "freddie", "charleston", "joe_pass", "final_and"):
            with self.subTest(grid=grid):
                self.assertTrue(
                    self._chord_positions(self.rainy, grid),
                    f"grid={grid} places nothing at all",
                )

    def test_a_stab_is_never_a_whole_note(self):
        """The duration is the grid's, not the melody note's — which is the point.

        Under `every_note` and `freddie` every duration on a 2/2 fixture is 0.5 — one
        notated beat. A stab that inherited the melody's length would be a whole note on a
        bar the melody holds, which is the confusion item 1 records.

        `joe_pass` is 0.25 or 0.5 because it names the *ands*, so the distance to the next
        position is half a beat — asserted here because it is the same rule producing a
        different number, which is what makes "the grid decides" a claim rather than a
        coincidence.
        """
        for grid, expected in (("every_note", {0.5}), ("freddie", {0.5}),
                               ("joe_pass", {0.25, 0.5})):
            with self.subTest(grid=grid):
                durations = {round(s[5], 6) for s in chord_slots(self.rainy, grid=grid)}
                self.assertEqual(durations, expected, f"grid={grid}")
                # And never a whole note, whichever grid asked.
                self.assertNotIn(1.0, durations, f"grid={grid} produced a whole note")

    def test_a_position_with_no_chord_in_force_is_skipped(self):
        """Never guessed: bar 1 beat 1 of `but_not_for_me` is a rest under no harmony.

        The file writes a quarter rest, and the first `<harmony>` arrives on beat 1.5, so
        beat 1.0 has neither a note nor a chord. `chord_at` returns `None` and the position
        is dropped rather than filled with the chord arriving half a beat later.
        """
        head = load_musicxml(BUT_NOT_FOR_ME)
        self.assertIsNone(chord_at(head.chords, 1, 1.0))
        first = min(beat for bar, beat in self._chord_positions(head, "freddie")
                    if bar == 1)
        self.assertGreater(first, 1.0, "a position with no harmony was filled in")

    def test_the_singing_route_is_not_touched(self):
        """`melody=auto` unions nothing, and no invented note reaches a singing part.

        The regression that makes this necessary, and it was measured rather than
        predicted: `parse_voices("auto")` returns the **sentinel** `("auto",)`, which has
        no soprano, so testing the route on the parsed value alone classified the *default*
        arrangement as the comping route. Fourteen steps of a singing `grid=freddie`
        arrangement carried the placeholder melody before `resolve_voices` was added.
        """
        body = harmony("C", "major") + note("C", 5)
        path = write_score(score(body, divisions=4, beats=4))
        self.addCleanup(os.unlink, path)
        singing, _head, _notes = arrange_xml_head(path)
        self.assertEqual([s.melody for s in singing], ["C5"])
        self.assertNotIn(None, [s.melody for s in singing])

    def test_a_slot_whose_melody_has_stopped_carries_no_melody(self):
        """Where no note is sounding, the slot carries `None` rather than an invention.

        Bar 32 of `heres_that_rainy_day` follows the last melody note, so there is no tune
        under the chord. The deleted `_PLACEHOLDER_MELODY` stood in with a pitch that
        parsed but was not playing; `None` is the honest value, and the assertion is
        `assertIsNone` rather than an equality a placeholder could have satisfied — all
        30 real `C4` slots across the fixtures sat on genuinely written C4s, which is why
        equality against a sentinel could pass for the wrong reason (§9.3 step B).
        """
        slots = [s for s in chord_slots(self.rainy, grid="freddie") if s[3] == 32]
        self.assertTrue(slots, "bar 32 must place its chords")
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
            (note.bar, round(note.beat + note.duration * 2.0, 6))
            for note in self.notes
            if note.duration > 0
        ]
        held = [
            (bar, beat) for bar, beat in probes
            if melody_state(self.notes, bar, beat) == "held"
        ]
        self.assertTrue(held, "no position inside a sounding note reports held")

    def test_a_bar_after_the_melody_ends_reports_silent(self):
        """Bar 32 of `heres_that_rainy_day` has chords and no tune over them."""
        for beat in (1.0, 1.5, 2.0):
            with self.subTest(beat=beat):
                self.assertEqual(melody_state(self.notes, 32, beat), "silent")

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
    partial)` was printed by the default line tab 14 times on `but_not_for_me` under
    `--voices alto,tenor --grid freddie`, reading as a claim that the guitar played C4.
    It did not. What is asserted here is the replacement: a slot the tune does not
    occupy carries `None` and prints blank, while a slot it does occupy is unchanged -
    held notes still carry the note in force (Option A), so this step moves nothing
    under a sounding melody.
    """

    def _arrange(self):
        """The comping union over `heres_that_rainy_day`, whose melody ends before bar 32."""
        return arrange_xml_head(RAINY_DAY, melody="alto,tenor", grid="freddie")

    def test_a_slot_where_the_melody_stopped_carries_none(self):
        """Bar 32 sits under a chord and over no note; the step says so plainly."""
        steps, _head, _notes = self._arrange()
        silent = [s for s in steps if s.bar == 32]
        self.assertTrue(silent, "bar 32 must place its chords")
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
        diagnostics = Diagnostics()
        steps, _rescued, _notes = arrange_slots(
            [(None, "m7", "Dm7"), ("C5", "maj7", "Cmaj7")],
            [(1, 1.0, 0.5), (1, 2.0, 0.5)],
            melody="auto",
            diagnostics=diagnostics,
        )
        self.assertEqual([s.chord for s in steps], ["Dm7", "Cmaj7"])
        self.assertIsNone(steps[0].melody)
        self.assertFalse(steps[0].melody_voiced, "the guitar does not sing a note it has not got")
        self.assertTrue(steps[1].melody_voiced)
        self.assertFalse(
            any("has no melody note" in w for w in diagnostics.warnings),
            diagnostics.warnings,
        )


class TestAnUnknownGridIsRefused(unittest.TestCase):
    """§9.3 step A: the library refuses an unknown grid instead of coercing it.

    `headxml._merge_chord_slots` used to coerce anything unrecognised to the
    melody-anchored grid, so `arrange_xml_head(..., grid="half-time")` silently
    returned `every_note`'s arrangement on the comping route - the exact guess
    `parse_grid` refuses. The coercion is gone: `auto` was the only thing that ever
    made it reachable, and once the sentinel was withdrawn the guess went with it.
    The CLI is unaffected (argparse rejects an unknown choice first), so this is
    observable only from library code - which is why it needs its own test rather
    than being left to the gate.
    """

    def test_an_unknown_grid_raises_on_the_comping_route(self):
        """The path that used to coerce now refuses, naming the real vocabulary."""
        with self.assertRaises(ValueError) as caught:
            arrange_xml_head(RAINY_DAY, melody="alto,tenor", grid="half-time")
        self.assertIn("joe_pass", str(caught.exception))

    def test_auto_is_no_longer_a_grid_a_library_caller_can_pass(self):
        """`auto` was withdrawn, so the library refuses it too - not just the CLI."""
        with self.assertRaises(ValueError):
            arrange_xml_head(RAINY_DAY, melody="alto,tenor", grid="auto")


class TestChordsOnlyHead(unittest.TestCase):
    """§9.3 step A': a chords-only lead sheet is a valid input.

    Four bars, six `<harmony>` elements, **zero pitched notes** — measured, the loader
    used to refuse it outright (`has no readable melody part`) because `_choose_part`
    selected on the note count alone. It now reads, reports its metre and bar count, and
    arranges **the whole head**.

    The default grid's silence here was `docs/open-issues.md` item 1's extreme case, and
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

        **This assertion is inverted, not deleted** (AGENTS.md trap 5). It used to assert
        `steps == []`, and the premise it rested on was step A' decision 2: "an empty
        arrangement is the default grid's own instruction rather than a hole to report."
        That premise is exactly what `docs/open-issues.md` item 1 measures as the defect —
        a chord in force that produces **no part at all**, not quiet, absent, on every
        export path. The rule now unions at the level of the **bar**, so a melody-less
        head is fully arranged and a note-bearing bar is untouched; `every_note`'s
        deference to the melody survives where it was load-bearing, which is inside a bar
        the tune already articulates.

        The soprano refusal below is the one case that did not move, and it is a different
        claim: a melody-only selection has nothing to *play* here, which is not the same
        as a grid having nowhere to *place* a chord.
        """
        steps, _head, _notes = arrange_xml_head(CHORDS_ONLY, melody="alto,tenor")
        self.assertEqual(len(steps), 16, "four bars, four beats each")
        self.assertEqual((steps[0].bar, steps[0].beat), (1, 1.0))
        self.assertTrue(
            all(step.melody is None for step in steps),
            "a chords-only head has no tune to invent",
        )

    def test_a_soprano_only_selection_arranges_nothing(self):
        """Naming soprano routes to the melody-bearing branch, where there is no tune.

        **This is the one refusal left, and it is not the same claim as the grid's
        deference.** `every_note` used to be silent here too, and that was the defect; a
        melody-only selection is silent because it *plays the tune and nothing else*, so a
        bar with no tune has nothing for it to play. A grid can place a chord there and a
        soprano cannot voice one without a top note. `melody_only_selection` gates the
        union in `arrange_xml_head`, which is why this still returns nothing while
        `alto,tenor` above now returns all four bars.
        """
        steps, _head, _notes = arrange_xml_head(CHORDS_ONLY, melody="soprano")
        self.assertEqual(steps, [])

    def test_a_named_grid_places_the_chords(self):
        """`freddie`, `joe_pass` and `final_and` each produce a part — the payoff.

        Exactly the rhythm each pattern names on a 4/4 bar: `freddie` a chord on every
        beat (16 = 4 bars x 4), `joe_pass` on the *ands* (first at bar 1 beat 1.5), and
        `final_and` on the final beat's upbeat (first at bar 1 beat 4.5). Every slot
        carries `melody=None`, because the file has no tune — the honest absence step B
        made expressible, not the deleted placeholder.
        """
        expected = {
            "freddie": ((1.0, "Dm7"), 16),
            "joe_pass": ((1.5, "Dm7"), 16),
            "final_and": ((4.5, "Dm7"), 4),
        }
        for grid, (first, count) in expected.items():
            with self.subTest(grid=grid):
                steps, _head, _notes = arrange_xml_head(
                    CHORDS_ONLY, melody="alto,tenor", grid=grid
                )
                self.assertEqual(len(steps), count, f"grid={grid}")
                self.assertEqual((steps[0].beat, steps[0].chord), first)
                self.assertTrue(
                    all(step.melody is None for step in steps),
                    f"grid={grid} invented a melody for a chords-only head",
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
        longer than the notes in it; `tabxml._events` caps a note at the length the
        file wrote, so the surplus became a **rest of about 1e-06 quarters** - a
        length MusicXML cannot express, and which music21 inflates to a whole
        triplet note. Measured on `i_was_doing_all_right.mxl`: **13 such rests and
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
        events, _pickup = _events(_substitute_steps(steps), head.beats_per_bar, True,
                                  head.beat_type)
        # Every rest is a real one: at least a sixteenth. The sixteenth is the
        # shortest event `_events` will write (`_MIN_EVENT_LENGTH`), so anything
        # shorter is a rounding artefact rather than silence the score contains.
        unexpressible = [
            length for step, _strikes, length in events
            if step is None and length < 0.25 - 1e-9
        ]
        self.assertEqual(unexpressible, [])

    def test_a_tuplet_head_keeps_every_note_on_every_grid(self):
        """The end-to-end claim, on the committed score rather than a hand-built one.

        A hand-built fixture is fine for a rule but not for a count: the point here is
        that the reduction no longer *loses notes of the tune*, and the only honest way
        to say that is against a real score's note count. `i_was_doing_all_right.mxl`
        carries 39 tuplets among its 110 written notes, and before this rule `eighths`
        kept 86 of them - losing 11 in the tuplet bars and **13 in the straight ones**,
        because two notes closer together than the grid collided.

        **78, not 39, is the tuplet count on the expanded head.** The score has a repeat,
        so its tuplet-bearing first section is played twice and every tuplet is stated on
        both passes: 39 written tuplets, 78 played. The claim - every note kept - is what
        the equality below asserts, and it holds at either count.
        """
        head = load_musicxml(I_WAS_DOING_ALL_RIGHT)
        # Every written note, including all 78 played tuplets (39 written, doubled by the
        # repeat). Under `eighths` this head used to keep 86 of 110 - losing 11 in the
        # tuplet bars and **13 in the straight ones**, because two notes closer together
        # than the grid shared a slot and one was dropped from the arrangement without a
        # word.
        self.assertEqual(len(head_skeleton(head)), len(head.notes))
        self.assertEqual(sum(1 for n in head.notes if n.tuplet), 78)

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
        """
        steps, _head, _notes = arrange_xml_head(
            self.path(harmony("D", "dominant", bass="C") + note("F", octave=4)),
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


class TestTheMetreHasADenominator(unittest.TestCase):
    """`beat` is a notated beat, and `beats_per_bar` is not the factor that produces one.

    `onset / divisions` is a count of **quarters** and a beat is `4 / beat_type` of them,
    so a note's beat is `1 + onset/divisions * beat_type/4`. Written as
    `beats_per_bar / 4` the factor agrees exactly when the numerator equals the
    denominator - 4/4 and 2/2, which is **six of the seven** committed heads - so the
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
        already round-tripped **22 and 27** extra beats on this head before this change,
        `every_note` **5**. The claim that actually matters is the one the assertion was a
        proxy for - every written beat comes back at the same beat - and that still holds
        exactly. What is asserted instead is that the extras are *only* the melody-less
        bars, so a round trip cannot silently add a beat inside a bar the tune has.
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
        # Every beat the file wrote comes back at the same beat - the claim.
        original = {(n.bar, round(n.beat, 6)) for n in written}
        surviving = {(n.bar, round(n.beat, 6)) for n in reread}
        self.assertTrue(original <= surviving, sorted(original - surviving)[:5])
        # And the extras are confined to the bars the melody never entered.
        melody_bars = {n.bar for n in head.notes}
        for bar, _beat in surviving - original:
            self.assertNotIn(bar, melody_bars, f"bar {bar} has notes and gained a beat")
        for original_note, copy in zip(written, (n for n in reread
                                                if n.bar in melody_bars)):
            self.assertAlmostEqual(original_note.beat, copy.beat, places=6, msg=str(copy))


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


class TestANarrowPaletteNeverLosesTheTune(unittest.TestCase):
    """A grip a chord cannot be voiced with must not take the melody note with it.

    `--grips shell` is the caller naming one family for the whole arrangement, and
    the family that has the least room to give: a shell states the chord's 3rd and
    7th and may sound **nothing** outside the chord, so a melody the non-chord-tone
    table cannot reharmonise has no candidate at all - where the four-note families
    keep a quality-only fallback to thin. "But Not For Me" bar 2 beat 2 is the
    smallest case: F4 over Ebmaj, the 9th over a plain triad.
    """

    def test_the_ninth_over_a_triad_is_voiced_rather_than_dropped(self):
        """The `maj` row reaches the shell family, so the step exists again.

        Before the row, this step had no candidate and `arrange_progression`
        dropped it with a warning - 76 steps out of 80 notes. The other three
        losses on this head are bars 18 and 22 (the same chord and note) and bar
        28, which is a different degree over a different quality.
        """
        steps, _head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, grips=("shell",))
        bar2 = [s for s in steps if s.bar == 2 and abs((s.beat or 0) - 2.0) < 1e-6]
        self.assertEqual(len(bar2), 1, "bar 2 beat 2 is missing again")
        step = bar2[0]
        self.assertEqual(step.melody, "F4")
        self.assertEqual(step.chord, "Ebmaj")
        self.assertEqual(step.harmonized_as, "Ebadd9")
        self.assertEqual(step.strategy, "extension")
        self.assertEqual(step.grip, "shell")
        # The 3rd, the 5th and the 9th: G Bb F, the shape a shell of Ebadd9 is.
        self.assertEqual({m % 12 for m in step.voicing.midi_notes()}, {5, 7, 10})

    def test_no_melody_note_is_dropped_by_a_palette_that_cannot_voice_it(self):
        """80 steps for 80 notes under `--grips shell`; it was 76.

        The four losses were bars 2, 18 and 22 (F4 over Ebmaj, the table row above)
        and bar 28 (Bb4 over F#dim7, which no dim7 shell can carry and which now
        sounds alone). The **count** is the assertion because a lost note is an
        absence: nothing in an arrangement says one should have been there.
        """
        steps, head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, grips=("shell",))
        self.assertEqual(len(steps), len(head.notes))

    def test_the_rescued_step_says_the_chord_is_not_sounding(self):
        """One step on this head has a chord and no voicing of it: bar 28.

        Reported rather than silently thin, because a bare note under a chord symbol
        reads as the chord being played quietly - see `ArrangementStep.chord_unvoiced`.
        """
        steps, _head, _notes = arrange_xml_head(BUT_NOT_FOR_ME, grips=("shell",))
        rescued = [s for s in steps if s.chord_unvoiced]
        self.assertEqual(len(rescued), 1)
        step = rescued[0]
        self.assertEqual((step.bar, step.beat), (28, 2.0))
        self.assertEqual(step.chord, "F#dim7")
        self.assertEqual(step.melody, "Bb4")
        self.assertEqual(step.grip, "melody")
        self.assertFalse(step.melody_only)
        self.assertIn("no voicing for this chord", arranger._step_annotation(step))


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



def _bar(number: int, pitch: str, inner: str = "", barline: str = "") -> str:
    """One whole-note measure with an optional harmony and barline, for repeat tests.

    `divisions=4` and a 4/4 bar, so a whole note is `duration` 16 and every measure is
    full. The synthetic counterpart to the committed scores: a real file cannot be
    edited to add the ending or the `times` a case needs.
    """
    return (
        f'<measure number="{number}">'
        + barline
        + inner
        + "<note><pitch>"
        + f"<step>{pitch[0]}</step><octave>{pitch[1]}</octave>"
        + "</pitch><duration>16</duration><type>whole</type></note>"
        + "</measure>"
    )


class TestRepeats(unittest.TestCase):
    """A score's repeats and volta endings: the head plays what a performer plays.

    Before this the loader read every `<measure>` once in document order, so a backward
    repeat was ignored and both endings were played. The tests below are the synthetic
    cases (a real file cannot be edited to add one) plus the committed score, whose play
    order and bar count are the end-to-end pin.
    """

    def load(self, measures: str, beats: int = 4, beat_type: int = 4) -> Head:
        # The divisions and metre go in the **first** measure rather than a synthetic
        # bar 0: an extra measure would be a bar of the play order with no notes, and the
        # absolute numbering these tests read is a fact about the play order.
        attributes = (
            f"<attributes><divisions>4</divisions>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
            "</attributes>"
        )
        opening = measures.find(">") + 1
        measures = measures[:opening] + attributes + measures[opening:]
        document = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<score-partwise version="3.1">\n'
            "  <part-list><score-part id=\"P1\"><part-name>Voice</part-name>"
            "</score-part></part-list>\n"
            '  <part id="P1">\n'
            f"{measures}\n"
            "  </part>\n</score-partwise>\n"
        )
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        return load_musicxml(path)

    def test_a_backward_repeat_plays_the_section_twice(self):
        """Four written bars with a backward repeat at the last play as eight.

        The simplest expansion, and the one the count speaks for: `bar` is renumbered to
        the absolute play order (1-8) and `written_bar` keeps the score's own (1-4, twice).
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4") + _bar(3, "E4")
            + _bar(4, "F4", barline='<barline location="right">'
                                 '<repeat direction="backward"/></barline>')
        )
        head = self.load(measures)
        self.assertEqual(head.bars, (1, 9), "4 written bars played twice is 8 bars")
        self.assertEqual([n.bar for n in head.notes], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(
            [n.written_bar for n in head.notes], [1, 2, 3, 4, 1, 2, 3, 4]
        )


    def test_the_second_ending_replaces_the_first_on_the_repeat(self):
        """The 1st/2nd ending taken in turn: play the 1st, repeat, skip it, play the 2nd.

        Bars 1-2 are the body, bar 3 the 1st ending (which carries the backward repeat),
        bar 4 the 2nd. A player hears `1 2 3 | 1 2 4` - six bars, and `written_bar` shows
        exactly which pass each one came from.
        """
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(
                3, "E4",
                barline=(
                    '<barline location="left"><ending number="1" type="start"/></barline>'
                    '<barline location="right"><ending number="1" type="stop"/>'
                    '<repeat direction="backward"/></barline>'
                ),
            )
            + _bar(
                4, "F4",
                barline=(
                    '<barline location="left"><ending number="2" type="start"/></barline>'
                    '<barline location="right"><ending number="2" type="stop"/></barline>'
                ),
            )
        )
        head = self.load(measures)
        self.assertEqual([n.written_bar for n in head.notes], [1, 2, 3, 1, 2, 4])
        self.assertEqual([n.bar for n in head.notes], [1, 2, 3, 4, 5, 6])

    def test_times_three_plays_the_section_three_times(self):
        """`times` is honoured rather than assumed to be two."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(3, "E4", barline='<barline location="right">'
                                 '<repeat direction="backward" times="3"/></barline>')
        )
        head = self.load(measures)
        self.assertEqual([n.bar for n in head.notes], [1, 2, 3, 4, 5, 6, 7, 8, 9])

    def test_a_forward_repeat_is_the_jump_back_target(self):
        """An explicit `direction="forward"` replaces the repeat-to-start default."""
        measures = (
            _bar(1, "C4")
            + _bar(2, "D4", barline='<barline location="left">'
                                  '<repeat direction="forward"/></barline>')
            + _bar(3, "E4", barline='<barline location="right">'
                                  '<repeat direction="backward"/></barline>')
        )
        head = self.load(measures)
        # Bar 1 once, then 2-3 twice: 1 2 3 2 3.
        self.assertEqual([n.written_bar for n in head.notes], [1, 2, 3, 2, 3])

    def test_a_head_with_no_repeat_is_untouched(self):
        """No barlines: nothing is renumbered and no markers are recorded.

        The contract that keeps the six non-repeating committed scores loading exactly as
        they did. `written_bar` is always the score's own number - it equals `bar` here
        because no repeat moved anything - and `markers` stays empty.
        """
        head = self.load(_bar(1, "C4") + _bar(2, "D4"))
        self.assertEqual([n.bar for n in head.notes], [1, 2])
        self.assertEqual([n.written_bar for n in head.notes], [1, 2])
        self.assertEqual(head.markers, [])


    def test_the_markers_name_the_repeat_and_both_endings(self):
        """The two-volta structure, on the bar numbers the expanded head landed on."""
        measures = (
            _bar(1, "C4") + _bar(2, "D4")
            + _bar(
                3, "E4",
                barline=(
                    '<barline location="left"><ending number="1" type="start"/></barline>'
                    '<barline location="right"><ending number="1" type="stop"/>'
                    '<repeat direction="backward"/></barline>'
                ),
            )
            + _bar(
                4, "F4",
                barline=(
                    '<barline location="left"><ending number="2" type="start"/></barline>'
                    '<barline location="right"><ending number="2" type="stop"/></barline>'
                ),
            )
        )
        head = self.load(measures)
        marks = sorted((m.bar, m.kind) for m in head.markers)
        self.assertEqual(
            marks,
            [
                (1, "repeat_start"),
                (3, "ending_start"),
                (3, "ending_stop"),
                (3, "repeat_end"),
                (6, "ending_start"),
                (6, "ending_stop"),
            ],
        )

    def test_the_committed_rainy_day_plays_its_repeat(self):
        """The end-to-end case: 36 written bars, the 1st ending skipped on the repeat.

        `heres_that_rainy_day` is 1-30, then ending 1 (31-32) with the backward repeat,
        then ending 2 (33-36). Played, that is `1-30, 31-32, 1-30, 33-36` - 66 bars - and
        the melody note count rises from 113 written to 160 played.
        """
        head = load_musicxml(RAINY_DAY)
        self.assertEqual(head.bars, (1, 67))
        self.assertEqual(len(head.notes), 160)
        # The 1st ending is written bars 31-32, but bar 32 has no note of its own: its
        # G4 is the tie-stop of bar 31's held note, so the ending contributes one written
        # bar of melody. The 2nd ending (written 33-36) is a four-bar tie chain and
        # likewise contributes one, at absolute bars 63-66.
        self.assertEqual(
            sorted({n.written_bar for n in head.notes if n.bar in (31, 32)}), [31]
        )
        self.assertEqual(
            sorted({n.written_bar for n in head.notes if n.bar in (63, 64, 65, 66)}),
            [33],
        )
        # And the repeat's own written bar - 32 - is never a melody bar at all.
        self.assertEqual([n.bar for n in head.notes if n.written_bar == 32], [])

    def test_the_play_order_maps_back_to_the_written_bars(self):
        """`Head.written_bars` is the inverse the writers need to write a written score.

        The arrangement is the 66 bars a player plays; a notation file holds the 36 the
        score writes, with the repeat signposted. `_as_written` is the fold between them,
        and it moves the markers onto the written bars at the same time.
        """
        from arranger.cli import _as_written

        steps, head, _ = arrange_xml_head(RAINY_DAY)
        self.assertEqual(head.bars, (1, 67))
        written_steps, written_markers = _as_written(
            steps, head.markers, head.written_bars
        )
        bars = sorted(
            {bar for bar in (step.bar for step in written_steps) if bar is not None}
        )
        self.assertEqual(bars, list(range(1, 37)))
        self.assertEqual(
            [(m.bar, m.kind) for m in written_markers],
            [
                (1, "repeat_start"),
                (31, "ending_start"),
                (32, "ending_stop"),
                (32, "repeat_end"),
                (33, "ending_start"),
                (36, "ending_stop"),
            ],
        )

    def test_a_head_with_no_repeat_projects_to_itself(self):
        """No markers and no map: `_as_written` is the identity on the arrangement."""
        from arranger.cli import _as_written

        steps, head, _ = arrange_xml_head(BUT_NOT_FOR_ME)
        self.assertEqual(head.markers, [])
        self.assertEqual(head.written_bars, {})
        written_steps, written_markers = _as_written(
            steps, head.markers, head.written_bars
        )
        self.assertEqual([s.bar for s in written_steps], [s.bar for s in steps])
        self.assertEqual(written_markers, [])


class TestRepeatSignsInTheAsciiStaff(unittest.TestCase):
    """The tab staff draws the `|:` / `:|` and the volta numbers the markers name.

    The staff is the display the head CLI prints, so a reader can see the repeat rather
    than only the extra bars it produced. The signs ride the barline of the bar they open
    - `|:` on a repeat's start, `:|` on the bar after its end - and an ending's number is
    a label row (`1.` / `2.`) above the staff.
    """

    def _arrangement(self, count: int = 8):
        engine = arranger.VoiceLeadingEngine()
        progression = [
            ("A4", "m7", "Dm7"), ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7"),
            ("A4", "m7", "Am7"), ("C5", "7", "D7"), ("B4", "maj7", "Fmaj7"),
            ("A4", "m7", "Bm7"), ("C5", "7", "E7"),
        ][:count]
        steps = engine.arrange_progression(progression)
        for index, step in enumerate(steps):
            step.bar = 1 + index // 4
            step.beat = 1.0 + index % 4
            step.duration = 0.25
        return steps

    def test_no_markers_draws_no_repeat_signs(self):
        """The default staff is unchanged - the markers are the only thing that adds signs."""
        text = format_tab_staff(self._arrangement(), measures_per_line=2)
        self.assertNotIn("|:", text)
        self.assertNotIn(":|", text)

    def test_repeat_start_and_end_ride_their_barlines(self):
        from headxml import BarMarker

        markers = [
            BarMarker(bar=1, kind="repeat_start", written_bar=1),
            BarMarker(bar=2, kind="repeat_end", written_bar=2, times=2),
        ]
        text = format_tab_staff(
            self._arrangement(), measures_per_line=2, markers=markers
        )
        self.assertIn("e*|:", text, "the opening barline of bar 1 should be a repeat")
        self.assertIn(":|", text, "bar 2's close should be a repeat")

    def test_a_volta_number_is_labelled_above_the_staff(self):
        from headxml import BarMarker

        markers = [
            BarMarker(bar=1, kind="ending_start", written_bar=1, numbers=(1,)),
            BarMarker(bar=2, kind="ending_stop", written_bar=2, numbers=(1,)),
        ]
        text = format_tab_staff(
            self._arrangement(), measures_per_line=2, markers=markers
        )
        self.assertIn("1.", text)

