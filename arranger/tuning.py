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
    HIGH_FRET_LIMIT,
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
    STANDARD_TUNING,
    STRING_NAMES,
    GuitarFretboard,
    Note,
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
]
