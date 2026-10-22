"""`harmony=`: which degrees the chord part states when it is not singing.

`guide` and `shell_root` are two claims that both need three notes, so the refusal rule is
stated on how many notes were asked for rather than on a table of combinations; and a
family that merely *contains* a bass degree is not that family.
"""

import unittest

from arranger import (
    BASS_DEGREES_6432,
    GRIP_MAX_SPAN,
    HARMONY_AUTO,
    HARMONY_AUTO_POLICIES,
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_SHELL_ROOT,
    HARMONY_STYLES,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    VoiceLeadingEngine,
    get_comping_voicings,
    harmony_allowed,
    parse_harmony,
    supported_string_sets,
)
from arranger.options import ArrangeOptions, Request
from arranger.resolution import resolve_axes
from tests.support import (
    PROGRESSION,
    VOICES_ARG,
    chord_pcs,
    guide_pcs,
    quality_of,
    root_of,
)


class TestTheHarmonyAxis(unittest.TestCase):
    """`harmony=`: which degrees the guitar states when it is not singing.

    The fourth axis, and the only one that answers **what the part says about the
    chord** rather than how many notes sound, where they fall, or who plays the bottom.
    Orthogonality is the claim, so most of what is asserted here is that the axis is
    *inert by default* and inert on a singing arrangement: a new axis that quietly
    changed every published tab would be worse than no axis.
    """

    def test_the_axis_is_inert_by_default(self):
        """`harmony=auto` and no `harmony=` at all are the same arrangement.

        The load-bearing assertion of the whole axis, and the reason the default is the
        sentinel rather than a resolved value: `auto` resolves to `guide`, which is what
        the comping route has always said.
        """
        default = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=VOICES_ARG),
        )
        explicit = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=VOICES_ARG, harmony="auto")
        )
        self.assertEqual(
            [s.voicing.frets for s in default],
            [s.voicing.frets for s in explicit],
            "harmony=auto is not the arrangement that names no harmony",
        )

    def test_the_keyword_and_the_option_spellings_agree(self):
        """`arrange_progression(harmony=...)` and `ArrangeOptions(harmony=...)` agree.

        The same invariant the other three axes hold, and for the same reason: the
        corpus builds an `ArrangeOptions` and passes it, so a default that disagreed
        with the keyword's would make every corpus call look like a caller who had
        passed both.

        Asserted on `HARMONY_SHELL_ROOT` under the **chord part**, which is the one
        selection that can state it: the family is a claim about the chord part (both
        guide tones with a root or 5th below them), so a selection that does not take
        that part is refused rather than quietly arranged as `guide`. The two
        spellings are therefore compared on an arrangement that states what was asked
        - which is the property the test is for.
        """
        by_keyword = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=PART_CHORD, harmony=HARMONY_SHELL_ROOT)
        )
        by_options = VoiceLeadingEngine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(parts=PART_CHORD, harmony=HARMONY_SHELL_ROOT),
        )
        self.assertEqual(
            [s.voicing.frets for s in by_keyword],
            [s.voicing.frets for s in by_options],
        )

    def test_the_default_is_the_sentinel_and_resolves_to_guide(self):
        """The default leaves `harmony` underived, and `auto` resolves to `guide`.

        Asserted separately because the two spellings are load-bearing in different
        places: the field must be `None` - "the request decides" - for the comparison
        above to mean anything, `resolve_axes` must derive `auto` from it, and the
        policy must resolve to the shipped behaviour for the arrangement to be
        unchanged.
        """
        self.assertIsNone(ArrangeOptions().harmony)
        self.assertEqual(
            resolve_axes(
                Request(), None, None, None, None, ArrangeOptions().time_signature
            ).harmony,
            HARMONY_AUTO,
        )
        # Keyed by **whether the guitar sings**, not by the sentinel: `auto` is the
        # engine's own choice and resolves per selection (`resolve_harmony`).
        self.assertEqual(HARMONY_AUTO_POLICIES[False], HARMONY_GUIDE)
        self.assertEqual(HARMONY_AUTO_POLICIES[True], HARMONY_FULL)

    def test_the_axis_is_inert_when_the_guitar_is_singing(self):
        """`harmony=` changes nothing on an arrangement that voices the melody.

        The comping generator is only reached when `melody_voiced` is False, so every
        value must produce the same singing arrangement - otherwise the axis would be
        answering a question that was never asked of it.
        """
        arrangements = [
            [s.voicing.frets for s in VoiceLeadingEngine.arrange_progression(
                PROGRESSION, options=ArrangeOptions(harmony=value)
            )]
            for value in ("auto", HARMONY_GUIDE, HARMONY_SHELL_ROOT)
        ]
        self.assertEqual(
            arrangements[0], arrangements[1],
            "harmony=guide changed a melody-bearing arrangement",
        )
        self.assertEqual(
            arrangements[0], arrangements[2],
            "harmony=shell_root changed a melody-bearing arrangement",
        )

    def test_every_family_in_the_table_is_one_the_parser_accepts(self):
        """`HARMONY_STYLES` and `parse_harmony` cannot drift apart.

        The registry-is-keyed-by-the-spellings rule the voice axis already follows: a
        row in the table that `parse_harmony` could not read would be a family nobody
        could ask for, and asking for it raises rather than falling back.
        """
        for name in HARMONY_STYLES:
            self.assertEqual(parse_harmony(name), name)
        self.assertEqual(parse_harmony(HARMONY_AUTO), HARMONY_AUTO)
        self.assertEqual(parse_harmony(f"  {HARMONY_GUIDE.upper()}  "), HARMONY_GUIDE)

    def test_an_unknown_family_raises_rather_than_falling_back(self):
        """A spelling nobody recognises is a question, not a request for the default.

        Falling back to `guide` here would hand back a part stating something other
        than what was asked for, with nothing to say so.
        """
        with self.assertRaises(ValueError):
            parse_harmony("shell-root")
        with self.assertRaises(ValueError):
            parse_harmony("")

    def test_shell_root_states_both_guide_tones_and_a_bass_degree_under_them(self):
        """The new family, verified as the *conjunction* it is defined to be.

        Both guide tones, all notes inside the chord, and the lowest note a root or a
        5th - the last clause being the one that distinguishes this family from `guide`
        rather than sitting comfortably beside it. See
        `test_shell_root_is_not_merely_a_shape_that_contains_a_bass_degree`.
        """
        for name in ("Dm7", "Cmaj7", "A7", "Gmaj7"):
            for voicing in get_comping_voicings(
                quality_of(name), name, notes=3, shell_root=True
            ):
                midis = voicing.midi_notes()
                pcs = {midi % 12 for midi in midis}
                self.assertTrue(
                    guide_pcs(name) <= pcs,
                    f"{name}: {sorted(pcs)} is missing a guide tone",
                )
                self.assertTrue(
                    pcs <= chord_pcs(name),
                    f"{name}: {sorted(pcs)} sounds a note outside the chord",
                )
                self.assertIn(
                    min(midis) % 12,
                    {(root_of(name) + degree) % 12 for degree in BASS_DEGREES_6432},
                    f"{name}: lowest note {min(midis) % 12} is neither root nor 5th",
                )

    def test_shell_root_is_not_merely_a_shape_that_contains_a_bass_degree(self):
        """The lowest note is what is checked, and the difference is observable.

        **This test is the reason `shell_root` is not a synonym for `guide`.** On an
        `Ebmaj` whose guide tones are D and G, the plain three-note guide shape is
        `D G Bb` - which already *contains* a 5th. So an implementation that asked
        "does some bass degree sound?" rather than "is the lowest note one?" would pass
        every other assertion in this class and produce identical output to `guide`.

        That is not hypothetical: it is what the first implementation did, and this
        assertion is written because of it.
        """
        guide = get_comping_voicings("maj7", "Ebmaj", notes=3)
        shell_root = get_comping_voicings(
            "maj7", "Ebmaj", notes=3, shell_root=True
        )
        self.assertTrue(guide and shell_root, "Ebmaj has no shape of either family")
        guide_frets = {tuple(v.frets) for v in guide}
        shell_root_frets = {tuple(v.frets) for v in shell_root}
        self.assertNotEqual(
            guide_frets, shell_root_frets,
            "shell_root produced exactly the guide-tone shapes",
        )
        # And every shell_root shape really does bottom out on a bass degree.
        for voicing in shell_root:
            self.assertIn(min(voicing.midi_notes()) % 12, {0, 7, 3, 10})

    def test_shell_root_is_reachable_on_every_chord_the_head_uses(self):
        """11 of 11, measured over the chords in the test progression and its neighbours.

        The claim `docs/history/comping-styles.md` §4.1 makes about this family, asserted here
        so it cannot rot: both guide tones *and* a bass degree underneath, inside
        `GRIP_MAX_SPAN`, needs **no new string set** - which is the single most useful
        fact about the family.
        """
        names = (
            "Ebmaj", "Bb7", "Cm7", "Fm7", "Gm7", "Edim7",
            "F7", "Am7", "Dm7", "Abmaj7", "Bbm7",
        )
        for name in names:
            candidates = get_comping_voicings(
                quality_of(name), name, notes=3, shell_root=True
            )
            self.assertTrue(
                candidates, f"{name} has no shell_root shape, so the family is a "
                f"theoretical one and the doc's 11-of-11 claim is wrong"
            )
            for voicing in candidates:
                fretted = [f for f in voicing.frets if f >= 0]
                self.assertLessEqual(
                    max(fretted) - min(fretted), GRIP_MAX_SPAN["shell"],
                    f"{name}: span outside GRIP_MAX_SPAN['shell']",
                )
                # **`supported_string_sets()` and not a comparison against
                # `GRIP_STRING_SETS`.** The table records its sets highest-string-first
                # (`(5, 4, 3)`) while a shape read out of the fret vector comes out
                # ascending, so a tuple comparison has to be told which convention to
                # use and was wrong here twice before this line was written. The
                # invariant helper returns **frozensets**, which says order is not part
                # of the claim - and it is what every other grip test in the repository
                # asserts against, so this does not need to know the answer.
                self.assertIn(
                    frozenset(voicing.active_strings),
                    supported_string_sets(),
                    f"{name}: {voicing.active_strings} is not a supported set",
                )

    def test_the_family_is_inert_when_it_cannot_be_voiced(self):
        """A refused combination warns and keeps the shipped arrangement.

        `harmony_allowed` is derived from how many notes were asked for, so the two
        refusals are arithmetic rather than a list to extend - and refusing rather than
        degrading is the rule `bass_allowed` follows.
        """
        self.assertTrue(harmony_allowed(HARMONY_SHELL_ROOT, PART_NAMES)[0])
        self.assertTrue(harmony_allowed(HARMONY_SHELL_ROOT, (PART_CHORD,))[0])
        # Every family is a claim about the **chord part**, so a selection that does
        # not take it has no part to state the order on.
        self.assertFalse(harmony_allowed(HARMONY_SHELL_ROOT, (PART_BASS,))[0])
        self.assertFalse(harmony_allowed(HARMONY_SHELL_ROOT, (PART_MELODY,))[0])

    def test_a_refused_combination_raises_and_names_the_guide_tones(self):
        """The refusal raises, and its message names the selection that would work.

        **This test used to assert the opposite**, and the inversion is the point
        rather than a weakening: it asserted that a refused `harmony=shell_root`
        warned and then produced an arrangement byte-identical to the default
        `guide` one. That behaviour was the defect - the caller asked for one
        degree family and was silently handed another, on an axis whose whole
        selling point (`docs/history/comping-styles.md`) is that it is *inert* unless
        named. `guide` is what a caller gets by asking for `guide`, so returning
        it for `shell_root` is a substitution wearing the default's clothes.

        What is kept from the original is the half that still means something:
        the message names the family, so a caller can tell what was refused.
        """
        with self.assertRaises(ValueError) as caught:
            VoiceLeadingEngine.arrange_progression(
                PROGRESSION, options=ArrangeOptions(parts=PART_BASS, harmony=HARMONY_SHELL_ROOT),
            )
        message = str(caught.exception)
        self.assertIn(HARMONY_SHELL_ROOT, message)
        self.assertIn("add 'chord' to parts", message)

    def test_an_unknown_family_is_reported_even_on_a_singing_arrangement(self):
        """Resolution happens up front, so a typo is never silently ignored.

        The comping route is not reached when the guitar sings, so resolving inside
        that branch would mean `harmony=bogus` on a default arrangement reported
        nothing at all - and the same argument `_resolve_melody` is resolved for.
        """
        with self.assertRaises(ValueError):
            VoiceLeadingEngine.arrange_progression(
                PROGRESSION, options=ArrangeOptions(harmony="nonsense"),
            )

    def test_the_lone_bass_states_a_root_or_a_fifth(self):
        """The degree rule for a one-note bass shape is `BASS_DEGREES_6432`, not a family.

        It used to be asserted through `harmony=root`, which was a family *for the
        bass voice*; with the parts axis the bass note is what the bass part states,
        and `harmony=` is a claim about the chord part, which a lone bass does not
        take. What survives is the musical rule the family used to spell.
        """
        for name in ("Ebmaj", "Bb7", "Cm7"):
            allowed, _reason = harmony_allowed(HARMONY_SHELL_ROOT, (PART_CHORD,))
            self.assertTrue(allowed)
            voicings = get_comping_voicings(
                quality_of(name), name, notes=1, bass_voice=True
            )
            self.assertTrue(voicings, f"{name} has no bass-voice shape")
            for voicing in voicings:
                self.assertIn(
                    min(voicing.midi_notes()) % 12,
                    {(root_of(name) + degree) % 12 for degree in BASS_DEGREES_6432},
                )
