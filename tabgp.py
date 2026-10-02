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

Six things about the format, each of which cost a failed round trip to find, and
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
- **`Beat.status` is not optional detail, and a note-less beat is a `rest`.** The
  default is `BeatStatus.empty`, which occupies zero duration, so a beat that is
  meant to sound must say `normal`. The converse also holds: a beat with *no notes*
  must say `BeatStatus.rest`, because the writer only emits the status byte when the
  status is not `normal`. A note-less beat marked `normal` goes out as an ordinary
  beat with an empty string-flags byte, which MuseScore 3 reads as a rest in the
  right place and TuxGuitar does not - it puts the pickup rest at the end of the bar
  rather than the head. See the pickup in `_measures`.
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
from typing import Any, Dict, List, Optional, Tuple

from arranger.tuning import ArrangementStep
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
    # A sliver may be left over, and it is **dropped**. The parts above already fill
    # the beat and the format has no note value covering the remainder, so the choice
    # is between a bar that is short and one that is long, and it must be short: a
    # reader tolerates a bar ending a little early and rejects one that overruns its
    # signature outright ("voice 1 is too long") - exactly the error this function
    # exists to avoid.
    #
    # An earlier version closed the sliver by appending the shortest legal note,
    # reasoning that a short bar "silently loses music". That is backwards: the
    # music is not lost, the bar is merely a hair long. It was reached by the
    # gap-as-rest work in `tabxml._events` - a `1/6`-quarter rest, which is a
    # triplet-eighth divided by the onset, leaves a remainder no single note covers,
    # and the appended sixteenth made bar 2 of the Weimar head 4.92 quarters of 4.
    # `test_a_length_the_format_cannot_exact_is_written_short_never_long` is the
    # regression.
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

    A **bass-only** step is the mirror image: the thumb alone is a new attack, and the
    upper voices are not re-struck. Unlike the ASCII and HTML renderers, GP5 cannot
    express "held" as an empty cell - a beat either has notes or it has none, so
    writing only the thumb would read as **silence above a moving bass**. The upper
    voices are therefore written as `NoteType.tie` continuations by `_build_song`,
    which is the one way this format says "still ringing, do not re-attack". Omitting
    them instead is silent corruption rather than an error, which is why it is not
    left to the caller.
    """
    voicing = step.voicing
    if step.melody_only:
        return [(index, fret) for index, fret in enumerate(voicing.frets) if fret >= 0]
    if step.bass_only:
        # Only the thumb. The upper voices are the caller's to add as ties, because
        # they are not this step's frets - they belong to the shape already ringing.
        bass_string = voicing.bass_string
        if bass_string is None:
            return []
        return [(bass_string, voicing.frets[bass_string])]
    if step.repeated:
        struck = [voicing.soprano_string()]
        # The thumb keeps moving under a repeated melody: it is a walking line, not
        # part of the held shape, and dropping it would delete the bass on that beat.
        if voicing.bass_midi is not None and voicing.bass_string is not None:
            struck.append(voicing.bass_string)
        return [
            (index, voicing.frets[index])
            for index in struck
            if index >= 0 and voicing.frets[index] >= 0
        ]
    return [(index, fret) for index, fret in enumerate(voicing.frets) if fret >= 0]


def _held_upper_frets(frets: List[int], bass_string: Optional[int]) -> List[Tuple[int, int]]:
    """The upper voices of a *held* fret vector, as (string_index, fret).

    `frets` is the shape still ringing, which is **not** the bass-only step's own
    fret vector: under decision C a fill is the melody alone, so a bass-only step
    carries just the melody and the thumb and would re-state a one-note "shape"
    above the bass. The shape to hold is the one from the last strike, so this takes
    it as an argument and `_build_song` is what remembers it.

    The thumb's own string is excluded, so a tie and the new bass note never collide
    on one string - which would be the silent corruption of writing two notes for one
    string in one beat.
    """
    return [
        (index, fret)
        for index, fret in enumerate(frets)
        if fret >= 0 and index != bass_string
    ]


def _measures(
    events: List[Tuple[Optional[ArrangementStep], bool, float]],
    pickup: float,
    beats_per_bar: int,
    beat_type: int = 4,
) -> List[List[Tuple[Optional[ArrangementStep], float, bool]]]:
    """
    The events as a list of measures, each a list of (step, length, tie) beats.

    **This is where GP5 and MusicXML differ**, and the difference is forced by the
    format rather than chosen. MusicXML has an anacrusis: a measure may simply be
    short, and `tabxml._build_part` writes it that way. A GP5 measure is a
    fixed-length container with no "implicit" or "pickup" attribute the format
    relies on, so a head that starts part-way into its first bar is written as a
    **rest** for the pickup and the music begins after it. The bar is then full
    length, exactly as GP5 requires, and every note keeps the position the score
    gave it.

    An event that runs across a bar line is **split**, not stretched and not
    dropped: the two halves are written in consecutive measures, exactly as
    `_build_part` splits a MusicXML note and joins the halves with a `<tie>`. The
    `tie` flag on each beat is what keeps the split from being heard as a
    re-articulation - the continuation is written with `NoteType.tie`, so the two
    halves are one held note rather than the same shape struck twice.

    GP5 has a real tie: `guitarpro.models.NoteType.tie`, verified to survive a
    write/parse round trip in PyGuitarPro 0.11. The earlier code believed a GP tie
    was "a slur the player has to interpret" and wrote both halves as plain notes
    instead, which re-struck the shape at the head of every bar a step crossed -
    14 of the 32 bars of "But Not For Me", and the source score ties Eb4 across
    the bar line in bars 2-3. A held chord in a chord-melody part is not something
    to re-finger, so the split has to carry the tie the score already had.
    """
    # The bar in quarter notes: `beats_per_bar` beats of **4 / beat_type**
    # quarters - a 2/2 beat is a *half* note, so two quarters to the beat, not
    # `2/4` of one. Both 4/4 and 2/2 bars are four quarters, which is the check
    # that catches this: reading the fraction the other way round is right in 4/4
    # and makes every cut-time bar a quarter note long, and 4/4 is the one metre
    # where the error is invisible to the whole suite.
    bar_length = float(beats_per_bar) * (4.0 / float(beat_type))
    measures: List[List[Tuple[Optional[ArrangementStep], float, bool]]] = []
    if pickup > 0:
        # The pickup is written as a **rest** at the head of the first measure, and
        # the cursor below starts at zero, so the music follows it rather than
        # replacing it. Bar 1 of "But Not For Me" is a quarter rest and then three
        # quarter notes; discarding the rest moved the whole head onto the downbeat
        # and wrote the bar as three chords where the file says rest-plus-three.
        #
        # The earlier code opened an *empty* measure here and dropped it again at the
        # end, which is not a representation of a pickup but its deletion: the music
        # after it slid forward by the length of the rest to fill the gap. A rest is
        # a beat the format can hold, so writing one keeps every onset where the
        # score puts it, which is the whole claim of this renderer.
        measures.append([(None, pickup, False)])

    # A running cursor in quarter notes, **offset by the pickup** so the music
    # follows the rest rather than starting on top of it. Whenever the cursor
    # *reaches* a bar line a measure is opened, not only when an event crosses one:
    # the eighth-note skeleton puts beats that land exactly on the boundary, and
    # testing only for a crossing leaves them all in one measure.
    cursor = pickup
    for step, _strikes, length in events:
        remaining = length
        # Whether any part of this event has already been written. The first chunk
        # is the attack; every chunk after it is a continuation of a note that began
        # in an earlier bar, and is flagged so `_build_song` can tie it rather than
        # strike the shape again.
        started = False
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
                measures[-1].append((step, chunk, started))
                started = True
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
    # The leading measure is *not* one of these: it now holds the pickup rest, so it
    # has a beat in it and survives. That is the point - see the `pickup` branch
    # above.
    return [beats for beats in measures if beats]


def _build_song(
    gp: Any,
    measures: List[List[Tuple[Optional[ArrangementStep], float, bool]]],
    title: str,
    subtitle: str,
    composer: str,
    tempo: int,
    beats_per_bar: int,
    beat_type: int = 4,
) -> Any:
    """
    The measures as a guitarpro `Song`, ready to write.

    Reuses the `Song`'s own default header and track rather than appending to
    them, and gives every measure its second empty voice - see the module
    docstring, both of which are silent corruptions rather than errors.

    `beat_type` is the denominator, and it is not always 4: a head notated in cut
    time is 2/2, and writing that as 2/4 states a metre the tune is not in. The
    *bar length* is the same either way, so this affects only what the file
    displays.
    """
    signature = gp.TimeSignature(beats_per_bar, gp.Duration(beat_type))
    song = gp.Song(
        versionTuple=GP_VERSION,
        title=title,
        subtitle=subtitle,
        artist=composer or "jazz-arranger",
        tempo=max(1, min(int(tempo), 999)),
    )
    header = song.measureHeaders[0]
    header.number = 1
    header.timeSignature = signature
    track = song.tracks[0]
    track.name = "Lead"
    track.measures = []

    # The shape currently ringing above the thumb, as a fret vector. A GP5 beat
    # cannot express "held" as an empty string the way a tab cell can, so a
    # bass-only beat has to *write* the held shape as tied notes - and the shape to
    # write is the one from the last strike, not the bass-only step's own frets,
    # which under decision C hold only the melody. Threaded through every measure
    # rather than per measure, because a held shape routinely spans a barline.
    ringing: Optional[List[int]] = None

    # The fret last written on each **GP string** (1 = high E), over the whole file.
    #
    # This exists because of what a GP5 tie means in the format, which is not "held"
    # in the abstract but a specific claim about the bytes. PyGuitarPro's writer
    # deliberately emits **no fret at all** for a `NoteType.tie` note
    # (`gp5.writeNote`: `fret = note.value if note.type != NoteType.tie else 0`), and
    # the reader reconstructs one by scanning backwards for the most recent note on the
    # same string (`getTiedNoteValue`). So a tie does not carry a pitch - it asserts
    # "same pitch as the last note on this string", and the file agrees only while that
    # assertion is true.
    #
    # Walking bass breaks it, because the thumb may be placed on a string the held shape
    # is still sounding. The engine only knows the *current* step's thinned voicing when
    # it picks that string (see `arranger/bass.py`), so on a `bass_only` step it can put
    # the thumb on a string the ringing shape occupies. The tie written for that string
    # then resolves to the thumb's fret rather than the shape's, and the file says a
    # pitch the engine never produced - an A5 where the arrangement has an A6.
    #
    # So the tie is written only where the claim holds, and the note is struck normally
    # where it does not. A re-struck note is a performance difference the player can
    # hear and forgive; a wrong pitch in a file they are reading note-for-note is not.
    last_on_string: Dict[int, int] = {}

    for index, beats in enumerate(measures, start=1):
        if index > 1:
            header = gp.MeasureHeader(
                number=index,
                timeSignature=gp.TimeSignature(beats_per_bar, gp.Duration(beat_type)),
            )
            song.measureHeaders.append(header)
        voice = gp.Voice(None)
        for step, length, tie in beats:
            # One beat per legal Duration. A length the format cannot hold exactly
            # - a dotted half, say - becomes two tied-looking notes rather than one
            # note of the wrong length, which is what made a bar outlast its
            # signature. See `_duration_split`.
            #
            # A beat that continues a note begun in an earlier bar is written as a
            # GP **tie** rather than a second attack, so a shape held across a bar
            # line is not re-struck at the head of the next one. `tie` carries that
            # from `_measures`; it is False for the first chunk of every event.
            for value, tuplet in _duration_split(length):
                duration = gp.Duration(value)
                if tuplet is not None:
                    # A triplet is a Duration *plus* a Tuplet, not a Duration of 12.
                    # See `_duration_split`.
                    duration.tuplet = gp.Tuplet(tuplet[0], tuplet[1])
                beat = gp.Beat(
                    voice,
                    duration=duration,
                    # A beat with notes is `normal`; a beat with none is a **rest**,
                    # and it must say so. The writer only emits the status byte when
                    # the status is not `normal`, so a note-less beat written as
                    # `normal` goes out as an ordinary beat with an empty string-flags
                    # byte - which MuseScore reads as a rest in the right place and
                    # TuxGuitar does not, putting the pickup rest at the end of the
                    # bar instead of the head. `BeatStatus.rest` sets the flag that
                    # says rest explicitly. See `_build_song`.
                    status=(gp.BeatStatus.normal if step is not None
                            else gp.BeatStatus.rest),
                    text=step.chord if step is not None else None,
                )
                if step is not None:
                    for string_index, fret in _sounding_frets(step):
                        gp_string = _GP_STRING_OFFSET - string_index
                        beat.notes.append(
                            gp.Note(
                                beat,
                                value=fret,
                                string=gp_string,
                                velocity=_VELOCITY,
                                # `NoteType.tie` is a real GP5 tie and round-trips
                                # through PyGuitarPro, so the two halves of a split
                                # step are one held note. A split writes the same frets
                                # as the chunk before it on the same strings, so the
                                # "same pitch as the last note here" claim a tie makes
                                # is true by construction - see `last_on_string`.
                                type=gp.NoteType.tie if tie else gp.NoteType.normal,
                            )
                        )
                        last_on_string[gp_string] = fret
                    # A bass-only beat still has to *say* the shape that is ringing
                    # above the thumb, because a GP beat cannot have an empty string
                    # in the way a tab cell can. Written as ties, so it reads as held
                    # rather than re-struck - see `_sounding_frets`. Skipped on a
                    # continuation chunk, which already carries the tie from the
                    # chunk that began it.
                    if step.bass_only and not tie and ringing is not None:
                        for string_index, fret in _held_upper_frets(
                            ringing, step.voicing.bass_string
                        ):
                            gp_string = _GP_STRING_OFFSET - string_index
                            # A tie here says "this string is still sounding what it
                            # sounded last", which holds only while nothing else has
                            # been written on it since. The thumb is written first and
                            # may well be on this string (the engine picks it from the
                            # current step's thinned voicing, not the ringing shape), in
                            # which case a tie would resolve to the thumb's fret and
                            # the file would carry a pitch the engine never produced.
                            # Struck normally instead: an audible re-strike is a far
                            # smaller fault than a silently wrong note.
                            held = last_on_string.get(gp_string) == fret
                            beat.notes.append(
                                gp.Note(
                                    beat,
                                    value=fret,
                                    string=gp_string,
                                    velocity=_VELOCITY,
                                    type=(gp.NoteType.tie if held
                                          else gp.NoteType.normal),
                                )
                            )
                            last_on_string[gp_string] = fret
                    elif step is not None and not step.bass_only:
                        # Any other step re-states the shape in full, so it becomes
                        # the one ringing. A `repeated` step strikes the soprano
                        # alone over the shape already sounding, which is why it is
                        # excluded: taking its one-fret vector would erase the held
                        # shape for the bass-only beats that follow.
                        if not step.repeated:
                            ringing = list(step.voicing.frets)
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
    beat_type: int = 4,
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
        beat_type: the denominator of that signature. Pass the notated value, so a
            head in cut time is written 2/2 rather than restated as 2/4; the bar
            length is identical either way and only the displayed metre differs.
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
        _substitute_steps(steps), beats_per_bar, rhythm and collapse, beat_type
    )
    if not any(step is not None for step, _, _ in events):
        return b""

    measures = _measures(events, pickup, beats_per_bar, beat_type)
    if not show_chords:
        measures = [
            [
                (
                    ArrangementStep(**{**step.__dict__, "chord": ""})
                    if step is not None
                    else None,
                    length,
                    tie,
                )
                for step, length, tie in beats
            ]
            for beats in measures
        ]

    song = _build_song(
        gp, measures, title, subtitle, composer, tempo, beats_per_bar, beat_type
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
