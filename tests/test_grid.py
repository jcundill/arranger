"""The grid axis: `grid=`, and the rhythm a comping style places chords on.

`harmony=` answers *what degrees* a stab states and this answers *where one lands*.
Those are two different questions and both are needed for a comping style to mean
anything: a shell on every beat and a shell on the ands are not variants of one
another.

What is verified, in order:

- **the table**: every name in `GRID_STYLES` has a row in `GRID_PATTERNS`, so a
  pattern cannot be listed without a rule or given one without a name - the same
  coupling `BASS_POLICY_ROLES` asserts over the bass axis;
- **the metre**: positions are **bar-relative**, so `final_and` is the upbeat of the
  bar's last beat in 2/2, 3/4 and 4/4 alike. This is the claim
  `docs/comping-styles.md` section 4.2 makes about `LAST`, and it is a table of three
  metres rather than a comment;
- **the default**: `grid=auto` resolves to `every_note`, which is on the grid at every
  beat - so the axis is inert and every existing arrangement is unaffected;
- **the refusal**: a metre-relative figure asked of a metre it was not written for
  warns and falls back, and the test is **one-directional** - a bar with no note on a
  grid position is not a warning, because that is the answer rather than an error.

The last one is the subtle half and it is why the last class below exists at all: a
grid that warned whenever it placed nothing in a bar would warn on almost every bar
of real material, and a warning that fires on the normal case teaches a reader to
ignore warnings.
"""

import unittest
from contextlib import contextmanager
from typing import Tuple

from arranger import (
    GRID_AUTO,
    GRID_CHARLESTON,
    GRID_EVERY_NOTE,
    GRID_FINAL_AND,
    GRID_FREDDIE,
    GRID_JOE_PASS,
    GRID_PATTERNS,
    GRID_STYLES,
    SUB,
    Diagnostics,
    GridPattern,
    grid_allowed,
    grid_positions,
    on_grid,
    parse_grid,
    resolve_grid,
)

PROGRESSION: Tuple[Tuple[str, str, str], ...] = (
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
)


#: A grid name no shipped row uses, so a test may add a pattern that genuinely
#: cannot be placed and exercise the refusal the shipped vocabulary cannot reach.
GRID_OUT_OF_METRE = "out_of_metre"


@contextmanager
def _temporary_pattern(name: str, pattern: GridPattern):
    """Add one row to `GRID_PATTERNS` for the duration of a `with` block.

    The table is module state and the axis is a closed set, so the only honest way
    to test the refusal is to add a row and take it out again. Restored in a
    `finally` so a failing assertion cannot leave the vocabulary altered for the
    next test - which would be a genuinely nasty failure mode, since every later
    assertion in the suite would be reading a table this test corrupted.
    """
    GRID_PATTERNS[name] = pattern
    try:
        yield
    finally:
        GRID_PATTERNS.pop(name, None)


def warning_text(run) -> str:
    """Every warning one call emits, joined - the collector is silent, not absent."""
    diagnostics = Diagnostics()
    run(diagnostics)
    return "\n".join(diagnostics.warnings)


class TestTheGridTable(unittest.TestCase):
    """The vocabulary is closed, and every name in it has a rule."""

    def test_every_style_has_a_pattern_and_every_pattern_a_style(self):
        """No name can be listed without a rule, or ruled without being asked for.

        The coupling is bidirectional on purpose. A style with no row would reach
        `grid_positions` and raise `KeyError` from inside a step loop; a row with no
        style is a pattern nobody can select, which is how an axis quietly grows
        vocabulary it does not use.
        """
        self.assertEqual(sorted(GRID_STYLES), sorted(GRID_PATTERNS))
        self.assertNotIn("auto", GRID_STYLES)

    def test_a_pattern_may_be_named_on_the_command_line(self):
        """`parse_grid` reads what the documentation tells a user to type.

        Spelled the way a caller passes it, because the surface is the string: a
        parser that could not read its own documented vocabulary would be caught by
        nothing else here. Case is **not** significant, and a name differing only in
        case resolves to the same pattern rather than raising - which is why the
        unknown-name test below uses a spelling that differs in more than case.
        """
        for style in GRID_STYLES:
            self.assertEqual(parse_grid(style), style)
            self.assertEqual(parse_grid(style.upper()), style)
        self.assertEqual(parse_grid("Charleston"), GRID_CHARLESTON)
        self.assertEqual(parse_grid(GRID_AUTO), GRID_AUTO)
        with self.assertRaises(ValueError):
            parse_grid("half-time")

    def test_an_unknown_grid_is_a_question_not_a_guess(self):
        """A spelling nobody recognises raises, and names the real vocabulary.

        Falling back would return a part that comps somewhere the caller did not ask
        for, which is worse than the error and worse than silence.
        """
        with self.assertRaises(ValueError) as caught:
            parse_grid("half-time")
        self.assertIn("joe_pass", str(caught.exception))


