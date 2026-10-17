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
  singing, instead of re-striking a soprano that is not there, and the melody marker
  stars no string on a part that is not singing;
"""

import unittest
from typing import List, Optional, Tuple

from musthe import Note

from arranger import (
    BASS_DEGREES_6432,
    GRID_PART_PATTERNS,
    GRIP_MAX_SPAN,
    GRIP_STRING_SETS,
    HARMONY_AUTO,
    HARMONY_AUTO_POLICIES,
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_SHELL_ROOT,
    HARMONY_STYLES,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    PARTS_AUTO,
    SHELL_DEGREES,
    TEXTURE_STYLES,
    ChordParser,
    VoiceLeadingEngine,
    format_progression,
    get_comping_voicings,
    harmony_allowed,
    parse_harmony,
    parse_parts,
    parts_has_melody_only,
    parts_have_melody,
    resolve_parts,
    supported_string_sets,
)
from arranger.grips import (
    _comping_palette,
    _comping_string_sets,
    _search_comping_voicings,
    _snapshot,
)
from arranger.options import ArrangeOptions
from arranger.render import _step_cells
from arranger.tuning import _MUTED_CELL

PROGRESSION: List[Tuple[str, str, str]] = [
    ("D5", "m7", "Dm7"),
    ("C5", "maj7", "Cmaj7"),
    ("A4", "7", "A7"),
    ("G4", "maj7", "Gmaj7"),
]

# The two selections these tests are about, spelled **the way a caller passes them**,
# because that is the surface `voices` actually has. `VOICES_NONE` and `PART_NAMES` are the
# same data as canonical tuples; these are the strings, and the tests would not catch a
# parser that could not read what its own documentation tells a user to type.
VOICES_ARG = "chord"

# The comping part **with** the thumb line, which is a different selection rather
# than a different setting: a bass style is a claim about the bass part, so a
# caller asking for a line has to take that part.
PARTS_WITH_BASS = "bass,chord"
PART_NAMES_ARG = "auto"


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


class TestTheCompingPaletteIsRemembered(unittest.TestCase):
    """`_search_comping_voicings` is answered through `_comping_palette`; the answer may not move.

    An invisible memo stops being invisible in the same three ways the placement memo
    does (`tests/test_placement.py` holds that one to them), and each has an assertion
    here: an answer that differs from the enumeration's, a caller's write reaching the
    next caller, and a memo that is never read - which would leave every other test in
    this file passing while the engine paid for a cache it never used.
    """

    #: Representative requests rather than the whole parameter space, because the
    #: *enumeration* is the expensive half and this is the one test that has to run it
    #: bypassing the memo. Every other test in this file, and every pinned corpus tab in
    #: the suite, reads the memo.
    CASES: List[Tuple[str, str]] = [
        ("maj7", "Cmaj7"),
        ("m7", "Dm7"),
        ("7", "A7"),
        ("9", "C9"),
        ("m7b5", "Bm7b5"),
        ("dim7", "Bdim7"),
    ]

    def setUp(self):
        # These assertions are about the *entry point*, so the memo starts empty and no
        # test here inherits another's entries.
        _comping_palette.cache_clear()

    def test_the_memo_answers_what_the_enumeration_answers(self):
        """One request asked both ways: what the memo stores *is* the search's answer.

        Compared as snapshots rather than as tabs, so a rebuilt `Voicing` cannot hide a
        field the memo dropped - `top_fret`, `avg_fret`, `role` and the bass fields all
        come out of it.
        """
        checked = 0
        for quality, name in self.CASES:
            for notes in (1, 3):
                for bass_voice in (False, True):
                    for shell_root in (False, True):
                        searched = _search_comping_voicings(
                            quality,
                            name,
                            notes=notes,
                            bass_voice=bass_voice,
                            shell_root=shell_root,
                        )
                        remembered = _comping_palette(
                            quality,
                            name,
                            NECK_FRET_MIN,
                            NECK_FRET_MAX,
                            notes,
                            bass_voice,
                            shell_root,
                        )
                        self.assertEqual(
                            [_snapshot(voicing) for voicing in searched],
                            list(remembered),
                            f"{name} notes={notes} bass_voice={bass_voice} "
                            f"shell_root={shell_root}",
                        )
                        checked += 1
        self.assertGreater(checked, 20, "the memo was compared over almost nothing")

    def test_a_caller_writing_into_its_shape_does_not_reach_the_next_caller(self):
        """The memo may not hand one object out twice, because the engine writes into it.

        The comping route is where this bites hardest: `decisions.select_step_voicing`
        returns one of the palette's **own objects**, and `bass_merge.attach_bass` then
        merges the walked thumb into its fret vector and `bass_pc`. A shared object would
        let one step's bass line become the next step's palette, silently and only in the
        tab, so the identity assertion is the witness: it is the *sharing* that is
        forbidden, not the equality of the two answers.
        """
        first = get_comping_voicings("maj7", "Cmaj7")
        second = get_comping_voicings("maj7", "Cmaj7")
        self.assertTrue(first)
        self.assertIsNot(first, second, "the memo handed one list out twice")
        self.assertIsNot(first[0], second[0], "the memo handed one object out twice")
        pristine_tab = first[0].tab_string()
        pristine_bass = first[0].bass_pc
        # Exactly what `attach_bass` does, down to the string: the thumb takes a string
        # the shape left muted and writes its fret there.
        muted = [index for index, fret in enumerate(first[0].frets) if fret < 0]
        self.assertTrue(muted, "no muted string for the thumb note to be written onto")
        first[0].frets[muted[0]] = 7
        first[0].bass_pc = None if pristine_bass is None else (pristine_bass + 1) % 12

        third = get_comping_voicings("maj7", "Cmaj7")
        self.assertEqual(third[0].tab_string(), pristine_tab)
        self.assertEqual(third[0].bass_pc, pristine_bass)

    def test_the_memo_is_read_rather_than_bypassed(self):
        """A memo nothing hits is a claim with no effect - an invisible knob.

        Pinned as a *count* rather than as a timing, because the second call being fast
        is exactly what a reader cannot see from the code.
        """
        before = _comping_palette.cache_info()
        get_comping_voicings("m7", "Dm7")
        after_first = _comping_palette.cache_info()
        get_comping_voicings("m7", "Dm7")
        after_second = _comping_palette.cache_info()
        self.assertEqual(after_first.misses - before.misses, 1)
        self.assertEqual(after_first.hits - before.hits, 0)
        self.assertEqual(after_second.misses - after_first.misses, 0)
        self.assertEqual(after_second.hits - after_first.hits, 1)

    def test_clearing_the_memo_runs_the_enumeration_again(self):
        """The seam the checks above need, and the one a changed table would need.

        After `cache_clear` the enumeration runs and the same shapes come back, which is
        what makes "the search is still the thing under test" a fact about this file
        rather than a hope.
        """
        first = get_comping_voicings("7", "A7")
        self.assertGreater(_comping_palette.cache_info().currsize, 0)
        _comping_palette.cache_clear()
        self.assertEqual(_comping_palette.cache_info().currsize, 0)
        self.assertEqual(
            [voicing.tab_string() for voicing in get_comping_voicings("7", "A7")],
            [voicing.tab_string() for voicing in first],
        )


class TestTheAxisIsInertByDefault(unittest.TestCase):
    """`voices=auto` and `voices=guitar` are the arrangement that always was."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_auto_and_guitar_agree_with_each_other(self):
        """The sentinel resolves to the same arrangement as saying so."""
        auto = self.engine.arrange_progression(PROGRESSION)
        explicit = self.engine.arrange_progression(PROGRESSION, parts=PART_NAMES_ARG)
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
        by_keyword = self.engine.arrange_progression(PROGRESSION, parts=VOICES_ARG)
        by_option = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=VOICES_ARG)
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
                PROGRESSION, parts=VOICES_ARG, options=ArrangeOptions()
            )

    def test_an_unknown_policy_raises(self):
        """A spelling nobody recognises is a question, not something to default."""
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(PROGRESSION, parts="banjo")


