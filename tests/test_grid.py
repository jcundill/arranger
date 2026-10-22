"""The rhythm layer: the lattice a position is counted on, and the metre under it.

`Rhythm` is the request - direct positions in felt beats - and it is tested where it
lives, in `test_rhythm.py`. What is left here is the *unit* the layer counts in and the
one thing a hand-built progression has to know about the metre:

- **the lattice**: `TICKS_PER_BEAT`, a twenty-fourth of a beat, and the note values a
  generated bar may be subdivided at (`grid_resolutions`, read through the metre). The
  unit is `headxml._tick_key`'s and the vocabulary is `headxml._generated_beats`', so a
  metre's table moving is a generated bar of the wrong density.
- **a progression with no timeline**: what it arranges to, with and without the metre's
  own felt beats supplied. The claim is about the **shipped request**, and the class
  below states the boundary rather than the slogan, because a texture that reads the
  metric weight is not inert and never was.
"""

import glob
import unittest
from functools import reduce
from math import gcd
from pathlib import Path
from typing import Dict, List, Tuple

import headxml
from arranger import TICKS_PER_BEAT, grid_resolutions
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

#: The same progression on the metre's own felt beats, four to the bar. Written out
#: rather than computed from a count of beats, because that is what the claim is about:
#: these are the positions the metre gives, not the ones a caller invented.
FELT_BEATS: List[Tuple[int, float, None]] = [
    (1, 1.0, None), (1, 2.0, None), (1, 3.0, None), (1, 4.0, None),
]


class TestAProgressionWithNoTiming(unittest.TestCase):
    """What a hand-built progression arranges to, with and without a timeline.

    A bare `arrange_progression(P)` carries no timings at all, so every slot is
    *unlocated* - which `metric_weight` reports as `-1`, not as a weak beat. The
    shipped request states the full harmonisation under every note, and **that
    selection does not read the weight**, so supplying the metre's felt beats moves
    nothing: byte-identical, which is the claim this class pins.

    **`texture="targets"` is the boundary of the claim, and the second test states
    it.** A target selection reads the weight to decide which beats carry the
    harmony, so a timeline is not decoration there - it is the difference between
    four full chords and chords on the strong beats with fills between. Naming the
    exception is what keeps the first claim from reading as a claim about the metre
    rather than about the selection.
    """

    def test_the_shipped_request_is_byte_identical_with_or_without_a_timeline(self):
        """Asserted through `format_progression`, because the claim is about what a player
        reads rather than about the fields a step happens to carry.
        """
        from arranger import VoiceLeadingEngine, format_progression

        bare = VoiceLeadingEngine.arrange_progression(list(PROGRESSION))
        laid = VoiceLeadingEngine.arrange_progression(
            list(PROGRESSION), timings=FELT_BEATS
        )
        self.assertEqual(format_progression(laid), format_progression(bare))

    def test_a_texture_that_reads_the_metric_weight_is_not_inert(self):
        """The exception, measured rather than argued: `targets` moves the harmony.

        Both arrangements keep their step count - the timeline moves which beats the
        chord *states*, not which positions exist - so the assertion is on the tabs.
        """
        from arranger import VoiceLeadingEngine

        options = ArrangeOptions(texture="targets")
        bare = VoiceLeadingEngine.arrange_progression(list(PROGRESSION), options=options)
        laid = VoiceLeadingEngine.arrange_progression(
            list(PROGRESSION), timings=FELT_BEATS, options=options
        )
        self.assertEqual(len(laid), len(bare))
        self.assertNotEqual(
            [step.tab_line() for step in laid], [step.tab_line() for step in bare]
        )

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

    def test_the_beat_is_twenty_four_ticks(self):
        """The unit a position is counted in: a twenty-fourth of a beat.

        `headxml._tick_key` rounds to it, `grid_resolutions` is expressed in it, and a
        generated bar is subdivided by it - so a change here moves the lattice every
        position in the library is measured against.
        """
        self.assertEqual(TICKS_PER_BEAT, 24)

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
        """Why the unit is a twenty-fourth and not a twelfth: `synthetic_triplets`.

        The coarsest unit holding a head's onsets is the greatest common divisor of its
        onsets in ticks, and this head's is **one tick** - so no coarser unit holds it, and
        the head is what fixes the size of the lattice. Measured rather than reasoned: its
        first bar states two lengths that put an onset five ticks off the beat, beside
        triplet onsets on the four-tick grid.
        """
        coarsest: Dict[str, int] = {}
        for path in HEADS:
            head = headxml.load_musicxml(path, None)
            onsets = [round((note.beat - 1.0) * TICKS_PER_BEAT) for note in head.notes]
            coarsest[Path(path).stem] = reduce(gcd, onsets, 0)
        self.assertEqual(coarsest["synthetic_triplets"], 1, "the lattice head moved")
        self.assertEqual(min(value for value in coarsest.values() if value), 1)

        self.assertEqual(grid_resolutions(16), (24,))

