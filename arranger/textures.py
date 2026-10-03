"""Metric roles and textures: what a slot is *for*.

The arranging guide's method has a shape the cost tuple cannot express: a full
chord belongs on the *principal* melody notes, and the notes between are filled
with something lighter. `voicing_cost` ranks completeness above position, so with
no rhythm at all a bar of running eighths comes out as eight re-struck four-note
chords - a chord list, not an arrangement.

The fix works by changing *which grips are on the table*, not by adding a term to
the cost. "Play fewer notes here" is not a preference competing against "stay in
position"; it is a change of what may be chosen at all, and putting it in the cost
would let a four-fret position outbid a whole texture. That is why `TEXTURE_GRIPS`
is a table `steps` reads and hands to the generator, and why this module imports
nothing from `cost` and nothing from `grips` but the one preference tuple.

`ROLE_TARGET` and `ROLE_FILL` are *defined* in `tuning` and re-exported here,
because `Voicing.role` and `ArrangementStep.role` both default to `ROLE_TARGET`
and `Voicing` sits below this module. One definition, two spellings.

The load-bearing line in this module is `_metric_weight` returning **-1** when
there is no timing at all. A caller that does not know where its notes fall has
not told us the note is weak; it has told us nothing, and treating the two the same
would thin out every hand-written progression. That one value is what makes the
feature opt-in: with no `timings` every slot is a target, and the output is
byte-identical to what it always was.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .grips import GRIP_PREFERENCE
from .tuning import ROLE_FILL, ROLE_TARGET

__all__ = [
    "MELODY_ONLY_TEXTURES",
    "ROLE_FILL",
    "ROLE_TARGET",
    "TARGET_BEATS",
    "TEXTURE_GRIPS",
    "TEXTURE_STYLES",
    "THUMB_TEXTURES",
]



# Texture styles, in the order that breaks a tie. `uniform` is the historical
# behaviour - every slot is a target and the cost tuple's completeness criterion
# decides, which is why it is the default and why existing output is unchanged.
TEXTURE_STYLES: Tuple[str, ...] = (
    "uniform", "targets", "walking_bass", "melody", "melody_bass",
)


# Textures that **harmonise nothing**: every slot is the melody alone, whatever the
# chord symbol says. Declared by name so that the four places that decide "does this
# slot become a single note" all read one table instead of each naming `walking_bass`
# in its own words - which is how a texture added to `TEXTURE_STYLES` silently misses
# a branch and harmonises nothing, or drops its melody.
#
# The pair differs in exactly one thing, which is the other table below: `melody` has
# no thumb line and `melody_bass` has one. Both are declared here rather than derived
# from `TEXTURE_GRIPS`, because a texture whose palettes happen to be empty is not the
# same claim as one that means to harmonise nothing.
MELODY_ONLY_TEXTURES: Tuple[str, ...] = ("melody", "melody_bass")

# Textures that build a **thumb line**: the walked-beat grid is unioned with the melody
# grid before the step loop, so a bar whose melody is one whole note still carries four
# bass notes. Separate from `MELODY_ONLY_TEXTURES` because `walking_bass` has a thumb
# and *does* harmonise, on its strong beats.
THUMB_TEXTURES: Tuple[str, ...] = ("walking_bass", "melody_bass")

# The beats of a bar that carry a full chord under the "targets" texture, counted
# from 1. Beats 1 and 3 are the guide's rule verbatim: in 4/4 they are the two
# half-note pulses, and they are where the harmony wants to be stated.
#
# Expressed as *beats*, not as an absolute onset, so the rule reads the metre it is
# given rather than assuming one: a 2/2 bar (two notated beats) gets beat 1 only, and
# a 3/4 bar gets 1 and 3 as it would in 4/4. A beat is a counting position, not a
# quarter note - see the cut-time notes in AGENTS.md.
TARGET_BEATS: Tuple[int, ...] = (1, 3)

# The grip families each role may use, by texture. This is the whole texture policy
# in one table, and it is read by `_roles_for_slot` and its caller.
#
# `drop3` is listed among a target's grips but generates nothing at
# GRIP_MAX_SPAN["drop3"] == 5, because drop-3 spans a twelfth by construction. That is
# where the library already stands, so listing it costs nothing and means a future
# span change takes effect without touching this code.
TEXTURE_GRIPS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "uniform": {"target": GRIP_PREFERENCE, "fill": GRIP_PREFERENCE},
    "targets": {
        "target": ("drop2", "drop3"),
        "fill": ("shell", "interval", "melody"),
    },
    # A walking bass is a *texture*, expressed in the table that already exists: a
    # shell (3rd & 7th) states the harmony on a target beat and nothing above the
    # melody sounds between them.
    #
    # The empty fill tuple is the point, not an omission: it means the left hand
    # plays **nothing** on a fill, which is why two four-note grips that would
    # collide with the thumb are never offered (drop2_6432 is the only four-note
    # grip that reaches the low E, and a shell is the only set that leaves both the
    # 6th and the 5th free under a high-E melody). `arrange_progression` resolves
    # the empty tuple through `get_melody_only_voicing` rather than through grip
    # lookup, and the same route is the fallback for a target no shell can sound -
    # `grips=("shell",)` has no second option, so without it a melody like D over
    # Bbm7 would disappear with only a warning.
    "walking_bass": {
        "target": ("shell",),
        "fill": (),
    },
    # `melody` is the lead sheet in, the tune out: every slot is the melody alone, so
    # nothing under it is ever harmonised and the chord name above it is context rather
    # than a claim about what is sounding. It is a texture rather than a grip because
    # "what may be played at all" is the question it answers, and a grip would have to
    # win a cost comparison it should not be in - see `GRIP_PREFERENCE`.
    #
    # The empty tuple on **both** roles is the declaration, in the same words
    # `walking_bass`'s fill uses for its fills: `arrange_progression` reads `()` as "the
    # left hand plays nothing" and routes the slot through `get_melody_only_voicing`.
    # It is never absent and never approximated by an empty list elsewhere.
    "melody": {"target": (), "fill": ()},
    # The same line with a thumb under it, and no shell above it anywhere: a bass voice
    # walking under the tune with nothing harmonising it. `walking_bass` states the
    # harmony on its strong beats and leaves the thumb to fill the gaps; this one is
    # thumb-and-melody throughout, which is why its **target** palette is empty too and
    # not only its fill's.
    "melody_bass": {"target": (), "fill": ()},
}

# How close a notated beat has to be to a whole beat to count as it. A 2/2 bar's
# eighths land on 1.0, 1.5, 2.0, 2.5, and a 3/4 bar's on 1.0, 1.666..., so an exact
# comparison would call almost none of them downbeats. Measured in beats, not in
# quarters, so this is the same tolerance in any metre.
_BEAT_EPSILON = 1e-6


def _metric_weight(
    bar: Optional[int], beat: Optional[float], beats_per_bar: int = 4
) -> int:
    """
    How metrically strong a slot is: 2 on beat 1, 1 on beat 3, 0 on any other beat.

    Returns **-1 when there is no timing at all** (`bar` or `beat` is None), which is
    the load-bearing part. A caller that does not know where its notes fall has not
    told us the note is weak - it has told us nothing - and treating those two the
    same would thin out every hand-written progression and every existing test. The
    -1 is what keeps the default behaviour byte-identical.

    `beats_per_bar` is honoured rather than assumed, because a count without a
    denominator is not a metre. TARGET_BEATS names *beats*, so in 2/2 (two notated
    beats) beat 3 does not exist and only the downbeat is a target; in 3/4 beats 1
    and 3 are targets exactly as they are in 4/4. This is the same reasoning the
    MusicXML importer needed when it discovered 2/2 is not 2/4.

    A beat is compared with `_BEAT_EPSILON` because a notated beat is a float: a
    3/4 bar's second beat is 1.666..., and an exact comparison would call almost no
    real note a downbeat.
    """
    if bar is None or beat is None:
        return -1
    for index, target in enumerate(TARGET_BEATS):
        if target > beats_per_bar:
            # Beyond the end of the bar: a 2/2 signature has two beats, so beat 3
            # does not exist. Compared as a beat number, not as a position in the
            # tuple, or a 2/2 bar would inherit 4/4's second target.
            break
        if abs(float(beat) - target) <= _BEAT_EPSILON:
            return 2 - index
    return 0


def _roles_for_slot(
    weight: int,
    texture: str,
    harmony_changed: bool = True,
    melody_moves: bool = False,
    has_thumb: bool = False,
) -> List[str]:
    """
    The metric roles a slot of the given weight may take under `texture`.

    This is the whole texture policy in one function, so changing the target-note
    rule is a change here and not a change spread through the selector:

      - an unknown texture is a programming error and raises, rather than silently
        arranging as `uniform`;
      - `uniform` makes every slot a target, which is the historical behaviour and
        the reason `arrange_progression` is unchanged unless a caller opts in;
      - a weight below zero means no timing was supplied, so the slot is a target;
      - a strong beat is a target and any other beat is a fill.

    Raises ValueError for an unknown texture, checked before any voicing work so a
    typo cannot cost a caller a full arrangement before it is reported.

    `harmony_changed` and `melody_moves` are the walking bass's extra condition and
    are defaulted to the values that leave every other texture untouched. Under
    `walking_bass` a slot is a target only when it is metrically strong **and**
    something new happens there: the harmony differs from the previous target's, or
    the melody moves onto it. The first half is the off-beat-change rule - a chord
    arriving on beat 4-and is voiced under the *new* chord by the harmony timeline,
    but is left as a fill, because a passing slot is exactly where the non-chord-tone
    strategies would rewrite the harmony. The second half is decision F: under
    `targets` the second bar of a two-bar chord is a fill, so a player who re-articulates
    the melody on that downbeat gets no chord under it. `TARGET_BEATS` alone cannot say
    either of those things, which is why the extra test lives here rather than in
    `_metric_weight`.

    Both arguments are ignored by every other texture, so `uniform` and `targets`
    stay byte-identical.
    """
    table = TEXTURE_GRIPS.get(texture)
    if table is None:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    if texture == "uniform" or weight < 0:
        # Historical behaviour, and "we were never told where this note falls".
        return [ROLE_TARGET]
    if has_thumb:
        # `weight > 0` is kept *inside* the conjunction, and that is the off-beat
        # change rule rather than a detail of it. A chord arriving on the 4-and is
        # voiced under the new chord by the harmony timeline - which axis says what is
        # harmonised is not this function's business - but it must not be a *target*:
        # off-beat slots are exactly where the melody is a passing tone, and a shell
        # there goes through the non-chord-tone strategies, which on a weak beat under
        # a note that was only passing through is mud rather than colour. The texture
        # would get busier precisely where it is meant to get lighter.
        #
        # So a target is a **strong** beat with something new on it: a harmony not yet
        # stated (the mid-bar change, decision E) or a melody that moves onto it
        # (decision F, which is what lets the second bar of a two-bar chord restate
        # its shell when the player re-articulates the line and stay thin when they do
        # not). Everything else is a fill, and a fill is the melody alone.
        #
        # Checked before `uniform`'s catch-all below so no later branch can return
        # TARGET first; `uniform` itself never reaches here.
        #
        # `has_thumb` rather than the texture name, because the thumb line is now an
        # argument of its own (`bass=`): any texture may carry one. The reason this
        # branch exists is the role's, not the shell's - `is_bass_only` reads it to
        # decide whether a beat invented for the thumb holds the melody or re-strikes
        # it, and a beat invented for the thumb must hold it. A texture with no thumb
        # has no invented beats and no use for either role, so it falls through to the
        # metric rule below.
        if weight > 0 and (harmony_changed or melody_moves):
            return [ROLE_TARGET]
        return [ROLE_FILL]
    if weight > 0:
        return [ROLE_TARGET]
    return [ROLE_FILL]
