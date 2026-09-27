from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Container, List, Optional, Sequence, Tuple, Dict, Any
from musthe import Note, Chord, Interval

# Standard tuning pitches in MIDI / Pitch class equivalents
# String 6 (Low E, index 0) to String 1 (High E, index 5)
STANDARD_TUNING = [
    Note("E2"), Note("A2"), Note("D3"), 
    Note("G3"), Note("B3"), Note("E4")
]

STRING_NAMES = ["E", "A", "D", "G", "B", "E"]

# Pitch-class names, used when a substitution has to be spelled back into a chord
# name (e.g. the dim7 a semitone below a resolution target). Flats are preferred
# because that is the common jazz spelling for the chords this library builds.
PITCH_CLASS_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# The Weimar Jazz Database's "no chord" marker: a bar that carries melody but no
# harmony. Such a step is voiced as melody alone - no harmonisation, no
# reharmonisation, no warning (see VoiceLeadingEngine.get_melody_only_voicing).
NO_CHORD = "NC"

# Soprano (melody) string indices a Drop-2 voicing may be pinned to, and the four
# contiguous strings each one uses. Index 0 = low E ... index 5 = high E.
#   5 -> strings D-G-B-E, melody on the high E string (traditional shape)
#   4 -> strings A-D-G-B, melody on the B string, one position lower on the neck
MELODY_STRING_CHOICES = (5, 4)

# The full set of strings a melody may be voiced on: high E (string 1), B (string 2)
# and G (string 3). Adding the G string is what lets a melodic position be held by
# *changing strings* rather than by moving the hand up or down the neck, which is the
# whole point of the position-aware selector in VoiceLeadingEngine._best_voicing.
#
# A G-string melody only ever reaches a three-note shape, because only the D and low
# E strings lie below it - and a shell on those two is the 6-4-3 grip. The A string
# and the low E string are therefore *inner voices only*: no harmonised grip puts the
# soprano on either. The floor of the melody range consequently rises from B3 to G3
# (the open G string) while the *chord* range extends down to E2 as a bass voice.
MELODY_STRING_CHOICES_FULL = (5, 4, 3)

# The comfortable neck window. Both ends are a strong *preference*, not a filter: a
# voicing is penalised by how many of its frets fall outside, never rejected for
# falling outside. A filter would silently drop every step whose melody has no
# in-window shape, and arrange_progression already skips such a step with a warning -
# losing a chord of the tune to keep a fretboard preference would be a bad trade.
NECK_FRET_MIN = 2
NECK_FRET_MAX = 13

# Grip families, in the order that breaks an exact tie. A four-note drop-2 shape is
# listed first so it is never displaced by a shell when the two cost the same.
#
# `drop3` and `closed` are generated but deliberately *not* listed here, because neither
# can be played within this library's span limit. A close-position four-note chord
# under a melody spans a seventh or more, and the four strings below the high E are only
# five semitones apart in tuning, so the frets come out more than five apart: Cmaj7 in
# close position under C5 wants frets 8, 12, 12 and 14. Drop-3 is worse, spanning a
# twelfth by construction. The generators stay, so a caller who raises GRIP_MAX_SPAN
# can reach them, but advertising them as a default would be a promise the span
# invariant cannot keep.
GRIP_PREFERENCE: Tuple[str, ...] = ("drop2", "shell", "duo")

# The maximum distance, in frets, from the soprano to any other finger. Five for every
# four-note shape and every three-note shell; a duo is only ever two fingers, so it is
# held to a tighter four.
GRIP_MAX_SPAN: Dict[str, int] = {
    "drop2": 5,
    "drop3": 5,
    "closed": 5,
    "shell": 5,
    "duo": 4,
}

# Every string set a grip may occupy, as (active string indices, soprano string
# index), ordered by preference. Index 0 = low E ... index 5 = high E, so the
# conventional string number is 6 - index.
#
# (0, 2, 3) is the 6-4-3 shell: low E, D and G, deliberately skipping the A string.
# It is the only non-contiguous set here, and it is the reason a G-string soprano can
# carry a full three-note shell at all - without it only the D string lies below the
# G string, which would cap a G-string melody at two voices.
GRIP_STRING_SETS: Dict[str, Tuple[Tuple[Tuple[int, ...], int], ...]] = {
    # The two traditional four-string blocks. There is deliberately no four-note block
    # for a G-string soprano: 6-5-4-3 with the melody on top does not sound good, so a
    # low melody is harmonised with a three-note shell instead - see the note below.
    #   (2, 3, 4, 5) -> strings 4-3-2-1, melody on the high E
    #   (1, 2, 3, 4) -> strings 5-4-3-2, melody on the B string
    "drop2": (((2, 3, 4, 5), 5), ((1, 2, 3, 4), 4)),
    "drop3": (((2, 3, 4, 5), 5), ((1, 2, 3, 4), 4)),
    "closed": (((2, 3, 4, 5), 5), ((1, 2, 3, 4), 4)),
    # Three-note shells: 1-2-3, 2-3-4, 5-4-3, the 6-4-3 that skips the A string, and
    # the 5-3-2 that skips the D string. A G-string melody has two shapes available,
    # 5-4-3 and 6-4-3, and the selector chooses between them like any other pair.
    #
    # 5-3-2 (A, G, B, melody on the B string) is the only shell whose A-string note
    # sounds *below* its G-string neighbour without the low E: the A is tuned five
    # semitones above the D it skips, and the G is five above that, so the pitches
    # descend while the string numbers ascend. Measured across 120 transcriptions it
    # adds no coverage at all - never the only shape for a melody - but it relocates
    # 1.3% of steps, always onto a better melodic position: F7 with a Db4 soprano
    # moves from `x-6-7-6-x-x` to `x-6-x-2-2-x`, the same three pitches with the
    # melody at B-string fret 2 instead of G-string fret 6. That is the whole point of
    # allowing the melody to hold its place by changing strings. It needs the search
    # in _place_shell, not stacking, for the same reason 6-4-3 does.
    "shell": (
        ((5, 4, 3), 5), ((4, 3, 2), 4), ((1, 2, 3), 3),
        ((0, 2, 3), 3), ((1, 3, 4), 4),
    ),
    # Duos: 1-2, 2-3 and 3-4, each with the higher note carrying the melody.
    "duo": (((5, 4), 5), ((4, 3), 4), ((3, 2), 3)),
}

# The two guide tones a shell is built from - the 3rd and the 7th - as semitones above
# the root. The table is explicit rather than derived because the house rule is never
# to guess a chord: a quality that is not listed simply has no shell, and the
# selector falls back to a four-note grip for it. Triads and suspended chords appear
# here with their nearest available pair (a triad's "7th" slot is its 5th), because a
# shell under a triad is just the triad in a playable position.
SHELL_DEGREES: Dict[str, Tuple[int, int]] = {
    "maj7": (4, 11), "m7": (3, 10), "m7b5": (3, 10), "dim7": (3, 9),
    "m6": (3, 9), "mMaj7": (3, 11), "maj9": (4, 11), "m9": (3, 10),
    "m9b5": (3, 10), "maj7#11": (4, 11),
    "6": (4, 9), "6/9": (4, 9), "madd9": (3, 7), "add9": (4, 7),
    "7": (4, 10), "9": (4, 10), "13": (4, 9), "7b9": (4, 10), "7alt": (4, 10),
    "7b13": (4, 10), "7#11": (4, 10), "7b5": (4, 10), "7#5": (4, 10),
    "7sus4": (5, 10),
    "maj": (4, 7), "m": (3, 7), "aug": (4, 8), "sus4": (5, 7), "sus2": (2, 7),
}

# The four lowest strings. A four-note voicing here is deliberately NOT offered, and
# this constant is the only place that says so.
#
# With the melody on the G string, a four-note shape would necessarily occupy all four
# of 6-5-4-3, and that does not sound good: it puts four voices in the bottom fourth of
# the compass, where the low E and the A string crowd each other and the chord loses
# its top. A low melody is harmonised with a three-note **shell** instead - 5-4-3 or
# 6-4-3 - which is the ordinary answer for a chord-melody line in this register, and
# which drops the 5th degree, the one the four-note shape was contributing there.
# A low melody is therefore never harmonised with more than three voices here.
# A frozenset, because it is compared against a set of sounding strings.
_BOTTOM_FOUR = frozenset((0, 1, 2, 3))

# The only soprano degrees a duo is generated for. When the melody is the root or the
# 5th the ear supplies the missing guide tones, so two voices are enough; under a 3rd
# or a 7th they are the entire definition of the chord's function, and a bare duo
# there is the voicing that sounds wrong. This is a hard rule - get_grip_voicings
# returns nothing for any other melody - and not a cost preference, so there is no
# last-resort escape hatch.
DUO_DEGREES: Tuple[int, int] = (0, 7)


def supported_string_sets() -> List[frozenset]:
    """
    Every set of strings a generated voicing may sound, as a set of frozensets.

    This is the playability invariant, stated in one place: a voicing's sounding
    strings must be exactly one of these, and must contain the melody on its topmost
    one. It includes the four-string drop-2 blocks, which `GRIP_STRING_SETS` does not
    list because drop-2 is defined generically - "the four strings below the soprano" -
    so that a caller passing their own `top_string` still works. Tests use this rather
    than re-deriving the rule, so a new grip cannot quietly escape the invariant.

    The bottom four strings are excluded, deliberately: see `_BOTTOM_FOUR`.
    """
    sets = {
        frozenset(range(top - 3, top + 1))
        for top in MELODY_STRING_CHOICES_FULL
        if frozenset(range(top - 3, top + 1)) != _BOTTOM_FOUR
    }
    for shapes in GRIP_STRING_SETS.values():
        sets.update(frozenset(strings) for strings, _ in shapes)
    return sorted(sets, key=lambda s: sorted(s))

# The neck position above which the melody is transposed down an octave and voiced on
# the B string instead of up at the top of the high E string. The B string is five
# semitones below the high E, so the same written pitch sits five frets *higher* on it
# (D5 is fret 10 on the high E, fret 15 on the B) - the only way to bring a high melody
# down the neck is to drop it an octave and let the B string play it an octave lower.
# A voicing whose soprano is above this fret is therefore re-voiced an octave down.
HIGH_FRET_LIMIT = 13

# Library version. Kept here as the single source of truth; pyproject.toml reads
# it via [tool.setuptools.dynamic] instead of duplicating the number.
# 0.4.0 added the optional Weimar Jazz Database corpus integration (wjazzd.py).
# 0.5.0 added MusicXML export (tabxml.py), behind the optional `xml` extra.
__version__ = "0.5.0"


@dataclass
class Voicing:
    """Represents a specific fretboard voicing."""
    frets: List[int]
    top_fret: int
    avg_fret: float
    # Which grip family produced this shape, one of GRIP_PREFERENCE. Purely
    # informational - nothing about playability or rendering depends on it - but it is
    # how a caller (and the tests) can tell a four-note drop-2 from a three-note shell.
    # Defaulted, so existing construction and the __getitem__ shim are unaffected.
    grip: str = "drop2"
    # The pitch class of the lowest sounding voice, or None for an all-muted shape.
    # Cached so the corpus slash-bass rule (wjazzd.bass_cost) does not have to
    # re-derive it, and so a caller can ask "what is the bass of this grip" directly.
    bass_pc: Optional[int] = None

    def tab_string(self) -> str:
        """Returns standard tab representation, e.g. 'x-x-12-13-13-13'."""
        return "-".join(str(f) if f >= 0 else "x" for f in self.frets)

    def tab_block(self) -> List[str]:
        """
        Renders the voicing as a six-line vertical tab, highest string first.

        Each line is labelled with the string name and holds the fret cell for
        that string, right-aligned to two characters so frets 0-9, 10-18 and
        the muted 'x' all line up in a column:

            e|--0---3---|
            B|--1---3---|
            G|--0---2---|
            D|--3---3---|
            A|-x-------|
            E|-x-------|

        Returns exactly six lines, one per string, ordered high E (string 1)
        down to low E (string 6) the way tab is read. A fully muted voicing
        renders as six 'x' lines rather than raising. Purely a render: it
        prints nothing, so callers decide how to display it.
        """
        return _tab_block_from_cells(_cells_from_frets(self.frets))

    def tab(self) -> str:
        """Returns tab_block() as a single newline-joined string."""
        return "\n".join(self.tab_block())

    def active_frets(self) -> List[int]:
        """Returns list of fret positions for played strings."""
        return [f for f in self.frets if f >= 0]

    def fret_span(self) -> int:
        """Returns the physical fret span between lowest and highest active fret."""
        active = self.active_frets()
        if not active:
            return 0
        return max(active) - min(active)

    def midi_notes(self) -> List[int]:
        """Calculates MIDI pitches played on each active string."""
        midis = []
        for s_idx, f in enumerate(self.frets):
            if f >= 0:
                midis.append(GuitarFretboard.fret_to_midi(s_idx, f))
        return midis

    def pitch_classes(self) -> List[int]:
        """Calculates pitch classes (0-11) of the active notes."""
        return [m % 12 for m in self.midi_notes()]

    def soprano_string(self) -> int:
        """
        Returns the index of the highest sounding string (0 = low E ... 5 = high E).

        This is the **index** used everywhere else in this module; the conventional
        guitar string number is 6 - index (index 5 = string 1 = high E, index 4 =
        string 2 = B). Returns -1 when every string is muted.
        """
        active = [s_idx for s_idx, f in enumerate(self.frets) if f >= 0]
        return max(active) if active else -1

    @property
    def active_strings(self) -> List[int]:
        """
        The indices of the strings that sound, in ascending (low to high) order.

        This is the shape of the grip: two to four strings, all of them from one
        GRIP_STRING_SETS entry. It is what a caller checks when it wants to know
        whether a voicing really is the shape it claims to be.
        """
        return [s_idx for s_idx, f in enumerate(self.frets) if f >= 0]

    @property
    def fret_on_soprano(self) -> int:
        """
        The fret under the highest sounding string, or -1 when all strings are muted.

        Compared against another voicing's this measures *neck position*, which is the
        thing a player has to travel: fret numbers mean the same place on the neck
        whichever string they are on, so this stays meaningful when a melody holds its
        place by moving to a different string.
        """
        soprano = self.soprano_string()
        return -1 if soprano < 0 else self.frets[soprano]

    # Backward compatibility: dictionary-like indexing step["voicing"]["frets"]
    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


