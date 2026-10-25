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
"""

from __future__ import annotations

import math
import re
import zipfile
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from xml.etree import ElementTree

from arranger import (
    ArrangementStep,
    ChordParser,
    Rhythm,
    beat_offset,
    default_grouping,
    format_grouping,
    grid_resolutions,
    group_starts,
    grouping_allowed,
    parse_grouping,
    parts_has_melody_only,
    parts_have_chord,
    parts_have_melody,
    resolve_grouping,
    rhythm_beats,
)
from arranger.chords import midi_to_note_name
from arranger.grid import RHYTHM_EVERY_BEAT, RHYTHM_MELODY, TICKS_PER_BEAT
from arranger.grouping import COMMON_TIME, GROUPING_AUTO, TimeSignature
from arranger.options import (
    CHORD_FILLS_COMP,
    CHORD_FILLS_NONE,
    DEFAULT_REQUEST,
    ArrangeOptions,
    Request,
    ResolvedRequest,
    format_request,
    resolve_request,
)
from arranger.resolution import settle_input_fact
from arranger.slots import arrange_slots
from arranger.tuning import NO_CHORD, PITCH_CLASS_NAMES

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
    "head_cli",
    "head_skeleton",
    "load_musicxml",
    "melody_at",
    "melody_rests",
    "melody_state",
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
# Records
# ---------------------------------------------------------------------------


@dataclass
class HeadNote:
    """One melody note read from a score, with the chord in force under it.

    `bar` is the measure number as written and `beat` the beat *within* it, in the
    notated beats - so a 2/2 bar is two beats wide rather than four, its quarter note
    on beat 1.5 and its fourth on 2.5, and the two halves of a cut-time bar are not
    mistaken for two bars. A beat is `4 / beat_type` quarters, which is the one factor
    `_beat_from_onset` converts an onset with. `duration` is in whole notes, the unit
    every renderer in this library takes.

    `chord` is the symbol in force, `quality` the library spelling of it (None when
    the symbol was untranslatable, which is counted in `Head.unmapped`) and `bass`
    a slash bass kept for the voicing preference.
    """

    bar: int
    beat: float
    pitch: int
    duration: float
    # The measure number **as written on the score**. It equals `bar` for a head with
    # no repeat; when a repeat renumbers `bar` to a unique play-order position (a
    # repeated bar is played twice, so two physical bars would otherwise share the
    # written number), this keeps the score's own numbering recoverable. The default
    # `-1` is a hand-built note, which has no score behind it. See `BarMarker` and
    # `expand_repeats`.
    written_bar: int = -1
    # True when the note came from a `<time-modification>`, i.e. it is part of a
    # tuplet. Carried **explicitly** rather than inferred from `duration`, because
    # the inference is wrong: a plain eighth is half a grid step under `eighths`, so
    # "is the duration a whole number of steps" is true for tuplets *and* for every
    # ordinary eighth, and the check silently re-spaced the whole head. Only the
    # file knows which notes were written as a tuplet.
    tuplet: bool = False
    chord: str = ""
    quality: Optional[str] = None
    bass: Optional[str] = None
    lyrics: Tuple[str, ...] = ()

    @property
    def is_no_chord(self) -> bool:
        return self.chord == NO_CHORD

    @property
    def key(self) -> Tuple[int, float]:
        """The `(bar, beat)` this note begins at.

        **The same rounding as `HeadChange.key`, and it must match.** The two timelines
        are compared against each other — `chord_at` against a note's position, and
        `melody_at` against a grid position — so a beat that differs only in the seventh
        decimal has to be the same position to both. Two floats from two different
        expressions are the same beat; two spellings of one key are not.
        """
        return (self.bar, round(self.beat, 6))

    @property
    def note_name(self) -> str:
        """The pitch as a note name, spelled with flats as the library prints."""
        return midi_to_note_name(self.pitch)


@dataclass
class HeadChange:
    """One `<harmony>` element: a chord **becoming** in force at a position.

    **`HeadNote.chord` and this are the same fact read two ways**, and the difference
    is the whole of open-issues item 1. A note carries the chord that was in force
    *where the note is*; this carries the chord that *begins* at a position, whether or
    not any note is ever written there.

    A `<harmony>` followed by no note is not a synthetic edge case: 6 of the 154
    `<harmony>` elements across the committed scores precede no note, and one of those
    bars carries **no notes at all**. Such a change is in force for the rest of the bar
    and **no note ever records it**, which is the loss `docs/history/open-issues.md` item 1
    measures and this field exists to make representable.

    `beat` is the beat **within the bar**, as everywhere else in this module, and
    `quality is None` is never recorded — an untranslatable chord is counted in
    `Head.unmapped` and not guessed, exactly as on the note path.
    """

    bar: int
    beat: float
    chord: str
    quality: Optional[str] = None
    bass: Optional[str] = None
    # The written measure number, exactly as on `HeadNote.written_bar`: equal to `bar`
    # for a head with no repeat, and the score's own number when a repeat renumbered
    # `bar`. Defaults to -1 for a hand-built change.
    written_bar: int = -1

    @property
    def key(self) -> Tuple[int, float]:
        """The `(bar, beat)` this change takes effect at, for timeline lookups."""
        return (self.bar, round(self.beat, 6))


@dataclass(frozen=True)
class BarInstruction:
    """One bar-level play-order instruction, as the reader saw it.

    This is the **vocabulary** every reader of a written head shares: the MusicXML
    walk (`_parse_barline`, `_parse_direction`) and, through `expand_repeats`, any
    other importer that can state the same facts. It stays primitive on purpose:

    - `repeat_start` / `repeat_end` (with `times`) are a repeat's two ends;
    - `ending_start` / `ending_stop` (with `numbers`) bracket a volta;
    - `segno` / `coda` are **destinations**, named so a `to_coda` can pair with one;
    - `fine` and `to_coda` are the two places a jump may end;
    - `da_capo` / `da_segno` (naming its `segno`) are the jumps themselves.

    "D.C. al Fine" is therefore not an instruction: it is a `da_capo` whose return
    path passes a `fine`, and `_expand_play_order` is the only place that decides
    which of the six resolved forms it is.

    A frozen dataclass rather than a tuple: a raw marker has four fields, and a
    positional unpack is where a fifth would go unnoticed. `name` is empty except on a
    destination and the jump to one.
    """

    kind: str
    numbers: Tuple[int, ...] = ()
    times: int = 2
    name: str = ""


@dataclass
class BarMarker:
    """A repeat, ending or navigation instruction, on the **absolute** play-order bar
    the loader assigned.

    `kind` is `BarInstruction`'s vocabulary, plus the four **resolved** jump forms
    `da_capo_al_fine`, `da_capo_al_coda`, `da_segno_al_fine` and `da_segno_al_coda`.
    The resolution happens once, in `_expand_play_order`: a writer that had to decide
    for itself whether a D.C. ends at a Fine or a Coda would be a second source for a
    decision the play order already made.

    `numbers` is a volta's number set - "1", "2", or "1,2" for a bracket played on
    more than one pass - and `times` is a repeat's play count (2 unless the file says
    otherwise). `name` is the Segno or Coda a destination or jump is spelled with;
    it is empty elsewhere.

    These are what the writers draw as `|:` / `:|`, the `1.` / `2.` brackets and the
    D.C. / D.S. / Fine / Coda directions, and what `_expand_play_order` uses to build
    the sequence a performer actually plays.
    """

    bar: int
    kind: str
    written_bar: int
    numbers: Tuple[int, ...] = ()
    times: int = 2
    name: str = ""


@dataclass
class Head:
    """A loaded head: the melody, its timing, and everything the loader learned.

    `title`, `composer` and `part` identify the source for the CLI header, and
    `beats_per_bar` is the notated bar length in beats, so a cut-time head is
    rendered two beats to the bar rather than four. `first_bar_implicit` is the source's
    own statement that bar 1 is an anacrusis, which the arrangement must not fill.

    `key_fifths` / `key_mode` are the key signature, so a renderer can state the key
    the tune is in instead of falling back to the format's default of C major. See
    their comments for the encoding, and `_key_signature` for how it is read.

    The notes are the reason a chord can go missing without the user
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
    # The score's own statement of the **grouping** - which denominator units are
    # felt as one beat - in those units, and the channel that stated it: "text" (an
    # `N+N` direction), "beams" (the primary beaming), "metronome" (a pulse mark),
    # or "" when the file says nothing. Empty is "not stated", not "one per beat":
    # an unbeamed score and a hand-built `Head` both take `grouping.auto`, and the
    # engine resolves that from `beats_per_bar` and `beat_type`.
    #
    # A tuple rather than the string the engine takes, because this is the file's
    # fact and `ArrangeOptions` is the request. `_head_request` converts it.
    grouping: Tuple[int, ...] = ()
    grouping_source: str = ""
    # True when the score marks its first measure `implicit="yes"` (or numbers it 0):
    # the measure is an anacrusis, so its missing time is a pickup and not comping
    # space. Carried because a generated accompaniment position in that short bar
    # would fill it, and the renderers infer the pickup from the bar's content.
    first_bar_implicit: bool = False
    # The key signature as MusicXML states it: `key_fifths` counts sharps (positive)
    # or flats (negative), so -3 is Eb major or C minor, and `key_mode` is which -
    # "major", "minor", or "" where the score did not say. Kept as the format's own
    # numbers rather than as a tonic name, because that is what a renderer needs to
    # write a signature back, and it is the one spelling every convention agrees on.
    #
    # Carried at all because a head with no key is C major, not *unknown*: a score
    # that omits `<key>` states no accidentals, and that is a key this library can
    # arrange and export.
    key_fifths: int = 0
    key_mode: str = ""
    unmapped: Tuple[str, ...] = ()
    skipped: Tuple[str, ...] = ()
    report: Tuple[str, ...] = ()
    # Every `<harmony>` in the part, in document order, as a **chord timeline**
    # independent of the melody. Empty by default, so a `Head` built by hand or by a
    # test keeps working, and `head_skeleton` reads `notes` only — this is recorded
    # and nothing else yet consumes it.
    #
    # It exists because `notes` cannot say what is in force where no note is written,
    # and open-issues item 1 measures what that costs: on `synthetic_repeat_slash` bars
    # 8, 16, 24 and 32 vanish from the arrangement entirely, and on
    # `synthetic_triplets` bar 34. See `HeadChange`.
    chords: List[HeadChange] = field(default_factory=list)
    # The (first, last) measure numbers the loader walked, or `None` for a `Head`
    # built by hand. `bars` reads it, so the head's length is a fact about the
    # **file** rather than about the melody - §9.3 step A' of `docs/comping-styles.md`.
    #
    # It is carried because a chords-only lead sheet has no notes to measure and still
    # knows how long it is, and because a head whose changes outlast its last note must
    # not be cut short at the tune's end. `None` keeps a hand-built `Head`'s note span
    # working, since it has no file behind it to state a range.
    measure_range: Optional[Tuple[int, int]] = None
    # Every repeat and ending (volta) instruction the score's barlines carried, on the
    # absolute play-order bars. Empty by default, so a hand-built `Head` and a score
    # with no repeat are both unaffected. The writers draw these; `Head.bars` is the
    # expanded length, so a repeated head arranges every bar a player actually plays.
    markers: List[BarMarker] = field(default_factory=list)
    # Absolute play-order bar -> the measure number the score writes for it. Empty for
    # a head with no repeat, where the two are the same number. A renderer that draws the
    # repeat signs needs it to fold the played arrangement back onto the **written**
    # score: writing the played bars out *and* looping them with signs would make a
    # reader play the repeated section twice more. See `arranger.cli._as_written`.
    written_bars: Dict[int, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.notes)

    def __iter__(self):
        return iter(self.notes)

    @property
    def bars(self) -> Tuple[int, int]:
        """The (first, last + 1) measure range the head occupies.

        **A fact about the file, not about the melody** (§9.3 step A'). The loader
        records the measures it walked, so this is right for a head whose last chord
        outlasts its last note and for one with no notes at all - a chords-only lead
        sheet. Nothing to guess: an empty file still has its measure count.

        A `Head` built by hand carries no such range, so it falls back to the melody's
        span, which is what every fixture in the tests is.
        """
        if self.measure_range is not None:
            first, last = self.measure_range
            return (first, last + 1)
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
            # numbered 0 says the same thing in the older spelling.
            self.head.first_bar_implicit = (
                (measure.get("implicit") or "").strip().lower() == "yes"
                or self.bar == 0
            )
        self.measure_numbers.append(self.bar)

        for barline in measure.findall("barline"):
            self.raw_markers.setdefault(self.position, []).extend(
                _parse_barline(barline)
            )

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

