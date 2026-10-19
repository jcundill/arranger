"""Shared fixtures for the test suite.

Every helper here was, at some point, copy-pasted between two test files with a
docstring saying roughly *"written here rather than imported so this file stays
independent"*. That is a reasonable instinct for a test that genuinely needs its
own fixture, and the wrong one for a fixture whose whole content is "derive
`top_fret` and `avg_fret` the way the engine does" - four files had that, and they
had already begun to drift.

What is **not** here, deliberately:

* a helper two files both want but which reads better in one of them. The case this
  bullet was written for has moved: `test_bass`'s `names(chords, onsets)` and the
  walking-bass suite's "the thumb's pitch class" were two functions sharing one name,
  and splitting that suite across three files left the second wanted by two of them.
  It is here as `bass_name`, renamed because a bare `support.names` would have been the
  same collision with a wider blast radius;

Every fixture here builds a value by hand rather than by running the engine, which
is the point: a test that arranges a progression and then asserts on the result is
testing the engine against itself.

The one exception is `arranged`, which runs the engine and hands back what it produced.
It is not an expectation, it is a **cache of evidence**: several tests assert different
things about one arrangement, and the arrangement is the expensive half of a sweep. A
fixture built by the engine is a defect; a share of the engine's own output is not.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from musthe import Note

import arranger
from arranger import (
    BASS_STYLE_WALK,
    PITCH_CLASS_NAMES,
    SHELL_DEGREES,
    STANDARD_TUNING,
    ArrangementStep,
    ChordParser,
    VoiceLeadingEngine,
    Voicing,
    get_comping_voicings,
)

#: The library's top-level modules: the shared score core, the renderers, the
#: importer and the grip-chart generator. Shared by `test_structure` (which budgets
#: them) and `test_front_end_dag` (which holds their imports to the facade rule), so
#: the two lists cannot drift apart.
FRONT_ENDS = (
    "tabscore.py",
    "tabstaff.py",
    "tabxml.py",
    "tabgp.py",
    "headxml.py",
    "grip_chart.py",
)

#: The committed MusicXML fixtures. Defined once because four test modules build paths
#: from it, and a second spelling of the same directory is a second source for one fact.
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: The synthetic 2/2 head the importer, the GP5 writer and the walk all name. It is
#: shared here rather than imported from the module that happened to define it first,
#: which is the test-suite form of the private-import problem: `test_headxml` is one
#: concern among several that need this fixture, not its owner.
BUT_NOT_FOR_ME = os.path.join(DATA, "synthetic_cut_time.mxl")

# The library's own demonstration cadences. These are the progressions whose tab is
# already asserted elsewhere in the suite, so they double as the fixture here: if the
# metric layer ever leaked into the default path, these strings would move.
MINOR_CADENCE = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("B4", "7", "G7"),
    ("C5", "maj7", "Cmaj7"),
]

MAJOR_CADENCE = [
    ("D5", "m7", "Dm7"),
    ("C#5", "7", "A7"),
    ("C#5", "m7", "A-7"),
    ("D5", "mMaj7", "Dm(maj7)"),
]

def minor_cadence_tabs():
    """
    The published fingerings for MINOR_CADENCE, as the library produces them now.

    Defined here as a function rather than a literal in each test, because two files
    assert this tab and a second copy of the literals is a second thing to forget when
    a change is deliberate. Callers compare against it rather than typing it.

    The G7 is a drop-3 on strings 5-3-2-1 (`x-8-x-7-8-7`) where it was a drop-2 at
    `x-x-5-7-6-7` - the same G7, span 1 against span 2. See
    `test_the_demo_cadences_still_produce_the_same_tab`, which pins both cadences and
    says why each shape moved.
    """
    return [
        "x-x-10-10-10-10", "x-x-9-9-8-8", "x-8-x-7-8-7", "x-x-9-9-8-8",
    ]


def major_cadence_tabs():
    """
    The published fingerings for MAJOR_CADENCE. See `minor_cadence_tabs`.

    The A-7 is `x-x-x-x-x-9` - the melody alone, its chord dropped - where it was a
    complete four-note drop-2 & 4 at `x-10-10-x-10-9`. That shape came from one of the
    four inner-skip `drop24` sets, removed because a finger had to reach over the
    unplucked G to fret it (`docs/history/fingering.md` §4.4), and C#5 over an Am7 is a non-chord
    tone, so the set that could harmonise it was doing the *fallback* work as well: the
    only candidate left needs five frets (`x-10-x-5-10-9`), the four-fret budget refuses
    it, and the step keeps the tune and loses the chord, with a diagnostic naming the
    cause. It is the ban's one audible cost in the demos, and it is pinned rather than
    re-pinned away - if that chord is judged worth more than the ban, the alternative is
    to keep the sets and let the *selector* rank them last (measured in §4.4).
    """
    return [
        "x-x-10-10-10-10", "x-10-x-9-10-9", "x-x-x-x-x-9", "x-x-11-10-10-10",
    ]

#: The 119 hand-written drop-2 templates, keyed by the degree their top voice states.
#: This is `grips.DROP2_INTERVAL_SETS` moved out of the engine, where it was paired
#: positionally with `grips.DEGREE_OFFSETS_FROM_ROOT`: it is a *witness*, so it belongs
#: beside the assertion that reads it rather than shipping in the library. Each entry is
#: `[0, offset2, offset3, offset4]`, semitones below the soprano.
#:
#: The degrees are written lowest first for readability, and that carries no claim - the
#: witness is keyed, so only the degree-to-shape pairing is asserted anywhere.
WITNESS: Dict[str, Dict[int, List[int]]] = {
    "maj7": {
        0: [0, -5, -8, -13],
        4: [0, -5, -9, -16],
        7: [0, -7, -8, -15],
        11: [0, -7, -11, -16],
    },
    "6": {
        0: [0, -5, -8, -15],
        4: [0, -7, -9, -16],
        7: [0, -7, -10, -15],
        9: [0, -5, -9, -14],
    },
    "m7": {
        0: [0, -5, -9, -14],
        3: [0, -5, -8, -15],
        7: [0, -7, -9, -16],
        10: [0, -7, -10, -15],
    },
    "m7b5": {
        0: [0, -6, -9, -14],
        3: [0, -5, -9, -15],
        6: [0, -6, -8, -15],
        10: [0, -7, -10, -16],
    },
    "dim7": {
        0: [0, -6, -9, -15],
        3: [0, -6, -9, -15],
        6: [0, -6, -9, -15],
        9: [0, -6, -9, -15],
    },
    "m6": {
        0: [0, -5, -9, -15],
        3: [0, -6, -8, -15],
        7: [0, -7, -10, -16],
        9: [0, -6, -9, -14],
    },
    "mMaj7": {
        0: [0, -5, -9, -13],
        3: [0, -4, -8, -15],
        7: [0, -7, -8, -16],
        11: [0, -8, -11, -16],
    },
    "7": {
        0: [0, -5, -8, -14],
        4: [0, -6, -9, -16],
        7: [0, -7, -9, -15],
        10: [0, -6, -10, -15],
    },
    "7b9": {
        0: [0, -8, -11, -14],
        1: [0, -6, -9, -15],
        4: [0, -6, -9, -15],
        7: [0, -6, -9, -15],
        10: [0, -6, -9, -15],
    },
    "7alt": {
        0: [0, -8, -11, -14],
        1: [0, -5, -9, -15],
        4: [0, -6, -8, -15],
        8: [0, -7, -10, -16],
        10: [0, -6, -9, -14],
    },
    "maj9": {
        0: [0, -8, -10, -13],
        2: [0, -7, -10, -15],
        4: [0, -5, -9, -14],
        7: [0, -5, -8, -15],
        11: [0, -7, -9, -16],
    },
    "m9": {
        0: [0, -9, -10, -14],
        2: [0, -7, -11, -16],
        3: [0, -5, -8, -13],
        7: [0, -5, -9, -16],
        10: [0, -7, -8, -15],
    },
    "9": {
        0: [0, -8, -10, -14],
        2: [0, -7, -10, -16],
        4: [0, -6, -9, -14],
        7: [0, -5, -9, -15],
        10: [0, -6, -8, -15],
    },
    "6/9": {
        0: [0, -8, -10, -15],
        2: [0, -7, -10, -17],
        4: [0, -7, -9, -14],
        7: [0, -5, -10, -15],
        9: [0, -5, -7, -14],
    },
    "13": {
        0: [0, -3, -8, -14],
        4: [0, -7, -9, -18],
        7: [0, -9, -10, -15],
        9: [0, -5, -11, -14],
        10: [0, -3, -6, -13],
    },
    "maj": {
        0: [0, -8, -12, -17],
        4: [0, -9, -12, -16],
        7: [0, -7, -12, -15],
    },
    "m": {
        0: [0, -9, -12, -17],
        3: [0, -8, -12, -15],
        7: [0, -7, -12, -16],
    },
    "aug": {
        0: [0, -8, -12, -16],
        4: [0, -8, -12, -16],
        8: [0, -8, -12, -16],
    },
    "sus4": {
        0: [0, -7, -12, -17],
        5: [0, -10, -12, -17],
        7: [0, -7, -12, -14],
    },
    "sus2": {
        0: [0, -10, -12, -17],
        2: [0, -7, -12, -14],
        7: [0, -7, -12, -17],
    },
    "add9": {
        0: [0, -8, -10, -17],
        2: [0, -7, -10, -14],
        4: [0, -4, -9, -14],
        7: [0, -5, -7, -15],
    },
    "madd9": {
        0: [0, -9, -10, -17],
        2: [0, -7, -11, -14],
        3: [0, -3, -8, -13],
        7: [0, -5, -7, -16],
    },
    "7sus4": {
        0: [0, -5, -7, -14],
        5: [0, -7, -10, -17],
        7: [0, -7, -9, -14],
        10: [0, -5, -10, -15],
    },
    "7b5": {
        0: [0, -6, -8, -14],
        4: [0, -6, -10, -16],
        6: [0, -6, -8, -14],
        10: [0, -6, -10, -16],
    },
    "7#5": {
        0: [0, -4, -8, -14],
        4: [0, -6, -8, -16],
        8: [0, -8, -10, -16],
        10: [0, -6, -10, -14],
    },
    "7#11": {
        0: [0, -6, -8, -14],
        4: [0, -6, -10, -16],
        6: [0, -6, -8, -14],
        10: [0, -6, -10, -16],
    },
    "7b13": {
        0: [0, -4, -8, -14],
        4: [0, -6, -8, -16],
        8: [0, -8, -10, -16],
        10: [0, -6, -10, -14],
    },
    "maj7#11": {
        0: [0, -6, -8, -13],
        4: [0, -5, -10, -16],
        6: [0, -6, -7, -14],
        11: [0, -7, -11, -17],
    },
    "m9b5": {
        0: [0, -9, -10, -14],
        2: [0, -8, -11, -16],
        3: [0, -5, -9, -13],
        6: [0, -4, -8, -15],
        10: [0, -7, -8, -16],
    },
}



# The four bars the comping, parts and harmony tests all arrange. Shared because the
# three files assert different things about the same progression.
PROGRESSION: List[Tuple[str, str, str]] = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
]

# The two selections these tests are about, spelled **the way a caller passes them**,
# because that is the surface `voices` actually has. `VOICES_NONE` and `PART_NAMES` are the
# same data as canonical tuples; these are the strings, and the tests would not catch a
# parser that could not read what its own documentation tells a user to type.
VOICES_ARG = "chord"


def quality_of(name: str) -> str:
    """The quality half of a chord name, which is what the generators want."""
    return ChordParser.parse_chord_name(name)[1] or ""

def guide_pcs(name: str) -> set:
    """The two guide tones of a chord as absolute pitch classes.

    Raises rather than returning None for a chord with no guide tones or no readable
    root, because every caller wants them and a `None` would have to be narrowed away
    at each one - and pyright does not narrow through `assertIsNotNone`, so that
    narrowing would have to be an `assert` in every test as well.
    """
    root, quality = ChordParser.parse_chord_name(name)
    degrees = SHELL_DEGREES.get(ChordParser.canonical_quality(quality or ""))
    if not root or degrees is None:
        raise ValueError(f"{name} has no guide tones to state")
    root_pc = Note(f"{root}4").midi_note() % 12
    return {(root_pc + degree) % 12 for degree in degrees}

def chord_pcs(name: str) -> set:
    """Every tone a chord allows, as absolute pitch classes."""
    root, quality = ChordParser.parse_chord_name(name)
    root_pc = Note(f"{root}4").midi_note() % 12 if root else 0
    return {(root_pc + tone) % 12 for tone in ChordParser.get_chord_tones(quality or "")}

def comping(name: str):
    """Every comping candidate for a chord name."""
    return get_comping_voicings(quality_of(name), name)

def bass_comping(name: str):
    """Every candidate for a chord name as a **lone bass voice**."""
    return get_comping_voicings(quality_of(name), name, notes=1, bass_voice=True)

def root_of(name: str) -> int:
    """A chord name's root as an absolute pitch class, or raise.

    The bass-voice tests are about *which* note sounds, which cannot be said without the
    root, so this raises rather than guessing a default the way `chord_pcs` does: a wrong
    root here would make a correct arrangement look wrong instead of failing loudly.
    """
    root, _quality = ChordParser.parse_chord_name(name)
    if not root:
        raise ValueError(f"{name} has no readable root")
    return Note(f"{root}4").midi_note() % 12

def make_voicing(
    frets: List[int],
    grip: str = "drop2",
    bass_midi: Optional[int] = None,
    bass_string: Optional[int] = None,
) -> Voicing:
    """A `Voicing` over a raw fret list, with the derived fields filled in.

    `top_fret` and `avg_fret` are computed the way `VoiceLeadingEngine` computes
    them, because a hand-built fixture that leaves them at their defaults is a
    fixture whose `fret_span()` and voice-leading costs do not mean anything.

    Frets of -1 are muted. An all-muted list is legal and yields 0 / 0.0.
    """
    active = [f for f in frets if f >= 0]
    return Voicing(
        frets=list(frets),
        top_fret=max(active) if active else 0,
        avg_fret=sum(active) / len(active) if active else 0.0,
        grip=grip,
        bass_midi=bass_midi,
        bass_string=bass_string,
    )


def make_step(
    frets: List[int],
    chord: str = "Cmaj7",
    melody: str = "B4",
    **kwargs: Any,
) -> ArrangementStep:
    """An `ArrangementStep` over a raw fret list, with the derived voicing fields.

    Extra keyword arguments go straight to `ArrangementStep`, which is how a
    renderer test asks for `melody_only=True` or a `bass_only` slot.
    """
    return ArrangementStep(
        chord=chord,
        melody=melody,
        voicing=make_voicing(frets),
        **kwargs,
    )


def bass_string(step: ArrangementStep) -> int:
    """The string carrying the walking thumb, narrowed from `Optional[int]`.

    A plain `int(...)` at the call site satisfies pyright only if it can see the
    value is not None, and it cannot see it through a `self.assertIsNotNone` - a
    checker narrows through a bare `assert`, not through unittest's. Going through
    one function keeps that narrowing in a single place instead of scattering a
    cast across every renderer test.
    """
    value = step.voicing.bass_string
    assert value is not None, "this step carries no bass"
    return value


def note_name(midi: int) -> str:
    """Spells a MIDI number the way the library spells its own transpositions."""
    return f"{PITCH_CLASS_NAMES[midi % 12]}{midi // 12 - 1}"


def pc(name: str) -> int:
    """A pitch class by name, so a test can read as the chord rather than as numbers."""
    return PITCH_CLASS_NAMES.index(name)


def upper_shape(frets: List[int], grip: str = "shell") -> Voicing:
    """A hand-built upper shape, which is what the placement rules are stated against."""
    return make_voicing(frets, grip=grip)


def nearest_reach_for_note(
    held_frets: List[int], held_thumb: Optional[int], midi: int
) -> Optional[int]:
    """How near the hand the walk could have placed *this note*, or None if nowhere.

    The answer to "was this wide reach the placement's doing, or the note's?" - and a
    **replica**, deliberately: it writes out `bass_place.place_bass`'s filters - the string must
    be free in what the hand is holding, the note must sound below all of it, and the merged
    step must fit the four-fret budget (`fingers.can_fret`) - and then returns the
    proximity the engine ranks on, so a test can ask the question without asking the engine
    that produced the answer.

    `held_frets` is the shape still ringing and `held_thumb` its bass string, because the
    walking line reuses its own string: that string is fretted but does **not** reserve the
    string for the next note (`bass_place.place_bass` spells the same rule out), while
    `can_fret` is asked about the whole ringing hand, which is what the engine does.

    The **note**, not the pitch class: this asks where the engine could have put the note it
    decided to play, not whether another octave would have been nearer. Which octave the
    walk wants is its register decision - documented in `bass`, measured in
    `docs/open-issues.md` item 5 - and re-deciding it here would be the replica choosing
    for the engine.

    Returns the smallest `abs(fret - hand_fret)` over those candidates, where `hand_fret` is
    the lowest active fret of `held_frets` - the reference `place_bass` itself uses. None
    means the note has no position the filters allow, which cannot happen for a note the
    engine placed; a test asserts that it did not.
    """
    from arranger.fingers import can_fret
    from arranger.tuning import STANDARD_TUNING

    active = [fret for fret in held_frets if fret >= 0]
    if not active:
        return None
    hand_fret = float(min(active))
    structure = [
        -1 if index == held_thumb else fret
        for index, fret in enumerate(held_frets)
    ]
    structure_midis = [
        STANDARD_TUNING[index].midi_note() + fret
        for index, fret in enumerate(structure)
        if fret >= 0
    ]
    if not structure_midis:
        return None
    lowest_note = min(structure_midis)
    if midi >= lowest_note:
        return None
    best: Optional[int] = None
    for index, fret in enumerate(structure):
        if fret >= 0:
            continue
        candidate_fret = midi - STANDARD_TUNING[index].midi_note()
        if not 0 <= candidate_fret <= 18:
            continue
        hand = list(held_frets)
        hand[index] = candidate_fret
        if not can_fret(hand):
            continue
        proximity = abs(float(candidate_fret) - hand_fret)
        if best is None or proximity < best:
            best = int(proximity)
    return best


#: The heads a **sweep** should use. A sweep is about a *rule*, and a rule is a claim about
#: every metre the engine branches on rather than about the corpus, so three heads answer
#: it: cut time, common time, and the only odd denominator. Between them they also carry
#: the notation axes a rule can trip on - ties across a barline, a `/`-slash chord, and a
#: melody that stops before the last bar.
#:
#: One sweep is deliberately **not** on this list, and it is the one whose subject is not a
#: rule but the behaviour space itself: `test_explanations`' witness table keeps every
#: committed head, because a narrower sweep retires witnesses rather than time. Its
#: docstring says so where the sweep is.
#:
#: A fact about *one* head keeps that head (`synthetic_tab_export`'s TAB staff, the
#: triplets in `synthetic_triplets`), and the tables that are *about the corpus* keep
#: every committed head (`test_placement`'s grip distribution, the GP5 files).
SWEEP_HEADS: List[str] = [
    "synthetic_cut_time.mxl",  # 2/2 cut time, ties over barlines, a one-beat pickup rest
    "synthetic_common_8.musicxml",  # 4/4 common time, a melody-less last bar
    "synthetic_waltz.musicxml",  # 3/4 - the only simple triple in the sweep
]

#: The one committed head with chords and no melody at all, for the chords-only route.
CHORDS_ONLY_HEAD = "synthetic_chords_only.musicxml"


def sweep_head_paths() -> List[str]:
    """`SWEEP_HEADS` as paths under `tests/data`, in the order they are declared.

    Checked against the working copy rather than trusted, so a renamed fixture fails here
    naming the file instead of failing an assertion about a rule three modules away.
    """
    paths = [os.path.join("tests", "data", name) for name in SWEEP_HEADS]
    missing = [path for path in paths if not os.path.exists(path)]
    if missing:
        raise AssertionError(f"sweep heads missing from tests/data: {missing}")
    return paths


#: One arrangement per `(path, kwargs)` for the life of the process: the suite asks for the
#: same head under the same config from several tests, and inside one test per assertion.
_ARRANGEMENTS: Dict[Any, Any] = {}


def arranged(path: str, **kwargs: Any) -> Any:
    """`headxml.arrange_xml_head` remembered: one request arranged once per process.

    The whole point is that a *sweep* asserts several things about one arrangement, so the
    arranging - which is the expensive half - is paid for once. The returned value is the
    engine's own `(steps, head, notes)` triple, not a fixture built here: a cached
    arrangement is evidence, not an expectation.

    Three things a caller has to know:

    - **the steps are shared**, so a test must not write into a step or its voicing. Nothing
      does, because `bass_merge.attach_bass` writes the walking bass during the arrangement
      rather than after it;
    - a test that **monkeypatches an engine seam** must call `headxml.arrange_xml_head`
      itself or `clear_arrangements()` first - an entry made before the patch was made with
      the unpatched function, so reading it would measure nothing;
    - `section=` is part of the key, so a test that reads only the first bars pays only for
      those.

    `headxml` is imported **inside** the call: this module is imported by pure unit-test
    modules that never arrange a head, and music21 behind that import is the one import
    worth not paying for eight times.
    """
    key = (str(path), tuple(sorted(kwargs.items())))
    found = _ARRANGEMENTS.get(key)
    if found is None:
        from headxml import arrange_xml_head

        found = arrange_xml_head(path, **kwargs)
        _ARRANGEMENTS[key] = found
    return found


def clear_arrangements() -> None:
    """Forget every remembered arrangement - the seam a patched-seam test needs."""
    _ARRANGEMENTS.clear()


def walk(
    progression: List[Tuple[str, str, str]],
    onsets: Optional[List[Tuple[int, float]]] = None,
) -> List[arranger.ArrangementStep]:
    """A walking-bass arrangement of `progression`, with or without a beat grid.

    `texture="targets"` rather than a `chordN` row, and that is the load-bearing part:
    the metre decides the roles, so a strong beat states the chord and the beats the
    bass grid invents between them hold the tune under the thumb. A fixed-arity row
    makes **every** slot a target, which would re-strike the chord on every walked
    beat - a walking line with a chord on all four beats is a different arrangement.
    """
    # Annotated rather than inferred, because `Tuple` is invariant: a list of
    # `(int, float, None)` triples is not a `List[Tuple[int, float, Optional[float]]]`,
    # and pyright rejects it for exactly that reason. Assigned in a statement of its
    # own for the second half of the same trap: a conditional expression does not carry
    # the declared type into the comprehension beside it, so the annotation has to be
    # on the assignment the comprehension is. Same spelling as `BUT_NOT_FOR_ME_TIMINGS`
    # in test_texture.py.
    timings: Optional[List[Tuple[int, float, Optional[float]]]] = None
    if onsets is not None:
        timings = [(bar, beat, None) for bar, beat in onsets]
    return VoiceLeadingEngine.arrange_progression(
        progression, timings=timings, texture="targets", bass=BASS_STYLE_WALK,
        grid="melody:every_note,bass:walk",
    )


def upper_pitches(step: arranger.ArrangementStep) -> List[int]:
    """The upper voices alone: every sounding pitch except the thumb's.

    Walked from the fret vector rather than by comparing string indices, because the
    two hands do not have to agree about which string is lower - a 5-3-2 shell's
    A-string note sounds below its G-string note, which is the whole reason the
    sounding-order filter in `place_bass` cannot be a tie-break. The thumb's string
    is dropped by **fret-vector index**, never by position in a filtered list, which
    is the mistake that would silently compare a string number against a list offset.
    """
    voicing = step.voicing
    bass_string = voicing.bass_string
    return sorted(
        STANDARD_TUNING[index].midi_note() + fret
        for index, fret in enumerate(voicing.frets)
        if fret >= 0 and index != bass_string
    )


def bass_name(step: arranger.ArrangementStep) -> str:
    """The thumb's pitch class by name, or '-' when the step carries no bass."""
    if step.bass is None:
        return "-"
    return PITCH_CLASS_NAMES[step.bass % 12]


