#!/usr/bin/env python
"""Generate - and audit - a drop-2 shape chart straight from the engine's tables.

`common_grips.md` was written by hand, and its fret numbers disagree with its
own inversion labels: a column headed "Root Pos" for Cmaj7 sounds B4-E4-C4-G3,
which is a **7th** in the top voice, and one cell (8-8-9-7) contains an A, which
is not in Cmaj7 at all. Practising from it teaches mislabelled shapes.

So the chart is generated here rather than transcribed. Every fret number comes
from `VoiceLeadingEngine.get_drop2_voicings`, and every label is derived from the
pitches that come back:

* the **top degree** is the melody, matched through `DEGREE_OFFSETS_FROM_ROOT` -
  the same table the engine steers by;
* the **inversion** is named by the **bass**, which is the only correct way to
  name an inversion. In a drop-2 the top voice is the melody and does not
  determine the inversion, which is exactly the mistake the old chart made;
* a shape that does not exist is reported, not fudged. A melody that cannot be
  voiced on 4-3-2-1 (an E4 melody on Cmaj7 has no such shape - the template puts
  the bass a 16th below the open high E) comes back empty and the chart says so.

    python grip_chart.py                    # print a corrected chart
    python grip_chart.py --write FILE      # ... and write it
    python grip_chart.py --audit FILE      # check a hand-written chart

`--audit` re-derives every shape it can find in a markdown chart and reports each
disagreement, so `common_grips.md` is measured rather than assumed wrong. The
audit and the renderer share one code path, so the audit cannot pass a shape the
renderer would not itself produce.

A development tool, like pyright: not part of the package, not imported by
anything, and never a runtime dependency.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from musthe import Note

from arranger import (
    STANDARD_TUNING,
    ChordParser,
    GuitarFretboard,
    VoiceLeadingEngine,
    Voicing,
)

# The two four-string blocks a drop-2 chord melody actually uses, as
# (conventional string numbers high-to-low, soprano string index). Drop-2 is
# defined generically as "the four strings below the soprano", so these are just
# the two sopranos a four-note block exists for - there is none on 6-5-4-3, see
# `_BOTTOM_FOUR` in arranger.py.
BLOCKS: Tuple[Tuple[str, int], ...] = (("4-3-2-1", 5), ("5-4-3-2", 4))

# The qualities the hand-written chart covered, in its own order.
DEFAULT_QUALITIES: Tuple[str, ...] = ("maj7", "m7", "7", "m7b5")

# How each degree above the root is spelled, for the top-voice label.
DEGREE_NAMES: Dict[int, str] = {
    0: "Root", 1: "b9", 2: "9", 3: "b3", 4: "3",
    5: "11", 6: "b5", 7: "5", 8: "b13", 9: "6", 10: "b7", 11: "7",
}

# An inversion is named by its bass. A triad bass (3 or 4) is a 1st inversion, a
# fifth is a 2nd, a seventh is a 3rd - the seventh-chord case being what a chart's
# four "inversions" are actually enumerating. A half-diminished shape can also put
# its own 5th in the bass, which is still a 1st inversion by interval: it is a
# diminished fifth above the root, and a diminished fifth in the bass is a first
# inversion, not an inversion the chart has no word for.
INVERSION_NAMES: Dict[int, str] = {
    0: "Root Pos", 3: "1st Inv", 4: "1st Inv", 6: "1st Inv",
    7: "2nd Inv", 10: "3rd Inv", 11: "3rd Inv",
}

# The words a hand-written chart uses to name an inversion, and the bass degree
# each one claims.
CLAIMED_INVERSIONS: Dict[str, int] = {
    "root": 0, "1st": 3, "2nd": 7, "3rd": 10,
}

MAX_FRET = 18

_PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


def spell(midi: int) -> str:
    """Spells a MIDI pitch: 71 -> 'B4'. `musthe.Note` parses strings only, so a
    pitch derived by transposition has to be spelled before it can be rebuilt."""
    return f"{_PITCH_NAMES[midi % 12]}{midi // 12 - 1}"


def chord_root_pc(quality: str, root: str = "C") -> int:
    """The pitch class of `root` in octave 4, so degrees index off a real C4."""
    parsed, _ = ChordParser.parse_chord_name(root + quality)
    if not parsed:
        raise ValueError(f"cannot parse a root from {root + quality!r}")
    return Note(f"{parsed}4").midi_note() % 12


@dataclass
class Cell:
    """One voicing, plus everything the chart's labels are derived from.

    The labels live here rather than in the renderer so `--audit` and the printed
    chart read the same facts rather than two parallel implementations.
    """

    quality: str
    top_degree: int
    melody_midi: int
    voicing: Voicing
    root_pc: int

    @property
    def top_name(self) -> str:
        return DEGREE_NAMES.get(self.top_degree % 12, f"degree {self.top_degree % 12}")

    @property
    def bass_degree(self) -> int:
        """The lowest sounding voice's degree above the root, as a pitch class."""
        return (min(self.voicing.midi_notes()) - self.root_pc) % 12

    @property
    def inversion(self) -> str:
        return INVERSION_NAMES.get(
            self.bass_degree, f"unlabelled (bass = {self.bass_degree})"
        )

    @property
    def tab(self) -> str:
        return self.voicing.tab_string()

    @property
    def frets_by_string(self) -> List[int]:
        """Frets in tab reading order: high E (index 5) down to low E (index 0)."""
        return [self.voicing.frets[i] for i in range(5, -1, -1)]

    @property
    def sounding_frets(self) -> str:
        return "-".join(str(f) for f in self.frets_by_string if f >= 0)

    @property
    def pitches(self) -> str:
        return " ".join(spell(m) for m in sorted(self.voicing.midi_notes()))


