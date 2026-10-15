"""The figures `docs/open-issues.md` states must be the figures the tree produces.

An open issue is filed with its measurement — that document's header says so, and the
measurement is what makes an item an issue rather than a complaint. Nothing enforced it.
`tests/test_docs.py` fails when a stated **version**, a **module count** or a relative
**link** goes stale, but a count inside `open-issues.md` could rot in silence, and did:
once when the `Diagnostics` collector was deleted, once when the loader began playing
repeats, and once when `bass_refused` started counting every refused thumb where the old
warning counted a single call site.

So every figure that document states is re-measured here and compared against what it
says. A number that moves fails the gate naming the document, and the fix is to re-measure
and write the new one down — the same discipline the hardcoded tab strings in the other
test modules enforce for the voicings, and for the same reason: a check that regenerates
its own expectation cannot catch a regression.

Two limits are deliberate. The measurement is *read* from the document and re-taken, so a
figure this file does not know about is not checked — the counts re-measured here are the
ones that moved. And item 2's cause split needs a **replica** of `_place_bass`'s three
filters, because `ArrangementStep.bass_refused` carries the wanted pitch class and not the
reason it could not be placed; the replica is justified where it is written.
"""

from __future__ import annotations

import contextlib
import glob
import io
import re
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import arranger.bass as bass
import arranger.movement as movement
import headxml
from arranger import (
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_LENGTH,
    HARMONY_SHELL_ROOT,
    VoiceLeadingEngine,
)
from arranger.chords import ChordParser
from arranger.fingers import can_fret
from arranger.tuning import STANDARD_TUNING
from tests.support import nearest_reach_for_note

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "open-issues.md"

#: Every committed head, in the order the document lists them.
HEADS: List[str] = (
    sorted(glob.glob(str(ROOT / "tests" / "data" / "*.musicxml")))
    + sorted(glob.glob(str(ROOT / "tests" / "data" / "*.mxl")))
)

#: The rows that place a thumb note under a texture that has one. `targets` and `uniform` are
#: the two textures that carry a thumb line; the walk itself is the bass part's grid row rather
#: than a texture, and the row is inert on the slots either way - the walked-beat union comes from
#: the bass part, so a `bass:walk` row adds nothing here. The two rule sets are the minimal one and
#: the whole chain, unchanged from the set item 2's earlier points were taken on.
THUMB_ROWS: Tuple[Tuple[str, str], ...] = (
    ("targets", "root"),
    ("targets", "root,5th,approach,nearest"),
    ("uniform", "root"),
    ("uniform", "root,5th,approach,nearest"),
)

#: Item 3's progression, spelled as the document says it was measured on, arranged through
#: `parts="chord"` - the comping route, which is the one that reads `harmony=`.
ITEM_THREE_PROGRESSION: List[Tuple[str, str, str]] = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
]


def _union_added() -> Dict[str, int]:
    """Per head, the slots the bar-level union adds.

    A bar the melody never enters contributes no melody slot at all, so every grid position
    in one is the union's — which is why this needs neither a monkeypatch nor a \"before\"
    tree (trap 8): the two methods agreeing is what made the figure trustworthy.
    """
    added: Dict[str, int] = {}
    for path in HEADS:
        head = headxml.load_musicxml(path, None)
        melody_bars = {bar for _t, bar, _b, _d in headxml.head_skeleton(head, None)}
        added[Path(path).name] = len(
            [
                slot
                for slot in headxml.chord_slots(head, None, "chord:every_note")
                if slot[3] not in melody_bars
            ]
        )
    return added


