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
* `load_musicxml` - a file to a `Head`: the melody, its timing, and the chord in
  force under each note.
* `head_skeleton` / `arrange_xml_head` - the reduction and the arrangement.
* `head_cli` - the `arranger head FILE` command.

**The harmony is a timeline, not a per-note attribute.** A `<harmony>` element
precedes the note it governs, several can share a bar, and - routinely - a bar can
carry none at all, so a chord is held from the note it is declared before until
the next one replaces it. Reading the chord off the note that follows it would
guess.

**The voicings are not re-implemented here.** `arrange_xml_head` hands its slots
to `wjazzd.arrange_slots`, the same function the corpus path uses, so a head read
from a score and the same head read from the database are voiced by identical
code. A second implementation of the step loop is how the corpus path came to
disagree with the library once already.

Deliberately stdlib-only, like `wjazzd`: `musthe` remains the sole dependency.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
from xml.etree import ElementTree

from arranger import (
    GRIP_PREFERENCE,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    ArrangementStep,
    ChordParser,
)
from wjazzd import (
    SKELETON_STRATEGIES,
    SLOT_PICKS,
    arrange_slots,
    midi_to_note_name,
    promote_slash_chord,
)

__all__ = [
    "MUSICXML_KIND_QUALITIES",
    "Head",
    "HeadNote",
    "arrange_xml_head",
    "head_cli",
    "head_skeleton",
    "load_musicxml",
    "parse_musicxml_chord",
]


# ---------------------------------------------------------------------------
# Chord symbols
# ---------------------------------------------------------------------------

# The MusicXML `kind-value` enumeration, translated into the library's qualities.
# This is the inverse of `tabxml._READABLE_KINDS`: that table says which values a
# 3.1-era reader will accept, this one says what each one *means* here.
#
# A kind the library cannot voice is absent rather than folded into a near
# neighbour, on the same principle as `wjazzd.WEIMAR_QUALITY_ALIASES`: an
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
    `wjazzd.parse_weimar_chord` documents for the database's slash chords.

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
# Records
# ---------------------------------------------------------------------------


@dataclass
class HeadNote:
    """One melody note read from a score, with the chord in force under it.

    `bar` is the measure number as written and `beat` the beat *within* it, in the
    notated beats - so a 2/2 bar is two beats wide rather than four, and the two
    halves of a cut-time bar are not mistaken for two bars. `duration` is in whole
    notes, the unit every renderer in this library takes.

    `chord` is the symbol in force, `quality` the library spelling of it (None when
    the symbol was untranslatable, which is counted in `Head.unmapped`) and `bass`
    a slash bass kept for the voicing preference, exactly as in the corpus path.
    """

    bar: int
    beat: float
    pitch: int
    duration: float
    chord: str = ""
    quality: Optional[str] = None
    bass: Optional[str] = None
    lyrics: Tuple[str, ...] = ()

    @property
    def is_no_chord(self) -> bool:
        return self.chord == NO_CHORD

    @property
    def note_name(self) -> str:
        """The pitch as a note name, spelled with flats as the library prints."""
        return midi_to_note_name(self.pitch)


@dataclass
class Head:
    """A loaded head: the melody, its timing, and everything the loader learned.

    `title`, `composer` and `part` identify the source for the CLI header, and
    `beats_per_bar` is the notated bar length in beats, so a cut-time head is
    rendered two beats to the bar rather than four.

    The diagnostics are the reason a chord can go missing without the user
    wondering why: `unmapped` lists the chord symbols this library cannot voice,
    `skipped` the notes that were not melodic, and `report` the prose for the
    terminal. `report` is a separate field from `notes` because `notes` is the
    melody itself.
    """

    notes: List[HeadNote] = field(default_factory=list)
    title: str = ""
    composer: str = ""
    part: str = ""
    beats_per_bar: int = 4
    # The notated value of one beat, as the denominator of the time signature: 4 for
    # 4/4, 2 for the cut time most standards are written in. Carried because
    # `beats_per_bar` alone cannot say which - a 2/2 and a 2/4 bar are both two
    # beats wide, and printing one as the other misstates the metre.
    beat_type: int = 4
    unmapped: Tuple[str, ...] = ()
    skipped: Tuple[str, ...] = ()
    report: Tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.notes)

    def __iter__(self):
        return iter(self.notes)

    @property
    def bars(self) -> Tuple[int, int]:
        """The (first, last + 1) measure range the head occupies."""
        if not self.notes:
            return (1, 1)
        return min(n.bar for n in self.notes), max(n.bar for n in self.notes) + 1


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
    """How many pitched notes a part has, used to choose between valid parts.

    The notes are reached through their measures, which is where MusicXML puts
    them: a `<note>` is a child of a `<measure>`, never of the `<part>` itself.
    """
    return sum(
        1
        for measure in part.findall("measure")
        for note in measure.findall("note")
        if note.find("pitch") is not None
    )


