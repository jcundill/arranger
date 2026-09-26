"""Export a clean, measure-aligned JSON lead sheet from the Weimar Jazz Database.

The database's real schema is *not* the one in the published description, so the
loader is written against what is actually in ``wjazzd.db``:

* there is no ``melopy_notes`` table -- notes live in ``melody``
  (``melid, onset, pitch, duration, bar, beat, tatum, subtatum, division``);
* ``solo_info`` has no ``tempo`` column -- the tempo is ``avgtempo``;
* **notes carry no chord at all**, and neither ``melody`` nor ``beats`` has a
  ``chord_type`` or a relative-pitch-class column.

Because the chord is not stored on the note, each note's active chord is
reconstructed by a *forward fill* over ``beats``: the last non-empty ``chord``
whose ``(bar, beat)`` is <= the note's. ``bar`` is a signed integer everywhere --
1,335 ``beats`` rows across 149 transcriptions are negative (the anacrusis,
down to bar -31) -- so ordering on the ``(bar, beat)`` tuple handles pickups
with no special case.

Chords are emitted per measure as ``{"beat": ..., "symbol": ...}`` rather than a
flat list of symbols, because ``beats.chord`` is populated only on the beat a
chord *starts*. A flat list loses both the ordering and the ability to tell that
a given note falls under an ``NC`` span.

Standard library only (``sqlite3``), per the standing rule that ``musthe`` is the
sole runtime dependency of the package.
"""

from __future__ import annotations

import bisect
import json
import sqlite3
from typing import Any, Optional

# The database's marker for a bar with melody but no harmony. Such a note is
# played alone -- see CORPUS_PLAN.md section 5.
NO_CHORD = "NC"

#: The twelve pitch classes, in the spelling the note names use.
PITCH_CLASSES = (
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
)


def midi_to_note_name(midi_val: float) -> str:
    """Convert a MIDI number to a note name (e.g. ``60`` -> ``'C4'``)."""
    midi_int = int(round(midi_val))
    return f"{PITCH_CLASSES[midi_int % 12]}{(midi_int // 12) - 1}"


def _load_chord_timeline(
    cursor: sqlite3.Cursor, melid: int
) -> tuple[list[tuple[int, int]], list[str]]:
    """Return sorted ``(bar, beat)`` keys and the chord symbol at each one.

    Only beats on which a chord *starts* are present, which is what makes the
    forward fill a single ``bisect`` lookup per note.
    """
    rows = cursor.execute(
        """
        SELECT bar, beat, chord
        FROM beats
        WHERE melid = ? AND chord IS NOT NULL AND chord <> ''
        ORDER BY bar ASC, beat ASC
        """,
        (melid,),
    ).fetchall()
    keys = [(int(r["bar"]), int(r["beat"])) for r in rows]
    chords = [str(r["chord"]) for r in rows]
    return keys, chords


def _forward_fill(
    keys: list[tuple[int, int]], chords: list[str], bar: int, beat: int
) -> Optional[str]:
    """Return the chord in force at ``(bar, beat)``, or ``None`` before the first.

    Comparing the ``(bar, beat)`` tuple keeps negative bars correct: they simply
    sort ahead of bar 0.
    """
    index = bisect.bisect_right(keys, (bar, beat))
    return chords[index - 1] if index else None


def export_wjd_leadsheet(
    db_path: str,
    melid: int,
    output_json_path: Optional[str] = None,
    bars: Optional[tuple[int, int]] = None,
) -> dict[str, Any]:
    """Build a clean, measure-aligned lead sheet for one transcription.

    Args:
        db_path: Path to the Weimar Jazz Database SQLite file (e.g. ``wjazzd.db``).
        melid: The unique ID of the transcription to extract.
        output_json_path: Optional path to save the resulting JSON file.
        bars: Optional half-open ``(lo, hi)`` measure range, inclusive of ``lo``
            and exclusive of ``hi``. Bounds may be negative to select anacrusis
            material; the default selects the whole transcription.

    Returns:
        A dict with metadata and a list of measures, each holding the chords
        that start in it and the melody notes that sound in it.

    Raises:
        ValueError: If ``melid`` is not present in ``solo_info``.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    meta_row = cursor.execute(
        """
        SELECT melid, title, performer, key, signature, avgtempo, style
        FROM solo_info
        WHERE melid = ?
        """,
        (melid,),
    ).fetchone()

    if not meta_row:
        conn.close()
        raise ValueError(f"No entry found in 'solo_info' for melid = {melid}")

    leadsheet: dict[str, Any] = {
        "melid": meta_row["melid"],
        "title": meta_row["title"],
        "performer": meta_row["performer"],
        "key": meta_row["key"],
        "time_signature": meta_row["signature"],
        "tempo": meta_row["avgtempo"],
        "style": meta_row["style"],
        "measures": [],
    }

    chord_keys, chord_symbols = _load_chord_timeline(cursor, melid)

    # A measure is emitted when either a chord starts in it or a note sounds in
    # it. Collecting chords from the timeline rather than from the note rows
    # keeps chord-only measures (bars 2 and 8 of melid 1) in the harmony.
    measures: dict[int, dict[str, Any]] = {}

    def measure(bar: int) -> dict[str, Any]:
        if bar not in measures:
            measures[bar] = {"measure": bar, "chords": [], "melody": []}
        return measures[bar]

    for index, (bar, beat) in enumerate(chord_keys):
        if bars is not None and not (bars[0] <= bar < bars[1]):
            continue
        symbol = chord_symbols[index]
        measure(bar)["chords"].append(
            {"beat": beat, "symbol": symbol, "is_no_chord": symbol == NO_CHORD}
        )

    note_rows = cursor.execute(
        """
        SELECT bar, beat, pitch, duration
        FROM melody
        WHERE melid = ?
        ORDER BY bar ASC, beat ASC
        """,
        (melid,),
    ).fetchall()
    conn.close()

    for row in note_rows:
        bar = int(row["bar"])
        beat = int(row["beat"])
        if bars is not None and not (bars[0] <= bar < bars[1]):
            continue
        midi = int(round(row["pitch"]))
        measure(bar)["melody"].append(
            {
                "beat": beat,
                "pitch_name": midi_to_note_name(midi),
                "midi": midi,
                "duration": float(row["duration"]),
                "active_chord": _forward_fill(chord_keys, chord_symbols, bar, beat),
            }
        )

    # Sorted so negative-bar anacrusis material leads, as it does in the data.
    leadsheet["measures"] = [measures[b] for b in sorted(measures)]

    if output_json_path:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(leadsheet, f, indent=2)

    return leadsheet

# --- Example Usage ---
if __name__ == "__main__":
    DB_FILE = "wjazzd.db"  # Path to your extracted Weimar Jazz Database SQLite file
    TRACK_ID = 342        # melid = 218 (John Coltrane, "Blue Train")

    try:
        data = export_wjd_leadsheet(
            db_path=DB_FILE,
            melid=TRACK_ID,
            output_json_path="leadsheet_export.json",
        )
        print(
            f"Successfully exported '{data['title']}' "
            f"({len(data['measures'])} measures) to JSON."
        )
    except Exception as e:
        print(f"Error executing script: {e}")