def _cause(upper: Any, pitch_class: int, held: Any) -> str:
    """Which of `_place_bass`'s three filters emptied the palette, as a label.

    **A replica, and that is the honest description of it.** `ArrangementStep.bass_refused`
    records the wanted pitch class and not the reason it could not be placed, so naming the
    cause means running the function's own three tests again: the free-string set, the
    octaves of the wanted pitch below the shape's own lowest note, and the `can_fret`
    four-fret budget — in that order, because the first that comes back empty is the reason.
    It is validated by agreement rather than by inspection: over all 2,624 calls it agrees
    with the real `_place_bass` on every outcome, which is what lets the split count as a
    measurement. Recording the cause on the field would delete this function.
    """
    upper_midis = upper.midi_notes()
    if not upper_midis:
        return "empty upper"
    lowest = min(upper_midis)
    sounding = list(upper.frets)
    hand_base = list(upper.frets)
    if held is not None:
        held_frets, held_thumb = held
        structure = [
            -1 if index == held_thumb else fret
            for index, fret in enumerate(held_frets)
        ]
        structure_midis = [
            STANDARD_TUNING[index].midi_note() + fret
            for index, fret in enumerate(structure)
            if 0 <= index < len(STANDARD_TUNING) and fret >= 0
        ]
        if structure_midis:
            lowest = min(lowest, min(structure_midis))
        sounding = [
            upper.frets[index]
            if upper.frets[index] >= 0
            else (structure[index] if index < len(structure) else -1)
            for index in range(len(upper.frets))
        ]
        hand_base = list(held_frets)
    free = [
        index
        for index in bass.BASS_STRING_INDICES
        if not (0 <= index < len(sounding) and sounding[index] >= 0)
    ]
    if not free:
        return "no free string"
    below = []
    for string_index in free:
        open_midi = STANDARD_TUNING[string_index].midi_note()
        first = (pitch_class - open_midi) % 12
        for fret in range(first, 19, 12):
            if open_midi + fret >= lowest:
                continue
            below.append((string_index, fret))
    if not below:
        return "no octave below"
    for string_index, fret in below:
        hand = list(hand_base)
        hand[string_index] = fret
        if can_fret(hand):
            return "reachable"
    return "fifth fret"


def _refusals() -> List[Tuple[Any, int, Any, str]]:
    """Every refusal over the committed heads and the four thumb rows.

    Each entry is `(upper voicing, wanted pitch class, held shape, chord name)`. The chord is
    captured through `_attach_bass` rather than read off the step afterwards because the
    walk's *pitch* is the only thing the fourth lever is allowed to change, so the chord's
    tones have to be known at the instant of the refusal.
    """
    captured: List[Tuple[Any, int, Any, str]] = []
    context: Dict[str, Any] = {"chord": ""}
    original_attach = movement._attach_bass
    original_place = bass._place_bass

    def attach(step: Any, note: Any, arrangements: Any) -> None:
        context["chord"] = step.chord
        original_attach(step, note, arrangements)

    def place(
        upper: Any, pitch_class: Any, previous_bass: Any = None, held: Any = None
    ) -> Any:
        placed = original_place(upper, pitch_class, previous_bass, held)
        if placed is None:
            captured.append((upper, pitch_class, held, context["chord"]))
        return placed

    # Plain assignment rather than `setattr`: a module attribute is not a classmethod, so the
    # pyright/B010 clash of AGENTS.md trap 4 does not arise here. Both wrappers take `Any`
    # for the same reason — they are seams, not reimplementations.
    movement._attach_bass = attach
    bass._place_bass = place
    movement._place_bass = place
    try:
        for path in HEADS:
            for texture, row in THUMB_ROWS:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    headxml.arrange_xml_head(path, texture=texture, bass=row)
    finally:
        movement._attach_bass = original_attach
        bass._place_bass = original_place
        movement._place_bass = original_place
    return captured


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _walk_reaches() -> Tuple[int, Dict[str, int], List[Tuple[int, int, int]]]:
    """Item 5's figures: the worst reach, the per-head count over 4, and the placement's part.

    The reach is measured the way `test_walking_bass` states it — a `bass_only` step's thumb
    fret against the fret range of the last shape the hand was holding. Each wide step
    contributes `(reach, chosen proximity)`, where the proximity is how near the hand the
    engine put the note; `tests.support.nearest_reach_for_note` is the replica that says
    whether that was as near as the note allowed.
    """
    worst = 0
    over: Dict[str, int] = {}
    forced: List[Tuple[int, int, int]] = []
    for path in HEADS:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            steps, _head, _notes = headxml.arrange_xml_head(
                path,
                texture="targets",
                bass="root,5th,approach,nearest",
                grid="melody:every_note,bass:walk",
            )
        held: Any = None
        count = 0
        for step in steps:
            if step.bass_only and held is not None and step.bass is not None:
                held_frets, held_thumb = held
                thumb = step.voicing.bass_string
                if thumb is not None:
                    thumb_fret = step.voicing.frets[thumb]
                    fingers = [fret for fret in held_frets if fret >= 0]
                    if fingers:
                        low, high = min(fingers), max(fingers)
                        reach = (
                            low - thumb_fret if thumb_fret <= low else thumb_fret - high
                        )
                        worst = max(worst, reach)
                        if reach > 4:
                            count += 1
                            nearest = nearest_reach_for_note(
                                list(held_frets), held_thumb, step.bass
                            )
                            forced.append((
                                reach,
                                abs(thumb_fret - min(fingers)),
                                -1 if nearest is None else nearest,
                            ))
            if not step.bass_only and not step.repeated:
                held = (list(step.voicing.frets), step.voicing.bass_string)
        over[Path(path).stem] = count
    return worst, over, forced