@dataclass
class ArrangementStep:
    """Represents one chord-melody step in an arranged progression."""
    chord: str
    melody: str
    voicing: Voicing
    # Non-chord-tone bookkeeping, filled in by arrange_progression. Defaults keep
    # the dataclass and its dict-style shim backward compatible.
    non_chord_tone: bool = False
    strategy: Optional[str] = None
    harmonized_as: Optional[str] = None
    # True for a step that was arranged melody-only because its chord slot was
    # NO_CHORD. Defaulted, so existing construction and the __getitem__ shim are
    # unaffected. A melody-only step is deliberately NOT a drop-2 voicing: it has
    # a single active fret and does not obey the four-string playability invariant.
    melody_only: bool = False
    # The melody as written, when the step was transposed down an octave to keep the
    # voicing below HIGH_FRET_LIMIT (see VoiceLeadingEngine.get_octave_down_candidates).
    # In that case `melody` holds the transposed note that actually sounds and this
    # holds the pitch the progression asked for, so the renderer can show both.
    # Defaulted to None, so an ordinary step is unaffected.
    original_melody: Optional[str] = None
    # Optional timing, in the same units the Weimar Jazz Database uses: `bar` is
    # signed (pickups are negative), `beat` is the beat *within* the bar, and
    # `duration` is in whole notes. All three default to None so plain
    # construction and the __getitem__ shim are unaffected, and so a progression
    # written by hand simply has no rhythm to render. When they are present the
    # staff renderer can space the chords on their real beats instead of one per
    # cell; when they are absent it falls back to a uniform grid.
    bar: Optional[int] = None
    beat: Optional[float] = None
    duration: Optional[float] = None
    # True when this step's melody sounds the same pitch as the step before it. The
    # step is then played as a *single note*: only the soprano string is struck and
    # the rest are muted, the way a player reads a held melody rather than re-fingering
    # the chord. The voicing is still generated in full - the engine needs a real shape
    # to voice lead from, and `tab_line()` returns it for a caller who wants it.
    # Defaulted to False, so an ordinary step and every existing construction are
    # unaffected. See VoiceLeadingEngine.arrange_progression, which sets it.
    #
    # Note the consequence across a chord change (ATTYA bars 61-63 hold C4 over
    # F-7, Bb-7, Eb7): the inner voices sounding under the held note belong to the
    # chord the hold started on, not the one written above it.
    repeated: bool = False
    # Which grip family harmonised this step, mirroring voicing.grip. One of
    # GRIP_PREFERENCE for an ordinary chord, "melody" for a no-chord step. Defaulted,
    # so an existing hand-built ArrangementStep is unaffected.
    grip: str = "drop2"
    # True when a chorded step is harmonised with fewer than four voices, i.e. it is a
    # shell or a duo rather than a complete chord. The chord name printed above such a
    # step describes the harmony, not every note sounding under it, so the renderers
    # annotate it. Defaulted, so an ordinary four-note step is unaffected.
    partial: bool = False

    @property
    def has_timing(self) -> bool:
        """
        True when this step carries a bar and beat, i.e. it can be placed on a
        rhythmic grid. A hand-written progression has no timing, so the renderer
        has to fall back to a uniform grid for it.
        """
        return self.bar is not None and self.beat is not None

    def tab_line(self) -> str:
        """Returns the one-line tab for this step, e.g. 'x-x-12-13-13-13'."""
        return self.voicing.tab_string()

    def tab_block(self) -> List[str]:
        """Returns the six-line vertical tab for this step's voicing."""
        return self.voicing.tab_block()

    # Backward compatibility: dictionary-like indexing step["chord"], step["voicing"]
    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


class GuitarFretboard:
    """Handles mapping notes to physical guitar fretboard positions."""
    
    @staticmethod
    def note_to_fret(string_index: int, note: Note) -> int:
        """Calculates the fret number for a given note on a specific string (0 = Low E)."""
        if string_index < 0 or string_index >= len(STANDARD_TUNING):
            return -1
        open_note = STANDARD_TUNING[string_index]
        semitones = note.midi_note() - open_note.midi_note()
        return semitones if 0 <= semitones <= 18 else -1

    @staticmethod
    def fret_to_midi(string_index: int, fret: int) -> int:
        """Calculates MIDI note number for a string and fret."""
        if string_index < 0 or string_index >= len(STANDARD_TUNING) or fret < 0:
            return -1
        return STANDARD_TUNING[string_index].midi_note() + fret


def _note_name(midi: int) -> str:
    """
    Spells a MIDI number as a pitch-class name plus octave, e.g. 82 -> 'Bb5'.

    Used when a step has been transposed down an octave and has to report the pitch
    that actually sounds. Flats are preferred, matching PITCH_CLASS_NAMES and the
    jazz spelling used elsewhere in this module. Takes a raw MIDI number because
    musthe.Note only parses a string, so an octave-transposed pitch has to be
    spelled before it can be rebuilt as a Note.
    """
    return f"{PITCH_CLASS_NAMES[midi % 12]}{midi // 12 - 1}"


def _melody_only_string_order(prefer: Tuple[int, ...]) -> List[int]:
    """
    String indices to try for a melody-only voicing: those in `prefer` first (in
    the order given), then every other string from the highest sounding one down.

    Duplicates and out-of-range indices in `prefer` are ignored, so a caller
    cannot make the search repeat a string or index past the fretboard.
    """
    order: List[int] = []
    top = len(STANDARD_TUNING) - 1
    for string_index in list(prefer) + list(range(top, -1, -1)):
        if 0 <= string_index <= top and string_index not in order:
            order.append(string_index)
    return order


# --- Grip generation -------------------------------------------------------
#
# Everything below turns a chord quality and a melody note into semitone offsets
# below the soprano. It is deliberately separate from VoiceLeadingEngine so the
# theory - which notes go in a grip, and in what order - is stated once and can be
# read without reading the search that follows it.


def _nearest_tone_below(midi: int, pitch_class: int, max_drop: int = 24) -> Optional[int]:
    """
    The highest pitch at or below `midi` that has `pitch_class`, or None.

    Working in real pitches rather than in differences of pitch classes is what keeps
    octave placement honest. The root below a major 3rd is a major sixth down, not a
    major third down: taking the mod-12 difference and calling it the distance puts
    the root a fourth too high and produces voicings that spell the wrong octave.
    """
    for drop in range(max_drop + 1):
        candidate = midi - drop
        if candidate % 12 == pitch_class % 12:
            return candidate
    return None


def _close_stack_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: Optional[int] = None
) -> List[int]:
    """
    A four-voice close-position stack under the melody, as semitone offsets.

    Each voice is the nearest chord tone below the one above it, so the result is the
    tightest four-note chord that fits under the melody. `tones` are pitch classes,
    absolute or relative to `root_pc`; passing the root makes the search a walk *down
    the chord* rather than down the keyboard, which is what a triad needs - with only
    three tones the walk simply wraps to the root an octave below, doubling it, so
    there is no special case for triads.

    Returns fewer than four offsets when the walk cannot continue, which the caller
    treats as "this quality has no four-note shape here".
    """
    if not tones:
        return []
    offsets = [0]
    current = melody_midi
    for _ in range(3):
        nxt: Optional[int] = None
        for tone in tones:
            absolute = tone if root_pc is None else (root_pc + tone) % 12
            found = _nearest_tone_below(current - 1, absolute)
            if found is not None and (nxt is None or found > nxt):
                nxt = found
        if nxt is None:
            break
        current = nxt
        offsets.append(current - melody_midi)
    return offsets


def _interval_set_for_grip(
    quality: str,
    grip: str,
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: Optional[int] = None,
) -> List[List[int]]:
    """
    The interval templates for a quality under a given grip, as offsets from the
    soprano (0 for the melody itself, negative below it).

    `drop2` returns DROP2_INTERVAL_SETS verbatim and derives nothing. Those tables are
    hand-authored: the extended qualities are voiced *rootless* on purpose, so a 9 or a
    13 that fits into four voices without the root is a musical decision rather than an
    accident of a stack search. Deriving drop-3 and close position from the same chord
    tones therefore gives a fuller chord - a legitimate but different voicing - and it
    is precisely why drop-2's own table is left alone.

    drop-2, drop-3 and close position share one close-position stack of four voices,
    taken as v1, v2, v3, v4 from the top:

        close position    v1  v2  v3  v4
        drop 2            v1  v3  v4  (v2 down an octave)
        drop 3            v1  v2  v4  (v3 down an octave)

    which is the usual definition: a drop-N voicing is a close-position stack with the
    Nth voice from the top lowered by an octave. The last voice of a drop-2 is
    therefore the octave of v2, not v4 - which is what makes the 3rd and the 7th of a
    seventh chord land on the D and G strings in the familiar 4-3-2-1 shell shape.
    """
    if grip == "drop2":
        return VoiceLeadingEngine.DROP2_INTERVAL_SETS.get(quality, [])

    if grip not in ("drop3", "closed"):
        return []

    stack = _close_stack_offsets(tones, melody_midi, root_pc)
    if len(stack) < 4:
        return []

    # stack[0] is the melody itself, so the three voices below it are stack[1:]. The
    # templates then read 0 (soprano), v1, v2, v3 as the four voices in the order they
    # sound.
    _, v1, v2, v3 = stack
    if grip == "closed":
        return [[0, v1, v2, v3]]
    # Drop 3: the third voice from the top drops an octave, so it lands below the
    # bottom voice and the shape closes with a 2nd at the bottom.
    return [[0, v1, v2 - 12, v3]]


def _duo_offsets(tones: Tuple[int, ...], melody_midi: int, root_pc: int) -> List[int]:
    """
    A two-note grip under the melody, or an empty list.

    Only ever a root or a 5th in the melody (DUO_DEGREES): there the ear supplies the
    guide tones, so two voices carry the harmony. A 3rd or a 7th in the melody is
    precisely the note that defines the chord's function, and pairing it with one
    other note is the voicing that sounds like a mistake - so this returns nothing and
    the selector has to find a shell or a complete shape instead.

    The second voice is the 3rd, which is what keeps the pair from being an empty
    fifth. A triad has no 3rd-and-7th distinction, so a 5th-top triad falls back to
    its own third, or to the root when the chord is a suspended fourth.
    """
    if (melody_midi - root_pc) % 12 not in DUO_DEGREES:
        return []

    # Preference order: the chord's own 3rd, then the minor 3rd for a chord that has
    # no major one, then the root for a suspended chord with nothing else available.
    third = next((d for d in (4, 3, 0) if d in tones and d not in DUO_DEGREES), None)
    if third is None:
        return []

    pitch = _nearest_tone_below(melody_midi, (root_pc + third) % 12)
    if pitch is None:
        return []
    return [0, pitch - melody_midi]


