"""Grip families: the builders and the candidate generators.

Everything that turns a chord quality and a melody note into a *set of candidate
voicings* is here, and nothing here chooses between them. That split is what lets
this module be read on its own: `cost` holds the selection rule, and no generator
below knows what came before it, what the neck window is, or what the answer
turned out to be. The tables these builders read live in `grip_tables`, below
this module.

**The generators are free functions, and `VoiceLeadingEngine` keeps one-line
`@classmethod` delegates.** Roughly forty call sites in the tests and the front ends
spell them `VoiceLeadingEngine.get_drop2_voicings(...)`, and the delegate keeps those
spellings working. It leaves one implementation, so there is nothing to keep in step.

The four non-contiguous string sets - 6-4-3, both 5-3-2s and 6-4-3-2 - are
*searched* rather than stacked, because their voices are not in descending pitch
order down the strings: the A string is tuned five semitones above the D. See
`_search_shape`, which is the search they share.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, Iterable, List, Optional, Tuple

from musthe import Note

from .chords import ChordParser
from .grip_tables import (
    BOTTOM_FOUR,
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    GRIP_STRING_SETS,
    SHELL_DEGREES,
    TONE_PRIORITY,
    comping_string_sets,
    stated_tones,
    supported_string_sets,
)
from .tuning import (
    HIGH_FRET_LIMIT,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    STANDARD_TUNING,
    GuitarFretboard,
    Voicing,
    note_name,
)

# How each family's shape is placed, as two tables rather than a branch in the generator.
#
# A **layout** family's shape *is* its interval template: `_place_template` lays the
# template's voices on the strings from the soprano down, and the template and the string
# set fix every fret. A **searched** family's shape is a claim about what it sounds - both
# guide tones, or four chord tones with a root or a 5th underneath - and `_search_shape`
# finds it. The two are placed by different code, so a family listed in neither would
# generate nothing at all; `tests/test_grips.py` holds the two to partitioning the
# families, which is what makes a new one a decision rather than a silent omission.
_LAYOUT_GRIPS: Tuple[str, ...] = (
    "drop2", "closed", "drop3", "drop24", "duo", "interval",
)
_SEARCHED_GRIPS: Tuple[str, ...] = ("shell", "drop2_6432")


# The degrees a duo's **second voice** may take: the root, or the 5th.
#
# It gates the *second voice*, not the melody. A duo under a 3rd or a 7th in the melody
# is still a duo: that melody note is exactly the note a guide tone is there to support -
# the guide tone *beneath* it states the function - and it is the one case where the pair
# is unmistakably the chord rather than two passing notes. A melody gate on this list
# would suppress exactly those cases, so there is none; see `_duo_offsets`, which takes
# its second voice from SHELL_DEGREES and skips a unison so the fallback is never the
# melody itself.
#
# A melody that is not a chord tone never reaches the duo at all: the non-chord-tone
# strategies rewrite the chord before generation, which is why a b6 arrives here as the
# 9th or 13th of a resolved chord rather than as a passing note with a duo under it.
#
# It is still the root and the 5th, and still for the reason stated above: they are the
# two notes that carry no information about the chord's quality, so a pair built on
# either leaves the guide tone to do the work. `BASS_DEGREES_6432` below is the same
# rule applied to the bass rather than to a melody.
DUO_DEGREES: Tuple[int, int] = (0, 7)

# The degrees the low-E note may take in a 6-4-3-2 shape. The same rule as
# DUO_DEGREES, applied to the bass rather than to the melody, and for a stronger reason:
# the lowest voice is what *defines* the chord, so a 3rd or a 7th down there sounds like
# the wrong harmony rather than a voicing of this one. With no 5-4-3-2, a root in the
# bass is a consequence of which string set was chosen and never a decision; 6-4-3-2 is
# the one default shape that reaches the low E, and this rule is what makes it place a
# root there.
#   0 = root, 7 = 5th
BASS_DEGREES_6432: Tuple[int, ...] = (0, 7)


# --- Grip generation -------------------------------------------------------
#
# Everything below turns a chord quality and a melody note into semitone offsets
# below the soprano. It is deliberately separate from VoiceLeadingEngine so the
# theory - which notes go in a grip, and in what order - is stated once and can be
# read without reading the search that follows it.


def _nearest_tone_below(midi: int, pitch_class: int, max_drop: int = 24) -> Optional[int]:
    """
    The highest pitch at or below `midi` that has `pitch_class`, or None.

    Working in real pitches rather than in differences of pitch classes is what keeps
    octave placement honest. The root below a major 3rd is a major sixth down, not a
    major third down: taking the mod-12 difference and calling it the distance puts
    the root a fourth too high and produces voicings that spell the wrong octave.
    """
    for drop in range(max_drop + 1):
        candidate = midi - drop
        if candidate % 12 == pitch_class % 12:
            return candidate
    return None


def _close_stack_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: Optional[int] = None
) -> List[int]:
    """
    A four-voice close-position stack under the melody, as semitone offsets.

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
    """
    The degrees of this chord that define it: its 3rd (or 4th) and its 7th.

    Read off the tone set rather than tabulated, because it is a property of the chord
    and not of any voicing. The **major** 3rd is preferred where the set holds both
    (7alt carries b3 and 3, since it is an altered chord and either may be asked for),
    because the major one is the chord's actual identity; the b3 there is an option.

    **A suspended chord's guide tone is the 4th, not the 3rd.** Dsus7 is 1 4 5 b7: it has
    no 3rd at all, so a lookup for one finds nothing and reports *no* third - where the note
    that defines the sus chord as a sus chord is exactly that 4th. Two sus voicings have to
    agree about which note
    plays that role, and the hand tables already say so: `SHELL_DEGREES` gives 7sus4
    `(4, b7)` and sus4 `(4, 5)`, and every drop-2 template for those qualities keeps the
    same pair. Reading the tables here rather than re-deriving the rule is what keeps the
    three in step.

    A triad has no 7th, so either may be absent - the caller treats "no 7th" as
    "nothing to preserve" rather than as a failure.
    """
    present = set(t % 12 for t in tones)
    if root_pc is not None:
        present = {(t - root_pc) % 12 for t in tones}
    # The note standing in for the 3rd. In order of preference: a real 3rd, then the 4th
    # of a sus chord, then the 9th of sus2 (whose defining tone is the 9th, not the 2nd -
    # SHELL_DEGREES gives sus2 `(9, 5)`), then the 5th, which is all a bare 6/9 or an
    # incomplete chord leaves.
    third = next(
        (d for d in (4, 3, 5, 2, 7) if d in present), None
    )
    # The note standing in for the 7th: a real b7, a major 7th, or the 6th that replaces
    # both on a 6 or 6/9 chord - SHELL_DEGREES gives 6 and 6/9 `(3, 6)`, not `(3, b7)`.
    seventh = next(
        (d for d in (10, 11, 9) if d in present), None
    )
    return tuple(d for d in (third, seventh) if d is not None)



