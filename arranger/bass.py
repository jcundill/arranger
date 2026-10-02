"""The walking bass: a thumb line on the three lowest strings.

Three passes, in this order, and the order is the design:

1. `_walking_bass_line` reads **harmony only** and returns one `BassNote` per
   walked beat, each a *pitch class*. It cannot know the octave or the string,
   because it runs before any upper voicing exists.
2. `_walking_slots` unions those beats with the melody grid into one `_Slot`
   list, built **before** the melody loop, so the loop's index still indexes the
   skeleton it was given.
3. `_place_bass` resolves the octave and the string together, after selection,
   because a note an octave away is a different fret on every string.

`bass_cost` is here rather than in `cost.py` because it ranks over the
`BASS_ROLE_*` constants below and is called by `_walking_bass_line`; in `cost` it
would need this module and this module would need `cost`.

**One slot union, built once.** Both step loops reach `_walking_slots` -
`VoiceLeadingEngine.arrange_progression` and `wjazzd.arrange_slots` - because a
second copy is exactly the failure this library documents having had once already:
the corpus path was built separately, drifted, and voiced an `Am7` under a
written `Bbm7` for twenty-five transcriptions before anyone noticed. Walking bass
is the same trap with the same stakes, since a path that arranged the shells but
not the walk would look plausible and be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from musthe import Note

from .chords import NON_CHORD_TONE_EXTENSIONS, ChordParser, normalised_harmony
from .textures import _BEAT_EPSILON, _metric_weight
from .tuning import STANDARD_TUNING, ArrangementStep, Voicing

# --- Walking bass ---
#
# The three strings a thumb line may use: the low E, the A and the D. All three are in
# play, and which one carries a given note is decided *per note* rather than fixed.
#
# The reason is that the thumb is part of the hand. Adjacent strings are five semitones
# apart, so the same pitch sits five frets lower on each string you move up - D3 is fret
# 10 on the low E, fret 5 on the A, and the open D string itself - which puts "prefer the
# lowest string" and "stay where the hand already is" in direct opposition, always, by
# exactly five frets. A hand sitting at fret 5 plays D3 on the A string under the
# position it is already in; on the low E the same D3 is five frets of travel for an
# identical pitch.
#
# So the placement step orders by fret proximity to the upper voicing and takes the
# nearest, the same economy `voicing_cost` already applies to the upper voices. The 4th
# string is therefore used only when the hand is genuinely low, and the 6th only when the
# note is below the A string's open A2 or when the A and the D are both occupied by the
# upper shape - the two cases the upper strings cannot cover.
BASS_STRING_INDICES: Tuple[int, ...] = (0, 1, 2)

# The roles a walking-bass note may take, for annotation and tests. Plain strings rather
# than an enum, for the same reason `grip` and `role` are: the module has no `enum`
# import and pyright must stay clean.
#
# "target" is deliberately **not** reused for beat 4, because that word already means the
# *left hand's* principal note (ROLE_TARGET) and one word cannot carry both:
#
#   anchor    beat 1, or any strong beat where the harmony changes: the root, always
#   connect   beats 2 and 3: a chord tone, an extension, or passing motion
#   approach  beat 4: a half step from the next bar's anchor
#   enclosure beat 3 or 4: half step above, then half step below the next anchor
#   hold      any beat: the previous note repeated, when nothing better is reachable
BASS_ROLE_ANCHOR = "anchor"
BASS_ROLE_CONNECT = "connect"
BASS_ROLE_APPROACH = "approach"
BASS_ROLE_ENCLOSURE = "enclosure"
BASS_ROLE_HOLD = "hold"


@dataclass
class BassNote:
    """
    One walked beat of a bass line: where it falls, what note it is, and why.

    The note is a **pitch class**, not a pitch, and that is load-bearing rather than
    a simplification. This pass runs before the melody loop, so before any upper
    voicing exists, and neither the octave nor the string can be known then: a
    descending C4-B3-A3-G3 under a held Dm7 is a beautiful walk and completely
    unplayable under a shell at fret 5, because C4 is fret 15 on the 5th string.
    The same line an octave down is not. Only the placement step, which can see
    `hand_fret`, resolves the octave and the string together.

    This is the split the library already draws for the melody: the pitch is
    musical, the string and the position are physical, and they are not decided in
    the same place.

    One entry per **walked beat**, not per melody slot - the bass grid is finer than
    the melody grid, which is what lets a held whole note sound one melody note over
    four thumb notes.
    """

    bar: Optional[int]
    beat: Optional[float]
    # Pitch class 0-11. The octave and the string are the placement step's business.
    pitch_class: int
    # One of the BASS_ROLE_* constants: what this note is *for*.
    role: str



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


def _bass_distance(first: int, second: int) -> int:
    """How far apart two pitch classes are, in semitones, the short way round."""
    return min((first - second) % 12, (second - first) % 12)


def bass_cost(
    pitch_class: int,
    role: str,
    previous_pc: Optional[int],
    next_anchor_pc: Optional[int],
    root_pc: Optional[int],
    permitted_pcs: Tuple[int, ...],
) -> Tuple[int, ...]:
    """
    The selection rule for one walking-bass candidate, as one comparable tuple.

    Lexicographic, never a weighted sum, matching the house rule `voicing_cost`
    states why it must be - and **role-conditional**, so the tuple is built per role
    rather than shared. That is the substantive rule here: being outside the chord is
    a *hard filter* for the anchor and a mere tie-break for a connective note, and no
    single ordering of criteria can say both at once.

      anchor    not-the-root. A hard filter, not a preference: the lowest voice
                defines the chord, which is the argument `BASS_DEGREES_6432` already
                makes for a 6-4-3-2 shape.
      approach  how far the note is from the next anchor, then motion from the
                previous note. A half step outranks a fourth below / fifth above.
      connect   out of the permitted set, then motion from the previous note, then a
                preference for stepwise motion
      enclosure as `connect`, for the note a half step *above* the next anchor
      hold      always last: the previous note, when nothing better is reachable

    The role rank comes first, which is what makes `hold` genuinely last rather than
    a peer of the alternatives.

    Note what is **not** in any of these: anything about the hand, the octave or the
    string. All three are physical, all three are decided in the placement step, and
    none of them is knowable here. An earlier draft of the design carried a
    "distance from the ideal octave of the previous note" term in exactly this tuple,
    which quietly re-decided the octave in the wrong place - a descending line would
    have committed to C4 before anything knew the hand was at fret 5.
    """
    motion = 0 if previous_pc is None else _bass_distance(pitch_class, previous_pc)
    out_of_chord = 0 if pitch_class in permitted_pcs else 1

    if role == BASS_ROLE_ANCHOR:
        return (0, 0 if pitch_class == root_pc else 1, 0, 0, 0, pitch_class)

    if role == BASS_ROLE_APPROACH:
        if next_anchor_pc is None:
            reach = 2
        else:
            interval = _bass_distance(pitch_class, next_anchor_pc)
            reach = 0 if interval == 1 else (1 if interval == 5 else 2)
        # `motion == 0` is penalised for the same reason it is on a connect: a
        # beat-4 note that merely repeats beat 3 has not approached anything, and
        # an enclosure whose two halves are the same pitch is not an enclosure.
        return (0, reach, 1 if motion == 0 else 0, motion, out_of_chord, 0, pitch_class)

    if role == BASS_ROLE_ENCLOSURE:
        # Ranked with the approach rather than the connects, because it is a
        # *deliberate* shape: the beat above the next anchor, to be answered by the
        # half step below it. It is only ever offered on the beat before an
        # approach, so ranking it with the connects would mean it was reachable
        # only by accident.
        return (0, out_of_chord, motion, 0, 0, pitch_class)

    if role == BASS_ROLE_HOLD:
        return (2, 0, 0, 0, 0, pitch_class)

    # connect. Three elements here are what make a walk a walk. `motion == 0` is
    # ranked ahead of everything, so a bar of four beats under one chord comes out a
    # line rather than a held note - without it, zero motion would win on every beat.
    # Motion itself is the *first* musical criterion, which is what makes being
    # outside the permitted set a tie-break rather than a veto: the design is
    # explicit that "out-of-chord tones" is not the first criterion of this role, and
    # ranking it first would make the chromatic-approach candidates dead code - they
    # could never beat a chord tone at any distance. And on a tie in distance the
    # line prefers to *rise*, because a walk ascends towards its next anchor; without
    # it a bar under a single chord oscillates between two chord tones (D-C-D-C),
    # which is a held figure wearing a walk's clothes.
    return (1, 1 if motion == 0 else 0, motion, out_of_chord,
            0 if motion <= 2 else 1,
            0 if previous_pc is not None and pitch_class > previous_pc else 1,
            0, pitch_class)


def _previous_bass(arrangements: List[ArrangementStep]) -> Optional[int]:
    """
    The most recent thumb note placed, or None at the head of the phrase.

    Scans backwards for the first step that actually carries a bass rather than the
    first that was *offered* one: the two differ as soon as a walk note cannot be
    placed, and continuing from a note that never sounded would drag the line towards
    an octave it was not in.
    """
    for step in reversed(arrangements):
        if step.bass is not None:
            return step.bass
    return None


def _held_shape(
    arrangements: List[ArrangementStep],
) -> Optional[Tuple[List[int], Optional[int]]]:
    """The shape the left hand is still holding, and which of its strings the thumb
    last played, or None when nothing has been struck yet.

    A `bass_only` step re-states nothing above the thumb - the upper voices are held
    from the last **struck** step - so the shape that is physically still down there is
    the previous strike's, not this step's own thinned vector. This is the same rule
    `tabgp._build_song` threads as `ringing`, and it is here for the same reason: both
    need to know what the hand is holding rather than what the current step carries.

    The thumb's string comes back too, because that note is **not** part of the shape
    the fingers are holding - see `_place_bass`. Identifying it by string rather than by
    pitch is what makes that exclusion exact: the thumb moves between beats, so the
    note it played two beats ago is not the one in the shape now being held.

    A `repeated` step is excluded for the reason it strikes only its soprano: taking
    its one-fret vector would erase the shape for every thumb note after it.
    """
    for step in reversed(arrangements):
        if step.bass_only or step.repeated or step.melody_only:
            continue
        return list(step.voicing.frets), step.voicing.bass_string
    return None


def _place_bass(
    upper: Voicing,
    pitch_class: int,
    previous_bass: Optional[int] = None,
    held: Optional[Tuple[Sequence[int], Optional[int]]] = None,
) -> Optional[Tuple[int, int, int]]:
    """
    Resolves one thumb note's octave and string against an upper voicing.

    Returns `(midi, string_index, fret)`, or None when no candidate survives. The
    pure pass returned a pitch *class* because neither the octave nor the string can
    be decided before the upper shape exists; this is where they are decided, together
    and in that order, because a note an octave away is a different fret on every
    string.

    `held` is the shape still ringing under a `bass_only` step - see `_held_shape`.
    It matters for **three** of the questions below at once, and passing it is the
    fix for the unplayable walking bass in `docs/open-issues.md` item 1. A `bass_only`
    step's own vector holds only the melody, so measuring against it alone gets all
    three wrong: the thumb is placed on a string the hand is already fingering, it is
    allowed to sound *above* the held shape's bottom note, and its proximity is
    measured from a fret the hand is not at. On "But Not For Me" bar 5 that put the
    thumb on the D string at fret 1 while the hand held frets 6-8 - a seven-fret
    stretch that no per-step span check can see, because every individual step is
    tidy.

    The rule is proximity, not string order. The thumb is part of the hand, and
    adjacent strings are five semitones apart, so "play the lowest string" and "stay
    where the fingers already are" differ by exactly five frets on every note. A hand
    at fret 5 plays D3 on the A string under itself; on the low E the same D3 is fret
    10 and the hand moves for an identical pitch. So the survivors are ranked by
    `abs(fret - hand_fret)` and the nearest wins.

    `hand_fret` is the **lowest active fret of the shape the hand is holding** - the
    held one where there is one, otherwise the upper voicing's. Not `avg_fret` and
    not `top_fret`. That is the measured choice: over the plan's own worked example,
    measuring to the lowest active fret matches 26 of the 28 readable bass notes
    against 24 for the average, because a shell's low voice is the note the thumb is
    trying to join. `avg_fret` and `top_fret` agree with each other on every one of
    those notes, so neither is contradicted by the evidence - the average is simply
    dragged up by the melody, which is up an octave from the position the hand is in.

    Three filters are **not** tie-breaks, because each rejects candidates that would
    be wrong rather than merely further away:

    - the string must not already sound, in the upper voicing **or in the held
      shape** - one string cannot play two frets at once, and this is the same
      collision that made the GP5 export write a tie resolving to the wrong pitch;
    - the note must sound below both, for the same reason. This is required rather
      than preferred because the tuning is not monotonic in the useful direction -
      the A string is five semitones *above* the D string it may neighbour, and a
      5-3-2 shell's A-string note can sound below its G-string note - so a candidate
      can be reachable, can be at the hand, and still belong above the chord it is
      meant to support.

    Reach (`0..18`) is a fourth, separate test: `note_to_fret` returning a fret says
    the pitch is playable and says nothing at all about where it lands.

    With no survivor the caller leaves the step without a bass and reports it, which
    is the "penalty, never a filter" argument the neck window already makes: a step
    is never dropped because the thumb could not reach it.
    """
    upper_midis = upper.midi_notes()
    if not upper_midis:
        return None
    lowest_upper = min(upper_midis)
    active = upper.active_frets()
    if not active:
        return None
    hand_fret = float(min(active))

    # The held shape widens "is this string free" and "what is the lowest note
    # sounding", and supplies the hand position, because the melody alone is up an
    # octave from where the fingers are.
    #
    # One note in the held vector is *not* structure: the thumb's own previous note.
    # A target folds the thumb into its fret vector, so the shape being held already
    # carries the last bass note, and treating it as a voice to stay beneath and not
    # share a string with would forbid every repeated and ascending walk note - a
    # walking bass is mostly repeated and ascending notes. It is excluded by pitch,
    # which is unambiguous, and the hand position still counts it: the thumb is part
    # of the hand whatever it last played.
    sounding_frets = list(upper.frets)
    if held is not None:
        held_frets, held_thumb = held
        structure = [
            -1 if index == held_thumb else fret
            for index, fret in enumerate(held_frets)
        ]
        structure_midis = [
            STANDARD_TUNING[index].midi_note() + fret
            for index, fret in enumerate(structure)
            if 0 <= index < len(STANDARD_TUNING) and fret >= 0
        ]
        if structure_midis:
            lowest_upper = min(lowest_upper, min(structure_midis))
        held_active = [fret for fret in held_frets if fret >= 0]
        if held_active:
            hand_fret = float(min(held_active))
        sounding_frets = [
            upper.frets[index] if upper.frets[index] >= 0 else (
                structure[index] if index < len(structure) else -1
            )
            for index in range(len(upper.frets))
        ]

    best: Optional[Tuple[Tuple[float, int, int], Tuple[int, int, int]]] = None
    for string_index in BASS_STRING_INDICES:
        if 0 <= string_index < len(sounding_frets) and sounding_frets[string_index] >= 0:
            continue  # the upper shape already speaks on this string
        open_midi = STANDARD_TUNING[string_index].midi_note()
        # Every fret on this string that sounds the wanted pitch class: the class
        # recurs every octave, so the candidates are a fixed offset plus twelves.
        first = (pitch_class - open_midi) % 12
        for fret in range(first, 19, 12):
            midi = open_midi + fret
            if midi >= lowest_upper:
                continue  # the thumb must sound below the structure it supports
            # Nearest the hand first; then continuity with the previous thumb note,
            # so a line does not leap octaves for no reason; then the lower pitch.
            key = (
                abs(float(fret) - hand_fret),
                0 if previous_bass is None or abs(midi - previous_bass) <= 4 else 1,
                midi,
            )
            candidate = (key, (midi, string_index, fret))
            if best is None or candidate[0] < best[0]:
                best = candidate
    return None if best is None else best[1]


@dataclass
class _Slot:
    """
    One entry of the slot list `arrange_progression` actually loops over.

    For `uniform` and `targets` this is exactly one slot per progression triple and
    the three timing fields are read off `timings` with the guard the corpus loader
    already applies. It exists as a type rather than a tuple because under
    `walking_bass` the list is the **union** of the melody slots and the walked
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


