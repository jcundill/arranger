"""
The metric and textural layer: which slots carry a full chord, which carry a fill.

These tests are deliberately split into "the rules" and "the guarantee". The rules
say what a strong beat and a weak beat should produce. The guarantee
(`TestBackwardCompatibility`) says the feature changes nothing until a caller asks
for it - and it is written before any behaviour changes, so every later step in the
implementation is checked against the output the library produced before any of it
existed.

No test here is `skipUnless`-guarded: this is engine work, with no optional
dependency and no database.
"""
from __future__ import annotations

import contextlib
import io
import unittest
from typing import List, Optional, Tuple

from musthe import Note

import arranger
from arranger import (
    BASS_STRING_INDICES,
    BASS_STYLE_WALK,
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    GRIP_STRING_SETS,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    ROLE_FILL,
    ROLE_TARGET,
    SHELL_DEGREES,
    TEXTURE_ARITY,
    TEXTURE_STYLES,
    ChordParser,
    VoiceLeadingEngine,
    derived_arity,
    supported_string_sets,
    texture_palette,
)
from arranger.bass_rules import (
    BASS_RULES,
    parse_bass_style,
)

# Imported from where they live rather than through the package facade, for the reason
# `test_walking_bass` gives for the private `bass` helpers: these are the rule's own
# spelling, and re-exporting them would enlarge the public surface for one test file's
# benefit.
from arranger.decisions import (
    hold_the_melody_string,
    holds_the_shape,
    is_repeated_step,
    resolve_texture_grips,
)
from arranger.grip_tables import (
    RIGHT_HAND_STRINGS,
    grip_pluck_count,
    thumb_safe_grips,
)
from arranger.grips import (
    _interval_offsets,
)
from arranger.texture import (
    FILL_THINNING,
    THIN_ENTRIES,
    families_up_to_arity,
    families_up_to_with_thin,
    metric_weight,
    roles_for_slot,
)
from tests.support import (
    MAJOR_CADENCE,
    MINOR_CADENCE,
    major_cadence_tabs,
    minor_cadence_tabs,
)

# "the synthetic cut-time head" bars 1-2 in F, as the arranging guide writes them: the C target on
# beat 1, the C-B-C-D run filling the gaps, then the F target of bar 3. Shared by the
# `targets` behaviour tests and the backward-compatibility pin below, so the two cannot
# drift apart.
BUT_NOT_FOR_ME = [
    ("C5", "maj7", "Fmaj7"),
    ("C5", "maj7", "Fmaj7"),
    ("B4", "maj7", "Fmaj7"),
    ("C5", "maj7", "Fmaj7"),
    ("D5", "maj7", "Fmaj7"),
    ("F5", "m7", "Gm7"),
    ("C5", "maj7", "Fmaj7"),
    ("A4", "7", "C7"),
]

# One chord per eighth for a single bar of 4/4, so the eight slots land on beats 1.0,
# 1.5, 2.0 ... 4.5 and exactly two of them - beats 1 and 3 - are strong. Annotated
# because a bare list of `(int, float, None)` triples is not assignable to the
# `List[Tuple[int, float, Optional[float]]]` the signature declares - the tuple is
# invariant, so the `None` has to be spelled as the optional it is.
BUT_NOT_FOR_ME_TIMINGS: List[Tuple[int, float, Optional[float]]] = [
    (0, 1.0 + 0.5 * eighth, None) for eighth in range(8)
]


class TestMetricWeight(unittest.TestCase):
    """How strongly a slot counts, as a function of where it falls in the bar."""

    def test_beat_one_is_the_strongest(self):
        """Beat 1 weighs 2 - it is the downbeat the whole bar is built from."""
        self.assertEqual(metric_weight(0, 1.0), 2)

    def test_beat_three_in_four_four_weighs_one(self):
        """Beat 3 weighs 1: the second half-note pulse of a 4/4 bar."""
        self.assertEqual(metric_weight(0, 3.0), 1)

    def test_the_other_beats_weigh_nothing(self):
        """Beats 2 and 4 are connecting notes, so they weigh 0."""
        self.assertEqual(metric_weight(0, 2.0), 0)
        self.assertEqual(metric_weight(0, 4.0), 0)

    def test_no_timing_weighs_minus_one(self):
        """
        A slot with no timing weighs -1, not 0.

        This is the distinction the whole feature rests on: "we were never told
        where this note falls" is not "we were told it is weak". Collapsing the two
        would thin out every hand-written progression.
        """
        self.assertEqual(metric_weight(None, 1.0), -1)
        self.assertEqual(metric_weight(0, None), -1)
        self.assertEqual(metric_weight(None, None), -1)

    def test_a_three_four_bar_still_has_a_second_target(self):
        """
        A 3/4 bar keeps beats 1 and 3.

        A waltz states its harmony on the downbeat and the third beat, so the rule
        has to read the metre it is given rather than assuming 4/4.
        """
        self.assertEqual(metric_weight(0, 1.0, beats_per_bar=3), 2)
        self.assertEqual(metric_weight(0, 3.0, beats_per_bar=3), 1)
        self.assertEqual(metric_weight(0, 2.0, beats_per_bar=3), 0)

    def test_a_two_two_bar_has_no_third_beat(self):
        """
        In 2/2 the beat count is two, so beat 3 does not exist and only the
        downbeat is a target.

        A count without a denominator is not a metre: reading 2/2 as if it had four
        beats would put a target on beat 3 of every bar of a cut-time head.
        """
        self.assertEqual(metric_weight(0, 1.0, beats_per_bar=2), 2)
        self.assertEqual(metric_weight(0, 3.0, beats_per_bar=2), 0)

    def test_a_float_beat_is_not_read_as_a_downbeat(self):
        """
        The eighth of a 2/2 bar (1.5) is not beat 1.

        Without a tolerance an exact comparison would call no real note a downbeat,
        because notated beats are floats.
        """
        self.assertEqual(metric_weight(0, 1.5), 0)
        self.assertEqual(metric_weight(0, 2.5), 0)
        self.assertEqual(metric_weight(0, 1.0 + 5e-7, beats_per_bar=3), 2)
        self.assertEqual(metric_weight(0, 3.0 - 5e-7, beats_per_bar=3), 1)

    def test_the_bar_number_does_not_change_the_weight(self):
        """
        Only the beat within the bar decides, not which bar it is.

        Otherwise a weak note in bar 40 would be treated differently from the same
        beat in bar 1, and the rule would not be a metric rule at all.
        """
        self.assertEqual(metric_weight(0, 1.0), metric_weight(39, 1.0))
        self.assertEqual(metric_weight(-3, 2.0), metric_weight(7, 2.0))


class TestGroupedMetricWeight(unittest.TestCase):
    """`TARGET_BEATS` indexes felt beats, and a grouping is what supplies them."""

    def test_a_twelve_eight_bar_targets_its_first_and_third_pulses(self):
        """12/8 is four groups of three eighths, so the targets are beats 1 and 7."""
        grouping = (3, 3, 3, 3)
        self.assertEqual(metric_weight(0, 1.0, 12, grouping), 2)
        self.assertEqual(metric_weight(0, 7.0, 12, grouping), 1)
        self.assertEqual(metric_weight(0, 4.0, 12, grouping), 0)
        self.assertEqual(metric_weight(0, 10.0, 12, grouping), 0)

    def test_a_nine_eight_bar_targets_its_first_and_last_pulses(self):
        grouping = (3, 3, 3)
        self.assertEqual(metric_weight(0, 1.0, 9, grouping), 2)
        self.assertEqual(metric_weight(0, 7.0, 9, grouping), 1)
        self.assertEqual(metric_weight(0, 4.0, 9, grouping), 0)

    def test_a_six_eight_bar_has_only_two_pulses_so_one_target(self):
        """The same arithmetic that leaves 2/2 with only a downbeat."""
        grouping = (3, 3)
        self.assertEqual(metric_weight(0, 1.0, 6, grouping), 2)
        self.assertEqual(metric_weight(0, 4.0, 6, grouping), 0)

    def test_an_explicit_asymmetric_grouping_is_honoured(self):
        """7/4 as 2+2+3 targets the first and third groups: beats 1 and 5."""
        grouping = (2, 2, 3)
        self.assertEqual(metric_weight(0, 1.0, 7, grouping), 2)
        self.assertEqual(metric_weight(0, 5.0, 7, grouping), 1)
        self.assertEqual(metric_weight(0, 3.0, 7, grouping), 0)

    def test_a_two_group_bar_has_no_third_group(self):
        """5/4 as 3+2 is a two-beat bar, so only its downbeat is a target."""
        grouping = (3, 2)
        self.assertEqual(metric_weight(0, 1.0, 5, grouping), 2)
        self.assertEqual(metric_weight(0, 4.0, 5, grouping), 0)

    def test_no_grouping_keeps_the_shipped_rule(self):
        """Every simple metre is one group per beat, so nothing moved."""
        self.assertEqual(metric_weight(0, 1.0, 4), 2)
        self.assertEqual(metric_weight(0, 3.0, 4), 1)
        self.assertEqual(metric_weight(0, 2.0, 4), 0)