def _interval_set_for_grip(
    grip: str,
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: Optional[int] = None,
) -> List[List[int]]:
    """
    The close-position templates for one grip, as offsets from the soprano (0 for the
    melody itself, negative below it).

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
    Nth voice from the top lowered by an octave. The last voice of a drop-2 is
    therefore the octave of v2, not v4 - which is what makes the 3rd and the 7th of a
    seventh chord land on the D and G strings in the familiar 4-3-2-1 shell shape.
    """
    if grip not in ("drop3", "closed", "drop24"):
        return []

    stack = _close_stack_offsets(tones, melody_midi, root_pc)
    if len(stack) < 4:
        return []

    # stack[0] is the melody itself, so the three voices below it are stack[1:]. The
    # templates then read 0 (soprano), v1, v2, v3 as the four voices in the order they
    # sound.
    _, v1, v2, v3 = stack
    if grip == "closed":
        return [[0, v1, v2, v3]]

    # Drop 2 & 4: the SECOND and FOURTH voices each drop an octave. In the names below
    # `v1` is the *second* voice (stack[1]), `v2` the third and `v3` the fourth - which is
    # the source of the confusion this shape invites. So the two that drop are `v1` and
    # `v3`, and `v2` is the one that stays, nearest the melody. The sounding order top to
    # bottom is therefore v2, then v1 and v3 an octave down: `[0, v2, v1 - 12, v3 - 12]`.
    if grip == "drop24":
        # The same root-doubled triad problem as drop-3, and worse: a triad's fourth
        # voice is the doubled root, and dropping *it* as well as v1 puts the chord's
        # identity a further octave down while the third voice keeps the one it has.
        # The doubled root stays where the stack put it.
        if root_pc is not None and (melody_midi + v3) % 12 == root_pc % 12:
            return [[0, v2, v1 - 12, v3]]
        return [[0, v2, v1 - 12, v3 - 12]]

    # Drop 3: the THIRD voice from the top drops an octave. It therefore lands below
    # the bottom voice, so it is the *last* note in the template rather than the
    # third - the shape closes with a 2nd at the bottom. Writing [0, v1, v2 - 12, v3]
    # instead drops the second voice and strands v3 above it, which is not a drop-3 of
    # anything: for a Cmaj7 close stack of C5 B4 G4 E4 it produced C5 B4 G3 E4, with
    # E4 sounding above the G3 that was supposed to be the bass.
    #
    # A triad's fourth voice is the **doubled root** - `_close_stack_offsets` wraps to
    # it an octave down, which is how a three-note chord reaches four. Dropping that
    # voice an octave further is not a drop-3, it is a different chord: for Ebmaj under
    # G4 the stack is G4 Eb4 Bb3 G3, and dropping v2 (Eb4) gives G4 Bb3 G3 Eb3 - a b3
    # and a b7 against a major triad, which sounds as Eb minor. So where the voice
    # being dropped is the root, it is left where the stack put it and v3 takes the
    # octave instead.
    if root_pc is not None and (melody_midi + v2) % 12 == root_pc % 12:
        return [[0, v1, v3 - 12, v2]]
    return [[0, v1, v3, v2 - 12]]


def _duo_offsets(
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: int,
    canonical: str,
) -> List[int]:
    """
    A two-note grip under the melody, or an empty list.

    The second voice is **the chord's own guide tone**, read from `SHELL_DEGREES`
    rather than from a list written out here. That is the same table a shell is built
    from, and it already encodes the arranging guide's rule: the 3rd, or the **4th** on
    a suspended chord, with the 7th as the alternative. A hand-written `(4, 3, 0)` scan
    here would list no sus degree, so `sus4`, `sus2` and `7sus4` - whose guide tone is
    the 4th, the 9th and the 4th - would admit **no duo anywhere**; reading the shared
    table gives them one and cannot drift from the shell.

    Preference within the table is `[0]`, then `[1]`. The fallback is **load-bearing,
    not decorative**: when the melody *is* the 3rd, `[0]` would place a unison under it -
    the common case, the 3rd being the melody's own guide tone. A unison is not a second
    voice, so the 7th takes over and the pair becomes a 6th.

    **A 2nd under the melody is dropped an octave.** When the guide tone lands within
    two semitones of the melody the shape is a 2nd, which in two voices is where they
    fight rather than agree; the same pitch class an octave lower makes it a 9th, which
    sits. This is why the duo owns a skipped-string pair: on the adjacent pairs a 9th is
    unreachable inside `GRIP_MAX_SPAN["duo"]`, so a wider pair is what makes it voiceable at
    all. Two cases remain unreachable even now and return nothing rather than sound a 2nd;
    `tests/test_grips.py` names both.

    The melody may be **any** chord tone, not only a root or a 5th. A guide tone beneath a
    3rd or a 7th is exactly what states that note's function, and putting the guide tone
    first is what makes the pair read as the chord rather than as two passing notes. A
    melody that is not a chord tone at all never reaches here: the non-chord-tone
    strategies rewrite the chord before the generator runs, so a duo is always placed
    against a resolved harmony.
    """
    guide = SHELL_DEGREES.get(canonical)
    if guide is None:
        return []

    for degree in guide:
        if degree not in tones:
            continue
        pitch_class = (root_pc + degree) % 12
        # A unison is not a second voice: skip this guide tone and try the other.
        if pitch_class == melody_midi % 12:
            continue
        pitch = _nearest_tone_below(melody_midi, pitch_class)
        if pitch is None:
            continue
        # A 2nd under the melody becomes a 9th - see the docstring.
        while pitch >= 0 and melody_midi - pitch <= 2:
            pitch -= 12
        if pitch < 0:
            continue
        return [0, pitch - melody_midi]
    return []


# The intervals an `interval` grip will pair with the melody, in preference order:
# a minor 3rd, then a major 6th, then a minor 6th. All three are consonant with any
# melody note, which is what a *filling* texture needs - unlike a duo, which is
# claiming to state the chord.
_INTERVAL_CLASSES = (3, 9, 8)

