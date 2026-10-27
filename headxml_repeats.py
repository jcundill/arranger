from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from headxml_model import BarInstruction, BarMarker, Head, HeadChange, HeadNote


def _ending_membership(
    raw_markers: Dict[int, List[BarInstruction]],
    measure_count: int,
) -> Dict[int, set]:
    """Which volta ending each measure position belongs to, by its numbers.

    A bracket runs from its `ending_start` to its `ending_stop` inclusive; an
    unterminated one runs to the last measure, because a writer that leaves a bracket
    open means it to the end rather than to nothing.
    """
    ending_at: Dict[int, set] = {}
    open_ending: Dict[Tuple[int, ...], int] = {}
    for position in sorted(raw_markers):
        for instruction in raw_markers[position]:
            if instruction.kind == "ending_start":
                open_ending[instruction.numbers] = position
            elif instruction.kind == "ending_stop":
                start = open_ending.pop(instruction.numbers, None)
                if start is not None:
                    for covered in range(start, position + 1):
                        ending_at[covered] = set(instruction.numbers)
    for numbers, start in open_ending.items():
        for covered in range(start, measure_count):
            ending_at[covered] = set(numbers)
    return ending_at


def _repeat_start_positions(
    raw_markers: Dict[int, List[BarInstruction]],
) -> List[int]:
    """The positions carrying a forward repeat, in document order - the jump targets."""
    return [
        position
        for position in sorted(raw_markers)
        if any(
            instruction.kind == "repeat_start"
            for instruction in raw_markers[position]
        )
    ]


def _repeat_target(position: int, starts: Sequence[int]) -> int:
    """Where a backward repeat at `position` jumps to: the nearest start before it.

    Zero when the score marks no forward repeat, which is the common case - a lead
    sheet's opening repeat sign is implied by the backward one, and a player reads a
    `|:` at bar 1 whether or not the file writes one.
    """
    earlier = [start for start in starts if start < position]
    return max(earlier) if earlier else 0




def _jump_target(
    instruction: BarInstruction, segno_at: Dict[str, int]
) -> Optional[int]:
    """Where a D.C. or D.S. jumps to: the start, or the segno it names.

    `None` means the score names a Segno it never draws. That is a malformed form
    rather than a jump to an arbitrary bar, so the caller reports it and plays on
    linearly instead of guessing a target.
    """
    if instruction.kind == "da_capo":
        return 0
    return segno_at.get(instruction.name.lower())


def _resolved_jump(
    instruction: BarInstruction,
    target: int,
    position: int,
    fine_at: set,
    to_coda_at: Dict[int, str],
) -> str:
    """Which of the six jump forms a D.C. / D.S. is, from the bar it returns over.

    The words a score prints - "al Fine", "al Coda" - are not separate instructions:
    they say what lies on the **return path**, between the jump's target and the
    instruction itself. When both a Fine and a To Coda are on it, the **earlier** one
    is reached first and names the form; a To Coda only wins when it comes first.
    """
    path = range(target, position + 1)
    fine_stop = min((step for step in path if step in fine_at), default=None)
    coda_stop = min((step for step in path if step in to_coda_at), default=None)
    # A bar carrying both is a Fine in playback: the Fine check runs first in the walk.
    al_coda = coda_stop is not None and (
        fine_stop is None or coda_stop < fine_stop
    )
    al_fine = fine_stop is not None and not al_coda
    if instruction.kind == "da_capo":
        if al_coda:
            return "da_capo_al_coda"
        if al_fine:
            return "da_capo_al_fine"
        return "da_capo"
    if al_coda:
        return "da_segno_al_coda"
    if al_fine:
        return "da_segno_al_fine"
    return "da_segno"


@dataclass
class _PlayOrderIndex:
    """The instructions a play order is built from, sorted by the question they answer.

    A value rather than ten locals: `_expand_play_order` reads most of these on every
    step of the walk, and a signature listing them would be a second copy of the table.
    """

    ending_at: Dict[int, set]
    repeat_end: Dict[int, int]
    repeat_starts: List[int]
    fine_at: set
    segno_at: Dict[str, int]
    coda_at: Dict[str, int]
    to_coda_at: Dict[int, str]
    jump_at: Dict[int, BarInstruction]


