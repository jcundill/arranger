"""Tests for the comp line: the band, the walk, the approach, the opening, the fill.

The **acceptance example** is `docs/history/comp-line.md`'s four bars of 4/4 - `Dm7 | G13 |
Cmaj7 | C6`, four attacks a bar - whose tops and tabs are pinned here. It is the
figure every rule in the module was tuned against, so it is the one test that has to
move when a rule does.
"""

from __future__ import annotations

import unittest

from arranger import Request, comp_line
from arranger.comp_line import FillTarget, LineShape, LineState
from arranger.steps import arrange_progression
from headxml import arrange_xml_head

#: The four-bar example's tops, bar by bar, exactly as `docs/history/comp-line.md` states them.
FOUR_BARS = [60, 62, 65, 62, 64, 65, 67, 64, 67, 60, 59, 60, 64, 67, 69, 64]

#: The same example's tabs, in order. Pinned rather than snapshotted: they are the
#: acceptance gate, and a snapshot would let a regression regenerate itself.
#:
#: Every one of them states its voices on **neighbouring strings, inside four frets, with
#: no pitch twice**: `grip_tables.COMPING_MAX_SPAN` for the reach,
#: `grip_tables._fills_its_strings` for the skip a comping shape is never allowed to make,
#: and `grip_place.sounds_distinct_pitches` for the unison - which is why bar 4's two `E4`
#: columns are `x-x-7-5-5-x` rather than `x-x-7-9-5-x`, a shape that sounded `E4` on two
#: strings and left the root out. Ten of the sixteen are spelled differently from the
#: first measurement of this example (which `docs/history/comp-line.md` keeps): nine muted
#: a string between two sounding ones - `8-x-3-7-x-x`, the `x-6-x-5-9-x` family - and one
#: reached a fifth fret on adjacent strings. **The tops are unchanged**, which is what makes
#: it the same line; the rules and what they cost are `docs/engine.md` §"`get_comping_voicings`:
#: a chord with no melody on top".
FOUR_BAR_TABS = [
    "x-8-7-5-x-x", "x-8-10-7-x-x", "x-x-7-5-6-x", "x-8-10-7-x-x",
    "x-x-9-7-5-x", "x-x-9-9-6-x", "x-x-9-9-8-x", "x-x-9-7-5-x",
    "x-x-9-9-8-x", "x-7-9-5-x-x", "x-7-5-4-x-x", "x-7-9-5-x-x",
    "x-x-7-5-5-x", "x-x-7-9-8-x", "x-x-7-9-10-x", "x-x-7-5-5-x",
]


def _four_bars():
    """The example as the engine sees it: one slot per attack, one chord per bar.

    The importer emits a comp as **one progression entry per grid position** with
    ``None`` as the melody, which is what makes the last position of a bar the last
    one before the change. Built here the same way rather than through a fixture, so
    the test does not depend on a head's chord rhythm.
    """
    names = ["Dm7", "G13", "Cmaj7", "C6"]
    progression = []
    timings = []
    for bar, name in enumerate(names, start=1):
        for beat in (1.0, 2.0, 3.0, 4.0):
            progression.append((None, name))
            timings.append((bar, beat, 1.0))
    return arrange_progression(
        progression, timings=timings, request=Request(melody=False)
    )


class TestHomeBand(unittest.TestCase):
    def test_shipped_window(self) -> None:
        self.assertEqual(comp_line.home_band(2, 13), (3, 10))

    def test_clamped(self) -> None:
        self.assertEqual(comp_line.home_band(10, 13), (11, 13))


class TestWalk(unittest.TestCase):
    def test_walks_up(self) -> None:
        tone, direction = comp_line.walk_step(60, 1, [58, 62, 64], [])
        self.assertEqual(tone, 62)
        self.assertEqual(direction, 1)

    def test_no_retrace(self) -> None:
        tone, _ = comp_line.walk_step(62, 1, [60, 62, 64], [60, 62])
        self.assertEqual(tone, 64)

    def test_reverses_at_the_bands_edge(self) -> None:
        """Nothing above the top, so the walk turns - the bar-3 move of the example.

        `60` is a jump rather than a step: the two tones nearer the edge (`64`, `67`)
        are both in the no-retrace window, which is what makes the fall a fall instead
        of a bounce.
        """
        tone, direction = comp_line.walk_step(67, 1, [59, 60, 64, 67], [64, 67])
        self.assertEqual((tone, direction), (60, -1))


