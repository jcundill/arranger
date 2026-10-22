"""Generate the synthetic MusicXML fixtures in ``tests/data``.

The corpus exists to exercise the importer, the arrangement engine and the four
writers.  It does not need to contain anyone's tune to do that, so every file
except the retained ``Trouble_in_Mind_Blues.musicxml`` is generated here from
this module's own material.  The generator is stdlib-only and deterministic: a
committed document is a pure function of the code below, which is what lets
``tests/meta_fixture_corpus.py`` compare the two.

Run ``python tests/fixture_scores.py`` to rewrite the fixtures, or
``python tests/fixture_scores.py --check`` to compare without writing.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from fractions import Fraction
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


# ---------------------------------------------------------------------------
# MusicXML vocabulary
# ---------------------------------------------------------------------------

#: The qualities the synthetic corpus needs, spelled the way MusicXML spells
#: them.  A quality absent from this table is deliberately absent from the
#: corpus too, because ``headxml`` reports an unreadable kind rather than
#: guessing at it.
KINDS: Dict[str, str] = {
    "maj": "major",
    "m": "minor",
    "7": "dominant",
    "maj7": "major-seventh",
    "m7": "minor-seventh",
    "dim7": "diminished-seventh",
    "m7b5": "half-diminished",
    "7b5": "dominant",
    "7b9": "dominant",
    "7#5": "augmented-seventh",
    "7sus4": "suspended-fourth-seventh",
    "6": "major-sixth",
    "m6": "minor-sixth",
    "9": "dominant-ninth",
    "maj9": "major-ninth",
    "m9": "minor-ninth",
    "13": "dominant-13th",
    "maj7#11": "major-11th",
    "sus2": "suspended-second",
    "sus4": "suspended-fourth",
}

#: The alterations MusicXML states beside a base kind.
DEGREES: Dict[str, Tuple[Tuple[int, int], ...]] = {
    "7b5": ((5, -1),),
    "7b9": ((9, -1),),
    "7#5": ((5, 1),),
    "7sus4": ((7, 0),),
    "maj7#11": ((11, 1),),
}


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pitch_xml(name: str) -> str:
    """A pitch from a scientific-pitch name, with ``b``/``#`` accidentals."""
    step = name[0].upper()
    rest = name[1:]
    alter = 0
    while rest and rest[0] in "b#":
        alter += -1 if rest[0] == "b" else 1
        rest = rest[1:]
    octave = int(rest)
    out = f"<step>{step}</step>"
    if alter:
        out += f"<alter>{alter}</alter>"
    out += f"<octave>{octave}</octave>"
    return out


def note(
    name: str,
    duration: int,
    *,
    chord: bool = False,
    tie: Optional[str] = None,
    tuplet: Optional[Tuple[int, int]] = None,
    voice: int = 1,
    staff: Optional[int] = None,
    beam: Optional[str] = None,
) -> str:
    """One pitched ``<note>``.

    ``duration`` is in divisions.  ``tie`` is ``"start"``, ``"stop"`` or
    ``"both"`` and writes both the sound-level ``<tie>`` and the notation-level
    ``<tied>``, because a real exporter writes both and the importer reads the
    first.
    """
    tie_xml = f'<tie type="{tie}"/>' if tie else ""
    tied_xml = f'<tied type="{tie}"/>' if tie else ""
    tuplet_xml = ""
    if tuplet is not None:
        actual, normal = tuplet
        tuplet_xml = (
            f"<time-modification><actual-notes>{actual}</actual-notes>"
            f"<normal-notes>{normal}</normal-notes></time-modification>"
        )
    staff_xml = f"<staff>{staff}</staff>" if staff is not None else ""
    beam_xml = f'<beam number="1">{beam}</beam>' if beam else ""
    return (
        "<note>"
        + ("<chord/>" if chord else "")
        + f"<pitch>{_pitch_xml(name)}</pitch>"
        + f"<duration>{duration}</duration>"
        + tie_xml
        + f"<voice>{voice}</voice>"
        + tuplet_xml
        + staff_xml
        + beam_xml
        + (f"<notations>{tied_xml}</notations>" if tied_xml else "")
        + "</note>"
    )