# A representative spread of the families the library voices well: sevenths, sixths,
# ninths, a half-diminished and a plain triad.
QUALITIES = [
    ("Cmaj7", "maj7"),
    ("Cm7", "m7"),
    ("C6", "6"),
    ("Cm6", "m6"),
    ("C7", "7"),
    ("Cm7b5", "m7b5"),
    ("Cdim7", "dim7"),
    ("Cm9", "m9"),
    ("C13", "13"),
    ("Cmaj", "maj"),
    ("C7sus4", "7sus4"),
]


def root_midi_of(chord_name):
    root, _ = ChordParser.parse_chord_name(chord_name)
    return Note(f"{root}4").midi_note()


def every_chord_tone(chord_name, quality):
    """Every tone of the chord, in the register around middle C.

    Built from the degrees rather than from `get_chord_tones`, which returns *absolute*
    pitch classes - adding those to the root would place a tone from a chord whose root
    is not C a tritone or more out, and a ninth would arrive as a non-chord tone.
    """
    root_pc = root_midi_of(chord_name) % 12
    degrees = {(pc - root_pc) % 12 for pc in ChordParser.get_chord_tones(quality, chord_name)}
    return [
        note_name(root_midi_of(chord_name) + degree)
        for degree in sorted(degrees)
    ]


