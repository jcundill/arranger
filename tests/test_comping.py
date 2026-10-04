"""The melody axis: `voices=`, and the guide-tone comping part it produces.

`texture`, `bass` and `voices` are three orthogonal axes, and these tests are mostly
about the **third** one being able to say "somebody else has the tune" without moving
anything else. The load-bearing claim throughout is that the default is inert: every
published arrangement, corpus step and hand-written progression must come out
byte-identical, which is asserted here against the same progression arranged both ways.

What is verified, in order:

- the **generator**: `get_comping_voicings` states a chord with no melody, sounds only
  chord tones, always sounds both guide tones, is a supported string set, and stays
  inside `GRIP_MAX_SPAN`;
- the **default**: `voices=auto` and `voices=guitar` are the arrangement that always
  was, and the option spelling agrees with the keyword spelling;
- the **arrangement**: a comping step is a three-voice shell chosen from the chord alone,
  and `melody_voiced` is `False` — the guitar is not singing. Note what is *not* claimed:
  that the melody's pitch never appears. Measured over three corpus heads, 409 of 2,069
  steps do contain it, because a guide tone can share the melody's pitch class. The
  invariant is the identical candidate set whatever melody is asked about;
- the **refusals**: a texture that harmonises nothing cannot also give the melody away,
  and an `NC` bar is reported rather than silently dropped;
- the **renderer**: a repeated melody holds the whole shape when the guitar is not
  singing, instead of re-striking a soprano that is not there.
"""

import unittest
from typing import List, Tuple

from musthe import Note

from arranger import (
    BASS_DEGREES_6432,
    GRIP_MAX_SPAN,
    GRIP_STRING_SETS,
    HARMONY_AUTO,
    HARMONY_GUIDE,
    HARMONY_POLICIES,
    HARMONY_ROOT,
    HARMONY_SHELL_ROOT,
    HARMONY_STYLES,
    MELODY_ALTO,
    MELODY_AUTO,
    MELODY_BASS,
    MELODY_ONLY_TEXTURES,
    MELODY_POLICIES,
    MELODY_SOPRANO,
    SHELL_DEGREES,
    TEXTURE_STYLES,
    VOICE_NAMES,
    VOICES_ALL,
    VOICES_NONE,
    ChordParser,
    Diagnostics,
    VoiceLeadingEngine,
    format_progression,
    get_comping_voicings,
    harmony_allowed,
    melody_allowed,
    parse_harmony,
    parse_voices,
    resolve_voices,
    supported_string_sets,
    voices_have_soprano,
)
from arranger.options import ArrangeOptions
from arranger.render import _step_cells
from arranger.tuning import _BLANK_CELL

PROGRESSION: List[Tuple[str, str, str]] = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
]

# The two selections these tests are about, spelled **the way a caller passes them**,
# because that is the surface `voices` actually has. `VOICES_NONE` and `VOICES_ALL` are the
# same data as canonical tuples; these are the strings, and the tests would not catch a
# parser that could not read what its own documentation tells a user to type.
VOICES_ARG = "alto,tenor"
VOICES_ALL_ARG = "soprano,alto,tenor,bass"


def quality_of(name: str) -> str:
    """The quality half of a chord name, which is what the generators want."""
    return ChordParser.parse_chord_name(name)[1] or ""


def guide_pcs(name: str) -> set:
    """The two guide tones of a chord as absolute pitch classes.

    Raises rather than returning None for a chord with no guide tones or no readable
    root, because every caller wants them and a `None` would have to be narrowed away
    at each one - and pyright does not narrow through `assertIsNotNone`, so that
    narrowing would have to be an `assert` in every test as well.
    """
    root, quality = ChordParser.parse_chord_name(name)
    degrees = SHELL_DEGREES.get(ChordParser.canonical_quality(quality or ""))
    if not root or degrees is None:
        raise ValueError(f"{name} has no guide tones to state")
    root_pc = Note(f"{root}4").midi_note() % 12
    return {(root_pc + degree) % 12 for degree in degrees}


def chord_pcs(name: str) -> set:
    """Every tone a chord allows, as absolute pitch classes."""
    root, quality = ChordParser.parse_chord_name(name)
    root_pc = Note(f"{root}4").midi_note() % 12 if root else 0
    return {(root_pc + tone) % 12 for tone in ChordParser.get_chord_tones(quality or "")}


def comping(name: str):
    """Every comping candidate for a chord name."""
    return get_comping_voicings(quality_of(name), name)


def bass_comping(name: str):
    """Every candidate for a chord name as a **lone bass voice**."""
    return get_comping_voicings(quality_of(name), name, notes=1, bass_voice=True)


def root_of(name: str) -> int:
    """A chord name's root as an absolute pitch class, or raise.

    The bass-voice tests are about *which* note sounds, which cannot be said without the
    root, so this raises rather than guessing a default the way `chord_pcs` does: a wrong
    root here would make a correct arrangement look wrong instead of failing loudly.
    """
    root, _quality = ChordParser.parse_chord_name(name)
    if not root:
        raise ValueError(f"{name} has no readable root")
    return Note(f"{root}4").midi_note() % 12


