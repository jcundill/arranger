"""The one-line tab: one line per step, its fixed columns and the annotation that explains it.

`format_progression` is what a user reads, so its layout - chord, melody, degree, the six
tab cells, then the step's own explanation - is pinned by column here rather than by
re-deriving it from a `split()` the padded cells make ambiguous.
"""

import io
import unittest
from contextlib import redirect_stdout
from typing import List

import arranger
from arranger import (
    ArrangementStep,
    VoiceLeadingEngine,
    format_progression,
    format_tab_html,
    format_tab_staff,
)
from arranger.annotation import step_annotation
from arranger.options import ArrangeOptions, Request
from arranger.tuning import NO_CHORD
from tests.support import arranged, make_voicing, sweep_head_paths

# The compact line's fixed layout, in columns: chord(8) + space + melody(3) + space =
# 13, then degree(4) + space = 18, then six two-character cells joined by '-' = 17 more.
# Named here so a test asserts the field the renderer builds, rather than re-deriving it
# from a `split()` that the padded cells make ambiguous.
_DEGREE_FIELD = slice(13, 17)
_TAB_FIELD = slice(18, 35)
# The four fields end at 35, one space follows, and the step's explanation begins. A step
# whose explanation does not fit the line continues below it, indented to this column -
# so a continuation line is one that has nothing but spaces in the fields above.
_ANNOTATION_FIELD = slice(36, None)

#: The committed heads, which between them carry every quality, metre and texture the
#: suite sweeps. `tests/data` is the only corpus there is.


def _tab_cells(line: str) -> List[str]:
    """The six tab cells of a `format_progression` line, trimmed of their padding."""
    return [cell.strip() for cell in line[_TAB_FIELD].split("-")]


def _blocks(rendered: str) -> List[List[str]]:
    """A `format_progression` rendering as one list of lines per step.

    A step starts on the line its chord column is written on; the continuation lines
    carry the explanation alone and so begin with spaces. That is the whole difference
    the wrapping makes, and grouping this way is what lets a test index *steps* rather
    than lines - which is what every test here did before a step could be more than one
    line.
    """
    blocks: List[List[str]] = []
    for line in rendered.split("\n") if rendered else []:
        if line.startswith(" ") and blocks:
            blocks[-1].append(line)
        else:
            blocks.append([line])
    return blocks


class TestVoicingTabBlock(unittest.TestCase):
    """Tests the six-line vertical tab renderer on a Voicing."""

    def setUp(self):
        # Dm7 in the traditional high-E block: strings D-G-B-E carry 10-10-10-10.
        self.high_e = make_voicing([-1, -1, 10, 10, 10, 10])
        # Same inversion voiced on the B string instead (strings A-D-G-B).
        self.b_string = make_voicing([-1, 3, 3, 2, 3, -1])

    def test_block_has_six_lines_in_reading_order(self):
        """One line per string, ordered high E (string 1) down to low E (string 6)."""
        lines = self.high_e.tab_block()
        self.assertEqual(len(lines), 6)
        self.assertEqual([line[0] for line in lines], ["e", "B", "G", "D", "A", "E"])

    def test_block_renders_frets_and_mutes(self):
        """Played strings show their fret; muted strings show 'x'."""
        lines = self.high_e.tab_block()
        for line in lines[:4]:
            self.assertIn("10", line)
        for line in lines[4:]:
            self.assertIn("x", line)

    def test_block_places_b_string_melody_on_second_line(self):
        """
        A B-string voicing mutes the high E and plays the A, so the topmost
        rendered line (high E) is 'x' and the melody appears one line lower.
        """
        # frets [-1, 3, 3, 2, 3, -1] low E -> high E, so rendering high E first
        # gives: high E x, B 3, G 2, D 3, A 3, low E x.
        cells = [line[2:4].strip() for line in self.b_string.tab_block()]
        self.assertEqual(cells, ["x", "3", "2", "3", "3", "x"])

    def test_block_columns_align_for_single_and_double_digit_frets(self):
        """
        Every fret cell is right-aligned to two characters, so the closing '|'
        of each line lands in the same column whether frets are 1 or 2 digits.
        This is what keeps a low B-string voicing visually aligned.
        """
        for voicing in (self.high_e, self.b_string):
            for line in voicing.tab_block():
                self.assertEqual(len(line), 6, line)
                self.assertTrue(line.endswith("-|"), line)

    def test_block_matches_the_one_line_tab(self):
        """Each rendered cell equals the corresponding entry of tab_string()."""
        expected = self.b_string.tab_string().split("-")
        # tab_string runs low E -> high E; tab_block renders high E -> low E.
        cells = [line[2:4].strip() for line in self.b_string.tab_block()]
        self.assertEqual(cells, list(reversed(expected)))

    def test_fully_muted_voicing_renders_without_raising(self):
        """An all-muted voicing still renders six lines rather than raising."""
        muted = make_voicing([-1] * 6)
        lines = muted.tab_block()
        self.assertEqual(len(lines), 6)
        self.assertTrue(all("x" in line for line in lines))

    def test_tab_joins_block_with_newlines(self):
        """tab() is exactly tab_block() joined by newlines."""
        self.assertEqual(self.high_e.tab(), "\n".join(self.high_e.tab_block()))


