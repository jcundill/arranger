"""Chord symbols: what a name means, and what a melody note does to it.

`ChordParser` is the one place a chord symbol is read - root, quality, and the
full tone set per quality. `QUALITY_ALIASES` resolves spelling to canonical form,
and `CHORD_TONES_FROM_ROOT` answers "is this note in this chord", which is a
*different* question from the one the drop-2 tables answer: those list only the
four notes a shape can voice, so the root of a rootless `7b9` is a chord tone that
no shape sounds.

The non-chord-tone machinery is here for the same reason. A melody note that is
not a chord tone is still a statement about a *chord*, and routing it to an
extension or a dim7 substitute is chord theory rather than voicing. So
`is_chord_tone`, `resolve_non_chord_tone` and `NON_CHORD_TONE_EXTENSIONS` are
functions here, and `VoiceLeadingEngine` keeps one-line classmethod delegates so
the existing `VoiceLeadingEngine.is_chord_tone(...)` call sites keep working.

`normalised_harmony` and `sounding_harmony` compare two spellings of one chord,
which is what lets a repeated melody be recognised as a hold across `D-7` and
`Dm7`. They read only a step's `chord` and `harmonized_as`, and take the type
itself under `TYPE_CHECKING`, which is what keeps this module below `steps`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from musthe import Note

from .tuning import PITCH_CLASS_NAMES

if TYPE_CHECKING:  # pragma: no cover - type only, never imported at runtime
    from .tuning import ArrangementStep


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
        'm7'): lower-casing first turns 'mMaj7' into 'mmaj7', which is no key in any
        table. Unknown qualities are returned unchanged so callers can report them.
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

    Decides whether a repeated melody is still a hold: a note repeating
    across a *chord change* is not a held shape, it is a new harmony that the
    held soprano has to be heard against.
    """
    return normalised_harmony(step.chord, step.harmonized_as)


# Non-chord-tone strategy routing: canonical base quality -> {melody degree
# (relative to root): extension quality that absorbs it as a chord tone}.
# Only entries that are musically unambiguous are listed; anything missing
# leaves the melody to the existing quality-only fallback.
NON_CHORD_TONE_EXTENSIONS = {
    # A 9th over a plain triad - the two rows this table was missing. A quality
    # with no row keeps the legacy quality-only fallback, and the three families
    # that have no fallback at all (`shell`, `duo`, `interval`, whose shapes are
    # defined by the chord's own degrees) then had nothing to fall back to, so
    # the step went missing instead: `Ebmaj` under `F4` in "But Not For Me" bar 2
    # with `--grips shell` produced no candidate and was dropped. `add9` is the
    # narrowest quality that contains the 9th, `madd9` its minor twin, and both
    # are already in CHORD_TONES_FROM_ROOT, SHELL_DEGREES and the drop-2 tables,
    # so no other table needs a row for them.
    "maj": {2: "add9"},
    "m": {2: "madd9"},
    "maj7": {2: "maj9", 6: "maj7#11", 9: "6/9"},   # 9th, #11, 6th/13th
    "6": {2: "6/9"},                               # 9th
    "m7": {2: "m9"},                               # 9th
    "m7b5": {2: "m9b5"},                           # 9th (half-diminished 9)
    # 9th, 11th (the suspended dominant), #11, b13, 13th, and the b9.
    #
    # The b9 is the one altered tension a dominant has that no extension of its own
    # names: `7alt` would have to be chosen instead, and that claims the #9, #5 and
    # b13 too, which the melody never stated. `7b9` is the narrowest quality that
    # contains the b9, and it is already voiceable - so this is the smallest
    # substitution that makes the note a chord tone.
    #
    # It is also the note a tritone substitution exists to absorb: the b9 of G7 is
    # the 3rd of Db7, so both routes make the melody a chord tone. This one keeps
    # the written root and the other moves it, which is why it is a table row
    # rather than a strategy - see docs/history/reharmonisation-proposals.md.
    "7": {1: "7b9", 2: "9", 5: "7sus4", 6: "7#11", 8: "7b13", 9: "13"},
    "7b9": {5: "7sus4", 6: "7#11", 8: "7b13"},     # 11th, #11, b13
    "9": {6: "7#11", 9: "13"},                     # #11, 13th
    "13": {6: "7#11"},                             # #11
}

# Accepted values for arrange_progression(non_chord_tone=...).
NON_CHORD_TONE_STRATEGIES = ("extension", "diminished", "sustain", "legacy")


# ------------------------------------------------------------------
# Non-chord melody tones
# ------------------------------------------------------------------
def is_chord_tone(melody_note: Note, chord_type: str, chord_name: Optional[str] = None) -> bool:
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

def resolve_non_chord_tone(
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
        extension = NON_CHORD_TONE_EXTENSIONS.get(canonical, {}).get(degree)
        if extension:
            return extension, f"{root_str}{extension}"
        return None

    if strategy == "diminished":
        target_pc = _resolution_pitch_class(melody_note, root_str, canonical, next_melody)
        if target_pc is None:
            return None
        # A dim7 is symmetrical, so naming the root a semitone below the
        # resolution target is the idiomatic Barry Harris spelling; all four
        # enharmonic roots finger identically.
        dim_root = PITCH_CLASS_NAMES[(target_pc - 1) % 12]
        return "dim7", f"{dim_root}dim7"

    return None

def _resolution_pitch_class(
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
