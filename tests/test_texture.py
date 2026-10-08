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
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    GRIP_STRING_SETS,
    ROLE_FILL,
    ROLE_TARGET,
    SHELL_DEGREES,
    TEXTURE_GRIPS,
    TEXTURE_STYLES,
    THUMB_TEXTURES,
    ChordParser,
    Diagnostics,
    VoiceLeadingEngine,
    _interval_offsets,
    _metric_weight,
    _roles_for_slot,
    supported_string_sets,
)

# Imported from where they live rather than through the package facade, for the reason
# `test_walking_bass` gives for the private `bass` helpers: these are the rule's own
# spelling, and re-exporting them would enlarge the public surface for one test file's
# benefit.
from arranger.decisions import resolve_texture_grips
from arranger.grips import RIGHT_HAND_STRINGS, grip_pluck_count, thumb_safe_grips

# The library's own demonstration cadences. These are the progressions whose tab is
# already asserted elsewhere in the suite, so they double as the fixture here: if the
# metric layer ever leaked into the default path, these strings would move.
MINOR_CADENCE = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("B4", "7", "G7"),
    ("C5", "maj7", "Cmaj7"),
]
def minor_cadence_tabs():
    """
    The published fingerings for MINOR_CADENCE, as the library produces them now.

    Defined here as a function rather than a literal in each test, because two files
    assert this tab and a second copy of the literals is a second thing to forget when
    a change is deliberate. Callers compare against it rather than typing it.

    The G7 is a drop-3 on strings 5-3-2-1 (`x-8-x-7-8-7`) where it was a drop-2 at
    `x-x-5-7-6-7` - the same G7, span 1 against span 2. See
    `test_the_demo_cadences_still_produce_the_same_tab`, which pins both cadences and
    says why each shape moved.
    """
    return [
        "x-x-10-10-10-10", "x-x-9-9-8-8", "x-8-x-7-8-7", "x-x-9-9-8-8",
    ]


def major_cadence_tabs():
    """
    The published fingerings for MAJOR_CADENCE. See `minor_cadence_tabs`.

    The A-7 is `x-x-x-x-x-9` - the melody alone, its chord dropped - where it was a
    complete four-note drop-2 & 4 at `x-10-10-x-10-9`. That shape came from one of the
    four inner-skip `drop24` sets, removed because a finger had to reach over the
    unplucked G to fret it (`docs/fingering.md` §4.4), and C#5 over an Am7 is a non-chord
    tone, so the set that could harmonise it was doing the *fallback* work as well: the
    only candidate left needs five frets (`x-10-x-5-10-9`), the four-fret budget refuses
    it, and the step keeps the tune and loses the chord, with a diagnostic naming the
    cause. It is the ban's one audible cost in the demos, and it is pinned rather than
    re-pinned away - if that chord is judged worth more than the ban, the alternative is
    to keep the sets and let the *selector* rank them last (measured in §4.4).
    """
    return [
        "x-x-10-10-10-10", "x-10-x-9-10-9", "x-x-x-x-x-9", "x-x-11-10-10-10",
    ]


MAJOR_CADENCE = [
    ("D5", "m7", "Dm7"),
    ("C#5", "7", "A7"),
    ("C#5", "m7", "A-7"),
    ("D5", "mMaj7", "Dm(maj7)"),
]