def _ending_membership(
    raw_markers: Dict[int, List[BarInstruction]],
    measure_count: int,
) -> Dict[int, set]:
    """Which volta ending each measure position belongs to, by its numbers.

    A bracket runs from its `ending_start` to its `ending_stop` inclusive; an
    unterminated one runs to the last measure, because a writer that leaves a bracket
    open means it to the end rather than to nothing.
    """
    ending_at: Dict[int, set] = {}
    open_ending: Dict[Tuple[int, ...], int] = {}
    for position in sorted(raw_markers):
        for instruction in raw_markers[position]:
            if instruction.kind == "ending_start":
                open_ending[instruction.numbers] = position
            elif instruction.kind == "ending_stop":
                start = open_ending.pop(instruction.numbers, None)
                if start is not None:
                    for covered in range(start, position + 1):
                        ending_at[covered] = set(instruction.numbers)
    for numbers, start in open_ending.items():
        for covered in range(start, measure_count):
            ending_at[covered] = set(numbers)
    return ending_at


def _repeat_start_positions(
    raw_markers: Dict[int, List[BarInstruction]],
) -> List[int]:
    """The positions carrying a forward repeat, in document order - the jump targets."""
    return [
        position
        for position in sorted(raw_markers)
        if any(
            instruction.kind == "repeat_start"
            for instruction in raw_markers[position]
        )
    ]


def _repeat_target(position: int, starts: Sequence[int]) -> int:
    """Where a backward repeat at `position` jumps to: the nearest start before it.

    Zero when the score marks no forward repeat, which is the common case - a lead
    sheet's opening repeat sign is implied by the backward one, and a player reads a
    `|:` at bar 1 whether or not the file writes one.
    """
    earlier = [start for start in starts if start < position]
    return max(earlier) if earlier else 0




def _jump_target(
    instruction: BarInstruction, segno_at: Dict[str, int]
) -> Optional[int]:
    """Where a D.C. or D.S. jumps to: the start, or the segno it names.

    `None` means the score names a Segno it never draws. That is a malformed form
    rather than a jump to an arbitrary bar, so the caller reports it and plays on
    linearly instead of guessing a target.
    """
    if instruction.kind == "da_capo":
        return 0
    return segno_at.get(instruction.name.lower())


def _resolved_jump(
    instruction: BarInstruction,
    target: int,
    position: int,
    fine_at: set,
    to_coda_at: Dict[int, str],
) -> str:
    """Which of the six jump forms a D.C. / D.S. is, from the bar it returns over.

    The words a score prints - "al Fine", "al Coda" - are not separate instructions:
    they say what lies on the **return path**, between the jump's target and the
    instruction itself. When both a Fine and a To Coda are on it, the **earlier** one
    is reached first and names the form; a To Coda only wins when it comes first.
    """
    path = range(target, position + 1)
    fine_stop = min((step for step in path if step in fine_at), default=None)
    coda_stop = min((step for step in path if step in to_coda_at), default=None)
    # A bar carrying both is a Fine in playback: the Fine check runs first in the walk.
    al_coda = coda_stop is not None and (
        fine_stop is None or coda_stop < fine_stop
    )
    al_fine = fine_stop is not None and not al_coda
    if instruction.kind == "da_capo":
        if al_coda:
            return "da_capo_al_coda"
        if al_fine:
            return "da_capo_al_fine"
        return "da_capo"
    if al_coda:
        return "da_segno_al_coda"
    if al_fine:
        return "da_segno_al_fine"
    return "da_segno"


@dataclass
class _PlayOrderIndex:
    """The instructions a play order is built from, sorted by the question they answer.

    A value rather than ten locals: `_expand_play_order` reads most of these on every
    step of the walk, and a signature listing them would be a second copy of the table.
    """

    ending_at: Dict[int, set]
    repeat_end: Dict[int, int]
    repeat_starts: List[int]
    fine_at: set
    segno_at: Dict[str, int]
    coda_at: Dict[str, int]
    to_coda_at: Dict[int, str]
    jump_at: Dict[int, BarInstruction]


def _play_order_index(
    raw_markers: Dict[int, List[BarInstruction]], measure_count: int
) -> _PlayOrderIndex:
    """Sort the raw instructions into the questions the play order asks of them."""
    ending_at = _ending_membership(raw_markers, measure_count)
    repeat_end: Dict[int, int] = {}
    fine_at: set = set()
    segno_at: Dict[str, int] = {}
    coda_at: Dict[str, int] = {}
    to_coda_at: Dict[int, str] = {}
    jump_at: Dict[int, BarInstruction] = {}
    for position in sorted(raw_markers):
        for instruction in raw_markers[position]:
            if instruction.kind == "repeat_end":
                repeat_end[position] = instruction.times
            elif instruction.kind == "fine":
                fine_at.add(position)
            elif instruction.kind == "segno":
                segno_at.setdefault(instruction.name.lower(), position)
            elif instruction.kind == "coda":
                coda_at.setdefault(instruction.name.lower(), position)
            elif instruction.kind == "to_coda":
                to_coda_at.setdefault(position, instruction.name)
            elif instruction.kind in ("da_capo", "da_segno"):
                jump_at.setdefault(position, instruction)
    return _PlayOrderIndex(
        ending_at=ending_at,
        repeat_end=repeat_end,
        repeat_starts=_repeat_start_positions(raw_markers),
        fine_at=fine_at,
        segno_at=segno_at,
        coda_at=coda_at,
        to_coda_at=to_coda_at,
        jump_at=jump_at,
    )


def _fine_stops(index: int, jumped: bool, plan: _PlayOrderIndex) -> bool:
    """Whether the bar at `index` ends the head.

    A Fine with **no** jump in the score is the end of the piece. With one, it only
    stops the return: passing it on the way out is what lets the jump be reached at all.
    """
    return index in plan.fine_at and (jumped or not plan.jump_at)


def _coda_target(
    index: int,
    jumped: bool,
    coda_taken: bool,
    plan: _PlayOrderIndex,
    notes: List[str],
) -> Optional[int]:
    """Where a To Coda at `index` diverts to, or None when it does not fire.

    It fires only after the jump, and only once: on the way out it is a sign the player
    passes, and after the detour the same bar is not reached again. A To Coda naming a
    Coda the score does not draw is reported rather than guessed at.
    """
    if not jumped or coda_taken or index not in plan.to_coda_at:
        return None
    coda = plan.coda_at.get(plan.to_coda_at[index].lower())
    if coda is None:
        notes.append(
            f"the 'To Coda' at measure {index + 1} names a Coda this score does not have"
        )
    return coda


def _jump_at(
    index: int, jumped: bool, plan: _PlayOrderIndex, notes: List[str]
) -> Optional[Tuple[int, str]]:
    """The `(target, resolved kind)` of a D.C. / D.S. at `index`, or None.

    None covers both "there is no jump here" and "the jump names a Segno the score does
    not have" - the second is reported and the head plays on linearly, which is the only
    honest reading of a malformed form.
    """
    if jumped:
        return None
    instruction = plan.jump_at.get(index)
    if instruction is None:
        return None
    target = _jump_target(instruction, plan.segno_at)
    if target is None:
        notes.append(
            f"the D.S. at measure {index + 1} names a Segno this score does not have"
        )
        return None
    return target, _resolved_jump(
        instruction, target, index, plan.fine_at, plan.to_coda_at
    )


