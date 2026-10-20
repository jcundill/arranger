"""How long a requested attack rings: a stab lasts its felt beat, a fill its rest.

The chord part is not the melody: it states a harmony to somebody else's ear, so a
position `--chord-on` names is an **attack**, not a note held until the next thing
happens. A stab that rang until the next requested position would still be sounding
over beats nobody asked for, and a fill that rang past its rest would walk into the
returning tune.

`duration` is in whole notes and is a **cap** in the score (`tabscore._capped_span`):
the span between onsets is the default, and a shorter duration leaves the remainder as
a rest. So the rules here are the engine's, and the rest they produce is the score's.

The carried thumb - a bass note ringing while the melody moves - is
`tests/test_bass_hold.py`'s; it is a length expressed by a tie rather than by a
number, because the step it sounds under is somebody else's note.
"""

import os
import unittest

from arranger import Request
from headxml import arrange_xml_head
from tabscore import score_events
from tests.support import harmony, note, rest, score_bars, write_score


def _long_note_score() -> str:
    """A 4/4 head whose melody is one whole note in bar 1 and a rest in bar 2.

    Written by hand rather than taken from the corpus because the bars have to be
    *empty* of melody for the chord part's own positions to be the ones that sound - the
    union keeps the melody's slot wherever the tune has a note, and that slot's length
    is the written note's.
    """
    return score_bars([
        harmony("C", "major") + note("C", 5, duration=16),
        harmony("C", "major") + rest(16),
    ])


class TestAStabLastsItsFeltBeat(unittest.TestCase):
    """`--chord-on` names attacks; each rings to the end of the beat it lands in."""

    def _steps(self, document: str, request: Request, **kwargs):
        path = write_score(document)
        self.addCleanup(os.unlink, path)
        steps, _head, _notes = arrange_xml_head(path, request=request, **kwargs)
        return steps

    def test_four_four_stab_is_a_quarter(self):
        steps = self._steps(_long_note_score(), Request(melody=False, chord_on="2,4"))
        stabs = {step.beat: step.duration for step in steps if step.bar == 1}
        self.assertEqual(stabs[2.0], 0.25)
        self.assertEqual(stabs[4.0], 0.25)

    def test_cut_time_stab_is_a_half_note(self):
        """2/2's felt beat is a half note, so its stab is twice 4/4's.

        The trap `AGENTS.md` records: a bar is `beats_per_bar` beats of `4 / beat_type`
        quarters, so both metres are four quarters long and only the counting differs.
        """
        document = score_bars(
            [harmony("C", "major") + note("C", 5, duration=8)],
            beats=2,
            beat_type=2,
        )
        steps = self._steps(document, Request(melody=False, chord_on="2"))
        stabs = [step.duration for step in steps if step.beat == 2.0]
        self.assertEqual(stabs, [0.5])

    def test_a_compound_pulse_is_the_group(self):
        """12/8's pulse is three eighths, so an attack in it rings out the group."""
        document = score_bars(
            [harmony("C", "major") + note("C", 5, duration=12)],
            beats=12,
            beat_type=8,
        )
        steps = self._steps(document, Request(melody=False, chord_on="2"))
        # `2` is the second *pulse*, which in 12/8 is the fourth eighth of the bar.
        stabs = [step.duration for step in steps if step.beat == 4.0]
        self.assertEqual(stabs, [0.375])

    def test_the_next_attack_caps_the_stab(self):
        """Two attacks inside one beat are two stabs, not one long one."""
        steps = self._steps(_long_note_score(), Request(melody=False, chord_on="2,2&"))
        stabs = {step.beat: step.duration for step in steps if step.bar == 1}
        self.assertEqual(stabs[2.0], 0.125)


class TestTheScoreRestsAfterAStab(unittest.TestCase):
    """`duration` is a cap, so the beats a stab does not fill are written as silence."""

    def test_the_tail_of_the_beat_is_a_rest(self):
        path = write_score(_long_note_score())
        self.addCleanup(os.unlink, path)
        steps, _head, _notes = arrange_xml_head(
            path, request=Request(melody=False, chord_on="2,4"), section=(1, 2)
        )
        events, _pickup = score_events(steps, 4, True, 4)
        # bar 1: a rest where the tune is silent, the stab on beat 2, the silence it
        # leaves, then the stab on beat 4 running to the bar line.
        self.assertEqual(
            [(step is None, round(length, 6)) for step, _strikes, length in events],
            [(False, 1.0), (False, 1.0), (True, 1.0), (False, 1.0)],
        )


class TestAFillStopsAtTheRestsEnd(unittest.TestCase):
    """A fill is a rest-relative policy, so its length is the rest's, not a rhythm's."""

    def _fills(self, fills: str):
        body = [
            harmony("C", "major") + note("C", 5, duration=16),
            harmony("C", "major") + rest(16),
            harmony("C", "major") + note("D", 5, duration=16),
        ]
        path = write_score(score_bars(body))
        self.addCleanup(os.unlink, path)
        steps, _head, _notes = arrange_xml_head(
            path, request=Request(chord_on="none", chord_fills=fills), section=(2, 3)
        )
        return steps

    def test_a_hold_fills_the_rest(self):
        steps = self._fills("hold")
        self.assertEqual([step.duration for step in steps], [1.0])

    def test_a_comp_attacks_each_felt_beat(self):
        steps = self._fills("comp")
        self.assertEqual([step.beat for step in steps], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual([step.duration for step in steps], [0.25] * 4)

    def test_no_fill_rings_past_the_rest(self):
        """The last attack ends at the bar line, where the tune returns."""
        steps = self._fills("comp")
        last = max(
            (step.beat or 0.0) + (step.duration or 0.0) * 4 for step in steps
        )
        self.assertAlmostEqual(last, 5.0)


if __name__ == "__main__":
    unittest.main()