def rest(
    duration: int,
    *,
    measure: bool = False,
    voice: int = 1,
    staff: Optional[int] = None,
) -> str:
    staff_xml = f"<staff>{staff}</staff>" if staff is not None else ""
    rest_xml = '<rest measure="yes"/>' if measure else "<rest/>"
    return (
        f"<note>{rest_xml}<duration>{duration}</duration><voice>{voice}</voice>"
        f"{staff_xml}</note>"
    )


def direction(text: str) -> str:
    """One ``<direction>`` carrying a ``<words>`` mark, as a lead sheet writes ``3+2``."""
    return (
        "<direction><direction-type><words>"
        + _xml(text)
        + "</words></direction-type></direction>"
    )


def beamed(
    names: Sequence[str], duration: int, groups: Sequence[int]
) -> List[str]:
    """A run of notes whose primary beams are split at ``groups`` (in notes).

    The final note of each group is its ``end`` and the notes between are
    ``continue``; the generator refuses a one-note group, which has no beam in
    practice.
    """
    out: List[str] = []
    index = 0
    for size in groups:
        if size < 2:
            raise ValueError("a beam group needs at least two notes")
        for offset in range(size):
            if offset == 0:
                mark = "begin"
            elif offset == size - 1:
                mark = "end"
            else:
                mark = "continue"
            out.append(note(names[index], duration, beam=mark))
            index += 1
    if index != len(names):
        raise ValueError("the beam groups do not cover the melody")
    return out


def _musical_type(quarters: Fraction) -> Tuple[str, int]:
    """The written note value and dot count for a duration in quarter notes.

    A reader that lays a score out from ``<type>`` - MuseScore among them - cannot
    place a note without one, however exact its ``<duration>`` is.  The durations
    this generator writes are all plain or singly dotted, so a value that matches
    neither is a generator bug rather than something to guess at.
    """
    values = (
        ("whole", Fraction(4)),
        ("half", Fraction(2)),
        ("quarter", Fraction(1)),
        ("eighth", Fraction(1, 2)),
        ("16th", Fraction(1, 4)),
        ("32nd", Fraction(1, 8)),
        ("64th", Fraction(1, 16)),
    )
    for name, value in values:
        if quarters == value:
            return name, 0
        if quarters == value * Fraction(3, 2):
            return name, 1
    raise ValueError(f"no note value for {quarters} quarter notes")


_DURATION = re.compile(r"<duration>(\d+)</duration>")
_MODIFICATION = re.compile(
    r"<actual-notes>(\d+)</actual-notes><normal-notes>(\d+)</normal-notes>"
)


def _add_note_types(contents: Iterable[str], divisions: int) -> List[str]:
    """Write the ``<type>`` a notation program needs beside each ``<duration>``.

    ``<duration>`` says how long a note sounds; ``<type>`` says which notehead
    value it is written as.  They disagree for a tuplet - a triplet eighth sounds
    a third of a quarter but is still an eighth - so the nominal value is the
    sounding one scaled back by ``actual/normal``.
    """
    out: List[str] = []
    for fragment in contents:
        if not fragment.startswith("<note>") or "<type>" in fragment:
            out.append(fragment)
            continue
        match = _DURATION.search(fragment)
        if match is None:
            raise ValueError(f"note has no duration: {fragment}")
        duration = int(match.group(1))
        actual = normal = 1
        modification = _MODIFICATION.search(fragment)
        if modification is not None:
            actual, normal = (int(value) for value in modification.groups())
        nominal = Fraction(duration, divisions) * Fraction(actual, normal)
        name, dots = _musical_type(nominal)
        typed = f"<type>{name}</type>" + "<dot/>" * dots
        position = fragment.find("<time-modification>")
        if position < 0:
            position = fragment.find("<staff>")
        if position < 0:
            position = fragment.find("<beam")
        if position < 0:
            position = fragment.find("<notations>")
        if position < 0:
            position = fragment.find("</note>")
        out.append(fragment[:position] + typed + fragment[position:])
    return out