def _melody_for_degree(root_pc: int, degree: int, top_string: int) -> Optional[int]:
    """The lowest pitch of `degree` playable as a melody on `top_string`, or None.

    Lowest, because a chart of shapes is read in the lower positions first and a
    shape that needs no stretch is the one worth practising. None when the degree
    cannot be reached on that string within the 18-fret board.
    """
    open_pitch = STANDARD_TUNING[top_string].midi_note()
    for midi in range(open_pitch, open_pitch + MAX_FRET + 1):
        if midi % 12 == (root_pc + degree) % 12:
            return midi
    return None


def cells_for(quality: str, top_string: int, root: str = "C") -> List[Optional[Cell]]:
    """One entry per degree in `DEGREE_OFFSETS_FROM_ROOT`, in table order.

    An entry is None where the engine has no playable voicing for that degree on
    that string. That is reported rather than replaced with a substitute, because
    the gap is information: it is the selector saying "hold this note on another
    string instead", and a chart that drew a stand-in would hide it.
    """
    degrees = VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.get(quality)
    if degrees is None:
        raise ValueError(f"no degree table for quality {quality!r}")
    root_pc = chord_root_pc(quality, root)
    cells: List[Optional[Cell]] = []
    for degree in degrees:
        melody = _melody_for_degree(root_pc, degree, top_string)
        if melody is None:
            cells.append(None)
            continue
        voicings = VoiceLeadingEngine.get_drop2_voicings(
            Note(spell(melody)), quality, root + quality, top_string=top_string
        )
        if not voicings:
            cells.append(None)
            continue
        cells.append(
            Cell(
                quality=quality,
                top_degree=degree,
                melody_midi=melody,
                voicing=voicings[0],
                root_pc=root_pc,
            )
        )
    return cells