class TestTheCompingArrangement(unittest.TestCase):
    """`parts=bass,chord` through the engine: what the guitarist is handed."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 3.0, 1.0), (0, 4.0, 1.0)]

    def comped(self, **kwargs):
        # `bass,chord`: the thumb line is the **bass part**, and a bass style is
        # refused without it ("add 'bass' to parts"). The arity is unaffected -
        # `comping_arity` reads the chord part and the hand, not how many parts are
        # named - so the shapes are the same as a chord-only selection's.
        steps = self.engine.arrange_progression(
            PROGRESSION, parts=PARTS_WITH_BASS, **kwargs
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

        Checked over the corpus, where the stronger per-step claim fails. The sets are
        the **comping** ones - the same `_comping_string_sets` the generator builds
        from - because the comping part is not a truncated grip palette: `(0, 2)` is a
        pair no `supported_string_sets()` entry lists, and truncating a shell set is
        how it would get into the tab.
        """
        comping_sets = {
            frozenset(s) for s in _comping_string_sets(3)
        }
        for step in self.comped():
            active = frozenset(
                i for i, fret in enumerate(step.voicing.frets) if fret >= 0
            )
            self.assertIn(active, comping_sets, step.tab_line())

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
                len(step.voicing.active_frets()), 3,
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
        `--texture targets --bass-style root,5th,approach,nearest` came back as a bare melody note - the guitar
        playing the tune it had been told to give away, on the weak beats only. The
        assertion is on the *shape*, not on the melody's pitch class, which a comping
        shape may legitimately share; see `test_the_generator_never_reads_the_melody`.
        """
        for step in self.comped(texture="targets", timings=self.timings):
            self.assertEqual(
                len(step.voicing.active_frets()), 3,
                step.tab_line(),
            )
            self.assertEqual(step.grip, "shell", step.tab_line())
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_the_bass_axis_still_decides_the_bottom(self):
        """`bass=walk` walks under a comping part, and `bass=none` does not.

        This is the band setting as a whole: both axes named, and neither inferred
        from the other.
        """
        walked = self.comped(
            texture="targets", bass="root,5th,approach,nearest", timings=self.timings
        )
        self.assertTrue(any(step.bass is not None for step in walked))
        silent = self.comped(texture="targets", bass="none", timings=self.timings)
        self.assertTrue(all(step.bass is None for step in silent))
        for step in silent:
            self.assertFalse(step.melody_voiced)

    def test_the_bass_axis_takes_the_option_spelling(self):
        """`ArrangeOptions.bass` reaches the engine, which it never did before.

        The test above spells `bass` as a keyword and this one spells it as an
        options field, and the two diverged for the field's whole life: the engine
        never read `options.bass` back out, so a walk handed over as options - which
        is how the slot layer hands over every request, `arranger head` among them -
        was silently dropped while the keyword test above stayed green.
        """
        by_keyword = self.comped(texture="targets", bass="root,5th,approach,nearest", timings=self.timings)
        by_option = self.engine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(
                parts=PARTS_WITH_BASS, texture="targets",
                bass="root,5th,approach,nearest",
                timings=self.timings,
            ),
        )
        self.assertTrue(any(step.bass is not None for step in by_option))
        self.assertEqual(format_progression(by_keyword), format_progression(by_option))

    def test_passing_both_bass_spellings_raises(self):
        """As for every other knob: two spellings of one value is a bug, not a merge."""
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(
                PROGRESSION, bass="root,5th,approach,nearest", options=ArrangeOptions(parts=VOICES_ARG)
            )

    def test_the_bass_axis_survives_the_slot_layer(self):
        """The head command's own path: `--bass-style` becomes an `ArrangeOptions` here.

        `arrange_slots` is the layer that builds the options and calls the engine,
        so this is the route `arranger head` actually takes and the one the unread
        field broke. Asserted on the thumb notes rather than on any warning, because
        a fix that quieted a warning while still dropping the line would pass
        otherwise.
        """
        from arranger.slots import arrange_slots

        steps, _rescued, _notes = arrange_slots(
            PROGRESSION, self.timings, parts=PARTS_WITH_BASS, bass="root,5th,approach,nearest",
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        self.assertTrue(any(step.bass is not None for step in steps))

    def test_an_nc_bar_is_emitted_silent_with_the_reason(self):
        """An `NC` bar has no chord, so there is no guide tone to state.

        The guitar is genuinely silent there, and the position is still **emitted**
        (item 4): a part that quietly omits a bar reads as a mistake, and a reader
        lining the comp against the tune needs the bar to be there. `silence` is
        what the tab's line reads for the reason, so it is what is asserted.
        """
        steps = self.engine.arrange_progression(
            [("D5", "m7", "Dm7"), ("C5", "NC", "NC"), ("A4", "7", "A7")],
            parts=VOICES_ARG,
        )
        self.assertEqual([step.chord for step in steps], ["Dm7", "NC", "A7"])
        self.assertEqual(steps[1].silence, "nc_comping")
        self.assertEqual(steps[1].voicing.frets, [-1] * 6)

    def test_the_corpus_nc_bar_keeps_its_place_in_the_tab(self):
        """The measured case: `Trouble_in_Mind_Blues` bar 1 is `NC`.

        It used to be absent from the comping part's tab - **12** positions over
        the three voice selections that reach the comping route, all of them this
        bar - while the horn played in it, so a reader lining the two parts up was
        one bar short with nothing to say which bar went. The bar is now present
        under every one of those selections, and every position in it is silent
        with the same reason.
        """
        from tests.support import arranged

        path = "tests/data/Trouble_in_Mind_Blues.musicxml"
        for parts in (PART_BASS, PART_CHORD, "bass,chord"):
            steps, head, _notes = arranged(path, parts=parts)
            bars = sorted(
                bar for bar in {step.bar for step in steps} if bar is not None
            )
            self.assertIn(1, bars, f"bar 1 vanished under parts={parts}")
            nc = [step for step in steps if step.silence == "nc_comping"]
            self.assertTrue(nc, f"no silent NC position under parts={parts}")
            self.assertTrue(
                all(not step.voicing.active_frets() for step in nc),
                f"a silent NC position sounds something under parts={parts}",
            )
            # Every bar the tune has is in the tab, bar 1 included.
            tune_bars = {note.bar for note in head.notes}
            self.assertTrue(
                tune_bars <= set(bars),
                f"bars missing under parts={parts}: {sorted(tune_bars - set(bars))}",
            )


class TestCompingMelodyIndependence(unittest.TestCase):
    """Step 0 of `docs/history/comping-styles.md` §9.3, **re-scoped by step C**.

    Step 0 pinned the comping route as melody-independent: scramble every melody pitch
    and no fret moves. It landed *before* step C deliberately, because C is the first
    step in which the melody affects the comping **harmony** - and once C lands the
    original claim is false by design. So it is **inverted rather than deleted**
    (AGENTS.md trap 5): the *placement* invariant survives (a slot's `bar`/`beat` never
    depends on the melody) while the *harmony* now does, under a strategy that
    substitutes. Both halves are asserted below.
    """

    #: The bars these tests arrange. See `_arrange`: the claim is about how a melody pitch
    #: reaches the comping part, which eight bars of the tune settle.
    SECTION = (1, 8)

    def _arrange(self, head, parts, grid="chord:freddie", non_chord_tone="extension"):
        """The `arrange_xml_head` comping path over an already-loaded head.

        `onsets` is computed the way `arrange_xml_head` computes it, so this exercises
        the real §9.2 guard rather than the all-onsets default a bare `arrange_slots`
        call would take.

        **`SECTION` bounds it, and the claim is why.** What is asserted is *how* a melody
        pitch reaches the comping part - the placement is blind to it, the harmony is not -
        and eight bars of the tune exhibit both. The scramble is the same function of the
        pitch either way, so the extra bars of a 32-bar tune were repeated evidence.
        """
        from arranger.slots import arrange_slots
        from headxml import _merge_chord_slots, head_skeleton, melody_state

        slots = head_skeleton(head, self.SECTION)
        if not parts_has_melody_only(resolve_parts(parse_parts(parts))):
            slots = _merge_chord_slots(slots, head, None, grid) or slots
        onsets = {
            index
            for index, slot in enumerate(slots)
            if melody_state(head.notes, slot[1], slot[2]) == "onset"
        }
        steps, _, _ = arrange_slots(
            [slot[0] for slot in slots],
            [(slot[1], slot[2], slot[3]) for slot in slots],
            parts=parts,
            grid=grid,
            beats_per_bar=head.beats_per_bar,
            non_chord_tone=non_chord_tone,
            onsets=onsets,
        )
        return tuple((step.bar, step.beat, step.chord, tuple(step.voicing.frets)) for step in steps)

    def _scrambled(self, head):
        """The head's chords, bars, beats and durations intact; only the pitches wild."""
        import copy

        scrambled = copy.deepcopy(head)
        for index, note in enumerate(scrambled.notes):
            note.pitch = 81 + (index * 3) % 14  # F#5-F6, mostly outside
        scrambled.notes.sort(key=lambda n: (n.bar, n.beat))
        return scrambled

    def _path(self):
        import os

        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data",
            "but_not_for_me.mxl",
        )

    def test_scrambling_the_melody_moves_no_fret_without_a_strategy(self):
        """Under `sustain` the melody cannot move a fret - the original step 0 claim.

        `sustain` substitutes nothing on the comping route (its hold-the-previous-voices
        move is a melody-route one), so this is the placement invariant alone: every
        pitch replaced by a wild high non-chord tone and nothing moves. `HeadNote.note_name`
        derives from `pitch`, so assigning `pitch` alone is enough - assigning
        `note_name` raises.
        """
        from headxml import load_musicxml

        for parts in (
            PART_CHORD,
            PART_BASS,
            "bass,chord",
        ):
            with self.subTest(parts=parts):
                head = load_musicxml(self._path())
                before = self._arrange(head, parts, non_chord_tone="sustain")
                self.assertTrue(before, "an arrangement with no steps at all is a defect")
                self.assertEqual(
                    self._arrange(self._scrambled(head), parts, non_chord_tone="sustain"),
                    before,
                    f"{parts}: a melody pitch reached the comping part with no strategy",
                )

    def test_a_substituted_melody_reaches_the_harmony_and_not_the_placement(self):
        """Under the default strategy the melody moves the *harmony*, never a *position*.

        Two claims in one, and the split between them is why step 0 existed: the
        `(bar, beat)` positions are identical whatever the melody does (the placement
        invariant survives), while the chord the guitar states at an onset now follows
        the horn's note (step C's intended change).
        """
        from headxml import load_musicxml

        head = load_musicxml(self._path())
        scrambled = self._scrambled(head)
        substituted = self._arrange(scrambled, PART_CHORD)  # default extension
        unsubstituted = self._arrange(scrambled, PART_CHORD, non_chord_tone="sustain")
        self.assertEqual(
            [(step[0], step[1]) for step in substituted],
            [(step[0], step[1]) for step in unsubstituted],
            "a melody pitch moved a slot's position",
        )
        self.assertNotEqual(
            substituted,
            unsubstituted,
            "the non-chord-tone strategy did not reach the comping harmony",
        )

