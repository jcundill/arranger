"""The two front ends take the same flags, and the tests say so.

Phase 7 removed the last of the six defects in `implementation_plan.md`: the two
CLIs hand-copied one argparse block, so a flag added to one was silently missing
from the other. Those blocks now live once in `arranger.cli`.

**That is a structural fix with no test behind it**, which is the failure mode the
whole refactor is about: a copy can be pasted, but so can a function that has been
edited in one place and left alone in another. So these tests assert the property
directly rather than trusting the refactor:

- the two parsers offer an **identical set** of shared flags, and every one of them
  agrees on `type`, `choices`, `default`, `nargs` and `metavar`;
- each command keeps exactly the flags that are genuinely its own;
- the `--help` text is not a single shared string. It was measured to differ on 11
  of the 17 flags before this module existed, and nothing asserted any of it, so
  a "simplification" that unified the prose would have silently changed what both
  commands print. `CommonHelp` exists to keep the difference visible.

`--vertical` was removed after that measurement, taking the shared count to 16; it
was one of the six whose help both commands agreed on, so the eleven are
unchanged. The counts are asserted in both directions below.

**The corpus half is gone, and what replaced it is stated where it was removed.**
This file existed to hold two parsers to each other: `corpus` and `head` shared an
argparse block, and the assertions were that they agreed on every flag they shared
and differed only where they had to. With the database removed there is one parser,
so those assertions had nothing to compare - and rather than delete the class, it
now asserts the two properties that survived and are still capable of breaking:

- **the flag count**, which was a tripwire for "a flag was added to one command and
  not the other" and is now a tripwire for "a flag appeared or vanished";
- **`CommonHelp` is wired to the parser**, which was "the table and the measurement
  agree" and is now "every declared field reaches a flag, and reaches it with that
  text". That is the check that catches a field added to the dataclass and never
  passed to `add_argument`.

The `corpus` command's own vocabulary assertions - that `--skeleton`'s choices were
`SKELETON_STRATEGIES` - were the other half, and they went with the flags.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
import unittest
from typing import Dict, List

import arranger
from arranger.cli import (
    HEAD_HELP,
    CommonHelp,
    add_common_arguments,
    render_and_write,
)
from arranger.tuning import NECK_FRET_MAX, NECK_FRET_MIN


def _parser_of(run: object) -> argparse.ArgumentParser:
    """The `ArgumentParser` a CLI builds, captured without doing its work.

    `--help` exits, so the parser is intercepted at `parse_args` instead: the
    argument is rejected for its own sake and the object it was built on comes
    back. Reading the private `_actions` is the only way to compare two parsers
    field by field, and it is stable - argparse exposes no public introspection.
    """
    captured: List[argparse.ArgumentParser] = []
    original = argparse.ArgumentParser.parse_args

    def spy(self: argparse.ArgumentParser, *args: object, **kwargs: object):
        captured.append(self)
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    argparse.ArgumentParser.parse_args = spy  # type: ignore[method-assign]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                with contextlib.suppress(SystemExit):
                    run(["--help"])  # type: ignore[operator]
    finally:
        argparse.ArgumentParser.parse_args = original  # type: ignore[method-assign]
    if not captured:
        raise AssertionError("the CLI never built a parser")
    return captured[0]


def _actions(parser: argparse.ArgumentParser) -> Dict[str, argparse.Action]:
    """The parser's options keyed by `dest`, which is `None` for `-h`."""
    return {
        action.dest: action
        for action in parser._actions  # noqa: SLF001 - argparse has no public API
        if action.dest is not None and action.dest != "help"
    }


def _semantics(action: argparse.Action) -> tuple:
    """Everything about an option that is *meaning*, excluding its help prose."""
    return (
        action.type,
        action.choices,
        action.default,
        action.nargs,
        action.metavar,
        action.option_strings,
    )

