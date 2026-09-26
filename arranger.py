from __future__ import annotations

import re
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

# Soprano (melody) string indices a Drop-2 voicing may be pinned to, and the four
# contiguous strings each one uses. Index 0 = low E ... index 5 = high E.
#   5 -> strings D-G-B-E, melody on the high E string (traditional shape)
#   4 -> strings A-D-G-B, melody on the B string, one position lower on the neck
MELODY_STRING_CHOICES = (5, 4)

# Library version. Kept here as the single source of truth; pyproject.toml reads
# it via [tool.setuptools.dynamic] instead of duplicating the number.
__version__ = "0.2.0"


@dataclass
class Voicing:
    """Represents a specific fretboard voicing."""
    frets: List[int]
    top_fret: int
    avg_fret: float

    def tab_string(self) -> str:
        """Returns standard tab representation, e.g. 'x-x-12-13-13-13'."""
        return "-".join(str(f) if f >= 0 else "x" for f in self.frets)

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
    }

    @staticmethod
    def canonical_quality(chord_type: str) -> str:
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
    def parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
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
    def get_chord_tones(chord_type: str, chord_name: str = None) -> Tuple[int, ...]:
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
    }

    # Non-chord-tone strategy routing: canonical base quality -> {melody degree
    # (relative to root): extension quality that absorbs it as a chord tone}.
    # Only entries that are musically unambiguous are listed; anything missing
    # leaves the melody to the existing quality-only fallback.
    NON_CHORD_TONE_EXTENSIONS = {
        "maj7": {2: "maj9", 9: "6/9"},  # 9th, 6th/13th
        "6": {2: "6/9"},                # 9th
        "m7": {2: "m9"},                # 9th
        "7": {2: "9", 9: "13"},         # 9th, 13th
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
        chord_name: str = None,
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
        chord_name: str = None,
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

    # ------------------------------------------------------------------
    # Non-chord melody tones
    # ------------------------------------------------------------------
    @classmethod
    def is_chord_tone(cls, melody_note: Note, chord_type: str, chord_name: str = None) -> bool:
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
        next_melody: str = None,
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
        """
        if non_chord_tone not in cls.NON_CHORD_TONE_STRATEGIES:
            raise ValueError(
                f"Unknown non_chord_tone strategy {non_chord_tone!r}; "
                f"expected one of {cls.NON_CHORD_TONE_STRATEGIES}"
            )

        arrangements: List[ArrangementStep] = []
        
        for index, (note_str, chord_type, name) in enumerate(progression):
            melody_note = Note(note_str)
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


# --- Demonstration ---
def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    annotation = ""
    if step.non_chord_tone:
        if step.harmonized_as:
            annotation = f" (non-chord tone -> {step.harmonized_as} via {step.strategy})"
        else:
            annotation = " (non-chord tone)"
    print(
        f"Chord: {step.chord:<8} | Melody: {step.melody:<3}{annotation} | "
        f"Tab [E-A-D-G-B-E]: {step.voicing.tab_string()} | Melody string: {melody_string}"
    )


def main() -> None:
    """
    Prints the built-in demonstration arrangements.

    Runs the four example progressions (minor ii-V-i, major ii-V-I, a low-register
    cadence with the melody on the B string, and a bar of non-chord melody tones
    shown under every strategy) through VoiceLeadingEngine.arrange_progression and
    prints each resulting tab. This is the entry point exposed as the
    `jazz-arranger` console script (see pyproject.toml).
    """
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


if __name__ == "__main__":
    main()