def _interval_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: int
) -> List[List[int]]:
    """
    Two-note interval shapes under the melody: a 3rd, a 6th or a 10th, as templates.

    This is the arranging guide's "2-note intervals (3rds or 6ths)" - the texture it
    calls for in the gaps between a chord on a strong beat and the next one. It is a
    **texture, not a harmony**, and that distinction is the whole reason it is a
    separate grip rather than a widening of `_duo_offsets`:

      - It is NOT gated on `DUO_DEGREES`. A duo refuses to sound under a 3rd or a 7th
        in the melody, because there those two notes *are* the chord's function and a
        bare pair sounds like a mistake. An interval is not claiming the harmony, so
        it is free to sit under any melody note - which is exactly the case a fill
        most often has to cover, since a passing tone is by definition not a chord
        tone.
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

    # The major scale's pitch classes, used only as a fallback for a melody that is
    # not in the chord. A fill under a passing note should still have a bottom note,
    # but it must be a note the *key* contains - reaching for a chromatic one would be
    # reharmonising, not filling.
    key_pcs = {0, 2, 4, 5, 7, 9, 11}
    chord_pcs = {pc % 12 for pc in tones}

    templates: List[List[int]] = []
    seen: set = set()
    for source in (chord_pcs, key_pcs):
        for size in _INTERVAL_CLASSES:
            # A 3rd or a 6th may sit either side of the octave line, so both are
            # tried; a 10th is the same classes an octave lower.
            for octave in (0, 12):
                candidate = melody_midi - size - octave
                if candidate % 12 not in source:
                    continue
                offset = candidate - melody_midi
                if offset in seen:
                    continue
                seen.add(offset)
                templates.append([0, offset])
        if templates:
            # The chord's own tones are enough on their own; the key is a fallback
            # for a melody that is not in the chord, never an addition to it.
            break
    return templates


def _shell_request(
    quality: str,
    root_pc: int,
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Optional[_Placement]:
    """
    What a shell asks the search for on one string set: three voices, and both guide tones.

    A shell cannot come from a stack, and the reason is not specific to the 6-4-3 shape:
    **a shell's notes are not in descending pitch order down the
    strings.** The tuning is not monotonic in the useful direction. The A string is
    tuned five semitones *above* the D string, and the D string five above the G, so a
    note fretted on the lower string can easily sound higher than its neighbour. A G7
    shell under G3 is `2-3-0-x-x-x` - B2 on the A string, F3 on the D string, G3 on the
    G - and the A string is carrying the *lower* note while being the higher string.
    Any model that lays the voices on strings from the top down by pitch gets this
    backwards and finds nothing.

    So the shape is found by searching: the melody is held at `top_fret` on the soprano
    string and every combination of frets within the span limit is tried on the
    remaining strings, keeping the ones where the guide tones sound and nothing outside
    the chord does. This states the *request*; `_place_shape` is what answers it, so this
    and every other searched family cannot drift apart on what a candidate may sound or on
    how two equally playable ones are ranked.

    Returns None when the chord has no shell pair - a quality `SHELL_DEGREES` does not
    know, or a set too small to hold three voices.
    """
    guide = SHELL_DEGREES.get(quality)
    if guide is None or len(strings) < 3:
        return None
    return _Placement(
        grip="shell",
        # The three strings from the soprano down: a shell is a three-voice grip, so a set
        # with a fourth string in it places the shape on the top three.
        strings=strings[:3],
        melody_midi=melody_midi,
        top_fret=top_fret,
        # Both guide tones have to sound.
        required=frozenset((root_pc + g) % 12 for g in guide),
    )


def _drop2_6432_request(
    root_pc: int,
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> _Placement:
    """
    What the 6-4-3-2 family asks the search for: four voices, and a root or a 5th underneath.

    It cannot come from the interval-laid drop-2 table for the reason 6-4-3 cannot, and
    the reason is structural: **this set skips the A string, so its strings are not in
    descending pitch order.** The D string is tuned a fifth above the low E, so the low
    E's note is frequently *not* the lowest sounding pitch, and a table that lays voices
    down by interval cannot express a shape whose bottom string is not the bottom voice.

    The extra rule is BASS_DEGREES_6432: the low E carries the chord's root or its 5th.
    That is the entire point of the shape, and it is also why the family needs a root at
    all - a rootless quality has nothing to measure the low E against, and gets nothing.
    """
    return _Placement(
        grip="drop2_6432",
        strings=strings,
        melody_midi=melody_midi,
        top_fret=top_fret,
        # No guide-tone claim: the shape states four of the chord's own tones and the
        # string set decides which, exactly as the four-note families do.
        required=frozenset(),
        # The lowest voice carries the chord's *function* rather than its quality, so it is
        # a root or a 5th - read from BASS_DEGREES_6432, which is where that rule is stated.
        lowest_pc_allowed=frozenset(
            (root_pc + degree) % 12 for degree in BASS_DEGREES_6432
        ),
    )


def _searched_request(
    grip: str,
    canonical: str,
    root_pc: Optional[int],
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Optional[_Placement]:
    """
    What a **searched** family asks for on one string set, or None when it asks nothing.

    Every claim these families make is measured *from the root* - a shell states this
    chord's 3rd and 7th, and a 6-4-3-2 states the chord's function in the bass - so a chord
    whose root cannot be found gets nothing here. That is a limitation rather than a
    fallback: a shell is a claim about *this* chord, and guessing a guide tone is how a
    wrong note gets in.

    Returns None for a family this is not about, so a family listed in neither
    `_SEARCHED_GRIPS` nor `_LAYOUT_GRIPS` generates nothing rather than something nobody
    asked for.
    """
    if root_pc is None or grip not in _SEARCHED_GRIPS:
        return None
    if grip == "shell":
        return _shell_request(canonical, root_pc, strings, melody_midi, top_fret)
    return _drop2_6432_request(root_pc, strings, melody_midi, top_fret)


def _templates_for(
    grip: str,
    canonical: str,
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: Optional[int],
) -> List[List[int]]:
    """
    The interval templates a **layout** family places on one string set.

    A template is the shape, so nothing here is searched: `drop3`, `drop24` and `closed`
    are transformations of the close stack under the melody, drop-2 reads the tone-priority
    rule, and `duo` and `interval` are the two notes they name. Those last two are the ones
    that need a root, because each *names a chord tone* - a guide tone, or an interval from
    the root - where the others are built from the stack itself.

    `drop2` has two cases and they are told apart by what the melody *is*. A melody that is
    a chord tone takes the rule's own shape for its degree, and one shape only: offering
    the quality's other degrees would pin this melody to the soprano string and let each
    other template's top note fall *below* it, so the result sounds whatever those offsets
    happen to spell over this melody rather than the inversion the melody belongs in. A
    melody that is **not** a chord tone has no degree to match, and neither has a call with
    no root at all - both are offered the rule at every degree the chord has
    (`_drop2_palette`), which is where `voicing_cost`'s tone-purity criterion earns its
    place by choosing among them.
    """
    if grip == "duo":
        if root_pc is None:
            return []
        duo = _duo_offsets(tones, melody_midi, root_pc, canonical)
        return [duo] if duo else []
    if grip == "interval":
        # A texture rather than a claim about the chord, and built from templates because
        # an interval *is* the two notes it names.
        return [] if root_pc is None else _interval_offsets(tones, melody_midi, root_pc)

    if grip == "drop2":
        if root_pc is not None and tones:
            degree = (melody_midi - root_pc) % 12
            if degree in {t % 12 for t in tones}:
                shape = drop2_template_for(canonical, degree)
                return [shape] if shape else []
        return _drop2_palette(canonical)
    return _interval_set_for_grip(grip, tones, melody_midi, root_pc)


def _place_template(
    template: List[int],
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
    grip: str,
) -> Optional[Voicing]:
    """
    Fits an interval template onto a string set, or returns None if it will not play.

    The voices go on the strings from the top down, so the template's order is the
    order they are heard - which is what makes this a *layout*: the shape is the template,
    not a claim about which of the chord's tones sound. A family placed this way asks
    nothing of the tone set, and that is deliberate rather than lax: the template is the
    whole claim, and `interval` is free to sound a key tone under a passing note.

    The frets are computed rather than searched, because the template and the string set
    fix each one. What they are then held to is `_candidate`, the same rules every searched
    shape is held to, so the melody-on-top rule reaches the template families too.

    The span is checked on the frets actually placed, not as "within N of the soprano".
    Those are not the same condition: bounding each finger to five frets either side of
    the soprano permits a span of ten. That is reachable in practice - the low E and D
    strings are five semitones apart in tuning, so a 6-4-3 shell that sounds correctly
    on them can sit at frets 8 and 0.

    Strings in the set the template does not use are left muted, which is how a
    three-note shell sits inside a four-string set and how 6-4-3 leaves the A string
    alone without saying anything special about it.
    """
    if len(template) > len(strings):
        return None

    frets = [-1] * len(STANDARD_TUNING)
    frets[strings[0]] = top_fret
    for position, offset in enumerate(template[1:], start=1):
        string_idx = strings[position]
        frets[string_idx] = (
            melody_midi + offset - STANDARD_TUNING[string_idx].midi_note()
        )

    return _candidate(
        _Placement(
            grip=grip,
            strings=strings,
            melody_midi=melody_midi,
            top_fret=top_fret,
            required=frozenset(),
            # The template's own voices, which may be fewer than the set offers - the rest
            # of the set is muted.
            voices=len(template),
        ),
        frets,
        # No claim about the chord's tones - the template is the claim.
        None,
    )


# --- The drop-2 rule -----------------------------------------------------------
#
# One shape per degree, computed rather than tabulated. `TONE_PRIORITY` above says which
# of the chord's tones a shape states; these two say what the shape *is*.


def drop2_template_for(quality: str, degree: int) -> List[int]:
    """
    The textbook drop-2 of the tones `degree` states, as offsets below the soprano.

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
    row or no tone set, and for a degree the rule cannot build a shape for. Measured over
    every chord tone of all 29 qualities (125 degrees): none empty, none sounding a note
    outside the chord, and every one stating both guide tones, which is what
    `tests/test_generated_grips.py` holds it to.
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
    """
    Every drop-2 shape the rule builds for a quality, in the rule's own order.

    This is what a melody with **no degree to match** is offered: one that is not a chord
    tone, and any call with no root at all. Each shape's top voice *is* the melody by
    construction, so the palette is the set of harmonisations the rule can put under it,
    and `voicing_cost` chooses among them - tone purity first, so the shapes that state
    the chord rank above the ones that merely fit.

    Shaped off `TONE_PRIORITY` rather than a list of degrees, which is what makes the
    palette the same rule as a single shape: the degrees a quality has *are* its priority
    row, so there is no second table to keep in step with this one.
    """
    return [
        shape
        for degree in TONE_PRIORITY.get(quality, ())
        if (shape := drop2_template_for(quality, degree))
    ]



def _parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
    """Delegates to ChordParser for backward compatibility."""
    return ChordParser.parse_chord_name(name)


