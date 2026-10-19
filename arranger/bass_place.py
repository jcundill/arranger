"""Where a walked pitch class becomes a fret: the thumb's octave and string.

The line itself is `bass`'s business - it runs harmony-only, before any upper voicing
exists. This module answers the physical half: `place_bass` resolves the octave and the
string together against the hand holding the shape, after selection, and `bass_cost`
ranks the line's candidates over the `BASS_ROLE_*` vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .bass_rules import (
    BASS_ROLE_ANCHOR,
    BASS_ROLE_APPROACH,
    BASS_ROLE_ENCLOSURE,
    BASS_ROLE_HOLD,
    BASS_STRING_INDICES,
)
from .fingers import can_fret
from .tuning import STANDARD_TUNING, ArrangementStep, Voicing


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
    a thumb note on every beat of the bar. That is four in 4/4 and two in 2/2, where
    the whole note is the whole bar; see `bass.walking_slots` for why the count is a
    property of the metre rather than a constant.
    """

    bar: Optional[int]
    beat: Optional[float]
    # Pitch class 0-11. The octave and the string are the placement step's business.
    pitch_class: int
    # One of the BASS_ROLE_* constants: what this note is *for*.
    role: str



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
    none of them is knowable here. An "ideal octave" term in this tuple would re-decide
    the octave in the wrong place: a descending line would commit to C4 before anything
    knew the hand was at fret 5.
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


def previous_bass(arrangements: List[ArrangementStep]) -> Optional[int]:
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


def held_shape(
    arrangements: List[ArrangementStep],
) -> Optional[Tuple[List[int], Optional[int]]]:
    """The shape the left hand is still holding, and which of its strings the thumb
    last played, or None when nothing has been struck yet.

    A `bass_only` step re-states nothing above the thumb - the upper voices are held
    from the last **struck** step - so the shape that is physically still down there is
    the previous strike's, not this step's own thinned vector. This is the same rule
    `tabgp._build_song` threads as `ringing`, and it is here for the same reason: both
    need to know what the hand is holding rather than what the current step carries.

    A `repeated` step is excluded for the same reason, and so is a **target**: the flag
    says what the left hand is doing, and a target re-states its harmony rather than
    holding a shape, so it never carries `bass_only` at all
    (`decisions.is_bass_only`).

    The thumb's string comes back too, because that note is **not** part of the shape
    the fingers are holding - see `place_bass`. Identifying it by string rather than by
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


def _thumb_frame(
    upper: Voicing,
    held: Optional[Tuple[Sequence[int], Optional[int]]],
) -> Optional[Tuple[int, List[int], List[int], float]]:
    """The geometry a thumb note is placed against.

    Returns the lowest note the thumb must sound below, the strings that already
    speak, the frets the fingers must cover, and the hand's position. None means
    the upper voicing sounds nothing, so there is no shape to place a bass under.
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
    # What the fingers must actually cover, which is **not** `sounding_frets`: see the
    # fret-budget filter in the loop below. Without a held shape the current voicing is
    # the shape, so the two start the same.
    hand_base = list(upper.frets)
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
        # The hand covers the **whole** held vector, including the note the thumb last
        # played: that string is still ringing, so it is still fretted. `structure` is the
        # base the three questions above need, because it excludes that note - right for
        # harmony, wrong for fingers. Measured on the committed heads the two readings give
        # the same answer, so this one is chosen on the physics rather than on a count.
        hand_base = list(held_frets)
    return lowest_upper, sounding_frets, hand_base, hand_fret


def _best_thumb_fret(
    pitch_class: int,
    previous_bass: Optional[int],
    lowest_upper: int,
    sounding_frets: Sequence[int],
    hand_base: Sequence[int],
    hand_fret: float,
) -> Optional[Tuple[int, int, int]]:
    """Every free string's octaves of `pitch_class`, filtered and ranked.

    The filters reject a placement that would be wrong; the key is the
    preference: nearest the hand, then continuity with the previous thumb note,
    then the lower pitch.
    """
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
            # Four fingers, four frets - and this loop is the one place a fifth can appear.
            # The hand is the shape still **ringing**, not this step's own vector and not
            # `sounding_frets`: under a `bass_only` step nothing above the thumb strikes at
            # all, so a melody carried on a string the held shape does not use is a note the
            # hand is not holding - it is already sounding elsewhere, which is the item-4
            # mistake made backwards. What the fingers cover is `hand_base` (the previous
            # strike, thumb note and all) with the thumb's own string replaced by the fret
            # chosen here. It is a filter rather than a preference because the alternative is
            # not a worse placement but an unplayable one, and `fingers.can_fret` is what
            # answers it.
            hand = list(hand_base)
            hand[string_index] = fret
            if not can_fret(hand):
                continue
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
def place_bass(
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

    `held` is the shape still ringing under a `bass_only` step - see `held_shape`.
    It matters for **four** of the questions below at once, and passing it is what keeps
    a `bass_only` step playable: that step's own vector holds only the
    melody, so measuring against it alone gets all
    four wrong - the thumb is placed on a string the hand is already fingering, it is
    allowed to sound *above* the held shape's bottom note, its proximity is measured
    from a fret the hand is not at, and its fret is counted as though it stood alone
    under the fingers rather than joining four frets already down. The first three are
    answered by measuring against the held shape rather than the thinned voicing; the
    fourth is a fifth fret for four fingers, and `fingers.can_fret` is what answers it.

    The rule is proximity, not string order. The thumb is part of the hand, and
    adjacent strings are five semitones apart, so "play the lowest string" and "stay
    where the fingers already are" differ by exactly five frets on every note. A hand
    at fret 5 plays D3 on the A string under itself; on the low E the same D3 is fret
    10 and the hand moves for an identical pitch. So the survivors are ranked by
    `abs(fret - hand_fret)` and the nearest wins.

    `hand_fret` is the **lowest active fret of the shape the hand is holding** - the
    held one where there is one, otherwise the upper voicing's. Not `avg_fret` and
    not `top_fret`, because a shell's low voice is the note the thumb is trying to
    join: ranking to the lowest active fret matches more of the readable bass notes than
    the average does, which is dragged up by the melody an octave above the position the
    hand is in.

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

    When **no** candidate survives, one of three things has happened, and the clause
    `annotation._bass_refusal_clause` phrases them all because none of them is visible from
    outside: no free string below the melody, **no octave of the wanted pitch below the
    shape's own lowest note**, or a fifth fret for four fingers. The middle clause is
    the common case; the counts are in `docs/open-issues.md` item 2, and the caller
    records the wanted pitch class on `ArrangementStep.bass_refused` rather than the
    reason, so the split is measured rather than read off the step.

    Reach (`0..18`) is a fourth, separate test: `note_to_fret` returning a fret says
    the pitch is playable and says nothing at all about where it lands.

    With no survivor the caller leaves the step without a bass and reports it, which
    is the "penalty, never a filter" argument the neck window already makes: a step
    is never dropped because the thumb could not reach it.
    """
    frame = _thumb_frame(upper, held)
    if frame is None:
        return None
    lowest_upper, sounding_frets, hand_base, hand_fret = frame
    return _best_thumb_fret(
        pitch_class, previous_bass, lowest_upper, sounding_frets, hand_base, hand_fret
    )