class TestTheSopranoIsPerSlotNotPerRoute(unittest.TestCase):
    """§9.3 step D: the guitar sings a slot only where the tune *articulates*.

    `parts_have_melody` answers the arrangement-level half of the route; the other
    half is per slot. A soprano-named selection still **comps** the grid positions its
    tune is silent at, or merely sustains through, so `grid=joe_pass --voices
    soprano,...` places chords on the offbeats instead of ignoring the grid. The written
    onsets are untouched - that is the acceptance criterion, and **the default grid
    generates positions of its own** too (`every_note`, at each bar's own subdivision),
    so the default is no longer inert but still invents no melody - see
    `test_the_default_grid_invents_no_melody`.

    "Does the guitar sing this slot?" reuses §9.2's onset signal rather than re-deriving
    it: a position the melody only *holds* through is not an onset, so the guitar states
    the chord there rather than re-articulating a note it did not begin under.
    """

    def _path(self):
        import os

        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "but_not_for_me.mxl"
        )

    def _arrange(self, parts=PART_NAMES_ARG, grid="chord:joe_pass"):
        from tests.support import arranged

        return arranged(self._path(), parts=parts, grid=grid)

    def test_a_singing_selection_comps_the_grid_positions_it_does_not_sing(self):
        """The grid is no longer ignored when the guitar has the tune."""
        steps, _head, _notes = self._arrange()
        comps = [s for s in steps if not s.melody_voiced]
        self.assertTrue(comps, "the grid was ignored on a singing selection")
        for step in comps:
            # A comp states the chord and invents no melody; the written symbol is kept.
            self.assertTrue(step.voicing.active_frets(), step.tab_line())
            self.assertFalse(step.grip == "melody", step.tab_line())

    def test_the_comp_arity_excludes_the_silent_soprano(self):
        """The shape is the voices that will sound: four voices state a three-note shell.

        The soprano has no note to sing at these positions, so it is not one of the
        sounding voices - which is why `soprano,alto,tenor,bass` states three notes on
        the offbeats, not a four-voice shape with a redundant root. (The four-note
        comping shape is §9.4 and needs new string sets - deliberately not this step.)
        """
        steps, _head, _notes = self._arrange()
        comps = [s for s in steps if not s.melody_voiced]
        self.assertTrue(comps)
        for step in comps:
            self.assertEqual(len(step.voicing.active_frets()), 3, step.tab_line())

    def test_every_comp_sounds_only_chord_tones(self):
        """A comping shape is held to the full tone set of the chord it states."""
        steps, head, _notes = self._arrange()
        for step in steps:
            if step.melody_voiced:
                continue
            allowed = chord_pcs(step.chord)
            sounding = {pitch % 12 for pitch in step.voicing.midi_notes()}
            self.assertTrue(sounding <= allowed, step.tab_line())

    def test_no_written_note_is_dropped_by_the_grid(self):
        """The grid *adds* positions; it never removes a written note's slot."""
        from headxml import head_skeleton

        steps, head, _notes = self._arrange()
        at = {(step.bar, step.beat): step for step in steps}
        written = head_skeleton(head, None)
        self.assertTrue(written)
        for triple, bar, beat, _duration in written:
            note = triple[0]
            self.assertIn((bar, beat), at, f"{note} at bar {bar} beat {beat} went missing")
            self.assertEqual(at[(bar, beat)].melody, note)

    def test_the_default_grid_invents_no_melody(self):
        """The default grid adds positions; it never adds a *note* of the tune.

        `every_note` generates a chord at each bar's own subdivision now (open-issues
        item 1's remaining half), so the step count is no longer the skeleton's - what
        must still hold is that **no invented pitch reaches a singing part**. Every step
        either carries a written note at its written position, or carries none at all;
        and the ones that carry none are positions the tune is *silent* at rather than
        positions it wrote.
        """
        from headxml import head_skeleton, melody_state

        steps, head, _notes = self._arrange(grid="melody:every_note")
        written = {(bar, round(beat, 6)) for _t, bar, beat, _d in head_skeleton(head, None)}
        self.assertTrue(steps)
        for step in steps:
            bar, beat = step.bar or 0, step.beat or 0.0
            if (bar, round(beat, 6)) in written:
                continue
            self.assertIsNone(step.melody, step.tab_line())
            self.assertEqual(
                melody_state(head.notes, bar, beat),
                "silent",
                step.tab_line(),
            )

    def test_a_parts_has_melody_only_adds_nothing(self):
        """`soprano` plays the tune and nothing else, so it never comps a grid position."""
        steps, _head, _notes = self._arrange(parts=PART_MELODY)
        self.assertTrue(steps)
        self.assertTrue(all(step.melody_voiced for step in steps))
        self.assertTrue(all(len(step.voicing.active_frets()) == 1 for step in steps))