def a_shape_on(strings):
    """A bare `Voicing` sounding exactly `strings`, for the table-level questions.

    Frets are all zero - nothing here is about where the hand is - so the shape's *strings*
    are the only thing under test. Built rather than taken from a generator because these
    questions are asked of sets the tables may no longer offer: `finger_skip_count` is what
    flagged the four removed `drop24` sets, and a test that could only ask about offered
    sets could not show what the rule costs.
    """
    frets = [-1] * 6
    for index in strings:
        frets[index] = 0
    return Voicing(frets=frets, top_fret=0, avg_fret=0.0)


# The committed scores the importer's tests read, in `tests/data/`. They are generated
# by `tests/fixture_scores.py`, except `Trouble_in_Mind_Blues.musicxml`, which is
# retained as a real notation program's export. They are committed and are NOT guarded:
# a missing fixture is a broken checkout, not a reason to pass the suite quietly.
# `tests/data/` is excepted from the `*.musicxml` / `*.mxl` rules in `.gitignore`,
# which exist for *export output*.
#
# What each one is for:
#   synthetic_cut_time.mxl       2/2, a pickup rest, a tie across a barline, a
#                                melody-less downbeat under a held note
#   synthetic_common_8.musicxml  4/4, a repeated-note bar and a melody-less last bar
#   synthetic_triplets.mxl       2/2, 10080 divisions, triplets, a repeat and endings
#   synthetic_repeat_slash.musicxml 2/2, slash chords, <degree> alterations, repeat
#   synthetic_tab_export.musicxml a TAB staff beside a notation one, chord groups
#   synthetic_waltz.musicxml     3/4, a repeat and two endings
#   synthetic_pickup_cut.musicxml 2/2, an incomplete first bar with `light-light`
#   synthetic_pickup_common.musicxml 4/4, the same shape without the bar line
#   synthetic_chords_only.musicxml four bars, six <harmony> symbols, no pitched notes
#   synthetic_five_four.musicxml 5/4, a `3+2` direction
#   synthetic_seven_four.musicxml 7/4, eighths beamed 2+2+3
#   synthetic_twelve_eight.musicxml 12/8, eighths beamed 4+4+4
#   Trouble_in_Mind_Blues.musicxml a 4/4 blues with ties across barlines, the case
#                                `TestAHeldNoteIsOneNoteAcrossABarline` pins
COMMON_8 = os.path.join(DATA, "synthetic_common_8.musicxml")
RAINY_DAY = os.path.join(DATA, "synthetic_repeat_slash.musicxml")
TROUBLE_IN_MIND = os.path.join(DATA, "Trouble_in_Mind_Blues.musicxml")
WALTZ = os.path.join(DATA, "synthetic_waltz.musicxml")
# The grouped metres: 5/4 states `3+2` in a direction, 7/4 states 2+2+3 by its
# beaming, and 12/8 states 4+4+4 by its beaming rather than the automatic threes.
FIVE_FOUR = os.path.join(DATA, "synthetic_five_four.musicxml")
SEVEN_FOUR = os.path.join(DATA, "synthetic_seven_four.musicxml")
TWELVE_EIGHT = os.path.join(DATA, "synthetic_twelve_eight.musicxml")
TENOR_MADNESS = os.path.join(DATA, "synthetic_tab_export.musicxml")
I_WAS_DOING_ALL_RIGHT = os.path.join(DATA, "synthetic_triplets.mxl")
# An **incomplete first bar**: bar 1 is a single quarter note in 2/2, closed by the
# thin double bar line a lead sheet writes after an anacrusis. Its content is one of
# the bar's four quarters, so the first written measure is the quarter note alone and
# the pickup is three quarters.
BLUE_MOON = os.path.join(DATA, "synthetic_pickup_cut.musicxml")

