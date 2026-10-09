"""Diagnostics: where the engine's warnings go.

The engine never prints. A warning is a *value*: a caller passes a `Diagnostics` in
and reads `.warnings` afterwards. That keeps the library's prose out of an embedding
service's log, and lets a test assert that a *condition* was reported rather than that
a *string* appeared on stdout.

    from arranger import Diagnostics, VoiceLeadingEngine

    diagnostics = Diagnostics()
    steps = VoiceLeadingEngine.arrange_progression(prog, diagnostics=diagnostics)
    for message in diagnostics.warnings:
        ...

The `emit` hook is what keeps a caller who passes nothing seeing the same output. A
`Diagnostics` with no `emit` collects silently; `default_diagnostics()` returns one
that prints each message as it happens, and that is what the engine uses when given no
collector. Printing stays the default deliberately: a warning that stops being shown is
a regression a user notices, and a warning that starts being collected is not.

The messages are user-facing prose tuned for a terminal reader, which is why this is a
collector rather than a switch to the `logging` module - reformatting text the demo and
the tests both rely on would buy nothing, and the library has one consumer and no other
logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Diagnostics:
    """Collects the engine's warnings instead of printing them.

    `emit` is called with each message as it is added, *after* it is recorded, so
    a collector and a printer see the same list in the same order. Leave it None
    to collect silently.
    """

    warnings: List[str] = field(default_factory=list)
    emit: Optional[Callable[[str], None]] = None

    def warn(self, message: str) -> None:
        """Records a warning, and passes it to `emit` if one is set."""
        self.warnings.append(message)
        if self.emit is not None:
            self.emit(message)

    def extend(self, messages: List[str]) -> None:
        """Records several warnings at once, in order."""
        for message in messages:
            self.warn(message)

    def __bool__(self) -> bool:
        """True when something was reported. Lets a caller write
        `if diagnostics: print(...)` without reaching for `.warnings`."""
        return bool(self.warnings)


def default_diagnostics() -> Diagnostics:
    """A collector that prints each warning as it happens.

    What `arrange_progression` uses when the caller passes nothing, so that the
    default path is byte-identical to the `print()` calls this replaces.
    """
    return Diagnostics(emit=print)
