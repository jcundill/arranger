"""HTML whole-progression staff renderer.

`format_tab_html` renders a whole progression as a self-contained HTML page with
an inlined stylesheet. It shares the column grid with `tabstaff_ascii` through
`tabstaff_grid`, so both renderers place a chord in the same column by
construction and cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from arranger.step_types import ArrangementStep
from tabstaff_grid import (
    _NAVIGATION_LABELS,
    _carries_melody,
    _draws,
    _is_timed,
    _melody_label,
    _meter_label,
    _moved_thumb,
    _staff_breaks,
    _staff_columns,
    _staff_lines,
    _staff_rhythm,
    _validate_staff_arguments,
)

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
# Marks every cell of a `bass_only` column, for the same reason `_CLASS_REPEAT`
# exists and it is the mirror image of it: those cells are empty too, and a thumb
# note with a blank column above it has to read as a deliberate held shape rather
# than as silence under a moving bass.
_CLASS_BASS = "bass"
# The written metre, and the note value of every column. Both sit above the chord
# row, where a score puts them, and both are the ASCII staff's `show_timing` rows -
# named here for the same reason as the rest, so a rename cannot half-apply.
_CLASS_METER = "meter"
_CLASS_RHYTHM = "rhythm"
_CLASS_HOLD = "hold"
_CLASS_REST = "rest"
# The repeat and ending marks, so a page shows the structure the importer honoured
# rather than only its effect. `repeat-start` / `repeat-end` thicken the measure's
# left / right rule into a repeat sign, and `volta` is the `1.` / `2.` label above it.
_CLASS_REPEAT_START = "repeat-start"
_CLASS_REPEAT_END = "repeat-end"
_CLASS_VOLTA = "volta"
# A navigation sign (Segno / Coda / Fine / D.C. / D.S.) sits on the opposite side of
# the measure from a volta, so a bar carrying both shows both rather than one covering
# the other.
_CLASS_NAV = "nav"
_CLASS_DIAGRAM = "diagram"

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
.measure { border-left: 1px solid var(--rule); padding: 0 .5rem; position: relative; }
.measure:first-of-type { border-left: 2px solid var(--rule); }
.measure.repeat-start { border-left: 3px double var(--ink); }
.measure.repeat-end { border-right: 3px double var(--ink); }
.volta { position: absolute; top: -.1rem; left: .5rem; font-size: .7rem;
         color: var(--accent); border-top: 1px solid var(--accent);
         padding: 0 .2rem; }
.nav { position: absolute; top: -.1rem; right: .5rem; font-size: .7rem;
       color: var(--accent); }
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
/* The metre and the note values, which are the two rows the ASCII staff draws from
   `show_timing`. They are small and quiet because they are read once and then the
   eye goes to the chords; the metre is a touch stronger since it is the one piece
   of information a reader cannot infer from the tab. */
tr.meter td { font-size: .78rem; font-weight: 600; color: var(--ink);
              padding-bottom: .1rem; }
tr.rhythm td { font-size: .68rem; color: var(--faint); padding-bottom: .25rem;
               font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
/* A tie and a rest both sit in a column with no new attack, and they mean opposite
   things: `~` is the note begun earlier still sounding, `r` is silence. They are
   dimmed rather than blanked so neither reads as a missing cell. */
td.hold, td.rest { color: var(--mute); }
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
/* The mirror image of td.repeat: a bass-only column holds every voice above the thumb
   and moves only the thumb, so its empty cells are tinted for the same reason. */
td.bass { background: var(--strike); border-radius: 2px; }
.notes { margin: 2.5rem 0 0; font-size: .78rem; color: var(--faint); }
.notes li { margin: .2rem 0; }
/* A fretboard chord diagram: six strings (low E left, high E right), four frets,
   dots at fretted positions, `o` above open strings and `x` above muted ones.
   The container is a fixed-size inline-block so it fits inside a table cell
   without disturbing the column grid. */
.fretboard { position: relative; display: inline-block; width: 4.2rem; height: 3.6rem; }
.fretboard-string { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--rule); }
.fretboard-fret { position: absolute; left: 0; right: 0; height: 2px; background: var(--ink); }
.fretboard-nut { height: 3px; background: var(--ink); }
.fretboard-dot { position: absolute; width: 0.7rem; height: 0.7rem; background: var(--ink);
                 border-radius: 50%; transform: translate(-50%, -50%); }
.fretboard-open, .fretboard-muted { position: absolute; top: -0.45rem; font-size: 0.68rem;
                                    transform: translateX(-50%); }
.fretboard-open { color: var(--faint); }
.fretboard-muted { color: var(--mute); }
.fretboard-first { position: absolute; left: -1.45rem; top: 0.15rem; font-size: 0.6rem;
                   color: var(--faint); }
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


def _html_timing_rows(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    values: Sequence[Tuple[str, str]],
    meter: str,
    show_meter: bool,
) -> List[str]:
    """
    The metre and note-value rows for one measure, in that order.

    **The metre appears on the first measure only.** A time signature holds until
    it changes, so writing one over every bar says something the score does not -
    and the same reasoning is why `tabxml` writes `<time>` into the first measure
    alone, since MuseScore draws a repeated signature over every bar and the bar
    stops reading as a continuation of the one before. `show_meter` is the page's
    "is this the first measure" flag.

    The note-value row repeats on every measure, because a rhythm is per-measure
    and a bar of rests is not the same information twice. It is omitted entirely
    when `values` is empty - an untimed progression has no written rhythm to show,
    and an empty row would read as a rendering failure rather than as an absence.

    The cells come from the shared `_staff_rhythm`, which the ASCII staff also
    reads, so the page and the terminal cannot disagree about how long a note is.
    """
    rows: List[str] = []
    if show_meter:
        meter_cells = [_html_cell(tag="th")]
        meter_cells += [
            _html_cell(_escape(meter) if position == 0 else "")
            for position in range(len(measure))
        ]
        rows.append(_html_row(_CLASS_METER, meter_cells))
    if values:
        cells = [_html_cell(tag="th")]
        for index in measure:
            label, kind = values[index] if index < len(values) else ("", "note")
            css = _CLASS_HOLD if kind == "hold" else _CLASS_REST if kind == "rest" else ""
            cells.append(_html_cell(_escape(label), css))
        rows.append(_html_row(_CLASS_RHYTHM, cells))
    return rows


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


def _html_fretboard_diagram(step: ArrangementStep) -> str:
    """One fretboard chord diagram for a step's voicing.

    Six strings (low E left, high E right), four frets, dots at fretted
    positions, `o` above open strings and `x` above muted ones. A `firstFret`
    label appears when the diagram starts above fret 0. Returns an empty
    string for a step with fewer than two sounding strings (a single note,
    an NC, a rest).
    """
    frets = step.voicing.frets
    active = [f for f in frets if f >= 0]
    if len(active) < 2:
        return ""
    first_fret = min(active)
    markers: List[str] = []
    dots: List[str] = []
    for library_index in range(6):
        fret = frets[library_index]
        left = f"{library_index * 20:.0f}%"
        if fret < 0:
            markers.append(
                f'<span class="fretboard-muted" style="left: {left}">x</span>'
            )
        elif fret == 0:
            markers.append(
                f'<span class="fretboard-open" style="left: {left}">o</span>'
            )
        else:
            top = f"{(fret - first_fret) * 25:.0f}%"
            dots.append(
                f'<span class="fretboard-dot" style="left: {left}; top: {top}"></span>'
            )
    strings = "".join(
        f'<span class="fretboard-string" style="left: {i * 20:.0f}%"></span>'
        for i in range(6)
    )
    frets_html = '<span class="fretboard-fret fretboard-nut"></span>'
    if first_fret > 0:
        frets_html = "".join(
            f'<span class="fretboard-fret" style="top: {i * 25:.0f}%"></span>'
            for i in range(4)
        )
    else:
        frets_html = (
            '<span class="fretboard-fret fretboard-nut"></span>'
            + "".join(
                f'<span class="fretboard-fret" style="top: {(i + 1) * 25:.0f}%"></span>'
                for i in range(3)
            )
        )
    first_label = (
        f'<span class="fretboard-first">{first_fret}fr</span>'
        if first_fret > 0
        else ""
    )
    return (
        '<span class="fretboard">'
        + first_label
        + strings
        + frets_html
        + "".join(markers)
        + "".join(dots)
        + "</span>"
    )


def _html_diagram_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    previous: Optional[str],
) -> Tuple[str, Optional[str]]:
    """One row of fretboard diagrams for a measure, plus the chord in force.

    A diagram is drawn only where the chord changes and the step is struck,
    matching the chord row's dedupe rule: a held chord gets no new diagram.
    """
    cells: List[str] = [_html_cell(tag="th")]
    for index in measure:
        _, step, strikes = columns[index]
        # A diagram is drawn only where the chord changes and only on a
        # struck chord; every other column is left empty.
        if step is None or not strikes or step.chord == previous:
            cells.append(_html_cell())
            continue
        cells.append(_html_cell(_html_fretboard_diagram(step)))
        previous = step.chord
    return _html_row(_CLASS_DIAGRAM, cells), previous


def _html_melody_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
) -> str:
    """
    One row of melody note names.

    Labelled on every step, not only on a strike: the melody moves on even while
    the shape underneath it is being held, so the held columns are exactly where a
    note name is most useful - and a note a chord attack ended is the one blank cell,
    because there the tune is no longer sounding (`_melody_label`).
    """
    cells = [_html_cell(tag="th")]
    for index in measure:
        cells.append(_html_cell(_escape(_melody_label(columns[index][1]))))
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
        # The step before this column, which is what says whether a **held** column's
        # thumb has moved (`_moved_thumb`)
        previous = columns[index - 1][1] if index else None
        cells.append(_html_fret_cell(step, previous, string_index, strikes, show_mutes))
    return _html_row(_CLASS_STRING, cells)


def _html_fret_cell(
    step: Optional[ArrangementStep],
    previous: Optional[ArrangementStep],
    string_index: int,
    strikes: bool,
    show_mutes: bool,
) -> str:
    """One fret cell of the HTML staff: its text, and the tint of its column.

    A `repeated`, a `bass_only` column and a **held column whose thumb has moved** each
    sound only some of their strings - the last because the shape is held while the bass
    attacks - and the whole column is tinted by one class so it reads as deliberate
    rather than as a gap in the music. Which strings of it sound is `_draws`'s answer,
    the same one the ASCII cell asks, so the two renderings cannot disagree.
    """
    partial = step is not None and _partial_column(step, previous)
    if step is None or not _draws(step, previous, string_index, strikes):
        return _html_cell(class_name=_tint(step, partial))
    fret = step.voicing.frets[string_index]
    if fret < 0:
        if show_mutes or step.melody_only:
            return _html_cell("x", _CLASS_MUTE)
        return _html_cell(class_name=_tint(step, partial))
    return _html_cell(str(fret), _tint(step, partial))


def _partial_column(
    step: ArrangementStep, previous: Optional[ArrangementStep]
) -> bool:
    """Whether this column sounds only some of its strings."""
    return step.repeated or step.bass_only or _moved_thumb(step, previous)


def _tint(step: Optional[ArrangementStep], partial: bool) -> str:
    """The class that tints a partial column, or nothing for a full one."""
    if step is not None and step.repeated:
        return _CLASS_REPEAT
    return _CLASS_BASS if partial else ""


def _html_head(
    title: str,
    subtitle: str,
    steps: Sequence[ArrangementStep],
    meter: str,
    show_timing: bool,
) -> List[str]:
    """The page's opening: document head, heading, provenance and the systems div.

    Split from the body so the page's *frame* is stated once, in one place, rather
    than interleaved with the loop that fills it.
    """
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
    count = len(steps)
    parts.append(
        f'<p class="meta">{count} step{"" if count == 1 else "s"}'
        f'{" · " + _escape(meter) if show_timing else ""}</p>'
    )
    parts.append('<div class="systems">')
    return parts


def _html_measure_spans(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    line: List[int],
    beats_per_bar: int,
    start_bar: int,
) -> List[List[int]]:
    """Split one system into measures at each bar change.

    Every measure gets its own ruled box, and the last measure of a system may be
    short. `start_bar` is subtracted because a pickup sits in a negative bar and the
    page counts bars from the first one it draws.
    """
    measures: List[List[int]] = []
    for index in line:
        same_bar = (
            measures
            and int(columns[measures[-1][0]][0] // beats_per_bar)
            == int(columns[index][0] // beats_per_bar)
        )
        if same_bar:
            measures[-1].append(index)
        else:
            measures.append([index])
    return measures


def _html_measure_opening(group: Sequence[Any]) -> str:
    """A measure's opening div: its repeat classes, its labels, and its table.

    `<table>` is appended to the same string so the default markup stays
    `<div class="measure"><table>`, which is what the layout tests match. A volta's
    `1.` and a navigation sign are both labels on the bar they open; they sit on
    opposite sides so a bar carrying both shows both.
    """
    classes = [_CLASS_MEASURE]
    if any(m.kind == "repeat_start" for m in group):
        classes.append(_CLASS_REPEAT_START)
    if any(m.kind == "repeat_end" for m in group):
        classes.append(_CLASS_REPEAT_END)
    opening = f'<div class="{" ".join(classes)}">'
    volta = next((m for m in group if m.kind == "ending_start"), None)
    if volta is not None:
        number = ",".join(str(n) for n in volta.numbers)
        opening += f'<span class="{_CLASS_VOLTA}">{number}.</span>'
    for marker in group:
        label = _NAVIGATION_LABELS.get(getattr(marker, "kind", ""))
        if label is not None:
            opening += f'<span class="{_CLASS_NAV}">{label}</span>'
    return opening + "<table>"


def format_tab_html(
    steps: List[ArrangementStep],
    title: str = "Chord-melody arrangement",
    subtitle: str = "",
    beats_per_bar: int = 4,
    beat_type: int = 4,
    rhythm: bool = True,
    show_melody: bool = True,
    show_mutes: bool = False,
    collapse: bool = True,
    measures_per_line: int = 4,
    notes: Optional[Sequence[str]] = None,
    show_timing: bool = True,
    markers: Sequence[Any] = (),
    first_bar_implicit: Optional[bool] = None,
) -> str:
    """
    Renders a whole progression as a self-contained HTML tab page.

    The same layout the ASCII staff draws, in a form a browser can present well:
    every column is a table cell, so chord names, fret numbers and barlines stay
    aligned by the table rather than by counting characters, and the page carries
    its own stylesheet (including a dark-mode one), so it needs no network access
    and no sibling files.

    `show_timing` adds the two rows the score renderers both carry: the **metre** over
    the first measure, and a **note value** per column. They are the same rows
    `format_tab_staff` draws and come from the same `_staff_rhythm`, so the page and the
    terminal cannot disagree about the rhythm.

    Args:
        steps: arranged steps, typically from arrange_progression().
        title: the page heading, and the browser window title.
        subtitle: an optional line under the heading, e.g. the performer.
        beats_per_bar: beats in a bar, used to place the barlines.
        beat_type: the denominator of that metre. Pass the notated value, so a head
            in cut time reads `2/2` rather than being restated as `2/4`, and its
            beat is a half note rather than a quarter.
        rhythm: space the chords on their real beats. Falls back to a uniform grid
            when the steps carry no timing, exactly as format_tab_staff does.
        show_melody: draw the melody-note line.
        show_mutes: spell out the unsounded strings as a dimmed x. A melody-only
            step always shows its x, since there the strings really are silent.
        collapse: strike each shape once and let it ring, rather than restriking
            an unchanged shape on every step.
        measures_per_line: bars per system of music.
        notes: optional lines of provenance, e.g. the register lift decision.
        show_timing: draw the metre and the note-value rows. On by default; `False`
            restores the page this renderer produced before them.
        markers: the head's repeat and ending instructions (`headxml.BarMarker`s), or
            empty for none. Each carries the **absolute** bar it sits on; the page marks
            the repeat bars and labels the volta brackets, the same structure the ASCII
            staff draws.
        first_bar_implicit: what the source said about the first bar, or `None` when
            nothing did. `False` fills a short first bar to its bar line rather than
            leaving it short as a pickup; see `format_tab_staff`.

    Returns:
        A complete HTML document as a string, or "" for no steps. Pure: nothing is
        printed and no file is written, so the caller stays in control.

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
    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)
    # Same predicate and rhythm as the ASCII staff, so both agree on note length.
    values = _staff_rhythm(
        columns, beats_per_bar, beat_type, _is_timed(steps, rhythm)
    )
    meter = _meter_label(beats_per_bar, beat_type)
    # Melody strings, marked once for the whole page rather than per chord.
    sopranos = {index for index in range(6) if _carries_melody(steps, index)}

    parts = _html_head(title, subtitle, steps, meter, show_timing)

    start_bar = int(columns[0][0] // beats_per_bar)
    # The head's repeat and ending signs, by the absolute bar they sit on - the same
    # bars the steps carry, so the page and the ASCII staff mark the same measures.
    markers_by_bar: Dict[int, List[Any]] = {}
    for marker in markers:
        markers_by_bar.setdefault(marker.bar, []).append(marker)
    # Chord in force, carried across systems so a held chord is named once.
    in_force: Optional[str] = None
    in_force_diagram: Optional[str] = None
    # Only the first measure of the page carries the metre; a signature holds until
    # it changes. See `_html_timing_rows`.
    first_measure = True

    def bar_of(index: int) -> int:
        return int(columns[index][0] // beats_per_bar) - start_bar

    for line in _staff_lines(columns, breaks, beats_per_bar):
        parts.append(f'<div class="{_CLASS_SYSTEM}">')
        parts.append(f'<span class="{_CLASS_BARNUM}">{bar_of(line[0]) + 1}</span>')
        # Split the system into measures at each bar change, so every measure gets
        # its own ruled box. The last measure of a system may be short.
        for measure in _html_measure_spans(columns, line, beats_per_bar, start_bar):
            absolute = int(columns[measure[0]][0] // beats_per_bar)
            parts.append(
                _html_measure_opening(markers_by_bar.get(absolute, ()))
            )
            if show_timing:
                parts.extend(
                    _html_timing_rows(columns, measure, values, meter, first_measure)
                )
                first_measure = False
            diagram_row, in_force_diagram = _html_diagram_row(columns, measure, in_force_diagram)
            parts.append(diagram_row)
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


# The seven names a star-import of this module must carry. Spelled out as one
# literal rather than `+=`, which a static checker cannot follow.
__all__ = [
    "format_tab_html",
    "write_tab_html",
]

