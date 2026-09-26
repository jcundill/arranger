from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
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

# Library version. Kept here as the single source of truth; pyproject.toml reads
# it via [tool.setuptools.dynamic] instead of duplicating the number.
# 0.4.0 added the optional Weimar Jazz Database corpus integration (wjazzd.py).
__version__ = "0.4.0"


@dataclass
class Voicing:
    """Represents a specific fretboard voicing."""
    frets: List[int]
    top_fret: int
    avg_fret: float

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
        cells = [("x" if f < 0 else str(f)).rjust(2) for f in self.frets]
        lines = []
        for string_index in range(len(self.frets) - 1, -1, -1):
            # The highest string is labelled with a lowercase 'e', the usual tab
            # convention, so the top and bottom lines of the block stay distinct.
            name = "e" if string_index == 5 else STRING_NAMES[string_index]
            lines.append(f"{name}|{cells[string_index]}-|")
        return lines

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
        """
        melody_midi = melody_note.midi_note()
        valid_voicings: List[Voicing] = []
        
        # The soprano (melody) string plus the three strings directly beneath it:
        # top_string=5 -> D-G-B-E, top_string=4 -> A-D-G-B.
        top_fret = GuitarFretboard.note_to_fret(top_string, melody_note)
        
        if top_fret < 0 or top_fret > 18:
            return valid_voicings

        canonical_type = ChordParser.canonical_quality(chord_type)
        interval_templates = cls.DROP2_INTERVAL_SETS.get(canonical_type, [])
        deg_offsets = cls.DEGREE_OFFSETS_FROM_ROOT.get(canonical_type)

        target_idx = None
        if chord_name and deg_offsets:
            root_str, _ = ChordParser.parse_chord_name(chord_name)
            if root_str:
                mel_offset = ChordParser.get_melody_degree(root_str, melody_note)
                for idx, d in enumerate(deg_offsets):
                    if d % 12 == mel_offset:
                        target_idx = idx
                        break
        
        for idx, template in enumerate(interval_templates):
            if target_idx is not None and idx != target_idx:
                continue

            frets = [-1, -1, -1, -1, -1, -1]
            frets[top_string] = top_fret
            
            # Map the remaining 3 voices down the three strings below the soprano
            possible = True
            for i, offset in enumerate(template[1:], start=1):
                string_idx = top_string - i
                target_midi = melody_midi + offset
                open_midi = STANDARD_TUNING[string_idx].midi_note()
                fret = target_midi - open_midi
                
                # Check playability constraints (max 5-fret span, valid fretboard area)
                if 0 <= fret <= 18 and abs(fret - top_fret) <= 5:
                    frets[string_idx] = fret
                else:
                    possible = False
                    break
            
            if possible:
                valid_voicings.append(Voicing(
                    frets=frets,
                    top_fret=top_fret,
                    avg_fret=sum([f for f in frets if f >= 0]) / 4.0
                ))
                
        return valid_voicings

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
        """
        candidates: List[Voicing] = []
        for top_string in top_strings:
            candidates.extend(cls.get_drop2_voicings(melody_note, chord_type, chord_name, top_string))

        if not candidates and chord_name:
            for top_string in top_strings:
                candidates.extend(cls.get_drop2_voicings(melody_note, chord_type, None, top_string))

        return candidates

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
        """
        for string_index in _melody_only_string_order(prefer):
            fret = GuitarFretboard.note_to_fret(string_index, melody_note)
            if 0 <= fret <= 18:
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

        return Voicing(frets=frets, top_fret=top_fret, avg_fret=sum(active) / 4.0)

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
    def arrange_progression(
        cls,
        progression: List[Tuple[str, str, str]],
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
        non_chord_tone: str = "extension",
    ) -> List[ArrangementStep]:
        """
        Takes a progression of (Melody Note, Chord Quality, Name) tuples 
        and computes the optimal voice-led arrangement.

        top_strings selects which strings may carry the melody (see
        MELODY_STRING_CHOICES). The default allows both the high E string and the B
        string, so melodies below E4 - unreachable on the high E string - are still
        arranged, and a chord is free to stay in the position the previous chord left
        behind instead of jumping down the neck.

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
                arrangements.append(ArrangementStep(
                    chord=name,
                    melody=note_str,
                    voicing=solo_voicing,
                    melody_only=True,
                ))
                continue

            # get_all_drop2_voicings applies the chord-tone match first and the
            # quality-only fallback second, across every allowed soprano string.
            candidates = cls.get_all_drop2_voicings(
                melody_note, chord_type, chord_name=name, top_strings=top_strings
            )

            strategy_used: Optional[str] = None
            harmonized_as: Optional[str] = None
            is_non_chord_tone = (
                ChordParser.canonical_quality(chord_type) in ChordParser.CHORD_TONES_FROM_ROOT
                and not cls.is_chord_tone(melody_note, chord_type, name)
            )

            if is_non_chord_tone and non_chord_tone != "legacy":
                previous_voicing = arrangements[-1].voicing if arrangements else None

                # Strategy 3 first: holding the shape moves less than any re-voicing.
                if non_chord_tone == "sustain" and previous_voicing is not None:
                    sustained = cls.sustain_inner_voices(previous_voicing, melody_note)
                    if sustained is not None:
                        candidates = [sustained]
                        strategy_used = "sustain"
                        harmonized_as = arrangements[-1].chord

                # Strategies 1 and 2 reharmonise the note as a genuine chord tone.
                if strategy_used is None:
                    resolved = cls.resolve_non_chord_tone(
                        melody_note,
                        chord_type,
                        name,
                        non_chord_tone,
                        next_melody=cls._next_resolution_melody(progression, index),
                    )
                    if resolved is not None:
                        substitute_quality, substitute_name = resolved
                        substituted = cls.get_all_drop2_voicings(
                            melody_note,
                            substitute_quality,
                            chord_name=substitute_name,
                            top_strings=top_strings,
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
                print(f"Warning: No valid drop-2 voicing found for {name} with melody {note_str}")
                continue

            if not arrangements:
                # Pick a comfortable middle-fretboard position for the first sounding chord
                best_voicing = min(candidates, key=lambda v: abs(v.avg_fret - 9))
            else:
                # Minimize sounding-pitch movement from the previous chord. Comparing
                # pitches rather than fret numbers stays meaningful when the melody moves
                # between the high E and B strings, where one pitch sits on a different string.
                prev_voicing = arrangements[-1].voicing
                best_voicing = min(
                    candidates,
                    key=lambda v: cls.calculate_pitch_leading_distance(prev_voicing, v)
                )
                
            arrangements.append(ArrangementStep(
                chord=name,
                melody=note_str,
                voicing=best_voicing,
                non_chord_tone=is_non_chord_tone,
                strategy=strategy_used,
                harmonized_as=harmonized_as,
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
    alone)'. Empty string for an ordinary chord tone. Shared by format_progression
    and the demonstration so the two renderings cannot drift apart.
    """
    if step.melody_only:
        return " (no chord - melody alone)"
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


def _staff_columns(
    steps: List[ArrangementStep],
    beats_per_bar: int,
    rhythm: bool,
    collapse: bool = True,
) -> List[Tuple[float, Optional[ArrangementStep], bool]]:
    """
    Places each step on an absolute beat, padding the gaps with rests.

    An absolute beat is `bar * beats_per_bar + (beat - 1)`, the same signed-bar
    arithmetic NoteEvent.beat_position uses, so a pickup in a negative bar sorts
    before bar 0 without a special case. The list is sorted and de-duplicated
    because two steps can share an onset (a chord change inside a held bar), and
    the first step in a column owns that column.

    Each column comes back with a `strikes` flag. With `collapse` on, a step
    sounding exactly the same pitches as the one before it is a *hold*, not a new
    attack: it stays on the grid (so the barlines and the chord line still line
    up) but prints no frets, because the previous shape is still ringing. That is
    what separates chord-melody tab from a chord list - the skeleton voices one
    step per eighth, and a player holds the shape rather than restriking it eight
    times a bar. Comparing sounding pitches rather than fret numbers is what makes
    this work: the same shape reached by a different route is still the same hold.

    Without timing - a hand-written progression, or `rhythm=False` - each step
    simply takes the next beat, reproducing a one-chord-per-cell grid.
    """
    if rhythm and steps and all(step.has_timing for step in steps):
        placed: List[Tuple[float, ArrangementStep]] = [
            (step.bar * beats_per_bar + (step.beat - 1), step)  # type: ignore[operator]
            for step in steps
        ]
    else:
        placed = [(float(index), step) for index, step in enumerate(steps)]

    columns: List[Tuple[float, Optional[ArrangementStep]]] = []
    for onset, step in sorted(placed, key=lambda item: item[0]):
        if columns and abs(columns[-1][0] - onset) < 1e-9:
            continue
        columns.append((onset, step))

    # Fill the holes a real rhythm leaves, so a chord held for two beats is
    # followed by a rest rather than by the next chord jammed up against it.
    # The grid starts at the first onset, not at zero: a head selected from bar 1
    # (or from a negative pickup bar) should not be preceded by a screen of empty
    # bars standing in for the music before it.
    filled: List[Tuple[float, Optional[ArrangementStep]]] = []
    current = columns[0][0] if columns else 0.0
    for onset, step in columns:
        while current < onset - 1e-9:
            filled.append((current, None))
            current += 1.0
        filled.append((onset, step))
        current = onset + 1.0

    if not collapse:
        return [(onset, step, True) for onset, step in filled]

    collapsed: List[Tuple[float, Optional[ArrangementStep], bool]] = []
    held: Optional[Tuple[int, ...]] = None
    for onset, step in filled:
        if step is None:
            # A rest breaks the ring: whatever was sounding has stopped, so the
            # next step is a fresh attack even when it is the same shape.
            held = None
            collapsed.append((onset, None, False))
            continue
        pitches = tuple(sorted(step.voicing.midi_notes()))
        strikes = pitches != held
        collapsed.append((onset, step, strikes))
        if strikes:
            held = pitches
    return collapsed


def _carries_melody(steps: List[ArrangementStep], string_index: int) -> bool:
    """True when the melody rides on this string somewhere in the progression."""
    return any(
        step.voicing.frets[string_index] >= 0
        and step.voicing.soprano_string() == string_index
        for step in steps
    )


def _staff_breaks(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
    measures_per_line: int,
) -> set:
    """
    The column indexes that carry a barline.

    A barline belongs to the *first* column of a bar, so a column qualifies only
    when its bar differs from the previous column's. Testing the bar number alone
    would flag every column of that bar - and since a bar holds several columns,
    the staff would come out with a barline between every chord.

    Barlines are drawn every `measures_per_line` bars, measured from the first
    column's own bar rather than from bar 0, because a head picked up
    mid-transcription (a negative pickup bar, or a `--bars` range that starts at
    12) must not be padded out by the bars before it.
    """
    start_bar = int(columns[0][0] // beats_per_bar)
    breaks = set()
    previous_bar: Optional[int] = None
    for index, (onset, _, _) in enumerate(columns):
        bar = int(onset // beats_per_bar)
        if index and bar != previous_bar and (bar - start_bar) % measures_per_line == 0:
            breaks.add(index)
        previous_bar = bar
    return breaks


def format_tab_staff(
    steps: List[ArrangementStep],
    beats_per_bar: int = 4,
    rhythm: bool = True,
    show_chords: bool = True,
    show_melody: bool = False,
    show_melody_string: bool = True,
    show_mutes: bool = False,
    collapse: bool = True,
    measures_per_line: int = 4,
) -> str:
    """
    Renders a whole progression as a standard six-line guitar staff.

    format_progression() gives one line, or one six-line block, *per chord*. This
    instead lays every step along a single staff in reading order - high E on top
    down to low E - which is how printed tab is read, with the chord names on a
    line above and a barline wherever the bar changes.

    Fret cells are a fixed width and the number sits at the left of its column,
    which is how tab is written and what keeps a chord name aligned with the fret
    it belongs to. The width is at least two characters, so a two-digit fret never
    runs into its neighbour. An unsounded string is left blank by default:
    in chord-melody a voice that is still ringing is not restruck, and marking
    it `x` on every chord would be noise. Pass `show_mutes` to spell them out. A
    melody-only (no chord) step always shows its `x`s, because there the other
    strings really are silent.

    Args:
        steps: arranged steps, typically from arrange_progression().
        beats_per_bar: beats in a bar, used to place the barlines.
        rhythm: space the steps on their real beats. This needs every step to
            carry `bar` and `beat`; if any does not, the uniform grid is used, so
            a hand-written progression still renders sensibly.
        show_chords: draw the chord-name line.
        show_melody: draw the melody-note line.
        show_melody_string: mark the string carrying the melody with a `*`.
        show_mutes: print `x` on every unsounded string.
        collapse: strike a shape once and let it ring while the melody moves over the
            same pitches, instead of restriking it on every step. This is the
            default, and it is what makes a held chord read as a held chord.
        measures_per_line: bars per staff line; the last line may be shorter.

    Returns:
        The rendered staff as a newline-joined string, or "" for no steps. Pure:
        nothing is printed, so the caller stays in control of the output.
    """
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if measures_per_line < 1:
        raise ValueError(f"measures_per_line must be at least 1, got {measures_per_line!r}")
    if not steps:
        return ""

    columns = _staff_columns(steps, beats_per_bar, rhythm, collapse)
    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)

    def cell(step: Optional[ArrangementStep], string_index: int, strikes: bool) -> str:
        """One fret cell: a fret number, a mute marker, or a blank."""
        if step is None or not strikes:
            return ""
        fret = step.voicing.frets[string_index]
        if fret < 0:
            return _MUTED_CELL if (show_mutes or step.melody_only) else ""
        return str(fret)

    # Every line shares one column width. A chord name is wider than two
    # characters, so the grid widens to the longest label rather than letting the
    # chord line push itself out of step with the frets underneath it.
    width = _STAFF_CELL_WIDTH
    for _, step, _ in columns:
        if step is None:
            continue
        for text in (step.chord, step.melody):
            width = max(width, len(text))

    def line(text_for: Any, when_struck: bool, dedupe: bool = False) -> str:
        """Renders a chord or melody line on the staff's own column grid.

        `when_struck` is False for the melody line, which must label every step:
        the melody moves on even while the shape underneath it is being held.
        `dedupe` prints a label only where it changes from the previous one, which
        is how a lead sheet spells a chord held across several slots.
        """
        # The same three-character offset the string lines use (label, melody
        # marker, '|'), so a chord name starts in the column of its own frets.
        out = ["   "]
        previous = None
        for index, (_, step, strikes) in enumerate(columns):
            if index in breaks:
                out.append("|")
            elif index:
                out.append(" ")
            text = text_for(step) if (strikes or not when_struck) else ""
            if dedupe and text and text == previous:
                text = ""
            if text:
                previous = text
            out.append(text.ljust(width) if text else " " * width)
        return "".join(out).rstrip()

    def string_line(string_index: int) -> str:
        out = ["*", "|"] if show_melody_string and _carries_melody(steps, string_index) else [" ", "|"]
        for index, (_, step, strikes) in enumerate(columns):
            if index in breaks:
                out.append("|")
            elif index:
                out.append("-")
            out.append(cell(step, string_index, strikes).ljust(width))
        out.append("|")
        # The highest string is labelled with a lowercase 'e', the usual tab
        # convention, so the top and bottom lines of the staff stay distinct.
        name = "e" if string_index == 5 else STRING_NAMES[string_index]
        return f"{name}{''.join(out)}"

    lines: List[str] = []
    if show_chords:
        lines.append(
            line(lambda step: step.chord if step else "", when_struck=True, dedupe=True)
        )
    if show_melody:
        lines.append(line(lambda step: step.melody if step else "", when_struck=False))
    lines.extend(string_line(index) for index in range(5, -1, -1))
    return "\n".join(lines).rstrip()


# --- HTML tab ---
#
# The staff above is ASCII, because that is what goes in a terminal. A browser can
# do better: a table gives every column its own box, so fret numbers, chord names
# and barlines align by construction rather than by counting characters, and the
# page can be styled, reflowed and printed. The output is one self-contained file -
# the stylesheet is inlined - so it can be emailed or opened from disk.
#
# Everything here reuses _staff_columns and _staff_breaks, so the text and HTML
# renderings place a chord in the same column by construction and cannot drift.

# Cell classes used by both the stylesheet and the row builder below. They are
# named here rather than spelled inline so a rename cannot half-apply.
_CLASS_SYSTEM = "system"
_CLASS_MEASURE = "measure"
_CLASS_STRING = "string"
_CLASS_CHORD = "chord"
_CLASS_MELODY = "melody"
_CLASS_MUTE = "mute"
_CLASS_SOPRANO = "soprano"
_CLASS_BARNUM = "barnum"

_HTML_STYLESHEET = """
:root { color-scheme: light dark; --ink: #1b1b1b; --rule: #b8b8b8;
        --fret: #1b1b1b; --accent: #7a2f2f; --mute: #a9a9a9;
        --strike: #f2ede2; --page: #fdfdfb; --faint: #8a8a8a; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #e8e6e1; --rule: #4a4a4a; --fret: #f2efe9; --accent: #e0a3a3;
          --mute: #6f6f6f; --strike: #2b2b2b; --page: #16181c; --faint: #8f8f8f; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 2.5rem 1.5rem 4rem; background: var(--page);
       color: var(--ink);
       font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 68rem; margin: 0 auto; }
h1 { font-size: 1.5rem; font-weight: 650; margin: 0 0 .25rem; letter-spacing: -.01em; }
p.sub { margin: 0 0 .35rem; color: var(--faint); font-size: .9rem; }
p.meta { margin: 0 0 2rem; font-size: .8rem; color: var(--faint); }
.systems { display: flex; flex-direction: column; gap: 1.6rem; }
.system { display: flex; align-items: stretch; overflow-x: auto; }
.measure { border-left: 1px solid var(--rule); padding: 0 .5rem; }
.measure:first-of-type { border-left: 2px solid var(--rule); }
.barnum { font-variant-numeric: tabular-nums; font-size: .7rem; color: var(--faint);
          align-self: flex-start; padding-top: .1rem; min-width: 1.6rem;
          text-align: right; }
table { border-collapse: collapse;
        font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
th, td { padding: .05rem .28rem; text-align: left; white-space: nowrap; }
/* Chord names share a column with the frets beneath them, so a name wider than a
   fret widens the column instead of shifting the staff out of alignment. */
tr.chord td { font-family: ui-sans-serif, system-ui, sans-serif; font-weight: 600;
              color: var(--accent); font-size: .82rem; padding-bottom: .15rem; }
tr.melody td { font-size: .72rem; color: var(--faint); padding-bottom: .3rem; }
tr.string th { font-weight: 500; font-size: .72rem; color: var(--faint); width: 1ch;
               padding-right: .5rem; }
tr.string th.soprano { color: var(--accent); }
tr.string td { font-size: .9rem; color: var(--fret);
               font-variant-numeric: tabular-nums; min-width: 1.1ch; }
/* A struck chord is tinted; a held one is left plain, because the shape is still
   ringing from the attack before it. */
td.strike { background: var(--strike); border-radius: 2px; }
td.mute { color: var(--mute); }
.notes { margin: 2.5rem 0 0; font-size: .78rem; color: var(--faint); }
.notes li { margin: .2rem 0; }
@media print { body { padding: 0; } .system { overflow: visible; } }
"""


def _escape(text: str) -> str:
    """HTML-escapes a value taken from the arrangement.

    Chord names and note names can come from the corpus database, so they are
    treated as untrusted text rather than assumed safe to interpolate.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _staff_lines(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    breaks: set,
    beats_per_bar: int,
) -> List[List[int]]:
    """
    Splits the columns into the systems of music that will be drawn, in order.

    A system ends at a barline, so a break both closes one system and opens the
    next. Columns that fall between barlines are all kept, including the rests.
    The last system may be short, which is why this returns a list of lists rather
    than a single count.
    """
    lines: List[List[int]] = []
    current: List[int] = []
    for index, (onset, _, _) in enumerate(columns):
        if index in breaks and current:
            lines.append(current)
            current = []
        current.append(index)
    if current:
        lines.append(current)
    return lines


def _html_chord_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    previous: Optional[str],
) -> Tuple[str, Optional[str]]:
    """
    One row of chord names, plus the chord now in force for the next measure.

    A name is printed only where it changes from the one in force, and only on a
    struck chord, which is how a lead sheet spells a chord held across several
    slots. The running `previous` is threaded through the whole page rather than
    kept in module state or reset per measure, so a chord spanning a barline is
    named once, and two calls in a row cannot see each other's chords.
    """
    # The leading empty <th> matches the string rows' label cell. Without it the
    # whole row would sit one column left of the frets it belongs to, because a
    # table column is shared by every row above and below it.
    cells: List[str] = ["<th></th>"]
    for index in measure:
        _, step, strikes = columns[index]
        if step is None or not strikes:
            cells.append("<td></td>")
            continue
        if step.chord != previous:
            cells.append(f"<td>{_escape(step.chord)}</td>")
            previous = step.chord
        else:
            cells.append("<td></td>")
    return f'<tr class="{_CLASS_CHORD}">{"".join(cells)}</tr>', previous


def _html_melody_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
) -> str:
    """
    One row of melody note names.

    Labelled on every step, not only on a strike: the melody moves on even while
    the shape underneath it is being held, so the held columns are exactly where a
    note name is most useful.
    """
    cells = "<th></th>" + "".join(
        f"<td>{_escape(columns[i][1].melody) if columns[i][1] else ''}</td>"
        for i in measure
    )
    return f'<tr class="{_CLASS_MELODY}">{cells}</tr>'


def _html_string_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    string_index: int,
    sopranos: set,
    show_mutes: bool,
) -> str:
    """
    One row of fret numbers for a measure, on the string given.

    A ringing voice is not restruck, so a muted string is left as an empty cell
    rather than marked x on every chord - that would be noise. `show_mutes` spells
    them out, and a melody-only step always shows its x, because there the other
    strings really are silent.
    """
    label = (
        f'<th class="{_CLASS_SOPRANO}">*</th>'
        if string_index in sopranos
        else "<th></th>"
    )
    cells = [label]
    for index in measure:
        _, step, strikes = columns[index]
        if step is None or not strikes:
            cells.append("<td></td>")
            continue
        fret = step.voicing.frets[string_index]
        if fret < 0:
            cells.append(
                f'<td class="{_CLASS_MUTE}">x</td>'
                if (show_mutes or step.melody_only)
                else "<td></td>"
            )
        else:
            cells.append(f"<td>{fret}</td>")
    return f'<tr class="{_CLASS_STRING}">{"".join(cells)}</tr>'


