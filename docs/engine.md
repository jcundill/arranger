# Engine reference

The voicing engine: what shapes exist, how one is chosen, and what the tables
behind them mean. Read this before touching anything under `arranger/` except
`options.py`.

The module map and the dependency order that holds it are in
[../AGENTS.md](../AGENTS.md); this document is the reasoning behind the decisions,
not the map. Where a rule was measured, the measurement is kept - it is what tells
you whether a change is an improvement or a different library.
## Architecture and key types

- `STANDARD_TUNING` — six open-string `Note`s, index `0` = low E (string 6)
  through index `5` = high E (string 1). `STRING_NAMES` mirrors these.
- `MELODY_STRING_CHOICES` — `(5, 4)`: the soprano string indices the *drop-2* path may
  be pinned to (`5` → D-G-B-E, `4` → A-D-G-B). Kept as the default of
  `get_drop2_voicings` so its published output is unchanged. Index `0` = low E ...
  `5` = high E, so the conventional guitar string number is `6 - index` (index
  `5` = string 1).
- `MELODY_STRING_CHOICES_FULL = (5, 4, 3)` — the default soprano set: the high E, the
  B **and the G** string. Adding the G string is what lets a melodic position be held
  by *changing strings* rather than by moving the hand. The A string and the low E are
  inner voices only; no grip puts the soprano on either, so the melody floor is `G3`
  while the chord range extends down to `E2` as a bass voice.
- `GRIP_PREFERENCE = ("drop2", "drop2_6432", "shell", "duo")` — the grip families and
  their tie-break order. `drop2_6432` (6-4-3-2) is listed second because it is the
  *alternative* to the contiguous drop-2, not a third string set for it:
  `grips=("drop2",)` still means the four contiguous strings, which is the idiom that
  reproduces the original output exactly. `drop3` and `closed` are generated but
  deliberately **not** listed: neither can be played within `GRIP_MAX_SPAN`
  (see Known Limitations).
- `GRIP_STRING_SETS` — for each grip, its supported `(active string indices, soprano
  index)` pairs: the 4-3-2-1 and 5-4-3-2 four-string blocks, **6-4-3-2**, the six
  shell shapes (1-2-3, 2-3-4, 5-4-3, **6-4-3**, and the two 5-3-2s — `(1,3,4)`
  skipping the D going down and `(5,3,2)` skipping the B going up). The **duos** are the
  three adjacent pairs 1-2, 2-3 and 3-4 plus **one** skipped pair, `(3,1)`, which exists
  to voice the 9ths a displaced 2nd needs — see the decisions below. An `interval` uses
  the three adjacent pairs only: a 3rd or a 6th has tuning to spare and gains nothing
  from a wider set.
  `6-4-3`, both `5-3-2`s and `6-4-3-2` are the four non-contiguous sets, each skipping
  one string; `6-4-3-2` and `(5,3,2)` skip one going *up* (the A to reach the B as
  soprano, and the B to reach the high E respectively).
  **No set skips an *inner* string any more except the `(5,3,2)` shell**: the four
  `drop24` sets that did - four of that family's eight, two of them its measured winners -
  were removed because the right hand had to reach over an unplucked string to fret them.
  [fingering.md](fingering.md) §4.4 holds the measurement and what the removal cost.
  `supported_string_sets()` is the playability invariant stated in
  one place, and adds the drop-2 blocks for all three sopranos (drop-2 is defined
  generically, so a caller passing their own `top_string` still works).
- `BASS_DEGREES_6432 = (0, 7)` — the degrees the low E may take in a 6-4-3-2 shape, and
  the analogue of `DUO_DEGREES` for the bass rather than the melody. The lowest voice is
  what *defines* the chord, so a 3rd or a 7th there sounds like a different harmony.
