"""ASCII whole-progression staff renderer.

`format_tab_staff` lays a whole progression along a single six-line staff in
reading order, with barlines closing every measure. It shares the column grid
with `tabstaff_html` through `tabstaff_grid`, so both place a chord in the same
column by construction and cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from arranger.step_types import MUTED_CELL, STAFF_CELL_WIDTH, ArrangementStep
from tabstaff_grid import (
    _carries_melody,
    _draws,
    _first_bar_content_end,
    _is_timed,
    _marker_columns,
    _meter_label,
    _staff_barlines,
    _staff_bars,
    _staff_breaks,
    _staff_columns,
    _staff_lines,
    _staff_rhythm,
    _validate_staff_arguments,
)
from tuning import STRING_NAMES

#: The rhythmic grid a whole note is divided into when drawing a staff.
#:
#: **Eight slots to the whole note - an eighth-note grid - is the floor**, and a bar
#: of a quarter rest and three quarter notes is what sets it: four notes on an
#: eighth-note grid, so no finer grid would make that bar any longer.
#: `docs/renderers.md` holds the measurement against `jon6.tab`.
#:
#: The floor only rises for music finer than an eighth - `_slots_per_whole` scales it
#: up so the shortest note in the progression still occupies at least one slot. A
#: grid coarser than that would round two different notes to the same width and lose
#: the difference, which is the one thing the width is there to keep.
_SLOTS_PER_WHOLE = 8


def _slots_per_whole(steps: List[ArrangementStep]) -> int:
    """
    The rhythmic grid for a whole note: `_SLOTS_PER_WHOLE`, or finer if needed.

    Scales up only when some note is shorter than half a slot at the floor, so that
    the shortest note in the progression never rounds away to nothing. Half a slot
    rather than a whole one, because a note that rounds *down* to zero width is
    invisible while one that rounds down to half is still a slot wide.
    """
    shortest = min(
        (step.duration for step in steps if step.duration), default=None
    )
    if shortest is None or shortest <= 0:
        return _SLOTS_PER_WHOLE
    return max(_SLOTS_PER_WHOLE, int(-(-0.5 // shortest)))


def _slot_counts(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
    beat_type: int,
    slots_per_whole: int,
    pickup_end: Optional[float] = None,
) -> List[int]:
    """
    How many grid slots each column occupies - the whole of the duration fix.

    **A column's width is what the note is worth.** A quarter and a half note must be
    drawn differently, or the tab says nothing about how long anything sounded. The
    ASCII tab conveys duration by *width*: a note two beats long is drawn
    across two slots, and the dashes between are the sound continuing.

    Three things this has to get right:

    - **The units are whole notes.** `ArrangementStep.duration` is in whole notes
      (`tuning.py`), so a quarter note (`duration=0.25`) is four grid slots wide.
      Multiplying it by a slot count as though it were in
      beats would make it one slot wide and draw every bar in the piece at the same
      width.
    - **A beat is not a slot-count either.** The grid is per *whole note*, so a bar in
      4/4 and a bar in 2/2 are both sixteen sixteenths and both sixteen slots at a
      finer grid; `beat_type` reaches this as the conversion from beats to whole notes
      rather than as a scale factor.
    - **Holds and rests get their real span.** They were pinned to one slot, which is
      what made a pickup's leading rest too short to see and left a half-note hold as
      narrow as a sixteenth. The rule is the one `_staff_rhythm` already uses: a column
      runs to the next *sounding* column, capped at its own barline.
    """
    bar_in_whole = beats_per_bar / float(beat_type)
    first_bar = int(columns[0][0] // beats_per_bar) if columns else 0
    counts: List[int] = []
    for index, (onset, _step, _strikes) in enumerate(columns):
        bar_end = (int(onset // beats_per_bar) + 1) * beats_per_bar
        if pickup_end is not None and int(onset // beats_per_bar) == first_bar:
            # **An anacrusis stops where its music stops.** The first bar's columns
            # are capped at the pickup's content end rather than at the bar line, so
            # a one-beat pickup is drawn one beat wide instead of filling the bar.
            bar_end = min(bar_end, pickup_end)
        # The next column is where this one stops being drawn. A held column has a
        # step of its own and counts as sounding, so its sound reaches the next
        # *sounding* column and the attack plus its holds add up to the note's real
        # length. A rest column has no step and no sound: it occupies only its own
        # slice - the gap to the next column (one grain). Reaching out to the next
        # attack would make an empty bar as wide as the silence to the next chord,
        # sometimes many bars wide.
        if _step is None:
            following = columns[index + 1][0] if index + 1 < len(columns) else bar_end
        else:
            following = next(
                (later for later in range(index + 1, len(columns))
                 if columns[later][1] is not None),
                None,
            )
            following = columns[following][0] if following is not None else bar_end
        span = following - onset
        span = min(span, bar_end - onset, bar_in_whole)
        whole = span / float(beat_type)  # a beat is `1 / beat_type` of a whole note
        counts.append(max(1, int(round(whole * slots_per_whole))))
    return counts


def _melody_label(step: Optional[ArrangementStep]) -> str:
    """The melody row's cell for one step: the note's name, or blank once it is released.

    The row labels every step, because the tune moves on while the shape underneath is
    held - which is exactly why the one cell it must not label is a note a **chord attack
    ended**. That note is not sounding, and its name on the row would claim the tune is
    still in. `annotation._comping_tail` says which note the stab took.
    """
    if step is None or step.melody_released:
        return ""
    return step.melody or ""

def _mark_pickup_barline(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    bars: List[int],
    barline_token: Dict[int, str],
    beats_per_bar: int,
    beat_type: int,
    first_bar_implicit: Optional[bool] = None,
) -> Optional[float]:
    """Mark the anacrusis's end, and return the content end it was found at.

    A short first bar is a pickup, and the thin double bar line closes it where the
    music stops - the same `light-light` the MusicXML writer puts there. A repeat
    sign already on that bar line wins, because `|:` carries play order and the
    double bar line is only a structural divider.

    A source that states a **whole** first bar (`first_bar_implicit=False`) is not a
    pickup however short its music is, so nothing is marked and `None` is returned:
    the bar is drawn full width and closed by an ordinary bar line.
    """
    pickup_end = (
        None
        if first_bar_implicit is False
        else _first_bar_content_end(
            [(onset, step) for onset, step, _strikes in columns],
            beats_per_bar,
            beat_type,
        )
    )
    if pickup_end is not None:
        for index, bar in enumerate(bars):
            if bar != bars[0]:
                barline_token.setdefault(index, "||")
                break
    return pickup_end


@dataclass(frozen=True)
class _StaffGrid:
    """The rules a row of the staff is drawn by, as one value.

    The row builders are methods here, so each takes the system it draws. What they
    read is what the value carries: the laid-out columns, the grid's own width rules,
    the barlines, and the flags that decide which rows exist.
    """

    steps: List[ArrangementStep]
    columns: List[Tuple[float, Optional[ArrangementStep], bool]]
    slots: List[int]
    values: List[Tuple[str, str]]
    bar_marks: set
    barline_token: Dict[int, str]
    label_at: Dict[int, str]
    beats_per_bar: int
    beat_type: int
    show_chords: bool
    show_melody: bool
    show_melody_string: bool
    show_mutes: bool
    show_timing: bool

    def cell(
        self,
        step: Optional[ArrangementStep],
        string_index: int,
        strikes: bool,
        previous: Optional[ArrangementStep] = None,
    ) -> str:
        """One fret cell: a fret number or a mute marker, or empty for a held voice.

        `previous` is the step before this one, which is what says whether a **held**
        column's thumb has moved - see `_moved_thumb`.
        """
        if step is None or not _draws(step, previous, string_index, strikes):
            return ""
        fret = step.voicing.frets[string_index]
        if fret < 0:
            return MUTED_CELL if (self.show_mutes or step.melody_only) else ""
        return str(fret)

    def system_width(self, system: List[int]) -> int:
        """
        The cell width for one system: the widest label among **its own** columns.

        Every row of a system shares one column width, and the grid widens to the
        longest label rather than letting the chord line push itself out of step with
        the frets underneath it. The metre and the note values go through the same
        calculation: a `4/4` or a `0.67q` fallback is wider than a fret, and
        truncating either would print a note value that is not the one being played.

        **Only labels that are actually drawn count.** The chord name counts under
        `show_chords` and the melody note under `show_melody`, because a label that is
        not printed cannot knock the grid out of alignment - and counting one anyway
        makes turning that row off print a tab *wider* than leaving it on, which is
        the opposite of what the flag says.

        **Per system, not per progression.** Computing it once over every column would
        let a single two-digit fret anywhere in the piece set the width for the whole
        arrangement, so a bar of nothing but single-digit frets would be drawn two
        characters per cell because some other bar held a `13`. TuxGuitar's export sizes
        its bars independently. Per system is the finest granularity that keeps the
        invariant the alignment tests exist to protect, since two bars drawn on one
        system have to share a grid or a fret stops lining up across the six strings.
        Per *bar* would match the export more closely and would break it.
        """
        width = STAFF_CELL_WIDTH
        for index in system:
            step = self.columns[index][1]
            label = self.label_at.get(index)
            if label:
                # A volta's `1.` and a `D.C.` are labels like any other and must not
                # knock the grid out of alignment - the same rule the chord and melody
                # rows obey.
                width = max(width, len(label))
            if step is None:
                continue
            if self.show_chords:
                width = max(width, len(step.chord))
            if self.show_melody:
                width = max(width, len(step.melody or ""))
        if self.show_timing:
            width = max(width, len(_meter_label(self.beats_per_bar, self.beat_type)))
            for label, _kind in self.values:
                if label:
                    width = max(width, len(label))
        return width

    def meter_cells(self, count: int) -> List[str]:
        """The metre in the first column and nothing elsewhere.

        A time signature is written once, at the head of the staff, and the
        signature holds until it changes - so printing it over every bar would say
        something the score does not. That is the same decision `tabxml` makes when
        it writes `<time>` in the first measure only, and for the same reason: a
        signature over every bar reads as a new one at each, and the bar stops
        reading as a continuation of the one before.
        """
        return [_meter_label(self.beats_per_bar, self.beat_type)] + [""] * (count - 1)

    def string_line(self, width: int, system: List[int], string_index: int) -> str:
        """One string's row: its label, its barlines, and its fret cells in dashes."""
        lead = (
            "*" if self.show_melody_string
            and _carries_melody(self.steps, string_index)
            else " "
        )
        out = [lead, self.barline_token.get(system[0], "|")]
        # The lead-in dash, for the reason given in `line`. On a string row it is a
        # real dash rather than the space used there, because here the character is
        # part of the string's own drawn line.
        out.append("-")
        for position, index in enumerate(system):
            # The `position` guard for the reason given in `line`: this row has
            # already written its own opening barline.
            if index in self.bar_marks and position:
                # A barline inside the line is followed by its own lead-in, exactly as
                # the opening one is. Without it the first fret of the second bar sat
                # hard against the `|`, where TuxGuitar - and the opening bar, and
                # every other bar - all have a dash between the two.
                out.append(self.barline_token.get(index, "|") + "-")
            # **The fill is a dash, not a space** - and this is the whole reason the
            # staff reads as tab rather than as a chord list. A string is one
            # continuous line running the length of the system, with the fret numbers
            # sitting *in* it. Left blank, the six lines were six scattered numbers
            # and the reader had to infer the strings from the labels alone.
            #
            # The cell spans **its own slots**, for the reason given in `line`: one
            # slot is one fret cell, so a note two slots long is drawn two cells wide
            # and the dashes after the fret are the note sounding on.
            _, step, strikes = self.columns[index]
            previous = self.columns[index - 1][1] if index else None
            out.append(
                self.cell(step, string_index, strikes, previous).ljust(
                    width * self.slots[index], "-"
                )
            )
        out.append("|")
        # The highest string is labelled with a lowercase 'e', the usual tab
        # convention, so the top and bottom lines of the staff stay distinct.
        name = "e" if string_index == 5 else STRING_NAMES[string_index]
        return f"{name}{''.join(out)}"


    def line(self, width: int, system: List[int], text_for: Any,
             when_struck: bool, dedupe: bool = False,
             cells: Optional[Sequence[str]] = None,
             in_force: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Renders a chord, melody, metre or rhythm row for one system of music.

        `width` is `self.system_width(system)` and is passed rather than recomputed,
        because it is a property of the system and every row of that system must use
        the same one. `system` is the column indexes of this system alone, not the
        whole progression: a staff that wraps draws each system separately, and a row
        built from the whole column list would run the full width of the progression
        while the strings beneath it ran the width of one line - the misalignment the
        alignment tests exist to catch.

        `when_struck` is False for the melody line, which must label every step:
        the melody moves on even while the shape underneath it is being held.
        `dedupe` prints a label only where it changes from the previous one, which
        is how a lead sheet spells a chord held across several slots. The chord in
        force is threaded in and out so a chord held across a *system break* is
        named once - the same rule the HTML page follows, for the same reason.

        `cells` supplies the text **by column index** instead of from the step, and
        that is what the metre and rhythm rows need: a held column has a step but no
        note of its own, and a rest column has neither a step nor anything to
        derive a value from. Routing both through this one function is what keeps
        the two rows ruled identically to the string rows - the alignment
        `TestStaffBarlineAlignment` asserts, which would otherwise only hold for the
        rows that existed when it was written.

        **These rows are not dash-filled.** A `-` between columns is the string's
        *own* line, running through the fret numbers; a chord name or a note value is
        text sitting above the staff, and ruling it would draw a line through the
        words. So the separator is a space here and a dash on the string rows - and
        both are exactly one character, which is what keeps the columns of the two
        kinds of row aligned.
        """
        # Two spaces then a barline, which is the same three-character offset the
        # string lines use (string label, melody marker, '|'), so a chord name
        # starts in the column of its own frets and every row is ruled identically.
        # The closing barline matters as much as the leading one: without it these
        # rows stop short of the string rows and the staff reads as unaligned.
        out = ["  " + self.barline_token.get(system[0], "|")]
        previous = in_force
        # **One separator after every barline, including this row's own opening one.**
        # TuxGuitar writes a dash between the barline and the first fret of the bar and
        # never a fret hard against the `|`, so no beat-1 fret reads as glued to the
        # barline it follows. Here it is a space, because these rows are text and
        # unruled; the string rows put a `-` in the same column, and both being exactly
        # one character wide is what keeps the two kinds of row aligned.
        # `docs/renderers.md` records the check against `jon6.tab`.
        #
        # It is written unconditionally because the row's own opening barline needs it
        # as much as any other, and the loop below already suppresses the *barline*
        # itself for position 0 - so without this, the first column of every system
        # would sit hard against the `|` while every later column had a separator.
        out.append(" ")
        for position, index in enumerate(system):
            # `position`, not `index`: the row has just written its own opening
            # barline, so the first column of a system must not write a second.
            # Every system begins on a barline, so this is not a rare case - without
            # it every line after the first opened with a doubled `||`.
            if index in self.bar_marks and position:
                # The barline's own lead-in, for the reason given above: every
                # barline is followed by a separator, not only the opening one.
                out.append(self.barline_token.get(index, "|") + " ")
            if cells is not None:
                text = cells[index] if index < len(cells) else ""
            else:
                _, step, strikes = self.columns[index]
                text = text_for(step) if (strikes or not when_struck) else ""
            if dedupe and text and text == previous:
                text = ""
            if text:
                previous = text
            # **The cell spans its own slots, and there is no separate separator.**
            # One slot is one fret cell wide, so a note two slots long is drawn two
            # cells wide and the whole line is the same width whatever it contains.
            # That is what puts our bars where TuxGuitar's are: seventeen characters
            # for a bar of a quarter rest and three quarter notes.
            out.append(text.ljust(width * self.slots[index]))
        # No rstrip here. The chord and melody rows share their column grid with the
        # string rows, so a trailing blank column has to stay blank rather than be
        # trimmed: trimming shortens the row and leaves its closing barline short of
        # the string rows'. The closing '|' is what makes the trailing spaces read as
        # an empty bar rather than as ragged text.
        return "".join(out) + "|", previous


def format_tab_staff(
    steps: List[ArrangementStep],
    beats_per_bar: int = 4,
    beat_type: int = 4,
    rhythm: bool = True,
    show_chords: bool = False,
    show_melody: bool = False,
    show_melody_string: bool = True,
    show_mutes: bool = False,
    collapse: bool = True,
    measures_per_line: int = 4,
    show_timing: bool = False,
    markers: Sequence[Any] = (),
    first_bar_implicit: Optional[bool] = None,
) -> str:
    """
    Renders a whole progression as a standard six-line guitar staff.

    format_progression() gives one block *per chord*, its explanation wrapped onto the
    lines below the step when it is too long for one. This
    instead lays every step along a single staff in reading order - high E on top
    down to low E - which is how printed tab is read, with a barline closing every
    measure.

    **The default output is the tab and nothing else**: six string rows, the fret
    numbers sitting in a drawn line of dashes, and the barlines. No chord names, no
    melody note names, no metre and no note values. That is what a tab file *is*, and
    it is what TuxGuitar's, Guitar Pro's and every other ASCII export produce - a
    thing you drop into a file and read, not a score with annotation. The chord row
    was on by default until this was changed, and it was the wrong default: a reader
    who wants the harmony can read it off the arrangement, and one who wants it on
    the page asked for it. Pass `show_chords` for it.

    Fret cells are a fixed width and the number sits at the left of its column,
    which is how tab is written and what keeps a chord name aligned with the fret
    it belongs to. The width is at least two characters, so a two-digit fret never
    runs into its neighbour. An unsounded string is left blank by default:
    in chord-melody a voice that is still ringing is not restruck, and marking
    it `x` on every chord would be noise. Pass `show_mutes` to spell them out. A
    melody-only (no chord) step always shows its `x`s, because there the other
    strings really are silent.

    `show_timing` adds two rows above the chord names: the **metre** (`4/4`) over the
    first bar, and a **rhythm** row naming the note value in every column - `w` for
    a whole note, `~` for a shape still held from an earlier column, `r` for a rest.
    With them the grid shows not only *where* a chord falls but *how long it sounds*,
    since a whole note and a quarter are drawn identically without them. They are
    **off by default** now, for the same reason the chord row is: they are a score's
    annotation, not the tab. `beat_type` is what the metre needs when they are on: a
    2/2 beat is a half note, so 2/2 reads `h` where 4/4 reads `q` on the same grid.

    Args:
        steps: arranged steps, typically from arrange_progression().
        beats_per_bar: beats in a bar, used to place the barlines.
        beat_type: the denominator of that metre. Pass the notated value, so a head
            in cut time reads `2/2` rather than being restated as `2/4`, and its
            beat is a half note rather than a quarter. The bar length is identical
            either way; only the displayed metre and the note values differ.
        rhythm: space the steps on their real beats. This needs every step to
            carry `bar` and `beat`; if any does not, the uniform grid is used, so
            a hand-written progression still renders sensibly.
        show_chords: draw the chord-name line above the staff. Off by default: the tab
            is the six string rows, and a chord name is a lead sheet's annotation.
        show_melody: draw the melody-note line. Off by default, as above.
        show_melody_string: mark the string carrying the melody with a `*`.
        show_mutes: print `x` on every unsounded string.
        collapse: strike a shape once and let it ring while the melody moves over the
            same pitches, instead of restriking it on every step. This is the
            default, and it is what makes a held chord read as a held chord.
        measures_per_line: bars per printed line of music; the staff wraps there and
            the last line may be shorter. Every bar is ruled regardless - this
            governs only where a line *ends*, not where the barlines fall.
        show_timing: draw the metre and the note-value rows above the chord names.
            Off by default along with them: they say how long each chord sounds,
            which a score needs and a tab file does not carry. Pass `True` for a
            staff that reads as a score rather than as tab.
        first_bar_implicit: what the source said about the first bar, or `None` when
            nothing did. `False` is a **whole** first bar - its silence is filled with
            rests and it is closed by an ordinary bar line; `True` and `None` both let a
            short first bar be drawn as a pickup and closed with `||`. Measured from the
            onsets on `None` because a progression with no score behind it has nothing
            else to go on.

    Returns:
        The rendered staff as a newline-joined string, or "" for no steps. Pure:
        nothing is printed, so the caller stays in control of the output.

    Raises:
        ValueError: if `beats_per_bar` or `beat_type` is below 1, or
            `measures_per_line` is below 1.
    """
    _validate_staff_arguments(beats_per_bar, beat_type, measures_per_line)
    if not steps:
        return ""

    columns = _staff_columns(
        steps, beats_per_bar, beat_type, rhythm, collapse, first_bar_implicit
    )
    bars = _staff_bars(columns, beats_per_bar)
    # Two different sets, deliberately: `bar_marks` is every bar (where the metre
    # falls) and `breaks` is every `measures_per_line` bars (where the line wraps).
    bar_marks = _staff_barlines(bars)
    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)

    # Repeat, ending and navigation signs, keyed by the column the bar they belong to
    # opens at - see `_marker_columns`.
    barline_token, label_at = _marker_columns(bars, markers)
    # A short first bar is a pickup; the helper closes it where its music stops.
    pickup_end = _mark_pickup_barline(
        columns, bars, barline_token, beats_per_bar, beat_type, first_bar_implicit
    )

    # The rhythm row and the column grid go through one predicate, so the row can
    # never claim a written rhythm the columns were not laid out by.
    timed = _is_timed(steps, rhythm)
    values = _staff_rhythm(columns, beats_per_bar, beat_type, timed)
    # How wide each column is drawn, so a note's duration shows as horizontal space.
    # **Only for a timed progression**: an untimed one is laid out one chord per beat
    # and has no durations to show, so every column stays one slot wide and the output
    # is the plain uniform grid it has always been.
    slots = (
        _slot_counts(
            columns, beats_per_bar, beat_type, _slots_per_whole(steps),
            pickup_end=pickup_end,
        )
        if timed else [1] * len(columns)
    )

    grid = _StaffGrid(
        steps=steps,
        columns=columns,
        slots=slots,
        values=values,
        bar_marks=bar_marks,
        barline_token=barline_token,
        label_at=label_at,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        show_chords=show_chords,
        show_melody=show_melody,
        show_melody_string=show_melody_string,
        show_mutes=show_mutes,
        show_timing=show_timing,
    )

    lines: List[str] = []
    # The chord in force, threaded across systems so a chord held over a system
    # break is named once - the rule `_html_chord_row` already follows for the page.
    in_force: Optional[str] = None
    labels = [label for label, _kind in values]
    # The label row, by global column index: a volta's number and a navigation sign
    # over the bar they begin at, blank elsewhere. Routed through `line` like the metre
    # and rhythm rows, so it is ruled identically and cannot drift from the grid.
    label_cells = [label_at.get(index, "") for index in range(len(columns))]
    for position, system in enumerate(_staff_lines(columns, breaks, beats_per_bar)):
        if position:
            # A blank line between systems. Without it two systems run together and
            # the reader cannot tell where one printed line ends and the next begins,
            # which is the only cue the wrapping itself provides.
            lines.append("")
        # One width for every row of this system. See `system_width` - per system,
        # because two bars drawn on one line have to share a grid or a fret stops
        # lining up across the six strings.
        width = grid.system_width(system)
        if label_at:
            # The volta numbers and the navigation signs, over the bars they belong to,
            # where a printed score puts them. Above everything else so the row reads as
            # a label on the form rather than on a chord.
            lines.append(grid.line(
                width, system, lambda step: "", when_struck=True, cells=label_cells,
            )[0])
        if show_timing:
            # The metre goes in the first column of the *first* system, over the bar it
            # governs, which is where a printed score puts a time signature - and not
            # again on the next system, because a signature holds until it changes.
            lines.append(grid.line(
                width, system, lambda step: "", when_struck=True,
                # The cells are addressed by global column index, so the metre row is
                # blank on every column but the very first of the first system.
                cells=(
                    grid.meter_cells(len(system)) if position == 0
                    else [""] * len(system)
                ),
            )[0])
            # The rhythm row is dropped when there is no rhythm to state. An untimed
            # progression is one chord per beat, so every cell would be the same letter
            # and the row would be a blank line that looks like a missing one.
            if values:
                lines.append(grid.line(
                    width, system, lambda step: "", when_struck=True, cells=labels,
                )[0])
        if show_chords:
            row, in_force = grid.line(
                width, system, lambda step: step.chord if step else "",
                when_struck=True, dedupe=True, in_force=in_force,
            )
            lines.append(row)
        if show_melody:
            lines.append(grid.line(
                width, system, _melody_label,
                when_struck=False,
            )[0])
        lines.extend(grid.string_line(width, system, index) for index in range(5, -1, -1))
    return "\n".join(lines).rstrip()


