"""The standing check: every choice about a voiced note is explained by its line.

AGENTS.md states the invariant - *a step has to account for what it did and for the shape
it did it with* - and this module is what keeps it true. It works from the **step's own
fields**, never from the wording, so the check cannot be satisfied by phrasing: each entry
below is a decision the engine can make, a predicate for "this step is one of those", and a
witness the line must carry.

Two decisions are deliberately exempt, and they are named here rather than left implicit,
because a rule with unnamed exceptions is a rule the next editor deletes:

- a **hold** restates what corrects a *column* (its octave, the chord a substitution
  stated) but not the shape count, which was explained on the step that chose the shape -
  and the same holds for the two routes whose **own** clause already states the count, an
  `NC` bar and a melody no shape could voice: `annotation._shape_clause` stays silent for them
  rather than repeating "melody alone" twice. Their palette is still read by the window
  clause, so retiring that exemption cost them no explanation;
- the **written slash bass** is excluded from the table because its witness cannot be
  written as a predicate over the step alone - whether it sounds *is* the clause's own
  question, and a witness that recomputed it would be the clause agreeing with itself.
  `TestEveryChoiceIsExplained.test_the_slash_bass_clause_is_not_a_tautology` pins it directly.

A third exemption - a melody-alone shape getting no neck-window clause, on the grounds that
its fret is where the melody has to be rather than a choice - is **gone**, because its premise
is gone: a lone note is chosen from a palette of single-note shapes (one position per eligible
string) by the same `cost.voicing_cost` a chord goes through, so its fret *is* a shape the
engine picked from alternatives, and the window clause has a measured `Palette.inside_window`
to state. `TestTheLoneNoteKeepsTheWindowHonest` holds that down from both ends: the clause
appears where the note is out of position, and the palette it reports on is the one the note
was actually chosen from.

Adding a decision to the engine means adding its witness here, in the same commit.
"""

from __future__ import annotations

import glob
import unittest
from typing import Any, Callable, Dict, List, Tuple

from musthe import Note

from arranger import (
    CHORD_FILLS_COMP,
    CHORD_FILLS_HOLD,
    PITCH_CLASS_NAMES,
    ChordParser,
    Request,
)
from arranger.annotation import _omission_clause, step_annotation
from arranger.chords import melody_degree_name
from arranger.tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    SILENCE_GRID,
    SILENCE_NC_COMPING,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    SILENCE_TUNE_SILENT,
    ArrangementStep,
    Palette,
)
from tests.support import arranged, make_step

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
    # A fill lives where no melody slot does, which is the one place a comping step
    # can exist without a note beside it. Both policies, because `comp` states more
    # attacks than `hold` and a clause that fired for one and not the other would be
    # invisible in a sweep that only ever asked for one.
    {"request": Request(chord_on="none", chord_fills=CHORD_FILLS_HOLD)},
    {"request": Request(chord_on="none", chord_fills=CHORD_FILLS_COMP)},
]

#: (what the engine decided, when this step is one of those, what the line must say).
#: A tuple rather than three parallel lists, so the three cannot drift apart - which is the
#: failure mode this module exists to catch.
Witness = Tuple[str, Callable[[ArrangementStep], bool], Callable[[ArrangementStep], bool]]


def _thin(step: ArrangementStep) -> bool:
    """Fewer voices than the right hand has, which is what makes a count worth stating."""
    return len(step.voicing.upper_midi_notes()) < 4


def _line(step: ArrangementStep) -> str:
    return step_annotation(step)


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
    `annotation._annotate`'s chain, or at the parenthetical's close - because clauses that follow
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