def _string_sets_for(grip: str, top_string: int) -> List[Tuple[int, ...]]:
    """
    Every string set `grip` can occupy with its soprano on `top_string`, each
    **ordered from the soprano downwards**, which is the order _place_template
    assigns voices in.

    A list rather than one set, because a grip can have more than one shape for the
    same string: a G-string shell is either 5-4-3 or 6-4-3, and returning only the
    first would silently hide 6-4-3 behind 5-4-3.

    For drop-2 the set is simply the four strings from the soprano down, which
    uses the four strings below the soprano for *any* top_string and so keeps
    get_drop2_voicings working for callers who pass their own. The other grips come
    from a fixed table (GRIP_STRING_SETS, stored low-to-high for readability) because
    they are named shapes: a 6-4-3 shell is that shape or it is nothing, and it is
    not available on every string.

    The table lists each set low-to-high, so the soprano is found by *searching* for
    it rather than by assuming an end: for a 1-2-3 shell the soprano is the first
    entry, for 6-4-3 it is the last, and a duo like (5, 4) happens to start on it.
    Every entry names its soprano as its **highest** string, so ordering the set
    descending is what puts the soprano first.

    Descending order, and specifically *not* a rotation. Rotating the stored
    low-to-high tuple from the soprano (`strings[pivot:] + strings[:pivot]`) looks
    equivalent and is not: for the four-string block stored (2, 3, 4, 5) with the
    soprano on 5 it yields (5, 2, 3, 4), which walks *up* the neck for the next
    three voices. That hands a voice the G-string note on the G string, the D-string
    note on the D string and the B-string note on the B string while claiming to
    descend - the pitches are right and the strings are not, and the span check then
    measures frets on strings the voice was never meant for. A rotation is only
    order-preserving if the tuple is already in the order being rotated *into*, and
    this one is stored the other way up.
    """
    if grip == "drop2":
        # A caller may pass any `top_string`, and the rule is that the four strings below
        # it are used, so a top_string with no table entry still works. The table is
        # consulted only where it has an entry - which is what adds the bass-skipping
        # sets, since they are keyed on the soprano they belong to.
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
        # A G-string soprano has no four-note block: see BOTTOM_FOUR. Shells and
        # duos still apply there, and the table below lists them.
        if frozenset(strings) == BOTTOM_FOUR:
            return []
        return [strings]
    sets: List[Tuple[int, ...]] = []
    for strings, soprano in GRIP_STRING_SETS.get(grip, ()):
        if soprano == top_string and soprano in strings:
            sets.append(tuple(sorted(strings, reverse=True)))
    return sets


def _chord_context(
    chord_type: str, chord_name: Optional[str]
) -> Tuple[str, Optional[int], Tuple[int, ...]]:
    """
    The canonical quality, the root's pitch class, and the chord's tones **as
    degrees from that root**.

    The degrees are deliberately not absolute. Every grip builder wants to reason
    in intervals - "the 3rd of a minor 7th is three semitones up" - and only the
    final pitch placement wants an absolute note. Keeping one frame throughout means
    there is a single place (the search for a pitch at or below the soprano) where
    degrees become pitches, and a chord whose root cannot be found simply yields
    nothing rather than being transposed by accident.

    Note this is *not* ChordParser.get_chord_tones(quality, chord_name), which
    returns absolute pitch classes once a name is supplied. The tones are the full
    set for the quality, not the four the drop-2 tables voice, so a shell or a duo
    is built from every tone the chord really has.

    A quality with no usable root - a bare quality symbol with no chord name, or an
    unparseable root - has root_pc of None, and only the drop-2 path still serves it,
    because those tables are written as offsets from the soprano and need no root.
    """
    canonical = ChordParser.canonical_quality(chord_type)
    root_pc: Optional[int] = None
    root_str, _ = ChordParser.parse_chord_name(chord_name) if chord_name else (None, None)
    if root_str:
        try:
            root_pc = Note(f"{root_str}4").midi_note() % 12
        except (KeyError, ValueError, TypeError):
            root_pc = None
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical, ())
    return canonical, root_pc, tones


def _shell_voicing(
    frets_by_string: Tuple[int, ...],
    frets: Tuple[int, ...],
    midis: List[int],
    canonical: str,
    root_pc: int,
    tones: Tuple[int, ...],
    notes: int = 3,
    bass_voice: bool = False,
    shell_root: bool = False,
) -> Optional[Voicing]:
    """
    One comping candidate, or None when it does not state the chord.

    Both guide tones must sound and nothing outside the chord may, which is the rule
    `_candidate` enforces for the melody-bearing shell and the reason this one shares its
    vocabulary. Shared by the melody-bearing shell and the melody-free one so the
    two cannot drift apart on what counts as a shell.

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

    **`shell_root` is the third way to spend the bottom of the shape**, and the only one
    that asks for *more* than a plain guide-tone shape: both guide tones, and a bass
    degree underneath them, so the ear hears which chord it is as well as what quality.
    It is checked as the conjunction of the two rules above rather than as a third list,
    which is why it can be added without deciding anything new about degrees - see
    `HARMONY_STYLES` in `harmony.py`, which is where the *vocabulary* lives.
    """
    guide = SHELL_DEGREES.get(canonical)
    if guide is None:
        return None
    if len(frets_by_string) < notes:
        return None
    pcs = {midi % 12 for midi in midis}
    if bass_voice:
        # The same containment check every other candidate makes, before anything else.
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not pcs <= allowed:
            return None
        # Root first, then the 5th: the degree order is `BASS_DEGREES_6432`'s, and it is
        # tried as a preference rather than required, so a chord whose root cannot be
        # fretted here still gets a bass note instead of no note.
        for degree in BASS_DEGREES_6432:
            if (root_pc + degree) % 12 in pcs:
                break
        else:
            return None
    elif shell_root:
        # **The new case, and it is a conjunction of two rules rather than a third one.**
        # A `shell_root` shape says both things at once: the guide tones state the chord's
        # *quality*, and a bass degree underneath says which chord it is. Each half is
        # already stated by a table - `SHELL_DEGREES` for the first, `BASS_DEGREES_6432`
        # for the second - so the check is both of those, applied, and not a new list
        # written here that could drift from either.
        #
        # The containment check comes first and unconditionally, exactly as in every
        # other branch: a shape sounding a note outside the chord is not a voicing of
        # this one whatever else it gets right.
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not pcs <= allowed:
            return None
        needed = {(root_pc + degree) % 12 for degree in guide}
        if not needed <= pcs:
            return None
        # **The lowest note, not merely *a* note of that degree.** This is the whole
        # difference between this family and a guide-tone shape, and it is the part that
        # is easy to get wrong: on an `Ebmaj` whose guide tones are D and G, a shape of
        # `D G Bb` already *contains* a fifth (Bb), so a check for "some bass degree is
        # sounding" is satisfied by the plain guide-tone shape and this family would
        # silently be a synonym for `guide`. Stating the harmony from the bottom up
        # means the bass degree is the one the ear hears **first**, so it is checked on
        # the lowest sounding note rather than on the set.
        #
        # Root first, 5th as the fallback: the same preference order `BASS_DEGREES_6432`
        # states, read here rather than re-decided, because the root is the note that
        # names the chord and a 5th names it only in company.
        lowest = min(midis) % 12
        if lowest not in {(root_pc + degree) % 12 for degree in BASS_DEGREES_6432}:
            return None
    else:
        # **One voice is a weaker claim, and the rule says so rather than refusing.** Two
        # notes can sound both guide tones, which is what states the chord; one note cannot,
        # and a single note *is* the whole of a `duo` - the grip family this library has
        # always offered for "the melody plus one guide tone". So a one-voice selection keeps
        # the **first** guide tone (the 3rd, or the 4th on a sus chord) and drops the second,
        # which is the same preference order `_duo_offsets` already applies.
        #
        # Refusing here would instead make `--texture chord1` fall through to the ordinary
        # melody-bearing route, which states the horn's line on the guitar on every step
        # and hands it back - the opposite of what asking for one note meant.
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


