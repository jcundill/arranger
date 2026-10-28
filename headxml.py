"""MusicXML import: read a written head (melody + chord symbols) and arrange it.

`tabxml` is the MusicXML *exporter*; this is its counterpart, and it needs no
optional dependency to do its job. `zipfile` and `xml.etree` are enough to read
both forms of the format - a bare `.musicxml` document and a zipped `.mxl`
container - so a plain `pip install jazz-arranger` can import a head. That is the
opposite of the exporter, which needs `music21`; the asymmetry is deliberate, and
it means neither path can break the other.

It provides:

* `MUSICXML_KIND_QUALITIES` / `parse_musicxml_chord` - the format's own chord
  notation translated into the library's chord qualities, with untranslatable
  chords reported rather than guessed.
* `load_musicxml` - a file to a `Head`: the melody, its timing, the metre (count,
  denominator and the grouping the score states), the key it is in, and the chord in
  force under each note.
* `head_skeleton` / `arrange_xml_head` - the reduction and the arrangement.
* `head_cli` - the `arranger head FILE` command.

**The harmony is a timeline, not a per-note attribute.** A `<harmony>` element
precedes the note it governs, several can share a bar, and - routinely - a bar can
carry none at all, so a chord is held from the note it is declared before until
the next one replaces it. Reading the chord off the note that follows it would
guess.

**The voicings are not re-implemented here.** `arrange_xml_head` hands its slots
to `arranger.slots.arrange_slots`, the engine's own slot layer, so a head read
from a score is voiced by exactly the code every other caller uses. A second
implementation of the step loop is how this importer came to disagree with the
library once already.

Deliberately stdlib-only: `musthe` remains the sole dependency.

The implementation is split across focused sibling modules - `headxml_model`
(the data model), `headxml_read` (chord parsing and XML ingestion),
`headxml_repeats` (repeat/play-order expansion), `headxml_timeline` (the melody
and chord timelines plus arrangement) and `headxml_cli` (the `head` command).
This module re-exports their public surface so every `from headxml import ...`
spelling keeps working.
"""

from __future__ import annotations

from headxml_cli import _key_label, head_cli
from headxml_model import BarInstruction, BarMarker, Head, HeadChange, HeadNote
from headxml_read import (
    MUSICXML_KIND_QUALITIES,
    _part_is_tab,
    load_musicxml,
    parse_musicxml_chord,
)
from headxml_repeats import expand_repeats
from headxml_timeline import (
    MelodyRest,
    _merge_chord_slots,
    arrange_xml_head,
    chord_at,
    chord_slots,
    fill_slots,
    first_complete_bar,
    head_skeleton,
    melody_at,
    melody_rests,
    melody_state,
    rhythm_slots,
)

__all__ = [
    "MUSICXML_KIND_QUALITIES",
    "BarInstruction",
    "BarMarker",
    "Head",
    "HeadChange",
    "HeadNote",
    "MelodyRest",
    "arrange_xml_head",
    "chord_at",
    "chord_slots",
    "expand_repeats",
    "fill_slots",
    "first_complete_bar",
    "head_cli",
    "head_skeleton",
    "load_musicxml",
    "melody_at",
    "melody_rests",
    "melody_state",
    "parse_musicxml_chord",
]
