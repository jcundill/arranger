"""Diagnostics: where the engine's warnings go.

The engine used to `print()` them. That is the wrong default for a library, for
three reasons that all showed up in practice:

* **A test could not read one.** Ten call sites across the suite wrapped an
  assertion in `contextlib.redirect_stdout`, which tests that a *string* appeared
  on stdout rather than that a *condition* was reported - and would pass just as
  happily if the warning were printed by the wrong function.
* **A caller could not silence one.** Embedding the engine in a service meant the
  library's prose appearing in the service's log, with no way to route it.
* **A caller could not collect one.** "What did this arrangement have to say?"
  was unanswerable, because the answer had already gone to stdout.

`Diagnostics` makes the warnings a value. A caller passes one in and reads
`.warnings`; the default keeps printing, so nothing a user sees changes.

    from arranger import Diagnostics, VoiceLeadingEngine

    diagnostics = Diagnostics()
    steps = VoiceLeadingEngine.arrange_progression(prog, diagnostics=diagnostics)
    for message in diagnostics.warnings:
        ...

The `emit` hook is what preserves today's behaviour exactly. A `Diagnostics` with
no `emit` collects silently; `default_diagnostics()` returns one that prints each
message as it happens, which is what a caller who passes nothing gets. Keeping
that on by default rather than silently switching to collection is deliberate: a
warning that stops being shown is a regression a user notices, and a warning that
starts being collected is not.

The messages themselves are unchanged from the `print()` calls this replaces -
they are user-facing prose already tuned for a terminal reader, which is why this
is a collector rather than a switch to the `logging` module. The library has one
consumer and no other logging, and reformatting text that the demo and the tests
both rely on would buy nothing.

A flat module for now. It moves to `arranger/diagnostics.py` when the engine is
split into a package, so that split is a `git mv` rather than a second rewrite.
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