def harmony(
    root: str,
    quality: str,
    *,
    bass: Optional[str] = None,
    text: Optional[str] = None,
) -> str:
    """One ``<harmony>`` symbol.

    ``quality`` is a key of ``KINDS``.  A slash bass is written through
    ``<bass>``, which is how MuseScore spells one, and an altered tone through
    ``<degree>``, which is how it spells an ``E7b5``.
    """
    root_xml = f"<root><root-step>{root[0]}</root-step>"
    if len(root) > 1 and root[1] == "b":
        root_xml += "<root-alter>-1</root-alter>"
    elif len(root) > 1 and root[1] == "#":
        root_xml += "<root-alter>1</root-alter>"
    root_xml += "</root>"
    label = text if text is not None else quality
    kind_xml = f'<kind text="{_xml(label)}">{KINDS[quality]}</kind>'
    bass_xml = ""
    if bass:
        bass_xml = f"<bass><bass-step>{bass[0]}</bass-step>"
        if len(bass) > 1 and bass[1] == "b":
            bass_xml += "<bass-alter>-1</bass-alter>"
        elif len(bass) > 1 and bass[1] == "#":
            bass_xml += "<bass-alter>1</bass-alter>"
        bass_xml += "</bass>"
    degree_xml = "".join(
        f"<degree><degree-value>{value}</degree-value>"
        f"<degree-alter>{alter}</degree-alter>"
        f"<degree-type>alter</degree-type></degree>"
        for value, alter in DEGREES.get(quality, ())
    )
    return f"<harmony>{root_xml}{kind_xml}{bass_xml}{degree_xml}</harmony>"


def barline(
    *,
    location: str = "right",
    style: Optional[str] = None,
    repeat: Optional[str] = None,
    ending: Optional[Tuple[str, str]] = None,
) -> str:
    inner = ""
    if style:
        inner += f"<bar-style>{style}</bar-style>"
    if ending:
        kind, number = ending
        inner += f'<ending number="{number}" type="{kind}"/>'
    if repeat:
        inner += f'<repeat direction="{repeat}"/>'
    return f'<barline location="{location}">{inner}</barline>'


def measure(number: int, contents: Iterable[str], *, implicit: bool = False) -> str:
    attribute = ' implicit="yes"' if implicit else ""
    return (
        f'<measure number="{number}"{attribute}>'
        + "".join(contents)
        + "</measure>"
    )


def attributes(
    divisions: int,
    beats: int,
    beat_type: int,
    *,
    fifths: Optional[int],
    mode: str = "major",
    clef_sign: str = "G",
    clef_line: int = 2,
    staff_details: bool = False,
    staves: Optional[int] = None,
) -> str:
    key = ""
    if fifths is not None:
        key = f"<key><fifths>{fifths}</fifths><mode>{mode}</mode></key>"
    staves_xml = f"<staves>{staves}</staves>" if staves else ""
    details = (
        "<staff-details><staff-lines>6</staff-lines></staff-details>"
        if staff_details
        else ""
    )
    return (
        "<attributes>"
        f"<divisions>{divisions}</divisions>"
        + key
        + f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
        + staves_xml
        + f"<clef><sign>{clef_sign}</sign><line>{clef_line}</line></clef>"
        + details
        + "</attributes>"
    )


def document(
    title: str,
    parts: Sequence[Tuple[str, str, Sequence[str]]],
    *,
    composer: Optional[str] = None,
) -> str:
    creator = (
        f'<creator type="composer">{_xml(composer)}</creator>' if composer else ""
    )
    part_list = "".join(
        f'<score-part id="{part_id}"><part-name>{_xml(name)}</part-name></score-part>'
        for part_id, name, _measures in parts
    )
    body = "".join(
        f'<part id="{part_id}">' + "".join(measures) + "</part>"
        for part_id, _name, measures in parts
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<score-partwise version="3.1">\n'
        f"<work><work-title>{_xml(title)}</work-title></work>\n"
        f"<movement-title>{_xml(title)}</movement-title>\n"
        f"<identification>{creator}</identification>\n"
        f"<part-list>{part_list}</part-list>\n"
        f"{body}\n"
        "</score-partwise>\n"
    )


def _zip(document_xml: str, member: str) -> bytes:
    """A deterministic ``.mxl`` container holding one score."""
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        def write(name: str, text: str) -> None:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text)

        write(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<container><rootfiles>"
            f'<rootfile full-path="{member}" '
            'media-type="application/vnd.recordare.musicxml+xml"/>'
            "</rootfiles></container>",
        )
        write(member, document_xml)
    return buffer.getvalue()


