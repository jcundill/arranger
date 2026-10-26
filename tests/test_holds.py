"""The `sustain` chord-on token: chord only at sustained melody onsets.

A note running at least one felt beat is harmonised at its onset; a shorter note
stays a single melody note. Positions the figure names (a `1and` stab) are still
honoured. With `--no-melody` the guitar comps but does not sing: the written onsets
and their durations still drive `sustain`, so sustained onsets comp while short ones
rest, just as `chord-on=melody --no-melody` comps to the written onsets.
"""

from __future__ import annotations

import unittest

from arranger import ArrangeOptions, Note, VoiceLeadingEngine
from arranger.grid import parse_rhythm
from arranger.options import Request
from tabstaff import format_tab_staff

_PROGRESSION = (
    ("C5", "Cmaj7"),
    ("D4", "Cmaj7"),
    ("E4", "Cmaj7"),
    ("F4", "Cmaj7"),
)

#: One whole note per slot (4 beats in 4/4): every onset is sustained.
_WHOLE = (
    (1, 1.0, 1.0),
    (1, 2.0, 1.0),
    (1, 3.0, 1.0),
    (1, 4.0, 1.0),
)

#: A long first note, then short eighth-notes: only the first onset is sustained.
_MIXED = (
    (1, 1.0, 1.0),
    (1, 2.0, 0.125),
    (1, 3.0, 0.125),
    (1, 4.0, 0.125),
)


def _arrange(progression=_PROGRESSION, timings=_WHOLE, **kwargs):
    """The library's own front door, with the request passed as one value."""
    return VoiceLeadingEngine.arrange_progression(
        progression, timings=timings, options=ArrangeOptions(**kwargs)
    )


def _sounded(step) -> int:
    """How many strings a step plucks; the tune alone is one."""
    return sum(1 for fret in step.voicing.frets if fret >= 0)


class TestSustainChordsOnlyLongOnsets(unittest.TestCase):
    """`chord-on=sustain` states the chord only where the tune outlasts a beat."""

    def test_every_whole_note_is_harmonised(self):
        """Every note outlasts a beat, so every onset gets a chord (more than one string)."""
        steps = _arrange(request=Request(chord_on="sustain"))
        self.assertEqual(len(steps), 4)
        for step in steps:
            with self.subTest(beat=step.beat):
                self.assertGreater(_sounded(step), 1)

    def test_a_short_note_stays_a_single_note(self):
        """Only the long first note is harmonised; the short eighth-notes sound alone."""
        steps = _arrange(timings=_MIXED, request=Request(chord_on="sustain"))
        self.assertEqual(len(steps), 4)
        self.assertGreater(_sounded(steps[0]), 1)
        for index in (1, 2, 3):
            with self.subTest(index=index):
                self.assertEqual(_sounded(steps[index]), 1)

    def test_melody_is_still_the_top_voice_when_alone(self):
        """A short note sounds alone but the written pitch is still on the soprano."""
        steps = _arrange(timings=_MIXED, request=Request(chord_on="sustain"))
        for index, step in enumerate(steps):
            with self.subTest(index=index):
                self.assertEqual(
                    max(step.voicing.midi_notes()),
                    Note(_PROGRESSION[index][0]).midi_note(),
                )


class TestSustainPositionStab(unittest.TestCase):
    """A position the figure names (such as `1and`) is still attacked."""

    def test_sustain_prints_and_parses_back(self):
        self.assertEqual(str(parse_rhythm("sustain", 4)), "sustain")
        self.assertEqual(str(parse_rhythm("sustain,1and", 4)), "sustain,1and")
        self.assertEqual(str(parse_rhythm("melody,sustain", 4)), "melody")

    def test_sustain_stab_attacks_its_position_without_the_tune(self):
        """`sustain,1and --no-melody` stabs on 1and even though the note there is short.

        A slot at the stab position (beat 1.5) comps because the figure names that
        position, regardless of the note's duration.
        """
        timings = (
            (1, 1.0, 0.125),   # short: not sustained, no stab here -> rest
            (1, 1.5, 0.125),   # short, but on the stab position -> comps
            (1, 2.0, 1.0),     # sustained -> comps
            (1, 3.0, 0.125),   # short: rest
        )
        steps = _arrange(
            timings=timings,
            request=Request(melody=False, chord_on="sustain,1and"),
        )
        self.assertEqual(len(steps), 4)
        self.assertEqual(_sounded(steps[0]), 0)   # short, no stab
        self.assertGreater(_sounded(steps[1]), 1) # stab position comps
        self.assertGreater(_sounded(steps[2]), 1) # sustained comps
        self.assertEqual(_sounded(steps[3]), 0)   # short, no stab


class TestSustainDurationTest(unittest.TestCase):
    """The duration test that decides whether a sustained onset is struck."""

    def test_sustained_onset_comps_without_the_tune(self):
        """`sustain --no-melody` comps at sustained onsets from written durations."""
        steps = _arrange(
            timings=_MIXED,
            request=Request(melody=False, chord_on="sustain"),
        )
        self.assertEqual(len(steps), 4)
        # The first note is a whole note (1.0 * 4 = 4 beats): it comps.
        self.assertGreater(_sounded(steps[0]), 1)
        # The short eighth-notes (0.125 * 4 = 0.5 beat) rest: nothing above the thumb.
        for index in (1, 2, 3):
            with self.subTest(index=index):
                self.assertEqual(_sounded(steps[index]), 0)


