"""Tests for the shared placement search: `_frets_in_span` and `_place_shape`.

The string sets whose voices are not in descending pitch order down the strings - 6-4-3,
both 5-3-2s and 6-4-3-2 - are *searched* rather than stacked, because the tuning is not
monotonic in the useful direction. `_place_shape` is that search stated once, and this
file holds it to two things nothing else can:

* the **rules** every candidate in the library obeys - the melody on the highest sounding
  string, nothing outside the chord, the span limit, the bass degree when the family
  states one - checked against a reference written from the rules rather than from the
  code, enumerating with `itertools.product` over the whole string set so the two do not
  share "which frets to try";
* **exhaustiveness and order**, which the search's own docstring claims: within the span
  limit it tries every combination, in ascending order, which is what makes an exact tie
  fall to the earliest shape.

`TestTheGripDistribution` is the stage's standing gate. A change to how a shape is placed
moves a **count** here rather than a tab in `tests/test_voicings.py` that a reader would
have to notice - which is the signal this repository asks a change to give.
"""

from __future__ import annotations

import glob
import unittest
from dataclasses import replace
from itertools import product
from typing import Dict, FrozenSet, List, Optional, Tuple

from musthe import Note

import headxml
from arranger import (
    BASS_DEGREES_6432,
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    MELODY_STRING_CHOICES_FULL,
    SHELL_DEGREES,
    ChordParser,
    GuitarFretboard,
)
from arranger.grips import (
    _candidate,
    _chord_context,
    _frets_in_span,
    _place_drop2_6432,
    _place_shape,
    _place_shell,
    _place_template,
    _Placement,
    _string_sets_for,
)

HEADS = sorted(glob.glob("tests/data/*.musicxml") + glob.glob("tests/data/*.mxl"))

# A spread of the qualities the searched families have to cope with: sevenths, a sixth, a
# half-diminished, a diminished, two extended chords, a triad and a suspended chord.
CASES = [
    ("Cmaj7", "B4"),
    ("Cm7", "G4"),
    ("C7", "E4"),
    ("C6", "A4"),
    ("Cm7b5", "F4"),
    ("Cdim7", "Ab4"),
    ("C9", "D5"),
    ("C13", "A4"),
    ("Cmaj", "E4"),
    ("C7sus4", "F4"),
]


def _context(chord_name: str) -> Tuple[str, int, Tuple[int, ...]]:
    """The canonical quality, the root's pitch class and the chord's tones as degrees.

    Read through the engine's own `_chord_context`, because what the search is handed is
    what the families hand it. The question this file asks is what the *search* does with a
    request, not how the request is derived.
    """
    _, quality = ChordParser.parse_chord_name(chord_name)
    canonical, root_pc, tones = _chord_context(quality or chord_name, chord_name)
    assert root_pc is not None
    return canonical, root_pc, tones


def _fret_vector(strings: Tuple[int, ...], combo: Tuple[int, ...]) -> List[int]:
    frets = [-1] * 6
    for string, fret in zip(strings, combo):
        frets[string] = fret
    return frets


def _allowed_for(canonical: str, root_pc: int, tones: Tuple[int, ...]) -> FrozenSet[int]:
    return frozenset((root_pc + tone) % 12 for tone in tones)


def _reference(placement: _Placement, allowed: frozenset) -> Optional[List[int]]:
    """The documented rules, written the obvious way: every combination, then filter.

    Deliberately a second implementation rather than a call to the thing under test, and
    deliberately a *dumb* one - `itertools.product` over the whole string set, where the
    search under test narrows the window as it recurses. The two agree only if the
    narrowing never drops a combination the span rule would have kept.
    """
    strings = placement.strings
    top_fret = placement.top_fret
    limit = GRIP_MAX_SPAN[placement.grip]
    if top_fret + limit > 18:
        return None
    lo, hi = max(0, top_fret - limit), top_fret + limit

    best: Optional[Tuple[Tuple[int, float], List[int]]] = None
    for combo in product(range(lo, hi + 1), repeat=len(strings)):
        if combo[0] != top_fret or max(combo) - min(combo) > limit:
            continue
        midis = sorted(
            GuitarFretboard.fret_to_midi(string, fret)
            for string, fret in zip(strings, combo)
        )
        if midis[-1] != GuitarFretboard.fret_to_midi(strings[0], top_fret):
            continue
        pcs = {midi % 12 for midi in midis}
        if not placement.required <= pcs or not pcs <= allowed:
            continue
        if (
            placement.lowest_pc_allowed is not None
            and midis[0] % 12 not in placement.lowest_pc_allowed
        ):
            continue
        key = (max(combo) - min(combo), sum(combo) / len(combo))
        if best is None or key < best[0]:
            best = (key, _fret_vector(strings, combo))
    return best[1] if best else None


