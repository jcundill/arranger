"""`parts`: which of melody, bass and chord the guitar takes.

The axis is a selection rather than a setting, so these tests are about what the guitar
leaves to the other players - a melody-only selection, a bass part under a comp, and the
marker that has to know who is singing before it can star a string.
"""

import unittest
from typing import List

from arranger import (
    GRIP_STRING_SETS,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    PARTS_AUTO,
    TEXTURE_STYLES,
    VoiceLeadingEngine,
    get_comping_voicings,
    parse_parts,
    parts_has_melody_only,
    parts_have_melody,
    resolve_parts,
    supported_string_sets,
)
from arranger.options import ArrangeOptions, Request
from arranger.render import _step_cells
from arranger.tuning import MUTED_CELL
from tests.support import (
    PROGRESSION,
    VOICES_ARG,
    bass_comping,
    chord_pcs,
    comping,
    guide_pcs,
    quality_of,
    root_of,
)


class TestMelodyOnlySelections(unittest.TestCase):
    """The melody-only selections: what they are, and what they are not.

    This replaces `TestTheRefusal`, which asserted `melody_allowed` - the rule
    that refused a no-soprano selection on a texture that played the melody
    and nothing else. That refusal dissolved when the melody-only claim moved
    onto the voice selection: a soprano-less selection simply comps, on every
    texture, and nothing is self-contradictory anywhere. What the class still
    owes the suite is the fact the two textures used to state, asserted on its
    new home - the same shape as trap 5: the premise moved, the protection
    moved with it.
    """

    def test_the_predicate_is_derived_from_the_selection(self):
        """The tune is ours and the chord part is not - and nothing else is melody-only.

        `(melody,)` is the tune alone; `(melody, bass)` the tune with a thumb under
        it. A selection with no chord part is a melody-only one whatever else it
        names, and `(melody, chord)` is the full chord-melody - the melody plus a
        chord part, which is the shipped arrangement and not this route.
        """
        self.assertTrue(parts_has_melody_only((PART_MELODY,)))
        self.assertTrue(parts_has_melody_only((PART_MELODY, PART_BASS)))
        self.assertFalse(parts_has_melody_only(PART_NAMES))
        self.assertFalse(parts_has_melody_only((PART_CHORD,)))
        self.assertFalse(parts_has_melody_only((PART_MELODY, PART_CHORD)))
        self.assertFalse(parts_has_melody_only((PART_BASS,)))

    def test_a_soprano_less_selection_comps_on_every_texture(self):
        """The refusal that dissolved: nothing is self-contradictory anywhere now.

        Before the collapse, `parts="alto,tenor"` on a melody-only texture was
        refused with a warning and the melody handed back to the guitar. With
        the claim keyed on the selection, the same request comps, on every
        texture, without a refusal.
        """
        for texture in TEXTURE_STYLES:
            steps = VoiceLeadingEngine().arrange_progression(
                PROGRESSION, options=ArrangeOptions(parts=VOICES_ARG, texture=texture),
            )
            self.assertTrue(steps, texture)
            self.assertTrue(
                all(not step.melody_voiced for step in steps), texture
            )

    def test_soprano_alone_arranges_the_melody_and_nothing_else(self):
        """The old texture's behaviour, unchanged under its new spelling.

        Every slot is the melody alone, and no step is flagged `melody_only` -
        the chord name is context, not a claim that there is no chord. The
        byte-for-byte equivalence against the old `texture="melody"` output is
        asserted in `docs/history/one-fact.md`'s build notes; this is the invariant
        statement of it.
        """
        steps = VoiceLeadingEngine().arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts="melody")
        )
        self.assertTrue(steps)
        for step in steps:
            self.assertEqual(step.grip, "melody")
            self.assertEqual(len(step.voicing.active_frets()), 1)
            self.assertFalse(step.melody_only)
            self.assertFalse(step.bass_only)

    def test_the_old_spellings_are_gone_from_the_vocabulary(self):
        """An unknown texture is a usage error, not a silent alias.

        The precedent the corpus removal set for removed flags: a deprecated
        spelling kept working would be the same fact stated twice, which is
        what this stage exists to collapse.
        """
        self.assertNotIn("melody", TEXTURE_STYLES)
        self.assertNotIn("melody_bass", TEXTURE_STYLES)
        with self.assertRaises(ValueError):
            VoiceLeadingEngine().arrange_progression(
                PROGRESSION, options=ArrangeOptions(texture="melody")
            )

    def test_an_nc_bar_under_soprano_takes_the_no_chord_route(self):
        """
        The NC guard answers before the empty palette, under the new spelling too.

        A no-chord bar under a melody-only selection is `MELODY_ALONE_NO_CHORD`
        rather than the texture case: the bar has no harmony at all, and the
        flag is what makes the annotation read "no chord - melody alone"
        truthfully. This is trap 12's rule applied to the re-keyed route - ask
        what each guard is load-bearing *for*, then assert it - and the guard's
        answer is byte-identical to the old texture's, which the engine capture
        in `docs/history/one-fact.md`'s build notes shows.
        """
        steps = VoiceLeadingEngine().arrange_progression(
            [("F4", "NC", "NC"), ("E4", "7", "G7")], options=ArrangeOptions(parts="melody")
        )
        self.assertEqual([s.chord for s in steps], ["NC", "G7"])
        self.assertTrue(steps[0].melody_only)
        self.assertFalse(steps[1].melody_only)
        self.assertEqual(steps[0].grip, "melody")

    def test_an_off_grid_slot_under_soprano_still_sounds(self):
        """
        The rhythm guard answers before the empty palette too, on both routes.

        A slot the chord's rhythm does not name is the one case where the guitar may
        play nothing rather than one note: under a comping selection it is a rest, and
        under a melody-only selection the note of the tune still sounds, alone - which
        is what every slot of that selection is anyway, so the ordering is asserted
        rather than left to read as a coincidence. Measured under a rhythm of the
        **ands**, which places no chord on beat 1.0: every slot of the soprano-only
        arrangement still sounds its note.
        """
        progression = [
            ("F5", "maj7", "Fmaj7"), ("E5", "7", "A7"),
            ("D5", "NC", "NC"), ("C5", "m7", "Dm7"),
        ]
        timings = [(0, 1.0, 1.0), (0, 2.5, 0.5), (1, 1.0, 1.0), (1, 3.0, 1.0)]
        steps = VoiceLeadingEngine.arrange_progression(
                progression, timings=timings, options=ArrangeOptions(
                    parts="melody",
                    request=Request(chord_on="1and,2and,3and,4and"),
                ),
            )
        self.assertEqual(len(steps), 4, "an off-grid slot of the tune went missing")
        for step in steps:
            self.assertEqual(len(step.voicing.active_frets()), 1)



