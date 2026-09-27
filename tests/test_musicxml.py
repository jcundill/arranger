"""Tests for the MusicXML renderer in `tabxml`.
Guarded on music21 being installed, exactly as the database-backed tests are guarded
on `wjazzd.db`: it is an optional extra, and a fresh clone runs a reduced suite.
Every test here checks the *document* - the XML a notation program receives - rather
than the music21 objects that produced it, because the document is the contract.
"""
import os
import tempfile
import unittest
from xml.etree import ElementTree
from arranger import ArrangementStep, Voicing, VoiceLeadingEngine
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

    def tab_part(self, root):
        """The tab part's element, found by its TAB clef rather than by position."""
        for part in root.findall("part"):
            for clef in part.iter("clef"):
                sign = clef.find("sign")
                if sign is not None and sign.text == "TAB":
                    return part
        self.fail("no tab part in the document")

    def other_part(self, root):
        """The notation part, i.e. the one that is not the tab staff."""
        tab = self.tab_part(root)
        for part in root.findall("part"):
            if part is not tab:
                return part
        self.fail("no notation part in the document")

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

    def fretted(self, part):
        """(string, fret) for every note that carries a position."""
        found = []
        for note in self.notes(part):
            for technical in note.iter("technical"):
                string = technical.find("string")
                fret = technical.find("fret")
                if string is not None and fret is not None:
                    found.append((string.text, fret.text))
        return found

@requires_music21

class TestMusicXMLDocument(MusicXMLTestCase):
    """The document is well-formed MusicXML with the staves a guitar needs."""

    def test_is_well_formed_score_partwise(self):
        """The output parses as XML and is a score, not an arbitrary tree."""
        root = self.root()
        self.assertEqual(root.tag, "score-partwise")

    def test_has_a_tab_staff_and_a_notation_staff(self):
        """Both staves are present by default, and the tab one is a TAB clef."""
        root = self.root()
        self.assertEqual(len(root.findall("part")), 2)
        self.assertIsNotNone(self.tab_part(root))
        self.assertIsNotNone(self.other_part(root))

    def test_the_tab_staff_has_six_lines(self):
        """
        `<staff-lines>6</staff-lines>` is what makes a staff a tab staff.
        music21 does not write it for a TabClef, so `tabxml` adds it. Without it a
        reader assumes five lines and every fret lands on the wrong one.
        """
        lines = self.tab_part(self.root()).iter("staff-lines")
        values = [node.text for node in lines]
        self.assertTrue(values, "the tab staff declares no staff-lines")
        self.assertEqual(set(values), {"6"})

    def test_show_notation_false_gives_one_staff(self):
        """`show_notation=False` drops the notation staff, keeping the tab."""
        root = self.root(show_notation=False)
        self.assertEqual(len(root.findall("part")), 1)
        self.assertIsNotNone(self.tab_part(root))

    def test_time_signature_is_written(self):
        """The time signature reaches the reader, and every measure carries it."""
        part = self.tab_part(self.root())
        beats = [node.text for node in part.iter("beats")]
        self.assertIn("4", beats)

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

class TestMusicXMLFretting(MusicXMLTestCase):
    """The fretting survives the round trip - which is the point of a tab staff."""

    def test_every_sounding_note_carries_a_fret_and_a_string(self):
        """
        Every note of every shape has its own `<fret>` and `<string>`.
        This is the regression the renderer exists for: music21 writes all of a
        chord's fret data onto the chord's *first* note and leaves the rest bare
        (cuthbertLab/music21#1534), and a note with no fret has no position at all -
        notation software then computes one from the pitch and puts the shape in the
        wrong place on the neck.
        """
        tab = self.tab_part(self.root())
        sounded = self.notes(tab)
        self.assertTrue(sounded)
        self.assertEqual(len(self.fretted(tab)), len(sounded))

    def test_the_strings_and_frets_are_the_ones_the_engine_chose(self):
        """
        The written positions match `Voicing.frets`, string 6 being the low E.
        String *numbering* is the one thing that can silently transpose a shape:
        music21 and MusicXML number the high E as string 1, while the library indexes
        strings 0 (low E) to 5 (high E), so the index is flipped on the way out.
        """
        tab = self.tab_part(self.root())
        for step in self.steps:
            for index, fret in enumerate(step.voicing.frets):
                if fret < 0:
                    continue
                self.assertIn((str(6 - index), str(fret)), self.fretted(tab))

    def test_a_held_shape_is_not_rewritten_as_a_second_attack(self):
        """A repeated melody is a single note, as it is in the tab."""
        from arranger import format_musicxml
        step = make_step([-1, -1, 3, 5, 5, -1], repeated=True)
        root = ElementTree.fromstring(format_musicxml([step]))
        sounded = self.notes(self.tab_part(root))
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
        self.assertEqual(len(self.attacks(self.tab_part(root))), len(self.steps))

    def test_timing_places_the_chords_in_bars(self):
        """Three chords spread over the first two beats of two bars fill two bars."""
        self.timed_steps()
        measures = self.tab_part(self.root()).findall("measure")
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

    def test_chord_symbols_appear_once_per_change(self):
        """
        A symbol on every step would bury the tab, so one is written per change.
        The ii-V-I has three distinct chords, so three symbols - and not one per note.
        """
        root = self.root()
        self.assertEqual(len(self.symbols(self.tab_part(root))), len(self.steps))

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
        symbols = self.symbols(self.tab_part(root))
        self.assertEqual(len(symbols), 1)
        self.assertIn("sus4", ElementTree.tostring(symbols[0], encoding="unicode"))

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

        self.assertEqual(
            len(parsed.recurse().getElementsByClass(music21_stream.Part)), 2
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
