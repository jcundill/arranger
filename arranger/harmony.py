"""The harmony axis: which *degrees* the chord part states when it is not singing.

A **degree order**, and nothing else. It answers "in which order does the chord part
state its degrees", not "how many notes are on the guitar": the arity is `texture=`'s,
and the order is `TONE_PRIORITY`'s row for the quality, sliced to that arity. A reduced
shape therefore gives up the order's **tail**.

The orders are read from tables that already state what a bass may be and what a shell
must sound, rather than re-derived here - the same rule the rest of the module follows,
and the reason `guide` is the *shipped* behaviour rather than a description of it.

  `HARMONY_FULL`       the whole row: every tone the quality defines, in priority order
  `HARMONY_GUIDE`      both guide tones - the 3rd and the 7th
  `HARMONY_SHELL_ROOT` both guide tones AND a root or 5th underneath them

**`shell_root` is the case the guide-tone table cannot express**: `SHELL_DEGREES` says
what must sound, `BASS_DEGREES_6432` says what may be the bottom, and a shape needing
both is a claim neither table makes alone. It is reachable on the **existing** `(5,4,3)`
shell sets, so it needs no new string sets and no new grip family. At an arity of two it
**is** the guide pair, which is why the old "room for three" refusal is gone rather than
relocated: a reduced shape gives up the tail of the order rather than needing a different
one.

`resolve_harmony` imports `parts_have_melody` and `parts_have_chord` from `parts` - this
module is the only axis module that reads another axis module, because `auto` resolves
from the parts selection.
"""

from __future__ import annotations

from typing import Dict, Tuple

from .parts import parts_have_chord, parts_have_melody

HARMONY_FULL = "full"
HARMONY_GUIDE = "guide"
HARMONY_SHELL_ROOT = "shell_root"

HARMONY_STYLES: Tuple[str, ...] = (
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_SHELL_ROOT,
)

#: The arity each named order supplies, for the check that a texture asks for no more
#: degrees than the order names. `HARMONY_FULL` is absent because its length is the
#: chord's own tone set, which varies by quality and lives in `TONE_PRIORITY`; an arity
#: longer than the row is refused there, where the row is known.
HARMONY_LENGTH: Dict[str, int] = {
    HARMONY_GUIDE: 2,
    HARMONY_SHELL_ROOT: 3,
}

HARMONY_AUTO = "auto"

#: `auto` means "whatever this part already says", and it **decides rather than naming
#: its own default**: the two shipped shapes are different. With the melody taken the
#: chord part is the full order - the chord-melody this library has always built - and
#: with the guitar comping under somebody else's tune it is the guide pair. One value
#: cannot be both, which is why this sentinel survives where `grid`'s was withdrawn.
HARMONY_AUTO_POLICIES: Dict[bool, str] = {
    True: HARMONY_FULL,
    False: HARMONY_GUIDE,
}


def parse_harmony(argument: str) -> str:
    """A `harmony` argument as one of `HARMONY_STYLES`, or the `HARMONY_AUTO` sentinel.

    A single identifier out of a closed set rather than a comma-separated list, because
    unlike the parts selection this axis names **one** degree family and not a subset of
    parts. Parsed here rather than inline at the call site so the vocabulary
    and the refusal live in one place, on the same rule as `parse_parts`.

    Raises `ValueError` on an unknown name: a spelling nobody recognises is a question,
    and answering it by falling back to `guide` would hand back a part that states
    something other than what was asked for.
    """
    text = argument.strip().lower()
    if text == HARMONY_AUTO:
        return HARMONY_AUTO
    if text not in HARMONY_STYLES:
        raise ValueError(
            f"Unknown harmony {argument!r}; expected any of "
            f"{', '.join(HARMONY_STYLES)}, or 'auto'"
        )
    return text


def resolve_harmony(harmony: str, parts: Tuple[str, ...]) -> str:
    """The degree order to actually state: `auto` resolved, then validated.

    `auto` resolves from the **parts**, through `HARMONY_AUTO_POLICIES`: the full order
    when the melody is the guitar's, and the guide pair when it is not.

    A combination that cannot state the order is refused by `harmony_allowed`, which
    names the part that would work rather than silently dropping something.
    """
    resolved = (
        HARMONY_AUTO_POLICIES[parts_have_melody(parts)]
        if harmony == HARMONY_AUTO
        else harmony
    )
    if harmony == HARMONY_AUTO:
        return resolved
    allowed, reason = harmony_allowed(resolved, parts)
    if not allowed:
        raise ValueError(reason)
    return resolved


def harmony_allowed(harmony: str, parts: Tuple[str, ...]) -> Tuple[bool, str]:
    """Whether this degree order can be stated by this selection, and why not.

    **Derived rather than listed**, from one fact: every `harmony=` value is a claim
    about the **chord part**, so a selection that does not take it has no part to state
    the order on. This is `harmony=root`'s old refusal generalised - a content policy
    for a part the selection does not name is refused, naming the part that would work.

    Checked before any voicing work, on the library's standing rule that an impossible
    request is answered by saying what would work rather than by dropping something the
    caller asked for.
    """
    if not parts_have_chord(parts):
        return False, (
            f"harmony={harmony} is a degree order for the chord part, and "
            f"parts={','.join(parts)} does not take it - add 'chord' to parts, or "
            f"drop the harmony"
        )
    return True, ""