def render_markdown(
    qualities: Sequence[str] = DEFAULT_QUALITIES, root: str = "C"
) -> str:
    """The corrected chart, as markdown. Every fret and label read from the tables."""
    out: List[str] = []
    out.append(f"# Drop-2 shapes on the two four-string blocks ({root} chords)")
    out.append("")
    out.append("Generated by `grip_chart.py` from `VoiceLeadingEngine.get_drop2_voicings`.")
    out.append("Do not hand-edit: regenerate with `python grip_chart.py --write`.")
    out.append("")
    out.append("Read each shape two ways, and do not confuse them.")
    out.append("")
    out.append(
        "- **Top degree** is the melody. It is pinned to the soprano string and is "
        "whatever the tune sings, so it changes step to step."
    )
    out.append(
        "- **Inversion** is named by the **bass**, the lowest voice. This is the only "
        "correct way to name an inversion: in a drop-2 the top voice is the melody and "
        "does not determine it."
    )
    out.append("")
    out.append(
        "The two are independent. A chart that names the inversion after the melody "
        "mislabels every shape it draws."
    )
    out.append("")
    for block, soprano in BLOCKS:
        out.append(f"## {block} block (melody on string {6 - soprano})")
        out.append("")
        for quality in qualities:
            out.append(f"### {root}{quality}")
            out.append("")
            out.append(
                "| top degree | inversion | top frets (high E -> low E) "
                "| sounding notes | tab |"
            )
            out.append("|---|---|---|---|---|")
            for cell in cells_for(quality, soprano, root=root):
                if cell is None:
                    out.append(
                        "| _none_ | - | _not voiceable on this block_ | - | - |"
                    )
                    continue
                out.append(
                    f"| {cell.top_name} ({spell(cell.melody_midi)}) | {cell.inversion} "
                    f"| {cell.sounding_frets} | {cell.pitches} | `{cell.tab}` |"
                )
            out.append("")

    out.append("## Why some cells are empty")
    out.append("")
    out.append(
        "A drop-2 template is four voices spread downwards from the melody. When the "
        "melody is already low, the lowest voice lands off the end of the board or "
        "outside the five-fret hand span, and the shape does not exist. `Cmaj7` with "
        "`E4` on 4-3-2-1 is the clearest case: the template wants the bass a 16th below "
        "the melody, and the melody is the open high E."
    )
    out.append("")
    out.append(
        "The engine is not picking a worse shape here. It is reporting that this block "
        "cannot voice this melody, and the selector then holds the note on the B string "
        "instead - the behaviour that keeps the hand still while the melody stays put. "
        "Those shapes are in the 5-4-3-2 table above."
    )
    out.append("")
    out.append("## Not in this chart")
    out.append("")
    out.append(
        "- **Close position and drop-3.** The engine generates both but offers neither: "
        "each spans a twelfth by construction, so neither can satisfy `GRIP_MAX_SPAN` "
        "at any position."
    )
    out.append(
        "- **6-4-3 four-note drop-3.** Not modelled. The engine's string sets for "
        "`drop3` are the same two contiguous four-string blocks as drop-2; 6-4-3 exists "
        "here only as a *three-note shell* under a G-string melody."
    )
    out.append(
        "- **Any shape the tables do not cover.** A quality with no degree table, or a "
        "degree with no playable inversion, is left out rather than approximated."
    )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Auditing a hand-written chart
# ---------------------------------------------------------------------------

# A tab line: a string name, then pipe-separated cells each holding a fret, then
# anything at all. The old chart writes all four inversions on one line -
# E |----7----|   |----8----| - and annotates the melody row with a trailing
# "<-- Melody (1st string)". That annotation has to be tolerated rather than
# treated as a malformed line: rejecting it would silently drop the melody row,
# which is the one row that decides what the shape is.
_TAB_LINE = re.compile(
    r"^\s*(?P<string>[EBGDAeb])\s*\|(?P<cells>(?:[-\s|]*\d+[-\s|]*)+)"
)
# A markdown heading naming a chord, e.g. "### $Cmaj7$ (C - E - G - B)".
_HEADING = re.compile(r"^#+\s*\$?(?P<name>[A-G][#b]?[A-Za-z0-9+#\-]*)")
# "Root Pos", "1st Inv", "2nd Inv", "3rd Inv", in reading order across a line.
_INVERSION_WORD = re.compile(r"root\s*pos|\b1st\b|\b2nd\b|\b3rd\b", re.IGNORECASE)
# The words a hand-written chart uses to name an inversion, and the bass degree each
# one claims. A fifth in the bass is a 2nd inversion, not a 3rd.
_WORD_DEGREE = {"root": 0, "1st": 3, "2nd": 7, "3rd": 10}
CLAIMED_NAMES: Dict[int, str] = {
    0: "'Root Pos'", 3: "'1st Inv'", 7: "'2nd Inv'", 10: "'3rd Inv'",
}

