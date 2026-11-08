"""Shim: re-exports the top-level `tuning` module through the package path.

`tuning` moved to a top-level module to break the arranger <-> tabstaff import
cycle (the facade resolved `tabstaff`, `tabstaff` imported `arranger.tuning`,
and importing a submodule runs the package `__init__` first). Front ends now
import `tuning` directly, so `tabstaff` no longer touches `arranger` at module
scope and the cycle is gone.

This shim keeps `arranger.tuning` and every `from .tuning import ...` inside the
package working, pointing them at the single source of truth in `tuning.py`.
"""

from __future__ import annotations

from tuning import (  # noqa: F401, F403
    HARMONIC_ARTIFICIAL,
    HARMONIC_NATURAL,
    HARMONIC_PINCH,
    HIGH_FRET_LIMIT,
    LINK_HAMMER,
    LINK_PULL,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    ROLE_FILL,
    ROLE_TARGET,
    SILENCE_GRID,
    SILENCE_NC_COMPING,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    SILENCE_TUNE_SILENT,
    SLIDE_IN_ABOVE,
    SLIDE_IN_BELOW,
    SLIDE_LEGATO,
    SLIDE_OUT_DOWN,
    SLIDE_OUT_UP,
    SLIDE_SHIFT,
    STANDARD_TUNING,
    STRING_NAMES,
    STROKE_DOWN,
    STROKE_UP,
    GuitarFretboard,
    Note,
    Technique,
    note_name,
)

__all__ = [
    "STANDARD_TUNING",
    "STRING_NAMES",
    "PITCH_CLASS_NAMES",
    "NO_CHORD",
    "MELODY_STRING_CHOICES",
    "MELODY_STRING_CHOICES_FULL",
    "NECK_FRET_MIN",
    "NECK_FRET_MAX",
    "HIGH_FRET_LIMIT",
    "GuitarFretboard",
    "Note",
    "note_name",
    "ROLE_TARGET",
    "ROLE_FILL",
    "SILENCE_GRID",
    "SILENCE_NC_COMPING",
    "SILENCE_NO_SHAPE",
    "SILENCE_OUT_OF_REACH",
    "SILENCE_TUNE_SILENT",
    "LINK_HAMMER",
    "LINK_PULL",
    "SLIDE_LEGATO",
    "SLIDE_SHIFT",
    "SLIDE_IN_BELOW",
    "SLIDE_IN_ABOVE",
    "SLIDE_OUT_DOWN",
    "SLIDE_OUT_UP",
    "HARMONIC_NATURAL",
    "HARMONIC_PINCH",
    "HARMONIC_ARTIFICIAL",
    "STROKE_DOWN",
    "STROKE_UP",
    "Technique",
]