class TestCompingGenerator(unittest.TestCase):
    """`get_comping_voicings`: a chord stated without the tune on top."""

    def test_every_quality_the_engine_can_voice_has_a_comping_shape(self):
        """No voiceable quality is left without a guide-tone shape.

        Checked over `CHORD_TONES_FROM_ROOT` rather than a hand-picked list, so a
        quality added later cannot join the engine without being measured here - the
        failure being guarded is exactly one that arrives silently.
        """
        missing = [
            quality
            for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT)
            if not get_comping_voicings(quality, f"C{quality}")
        ]
        self.assertEqual(missing, [], f"no comping shape for {missing}")

    def test_every_candidate_states_the_chord(self):
        """Both guide tones sound, and nothing outside the chord does."""
        for name in ("Cmaj7", "Am7", "G7", "Dm7b5", "Bdim7", "Fmaj7", "C6", "G7sus4"):
            needed, allowed = guide_pcs(name), chord_pcs(name)
            for voicing in comping(name):
                pcs = {midi % 12 for midi in voicing.midi_notes()}
                self.assertTrue(
                    needed <= pcs, f"{name} {voicing.tab_string()} lacks a guide tone"
                )
                self.assertTrue(
                    pcs <= allowed, f"{name} {voicing.tab_string()} sounds a wrong note"
                )

    def test_a_shape_is_three_voices_in_a_supported_set_inside_the_span(self):
        """The playability invariant, minus the melody clause.

        The clause that is dropped is "the melody is on the topmost string", and it is
        dropped for the only reason there is: there is no melody. Everything else -
        three voices, one of the `shell` sets, span within `GRIP_MAX_SPAN["shell"]` -
        is asserted exactly as it is for every other grip.
        """
        supported = {frozenset(s) for s in supported_string_sets()}
        shell_sets = {frozenset(strings) for strings, _ in GRIP_STRING_SETS["shell"]}
        for name in ("Cmaj7", "G7", "Am7", "Fmaj7"):
            for voicing in comping(name):
                active = frozenset(
                    i for i, fret in enumerate(voicing.frets) if fret >= 0
                )
                self.assertEqual(len(voicing.active_frets()), 3, voicing.tab_string())
                self.assertIn(active, supported, voicing.tab_string())
                self.assertIn(active, shell_sets, voicing.tab_string())
                self.assertLessEqual(
                    voicing.fret_span(), GRIP_MAX_SPAN["shell"], voicing.tab_string()
                )

    def test_a_chord_with_no_root_gets_nothing(self):
        """A guide tone is a claim about *this* chord, so no root means no claim.

        The same rule `get_grip_voicings` applies to its shell and duo branches, and
        for the same reason: guessing the 3rd and 7th without a root is how a wrong
        note gets into the tab.
        """
        self.assertEqual(get_comping_voicings("maj7", None), [])
        self.assertEqual(get_comping_voicings("maj7", "H7"), [])
        self.assertEqual(get_comping_voicings("", "C"), [])

    def test_the_window_is_a_preference_and_never_a_filter(self):
        """Narrowing it may cost shapes, but it must never cost the chord.

        The rule the whole library states about `fret_min`/`fret_max`: losing a chord of
        the tune is worse than being a fret out of position.
        """
        wide = get_comping_voicings("maj7", "Cmaj7")
        narrow = get_comping_voicings("maj7", "Cmaj7", fret_min=0, fret_max=0)
        self.assertTrue(wide)
        self.assertTrue(narrow, "a zero-width window must still voice the chord")