def _search_comping_voicings(
    chord_type: str,
    chord_name: Optional[str] = None,
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    notes: int = 3,
    bass_voice: bool = False,
    shell_root: bool = False,
) -> List[Voicing]:
    """
    Guide-tone comping shapes: the chord stated **without** the melody on top.

    This is the guitarist's part when somebody else has the tune - a horn in front of
    the band - which is why it takes no melody argument at all. Every other candidate
    in this module is built around pinning the melody to the soprano string; this is
    the one that has none to pin.

    **It is the same exhaustive search with nothing held at the top.** A shell is
    already a claim about the chord's 3rd and 7th rather than about the tune, so the
    search needed no new rule: `_frets_in_span` already tries every fret combination on
    the remaining strings and the candidate keeps the ones where both guide tones sound
    and nothing outside the chord does. The only difference is that the top fret is searched too
    rather than fixed by a melody, and the shape is ranked on spread and position
    instead of against a pinned note. Because the window is exactly `GRIP_MAX_SPAN`,
    the search stays exhaustive within the playability invariant.

    Only the `shell` string sets are offered, and that is the musical claim rather
    than a limitation: with no melody to support, a fourth voice would be the root or
    the 5th - the two notes that carry no information about the chord's quality. The
    guide tones are what state whether the ear hears a major or a minor chord.

    `notes` is the **arity asked for**, and it is honoured rather than treated as a
    preference: `2` is the alto-and-tenor comping pair, `3` the shell. A string set too
    small for the request is **skipped rather than padded**, because a part sounding more
    notes than the caller named is worse than a thinner one - the extra note is a voice
    somebody else was supposed to have.

    **`bass_voice` is what stops the arity from being the whole question.** It is True
    only for a selection naming the bass and nothing else, and it does two things: it
    offers the bottom-of-neck string sets instead of the `duo` tops (so the note lands
    in a bass register rather than the middle of the neck), and it takes the note from
    `BASS_DEGREES_6432` rather than `SHELL_DEGREES` (so it is a root or a 5th rather than
    a 3rd). Both are needed and neither is enough: a low 3rd is still not a bass note.

    **`shell_root` asks for both guide tones *and* a root or 5th under them**, which is
    the claim neither flag above can state: `bass_voice` spends the whole shape on the
    bass, and the default spends it on the guide tones alone. It is a `harmony=` value
    rather than a change of arity, because it is a claim about *which degrees sound* and
    not about how many notes there are - the same reason `HARMONY_STYLES` is a table of
    degree families and not a count. It resolves on the **existing** `(5,4,3)` shell sets,
    so no new string set is involved - `docs/history/comping-styles.md` holds the measurement.

    Every candidate sounds only chord tones, holds a fret span of at most
    `GRIP_MAX_SPAN["shell"]`, and occupies one string set from `GRIP_STRING_SETS["shell"]`
    - or, for a bass voice, one from `BASS_VOICE_STRING_SETS` / the `duo` tops. **Unlike
    every other candidate in the library, none of these carries a melody**, so the
    invariant that a voicing sounds the melody on its topmost string does not apply to
    them and is not asserted - see `tests/test_comping.py`.

    `fret_min`/`fret_max` bound the search the way they bound the selector everywhere
    else: as a **preference**, never a filter. A chord whose comping shape sits
    outside the window is still generated and still playable, because losing a chord
    of the tune is worse than being a fret out of position.
    """
    canonical, root_pc, tones = _chord_context(chord_type, chord_name)
    # No root, no claim to make: a guide tone is a claim about *this* chord's 3rd and
    # 7th, and guessing them without a root is how a wrong note gets in. The same
    # rule, and the same reason, as `get_grip_voicings`'s shell and duo branches.
    if root_pc is None:
        return []

    limit = GRIP_MAX_SPAN["shell"]
    # The board, not the window: `fret_max` is a preference `voicing_cost` applies, so
    # searching past it and letting the selector rank is what keeps a chord of the tune
    # from vanishing. Clamped at 18, which is the end of the neck.
    hi = min(fret_max + limit, 18)
    lo = max(0, fret_min - limit)

    valid: List[Voicing] = []
    for used in comping_string_sets(notes, bass_voice):
        best: Optional[Tuple[Tuple[int, float], Voicing]] = None
        for frets in _frets_in_span(used, lo, hi, limit):
            midis = sorted(
                GuitarFretboard.fret_to_midi(string, fret)
                for string, fret in zip(used, frets)
            )
            found = _shell_voicing(
                used, frets, midis, canonical, root_pc, tones, notes, bass_voice,
                shell_root,
            )
            if found is None:
                continue
            # Ranked here rather than by `voicing_cost`, because this is a *generator*
            # and choosing is the selector's job - the split every other family keeps.
            # One per string set: a tighter shape lower on the neck is the one a player
            # would pick, and offering the rest would only give the selector a worse
            # shape to lose.
            key = (max(frets) - min(frets), sum(frets) / len(frets))
            if best is None or key < best[0]:
                best = (key, found)
        if best is not None:
            valid.append(best[1])
    return valid


@lru_cache(maxsize=None)
def _comping_palette(
    chord_type: str,
    chord_name: Optional[str],
    fret_min: int,
    fret_max: int,
    notes: int,
    bass_voice: bool,
    shell_root: bool,
) -> Tuple[_ShapeSnapshot, ...]:
    """
    `_search_comping_voicings` remembered: one request enumerated once, read back after.

    The enumeration is a **pure function of the request**: the seven arguments above are
    all it reads, and the rest - `GRIP_STRING_SETS`, `BASS_VOICE_STRING_SETS`,
    `GRIP_MAX_SPAN`, `NECK_FRET_MIN`, `NECK_FRET_MAX`, `STANDARD_TUNING` and
    `ChordParser.CHORD_TONES_FROM_ROOT` - is fixed when this module is imported. That is
    what makes the key sufficient and the memo need no invalidation, and it is why those
    tables must not be reassigned at runtime. Same argument, and the same snapshot, as
    `_searched_shape`.

    The same request is asked repeatedly: every slot of a comping bar, every head of a
    sweep, and every caller that arranges a head another caller has already arranged.
    The counts are in `docs/history/comping-styles.md`.
    """
    return tuple(
        _snapshot(voicing)
        for voicing in _search_comping_voicings(
            chord_type,
            chord_name,
            fret_min,
            fret_max,
            notes,
            bass_voice,
            shell_root,
        )
    )


def get_comping_voicings(
    chord_type: str,
    chord_name: Optional[str] = None,
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    notes: int = 3,
    bass_voice: bool = False,
    shell_root: bool = False,
) -> List[Voicing]:
    """
    The comping shapes for one request, answered through the memo.

    **A fresh list of fresh `Voicing`s on every call**, which is why this is a wrapper
    around the memo rather than the memoised function itself: `decisions.select_step_voicing`
    hands one of these objects back and `bass_merge.attach_bass` then writes the walked
    thumb into its fret vector and `bass_pc`. Returning the stored objects would let one
    step's bass line rewrite the palette the next step is offered.

    The rules - the string sets, the degrees, the window - are
    `_search_comping_voicings`'s docstring; the memo changes nothing but how often the
    enumeration runs, which `tests/test_comping.py` holds it to.
    """
    return [
        _voicing_from_snapshot(snapshot)
        for snapshot in _comping_palette(
            chord_type,
            chord_name,
            fret_min,
            fret_max,
            notes,
            bass_voice,
            shell_root,
        )
    ]


def _frets_in_span(
    strings: Tuple[int, ...], lo: int, hi: int, limit: int
) -> Iterable[Tuple[int, ...]]:
    """Every fret tuple on `strings` inside `lo`..`hi` whose span is at most `limit`.

    Written as a recursive generator rather than one nested loop per arity, because
    `notes` is a parameter and the alternative is a separate copy of this search for
    every arity - which is exactly how the melody-bearing shell and this one drifted
    apart the first time they were written separately.

    The window narrows as it recurses (`first - limit` .. `first + limit`), so the
    search is still exhaustive over span-legal combinations and never materialises the
    ones the span rule would reject.
    """
    if not strings:
        yield ()
        return
    rest = strings[1:]
    for first in range(lo, hi + 1):
        window_lo = max(lo, first - limit)
        window_hi = min(hi, first + limit)
        for tail in _frets_in_span(rest, window_lo, window_hi, limit):
            yield (first,) + tail


