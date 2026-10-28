"""Engine API grouping: re-exports the arrangement engine's public surface.

This module is one half of the facade subdivision (the other half is `render`).
It gathers the engine's public names - the types, functions and values a caller
builds arrangements with - so `arranger/__init__.py` can re-export them in one
line instead of thirty.

Every import here is a level-1 relative import from a sibling engine module, so
`engine` sits above its dependencies in the dependency order and the DAG stays
acyclic. `engine` is not itself in the import order of any engine module: nothing
below it imports it back.
"""

from __future__ import annotations

from .bass import bass_line_for
from .bass_place import BassNote, bass_cost
from .bass_rules import bass_allowed, comping_capacity, parse_bass_style, thumb_capacity
from .chords import (
    ChordParser,
    melody_degree_name,
    normalised_harmony,
    sounding_harmony,
)
from .cost import SelectionCriteria, VoicingScore
from .grid import (
    BarRhythm,
    Rhythm,
    beat_offset,
    felt_beat,
    grid_resolutions,
    parse_rhythm,
    rhythm_beats,
)
from .grip_tables import supported_string_sets
from .grips import CompingRequest, get_comping_voicings, get_comping_voicings_for
from .grouping import (
    ParsedGrouping,
    TimeSignature,
    default_grouping,
    format_grouping,
    group_starts,
    grouping_allowed,
    parse_grouping,
    resolve_grouping,
)
from .options import (
    ArrangeOptions,
    Request,
    ResolvedRequest,
    format_request,
    resolve_request,
)
from .parts import (
    parts_has_melody_only,
    parts_have_bass,
    parts_have_chord,
    parts_have_melody,
)
from .slots import arrange_slots, parse_bar_range, unresolved_steps
from .step_types import ArrangementStep, Voicing
from .steps import StepPreparation, VoiceLeadingEngine
from .texture import comping_arity, derived_arity, texture_arity, texture_palette
from .tuning import GuitarFretboard

__all__ = [
    "ArrangeOptions",
    "ArrangementStep",
    "BarRhythm",
    "BassNote",
    "ChordParser",
    "CompingRequest",
    "GuitarFretboard",
    "ParsedGrouping",
    "Request",
    "ResolvedRequest",
    "Rhythm",
    "SelectionCriteria",
    "StepPreparation",
    "TimeSignature",
    "VoiceLeadingEngine",
    "Voicing",
    "VoicingScore",
    "arrange_slots",
    "bass_allowed",
    "bass_cost",
    "bass_line_for",
    "beat_offset",
    "comping_arity",
    "comping_capacity",
    "default_grouping",
    "derived_arity",
    "felt_beat",
    "format_grouping",
    "format_request",
    "get_comping_voicings",
    "get_comping_voicings_for",
    "grid_resolutions",
    "group_starts",
    "grouping_allowed",
    "melody_degree_name",
    "normalised_harmony",
    "parse_bass_style",
    "parse_bar_range",
    "parse_grouping",
    "parse_rhythm",
    "parts_has_melody_only",
    "parts_have_bass",
    "parts_have_chord",
    "parts_have_melody",
    "resolve_grouping",
    "resolve_request",
    "rhythm_beats",
    "sounding_harmony",
    "supported_string_sets",
    "texture_arity",
    "texture_palette",
    "thumb_capacity",
    "unresolved_steps",
]
