"""The instrument, and the two value types every other module speaks in.

`STANDARD_TUNING` and `GuitarFretboard` are the physical facts: which six strings
there are, what they are tuned to, and how a note becomes a fret. Nothing below
this module decides anything musical.

`Voicing` and `ArrangementStep` live here rather than with the engine that builds
them, and that placement is what keeps the package acyclic:

- `grips` *constructs* a `Voicing`, so `Voicing` has to be below `grips`;
- `Voicing.role` and `ArrangementStep.role` both default to `ROLE_TARGET`, so the
  role vocabulary has to be below `grips` and `texture` alike. `ROLE_TARGET` and
  `ROLE_FILL` are therefore *defined* here and re-exported by `texture`, rather
  than the other way round;
- `Voicing.tab_block` calls `cells_from_frets` / `_tab_block_from_cells`, so the
  tab-cell primitives have to be below `Voicing` too, and `render` imports them
  from here instead of owning them. `STAFF_CELL_WIDTH` was the second of two
  identical definitions of that one constant; `tabstaff` had the other.

`ArrangementStep` is here for one more reason: `bass` compares steps and `chords`
annotates them, and both sit below `steps`.
"""

from __future__ import annotations

from musthe import Note

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
# reharmonisation, no clause (see VoiceLeadingEngine.get_melody_only_voicing).
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
# in-window shape, and arrange_progression already emits such a step as a rest with the
# reason on it -
# losing a chord of the tune to keep a fretboard preference would be a bad trade.
NECK_FRET_MIN = 2
NECK_FRET_MAX = 13
# The neck position above which the melody is transposed down an octave and voiced on
# the B string instead of up at the top of the high E string. The B string is five
# semitones below the high E, so the same written pitch sits five frets *higher* on it
# (D5 is fret 10 on the high E, fret 15 on the B) - the only way to bring a high melody
# down the neck is to drop it an octave and let the B string play it an octave lower.
# A voicing whose soprano is above this fret is therefore re-voiced an octave down.
HIGH_FRET_LIMIT = 13


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


def note_name(midi: int) -> str:
    """
    Spells a MIDI number as a pitch-class name plus octave, e.g. 82 -> 'Bb5'.

    Used when a step has been transposed down an octave and has to report the pitch
    that actually sounds. Flats are preferred, matching PITCH_CLASS_NAMES and the
    jazz spelling used elsewhere in this module. Takes a raw MIDI number because
    musthe.Note only parses a string, so an octave-transposed pitch has to be
    spelled before it can be rebuilt as a Note.
    """
    return f"{PITCH_CLASS_NAMES[midi % 12]}{midi // 12 - 1}"


# A principal melody note: the chord is spelled out in full.
ROLE_TARGET = "target"
# A connecting note: a shell, an interval, or the melody alone.
ROLE_FILL = "fill"

# Why a step sounds nothing, recorded on `ArrangementStep.silence` and phrased by
# the renderer (`annotation._silence_clause`). A position the guitar cannot play is
# still **emitted** - carrying the bar, the beat and the chord name - so the tab
# keeps its line-up against the tune; a message alone was not enough, because it
# reached nobody reading the part. Five values, one
# per route that can decline to play:
# The grid - the layer that decides when each part sounds - placed nothing here. The
# phrase a reader sees (`annotation._SILENCE_PHRASES`) names the *request* rather than
# the grid, which is the vocabulary a caller has.
SILENCE_GRID = "grid"
SILENCE_NC_COMPING = "nc_comping"  # an NC bar: nothing for a comping part to state
SILENCE_NO_SHAPE = "no_shape"    # no shape in the palette, and the tune cannot stand alone
SILENCE_OUT_OF_REACH = "out_of_reach"  # no string reaches the written melody note
SILENCE_TUNE_SILENT = "tune_silent"    # a melody-only selection at a note-less position

__all__ = [
    "STANDARD_TUNING",
    "STRING_NAMES",
    "PITCH_CLASS_NAMES",
    "NO_CHORD",
    "MELODY_STRING_CHOICES",
    "MELODY_STRING_CHOICES_FULL",
    "NECK_FRET_MIN",
    "NECK_FRET_MAX",
    "HIGH_FRET_LIMIT",
    "GuitarFretboard",
    "Note",
    "note_name",
    "ROLE_TARGET",
    "ROLE_FILL",
    "SILENCE_GRID",
    "SILENCE_NC_COMPING",
    "SILENCE_NO_SHAPE",
    "SILENCE_OUT_OF_REACH",
    "SILENCE_TUNE_SILENT",
]