# "But Not For Me" bars 1-2 in F, as the arranging guide writes them: the C target on
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
        self.assertEqual(_metric_weight(0, 1.0), 2)

    def test_beat_three_in_four_four_weighs_one(self):
        """Beat 3 weighs 1: the second half-note pulse of a 4/4 bar."""
        self.assertEqual(_metric_weight(0, 3.0), 1)

    def test_the_other_beats_weigh_nothing(self):
        """Beats 2 and 4 are connecting notes, so they weigh 0."""
        self.assertEqual(_metric_weight(0, 2.0), 0)
        self.assertEqual(_metric_weight(0, 4.0), 0)

    def test_no_timing_weighs_minus_one(self):
        """
        A slot with no timing weighs -1, not 0.

        This is the distinction the whole feature rests on: "we were never told
        where this note falls" is not "we were told it is weak". Collapsing the two
        would thin out every hand-written progression.
        """
        self.assertEqual(_metric_weight(None, 1.0), -1)
        self.assertEqual(_metric_weight(0, None), -1)
        self.assertEqual(_metric_weight(None, None), -1)

    def test_a_three_four_bar_still_has_a_second_target(self):
        """
        A 3/4 bar keeps beats 1 and 3.

        A waltz states its harmony on the downbeat and the third beat, so the rule
        has to read the metre it is given rather than assuming 4/4.
        """
        self.assertEqual(_metric_weight(0, 1.0, beats_per_bar=3), 2)
        self.assertEqual(_metric_weight(0, 3.0, beats_per_bar=3), 1)
        self.assertEqual(_metric_weight(0, 2.0, beats_per_bar=3), 0)

    def test_a_two_two_bar_has_no_third_beat(self):
        """
        In 2/2 the beat count is two, so beat 3 does not exist and only the
        downbeat is a target.

        A count without a denominator is not a metre: reading 2/2 as if it had four
        beats would put a target on beat 3 of every bar of a cut-time head.
        """
        self.assertEqual(_metric_weight(0, 1.0, beats_per_bar=2), 2)
        self.assertEqual(_metric_weight(0, 3.0, beats_per_bar=2), 0)

    def test_a_float_beat_is_not_read_as_a_downbeat(self):
        """
        The eighth of a 2/2 bar (1.5) is not beat 1.

        Without a tolerance an exact comparison would call no real note a downbeat,
        because notated beats are floats.
        """
        self.assertEqual(_metric_weight(0, 1.5), 0)
        self.assertEqual(_metric_weight(0, 2.5), 0)
        self.assertEqual(_metric_weight(0, 1.0 + 5e-7, beats_per_bar=3), 2)
        self.assertEqual(_metric_weight(0, 3.0 - 5e-7, beats_per_bar=3), 1)

    def test_the_bar_number_does_not_change_the_weight(self):
        """
        Only the beat within the bar decides, not which bar it is.

        Otherwise a weak note in bar 40 would be treated differently from the same
        beat in bar 1, and the rule would not be a metric rule at all.
        """
        self.assertEqual(_metric_weight(0, 1.0), _metric_weight(39, 1.0))
        self.assertEqual(_metric_weight(-3, 2.0), _metric_weight(7, 2.0))


