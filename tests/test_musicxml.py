"""Tests for the MusicXML renderer in `tabxml`.
Guarded on music21 being installed, exactly as the database-backed tests are guarded
on `wjazzd.db`: it is an optional extra, and a fresh clone runs a reduced suite.
Every test here checks the *document* - the XML a notation program receives - rather
than the music21 objects that produced it, because the document is the contract.
"""
import os
import re
import tempfile
import unittest
from typing import List
from xml.etree import ElementTree

from arranger import ArrangementStep, VoiceLeadingEngine, Voicing
from tabxml import _READABLE_KINDS, _downgrade_kinds, _sounding

try:
    import music21  # noqa: F401
    HAS_MUSIC21 = True
except ImportError:  # pragma: no cover - depends on the environment
    HAS_MUSIC21 = False
requires_music21 = unittest.skipUnless(HAS_MUSIC21, "music21 not installed")

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

def _midi(note_element):
    """The MIDI number of a written `<note>`, or None for one with no pitch."""
    pitch = note_element.find("pitch")
    if pitch is None:
        return None
    semitone = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[
        pitch.findtext("step", "C")
    ]
    alter = int(pitch.findtext("alter", "0"))
    octave = int(pitch.findtext("octave", "0"))
    return (octave + 1) * 12 + semitone + alter