class TestRoles(unittest.TestCase):
    """The mapping from a weight to the roles a slot may take."""

    def test_uniform_makes_every_slot_a_target(self):
        """`uniform` is the historical behaviour, for every weight including 0."""
        for weight in (-1, 0, 1, 2):
            self.assertEqual(roles_for_slot(weight, "uniform"), [ROLE_TARGET])

    def test_targets_gives_a_full_chord_to_a_strong_beat(self):
        """Beats 1 and 3 are targets under the `targets` texture."""
        self.assertEqual(roles_for_slot(2, "targets"), [ROLE_TARGET])
        self.assertEqual(roles_for_slot(1, "targets"), [ROLE_TARGET])

    def test_targets_makes_an_ordinary_beat_a_fill(self):
        """Beat 2 and beat 4 are fills - the guide's 'fill the gaps'."""
        self.assertEqual(roles_for_slot(0, "targets"), [ROLE_FILL])

    def test_a_slot_with_no_timing_is_still_a_target(self):
        """
        With timings=None nothing is known, so every slot is a target.

        This is the single most important line in the feature: it is what makes
        `targets` a no-op on a progression that carries no rhythm.
        """
        self.assertEqual(roles_for_slot(-1, "targets"), [ROLE_TARGET])

    def test_an_unknown_texture_is_rejected(self):
        """A typo must be reported, not silently arranged as `uniform`."""
        with self.assertRaises(ValueError) as caught:
            roles_for_slot(2, "sorcery")
        self.assertIn("sorcery", str(caught.exception))
        self.assertIn("targets", str(caught.exception))

    def test_every_declared_texture_has_an_arity(self):
        """
        TEXTURE_ARITY is a total table: a texture with a missing row would raise
        KeyError deep inside the selector instead of at the call site.

        The row is the **only** thing that decides a palette now. `None` means
        *derived* - the most notes the arithmetic allows at that position - and a
        number is the arity the caller asked for; both are complete answers, so
        what has to hold is that the row exists, not that it is non-`None`.
        """
        self.assertEqual(set(TEXTURE_ARITY), set(TEXTURE_STYLES))
        for texture in TEXTURE_STYLES:
            with self.subTest(texture=texture):
                arity = derived_arity(texture, PART_NAMES)
                self.assertGreaterEqual(arity, 1, "a selection has to state something")
                self.assertLessEqual(arity, 3, "four notes under a tune is five strings")

    def test_no_texture_can_reach_the_melody_alone_palette_by_accident(self):
        """
        No texture, selection or thumb line yields an empty palette.

        An empty palette means "the left hand plays nothing" and routes the step
        through the melody-alone path. The only thing that may reach it is a
        **melody-only selection** (`parts_has_melody_only`), which is handed `()`
        without consulting this table at all - so a texture that harmonises
        something cannot lose its harmony by being absent from a table.

        **This assertion was inverted, not deleted.** It used to name the one
        empty palette a texture *did* carry - `walking_bass`'s fill - and assert
        that it was the only one. `walking_bass` is not a texture any more (it is
        `bass=BASS_STYLE_WALK` over `texture=targets`), and the arity rule leaves
        no row that can be empty: a fill one thinner than a one-note target is the
        `melody` entry rather than nothing. What survives is the rule the test was
        for, and it is now stated over the whole palette table rather than over a
        hand-written subset of it.
        """
        selections = (
            (PART_MELODY,), (PART_BASS,), (PART_CHORD,), PART_NAMES,
            (PART_MELODY, PART_BASS), (PART_CHORD, PART_BASS),
            (PART_MELODY, PART_CHORD),
        )
        empty = [
            (texture, parts, has_thumb, role)
            for texture in TEXTURE_STYLES
            for parts in selections
            for has_thumb in (False, True)
            for role in (ROLE_TARGET, ROLE_FILL)
            if not texture_palette(role, texture, parts, has_thumb)
        ]
        self.assertEqual(
            empty,
            [],
            "a texture gained an empty palette - name the texture that means it, "
            "and the route that has to read it",
        )
        # The thinnest fill is the melody alone, which is a real entry rather than
        # an empty palette - the distinction the emptied row used to blur.
        self.assertEqual(families_up_to_with_thin(0), ("melody",))
        self.assertEqual(THIN_ENTRIES["melody"], 0)
        self.assertEqual(FILL_THINNING, 1)

    def test_the_walking_line_is_a_bass_style_not_a_texture(self):
        """
        A walk is the bass axis' own row, over a texture that names an arity.

        It used to be a texture of its own (`texture="walking_bass"`), which made
        one name cover two claims: which note the thumb states (a *bass* fact) and
        how many notes the chord part states (a *texture* fact). `docs/history/parts.md` §6
        splits them - `bass=BASS_STYLE_WALK` with `texture="targets"` - and the
        arrangement is the same, so what is asserted here is the pair rather than
        the one spelling.
        """
        self.assertEqual(set(parse_bass_style(BASS_STYLE_WALK)), set(BASS_RULES))
        # A walk's targets are the arity a thumb leaves room for, so the chord part
        # states a shell or a duo and nothing wider.
        self.assertEqual(
            texture_palette(ROLE_TARGET, "targets", PART_NAMES, True), ("shell", "duo")
        )
        steps = VoiceLeadingEngine.arrange_progression(
            MINOR_CADENCE,
            texture="targets",
            bass=BASS_STYLE_WALK,
            timings=[(0, 1.0 + 0.5 * i, None) for i in range(len(MINOR_CADENCE))],
        )
        self.assertTrue(steps)
        self.assertTrue(
            any(step.bass is not None for step in steps),
            "the walking line states nothing, so this is not a walk",
        )
        for step in steps:
            if step.role == ROLE_TARGET:
                self.assertLessEqual(
                    grip_pluck_count(step.grip), RIGHT_HAND_STRINGS - 1, step.tab_line()
                )

    def test_a_uniform_texture_offers_the_whole_family_set(self):
        """
        `uniform` must offer every family the hand can play, not an approximation
        of them.

        If it drifted, the default arrangement would change without anyone asking
        for a texture, and the backward-compatibility guarantee would be a fiction.
        The set is compared rather than the order: the palette is read off
        `GRIP_STRING_SETS` (families at *this* arity first), while
        `GRIP_PREFERENCE` is the authored ranking, and the tuple no longer names a
        family - so an order difference is not a behavioural one here. The order
        that *is* load-bearing is the generation order, and that is pinned by
        `TestBackwardCompatibility` and by the exact fingerings in `test_grips.py`:
        a tie shows only in which shape wins.

        Only the **target** row: `uniform` makes every slot a target, so its fill
        row is never read - it exists because the table is total, and it is the
        one-thinner ceiling like any other.
        """
        palette = texture_palette(ROLE_TARGET, "uniform", PART_NAMES)
        self.assertEqual(set(palette), set(GRIP_PREFERENCE))
        # A four-note family is in the default palette, or the whole chord (which is
        # what `uniform` means) is not reachable.
        self.assertTrue(
            any(grip_pluck_count(grip) == RIGHT_HAND_STRINGS for grip in palette)
        )


