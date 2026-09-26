"""Optional Weimar Jazz Database (wjazzd.db) glue for the `arranger` library.

The database is **not** committed to this repository (see `.gitignore`); it is
downloaded from jazzomat.hfm-weimar.de and located at runtime. This module is
therefore optional dataset glue: nothing in `arranger.py` imports it, and the
library's public surface is unchanged by its presence.

It provides:

* `WEIMAR_QUALITY_ALIASES` / `parse_weimar_chord` - the database's chord notation
  translated into the library's chord qualities, with unmapped suffixes reported
  rather than guessed.
* `list_solos` / `list_sections` / `parse_section_selector` / `load_solo` /
  `load_section` - metadata, span selection and note loading, with each note's
  active chord reconstructed by a forward fill over the `beats` table.

Deliberately stdlib-only (`sqlite3`): `musthe` remains the sole dependency.

See `CORPUS_PLAN.md` for the measurements the design decisions rest on.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from arranger import NO_CHORD, ChordParser

__all__ = [
    "DEFAULT_DB",
    "NO_CHORD",
    "SECTION_TYPES",
    "Solo",
    "NoteEvent",
    "Section",
    "WeimarChord",
    "parse_weimar_chord",
    "list_solos",
    "list_sections",
    "parse_section_selector",
    "matching_sections",
    "load_solo",
    "load_section",
]


# Database location: a `wjazzd.db` sitting beside this module by default, and
# overridable with the WJAZZD_DB environment variable (absolute, or relative to
# the current working directory).
DEFAULT_DB = Path(__file__).resolve().parent / "wjazzd.db"

# The five span kinds the `sections` table actually uses. A selector naming
# anything else is a typo, and raises rather than silently matching no rows.
SECTION_TYPES = ("CHORD", "IDEA", "PHRASE", "FORM", "CHORUS")


# ---------------------------------------------------------------------------
# Weimar chord notation
# ---------------------------------------------------------------------------

# Suffix -> library quality, derived from the 108 distinct suffixes in the
# database rather than guessed. A suffix that is absent resolves to None and is
# counted and reported, so an incomplete table degrades into "this chord was not
# translated" instead of a silently wrong chord.
#
# Note the deliberate asymmetry with ChordParser: here "" is a major triad and
# "-" is a minor triad, because that is what the Weimar notation means. Both map
# onto the library's canonical spellings via ChordParser.canonical_quality.
WEIMAR_QUALITY_ALIASES: Dict[str, Optional[str]] = {
    # triads
    "": "maj",
    "-": "m",
    "+": "aug",
    # "o" is a diminished triad, which this library does not voice; its "dim"
    # alias resolves to dim7, the shape actually used.
    "o": "dim7",
    # sixths and sevenths
    "6": "6",
    "-6": "m6",
    "-69": "m6",
    "69": "6/9",
    "7": "7",
    "-7": "m7",
    "j7": "maj7",
    "-j7": "mMaj7",
    "sus": "sus4",
    "sus7": "7sus4",
    "m7b5": "m7b5",
    "o7": "dim7",
    "+7": "7#5",
    "+j7": "maj7#11",
    # extended
    "79": "9",
    "-79": "m9",
    "j9": "maj9",
    "13": "13",
    "7911": "7sus4",
    "7911#": "7#11",
    "7913": "13",
    "7913b": "7b13",
    "79b": "7b9",
    "79#": "7#11",
    "79b13": "7b13",
    "7alt": "7alt",
    # Compound suffixes the database actually uses, listed explicitly rather
    # than pattern-matched. Only qualities the library can actually voice appear
    # here: a Weimar chord the library has no shape for (m13, 9sus4, 7#13, ...)
    # is deliberately left out so it reports as an unmapped suffix and is
    # counted, instead of resolving to a nearby-but-wrong quality. "79#13" is one
    # such case: the Weimar notation is a real 7#13, and the library voices
    # 7b13 but not 7#13, so it is left unmapped rather than folded into 7b13.
    "-7911": "m9",        # minor 7sus4 read as a minor 9th chord
    "+79": "7#5",         # the '+' family is read as an altered dominant
    "+79#": "7#5",
    "+7911#": "7#5",
    "+79b": "7#5",
    "-j7911#": "m9b5",    # minor-major-7 #11 == half-diminished 9th
    "-79b": "m7b5",
    "79#11#": "7#11",     # alternate spellings of the same altered dominants
    "j79": "maj9",
    "j79#": "maj7#11",
    "j79#11#": "maj7#11",
    "j7911#": "maj7#11",
}

# A Weimar chord symbol: an optional root, a quality suffix, and an optional
# slash bass.
_CHORD_SYMBOL_RE = re.compile(
    r"""^
    (?P<root>[A-G][#b]?)     # root pitch, e.g. Eb
    (?P<suffix>[^/]*)       # quality suffix, e.g. -7
    (?:/(?P<bass>[A-G][#b]?))?   # optional slash bass, e.g. /G
    $""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class WeimarChord:
    """A parsed Weimar chord symbol.

    `quality` is the library quality, or None when the suffix is not in
    WEIMAR_QUALITY_ALIASES. `is_no_chord` marks the "NC" (no chord) symbol.
    """

    symbol: str
    root: Optional[str] = None
    quality: Optional[str] = None
    bass: Optional[str] = None

    @property
    def is_no_chord(self) -> bool:
        return self.symbol == NO_CHORD

    @property
    def unresolved(self) -> bool:
        """True for a real chord whose suffix the table does not translate."""
        return not self.is_no_chord and self.quality is None


def parse_weimar_chord(symbol: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Splits a Weimar chord symbol into (root, quality, bass).

    The slash bass is stripped before anything else, because arranger's
    ChordParser glues a bass onto the quality and would fail every table lookup
    (and the voicing engine has no notion of a bass note at all).

        'Bb6'   -> ('Bb', '6',    None)
        'A-/G'  -> ('A',  'm',    'G')
        'NC'    -> (None, None,   None)

    `quality` is the library spelling, or None when the suffix is unmapped.
    """
    symbol = (symbol or "").strip()
    if not symbol or symbol == NO_CHORD:
        return None, None, None

    match = _CHORD_SYMBOL_RE.match(symbol)
    if not match:
        return None, None, None

    root = match.group("root")
    suffix = match.group("suffix")
    bass = match.group("bass")
    quality = WEIMAR_QUALITY_ALIASES.get(suffix)
    if quality is not None:
        # Guard against a table entry that names a spelling the library does not
        # itself know; those would fail silently later, so they report as None.
        quality = ChordParser.canonical_quality(quality) or None
        if quality not in ChordParser.CHORD_TONES_FROM_ROOT:
            quality = None
    return root, quality, bass


def _weimar_chord(symbol: str) -> WeimarChord:
    """parse_weimar_chord wrapped in the WeimarChord record."""
    root, quality, bass = parse_weimar_chord(symbol)
    return WeimarChord(symbol=symbol, root=root, quality=quality, bass=bass)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """One `sections` row: a half-open bar span [start, end) of one kind.

    `type` is the kind of span (CHORD, IDEA, PHRASE, FORM, CHORUS) and `value` is
    what the span is - a chord symbol, an analyst's idea, a phrase number, a form
    label or a chorus number. Bars are signed: the anacrusis is numbered with
    negative bars, and a `start == end` span is legal and selects nothing.
    """

    melid: int
    type: str
    start: int
    end: int
    value: str

    @property
    def length(self) -> int:
        """Span length in bars; 0 for the degenerate start == end case."""
        return max(0, self.end - self.start)

    def contains_bar(self, bar: int) -> bool:
        return self.start <= bar < self.end


@dataclass
class NoteEvent:
    """One transcribed melody note, with its chord reconstructed.

    `pitch` is the MIDI number, `bar` and `beat` its position (bar may be
    negative). `chord` is the raw Weimar symbol from the forward fill - "NC" for
    a bar with no harmony - and `quality` is its library translation, or None
    when the suffix is unmapped.
    """

    bar: int
    beat: float
    pitch: int
    duration: float
    onset: float = 0.0
    tatum: float = 0.0
    chord: str = ""
    quality: Optional[str] = None
    bass: Optional[str] = None

    @property
    def is_no_chord(self) -> bool:
        return self.chord == NO_CHORD

    @property
    def beat_position(self) -> float:
        """Absolute beat offset from the start of the piece, negative-bar safe.

        `beat` in the database is the beat *within* its bar, so the absolute
        position is bar + (beat - 1). Because bars are signed this orders pickup
        material correctly without a special case.
        """
        return self.bar + (self.beat - 1)


@dataclass
class Solo:
    """A transcription: its `solo_info` metadata plus its note events."""

    melid: int
    performer: str = ""
    title: str = ""
    key: str = ""
    signature: str = ""
    avgtempo: float = 0.0
    style: str = ""
    chord_changes: str = ""
    chorus_count: int = 0
    notes: List[NoteEvent] = field(default_factory=list)
    # Suffixes seen on this solo's chords that WEIMAR_QUALITY_ALIASES could not
    # translate, with counts. Reported rather than guessed.
    unmapped_suffixes: Dict[str, int] = field(default_factory=dict)

    @property
    def bars(self) -> Tuple[int, int]:
        """(first, last + 1) bar covered by the notes, empty-safe."""
        if not self.notes:
            return (0, 0)
        return (min(n.bar for n in self.notes), max(n.bar for n in self.notes) + 1)

    def notes_in_bars(self, lo: Optional[int] = None, hi: Optional[int] = None) -> List[NoteEvent]:
        """Notes with lo <= bar < hi; both bounds default to the whole solo."""
        if lo is None and hi is None:
            return list(self.notes)
        first, last = self.bars
        lo = first if lo is None else lo
        hi = last if hi is None else hi
        return [n for n in self.notes if lo <= n.bar < hi]

    def chords(self) -> List[Tuple[int, str]]:
        """The chord changes as (bar, Weimar symbol), read from the forward fill.

        Only the changes are returned, not one row per note: consecutive notes
        sharing a chord collapse into a single entry.
        """
        changes: List[Tuple[int, str]] = []
        last: Optional[str] = None
        for note in self.notes:
            if note.chord and note.chord != last:
                changes.append((note.bar, note.chord))
                last = note.chord
        return changes


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def _db_path(db_path: Optional[Union[str, Path]] = None) -> Path:
    """Resolves the database location: argument, then WJAZZD_DB, then DEFAULT_DB."""
    if db_path is not None:
        return Path(db_path)
    env = os.environ.get("WJAZZD_DB")
    if env:
        return Path(env)
    return DEFAULT_DB


def _connect(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Opens the database read-only, failing with a clear message when absent."""
    path = _db_path(db_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Weimar Jazz Database not found at {path}. Download wjazzd.db from "
            f"jazzomat.hfm-weimar.de, or point WJAZZD_DB at an existing copy."
        )
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def list_solos(db_path: Optional[Union[str, Path]] = None) -> List[Solo]:
    """Every transcription in the database (456 rows), without note events."""
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT melid, performer, title, key, signature, avgtempo, style,
                   chord_changes, chorus_count
            FROM solo_info
            ORDER BY melid
            """
        ).fetchall()
    return [
        Solo(
            melid=int(row["melid"]),
            performer=row["performer"] or "",
            title=row["title"] or "",
            key=row["key"] or "",
            signature=row["signature"] or "",
            avgtempo=float(row["avgtempo"] or 0.0),
            style=row["style"] or "",
            chord_changes=row["chord_changes"] or "",
            chorus_count=int(row["chorus_count"] or 0),
        )
        for row in rows
    ]


def list_sections(
    melid: int,
    type: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Section]:
    """Every `sections` row for one transcription, ordered by start bar.

    `type` filters by span kind; the name is validated against SECTION_TYPES so
    a typo raises instead of quietly matching no rows.
    """
    if type is not None and type.upper() not in SECTION_TYPES:
        raise ValueError(f"Unknown section type {type!r}; expected one of {SECTION_TYPES}")

    query = "SELECT melid, type, start, end, value FROM sections WHERE melid = ?"
    params: List[object] = [melid]
    if type is not None:
        query += " AND type = ?"
        params.append(type.upper())
    query += " ORDER BY start, end"

    with _connect(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [
        Section(
            melid=int(row["melid"]),
            type=row["type"],
            start=int(row["start"]),
            end=int(row["end"]),
            value=row["value"] or "",
        )
        for row in rows
    ]


def parse_section_selector(selector: str) -> Tuple[str, str]:
    """Parses a "type:value" selector into (SECTION_TYPE, value).

        'form:A1'    -> ('FORM', 'A1')
        'form:A*'    -> ('FORM', 'A*')
        'chorus:1'   -> ('CHORUS', '1')
        'phrase:-1'  -> ('PHRASE', '-1')

    The type is matched case-insensitively and validated against SECTION_TYPES,
    raising ValueError for an unknown one - a mistyped kind matches no rows,
    which reads like "this transcription has no such section" and hides a typo.

    A `*` in the value is a glob (applied by `matching_sections`), which is how
    `form:A*` selects every A-block. Note the value is returned verbatim: it may
    legitimately start with a `-`, as `phrase:-1` does.
    """
    if ":" not in selector:
        raise ValueError(
            f"Invalid section selector {selector!r}; expected 'type:value' "
            f"e.g. 'form:A1', 'chorus:1'"
        )
    raw_type, _, value = selector.partition(":")
    kind = raw_type.strip().upper()
    if kind not in SECTION_TYPES:
        raise ValueError(f"Unknown section type {raw_type!r}; expected one of {SECTION_TYPES}")
    value = value.strip()
    if not value:
        raise ValueError(f"Missing section value in {selector!r}")
    return kind, value


def matching_sections(
    melid: int,
    selector: str,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Section]:
    """Sections of a transcription matching a "type:value" selector, in bar order.

    Matching is case-insensitive and a `*` in the value is a glob. Several
    selectors may be given in one comma-separated string, so
    `--section 'chorus:1,chorus:2'` is one selection. Overlapping spans are
    returned as they are: merging them would silently hide double-stated material.
    """
    results: List[Section] = []
    for part in selector.split(","):
        kind, value = parse_section_selector(part.strip())
        pattern = value.lower()
        for section in list_sections(melid, type=kind, db_path=db_path):
            if fnmatch(section.value.lower(), pattern):
                results.append(section)
    results.sort(key=lambda s: (s.start, s.end))
    return results


def _chord_timeline(melid: int, connection: sqlite3.Connection) -> List[Tuple[Tuple[int, float], str]]:
    """The (position, chord) rows a note's chord is filled forward from.

    `beats` carries a chord only on the beat a chord *starts*, so this is the
    sparse list of chord onsets, ordered by the (bar, beat) tuple. Comparing that
    tuple rather than the bar alone is what makes the fill correct for the
    anacrusis, where a pickup note at bar -1 beat 3 must see a chord that also
    starts at a negative bar.
    """
    rows = connection.execute(
        "SELECT bar, beat, chord FROM beats "
        "WHERE melid = ? AND chord IS NOT NULL AND chord <> '' "
        "ORDER BY bar, beat",
        (melid,),
    ).fetchall()
    return [((int(row["bar"]), float(row["beat"])), row["chord"]) for row in rows]


def _forward_fill(
    timeline: Sequence[Tuple[Tuple[int, float], str]],
    bar: int,
    beat: float,
) -> Optional[str]:
    """The last chord that started at or before (bar, beat), or None.

    The timeline is ordered, so this is a binary search rather than a scan: it
    runs once per note and a long transcription has thousands of them.
    """
    if not timeline:
        return None
    position = (bar, beat)
    low, high = 0, len(timeline) - 1
    found = -1
    while low <= high:
        mid = (low + high) // 2
        if timeline[mid][0] <= position:
            found = mid
            low = mid + 1
        else:
            high = mid - 1
    return timeline[found][1] if found >= 0 else None


def load_solo(melid: int, db_path: Optional[Union[str, Path]] = None) -> Solo:
    """Loads one transcription: metadata plus every note with its chord filled in.

    Notes have no chord column in the database, so each note's active chord is a
    forward fill over the `beats` chord onsets (see `_forward_fill`). A note
    before the first chord gets an empty chord, and any suffix the alias table
    cannot translate is counted in `unmapped_suffixes` rather than guessed.

    Raises ValueError for an unknown melid, so a typo is not silently an empty
    transcription.
    """
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT melid, performer, title, key, signature, avgtempo, style,
                   chord_changes, chorus_count
            FROM solo_info WHERE melid = ?
            """,
            (melid,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No solo_info entry for melid {melid}")

        solo = Solo(
            melid=int(row["melid"]),
            performer=row["performer"] or "",
            title=row["title"] or "",
            key=row["key"] or "",
            signature=row["signature"] or "",
            avgtempo=float(row["avgtempo"] or 0.0),
            style=row["style"] or "",
            chord_changes=row["chord_changes"] or "",
            chorus_count=int(row["chorus_count"] or 0),
        )

        timeline = _chord_timeline(melid, connection)
        note_rows = connection.execute(
            """
            SELECT bar, beat, pitch, duration, onset, tatum
            FROM melody WHERE melid = ? ORDER BY bar, beat, onset
            """,
            (melid,),
        ).fetchall()

    unmapped: Dict[str, int] = {}
    for note_row in note_rows:
        bar = int(note_row["bar"])
        beat = float(note_row["beat"])
        chord = _forward_fill(timeline, bar, beat) or ""
        root, quality, bass = parse_weimar_chord(chord)
        if quality is None and chord and chord != NO_CHORD:
            # Counted by symbol, not by suffix: the suffix is the part that
            # failed to translate, and the symbol is what a reader needs to see.
            unmapped[chord] = unmapped.get(chord, 0) + 1
        solo.notes.append(
            NoteEvent(
                bar=bar,
                beat=beat,
                pitch=int(round(float(note_row["pitch"]))),
                duration=float(note_row["duration"] or 0.0),
                onset=float(note_row["onset"] or 0.0),
                tatum=float(note_row["tatum"] or 0.0),
                chord=chord,
                quality=quality,
                bass=bass,
            )
        )

    solo.unmapped_suffixes = dict(sorted(unmapped.items(), key=lambda kv: (-kv[1], kv[0])))
    return solo


def load_section(
    melid: int,
    selector: str,
    db_path: Optional[Union[str, Path]] = None,
    bars: Optional[Tuple[int, int]] = None,
) -> Tuple[Solo, List[Section]]:
    """Loads a transcription narrowed to the spans a selector matches.

    The chord fill runs over the *whole* transcription before narrowing, so a note
    at the start of a selected span still knows the chord that began in an
    earlier bar - the common case, since most spans start mid-chord.

    `bars` optionally narrows further, as a half-open [lo, hi) range; both bounds
    may be negative for pickup material.

    Returns the narrowed solo (metadata preserved) and the matching sections, so
    the caller can report what was actually selected.
    """
    solo = load_solo(melid, db_path)
    sections = matching_sections(melid, selector, db_path)
    if not sections:
        raise ValueError(f"No section matches {selector!r} for melid {melid}")

    lo = min(s.start for s in sections)
    hi = max(s.end for s in sections)
    if bars is not None:
        lo = max(lo, bars[0])
        hi = min(hi, bars[1])
    solo.notes = solo.notes_in_bars(lo, hi)
    return solo, sections