class TestTheStatedNumbersAreTheMeasuredOnes(unittest.TestCase):
    """Item 1's and item 2's figures, re-taken and compared with what the document says."""

    @classmethod
    def setUpClass(cls) -> None:
        # Once: the refusals are a pass over every head across four rows.
        cls.added = _union_added()
        cls.refusals = _refusals()

    def test_item_one_states_the_measured_union_delta(self) -> None:
        """87 steps across six of the eight heads, and every per-head figure named."""
        total = sum(self.added.values())
        contributing = len([count for count in self.added.values() if count])
        self.assertEqual((total, contributing), (87, 6), self.added)
        text = _doc()
        self.assertIn(f"**{total} steps** were added across six of the eight", text)
        for name, count in sorted(self.added.items()):
            if count:
                self.assertIn(f"`{Path(name).stem}` {count}", text)

    def test_item_one_names_the_two_heads_with_no_gap_bar(self) -> None:
        """The zeros are the claim that this is a fix rather than a behaviour change."""
        silent = sorted(Path(name).stem for name, count in self.added.items() if not count)
        self.assertEqual(silent, ["but_not_for_me", "tenor_madness"])
        for stem in silent:
            self.assertIn(stem, _doc())

    def test_item_two_states_the_measured_refusal_count_and_causes(self) -> None:
        """220 refusals on the four thumb rows, split 0 / 220 / 0 down `_place_bass`'s three."""
        counted = Counter(_cause(upper, pc, held) for upper, pc, held, _c in self.refusals)
        split = {
            name: counted.get(name, 0)
            for name in ("no free string", "no octave below", "fifth fret")
        }
        self.assertEqual(len(self.refusals), 220)
        self.assertEqual(
            split, {"no free string": 0, "no octave below": 220, "fifth fret": 0}
        )
        text = _doc()
        self.assertIn(f"refusals number **{len(self.refusals)}** today", text)
        self.assertIn("| no free string | **0** |", text)
        self.assertIn(
            f"| **no octave of the walk's pitch below the shape**"
            f" | **{split['no octave below']}** |",
            text,
        )
        self.assertIn(f"| five frets for four fingers | **{split['fifth fret']}** |", text)

    def test_item_two_states_the_measured_doubling_split(self) -> None:
        """How many refusals wanted the pitch class the shape already sounds underneath."""
        doubling = Counter(
            "doubling" if min(upper.midi_notes()) % 12 == pc else "absent"
            for upper, pc, _held, _c in self.refusals
        )
        self.assertEqual(dict(doubling), {"doubling": 98, "absent": 122})
        self.assertIn(f"{doubling['doubling']} of the {len(self.refusals)} are a", _doc())

    def test_item_two_states_the_measured_walk_pitch_lever(self) -> None:
        """The fourth lever: another pitch under the chosen shape, and whether it is a tone.

        The one lever that costs the cost tuple nothing, so its reach is the whole argument —
        and the shape-level retry is not measurable without the candidate pool, which is why
        the document marks those two figures *not re-measured* instead of restating them.
        """
        by_any = by_tone = by_none = 0
        for upper, _pc, held, chord in self.refusals:
            _root, quality = ChordParser.parse_chord_name(chord)
            tones = (
                set(ChordParser.get_chord_tones(quality or "", chord)) if chord else set()
            )
            placeable = [
                pitch
                for pitch in range(12)
                if bass._place_bass(upper, pitch, None, held) is not None
            ]
            if not placeable:
                by_none += 1
            else:
                by_any += 1
                if any(pitch in tones for pitch in placeable):
                    by_tone += 1
        self.assertEqual((by_any, by_tone, by_none), (144, 105, 76))
        text = _doc()
        self.assertIn(f"reaches **{by_any} of the {len(self.refusals)}**", text)
        self.assertIn(f"only **{by_tone}** of those", text)
        self.assertIn(f"**{by_none} of the {len(self.refusals)}** cannot be", text)

    def test_the_reproducing_tail_states_the_measured_split_too(self) -> None:
        """The 220 is written twice, so the `Reproducing` tail's copy is checked as well.

        It said `0 / 215 / 0` while the item itself and the table said 222, and only the table
        was pinned — so the document contradicted itself in the very place a reader goes to
        re-take the number.
        """
        total = len(self.refusals)
        self.assertEqual(total, 220)
        text = _doc()
        self.assertIn(f"`0 / {total} / 0`", text)
        self.assertNotIn("0 / 215 / 0", text)