class TestPositionsAreBarRelative(unittest.TestCase):
    """`LAST` resolves against the metre, so one pattern is one idea in three metres.

    This is the claim `docs/comping-styles.md` section 4.2 makes and the reason the
    positions are named rather than counted: spelled `[(4, SUB)]`, `final_and` would
    look to a 2/2 head like a pattern naming a beat that does not exist.
    """

    def test_the_final_upbeat_is_the_upbeat_of_the_last_beat_in_every_metre(self):
        """2.5 in 2/2, 3.5 in 3/4, 4.5 in 4/4 - the same figure three times over."""
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertEqual(
                    grid_positions(GRID_FINAL_AND, beats), ((beats, (beats + 0.5,)),)
                )

    def test_the_final_upbeat_is_not_the_first_upbeat(self):
        """The sentinel means *last*, and this is what catches it meaning something else.

        A beat is 1-based, so an off-by-one in the resolution puts the pattern on the
        upbeat of the **first** beat - a position that exists in every metre, so every
        other assertion in this file would still pass. That is why this is its own
        test rather than a comment, and it is the bug this file was written against.
        """
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertTrue(on_grid(beats + 0.5, GRID_FINAL_AND, beats))
                self.assertFalse(on_grid(1.5, GRID_FINAL_AND, beats))

    def test_freddie_is_every_beat_the_metre_has(self):
        """Two notes in 2/2, three in 3/4, four in 4/4.

        A count without a denominator is not a metre (`AGENTS.md` trap 9), and this
        is that trap applied to a rhythm: a four-beat bar has four of these and a
        two-beat bar has two.
        """
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertEqual(
                    [number for number, _ in grid_positions(GRID_FREDDIE, beats)],
                    list(range(1, beats + 1)),
                )

    def test_joe_pass_is_the_upbeat_of_every_beat(self):
        """The arranging guide's "the chord pops live primarily on the and"."""
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertEqual(
                    grid_positions(GRID_JOE_PASS, beats),
                    tuple((n, (n + 0.5,)) for n in range(1, beats + 1)),
                )


class TestTheDefaultIsInert(unittest.TestCase):
    """`auto` resolves to a grid that is on everywhere, which is what "no change" means."""

    def test_auto_resolves_to_every_note(self):
        """The resolved value is the shipped behaviour, not merely a harmless one."""
        self.assertEqual(resolve_grid(GRID_AUTO, 4, Diagnostics()), GRID_EVERY_NOTE)

    def test_every_note_is_on_the_grid_at_every_beat(self):
        """So a caller that names no grid places exactly the chords it always did."""
        for beat in (1.0, 1.5, 2.0, 2.5, 3.3333, 4.75):
            with self.subTest(beat=beat):
                self.assertTrue(on_grid(beat, GRID_EVERY_NOTE, 4))

    def test_an_unlocated_slot_is_on_the_grid(self):
        """`beat=None` has no position to be off.

        The rule `_metric_weight` already follows with its `-1`: not being told
        where a note falls is not being told it is weak. Without this, a
        hand-written progression - which carries no timings at all - would lose
        every chord the moment someone passed a grid, which is the opposite of an
        opt-in.
        """
        for style in GRID_STYLES:
            with self.subTest(style=style):
                self.assertTrue(on_grid(None, style, 4))

    def test_a_progression_with_no_timing_arranges_identically(self):
        """The end-to-end version of the claim above, on a real arrangement.

        Asserted through `format_progression` rather than through the predicate,
        because "byte-identical" is a claim about what a player reads and the
        predicate is only a step on the way to it.
        """
        from arranger import VoiceLeadingEngine, format_progression

        # `arrange_progression` returns the **list** of steps, not one step: indexing
        # it here would hand `format_progression` a single `ArrangementStep`, which is
        # dict-style and would be iterated as its field names.
        default = VoiceLeadingEngine.arrange_progression(list(PROGRESSION))
        self.assertEqual(
            format_progression(
                VoiceLeadingEngine.arrange_progression(
                    list(PROGRESSION), grid=GRID_FINAL_AND
                )
            ),
            format_progression(default),
        )


