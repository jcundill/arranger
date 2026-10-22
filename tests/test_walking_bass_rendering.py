"""The walking bass as the renderers draw it: one strike held, the thumb moving.

The regression that matters most is the **collapse** one, because it is silent:
`_staff_columns` decides hold-versus-strike from the sounding pitches, a thumb line
changes the lowest of them every quarter, and nothing raises when the hold chain breaks -
the arrangement just becomes the chord list the collapse behaviour exists to prevent. So
the first test asserts the chain survives rather than what it looks like, and the rest
hold the three renderer families to it.
"""

from __future__ import annotations

import re
import unittest
from typing import List

from arranger import (
    BASS_STRING_INDICES,
    BASS_STYLE_WALK,
    ROLE_TARGET,
    ArrangementStep,
    ArrangeOptions,
    VoiceLeadingEngine,
    format_progression,
    format_tab_html,
    format_tab_staff,
)

# The precedence rule `bass._melody_in_force` implements. Imported from where it
# lives rather than through the package facade, because these are private to
# `arranger.bass` and re-exporting them would put four internals into the public
# surface for the benefit of one test file. `test_bass.py` covers them directly for
# the same reason.
from arranger.annotation import step_annotation
from tabgp import _sounding_frets
from tabstaff import _strikes_here
from tests.support import (
    MINOR_CADENCE,
    bass_name,
    bass_string,
    make_voicing,
    upper_pitches,
    walk,
)

# A staff string row, as opposed to the chord-name or melody line above it. Anchored
# on the label and the barline the renderer puts right after it (`e*|`, `B |`, ...),
# which is what separates it from a chord row: a chord called "Dm7" also starts with
# a `D`, so matching on the letter alone picks up the wrong line.
#
# Both cases of the high E are in the class because the renderer prints it either way:
# the top row is labelled lowercase `e` (the usual tab convention, so the two E rows
# stay distinct) while the bottom row keeps the uppercase `E` of `STRING_NAMES`.
_STRING_ROW = re.compile(r"^[eBGDAE][* ]?\|")