class TestThePaletteFollowsTheArity(unittest.TestCase):
    """
    The families are the chord part's **search space**, not a caller's choice.

    This class replaces `TestGripsIntersectTheTexture`, whose subject - the
    intersection of a requested grip list with the texture's - no longer exists
    (`docs/history/parts.md` §4 and §6): what a caller chooses is the *arity*, and the
    families that state exactly that many notes under the melody are the ones the
    selector may use. **Inverted rather than deleted**, so the fact that there is
    nothing left to intersect is still asserted, and the two rules that survived
    the change - a target is thicker than a fill, and a target that cannot be
    played falls back to the melody alone - keep their own tests below.
    """

    # the synthetic cut-time head's strong beats, in a form both paths can read.
    PROGRESSION = [("G4", "maj", "Ebmaj")]

    def test_the_palette_is_the_families_the_arity_names(self):
        """
        The derivation, stated as an identity rather than as a list.

        `families_up_to_arity` is a **ceiling**, so the fullest shape a position
        admits is generated first and a position only a shell fits is a shell
        rather than silence; a fill is one arity lower and may also reach the two
        entries that are not grips at all.
        """
        for texture in TEXTURE_STYLES:
            arity = derived_arity(texture, PART_NAMES)
            with self.subTest(texture=texture, role=ROLE_TARGET):
                self.assertEqual(
                    texture_palette(ROLE_TARGET, texture, PART_NAMES),
                    families_up_to_arity(arity),
                )
            with self.subTest(texture=texture, role=ROLE_FILL):
                self.assertEqual(
                    texture_palette(ROLE_FILL, texture, PART_NAMES),
                    families_up_to_with_thin(arity - FILL_THINNING),
                )

    def test_the_three_fixed_arities_are_three_different_palettes(self):
        """
        `chord1`, `chord2` and `chord3` are pinned, because they are the axis.

        A caller who asks for exactly one note under the tune must get exactly one
        family's worth of choice - `duo` states a 3rd or a 7th and nothing else -
        and the ceiling has to widen by one each time rather than jumping to the
        whole set.
        """
        self.assertEqual(texture_palette(ROLE_TARGET, "chord1", PART_NAMES), ("duo",))
        self.assertEqual(
            texture_palette(ROLE_TARGET, "chord2", PART_NAMES), ("shell", "duo")
        )
        self.assertEqual(
            texture_palette(ROLE_TARGET, "chord3", PART_NAMES),
            families_up_to_arity(3),
        )

    def test_only_the_arity_and_the_thumb_change_the_palette(self):
        """
        There is no other input, which is what `grips=` being deleted *means*.

        The four arguments of `texture_palette` are the whole surface - role,
        texture, parts, and whether a thumb is taking a string - so the assertion
        that no third thing narrows a palette is a signature check plus a TypeError
        on the old spelling. Both are cheap and both fail loudly if a request
        channel is ever reintroduced without a decision.
        """
        import inspect

        self.assertEqual(
            list(inspect.signature(texture_palette).parameters),
            ["role", "texture", "parts", "has_thumb"],
        )
        with self.assertRaises(TypeError):
            VoiceLeadingEngine.arrange_progression(
                self.PROGRESSION,
                timings=[(0, 1.0, 1.0)],
                grips=("shell",),  # type: ignore[call-arg]
            )
        self.assertFalse(hasattr(arranger.options.ArrangeOptions, "grips"))

    def test_an_empty_palette_still_arranges(self):
        """
        The empty palette is a declaration, not a palette that fails a budget.

        It means "the left hand plays nothing here", which is how a **melody-only
        selection** arrives at `decisions.melody_alone_case`, and it is the one
        answer that must not be "fixed" by handing the hand a chord nobody offered.
        The thumb budget leaves it alone for the same reason.

        **Inverted rather than deleted.** It used to be the companion of an
        `--grips shell` on a walk's fill, whose palette was empty by design: the
        point was that an empty palette is *not* a caller error while a non-empty
        palette lacking the request was. There is no requested palette any more, so
        what survives is the first half - an empty palette is honoured rather than
        reported - and it is now stated on the route that produces one.
        """
        self.assertEqual(resolve_texture_grips(ROLE_TARGET, (), has_thumb=True), ())
        steps = VoiceLeadingEngine.arrange_progression(
            MINOR_CADENCE, parts=PART_MELODY
        )
        self.assertTrue(steps, "the arrangement must not be lost")
        for step in steps:
            self.assertEqual(step.grip, "melody", step.tab_line())

    def test_a_fill_may_reach_the_entries_that_are_not_grips(self):
        """
        The two thin entries are the fill's, and never a target's.

        `interval` and `melody` are not grip families - they state a texture rather
        than a chord function - so a **target** may not use them: a target states
        the chord part's arity, and neither of these states a chord part. A fill is
        heard *between* two chords and makes no claim about the chord, so both are
        hers. This is the surviving half of the old "no grip is shared between the
        roles" assertion, which the arity rule falsifies for the families themselves
        (a target's palette is a ceiling, so it contains `shell` too).
        """
        self.assertNotIn("interval", GRIP_PREFERENCE)
        self.assertNotIn("melody", GRIP_PREFERENCE)
        for name in THIN_ENTRIES:
            with self.subTest(entry=name):
                self.assertIn(name, texture_palette(ROLE_FILL, "targets", PART_NAMES))
                self.assertNotIn(
                    name, texture_palette(ROLE_TARGET, "targets", PART_NAMES)
                )
        # A target still states a chord, which is what the entries above cannot do.
        self.assertIn(
            "drop3", texture_palette(ROLE_TARGET, "targets", PART_NAMES)
        )

    def test_a_target_that_cannot_be_played_becomes_the_melody_alone(self):
        """
        The fallback, and what it now produces for this melody.

        A `targets` target is offered the four-note ceilings, so for Ebmaj under G4
        the span-0 shell `x-x-8-8-8-x` is not a candidate - and the cost tuple would
        not have chosen it anyway, because `missing` outranks span. The complete
        chords whose only shape is a five-fret stretch fall back to the melody
        alone, which is the rule this asserts.

        The *answer* has moved once already (drop-2's `x-6-5-3-8-x` used to leave
        nothing playable, then drop-3's `3-x-1-3-4-x` did) and it has moved again
        with the palette: `closed` now states this chord inside the hand
        (`x-10-8-8-8-x`, span 2). So what is asserted is the *rule* rather than the
        shape - a `targets` target is always either a complete chord or the melody
        alone, never a partial one, and never a melody with a stale chord name.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION,
            texture="targets",
            timings=[(0, 1.0, 1.0)],
        )
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertIn(step.voicing.grip, ("drop3", "drop2", "closed", "melody"), step.tab_line())
        self.assertEqual(step.chord, "Ebmaj")
        self.assertEqual(max(step.voicing.midi_notes()), Note("G4").midi_note())
        if step.voicing.grip == "melody":
            self.assertEqual(step.voicing.fret_span(), 0)
        else:
            # A complete chord, and every note is a tone of Ebmaj.
            self.assertEqual(len(step.voicing.active_frets()), 4, step.tab_line())
            tones = {t % 12 for t in ChordParser.get_chord_tones("maj", "Ebmaj")}
            self.assertLessEqual(
                {p % 12 for p in step.voicing.midi_notes()}, tones, step.tab_line()
            )

    def test_a_playable_target_is_never_demoted(self):
        """
        The fallback is last, not first: a complete chord is still what you get.

        A low Dm7 gets a span-1 shape and keeps its four voices, so the rule demotes
        only what sits at the very top of the budget.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D4", "m7", "Dm7")], texture="targets", timings=[(0, 1.0, 1.0)]
        )
        self.assertEqual(len(steps), 1)
        self.assertNotEqual(steps[0].voicing.grip, "melody")
        self.assertEqual(len(steps[0].voicing.active_frets()), 4)

    def test_a_target_texture_separates_thick_from_thin(self):
        """
        The `targets` texture states a chord on a strong beat and thins everywhere
        else - which is the whole point, so it is asserted on the palettes.

        Thickness is compared where the roles actually differ: the widest statement
        each may make. A target reaches a four-string family; a fill stops at the
        shell, and may also reach the two entries that are not grips at all. The
        *sets* are not disjoint any more - a target's palette is a **ceiling**, so
        it contains the thinner families too - and the fill's own list is unchanged
        from the hand-written row this rule replaced (`shell`, `interval`, `melody`).
        """
        target = texture_palette(ROLE_TARGET, "targets", PART_NAMES)
        fill = texture_palette(ROLE_FILL, "targets", PART_NAMES)
        self.assertEqual(fill, ("shell", "interval", "melody"))
        self.assertEqual(max(map(grip_pluck_count, target)), RIGHT_HAND_STRINGS)
        self.assertEqual(max(map(grip_pluck_count, fill)), RIGHT_HAND_STRINGS - 1)