class TestTheAxisIsInertByDefault(unittest.TestCase):
    """`voices=auto` and `voices=guitar` are the arrangement that always was."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_auto_and_guitar_agree_with_each_other(self):
        """The sentinel resolves to the same arrangement as saying so."""
        auto = self.engine.arrange_progression(PROGRESSION)
        explicit = self.engine.arrange_progression(PROGRESSION, melody=VOICES_ALL_ARG)
        self.assertEqual(format_progression(auto), format_progression(explicit))

    def test_the_default_still_pins_the_melody_to_the_soprano(self):
        """And every step says the guitar is singing."""
        for step in self.engine.arrange_progression(PROGRESSION):
            self.assertTrue(step.melody_voiced)
            self.assertEqual(
                max(step.voicing.midi_notes()), Note(step.melody).midi_note()
            )

    def test_the_keyword_and_the_option_spellings_agree(self):
        """`arrange_progression` takes the axis both ways and they must not diverge.

        Measured, because the two spellings *did* diverge: `ArrangeOptions.melody`
        defaulted to the resolved `"guitar"` while the keyword defaulted to the
        `"auto"` sentinel, so a caller passing the options was compared field-by-field
        against a different default and told it had passed both.
        """
        by_keyword = self.engine.arrange_progression(PROGRESSION, melody=VOICES_ARG)
        by_option = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(melody=VOICES_ARG)
        )
        self.assertEqual(format_progression(by_keyword), format_progression(by_option))
        self.assertEqual(
            format_progression(self.engine.arrange_progression(PROGRESSION)),
            format_progression(
                self.engine.arrange_progression(PROGRESSION, options=ArrangeOptions())
            ),
        )

    def test_passing_both_spellings_raises(self):
        """As for every other knob: two spellings of one value is a bug, not a merge."""
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(
                PROGRESSION, melody=VOICES_ARG, options=ArrangeOptions()
            )

    def test_an_unknown_policy_raises(self):
        """A spelling nobody recognises is a question, not something to default."""
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(PROGRESSION, melody="banjo")


class TestTheCompingArrangement(unittest.TestCase):
    """`voices=none` through the engine: what the guitarist is handed."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 3.0, 1.0), (0, 4.0, 1.0)]

    def comped(self, **kwargs):
        steps = self.engine.arrange_progression(
            PROGRESSION, melody=VOICES_ARG, **kwargs
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_generator_never_reads_the_melody(self):
        """The load-bearing claim of the whole feature, stated so it cannot pass by luck.

        The first version of this test asserted that no comping step *contains* the
        melody's pitch, which reads well and is false: measured over three corpus
        heads, **409 of 2,069 steps do contain it**. That is not a defect but it is
        worth being exact about, because the two claims are not the same claim:

        - the guitar is not *singing* - the shape was chosen from the chord alone;
        - a chord tone in the shell may *coincide* with the melody's pitch class,
          which is unremarkable and happens on a fifth of all steps.

        So the invariant asserted here is the first one, and it is asserted the only way
        that can be conclusive: **the candidate set is identical whatever melody is
        asked about.** A generator that read the melody could not produce the same
        shapes for `D5` and `G3` under the same chord.
        """
        from arranger.grips import get_comping_voicings

        for chord in ("Dm7", "G7", "Fmaj7"):
            quality = quality_of(chord)
            sets = {
                tuple(sorted(v.tab_string() for v in get_comping_voicings(quality, chord)))
                for _melody in ("D5", "C5", "A4", "F4", "Bb4", "E5", "G3", "D6")
            }
            self.assertEqual(
                len(sets), 1, f"{chord}: the generator's output varies with the melody"
            )

    def test_no_step_is_marked_as_singing(self):
        """What a renderer reads, and what the whole feature is for.

        This is the honest form of the claim: the guitar's part is *not the tune*, and
        `melody_voiced=False` is the flag that says so. It is deliberately **not** the
        stronger "the melody's pitch never appears", which is coincidence-dependent.
        """
        for step in self.comped():
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_the_melody_is_never_pinned_to_a_top_string(self):
        """No soprano is reserved for the tune, because there is no tune to pin.

        Checked over the corpus, where the stronger per-step claim fails. The sets are the
        *duo* family rather than the shell's, because a two-voice comping part is a duo -
        see `grips._comping_string_sets` for why truncating a shell set would have put
        unvetted pairs such as (0, 2) into the tab.
        """
        duo_sets = {frozenset(s) for s, _ in GRIP_STRING_SETS["duo"]}
        for step in self.comped():
            active = frozenset(
                i for i, fret in enumerate(step.voicing.frets) if fret >= 0
            )
            self.assertIn(active, duo_sets, step.tab_line())

    def test_the_step_still_carries_the_written_melody(self):
        """It is the horn's line, and the band lines up against it.

        Dropping it would leave the guitar part with nothing to check the chord name
        against, so `step.melody` is the written note and only the *playing* of it is
        given away.
        """
        for step, triple in zip(self.comped(), PROGRESSION):
            self.assertEqual(step.chord, triple[2])

    def test_every_step_is_a_guide_tone_shape_of_the_requested_arity(self):
        """`partial` is set, because the chord name above describes the harmony only.

        The arity is asserted rather than assumed, because `VOICES_ARG` is two voices and
        the first version of the generator always built a three-note shell regardless.
        """
        for step in self.comped():
            self.assertEqual(step.grip, "shell")
            self.assertEqual(
                len(step.voicing.active_frets()), len(parse_voices(VOICES_ARG)),
                step.tab_line(),
            )
            self.assertTrue(step.partial)

    def test_the_texture_axis_still_decides_where_notes_fall(self):
        """`voices` and `texture` are orthogonal, not one mode between them."""
        steps = self.comped(texture="targets", timings=self.timings)
        roles = [step.role for step in steps]
        self.assertIn("target", roles)
        self.assertIn("fill", roles)

    def test_a_fill_comps_rather_than_singing(self):
        """A texture fill is thin, but it is thin *with a chord*.

        Measured: before `melody_alone_case` learned about the axis, every fill under
        `--texture targets --bass walk` came back as a bare melody note - the guitar
        playing the tune it had been told to give away, on the weak beats only. The
        assertion is on the *shape*, not on the melody's pitch class, which a comping
        shape may legitimately share; see `test_the_generator_never_reads_the_melody`.
        """
        for step in self.comped(texture="targets", timings=self.timings):
            self.assertEqual(
                len(step.voicing.active_frets()), len(parse_voices(VOICES_ARG)),
                step.tab_line(),
            )
            self.assertEqual(step.grip, "shell", step.tab_line())
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_the_bass_axis_still_decides_the_bottom(self):
        """`bass=walk` walks under a comping part, and `bass=none` does not.

        This is the band setting as a whole: both axes named, and neither inferred
        from the other.
        """
        walked = self.comped(texture="targets", bass="walk", timings=self.timings)
        self.assertTrue(any(step.bass is not None for step in walked))
        silent = self.comped(texture="targets", bass="none", timings=self.timings)
        self.assertTrue(all(step.bass is None for step in silent))
        for step in silent:
            self.assertFalse(step.melody_voiced)

    def test_an_nc_bar_is_reported_rather_than_silently_dropped(self):
        """An `NC` bar has no chord, so there is no guide tone to state.

        The guitar is genuinely silent there and that is worth a sentence: the horn is
        not silent, and a part that quietly omits a bar reads as a mistake.
        """
        diagnostics = Diagnostics()
        steps = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("C5", "NC", "NC"), ("A4", "7", "A7")],
            melody=VOICES_ARG, diagnostics=diagnostics,
        )
        self.assertEqual([step.chord for step in steps], ["Dm7", "A7"])
        self.assertTrue(
            any("NC" in warning for warning in diagnostics.warnings),
            diagnostics.warnings,
        )


