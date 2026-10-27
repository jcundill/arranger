from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
from xml.etree import ElementTree

from arranger.chords import ChordParser
from arranger.grouping import grouping_allowed, parse_grouping
from headxml_model import BarInstruction, Head, HeadChange, HeadNote
from headxml_repeats import expand_repeats
from tuning import NO_CHORD, PITCH_CLASS_NAMES

# ---------------------------------------------------------------------------
# Chord symbols
# ---------------------------------------------------------------------------

# The MusicXML `kind-value` enumeration, translated into the library's qualities.
# This is the inverse of `tabxml._READABLE_KINDS`: that table says which values a
# 3.1-era reader will accept, this one says what each one *means* here.
#
# A kind the library cannot voice is absent rather than folded into a near
# neighbour, on the same principle as `chords.promote_slash_chord` beside it: an
# untranslatable chord is counted and reported, because a plausible wrong chord is
# worse than a gap the user can see. `Neapolitan`, `Italian`, `French`, `German`,
# `pedal`, `power`, `Tristan` and `none` are all absent for that reason - they are
# real MusicXML kinds, and none is a chord this library holds under a melody.
MUSICXML_KIND_QUALITIES: Dict[str, str] = {
    "major": "maj",
    "minor": "m",
    "augmented": "aug",
    "diminished": "dim7",
    "dominant": "7",
    "major-seventh": "maj7",
    "minor-seventh": "m7",
    "diminished-seventh": "dim7",
    "augmented-seventh": "7#5",
    "half-diminished": "m7b5",
    "major-minor": "mMaj7",
    "major-sixth": "6",
    "minor-sixth": "m6",
    "dominant-ninth": "9",
    "major-ninth": "maj9",
    "minor-ninth": "m9",
    # No 11th chord is voiced. A dominant 11th is played as the 9th shape, which
    # is the same four notes with the 11th left to the melody: naming the quality
    # it would be voiced as is more useful than refusing the chord.
    "dominant-11th": "9",
    "major-11th": "maj7#11",
    "minor-11th": "m9",
    "dominant-13th": "13",
    "major-13th": "maj7#11",
    "minor-13th": "m9",
    "suspended-second": "sus2",
    "suspended-fourth": "sus4",
    # MusicXML 4.0 values, which this library's own exporter downgrades on write
    # and which a third-party file may still carry.
    "suspended-fourth-seventh": "7sus4",
    "suspended-second-seventh": "7sus4",
    "suspended-fourth-ninth": "9",
    "suspended-second-ninth": "9",
}

# How a `<degree>` alters a base kind, as
# `(base quality, degree-value, degree-alter) -> refined quality`.
#
# A `<degree>` is how MusicXML spells a chord its `kind` cannot name: the kind
# gives the plain chord and the degrees say what was added, altered or removed.
# `dominant` plus a flattened 5th is a 7b5, and that is exactly how MuseScore
# writes one - see "Here's That Rainy Day", which is a third of an E7b5 under an
# F melody line.
#
# Only alterations landing on a quality the library holds are listed. An
# unrecognised degree leaves the base kind alone rather than inventing a chord the
# writer did not name: reporting a whole chord as untranslatable because one
# optional alteration is unfamiliar would lose more than it protects.
_DEGREE_REFINEMENTS: Dict[Tuple[str, int, int], str] = {
    # A dominant, which is the family the alterations actually qualify.
    ("7", 5, -1): "7b5",
    ("7", 5, 1): "7#5",
    ("7", 7, 0): "7sus4",
    ("7", 9, -1): "7b9",
    ("7", 9, 0): "9",
    ("7", 11, 1): "7#11",
    ("7", 11, -1): "7b13",
    ("7", 13, 0): "13",
    # The same alterations applied to a chord the degrees have already refined.
    # A dominant carrying both a flat 5th and a flat 9th is a real and common
    # spelling (MuseScore writes it for "Here's That Rainy Day"), and each degree
    # is applied in turn, so the second is looked up from the first's *result*.
    # Without these the chain would stop after the first degree and the chord
    # would be voiced as a 7b5 - playable, and wrong.
    ("7b5", 9, -1): "7b9",
    ("7b5", 9, 0): "9",
    ("7b5", 11, 1): "7#11",
    ("7b5", 13, 0): "13",
    ("7b9", 5, -1): "7b9",
    ("7b9", 13, 0): "13",
    ("7#5", 9, -1): "7b9",
    ("7#5", 9, 0): "9",
    ("7#11", 9, 0): "13",
    ("7b13", 9, 0): "13",
    # An extended chord, altered to a colour this library holds.
    ("9", 5, -1): "7b5",
    ("9", 5, 1): "7#5",
    ("9", 9, 0): "9",
    ("9", 9, -1): "7b9",
    ("9", 13, 0): "13",
    ("13", 5, -1): "7b5",
    ("13", 9, 0): "13",
    ("13", 11, -1): "7b13",
    # A seventh chord, altered.
    ("maj7", 9, 0): "maj9",
    ("maj7", 11, 1): "maj7#11",
    ("maj9", 11, 1): "maj7#11",
    ("m7", 5, -1): "m7b5",
    ("m7", 5, 0): "m7b5",
    ("m7", 9, 0): "m9",
    ("m7", 11, 1): "m9b5",
    ("m9", 5, -1): "m9b5",
    # A triad, extended.
    ("maj", 7, 0): "maj7",
    ("maj", 9, 0): "add9",
    ("m", 7, 0): "m7",
    ("m", 9, 0): "madd9",
    ("m", 11, 1): "m7b5",
    # A 7th added to a suspended chord. This is what `tabxml._downgrade_kinds`
    # writes when it meets a 4.0 `suspended-fourth-seventh`, so it is the reading
    # that makes this library's own export round-trip.
    ("sus4", 7, 0): "7sus4",
    ("sus2", 7, 0): "7sus4",
    ("sus4", 9, 0): "9",
    ("sus2", 9, 0): "9",
}

# A pitch name as MusicXML spells one: a step, an optional alteration, nothing
# else. Kept as a pattern so a key signature's spelling (`Fb`, `C#`) is preserved
# rather than normalised away.
_STEP_RE = re.compile(r"^([A-G])([#b]*)$")

# MusicXML pitch steps, as semitones above C.
_STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _pitch_name(
    element: Optional[ElementTree.Element], step_tag: str, alter_tag: str
) -> Optional[str]:
    """A `<root>` or `<bass>` element as a note name, or None if it has no step.

    MusicXML splits the spelling across elements, so `root-step` `B` with a
    `root-alter` of -1 is `Bb`. The alteration is a semitone offset from the step
    and is mapped back to accidentals, which is exact for the double sharps and
    flats a key signature can produce.

    A step carrying three or more accidentals is enharmonically respelled to the
    single accidental the library prefers. The chord is the same chord and only
    the spelling changes, which matters because the library spells flats
    throughout (`PITCH_CLASS_NAMES`) and musthe cannot read `B#`.
    """
    if element is None:
        return None
    step = (element.findtext(step_tag) or "").strip()
    if not step:
        return None
    alter = _number(element.findtext(alter_tag))
    if len(step) > 2:
        return PITCH_CLASS_NAMES[(_STEP_SEMITONES.get(step[0], 0) + alter) % 12]
    if _STEP_RE.match(step) is None:
        return None
    return step + ("#" * alter if alter > 0 else "b" * -alter if alter < 0 else "")