class TestTheRightHandBudget(unittest.TestCase):
    """The four digits on the right hand, and what a thumb line costs a target.

    The right hand plucks with thumb, index, middle and ring - `p-i-m-a`, four digits -
    so four strings is the most that can sound at once. That is the same four
    `supported_string_sets()` states, and it states it for a **voicing**: a step is the
    thing the renderers print, and the thumb note is merged into the step *after*
    selection (`VoiceLeadingEngine.attach_bass`), so no check ever saw the two together.
    A four-note target on a strong beat with a bass note placed under it is five
    simultaneous plucks - one more hand than a player has. The counts are in
    [docs/open-issues.md](../docs/open-issues.md) item 2.

    The rule is a **budget** rather than a preference, so it narrows the *target* palette
    only, and only while a thumb line is running.

    A target's palette is the arity ceiling, which is where a four-string family comes
    from: `texture="chord3"` with a thumb states four strings unless the budget is
    applied, because a *fixed* arity is what the caller asked for and the thumb is a
    separate question. `derived_arity` counts the thumb into the ceiling; the fixed rows
    do not, and that is exactly the gap this rule closes.
    """

    def test_every_grip_is_measured_from_its_widest_string_set(self) -> None:
        """One number per grip, pinned as literals because these are what the rule compares.

        A grip that gains a wider string set - or a new four-string grip - has to move one
        of these values before the budget can admit it, which is the signal rather than a
        silent widening.
        """
        counts = {grip: grip_pluck_count(grip) for grip in GRIP_STRING_SETS}
        self.assertEqual(
            {grip for grip, n in counts.items() if n == RIGHT_HAND_STRINGS},
            {"drop2", "drop3", "drop24", "drop2_6432", "closed"},
            "the four-string grips are the four-note families",
        )
        self.assertEqual(counts["shell"], 3)
        self.assertEqual({grip for grip, n in counts.items() if n == 2}, {"duo", "interval"})

    def test_a_palette_entry_that_is_not_a_grip_counts_as_one_string(self) -> None:
        """`melody` is a palette entry a texture names, and the shape it builds is one note."""
        self.assertEqual(grip_pluck_count("melody"), 1)
        self.assertEqual(grip_pluck_count("a-name-no-table-knows"), 1)

    def test_a_target_palette_of_four_note_grips_becomes_the_widest_thumb_safe_one(self) -> None:
        """`("drop2", "drop3")` plus a thumb is five plucks.

        So a target resolves to the widest statement that leaves a finger free - the
        `("shell",)` palette `walking_bass` already names for its own targets.
        """
        self.assertEqual(thumb_safe_grips(("drop2", "drop3")), ("shell",))

    def test_the_premise_that_a_fixed_arity_can_name_a_four_string_target(self) -> None:
        """Without this the narrowing below is load-bearing for nothing.

        The whole defect is a four-note target voiced on a beat the thumb is also playing.
        A **fixed** arity is the caller's own request, so the thumb does not reduce it the
        way `derived_arity`'s ceiling folds the thumb in: `texture="chord3"` still names
        the four-string families, and `resolve_texture_grips` is the only thing between
        that palette and a five-string step. Both halves are asserted - the fixed row
        that needs the rule, and the derived row that is already inside the budget.
        """
        self.assertTrue(
            any(
                grip_pluck_count(grip) == RIGHT_HAND_STRINGS
                for grip in texture_palette(ROLE_TARGET, "chord3", PART_NAMES)
            ),
            "no texture offers a four-string target, so nothing needs narrowing",
        )
        self.assertFalse(
            any(
                grip_pluck_count(grip) == RIGHT_HAND_STRINGS
                for grip in texture_palette(ROLE_TARGET, "targets", PART_NAMES, True)
            ),
            "a derived ceiling already counts the thumb",
        )


    def test_an_empty_palette_comes_back_unchanged(self) -> None:
        """`()` is the table saying "the left hand plays nothing", not a palette to fix.

        Narrowing it would hand the thumb a chord it was never offered. It is the answer
        a melody-only selection is routed with, and the budget must not turn it into a
        statement.
        """
        self.assertEqual(thumb_safe_grips(()), ())

    def test_the_shipped_palettes_that_are_already_thumb_safe_do_not_move(self) -> None:
        """`targets`' targets under a thumb, and `targets`' fills, are inside the budget."""
        self.assertEqual(
            thumb_safe_grips(texture_palette(ROLE_TARGET, "targets", PART_NAMES, True)),
            ("shell", "duo"),
        )
        self.assertEqual(
            thumb_safe_grips(texture_palette(ROLE_FILL, "targets", PART_NAMES)),
            ("shell", "interval", "melody"),
        )

    def test_the_rule_is_inert_without_a_thumb(self) -> None:
        """`has_thumb=False` is the shipped path for every arrangement with no bass line."""
        palette = texture_palette(ROLE_TARGET, "chord3", PART_NAMES)
        for role in (ROLE_TARGET, ROLE_FILL):
            with self.subTest(role=role):
                self.assertEqual(resolve_texture_grips(role, palette), palette)

    def test_a_thumb_narrows_a_target_and_leaves_a_fill_alone(self) -> None:
        """The budget is one palette's, not the slot's: a fill falls between thumb notes."""
        target = resolve_texture_grips(
            ROLE_TARGET,
            texture_palette(ROLE_TARGET, "chord3", PART_NAMES),
            has_thumb=True,
        )
        fill = resolve_texture_grips(
            ROLE_FILL,
            texture_palette(ROLE_FILL, "chord3", PART_NAMES),
            has_thumb=True,
        )
        self.assertEqual(target, ("shell", "duo"))
        self.assertEqual(fill, texture_palette(ROLE_FILL, "chord3", PART_NAMES))

    def test_a_palette_that_spends_all_four_fingers_narrows_to_the_widest_safe_one(
        self,
    ) -> None:
        """A palette of nothing but four-string grips is not an error, and not silence.

        It resolves to the widest statement that leaves a finger free, because a target
        still has to state the harmony. **Inverted rather than deleted**: this used to
        assert the *caller* was refused for asking for such a grip (`--grips drop2`
        under a thumb), which was right while a request could be intersected with the
        budget. There is no request any more - the palette arrives from the arity rule -
        so the surviving half is what the budget does with one.
        """
        self.assertEqual(resolve_texture_grips(ROLE_TARGET, ("drop2",), has_thumb=True), ("shell",))
        self.assertEqual(thumb_safe_grips(("drop2", "closed")), ("shell",))

    def test_a_thumb_carrying_targets_arrangement_never_sounds_five_strings(self) -> None:
        """The engine-level sweep, and the assertion whose absence let this ship."""
        progression = [
            ("F5", "maj7", "Fmaj7"), ("D5", "m7", "Dm7"),
            ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7"),
        ]
        timings = [(bar, 1.0 + 0.5 * n, None) for bar in range(4) for n in range(4)]
        with contextlib.redirect_stdout(io.StringIO()):
            steps = VoiceLeadingEngine.arrange_progression(
                progression, timings=timings, texture="targets", bass="root,5th,approach,nearest"
            )
        checked = 0
        for step in steps:
            sounding = [fret for fret in step.voicing.frets if fret >= 0]
            self.assertLessEqual(len(sounding), RIGHT_HAND_STRINGS, step.tab_line())
            if step.role == ROLE_TARGET and step.voicing.bass_string is not None:
                self.assertLessEqual(
                    grip_pluck_count(step.voicing.grip),
                    RIGHT_HAND_STRINGS - 1,
                    f"{step.tab_line()} spends every finger on the chord",
                )
                checked += 1
        self.assertGreater(checked, 0, "no target carried a bass, so nothing was tested")


class TestTheThumbReach(unittest.TestCase):
    """§2.5's second half: the thumb sweeps the low four strings and no higher.

    The right hand assigns **strings**, not roles - the thumb takes the bottom note of a two-
    or three-note shape whenever that note sits on the E, A, D or G string, with or without a
    bass line under the shape. `bass=` is an arrangement-level fact and never reaches it: the
    merged bass note is written into the fret vector *after* selection. Above the G the thumb
    is out of reach and the fingers take the bottom, which `duo`'s 1-2 pair and the two
    one-note comping shapes are the only reachable sets to ask for. How often it happens is
    measured in `docs/history/fingering.md` §4.4.

    Asserted because of what it *buys*: a string set with nothing below the G can only contain
    the B, the high E, or both - adjacent strings - so the thumb-to-index gap §2.5 exempts
    cannot occur on a shape the thumb cannot reach, and narrowing the exemption to the thumb's
    real reach moves §4.4's finger-skip count by **0**, measured on all five rows.
    """

    # Low E, A, D and G - what a right-hand thumb sweeps. Index 0 is the low E.
    THUMB_STRINGS = frozenset((0, 1, 2, 3))

    def test_only_three_reachable_sets_put_the_bottom_note_above_the_g(self) -> None:
        """Named rather than counted, so a fourth one has to be considered."""
        above_the_g = {
            frozenset(strings)
            for strings in supported_string_sets()
            if min(strings) > max(self.THUMB_STRINGS)
        }
        self.assertEqual(
            above_the_g,
            {frozenset((4,)), frozenset((5,)), frozenset((4, 5))},
            "the B alone, the high E alone, and the 1-2 pair - nothing else is up there",
        )

    def test_the_sets_the_thumb_cannot_reach_are_contiguous(self) -> None:
        """Why the exemption can be narrowed without moving §4.4's count.

        A gap needs a string *between* two sounding ones, and above the G there is no string
        between the B and the high E - so all three sets are already gap-free and the exemption
        was never doing any work for them.
        """
        above = [
            sorted(strings)
            for strings in supported_string_sets()
            if min(strings) > max(self.THUMB_STRINGS)
        ]
        self.assertEqual(len(above), 3, "the sweep below is only as good as its denominator")
        for strings in above:
            self.assertEqual(
                strings,
                list(range(strings[0], strings[0] + len(strings))),
                f"{strings} has a gap above the G string",
            )