class TestTheCompingRouteCarriesAThumb(unittest.TestCase):
    """The thumb line must not be refused for a palette the comping route never plays.

    **`bass_allowed` was asked about `TEXTURE_GRIPS` on a route where it is inert.**
    That table describes the shapes `get_all_grip_voicings` generates; on the comping
    route the shapes come from `get_comping_voicings` and the texture is a meaningless
    name - measured on `tests/data/but_not_for_me.mxl`, all 80 comping shapes are
    byte-identical under `texture=uniform` and `texture=targets`.

    So `melody="alto,tenor", bass="walk"` under the **default** texture was refused with
    "uniform leaves no bass string free for a target" and emitted no thumb at all, while
    the same request under `texture=targets` emitted 127. The warning named a setting
    that could not change the outcome.

    The existing `test_the_bass_axis_still_decides_the_bottom` passed throughout,
    because it spelled `texture="targets"` - the one texture that happened to fit. These
    tests pin the invariant rather than the workaround: **the texture is inert on this
    route, so it must not appear in the decision.**
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # The same hand-written progression and timings the arrangement class above
        # uses. `test_the_walked_beats_reach_the_part` depends on the timings being
        # denser than the four notes, since it asserts that a walk can invent beats -
        # so they are spread over four beats rather than sitting on all four slots.
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 2.5, 0.5), (0, 3.5, 0.5)]

    def comped(self, **kwargs):
        steps = self.engine.arrange_progression(
            PROGRESSION, melody=VOICES_ARG,
            diagnostics=Diagnostics(), timings=self.timings, **kwargs,
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_default_texture_no_longer_refuses_a_thumb_line(self):
        """The regression itself: `bass=walk` under the default texture.

        Asserted on the *thumb notes* rather than on the warning, because a fix that
        merely quieted the warning while still dropping the line would pass otherwise.
        """
        steps = self.comped(bass="walk")
        self.assertTrue(
            any(step.bass is not None for step in steps),
            "the comping route emitted no thumb notes at all",
        )

    def test_the_texture_does_not_change_the_comping_arrangement(self):
        """The invariant that was broken, stated as one assertion over every texture.

        This is the test the defect made impossible to write. It is stronger than
        "they are all allowed" and stronger than comparing one texture against another:
        it says the texture cannot reach this decision **at all**, so a texture added to
        `TEXTURE_STYLES` later is covered without editing this test.
        """
        baseline = None
        for texture in TEXTURE_STYLES:
            if texture in MELODY_ONLY_TEXTURES:
                # These harmonise nothing and refuse a voice selection without the
                # soprano outright (`melody_allowed`), so they never reach this route.
                continue
            steps = self.comped(bass="walk", texture=texture)
            frets = [step.voicing.frets for step in steps]
            if baseline is None:
                baseline = (texture, frets)
                continue
            self.assertEqual(
                frets, baseline[1],
                f"texture={texture} changed the comping route; "
                f"texture={baseline[0]} is the reference",
            )

    def test_bass_none_is_still_honoured_on_this_route(self):
        """The fix removed a refusal, not the axis.

        Without this, "the thumb line now appears" and "the thumb line always appears"
        would be indistinguishable, and the second is the bug's mirror image.
        """
        steps = self.comped(bass="none", texture="uniform")
        self.assertTrue(all(step.bass is None for step in steps))

    def test_the_walked_beats_reach_the_part(self):
        """The union is built on this route now, so a walk invents its own beats.

        `_walking_slots` unions the melody grid with the walked beats. It was never
        called here, because the refusal made `has_thumb` False first - so this is the
        observable consequence of the fix rather than of the axis: a bar the melody
        barely visits still carries four quarters, and the part has more steps than the
        head had notes.

        **Compared against `bass=none` and not against a texture.** The first draft of
        this test compared `uniform` against `targets` and failed, which was the fix
        working: both now build the same union, because the texture no longer reaches
        the decision. A test asserting the texture *changes* the step count here would
        have pinned the bug.
        """
        walked = self.comped(bass="walk")
        silent = self.comped(bass="none")
        # Four written notes, and the walk adds the two beats the melody skips.
        self.assertEqual(len(silent), 4, "the head is four notes in one bar")
        self.assertEqual(len(walked), 6, "the walk should add the two empty beats")
        self.assertGreater(
            len(walked), len(silent),
            "a walking line adds no beats, so the walk is not being heard",
        )


class TestTheRefusal(unittest.TestCase):
    """A texture that harmonises nothing cannot also give the melody away."""

    def test_the_two_melody_only_textures_are_refused(self):
        """Derived from `MELODY_ONLY_TEXTURES`, not listed, so it cannot drift."""
        for texture in MELODY_ONLY_TEXTURES:
            allowed, reason = melody_allowed(texture, VOICES_NONE)
            self.assertFalse(allowed, texture)
            self.assertIn("voices='alto,tenor'", reason)

    def test_every_other_texture_is_allowed(self):
        """Measured across the tree: only those two fail."""
        for texture in TEXTURE_STYLES:
            allowed, _reason = melody_allowed(texture, VOICES_NONE)
            self.assertEqual(allowed, texture not in MELODY_ONLY_TEXTURES, texture)

    def test_a_selection_keeping_the_soprano_is_allowed_under_every_texture(self):
        """The refusal is about giving the melody away, not about the axis itself."""
        for texture in TEXTURE_STYLES:
            allowed, _reason = melody_allowed(texture, VOICES_ALL)
            self.assertTrue(allowed, texture)

    def test_a_refused_combination_warns_and_keeps_the_melody(self):
        """Refused rather than degraded: the arrangement still sounds."""
        diagnostics = Diagnostics()
        steps = VoiceLeadingEngine().arrange_progression(
            PROGRESSION, melody=VOICES_ARG, texture="melody", diagnostics=diagnostics
        )
        self.assertTrue(steps)
        self.assertTrue(all(step.melody_voiced for step in steps))
        self.assertTrue(diagnostics.warnings)

    def test_the_registry_is_keyed_by_the_spellings_parse_voices_accepts(self):
        """A policy row is a row `parse_voices` can be asked for, not a private name.

        `parse_voices` deliberately does **not** resolve `auto` - resolution is
        `resolve_voices`' job, and keeping the two apart is what lets a policy table be
        read without knowing the texture. So `auto` is the one key whose parsed value is
        the sentinel rather than the voices it stands for.
        """
        for key, voices in MELODY_POLICIES.items():
            if key == MELODY_AUTO:
                self.assertEqual(parse_voices(key), (MELODY_AUTO,))
            else:
                self.assertEqual(parse_voices(key), voices)
        self.assertEqual(MELODY_POLICIES[MELODY_AUTO], VOICES_ALL)

    def test_every_voice_name_the_library_uses_is_in_the_quartet(self):
        """So a policy row cannot name a voice a caller could not have typed."""
        for voices in MELODY_POLICIES.values():
            for name in voices:
                self.assertIn(name, VOICE_NAMES, name)


class TestParseVoices(unittest.TestCase):
    """The `--voices` argument surface: what a caller can actually write."""

    def test_the_order_a_caller_lists_them_in_does_not_matter(self):
        """`alto,tenor` and `tenor,alto` are one request, not two that happen to agree."""
        self.assertEqual(parse_voices("alto,tenor"), parse_voices("tenor,alto"))

    def test_the_result_is_always_highest_voice_first(self):
        """Canonical order, so a policy row and an argument can be compared directly."""
        self.assertEqual(
            parse_voices("bass,soprano"), (MELODY_SOPRANO, MELODY_BASS)
        )

    def test_none_is_the_two_middle_voices(self):
        """The ensemble shorthand, and the thing the README tells a user to type."""
        self.assertEqual(parse_voices("none"), VOICES_NONE)
        self.assertEqual(parse_voices(VOICES_ARG), parse_voices("none"))

    def test_whitespace_and_case_are_not_the_callers_problem(self):
        """A player types what they say."""
        self.assertEqual(parse_voices(" Soprano , ALTO "), (MELODY_SOPRANO, MELODY_ALTO))

    def test_a_repeated_voice_is_one_voice(self):
        """`alto,alto` is a slip, not a request for two altos."""
        self.assertEqual(parse_voices("alto,alto"), (MELODY_ALTO,))

    def test_every_single_voice_parses(self):
        """All four are nameable, which is what makes the axis an enumeration."""
        for name in VOICE_NAMES:
            self.assertEqual(parse_voices(name), (name,))

    def test_an_unknown_voice_raises(self):
        """A spelling nobody recognises is a question, not a voice to drop."""
        with self.assertRaises(ValueError):
            parse_voices("banjo")
        with self.assertRaises(ValueError):
            parse_voices("alto,banjo")

    def test_an_empty_selection_raises(self):
        """The guitar has to play something; silence is not an arrangement."""
        with self.assertRaises(ValueError):
            parse_voices("")

    def test_auto_cannot_be_mixed_with_named_voices(self):
        """`auto` means *all* of them, so it is a whole answer and not a part."""
        self.assertEqual(parse_voices("auto"), (MELODY_AUTO,))
        with self.assertRaises(ValueError):
            parse_voices("auto,alto")

    def test_resolve_voices_turns_auto_into_every_voice(self):
        """Which is what keeps the whole axis inert until a caller opts in."""
        self.assertEqual(
            resolve_voices((MELODY_AUTO,), "uniform", Diagnostics()), VOICES_ALL
        )

    def test_voices_have_soprano_is_the_one_predicate_that_matters(self):
        """Whether the tune is ours is what decides the engine's route."""
        self.assertTrue(voices_have_soprano(VOICES_ALL))
        self.assertFalse(voices_have_soprano(VOICES_NONE))
        self.assertTrue(voices_have_soprano((MELODY_SOPRANO, MELODY_BASS)))