class TestApproach(unittest.TestCase):
    def test_a_shared_tone_is_the_pivot(self) -> None:
        """`Dm7 -> G13`: a 3rd below the previous top, and both chords state it."""
        self.assertEqual(
            comp_line.approach_tone(65, [60, 62, 65, 69], [59, 62, 64, 65, 67, 69]),
            62,
        )

    def test_it_never_repeats_the_previous_top(self) -> None:
        """`G13 -> Cmaj7`, whose shared tones are `G`, `B` and `E`: `G` is refused."""
        self.assertEqual(
            comp_line.approach_tone(67, [59, 62, 64, 65, 67, 69], [59, 60, 64, 67]),
            64,
        )

    def test_no_shared_tone_falls_back_to_the_landing(self) -> None:
        """`Dm7 -> C6` shares no tone, so the nearest next-chord tone is the target."""
        self.assertEqual(
            comp_line.approach_tone(65, [60, 62, 65], [60, 64, 67, 69]), 60
        )

    def test_the_landing_is_read_on_pitch_classes(self) -> None:
        """A tone set, not a pitch list: the octave is the palette's business."""
        self.assertEqual(comp_line.landing_tone([0, 4, 7, 11], 65), 64)


class TestOpening(unittest.TestCase):
    def test_nearest_the_band_s_middle(self) -> None:
        shapes = [LineShape(60, 6.67, True), LineShape(65, 4.0, True)]
        self.assertEqual(comp_line.opening_no_melody(shapes, (3, 10)), 60)

    def test_the_register_decides_and_not_the_pitch(self) -> None:
        """A low tone placed low loses to a higher tone placed nearer the middle."""
        shapes = [LineShape(60, 13.0, True), LineShape(67, 6.0, True)]
        self.assertEqual(comp_line.opening_no_melody(shapes, (3, 10)), 67)


class TestInterpolate(unittest.TestCase):
    def test_endpoints(self) -> None:
        path = comp_line.interpolate(8.0, 3.0, 4)
        self.assertEqual((path[0], path[-1]), (8.0, 3.0))
        self.assertEqual(len(path), 4)

    def test_one_position_is_the_target(self) -> None:
        self.assertEqual(comp_line.interpolate(8.0, 3.0, 1), [3.0])


class TestFillRun(unittest.TestCase):
    def test_it_reads_the_run_of_melody_less_positions(self) -> None:
        progression = [
            ("C4", "Cmaj7"), (None, "Am7"), (None, "D9"), ("D4", "Gmaj9"),
        ]
        self.assertEqual(comp_line.fill_run(progression, 1), (0, 2))
        self.assertEqual(comp_line.fill_run(progression, 2), (1, 2))

    def test_a_single_position_is_its_own_run(self) -> None:
        progression = [("C4", "Cmaj7"), (None, "D9"), ("D4", "Gmaj9")]
        self.assertEqual(comp_line.fill_run(progression, 1), (0, 1))


class TestTheFourBarExample(unittest.TestCase):
    """`docs/history/comp-line.md` §"The four-bar example", in the engine's own output."""

    def test_the_tops_are_the_documented_line(self) -> None:
        steps = _four_bars()
        self.assertEqual(
            [max(step.voicing.midi_notes()) for step in steps], FOUR_BARS
        )

    def test_the_tabs_are_the_documented_shapes(self) -> None:
        tabs = [step.voicing.tab_string() for step in _four_bars()]
        self.assertEqual(tabs, FOUR_BAR_TABS)

    def test_every_position_states_its_chord(self) -> None:
        """No step loses its chord, and no shape leaves the playable span."""
        steps = _four_bars()
        self.assertEqual(len(steps), 16)
        for step in steps:
            self.assertTrue(step.voicing.active_frets(), step.tab_line())
            self.assertLessEqual(step.voicing.fret_span(), 5, step.tab_line())

    def test_the_roles_are_the_rule_that_produced_each_move(self) -> None:
        roles = [step.top_role for step in _four_bars()]
        self.assertEqual(
            roles[:4], ["opening", "walk up", "walk up", "approach from below"]
        )
        self.assertEqual(
            roles[4:8], ["walk up", "walk up", "walk up", "approach from below"]
        )
        self.assertEqual(
            roles[8:12], ["walk up", "walk down", "walk down", "approach from below"]
        )
        self.assertEqual(
            roles[12:], ["walk up", "walk up", "walk up", "walk down"]
        )

    def test_the_hand_stays_in_the_band(self) -> None:
        """The comp's register, for every position of the example."""
        band = comp_line.home_band(2, 13)
        for step in _four_bars():
            for fret in step.voicing.active_frets():
                self.assertTrue(band[0] <= fret <= band[1], step.tab_line())