class TestItemFiveStatesTheMeasuredReach(unittest.TestCase):
    """Item 5's figures: how far the walk lands from the hand, and whether it had a choice."""

    @classmethod
    def setUpClass(cls) -> None:
        # Once: a pass over every head for the walk row.
        cls.worst, cls.over, cls.forced = _walk_reaches()

    def test_item_five_states_the_measured_worst_and_the_heads(self) -> None:
        """"the worst reach is 7 (`i_was_doing_all_right`)"."""
        self.assertEqual(self.worst, 7)
        text = _doc()
        self.assertIn(f"the worst reach is **{self.worst}**", text)
        holders = sorted(name for name, count in self.over.items() if count)
        self.assertEqual(
            holders,
            [
                "All_the_Things_You_Are",
                "The_Jitterbug_Waltz",
                "but_not_for_me",
                "i_was_doing_all_right",
            ],
        )
        for stem in holders:
            self.assertIn(f"`{stem}`", text)

    def test_item_five_states_how_many_steps_exceed_the_bound(self) -> None:
        """"**6** steps exceed **4** frets", split 1 / 2 / 1 / 2 by head."""
        total = sum(self.over.values())
        self.assertEqual((total, self.over["i_was_doing_all_right"]), (6, 2))
        text = _doc()
        self.assertIn(f"and **{total}** steps exceed **4** frets", text)

    def test_item_five_states_that_every_wide_reach_was_placed_as_near_as_it_could_be(self) -> None:
        """"every one of those six is placed as near the hand as its own note allows"."""
        self.assertEqual(len(self.forced), 6)
        for reach, chosen, nearest in self.forced:
            self.assertEqual(
                nearest,
                chosen,
                f"a reach of {reach} sits {chosen} frets from the hand while its own note "
                f"had a position {nearest} frets away",
            )
        self.assertIn("**every one of those six is placed as near the hand", _doc())