def _choose_part(
    parts: Sequence[ElementTree.Element], part_id: Optional[str]
) -> Optional[ElementTree.Element]:
    """The part to read the melody from.

    An explicit id wins. Otherwise TAB staves are excluded - this library's own
    export has one, and its notes are the same music written per string - and the
    part with the most pitched notes wins, which is the melody rather than a
    doubling staff.
    """
    if part_id is not None:
        for candidate in parts:
            if candidate.get("id") == part_id:
                return candidate
        return None
    readable = [p for p in parts if not _part_is_tab(p) and _part_note_count(p) > 0]
    if not readable:
        readable = [p for p in parts if _part_note_count(p) > 0]
    if not readable:
        return None
    return max(readable, key=_part_note_count)


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


def _midi(pitch: ElementTree.Element) -> Optional[int]:
    """A `<pitch>` as a MIDI number, or None if its spelling is unusable."""
    step = (pitch.findtext("step") or "").strip()
    if step not in _STEP_SEMITONES:
        return None
    octave = _number(pitch.findtext("octave"), -1)
    return (octave + 1) * 12 + _STEP_SEMITONES[step] + _number(pitch.findtext("alter"))


def _duration_in_divisions(note: ElementTree.Element) -> int:
    """A note's length in divisions, divided down for a tuplet.

    MusicXML writes a tuplet's note with an *unreduced* `<duration>` plus a
    `<time-modification>` saying how many of them fill the space of how many normal
    ones - a triplet quarter is written as two thirds of a quarter, which is 6720
    in the divisions of 10080 that "I Was Doing All Right" uses. Without this
    division a triplet lasts a third too long and every bar after the first drifts
    out of time.
    """
    duration = _number(note.findtext("duration"))
    modification = note.find("time-modification")
    if modification is None:
        return duration
    actual = _number(modification.findtext("actual-notes"), 1)
    normal = _number(modification.findtext("normal-notes"), 1)
    if actual > 0 and normal > 0 and actual != normal:
        duration = duration * normal // actual
    return duration


def _stops_a_tie(note: ElementTree.Element) -> bool:
    """True when the note is tied from a previous one, so it extends that note."""
    return any(tie.get("type") == "stop" for tie in note.findall("tie"))


def _flush_group(
    group: List[Tuple[int, int]],
    notes: List[HeadNote],
    bar: int,
    onset: int,
    divisions: int,
    beats_per_bar: float,
    chord: str,
    quality: Optional[str],
    bass: Optional[str],
    tie_stop: bool = False,
    lyrics: Tuple[str, ...] = (),
) -> None:
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
    """
    if not group:
        return
    pitch, length = max(group, key=lambda item: item[0])
    if tie_stop and notes and notes[-1].pitch == pitch:
        notes[-1].duration += length / divisions / 4.0
        return
    notes.append(
        HeadNote(
            bar=bar,
            # Beat *within* the bar, in notated beats. A bar of `beats_per_bar`
            # beats is `beats_per_bar` quarters long, so a note `onset` divisions in
            # is on beat 1 + onset/divisions * beats_per_bar / 4. The division by
            # four is what makes a 2/2 bar two beats wide: a quarter note in it is
            # on beat 1.5, not beat 3.
            beat=1.0 + (onset / divisions) * (beats_per_bar / 4.0),
            pitch=pitch,
            duration=length / divisions / 4.0,
            chord=chord,
            quality=quality,
            bass=bass,
            lyrics=lyrics,
        )
    )


def load_musicxml(path: Union[str, Path], part: Optional[str] = None) -> Head:
    """Reads a melody-and-chords MusicXML file into a `Head`.

    Handles both forms of the format: a bare `.musicxml` document and a zipped
    `.mxl` container, read through its `META-INF/container.xml`.

    `part` selects a part by its `<score-part>` id; by default the melody is taken
    from the first part that is not a TAB staff and has the most pitched notes.

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
    head = Head(
        title=title,
        composer=composer,
        part=part_name,
        beats_per_bar=beats,
        beat_type=beat_type,
    )
    _read_notes(chosen, head)
    return head