class TestTheFlagsAreOneDefinition(unittest.TestCase):
    """The parser is one definition, and this is what still needs asserting.

    The invariant defect #4 was about is structural now - one `add_common_arguments`
    builds it - but a *structural* fix still needs an assertion, or the next edit
    reintroduces the copy and nothing says so.

    **This class compared two parsers and now checks one, which is not the same
    test.** `corpus` and `head` each had their own; the assertions were that they
    agreed on every shared flag and differed only where they had to. That is not a
    weaker statement about a single parser - it is a *different* one, because "the
    two agree" and "this one is complete" fail in different ways. So the surviving
    assertions are the two halves of the old subject that still have teeth, and the
    rest of the class is a record of what was there and why it went.
    """

    def parser(self):
        """`head`'s parser as an `_actions` mapping."""
        from headxml import head_cli

        return _actions(_parser_of(head_cli))

    def test_the_flag_count_is_what_it_was(self):
        """Counted, not derived, deliberately.

        This was "the two parsers agree on every shared flag", and it was a
        tripwire for *a flag added to one command and not the other* - a number that
        recomputed itself from the parsers would have noticed nothing. With one
        parser there is nothing to disagree with, so what the count is for changes:
        it is now a tripwire for a flag appearing or vanishing unnoticed.

        **20, and it was 20 before this change too**, which is the interesting part.
        `--skeleton` and `--pick` were `add_common_arguments` parameters, gated on a
        vocabulary the one real caller never passed - so `head` never offered them
        and removing the gate removed no flag from this parser. The count is
        unchanged because what was removed was a branch nothing took, not an option
        anyone could type. See `test_the_reduction_flags_are_gone`.

        `_actions` already drops `help`, so this is the length of the mapping and
        not the parser's action count.
        """
        flags = self.parser()
        self.assertEqual(len(flags), 20, "the flag count moved; remeasure")

    def test_every_flag_is_one_somewhere(self):
        """No flag is registered without a decision behind it.

        **This is the assertion that replaced `test_each_command_keeps_exactly_its_own_flags`.**
        That test held that `corpus` alone named a transcription and `head` alone a
        file - `--melid` only meant something against the database, `file` only
        against a file on disk. With one command the surviving claim is the weaker
        but still real one that *every* flag reaches the parser: `file` and `part`
        are `head`'s own, and they are named rather than derived.
        """
        self.assertEqual(
            sorted(self.parser()),
            [
                "bars", "bars_per_line", "bass", "fallback", "file", "fret_max",
                "fret_min", "gp5", "grid", "grips", "harmony", "html",
                "melody", "musicxml", "mutes", "non_chord_tone", "part", "tab",
                "texture", "voices",
            ],
        )

    def test_the_help_text_is_not_one_shared_string(self):
        """Eleven flags carry written prose, and eight carry none from the table.

        Measured before `arranger/cli.py` existed: of the seventeen shared flags,
        all seventeen agreed on every field of *meaning*, and eleven disagreed on
        their `--help` string - `--fret-min` and `--fret-max` had help in `corpus`
        and none at all in `head`. A refactor that "tidied" the prose would have
        silently changed what both commands print, with nothing to catch it.

        With one parser there is no "differing" set any more, so this asserts the
        partition that produced it instead: **eleven flags get their text from
        `CommonHelp` and eight get it written inline**, and both halves are named.
        That is the property the split was built on - a flag whose help is the same
        wherever it is read is written once at the `add_argument` call, and one
        whose wording carries an arrangement of its own lives in the table.

        The eight: `bass`, `fallback`, `grid`, `grips`, `harmony`, `non_chord_tone`
        and `voices` are arranging choices that mean the same thing against a
        transcription and against a score, so they print one help string rather
        than two - that was the original reason each is *not* in `CommonHelp`, and
        the reason survives the corpus. `file` and `part` are prose argparse writes
        from the flag name.
        """
        from dataclasses import fields

        flags = self.parser()
        declared = {field.name for field in fields(CommonHelp)}
        self.assertEqual(
            sorted(flags),
            [
                "bars", "bars_per_line", "bass", "fallback", "file", "fret_max",
                "fret_min", "gp5", "grid", "grips", "harmony", "html",
                "melody", "musicxml", "mutes", "non_chord_tone", "part", "tab",
                "texture", "voices",
            ],
        )
        self.assertEqual(
            declared,
            {
                "bars", "bars_per_line", "fret_max", "fret_min", "gp5", "html",
                "melody", "musicxml", "mutes", "tab", "texture",
            },
        )
        # Every declared field reaches its flag, and reaches it with that text.
        # This is the half of the old "table and measurement agree" test that
        # still has teeth: it catches a field added to the dataclass and never
        # passed to `add_argument`, which nothing else here would notice.
        for name in sorted(declared):
            with self.subTest(flag=name):
                self.assertEqual(flags[name].help, getattr(HEAD_HELP, name))
        # And nothing claims to come from the table without declaring it.
        self.assertEqual(
            sorted(flags),
            sorted(declared | {"bass", "fallback", "file", "grid", "grips",
                               "harmony", "non_chord_tone", "part", "voices"}),
        )

    def test_the_reduction_flags_are_gone(self):
        """`--skeleton` and `--pick` went with the database, and that is asserted.

        Both were a *reduction* - they decided which melody notes were dropped -
        and the MusicXML path does not reduce: every written note of a score sounds,
        because a note of the tune going missing silently is worse than a busy tab.
        The corpus command kept both while it existed, which is why they were
        *parameters* of `add_common_arguments` rather than flags: their vocabularies
        belonged to `wjazzd`, and `head` never passed them.

        So these two flags were unreachable before this change - gated on a
        vocabulary the one caller had no way to supply. Removing the gate is what
        makes them removable, and the assertion is that they are not offered: a flag
        reaching a parameter that had gone would be a `TypeError` at first run rather
        than a parser error, which is the worse of the two.
        """
        flags = self.parser()
        for name in ("--skeleton", "--pick", "--vertical", "--melid", "--list",
                     "--lift", "--section"):
            with self.subTest(flag=name):
                self.assertNotIn(name, flags)

    def test_head_states_the_fret_window(self):
        """The one omission, filled deliberately rather than quietly preserved.

        `corpus` told the user what its fret window defaulted to and `head` said
        nothing. That read like an oversight, so it was pinned as a *deliberate*
        difference (`Optional[str]` in `CommonHelp` exists for exactly it), which
        turned "tidying it up" into a change someone had to look at.

        Someone looked, and filled it: a flag the reader can pass but cannot
        understand is worse than either state. The gap is closed here.

        **What this asserts now that there is one command.** The old version pinned
        that the two spellings differed, so that copying one across to "tidy" them
        would fail. With the other half deleted there is nothing to differ *from* -
        so the surviving claim is the one that was always the point: the window is
        an aim and not a filter, and only the text can say so.
        """
        self.assertIsNotNone(HEAD_HELP.fret_min)
        self.assertIsNotNone(HEAD_HELP.fret_max)
        self.assertIn(str(NECK_FRET_MIN), str(HEAD_HELP.fret_min))
        self.assertIn(str(NECK_FRET_MAX), str(HEAD_HELP.fret_max))
        # The one thing a reader cannot infer from the flag name: the window is a
        # preference and never a filter, so a step with no voicing inside it is
        # still played rather than dropped.
        self.assertIn("filter", str(HEAD_HELP.fret_min))
        # And the text that states it is the one the parser prints, so the promise
        # is a promise about what `arranger head --help` says.
        flags = self.parser()
        self.assertEqual(flags["fret_min"].help, HEAD_HELP.fret_min)