class TestTheSearchIsExhaustive(unittest.TestCase):
    """`_frets_in_span` tries every span-legal combination, in ascending order."""

    def test_every_span_legal_combination_is_yielded_and_none_other(self):
        """The window-narrowing recursion misses nothing and invents nothing.

        The property `_place_shape`'s docstring rests on: because the search is
        exhaustive within the span limit, "no shape was found" means there is none.
        """
        for strings, lo, hi, limit in (
            ((5, 4), 3, 9, 4),
            ((2, 3, 4, 5), 5, 11, 5),
            ((4, 3, 2), 0, 5, 3),
            ((2, 3, 4), 10, 14, 2),
        ):
            expected = [
                combo
                for combo in product(range(lo, hi + 1), repeat=len(strings))
                if max(combo) - min(combo) <= limit
            ]
            self.assertEqual(
                list(_frets_in_span(strings, lo, hi, limit)),
                expected,
                f"{strings} in {lo}..{hi} at span {limit}",
            )

    def test_the_yielded_order_is_ascending(self):
        """The order is load-bearing: it is how an exact tie is broken."""
        yielded = list(_frets_in_span((4, 3, 2), 0, 4, 3))
        self.assertEqual(yielded, sorted(yielded))

    def test_an_empty_string_set_yields_the_empty_shape(self):
        """The recursion's base case, which a one-voice shape would reach."""
        self.assertEqual(list(_frets_in_span((), 0, 5, 5)), [()])


def _requests(chord_name: str, melody: str, top_string: int) -> List[Tuple[_Placement, frozenset]]:
    """The requests the two searched families make for one melody on one soprano string.

    Built here from the rules each family states - a shell wants both guide tones on the
    three strings from the soprano down, the 6-4-3-2 wants four of the chord's tones with a
    root or a 5th underneath - so the search is asked the same question the family asks it,
    rather than a question a test invented.
    """
    canonical, root_pc, tones = _context(chord_name)
    melody_midi = Note(melody).midi_note()
    top_fret = GuitarFretboard.note_to_fret(top_string, Note(melody))
    if top_fret < 0:
        return []
    allowed = _allowed_for(canonical, root_pc, tones)
    guide = SHELL_DEGREES[canonical]
    requests: List[Tuple[_Placement, frozenset]] = []
    for strings in _string_sets_for("shell", top_string):
        requests.append(
            (
                _Placement(
                    grip="shell",
                    strings=strings[:3],
                    melody_midi=melody_midi,
                    top_fret=top_fret,
                    required=frozenset((root_pc + g) % 12 for g in guide),
                ),
                allowed,
            )
        )
    for strings in _string_sets_for("drop2_6432", top_string):
        requests.append(
            (
                _Placement(
                    grip="drop2_6432",
                    strings=strings,
                    melody_midi=melody_midi,
                    top_fret=top_fret,
                    required=frozenset(),
                    lowest_pc_allowed=frozenset(
                        (root_pc + d) % 12 for d in BASS_DEGREES_6432
                    ),
                ),
                allowed,
            )
        )
    return requests