class TestWalkingBassRendering(unittest.TestCase):
    """The three renderer families draw a walking line rather than a chord list.

    The regression that matters most is the **collapse** one, because it is silent:
    `_staff_columns` decides hold-versus-strike from the sounding pitches, a thumb
    line changes the lowest of them every quarter, and nothing raises when the hold
    chain breaks - the arrangement just silently becomes the chord list the 0.7.0
    collapse behaviour exists to prevent. So the first test asserts the chain
    *survives* rather than asserting what it looks like.
    """

    def setUp(self):
        # The plan's own worked example, bar 1: one melody slot - a whole note - over
        # one chord, which the union turns into four steps. Chosen because it is the
        # case every rule here exists for: a held melody with a moving thumb.
        self.steps = walk([("F5", "maj7", "Fmaj7")], [(0, 1.0)])
        self.staff = format_tab_staff(self.steps, show_melody=True)

    def sounded(self, step: ArrangementStep) -> List[int]:
        """The string indices a renderer strikes, via the shared predicate.

        Deliberately the helper rather than the drawn cells: the ASCII staff and the
        HTML cell both call `_strikes_here`, so asserting on it states the rule once
        rather than twice - and `test_the_ascii_staff_draws_that` below is the half
        that checks the drawing actually follows it.
        """
        return [
            index for index in range(6)
            if _strikes_here(step, index) and step.voicing.frets[index] >= 0
        ]

    def test_a_walking_line_does_not_break_the_hold_chain(self):
        """
        The collapse regression, and the reason the fix is mandatory.

        The upper shape is struck once and held while the thumb walks, so only the
        first of the four steps may strike a string above the thumb. Comparing the
        full pitch set in `_staff_columns` would mark all four a strike.
        """
        self.assertEqual(len(self.steps), 4)
        above = [
            [index for index in self.sounded(step)
             if index != step.voicing.bass_string]
            for step in self.steps
        ]
        self.assertEqual(above[0], sorted(above[0]), "the first step is not a shell")
        self.assertGreater(len(above[0]), 1, "the first step strikes no upper voice")
        for index, struck in enumerate(above[1:], start=1):
            self.assertEqual(
                struck, [], f"step {index} re-struck the shape above the thumb"
            )

    def test_every_step_strikes_exactly_the_thumb_after_the_first(self):
        """
        The `bass_only` cell behaviour: the three slots the union invented draw **no**
        fret above the thumb, because the shape struck on beat 1 is still ringing.

        The opposite rule to `repeated`, which mutes the strings it does not strike and
        keeps the soprano, so this is asserted as the *absence* of upper frets rather
        than as a particular one - which is also what catches a fill silently reverting
        to a duo.
        """
        for step in self.steps[1:]:
            self.assertTrue(step.bass_only)
            self.assertEqual(self.sounded(step), [bass_string(step)])

    def fretted_cells(self, row: str) -> List[str]:
        """The fret numbers drawn in one string row, one per non-empty cell.

        Read off the row's own fixed-width cells rather than by counting digits: a
        two-digit fret like `13` is two digits, and counting characters is how a test
        of this kind comes to disagree with the drawing for no musical reason. The
        cells are `width` characters wide and separated by a single `-`, which is what
        `format_tab_staff` writes between columns.
        """
        # Past the label, the melody marker and the opening barline.
        body = row[3:]
        cells, current = [], ""
        for char in body:
            if char == "-":
                if current:
                    cells.append(current)
                current = ""
            elif char != "|":
                current += char
        if current:
            cells.append(current)
        return [cell.strip() for cell in cells if cell.strip()]

    def test_the_ascii_staff_draws_one_strike_and_a_moving_thumb(self):
        """
        The drawing, read off the rendered staff rather than off the predicate.

        The melody's string carries exactly one fret in the whole bar - the collapse
        fix, in one number - and the thumb's carries one per column. Together those
        are the held shape and the walking line.
        """
        rows = [line for line in self.staff.splitlines() if _STRING_ROW.match(line)]
        self.assertEqual(len(rows), 6, f"could not read the string rows: {self.staff!r}")
        melody_row = rows[5 - self.steps[0].voicing.soprano_string()]
        self.assertEqual(
            self.fretted_cells(melody_row), ["13"],
            f"the held shape was re-struck: {melody_row!r}",
        )
        # The thumb **per column**, not on one row: it follows the hand, so it may sit
        # on a different string on beat 1 from the one it walks on. Reading a single
        # row would assert a fixed string, which is the one thing the placement rule
        # explicitly does not do.
        drawn = [
            self.fretted_cells(rows[5 - bass_string(step)])
            for step in self.steps
        ]
        for step, frets in zip(self.steps, drawn):
            self.assertTrue(
                frets, f"beat {step.beat} drew no thumb note: {rows[5 - bass_string(step)]!r}"
            )

    def test_the_thumb_reaches_every_walked_beat(self):
        """No walked beat is silent: each carries a placed thumb note."""
        for step in self.steps:
            self.assertIsNotNone(step.bass, "a walked beat has no bass")
            self.assertIsNotNone(step.voicing.bass_string)
            self.assertGreaterEqual(step.voicing.frets[bass_string(step)], 0)

    def test_the_thumb_may_change_string_between_beats(self):
        """
        The thumb follows the hand, so it is not pinned to one string, and the
        renderers read `bass_string` per step rather than assuming index 0.

        Not an assertion that a particular string is chosen - the placement rule is
        `test_walking_bass.py`'s to own - but that no renderer may assume it.
        """
        for step in self.steps:
            self.assertIn(step.voicing.bass_string, BASS_STRING_INDICES)

    def test_a_repeated_melody_still_strikes_the_thumb(self):
        """
        The one case where the two partial-attack rules meet.

        `repeated` holds the inner voices and `bass_only` holds everything above the
        thumb, so a step that is both must play the soprano **and** the bass and hold
        only what is between. Written as a hand-built step rather than an arrangement,
        because reaching it through the engine needs a melody that repeats under one
        harmony *and* a bass grid finer than the melody's - and the defect it guards
        against is in the renderers, not in how that state is produced.
        """
        voicing = make_voicing([8, 10, 9, 10, 10, 13], bass_midi=41, bass_string=0)
        step = ArrangementStep(
            chord="Fmaj7", melody="F5", voicing=voicing, repeated=True,
            bass_role="connect",
        )
        self.assertEqual(
            [index for index in range(6) if _strikes_here(step, index)],
            [0, 5],
            "the thumb or the soprano went missing from a repeated+walking step",
        )
        # The same rule in the GP5 renderer's terms: the thumb is a moving voice, so a
        # repeated melody must not delete it.
        self.assertEqual(
            sorted(index for index, _fret in _sounding_frets(step)), [0, 5]
        )

    def test_the_annotation_names_the_bass_and_its_role(self):
        """
        The role is printed because the thumb is no longer uniformly chord tones, so a
        reader counting strings would wonder why the bass is not playing the chord.

        The connect note on the fill is `E2`, not `E3`: the hand is at the open position
        there, and `E3` is the low E at fret 12 - twelve frets from the fingers, which no
        hand reaches (`fingers.MAX_HAND_SPAN`). The line takes the octave it can play, and
        the pitch class is the same one the walk asked for.
        """
        rendered = format_progression(self.steps)
        self.assertIn("(bass: F3, anchor)", rendered)
        self.assertIn("(bass: E2, connect)", rendered)
        self.assertNotIn("(bass: E3, connect)", rendered)

    def test_the_bass_annotates_a_partial_shell_as_well_as_a_plain_one(self):
        """
        Every early return out of `step_annotation` has to carry the bass.

        A walking step can equally be a partial shell, a melody-alone fill or a
        repeated melody, and a bass annotated on some of those and not the others is a
        worse defect than no annotation at all. The shell and its own `partial` text
        must both survive.
        """
        shell = self.steps[0]
        annotation = step_annotation(shell)
        self.assertIn("partial", annotation)
        self.assertIn("(bass: F3, anchor)", annotation)

    def test_an_unchanged_texture_renders_identically(self):
        """
        The backward-compatibility claim of this phase, on the renderers themselves.

        Every change here is behind `step.bass`, `step.bass_only` or
        `voicing.bass_string`, so a step carrying none must render exactly as before -
        which is what keeps `uniform` and `targets` byte-identical.
        """

        steps = VoiceLeadingEngine.arrange_progression(MINOR_CADENCE)
        rendered = format_progression(steps)
        # The tab and the chord/melody/degree columns are the ones this renderer always
        # produced; the trailing harmony annotation is added to every chord tone, and
        # this step's is not a bass note.
        self.assertIn("Dm7      D5  Root x-x-10-10-10-10", rendered.splitlines()[0])
        self.assertNotIn("(bass:", rendered)
        self.assertNotIn("bass:", format_tab_html(steps))

    """How far the walk reaches: the metre's own layout, and a stated absence of one."""

    def test_the_metres_layout_gives_the_walk_four_quarters(self):
        """A hand-built progression is laid out on the felt beats, so the walk places four.

        Two chords in 4/4 make one bar of four positions, and the thumb walks them: an
        anchor on each chord and a connection between. The degradation in the next test is
        for a caller who *states* no positions, which is a different request.
        """
        steps = walk([("F5", "maj7", "Fmaj7"), ("G4", "maj7", "Gmaj7")])
        self.assertEqual(
            [(step.bar, step.beat) for step in steps],
            [(1, 1.0), (1, 2.0), (1, 3.0), (1, 4.0)],
        )
        self.assertEqual(
            [step.bass_role for step in steps], ["anchor", "connect", "anchor", "connect"]
        )
        self.assertEqual([bass_name(step) for step in steps], ["F", "F#", "G", "F#"])

    def test_an_unplaced_timeline_degrades_to_one_note_per_slot(self):
        """`(None, None, None)` gives nothing to place four quarters on, so it anchors.

        This is the path a caller takes who knows a position is *not* on the metre - and
        it is worth a test of its own, because a silent degradation here would read as
        "the feature does nothing" rather than as a documented limit of the grid.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("F5", "maj7", "Fmaj7"), ("G4", "maj7", "Gmaj7")],
            timings=[(None, None, None)] * 2,
            options=ArrangeOptions(texture="targets", bass=BASS_STYLE_WALK),
        )
        self.assertEqual(len(steps), 2)
        self.assertEqual([step.bass_role for step in steps], ["anchor", "anchor"])
        self.assertEqual([bass_name(step) for step in steps], ["F", "G"])

    def test_the_upper_voices_are_still_there_on_a_single_note(self):
        """
        The degradation costs the walk, not the arrangement: one position on a strong beat
        is a target, so it is a shell as it always would be.
        """
        steps = walk([("F5", "maj7", "Fmaj7")])
        self.assertEqual(steps[0].role, ROLE_TARGET)
        self.assertEqual(steps[0].voicing.grip, "shell")
        self.assertEqual(len(upper_pitches(steps[0])), 3)
