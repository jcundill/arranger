"""The selection rule: which of the candidates is played.

`voicing_cost` is the library's central invariant. It is a **tuple**, compared
lexicographically, not a weighted sum, because the criteria are genuine
trade-offs that must not be traded against each other - "stay in position" is not
worth a semitone of inner-voice movement, but both are worth far more than
preferring drop-2 over a shell, and a weighted sum would hide that behind magic
numbers nobody can defend. The order is asserted positionally by
`tests/test_grips.py::TestVoicingCost`, so changing it is a musical decision and
not a refactor.

Generation and selection are separate modules, which is what lets `grips` and the
octave-down rescue not have to know about each other: `grips` produces candidates,
`cost` picks one. `_window_penalty` is the one place position is compared *across*
candidate pools rather than within a single one - it is what `prepare_step` uses
to decide whether the octave-down pool beats the written one.

`bass_cost` is **not** here, and its absence is deliberate. It is the same *kind*
of rule - one comparable tuple, built per role - and it would sit naturally beside
this one, but the two would then need each other: `bass_cost` ranks over the
`BASS_ROLE_*` constants, which are the walking bass's own vocabulary, and
`bass._walking_bass_line` is what calls it. Putting it here would make `cost`
import `bass` and `bass` import `cost`. It lives in `bass` instead, next to the
roles it ranks over.
"""

from __future__ import annotations

from typing import Container, List, Optional, Tuple

from .grips import BASS_DEGREES_6432, GRIP_PREFERENCE
from .tuning import NECK_FRET_MAX, NECK_FRET_MIN, GuitarFretboard, Voicing


def _window_penalty(
    candidates: List[Voicing],
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
) -> int:
    """
    How many frets the best of `candidates` puts outside the neck window.

    Zero means at least one candidate lies wholly inside it. This is the test the
    octave-down rescue uses to decide whether a melody is *badly placed* - and it
    deliberately asks the best candidate rather than the average, so one
    comfortable voicing is enough to leave the melody where it was written.
    """
    return min(
        (
            sum(1 for fret in v.active_frets() if not fret_min <= fret <= fret_max)
            for v in candidates
        ),
        default=0,
    )