def _expand_play_order(
    measure_count: int,
    raw_markers: Dict[int, List[BarInstruction]],
) -> Tuple[List[Tuple[int, int]], Dict[int, str], List[str]]:
    """The measures a performer actually plays, as `(position, pass)` in order.

    Returns the order, the **resolved** kind of each jump that fired, and any report
    lines for a form that could not be honoured. The resolution is returned rather
    than recomputed by the writers: one decision, one source.

    The repeat and volta rules are the ones a lead sheet asks for:

    - a **backward repeat** jumps back to the matching **forward repeat**, or to the
      very start when the score marks no forward repeat. The backward repeat's
      `times` (default 2) is how many times the section is played.
    - a **volta ending** numbered N is played only on pass N, which is exactly the
      "take the 1st ending, repeat, skip it and take the 2nd" a score writes.

    The navigation rules are what makes D.C. / D.S. / Coda / Fine a form rather than
    four decorations, and each is a decision:

    - **A jump fires once.** After it is taken, every later D.C. / D.S. is ignored -
      otherwise the instruction just obeyed would fire again as the return path
      reached it.
    - **A Fine or To Coda is a destination only after the jump.** On the first pass
      they are passed through: a player who stopped at the Fine on the way to the
      D.C. would never reach it. A Fine with **no** jump is the one exception - there
      it is the end of the piece, and ends it.
    - **A To Coda fires once, and only after the jump**, at the bar that carries it;
      the coda section is otherwise unreachable. A To Coda with no jump is inert.
    - **Repeats are not re-taken after a jump.** A D.C. that re-entered a backward
      repeat at bar 1 would reach the same instruction again and jump forever; a
      performer reading "D.C." plays the section straight through.
    - Volta passes reset to 1 on a jump, for the same reason: the return is a fresh
      read of the written page.

    A head with no repeat, ending or jump returns the identity order, so
    `expand_repeats` can leave it byte-identical. The limit guards a malformed score
    against looping forever; it is far above any real expansion, and the report says
    when it was reached rather than truncating in silence.
    """
    notes: List[str] = []
    if not raw_markers:
        return [(position, 1) for position in range(measure_count)], {}, notes

    # The instructions, sorted into the questions this walk asks of them.
    plan = _play_order_index(raw_markers, measure_count)
    has_jump = bool(plan.jump_at)

    order: List[Tuple[int, int]] = []
    jumps: Dict[int, str] = {}
    pass_no = 1
    index = 0
    guard = 0
    limit = 8 * (measure_count + 1) + 64
    jumped = False
    coda_taken = False
    while index < measure_count and guard < limit:
        guard += 1
        # The Fine sounds: it is the end of a phrase, not the bar before one.
        if _fine_stops(index, jumped, plan):
            order.append((index, pass_no))
            break
        numbers = plan.ending_at.get(index)
        # A volta this pass does not take is skipped - but only when a pass is actually
        # in play. On a head with an ending and no repeat the pass never advances past
        # 1, so an ending numbered "2" would otherwise never sound.
        if numbers is not None and pass_no not in numbers:
            index += 1
            continue
        order.append((index, pass_no))
        if (
            not jumped
            and index in plan.repeat_end
            and pass_no < plan.repeat_end[index]
        ):
            pass_no += 1
            index = _repeat_target(index, plan.repeat_starts)
            continue
        coda = _coda_target(index, jumped, coda_taken, plan, notes)
        if coda is not None:
            coda_taken = True
            pass_no = 1
            index = coda
            continue
        jump = _jump_at(index, jumped, plan, notes)
        if jump is not None:
            target, kind = jump
            jumped = True
            jumps[index] = kind
            pass_no = 1
            index = target
            continue
        index += 1

    if guard >= limit and index < measure_count:
        notes.append(
            "the play order was cut short: a repeat or jump never terminated"
        )
    if not has_jump:
        for position in sorted(plan.to_coda_at):
            notes.append(
                f"the 'To Coda' at measure {position + 1} has no D.C. or D.S. "
                "to return from"
            )
    return order, jumps, notes


def expand_repeats(
    head: Head,
    measure_numbers: List[int],
    raw_markers: Dict[int, List[BarInstruction]],
) -> Tuple[str, ...]:
    """Rewrite a head so it plays its repeats, endings and jumps, in place.

    The measures were walked once in document order, each note and `<harmony>` stamped
    with the written measure number. This recomputes the **play order** and renumbers
    `bar` to a unique absolute position, duplicating the notes and chords of a repeated
    section - or a section a D.C. / D.S. returns over - so the arrangement states them
    on every pass a player makes.

    `bar` must be unique because the engine keys everything - `chord_at`, `melody_at`,
    the bass timeline, the renderers' bar grouping - on `(bar, beat)`, and a repeat puts
    two physical bars on the same written number. The written number is kept on
    `HeadNote.written_bar` / `HeadChange.written_bar` so the score's own numbering is
    never lost, and `--bars a-b` filters on the **absolute** (played) bars - so on a
    repeated head `--bars 31-32` is the 1st ending as played, not written bar 31.

    A head with no repeat, ending or jump is left byte-identical, but its markers are
    still recorded: a lone Segno or Coda is a sign the score states and the writers
    draw, even where it moves no bar.

    Returns the report lines for a form that could not be honoured (a D.S. naming no
    Segno, a To Coda naming no Coda, a play order the guard cut short), so the caller
    can put them where the rest of the loader's notes go. Headers that only care about
    the rewrite may ignore the value.
    """
    if not raw_markers or not measure_numbers:
        return ()
    order, jumps, notes = _expand_play_order(len(measure_numbers), raw_markers)
    base = measure_numbers[0]
    # An ending with no repeat, an unreferenced sign: the identity order. Touching the
    # head then would renumber bars for no musical reason, so it is left as read.
    if order == [(position, 1) for position in range(len(measure_numbers))]:
        first_abs = {
            position: base + position for position in range(len(measure_numbers))
        }
        head.markers = _played_markers(raw_markers, measure_numbers, first_abs, jumps)
        return tuple(notes)

    head.notes, head.chords, first_abs = _played_bars(
        head, order, measure_numbers, base
    )

    # A backward repeat jumps back to a target - an explicit forward repeat, or the very
    # start when the score marks none (both committed repeats do). The writers draw a
    # `|:` there, so a target with no `<repeat direction="forward">` of its own still gets
    # a `repeat_start` marker: the opening barline of `synthetic_repeat_slash` carries no
    # repeat sign in the file, yet a player reads one there.
    head.markers = _played_markers(raw_markers, measure_numbers, first_abs, jumps)
    head.measure_range = (base, base + len(order) - 1)
    # The absolute -> written bar map, for the renderers that draw the signs: it is what
    # lets them write the score the file actually contains rather than the played bars.
    head.written_bars = {
        base + index: measure_numbers[position]
        for index, (position, _pass) in enumerate(order)
    }
    return tuple(notes)


def _played_bars(
    head: Head,
    order: List[Tuple[int, int]],
    measure_numbers: List[int],
    base: int,
) -> Tuple[List[HeadNote], List[HeadChange], Dict[int, int]]:
    """Every played pass, renumbered, plus each position's first absolute bar.

    The `position -> absolute bar` map is what the markers are placed by, and it is
    **first** pass deliberately: a repeat sign belongs where the section begins, not
    on every bar it is played in.

    A section played twice contributes its notes twice, which is the point - the
    arrangement states them on every pass a player makes - and is why `bar` has to be
    a unique absolute position rather than the written measure number.
    """
    notes_by_bar: Dict[int, List[HeadNote]] = {}
    for note in head.notes:
        notes_by_bar.setdefault(note.written_bar, []).append(note)
    changes_by_bar: Dict[int, List[HeadChange]] = {}
    for change in head.chords:
        changes_by_bar.setdefault(change.written_bar, []).append(change)

    new_notes: List[HeadNote] = []
    new_changes: List[HeadChange] = []
    first_abs: Dict[int, int] = {}
    for index, (position, _pass) in enumerate(order):
        absolute = base + index
        first_abs.setdefault(position, absolute)
        written = measure_numbers[position]
        for note in notes_by_bar.get(written, ()):
            new_notes.append(replace(note, bar=absolute))
        for change in changes_by_bar.get(written, ()):
            new_changes.append(replace(change, bar=absolute))
    return new_notes, new_changes, first_abs


def _played_markers(
    raw_markers: Dict[int, List[BarInstruction]],
    measure_numbers: List[int],
    first_abs: Dict[int, int],
    jumps: Dict[int, str],
) -> List[BarMarker]:
    """The repeat, ending and navigation signs, on the absolute bars that carry them.

    `jumps` is `_expand_play_order`'s resolved form of each jump that fired, keyed by
    position: `da_capo_al_fine` and the rest. A marker's `kind` is the resolved kind
    where there is one, because the writers need the words a score prints ("D.C. al
    Fine") rather than the primitive the file stated.

    A backward repeat jumps back to a target - an explicit forward repeat, or the very
    start when the score marks none (both committed repeats do). The writers draw a
    `|:` there, so a target with no `<repeat direction="forward">` of its own still gets
    a `repeat_start` marker: the opening barline of `synthetic_repeat_slash` carries no
    repeat sign in the file, yet a player reads one there.

    A marker on a measure the expansion never played (an ending bracket no pass takes)
    has no absolute bar to land on, so it is dropped rather than guessed. A sign stated
    twice on one bar - a forward repeat on both the `<barline>` and the `<sound>` - is
    drawn once.
    """
    repeat_targets: Dict[int, None] = {}
    starts = _repeat_start_positions(raw_markers)
    for position in sorted(raw_markers):
        for instruction in raw_markers[position]:
            if instruction.kind == "repeat_end":
                repeat_targets.setdefault(_repeat_target(position, starts), None)
    marked_starts = set(starts)

    markers: List[BarMarker] = []
    seen: set = set()
    for position in sorted(raw_markers):
        absolute = first_abs.get(position)
        if absolute is None:
            continue
        for instruction in raw_markers[position]:
            kind = jumps.get(position, instruction.kind)
            key = (absolute, kind, instruction.numbers, instruction.name)
            if key in seen:
                continue
            seen.add(key)
            markers.append(
                BarMarker(
                    bar=absolute,
                    kind=kind,
                    written_bar=measure_numbers[position],
                    numbers=instruction.numbers,
                    times=instruction.times,
                    name=instruction.name,
                )
            )
    for position in sorted(repeat_targets):
        if position not in marked_starts and position in first_abs:
            markers.append(
                BarMarker(
                    bar=first_abs[position],
                    kind="repeat_start",
                    written_bar=measure_numbers[position],
                )
            )
            marked_starts.add(position)
    markers.sort(key=lambda m: (m.bar, m.kind))
    return markers


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


# ---------------------------------------------------------------------------
# Reduction and arrangement
# ---------------------------------------------------------------------------

# How far inside its bar a note's beat is kept, so it cannot collide with the next
# bar's downbeat. A 2/2 bar is two beats wide, so its last quarter is beat 2.5.
BEAT_EPSILON = 1e-6