# The same shape without the source's bar line: 4/4, bar 1 one beat of the bar. It is
# the fixture that says the incompleteness is what makes a pickup, not the `<bar-style>`.
MISTY = os.path.join(DATA, "synthetic_pickup_common.musicxml")


# A lead sheet with **no melody at all**: four bars, six `<harmony>` symbols and not
# one pitched note (§9.3 step A'). It is the fixture the loader used to refuse.
CHORDS_ONLY = os.path.join(DATA, "synthetic_chords_only.musicxml")


def score(
    measures: str,
    divisions: int = 4,
    beats: int = 4,
    beat_type: int = 4,
    part_id: str = "P1",
    fifths: Optional[int] = None,
    mode: str = "",
    transpose: str = "",
) -> str:
    """A minimal score-partwise document around the measures given.

    `fifths` states a `<key>` when given, and omitting it writes no `<key>` at all -
    which is a real case rather than a gap in the fixture, because a score with no
    signature states C major.

    `transpose` is raw `<transpose>` XML placed in the part's `<attributes>`, so a
    test can state a transposing instrument: a guitar notated an octave above its
    sound, or a Bb horn a tone above it.
    """
    return score_bars(
        [measures],
        divisions=divisions,
        beats=beats,
        beat_type=beat_type,
        part_id=part_id,
        fifths=fifths,
        mode=mode,
        transpose=transpose,
    )


