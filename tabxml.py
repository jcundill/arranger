"""MusicXML export for a whole arranged progression.

`tabstaff` renders an arrangement for a human to read - characters in a terminal, a
table in a browser. This module renders the same arrangement as **MusicXML**, the
interchange format every notation program reads, so a head can go on to Sibelius,
MuseScore or Final without being retyped.

What it writes is a real score rather than a note list:

- a **notation staff** of the music, in the treble clef a chord-melody part is
  written in, and
- the **chord symbols** on each chord change, on
- the **written rhythm**: each step is a note or chord of the length it occupies, an
  unchanged shape is written as one longer note rather than a re-strike, and an event
  that runs across a bar line is tied rather than stretched.

**There is no TAB staff here, deliberately.** This module used to write a six-line TAB
staff beside the notation one, and it is worth recording why it no longer does.
music21 cannot produce a TAB staff that a real reader renders correctly: it writes
neither the `<staff-lines>6</staff-lines>` a tab staff needs nor a fret and string for
each note *inside* a chord - music21 issue 1534 puts them all on the chord's first
note - so both had to be patched into the finished XML afterwards. The patched
document still did not display correctly in MuseScore 3, and a workaround that does
not work costs more than not shipping it.

Fretting belongs to the renderer whose format stores it natively. `tabgp` writes a
Guitar Pro 5 file, which is a *tab* format: a fret and a string per note survive the
round trip exactly, with no post-processing at all. So the two renderers divide the
work by what each format can actually do - notation here, tab there - while the
placement of every step is still shared, so a head lands on the same beats in both.

The placement is its own, in `_events`, and deliberately does **not** reuse
`tabstaff._staff_columns`. That column grid is lossy - two steps on one onset collapse
into one column - which is right for a fixed-width ASCII staff and wrong for a score,
where the second chord is a note the reader must see. The eighth-note skeleton puts
two steps on the last beat of most bars, so sharing the grid would drop a chord from
every bar of a head. What *is* shared is the semantics: absolute onsets with signed
bars, and collapse on unchanged sounding pitches. See `_events`.

`music21` is an **optional extra** (`pip install 'jazz-arranger[xml]'`) and is
imported inside the functions, not at the top of the module. The library must keep
working - and keep importing - with it absent, so nothing here may run at import
time.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence, Tuple
from xml.etree import ElementTree

from arranger import NO_CHORD, PITCH_CLASS_NAMES, ArrangementStep, GuitarFretboard

# The shortest event MusicXML can write, in quarter lengths: a sixteenth. See the
# duration floor in `_events`.
_MIN_EVENT_LENGTH = 0.25


# The MusicXML 3.1 `kind-value` enumeration, transcribed from the 3.1 schema.
#
# `kind` is a **closed** enumeration, so a value outside it is a fatal import error in
# any 3.1-era reader, not a warning. MusicXML 4.0 added values to it -
# `suspended-fourth-seventh` among them - and music21 writes 4.0: MuseScore 3 rejects
# the file outright with
#
#     Content of element kind does not match its type definition:
#     String content is not listed in the enumeration facet.
#
# and `converter.parse()` does not notice, because music21 both wrote the value and
# reads it back. 3.1 rather than 4.0 deliberately: it is a strict subset, so a
# 3.1-legal document is also 4.0-legal. That keeps the DOCTYPE honest while making
# the file importable by as many readers as possible.
_READABLE_KINDS = frozenset(
    {
        "major",
        "minor",
        "augmented",
        "diminished",
        "dominant",
        "major-seventh",
        "minor-seventh",
        "diminished-seventh",
        "augmented-seventh",
        "half-diminished",
        "major-minor",
        "major-sixth",
        "minor-sixth",
        "dominant-ninth",
        "major-ninth",
        "minor-ninth",
        "dominant-11th",
        "major-11th",
        "minor-11th",
        "dominant-13th",
        "major-13th",
        "minor-13th",
        "suspended-second",
        "suspended-fourth",
        "Neapolitan",
        "Italian",
        "French",
        "German",
        "pedal",
        "power",
        "Tristan",
        "other",
        "none",
    }
)

# The MusicXML 4.0 `kind` values that 3.1 lacks, and how each is spelled in 3.1:
# the base kind it becomes, plus the degrees to `add` to carry the part the new value
# folded into its name. MusicXML has no 3.1 kind for a sus chord with another interval
# in the name, but it does have the `<degree>` idiom for a harmony expressed as a base
# kind plus alterations - which is the case 3.1 was designed to cover, so a 7sus4 still
# arrives as a real chord symbol rather than as text.
_SUS_KINDS = {
    "suspended-fourth-seventh": ("suspended-fourth", (7,)),
    "suspended-second-seventh": ("suspended-second", (7,)),
    "suspended-fourth-ninth": ("suspended-fourth", (9,)),
    "suspended-second-ninth": ("suspended-second", (9,)),
}

def _music21() -> Any:
    """
    Imports music21 on demand, with a message that says how to get it.

    music21 is the library's only optional dependency and it is a large one, so it
    is not installed with the base package. Importing it lazily is what keeps
    `import arranger` (and therefore `import tabstaff` and `from arranger import *`)
    working on a machine that has never heard of it - the same lazy-import
    discipline `arranger.main()` uses for `wjazzd`, for the same reason.
    """
    try:
        import music21  # noqa: F401  (imported for the side effect of availability)
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            "MusicXML export needs music21, which is an optional extra. "
            "Install it with: pip install 'jazz-arranger[xml]'"
        ) from error
    return music21


def _pitch(midi: int) -> Tuple[str, int]:
    """
    Spells a MIDI number as (step, octave) for music21, flats preferred.

    Flats because that is the convention the rest of the library prints in
    (`PITCH_CLASS_NAMES`, `arranger._note_name`): a `Bb7` that came out of the
    Weimar database as a flat should not be re-spelled sharp on its way into a
    score a player reads.
    """
    return PITCH_CLASS_NAMES[midi % 12], midi // 12 - 1


def _sounding(step: ArrangementStep) -> List[int]:
    """
    The pitches a step actually sounds, as MIDI numbers, lowest string first.

    A repeated melody is a **single note**: the renderers show the soprano alone and
    leave the inner voices blank, because the held shape belongs to the chord the
    hold began on and the player is not re-fingering it. Honoured here rather than
    taken from the full voicing, so the score says the same thing the tab says.
    """
    voicing = step.voicing
    soprano = voicing.soprano_string()
    strings = [index for index, fret in enumerate(voicing.frets) if fret >= 0]
    if step.repeated and soprano >= 0:
        strings = [soprano]
    return [
        GuitarFretboard.fret_to_midi(index, voicing.frets[index]) for index in strings
    ]



def _events(
    steps: List[ArrangementStep], beats_per_bar: int, rhythm: bool
) -> Tuple[List[Tuple[Optional[ArrangementStep], bool, float]], float]:
    """
    The arrangement as (step, strikes, quarter_length) events, and the pickup.

    A **held** step is not emitted: its length is folded into the event before it,
    which is what a tie means. A step is a hold when it sounds the same pitches as
    the one before it and is not a re-articulated melody - the same rule, on the same
    comparison of sounding pitches, that `tabstaff._staff_columns` applies.

    The pickup is how quarter lengths long the **first** written bar is, which is the
    bar line before the first note rather than the one after it. A head that starts on
    a downbeat has a pickup of 0 and every bar is a full bar; one that starts on the
    third beat has a pickup of two beats, and the first bar is written short. It
    matters because the onsets are counted from zero at the first note, so the bar
    lines are not at multiples of the bar length - the first note of a Blue Train
    head sits at onset 4.0, which is bar 1's downbeat, and a grid anchored at zero
    would put a bar line in the middle of its first bar. The offset of the first note
    within its own bar is what recovers the real metre.

    Note that the steps are placed here rather than taken from
    `tabstaff._staff_columns`, although the two agree on everything a *staff* can
    show. The column grid is deliberately lossy: two steps sharing an onset collapse
    into one column, "the first step in a column owns that column", which is right
    for a fixed-width ASCII staff and wrong for a score, where the second chord is a
    note the reader must see. The eighth-note skeleton puts two steps on the last beat
    of most bars, so sharing the grid would drop a chord from every bar of a head.
    What is shared is the *semantics* - absolute onsets with signed bars, and
    collapse on unchanged sounding pitches - and both are implemented here.
    """
    beat_in_quarters = 4.0 / beats_per_bar
    timed = bool(rhythm) and bool(steps) and all(step.has_timing for step in steps)

    if timed:
        # Absolute beat, exactly as NoteEvent.beat_position computes it, so a pickup
        # in a negative bar sorts before bar 0 with no special case.
        placed = [
            (step.bar * beats_per_bar + (step.beat - 1.0), step)  # type: ignore[operator]
            for step in steps
        ]
    else:
        # No timing, or `rhythm=False`: one chord per beat, reproducing the uniform
        # grid the other two renderers fall back to.
        placed = [(float(index), step) for index, step in enumerate(steps)]
    placed.sort(key=lambda item: item[0])

    # How far the first note sits past the bar line before it. Zero when the head
    # starts on a downbeat, which is the usual case; the first written bar is then a
    # full bar rather than a pickup.
    pickup = (placed[0][0] % beats_per_bar) * beat_in_quarters

    events: List[Tuple[Optional[ArrangementStep], bool, float]] = []
    index = 0
    while index < len(placed):
        onset = placed[index][0]
        # Every step sharing this onset, kept: a score has to show them all.
        group: List[ArrangementStep] = []
        while index < len(placed) and abs(placed[index][0] - onset) < 1e-9:
            group.append(placed[index][1])
            index += 1
        # The group lasts until the next distinct onset, so the written rhythm
        # survives: a triplet transcription exports as triplets, without this module
        # ever having to know what a triplet is.
        if index < len(placed):
            span = (placed[index][0] - onset) * beat_in_quarters
        else:
            # The last group has no next onset to measure against, so it runs to the
            # end of its own bar. The transcribed `duration` is not used for the span:
            # it is the length of the *last melody note*, a fraction of a whole note
            # that MusicXML cannot always express (music21 raises
            # MusicXMLExportException), and losing the tail of a head to that would be
            # a poor trade. `_build_part` pads the closing bar.
            bar_end = (int(onset // beats_per_bar) + 1) * beats_per_bar
            span = max(bar_end - onset, 1.0) * beat_in_quarters

        # Several steps can share one onset - the eighth-note skeleton puts two on the
        # last beat of most bars - and they divide the time up to the next onset
        # equally. The transcribed `duration` is deliberately not used as a weight
        # here: it is the length of the *melody note* that step came from, which
        # extends past this onset, and the corpus's own values are arbitrary fractions
        # of a whole note. Scaling by them produces note values MusicXML cannot
        # express, and music21 refuses the whole export rather than rounding one. Two
        # eighths on the last beat of a bar are two eighths, which is what dividing the
        # beat gives.
        lengths = [span / len(group)] * len(group)

        for step, length in zip(group, lengths):
            # MusicXML cannot write a duration shorter than a sixteenth, and music21
            # aborts the whole export rather than rounding one. A floor of a sixteenth
            # is therefore a floor on the *export*, not on the music: no step this
            # library generates is shorter than an eighth, so nothing real is affected.
            length = max(length, _MIN_EVENT_LENGTH)
            if _is_hold(step, events):
                # Held, not struck: extend what is already ringing rather than
                # writing a second copy of the same shape.
                held_step, held_strikes, held_length = events[-1]
                events[-1] = (held_step, held_strikes, held_length + length)
                continue
            events.append((step, True, length))
    return events, pickup


def _is_hold(
    step: ArrangementStep,
    events: Sequence[Tuple[Optional[ArrangementStep], bool, float]],
) -> bool:
    """
    True when this step is the previous one still ringing rather than a new attack.

    The comparison is of sounding pitches, not of written note names, because either
    step may itself have been transposed down an octave by the `HIGH_FRET_LIMIT`
    rule. A repeated melody is excluded: its note is genuinely re-articulated, which
    is why `ArrangementStep.repeated` overrides the hold - see
    `tabstaff._staff_columns` for the same rule in the same words.
    """
    if not events or step.repeated:
        return False
    previous = events[-1][0]
    if previous is None:
        return False
    return sorted(previous.voicing.midi_notes()) == sorted(step.voicing.midi_notes())


def _build_note(step: ArrangementStep, length: float) -> Any:
    """
    One step as a music21 `Chord`, a single `Note`, or a `Rest`.

    A one-pitch step becomes a `Note` rather than a one-note `Chord`, so a repeated
    melody exports as the single note it is played as, and a melody-only (no chord)
    step does the same. Anything else is a `Chord` carrying one note per sounding
    string, written as **pitches only**: the staff is notation, and a `<fret>` or a
    `<string>` on a notation staff is information no reader can use. Fretting is
    written by `tabgp` - see the module docstring.
    """
    from music21 import chord, note

    sounding = _sounding(step)
    if not sounding:
        return note.Rest(quarterLength=length)

    pitches = []
    for midi in sounding:
        step_name, octave = _pitch(midi)
        pitches.append(f"{step_name}{octave}")
    if len(pitches) == 1:
        return note.Note(pitches[0], quarterLength=length)

    built: Any = chord.Chord(pitches, quarterLength=length)
    # A guitar shape is played with the fingers on the frets it is written on, so
    # the stems point down however high the top note is - the top note of a drop-2
    # voicing is often the *lowest* sounding voice inverted on the high string.
    built.stemDirection = "down"
    return built


def _build_part(
    events: Sequence[Tuple[Optional[ArrangementStep], bool, float]],
    title: str,
    beats_per_bar: int,
    pickup: float = 0.0,
    show_chords: bool = True,
) -> Any:
    """
    The staff of the score: a `Part` of measures, in reading order.

    A new `Measure` is started at every bar line, because music21 exports the
    measures a stream actually has: given one measure holding a whole head, it
    writes a whole head as one overfull measure. The first measure may be short -
    a head selected from a pickup bar starts part-way through a bar - so it is
    marked as an anacrusis, and the last one is padded with a rest, rather than
    either being quietly stretched to fill its bar.
    """
    from music21 import clef, meter, stream

    bar_length = float(beats_per_bar)
    part = stream.Part()
    part.partName = title
    part.append(clef.TrebleClef())

    # Offsets run from zero, so a head picked up part-way through a bar simply starts
    # the first written bar as a short one - which is what it is.
    number = 1
    in_force: Optional[str] = None
    offset = 0.0
    # `state` tracks where the writing has got to: the measure being filled, where
    # that measure begins on the score's timeline (offsets inside a measure count
    # from the bar line, so the second bar's first note is at 0.0 and not 4.0), its
    # number, and how long that measure may be - the first is short when there is a
    # pickup, the rest are full bars.
    state: dict = {
        "measure": None, "start": 0.0, "number": number,
        "length": bar_length - pickup,
    }
    # The time signature is written once, in the first measure. MusicXML says a
    # signature holds until it changes, so repeating it in every bar is legal but
    # reads as a new one at each: MuseScore 3 draws a 4/4 over every bar of the head.
    def new_measure() -> Any:
        """Appends an empty, numbered, timed measure and returns it."""
        built = stream.Measure(number=state["number"])
        # Every measure carries the time signature, not just the first. music21 resolves
        # a measure's bar length from its own context when it pads and ties the bar,
        # and with the signature only on the first measure the later ones have none, so
        # the export dies inside makeRests with 'NoneType' has no attribute
        # 'barDuration'. Repeating the element in each measure is valid MusicXML.
        built.timeSignature = meter.TimeSignature(f"{beats_per_bar}/4")
        part.append(built)
        return built

    state["measure"] = new_measure()

    def write_symbol(name: str) -> None:
        # On the change, and *at* the change: only on the change, the way a lead sheet
        # spells a chord held over several slots, and at its own offset, because a
        # symbol pinned to the bar line names the wrong chord for every chord after
        # the first.
        state["measure"].insert(offset - state["start"], _chord_symbol(name))

    def write_event(step: Optional[ArrangementStep], length: float) -> None:
        """
        Writes one event, cutting it at a bar line and tying the halves.

        A note cannot cross a bar line in MusicXML, and a measure holding more than
        its time signature is not a measure. So an event that runs across one becomes
        two notes tied together - which is what an engraver does too, and it keeps
        the written rhythm: a transcription whose phrasing disagrees with the metre
        comes out as the player heard it rather than silently straightened.
        """
        nonlocal offset
        from music21 import tie as tie_module

        # Cut the event into the pieces each measure can hold, opening a new measure
        # wherever one fills up. The offsets are recorded as they are decided, because
        # a piece's offset is measured from the bar line it lands in.
        pieces: List[Tuple[Any, float, float]] = []
        remaining = length
        while remaining > 1e-9:
            room = state["length"] - (offset - state["start"])
            if room <= 1e-9:
                # The measure is already full and the event continues past it. Opening
                # the next bar *before* measuring the piece matters: a zero-length
                # piece would be written as a note of default length, quietly adding a
                # beat to the bar it was meant to end at the end of.
                state["number"] += 1
                state["measure"] = new_measure()
                state["start"] = offset
                state["length"] = bar_length
                continue
            piece = min(remaining, room)
            pieces.append((state["measure"], offset - state["start"], piece))
            offset += piece
            remaining -= piece

        for index, (where, at, piece) in enumerate(pieces):
            built = _rest(piece) if step is None else _build_note(step, piece)
            if len(pieces) > 1:
                built.tie = tie_module.Tie(
                    "start" if index == 0
                    else "stop" if index == len(pieces) - 1
                    else "continue"
                )
            where.insert(at, built)

    for step, _, length in events:
        if step is not None and show_chords and step.chord != in_force:
            in_force = step.chord
            if in_force and in_force != NO_CHORD:
                write_symbol(in_force)
        write_event(step, length)

    measures = list(part.getElementsByClass(stream.Measure))
    if measures:
        # A short first measure is a pickup and a short last one is where the head
        # stops; both are written as they are, which is what `<implicit>` and the
        # closing rest are for.
        first, last = measures[0], measures[-1]
        # The test is "is there a pickup", not "is this measure short". They are not
        # the same thing: a head that starts on the third beat fills its two-beat
        # pickup *exactly*, so the measure is complete and still an anacrusis. Testing
        # the length alone would write it as a normal bar, and a reader would expect a
        # downbeat that is not there.
        #
        # Two separate music21 levers, because they do different jobs:
        # `padAsAnacrusis` says the bar is incomplete and must be padded when the
        # stream is re-barred, while `showNumber` is what music21 actually writes into
        # `<measure implicit="...">` - `padAsAnacrusis` on its own changes nothing in
        # the output. It is a method rather than a flag, so assigning to it would
        # silently do nothing at all.
        if pickup > 1e-9:
            first.padAsAnacrusis(True)
            first.showNumber = stream.enums.ShowNumber.NEVER
        last.padAsAnacrusis(False)
        # `last` and `first` can be the same measure - an arrangement that fits in one
        # bar - and the pickup flag must not then be overwritten by the closing one.
        # A lone pickup bar stays implicit: it is still a pickup.
        if last is not first:
            last.showNumber = stream.enums.ShowNumber.ALWAYS
        # The closing bar is a full one, unless the whole arrangement is the pickup.
        closing = bar_length if len(measures) > 1 else bar_length - pickup
        shortfall = closing - last.duration.quarterLength
        if shortfall > 1e-9:
            last.insert(last.duration.quarterLength, _rest(shortfall))
    return part


def _rest(length: float) -> Any:
    """A rest of `length` quarter lengths, for a gap in the arrangement."""
    from music21 import note

    return note.Rest(quarterLength=length)


def _drop_empty_inversions(root: ElementTree.Element) -> None:
    """
    Removes the `<inversion>-1</inversion>` that a text-only chord symbol carries.

    music21 writes an inversion for a `ChordSymbol` that has no pitches, and -1 is
    its way of saying "there is none". MusicXML makes `<inversion>` optional, so the
    element is dropped rather than left as a number no reader can act on.
    """
    for inversion in root.iter("inversion"):
        if inversion.text is None or inversion.text.strip().startswith("-"):
            for harmony_node in root.iter("harmony"):
                if inversion in list(harmony_node):
                    harmony_node.remove(inversion)
                    break


# The XML declaration and the MusicXML DTD that music21 writes ahead of the root
# element. `ElementTree` keeps neither when it serialises, and the DOCTYPE is what
# tells a reader which MusicXML version the file claims to be, so both are carried
# over from the document music21 produced rather than re-invented here.
_DOCTYPE_PATTERN = re.compile(r"<!DOCTYPE[^>]*>")


def _document_prologue(document: str) -> str:
    """
    The XML declaration and DOCTYPE music21 wrote, or an empty string without them.

    A MusicXML file is written before the root element rather than inside it, so
    `ElementTree` cannot carry these through a parse/serialise round trip: the DOCTYPE
    is the declaration of the MusicXML 4.0 DTD, which is how a reader knows which
    version the file is claiming. It is captured from the text music21 emitted, so a
    future music21 that declares a different version is carried through rather than
    overridden.
    """
    prologue = '<?xml version="1.0" encoding="UTF-8"?>'
    match = _DOCTYPE_PATTERN.search(document)
    if match:
        prologue += "\n" + match.group(0)
    return prologue + "\n"


def _chord_symbol(name: str) -> Any:
    """
    A chord symbol for the score, or a text-only one when music21 cannot read the name.

    music21 knows most of the qualities this library voices, but not all of them:
    `mMaj7`, `maj9` and `7alt` are among the ones it rejects, and the Weimar
    Database's own notation produces a few more. A symbol that cannot be parsed is
    not a reason to lose the chord, so it is written as `<kind text="...">other</kind>`
    with the root still parsed out by the library - which is how MusicXML spells a
    chord symbol whose type the writer does not recognise. The chord still reads
    correctly; it just is not classified.

    The exception is deliberately broad: this is a formatting fallback for names
    from an external database, and a new music21 release should degrade the symbol
    rather than fail the export.
    """
    from music21 import harmony

    try:
        symbol = harmony.ChordSymbol(name)
    except Exception:
        from arranger import ChordParser

        root, _ = ChordParser.parse_chord_name(name)
        symbol = harmony.ChordSymbol()
        if root:
            symbol.root(root)
        symbol.chordKind = "other"
        symbol.chordKindStr = name
    symbol.writeAsChord = False
    return symbol


def _unique_instrument_ids(root: ElementTree.Element) -> None:
    """
    Gives every `<score-instrument>` in the part list an id of its own.

    The instrument ids live in the `<part-list>`, not in the parts, and music21 writes
    the *same* one into every `<score-part>` when the parts share a single
    `instrument.Guitar()`. The score has one part now, so this is a no-op on the
    document this renderer writes; it is kept because the ids are minted by music21
    rather than by this renderer, and MusicXML requires them to be unique within the
    part list regardless. MuseScore refuses to open the file outright when they are
    not:

        Fatal error: ID value 'I56a9...' is not unique.

    Each `<score-instrument>` is paired with a `<midi-instrument>` of the same id, and
    that pairing is what identifies "this part plays this instrument", so the two are
    renumbered together and a part's `<score-instrument>` and `<midi-instrument>` keep
    matching. Nothing else refers to these ids: an `<midi-device>` would, and a
    part-list written this way has none.
    """
    for index, score_part in enumerate(root.findall("part-list/score-part"), start=1):
        renumbered = f"P{index}-I"
        for instrument in score_part.findall("score-instrument"):
            instrument.set("id", renumbered)
        for instrument in score_part.findall("midi-instrument"):
            instrument.set("id", renumbered)


def _add_degrees(harmony: ElementTree.Element, values: Sequence[int]) -> None:
    """
    Appends one `add` `<degree>` per value to a `<harmony>`, in schema order.

    A `<harmony>` is a sequence - root, kind, inversion, bass, then the degrees - so
    these are appended rather than inserted, which puts them after everything music21
    already wrote and in the right order among the degrees themselves.
    """
    for value in values:
        degree = ElementTree.SubElement(harmony, "degree")
        for tag, text in (
            ("degree-value", str(value)),
            ("degree-alter", "0"),
            ("degree-type", "add"),
        ):
            node = ElementTree.SubElement(degree, tag)
            node.text = text


def _downgrade_kinds(root: ElementTree.Element) -> None:
    """
    Rewrites any `<kind>` value MusicXML 3.1 does not have, so a 3.1-era reader can
    open the file.

    music21 writes MusicXML 4.0, and 4.0 extended the closed `kind-value` enumeration -
    `suspended-fourth-seventh` among the additions. A reader that validates against 3.1
    rejects the whole document, so the cost of one chord is the whole file. Two
    rewrites, in this order of preference:

    1. **The spec's own spelling.** `suspended-fourth-seventh` becomes
       `suspended-fourth` plus a `<degree>` adding the 7th. MusicXML 3.1 has no kind
       for the combination, but it does have the `add`-degree idiom for a harmony
       expressed as a base kind plus alterations, so the chord still arrives as a
       classified symbol rather than as loose text. The other 4.0-only sus kinds get
       the same treatment, with the degree each one folded in.
    2. **`other` with the name text.** Anything else unknown becomes
       `<kind text="...">other</kind>` - the same fallback `_chord_symbol` already uses
       for a name music21 cannot parse. Guaranteed to import; not classified.

    The `<root>` is untouched: a sus chord's root is not what is in question. This is a
    no-op on a document that only uses 3.1 kinds, which is the overwhelmingly common
    case, and it runs last so that it sees the finished document rather than an
    intermediate one.
    """
    for harmony in root.iter("harmony"):
        kind = harmony.find("kind")
        if kind is None:
            continue
        text = (kind.text or "").strip()
        if text in _READABLE_KINDS:
            continue
        downgrade = _SUS_KINDS.get(text)
        if downgrade is not None:
            base, degrees = downgrade
            kind.text = base
            _add_degrees(harmony, degrees)
        else:
            # Unknown to 3.1. `text` is the attribute MusicXML 3.1 defines on `kind`
            # for a chord it has no type for, which is precisely this case.
            kind.set("text", text)
            kind.text = "other"


def _substitute_steps(steps: List[ArrangementStep]) -> List[ArrangementStep]:
    """
    The harmony a step is *sounding*, as a step carrying that chord name.

    The chord name to print for a step, which is the one actually sounding.

    A step harmonised under a substitution or a tension carries it in
    `harmonized_as`, and the written name is not what the notes are. Printing the
    written chord over such a step would put a symbol on the score for pitches that
    are not in it - the same thing `_step_annotation` exists to prevent in the tab.
    A step with no substitution is returned untouched, so the two renderers spell
    an ordinary chord identically.
    """
    substituted: List[ArrangementStep] = []
    for step in steps:
        harmony_name = step.harmonized_as
        if harmony_name and harmony_name != step.chord:
            step = ArrangementStep(**{**step.__dict__, "chord": harmony_name})
        substituted.append(step)
    return substituted


def format_musicxml(
    steps: List[ArrangementStep],
    title: str = "Chord-melody arrangement",
    subtitle: str = "",
    composer: str = "",
    beats_per_bar: int = 4,
    rhythm: bool = True,
    collapse: bool = True,
    show_chords: bool = True,
) -> str:
    """
    Renders a whole progression as a MusicXML (score-partwise) document.

    The document is a **notation staff** in the treble clef a chord-melody part is
    written in, with the **chord symbols** on each change and the **written rhythm**:
    a shape that is held rather than restruck is one longer note, and a step whose
    melody repeats under an unchanged harmony is a single struck note.

    There is no TAB staff. music21 cannot write one that a notation program renders
    correctly, so the fretting is written by `tabgp` as a Guitar Pro 5 file instead -
    see the module docstring for why the two renderers divide the work that way.

    Args:
        steps: arranged steps, typically from `arrange_progression()`.
        title: the score title.
        subtitle: an optional line under it, e.g. the performer.
        composer: an optional composer credit.
        beats_per_bar: beats in a bar, used for the time signature and the bars.
        rhythm: space the steps on their real beats. Falls back to a uniform
            one-chord-per-beat grid when the steps carry no timing, exactly as
            `format_tab_staff` does, so a hand-written progression still exports.
        collapse: write a held shape as one longer note instead of restriking it.
        show_chords: write the chord symbols.

    Returns:
        A complete MusicXML document as a string, or "" for no steps. Pure: nothing
        is printed and no file is written, so the caller stays in control. Needs the
        optional `music21` extra; see `_music21` for the error raised without it.
    """
    _music21()
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if not steps:
        return ""

    from music21 import instrument, metadata, musicxml, stream

    # The sounding harmony is settled here rather than inside the note builder,
    # because a substitution is a property of the *step* - it changes the chord name
    # printed above the shape, not the pitches of the shape.
    events, pickup = _events(_substitute_steps(steps), beats_per_bar, rhythm and collapse)
    if not any(step is not None for step, _, _ in events):
        return ""

    score = stream.Score()
    score.insert(0, instrument.Guitar())
    score.insert(0, metadata.Metadata(title=title, composer=composer or None))
    if subtitle:
        score.metadata.movementName = subtitle

    score.insert(
        0,
        _build_part(
            events, title, beats_per_bar, pickup=pickup, show_chords=show_chords
        ),
    )

    document = musicxml.m21ToXml.GeneralObjectExporter().parse(score).decode("utf-8")

    # What music21's own output still needs, applied to the parsed tree rather than
    # by editing the text. None of it is about tab any more.
    root = ElementTree.fromstring(document)
    _unique_instrument_ids(root)
    _drop_empty_inversions(root)
    # A compatibility filter, so it runs last: it sees the finished document, and
    # nothing below it can put a 4.0-only value back.
    _downgrade_kinds(root)
    return _document_prologue(document) + ElementTree.tostring(root, encoding="unicode")


def write_musicxml(steps: List[ArrangementStep], path: str, **kwargs: Any) -> str:
    """
    Renders `format_musicxml` to a file and returns the path written.

    The only function in this module that touches the filesystem, which is what lets
    every renderer stay pure. Writing is separated from rendering so a caller who
    only wants the string never creates a file by accident.
    """
    document = format_musicxml(steps, **kwargs)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return str(path)


# Re-exported from `tabstaff` (and through it from `arranger`) for the same reason
# that module's renderers are: `tabxml` imports both, so a top-level import in
# either direction would be a cycle. The names are resolved on first access.
__all__ = ["format_musicxml", "write_musicxml"]
