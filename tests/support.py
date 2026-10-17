"""Shared fixtures for the test suite.

Every helper here was, at some point, copy-pasted between two test files with a
docstring saying roughly *"written here rather than imported so this file stays
independent"*. That is a reasonable instinct for a test that genuinely needs its
own fixture, and the wrong one for a fixture whose whole content is "derive
`top_fret` and `avg_fret` the way the engine does" - four files had that, and they
had already begun to drift.

What is **not** here, deliberately:

* a helper two files both want but which reads better in one of them - the walked
  line's `names(chords, onsets)` in `test_bass` and a step's thumb note in
  `test_walking_bass` share a name and nothing else, so both stay local;

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
from typing import Any, Dict, List, Optional, Tuple

from musthe import Note

from arranger import (
    PITCH_CLASS_NAMES,
    SHELL_DEGREES,
    ArrangementStep,
    ChordParser,
    Voicing,
    get_comping_voicings,
)

#: The committed MusicXML fixtures. Defined once because four test modules build paths
#: from it, and a second spelling of the same directory is a second source for one fact.
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: The Gershwin head the importer, the GP5 writer and the walk all name. It is shared
#: here rather than imported from the module that happened to define it first, which is
#: the test-suite form of the private-import problem: `test_headxml` is one concern among
#: several that need this fixture, not its owner.
BUT_NOT_FOR_ME = os.path.join(DATA, "but_not_for_me.mxl")

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
    **replica**, deliberately: it writes out `bass.place_bass`'s filters - the string must
    be free in what the hand is holding, the note must sound below all of it, and the merged
    step must fit the four-fret budget (`fingers.can_fret`) - and then returns the
    proximity the engine ranks on, so a test can ask the question without asking the engine
    that produced the answer.

    `held_frets` is the shape still ringing and `held_thumb` its bass string, because the
    walking line reuses its own string: that string is fretted but does **not** reserve the
    string for the next note (`bass.place_bass` spells the same rule out), while
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
#: committed head, because that was measured - over these three, **seven of its eighteen
#: labels** are never triggered (the `NC` bar, the melody no shape can reach, the position
#: the guitar sounds nothing at), so narrowing it there would retire witnesses rather than
#: time. Its docstring says so where the sweep is.
#:
#: A fact about *one* head keeps that head (`tenor_madness`'s TAB staff, the triplets in
#: `i_was_doing_all_right`), and the tables that are *about the corpus* keep all eight
#: (`test_placement`'s grip distribution, the GP5 files).
SWEEP_HEADS: List[str] = [
    "but_not_for_me.mxl",  # 2/2 cut time, ties over barlines, lyrics
    "heres_that_rainy_day.musicxml",  # 4/4, `/`-slash chords, repeats, 66 played bars
    "The_Jitterbug_Waltz.musicxml",  # 3/4 - the only odd beat_type in the corpus
]

#: The one committed head with chords and no melody at all, for the chords-only route.
CHORDS_ONLY_HEAD = "lead_sheet_chords_only.musicxml"


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
