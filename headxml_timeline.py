from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from arranger import (
    ArrangementStep,
    Rhythm,
    beat_offset,
    default_grouping,
    format_grouping,
    grid_resolutions,
    group_starts,
    parts_has_melody_only,
    parts_have_chord,
    parts_have_melody,
    rhythm_beats,
)
from arranger.grid import (
    RHYTHM_EVERY_BEAT,
    SUBDIVISIONS_PER_FELT_BEAT,
    TICKS_PER_BEAT,
    snap_to_felt_grid,
)
from arranger.grouping import COMMON_TIME, GROUPING_AUTO, TimeSignature
from arranger.options import (
    CHORD_FILLS_COMP,
    CHORD_FILLS_NONE,
    DEFAULT_REQUEST,
    ArrangeOptions,
    Request,
    ResolvedRequest,
    resolve_request,
)
from arranger.resolution import settle_input_fact
from arranger.slots import arrange_slots
from headxml_model import Head, HeadChange, HeadNote
from headxml_read import load_musicxml
from tuning import NO_CHORD

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
    """Every position in a bar, at every 1/12 of a felt beat.

    The grid is per felt beat: each felt beat splits into
    `SUBDIVISIONS_PER_FELT_BEAT` equal parts, so thirds (index 4, 8) and quarters
    (index 3, 6, 9) land exactly. Mixed groupings (`3+2` in 5/4) keep their
    alternating spacing because each group is divided on its own terms.

    Every grid point is exact on the `TICKS_PER_BEAT` lattice - a felt beat is a
    whole number of raw beats, so `1/12` of one is `2 * group_length` ticks - and
    `_tick_key` stays an exact dedup key.

    **Every one of these is a candidate, not a decision**: `_merge_chord_slots`
    drops the ones the melody already occupies and the ones it is still holding,
    and `chord_slots` drops the ones with no chord in force.
    """
    grouping = _chord_grouping(head, grouping)
    lengths = tuple(grouping)
    starts = group_starts(head.beats_per_bar, lengths)
    beats: List[float] = []
    for index, length in enumerate(lengths):
        for k in range(SUBDIVISIONS_PER_FELT_BEAT):
            beat = starts[index] + (k / SUBDIVISIONS_PER_FELT_BEAT) * length
            beats.append(beat)
    return tuple(sorted(beats))


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


def first_complete_bar(head: Head) -> int:
    """The bar a requested figure's **first segment** lands on.

    An anacrusis is not a bar of the form: the score says bar 1 is short, so the
    first bar the form actually begins in is bar 2. A figure therefore starts there,
    and the pickup bar takes the tune's own onsets instead - which is what keeps an
    accompaniment from beginning one bar early on a head that opens with a pickup.

    `first_bar_implicit` states it when the source marks the first bar `implicit="yes"`
    (or numbers it 0). When the source says nothing (`None`), a **double barline**
    after bar 1 is the notation's own statement that the bar is an anacrusis: the
    music stops mid-measure and the form begins in the next bar. That is the
    Blue Moon case - a real-world pickup bar that MuseScore ships unmarked, closed
    by a double barline.

    Exported through the importer's module rather than kept private, because it is
    the one answer to "where does the form begin", and `arrange_xml_head` and the
    slot builders must agree on it.
    """
    if head.first_bar_implicit is True:
        return head.bars[0] + 1
    if (
        head.first_bar_implicit is None
        and head.first_bar_ends_with_double_barline
    ):
        # An unmarked short first bar closed by a double barline: the source said
        # nothing, but its barline says the bar is an anacrusis, so the form begins
        # in the next bar.
        return head.bars[0] + 1
    return head.bars[0]


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
    4/4 bar is beat 1.5 of every bar the figure covers, and a position the tune merely
    holds through is still one the chord attacks on - a stab under a held note is
    wanted, so unlike the melody-anchored union there is no hold filter here. A
    figure longer than one bar gives each bar of the section its own segment
    (`Rhythm.at`), so a two-bar figure alternates rather than repeating, and it
    begins at `first_complete_bar`: an anacrusis states no requested position, because
    the pickup bar takes the tune's own onsets and the figure starts where the form
    does.

    `extra_positions` are the caller's own positions beside the rhythm's - the tune's
    written onsets, for a rhythm that names `melody` *and* positions and so plays
    both. They are unioned on `(bar, beat)` with the rhythm's, and every slot is built
    by `_slots_at` with `_stab_length` over the whole set: the two sources cannot
    disagree about the harmony in force, nor about how long an attack rings.
    """
    lo, hi = section if section is not None else head.bars
    grouping = _chord_grouping(head, grouping)
    first_bar = first_complete_bar(head)
    at: Dict[Tuple[int, int], Tuple[int, float]] = {}
    for bar in range(lo, hi):
        segment = rhythm.at(bar, first_bar)
        for beat in rhythm_beats(segment, head.beats_per_bar, grouping):
            snapped = snap_to_felt_grid(beat, head.beats_per_bar, grouping)
            at.setdefault(_tick_key(bar, snapped), (bar, snapped))
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
            snapped = snap_to_felt_grid(beat, beats_per_bar, grouping)
            absolute = beat_offset(bar, snapped, beats_per_bar)
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
    if not rhythm.is_melody_only:
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
    named = not chord_on.is_none and not chord_on.is_melody_only
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
    onsets = [
        (slot[1], slot[2])
        for slot in skeleton
        if chord_on.at(slot[1], first_complete_bar(head)).melody
    ]
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
    # **Where the form begins**, stated once and read by both layers: the slot builders
    # (`rhythm_slots`, `_comp_only_timeline`) and the engine's chord and bass rhythms all
    # take their cycle's origin from this bar, so a figure lands on the first complete
    # bar rather than on the pickup. Only the score knows which bar that is.
    options = replace(options, first_full_bar=first_complete_bar(head))
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