def score_bars(
    bars: Sequence[str],
    divisions: int = 4,
    beats: int = 4,
    beat_type: int = 4,
    part_id: str = "P1",
    fifths: Optional[int] = None,
    mode: str = "",
    transpose: str = "",
) -> str:
    """A score of several measures, one per entry in `bars`.

    The metre and the attributes are stated once, on the first bar, because that is
    what an exporter writes and what the importer's first-measure path expects. A
    one-bar score is `score`, which is this function with a single entry - the odd
    metres need two bars to show that a metre is not a one-bar accident.
    """
    key = "" if fifths is None else f"<key><fifths>{fifths}</fifths>{mode}</key>"
    measures = []
    for index, contents in enumerate(bars):
        attributes = ""
        if index == 0:
            attributes = (
                "      <attributes>\n"
                f"        <divisions>{divisions}</divisions>\n"
                f"        {key}\n"
                f"        <time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>\n"
                f"        {transpose}\n"
                "      </attributes>\n"
            )
        measures.append(
            f'    <measure number="{index + 1}">\n'
            f"{attributes}"
            f"      {contents}\n"
            "    </measure>"
        )
    body = "\n".join(measures)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <work><work-title>Test</work-title></work>
  <part-list><score-part id="{part_id}"><part-name>Voice</part-name></score-part></part-list>
  <part id="{part_id}">
{body}
  </part>