def chord_at(
    changes: Sequence[HeadChange], bar: int, beat: float
) -> Optional[HeadChange]:
    """The change in force at `(bar, beat)`, by forward fill, or `None` if none is.

    **The query open-issues item 1 needs, and the twin of `bass._melody_in_force`.**
    That one answers "which melody slot is sounding here" for a beat the thumb invented;
    this answers "which chord is sounding here" for a beat no note describes. Both are
    forward fills over an ordered timeline, and both are *needed* because the step loop
    iterates melody slots — so a position with no melody slot must be able to ask the
    harmony question anyway.

    Three rules, each a decision rather than an implementation detail:

    - **A chord holds until the next one replaces it** (`<=`, not `<`). A change *on*
      beat 2 is in force *at* beat 2, which is what the note path already does: a note
      carries the chord captured before it, so a change on the same position applies.
    - **The last change at a position wins.** Bars 33 and 35 of `synthetic_triplets`
      each carry two `<harmony>` elements at beat 1.0, and the note in each bar carries the
      second one — so "the last declared" is the rule the note path already follows, and
      taking the first would disagree with it. `docs/history/open-issues.md` item 1 holds the
      measurement.
    - **`None` before the first change**, never a guess. A position no chord has reached
      has no harmony, and inventing one is the failure this module refuses everywhere
      else. The caller decides what to do — drop the bar, or emit a rest for it — because
      only it knows whether the position is real.

    **The answer is the change with the greatest position at or before the target**, which
    makes the scan order-independent: an unsorted list gives the same answer as a sorted
    one, because "greatest key not after the position" does not depend on the order the
    entries arrive in. Last-wins at a duplicated position falls out of the same rule —
    two changes at one position have *equal* keys, so `>=` takes the later of them, which
    is the one the note path captures.

    That last point is why this is not "the last matching entry in the list". Scanning
    and overwriting returns whichever entry happens to come last *in the input*, which on
    an unsorted list can be a stale one: with `[bar 2, bar 3, bar 1]` in that order, every
    bar answers `Gmaj`. The comparison below is what makes that impossible rather than
    merely unlikely.
    """
    position = (bar, round(beat, 6))
    found: Optional[HeadChange] = None
    for change in changes:
        key = change.key
        if key > position:
            continue
        if found is None or key >= found.key:
            found = change
    return found


def melody_at(head: Head, bar: int, beat: float) -> Optional[str]:
    """The written note sounding at `(bar, beat)`, by forward fill, or `None`.

    **The note-path twin of `chord_at`, and the reason `chord_slots` can carry a
    melody.** A chord stab is placed by the comping union, but the part still has to line up
    against the tune it is comping under, so the step needs *a* note — and the honest one
    is the note actually sounding at that instant.

    **"Last onset at or before" rather than "the previous note".** A note whose length
    runs past the position keeps winning, so a phrase holding one note across a barline
    hands that note to a stab on the far side rather than the one that follows it — the
    same in-force rule `bass._melody_in_force` reads by onset *and* duration, and the
    distinction between an onset and a hold.

    **A note that has stopped is not in force.** `duration` is in whole notes, so the end
    is the onset plus that length in **beats**; this is why the function returns `None`
    for a position after the melody ends rather than carrying the last note forever.

    **A note sounds over `[onset, end)`, so its release instant is already silence.** A
    position exactly on the end returns `None`: the tune has stopped there, and a comp
    placed on it carries no melody rather than borrowing the pitch that just stopped.
    That is the boundary `melody_rests` already reads, since the rest after a note begins
    where that note ended. The one position that is never a release is an **onset** — a
    note's own `HeadNote.key` — because a zero-length note would otherwise be ended by its
    own release instant.

    **The end is computed on one absolute beat line, and a beat is not a quarter.** A
    note may end in a later bar than it began, so the onset and the probe are both
    placed by `grid.beat_offset` before they are compared; a `(bar, beat)` pair cannot
    express a duration that crosses a barline. And a whole note is `beat_type` beats,
    not four: in 2/2 a beat is a minim, so `duration * 4` would end a note written to
    the barline halfway through the next bar and re-strike it there.

    `head` rather than a bare note list because both numbers are the head's: the bar
    length, which places a position, and the beat value, which converts the duration.
    A caller that has only the notes has lost the metre, and guessing 4/4 for it is the
    defect this signature makes impossible.

    `None` before the melody starts for the same reason: nothing is sounding, and a step
    naming a note that has not begun is a claim about music that is not there.
    """
    position = (bar, round(beat, 6))
    found: Optional[HeadNote] = None
    for note in head.notes:
        if note.key > position:
            continue
        if found is None or note.key >= found.key:
            found = note
    if found is None:
        return None
    # A position that is also an onset is never a release, so it is answered before the
    # end is computed: a zero-length note would otherwise be ended by its own release.
    if found.key == position:
        return found.note_name
    beats_per_bar = head.beats_per_bar
    end = beat_offset(found.bar, found.beat, beats_per_bar) + found.duration * head.beat_type
    if beat_offset(bar, beat, beats_per_bar) >= round(end, 6):
        return None
    return found.note_name


def melody_state(head: Head, bar: int, beat: float) -> str:
    """Whether a melody note **articulates**, still **sounds**, or is absent at `(bar, beat)`.

    The three-way sibling of `melody_at`, for the question its two-way answer cannot
    ask. `melody_at` says only whether something is in force; §9.2 needs the split
    because only an **onset** is a position to reharmonise under — a held note was
    already harmonised where it began, and substituting the chord beneath it now would
    re-decide a decision already made under the very note that motivated it.

    Returns `"onset"`, `"held"` or `"silent"`:

    - **onset** — a note begins exactly here (its `HeadNote.key` is this position);
    - **held** — a note begun earlier still sounds here, so the position inherits it;
    - **silent** — nothing sounds, the melody has stopped or has not begun, which is
      exactly when `melody_at` returns `None`.

    **The first silent position after a note is that note's own release instant.** A note
    sounds over `[onset, end)`, so a position exactly on its end is silent rather than
    held: the tune has stopped, and §9.2 is free to put a chord there. A note whose
    release coincides with the next note's onset is the other way round — the position is
    that next note's onset, and the release is not what it is read as.

    **The onset test is `HeadNote.key`'s rounding, not a tolerance of its own.**
    The timelines this library compares against each other — `chord_at` against a
    note's position, `melody_at` against a grid position — round the beat the same
    way, so a value differing only in the seventh decimal is one position to both. An
    `abs(diff) < 1e-9` check here would be a second rule with its own answer, and the
    two would disagree exactly on the file strange enough to need them.

    A plain `str` rather than an enum: nothing branches on the answer yet — step C's
    reharmonise table is what will read it.

    `head` rather than a bare note list for the same reason `melody_at` takes it: the
    metre decides whether a note crossing a barline is still sounding on the far side,
    and a note list cannot carry it.
    """
    if melody_at(head, bar, beat) is None:
        return "silent"
    position = (bar, round(beat, 6))
    return "onset" if any(note.key == position for note in head.notes) else "held"


def _position_at(head: Head, absolute: float) -> Tuple[int, float]:
    """A beat on the absolute line as the `(bar, beat)` pair a slot carries.

    The inverse of `grid.beat_offset`, and the only place this module turns one
    back into the other: a segment built from durations has to name where it
    begins in the coordinates the step loop indexes by. Rounded to six places, so
    the sum of an eighth triplet is bar 3 beat 1 rather than a rest beginning a
    hair before the barline.
    """
    beats_per_bar = head.beats_per_bar
    index = math.floor(absolute / beats_per_bar + 1e-9)
    return index + 1, round(absolute - index * beats_per_bar + 1.0, 6)


@dataclass(frozen=True)
class MelodyRest:
    """A **notated silence** in the melody line: the span `--chord-fills` acts on.

    `bar`/`beat` are where the rest begins and `beats` its length in this head's
    metre. A rest may run past a bar line - that is a barline, not a musical split -
    so a position plus a duration is the honest shape rather than a bar range.
    """

    bar: int
    beat: float
    beats: float


def melody_rests(
    head: Head, section: Optional[Tuple[int, int]] = None
) -> List[MelodyRest]:
    """The gaps between the melody's notes, as spans of silence.

    **A rest is a notated silence, not a held note.** The sounding spans come from
    each note's onset and its written duration - `melody_at`'s arithmetic, on the
    same absolute beat line - and what is left between them is a rest. A note held
    across a bar line covers the far side of it, so the rest after it starts where
    the note actually stopped.

    Overlapping notes are merged rather than producing a negative gap: a part with
    two written voices can have a note begin before another ends, and silence is
    only where nothing sounds.

    The section's bounds are boundaries, so `--bars 5-8` fills 5-8 and nothing on
    either side of it.
    """
    lo, hi = section if section is not None else head.bars
    start = beat_offset(lo, 1.0, head.beats_per_bar)
    stop = beat_offset(hi, 1.0, head.beats_per_bar)
    spans: List[Tuple[float, float]] = []
    for note in head.notes:
        if not lo <= note.bar < hi:
            continue
        begin = beat_offset(note.bar, note.beat, head.beats_per_bar)
        end = begin + note.duration * head.beat_type
        spans.append((begin, min(end, stop)))
    spans.sort()

    rests: List[MelodyRest] = []
    cursor = start
    for begin, end in spans:
        if begin - cursor > BEAT_EPSILON:
            rests.append(_rest_at(head, cursor, begin - cursor))
        cursor = max(cursor, end)
    if stop - cursor > BEAT_EPSILON:
        rests.append(_rest_at(head, cursor, stop - cursor))
    return rests


def _rest_at(head: Head, absolute: float, beats: float) -> MelodyRest:
    """One rest span, with its start expressed in the slot coordinates."""
    bar, beat = _position_at(head, absolute)
    return MelodyRest(bar=bar, beat=beat, beats=round(beats, 6))


def _tick_key(bar: int, beat: float) -> Tuple[int, int]:
    """A position as a **grouping key**: its bar and its beat rounded to the nearest tick.

    The union of the melody's slots with `chord_slots`' needs to ask whether two producers mean
    the same instant, and that is the only question this answers. A beat is a float in
    practice - an eighth-note triplet's members land on 1.3333333333333333 and
    1.6666666666666665 - so comparing them directly is the comparison `BEAT_EPSILON` and
    `head_skeleton`'s own rounding both exist to avoid. Rounding to a `1/24` beat makes it
    integer equality, and every position either producer emits is already on that lattice.

    **A grouping key, never a position** - the same distinction `head_skeleton` draws: the
    slot still carries the note's own float beat, and only the *lookup* is rounded.
    """
    return (bar, round(beat * TICKS_PER_BEAT))


