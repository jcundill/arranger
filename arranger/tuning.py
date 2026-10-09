"""The instrument, and the two value types every other module speaks in.

`STANDARD_TUNING` and `GuitarFretboard` are the physical facts: which six strings
there are, what they are tuned to, and how a note becomes a fret. Nothing below
this module decides anything musical.

`Voicing` and `ArrangementStep` live here rather than with the engine that builds
them, and that placement is what keeps the package acyclic:

- `grips` *constructs* a `Voicing`, so `Voicing` has to be below `grips`;
- `Voicing.role` and `ArrangementStep.role` both default to `ROLE_TARGET`, so the
  role vocabulary has to be below `grips` and `textures` alike. `ROLE_TARGET` and
  `ROLE_FILL` are therefore *defined* here and re-exported by `textures`, rather
  than the other way round;
- `Voicing.tab_block` calls `_cells_from_frets` / `_tab_block_from_cells`, so the
  tab-cell primitives have to be below `Voicing` too, and `render` imports them
  from here instead of owning them. `_STAFF_CELL_WIDTH` was the second of two
  identical definitions of that one constant; `tabstaff` had the other.

`ArrangementStep` is here for one more reason: `bass` compares steps and `chords`
annotates them, and both sit below `steps`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

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


# A principal melody note: the chord is spelled out in full.
ROLE_TARGET = "target"
# A connecting note: a shell, an interval, or the melody alone.
ROLE_FILL = "fill"


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
    # Cached so the slash-bass rule (`slots.slash_bass_cost`) does not have to
    # re-derive it, and so a caller can ask "what is the bass of this grip" directly.
    bass_pc: Optional[int] = None
    # Which metric role produced this shape, mirroring ArrangementStep.role: ROLE_TARGET
    # for a shape that is meant to state the chord, ROLE_FILL for one that is only
    # connecting. Set by whichever generator produced the shape, so a caller
    # inspecting a candidate directly - rather than a chosen step - can still tell.
    # Defaulted, so every existing construction and the __getitem__ shim are
    # unaffected. A plain string rather than an enum, for the same reason `grip` is.
    role: str = ROLE_TARGET
    # A walking-bass thumb note merged into the fret vector, and the string carrying it.
    # Set **only after** `_best_voicing` has chosen the upper shape, never as a
    # candidate: `voicing_cost`'s `missing = 4 - len(active)` counts the voices that
    # sound, and a merged fifth voice would corrupt it. Selecting first and merging
    # after is what keeps the bass out of the cost tuple by construction rather than by
    # discipline.
    #
    # `bass_string` is recorded rather than assumed to be the low E, because the string
    # is chosen per note by proximity to the hand and the thumb genuinely moves between
    # strings as the left hand moves up the neck. `tabstaff` reads it to exclude the
    # bass from its hold comparison, and any renderer that wants to know which voice is
    # the thumb reads it here rather than guessing index 0.
    bass_midi: Optional[int] = None
    bass_string: Optional[int] = None

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

    def upper_midi_notes(self) -> List[int]:
        """
        Every sounding pitch except the walking-bass thumb note.

        The comparison both renderers use to decide hold-versus-strike reads this
        rather than `midi_notes()`, because a walking line changes the lowest pitch
        on every quarter: comparing the full set would break the hold chain
        permanently and destroy the "held shape, not a chord list" behaviour for the
        whole arrangement. Excluding the thumb is what lets a `bass_only` step read
        as a *held* upper shape with a moving thumb.

        The exclusion is by the **recorded string**, not by pitch or by a constant
        index, because the thumb is placed per note and genuinely moves between the
        6th, 5th and 4th strings. A step with no bass is unchanged.
        """
        if self.bass_midi is None or self.bass_string is None:
            return self.midi_notes()
        bass_string = self.bass_string
        # Filtered by string index, never by a position in a filtered list: the two are
        # different things. Enumerating the *pitches* and comparing that counter against
        # `bass_string` would keep the thumb and drop the melody whenever the thumb is
        # not the lowest-indexed active string - correct only when the thumb is on the
        # low E, where the two happen to coincide.
        return [
            GuitarFretboard.fret_to_midi(index, fret)
            for index, fret in enumerate(self.frets)
            if fret >= 0 and index != bass_string
        ]

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
    # The melody this step carries, or None when no note sounds at its position: a
    # comping slot placed by the grid where the tune is silent says so plainly rather
    # than borrowing a pitch (the deleted `_PLACEHOLDER_MELODY`, §9.3 step B). A held
    # position keeps the note in force, so None means *silent*, not *held* - the
    # onset/held/silent split is `headxml.melody_state` when the difference is asked.
    melody: Optional[str]
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
    # True when this step's chord could not be voiced **at all** under its melody: the
    # palette had no shape to offer, so the tune sounds alone and the harmony of this
    # slot is not stated. `melody_only` above is the opposite in origin - there the
    # slot had *no* chord (`NO_CHORD`), here there is one that nothing could voice.
    # Kept as its own field rather than derived from `grip == "melody"`, because a
    # texture **fill** is deliberately the melody alone and must not carry this claim:
    # the two arrive at the same shape by different routes, which is the distinction
    # `decisions.melody_alone_case` exists to keep. See `render._step_annotation`.
    chord_unvoiced: bool = False
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
    # True when a chorded step is harmonised with fewer than four voices, i.e. it is a
    # shell or a duo rather than a complete chord. The chord name printed above such a
    # step describes the harmony, not every note sounding under it, so the renderers
    # annotate it. Defaulted, so an ordinary four-note step is unaffected.
    partial: bool = False
    # Which metric role the texture rules gave this step: ROLE_TARGET on a principal
    # melody note (a full chord states the harmony there), ROLE_FILL on a connecting
    # note (a shell, an interval or the melody alone). Set by
    # VoiceLeadingEngine.arrange_progression from the slot's timing, and defaulted
    # to target so a hand-built step and every existing construction are unaffected.
    role: str = ROLE_TARGET
    # How metrically strong the slot was: 2 on beat 1, 1 on beat 3, 0 on any other
    # beat, and **-1 when the step carries no timing at all**. The -1 matters: it
    # separates "we know this note is weak" from "we were never told where it falls",
    # and it is what keeps a progression with no rhythm on the default path.
    # See `_metric_weight`.
    metric_weight: int = 0
    # --- Walking bass (texture="walking_bass") ---
    #
    # The bass note's role, one of the BASS_ROLE_* constants. Defaulted and a plain
    # string, like `role`.
    bass_role: Optional[str] = None
    # The step exists for the thumb and **nothing above it strikes**: the upper voices
    # are held from the previous strike and the melody is not re-attacked. This is the
    # opposite of `repeated`, not a variant of it - `repeated` marks a melody that *is*
    # re-articulated (the soprano strikes, the inner voices are held) - so setting one
    # never sets the other, and an NC step is never marked either.
    #
    # It is what lets the bass grid be finer than the melody grid: a bar whose melody is
    # a single whole note still gets a thumb note on each of its `beats_per_bar` beats,
    # one of them on the step that carries the melody and the rest bass-only. That is
    # four in 4/4 and **two in 2/2**, where a whole note is the whole bar - the grid is
    # `beats_per_bar` beats wide, not four quarters. `arrange_progression` therefore
    # returns more steps than the progression it was given under this texture, and this
    # field is how a renderer tells which is which.
    #
    # It is a statement about the **left hand**, so it never coexists with
    # `role == ROLE_TARGET`: a target states the harmony, and a step that re-states a
    # chord cannot also be one that holds the previous shape. `decisions.is_bass_only`
    # is what keeps the two apart - see `docs/open-issues.md` item 4, where a
    # walk-invented downbeat the melody moved onto arrived carrying both and every
    # renderer obeyed the flag and dropped the chord.
    bass_only: bool = False
    # The guitar does **not** sound the melody on this step: the melodic voice belongs
    # to another instrument, and this one is a guide-tone comping shape underneath it.
    # Set from `melody=` (MELODY_NONE) rather than inferred, so a renderer can ask the
    # question without re-deriving it from the grip - and so the answer survives on a
    # step a caller built by hand.
    #
    # `step.melody` still carries the tune. That is deliberate: it is the *written* note
    # the horn is playing, the chord name above the step belongs to it, and dropping it
    # would leave a band part with nothing to line up against. What is missing is the
    # guitar playing it, which is what this says.
    #
    # It changes what a renderer draws in one specific way: there is no soprano string
    # carrying the tune, so a `repeated` melody cannot be a soprano-only re-strike.
    # See `render._step_cells`, which holds the whole shape instead.
    melody_voiced: bool = True

    @property
    def grip(self) -> str:
        """
        Which grip family harmonised this step: one of GRIP_PREFERENCE for an
        ordinary chord, "melody" for a melody-alone step, "rest" for a rest.

        A **derived view** of `voicing.grip` rather than a second stored field,
        deliberately: the two were one fact stated twice, and on a no-chord step
        they disagreed - the step said "drop2" while the voicing said "melody"
        - which is the bug class `docs/one-fact.md` exists to remove. The
        voicing owns the fact, because it is set at construction by whichever
        generator produced the shape and read by `voicing_cost`; the step
        answers in its own spelling and cannot be written apart from the
        voicing, which is what makes disagreement impossible rather than merely
        asserted against.
        """
        return self.voicing.grip

    @property
    def bass(self) -> Optional[int]:
        """
        MIDI pitch of the thumb note under this step, or None when there is none.

        A **derived view** of `voicing.bass_midi`, for the same reason `grip` is a
        view of `voicing.grip`: the two were one fact stated twice, written
        together in `_attach_bass`, and a stored copy was another field that
        could disagree - see `docs/one-fact.md`, commit 2. The voicing owns the
        fact, because the thumb is merged into its fret vector and its string
        recorded beside the pitch; deriving the step's spelling from it is also
        what makes a copy taken *before* the merge impossible, which is the
        failure a defaulted field could not prevent. Attached only after the
        upper shape has been chosen, so it never enters the voicing cost.
        """
        return self.voicing.bass_midi

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
