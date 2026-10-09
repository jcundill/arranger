"""The engine's published facade: `VoiceLeadingEngine`.

This module is the class the library spells `VoiceLeadingEngine.get_drop2_voicings`
and forty test call sites depend on. Every method is a one-line forwarder to the
module that owns the body - `grips`, `cost`, `chords`, and, for the two entry
points, `movement`.

**The step loop is not here** - it is in `movement`, which imports this module's
collaborators directly and does not import this module. The two methods below
forward to it, so the published spelling is unchanged and there is one loop rather
than two.

`StepPreparation` is re-exported for the same reason: it is the value
`prepare_step` returns, and callers reach it as `arranger.steps.StepPreparation`.
"""

from __future__ import annotations

from typing import Container, List, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass import (
    BASS_AUTO,
    BassNote,
)
from .chords import (
    NON_CHORD_TONE_EXTENSIONS,
    NON_CHORD_TONE_STRATEGIES,
)
from .diagnostics import Diagnostics
from .grips import (
    DEGREE_OFFSETS_FROM_ROOT,
    DROP2_INTERVAL_SETS,
    GRIP_PREFERENCE,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
)
from .movement import (
    StepPreparation,
    _attach_bass,
    arrange_progression,
    prepare_step,
)
from .options import ArrangeOptions
from .textures import (
    GRID_EVERY_NOTE,
    HARMONY_AUTO,
    MELODY_AUTO,
)
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    ArrangementStep,
    Voicing,
)

__all__ = [
    "StepPreparation",
    "VoiceLeadingEngine",
]


class VoiceLeadingEngine:
    """Generates and voice-leads jazz guitar voicings dynamically.

    A facade. Every generator, the cost rule, the non-chord-tone helpers and --
    since the loop moved -- the step loop itself live in other modules; the
    methods below forward to them, so the published spelling is unchanged. The
    full docstrings live with the implementations; these say where.

    **Why the delegates are written out rather than bound.**
    `get_grip_voicings = classmethod(get_grip_voicings)` is shorter, and it is what
    a first attempt did - but it is unsatisfiable: ruff's B010 wants `setattr`,
    and `setattr` is invisible to a type checker, so each pass breaks the one
    before it. Real one-line methods satisfy both.
    """

    # Tables, re-exported as class attributes. `grip_chart`, `headxml` and the
    # tests all read these off the class; they are the same objects, not
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

    # --- the two entry points: forwarded to `movement`, which owns the loop ---

    @classmethod
    def _attach_bass(
        cls,
        step: ArrangementStep,
        note: Optional[BassNote],
        arrangements: List[ArrangementStep],
        diagnostics: Optional[Diagnostics] = None,
    ) -> None:
        """See `movement._attach_bass` - the full docstring is there."""
        return _attach_bass(step, note, arrangements, diagnostics)

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
        """See `movement.prepare_step` - the full docstring is there."""
        return prepare_step(
            progression, index, previous, previous_chord, top_strings,
            non_chord_tone, fret_min, fret_max, grips, diagnostics,
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
        # a slot a caller could not place is `(None, None, None)`, so an entry point may
        # hold either shape. See `movement.arrange_progression` for the same note.
        timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
        texture: str = "uniform",
        bass: str = BASS_AUTO,
        melody: str = MELODY_AUTO,
        harmony: str = HARMONY_AUTO,
        grid: str = GRID_EVERY_NOTE,
        beats_per_bar: int = 4,
        # The metre's denominator, read by the walking bass's melody timeline alone: a
        # slot's `duration` is in whole notes and one whole note is `beat_type` beats
        # (`4 / beat_type` quarters to the beat). Defaulted rather than required, so a
        # hand-built progression - which has no notated metre to state - keeps the
        # arithmetic it had.
        beat_type: int = 4,
        # The progression indexes whose melody note articulates, for the §9.2
        # reharmonise rule on the comping route (§9.3 step C). `None` means every slot
        # is an onset - the correct answer for a hand-built progression with no
        # timeline, and what keeps a bare `arrange_progression(..., melody="alto,tenor")`
        # honouring `--non-chord-tone`. See `ArrangeOptions.melody_onsets`.
        melody_onsets: Optional[Container[int]] = None,
        diagnostics: Optional[Diagnostics] = None,
        options: Optional[ArrangeOptions] = None,
    ) -> List[ArrangementStep]:
        """See `movement.arrange_progression` - the full docstring is there."""
        return arrange_progression(
            progression, top_strings, non_chord_tone, fret_min,
            fret_max, grips, timings, texture, bass, melody, harmony,
            grid, beats_per_bar, beat_type, melody_onsets, diagnostics,
            options,
        )