class TestArrangementStepTab(unittest.TestCase):
    """Tests that ArrangementStep delegates its tab rendering to its Voicing."""

    def setUp(self):
        self.voicing = make_voicing([-1, -1, 10, 10, 10, 10])
        self.step = ArrangementStep(chord="Dm7", melody="D5", voicing=self.voicing)

    def test_tab_line_delegates_to_voicing(self):
        """tab_line() is the one-line form and equals voicing.tab_string()."""
        self.assertEqual(self.step.tab_line(), "x-x-10-10-10-10")
        self.assertEqual(self.step.tab_line(), self.voicing.tab_string())

    def test_tab_block_delegates_to_voicing(self):
        """tab_block() equals voicing.tab_block() line for line."""
        self.assertEqual(self.step.tab_block(), self.voicing.tab_block())


class TestFormatProgression(unittest.TestCase):
    """Tests the progression-level renderer returned by format_progression()."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # Dm7 -> G7 -> Cmaj7, pinned to the high E block. These tests are about the
        # *renderer*, so the string set is fixed and the grip is left to the
        # selector - the arity rule offers the whole family set, and this fixture is
        # whatever the tuple prefers inside it.
        self.major = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("B4", "7", "G7"), ("C5", "maj7", "Cmaj7")],
            top_strings=(5,),
        )
        self.all_of_me = self.engine.arrange_progression(
            [("C5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7"), ("C5", "maj7", "Cmaj7")]
        )

    def test_a_short_explanation_is_one_line_per_step(self):
        """A step whose explanation fits the width is one line, as it always was.

        The renderer is no longer "one line per step" for *every* step - a long
        explanation continues below its step - but nothing about the short case changed:
        the four columns are on the one line, with the annotation trailing them.
        """
        steps = self.engine.arrange_progression([("F4", NO_CHORD, NO_CHORD)])
        lines = format_progression(steps).split("\n")
        self.assertEqual(len(lines), 1)
        self.assertIn("F4", lines[0])
        self.assertIn("(no chord - melody alone)", lines[0])

    def test_a_long_explanation_continues_below_its_step(self):
        """The explanation wraps rather than running off the page, one step still a block.

        Each continuation line carries the explanation alone: the four columns are on the
        step's first line, so the table is still read down the page.
        """
        blocks = _blocks(format_progression(self.major))
        self.assertEqual(len(blocks), len(self.major))
        self.assertGreater(
            sum(len(block) for block in blocks), len(self.major), "nothing wrapped"
        )
        for block in blocks:
            self.assertRegex(block[0][_TAB_FIELD].strip(), r"^[x0-9]+(-[x0-9]+){5}$")
            for continuation in block[1:]:
                self.assertEqual(continuation[:_ANNOTATION_FIELD.start], " " * 36)
                self.assertTrue(continuation[_ANNOTATION_FIELD.start:].strip())

    def test_width_none_is_one_line_per_step(self):
        """The escape hatch: the caller who wants a line per step still gets one."""
        rendered = format_progression(self.major, width=None)
        lines = rendered.split("\n")
        self.assertEqual(len(lines), len(self.major))
        for line, step in zip(lines, self.major):
            self.assertIn(step_annotation(step).strip(), line)
            self.assertIn(step.chord, line)

    def test_vertical_is_no_longer_an_argument(self):
        """`format_progression` no longer takes `vertical`, and says so by raising.

        The inversion of the test this replaces, which asserted that `vertical=True`
        gave seven lines per step. That branch is gone: the compact one-line form is
        the whole renderer, and a whole-progression staff is `format_tab_staff`'s
        job. Asserting the `TypeError` pins the removal, so a caller that still
        passes it gets a clear failure rather than a silently different rendering.

        A `TypeError` is the honest form of that failure: the parameter was removed
        rather than deprecated, so there is nothing to warn about and nothing to
        keep working.
        """
        with self.assertRaises(TypeError):
            format_progression(self.major, vertical=True)  # type: ignore[call-arg]

    def test_non_chord_tone_step_is_annotated(self):
        """
        The D5 in 'All of Me' bar 2 is the 9th over Cmaj7, so the default
        strategy reharmonises it and the rendered line must say so.
        """
        rendered = format_progression(self.all_of_me)
        self.assertIn("non-chord tone", rendered)
        self.assertIn("Cmaj9", rendered)
        # The two chord-tone steps name their degree instead of coming back blank.
        self.assertEqual(rendered.count("non-chord tone"), 1)
        self.assertEqual(rendered.count("(harmony under "), 2)

    def test_chord_tone_steps_name_their_degree(self):
        """A plain chord-tone progression says which degree each melody note is."""
        rendered = format_progression(self.major)
        self.assertNotIn("non-chord", rendered)
        self.assertEqual(rendered.count("(harmony under "), 3)

    def test_empty_progression_renders_empty_string(self):
        """No steps means an empty string, not a stray newline."""
        self.assertEqual(format_progression([]), "")

    def test_renderers_print_nothing(self):
        """
        format_progression() and the Voicing/ArrangementStep tab helpers are pure
        renderers: they return a string and write nothing to stdout, leaving the
        caller in control of how tab is displayed.
        """
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            format_progression(self.major)
            self.major[0].tab_line()
            self.major[0].tab_block()
            self.major[0].voicing.tab()
            self.major[0].voicing.tab_block()
        self.assertEqual(buffer.getvalue(), "")


class TestTextureAnnotation(unittest.TestCase):
    """
    A fill step has to say why it is thin.

    The chord name printed above a two-note shape describes the harmony, not every
    note sounding, so a reader counting strings would otherwise wonder where the rest
    of the chord went. That is already true of a shell and a duo; an `interval` fill
    is the case where it matters most, because the two notes need not both be chord
    tones at all.
    """

    def setUp(self):
        # A bar of running notes under one chord: the strong beats are full, the rest
        # thin. Every melody note is a **chord tone of Fmaj7** and every one is
        # different, because both of those matter to what is being tested here: a
        # repeated note is annotated as a held single note, and a non-chord tone is
        # annotated with its substitution. Either would take precedence over the
        # partial-harmonisation note, correctly - see
        # test_a_non_chord_tone_annotation_takes_precedence_over_the_fill_note.
        self.steps = VoiceLeadingEngine.arrange_progression(
            [
                ("C5", "maj7", "Fmaj7"),
                ("E5", "maj7", "Fmaj7"),
                ("A4", "maj7", "Fmaj7"),
                ("F4", "maj7", "Fmaj7"),
            ],
            timings=[(0, 1.0, None), (0, 1.5, None), (0, 2.0, None), (0, 3.0, None)],
            options=ArrangeOptions(request=Request(chord_notes="targets")),
        )
        self.rendered = format_progression(self.steps)

    def test_a_thin_step_is_annotated_as_partial(self):
        """Every fill says so, in the shared annotation the staff renderer uses too."""
        fills = [s for s in self.steps if s.role == arranger.tuning.ROLE_FILL]
        self.assertTrue(fills, "the fixture must contain fills")
        for step in fills:
            self.assertTrue(step.partial, f"{step.melody} is a fill but not partial")
            self.assertIn("partial", step_annotation(step))

    def test_a_non_chord_tone_annotation_takes_precedence_over_the_fill_note(self):
        """
        A substituted chord is named instead of the partial-harmonisation note.

        Both are true of such a step, but the substitution is the more important fact:
        it says the *chord* changed, and a reader who missed that would be reading
        the wrong harmony over the tab. This is the pre-existing precedence in
        `step_annotation` - a fill does not get its own exception to it.
        """
        steps = VoiceLeadingEngine.arrange_progression(
                [("D5", "maj7", "Fmaj7")], timings=[(0, 2.0, None)], options=ArrangeOptions(
                    request=Request(chord_notes="targets"),
                ),
            )
        step = steps[0]
        self.assertEqual(step.role, arranger.tuning.ROLE_FILL)
        self.assertTrue(step.non_chord_tone)
        self.assertIn("non-chord tone", step_annotation(step))

    def test_the_annotation_names_the_interval_not_the_grip(self):
        """
        An interval fill names the interval it actually is.

        A player needs to read "6th", not "interval": the first says what to play
        against the melody, the second only says what the software called it.
        """
        intervals = [s for s in self.steps if s.grip == "interval"]
        if not intervals:
            self.skipTest("this fixture produced no interval fills")
        for step in intervals:
            note = step_annotation(step)
            self.assertIn("interval fill", note)
            self.assertRegex(note, r"interval fill - (3rd|b6|6th|2 notes)")

    def test_the_staff_draws_the_fill_as_the_thin_shape_that_sounds(self):
        """
        The staff renders the fill's own shape, not a re-derived full chord.

        `format_tab_staff` has no annotation channel - the line above the staff carries
        chord names only - so the way it must not mislead a reader is by drawing the
        shape that actually sounds. For this fixture every shape sits in the top four
        strings, so the low E row carries no fret at all: a three-note fill leaves it
        blank, and a four-note drop-2 on the high E would not.
        """
        staff = format_tab_staff(self.steps, show_chords=True)
        low_e = next(line for line in staff.split("\n") if line.startswith("E |"))
        self.assertFalse(
            [c for c in low_e if c.isdigit()],
            f"the low E row should be blank for this fixture: {low_e!r}",
        )
        # And the melody row is not blank, or the assertion above would be vacuous.
        high_e = next(line for line in staff.split("\n") if line.startswith("e"))
        self.assertTrue([c for c in high_e if c.isdigit()], "the melody row is empty")

    def test_a_uniform_arrangement_carries_no_texture_annotation(self):
        """
        The default output is unchanged by all of this.

        Without timings every step is a target, so no fill annotation appears and the
        rendering is what it always was.
        """
        plain = VoiceLeadingEngine.arrange_progression(
            [("C5", "maj7", "Fmaj7"), ("B4", "maj7", "Fmaj7")]
        )
        self.assertNotIn("interval fill", format_progression(plain))


class TestRepeatedMelody(unittest.TestCase):
    """
    A melody that repeats the previous step's pitch is played as a single note:
    the shape is struck once and the melody is re-articulated on its own. This
    matches what the Weimar transcription of "All the Things You Are" does at bars
    61-63, where one note is held across three chord changes. The voicing is still
    generated in full, so these tests check the *rendering* while `voicing` keeps
    the real shape available to a caller.
    """

    def setUp(self):
        # C4 on the B string at fret 1: the shape F-7 is voiced with in bar 61.
        self.voicing = make_voicing([-1, 1, 1, 0, 1, -1])
        self.steps = [
            ArrangementStep(
                chord="F-7", melody="C4", voicing=self.voicing, bar=0, beat=1.0
            ),
            ArrangementStep(
                chord="Bb-7", melody="C4", voicing=self.voicing,
                repeated=True, bar=1, beat=1.0,
            ),
            ArrangementStep(
                chord="Eb7", melody="C4", voicing=self.voicing,
                repeated=True, bar=2, beat=1.0,
            ),
        ]

    def test_engine_marks_a_repeated_melody(self):
        """arrange_progression flags every step after the first on the same pitch."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("D5", "m7", "Dm7"), ("F5", "maj7", "Fmaj7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, True, False])

    def test_engine_does_not_flag_a_moving_melody(self):
        """A step whose melody moves is not a repeat, even on the same chord."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "m7", "Dm7"), ("F5", "m7", "Dm7")]
        )
        self.assertFalse(any(step.repeated for step in steps))

    def test_a_run_of_repeats_is_all_flagged(self):
        """Four notes on the same pitch: the first is struck, the next three repeat."""
        progression = [("C4", "m7", "Dm7")] * 4
        steps = VoiceLeadingEngine.arrange_progression(progression)
        self.assertEqual([step.repeated for step in steps], [False, True, True, True])

    def test_engine_does_not_flag_a_repeat_across_a_chord_change(self):
        """
        A held note under a new chord is not a hold: the ringing voices belong to the
        chord the hold started on, so the step is re-harmonised and struck in full.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C4", "m7", "F-7"), ("C4", "m7", "Bb-7"), ("C4", "7", "Eb7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, False, False])

    def test_engine_still_holds_a_repeat_under_one_chord(self):
        """
        The flip side: a repeat that is not also a chord change is still a hold. This
        is the case that leaves the shape ringing rather than re-fingering it.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C4", "7", "Eb7"), ("C4", "7", "Eb7"), ("C4", "7", "Eb7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, True, True])

    def test_engine_compares_harmony_not_the_chord_spelling(self):
        """
        `D-7` and `Dm7` are the same chord written two ways, so a note repeating
        across that change is still a hold. Compared as (root, quality), not as text.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C4", "m7", "D-7"), ("C4", "m7", "Dm7")]
        )
        self.assertEqual([step.repeated for step in steps], [False, True])

    def test_repeat_across_a_chord_change_is_reharmonised(self):
        """
        A melody repeating is a hold only while the harmony under it is unchanged.
        Across a chord change the ringing voices belong to the chord the hold began
        on, so the step is sounded in full and the renderers show the whole shape.
        """
        chords = ["F-7", "Bb-7", "Eb7", "Eb7"]
        steps = [
            ArrangementStep(
                chord=chord, melody="C4", voicing=self.voicing,
                # Only the second Eb7 is a hold: a repeat under the same chord.
                repeated=(index == 2),
                bar=index, beat=1.0,
            )
            for index, chord in enumerate(chords[1:])
        ]
        blocks = _blocks(format_progression(steps))
        # The two chord changes are sounded in full, so the renderers show the shape.
        for block, chord in zip(blocks[:2], chords[1:3]):
            self.assertNotIn("melody repeated", block[0], chord)
        # Only the last is a hold: the Eb7 repeating under the Eb7.
        self.assertIn("melody repeated", blocks[-1][0])
        # The shape has collapsed to the soprano, so the strings it does not strike are x.
        self.assertEqual(_tab_cells(blocks[-1][0]), ["x", "x", "x", "x", "1", "x"])

    def test_voicing_is_unchanged_so_the_shape_is_still_available(self):
        """The flag is presentational: the step keeps its full drop-2 voicing."""
        self.assertEqual(self.steps[1].tab_line(), "x-1-1-0-1-x")

    def test_one_line_tab_plays_a_single_note(self):
        """Only the melody string carries a fret; every other string is muted."""
        block = _blocks(format_progression(self.steps))[1]
        self.assertEqual(_tab_cells(block[0]), ["x", "x", "x", "x", "1", "x"])

    def test_annotation_says_the_note_repeats(self):
        """The chord label alone would imply a full shape, so the line is annotated."""
        self.assertIn(
            "melody repeated", _blocks(format_progression(self.steps))[1][0]
        )

    def test_staff_shows_the_soprano_only(self):
        """On the staff the other strings are left blank, as for a held voice."""
        string_lines = format_tab_staff(self.steps).split("\n")[-6:]
        # The B line carries the melody on all three steps; the G line only on the
        # first, because the repeats strike the melody alone.
        self.assertEqual(string_lines[1].count("1"), 3)
        self.assertEqual(string_lines[2].count("0"), 1)

    def test_staff_still_strikes_a_repeated_step_under_collapse(self):
        """
        Collapse would normally print nothing for an unchanged shape, but a
        repeated melody is re-articulated, so the step must still strike.
        """
        string_lines = format_tab_staff(self.steps, collapse=True).split("\n")[-6:]
        self.assertEqual(string_lines[1].count("1"), 3)

    def test_html_shows_the_soprano_only(self):
        """The HTML table leaves the other strings empty, not marked x."""
        page = format_tab_html(self.steps)
        measures = page.split('<div class="measure">')[1:]
        self.assertEqual(measures[0].count("<td>1</td>"), 3)
        self.assertEqual(measures[1].count('class="repeat">1<'), 1)
        self.assertIn('<td class="repeat"></td>', measures[1])

    def test_html_marks_a_repeated_column(self):
        """
        The muted strings are drawn faintly, so without a marker a repeated note
        would read as a mostly-empty column rather than a deliberate single note.
        """
        page = format_tab_html(self.steps)
        measures = page.split('<div class="measure">')[1:]
        self.assertNotIn("repeat", measures[0])
        self.assertIn("repeat", measures[1])

    def test_melody_only_repeat_stays_a_single_fret(self):
        """
        An NC step has no inner voices to hold, so it is never marked as a repeat
        and keeps spelling its own mutes.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D5", "NC", "NC"), ("D5", "NC", "NC")]
        )
        self.assertFalse(any(step.repeated for step in steps))
        self.assertTrue(all(step.melody_only for step in steps))


class TestTheExplanationWraps(unittest.TestCase):
    """A long explanation is the same text over more lines, and it stays in its column.

    Three invariants make a continuation line safe to read: **nothing is lost** (the layout
    inserts a newline in place of a space and changes nothing else), **no line runs past the
    width** except for a single word wider than the room it has, and the four columns are on
    the step's own line rather than repeated above the prose. Swept over the sweep heads,
    because a break falls differently for every clause the sweep meets - a walk's bass
    phrase, a comping grid, a substitution, a thin fill.
    """

    #: Where the explanation begins, and so where a continuation line is indented to.
    COLUMN = 36

    #: The renderer's own default, named here so a change to it fails this class.
    WIDTH = 100

    def rendered_steps(self):
        """(head, step) for the sweep heads under four clause-bearing configs.

        Four tests in this class read the same generator, and each of those calls it once
        per assertion, so the arrangements come from `tests.support.arranged`: one per
        (head, config) for the whole class rather than one per pass. The heads are
        `tests.support.sweep_head_paths()` - the wrapping rule is about width, and a
        clause long enough to wrap is not a property of any one tune.
        """
        for head in sweep_head_paths():
            for config in (
                {},
                {"options": ArrangeOptions(request=Request(melody=False))},
                {"request": Request(chord_on="every-beat")},
                {"options": ArrangeOptions(request=Request(chord_notes="targets"))},
            ):
                steps, _head, _notes = arranged(head, section=(1, 4), **config)
                for step in steps:
                    yield head, step

    def test_the_wrapped_lines_are_the_annotation_and_nothing_else(self):
        """Every word of the annotation is printed once, in order - and no other word is."""
        from arranger.render import _format_step

        checked = 0
        for head, step in self.rendered_steps():
            annotation = step_annotation(step).strip()
            lines = _format_step(step, self.WIDTH)
            if not annotation:
                self.assertEqual(len(lines), 1, f"{head} {step.chord}")
                continue
            checked += 1
            self.assertEqual(
                " ".join(line[self.COLUMN:] for line in lines).split(),
                annotation.split(),
                f"{head} {step.chord} {step.tab_line()}",
            )
        self.assertGreater(checked, 100, "the sweep stopped rendering anything")

    def test_no_line_runs_past_the_width_unless_a_word_does(self):
        """The width is a preference: a clause is wrapped, a word is never cut in half."""
        from arranger.render import _format_step

        for head, step in self.rendered_steps():
            for line in _format_step(step, self.WIDTH):
                if len(line) <= self.WIDTH:
                    continue
                room = self.WIDTH - self.COLUMN
                self.assertTrue(
                    any(len(word) > room for word in line[self.COLUMN:].split()),
                    f"{head} {step.chord}: {len(line)} columns in {line!r}",
                )

    def test_the_columns_are_on_the_step_line_and_nowhere_else(self):
        """A continuation line carries the explanation alone, so its fields are blank."""
        from arranger.render import _format_step

        for head, step in self.rendered_steps():
            for line in _format_step(step, self.WIDTH)[1:]:
                self.assertEqual(
                    line[: self.COLUMN],
                    " " * self.COLUMN,
                    f"{head} {step.chord} {step.tab_line()}",
                )

    def test_the_number_of_steps_that_wrap(self):
        """A count, because a step that stops wrapping is silent.

        Measured over this sweep: **82** of the steps it renders carry an explanation too
        long for the width, so each of them continues below the step. A clause that stopped
        being printed, or a width that stopped being honoured, would move this number.

        The count is a function of the width and the clauses, and two things set it: the
        union's gate reading the **selection** (`targets` does not comp a position before
        the waltz's first note, so that note is harmonised rather than read as a repeat of
        the comping shape) and the comping palette's string set - the waltz's comping shape
        left the G-B-E set for `x-6-5-5-x-x` on the A, D and G strings, which states
        `G 3, Bb 5 & C 6` where the G-B-E set stated `Eb Root, G 3 & C 6`, three
        characters shorter. Three characters is the whole of the difference at this width.
        """
        from arranger.render import _format_step

        wrapped = sum(
            len(_format_step(step, self.WIDTH)) > 1 for _head, step in self.rendered_steps()
        )
        self.assertEqual(wrapped, 82, "the number of steps that wrap moved")


class TestOneLineColumns(unittest.TestCase):
    """The compact line's four columns: chord, melody, degree, tab - then annotation.

    Two guarantees. The **tab column is fixed**, so shapes line up down the page: the
    annotation, whose length varies, trails the line instead of sitting between the
    melody and the tab, where it used to push every annotated shape out of line. And
    the **degree column** names the melody's chord tone - or, for a note outside the
    chord, the tension it spells - immediately after the melody note.
    """

    def build(self, progression):
        return format_progression(VoiceLeadingEngine.arrange_progression(progression))

    def test_every_tab_starts_in_the_same_column(self):
        """An annotation, however long, cannot move the shape.

        The cells stay hyphen-joined and ragged - `x-11-x` is wider than `x-x-x` - so
        it is the *field* that is fixed: the tab begins at column 18 on every line,
        whatever width the shape itself is. The step's **first** line is the one checked,
        since a continuation line carries the explanation alone.
        """
        rendered = self.build(
            [("D4", "7", "D7"), ("Eb4", "7", "D7"), ("D4", "7", "D7")]
        )
        for block in _blocks(rendered):
            self.assertRegex(block[0][_TAB_FIELD].strip(), r"^[x0-9]+(-[x0-9]+){5}$")

    def test_every_annotation_starts_in_the_same_column(self):
        """The explanation trails a padded field, so it begins in one column.

        Two shapes of different widths - `x-x-x-9-10-8` against `x-x-11-9-11-11` -
        would otherwise start their explanations wherever each shape happened to end.
        """
        from arranger.render import _format_step

        blocks = [
            _format_step(
                ArrangementStep(
                    chord="Dm7", melody="A4", original_melody="A5",
                    voicing=make_voicing(frets),
                )
            )
            for frets in ([-1, -1, -1, 9, 10, 8], [-1, -1, 11, 9, 11, 11])
        ]
        for block in blocks:
            self.assertIn("transposed down an octave from A5", block[0])
        self.assertEqual(len({block[0].index("(") for block in blocks}), 1, blocks)

    def test_the_degree_column_names_the_melody_note(self):
        rendered = self.build([("G4", "maj7", "Ebmaj7"), ("D4", "maj7", "Ebmaj7")])
        blocks = _blocks(rendered)
        self.assertEqual(blocks[0][0][_DEGREE_FIELD].strip(), "3")
        self.assertEqual(blocks[1][0][_DEGREE_FIELD].strip(), "7")

    def test_a_tension_is_named_in_the_degree_column(self):
        """`Eb` over `D7` is the b9 the reharmonisation below it names."""
        rendered = self.build([("Eb4", "7", "D7")])
        self.assertEqual(_blocks(rendered)[0][0][_DEGREE_FIELD].strip(), "b9")

    def test_the_annotation_trails_the_tab(self):
        """The explanation is appended after the shape, not between the melody and it."""
        block = _blocks(self.build([("Eb4", "7", "D7")]))[0]
        self.assertLess(_TAB_FIELD.stop, block[0].index("("))

    def test_a_slot_with_no_melody_leaves_the_degree_column_blank(self):
        """A comping slot at a position the tune is silent at has nothing to name."""
        step = ArrangementStep(
            chord="Gmaj9", melody=None, voicing=make_voicing([-1, -1, -1, -1, 7, 7])
        )
        block = _blocks(format_progression([step]))[0]
        self.assertEqual(block[0][_DEGREE_FIELD], "    ")