def _generated_but_silent() -> List[Tuple[str, int, float]]:
    """Positions the default grid generates that the arrangement does **not** sound.

    Item 1's remaining half used to be measured as a *remainder* - positions the grid named
    and nothing played. It is closed, so the same pass now measures the complement, and the
    complement must be empty: a position the grid names that is not a written note, and not
    one the tune is still **holding** (§9.2 - the note was harmonised where it began), has to
    be a step. `[]` is the assertion, which is why this returns the offenders rather than a
    count: a count would have to be re-pinned by whoever broke it.

    Read from the tree, like every figure in this file, so it cannot be satisfied by prose.
    """
    missing: List[Tuple[str, int, float]] = []
    for path in HEADS:
        head = headxml.load_musicxml(path, None)
        written = {
            (bar, round(beat, 6))
            for _triple, bar, beat, _dur in headxml.head_skeleton(head, None)
        }
        sounded = {
            (step.bar or 0, round(step.beat or 0.0, 6))
            for step in headxml.arrange_xml_head(path)[0]
        }
        for slot in headxml.chord_slots(head, None, "chord:every_note"):
            bar, beat = slot[3], slot[4]
            key = (bar, round(beat, 6))
            if key in written or key in sounded:
                continue
            if headxml.melody_state(head.notes, bar, beat) != "silent":
                continue
            missing.append((Path(path).stem, bar, beat))
    return missing