# Chart string names to this library's indices. Note the deliberate asymmetry:
# an upper-case "E" is the LOW E (it heads the bass row of a 6-4-3 block) while
# a lower-case "e" is the high E. That is the convention the old chart follows.
_STRING_INDEX = {"E": 0, "A": 1, "D": 2, "G": 3, "B": 4, "e": 5}


class ChartCell:
    """One shape as read off a hand-written chart, before it is judged.

    Holds the chart's own claim as well as its frets, so a label can be checked
    against the pitches rather than taken on trust.
    """

    def __init__(
        self,
        line: int,
        column: int,
        frets: List[int],
        claim: Optional[int],
        ambiguous: bool = False,
    ):
        self.line = line
        self.column = column
        self.frets = frets          # index 0 = low E .. 5 = high E, -1 muted
        self.claim = claim          # bass degree the label claims, or None
        self.ambiguous = ambiguous  # True when the chart's "E" could be either end

    @property
    def where(self) -> str:
        return f"line {self.line}, column {self.column + 1}"

    @property
    def midis(self) -> List[int]:
        return [
            GuitarFretboard.fret_to_midi(s, f)
            for s, f in enumerate(self.frets)
            if f >= 0
        ]

    def tab(self) -> str:
        return Voicing(list(self.frets), 0, 0.0).tab_string()


def _readings(frets: List[int], ambiguous: bool) -> List[List[int]]:
    """The fret vectors this cell could mean, high E and low E for a bare "E".

    A chart writes the high E and the low E with the same letter, and which one it
    means depends on the block: the top line of a 4-3-2-1 block is the high E,
    while the bottom line of a 6-4-3 block is the low E. The letter alone cannot
    settle it, so both readings are offered and a shape is accepted if **either**
    is a valid voicing. That is the honest treatment of an ambiguous source: the
    alternative is guessing, and a wrong guess reports correct shapes as errors.
    """
    if not ambiguous:
        return [list(frets)]
    other = list(frets)
    other[0], other[5] = other[5], other[0]
    return [list(frets), other]


def _claim_word(raw: str) -> Optional[int]:
    """The bass degree a label word claims, or None when it names no inversion.

    Strips the decoration a chart puts around the word - "Root Pos", "2nd Inv" -
    so the lookup is on the word itself rather than on the exact spelling, which
    varies between charts.
    """
    word = re.sub(r"\s*(pos|inv|inversion|root position)\s*$", "", raw.strip().lower())
    return _WORD_DEGREE.get(word)


def parse_chart(text: str) -> List[ChartCell]:
    """Read every shape out of a markdown chart, without judging any of them.

    A shape is a run of consecutive tab lines: one line per string, one column per
    inversion. The label line immediately above the run supplies the inversion each
    column claims, read left to right the way such a chart is laid out.
    """
    cells: List[ChartCell] = []
    claims: List[int] = []
    run: List[Tuple[int, str, List[int]]] = []   # (line no, string name, frets)

    def flush() -> None:
        nonlocal run
        if run:
            cells.extend(_cells_from_run(run, claims))
        run = []

    for number, raw in enumerate(text.splitlines(), start=1):
        if _HEADING.match(raw):
            flush()
            claims = []
            continue
        tab = _TAB_LINE.match(raw)
        if tab:
            frets = [int(n) for n in re.findall(r"\d+", tab.group("cells"))]
            if run and len(frets) != len(run[0][2]):
                flush()   # a fresh run of shapes starts here
            run.append((number, tab.group("string"), frets))
            continue
        words = [
            degree
            for degree in (_claim_word(w) for w in _INVERSION_WORD.findall(raw))
            if degree is not None
        ]
        if words:
            flush()
            claims = words
        else:
            flush()
    flush()
    return cells


