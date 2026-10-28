from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from arranger.grid import RHYTHM_MELODY
from arranger.grouping import GROUPING_AUTO, format_grouping, group_starts, resolve_grouping
from arranger.options import ArrangeOptions, Request, format_request, resolve_request
from headxml_model import Head
from headxml_read import load_musicxml
from headxml_timeline import arrange_xml_head


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
    #
    # `first_bar_implicit` rides along on the same terms: the importer read the file,
    # so it knows whether bar 1 is whole, and a writer re-deriving that from the onsets
    # draws a pickup bar wherever the tune enters late.
    return render_and_write(
        args,
        steps,
        meta=ScoreMeta(
            title=title,
            beats_per_bar=head.beats_per_bar,
            beat_type=head.beat_type,
            fifths=head.key_fifths,
            mode=head.key_mode,
            markers=head.markers, first_bar_implicit=head.first_bar_implicit,
        ),
        notes=notes,
        written_bars=head.written_bars,
    )
