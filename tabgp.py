"""Guitar Pro 5 export for a whole arranged progression.

This is a **third renderer family**, beside the ASCII/HTML staff in `tabstaff` and
the MusicXML score in `tabxml`. It is also where the **fingering** now lives, because
GP5 is a *tab* format: it stores a fret number and a string for every note natively,
so a chord shape survives the round trip exactly. `tabxml` used to write a TAB staff
alongside its notation one, but `music21` cannot write a TAB staff a notation program
renders correctly - it emits neither the six `<staff-lines>` nor a fret and string per
note, and the patched-up document still displayed incorrectly in MuseScore 3. So the
two renderers divide the work by what each format can do: **notation in MusicXML,
tab here**, with `_events` and `_substitute_steps` shared so a head lands on the same
beats in both files.

What it writes is one guitar track of shapes, each carrying the chord name it is
sounding, on the written rhythm, with a held shape written as one longer note
rather than a re-strike.

**It is not a replacement for MusicXML.** GP5 opens in Guitar Pro and nowhere else;
it has no notation staff, and it is a closed format. MusicXML remains the way into
Sibelius, MuseScore and Final. What the two share is the *placement*: both call
`tabxml._events`, so a head lands on the same beats in both files and the two
renderings cannot drift apart. Where they genuinely differ is bar lines - see
`_measures`.

Five things about the format, each of which cost a failed round trip to find, and
each of which is a silent corruption rather than an exception. They are recorded
here because none of them is in the library's documentation and all of them look
innocent:

- **`Song()` already contains one `MeasureHeader` and one `Track`.** Appending
  another produces a file that reads back as an extra track and fails partway
  through. Use `song.measureHeaders[0]` and `song.tracks[0]`.
- **`Measure.maxVoices` is 2, and the writer emits every voice on a measure.** A
  measure built with one voice desyncs the byte stream, so the reader fails later
  with an unrelated-looking error (`count must be less than or equal to 255`).
  Every measure here gets a second, empty `Voice`.
- **`Beat.status` defaults to `BeatStatus.empty`, which occupies zero duration.**
  A beat that is meant to sound must say `BeatStatus.normal`.
- **Strings are numbered 1-6 with 1 = high E.** This library indexes 0 = low E, so
  the conversion is `6 - index`, the same flip `tabxml` does for a MusicXML staff.
- **`Chord` is a chord *diagram*, not a shape.** It carries a name, a root and a
  fret vector for the little box drawn above the staff. A played shape is several
  `Note` objects on one `Beat`, `Note.value` being the fret. Using `Chord` for the
  shape is the obvious mistake and writes a box rather than a chord.

`PyGuitarPro` is an **optional extra** (`pip install 'jazz-arranger[gp]'`) and is
imported inside the functions, never at module level, so the library keeps working
- and keeps importing - with it absent. See `_guitarpro`.
"""

from __future__ import annotations

import io
from typing import Any, List, Optional, Tuple

from arranger import ArrangementStep
from tabxml import _events, _substitute_steps

# The GP file version written. (5, 1, 0) is the 5.1 format, which Guitar Pro 5 and
# every later release read. PyGuitarPro writes GP3/GP4/GP5/TGP from the same model,
# so this is the top of the available range rather than a choice between formats.
GP_VERSION = (5, 1, 0)

# The signature guitarpro writes, and what a valid GP5 file begins with.
GP_SIGNATURE = b"\x18FICHIER GUITAR PRO v5.10\x00"

# guitarpro numbers the strings 1..6 with 1 = high E; this library indexes 0 = low
# E, so the conversion is `6 - index`.


def _guitarpro() -> Any:
    """
    Imports PyGuitarPro on demand, with a message that says how to get it.

    The same lazy-import discipline as `tabxml._music21`, and for the same reason:
    a plain `pip install jazz-arranger` must keep working on a machine that has
    never heard of the renderer. Raising `ImportError` with the install command
    rather than letting the original propagate is what lets `corpus_cli` report a
    missing extra as a usage message instead of a traceback.
    """
    try:
        import guitarpro  # noqa: F401  (imported for the side effect of availability)
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            "Guitar Pro export needs PyGuitarPro, which is an optional extra. "
            "Install it with: pip install 'jazz-arranger[gp]'"
        ) from error
    return guitarpro