class TestRoles(unittest.TestCase):
    """The mapping from a weight to the roles a slot may take."""

    def test_uniform_makes_every_slot_a_target(self):
        """`uniform` is the historical behaviour, for every weight including 0."""
        for weight in (-1, 0, 1, 2):
            self.assertEqual(_roles_for_slot(weight, "uniform"), [ROLE_TARGET])

    def test_targets_gives_a_full_chord_to_a_strong_beat(self):
        """Beats 1 and 3 are targets under the `targets` texture."""
        self.assertEqual(_roles_for_slot(2, "targets"), [ROLE_TARGET])
        self.assertEqual(_roles_for_slot(1, "targets"), [ROLE_TARGET])

    def test_targets_makes_an_ordinary_beat_a_fill(self):
        """Beat 2 and beat 4 are fills - the guide's 'fill the gaps'."""
        self.assertEqual(_roles_for_slot(0, "targets"), [ROLE_FILL])

    def test_a_slot_with_no_timing_is_still_a_target(self):
        """
        With timings=None nothing is known, so every slot is a target.

        This is the single most important line in the feature: it is what makes
        `targets` a no-op on a progression that carries no rhythm.
        """
        self.assertEqual(_roles_for_slot(-1, "targets"), [ROLE_TARGET])

    def test_an_unknown_texture_is_rejected(self):
        """A typo must be reported, not silently arranged as `uniform`."""
        with self.assertRaises(ValueError) as caught:
            _roles_for_slot(2, "sorcery")
        self.assertIn("sorcery", str(caught.exception))
        self.assertIn("targets", str(caught.exception))

    def test_every_declared_texture_has_both_roles(self):
        """
        TEXTURE_GRIPS is a total table: a texture with a missing role would raise
        KeyError deep inside the selector instead of at the call site.

        The **key** is what must be present, not a non-empty tuple. `walking_bass`
        declares `fill: ()` on purpose - an empty tuple means the left hand plays
        nothing there and the melody is voiced alone - so "non-empty" was a proxy for
        "this role is handled" that the texture itself falsifies. What has to hold is
        that the key exists, and that a texture which does mean to be thin says so the
        same way every time: by being the empty tuple, never by being absent.
        """
        for texture in TEXTURE_STYLES:
            for role in (ROLE_TARGET, ROLE_FILL):
                self.assertIn(role, TEXTURE_GRIPS[texture])

    def test_every_empty_palette_is_a_texture_that_means_it(self):
        """
        An empty grip tuple is a decision, and the set of them is asserted exactly.

        `arrange_progression` treats `()` as "the left hand plays nothing" and routes
        the step through the melody-alone path. Any *other* texture reaching that branch
        would silently lose its harmony, which is the failure the walking-bass rule is
        careful not to create anywhere else.

        **This assertion was narrowed, not deleted, when the melody-only textures
        moved to the voices axis.** It used to list the `melody` and `melody_bass`
        palettes alongside `walking_bass`'s fill; those two textures are gone, and
        the fact they stated is keyed on the voice selection now - the loop hands
        the empty palette to a melody-only selection (`melody_only_selection`)
        without consulting this table at all, which is why a selection cannot miss
        the melody-alone route by being absent from it.

        What survives is the rule the test was for: the only empty palette a
        *texture* carries is `walking_bass`'s fill, declared by name in the same
        tables `arrange_progression` reads - so a texture that harmonises something
        cannot reach the melody-alone route by accident.
        """
        empty = [
            (texture, role)
            for texture in TEXTURE_STYLES
            for role in (ROLE_TARGET, ROLE_FILL)
            if not TEXTURE_GRIPS[texture][role]
        ]
        self.assertEqual(
            empty,
            [("walking_bass", ROLE_FILL)],
            "an empty palette appeared or disappeared - name the texture that means it",
        )
        # And the table that routes it is the one declaring the textures, so a
        # thumb texture cannot gain an empty palette without reaching the right branch.
        for texture, _role in empty:
            self.assertTrue(
                texture in THUMB_TEXTURES,
                f"{texture} has an empty palette but is not a thumb texture",
            )

    def test_the_walking_bass_texture_is_declared(self):
        """
        `walking_bass` is a texture like any other: in TEXTURE_STYLES, validated by
        `arrange_progression` before any voicing work, and policy in TEXTURE_GRIPS.
        """
        self.assertIn("walking_bass", TEXTURE_STYLES)
        # A shell (3rd & 7th) on a target and nothing above the melody between them.
        self.assertEqual(TEXTURE_GRIPS["walking_bass"][ROLE_TARGET], ("shell",))
        self.assertEqual(TEXTURE_GRIPS["walking_bass"][ROLE_FILL], ())
        # No grip is shared between the two roles, or the texture would do nothing.
        self.assertFalse(
            set(TEXTURE_GRIPS["walking_bass"][ROLE_TARGET])
            & set(TEXTURE_GRIPS["walking_bass"][ROLE_FILL])
        )

    def test_a_uniform_texture_offers_exactly_the_default_grips(self):
        """
        `uniform` must be GRIP_PREFERENCE, not an approximation of it.

        If it drifted, the default arrangement would change without anyone asking
        for a texture, and the backward-compatibility guarantee would be a fiction.
        """
        self.assertEqual(
            TEXTURE_GRIPS["uniform"][ROLE_TARGET], arranger.GRIP_PREFERENCE
        )
        self.assertEqual(
            TEXTURE_GRIPS["uniform"][ROLE_FILL], arranger.GRIP_PREFERENCE
        )


