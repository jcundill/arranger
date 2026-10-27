"""Grip templates: pure interval, offset and stack computation.

Everything that turns a chord quality and a melody note into *semitone offsets
below the soprano* is here, plus `_shell_voicing` which builds a comping or
searched-family candidate from those offsets. Nothing here chooses between
candidates - `cost` holds the selection rule, and no builder below knows what
came before it, what the neck window is, or what the answer turned out to be.

The tables these builders read live in `grip_tables`, below this module.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .chords import ChordParser
from .grip_place import sounds_distinct_pitches
from .grip_tables import (
    BOTTOM_FOUR,
    GRIP_STRING_SETS,
    SHELL_DEGREES,
    TONE_PRIORITY,
    stated_tones,
)
from .step_types import Voicing
from .tuning import STANDARD_TUNING

_LAYOUT_GRIPS: Tuple[str, ...] = (
    "drop2", "closed", "drop3", "drop24", "duo", "interval",
)
_SEARCHED_GRIPS: Tuple[str, ...] = ("shell", "drop2_6432")

BASS_DEGREES_6432: Tuple[int, ...] = (0, 7)


def _nearest_tone_below(midi: int, pitch_class: int, max_drop: int = 24) -> Optional[int]:
    """The highest pitch at or below `midi` that has `pitch_class`, or None.

    Working in real pitches rather than in differences of pitch classes is what keeps
    octave placement honest. The root below a major 3rd is a major sixth down, not a
    major third down: taking the mod-12 difference and calling it the distance puts
    the root a fourth too high and produces voicings that spell the wrong octave.
    """
    for drop in range(max_drop + 1):
        pitch = midi - drop
        if pitch % 12 == pitch_class % 12:
            return pitch
    return None


def _close_stack_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: Optional[int] = None
) -> List[int]:
    """A four-voice close-position stack under the melody, as semitone offsets.

    Each voice is the nearest chord tone below the one above it, so the result is the
    tightest four-note chord that fits under the melody. `tones` are pitch classes,
    absolute or relative to `root_pc`; passing the root makes the search a walk *down
    the chord* rather than down the keyboard, which is what a triad needs - with only
    three tones the walk simply wraps to the root an octave below, doubling it, so
    there is no special case for triads.

    Returns fewer than four offsets when the walk cannot continue, which the caller
    treats as "this quality has no four-note shape here".
    """
    if not tones:
        return []
    offsets = [0]
    current = melody_midi
    for _ in range(3):
        nxt: Optional[int] = None
        for tone in tones:
            absolute = tone if root_pc is None else (root_pc + tone) % 12
            found = _nearest_tone_below(current - 1, absolute)
            if found is not None and (nxt is None or found > nxt):
                nxt = found
        if nxt is None:
            break
        current = nxt
        offsets.append(current - melody_midi)
    return offsets


def _guide_tones(tones: Tuple[int, ...], root_pc: Optional[int]) -> Tuple[int, ...]:
    """The degrees of this chord that define it: its 3rd (or 4th) and its 7th.

    Read off the tone set rather than tabulated, because it is a property of the chord
    and not of any voicing. The **major** 3rd is preferred where the set holds both
    (7alt carries b3 and 3, since it is an altered chord and either may be asked for),
    because the major one is the chord's actual identity; the b3 there is an option.

    **A suspended chord's guide tone is the 4th, not the 3rd.** Dsus7 is 1 4 5 b7: it has
    no 3rd at all, so a lookup for one finds nothing and reports *no* third - where the note
    that defines the sus chord as a sus chord is exactly that 4th. Two sus voicings have to
    agree about which note plays that role, and the hand tables already say so: `SHELL_DEGREES`
    gives 7sus4 `(4, b7)` and sus4 `(4, 5)`, and every drop-2 template for those qualities keeps
    the same pair. Reading the tables here rather than re-deriving the rule is what keeps the
    three in step.

    A triad has no 7th, so either may be absent - the caller treats "no 7th" as
    "nothing to preserve" rather than as a failure.
    """
    present = set(t % 12 for t in tones)
    if root_pc is not None:
        present = {(t - root_pc) % 12 for t in tones}
    third = next(
        (d for d in (4, 3, 5, 2, 7) if d in present), None
    )
    seventh = next(
        (d for d in (10, 11, 6) if d in present), None
    )
    keep = []
    if third is not None:
        keep.append(third)
    if seventh is not None:
        keep.append(seventh)
    return tuple(keep)


_INTERVAL_CLASSES = (3, 9, 8)


def _interval_set_for_grip(
    grip: str,
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: Optional[int] = None,
) -> List[List[int]]:
    """The close-position templates for one grip, as offsets from the soprano.

    Deriving drop-3 and close position from the chord tones gives a *fuller* chord than
    the tone-priority rule gives at four voices - every tone the rule left out comes
    back - which is a legitimate but different voicing rather than an error, and is why
    these families have their own rule instead of sharing drop-2's.

    drop-2, drop-3 and close position share one close-position stack of four voices,
    taken as v1, v2, v3, v4 from the top:

        close position    v1  v2  v3  v4
        drop 2            v1  v3  v4  (v2 down an octave)
        drop 3            v1  v2  v4  (v3 down an octave)

    which is the usual definition: a drop-N voicing is a close-position stack with the
    Nth voice from the top lowered by an octave.
    """
    if grip not in ("drop3", "closed", "drop24"):
        return []

    stack = _close_stack_offsets(tones, melody_midi, root_pc)
    if len(stack) < 4:
        return []

    # stack[0] is the melody itself (offset 0), so the three voices below it are
    # stack[1:]. The templates read 0 (soprano), v1, v2, v3 as the four voices in the
    # order they sound.
    _, v1, v2, v3 = stack
    if grip == "closed":
        return [[0, v1, v2, v3]]

    # Drop 2 & 4: the SECOND and FOURTH voices each drop an octave. The sounding order
    # top to bottom is therefore v2, then v1 and v3 an octave down: [0, v2, v1-12, v3-12].
    if grip == "drop24":
        if root_pc is not None and (melody_midi + v3) % 12 == root_pc % 12:
            return [[0, v2, v1 - 12, v3]]
        return [[0, v2, v1 - 12, v3 - 12]]

    # Drop 3: the THIRD voice from the top drops an octave. It therefore lands below
    # the bottom voice, so it is the *last* note in the template rather than the third.
    if root_pc is not None and (melody_midi + v2) % 12 == root_pc % 12:
        return [[0, v1, v3 - 12, v2]]
    return [[0, v1, v3, v2 - 12]]


def _duo_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: int, canonical: str
) -> List[int]:
    """Two notes under the melody: root or 5th, plus one guide tone.

    A duo states the chord's *function*, not its quality: root or 5th underneath,
    and one guide tone above. The guide tone is the 3rd (or 4th on a sus chord),
    because that is what tells the ear major from minor. The second voice is never
    the melody itself - a unison is not a voice.
    """
    guide = SHELL_DEGREES.get(canonical)
    if guide is None:
        return []
    melody_pc = (melody_midi - root_pc) % 12
    for degree in guide:
        if degree % 12 == melody_pc:
            continue
        pitch = _nearest_tone_below(melody_midi, (root_pc + degree) % 12)
        if pitch is None:
            continue
        while pitch >= 0 and melody_midi - pitch <= 2:
            pitch -= 12
        if pitch < 0:
            continue
        return [0, pitch - melody_midi]
    return []


def _interval_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: int
) -> List[List[int]]:
    """Two-note interval shapes under the melody: a 3rd, a 6th or a 10th, as templates.

    This is the arranging guide's "2-note intervals (3rds or 6ths)" - the texture it
    calls for in the gaps between a chord on a strong beat and the next one. It is a
    **texture, not a harmony**, and that distinction is the whole reason it is a
    separate grip rather than a widening of `_duo_offsets`:

      - It is NOT gated on the duo's root-or-5th rule. A duo refuses to sound under a 3rd or a 7th
        in the melody, because there those two notes *are* the chord's function and a
        bare pair sounds like a mistake. An interval is not claiming the harmony, so
        it is free to sit under any melody note - which is exactly the case a fill
        most often has to cover, since a passing tone is by definition not a chord tone.
      - Because it is confined to fill slots, the looser rule cannot leak into a
        position where a chord is being stated. The **fill-only palette** is what enforces
        that, and it is the reason this can safely be more permissive than a duo.

    The second voice is the nearest pitch a 3rd, a 6th or a 10th below the melody that
    is one of the chord's own tones. When the melody is *not* a chord tone, the walk
    also considers the diatonic tones of the prevailing key, so a passing note can
    still be accompanied rather than left naked - and only for the key's own notes,
    never for a chromatic one. That limit is what keeps a fill from quietly
    reharmonising the bar.

    Returns an empty list when the chord has no root or no tone set, on the same
    argument as the shell: an interval named against a chord we cannot identify is a
    guess, and a guess here is how a wrong note gets in.
    """
    if not tones or root_pc is None:
        return []

    key_pcs = {0, 2, 4, 5, 7, 9, 11}
    chord_pcs = {pc % 12 for pc in tones}

    templates: List[List[int]] = []
    seen: set = set()
    for source in (chord_pcs, key_pcs):
        for size in _INTERVAL_CLASSES:
            for octave in (0, 12):
                pitch = melody_midi - size - octave
                if pitch % 12 not in source:
                    continue
                offset = pitch - melody_midi
                if offset in seen:
                    continue
                seen.add(offset)
                templates.append([0, offset])
        if templates:
            break
    return templates


def _templates_for(
    grip: str,
    canonical: str,
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: Optional[int],
) -> List[List[int]]:
    """The interval templates a **layout** family places on one string set.

    A template is the shape, so nothing here is searched: `drop3`, `drop24` and `closed`
    are transformations of the close stack under the melody, drop-2 reads the tone-priority
    rule, and `duo` and `interval` are the two notes they name. Those last two are the ones
    that need a root, because each *names a chord tone* - a guide tone, or an interval from
    the root - where the others are built from the stack itself.
    """
    if grip == "duo":
        if root_pc is None:
            return []
        duo = _duo_offsets(tones, melody_midi, root_pc, canonical)
        return [duo] if duo else []
    if grip == "interval":
        return [] if root_pc is None else _interval_offsets(tones, melody_midi, root_pc)

    if grip in ("closed", "drop3", "drop24"):
        return _interval_set_for_grip(grip, tones, melody_midi, root_pc)

    if grip == "drop2":
        if root_pc is not None and tones:
            degree = (melody_midi - root_pc) % 12
            if degree in {t % 12 for t in tones}:
                shape = drop2_template_for(canonical, degree)
                return [shape] if shape else []
        return _drop2_palette(canonical)
    return []


def drop2_template_for(quality: str, degree: int) -> List[int]:
    """The textbook drop-2 of the tones `degree` states, as offsets below the soprano.

    `degree` is the melody's own degree above the root, so the melody is `0` and the
    three voices below it are the walk's: `_close_stack_offsets` takes the nearest
    *stated* tone below each voice already placed, and the second voice from the top is
    then lowered an octave - which is what puts the 3rd and the 7th on the D and G
    strings in the familiar 4-3-2-1 shell shape.

    Two properties are the whole reason this is a rule and not a table:

      - the tone set is `stated_tones`, so the root goes before the natural 5th and an
        altered 5th is kept, which is the musical decision the tables encode;
      - the walk sees only the *stated* tones, so it cannot spend a voice on a tone the
        rule left out.

    **A triad has only three tones, so its fourth voice is the root doubled an octave
    down** - and the walk finds it rather than a special case naming it: handed the full
    tone set it wraps to the root on its own. Handing it the three stated tones only
    produces a duplicate of the 5th instead (`[0, -8, -17, -17]` for a C major), which is
    not a chord at all. That is why `walk` is the stated tones when there are four of
    them and the quality's whole tone set when there are not.

    Returns `[]` - nothing offered rather than a guess - for a quality with no priority
    row or no tone set, and for a degree the rule cannot build a shape for.
    """
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(quality)
    if quality not in TONE_PRIORITY or not tones:
        return []
    keep = stated_tones(quality, degree, 4)
    walk = keep if len(keep) >= 4 else tuple(tones)
    stack = _close_stack_offsets(walk, 60 + degree, 0)
    if len(stack) < 4:
        return []
    return [0, stack[2], stack[3], stack[1] - 12]


def _drop2_palette(quality: str) -> List[List[int]]:
    """Every drop-2 shape the rule builds for a quality, in the rule's own order.

    This is what a melody with **no degree to match** is offered: one that is not a chord
    tone, and any call with no root at all. Each shape's top voice *is* the melody by
    construction, so the palette is the set of harmonisations the rule can put under it,
    and `voicing_cost` chooses among them - tone purity first, so the shapes that state
    the chord rank above the ones that merely fit.

    Shaped off `TONE_PRIORITY` rather than a list of degrees, which is what makes the
    palette the same rule as a single shape: the degrees a quality has *are* its priority
    row, so there is no second table to keep in step with this one.
    """
    order = TONE_PRIORITY.get(quality)
    if order is None:
        return []
    return [
        drop2_template_for(quality, degree)
        for degree in order
    ]


def string_sets_for(grip: str, top_string: int) -> List[Tuple[int, ...]]:
    """The string sets a grip family may use, with the soprano first.

    Every entry names its soprano as its **highest** string, so ordering the set
    descending is what puts the soprano first. For `drop2`, any top string works:
    the four strings below it are used. For the named families, the table lists
    each set low-to-high, so the soprano is found by searching for it rather than
    by assuming an end: for a 1-2-3 shell the soprano is the first entry, for
    6-4-3 it is the last, and a duo like (5, 4) happens to start on it.

    Descending order, and specifically *not* a rotation. Rotating the stored
    low-to-high tuple from the soprano (`strings[pivot:] + strings[:pivot]`) looks
    equivalent and is not: for the four-string block stored (2, 3, 4, 5) with the
    soprano on 5 it yields (5, 2, 3, 4), which walks *up* the neck for the next
    three voices. That hands a voice the G-string note on the G string, the D-string
    note on the D string and the B-string note on the B string while claiming to
    descend - the pitches are right and the strings are not, and the span check then
    measures frets on strings the voice was never meant for. A rotation is only
    order-preserving if the tuple is already in the order being rotated *into*,
    and this one is stored the other way up.
    """
    if grip == "drop2":
        tabulated = [
            tuple(sorted(strings, reverse=True))
            for strings, soprano in GRIP_STRING_SETS["drop2"]
            if soprano == top_string
        ]
        if tabulated:
            return tabulated
        if top_string < 3:
            return []
        strings = tuple(range(top_string, top_string - 4, -1))
        if frozenset(strings) == BOTTOM_FOUR:
            return []
        return [strings]
    sets: List[Tuple[int, ...]] = []
    for strings, soprano in GRIP_STRING_SETS.get(grip, ()):
        if soprano == top_string and soprano in strings:
            sets.append(tuple(sorted(strings, reverse=True)))
    return sets


def _shell_voicing(
    frets_by_string: Tuple[int, ...],
    frets: Tuple[int, ...],
    midis: List[int],
    canonical: str,
    root_pc: int,
    tones: Tuple[int, ...],
    notes: int = 3,
    bass_voice: bool = False,
) -> Optional[Voicing]:
    """One comping candidate, or None when it does not state the chord.

    Both guide tones must sound and nothing outside the chord may, which is the rule
    `candidate` enforces for the melody-bearing shell and the reason this one shares its
    vocabulary. The **unison rule** is the other one it shares: no two sounding strings may
    carry the same pitch, because a unison states the chord with one voice fewer than the
    arity claims (`grip_place.sounds_distinct_pitches`). Shared by the melody-bearing shell
    and the melody-free one so the two cannot drift apart on what counts as a shell.

    `notes` is **how many voices the guitar was asked to play**, which is the arity of the
    shape: `alto,tenor` is two notes and `alto,tenor,tenor`-style requests are still two
    because a voice is a *role* in the stack, not a count. The pair case is the reason
    this is a parameter and not a constant -- with two voices there is no room for the
    third note a three-voice shell spends on the root or the 5th, and asking for a shape
    that sounds three notes when two were named is how a part ends up with a voice in it
    that belongs to somebody else.

    **`bass_voice` changes which note the shape must sound, because it changes what the
    shape is.** Every other selection here is stating a chord *quality* to somebody
    else's ear, so the guide tones are the claim. A lone bass note is stating the chord's
    *function*, and a 3rd or a 7th down there does not sound like a bass note at all - it
    sounds like the wrong chord. The library already states that rule for the one place
    it had to: `BASS_DEGREES_6432` carries the comment "the lowest voice is what *defines*
    the chord, so a 3rd or a 7th down there sounds like the wrong harmony rather than a
    voicing of this one", and this is that same rule read from that same table rather than
    a second one written here.

    So a bass voice takes the **root, or the 5th where the root is unreachable**, in
    preference order, and keeps the same rule as every other shape: nothing outside the
    chord may sound. The 5th is a fallback rather than a co-equal choice because the
    root is the note that names the chord; a 5th names it only in company.
    """
    guide = SHELL_DEGREES.get(canonical)
    if guide is None:
        return None
    if len(frets_by_string) < notes:
        return None
    if not sounds_distinct_pitches(midis):
        return None
    pcs = {midi % 12 for midi in midis}
    if bass_voice:
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not pcs <= allowed:
            return None
        for degree in BASS_DEGREES_6432:
            if (root_pc + degree) % 12 in pcs:
                break
        else:
            return None
    else:
        keep = 2 if notes >= 2 else 1
        needed = {(root_pc + degree) % 12 for degree in guide[:keep]}
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not needed <= pcs or not pcs <= allowed:
            return None

    vector = [-1] * len(STANDARD_TUNING)
    for string, fret in zip(frets_by_string, frets):
        vector[string] = fret
    active = list(frets)
    return Voicing(
        frets=vector,
        top_fret=frets[0],
        avg_fret=sum(active) / len(active),
        grip="shell",
        bass_pc=min(midis) % 12,
    )