class TestTheNonChordToneStrategyReachesTheCompingRoute(unittest.TestCase):
    """§9.3 step C: `--non-chord-tone` harmonises the guitar's *comping* part too.

    The melody is the horn's, so the flag moves the chord the guitar **states** and
    nothing it sings: `melody_voiced` stays `False`, the shape is still a guide-tone
    comping shape, drawn now from the substituted chord, and `melody_pc` stays `None`
    so that shape is held to the substitute's full tone set.
    """

    def _comp(self, progression, strategy, **kwargs):
        steps = VoiceLeadingEngine.arrange_progression(
            progression, parts=VOICES_ARG, non_chord_tone=strategy, **kwargs
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_extension_absorbs_the_note_as_an_extension(self):
        steps = self._comp([("D5", "maj7", "Cmaj7")], "extension")
        self.assertEqual([s.harmonized_as for s in steps], ["Cmaj9"])
        # `chord` stays the written symbol; `harmonized_as` says what was stated.
        self.assertEqual([s.chord for s in steps], ["Cmaj7"])
        self.assertTrue(steps[0].non_chord_tone)
        self.assertEqual(steps[0].strategy, "extension")

    def test_diminished_states_the_dim7_a_semitone_below_the_resolution(self):
        steps = self._comp([("D5", "maj7", "Cmaj7")], "diminished")
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7"])
        self.assertEqual(steps[0].strategy, "diminished")

    def test_the_guitar_still_does_not_sing_the_substitute(self):
        """`melody_voiced` stays false and the shape is only the substitute's tones.

        `melody_pc` is `None` on this route, so the selector cannot excuse a wrong note
        for coinciding with the tune - every sounding pitch must be a tone of the chord
        actually stated, `Bdim7`.
        """
        steps = self._comp([("D5", "maj7", "Cmaj7")], "diminished")
        self.assertFalse(steps[0].melody_voiced)
        sounding = {pitch % 12 for pitch in steps[0].voicing.midi_notes()}
        self.assertTrue(sounding <= chord_pcs("Bdim7"), steps[0].tab_line())

    def test_sustain_substitutes_nothing(self):
        """The one strategy with no comping meaning leaves the written chord alone.

        A comping shape is built fresh on every slot, so `sustain`'s hold-the-previous
        move has nothing to act on and it must fall through to no substitution.
        """
        steps = self._comp([("D5", "maj7", "Cmaj7")], "sustain")
        self.assertIsNone(steps[0].harmonized_as)
        self.assertIsNone(steps[0].strategy)
        self.assertFalse(steps[0].non_chord_tone)

    def test_a_chord_tone_melody_is_untouched(self):
        """A melody the chord already contains is not reharmonised under any strategy."""
        for strategy in ("extension", "diminished"):
            with self.subTest(strategy=strategy):
                steps = self._comp([("C5", "maj7", "Cmaj7")], strategy)
                self.assertIsNone(steps[0].harmonized_as, strategy)

    def test_the_onset_guard_skips_a_held_position(self):
        """§9.2: a non-chord note is substituted where it **begins**, not where it holds.

        Index 1 is deliberately absent from `melody_onsets`, so it is a held position
        carrying the same note - it must be voiced as the written chord, not re-decided
        under a note whose onset already decided it.
        """
        progression = [("D5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7")]
        steps = self._comp(progression, "diminished", melody_onsets={0})
        self.assertEqual(steps[0].harmonized_as, "Bdim7")
        self.assertIsNone(steps[1].harmonized_as)

    def test_a_bare_call_with_no_timeline_treats_every_slot_as_an_onset(self):
        """`melody_onsets=None` (the default) is all-onsets - the hand-built caller's rule."""
        progression = [("D5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7")]
        steps = self._comp(progression, "diminished")
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7", "Bdim7"])

    def test_the_substitution_is_reported(self):
        """A guitarist with no melody on their part must be told why the chord moved.

        Asserted on the step's `harmonized_as` and `strategy`, which are the fields
        `render._substitution_clause` reads - so this is the same fact the tab line
        phrases, rather than a second spelling of it. One triple in, one step out:
        the fixture is a single slot, so a second element would mean the route
        duplicated it.
        """
        steps = self._comp([("D5", "maj7", "Cmaj7")], "diminished")
        self.assertEqual(len(steps), 1)
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7"])
        self.assertTrue(all(s.strategy for s in steps))

    def test_the_fallback_fires_at_onsets_only(self):
        """`--fallback` obeys the same §9.2 guard, at the slot layer where it lives.

        `D` over `Bbm7` is the major 3rd over a minor chord - no `NON_CHORD_TONE_EXTENSIONS`
        route - so `--fallback diminished` rescues it at an onset. The same note held at
        index 1 is not an onset and must be left alone.
        """
        from arranger.slots import arrange_slots

        progression = [("D5", "m7", "Bbm7"), ("D5", "m7", "Bbm7")]
        timings = [(0, 1.0, 1.0), (0, 1.5, 0.5)]
        steps, rescued, _notes = arrange_slots(
            progression, timings, parts=VOICES_ARG, fallback="diminished", onsets={0},
        )
        self.assertEqual(rescued, [0])
        self.assertNotEqual(steps[0].chord, "Bbm7")
        self.assertEqual(steps[1].chord, "Bbm7")


class TestTheCompingRouteCarriesAThumb(unittest.TestCase):
    """The thumb line must not be refused for a palette the comping route never plays.

    **`bass_allowed` was asked about `TEXTURE_GRIPS` on a route where it is inert.**
    That table describes the shapes `get_all_grip_voicings` generates; on the comping
    route the shapes come from `get_comping_voicings` and the texture is a meaningless
    name - measured on `tests/data/but_not_for_me.mxl`, all 80 comping shapes are
    byte-identical under `texture=uniform` and `texture=targets`.

    So `parts="chord", bass="root,5th,approach,nearest"` under the **default** texture was refused with
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
        # `bass,chord`: the thumb line is the bass part, and a bass style with no
        # bass part is refused ("add 'bass' to parts"). This class is the one that
        # carries a thumb, so it takes both parts.
        steps = self.engine.arrange_progression(
            PROGRESSION, parts=PARTS_WITH_BASS,
            timings=self.timings, **kwargs,
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_default_texture_no_longer_refuses_a_thumb_line(self):
        """The regression itself: `bass=walk` under the default texture.

        Asserted on the *thumb notes* rather than on the warning, because a fix that
        merely quieted the warning while still dropping the line would pass otherwise.
        """
        steps = self.comped(bass="root,5th,approach,nearest")
        self.assertTrue(
            any(step.bass is not None for step in steps),
            "the comping route emitted no thumb notes at all",
        )

    def test_the_texture_changes_the_arity_and_nothing_else_on_this_route(self):
        """How many notes the comping part states is the texture's; the slots are not.

        **Inverted rather than deleted.** It used to assert the frets were identical
        under every texture, and that was true while the arity came from the *number of
        voice names* - so the texture could not reach this route at all, and a texture
        that thinned a comping part was a defect. The arity is the texture's now
        (`chord1`/`chord2`/`chord3`), so the surviving claim is the split between the
        two: the texture decides the count, and the harmony timeline, the slot
        structure and the role are untouched by it.
        """
        baseline: Optional[list] = None
        for texture, ceiling in (
            ("chord1", 1), ("chord2", 2), ("chord3", 3), ("uniform", 3),
        ):
            steps = self.comped(bass="root,5th,approach,nearest", texture=texture)
            for step in steps:
                # The **upper** voices: the thumb is merged into the fret vector
                # after the comping shape is chosen, so it is not one of the notes
                # the arity counts.
                self.assertLessEqual(
                    len(step.voicing.upper_midi_notes()), ceiling, step.tab_line()
                )
            structure = [(s.bar, s.beat, s.chord, s.role) for s in steps]
            if baseline is None:
                baseline = structure
                continue
            self.assertEqual(
                structure, baseline,
                f"texture={texture} moved a slot rather than thinning one",
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

        `walking_slots` unions the melody grid with the walked beats. It was never
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
        walked = self.comped(bass="root,5th,approach,nearest")
        silent = self.comped(bass="none")
        # Four written notes, and the walk adds the two beats the melody skips.
        self.assertEqual(len(silent), 4, "the head is four notes in one bar")
        self.assertEqual(len(walked), 6, "the walk should add the two empty beats")
        self.assertGreater(
            len(walked), len(silent),
            "a walking line adds no beats, so the walk is not being heard",
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

        Before the collapse, `parts=alto,tenor` on a melody-only texture was
        refused with a warning and the melody handed back to the guitar. With
        the claim keyed on the selection, the same request comps, on every
        texture, without a refusal.
        """
        for texture in TEXTURE_STYLES:
            steps = VoiceLeadingEngine().arrange_progression(
                PROGRESSION, parts=VOICES_ARG, texture=texture,
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
            PROGRESSION, parts="melody"
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
                PROGRESSION, texture="melody"
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
            [("F4", "NC", "NC"), ("E4", "7", "G7")], parts="melody"
        )
        self.assertEqual([s.chord for s in steps], ["NC", "G7"])
        self.assertTrue(steps[0].melody_only)
        self.assertFalse(steps[1].melody_only)
        self.assertEqual(steps[0].grip, "melody")

    def test_an_off_grid_slot_under_soprano_still_sounds(self):
        """
        The grid guard answers before the empty palette too, on both routes.

        An off-grid slot is the one case where the guitar may play nothing
        rather than one note: under a comping selection it is a rest, and under
        a melody-only selection the note of the tune still sounds, alone -
        which is what every slot of that selection is anyway, so the ordering
        is asserted rather than left to read as a coincidence. Measured under
        `grid=joe_pass`, which places no chord on beat 1.0: every slot of the
        soprano-only arrangement still sounds its note.
        """
        progression = [
            ("F5", "maj7", "Fmaj7"), ("E5", "7", "A7"),
            ("D5", "NC", "NC"), ("C5", "m7", "Dm7"),
        ]
        timings = [(0, 1.0, 1.0), (0, 2.5, 0.5), (1, 1.0, 1.0), (1, 3.0, 1.0)]
        steps = VoiceLeadingEngine.arrange_progression(
            progression, timings=timings, parts="melody", grid="chord:joe_pass"
        )
        self.assertEqual(len(steps), 4, "an off-grid slot of the tune went missing")
        for step in steps:
            self.assertEqual(len(step.voicing.active_frets()), 1)


    def test_every_part_name_the_library_uses_is_in_the_vocabulary(self):
        """So a table cannot name a part a caller could not have typed."""
        for part in GRID_PART_PATTERNS:
            self.assertIn(part, PART_NAMES, part)
        self.assertEqual(set(GRID_PART_PATTERNS), set(PART_NAMES))


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
    was supposed to have. The equivalent hole now is `texture=`: a comping slot that
    states the default three regardless of the arity the caller asked for would be the
    same defect with the knob renamed, and this is the class that would catch it.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def counts_for(self, texture: str) -> List[int]:
        steps = self.engine.arrange_progression(
            PROGRESSION, parts=PART_CHORD, texture=texture
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
    """`parts=bass` sounds a bass note: low, and a root or a 5th.

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

    `parts=` names **parts**, not voices, which is what makes the first defect
    unreachable through the API: there is one bass part and it is addressed by name, so
    two different requests cannot collapse to one arrangement. The inner voices are
    reached as the chord part - both guide tones together - and
    `test_an_inner_voice_is_not_addressable_as_a_part` is the inversion of the old
    per-voice test.
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def arrange(self, parts: str):
        return self.engine.arrange_progression(PROGRESSION, parts=parts)

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
        self.assertEqual(cells[3], _MUTED_CELL)
        self.assertEqual(cells[4], _MUTED_CELL)

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
            self.assertEqual(cells[string_index], _MUTED_CELL)

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
        default = VoiceLeadingEngine.arrange_progression(PROGRESSION, parts=VOICES_ARG)
        explicit = VoiceLeadingEngine.arrange_progression(
            PROGRESSION, parts=VOICES_ARG, harmony="auto"
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
            PROGRESSION, parts=PART_CHORD, harmony=HARMONY_SHELL_ROOT
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
        """`ArrangeOptions().harmony` is `auto`, and `auto` resolves to `guide`.

        Asserted separately because the two spellings are load-bearing in different
        places: the field must match `arrange_progression`'s keyword default for the
        comparison above to mean anything, and the policy must resolve to the shipped
        behaviour for the arrangement to be unchanged.
        """
        self.assertEqual(ArrangeOptions().harmony, HARMONY_AUTO)
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
                PROGRESSION, parts=PART_BASS, harmony=HARMONY_SHELL_ROOT,
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
            VoiceLeadingEngine.arrange_progression(PROGRESSION, harmony="nonsense")

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

if __name__ == "__main__":
    unittest.main()