def _bar_resolution(
    head: Head, bar: int, beat_type: int, grouping: Optional[Sequence[int]] = None
) -> int:
    """The coarsest subdivision of a beat that holds every note this bar's melody writes.

    The bar's own rhythm is the grid it is generated on, which is what makes a generated
    chord land where the tune is: a bar of sixteenths is subdivided at sixteenths, an
    eighth-note-triplet bar at triplets, and a bar whose tune is all on the beat at beats.
    `grid_resolutions` is the vocabulary, converted through the metre - so no bar is ever
    generated finer than a sixteenth note however busy its tune reads.

    **The fallback is the beat, and it is a real answer rather than a failure.** A bar
    mixing a sixteenth with a triplet has no single resolution that divides both, and
    generating on its beats is what a player does under a line that busy. A bar with no
    melody at all has nothing to fit and so takes the beat too, which is the rule
    `chord_slots` has always followed for a bar the tune never enters.
    """
    onsets = [
        round((note.beat - 1.0) * TICKS_PER_BEAT)
        for note in head.notes
        if note.bar == bar
    ]
    resolutions = grid_resolutions(beat_type)
    # **A group is a candidate only when it divides the bar.** A 12/8 bar's generated
    # positions are its dotted-quarter pulses when the tune is written on them, which
    # is the coarsest reading of the bar's own rhythm; a mixed grouping (3+2) does not
    # divide the bar, so it is not offered and the beat remains the fallback. The
    # fallback stays `resolutions[0]` - the beat - rather than a group, so a bar mixing
    # a sixteenth with a triplet is still generated on its beats.
    group_ticks = TICKS_PER_BEAT * grouping[0] if grouping else 0
    span = head.beats_per_bar * TICKS_PER_BEAT
    coarse: Tuple[int, ...] = (
        (group_ticks,)
        if group_ticks > TICKS_PER_BEAT and span % group_ticks == 0
        else ()
    )
    return next(
        (
            resolution
            for resolution in coarse + resolutions
            if all(onset % resolution == 0 for onset in onsets)
        ),
        resolutions[0],
    )


def _generated_beats(
    head: Head, bar: int, beat_type: int, grouping: Optional[Sequence[int]] = None
) -> Tuple[float, ...]:
    """Every position a bar's own rhythm generates, at that bar's own resolution.

    Positioned from beat 1 so the first is the downbeat in any metre, and stepping by the
    resolution `_bar_resolution` chose. **Every one of these is a candidate, not a decision**:
    `_merge_chord_slots` drops the ones the melody already occupies and the ones it is still
    holding, and `chord_slots` drops the ones with no chord in force.
    """
    span = head.beats_per_bar * TICKS_PER_BEAT
    stride = _bar_resolution(head, bar, beat_type, grouping)
    return tuple(1.0 + tick / TICKS_PER_BEAT for tick in range(0, span, stride))


def _chord_grouping(
    head: Head, grouping: Optional[Sequence[int]]
) -> Sequence[int]:
    """The grouping `chord_slots` generates on: the caller's, or the head's own.

    A loaded head carries what its score stated (a direction, its beaming or a
    metronome); an unbeamed score and a hand-built head state nothing, and the
    metre's convention is the fallback.
    """
    if grouping is not None:
        return grouping
    if head.grouping:
        return head.grouping
    return default_grouping(head.beats_per_bar, int(head.beat_type))


def chord_slots(
    head: Head,
    section: Optional[Tuple[int, int]] = None,
    grouping: Optional[Sequence[int]] = None,
) -> List[Tuple[Optional[str], str, int, float, float]]:
    """Every position the bar's own rhythm generates, **including positions no melody has**.

    **The complement of `head_skeleton`, and the union of the two is what a comping part
    needs.** `head_skeleton` yields one slot per written note; this yields one per
    position the bar's rhythm generates. On the melody-bearing route the melody is ours
    and "a chord under each note" is the chord-melody idiom, so the two must *not* be
    merged. On the comping route the guitar is not under the melody, so a position with no
    note is a position the chord of the tune still occupies — and open-issues item 1
    measures what dropping those costs.

    **A position is generated at every subdivision of the bar's own rhythm**, from
    `_generated_beats`: a bar of sixteenths is generated at sixteenths, a triplet bar at
    eighth-note triplets, and a bar whose tune is all on the beat is generated at beats.
    So a position the tune *skips* inside a bar it occupies is a position this function
    reports, which is what closes `docs/history/open-issues.md` item 1's remaining half.

    Returns `(melody, quality, chord, bar, beat, duration)`, and **`melody` is the note in
    force at that position, not a written one** — the rule `bass._bass_slots` already uses
    for an invented beat — or **`None` when no note sounds**: the melody has stopped or has
    not begun, and inventing one there is the failure `chord_at` refuses when it returns
    `None`. `ArrangementStep.melody` is `Optional` to carry that honesty into the step, the
    renderers print the absence blank, and `melody_state` says whether a present note is an
    onset or a hold when that distinction is the question (§9.2's reharmonise rule).

    **A position with no melody note and no chord is skipped**, never guessed. Bar 1 beat
    1 of `synthetic_cut_time` is exactly that — a quarter rest under a `<harmony>` that only
    arrives on beat 1.5 — so there is no harmony to state and `chord_at` returns `None`.
    That is the "never guess a chord" rule holding, not a gap in the union.

    **`duration` is the distance to the next generated position, capped at the bar line**,
    because a stab is struck and released rather than tied onward. That is the arithmetic
    open-issues item 1 says the note path gets wrong, done here deliberately: this layer is
    placing the chord, so it decides how long it sounds. It is also why a chord is not held
    across a barline when the next bar names nothing.

    `section` is `head_skeleton`'s half-open `(first, last + 1)` bar range, so the two
    agree on which bars a part covers; the default is the whole head.
    """
    lo, hi = section if section is not None else head.bars
    beats_per_bar = head.beats_per_bar
    # The other half of the same conversion, used the other way round: a *length* in
    # beats becomes whole notes by dividing by `beat_type`, because one whole note is
    # `beat_type` beats (four quarters at `4 / beat_type` quarters to the beat). Dividing
    # by `beats_per_bar` instead is right only where the numerator and the denominator
    # are equal - 4/4 and 2/2, six of the seven committed heads - and in 3/4 it made
    # every synthetic comping slot a third too long.
    beat_type = int(head.beat_type)
    if beats_per_bar <= 0:
        return []
    # The head states the count and the denominator; `auto` is the grouping that
    # follows from them. A direct caller that wants the simple reading passes
    # `(1,) * beats_per_bar`.
    grouping = _chord_grouping(head, grouping)

    # Every position the bar's own rhythm generates, in `(bar, beat)` order. A bar of
    # sixteenths is generated at sixteenths, a triplet bar at eighth-note triplets, and a
    # bar whose tune is all on the beat is generated at beats - which is what lets a
    # position the tune *skips* inside a bar it occupies become a slot.
    positions: List[Tuple[int, float]] = []
    for bar in range(lo, hi):
        positions.extend(
            (bar, beat) for beat in _generated_beats(head, bar, beat_type, grouping)
        )
    if not positions:
        return []
    positions.sort()

    return _slots_at(head, positions, beat_type, beats_per_bar)


def rhythm_slots(
    head: Head,
    rhythm: Rhythm,
    section: Optional[Tuple[int, int]] = None,
    grouping: Optional[Sequence[int]] = None,
    extra_positions: Sequence[Tuple[int, float]] = (),
) -> List[Tuple[Optional[str], str, int, float, float]]:
    """Every position `rhythm` names, as slots, including positions no note has.

    The complement of `head_skeleton` for a **requested** chord rhythm: `1and` in a
    4/4 bar is beat 1.5 of every bar in the section, and a position the tune merely
    holds through is still one the chord attacks on - a stab under a held note is
    wanted, so unlike the melody-anchored union there is no hold filter here.

    `extra_positions` are the caller's own positions beside the rhythm's - the tune's
    written onsets, for a rhythm that names `melody` *and* positions and so plays
    both. They are unioned on `(bar, beat)` with the rhythm's, and every slot is built
    by `_slots_at` with `_stab_length` over the whole set: the two sources cannot
    disagree about the harmony in force, nor about how long an attack rings.
    """
    lo, hi = section if section is not None else head.bars
    grouping = _chord_grouping(head, grouping)
    beats = rhythm_beats(rhythm, head.beats_per_bar, grouping)
    at: Dict[Tuple[int, int], Tuple[int, float]] = {}
    for bar in range(lo, hi):
        for beat in beats:
            at.setdefault(_tick_key(bar, beat), (bar, beat))
    for bar, beat in extra_positions:
        if lo <= bar < hi:
            at.setdefault(_tick_key(bar, beat), (bar, beat))
    positions = [at[key] for key in sorted(at)]
    return [
        (_note, _name, bar, beat, _stab_length(head, beat, length, grouping))
        for (_note, _name, bar, beat, length) in _slots_at(
            head, positions, int(head.beat_type), head.beats_per_bar
        )
    ]


def _stab_length(
    head: Head, beat: float, length: float, grouping: Sequence[int]
) -> float:
    """How long a requested chord attack rings: its **felt beat**, and no further.

    The chord part states a harmony to somebody else's ear, so an attack that rang
    until the next requested position would still be sounding over a beat it was not
    asked for - `--chord-on 1` in a 4/4 bar would hold four beats, and the tab would be
    one chord per bar rather than one stab on each downbeat. The length is the rest of
    the felt beat the attack sits in (a whole pulse in 6/8, half a bar in 2/2), and the
    gap to the next position still caps it: two attacks inside one beat are two
    stabs, not one.

    `length` is the distance to the next requested position, already in whole notes;
    the felt beat is read from the grouping rather than from the denominator because
    that is what a compound metre's pulse is.
    """
    felt = (_felt_beat_end(beat, grouping) - beat) / head.beat_type
    return round(min(length, felt), 6)


def _felt_beat_end(beat: float, grouping: Sequence[int]) -> float:
    """The beat number that ends the group `beat` falls in, in the same units.

    A group of one is the beat itself, so its end is the next beat; a group of three
    is a 6/8 pulse and ends two denominator units later. A beat past every group's
    end - which only a caller reading a position from another metre can supply - ends
    at the bar line rather than raising: it is already outside where this can be
    wrong in a way a length would show.
    """
    starts = group_starts(sum(grouping), grouping)
    for start, group in zip(starts, grouping):
        if beat < start + group - BEAT_EPSILON:
            return start + float(group)
    return float(sum(grouping)) + 1.0


def _slots_at(
    head: Head,
    positions: List[Tuple[int, float]],
    beat_type: int,
    beats_per_bar: int,
) -> List[Tuple[Optional[str], str, int, float, float]]:
    """One slot per position the caller resolved, with the harmony in force there.

    Shared by the two position sources - the generated positions and a rhythm's
    felt beats - so the harmony lookup, the slash-bass promotion and the
    "distance to the next position" duration cannot differ between them.
    """
    slots: List[Tuple[Optional[str], str, int, float, float]] = []
    for index, (bar, beat) in enumerate(positions):
        change = chord_at(head.chords, bar, beat)
        if change is None or change.quality is None:
            # Nothing in force here, or a chord this library cannot voice. The latter was
            # counted in `Head.unmapped` at load time, so the gap is reported rather than
            # silent — the rule `head_skeleton` follows for a note.
            continue
        following = positions[index + 1] if index + 1 < len(positions) else None
        if following is not None and following[0] == bar:
            length = (following[1] - beat) / beat_type
        else:
            length = (beats_per_bar - beat + 1.0) / beat_type
        # The symbol carries the whole harmony, promotion included: `parse_symbol`
        # applies Rule B itself, so a triad over its own seventh arrives a seventh
        # chord without a second spelling to keep in step.
        name = f"{change.chord}/{change.bass}" if change.bass else change.chord
        note = melody_at(head, bar, beat)
        slots.append((note, name, bar, beat, length))
    return slots