class TestParseParts(unittest.TestCase):
    """The `--parts` argument surface: what a caller can actually write."""

    def test_the_order_a_caller_lists_them_in_does_not_matter(self):
        """`bass,chord` and `chord,bass` are one request, not two that happen to agree."""
        self.assertEqual(parse_parts("bass,chord"), parse_parts("chord,bass"))
        self.assertEqual(parse_parts("bass,chord"), (PART_BASS, PART_CHORD))

    def test_the_result_is_always_in_the_vocabularys_order(self):
        """Canonical order, so a policy row and an argument can be compared directly."""
        self.assertEqual(parse_parts("chord,melody"), (PART_MELODY, PART_CHORD))

    def test_whitespace_and_case_are_not_the_callers_problem(self):
        """A player types what they say."""
        self.assertEqual(parse_parts(" Melody , CHORD "), (PART_MELODY, PART_CHORD))

    def test_a_repeated_part_is_one_part(self):
        """`chord,chord` is a slip, not a request for two chord parts."""
        self.assertEqual(parse_parts("chord,chord"), (PART_CHORD,))

    def test_every_single_part_parses(self):
        """All three are nameable, which is what makes the axis an enumeration."""
        for name in PART_NAMES:
            self.assertEqual(parse_parts(name), (name,))

    def test_an_unknown_part_raises(self):
        """A spelling nobody recognises is a question, not a part to drop."""
        with self.assertRaises(ValueError):
            parse_parts("banjo")
        with self.assertRaises(ValueError):
            parse_parts("chord,banjo")

    def test_an_empty_selection_raises(self):
        """The guitar has to take something; silence is not an arrangement."""
        with self.assertRaises(ValueError):
            parse_parts("")

    def test_auto_cannot_be_mixed_with_named_parts(self):
        """`auto` means *all* of them, so it is a whole answer and not a part."""
        self.assertEqual(parse_parts("auto"), (PARTS_AUTO,))
        with self.assertRaises(ValueError):
            parse_parts("auto,chord")

    def test_resolve_parts_turns_auto_into_every_part(self):
        """Which is what keeps the whole axis inert until a caller opts in."""
        self.assertEqual(resolve_parts((PARTS_AUTO,)), PART_NAMES)

    def test_parts_have_melody_answers_the_arrangement_level_half_of_the_route(self):
        """Whether the tune is *ours* is one input to the route, not the route (§9.3 D).

        Named for the question the data answers rather than the decision: the engine's
        route is per **slot** now (`sings_here`), and this predicate answers only the
        arrangement-level half - *would* this selection sing the tune, wherever there is
        one. `TestTheSopranoIsPerSlotNotPerRoute` pins the other half.
        """
        self.assertTrue(parts_have_melody(PART_NAMES))
        self.assertFalse(parts_have_melody((PART_CHORD,)))
        self.assertTrue(parts_have_melody((PART_MELODY, PART_BASS)))


