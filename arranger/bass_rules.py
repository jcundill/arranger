"""The bass vocabulary: styles, note rules, and the hand's capacity questions.

What a thumb line may be asked for (`BASS_RULES`, `BASS_RULE_ROLES`, the `BASS_STYLE_*`
spellings and `parse_bass_style`) and what the right and left hands can still play
while it runs (`thumb_capacity`, `comping_capacity`, `bass_allowed`). Policy only: the
line itself, its slots and its placement are in `bass`, which reads this module.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from .grip_tables import GRIP_STRING_SETS, comping_string_sets
from .parts import PART_BASS, PART_NAMES, parts_has_melody_only, parts_have_bass, parts_have_melody
from .texture import TEXTURE_STYLES, derived_arity, texture_palette
from .tuning import ROLE_FILL, ROLE_TARGET

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
#   anchor    the first position of a bar, and any strong beat where the harmony
#             changes: the root, always
#   connect   a position between those: a chord tone, an extension, or passing motion
#   approach  the last position of a bar: a half step from the next bar's anchor
#   enclosure the position before an approach: half step above, then below the anchor
#   pedal     the root on a position the line does not anchor - `root` asked to sound
#             at every position names the root everywhere, and only the first one per
#             bar *marks* the bar
#   fifth     the 5th on a position the line does not anchor, which is what
#             `root-5th` alternates with the root
#   hold      any position: the previous note repeated, when nothing else is reachable
BASS_ROLE_ANCHOR = "anchor"
BASS_ROLE_CONNECT = "connect"
BASS_ROLE_APPROACH = "approach"
BASS_ROLE_ENCLOSURE = "enclosure"
BASS_ROLE_PEDAL = "pedal"
BASS_ROLE_FIFTH = "fifth"
BASS_ROLE_HOLD = "hold"


# --- The bass style: which note rules the thumb line is written on -----------------
#
# A **style**, not a flag, and it names *note rules* rather than a rhythm: how many beats
# carry a note is `grid`'s business ([docs/history/parts.md](docs/history/parts.md) §4), and the rule list
# says only what a note that does sound is *for*.
#
# The four rules, and the `BASS_ROLE_*` values each admits:
#
#   root      the chord's root, at every position the rhythm names - on the anchor it
#             *marks* the bar, and elsewhere it is a pedal. Admits `anchor` and `pedal`.
#   5th       the root and the 5th alternating at those positions: the anchor takes the
#             root and a non-anchor position takes the 5th, which is `BASS_DEGREES_6432`
#             read as a line rather than as the one note the low E may carry.
#   approach  a note reaching the *next* anchor - the half step below it on the last beat,
#             the half step above on the penultimate. Admits `approach` and `enclosure`,
#             which are one rule read at two beats.
#   nearest   the connective vocabulary - a chord tone, a nameable extension, or passing
#             motion nearest the previous note. Admits `connect`.
#
# `hold` is deliberately **not** a rule: it is the fallback of "first reachable wins" - the
# previous note when no rule above is reachable - and it is ranked last whatever the style
# says. Naming it would let a caller ask for a line that only repeats, which is not a bass
# line.
#
# The shipped resolution order is `root, 5th, approach, nearest`. `approach` sits *before*
# `nearest` because on the last beat the approach outranks the connective note - that
# ordering is what makes the full list the library's walk. [docs/history/parts.md](docs/history/parts.md) §9
# records why it is not §4's literal `root, 5th, nearest, approach`.
BASS_RULE_ROOT = "root"
BASS_RULE_5TH = "5th"
BASS_RULE_APPROACH = "approach"
BASS_RULE_NEAREST = "nearest"

# The full vocabulary, in the shipped resolution order. A style is an ordered subset of
# this; the order is preserved on parse (it is a preference, like `grips`) but the roles
# are pre-ranked by `_walking_bass_line`, so the shipped order is the byte-identical one.
BASS_RULES: Tuple[str, ...] = (
    BASS_RULE_ROOT,
    BASS_RULE_5TH,
    BASS_RULE_APPROACH,
    BASS_RULE_NEAREST,
)

# Which `BASS_ROLE_*` values each rule admits. Keyed by rule so a new one is a row here,
# and asserted against `BASS_RULES` in the tests so a rule cannot be named without the
# roles it governs. `root` and `5th` share the anchor (the root marks the bar whichever
# of the two was asked for) and differ between anchors: a pedal or the 5th. `approach`
# governs both the last-position approach and the enclosure before it, because they are
# one rule read at two positions.
BASS_RULE_ROLES: Dict[str, FrozenSet[str]] = {
    BASS_RULE_ROOT: frozenset({BASS_ROLE_ANCHOR, BASS_ROLE_PEDAL}),
    BASS_RULE_5TH: frozenset({BASS_ROLE_ANCHOR, BASS_ROLE_FIFTH}),
    BASS_RULE_APPROACH: frozenset({BASS_ROLE_APPROACH, BASS_ROLE_ENCLOSURE}),
    BASS_RULE_NEAREST: frozenset({BASS_ROLE_CONNECT}),
}

# `BASS_ALL_RULES` is the bass axis's own default - every rule, in the table's order,
# derived rather than listed so the table above stays the one source - and it is the same
# string the request's `walk` maps to.
#
BASS_ALL_RULES = ",".join(BASS_RULES)

# `none` is not a rule: it is the **absence** of a style, the value a request whose bass
# layer never attacks resolves to. Keeping it out of the rule vocabulary is what lets the
# engine validate a style without special-casing a sentinel.
BASS_STYLE_NONE = "none"


def parse_bass_style(argument: str) -> Tuple[str, ...]:
    """A bass style argument as the ordered tuple of note rules it names.

    The spelling: comma-separated rule names, matched case-insensitively, whitespace
    around the commas ignored, so `"root,approach"` and `" Root , APPROACH "` are one
    request. **The order is part of the request**, not formatting - it is the resolution
    order, so `"approach,root"` and `"root,approach"` are two styles even though they
    admit the same roles. A repeat is dropped keeping its first occurrence, and nothing
    is re-sorted, for the same reason `grips.parse_grips` keeps its order: a sequence
    is ordered and a set is not.

    `none` is **not** a rule and is refused here: it is the absence of a style,
    resolved before this runs. Refusing it keeps the rule vocabulary to things that
    name a note, so a style can never be a rhythm word in disguise.

    Raises `ValueError` on an empty request, or on a name outside `BASS_RULES`, naming
    the vocabulary. The rule is the library's: a spelling nobody recognises is a
    question, and answering it by dropping a rule would hand back a bass line missing
    something nobody asked it to drop.
    """
    text = argument.strip().lower()
    if text == BASS_STYLE_NONE:
        raise ValueError(
            f"{argument!r} is not a note rule; expected a comma-separated list of "
            f"{BASS_RULES}"
        )
    if not text:
        raise ValueError(f"bass_style is empty; expected any of {BASS_RULES}")
    chosen: List[str] = []
    for part in text.split(","):
        name = part.strip().lower()
        if name not in BASS_RULES:
            raise ValueError(f"Unknown bass rule {name!r}; expected any of {BASS_RULES}")
        if name not in chosen:
            chosen.append(name)
    return tuple(chosen)


def thumb_capacity(
    texture: str,
    role: str,
    parts: Tuple[str, ...] = (),
    has_thumb: bool = False,
) -> Optional[int]:
    """How many of the three thumb strings the left hand leaves free, worst case.

    **The number a bass policy is checked against.** `place_bass` skips whichever
    thumb strings the upper shape already speaks on, per note, so a thumb line is a
    question of *capacity* rather than of conflict - and the capacity is whatever the
    texture's palette for this role may play, read from `texture.texture_palette` and
    the string tables rather than listed here.

    Returns `None` for a palette that is empty, which means "the left hand plays
    nothing here" and so leaves every thumb string free; the caller reads that as
    unbounded rather than as zero.

    Derived rather than listed, so a texture added to `TEXTURE_STYLES` cannot join the
    thumb-line route without its capacity being measured too. A
    melody-only **selection** is not answered here: its upper shapes are single frets,
    and its capacity is unbounded by construction - see `bass_allowed`.
    """
    families = texture_palette(
        role, texture, parts or PART_NAMES, has_thumb
    )
    if not families:
        return None
    sets = [
        strings
        for family in families
        for strings, _soprano in GRIP_STRING_SETS.get(family, ())
    ]
    if not sets:
        return None
    return _worst_free_capacity(sets)


def _worst_free_capacity(string_sets: Sequence[Tuple[int, ...]]) -> int:
    """The fewest of `BASS_STRING_INDICES` any of `string_sets` leaves free.

    The shared arithmetic of `thumb_capacity` and `comping_capacity`, factored so the
    two cannot drift: both answer "how bad could the left hand get", and they differ
    only in **where the string sets come from** - the role's grip palette on the
    melody-bearing route, `comping_string_sets` on the comping one.

    Worst case across the sets, deliberately, and for the reason `bass_allowed` gives:
    a thumb line with gaps in it is worse than no thumb line, so the question is
    whether the string is *ever* unavailable rather than whether it usually is.
    """
    return min(len(set(BASS_STRING_INDICES) - set(strings)) for strings in string_sets)


def comping_capacity(notes: int, bass_voice: bool = False) -> int:
    """How many thumb strings a **melody-free comping shape** leaves free, worst case.

    **`thumb_capacity` cannot answer this.** That function
    derives its answer from the melody-bearing route's own palette (`texture_palette`) read
    against the string tables (`GRIP_STRING_SETS`), which describe the shapes that route
    generates. On the comping route the shapes come from
    `get_comping_voicings` instead, and the chord content is *inert* there: all 80
    comping shapes on `tests/data/synthetic_cut_time.mxl` are byte-identical under
    `chord_notes="full"` and `chord_notes="targets"`. Asking `thumb_capacity` therefore
    refuses a combination that is perfectly playable, on the strength of a palette the
    comping route never uses - `bass_allowed("uniform", "root,5th,approach,nearest")`
    refuses a walk beside a comping selection under the default content.

    The warning was false on the facts too: the comping shapes on that head sound within
    strings `(1, 2, 3)`, `(2, 3, 4)` and `(1, 3, 4)` - never on the low E or the A, so
    the thumb had the whole bottom of the neck, and never on the high E, which
    `comping_string_sets` excludes at every arity.

    **Derived from the generator rather than listed**: a family that can be voiced is
    not a list of combinations somebody has to remember to extend. The worst case over
    the sets `comping_string_sets` may pick at each arity:

        1 note (an inner voice)   3 free
        1 note (`bass_voice`)     2 free
        2 notes (`alto,tenor`)    2 free
        3 notes                   1 free
        4 notes                   1 free

    **Never zero, at any arity** - which is the finding rather than a coincidence, and
    the reason `bass_allowed` cannot refuse this route at all: the comping shapes are
    built from the `duo` and `shell` families, which live on the top half of the neck
    precisely because the bottom of it belongs to the thumb - and the very top string is
    off the palette too (`grip_tables.COMPING_EXCLUDED_STRINGS`).

    A one-note `bass_voice` shape is the one case that reaches the bottom of the neck
    (`BASS_VOICE_STRING_SETS` is `(0, 1, 2)`), and it still leaves two strings free -
    the same note cannot occupy all three, because a one-note shape is one string.

    No `None` return, unlike `thumb_capacity`: an empty palette there means "the left
    hand plays nothing", which is unbounded. A comping shape always sounds at least one
    note, so the capacity is always a real count and never a sentinel.
    """
    # Imported here for the reason `thumb_capacity` gives: `grips` sits above `bass` in
    # the package order, and this - like that one - is the only question in this module
    # that needs the grip tables.

    return _worst_free_capacity(comping_string_sets(notes, bass_voice))


def bass_allowed(
    parts: Tuple[str, ...],
    texture: str,
    bass: str,
    notes: Optional[int] = None,
    bass_voice: bool = False,
    melody_only: bool = False,
) -> Tuple[bool, str]:
    """Whether `texture` can carry `bass`, and why not when it cannot.

    **The refusal rule, and it is one line:** a thumb line needs the left hand to leave
    at least one of the three thumb strings free, and `thumb_capacity` derives that from
    the texture's palette and the string tables rather than from a list here. Both `walk`
    and `anchors` need exactly
    one - they differ in how many *notes* they write, not in where the thumb can go - so
    the same threshold covers both, and a future policy is refused or allowed on the
    same terms without this function being taught about it.

    **No shipped texture fails it**, and that follows from the grip tables rather than
    from this rule: the worst case anywhere in the tree is one free string - the rule's
    threshold - so every texture carries every policy. The refusal and its reason string
    stay, because the question is still the right one to ask: a *comping* arity that
    filled the neck is caught through `comping_capacity`, and a texture added later whose
    palette reaches the whole thumb range is caught here without this function being
    taught about it.

    Note this is the **worst case across the sets a grip may use**, and in practice the
    selector rarely picks the worst one, so the rule is deliberately conservative: it refuses
    a combination that would *usually* work rather than shipping a line that is occasionally
    holed, because a bass line with gaps in it is worse than no bass line.
    `docs/engine.md` holds the measurement.

    The alternative is named in the reason string, so a refusal is a sentence a player can
    act on rather than a policy they have to reverse-engineer.

    **`notes` and `bass_voice` are the comping route's half of the question, and they
    are why this function takes them.** On the comping route the left hand's shapes are
    not described by the texture's palette at all - the texture is inert there, so passing one
    here and refusing on it refuses a combination that is perfectly playable.
    `comping_capacity`'s own docstring holds the per-arity
    table. The route is stated by the *caller*
    passing them rather than inferred from the texture, because the texture cannot
    distinguish it: `uniform` is a real palette on one route and a meaningless name on
    the other, and only the engine's own route decision knows which.

    **`melody_only` is the melody-only route's half, and it is unbounded rather than
    measured.** A selection that plays the tune and no chord part (`parts="melody"`,
    with or without the bass part named) puts a single fret above the thumb on every
    slot, so all three thumb strings are free whatever the texture's palette says -
    asking the palette would refuse a line with the whole neck to walk under, on the
    say-so of grips that route never generates. The texture is inert on that route for
    the same reason it is on the comping one.
    """
    if bass == BASS_STYLE_NONE:
        return True, ""
    if not parts_have_bass(parts):
        # **A style named for a part the selection leaves out is refused**, naming the
        # part that would work (docs/history/parts.md §9). A bass line is a claim about the
        # bass part; a selection that does not take it has nothing for the line to
        # state, and writing one anyway would put a note in the part a bassist owns.
        return False, (
            f"a bass line is a claim about the bass part, and "
            f"parts=\"{','.join(parts)}\" does not take it - add 'bass' to parts, or "
            f"drop the bass style"
        )
    if melody_only and notes is None:
        return True, ""
    if notes is not None:
        # The comping route: `comping_capacity` leaves at least one thumb string free at
        # every arity, so this cannot refuse. Checked rather than assumed, so a future
        # arity that really did fill the neck is caught here rather than arriving as an
        # unplaceable line.
        if comping_capacity(notes, bass_voice) < 1:
            return False, _comping_no_room_reason(notes, bass_voice)
        return True, ""
    for role in (ROLE_TARGET, ROLE_FILL):
        free = thumb_capacity(texture, role, parts)
        if free is None:
            continue                      # the left hand plays nothing: all three free
        if free < 1:
            return False, _no_room_reason(texture, role)
    return True, ""


def resolve_bass(
    bass: str,
    parts: Tuple[str, ...],
    texture: str,
) -> str:
    """The bass style to actually run, validated.

    Three outcomes, in the order they are decided:

    - `none` is **no line**: the request's bass layer never attacks, so there is
      nothing to play. A melody-only selection that also names the bass part is the
      tune with a thumb under it, whose line the part itself states.
      line, and a thumb under it would double it.
    - an unknown rule raises. A spelling nobody recognises is a question, and
      answering it by defaulting to a walk would put a line under an arrangement that
      did not ask for one; `parse_bass_style` owns the vocabulary and the message.
    - a combination the left hand cannot carry **raises**, naming a texture that
      would work. `none` is what a caller gets by asking for `none`, so handing it
      back for a walk the hand cannot accommodate would be a silent substitution, and
      a walking line with gaps in it is worse than no line. Losing the *bass* still
      costs less than losing the tune - that trade is made per beat by
      `attach_bass`, where the step survives and the tab says so.

    Takes the resolved `parts` rather than the flags derived from them: the route,
    the comping arity and the lone-bass case are decided here from the one selection,
    so two spellings of one request cannot disagree. Which capacity question is
    asked is `bass_allowed`'s business - the comping generator's on that route, the
    melody-only route's on its own, and the texture's palette otherwise, since
    `uniform` is a real palette on the melody-bearing route and a meaningless name on
    the comping one.
    """
    melody_voiced = parts_have_melody(parts)
    melody_only = parts_has_melody_only(parts)

    if bass == BASS_STYLE_NONE:
        return bass
    parse_bass_style(bass)  # raises on an unknown rule
    allowed, reason = bass_allowed(
        parts,
        texture,
        bass,
        None if melody_voiced else derived_arity(texture, parts),
        parts == (PART_BASS,),
        melody_only=melody_only,
    )
    if not allowed:
        raise ValueError(reason)
    return bass


def _comping_no_room_reason(notes: int, bass_voice: bool) -> str:
    """The sentence a refused **comping** combination reports.

    Separate from `_no_room_reason` rather than a branch inside it, because the two
    sentences are about different things: that one names a texture to try instead, and
    there is no texture to try here - the route is chosen by the voice selection, not
    by a palette. Naming a texture on this route is how the original bug produced a
    message that told the player to change a setting that had no effect.
    """
    return (
        f"a {notes}-note comping shape can occupy all of "
        f"{tuple(BASS_STRING_INDICES)}"
        + (" with bass_voice" if bass_voice else "")
        + ", leaving the thumb nowhere to go. Every bass policy needs the same string. "
        "Try naming fewer parts for the guitar, or drop the bass."
    )


def _no_room_reason(texture: str, role: str) -> str:
    """The sentence a refused combination reports.

    It names an alternative content **only if that content would have fitted**, and it
    reads `thumb_capacity` directly rather than calling `bass_allowed`. Every non-`none`
    policy shares the same one-string threshold, so there is never a different *policy*
    to suggest - and re-entering the refusal to look would recurse. A refusal that
    misdirects is worse than one that only explains itself.
    """
    head = (
        f"{texture} leaves no bass string free for a {role} - its grips can occupy "
        f"all of {tuple(BASS_STRING_INDICES)}. "
    )
    fits = [
        other
        for other in TEXTURE_STYLES
        if other != texture
        and all(
            (free := thumb_capacity(other, r)) is None or free >= 1
            for r in (ROLE_TARGET, ROLE_FILL)
        )
    ]
    if fits:
        return (
            head + "Every bass policy needs the same string, so no policy fits here. "
            f"Try the {fits[0]!r} content, or drop the bass."
        )
    return head + "No chord content in this set leaves the thumb a string."