class TestBackwardCompatibility(unittest.TestCase):
    """
    The guarantee: without timing, nothing about an arrangement changes.

    This class is the reason the feature is safe to ship. It pins the exact tab of
    the library's own cadences - output produced before any metric awareness
    existed - and it checks every other field a caller might be reading.
    """

    def test_the_demo_cadences_still_produce_the_same_tab(self):
        """
        The published fingerings, fret for fret.

        `x-x-7-9-7-9` became `x-x-9-9-9-9` on the A7. Span is now ranked above neck
        position in `voicing_cost`, and those two shapes are the same chord one fret
        apart in position but two frets apart in span: the old one spans 7-9-7-9, the
        new one is a barre at the ninth. Same notes, a playable position.

        The G7 in the minor cadence moved again, to `x-8-x-7-8-7` - a drop-3 on strings
        5-3-2-1 where it was a drop-2 at `x-x-5-7-6-7`. Both sound G7 (F3 D4 G4 B4 is the
        same 3, 5, b7 and root the drop-2 carried) and both sit under the B4 melody; the
        drop-3 is span 1 against the drop-2's 2, and span outranks position by design.
        `drop3` is in GRIP_PREFERENCE, so it is a candidate, and criterion 0 now counts
        wrong notes instead of flagging them.
        """
        self.assertEqual(
            [s.tab_line() for s in VoiceLeadingEngine.arrange_progression(MINOR_CADENCE)],
            minor_cadence_tabs(),
        )
        self.assertEqual(
            [s.tab_line() for s in VoiceLeadingEngine.arrange_progression(MAJOR_CADENCE)],
            major_cadence_tabs(),
        )
        # Three of the four moved, all for the same reason: `drop3` and `drop24` are in
        # the palette now, so a complete chord can be built on the skipped-bass sets and
        # a tighter shape outranks the old one. The A7 is a drop-3 (G3 E4 A4 Db5) where it
        # was a drop-2 at `x-x-7-9-8-9` - the same A7, span 1 against span 2. The Am7
        # likewise. The Dm(maj7) is unchanged, and staying that way was not automatic:
        # that spelling does not parse, so it has no tone set, and counting wrong notes
        # against an empty set made a two-note duo look *better* than a four-note chord.
        # An unreadable chord now leaves the criterion unasked - see cost.voicing_cost.
        # The A-7 of the other cadence is the exception, and it went the other way: the
        # four-note shape it had was an inner-skip set, and no playable replacement exists
        # at C#5 in that position, so `major_cadence_tabs` records the melody alone there.

    def test_the_targets_texture_pins_its_exact_tab(self):
        """
        The `targets` texture's output, pinned against deliberate review.

        The first three fills are `x-x-7-9-x-8`, `x-x-7-9-x-7` and `x-x-7-9-x-8` -
        the (5,3,2) shell added for the walking-bass work, where before the walk landed
        these on the contiguous 5-4-3 (`x-x-x-9-10-8` and friends). The relocation is
        the intended one: the melody stays on the high E at the same fret, both guide
        tones still sound, the B string is released, and the 5th and 6th strings become
        free for a thumb. That is exactly the three-layer split the walk needs, so the
        pin moved here rather than the set being withdrawn.

        The last two fills moved back onto the contiguous 5-4-3 (`x-x-x-9-10-8` and
        then `x-x-10-9-10-x`) from the non-contiguous 6-4-2 shapes that preceded them. Span
        is now ranked above neck position, and the 6-4-2 versions needed frets 12 and
        13 against 9 and 10 - a five-fret spread for a fill. The 5-4-3 shapes put the
        same notes within two frets, and keep the B string carrying the melody, so the
        three-layer split the walking bass needs still holds.

        The very last fill is `x-x-10-9-10-x` rather than `x-x-x-5-5-5`: span 0 and
        span 1 are bucketed together at the span index of `voicing_cost`, so a
        zero-span barre no longer beats a one-fret shape sitting where the hand
        already is. Both are legal and both are tight - the previous fill is at
        frets 9-10 - so the selector holds the position instead of jumping to fret 5
        for the last chord of the phrase. Span 2 and above still outrank position
        untouched, which is the trade `docs/engine.md` measures.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            BUT_NOT_FOR_ME, timings=BUT_NOT_FOR_ME_TIMINGS, texture="targets"
        )
        self.assertEqual(
            [s.tab_line() for s in steps],
            [
                "x-x-7-9-6-8",
                "x-x-7-9-x-8",
                "x-x-7-9-x-7",
                "x-x-7-9-x-8",
                "x-x-10-12-10-10",
                "x-x-x-12-11-13",
                "x-x-x-9-10-8",
                "x-x-10-9-10-x",
            ],
        )

    def test_the_uniform_texture_on_the_same_fixture_is_unchanged(self):
        """
        The same fixture under `uniform`, pinned alongside the `targets` one.

        A change to the grip tables can reach the default path too - and this time it did -
        so the two textures are pinned on the same bar rather than the default being
        trusted to an older fixture that carries no timing at all.

        Seven of the eight had moved to `drop24` on the skipped-bass set, and the ban has
        put them back: `x-7-7-x-6-8` is `x-x-7-9-6-8` again, the contiguous drop-2. The
        four pitches are still the four Fmaj7 tones (A3 E4 F4 C5 against E3 A3 F4 C5), but
        the bass is the 5th where it was the root, and the span is 2 where it was 1 - so
        this pin records a *trade*, not an improvement, and it is the same trade the
        removed sets were kept for (see `docs/history/fingering.md` §4.4).

        The last step moved the other way, and that one is an improvement: `x-5-5-x-5-5`
        (D3 G3 E4 A4 under A4) became `8-x-8-9-10-x` (C3 Bb3 E4 A4), so C7 now sounds its
        root and its b7 instead of a D and a G. `targets` is untouched: its fills are
        shells and its targets are drop-2, and neither takes a set that was removed.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            BUT_NOT_FOR_ME, timings=BUT_NOT_FOR_ME_TIMINGS, texture="uniform"
        )
        self.assertEqual(
            [s.tab_line() for s in steps],
            [
                "x-x-7-9-6-8",
                "x-x-7-9-6-8",
                "x-x-7-9-6-7",
                "x-x-7-9-6-8",
                "x-x-10-12-10-10",
                "x-x-12-12-11-13",
                "x-x-7-9-6-8",
                "8-x-8-9-10-x",
            ],
        )

    def test_every_step_defaults_to_a_target_with_no_weight(self):
        """No timing means role=target and metric_weight=-1 on every step."""
        for step in VoiceLeadingEngine.arrange_progression(MINOR_CADENCE):
            self.assertEqual(step.role, ROLE_TARGET)
            self.assertEqual(step.metric_weight, -1)

    def test_the_grip_and_partial_flags_are_untouched(self):
        """
        The other bookkeeping a caller reads is unaffected, so an existing caller
        reading `grip` or `partial` sees the same values.
        """
        for step in VoiceLeadingEngine.arrange_progression(MINOR_CADENCE):
            self.assertIn(step.grip, arranger.GRIP_PREFERENCE)
            self.assertEqual(step.partial, len(step.voicing.active_frets()) < 4)
            self.assertFalse(step.repeated)
            self.assertIsNone(step.original_melody)

    def test_supplying_the_default_texture_changes_nothing(self):
        """
        Asking for `uniform` explicitly is the same as not asking at all.

        A caller who passes every new argument must not get different music, or
        "opt-in" would not be true.
        """
        plain = VoiceLeadingEngine.arrange_progression(MINOR_CADENCE)
        explicit = VoiceLeadingEngine.arrange_progression(
            MINOR_CADENCE, timings=None, texture="uniform", beats_per_bar=4
        )
        self.assertEqual(
            [s.tab_line() for s in plain], [s.tab_line() for s in explicit]
        )

    def test_an_unknown_texture_raises_before_any_voicing_work(self):
        """
        The check happens up front, so a typo costs a message rather than a full
        arrangement followed by a surprise.
        """
        with self.assertRaises(ValueError):
            VoiceLeadingEngine.arrange_progression(MINOR_CADENCE, texture="sorcery")


