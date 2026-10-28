"""Whole-progression tab renderers: the six-line ASCII staff and the HTML page.

These are the two renderers that lay an arrangement out **along one staff in
reading order**, rather than one block per chord as `format_progression()` does:

- `format_tab_staff` - the ASCII staff, for a terminal.
- `format_tab_html` / `write_tab_html` - a self-contained HTML page for a browser.

They live together here because they share `_staff_columns`, which places each
step on an absolute beat and decides what is a strike and what is a hold. That
sharing is the point: both renderings place a chord in the same column *by
construction* and cannot drift apart, which is what the two grids have to agree
on for the `collapse` behaviour to mean the same thing in each.

The grid lives in `tabstaff_grid`, the ASCII drawing in `tabstaff_ascii` and
the HTML drawing in `tabstaff_html`. This module is the public facade: it
re-exports both renderers plus the MusicXML and GP5 writers so `from arranger import
format_tab_staff` and `from arranger import format_musicxml` keep one spelling.

Split out of `arranger.py` so the renderers can grow without making the voicing
engine harder to read. The only thing here that reaches into the package is
`arranger.step_types`; `tuning` is imported as a top-level module, so `tabstaff`
no longer reaches into `arranger` at module scope. [docs/dependency-dag.md]
(../docs/dependency-dag.md) has the measurement.
"""

from __future__ import annotations

from arranger.step_types import ArrangementStep

# The MusicXML and Guitar Pro renderers are ordinary top-level imports, re-exported
# from `arranger` so that `from arranger import format_musicxml` - the spelling in
# the README and the tests - keeps working.
#
# They are resolved as ordinary top-level imports because neither re-enters this
# module: both import `tuning` directly (top-level module) rather than
# `arranger.tuning`, and `tabgp` imports `tabxml`, not the reverse. Nothing here
# imports `tabstaff`.
#
# Nor is the laziness buying anything. `tabxml` needs music21 and `tabgp` needs
# PyGuitarPro, but each imports its extra *inside* the functions that use it, so
# importing either module is free on a machine that has neither - asserted with
# `sys.modules['music21'] = None` rather than assumed, so the two extras stay
# optional by test rather than by promise.
#
# Re-exporting here is what keeps one spelling for the whole rendering surface:
# `from arranger import format_musicxml` resolves through this module, and
# `arranger/__init__.py` re-exports *this* module's names.
from tabgp import format_gp5, write_gp5

# The ASCII and HTML staff renderers share the grid in `tabstaff_grid`; this
# facade re-exports their public entry points so callers keep one spelling.
from tabstaff_ascii import format_tab_staff
from tabstaff_html import format_tab_html, write_tab_html
from tabxml import format_musicxml, write_musicxml

# `STAFF_CELL_WIDTH` and `MUTED_CELL` are `tuning`'s: the staff and the vertical
# block have to put a fret in the same column by construction, and a second copy
# of the width here is exactly how the two would drift apart.


# The seven names a star-import of this module must carry. Spelled out as one
# literal rather than `+=`, which a static checker cannot follow.
__all__ = [
    "format_tab_staff",
    "format_tab_html",
    "write_tab_html",
    "format_musicxml",
    "write_musicxml",
    "format_gp5",
    "write_gp5",
]
