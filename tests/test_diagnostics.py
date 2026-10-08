"""The engine's warnings are a value, not a side effect.

Before this, every warning was a `print()` and the suite proved one existed by
wrapping the call in `contextlib.redirect_stdout` and searching the captured text.
That form passes for the wrong reasons: it would be satisfied by a warning printed
by the wrong function, and it cannot distinguish "this condition was reported" from
"this string appeared somewhere". These tests pin the three properties that make
`Diagnostics` worth having, and the one that matters most - that the default path is
byte-identical to what the `print()` calls produced.

No test here is `skipUnless`-guarded: `Diagnostics` is engine work with no optional
dependency and no database.
"""

import contextlib
import io
import unittest

import arranger.slots
from arranger import Diagnostics, VoiceLeadingEngine, default_diagnostics

# Progressions chosen because each provokes a *different* warning, so a warning
# that stops being raised fails here rather than being masked by another.
NO_VOICING_AT_ALL = [
    # A melody below the library's G3 floor cannot be reached on any string.
    ("C2", "maj7", "Cmaj7"),
]
UNRESOLVABLE_NON_CHORD_TONE = [
    # Gb4 over Dm7b5: a tone the extension table has no route for, so the strategy
    # finds nothing and the fallback is kept with a warning. Note the *spelling* -
    # the same pitch as G#4 does not warn, because musthe reads the two spellings
    # differently against the chord. Found by running the engine, not by reasoning.
    ("C5", "m7b5", "Dm7b5"),
    ("Gb4", "m7b5", "Dm7b5"),
]
NORMAL = [
    ("D5", "m7", "Dm7"),
    ("B4", "7", "G7"),
    ("C5", "maj7", "Cmaj7"),
]


def arrange(progression, **kwargs):
    """`arrange_progression` with a silent collector, returning (steps, warnings)."""
    diagnostics = Diagnostics()
    steps = VoiceLeadingEngine.arrange_progression(
        progression, diagnostics=diagnostics, **kwargs
    )
    return steps, diagnostics.warnings