def _duration_split(
    length: float,
) -> List[Tuple[int, Optional[Tuple[int, int]]]]:
    """
    A length in quarter notes as the (guitarpro `Duration`, `Tuplet`) pairs to write.

    4 is a quarter, 8 an eighth, 16 a sixteenth - the number is the
    *denominator*, so a longer note is a smaller number.

    **The format has no dotted note, and a duration is a power of two.** `Duration`
    values are written as `value.bit_length() - 3` and read back as `1 << (n + 2)`,
    so a length that is not a power of two has to be *split*: a dotted half (3
    quarters) becomes a half plus a quarter. Rounding it to the nearest legal
    value instead gave a whole note - a quarter too long - and that is what made
    TuxGuitar report `voice 1 is too long`, the bar summing to more than its
    signature.

    **A triplet is a tuplet, not a duration.** A triplet eighth is `Duration(8)`
    with a `Tuplet(3, 2)`, and writing a bare `Duration(12)` is silently wrong:
    `12.bit_length() - 3` is 1, which the reader turns back into an *eighth*. The
    file then holds three triplets and a quarter where the bar is meant to hold
    three triplets and a quarter of real time, so it is a quarter too long. Nothing
    errors - the value simply comes back different. The corpus's triplet
    transcriptions need this, and `tabxml` handles triplets by the same
    onset-division rule rather than by scaling a note value.

    Returns (Duration value, Tuplet) pairs, longest first. A `Tuplet()` is a plain
    note; the import is deferred to `_build_song`, which is where guitarpro exists.
    """
    if length <= 1e-9:
        # Nothing to write. A beat of no length occupies no time, so writing one
        # would inflate the bar it sits in rather than filling it.
        return []

    # Every length guitarpro can hold, as (quarter-length, Duration value, Tuplet).
    # The plain values come first, then the triplets, so a triplet is only reached
    # once no plain note fits - which is what keeps a dotted half a half plus a
    # quarter rather than three triplet eighths. Built by appending rather than by
    # adding two comprehensions, because `list` is invariant and the two would
    # otherwise infer different literal types for the same list.
    candidates: List[Tuple[float, int, Optional[Tuple[int, int]]]] = []
    for value in _DURATION_VALUES:
        candidates.append((4.0 / value, value, None))
    for value in _DURATION_VALUES:
        candidates.append((4.0 / value * 2.0 / 3.0, value, (3, 2)))
    # An exact fit is the common case and the only one that needs no thought.
    for exact, value, tuplet in candidates:
        if abs(exact - length) < 1e-6:
            return [(value, tuplet)]

    # Otherwise greedily take the longest parts that fit, longest note first. This
    # is a 3:2 eighth or a dotted half being *decomposed*, never rounded up: a part
    # is only taken when it fits, so the parts can only ever be short of the whole.
    parts: List[Tuple[int, Optional[Tuple[int, int]]]] = []
    remaining = length
    for exact, value, tuplet in candidates:
        while remaining >= exact - 1e-6:
            parts.append((value, tuplet))
            remaining -= exact
    if not parts:
        # Shorter than a triplet sixteenth; the shortest legal note is the closest
        # thing the format can say, and it is short rather than long - a bar may
        # then end slightly early, which a reader tolerates.
        return [(_MIN_DURATION, None)]
    if remaining > 1e-6:
        # A sliver is left over. Put it on the last part by stepping that part up to
        # the next longer note, so the written total is never *shorter* than the
        # length asked for - a bar that came out short would silently lose music.
        value, tuplet = parts[-1]
        longer = next(
            (v for e, v, t in reversed(candidates)
             if v < value and abs(e - (4.0 / value + remaining)) < 1e-6),
            None,
        )
        if longer is not None:
            parts[-1] = (longer, tuplet)
        else:
            # No single note covers the remainder; append the shortest legal one.
            parts.append((_MIN_DURATION, None))
    return parts


