"""The grid axis: `grid=`, and the rhythm a part places its notes on.

`parts=` answers *which parts sound* and `texture=` *how many notes the chord part
states*; this answers *where in the bar a part sounds*. Those are different questions
and all three are needed for a comping style to mean anything: a shell on every beat
and a shell on the ands are not variants of one another.

A grid is **rows of `part:pattern`**, because the parts do not move together:
`joe_pass` is a chord on every upbeat and a bass note on every beat.

What is verified, in order:

- **the table**: every row name in `GRID_STYLES` is a pair the parts table allows,
  and every pattern a part may take has a rule (`GRID_PATTERNS`) or is declared a
  **timeline** pattern (`GRID_TIMELINE_PATTERNS`, whose positions come from the
  harmony rather than the metre) - the same coupling `BASS_RULE_ROLES` asserts over
  the bass axis;
- **the metre**: positions are **bar-relative**, so `final_and` is the upbeat of the
  bar's last beat in 2/2, 3/4 and 4/4 alike. This is the claim
  `docs/history/comping-styles.md` section 4.2 makes about `LAST`, and it is a table of three
  metres rather than a comment;
- **the default**: `melody:every_note` is the default outright (there is no `auto`
  sentinel), and it defers to the melody's own slots at every beat - so the axis is
  inert and every existing arrangement is unaffected;
- **the refusal**: a metre-relative figure asked of a metre it was not written for
  raises and names the pattern, and the test is **one-directional** - a bar with no
  note on a grid position is not a refusal, because that is the answer rather than an
  error;
- **the lattice**: the unit a position is counted in (`TICKS_PER_BEAT`, a
  twenty-fourth of a beat) and the note values a **generated** bar may be subdivided
  at (`grid_resolutions`, read through the metre) - the unit is `headxml._tick_key`'s,
  and the vocabulary is `headxml._generated_beats`', so a metre's table moving is a
  generated bar of the wrong density.

The last one is the subtle half and it is why the last class below exists at all: a
grid that refused whenever it placed nothing in a bar would refuse on almost every bar
of real material, and a refusal that fires on the normal case teaches a reader to
ignore refusals.
"""

import glob
import unittest
from contextlib import contextmanager
from functools import reduce
from math import gcd
from pathlib import Path
from typing import Dict, List, Tuple

import headxml
from arranger import (
    GRID_ANCHORS,
    GRID_CHARLESTON,
    GRID_DEFAULT,
    GRID_EVERY_NOTE,
    GRID_FINAL_AND,
    GRID_FREDDIE,
    GRID_JOE_PASS,
    GRID_PART_PATTERNS,
    GRID_PATTERNS,
    GRID_STYLES,
    GRID_TIMELINE_PATTERNS,
    GRID_WALK,
    PART_BASS,
    PART_CHORD,
    SUB,
    TICKS_PER_BEAT,
    GridPattern,
    grid_allowed,
    grid_defers_to_melody,
    grid_positions,
    grid_resolutions,
    on_grid,
    parse_grid,
    resolve_grid,
)
from arranger.options import ArrangeOptions

ROOT = Path(__file__).resolve().parents[1]

#: The committed heads, which the lattice tests read: the same set the importer's figures
#: are taken over, so the unit is measured on the material the engine is measured on.
HEADS: List[str] = sorted(
    glob.glob(str(ROOT / "tests" / "data" / "*.musicxml"))
) + sorted(glob.glob(str(ROOT / "tests" / "data" / "*.mxl")))


PROGRESSION: Tuple[Tuple[str, str, str], ...] = (
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
)


#: A grid name no shipped row uses, so a test may add a pattern that genuinely
#: cannot be placed and exercise the refusal the shipped vocabulary cannot reach.
GRID_OUT_OF_METRE = "out_of_metre"


def _chord(pattern: str) -> str:
    """The **chord part's** row naming `pattern`, which is how a grid is spelled.

    A bare pattern name is not a grid: `parse_grid` refuses it, because every row is
    `part:pattern` and a pattern alone does not say which part moves. Every assertion
    below that means "the chord part plays this figure" has to say so, and this is
    that spelling in one place.
    """
    return f"{PART_CHORD}:{pattern}"