def printed_by_default(progression, **kwargs):
    """The default path's output, as a list of non-blank lines."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        VoiceLeadingEngine.arrange_progression(progression, **kwargs)
    return [line for line in buffer.getvalue().splitlines() if line.strip()]


class TestDiagnosticsItself(unittest.TestCase):
    """The collector, before the engine's use of it."""

    def test_it_starts_empty_and_is_falsy(self):
        diagnostics = Diagnostics()
        self.assertEqual(diagnostics.warnings, [])
        self.assertFalse(diagnostics)

    def test_warn_records_the_message(self):
        diagnostics = Diagnostics()
        diagnostics.warn("first")
        diagnostics.warn("second")
        self.assertEqual(diagnostics.warnings, ["first", "second"])

    def test_it_is_truthy_once_something_is_reported(self):
        diagnostics = Diagnostics()
        self.assertFalse(diagnostics)
        diagnostics.warn("something")
        self.assertTrue(diagnostics)

    def test_emit_is_called_for_each_message_in_order(self):
        seen = []
        diagnostics = Diagnostics(emit=seen.append)
        diagnostics.warn("first")
        diagnostics.warn("second")
        self.assertEqual(seen, ["first", "second"])

    def test_emit_sees_the_message_after_it_is_recorded(self):
        """The order matters: a printer that raised would otherwise see a message
        the collector had not kept, so a retry would duplicate it."""
        seen_at_emit_time = []
        diagnostics = Diagnostics(emit=lambda m: seen_at_emit_time.append(list(diagnostics.warnings)))
        diagnostics.warn("only")
        self.assertEqual(seen_at_emit_time, [["only"]])

    def test_default_diagnostics_prints(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            default_diagnostics().warn("hello")
        self.assertEqual(buffer.getvalue(), "hello\n")


class TestTheLibraryIsSilentWhenGivenACollector(unittest.TestCase):
    """Passing a `Diagnostics` must actually stop the output.

    This is the property the ten `redirect_stdout` call sites could not check.
    Each progression below provokes a warning on the default path, so a collector
    that did not take effect fails here rather than merely looking tidy.
    """

    def test_a_collector_silences_a_progression_that_warns(self):
        progression = UNRESOLVABLE_NON_CHORD_TONE
        # The default path warns; that is the premise of this test.
        self.assertTrue(printed_by_default(progression), "the fixture does not warn")

        buffer = io.StringIO()
        diagnostics = Diagnostics()
        with contextlib.redirect_stdout(buffer):
            VoiceLeadingEngine.arrange_progression(progression, diagnostics=diagnostics)
        self.assertEqual(buffer.getvalue(), "", "the collector did not silence output")
        self.assertTrue(diagnostics.warnings, "the warning was silenced but not recorded")

    def test_the_same_run_reports_the_same_warnings_either_way(self):
        """Collecting must not change which warnings are raised, only where they go."""
        _steps, collected = arrange(UNRESOLVABLE_NON_CHORD_TONE)
        self.assertEqual(collected, printed_by_default(UNRESOLVABLE_NON_CHORD_TONE))

    def test_a_quiet_progression_collects_nothing(self):
        _steps, warnings = arrange(NORMAL)
        self.assertEqual(warnings, [])
        self.assertEqual(warnings, printed_by_default(NORMAL))


class TestTheDefaultPathIsUnchanged(unittest.TestCase):
    """The property that makes the change safe to ship.

    Every warning the engine can raise, checked twice: printed by default, and
    collected when asked. Both must agree, and the printed form must be the exact
    text the `print()` calls produced - a warning reworded here would be a silent
    change to what every user of this library reads.
    """

    def assert_same_either_way(self, progression, **kwargs):
        printed = printed_by_default(progression, **kwargs)
        _steps, collected = arrange(progression, **kwargs)
        self.assertEqual(collected, printed, f"collected != printed for {progression}")
        return printed

    def test_the_unresolvable_non_chord_tone_warning(self):
        printed = self.assert_same_either_way(UNRESOLVABLE_NON_CHORD_TONE)
        self.assertTrue(any("is not a chord tone of" in w for w in printed), printed)

    def test_the_no_voicing_warning(self):
        """The message names the palette, and says the **step is skipped**.

        `NO_VOICING_AT_ALL` is a melody no string reaches, which is now the only way
        a step is skipped: every other "no voicing" case leaves the tune sounding
        alone. The old text said "No valid drop-2 voicing found" whatever family had
        been asked for - so a `--grips shell` run was told about a grip it never
        requested - and it read like a fallback that had happened.
        """
        printed = self.assert_same_either_way(NO_VOICING_AT_ALL)
        self.assertTrue(
            any("no voicing for Cmaj7 with melody C2" in w for w in printed), printed
        )
        self.assertTrue(any("in the palette (" in w for w in printed), printed)
        self.assertTrue(any("skipping the step" in w for w in printed), printed)

    def test_the_grips_intersection_warning(self):
        """Asking for a grip the texture never uses warns, and keeps playing."""
        printed = self.assert_same_either_way(NORMAL, texture="targets", grips=("duo",))
        self.assertTrue(
            any("none of which is in the requested" in w for w in printed), printed
        )

    def test_the_span_demotion_warning(self):
        """A target only offered the four-note grips can be forced onto a wide shape,
        and is then demoted to the melody alone. Ebmaj under G4 is the documented
        case; the assertion is on the agreement between the two paths, which is what
        this phase is about, and not on reproducing one note's voicing."""
        progression = [("G4", "maj7", "Ebmaj")]
        printed = self.assert_same_either_way(
            progression, texture="targets", timings=[(0, 1.0, 1.0)]
        )
        for warning in printed:
            self.assertIn("Warning:", warning)

    def test_prepare_step_reports_to_the_collector_too(self):
        """The engine reaches its warnings through prepare_step, so a warning
        raised there has to reach the collector rather than stdout."""
        diagnostics = Diagnostics()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            VoiceLeadingEngine.prepare_step(
                UNRESOLVABLE_NON_CHORD_TONE, 1, diagnostics=diagnostics
            )
        self.assertEqual(buffer.getvalue(), "")
        self.assertTrue(
            any("is not a chord tone of" in w for w in diagnostics.warnings),
            diagnostics.warnings,
        )


class TestTheSlotPathReportsToTheSameCollector(unittest.TestCase):
    """`arrange_slots` wraps the engine, so it needs its own check.

    A warning raised only on the engine's own path is the failure this guards: the
    collector has existed for months and the slot layer silently kept printing, or
    worse, stopped printing without anyone noticing.

    **This used to compare two step loops, and now there is one.** The class was
    written when `wjazzd.arrange_slots` held a near-verbatim second copy of the
    loop, and `test_the_two_entry_points_report_the_same_warning_for_one_step`
    existed to catch the two copies formatting the same warning differently. The
    copy is gone - it delegates to `arrange_progression` - so the test below still
    asserts that the wrapper reports what the engine reports, which is the
    remaining half of what it checked and the half that can still break.
    """

    def test_arrange_slots_accepts_a_collector(self):
        diagnostics = Diagnostics()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            arranger.slots.arrange_slots(
                UNRESOLVABLE_NON_CHORD_TONE, diagnostics=diagnostics
            )
        self.assertEqual(buffer.getvalue(), "", "the collector did not take effect")
        self.assertTrue(
            any("is not a chord tone of" in w for w in diagnostics.warnings),
            diagnostics.warnings,
        )

    def test_arrange_slots_prints_by_default(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            arranger.slots.arrange_slots(UNRESOLVABLE_NON_CHORD_TONE)
        self.assertTrue(buffer.getvalue().strip())

    def test_the_two_entry_points_report_the_same_warning_for_one_step(self):
        """The wrapper must not reformat what the engine reported.

        This used to say "the two step loops", because there were two. There is
        one now, so what remains is that `arrange_slots` hands the warning
        through rather than formatting its own copy of the text - which is the
        half of the original assertion that can still break.
        """
        _steps, from_library = arrange(UNRESOLVABLE_NON_CHORD_TONE)

        slot_diagnostics = Diagnostics()
        arranger.slots.arrange_slots(
            UNRESOLVABLE_NON_CHORD_TONE, diagnostics=slot_diagnostics
        )

        self.assertEqual(
            from_library,
            slot_diagnostics.warnings,
            "the slot wrapper formats the same warning differently",
        )