def _walking_slots(
    progression: List[Tuple[str, str, str]],
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
) -> List[_Slot]:
    """
    The walking-bass slot union: the melody grid plus the walked beats.

    **The one place the union is built.** Both step loops reach it -
    `VoiceLeadingEngine.arrange_progression` and `wjazzd.arrange_slots` - because a
    second copy is exactly the failure this module documents having had once already:
    the corpus path was built separately, drifted from the library, and shipped a
    voiced `Am7` under a written `Bbm7` for twenty-five transcriptions before anyone
    noticed. Walking bass is the same trap with the same stakes, since it is the
    texture whose whole output is the thumb line: a path that arranged the shells but
    not the walk would look plausible and be wrong.

    Reads harmony only, never the melody pitches - the melody is read when the slot is
    voiced, and a slot's `index` says which melody is sounding under it. That is what
    lets the walked beats be discovered before any voicing exists.

    With `timings=None` there is no beat grid to place four quarters on, so this
    degrades to one note per slot: the documented gridless case.
    """
    chords: List[Tuple[Optional[str], str, str]] = []
    for _note, _quality, name in progression:
        root, quality = ChordParser.parse_chord_name(name)
        chords.append((root, quality or "", name))

    onsets: List[Optional[Tuple[int, float]]] = []
    for index in range(len(progression)):
        timing = timings[index] if timings is not None and index < len(timings) else None
        bar = timing[0] if timing is not None else None
        beat = timing[1] if timing is not None else None
        # A slot with no beat has no place on the grid, which is what the walk needs
        # to know: an onset it cannot locate is a beat it does not invent one for.
        onsets.append(
            (bar, float(beat)) if bar is not None and beat is not None else None
        )

    bass_line = _walking_bass_line(chords, onsets, beats_per_bar)
    return _bass_slots(progression, timings, bass_line)


