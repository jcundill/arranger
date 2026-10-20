"""The head CLI: the flags it parses and the output it dispatches.

`head_cli` is the only part of the importer that prints, so what it produces is a string
per writer rather than a returned value - and the flags are pinned here because a
default that moves is silent. The writers themselves are `test_guitarpro.py`,
`test_musicxml.py` and `test_staff_rendering.py`.
"""

import os
import tempfile
import unittest
from xml.etree import ElementTree

import arranger
from arranger import format_progression
from headxml import (
    arrange_xml_head,
    head_cli,
    load_musicxml,
)
from tests.support import (
    BUT_NOT_FOR_ME,
    I_WAS_DOING_ALL_RIGHT,
    RAINY_DAY,
    harmony,
    note,
    score,
    write_score,
)


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
        # 8 bars is 8 measures and not 16 half-length ones. Reading the beat count
        # as a quarter count is what doubled it.
        self.assertEqual(len(song.tracks[0].measures), 8)

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
        output = self.run_cli(self.score_path(), "--tab", "staff", "--note-names")
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

    def test_the_grips_flag_is_gone_and_a_list_flag_is_one_argument(self):
        """The deleted spelling is a usage error, and the surviving list is one string.

        `--grips` named a family list, and the family axis is deleted, so the flag is gone
        rather than deprecated: a spelling quietly ignored would arrange something other
        than what the run header reported. What survives of its lesson is `--chord-on`,
        the same shape of option - a list, spelled the way the flags beside it spell one -
        and it is one argument, never `nargs="+"`.
        """
        import io
        from contextlib import redirect_stderr

        from arranger.options import ArrangeOptions

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            self.run_cli(RAINY_DAY, "--grips", "shell,duo")
        self.assertIn("--grips", errors.getvalue())
        # And the library's spelling went with the flag, both halves of it.
        self.assertFalse(hasattr(arranger, "parse_grips"))
        self.assertFalse(hasattr(ArrangeOptions(), "grips"))

        output = self.run_cli(RAINY_DAY, "--bars", "1-3", "--chord-on", "1,2&")
        self.assertEqual(self.code, 0)
        self.assertIn("chord-on=1,2&", output)

    def test_a_flag_named_before_the_file_still_arranges_that_file(self):
        """`head --chord-on 1,2& FILE` finds the file.

        The quieter half of the old `nargs="+"` trap: an option that takes a list with
        spaces consumes the positional written after it, so it could only ever come last.
        One comma-separated string has no such order, and this is the round trip saying so.
        """
        output = self.run_cli("--bars", "1-3", "--chord-on", "1,2&", RAINY_DAY)
        self.assertEqual(self.code, 0)
        self.assertIn("chord-on=1,2&", output)

    def test_the_request_reaches_the_engine(self):
        """The flag is a spelling of the request, so both reach the same arrangement.

        Asserted against the library call rather than against a recorded tab, which is what
        makes it a claim about the *wiring*: a flag that parsed correctly and then arranged
        the default would pass a snapshot and fail this.
        """
        from arranger.options import Request

        path = self.score_path()
        output = self.run_cli(path, "--chord-notes", "1")
        self.assertEqual(self.code, 0)
        steps, _head, _notes = arrange_xml_head(
            path, request=Request(chord_notes="1")
        )
        self.assertIn(format_progression(steps), output)

    def test_the_banner_spelling_is_accepted_back_on_the_flag(self):
        """The run header's own request row can be pasted back onto the flags.

        The header is how a reader reproduces a run, so a spelling it prints that the flag
        refuses is a trap: the line a reader copies is the one that does not work. The
        `chord-on=` value is fed back to `--chord-on` and the header must repeat it -
        `every-beat` prints as the positions it resolves to, which is the same request in
        that metre, so the round trip is on the *value* rather than on the spelling.
        """
        output = self.run_cli(RAINY_DAY, "--bars", "1-3", "--chord-on", "1,2&")
        row = next(line for line in output.splitlines() if "request: " in line)
        fields = dict(
            field.split("=", 1)
            for field in row.split("request: ", 1)[1].split()
        )
        self.assertEqual(fields["chord-on"], "1,2&")
        again = self.run_cli(RAINY_DAY, "--bars", "1-3", "--chord-on", fields["chord-on"])
        self.assertEqual(self.code, 0, again)
        self.assertIn(f"chord-on={fields['chord-on']}", again)

    def test_no_melody_defaults_the_chord_to_every_beat(self):
        """`--no-melody` hands the tune away, and the chord defaults to every beat.

        The default is a **derivation**, not a rule: `chord-on=melody` names the written
        onsets, and this guitar has none - so the metre's own reading is used, and the
        canonical header prints the positions it actually resolved to rather than the
        word `every-beat`. Spellings are one request: omitting the flag and naming
        `melody` produce the same arrangement.
        """
        output = self.run_cli(RAINY_DAY, "--bars", "1-3", "--no-melody")
        self.assertEqual(self.code, 0)
        self.assertIn("melody=off", output)
        self.assertIn("chord-on=", output)
        self.assertNotIn("chord-on=melody", output)

        named = self.run_cli(
            RAINY_DAY, "--bars", "1-3", "--no-melody", "--chord-on", "melody"
        )
        self.assertEqual(self.code, 0)
        self.assertEqual(named, output, "two spellings of one request differed")

    def test_bass_on_is_what_writes_a_bass_line(self):
        """`--bass-on` is the only thing that adds a note below the tune.

        The default is no bass at all, which the header states and the tab shows:
        no step carries a `(bass: ...)` clause. Asking for one states the part and
        the note rules, and the line reaches the tab.
        """
        plain = self.run_cli(RAINY_DAY, "--bars", "1-3")
        self.assertIn("bass-on=none", plain)
        self.assertNotIn("(bass:", plain)

        walked = self.run_cli(
            RAINY_DAY, "--bars", "1-3", "--bass-on", "every-beat",
            "--bass-notes", "walk",
        )
        self.assertEqual(self.code, 0)
        self.assertIn("bass-notes=walk", walked)
        self.assertIn("(bass:", walked)

    def test_a_name_outside_a_vocabulary_is_a_usage_error_naming_it(self):
        """A name the request does not know is refused with the vocabulary it has.

        Three, because each names a different table: an arity outside
        `--chord-notes`, a position the metre does not have, and a bass name outside
        `--bass-notes`. The position is refused by the *metre* rather than by argparse,
        because a position list is only legal against a bar - which is why the message
        names the beats this one has.
        """
        import io
        from contextlib import redirect_stderr

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            self.run_cli(self.score_path(), "--chord-notes", "4")
        self.assertIn("full", errors.getvalue())

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            self.run_cli(self.score_path(), "--chord-on", "9")
        self.assertIn("felt beat 9", errors.getvalue())

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            self.run_cli(self.score_path(), "--bass-notes", "swing")
        self.assertIn("root-5th", errors.getvalue())