class TestTheGeneratedSlotsRemainder(unittest.TestCase):
    """Item 1's default-grid half, **closed**, and the two corrections behind the figures.

    The bullet used to claim that a beat the tune skips inside a bar it occupies was still
    silent under `every_note`, and sized the change at 347 positions named / 192 held / 155
    owed. Two things about that are worth keeping rather than deleting:

    - **it is a diagnosis of the right shape.** The split is §9.2's: a position a note still
      holds must not become a slot, so only the *silent* ones are positions generating
      would add. That is exactly the rule the union now follows, and the closure below
      measures it the same way;
    - **the 347 double-counted.** It was taken over *every* bar, so it included the 87
      positions the earlier bar-level fix already added - the same 87 item 1's landed
      paragraph records. Restricted to the bars its own prose claimed, the split was
      260 / 192 / **68**, which is the size the change actually had.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.head = headxml.load_musicxml(
            str(ROOT / "tests" / "data" / "All_the_Things_You_Are.musicxml"), None
        )
        # Cached by `(grid, melody)`: `arrange_xml_head` reloads the file on every call,
        # and the three arrangements below are what these four assertions read from.
        cls.arranged: Dict[Tuple[str, str], List[Any]] = {}

    def _bar(self, grid: str, parts: str, bar: int) -> List[Any]:
        """One bar of an arrangement, keyed by the grid row and the parts selection.

        `grid` is a row spelling, and `parts` is the selection - `auto` for a head whose
        tune the guitar takes, `chord` for the melody-less route another instrument plays.
        """
        key = (grid, parts)
        if key not in self.arranged:
            steps, _head, _notes = headxml.arrange_xml_head(
                str(ROOT / "tests" / "data" / "All_the_Things_You_Are.musicxml"),
                grid=grid,
                parts=parts,
            )
            self.arranged[key] = steps
        return [s for s in self.arranged[key] if s.bar == bar]

    def test_a_named_grid_already_generates_inside_a_melody_bar(self) -> None:
        """`joe_pass` sounds the beats the tune skips — so the old claim could not stand.

        Bar 3's onsets are exactly 1, 2, 3, 4: every written note sits on the beat, which
        is the case the stale prose said was silent. It yields 8 steps under `joe_pass` on
        both routes, and bar 4's skipped beats 1.5, 2.5 and 3.5 sound too.
        """
        for parts in ("auto", "chord"):
            bar3 = self._bar("chord:joe_pass", parts, 3)
            self.assertEqual(len(bar3), 8, [(s.beat, s.silence) for s in bar3])
        bar4 = self._bar("chord:joe_pass", "auto", 4)
        sounded = {round(s.beat, 2) for s in bar4}
        self.assertEqual(len(bar4), 7)
        for skipped in (1.5, 2.5, 3.5):
            self.assertIn(skipped, sounded)
        # None of them is a written onset, which is the whole of the claim.
        written = {round(n.beat, 2) for n in self.head.notes if n.bar == 4}
        self.assertTrue({1.5, 2.5, 3.5}.isdisjoint(written), written)

    def test_the_default_grid_sounds_a_beat_the_tune_skips_in_a_bar_it_enters(self) -> None:
        """Bar 16 enters on beat 2, so its downbeat was silent — and is now a step.

        This is the closure in one bar of the fixture the rest of this class uses: the tune
        occupies bar 16 (onsets 2, 3 and 4) and skips beat 1, which the old bar-level
        exception excluded along with the rest of the bar and the union now fills.
        """
        self.assertEqual(
            sorted(n.beat for n in self.head.notes if n.bar == 16), [2.0, 3.0, 4.0]
        )
        bar16 = self._bar("chord:every_note", "auto", 16)
        self.assertEqual(sorted(round(s.beat, 2) for s in bar16), [1.0, 2.0, 3.0, 4.0])
        downbeat = next(s for s in bar16 if round(s.beat, 2) == 1.0)
        self.assertIsNone(downbeat.melody, "the tune is silent on beat 1 of bar 16")
        self.assertTrue(downbeat.voicing.active_frets(), downbeat.tab_line())

    def test_a_position_the_tune_is_holding_is_still_not_a_slot(self) -> None:
        """Bar 4's beat 3 is a held `C5`, so it stays absent — §9.2, not the old exception.

        The two refusals are different claims and this is the second one: the tune *does*
        occupy bar 4, and beat 3 is inside the note that began on beat 2. Re-stating a chord
        under it would re-decide a harmony already chosen under that very note.
        """
        bar4 = self._bar("chord:every_note", "auto", 4)
        self.assertEqual(sorted(round(s.beat, 2) for s in bar4), [1.0, 2.0, 4.0])
        self.assertEqual(headxml.melody_state(self.head.notes, 4, 3.0), "held")

    def test_the_document_states_the_closure_and_the_correction(self) -> None:
        """No position is generated-but-unsounded, and the document carries the figures."""
        self.assertEqual(_generated_but_silent(), [])
        text = _doc()
        self.assertIn("**68**", text)
        self.assertIn("**260**", text)
        self.assertIn("**88 steps**", text)

    def test_the_document_states_the_step_counts_it_was_corrected_against(self) -> None:
        """The figures that disprove the old claim are the ones written down."""
        text = _doc()
        self.assertIn("yields\n  7 steps under `joe_pass`", text)
        self.assertIn("yields 8 under the same grid on both routes", text)
        self.assertIn("bar 16", text)


class TestTheReproductionSnippetsRun(unittest.TestCase):
    """Every snippet in the `Reproducing` block runs, and prints what it says it prints.

    The failure this catches is the one that was actually in the file: a snippet that ran
    happily and printed something other than its own comment (`36 of 37` against a head that
    plays 66 bars), and a recipe naming `steps._place_bass`, which is a module that has no
    such function. Neither is visible to a reader and neither failed anything.
    """

    #: Every line the block's own comments claim, in the order the block lists them.
    EXPECTED: Tuple[str, ...] = (
        "bars arranged: 66 of 66",
        "bar 32 (no notes at all): [(1.0, 'Am7'), (2.0, 'D9')]",
        "steps: 16",
        "steps: 0",
        "total added: 87",
        "bar 2 present: False",
        "bars walked: [1, 3]",
        "inert rows: 8 of 8 heads identical",
        # Item 6's split, spelled the way `'%-40s %+d'` prints it, so the padding is the format
        # string's rather than a hand-counted run of spaces that can rot.
        "%-40s %+d" % ("i_was_doing_all_right.mxl", 42),
        "%-40s %+d" % ("heres_that_rainy_day.musicxml", 14),
        "%-40s %+d" % ("tenor_madness.musicxml", 1),
        "added: 57 over 8 heads",
    )

    @classmethod
    def setUpClass(cls) -> None:
        block = re.search(r"```bash\n(.*?)```", _doc(), re.S)
        assert block is not None, "open-issues.md has no fenced bash block"
        cls.snippets = re.findall(r'python -c "(.*?)"\n', block.group(1), re.S)
        cls.outputs = []
        for snippet in cls.snippets:
            completed = subprocess.run(
                [sys.executable, "-c", snippet],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
            cls.outputs.append(completed.stdout)

    def test_the_block_still_holds_every_snippet(self) -> None:
        """One snippet per item that carries a figure — the eighth is item 6's."""
        self.assertEqual(len(self.snippets), 8)

    def test_each_snippet_prints_what_its_comment_claims(self) -> None:
        joined = "\n".join(self.outputs)
        for expected in self.EXPECTED:
            self.assertIn(expected, joined, joined)