class TestTheRefusalIsOneDirectional(unittest.TestCase):
    """Only a pattern that places *nothing anywhere* is a mismatch.

    The other direction - "this bar had no note on one of the grid's positions" - has
    a correct answer of "no, and that is fine", so warning there would fire on
    almost every bar of real material.
    """

    def test_a_bar_relative_pattern_is_allowed_in_every_metre(self):
        """`LAST` and `ALL` both resolve, so these can never be a mismatch."""
        for style in (GRID_FREDDIE, GRID_FINAL_AND, GRID_EVERY_NOTE):
            for beats in (2, 3, 4, 5, 6):
                with self.subTest(style=style, metre=beats):
                    allowed, reason = grid_allowed(style, beats)
                    self.assertTrue(allowed, reason)
                    self.assertEqual(reason, "")

    def test_no_shipped_row_is_a_mismatch_in_any_metre(self):
        """Measured, and it is why the refusal is defensive rather than routine.

        Every metre-relative row is asked of every metre from one beat up, and none
        of them is ever refused: `charleston` keeps its beat 1, which exists
        everywhere, and `joe_pass` is built on `ALL`, which always resolves. So the
        refusal below is unreachable through the shipped vocabulary **today**.

        That is worth stating rather than leaving implied. A check no input can fail
        proves nothing about the axis, which is why the next two tests exercise it
        against a row that genuinely cannot be expressed - and why this one exists
        to keep the two claims apart.
        """
        for style in GRID_STYLES:
            for beats in range(1, 9):
                with self.subTest(style=style, metre=beats):
                    allowed, reason = grid_allowed(style, beats)
                    self.assertTrue(allowed, f"{style} in {beats}/4: {reason}")

    def test_a_metre_relative_figure_that_cannot_fit_warns_and_names_the_pattern(self):
        """The refusal, exercised against a pattern that genuinely places nothing.

        A row of the table, not a shipped one: the function is *derived* from
        `GRID_PATTERNS`, so testing the derivation needs a row the derivation can
        fail on. The alternative - asserting only that no shipped row is refused -
        would leave both warning messages unexercised, and a message nothing can
        produce is a message nothing has checked.
        """
        pattern = GridPattern(positions=((4, 0), (4, SUB)), bar_relative=False)
        with _temporary_pattern(GRID_OUT_OF_METRE, pattern):
            text = warning_text(
                lambda d: resolve_grid(GRID_OUT_OF_METRE, 3, d)
            )
        self.assertIn(GRID_OUT_OF_METRE, text)
        self.assertIn("bar-relative", text)

    def test_a_bar_relative_row_that_places_nothing_is_reported_as_a_defect(self):
        """The two refusals are different claims, and each says which it is.

        A bar-relative pattern that resolved nowhere would be a bug in the table,
        because `LAST` and `ALL` are defined to resolve in any metre - so its warning
        says so, and does not suggest the user asked for the wrong thing.
        """
        pattern = GridPattern(positions=((7, 0),), bar_relative=True)
        with _temporary_pattern(GRID_OUT_OF_METRE, pattern):
            allowed, reason = grid_allowed(GRID_OUT_OF_METRE, 3)
        self.assertFalse(allowed)
        self.assertIn("defect in the pattern", reason)

    def test_a_pattern_that_places_nothing_in_a_bar_is_not_a_warning(self):
        """A bar with no note on a grid position is the answer, not an error.

        This is the measurement that keeps the refusal honest. `final_and` places one
        chord per bar at 2.5, and a head whose bars carry no note there is a head
        where the grid has nothing to do - which is what the user asked for by
        choosing a sparse pattern. Resolving the grid consults only the metre, never
        the material, so this holds before a single note is read.
        """
        diagnostics = Diagnostics()
        self.assertEqual(resolve_grid(GRID_FINAL_AND, 2, diagnostics), GRID_FINAL_AND)
        self.assertEqual(diagnostics.warnings, [])

    def test_a_resolved_auto_never_warns(self):
        """`every_note` places everywhere, so the default is silent in every metre."""
        for beats in (1, 2, 3, 4, 7):
            with self.subTest(metre=beats):
                diagnostics = Diagnostics()
                resolve_grid(GRID_AUTO, beats, diagnostics)
                self.assertEqual(diagnostics.warnings, [])