def voicing_cost(
    voicing: Voicing,
    previous: Optional[Voicing],
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    allowed_tones: Optional[Container[int]] = None,
    root_pc: Optional[int] = None,
    melody_pc: Optional[int] = None,
) -> Tuple[float, ...]:
    """
    The whole selection rule as one comparable number, lowest wins.

    It is a *tuple* rather than a weighted sum on purpose. These priorities are
    genuine trade-offs that must not be traded against each other - "stay in
    position" is not worth a semitone of inner-voice movement, but both are worth
    far more than preferring drop-2 over a shell - and a weighted sum would hide
    that behind magic numbers whose values nobody can defend. Lexicographic order
    states the ranking directly, so each criterion is only consulted when the ones
    before it are exactly tied.

    In order:

    0. notes outside the chord, when `allowed_tones` is given. This is a
       *correctness* criterion and it outranks every preference, because a wrong note
       is not playable at all while an awkward position is merely awkward. It exists
       because the hand-authored drop-2 tables do not have an inversion for every
       chord tone - a 9th in the melody of a 13 chord, for instance - and the
       quality-only fallback that covers the gap is free to sound a note the chord
       does not contain. Several of the derived grips always pass this.

       **A count, not a yes/no, and `melody_pc` is excluded from it.** Both parts were
       needed to make it work and either alone does nothing.

       *Counting* is what separates a shape adding one wrong note from one adding four.
       As a boolean they scored identically, so the tie fell through to fret span - and
       the wronger shape usually won there, because a shape with more wrong notes is not
       obliged to be wider but tends to be.

       *Excluding the melody* is what lets a correct shape reach zero at all. The melody
       is the caller's note and the engine does not rewrite it, so when it lies outside
       the chord **every** candidate is impure on it and the criterion cannot tell them
       apart. G7 under F#5 is the case: drop-2's fallback offers shapes carrying two to
       four notes the chord does not contain, while drop-2 & 4 derives one carrying
       none - and both scored 1.0, so the wrong one won on span. Measured over five
       qualities and every non-chord melody in the register, the two changes together
       take 134 wrong notes down to 9.

       `melody_pc` is passed by the caller rather than recovered here: a Voicing knows
       which of its notes is the melody only by position, and the soprano is not the
       melody in every family. Left None, the melody is counted like any other note -
       the previous behaviour.
    1. frets outside the window. This is a *penalty*, not a filter. A melody that
       cannot be voiced between the two frets is still played, one fret-pair at a
       time out of position, because a chord of the tune is worth more than a
       fretboard preference. See NECK_FRET_MIN.
    2. missing voices. A partial harmonisation is a *fallback*, not a style: where a
       complete chord can be played at all, it is used, and it outranks staying in
       exactly the same spot. This sits below the window and above position because
       both of those are about comfort and this is about whether the chord is
       actually there. A root-and-3rd duo is a real voicing of a root-and-3rd, not a
       Cmaj7 - but it is one chord tone under the melody where a shell is **two**, the
       3rd and the 7th together, and "it is important to play the guide tones" is what
       makes a shell the fuller statement of the two. So the term counts: four-note 0,
       shell 1, duo 2, and a duo loses to a shell that holds the position better.

       An earlier version of this docstring said a permitted root-or-5th duo "scores
       zero here, so where two notes really are enough it competes on equal terms with
       a four-note shape". The code has never done that - `missing` is computed as
       `4 - len(active)` and nothing exempts a duo - so the sentence described a rule
       that was not implemented. Measured, adopting it would move 33 of 463 corpus
       steps (7.1%) and take **7 of them from shells**, which is the one outcome the
       guide-tone argument rules out. The code is right and the sentence was wrong; it
       is corrected here rather than the tuple.
    3. fret span: a tighter shape is easier to hold and to move, and a five-fret
       stretch is not always a stretch a hand can take. This sits *above* neck
       position, which is the one priority it is promoted across, and that is a
       deliberate trade rather than an oversight.

       The reason is that the two criteria disagree about the same thing. Neck
       position measures how far the *hand* moves; span measures how far the hand
       has to *stretch* once it is there. A five-fret shape sitting one fret from
       where the hand already was wins on position and loses on span, and before
       this change it was chosen - which is how the engine came to select shapes
       like `8-x-8-8-13-x` (index at 8, pinky at 13) for a Cm7b5. Keeping the
       hand still is worth less than being able to play the shape it is holding.

       Promoting span rather than lowering GRIP_MAX_SPAN is what keeps this free.
       A tightened cap is a hard filter, so it deletes a voicing wherever no
       tighter one exists - measured, that cost the only Gsus4 fingering
       (`x-x-5-5-3-8`) and the 6-4-3 shell, the one shape that reaches the low E.
       Ranking instead only ever chooses between shapes already on the table, so
       nothing stops being voiceable. It is not a guarantee that every selected
       shape is narrow: where the only option is wide, span is consulted first and
       finds every candidate equal, and the wide one is still played. The cap
       remains the outer bound on that. Promoting it over the bass-function term at
       index 6 is the one real cost: a low Dm7 under D4 now takes a span-1 shape
       with C in the bass over a span-2 6-4-3-2 with A. Ranking the bass above span
       was measured and brings `8-x-8-8-13-x` back, so the two cannot both come
       first; span wins because an unplayable stretch costs more than a 3rd in the
       bass. See AGENTS.md, "Span outranks neck position".
    4. distance in neck position from the previous voicing, measured as the
       difference of average frets. Absolute fret numbers mean the same place on the
       neck whichever string they are on, so this stays meaningful when a melody
       holds its place by moving to a different string - which is the behaviour the
       G-string soprano exists to enable. With no previous chord this becomes the
       long-standing "start near the middle of the neck" rule.
    5. total pitch movement of the voices, the historical voice-leading measure.
    6. bass function, when `root_pc` is given: 0 for a root or a 5th in the lowest
       voice, 1 otherwise. This is a *tie-break*, not a priority - it is consulted
       only when two shapes already agree on everything above, which is exactly the
       situation 6-4-3-2 creates. Its whole point is to make the low-E root bass
       reachable at all: the contiguous 5-4-3-2 block places its lowest note on the A
       string, so a root there is a consequence of the string set and never a
       decision, and without this term `voicing_cost` declines the alternative on
       neck position before it ever reaches the bass. Putting it at 6 rather than
       near the front is deliberate: "the bass should be the root" must not outbid
       "do not sound a wrong note" or "keep the hand where it is". The same rule as
       BASS_DEGREES_6432, applied to whatever shape won rather than to one family,
       so a contiguous shape with a root bass is not penalised either.
    7. grip preference, so a four-note drop-2 wins an exact tie against a shell.
    """
    active = voicing.active_frets()
    outside = sum(1 for fret in active if not fret_min <= fret <= fret_max)
    foreign = 0.0
    # An *empty* tone set means the chord could not be read, not that every note is
    # wrong, so the criterion is not asked at all. This is the docstring's rule -
    # "when `allowed_tones` is given" - and it needs the emptiness check because an
    # empty container is not None. Without it a count turns an unreadable chord into
    # "every note is a wrong note", which then ranks a two-note duo (2.0) above a
    # four-note chord (4.0): fewer notes becomes *better*. As a boolean that could
    # not happen, since every shape scored 1.0 and the field was inert. `Dm(maj7)`
    # is the live case - the spelling does not parse, so it has no tone set.
    if allowed_tones:
        for pitch in voicing.midi_notes():
            pc = pitch % 12
            if melody_pc is not None and pc == melody_pc % 12:
                continue
            if pc not in allowed_tones:
                foreign += 1.0

    if previous is None:
        # The first chord of a progression has nothing to lead from, so "stay near
        # where we are" becomes "start in a comfortable part of the neck".
        position = abs(voicing.avg_fret - 9)
        movement = 0.0
    else:
        position = abs(voicing.avg_fret - previous.avg_fret)
        movement = calculate_pitch_leading_distance(previous, voicing)

    grip_rank = (
        GRIP_PREFERENCE.index(voicing.grip)
        if voicing.grip in GRIP_PREFERENCE
        else len(GRIP_PREFERENCE)
    )
    missing = 4 - len(active)
    # No root, no claim to make: an unparseable chord name simply does not get this
    # criterion, which is why it is opt-in per call rather than derived.
    bass_root_or_fifth = (
        0.0
        if root_pc is not None
        and voicing.bass_pc is not None
        and (voicing.bass_pc - root_pc) % 12 in BASS_DEGREES_6432
        else 1.0
    )

    return (
        foreign,
        float(outside),
        float(missing),
        float(voicing.fret_span()),
        position,
        movement,
        bass_root_or_fifth,
        float(grip_rank),
    )