def _duration_value(length: float) -> int:
    """
    The single guitarpro `Duration` nearest a length, or the shortest legal one.

    Kept for a caller that genuinely wants one value - a test, or a beat the format
    can hold exactly. **Do not use it to lay out a bar**: it rounds, and rounding a
    dotted half to a whole note is what made a bar longer than its signature. Use
    `_duration_split`, which cannot.
    """
    if length <= 0:
        return _MIN_DURATION
    value = int(round(4.0 / length))
    return max(_MAX_DURATION, min(value, _MIN_DURATION))


def _sounding_frets(step: ArrangementStep) -> List[Tuple[int, int]]:
    """
    The frets a step actually plays, as (string_index, fret), low string first.

    A repeated melody is a **single note**, matching `tabxml._sounding` and the two
    other renderers: the held shape belongs to the chord the hold began on and the
    player is not re-fingering it. A muted string is an *absence* of a note, which
    is what leaves the other strings blank in the other renderers too.
    """
    voicing = step.voicing
    if step.repeated:
        soprano = voicing.soprano_string()
        return [(soprano, voicing.frets[soprano])] if soprano >= 0 else []
    return [(index, fret) for index, fret in enumerate(voicing.frets) if fret >= 0]


def _measures(
    events: List[Tuple[Optional[ArrangementStep], bool, float]],
    pickup: float,
    beats_per_bar: int,
) -> List[List[Tuple[Optional[ArrangementStep], float]]]:
    """
    The events as a list of measures, each a list of (step, length) beats.

    **This is where GP5 and MusicXML genuinely differ**, and the difference is
    forced by the format rather than chosen. MusicXML has an anacrusis: a measure
    may simply be short, and `tabxml._build_part` writes it that way. A GP5 measure
    is a fixed-length container and the file has no way to say "this first bar is
    only two beats long", so a head that starts on the third beat is written as a
    **full first measure with the leading beats left empty** and the music begins
    on its downbeat. That moves every onset later by the length of the pickup
    rather than reshaping the metre, which is the lesser of the two distortions:
    the notes and their order are untouched, only their position within the bar.

    An event that runs across a bar line is **split**, not stretched and not
    dropped: the two halves are written in consecutive measures, which is what
    `_build_part` does with a tie in the XML and gives the same music. A GP tie
    across a bar line is a slur the player has to interpret rather than a hold, so
    the halves are written out instead.
    """
    bar_length = float(beats_per_bar)
    # A GP5 measure is a fixed-length container, so a head that starts part-way
    # into a bar gets a full first measure with its leading beats left empty and
    # the music begins on the following downbeat. See the docstring.
    measures: List[List[Tuple[Optional[ArrangementStep], float]]] = []
    if pickup > 0:
        measures.append([])

    # A running cursor in quarter notes from the first note. A measure is opened
    # whenever the cursor *reaches* a bar line, not only when an event crosses
    # one: the eighth-note skeleton puts beats that land exactly on the boundary,
    # and testing only for a crossing leaves them all in one measure.
    cursor = 0.0
    for step, _strikes, length in events:
        remaining = length
        while remaining > 1e-9:
            position = cursor % bar_length
            # On a bar line, and the current measure already has something in it:
            # this beat belongs to the next bar.
            if position <= 1e-9 and measures and measures[-1]:
                measures.append([])
                continue
            if not measures:
                measures.append([])
            room = bar_length - position
            chunk = min(room, remaining)
            # A chunk of no length is dropped, not written. It happens when two
            # steps share an onset exactly at a bar line: the first fills the bar
            # and leaves the second nothing, and a beat of no length occupies no
            # time at all, so writing it would inflate the bar rather than fill it.
            if chunk > 1e-9:
                measures[-1].append((step, chunk))
            cursor += chunk
            remaining -= chunk
            # Exactly filling a bar ends it, so the next beat opens a new measure.
            if abs(position + chunk - bar_length) < 1e-9:
                measures.append([])
    # Drop empty measures. Two things create one: a beat whose length split to
    # nothing, and a beat that lands exactly on a bar line with a measure already
    # open. A measure with no beats is worse than either error - a reader shows it
    # as a bar of rests, and it reads as a hole in the song - so it goes rather
    # than being padded. This also removes the trailing measure left when a bar is
    # filled exactly, which is why there is no separate trim afterwards.
    #
    # The leading measure is a pickup and is empty by construction, so it is
    # dropped here too and the music simply starts on the first written downbeat.
    # That is the same outcome `_measures` documents for a head that starts on an
    # upbeat - the onsets are already counted from the first note, so nothing else
    # has to move.
    return [beats for beats in measures if beats]