class TestTimingsDefensive(unittest.TestCase):
    """A caller's timing list cannot shift a step onto the wrong role."""

    def test_a_short_timings_list_leaves_the_rest_as_targets(self):
        """
        Fewer timings than steps is not an error.

        The trailing steps were never located, so they are targets - the same
        "we know nothing" rule that governs a progression with no timings at all.
        This is the guard `slots.arrange_slots` already applies to its own timings,
        for the same reason: a hand-built list must not silently shift the rhythm.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            MINOR_CADENCE, timings=[(0, 2.0, None)], texture="targets"
        )
        self.assertEqual(len(steps), len(MINOR_CADENCE))
        self.assertEqual(steps[0].metric_weight, 0)
        self.assertEqual(steps[0].role, ROLE_FILL)
        for step in steps[1:]:
            self.assertEqual(step.metric_weight, -1)
            self.assertEqual(step.role, ROLE_TARGET)

    def test_a_long_timings_list_is_ignored_past_the_progression(self):
        """Extra timings for slots that do not exist are simply never read."""
        steps = VoiceLeadingEngine.arrange_progression(
            MINOR_CADENCE,
            timings=[(bar, 1.0, None) for bar in range(20)],
            texture="targets",
        )
        self.assertEqual(len(steps), len(MINOR_CADENCE))

    def test_timings_do_not_change_the_melody_pitches(self):
        """
        Timing is a texture decision, never a transposition.

        The `HIGH_FRET_LIMIT` octave rescue reads the window, not the metre, so the
        melody that sounds is the same either way.
        """
        plain = VoiceLeadingEngine.arrange_progression(MINOR_CADENCE)
        timed = VoiceLeadingEngine.arrange_progression(
            MINOR_CADENCE,
            timings=[(0, 1.0 + 0.5 * i, None) for i in range(len(MINOR_CADENCE))],
            texture="targets",
        )
        self.assertEqual([s.melody for s in plain], [s.melody for s in timed])


class TestMelodyOnlySelections(unittest.TestCase):
    """`parts=melody` and `parts=melody,bass`: the tune alone, and the tune
    with a thumb under it.

    Both answer "lead sheet in, melody out". They are **part selections** rather
    than grips because what they change is *which parts sound at all* - a grip
    would have to win a cost comparison it should not be in, and
    `GRIP_PREFERENCE` deliberately leaves `melody` out for exactly that reason.
    They were the `melody` and `melody_bass` textures, then the `voices=` axis,
    and they are the `parts=` axis now - see `docs/history/one-fact.md` and
    `docs/history/parts.md`.
    """

    PROGRESSION = BUT_NOT_FOR_ME
    TIMINGS = BUT_NOT_FOR_ME_TIMINGS

    def arrange(self, parts, **kwargs):
        return VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION, timings=self.TIMINGS, parts=parts, **kwargs
        )

    def test_every_slot_is_the_melody_alone(self):
        """Neither selection harmonises anything, on any slot, strong or weak.

        Counted on `upper_midi_notes`, not on `active_frets`: `attach_bass` merges the
        thumb into the voicing *after* the upper voice is chosen, so a
        `melody,bass` step legitimately has two sounding frets. The thing under
        test is that the **left hand** plays one note, and that is what the
        upper voices are.
        """
        for parts in ("melody", "melody,bass"):
            steps = self.arrange(parts)
            self.assertTrue(steps, parts)
            for step in steps:
                self.assertEqual(step.grip, "melody", f"{parts} {step.melody}")
                self.assertEqual(
                    len(step.voicing.upper_midi_notes()),
                    1,
                    f"{parts} {step.melody} harmonised the melody",
                )
                self.assertEqual(
                    max(step.voicing.upper_midi_notes()),
                    Note(step.melody).midi_note(),
                    f"{parts} {step.melody}: the melody is not the top note",
                )
                self.assertFalse(step.melody_only, parts)
                # The harmony still exists; it is simply not spelled out. `melody_only`
                # would make the annotation claim "no chord - melody alone", which is
                # false here - the chord name is printed as context.
                self.assertTrue(step.chord)
                self.assertFalse(
                    step.partial, f"{parts} {step.melody} claims a partial chord"
                )

    def test_the_two_differ_only_in_the_thumb_line(self):
        """`melody` alone has no bass; `melody,bass` walks one under every bar."""
        for parts in ("melody", "melody,bass"):
            steps = self.arrange(parts)
            with_bass = [s for s in steps if s.bass is not None]
            if parts == "melody":
                self.assertEqual(with_bass, [], "melody alone must not carry a thumb")
            else:
                self.assertTrue(
                    with_bass, "melody,bass must carry a thumb line"
                )
                for step in with_bass:
                    self.assertIn(
                        step.voicing.bass_string,
                        BASS_STRING_INDICES,
                        f"thumb on string {step.voicing.bass_string}",
                    )

    def test_soprano_bass_keeps_every_note_of_the_tune(self):
        """The thumb is added underneath; the melody is not thinned to make room.

        A step invented purely for the thumb holds the melody rather than re-striking
        it, which is what `is_bass_only` decides from the role - so a bar of running
        notes must still sound every note it was given.
        """
        played = [s.melody for s in self.arrange("melody,bass") if not s.bass_only]
        self.assertEqual(
            played,
            [t[0] for t in self.PROGRESSION],
            "melody,bass dropped, duplicated or reordered the melody",
        )

    def test_no_texture_can_thicken_a_melody_only_selection(self):
        """A melody-only selection states the tune whatever the *other* axes say.

        The loop hands it an empty chord palette without consulting the texture at
        all - the selection means the left hand plays no chord whatever the arity
        asks for - so no arity can add a voice to a line nobody asked to harmonise.

        **Inverted rather than deleted.** It used to loop over `grips=("duo",)`,
        `("shell",)` and so on, asserting the same thing about the axis that was
        deleted; `texture=` is the axis that survived, and it is the one that can
        change how many notes the chord part states.
        """
        for parts in ("melody", "melody,bass"):
            for texture in TEXTURE_STYLES:
                steps = self.arrange(parts, texture=texture)
                self.assertTrue(steps, f"{parts} {texture} produced nothing")
                for step in steps:
                    self.assertEqual(step.grip, "melody", f"{parts} {texture}")

    def test_a_solo_note_is_a_supported_single_string_set(self):
        """A solo note is a singleton, and the invariant now says so.

        **This assertion was inverted, not deleted.** It previously read
        `assertNotIn(..., supported_string_sets())`, pinning the fact that a one-string
        shape was *outside* the playability invariant. That was true and it was a real
        gap: the invariant claims "the sounding strings are exactly one
        `supported_string_sets()` entry", and a melody-only selection violates it on every
        slot, so the library shipped shapes it had not agreed to be playable.

        `grips.SINGLE_NOTE_STRING_SETS` fixes that rather than excusing it: one note on
        one string has no span to exceed and no second voice to clash with, so it is
        playable anywhere, and `supported_string_sets()` now lists all six singletons.
        The claim this test protects is unchanged - that the solo note is one string, and
        that the library says so in one place - only the direction of it has moved.

        Measured alongside: the same gap existed for the one-note *comping* shape, which
        `SINGLE_NOTE_STRING_SETS` also closes; see `tests/test_comping.py`.
        """
        for step in self.arrange("melody"):
            self.assertEqual(len(step.voicing.active_frets()), 1)
            self.assertIn(
                frozenset(step.voicing.active_strings),
                supported_string_sets(),
                "a solo note must be one of the singleton sets",
            )


class TestTargetsTexture(unittest.TestCase):
    """What a `targets` arrangement actually sounds like, on a real 4/4 bar."""

    # "the synthetic cut-time head" bars 1-2 in F, as the arranging guide writes them: the C
    # target on beat 1, the C-B-C-D run filling the gaps, then the F target of bar 3.
    PROGRESSION = BUT_NOT_FOR_ME
    # One chord per eighth for a single bar of 4/4, so the eight slots land on beats
    # 1.0, 1.5, 2.0 ... 4.5 and exactly two of them - beats 1 and 3 - are strong.
    TIMINGS = BUT_NOT_FOR_ME_TIMINGS

    def setUp(self):
        self.steps = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION, timings=self.TIMINGS, texture="targets"
        )
        self.assertEqual(len(self.steps), len(self.PROGRESSION))

    def test_the_timing_is_read_back_onto_every_step(self):
        """
        The rhythm the caller supplied is stamped onto the result.

        A caller that passed timings wants to read the arrangement, not to have to
        correlate two parallel lists, and `has_timing` becomes true as a side effect.
        """
        for step, (bar, beat, _) in zip(self.steps, self.TIMINGS):
            self.assertEqual(step.metric_weight, metric_weight(bar, beat))
            self.assertEqual(step.bar, bar)
            self.assertEqual(step.beat, beat)
            self.assertTrue(step.has_timing)

    def test_a_strong_beat_gets_a_full_chord(self):
        """Beats 1 and 3 are stated in four voices - the harmony is declared there."""
        strong = [s for s in self.steps if s.metric_weight > 0]
        self.assertEqual(len(strong), 2, "the fixture must have two strong beats")
        for step in strong:
            self.assertEqual(step.role, ROLE_TARGET)
            self.assertEqual(len(step.voicing.active_frets()), 4)
            self.assertEqual(step.grip, "drop2")
            self.assertFalse(step.partial)

    def test_a_weak_beat_is_thinned(self):
        """
        Beats 2 and 4 are filled, not re-struck in four voices.

        This is the change the whole feature exists for: the guide's "fill the gaps
        with single-note runs, 2-note intervals or shell voicings".
        """
        weak = [s for s in self.steps if s.metric_weight == 0]
        self.assertEqual(len(weak), 6, "the fixture must have six weak beats")
        for step in weak:
            self.assertEqual(step.role, ROLE_FILL)
            self.assertLess(len(step.voicing.active_frets()), 4)
            self.assertTrue(step.partial)
            self.assertIn(step.grip, ("shell", "interval", "melody"))

    def test_the_arrangement_is_thinner_than_the_uniform_one(self):
        """
        The measurable claim: the same melody, voiced with fewer notes on average.

        The guide's objection to voicing every note is that it "bogs down the rhythm",
        and that is exactly what this asserts - without losing any of the chords on
        the strong beats.
        """
        uniform = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION, timings=self.TIMINGS, texture="uniform"
        )
        targets = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION, timings=self.TIMINGS, texture="targets"
        )

        def mean_voices(steps):
            return sum(len(s.voicing.active_frets()) for s in steps) / len(steps)

        self.assertLess(mean_voices(targets), mean_voices(uniform))

        # And the chords on the target beats must still be *stated in full*. The frets
        # are deliberately not compared: a target is voice-led from the shape before
        # it, and that shape is now a shell or an interval, so the same position
        # would be the wrong answer. What must not vary is the voice count and grip.
        FOUR_NOTE_GRIPS = ("drop2", "drop3", "drop24", "drop2_6432")
        for plain, thin in zip(uniform, targets):
            if thin.metric_weight > 0:
                self.assertEqual(
                    len(plain.voicing.active_frets()),
                    len(thin.voicing.active_frets()),
                )
                # Both are complete four-note chords; *which* family supplied one is the
                # selector's business, and with `drop3` and `drop24` in the palette the
                # two textures need not agree - a target is voice-led from the shape
                # before it, which is thinner, and a different string set can follow
                # from that. What must hold is that a target never drops below four notes.
                self.assertIn(thin.grip, FOUR_NOTE_GRIPS, thin.tab_line())
                self.assertIn(plain.grip, FOUR_NOTE_GRIPS, plain.tab_line())

    def test_a_weak_beat_never_sounds_a_note_outside_the_chord(self):
        """
        Every pitch under a fill is a chord tone, or the melody itself.

        The interval grip may reach for a diatonic tone to complete a 6th, but a fill
        is a texture - it must never quietly reharmonise the bar.
        """
        checked = 0
        for step in self.steps:
            if step.role != ROLE_FILL:
                continue
            checked += 1
            root, quality = arranger.ChordParser.parse_chord_name(step.chord)
            self.assertIsNotNone(root)
            tones = set(
                arranger.ChordParser.get_chord_tones(
                    arranger.ChordParser.canonical_quality(quality or ""), step.chord
                )
            )
            harmony = tones | {max(step.voicing.midi_notes()) % 12}
            for pc in step.voicing.pitch_classes():
                self.assertIn(pc, harmony, f"{step.chord} under {step.melody}")
        self.assertGreater(checked, 0, "the fixture must contain fills")

    def test_every_generated_voicing_is_still_playable(self):
        """
        The playability invariants survive the new grip.

        A texture is a decision about how many notes to play, never about whether the
        shape can be fingered.
        """
        for step in self.steps:
            voicing = step.voicing
            self.assertIn(frozenset(voicing.active_strings), supported_string_sets())
            self.assertLessEqual(voicing.fret_span(), GRIP_MAX_SPAN[voicing.grip])
            # The melody is on the soprano string and is the highest note sounding.
            self.assertEqual(voicing.soprano_string(), voicing.active_strings[-1])
            for fret in voicing.active_frets():
                self.assertTrue(0 <= fret <= 18)

    def test_a_no_chord_step_keeps_its_own_semantics(self):
        """
        An NC bar is a single note whatever the metre says.

        It has no harmony to state and nothing to fill, so the texture rules have
        nothing to say about it - and it must still be flagged melody_only.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("C5", "NC", "NC"), ("C5", "maj7", "Fmaj7")],
            timings=[(0, 2.0, None), (0, 1.0, None)],
            texture="targets",
        )
        self.assertTrue(steps[0].melody_only)
        self.assertEqual(len(steps[0].voicing.active_frets()), 1)
        self.assertEqual(steps[1].role, ROLE_TARGET)

    def test_a_fill_that_cannot_be_filled_becomes_a_target(self):
        """
        A thin texture must never cost the tune a chord.

        Where a weak beat has no shell, interval or melody-alone voicing, the step is
        re-prepared as a principal note and its `role` is corrected to match, so the
        reported role never disagrees with the shape that sounds. This is the same
        reasoning that makes the neck window a penalty rather than a filter.

        Asserted as an invariant over a sweep rather than against one hand-picked
        note, because *which* notes force the fallback is an implementation detail
        that would change whenever the grip tables do. What must hold is the
        correspondence: a fill is thin, and anything sounding four voices says it is
        a target - never a fill that quietly got thick.
        """
        checked = 0
        for quality, chord in (
            ("maj7", "Fmaj7"), ("m7", "Dm7"), ("7", "G7"), ("m7b5", "Bm7b5"),
        ):
            for melody in ("C5", "A4", "F4", "E4"):
                steps = VoiceLeadingEngine.arrange_progression(
                    [(melody, quality, chord)],
                    timings=[(0, 2.0, None)],
                    texture="targets",
                )
                for step in steps:
                    checked += 1
                    voices = len(step.voicing.active_frets())
                    if step.role == ROLE_FILL:
                        self.assertLess(voices, 4, f"{chord} {melody}")
                        self.assertNotEqual(step.grip, "drop2", f"{chord} {melody}")
                    else:
                        # The fallback fired, and the role says so.
                        self.assertEqual(step.role, ROLE_TARGET, f"{chord} {melody}")
                        self.assertEqual(voices, 4, f"{chord} {melody}")
        self.assertGreater(checked, 0, "no step was arranged at all")