def _cells_from_run(
    run: List[Tuple[int, str, List[int]]], claims: Sequence[int]
) -> List[ChartCell]:
    """Turn one run of tab lines into a ChartCell per column.

    The nth column of an n-column run is the nth inversion of the shape, so the
    label is claimed positionally - the way such a chart is laid out and read. A
    column with no corresponding label carries no claim and is not checked on
    that point. A ragged run is truncated rather than padded with guesses.
    """
    out: List[ChartCell] = []
    # A bare "E" is the high E in a 4-3-2-1 or 5-4-3-2 block and the low E in a
    # 6-4-3 one, so its position in the run decides whether it is ambiguous.
    names = [name for _, name, _ in run]
    ambiguous = names.count("E") == 1
    for column in range(len(run[0][2])):
        frets = [-1] * len(STANDARD_TUNING)
        for _, name, values in run:
            if column >= len(values):
                break
            slot = _STRING_INDEX.get(name)
            if slot is not None:
                frets[slot] = values[column]
        claim = claims[column] if column < len(claims) else None
        out.append(ChartCell(run[0][0], column, frets, claim, ambiguous))
    return out


def audit(text: str) -> List[str]:
    """Every disagreement between a chart and the engine's own tables.

    Returns human-readable problems; an empty list means the chart agrees
    everywhere it could be checked. A cell that cannot be read is reported rather
    than skipped, so a malformed chart never passes silently.
    """
    problems: List[str] = []
    for cell in parse_chart(text):
        problems.extend(_check_cell(cell, text))
    return problems


def _check_cell(cell: ChartCell, text: str) -> List[str]:
    """Judge one cell, trying each reading its notation allows.

    The chart's bare "E" may be the high E or the low E, so a cell can have two
    readings. A shape counts as sound if either reading is a valid voicing: the
    ambiguity is in the notation, not in the music, and reporting a correct shape
    as broken because of a guess about layout would be worse than saying nothing.
    """
    quality = _quality_near(text, cell.line)
    if quality is None:
        return [
            f"{cell.where}: cannot tell which chord quality this is, so the shape is "
            "not checked - the chart should head each block with the chord name"
        ]
    readings = _readings(cell.frets, cell.ambiguous)
    for reading in readings:
        if not _check_reading(cell, reading, quality):
            return []
    # Neither reading is sound: report the one that is least wrong, so the message
    # names a real problem rather than an artefact of the ambiguity.
    return min((_check_reading(cell, r, quality) for r in readings), key=len)


def _check_reading(cell: ChartCell, frets: List[int], quality: str) -> List[str]:
    """One chart cell, read one way, against one quality."""
    problems: List[str] = []
    root_pc = chord_root_pc(quality)
    midis = [
        GuitarFretboard.fret_to_midi(s, f) for s, f in enumerate(frets) if f >= 0
    ]
    if not midis:
        return [f"{cell.where}: no sounding strings"]
    tones = set(ChordParser.get_chord_tones(quality))
    degrees = {(m - root_pc) % 12 for m in midis}

    foreign = sorted(degrees - tones)
    if foreign:
        names = ", ".join(DEGREE_NAMES.get(d, str(d)) for d in foreign)
        problems.append(
            f"{cell.where}: the shape sounds {names}, which is not in {quality} - so it is "
            "not a voicing of that chord at all"
        )

    bass_degree = (min(midis) - root_pc) % 12
    if cell.claim is not None and cell.claim != bass_degree:
        actual = INVERSION_NAMES.get(bass_degree, f"unlabelled (bass {bass_degree})")
        problems.append(
            f"{cell.where}: labelled {CLAIMED_NAMES[cell.claim]} here, but the bass is the "
            f"{DEGREE_NAMES.get(bass_degree, str(bass_degree))}, which is {actual} - in a "
            "drop-2 the inversion is named by the bass, not by the melody"
        )

    if not _engine_has_shape(quality, max(midis), frets):
        problems.append(
            f"{cell.where}: {spell(max(midis))} over {quality} sounds only chord tones, "
            "but its interval structure is not one of the engine's drop-2 templates - "
            "the engine would voice these notes differently"
        )
    return problems