def _play_order_index(
    raw_markers: Dict[int, List[BarInstruction]], measure_count: int
) -> _PlayOrderIndex:
    """Sort the raw instructions into the questions the play order asks of them."""
    ending_at = _ending_membership(raw_markers, measure_count)
    repeat_end: Dict[int, int] = {}
    fine_at: set = set()
    segno_at: Dict[str, int] = {}
    coda_at: Dict[str, int] = {}
    to_coda_at: Dict[int, str] = {}
    jump_at: Dict[int, BarInstruction] = {}
    for position in sorted(raw_markers):
        for instruction in raw_markers[position]:
            if instruction.kind == "repeat_end":
                repeat_end[position] = instruction.times
            elif instruction.kind == "fine":
                fine_at.add(position)
            elif instruction.kind == "segno":
                segno_at.setdefault(instruction.name.lower(), position)
            elif instruction.kind == "coda":
                coda_at.setdefault(instruction.name.lower(), position)
            elif instruction.kind == "to_coda":
                to_coda_at.setdefault(position, instruction.name)
            elif instruction.kind in ("da_capo", "da_segno"):
                jump_at.setdefault(position, instruction)
    return _PlayOrderIndex(
        ending_at=ending_at,
        repeat_end=repeat_end,
        repeat_starts=_repeat_start_positions(raw_markers),
        fine_at=fine_at,
        segno_at=segno_at,
        coda_at=coda_at,
        to_coda_at=to_coda_at,
        jump_at=jump_at,
    )


def _fine_stops(index: int, jumped: bool, plan: _PlayOrderIndex) -> bool:
    """Whether the bar at `index` ends the head.

    A Fine with **no** jump in the score is the end of the piece. With one, it only
    stops the return: passing it on the way out is what lets the jump be reached at all.
    """
    return index in plan.fine_at and (jumped or not plan.jump_at)


def _coda_target(
    index: int,
    jumped: bool,
    coda_taken: bool,
    plan: _PlayOrderIndex,
    notes: List[str],
) -> Optional[int]:
    """Where a To Coda at `index` diverts to, or None when it does not fire.

    It fires only after the jump, and only once: on the way out it is a sign the player
    passes, and after the detour the same bar is not reached again. A To Coda naming a
    Coda the score does not draw is reported rather than guessed at.
    """
    if not jumped or coda_taken or index not in plan.to_coda_at:
        return None
    coda = plan.coda_at.get(plan.to_coda_at[index].lower())
    if coda is None:
        notes.append(
            f"the 'To Coda' at measure {index + 1} names a Coda this score does not have"
        )
    return coda


def _jump_at(
    index: int, jumped: bool, plan: _PlayOrderIndex, notes: List[str]
) -> Optional[Tuple[int, str]]:
    """The `(target, resolved kind)` of a D.C. / D.S. at `index`, or None.

    None covers both "there is no jump here" and "the jump names a Segno the score does
    not have" - the second is reported and the head plays on linearly, which is the only
    honest reading of a malformed form.
    """
    if jumped:
        return None
    instruction = plan.jump_at.get(index)
    if instruction is None:
        return None
    target = _jump_target(instruction, plan.segno_at)
    if target is None:
        notes.append(
            f"the D.S. at measure {index + 1} names a Segno this score does not have"
        )
        return None
    return target, _resolved_jump(
        instruction, target, index, plan.fine_at, plan.to_coda_at
    )