- `SHELL_DEGREES` — the (3rd, 7th) pair per quality, explicit rather than inferred:
  a quality not listed gets no shell rather than a guessed one. A **duo reads its second
  voice from this same table** — `[0]` first (the 3rd, or the 4th on a suspended chord),
  `[1]` when `[0]` is the melody itself — so a quality cannot gain a shell and lose its
  duo. `DUO_DEGREES = (0, 7)` is the degrees a duo's *second voice* may take, not the
  melody's: a duo is generated under **any** chord tone, because a guide tone beneath a
  3rd or a 7th is what states the chord's function. The `interval` grip is a separate
  family for a different reason — it is a texture rather than a harmony; see
  [Texture: chords on the beats, fills between](#texture-chords-on-the-beats-fills-between).
- `ROLE_TARGET` / `ROLE_FILL`, `TEXTURE_STYLES`, `TARGET_BEATS`, `TEXTURE_GRIPS` —
  the metric layer's whole vocabulary. `TARGET_BEATS = (1, 3)` names *beats*, not
  an absolute onset, so the rule reads the metre it is given; `_metric_weight` and
  `_roles_for_slot` are the two functions that apply it.
- `NECK_FRET_MIN` / `NECK_FRET_MAX` — `2` and `13`. A strong preference, never a
  filter; see the selector below.
- `HIGH_FRET_LIMIT` — `13`. A melody whose only available position sits above this
  fret is re-voiced an octave down on the B string. See
  [High melodies move down an octave](#high-melodies-move-down-an-octave).
- `Voicing` — a dataclass for one fretboard shape: `frets` (6 entries,
  `-1` = muted), `top_fret`, `avg_fret`. Helpers: `tab_string()` (one-line
  `x-x-12-13-13-13`, frozen: ~40 call sites in tests and docs depend on it),
  `tab_block()` (six-line vertical tab, high E first, two-char right-aligned
  cells, highest string labelled lowercase `e`), `tab()` (`tab_block()` joined
  with newlines), `active_frets()`, `fret_span()`, `midi_notes()`,
  `pitch_classes()`, `soprano_string()` (index of the highest sounding string;
  `-1` if all muted). Supports legacy dict-style access (`v["frets"]`).
- Tab rendering is **pure**: every renderer returns a string (or list of
  strings) and prints nothing, so callers control display. Only `main()` and the
  `arrange_progression` warning paths write to stdout.
- `ArrangementStep` — a dataclass of `chord`, `melody`, `voicing` plus the
  non-chord-tone bookkeeping `non_chord_tone` (bool), `strategy` (which strategy
  handled the step) and `harmonized_as` (the substitute chord name). Also
  `tab_line()` / `tab_block()`, which delegate to the `Voicing` renderers.
  Supports legacy dict-style access (`step["chord"]`).
  The optional `bar` / `beat` / `duration` (all default `None`) carry the timing the
  staff renderer needs; `has_timing` reports whether a step can be placed on a grid.
  `repeated` (default `False`) marks a step whose melody repeats the previous step's
  pitch **under an unchanged harmony**: the voicing is still generated in full, but the
  renderers show only the soprano and hold the inner voices. A repeat across a chord
  change is not a hold and is not marked. See
  [Repeated melodies hold the shape](#repeated-melodies-hold-the-shape).
- `format_progression(steps)` — module-level renderer for a whole
  arrangement: one line per step. Non-chord-tone steps are annotated via the shared
  `_step_annotation()` helper, which `_print_step()` also uses so the two
  renderings cannot drift. It used to take `vertical=True` for a six-line block per
  chord, and the `--vertical` flag existed only to reach it; both are removed, so
  this is the compact one-line form alone and `format_tab_staff` is the six-line
  rendering. `Voicing.tab_block()` still renders a single voicing vertically.
- `format_tab_staff`, `format_tab_html` and `write_tab_html` **live in
  `tabstaff.py`**, not here, and are re-exported below. See
  [The staff renderers live in `tabstaff.py`](#the-staff-renderers-live-in-tabstaffpy).
- `format_tab_staff(steps, beats_per_bar=4, beat_type=4, rhythm=True,
  show_chords=False, show_melody=False, show_melody_string=True, show_mutes=False,
  collapse=True, measures_per_line=4, show_timing=False)` — renders the **whole
  progression along one six-line staff** in reading order (high E on top), which is
  the standard tab layout and unlike `format_progression` is not one block per chord.
  The defaults draw **the tab and nothing else** — six string rows, frets sitting in a
  line of dashes, every bar ruled. `show_chords`, `show_melody` and `show_timing` add
  the lead-sheet and score annotation on top, and all three were on by default once.
  With `show_chords`, the chord names go on a line above, each starting in the column
  where its shape is struck, and `show_timing` adds the **metre** and a **note value per
  column** above them — see [docs/renderers.md](renderers.md#what-the-staffs-timing-rows-are-and-what-they-are-not).
  Neither is on by default: **width already says how long a note sounds**, so that row
  is a second, explicit way of saying it rather than the only one.
  Three decisions are load-bearing and were each forced by looking at the output:
  - **Fret cells are left-aligned in a fixed-width column.** A right-aligned cell
    looks tidy on its own but puts the fret at the far end of the column, so the
    chord name and its frets no longer share a column. The column width widens to
    the longest chord name rather than letting the chord line drift out of step
    with the frets under it.
  - **`collapse` compares sounding pitches, not fret numbers.** The skeleton voices
    one step per eighth, so without it a held chord is restruck eight times a bar and
    the staff is a chord list rather than a held shape. A rest clears the held
    pitches, because a rest genuinely stops the ringing.
  - **Every bar is ruled, and `measures_per_line` is bars per *line*.** These were one
    setting once: barlines were drawn every `measures_per_line` bars, on the reasoning
    that a barline every bar cluttered a grid already dense with columns. Splitting them
    was forced by TuxGuitar's ASCII export, which closes every measure and wraps at a
    fixed number of bars. A barline is not clutter — it is the one mark saying where the
    metre falls, and without one on every bar a reader cannot tell a two-bar phrase from
    a four-bar one. So `_staff_barlines` marks every bar and `_staff_breaks` marks where a
    line ends, both derived from one `_staff_bars` list so the two cannot disagree. The
    grid starts at the first step's own onset so a head selected from bar 1 (or from a
    negative pickup bar) is not preceded by empty bars.
  - **A string is drawn as a continuous line of dashes**, with the fret numbers sitting
    *in* it, and the chord/melody/metre rows above are **not** filled. That asymmetry is
    deliberate and is the difference between a staff that reads as tab and one that reads
    as a chord list; a dash through a chord name would be a line through the word.
  Muted strings are blank by default (a ringing voice is not restruck);
  `show_mutes` spells them out, and a melody-only step always shows its `x`s.
  With no step timing, `rhythm=True` falls back to a uniform one-chord-per-beat
  grid rather than failing.
- `GuitarFretboard` — static helpers `note_to_fret(string_index, note)` and
  `fret_to_midi(string_index, fret)`. Out-of-range inputs return `-1`.
- `ChordParser` — `parse_chord_name(name) -> (root, quality)`,
  `get_melody_degree(root, melody_note) -> 0..11`, `canonical_quality(quality)`
  (case-sensitive alias resolution: `M7` -> `maj7`, `M` -> `maj`, `m7` stays `m7`)
  and
  `get_chord_tones(quality, chord_name=None)` -> every pitch class in the chord.
  `CHORD_TONES_FROM_ROOT` is the full tone set per quality, deliberately distinct
  from `DEGREE_OFFSETS_FROM_ROOT`, which lists only the four notes a drop-2 shape
  voices — so the root of a rootless `7b9` still counts as a chord tone.
- `VoiceLeadingEngine` — the core engine:
  - `DROP2_INTERVAL_SETS`: semitone offsets from the soprano voice for each
    supported chord quality (seventh, extended, triad, suspended and altered
    families) plus aliases.
  - `DEGREE_OFFSETS_FROM_ROOT`: which chord tone each inversion places on top.
  - `get_drop2_voicings(melody_note, chord_type, chord_name=None, top_string=5)`
    — one string block; `top_string=4` pins the melody to the B string.
  - `get_grip_voicings(melody_note, chord_type, chord_name=None, top_string=5,
    grips=GRIP_PREFERENCE)` — candidates for one soprano string across every grip
    family, the general form of `get_drop2_voicings`.
  - `get_all_grip_voicings(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES_FULL, grips=GRIP_PREFERENCE)` — candidates
    across every allowed soprano string, high-E first, applying the chord-tone match
    then the quality-only fallback. **Pure**: it neither filters by fret nor
    transposes. `get_all_drop2_voicings` is this pinned to `grips=("drop2",)`.
  - `voicing_cost(voicing, previous, fret_min, fret_max, allowed_tones)` — the whole
    selection rule as one comparable tuple: notes outside the chord, then frets
    outside the window, then missing voices, then **span** (with spans 0 and 1
    bucketed to the same value — see §"Span outranks neck position"), then neck
    position (the difference of average frets from the previous voicing), then pitch
    movement, then grip preference. Lexicographic, not a weighted sum, because these
    priorities must not be traded against each other. `_best_voicing` is its argmin
    and is stable, so the engine is deterministic.
  - `get_octave_down_candidates(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES)` — the same for the melody an octave lower,
    on the strings below the high E. Empty when the transposed melody is unvoiceable,
    so the caller keeps its original candidates.
  - `calculate_voice_leading_distance(voicing_a, voicing_b)` — per-string fret
    movement, kept for backward compatibility (only meaningful within one block).
  - `calculate_pitch_leading_distance(voicing_a, voicing_b)` — movement in
    semitones between sorted sounding pitches; identical to the fret metric within
    one block, and the metric `arrange_progression` uses across blocks.
  - `NON_CHORD_TONE_EXTENSIONS` — canonical quality → `{melody degree: extension
    quality}`, the routing used by the `extension` strategy.
  - `NON_CHORD_TONE_STRATEGIES` — the accepted `non_chord_tone` values.
  - `is_chord_tone(melody_note, chord_type, chord_name)` — chord-tone detection
    using `ChordParser.CHORD_TONES_FROM_ROOT`; `False` for unknown qualities.
  - `resolve_non_chord_tone(melody_note, chord_type, chord_name, strategy,
    next_melody=None)` -> `(quality, name)` for a substitute chord, or `None` when
    the strategy cannot help (the caller then keeps its fallback).
  - `sustain_inner_voices(previous_voicing, melody_note)` — holds the previous
    voicing's inner voices and moves only the soprano; `None` when unplayable.
  - `arrange_progression(progression, top_strings=MELODY_STRING_CHOICES_FULL,
    non_chord_tone="extension", fret_min=NECK_FRET_MIN, fret_max=NECK_FRET_MAX,
    grips=GRIP_PREFERENCE, timings=None, texture="uniform", beats_per_bar=4)`
    — voices each step, applying the selected non-chord-tone strategy where needed,
    and chooses each shape with `_best_voicing`. An unknown strategy or texture
    raises `ValueError`, both before any voicing work. `grips=("drop2",)` with
    `top_strings=MELODY_STRING_CHOICES` reproduces the library's original output
    exactly, which is what the renderer tests pin their fixture to. `timings` and
    `texture` are the metric layer; see
    [Texture: chords on the beats, fills between](#texture-chords-on-the-beats-fills-between).
  - `VoiceLeadingEngine.get_interval_voicings(melody_note, chord_type,
    chord_name=None, top_string=5)` — the two-note `interval` grip, a public entry
    point like `get_drop2_voicings` so every family is reachable on its own.
  - `__version__` — the library version string, the single source of truth that
    `pyproject.toml` reads as the dynamic project version. No document may state a
    different one: `tests/test_docs.py` fails the suite if one does.
- `NO_CHORD` — the string `"NC"`, a bar carrying melody with no harmony.
- `VoiceLeadingEngine.get_melody_only_voicing(melody_note, prefer=...)` — a
  **single-fret** `Voicing` for an NC step, or `None` if unreachable. It is
  explicitly *not* a harmonised voicing and is exempt from the string-set invariant.
- `ArrangementStep.melody_only` — defaulted flag set on NC steps.
- `main()` — with no arguments, prints the built-in demonstrations; with `head`
  as the first argument, delegates to `headxml.head_cli` through a **lazy** import
  inside the branch, so `import arranger` never depends on the importer or, through
  it, on the renderers.
- `main()` — prints the built-in demonstration arrangements; exposed as the
  `jazz-arranger` console script via `[project.scripts]`.

### Adding a new chord quality

1. Add a template list to `DROP2_INTERVAL_SETS` (one inversion template per voiced
   tone, each `[0, offset2, offset3, offset4]` in semitones below the soprano).
   Derive each template from the close-position stack under the melody: with
   `d1 < d2 < d3` the **cumulative** semitone distances down from the top voice to
   the next three chord tones (each the nearest chord tone below), the drop-2 shape
   is `[0, -d2, -d3, -(d1 + 12)]` — the second voice from the top lowered an octave.
   A triad needs a fourth voice, so its templates double the root an octave below the
   stack; ninth/13th qualities are voiced rootless (root, or 5th when the root is on
   top, omitted) so the extra tone still fits four strings.
2. Add the matching entry to `DEGREE_OFFSETS_FROM_ROOT` **in the same order** as
   the templates, so each melody note is matched to the correct inversion.
3. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`. This is also
   what `drop3`, `closed`, `shell` and `duo` build themselves from, so it is required
   for the new grips to reach the quality at all. If the quality should also get a
   shell, add it to `SHELL_DEGREES` — the default drop-2 and the derived grips work
   without one.
4. Add aliases to `ChordParser.QUALITY_ALIASES` (and, for backward compatibility,
   optionally to the `DROP2_INTERVAL_SETS[...] = ...` block).
5. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
6. **If a MusicXML file should be able to spell it**, add the matching
   `kind-value` to `MUSICXML_KIND_QUALITIES` in `headxml.py`, and any `<degree>`
   alteration that reaches it to `_DEGREE_REFINEMENTS`. The same rule applies: an
   absent kind resolves to `None` and is counted in `Head.unmapped`, so a new
   quality MusicXML cannot spell stays silent until this step is done. Note the
   table is keyed on the *library* quality, so a `kind` that only a `<degree>`
   reaches (a 7b5, say) needs a degree entry rather than a kind entry.
8. Add tests to `tests/test_voicings.py` for the drop-2 fingerings and to
   `tests/test_grips.py` for the other grips: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`, and the sounding strings
   a member of `supported_string_sets()`.
   `TestQualityTableInvariants` checks the template and degree lists stay the same
   length, and `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route.
   `tests/test_headxml.py::TestChordParsing::test_every_kind_the_table_names_is_voiceable`
   asserts that every quality `MUSICXML_KIND_QUALITIES` names can be voiced, so a
   table entry naming an unvoiceable quality fails the suite.

## Grips, and the position-aware selector

The engine generates several grip families and then chooses between them, rather than
generating one kind and voice-leading it. Generation and selection are deliberately
separate: `get_grip_voicings` and `get_all_grip_voicings` are *pure* (no position
filtering, no transposition) and `_best_voicing` does all the deciding. That split is
what stops the grip families and the octave-down rescue from having to know about each
other, and it is asserted in `tests/test_grips.py`.

### Span outranks neck position

`voicing_cost` ranks **fret span above neck position**. This is the only place one
criterion is promoted across another, and the trade was measured rather than guessed.

**The two criteria disagree about the same thing.** Position measures how far the
*hand* moves; span measures how far the hand has to *stretch* once it is there. A
five-fret shape sitting one fret from where the hand already was wins on position and
loses on span — and with span ranked below position that shape was chosen, which is
how the engine came to select `8-x-8-8-13-x` (index at 8, pinky at 13) for a Cm7b5.
Keeping the hand still is worth less than being able to play the shape it is holding.

**Promoting span is free where tightening the cap is not.** The obvious alternative is
to lower `GRIP_MAX_SPAN` from 5, and it was implemented and measured first. It is a
*filter*, so it deletes a voicing wherever no tighter one exists, and that cost real
music:

| cap | voicings kept (of 1008) | what went missing |
|---|---|---|
| 5 | 960 | — |
| 4 | 960 | the only Gsus4 fingering, `x-x-5-5-3-8`; and the **6-4-3** shell |

6-4-3 is the one default shape that reaches the low E, and losing it is a far bigger
musical cost than a few wide shapes. Ranking instead only ever chooses *between shapes
already on the table*, so nothing stops being voiceable at all. Over the same 1008
(melody, quality) pairs, coverage is identical at 960 and the share of selected
five-fret shapes fell from **4.1% to 0.8%**, with span-1 shapes rising from 27.8% to
44.4%.

**What it does not promise.** A selected shape can still span five frets, because
where the only candidate is wide, span is consulted first, finds every candidate
equal, and the wide one is played. `GRIP_MAX_SPAN` remains the outer bound. The
promotion is also below the correctness criteria: a shape sounding a foreign note or
a partial harmonisation still loses to a correct one however tight it is, which
`tests/test_grips.py::TestVoicingCost` asserts directly on the tuple rather than only
through a result.

**Span 0 and span 1 are bucketed together.** The span index reports `0.0` for both,
so a zero-span barre and a one-fret reach tie and the decision falls through to neck
position. One fret of stretch is not a stretch worth moving the hand for, and the
case that showed it was a player reading the tab rather than a corpus measurement:
`Bb7` under `F4 → G4 → F4` with `--grips shell` was voiced `x-x-6-7-6-x`,
`x-x-x-3-3-3`, `x-x-6-7-6-x` — down to a fret-3 barre for one note and straight back,
because the barre spans zero and the natural shape at frets 7–8 spans one. The
bucket keeps the hand at 6–8 (`x-x-8-7-8-x`). The bucket is applied to the *value*
at the span index, not by reordering the tuple, so **every span of two or more still
outranks position exactly as before**: the `8-x-8-8-13-x` case below is untouched,
and so is the low-Dm7 trade measured below it. Measured over the suite, the change
moves exactly one pinned tab — the last fill of the `targets` texture, `x-x-x-5-5-5`
→ `x-x-10-9-10-x`, which is the same stay-in-place behaviour on a different chord.
A bucket of `0/1/2` was measured too and **rejected**: it costs 13 tests, including
the low-Dm7 trade reverting to `5-x-3-5-3-x` and two walking-bass anchor
diagnostics, because a four-fret reach competing with barres on position is a
different decision than a one-fret reach doing so.

**The one case it costs, and why it is not tuned away.** A low Dm7 under D4 is now
`x-3-3-2-3-x` (span 1, lowest voice C3) where it was `5-x-3-5-3-x` on 6-4-3-2 (span 2,
lowest voice A2). Both sound the same four pitch classes, both are inside the window,
both are complete, so span decides and the narrower one wins — and the cost is the
bass, since C is the 3rd where A was the 5th, and 6-4-3-2 is the only default set that
reaches the low E at all.

The obvious repair is to rank the bass-function term above span. That was implemented
and measured, and it **brings `8-x-8-8-13-x` straight back**: the same ordering that
rescues the low bass also lets a five-fret shape with a root bass beat a one-fret shape
without one. The two criteria cannot both come first, so the choice is which to
favour. Span is favoured because a five-fret stretch is a shape the hand may not be
able to play at all, while a 3rd in the bass is a musical detail the ear supplies
around. The regression is asserted explicitly in
`tests/test_progressions.py::test_low_register_cadence_voices_low_with_a_complete_chord_or_a_shell`
so it stays visible rather than being quietly re-tuned away.

**Span is a distance, not a count.** `fret_span()` is `max(frets) - min(frets)`, so a
shape on frets 6 and 10 spans *four*: the stretch from index to pinky is four frets
even though five fret positions are involved. Counting the touched frets
inclusively would describe a reach the hand does not make, and would make the limit of
5 mean a five-finger stretch.

| grip | voices | how it is built |
|---|---|---|
| `drop2` | 4 | `DROP2_INTERVAL_SETS`, verbatim — the tables are hand-authored |
| `drop2_6432` | 4 | 6-4-3-2, found by search — the one default set that reaches the low E |
| `drop3` / `closed` | 4 | derived from a close stack; not offered by default |
| `drop24` | 4 | **drop-2 & 4** — the second *and* fourth voices lowered an octave; not offered by default |
| `shell` | 3 | `SHELL_DEGREES` plus one more note |
| `duo` | 2 | the chord's guide tone — the 3rd, or the 4th on a sus chord — under any chord tone |

**Every four-note voicing sounds the chord's 3rd and 7th**, and so does every three-note
one — except a suspended chord, which has no 3rd and whose guide tone is therefore the
**4th**. `Dsus7` is 1 4 5 b7 and its pair is (4, b7); `sus2`'s is the 9th. `SHELL_DEGREES`
already said so, and `tests/test_grips.py::TestGuideTones` holds the three tables to
the same answer. Those two notes are what decide whether the ear hears a major or minor chord, and
a dominant or a minor 7th, so a shape without them is a different chord rather than a
thinner one. All 109 hand-authored drop-2 templates keep both in all four inversions;
the rule is enforced where a table has no entry for the melody's degree, and
`_drop2_for_untabled_degree` derives that shape from the close stack under *this*
melody, falling back to `_guide_tone_drop2` if the derivation drops a guide tone. An
empty result offers nothing rather than borrowing another degree's template.

**Drop-2 & 4** lowers the second and fourth voices of a close stack an octave each — the
widest four-note shape there is, twenty semitones from melody to bass for a Cmaj7. It
is unplayable on four neighbouring strings and becomes frettable only through the
skipping rule below: the bass voice takes a lower string. Four of its eight sets instead
made it frettable by skipping an **inner** string — 1-2-4-5 (the G), 2-3-5-6 (the B),
1-3-4-6 and 2-4-5-6 — and **those four are now removed**, because the digit that takes a
string above an unplucked one has to reach over it. That is not a tidy-up: 1-2-4-5 and
2-3-5-6 were this family's measured winners over sevenths, ninths and sixths, and over
the committed heads the removal moves 260 of 1,204 selections and takes 57 of the 1,087
four-note steps down to fewer voices — **41 of them to the melody alone**, 16 to a duo —
because the best shape left at that melody position then sits at the top of the span
budget and `should_demote_to_melody_alone` drops it, and two positions in the pinned
fixtures lose their chord the same way (F5 at fret 13 over an F7, and C#5 over an Am7).
The full measurement, including which of the lost shapes were span-0 barres that cost
the hand nothing, the alternative that keeps every chord, and the open question of
whether the rule should be per *set* or per *shape*, are in
[fingering.md](fingering.md) §4.4. Not in `GRIP_PREFERENCE`: it is reachable, but it
spans nearly two octaves and is a colour rather than the default four-note reading.

Note the local names, which cost a wrong answer here: in `_, v1, v2, v3 = stack`, `v1`
is the **second** voice. So drop-2 & 4 drops `v1` and `v3` and keeps `v2` beside the
melody — `[0, v2, v1 - 12, v3 - 12]`. The other order sounds four chord tones too, and
so passes a tone-purity check while being the wrong shape.

**A four-note shape need not occupy four neighbouring strings.** The lowest voice may
skip to a lower string — what `drop2_6432` does with the low E, generalised. The
strings are tuned higher than the one below, so a deep bass runs out of board on a
contiguous block long before the low E would; skipping moves the shape down the neck as
a unit instead of stretching it. `GRIP_STRING_SETS` carries the skipping set for each
four-string block, and `_place_template` still assigns the voices soprano-first, so a
set is ordered descending with the gap at the bottom.

Five decisions in here were each forced by something measurable:

- **drop-2's tables are never derived.** The extended qualities are voiced *rootless*
  on purpose, so a 9 or a 13 that fits in four voices without the root is a musical
  decision. Deriving drop-3 and close position from the same chord tones gives a
  *fuller* chord — a legitimate but different voicing — which is exactly why drop-2 is
  left alone.
- **Duos sound the chord's guide tone, under any chord tone.** The second voice is read
  from `SHELL_DEGREES` — the 3rd, or the **4th** on a suspended chord, with the 7th as the
  fallback — rather than from a list written out separately. That table already encodes
  the arranging guide's rule, and sharing it means a quality cannot gain a shell and lose
  its duo. It replaced a hand-written `(4, 3, 0)` scan that had two faults: it listed no
  sus degree, so `sus4`, `sus2` and `7sus4` admitted **no duo anywhere**, and its root
  fallback was unreachable besides, filtered out by its own `d not in DUO_DEGREES` guard.
  The fallback to the 7th is load-bearing: when the melody *is* the 3rd, `[0]` would place
  a unison under it, and a measured 252 of these cases are exactly that.

  This used to be a **hard rule on the melody** — `DUO_DEGREES = (0, 7)`, generated only
  under a root or a 5th, on the reasoning that a 3rd or a 7th there *is* the chord's
  function and a bare duo under it sounds wrong. That reasoning does not survive the
  guide-tone rule the family is built from: a guide tone *beneath* a 3rd or a 7th is what
  states that function, and it is the clearest possible statement that the two notes are
  this chord. The gate is gone. A melody that is not a chord tone never reaches the duo
  at all, because the non-chord-tone strategies rewrite the chord before generation — so
  a b6 arrives as the 9th or 13th of a resolved chord rather than as a passing note with
  a duo under it. `TestDuoHardRule` asserted the old rule and is **inverted rather than
  deleted**, because a 3/7 duo consists of genuine chord tones and the "only chord tones"
  check would not catch it either way.

  - **A 2nd under the melody is dropped an octave.** When the guide tone lands within two
    semitones of the melody the shape is a 2nd, which in two voices is where they fight
    rather than agree; the same pitch class an octave lower is a 9th, which sits. This is
    why the duo owns a **skipped-string** pair. A 9th spans 14 semitones and two adjacent
    strings are tuned 4 or 5 apart, so the lower note needs a fret difference of 9 or 10
    against a span cap of 4 — and over the 812 cases where the guide tone is displaced,
    **none** is voiceable on the adjacent pairs. `(3,1)` (strings 3-5, 10 semitones of
    tuning between the open strings) recovers 810 of them; `(5,2)` ties it, `(5,3)`
    recovers 118 and `(4,2)` 31, so **one pair was added, not four**. The cap is not
    widened for it: the pair works because it is wide in *tuning* and narrow in *frets*.
    Two cases remain unreachable — a `sus4` and a `7sus4` with G3 in the melody — and they
    return no duo rather than sound a 2nd, pinned by name in `test_grips.py`.
- **A shell is searched for, never stacked.** A shell's notes are not in descending pitch
  order down the strings, because the tuning is not monotonic in the useful direction: the
  A string is tuned five semitones *above* the D string. A G7 shell under G3 is
  `2-3-0-x-x-x` — B2 on the A string, F3 on the D string, G3 on the G — where the A string
  carries the *lower* note while being the higher string; Gm7 in 6-4-3 is `3-x-3-3-x-x`,
  with G3 on the D string below A2 on the low E. A model that stacks voices by pitch gets
  both backwards and finds nothing, so `_place_shell` holds the melody and searches every
  combination of frets inside the span limit. That makes the search *exhaustive within the
  playability invariant*: if a playable shell exists in that position, it is found.
- **No four-note voicing on 6-5-4-3.** A G-string soprano has no four-note block, because
  the only one available is all of the four lowest strings and that does not sound good —
  four voices in the bottom fourth of the compass. A low melody is harmonised with a
  three-note shell (5-4-3 or 6-4-3) instead, dropping the 5th degree. Stated in one
  place, `_BOTTOM_FOUR`, and asserted by `TestStringSetTable`. **6-4-3-2 is not an
  exception to this rule**, which is why the two must not be conflated: it swaps the A
  string out for the B, so its lowest note is the low E while its soprano is the B, not
  the G. It is the answer to a different question — a *bass* — and it is the only default
  set that can reach one.
- **6-4-3-2 is searched for, and it needed a cost term to be chosen at all.** The same
  reason as 6-4-3: the set skips a string, so it is not in descending pitch order down
  the strings, so a hand-authored table cannot express it — the D string is a fifth above
  the low E, and the low E's note is frequently *not* the lowest sounding pitch.
  `_place_drop2_6432` therefore reuses `_place_shell`'s exhaustive search rather than
  inventing a second way to place notes, and ranks the survivors by `(fret_span,
  avg_fret)`. Two measurements forced the rest. Ranking is not cosmetic: an unranked
  search returns the first shape it meets, which puts the low E at fret 0–1, below
  `NECK_FRET_MIN`, and an earlier "0 of 22, never selected" reading was that bug. And
  ranked correctly it still lost — `voicing_cost` reached the neck-position term first
  and declined the better bass, so it wins only where the two shapes tie outright. Hence
  the root-or-5th bass term at index 6, a *tie-break* below every correctness criterion,
  which is what finally lets `5-x-5-5-5-x` (A2 G3 C4 E4) beat `x-3-5-2-5-x` (A2 E3 C4 E4).
- **A partial harmonisation is a fallback, not a style.** `missing` voices outranks neck
  position in the cost, so a complete chord wins even when a shell would have held the
  position better. The term counts the voices: a four-note shape scores 0, a shell 1 and a
  duo 2, so **a duo loses to a shell** wherever both are playable. That ordering is the
  arranging guide's — a shell sounds the 3rd *and* the 7th and a duo only one of them, so
  the shell is the fuller statement and the duo is the fallback beneath it.

  This paragraph used to claim a permitted root-or-5th duo "scores zero there and
  competes on equal terms". It never did: `missing` is `4 - len(active)` and nothing
  exempts a duo. Measured, adopting that claim would move 33 of 463 corpus steps (7.1%)
  and take **7 of them from shells** — inverting the very ranking the guide-tone argument
  requires. The code was right and the sentence was wrong, so the sentence is corrected
  and the cost tuple is untouched.

The window is a **penalty, not a filter**: a step with no voicing inside frets 2–13 is
still played, just outside it. A filter would silently drop every step whose melody
has no in-window shape, and losing a chord of the tune is worse than being a fret out
of position. `tests/test_grips.py::TestFretWindow` pins that.

## Texture: chords on the beats, fills between

`voicing_cost` ranks **completeness above position** and knows nothing about where in
the bar a note falls, so the `eighths` skeleton — one slot per eighth — produces eight
re-struck four-note chords per bar. That is a chord list. `tabstaff`'s `collapse`
hides it in the *drawing*; the selection never made the decision.

`texture="targets"` is that decision. It is the arranging guide's method — full chords
on the principal melody notes, something lighter in the gaps — expressed as **a change
to what may be played**, never as a change to what is preferred.

Five decisions are load-bearing:

- **Timing narrows the candidate set; it does not touch the cost tuple.** "Play fewer
  notes here" is not a preference competing against "stay in position" — it is a
  change of what is on the table. A term in the cost would let a four-fret position
  outbid an entire texture, and it would make the "priorities must not be traded
  against each other" property of `voicing_cost` untrue. `TEXTURE_GRIPS` maps
  texture → role → permitted grips, and `arrange_progression` passes the role's tuple
  to `prepare_step`, which already took `grips`. Generation and selection stay
  separate exactly as they already were.
- **"No timing" is not "a weak note".** `_metric_weight` returns **-1** when `bar` or
  `beat` is `None`, and `_roles_for_slot` treats anything below zero as a target. This
  is the single line that makes the feature opt-in: with `timings=None` every slot is a
  target and the output is byte-identical to what it always was.
  `tests/test_texture.py::TestBackwardCompatibility` pins that against the exact tab
  of the library's own demo cadences, and it was written *before* any behaviour
  changed so every later step is checked against pre-existing output.
- **A beat is a counting position, not a quarter note.** `TARGET_BEATS = (1, 3)` names
  beats, and `beats_per_bar` decides which exist, so a 3/4 head targets 1 and 3 while
  a 2/2 head has only the downbeat. The comparison uses `_BEAT_EPSILON` because a
  notated beat is a float — a 3/4 bar's second beat is 1.666… — and the earlier draft
  of `_metric_weight` compared the *tuple index* against `beats_per_bar`, which let a
  2/2 bar inherit 4/4's second target. `headxml.arrange_xml_head` passes
  `head.beats_per_bar` through for this reason, and three of the five committed scores
  are in cut time — `The_Jitterbug_Waltz.musicxml` is the 3/4 one, and it is the reason
  a rule stated only in quarters would pass on 4/4 and fail on a waltz.
- **A fill that cannot be filled becomes a target.** If a weak beat has no shell,
  interval or melody-alone voicing, the step is re-prepared as a principal note and
  its `role` is corrected to match. The texture is a lighter *texture*, never a missing
  harmony — the same argument that makes the neck window a penalty rather than a filter.
  Measured over melid 218, 2 of 30 weak slots take this path, so the reported role and
  the sounding shape must be allowed to disagree with `metric_weight` but never with
  each other.
- **A target that cannot be *played* becomes the melody alone.** The mirror of the rule
  above, and it exists because `targets` offers a target only `("drop2", "drop3")` — so a
  narrow shell is not merely outranked on such a step, it is **never generated**, and the
  cost tuple would not have chosen it anyway (`missing` is index 2, above span). Ebmaj
  under G4 in "But Not For Me" is the real case: the engine can sound `x-x-8-8-8-x`
  (span 0) there, but the only complete option a target is offered is `x-6-5-3-8-x`, a
  five-fret stretch. The step falls back to the melody alone, and warns.

  It is a **fallback, not a re-ranking**, and deliberately the last thing tried. Lowering
  `GRIP_MAX_SPAN` is a filter that deletes the voicing everywhere; promoting span above
  `missing` would dissolve the shell and duo families across the whole library. Here a
  complete chord is still what you get whenever it is playable, and only a shape at the
  very top of the budget is demoted. The demotion target is the melody alone rather than
  a shell because a shell is only reachable when the role's palette contains one, and
  where it does not — a `targets` target — there is nothing to demote *to*.
  `melody_only` stays **False**: the step does have a harmony, it is simply not spelled
  out, so the flag would make the annotation claim "no chord".
- **`grips` is an intersection, not an override.** A caller's `grips` used to be
  discarded outright by any non-uniform texture (`slot_grips = texture_grips[role]`), so
  `--grips shell --texture targets` asked for shell-only and silently got a four-note
  drop-2 on every strong beat. It is now the intersection of the caller's restriction and
  the role's palette, in the caller's order; `GRIP_PREFERENCE` intersects to the full
  palette, so the default is untouched. An **empty** intersection is a caller asking for
  a grip the texture never uses: the step still sounds, and says so on stdout.

  Both entry points need this — `arrange_progression` and
  `arranger.slots.arrange_slots` — because a head read from a file takes the second
  and a hand-built progression the first. They are no longer two loops, so this is
  a request built in two places rather than a policy applied twice: fixing only one
  would leave the same flag behaving two different ways depending on the entry point.
- **An `interval` is a texture; a duo is a harmony.** Both are two notes under the melody,
  and they are now offered under any melody degree, so the degree no longer distinguishes
  them. What does is the rule that builds them. An interval is not claiming the chord, so
  its second voice is whichever of a 3rd, 6th or 10th it can reach — falling back to the
  **major scale's** pitch classes when the melody is not in the chord, because a diatonic
  note is accompaniment and a chromatic one would be reharmonising. A duo *is* claiming
  the chord, so its second voice is the chord's guide tone and nothing else. Confining an
  interval to fill slots via `TEXTURE_GRIPS` is what makes its looser rule safe.

`_step_annotation` names the interval it actually is ("6th"), not the grip, and it
takes the existing precedence for free: a non-chord tone's substitution is annotated
instead, which is the more important fact about the step. `format_tab_staff` has **no**
annotation channel at all — the line above the staff carries chord names only — so
there the guarantee is simply that it draws the shape that sounds.

### Measured, over six corpus heads

| texture | mean sounding notes per melody note | share of steps in four voices |
|---|---|---|
| `uniform` (before) | 3.86 | 86.7% |
| `targets` | 3.39 | 50.8% |

Every head moved the same way, and none of them lost a step: melid 218 (Blue Train)
goes 4.00 → 3.42 notes per note and 100% → 55% four-voice steps, melid 266 3.97 → 3.34
and 96.6% → 48.3%. The ~50% ceiling is `TARGET_BEATS` itself — two of four beats — plus
the small number of fills that fall back. That is the trade the guide describes: the
chord is stated where it counts and the rest of the bar moves, instead of every note
carrying four voices.

## Repeated melodies hold the shape

When a step's melody sounds the same pitch as the step before it **and the harmony
under it is unchanged**, the step is played as a **single note**: the soprano string is
struck alone and every other string is left blank. Restriking the whole chord is harder
than the music needs, and it is how a player actually reads a held melody.

The Weimar transcription of "All the Things You Are" is the motivating case: at bars
61–63 it holds C4 across three chord changes (F-7, Bb-7, Eb7). The repeated Eb7 is a
genuine hold — one strike, then the note alone. The two *changes* underneath it are not.

The decision is deliberately **presentational, not a voicing change**:

- `arrange_progression` still generates a full `Voicing` for every step. The
  engine voice-leads from it, `midi_notes()` reports it, and a caller wanting the
  literal shape still has it via `step.tab_line()`. What changes is that
  `ArrangementStep.repeated` is set, and the renderers honour it.
- The flag is set by comparing **sounding pitches** (`max(midi_notes())`), not written
  note names, because either step may itself have been transposed down an octave by
  the `HIGH_FRET_LIMIT` rule. A run of four identical notes under one chord yields
  `[False, True, True, True]`.
- **The harmony must also be unchanged.** A note repeating across a *chord change* is
  not a hold: the ringing inner voices belong to the chord the hold began on, so
  printing the new chord's name over a single struck note claims a harmony that is not
  sounding. Those steps are harmonised against the new chord and struck in full, which
  is what the engine already does — only the rendering used to discard it.
  `normalised_harmony()` supplies the comparison: `harmonized_as` when a strategy
  substituted a chord, otherwise the written name, canonicalised to `(root, quality)`
  so `D-7` and `Dm7` are one chord rather than two. The `-7` suffix is an alias of
  `m7` for exactly this reason.
- A **melody-only (`NC`) step is never marked repeated**: it has one active fret and
  no inner voices to hold, so the flag would mean nothing.
- `collapse` in the staff renderer compares sounding pitches, so an unchanged shape
  is normally suppressed entirely as a *hold*. A repeated step overrides that and still
  strikes, because the melody is genuinely re-articulated.
- `_step_annotation()` adds `(melody repeated - single note)`, because the
  chord name printed above a single note would otherwise imply a full voicing. The
  annotation is shared with `format_progression`, so the two cannot disagree.

The other strings are **left blank**, not marked `x`. The player is not being asked
to mute anything — the strings are simply not part of this step, and five `x` say more
than the gesture does. This reuses the blank the staff and HTML already use for a voice
that is not struck. Two earlier drafts were both wrong: `~` ("let ring") across a chord
change, and then `x`, which overstates the instruction.

The HTML marks the whole column with `_CLASS_REPEAT` (`td.repeat`) and tints it. The
cells are otherwise empty, so without the tint a repeated note reads as a gap in the
music rather than as a deliberate single note. The ASCII staff needed no equivalent,
because a gap in a fixed-width cell is already legible.

## High melodies move down an octave

The user requirement was "anything over the 13th fret, play the soprano on the B
string and move the harmonisation down". The trap is that this is **not** a
re-stringing: the B string is five semitones below the high E, so the same written
pitch sits five frets *higher* on it (`D5` is fret 10 on the high E, fret 15 on the
B). Simply choosing the B string would move the voicing *up* the neck, and for
anything above `F5` the B string cannot reach the pitch at all (`B3` + 18 frets =
`F5`). Dropping the melody an octave is the only thing that actually lowers the
position — it lands a major tenth below where the note sat on the high E.

| name | role |
|---|---|
| `HIGH_FRET_LIMIT = 13` | the neck position above which the move happens |
| `get_octave_down_candidates(...)` | candidates for the melody an octave down, B string only |
| `_lower_soprano_strings(top_strings)` | the soprano strings below the high E, so the transposed note is not put straight back on the high E |
| `ArrangementStep.original_melody` | the written pitch, when the step was transposed |
| `_note_name(midi)` | spells a MIDI number (`Bb5`); `musthe.Note` parses strings only, so a transposed pitch must be spelled before it can be rebuilt as a `Note` |

Three decisions are load-bearing:

- **`get_all_drop2_voicings` stays pure.** It neither filters by fret nor
  transposes, so it and `get_octave_down_candidates` cannot recurse into each other.
  Filtering it was tried first and broke the documented "both families are offered"
  contract that `tests/test_voicings.py::TestMelodyStringChoices` asserts.
- **The guard requires candidates to exist.** This repositions a voicing that is
  playable but too high; a melody unreachable at the written pitch (`B5` is fret 19,
  `C6` is fret 20 — past the end of the board) is still skipped with a warning.
  Silently respelling it would hide a real problem behind a plausible-looking tab.
- **The transposition is reported from the sounding pitch, not the fret.** The
  octave-down note lands at a *lower* fret, so a fret comparison would read it as
  untransposed. `max(voicing.midi_notes())` is the reliable test.

**Known limitation.** The decision is per step and applies to the melody only, so a
melody leaping across the limit can arrive an octave apart from its neighbour. This
is deliberately unlike the removed corpus loader's `--lift auto`, which transposed a whole head at
once; `--lift auto` cannot tear the line apart, and this can. The trade is
deliberate: no step is ever left unplayable, at the cost of one melodic interval.


## Known limitations

- Voicings use two to four strings, never all six. The melody may be on the high E, B
  or G string; the A string and low E are inner voices only, so no grip puts the
  soprano on either. There are no barres. Fret `0` does appear when a voice happens to
  land on an open string (e.g. `x-2-3-0-3-x`). 6-4-3, 5-3-2 and 6-4-3-2 are the
  non-contiguous sets.
- Melodies are still confined to `G3`–`Bb5`: `G3` is the lowest pitch reachable on the
  G string, `Bb5` the highest on the high E string. The *chord* range reaches further
  down, to `E2` as a bass voice on the low E string in a 6-4-3 shell.
- **A fixed max fret span of 5 rules out close position and drop-3 entirely.** A
  close-position four-note chord under a melody spans a seventh or more, and the four
  strings below the high E are only five semitones apart in tuning, so the frets come
  out more than five apart (Cmaj7 close under C5 wants frets 8, 12, 12, 14); drop-3
  spans a twelfth by construction. The generators exist for a caller who widens
  `GRIP_MAX_SPAN`, but neither is offered by default because the span invariant could
  never keep the promise. Raising the span to admit them is a real change to the
  library's playability contract, not a tuning knob.
- **A chord tone with no matching inversion in the drop-2 tables falls through to the
  quality-only fallback**, which can sound a note the chord does not contain — a 9th in
  the melody of a 13 chord, for example. `voicing_cost`'s first criterion rejects such a
  shape whenever a correct one exists, so an *arrangement* only hears one when nothing
  else is playable, but `get_drop2_voicings` still offers it. Completing the tables is
  a separate piece of work and would change the published drop-2 output.
  `tests/test_grips.py::TestKnownTableGaps` pins the gap so it stays visible.
  Measured over 25 transcriptions after the head-path fix, **26.0%** of head steps still
  carry an inner voice outside the sounding chord, against **23.0%** for the same
  progressions through the library. The two are close, which is the point: the head
  path is no longer a second, weaker implementation of the same rule.
- A melody that can only be voiced above `HIGH_FRET_LIMIT` is moved down an octave,
  so `step.melody` can be an octave below the written note. The decision is per step
  and applies to the melody alone, so a leap across the limit can leave one melodic
  interval an octave wide — unlike the corpus loader's `--lift auto`, which transposed a whole
  head at once. See
  [High melodies move down an octave](#high-melodies-move-down-an-octave).
- A fixed max fret span of 5 and fret range 0–18 is assumed.
- Non-chord melody notes are only covered for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths and the
  half-diminished 9th) plus the dim7 substitution. An unmapped non-chord tone prints
  a warning and keeps the legacy quality-only fallback, which can sound the melody
  over a different chord's shape.
- A handful of low melodies (around `G3`–`C4`) reach no chord-tone-matched inversion
  and therefore use the quality-only fallback. Triad shapes double the root, so their
  second voice can sit up to 10 semitones below the melody — the same span limit, not a
  new failure mode.
- **A partial harmonisation means the printed chord name is not every note sounding.**
  Where a shell or a duo is used, the chord describes the harmony rather than the full
  voicing, and `_step_annotation` says so (`(shell - 3rd & 7th, partial)`). The full
  shape is still in `step.voicing`. This is a consequence of the user's own brief —
  "just harmonising with the 3rd and 7th is fine" — not a defect, but it is a real
  thing to know before reading a tab.
- The `sustain` strategy is structural, not rhythmic: `arrange_progression` takes
  only `(note, quality, name)` triples, so it cannot tell a brief passing note from
  an accented tension. Holding the inner voices is applied whenever the shape can
  physically stay put.
- `7b9`/`7alt` are voiced rootless apart from their new root-in-top inversion;
  other omitted tones (e.g. a root-on-top `13`) have no template yet.
- If no voicing matches a melody/chord, `arrange_progression` prints a warning
  and **skips** that step (rather than raising).
- **Texture (`texture="targets"`):**
  - **The target-note rule is a fixed `(1, 3)`.** There is no way to say "chords on
    beat 1 only", or "fills on beat 2 as well", or to mark a bar that is all target
    notes — a cadenza or a shout chorus, say. The rule lives in one function
    (`_roles_for_slot`) and one table (`TARGET_BEATS`), which is where a change would
    go, but neither is configurable per call.
  - **A fill that cannot be filled becomes a target.** Measured over melid 218, 2 of
    30 weak slots take this path, so a `targets` arrangement is not uniformly thin: a
    reader looking for "chord on the beat, nothing between" will still find a few
    full chords between. That is deliberate — see the section above — but it means
    the texture is a *tendency*, not a guarantee.
  - **Strong-beat fingerings differ from a `uniform` arrangement.** A target is
    voice-led from the shape before it, which is now thinner, so it does not keep the
    same position. Correct, but it means the two textures are not comparable
    fret-for-fret.
  - **The `interval` grip's diatonic fallback assumes a major key.** `_interval_offsets`
    reaches for major-scale pitch classes when the melody is outside the chord, which
    is right in most standards and wrong in a genuinely modal passage, where a
    non-diatonic note may be the *point*. The `key` argument the plan anticipated was
    not added: nothing in the pipeline supplies a key, and inferring one from the
    chord progression would be a guess.

### Melody alone: `voices=soprano` and `voices=soprano,bass`

Two selections that answer "lead sheet in, the tune out". `melody="soprano"` plays the
melody and nothing else, and `melody="soprano,bass"` plays the same line with a walking
thumb under it and still nothing harmonising it. Neither is a *grip*, for the reason
above: what they change is which voices sound at all, and a grip would have to win a
cost comparison it should not be in. They were the `melody` and `melody_bass` textures
until the fact moved to the voices axis — the question `voices=` answers — which is
`docs/one-fact.md`'s own subject.

The declaration is the empty palette on **both** roles — the same word
`TEXTURE_GRIPS` already used to mean "the left hand plays nothing here", handed to the
step loop directly for a melody-only selection (`melody_only_selection` in
`textures.py`) so the declaration arrives at `melody_alone_case` through the one channel
it always had. The route is `get_melody_only_voicing`, and the step it builds keeps
`melody_only=False` — the harmony still exists and the chord name is still printed as
context, so the flag that would annotate "(no chord - melody alone)" would be claiming
something false.

Three decisions are load-bearing:

- **One predicate names the selections, derived from the quartet.**
  `melody_only_selection` reads the resolved voices — soprano present, alto and tenor
  absent — and every site that decides "does this slot become a single note" reads it
  through the same channel: the empty palette the loop hands the step loop,
  `BASS_AUTO`'s rule, `should_promote_fill`'s `melody_only=`. A site naming a texture as
  a literal is how a spelling joins the melody-alone route in one place and misses it
  in another.
- **The empty tuple is the declaration; it is never absent.** `()` and a missing key
  mean opposite things — "the left hand plays nothing" against "this role is
  unhandled" — so the assertion is over the *set* of empty palettes, not over the
  presence of one. That set is `walking_bass`'s fill alone since the melody-only
  palettes left it for the selection, and `tests/test_texture.py` asserts the one
  entry and the tables behind it.
- **A solo note is one string, and that is inside the playability invariant.**
  `supported_string_sets()` lists the six singletons; a melody-alone step has one
  active fret. That has always been true of an `NC` bar and a walking-bass fill; a
  selection that builds an entire output on it makes it a headline, so it is stated
  and pinned in `TestMelodyOnlySelections` rather than left implied by a test that
  happens not to look at it.

The two selections differ in exactly one thing — the thumb line — which is what makes
them one selection plus a `bass=` answer rather than two spellings: `soprano,bass` is
`soprano` with the thumb named, and `BASS_AUTO` reads the selection (the table below).

### The bass policy: `bass=` as its own axis

The thumb line used to be part of a texture's *name*: `walking_bass` meant both "a
shell on the strong beats" and "a note on every beat below". Two separable decisions
wearing one identifier. It is now `texture=` (the left hand) crossed with `bass=` (the
thumb), with `BASS_AUTO` resolving from the texture and the voice selection so nothing
has to be rewritten:

| texture | default bass | equivalent to |
|---|---|---|
| `walking_bass` | `walk` | `texture="walking_bass", bass="walk"` |
| everything else | `none` | `texture=..., bass="none"` |

and on the voices axis, a melody-only selection that names the bass voice walks too:
`melody="soprano,bass"` and `melody="soprano", bass="walk"` are the same arrangement
— the old `melody_bass` texture under its new spelling — while `melody="soprano"`
alone keeps no thumb. A lone `melody="bass"` selection keeps none either: that part
already is the bass line, and a thumb under it would double it.

All the equivalences are asserted byte-for-byte against the rendered tab, which is
what makes the axis safe to add: every published walking-bass output is pinned against
the `auto` default, so nothing moved.

**The policies are a registry, not a flag**, because the set of patterns is open and is
meant to stay that way. `BASS_POLICY_ROLES` maps a policy name to the `BASS_ROLE_*`
values it keeps, and `bass_line_for` applies it as a *filter over the roles
`_walking_bass_line` already assigns*. So:

- `walk` keeps every role — a note on every beat.
- `anchors` keeps only `BASS_ROLE_ANCHOR` — a root where the harmony changes.

`anchors` is deliberately **not a second generator**. The harmonic reasoning about what
a bass note is *for* is written once, and both policies inherit it; they cannot drift
apart because one of them is a subset of the other by construction. A pattern that
needs new reasoning gets its own generator beside `_walking_bass_line` and a row in the
table; a pattern that is a rhythm of an existing one is a row.

`BASS_AUTO` is deliberately **not** in `BASS_STYLES`. It is a default for an argument,
not a pattern, so keeping it out means `arrange_progression` validates `bass` against
the policies and never has to special-case a sentinel. An unknown spelling raises
rather than defaulting to a walk.

**One refusal rule, derived rather than listed: a thumb line needs one free bass
string.** `thumb_capacity` computes it from `TEXTURE_GRIPS` and `GRIP_STRING_SETS` — the
left hand's palette is the whole question — so a texture added later cannot reach the
thumb-line route without its capacity being measured too. Measured here:

```
a walking_bass fill                        all three free
targets, a walking_bass target             one
uniform                                     one, and **zero** until the four
                                           inner-skip `drop24` sets were removed
```

A melody-only **selection** is not in the table at all: its upper shapes are single
frets, so all three thumb strings are free whatever the texture's palette says, and
`bass_allowed` answers its capacity unbounded when the route is known.

**Nothing in the tree is refused any more, and that is a consequence of the grip tables
rather than of this rule.** `uniform` used to be the one that failed: its palette held
`drop24`'s `(4,2,1,0)`, the one reachable set that spanned all three thumb strings, so
`bass="walk"` under the default texture was refused with a warning naming a texture that
would work. Removing the four inner-skip `drop24` sets for the right-hand reason in
[fingering.md](fingering.md) §4.4 removed that set with them, so the worst case anywhere
is now one free string — the rule's threshold — and `uniform` carries every policy. The
refusal and its reason string stay, because the question is still the right one: the
comping route is answered by `comping_capacity`, and a palette added later that reaches
the whole thumb range is caught here without this function being taught about it.

Two honest caveats, both measured rather than assumed:

- This is the **worst case across the sets a grip may use**, and in practice the
  selector rarely picks the worst one. On "But Not For Me" every `uniform` step still
  left a string, even under the old tables that made the refusal fire. The rule is
  deliberately conservative: it refuses a combination that would usually work rather than
  shipping a line that is occasionally holed.
- **A thumb line is lossy under any four-note or shell texture, and always was.**
  Measured on "But Not For Me" bars 1-2: `walking_bass` loses 9 of 151 thumb notes (6.0%)
  — that is pre-existing behaviour, not something this change introduced — and `targets`
  loses 11 of 151 (7.3%) under `walk`, 7 of 88 (8.0%) under `anchors`. The two melody
  textures lose **none**, because a single left-hand note leaves every thumb string
  free. So the rule was aimed at the one combination that can *never* work and let the
  others through with their existing warning, rather than refusing a texture whose loss
  rate is the same order as the flagship's — and the one it did refuse lost the set that
  made it fail, so the rule now has nothing to fire on.

**The other half of the budget: four fingers on the right hand.** A thumb line needs a
free bass *string*; it also needs a free *finger*, and those are different questions.
The right hand plucks with thumb, index, middle and ring — `p-i-m-a` — so a step may
sound four strings and never five. `thumb_capacity` only ever answered the first:
`targets` has a free thumb string, so `bass_allowed` let the axis through, and then a
**four-note** target had a bass note merged under it — five plucks at once. Measured over
the six committed heads before this was fixed, `--texture targets` sounded five strings on
**151** steps under `--bass walk` and **130** under `--bass anchors`; `walking_bass` and
`uniform` sounded none, the first because its targets are shells and the second because
the axis is refused there.

The rule is `grips.thumb_safe_grips`, derived from `GRIP_STRING_SETS`: while a bass note
is being placed under a slot, a **target** may sound at most three strings, and a palette
with none is narrowed to the widest statement that leaves a finger free
(`("drop2", "drop3")` → `("shell",)`). It narrows *this slot's* palette rather than the
arrangement's, because `anchors` leaves most beats bare and a target with nothing
underneath it may use all four strings. Measured effect on the same heads:

| row | before | after |
|---|---|---|
| `targets --bass walk` | 151 five-string steps | **0**, and byte-identical to `walking_bass --bass walk` |
| `targets --bass anchors` | 130 | **0**, with 9 drop-2 and 19 drop-3 targets kept where the thumb plays nothing |
| `walking_bass`, `uniform`, `targets --voices none` | 0 | **0** — unchanged |

`walking_bass` does not move because the texture had already made this decision; its
target palette is `("shell",)` for exactly this reason, and its comment says so. What the
rule costs: a target whose quality has no shell — `Bmaj` under a `D5` melody, say — is a
melody alone over the thumb rather than a four-note shape nobody can play, which is the
outcome `walking_bass` has always had. See [open-issues.md](open-issues.md) item 11.

### `voices=` as a third axis: which voices the guitar plays

`bass=` answers *who plays the bottom*. `voices=` answers *which voices this instrument
sounds*, and it is an axis of the same kind rather than a mode — a band setting is a
**combination**, not one name.

| axis | question | values |
|---|---|---|
| `texture=` | where notes fall, how thick the left hand is | `uniform`, `targets`, `walking_bass` |
| `bass=` | the bass voice | `none`, `anchors`, `walk` |
| `voices=` | which voices the guitar plays | any subset of `soprano`, `alto`, `tenor`, `bass`; `soprano` alone is the tune and nothing else |

**The four names are the SATB quartet, and they are the argument's whole grammar.**
`--voices` takes a **comma-separated list**, not one identifier out of a fixed set, because
the useful combinations are named by the *arranger* and not by us — and because the
question a player asks is never "how many notes" but "which voices am I playing".

| `--voices` | the part |
|---|---|
| `auto` *(default)* | all four voices: the historical chord-melody |
| `soprano,alto,tenor,bass` | the same, said explicitly |
| `none` | shorthand for **`alto,tenor`** |
| `alto,tenor` | the two middle voices: the ensemble comping part |
| `alto` | one voice |

`none` is **not** "the guitar plays nothing" — that would be silence, and silence is not an
arrangement. It is the ordinary ensemble answer: the tune belongs to the horn, the root to
the bassist, and the guitar takes the voices in between.

**`parse_voices` returns a canonical tuple, highest voice first, deduplicated.** So
`tenor,alto` and `alto,tenor` are one request and not two that happen to agree, and a
policy row and an argument can be compared with `==`. Whitespace and case are the caller's
business, not the parser's. An unknown name raises: a spelling nobody recognises is a
question, and answering it by dropping the voice would hand back a part missing something
nobody asked it to drop.

**`MELODY_AUTO` resolves to `VOICES_ALL`, so the axis is inert until asked for.** Every
pre-existing test passes unchanged and no published arrangement moves.

**One asymmetry with `BASS_AUTO`, stated rather than implied.** `BASS_AUTO` reads the
texture, because `walking_bass` *means* a thumb line. **No texture means "somebody else
sings"** — that is a fact about the band, not about the texture — so `MELODY_AUTO` resolves
to the historical behaviour unconditionally, and no texture implies it.

**`MELODY_POLICIES` is a registry, not a flag**, for the reason `BASS_POLICY_ROLES` is: the
set of patterns is open and meant to stay open. A named comping pattern — Freddie Green,
Charleston — is a **row**, not another branch at each of the call sites that decide which
voices sound. Each row states the voices it keeps using the same four names a caller
passes, so the table and the argument vocabulary cannot drift apart.

### `get_comping_voicings`: a chord with no melody on top

The generator behind `voices="none"`. **It is `_place_shell`'s own search with nothing held
at the top.** A shell is already a claim about the chord's 3rd and 7th rather than about
the tune, so `_place_shell` needed no change: it already tries every fret combination on
the remaining strings and keeps the ones where both guide tones sound and nothing outside
the chord does. The only difference is that the top fret is searched too rather than fixed
by a melody. Because the window is exactly `GRIP_MAX_SPAN["shell"]`, the search stays
*exhaustive within the playability invariant*.

The shared half is factored into `_shell_voicing` so the melody-bearing shell and the
melody-free one cannot drift apart on what counts as a shell.

**It takes no melody argument, and that is the invariant rather than an accident.** Asking
it for `D5` and for `G3` under the same chord returns the **identical candidate set** — a
generator that read the melody could not do that. `tests/test_comping.py` asserts exactly
this, over eight melody notes and three chords.

**The arity is the length of the selection, and it is honoured.** `notes` says how many
voices the guitar was asked for, and a two-voice request is **two notes**. The first
version of this generator always built a three-note shell, so `--voices alto` and
`--voices alto,tenor` both came back with three — a part sounding a voice nobody named,
which in a band setting is a voice another player was supposed to have.

**The arity picks the grip family rather than truncating one.** Truncating a `shell` set to
two strings looks free and is not: it yields pairs the library has never measured —
`(0, 2)` skips the A string, `(5, 3)` skips the B — and they would enter the tab as though
they had been designed for the job. A two-note shape is a `duo`, the family this library
has always offered for exactly that, so two voices take the `duo` sets and three take the
`shell` sets unchanged.

**One voice is a weaker claim, and the rule says so rather than refusing.** Two notes can
sound both guide tones, which is what states the chord; one note cannot, so a single note
keeps the **first** guide tone (the 3rd, or the 4th on a sus chord) — the same preference
order `_duo_offsets` already applies. Refusing instead would have made `--voices alto` fall
through to the melody-bearing route: measured, it warned on every step and handed the
horn's line back to the guitarist, the opposite of what naming one voice asked for.

**With no melody to support, a fourth voice would be the root or the 5th** — the two notes
that carry no information about the chord's quality. That is why only the `shell` family is
offered at all.

**A quality with no readable root gets nothing**, on the same rule as every other
guide-tone generator here: a shell is a claim about *this* chord's 3rd and 7th, and guessing
them without a root is how a wrong note gets into the tab.

**The playability invariant, minus the melody clause.** Every candidate sounds only chord
tones, sounds exactly the number of notes asked for, occupies one string set from the
matching family, and holds a span within that family's `GRIP_MAX_SPAN`. The dropped clause
is "the melody is on the topmost string", and it is dropped for the only reason there is:
there is no melody.

Measured over three corpus heads under `--voices alto,tenor` — 2,069 steps:

```
notes per step          2        (2069 of 2069)
melody_voiced           False    (2069 of 2069)
supported string set    yes      (2069 of 2069)
over GRIP_MAX_SPAN      0
wrong notes             0
guide tone missing      0
unreadable chord        610      (no tone set at all; the library's own rule is not to
                                  judge a chord it could not read - see cost.voicing_cost)
```

**What is *not* claimed, measured rather than assumed.** A comping step may well contain the
melody's own pitch: **409 of 2,069 corpus steps do.** That is coincidence, not the guitar
singing — the melody's pitch class is often a chord tone the shell needs anyway. What the
axis guarantees is that the shape was *chosen from the chord alone*, and that
`step.melody_voiced` is `False`. An earlier version of this document and of the test suite
claimed the stronger, falsifiable version ("no step sounds the melody"), and the
measurement is what corrected it.

### The renderer rule: a repeated melody holds the whole shape

Normally `repeated` is a **soprano-only re-strike** — the melody re-articulates under an
unchanged harmony, so the inner voices are held. That presumes there *is* a soprano
carrying the tune. Under `voices="none"` there is none, so "re-strike the soprano" would
re-strike a guide tone and the shape would change on a beat where nothing has. The rule
becomes **hold the whole shape**, which is what a guitarist comping behind a horn does while
the horn repeats the note.

This is not a corner case. Measured over 2,243 corpus steps, **152 carry `repeated`**, and
keeping the old rule rendered every one as a single moving note — a melody line on the
guitar part, on exactly the beats where the arrangement had handed the tune away.

The rule is stated in **two** places, `render._step_cells` and `tabstaff._strikes_here`,
because those two are what keep the one-line renderer, the ASCII staff and the HTML from
disagreeing about what attacks. `tests/test_comping.py::TestRepeatedStepsHoldTheShape`
asserts they agree, string by string.

### Two consequences, both derived rather than listed

**A texture that harmonises nothing cannot also give the melody away — and no texture
harmonises nothing any more.** The refusal `melody_allowed` used to make —
`voices="none"` on a texture that *was* the melodic voice — dissolved when the
melody-only claim moved onto the selection: a soprano-less selection simply comps, on
every texture, and nothing is self-contradictory anywhere. The equivalent fact on the
selection axis is `melody_only_selection`, which is derived from the quartet rather
than listed, so a spelling that cannot be voiced cannot miss it either.

**`melody_alone_case` gains a guard, because its routes all end at the melody alone.** Every
answer it gives reaches `get_melody_only_voicing`, so under `voices="none"` it must not
answer `MELODY_ALONE_TEXTURE` — or a texture *fill* would put the tune straight back on the
guitar, and the axis would be honoured only on targets. Measured: before the guard, every
fill under `--texture targets --bass walk` came back `x-7-x-x-x-8`, a bare melody note.

**An `NC` bar is reported, not quietly dropped.** There is no chord, so there are no guide
tones, and the guitar is genuinely silent while the horn is not. It is skipped with one
sentence naming the reason, rather than reaching the generator (which correctly refuses a
chord with no root) and then falling through to a melody-bearing route that would either
warn twice or hand the horn's line back to the guitarist.




## `grid=` — where a chord falls

`harmony=` answers *which degrees* a stab states; this answers *where one lands*. A
comping style needs both, and `bass=` supplies a third orthogonal question (what plays the
bottom). The vocabulary is `GRID_STYLES` + `GRID_PATTERNS` in `textures.py`, with
`GRID_DEFERS_TO_MELODY` (derived from `GRID_PATTERNS`) and `parse_grid` / `resolve_grid` /
`grid_allowed` / `grid_defers_to_melody` beside the other axes' functions. There is **no
`GRID_AUTO`**: `every_note` is the default outright, and `grid=auto` is refused like any
other unknown name (see [comping-styles.md](comping-styles.md) §9.3).

**Positions are `(beat, eighths)` pairs, and `beat` may be a sentinel.** `LAST` resolves
to the metre's final beat and `ALL` to every beat of the bar, so a pattern names *a
position* rather than a beat number — `final_and` is 2.5 in 2/2, 3.5 in 3/4 and 4.5 in
4/4 from one row. `eighths` is an **integer count of eighths**, not a float, because a
notated position is a float in practice (a 3/4 bar's second beat is 1.666...) and
comparing floats for equality is a comparison that will eventually be false for the wrong
reason — the same argument as `_BEAT_EPSILON`.

| pattern | positions | kind |
|---|---|---|
| `every_note` | **none** — the absence of a restriction | bar-relative |
| `freddie` | `(ALL, 0)` | bar-relative |
| `final_and` | `(LAST, SUB)` | bar-relative |
| `charleston` | `(1, 0), (2, SUB)` | metre-relative |
| `joe_pass` | `(ALL, SUB)` | metre-relative |

**`bar_relative` is a property of the pattern, not a comment.** It says whether a *silence*
is the arranger's mistake: a bar-relative pattern resolves in any metre, while a
metre-relative one is a named figure of a particular metre and is either right or is a 4/4
figure asked of a 2/2 bar. That is the arranger's calling, not an engine defect, and
recording it as data is what stops "the pattern silently did nothing" reading as a bug.

**`every_note` is not a pattern with positions; it is the absence of one.** `grid_positions`
returns nothing for it, so `grid_allowed` must test it explicitly — deriving the check from
`grid_positions` made the *default* warn in every metre, which is the false reading the
check exists to avoid. "Places nothing" and "has no positions to place" are different
claims and only the first is a mismatch.

**The refusal is unreachable through the shipped rows**, measured: every metre-relative
pattern fits every metre, because `charleston` keeps its beat 1 and `joe_pass` is built on
`ALL`. `grid_allowed` is therefore defensive, and the two warning messages are tested
against a temporary row. `tests/test_grid.py::test_no_shipped_row_is_a_mismatch_in_any_metre`
exists to keep that fact from being forgotten — a check no input can fail proves nothing.

**`beat=None` is on the grid.** A slot nobody located has no position to be off, the same
rule `_metric_weight` follows with its `-1`. Without it a hand-written progression — which
carries no timings — would lose every chord the moment a grid was passed, which is the
opposite of an opt-in.

### What an off-grid slot does, and why it is a fourth kind

`decisions.melody_alone_case` returns a *kind*, and the grid added `MELODY_ALONE_REST`
alongside `MELODY_ALONE_NONE`, `MELODY_ALONE_TEXTURE` and `MELODY_ALONE_NO_CHORD`:

- **guitar singing** → `MELODY_ALONE_TEXTURE`: the note of the tune sounds alone. No note
  is dropped, ever.
- **guitar comping** → `MELODY_ALONE_REST`: the guitar is silent. There is no melody on
  this guitar to play alone, and the tune is the horn's. The step is still emitted, so the
  part keeps its bar and beat and lines up against the tune; all six strings are muted, so
  every renderer draws silence rather than a held shape.
- **`NC`** → unchanged per route. It has *no chord to place*, so "off the grid" is not a
  claim about it: the comping route drops the bar with a warning, the singing route plays
  the note alone.

The **ordering of those guards is load-bearing and was got wrong twice** — see
[../AGENTS.md](../AGENTS.md) trap 12 for the three orderings and what each one breaks.

**The grid does not touch the bass line**, and that is orthogonality tested rather than
asserted: measured on `but_not_for_me` with `texture=targets, melody=alto,tenor,
bass=walk`, the walked notes are `[51, None, 52, None]` at both `grid=every_note` and
`grid=freddie`. A grid removes chords, never the thumb.

### What is not built

The **free-form** spelling (naming positions directly rather than choosing a row) and a
**held baseline** (`hold=`). **Both were withdrawn on 2026-10-04, on measurement** — a stab
already lasts as long as the melody note under it, because `step.duration` *is* that
note's duration and every renderer already honours it, so "a held baseline" as a flag
would add a second answer to a question the step model already answers. The real gap is
the inverse one: a stab *outlasting* its note. See
[comping-styles.md](comping-styles.md) §8 Stage D, and
[open-issues.md](open-issues.md) item 10 for the larger thing underneath it — that a grid
can only filter melody slots, so a quarter of the positions it names produce no chord.
