"""The value types every other module speaks in: `Voicing`, `ArrangementStep` and
`Palette`, plus the tab-cell primitives they render through.

Sits above `tuning` (it reads `GuitarFretboard`, `STRING_NAMES` and `ROLE_TARGET`
from there) and below everything that builds or chooses a shape: `grips` constructs
a `Voicing`, so `Voicing` has to be below `grips`; `Voicing.role` and
`ArrangementStep.role` both default to `ROLE_TARGET`, so this module is below
`grips` and `texture` alike.

The tab-cell primitives live here because `Voicing.tab_block` calls
`cells_from_frets` / `_tab_block_from_cells`, and `render` imports them from here
instead of owning them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from .tuning import ROLE_TARGET, STRING_NAMES, GuitarFretboard

# What an unsounded string renders as when the caller asks to see mutes, and the
# width every fret cell is padded to. Two characters covers frets 0-18, which is
# the whole range the library allows, and it is the same convention tab_block()
# uses - so the two renderings put a fret in the same column.
MUTED_CELL = "x"
STAFF_CELL_WIDTH = 2


@dataclass
class Voicing:
    """Represents a specific fretboard voicing."""
    frets: List[int]
    top_fret: int
    avg_fret: float
    grip: str = "drop2"
    bass_pc: Optional[int] = None
    role: str = ROLE_TARGET
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
        return _tab_block_from_cells(cells_from_frets(self.frets))

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

    # Backward compatibility: dictionary-like indexing voicing["frets"]
    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


@dataclass(frozen=True)
class Palette:
    """What a palette offered under a melody note, and the shape it did not take.

    Recorded by the route that *chooses* a shape, where the choice is the engine's, and
    it is what makes a thin step explicable rather than mysterious: the chord name above
    a step describes the harmony, so a reader counting strings otherwise has to take on
    faith that nothing fuller was available.

    `available` is the most voices any candidate in that palette states. A three-voice
    shell under a palette that never had four is the palette's limit; the same shell
    under one that did is a decision, and the two read differently.

    `alternative` is the best candidate with **more** voices than the shape that was
    taken - the chord that is not being played, which is the question a reader actually
    asks - and `decided_by` is the element of `cost.voicing_cost` that ranked it lower.
    That index is never the voice-count criterion, since a fuller shape cannot lose on
    how many voices it has: it is correctness, the neck window or the hand's travel.

    `decided_by` is an index into that tuple rather than a phrase because the phrases
    live beside the tuple, as `cost.VOICING_COST_CRITERIA`. `cost.SPAN_CRITERION` is the
    one entry recorded by the demotion rule (`decisions.should_demote_to_melody_alone`)
    rather than by the tuple itself.

    `inside_window` is whether **any** candidate sits wholly inside the neck window, which
    is what makes an out-of-position shape explicable: the window is a preference and never
    a filter, so a shape outside it is played rather than dropped, and only the palette can
    say whether there was anything inside to play instead.

    `dropped_for_bass` is the shape the ranking preferred from the palette **before** the
    requested bass note narrowed it (`decisions.leaving_room_for_the_bass`). It is not
    `alternative`: that is the fuller shape the tuple turned down on merit, while this one
    was never ranked at all, because the thumb could not reach the line's note under it. A
    step that carries no thumb line leaves it None, and so does a narrow that did not change
    the winner - in both cases the shape played is the ranking's own first choice.

    `dropped_for_line` is the same fact one narrowing later: the shape the ranking preferred
    before the **comp line** narrowed the palette to the tone it put on top. It is recorded
    and deliberately **not printed** - the line narrows on almost every position, so a
    sentence for it would repeat on nearly every step, while what a reader needs is the tone
    and its role, which is `annotation._comp_line_clause`'s. What it is for is the
    measurement: it is how `docs/history/comp-line.md` shows what the line took away from the
    ranking.
    """

    available: int
    alternative: Optional[Voicing] = None
    decided_by: Optional[int] = None
    inside_window: bool = False
    dropped_for_bass: Optional[Voicing] = None
    dropped_for_line: Optional[Voicing] = None


# What the comp line's top voice is *doing* on a step, recorded on
# `ArrangementStep.top_role` and phrased by `annotation._comp_line_clause`. They live
# beside the field rather than in `comp_line`, which writes them, because `annotation`
# reads them and sits *below* `comp_line` in the dependency order - a vocabulary with
# two spellings is the thing this module exists to prevent. `comp_line` imports them
# back, so a caller that spells `comp_line.TOP_WALK_UP` still resolves.
TOP_OPENING = "opening"
TOP_WALK_UP = "walk up"
TOP_WALK_DOWN = "walk down"
TOP_APPROACH_FROM_ABOVE = "approach from above"
TOP_APPROACH_FROM_BELOW = "approach from below"
TOP_FILL_UP = "fill up"
TOP_FILL_DOWN = "fill down"


@dataclass
class ArrangementStep:
    """Represents one chord-melody step in an arranged progression."""
    chord: str
    melody: Optional[str]
    voicing: Voicing
    non_chord_tone: bool = False
    strategy: Optional[str] = None
    harmonized_as: Optional[str] = None
    melody_only: bool = False
    chord_unvoiced: bool = False
    original_melody: Optional[str] = None
    bar: Optional[int] = None
    beat: Optional[float] = None
    duration: Optional[float] = None
    repeated: bool = False
    partial: bool = False
    palette: Optional[Palette] = None
    role: str = ROLE_TARGET
    metric_weight: int = 0
    bass_role: Optional[str] = None
    top_role: Optional[str] = None
    bass_only: bool = False
    bass_held: bool = False
    # True when this step's chord is a new attack here rather than a shape still
    # ringing. `slot_plan._chord_attacks` decides it once per slot.
    chord_attack: bool = False
    # True when the guitar sounds this step's melody: False on a comping step
    # where the horn has the tune. Defaulted to True so an ordinary melody step
    # is unaffected.
    melody_voiced: bool = True
    # Why this step sounds nothing, one of the SILENCE_* constants. Set by the
    # route that declines to play; None when the step sounds.
    silence: Optional[str] = None
    # The pitch class of a bass note the left hand could not place, or None when
    # every thumb note the arrangement asked for sounded. Set by `bass_merge`.
    bass_refused: Optional[str] = None
    # True when a chord attack here ends the tune's tie, so the note is not
    # sounding rather than held. Nothing restrikes it - `comp_line_route`
    # keeps the chord below the tune's register. Set by the comping route.
    #
    # Last in the dataclass rather than beside `melody_voiced`: a field added in the
    # middle shifts every positional construction of a step, which is a silent
    # mis-bind rather than a type error.
    melody_released: bool = False

    @property
    def grip(self) -> str:
        return self.voicing.grip

    @property
    def bass(self) -> Optional[int]:
        return self.voicing.bass_midi

    @property
    def has_timing(self) -> bool:
        return self.bar is not None and self.beat is not None

    def tab_line(self) -> str:
        """Returns the one-line tab for this step, e.g. 'x-x-12-13-13-13'."""
        return self.voicing.tab_string()

    def tab_block(self) -> List[str]:
        """Returns the six-line vertical tab for this step's voicing."""
        return self.voicing.tab_block()

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


def cells_from_frets(frets: List[int]) -> List[str]:
    """Renders each fret as a one-character tab cell, muted strings as 'x'.

    A string that is sounding but not being struck is handled by the caller
    (_step_cells), which mutes it; this function renders a literal voicing.
    """
    return [MUTED_CELL if fret < 0 else str(fret) for fret in frets]


def _tab_block_from_cells(cells: List[str]) -> List[str]:
    """Lays six one-character cells out as a six-line vertical tab block."""
    padded = [cell.rjust(2) for cell in cells]
    lines = []
    for string_index in range(len(cells) - 1, -1, -1):
        name = "e" if string_index == 5 else STRING_NAMES[string_index]
        lines.append(f"{name}|{padded[string_index]}-|")
    return lines