</score-partwise>
"""


def harmony(root: str = "C", kind: str = "major", text: Optional[str] = None,
            degrees: str = "", bass: str = "") -> str:
    """One `<harmony>` element, as a score would spell it."""
    root_xml = f"<root><root-step>{root[0]}</root-step>"
    if len(root) > 1:
        root_xml += f"<root-alter>{'-1' if root[1] == 'b' else '1'}</root-alter>"
    root_xml += "</root>"
    kind_xml = f'<kind text="{text}">{kind}</kind>' if text else f"<kind>{kind}</kind>"
    bass_xml = (
        f"<bass><bass-step>{bass[0]}</bass-step>"
        + (f"<bass-alter>{'-1' if bass[1] == 'b' else '1'}</bass-alter>" if len(bass) > 1 else "")
        + "</bass>"
        if bass
        else ""
    )
    return f"<harmony>{root_xml}{kind_xml}{bass_xml}{degrees}</harmony>"


def degree(value: int, alter: int = 0, kind_type: str = "alter") -> str:
    """One `<degree>` child, as MusicXML spells an altered tone."""
    return (
        f"<degree><degree-value>{value}</degree-value>"
        f"<degree-alter>{alter}</degree-alter>"
        f"<degree-type>{kind_type}</degree-type></degree>"
    )


def note(step: str, octave: int = 4, duration: int = 4, alter: Optional[int] = None,
         chord: bool = False, tie: str = "", tuplet: bool = False,
         lyric: Optional[str] = None, beam: str = "") -> str:
    """One `<note>` element.

    ``lyric`` states a single syllable. It is here for the importer's lyric test,
    not for the committed corpus: the synthetic fixtures carry no lyrics.
    """
    pitch = f"<pitch><step>{step}</step>"
    if alter is not None:
        pitch += f"<alter>{alter}</alter>"
    pitch += f"<octave>{octave}</octave></pitch>"
    return (
        "<note>"
        + ("<chord/>" if chord else "")
        + pitch
        + f"<duration>{duration}</duration>"
        + (f"<tie type=\"{tie}\"/>" if tie else "")
        + ("<time-modification><actual-notes>3</actual-notes>"
           "<normal-notes>2</normal-notes></time-modification>" if tuplet else "")
        + (f'<beam number="1">{beam}</beam>' if beam else "")
        + (f"<lyric><text>{lyric}</text></lyric>" if lyric is not None else "")
        + "</note>"
    )


def words(text: str) -> str:
    """A direction carrying a ``<words>`` mark, as a lead sheet writes ``3+2``."""
    return (
        "<direction><direction-type><words>"
        + text
        + "</words></direction-type></direction>"
    )


def metronome(unit: str = "quarter", *, dotted: bool = False) -> str:
    """A metronome direction naming a pulse, with an optional dot."""
    dot = "<beat-unit-dot/>" if dotted else ""
    return (
        "<direction><direction-type><metronome>"
        f"<beat-unit>{unit}</beat-unit>{dot}<per-minute>60</per-minute>"
        "</metronome></direction-type></direction>"
    )


def rest(duration: int = 4) -> str:
    return f"<note><rest/><duration>{duration}</duration></note>"


def write_score(document: str, suffix: str = ".musicxml", container: bool = False) -> str:
    """Write a document to a temp file, optionally zipped as a real `.mxl`."""
    handle, path = tempfile.mkstemp(suffix=suffix)
    os.close(handle)
    if not container:
        with open(path, "w", encoding="utf-8") as out:
            out.write(document)
        return path
    # A real container, with the score *not* first in the archive and a decoy XML
    # member beside it: both are the cases a "first .xml in the zip" reader gets
    # wrong, so both are here on purpose.
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="music/score.xml" media-type="application/vnd.recordare.musicxml+xml"/>'
            "</rootfiles></container>",
        )
        archive.writestr("META-INF/other.xml", "<junk/>")
        archive.writestr("music/score.xml", document)
    return path