def _sounding_pairs(step: ArrangementStep) -> List[str]:
    """The `note degree` pair every upper voice states, from the step's **fields**.

    The decision as stated, worked from the other side of the clause: a shape that sounds
    two or more upper voices on a route that sings the tune names each of them. The pitches
    are the step's own - the thumb is not among them - in the tab's order, and the degree is
    read through `chords.melody_degree_name`, the vocabulary the degree column uses, against
    the chord the part **states** (`harmonized_as` where a substitute was found). A witness
    built this way cannot be satisfied by a clause that names a note the shape does not
    sound, measures it against a chord the part is not playing, or stops one voice short.

    The routes the clause is silent on come back empty here too - a hold, a chord no shape
    could state, a comping part, and a harmony no table can read - which is what lets the
    witness catch a clause that speaks where it should not as well as one that stays quiet
    where it should speak.
    """
    if not step.melody_voiced or step.repeated or step.chord_unvoiced:
        return []
    harmony = step.harmonized_as or step.chord
    pitches = step.voicing.upper_midi_notes()
    if len(pitches) < 2:
        return []
    pairs = []
    for pitch in pitches:
        name = PITCH_CLASS_NAMES[pitch % 12]
        pairs.append(f"{name} {melody_degree_name(Note(name + '4'), harmony)}")
    if not all(pair.split(" ", 1)[-1] for pair in pairs):
        return []
    return pairs


def _voices_named_on_the_line(step: ArrangementStep) -> List[str]:
    """The voices a line says the shape sounds, read from the clause's own marker.

    **Not** a search of the whole line: the tab is frets, so a note name has to come from
    the clause or not at all. The list ends where the clause does - at the next ` - ` in
    `annotation._annotate`'s chain, or at the parenthetical's close - because clauses that
    follow it carry names of their own (`the chord tone it leaves out is Root`).
    """
    line = _line(step)
    marker = "sounding: "
    if marker not in line:
        return []
    tail = line.split(marker, 1)[1]
    for end in (" - ", ")"):
        cut = tail.find(end)
        if cut != -1:
            tail = tail[:cut]
    return [pair.strip() for pair in tail.split(", ") if pair.strip()]


def _comping_names(step: ArrangementStep) -> List[str]:
    """Every voice a **comping** shape states, as `note degree`, from the step's fields.

    A comping step has no melody column, so the clause is the only place a reader can learn
    which note of the chord the shape put where - and the tab gives frets. Read from the
    step's own pitches against the chord the part **states**, one entry per degree (two
    octaves of one degree is one entry, which is the shape's own claim), and compared as a
    sorted list by the witness below, because the clause orders the voices by the interval
    from the root and that order is not the question.

    The routes are the ones `step_annotation` reaches `_comping_clause` by, in the same
    order - a no-chord bar, a chord no shape could state, and a silent step are all answered
    before it - so the clause speaking where it should not is caught as well as its silence.
    """
    if step.melody_only or step.chord_unvoiced or step.melody_voiced:
        return []
    if not step.voicing.active_frets():
        return []
    harmony = step.harmonized_as or step.chord
    named: Dict[str, str] = {}
    for pitch in step.voicing.upper_midi_notes():
        name = PITCH_CLASS_NAMES[pitch % 12]
        degree = melody_degree_name(Note(name + "4"), harmony)
        if not degree or degree in named:
            continue
        named[degree] = f"{name} {degree}"
    return list(named.values())


def _comping_names_on_the_line(step: ArrangementStep) -> List[str]:
    """The voices the line's comping clause names, read from the clause's own marker.

    The list ends where the clause does - at the `;` that introduces what the part is not
    doing with the tune - because that tail is prose rather than a voice list.
    """
    line = _line(step)
    marker = "comping - "
    if marker not in line:
        return []
    tail = line.split(marker, 1)[1].split(";", 1)[0]
    return [
        name.strip() for name in tail.replace(" & ", ", ").split(",") if name.strip()
    ]


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
        "the guitar comps, so the voices it states are the only harmony a reader can see",
        lambda step: bool(_comping_names(step) or _comping_names_on_the_line(step)),
        lambda step: (
            sorted(_comping_names_on_the_line(step)) == sorted(_comping_names(step))
        ),
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
            # The routes whose own clause states the count - an `NC` bar and a melody no
            # shape could voice - keep it to themselves, the way a hold does. See
            # `annotation._shape_clause`: the *window* fact they carry is still witnessed.
            and not step.melody_only
            and not step.chord_unvoiced
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
        "the shape sounds two or more voices, which the frets do not name",
        lambda step: bool(_sounding_pairs(step) or _voices_named_on_the_line(step)),
        lambda step: _voices_named_on_the_line(step) == _sounding_pairs(step),
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
            # As above: an `NC` fill-role slot states its own count ("no chord - melody
            # alone"), and it is the no-harmony fact that explains the thinness, not the
            # texture. The palette's window fact is still witnessed.
            and not step.melody_only
            and not step.chord_unvoiced
        ),
        lambda step: "a fill's" in _line(step),
    ),
]