class TestIntervalGrip(unittest.TestCase):
    """The new two-note grip: where it sits, and what it is allowed to contain."""

    QUALITIES = [
        ("maj7", "Cmaj7"), ("m7", "Dm7"), ("7", "G7"), ("m7b5", "Bm7b5"),
        ("6", "C6"), ("m", "Cm"), ("9", "C9"), ("13", "C13"), ("dim7", "Bdim7"),
        ("maj9", "Cmaj9"), ("7b9", "G7b9"), ("7alt", "G7alt"), ("sus4", "Csus4"),
    ]

    def test_the_interval_grip_is_registered_in_both_tables(self):
        """
        It is a real grip family, in the two tables that define the playability
        invariant - not a special case inside the selector.
        """
        self.assertIn("interval", GRIP_MAX_SPAN)
        self.assertIn("interval", GRIP_STRING_SETS)
        self.assertEqual(GRIP_MAX_SPAN["interval"], 4)
        for strings, soprano in GRIP_STRING_SETS["interval"]:
            self.assertIn(frozenset(strings), supported_string_sets())
            self.assertEqual(soprano, strings[0])

    def test_an_interval_is_two_fingers_within_the_span(self):
        """
        Every interval voicing: two active frets, inside the span, on a supported
        string set, with the melody on top.
        """
        checked = 0
        for quality, name in self.QUALITIES:
            for melody in ("C5", "E5", "A4", "G4", "B4"):
                for voicing in VoiceLeadingEngine.get_interval_voicings(
                    Note(melody), quality, chord_name=name
                ):
                    checked += 1
                    active = voicing.active_frets()
                    self.assertEqual(len(active), 2, f"{name} under {melody}")
                    self.assertLessEqual(voicing.fret_span(), 4)
                    self.assertIn(
                        frozenset(voicing.active_strings), supported_string_sets()
                    )
                    self.assertEqual(voicing.grip, "interval")
                    # The melody is the higher of the two notes.
                    self.assertEqual(
                        max(voicing.midi_notes()),
                        Note(melody).midi_note(),
                        f"{name} under {melody}: melody is not the top voice",
                    )
                    for fret in active:
                        self.assertTrue(0 <= fret <= 18)
        self.assertGreater(checked, 0, "no interval voicings were generated at all")

    def test_the_two_notes_are_a_third_or_a_sixth_apart(self):
        """A 3rd, a 6th or a 10th - the intervals the guide names, and no others."""
        allowed = {3, 8, 9}
        for quality, name in self.QUALITIES:
            for melody in ("C5", "A4", "G4"):
                for voicing in VoiceLeadingEngine.get_interval_voicings(
                    Note(melody), quality, chord_name=name
                ):
                    low, high = sorted(voicing.midi_notes())
                    self.assertIn((high - low) % 12, allowed, f"{name} under {melody}")

    def test_an_interval_is_offered_under_any_melody_degree(self):
        """
        An interval is offered under any melody degree, and so - since the duo's melody
        gate was lifted - is a duo.

        The guide asks for "2-note intervals (3rds or 6ths)" as a *fill*, so a 3rd or a
        7th in the melody has to be playable.

        The second half of this test was **inverted rather than deleted**. It used to
        assert that a duo refuses those same three melodies, and cited that refusal as
        the reason `interval` is a distinct family. A duo no longer refuses them: its
        second voice is the chord's guide tone, and a guide tone *beneath* a 3rd or a 7th
        is what states the chord's function rather than losing it. So the distinction
        between the two families is no longer the melody degree, and asserting the old
        difference would assert a rule the engine does not have.

        What still distinguishes them is asserted below: a duo is a **harmony** and must
        sound a guide tone, while an interval is a **texture** and pairs the melody with
        whichever of a 3rd, 6th or 10th it can reach - including, for a non-chord tone, a
        note of the prevailing key rather than of the chord.
        """
        for quality, name, melody in (
            ("m7", "Dm7", "C5"),
            ("7", "D7", "F#4"),
            ("maj7", "Dmaj7", "C#5"),
        ):
            voicings = VoiceLeadingEngine.get_all_grip_voicings(
                Note(melody), quality, chord_name=name, grips=("interval",)
            )
            self.assertTrue(voicings, f"no interval under {melody} for {name}")

    def test_a_duo_under_a_third_or_a_seventh_sounds_a_guide_tone(self):
        """
        The rule that replaced the melody gate: under a 3rd or a 7th, a duo is offered,
        and its second voice is the chord's guide tone.

        This is what makes the pair above a *harmony* rather than a renamed interval -
        the assertion the old "a duo refuses these" check used to stand for.
        """
        for quality, name, melody in (
            ("m7", "Dm7", "C5"),      # the b7 in the melody
            ("7", "D7", "F#4"),      # the 3rd in the melody
            ("maj7", "Dmaj7", "C#5"),  # the major 7th in the melody
        ):
            duos = VoiceLeadingEngine.get_all_grip_voicings(
                Note(melody), quality, chord_name=name, grips=("duo",)
            )
            self.assertTrue(duos, f"no duo under {melody} for {name}")
            guide = set(SHELL_DEGREES[quality])
            # The degrees are measured from the **chord's** root, not from the melody:
            # the melody is often the 7th, and measuring from it would report every
            # pair as containing a guide tone by accident.
            root_name, _ = ChordParser.parse_chord_name(name)
            root_pc = Note(f"{root_name}4").midi_note() % 12
            for v in duos:
                degrees = {(p - root_pc) % 12 for p in v.midi_notes()}
                self.assertEqual(len(degrees), 2, v.tab_string())
                self.assertTrue(
                    degrees & guide,
                    f"{v.tab_string()} under {melody} sounds {sorted(degrees)}, "
                    f"which contains no guide tone of {quality}",
                )

    def test_no_interval_without_a_chord_root(self):
        """
        With no chord name there are no guide tones to measure from, so nothing is
        generated.

        The same argument as the shell: an interval named against a chord we cannot
        identify is a guess, and a guess here is how a wrong note gets in.
        """
        self.assertEqual(VoiceLeadingEngine.get_interval_voicings(Note("C5"), "maj7"), [])

    def test_offsets_are_empty_rather_than_guessed_for_an_unknown_quality(self):
        """A quality with no tone set yields no intervals at all."""
        self.assertEqual(_interval_offsets((), Note("C5").midi_note(), 0), [])