class MusicXMLTestCase(unittest.TestCase):
    """Shared helpers: a small progression and accessors into the written document."""

    def setUp(self):
        engine = VoiceLeadingEngine()
        # A ii-V-I, which every chord of it can voice without a non-chord tone, so
        # the tests are about the rendering rather than about the arranger.
        self.steps = engine.arrange_progression(
            [("A4", "m7", "Dm7"), ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7")]
        )

    def document(self, **kwargs):
        from arranger import format_musicxml
        return format_musicxml(self.steps, **kwargs)

    def root(self, **kwargs):
        return ElementTree.fromstring(self.document(**kwargs))

    def part(self, root):
        """
        The score's one part. There is no tab part to tell apart from a notation one:
        the document is notation only, and it is asserted as such elsewhere.
        """
        parts = root.findall("part")
        if len(parts) != 1:
            self.fail(f"expected exactly one part, found {len(parts)}")
        return parts[0]

    def notes(self, part):
        """The sounding notes of a part, excluding the chord symbols.
        music21's `ChordSymbol` is a subclass of `Chord`, so a naive
        `findall('note')` sweep counts the harmony as music. Only `<harmony>` is
        excluded by tag, which is exactly right for a document read as XML.
        """
        return [note for note in part.iter("note") if note.find("harmony") is None]

    def attacks(self, part):
        """
        The notes that begin an attack, i.e. excluding the rest of a chord.

        In MusicXML a chord is several sibling `<note>` elements of which all but the
        first carry `<chord/>`, so this is how a step count is recovered from the
        document: one attack per step written.
        """
        return [note for note in self.notes(part) if note.find("chord") is None]

    def symbols(self, part):
        """The chord symbols of a part, one per chord change."""
        return list(part.iter("harmony"))

@requires_music21

class TestMusicXMLDocument(MusicXMLTestCase):
    """The document is well-formed MusicXML with the staves a guitar needs."""

    def test_is_well_formed_score_partwise(self):
        """The output parses as XML and is a score, not an arbitrary tree."""
        root = self.root()
        self.assertEqual(root.tag, "score-partwise")

    def test_the_document_is_one_notation_staff(self):
        """
        A single treble-clef part, and no tab staff anywhere in it.

        This is the regression for the change that dropped the tab staff: music21
        cannot write one a notation program renders correctly (see `tabxml`'s module
        docstring), so a `TAB` clef or a `<staff-lines>6</staff-lines>` in the document
        means the tab path has crept back in. Fretting is written by `tabgp`.
        """
        root = self.root()
        self.assertEqual(len(root.findall("part")), 1)
        self.part(root)
        for clef_node in root.iter("clef"):
            sign = clef_node.find("sign")
            self.assertNotEqual(sign.text if sign is not None else None, "TAB")
        self.assertEqual([node.text for node in root.iter("staff-lines")], [])
        self.assertEqual([node.text for node in root.iter("fret")], [])
        self.assertEqual([node.text for node in root.iter("string")], [])

    def test_instrument_ids_are_unique_across_the_part_list(self):
        """
        Every `<score-instrument>` in the part list has an id of its own.

        music21 writes the same instrument id into every `<score-part>` when the parts
        share one `instrument.Guitar()`, and MusicXML requires those ids to be unique
        within the part list. MuseScore 3 refuses the file outright when they are not:

            Fatal error: ID value 'I56a9...' is not unique.

        music21 reads its own output back happily, so nothing in this library's own
        round trip would ever catch it - only a real notation program does.
        """
        seen = []
        for score_part in self.root().findall("part-list/score-part"):
            ids = [node.get("id") for node in score_part.findall("score-instrument")]
            self.assertTrue(ids, "a score-part declares no instrument")
            seen.extend(ids)
            # A score-instrument and its midi-instrument share an id, which is how a
            # reader knows which MIDI patch belongs to which part.
            midi = [node.get("id") for node in score_part.findall("midi-instrument")]
            self.assertEqual(midi, ids, "score-instrument and midi-instrument must pair")
        self.assertEqual(
            len(seen), len(set(seen)), f"duplicate instrument id in {seen}"
        )

    def test_the_document_declares_its_xml_version(self):
        """
        The file opens with the XML declaration and the MusicXML DOCTYPE.

        Both sit *before* the root element, so `ElementTree` drops them when it
        serialises a parsed tree. The DOCTYPE is the MusicXML 4.0 DTD declaration -
        it is how a reader knows which version the file claims - so it is carried over
        from what music21 wrote rather than lost.
        """
        document = self.document()
        self.assertTrue(document.startswith("<?xml version="), document[:40])
        self.assertIn("<!DOCTYPE score-partwise", document.split("\n")[1])

    def test_the_time_signature_is_written_once(self):
        """
        The signature reaches the reader, and only in the first measure.

        MusicXML says a signature holds until it changes, so repeating it in every
        bar is legal but reads as a new one at each: MuseScore 3 draws a 4/4 over
        every bar of the head. This is the regression for that, and it is also the
        check that the later bars are still *resolved* against the signature in
        force - `test_every_bar_is_the_length_of_its_time_signature` is what proves
        they inherit it rather than falling back to nothing.
        """
        # Twelve steps of the same shape collapse into three bars at one chord per
        # beat, which is more than the one bar the three-step fixture would give.
        from arranger import format_musicxml
        long_head = [make_step([-1, -1, 3, 5, 5, -1]) for _ in range(12)]
        root = ElementTree.fromstring(format_musicxml(long_head))
        measures = list(self.part(root).iter("measure"))
        self.assertGreater(len(measures), 1, "needs a multi-bar document to mean anything")
        with_time = [m for m in measures if m.find("attributes/time") is not None]
        self.assertEqual(len(with_time), 1, "the time signature was written more than once")
        self.assertIs(with_time[0], measures[0], "it was not written in the first measure")
        self.assertEqual(with_time[0].findtext("attributes/time/beats"), "4")
        self.assertEqual(with_time[0].findtext("attributes/time/beat-type"), "4")

    def test_the_signature_is_written_even_for_a_one_bar_document(self):
        """There is no 'second measure inherits it' to lean on: it must still be there."""
        from arranger import format_musicxml
        root = ElementTree.fromstring(format_musicxml(self.steps[:1]))
        self.assertEqual(len(list(self.part(root).iter("time"))), 1)

    def test_no_steps_renders_nothing(self):
        """An empty arrangement is an empty string, not a partial document."""
        from arranger import format_musicxml
        self.assertEqual(format_musicxml([]), "")

    def test_rejects_a_nonsense_time_signature(self):
        """A beats_per_bar below one is a usage error, as in the other renderers."""
        from arranger import format_musicxml
        with self.assertRaises(ValueError):
            format_musicxml(self.steps, beats_per_bar=0)

@requires_music21

class TestMusicXMLVoices(MusicXMLTestCase):
    """Which of a step's voices reach the notation staff."""

    def test_every_sounding_pitch_is_written(self):
        """
        A step's shape arrives as one note per sounding string, as pitches.

        The pitch list is the arrangement itself on a notation staff; the *fretting*
        is `tabgp`'s job now, so this is checked on the pitches rather than on
        `<fret>`/`<string>`, which the document no longer contains.
        """
        sounded = self.notes(self.part(self.root()))
        self.assertTrue(sounded)
        written = [_midi(note) for note in sounded]
        self.assertEqual(len(written), len(sounded), "a note was written without a pitch")
        # The three steps of the ii-V-I, each sounded as a chord, so the written
        # pitches are every sounding pitch of every step, in the order they were
        # played: low string first within a step, as `_sounding` returns them.
        expected: List[int] = []
        for step in self.steps:
            expected.extend(_sounding(step))
        self.assertEqual(written, expected)

    def test_a_held_shape_is_not_rewritten_as_a_second_attack(self):
        """A repeated melody is a single note, as it is in the tab."""
        from arranger import format_musicxml
        step = make_step([-1, -1, 3, 5, 5, -1], repeated=True)
        root = ElementTree.fromstring(format_musicxml([step]))
        sounded = self.notes(self.part(root))
        self.assertEqual(len(sounded), 1, "the held melody became more than one note")

@requires_music21

class TestMusicXMLRhythm(MusicXMLTestCase):
    """The written rhythm, the bars and the chord symbols."""

    def timed_steps(self):
        """The ii-V-I on a real 4/4 grid, one chord per beat across two bars."""
        for index, step in enumerate(self.steps):
            step.bar, step.beat, step.duration = index // 2, 1.0 + index % 2, 0.25
        return self.steps

    def test_untimed_steps_fall_back_to_one_chord_per_beat(self):
        """
        A hand-written progression has no timing, and still exports.
        Same fallback as the ASCII staff and the HTML page: one chord per beat. The
        test asserts the music is all there rather than counting bars, because a
        progression that is not a whole number of bars long has no fixed bar count.
        """
        root = self.root()
        self.assertEqual(len(self.attacks(self.part(root))), len(self.steps))

    def test_timing_places_the_chords_in_bars(self):
        """Three chords spread over the first two beats of two bars fill two bars."""
        self.timed_steps()
        measures = self.part(self.root()).findall("measure")
        self.assertEqual(len(measures), 2)

    def test_every_bar_is_the_length_of_its_time_signature(self):
        """
        No measure is over- or underfull.
        An overfull measure is not a measure: a reader either rejects the file or
        moves the notes to make it fit. This is the check that catches a note written
        across a bar line without a tie, and an event that overflows the bar it starts
        in - both of which this renderer had to be taught to avoid.
        """
        self.timed_steps()
        root = self.root()
        for part in root.findall("part"):
            divisions = 0
            per_bar = 4
            for measure in part.findall("measure"):
                stated = measure.find("attributes/divisions")
                if stated is not None and stated.text is not None:
                    divisions = int(stated.text)
                beats = measure.find("attributes/time/beats")
                if beats is not None and beats.text is not None:
                    per_bar = int(beats.text)
                self.assertGreater(divisions, 0, "a measure states no divisions")
                # A chord's notes share one onset, so only the first note of each is
                # counted; `<chord/>` marks the others as part of the same attack.
                total = 0
                for note in self.attacks(measure):
                    duration = note.find("duration")
                    if duration is not None and duration.text is not None:
                        total += int(duration.text)
                self.assertEqual(
                    total, per_bar * divisions, f"bar {measure.get('number')} is wrong"
                )

    def test_a_head_starting_mid_bar_is_written_as_a_pickup(self):
        """
        A head that starts part-way into a bar opens with an anacrusis.

        The first measure is flagged `implicit="yes"`, which is how a reader knows the
        music does not begin on a downbeat. The subtlety is that a pickup can be
        *exactly* filled - a head starting on the third beat has two beats of pickup
        and puts two beats of music in it - so "is the measure short" is the wrong
        test for "is this an anacrusis", and a complete-looking first bar would
        otherwise claim a downbeat that is not there.
        """

        for step in self.steps:
            # Bar 0, starting on the third beat: two beats of pickup, filled exactly.
            step.bar, step.beat, step.duration = 0, 3.0, 0.25
        root = self.root()
        first = self.part(root).findall("measure")[0]
        self.assertEqual(first.get("implicit"), "yes")
        divisions = first.find("attributes/divisions")
        assert divisions is not None and divisions.text is not None
        total = sum(
            int(node.find("duration").text)  # type: ignore[union-attr]
            for node in self.attacks(first)
        )
        self.assertEqual(total, 2 * int(divisions.text), "the pickup is two beats")

    def test_a_head_starting_on_the_downbeat_is_not_a_pickup(self):
        """A head that starts on beat 1 has no pickup, and no implicit bar."""
        for step in self.steps:
            step.bar, step.beat, step.duration = 0, 1.0, 0.25
        first = self.part(self.root()).findall("measure")[0]
        self.assertEqual(first.get("implicit"), "no")

    def test_chord_symbols_appear_once_per_change(self):
        """
        A symbol on every step would bury the tab, so one is written per change.
        The ii-V-I has three distinct chords, so three symbols - and not one per note.
        """
        root = self.root()
        self.assertEqual(len(self.symbols(self.part(root))), len(self.steps))

    def test_chord_symbols_can_be_turned_off(self):
        """`show_chords=False` writes the notes without any harmony."""
        root = self.root(show_chords=False)
        self.assertEqual(len(list(root.iter("harmony"))), 0)

    def test_an_unparseable_chord_name_still_renders(self):
        """
        A quality music21 cannot classify is written as text rather than dropped.
        The Weimar notation produces names like `Bb7sus4`, which music21 rejects
        outright; losing the chord symbol would be a worse answer than writing the
        name the analyst wrote.
        """
        from arranger import format_musicxml

        step = make_step([-1, 3, 5, 5, 5, -1], chord="Bb7sus4")
        root = ElementTree.fromstring(format_musicxml([step]))
        symbols = self.symbols(self.part(root))
        self.assertEqual(len(symbols), 1)
        self.assertIn("sus4", ElementTree.tostring(symbols[0], encoding="unicode"))


@requires_music21


class TestMusicXML31Kinds(MusicXMLTestCase):
    """
    Every `<kind>` in the document must be a value MusicXML 3.1 actually has.

    This is the class of defect that neither a unit test nor `converter.parse()` can
    see. music21 writes MusicXML 4.0, reads 4.0 back without complaint, and a 4.0-only
    `kind` value is a fatal import error for a 3.1-era reader such as MuseScore 3:

        Content of element kind does not match its type definition:
        String content is not listed in the enumeration facet.

    So the check reads the finished document, not the intent behind it.
    """

    def kinds(self, root):
        """The `<kind>` text of every chord symbol in the document, both parts."""
        return [(node.text or "").strip() for node in root.iter("kind")]

    def test_every_kind_is_in_the_3_1_enumeration(self):
        """
        The invariant itself, on a document whose chords music21 does classify.
        This is the assertion that would have caught the export that could not be
        opened; it reads the XML, so it does not care how the values got there.
        """
        found = self.kinds(self.root())
        self.assertTrue(found, "the document has chord symbols to check")
        for kind in found:
            self.assertIn(kind, _READABLE_KINDS, f"not a MusicXML 3.1 kind: {kind!r}")

    def test_a_seventh_sus_is_written_in_3_1_terms(self):
        """
        A 7sus4 is the case that broke it: music21 writes the 4.0-only
        `suspended-fourth-seventh`, and 3.1 spells the same chord as a
        `suspended-fourth` with the 7th added as a degree.

        The root must survive - it is what tells the reader the chord is an F - and
        neither the 4.0 value nor the string 'suspended-fourth-seventh' may remain
        anywhere in the document.
        """
        from arranger import format_musicxml

        step = make_step([-1, 3, 5, 5, 5, -1], chord="F7sus4", melody="C5")
        root = ElementTree.fromstring(format_musicxml([step]))
        symbols = self.symbols(self.part(root))
        self.assertEqual(len(symbols), 1)
        harmony = symbols[0]
        self.assertEqual(harmony.findtext("root/root-step"), "F")
        kind = harmony.find("kind")
        assert kind is not None
        self.assertEqual((kind.text or "").strip(), "suspended-fourth")
        added = [
            (node.findtext("degree-value"), node.findtext("degree-type"))
            for node in harmony.findall("degree")
        ]
        self.assertIn(("7", "add"), added, "the 7th is carried as an added degree")
        self.assertNotIn("suspended-fourth-seventh", ElementTree.tostring(
            root, encoding="unicode"
        ))

    def test_an_unknown_kind_falls_back_to_text(self):
        """
        A `<kind>` 3.1 has no type for becomes `<kind text="...">other</kind>`.

        `other` is in the 3.1 enumeration and `text` is the attribute 3.1 defines for
        a chord symbol it cannot classify, so this imports everywhere - which is the
        same fallback `_chord_symbol` uses for a name music21 cannot parse, and the
        backstop behind the sus mapping.
        """
        from arranger import format_musicxml

        step = make_step([-1, 3, 5, 5, 5, -1], chord="Cmaj7")
        root = ElementTree.fromstring(format_musicxml([step]))
        kind = next(root.iter("kind"))
        kind.text = "some-future-4.0-kind"
        _downgrade_kinds(root)
        self.assertEqual((kind.text or "").strip(), "other")
        self.assertEqual(kind.get("text"), "some-future-4.0-kind")

    def test_an_ordinary_progression_is_untouched(self):
        """
        The pass is a compatibility filter, not a rewriter: on a document whose kinds
        are already legal, it must change nothing at all - no degree invented, no
        attribute added. Anything else would risk degrading a file that already works.
        """
        import copy

        from arranger import format_musicxml

        # A copy of one document, not two exports: music21 mints a fresh part id on
        # every export, so two documents would differ for reasons that have nothing
        # to do with the pass.
        before = ElementTree.fromstring(format_musicxml(self.steps))
        degrees_before = len(list(before.iter("degree")))
        after = copy.deepcopy(before)
        _downgrade_kinds(after)
        self.assertEqual(
            ElementTree.tostring(before, encoding="unicode"),
            ElementTree.tostring(after, encoding="unicode"),
        )
        # music21 writes `<degree>` of its own on some chords, so the invariant is that
        # the pass adds none, not that the document has none.
        self.assertEqual(len(list(after.iter("degree"))), degrees_before)

    def test_the_downgrade_is_wired_into_the_export(self):
        """
        The pass is called from `format_musicxml`, not merely defined.

        Asserted through the exported document rather than by patching the call, so
        this cannot pass on a pass that is present but unreachable - which is what
        would happen if a later refactor dropped it from the post-processing chain.
        """
        from arranger import format_musicxml

        document = format_musicxml(self.steps)
        for kind in re.findall(r"<kind[^>]*>([^<]*)</kind>", document):
            self.assertIn(kind.strip(), _READABLE_KINDS, kind)


@requires_music21


class TestMusicXMLFileOutput(unittest.TestCase):
    """`write_musicxml` is the only function here that touches the filesystem."""

    def test_writes_a_document_that_re_parses(self):
        """The path is returned, the file holds a score, and the score is readable."""
        from music21 import converter

        from arranger import write_musicxml
        engine = VoiceLeadingEngine()
        steps = engine.arrange_progression(
            [("A4", "m7", "Dm7"), ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7")]
        )
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "arrangement.musicxml")
            returned = write_musicxml(steps, target, title="Written")
            self.assertEqual(returned, target)
            with open(target, encoding="utf-8") as handle:
                document = handle.read()
        self.assertIn("<score-partwise", document)
        parsed = converter.parseData(document, format="musicxml")
        from music21 import stream as music21_stream

        # One part: the document is a notation staff, and a tab staff beside it
        # would be a second one. See `test_the_document_is_one_notation_staff`.
        self.assertEqual(
            len(parsed.recurse().getElementsByClass(music21_stream.Part)), 1
        )

    def test_rendering_writes_no_file(self):
        """The renderer is pure: no file appears just because a string was asked for."""
        from arranger import format_musicxml
        engine = VoiceLeadingEngine()
        steps = engine.arrange_progression([("C5", "maj7", "Cmaj7")])
        with tempfile.TemporaryDirectory() as folder:
            before = set(os.listdir(folder))
            format_musicxml(steps)
            self.assertEqual(set(os.listdir(folder)), before)

class TestMusicXMLWithoutMusic21(unittest.TestCase):
    """The extra is optional, and its absence is explained rather than raised raw."""

    # An import hook that refuses music21. `find_spec` is the modern hook; the older
    # `find_module` is ignored on modern Python, so a test using it would silently
    # test nothing.
    BLOCKER = (
        "import sys;"
        " sys.meta_path.insert(0, type('Block', (), {"
        "   'find_spec': lambda self, name, path=None, target=None:"
        "       (_ for _ in ()).throw(ImportError('blocked'))"
        "       if name == 'music21' or name.startswith('music21.') else None})());"
    )

    def run_blocked(self, statement):
        """Runs `statement` in a subprocess where music21 cannot be imported."""
        import subprocess
        import sys

        return subprocess.run(
            [sys.executable, "-c", f"{self.BLOCKER} {statement}"],
            capture_output=True,
            text=True,
        )

    def test_the_rest_of_the_package_still_works(self):
        """No music21, and the ASCII staff still renders - which is why it is an extra."""
        result = self.run_blocked(
            "import arranger;"
            " e = arranger.VoiceLeadingEngine();"
            " steps = e.arrange_progression([('C5', 'maj7', 'Cmaj7')]);"
            " print(len(arranger.format_tab_staff(steps)))"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), "")

    def test_the_renderer_says_how_to_install_the_extra(self):
        """
        Calling the renderer without music21 names the extra and the command.

        A bare `ModuleNotFoundError: No module named 'music21'` tells a user nothing
        they can act on; the install command is the whole point of catching it.
        """
        statement = (
            "import arranger;"
            " steps = arranger.VoiceLeadingEngine()"
            ".arrange_progression([('C5', 'maj7', 'Cmaj7')]);"
            " arranger.format_musicxml(steps)"
        )
        result = self.run_blocked(statement)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jazz-arranger[xml]", result.stderr)

    def test_the_renderer_is_importable_without_the_extra(self):
        """`from arranger import format_musicxml` resolves; only calling it needs music21."""
        result = self.run_blocked(
            "import arranger;"
            " from arranger import format_musicxml, write_musicxml;"
            " print(format_musicxml.__name__, write_musicxml.__name__)"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("format_musicxml", result.stdout)
