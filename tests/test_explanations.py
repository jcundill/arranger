"""The standing check: every choice about a voiced note is explained by its line.

AGENTS.md states the invariant - *a step has to account for what it did and for the shape
it did it with* - and this module is what keeps it true. It works from the **step's own
fields**, never from the wording, so the check cannot be satisfied by phrasing: each entry
below is a decision the engine can make, a predicate for "this step is one of those", and a
witness the line must carry.

Three decisions are deliberately exempt, and they are named here rather than left implicit,
because a rule with unnamed exceptions is a rule the next editor deletes:

- a **hold** restates what corrects a *column* (its octave, the chord a substitution
  stated) but not the shape count, which was explained on the step that chose the shape;
- a **melody-alone shape with no palette** gets no neck-window clause: its fret is where the
  melody has to be, not a shape the engine picked from alternatives;
- the **written slash bass** is excluded from the table because its witness cannot be
  written as a predicate over the step alone - whether it sounds *is* the clause's own
  question, and a witness that recomputed it would be the clause agreeing with itself.
  `TestEveryChoiceIsExplained.test_the_slash_bass_clause_is_not_a_tautology` pins it directly.

Adding a decision to the engine means adding its witness here, in the same commit.
"""

from __future__ import annotations

import glob
import unittest
from typing import Any, Callable, Dict, List, Tuple

from musthe import Note

from arranger import PITCH_CLASS_NAMES, ChordParser
from arranger.chords import melody_degree_name
from arranger.render import _omission_clause, _step_annotation
from arranger.tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    SILENCE_GRID,
    SILENCE_NC_COMPING,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    SILENCE_TUNE_SILENT,
    ArrangementStep,
)
from headxml import arrange_xml_head
from tests.support import make_step

#: The committed heads, which between them carry every quality, metre and texture the
#: library can be asked for. `tests/data` is the only corpus there is.
HEADS: List[str] = sorted(
    glob.glob("tests/data/*.mxl") + glob.glob("tests/data/*.musicxml")
)

#: One config per axis, plus the three that combine axes. Bounded deliberately: this is a
#: sweep of every committed head, so each config costs seconds.
CONFIGS: List[Dict[str, Any]] = [
    {},
    {"texture": "chord1"},
    {"texture": "targets"},
    {"parts": "melody"},
    {"parts": "bass"},
    {"parts": "chord"},
    {"parts": "bass,chord"},
    {"bass": "root,5th,approach,nearest", "grid": "melody:every_note,bass:walk"},
    {"grid": "chord:freddie"},
    {"non_chord_tone": "sustain"},
]

#: (what the engine decided, when this step is one of those, what the line must say).
#: A tuple rather than three parallel lists, so the three cannot drift apart - which is the
#: failure mode this module exists to catch.
Witness = Tuple[str, Callable[[ArrangementStep], bool], Callable[[ArrangementStep], bool]]


def _thin(step: ArrangementStep) -> bool:
    """Fewer voices than the right hand has, which is what makes a count worth stating."""
    return len(step.voicing.upper_midi_notes()) < 4


def _line(step: ArrangementStep) -> str:
    return _step_annotation(step)


def _missing_degree_names(step: ArrangementStep) -> List[str]:
    """The chord tones a four-voice shape leaves out, named as the line names them.

    The decision as stated, worked out from the step's **fields**: a shape stating four
    voices, against the chord the part actually states (`harmonized_as` where a substitute
    was found), whose tones are not all among the pitches sounding - the whole step's, so a
    thumb that lands on the root counts as stating it. The routes that answered for the
    shape elsewhere (a hold, a thumb-only slot, a thin `partial` shell, a melody alone, a
    chord no shape could state) are the ones the clause is silent on, so they come back
    empty here too - which is what lets the witness below catch a clause that speaks where
    it should not as well as one that stays quiet where it should speak.
    """
    if (
        step.repeated
        or step.bass_only
        or step.partial
        or step.melody_only
        or step.chord_unvoiced
    ):
        return []
    if len(step.voicing.upper_midi_notes()) != 4:
        return []
    harmony = step.harmonized_as or step.chord
    root_str, quality = ChordParser.parse_chord_name(harmony)
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(
        ChordParser.canonical_quality((quality or "").split("/", 1)[0])
    )
    if not root_str or not tones:
        return []
    root_pc = Note(root_str + "4").midi_note() % 12
    sounding = {pitch % 12 for pitch in step.voicing.midi_notes()}
    return [
        melody_degree_name(Note(f"{PITCH_CLASS_NAMES[(root_pc + tone) % 12]}4"), harmony)
        for tone in tones
        if (root_pc + tone) % 12 not in sounding
    ]