@contextmanager
def _temporary_pattern(name: str, pattern: GridPattern):
    """Add one pattern to both tables for the duration of a `with` block.

    The tables are module state and the axis is a closed set, so the only honest way
    to test the refusal is to add a row and take it out again. **Both** tables are
    patched, because a pattern with a rule and no part that may take it is not
    reachable through `parse_grid` and would fail for the wrong reason. Restored in a
    `finally` so a failing assertion cannot leave the vocabulary altered for the
    next test - which would be a genuinely nasty failure mode, since every later
    assertion in the suite would be reading a table this test corrupted.
    """
    GRID_PATTERNS[name] = pattern
    GRID_PART_PATTERNS[PART_CHORD] = GRID_PART_PATTERNS[PART_CHORD] + (name,)
    try:
        yield
    finally:
        GRID_PATTERNS.pop(name, None)
        GRID_PART_PATTERNS[PART_CHORD] = tuple(
            p for p in GRID_PART_PATTERNS[PART_CHORD] if p != name
        )


def refusal_text(call) -> str:
    """The message a refused call raises, or "" when it raises nothing.

    The refusals raise now rather than warning into a collector, so the assertion
    reads the exception - which is stronger than the collector was: a refusal that
    stopped refusing used to be invisible, and now it fails here.
    """
    try:
        call()
    except ValueError as exc:
        return str(exc)
    return ""


class TestTheGridTable(unittest.TestCase):
    """The vocabulary is closed, and every name in it has a rule."""

    def test_every_style_is_a_pair_the_parts_table_allows(self):
        """No row can be listed without a rule, or ruled without being askable.

        The coupling is bidirectional on purpose. A pattern a part may take but which
        has no row in `GRID_PATTERNS` would read `None` where a position set is
        expected; a rule no part names is a pattern nobody can select, which is how an
        axis quietly grows vocabulary it does not use. A **timeline** pattern is the
        one exception and is declared as one: `anchors` has no within-bar rule at all,
        because its positions come from the harmony rather than the metre.
        """
        self.assertEqual(
            sorted(GRID_STYLES),
            sorted(
                f"{part}:{pattern}"
                for part, patterns in GRID_PART_PATTERNS.items()
                for pattern in patterns
            ),
        )
        for part, patterns in GRID_PART_PATTERNS.items():
            for pattern in patterns:
                with self.subTest(part=part, pattern=pattern):
                    self.assertTrue(
                        pattern in GRID_PATTERNS
                        or pattern in GRID_TIMELINE_PATTERNS,
                        pattern,
                    )
        for pattern in GRID_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertTrue(
                    any(pattern in ps for ps in GRID_PART_PATTERNS.values()), pattern
                )
        self.assertNotIn("auto", GRID_STYLES)

    def test_the_melody_anchored_rows_are_derived_from_the_patterns(self):
        """`grid_defers_to_melody` reads the chord row's own emptiness.

        Derived rather than listed: a pattern cannot be emptied without becoming
        melody-anchored, and a second one is a row rather than a branch at each call
        site. `every_note` is the shipped pattern that does it, and a grid that names
        no chord row defers for the same reason - the chord part then takes the
        melody's slots. That is why the *bass* rows defer too: they say where the
        thumb moves and nothing about the chord.
        """
        for part, patterns in GRID_PART_PATTERNS.items():
            for pattern in patterns:
                row = _chord(pattern) if part == PART_CHORD else f"{part}:{pattern}"
                with self.subTest(row=row):
                    self.assertEqual(
                        grid_defers_to_melody(row),
                        part != PART_CHORD or pattern == GRID_EVERY_NOTE,
                        row,
                    )
        self.assertTrue(grid_defers_to_melody(GRID_DEFAULT))
        self.assertTrue(grid_defers_to_melody(_chord(GRID_EVERY_NOTE)))
        self.assertTrue(grid_defers_to_melody(f"{PART_BASS}:{GRID_WALK}"))
        self.assertFalse(grid_defers_to_melody(_chord(GRID_FREDDIE)))
        # A timeline row is not melody-anchored: it has positions, they just come
        # from the harmony rather than the metre - a different claim from "none".
        self.assertFalse(grid_defers_to_melody(_chord(GRID_ANCHORS)))

    def test_a_row_is_spelled_part_colon_pattern(self):
        """`parse_grid` reads what the documentation tells a user to type.

        Spelled the way a caller passes it, because the surface is the string: a
        parser that could not read its own documented vocabulary would be caught by
        nothing else here. Case is **not** significant, a row's order is not a request
        (the result is sorted and de-duplicated), and a spelling that names no pair -
        a bare pattern, or a pattern the named part cannot take - is refused rather
        than guessed at.
        """
        for style in GRID_STYLES:
            self.assertEqual(parse_grid(style), style)
            self.assertEqual(parse_grid(style.upper()), style)
        self.assertEqual(parse_grid("Chord:Charleston"), _chord(GRID_CHARLESTON))
        self.assertEqual(
            parse_grid(f"melody:every_note,bass:{GRID_WALK}"),
            f"bass:{GRID_WALK},{GRID_DEFAULT}",
        )
        # `auto` was withdrawn when the axis was named (it named the default rather
        # than deferring to any context), so it is refused like any other unknown name.
        with self.assertRaises(ValueError):
            parse_grid("auto")
        with self.assertRaises(ValueError):
            parse_grid(GRID_FREDDIE)
        with self.assertRaises(ValueError):
            parse_grid(_chord(GRID_WALK))
        with self.assertRaises(ValueError):
            parse_grid("half-time")

    def test_an_unknown_grid_is_a_question_not_a_guess(self):
        """A spelling nobody recognises raises, and names the real vocabulary.

        Falling back would comp a part somewhere the caller did not ask for, which is
        worse than the error and worse than silence.
        """
        with self.assertRaises(ValueError) as caught:
            parse_grid(_chord("half-time"))
        self.assertIn("joe_pass", str(caught.exception))