@dataclass(frozen=True)
class _Placement:
    """
    One family's request of the placement search: where to sit, and what must sound.

    A *value*, so a caller states the request and the search answers it - which is what
    lets the non-contiguous families share one placement instead of each owning a nest of
    loops. `strings` is ordered from the soprano downwards, as `_string_sets_for` returns
    it, so `strings[0]` is the string the melody is pinned to and `melody_midi` is that
    pin's pitch.

    `required` is the family's claim about which of the chord's tones have to be present,
    as pitch classes; **empty means the family makes no claim** and any subset of the
    chord's own tones will do, which is the drop-2 & 4 rule - it states four chord tones
    and leaves which ones to the string set. `lowest_pc_allowed` is the separate claim about
    the **bottom** voice, for the families whose shape is defined by its bass (a 6-4-3-2
    states the chord's function, so its lowest note is a root or a 5th); None asks nothing.

    `voices` is how many of `strings` the shape sounds, counting down from the soprano, and
    None means all of them. It exists because a template may be shorter than the set it sits
    on - a two-note pair on a three-string shell set - and the shape then has to leave the
    rest of the set **muted** rather than placing a voice there.
    """

    grip: str
    strings: Tuple[int, ...]
    melody_midi: int
    top_fret: int
    required: FrozenSet[int]
    lowest_pc_allowed: Optional[FrozenSet[int]] = None
    voices: Optional[int] = None


#: The string sets a candidate may sound, as one set for the membership test `_candidate`
#: makes. Built from `supported_string_sets()`, which is the playability invariant stated
#: from the shape's side, so no producer can put a shape on strings the tables never
#: offered - a set is a musical decision, and this is what makes it one rather than an
#: accident of which strings a producer happened to fill in.
_SUPPORTED_STRING_SETS = frozenset(supported_string_sets())


def _candidate(
    placement: _Placement, frets: List[int], allowed: Optional[FrozenSet[int]]
) -> Optional[Voicing]:
    """
    The one place a set of frets becomes a candidate voicing, or None when it is not one.

    Every rule a candidate has to satisfy is here, so no family can be placed by a path that
    skips one: the melody sounds and is the **highest** sounding note, every fret is on the
    board, the fret span is within `GRIP_MAX_SPAN[placement.grip]`, the family's tone claim
    (`required`) and bass claim (`lowest_pc_allowed`) hold, nothing outside `allowed`
    sounds - `allowed` being None when the family makes no claim about the chord's tones at
    all, which is what a template-laid shape is: the template *is* the claim, and the
    interval family is free to sound a key tone under a passing note - and the sounding
    strings are one `supported_string_sets()` entry.

    Both proposers call it: the search (`_search_shape`, reached through the memo
    `_place_shape`), which enumerates frets, and the layouts (`_place_template`), which
    compute them from an interval template. One producer per shape, one rule set for all of
    them - a rule stated in a producer reaches only the families that producer serves.

    `frets` is a full board vector, and only its entries for `placement.strings` are read.
    The `voices` strings from the soprano down are the shape and must each carry a fret
    between 0 and 18; **the rest of the set must be muted**. Both halves matter: a computed
    -1 is a note below its string's open pitch rather than a mute, and reading that as
    unused thins the shape into strings the tables never offered.
    """
    strings = placement.strings
    top_fret = placement.top_fret
    limit = GRIP_MAX_SPAN[placement.grip]

    set_frets = [frets[string] for string in strings]
    voices = len(strings) if placement.voices is None else placement.voices
    used, unused = set_frets[:voices], set_frets[voices:]
    if any(fret < 0 or fret > 18 for fret in used):
        return None
    if any(fret != -1 for fret in unused):
        return None
    if frozenset(strings[:voices]) not in _SUPPORTED_STRING_SETS:
        return None
    if not used or max(used) - min(used) > limit:
        return None
    sounded = strings[:voices]
    active = used
    midis = sorted(
        GuitarFretboard.fret_to_midi(string, fret)
        for string, fret in zip(sounded, active)
    )
    if midis[-1] != GuitarFretboard.fret_to_midi(strings[0], top_fret):
        return None
    pcs = {midi % 12 for midi in midis}
    if not placement.required <= pcs:
        return None
    if allowed is not None and not pcs <= allowed:
        return None
    if (
        placement.lowest_pc_allowed is not None
        and midis[0] % 12 not in placement.lowest_pc_allowed
    ):
        return None
    return Voicing(
        frets=list(frets),
        top_fret=top_fret,
        avg_fret=sum(active) / len(active),
        grip=placement.grip,
        bass_pc=midis[0] % 12,
    )


def _search_shape(
    placement: _Placement, allowed: Optional[FrozenSet[int]] = None
) -> Optional[Voicing]:
    """
    The one shape `placement` asks for on its string set, or None when it will not play.

    `_place_shape` is what the generators call; this is the search they are answered with.

    An enumerator over `_frets_in_span`, and `_candidate` is what decides: the melody is
    held at its own fret and every combination of the other frets within
    `GRIP_MAX_SPAN[placement.grip]` of it is tried, so if a playable shape exists in this
    position this finds it, and "found nothing" means there is none.

    A window that runs off the end of the board yields nothing, which is the melody being
    too high to voice here rather than a shape being refused: `get_octave_down_candidates`
    is what covers a melody above the neck window.

    **Ties are broken by fret spread, then by position**, so the shape a player would pick
    wins over the first one the search reaches; and of two still equal the earlier one
    survives, which is the enumeration order `_frets_in_span` yields in. Ranking the
    survivors is not cosmetic: an unranked search returns whatever comes first, so a family
    can look as though it is never selected when it is merely ranked last.
    """
    strings = placement.strings
    top_fret = placement.top_fret
    limit = GRIP_MAX_SPAN[placement.grip]

    lo = max(0, top_fret - limit)
    hi = top_fret + limit
    if hi > 18:
        return None

    best: Optional[Tuple[Tuple[int, float], Voicing]] = None
    for tail in _frets_in_span(strings[1:], lo, hi, limit):
        frets = [-1] * len(STANDARD_TUNING)
        for string, fret in zip(strings, (top_fret,) + tail):
            frets[string] = fret
        voicing = _candidate(placement, frets, allowed)
        if voicing is None:
            continue
        key = (voicing.fret_span(), voicing.avg_fret)
        if best is None or key < best[0]:
            best = (key, voicing)
    return best[1] if best else None


#: Everything a `Voicing` carries, with the fret vector as a tuple: what `_searched_shape`
#: and `_comping_palette` store. A result is snapshotted rather than stored as a `Voicing`
#: so that no caller can write through a memo - `bass_merge.attach_bass` merges the walking
#: bass by writing into the chosen shape's fret vector and `bass_pc`.
_ShapeSnapshot = Tuple[
    Tuple[int, ...], int, float, str, Optional[int], str, Optional[int], Optional[int]
]


def _snapshot(voicing: Voicing) -> _ShapeSnapshot:
    """One `Voicing` as the tuple the memos store, so the object cannot be written to."""
    return (
        tuple(voicing.frets),
        voicing.top_fret,
        voicing.avg_fret,
        voicing.grip,
        voicing.bass_pc,
        voicing.role,
        voicing.bass_midi,
        voicing.bass_string,
    )


def _voicing_from_snapshot(snapshot: _ShapeSnapshot) -> Voicing:
    """A **fresh** `Voicing` with a **fresh** fret vector, rebuilt from `snapshot`."""
    frets, top_fret, avg_fret, grip, bass_pc, role, bass_midi, bass_string = snapshot
    return Voicing(
        frets=list(frets),
        top_fret=top_fret,
        avg_fret=avg_fret,
        grip=grip,
        bass_pc=bass_pc,
        role=role,
        bass_midi=bass_midi,
        bass_string=bass_string,
    )


