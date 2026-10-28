"""Grip families: the public builders and candidate generators.

Everything that turns a chord quality and a melody note into a *set of candidate
voicings* is here, and nothing here chooses between them. That split is what lets
this module be read on its own: `cost` holds the selection rule, and no generator
below knows what came before it, what the neck window is, or what the answer
turned out to be. The table-driven theory lives in `grip_templates`, the symbol
reading and searched-family requests in `grip_requests`, and the melody-free
comping generation in `grip_comping`.

**The generators are free functions, and `VoiceLeadingEngine` keeps one-line
`@classmethod` delegates.** Roughly forty call sites in the tests and the front ends
spell them `VoiceLeadingEngine.get_drop2_voicings(...)`, and the delegate keeps those
spellings working. It leaves one implementation, so there is nothing to keep in step.

The four non-contiguous string sets - 6-4-3, both 5-3-2s and 6-4-3-2 - are
*searched* rather than stacked, because their voices are not in descending pitch
order down the strings: the A string is tuned five semitones above the D. See
`search_shape`, which is the search they share.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from musthe import Note

from .grip_place import place_shape, place_template
from .grip_tables import GRIP_PREFERENCE
from .step_types import Voicing
from .tuning import (
    HIGH_FRET_LIMIT,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    STANDARD_TUNING,
    GuitarFretboard,
    note_name,
)


def get_grip_voicings(
    melody_note: Note,
    chord_name: str,
    top_string: int = 5,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """Generates fingerings for `grips` on one string block, pinned to the melody.

    This is the general form of `get_drop2_voicings`, and with `grips=("drop2",)` it
    produces exactly what that method always has. The other families differ in what
    they carry rather than in where they sit:

      drop2   four voices, from the tone-priority rule (`drop2_template_for`)
      drop3   four voices, a close stack with the third voice dropped
      drop24  four voices, a close stack with the second *and* fourth dropped
      closed  four voices in close position under the melody
      shell   three voices: the 3rd, the 7th, and one more
      duo     two voices, and only under a root or a 5th
      interval  two voices a 3rd, 6th or 10th apart - a fill, and under *any*
               melody degree

    Candidate generation is *pure*. It does not filter by neck position, does not
    transpose, and does not know what came before - choosing among the results is
    `best_voicing`'s job. Keeping that split is what stops the grip families and the
    octave-down rescue from having to know about each other.

    Every candidate uses 2-4 strings belonging to one `supported_string_sets()` entry,
    carries the melody as the **highest** sounding note, and holds a fret span of at most
    `GRIP_MAX_SPAN[grip]`. It sounds chord tones only, with one deliberate exception: an
    `interval` fill may sit a diatonic tone of the key under a melody that is not a chord
    tone, because a fill is a texture rather than a claim about the chord.
    """
    melody_midi = melody_note.midi_note()

    top_fret = GuitarFretboard.note_to_fret(top_string, melody_note)
    if top_fret < 0 or top_fret > 18:
        return []

    canonical, root_pc, tones = chord_context(chord_name)

    # The chord's tones as pitch classes: what `candidate` holds a searched shape's own
    # notes to. Computed once, because every searched family measures the same chord.
    allowed = (
        None if root_pc is None else frozenset((root_pc + t) % 12 for t in tones)
    )

    valid_voicings: List[Voicing] = []
    for grip in grips:
        for strings in string_sets_for(grip, top_string):
            if grip not in _SEARCHED_GRIPS:
                # A layout family: each template *is* a shape, so each is placed in turn.
                for template in _templates_for(
                    grip, canonical, tones, melody_midi, root_pc
                ):
                    voicing = place_template(
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
            found = place_shape(request, allowed)
            if found is not None:
                valid_voicings.append(found)

    return valid_voicings


def get_drop2_voicings(
    melody_note: Note,
    chord_name: str,
    top_string: int = 5,
) -> List[Voicing]:
    """Generates valid 4-string Drop-2 fretboard fingerings pinned to the melody note.

    top_string is the index of the string carrying the melody: 5 (high E) yields the
    traditional D-G-B-E shape, while 4 (B) yields the lower A-D-G-B shape used when
    the melody sits below the high E string's open pitch. The chord_name (e.g.
    'Dm7b5') is the whole harmony: its quality selects the shape and its root places
    the melody as the correct chord tone.

    Kept as a named entry point because it is what callers reach for directly and
    its output is part of the library's published behaviour. It is exactly
    `get_grip_voicings` with the grip pinned to drop-2.
    """
    return get_grip_voicings(
        melody_note, chord_name, top_string, grips=("drop2",)
    )


def get_interval_voicings(
    melody_note: Note,
    chord_name: str,
    top_string: int = 5,
) -> List[Voicing]:
    """Two-note interval fingerings under the melody: a 3rd, a 6th or a 10th.

    The arranging guide's fill for the notes between a chord on a strong beat and
    the next one. It is a **texture and not a harmony** - it says nothing about
    what the chord is, and it is meant to sit on a weak beat - so unlike a duo it
    is offered under *any* melody degree, including a 3rd or a 7th that a duo
    refuses. The **fill-only palette** is what confines it to fill slots, which is what
    makes the looser rule safe.

    Kept as a named entry point for the same reason as `get_drop2_voicings`: every
    grip family is reachable from the public surface, so a caller who wants a
    single one does not have to know the tuple spelling. It is exactly
    `get_grip_voicings` with the grip pinned to "interval".

    Returns an empty list when the melody is unreachable on that string - the same
    limitation every root-measured grip has.
    """
    return get_grip_voicings(
        melody_note, chord_name, top_string, grips=("interval",)
    )


def lower_soprano_strings(top_strings: Tuple[int, ...]) -> Tuple[int, ...]:
    """The subset of `top_strings` below the high E, so a transposed melody is voiced
    on the B string rather than back on the high E. Falls back to `top_strings`
    when it contains nothing below the high E, so a caller restricted to (5,)
    still gets a (higher) voicing instead of nothing.
    """
    lower = tuple(s for s in top_strings if s < len(STANDARD_TUNING) - 1)
    return lower or tuple(top_strings)


def _melody_only_string_groups(
    prefer: Tuple[int, ...],
) -> List[Tuple[Tuple[int, ...], int]]:
    """The (strings, octave shift) groups a melody-only voicing is searched in, in order.

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

    Duplicates and out-of-range indices in `prefer` are ignored: they name nothing the
    fretboard can answer.
    """
    named = tuple(s for s in prefer if 0 <= s < len(STANDARD_TUNING))
    seen: set = set()
    groups: List[Tuple[Tuple[int, ...], int]] = []

    # Group 1: the named strings at the written pitch.
    if named:
        ordered = tuple(s for s in named if s not in seen and not seen.add(s))
        groups.append((ordered, 0))

    # Group 2: every other string from the top down, at the written pitch.
    others = tuple(
        s for s in range(len(STANDARD_TUNING) - 1, -1, -1)
        if s not in named
    )
    if others:
        groups.append((others, 0))

    # Groups 3 and 4: the same two an octave down.
    if named:
        groups.append((named, -12))
    if others:
        groups.append((others, -12))

    return groups


def _melody_only_voicings_on(
    melody_note: Note,
    strings: Tuple[int, ...],
    octave_shift: int,
) -> List[Voicing]:
    """One single-fret Voicing per string in `strings` that can carry `melody_note`, in the
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
    chord_name: str,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """Candidates for melody_note an octave lower, on the strings below the high E.

    Used when the melody's only position lies above HIGH_FRET_LIMIT: transposing it
    down an octave brings it into a playable position rather than dropping the step.
    High-E candidates are excluded - the octave-down note lands on a lower string,
    which is why `lower_soprano_strings` trims the set.
    """
    octave_down = Note(note_name(melody_note.midi_note() - 12))
    return get_all_grip_voicings(
        octave_down,
        chord_name,
        top_strings=lower_soprano_strings(top_strings),
        grips=grips,
    )