def _build_song(
    gp: Any,
    measures: List[List[Tuple[Optional[ArrangementStep], float]]],
    title: str,
    subtitle: str,
    composer: str,
    tempo: int,
    beats_per_bar: int,
) -> Any:
    """
    The measures as a guitarpro `Song`, ready to write.

    Reuses the `Song`'s own default header and track rather than appending to
    them, and gives every measure its second empty voice - see the module
    docstring, both of which are silent corruptions rather than errors.
    """
    song = gp.Song(
        versionTuple=GP_VERSION,
        title=title,
        subtitle=subtitle,
        artist=composer or "jazz-arranger",
        tempo=max(1, min(int(tempo), 999)),
    )
    header = song.measureHeaders[0]
    header.number = 1
    header.timeSignature = gp.TimeSignature(beats_per_bar, gp.Duration(4))
    track = song.tracks[0]
    track.name = "Lead"
    track.measures = []

    for index, beats in enumerate(measures, start=1):
        if index > 1:
            header = gp.MeasureHeader(
                number=index,
                timeSignature=gp.TimeSignature(beats_per_bar, gp.Duration(4)),
            )
            song.measureHeaders.append(header)
        voice = gp.Voice(None)
        for step, length in beats:
            # One beat per legal Duration. A length the format cannot hold exactly
            # - a dotted half, say - becomes two tied-looking notes rather than one
            # note of the wrong length, which is what made a bar outlast its
            # signature. See `_duration_split`.
            for value, tuplet in _duration_split(length):
                duration = gp.Duration(value)
                if tuplet is not None:
                    # A triplet is a Duration *plus* a Tuplet, not a Duration of 12.
                    # See `_duration_split`.
                    duration.tuplet = gp.Tuplet(tuplet[0], tuplet[1])
                beat = gp.Beat(
                    voice,
                    duration=duration,
                    # Without this a beat occupies zero duration and the measure's
                    # beat count no longer adds up. See the module docstring.
                    status=gp.BeatStatus.normal,
                    text=step.chord if step is not None else None,
                )
                if step is not None:
                    for string_index, fret in _sounding_frets(step):
                        beat.notes.append(
                            gp.Note(
                                beat,
                                value=fret,
                                string=_GP_STRING_OFFSET - string_index,
                                velocity=_VELOCITY,
                                type=gp.NoteType.normal,
                            )
                        )
                voice.beats.append(beat)
        # maxVoices is 2 and the writer emits every voice; one would desync the
        # file. See the module docstring.
        track.measures.append(
            gp.Measure(track, header, voices=[voice, gp.Voice(None)])
        )
    return song


