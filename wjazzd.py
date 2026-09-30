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

It provides:

* `WEIMAR_QUALITY_ALIASES` / `parse_weimar_chord` - the database's chord notation
  translated into the library's chord qualities, with unmapped suffixes reported
  rather than guessed.
* `list_solos` / `list_sections` / `parse_section_selector` / `load_solo` /
  `load_section` - metadata, span selection and note loading, with each note's
  active chord reconstructed by a forward fill over the `beats` table.
* `select_head` - the head, found on the chord progression rather than the form
  label.
* `skeleton` / `build_skeleton` / `arrange_head` - reducing a head to a playable
  skeleton, choosing its register, and voicing it.

Two defaults were settled by measurement rather than by assumption, and the
numbers are recorded here because they are the reason for the defaults:

* **Skeleton density is `eighths`.** Across 116 sampled heads the median
  voiced-step rate is 85.9% for eighths against 85.6% for sixteenths and 85.7%
  for beats, so the extra density buys no extra playability; eighths keeps 32
  steps where sixteenths keeps 38. `chords` voices everything but yields four
  steps for an eight-bar head, which is a chord list rather than an arrangement.
* **Heads are often lifted an octave.** `--lift auto` compares how much of the
  head each version voices and keeps the better one. On the *trimmed* head this
  fires more often than the plan expected: Blue Train's head voices 51 of 62
  steps as transcribed and 60 of 62 an octave up, so it is lifted, because the
  head dips to Eb3. The plan's "Blue Train is not transposed" figure was
  measured on the untrimmed 79-bar A-block, where those few low notes were
  diluted across 845 notes.

