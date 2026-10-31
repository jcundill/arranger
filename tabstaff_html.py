"""HTML whole-progression staff renderer.

`format_tab_html` renders a whole progression as a self-contained HTML page
containing one inline SVG score modelled on TuxGuitar's `diag.svg`:
systems of measures stacked vertically, each measure a white card with six
staff lines, tab numbers on their string lines, red bar numbers and black
barlines on the staff, and fretboard chord diagrams above the staff at
each new fretted shape. The column grid is shared with
`tabstaff_ascii` through `tabstaff_grid`, so both renderers place a chord in
the same column by construction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from arranger.step_types import ArrangementStep
from tabstaff_grid import (
    _first_bar_content_end,
    _staff_breaks,
    _staff_columns,
    _staff_lines,
    _validate_staff_arguments,
)

# --- Page chrome (mirrors diag.svg) ----------------------------------------

_TITLE_Y = 18.0
_TITLE_SIZE = 16.0
_SUBTITLE_Y = 38.0
_SUBTITLE_SIZE = 12.0
_PAGE_RIGHT_MARGIN = 20.0
_PAGE_BOTTOM_MARGIN = 40.0

# --- System / measure geometry ---------------------------------------------

_SYSTEM_X = 20.0
_SYSTEM_FIRST_Y = 60.0
_SYSTEM_PITCH = 164.0
_MEASURE_CARD_HEIGHT = 153.0
_BEAT_UNIT = 27.5

_STAFF_LINE_YS = (67.0, 77.0, 87.0, 97.0, 107.0, 117.0)
_STAFF_STROKE = "#d6d6d6"
_STAFF_STROKE_WIDTH = "0.75"

_BARLINE_TOP = 67.0
_BARLINE_BOTTOM = 117.0
_MEASURE_NUMBER_Y = 62.0
_MEASURE_NUMBER_SIZE = 10.0
_MEASURE_NUMBER_FILL = "#ff0000"

_TAB_BASELINE_OFFSET = 3.75
_TAB_SIZE = 10.0
_TAB_FILL = "#404040"
_TAB_RECT_HEIGHT = 7.5
_TAB_RECT_CHAR_WIDTH = 7.0

# --- Chord diagram geometry (mirrors diag.svg) -----------------------------

_DIAGRAM_WIDTH = 43.0
_DIAGRAM_HEIGHT = 42.0
_MEASURE_NUMBER_X = 1.0

# Uniform left offset applied to every grid position (tab numbers,
# diagrams, beat markers) so beat 1 clears the left barline while keeping
# even spacing with beat 2 and beyond. Half a diagram width keeps a diagram
# centred on beat 0 fully inside the card.
_GRID_OFFSET_X = _DIAGRAM_WIDTH / 2.0
_DIAGRAM_GAP = 6.0
_DIAGRAM_STRING_XS = (13.0, 18.0, 23.0, 28.0, 33.0, 38.0)
_DIAGRAM_FRET_YS = (6.0, 12.0, 18.0, 24.0, 30.0, 36.0)
_DIAGRAM_DOT_R = 2.5
_DIAGRAM_DOT_FILL = "#404040"
_DIAGRAM_LINE_STROKE = "#d6d6d6"
_DIAGRAM_LINE_WIDTH = "0.75"
_DIAGRAM_X_SIZE = 2.0
_DIAGRAM_FIRST_FRET_Y = 12.0
_DIAGRAM_FIRST_FRET_SIZE = 8.0
_DIAGRAM_FIRST_FRET_FILL = "#000000"
# Minimum horizontal space (in pixels) between the right edge of the last
# diagram in a measure and the right barline, so the final chord never touches
# the bar line.
_MEASURE_RIGHT_PAD = 10.0
_DIAGRAM_NAME_Y = 49.5
_DIAGRAM_NAME_SIZE = 10.0
_DIAGRAM_NAME_FILL = "#000000"

# --- Beat markers under the staff ------------------------------------------

_BEAT_MARKER_Y = 135.0
_BEAT_MARKER_SIZE = 9.0
_BEAT_MARKER_FILL = "#000000"


def _pickup_first_bar(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
    beat_type: int,
) -> bool:
    """Whether the first bar is a pickup (short, not reaching the bar line).

    Reuses `_first_bar_content_end` from the shared grid: it returns `None`
    when the first bar runs to the bar line, and a float end position when
    it stops short (an anacrusis). Pickup bars are not numbered; numbering
    starts at 1 on the first complete bar.
    """
    return bool(
        columns
        and _first_bar_content_end(
            [(onset, step) for onset, step, _ in columns], beats_per_bar, beat_type
        )
        is not None
    )


def _bar_number(
    bar: int,
    first_bar_in_data: int,
    bar0_is_pickup: bool,
) -> Optional[int]:
    """Bar number for a measure: `None` for a pickup bar, otherwise starting at 1.

    Only bar 0 can be a pickup. If bar 0 is a pickup it is skipped and bar 1
    is number 1; otherwise the first bar in the data is number 1.
    """
    if bar == 0 and bar0_is_pickup:
        return None
    if bar0_is_pickup:
        return bar
    return bar - first_bar_in_data + 1


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


def _measure_width(
    beats_per_bar: int,
    diagrams: List[Tuple[ArrangementStep, float]],
) -> float:
    """Width of one measure card, wide enough that its diagrams do not overlap.

    Diagrams are centred on their beat positions scaled to the card width, so two
    diagrams on adjacent beats need centre spacing of at least ``_DIAGRAM_WIDTH +
    _DIAGRAM_GAP``. A diagram at beat 0 is clamped to half a card width from the
    left edge, so the next diagram needs even more room. The card is never
    narrower than the beat grid.
    """
    base = float(beats_per_bar) * _BEAT_UNIT
    # Every grid position carries the uniform left offset, so the rightmost
    # beat's diagram must fit with its right half inside the card, plus right
    # padding before the barline. The card is never narrower than this minimum.
    min_width = (
        (beats_per_bar - 1) * _BEAT_UNIT
        + 2 * _GRID_OFFSET_X
        + _MEASURE_RIGHT_PAD
    )
    if len(diagrams) < 2:
        return max(base, min_width)
    beats = sorted(beat for _, beat in diagrams)
    needed = base
    half = _DIAGRAM_WIDTH / 2.0
    pair_min = _DIAGRAM_WIDTH + _DIAGRAM_GAP
    for i in range(len(beats) - 1):
        b1, b2 = beats[i], beats[i + 1]
        gap_beats = b2 - b1
        if b1 == 0:
            # First diagram clamped to cx=half; second at b2 * W / B.
            # Need: b2 * W / B - half >= pair_min  ->  W >= B * (pair_min + half) / b2
            pair_needed = beats_per_bar * (pair_min + half) / b2
        else:
            pair_needed = beats_per_bar * pair_min / gap_beats
        needed = max(needed, pair_needed)
    # The last diagram's right edge must clear the right barline by
    # _MEASURE_RIGHT_PAD: cx + half <= measure_width - _MEASURE_RIGHT_PAD,
    # where cx = last_beat * W / B + half.
    # 2 * half + last_beat * W / B <= W - _MEASURE_RIGHT_PAD
    # W >= (2 * half + _MEASURE_RIGHT_PAD) / (1 - last_beat / beats_per_bar)
    last_beat = beats[-1]
    right_needed = (
        (2 * half + _MEASURE_RIGHT_PAD)
        / (1.0 - last_beat / beats_per_bar)
    )
    needed = max(needed, right_needed)
    return max(needed, min_width)


def _diagram_svg(step: ArrangementStep, cx: float) -> str:
    """One SVG fretboard chord diagram card centred on `cx` at the card top.

    Mirrors `diag.svg`: a 43x42 card with six strings, six frets, an X on
    each muted string at the nut, a grey first-fret index when the shape
    starts above fret 0, and a filled dot at each fretted string/fret
    intersection. Returns "" for fewer than two sounding strings.
    """
    frets = step.voicing.frets
    active = [f for f in frets if f >= 0]
    if len(active) < 2:
        return ""

    first_fret = min(active)
    x0 = cx - _DIAGRAM_WIDTH / 2.0

    parts: List[str] = []
    parts.append(
        f'<rect x="{x0:.1f}" y="0.0" width="{_DIAGRAM_WIDTH:.1f}" '
        f'height="{_DIAGRAM_HEIGHT:.1f}" fill="#ffffff" stroke="none"/>'
    )
    if first_fret > 0:
        parts.append(
            f'<text x="{x0 + 2.0:.1f}" y="{_DIAGRAM_FIRST_FRET_Y:.1f}" '
            f'text-anchor="start" font-family="Default" '
            f'font-size="{_DIAGRAM_FIRST_FRET_SIZE:.1f}" '
            f'fill="{_DIAGRAM_FIRST_FRET_FILL}">{first_fret}</text>'
        )
    # Six vertical strings.
    strings = " ".join(
        f"M {x0 + sx:.1f} 6.0 L {x0 + sx:.1f} 36.0"
        for sx in _DIAGRAM_STRING_XS
    )
    parts.append(
        f'<path d="{strings}" fill="none" stroke="{_DIAGRAM_LINE_STROKE}" '
        f'stroke-width="{str(_DIAGRAM_LINE_WIDTH)}"/>'
    )
    # Six horizontal frets.
    fret_path = " ".join(
        f"M {x0 + _DIAGRAM_STRING_XS[0]:.1f} {fy:.1f} "
        f"L {x0 + _DIAGRAM_STRING_XS[-1]:.1f} {fy:.1f}"
        for fy in _DIAGRAM_FRET_YS
    )
    parts.append(
        f'<path d="{fret_path}" fill="none" stroke="{_DIAGRAM_LINE_STROKE}" '
        f'stroke-width="{_DIAGRAM_LINE_WIDTH}"/>'
    )
    # X nut marks on muted strings.
    for i, fret in enumerate(frets):
        if fret < 0:
            sx = _DIAGRAM_STRING_XS[i]
            parts.append(
                f'<path d="M {x0 + sx - _DIAGRAM_X_SIZE:.1f} 0.0 '
                f'L {x0 + sx + _DIAGRAM_X_SIZE:.1f} 4.0 '
                f'M {x0 + sx + _DIAGRAM_X_SIZE:.1f} 0.0 '
                f'L {x0 + sx - _DIAGRAM_X_SIZE:.1f} 4.0 Z" '
                f'fill="none" stroke="{_DIAGRAM_LINE_STROKE}" '
                f'stroke-width="{_DIAGRAM_LINE_WIDTH}"/>'
            )
    # Filled dots at fretted positions.
    for i, fret in enumerate(frets):
        if fret >= 0:
            sx = _DIAGRAM_STRING_XS[i]
            fy = 9.0 + (fret - first_fret) * 6.0
            parts.append(
                f'<path d="M {x0 + sx - _DIAGRAM_DOT_R:.1f} {fy:.1f} '
                f'a {_DIAGRAM_DOT_R:.1f} {_DIAGRAM_DOT_R:.1f} 0 1 0 '
                f'{2 * _DIAGRAM_DOT_R:.1f} 0 {_DIAGRAM_DOT_R:.1f} {_DIAGRAM_DOT_R:.1f} '
                f'0 1 0 -{2 * _DIAGRAM_DOT_R:.1f} 0 Z" '
                f'fill="{_DIAGRAM_DOT_FILL}" stroke="none"/>'
            )
    return "".join(parts)


def _tab_number_svg(x: float, line_y: float, fret: int) -> str:
    """One tab number with a white rect behind it, baseline on the string line.

    Matches diag.svg: a white rect sized to the digit(s), then `#404040`
    text at font-size 10 whose baseline sits 3.75px below the string line so
    the glyph centre rests on the line.
    """
    text = str(fret)
    rect_width = len(text) * _TAB_RECT_CHAR_WIDTH + 1.0
    rect_y = line_y - _TAB_BASELINE_OFFSET - _TAB_RECT_HEIGHT / 2.0
    return (
        f'<rect x="{x:.1f}" y="{rect_y:.1f}" '
        f'width="{rect_width:.1f}" height="{_TAB_RECT_HEIGHT:.1f}" '
        f'fill="#ffffff" stroke="none"/>'
        f'<text x="{x:.1f}" y="{line_y + _TAB_BASELINE_OFFSET:.1f}" '
        f'text-anchor="start" font-family="Default" font-size="{_TAB_SIZE:.1f}" '
        f'fill="{_TAB_FILL}">{text}</text>'
    )


_CSS = """
body { margin: 0; padding: 1rem; font-family: ui-sans-serif, system-ui,
       -apple-system, "Segoe UI", sans-serif; color: #1b1b1b; }
h1 { font-size: 1.25rem; margin: 0 0 0.25rem; }
p.sub { margin: 0 0 1rem; color: #666; font-size: 0.9rem; }
svg { display: block; background: #ffffff; }
"""



def _sounded_frets(step: ArrangementStep) -> Tuple[int, ...]:
    """Return the frets actually struck at this step, muting the rest.

    - `repeated`: only the melody note on the soprano string — the other
      renderers play repeats as single notes with no chord underneath.
    - `bass_only`: only the bass string — the thumb invented this slot, the
      shape above it is held from the previous step and is silent here.
    - otherwise: every fretted string.
    """
    frets = step.voicing.frets
    if step.repeated:
        soprano = max(i for i, f in enumerate(frets) if f >= 0)
        return tuple(f if i == soprano else -1 for i, f in enumerate(frets))
    if step.bass_only:
        bass_string = step.voicing.bass_string
        if bass_string is not None:
            return tuple(f if i == bass_string else -1 for i, f in enumerate(frets))
    return tuple(frets)


def _render_tab_numbers(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    bar_col_indexes: List[int],
    beats_per_bar: int,
    bar: int,
    measure_width: float,
    measure_parts: List[str],
) -> None:
    """Append tab numbers for all struck strings in this measure's columns.

    x positions are scaled from beat space to the (possibly wider) measure
    width so they line up vertically with the diagram centres above them.
    On a repeated step only the melody note on the soprano string is shown,
    matching the other renderers which play repeats as single notes.
    """
    for i in bar_col_indexes:
        onset, step, strikes = columns[i]
        if step is None or not strikes:
            continue
        beat_in_bar = onset - bar * beats_per_bar
        # Scale beat position to the actual measure width, mirroring
        # `_draw_diagram`, so tab numbers sit directly below diagram centres.
        x = beat_in_bar * measure_width / beats_per_bar + _GRID_OFFSET_X
        # Clamp only on the left so beat 1 clears the barline. The number is
        # small enough to sit near the right edge of the card; keeping even
        # spacing between beats matters more than a right margin.
        x = max(_GRID_OFFSET_X, x)
        frets = _sounded_frets(step)
        for string_index in range(6):
            fret = frets[string_index]
            if fret < 0:
                continue
            # String index 0 = low E on the bottom line (y=117),
            # index 5 = high E on the top line (y=67).
            line_y = 117.0 - string_index * 10.0
            measure_parts.append(_tab_number_svg(x, line_y, fret))


def _collect_diagrams(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    bar_col_indexes: List[int],
    beats_per_bar: int,
    bar: int,
    previous_frets: Optional[Tuple[int, ...]],
) -> Tuple[List[Tuple[ArrangementStep, float]], Optional[Tuple[int, ...]]]:
    """Collect every new fretted shape in this measure as (step, beat_in_bar) pairs.

    A diagram is drawn each time the left hand moves to a new fretted shape — the
    same chord at a different position gets a new diagram, a held shape does not.
    A repeated step (same melody note re-sounded) gets no diagram: the other
    renderers play it as a single note with no chord underneath, and so does this
    one. Returns the diagram list plus the frets last seen (to carry dedupe state
    across bars).
    """
    diagrams: List[Tuple[ArrangementStep, float]] = []
    for i in bar_col_indexes:
        onset, step, strikes = columns[i]
        if step is None or not strikes:
            continue
        # A repeated step re-sounds the same melody note — the other renderers
        # play it as a single note with no chord diagram underneath, so skip it
        # here too. Only the first sounding of a note gets a diagram card.
        if step.repeated:
            continue
        # A `bass_only` step is invented by the thumb: the shape above it is
        # held from the previous step, so no new diagram card belongs here.
        if step.bass_only:
            continue
        frets = tuple(step.voicing.frets)
        if frets == previous_frets:
            continue
        beat_in_bar = onset - bar * beats_per_bar
        diagrams.append((step, beat_in_bar))
        previous_frets = frets
    return diagrams, previous_frets


def _draw_diagram(
    step: ArrangementStep,
    cx: float,
    measure_width: float,
    beats_per_bar: int,
    measure_parts: List[str],
) -> None:
    """Draw one fretboard diagram card centred on `cx` at the card top.

    `cx` is scaled from beat space to the (possibly wider) measure width so
    diagrams stay at their relative beat positions while having room to avoid
    overlap when a measure needs to be wider than the beat grid.
    """
    # Scale beat position to the actual measure width, then apply the uniform
    # left offset so beat 1 clears the barline. No right clamp: _measure_width
    # already makes the card wide enough that every diagram fits with right
    # padding before the barline.
    diagram_cx = cx * measure_width / beats_per_bar + _GRID_OFFSET_X
    diagram_cx = max(_GRID_OFFSET_X, diagram_cx)
    diagram_svg = _diagram_svg(step, diagram_cx)
    # Only draw the chord name if there is an actual diagram card (single-note
    # steps with fewer than two sounding strings get no diagram).
    if diagram_svg:
        measure_parts.append(diagram_svg)
        name_x = diagram_cx - _DIAGRAM_WIDTH / 2.0 + 2.0
        measure_parts.append(
            f'<text x="{name_x:.1f}" y="{_DIAGRAM_NAME_Y:.1f}" '
            f'text-anchor="start" font-family="Default" '
            f'font-size="{_DIAGRAM_NAME_SIZE:.1f}" '
            f'fill="{_DIAGRAM_NAME_FILL}">{_escape(step.chord)}</text>'
        )


def _html_head(title: str, subtitle: str) -> List[str]:
    """The HTML head and opening body, with the subtitle if any."""
    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{_escape(title)}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body><main>",
    ]
    if subtitle:
        parts.append(f'<p class="sub">{_escape(subtitle)}</p>')
    return parts


def _svg_opening(
    page_width: float, page_height: float, title: str, subtitle: str
) -> List[str]:
    """The SVG root element with background, title, and subtitle text."""
    parts: List[str] = [
        f'<svg width="{page_width:.1f}" height="{page_height:.1f}" '
        f'xmlns="http://www.w3.org/2000/svg" version="1.1">'
    ]
    parts.append(
        f'<rect width="{page_width:.1f}" height="{page_height:.1f}" '
        f'fill="#ffffff" stroke="none"/>'
    )
    if title:
        parts.append(
            f'<text x="{page_width / 2:.1f}" y="{_TITLE_Y:.1f}" '
            f'text-anchor="middle" font-family="Default" '
            f'font-size="{_TITLE_SIZE:.1f}" fill="#000000">{_escape(title)}</text>'
        )
    if subtitle:
        parts.append(
            f'<text x="{page_width / 2:.1f}" y="{_SUBTITLE_Y:.1f}" '
            f'text-anchor="middle" font-family="Default" '
            f'font-size="{_SUBTITLE_SIZE:.1f}" fill="#000000">{_escape(subtitle)}</text>'
        )
    return parts


def _render_beat_markers(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    bar_col_indexes: List[int],
    beats_per_bar: int,
    measure_width: float,
    measure_parts: List[str],
    bar_number: Optional[int],
) -> None:
    """Draw beat numbers (1, 2, 3, ...) under the staff at their beat positions.

    Beat N sits at (N-1)/beats_per_bar across the card, using the same
    beat-to-x scaling as the tab numbers and diagram centres above. Beat 1 is
    clamped to half a diagram width so it does not sit under the left barline
    but lines up with a diagram or tab number on beat 1.

    On a pickup bar (`bar_number` is None) only beats that actually carry a
    column are marked, so the markers stay in sync with the chords in the
    short bar rather than implying beats that do not exist there.
    """
    if bar_number is None and bar_col_indexes:
        # Pickup bar: mark only beats where columns exist, so markers stay
        # in sync with the actual chords in the incomplete bar.
        beats_seen: set[float] = set()
        for i in bar_col_indexes:
            onset, _, _ = columns[i]
            beat_in_bar = onset  # bar 0: no offset
            if beat_in_bar in beats_seen:
                continue
            beats_seen.add(beat_in_bar)
            x = beat_in_bar * measure_width / beats_per_bar + _GRID_OFFSET_X
            x = max(_GRID_OFFSET_X, x)
            label = str(int(beat_in_bar) + 1)
            measure_parts.append(
                f'<text x="{x:.1f}" y="{_BEAT_MARKER_Y:.1f}" '
                f'text-anchor="middle" font-family="Default" '
                f'font-size="{_BEAT_MARKER_SIZE:.1f}" '
                f'fill="{_BEAT_MARKER_FILL}">{label}</text>'
            )
    else:
        for beat in range(beats_per_bar):
            x = beat * measure_width / beats_per_bar + _GRID_OFFSET_X
            label = str(beat + 1)
            # Clamp only on the left so beat 1 clears the barline. Even spacing
            # between beats matters more than a right margin: markers are small
            # and sit near the right edge of the card without overflowing.
            x = max(_GRID_OFFSET_X, x)
            measure_parts.append(
                f'<text x="{x:.1f}" y="{_BEAT_MARKER_Y:.1f}" '
                f'text-anchor="middle" font-family="Default" '
                f'font-size="{_BEAT_MARKER_SIZE:.1f}" '
                f'fill="{_BEAT_MARKER_FILL}">{label}</text>'
            )


def _render_measure(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    bar_col_indexes: List[int],
    beats_per_bar: int,
    bar: int,
    measure_width: float,
    diagrams: List[Tuple[ArrangementStep, float]],
    measure_parts: List[str],
    bar_number: Optional[int],
) -> None:
    """Append one measure group's SVG to `measure_parts`.

    The measure carries a white card, six staff lines, tab numbers at struck
    columns, a fretboard diagram for each new chord (with its chord name below),
    a red bar number (skipped when `bar_number` is None, i.e. on a pickup bar;
    starting at 1 on the first complete bar), and black barlines on the staff
    at both edges.
    """
    # Card rect.
    measure_parts.append(
        f'<rect x="0.0" y="0.0" width="{measure_width:.1f}" '
        f'height="{_MEASURE_CARD_HEIGHT:.1f}" fill="#ffffff" stroke="none"/>'
    )
    # Six staff lines.
    staff_lines = " ".join(
        f"M 0.0 {y:.1f} L {measure_width:.1f} {y:.1f}" for y in _STAFF_LINE_YS
    )
    measure_parts.append(
        f'<path d="{staff_lines}" fill="none" stroke="{_STAFF_STROKE}" '
        f'stroke-width="{_STAFF_STROKE_WIDTH}"/>'
    )
    # Tab numbers at struck columns (scaled to line up with diagram centres).
    _render_tab_numbers(
        columns, bar_col_indexes, beats_per_bar, bar, measure_width, measure_parts
    )
    # Diagram on every new fretted shape of this measure.
    for step, beat_in_bar in diagrams:
        _draw_diagram(step, beat_in_bar, measure_width, beats_per_bar, measure_parts)
    # Measure number (red, like diag.svg). None means a pickup bar: skip it.
    # Numbering starts at 1 on the first complete bar.
    if bar_number is not None:
        measure_parts.append(
            f'<text x="{_MEASURE_NUMBER_X:.1f}" y="{_MEASURE_NUMBER_Y:.1f}" '
            f'text-anchor="start" font-family="Default" '
            f'font-size="{_MEASURE_NUMBER_SIZE:.1f}" '
            f'fill="{_MEASURE_NUMBER_FILL}">{bar_number}</text>'
        )
    # Left barline (below the staff, clear of tab numbers).
    measure_parts.append(
        f'<path d="M 0.0 {_BARLINE_TOP:.1f} L 0.0 {_BARLINE_BOTTOM:.1f}" '
        f'fill="#000000" stroke="#000000" stroke-width="1.0"/>'
    )
    # Right barline (below the staff, clear of tab numbers).
    measure_parts.append(
        f'<path d="M {measure_width:.1f} {_BARLINE_TOP:.1f} L {measure_width:.1f} {_BARLINE_BOTTOM:.1f}" '
        f'fill="#000000" stroke="#000000" stroke-width="1.0"/>'
    )
    # Beat markers under the staff.
    _render_beat_markers(
        columns, bar_col_indexes, beats_per_bar, measure_width,
        measure_parts, bar_number,
    )


def format_tab_html(
    steps: List[ArrangementStep],
    title: str = "Chord-melody arrangement",
    subtitle: str = "",
    beats_per_bar: int = 4,
    beat_type: int = 4,
    rhythm: bool = True,
    measures_per_line: int = 4,
) -> str:
    """
    Renders a whole progression as a self-contained HTML tab page.

    The page shows SVG fretboard chord diagrams above a six-line tab staff,
    matching the appearance of `diag.svg`/`diag.tab`. Every column is laid out
    from the shared grid in `tabstaff_grid`, so the HTML page and the ASCII
    staff place a chord in the same column by construction.

    Args:
        steps: arranged steps, typically from arrange_progression().
        title: the page heading, and the browser window title.
        subtitle: an optional line under the heading, e.g. the performer.
        beats_per_bar: beats in a bar, used to place the barlines.
        beat_type: the denominator of that metre. Pass the notated value, so a
            head in cut time reads `2/2` rather than being restated as `2/4`.
        rhythm: space the chords on their real beats. Falls back to a uniform
            grid when the steps carry no timing.
        measures_per_line: bars per system of music.

    Returns:
        A complete HTML document as a string, or "" for no steps. Pure: nothing
        is printed and no file is written, so the caller stays in control.

    Raises:
        ValueError: if `beats_per_bar` or `beat_type` is below 1, or
            `measures_per_line` is below 1.
    """
    _validate_staff_arguments(beats_per_bar, beat_type, measures_per_line)
    if not steps:
        return ""

    columns = _staff_columns(steps, beats_per_bar, beat_type, rhythm, collapse=True)
    if not columns:
        return ""

    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)
    systems = _staff_lines(columns, breaks, beats_per_bar)
    if not systems:
        return ""

    # The bar index of the first column, and whether bar 0 is a pickup.
    # Only bar 0 can be a pickup; if the data starts at a later bar, bar 0
    # simply doesn't exist and is not a pickup.
    first_bar_in_data = int(columns[systems[0][0]][0] // beats_per_bar)
    bar0_is_pickup = (
        first_bar_in_data == 0
        and _pickup_first_bar(columns, beats_per_bar, beat_type)
    )

    # Pre-compute per-measure widths (variable: wider measures fit more diagrams)
    # and collect diagram info per measure. Returns list of (system_index, bar,
    # width, diagrams, bar_number) tuples; bar_number is None for pickup bars.
    measure_plans: List[
        Tuple[int, int, float, List[Tuple[ArrangementStep, float]], Optional[int]]
    ] = []
    system_total_widths: Dict[int, float] = {}
    for system_index, system in enumerate(systems):
        first_bar = int(columns[system[0]][0] // beats_per_bar)
        last_bar = int(columns[system[-1]][0] // beats_per_bar)
        total = 0.0
        for bar in range(first_bar, last_bar + 1):
            bar_col_indexes = [
                i for i in system if int(columns[i][0] // beats_per_bar) == bar
            ]
            # Reset dedupe state per bar so each measure shows its own first shape.
            diagrams, _ = _collect_diagrams(
                columns, bar_col_indexes, beats_per_bar, bar, None
            )
            mw = _measure_width(beats_per_bar, diagrams)
            bar_number = _bar_number(bar, first_bar_in_data, bar0_is_pickup)
            measure_plans.append((system_index, bar, mw, diagrams, bar_number))
            total += mw
        system_total_widths[system_index] = total

    page_width = _SYSTEM_X + max(system_total_widths.values()) + _PAGE_RIGHT_MARGIN
    page_height = (
        _SYSTEM_FIRST_Y + (len(systems) - 1) * _SYSTEM_PITCH
        + _MEASURE_CARD_HEIGHT + _PAGE_BOTTOM_MARGIN
    )

    parts = _html_head(title, subtitle)
    parts.extend(_svg_opening(page_width, page_height, title, subtitle))

    # Render measures, accumulating x position per system.
    system_measure_x: Dict[int, float] = {}
    for system_index, bar, mw, diagrams, bar_number in measure_plans:
        if system_index not in system_measure_x:
            system_measure_x[system_index] = _SYSTEM_X
        measure_x = system_measure_x[system_index]
        sys_y = _SYSTEM_FIRST_Y + system_index * _SYSTEM_PITCH

        bar_col_indexes = [
            i for i in systems[system_index]
            if int(columns[i][0] // beats_per_bar) == bar
        ]

        measure_parts: List[str] = []
        _render_measure(
            columns,
            bar_col_indexes,
            beats_per_bar,
            bar,
            mw,
            diagrams,
            measure_parts,
            bar_number,
        )

        parts.append(
            f'<g transform="translate({measure_x:.1f}, {sys_y:.1f})">'
            + "".join(measure_parts)
            + "</g>"
        )
        system_measure_x[system_index] = measure_x + mw

    parts.append("</svg>")
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


# The two names a star-import of this module must carry. Spelled out as one
# literal rather than `+=`, which a static checker cannot follow.
__all__ = [
    "format_tab_html",
    "write_tab_html",
]