def _best_voicing(
    candidates: List[Voicing],
    previous: Optional[Voicing] = None,
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    allowed_tones: Optional[Container[int]] = None,
    root_pc: Optional[int] = None,
    melody_pc: Optional[int] = None,
) -> Optional[Voicing]:
    """
    The candidate voicing_cost likes best, or None when there are no candidates.

    Python's min is stable, so two candidates that cost exactly the same are
    decided by generation order, which is high-E strings first and GRIP_PREFERENCE
    within a string. That keeps the whole engine deterministic: the same progression
    always arranges to the same tab, which is what makes its output worth asserting
    on in tests.

    `root_pc` is passed straight through to voicing_cost and is what enables the
    bass-function tie-break. A caller that does not have a root simply omits it and
    gets the previous behaviour, unchanged.
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda v: voicing_cost(
            v, previous, fret_min, fret_max, allowed_tones, root_pc, melody_pc
        ),
    )


def calculate_voice_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
    """Calculates total physical movement across all active strings."""
    frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
    frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
    total_distance = 0
    for f_a, f_b in zip(frets_a, frets_b):
        if f_a >= 0 and f_b >= 0:
            total_distance += abs(f_a - f_b)
    return float(total_distance)


def calculate_pitch_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
    """
    Sums the movement of every voice between two voicings, measured in semitones.

    This is the string-set agnostic counterpart to calculate_voice_leading_distance:
    it compares sounding pitches rather than fret numbers, so it stays meaningful
    when one chord puts the melody on the high E string and the next puts it on the
    B string (the same pitch sounding on a different string). Within a single string
    set the two metrics agree exactly, since a fret delta is a semitone delta.
    """
    frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
    frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
    pitches_a = sorted(
        GuitarFretboard.fret_to_midi(s_idx, f) for s_idx, f in enumerate(frets_a) if f >= 0
    )
    pitches_b = sorted(
        GuitarFretboard.fret_to_midi(s_idx, f) for s_idx, f in enumerate(frets_b) if f >= 0
    )
    return float(sum(abs(p_a - p_b) for p_a, p_b in zip(pitches_a, pitches_b)))
