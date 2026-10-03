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

`head_cli` builds its parser from a fixture score and never touches the database,
so none of this needs `wjazzd.db`; `corpus_cli`'s parser is read without arranging
anything, for the same reason.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

import arranger
from arranger.cli import (
    CORPUS_HELP,
    HEAD_HELP,
    CommonHelp,
    add_common_arguments,
    render_and_write,
)
from arranger.tuning import NECK_FRET_MAX, NECK_FRET_MIN
from wjazzd import SKELETON_STRATEGIES, SLOT_PICKS, corpus_cli


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
    """The two parsers agree on every flag they share, and differ only where they must.

    The invariant defect #4 was about is structural now - one `add_common_arguments`
    builds both - but a *structural* fix still needs an assertion, or the next edit
    reintroduces the copy and nothing says so.
    """

    def parsers(self):
        """Both CLIs' parsers as `_actions` mappings."""
        from headxml import head_cli

        corpus = _actions(_parser_of(corpus_cli))
        head = _actions(_parser_of(head_cli))
        return corpus, head, sorted((set(corpus) & set(head)) - {"help"})

    def test_the_two_parsers_agree_on_every_shared_flag(self):
        """Same spelling, type, choices, default, nargs and metavar - flag for flag.

        This is the assertion that makes the copy impossible to reintroduce: a
        flag added to one CLI and not the other cannot satisfy it, because the
        other simply has no such option.
        """
        corpus, head, shared = self.parsers()
        self.assertEqual(len(shared), 17, "the shared flag count moved")

        disagreeing = [
            f"{dest}: corpus={_semantics(corpus[dest])!r} head={_semantics(head[dest])!r}"
            for dest in shared
            if _semantics(corpus[dest]) != _semantics(head[dest])
        ]
        self.assertEqual(disagreeing, [], "a shared flag means two different things")

    def test_each_command_keeps_exactly_its_own_flags(self):
        """`corpus` alone names a transcription; `head` alone names a score.

        These are the flags that are *not* duplication, pinned so a shared flag
        cannot quietly absorb one: `--melid` only means something against the
        database, and `file` only against a file on disk.
        """
        corpus, head, _shared = self.parsers()
        self.assertEqual(
            sorted(set(corpus) - set(head)), ["lift", "list", "melid", "section"]
        )
        self.assertEqual(sorted(set(head) - set(corpus)), ["file", "part"])

    def test_the_help_text_is_not_one_shared_string(self):
        """Eleven flags are worded differently, and that difference is load-bearing.

        Measured before `arranger/cli.py` existed: of the seventeen shared flags,
        all seventeen agreed on every field of *meaning*, and eleven disagreed on
        their `--help` string - `--fret-min` and `--fret-max` had help in `corpus`
        and none at all in `head`. A refactor that "tidied" the prose would have
        silently changed what both commands print, with nothing to catch it.

        So the difference is asserted in both directions: each of the eleven is
        different, and the ones that are identical are named, so a flag drifting
        into `CommonHelp` fails here instead of being noticed by a user.

        **The identical set is now six, not five**, and the sixth is `bass`. It is
        named rather than absorbed into `CommonHelp` because the policy means the
        same thing against a transcription and against a score - it is an arrangement
        choice, and neither command reads a different metre for it. The count a
        sixth was supposed to be impossible to reach without stating its text twice;
        it is reachable by being written once *on purpose*, which is what this is.

        The counts are seventeen and eleven now, not seventeen and eleven:
        `--vertical` was removed along with the `format_progression` branch it
        selected, and it was one of the six whose help the commands spelled
        identically. Only that side of the split moved, which is why the eleven are
        named one by one below rather than counted - a flag leaving the *differing*
        set would change what both commands print, and one leaving the *identical*
        set only changes the number.
        """
        corpus, head, shared = self.parsers()
        differing = sorted(d for d in shared if corpus[d].help != head[d].help)
        self.assertEqual(
            differing,
            [
                "bars", "bars_per_line", "fret_max", "fret_min", "gp5", "html",
                "melody", "musicxml", "mutes", "tab", "texture",
            ],
        )
        self.assertEqual(
            sorted(set(shared) - set(differing)),
            ["bass", "fallback", "grips", "non_chord_tone", "pick", "skeleton"],
            "a flag gained or lost its differing help - remeasure before editing",
        )

    def test_the_help_tables_cover_exactly_the_differing_flags(self):
        """`CommonHelp` names the eleven, and nothing else.

        A field for a flag the two commands already agree on would be a second
        place to state the same prose - the duplication this module exists to
        remove - so the table and the measurement are asserted against each other.
        """
        from dataclasses import fields

        declared = {field.name for field in fields(CommonHelp)}
        self.assertEqual(
            declared,
            {
                "bars", "bars_per_line", "fret_max", "fret_min", "gp5", "html",
                "melody", "musicxml", "mutes", "tab", "texture",
            },
        )
        corpus, head, shared = self.parsers()
        self.assertEqual(
            declared,
            {d for d in shared if corpus[d].help != head[d].help},
            "CommonHelp and the measured difference disagree",
        )

    def test_head_states_the_fret_window_too(self):
        """The one omission, filled deliberately rather than quietly preserved.

        `corpus` told the user what its fret window defaulted to and `head` said
        nothing. That read like an oversight, so it was pinned as a *deliberate*
        difference (`Optional[str]` in `CommonHelp` exists for exactly it), which
        turned "tidying it up" into a change someone had to look at.

        Someone looked, and filled it: a flag the reader can pass but cannot
        understand is worse than either state. The gap is closed here.

        So this asserts the *new* deliberate difference rather than deleting the
        test. Both commands state the window now, so what must be pinned is the
        remaining asymmetry - the two spellings are **not** the same text, because
        `head`'s has to say what `corpus`'s cannot (that the window is an aim
        rather than a filter). If someone copies `CORPUS_HELP`'s wording across to
        make them "consistent", the two move into the identical set and
        `test_the_help_text_is_not_one_shared_string` fails - which is the point.
        The warning survives the fix: still remeasure before editing.
        """
        for help_text in (CORPUS_HELP, HEAD_HELP):
            self.assertIsNotNone(help_text.fret_min)
            self.assertIsNotNone(help_text.fret_max)
        self.assertNotEqual(CORPUS_HELP.fret_min, HEAD_HELP.fret_min)
        self.assertNotEqual(CORPUS_HELP.fret_max, HEAD_HELP.fret_max)
        # Both state the window, and both say it is an aim rather than a filter -
        # the one thing a reader cannot infer from the flag name.
        for help_text in (CORPUS_HELP, HEAD_HELP):
            self.assertIn(str(NECK_FRET_MIN), str(help_text.fret_min))
            self.assertIn(str(NECK_FRET_MAX), str(help_text.fret_max))
        self.assertIn("filter", str(HEAD_HELP.fret_min))

    def test_vertical_is_no_longer_a_shared_flag(self):
        """`--vertical` was removed, and the removal is asserted rather than assumed.

        It selected a six-line block per chord from `format_progression`, which is
        a branch that no longer exists. A whole-progression staff is what a player
        reads, and `--tab staff` renders one. The flag used to be one of the six
        whose help both commands spelled identically, so leaving it in place would
        have been a flag reaching a parameter that had gone - a `TypeError` at the
        first run rather than a parser error, which is the worse of the two.

        So the assertion is the opposite of the one it replaces: neither parser
        offers it, which is what "both commands agree" now means for a flag neither
        of them has.
        """
        corpus, head, shared = self.parsers()
        for name, flags in (("corpus", corpus), ("head", head)):
            self.assertNotIn("--vertical", flags, name)
        self.assertNotIn("vertical", shared)