def _number(text: Optional[str], default: int = 0) -> int:
    """A MusicXML numeric field, defensively: an unusable one is `default`.

    `<duration>`, `<alter>` and `<octave>` are all written as decimals by some
    exporters, and a missing or malformed one is not worth losing a note over.
    """
    try:
        return int(round(float(text)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _degree_quality(base: str, degrees: Sequence[ElementTree.Element]) -> str:
    """A base quality with its `<degree>` alterations folded in.

    The degrees are applied in document order, each refining the result of the
    last, so a chord written as a kind plus several alterations lands on the
    quality the writer meant rather than on whichever single degree happened to be
    recognised. An unrecognised degree is ignored rather than treated as an error:
    the base kind is still a real chord, and declaring a whole chord
    untranslatable because one optional alteration is unfamiliar would lose more
    than it protects.
    """
    quality = base
    for degree in degrees:
        value_text = degree.findtext("degree-value")
        if not value_text:
            continue
        value = _number(value_text, -1)
        alter = _number(degree.findtext("degree-alter"))
        # A `subtract` removes a tone the kind already carries, and is keyed by
        # nothing here: dropping a 7th from a dominant leaves a triad this library
        # would rather not guess at, so the kind stands as written.
        if (degree.get("type") or "alter").strip().lower() == "subtract":
            continue
        refined = _DEGREE_REFINEMENTS.get((quality, value, alter))
        if refined is not None:
            quality = refined
    return quality


def parse_musicxml_chord(
    harmony: ElementTree.Element,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Splits a `<harmony>` element into (root, quality, slash bass).

    The root comes from `<root>`, which is always present and is not the thing in
    question: the root of a sus chord or an altered chord is unambiguous even when
    its kind is not. The quality is resolved in a fixed order of preference:

    1. the `<kind>` element, through MUSICXML_KIND_QUALITIES;
    2. that kind refined by its `<degree>` children, so `dominant` with a flat 5th
       is a 7b5 rather than a plain 7;
    3. the `text` attribute, through `ChordParser`, for the chords the format
       itself has no kind for.

    Step 3 is not a nicety: it is how `tabxml` writes a name music21 cannot
    classify (`<kind text="Bb7sus4">other</kind>`), so without it a round trip of
    this library's own export would lose every chord it could not spell. It is
    also where a chord symbol written freehand ends up.

    The `<bass>` is split out and returned rather than glued onto the quality,
    because `ChordParser` would then fail every table lookup - the same trap
    `slots._slash_bass` documents for a slash chord in a symbol.

    `quality` is None for a chord this library cannot voice, and the caller counts
    it: a wrong-but-plausible quality is worse than a reported gap.
    """
    root = _pitch_name(harmony.find("root"), "root-step", "root-alter")
    if root is None:
        return None, None, None

    kind = harmony.find("kind")
    quality: Optional[str] = None
    if kind is not None and kind.text:
        base = MUSICXML_KIND_QUALITIES.get(kind.text.strip())
        if base is not None:
            quality = _degree_quality(base, harmony.findall("degree"))

    if quality is None and kind is not None:
        text = (kind.get("text") or "").strip()
        if text:
            parsed_root, text_quality = ChordParser.parse_chord_name(text)
            if parsed_root == root and text_quality:
                quality = ChordParser.canonical_quality(text_quality) or None

    if quality is not None and quality not in ChordParser.CHORD_TONES_FROM_ROOT:
        # A table entry naming a spelling the voicing tables do not hold would
        # fail silently later, so it reports as untranslatable instead.
        quality = None

    return root, quality, _pitch_name(harmony.find("bass"), "bass-step", "bass-alter")


def _chord_symbol(harmony: ElementTree.Element) -> str:
    """The chord as the file spells it, for the untranslatable report.

    Used only when a chord could not be translated, so the user is told which
    symbol was dropped rather than that "a chord" was.
    """
    kind = harmony.find("kind")
    text = (kind.get("text") if kind is not None else "") or ""
    if text.strip():
        return text.strip()
    root = _pitch_name(harmony.find("root"), "root-step", "root-alter")
    value = (kind.text if kind is not None else "") or ""
    return f"{root or '?'}{value}".strip()


# ---------------------------------------------------------------------------
# Reading the document
# ---------------------------------------------------------------------------


def _read_document(path: Union[str, Path]) -> bytes:
    """The score's bytes from a `.musicxml` file or a zipped `.mxl` container.

    A compressed score is read through its `META-INF/container.xml`, which names
    the root file. Taking "the first `.xml` in the archive" looks equivalent and is
    not: a container may carry a `score.xml` beside a stylesheet, a thumbnail or a
    second variant, and picking the wrong one is a silent failure rather than an
    error. The largest XML member is the fallback when the container is missing or
    unusable, which beats a hard failure on a perfectly readable score.

    "Unusable" includes a container that is not well-formed XML, which is not
    hypothetical: a score whose filename carries an apostrophe is written by some
    notation programs as `<rootfile full-path='Core 'ngrato.xml'/>`, an unescaped
    quote that no XML parser will accept. 93 of the 502 files in the OpenEWLD
    corpus are built that way, and every one of them holds a perfectly readable
    score - so a `ParseError` here must fall through to the fallback rather than
    propagate, which is the whole point of having one.

    A file that is not a zip is read as a bare document, so a mislabelled `.mxl`
    still works.
    """
    source = Path(path)
    raw = source.read_bytes()
    if raw.lstrip()[:2] != b"PK":
        return raw
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if "META-INF/container.xml" in names:
            try:
                container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            except ElementTree.ParseError:
                # Malformed container, readable score: fall through to the
                # largest-member fallback rather than failing the whole file.
                container = None
            if container is not None:
                rootfile = container.find("rootfiles/rootfile")
                full_path = rootfile.get("full-path") if rootfile is not None else None
                if full_path and full_path in names:
                    return archive.read(full_path)
        candidates = [n for n in names if n.lower().endswith((".xml", ".musicxml"))]
        if not candidates:
            raise ValueError(f"{source} is a zip with no MusicXML document in it")
        return archive.read(max(candidates, key=lambda n: archive.getinfo(n).file_size))


def _part_is_tab(part: ElementTree.Element) -> bool:
    """True for a TAB part, which is not a melody and must not be read as one.

    A score this library exported carries both a notation staff and a TAB staff.
    The TAB staff is the *same music* with frets attached, so reading it would
    appear to work - and would double every note, because a MusicXML tab staff
    writes one `<note>` per sounding string. The notation staff is the melody.
    """
    for attributes in part.iter("attributes"):
        for clef in attributes.findall("clef"):
            if (clef.findtext("sign") or "").strip() == "TAB":
                return True
        details = attributes.find("staff-details")
        if details is not None and (details.findtext("staff-lines") or "").strip() == "6":
            return True
    return False


def _part_note_count(part: ElementTree.Element) -> int:
    """How many pitched notes a part has.

    The notes are reached through their measures, which is where MusicXML puts
    them: a `<note>` is a child of a `<measure>`, never of the `<part>` itself.
    """
    return sum(
        1
        for measure in part.findall("measure")
        for note in measure.findall("note")
        if note.find("pitch") is not None
    )


def _part_harmony_count(part: ElementTree.Element) -> int:
    """How many `<harmony>` symbols a part declares, used alongside the note count.

    The counterpart of `_part_note_count`, and the reason a **chords-only lead
    sheet** is a readable part: such a score has zero pitched notes, so a selection
    rule keyed on notes alone calls the file unreadable even though its whole
    content is the chord timeline (§9.3 step A' of `docs/comping-styles.md`).
    """
    return sum(
        len(measure.findall("harmony")) for measure in part.findall("measure")
    )


def _choose_part(
    parts: Sequence[ElementTree.Element], part_id: Optional[str]
) -> Optional[ElementTree.Element]:
    """The part to read the head from.

    An explicit id wins. Otherwise TAB staves are excluded - this library's own
    export has one, and its notes are the same music written per string - and the
    part with the most pitched notes wins, which is the melody rather than a
    doubling staff.

    **A part with chords but no notes is readable too.** A chords-only lead sheet
    carries no melody, so a rule keyed on `_part_note_count` alone reported the file
    as having no readable part and refused it. Scoring on `(notes, chords)` keeps the
    melody winning wherever both exist - the note count is the first key - while a
    score that has only changes still yields the chord part rather than `None`.
    """

    def score(part: ElementTree.Element) -> Tuple[int, int]:
        return (_part_note_count(part), _part_harmony_count(part))

    if part_id is not None:
        for candidate in parts:
            if candidate.get("id") == part_id:
                return candidate
        return None
    readable = [p for p in parts if not _part_is_tab(p) and score(p) != (0, 0)]
    if not readable:
        readable = [p for p in parts if score(p) != (0, 0)]
    if not readable:
        return None
    return max(readable, key=score)


def _score_metadata(
    root: ElementTree.Element, part_id: Optional[str]
) -> Tuple[str, str, str]:
    """(title, composer, part name) for the CLI header."""
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
    composer = ""
    for creator in root.findall("identification/creator"):
        if (creator.get("type") or "").strip() == "composer":
            composer = (creator.text or "").strip()
            break
    part_name = ""
    if part_id is not None:
        for score_part in root.findall("part-list/score-part"):
            if score_part.get("id") == part_id:
                part_name = (score_part.findtext("part-name") or "").strip()
                break
    return title, composer, part_name


def _time_signature(part: ElementTree.Element) -> Tuple[int, int]:
    """The notated (beats, beat-type) of the last `<time>` that states one.

    A score may change metre and the first `<time>` is not the one in force for
    most of the piece, so the **last** stated signature is used. A head that
    changes metre is laid out in its prevailing metre, which is a limitation worth
    naming rather than a silent mis-render.

    The beat *type* is kept as well as the count, because most standards are
    written in cut time: a 2/2 and a 2/4 bar are both two beats wide, and
    reporting one as the other misstates the metre the tune is in.
    """
    beats, beat_type = 4, 4
    for time in part.iter("time"):
        stated = (time.findtext("beats") or "").strip()
        if stated.isdigit() and int(stated) > 0:
            beats = int(stated)
        stated_type = (time.findtext("beat-type") or "").strip()
        if stated_type.isdigit() and int(stated_type) > 0:
            beat_type = int(stated_type)
    return beats, beat_type


def _key_signature(part: ElementTree.Element) -> Tuple[int, str]:
    """The `(fifths, mode)` of the last `<key>` that states one.

    **`fifths` is the number of sharps (positive) or flats (negative)** that the
    signature carries, and it is the one number every notation convention agrees on:
    -3 is Eb major *or* C minor, which is why `mode` is read beside it. MusicXML
    allows `<mode>` to be absent, so the default is `""` - "a signature, and no
    claim about which of its two keys this is" - rather than a guessed `major`.

    The **last** stated signature wins, for the same reason as the metre: a score
    may modulate, and a head is arranged in the key it ends in rather than the one
    it starts in.

    An out-of-range or unparseable `fifths` is read as 0 (C major). MusicXML caps it
    at -7..7 for a conventional signature, so anything wider is a notation program's
    own spelling convention rather than a key this library could state.
    """
    fifths, mode = 0, ""
    for key in part.iter("key"):
        stated = (key.findtext("fifths") or "").strip()
        try:
            value = int(round(float(stated)))
        except (TypeError, ValueError):
            continue
        if -7 <= value <= 7:
            fifths = value
        stated_mode = (key.findtext("mode") or "").strip().lower()
        if stated_mode in ("major", "minor"):
            mode = stated_mode
    return fifths, mode


#: A metronome's beat-unit as a length in quarter notes, so a dotted-quarter pulse
#: in 12/8 can be compared with the bar's own denominator.
_BEAT_UNIT_QUARTERS: Dict[str, Fraction] = {
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
    "128th": Fraction(1, 32),
    "256th": Fraction(1, 64),
}

#: A written grouping in a direction: `3+2`, `2 + 2 + 3`, and nothing looser. The
#: lookarounds keep it from matching the tail of a longer number.
_GROUPING_TEXT = re.compile(r"(?<!\d)(\d+(?:\s*\+\s*\d+)+)(?!\d)")


def _grouping_hint(direction: ElementTree.Element) -> Optional[str]:
    """The first `N+N` a direction writes, from a `<words>` or `<rehearsal>` mark.

    A lead sheet can state a grouping in prose when the beaming cannot: a 5/4
    written in quarters has no beams to group, and "3+2" is how a player is told
    which side of the bar is long. Read at the direction layer so the mark reaches
    the walk even when it precedes no note; `_score_grouping` validates it against
    the bar before using it.
    """
    for direction_type in direction.findall("direction-type"):
        for child in direction_type:
            if child.tag not in ("words", "rehearsal"):
                continue
            text = " ".join(child.itertext()).strip()
            match = _GROUPING_TEXT.search(text)
            if match is not None:
                return match.group(1).strip()
    return None


def _metronome_pulse(direction: ElementTree.Element) -> Optional[Fraction]:
    """The pulse a `<metronome>` mark states, in quarter notes, dots included.

    A dotted-quarter mark in 12/8 is the score saying "feel this in four" in the
    one other channel that can state it when the notes are not beamed. Only the
    beat unit is read; the tempo is not this library's business.
    """
    for metronome in direction.iter("metronome"):
        unit = (metronome.findtext("beat-unit") or "").strip().lower()
        pulse = _BEAT_UNIT_QUARTERS.get(unit)
        if pulse is None:
            continue
        for _dot in metronome.findall("beat-unit-dot"):
            pulse *= Fraction(3, 2)
        return pulse
    return None


def _starts_a_beam(note: ElementTree.Element) -> bool:
    """True when the note begins a primary (number-1) beam."""
    for beam in note.findall("beam"):
        if (beam.get("number") or "1") != "1":
            continue
        if (beam.text or "").strip() == "begin":
            return True
    return False


def _beam_partition(
    offsets: Sequence[float], beats: int
) -> Optional[Tuple[int, ...]]:
    """The grouping a bar's primary-beam starts state, if they partition it.

    `offsets` are beat offsets from the bar's start, one per beam group that begins
    there. A group lasts until the next group begins, and the last until the bar
    ends. Anything that does not give whole, positive group lengths adding to the
    bar is not a statement about the metre - a beam that starts mid-bar, crosses a
    bar line, or follows a rest - and is refused rather than rounded into one.
    """
    unique = sorted({round(offset, 6) for offset in offsets})
    if not unique or abs(unique[0]) > 1e-6:
        return None
    positions = unique + [float(beats)]
    lengths = [later - earlier for earlier, later in zip(positions, positions[1:])]
    rounded = tuple(int(round(length)) for length in lengths)
    if any(abs(length - whole) > 1e-6 for length, whole in zip(lengths, rounded)):
        return None
    if any(length <= 0 for length in rounded):
        return None
    if sum(rounded) != beats:
        return None
    return rounded


def _beams_decide(beats: int, beat_type: int) -> bool:
    """Whether the score's beaming can outrank the metre's own convention.

    A conventional simple metre - 2/4, 3/4, 4/4, 2/2 - is already grouped by its
    count, and notation programs beam eighths in whatever pairs or fours fit the
    beat. Reading that as a grouping would turn a half-bar beam in 4/4 into two
    felt beats. A compound or asymmetric metre is where beaming carries
    information the count cannot, so it is read there.
    """
    return not (beat_type <= 4 and beats in (2, 3, 4))


def _score_grouping(
    beats: int,
    beat_type: int,
    hints: Sequence[str],
    beam_starts: Dict[Tuple[int, int], List[float]],
    pulses: Sequence[Fraction],
    skip_bar: Optional[int] = None,
) -> Tuple[Tuple[int, ...], str]:
    """The grouping the score states, and the channel that stated it.

    Precedence is the written mark, then the beaming, then a metronome pulse. Each
    candidate is used only if it partitions the bar; an unreadable one falls
    through, because a stray `3+2` in a lyric or a mark on a bar of another metre
    is not a broken score. No candidate leaves `((), "")`, which the engine reads
    as `auto`.
    """
    for hint in hints:
        try:
            grouping = parse_grouping(hint)
        except ValueError:
            continue
        if isinstance(grouping, tuple) and grouping_allowed(grouping, beats)[0]:
            return grouping, "text"
    if _beams_decide(beats, beat_type):
        # The same grouping should recur in most bars; a single unusual bar's
        # beams do not redefine the tune. Ties go to the earliest bar.
        counts: Dict[Tuple[int, ...], int] = {}
        first: Dict[Tuple[int, ...], int] = {}
        for (bar, _voice), offsets in beam_starts.items():
            if bar == skip_bar:
                # A pickup is short by design, so its last beam would run to a bar
                # line that is not there; the full bars after it state the metre.
                continue
            partition = _beam_partition(offsets, beats)
            if partition is None:
                continue
            counts[partition] = counts.get(partition, 0) + 1
            first.setdefault(partition, bar)
        if counts:
            chosen = max(counts, key=lambda item: (counts[item], -first[item]))
            return chosen, "beams"
    for pulse in pulses:
        pulse_units = pulse * beat_type / 4
        if pulse_units.denominator != 1:
            continue
        length = int(pulse_units)
        if length > 0 and beats % length == 0:
            return (length,) * (beats // length), "metronome"
    return (), ""


def _transposition(part: ElementTree.Element) -> int:
    """The part's `<transpose>` in semitones, or 0 when it declares none.

    MusicXML defines `<transpose>` as **what is added to a written pitch to get the
    sounding pitch**, so a guitar part - written an octave above what it sounds -
    states octave-change -1, and a Bb instrument states chromatic -2. Both spellings
    the format allows are summed here, `<chromatic>` plus twelve per
    `<octave-change>`, because a writer may state an octave either way. `<diatonic>`
    is deliberately ignored: it selects an enharmonic *spelling*, and this reader
    wants the pitch itself, which `<chromatic>` already fixes.

    The **last** stated value wins, for the same reason as the metre and the key: a
    score that changes instrument states it again, and a melody is read at concert
    pitch for the instrument it ends on. An absent or unparseable value is 0, which
    is concert pitch.
    """
    transposition = 0
    for element in part.iter("transpose"):
        chromatic = _number(element.findtext("chromatic"), 0)
        octave_change = _number(element.findtext("octave-change"), 0)
        stated = chromatic + 12 * octave_change
        if stated:
            transposition = stated
    return transposition


def _midi(pitch: ElementTree.Element) -> Optional[int]:
    """A `<pitch>` as a MIDI number, or None if its spelling is unusable."""
    step = (pitch.findtext("step") or "").strip()
    if step not in _STEP_SEMITONES:
        return None
    octave = _number(pitch.findtext("octave"), -1)
    return (octave + 1) * 12 + _STEP_SEMITONES[step] + _number(pitch.findtext("alter"))


def _duration_in_divisions(note: ElementTree.Element, divisions: int = 0) -> int:
    """A note's length in divisions, **already divided down** if the writer reduced it.

    MusicXML's specification says a tuplet's `<duration>` is *unreduced*: three
    eighth-note triplets are written as six divisions each, so a reader must divide
    them by three or the bar runs a third long. **Real writers do not agree**, so the
    reader must decide which convention a file used.

    The two conventions are not distinguishable by arithmetic on the value alone: the
    fixture's triplet quarter is written `6720` in the divisions of 10080, and 6720
    divides cleanly both as "already reduced" (6720/10080 = 2/3) and as "unreduced"
    (6720 x 2/3 = 4480). Deciding per measure is no better - 24 of the 36 measures in
    `synthetic_triplets.mxl` come out a whole number of bars under **both** readings.

    What does decide it is the **relationship to `<type>`**, which states the note's
    nominal value:

    | `<type>` | written | of a nominal quarter | reading |
    |---|---|---|---|
    | `quarter` | 10080 | exactly 1.0 | plain |
    | `quarter` | **6720** | **exactly 2/3** | **already reduced** - a triplet quarter is 2/3 of a quarter |
    | `quarter` | 4480 | 4/9 | neither; treated as unreduced, per the spec |

    So: if the written value is *already* `normal/actual` of its nominal, take it as
    it stands; otherwise divide, as the specification says. The first row of that table
    is what makes the rule safe - a tuplet quarter is **2/3 of a quarter**, and dividing
    6720 produced **4/9**, a whole third of the true length. Three such notes spanned
    4/3 of a quarter where the figure must fill two.

    A wrong `duration` is invisible to everything but the MusicXML writer: onsets stay
    correct because the cursor is re-based per bar from `bar_index`, and tablature
    ignores `duration` entirely. music21 refuses an inexpressible one outright
    ("Cannot convert inexpressible durations to MusicXML"). `docs/renderers.md` §"A rest
    is not a note, but it is time" holds the measurement.
    """
    duration = _number(note.findtext("duration"))
    modification = note.find("time-modification")
    if modification is None:
        return duration
    actual = _number(modification.findtext("actual-notes"), 1)
    normal = _number(modification.findtext("normal-notes"), 1)
    if actual <= 0 or normal <= 0 or actual == normal:
        return duration
    if divisions > 0 and _duration_is_already_reduced(
        note, duration, divisions, actual, normal
    ):
        return duration
    return duration * normal // actual


#: `<type>` to its length in quarters. The nominal value a written duration is measured
#: against to decide whether a writer reduced a tuplet already - see
#: `_duration_in_divisions`, which is the only user.
_TYPE_IN_QUARTERS: Dict[str, float] = {
    "maxima": 32.0, "long": 16.0, "breve": 8.0, "whole": 4.0, "half": 2.0,
    "quarter": 1.0, "eighth": 0.5, "16th": 0.25, "32nd": 0.125, "64th": 0.0625,
    "128th": 0.03125, "256th": 0.015625,
}


def _duration_is_already_reduced(
    note: ElementTree.Element, duration: int, divisions: int, actual: int, normal: int
) -> bool:
    """Whether this note's written duration is already `normal/actual` of its `<type>`.

    True for a writer that reduced the value, false for one following the
    specification's unreduced convention. `<type>` is what makes the question
    answerable: without a nominal value to measure against, 6720 is divisible both ways
    and the two conventions are the same number.
    """
    modification = note.find("time-modification")
    # `<normal-type>` is the tuplet's own nominal value and is the better of the two
    # sources; `<type>` is the fallback for a file that omits it.
    nominal_text = ""
    if modification is not None:
        nominal_text = (modification.findtext("normal-type") or "").strip()
    if not nominal_text:
        nominal_text = (note.findtext("type") or "").strip()
    nominal = _TYPE_IN_QUARTERS.get(nominal_text)
    if nominal is None or divisions <= 0 or nominal <= 0:
        # No nominal to measure against, so the specification's reading is the only
        # defensible one: a note that says nothing about itself is taken unreduced.
        return False
    # **`<divisions>` is per QUARTER note, not per whole note.** MusicXML defines it as
    # "the number of duration units in a quarter note", so 10080 divisions is a quarter
    # and 6720/10080 is already 2/3 - multiplying by four here read the file as 1/6 and
    # rejected a value it should have accepted.
    written_quarters = duration / divisions
    # Already reduced when the written value *is* normal/actual of the nominal - to
    # within a division, since a reduced value is not always an exact multiple.
    reduced = written_quarters * actual / normal
    return abs(reduced - nominal) <= 1.0 / divisions + 1e-9


def _is_tuplet(note: ElementTree.Element) -> bool:
    """Whether this note is written as part of a tuplet.

    A **marker read from the file**, not a property deduced from the duration.
    MusicXML says so explicitly with `<time-modification>`, and the deduction is not
    merely worse but wrong: under `eighths` a plain eighth lasts half a grid step,
    so "the duration is not a whole number of steps" holds for ordinary eighths as
    well as for triplets, and using it re-spaced every eighth in the head.
    """
    modification = note.find("time-modification")
    if modification is None:
        return False
    actual = _number(modification.findtext("actual-notes"), 1)
    normal = _number(modification.findtext("normal-notes"), 1)
    return actual > 0 and normal > 0 and actual != normal


def _stops_a_tie(note: ElementTree.Element) -> bool:
    """True when the note is tied from a previous one, so it extends that note."""
    return any(tie.get("type") == "stop" for tie in note.findall("tie"))


def _beat_from_onset(onset: float, divisions: int, beat_type: int) -> float:
    """The **notated beat** within the bar that a note `onset` divisions into falls on.

    `onset / divisions` counts *quarters* - MusicXML defines `<divisions>` as the number
    of duration units in a quarter note - and a beat is `4 / beat_type` quarters, so the
    conversion is `onset/divisions * beat_type/4`. It is spelled out once because a
    `<harmony>` and the note it governs must not be able to disagree about which beat
    they are on: both callers go through here.

    **`beats_per_bar` is not that factor, and using it was a real defect.** The two agree
    only when the numerator equals the denominator - 4/4 and 2/2, which is six of the
    seven committed heads - so bar 1 of the 3/4 `synthetic_waltz` read 1.375, 1.75,
    2.125, 2.5, 2.875 for six written eighths, i.e. a whole bar of music in 2.25 of its
    3 beats, and every `--musicxml` round trip squeezed it by another 0.75. `beat_type`
    is the denominator, and a count without one is not a metre - `AGENTS.md` trap 9, the
    same family `docs/renderers.md` lists four renderer bugs from.
    """
    return 1.0 + (onset / divisions) * (beat_type / 4.0)


@dataclass
class _NotesWalk:
    """One part's walk, and everything it remembers between elements.

    The importer's read is a single pass with a lot of carried state: the chord in
    force, the `<chord>` group being assembled, the cursor, the measure numbers, the
    things skipped. Those are fields here rather than locals because each stage -
    the measure header, one `<harmony>`, one `<note>`, the flush - reads and writes
    most of them, and a stage that had to thread fourteen values in and out would be
    harder to read than the one function they came from.

    The order of the fields is the order the walk fills them, so the value reads as
    the state rather than as a bag.
    """

    part: ElementTree.Element
    head: Head
    transposition: int = 0

    beat_type: int = 0
    # The chord in force: a `<harmony>` holds until the next one replaces it.
    chord: str = NO_CHORD
    quality: Optional[str] = NO_CHORD
    bass: Optional[str] = None
    unmapped: List[str] = field(default_factory=list)
    skipped: Dict[str, int] = field(default_factory=dict)
    notes: List[HeadNote] = field(default_factory=list)
    # The chord timeline, built as the document is walked so `cursor` is the position
    # each `<harmony>` occupies. Separate from `notes` because a `<harmony>` can
    # precede nothing at all - see `HeadChange` and open-issues item 1.
    changes: List[HeadChange] = field(default_factory=list)
    # The `<chord>` group being assembled at the current cursor: (pitch, length),
    # together with the onset it started at, whether it ends a tie, and the lyrics
    # on its first member. Flushed when the next unmarked note - or the bar line -
    # proves the group is complete.
    group: List[Tuple[int, int]] = field(default_factory=list)
    group_onset: int = 0
    group_tie: bool = False
    group_tuplet: bool = False
    group_chord: str = NO_CHORD
    group_quality: Optional[str] = NO_CHORD
    group_bass: Optional[str] = None
    group_lyrics: Tuple[str, ...] = ()
    divisions: int = 1
    bar: int = 1
    bar_index: int = 1
    cursor: int = 0
    # Every measure number walked, in document order, so `Head.bars` is a fact about
    # the file rather than about the melody (§9.3 step A'). The first and last are
    # what `bars` reports; a chords-only head has no notes to derive them from.
    measure_numbers: List[int] = field(default_factory=list)
    # Play-order instructions (repeats, endings and navigation signs) keyed by the
    # measure's **document position**, not its written number: a score's measure numbers
    # can be non-contiguous, and the expansion walks positions in order. Consumed by
    # `expand_repeats` after the walk; empty for a score with no barlines or directions
    # of interest, which is every committed head but the three that carry a repeat.
    raw_markers: Dict[int, List[BarInstruction]] = field(default_factory=dict)
    position: int = 0
    # The score's own grouping evidence, in the order `_score_grouping` weighs it:
    # `N+N` marks from directions, then the beat offset of every primary-beam
    # start keyed by (written bar, voice), then metronome pulses in quarter notes.
    grouping_hints: List[str] = field(default_factory=list)
    beam_starts: Dict[Tuple[int, int], List[float]] = field(default_factory=dict)
    metronome_pulses: List[Fraction] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.beat_type = int(self.head.beat_type)

    def run(self) -> None:
        """Walk every measure, then fill the head and report what was left out."""
        for measure in self.part.findall("measure"):
            self.measure(measure)

        head = self.head
        head.notes = self.notes
        head.chords = self.changes
        head.grouping, head.grouping_source = _score_grouping(
            head.beats_per_bar,
            int(head.beat_type),
            self.grouping_hints,
            self.beam_starts,
            self.metronome_pulses,
            skip_bar=(
                self.measure_numbers[0]
                if head.first_bar_implicit and self.measure_numbers
                else None
            ),
        )
        # The file's measure extent, so `Head.bars` reports the file's length rather
        # than the melody's - which is what makes a chords-only head arrangeable at
        # all (§9.3 step A'). Recorded here because this is the one place the measures
        # are walked.
        if self.measure_numbers:
            head.measure_range = (self.measure_numbers[0], self.measure_numbers[-1])
        # A bar the melody never enters and a bar with no notes at all are still
        # walked, so their barlines and directions are read too. Expand the repeat now
        # that every measure, marker, note and change is in hand: `expand_repeats`
        # rewrites `bar` to the absolute play-order position, sets `Head.markers` and
        # updates `measure_range`. It is a no-op (byte-identical) on a score with no
        # repeat, and returns the report lines for a form it could not honour.
        play_notes = expand_repeats(head, self.measure_numbers, self.raw_markers)
        head.unmapped = tuple(dict.fromkeys(self.unmapped))
        head.skipped = tuple(
            f"{count} {reason}" for reason, count in sorted(self.skipped.items())
        )
        report: List[str] = []
        if self.unmapped:
            report.append(
                f"{len(self.unmapped)} chord(s) this library cannot voice were left out: "
                + ", ".join(sorted(set(self.unmapped)))
            )
        report.extend(head.skipped)
        report.extend(play_notes)
        head.report = tuple(report)

    def skip(self, reason: str) -> None:
        """Count one skipped element, by reason, for the head's report."""
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


    def measure(self, measure: ElementTree.Element) -> None:
        """Read one measure: its header, its elements, and the group it leaves open.

        The cursor runs in **divisions** and is converted on the way out, because
        `divisions` is stated per measure and a score may change it; a single running
        total in quarters would drift the moment it did. `<backup>` and `<forward>`
        move the cursor without sounding anything and are honoured, so a part with
        several voices does not desync - the melody is read at the position the file
        says it is at, whatever the other voices do.

        A measure number that is not an integer ("12a", a pickup numbered "0") is not
        discarded: the measure is read at its running index and reported, because
        losing a bar of a head over a label is a poor trade.
        """
        for attributes in measure.findall("attributes"):
            stated = attributes.findtext("divisions")
            if stated:
                self.divisions = max(1, _number(stated, self.divisions))

        number = (measure.get("number") or "").strip()
        if re.match(r"^-?\d+$", number):
            self.bar = self.bar_index = int(number)
        else:
            self.bar = self.bar_index
            if number:
                self.skip(f'measures not numbered with an integer ("{number}")')
        if not self.measure_numbers:
            # The source's own statement that bar 1 is an anacrusis. A pickup
            # numbered 0 says the same thing in the older spelling. Anything
            # else - including an unmarked short first bar - is left `None` so
            # the renderers infer the pickup from the bar's own content rather
            # than treating it as a stated whole bar.
            if (
                (measure.get("implicit") or "").strip().lower() == "yes"
                or self.bar == 0
            ):
                self.head.first_bar_implicit = True
        self.measure_numbers.append(self.bar)

        for barline in measure.findall("barline"):
            self.raw_markers.setdefault(self.position, []).extend(
                _parse_barline(barline)
            )
            # A double barline after bar 1 is the notation's statement that the
            # first bar is an anacrusis - the music stops mid-measure and the form
            # begins in the next bar. Only bar 1 is checked: a double barline
            # elsewhere is a section change, not a pickup.
            if len(self.measure_numbers) == 1 and self.bar == 1:
                for style in barline.findall("bar-style"):
                    if (style.text or "").strip() == "light-light":
                        self.head.first_bar_ends_with_double_barline = True

        self.cursor = 0
        self.group.clear()
        for child in measure:
            self.element(child)
        # A group still open at the end of a bar is closed by the bar line. The
        # MusicXML it came from is malformed, but reading the notes is better than
        # losing the last chord of the bar.
        self.flush()
        self.group.clear()
        self.position += 1
        self.bar_index = self.bar + 1

    def element(self, child: ElementTree.Element) -> None:
        """Dispatch one child of a measure: cursor moves, a chord symbol, a note, or a
        navigation direction.

        `<direction>` and `<sound>` are bar-level instructions rather than cursor
        events, so they are recorded against the measure being walked and move nothing.
        A `<sound>` nested inside a `<direction>` is read by `_parse_direction`; the
        direct-child branch is the older spelling of the same element.
        """
        if child.tag == "backup":
            self.cursor = max(0, self.cursor - _number(child.findtext("duration")))
        elif child.tag == "forward":
            self.cursor += _number(child.findtext("duration"))
        elif child.tag == "harmony":
            self.harmony(child)
        elif child.tag == "note":
            self.note(child)
        elif child.tag == "direction":
            hint = _grouping_hint(child)
            if hint is not None:
                self.grouping_hints.append(hint)
            pulse = _metronome_pulse(child)
            if pulse is not None:
                self.metronome_pulses.append(pulse)
            for instruction in _parse_direction(child):
                self.raw_markers.setdefault(self.position, []).append(instruction)
        elif child.tag == "sound":
            for instruction in _parse_sound(child):
                self.raw_markers.setdefault(self.position, []).append(instruction)

    def harmony(self, child: ElementTree.Element) -> None:
        """Read one `<harmony>`: the chord in force, and a change on the timeline."""
        root_name, parsed_quality, parsed_bass = parse_musicxml_chord(child)
        if root_name is None or parsed_quality is None:
            # Counted, never guessed: a wrong chord under a good melody is
            # worse than a gap the user can see reported.
            self.unmapped.append(_chord_symbol(child))
            return
        self.chord = f"{root_name}{parsed_quality}"
        self.quality = parsed_quality
        self.bass = parsed_bass
        # **Recorded as well as held.** The fields above are the forward fill the
        # melody path reads, and they are correct; what they cannot do is describe a
        # `<harmony>` no note ever reaches, because the only place they are written
        # out is `group_chord` on the next note. This append is the whole of phase 1:
        # the timeline exists, and nothing consumes it yet.
        #
        # **The beat conversion is `_beat_from_onset`'s, not `cursor / divisions`.**
        # `cursor/divisions` is quarters and a beat is `4 / beat_type` of them, and the
        # one function is called from both places so a `<harmony>` and the note it
        # precedes can never disagree about which beat they are on. It must use
        # `beat_type`, not `beats_per_bar` - the denominator trap, which is invisible
        # while the numerator and the denominator happen to be equal.
        #
        # `cursor` rather than `group_onset`, because the element sits *before*
        # whatever follows it: a `<harmony>` after the bar's last note is recorded on
        # the beat it occupies and in force into the next bar.
        #
        # 6 of the 154 `<harmony>` elements on the committed scores are followed by no
        # note at all, so this is a real loss and not an edge case. See `HeadChange`
        # and `docs/history/open-issues.md` item 1.
        self.changes.append(
            HeadChange(
                bar=self.bar,
                written_bar=self.bar,
                beat=_beat_from_onset(self.cursor, self.divisions, self.beat_type),
                chord=self.chord,
                quality=self.quality,
                bass=self.bass,
            )
        )


    def note(self, child: ElementTree.Element) -> None:
        """Read one `<note>`: time only, or a pitch that may open a `<chord>` group."""
        if child.find("grace") is not None:
            self.skip("grace notes")
            # A grace note has no `<duration>` of its own - it borrows the
            # length of the note it decorates - so it occupies no cursor time
            # and must *not* be added here or it would be counted twice.
            return
        if child.find("cue") is not None:
            self.skip("cue notes")
            if child.find("chord") is None:
                self.cursor += _duration_in_divisions(child, self.divisions)
            return
        # A rest is not a melody note, but it is still *time*: the cursor has to
        # move past it or every note after it is read too early - bar 1 of "But
        # Not For Me" is a quarter rest followed by three quarter notes, so dropping
        # the rest's length moves the whole head a beat early and fills a bar a rest
        # should have shared. Every skip below leaves the cursor alone only where the
        # element really occupies no time; a rest, a grace note and a cue note all do. `docs/renderers.md` §"A rest is not a note, but it is time"
        # holds the worked example.
        pitch_element = child.find("pitch")
        if pitch_element is None:
            self.skip("rests and unpitched notes")
            # Not a `<chord>` member, so it advances the cursor in its own right.
            if child.find("chord") is None:
                self.cursor += _duration_in_divisions(child, self.divisions)
            return
        written = _midi(pitch_element)
        if written is None:
            self.skip("notes with an unreadable pitch")
            return
        # Written pitch to sounding: `<transpose>` is what is added to a written
        # note to get the sounding one, so a guitar part - octave-change -1 - is
        # read a whole octave below its notation. See `_transposition`.
        pitch = written + self.transposition

        length = _duration_in_divisions(child, self.divisions)
        onset = self.cursor
        if _starts_a_beam(child):
            voice = _number(child.findtext("voice"), 1)
            offset = _beat_from_onset(
                onset, self.divisions, self.beat_type
            ) - 1.0
            self.beam_starts.setdefault((self.bar, voice), []).append(offset)
        if child.find("chord") is not None:
            # A member of a `<chord>` group: the same onset, the same length.
            # MusicXML does **not** order a group by pitch - only the first
            # note of the group is unmarked, and the rest may be written in
            # any order - so the melody is the group's *highest* note, found
            # by taking the maximum rather than by trusting the position. A
            # chord-melody part's top line is the tune and the rest is the
            # arrangement under it, so the reduction is the point, not a loss.
            self.skip("lower voices of a chord group")
            self.group.append((pitch, length))
            return
        # An unmarked note ends whatever group was open: its own group starts
        # here, and the previous one is complete. The flush is therefore
        # *before* this note joins - emitting after would take the group's first
        # member as the melody, which is its lowest in a descending shape.
        #
        # The harmony is captured with the group rather than read at flush time,
        # because a `<harmony>` between the group's last member and the next
        # unmarked note would otherwise be applied one note early. The chord a
        # note sounds is the one in force where the note is, not the one in
        # force where the reader happened to finish reading it.
        if self.group:
            self.flush()
            self.group.clear()
        self.group.append((pitch, length))
        self.group_onset = onset
        self.group_tie = _stops_a_tie(child)
        self.group_tuplet = _is_tuplet(child)
        self.group_chord, self.group_quality, self.group_bass = (
            self.chord, self.quality, self.bass,
        )
        self.group_lyrics = tuple(
            (lyric.findtext("text") or "").strip()
            for lyric in child.findall("lyric")
        )
        self.cursor += length


    def flush(self) -> None:
        """Emit one melody note from a finished `<chord>` group.

        The group holds `(pitch, length)` for every note sharing an onset. The melody
        is the **highest** of them, because MusicXML does not order a group by pitch -
        only its first member is unmarked, and in a chord-melody part that first member
        is the *lowest* note of the shape, being the first string struck. Taking the
        maximum is what makes the reduction independent of how the writer ordered them.

        A note whose group carries a tie-stop extends the previous note instead of
        becoming a second one. That is the whole reason this is a flush and not an
        append per `<note>`: a tie crosses a bar line, so the two halves are read in
        different measures and cannot be joined at read time.

        **The merge must NOT be restricted to this bar.** Adding `and notes[-1].bar == bar`
        looks like a fix - `notes[-1]` is the last note *read*, not the last note in this
        measure - but it does the opposite, because a `tie type="stop"` in a new bar is
        precisely the continuation the merge exists to absorb: restricting the merge turns
        every cross-barline tie into a *second* note at the same pitch. The premise that
        prompted it, that merging across a barline ate a new bar's downbeat, confused
        *merged* with *lost*: bar 2's A4 eighth and bar 3's A4 half are one note of 3.5 beats,
        so bar 3 has no downbeat note because its downbeat is still sounding the one written
        in bar 2. `tests/test_headxml.py` states this rule directly, and
        `docs/history/open-issues.md` item 1 holds the measurement.
        """
        if not self.group:
            return
        pitch, length = max(self.group, key=lambda item: item[0])
        if self.group_tie and self.notes and self.notes[-1].pitch == pitch:
            self.notes[-1].duration += length / self.divisions / 4.0
            return
        self.notes.append(
            HeadNote(
                bar=self.bar,
                # The written measure number, captured at read time. It equals `bar` for
                # a head with no repeat; `_expand_play_order` rewrites `bar` to the
                # absolute play-order position afterwards and this keeps the score's own
                # numbering.
                written_bar=self.bar,
                # Beat *within* the bar, in notated beats, through the one conversion that
                # is right for every metre: `onset/divisions` is quarters and a beat is
                # `4 / beat_type` of them. That single factor is what makes a 2/2 bar two
                # beats wide - its quarter note is on beat 1.5, not beat 3 - *and* what
                # puts a 3/4 bar's six eighths on 1.0 … 3.5 instead of squeezing them
                # into 2.25 beats. See `_beat_from_onset`.
                beat=_beat_from_onset(
                    self.group_onset, self.divisions, self.beat_type
                ),
                pitch=pitch,
                duration=length / self.divisions / 4.0,
                tuplet=self.group_tuplet,
                chord=self.group_chord,
                quality=self.group_quality,
                bass=self.group_bass,
                lyrics=self.group_lyrics,
            )
        )


def load_musicxml(path: Union[str, Path], part: Optional[str] = None) -> Head:
    """Reads a melody-and-chords MusicXML file into a `Head`.

    Handles both forms of the format: a bare `.musicxml` document and a zipped
    `.mxl` container, read through its `META-INF/container.xml`.

    `part` selects a part by its `<score-part>` id; by default the part with the most
    pitched notes is taken, which is the melody. A part carrying only `<harmony>`
    symbols and no notes is read too - a chords-only lead sheet has an empty melody
    but a full chord timeline - so such a file loads rather than being refused.

    The melody of a chord-melody part is its **top line**, so the highest note of a
    `<chord>` group is the note and the rest are counted in `skipped`: a
    piano-style part is a legitimate input, and reading all of its voices would
    harmonise the accompaniment as though it were the tune. Rests, unpitched
    notes, grace notes and cue notes are skipped for the same reason, and each is
    reported rather than dropped in silence.

    Ties are merged: a note tied across a bar line is one note of the summed
    length, not two, so a held note does not become two slots to arrange - which is
    the whole point of the `repeated` hold in the renderers.

    Harmony is held from the `<harmony>` that declares it until the next one, since
    a bar can carry no harmony at all and one bar can carry several.

    The metre and the **key signature** are both read from the last one stated, and
    both are carried on the `Head`: a head that dropped its key would be exported in
    C major, which is a wrong score rather than a missing decoration.

    The part's **`<transpose>`** is applied to every melody pitch, so a head written
    for a transposing instrument - guitar above all, whose part is notated an octave
    above it sounds - is arranged at concert pitch rather than an octave high. It is
    the inverse of the exporter's `_WRITTEN_OCTAVE_SHIFT`.
    """
    document = _read_document(path)
    root = ElementTree.fromstring(document)
    if root.tag not in ("score-partwise", "score-timewise"):
        raise ValueError(f"{path} is not a MusicXML score (root element is <{root.tag}>)")

    parts = root.findall("part")
    if not parts:
        raise ValueError(f"{path} has no parts to read")
    chosen = _choose_part(parts, part)
    if chosen is None:
        raise ValueError(
            f"{path} has no readable melody part" + (f" with id {part!r}" if part else "")
        )

    title, composer, part_name = _score_metadata(root, chosen.get("id"))
    beats, beat_type = _time_signature(chosen)
    fifths, mode = _key_signature(chosen)
    head = Head(
        title=title,
        composer=composer,
        part=part_name,
        beats_per_bar=beats,
        beat_type=beat_type,
        key_fifths=fifths,
        key_mode=mode,
    )
    _read_notes(chosen, head, _transposition(chosen))
    return head


# ---------------------------------------------------------------------------
# Repeats and play order
# ---------------------------------------------------------------------------

# A written score is not just its bars in document order: repeat barlines,
# volta endings, segno/coda signs and D.C./D.S. jumps make the play order
# longer than the file's measure count. These functions read every channel
# that states navigation - `<barline>`, `<sound>`, `<direction>` - and expand
# it into the absolute bar sequence the arrangement walks. See
# docs/renderers.md for the full vocabulary (`|:` / `:|` / `1.` / `2.` /
# `D.C.` / `D.S.` / `Coda` / `Fine`) and what each writer draws for it.


def _parse_barline(barline: ElementTree.Element) -> List[BarInstruction]:
    """One `<barline>` as play-order instructions.

    A `<repeat direction="forward|backward">` is a `repeat_start` / `repeat_end`,
    and a volta bracket's `<ending type="start|stop">` is an `ending_start` /
    `ending_stop`. `numbers` is the ending's volta set ("1", "2", or "1,2" for a
    bracket taken on more than one pass); `times` is the repeat's play count, which
    MusicXML states only on the backward repeat and which defaults to 2. A
    `<bar-style>` (a final `light-heavy`, say) yields nothing here - it is
    decoration the engine has no use for, and reading it would make every score look
    like it had a repeat.

    Navigation signs are **not** read here. MusicXML states them as `<sound>` and
    `<direction>` elements rather than barlines, and `_parse_direction` /
    `_parse_sound` are where that channel is read.
    """
    out: List[BarInstruction] = []
    repeat = barline.find("repeat")
    if repeat is not None:
        direction = (repeat.get("direction") or "").strip()
        times = max(2, _number(repeat.get("times"), 2))
        if direction == "forward":
            out.append(BarInstruction("repeat_start", times=times))
        elif direction == "backward":
            out.append(BarInstruction("repeat_end", times=times))
    for ending in barline.findall("ending"):
        etype = (ending.get("type") or "").strip()
        numbers = tuple(int(n) for n in re.findall(r"\d+", ending.get("number") or ""))
        if not numbers:
            numbers = (1,)
        if etype == "start":
            out.append(BarInstruction("ending_start", numbers=numbers))
        elif etype == "stop":
            out.append(BarInstruction("ending_stop", numbers=numbers))
        # "discontinue" is a bracket that stops without a repeat; it carries no
        # play-order information, so it is ignored rather than guessed at.
    return out


def _sound_name(value: Optional[str]) -> Optional[str]:
    """A `<sound>` attribute naming a destination, or `None` when it is absent.

    MusicXML spells an unnamed sign as `"yes"` and a named one as its name, so
    `segno="yes"` and `segno="segno"` are the same destination. `"no"` (and an
    absent attribute) means the score states nothing.
    """
    text = (value or "").strip()
    if not text or text.lower() == "no":
        return None
    if text.lower() == "yes":
        return ""
    return text


def _sound_yes(value: Optional[str]) -> bool:
    """Whether a `<sound>` attribute is the yes-no `"yes"` MusicXML uses."""
    return (value or "").strip().lower() in ("yes", "true", "1")


def _parse_sound(sound: ElementTree.Element) -> List[BarInstruction]:
    """The play-order instructions one `<sound>` element carries.

    This is MusicXML's **semantic** channel for jumps, and the one the importer
    reads: a `<direction>` may also carry `<words>D.C. al Fine</words>`, but words
    are prose, vary between exporters, and cannot be told from a title. A sign with
    no `<sound>` is still read from its glyph by `_parse_direction`, which is the
    one fallback worth having.

    The primitives are stated independently here; "al Fine" / "al Coda" is the
    expansion's reading of the return path, never the file's spelling.
    """
    out: List[BarInstruction] = []
    if _sound_yes(sound.get("dacapo")):
        out.append(BarInstruction("da_capo"))
    name = _sound_name(sound.get("dalsegno"))
    if name is not None:
        out.append(BarInstruction("da_segno", name=name or "segno"))
    name = _sound_name(sound.get("segno"))
    if name is not None:
        out.append(BarInstruction("segno", name=name or "segno"))
    name = _sound_name(sound.get("coda"))
    if name is not None:
        out.append(BarInstruction("coda", name=name or "coda"))
    name = _sound_name(sound.get("tocoda"))
    if name is not None:
        out.append(BarInstruction("to_coda", name=name or "coda"))
    if _sound_yes(sound.get("fine")):
        out.append(BarInstruction("fine"))
    # A forward repeat stated on `<sound>` rather than on a `<barline>`. Both are
    # legal spellings of one fact, so a score carrying both yields the instruction
    # twice; `_played_markers` deduplicates the sign it draws.
    if _sound_yes(sound.get("forward-repeat")):
        out.append(BarInstruction("repeat_start"))
    return out


def _parse_direction(direction: ElementTree.Element) -> List[BarInstruction]:
    """The instructions one `<direction>` carries: its `<sound>`, or its glyphs.

    The `<sound>` child wins when there is one, because it states the whole
    instruction ("D.C. **al Fine**" is a jump *plus* a destination whose Fine lies
    on the return path). A `<direction-type><segno/>` or `<coda/>` with no `<sound>`
    is read as the destination it draws, unnamed; a `<words>` element is never read,
    for the reason `_parse_sound` gives.
    """
    out: List[BarInstruction] = []
    for sound in direction.findall("sound"):
        out.extend(_parse_sound(sound))
    if out:
        return out
    for direction_type in direction.findall("direction-type"):
        if direction_type.find("segno") is not None:
            out.append(BarInstruction("segno", name="segno"))
        if direction_type.find("coda") is not None:
            out.append(BarInstruction("coda", name="coda"))
    return out


def _read_notes(
    part: ElementTree.Element, head: Head, transposition: int = 0
) -> None:
    """Walks one part, filling `head` with its melody and their chords.

    `transposition` is the part's `<transpose>` in semitones (see `_transposition`),
    added to every written pitch so the melody is read at **sounding** pitch. It is 0
    for a concert-pitch part, which is every committed head.

    The walk itself is `_NotesWalk` - one value carrying the cursor, the chord in
    force, the `<chord>` group being assembled and the things skipped, because every
    stage of the read touches most of them.
    """
    _NotesWalk(part=part, head=head, transposition=transposition).run()