class TestTheSharedDispatch(unittest.TestCase):
    """`render_and_write` is one function, and what `head` hands it.

    Read through the function rather than through the CLI: `head` needs a
    committed score, and that is not what this behaviour *is*. The end-to-end CLI
    is still exercised where it lives - in `tests/test_headxml.py` - so nothing here
    replaces it; this only states the dispatch itself, which is reachable without
    a file on disk.

    **These were the "shared" half of a pair of commands**, and every test here
    existed to hold the two callers to one definition: a metre passed by one and
    defaulted by the other had to land in the same place. That comparison is gone,
    and what remains is the weaker and still real claim that the defaults are the
    writers' own - which is what the tests assert.
    """

    def steps(self, count: int = 2):
        from tests.support import make_step

        return [
            make_step([-1, -1, 10, 12, 12, 12], chord="Dm7", melody="A5")
            for _ in range(count)
        ]

    def args(self, **overrides):
        """A parsed namespace, as `render_and_write` is handed one by a CLI."""
        parser = argparse.ArgumentParser(prog="test")
        add_common_arguments(parser, HEAD_HELP)
        namespace = parser.parse_args([])
        for name, value in overrides.items():
            setattr(namespace, name, value)
        return namespace

    def test_the_default_run_prints_the_tab_and_writes_nothing(self):
        """No flag asked for a file, so none is written - and the exit code is 0."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = render_and_write(self.args(), self.steps(), title="T")
        printed = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Dm7", printed)
        self.assertNotIn("wrote", printed)

    def test_a_missing_extra_is_reported_after_the_tab_is_printed(self):
        """A run that asked for a GP5 file keeps the tab it had already produced.

        This is why the dispatch catches `ImportError` and returns 1 rather than
        letting it escape: losing the arrangement to a missing *optional*
        dependency would be worse than losing the file.
        """
        import tabgp

        def refuse(*args, **kwargs):
            raise ImportError(
                "Guitar Pro export needs PyGuitarPro, which is an optional extra. "
"Install it with: pip install 'jazz-arranger[gp]'"
            )

        original = tabgp.write_gp5
        tabgp.write_gp5 = refuse
        self.addCleanup(setattr, tabgp, "write_gp5", original)

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = render_and_write(
                self.args(gp5="unused.gp5"), self.steps(), title="T"
            )
        printed = buffer.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("Dm7", printed)
        self.assertIn("jazz-arranger[gp]", printed)

    def captured_calls(self, **metre):
        """What the dispatch passes each renderer, by standing in for all three.

        The metre is asserted as *forwarded arguments* rather than as rendered
        output. That was the first attempt at this test and it failed for an
        instructive reason: `format_tab_html` does not put the metre on the page
        at all, so there is nothing in the HTML to assert against - the only place
        the denominator becomes visible is the MusicXML and GP5 writers, each of
        which needs an optional extra to run at all.

        So the property under test is the one the dispatch actually owns: it hands
        the notated metre on rather than dropping it, and it hands the writers'
        own 4 when it has none to hand. That is what makes the two commands
        equivalent, and it is checkable without a fixture or an extra.
        """
        import tabgp
        import tabstaff
        import tabxml

        calls: Dict[str, Dict[str, object]] = {}

        def recorder(name):
            def record(steps, path, **kwargs):
                calls[name] = kwargs
                return str(path)

            return record

        def staff(*args, **kwargs):
            calls["staff"] = kwargs
            return "staff"

        originals = {
            (tabstaff, "format_tab_staff"): staff,
            (tabstaff, "write_tab_html"): recorder("html"),
            (tabxml, "write_musicxml"): recorder("musicxml"),
            (tabgp, "write_gp5"): recorder("gp5"),
        }
        for (module, name), replacement in originals.items():
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, replacement)

        namespace = self.args(
            tab="staff",
            html="out.html",
            musicxml="out.musicxml",
            gp5="out.gp5",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            code = render_and_write(namespace, self.steps(), title="T", **metre)
        self.assertEqual(code, 0)
        return calls

    def test_the_notated_metre_reaches_every_renderer(self):
        """2/2 in means 2/2 out - the reason `head` passes a metre at all.

        A count without a denominator is not a metre, and the writers' own default
        is 4/4, so a dispatch that dropped this would lay a cut-time head out
        against the wrong grid and display 2/2 as common time.

        `head`'s own `test_the_written_files_carry_the_notated_metre` drives the
        CLI over a real score and would catch it; this states the same property
        with no fixture and no optional extra, which is the point of putting the
        shared half in a shared place.
        """
        calls = self.captured_calls(beats_per_bar=2, beat_type=2)
        for name in ("staff", "html", "musicxml", "gp5"):
            self.assertEqual(calls[name]["beats_per_bar"], 2, name)
        # `beat_type` used to reach only the two score writers, and this test asserted
        # the staff and the HTML did *not* take it - on the stated grounds that
        # "neither the ASCII staff nor the HTML page writes a time signature at all".
        # Both now do, from `show_timing`: a staff that shows where a chord falls but
        # not how long it sounds, and prints no metre, is half a score. So the
        # assertion is inverted rather than dropped: all four renderers must now
        # carry the notated metre, or a 2/2 head is laid out on the wrong grid and
        # displayed as common time.
        for name in ("staff", "html", "musicxml", "gp5"):
            self.assertEqual(calls[name]["beat_type"], 2, name)

    def test_the_metre_defaults_to_the_writers_own_four(self):
        """`None` becomes the writers' own 4 rather than being forwarded as a null.

        `format_tab_html` takes a null `beats_per_bar` as "lay out against no grid",
        so forwarding it is a crash rather than a default. **This was written when
        `corpus` passed no metre and `head` did** - a Weimar transcription is 4/4 -
        and the default existed so the two callers could share one dispatch. With
        `head` the only caller it always has a score's own metre, so the branch is
        unreachable from the CLI. It stays because every writer has that default
        anyway and a caller with no metre should land on it rather than raise.
        """
        calls = self.captured_calls()
        for name in ("staff", "html", "musicxml", "gp5"):
            self.assertEqual(calls[name]["beats_per_bar"], 4, name)
            self.assertEqual(calls[name]["beat_type"], 4, name)

    def test_the_key_reaches_the_two_score_writers(self):
        """The key a head is in has to reach the files that can state it.

        A dispatch that dropped it left every score in C major, and the score
        writers are the only two that write pitches: the staff and the HTML page
        show fret numbers, so a signature has nothing there to apply to. The
        absence is asserted rather than left implicit, because that asymmetry is
        the easy thing to get wrong in either direction.
        """
        calls = self.captured_calls(fifths=-3, mode="major")
        for name in ("musicxml", "gp5"):
            self.assertEqual(calls[name]["fifths"], -3, name)
            self.assertEqual(calls[name]["mode"], "major", name)
        for name in ("staff", "html"):
            self.assertNotIn("fifths", calls[name], name)

    def test_the_key_defaults_to_the_writers_own_zero(self):
        """`None` becomes 0 rather than being forwarded as a null.

        The same bargain the metre makes above, and for the same original reason:
        a Weimar transcription is usually C, so `corpus` passed no key and `head`
        passed the score's. It was also the right default on its own terms - 0 is
        C major, which is what a MusicXML document with no `<key>` already means,
        so a caller with no signature is asking for C rather than for "unknown".
        """
        calls = self.captured_calls()
        for name in ("musicxml", "gp5"):
            self.assertEqual(calls[name]["fifths"], 0, name)
            self.assertEqual(calls[name]["mode"], "", name)

    def test_the_subtitle_reaches_the_renderers_that_have_one(self):
        """The subtitle is metadata on all three file writers and a heading on the
        HTML.

        It was one of the few places the two commands' *output* genuinely differed
        - `corpus` named performer and key, `head` has neither - which is why it is
        a parameter here rather than something the dispatch infers. `head` passes
        the score's own composer when there is one, and `""` otherwise, which is
        also the writers' own default.
        """
        import tabstaff

        calls: Dict[str, object] = {}

        def record(steps, path, **kwargs):
            calls.update(kwargs)
            return str(path)

        original = tabstaff.write_tab_html
        self.addCleanup(setattr, tabstaff, "write_tab_html", original)
        tabstaff.write_tab_html = record

        handle, path = tempfile.mkstemp(suffix=".html")
        os.close(handle)
        self.addCleanup(os.unlink, path)
        with contextlib.redirect_stdout(io.StringIO()):
            render_and_write(
                self.args(html=path),
                self.steps(),
                title="Blue Train",
                subtitle="John Coltrane - Bb",
            )
        self.assertEqual(calls["subtitle"], "John Coltrane - Bb")


class TestAMainThatKnowsWhatItDoesNotHave(unittest.TestCase):
    """An unrecognised subcommand is a usage error, not the demo.

    **This is a trap the removal of `corpus` opened, and it was not new.** With two
    subcommands, an unknown first argument fell through to the built-in
    demonstration and exited 0 - so `arranger corpus --melid 218` printed three
    arrangements and reported success, to a user who had asked for a head and got
    nothing resembling one. That was survivable while the fallthrough was merely
    sloppy. It is not survivable now: `corpus` *was* a command, so the exact
    invocation in the README before this change now silently produces the demo, and
    the exit code says it worked.

    The test is on the shape of the argument, not on the word: `argv[1]` being a
    bare alphabetic word is a subcommand or a typo for one, and a leading option is
    not. `arranger --grips shell` must still reach the demo.
    """

    def run_main(self, argv):
        """`main()` under a given `sys.argv`, with its streams captured."""
        buffer = io.StringIO()
        errors = io.StringIO()
        saved = sys.argv
        sys.argv = ["arranger"] + argv
        code = 0
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(errors):
                try:
                    arranger.main()
                except SystemExit as exit_code:
                    code = exit_code.code if exit_code.code is not None else 0
        finally:
            sys.argv = saved
        return code, buffer.getvalue(), errors.getvalue()

    def test_the_removed_corpus_command_is_reported_not_run(self):
        """The README's own example from before the removal, now an error."""
        code, out, err = self.run_main(["corpus", "--melid", "218"])
        self.assertEqual(code, 2, "a removed command must not exit 0")
        self.assertIn("Unknown command", err)
        self.assertIn("'head'", err)
        # The trap this closes: the demo is *silent* on stdout, so a user who only
        # looked at the arrangements would see nothing at all.
        self.assertEqual(out, "", "the demo must not run behind a usage error")

    def test_no_arguments_still_prints_the_demo(self):
        code, out, err = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("ARRANGEMENT", out)
        self.assertEqual(err, "")

    def test_a_leading_option_is_not_mistaken_for_a_subcommand(self):
        """`--grips shell` is a demo argument, and saying otherwise would break it."""
        code, out, _err = self.run_main(["--grips", "shell"])
        self.assertEqual(code, 0)
        self.assertIn("ARRANGEMENT", out)


if __name__ == "__main__":
    unittest.main()