class TestTheSharedDispatch(unittest.TestCase):
    """`render_and_write` is one function, and it serves both commands.

    Read through the function rather than through either CLI: `head` needs a
    committed score and `corpus` needs the 42 MB database, and neither is what
    this behaviour *is*. The two end-to-end CLIs are still exercised where they
    live - in `tests/test_headxml.py` and `tests/test_wjazzd.py` - so nothing here
    replaces them; this only states the shared half where the shared half is.
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
        add_common_arguments(
            parser,
            HEAD_HELP,
            skeleton_strategies=SKELETON_STRATEGIES,
            slot_picks=SLOT_PICKS,
        )
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
        """`corpus` passes no metre, because a Weimar transcription is 4/4.

        So `None` has to become the writers' own 4 rather than being forwarded as
        a null, which `format_tab_html` would take as "lay out against no grid" -
        so this is a crash that only a score command could have triggered.
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
        """`corpus` passes no key, and a Weimar transcription is usually C.

        So `None` has to become 0 rather than being forwarded as a null, which is
        what lets the two commands share one dispatch - the same bargain the metre
        makes two paragraphs above.
        """
        calls = self.captured_calls()
        for name in ("musicxml", "gp5"):
            self.assertEqual(calls[name]["fifths"], 0, name)
            self.assertEqual(calls[name]["mode"], "", name)

    def test_the_subtitle_reaches_the_renderers_that_have_one(self):
        """`corpus` names performer and key; `head` has neither.

        The subtitle is metadata on all three file writers and a heading on the
        HTML, so it is one of the few places the two commands' *output* genuinely
        differs - which is why it is a parameter here rather than something the
        dispatch infers.
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


class TestTheVocabularyIsPassedIn(unittest.TestCase):
    """The reduction vocabularies are arguments, not imports.

    `SKELETON_STRATEGIES` and `SLOT_PICKS` belong to `wjazzd`, a top-level module
    outside the package's DAG. An import here would reach out of the package and
    the layering would stop meaning anything - and it would make `import
    arranger.cli` depend on the database module, which is the laziness
    `docs/corpus.md` goes to some trouble to preserve.
    """

    def test_the_cli_module_does_not_import_wjazzd(self):
        """Read from the source, so it holds whatever the import style becomes."""
        import ast

        tree = ast.parse((Path(arranger.__file__).parent / "cli.py").read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("wjazzd", imported)

    def test_the_vocabulary_is_the_one_the_reduction_uses(self):
        """The choices offered are the reduction's own, not a copy that can drift."""
        self.assertEqual(
            SKELETON_STRATEGIES, ("chords", "beats", "eighths", "sixteenths", "notes")
        )
        self.assertEqual(SLOT_PICKS, ("first", "longest"))


if __name__ == "__main__":
    unittest.main()
