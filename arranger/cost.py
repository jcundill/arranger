"""The selection rule: which of the candidates is played.

`voicing_cost` is the library's central invariant - a tuple compared lexicographically,
not a weighted sum, with its order asserted positionally by
`tests/test_grips.py::TestVoicingCost` - and `_best_voicing` is its argmin. **No
criterion names a grip family**: a tie that runs off the end of the tuple is broken by
generation order, which is `grips.GRIP_PREFERENCE`. `bass_cost` deliberately lives in
`bass` instead, next to the `BASS_ROLE_*` vocabulary it ranks over, because importing it
here would make `cost` import `bass` and `bass` import `cost`.
"""

from __future__ import annotations

from typing import Container, List, Optional, Sequence, Tuple

from .grips import BASS_DEGREES_6432
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

    In order, and this order is the invariant:

    0. notes outside the chord, when `allowed_tones` is given. A *correctness*
       criterion that outranks every preference, because a wrong note is not playable
       at all while an awkward position is merely awkward. It exists because the
       hand-authored drop-2 tables do not have an inversion for every chord tone - a
       9th in the melody of a 13 chord, for instance - and the quality-only fallback
       that covers the gap is free to sound a note the chord does not contain. Several
       of the derived grips always pass this.

       **A count, not a yes/no, and `melody_pc` is excluded from it.** Both parts are
       load-bearing. Counting separates a shape adding one wrong note from one adding
       four, which a boolean scores identically and so hands to fret span. Excluding
       the melody is what lets a correct shape reach zero at all: the melody is the
       caller's note and the engine does not rewrite it, so when it lies outside the
       chord **every** candidate is impure on it and the criterion cannot tell them
       apart. The measurement behind both is in `docs/engine.md` §"Grips, and the
       position-aware selector".

       `melody_pc` is passed by the caller rather than recovered here: a Voicing knows
       which of its notes is the melody only by position, and the soprano is not the
       melody in every family. Left None, the melody is counted like any other note.

       An *empty* `allowed_tones` means the chord could not be read rather than that
       every note is wrong, so the criterion is not asked at all.
    1. frets outside the window. A *penalty*, not a filter: a melody that cannot be
       voiced between the two frets is still played, one fret-pair at a time out of
       position, rather than dropped. It is a comfort criterion, but it sits *above*
       completeness, so where nothing complete fits the window the engine plays a
       partial shape that does. See `tuning.NECK_FRET_MIN`.
    2. missing voices. A partial harmonisation is a *fallback*, not a style: where a
       complete chord can be played, it is used, and it outranks staying in exactly
       the same spot, because the window and position are about comfort while this is
       about whether the chord is actually there. The term is `4 - len(active)` and
       **nothing exempts a duo**, so a four-note shape scores 0, a shell 1 and a duo
       2, and a duo loses to a shell that holds the position better. A shell sounds the
       3rd *and* the 7th where a duo sounds one of them, which is what makes the shell
       the fuller statement of the two.
    3. fret span: a tighter shape is easier to hold and to move. It sits *above* neck
       position, the one priority promoted across another - a deliberate trade,
       measured rather than guessed; the reasoning is in `docs/engine.md` §"Span
       outranks neck position".

       **Span 0 and span 1 are bucketed to the same value**, because one fret of
       stretch is not worth moving the hand for. The bucket is applied to the *value*
       at this index rather than by reordering the tuple, so **every span of two or
       more still outranks position exactly as before** - do not turn it into an
       ordering change. `GRIP_MAX_SPAN` remains the outer bound, so where the only
       candidate is wide it is still played.
    4. distance in neck position from the previous voicing, measured as the difference
       of average frets. Absolute fret numbers mean the same place on the neck
       whichever string they are on, so this stays meaningful when a melody holds its
       place by moving to a different string - the behaviour the G-string soprano
       exists to enable. With no previous chord it becomes "start near the middle of
       the neck".
    5. total pitch movement of the voices in semitones, so it stays meaningful when the
       melody changes string: `calculate_pitch_leading_distance`, not the fret-based
       `calculate_voice_leading_distance`.
    6. bass function, when `root_pc` is given: 0 for a root or a 5th in the lowest
       voice, 1 otherwise. A *tie-break*, not a priority - consulted only when two
       shapes already agree on everything above, which is exactly the situation
       6-4-3-2 creates. Its point is to make the low-E root bass reachable at all: the
       contiguous 5-4-3-2 block places its lowest note on the A string, so a root there
       is a consequence of the string set and never a decision, and without this term
       `voicing_cost` declines the alternative on neck position before it ever reaches
       the bass. It sits below the correctness and position criteria deliberately: "the
       bass should be the root" must not outbid "do not sound a wrong note" or "keep
       the hand where it is". The same rule as `BASS_DEGREES_6432`, applied to whatever
       shape won rather than to one family, so a contiguous shape with a root bass is
       not penalised either.

    **No criterion names a grip family**, and that is deliberate. Two families can
    generate the very same tab, so at this depth the tuple would be choosing a *name*
    rather than a sound - and a four-note drop-2 never reaches a tie with a shell to
    begin with, because criterion 2 separates them on note count. The order families are
    offered in is `grips.GRIP_PREFERENCE`, and that is where an exact tie is broken: see
    `_best_voicing`.
    """
    active = voicing.active_frets()
    outside = sum(1 for fret in active if not fret_min <= fret <= fret_max)
    foreign = 0.0
    # An empty tone set means the chord could not be read, not that every note is
    # wrong - which is why this tests truthiness and not `is not None`. Without it a
    # count turns an unreadable chord into "every note is a wrong note", and fewer
    # notes becomes *better* than more. `Dm(maj7)` is the live case: the spelling
    # does not parse, so it has no tone set.
    if allowed_tones:
        for pitch in voicing.midi_notes():
            pc = pitch % 12
            if melody_pc is not None and pc == melody_pc % 12:
                continue
            if pc not in allowed_tones:
                foreign += 1.0

    if previous is None:
        position = abs(voicing.avg_fret - 9)
        movement = 0.0
    else:
        position = abs(voicing.avg_fret - previous.avg_fret)
        movement = calculate_pitch_leading_distance(previous, voicing)

    missing = 4 - len(active)
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
        # Spans 0 and 1 bucketed - see criterion 3. Two or more still outranks position.
        0.0 if voicing.fret_span() <= 1 else float(voicing.fret_span()),
        position,
        movement,
        bass_root_or_fifth,
    )


#: The name of each way a shape can lose to another, so a caller holding two candidates
#: can say *which* one separated them: `movement` records the index on the step and
#: `render` reads the phrase from here, which is what keeps the labels from going stale.
#:
#: The first seven are `voicing_cost`'s tuple in its own order - that order is the
#: invariant and this spells it. The eighth is **not a cost criterion at all**: it names a
#: shape removed by a caller's partition *before* the tuple ever saw it, which is how the
#: written slash bass is honoured (`decisions.select_step_voicing`).
#:
#: Each entry is a predicate, read after "the N-voice voicing <tab>".
VOICING_COST_CRITERIA = (
    "sounds a note outside the chord",
    "lies outside the neck window",
    "leaves a voice out",
    "needs a wider stretch",
    "sits further up the neck",
    "moves the inner voices more",
    "sounds a weaker bass",
    "does not sound the written bass",
)

#: `VOICING_COST_CRITERIA`'s span entry, which is the one
#: `decisions.should_demote_to_melody_alone` turns a shape away for.
SPAN_CRITERION = VOICING_COST_CRITERIA.index("needs a wider stretch")

#: `VOICING_COST_CRITERIA`'s last entry: lost to a caller's partition rather than to a
#: cost, so no element of the two tuples need differ.
PARTITION_CRITERION = VOICING_COST_CRITERIA.index("does not sound the written bass")


def decisive_criterion(winner: Sequence[float], loser: Sequence[float]) -> Optional[int]:
    """Which element of `voicing_cost`'s tuple ranked `loser` below `winner`.

    The first index at which two costs differ *is* the criterion that decided between
    them, because every element before it is equal. None means the two tied, in which
    case no criterion can be named - `_best_voicing` broke it on generation order.

    Asking this of a shape with **more** voices than the winner never returns the
    voice-count criterion, because a fuller shape cannot lose on how many voices it has.
    That is what makes the answer worth recording: it says whether the chord was thinned
    because of a wrong note, the neck window or the hand's travel rather than for its own
    sake.
    """
    for index, (a, b) in enumerate(zip(winner, loser)):
        if a != b:
            return index
    return None


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

    **An exact tie is broken by generation order**, because that is what Python's stable
    `min` does with candidates whose cost tuples are equal - and there is deliberately no
    grip criterion to fall back on (`voicing_cost` says why). The order is `top_strings`
    first, then `grips` within one string, so a tie *across* strings goes to the earlier
    string. That makes the caller's own ordering part of the rule rather than an accident
    of the loop: where two families tie - `Cmaj` under a `C4` melody is the pinned case,
    and `tests/test_grips.py::TestClosePosition` holds it - `grips=("closed",
    "drop2_6432")` takes the first tab and the reversed pair takes the second. That is
    what `--grips`' "most preferred first" promises, and it is why the position of a
    family in `GRIP_PREFERENCE` is load-bearing.

    Determinism follows from the inputs being sequences: the same progression always
    arranges to the same tab, which is what makes its output worth asserting on in tests.

    `root_pc` is passed straight through to voicing_cost and is what enables the
    bass-function tie-break. A caller that has no root omits it and gets no bass term.
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
    """
    Total fret movement across the strings both voicings sound.

    The string-set dependent counterpart to `calculate_pitch_leading_distance`: a fret
    delta is a semitone delta, but only for as long as the note stays on its string.
    """
    frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
    frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
    total_distance = 0
    for f_a, f_b in zip(frets_a, frets_b):
        if f_a >= 0 and f_b >= 0:
            total_distance += abs(f_a - f_b)
    return float(total_distance)


def calculate_pitch_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
    """
    Sums the movement of every voice between two voicings, in semitones.

    The string-set agnostic counterpart to `calculate_voice_leading_distance`: it
    compares sounding pitches rather than fret numbers, so it stays meaningful when one
    chord puts the melody on the high E string and the next on the B string.
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
