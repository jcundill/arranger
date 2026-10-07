"""The engine: `VoiceLeadingEngine`, and the one step loop.

This module *decides*. Every other module produces something - candidates in
`grips`, a cost in `cost`, a role in `textures`, a thumb line in `bass` - and this
is where those are combined into an arrangement.

**The class is a facade over functions that now live elsewhere.** Each delegate
below is one line forwarding to the module that owns the body, and the bodies
themselves were moved rather than rewritten. The classmethods are kept because
roughly forty test call sites and every front end spell them
`VoiceLeadingEngine.get_drop2_voicings(...)`: a refactor is not the moment to
break those spellings, and a delegate that forwards leaves no second
implementation to drift.

`prepare_step` and `arrange_progression` are the only substantial bodies left
here, and they are byte-for-byte what they were. That is what makes the two entry
points unable to disagree - `wjazzd.arrange_slots` delegates to this loop rather
than running a second one. The project has already paid for the two-loop version:
the corpus path was built separately, drifted, and voiced an `Am7` under a written
`Bbm7` for twenty-five transcriptions before anyone noticed. The six decisions
both loops used to make separately now live in `decisions`, one function each.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Container, List, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass import (
    BASS_AUTO,
    BASS_NONE,
    BASS_STYLES,
    BASS_WALK,
    BassNote,
    _held_shape,
    _place_bass,
    _previous_bass,
    _Slot,
    _walking_slots,
    bass_allowed,
)
from .chords import (
    NON_CHORD_TONE_EXTENSIONS,
    NON_CHORD_TONE_STRATEGIES,
    ChordParser,
    normalised_harmony,
)
from .decisions import (
    MELODY_ALONE_NO_CHORD,
    MELODY_ALONE_REST,
    MELODY_ALONE_TEXTURE,
    is_bass_only,
    is_repeated_step,
    melody_alone_case,
    resolve_texture_grips,
    select_step_voicing,
    should_demote_to_melody_alone,
    should_promote_fill,
)
from .diagnostics import Diagnostics, default_diagnostics
from .grips import (
    DEGREE_OFFSETS_FROM_ROOT,
    DROP2_INTERVAL_SETS,
    GRIP_PREFERENCE,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
)
from .options import ArrangeOptions
from .textures import (
    GRID_EVERY_NOTE,
    HARMONY_AUTO,
    HARMONY_SHELL_ROOT,
    MELODY_AUTO,
    MELODY_BASS,
    TEXTURE_GRIPS,
    TEXTURE_STYLES,
    THUMB_TEXTURES,
    _metric_weight,
    _roles_for_slot,
    melody_only_selection,
    on_grid,
    parse_grid,
    parse_harmony,
    parse_voices,
    resolve_grid,
    resolve_harmony,
    resolve_voices,
    voices_have_soprano,
)
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    ROLE_TARGET,
    STANDARD_TUNING,
    ArrangementStep,
    Voicing,
    _note_name,
)


@dataclass
class StepPreparation:
    """One step's voicing candidates, plus the bookkeeping to report the step.

    Returned by `VoiceLeadingEngine.prepare_step` so a caller that needs extra
    per-step control - the corpus loader honours a slash bass and attaches the
    slot's timing - can choose from these candidates using the engine's own rule
    rather than re-deriving the voicing itself.

    That distinction is load-bearing. The loader used to build its own
    candidates and call `_best_voicing` directly, which silently skipped the
    non-chord-tone strategies, the selector's tone-purity criterion (because
    `allowed_tones` defaults to None) and the octave-down rescue. `chord_type`
    and `chord_name` stay the *written* chord even when `harmonized_as` names a
    substitute, because `allowed_tones` has always been built from the written
    chord and changing that would move the library's published output.
    """

    candidates: List["Voicing"]
    written_melody: str
    melody: str
    original_melody: Optional[str]
    chord_type: str
    chord_name: str
    is_non_chord_tone: bool
    strategy: Optional[str]
    harmonized_as: Optional[str]





def _resolve_bass(
    texture: str,
    bass: str,
    voices: Tuple[str, ...],
    diagnostics: Diagnostics,
) -> str:
    """The policy to actually run: `BASS_AUTO` resolved, validated, or refused.

    Three outcomes, in the order they are decided:

    - `auto` resolves from the texture and the selection. `texture="walking_bass"`
      walks; so does a melody-only selection that names the bass voice -
      `melody="soprano,bass"` is the tune with a thumb under it, the part the
      `melody_bass` texture used to spell. A lone `bass` selection is **not**
      melody-only (it has no soprano) and keeps no thumb: that part already is the
      bass line, and a thumb under it would double it.
    - an unknown spelling raises. The same rule as everywhere else in the library: a
      policy nobody recognises is a question, and answering it by defaulting to a walk
      would put a bass line under an arrangement that did not ask for one.
    - a combination the left hand cannot accommodate is **refused with a warning**, and
      the arrangement proceeds without a thumb line. Not dropped and not degraded: a
      walking line with gaps in it is worse than no line, and losing the bass costs less
      than losing the tune. The warning names a texture that would work.

    **The selection is passed rather than the flags derived from it** - the route
    (`voices_have_soprano`), the comping arity (`len(voices)`), the lone-bass case
    and the melody-only case are all decided here from the one fact, so the two
    spellings of one request cannot disagree. Which left-hand shapes an arrangement
    will generate is decided by the selection, and no texture can express it:
    `uniform` is a real grip palette on the melody-bearing route and a
    **meaningless name** on the comping one, where the shapes come from
    `get_comping_voicings`, and inert a third time over on a melody-only selection,
    whose shapes are single frets. So this function asks `bass_allowed` about the
    comping route's capacity when that is the route, the melody-only route's when
    that is, and the texture's otherwise.

    This is why the call site resolves the melody axis **first**. That ordering is
    deliberate rather than incidental - see `arrange_progression`, and note that the two
    resolutions are independent of each other, so swapping them back would only
    reintroduce the bug. What must not change is that both happen *before*
    `has_thumb` is read, because that flag gates whether the walked-beat union is built
    at all.
    """
    melody_voiced = voices_have_soprano(voices)
    melody_only = melody_only_selection(voices)
    if bass == BASS_AUTO:
        bass = (
            BASS_WALK
            if texture in THUMB_TEXTURES
            or (melody_only and MELODY_BASS in voices)
            else BASS_NONE
        )
    if bass not in BASS_STYLES:
        raise ValueError(
            f"Unknown bass policy {bass!r}; expected one of {BASS_STYLES}, "
            f"or 'auto'"
        )
    allowed, reason = bass_allowed(
        texture,
        bass,
        # `None` for the melody-bearing route, so `bass_allowed` asks the route's
        # own capacity - the melody-only route's, or the texture's palette.
        # `len(voices)` on the comping one, which is the arity the comping
        # generator will actually build.
        None if melody_voiced else len(voices),
        voices == (MELODY_BASS,),
        melody_only=melody_only,
    )
    if not allowed:
        diagnostics.warn(f"Warning: {reason}")
        return BASS_NONE
    return bass


def _resolve_melody(voices: str) -> Tuple[str, ...]:
    """The voices to actually play: `auto` resolved, parsed, validated.

    Two steps and they are not the same step. **Parsing** turns the caller's string into a
    canonical tuple of voice names, so `tenor,alto` and `alto,tenor` are one request -
    `textures.parse_voices` owns the vocabulary and the ordering. **Resolution** is what
    `textures.resolve_voices` owns: `auto` becomes every voice.

    An unknown voice name raises from `parse_voices`, before any voicing work, on the
    library's standing rule: a spelling nobody recognises is a question, and answering it
    by dropping the voice would hand back a part missing something nobody asked it to drop.
    """
    return resolve_voices(parse_voices(voices))



def _resolve_harmony(
    harmony: str, voices: Tuple[str, ...], diagnostics: Diagnostics
) -> str:
    """The degree family to actually voice: `auto` resolved, parsed, or refused.

    The same two-step shape as `_resolve_melody` above - parse, then resolve - because
    it is the same rule about the same thing: `textures` owns the vocabulary and the
    refusal, this function owns nothing but the wiring.

    Takes **no texture**, and that is deliberate rather than an oversight: whether a
    degree family can be voiced depends on how many notes were asked for, and on
    nothing about where the notes fall. `guide` under `walking_bass` and `guide` under
    `uniform` are the same two degrees.

    Resolved **once per arrangement**, next to `_resolve_melody` and for the reason
    stated there: the band does not change halfway through a tune.
    """
    return resolve_harmony(parse_harmony(harmony), voices, diagnostics)


def _resolve_grid(grid: str, beats_per_bar: int, diagnostics: Diagnostics) -> str:
    """The grid to place chords on: parsed, `auto` resolved, validated or refused.

    The same two-step shape as `_resolve_melody` and `_resolve_harmony` above,
    because it is the same rule about the same kind of thing: `textures` owns the
    vocabulary and the refusal, this function owns only the wiring.

    **Takes the metre rather than a texture**, and that is what distinguishes it from
    `harmony`. Whether a rhythm fits is a property of the metre - `final_and` is the
    upbeat of the last beat whatever the arrangement is doing - so it is resolved
    against `beats_per_bar` and nothing else.
    """
    return resolve_grid(parse_grid(grid), beats_per_bar, diagnostics)


class VoiceLeadingEngine:
    """Generates and voice-leads jazz guitar voicings dynamically.

    A facade. Every generator, the cost rule and the non-chord-tone helpers now
    live in `grips`, `cost` and `chords` respectively; the methods below forward
    to them, so the published spelling is unchanged. What is actually implemented
    here is the step loop - `prepare_step` and `arrange_progression` - and the two
    private helpers it calls.

    **Why the delegates are written out rather than bound.**
    `get_grip_voicings = classmethod(get_grip_voicings)` is shorter, and it is what
    a first attempt did - but it is unsatisfiable: ruff's B010 wants `setattr`,
    and `setattr` is invisible to a type checker, so each pass breaks the one
    before it. Real one-line methods satisfy both. The full docstring for each
    lives with the implementation; these say where that is.
    """

    # Tables, re-exported as class attributes. `grip_chart`, `wjazzd`, `headxml`
    # and the tests all read these off the class; they are the same objects, not
    # copies, so a caller editing one edits the one the engine reads.
    DROP2_INTERVAL_SETS = DROP2_INTERVAL_SETS
    DEGREE_OFFSETS_FROM_ROOT = DEGREE_OFFSETS_FROM_ROOT
    NON_CHORD_TONE_EXTENSIONS = NON_CHORD_TONE_EXTENSIONS
    NON_CHORD_TONE_STRATEGIES = NON_CHORD_TONE_STRATEGIES

    # --- delegates: each forwards to the module that owns the body ---

    @staticmethod
    def _parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
        """See `grips._parse_chord_name`."""
        return _grips._parse_chord_name(name)

    @staticmethod
    def _string_sets_for(grip: str, top_string: int) -> List[Tuple[int, ...]]:
        """See `grips._string_sets_for`."""
        return _grips._string_sets_for(grip, top_string)

    @classmethod
    def _chord_context(
        cls, chord_type: str, chord_name: Optional[str]
    ) -> Tuple[str, Optional[int], Tuple[int, ...]]:
        """See `grips._chord_context`."""
        return _grips._chord_context(chord_type, chord_name)

    @staticmethod
    def get_comping_voicings(
        chord_type: str,
        chord_name: Optional[str] = None,
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        notes: int = 3,
        bass_voice: bool = False,
        shell_root: bool = False,
    ) -> List[Voicing]:
        """See `grips.get_comping_voicings`."""
        return _grips.get_comping_voicings(
            chord_type,
            chord_name,
            fret_min,
            fret_max,
            notes,
            bass_voice,
            shell_root,
        )

    @staticmethod
    def _lower_soprano_strings(top_strings: Tuple[int, ...]) -> Tuple[int, ...]:
        """See `grips._lower_soprano_strings`."""
        return _grips._lower_soprano_strings(top_strings)

    @classmethod
    def get_grip_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_string: int = 5,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """See `grips.get_grip_voicings` - the full docstring is there."""
        return _grips.get_grip_voicings(
            melody_note, chord_type, chord_name, top_string, grips
        )

    @classmethod
    def get_drop2_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_string: int = 5,
    ) -> List[Voicing]:
        """See `grips.get_drop2_voicings`."""
        return _grips.get_drop2_voicings(melody_note, chord_type, chord_name, top_string)

    @classmethod
    def get_interval_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_string: int = 5,
    ) -> List[Voicing]:
        """See `grips.get_interval_voicings`."""
        return _grips.get_interval_voicings(
            melody_note, chord_type, chord_name, top_string
        )

    @classmethod
    def get_octave_down_candidates(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """See `grips.get_octave_down_candidates`."""
        return _grips.get_octave_down_candidates(
            melody_note, chord_type, chord_name, top_strings, grips
        )

    @classmethod
    def get_all_grip_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """See `grips.get_all_grip_voicings`."""
        return _grips.get_all_grip_voicings(
            melody_note, chord_type, chord_name, top_strings, grips
        )

    @classmethod
    def get_all_drop2_voicings(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
    ) -> List[Voicing]:
        """See `grips.get_all_drop2_voicings`."""
        return _grips.get_all_drop2_voicings(
            melody_note, chord_type, chord_name, top_strings
        )

    @classmethod
    def get_melody_only_voicing(
        cls,
        melody_note: Note,
        prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
    ) -> Optional[Voicing]:
        """See `grips.get_melody_only_voicing`."""
        return _grips.get_melody_only_voicing(melody_note, prefer)

    @classmethod
    def sustain_inner_voices(
        cls, previous_voicing: Voicing | dict, melody_note: Note
    ) -> Optional[Voicing]:
        """See `grips.sustain_inner_voices`."""
        return _grips.sustain_inner_voices(previous_voicing, melody_note)

    @classmethod
    def is_chord_tone(
        cls, melody_note: Note, chord_type: str, chord_name: Optional[str] = None
    ) -> bool:
        """See `chords.is_chord_tone`."""
        return _chords.is_chord_tone(melody_note, chord_type, chord_name)

    @classmethod
    def resolve_non_chord_tone(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: str,
        strategy: str = "extension",
        next_melody: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """See `chords.resolve_non_chord_tone`."""
        return _chords.resolve_non_chord_tone(
            melody_note, chord_type, chord_name, strategy, next_melody
        )

    @classmethod
    def _resolution_pitch_class(
        cls,
        melody_note: Note,
        root_str: str,
        canonical_type: str,
        next_melody: Optional[str],
    ) -> Optional[int]:
        """See `chords._resolution_pitch_class`."""
        return _chords._resolution_pitch_class(
            melody_note, root_str, canonical_type, next_melody
        )

    @staticmethod
    def _window_penalty(
        candidates: List[Voicing],
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
    ) -> int:
        """See `cost._window_penalty`."""
        return _cost._window_penalty(candidates, fret_min, fret_max)

    @classmethod
    def voicing_cost(
        cls,
        voicing: Voicing,
        previous: Optional[Voicing],
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        allowed_tones: Optional[Container[int]] = None,
        root_pc: Optional[int] = None,
        melody_pc: Optional[int] = None,
    ) -> Tuple[float, ...]:
        """See `cost.voicing_cost` - the library's central invariant is there."""
        return _cost.voicing_cost(
            voicing, previous, fret_min, fret_max, allowed_tones, root_pc, melody_pc
        )

    @classmethod
    def _best_voicing(
        cls,
        candidates: List[Voicing],
        previous: Optional[Voicing] = None,
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        allowed_tones: Optional[Container[int]] = None,
        root_pc: Optional[int] = None,
        melody_pc: Optional[int] = None,
    ) -> Optional[Voicing]:
        """See `cost._best_voicing`."""
        return _cost._best_voicing(
            candidates, previous, fret_min, fret_max, allowed_tones, root_pc, melody_pc
        )

    @staticmethod
    def calculate_voice_leading_distance(
        voicing_a: Voicing | dict, voicing_b: Voicing | dict
    ) -> float:
        """See `cost.calculate_voice_leading_distance`."""
        return _cost.calculate_voice_leading_distance(voicing_a, voicing_b)

    @staticmethod
    def calculate_pitch_leading_distance(
        voicing_a: Voicing | dict, voicing_b: Voicing | dict
    ) -> float:
        """See `cost.calculate_pitch_leading_distance`."""
        return _cost.calculate_pitch_leading_distance(voicing_a, voicing_b)



    @classmethod
    def prepare_step(
        cls,
        progression: Sequence[Tuple[Optional[str], str, str]],
        index: int,
        previous: Optional[Voicing] = None,
        previous_chord: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
        diagnostics: Optional[Diagnostics] = None,
    ) -> Optional[StepPreparation]:
        """
        Builds one step's candidates, leaving the choice of shape to the caller.

        This is a whole step up to selection: the candidates across every allowed
        soprano string and grip family, the octave-down rescue, and the
        non-chord-tone strategies. `arrange_progression` selects with
        `_best_voicing` straight afterwards, and the corpus loader selects the
        same way after honouring a slash bass, so the two cannot drift.

        Returns None when the step has no voicing at all. `previous` is only read
        by the `sustain` strategy, and `previous_chord` is what that strategy
        reports as `harmonized_as`.

        `diagnostics` receives the one warning this function can raise - a
        non-chord tone no strategy could resolve. It defaults to printing, which
        is what this function always did; see `diagnostics.Diagnostics`.
        """
        if diagnostics is None:
            diagnostics = default_diagnostics()
        note_str, chord_type, name = progression[index]
        if note_str is None:
            # No melody to pin. `arrange_progression` skips such a slot before it can
            # reach here - every singing route needs a note, and the comping route
            # never calls this - so this is the widened triple type's honest answer
            # rather than a `Note(None)` waiting for a caller that lies.
            return None
        melody_note = Note(note_str)

        # Chord-tone match first, quality-only fallback second, across every
        # allowed soprano string and every grip family.
        candidates = cls.get_all_grip_voicings(
            melody_note, chord_type, chord_name=name,
            top_strings=top_strings, grips=grips,
        )

        # A melody whose best position sits outside the neck window is re-voiced an
        # octave down on the B string. The written pitch is kept in original_melody.
        # Decided before the non-chord-tone strategies run, so a substituted chord
        # is voiced at the transposed pitch too rather than snapping back up.
        #
        # The guard requires candidates to exist: this repositions a voicing that
        # is playable but sits too high. A melody unreachable at the written pitch
        # (C6, fret 20 - past the end of the board) is left alone, because there is
        # no shape to move down and respelling it would hide the real problem.
        sounding_melody = melody_note
        original_melody: Optional[str] = None
        if candidates and cls._window_penalty(candidates, fret_min, fret_max) > 0:
            octave_down = cls.get_octave_down_candidates(
                melody_note, chord_type, chord_name=name,
                top_strings=top_strings, grips=grips,
            )
            # Only take the lower octave when it genuinely improves the placement,
            # or a merely slightly out-of-window melody would be moved for nothing.
            here = cls._window_penalty(candidates, fret_min, fret_max)
            there = cls._window_penalty(octave_down, fret_min, fret_max)
            if octave_down and there < here:
                candidates = octave_down
                sounding_melody = Note(_note_name(melody_note.midi_note() - 12))
                original_melody = note_str

        strategy_used: Optional[str] = None
        harmonized_as: Optional[str] = None
        is_non_chord_tone = (
            ChordParser.canonical_quality(chord_type) in ChordParser.CHORD_TONES_FROM_ROOT
            and not cls.is_chord_tone(melody_note, chord_type, name)
        )

        if is_non_chord_tone and non_chord_tone != "legacy":
            # Strategy 3 first: holding the shape moves less than any re-voicing.
            if non_chord_tone == "sustain" and previous is not None:
                sustained = cls.sustain_inner_voices(previous, sounding_melody)
                if sustained is not None:
                    candidates = [sustained]
                    strategy_used = "sustain"
                    harmonized_as = previous_chord

            # Strategies 1 and 2 reharmonise the note as a genuine chord tone.
            if strategy_used is None:
                resolved = cls.resolve_non_chord_tone(
                    sounding_melody,
                    chord_type,
                    name,
                    non_chord_tone,
                    next_melody=cls._next_resolution_melody(progression, index),
                )
                if resolved is not None:
                    substitute_quality, substitute_name = resolved
                    substituted = cls.get_all_grip_voicings(
                        sounding_melody,
                        substitute_quality,
                        chord_name=substitute_name,
                        top_strings=top_strings,
                        grips=grips,
                    )
                    if substituted:
                        candidates = substituted
                        strategy_used = non_chord_tone
                        harmonized_as = substitute_name

            if strategy_used is None:
                diagnostics.warn(
                    f"Warning: melody {note_str} is not a chord tone of {name} and the "
                    f"'{non_chord_tone}' strategy found no voicing; keeping the fallback"
                )

        if not candidates:
            return None

        return StepPreparation(
            candidates=candidates,
            written_melody=note_str,
            # The transposed pitch when moved down an octave: the step reports
            # what actually sounds.
            melody=(
                note_str
                if original_melody is None
                else _note_name(sounding_melody.midi_note())
            ),
            original_melody=original_melody,
            chord_type=chord_type,
            chord_name=name,
            is_non_chord_tone=is_non_chord_tone,
            strategy=strategy_used,
            harmonized_as=harmonized_as,
        )


    @classmethod
    def arrange_progression(
        cls,
        progression: Sequence[Tuple[Optional[str], str, str]],
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
        # `Sequence` and Optional *bar* and *beat*, not `List[Tuple[int, float, ...]]`:
        # the corpus supplies `(None, None, None)` for a slot it could not place, so
        # the two entry points genuinely hold different types. This is the fourth
        # time that has cost this library something, and previously it showed up as a
        # signature that would not typecheck rather than as a crash at runtime - the
        # `float(beat)` below had assumed a non-None beat until the corpus was first
        # allowed to delegate here.
        timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
        texture: str = "uniform",
        bass: str = BASS_AUTO,
        melody: str = MELODY_AUTO,
        harmony: str = HARMONY_AUTO,
        grid: str = GRID_EVERY_NOTE,
        beats_per_bar: int = 4,
        diagnostics: Optional[Diagnostics] = None,
        options: Optional[ArrangeOptions] = None,
    ) -> List[ArrangementStep]:
        """
        Takes a progression of (Melody Note, Chord Quality, Name) tuples
        and computes the optimal voice-led arrangement.

        top_strings selects which strings may carry the melody (see
        MELODY_STRING_CHOICES_FULL). The default allows the high E, the B *and* the G
        string, so a melody can hold its place on the neck by changing strings rather
        than by moving the hand, and a melody below the high E string's open pitch is
        still arranged rather than skipped.

        fret_min and fret_max bound the comfortable neck window the selector aims for
        (frets 2-13 by default). They are a strong preference, not a constraint: a step
        with no voicing inside the window is still played, just outside it, because
        losing a chord of the tune is worse than being a fret out of position.

        grips limits which grip families may be used, in the order they break a tie
        (see GRIP_PREFERENCE). The default offers all of them. `grips=("drop2",)` with
        `top_strings=MELODY_STRING_CHOICES` reproduces this library's original,
        four-string-drop-2-only output exactly, which is what a caller wants when they
        need a known arrangement rather than the best one.

        non_chord_tone selects what happens when a melody note is not a chord tone
        (one of NON_CHORD_TONE_STRATEGIES):
          'extension'  - reharmonise the note as a chord extension (D over Cmaj7
                         becomes Cmaj9), the default;
          'diminished' - Barry Harris 6/dim7 substitution (D over Cmaj7 -> Bdim7);
          'sustain'    - keep the previous chord's inner voices and move only the
                         melody, for brief passing tones;
          'legacy'     - keep the original quality-only fallback behaviour.
        Steps whose melody is already a chord tone are unaffected by this choice.

        A step whose chord_type or name is NO_CHORD ("NC") is voiced as the melody
        alone on a single fret (get_melody_only_voicing) and flagged
        melody_only=True. Such a step is short-circuited before any chord logic,
        so it is never reharmonised and never warns; it also does not take part in
        voice-leading minimisation, and being neither a drop-2 voicing nor a
        four-string shape it is exempt from that playability invariant.

        **Texture and rhythm.** `timings` is each slot's own `(bar, beat, duration)`
        in the caller's units - a signed bar, the beat within it, and a length in
        whole notes - the same triple `ArrangementStep` already carries. `None`, the
        default, means the caller has told us nothing about where its notes fall, and
        then every slot is a principal note and this function behaves exactly as it
        always has.

        `bass` selects the **policy** the thumb line is written on, from BASS_STYLES:
        `"none"` (the default, no thumb line), `"anchors"` (a note only where the
        harmony changes, carrying that chord's root), or `"walk"` (a note on every beat,
        which is what makes the line a walk). It is an argument of its own rather than a
        property of the texture, because the pattern is the composer's choice and the set
        of patterns is open - a new one is a row in `BASS_POLICY_ROLES`.

        `BASS_AUTO`, the default here, resolves from the texture and the voice
        selection: `texture="walking_bass"` walks, and so does a melody-only selection
        that names the bass voice (`melody="soprano,bass"` - the tune with a thumb under
        it); everything else does not. So `texture="walking_bass"` and
        `texture="walking_bass", bass="walk"` are the same arrangement, and
        `bass="none"` on a walking bass gives the same strong-beat shells with the thumb
        dropped - a coherent texture in its own right. A lone `melody="bass"` selection
        keeps no thumb: that part already is the bass line, and a thumb under it
        would double it.

        A combination the left hand cannot accommodate is **refused rather than
        degraded**. `uniform` leaves no bass string free, because its four-note grips can
        span all three, so a thumb line under it would come and go; the refusal names a
        texture that would work and the arrangement still sounds, because losing a bass
        costs less than shipping a line with holes in it.

        `texture="targets"` uses the timing to arrange the way the guide describes:
        a full four-note chord on beats 1 and 3 of the bar, and a shell, a 3rd/6th
        interval or the melody alone in between. `beats_per_bar` is what the rule
        reads to decide which beats exist, so a 3/4 or 2/2 head is not treated as
        4/4 (see TARGET_BEATS). The rule changes *which grips are offered*, never
        the cost tuple, so the selection order and the engine's determinism are
        untouched.

        A `timings` list shorter than `progression` is not an error: the unlocated
        trailing steps are simply treated as principal notes, which is the same
        "we know nothing" rule that governs `timings=None`. The guard is the one
        `wjazzd.arrange_slots` already applies to its own timings, for the same
        reason - a hand-built list must not silently shift the rhythm.

        `texture="walking_bass"` adds a thumb line on the bass strings under a light
        left hand: a **shell** (3rd & 7th) on a target beat, the **melody alone**
        between, and a walk underneath, one thumb note per beat of the bar. Four
        consequences are part of its contract rather than details of it:

        - **It may return more steps than it was given.** The bass grid is finer than
          the melody grid, so a bar whose melody is a whole note still yields a step
          for each of its `beats_per_bar` beats - one carrying the melody and the rest
          marked `bass_only`, whose upper voices are held rather than re-struck. That
          is **four** steps in 4/4, **three** in 3/4 and **two** in 2/2, because the
          grid is `beats_per_bar` beats wide; the wording here used to say "four", and
          three of the four committed scores are in cut time. Callers that zip their
          progression against the result, or derive a bar count from `len(steps)`, are
          wrong under this texture only; `uniform` and `targets` are untouched. A step
          the walk invented can be promoted to a **target** when the melody moves onto
          it, and then it states its harmony rather than holding - which is
          `decisions.is_bass_only`, and the reason a `bass_only` step is always a fill.
        - **A `bass_only` step carries the melody sounding at that instant**, not the
          melody the walk last passed. Those differ whenever the melody moves on a beat
          the walk does not visit - the beat 2.5 of a 2/2 bar, where the walk is on 1.0
          and 2.0 - and getting it wrong states a note the score has not reached yet.
          See `docs/open-issues.md` item 5.
        - **A fill is the melody alone**, and so is a target no shell can sound. The
          chord name above such a step describes the harmony rather than everything
          sounding, which is the texture rather than a defect - the harmony is stated
          in full at the next target.
        - **With `timings=None` the walk degrades to one note per slot.** There is no
          beat grid to place the walk on, and that is the path every existing
          hand-written caller takes, so it is documented rather than silent.

        The bass is merged into `Voicing.frets` *after* `_best_voicing` has chosen the
        upper shape, so it cannot enter `voicing_cost`'s tuple by construction. That
        also means the combined string set is deliberately **not** a member of
        `supported_string_sets()`: the playability invariant applies to the upper
        voices, with exactly one `BASS_STRING_INDICES` string outside that set carrying
        the thumb below it.

        `diagnostics` collects this function's warnings - a melody that reaches no
        voicing, a step demoted to the melody alone, a fill promoted to a target, an
        unresolvable non-chord tone, a thumb with nowhere to go. It defaults to
        printing each one, which is what this function has always done, so a caller
        that passes nothing sees no change. Pass a `Diagnostics()` to collect them
        silently instead; see the `diagnostics` module for why that is a value
        rather than a logging call.
        """
        # `options` and the keywords are two spellings of the same knobs. An
        # `options` wins outright rather than being merged field by field: a partial
        # merge would make it impossible to tell which of two conflicting values won,
        # and there is no use case for "the options, but with one keyword overridden".
        # It raises instead of silently preferring one, because a caller who passes
        # both has a bug and would otherwise spend an afternoon finding out why their
        # keyword had no effect.
        if options is not None:
            given = {
                name: value
                for name, value in (
                    ("top_strings", top_strings),
                    ("non_chord_tone", non_chord_tone),
                    ("fret_min", fret_min),
                    ("fret_max", fret_max),
                    ("grips", grips),
                    ("texture", texture),
                    # `bass` is compared here like every other knob, which it was not
                    # for its whole life: `ArrangeOptions.bass` defaulted to the
                    # resolved "none" while the keyword defaults to the `BASS_AUTO`
                    # sentinel, so the two could never be compared - and the field was
                    # never read back out of `options` either, which is what made
                    # `--bass` silently inert on every slot-path caller (`arranger
                    # head` among them) while the walking-bass tests, which pass the
                    # keyword directly, stayed green. The field default is the sentinel
                    # now, so the comparison below holds, and the unpack below reads the
                    # field back.
                    ("bass", bass),
                    ("melody", melody),
                    ("harmony", harmony),
                    ("grid", grid),
                    ("beats_per_bar", beats_per_bar),
                )
                if value != ArrangeOptions.__dataclass_fields__[name].default
            }
            if given:
                raise ValueError(
                    f"arrange_progression got both options= and the keyword(s) "
                    f"{sorted(given)}; pass one or the other, not both"
                )
            top_strings = options.top_strings
            non_chord_tone = options.non_chord_tone
            fret_min = options.fret_min
            fret_max = options.fret_max
            grips = options.grips
            texture = options.texture
            bass = options.bass
            melody = options.melody
            harmony = options.harmony
            grid = options.grid
            beats_per_bar = options.beats_per_bar
            if options.timings is not None:
                timings = list(options.timings)
        bass_pcs = options.bass_pcs if options is not None else None
        bass_cost_for = options.bass_cost if options is not None else None

        if non_chord_tone not in cls.NON_CHORD_TONE_STRATEGIES:
            raise ValueError(
                f"Unknown non_chord_tone strategy {non_chord_tone!r}; "
                f"expected one of {cls.NON_CHORD_TONE_STRATEGIES}"
            )
        # Checked up front, so a typo costs a message rather than a full arrangement
        # followed by a surprise.
        texture_grips = TEXTURE_GRIPS.get(texture)
        if texture_grips is None:
            raise ValueError(
                f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
            )
        # Resolved once, here, and passed down: every warning this function reaches
        # goes to the one collector, so a caller that passed one sees all of them
        # rather than the first few. Defaults to printing, as this always did.
        if diagnostics is None:
            diagnostics = default_diagnostics()

        arrangements: List[ArrangementStep] = []

        # The walking bass is computed here, over the **walked beats** rather than
        # over the slots, and it yields a pitch *class* rather than a pitch and a
        # string: neither the octave nor the string can be decided before an upper
        # voicing exists, and only this function is downstream of one. `_place_bass`
        # resolves both together, after selection.

        # The melody axis, resolved first and for the reason below. `auto` keeps
        # every voice, which is why nothing below this line changes unless a caller
        # opts in. Decided once rather than per step: the band does not change halfway
        # through a tune.
        #
        # **This resolution comes before `_resolve_bass` because the bass policy needs
        # to know which route the engine is on**, and only this line knows. `bass_allowed`
        # measures thumb capacity against `TEXTURE_GRIPS`, which describes the shapes the
        # melody-bearing route generates and is *inert* on the comping one - so asking it
        # about a texture on that route refused a combination that is playable and, worse,
        # told the player to change a setting that could not affect the result. See
        # `comping_capacity`, and `docs/open-issues.md` for the measurement.
        #
        # The two resolutions are independent of each other, so the order between them
        # carries no other meaning; what matters is that both finish before
        # `has_thumb` is read, because that flag gates whether the walked-beat union is
        # built at all.
        voices = _resolve_melody(melody)
        melody_voiced = voices_have_soprano(voices)
        # The melody-only selection, decided once here and read by the bass policy,
        # the grip resolution and the promotion rule below: `(soprano,)` is the
        # tune alone and `(soprano, bass)` the tune with a thumb under it,
        # whatever `texture=` says - the texture is inert on that route, the same
        # way it is on the comping one.
        melody_only = melody_only_selection(voices)

        # The bass policy. `auto` means "whatever this texture and this selection
        # mean", so `walking_bass` keeps walking and a melody-only selection that
        # names the bass voice walks too; an explicit policy overrides both, which
        # is what lets a texture that was never written for a thumb line carry one.
        #
        # The resolved `voices` are passed rather than the flags derived from them -
        # the route, the arity and the lone-bass case are decided inside, from the
        # selection, so the two spellings of one request cannot disagree.
        bass = _resolve_bass(
            texture,
            bass,
            voices,
            diagnostics,
        )
        has_thumb = bass != BASS_NONE

        # The harmony axis, resolved here for the same reason and read only by the
        # comping route below. Resolving it unconditionally rather than inside
        # `if not melody_voiced` is deliberate: a spelling nobody recognises must be
        # reported **once, up front**, rather than never at all on an arrangement where
        # the guitar happens to be singing - the same argument as `_resolve_melody`'s.
        harmony_family = _resolve_harmony(harmony, voices, diagnostics)
        # The grid axis, resolved here for the same reason and read by **both** routes
        # below rather than only the comping one - unlike `harmony=`, which the guitar
        # singing makes unreachable. A grid says where a chord lands, and that is a
        # question about the part whether the guitar is singing it or comping under a
        # horn, so scoping it to one route would make `grid=` silently inert on a
        # melody-bearing arrangement rather than doing nothing there.
        grid_pattern = _resolve_grid(grid, beats_per_bar, diagnostics)

        slots: Optional[List[_Slot]] = None
        if has_thumb:
            # Decision B: the union is built here, before the melody loop, so the
            # loop's index still indexes the skeleton it was given. `_walking_slots`
            # is shared with `wjazzd.arrange_slots`, so the corpus and head paths
            # cannot walk a different line from this one - see its docstring for why
            # that duplication has already cost this project one bug.
            slots = _walking_slots(progression, timings, beats_per_bar, bass)

        # Harmony and melody state for the walking-bass role rule. Both are read from
        # what actually sounds, not from the written chord, so a substituted chord
        # compares as itself (the same `normalised_harmony` the `repeated` hold uses).
        last_target_harmony: Optional[Tuple[Optional[str], Optional[str]]] = None
        previous_melody_midi: Optional[int] = None

        # One slot per triple, carrying that triple's own `(bar, beat, duration)` or
        # None for a slot nobody located. Read defensively - a short `timings` leaves
        # the trailing steps unlocated - and, importantly, tolerating a *present but
        # empty* entry: the corpus normalises its unplaced slots to `(None, None, None)`,
        # so `float(beat)` here has to cope with None or the head path raises the
        # moment it is allowed to delegate. That is the fourth time the two paths'
        # differing timing types have cost something, and the first time it was a
        # crash rather than a signature that would not typecheck.
        def _timing(index: int) -> Tuple[Optional[int], Optional[float], Optional[float]]:
            if timings is None or index >= len(timings):
                return (None, None, None)
            bar, beat, duration = timings[index]
            return (
                bar,
                None if beat is None else float(beat),
                duration,
            )

        loop: List[_Slot] = (
            slots if slots is not None
            else [
                _Slot(index=index, bar=bar, beat=beat, duration=duration)
                for index, (bar, beat, duration) in enumerate(
                    _timing(i) for i in range(len(progression))
                )
            ]
        )

        for slot in loop:
            index = slot.index
            note_str, chord_type, name = progression[index]
            if note_str is None:
                if melody_voiced:
                    # Defensive, and never taken by a shipped flow: a slot with no
                    # melody note arrives only through the comping union
                    # (`headxml._merge_chord_slots`), which runs only when the voice
                    # selection has no soprano. Refusing loudly rather than inventing
                    # a note is the rule the deleted placeholder used to break.
                    diagnostics.warn(
                        f"Warning: slot {index} has no melody note but this voice "
                        f"selection asks the guitar to sing; skipping the slot"
                    )
                    continue
                melody_note = None
            else:
                melody_note = Note(note_str)

            # Where this slot falls in the bar, and therefore what it is for. Read
            # defensively, exactly as wjazzd.arrange_slots guards its own timings: a
            # short list leaves the trailing steps unlocated, and an unlocated step is
            # a principal note rather than a fill. The bar and beat are also stamped
            # onto the step, because a caller that supplied the rhythm wants to read it
            # back off the result rather than have to correlate two lists.
            bar, beat, duration = slot.bar, slot.beat, slot.duration
            weight = _metric_weight(bar, beat, beats_per_bar)
            # _roles_for_slot re-validates the texture, which is harmless: the table was
            # already checked before the loop, so this cannot raise here.
            #
            # Under walking_bass a strong beat is only a target when something new
            # happens on it: a different harmony from the last target's (the off-beat
            # change rule), or the melody actually moving onto it (decision F, which is
            # what lets the second bar of a two-bar chord restate its shell when the
            # player re-articulates the line there and stay thin when they do not).
            harmony_key = normalised_harmony(name)
            # A silent slot moves nothing onto the beat: `melody_moves` is False, and
            # the tracked pitch clears to None so the next onset reads as the melody
            # arriving there - a fresh attack after silence counts as movement, which
            # is what the placeholder's C4 accidentally produced for the slot *after*
            # a rest, minus its false claim about the silent slot itself.
            melody_moves = (
                melody_note is not None
                and (previous_melody_midi is None
                     or melody_note.midi_note() != previous_melody_midi)
            )
            role = _roles_for_slot(
                weight,
                texture,
                harmony_changed=(last_target_harmony is None
                                 or harmony_key != last_target_harmony),
                melody_moves=melody_moves,
                has_thumb=has_thumb,
                melody_only=melody_only,
            )[0]
            if role == ROLE_TARGET:
                last_target_harmony = harmony_key
            previous_melody_midi = (
                melody_note.midi_note() if melody_note is not None else None
            )
            # The texture decides which grips are *available* on this step. It is not a
            # term in the cost, so a fill cannot be outbid for being in position - the
            # point is that fewer notes are played here, not that this shape is better.
            # The narrowing rule itself, and why the default is not an intersection,
            # are documented once in decisions.resolve_texture_grips.
            #
            # A melody-only selection never asks: the left hand plays nothing on
            # every slot, whatever the texture's palettes say, so the loop hands the
            # empty palette straight through - the same declaration `TEXTURE_GRIPS`
            # makes with an empty tuple, and the one channel `melody_alone_case`
            # reads. Skipping the resolution also skips its warnings, which is what
            # makes `texture=` and `grips=` silently inert here rather than noisily so.
            slot_grips = (
                ()
                if melody_only
                else resolve_texture_grips(
                    role, texture, texture_grips, grips, diagnostics
                )
            )

            # A slot that is played as a single note rather than looked up. Which
            # slots those are, and why each is a branch rather than a missing case,
            # is decisions.melody_alone_case. It returns a *kind*, because the three
            # non-default routes build different steps: an NC bar sets
            # `melody_only=True`, a texture case must not, and an off-grid slot on the
            # comping route is a rest with no notes in it at all.
            #
            # `on_grid` is read from the **slot's own beat**, not from the bar it sits
            # in: the grid is bar-relative, so the same beat number means different
            # positions in different bars of different metres, and `textures.on_grid`
            # is the one place that knows the metre.
            melody_alone = melody_alone_case(
                texture, role, slot_grips, chord_type, name, has_thumb,
                melody_voiced=melody_voiced,
                on_grid=on_grid(beat, grid_pattern, beats_per_bar),
            )
            if melody_alone == MELODY_ALONE_REST:
                # The guitar is silent and the horn has the note. **The step is still
                # emitted**, carrying the bar, the beat and the chord name: it is what
                # keeps the melody's position in the tab staff, and a comping part
                # whose bars collapsed to their stabs would no longer line up against
                # the tune it is comping under.
                #
                # All six strings muted, so every renderer draws it as silence rather
                # than as a held shape - `bass_only` would be the opposite claim (the
                # thumb alone) and `repeated` would claim a melody this part does not
                # play. `melody_only` stays **False**: the step does have a harmony,
                # it simply is not being stated here.
                arrangements.append(ArrangementStep(
                    chord=name,
                    melody=note_str,
                    voicing=Voicing(
                        frets=[-1] * len(STANDARD_TUNING),
                        top_fret=0,
                        avg_fret=0.0,
                        grip="rest",
                    ),
                    bar=bar,
                    beat=beat,
                    duration=duration,
                    role=role,
                    metric_weight=weight,
                    melody_voiced=melody_voiced,
                ))
                # The thumb still walks on a rest. A comping grid thins the **chords**,
                # not the bass line - that is the whole difference between `grid=` and
                # `bass=none`, and dropping the attach here would silently delete the
                # walk from every bar the grid thinned.
                cls._attach_bass(
                    arrangements[-1], slot.bass, arrangements, diagnostics
                )
                continue
            if melody_alone == MELODY_ALONE_TEXTURE:
                # This kind is answered only when the guitar sings, and a singing slot
                # with no note was refused at the top of this loop - so a note is
                # pinned here, which is what lets the type say so below.
                assert melody_note is not None
                solo_voicing = cls.get_melody_only_voicing(
                    melody_note, prefer=top_strings
                )
                if solo_voicing is not None:
                    fill = ArrangementStep(
                        chord=name,
                        melody=note_str,
                        voicing=solo_voicing,
                        partial=False,
                        bar=bar,
                        beat=beat,
                        duration=duration,
                        role=role,
                        metric_weight=weight,
                        bass_only=is_bass_only(slot.bass_only, role),
                    )
                    cls._attach_bass(fill, slot.bass, arrangements, diagnostics)
                    arrangements.append(fill)
                    continue
                # An unreachable melody is genuinely unplayable, so fall through to
                # the harmonised path rather than inventing one.

            # A NO_CHORD step carries melody but no harmony: it is voiced as the
            # melody alone. This happens before any chord logic, so there is no
            # non-chord-tone strategy, no substitute chord and no warning. The
            # `melody_only` flag is set here and *only* here; a texture case above
            # reaches the same route deliberately without it.
            if melody_alone == MELODY_ALONE_NO_CHORD:
                # As the texture branch above: this kind means the guitar sings, and
                # that guard already refused a singing slot with no note.
                assert melody_note is not None
                solo_voicing = cls.get_melody_only_voicing(melody_note, prefer=top_strings)
                if solo_voicing is None:
                    diagnostics.warn(
                        f"Warning: melody {note_str} is unreachable on any string; "
                        f"skipping the no-chord step"
                    )
                    continue
                # get_melody_only_voicing may have dropped the note an octave to stay
                # below HIGH_FRET_LIMIT. Compare the pitch that actually sounds rather
                # than the fret number: an octave-down note lands at a *lower* fret, so
                # only the sounding pitch reveals that the transposition happened.
                sounding_midi = max(solo_voicing.midi_notes())
                written_midi = melody_note.midi_note()
                transposed = (
                    note_str
                    if sounding_midi == written_midi
                    else _note_name(written_midi - 12)
                )
                arrangements.append(ArrangementStep(
                    chord=name,
                    melody=transposed,
                    voicing=solo_voicing,
                    original_melody=(
                        None if transposed == note_str else note_str
                    ),
                    melody_only=True,
                    # `step.grip` is a derived view of `voicing.grip`, so nothing is
                    # passed here: the voicing says "melody" and the step cannot
                    # disagree with it. The property is what keeps the two spellings
                    # one fact with one home - see `docs/one-fact.md`, commit 1.
                    bar=bar,
                    beat=beat,
                    duration=duration,
                    role=role,
                    metric_weight=weight,
                ))
                # An `NC` bar is still a place the thumb walks: the walk reads the last
                # known harmony (or skips), and the melody-alone shape leaves every bass
                # string free. Attaching it here rather than only on harmonised steps is
                # what keeps a bar of no-chord melody from being a hole in the walk.
                arrangements[-1].bass_only = is_bass_only(slot.bass_only, role)
                cls._attach_bass(arrangements[-1], slot.bass, arrangements, diagnostics)
                continue

            # --- The comping route: the guitar harmonises, somebody else sings ---
            #
            # Taken before `prepare_step`, because `prepare_step` is built around a
            # melody to pin: it asks `get_all_grip_voicings` for shapes carrying this
            # note on their topmost string, and every one of them would put the tune
            # back on the guitar. There is nothing to subtract afterwards - the guitar's
            # part was never generated - so the candidates have to come from the
            # melody-free generator in the first place.
            #
            # Deliberately *after* the NC branch above and the melody-alone branch
            # before it, because both are cases where there is no harmony to state:
            # an NC bar has no chord at all, and a melody-only selection's fill has
            # already committed to playing one note. This branch cannot be reached
            # with nothing to play, because it requires no soprano in the selection -
            # and every melody-only selection has one.
            if not melody_voiced:
                # An `NC` bar has no chord, so there is no guide tone to state and
                # nothing at all for the guitar to play under the horn's line. That is
                # a real hole in the part and it is reported as one, in one sentence -
                # rather than reaching `get_comping_voicings`, which correctly refuses a
                # chord with no root, and then falling through to a melody-bearing route
                # that would either warn twice or hand the horn's line back to the
                # guitarist. Skipping is the honest answer: the guitar is silent on this
                # bar, and the horn is not.
                if chord_type == NO_CHORD or name == NO_CHORD:
                    diagnostics.warn(
                        f"Warning: {name} has no chord and this voice selection "
                        f"({', '.join(voices)}) leaves the guitar nothing to comp; "
                        f"skipping the bar"
                    )
                    continue
                candidates = cls.get_comping_voicings(
                    chord_type,
                    chord_name=name,
                    fret_min=fret_min,
                    fret_max=fret_max,
                    # How many notes were asked for. A voice is a *role* in the stack,
                    # so this is the length of the selection and not a count of parts
                    # played twice - `--voices alto,tenor` is two notes, and padding it
                    # to three would put a voice in the part that belongs to the bassist.
                    notes=len(voices),
                    # **Whether this selection is the bass voice and nothing else**,
                    # which arity cannot say: `alto`, `tenor` and `bass` all ask for one
                    # note. Measured before this was passed, all three produced
                    # byte-identical arrangements on strings 1-3 - the middle of the
                    # neck - and the bass voice is the one selection whose register is
                    # part of what it *is*. Derived from the resolved voices rather than
                    # an extra CLI flag, so the two spellings of one request cannot
                    # disagree.
                    bass_voice=voices == (MELODY_BASS,),
                    # Whether this part states both guide tones **and** a root or 5th
                    # under them. The one degree family neither `notes` nor
                    # `bass_voice` can express, and derived from the resolved family
                    # rather than passed as another flag, so the two spellings of one
                    # request cannot disagree.
                    shell_root=harmony_family == HARMONY_SHELL_ROOT,
                )
                if not candidates:
                    if melody_note is None:
                        # The ordinary fallback below voices *the melody*, and this
                        # slot has none to voice - there is no thin shape to fall back
                        # to either, so the chord of the tune cannot be stated here at
                        # all. Reported as the hole it is and skipped; the next grid
                        # position still gets its chance.
                        diagnostics.warn(
                            f"Warning: no guide-tone comping shape found for {name} "
                            f"and no melody note at this position to fall back to; "
                            f"skipping the slot"
                        )
                        continue
                    # No guide-tone shape in a playable position. The chord of the tune
                    # is still owed to the band, so fall through to the ordinary
                    # melody-bearing route rather than dropping the bar - the same
                    # trade `prepare_step` makes when a strategy finds nothing. The
                    # guitar plays the tune here, which is a worse answer than a thin
                    # one and a better one than silence.
                    diagnostics.warn(
                        f"Warning: no guide-tone comping shape found for {name}; "
                        f"falling back to voicing the melody on the guitar"
                    )
                else:
                    # The root, read once for the selector's bass-function tie-break.
                    # `get_comping_voicings` has already refused to generate anything
                    # without a root, so by this point it is never None - the check is
                    # read from the same place the generator read it rather than
                    # re-derived, so the two cannot disagree.
                    _canonical, root_pc, _tones = cls._chord_context(chord_type, name)
                    arrangements.append(ArrangementStep(
                        chord=name,
                        # The written note, which is the horn's line. The guitar does not
                        # sound it - `melody_voiced=False` is what says so.
                        melody=note_str,
                        voicing=select_step_voicing(
                            candidates,
                            arrangements[-1].voicing if arrangements else None,
                            fret_min,
                            fret_max,
                            # The tones the written chord allows. Passed even though the
                            # generator already filters on them: `voicing_cost` counts
                            # wrong notes itself, and a generator that could be wrong
                            # should not be the only thing standing between a chord symbol
                            # and a note that is not in it.
                            ChordParser.get_chord_tones(chord_type, name),
                            # The root, which enables the bass-function tie-break. None
                            # for a chord whose name will not parse, which leaves that
                            # criterion unasked rather than guessing a bass - the same
                            # rule the ordinary route follows.
                            root_pc,
                            # No `melody_pc`: there is no melody on the guitar for the
                            # wrong-note count to excuse, which is what lets a comping
                            # shape be held to the chord's full tone set.
                            None,
                            # The corpus's slash bass, honoured before selection rather
                            # than after, exactly as on the ordinary route.
                            bass_pcs.get(index) if bass_pcs else None,
                            bass_cost_for,
                        ) or candidates[0],
                        # A comping shape is three voices by construction, so `partial`
                        # is always true and is not worth re-deriving per step.
                        partial=True,
                        bar=bar,
                        beat=beat,
                        duration=duration,
                        role=role,
                        metric_weight=weight,
                        bass_only=is_bass_only(slot.bass_only, role),
                        melody_voiced=False,
                    ))
                    cls._attach_bass(
                        arrangements[-1], slot.bass, arrangements, diagnostics
                    )
                    continue

            # Every melody-bearing route below pins a note, and a slot with none has
            # left the loop by now: the guard at the top refuses one the guitar is
            # asked to sing, and the comping block above always steps or continues.
            assert melody_note is not None
            # Everything up to choosing a shape is shared with the corpus loader,
            # which needs the same candidates but honours a slash bass first. See
            # prepare_step.
            prepared = cls.prepare_step(
                progression, index,
                previous=arrangements[-1].voicing if arrangements else None,
                previous_chord=arrangements[-1].chord if arrangements else None,
                top_strings=top_strings,
                non_chord_tone=non_chord_tone,
                fret_min=fret_min,
                fret_max=fret_max,
                grips=slot_grips,
                diagnostics=diagnostics,
            )
            if prepared is None:
                # A target under walking_bass has one grip and no second option, so a
                # melody no shell can sound (D over Bbm7 - the major 3rd over a minor
                # chord, which `NON_CHORD_TONE_EXTENSIONS` has no route for) would be
                # *dropped*, with a warning as the only sign. The melody-alone route a
                # fill takes is the right one here too: the note of the tune survives,
                # the thumb still walks, and the harmony is stated at the next target.
                #
                # A melody-only selection reaches this branch only when the melody
                # cannot be played at all, which `get_melody_only_voicing` answers with
                # None; there is nothing to fall back to and the step is skipped below
                # with the warning. The branch is kept for it anyway so that a future
                # spelling of "the tune and nothing else" inherits the rescue rather
                # than needing this condition widened again.
                if has_thumb or melody_only:
                    solo_voicing = cls.get_melody_only_voicing(
                        melody_note, prefer=top_strings
                    )
                    if solo_voicing is not None:
                        step = ArrangementStep(
                            chord=name,
                            melody=note_str,
                            voicing=solo_voicing,
                            partial=False,
                            bar=bar,
                            beat=beat,
                            duration=duration,
                            role=role,
                            metric_weight=weight,
                            bass_only=is_bass_only(slot.bass_only, role),
                        )
                        cls._attach_bass(step, slot.bass, arrangements, diagnostics)
                        arrangements.append(step)
                        continue
                # A fill slot with nothing thin to play must not lose the chord of
                # the tune - the whole point of the texture is a lighter *texture*,
                # never a missing harmony. So a fill that cannot be filled is
                # re-prepared as a principal note before it is reported as missing.
                # Same argument as NECK_FRET_MIN being a penalty and not a filter.
                if should_promote_fill(
                    texture, role, True, slot_grips, grips,
                    has_thumb=has_thumb,
                    melody_only=melody_only,
                ):
                    prepared = cls.prepare_step(
                        progression, index,
                        previous=arrangements[-1].voicing if arrangements else None,
                        previous_chord=arrangements[-1].chord if arrangements else None,
                        top_strings=top_strings,
                        non_chord_tone=non_chord_tone,
                        fret_min=fret_min,
                        fret_max=fret_max,
                        grips=grips,
                        diagnostics=diagnostics,
                    )
                    if prepared is not None:
                        role = ROLE_TARGET
                if prepared is None:
                    diagnostics.warn(
                        f"Warning: No valid drop-2 voicing found for {name} "
                        f"with melody {note_str}"
                    )
                    continue
            candidates = prepared.candidates
            chord_type = prepared.chord_type
            name = prepared.chord_name
            original_melody = prepared.original_melody
            strategy_used = prepared.strategy
            harmonized_as = prepared.harmonized_as
            is_non_chord_tone = prepared.is_non_chord_tone

            # The whole selection rule lives in voicing_cost. The first chord has no
            # previous shape to lead from, so it falls back to "somewhere comfortable on
            # the neck"; every later chord is scored against the one before it, which is
            # what keeps the hand from jumping and lets a melody hold its place by
            # changing strings.
            prev_voicing = arrangements[-1].voicing if arrangements else None
            # The tones the *written* chord allows, so the selector can prefer a
            # shape that is merely out of position over one that sounds a wrong note.
            # The root enables the bass-function tie-break in voicing_cost; it is None
            # for a chord whose name cannot be parsed, which simply leaves that
            # criterion unasked rather than guessing a bass.
            #
            # The tones are those of the chord **actually sounding**, which is
            # `harmonized_as` where a non-chord-tone strategy substituted one. Scoring
            # the substitute against the written chord asked the wrong question: a
            # Bdim7 voicing under a written Cmaj7 is three foreign notes and every
            # candidate alike, so criterion 0 could not separate them and `missing` then
            # picked a three-note shell over the complete Bdim7 drop-2 that was
            # generated and correct. The step sounded D4-Ab4-D5 - two tones of Bdim7
            # rather than four - under a strategy whose whole purpose is to state the
            # substituted chord.
            #
            # `harmonized_as` is a chord *name* ("Bdim7"), not a quality, so it is
            # parsed rather than passed to `canonical_quality` directly: that returns
            # the whole name unchanged for an unrecognised spelling, and
            # `get_chord_tones` then yields an empty set, which silently switches the
            # criterion off rather than asking it the right question.
            substitute = harmonized_as if harmonized_as is not None else name
            _sub_root, sub_quality = ChordParser.parse_chord_name(substitute)
            if sub_quality is None:
                sub_quality = ChordParser.canonical_quality(chord_type)
                substitute = name
            best_voicing = select_step_voicing(
                candidates,
                prev_voicing,
                fret_min,
                fret_max,
                allowed_tones=ChordParser.get_chord_tones(sub_quality, substitute),
                root_pc=cls._chord_context(chord_type, name)[1],
                # The melody is the caller's note and is never rewritten, so when it
                # lies outside the chord every candidate is impure on it. Excluding it
                # lets a shape that adds no *other* wrong note reach zero - see
                # cost.voicing_cost, where counting rather than flagging makes the
                # difference between one wrong note and four.
                melody_pc=melody_note.midi_note() % 12,
                bass_pc=None if bass_pcs is None else bass_pcs.get(index),
                bass_cost=bass_cost_for,
            )
            # `candidates` is non-empty here (the step is skipped otherwise), so this
            # cannot fire. Written as an assertion rather than left to Optional
            # narrowing at every use below.
            assert best_voicing is not None

            # A complete chord at the very top of the span budget is demoted to
            # the melody alone. Why that is a fallback rather than a re-ranking is
            # documented once in decisions.should_demote_to_melody_alone.
            if should_demote_to_melody_alone(best_voicing, role):
                solo = cls.get_melody_only_voicing(
                    melody_note, prefer=top_strings
                )
                if solo is not None and solo.fret_span() < best_voicing.fret_span():
                    diagnostics.warn(
                        f"Warning: {name} with melody {note_str} needs a "
                        f"{best_voicing.fret_span()}-fret stretch "
                        f"({best_voicing.tab_string()}); playing the melody alone"
                    )
                    arrangements.append(ArrangementStep(
                        chord=name,
                        melody=note_str,
                        voicing=solo,
                        partial=False,
                        bar=bar,
                        beat=beat,
                        duration=duration,
                        role=role,
                        metric_weight=weight,
                        bass_only=is_bass_only(slot.bass_only, role),
                    ))
                    cls._attach_bass(arrangements[-1], slot.bass, arrangements, diagnostics)
                    continue
            # A repeated melody is a soprano-only re-strike, so the renderers hold
            # the inner voices. The rule - and the harmony-change case that is not
            # a hold - is decisions.is_repeated_step.
            repeated = is_repeated_step(
                arrangements[-1] if arrangements else None,
                best_voicing,
                normalised_harmony(name, harmonized_as),
            )

            arrangements.append(ArrangementStep(
                chord=name,
                # The transposed pitch when the step was moved down an octave, so the
                # step reports what actually sounds; original_melody keeps the written one.
                melody=prepared.melody,
                voicing=best_voicing,
                non_chord_tone=is_non_chord_tone,
                strategy=strategy_used,
                harmonized_as=harmonized_as,
                original_melody=original_melody,
                repeated=repeated,
                # A shell or a duo leaves part of the chord unsounded, so the chord name
                # printed above the step describes the harmony rather than every note in
                # it. The renderers annotate this.
                #
                # Counted over the **upper voices**: the thumb is merged after this, so
                # a shell plus a bass note is still a shell and stays annotated
                # "(shell - 3rd & 7th, partial)". The merge happens below, which is what
                # makes that true by ordering rather than by a second count.
                partial=len(best_voicing.active_frets()) < 4,
                bar=bar,
                beat=beat,
                duration=duration,
                role=role,
                metric_weight=weight,
                # Decision B: this slot exists for the thumb. The upper voices are held
                # across it by the renderers rather than re-struck, and the melody is
                # not re-attacked - the opposite of `repeated`, and never set together.
                #
                # `is_bass_only` and not the slot's own flag: the bass grid invented
                # this beat, but a strong beat the melody moves onto is a **target**,
                # and a target states the harmony rather than holding it. Passing the
                # slot's flag straight through marked such a step both bass-only and a
                # target, which silenced the chord this line had just voiced - see
                # `docs/open-issues.md` item 4.
                bass_only=is_bass_only(slot.bass_only, role),
            ))
            # Select first, merge after: the bass is written into the fret vector only
            # once `_best_voicing` has returned, so it cannot enter the cost tuple by
            # construction rather than by discipline.
            cls._attach_bass(arrangements[-1], slot.bass, arrangements, diagnostics)

        return arrangements


    @classmethod
    def _attach_bass(
        cls,
        step: ArrangementStep,
        note: Optional[BassNote],
        arrangements: List[ArrangementStep],
        diagnostics: Optional[Diagnostics] = None,
    ) -> None:
        """
        Merges one walked beat into a step: records it, then places it on a string.

        Deliberately after selection (see the caller). Two independent failures are
        both handled the same way - **the step survives and the bass is reported**:

        - no candidate string survives `_place_bass`'s filters, so there is nowhere to
          put the thumb. Same argument as the neck window being a penalty rather than
          a filter: losing a step is worse than losing its bass.
        - a step that already carries a bass, which cannot happen while the union is
          one walked note per slot, but is checked rather than assumed.

        The previous thumb note is the search's continuity term, so a line does not
        leap octaves between beats purely because a nearer-in-fret candidate happened
        to be two octaves away.
        """
        if note is None:
            return
        step.bass_role = note.role
        if step.bass is not None:
            return
        # A `bass_only` step re-states nothing above the thumb, so the shape the hand is
        # holding is the last **struck** one, not this step's own thinned vector.
        # Measured against the thinned vector the thumb is placed on a string the hand
        # is already fingering and ranked from a fret the hand is not at - the
        # unplayable bar in `docs/open-issues.md` item 1. For any other step the current
        # voicing *is* the shape, so `held` must not narrow it.
        held = (
            _held_shape(arrangements)
            if step.bass_only and not step.melody_only
            else None
        )
        placed = _place_bass(
            step.voicing,
            note.pitch_class,
            previous_bass=_previous_bass(arrangements),
            held=held,
        )
        if placed is None:
            (diagnostics or default_diagnostics()).warn(
                f"Warning: no bass string free below the melody for bass "
                f"{PITCH_CLASS_NAMES[note.pitch_class % 12]}; "
                f"the step keeps its upper voicing"
            )
            return
        midi, string_index, fret = placed
        step.voicing.bass_midi = midi
        step.voicing.bass_string = string_index
        step.voicing.frets[string_index] = fret
        # `bass_pc` is the lowest sounding voice, which the thumb now is by
        # construction: it sounds below every upper voice, or it was not placed.
        step.voicing.bass_pc = midi % 12


    @classmethod
    def _next_resolution_melody(
        cls, progression: Sequence[Tuple[Optional[str], str, str]], index: int
    ) -> Optional[str]:
        """
        The pitch the melody line resolves into: the first following step whose
        melody is a chord tone of its own chord (None when the phrase never
        resolves). Used to spell the dim7 substitution's root.

        A slot with no melody note is stepped over: silence resolves into nothing.
        """
        for note_str, chord_type, name in progression[index + 1:]:
            if note_str is None:
                continue
            if cls.is_chord_tone(Note(note_str), chord_type, name):
                return note_str
        return None