class TestGripsIntersectTheTexture(unittest.TestCase):
    """
    `grips` narrows the texture, and the texture does not overrule it.

    A caller's `grips` used to be discarded outright by any non-uniform texture
    (`slot_grips = texture_grips[role]`), so `--grips shell --texture targets` asked
    for shell-only and silently got a four-note drop-2 on every strong beat. The rule is
    now the intersection, and an empty intersection is reported rather than ignored.
    """

    # But Not For Me's strong beats, in a form both paths can read.
    PROGRESSION = [("G4", "maj", "Ebmaj")]

    def test_a_requested_grip_wins_on_a_fill(self):
        """`shell` is in the `targets` fill palette, so the intersection keeps it."""
        steps = VoiceLeadingEngine.arrange_progression(
            [("F4", "maj7", "Fmaj7")],
            grips=("shell",),
            texture="targets",
            timings=[(0, 2.0, 1.0)],
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].voicing.grip, "shell")

    def test_a_requested_grip_narrowing_a_target_is_honoured(self):
        """
        `drop2` is the one grip both the caller's and a target's palette contain.

        `grips=("drop2",)` under `targets` narrows the target to `("drop2", "drop3")` to
        just `("drop2",)`, so `drop3` is never offered. Dm7 under D4 is used rather than
        the Ebmaj below because it is a target whose drop-2 *is* playable: the Ebmaj step
        is demoted to the melody alone by the fallback, which is a different rule and is
        tested on its own.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            [("D4", "m7", "Dm7")],
            grips=("drop2",),
            texture="targets",
            timings=[(0, 1.0, 1.0)],
        )
        self.assertTrue(steps)
        for step in steps:
            self.assertEqual(step.voicing.grip, "drop2", step.tab_line())
            self.assertEqual(len(step.voicing.active_frets()), 4, step.tab_line())

    def test_an_empty_intersection_falls_back_and_says_so(self):
        """
        Asking for a grip the texture never uses is a caller error, not a silent change.

        `--grips shell --texture targets` on a *target* has nothing in common: a target
        is only offered `("drop2", "drop3")`. The step still sounds - losing a chord of
        the tune is worse than ignoring a flag - and the warning says what was ignored,
        which the old code never did.
        """
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            steps = VoiceLeadingEngine.arrange_progression(
                self.PROGRESSION,
                grips=("shell",),
                texture="targets",
                timings=[(0, 1.0, 1.0)],
            )
        self.assertTrue(steps, "the step must not be lost")
        self.assertIn("none of which is in the requested", buffer.getvalue())

    def test_an_empty_palette_is_not_reported(self):
        """
        The companion to the case above, and the one that was broken.

        `walking_bass`'s **fill** palette is `()` on purpose - it means the left hand
        plays nothing between the anchors - so an explicit `--grips shell` intersects
        to nothing on every single fill. That is not a caller asking for a grip the
        texture cannot use, so it is not a caller error, and warning about it printed
        the same line 76 times over one arrangement: output that unusable on a
        legitimate flag combination is a defect in its own right.

        The warning still stands for the case above, where the palette is non-empty
        and simply does not contain what was asked for.
        """
        self.assertEqual(
            TEXTURE_GRIPS["walking_bass"][ROLE_FILL],
            (),
            "the premise: this palette is empty by design, not by accident",
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            steps = VoiceLeadingEngine.arrange_progression(
                MINOR_CADENCE,
                grips=("shell",),
                texture="walking_bass",
            )
        self.assertTrue(steps, "the arrangement must not be lost")
        self.assertNotIn(
            "none of which is in the requested",
            buffer.getvalue(),
            "a deliberately empty palette must not be reported as a caller error",
        )
        # Every warning that *is* legitimate still gets through, so this is a
        # suppression of one case and not of the diagnostics path.
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            VoiceLeadingEngine.arrange_progression(
                self.PROGRESSION,
                grips=("shell",),
                texture="targets",
                timings=[(0, 1.0, 1.0)],
            )
        self.assertIn(
            "none of which is in the requested",
            buffer.getvalue(),
            "the non-empty case must still be reported",
        )

    def test_the_default_grips_are_never_narrowed(self):
        """
        The default is not a restriction, so nothing is deleted from the texture.

        This is the case a plain set intersection gets wrong. `GRIP_PREFERENCE` is the
        order a *caller* ranks grips in, and it does not list `interval`, `melody` or
        `drop3` - all of which the texture palettes do use. Intersecting with it would
        silently drop `drop3` from every `targets` target and `interval` from every
        fill, changing the default arrangement. The texture table is the authority on
        what a role may play.
        """
        for role in (ROLE_TARGET, ROLE_FILL):
            self.assertEqual(
                TEXTURE_GRIPS["targets"][role], ("drop2", "drop3")
                if role == ROLE_TARGET
                else ("shell", "interval", "melody"),
            )
        # With no restriction, every role keeps its full palette - which is what the
        # `grips == GRIP_PREFERENCE` branch in the step loop guarantees.
        self.assertNotIn("interval", arranger.GRIP_PREFERENCE)
        self.assertIn("interval", TEXTURE_GRIPS["targets"][ROLE_FILL])
        self.assertIn("drop3", TEXTURE_GRIPS["targets"][ROLE_TARGET])

    def test_a_target_that_cannot_be_played_becomes_the_melody_alone(self):
        """
        The fallback, and the case that no longer needs it for this melody.

        A `targets` target is offered only the four-note grips, so for Ebmaj under G4
        the span-0 shell `x-x-8-8-8-x` is not a candidate - and the cost tuple would not
        have chosen it anyway, because `missing` outranks span. Drop-2's only complete
        option is `x-6-5-3-8-x`, a five-fret stretch, so this step used to fall back to
        the melody alone.

        It no longer does. Drop-3 is offered to a target and is now correct: it places
        its voices on descending strings, and it leaves a triad's doubled root where the
        stack put it instead of dropping it an octave into a b3 - which is what used to
        make Ebmaj sound as Eb minor. So the step now gets a real four-note chord,
        `3-x-1-3-4-x`, and the melody-alone fallback has nothing to do here.

        What is asserted is the *rule*, not the old answer: a `targets` target is always
        either a complete chord or the melody alone, never a partial one, and never a
        melody with a stale chord name.
        """
        steps = VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION,
            texture="targets",
            timings=[(0, 1.0, 1.0)],
        )
        self.assertEqual(len(steps), 1)
        step = steps[0]
        # Either the complete chord drop-3 now provides, or the melody alone - but
        # never a partial harmonisation, which is what this texture exists to avoid.
        self.assertIn(step.voicing.grip, ("drop3", "drop2", "melody"), step.tab_line())
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
        else - which is the whole point, so it is asserted on the table itself.
        """
        self.assertEqual(TEXTURE_GRIPS["targets"][ROLE_TARGET], ("drop2", "drop3"))
        self.assertEqual(
            TEXTURE_GRIPS["targets"][ROLE_FILL], ("shell", "interval", "melody")
        )
        # A target may never use a fill grip, or the texture would do nothing.
        self.assertFalse(
            set(TEXTURE_GRIPS["targets"][ROLE_TARGET])
            & set(TEXTURE_GRIPS["targets"][ROLE_FILL])
        )


