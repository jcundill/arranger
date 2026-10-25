"""The walking bass: a thumb line on the three lowest strings.

Three passes, in this order, and the order is the design:

1. `_walking_bass_line` reads **harmony only** and returns one `BassNote` per
   walked beat, each a *pitch class*. It cannot know the octave or the string,
   because it runs before any upper voicing exists.
2. `walking_slots` unions those beats with the melody grid into one `Slot`
   list, built **before** the melody loop, so the loop's index still indexes the
   skeleton it was given.
3. `place_bass` - in `bass_place` - resolves the octave and the string together,
   after selection, because a note an octave away is a different fret on every
   string.

`bass_cost` also lives in `bass_place`, not in `cost.py`, because it ranks over the
`BASS_ROLE_*` vocabulary and is called by `_walking_bass_line`; in `cost` it would
need this module and this module would need `cost`.

**One slot union, built once.** The step loop reaches `walking_slots` -
`VoiceLeadingEngine.arrange_progression`, and through it the imported-head path -
because a second copy is exactly the failure this library documents having had once
already: the corpus path was built separately, drifted, and voiced an `Am7` under a
written `Bbm7` for twenty-five transcriptions before anyone noticed. That path has
since been removed, and the lesson outlived it. Walking bass
is the same trap with the same stakes, since a path that arranged the shells but
not the walk would look plausible and be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from musthe import Note

from .bass_place import BassNote, bass_cost
from .bass_rules import (
    BASS_ALL_RULES,
    BASS_ROLE_ANCHOR,
    BASS_ROLE_APPROACH,
    BASS_ROLE_CONNECT,
    BASS_ROLE_ENCLOSURE,
    BASS_ROLE_FIFTH,
    BASS_ROLE_HOLD,
    BASS_ROLE_PEDAL,
    BASS_RULE_5TH,
    BASS_RULE_APPROACH,
    BASS_RULE_NEAREST,
    BASS_RULE_ROLES,
    BASS_RULE_ROOT,
    BASS_RULES,
    BASS_STYLE_NONE,
    parse_bass_style,
)
from .chords import NON_CHORD_TONE_EXTENSIONS, ChordParser, normalised_harmony, parse_symbol
from .grid import BEAT_EPSILON, Rhythm, beat_offset, rhythm_beats
from .grips import BASS_DEGREES_6432
from .grouping import group_starts
from .texture import metric_weight
from .tuning import NO_CHORD


def _bass_harmony(
    root: Optional[str], quality: str
) -> Optional[Tuple[int, Tuple[int, ...]]]:
    """
    A chord's bass-relevant facts: its root's pitch class, and every pitch class a
    thumb may play under it without leaving the chord's vocabulary.

    The permitted set is the chord's own tones **plus** the extensions this quality's
    `NON_CHORD_TONE_EXTENSIONS` row can name - not purity. Two thirds of the notes in
    a textbook walk are not chord tones of the chord they sit under, and a
    purity-first rule returns the arpeggio the arranging guide explicitly warns
    against ("pure arpeggios can sound like exercise drills"). Reaching for the
    extension table rather than a scale is also what keeps the "no key model" claim
    true: strip the extensions out and diatonic movement becomes unreachable, at
    which point a key model really would be necessary.

    Returns **None** for a chord this library cannot speak - an unparseable root, or
    a quality with no tone table. Never a guess, the same rule
    `WEIMAR_QUALITY_ALIASES` and `MUSICXML_KIND_QUALITIES` already follow; a walk
    that invents a harmony under the thumb is worse than no walk at all.
    """
    canonical = ChordParser.canonical_quality(quality)
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical, ())
    if not root or not tones:
        return None
    try:
        root_pc = Note(f"{root}4").midi_note() % 12
    except (KeyError, ValueError, TypeError):
        return None
    extensions = NON_CHORD_TONE_EXTENSIONS.get(canonical, {})
    permitted = {(root_pc + degree) % 12 for degree in tones}
    permitted.update((root_pc + degree) % 12 for degree in extensions)
    return root_pc, tuple(sorted(permitted))



@dataclass
class Slot:
    """
    One entry of the slot list `arrange_progression` actually loops over.

    For `uniform` and `targets` this is exactly one slot per progression triple and
    the three timing fields are read off `timings` with the guard the corpus loader
    already applies. It exists as a type rather than a tuple because on a walked
    route the list is the **union** of the melody slots and the walked
    beats, so an entry can name a progression index that is not its own position -
    which is the price of decision B, and the reason the union has to be built
    *before* the melody loop rather than spliced into its output.

    `bass_only` marks the entries the walk invented: they carry the previous melody
    pitch (so `index` points at it) and exist so the thumb has a beat to sound on.
    """

    # Which progression triple this slot's melody and harmony come from.
    index: int
    bar: Optional[int] = None
    beat: Optional[float] = None
    duration: Optional[float] = None
    # The walked beat landing on this slot, if any.
    bass: Optional[BassNote] = None
    # True when the slot exists only for the thumb and nothing above it strikes.
    bass_only: bool = False


def _walked_chords(
    progression: Sequence[Tuple[Optional[str], str]],
) -> List[Tuple[Optional[str], str, str]]:
    """The walk's own view of each slot: its root, its quality, and the symbol.

    One reading of the symbol - the same one the voicing path uses - so the walk cannot
    disagree with the shape about what the chord is. A symbol asking for no chord carries
    the marker through, so the line has something to be silent about.
    """
    chords: List[Tuple[Optional[str], str, str]] = []
    for _note, name in progression:
        symbol = parse_symbol(name)
        chords.append(
            (symbol.root, symbol.quality, name) if symbol
            else (None, NO_CHORD, name)
        )
    return chords


def walking_slots(
    # `Sequence` + `Optional`, for the same reason as `timings` below: the engine's
    # pairs carry an `Optional` melody (§9.3 step B), and `List` is invariant - the
    # covariance note on `timings` is this signature's whole reason for spelling both
    # this way.
    progression: Sequence[Tuple[Optional[str], str]],
    # `Sequence`, not `List`, and that is load-bearing rather than stylistic: the two
    # callers hold *different* timing types. `arrange_progression` supplies
    # `Tuple[int, float, ...]`, while `arrange_slots` builds
    # `Tuple[Optional[int], Optional[float], ...]` placeholders for slots it could not
    # place. `List` is invariant, so neither is assignable to the other and the two
    # paths cannot share one function at all; `Sequence` is covariant, so both are
    # accepted and the unplaced placeholders are filtered out below. This is the third
    # time list invariance in a signature has cost this library something - see also
    # `BUT_NOT_FOR_ME_TIMINGS` in test_texture.py and `arrange_slots` itself.
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    beats_per_bar: int = 4,
    # The metre's denominator. It reaches `_bass_slots` and stops there: the *grid* the
    # walk invents beats on is counted in beats (`bass_line_for` needs only the count),
    # while the melody *timeline* those beats are attributed through converts each slot's
    # whole-note `duration` to beats, which needs this. See `_melody_timeline`.
    beat_type: int = 4,
    bass: str = BASS_ALL_RULES,
    # The metre's felt beats, as group lengths. `None` means one per denominator
    # unit, the reading this function had before grouping existed. The walk invents
    # one note per **felt** beat, so 12/8 walks four dotted-quarter pulses rather
    # than twelve eighths.
    grouping: Optional[Sequence[int]] = None,
    # The bass's **positions**, when the caller named them. `None` means the metre's
    # own felt beats - the reading every caller had before a request could name a
    # rhythm - so a sparse `--bass-on 1` walks beat 1 and nothing else.
    rhythm: Optional[Rhythm] = None,
    # The form's first complete bar, where a figure's first segment lands. `None` is a
    # figure placed on no form, which runs on absolute phase from bar 1.
    first_full_bar: Optional[int] = None,
) -> List[Slot]:
    """
    The walking-bass slot union: the melody grid plus the walked beats.

    `bass` names the style from the note-rule vocabulary, and what each note is *for*
    is the style's business: the full `root,5th,approach,nearest` writes a note at
    every position, and `root` keeps the beats that already carry an anchor - which
    needs far less room under the left hand and so works under textures the walk is
    refused for. The union is built the same way either way.

    `rhythm` replaces that grid. A request names its own positions, so
    `--bass-on every-beat` and `--bass-on 1,3` are one spelling of "where the thumb
    sounds" and the metre fills the beats in; with no rhythm the felt beats stand.
    `first_full_bar` is where that figure's **first segment** lands - the form's first
    complete bar - so a figure longer than one bar begins with the form rather than
    consuming the pickup. `None` is a figure placed on no form, which the walk runs on
    absolute phase from bar 1 instead.

    **The one place the union is built**: the reason is in the module docstring, and
    it is that a path which arranged the shells but not the walk would look plausible
    and be wrong.

    Reads harmony only, never the melody pitches - the melody is read when the slot is
    voiced, and a slot's `index` says which melody is sounding under it. That is what
    lets the walked beats be discovered before any voicing exists.

    With `timings=None` there is no beat grid to place four quarters on, so this
    degrades to one note per slot: the documented gridless case.
    """
    chords = _walked_chords(progression)
    onsets = _placed_onsets(timings, len(progression))
    bass_line = bass_line_for(
        bass, chords, onsets, beats_per_bar, grouping, rhythm, first_full_bar
    )
    return _bass_slots(progression, timings, bass_line, beats_per_bar, beat_type)


def _placed_onsets(
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    count: int,
) -> List[Optional[Tuple[int, float]]]:
    """The `(bar, beat)` of every slot the caller could place, and `None` where it could not.

    A slot with no beat has no place on the grid, which is what the walk needs to know:
    an onset it cannot locate is a beat it does not invent one for.
    """
    onsets: List[Optional[Tuple[int, float]]] = []
    for index in range(count):
        timing = timings[index] if timings is not None and index < len(timings) else None
        bar = timing[0] if timing is not None else None
        beat = timing[1] if timing is not None else None
        onsets.append(
            (bar, float(beat)) if bar is not None and beat is not None else None
        )
    return onsets


def _melody_in_force(
    timeline: Sequence[Tuple[float, float, int]], at: float
) -> int:
    """Which melody slot is sounding at beat `at`, or -1 if the melody has not started.

    `timeline` is `(onset, end, index)` in absolute beats, ordered by onset. The rule
    is **the latest note that has not stopped sounding**, which is not the same as
    "the latest onset" and not the same as "whatever the walk last passed":

    - A note whose `duration` runs past the next note's onset keeps winning until it
      stops, so a phrase that holds one note across a barline hands that note - not
      the one that follows - to the invented downbeat.
    - A later note that *has* ended loses to an earlier one still sounding, which is
      what "in force" means and what onset order alone cannot say.

    Where the score writes **silence** at `at`, nothing is in force and the note that
    most recently started is returned instead: the left hand is still holding that
    shape, and a beat invented for the thumb has to name the harmony that is
    actually up. -1 means the melody has not started yet at all, which is the
    caller's problem to decide and not this function's to guess.

    One forward pass suffices and needs no cursor: `timeline` is in onset order, so
    the last assignment in each variable is the latest one.
    """
    latest = -1
    sounding = -1
    for onset, end, index in timeline:
        if onset > at + BEAT_EPSILON:
            break
        latest = index
        if at < end - BEAT_EPSILON:
            sounding = index
    return sounding if sounding >= 0 else latest


def _melody_timeline(
    located: Sequence[Tuple[int, int, float, Optional[float]]],
    beats_per_bar: int,
    beat_type: int = 4,
) -> List[Tuple[float, float, int]]:
    """`located` as `(onset, end, index)` spans on one absolute beat line.

    A slot's `duration` is in **whole notes**, and the number of beats in one is
    `beat_type`: a beat is `4 / beat_type` quarters - the same `beat_in_quarters` the
    renderers convert with - so four quarters of whole note is `beat_type` beats and a
    duration becomes `duration * beat_type` beats. It is **not** `duration *
    beats_per_bar`: the two agree only where the numerator equals the denominator, which
    is 4/4 and 2/2 and so six of the seven committed heads. In 3/4 the count is 3 while a
    whole note is 4 beats, so `duration * beats_per_bar` would make every span a quarter
    short. It is written as `duration * beat_type` rather than left, because the next
    metre-sensitive rule would inherit the error.

    `beats_per_bar` is still here and still the *count*: `beat_offset` places a
    `(bar, beat)` pair with it, and that is a question about how many beats a bar has
    and not about how long one lasts. Both numbers are needed, and they are not
    interchangeable.

    An unknown duration is `inf`, not zero: "we were not told" is not "it ended
    here", and a note given no length is the one case where holding it is the safe
    reading. `located` is already in onset order, and a stable sort keeps two slots
    sharing an onset in progression order, so the later index wins - the same
    last-one-wins rule `melody_at` applies below.
    """
    return sorted(
        (
            (
                beat_offset(bar, beat, beats_per_bar),
                (
                    float("inf")
                    if duration is None
                    else beat_offset(bar, beat, beats_per_bar)
                    + duration * beat_type
                ),
                index,
            )
            for index, bar, beat, duration in located
        ),
        key=lambda span: (span[0], span[2]),
    )


_SlotEntry = Tuple[Tuple[int, float], int, Optional[BassNote], bool]


def _located_slots(
    progression: Sequence[Tuple[Optional[str], str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
) -> List[Tuple[int, int, float, Optional[float]]]:
    """Every progression index whose slot the caller could place, with its timing."""
    located: List[Tuple[int, int, float, Optional[float]]] = []
    for index in range(len(progression)):
        timing = timings[index] if timings is not None and index < len(timings) else None
        if timing is None:
            continue
        bar, beat, duration = timing
        # A `(None, None, None)` placeholder is a slot the caller could not place, not
        # a timing. Testing the tuple rather than the reference is what catches it -
        # the head path builds those placeholders explicitly, and an unplaced slot
        # reaching the grid arithmetic below would place a note at bar None.
        if bar is None or beat is None:
            continue
        located.append((index, bar, beat, duration))
    return located


def _gridless_slots(
    progression: Sequence[Tuple[Optional[str], str]],
    bass_line: List[BassNote],
) -> List[Slot]:
    """One slot per progression entry, when there is no beat grid to union against."""
    # Gridless: one note per slot, attached by position and guarded, because the
    # bass line can be shorter than the progression when a chord is unparseable.
    slots: List[Slot] = []
    for index in range(len(progression)):
        slots.append(Slot(
            index=index,
            bass=bass_line[index] if index < len(bass_line) else None,
        ))
    return slots


def _melody_entries(
    located: Sequence[Tuple[int, int, float, Optional[float]]],
    bass_line: List[BassNote],
) -> List[_SlotEntry]:
    """One entry per melody slot, carrying the walk note on the same onset."""
    entries: List[Tuple[Tuple[int, float], int, Optional[BassNote], bool]] = []
    for index, bar, beat, _duration in located:
        key = (bar, float(beat))
        bass = next((note for note in bass_line
                     if note.bar == bar and note.beat is not None
                     and abs(note.beat - float(beat)) <= BEAT_EPSILON), None)
        entries.append((key, index, bass, False))
    return entries


def _bass_only_entries(
    located: Sequence[Tuple[int, int, float, Optional[float]]],
    bass_line: List[BassNote],
    melody_at: Dict[Tuple[int, float], Tuple[int, Optional[float]]],
    beats_per_bar: int,
    beat_type: int,
) -> List[_SlotEntry]:
    """The walked beats with no melody slot, each carrying the melody in force."""
    # The walked beats with no melody slot. Each takes the melody **in force** at its
    # own instant, read off the melody timeline rather than off the walk's own beats.
    #
    # That distinction is the whole fix. Tracking the previous melody while iterating
    # `bass_line` means a melody slot is only noticed when the walk happens to land on
    # it, so in a 2/2 bar - where the walk visits beats 1.0 and 2.0 only - a melody
    # moving at beat 2.5 is invisible and the invented downbeat inherits from beat 2.0
    # instead. Nine downbeats of "But Not For Me" stated the wrong note that way, and
    # because the wrong note then became the melody the slot *looks* correct to every
    # check that compares against the arrangement's own idea of itself.
    #
    # `melody_at` stays for what it is good for - the exact onset test below and the
    # duration each slot reports - but precedence over time is now `_melody_in_force`'s
    # job, and it is a different question with a different answer.
    timeline = _melody_timeline(located, beats_per_bar, beat_type)
    entries: List[_SlotEntry] = []
    for note in bass_line:
        if note.bar is None or note.beat is None:
            continue
        key = (note.bar, float(note.beat))
        if key in melody_at:
            continue
        in_force = _melody_in_force(
            timeline, beat_offset(note.bar, float(note.beat), beats_per_bar)
        )
        # Index 0 when the melody has not started yet, which is the pre-existing
        # fallback: something has to be named, and the opening slot is the least
        # wrong thing to say on a beat before the tune begins.
        entries.append((key, in_force if in_force >= 0 else 0, note, True))
    return entries


def _bass_slots(
    progression: Sequence[Tuple[Optional[str], str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    bass_line: List[BassNote],
    beats_per_bar: int = 4,
    beat_type: int = 4,
) -> List[Slot]:
    """
    The union of the melody grid and the walked beats, as one ordered slot list.

    Decision B: the bass grid may be **finer** than the melody grid, because a bar
    whose melody is a single whole note still has a beat on every one of its
    `beats_per_bar` beats to walk. Every walked beat that has no melody slot becomes
    an extra slot carrying the melody in force at that instant, marked `bass_only` -
    the renderer holds the upper voices across it and strikes only the thumb.

    **"A beat on every beat" is not "four beats".** The grid is `beats_per_bar` beats
    wide, so a bar yields four thumb notes in 4/4, three in 3/4 and **two in 2/2** -
    and three of the four committed scores are notated in cut time. "A four-quarter
    walk" is the same claim written as a literal, and it holds only in the metre it is
    written in: in 2/2 the walk never reaches beat 2.5. The grid is the grid; the
    precedence question below is separate and is answered over the melody timeline.

    `timings` is `(bar, beat, duration)` per slot and a slot placed nowhere arrives as
    `(None, None, None)`: the head path positions every note but not the rests it skips,
    and a caller may state an absence. Such a slot is skipped here, exactly as
    `arrange_slots` skips it - an unlocated slot has no place on a grid, and inventing one
    would be the "a count without a denominator is not a metre" mistake in a new hat. A
    progression that supplied no timeline is laid out by `movement` before it gets here.

    Two properties are load-bearing and both are about ordering:

    - the union is built **before** the melody loop, so the loop's index still means
      what it meant - `arrange_head`'s timings guard and `arrange_slots`' retry index
      index into the skeleton, not into the result;
    - an extra slot's `index` is the melody slot **in force** at that beat - found
      from the melody timeline by onset *and* duration, not from the walk's own
      beats. The melody it carries is therefore the one actually sounding at that
      instant, and the harmonic timeline the walk reads is unchanged by the union
      itself.

    The distinction between "in force" and "the previous slot" is not a refinement.
    It is the difference between the arrangement matching the score between its note
    onsets and not: the two rules disagree on nine downbeats of "But Not For Me",
    and the renderers faithfully wrote the wrong melody at every one of them.

    With no usable timing there is no beat grid to union against, and the gridless
    degradation stands: one thumb note per anchor, one per slot. That is the
    documented `timings=None` case, not a failure.
    """
    located = _located_slots(progression, timings)
    if not located:
        return _gridless_slots(progression, bass_line)

    melody_at: Dict[Tuple[int, float], Tuple[int, Optional[float]]] = {
        (bar, float(beat)): (index, duration) for index, bar, beat, duration in located
    }
    entries = _melody_entries(located, bass_line)
    entries.extend(
        _bass_only_entries(located, bass_line, melody_at, beats_per_bar, beat_type)
    )

    # Sort by onset, with a melody slot ahead of a bass-only slot on the same onset
    # so the step that strikes the melody is the step that carries that walk note.
    entries.sort(key=lambda entry: (entry[0][0], entry[0][1], entry[3], entry[1]))

    slots: List[Slot] = []
    for key, index, bass, bass_only in entries:
        duration = melody_at.get(key, (index, None))[1]
        slots.append(Slot(
            index=index,
            bar=key[0],
            beat=key[1],
            duration=duration,
            bass=bass,
            bass_only=bass_only,
        ))
    return slots


_Harmony = Tuple[int, Tuple[int, ...]]
_HarmonyKey = Optional[Tuple[Optional[str], Optional[str]]]


def _located_onsets(
    onsets: Optional[Sequence[Optional[Tuple[int, float]]]],
) -> List[Tuple[int, float, int]]:
    """The (bar, beat, progression index) of every slot that has a position."""
    return (
        [
            (onset[0], onset[1], index)
            for index, onset in enumerate(onsets)
            if onset is not None
        ]
        if onsets is not None
        else []
    )


def _anchor_only_line(
    chords: Sequence[Tuple[Optional[str], str, str]],
) -> List[BassNote]:
    """The line when there is no beat grid: one anchor per slot."""
    notes: List[BassNote] = []
    for root, quality, _name in chords:
        harmony = _bass_harmony(root, quality)
        if harmony is None:
            continue
        notes.append(BassNote(None, None, harmony[0], BASS_ROLE_ANCHOR))
    return notes


def _walked_beats(
    located: Sequence[Tuple[int, float, int]],
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
    rhythm: Optional[Rhythm] = None,
    first_full_bar: Optional[int] = None,
) -> List[Tuple[int, float]]:
    """One beat per **requested position** in every bar the melody touches.

    The grid is the grouping, not the melody: a 12/8 bar whose tune is a whole note
    still yields four thumb notes, one on each dotted-quarter pulse, and a 4/4 bar
    yields four. With no grouping every denominator unit is its own group, which is
    the reading this function had before grouping existed.

    `rhythm` replaces the felt beats with the positions a request named, **bar by
    bar**: a sparse `--bass-on 1,3` walks two notes in every bar of a one-bar
    figure, a bar naming `melody` walks the metre's own felt beats, a bar the cycle
    leaves silent walks nothing, and a longer figure gives each bar its own segment
    from `first_full_bar` onwards. The bars are unchanged either way - the melody's
    own span is what says how much music there is.
    """
    bars = sorted({bar for bar, _beat, _index in located})
    metre_beats = group_starts(beats_per_bar, grouping)
    walked: List[Tuple[int, float]] = []
    for bar in bars:
        segment = (
            rhythm.at(bar, first_full_bar) if rhythm is not None else None
        )
        if segment is None or segment.melody:
            walked.extend((bar, beat) for beat in metre_beats)
        elif not segment.is_none:
            walked.extend(
                (bar, beat) for beat in rhythm_beats(segment, beats_per_bar, grouping)
            )
    return walked


def _walked_harmony(
    chords: Sequence[Tuple[Optional[str], str, str]],
    onsets: Optional[Sequence[Optional[Tuple[int, float]]]],
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
    rhythm: Optional[Rhythm] = None,
    first_full_bar: Optional[int] = None,
) -> Tuple[
    List[Tuple[int, float]], List[Optional[_Harmony]], List[_HarmonyKey]
]:
    """Where the line sounds, and the harmony in force at each of those positions.

    The one place "which positions are walked" and "what chord is under them" are
    answered together, so the walking line and the simple root/5th line cannot
    disagree about either. Empty `walked` means there is no beat grid at all - the
    documented `timings=None` case.
    """
    located = _located_onsets(onsets)
    if not located:
        return [], [], []
    walked = _walked_beats(located, beats_per_bar, grouping, rhythm, first_full_bar)
    harmonies, keys = _filled_harmony(walked, chords, located)
    return walked, harmonies, keys


def _filled_harmony(
    walked: Sequence[Tuple[int, float]],
    chords: Sequence[Tuple[Optional[str], str, str]],
    located: Sequence[Tuple[int, float, int]],
) -> Tuple[List[Optional[_Harmony]], List[_HarmonyKey]]:
    """The harmony in force at each walked beat, by forward fill.

    An `NC` slot ends the harmony rather than continuing it; a slot this library
    cannot voice leaves the previous harmony in force.
    """
    # The harmony in force at each walked beat, by forward fill on the (bar, beat)
    # tuple - the same rule the corpus loader and the MusicXML importer apply, and
    # the same one the left hand reads. An `NC` slot **ends** the harmony rather than
    # continuing it, and a bar with no harmony behind it yet gets no notes at all.
    #
    # The end is a derivation, not a rule about chordless bars: a part whose notes are
    # chosen from a chord cannot state anything where there is no chord
    # (docs/history/parts.md §4). So `carried` is cleared rather than left standing, which is
    # what keeps the *bass* part out of an `NC` bar: the forward fill below is the only
    # thing that would otherwise hand it the previous chord's root, and the emission
    # then skips every beat whose harmony is None. "No chord here" and "a chord this
    # library cannot voice" are different facts, and only the first ends the harmony -
    # an untranslatable symbol, counted in `Head.unmapped`, leaves the chord in force,
    # because its harmony is still the music's.
    onsets_sorted = sorted(located)
    harmonies: List[Optional[_Harmony]] = []
    keys: List[_HarmonyKey] = []
    cursor = 0
    carried: Optional[_Harmony] = None
    carried_key: _HarmonyKey = None
    for bar, beat in walked:
        while (
            cursor < len(onsets_sorted)
            and (onsets_sorted[cursor][0], onsets_sorted[cursor][1]) <= (bar, beat)
        ):
            root, quality, name = chords[min(onsets_sorted[cursor][2], len(chords) - 1)]
            if name == NO_CHORD:
                carried = None
                carried_key = None
                cursor += 1
                continue
            parsed = _bass_harmony(root, quality)
            if parsed is not None:
                carried = parsed
                carried_key = normalised_harmony(f"{root}{quality}")
            # Otherwise the slot is unspeakable, and `carried` holds unchanged: the
            # chord is in force even where this library cannot voice it.
            cursor += 1
        harmonies.append(carried)
        keys.append(carried_key)
    return harmonies, keys


def _anchor_flags(
    walked: Sequence[Tuple[int, float]],
    harmonies: Sequence[Optional[_Harmony]],
    keys: Sequence[_HarmonyKey],
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> List[bool]:
    """The first position of a bar, plus a strong beat whose harmony is new."""
    # An anchor is the first walked position of a bar, plus any strong beat whose
    # harmony is not already stated. The second clause is the mid-bar change, and it is
    # the *same* predicate `roles_for_slot` already applies to the left hand - strong
    # beat, and a harmony differing from the previous target's - so the thumb and the
    # fingers fire on one slot by construction rather than by a second mechanism kept
    # in step by hand.
    #
    # **The first position, not beat 1**, because a rhythm may not name the downbeat:
    # `--bass-on 2,4` still needs a root to mark each bar, and a `downbeat` test would
    # leave every note in the line connective with no anchor to approach. On the full
    # felt-beat grid the two readings are the same position, so this is the same rule
    # written where a sparse line can keep it.
    is_anchor: List[bool] = []
    previous_anchor: _HarmonyKey = None
    # The last bar the line has stated a chord in, so "the first position of a bar"
    # means the first one the bar's harmony has *reached*: a bar whose downbeat is
    # before the first chord change has no note there at all, and its anchor is the
    # first position that does state one.
    stated_bar: Optional[int] = None
    for index, (bar, beat) in enumerate(walked):
        if harmonies[index] is None:
            is_anchor.append(False)
            continue
        strong = metric_weight(bar, beat, beats_per_bar, grouping) > 0
        first_in_bar = stated_bar != bar
        anchor = first_in_bar or (strong and keys[index] != previous_anchor)
        is_anchor.append(anchor)
        if anchor:
            previous_anchor = keys[index]
        stated_bar = bar
    return is_anchor


def _next_anchor_pitches(
    walked: Sequence[Tuple[int, float]],
    harmonies: Sequence[Optional[_Harmony]],
    is_anchor: Sequence[bool],
) -> List[Optional[int]]:
    """The next anchor's pitch class after each beat, by a backwards scan.

    This backwards pass is the lookahead: `approach` and `enclosure` are chosen
    against a note that has not been emitted yet.
    """
    next_anchor: List[Optional[int]] = [None] * len(walked)
    upcoming: Optional[int] = None
    for index in range(len(walked) - 1, -1, -1):
        next_anchor[index] = upcoming
        harmony = harmonies[index]
        if is_anchor[index] and harmony is not None:
            upcoming = harmony[0]
    return next_anchor


def _walk_note(
    permitted: Tuple[int, ...],
    root_pc: int,
    anchor_pc: Optional[int],
    previous_pc: Optional[int],
    beat: float,
    positions: Sequence[float],
) -> Tuple[int, str]:
    """The candidate set for one non-anchor beat, and the cost's choice from it.

    The order of `candidates` is load-bearing: `min` returns the first of equal
    costs, so this is where the tie-break lives.

    `positions` are the bar's **walked** positions - its felt beats on the full
    grid, so the last two are the dotted-quarter pulses of a 12/8 bar rather than
    its last two eighths; and on a sparse rhythm they are the positions the caller
    asked for, so the last note of a `--bass-on 1,3` bar is the approach to the next
    bar's anchor rather than an untouched connective note.
    """
    is_last_beat = abs(beat - positions[-1]) <= BEAT_EPSILON
    is_penultimate = len(positions) > 1 and abs(beat - positions[-2]) <= BEAT_EPSILON

    candidates: List[Tuple[int, str]] = [
        (pitch_class, BASS_ROLE_CONNECT) for pitch_class in permitted
    ]
    if previous_pc is not None:
        candidates.append((previous_pc, BASS_ROLE_HOLD))
    if anchor_pc is not None:
        # A chromatic approach to the next root. This is how a connective note
        # reaches a pitch that is neither a chord tone nor a nameable extension,
        # and it is a large part of why the walk needs no key model: the
        # "diatonic" movement of a real line (G-A-Bb) is extensions of the chord
        # it sits under, and the one genuinely chromatic note is exactly this.
        candidates.append(((anchor_pc + 1) % 12, BASS_ROLE_CONNECT))
        candidates.append(((anchor_pc - 1) % 12, BASS_ROLE_CONNECT))
        candidates.append(((anchor_pc + 7) % 12, BASS_ROLE_CONNECT))
        if is_last_beat:
            # The approach role is offered the half step above, the half step
            # below and the fourth below / fifth above, and `bass_cost` ranks a
            # half step first. Nothing here decides the note; the cost does, so
            # the same rule holds whichever chord is on either side.
            candidates.append(((anchor_pc + 1) % 12, BASS_ROLE_APPROACH))
            candidates.append(((anchor_pc - 1) % 12, BASS_ROLE_APPROACH))
            candidates.append(((anchor_pc + 7) % 12, BASS_ROLE_APPROACH))
        elif is_penultimate:
            # Half step above the next anchor, so the beat after it can take the
            # half step below: the simplest form of an enclosure, and the only
            # one in scope.
            candidates.append(((anchor_pc + 1) % 12, BASS_ROLE_ENCLOSURE))

    return min(
        candidates,
        key=lambda candidate: bass_cost(
            candidate[0], candidate[1], previous_pc, anchor_pc, root_pc, permitted
        ),
    )


def _walking_bass_line(
    # `Sequence` rather than `List`, for the reason `bass_line_for` gives: invariance
    # would reject a caller whose chords are a narrower tuple type than this signature
    # declares, which means the same thing and is what `walking_slots` builds.
    chords: Sequence[Tuple[Optional[str], str, str]],
    onsets: Optional[Sequence[Optional[Tuple[int, float]]]],
    beats_per_bar: int = 4,
    grouping: Optional[Sequence[int]] = None,
    rhythm: Optional[Rhythm] = None,
    first_full_bar: Optional[int] = None,
) -> List[BassNote]:
    """
    The bass line for a progression: one `BassNote` per **walked beat**.

    A pure, phrase-level pass. It reads harmony and timing only, never the melody
    pitches, because *what note to play* is a harmonic question and *where to play
    it* is a physical one - and only the second depends on the upper voicing, which
    does not exist yet at this point in the pipeline.

    The governing rule: **beat 1 is the anchor, the last beat is the target.** A
    walking line does two jobs, marking time and bridging one chord to the next, and
    they fall on predictable beats:

      anchor    the current chord's root, on every downbeat *and* on any strong beat
                where the harmony changes - bar 10's mid-bar `Eb7` gets its root
                there, on the same slot where the left hand states the chord
      connect   the beats in between: a chord tone, a nameable extension, or a
                chromatic approach
      approach  the last beat of the bar, chosen **backwards** from the next anchor.
                This is the strongest argument for the pass being phrase-level: beat
                4 is defined by a note that has not happened yet, so it cannot be
                generated per step.
      enclosure the beat before an approach, a half step above the next anchor
      hold      the previous note, when nothing else is reachable

    A chord lasting two bars is re-anchored on the second downbeat, because the
    anchor is a **metric** event, not a harmonic one: re-striking the root is what
    marks the bar, and suppressing it would leave that bar unmarked.

    `onsets=None` - `timings=None`, or a `chords` skeleton - means there is no beat
    grid, so there is nothing to walk four quarters across. It degrades to one note
    per slot, every slot an anchor, rather than failing. This is documented rather
    than silent because it is the path every hand-written progression takes.
    """
    if not chords:
        return []

    walked, harmonies, keys = _walked_harmony(
        chords, onsets, beats_per_bar, grouping, rhythm, first_full_bar
    )
    if not walked:
        return _anchor_only_line(chords)

    is_anchor = _anchor_flags(walked, harmonies, keys, beats_per_bar, grouping)
    next_anchor = _next_anchor_pitches(walked, harmonies, is_anchor)
    # The walked positions of each bar, which is what "the last note of the bar"
    # means to `_walk_note`. On the full grid these are the bar's felt beats.
    in_bar: Dict[int, List[float]] = {}
    for bar, beat in walked:
        in_bar.setdefault(bar, []).append(beat)
    return _walk_notes(walked, harmonies, is_anchor, next_anchor, in_bar)


def _walk_notes(
    walked: Sequence[Tuple[int, float]],
    harmonies: Sequence[Optional[_Harmony]],
    is_anchor: Sequence[bool],
    next_anchor: Sequence[Optional[int]],
    in_bar: Dict[int, List[float]],
) -> List[BassNote]:
    """One note per walked position: the anchor's root, or `_walk_note`'s choice.

    Split from `_walking_bass_line` because the setup and the emission are two jobs -
    one reads the harmony timeline, the other picks a pitch - and the two are chunked
    by different facts (bars and chords versus the notes around one position).
    """
    notes: List[BassNote] = []
    previous_pc: Optional[int] = None
    for index, (bar, beat) in enumerate(walked):
        harmony = harmonies[index]
        if harmony is None:
            continue
        root_pc, permitted = harmony
        if is_anchor[index]:
            notes.append(BassNote(bar, beat, root_pc, BASS_ROLE_ANCHOR))
            previous_pc = root_pc
            continue
        best_pc, best_role = _walk_note(
            permitted,
            root_pc,
            next_anchor[index],
            previous_pc,
            beat,
            in_bar[bar],
        )
        notes.append(BassNote(bar, beat, best_pc, best_role))
        previous_pc = best_pc
    return notes


def _simple_bass_line(
    chords: Sequence[Tuple[Optional[str], str, str]],
    onsets: Optional[Sequence[Optional[Tuple[int, float]]]],
    beats_per_bar: int,
    grouping: Optional[Sequence[int]],
    rhythm: Optional[Rhythm],
    first_full_bar: Optional[int],
    alternate: bool,
) -> List[BassNote]:
    """The `root` and `root-5th` lines: one note at **every** walked position.

    A note rule is not a rhythm, so `--bass-notes root` on every requested position
    has to state *something* at each of them; the walk's vocabulary cannot, because it
    has no note for a position that is not an anchor. So the two simple rules build
    their own line, and the role says which case a note is: the root on the bar's
    first position marks the bar (`anchor`), and the root anywhere else is a `pedal` -
    the same pitch restated, which is what a pedal *is*.

    `alternate` is `root-5th`: the anchor takes the root and each following position
    takes the 5th, alternating with the root as the line goes. `BASS_DEGREES_6432`
    names the interval rather than this function spelling `7`, for the reason that
    table exists - the root's partner in the low register is one fact.

    The line reads the same `_walked_harmony` the walk does, so where the positions are
    and which chord is under each cannot differ between the two.
    """
    if not chords:
        return []
    walked, harmonies, keys = _walked_harmony(
        chords, onsets, beats_per_bar, grouping, rhythm, first_full_bar
    )
    if not walked:
        return _anchor_only_line(chords)
    is_anchor = _anchor_flags(walked, harmonies, keys, beats_per_bar, grouping)
    notes: List[BassNote] = []
    previous: Optional[int] = None
    for index, (bar, beat) in enumerate(walked):
        harmony = harmonies[index]
        if harmony is None:
            continue
        root_pc = harmony[0]
        fifth_pc = (root_pc + BASS_DEGREES_6432[1]) % 12
        if is_anchor[index]:
            pitch, role = root_pc, BASS_ROLE_ANCHOR
        elif alternate and previous != fifth_pc:
            pitch, role = fifth_pc, BASS_ROLE_FIFTH
        else:
            pitch, role = root_pc, BASS_ROLE_PEDAL
        notes.append(BassNote(bar, beat, pitch, role))
        previous = pitch
    return notes


def _simple_style(rules: Sequence[str]) -> bool:
    """Whether these rules ask for a simple line rather than the walk.

    Derived from the rules rather than listed: `root` and `root-5th` name no
    connective rule, so what they ask for is the root (and the 5th) at the positions
    the rhythm names. A style naming `approach` or `nearest` is the walk, and is
    filtered by role exactly as it always was.
    """
    return BASS_RULE_ROOT in rules and not (
        {BASS_RULE_APPROACH, BASS_RULE_NEAREST} & set(rules)
    )


def bass_line_for(
    bass: str,
    # `Sequence`, not `List`, for the reason `walking_slots` gives in full: `List` is
    # invariant, so a caller holding a `List[Tuple[str, str, str]]` is not assignable
    # to a `List[Tuple[Optional[str], str]]` and pyright rejects it over a *narrower*
    # type that means the same thing. `Sequence` is covariant and both fit.
    chords: Sequence[Tuple[Optional[str], str, str]],
    onsets: Optional[Sequence[Optional[Tuple[int, float]]]],
    beats_per_bar: int = 4,
    grouping: Optional[Sequence[int]] = None,
    rhythm: Optional[Rhythm] = None,
    first_full_bar: Optional[int] = None,
) -> List[BassNote]:
    """The bass line for one style: `_walking_bass_line`, filtered by the roles its rules admit.

    This is the seam a new note rule goes through. `none` returns nothing and is never
    called with a grid to build - `arrange_progression` skips the union entirely - so it
    is answered here too rather than by a caller-side `if`, which keeps the "which styles
    produce a line" question in one place.

    A style names an ordered list of note rules (`parse_bass_style` owns the vocabulary);
    the roles those rules admit come from `BASS_RULE_ROLES`, and the walked line keeps a
    note when its role is admitted by **any** named rule. The full
    `root,5th,approach,nearest` is the walk (a note at every position). The harmonic
    reasoning - what a walking note is *for* - is written once in `_walking_bass_line`
    and every connective style inherits it; a sparser style is sparser and nothing else.

    `root` and `root-5th` are **not** the walk filtered, when a rhythm was named: they
    ask for one note at every position the rhythm names, which the walk's vocabulary has
    no role for, so `_simple_bass_line` builds them. With **no** rhythm - the `bass`
    axis, which is the engine's own spelling - `root` keeps its documented anchors-only
    meaning: there, the polyphony *is* the grid's, and the walk's own beats are the
    metre's felt beats rather than a caller's positions.

    A style naming a rule with no entry in `BASS_RULE_ROLES` raises rather than
    defaulting, on the same rule the rest of the library follows: a spelling nobody
    recognises is a question, and answering it by guessing is how a wrong note gets in.
    """
    if bass == BASS_STYLE_NONE:
        return []
    rules = parse_bass_style(bass)
    named_positions = rhythm is not None and not rhythm.is_none
    if named_positions and _simple_style(rules):
        return _simple_bass_line(
            chords,
            onsets,
            beats_per_bar,
            grouping,
            rhythm,
            first_full_bar,
            alternate=BASS_RULE_5TH in rules,
        )
    admitted: FrozenSet[str] = frozenset()
    for rule in rules:
        try:
            admitted |= BASS_RULE_ROLES[rule]
        except KeyError:  # pragma: no cover - the parser refuses unknown rules first
            raise ValueError(
                f"Unknown bass rule {rule!r}; expected any of {BASS_RULES}"
            ) from None
    line = _walking_bass_line(
        chords, onsets, beats_per_bar, grouping, rhythm, first_full_bar
    )
    return [note for note in line if note.role in admitted]