class TestTheInertBassGridRow(unittest.TestCase):
    """Item 4: a `bass:` row is accepted, validated, and changes no note.

    The claim is an **equality**, so it is measured as one: the same arrangement under the
    default row and under each of the three `bass:` spellings, compared byte for byte.
    When it starts failing, the row has been wired and the item is ready to be removed.
    """

    def test_every_bass_row_is_the_default_row(self) -> None:
        rows = ("melody:every_note", "bass:every_note", "bass:walk", "bass:anchors")
        for path in HEADS:
            with self.subTest(head=Path(path).name):
                tabs = set()
                for grid in rows:
                    steps, _head, _notes = headxml.arrange_xml_head(
                        path,
                        texture="targets",
                        bass=bass.BASS_STYLE_WALK,
                        grid=grid,
                    )
                    tabs.add(tuple(step.tab_line() for step in steps))
                self.assertEqual(len(tabs), 1, f"{Path(path).name}: a bass row changed a step")

    def test_the_document_states_the_measured_equality(self) -> None:
        """The figure the document states is the one the tree produces."""
        text = _doc()
        self.assertIn(
            "# inert rows: %d of %d heads identical" % (len(HEADS), len(HEADS)), text
        )


class TestTheHarmonyFullNoOp(unittest.TestCase):
    """Item 3: `harmony=full` on the comping route is accepted and answered with guide tones.

    The document's claim is an **equality** — the arrangement with `harmony=full` is
    byte-identical to the one with no `harmony=` at all — so it is measured as one, on the
    progression the document names and through the selection a caller actually types. When
    this starts failing, `full` has been given an implementation on the comping route and the
    item is ready to be removed.
    """

    def _tabs(self, **kwargs: Any) -> Tuple[str, ...]:
        """Every step's tab line, which is how "byte-identical" is spelled here."""
        steps = VoiceLeadingEngine.arrange_progression(ITEM_THREE_PROGRESSION, **kwargs)
        return tuple(step.tab_line() for step in steps)

    def test_full_is_the_default_arrangement_on_the_comping_route(self) -> None:
        """`parts=chord` is the route that reads `harmony=`, and `full` changes nothing on it."""
        default = self._tabs(parts="chord")
        self.assertTrue(default)
        self.assertEqual(self._tabs(parts="chord", harmony=HARMONY_FULL), default)
        # `guide` is what the route ships, so the three spellings are one arrangement.
        self.assertEqual(self._tabs(parts="chord", harmony=HARMONY_GUIDE), default)

    def test_the_document_names_the_table_the_tree_has(self) -> None:
        """The record names `HARMONY_LENGTH`, which lists `guide` and `shell_root`, not `full`.

        Item 3 named a symbol (`HARMONY_BUILT`) that never existed in the tree, and nothing
        caught it because this was the one item with no re-measurement. So the sentence is
        pinned against the table itself: the families it names are compared with the
        vocabulary rather than with the document's own wording.
        """
        self.assertEqual(set(HARMONY_LENGTH), {HARMONY_GUIDE, HARMONY_SHELL_ROOT})
        self.assertNotIn(HARMONY_FULL, HARMONY_LENGTH)
        text = _doc()
        self.assertIn("`HARMONY_LENGTH`", text)
        self.assertNotIn("HARMONY_BUILT", text)