class TestEveryChoiceIsExplained(unittest.TestCase):
    """The invariant, swept over the committed heads rather than argued.

    Every committed head, and not `tests.support.sweep_head_paths()`: the subject here is the
    behaviour space the witness table claims to cover, and that was measured - over the three
    sweep heads, seven of the table's eighteen labels are never triggered, so a narrower
    sweep would retire witnesses rather than save time.
    """

    def test_every_decision_has_a_witness_in_its_line(self):
        """No step may make a decision its own annotation does not account for.

        The arrangements are `tests.support.arranged`'s, so the other sweep in this file
        that shares a config reads the same steps rather than paying for them again.
        """
        missing: List[str] = []
        checked = 0
        omitted = 0
        named = 0
        comping = 0
        for head in HEADS:
            for config in CONFIGS:
                steps, _head, _notes = arranged(head, section=(1, 8), **config)
                for step in steps:
                    checked += 1
                    omitted += bool(_missing_degree_names(step))
                    named += bool(_sounding_pairs(step))
                    comping += bool(_comping_names(step))
                    for label, when, witness in WITNESSES:
                        if when(step) and not witness(step):
                            missing.append(
                                f"{head.split('/')[-1]} {config} {step.chord} "
                                f"{step.melody} {step.tab_line()}: {label}"
                            )
        self.assertGreater(checked, 500, "the sweep stopped arranging anything")
        self.assertEqual(missing[:10], [], f"{len(missing)} unexplained steps")
        # A count, because a clause that stops firing is silent: measured over this sweep,
        # **139** of the steps it arranges give up a chord tone, and every one of them is
        # asked about above. The three grouped fixtures (5/4, 7/4, 12/8) account for the
        # last 40: they are melody-dense and every note carries a chord. A corpus, grip
        # table or rule that stops reaching the clause would otherwise leave every
        # assertion here passing on its absence.
        self.assertEqual(
            omitted, 139, "the number of steps owing an omitted-tone clause moved"
        )
        # The same reasoning for the voice list, which is the clause most steps carry:
        # measured over this sweep, **1377** of the steps it arranges sound two or more
        # upper voices on a route that sings the tune - so a change that thinned the
        # default palette, or that stopped the clause firing, moves this number. The
        # grouped fixtures add 352, all of them from notes the old corpus did not have.
        self.assertEqual(named, 1377, "the number of steps naming their voices moved")
        # And for the comping part, whose voices are the only harmony the line can show:
        # measured over this sweep, **1827** of the steps it arranges state a comping shape
        # and name each of its voices, so the reading of a thin line cannot quietly become
        # a list of degrees again. The grouped fixtures add 802, and the 116 rest fills
        # (`--chord-fills`) are the newest addition: a fill is a comping step with no
        # melody beside it, which is why it counts here and nowhere else.
        self.assertEqual(comping, 1827, "the number of comping lines naming a voice moved")

    def test_the_slash_bass_clause_is_not_a_tautology(self):
        """The one decision the witness table cannot hold, pinned in both directions.

        Whether the written bass sounds is decided *inside* `annotation._slash_bass_clause`, so a
        witness that recomputed it would be the clause agreeing with itself. Asserted against
        the head that exercises it instead: `Am7/D` loses its D and must say so, `Gmaj/D`
        sounds its F# and must stay quiet about it.

        The witness is a **named** grid. The default grid now withholds a position the
        tune is still holding (§9.2), and the `Am7/D` bars are exactly such a hold, so
        the default arrangement no longer states them at all. `freddie` states its figure
        whatever the tune is doing, which is what keeps the slash-bass question asked.
        """
        steps, _head, _notes = arranged(
            "tests/data/Trouble_in_Mind_Blues.musicxml", grid="chord:freddie"
        )
        lost = [
            step for step in steps
            if "/" in step.chord and "written bass" in step_annotation(step)
        ]
        kept = [
            step for step in steps
            if step.chord == "Gmaj/D" and "written bass" not in step_annotation(step)
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


class TestTheLoneNoteKeepsTheWindowHonest(unittest.TestCase):
    """A lone note is chosen from a palette, so its window fact is measured, not defaulted.

    This is the exemption that went. A melody-alone shape used to carry no palette, which
    meant `annotation._window_clause` could say nothing about it - and a step that *did* carry
    one (a fill) recorded `inside_window` at its `False` default, so the clause read as an
    engine judgement nobody had made. Every lone note now records the palette it was chosen
    from, and the two halves of the fact can be asserted together: the clause appears where
    the note is out of position, and the palette behind it has nothing inside the window.
    """

    #: The configs that thin the guitar to a lone note at all: the off-grid rows, the walk's
    #: fills, and the melody-only selection.
    CONFIGS: List[Dict[str, Any]] = [
        {},
        {"grid": "chord:freddie"},
        {"bass": "root,5th,approach,nearest", "grid": "melody:every_note,bass:walk"},
        {"parts": "melody"},
    ]

    def test_every_lone_shape_reports_the_palette_it_came_from(self):
        """A lone step always has a palette - the exemption's premise is gone."""
        checked = 0
        for head in HEADS:
            for config in self.CONFIGS:
                steps, _head, _notes = arranged(head, section=(1, 8), **config)
                for step in steps:
                    if step.grip != "melody":
                        continue
                    # A lone *upper* shape: the walk may have merged a thumb into it, which
                    # is a second active fret and a different question (`bass_only`).
                    if len(step.voicing.upper_midi_notes()) != 1:
                        continue
                    checked += 1
                    self.assertIsNotNone(
                        step.palette, f"{head.split('/')[-1]} {config} {step.tab_line()}"
                    )
                    assert step.palette is not None
                    # The walk may have merged a thumb into this step, which is a second
                    # active fret and a different question - hence the filter on the upper
                    # notes rather than on `active_frets()`.
                    self.assertEqual(len(step.voicing.upper_midi_notes()), 1)
                    # Either the lone note's own palette, or the demotion's record of the
                    # shape it turned away - which is a different question and says so.
                    self.assertTrue(
                        step.palette.available == 1
                        or step.palette.alternative is not None
                    )
        self.assertGreater(checked, 50, "the sweep stopped thinning anything")

    def test_the_window_clause_reports_the_lone_note_palette(self):
        """The clause reads the palette, in both directions, on the step it is given.

        F4 on the high E string is fret 1 - below `NECK_FRET_MIN` - and the same note is
        fret 6 on the B string, inside it. Same note, same one-note palette; only what the
        caller's strings offered differs. The third case is the contrast a chord palette
        can make and a lone one cannot: an inside-the-window shape losing on correctness.
        """
        outside = make_step(
            [-1, -1, -1, -1, -1, 1],
            melody="F4",
            palette=Palette(available=1, inside_window=False),
        )
        inside = make_step(
            [-1, -1, -1, -1, 6, -1],
            melody="F4",
            palette=Palette(available=1, inside_window=True),
        )
        chord = make_step(
            [-1, -1, 15, 14, -1, -1],
            palette=Palette(available=4, inside_window=True),
        )
        self.assertIn("nothing in this palette sits inside the window", _line(outside))
        self.assertNotIn("preferred frets", _line(inside))
        self.assertIn("sound a note outside the chord", _line(chord))


class TestNewClausesMustBeRegistered(unittest.TestCase):
    """A gate that enumerates its inputs by hand skips whatever was added last.

    The set below is read **off the module** rather than typed as the answer, so another
    clause cannot be added without landing in this test - and so without meeting
    `WITNESSES` above, or recording here why it needs no witness.
    """

    def test_every_clause_helper_is_known(self):
        from arranger import annotation

        known = {
            "_bass_refusal_clause",
            "_comping_clause",
            "_held_clause",
            "_omission_clause",
            "_shape_clause",
            "_silence_clause",
            "_slash_bass_clause",
            "_sounding_clause",
            "_substitution_clause",
            "_transposition_clause",
            "_window_clause",
        }
        found = {name for name in dir(annotation) if name.endswith("_clause")}
        self.assertEqual(
            found,
            known,
            "a clause helper changed: add its witness to WITNESSES in this file, or say "
            "there why it needs none",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