class TestTheArityFollowsTheVoices(unittest.TestCase):
    """How many notes the part has is the length of the selection, not a constant.

    The first version of the generator always built a three-voice shell, so
    `--voices alto` and `--voices alto,tenor` both came back with three notes - the part
    sounding a voice nobody asked for, which in a band setting is a voice another player
    was supposed to have. This is the class that would catch that returning.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def counts_for(self, voices: str) -> List[int]:
        steps = self.engine.arrange_progression(PROGRESSION, melody=voices)
        self.assertTrue(steps, voices)
        return [len(step.voicing.active_frets()) for step in steps]

    def test_every_voice_count_produces_exactly_that_many_notes(self):
        """One note per named voice, for every selection that drops the soprano."""
        for voices, expected in (
            ("alto", 1),
            ("tenor", 1),
            ("alto,tenor", 2),
            ("tenor,bass", 2),
            ("alto,tenor,bass", 3),
        ):
            self.assertEqual(
                set(self.counts_for(voices)), {expected},
                f"{voices}: expected {expected} note(s) everywhere",
            )

    def test_two_voices_is_the_pair_the_original_ask_named(self):
        """`--voices alto,tenor` is two notes, and the default three is not it."""
        self.assertEqual(set(self.counts_for("alto,tenor")), {2})

    def test_one_voice_is_one_note(self):
        """A single note cannot sound both guide tones, and the warning says so.

        Measured: before `_shell_voicing` learned to keep one guide tone, `--voices alto`
        found no shape, warned on every step, and fell through to the melody-bearing
        route - handing the horn's line back to the guitarist, which is the opposite of
        what naming one voice asked for.
        """
        self.assertEqual(set(self.counts_for("alto")), {1})

    def test_a_selection_is_never_sounded_thicker_than_asked(self):
        """The direction that matters: no selection plays more voices than it named."""
        for voices in ("alto", "tenor", "bass", "alto,tenor", "tenor,bass", "none"):
            for count in self.counts_for(voices):
                self.assertLessEqual(
                    count, len(parse_voices(voices)), f"{voices} sounded {count} notes"
                )


class TestABassVoiceIsABassNote(unittest.TestCase):
    """`--voices bass` sounds a bass note: low, and a root or a 5th.

    Three defects, all measured on `tests/data/but_not_for_me.mxl` before this class
    existed, and all three had to be fixed together - which is why the tests are three
    and not one:

    - **The voice identity was discarded.** `steps` passed `notes=len(voices)`, so
      `alto`, `tenor` and `bass` - all three one-note selections - produced *identical*
      arrangements. Arity cannot tell a bass from a tenor; they ask for the same count.
    - **The low register was unreachable.** `_comping_string_sets(1)` offered only the
      *top* string of each `duo` pair - indices 5, 4 and 3, the high E, B and G - so all
      80 steps landed in the middle of the neck. Re-ranking cannot fix an unavailable
      position; the string sets had to change.
    - **The note was the 3rd.** One note keeps `SHELL_DEGREES[...][:1]`, which is the
      guide tone. For `Bb7` that is `D`, and a `D` in the bass is not a bass note - it
      sounds like the wrong chord, which is what `BASS_DEGREES_6432` says in as many
      words. So register alone would have produced a *low 3rd*, still wrong.

    Every assertion here is about the **bass** selection specifically. The inner voices
    must not move, and `test_an_inner_voice_is_untouched_by_this` says so.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def arrange(self, voices: str):
        return self.engine.arrange_progression(PROGRESSION, melody=voices)

    def test_the_three_one_note_selections_are_no_longer_the_same_arrangement(self):
        """The identity of the voice reaches the generator, not just its arity.

        The regression that started all three: one arity, three names, one arrangement.
        `bass` is compared against each inner voice *separately* rather than against a
        set, because a test that only asserted "they differ" would pass if `alto` and
        `tenor` had swapped places.
        """
        bass = format_progression(self.arrange("bass"))
        for inner in ("alto", "tenor"):
            self.assertNotEqual(
                bass,
                format_progression(self.arrange(inner)),
                f"--voices bass must not arrange like --voices {inner}",
            )

    def test_an_inner_voice_is_untouched_by_this(self):
        """And the fix is confined to the bass.

        `alto` and `tenor` remain one guide tone on the top of a `duo` pair, in the
        middle of the neck. They are guide tones under somebody else's melody, and the
        top of a duo pair is where a player puts one - which is the whole reason the
        register rule is a branch on the voice rather than a rule about single notes.
        """
        for inner in ("alto", "tenor"):
            for step in self.arrange(inner):
                self.assertEqual(len(step.voicing.active_frets()), 1)
                # The top of a duo pair: indices 5, 4 and 3 only, never the bottom three.
                self.assertGreater(
                    min(step.voicing.active_strings), 2, step.tab_line()
                )

    def test_an_inner_voice_still_sounds_a_guide_tone(self):
        """The other half of "untouched": the note is still the chord's 3rd.

        Asserted separately from the register above because a generator that moved an
        inner voice to a low string while leaving its degree alone would pass that one.
        """
        for inner in ("alto", "tenor"):
            for step in self.arrange(inner):
                canonical = ChordParser.canonical_quality(quality_of(step.chord))
                third = (root_of(step.chord) + SHELL_DEGREES[canonical][0]) % 12
                self.assertEqual(
                    {m % 12 for m in step.voicing.midi_notes()},
                    {third},
                    f"{inner}: {step.tab_line()} is no longer a guide tone",
                )

    def test_a_bass_voice_lies_in_the_low_register(self):
        """The strings are the bottom three, which is what "low register" means on a tab.

        Asserted on the **generator** as well as the arrangement, because the defect was
        in the generator's string sets and the arrangement is downstream of it: a fix
        that reordered the selector's preferences would pass a register test and leave the
        one-note shapes still unavailable down there.
        """
        for name in ("Cmaj7", "A7", "Dm7b5", "Bbmaj7", "Fmaj7", "G7"):
            for voicing in bass_comping(name):
                self.assertIn(
                    min(voicing.active_strings), (0, 1, 2), voicing.tab_string()
                )
        for step in self.arrange("bass"):
            self.assertLessEqual(min(step.voicing.active_strings), 2, step.tab_line())

    def test_a_bass_voice_sounds_a_root_or_a_fifth(self):
        """The degree rule `BASS_DEGREES_6432` already states, read from that table.

        Checked as root-or-5th rather than as "the root", because the rule is a
        preference: the 5th is a legitimate fallback where the root cannot be fretted in
        the window, and a test demanding the root would fail that case for being correct.
        """
        for name in ("Cmaj7", "A7", "Dm7b5", "Bbmaj7", "Fmaj7", "G7"):
            root = root_of(name)
            for voicing in bass_comping(name):
                self.assertIn(
                    {m % 12 for m in voicing.midi_notes()},
                    [{root % 12}, {(root + 7) % 12}],
                    f"{name} {voicing.tab_string()} is not a root or a 5th",
                )

    def test_the_root_is_preferred_over_the_fifth(self):
        """Where both are reachable, the root is the note that names the chord.

        Stated separately from the test above because "root or 5th" and "root, else 5th"
        are different rules and only one of them is implemented: a generator that
        accepted either in any order would pass the previous test.
        """
        for name in ("Cmaj7", "A7", "Dm7b5", "Bbmaj7", "F6", "G7sus4"):
            self.assertTrue(
                any(
                    {m % 12 for m in v.midi_notes()} == {root_of(name) % 12}
                    for v in bass_comping(name)
                ),
                f"{name} has no root candidate at all",
            )

    def test_a_bass_note_sounds_nothing_outside_the_chord(self):
        """The containment rule every other candidate makes, kept for this one too.

        This is the check that would catch the register fix being made at the cost of the
        degree rule, and the degree fix at the cost of the containment rule: a shape that
        reached the low strings by loosening `pcs <= allowed` would pass a register test
        and a root-or-5th test and still put a foreign note in the part.
        """
        for name in ("Cmaj7", "A7", "Dm7b5", "Bbmaj7", "F6", "G7sus4"):
            for voicing in bass_comping(name):
                self.assertLessEqual(
                    {m % 12 for m in voicing.midi_notes()},
                    chord_pcs(name),
                    f"{name} {voicing.tab_string()} sounds a wrong note",
                )

    def test_a_one_note_shape_is_now_a_supported_string_set(self):
        """The invariant, for the one shape that was silently outside it.

        `supported_string_sets()` listed no singletons, so **every** one-note comping
        shape the library could produce - `alto`, `tenor` and `bass` alike - violated
        "the sounding strings are exactly one supported set". Nothing caught it because
        the per-shape assertions in `tests/test_grips.py` never generated one. Asserting
        it here for the inner voices as well as the bass is what closes that: the fix
        added `SINGLE_NOTE_STRING_SETS` rather than leaving a shape outside the contract.
        """
        supported = {frozenset(s) for s in supported_string_sets()}
        for voices in ("alto", "tenor", "bass"):
            for step in self.arrange(voices):
                self.assertIn(
                    frozenset(step.voicing.active_strings),
                    supported,
                    f"{voices}: {step.tab_line()}",
                )

    def test_the_bass_voice_sits_under_the_inner_voices(self):
        """The band setting the axis exists for, as an ordering rather than a count.

        Asserted on sounding pitches because that is what "under" means, and because a
        fret-number comparison would not survive the octave transposition that moves the
        same pitch between strings.
        """
        inner = [max(s.voicing.midi_notes()) for s in self.arrange("alto,tenor")]
        bass = [max(s.voicing.midi_notes()) for s in self.arrange("bass")]
        self.assertEqual(len(inner), len(bass))
        self.assertLess(
            sum(bass), sum(inner), "the bass voice is not below the inner voices"
        )

    def test_the_flag_only_applies_to_the_bass_alone(self):
        """Two voices including the bass is a duo, and its string set is not re-decided.

        `bass_voice` is derived from `voices == (MELODY_BASS,)` in `steps`, so
        `tenor,bass` is not flagged. This asserts the arrangement that must not move,
        because moving it would be re-deciding a shape that is already correct: the
        lowest note of a duo belongs to the duo's string set.
        """
        for voices in ("tenor,bass", "alto,tenor,bass"):
            for step in self.arrange(voices):
                self.assertEqual(
                    len(step.voicing.active_frets()),
                    len(parse_voices(voices)),
                    f"{voices} changed arity",
                )

    def test_an_unreadable_chord_still_gets_no_bass_note(self):
        """No root, no claim - the same rule, on the branch that was added.

        A bass note is *more* dependent on the root than a guide-tone shape is, not less:
        it is the root or the 5th **of that root**, so a guessed one is not a weak claim,
        it is a wrong one. Asserted because the new branch reads `root_pc` directly, and a
        regression there would be silent rather than loud.
        """
        self.assertEqual(
            get_comping_voicings("maj7", None, notes=1, bass_voice=True), []
        )
        self.assertEqual(
            get_comping_voicings("maj7", "H7", notes=1, bass_voice=True), []
        )

    def test_the_default_generates_no_singletons_on_its_own(self):
        """`supported_string_sets()` grew; nothing else did.

        The singleton entries exist because a one-note shape needs them, and this asserts
        they are not a licence for some other grip to start sounding a single string by
        accident: the default arity still produces shells and nothing here is a shell set.

        `GRIP_STRING_SETS` stores each entry as `(strings, soprano)`, so the set is built
        from the first element of each pair - unpacking the pair itself would compare a
        `frozenset` against a 2-tuple and fail on the container rather than on the
        music, which is the failure mode this is here to rule out.
        """
        shell_sets = {
            frozenset(strings) for strings, _soprano in GRIP_STRING_SETS["shell"]
        }
        for name in ("Cmaj7", "A7", "Dm7b5"):
            for voicing in comping(name):
                self.assertEqual(
                    len(voicing.active_frets()),
                    3,
                    f"{name} {voicing.tab_string()} is no longer a three-voice shell",
                )
                self.assertIn(
                    frozenset(voicing.active_strings), shell_sets, voicing.tab_string()
                )