def fill_slots(
    head: Head,
    request: ResolvedRequest,
    section: Optional[Tuple[int, int]] = None,
    grouping: Optional[Sequence[int]] = None,
) -> List[Tuple[Optional[str], str, int, float, float]]:
    """The chord slots `--chord-fills` puts in the tune's rests.

    A **rest-relative policy**, not a rhythm: `--chord-on` names the positions the
    chord attacks on, and this answers the other question - what the chord does
    while the tune is *not* playing. `hold` states one chord per rest, `comp` one
    per felt beat inside it, and both attack at the rest's onset wherever that is.

    A rest is **split** where the harmony changes and where a `--chord-on` target
    falls inside it, because either is a new chord to state; a fill then continues
    after the target. The union in `_head_slots` deduplicates a fill landing on a
    target, and the target's slot is the one kept.

    A rest with **no chord in force** (`NC`, or a symbol this library cannot voice)
    gets nothing: there is no chord to state, and inventing one is the failure every
    other position rule in this module refuses.
    """
    fills = request.chord_fills
    if fills == CHORD_FILLS_NONE:
        return []
    lo, hi = section if section is not None else head.bars
    lengths = tuple(grouping) if grouping else (1,) * head.beats_per_bar
    cuts = _fill_cuts(head, request.chord_rhythm, (lo, hi), lengths)
    slots: List[Tuple[Optional[str], str, int, float, float]] = []
    for rest in melody_rests(head, (lo, hi)):
        begin = beat_offset(rest.bar, rest.beat, head.beats_per_bar)
        end = begin + rest.beats
        bounds = [begin] + [cut for cut in cuts if begin < cut < end] + [end]
        for start, stop in zip(bounds, bounds[1:]):
            slots.extend(_fill_segment(head, start, stop, fills, lengths))
    return slots


def _fill_cuts(
    head: Head,
    rhythm: Optional[Rhythm],
    section: Tuple[int, int],
    grouping: Tuple[int, ...],
) -> List[float]:
    """The positions that split a rest: a harmony change, and a chord target.

    Both mean "a new chord starts here" to a fill, and both are placed on the
    absolute beat line so a rest can be cut by either without asking which bar it
    lies in. `rhythm` may name nothing (`--chord-on none`), which is the mode where
    the chord exists *only* in the rests.
    """
    lo, hi = section
    points = {
        round(beat_offset(change.bar, change.beat, head.beats_per_bar), 6)
        for change in head.chords
        if lo <= change.bar < hi
    }
    if rhythm is not None and not rhythm.is_none:
        for _melody, _name, bar, beat, _length in rhythm_slots(
            head, rhythm, section, grouping
        ):
            points.add(round(beat_offset(bar, beat, head.beats_per_bar), 6))
    return sorted(points)


def _fill_segment(
    head: Head,
    start: float,
    stop: float,
    fills: str,
    grouping: Tuple[int, ...],
) -> List[Tuple[Optional[str], str, int, float, float]]:
    """One un-split stretch of rest: its attacks, each with the harmony in force."""
    positions = [start]
    if fills == CHORD_FILLS_COMP:
        positions.extend(_felt_starts(head, start, stop, grouping))
    slots: List[Tuple[Optional[str], str, int, float, float]] = []
    for index, position in enumerate(positions):
        bar, beat = _position_at(head, position)
        change = chord_at(head.chords, bar, beat)
        if change is None or change.quality is None:
            continue
        following = positions[index + 1] if index + 1 < len(positions) else stop
        name = f"{change.chord}/{change.bass}" if change.bass else change.chord
        slots.append(
            (
                None,
                name,
                bar,
                beat,
                round((following - position) / head.beat_type, 6),
            )
        )
    return slots


def _felt_starts(
    head: Head, start: float, stop: float, grouping: Tuple[int, ...]
) -> List[float]:
    """The felt beats **strictly inside** `(start, stop)`, on the absolute line.

    A rest's onset is the fill's first attack wherever it falls, so this answers
    only the interior - the group starts a `comp` also attacks on. The grouping
    rather than the denominator count, for the reason `rhythm_beats` reads it: a
    6/8 bar has two pulses, not six eighths.
    """
    beats_per_bar = head.beats_per_bar
    first_bar = _position_at(head, start)[0]
    last_bar = _position_at(head, stop - BEAT_EPSILON)[0]
    starts = group_starts(beats_per_bar, grouping)
    found: List[float] = []
    for bar in range(first_bar, last_bar + 1):
        for beat in starts:
            absolute = beat_offset(bar, beat, beats_per_bar)
            if start + BEAT_EPSILON < absolute < stop - BEAT_EPSILON:
                found.append(absolute)
    return found


def head_skeleton(
    head: Head,
    section: Optional[Tuple[int, int]] = None,
) -> List[Tuple[Tuple[Optional[str], str], int, float, float]]:
    """A loaded head as slots: (triple, bar, beat, duration), **one per written note**.

    The melody half is typed `Optional[str]` although every note *this* function
    emits is written: its slots are unioned with `chord_slots`', whose positions
    include ones no note occupies, and one list has one type (§9.3 step B).

    **There is no reduction here.** The soprano plays the tune: every note the file wrote
    gets a slot, on the beat it was written, down to the floor (a 16th in practice; 32nds
    do not occur in real material). Where the *chords* fall is a separate question with
    its own axis, and answering it here would quantise notes onto a grid and drop any pair
    closer together than the grid - a note of the tune going missing with nothing said.

    `section` is a half-open (start, end) bar range, defaulting to the whole head.
    `pick` is not needed: it chose which of several notes sharing a slot represented it,
    and no two notes share a slot.

    A note under no harmony becomes a melody-only `NO_CHORD` step, which
    `arrange_progression` short-circuits rather than inventing a chord for. A note
    whose chord symbol the loader could not translate is **skipped** rather than
    guessed: a wrong chord under a good melody is worse than a gap.
    """
    lo, hi = section if section is not None else head.bars
    notes = [n for n in head.notes if lo <= n.bar < hi]
    if not notes:
        return []

    # **The rounding is a grouping key, never a position.** It exists so that two
    # notes read from different `divisions` compare equal as one slot, and for that
    # it is right. It must not be the value either, and a triplet is what shows why:
    # `1/3` has no exact binary form, so the beats of an eighth-note triplet are
    # 1.3333333333333333 and 1.6666666666666665 - and rounding to six places sends
    # the first DOWN and the second UP, so the gap between them grows from a third
    # to a third plus 6.7e-07.
    #
    # That surplus is not noise downstream. `tabscore.score_events` caps each note at the
    # length the file wrote, so the extra becomes a **rest of 6.7e-07 quarters** -
    # a length MusicXML cannot express, which music21 rounds up to a whole triplet
    # note. Bar 1 of "Trouble in Mind" came out with four notes under one `3`
    # bracket, a rest inside the triplet, and a bar two beats long instead of one;
    # the committed triplet head carried 13 such rests. So the slot carries
    # `chosen.beat`, the note's own float, and only the grouping is rounded.
    groups = {(note.bar, round(note.beat, 6)): note for note in notes}

    slots: List[Tuple[Tuple[Optional[str], str], int, float, float]] = []
    for key in sorted(groups):
        chosen = groups[key]
        # `key[0]` rather than unpacking: the bar is an int and needs no rounding, and
        # unpacking both is what made the rounded beat the obvious thing to use.
        bar = key[0]
        beat = chosen.beat
        if chosen.quality is None:
            if chosen.chord == NO_CHORD:
                slots.append(
                    ((chosen.note_name, NO_CHORD), bar, beat, chosen.duration)
                )
            # Otherwise the chord was untranslatable and the slot is dropped; the
            # loader counted it in `Head.unmapped`, so the gap is reported rather
            # than silent.
            continue
        # A triad whose bass is its own seventh implies the seventh chord, and
        # `parse_symbol` applies that promotion to the symbol itself - so the name
        # carries both facts and there is no second spelling to keep in step.
        name = f"{chosen.chord}/{chosen.bass}" if chosen.bass else chosen.chord
        slots.append(((chosen.note_name, name), bar, beat, chosen.duration))
    return slots


def _melodyless(
    head: Head, options: ArrangeOptions
) -> Tuple[ArrangeOptions, Optional[str]]:
    """A chord chart, with the melody-anchored default answered as comping.

    `chord-on=melody` attaches the chord to the written tune, and a file with **no
    melody notes** has none to attach it to. The rhythm becomes `every-beat` - the
    same default `--no-melody` uses - and the substitution is returned as a note,
    because a request quietly rewritten is what the annotation invariant exists to
    prevent. `None` means the request was left alone.
    """
    if len(head):
        return options, None
    rhythm = resolve_request(
        options.request, head.beats_per_bar, _chord_grouping(head, None)
    ).chord_rhythm
    if not rhythm.wants_melody or rhythm.positions:
        return options, None
    return (
        replace(
            options,
            request=replace(options.request, chord_on=RHYTHM_EVERY_BEAT),
        ),
        "the head has no melody notes, so the chord comps on every felt beat "
        "(chord-on=every-beat) - it is a chord chart rather than a tune",
    )