def _read_notes(part: ElementTree.Element, head: Head) -> None:
    """Walks one part, filling `head` with its melody and their chords.

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
    beats_per_bar = float(head.beats_per_bar)
    # The chord in force: a `<harmony>` holds until the next one replaces it.
    chord = NO_CHORD
    quality: Optional[str] = NO_CHORD
    bass: Optional[str] = None
    unmapped: List[str] = []
    skipped: Dict[str, int] = {}
    notes: List[HeadNote] = []
    # The `<chord>` group being assembled at the current cursor: (pitch, length),
    # together with the onset it started at, whether it ends a tie, and the lyrics
    # on its first member. Flushed when the next unmarked note - or the bar line -
    # proves the group is complete.
    group: List[Tuple[int, int]] = []
    group_onset = 0
    group_tie = False
    group_chord = NO_CHORD
    group_quality: Optional[str] = NO_CHORD
    group_bass: Optional[str] = None
    group_lyrics: Tuple[str, ...] = ()
    divisions = 1
    bar_index = 1

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for measure in part.findall("measure"):
        for attributes in measure.findall("attributes"):
            stated = attributes.findtext("divisions")
            if stated:
                divisions = max(1, _number(stated, divisions))

        number = (measure.get("number") or "").strip()
        if re.match(r"^-?\d+$", number):
            bar = bar_index = int(number)
        else:
            bar = bar_index
            if number:
                skip(f'measures not numbered with an integer ("{number}")')

        cursor = 0
        group.clear()
        for child in measure:
            if child.tag == "backup":
                cursor = max(0, cursor - _number(child.findtext("duration")))
                continue
            if child.tag == "forward":
                cursor += _number(child.findtext("duration"))
                continue
            if child.tag == "harmony":
                root_name, parsed_quality, parsed_bass = parse_musicxml_chord(child)
                if root_name is None or parsed_quality is None:
                    # Counted, never guessed: a wrong chord under a good melody is
                    # worse than a gap the user can see reported.
                    unmapped.append(_chord_symbol(child))
                    continue
                chord, quality, bass = f"{root_name}{parsed_quality}", parsed_quality, parsed_bass
                continue
            if child.tag != "note":
                continue
            if child.find("grace") is not None:
                skip("grace notes")
                # A grace note has no `<duration>` of its own - it borrows the
                # length of the note it decorates - so it occupies no cursor time
                # and must *not* be added here or it would be counted twice.
                continue
            if child.find("cue") is not None:
                skip("cue notes")
                if child.find("chord") is None:
                    cursor += _duration_in_divisions(child)
                continue
            # A rest is not a melody note, but it is still *time*: the cursor has to
            # move past it or every note after it is read too early. Bar 1 of "But
            # Not For Me" is a quarter rest followed by three quarter notes, and
            # dropping the rest's length put the F4 on beat 1.0 instead of 1.5 -
            # which moved the whole head up a beat, invented a pickup that was not
            # there, and wrote bar 1 as three chords filling a bar it should have
            # shared with a rest. Every skip below is therefore `continue`-with-no-
            # cursor-move only where the element really occupies no time; a rest,
            # a grace note and a cue note all do.
            pitch_element = child.find("pitch")
            if pitch_element is None:
                skip("rests and unpitched notes")
                # Not a `<chord>` member, so it advances the cursor in its own right.
                if child.find("chord") is None:
                    cursor += _duration_in_divisions(child)
                continue
            pitch = _midi(pitch_element)
            if pitch is None:
                skip("notes with an unreadable pitch")
                continue

            length = _duration_in_divisions(child)
            onset = cursor
            if child.find("chord") is not None:
                # A member of a `<chord>` group: the same onset, the same length.
                # MusicXML does **not** order a group by pitch - only the first
                # note of the group is unmarked, and the rest may be written in
                # any order - so the melody is the group's *highest* note, found
                # by taking the maximum rather than by trusting the position. A
                # chord-melody part's top line is the tune and the rest is the
                # arrangement under it, so the reduction is the point, not a loss.
                skip("lower voices of a chord group")
                group.append((pitch, length))
                continue
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
            if group:
                _flush_group(group, notes, bar, group_onset, divisions, beats_per_bar,
                             group_chord, group_quality, group_bass,
                             tie_stop=group_tie, lyrics=group_lyrics)
                group.clear()
            group.append((pitch, length))
            group_onset = onset
            group_tie = _stops_a_tie(child)
            group_chord, group_quality, group_bass = chord, quality, bass
            group_lyrics = tuple(
                (lyric.findtext("text") or "").strip()
                for lyric in child.findall("lyric")
            )
            cursor += length
        # A group still open at the end of a bar is closed by the bar line. The
        # MusicXML it came from is malformed, but reading the notes is better than
        # losing the last chord of the bar.
        _flush_group(group, notes, bar, group_onset, divisions, beats_per_bar,
                     group_chord, group_quality, group_bass,
                     tie_stop=group_tie, lyrics=group_lyrics)
        group.clear()
        bar_index = bar + 1

    head.notes = notes
    head.unmapped = tuple(dict.fromkeys(unmapped))
    head.skipped = tuple(f"{count} {reason}" for reason, count in sorted(skipped.items()))
    report: List[str] = []
    if unmapped:
        report.append(
            f"{len(unmapped)} chord(s) this library cannot voice were left out: "
            + ", ".join(sorted(set(unmapped)))
        )
    report.extend(head.skipped)
    head.report = tuple(report)


# ---------------------------------------------------------------------------
# Reduction and arrangement
# ---------------------------------------------------------------------------

# The slot width each reduction strategy names, in beats. None means "keep every
# note on its own onset", which is what "notes" means. The strategy *names* are
# imported from `wjazzd` rather than restated, so the two input paths cannot drift
# apart: a strategy that means one thing in the corpus means the same thing here.
_STRATEGY_GRID: Dict[str, Optional[float]] = {
    "beats": 1.0,
    "eighths": 0.5,
    "sixteenths": 0.25,
    "notes": None,
}

# The distance a slot's beat is kept inside its bar when there is no grid to step
# back by. See `_slot_key`, which is the only user.
_BEAT_EPSILON = 1e-6


def head_skeleton(
    head: Head,
    strategy: str = "eighths",
    section: Optional[Tuple[int, int]] = None,
    pick: str = "first",
) -> List[Tuple[Tuple[str, str, str], int, float, float]]:
    """Reduces a loaded head to slots: (triple, bar, beat, duration).

    One voicing is generated per slot, and `strategy` decides what a slot is - a
    chord change, a beat, an eighth, a sixteenth, or a single note - which is the
    whole reduction mechanism, and the same set the corpus path offers
    (`wjazzd.SKELETON_STRATEGIES`). `section` is a half-open (start, end) bar
    range, defaulting to the whole head; `pick` chooses which note represents a
    slot several notes share.

    A note under no harmony becomes a melody-only `NO_CHORD` step, which
    `arrange_progression` short-circuits rather than inventing a chord for. A note
    whose chord symbol the loader could not translate is **skipped** rather than
    guessed: a wrong chord under a good melody is worse than a gap.
    """
    if strategy not in SKELETON_STRATEGIES:
        raise ValueError(
            f"Unknown skeleton strategy {strategy!r}; expected one of {SKELETON_STRATEGIES}"
        )
    if pick not in SLOT_PICKS:
        raise ValueError(f"Unknown slot pick {pick!r}; expected one of {SLOT_PICKS}")

    lo, hi = section if section is not None else head.bars
    notes = [n for n in head.notes if lo <= n.bar < hi]
    if not notes:
        return []

    if strategy == "chords":
        groups = _chord_change_groups(notes)
    else:
        grid = _STRATEGY_GRID[strategy]
        groups = {}
        for note in notes:
            groups.setdefault(_slot_key(note, head, grid), []).append(note)

    slots: List[Tuple[Tuple[str, str, str], int, float, float]] = []
    for key in sorted(groups):
        candidates = groups[key]
        chosen = (
            max(candidates, key=lambda n: n.duration) if pick == "longest" else candidates[0]
        )
        # The slot's beat is the *key's* - the quantised grid position - not the
        # note's own onset. They differ for a triplet, and it is the grid that the
        # voicings are spaced on: a chord written a sixteenth off the beat would
        # otherwise sit between two columns of the staff and off the beat of the
        # barline it belongs to.
        bar, beat = key
        if chosen.quality is None:
            if chosen.chord == NO_CHORD:
                slots.append(
                    ((chosen.note_name, NO_CHORD, NO_CHORD), bar, beat, chosen.duration)
                )
            # Otherwise the chord was untranslatable and the slot is dropped; the
            # loader counted it in `Head.unmapped`, so the gap is reported rather
            # than silent.
            continue
        # Rule B, the same promotion the corpus path applies: a triad whose bass
        # is its own seventh implies the seventh chord. It takes the *root*, not
        # the full chord name, which is why the root is split off here rather
        # than rebuilt from `chosen.chord` at the call site.
        root_name, _ = ChordParser.parse_chord_name(chosen.chord)
        promoted = promote_slash_chord(root_name or "", chosen.quality, chosen.bass)
        name = f"{chosen.chord}/{chosen.bass}" if chosen.bass else chosen.chord
        slots.append(((chosen.note_name, promoted, name), bar, beat, chosen.duration))
    return slots


def _slot_key(note: HeadNote, head: Head, grid: Optional[float]) -> Tuple[int, float]:
    """The (bar, beat) a note occupies under a strategy.

    `grid` is the strategy's beat width; None keeps every note on its own onset,
    which is what "notes" means. A slot's beat is *quantised* to the grid rather
    than being the note's own beat, because the grid is what the voicings are
    spaced on: a note a hair off the beat must land on the beat, which is the same
    quantisation the corpus path does by deriving its key from `tatum`.

    A beat that lands **on or past the bar line** is pulled back inside the bar, so
    a bar cannot gain a phantom step on its own downbeat and collide with the first
    step of the next. The limit is therefore the *last grid position still inside
    the bar*, which is one grid step short of `beats_per_bar + 1` - **not**
    `beats_per_bar` itself.

    That distinction is the whole point, and it is what cut time exposes. A 2/2 bar
    is two beats wide, so its eighths run 1.0, 1.5, 2.0, **2.5**: the last eighth of
    the bar is beat 2.5, half a beat past `beats_per_bar`. Clamping to
    `beats_per_bar` folded every one of those notes onto beat 2.0, where they
    collided with the note already there and were dropped by the slot's `pick` rule
    - 13 of the 80 notes in "But Not For Me", a music21-written 2/2 head whose
    fourth quarter of every bar sits at beat 2.5. Losing a note of the tune to a
    clamp is far worse than voicing one a hair off the beat.
    """
    if grid is None:
        # No quantisation, so there is no grid to step back by and the limit is the
        # bar line itself, approached from inside.
        limit = float(head.beats_per_bar) + 1.0 - _BEAT_EPSILON
        return (note.bar, round(min(note.beat, limit), 6))
    beat = 1.0 + round((note.beat - 1.0) / grid) * grid
    limit = float(head.beats_per_bar) + 1.0 - grid
    return (note.bar, round(min(beat, limit), 6))


def _chord_change_groups(notes: Sequence[HeadNote]) -> Dict[Tuple[int, float], List[HeadNote]]:
    """The slots the `chords` strategy reduces to: one per written chord change.

    The written harmony rather than the melody, which is how a slow tune reads: a
    head that moves roughly once a bar should be voiced once a bar, not on every
    eighth of it. A slot's beat is the first note the change lands on, so the
    change is voiced where the file puts it rather than always on the downbeat.
    """
    groups: Dict[Tuple[int, float], List[HeadNote]] = {}
    previous: Optional[str] = None
    for note in notes:
        if note.chord == NO_CHORD:
            continue
        if note.chord != previous:
            groups.setdefault((note.bar, round(note.beat, 6)), []).append(note)
            previous = note.chord
    return groups


def arrange_xml_head(
    path: Union[str, Path],
    part: Optional[str] = None,
    strategy: str = "eighths",
    pick: str = "first",
    non_chord_tone: str = "extension",
    fallback: Optional[str] = None,
    section: Optional[Tuple[int, int]] = None,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
    texture: str = "uniform",
) -> Tuple[List[ArrangementStep], Head, List[str]]:
    """Loads a MusicXML head, reduces it and arranges it, end to end.

    Returns the steps, the `Head` they came from - so the caller can report the
    title, the metre and the loader's diagnostics - and any notes worth printing.

    The voicings come from `wjazzd.arrange_slots`, which is the corpus path's own
    step loop, so the non-chord-tone strategies, the opt-in diminished retry, the
    repeated-melody hold and the slash-bass preference are identical whichever
    source a head was read from. Only the *selection* is this module's business.

    `fallback` may be "diminished"; it replaces the written chord, so it is off
    unless asked for.

    `texture` is the arranging guide's target-note rule, forwarded the same way. It
    is passed `head.beats_per_bar` because **this** module is where the metre trap
    bites hardest: three of the four committed scores are in cut time, whose beat is
    a half note, so a rule that assumed four beats to the bar would put a full chord
    on a beat that does not exist in a 2/2 head. A count without a denominator is
    not a metre.
    """
    head = load_musicxml(path, part)
    slots = head_skeleton(head, strategy, section, pick)
    triples = [slot[0] for slot in slots]
    timings = [(slot[1], slot[2], slot[3]) for slot in slots]
    steps, _rescued, notes = arrange_slots(
        triples, timings, non_chord_tone=non_chord_tone, fallback=fallback,
        grips=grips, texture=texture, beats_per_bar=head.beats_per_bar,
    )
    return steps, head, list(head.report) + notes


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def head_cli(argv: Optional[Sequence[str]] = None) -> int:
    """The `head` command: arrange a MusicXML file as chord-melody.

    Returns a process exit code. It is a thin front end over `arrange_xml_head`
    and the same renderers `corpus_cli` uses, so a head from a score and a head
    from the database render identically.

    `argparse` is imported inside the function for the reason `wjazzd.corpus_cli`
    imports it there: the module stays importable - and cheap - for a caller who
    only wants `load_musicxml`.
    """
    import argparse

    from arranger.cli import HEAD_HELP, add_common_arguments, render_and_write
    from wjazzd import SKELETON_STRATEGIES, SLOT_PICKS, parse_bar_range

    parser = argparse.ArgumentParser(
        prog="arranger head",
        description="Render the melody and chord symbols of a MusicXML file as chord-melody.",
    )
    parser.add_argument("file", help="a .musicxml document or a zipped .mxl container")
    parser.add_argument(
        "--part", default=None, help="score-part id to read (default: the melody part)"
    )
    # The seventeen flags both commands take, with `head`'s own help wording.
    add_common_arguments(
        parser,
        HEAD_HELP,
        skeleton_strategies=SKELETON_STRATEGIES,
        slot_picks=SLOT_PICKS,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.fret_min > args.fret_max:
        parser.error("--fret-min must not be above --fret-max")
    if not Path(args.file).is_file():
        parser.error(f"no such file: {args.file}")

    section: Optional[Tuple[int, int]] = None
    if args.bars:
        try:
            lo, hi = parse_bar_range(args.bars)
        except ValueError as error:
            # A bad range is a usage error, so report it as one rather than
            # letting a ValueError traceback reach the user.
            parser.error(str(error))
        # `parse_bar_range` allows an open-ended "12", which the corpus path
        # resolves against the section's own end. A file has no section, so an
        # open range runs to the end of the head - which is what "the rest of it"
        # means, and is why this is not silently ignored.
        if hi is None:
            head = load_musicxml(args.file, args.part)
            hi = head.bars[1]
        section = (lo, hi)

    try:
        steps, head, notes = arrange_xml_head(
            args.file,
            part=args.part,
            strategy=args.skeleton,
            pick=args.pick,
            non_chord_tone=args.non_chord_tone,
            fallback=args.fallback,
            section=section,
            grips=tuple(args.grips),
            texture=args.texture,
        )
    except (ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))

    title = head.title or Path(args.file).name
    print(f"{title}{f' - {head.composer}' if head.composer else ''}")
    if head.part:
        print(f"  part: {head.part}")
    print(
        f"  {head.beats_per_bar}/{head.beat_type}, {len(head)} melody note(s), "
        f"bars {head.bars[0]}-{head.bars[1] - 1}; neck window: frets "
        f"{args.fret_min}-{args.fret_max}; grips: {', '.join(args.grips)}"
    )
    for note in notes:
        print(f"  note: {note}")
    if args.texture == "targets":
        # Named in the output because the metre is what the rule reads, and the
        # metre is not 4/4 in three of the four committed scores.
        print(
            f"  texture: targets - a full chord on beats 1 and 3 of {head.beats_per_bar}/"
            f"{head.beat_type}, a shell, a 3rd/6th or the melody alone elsewhere"
        )
    if not steps:
        print("  nothing could be voiced from this file")
        return 1
    print()
    # The notated metre goes to every renderer, as it does to the terminal output
    # above. Omitting it left each writer on its own `beats_per_bar=4` default, so
    # a head in cut time was written as 4/4: every bar's contents laid out against
    # the wrong grid, and a tune notated 2/2 displayed as common time. `beat_type`
    # is what makes it 2/2 rather than 2/4 - the bar length is the same either
    # way, so this is the difference between the right metre and a wrong-looking
    # one. The corpus command passes nothing here, because a Weimar transcription
    # is 4/4 and every writer already assumes that.
    return render_and_write(
        args,
        steps,
        title=title,
        notes=notes,
        beats_per_bar=head.beats_per_bar,
        beat_type=head.beat_type,
    )
