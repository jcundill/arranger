"""The engine's published facade: `VoiceLeadingEngine`.

This module is the class the library spells `VoiceLeadingEngine.get_drop2_voicings`
and the test suite's call sites depend on. Every method is a one-line forwarder to
the module that owns the body - `grips`, `cost`, `chords`, `bass_merge`, and, for
the two entry points, `movement` and `step_prepare`.

**The step loop is not here** - it is in `movement`, which imports this module's
collaborators directly and does not import this module. `arrange_progression` below
forwards to it and `prepare_step` to `step_prepare`, so the published spelling is
unchanged and there is one loop rather than two.

`StepPreparation` is re-exported for the same reason: it is the value
`prepare_step` returns, and callers reach it as `arranger.steps.StepPreparation`.
"""

from __future__ import annotations

from typing import Container, List, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass_merge import attach_bass
from .bass_place import (
    BassNote,
)
from .chords import (
    NON_CHORD_TONE_EXTENSIONS,
    NON_CHORD_TONE_STRATEGIES,
)
from .grip_tables import (
    GRIP_PREFERENCE,
)
from .grips import (
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
)
from .grouping import COMMON_TIME, TimeSignature
from .movement import (
    arrange_progression,
)
from .options import DEFAULT_REQUEST, ArrangeOptions, Request
from .step_prepare import (
    StepPreparation,
    prepare_step,
)
from .step_types import ArrangementStep, Voicing
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
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

    # Tables, re-exported as class attributes. The package's own modules and the
    # tests read these off the class as well as from the module that owns them;
    # they are the same objects, not copies, so a caller editing one edits the one
    # the engine reads.
    NON_CHORD_TONE_EXTENSIONS = NON_CHORD_TONE_EXTENSIONS
    NON_CHORD_TONE_STRATEGIES = NON_CHORD_TONE_STRATEGIES

    # --- delegates: each forwards to the module that owns the body ---

    @staticmethod
    def get_comping_voicings(
        chord_name: Optional[str] = None,
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        notes: int = 3,
        bass_voice: bool = False,
    ) -> List[Voicing]:
        """See `grips.get_comping_voicings`."""
        return _grips.get_comping_voicings(
            chord_name=chord_name,
            fret_min=fret_min,
            fret_max=fret_max,
            notes=notes,
            bass_voice=bass_voice,
        )

    @classmethod
    def get_grip_voicings(
        cls,
        melody_note: Note,
        chord_name: str,
        top_string: int = 5,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """See `grips.get_grip_voicings` - the full docstring is there."""
        return _grips.get_grip_voicings(
            melody_note,
            chord_name=chord_name,
            top_string=top_string,
            grips=grips,
        )

    @classmethod
    def get_drop2_voicings(
        cls,
        melody_note: Note,
        chord_name: str,
        top_string: int = 5,
    ) -> List[Voicing]:
        """See `grips.get_drop2_voicings`."""
        return _grips.get_drop2_voicings(
            melody_note, chord_name=chord_name, top_string=top_string
        )

    @classmethod
    def get_interval_voicings(
        cls,
        melody_note: Note,
        chord_name: str,
        top_string: int = 5,
    ) -> List[Voicing]:
        """See `grips.get_interval_voicings`."""
        return _grips.get_interval_voicings(
            melody_note, chord_name=chord_name, top_string=top_string
        )

    @classmethod
    def get_octave_down_candidates(
        cls,
        melody_note: Note,
        chord_name: str,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """See `grips.get_octave_down_candidates`."""
        return _grips.get_octave_down_candidates(
            melody_note,
            chord_name=chord_name,
            top_strings=top_strings,
            grips=grips,
        )

    @classmethod
    def get_all_grip_voicings(
        cls,
        melody_note: Note,
        chord_name: str,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> List[Voicing]:
        """See `grips.get_all_grip_voicings`."""
        return _grips.get_all_grip_voicings(
            melody_note,
            chord_name=chord_name,
            top_strings=top_strings,
            grips=grips,
        )

    @classmethod
    def get_all_drop2_voicings(
        cls,
        melody_note: Note,
        chord_name: str,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
    ) -> List[Voicing]:
        """See `grips.get_all_drop2_voicings`."""
        return _grips.get_all_drop2_voicings(
            melody_note, chord_name=chord_name, top_strings=top_strings
        )

    @classmethod
    def get_melody_only_voicings(
        cls,
        melody_note: Note,
        prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
    ) -> List[Voicing]:
        """See `grips.get_melody_only_voicings`."""
        return _grips.get_melody_only_voicings(melody_note, prefer)

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
        cls, melody_note: Note, chord_name: str
    ) -> bool:
        """See `chords.is_chord_tone`."""
        return _chords.is_chord_tone(melody_note, chord_name=chord_name)

    @classmethod
    def resolve_non_chord_tone(
        cls,
        melody_note: Note,
        chord_name: str,
        strategy: str = "extension",
        next_melody: Optional[str] = None,
    ) -> Optional[str]:
        """See `chords.resolve_non_chord_tone`."""
        return _chords.resolve_non_chord_tone(
            melody_note,
            chord_name=chord_name,
            strategy=strategy,
            next_melody=next_melody,
        )

    @classmethod
    def voicing_cost(
        cls,
        voicing: Voicing,
        criteria: _cost.SelectionCriteria,
    ) -> _cost.VoicingScore:
        """See `cost.voicing_cost` - the library's central invariant is there.

        `criteria` is the whole ranking context, so a caller that wants one more input
        passes a `SelectionCriteria` field rather than another keyword; for "rank
        against nothing" pass `SelectionCriteria()`, which is no previous shape, no
        window override and no chord to check against.
        """
        return _cost.voicing_cost(voicing, criteria)

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
        """See `cost.best_voicing`."""
        return _cost.best_voicing(
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
    def attach_bass(
        cls,
        step: ArrangementStep,
        note: Optional[BassNote],
        arrangements: List[ArrangementStep],
    ) -> None:
        """See `bass_merge.attach_bass` - the full docstring is there."""
        return attach_bass(step, note, arrangements)

    @classmethod
    def prepare_step(
        cls,
        progression: Sequence[Tuple[Optional[str], str]],
        index: int,
        previous: Optional[Voicing] = None,
        previous_chord: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> Optional[StepPreparation]:
        """See `step_prepare.prepare_step` - the full docstring is there."""
        return prepare_step(
            progression,
            index,
            previous,
            previous_chord,
            top_strings,
            non_chord_tone,
            fret_min,
            fret_max,
            grips,
        )

    @classmethod
    def arrange_progression(
        cls,
        progression: Sequence[Tuple[Optional[str], str]],
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        # `Sequence` and Optional *bar* and *beat*, not `List[Tuple[int, float, ...]]`:
        # a slot a caller could not place is `(None, None, None)`, so an entry point may
        # hold either shape. See `movement.arrange_progression` for the same note.
        timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
        request: Request = DEFAULT_REQUEST,
        # The metre as one value: count, denominator and felt grouping, validated
        # together. Omitting it means `COMMON_TIME` (4/4). See
        # `movement.arrange_progression`.
        time_signature: TimeSignature = COMMON_TIME,
        # The progression indexes whose melody note articulates, for the §9.2
        # reharmonise rule on the comping route (§9.3 step C). `None` means every slot
        # is an onset - the correct answer for a hand-built progression with no
        # timeline, and what keeps a bare `arrange_progression(..., options=...)`
        # honouring `--non-chord-tone`. See `ArrangeOptions.melody_onsets`.
        melody_onsets: Optional[Container[int]] = None,
        # The knobs that are not a question about the music; the axes themselves are
        # derived from the request. See `resolution.resolve_knobs`.
        options: Optional[ArrangeOptions] = None,
    ) -> List[ArrangementStep]:
        """See `movement.arrange_progression` - the full docstring is there."""
        return arrange_progression(
            progression,
            top_strings=top_strings,
            non_chord_tone=non_chord_tone,
            fret_min=fret_min,
            fret_max=fret_max,
            timings=timings,
            request=request,
            time_signature=time_signature,
            melody_onsets=melody_onsets,
            options=options,
        )