class TestSustainRefusals(unittest.TestCase):
    """`sustain` refuses nothing it can measure."""

    def test_sustain_is_accepted_without_the_tune(self):
        """`chord-on=sustain --no-melody` is not refused: written durations still
        exist, so sustained onsets comp just like `chord-on=melody --no-melody`
        comps to the written onsets."""

        # No exception: the request is honoured, not refused.
        _arrange(
            timings=_WHOLE,
            request=Request(melody=False, chord_on="sustain"),
        )
        _arrange(
            timings=_WHOLE,
            request=Request(melody=False, chord_on="sustain,1and"),
        )


class TestSustainShortNotesStrike(unittest.TestCase):
    """`sustain` short melody notes are re-articulated, not held.

    A single plucked note cannot "hold" - if the same pitch sounds again, the
    string is restruck. Without this, consecutive same-pitch short notes in
    `sustain` mode collapse into one long note in the staff renderer.
    """

    def test_same_pitch_short_notes_each_strike(self):
        """Four short C5 eighth-notes each strike, not one long hold."""
        progression = (("C5", "Cmaj7"), ("C5", "Cmaj7"), ("C5", "Cmaj7"), ("C5", "Cmaj7"))
        timings = ((1, 1.0, 0.125), (1, 2.0, 0.125), (1, 3.0, 0.125), (1, 4.0, 0.125))
        steps = VoiceLeadingEngine.arrange_progression(
            progression,
            timings=timings,
            options=ArrangeOptions(request=Request(chord_on="sustain")),
        )
        self.assertEqual(len(steps), 4)
        # Each step is a single-string melody note
        for step in steps:
            self.assertEqual(sum(1 for f in step.voicing.frets if f >= 0), 1)
        # Render with collapse=True (the default): every column strikes
        staff = format_tab_staff(steps, 4, 4)
        # Four separate strike columns, no `~` holds between them
        hold_columns = staff.count("~")
        self.assertEqual(hold_columns, 0, staff)

    def test_same_pitch_short_notes_are_not_held_in_score(self):
        """`tabscore.score_events` marks each single-note step as a strike, not a hold."""
        progression = (("C5", "Cmaj7"), ("C5", "Cmaj7"), ("C5", "Cmaj7"), ("C5", "Cmaj7"))
        timings = ((1, 1.0, 0.125), (1, 2.0, 0.125), (1, 3.0, 0.125), (1, 4.0, 0.125))
        steps = VoiceLeadingEngine.arrange_progression(
            progression,
            timings=timings,
            options=ArrangeOptions(request=Request(chord_on="sustain")),
        )
        from tabscore import score_events

        events, _pickup = score_events(steps, 4, True, 4, None)
        # Every real step is a strike (is_strike=True), none is a hold.
        # Rest events (step is None) are skipped.
        step_events = [(s, strike) for s, strike, _ in events if s is not None]
        self.assertTrue(all(strike for _, strike in step_events), step_events)


class TestSustainShortNotesUnderHeldBass(unittest.TestCase):
    """`sustain` short melody notes over a walking bass re-articulate, not hold.

    When the thumb strikes a bass note and it rings under repeated same-pitch
    melody notes, each melody note re-strikes the soprano while the held thumb
    stays silent. The step must be marked `repeated`; without it the staff
    renderer collapses the repeated strikes into holds and loses the
    re-articulation - bar 18 of "Blue Moon" with `--chord-on sustain
    --bass-on 1,2` was exactly this collapse.
    """

    def test_repeated_melody_over_held_bass_strikes_each_note(self):
        progression = (("C5", "Cmaj7"), ("C5", "Cmaj7"), ("C5", "Cmaj7"), ("C5", "Cmaj7"))
        timings = ((1, 1.0, 0.125), (1, 1.25, 0.125), (1, 1.5, 0.125), (1, 1.75, 0.125))
        steps = VoiceLeadingEngine.arrange_progression(
            progression,
            timings=timings,
            options=ArrangeOptions(request=Request(chord_on="sustain", bass_on="1")),
        )
        self.assertEqual(len(steps), 4)
        # Beat 1.0 strikes the bass; beats 1.25-1.75 hold that same bass.
        self.assertFalse(steps[0].bass_held)
        self.assertFalse(steps[0].repeated)
        for step in steps[1:]:
            with self.subTest(beat=step.beat):
                self.assertTrue(step.bass_held, f"{step.beat}: bass should be held")
                # The melody re-articulates: the step is repeated so the soprano
                # re-strikes while only the held thumb rings.
                self.assertTrue(step.repeated, f"{step.beat}: repeated melody must strike")
        # Render with collapse=True (the default): every column strikes, no holds.
        staff = format_tab_staff(steps, 4, 4)
        self.assertNotIn("~", staff, staff)