def _head_request(
    head: Head,
    options: Optional[ArrangeOptions],
    *,
    non_chord_tone: str,
    request: Request,
    time_signature: TimeSignature,
) -> Tuple[ArrangeOptions, Optional[str]]:
    """The arrangement request for a loaded head, from either spelling.

    The head owns the **count and the denominator**: they describe the bars the
    slots came from, and a caller cannot know them before the file is read, so the
    score's own replace whatever a supplied `TimeSignature` states. The metre's
    third fact - its grouping - is the one fact of it a caller may set, and it is
    read off that same `TimeSignature` rather than a parameter of its own.

    `auto` means "use what the file says, and the metre's convention if it says
    nothing", and it is also what the untouched `COMMON_TIME` default means, so a
    bare `arrange_xml_head(path)` reads the score's metre. A caller who *did* set a
    grouping meant the metre, so a count or denominator that disagrees with the file
    is refused rather than silently replaced: a `TimeSignature` two of whose three
    fields are ignored is a value that lies.

    The implementation axes are derived from the request, so the two spellings of the
    request have nothing to disagree about. The request and the metre are **input facts**
    instead - *what is being arranged* rather than *how to play it* - so they sit *beside*
    `options=`
    rather than inside it, and `settle_input_fact` reconciles the two spellings: the
    keyword wins, the object's own is read only when the keyword was left at its
    default, and both stated raises. `non_chord_tone` is the one remaining knob, and a
    keyword beside `options=` raises rather than silently choosing.
    """
    if options is not None:
        if non_chord_tone != "extension":
            raise ValueError(
                "pass either options= or the individual arrangement knobs, not both"
            )
        request = settle_input_fact(
            request, options.request, DEFAULT_REQUEST, "request", "arrange_xml_head"
        )
        time_signature = settle_input_fact(
            time_signature, options.time_signature, COMMON_TIME,
            "time_signature", "arrange_xml_head",
        )
    else:
        options = ArrangeOptions(non_chord_tone=non_chord_tone, request=request)

    stated = format_grouping(head.grouping) if head.grouping else GROUPING_AUTO
    supplied = time_signature
    grouping = supplied.grouping
    if grouping != GROUPING_AUTO and (
        supplied.beats_per_bar != head.beats_per_bar
        or supplied.beat_type != head.beat_type
    ):
        raise ValueError(
            f"the score is in {head.beats_per_bar}/{head.beat_type}, but "
            f"time_signature= says {supplied.beats_per_bar}/{supplied.beat_type}; "
            f"the file owns the count and the denominator, so only the grouping "
            f"can be overridden"
        )
    # One place builds the request and the metre, whichever door the caller came
    # through: the settled `request` may be the keyword's rather than the object's.
    options = replace(
        options,
        request=request,
        time_signature=TimeSignature(
            head.beats_per_bar,
            head.beat_type,
            grouping if grouping != GROUPING_AUTO else stated,
        ),
    )
    return _melodyless(head, options)


def _head_slots(
    head: Head,
    section: Optional[Tuple[int, int]],
    options: ArrangeOptions,
    grouping: Tuple[int, ...],
) -> List[Tuple[Tuple[Optional[str], str], int, float, float]]:
    """The head's slots: the tune's notes, with the comping positions added.

    **The union is gated on whether the guitar comps at all - not on the route.**
    A selection that *comps* states the chord where the tune is silent -
    `docs/comping-styles.md` §9.3 step D - which is a chord part with no tune to
    play: a melody-only selection plays the tune and nothing else, and a **lone bass
    line** has no chord to state at a position the tune left.
    `docs/history/open-issues.md` item 1 holds the measurement.

    **A requested rhythm is the whole timeline of a selection with no tune to play.**
    The positions it names are the ones the guitar attacks on, each ringing its felt
    beat - `_comp_only_timeline`, because the tune's written rhythm is not the bar's
    when nothing sings it. A selection that *does* sing the tune keeps the union: every
    written note is a step there, and the request only adds positions to it.
    """
    slots = head_skeleton(head, section)
    # The parts gate reads the **derivation**, which is the same value the step loop
    # reads: the selection is what the request's own questions decide.
    axes = resolve_request(options.request, head.beats_per_bar, grouping)
    parts = axes.parts
    if parts_has_melody_only(parts):
        return slots
    # **A requested rhythm wins, and the engine's own union is the fallback.** The
    # request is the public vocabulary for where a chord falls, so a caller who names
    # positions gets them whatever else is spelled - spelling `texture` must not
    # silently answer a different question about the chord's rhythm. What is left for
    # the fallback is a request that names nothing added *and* a selection with no
    # tune to play: that part states the chord of the tune in a bar the tune never
    # enters, while a selection that sings the tune already articulates every bar it
    # enters.
    request = axes
    chord_on = request.chord_rhythm
    # `melody` alone adds nothing to the union: the skeleton already has one chord per
    # written note. A **positions** rhythm adds the attacks the caller named.
    named = not chord_on.is_none and not (
        chord_on.wants_melody and not chord_on.positions
    )
    comps = parts_have_chord(parts) and not parts_have_melody(parts)
    if named and comps:
        return _comp_only_timeline(head, slots, chord_on, section, grouping)
    extra: List[Tuple[Optional[str], str, int, float, float]] = []
    if named:
        extra = rhythm_slots(head, chord_on, section, grouping)
    if not extra and comps:
        return _merge_chord_slots(slots, head, section, grouping)
    extra.extend(fill_slots(head, request, section, grouping))
    if head.first_bar_implicit:
        # The anacrusis is not comping space, for the reason `_merge_chord_slots`
        # gives: a chord there fills the pickup and moves the head's downbeat.
        extra = [slot for slot in extra if slot[2] != head.bars[0]]
    return _unioned(slots, extra)


def _comp_only_timeline(
    head: Head,
    skeleton: List[Tuple[Tuple[Optional[str], str], int, float, float]],
    chord_on: Rhythm,
    section: Optional[Tuple[int, int]],
    grouping: Tuple[int, ...],
) -> List[Tuple[Tuple[Optional[str], str], int, float, float]]:
    """A comp-only selection's slots: **the positions the request names**, and no others.

    The chord is the only thing the guitar plays, so the tune's written rhythm is not
    the bar's rhythm: a note that happens to begin between two named positions is not
    an attack, and a named position rings its felt beat (`_stab_length`) rather than
    the length of a note beginning there. Both rules are `rhythm_slots`', so nothing
    here re-times an attack - the alternative is a slot per written note whose
    *duration* is the horn's, which is a chord either cut short by a triplet or left
    sounding over a beat the caller did not ask for.

    The melody column is still `melody_at` at every position, because the comp is
    voiced **under** the tune even when the tune is not played: `leaving_room_for_the_tune`
    reads it as the ceiling. A rhythm that also names `melody` plays the written onsets
    too, which is the one way the tune contributes positions of its own.

    No fill is added, and not for want of asking: `--chord-fills` is a policy for the
    tune's notated rests, so `resolve_request` refuses it on a selection with no melody
    part (`options._refuse_melody`). There is no rest to fill because there is no tune.

    A **pickup bar** keeps the skeleton's slots and takes no requested ones, for the
    reason `_merge_chord_slots` gives: they are what the pickup *is*, and a chord
    attack in the short bar would erase it and move the head's downbeat.
    """
    onsets = [(slot[1], slot[2]) for slot in skeleton] if chord_on.wants_melody else []
    slots = rhythm_slots(head, chord_on, section, grouping, onsets)
    base: List[Tuple[Tuple[Optional[str], str], int, float, float]] = []
    if head.first_bar_implicit:
        first = head.bars[0]
        base = [slot for slot in skeleton if slot[1] == first]
        slots = [slot for slot in slots if slot[2] != first]
    return _unioned(base, slots)


def arrange_xml_head(
    path: Union[str, Path],
    part: Optional[str] = None,
    non_chord_tone: str = "extension",
    fallback: Optional[str] = None,
    section: Optional[Tuple[int, int]] = None,
    request: Request = DEFAULT_REQUEST,
    time_signature: TimeSignature = COMMON_TIME,
    options: Optional[ArrangeOptions] = None,
) -> Tuple[List[ArrangementStep], Head, List[str]]:
    """Loads a MusicXML head, reduces it and arranges it, end to end.

    Returns the steps, the `Head` they came from - so the caller can report the
    title, the metre and the loader's notes - and any notes worth printing.

    The voicings come from `arranger.slots.arrange_slots`, the engine's own slot
    layer, so the non-chord-tone strategies, the opt-in diminished retry, the
    repeated-melody hold and the slash-bass preference are the engine's rather than
    this importer's. Only the *selection* is this module's business.

    `fallback` may be "diminished"; it replaces the written chord, so it is off
    unless asked for.

    What to play is asked as `request=` - the six questions - and the implementation axes
    are derived from it. `options=ArrangeOptions(...)` carries the knobs that are not a
    question about the music, which must be left at their defaults when the score states
    the metre and the key: that is the spelling `head` uses.

    The metre trap bites hardest here: three of the four committed scores are in cut
    time, whose beat is a half note, so a rule that assumed four beats to the bar
    would put a full chord on a beat that does not exist in a 2/2 head. A count
    without a denominator is not a metre.

    `head.beat_type` goes with it, and it is not a duplicate: the count says which beats
    exist, the denominator says how long one lasts. The walking bass converts each
    slot's whole-note `duration` into beats with it, and the one committed 3/4 head is
    where passing the count in its place shows up.

    The metre is one value, `time_signature=`, and its **grouping** - which denominator
    units are felt as one beat - is the one fact of it a caller may set. `auto` (the
    default, and `COMMON_TIME`'s own) reads the score's statement: an `N+N` direction,
    then the primary beaming, then a metronome pulse, and finally the metre's convention
    (threes for 6/8, 9/8 and 12/8; one per beat otherwise). An explicit `3+2` overrides
    the file, and the count and denominator must then agree with the score's, because
    the file owns those two. A conventional simple metre ignores its beaming, because a
    notation program's beam pairs restate the beat rather than group it.
    """
    head = load_musicxml(path, part)
    options, melodyless = _head_request(
        head,
        options,
        non_chord_tone=non_chord_tone,
        request=request,
        time_signature=time_signature,
    )
    # Resolved once here, because this layer needs the tuple **before** the engine
    # sees it: `_merge_chord_slots` generates the comping positions, and the engine
    # resolves the same request again for the step loop. One pure function, two
    # calls, so the two cannot disagree.
    resolved_grouping = options.time_signature.resolved_grouping
    slots = _head_slots(head, section, options, resolved_grouping)
    progression = [slot[0] for slot in slots]
    timings = [(slot[1], slot[2], slot[3]) for slot in slots]
    # §9.3 step C: which slots the melody **articulates** on. On the note path every
    # slot is a written note, so every one is an onset; the comping union adds
    # positions a note only *sustains* through or is silent at, and §9.2 reharmonises at
    # an onset only - a held position was decided where the note began. Computed here
    # because `melody_state` reads the head's own notes, which only this layer has, and
    # the engine's comping branch is downstream of the merge that produced the order.
    onsets = {
        index
        for index, slot in enumerate(slots)
        if melody_state(head, slot[1], slot[2]) == "onset"
    }
    # Both halves of the metre are in `options`: the count says which beats exist,
    # the denominator says how long one lasts, and `arrange_xml_head` took them from
    # the head above. The walking bass is the only engine rule that needs the second.
    steps, _rescued, notes = arrange_slots(
        progression,
        timings,
        fallback=fallback,
        onsets=onsets,
        options=options,
    )
    report = list(head.report) + notes
    if melodyless:
        report.insert(0, melodyless)
    return steps, head, report