@lru_cache(maxsize=None)
def _searched_shape(
    placement: _Placement, allowed: Optional[FrozenSet[int]]
) -> Optional[_ShapeSnapshot]:
    """
    `_search_shape` remembered: one request searched once, and read back after that.

    The search is a **pure function of the request**. `placement` and `allowed` carry
    everything it reads, and the rest - `GRIP_MAX_SPAN`, `STANDARD_TUNING`,
    `supported_string_sets()` - is fixed when this module is imported. That is what makes
    the key sufficient and the memo need no invalidation, and it is why those tables must
    not be reassigned at runtime.

    The same request is asked over and over: a repeated melody degree, a repeated bar, and
    the target, fill and retry paths each asking again for what was answered already. The
    counts are in `docs/history/generated-grips.md` §4.
    """
    found = _search_shape(placement, allowed)
    if found is None:
        return None
    return _snapshot(found)


def _place_shape(
    placement: _Placement, allowed: Optional[FrozenSet[int]] = None
) -> Optional[Voicing]:
    """
    The one shape `placement` asks for, answered through the memo.

    **A fresh `Voicing` with a fresh fret vector on every call.** The engine writes into
    the shape it chose - `bass_merge.attach_bass` sets `frets[string]` and `bass_pc` for the
    walking bass - so returning the stored object would let one step's thumb line rewrite
    the shape the next step is handed.

    The rules, the ranking and the enumeration order are `_search_shape`'s docstring; the
    memo changes nothing but how often the search runs, which `tests/test_placement.py`
    holds it to.
    """
    snapshot = _searched_shape(placement, allowed)
    if snapshot is None:
        return None
    return _voicing_from_snapshot(snapshot)


def get_grip_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_string: int = 5,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """
    Generates fingerings for `grips` on one string block, pinned to the melody.

    This is the general form of get_drop2_voicings, and with `grips=("drop2",)` it
    produces exactly what that method always has. The other families differ in what
    they carry rather than in where they sit:

      drop2   four voices, from the tone-priority rule (`drop2_template_for`)
      drop3   four voices, a close stack with the third voice dropped
      drop24  four voices, a close stack with the second *and* fourth dropped
      closed  four voices in close position under the melody
      shell   three voices: the 3rd, the 7th, and one more
      duo     two voices, and only under a root or a 5th (see DUO_DEGREES)
      interval  two voices a 3rd, 6th or 10th apart - a fill, and under *any*
               melody degree (see _interval_offsets for why that is safe)

    Candidate generation is *pure*. It does not filter by neck position, does not
    transpose, and does not know what came before - choosing among the results is
    best_voicing's job. Keeping that split is what stops the grip families and the
    octave-down rescue from having to know about each other.

    Every candidate uses 2-4 strings belonging to one `supported_string_sets()` entry,
    carries the melody as the **highest** sounding note, and holds a fret span of at most
    `GRIP_MAX_SPAN[grip]`. It sounds chord tones only, with one deliberate exception: an
    `interval` fill may sit a diatonic tone of the key under a melody that is not a chord
    tone, because a fill is a texture rather than a claim about the chord - see
    `_interval_offsets` for why that cannot quietly reharmonise the bar.
    """
    melody_midi = melody_note.midi_note()

    top_fret = GuitarFretboard.note_to_fret(top_string, melody_note)
    if top_fret < 0 or top_fret > 18:
        return []

    canonical, root_pc, tones = _chord_context(chord_type, chord_name)

    # The chord's tones as pitch classes: what `_candidate` holds a searched shape's own
    # notes to. Computed once, because every searched family measures the same chord.
    allowed = (
        None if root_pc is None else frozenset((root_pc + t) % 12 for t in tones)
    )

    valid_voicings: List[Voicing] = []
    for grip in grips:
        for strings in _string_sets_for(grip, top_string):
            if grip not in _SEARCHED_GRIPS:
                # A layout family: each template *is* a shape, so each is placed in turn.
                for template in _templates_for(
                    grip, canonical, tones, melody_midi, root_pc
                ):
                    voicing = _place_template(
                        template, strings, melody_midi, top_fret, grip
                    )
                    if voicing is not None:
                        valid_voicings.append(voicing)
                continue
            # A searched family: one shape per string set, and the search finds it.
            request = _searched_request(
                grip, canonical, root_pc, strings, melody_midi, top_fret
            )
            if request is None:
                continue
            found = _place_shape(request, allowed)
            if found is not None:
                valid_voicings.append(found)

    return valid_voicings
def get_drop2_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_string: int = 5,
) -> List[Voicing]:
    """
    Generates valid 4-string Drop-2 fretboard fingerings pinned to the melody note.

    top_string is the index of the string carrying the melody: 5 (high E) yields the
    traditional D-G-B-E shape, while 4 (B) yields the lower A-D-G-B shape used when
    the melody sits below the high E string's open pitch. When chord_name (e.g.
    'Dm7b5') is provided, it matches the specific inversion where melody_note
    functions as the correct chord tone.

    Kept as a named entry point because it is what callers reach for directly and
    its output is part of the library's published behaviour. It is exactly
    get_grip_voicings with the grip pinned to drop-2.
    """
    return get_grip_voicings(
        melody_note, chord_type, chord_name, top_string, grips=("drop2",)
    )


def get_interval_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_string: int = 5,
) -> List[Voicing]:
    """
    Two-note interval fingerings under the melody: a 3rd, a 6th or a 10th.

    The arranging guide's fill for the notes between a chord on a strong beat and
    the next one. It is a **texture and not a harmony** - it says nothing about
    what the chord is, and it is meant to sit on a weak beat - so unlike a duo it
    is offered under *any* melody degree, including a 3rd or a 7th that a duo
    refuses. The **fill-only palette** is what confines it to fill slots, which is what
    makes the looser rule safe.

    Kept as a named entry point for the same reason as `get_drop2_voicings`: every
    grip family is reachable from the public surface, so a caller who wants a
    single one does not have to know the tuple spelling. It is exactly
    get_grip_voicings with the grip pinned to "interval".

    Returns an empty list when the chord has no usable root, or when the melody is
    unreachable on that string - the same limitation every root-measured grip has.
    """
    return get_grip_voicings(
        melody_note, chord_type, chord_name, top_string, grips=("interval",)
    )


def _lower_soprano_strings(top_strings: Tuple[int, ...]) -> Tuple[int, ...]:
    """
    The subset of `top_strings` below the high E, so a transposed melody is voiced
    on the B string rather than back on the high E. Falls back to `top_strings`
    when it contains nothing below the high E, so a caller restricted to (5,)
    still gets a (higher) voicing instead of nothing.
    """
    lower = tuple(s for s in top_strings if s < len(STANDARD_TUNING) - 1)
    return lower or tuple(top_strings)


def _melody_only_string_groups(
    prefer: Tuple[int, ...],
) -> List[Tuple[Tuple[int, ...], int]]:
    """
    The (strings, octave shift) groups a melody-only voicing is searched in, in order.

    **The first group that can carry the note is the whole palette** - the choice among
    its members is `cost.voicing_cost`'s, exactly as it is for a chord - so a group is a
    claim about which strings the caller allowed rather than about tone, and it is the
    same claim `top_strings` makes everywhere else:

    1. the strings in `prefer`, in the order given, at the written pitch. A caller that
       names one soprano string gets candidates on that string alone while it can carry
       the note: the fallback below is a rescue for a note the named set cannot reach,
       never a licence to widen a named set;
    2. every other string from the highest sounding one down, at the written pitch, so a
       low melody such as G3 still sounds on the open G string rather than being refused;
    3. and 4. the same two an octave down, so a melody that is playable but only above
       HIGH_FRET_LIMIT is played in a comfortable position rather than dropped. The high
       E returns in group 4 whenever it was named, which is where a note high enough to
       need the transposition lands once it is an octave lower.

    Duplicates and out-of-range indices in `prefer` are ignored, so a caller cannot make
    the search repeat a string or index past the fretboard.
    """
    top = len(STANDARD_TUNING) - 1
    named: Tuple[int, ...] = ()
    for string_index in prefer:
        if 0 <= string_index <= top and string_index not in named:
            named += (string_index,)
    lower = _lower_soprano_strings(named)

    def rest(excluded: Tuple[int, ...]) -> Tuple[int, ...]:
        """Every string not in `excluded`, from the highest sounding one down."""
        return tuple(s for s in range(top, -1, -1) if s not in excluded)

    return [
        (named, 0),
        (rest(named), 0),
        (lower, -12),
        (rest(lower), -12),
    ]