class TestTheFill(unittest.TestCase):
    """The fill bridges the register it was handed and the tune's own - both ways."""

    def test_the_documented_run_descends_into_the_tune(self) -> None:
        steps, _head, _notes = arrange_xml_head(
            "tests/data/synthetic_repeat_slash.musicxml",
            section=(5, 8),
            request=Request(chord_fills="comp"),
        )
        fills = [step for step in steps if step.top_role in ("fill up", "fill down")]
        self.assertEqual(
            [(step.bar, step.beat, step.voicing.tab_string()) for step in fills],
            [(6, 1.5, "x-x-7-5-8-x"), (6, 2.0, "x-3-4-2-x-x")],
        )
        # It opens where the hand already was - the previous top, `G4`, is the shape the
        # fill is nearest to at register 8.0 - and closes at the fret the tune returns on
        # (`D4`, fret 3).
        self.assertEqual(
            [round(step.voicing.avg_fret, 2) for step in fills], [6.67, 3.0]
        )

    @staticmethod
    def _fill(target: float, index: int) -> FillTarget:
        return FillTarget(previous=8.0, target=target, index=index, count=2)

    def test_the_rule_is_symmetric(self) -> None:
        """Climb into a high return, descend into a low one, hold the opening.

        The three directions are the acceptance criterion, so they are asserted
        directly on the rule as well as on the one head that contains two of them.
        """
        shapes = [
            LineShape(57, 1.0, False),
            LineShape(60, 6.67, True),
            LineShape(74, 12.0, False),
        ]
        band = comp_line.home_band(2, 13)
        climbs = comp_line.chosen_top(
            LineState(), shapes, band, fill=self._fill(12.0, 1)
        )
        descends = comp_line.chosen_top(
            LineState(), shapes, band, fill=self._fill(1.0, 1)
        )
        # `index == 0` is the previous register, which is the opening rule.
        opens = comp_line.chosen_top(
            LineState(), shapes, band, fill=self._fill(12.0, 0)
        )
        self.assertEqual([climbs[0], descends[0], opens[0]], [74, 57, 60])

    def test_a_tie_keeps_the_comp_under_the_tune(self) -> None:
        """Equally placed shapes keep the lower top: the chord stays below the tune."""
        shapes = [LineShape(69, 6.67, True), LineShape(60, 6.67, True)]
        filler = FillTarget(previous=8.0, target=6.67, index=0, count=2)
        tone, _role = comp_line.chosen_top(
            LineState(), shapes, (3, 10), fill=filler
        )
        self.assertEqual(tone, 60)




class TestTheRenderersAgree(unittest.TestCase):
    """A top voice that moves inside a bar is four strikes, not one held chord.

    The walking bass forced the same audit, and a comp line is the same problem one
    register up: the four positions of a bar state four *different* shapes, so a
    renderer that compares pitches and folds them into a hold would lose three
    attacks. The four writers are checked where each of them decides: `tabscore`
    places the events (and both `tabstaff` and `tabgp` read it), the staff draws
    the columns, and `tabxml` writes the notes. The Guitar Pro half lives in
    `tests/test_guitarpro.py`, behind the optional-extra guard.
    """

    def test_the_score_places_four_events(self) -> None:
        from tabscore import score_events

        events, _pickup = score_events(_four_bars(), 4, True, 4)
        self.assertEqual(
            len([event for event in events if event[0] is not None]), 16
        )

    def test_the_staff_draws_every_position_as_a_strike(self) -> None:
        from tabstaff_grid import _staff_columns

        columns = _staff_columns(_four_bars(), 4, 4, True)
        # The last entry is the trailing column the staff draws after the final bar;
        # every column that carries a step is a strike.
        played = [column for column in columns if column[1] is not None]
        self.assertEqual(len(played), 16)
        self.assertTrue(all(strikes for _onset, _step, strikes in played))

    def test_the_score_writes_twelve_notes_and_no_tie(self) -> None:
        """Four attacks of three voices in bar 1: twelve notes, none of them tied."""
        import re

        from tabxml import format_musicxml

        document = format_musicxml(_four_bars(), beats_per_bar=4, beat_type=4)
        measures = re.findall(r"<measure[^>]*>(.*?)</measure>", document, re.S)
        pitched = [
            note for note in re.findall(r"<note.*?</note>", measures[0], re.S)
            if "<rest" not in note
        ]
        self.assertEqual(len(pitched), 12)
        self.assertEqual([note for note in pitched if "<tie" in note], [])


if __name__ == "__main__":
    unittest.main()