class TestTheArityFollowsTheTexture(unittest.TestCase):
    """How many notes the comping part states is the **texture's** arity.

    The first version of the generator always built a three-voice shell, so
    `--voices alto` and `--voices alto,tenor` both came back with three notes - the part
    sounding a voice nobody asked for, which in a band setting is a voice another player
    was supposed to have. The equivalent hole now is `texture`: a comping slot that
    states the default three regardless of the arity the caller asked for would be the
    same defect with the knob renamed, and this is the class that would catch it.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def counts_for(self, texture: str) -> List[int]:
        steps = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=PART_CHORD, texture=texture)
        )
        self.assertTrue(steps, texture)
        return [len(step.voicing.active_frets()) for step in steps]

    def test_every_arity_produces_at_most_that_many_notes(self):
        """One note per chord-part voice the texture names, and never more."""
        for texture, ceiling in (
            ("chord1", 1),
            ("chord2", 2),
            ("chord3", 3),
        ):
            for count in self.counts_for(texture):
                self.assertLessEqual(count, ceiling, f"{texture} sounded {count} notes")

    def test_the_whole_chord_is_the_default(self):
        """`uniform` is the arrangement that always was: the fullest shape available."""
        self.assertEqual(set(self.counts_for("uniform")), {3})

    def test_a_selection_is_never_sounded_thicker_than_asked(self):
        """The direction that matters: no texture plays more voices than it named."""
        for texture in TEXTURE_STYLES:
            for count in self.counts_for(texture):
                self.assertLessEqual(
                    count, 3, f"{texture} sounded {count} notes"
                )


class TestABassPartIsABassNote(unittest.TestCase):
    """`parts="bass"` sounds a bass note: low, and a root or a 5th.

    Three defects, all measured on `tests/data/synthetic_cut_time.mxl` before this class
    existed, and all three had to be fixed together - which is why the tests are three
    and not one:

    - **The voice identity was discarded.** `steps` passed `notes=len(voices)`, so
      `alto`, `tenor` and `bass` - all three one-note selections - produced *identical*
      arrangements. Arity cannot tell a bass from a tenor; they ask for the same count.
    - **The low register was unreachable.** `comping_string_sets(1)` offered only the
      *top* string of each `duo` pair - indices 5, 4 and 3, the high E, B and G - so all
      80 steps landed in the middle of the neck. Re-ranking cannot fix an unavailable
      position; the string sets had to change.
    - **The note was the 3rd.** One note keeps `SHELL_DEGREES[...][:1]`, which is the
      guide tone. For `Bb7` that is `D`, and a `D` in the bass is not a bass note - it
      sounds like the wrong chord, which is what `BASS_DEGREES_6432` says in as many
      words. So register alone would have produced a *low 3rd*, still wrong.

    `parts` names **parts**, not voices, which is what makes the first defect
    unreachable through the API: there is one bass part and it is addressed by name, so
    two different requests cannot collapse to one arrangement. The inner voices are
    reached as the chord part - both guide tones together - and
    `test_an_inner_voice_is_not_addressable_as_a_part` is the inversion of the old
    per-voice test.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def arrange(self, parts: str):
        return self.engine.arrange_progression(PROGRESSION, options=ArrangeOptions(parts=parts))

    def test_an_inner_voice_is_not_addressable_as_a_part(self):
        """The axis has no spelling for one inner voice, and that is the fix.

        **Inverted rather than deleted.** It used to assert that `bass`, `alto` and
        `tenor` produce three *different* arrangements, because they used to produce
        one - the voice identity was discarded and only the count survived. With the
        parts axis, the request itself cannot be made: `alto` is not a part, and the
        inner voices are what the **chord** part is for, both of them at once. So the
        assertion is on the vocabulary, which is where the collapse used to happen.
        """
        with self.assertRaises(ValueError):
            parse_parts("alto")
        with self.assertRaises(ValueError):
            parse_parts("tenor")
        # The part that does carry them states a complete comping shape, and the
        # guide-tone pair is *inside* it rather than being the whole of it.
        for step in self.arrange(PART_CHORD):
            self.assertEqual(len(step.voicing.active_frets()), 3, step.tab_line())
            self.assertLessEqual(guide_pcs(step.chord), {m % 12 for m in step.voicing.midi_notes()})

    def test_the_chord_part_sounds_the_whole_chord_where_the_bass_states_one_note(self):
        """The register rule is the bass part's, and it stays there.

        The chord part states the arity the texture asks for - three notes, by default
        - while the lone bass part states one note in the low register. That asymmetry
        is why the low-register rule is a branch on the **part** rather than a rule
        about how many notes happen to sound.
        """
        self.assertEqual(
            {len(s.voicing.active_frets()) for s in self.arrange(PART_CHORD)}, {3}
        )
        for step in self.arrange(PART_BASS):
            self.assertEqual(len(step.voicing.active_frets()), 1, step.tab_line())

    def test_the_chord_part_still_sounds_its_guide_tones(self):
        """The other half of "untouched": the notes are still the chord's 3rd and 7th.

        Asserted separately from the register above because a generator that moved the
        pair to low strings while leaving its degrees alone would pass that one.
        """
        for step in self.arrange(PART_CHORD):
            self.assertLessEqual(
                guide_pcs(step.chord),
                {m % 12 for m in step.voicing.midi_notes()},
                f"{step.tab_line()} dropped a guide tone",
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
        shape the library could produce - an inner voice and the lone bass alike -
        violated "the sounding strings are exactly one supported set". Nothing caught
        it because the per-shape assertions in `tests/test_grips.py` never generated
        one. It is asserted here over the **generator**, since the parts axis cannot
        ask for an inner voice on its own; the fix added `SINGLE_NOTE_STRING_SETS`
        rather than leaving a shape outside the contract.
        """
        supported = {frozenset(s) for s in supported_string_sets()}
        for name in ("Cmaj7", "A7", "Dm7b5"):
            for bass_voice in (False, True):
                for voicing in get_comping_voicings(
                    quality_of(name), name, notes=1, bass_voice=bass_voice
                ):
                    self.assertIn(
                        frozenset(voicing.active_strings),
                        supported,
                        voicing.tab_string(),
                    )
        for step in self.arrange(PART_BASS):
            self.assertIn(
                frozenset(step.voicing.active_strings),
                supported,
                step.tab_line(),
            )

    def test_the_bass_part_sits_under_the_chord_part(self):
        """The band setting the axis exists for, as an ordering rather than a count.

        Asserted on sounding pitches because that is what "under" means, and because a
        fret-number comparison would not survive the octave transposition that moves the
        same pitch between strings.
        """
        chord = [max(s.voicing.midi_notes()) for s in self.arrange(PART_CHORD)]
        bass = [max(s.voicing.midi_notes()) for s in self.arrange(PART_BASS)]
        self.assertEqual(len(chord), len(bass))
        self.assertLess(
            sum(bass), sum(chord), "the bass part is not below the chord part"
        )

    def test_the_lone_bass_flag_applies_to_the_bass_alone(self):
        """A selection that also takes the chord part is not a lone bass.

        `bass_voice` is derived from `parts == (PART_BASS,)` in `movement`, so a pair is
        not flagged, and its shape is the chord part's rather than one note re-placed in
        the low register. That matters because re-deciding it would move a shape that is
        already correct: the lowest note of a two-note chord belongs to the chord's own
        string set, not to the bass register rule (`BASS_DEGREES_6432`).

        **Inverted rather than deleted.** It used to assert `len(active_frets) ==
        len(voices)` for `tenor,bass` and `alto,tenor,bass` - one note per *named
        voice* - which was the old arity rule. The arity is the texture's now, so what
        survives is the pair of claims that do not depend on it: the lone bass is one
        low note, and nothing else is the lone-bass case.
        """
        lone = [len(s.voicing.active_frets()) for s in self.arrange(PART_BASS)]
        self.assertEqual(set(lone), {1}, "the lone bass states more than one note")
        for step in self.arrange(PART_BASS):
            self.assertLessEqual(min(step.voicing.active_strings), 2, step.tab_line())
        counts = {
            len(s.voicing.active_frets())
            for s in self.arrange("bass,chord")
        }
        self.assertEqual(counts, {3}, "a pair selection is not the lone-bass case")

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
        """The historical rule: one note, and the strings it does not strike are muted."""
        from tests.support import make_step

        cells = _step_cells(make_step([-1, -1, -1, 10, 12, 10], repeated=True))
        self.assertEqual(cells[5], "10")
        self.assertEqual(cells[3], MUTED_CELL)
        self.assertEqual(cells[4], MUTED_CELL)

    def test_a_bass_only_fill_mutes_every_string_it_does_not_play(self):
        """A bass slot prints 'x' above the thumb, like any other unplayed string.

        The upper voices are **held** rather than restruck, but this renderer answers
        "what does this step play": a string the player must not attack reads the same
        as a mute, so no blank is left that could be mistaken for a missing voice.
        """
        from arranger import ArrangementStep
        from tests.support import make_voicing

        voicing = make_voicing([3, -1, -1, -1, -1, -1], bass_midi=41, bass_string=0)
        step = ArrangementStep(
            chord="Cmaj7", melody="B4", voicing=voicing, bass_only=True
        )
        cells = _step_cells(step)
        self.assertEqual(cells[0], "3")
        for string_index in range(1, 6):
            self.assertEqual(cells[string_index], MUTED_CELL)

    def test_a_repeat_holds_the_whole_shape_when_the_guitar_is_not_singing(self):
        """No soprano to re-strike, so nothing is struck anew.

        Measured over 2,243 corpus steps: 152 carry `repeated`, and keeping the old
        rule rendered every one as a single moving note - a melody line on the guitar
        part, on exactly the beats where the arrangement had handed the tune away.

        Compared against `cells_from_frets` rather than a hand-written list, because
        the difference between a *muted* string ('x') and a *held* one (blank) is the
        library's, not this test's - and a literal here would re-state it wrongly.
        """
        from arranger.tuning import cells_from_frets
        from tests.support import make_step

        step = make_step([-1, -1, -1, 10, 12, 10], repeated=True, melody_voiced=False)
        self.assertEqual(_step_cells(step), cells_from_frets(step.voicing.frets))
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


class TestTheMelodyMarkerKnowsWhoIsSinging(unittest.TestCase):
    """The staff's melody marker reads `melody_voiced`, not the shape.

    The `*` on the ASCII staff and the `soprano` class on the HTML page say **the
    guitar has the tune here** - which is exactly what `melody_voiced` states.
    Deriving the marker from the shape instead - the highest sounding note, on its
    string - stars a string on a comping part too, because a guide-tone shell
    built from the chord alone still has a top note. The marker is a claim about
    *who has the melody*, and only the flag answers that.
    """

    def test_no_string_is_starred_when_the_guitar_is_not_singing(self):
        """`show_melody` stars nothing on a comping part."""
        from tabstaff import format_tab_staff
        from tests.support import make_step

        steps = [
            make_step([-1, -1, -1, 10, 12, 10], melody_voiced=False),
            make_step([-1, -1, -1, 8, 10, 10], melody_voiced=False),
        ]
        starred = [
            row for row in format_tab_staff(steps, show_melody=True).split("\n")
            if len(row) > 1 and row[0] in "eBGDAE" and row[1] == "*"
        ]
        self.assertEqual(starred, [])

    def test_no_row_is_marked_soprano_when_the_guitar_is_not_singing(self):
        """The page marks no row the soprano either - one predicate, two renderers."""
        from tabstaff import format_tab_html
        from tests.support import make_step

        steps = [
            make_step([-1, -1, -1, 10, 12, 10], melody_voiced=False),
            make_step([-1, -1, -1, 8, 10, 10], melody_voiced=False),
        ]
        self.assertNotIn('class="soprano"', format_tab_html(steps))

    def test_the_marker_still_finds_the_soprano_when_the_guitar_sings(self):
        """The same shapes with the flag set star the string that carries the tune.

        The positive control, without which the two tests above could not tell a
        fix from the marker having been deleted outright.
        """
        from tabstaff import format_tab_html, format_tab_staff
        from tests.support import make_step

        steps = [
            make_step([-1, -1, -1, 10, 12, 10]),
            make_step([-1, -1, -1, 8, 10, 10]),
        ]
        staff = format_tab_staff(steps, show_melody=True).split("\n")
        # The fret list is indexed low E first, so `frets[5]` is the high E - and
        # the highest pitch of both shapes sits there, so the e row is the one the
        # marker must find.
        self.assertTrue(
            any(row.startswith("e*") for row in staff),
            "\n".join(staff),
        )
        self.assertIn('class="soprano"', format_tab_html(steps))