def _expand_play_order(
    measure_count: int,
    raw_markers: Dict[int, List[BarInstruction]],
) -> Tuple[List[Tuple[int, int]], Dict[int, str], List[str]]:
    """The measures a performer actually plays, as `(position, pass)` in order.

    Returns the order, the **resolved** kind of each jump that fired, and any report
    lines for a form that could not be honoured. The resolution is returned rather
    than recomputed by the writers: one decision, one source.

    The repeat and volta rules are the ones a lead sheet asks for:

    - a **backward repeat** jumps back to the matching **forward repeat**, or to the
      very start when the score marks no forward repeat. The backward repeat's
      `times` (default 2) is how many times the section is played.
    - a **volta ending** numbered N is played only on pass N, which is exactly the
      "take the 1st ending, repeat, skip it and take the 2nd" a score writes.

    The navigation rules are what makes D.C. / D.S. / Coda / Fine a form rather than
    four decorations, and each is a decision:

    - **A jump fires once.** After it is taken, every later D.C. / D.S. is ignored -
      otherwise the instruction just obeyed would fire again as the return path
      reached it.
    - **A Fine or To Coda is a destination only after the jump.** On the first pass
      they are passed through: a player who stopped at the Fine on the way to the
      D.C. would never reach it. A Fine with **no** jump is the one exception - there
      it is the end of the piece, and ends it.
    - **A To Coda fires once, and only after the jump**, at the bar that carries it;
      the coda section is otherwise unreachable. A To Coda with no jump is inert.
    - **Repeats are not re-taken after a jump.** A D.C. that re-entered a backward
      repeat at bar 1 would reach the same instruction again and jump forever; a
      performer reading "D.C." plays the section straight through.
    - Volta passes reset to 1 on a jump, for the same reason: the return is a fresh
      read of the written page.

    A head with no repeat, ending or jump returns the identity order, so
    `expand_repeats` can leave it byte-identical. The limit guards a malformed score
    against looping forever; it is far above any real expansion, and the report says
    when it was reached rather than truncating in silence.
    """
    notes: List[str] = []
    if not raw_markers:
        return [(position, 1) for position in range(measure_count)], {}, notes

    # The instructions, sorted into the questions this walk asks of them.
    plan = _play_order_index(raw_markers, measure_count)
    has_jump = bool(plan.jump_at)

    order: List[Tuple[int, int]] = []
    jumps: Dict[int, str] = {}
    pass_no = 1
    index = 0
    guard = 0
    limit = 8 * (measure_count + 1) + 64
    jumped = False
    coda_taken = False
    while index < measure_count and guard < limit:
        guard += 1
        # The Fine sounds: it is the end of a phrase, not the bar before one.
        if _fine_stops(index, jumped, plan):
            order.append((index, pass_no))
            break
        numbers = plan.ending_at.get(index)
        # A volta this pass does not take is skipped - but only when a pass is actually
        # in play. On a head with an ending and no repeat the pass never advances past
        # 1, so an ending numbered "2" would otherwise never sound.
        if numbers is not None and pass_no not in numbers:
            index += 1
            continue
        order.append((index, pass_no))
        if (
            not jumped
            and index in plan.repeat_end
            and pass_no < plan.repeat_end[index]
        ):
            pass_no += 1
            index = _repeat_target(index, plan.repeat_starts)
            continue
        coda = _coda_target(index, jumped, coda_taken, plan, notes)
        if coda is not None:
            coda_taken = True
            pass_no = 1
            index = coda
            continue
        jump = _jump_at(index, jumped, plan, notes)
        if jump is not None:
            target, kind = jump
            jumped = True
            jumps[index] = kind
            pass_no = 1
            index = target
            continue
        index += 1

    if guard >= limit and index < measure_count:
        notes.append(
            "the play order was cut short: a repeat or jump never terminated"
        )
    if not has_jump:
        for position in sorted(plan.to_coda_at):
            notes.append(
                f"the 'To Coda' at measure {position + 1} has no D.C. or D.S. "
                "to return from"
            )
    return order, jumps, notes


def expand_repeats(
    head: Head,
    measure_numbers: List[int],
    raw_markers: Dict[int, List[BarInstruction]],
) -> Tuple[str, ...]:
    """Rewrite a head so it plays its repeats, endings and jumps, in place.

    The measures were walked once in document order, each note and `<harmony>` stamped
    with the written measure number. This recomputes the **play order** and renumbers
    `bar` to a unique absolute position, duplicating the notes and chords of a repeated
    section - or a section a D.C. / D.S. returns over - so the arrangement states them
    on every pass a player makes.

    `bar` must be unique because the engine keys everything - `chord_at`, `melody_at`,
    the bass timeline, the renderers' bar grouping - on `(bar, beat)`, and a repeat puts
    two physical bars on the same written number. The written number is kept on
    `HeadNote.written_bar` / `HeadChange.written_bar` so the score's own numbering is
    never lost, and `--bars a-b` filters on the **absolute** (played) bars - so on a
    repeated head `--bars 31-32` is the 1st ending as played, not written bar 31.

    A head with no repeat, ending or jump is left byte-identical, but its markers are
    still recorded: a lone Segno or Coda is a sign the score states and the writers
    draw, even where it moves no bar.

    Returns the report lines for a form that could not be honoured (a D.S. naming no
    Segno, a To Coda naming no Coda, a play order the guard cut short), so the caller
    can put them where the rest of the loader's notes go. Headers that only care about
    the rewrite may ignore the value.
    """
    if not raw_markers or not measure_numbers:
        return ()
    order, jumps, notes = _expand_play_order(len(measure_numbers), raw_markers)
    base = measure_numbers[0]
    # An ending with no repeat, an unreferenced sign: the identity order. Touching the
    # head then would renumber bars for no musical reason, so it is left as read.
    if order == [(position, 1) for position in range(len(measure_numbers))]:
        first_abs = {
            position: base + position for position in range(len(measure_numbers))
        }
        head.markers = _played_markers(raw_markers, measure_numbers, first_abs, jumps)
        return tuple(notes)

    head.notes, head.chords, first_abs = _played_bars(
        head, order, measure_numbers, base
    )

    # A backward repeat jumps back to a target - an explicit forward repeat, or the very
    # start when the score marks none (both committed repeats do). The writers draw a
    # `|:` there, so a target with no `<repeat direction="forward">` of its own still gets
    # a `repeat_start` marker: the opening barline of `synthetic_repeat_slash` carries no
    # repeat sign in the file, yet a player reads one there.
    head.markers = _played_markers(raw_markers, measure_numbers, first_abs, jumps)
    head.measure_range = (base, base + len(order) - 1)
    # The absolute -> written bar map, for the renderers that draw the signs: it is what
    # lets them write the score the file actually contains rather than the played bars.
    head.written_bars = {
        base + index: measure_numbers[position]
        for index, (position, _pass) in enumerate(order)
    }
    return tuple(notes)