def format_tab_html(
    steps: List[ArrangementStep],
    title: str = "Chord-melody arrangement",
    subtitle: str = "",
    beats_per_bar: int = 4,
    rhythm: bool = True,
    show_melody: bool = True,
    show_mutes: bool = False,
    collapse: bool = True,
    measures_per_line: int = 4,
    notes: Optional[Sequence[str]] = None,
) -> str:
    """
    Renders a whole progression as a self-contained HTML tab page.

    The same layout the ASCII staff draws, in a form a browser can present well:
    every column is a table cell, so chord names, fret numbers and barlines stay
    aligned by the table rather than by counting characters, and the page carries
    its own stylesheet (including a dark-mode one), so it needs no network access
    and no sibling files.

    Args:
        steps: arranged steps, typically from arrange_progression().
        title: the page heading, and the browser window title.
        subtitle: an optional line under the heading, e.g. the performer.
        beats_per_bar: beats in a bar, used to place the barlines.
        rhythm: space the chords on their real beats. Falls back to a uniform grid
            when the steps carry no timing, exactly as format_tab_staff does.
        show_melody: draw the melody-note line.
        show_mutes: spell out the unsounded strings as a dimmed x. A melody-only
            step always shows its x, since there the strings really are silent.
        collapse: strike each shape once and let it ring, rather than restriking
            an unchanged shape on every step.
        measures_per_line: bars per system of music.
        notes: optional lines of provenance, e.g. the register lift decision.

    Returns:
        A complete HTML document as a string, or "" for no steps. Pure: nothing is
        printed and no file is written, so the caller stays in control.
    """
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if measures_per_line < 1:
        raise ValueError(f"measures_per_line must be at least 1, got {measures_per_line!r}")
    if not steps:
        return ""

    columns = _staff_columns(steps, beats_per_bar, rhythm, collapse)
    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)
    # Which strings carry the melody somewhere in the progression, so those rows
    # can be marked once for the whole page rather than per chord.
    sopranos = {index for index in range(6) if _carries_melody(steps, index)}

    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        f"<style>{_HTML_STYLESHEET}</style>",
        "</head>",
        "<body><main>",
        f"<h1>{_escape(title)}</h1>",
    ]
    if subtitle:
        parts.append(f'<p class="sub">{_escape(subtitle)}</p>')
    parts.append(
        f'<p class="meta">{len(steps)} step{"" if len(steps) == 1 else "s"}</p>'
    )
    parts.append('<div class="systems">')

    start_bar = int(columns[0][0] // beats_per_bar)
    # The chord in force, carried across systems so a chord held over a system
    # break is not named a second time.
    in_force: Optional[str] = None

    def bar_of(index: int) -> int:
        return int(columns[index][0] // beats_per_bar) - start_bar

    for line in _staff_lines(columns, breaks, beats_per_bar):
        parts.append(f'<div class="{_CLASS_SYSTEM}">')
        parts.append(f'<span class="{_CLASS_BARNUM}">{bar_of(line[0]) + 1}</span>')
        # Split the system into measures at each bar change, so every measure gets
        # its own ruled box. The last measure of a system may be short.
        measures: List[List[int]] = []
        for index in line:
            if measures and bar_of(measures[-1][0]) == bar_of(index):
                measures[-1].append(index)
            else:
                measures.append([index])
        for measure in measures:
            parts.append(f'<div class="{_CLASS_MEASURE}"><table>')
            chord_row, in_force = _html_chord_row(columns, measure, in_force)
            parts.append(chord_row)
            if show_melody:
                parts.append(_html_melody_row(columns, measure))
            for string_index in range(5, -1, -1):
                parts.append(
                    _html_string_row(
                        columns, measure, string_index, sopranos, show_mutes
                    )
                )
            parts.append("</table></div>")
        parts.append("</div>")

    parts.append("</div>")

    if notes:
        items = "".join(f"<li>{_escape(note)}</li>" for note in notes)
        parts.append(f'<ul class="notes">{items}</ul>')

    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_tab_html(steps: List[ArrangementStep], path: str, **kwargs: Any) -> str:
    """
    Renders `format_tab_html` to a file and returns the path written.

    The one function in this module that touches the filesystem, which is what
    lets every renderer stay pure. Writing is separated from rendering so a caller
    who only wants the string never creates a file by accident.
    """
    html = format_tab_html(steps, **kwargs)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return str(path)


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
            f"{_step_annotation(step)} {step.tab_line()}".rstrip()
            for step in steps
        )

    blocks = []
    for step in steps:
        header = f"{step.chord} ({step.melody}){_step_annotation(step)}"
        blocks.append("\n".join([header, *step.tab_block()]))
    return "\n\n".join(blocks)


# --- Demonstration ---
def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    print(
        f"Chord: {step.chord:<8} | Melody: {step.melody:<3}{_step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {step.tab_line()} | Melody string: {melody_string}"
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

    # Example 3: Low-register cadence (Dm7 -> G7 -> Cmaj7) with the melody in the
    # octave below middle C. E4 is the lowest note the high E string can play, so
    # these steps used to be skipped; on the B string (strings A-D-G-B) the phrase
    # sits in a comfortable low position instead.
    low_progression = [
        ("D4", "m7", "Dm7"),
        ("D4", "7", "G7"),
        ("C4", "maj7", "Cmaj7")
    ]
    result_low = engine.arrange_progression(low_progression)

    print("\n--- LOW-REGISTER CADENCE, MELODY ON THE B STRING (Dm7 -> G7 -> Cmaj7) ---")
    for step in result_low:
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

    # Example 5: Tab rendering. format_progression() returns the tab as a string
    # and prints nothing itself, so callers choose what to do with it. Here it is
    # used once horizontally and once as vertical six-line tab blocks.
    print("\n--- TAB RENDERING: format_progression(), one line per chord ---")
    print(format_progression(result_major))

    print("\n--- TAB RENDERING: format_progression(vertical=True), six lines per chord ---")
    print(format_progression(result_major, vertical=True))

    # Example 6: The whole progression on one six-line staff. format_tab_staff()
    # is the standard reading order - high E on top, chord names above, barlines
    # between bars - so it is what a player would actually read off the page. These
    # steps carry no timing, so the chords fall on consecutive beats; a transcribed
    # head (see `arranger.py corpus --tab staff`) is spaced on its real rhythm.
    print("\n--- TAB RENDERING: format_tab_staff(), one progression on a six-line staff ---")
    print(format_tab_staff(result_major, show_melody=True))

    # Example 7: The same cadence with the timing the corpus loader supplies, so the
    # chords sit on their own beats and a barline falls between the two bars.
    timed_major = engine.arrange_progression(major_progression)
    for index, step in enumerate(timed_major):
        step.bar, step.beat, step.duration = index, 1.0, 1.0
    print("\n--- TAB RENDERING: format_tab_staff() on a timed progression, barline per bar ---")
    print(format_tab_staff(timed_major, show_melody=True, measures_per_line=1))


if __name__ == "__main__":
    main()