def _measures(
    bars: Sequence[Sequence[str]],
    *,
    divisions: int,
    beats: int,
    beat_type: int,
    fifths: Optional[int],
    clef_sign: str = "G",
    clef_line: int = 2,
    staff_details: bool = False,
    staves: Optional[int] = None,
    first_implicit: bool = False,
) -> List[str]:
    """Measures with the attributes stated on the first one.

    MusicXML states ``<divisions>``, the key, the metre and the clef once, in the
    first measure of a part; repeating them is legal but not what an exporter
    writes, and a reader that only looks at the first measure is the common case
    this corpus should exercise.
    """
    out: List[str] = []
    for index, contents in enumerate(bars):
        body = _add_note_types(contents, divisions)
        if index == 0:
            body.insert(
                0,
                attributes(
                    divisions,
                    beats,
                    beat_type,
                    fifths=fifths,
                    clef_sign=clef_sign,
                    clef_line=clef_line,
                    staff_details=staff_details,
                    staves=staves,
                ),
            )
        out.append(measure(index + 1, body, implicit=first_implicit and index == 0))
    return out


def cut_time() -> str:
    """8 bars of 2/2: a pickup rest, a cross-barline tie, a melody-less beat.

    Replaces ``synthetic_cut_time.mxl``.  The features it keeps are the ones the
    tests name: a first note after a quarter rest (beat 1.5 and a one-quarter
    pickup), a chord change arriving after a tie in bar 3, a narrow-palette
    ``F4`` over ``Ebmaj`` in bar 2, and a ``Cm7`` under a held ``Eb4`` on bar 3's
    downbeat.
    """
    d = 4  # divisions per quarter; a 2/2 bar is 16
    bars = [
        [
            rest(4),
            harmony("Bb", "7"),
            note("F4", 4),
            note("G4", 4),
            note("F4", 4),
        ],
        [
            harmony("Eb", "maj"),
            note("G4", 8),
            note("F4", 4),
            harmony("Cm", "m7"),
            note("Eb4", 4, tie="start"),
        ],
        [
            harmony("Cm", "m7"),
            note("Eb4", 4, tie="stop"),
            harmony("Bb", "7"),
            note("F4", 4),
            note("G4", 4),
            note("F4", 4),
        ],
        [harmony("Eb", "maj"), note("G4", 16)],
        [harmony("Bb", "7"), note("F4", 4), note("G4", 4), note("F4", 4), rest(4)],
        [harmony("F", "7"), note("G4", 8), note("F4", 4), note("Eb4", 4)],
        [harmony("Bb", "7"), note("F4", 4), note("G4", 4), note("F4", 4), rest(4)],
        [harmony("Eb", "7"), note("G4", 16)],
    ]
    measures = _measures(
        bars, divisions=d, beats=2, beat_type=2, fifths=-3
    )
    return document(
        "Synthetic Cut Time",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def common_8() -> str:
    """8 bars of 4/4 with a repeated-note bar and a melody-less last bar.

    Replaces ``synthetic_common_8.musicxml``.  Bar 3 is four ``G4``s over
    ``Eb7`` - the reported bar of the fill rule - and bar 8 carries changes but no
    tune, which is where the comping grid has to stab without inventing a melody.
    """
    d = 8  # divisions per quarter; a 4/4 bar is 32
    bars = [
        [
            harmony("C", "maj7"),
            note("E4", 8),
            note("G4", 8),
            note("A4", 8),
            note("G4", 8),
        ],
        [
            harmony("D", "m7"),
            note("F4", 24),
            harmony("G", "7"),
            note("D4", 8),
        ],
        [
            harmony("Eb", "7"),
            note("G4", 8),
            note("G4", 8),
            note("G4", 8),
            note("G4", 8),
        ],
        [
            harmony("Ab", "maj7"),
            note("Eb4", 16),
            harmony("F", "m7"),
            note("C4", 16),
        ],
        [
            harmony("Bb", "maj7"),
            note("D4", 8),
            note("F4", 8),
            note("Bb4", 8),
            note("A4", 8),
        ],
        [
            harmony("Eb", "maj7"),
            note("G4", 16),
            harmony("C", "13"),
            note("Eb5", 16),
        ],
        [
            harmony("Am", "m7"),
            note("C5", 8),
            note("A4", 8),
            harmony("E", "7b5"),
            note("A4", 8),
            note("D4", 8),
        ],
        [
            harmony("G", "maj7"),
            harmony("C", "7"),
            rest(32, measure=True),
        ],
    ]
    measures = _measures(bars, divisions=d, beats=4, beat_type=4, fifths=-3)
    return document(
        "Synthetic Common Time",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def repeat_slash() -> str:
    """8 written bars of 2/2, played as 12, with a repeat and two endings.

    Replaces ``synthetic_repeat_slash.musicxml``.  The features are the ones the
    repeat and timeline tests name: the 1st ending has a tie into a melody-less
    bar that states two changes, the 2nd ending is a two-bar tie chain, and the
    first bar carries a ``Gmaj9/F#`` slash chord beside an ``E7b5`` written as a
    ``<degree>``.
    """
    d = 4  # divisions per quarter; a 2/2 bar is 16
    bars = [
        [
            harmony("G", "maj9"),
            note("D4", 4),
            note("D4", 8),
            harmony("G", "maj9", bass="F#"),
            note("D4", 4),
        ],
        [
            harmony("Bb", "7", bass="F"),
            note("D4", 4),
            note("F4", 4),
            harmony("E", "7b5"),
            note("Bb4", 4),
            note("D5", 4),
        ],
        [harmony("Eb", "maj7"), note("D5", 8), note("C5", 4), note("B4", 4)],
        [harmony("Eb", "6"), note("C5", 16)],
        [
            barline(location="left", ending=("start", "1")),
            harmony("Am", "m7"),
            note("D4", 4),
            note("D4", 4),
            note("G4", 8, tie="start"),
        ],
        [
            harmony("Am", "m7"),
            note("G4", 4, tie="stop"),
            rest(4),
            harmony("D", "9"),
            rest(8),
            barline(
                ending=("stop", "1"),
                repeat="backward",
                style="light-heavy",
            ),
        ],
        [
            barline(location="left", ending=("start", "2")),
            harmony("Bb", "maj7"),
            note("F4", 16, tie="start"),
        ],
        [
            harmony("Eb", "maj7"),
            note("F4", 16, tie="stop"),
            barline(ending=("stop", "2"), style="light-heavy"),
        ],
    ]
    measures = _measures(bars, divisions=d, beats=2, beat_type=2, fifths=1)
    return document(
        "Synthetic Repeat Slash",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def waltz() -> str:
    """8 written bars of 3/4, played as 12, with a repeat and two endings.

    Replaces ``synthetic_waltz.musicxml``.  The first bar is an eighth rest
    followed by five eighths, which is the onset pattern the metre tests pin; the
    next two bars are six eighths each.
    """
    d = 4  # divisions per quarter; a 3/4 bar is 12 and an eighth is 2
    bars = [
        [
            harmony("Eb", "6"),
            rest(2),
            note("C5", 2),
            note("Eb5", 2),
            note("G5", 2),
            note("F5", 2),
            note("D5", 2),
        ],
        [
            harmony("Eb", "6"),
            note("Eb5", 2),
            note("Bb4", 2),
            note("G4", 2),
            note("Ab4", 2),
            note("C5", 2),
            note("Bb4", 2),
        ],
        [
            harmony("Eb", "6"),
            note("G4", 2),
            note("Eb4", 2),
            note("F4", 2),
            note("D4", 2),
            note("Eb4", 2),
            note("Bb3", 2),
        ],
        [harmony("Ab", "maj7"), note("F4", 12)],
        [
            barline(location="left", ending=("start", "1")),
            harmony("Bb", "7"),
            note("G4", 6),
            note("F4", 6),
        ],
        [
            harmony("Bb", "7"),
            note("Eb4", 6),
            note("D4", 6),
            barline(ending=("stop", "1"), repeat="backward", style="light-heavy"),
        ],
        [
            barline(location="left", ending=("start", "2")),
            harmony("Eb", "maj7"),
            note("Eb4", 6),
            note("G4", 6),
        ],
        [
            harmony("Eb", "6"),
            note("Bb4", 12),
            barline(ending=("stop", "2"), style="light-heavy"),
        ],
    ]
    measures = _measures(bars, divisions=d, beats=3, beat_type=4, fifths=-3)
    return document(
        "Synthetic Waltz",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def _triplet_group(names: Sequence[str], duration: int) -> List[str]:
    return [note(name, duration, tuplet=(3, 2)) for name in names]


def triplets() -> str:
    """8 written bars of 2/2 in 10080 divisions, played as 12.

    Replaces ``synthetic_triplets.mxl``.  The first bar states two lengths
    that put an onset five ticks off the beat, so the head still needs the whole
    twenty-fourth-note lattice; bars 2-8 carry eighth-note triplets; a repeat and
    two endings make the played form three times the written body plus the second
    ending.
    """
    d = 10080  # divisions per quarter
    bar = 4 * d
    # An eighth-note triplet sounds 3360 divisions: a third of a quarter, which is
    # one sixth of a 2/2 beat and therefore exactly four ticks. Four groups fill
    # the bar.  The written ``<duration>`` is the sounding length; ``<type>``
    # names the eighth that the tuplet dims.
    step = 3360

    def triplet_bar(
        first: Tuple[str, str],
        second: Optional[Tuple[str, str]],
        groups: Sequence[Sequence[str]],
    ) -> List[str]:
        contents = [harmony(*first)]
        contents += _triplet_group(groups[0], step)
        contents += _triplet_group(groups[1], step)
        if second is not None:
            contents.append(harmony(*second))
        contents += _triplet_group(groups[2], step)
        contents += _triplet_group(groups[3], step)
        return contents

    body: List[List[str]] = [
        [
            harmony("G", "maj"),
            # Two tied pairs spell the odd durations the lattice test needs:
            # 2520 + 1680 = 4200 and 2520 + 3360 = 5880 divisions.  The tails are
            # tuplets, so every notehead has a standard value even though the
            # sounding length that reaches the importer does not.
            note("D5", 2520, tie="start"),
            note("D5", 1680, tuplet=(3, 2), tie="stop"),
            note("B4", 2520, tie="start"),
            note("B4", 3360, tuplet=(3, 2), tie="stop"),
            note("C5", d),
            note("D5", d),
            note("E5", d),
        ],
        [
            harmony("Am", "m7"),
            note("D5", d),
            note("B4", d),
            note("C5", d),
            harmony("D", "7"),
            rest(d),
        ],
        triplet_bar(
            ("G", "maj"),
            ("G#", "dim7"),
            (
                ["D5", "B4", "C5"],
                ["D5", "B4", "C5"],
                ["B4", "A4", "G4"],
                ["B4", "A4", "G4"],
            ),
        ),
        triplet_bar(
            ("Am", "m7"),
            ("D", "7"),
            (
                ["C5", "A4", "F#4"],
                ["C5", "A4", "F#4"],
                ["D4", "F#4", "A4"],
                ["D4", "F#4", "A4"],
            ),
        ),
        [barline(location="left", ending=("start", "1"))]
        + [
            harmony("G", "maj"),
            harmony("Eb", "7"),
        ]
        + _triplet_group(["G4", "Bb4", "Db5"], step)
        + _triplet_group(["C5", "Bb4", "G4"], step)
        + _triplet_group(["G4", "Bb4", "Db5"], step)
        + _triplet_group(["C5", "Bb4", "G4"], step),
        triplet_bar(
            ("Am", "m7"),
            ("D", "7"),
            (
                ["A4", "C5", "E5"],
                ["A4", "C5", "E5"],
                ["D5", "C5", "A4"],
                ["D5", "C5", "A4"],
            ),
        )
        + [barline(ending=("stop", "1"), repeat="backward", style="light-heavy")],
        [barline(location="left", ending=("start", "2"))]
        + [
            harmony("G", "6"),
            harmony("Eb", "7"),
        ]
        + _triplet_group(["G4", "Bb4", "Db5"], step)
        + _triplet_group(["C5", "Bb4", "G4"], step)
        + _triplet_group(["G4", "Bb4", "Db5"], step)
        + _triplet_group(["C5", "Bb4", "G4"], step),
        triplet_bar(
            ("G", "maj7"),
            None,
            (
                ["B4", "D5", "G5"],
                ["F#5", "D5", "B4"],
                ["G4", "B4", "D5"],
                ["F#4", "A4", "D5"],
            ),
        )
        + [barline(ending=("stop", "2"), style="light-heavy")],
    ]
    # The first four bars are the repeated body; bars 5-6 are ending 1 and bars
    # 7-8 ending 2.  The attributes are stated on bar 1 only.
    assert sum(
        4200 + 5880 + d + d + d for _ in [0]
    ) == bar
    measures = _measures(body, divisions=d, beats=2, beat_type=2, fifths=1)
    return document(
        "Synthetic Triplets",
        [("P1", "Piano", measures)],
        composer="Fixture Generator",
    )


def tab_export() -> str:
    """6 bars of 4/4 with a notation part and a TAB part beside it.

    Replaces ``synthetic_tab_export.musicxml``.  The point is the part choice: both
    parts carry the same music, the TAB one is identified by its clef, and the
    notation part wins.  A ``<chord>`` group in the notation part also exercises
    the top-line reduction and its ``skipped`` report.
    """
    d = 12  # divisions per quarter; triplet eighths are 4
    four = 4 * d
    bars: List[List[str]] = [
        [
            harmony("C", "maj7"),
            note("E4", four),
            note("C5", four, chord=True),
        ],
        [
            harmony("D", "m7"),
            note("F4", d),
            note("A4", d),
            note("C5", d),
            note("D5", d),
        ],
        [
            harmony("G", "7"),
        ]
        + _triplet_group(["G4", "B4", "D5"], 4)
        + _triplet_group(["F5", "D5", "B4"], 4)
        + [note("G4", d), note("G4", d)],
        [
            harmony("Eb", "maj7"),
            note("Eb4", 2 * d),
            note("G4", d),
            note("Bb4", d),
        ],
        [
            harmony("Am", "m7"),
            note("A4", d),
            note("C5", d),
            note("E5", d),
            note("A5", d),
        ],
        [
            harmony("D", "7"),
            note("D4", 2 * d),
            note("F#4", d),
            note("A4", d),
        ],
    ]
    notation = _measures(bars, divisions=d, beats=4, beat_type=4, fifths=0)
    tab = _measures(
        bars,
        divisions=d,
        beats=4,
        beat_type=4,
        fifths=0,
        clef_sign="TAB",
        clef_line=5,
        staff_details=True,
    )
    return document(
        "Synthetic Tab Export",
        [
            ("P1", "Synthetic Tab Export", notation),
            ("P2", "Synthetic Tab Export TAB", tab),
        ],
        composer="Fixture Generator",
    )


def pickup_cut() -> str:
    """4 bars of 2/2 whose first bar is one quarter, closed with ``light-light``."""
    d = 4
    bars = [
        [harmony("Bb", "7"), note("Bb4", 4), barline(style="light-light")],
        [harmony("Eb", "maj7"), note("F4", 16)],
        [harmony("Cm", "m7"), note("Eb4", 8), note("G4", 8)],
        [harmony("Bb", "7"), note("D4", 16)],
    ]
    measures = _measures(
        bars, divisions=d, beats=2, beat_type=2, fifths=-3, first_implicit=True
    )
    return document(
        "Synthetic Pickup Cut",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def pickup_common() -> str:
    """4 bars of 4/4 whose first bar is one quarter and has no double bar line."""
    d = 4
    bars = [
        # No harmony in the pickup bar: the tune is there and the changes have not
        # started, which is also what keeps the default grid from filling the short
        # bar with chord stabs after its single note.
        [note("C5", 4)],
        [harmony("F", "maj7"), note("A4", 16)],
        [harmony("D", "m7"), note("F4", 8), note("A4", 8)],
        [harmony("G", "7"), note("B4", 16)],
    ]
    measures = _measures(
        bars, divisions=d, beats=4, beat_type=4, fifths=0, first_implicit=True
    )
    return document(
        "Synthetic Pickup Common",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def five_four() -> str:
    """2 bars of 5/4 with ``3+2`` written as a direction.

    The melody is in quarters, so the bar has no beaming to group: the direction is
    the score's only channel for the asymmetric feel, and the fixture is what proves
    the importer reads it rather than guessing every quarter as a felt beat.
    """
    d = 4
    bars = [
        [
            direction("3+2"),
            harmony("C", "maj"),
            note("C4", 4),
            note("E4", 4),
            note("G4", 4),
            note("A4", 4),
            note("G4", 4),
        ],
        [
            harmony("F", "maj"),
            note("F4", 4),
            note("A4", 4),
            note("C5", 4),
            note("D5", 4),
            note("C5", 4),
        ],
    ]
    measures = _measures(bars, divisions=d, beats=5, beat_type=4, fifths=0)
    return document(
        "Synthetic Five Four",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def seven_four() -> str:
    """2 bars of 7/4 beamed 2+2+3: 14 eighths in groups of 4, 4 and 6.

    The grouping comes from the beaming alone; the metre's own count cannot say
    which side of the bar is long.
    """
    d = 4
    names = (
        "C4", "D4", "E4", "F4", "G4", "A4", "B4",
        "C5", "B4", "A4", "G4", "F4", "E4", "D4",
    )
    groups = (4, 4, 6)
    bars = [
        [harmony("C", "maj7")] + beamed(names, 2, groups),
        [harmony("F", "maj7")] + beamed(tuple(reversed(names)), 2, groups),
    ]
    measures = _measures(bars, divisions=d, beats=7, beat_type=4, fifths=0)
    return document(
        "Synthetic Seven Four",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def twelve_eight() -> str:
    """2 bars of 12/8 beamed 4+4+4: three four-eighth groups, not four threes.

    The beaming is the score's own statement that the bar is felt in three, which
    is exactly the case `grouping.auto` cannot derive from 12/8's count.
    """
    d = 4
    names = (
        "C4", "E4", "G4", "C5",
        "B4", "G4", "E4", "C4",
        "D4", "F4", "A4", "C5",
    )
    groups = (4, 4, 4)
    bars = [
        [harmony("C", "maj")] + beamed(names, 2, groups),
        [harmony("G", "7")] + beamed(tuple(reversed(names)), 2, groups),
    ]
    measures = _measures(bars, divisions=d, beats=12, beat_type=8, fifths=0)
    return document(
        "Synthetic Twelve Eight",
        [("P1", "Voice", measures)],
        composer="Fixture Generator",
    )


def chords_only() -> str:
    """Four bars, six changes and no pitched note.

    The content is deliberately the same six symbols the chords-only tests name;
    only the file's provenance changes.
    """
    d = 4
    bars = [
        [harmony("D", "m7"), rest(16)],
        [harmony("C", "maj7"), rest(8), harmony("G", "7"), rest(8)],
        [harmony("F", "maj7"), rest(8), harmony("B", "7"), rest(8)],
        [harmony("E", "maj7"), rest(16)],
    ]
    measures = _measures(bars, divisions=d, beats=4, beat_type=4, fifths=0)
    return document(
        "Synthetic Chords Only",
        [("P1", "Lead Sheet", measures)],
        composer="Fixture Generator",
    )


#: Every generated fixture, by the name it is committed under.  The two
#: container files are written through ``_zip``; the rest are plain MusicXML.
SCORES: Dict[str, str] = {
    "synthetic_common_8.musicxml": common_8(),
    "synthetic_cut_time.mxl": cut_time(),
    "synthetic_pickup_common.musicxml": pickup_common(),
    "synthetic_pickup_cut.musicxml": pickup_cut(),
    "synthetic_repeat_slash.musicxml": repeat_slash(),
    "synthetic_tab_export.musicxml": tab_export(),
    "synthetic_triplets.mxl": triplets(),
    "synthetic_waltz.musicxml": waltz(),
    "synthetic_five_four.musicxml": five_four(),
    "synthetic_seven_four.musicxml": seven_four(),
    "synthetic_twelve_eight.musicxml": twelve_eight(),
    "synthetic_chords_only.musicxml": chords_only(),
}


def documents() -> Dict[str, bytes]:
    """The committed bytes of every generated fixture."""
    out: Dict[str, bytes] = {}
    for name, text in SCORES.items():
        if name.endswith(".mxl"):
            member = name[: -len(".mxl")] + ".xml"
            out[name] = _zip(text, member)
        else:
            out[name] = text.encode("utf-8")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Write the fixtures, or with ``--check`` compare them."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in arguments
    changed: List[str] = []
    for name, content in documents().items():
        path = os.path.join(DATA, name)
        if check:
            try:
                with open(path, "rb") as existing:
                    if existing.read() == content:
                        continue
            except FileNotFoundError:
                pass
            changed.append(name)
            continue
        with open(path, "wb") as out:
            out.write(content)
    if check:
        if changed:
            print("fixtures differ: " + ", ".join(changed), file=sys.stderr)
            return 1
        print(f"{len(SCORES)} synthetic fixtures match")
        return 0
    print(f"wrote {len(SCORES)} synthetic fixtures")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