class TestTheReleaseInstantRemainder(unittest.TestCase):
    """Item 6: §9.2's hold rule is inclusive at its edge, so a release is not a position.

    Two different kinds of claim, checked differently. The **boundary** is a structural fact
    about one head and is read directly: `tenor_madness` bar 1 writes two quarter notes, and the
    instant the second ends reports `held` rather than `silent`, which is what §9.2 then
    declines. The **figure** — 57 positions across the eight heads — is measured by the
    document's own recipe, which `TestTheReproductionSnippetsRun` runs as a subprocess, so only
    its anchor is pinned here. That is the same split item 4's tests make between the measured
    equality and the sentence stating it.
    """

    #: `tenor_madness` bar 1: quarters on beats 1 and 2, so beat 3 is the second one's own end.
    BAR = 1
    ONSET = 2.0
    RELEASE = 3.0

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = next(p for p in HEADS if p.endswith("tenor_madness.musicxml"))
        cls.head = headxml.load_musicxml(cls.path, None)

    def test_the_fixture_ends_a_note_exactly_on_the_release_beat(self) -> None:
        """What the item says the bar is, before anything is concluded from it."""
        notes = [(n.beat, round(n.duration * 4, 6)) for n in self.head.notes if n.bar == self.BAR]
        self.assertEqual(notes, [(1.0, 1.0), (self.ONSET, 1.0)])

    def test_a_release_instant_is_reported_as_a_hold(self) -> None:
        """Nothing sounds at the release, and the answer is `held` anyway — the finding."""
        notes = self.head.notes
        self.assertEqual(headxml.melody_state(notes, self.BAR, self.ONSET), "onset")
        self.assertEqual(headxml.melody_state(notes, self.BAR, self.RELEASE), "held")
        self.assertEqual(headxml.melody_state(notes, self.BAR, 4.0), "silent")
        # The mechanism rather than a second opinion: the note is returned *at* its own end,
        # which is the `position > (found.bar, round(end_beat, 6))` test read from outside.
        self.assertIsNotNone(headxml.melody_at(notes, self.BAR, self.RELEASE))

    def test_the_release_beat_is_a_position_the_default_grid_would_name(self) -> None:
        """And it costs the bar a step: 3 sound where an inclusive lattice names 4."""
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            steps, _head, _notes = headxml.arrange_xml_head(self.path)
        # `ArrangementStep.beat` is `Optional` because a step may carry no timing; every step
        # arranged from a head has one, and the filter states that rather than asserting it.
        beats = sorted(
            round(step.beat, 2)
            for step in steps
            if step.bar == self.BAR and step.beat is not None
        )
        self.assertEqual(beats, [1.0, self.ONSET, 4.0])

    def test_the_document_states_the_measured_total(self) -> None:
        """The figure, and the snippet that measures it, both stated where the item is."""
        text = _doc()
        self.assertIn("**57**", text)
        self.assertIn("added: 57 over 8 heads", text)
        self.assertIn("## 6. A position falling on a note's release is not generated", text)

        # The comping route is spelled with the axis that exists: `melody=alto,tenor` was the
        # retired voices spelling, and a document that reproduces its claim with a selection
        # the parser refuses is a claim a reader cannot run.
        self.assertIn("`parts=chord`", text)
        self.assertNotIn("melody=alto,tenor", text)