class TestTheRightHandBudget(unittest.TestCase):
    """The four digits on the right hand, and what a thumb line costs a target.

    The right hand plucks with thumb, index, middle and ring - `p-i-m-a`, four digits -
    so four strings is the most that can sound at once. That is the same four
    `supported_string_sets()` states, and it states it for a **voicing**: a step is the
    thing the renderers print, and the thumb note is merged into the step *after*
    selection (`VoiceLeadingEngine._attach_bass`), so no check ever saw the two together.
    `--texture targets` voiced a four-note target on its strong beats and then placed a
    bass note under it, which is five simultaneous plucks - one more hand than a player
    has. Measured over the six committed heads before this rule existed, **151** steps
    under `--bass walk` and **130** under `--bass anchors` sounded five strings;
    `walking_bass` and `uniform` sounded none, the first because its targets are shells
    and the second because `bass_allowed` refuses the whole axis.

    The rule is a **budget** rather than a preference, so it narrows the *target* palette
    only, and only while a thumb line is running. See `docs/open-issues.md` item 11.
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

    def test_the_premise_that_the_targets_texture_names_four_string_grips(self) -> None:
        """Without this the narrowing above is load-bearing for nothing.

        The whole defect is a four-note target voiced on a beat the thumb is also playing.
        If that palette ever becomes thumb-safe on its own, this fails so the rule can be
        re-argued rather than quietly kept.
        """
        self.assertTrue(
            any(
                grip_pluck_count(grip) == RIGHT_HAND_STRINGS
                for grip in TEXTURE_GRIPS["targets"][ROLE_TARGET]
            ),
            "targets no longer offers a four-string target, so nothing needs narrowing",
        )


    def test_an_empty_palette_comes_back_unchanged(self) -> None:
        """`()` is the table saying "the left hand plays nothing", not a palette to fix.

        Narrowing it would hand the thumb a chord it was never offered, on every fill of
        the one texture that exists for a thumb.
        """
        self.assertEqual(TEXTURE_GRIPS["walking_bass"][ROLE_FILL], ())
        self.assertEqual(thumb_safe_grips(()), ())

    def test_the_shipped_palettes_that_are_already_thumb_safe_do_not_move(self) -> None:
        """`walking_bass`'s targets and `targets`' fills are inside the budget as they stand."""
        self.assertEqual(
            thumb_safe_grips(TEXTURE_GRIPS["walking_bass"][ROLE_TARGET]), ("shell",)
        )
        self.assertEqual(
            thumb_safe_grips(TEXTURE_GRIPS["targets"][ROLE_FILL]),
            ("shell", "interval", "melody"),
        )

    def test_the_rule_is_inert_without_a_thumb(self) -> None:
        """`has_thumb=False` is the shipped path for every arrangement with no bass line."""
        for role in (ROLE_TARGET, ROLE_FILL):
            self.assertEqual(
                resolve_texture_grips(
                    role, "targets", TEXTURE_GRIPS["targets"], GRIP_PREFERENCE, Diagnostics()
                ),
                TEXTURE_GRIPS["targets"][role],
            )

    def test_a_thumb_narrows_a_target_and_leaves_a_fill_alone(self) -> None:
        """The budget is one palette's, not the slot's: a fill falls between thumb notes."""
        target = resolve_texture_grips(
            ROLE_TARGET, "targets", TEXTURE_GRIPS["targets"], GRIP_PREFERENCE,
            Diagnostics(), has_thumb=True,
        )
        fill = resolve_texture_grips(
            ROLE_FILL, "targets", TEXTURE_GRIPS["targets"], GRIP_PREFERENCE,
            Diagnostics(), has_thumb=True,
        )
        self.assertEqual(target, ("shell",))
        self.assertEqual(fill, TEXTURE_GRIPS["targets"][ROLE_FILL])

    def test_a_requested_grip_that_spends_all_four_fingers_is_reported_not_restored(self) -> None:
        """`--grips drop2` under a thumb reads as "that grip is not available here".

        The budget is applied *before* the caller's narrowing, so the intersection with
        `("shell",)` is empty and takes the existing reported fallback - rather than
        resurrecting the five-pluck step the caller asked for by name.
        """
        diagnostics = Diagnostics()
        resolved = resolve_texture_grips(
            ROLE_TARGET, "targets", TEXTURE_GRIPS["targets"], ("drop2",), diagnostics,
            has_thumb=True,
        )
        self.assertEqual(resolved, ("shell",))
        self.assertTrue(
            any("none of which is in the requested" in w for w in diagnostics.warnings),
            "the fallback must be reported rather than silent",
        )

    def test_a_thumb_carrying_targets_arrangement_never_sounds_five_strings(self) -> None:
        """The engine-level sweep, and the assertion whose absence let this ship."""
        progression = [
            ("F5", "maj7", "Fmaj7"), ("D5", "m7", "Dm7"),
            ("C5", "7", "G7"), ("B4", "maj7", "Cmaj7"),
        ]
        timings = [(bar, 1.0 + 0.5 * n, None) for bar in range(4) for n in range(4)]
        with contextlib.redirect_stdout(io.StringIO()):
            steps = VoiceLeadingEngine.arrange_progression(
                progression, timings=timings, texture="targets", bass="walk"
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
    measured in `docs/fingering.md` §4.4.

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
        removed sets were kept for (see `docs/fingering.md` §4.4).

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
    """`melody=soprano` and `melody=soprano,bass`: the tune alone, and the tune
    with a thumb under it.

    Both answer "lead sheet in, melody out". They are voice selections rather
    than grips because what they change is *which voices sound at all* - a grip
    would have to win a cost comparison it should not be in, and
    `GRIP_PREFERENCE` deliberately leaves `melody` out for exactly that reason.
    They were the `melody` and `melody_bass` textures until the melody-only
    claim moved to the voices axis, which is the question `voices=` answers -
    see `docs/one-fact.md`, commit 3.
    """

    PROGRESSION = BUT_NOT_FOR_ME
    TIMINGS = BUT_NOT_FOR_ME_TIMINGS

    def arrange(self, voices, **kwargs):
        return VoiceLeadingEngine.arrange_progression(
            self.PROGRESSION, timings=self.TIMINGS, melody=voices, **kwargs
        )

    def test_every_slot_is_the_melody_alone(self):
        """Neither selection harmonises anything, on any slot, strong or weak.

        Counted on `upper_midi_notes`, not on `active_frets`: `_attach_bass` merges the
        thumb into the voicing *after* the upper voice is chosen, so a
        `soprano,bass` step legitimately has two sounding frets. The thing under
        test is that the **left hand** plays one note, and that is what the
        upper voices are.
        """
        for voices in ("soprano", "soprano,bass"):
            steps = self.arrange(voices)
            self.assertTrue(steps, voices)
            for step in steps:
                self.assertEqual(step.grip, "melody", f"{voices} {step.melody}")
                self.assertEqual(
                    len(step.voicing.upper_midi_notes()),
                    1,
                    f"{voices} {step.melody} harmonised the melody",
                )
                self.assertEqual(
                    max(step.voicing.upper_midi_notes()),
                    Note(step.melody).midi_note(),
                    f"{voices} {step.melody}: the melody is not the top note",
                )
                self.assertFalse(step.melody_only, voices)
                # The harmony still exists; it is simply not spelled out. `melody_only`
                # would make the annotation claim "no chord - melody alone", which is
                # false here - the chord name is printed as context.
                self.assertTrue(step.chord)
                self.assertFalse(
                    step.partial, f"{voices} {step.melody} claims a partial chord"
                )

    def test_the_two_differ_only_in_the_thumb_line(self):
        """`soprano` alone has no bass; `soprano,bass` walks one under every bar."""
        for voices in ("soprano", "soprano,bass"):
            steps = self.arrange(voices)
            with_bass = [s for s in steps if s.bass is not None]
            if voices == "soprano":
                self.assertEqual(with_bass, [], "soprano alone must not carry a thumb")
            else:
                self.assertTrue(
                    with_bass, "soprano,bass must carry a thumb line"
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
        played = [s.melody for s in self.arrange("soprano,bass") if not s.bass_only]
        self.assertEqual(
            played,
            [t[0] for t in self.PROGRESSION],
            "soprano,bass dropped, duplicated or reordered the melody",
        )

    def test_they_need_no_grip_to_be_honoured(self):
        """A caller asking for these selections under any `grips` still gets the melody.

        The loop hands a melody-only selection the empty palette without consulting
        `resolve_texture_grips` at all - the selection means the left hand plays
        nothing whatever the grips say, and skipping the resolution skips its
        empty-intersection warnings too. So `--grips duo --voices soprano` must
        still produce the tune, silently.
        """
        for voices in ("soprano", "soprano,bass"):
            for grips in (("duo",), ("shell",), ("drop2",), ()):
                steps = VoiceLeadingEngine.arrange_progression(
                    self.PROGRESSION, timings=self.TIMINGS, melody=voices, grips=grips
                )
                self.assertTrue(steps, f"{voices} {grips} produced nothing")
                for step in steps:
                    self.assertEqual(step.grip, "melody", f"{voices} {grips}")

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
        for step in self.arrange("soprano"):
            self.assertEqual(len(step.voicing.active_frets()), 1)
            self.assertIn(
                frozenset(step.voicing.active_strings),
                supported_string_sets(),
                "a solo note must be one of the singleton sets",
            )


class TestTargetsTexture(unittest.TestCase):
    """What a `targets` arrangement actually sounds like, on a real 4/4 bar."""

    # "But Not For Me" bars 1-2 in F, as the arranging guide writes them: the C
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
            self.assertEqual(step.metric_weight, _metric_weight(bar, beat))
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