class TestTheSearchObeysTheInvariants(unittest.TestCase):
    """`_place_shape` against the rules, and against a second implementation of them."""

    def test_the_search_agrees_with_the_rules_written_out(self):
        """Every searched family's request, checked against the brute-force reference."""
        checked = 0
        for chord_name, melody in CASES:
            for top_string in MELODY_STRING_CHOICES_FULL:
                for placement, allowed in _requests(chord_name, melody, top_string):
                    found = _place_shape(placement, allowed)
                    self.assertEqual(
                        found.frets if found else None,
                        _reference(placement, allowed),
                        f"{chord_name} {melody} on {placement.strings}",
                    )
                    checked += 1
        self.assertGreater(checked, 60)

    def test_the_families_ask_the_question_the_reference_checks(self):
        """A shell's own answer is the search's answer to the request above.

        Which is what makes `_place_shell` and `_place_drop2_6432` one placement path
        rather than two that happen to agree - a test of the seam, not of the rules.
        """
        for chord_name, melody in CASES:
            canonical, root_pc, tones = _context(chord_name)
            melody_midi = Note(melody).midi_note()
            for top_string in MELODY_STRING_CHOICES_FULL:
                top_fret = GuitarFretboard.note_to_fret(top_string, Note(melody))
                if top_fret < 0:
                    continue
                for strings in _string_sets_for("shell", top_string):
                    by_family = _place_shell(
                        canonical, tones, root_pc, strings, melody_midi, top_fret
                    )
                    by_search = _place_shape(
                        next(
                            p
                            for p, _ in _requests(chord_name, melody, top_string)
                            if p.grip == "shell" and p.strings == strings[:3]
                        ),
                        _allowed_for(canonical, root_pc, tones),
                    )
                    self.assertEqual(
                        by_family.frets if by_family else None,
                        by_search.frets if by_search else None,
                    )

    def test_the_melody_is_always_the_highest_sounding_note(self):
        """The invariant for every searched shape, not merely for the ones tried here."""
        for chord_name, melody in CASES:
            canonical, root_pc, tones = _context(chord_name)
            melody_midi = Note(melody).midi_note()
            for top_string in MELODY_STRING_CHOICES_FULL:
                top_fret = GuitarFretboard.note_to_fret(top_string, Note(melody))
                if top_fret < 0:
                    continue
                for strings in _string_sets_for("shell", top_string):
                    found = _place_shell(
                        canonical, tones, root_pc, strings, melody_midi, top_fret
                    )
                    if found is None:
                        continue
                    self.assertEqual(found.midi_notes()[-1], melody_midi, found.frets)
                    self.assertEqual(found.soprano_string(), strings[0])

    def test_the_melody_must_be_the_highest_sounding_note(self):
        """A shape whose inner voice sounds *above* the melody is refused, not returned.

        Pinning the melody to the top *string* does not put it on top in *pitch*: the B and
        G strings are four semitones apart, so an inner string one fret up sounds a
        semitone above the melody. Am9 with a B3 melody on the B string is the case, and
        the (4,3,2) set's only reachable shape there is `[B:0, G:5, D:5]` - B3 under C4.

        The three assertions below are what make it a witness rather than a refusal: the
        crossed shape sounds only chord tones and holds both guide tones, so the melody rule
        is the *only* thing refusing it.
        """
        canonical, root_pc, tones = _context("Am9")
        melody = Note("B3")
        top_fret = GuitarFretboard.note_to_fret(4, melody)
        self.assertEqual(top_fret, 0)
        self.assertIsNone(
            _place_shell(
                canonical, tones, root_pc, (4, 3, 2), melody.midi_note(), top_fret
            )
        )

        guide = frozenset((root_pc + g) % 12 for g in SHELL_DEGREES[canonical])
        allowed = _allowed_for(canonical, root_pc, tones)
        crossed = (top_fret, 5, 5)  # melody on the B string, G and D a fret above
        midis = [
            GuitarFretboard.fret_to_midi(string, fret)
            for string, fret in zip((4, 3, 2), crossed)
        ]
        self.assertLessEqual({midi % 12 for midi in midis}, allowed)
        self.assertLessEqual(guide, {midi % 12 for midi in midis})
        self.assertLessEqual(max(crossed) - min(crossed), GRIP_MAX_SPAN["shell"])
        self.assertGreater(max(midis), melody.midi_note())

    def test_a_window_off_the_end_of_the_board_yields_nothing(self):
        """A melody too high to voice here is refused rather than clamped.

        The window is the span limit either side of the melody, so a window that runs past
        fret 18 belongs to `get_octave_down_candidates`, not to this search. Pinned because
        clamping instead would *add* candidates for a high melody rather than move one.
        """
        melody = Note("F#5")
        top_fret = GuitarFretboard.note_to_fret(5, melody)
        placement = _Placement(
            grip="shell",
            strings=(5, 4, 3),
            melody_midi=melody.midi_note(),
            top_fret=top_fret,
            required=frozenset(),
        )
        self.assertEqual(top_fret, 14)
        self.assertGreater(top_fret + GRIP_MAX_SPAN["shell"], 18)
        self.assertIsNone(_place_shape(placement, frozenset(range(12))))

    def test_a_tone_the_chord_does_not_contain_is_refused(self):
        """`required ⊆ pcs ⊆ allowed` is one condition, so an impossible claim finds nothing."""
        melody = Note("B4")
        placement = _Placement(
            grip="shell",
            strings=(5, 4, 3),
            melody_midi=melody.midi_note(),
            top_fret=GuitarFretboard.note_to_fret(5, melody),
            required=frozenset({1}),
        )
        # Cmaj7 without its root: nothing can sound a Db, so no shape can honour the claim.
        self.assertIsNone(_place_shape(placement, frozenset({4, 7, 11})))

    def test_the_bass_rule_refuses_a_bottom_note_outside_the_degrees(self):
        """`lowest_pc_allowed` is the family's claim about the bass, and it is enforced."""
        melody = Note("B4")
        base = _Placement(
            grip="drop2_6432",
            strings=_string_sets_for("drop2_6432", 4)[0],
            melody_midi=melody.midi_note(),
            top_fret=GuitarFretboard.note_to_fret(4, melody),
            required=frozenset(),
        )
        # A Cmaj7 whose bass may only be an F: no shape of it can honour that.
        self.assertIsNone(
            _place_shape(
                replace(base, lowest_pc_allowed=frozenset({5})),
                frozenset({0, 4, 7, 11}),
            )
        )
        # The same request with the chord's own root or 5th allowed does find one.
        self.assertIsNotNone(
            _place_shape(
                replace(base, lowest_pc_allowed=frozenset({0, 7})),
                frozenset({0, 4, 7, 11}),
            )
        )

    def test_an_empty_required_makes_no_claim_about_which_tones_sound(self):
        """The 6-4-3-2's rule: four of the chord's tones, and the string set decides which."""
        _, root_pc, tones = _context("Cmaj7")
        found = _place_drop2_6432(
            tones, root_pc, Note("B4").midi_note(),
            GuitarFretboard.note_to_fret(4, Note("B4")),
            _string_sets_for("drop2_6432", 4)[0],
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertLessEqual({midi % 12 for midi in found.midi_notes()}, {0, 4, 7, 11})
        self.assertEqual(len(found.active_frets()), 4)

    def test_a_shell_uses_the_three_strings_from_the_soprano_down(self):
        """A four-string set cannot silently become a four-voice shell."""
        canonical, root_pc, tones = _context("Cmaj7")
        found = _place_shell(
            canonical, tones, root_pc, (5, 4, 3, 2), Note("B4").midi_note(),
            GuitarFretboard.note_to_fret(5, Note("B4")),
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.active_strings, [3, 4, 5])

    def test_a_shape_cannot_sound_strings_the_tables_never_offered(self):
        """`supported_string_sets()` is enforced where the frets are, not only in the table.

        Which strings a shape sounds is a *musical* decision, so the validator is where it
        has to hold: the 5-3-2 shell set is offered, the top two of it are not, and the
        request says how many strings the shape uses. Without the rule a producer that
        filled in a different subset would ship a shape nobody chose.
        """
        placement = _Placement(
            grip="shell",
            strings=(5, 3, 2),
            melody_midi=Note("E4").midi_note(),
            top_fret=GuitarFretboard.note_to_fret(5, Note("E4")),
            required=frozenset(),
        )
        frets = [-1, -1, 0, 0, -1, 0]
        self.assertIsNotNone(_candidate(placement, frets, None))
        # The same frets read as a two-voice shape sound the high E and the G, which is
        # `{3, 5}` - a set no table entry offers.
        self.assertIsNone(_candidate(replace(placement, voices=2), frets, None))

    def test_a_voice_below_a_strings_open_pitch_refuses_the_shape(self):
        """A fret of -1 is a refusal here, not a mute - and it is reachable.

        `voices` is what says which of the set's strings the shape uses, so anything below
        the set's first `voices` strings is muted and the used ones must each carry a real
        fret. A computed -1 - the note one semitone below a string's open pitch - must not
        be mistaken for "unused": reading it that way thins the shape, and on a disjoint set
        it invents one. C7 under E4 reaches both, its guide tone lying a tritone below the
        melody, which is exactly -1 on the B string.
        """
        melody = Note("E4")
        top_fret = GuitarFretboard.note_to_fret(5, melody)
        # A duo's second voice a tritone below the melody: -1 on the B string.
        self.assertIsNone(
            _place_template([0, -6], (5, 4), melody.midi_note(), top_fret, "duo")
        )
        # A four-voice drop-2 of C7 reaches the same string. Read as a mute, this shape
        # sounded the high E, the G and the A - {1, 3, 5}, which is no set in the table.
        self.assertIsNone(
            _place_template(
                [0, -6, -9, -16], (5, 4, 3, 1), melody.midi_note(), top_fret, "drop2"
            )
        )
        # A note *further* below the open pitch is refused for the same reason, so the rule
        # is "used strings carry a fret on the board" rather than "no fret of exactly -1".
        self.assertIsNone(
            _place_template(
                [0, -14], (3, 2), Note("C4").midi_note(),
                GuitarFretboard.note_to_fret(3, Note("C4")), "duo",
            )
        )

    def test_the_tightest_shape_wins_a_choice(self):
        """Ranking is `(span, position)`, so the shape a player would pick is the one kept.

        Asserted against the reference's own ranking, because an unranked search would
        return whichever shape the enumeration reached first.
        """
        ranked = 0
        for placement, allowed in _requests("Cmaj7", "B4", 5):
            found = _place_shape(placement, allowed)
            if found is None:
                continue
            reference = _reference(placement, allowed)
            assert reference is not None
            frets = [fret for fret in reference if fret >= 0]
            self.assertEqual(
                (found.fret_span(), round(found.avg_fret, 6)),
                (max(frets) - min(frets), round(sum(frets) / len(frets), 6)),
            )
            ranked += 1
        self.assertGreater(ranked, 0)


class TestTheGripDistribution(unittest.TestCase):
    """How the families are actually used over every committed head.

    This is the shared placement's gate rather than a curiosity: `_place_shape` is the one
    path every searched family now takes, so a change that altered a shape moves one of
    these counts. A *count* is the metre this repository asks a change to give - a moved
    tab in `tests/test_voicings.py` says something changed, and this table says what.
    """

    def test_every_head_arranges_to_the_same_families(self):
        total = 0
        counts: Dict[str, int] = {}
        for path in HEADS:
            steps = headxml.arrange_xml_head(path)[0]
            total += len(steps)
            for step in steps:
                grip = step.voicing.grip
                counts[grip] = counts.get(grip, 0) + 1

        self.assertEqual(total, 1103)
        self.assertEqual(
            counts,
            {
                "drop3": 289,
                "drop2_6432": 209,
                "drop2": 185,
                "shell": 179,
                "closed": 129,
                "melody": 49,
                "drop24": 34,
                "duo": 29,
            },
        )
        # Every family in the default preference wins somewhere over these heads, so the
        # table above is a distribution rather than a list of what happened to survive.
        # The one key that is not a family is `melody`, which names a step whose chord
        # nothing could voice rather than a shape placed on strings.
        self.assertEqual(set(counts) - {"melody"}, set(GRIP_PREFERENCE))
