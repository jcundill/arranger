"""Whole-progression tab renderers: the six-line ASCII staff and the HTML page.

These are the two renderers that lay an arrangement out **along one staff in
reading order**, rather than one block per chord as `format_progression()` does:

- `format_tab_staff` - the ASCII staff, for a terminal.
- `format_tab_html` / `write_tab_html` - a self-contained HTML page for a browser.

They live together because they share `_staff_columns`, which places each step on
an absolute beat and decides what is a strike and what is a hold. That sharing is
the point: both renderings place a chord in the same column *by construction* and
cannot drift apart, which is what the two grids have to agree on for the `collapse`
behaviour to mean the same thing in each.

Split out of `arranger.py` so the renderers can grow without making the voicing
engine harder to read. Everything here imports from `arranger`, never the reverse,
except for the public re-exports at the bottom - see the note there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Sequence, Tuple

from arranger import STRING_NAMES, ArrangementStep, _MUTED_CELL

# The width every fret cell is padded to. Two characters covers frets 0-18, the
# whole range the library allows, and matches the convention `Voicing.tab_block()`
# uses, so the vertical block and the staff put a fret in the same column.
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
        # A repeated melody still strikes: the soprano is re-articulated even when the
        # shape underneath is the one already ringing, so the note is heard again. The
        # renderers show the soprano alone and blank the held inner voices.
        strikes = pitches != held or step.repeated
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
        # A repeated melody is a single note: the soprano alone is struck, and the
        # other strings are simply not played. They stay blank rather than 'x',
        # because the player is not muting them.
        if step.repeated and string_index != step.voicing.soprano_string():
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
        # Two spaces then a barline, which is the same three-character offset the
        # string lines use (string label, melody marker, '|'), so a chord name
        # starts in the column of its own frets and every row is ruled identically.
        # The closing barline matters as much as the leading one: without it these
        # rows stop short of the string rows and the staff reads as unaligned.
        out = ["  |"]
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
        # No rstrip here. The chord and melody rows share their column grid with the
        # string rows, so a trailing blank column has to stay blank rather than be
        # trimmed: trimming shortens the row and leaves its closing barline short of
        # the string rows'. The closing '|' is what makes the trailing spaces read as
        # an empty bar rather than as ragged text.
        return "".join(out) + "|"

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
# format_tab_staff above is ASCII, because that is what goes in a terminal. A browser
# can do better: a table gives every column its own box, so fret numbers, chord names
# and barlines align by construction rather than by counting characters, and the
# page can be styled, reflowed and printed. The output is one self-contained file -
# the stylesheet is inlined - so it can be emailed or opened from disk.
#
# Everything here reuses _staff_columns and _staff_breaks, so the two renderings
# place a chord in the same column by construction and cannot drift.

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
# Marks every cell of a repeated-melody column. Those cells are otherwise empty, so
# without this a repeated note reads as a gap in the music rather than as a deliberate
# single note.
_CLASS_REPEAT = "repeat"

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
/* A repeated melody is played as a single note: the other strings are left empty and
   the column is tinted, so it reads as a deliberate single note rather than as a gap
   in the music. */
td.repeat { background: var(--strike); border-radius: 2px; }
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


def _html_cell(text: str = "", class_name: str = "", tag: str = "td") -> str:
    """
    One table cell, with its class attribute only when there is a class to give it.

    An empty `class_name` omits the attribute entirely, so a plain cell stays
    `<td>3</td>` rather than becoming `<td class="">3</td>`. The row builders below
    use this instead of assembling tags inline, which is what made the repeat
    marking a nested conditional: deciding the class and emitting the cell are the
    same decision, so they belong in one call.

    `tag` is "th" only for the leading label cell, which has to be a header for
    the string rows to line their labels up and to keep the chord and melody rows
    in the same columns as the frets beneath them.
    """
    attribute = f' class="{class_name}"' if class_name else ""
    return f"<{tag}{attribute}>{text}</{tag}>"


def _html_row(class_name: str, cells: Sequence[str]) -> str:
    """One table row, from cells that are already built by `_html_cell`."""
    return f'<tr class="{class_name}">{"".join(cells)}</tr>'


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
    cells: List[str] = [_html_cell(tag="th")]
    for index in measure:
        _, step, strikes = columns[index]
        # A name is printed only where the chord changes and only on a strike; every
        # other column is left empty so a held chord is not spelled out again.
        if step is None or not strikes or step.chord == previous:
            cells.append(_html_cell())
            continue
        cells.append(_html_cell(_escape(step.chord)))
        previous = step.chord
    return _html_row(_CLASS_CHORD, cells), previous


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
    cells = [_html_cell(tag="th")]
    for index in measure:
        # An empty cell is one with no step on it; pyright cannot see that the
        # conditional already guards it, so the binding is named explicitly.
        step = columns[index][1]
        cells.append(_html_cell(_escape(step.melody) if step else ""))
    return _html_row(_CLASS_MELODY, cells)


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
    is_soprano = string_index in sopranos
    cells = [
        _html_cell(
            "*" if is_soprano else "", _CLASS_SOPRANO if is_soprano else "",
            tag="th",
        )
    ]
    for index in measure:
        _, step, strikes = columns[index]
        if step is None or not strikes:
            cells.append(_html_cell())
            continue
        # A repeated melody is a single note, so the other strings are not played at
        # all and their cells stay empty, while the struck one is still marked. The
        # whole column is tinted by that single class either way, which is what keeps
        # a repeated note visible as such rather than looking like a gap.
        if step.repeated and string_index != step.voicing.soprano_string():
            cells.append(_html_cell(class_name=_CLASS_REPEAT))
            continue
        fret = step.voicing.frets[string_index]
        if fret < 0:
            cells.append(
                _html_cell("x", _CLASS_MUTE)
                if (show_mutes or step.melody_only)
                else _html_cell()
            )
        else:
            cells.append(
                _html_cell(str(fret), _CLASS_REPEAT if step.repeated else "")
            )
    return _html_row(_CLASS_STRING, cells)


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


# The renderers are re-exported from `arranger` rather than imported at its top, so
# that `from arranger import format_tab_html` - the spelling in the README, the
# tests and `wjazzd` - keeps working. A plain top-level `from tabstaff import ...`
# in `arranger` would be a genuine import cycle: importing `tabstaff` first would
# re-enter a half-initialised `arranger` and fail to find these names. The lazy
# `__getattr__` in `arranger` breaks it without a lazy import at every call site.
# The MusicXML renderer lives in `tabxml`, which imports this module. Re-exporting it
# here is what keeps one spelling for the whole staff-rendering surface - `from
# arranger import format_musicxml` - and the re-export is lazy for the same reason
# and with the same cycle: `tabxml` imports `tabstaff`, so a top-level import here
# would re-enter a half-initialised `tabxml`.
_TABXML_EXPORTS = ("format_musicxml", "write_musicxml")

if TYPE_CHECKING:
    # The names are resolved by `__getattr__` below, which a static checker cannot
    # follow - so without this it would report them as absent from the module and
    # flag the `__all__` entries. The same trick `arranger` uses for these names.
    from tabxml import format_musicxml, write_musicxml

# The five names a star-import of this module must carry. Spelled out as one literal
# rather than `+=`, which a static checker cannot follow.
__all__ = [
    "format_tab_staff",
    "format_tab_html",
    "write_tab_html",
    "format_musicxml",
    "write_musicxml",
]


def __getattr__(name: str) -> Any:
    """Resolves the `tabxml` renderers on first access. See _TABXML_EXPORTS."""
    if name in _TABXML_EXPORTS:
        import tabxml

        return getattr(tabxml, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