def format_gp5(
    steps: List[ArrangementStep],
    title: str = "Chord-melody arrangement",
    subtitle: str = "",
    composer: str = "",
    tempo: int = 120,
    beats_per_bar: int = 4,
    rhythm: bool = True,
    collapse: bool = True,
    show_chords: bool = True,
) -> bytes:
    """
    Renders an arrangement as a Guitar Pro 5 file and returns the bytes.

    A GP5 file is binary and is normally opened by Guitar Pro; the useful thing
    to do with the bytes is write them out, which `write_gp5` does. It is a
    separate function from `write_gp5` so a caller can post-process or transmit
    the file without ever touching the filesystem.

    What it writes is one guitar track: each step as a beat whose notes are the
    strings it actually sounds, each beat carrying the chord name it is sounding
    so a substituted or extended chord is labelled with what is played, on the
    written rhythm. A held shape is written as one longer note rather than
    restruck, and a repeated melody as a single struck note - the same two rules
    `tabstaff` and `tabxml` apply, so all three renderers agree.

    Args:
        steps: arranged steps, typically from
            `VoiceLeadingEngine.arrange_progression()`.
        title: the score title.
        subtitle: a line under the title, e.g. the performer.
        composer: the artist credit.
        tempo: beats per minute, clamped to what a GP file can hold.
        beats_per_bar: beats in a bar, used for the time signature and the bars.
        rhythm: place the steps on their real beats. Falls back to a uniform
            one-chord-per-beat grid when the steps carry no timing, exactly as
            `format_musicxml` and `format_tab_staff` do, so a hand-written
            progression still exports.
        collapse: write a held shape as one longer note instead of restriking it.
        show_chords: write the chord name above each shape.

    Returns:
        The GP5 file as bytes, or b"" for no steps. Pure: nothing is printed and
        no file is written, so the caller stays in control. Needs the optional
        `PyGuitarPro` extra; see `_guitarpro` for the error raised without it.

    Raises:
        ValueError: if `beats_per_bar` is below 1.
    """
    gp = _guitarpro()
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if not steps:
        return b""

    # The substitution pass is shared with the MusicXML renderer, so a step that
    # is sounding a different chord from the one written is named the same way in
    # both files rather than only in the one that remembered to ask.
    events, pickup = _events(
        _substitute_steps(steps), beats_per_bar, rhythm and collapse
    )
    if not any(step is not None for step, _, _ in events):
        return b""

    measures = _measures(events, pickup, beats_per_bar)
    if not show_chords:
        measures = [
            [
                (
                    ArrangementStep(**{**step.__dict__, "chord": ""})
                    if step is not None
                    else None,
                    length,
                )
                for step, length in beats
            ]
            for beats in measures
        ]

    song = _build_song(
        gp, measures, title, subtitle, composer, tempo, beats_per_bar
    )
    buffer = io.BytesIO()
    gp.write(song, buffer, version=GP_VERSION)
    return buffer.getvalue()


def write_gp5(steps: List[ArrangementStep], path: str, **kwargs: Any) -> str:
    """
    Renders `format_gp5` to a file and returns the path written.

    The only function in this module that touches the filesystem, which is what
    lets every renderer stay pure. Writing is separated from rendering so a caller
    who only wants the bytes never creates a file by accident. The file is opened
    in binary mode, because a GP file is a compressed byte stream rather than text.
    """
    data = format_gp5(steps, **kwargs)
    with open(path, "wb") as handle:
        handle.write(data)
    return str(path)


# Re-exported from `tabstaff` (and through it from `arranger`) for the same reason
# the MusicXML renderers are: `tabgp` imports both, so a top-level import in either
# direction would be a cycle. The names are resolved on first access.
__all__ = ["format_gp5", "write_gp5"]


_GP_STRING_OFFSET = 6

# The shortest note value a beat can carry, as a guitarpro Duration value. A
# sixteenth is the practical floor: nothing this library generates is shorter than
# an eighth, but a transcribed beat grid can divide further, and a beat written
# with no duration occupies no time at all, which would delete it silently.
_MIN_DURATION = 16

# The longest, a whole note. Guitarpro has no dotted note, so a length that is not
# a clean power of two cannot be written as one beat - see `_duration_split`.
_MAX_DURATION = 1

# Every note value a guitarpro measure can hold, longest first: a whole note down
# to a sixteenth. A triplet is one of these plus a `Tuplet`, never a value of its
# own - see `_duration_split`.
_DURATION_VALUES: Tuple[int, ...] = (1, 2, 4, 8, 16)

# The note velocity written for every note: guitarpro's own default, and audibly
# ordinary rather than an accent. This is a reading chart, not a performance.
_VELOCITY = 95