def _quality_near(text: str, line: int) -> Optional[str]:
    """The quality named by the nearest heading above `line`, or None.

    Walks upwards, because a chart groups all four inversions of one chord under a
    single heading. A heading naming a quality the engine cannot voice gives None and
    is reported by the caller - never guessed at, on the same principle as the Weimar
    and MusicXML tables.
    """
    for raw in reversed(text.splitlines()[:line]):
        heading = _HEADING.match(raw)
        if heading:
            return _quality_of(heading.group("name"))
    return None


def _quality_of(heading: str) -> Optional[str]:
    """The library quality for a chart heading such as 'Cmaj7', or None.

    Tries the heading whole and then with its leading root note stripped, since a
    chart may head a block with the chord name or with the bare quality.
    """
    for candidate in (heading, heading[1:]):
        parsed, quality = ChordParser.parse_chord_name(candidate)
        if parsed and quality in VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT:
            return quality
    return None


def _engine_has_shape(quality: str, top: int, chart_frets: List[int]) -> bool:
    """Does the engine voice this melody over this chord with these notes?

    The comparison is on the **interval structure**, which is what makes a shape a
    drop-2 of that chord, and it is position-independent by construction:

    * a shape is correct if its notes, measured down from the melody, match one of
      the engine's own `DROP2_INTERVAL_SETS` templates for the melody's degree;
    * failing that, it is correct if the engine can actually voice those notes on
      one of its two blocks.

    Checking against the voicing the engine *chose* instead would be wrong in a
    way that is easy to miss: `get_drop2_voicings` returns one placement per
    degree, its lowest. A chart is a set of positions to practise, so a perfectly
    good shape three frets higher would be reported as an error. The template is
    the rule; the placement is an implementation detail of where the engine
    happens to put it.
    """
    offsets = sorted(
        top - m for m in (
            GuitarFretboard.fret_to_midi(s, f)
            for s, f in enumerate(chart_frets)
            if f >= 0
        )
    )
    degrees = VoiceLeadingEngine.DEGREE_OFFSETS_FROM_ROOT.get(quality, [])
    root_pc = chord_root_pc(quality)
    degree = (top - root_pc) % 12
    index = degrees.index(degree) if degree in degrees else None
    templates = VoiceLeadingEngine.DROP2_INTERVAL_SETS.get(quality, [])
    if index is not None and index < len(templates):
        template = sorted(-offset for offset in templates[index])
        if offsets == template:
            return True

    # Not a template shape: the last resort is asking the engine directly, on either
    # block, whether it can voice this melody with these notes at all.
    wanted = sorted(
        m % 12
        for s, f in enumerate(chart_frets)
        if f >= 0
        for m in (GuitarFretboard.fret_to_midi(s, f),)
    )
    for soprano in (5, 4):
        for voicing in VoiceLeadingEngine.get_drop2_voicings(
            Note(spell(top)), quality, "C" + quality, top_string=soprano
        ):
            # A sorted list, not a set: a shape may double a chord tone, and a set
            # would quietly accept a four-note shape with only three distinct notes.
            if sorted(m % 12 for m in voicing.midi_notes()) == wanted:
                return True
    return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    # __doc__ is Optional[str] to a type checker, and argparse wants a str. The
    # summary is a literal here rather than read from the module docstring, so it
    # cannot be None however the file is edited.
    parser = argparse.ArgumentParser(
        description="Generate or audit a drop-2 shape chart from the engine's tables"
    )
    parser.add_argument(
        "--audit",
        metavar="FILE",
        help="check a hand-written chart against the engine's tables, instead of printing one",
    )
    parser.add_argument("--write", metavar="FILE", help="write the generated chart to FILE")
    parser.add_argument(
        "--root", default="C", help="root note for the generated chart (default: C)"
    )
    args = parser.parse_args(argv)

    if args.audit:
        with open(args.audit, encoding="utf-8") as handle:
            problems = audit(handle.read())
        if not problems:
            print(f"{args.audit}: agrees with the engine's tables on every shape checked.")
            return 0
        print(f"{args.audit}: {len(problems)} disagreement(s) with the engine's tables.")
        for problem in problems:
            print(f"  {problem}")
        return 1

    text = render_markdown(root=args.root)
    if args.write:
        with open(args.write, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"wrote {args.write}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