def _played_bars(
    head: Head,
    order: List[Tuple[int, int]],
    measure_numbers: List[int],
    base: int,
) -> Tuple[List[HeadNote], List[HeadChange], Dict[int, int]]:
    """Every played pass, renumbered, plus each position's first absolute bar.

    The `position -> absolute bar` map is what the markers are placed by, and it is
    **first** pass deliberately: a repeat sign belongs where the section begins, not
    on every bar it is played in.

    A section played twice contributes its notes twice, which is the point - the
    arrangement states them on every pass a player makes - and is why `bar` has to be
    a unique absolute position rather than the written measure number.
    """
    notes_by_bar: Dict[int, List[HeadNote]] = {}
    for note in head.notes:
        notes_by_bar.setdefault(note.written_bar, []).append(note)
    changes_by_bar: Dict[int, List[HeadChange]] = {}
    for change in head.chords:
        changes_by_bar.setdefault(change.written_bar, []).append(change)

    new_notes: List[HeadNote] = []
    new_changes: List[HeadChange] = []
    first_abs: Dict[int, int] = {}
    for index, (position, _pass) in enumerate(order):
        absolute = base + index
        first_abs.setdefault(position, absolute)
        written = measure_numbers[position]
        for note in notes_by_bar.get(written, ()):
            new_notes.append(replace(note, bar=absolute))
        for change in changes_by_bar.get(written, ()):
            new_changes.append(replace(change, bar=absolute))
    return new_notes, new_changes, first_abs


def _played_markers(
    raw_markers: Dict[int, List[BarInstruction]],
    measure_numbers: List[int],
    first_abs: Dict[int, int],
    jumps: Dict[int, str],
) -> List[BarMarker]:
    """The repeat, ending and navigation signs, on the absolute bars that carry them.

    `jumps` is `_expand_play_order`'s resolved form of each jump that fired, keyed by
    position: `da_capo_al_fine` and the rest. A marker's `kind` is the resolved kind
    where there is one, because the writers need the words a score prints ("D.C. al
    Fine") rather than the primitive the file stated.

    A backward repeat jumps back to a target - an explicit forward repeat, or the very
    start when the score marks none (both committed repeats do). The writers draw a
    `|:` there, so a target with no `<repeat direction="forward">` of its own still gets
    a `repeat_start` marker: the opening barline of `synthetic_repeat_slash` carries no
    repeat sign in the file, yet a player reads one there.

    A marker on a measure the expansion never played (an ending bracket no pass takes)
    has no absolute bar to land on, so it is dropped rather than guessed. A sign stated
    twice on one bar - a forward repeat on both the `<barline>` and the `<sound>` - is
    drawn once.
    """
    repeat_targets: Dict[int, None] = {}
    starts = _repeat_start_positions(raw_markers)
    for position in sorted(raw_markers):
        for instruction in raw_markers[position]:
            if instruction.kind == "repeat_end":
                repeat_targets.setdefault(_repeat_target(position, starts), None)
    marked_starts = set(starts)

    markers: List[BarMarker] = []
    seen: set = set()
    for position in sorted(raw_markers):
        absolute = first_abs.get(position)
        if absolute is None:
            continue
        for instruction in raw_markers[position]:
            kind = jumps.get(position, instruction.kind)
            key = (absolute, kind, instruction.numbers, instruction.name)
            if key in seen:
                continue
            seen.add(key)
            markers.append(
                BarMarker(
                    bar=absolute,
                    kind=kind,
                    written_bar=measure_numbers[position],
                    numbers=instruction.numbers,
                    times=instruction.times,
                    name=instruction.name,
                )
            )
    for position in sorted(repeat_targets):
        if position not in marked_starts and position in first_abs:
            markers.append(
                BarMarker(
                    bar=first_abs[position],
                    kind="repeat_start",
                    written_bar=measure_numbers[position],
                )
            )
            marked_starts.add(position)
    markers.sort(key=lambda m: (m.bar, m.kind))
    return markers