def _names_left_out_on_the_line(step: ArrangementStep) -> List[str]:
    """The tones a line says the shape leaves out, read from the clause's own marker.

    **Not** a search of the whole line: a tab is full of digits, so `"5" in line` is true
    whether or not the 5th was named, and a witness that could pass on a line with no clause
    at all is no witness. The names end where the clause does - at the next ` - ` in
    `render._annotate`'s chain, or at the parenthetical's close - because clauses that follow
    it carry digits of their own (`reaches outside the preferred frets 2-13`), and the list
    itself is separated by `_and_list`'s `, ` and ` & `.
    """
    line = _line(step)
    marker = "it leaves out"
    if marker not in line:
        return []
    tail = line.split(marker, 1)[1]
    for end in (" - ", ")"):
        cut = tail.find(end)
        if cut != -1:
            tail = tail[:cut]
    for lead in (" is ", " are "):
        if tail.startswith(lead):
            tail = tail[len(lead) :]
            break
    else:  # pragma: no cover - a clause that fired always reads one way or the other
        return []
    return [name.strip() for name in tail.replace(" & ", ", ").split(",") if name.strip()]


WITNESSES: List[Witness] = [
    (
        "a substitute chord was stated, so the chord column is not what sounds",
        lambda step: bool(step.harmonized_as),
        lambda step: " via " in _line(step),
    ),
    (
        "the guitar sounds nothing at all there",
        lambda step: not step.voicing.active_frets(),
        lambda step: "rests here" in _line(step),
    ),
    (
        "the guitar is silent because the grid places no chord",
        lambda step: step.silence == SILENCE_GRID,
        lambda step: "the grid places no chord" in _line(step),
    ),
    (
        "the guitar is silent because an NC bar gives a comping part nothing to state",
        lambda step: step.silence == SILENCE_NC_COMPING,
        lambda step: "no chord to comp" in _line(step),
    ),
    (
        "the guitar is silent because no shape could carry the chord or the tune",
        lambda step: step.silence == SILENCE_NO_SHAPE,
        lambda step: "no voicing for this chord and none for the melody" in _line(step),
    ),
    (
        "the guitar is silent because no string reaches the written melody",
        lambda step: step.silence == SILENCE_OUT_OF_REACH,
        lambda step: "no string reaches the melody" in _line(step),
    ),
    (
        "the guitar is silent because a melody-only selection has no tune here",
        lambda step: step.silence == SILENCE_TUNE_SILENT,
        lambda step: "the tune is silent here" in _line(step),
    ),
    (
        "the guitar comps: the tune is not its to play",
        lambda step: not step.melody_voiced and bool(step.voicing.active_frets()),
        lambda step: (
            "does not play the tune" in _line(step)
            or "the tune is silent here" in _line(step)
        ),
    ),
    (
        "the tune is silent at this position, so nothing is being declined",
        lambda step: not step.melody_voiced and step.melody is None,
        lambda step: "the tune is silent here" in _line(step),
    ),
    (
        "the shape states fewer voices than the palette offered",
        lambda step: (
            step.palette is not None
            and step.palette.available > len(step.voicing.upper_midi_notes())
            and not step.repeated
        ),
        lambda step: "voices" in _line(step) or "melody alone" in _line(step),
    ),
    (
        "the palette's own limit was reached, which is a different answer",
        lambda step: (
            step.palette is not None
            and step.palette.alternative is None
            and _thin(step)
            and not step.repeated
        ),
        lambda step: "palette offers" in _line(step),
    ),
    (
        "a four-voice shape leaves a chord tone out, which the frets cannot show",
        lambda step: bool(
            _missing_degree_names(step) or _names_left_out_on_the_line(step)
        ),
        lambda step: (
            sorted(_names_left_out_on_the_line(step))
            == sorted(_missing_degree_names(step))
        ),
    ),
    (
        "the sounding melody is an octave below the written one",
        lambda step: step.original_melody is not None,
        lambda step: "transposed down an octave" in _line(step),
    ),
    (
        "a bass note was written into the step",
        lambda step: step.bass is not None,
        lambda step: "bass: " in _line(step),
    ),
    (
        "a bass note the walk asked for could not be placed, so the walk reads whole but is not",
        lambda step: step.bass_refused is not None,
        lambda step: "no playable bass note" in _line(step),
    ),
    (
        "the shape reaches outside the neck window",
        lambda step: (
            step.palette is not None or len(step.voicing.upper_midi_notes()) > 1
        )
        and any(
            not (NECK_FRET_MIN <= fret <= NECK_FRET_MAX)
            for fret in step.voicing.active_frets()
        ),
        lambda step: "preferred frets" in _line(step),
    ),
    (
        "a non-chord tone was left unsubstituted, so the strategy is worth naming",
        lambda step: (
            step.non_chord_tone and bool(step.strategy) and not step.harmonized_as
        ),
        lambda step: str(step.strategy) in _line(step),
    ),
    (
        "a chord no shape could state",
        lambda step: step.chord_unvoiced,
        lambda step: "no voicing" in _line(step) or "could not be read" in _line(step),
    ),
    (
        "a melody alone on a no-chord bar",
        lambda step: step.melody_only,
        lambda step: "no chord" in _line(step),
    ),
    (
        "the palette is thin because the texture asked, not because it ran out",
        lambda step: (
            step.role == "fill"
            and step.palette is not None
            and step.palette.alternative is None
            and _thin(step)
            and not step.repeated
        ),
        lambda step: "a fill's" in _line(step),
    ),
]