class TestPositionsAreBarRelative(unittest.TestCase):
    """`LAST` resolves against the metre, so one pattern is one idea in three metres.

    This is the claim `docs/history/comping-styles.md` section 4.2 makes and the reason the
    positions are named rather than counted: spelled `[(4, SUB)]`, `final_and` would
    look to a 2/2 head like a pattern naming a beat that does not exist.
    """

    def test_the_final_upbeat_is_the_upbeat_of_the_last_beat_in_every_metre(self):
        """2.5 in 2/2, 3.5 in 3/4, 4.5 in 4/4 - the same figure three times over."""
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertEqual(
                    grid_positions(_chord(GRID_FINAL_AND), beats),
                    ((beats, (beats + 0.5,)),),
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
                self.assertTrue(on_grid(beats + 0.5, _chord(GRID_FINAL_AND), beats))
                self.assertFalse(on_grid(1.5, _chord(GRID_FINAL_AND), beats))

    def test_freddie_is_every_beat_the_metre_has(self):
        """Two notes in 2/2, three in 3/4, four in 4/4.

        A count without a denominator is not a metre (`AGENTS.md` trap 9), and this
        is that trap applied to a rhythm: a four-beat bar has four of these and a
        two-beat bar has two.
        """
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertEqual(
                    [number for number, _ in grid_positions(_chord(GRID_FREDDIE), beats)],
                    list(range(1, beats + 1)),
                )

    def test_joe_pass_is_the_upbeat_of_every_beat(self):
        """The arranging guide's "the chord pops live primarily on the and"."""
        for beats in (2, 3, 4):
            with self.subTest(metre=f"{beats}/4"):
                self.assertEqual(
                    grid_positions(_chord(GRID_JOE_PASS), beats),
                    tuple((n, (n + 0.5,)) for n in range(1, beats + 1)),
                )


class TestTheDefaultIsInert(unittest.TestCase):
    """`every_note` is the default and is on everywhere, which is what "no change" means."""

    def test_the_default_grid_is_every_note(self):
        """The default is the shipped behaviour, not merely a harmless one.

        `grid=auto` used to be the sentinel that resolved to this; Step A withdrew it,
        so the default names `every_note` outright - matching `arrange_progression`'s
        keyword default, which is what makes the two spellings comparable.
        """
        self.assertEqual(ArrangeOptions().grid, GRID_DEFAULT)

    def test_every_note_is_on_the_grid_at_every_beat(self):
        """So a caller that names no grid places exactly the chords it always did."""
        for beat in (1.0, 1.5, 2.0, 2.5, 3.3333, 4.75):
            with self.subTest(beat=beat):
                self.assertTrue(on_grid(beat, GRID_DEFAULT, 4))

    def test_an_unlocated_slot_is_on_the_grid(self):
        """`beat=None` has no position to be off.

        The rule `metric_weight` already follows with its `-1`: not being told
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
                    list(PROGRESSION), grid=_chord(GRID_FINAL_AND)
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
        for style in (_chord(GRID_FREDDIE), _chord(GRID_FINAL_AND), GRID_DEFAULT):
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

    def test_a_metre_relative_figure_that_cannot_fit_raises_and_names_the_pattern(self):
        """The refusal, exercised against a pattern that genuinely places nothing.

        A row of the table, not a shipped one: the function is *derived* from
        `GRID_PATTERNS`, so testing the derivation needs a row the derivation can
        fail on. The alternative - asserting only that no shipped row is refused -
        would leave both messages unexercised, and a message nothing can produce is
        a message nothing has checked.
        """
        pattern = GridPattern(positions=((4, 0), (4, SUB)), bar_relative=False)
        with _temporary_pattern(GRID_OUT_OF_METRE, pattern):
            text = refusal_text(lambda: resolve_grid(_chord(GRID_OUT_OF_METRE), 3))
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
            allowed, reason = grid_allowed(_chord(GRID_OUT_OF_METRE), 3)
        self.assertFalse(allowed)
        self.assertIn("defect in the pattern", reason)

    def test_a_pattern_that_places_nothing_in_a_bar_is_not_refused(self):
        """A bar with no note on a grid position is the answer, not an error.

        This is the measurement that keeps the refusal honest. `final_and` places one
        chord per bar at 2.5, and a head whose bars carry no note there is a head
        where the grid has nothing to do - which is what the user asked for by
        choosing a sparse pattern. Resolving the grid consults only the metre, never
        the material, so this holds before a single note is read.
        """
        self.assertEqual(
            resolve_grid(_chord(GRID_FINAL_AND), 2), _chord(GRID_FINAL_AND)
        )

    def test_the_default_grid_is_never_refused(self):
        """`every_note` places everywhere, so the default resolves in every metre."""
        for beats in (1, 2, 3, 4, 7):
            with self.subTest(metre=beats):
                self.assertEqual(resolve_grid(GRID_DEFAULT, beats), GRID_DEFAULT)


class TestTheLatticeAndItsResolutions(unittest.TestCase):
    """One unit for both halves of a bar: `TICKS_PER_BEAT`, and what a generated bar takes.

    `headxml._generated_beats` subdivides a generated bar in these, and `headxml._tick_key`
    rounds a position to one to decide whether the melody and the grid mean the same
    instant - so this is where `docs/open-issues.md` item 1's two halves meet. Three things
    follow, and each is asserted rather than assumed:

    - **the unit holds every onset of every committed head already**, which is what the
      round trip through `_tick_key` needs: an onset *between* two ticks would be split in
      two rather than matched to one;
    - **the vocabulary is a table read through the metre**, because a resolution is a note
      value and a note value is a fraction of a quarter note - cut time reads a quarter note
      as half a *beat*, so a table read as beats would generate a 2/2 bar at the wrong
      density;
    - **every entry divides the beat, and none is finer than the metre's sixteenth**, which
      is the one property the caller depends on: a grid missing its own downbeat would leave
      a bar's strongest position silent.
    """

    def test_the_beat_is_twenty_four_ticks_and_its_upbeat_is_half_of_one(self):
        """The unit is a twenty-fourth of a beat, and `SUB` is the upbeat in those units.

        `SUB` is a position *within* a beat rather than a note value, so it moves with the
        unit: it was one eighth when a beat was counted in eighths and is twelve ticks now.
        `GRID_CHARLESTON` and `GRID_JOE_PASS` name it as their position, so a change here
        moves every named figure that plays an upbeat - hence pinning both.
        """
        self.assertEqual(TICKS_PER_BEAT, 24)
        self.assertEqual(SUB, TICKS_PER_BEAT // 2)

    def test_the_vocabulary_is_a_note_value_table_read_through_the_metre(self):
        """Common, cut, eighth-note and sixteenth-note beats, each with its own densities.

        The tuples are the ones `grid_resolutions` states, pinned because a metre's table
        moving is a generated bar of the wrong density. The cut-time row is the one a
        beat-relative reading gets wrong: a quarter note there is *half* a beat, and its two
        finest entries - an eighth-note triplet and a sixteenth - have no beat-relative
        reading at all, which is why this takes `beat_type` rather than a count of beats.
        """
        self.assertEqual(grid_resolutions(4), (24, 12, 8, 6))
        self.assertEqual(grid_resolutions(2), (24, 12, 8, 6, 4, 3))
        self.assertEqual(grid_resolutions(8), (24, 12))

    def test_every_resolution_divides_the_beat_and_the_beat_is_always_offered(self):
        """The one property the caller depends on, over every metre the library accepts."""
        for beat_type in (2, 4, 8, 16):
            with self.subTest(beat_type=beat_type):
                resolutions = grid_resolutions(beat_type)
                self.assertEqual(resolutions[0], TICKS_PER_BEAT, "the beat is not offered")
                self.assertEqual(len(set(resolutions)), len(resolutions), "a duplicate")
                self.assertEqual(
                    tuple(sorted(resolutions, reverse=True)),
                    resolutions,
                    "not coarsest first",
                )
                for resolution in resolutions:
                    self.assertEqual(TICKS_PER_BEAT % resolution, 0)

    def test_a_bar_is_never_generated_finer_than_its_metres_sixteenth(self):
        """The floor is a sixteenth note of the metre, not a tick count.

        A sixteenth is a quarter of a beat in common time, an eighth of one in cut time and
        half of one where the beat is an eighth note - so the smallest entry is measured
        against the metre rather than against a number, which is the difference between a
        claim about music and a claim about arithmetic.
        """
        for beat_type in (2, 4, 8, 16):
            with self.subTest(beat_type=beat_type):
                quarter = 6 * beat_type
                sixteenth = quarter // 4
                self.assertGreaterEqual(min(grid_resolutions(beat_type)), sixteenth)

    def test_every_onset_of_every_committed_head_is_on_the_lattice(self):
        """The premise the union rounds on, taken over all the heads rather than argued.

        `_tick_key` decides whether the melody and the grid mean one instant by rounding
        both to a tick, so this is what makes that comparison sound: every written onset is
        within a millionth of a tick, and the rounding therefore merges positions that are
        equal and splits none that are not.
        """
        self.assertTrue(HEADS, "no head was found, so nothing was measured")
        for path in HEADS:
            head = headxml.load_musicxml(path, None)
            with self.subTest(head=Path(path).stem):
                for note in head.notes:
                    ticks = (note.beat - 1.0) * TICKS_PER_BEAT
                    self.assertAlmostEqual(
                        ticks,
                        round(ticks),
                        places=6,
                        msg=f"bar {note.bar} beat {note.beat} sits between two ticks",
                    )

    def test_one_committed_head_needs_the_whole_lattice(self):
        """Why the unit is a twenty-fourth and not a twelfth: `i_was_doing_all_right`.

        The coarsest unit holding a head's onsets is the greatest common divisor of its
        onsets in ticks, and this head's is **one tick** - so no coarser unit holds it, and
        the head is what fixes the size of the lattice. Measured rather than reasoned, and
        it is the cut-time head: a sixteenth note there is an eighth of a half-note beat and
        an eighth-note triplet a sixth of one.
        """
        coarsest: Dict[str, int] = {}
        for path in HEADS:
            head = headxml.load_musicxml(path, None)
            onsets = [round((note.beat - 1.0) * TICKS_PER_BEAT) for note in head.notes]
            coarsest[Path(path).stem] = reduce(gcd, onsets, 0)
        self.assertEqual(coarsest["i_was_doing_all_right"], 1, "the cut-time head moved")
        self.assertEqual(min(value for value in coarsest.values() if value), 1)

        self.assertEqual(grid_resolutions(16), (24,))