class TestRepeatedStepsHoldTheShape(unittest.TestCase):
    """The renderer rule the axis needs, and the reason it is stated in two places."""

    def test_a_repeat_re_strikes_the_soprano_when_the_guitar_sings(self):
        """The historical rule, unchanged: one note, inner voices held."""
        from tests.support import make_step

        cells = _step_cells(make_step([-1, -1, -1, 10, 12, 10], repeated=True))
        self.assertEqual(cells[5], "10")
        self.assertEqual(cells[3], _BLANK_CELL)
        self.assertEqual(cells[4], _BLANK_CELL)

    def test_a_repeat_holds_the_whole_shape_when_the_guitar_is_not_singing(self):
        """No soprano to re-strike, so nothing is struck anew.

        Measured over 2,243 corpus steps: 152 carry `repeated`, and keeping the old
        rule rendered every one as a single moving note - a melody line on the guitar
        part, on exactly the beats where the arrangement had handed the tune away.

        Compared against `_cells_from_frets` rather than a hand-written list, because
        the difference between a *muted* string ('x') and a *held* one (blank) is the
        library's, not this test's - and a literal here would re-state it wrongly.
        """
        from arranger.tuning import _cells_from_frets
        from tests.support import make_step

        step = make_step([-1, -1, -1, 10, 12, 10], repeated=True, melody_voiced=False)
        self.assertEqual(_step_cells(step), _cells_from_frets(step.voicing.frets))
        # And the three sounding strings are all struck, not just the top one.
        for string_index in (3, 4, 5):
            self.assertEqual(_step_cells(step)[string_index], str(step.voicing.frets[string_index]))

    def test_both_renderers_agree_on_what_strikes(self):
        """`render` and `tabstaff` must not disagree, or the staff lies about the tab."""
        from tabstaff import _strikes_here
        from tests.support import make_step

        step = make_step([-1, -1, -1, 10, 12, 10], repeated=True, melody_voiced=False)
        for string_index in range(6):
            self.assertTrue(
                _strikes_here(step, string_index),
                f"string {string_index}: the two renderers disagree",
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
        default = VoiceLeadingEngine.arrange_progression(PROGRESSION, melody=VOICES_ARG)
        explicit = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, melody=VOICES_ARG, harmony="auto"
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
        """
        by_keyword = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, melody=VOICES_ARG, harmony=HARMONY_SHELL_ROOT
        )
        by_options = VoiceLeadingEngine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(melody=VOICES_ARG, harmony=HARMONY_SHELL_ROOT),
        )
        self.assertEqual(
            [s.voicing.frets for s in by_keyword],
            [s.voicing.frets for s in by_options],
        )

    def test_the_default_is_the_sentinel_and_resolves_to_guide(self):
        """`ArrangeOptions().harmony` is `auto`, and `auto` resolves to `guide`.

        Asserted separately because the two spellings are load-bearing in different
        places: the field must match `arrange_progression`'s keyword default for the
        comparison above to mean anything, and the policy must resolve to the shipped
        behaviour for the arrangement to be unchanged.
        """
        self.assertEqual(ArrangeOptions().harmony, HARMONY_AUTO)
        self.assertEqual(HARMONY_POLICIES[HARMONY_AUTO], HARMONY_GUIDE)

    def test_the_axis_is_inert_when_the_guitar_is_singing(self):
        """`harmony=` changes nothing on an arrangement that voices the melody.

        The comping generator is only reached when `melody_voiced` is False, so every
        value must produce the same singing arrangement - otherwise the axis would be
        answering a question that was never asked of it.
        """
        arrangements = [
            [s.voicing.frets for s in VoiceLeadingEngine.arrange_progression(
                PROGRESSION, harmony=value
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

        The claim `docs/comping-styles.md` §4.1 makes about this family, asserted here
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
        degrading is the rule `melody_allowed` and `bass_allowed` both follow.
        """
        self.assertTrue(harmony_allowed(HARMONY_SHELL_ROOT, ("alto", "tenor", "bass"))[0])
        self.assertFalse(harmony_allowed(HARMONY_SHELL_ROOT, ("alto", "tenor"))[0])
        self.assertTrue(harmony_allowed(HARMONY_ROOT, ("bass",))[0])
        self.assertFalse(harmony_allowed(HARMONY_ROOT, ("alto", "tenor"))[0])

    def test_a_refused_combination_warns_and_keeps_the_guide_tones(self):
        """The warning names what would work, and the output is the inert answer.

        Asserted on the output as well as the warning, because a refusal that warned
        and then produced something else would be the worse of the two failures.
        """
        diagnostics = Diagnostics()
        collected: List[str] = []
        diagnostics.emit = collected.append  # type: ignore[method-assign]
        steps = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, melody=VOICES_ARG, harmony=HARMONY_SHELL_ROOT,
            diagnostics=diagnostics,
        )
        self.assertTrue(
            any(HARMONY_SHELL_ROOT in w for w in collected),
            f"no warning names the refused family: {collected}",
        )
        reference = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, melody=VOICES_ARG
        )
        self.assertEqual(
            [s.voicing.frets for s in steps],
            [s.voicing.frets for s in reference],
            "a refused family changed the arrangement",
        )

    def test_an_unknown_family_is_reported_even_on_a_singing_arrangement(self):
        """Resolution happens up front, so a typo is never silently ignored.

        The comping route is not reached when the guitar sings, so resolving inside
        that branch would mean `harmony=bogus` on a default arrangement reported
        nothing at all - and the same argument `_resolve_melody` is resolved for.
        """
        with self.assertRaises(ValueError):
            VoiceLeadingEngine.arrange_progression(PROGRESSION, harmony="nonsense")

    def test_root_names_the_lowest_note_of_the_chord(self):
        """`harmony=root` is a bass voice, so it needs the bass selection and nothing else.

        The one family that is exactly the behaviour of a lone `--voices bass`, which
        is why `harmony_allowed` derives rather than lists it: a family naming the bass
        voice alone cannot be voiced by a selection asking for two notes.
        """
        for name in ("Ebmaj", "Bb7", "Cm7"):
            allowed, _reason = harmony_allowed(HARMONY_ROOT, ("bass",))
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

if __name__ == "__main__":
    unittest.main()