class TestEveryChoiceIsExplained(unittest.TestCase):
    """The invariant, swept over the committed heads rather than argued."""

    def test_every_decision_has_a_witness_in_its_line(self):
        """No step may make a decision its own annotation does not account for."""
        missing: List[str] = []
        checked = 0
        omitted = 0
        for head in HEADS:
            for config in CONFIGS:
                steps, _head, _notes = arrange_xml_head(head, section=(1, 8), **config)
                for step in steps:
                    checked += 1
                    omitted += bool(_missing_degree_names(step))
                    for label, when, witness in WITNESSES:
                        if when(step) and not witness(step):
                            missing.append(
                                f"{head.split('/')[-1]} {config} {step.chord} "
                                f"{step.melody} {step.tab_line()}: {label}"
                            )
        self.assertGreater(checked, 500, "the sweep stopped arranging anything")
        self.assertEqual(missing[:10], [], f"{len(missing)} unexplained steps")
        # A count, because a clause that stops firing is silent: measured over this sweep,
        # **82** of the steps it arranges give up a chord tone, and every one of them is
        # asked about above. A corpus, grip table or rule that stops reaching the clause
        # would otherwise leave every assertion here passing on its absence.
        self.assertEqual(
            omitted, 82, "the number of steps owing an omitted-tone clause moved"
        )

    def test_the_slash_bass_clause_is_not_a_tautology(self):
        """The one decision the witness table cannot hold, pinned in both directions.

        Whether the written bass sounds is decided *inside* `render._slash_bass_clause`, so a
        witness that recomputed it would be the clause agreeing with itself. Asserted against
        the head that exercises it instead: `Am7/D` loses its D and must say so, `Gmaj/D`
        sounds its F# and must stay quiet about it.
        """
        steps, _head, _notes = arrange_xml_head(
            "tests/data/Trouble_in_Mind_Blues.musicxml"
        )
        lost = [
            step for step in steps
            if "/" in step.chord and "written bass" in _step_annotation(step)
        ]
        kept = [
            step for step in steps
            if step.chord == "Gmaj/D" and "written bass" not in _step_annotation(step)
        ]
        self.assertTrue(lost, "the head stopped losing a slash bass")
        self.assertTrue(kept, "a shape that sounds its written bass was flagged")


#: `Eb6` under D5 as the corpus voices it: four voices stating the 3rd, the 5th and the
#: 6th, with the root left out. The middle of the corpus's `drop2_6432` reach, and the shape
#: the clause exists for.
_DROPS_THE_ROOT = [-1, 13, -1, 12, 13, 10]