def _merge_chord_slots(
    slots: List[Tuple[Tuple[Optional[str], str], int, float, float]],
    head: Head,
    section: Optional[Tuple[int, int]],
    grouping: Optional[Sequence[int]] = None,
) -> List[Tuple[Tuple[Optional[str], str], int, float, float]]:
    """`head_skeleton`'s slots plus `chord_slots`', in one ordered list.

    **A union on `(bar, beat)`, and the melody slot wins a collision.** A position that
    has both a written note and a generated one is one slot, not two: the note carries a
    duration the score wrote and the exact pitch the horn is playing, so it is strictly
    the better description of that instant. `chord_slots`' contribution is the positions
    where there is no note, which is the only thing this function adds.

    **Every position a bar's rhythm allows contributes, inside a melody bar included** —
    this is `docs/history/open-issues.md` item 1's remaining half, and the two rules that say
    which of them become slots are what make it a fix rather than a rewrite:

    - **the note path wins**, so a position the tune writes is left exactly as it was, with
      the note's own duration and pitch (`_tick_key` groups the two producers' spellings of
      one instant, so a triplet does not become two slots);
    - **a position the tune is still *holding* is not a slot at all** (§9.2). The note was
      harmonised where it began, under the very note that motivated the chord, so
      re-stating a chord beneath it would re-decide a decision already made. Measured on
      the committed heads, that holds back far more positions than it admits.

    A **melody-less bar** is the case `chord_slots` has always covered.

    **A pickup bar is the one place nothing contributes.** `Head.first_bar_implicit` is
    the source's statement that bar 1 is an anacrusis, so its short bar is not space for
    an accompaniment: filling it would erase the pickup the renderers infer from the
    bar's content. The written melody slots stay, because they are what the pickup is.

    **Order is `(bar, beat)`, which is what both producers already emit.** Sorting is
    done here rather than trusted from either, because the step loop indexes the melody
    and a `bass_only`-style union that arrived out of order would attribute the wrong
    note to the wrong beat, reached from a new direction.
    """
    extra = chord_slots(head, section, grouping)
    if head.first_bar_implicit and extra:
        # **A pickup bar is not comping space.** Its missing time is the anacrusis the
        # renderers infer from the bar's content; a generated chord there fills the
        # short bar, erases the pickup, and (because the bar is no longer short) moves
        # the whole head to a different downbeat. The melody's own slots stay - they
        # are what the pickup *is* - and the accompaniment starts in bar 2.
        first = head.bars[0]
        extra = [slot for slot in extra if slot[2] != first]
    # **§9.2, and the whole of what this union holds back.** The positions
    # `_generated_beats` produced are candidates for slots, and the tune's own written
    # positions are already in `slots` - so all that is left to refuse is a position where
    # a note is still *held*. A note sounds over `[onset, end)`, so the instant it is
    # released is not one of them: the tune has stopped and the chord part states the
    # chord, which is what `docs/history/open-issues.md` item 6 measured. It is refused here
    # rather than in `chord_slots` because this is the union: `chord_slots` reports the
    # geometry of the bar, and which of those positions become steps is this function's
    # question. `chord_slots` has already skipped
    # the positions with no chord in force, so a silent position with no `<harmony>` behind
    # it still adds nothing and is never guessed a chord.
    extra = [
        slot
        for slot in extra
        if melody_state(head, slot[2], slot[3]) != "held"
    ]
    return _unioned(slots, extra)


def _unioned(
    slots: List[Tuple[Tuple[Optional[str], str], int, float, float]],
    extra: List[Tuple[Optional[str], str, int, float, float]],
) -> List[Tuple[Tuple[Optional[str], str], int, float, float]]:
    """The skeleton with `extra` positions added, one step per `(bar, beat)`.

    A position the melody already has a slot on keeps the skeleton's - it is the
    longer of the two, because it runs for the note's written duration - and the
    result is in `(bar, beat)` order, which is the order the step loop indexes.
    """
    if not extra:
        return slots
    existing = {_tick_key(bar, beat) for _pair, bar, beat, _dur in slots}
    merged = list(slots)
    for melody, name, bar, beat, length in extra:
        if _tick_key(bar, beat) in existing:
            continue
        merged.append(((melody, name), bar, beat, length))
    merged.sort(key=lambda slot: (slot[1], slot[2]))
    return merged


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _key_label(head: Head) -> str:
    """
    The head's key for the CLI header, as a name: `Eb major`, `C minor`, `C major`.

    Named rather than counted because the header is read by a person deciding
    whether this is the arrangement they meant, and `-3 (major)` is not that.

    The tonic is the circle of fifths, read as one table rather than two: the flat
    side and the sharp side are the same circle approached from opposite ends, so
    -3 is Eb major and -1 is F major - not "one sharp fewer" on the other spelling.
    The minor tonic is the **relative** minor, three semitones below the major one, so
    a signature of -3 is Eb major or C minor and never Eb minor: the mode decides
    which of the two, not the count.

    **A mode the head does not state is not guessed**, so -3 with no mode reads
    `Eb major/C minor` - the two keys that signature spells, which is what the file
    said and all it said. C major is the one case not listed twice, because a
    signature of zero is one key under either mode rather than a signature sitting
    between two.
    """
    # The circle of fifths as two parallel halves, indexed identically: position 0
    # is seven flats and position 14 is seven sharps, and each is the relative minor
    # of the other.
    major = ("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F",
             "C", "G", "D", "A", "E", "B", "F#", "C#")
    minor = ("Ab", "Eb", "Bb", "F", "C", "G", "D",
             "A", "E", "B", "F#", "C#", "G#", "D#", "A#")
    fifths, mode = head.key_fifths, head.key_mode
    index = fifths + 7
    if mode == "major":
        return f"{major[index]} major"
    if mode == "minor":
        return f"{minor[index]} minor"
    if fifths == 0:
        return "C major"
    return f"{major[index]} major/{minor[index]} minor"


def _head_options(args: Any) -> ArrangeOptions:
    """The `head` command's request, as the engine's one value.

    `--chord-on` reaches the request as the flag gave it, or as the request's own
    default when the flag was absent. What that default *means* under `--no-melody`
    - every felt beat, because this guitar has no written onsets to attach chords to
    - is `resolve_request`'s derivation, so the flag layer holds no metre-dependent
    rule of its own.
    """
    return ArrangeOptions(
        non_chord_tone=args.non_chord_tone,
        request=Request(
            melody=not args.no_melody,
            chord_on=args.chord_on if args.chord_on is not None else RHYTHM_MELODY,
            chord_notes=args.chord_notes,
            chord_fills=args.chord_fills,
            bass_on=args.bass_on,
            bass_notes=args.bass_notes,
        ),
    )


def _request_line(head: Head, args: Any) -> str:
    """The canonical request, for the run header.

    Resolved against the head's own metre, so the positions printed are the ones
    this score's bars actually have; the spelling parses back, which is what
    `tests/test_cli.py` asserts rather than the wording.
    """
    grouping = resolve_grouping(
        head.grouping if head.grouping else GROUPING_AUTO,
        head.beats_per_bar,
        head.beat_type,
    )
    resolved = resolve_request(
        _head_options(args).request, head.beats_per_bar, grouping
    )
    return format_request(resolved)


def _print_play_order(head: Head) -> None:
    """The repeats/jumps line: the played bars, and the written score they came from.

    The arrangement is the bars played; a score is written with repeats and jumps.
    Saying both keeps the header's `bars 1-66` from reading as a claim about a file
    that now holds the written score.
    """
    written = len(set(head.written_bars.values()))
    jumped = any(m.kind.startswith("da_") for m in head.markers)
    label = "repeats and jumps" if jumped else "repeats"
    print(
        f"  {label}: {written} written bars play as "
        f"{head.bars[1] - head.bars[0]} - signposted, not written out"
    )


def _print_metre_notes(head: Head, args: Any) -> None:
    """The header's grouping line, and the beats `targets` fills.

    The grouping is the score's own where it states one (`Head.grouping`), and the
    metre's convention otherwise, so the line cannot name a felt beat the arrangement
    does not use. Its provenance is printed because "3+2" from a direction and "3+2"
    from the metre's convention are different claims about the file. Printed only
    when it is not one group per beat, because that is the shipped reading and
    saying it on every 4/4 head would be noise.
    """
    grouping = resolve_grouping(
        head.grouping if head.grouping else GROUPING_AUTO,
        head.beats_per_bar,
        head.beat_type,
    )
    starts = group_starts(head.beats_per_bar, grouping)
    if grouping != (1,) * head.beats_per_bar:
        source = {
            "text": "from the score's text",
            "beams": "from beaming",
            "metronome": "from the metronome",
        }.get(head.grouping_source, "auto: the metre's convention")
        print(
            f"  grouping: {format_grouping(grouping)} ({source}; "
            f"felt beats {', '.join(f'{beat:g}' for beat in starts)})"
        )


def head_cli(argv: Optional[Sequence[str]] = None) -> int:
    """The `head` command: arrange a MusicXML file as chord-melody.

    Returns a process exit code. It is a thin front end over `arrange_xml_head`
    and the whole-progression renderers, so it prints the same tabs any other
    caller gets.

    `argparse` is imported inside the function so the module stays importable -
    and cheap - for a caller who only wants `load_musicxml`.
    """
    import argparse

    from arranger.cli import (
        HEAD_HELP,
        ScoreMeta,
        add_common_arguments,
        render_and_write,
    )
    from arranger.slots import parse_bar_range

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
        # `parse_bar_range` allows an open-ended "12", which the section
        # resolves against its own end. A file has no section, so an
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
            fallback=args.fallback,
            section=section,
            options=_head_options(args),
        )
    except (ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))

    title = head.title or Path(args.file).name
    print(f"{title}{f' - {head.composer}' if head.composer else ''}")
    if head.part:
        print(f"  part: {head.part}")
    print(
        f"  {head.beats_per_bar}/{head.beat_type}, {_key_label(head)}, {len(head)} "
        f"melody note(s), bars {head.bars[0]}-{head.bars[1] - 1}; neck window: "
        f"frets {args.fret_min}-{args.fret_max}"
    )
    if head.markers and head.written_bars:
        _print_play_order(head)
    for note in notes:
        print(f"  note: {note}")
    _print_metre_notes(head, args)
    print(f"  request: {_request_line(head, args)}")
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
    # one.
    #
    # The **key** is passed on exactly the same terms, and for the same kind of
    # reason: it is not decoration either. A score in three flats exported in C
    # major writes a flat on every note of its own scale, because a reader with no
    # signature has nothing else to go on - so the key is a property of the score
    # the writers must be given, not a preference of the terminal header.
    return render_and_write(
        args,
        steps,
        meta=ScoreMeta(
            title=title,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
            fifths=head.key_fifths,
            mode=head.key_mode,
            markers=head.markers,
        ),
        notes=notes,
        written_bars=head.written_bars,
    )