def get_all_grip_voicings(
    melody_note: Note,
    chord_name: str,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """Collects fingerings for every allowed soprano string in `top_strings`.

    High-E candidates come first, so a caller that simply takes the first result
    keeps the traditional top-string fingering. A melody below the high E string's
    open pitch (E4) simply yields no high-E candidates and is arranged on a lower
    string instead of being skipped.

    This is pure candidate generation: it neither filters by neck position nor
    transposes. A melody whose only position lies outside the window is re-voiced
    an octave down by `get_octave_down_candidates`, which `arrange_progression`
    calls - so the two cannot recurse into each other.
    """
    candidates: List[Voicing] = []
    for top_string in top_strings:
        candidates.extend(
            get_grip_voicings(melody_note, chord_name, top_string, grips)
        )

    return candidates


def get_all_drop2_voicings(
    melody_note: Note,
    chord_name: str,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> List[Voicing]:
    """Collects Drop-2 fingerings for every allowed soprano string in top_strings.

    High-E candidates come first, so a caller that simply takes the first result
    keeps the traditional top-string fingering. A melody below the high E string's
    open pitch (E4) simply yields no high-E candidates and is arranged on the B
    string instead of being skipped.

    This is pure candidate generation: it neither filters by neck position nor
    transposes. A melody whose only position lies above HIGH_FRET_LIMIT is
    re-voiced an octave down by `get_octave_down_candidates`, which
    `arrange_progression` calls - so the two cannot recurse into each other.
    """
    return get_all_grip_voicings(
        melody_note, chord_name, top_strings, grips=("drop2",)
    )


def get_melody_only_voicings(
    melody_note: Note,
    prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> List[Voicing]:
    """Every single-fret Voicing that plays melody_note alone, in preference order.

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
    """The first candidate `get_melody_only_voicings` offers, or None when it offers none.

    A caller that just wants *a* fingering for the tune alone takes the earliest string
    in the preference order that can carry the note, which is the high E whenever it can.
    A route that can weigh the alternatives against where the hand is asks for the list
    and lets `cost.voicing_cost` choose.
    """
    candidates = get_melody_only_voicings(melody_note, prefer)
    return candidates[0] if candidates else None


def sustain_inner_voices(previous_voicing: Voicing | dict, melody_note: Note) -> Optional[Voicing]:
    """Strategy 3: hold the previous chord's three inner voices and move only the
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


# --- Re-exports from the split modules ---------------------------------------
#
# `grips` stays the public entry point: every name that used to live here is
# re-exported from the module that now owns it. Internal engine code imports
# directly from the owning module; this block keeps the published surface
# stable for tests and front ends.
# Re-exports for external consumers that import these names from `arranger.grips`.
# They are not used within this module but are part of the published surface.
from .grip_comping import (  # noqa: E402, F401
    CompingRequest,
    _comping_collapse_key,
    _comping_palette,
    _search_comping_voicings,
    get_comping_voicings,
    get_comping_voicings_for,
)
from .grip_requests import (  # noqa: E402, F401
    _drop2_6432_request,
    _searched_request,
    _shell_request,
    chord_context,
)
from .grip_templates import (  # noqa: E402, F401
    _LAYOUT_GRIPS,
    _SEARCHED_GRIPS,
    BASS_DEGREES_6432,
    _close_stack_offsets,
    _drop2_palette,
    _guide_tones,
    _interval_offsets,
    _interval_set_for_grip,
    _shell_voicing,
    _templates_for,
    drop2_template_for,
    string_sets_for,
)