class TestTheToneAFourVoiceShapeGivesUp(unittest.TestCase):
    """The clause that names the chord tone a four-voice shape leaves out.

    `TONE_PRIORITY` decides which tone goes when a chord has more tones than voices, and a
    shape filling four strings reads as a complete chord however many tones the name above it
    has - so this is a choice only the line can state. `TestEveryChoiceIsExplained` checks the
    naming against the fields, and the population; these pin the words, and the routes that
    had already answered for the shape.
    """

    def test_a_shape_that_drops_its_root_says_so(self):
        """`Eb6` under D5: the rule drops the root first, and the line names it."""
        step = make_step(_DROPS_THE_ROOT, chord="Eb6", melody="D5")
        self.assertEqual(_omission_clause(step), "the chord tone it leaves out is Root")

    def test_two_dropped_tones_are_both_named(self):
        """`Ab9` under E4 states four voices and leaves out the root *and* the 7th."""
        step = make_step([8, -1, 8, 8, 5, -1], chord="Ab9", melody="E4")
        self.assertEqual(
            _omission_clause(step), "the chord tones it leaves out are Root & b7"
        )

    def test_a_shape_that_states_every_tone_is_silent(self):
        """`Cmaj7` voiced C-G-E-B under B4 gives nothing up, so nothing is owed."""
        step = make_step([-1, 3, 5, 9, 12, -1], chord="Cmaj7", melody="B4")
        self.assertEqual(_omission_clause(step), "")

    def test_the_routes_that_answered_for_the_shape_stay_silent(self):
        """A hold and a thumb-only slot were explained where the shape was chosen.

        Both are the same frets as the pinned case, so silence here is the *route* and not
        the shape: the hold is annotated by what is struck, and `bass_only` by what is held.
        """
        held = make_step(_DROPS_THE_ROOT, chord="Eb6", melody="D5", repeated=True)
        thumb = make_step(_DROPS_THE_ROOT, chord="Eb6", melody="D5", bass_only=True)
        self.assertEqual(_omission_clause(held), "")
        self.assertEqual(_omission_clause(thumb), "")

    def test_a_thin_shape_and_a_melody_alone_stay_silent(self):
        """`partial` says `shell - 3rd & 7th` and a no-chord bar says `no chord`."""
        partial = make_step(_DROPS_THE_ROOT, chord="Eb6", melody="D5", partial=True)
        alone = make_step(_DROPS_THE_ROOT, chord="Eb6", melody="D5", melody_only=True)
        self.assertEqual(_omission_clause(partial), "")
        self.assertEqual(_omission_clause(alone), "")

    def test_a_chord_no_table_can_read_is_silent(self):
        """No tone set, no claim to make - the line already says the symbol was unreadable."""
        step = make_step([-1, 3, 5, 9, 12, -1], chord="Czz", melody="B4")
        self.assertEqual(_omission_clause(step), "")

    def test_the_tone_is_read_against_the_chord_the_part_states(self):
        """`harmonized_as` is the routed chord, which is what the rest of the line names."""
        step = make_step(_DROPS_THE_ROOT, chord="Czz", melody="D5", harmonized_as="Eb6")
        self.assertEqual(_omission_clause(step), "the chord tone it leaves out is Root")


class TestNewClausesMustBeRegistered(unittest.TestCase):
    """A gate that enumerates its inputs by hand skips whatever was added last.

    The set below is read **off the module** rather than typed as the answer, so a seventh
    clause cannot be added without landing in this test - and so without meeting
    `WITNESSES` above, or recording here why it needs no witness.
    """

    def test_every_clause_helper_is_known(self):
        from arranger import render

        known = {
            "_bass_refusal_clause",
            "_comping_clause",
            "_held_clause",
            "_omission_clause",
            "_shape_clause",
            "_silence_clause",
            "_slash_bass_clause",
            "_substitution_clause",
            "_transposition_clause",
            "_window_clause",
        }
        found = {name for name in dir(render) if name.endswith("_clause")}
        self.assertEqual(
            found,
            known,
            "a clause helper changed: add its witness to WITNESSES in this file, or say "
            "there why it needs none",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