def _melody_only_voicings_on(
    melody_note: Note,
    strings: Tuple[int, ...],
    octave_shift: int,
) -> List[Voicing]:
    """
    One single-fret Voicing per string in `strings` that can carry `melody_note`, in the
    order given. The shift is applied to the *note*, not to the fret, so an octave-down
    attempt asks the fretboard the same question it would ask of the written pitch.
    """
    shifted = Note(note_name(melody_note.midi_note() + octave_shift))
    candidates: List[Voicing] = []
    for string_index in strings:
        fret = GuitarFretboard.note_to_fret(string_index, shifted)
        if 0 <= fret <= HIGH_FRET_LIMIT:
            frets = [-1] * len(STANDARD_TUNING)
            frets[string_index] = fret
            # `grip` is set rather than left at its "drop2" default: this is a
            # single-fret shape, and a caller reading `voicing.grip` would otherwise
            # conclude a four-note drop-2 had been chosen. The playability invariant
            # keys off this field.
            candidates.append(Voicing(
                frets=frets,
                top_fret=fret,
                avg_fret=float(fret),
                grip="melody",
            ))
    return candidates


def get_octave_down_candidates(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """
    Candidates for melody_note an octave lower, on the strings below the high E.

    A melody whose only position sits outside the neck window is re-voiced here so
    the whole harmonisation comes down the neck. Because the B string is five
    semitones below the high E, the octave-down transposition lands seventeen
    semitones - exactly a major tenth - below where the same note sat on the high
    E, which is what actually brings it into a playable position.

    The wider candidate pool matters here as much as anywhere: a high melody that no
    four-note shape can reach inside the window may still have a three-note shell
    under it, and taking that beats skipping the step.

    Returns an empty list when the octave-down melody cannot be voiced at all, so
    the caller can keep the original candidates rather than losing the step.
    """
    octave_down = Note(note_name(melody_note.midi_note() - 12))
    return get_all_grip_voicings(
        octave_down,
        chord_type,
        chord_name=chord_name,
        top_strings=_lower_soprano_strings(top_strings),
        grips=grips,
    )


def get_all_grip_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """
    Collects fingerings for every allowed soprano string in `top_strings`.

    High-E candidates come first, so a caller that simply takes the first result
    keeps the traditional top-string fingering. Candidate generation tries the
    chord-tone-matched inversion first and falls back to quality-only voicings, so
    nothing is lost when chord_name cannot place the melody on a chord tone. A
    melody below the high E string's open pitch (E4) simply yields no high-E
    candidates and is arranged on a lower string instead of being skipped.

    This is pure candidate generation: it neither filters by neck position nor
    transposes. A melody whose only position lies outside the window is re-voiced
    an octave down by get_octave_down_candidates, which arrange_progression calls -
    so the two cannot recurse into each other.
    """
    candidates: List[Voicing] = []
    for top_string in top_strings:
        candidates.extend(
            get_grip_voicings(
                melody_note, chord_type, chord_name, top_string, grips
            )
        )

    if not candidates and chord_name:
        for top_string in top_strings:
            candidates.extend(
                get_grip_voicings(
                    melody_note, chord_type, None, top_string, grips
                )
            )

    return candidates


def get_all_drop2_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> List[Voicing]:
    """
    Collects Drop-2 fingerings for every allowed soprano string in top_strings.

    High-E candidates come first, so a caller that simply takes the first result
    keeps the traditional top-string fingering. Candidate generation tries the
    chord-tone-matched inversion first and falls back to quality-only voicings, so
    nothing is lost when chord_name cannot place the melody on a chord tone. A
    melody below the high E string's open pitch (E4) simply yields no high-E
    candidates and is arranged on the B string instead of being skipped.

    This is pure candidate generation: it neither filters by neck position nor
    transposes. A melody whose only position lies above HIGH_FRET_LIMIT is
    re-voiced an octave down by get_octave_down_candidates, which
    arrange_progression calls - so the two cannot recurse into each other.
    """
    return get_all_grip_voicings(
        melody_note, chord_type, chord_name, top_strings, grips=("drop2",)
    )


def get_melody_only_voicings(
    melody_note: Note,
    prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> List[Voicing]:
    """
    Every single-fret Voicing that plays melody_note alone, in preference order.

    This is the **palette a lone note is chosen from**: an `NC` bar, a slot the texture
    thins to a fill, a melody no shape under it could carry, and the span demotion all
    reach these shapes. Which strings are on the table is
    `_melody_only_string_groups`' business - the caller's strings while they can carry
    the note, then every other string, then the octave-down retry for a note whose only
    position is above HIGH_FRET_LIMIT - and the choice among them is
    `cost.voicing_cost`'s, so a lone note is placed by the same window and the same
    distance from the shape the hand is holding as a chord is.

    These are deliberately NOT drop-2 voicings and so do not obey the
    four-contiguous-strings playability invariant - a candidate has exactly one active
    fret, and `fret_span()` is 0.

    A melody that is unreachable at the written pitch at all returns an empty list
    rather than being respelled: emptiness is the documented signal that a note cannot
    sound (B5 is fret 19, C6 is fret 20 - both past the end of the board), and quietly
    playing it an octave down would hide that from the caller.
    """
    # Reachability at the written pitch, across every string, decides whether the
    # octave-down attempt is legitimate at all. Without this a genuinely
    # unplayable note would be silently respelled and reported as playable.
    if not any(
        0 <= GuitarFretboard.note_to_fret(s, melody_note) <= 18
        for s in range(len(STANDARD_TUNING))
    ):
        return []

    for strings, octave_shift in _melody_only_string_groups(prefer):
        candidates = _melody_only_voicings_on(melody_note, strings, octave_shift)
        if candidates:
            return candidates
    return []


def get_melody_only_voicing(
    melody_note: Note,
    prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> Optional[Voicing]:
    """
    The first candidate `get_melody_only_voicings` offers, or None when it offers none.

    A caller that just wants *a* fingering for the tune alone takes the earliest string
    in the preference order that can carry the note, which is the high E whenever it can.
    A route that can weigh the alternatives against where the hand is asks for the list
    and lets `cost.voicing_cost` choose.
    """
    candidates = get_melody_only_voicings(melody_note, prefer)
    return candidates[0] if candidates else None


def sustain_inner_voices(previous_voicing: Voicing | dict, melody_note: Note) -> Optional[Voicing]:
    """
    Strategy 3: hold the previous chord's three inner voices and move only the
    soprano to the new melody note, the way a player sustains a shape under a
    passing tone. Returns None when the melody is unreachable on the same
    string within a playable span, so the caller can reharmonise instead.
    """
    frets = previous_voicing["frets"] if isinstance(previous_voicing, dict) else previous_voicing.frets
    frets = list(frets)

    soprano = max((s_idx for s_idx, fret in enumerate(frets) if fret >= 0), default=-1)
    if soprano < 0:
        return None

    top_fret = GuitarFretboard.note_to_fret(soprano, melody_note)
    if top_fret < 0:
        return None

    frets[soprano] = top_fret
    active = [fret for fret in frets if fret >= 0]
    if max(active) - min(active) > 5:
        return None

    # Divided by the number of *sounding* fingers, not by four: the previous voicing may be
    # a three-note shell or a two-note duo, and a shell's mean fret is not one quarter of
    # its sum. Getting this wrong misreports where the shape is, which is exactly what the
    # selector compares.
    prev_grip = (
        previous_voicing.grip if isinstance(previous_voicing, Voicing) else "drop2"
    )
    midis = [
        GuitarFretboard.fret_to_midi(s, fret) for s, fret in enumerate(frets) if fret >= 0
    ]
    return Voicing(
        frets=frets,
        top_fret=top_fret,
        avg_fret=sum(active) / len(active),
        grip=prev_grip,
        bass_pc=min(midis) % 12 if midis else None,
    )