def _place_shell(
    quality: str,
    tones: Tuple[int, ...],
    root_pc: int,
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Optional[Voicing]:
    """
    A three-note shell on one string set, found by searching rather than stacking.

    This needs its own placement for the same reason 6-4-3 does, and the reason is not
    specific to that shape: **a shell's notes are not in descending pitch order down the
    strings.** The tuning is not monotonic in the useful direction. The A string is
    tuned five semitones *above* the D string, and the D string five above the G, so a
    note fretted on the lower string can easily sound higher than its neighbour. A G7
    shell under G3 is `2-3-0-x-x-x` - B2 on the A string, F3 on the D string, G3 on the
    G - and the A string is carrying the *lower* note while being the higher string.
    Any model that lays the voices on strings from the top down by pitch gets this
    backwards and finds nothing.

    So the shape is found by searching: the melody is held at `top_fret` on the soprano
    string and every combination of frets within the span limit is tried on the
    remaining strings, keeping the ones where the guide tones sound and nothing outside
    the chord does. Because the search window is exactly the span limit, the search is
    *exhaustive within the playability invariant* - if a playable shell exists in this
    position, this finds it, which is a stronger guarantee than stacking a nearest-tone
    stack and hoping.

    Ties are broken by fret spread, then by position, so the shape a player would pick
    wins over the first one the search happens to reach.
    """
    guide = SHELL_DEGREES.get(quality)
    if guide is None or len(strings) < 3:
        return None
    allowed = {(root_pc + t) % 12 for t in tones}
    needed = {(root_pc + g) % 12 for g in guide}
    limit = GRIP_MAX_SPAN["shell"]

    lo = max(0, top_fret - limit)
    hi = top_fret + limit
    if hi > 18:
        return None

    best: Optional[Tuple[int, float, Voicing]] = None
    for first in range(lo, hi + 1):
        for second in range(lo, hi + 1):
            frets = [-1] * len(STANDARD_TUNING)
            frets[strings[0]] = top_fret
            frets[strings[1]] = first
            frets[strings[2]] = second
            active = [top_fret, first, second]
            if max(active) - min(active) > limit:
                continue
            midis = sorted(
                GuitarFretboard.fret_to_midi(str, fret)
                for str, fret in zip(strings, (top_fret, first, second))
            )
            pcs = {m % 12 for m in midis}
            # Both guide tones have to sound, and nothing outside the chord may.
            if not needed <= pcs or not pcs <= allowed:
                continue
            spread = max(active) - min(active)
            voicing = Voicing(
                frets=frets,
                top_fret=top_fret,
                avg_fret=sum(active) / len(active),
                grip="shell",
                bass_pc=min(midis) % 12,
            )
            key = (spread, voicing.avg_fret)
            if best is None or key < best[:2]:
                best = (spread, voicing.avg_fret, voicing)
    return best[2] if best else None


def _place_template(
    template: List[int],
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
    grip: str,
) -> Optional[Voicing]:
    """
    Fits an interval template onto a string set, or returns None if it will not play.

    The voices go on the strings from the top down, so the template's order is the
    order they are heard. Playability is the rule the drop-2 engine has always used:
    every fret on the board, and a hand that does not stretch - `fret_span() <= 5`.

    The span is checked on the frets actually placed, not as "within N of the soprano".
    Those are not the same condition: bounding each finger to five frets either side of
    the soprano permits a span of ten, which is exactly what the 6-4-3 shell produced
    before this was caught - the low E and D strings are five semitones apart in tuning,
    so a shell that sounds correctly on them can sit at frets 8 and 0.

    Strings in the set the template does not use are left muted, which is how a
    three-note shell sits inside a four-string set and how 6-4-3 leaves the A string
    alone without saying anything special about it.
    """
    if len(template) > len(strings):
        return None

    frets = [-1] * len(STANDARD_TUNING)
    frets[strings[0]] = top_fret
    limit = GRIP_MAX_SPAN.get(grip, 5)

    for position, offset in enumerate(template[1:], start=1):
        string_idx = strings[position]
        fret = melody_midi + offset - STANDARD_TUNING[string_idx].midi_note()
        if not 0 <= fret <= 18:
            return None
        frets[string_idx] = fret

    active = [f for f in frets if f >= 0]
    if max(active) - min(active) > limit:
        return None
    midis = sorted(
        GuitarFretboard.fret_to_midi(s, f) for s, f in enumerate(frets) if f >= 0
    )
    return Voicing(
        frets=frets,
        top_fret=top_fret,
        avg_fret=sum(active) / len(active),
        grip=grip,
        bass_pc=midis[0] % 12 if midis else None,
    )


class ChordParser:
    """Parses chord symbols and identifies harmonic degrees."""

    # Canonical chord-quality spellings. Keys are every accepted spelling; values
    # are the keys used by DROP2_INTERVAL_SETS / DEGREE_OFFSETS_FROM_ROOT. The
    # lookup is case-sensitive on purpose: "M7" is a major seventh while "m7" is a
    # minor seventh, so normalising with .lower() would confuse the two families.
    QUALITY_ALIASES = {
        # minor family
        "min7": "m7",
        "min7b5": "m7b5",
        "ø7": "m7b5",
        "ø": "m7b5",
        "half-dim": "m7b5",
        "min6": "m6",
        "minMaj7": "mMaj7",
        "mmaj7": "mMaj7",
        "min9": "m9",
        # diminished
        "°7": "dim7",
        "°": "dim7",
        "dim": "dim7",
        # dominant family
        "dom7": "7",
        "dom9": "9",
        "dom13": "13",
        # major family
        "M7": "maj7",
        "M9": "maj9",
        "69": "6/9",
        # triads and suspended chords. Note the bare major-third symbol "M" is a
        # triad here while "M7" stays a major seventh; "dim" deliberately keeps
        # resolving to dim7 (the diminished triad is not voiced by this library).
        "M": "maj",
        "min": "m",
        "-": "m",
        # The Weimar Jazz Database spells a minor seventh with a leading hyphen
        # ("F-7"), and its own table already maps that to m7. Recognising the suffix
        # here as well means a chord name written either way resolves to one chord,
        # which is what comparing two steps' harmony depends on. Without it a name
        # like "D-7" parsed to the unusable quality "-7".
        "-7": "m7",
        "+": "aug",
        "sus": "sus4",
        "7sus": "7sus4",
    }

    # Every chord tone of each quality, as pitch classes relative to the root
    # (0 = root). This is deliberately *separate* from the drop-2 templates: it
    # answers "is this melody note in the chord?", including tones the four-note
    # voicings omit (the root of a rootless 7b9, or the 9th of a maj9).
    CHORD_TONES_FROM_ROOT: Dict[str, Tuple[int, ...]] = {
        # Seventh/sixth chords whose four tones are all voiced
        "maj7": (0, 4, 7, 11),
        "6": (0, 4, 7, 9),
        "m7": (0, 3, 7, 10),
        "m7b5": (0, 3, 6, 10),
        "dim7": (0, 3, 6, 9),
        "m6": (0, 3, 7, 9),
        "mMaj7": (0, 3, 7, 11),
        "7": (0, 4, 7, 10),
        # Altered dominants voiced without their root; the root is still a chord tone
        "7b9": (0, 1, 4, 7, 10),
        "7alt": (0, 1, 3, 4, 6, 8, 10),
        # Extended qualities, voiced rootless as four-note drop-2 shapes
        "maj9": (0, 2, 4, 7, 11),
        "m9": (0, 2, 3, 7, 10),
        "9": (0, 2, 4, 7, 10),
        "6/9": (0, 2, 4, 7, 9),
        "13": (0, 2, 4, 7, 9, 10),
        # Triads and suspended chords. A drop-2 shape needs four voices, so the
        # triad templates double the root an octave below the stack.
        "maj": (0, 4, 7),
        "m": (0, 3, 7),
        "aug": (0, 4, 8),
        "sus4": (0, 5, 7),
        "sus2": (0, 2, 7),
        # Added-note colours
        "add9": (0, 2, 4, 7),
        "madd9": (0, 2, 3, 7),
        # Suspended and altered dominants
        "7sus4": (0, 5, 7, 10),
        "7b5": (0, 4, 6, 10),
        "7#5": (0, 4, 8, 10),
        # Colour qualities whose four-note shapes omit a tone, so the full tone
        # set is deliberately wider than the notes any one shape sounds.
        "7#11": (0, 4, 6, 7, 10),
        "7b13": (0, 4, 7, 8, 10),
        "maj7#11": (0, 4, 6, 7, 11),
        "m9b5": (0, 2, 3, 6, 10),
    }

    @staticmethod
    def canonical_quality(chord_type: Optional[str]) -> str:
        """
        Normalises a chord quality to its canonical spelling.

        Aliases are resolved case-sensitively (so 'M7' -> 'maj7' but 'm7' stays
        'm7'), which also fixes the historical case bug where 'mMaj7'.lower()
        produced 'mmaj7' and silently missed every table lookup. Unknown
        qualities are returned unchanged so callers can report them.
        """
        if not chord_type:
            return ""
        quality = chord_type.strip()
        return ChordParser.QUALITY_ALIASES.get(quality, quality)

    @staticmethod
    def parse_chord_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Extracts root pitch and quality string from chord name (e.g. 'Dm7b5' -> ('D', 'm7b5'))."""
        if not name:
            return None, None
        m = re.match(r"^([A-G][#b]?)(.*)$", name.strip())
        if m:
            return m.group(1), m.group(2)
        return None, None

    @staticmethod
    def get_melody_degree(root_str: str, melody_note: Note) -> int:
        """Returns the melody note interval class (0-11) relative to chord root."""
        root_midi = Note(root_str + "4").midi_note()
        return (melody_note.midi_note() - root_midi) % 12

    @staticmethod
    def get_chord_tones(chord_type: str, chord_name: Optional[str] = None) -> Tuple[int, ...]:
        """
        Returns the pitch classes (0-11) of every tone in a chord quality.

        With chord_name the pitch classes are absolute; without it they are
        relative to the root (0 = root). Unknown qualities return an empty tuple.
        """
        tones = ChordParser.CHORD_TONES_FROM_ROOT.get(ChordParser.canonical_quality(chord_type), ())
        if not tones or not chord_name:
            return tones
        root_str, _ = ChordParser.parse_chord_name(chord_name)
        if not root_str:
            return tones
        root_pc = Note(root_str + "4").midi_note() % 12
        return tuple((root_pc + pc) % 12 for pc in tones)

@dataclass
class StepPreparation:
    """One step's voicing candidates, plus the bookkeeping to report the step.

    Returned by `VoiceLeadingEngine.prepare_step` so a caller that needs extra
    per-step control - the corpus loader honours a slash bass and attaches the
    slot's timing - can choose from these candidates using the engine's own rule
    rather than re-deriving the voicing itself.

    That distinction is load-bearing. The loader used to build its own
    candidates and call `_best_voicing` directly, which silently skipped the
    non-chord-tone strategies, the selector's tone-purity criterion (because
    `allowed_tones` defaults to None) and the octave-down rescue. `chord_type`
    and `chord_name` stay the *written* chord even when `harmonized_as` names a
    substitute, because `allowed_tones` has always been built from the written
    chord and changing that would move the library's published output.
    """

    candidates: List["Voicing"]
    written_melody: str
    melody: str
    original_melody: Optional[str]
    chord_type: str
    chord_name: str
    is_non_chord_tone: bool
    strategy: Optional[str]
    harmonized_as: Optional[str]


def normalised_harmony(
    chord: str, harmonized_as: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """A (root, quality) pair for a chord, however it is spelled.

    `harmonized_as` wins when a non-chord-tone strategy substituted a chord,
    otherwise the written name. Normalised through `ChordParser` so `D-7` and
    `Dm7` are the same chord rather than two, which matters because the corpus
    writes Weimar notation and the library writes its own.
    """
    root, quality = ChordParser.parse_chord_name(harmonized_as or chord)
    return (root, ChordParser.canonical_quality(quality) if quality else quality)


def sounding_harmony(step: ArrangementStep) -> Tuple[Optional[str], Optional[str]]:
    """The harmony a step actually sounds, normalised so two spellings compare equal.

    Used to decide whether a repeated melody is still a hold: a note repeating
    across a *chord change* is not a held shape, it is a new harmony that the
    held soprano has to be heard against.
    """
    return normalised_harmony(step.chord, step.harmonized_as)


class VoiceLeadingEngine:
    """Generates and voice-leads jazz guitar voicings dynamically."""
    
    # Accurate Drop-2 interval structures relative to top melody voice for top 4 strings (Strings 4-3-2-1: D, G, B, E).
    # Semitone offsets from the soprano (String 1 / High E) down to String 2 (B), String 3 (G), and String 4 (D).
    DROP2_INTERVAL_SETS = {
        # --- Major Family ---
        "maj7": [
            [0, -7, -11, -16],  # 7th in top voice
            [0, -5, -8, -13],   # Root in top voice
            [0, -5, -9, -16],   # 3rd in top voice
            [0, -7, -8, -15],   # 5th in top voice
        ],
        "6": [
            [0, -5, -9, -14],   # 6th in top voice
            [0, -5, -8, -15],   # Root in top voice
            [0, -7, -9, -16],   # 3rd in top voice
            [0, -7, -10, -15],  # 5th in top voice
        ],

        # --- Minor Family (Essential for Minor Tunes) ---
        "m7": [
            [0, -7, -10, -15],  # b7 in top voice
            [0, -5, -9, -14],   # Root in top voice
            [0, -5, -8, -15],   # b3 in top voice
            [0, -7, -9, -16],   # 5th in top voice
        ],
        "m7b5": [
            [0, -7, -10, -16],  # b7 in top voice (half-diminished ii chord)
            [0, -6, -9, -14],   # Root in top voice
            [0, -5, -9, -15],   # b3 in top voice
            [0, -6, -8, -15],   # b5 in top voice
        ],
        "dim7": [
            [0, -6, -9, -15],   # bb7 / dim7 in top voice (symmetrical)
            [0, -6, -9, -15],   # Root in top voice
            [0, -6, -9, -15],   # b3 in top voice
            [0, -6, -9, -15],   # b5 in top voice
        ],
        "m6": [
            [0, -6, -9, -14],   # 6th in top voice (tonic minor)
            [0, -5, -9, -15],   # Root in top voice
            [0, -6, -8, -15],   # b3 in top voice
            [0, -7, -10, -16],  # 5th in top voice
        ],
        "mMaj7": [
            [0, -8, -11, -16],  # 7th in top voice (melodic minor tonic)
            [0, -5, -9, -13],   # Root in top voice
            [0, -4, -8, -15],   # b3 in top voice
            [0, -7, -8, -16],   # 5th in top voice
        ],

        # --- Dominant Family (Resolutions in Major & Minor Keys) ---
        "7": [
            [0, -6, -10, -15],  # b7 in top voice
            [0, -5, -8, -14],   # Root in top voice
            [0, -6, -9, -16],   # 3rd in top voice
            [0, -7, -9, -15],   # 5th in top voice
        ],
        "7b9": [
            [0, -6, -9, -15],   # b9 in top voice (rootless diminished 7th shell: 3, 5, b7, b9)
            [0, -6, -9, -15],   # 3rd in top voice
            [0, -6, -9, -15],   # 5th in top voice
            [0, -6, -9, -15],   # b7 in top voice
            [0, -8, -11, -14],  # Root in top voice (5th omitted: 1, b9, 3, b7)
        ],
        "7alt": [
            [0, -6, -9, -14],   # b7 in top voice (altered dominant: 3, b7, b9, b13)
            [0, -5, -9, -15],   # b9 in top voice
            [0, -6, -8, -15],   # 3rd in top voice
            [0, -7, -10, -16],  # b13 in top voice
            [0, -8, -11, -14],  # Root in top voice (b13 omitted: root, b9, 3, b7)
        ],

        # --- Extended / colour qualities ---
        # These are voiced rootless (root, 5th or 13th omitted as needed) so the
        # five chord tones of a ninth always fit the four strings. They are what
        # the 'extension' non-chord-tone strategy reharmonises into, e.g. the 9th
        # of Cmaj7 (D) becomes a Cmaj9, so D is a genuine chord tone again.
        "maj9": [
            [0, -8, -10, -13],  # Root in top voice (5th omitted)
            [0, -5, -9, -14],   # 3rd in top voice (rootless 3-5-7-9)
            [0, -5, -8, -15],   # 5th in top voice
            [0, -7, -9, -16],   # 7th in top voice
            [0, -7, -10, -15],  # 9th in top voice
        ],
        "m9": [
            [0, -9, -10, -14],  # Root in top voice (5th omitted)
            [0, -5, -8, -13],   # b3 in top voice (rootless b3-5-b7-9)
            [0, -5, -9, -16],   # 5th in top voice
            [0, -7, -8, -15],   # b7 in top voice
            [0, -7, -11, -16],  # 9th in top voice
        ],
        "9": [
            [0, -8, -10, -14],  # Root in top voice (5th omitted)
            [0, -6, -9, -14],   # 3rd in top voice (rootless 3-5-b7-9)
            [0, -5, -9, -15],   # 5th in top voice
            [0, -6, -8, -15],   # b7 in top voice
            [0, -7, -10, -16],  # 9th in top voice
        ],
        "6/9": [
            [0, -8, -10, -15],  # Root in top voice (5th omitted)
            [0, -7, -9, -14],   # 3rd in top voice (rootless 3-5-6-9)
            [0, -5, -10, -15],  # 5th in top voice
            [0, -5, -7, -14],   # 6th in top voice
            [0, -7, -10, -17],  # 9th in top voice
        ],
        "13": [
            [0, -3, -8, -14],   # Root in top voice (5th omitted)
            [0, -7, -9, -18],   # 3rd in top voice (rootless 3-5-b7-13)
            [0, -9, -10, -15],  # 5th in top voice
            [0, -3, -6, -13],   # b7 in top voice
            [0, -5, -11, -14],  # 13th in top voice
        ],

        # --- Triads (four voices: the root is doubled an octave below the stack) ---
        "maj": [
            [0, -8, -12, -17],  # Root in top voice (root doubled underneath)
            [0, -9, -12, -16],  # 3rd in top voice
            [0, -7, -12, -15],  # 5th in top voice
        ],
        "m": [
            [0, -9, -12, -17],  # Root in top voice (root doubled underneath)
            [0, -8, -12, -15],  # b3 in top voice
            [0, -7, -12, -16],  # 5th in top voice
        ],
        "aug": [
            # Symmetrical, so every inversion fingers identically (like dim7).
            [0, -8, -12, -16],  # Root in top voice
            [0, -8, -12, -16],  # 3rd in top voice
            [0, -8, -12, -16],  # #5 in top voice
        ],

        # --- Suspended chords ---
        "sus4": [
            [0, -7, -12, -17],   # Root in top voice
            [0, -10, -12, -17],  # 4th in top voice
            [0, -7, -12, -14],   # 5th in top voice
        ],
        "sus2": [
            [0, -10, -12, -17],  # Root in top voice
            [0, -7, -12, -14],   # 2nd (9th) in top voice
            [0, -7, -12, -17],   # 5th in top voice
        ],
        "7sus4": [
            [0, -5, -7, -14],   # Root in top voice (3rd replaced by the 4th)
            [0, -7, -10, -17],  # 4th in top voice
            [0, -7, -9, -14],   # 5th in top voice
            [0, -5, -10, -15],  # b7 in top voice
        ],

        # --- Added-note colours ---
        "add9": [
            [0, -8, -10, -17],  # Root in top voice (5th omitted)
            [0, -7, -10, -14],  # 9th in top voice
            [0, -4, -9, -14],   # 3rd in top voice
            [0, -5, -7, -15],   # 5th in top voice
        ],
        "madd9": [
            [0, -9, -10, -17],  # Root in top voice (5th omitted)
            [0, -7, -11, -14],  # 9th in top voice
            [0, -3, -8, -13],   # b3 in top voice
            [0, -5, -7, -16],   # 5th in top voice
        ],

        # --- Altered and Lydian dominants ---
        "7b5": [
            # Symmetrical, so only two distinct shapes cover the four inversions.
            [0, -6, -8, -14],   # Root in top voice
            [0, -6, -10, -16],  # 3rd in top voice
            [0, -6, -8, -14],   # b5 in top voice
            [0, -6, -10, -16],  # b7 in top voice
        ],
        "7#5": [
            [0, -4, -8, -14],   # Root in top voice
            [0, -6, -8, -16],   # 3rd in top voice
            [0, -8, -10, -16],  # #5 in top voice
            [0, -6, -10, -14],  # b7 in top voice
        ],
        "7#11": [
            # The #11 replaces the perfect 5th: root, 3rd, #11, b7.
            [0, -6, -8, -14],   # Root in top voice (5th omitted)
            [0, -6, -10, -16],  # 3rd in top voice
            [0, -6, -8, -14],   # #11 in top voice
            [0, -6, -10, -16],  # b7 in top voice
        ],
        "7b13": [
            # b13 is enharmonic with #5, so the shapes match 7#5.
            [0, -4, -8, -14],   # Root in top voice (natural 5th omitted)
            [0, -6, -8, -16],   # 3rd in top voice
            [0, -8, -10, -16],  # b13 in top voice
            [0, -6, -10, -14],  # b7 in top voice
        ],
        "maj7#11": [
            [0, -6, -8, -13],   # Root in top voice (5th omitted)
            [0, -5, -10, -16],  # 3rd in top voice
            [0, -6, -7, -14],   # #11 in top voice
            [0, -7, -11, -17],  # 7th in top voice
        ],
        "m9b5": [
            # Half-diminished ninth: the m9 shapes with the 5th flattened.
            [0, -9, -10, -14],  # Root in top voice (b5 omitted: root-9-b3-b7)
            [0, -5, -9, -13],   # b3 in top voice (rootless b3-b5-b7-9)
            [0, -4, -8, -15],   # b5 in top voice
            [0, -7, -8, -16],   # b7 in top voice
            [0, -8, -11, -16],  # 9th in top voice
        ],
    }

    # Aliases for flexible chord quality notation
    DROP2_INTERVAL_SETS["min7"] = DROP2_INTERVAL_SETS["m7"]
    DROP2_INTERVAL_SETS["min7b5"] = DROP2_INTERVAL_SETS["m7b5"]
    DROP2_INTERVAL_SETS["ø7"] = DROP2_INTERVAL_SETS["m7b5"]
    DROP2_INTERVAL_SETS["ø"] = DROP2_INTERVAL_SETS["m7b5"]
    DROP2_INTERVAL_SETS["half-dim"] = DROP2_INTERVAL_SETS["m7b5"]
    DROP2_INTERVAL_SETS["°7"] = DROP2_INTERVAL_SETS["dim7"]
    DROP2_INTERVAL_SETS["°"] = DROP2_INTERVAL_SETS["dim7"]
    DROP2_INTERVAL_SETS["dim"] = DROP2_INTERVAL_SETS["dim7"]
    DROP2_INTERVAL_SETS["min6"] = DROP2_INTERVAL_SETS["m6"]
    DROP2_INTERVAL_SETS["minMaj7"] = DROP2_INTERVAL_SETS["mMaj7"]
    DROP2_INTERVAL_SETS["mmaj7"] = DROP2_INTERVAL_SETS["mMaj7"]
    DROP2_INTERVAL_SETS["dom7"] = DROP2_INTERVAL_SETS["7"]
    DROP2_INTERVAL_SETS["M7"] = DROP2_INTERVAL_SETS["maj7"]

    # Degree pitch classes relative to chord root (used to match soprano note to inversion).
    # Each entry lines up one-to-one with DROP2_INTERVAL_SETS[quality]: entry i is the
    # chord tone sitting in the top voice of template i.
    DEGREE_OFFSETS_FROM_ROOT = {
        "maj7": [11, 0, 4, 7],
        "6": [9, 0, 4, 7],
        "m7": [10, 0, 3, 7],
        "m7b5": [10, 0, 3, 6],
        "dim7": [9, 0, 3, 6],
        "m6": [9, 0, 3, 7],
        "mMaj7": [11, 0, 3, 7],
        "7": [10, 0, 4, 7],
        "7b9": [1, 4, 7, 10, 0],
        "7alt": [10, 1, 4, 8, 0],
        "maj9": [0, 4, 7, 11, 2],
        "m9": [0, 3, 7, 10, 2],
        "9": [0, 4, 7, 10, 2],
        "6/9": [0, 4, 7, 9, 2],
        "13": [0, 4, 7, 10, 9],
        "maj": [0, 4, 7],
        "m": [0, 3, 7],
        "aug": [0, 4, 8],
        "sus4": [0, 5, 7],
        "sus2": [0, 2, 7],
        "add9": [0, 2, 4, 7],
        "madd9": [0, 2, 3, 7],
        "7sus4": [0, 5, 7, 10],
        "7b5": [0, 4, 6, 10],
        "7#5": [0, 4, 8, 10],
        "7#11": [0, 4, 6, 10],
        "7b13": [0, 4, 8, 10],
        "maj7#11": [0, 4, 6, 11],
        "m9b5": [0, 3, 6, 10, 2],
    }

    # Non-chord-tone strategy routing: canonical base quality -> {melody degree
    # (relative to root): extension quality that absorbs it as a chord tone}.
    # Only entries that are musically unambiguous are listed; anything missing
    # leaves the melody to the existing quality-only fallback.
    NON_CHORD_TONE_EXTENSIONS = {
        "maj7": {2: "maj9", 6: "maj7#11", 9: "6/9"},   # 9th, #11, 6th/13th
        "6": {2: "6/9"},                               # 9th
        "m7": {2: "m9"},                               # 9th
        "m7b5": {2: "m9b5"},                           # 9th (half-diminished 9)
        # 9th, 11th (the suspended dominant), #11, b13, 13th
        "7": {2: "9", 5: "7sus4", 6: "7#11", 8: "7b13", 9: "13"},
        "7b9": {5: "7sus4", 6: "7#11", 8: "7b13"},     # 11th, #11, b13
        "9": {6: "7#11", 9: "13"},                     # #11, 13th
        "13": {6: "7#11"},                             # #11
    }

    # Accepted values for arrange_progression(non_chord_tone=...).
    NON_CHORD_TONE_STRATEGIES = ("extension", "diminished", "sustain", "legacy")

    @staticmethod
    def _parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
        """Delegates to ChordParser for backward compatibility."""
        return ChordParser.parse_chord_name(name)

    @staticmethod
    def _string_sets_for(grip: str, top_string: int) -> List[Tuple[int, ...]]:
        """
        Every string set `grip` can occupy with its soprano on `top_string`, each
        **ordered from the soprano downwards**, which is the order _place_template
        assigns voices in.

        A list rather than one set, because a grip can have more than one shape for the
        same string: a G-string shell is either 5-4-3 or 6-4-3, and returning only the
        first would silently hide 6-4-3 behind 5-4-3.

        For drop-2 the set is simply the four strings from the soprano down, which
        reproduces the historical behaviour for *any* top_string and so keeps
        get_drop2_voicings working for callers who pass their own. The other grips come
        from a fixed table (GRIP_STRING_SETS, stored low-to-high for readability) because
        they are named shapes: a 6-4-3 shell is that shape or it is nothing, and it is
        not available on every string.

        The table lists each set low-to-high, so the soprano is found by *searching* for
        it rather than by assuming an end: for a 1-2-3 shell the soprano is the first
        entry, for 6-4-3 it is the last, and a duo like (5, 4) happens to start on it.
        Rotating from wherever it actually is what keeps every grip's soprano on the
        melody.
        """
        if grip == "drop2":
            if top_string < 3:
                return []
            strings = tuple(range(top_string, top_string - 4, -1))
            # A G-string soprano has no four-note block: see _BOTTOM_FOUR. Shells and
            # duos still apply there, and the table below lists them.
            if frozenset(strings) == _BOTTOM_FOUR:
                return []
            return [strings]
        sets: List[Tuple[int, ...]] = []
        for strings, soprano in GRIP_STRING_SETS.get(grip, ()):
            if soprano == top_string and soprano in strings:
                pivot = strings.index(soprano)
                sets.append(tuple(strings[pivot:]) + tuple(strings[:pivot]))
        return sets

    @classmethod
    def _chord_context(
        cls, chord_type: str, chord_name: Optional[str]
    ) -> Tuple[str, Optional[int], Tuple[int, ...]]:
        """
        The canonical quality, the root's pitch class, and the chord's tones **as
        degrees from that root**.

        The degrees are deliberately not absolute. Every grip builder wants to reason
        in intervals - "the 3rd of a minor 7th is three semitones up" - and only the
        final pitch placement wants an absolute note. Keeping one frame throughout means
        there is a single place (the search for a pitch at or below the soprano) where
        degrees become pitches, and a chord whose root cannot be found simply yields
        nothing rather than being transposed by accident.

        Note this is *not* ChordParser.get_chord_tones(quality, chord_name), which
        returns absolute pitch classes once a name is supplied. The tones are the full
        set for the quality, not the four the drop-2 tables voice, so a shell or a duo
        is built from every tone the chord really has.

        A quality with no usable root - a bare quality symbol with no chord name, or an
        unparseable root - has root_pc of None, and only the drop-2 path still serves it,
        because those tables are written as offsets from the soprano and need no root.
        """
        canonical = ChordParser.canonical_quality(chord_type)
        root_pc: Optional[int] = None
        root_str, _ = ChordParser.parse_chord_name(chord_name) if chord_name else (None, None)
        if root_str:
            try:
                root_pc = Note(f"{root_str}4").midi_note() % 12
            except (KeyError, ValueError, TypeError):
                root_pc = None
        tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical, ())
        return canonical, root_pc, tones

    @classmethod
    def get_grip_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_string: int = 5,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """
        Generates fingerings for `grips` on one string block, pinned to the melody.

        This is the general form of get_drop2_voicings, and with `grips=("drop2",)` it
        produces exactly what that method always has. The other families differ in what
        they carry rather than in where they sit:

          drop2   four voices, from the hand-authored tables
          drop3   four voices, a close stack with the third voice dropped
          closed  four voices in close position under the melody
          shell   three voices: the 3rd, the 7th, and one more
          duo     two voices, and only under a root or a 5th (see DUO_DEGREES)

        Candidate generation is *pure*. It does not filter by neck position, does not
        transpose, and does not know what came before - choosing among the results is
        _best_voicing's job. Keeping that split is what stops the grip families and the
        octave-down rescue from having to know about each other.

        Every candidate sounds only chord tones, uses 2-4 strings all belonging to one
        GRIP_STRING_SETS entry, carries the melody on its topmost string, and keeps
        every finger within GRIP_MAX_SPAN of it.
        """
        melody_midi = melody_note.midi_note()

        top_fret = GuitarFretboard.note_to_fret(top_string, melody_note)
        if top_fret < 0 or top_fret > 18:
            return []

        canonical, root_pc, tones = cls._chord_context(chord_type, chord_name)

        # Which inversion of a drop-2 table puts this melody in the top voice. The
        # derived families build their shape from the chord tones themselves and so
        # need no steering; this only narrows the table lookup.
        target_idx: Optional[int] = None
        deg_offsets = cls.DEGREE_OFFSETS_FROM_ROOT.get(canonical)
        if chord_name and deg_offsets and root_pc is not None:
            mel_degree = (melody_midi - root_pc) % 12
            for idx, d in enumerate(deg_offsets):
                if d % 12 == mel_degree:
                    target_idx = idx
                    break

        valid_voicings: List[Voicing] = []
        for grip in grips:
            for strings in cls._string_sets_for(grip, top_string):
                if grip in ("shell", "duo"):
                    # These two are defined by the guide tones, so a chord with no root
                    # to measure them from gets nothing. That is a real limitation
                    # rather than a fallback: a shell is a claim about *this* chord's
                    # 3rd and 7th, and guessing them without a root is how a chord gets
                    # a wrong note in it.
                    if root_pc is None:
                        continue
                    if grip == "duo":
                        duo = _duo_offsets(tones, melody_midi, root_pc)
                        templates = [duo] if duo else []
                    else:
                        # Every shell set is placed by the same search, 6-4-3 included:
                        # a shell's notes are not in descending pitch order down the
                        # strings, so none of them can come from a stack.
                        found = _place_shell(
                            canonical, tones, root_pc, strings, melody_midi, top_fret
                        )
                        if found is not None:
                            valid_voicings.append(found)
                        continue
                else:
                    templates = _interval_set_for_grip(
                        canonical, grip, tones, melody_midi, root_pc
                    )
                    if (
                        target_idx is not None
                        and grip == "drop2"
                        and 0 <= target_idx < len(templates)
                    ):
                        templates = [templates[target_idx]]

                for template in templates:
                    voicing = _place_template(
                        template, strings, melody_midi, top_fret, grip
                    )
                    if voicing is not None:
                        valid_voicings.append(voicing)

        return valid_voicings

    @classmethod
    def get_drop2_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_string: int = 5,
    ) -> List[Voicing]:
        """
        Generates valid 4-string Drop-2 fretboard fingerings pinned to the melody note.

        top_string is the index of the string carrying the melody: 5 (high E) yields the
        traditional D-G-B-E shape, while 4 (B) yields the lower A-D-G-B shape used when
        the melody sits below the high E string's open pitch. When chord_name (e.g.
        'Dm7b5') is provided, it matches the specific inversion where melody_note
        functions as the correct chord tone.

        Kept as a named entry point because it is what callers reach for directly and
        its output is part of the library's published behaviour. It is exactly
        get_grip_voicings with the grip pinned to drop-2.
        """
        return cls.get_grip_voicings(
            melody_note, chord_type, chord_name, top_string, grips=("drop2",)
        )

    @staticmethod
    def _lower_soprano_strings(top_strings: Tuple[int, ...]) -> Tuple[int, ...]:
        """
        The subset of `top_strings` below the high E, so a transposed melody is voiced
        on the B string rather than back on the high E. Falls back to `top_strings`
        when it contains nothing below the high E, so a caller restricted to (5,)
        still gets a (higher) voicing instead of nothing.
        """
        lower = tuple(s for s in top_strings if s < len(STANDARD_TUNING) - 1)
        return lower or tuple(top_strings)

    @classmethod
    def get_octave_down_candidates(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """
        Candidates for melody_note an octave lower, on the strings below the high E.

        A melody whose only position sits outside the neck window is re-voiced here so
        the whole harmonisation comes down the neck. Because the B string is five
        semitones below the high E, the octave-down transposition lands seventeen
        semitones - exactly a major tenth - below where the same note sat on the high
        E, which is what actually brings it into a playable position.

        The wider candidate pool matters here as much as anywhere: a high melody that no
        four-note shape can reach inside the window may still have a three-note shell
        under it, and taking that beats skipping the step.

        Returns an empty list when the octave-down melody cannot be voiced at all, so
        the caller can keep the original candidates rather than losing the step.
        """
        octave_down = Note(_note_name(melody_note.midi_note() - 12))
        return cls.get_all_grip_voicings(
            octave_down,
            chord_type,
            chord_name=chord_name,
            top_strings=cls._lower_soprano_strings(top_strings),
            grips=grips,
        )

    @classmethod
    def get_all_grip_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """
        Collects fingerings for every allowed soprano string in `top_strings`.

        High-E candidates come first, so a caller that simply takes the first result
        keeps the traditional top-string fingering. Candidate generation tries the
        chord-tone-matched inversion first and falls back to quality-only voicings, so
        nothing is lost when chord_name cannot place the melody on a chord tone. A
        melody below the high E string's open pitch (E4) simply yields no high-E
        candidates and is arranged on a lower string instead of being skipped.

        This is pure candidate generation: it neither filters by neck position nor
        transposes. A melody whose only position lies outside the window is re-voiced
        an octave down by get_octave_down_candidates, which arrange_progression calls -
        so the two cannot recurse into each other.
        """
        candidates: List[Voicing] = []
        for top_string in top_strings:
            candidates.extend(
                cls.get_grip_voicings(
                    melody_note, chord_type, chord_name, top_string, grips
                )
            )

        if not candidates and chord_name:
            for top_string in top_strings:
                candidates.extend(
                    cls.get_grip_voicings(
                        melody_note, chord_type, None, top_string, grips
                    )
                )

        return candidates

    @classmethod
    def get_all_drop2_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
    ) -> List[Voicing]:
        """
        Collects Drop-2 fingerings for every allowed soprano string in top_strings.

        High-E candidates come first, so a caller that simply takes the first result
        keeps the traditional top-string fingering. Candidate generation tries the
        chord-tone-matched inversion first and falls back to quality-only voicings, so
        nothing is lost when chord_name cannot place the melody on a chord tone. A
        melody below the high E string's open pitch (E4) simply yields no high-E
        candidates and is arranged on the B string instead of being skipped.

        This is pure candidate generation: it neither filters by neck position nor
        transposes. A melody whose only position lies above HIGH_FRET_LIMIT is
        re-voiced an octave down by get_octave_down_candidates, which
        arrange_progression calls - so the two cannot recurse into each other.
        """
        return cls.get_all_grip_voicings(
            melody_note, chord_type, chord_name, top_strings, grips=("drop2",)
        )

    @classmethod
    def get_melody_only_voicing(
        cls,
        melody_note: Note,
        prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
    ) -> Optional[Voicing]:
        """
        Returns a single-fret Voicing that plays melody_note alone, or None.

        This is the voicing used for a NO_CHORD ("NC") step: a bar of melody with
        no harmony behind it, which is voiced as written rather than harmonised or
        reharmonised. It is deliberately NOT a drop-2 voicing and so does not obey
        the four-contiguous-strings playability invariant - there is exactly one
        active fret, and fret_span() is 0.

        The strings in `prefer` (high E, then B) are tried in order; when none of
        them can reach the note - or the preferred ones are exhausted - the
        remaining strings are tried from the high E downwards, so a low melody
        such as G3 still sounds on the open G string.

        A melody that is playable but only above HIGH_FRET_LIMIT is retried an octave
        down on the strings below the high E, so a high note is played in a
        comfortable position.

        A melody that is unreachable at the written pitch at all still returns None
        rather than being respelled: None is the documented signal that a note cannot
        sound (B5 is fret 19, C6 is fret 20 - both past the end of the board), and
        quietly playing it an octave down would hide that from the caller.
        """
        # Reachability at the written pitch, across every string, decides whether the
        # octave-down attempt is legitimate at all. Without this a genuinely
        # unplayable note would be silently respelled and reported as playable.
        if not any(
            0 <= GuitarFretboard.note_to_fret(s, melody_note) <= 18
            for s in range(len(STANDARD_TUNING))
        ):
            return None

        attempts: List[Tuple[Tuple[int, ...], int]] = [
            (prefer, 0),
            (cls._lower_soprano_strings(prefer), -12),
        ]
        for strings, octave_shift in attempts:
            for string_index in _melody_only_string_order(strings):
                shifted = Note(_note_name(melody_note.midi_note() + octave_shift))
                fret = GuitarFretboard.note_to_fret(string_index, shifted)
                if 0 <= fret <= HIGH_FRET_LIMIT:
                    frets = [-1] * len(STANDARD_TUNING)
                    frets[string_index] = fret
                    return Voicing(frets=frets, top_fret=fret, avg_fret=float(fret))
        return None

    # ------------------------------------------------------------------
    # Non-chord melody tones
    # ------------------------------------------------------------------
    @classmethod
    def is_chord_tone(cls, melody_note: Note, chord_type: str, chord_name: Optional[str] = None) -> bool:
        """
        True when melody_note is one of the chord's tones.

        Detection uses ChordParser.CHORD_TONES_FROM_ROOT (every chord tone), not
        DEGREE_OFFSETS_FROM_ROOT (only the four notes a drop-2 shape can voice),
        so the root of a rootless quality such as 7b9 still counts as a chord
        tone and is not needlessly reharmonised. Unknown qualities return False.
        """
        canonical = ChordParser.canonical_quality(chord_type)
        tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical)
        if not tones:
            return False

        root_pc = 0
        if chord_name:
            root_str, _ = ChordParser.parse_chord_name(chord_name)
            if root_str:
                root_pc = Note(root_str + "4").midi_note() % 12

        return ((melody_note.midi_note() - root_pc) % 12) in {t % 12 for t in tones}

    @classmethod
    def resolve_non_chord_tone(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: str,
        strategy: str = "extension",
        next_melody: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Picks a substitute (chord quality, chord name) that turns a non-chord
        melody note into a genuine chord tone, so get_drop2_voicings can voice it.
        Returns None when the strategy cannot help, leaving the caller's existing
        behaviour untouched.

        strategy:
          'extension'  - keep the harmony and absorb the note as an extension,
                         e.g. D over Cmaj7 (the 9th) -> Cmaj9.
          'diminished' - Barry Harris 6/dim7: voice the note inside a dim7 built a
                         semitone below the pitch the line resolves to, e.g. the
                         passing D over Cmaj7 -> Bdim7.
          'legacy'     - no substitution.
        """
        if strategy == "legacy" or not chord_name:
            return None

        canonical = ChordParser.canonical_quality(chord_type)
        root_str, _ = ChordParser.parse_chord_name(chord_name)
        if not root_str:
            return None

        if strategy == "extension":
            degree = ChordParser.get_melody_degree(root_str, melody_note)
            extension = cls.NON_CHORD_TONE_EXTENSIONS.get(canonical, {}).get(degree)
            if extension:
                return extension, f"{root_str}{extension}"
            return None

        if strategy == "diminished":
            target_pc = cls._resolution_pitch_class(melody_note, root_str, canonical, next_melody)
            if target_pc is None:
                return None
            # A dim7 is symmetrical, so naming the root a semitone below the
            # resolution target is the idiomatic Barry Harris spelling; all four
            # enharmonic roots finger identically.
            dim_root = PITCH_CLASS_NAMES[(target_pc - 1) % 12]
            return "dim7", f"{dim_root}dim7"

        return None

    @classmethod
    def _resolution_pitch_class(
        cls,
        melody_note: Note,
        root_str: str,
        canonical_type: str,
        next_melody: Optional[str],
    ) -> Optional[int]:
        """
        Pitch class the non-chord tone resolves into: the next chord tone of the
        line when one is known, otherwise the nearest chord tone of the underlying
        chord at or below the melody.
        """
        if next_melody:
            return Note(next_melody).midi_note() % 12

        tones = sorted(
            (Note(root_str + "4").midi_note() + tone) % 12
            for tone in ChordParser.CHORD_TONES_FROM_ROOT.get(canonical_type, ())
        )
        if not tones:
            return None

        melody_pc = melody_note.midi_note() % 12
        below = [tone for tone in tones if tone <= melody_pc]
        return below[-1] if below else tones[-1]

    @staticmethod
    def _window_penalty(
        candidates: List[Voicing],
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
    ) -> int:
        """
        How many frets the best of `candidates` puts outside the neck window.

        Zero means at least one candidate lies wholly inside it. This is the test the
        octave-down rescue uses to decide whether a melody is *badly placed* - and it
        deliberately asks the best candidate rather than the average, so one
        comfortable voicing is enough to leave the melody where it was written.
        """
        return min(
            (
                sum(1 for fret in v.active_frets() if not fret_min <= fret <= fret_max)
                for v in candidates
            ),
            default=0,
        )

    @classmethod
    def voicing_cost(
        cls,
        voicing: Voicing,
        previous: Optional[Voicing],
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        allowed_tones: Optional[Container[int]] = None,
    ) -> Tuple[float, ...]:
        """
        The whole selection rule as one comparable number, lowest wins.

        It is a *tuple* rather than a weighted sum on purpose. These six priorities are
        genuine trade-offs that must not be traded against each other - "stay in
        position" is not worth a semitone of inner-voice movement, but both are worth
        far more than preferring drop-2 over a shell - and a weighted sum would hide
        that behind magic numbers whose values nobody can defend. Lexicographic order
        states the ranking directly, so the second criterion is only consulted when the
        first is exactly tied.

        In order:

        0. notes outside the chord, when `allowed_tones` is given. This is a
           *correctness* criterion and it outranks every preference, because a wrong note
           is not playable at all while an awkward position is merely awkward. It exists
           because the hand-authored drop-2 tables do not have an inversion for every
           chord tone - a 9th in the melody of a 13 chord, for instance - and the
           quality-only fallback that covers the gap is free to sound a note the chord
           does not contain. Several of the derived grips always pass this.
        1. frets outside the window. This is a *penalty*, not a filter. A melody that
           cannot be voiced between the two frets is still played, one fret-pair at a
           time out of position, because a chord of the tune is worth more than a
           fretboard preference. See NECK_FRET_MIN.
        2. missing voices. A partial harmonisation is a *fallback*, not a style: where a
           complete chord can be played at all, it is used, and it outranks staying in
           exactly the same spot. This sits below the window and above position because
           both of those are about comfort and this is about whether the chord is
           actually there - a root-and-3rd duo is a real voicing of a root-and-3rd, not a
           Cmaj7. A permitted root-or-5th duo scores zero here, so where two notes really
           are enough it competes on equal terms with a four-note shape.
        3. distance in neck position from the previous voicing, measured as the
           difference of average frets. Absolute fret numbers mean the same place on the
           neck whichever string they are on, so this stays meaningful when a melody
           holds its place by moving to a different string - which is the behaviour the
           G-string soprano exists to enable. With no previous chord this becomes the
           long-standing "start near the middle of the neck" rule.
        4. total pitch movement of the voices, the historical voice-leading measure.
        5. fret span: a tighter shape is easier to hold and to move.
        6. grip preference, so a four-note drop-2 wins an exact tie against a shell.
        """
        active = voicing.active_frets()
        outside = sum(1 for fret in active if not fret_min <= fret <= fret_max)
        foreign = (
            1.0
            if allowed_tones is not None
            and not all(pc in allowed_tones for pc in voicing.pitch_classes())
            else 0.0
        )

        if previous is None:
            # The first chord of a progression has nothing to lead from, so "stay near
            # where we are" becomes "start in a comfortable part of the neck".
            position = abs(voicing.avg_fret - 9)
            movement = 0.0
        else:
            position = abs(voicing.avg_fret - previous.avg_fret)
            movement = cls.calculate_pitch_leading_distance(previous, voicing)

        grip_rank = (
            GRIP_PREFERENCE.index(voicing.grip)
            if voicing.grip in GRIP_PREFERENCE
            else len(GRIP_PREFERENCE)
        )
        missing = 4 - len(active)

        return (
            foreign,
            float(outside),
            float(missing),
            position,
            movement,
            float(voicing.fret_span()),
            float(grip_rank),
        )

    @classmethod
    def _best_voicing(
        cls,
        candidates: List[Voicing],
        previous: Optional[Voicing] = None,
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        allowed_tones: Optional[Container[int]] = None,
    ) -> Optional[Voicing]:
        """
        The candidate voicing_cost likes best, or None when there are no candidates.

        Python's min is stable, so two candidates that cost exactly the same are
        decided by generation order, which is high-E strings first and GRIP_PREFERENCE
        within a string. That keeps the whole engine deterministic: the same progression
        always arranges to the same tab, which is what makes its output worth asserting
        on in tests.
        """
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda v: cls.voicing_cost(
                v, previous, fret_min, fret_max, allowed_tones
            ),
        )

    @classmethod
    def sustain_inner_voices(cls, previous_voicing: Voicing | dict, melody_note: Note) -> Optional[Voicing]:
        """
        Strategy 3: hold the previous chord's three inner voices and move only the
        soprano to the new melody note, the way a player sustains a shape under a
        passing tone. Returns None when the melody is unreachable on the same
        string within a playable span, so the caller can reharmonise instead.
        """
        frets = previous_voicing["frets"] if isinstance(previous_voicing, dict) else previous_voicing.frets
        frets = list(frets)

        soprano = max((s_idx for s_idx, fret in enumerate(frets) if fret >= 0), default=-1)
        if soprano < 0:
            return None

        top_fret = GuitarFretboard.note_to_fret(soprano, melody_note)
        if top_fret < 0:
            return None

        frets[soprano] = top_fret
        active = [fret for fret in frets if fret >= 0]
        if max(active) - min(active) > 5:
            return None

        # Divided by the number of *sounding* fingers, not by four. The previous
        # voicing can now be a three-note shell or a two-note duo, and a shell's mean
        # fret is not one quarter of its sum - getting this wrong misreports where the
        # shape is, which is exactly what the selector compares.
        prev_grip = (
            previous_voicing.grip if isinstance(previous_voicing, Voicing) else "drop2"
        )
        midis = [
            GuitarFretboard.fret_to_midi(s, fret) for s, fret in enumerate(frets) if fret >= 0
        ]
        return Voicing(
            frets=frets,
            top_fret=top_fret,
            avg_fret=sum(active) / len(active),
            grip=prev_grip,
            bass_pc=min(midis) % 12 if midis else None,
        )

    @staticmethod
    def calculate_voice_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
        """Calculates total physical movement across all active strings."""
        frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
        frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
        total_distance = 0
        for f_a, f_b in zip(frets_a, frets_b):
            if f_a >= 0 and f_b >= 0:
                total_distance += abs(f_a - f_b)
        return float(total_distance)

    @staticmethod
    def calculate_pitch_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
        """
        Sums the movement of every voice between two voicings, measured in semitones.

        This is the string-set agnostic counterpart to calculate_voice_leading_distance:
        it compares sounding pitches rather than fret numbers, so it stays meaningful
        when one chord puts the melody on the high E string and the next puts it on the
        B string (the same pitch sounding on a different string). Within a single string
        set the two metrics agree exactly, since a fret delta is a semitone delta.
        """
        frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
        frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
        pitches_a = sorted(
            GuitarFretboard.fret_to_midi(s_idx, f) for s_idx, f in enumerate(frets_a) if f >= 0
        )
        pitches_b = sorted(
            GuitarFretboard.fret_to_midi(s_idx, f) for s_idx, f in enumerate(frets_b) if f >= 0
        )
        return float(sum(abs(p_a - p_b) for p_a, p_b in zip(pitches_a, pitches_b)))

    @classmethod
    def prepare_step(
        cls,
        progression: List[Tuple[str, str, str]],
        index: int,
        previous: Optional[Voicing] = None,
        previous_chord: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> Optional[StepPreparation]:
        """
        Builds one step's candidates, leaving the choice of shape to the caller.

        This is a whole step up to selection: the candidates across every allowed
        soprano string and grip family, the octave-down rescue, and the
        non-chord-tone strategies. `arrange_progression` selects with
        `_best_voicing` straight afterwards, and the corpus loader selects the
        same way after honouring a slash bass, so the two cannot drift.

        Returns None when the step has no voicing at all. `previous` is only read
        by the `sustain` strategy, and `previous_chord` is what that strategy
        reports as `harmonized_as`.
        """
        note_str, chord_type, name = progression[index]
        melody_note = Note(note_str)

        # Chord-tone match first, quality-only fallback second, across every
        # allowed soprano string and every grip family.
        candidates = cls.get_all_grip_voicings(
            melody_note, chord_type, chord_name=name,
            top_strings=top_strings, grips=grips,
        )

        # A melody whose best position sits outside the neck window is re-voiced an
        # octave down on the B string. The written pitch is kept in original_melody.
        # Decided before the non-chord-tone strategies run, so a substituted chord
        # is voiced at the transposed pitch too rather than snapping back up.
        #
        # The guard requires candidates to exist: this repositions a voicing that
        # is playable but sits too high. A melody unreachable at the written pitch
        # (C6, fret 20 - past the end of the board) is left alone, because there is
        # no shape to move down and respelling it would hide the real problem.
        sounding_melody = melody_note
        original_melody: Optional[str] = None
        if candidates and cls._window_penalty(candidates, fret_min, fret_max) > 0:
            octave_down = cls.get_octave_down_candidates(
                melody_note, chord_type, chord_name=name,
                top_strings=top_strings, grips=grips,
            )
            # Only take the lower octave when it genuinely improves the placement,
            # or a merely slightly out-of-window melody would be moved for nothing.
            here = cls._window_penalty(candidates, fret_min, fret_max)
            there = cls._window_penalty(octave_down, fret_min, fret_max)
            if octave_down and there < here:
                candidates = octave_down
                sounding_melody = Note(_note_name(melody_note.midi_note() - 12))
                original_melody = note_str

        strategy_used: Optional[str] = None
        harmonized_as: Optional[str] = None
        is_non_chord_tone = (
            ChordParser.canonical_quality(chord_type) in ChordParser.CHORD_TONES_FROM_ROOT
            and not cls.is_chord_tone(melody_note, chord_type, name)
        )

        if is_non_chord_tone and non_chord_tone != "legacy":
            # Strategy 3 first: holding the shape moves less than any re-voicing.
            if non_chord_tone == "sustain" and previous is not None:
                sustained = cls.sustain_inner_voices(previous, sounding_melody)
                if sustained is not None:
                    candidates = [sustained]
                    strategy_used = "sustain"
                    harmonized_as = previous_chord

            # Strategies 1 and 2 reharmonise the note as a genuine chord tone.
            if strategy_used is None:
                resolved = cls.resolve_non_chord_tone(
                    sounding_melody,
                    chord_type,
                    name,
                    non_chord_tone,
                    next_melody=cls._next_resolution_melody(progression, index),
                )
                if resolved is not None:
                    substitute_quality, substitute_name = resolved
                    substituted = cls.get_all_grip_voicings(
                        sounding_melody,
                        substitute_quality,
                        chord_name=substitute_name,
                        top_strings=top_strings,
                        grips=grips,
                    )
                    if substituted:
                        candidates = substituted
                        strategy_used = non_chord_tone
                        harmonized_as = substitute_name

            if strategy_used is None:
                print(
                    f"Warning: melody {note_str} is not a chord tone of {name} and the "
                    f"'{non_chord_tone}' strategy found no voicing; keeping the fallback"
                )

        if not candidates:
            return None

        return StepPreparation(
            candidates=candidates,
            written_melody=note_str,
            # The transposed pitch when moved down an octave: the step reports
            # what actually sounds.
            melody=(
                note_str
                if original_melody is None
                else _note_name(sounding_melody.midi_note())
            ),
            original_melody=original_melody,
            chord_type=chord_type,
            chord_name=name,
            is_non_chord_tone=is_non_chord_tone,
            strategy=strategy_used,
            harmonized_as=harmonized_as,
        )

    @classmethod
    def arrange_progression(
        cls,
        progression: List[Tuple[str, str, str]],
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[ArrangementStep]:
        """
        Takes a progression of (Melody Note, Chord Quality, Name) tuples
        and computes the optimal voice-led arrangement.

        top_strings selects which strings may carry the melody (see
        MELODY_STRING_CHOICES_FULL). The default allows the high E, the B *and* the G
        string, so a melody can hold its place on the neck by changing strings rather
        than by moving the hand, and a melody below the high E string's open pitch is
        still arranged rather than skipped.

        fret_min and fret_max bound the comfortable neck window the selector aims for
        (frets 2-13 by default). They are a strong preference, not a constraint: a step
        with no voicing inside the window is still played, just outside it, because
        losing a chord of the tune is worse than being a fret out of position.

        grips limits which grip families may be used, in the order they break a tie
        (see GRIP_PREFERENCE). The default offers all of them. `grips=("drop2",)` with
        `top_strings=MELODY_STRING_CHOICES` reproduces this library's original,
        four-string-drop-2-only output exactly, which is what a caller wants when they
        need a known arrangement rather than the best one.

        non_chord_tone selects what happens when a melody note is not a chord tone
        (one of NON_CHORD_TONE_STRATEGIES):
          'extension'  - reharmonise the note as a chord extension (D over Cmaj7
                         becomes Cmaj9), the default;
          'diminished' - Barry Harris 6/dim7 substitution (D over Cmaj7 -> Bdim7);
          'sustain'    - keep the previous chord's inner voices and move only the
                         melody, for brief passing tones;
          'legacy'     - keep the original quality-only fallback behaviour.
        Steps whose melody is already a chord tone are unaffected by this choice.

        A step whose chord_type or name is NO_CHORD ("NC") is voiced as the melody
        alone on a single fret (get_melody_only_voicing) and flagged
        melody_only=True. Such a step is short-circuited before any chord logic,
        so it is never reharmonised and never warns; it also does not take part in
        voice-leading minimisation, and being neither a drop-2 voicing nor a
        four-string shape it is exempt from that playability invariant.
        """
        if non_chord_tone not in cls.NON_CHORD_TONE_STRATEGIES:
            raise ValueError(
                f"Unknown non_chord_tone strategy {non_chord_tone!r}; "
                f"expected one of {cls.NON_CHORD_TONE_STRATEGIES}"
            )

        arrangements: List[ArrangementStep] = []
        
        for index, (note_str, chord_type, name) in enumerate(progression):
            melody_note = Note(note_str)

            # A NO_CHORD step carries melody but no harmony: it is voiced as the
            # melody alone. This happens before any chord logic, so there is no
            # non-chord-tone strategy, no substitute chord and no warning.
            if chord_type == NO_CHORD or name == NO_CHORD:
                solo_voicing = cls.get_melody_only_voicing(melody_note, prefer=top_strings)
                if solo_voicing is None:
                    print(
                        f"Warning: melody {note_str} is unreachable on any string; "
                        f"skipping the no-chord step"
                    )
                    continue
                # get_melody_only_voicing may have dropped the note an octave to stay
                # below HIGH_FRET_LIMIT. Compare the pitch that actually sounds rather
                # than the fret number: an octave-down note lands at a *lower* fret, so
                # only the sounding pitch reveals that the transposition happened.
                sounding_midi = max(solo_voicing.midi_notes())
                written_midi = melody_note.midi_note()
                transposed = (
                    note_str
                    if sounding_midi == written_midi
                    else _note_name(written_midi - 12)
                )
                arrangements.append(ArrangementStep(
                    chord=name,
                    melody=transposed,
                    voicing=solo_voicing,
                    original_melody=(
                        None if transposed == note_str else note_str
                    ),
                    melody_only=True,
                ))
                continue

            # Everything up to choosing a shape is shared with the corpus loader,
            # which needs the same candidates but honours a slash bass first. See
            # prepare_step.
            prepared = cls.prepare_step(
                progression, index,
                previous=arrangements[-1].voicing if arrangements else None,
                previous_chord=arrangements[-1].chord if arrangements else None,
                top_strings=top_strings,
                non_chord_tone=non_chord_tone,
                fret_min=fret_min,
                fret_max=fret_max,
                grips=grips,
            )
            if prepared is None:
                print(
                    f"Warning: No valid drop-2 voicing found for {name} "
                    f"with melody {note_str}"
                )
                continue
            candidates = prepared.candidates
            chord_type = prepared.chord_type
            name = prepared.chord_name
            original_melody = prepared.original_melody
            strategy_used = prepared.strategy
            harmonized_as = prepared.harmonized_as
            is_non_chord_tone = prepared.is_non_chord_tone

            # The whole selection rule lives in voicing_cost. The first chord has no
            # previous shape to lead from, so it falls back to "somewhere comfortable on
            # the neck"; every later chord is scored against the one before it, which is
            # what keeps the hand from jumping and lets a melody hold its place by
            # changing strings.
            prev_voicing = arrangements[-1].voicing if arrangements else None
            # The tones the *written* chord allows, so the selector can prefer a
            # shape that is merely out of position over one that sounds a wrong note.
            best_voicing = cls._best_voicing(
                candidates,
                prev_voicing,
                fret_min,
                fret_max,
                allowed_tones=ChordParser.get_chord_tones(
                    ChordParser.canonical_quality(chord_type), name
                ),
            )
            # `candidates` is non-empty here (the step is skipped otherwise), so this
            # cannot fire. Written as an assertion rather than left to Optional
            # narrowing at every use below.
            assert best_voicing is not None
                
            # A melody that repeats the previous step's pitch is a soprano-only
            # re-strike: the shape is held, so the renderers show just the melody
            # string and leave the inner voices ringing. Compared on the sounding
            # pitch rather than the written name, because a step either side of this
            # may itself have been transposed down an octave.
            #
            # The harmony must be unchanged too. A note repeating across a *chord
            # change* is not a hold: the inner voices ringing belong to the chord
            # the hold started on, so printing the new chord's name over a single
            # note claims a harmony that is not sounding. Those steps are
            # harmonised against the new chord instead, which is what the voicing
            # already does - only the rendering was discarding it.
            previous_step = arrangements[-1] if arrangements else None
            repeated = bool(
                previous_step is not None
                and not previous_step.melody_only
                and max(previous_step.voicing.midi_notes()) == max(best_voicing.midi_notes())
                and sounding_harmony(previous_step)
                == normalised_harmony(name, harmonized_as)
            )

            arrangements.append(ArrangementStep(
                chord=name,
                # The transposed pitch when the step was moved down an octave, so the
                # step reports what actually sounds; original_melody keeps the written one.
                melody=prepared.melody,
                voicing=best_voicing,
                non_chord_tone=is_non_chord_tone,
                strategy=strategy_used,
                harmonized_as=harmonized_as,
                original_melody=original_melody,
                repeated=repeated,
                grip=best_voicing.grip,
                # A shell or a duo leaves part of the chord unsounded, so the chord name
                # printed above the step describes the harmony rather than every note in
                # it. The renderers annotate this.
                partial=len(best_voicing.active_frets()) < 4,
            ))
            
        return arrangements

    @classmethod
    def _next_resolution_melody(
        cls, progression: List[Tuple[str, str, str]], index: int
    ) -> Optional[str]:
        """
        The pitch the melody line resolves into: the first following step whose
        melody is a chord tone of its own chord (None when the phrase never
        resolves). Used to spell the dim7 substitution's root.
        """
        for note_str, chord_type, name in progression[index + 1:]:
            if cls.is_chord_tone(Note(note_str), chord_type, name):
                return note_str
        return None


def _step_annotation(step: ArrangementStep) -> str:
    """
    Returns the non-chord-tone annotation for a step, e.g. '-> Cmaj9 via extension'.

    A melody-only (no chord) step is annotated instead with '(no chord - melody
    alone)'. A step that was transposed down an octave to stay below
    HIGH_FRET_LIMIT is annotated with the written pitch, since its `melody` is the
    transposed note. Empty string for an ordinary chord tone. Shared by
    format_progression and the demonstration so the two renderings cannot drift
    apart.
    """
    if step.melody_only:
        return " (no chord - melody alone)"
    if step.repeated:
        return " (melody repeated - single note)"
    if step.original_melody is not None:
        return f" (transposed down an octave from {step.original_melody})"
    # A partial harmonisation is worth saying out loud: the chord name above the step
    # describes the harmony, not every note sounding under the melody, so a reader
    # counting strings would otherwise wonder where the rest of the chord went.
    if step.partial and not step.non_chord_tone:
        if step.grip == "duo":
            return " (root & 5th duo - partial)"
        return f" ({step.grip} - 3rd & 7th, partial)"
    if not step.non_chord_tone:
        return ""
    if step.harmonized_as:
        return f" (non-chord tone -> {step.harmonized_as} via {step.strategy})"
    return " (non-chord tone)"


# --- Standard six-line staff tab ---

# What an unsounded string renders as when the caller asks to see mutes, and the
# width every fret cell is padded to. Two characters covers frets 0-18, which is
# the whole range the library allows, and it is the same convention tab_block()
# uses - so the two renderings put a fret in the same column.
_MUTED_CELL = "x"
_STAFF_CELL_WIDTH = 2

# A string that is not part of this step at all. A repeated melody strikes the
# soprano alone, and the rest are left blank rather than marked 'x': the player is
# not muting them, they are simply not played. This is the same blank the staff and
# HTML already use for a voice that is not struck, so a repeated note reads as a
# single note instead of as five mutes.
_BLANK_CELL = ""


def _cells_from_frets(frets: List[int]) -> List[str]:
    """
    Renders each fret as a one-character tab cell, muted strings as 'x'.

    A string that is sounding but not being struck is handled by the caller
    (_step_cells), which blanks it; this function renders a literal voicing.
    """
    return [_MUTED_CELL if fret < 0 else str(fret) for fret in frets]

def _tab_block_from_cells(cells: List[str]) -> List[str]:
    """Lays six one-character cells out as a six-line vertical tab block."""
    padded = [cell.rjust(2) for cell in cells]
    lines = []
    for string_index in range(len(cells) - 1, -1, -1):
        # The highest string is labelled with a lowercase 'e', the usual tab
        # convention, so the top and bottom lines of the block stay distinct.
        name = "e" if string_index == 5 else STRING_NAMES[string_index]
        lines.append(f"{name}|{padded[string_index]}-|")
    return lines


def _step_cells(step: ArrangementStep) -> List[str]:
    """The tab cells for one step, honouring step.repeated.

    A repeated melody is played as a **single note**: only the soprano string is
    struck. Every other string is left blank rather than marked 'x', because the
    player is not being asked to mute anything - the other strings are simply not
    part of this step, and 'x' on five strings says more than the gesture does.

    The step still carries a full drop-2 `voicing`: the engine voice-leads from
    it and a caller wanting the literal shape still has `step.tab_line()`.
    """
    frets = step.voicing.frets
    if not step.repeated or step.melody_only:
        return _cells_from_frets(frets)
    soprano = step.voicing.soprano_string()
    if soprano < 0:
        return _cells_from_frets(frets)
    cells = [_BLANK_CELL] * len(frets)
    cells[soprano] = str(frets[soprano])
    return cells


# The whole-progression staff renderers live in `tabstaff`, which imports this
# module. They are exposed here through a module-level __getattr__ rather than a
# top-level `from tabstaff import ...`, because that would be an import cycle:
# importing `tabstaff` first would re-enter this half-initialised module and fail to
# find the names. PEP 562 resolves each name on first access instead, so
# `from arranger import format_tab_html` keeps working - the spelling the README,
# the tests and wjazzd all use - without a lazy import at every call site. This is
# the same lazy-import discipline main() uses for wjazzd, for the same reason.
_TABSTAFF_EXPORTS = {
    # name -> the module it lives in. The MusicXML renderers live in `tabxml`, which
    # `tabstaff` re-exports, so resolving them through `tabstaff` as well keeps one
    # spelling for the whole rendering surface.
    "format_tab_staff": "tabstaff",
    "format_tab_html": "tabstaff",
    "write_tab_html": "tabstaff",
    "format_musicxml": "tabstaff",
    "write_musicxml": "tabstaff",
}


def __getattr__(name: str) -> Any:
    """Resolves the renderer modules on first access. See _TABSTAFF_EXPORTS."""
    if name in _TABSTAFF_EXPORTS:
        return getattr(importlib.import_module(_TABSTAFF_EXPORTS[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    """Lists the lazily-exported renderers alongside the module's own names."""
    return sorted(__all__)


def format_progression(steps: List[ArrangementStep], vertical: bool = False) -> str:
    """
    Renders an arranged progression as tab and returns it as a string.

    This is a pure renderer: it prints nothing and writes nothing to stdout, so
    the caller stays in control of the output.

    With vertical=False (the default) each step is one line, most compact first:

        Dm7      D5  x-x-10-10-10-10
        G7       B4  x-x-5-7-6-7
        Cmaj7    C5  x-x-9-9-8-8

    With vertical=True each step is rendered as a full six-line vertical tab
    block, preceded by its chord, melody and any non-chord-tone annotation.

    Args:
        steps: arrangement steps, typically from VoiceLeadingEngine.arrange_progression.
        vertical: render the six-line vertical tab instead of the one-line form.

    Returns:
        The rendered tab, with steps separated by newlines.
    """
    if not vertical:
        return "\n".join(
            f"{step.chord:<8} {step.melody:<3} "
            f"{_step_annotation(step)} {'-'.join(_step_cells(step))}".rstrip()
            for step in steps
        )

    blocks = []
    for step in steps:
        header = f"{step.chord} ({step.melody}){_step_annotation(step)}"
        blocks.append("\n".join([header, *_tab_block_from_cells(_step_cells(step))]))
    return "\n\n".join(blocks)


# --- Demonstration ---
def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    print(
        f"Chord: {step.chord:<8} | Melody: {step.melody:<3}{_step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {'-'.join(_step_cells(step))} | Melody string: {melody_string}"
    )


def main() -> None:
    """
    Entry point: the built-in demonstration, or a subcommand.

    With no arguments this prints the built-in demonstration arrangements.

    With `corpus` as the first argument it hands over to `wjazzd.corpus_cli`, the
    Weimar Jazz Database front end, which is where the transcribed-head feature
    lives. The import is deliberately lazy and inside the branch: the database
    module is optional glue over a 42 MB file that most users do not have, and
    `import arranger` must never depend on it.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "corpus":
        from wjazzd import corpus_cli

        raise SystemExit(corpus_cli(sys.argv[2:]))

    engine = VoiceLeadingEngine()

    # Example 1: Minor ii - V - i cadence in C Minor (Dm7b5 -> G7b9 -> Cm7)
    # The staple progression for minor jazz standards (Autumn Leaves, Alone Together, Blue Bossa, etc.)
    minor_progression = [
        ("F5", "m7b5", "Dm7b5"),
        ("F5", "7b9", "G7b9"),
        ("Eb5", "m7", "Cm7")
    ]
    result_minor = engine.arrange_progression(minor_progression)

    print("\n--- MINOR ii - V - i ARRANGEMENT (Dm7b5 -> G7b9 -> Cm7) ---")
    for step in result_minor:
        _print_step(step)

    # Example 2: Major ii - V - I in C Major over a melody on the top string (D5 -> B4 -> C5)
    major_progression = [
        ("D5", "m7", "Dm7"),
        ("B4", "7", "G7"),
        ("C5", "maj7", "Cmaj7")
    ]
    result_major = engine.arrange_progression(major_progression)

    print("\n--- MAJOR ii - V - I ARRANGEMENT (Dm7 -> G7 -> Cmaj7) ---")
    for step in result_major:
        _print_step(step)

    # Example 3: The same low melody arranged two ways. Pinning grips=("drop2",) with
    # the two traditional soprano strings reproduces the library's original
    # four-string-only output, which is what a caller wants when they need a known
    # arrangement rather than the best one.
    #
    # The difference is the Cmaj7. D4 and C4 sit at the very bottom of the B string's
    # range, where the original engine put the whole phrase up at frets 2-3 on strings
    # A-D-G-B. With the G string available the last chord can drop to a three-note
    # shell on 5-4-3, an octave lower, and still sound its 3rd and 7th.
    low_progression = [
        ("D4", "m7", "Dm7"),
        ("D4", "7", "G7"),
        ("C4", "maj7", "Cmaj7")
    ]
    for label, kwargs in (
        ("every grip, frets 2-13", {}),
        ("drop-2 only, high E and B strings", {"top_strings": (5, 4), "grips": ("drop2",)}),
    ):
        print(f"\n--- LOW-REGISTER CADENCE, {label} (Dm7 -> G7 -> Cmaj7) ---")
        for step in engine.arrange_progression(low_progression, **kwargs):
            _print_step(step)

    # Example 4: Non-chord melody tones. Bar 2 of "All of Me" moves C5 -> D5 -> C5
    # over Cmaj7; D5 is the 9th, not a chord tone, so each strategy harmonises it
    # differently: as an extension (Cmaj9), as a Barry Harris dim7 substitution
    # (Bdim7), by holding the inner voices under the passing tone, or not at all
    # (the historical quality-only fallback).
    all_of_me = [
        ("C5", "maj7", "Cmaj7"),
        ("D5", "maj7", "Cmaj7"),
        ("C5", "maj7", "Cmaj7"),
    ]

    print("\n--- NON-CHORD MELODY TONES: 'All of Me' bar 2 (C5 -> D5 -> C5 over Cmaj7) ---")
    for strategy in VoiceLeadingEngine.NON_CHORD_TONE_STRATEGIES:
        print(f"  strategy: {strategy}")
        for step in engine.arrange_progression(all_of_me, non_chord_tone=strategy):
            _print_step(step)

    # Example 8: Tab rendering. format_progression() returns the tab as a string
    # and prints nothing itself, so callers choose what to do with it. Here it is
    # used once horizontally and once as vertical six-line tab blocks.
    print("\n--- TAB RENDERING: format_progression(), one line per chord ---")
    print(format_progression(result_major))

    print("\n--- TAB RENDERING: format_progression(vertical=True), six lines per chord ---")
    print(format_progression(result_major, vertical=True))

    # Example 8: The whole progression on one six-line staff. format_tab_staff()
    # is the standard reading order - high E on top, chord names above, barlines
    # between bars - so it is what a player would actually read off the page. These
    # steps carry no timing, so the chords fall on consecutive beats; a transcribed
    # head (see `arranger.py corpus --tab staff`) is spaced on its real rhythm.
    # The renderer is reached through the module's lazy export rather than imported
    # at the top, which is what keeps tabstaff importable on its own; see __getattr__.
    import tabstaff

    print("\n--- TAB RENDERING: format_tab_staff(), one progression on a six-line staff ---")
    print(tabstaff.format_tab_staff(result_major, show_melody=True))

    # Example 8: The same cadence with the timing the corpus loader supplies, so the
    # chords sit on their own beats and a barline falls between the two bars.
    timed_major = engine.arrange_progression(major_progression)
    for index, step in enumerate(timed_major):
        step.bar, step.beat, step.duration = index, 1.0, 1.0
    print("\n--- TAB RENDERING: format_tab_staff() on a timed progression, barline per bar ---")
    print(tabstaff.format_tab_staff(timed_major, show_melody=True, measures_per_line=1))


if __name__ == "__main__":
    main()


# The three renderers are re-exported lazily (see __getattr__), which a static
# checker cannot follow. A TYPE_CHECKING import gives it the real declarations, so
# `from arranger import format_tab_html` type-checks and IDEs resolve it, while at
# runtime the names still come from __getattr__ and never trigger an import cycle.
if TYPE_CHECKING:
    from tabstaff import (
        format_musicxml,
        format_tab_html,
        format_tab_staff,
        write_musicxml,
        write_tab_html,
    )

# Star-import support. This module never had an __all__, so `from arranger import *`
# used to export every public name; the lazy __getattr__ above hides the tabstaff
# renderers from that, so they are listed here explicitly. Keep it in step when
# adding a public name - test_dunder_all_matches_the_public_surface checks that.
__all__ = [
    "DUO_DEGREES",
    "GRIP_MAX_SPAN",
    "GRIP_PREFERENCE",
    "GRIP_STRING_SETS",
    "HIGH_FRET_LIMIT",
    "MELODY_STRING_CHOICES",
    "MELODY_STRING_CHOICES_FULL",
    "NECK_FRET_MAX",
    "NECK_FRET_MIN",
    "NO_CHORD",
    "PITCH_CLASS_NAMES",
    "SHELL_DEGREES",
    "STANDARD_TUNING",
    "STRING_NAMES",
    "ArrangementStep",
    "ChordParser",
    "GuitarFretboard",
    "StepPreparation",
    "VoiceLeadingEngine",
    "Voicing",
    "format_progression",
    "format_musicxml",
    "format_tab_html",
    "format_tab_staff",
    "main",
    "normalised_harmony",
    "sounding_harmony",
    "supported_string_sets",
    "write_musicxml",
    "write_tab_html",
]