class TestARepeatedMelodyHoldsItsString(unittest.TestCase):
    """A held note stays on the string the hand is already on.

    A `repeated` step is a **hold**: the renderers strike its soprano alone and let the
    inner voices ring. That is only true if the melody is where the previous step's
    finger already is - and the selector used to be free to move it. Span outranks neck
    position in `voicing_cost`, and a fill's thin palette has a compact shape whose top
    note sits on a different string, so a bar of four identical notes read as a
    four-fret jump and the chord the step had just voiced was muted by a rule that meant
    "hold what is already ringing".

    Two halves of one claim, which is why the last test here is a sweep rather than the
    bar the report came from: `decisions.hold_the_melody_string` narrows the candidates
    to the held string before the selector sees them, and `decisions.is_repeated_step`
    marks the step only when the melody really did stay there.
    """

    def test_a_fill_on_a_repeated_note_keeps_the_melody_string(self):
        """The reported bar, reduced: four G4s over `Eb7` under `--texture targets`.

        Beats 1 and 3 are targets and beats 2 and 4 are fills. Measured before the fix,
        the soprano string ran `[4, 3, 4, 3]` - the B string for the targets and the G
        string for the fills, four frets apart, on a note that never moves.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("G4", "7", "Eb7")] * 4,
            timings=[(0, float(beat), None) for beat in (1, 2, 3, 4)],
            texture="targets",
        )
        self.assertEqual([step.melody for step in steps], ["G4"] * 4)
        self.assertEqual(
            [step.voicing.soprano_string() for step in steps],
            [4, 4, 4, 4],
            "the melody changed strings on a note that never moved",
        )

    def test_the_reported_bar_of_the_committed_head_holds_one_string(self):
        """Bar 3 of "All the Things You Are", read from the file.

        The hand-built case above is this bar with everything else stripped away; the
        fixture is where the report came from, and asserting it keeps the head under a
        test rather than only under the loader's.
        """
        from headxml import arrange_xml_head

        steps, _head, _notes = arrange_xml_head(
            "tests/data/synthetic_common_8.musicxml", texture="targets"
        )
        bar_three = [step for step in steps if step.bar == 3]
        self.assertEqual([step.melody for step in bar_three], ["G4"] * 4)
        self.assertEqual([step.chord for step in bar_three], ["Eb7"] * 4)
        self.assertEqual(
            [step.voicing.soprano_string() for step in bar_three], [5, 5, 5, 5]
        )

    def test_the_rule_never_comes_back_empty_handed(self):
        """A palette with nothing on the held string is left alone, not emptied.

        The narrowing may not be a filter that can starve a step: a thin palette has no
        shape on some strings, and a step left with no candidates is a chord the engine
        had already voiced and then dropped. The caller keeps its own candidates in that
        case, and `is_repeated_step` then simply does not mark the step.
        """
        from tests.support import make_step, make_voicing

        previous = make_step([-1, -1, -1, 10, 12, 10], chord="Cmaj7", melody="A4")
        elsewhere = [make_voicing([-1, -1, -1, 10, 15, -1])]
        self.assertIs(hold_the_melody_string(elsewhere, previous), elsewhere)

    def test_a_step_whose_soprano_moved_is_not_a_hold(self):
        """The flag's second clause, on its own.

        Both shapes below re-state the same top pitch under the same harmony, so
        `holds_the_shape` is true of each and the string is the only thing separating a
        hold from a jump.
        """
        from arranger.chords import sounding_harmony
        from tests.support import make_step, make_voicing

        previous = make_step([-1, -1, -1, 10, 12, 10], chord="Cmaj7", melody="A4")
        harmony = sounding_harmony(previous)
        top = max(previous.voicing.midi_notes())
        # D5 on the high E string (index 5), and the same note on the B string (index 4).
        same = make_voicing([-1, -1, -1, 10, 12, 10])
        moved = make_voicing([-1, -1, -1, 10, 15, -1])
        self.assertEqual(max(moved.midi_notes()), top)
        self.assertTrue(holds_the_shape(previous, top, harmony))
        self.assertTrue(is_repeated_step(previous, same, harmony))
        self.assertFalse(is_repeated_step(previous, moved, harmony))

    def test_every_repeated_step_over_the_committed_heads_keeps_its_string(self):
        """The rule asserted on the whole, where a shape-level check cannot see it.

        Every renderer assumes *a `repeated` step's melody is on the string the previous
        step's melody is on*, and a rule stated over a generated `Voicing` says nothing
        about the step the engine assembles afterwards. So it is swept: the committed
        heads over five arity/bass combinations. The thumb rows carry no holds at all,
        because a fill under a thumb is `bass_only` and nothing there is marked
        `repeated`; they are swept so that a change which makes one is caught rather
        than assumed away. The counts are in
        [docs/open-issues.md](../docs/open-issues.md) item 2.

        The arrangements are `tests.support.arranged`'s: this sweep and the four-fret one
        in `test_walking_bass` ask for the same heads under the same textures. The heads
        are `tests.support.sweep_head_paths()`: the string a hold keeps is a rule about the
        metre and the notation, so one head per metre answers it.
        """
        from tests.support import arranged, sweep_head_paths

        paths = sweep_head_paths()
        configs = (
            ("uniform", "auto"),
            ("targets", "auto"),
            ("targets", BASS_STYLE_WALK),
            ("targets", "root"),
            ("chord1", BASS_STYLE_WALK),
        )
        checked = 0
        for path in paths:
            for texture, bass in configs:
                steps, _head, _notes = arranged(path, texture=texture, bass=bass)
                for previous, step in zip(steps, steps[1:]):
                    if not step.repeated:
                        continue
                    checked += 1
                    self.assertEqual(
                        step.voicing.soprano_string(),
                        previous.voicing.soprano_string(),
                        f"{path} bar {step.bar} beat {step.beat}: the hold of "
                        f"{step.melody} re-struck on another string ({step.tab_line()})",
                    )
        # The corpus is deliberately shorter than the retired transcriptions, so
        # the premise is that the hold is exercised, not an old population count.
        self.assertGreater(checked, 20, "the hold is not exercised at all")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