def _bass_slots(
    progression: List[Tuple[str, str, str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    bass_line: List[BassNote],
) -> List[_Slot]:
    """
    The union of the melody grid and the walked beats, as one ordered slot list.

    Decision B: the bass grid may be **finer** than the melody grid, because a bar
    whose melody is a single whole note still has four beats to walk. Every walked
    beat that has no melody slot becomes an extra slot carrying the previous melody
    pitch, marked `bass_only` - the renderer holds the upper voices across it and
    strikes only the thumb.

    `timings` is `(bar, beat, duration)` per slot and a slot the caller never located
    arrives as `(None, None, None)`: the corpus path supplies no timings at all, and
    the head path supplies them for every note but not for the rests it skips. Such a
    slot is skipped here, exactly as `arrange_slots` skips it - an unlocated slot has
    no place on a grid, and inventing one would be the "a count without a denominator
    is not a metre" mistake wearing a different hat.

    Two properties are load-bearing and both are about ordering:

    - the union is built **before** the melody loop, so the loop's index still means
      what it meant - `arrange_head`'s timings guard and `arrange_slots`' retry index
      index into the skeleton, not into the result;
    - an extra slot's `index` is the *previous* melody slot, so the melody it carries
      is the one actually sounding, and the harmonic timeline the walk reads is
      unchanged by the union itself.

    With no usable timing there is no beat grid to union against, and the gridless
    degradation stands: one thumb note per anchor, one per slot. That is the
    documented `timings=None` case, not a failure.
    """
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

    if not located:
        # Gridless: one note per slot, attached by position and guarded, because the
        # bass line can be shorter than the progression when a chord is unparseable.
        slots: List[_Slot] = []
        for index in range(len(progression)):
            slots.append(_Slot(
                index=index,
                bass=bass_line[index] if index < len(bass_line) else None,
            ))
        return slots

    melody_at: Dict[Tuple[int, float], Tuple[int, Optional[float]]] = {
        (bar, float(beat)): (index, duration) for index, bar, beat, duration in located
    }

    entries: List[Tuple[Tuple[int, float], int, Optional[BassNote], bool]] = []
    for index, bar, beat, _duration in located:
        key = (bar, float(beat))
        bass = next((note for note in bass_line
                     if note.bar == bar and note.beat is not None
                     and abs(note.beat - float(beat)) <= _BEAT_EPSILON), None)
        entries.append((key, index, bass, False))

    # The walked beats with no melody slot. Ordered by onset, and each takes the
    # melody slot in force before it - which is why the nearest preceding slot is
    # found rather than "the previous index".
    previous_melody = -1
    for note in bass_line:
        if note.bar is None or note.beat is None:
            continue
        key = (note.bar, float(note.beat))
        if key in melody_at:
            previous_melody = melody_at[key][0]
            continue
        entries.append((key, previous_melody if previous_melody >= 0 else 0, note, True))

    # Sort by onset, with a melody slot ahead of a bass-only slot on the same onset
    # so the step that strikes the melody is the step that carries that walk note.
    entries.sort(key=lambda entry: (entry[0][0], entry[0][1], entry[3], entry[1]))

    slots = []
    for key, index, bass, bass_only in entries:
        duration = melody_at.get(key, (index, None))[1]
        slots.append(_Slot(
            index=index,
            bar=key[0],
            beat=key[1],
            duration=duration,
            bass=bass,
            bass_only=bass_only,
        ))
    return slots


def _walking_bass_line(
    chords: List[Tuple[Optional[str], str, str]],
    onsets: Optional[List[Optional[Tuple[int, float]]]],
    beats_per_bar: int = 4,
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
    marks the bar, and suppressing it would leave that bar unmarked. An earlier draft
    of the design held the opposite, and was wrong.

    `onsets=None` - `timings=None`, or a `chords` skeleton - means there is no beat
    grid, so there is nothing to walk four quarters across. It degrades to one note
    per slot, every slot an anchor, rather than failing. This is documented rather
    than silent because it is the path every hand-written progression takes.
    """
    if not chords:
        return []

    located = (
        [
            (onset[0], onset[1], index)
            for index, onset in enumerate(onsets)
            if onset is not None
        ]
        if onsets is not None
        else []
    )

    if not located:
        # No beat grid: one note per slot, and every slot is an anchor.
        notes: List[BassNote] = []
        for root, quality, _name in chords:
            harmony = _bass_harmony(root, quality)
            if harmony is None:
                continue
            notes.append(BassNote(None, None, harmony[0], BASS_ROLE_ANCHOR))
        return notes

    # One walked beat per quarter of every bar the melody touches. Signed bars sort
    # correctly, and a bar whose melody is a single whole note still yields four
    # notes - the grid, not the melody, is what the line is written on.
    bars = sorted({bar for bar, _beat, _index in located})
    walked: List[Tuple[int, float]] = [
        (bar, float(beat)) for bar in bars for beat in range(1, beats_per_bar + 1)
    ]

    # The harmony in force at each walked beat, by forward fill on the (bar, beat)
    # tuple - the same rule the corpus loader and the MusicXML importer apply, and
    # the same one the left hand reads. An `NC` bar continues the last known harmony
    # rather than being given a guessed one, and a bar with no harmony behind it yet
    # gets no notes at all.
    onsets_sorted = sorted(located)
    harmonies: List[Optional[Tuple[int, Tuple[int, ...]]]] = []
    keys: List[Optional[Tuple[Optional[str], Optional[str]]]] = []
    cursor = 0
    carried: Optional[Tuple[int, Tuple[int, ...]]] = None
    carried_key: Optional[Tuple[Optional[str], Optional[str]]] = None
    for bar, beat in walked:
        while (
            cursor < len(onsets_sorted)
            and (onsets_sorted[cursor][0], onsets_sorted[cursor][1]) <= (bar, beat)
        ):
            root, quality, _name = chords[min(onsets_sorted[cursor][2], len(chords) - 1)]
            parsed = _bass_harmony(root, quality)
            if parsed is not None:
                carried = parsed
                carried_key = normalised_harmony(f"{root}{quality}")
            # Otherwise the slot is NC or unspeakable, and `carried` holds unchanged.
            cursor += 1
        harmonies.append(carried)
        keys.append(carried_key)

    # An anchor is every downbeat, plus any strong beat whose harmony is not already
    # stated. The second clause is the mid-bar change, and it is the *same* predicate
    # `_roles_for_slot` already applies to the left hand - strong beat, and a harmony
    # differing from the previous target's - so the thumb and the fingers fire on one
    # slot by construction rather than by a second mechanism kept in step by hand.
    is_anchor: List[bool] = []
    previous_anchor: Optional[Tuple[Optional[str], Optional[str]]] = None
    for index, (bar, beat) in enumerate(walked):
        if harmonies[index] is None:
            is_anchor.append(False)
            continue
        strong = _metric_weight(bar, beat, beats_per_bar) > 0
        downbeat = abs(beat - 1.0) <= _BEAT_EPSILON
        anchor = downbeat or (strong and keys[index] != previous_anchor)
        is_anchor.append(anchor)
        if anchor:
            previous_anchor = keys[index]

    # The next anchor after each walked beat, which is what `approach` and
    # `enclosure` are chosen *against*. This backwards scan is the lookahead.
    next_anchor: List[Optional[int]] = [None] * len(walked)
    upcoming: Optional[int] = None
    for index in range(len(walked) - 1, -1, -1):
        next_anchor[index] = upcoming
        harmony = harmonies[index]
        if is_anchor[index] and harmony is not None:
            upcoming = harmony[0]

    # One note per walked beat, with the previous note carried forward so the cost
    # can measure motion. `previous_pc` is the only state the pass keeps, which is
    # what makes a single forward pass enough: the lookahead is already resolved
    # above, into `next_anchor`.
    notes = []
    previous_pc: Optional[int] = None
    for index, (bar, beat) in enumerate(walked):
        harmony = harmonies[index]
        if harmony is None:
            # No harmony has sounded yet: nothing to anchor and nothing to walk
            # under. Skipping rather than guessing is the rule this module keeps
            # everywhere else.
            continue
        root_pc, permitted = harmony
        anchor_pc = next_anchor[index]
        if is_anchor[index]:
            notes.append(BassNote(bar, beat, root_pc, BASS_ROLE_ANCHOR))
            previous_pc = root_pc
            continue

        is_last_beat = abs(beat - beats_per_bar) <= _BEAT_EPSILON
        is_penultimate = abs(beat - (beats_per_bar - 1)) <= _BEAT_EPSILON

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

        best_pc, best_role = min(
            candidates,
            key=lambda candidate: bass_cost(
                candidate[0], candidate[1], previous_pc, anchor_pc, root_pc, permitted
            ),
        )
        notes.append(BassNote(bar, beat, best_pc, best_role))
        previous_pc = best_pc

    return notes
