"""The slot layer: turn `(melody, quality, name)` triples into arrangement steps.

This module was `wjazzd.arrange_slots` and arrived here by a route worth stating,
because the name was misleading for its whole life. It lived beside the Weimar
Jazz Database loader, so it read as *the corpus path's* step loop - and the
docstrings said so, which is how a function two thirds of whose callers were
MusicXML came to describe itself as the database's own. It was never coupled to
the database: it took triples and timings and handed them to
`VoiceLeadingEngine.arrange_progression`. The Weimar loader was simply its first
caller, and `headxml` the second.

The database is gone, and this is what remains of that dependency.

**It is a thin pre-pass, and that is the point.** The engine must see whatever
triples it is handed, so everything here is a *decision about what to ask for* -
the diminished retry, the timings, the slash bass - and the voicing itself
belongs to `steps.py`. Two of those three were corpus requirements that happen to
be useful to any caller, and one (`_slot_options`) is a named seam rather than a
public API: the request this module makes of the engine, in one value, so a test
can read it.

What survives here is corpus-independent, and what went with the database is the
**Weimar quality table** (108 suffixes) and the chord-symbol spelling built on it.
The slash-bass rule kept below is the general part of it - "prefer a candidate
whose lowest note is the one the chord asks for" - and it reads the bass off a
symbol with a general pattern rather than a Weimar one, so `A-/G` means the same
thing wherever it came from.

Ordering note for `tests/test_package_dag.py`: this module sits after `steps`
(it constructs `VoiceLeadingEngine`) and imports nothing from `render` or `cli`,
so it needs no entry in `ALLOWED_EDGES`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from musthe import Note

from arranger.diagnostics import Diagnostics, default_diagnostics
from arranger.grips import GRIP_PREFERENCE
from arranger.options import ArrangeOptions
from arranger.steps import VoiceLeadingEngine
from arranger.textures import TEXTURE_STYLES
from arranger.tuning import NO_CHORD, PITCH_CLASS_NAMES, ArrangementStep

__all__ = [
    "arrange_slots",
    "bass_cost",
    "bass_pitch_class",
    "midi_to_note_name",
    "parse_bar_range",
    "promote_slash_chord",
    "unresolved_steps",
]

# A bar range is an optionally negative LO, a hyphen, and an optionally negative
# HI. Both bounds may be negative at once ("-8--1"), so the two numbers are pulled
# out by pattern rather than by splitting on a hyphen, which cannot tell a
# separator from a minus sign. Whitespace is allowed because a quoted shell
# argument commonly carries it.
_BAR_RANGE_RE = re.compile(r"^\s*(-?\d+)\s*(?:-\s*(-?\d+))?\s*$")


def parse_bar_range(text: str) -> Tuple[int, Optional[int]]:
    """Parses a "LO-HI" bar range, half-open, with signed bounds.

        '0-8'   -> (0, 8)
        '-4-8'  -> (-4, 8)     the anacrusis, as a negative LO
        '12'    -> (12, None)  open-ended; the section's own end applies
        '-8--1' -> (-8, -1)    a range that lies entirely in the pickups

    Negative bounds are ordinary, not malformed: 1,335 `beats` rows across 149
    transcriptions sit below bar 0, reaching bar -31, and the ATTYA pickups live
    there.
    """
    match = _BAR_RANGE_RE.match((text or "").strip())
    if match is None:
        raise ValueError(f"Invalid bar range {text!r}; expected LO-HI, e.g. '0-8' or '-4-8'")
    lo = int(match.group(1))
    hi = int(match.group(2)) if match.group(2) is not None else None
    if hi is not None and hi <= lo:
        raise ValueError(f"Bar range {text!r} is empty; HI must be greater than LO")
    return (lo, hi)
def unresolved_steps(
    triples: Sequence[Tuple[str, str, str]],
    non_chord_tone: str = "extension",
) -> List[int]:
    """Indexes of steps no non-chord-tone strategy could resolve.

    These are the steps a diminished retry would have to rescue: the melody is
    not a chord tone, and neither `extension` nor the strategy in force maps it
    onto a substitute. Reported so a user can see what `--fallback diminished`
    would buy without enabling it.
    """
    unresolved: List[int] = []
    for index, (note, quality, name) in enumerate(triples):
        if quality == NO_CHORD or not name:
            continue
        melody = Note(note)
        if VoiceLeadingEngine.is_chord_tone(melody, quality, name):
            continue
        if non_chord_tone == "legacy":
            continue
        resolved = VoiceLeadingEngine.resolve_non_chord_tone(melody, quality, name, non_chord_tone)
        if resolved is None:
            unresolved.append(index)
    return unresolved


_TRIAD_QUALITIES = ("maj", "m")

# Which seventh a triad becomes when its bass note is the seventh, keyed by the
# triad's own quality. A minor triad over a minor seventh is m7, a major triad
# over a major seventh is maj7.
_TRIAD_PROMOTION = {"m": "m7", "maj": "maj7"}


def promote_slash_chord(root: str, quality: str, bass: Optional[str]) -> str:
    """Promotes a triad to a seventh chord when the bass implies one.

    The Weimar database writes `A-/G`, `C-/Bb` and `D/C` for what a musician
    reads as Am7/G, Cm7/Bb and Dm7/C: a triad whose bass is its own seventh.
    Naming the seventh makes the melody note a chord tone instead of an
    unresolved tension, and it recovers the largest group of otherwise
    inexplicable basses.

    Triads with any other bass, and every non-triad quality, pass through
    unchanged. A pedal or an inverted bass is honoured by `bass_pitch_class`
    instead, which is a preference rather than a change of chord.
    """
    if bass is None or quality not in _TRIAD_QUALITIES:
        return quality
    root_pc = Note(root + "4").midi_note() % 12
    bass_pc = Note(bass + "4").midi_note() % 12
    if (bass_pc - root_pc) % 12 == 10:  # the seventh
        return _TRIAD_PROMOTION[quality]
    return quality


def midi_to_note_name(pitch: int) -> str:
    """MIDI number to a note name, spelled with flats.

    Flats because the keys and chord symbols this library is handed are
    flat-based (Eb, Bb, Ab), so a flat spelling is the one that reads correctly
    next to them.
    """
    pitch = int(round(pitch))
    return f"{PITCH_CLASS_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _next_chord_tone_melody(
    triples: Sequence[Tuple[str, str, str]], index: int
) -> Optional[str]:
    """The next melody note that is a chord tone of its own chord, if any.

    Read by the diminished retry: a substituted chord is easier to sing and easier
    to voice when there is a following note the ear can move to, so this is what
    the retry offers the engine as `next_melody`.
    """
    for melody, quality, name in triples[index + 1:]:
        if quality == NO_CHORD or not name:
            continue
        if VoiceLeadingEngine.is_chord_tone(Note(melody), quality, name):
            return melody
    return None


def bass_pitch_class(bass: Optional[str]) -> Optional[int]:
    """The pitch class a slash bass asks for, or None when there is none."""
    if bass is None:
        return None
    return Note(bass + "4").midi_note() % 12


# A chord symbol's slash bass: anything after a single `/`, which must be a
# pitch. Deliberately looser than the Weimar pattern this replaces - it read the
# *same* field with a stricter one, and the strictness bought a quality lookup
# this call site never used. `A-/G` -> `G`; `A-` and `NC` -> None.
_SLASH_BASS_RE = re.compile(r"^[^/]*/([A-Ga-g][#b]?)\s*$")


def _slash_bass(symbol: str) -> Optional[str]:
    """The bass note a chord symbol asks for, or None when it asks for none.

    **This is the general reading, and the Weimar spelling it replaces was only
    ever used for this field.** `parse_weimar_chord` returned a three-tuple and
    this call site read the third element; the first two, including the 108-entry
    quality table that had to be present for the function to exist, were dead at
    this call site. So the replacement drops the table rather than porting it.
    """
    symbol = (symbol or "").strip()
    if not symbol or symbol == NO_CHORD:
        return None
    match = _SLASH_BASS_RE.match(symbol)
    return match.group(1) if match else None


def bass_cost(voicing_midis: Sequence[int], bass_pc: Optional[int]) -> int:
    """How far a voicing's lowest sounding pitch is from the requested bass.

    In semitones, as the smallest interval from the bass pitch class to the
    lowest note actually played. Zero means the bass is in the voicing; 6 means
    it is a tritone away. Used only to *prefer* one candidate over another, so a
    voicing that cannot honour the bass is still usable.
    """
    if bass_pc is None or not voicing_midis:
        return 0
    lowest = min(voicing_midis) % 12
    direct = abs(lowest - bass_pc)
    return min(direct, 12 - direct)


# ---------------------------------------------------------------------------
# The slot layer proper: the pre-pass, and the request it makes of the engine
# ---------------------------------------------------------------------------


def arrange_slots(
    triples: Sequence[Tuple[str, str, str]],
    timings: Sequence[Tuple[Optional[int], Optional[float], Optional[float]]] = (),
    non_chord_tone: str = "extension",
    fallback: Optional[str] = None,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
    texture: str = "uniform",
    bass: str = "auto",
    melody: str = "auto",
    harmony: str = "auto",
    grid: str = "auto",
    beats_per_bar: int = 4,
    diagnostics: Optional[Diagnostics] = None,
) -> Tuple[List[ArrangementStep], List[int], List[str]]:
    """Voices a list of (note, quality, name) triples, one step per slot.

    **This no longer contains a step loop.** It is a pre-pass over the triples
    followed by a call to `VoiceLeadingEngine.arrange_progression`. It used to be
    a second, near-verbatim copy of that loop - 366 lines, carrying its own copies
    of six decisions under a comment reading *"Both copies must agree"*. Both
    callers reached the voicings through here, so a head imported from a score was
    voiced by exactly the same code as the same head read out of the database.
    That was the intention before; now it is a property of the structure rather
    than a promise in a comment.

    What a caller needs that the engine does not take, and how each is passed:

    - **a slash bass** (the corpus called this rule C) becomes `ArrangeOptions.bass_pcs`,
      a mapping from triple index to the pitch class the caller wants in the bass. It
      narrows *which candidates are considered*, and `decisions.select_step_voicing`
      applies the engine's own rule within that narrowed set - so the two selection
      rules stay combined rather than sequential, which is the whole point of the rule.
    - **the diminished retry** becomes a pre-pass below, rewriting the triples
      before the engine sees them.
    - **the timing** becomes `ArrangeOptions.timings`, normalised to one entry per
      triple so the engine's defensive indexing is the only one that runs.

    `timings` is the slots' own `(bar, beat, duration)`, in the renderer's units: a
    signed bar, the beat within it, and a length in whole notes. The duration is
    **optional per slot and `None` in practice**: it is a *notated* length, and a
    caller reading performed durations off a database has nothing of the kind -
    handing one to `tabxml._events`, which caps a step's span by it, truncates
    every chord to a fraction of its real length. So `headxml` supplies one and a
    caller with no written rhythm may not. The whole sequence is optional too and
    indexed defensively, so a hand-built sequence without timings still arranges -
    the step simply has none, and the renderers fall back to a uniform grid.

    `fallback` may be "diminished", which retries the steps no strategy could
    resolve as Barry Harris dim7 substitutions. It replaces the written chord, so
    it is off unless asked for; the count of steps it *would* rescue is always
    returned in the notes.

    `texture` is the arranging guide's target-note rule, applied by the engine's own
    `_metric_weight` and `_roles_for_slot`, so every caller is textured identically. "targets" states a full
    chord on beats 1 and 3 and fills the notes between with a shell, a 3rd/6th
    interval or the melody alone; "uniform" (the default) voices every slot in full.
    `beats_per_bar` is the metre that rule reads, and a head in cut time must pass
    its own - a count without a denominator is not a metre.

    Returns the steps, the indexes of the steps the diminished retry actually
    substituted, and any diagnostic notes worth printing. The `notes` are *not* the
    `diagnostics` warnings: they are arrangement-level remarks the caller is
    expected to print itself.
    """
    if texture not in TEXTURE_STYLES:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    if fallback not in (None, "diminished"):
        raise ValueError(f"Unknown fallback {fallback!r}; expected None or 'diminished'")
    if diagnostics is None:
        diagnostics = default_diagnostics()

    engine = VoiceLeadingEngine()
    notes: List[str] = []

    # --- the diminished retry, as a pre-pass -------------------------------------
    #
    # A pre-pass rather than something inside a loop, because there is no loop here
    # any more. The engine must see the substituted chord, and it sees whatever
    # triples it is handed.
    #
    # It used to be applied *after* the slot's role had been computed from the
    # written chord. Under `targets` the role does not read the harmony, so nothing
    # moved; under `walking_bass` it does. That ordering change is measured rather
    # than assumed - `tests/test_wjazzd.py::TestTheRetryReordersNothingVisible`.
    unresolved = unresolved_steps(list(triples), non_chord_tone)
    retry = set(unresolved) if fallback == "diminished" else set()
    rescued: List[int] = []
    working = list(triples)
    if retry:
        notes.append(
            f"diminished fallback replaced the written chord on {len(retry)} step(s)"
        )
        for index in sorted(retry):
            # Named `note`, not `melody`: this loop variable would otherwise shadow the
            # `melody` **policy** parameter for the rest of the function, and
            # `_corpus_options(melody=...)` below would be handed whatever note this
            # loop last visited - `ValueError: Unknown melody policy 'D4'`, raised only
            # when a diminished retry had something to rescue, so it looked like a
            # corpus bug rather than a shadowing one. The same trap `_corpus_options`
            # dodges for `bass`, documented beside its own loop.
            note, quality, name = triples[index]
            resolved = engine.resolve_non_chord_tone(
                Note(note), quality, name, "diminished",
                next_melody=_next_chord_tone_melody(triples, index),
            )
            if resolved is not None:
                working[index] = (note, resolved[0], resolved[1])
                rescued.append(index)

    options = _slot_options(
        triples=working,
        timings=timings,
        non_chord_tone=non_chord_tone,
        grips=grips,
        texture=texture,
        bass=bass,
        melody=melody,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
    )

    steps = engine.arrange_progression(
        list(working), options=options, diagnostics=diagnostics
    )
    return steps, rescued, notes

def _slot_options(
    triples: Sequence[Tuple[str, str, str]],
    timings: Sequence[Tuple[Optional[int], Optional[float], Optional[float]]],
    non_chord_tone: str,
    grips: Tuple[str, ...],
    texture: str,
    beats_per_bar: int,
    bass: str = "auto",
    melody: str = "auto",
    harmony: str = "auto",
    grid: str = "auto",
) -> ArrangeOptions:
    """The request `arrange_slots` makes of the engine, as one value.

    Extracted from `arrange_slots` so this module's whole remaining job - deciding
    *what to ask for*, rather than deciding the voicing itself - is a named thing a
    test can read. It is a seam, not a public API: the function is private and the
    arrangement it produces is tested through `arrange_slots`.

    Two things happen here that used to be scattered through the loop.

    **The timings are normalised to one entry per triple.** Written out rather than
    reusing `timings` because that sequence is a `Sequence` and may be shorter than
    `triples`, and pyright will not narrow an index it cannot see. The engine guards
    its own indexing too, but establishing the length invariant once is better than
    defending it twice.

    **The slash bass becomes a pitch class per index.** `None` for a triple with no
    slash, which is every triple of a score-imported head unless the score writes
    one. The bass note normally rides along in the chord name, so the triple carries
    it and the name does not have to; a caller that has already promoted the bass
    into the quality writes the promoted name. `bass_cost` is supplied alongside
    because the pitch class says *what* is wanted and the cost says *how near* a
    candidate is to it; neither alone narrows anything.

    **The slash is read with a general pattern, not the Weimar one.** This used to
    call `wjazzd.parse_weimar_chord(name)[2]`, which needed the 108-suffix Weimar
    quality table to reach - and returned the *bass field*, so the table bought
    nothing here. What survives is only the ordinary reading of `A-/G`, so it is
    spelled out below and the dependency on a database's spelling goes with it.
    """
    # --- the timings, normalised to one entry per triple -------------------------
    #
    # Written out rather than reusing `timings` because that sequence is a `Sequence`
    # and may be shorter than `triples`, and pyright will not narrow an index it
    # cannot see. The engine guards its own indexing too, but doing it here means the
    # length invariant is established once rather than defended twice.
    typed_timings: List[Tuple[Optional[int], Optional[float], Optional[float]]] = [
        (bar, beat, duration)
        if index < len(timings) else (None, None, None)
        for index, (bar, beat, duration) in enumerate(timings)
    ]
    typed_timings.extend(
        [(None, None, None)] * (len(triples) - len(typed_timings))
    )

    # --- the slash bass, as data -------------------------------------------------
    bass_pcs: Dict[int, Optional[int]] = {}
    for index, (_melody, _quality, name) in enumerate(triples):
        # Named `slash`, not `bass`: this function now takes a `bass` **policy**
        # parameter, and a loop local of that name would silently shadow it and pass a
        # pitch class where the policy belongs.
        slash = _slash_bass(name)
        if slash is not None:
            bass_pcs[index] = bass_pitch_class(slash)

    return ArrangeOptions(
        non_chord_tone=non_chord_tone,
        grips=grips,
        texture=texture,
        bass=bass,
        melody=melody,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        timings=typed_timings,
        bass_pcs=bass_pcs or None,
        bass_cost=bass_cost,
    )