See `CORPUS_PLAN.md` for the measurements the design decisions rest on.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sqlite3
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from arranger import (
    GRIP_PREFERENCE,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    TEXTURE_STYLES,
    ArrangementStep,
    ChordParser,
    Note,
    VoiceLeadingEngine,
)
from arranger.diagnostics import Diagnostics, default_diagnostics
from arranger.options import ArrangeOptions

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
    "HeadSelection",
    "select_head",
    "Skeleton",
    "build_skeleton",
    "arrange_slots",
    "arrange_head",
    "promote_slash_chord",
    "corpus_cli",
    "parse_bar_range",
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
    when the suffix is unmapped. `tatum` is the note's position within its beat
    (1-based) and `division` how many tatums a beat is divided into, which is
    what the rhythmic skeletons derive their grid from.
    """

    bar: int
    beat: float
    pitch: int
    duration: float
    onset: float = 0.0
    tatum: float = 0.0
    division: int = 4
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
            SELECT bar, beat, pitch, duration, onset, tatum, division
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
                division=int(note_row["division"] or 4),
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


# ---------------------------------------------------------------------------
# Head selection
# ---------------------------------------------------------------------------

# Bounds on the head search. MIN_HEAD_BARS is an empirical floor, not a musical
# constant: 4 is where a head stops being a fragment (a 4-bar slice of a diatonic
# progression recurs inside almost any standard, so 4 matches by coincidence),
# while 6 is the shortest span that did not do so across the corpus. MAX_HEAD_BARS
# bounds the search so a 1352-bar A-block cannot produce a useless scan.
MIN_HEAD_BARS = 6
MAX_HEAD_BARS = 64

# How many bars two statements of the same progression may differ in. Analysts do
# not enter every change a piece is usually written with - Konitz's ATTYA omits the
# G7 of bar 6 - so an exact match fails on real transcriptions. One is enough to
# recognise a statement; two also matches unrelated progressions, so this stays 1.
REPEAT_TOLERANCE = 1

# How far back from an A-block to look for the intro that may contain the head,
# and how much of a gap between the two still counts as contiguous. The slack is
# small on purpose: an intro ending fourteen bars before the A-block is a
# different section, not a prefix of the head.
MAX_INTRO_BARS = 16
INTRO_CONTIGUITY_SLACK = 2


@dataclass(frozen=True)
class HeadSelection:
    """A head, plus what was selected and why.

    `section` is the head itself as a bar span. `seed` is the A-block it was found
    through (or None when there was no A-form at all), `anchor_chords` the chord
    progression the head was cut on, and `degraded`/`note` report the degenerate
    cases the selector detected rather than crashing on them.
    """

    melid: int
    section: Section
    seed: Optional[Section] = None
    anchor_chords: Tuple[str, ...] = ()
    degraded: bool = False
    note: str = ""

    @property
    def start(self) -> int:
        return self.section.start

    @property
    def end(self) -> int:
        return self.section.end

    @property
    def length(self) -> int:
        return self.section.length

    def describe(self) -> str:
        """One line naming the melid, the bars, and the anchor progression."""
        chords = " ".join(self.anchor_chords) if self.anchor_chords else "no chords"
        suffix = f" [{self.note}]" if self.note else ""
        return (
            f"melid {self.melid}: head at bars {self.start}-{self.end - 1} "
            f"({self.length} bars), anchored on {chords}{suffix}"
        )


def _form_sections(melid: int, db_path: Optional[Union[str, Path]] = None) -> List[Section]:
    """FORM spans of a transcription, ordered by start bar."""
    return sorted(list_sections(melid, type="FORM", db_path=db_path), key=lambda s: s.start)


def _seed_span(forms: Sequence[Section]) -> Optional[Tuple[Section, int, int]]:
    """The span to search for a head: the first A-block, extended back over intros.

    Returns (seed_section, lo, hi). The extension is the important part: the `I`
    (intro) block routinely *contains* the head, with `A1` starting at the second
    statement - on all four "All the Things You Are" transcriptions the real
    8-bar head sits in the intro, before `A1` begins. Extension stops at the first
    bar no preceding I-block reaches, and is bounded by MAX_INTRO_BARS so a
    distant intro cannot swallow the head.

    Returns None when the transcription has no A-form at all.
    """
    a_block = next((f for f in forms if f.value.upper().startswith("A")), None)
    if a_block is None:
        return None

    lo = a_block.start
    extended = True
    while extended:
        extended = False
        for form in forms:
            if not form.value.upper().startswith("I"):
                continue
            # The intro must actually reach the A-block, allowing a bar or two of
            # slack since analysts do not always label spans contiguously. Without
            # the slack requirement an unrelated intro far earlier would be
            # absorbed and the seed would start at the top of the piece.
            reaches = form.end >= lo - INTRO_CONTIGUITY_SLACK
            if form.start < lo and lo - form.length <= MAX_INTRO_BARS and reaches:
                lo = form.start
                extended = True
    return a_block, lo, a_block.end


def _bar_grid(solo: Solo, lo: int, hi: int) -> Dict[int, Optional[Tuple[Tuple[str, int], ...]]]:
    """Per-bar chords of a span as (quality, root pitch class), from the forward fill.

    A bar-grid rather than a list of changes, because a chord routinely lasts two
    bars and transcriptions are not consistent about it: ATTYA's A section is
    written as eight changes, but Konitz enters seven of them with `Cj7` held for
    two bars. Comparing change *lists* therefore fails to line the two statements
    up at all, while comparing bar-by-bar lines them up and lets the one
    disagreeing bar be tolerated.

    Each bar holds a *tuple* of chords, because two changes can share a bar. Sims's
    ATTYA puts `D-7` and `G7` both in bar 6; keeping only the first of them loses
    the `G7`, and the statement then fails to match its own return. A tuple keeps
    every change, and the single-chord case - nearly every bar - is unchanged.
    """
    by_bar: Dict[int, List[Tuple[str, int]]] = {}
    nc_bars: set = set()
    for bar, chord in solo.chords():
        if bar >= hi:
            break
        if bar < lo:
            continue
        if chord == NO_CHORD:
            nc_bars.add(bar)
            continue
        root, quality, _ = parse_weimar_chord(chord)
        if root is not None and quality is not None:
            by_bar.setdefault(bar, []).append((quality, Note(root + "4").midi_note() % 12))

    # Bars with no change of their own carry the previous bar's harmony forward,
    # which is exactly what the forward fill means. An NC bar is recorded as None
    # rather than inheriting: it is genuinely unaccompanied, and the repeat test
    # treats it as a wildcard rather than as a chord carried forward.
    grid: Dict[int, Optional[Tuple[Tuple[str, int], ...]]] = {}
    running: Optional[Tuple[Tuple[str, int], ...]] = None
    for bar in range(lo, hi):
        if bar in by_bar:
            running = tuple(by_bar[bar])
        grid[bar] = None if bar in nc_bars else running
    return grid


def _is_transposed_repeat(
    grid: Mapping[int, Optional[Tuple[Tuple[str, int], ...]]],
    start: int,
    period: int,
    hi: int,
    tolerance: int = 1,
) -> bool:
    """True when the `period` bars at `start` are restated at `start + period`.

    Matching is modulo transposition: chord *qualities* must agree and every root
    must move by one constant interval. Comparing qualities alone is too weak - a
    blues head is nearly all dominant sevenths, so it would match itself at every
    offset - while comparing absolute roots is too strict, because the same
    progression recurs in a new key in the later sections of a modulating form.

    `tolerance` is how many chords the two statements may differ by, which real
    transcriptions require: analysts do not enter every change a piece is usually
    written with. Konitz's ATTYA omits the `G7` of bar 6, so an exact match fails
    on all four transcriptions; one is enough to recognise a statement, and two
    also matches unrelated progressions, so the default stays at one.

    An unaccompanied bar is a wildcard rather than a mismatch, so the `NC` bars of
    an intro cannot decide whether a progression repeats. A bar that is *absent*
    from the grid is not a wildcard: that means the span ran out, which the bound
    above has already excluded.
    """
    if start + 2 * period > hi:
        return False

    transpose: Optional[int] = None
    differences = 0
    for offset in range(period):
        first = grid.get(start + offset, ())
        second = grid.get(start + period + offset, ())
        if first is None or second is None:
            continue
        # Pair the chords of the two bars in order, which is exact whenever they
        # hold the same number of changes and tolerant when one has an extra.
        for (quality_a, root_a), (quality_b, root_b) in zip(first, second):
            if quality_a == quality_b:
                shift = (root_b - root_a) % 12
                if transpose is None:
                    transpose = shift
                elif shift != transpose:
                    # Same quality, different root: a genuine harmonic difference
                    # (an altered dominant against a plain one), not a dropped
                    # change, so this is not a candidate repeat at all.
                    return False
            else:
                differences += 1
                if differences > tolerance:
                    return False
        # Chords present in one bar but not the other are dropped changes.
        differences += abs(len(first) - len(second))
        if differences > tolerance:
            return False
    return True



def select_head(melid: int, db_path: Optional[Union[str, Path]] = None) -> Optional[HeadSelection]:
    """Selects the head of a transcription - the tune, as distinct from the solo.

    The head is found on the **chord progression, not the form label**, because
    the label is unreliable: on all four "All the Things You Are" transcriptions
    `FORM A1` starts at the *second* statement, and the real 8-bar head lies
    inside the preceding `I` (intro) block, before `A1` begins.

    The algorithm, in order:

    1. **Seed** from the first `FORM` A-block, extended backwards over any
       contiguous preceding `I` block. This alone recovers all four ATTYA heads.
    2. **Anchor** on the chord progression at the seed's first chord bar.
    3. **Trim** to the shortest span that is then repeated - the first
       transposed repeat of the anchor progression. This is what makes the result
       a *head* rather than a form cycle: it cuts a 35-99 bar A-block down to one
       statement.
    4. **Report** the anchor chords and the trimmed length, so the caller can see
       what was chosen and override it with an explicit bar range.

    Returns None when the transcription has no A-form. Degenerate A-forms are
    reported through `HeadSelection.degraded` and `note` rather than crashing: a
    zero-length or sub-4-bar block, a block over-long enough that the user should
    hear about it first, and a progression that never repeats.

    Known limitation: the trim is a heuristic and does not land on the head for
    every transcription. On the four "All the Things You Are" transcriptions it
    finds the 8-bar head on 266 and 342, but returns a 6-bar fragment on 328 and
    falls back to the whole A-block on 451, whose A section the analyst wrote with
    fewer changes than the head has bars. Across the corpus 434 of 456
    transcriptions yield a head and the median length is 8 bars, which is what a
    head should be, but a user wanting a specific tune should pass an explicit bar
    range. This is the open question CORPUS_PLAN.md section 12 records about how
    aggressive the progression trim should be.
    """
    forms = _form_sections(melid, db_path)
    seeded = _seed_span(forms)
    if seeded is None:
        return None
    seed, lo, hi = seeded

    notes: List[str] = []
    degraded = False
    if seed.length < MIN_HEAD_BARS:
        degraded = True
        notes.append(f"degenerate A-block ({seed.value}, bars {seed.start}-{seed.end})")
    elif seed.length > MAX_HEAD_BARS:
        notes.append(f"A-block is {seed.length} bars; trimmed to one statement")

    solo = load_solo(melid, db_path)
    grid = _bar_grid(solo, lo, hi)
    bars = [bar for bar, cell in grid.items() if cell]
    if not bars:
        return None

    # Search every bar as a candidate start, earliest first, and at each one take
    # the *shortest* span that recurs. Both halves of that ordering matter:
    #
    # * Earliest-first skips the anacrusis. ATTYA's pickups run bars -12..-1 and
    #   bar 0 holds the turnaround back into the tune, so the seed's first chord is
    #   the tail of the previous section, not the head. The head is the first bar
    #   that begins a progression which then repeats.
    # * Shortest-at-each-bar keeps the result one statement rather than a form
    #   cycle. ATTYA's whole 36-bar form is itself periodic, so searching for the
    #   longest repeat anywhere returns 36 bars; the 8-bar A section is the head.
    longest = min(MAX_HEAD_BARS, (hi - bars[0]) // 2)
    start: Optional[int] = None
    period: Optional[int] = None
    for bar in bars:
        found = next(
            (
                p
                for p in range(MIN_HEAD_BARS, min(longest, (hi - bar) // 2) + 1)
                if _is_transposed_repeat(grid, bar, p, hi, REPEAT_TOLERANCE)
            ),
            None,
        )
        if found is not None:
            start, period = bar, found
            break

    if start is None or period is None:
        # Nothing recurs, so the head cannot be cut from a repeat. Fall back to
        # the A-block itself and say so, rather than inventing a length.
        degraded = True
        notes.append("no repeated progression found; using the whole A-block")
        start, end = seed.start, seed.end
    else:
        # The head runs up to the bar where the restatement begins, so an 8-bar
        # head starting at bar 1 ends at bar 9.
        end = start + period

    if end <= start:
        return None

    anchor = tuple(chord for bar, chord in solo.chords() if start <= bar < end)[:16]
    head = Section(melid=melid, type="FORM", start=start, end=end, value="head")
    return HeadSelection(
        melid=melid,
        section=head,
        seed=seed,
        anchor_chords=anchor,
        degraded=degraded,
        note="; ".join(notes),
    )


# ---------------------------------------------------------------------------
# Slash chords
# ---------------------------------------------------------------------------

# The chord qualities that are triads, and so can be promoted to a seventh chord
# when the notation implies one (rule B).
_TRIAD_QUALITIES = ("maj", "m")

# Which seventh a triad becomes when its bass note is the seventh, keyed by the
# triad's own quality. A minor triad over a minor seventh is m7, a major triad
# over a major seventh is maj7.
_TRIAD_PROMOTION = {"m": "m7", "maj": "maj7"}


def promote_slash_chord(root: str, quality: str, bass: Optional[str]) -> str:
    """Rule B: promotes a triad to a seventh chord when the bass implies one.

    The database writes `A-/G`, `C-/Bb` and `D/C` for what a musician reads as
    Am7/G, Cm7/Bb and Dm7/C: a triad whose bass is its own seventh. Naming the
    seventh makes the melody note a chord tone instead of an unresolved tension,
    and it recovers the largest group of otherwise inexplicable basses.

    Triads with any other bass, and every non-triad quality, pass through
    unchanged. A pedal or an inverted bass is honoured by `bass_pitch_class`
    instead, which is a preference rather than a change of chord.
    """
    if bass is None or quality not in _TRIAD_QUALITIES:
        return quality
    root_pc = Note(root + "4").midi_note() % 12
    bass_pc = Note(bass + "4").midi_note() % 12
    if (bass_pc - root_pc) % 12 == 10:  # the seventh
        return _TRIAD_PROMOTION[quality]
    return quality


def bass_pitch_class(bass: Optional[str]) -> Optional[int]:
    """Rule C: the pitch class a slash bass asks for, or None when there is none."""
    if bass is None:
        return None
    return Note(bass + "4").midi_note() % 12


def bass_cost(voicing_midis: Sequence[int], bass_pc: Optional[int]) -> int:
    """How far a voicing's lowest sounding pitch is from the requested bass.

    In semitones, as the smallest interval from the bass pitch class to the
    lowest note actually played. Zero means the bass is in the voicing; 6 means
    it is a tritone away. Used only to *prefer* one candidate over another, so a
    voicing that cannot honour the bass is still usable.
    """
    if bass_pc is None or not voicing_midis:
        return 0
    lowest = min(voicing_midis) % 12
    direct = abs(lowest - bass_pc)
    return min(direct, 12 - direct)


# ---------------------------------------------------------------------------
# Skeletons - reducing a transcribed line to a playable skeleton
# ---------------------------------------------------------------------------

# The five reduction strategies, coarsest first. A drop-2 voicing is a per-beat
# object, so a head has to be thinned before it can be arranged: a raw head runs
# to 10.7 notes per bar, which is not an arrangement.
SKELETON_STRATEGIES = ("chords", "beats", "eighths", "sixteenths", "notes")

# Which note represents a slot when several notes share it.
SLOT_PICKS = ("first", "longest")

# How a head may be transposed into the library's playable register.
#
# `auto` (the default) is the coverage comparison: build the head as transcribed
# and again an octave up, and keep whichever voices more steps, with ties going
# to the original. It is self-correcting and threshold-free, so it cannot be
# defeated by a median sitting one semitone above an arbitrary cut-off, and it
# cannot move music that was already fine.
#
# `always` and `per-note` are there for when the user knows better. `per-note` is
# opt-in only: lifting single notes tears the line apart, turning a descending
# 3rd into a descending 10th.
LIFT_MODES = ("auto", "none", "always", "per-note")

# An octave is the only transposition considered: the library's window is B3-Bb5,
# so a head is either an octave too low or already in reach.
LIFT_SEMITONES = 12

# The library's melody floor, B3. Notes below it are unplayable and get skipped.
MELODY_FLOOR = 59


@dataclass
class Skeleton:
    """A reduced line, ready to arrange, with the diagnostics behind it.

    `triples` are the (note, quality, name) tuples for arrange_progression.
    `lift` is the transposition applied to reach them and `lift_mode` how that was
    decided. `coverage` and `coverage_lifted` record how many steps each version
    voiced - the measurement `auto` is defined by. `rescued` is how many steps a
    diminished retry would have rescued, reported whether or not the retry is
    enabled, so a user can see what they are missing without opting in.
    """

    triples: List[Tuple[str, str, str]] = field(default_factory=list)
    lift: int = 0
    lift_mode: str = "none"
    coverage: Tuple[int, int] = (0, 0)
    coverage_lifted: Tuple[int, int] = (0, 0)
    rescued: int = 0
    notes: Tuple[str, ...] = ()
    # Each slot's (bar, beat, duration), in the same order as `triples`, so a
    # renderer can place the chords on their real beats instead of one per cell.
    # Parallel to `triples` by construction: the lift transposes melody notes
    # but never drops or reorders a slot, and the diminished fallback in
    # arrange_head acts per step.
    timings: Tuple[Tuple[int, float, Optional[float]], ...] = ()

    def __len__(self) -> int:
        return len(self.triples)

    def __iter__(self):
        return iter(self.triples)


def midi_to_note_name(pitch: int) -> str:
    """MIDI number to a note name, spelled with flats.

    Flats because the database's keys and chord symbols are flat-based (Eb, Bb,
    Ab), so a flat spelling is the one that reads correctly next to them.
    """
    pitch = int(round(pitch))
    return f"{PITCH_CLASS_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _slot_key(note: NoteEvent, strategy: str) -> Tuple[int, float, int]:
    """The (bar, beat, subdivision) key a note occupies under a strategy.

    The grid is derived from each note's own `tatum` and `division` rather than
    assumed to be 4/4 sixteenths: a transcription in division 3 is in triplets,
    and one in division 2 has no eighths at all. Bars are signed, so pickup
    material orders correctly with no special case.
    """
    if strategy == "beats":
        return (note.bar, note.beat, 0)
    if strategy == "eighths":
        # Two tatums make an eighth. In a triplet division there is no eighth, so
        # the tatum is used as-is rather than inventing a division that is not there.
        step = 2 if note.division and note.division % 2 == 0 else 1
        return (note.bar, note.beat, int((note.tatum - 1) // step))
    if strategy == "sixteenths":
        return (note.bar, note.beat, int(note.tatum - 1))
    # "notes" keeps every note: each gets a slot of its own, ordered by onset.
    return (note.bar, note.beat, int(round(note.onset * 1000)))


def _chord_slots(solo: Solo, lo: int, hi: int) -> List[Tuple[int, float, int]]:
    """One slot per chord change, at the bar the change starts.

    The `chords` skeleton is the written harmony rather than the melody: it is
    the natural reading of a slow tune, where the head moves roughly once per bar.
    """
    slots: List[Tuple[int, float, int]] = []
    for bar, chord in solo.chords():
        if lo <= bar < hi and chord != NO_CHORD:
            slots.append((bar, 1.0, 0))
    return slots


def skeleton_slots(
    solo: Solo,
    strategy: str = "beats",
    section: Optional[Tuple[int, int]] = None,
    pick: str = "first",
) -> List[Tuple[Tuple[str, str, str], int, float, Optional[float]]]:
    """As `skeleton`, but each slot keeps its timing: (triple, bar, beat, duration).

    **The slot's `duration` is `None`, deliberately.** The database's
    `melody.duration` column is a *performance measurement* in beats - a 0.21 is a
    triplet eighth, a 1.75 a note held through a bar line - and it is not a notated
    note value. It is not a length any renderer can use, so it is not offered as one:
    the staff renderer spaces the slots on their own `bar` and `beat`, and the
    notated rhythm comes from the onsets.

    This matters because `tabxml._events` *caps* a step's span by its `duration` to
    stop a note being held across a rest, and a cap is only meaningful against a
    written length. Handing it a performance measurement truncated every corpus step
    to a fraction of its real length: the 8-bar head of melid 106 came out with 44
    rests to 31 notes, each chord a sixteenth stub, because a 0.015 whole note is a
    60-millisecond ornament. `headxml` is the loader whose `duration` is notated, and
    it is the one that supplies one.

    One voicing is generated per *slot*, and the strategy decides what a slot is:
    a chord change, a beat, an eighth, a sixteenth, or a single note. That is the
    whole reduction mechanism - the line is thinned to the density the strategy
    names, and what remains is arranged as chord-melody.

    `section` is a half-open (start, end) bar range, normally the head from
    `select_head`; it defaults to the whole transcription. `pick` chooses which
    note represents a slot holding several: `first` (the default, and almost
    always the only one on a sixteenth grid) or `longest`, which favours the
    sustained note and is useful on the beat grid.

    An `NC` bar becomes a melody-only step, carried through as the literal "NC"
    so `arrange_progression` short-circuits it instead of inventing a harmony.
    A chord whose suffix the alias table could not translate is skipped, because
    there is no quality to hand the engine and guessing one is worse than a gap.
    """
    if strategy not in SKELETON_STRATEGIES:
        raise ValueError(f"Unknown skeleton strategy {strategy!r}; expected one of {SKELETON_STRATEGIES}")
    if pick not in SLOT_PICKS:
        raise ValueError(f"Unknown slot pick {pick!r}; expected one of {SLOT_PICKS}")

    lo, hi = section if section is not None else solo.bars
    notes = [n for n in solo.notes if lo <= n.bar < hi]
    if not notes:
        return []

    if strategy == "chords":
        wanted = set(_chord_slots(solo, lo, hi))
        groups: Dict[Tuple[int, float, int], List[NoteEvent]] = {}
        for note in notes:
            key = _slot_key(note, "beats")
            if key in wanted:
                groups.setdefault(key, []).append(note)
        ordered = [k for k in sorted(groups)]
    else:
        groups = {}
        for note in notes:
            groups.setdefault(_slot_key(note, strategy), []).append(note)
        ordered = sorted(groups)

    slots: List[Tuple[Tuple[str, str, str], int, float, Optional[float]]] = []
    for key in ordered:
        candidates = groups[key]
        chosen = max(candidates, key=lambda n: n.duration) if pick == "longest" else candidates[0]
        chord = chosen.chord
        # `duration` is None on purpose: the database's own value is a performance
        # measurement in beats, not a notated length, and `_events` caps a span by
        # this field. See the docstring.
        length: Optional[float] = None
        if chord == NO_CHORD:
            slots.append(
                ((midi_to_note_name(chosen.pitch), NO_CHORD, NO_CHORD), chosen.bar, chosen.beat, length)
            )
            continue
        if not chord or chosen.quality is None:
            # No chord, or a suffix the notation table does not translate.
            continue
        root, quality, bass = parse_weimar_chord(chord)
        if root is None or quality is None:
            continue
        promoted = promote_slash_chord(root, quality, bass)
        slots.append(
            ((midi_to_note_name(chosen.pitch), promoted, chord), chosen.bar, chosen.beat, length)
        )
    return slots


def skeleton(
    solo: Solo,
    strategy: str = "beats",
    section: Optional[Tuple[int, int]] = None,
    pick: str = "first",
) -> List[Tuple[str, str, str]]:
    """Reduces a transcribed line to the (note, quality, name) triples to arrange.

    This is `skeleton_slots` with the timing discarded, kept as the plain public
    reduction because that is all most callers need.
    """
    return [triple for triple, _, _, _ in skeleton_slots(solo, strategy, section, pick)]


def _transpose(triples: Sequence[Tuple[str, str, str]], semitones: int) -> List[Tuple[str, str, str]]:
    """Moves every melody note by `semitones`, leaving the harmony alone.

    Transposing the whole unit at once cannot distort an interval: a uniform
    transposition leaves every melodic interval exactly as transcribed. That is
    why the lift is applied to a whole head rather than to individual notes.
    """
    if not semitones:
        return list(triples)
    moved: List[Tuple[str, str, str]] = []
    for note, quality, name in triples:
        if quality == NO_CHORD:
            moved.append((note, quality, name))
            continue
        moved.append((midi_to_note_name(Note(note).midi_note() + semitones), quality, name))
    return moved


def _voice_coverage(
    triples: Sequence[Tuple[str, str, str]],
    non_chord_tone: str = "extension",
) -> Tuple[int, int]:
    """How many steps of a progression the engine can actually voice.

    (voiced, attempted). Measured by arranging with stdout captured, because
    arrange_progression reports an unvoiceable step by warning and skipping it
    rather than raising - and the whole point of the lift is that comparison.
    """
    if not triples:
        return (0, 0)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        steps = VoiceLeadingEngine.arrange_progression(list(triples), non_chord_tone=non_chord_tone)
    return (len(steps), len(triples))


def unresolved_steps(
    triples: Sequence[Tuple[str, str, str]],
    non_chord_tone: str = "extension",
) -> List[int]:
    """Indexes of steps no non-chord-tone strategy could resolve.

    These are the steps a diminished retry would have to rescue: the melody is
    not a chord tone, and neither `extension` nor the strategy in force maps it
    onto a substitute. Reported so a user can see what `--fallback diminished`
    would buy without enabling it.
    """
    unresolved: List[int] = []
    for index, (note, quality, name) in enumerate(triples):
        if quality == NO_CHORD or not name:
            continue
        melody = Note(note)
        if VoiceLeadingEngine.is_chord_tone(melody, quality, name):
            continue
        if non_chord_tone == "legacy":
            continue
        resolved = VoiceLeadingEngine.resolve_non_chord_tone(melody, quality, name, non_chord_tone)
        if resolved is None:
            unresolved.append(index)
    return unresolved


def build_skeleton(
    solo: Solo,
    strategy: str = "eighths",
    section: Optional[Tuple[int, int]] = None,
    pick: str = "first",
    lift: str = "auto",
    non_chord_tone: str = "extension",
) -> Skeleton:
    """Reduces a head to a playable skeleton, transposing it if that helps.

    The reduction itself is `skeleton`; this adds the register decision and the
    diagnostics. `lift` is one of LIFT_MODES, and `auto` - the default - keeps
    the +12 version only when it voices strictly more steps than the original.
    Ties go to the original, so music is never moved without a gain.

    The cost of `auto` is that the head is voiced twice. That is cheap next to
    being wrong: the alternative rule, "lift when the median is below B3", is
    defeated by a head whose median sits one or two semitones above the
    threshold while half of it is unplayable.
    """
    if lift not in LIFT_MODES:
        raise ValueError(f"Unknown lift mode {lift!r}; expected one of {LIFT_MODES}")

    slots = skeleton_slots(solo, strategy, section, pick)
    base = [triple for triple, _, _, _ in slots]
    timings = tuple((bar, beat, duration) for _, bar, beat, duration in slots)
    notes: List[str] = []
    coverage = _voice_coverage(base, non_chord_tone)
    if lift == "none":
        return Skeleton(base, 0, "none", coverage, coverage, 0, tuple(notes), timings)

    raised = _transpose(base, LIFT_SEMITONES)
    coverage_lifted = _voice_coverage(raised, non_chord_tone)

    if lift == "always":
        return Skeleton(raised, LIFT_SEMITONES, "always", coverage, coverage_lifted, 0, tuple(notes), timings)
    if lift == "per-note":
        # Lift only the notes the library cannot play. This is the mode the plan
        # warns tears the line, kept because it is occasionally what is wanted.
        mixed = [
            (midi_to_note_name(Note(n).midi_note() + LIFT_SEMITONES) if Note(n).midi_note() < MELODY_FLOOR else n, q, c)
            for n, q, c in base
        ]
        notes.append("per-note lift can distort melodic intervals")
        return Skeleton(mixed, LIFT_SEMITONES, "per-note", coverage, coverage_lifted, 0, tuple(notes), timings)

    # auto: keep the octave only when it demonstrably voices more of the head.
    if coverage_lifted[0] > coverage[0]:
        notes.append(f"lifted an octave: {coverage[0]} -> {coverage_lifted[0]} of {coverage[1]} steps voiced")
        return Skeleton(raised, LIFT_SEMITONES, "auto", coverage, coverage_lifted, 0, tuple(notes), timings)
    notes.append(f"left in register: {coverage[0]} of {coverage[1]} steps voiced, no better an octave up")
    return Skeleton(base, 0, "auto", coverage, coverage_lifted, 0, tuple(notes), timings)


@dataclass
class HeadArrangement:
    """An arranged head, with everything the caller needs to explain it."""

    steps: List[ArrangementStep] = field(default_factory=list)
    skeleton: Skeleton = field(default_factory=Skeleton)
    head: Optional[HeadSelection] = None
    rescued: Tuple[int, ...] = ()
    notes: Tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.steps)


# A bar range is an optionally negative LO, a hyphen, and an optionally negative
# HI. Both bounds may be negative at once ("-8--1"), so the two numbers are pulled
# out by pattern rather than by splitting on a hyphen, which cannot tell a
# separator from a minus sign. Whitespace is allowed because a quoted shell
# argument commonly carries it.
_BAR_RANGE_RE = re.compile(r"^\s*(-?\d+)\s*(?:-\s*(-?\d+))?\s*$")


def parse_bar_range(text: str) -> Tuple[int, Optional[int]]:
    """Parses a "LO-HI" bar range, half-open, with signed bounds.

        '0-8'   -> (0, 8)
        '-4-8'  -> (-4, 8)     the anacrusis, as a negative LO
        '12'    -> (12, None)  open-ended; the section's own end applies
        '-8--1' -> (-8, -1)    a range that lies entirely in the pickups

    Negative bounds are ordinary, not malformed: 1,335 `beats` rows across 149
    transcriptions sit below bar 0, reaching bar -31, and the ATTYA pickups live
    there.
    """
    match = _BAR_RANGE_RE.match((text or "").strip())
    if match is None:
        raise ValueError(f"Invalid bar range {text!r}; expected LO-HI, e.g. '0-8' or '-4-8'")
    lo = int(match.group(1))
    hi = int(match.group(2)) if match.group(2) is not None else None
    if hi is not None and hi <= lo:
        raise ValueError(f"Bar range {text!r} is empty; HI must be greater than LO")
    return (lo, hi)


def corpus_cli(argv: Optional[Sequence[str]] = None) -> int:
    """The `corpus` command: render a head from the Weimar Jazz Database.

    Returns a process exit code. Defaults follow the decisions in
    CORPUS_PLAN.md: the head is the default selection, the register is decided
    by measured coverage, the non-chord-tone strategy is `extension`, and the
    diminished retry is off because it replaces the written chord.

    Nothing here is required to use the library - this is a thin front end over
    `select_head` and `arrange_head`.
    """
    import argparse

    from arranger import (
        format_progression,
        format_tab_staff,
        write_gp5,
        write_musicxml,
        write_tab_html,
    )

    parser = argparse.ArgumentParser(
        prog="arranger.py corpus",
        description="Render the head of a Weimar Jazz Database transcription as chord-melody.",
    )
    parser.add_argument("--melid", type=int, default=None, help="transcription id (melid)")
    parser.add_argument(
        "--list", action="store_true", help="list the 456 transcriptions and exit"
    )
    parser.add_argument(
        "--section",
        default=None,
        help="a span selector such as form:A1, chorus:1, phrase:2, idea:lick; "
             "a * glob is allowed. Defaults to the head.",
    )
    parser.add_argument(
        "--bars",
        default=None,
        help="narrow to a half-open LO-HI bar range; bounds may be negative for pickups",
    )
    parser.add_argument("--skeleton", choices=SKELETON_STRATEGIES, default="eighths")
    parser.add_argument("--pick", choices=SLOT_PICKS, default="first")
    parser.add_argument("--lift", choices=LIFT_MODES, default="auto")
    parser.add_argument(
        "--non-chord-tone",
        choices=VoiceLeadingEngine.NON_CHORD_TONE_STRATEGIES,
        default="extension",
    )
    parser.add_argument(
        "--fallback",
        choices=["diminished"],
        default=None,
        help="retry unresolved tensions as dim7 substitutions; replaces the written chord",
    )
    parser.add_argument(
        "--texture",
        choices=list(TEXTURE_STYLES),
        default="uniform",
        help=(
            "'targets' states a full chord on beats 1 and 3 and fills the notes "
            "between with a shell, a 3rd/6th or the melody alone; 'uniform' (the "
            "default) voices every note in full"
        ),
    )
    parser.add_argument(
        "--fret-min",
        type=int,
        default=NECK_FRET_MIN,
        help=f"lowest fret the selector aims for (default {NECK_FRET_MIN})",
    )
    parser.add_argument(
        "--fret-max",
        type=int,
        default=NECK_FRET_MAX,
        help=f"highest fret the selector aims for (default {NECK_FRET_MAX})",
    )
    parser.add_argument(
        "--grips",
        nargs="+",
        choices=GRIP_PREFERENCE,
        default=list(GRIP_PREFERENCE),
        help="grip families to use, most preferred first (default: all of them)",
    )
    parser.add_argument("--vertical", action="store_true", help="six-line tab per step")
    parser.add_argument(
        "--tab",
        choices=["line", "staff"],
        default="line",
        help="'staff' lays the head on one six-line staff, spaced on its real "
             "rhythm; 'line' (the default) keeps one line per chord",
    )
    parser.add_argument(
        "--melody",
        action="store_true",
        help="with --tab staff, add a line of melody note names",
    )
    parser.add_argument(
        "--mutes",
        action="store_true",
        help="with --tab staff, spell out the unsounded strings as x",
    )
    parser.add_argument(
        "--bars-per-line", type=int, default=4, help="with --tab staff, bars per line"
    )
    parser.add_argument(
        "--html",
        default=None,
        metavar="PATH",
        help="also write the head to PATH as a self-contained HTML page "
             "(e.g. --html head.html), and say where it went",
    )
    parser.add_argument(
        "--musicxml",
        default=None,
        metavar="PATH",
        help="also write the head to PATH as MusicXML, for a notation program "
             "(e.g. --musicxml head.musicxml). A notation staff only; for the "
             "fingering use --gp5. Needs the optional extra: "
             "pip install 'jazz-arranger[xml]'",
    )
    parser.add_argument(
        "--gp5",
        default=None,
        metavar="PATH",
        help="also write the head to PATH as a Guitar Pro 5 file "
             "(e.g. --gp5 head.gp5). Needs the optional extra: "
             "pip install 'jazz-arranger[gp]'",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list:
        for solo in list_solos():
            print(f"{solo.melid:>4}  {solo.performer:<22} {solo.title}")
        return 0

    if args.melid is None:
        parser.error("--melid is required unless --list is given")

    solo = load_solo(args.melid)
    head: Optional[HeadSelection] = None
    section: Optional[Tuple[int, int]] = None
    if args.section:
        try:
            matched = matching_sections(args.melid, args.section)
        except ValueError as error:
            # A bad selector is a usage error, so report it as one rather than
            # letting a ValueError traceback reach the user.
            parser.error(str(error))
        if not matched:
            parser.error(f"no section matches {args.section!r} for melid {args.melid}")
        section = (min(s.start for s in matched), max(s.end for s in matched))
    else:
        head = select_head(args.melid)
        if head is not None:
            section = (head.start, head.end)

    if args.bars:
        # An explicit range *overrides* the selected span rather than being
        # intersected with it. Intersecting is the narrower reading, but it makes
        # the negative bounds unreachable in the default path: the head starts at
        # bar 1, so --bars -4-2 would silently clamp to bar 1 and the pickups
        # could never be rendered. Being explicit about bars should win.
        try:
            lo, hi = parse_bar_range(args.bars)
        except ValueError as error:
            parser.error(str(error))
        first, last = solo.bars
        section = (max(first, lo), last if hi is None else min(last, hi))

    if args.fret_min > args.fret_max:
        parser.error("--fret-min must not be above --fret-max")

    arrangement = arrange_head(
        solo,
        head,
        strategy=args.skeleton,
        pick=args.pick,
        lift=args.lift,
        non_chord_tone=args.non_chord_tone,
        fallback=args.fallback,
        section=section,
        grips=tuple(args.grips),
        texture=args.texture,
    )

    print(f"{solo.title} - {solo.performer} (melid {solo.melid}, {solo.key})")
    if head is not None:
        print(f"  {head.describe()}")
    if args.section and section is not None:
        print(f"  section {args.section}: bars {section[0]}-{section[1] - 1}")
    notes = getattr(arrangement, "notes", ())
    print(
        f"  neck window: frets {args.fret_min}-{args.fret_max}"
        f" (a preference, not a constraint); grips: {', '.join(args.grips)}"
    )
    if args.texture == "targets":
        # Reported the way --lift is: the reader should be able to see what the
        # arrangement did and why, rather than infer it from a thin bar.
        print(
            "  texture: targets - a full chord on beats 1 and 3, a shell, a 3rd/6th "
            "or the melody alone elsewhere"
        )
    for note in notes:
        print(f"  note: {note}")
    if arrangement.skeleton.rescued and not args.fallback:
        print(
            f"  note: {arrangement.skeleton.rescued} unresolved tension(s) could be "
            f"rescued with --fallback diminished, which replaces the written chord"
        )
    print()
    if args.tab == "staff":
        # The staff is the only renderer that uses the step timing, so it is the
        # one that can show where a chord actually falls in the bar.
        print(
            format_tab_staff(
                arrangement.steps,
                measures_per_line=args.bars_per_line,
                show_melody=args.melody,
                show_mutes=args.mutes,
            )
        )
    else:
        print(format_progression(arrangement.steps, vertical=args.vertical))

    if args.html:
        # The HTML page carries the diagnostics the terminal output prints above,
        # so the saved file explains itself without this run's log.
        provenance = list(arrangement.notes)
        if arrangement.skeleton.rescued and not args.fallback:
            provenance.append(
                f"{arrangement.skeleton.rescued} unresolved tension(s) could be "
                f"rescued with --fallback diminished, which replaces the written chord"
            )
        written = write_tab_html(
            arrangement.steps,
            args.html,
            title=solo.title or f"melid {solo.melid}",
            subtitle=f"{solo.performer} - {solo.key}".strip(" -"),
            measures_per_line=args.bars_per_line,
            show_melody=args.melody,
            show_mutes=args.mutes,
            notes=provenance,
        )
        print(f"\nwrote {written}")

    if args.musicxml:
        # The score is written separately from the HTML rather than inside it, so a
        # run that asks for both produces both, and a run that asks for neither is
        # unaffected by the optional extra. A missing music21 is a usage problem,
        # not a crash: the message says which install command fixes it.
        try:
            written = write_musicxml(
                arrangement.steps,
                args.musicxml,
                title=solo.title or f"melid {solo.melid}",
                subtitle=f"{solo.performer} - {solo.key}".strip(" -"),
            )
        except ImportError as error:
            print(f"\n{error}")
            return 1
        print(f"wrote {written}")

    if args.gp5:
        # Written separately from the other outputs for the same reason, and on its
        # own extra: a run asking for a GP5 file and a run asking for MusicXML must
        # not require each other's dependency. A missing PyGuitarPro is a usage
        # problem rather than a crash, exactly as for music21 above.
        try:
            written = write_gp5(
                arrangement.steps,
                args.gp5,
                title=solo.title or f"melid {solo.melid}",
                subtitle=f"{solo.performer} - {solo.key}".strip(" -"),
            )
        except ImportError as error:
            print(f"\n{error}")
            return 1
        print(f"wrote {written}")
    return 0

def arrange_slots(
    triples: Sequence[Tuple[str, str, str]],
    timings: Sequence[Tuple[Optional[int], Optional[float], Optional[float]]] = (),
    non_chord_tone: str = "extension",
    fallback: Optional[str] = None,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
    texture: str = "uniform",
    beats_per_bar: int = 4,
    diagnostics: Optional[Diagnostics] = None,
) -> Tuple[List[ArrangementStep], List[int], List[str]]:
    """Voices a list of (note, quality, name) triples, one step per slot.

    **This no longer contains a step loop.** It is a pre-pass over the triples
    followed by a call to `VoiceLeadingEngine.arrange_progression`. It used to be
    a second, near-verbatim copy of that loop - 366 lines, carrying its own copies
    of six decisions under a comment reading *"Both copies must agree"*. The Weimar
    corpus path and the MusicXML path in `headxml` both reach the voicings through
    here, so a head imported from a score is voiced by exactly the same code as the
    same head read out of the database. That was the intention before; now it is a
    property of the structure rather than a promise in a comment.

    What the corpus needs that the library does not, and how each is passed:

    - **a slash bass** (Weimar rule C) becomes `ArrangeOptions.bass_pcs`, a mapping
      from triple index to the pitch class the caller wants in the bass. It narrows
      *which candidates are considered*, and `decisions.select_step_voicing`
      applies the engine's own rule within that narrowed set - so the two selection
      rules stay combined rather than sequential, which is the whole point of rule C.
    - **the diminished retry** becomes a pre-pass below, rewriting the triples
      before the engine sees them.
    - **the timing** becomes `ArrangeOptions.timings`, normalised to one entry per
      triple so the engine's defensive indexing is the only one that runs.

    `timings` is the slots' own `(bar, beat, duration)`, in the renderer's units: a
    signed bar, the beat within it, and a length in whole notes. The duration is
    **optional per slot and `None` in practice** - see `skeleton_slots` for why the
    Weimar path does not supply one, and `headxml` for the one that does. The whole
    sequence is optional too and indexed defensively, so a hand-built sequence
    without timings still arranges - the step simply has none, and the renderers
    fall back to a uniform grid.

    `fallback` may be "diminished", which retries the steps no strategy could
    resolve as Barry Harris dim7 substitutions. It replaces the written chord, so
    it is off unless asked for; the count of steps it *would* rescue is always
    returned in the notes.

    `texture` is the arranging guide's target-note rule, applied by the engine's own
    `_metric_weight` and `_roles_for_slot`, so a head read from the database and the
    same head read from a score are textured identically. "targets" states a full
    chord on beats 1 and 3 and fills the notes between with a shell, a 3rd/6th
    interval or the melody alone; "uniform" (the default) voices every slot in full.
    `beats_per_bar` is the metre that rule reads, and a head in cut time must pass
    its own - a count without a denominator is not a metre.

    Returns the steps, the indexes of the steps the diminished retry actually
    substituted, and any diagnostic notes worth printing. The `notes` are *not* the
    `diagnostics` warnings: they are arrangement-level remarks the caller is
    expected to print itself.
    """
    if texture not in TEXTURE_STYLES:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    if fallback not in (None, "diminished"):
        raise ValueError(f"Unknown fallback {fallback!r}; expected None or 'diminished'")
    if diagnostics is None:
        diagnostics = default_diagnostics()

    engine = VoiceLeadingEngine()
    notes: List[str] = []

    # --- the diminished retry, as a pre-pass -------------------------------------
    #
    # A pre-pass rather than something inside a loop, because there is no loop here
    # any more. The engine must see the substituted chord, and it sees whatever
    # triples it is handed.
    #
    # It used to be applied *after* the slot's role had been computed from the
    # written chord. Under `targets` the role does not read the harmony, so nothing
    # moved; under `walking_bass` it does. That ordering change is measured rather
    # than assumed - see the `fallback=` cases in `.baseline_capture.py`, and
    # `tests/test_wjazzd.py::TestTheRetryReordersNothingVisible`.
    unresolved = unresolved_steps(list(triples), non_chord_tone)
    retry = set(unresolved) if fallback == "diminished" else set()
    rescued: List[int] = []
    working = list(triples)
    if retry:
        notes.append(
            f"diminished fallback replaced the written chord on {len(retry)} step(s)"
        )
        for index in sorted(retry):
            melody, quality, name = triples[index]
            resolved = engine.resolve_non_chord_tone(
                Note(melody), quality, name, "diminished",
                next_melody=_next_chord_tone_melody(triples, index),
            )
            if resolved is not None:
                working[index] = (melody, resolved[0], resolved[1])
                rescued.append(index)

    options = _corpus_options(
        triples=working,
        timings=timings,
        non_chord_tone=non_chord_tone,
        grips=grips,
        texture=texture,
        beats_per_bar=beats_per_bar,
    )

    steps = engine.arrange_progression(
        list(working), options=options, diagnostics=diagnostics
    )
    return steps, rescued, notes


def _corpus_options(
    triples: Sequence[Tuple[str, str, str]],
    timings: Sequence[Tuple[Optional[int], Optional[float], Optional[float]]],
    non_chord_tone: str,
    grips: Tuple[str, ...],
    texture: str,
    beats_per_bar: int,
) -> ArrangeOptions:
    """The request `arrange_slots` makes of the engine, as one value.

    Extracted from `arrange_slots` so the corpus's whole remaining job - deciding
    *what to ask for*, rather than deciding the voicing itself - is a named thing a
    test can read. It is a seam, not a public API: the function is private and the
    arrangement it produces is tested through `arrange_slots`.

    Two things happen here that used to be scattered through the loop.

    **The timings are normalised to one entry per triple.** Written out rather than
    reusing `timings` because that sequence is a `Sequence` and may be shorter than
    `triples`, and pyright will not narrow an index it cannot see. The engine guards
    its own indexing too, but establishing the length invariant once is better than
    defending it twice.

    **The slash bass becomes a pitch class per index.** `None` for a triple with no
    slash, which is every triple of a score-imported head and most of a corpus one.
    The bass note normally rides along in the chord name, which `skeleton_slots`
    keeps intact; `promote_slash_chord` is the case where it does not, and it has
    already written the promoted quality into the name. `bass_cost` is supplied
    alongside because the pitch class says *what* is wanted and the cost says *how
    near* a candidate is to it; neither alone narrows anything.
    """
    # --- the timings, normalised to one entry per triple -------------------------
    #
    # Written out rather than reusing `timings` because that sequence is a `Sequence`
    # and may be shorter than `triples`, and pyright will not narrow an index it
    # cannot see. The engine guards its own indexing too, but doing it here means the
    # length invariant is established once rather than defended twice.
    typed_timings: List[Tuple[Optional[int], Optional[float], Optional[float]]] = [
        (bar, beat, duration)
        if index < len(timings) else (None, None, None)
        for index, (bar, beat, duration) in enumerate(timings)
    ]
    typed_timings.extend(
        [(None, None, None)] * (len(triples) - len(typed_timings))
    )

    # --- the slash bass, as data -------------------------------------------------
    bass_pcs: Dict[int, Optional[int]] = {}
    for index, (_melody, _quality, name) in enumerate(triples):
        bass = parse_weimar_chord(name)[2]
        if bass is not None:
            bass_pcs[index] = bass_pitch_class(bass)

    return ArrangeOptions(
        non_chord_tone=non_chord_tone,
        grips=grips,
        texture=texture,
        beats_per_bar=beats_per_bar,
        timings=typed_timings,
        bass_pcs=bass_pcs or None,
        bass_cost=bass_cost,
    )


def arrange_head(
    solo: Solo,
    head: Optional[HeadSelection] = None,
    strategy: str = "eighths",
    pick: str = "first",
    lift: str = "auto",
    non_chord_tone: str = "extension",
    fallback: Optional[str] = None,
    section: Optional[Tuple[int, int]] = None,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
    texture: str = "uniform",
) -> HeadArrangement:
    """Builds a chord-melody arrangement of a head, end to end.

    Loads nothing itself: it reduces the notes it is given to a skeleton, decides
    the register, and arranges. `fallback` may be "diminished", which retries
    the steps no strategy could resolve as Barry Harris dim7 substitutions.

    That retry is opt-in for a reason. It works mechanically - it finds the dim7 a
    semitone below the resolution target - but it **replaces the written chord**,
    and on a 12-bar blues six of the substitutions tend to land on the tonic, so
    the tonic bar stops being a plain dominant. A head is meant to be the written
    tune, so substituting under it is not something a "give me the head" command
    should do by default. The count of steps it *would* rescue is always reported
    in `rescued`, whether or not the retry is enabled.

    `section` narrows to a bar range directly, for callers that want a span the
    head selector did not choose; `head` takes precedence when both are given.

    The voicing itself is `arrange_slots`, shared with the MusicXML importer in
    `headxml`: which source a head was read from is the loader's business, and
    nothing about the voicings may depend on it.

    `texture` is passed straight through to it. "targets" states a full chord on
    beats 1 and 3 of the bar and fills the notes between with a shell, a 3rd/6th
    interval or the melody alone - the arranging guide's method, and the reason a
    head voiced one note per eighth stops reading as a chord list. "uniform", the
    default, voices every slot in full, which is what this did before textures
    existed and is kept so no existing invocation changes.
    """
    if section is None and head is not None:
        section = (head.start, head.end)
    built = build_skeleton(solo, strategy, section, pick, lift, non_chord_tone)
    steps, rescued, arrange_notes = arrange_slots(
        built.triples, built.timings, non_chord_tone=non_chord_tone,
        fallback=fallback, grips=grips, texture=texture,
    )
    # How many steps a diminished retry *would* rescue, whether or not it ran. Set
    # here rather than in arrange_slots, which has no Skeleton to report it on and
    # should not grow one for the benefit of one caller.
    built.rescued = len(unresolved_steps(list(built.triples), non_chord_tone))
    return HeadArrangement(
        steps, built, head, tuple(rescued), tuple(built.notes) + tuple(arrange_notes)
    )


def _next_chord_tone_melody(triples: Sequence[Tuple[str, str, str]], index: int) -> Optional[str]:
    """The next melody note that is a chord tone of its own chord, if any."""
    for melody, quality, name in triples[index + 1:]:
        if quality == NO_CHORD or not name:
            continue
        if VoiceLeadingEngine.is_chord_tone(Note(melody), quality, name):
            return melody
    return None








