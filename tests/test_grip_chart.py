"""Tests for `grip_chart`, the drop-2 chart generator and auditor.

The generator exists because `common_grips.md` was written by hand and its fret
numbers disagreed with its own inversion labels. These tests pin the two things
that must not regress:

* the **labels**, which are derived from the pitches rather than written down - in
  particular that an inversion is named by the bass, which is the mistake the old
  chart made on every row;
* the **audit**, which has to be able to *find* a bad chart. An auditor that
  reports nothing is indistinguishable from one that does not work, so the
  hand-written defects are pinned as fixtures and asserted to be caught.

`grip_chart` is a development tool and imports nothing from the library that the
tests do not already exercise, so no guard is needed here.
"""

import unittest

import grip_chart
from arranger import ChordParser, VoiceLeadingEngine, Voicing

# A minimal chart in the hand-written style: a heading, a label line, and one tab
# line per string with a column per inversion. `E` is the high E, as it is at the
# top of a 4-3-2-1 block.
CHART = """### Cmaj7

   Root Pos       1st Inv        2nd Inv        3rd Inv
E|----7----|   |----8----|   |----12---|   |----3----|
B|----5----|   |----8----|   |----12---|   |----1----|
G|----5----|   |----9----|   |----12---|   |----4----|
D|----5----|   |----7----|   |----10---|   |----2----|
"""


def _voicing(frets):
    active = [f for f in frets if f >= 0]
    return Voicing(list(frets), max(active), sum(active) / len(active))


class TestLabels(unittest.TestCase):
    """The inversion is named by the bass, never by the melody."""

    def test_the_inversion_comes_from_the_lowest_voice(self):
        cell = grip_chart.Cell(
            quality="maj7",
            top_degree=11,                       # the melody is the 7th...
            melody_midi=71,
            voicing=_voicing([-1, -1, 5, 5, 5, 7]),   # ...and the bass is G
            root_pc=0,
        )
        # The melody being the 7th must not make this a "3rd inversion": the
        # lowest sounding voice is the 5th, so it is a 2nd inversion.
        self.assertEqual(cell.bass_degree, 7)
        self.assertEqual(cell.inversion, "2nd Inv")

    def test_every_generated_shape_names_an_inversion_from_its_bass(self):
        for quality in grip_chart.DEFAULT_QUALITIES:
            for soprano in (5, 4):
                for cell in grip_chart.cells_for(quality, soprano):
                    if cell is None:
                        continue
                    self.assertIn(
                        cell.bass_degree,
                        grip_chart.INVERSION_NAMES,
                        f"{quality} on string {soprano}: {cell.tab}",
                    )

    def test_top_degree_and_inversion_are_independent(self):
        """The same bass is reachable under different melodies, and vice versa."""
        pairs = set()
        for quality in grip_chart.DEFAULT_QUALITIES:
            for cell in grip_chart.cells_for(quality, 5):
                if cell is not None:
                    pairs.add((cell.bass_degree, cell.top_degree))
        self.assertGreater(len({bass for bass, _ in pairs}), 1)


class TestGeneratedChart(unittest.TestCase):
    """What the generator emits."""

    def test_every_shape_comes_from_the_engine(self):
        for quality in grip_chart.DEFAULT_QUALITIES:
            for soprano in (5, 4):
                for cell in grip_chart.cells_for(quality, soprano):
                    if cell is None:
                        continue
                    # Position-independent: the shape must be one of the engine's
                    # own templates for the melody's degree.
                    self.assertTrue(
                        grip_chart._engine_has_shape(
                            quality, cell.melody_midi, cell.voicing.frets
                        ),
                        f"{quality} {cell.tab}",
                    )

    def test_every_sounding_pitch_is_a_chord_tone(self):
        """No shape in the chart may sound a note the chord does not contain.

        This is the property the hand-written chart broke: one of its cells held
        an A under a Cmaj7 heading. Tones are compared relative to the cell's own
        root, so the test is `(pitch - root) % 12` against the quality's relative
        tone set - the same table the engine steers by.
        """
        for quality in grip_chart.DEFAULT_QUALITIES:
            tones = {t % 12 for t in ChordParser.get_chord_tones(quality)}
            for soprano in (5, 4):
                for cell in grip_chart.cells_for(quality, soprano):
                    if cell is None:
                        continue
                    for midi in cell.voicing.midi_notes():
                        self.assertIn(
                            (midi - cell.root_pc) % 12,
                            tones,
                            f"{quality} on string {soprano}: {cell.tab} "
                            f"sounds a pitch the chord does not contain",
                        )


class TestAuditFindsRealDefects(unittest.TestCase):
    """An auditor that reports nothing is indistinguishable from a broken one."""

    def test_a_mislabelled_inversion_is_caught(self):
        problems = grip_chart.audit(CHART)
        self.assertTrue(
            any("named by the bass" in p for p in problems),
            f"expected a mislabelled inversion, got {problems}",
        )

    def test_a_note_outside_the_chord_is_caught(self):
        # 8-8-9-7 under Cmaj7 sounds an A, which is not in the chord.
        problems = grip_chart.audit(CHART)
        self.assertTrue(
            any("not in maj7" in p for p in problems),
            f"expected a foreign tone to be reported, got {problems}",
        )

    def test_the_melody_row_is_not_silently_dropped(self):
        """The chart's top line carries a trailing "<-- Melody" annotation.

        A parser that rejected that line would lose the melody - the one row that
        says what the shape is - and quietly audit three strings instead of four.
        """
        cells = grip_chart.parse_chart(CHART)
        self.assertTrue(cells)
        for cell in cells:
            self.assertEqual(
                sum(1 for f in cell.frets if f >= 0), 4, f"{cell.where}: {cell.tab}"
            )

    def test_an_unlabelled_chart_reports_rather_than_guessing(self):
        """A block with no chord heading is reported, not assumed to be a chord."""
        problems = grip_chart.audit("E|----7----|\nB|----5----|\n")
        self.assertTrue(any("cannot tell which chord" in p for p in problems))

    def test_a_correct_chart_reports_nothing(self):
        self.assertEqual(grip_chart.audit(grip_chart.render_markdown()), [])


class TestParsing(unittest.TestCase):
    def test_four_columns_produce_four_cells(self):
        self.assertEqual(len(grip_chart.parse_chart(CHART)), 4)

    def test_each_column_inherits_its_own_label(self):
        """Positional: column n of an n-column run is the nth inversion."""
        self.assertEqual(
            [c.claim for c in grip_chart.parse_chart(CHART)], [0, 3, 7, 10]
        )

    def test_claims_are_read_from_the_words(self):
        self.assertEqual(grip_chart._claim_word("Root Pos"), 0)
        self.assertEqual(grip_chart._claim_word("2nd Inv"), 7)
        self.assertIsNone(grip_chart._claim_word("melody"))


class TestHelpers(unittest.TestCase):
    def test_spell_round_trips_through_musthe(self):
        from musthe import Note

        for midi in (60, 64, 71, 76):
            self.assertEqual(Note(grip_chart.spell(midi)).midi_note(), midi)

    def test_degree_names_cover_every_chord_tone_the_engine_voices(self):
        """A degree with no name would render as "degree N" in the chart."""
        for quality in grip_chart.DEFAULT_QUALITIES:
            for degree in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT[quality]:
                self.assertIn(degree % 12, grip_chart.DEGREE_NAMES, quality)


if __name__ == "__main__":
    unittest.main()
