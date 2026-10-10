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

from arranger.render import _step_annotation
from arranger.tuning import NECK_FRET_MAX, NECK_FRET_MIN, ArrangementStep
from headxml import arrange_xml_head

#: The committed heads, which between them carry every quality, metre and texture the
#: library can be asked for. `tests/data` is the only corpus there is.
HEADS: List[str] = sorted(
    glob.glob("tests/data/*.mxl") + glob.glob("tests/data/*.musicxml")
)

#: One config per axis, plus the three that combine axes. Bounded deliberately: this is a
#: sweep of every committed head, so each config costs seconds.
CONFIGS: List[Dict[str, Any]] = [
    {},
    {"texture": "targets"},
    {"texture": "walking_bass"},
    {"bass": "walk"},
    {"melody": "none"},
    {"melody": "soprano"},
    {"melody": "alto,tenor"},
    {"grid": "freddie"},
    {"grips": ("shell",)},
    {"grips": ("duo",)},
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
        for head in HEADS:
            for config in CONFIGS:
                steps, _head, _notes = arrange_xml_head(head, section=(1, 8), **config)
                for step in steps:
                    checked += 1
                    for label, when, witness in WITNESSES:
                        if when(step) and not witness(step):
                            missing.append(
                                f"{head.split('/')[-1]} {config} {step.chord} "
                                f"{step.melody} {step.tab_line()}: {label}"
                            )
        self.assertGreater(checked, 500, "the sweep stopped arranging anything")
        self.assertEqual(missing[:10], [], f"{len(missing)} unexplained steps")

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


class TestNewClausesMustBeRegistered(unittest.TestCase):
    """A gate that enumerates its inputs by hand skips whatever was added last.

    The set below is read **off the module** rather than typed as the answer, so a seventh
    clause cannot be added without landing in this test - and so without meeting
    `WITNESSES` above, or recording here why it needs no witness.
    """

    def test_every_clause_helper_is_known(self):
        from arranger import render

        known = {
            "_comping_clause",
            "_held_clause",
            "_shape_clause",
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
