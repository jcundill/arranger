# Engine reference

The voicing engine: what shapes exist, how one is chosen, and what the tables
behind them mean. Read this before touching anything under `arranger/` except
`options.py`.

The module map and the dependency order that holds it are in
[../AGENTS.md](../AGENTS.md), and [dependency-dag.md](dependency-dag.md) draws
that order as a graph; this document is the reasoning behind the decisions,
not the map.

## Architecture and key types

- `tuning` — the instrument: `STANDARD_TUNING` (six open-string `Note`s, low E at
  index 0 through high E at index 5), `STRING_NAMES`, `NO_CHORD = "NC"`,
  `MELODY_STRING_CHOICES = (5, 4)` (high E and B), `MELODY_STRING_CHOICES_FULL =
  (5, 4, 3)` (adds the G string), `NECK_FRET_MIN = 2`, `NECK_FRET_MAX = 13`,
  `HIGH_FRET_LIMIT = 13`, `GuitarFretboard`, `note_name`, `ROLE_TARGET`,
  `ROLE_FILL`, and the `SILENCE_*` constants. The A string and low E are inner voices
  only — no grip puts the soprano on them — so the melody floor is `G3`.
- `step_types` — `Voicing` (frets, top_fret, avg_fret, grip, bass_pc, role,
  bass_midi, bass_string, plus `tab_string()`, `tab_block()`, `tab()`,
  `active_frets()`, `fret_span()`, `midi_notes()`, `pitch_classes()`,
  `soprano_string()`, `upper_midi_notes()`) and `ArrangementStep` (chord, melody,
  voicing, non_chord_tone, strategy, harmonized_as, melody_only, chord_unvoiced,
  original_melody, bar, beat, duration, repeated, partial, palette, role,
  metric_weight, bass_role, top_role, bass_only, bass_held, chord_attack,
  melody_voiced, silence, bass_refused, melody_released). Both support legacy
  dict-style access (`v["frets"]`, `step["chord"]`).
- `context` — `SlotInputs` and its four groups
  (`SlotArrangementFacts`, `SlotRhythmFacts`, `SlotNeckFacts`, `SlotBassFacts`),
  plus `SlotContext` and `Carried`.
- `fingers` — the left-hand budget (`can_fret`); read by `bass_place` and
  `bass_merge` only.
- `chords` — `ChordParser` (`parse_symbol`, `parse_chord_name`,
  `get_chord_tones`, `get_melody_degree`, `quality_of`, `canonical_quality`),
  `CHORD_TONES_FROM_ROOT`, `QUALITY_ALIASES`, `NON_CHORD_TONE_EXTENSIONS`,
  `NON_CHORD_TONE_STRATEGIES`, `is_chord_tone`, `resolve_non_chord_tone`,
  `normalised_harmony`, `slash_bass`, `slash_bass_cost`, `melody_degree_name`.
- `grip_tables` — `GRIP_PREFERENCE`, `GRIP_STRING_SETS`, `TONE_PRIORITY`,
  `SHELL_DEGREES`, `COMPING_MAX_SPAN`, `COMPING_EXCLUDED_STRINGS`,
  `comping_string_sets`, `stated_tones`.
- `grips` — the builders and candidate generators: `get_drop2_voicings`,
  `get_grip_voicings`, `get_all_grip_voicings`, `get_interval_voicings`,
  `get_octave_down_candidates`, `get_melody_only_voicings`,
  `get_melody_only_voicing`, `get_comping_voicings`,
  `get_comping_voicings_for`, `sustain_inner_voices`, `CompingRequest`,
  `BASS_DEGREES_6432`.
- `grip_place` — `search_shape`, `_searched_shape`, `place_shape`,
  `place_template`, `snapshot`, `sounds_distinct_pitches`, `frets_in_span`,
  `frets_in_band`, `Placement`, `ShapeSnapshot`.
- `grips` — the builders and candidate generators: `get_drop2_voicings`,
  `get_grip_voicings`, `get_all_grip_voicings`, `get_interval_voicings`,
  `get_octave_down_candidates`, `get_melody_only_voicings`,
  `get_melody_only_voicing`, `get_comping_voicings`,
  `get_comping_voicings_for`, `sustain_inner_voices`, `CompingRequest`.
- `cost` — `voicing_cost`, `SelectionCriteria`, `best_voicing_for`,
  `VoicingScore` (7 fields: `foreign`, `outside`, `missing`, `span`, `position`,
  `movement`, `bass`), `VOICING_COST_CRITERIA`, `_CRITERION_LABELS`,
  `calculate_voice_leading_distance`, `calculate_pitch_leading_distance`.
- `annotation` — `step_annotation`, `melody_degree_label`, `_silence_clause`,
  `_shape_clause`, `_window_clause`, `_omission_clause`, `_sounding_clause`,
  `_comp_line_clause`, `_comping_clause`, `_bass_annotation`.
- `text_layout` — breaks an annotation into lines beside the tab.
- `parts` — `PART_NAMES`, `parts_have_melody`, `parts_has_melody_only`,
  `parts_have_bass`.
- `grouping` — `TimeSignature`, `COMMON_TIME`, `GROUPING_AUTO`.
- `grid` — `Rhythm`, `parse_rhythm`, `felt_beat`, `beat_offset`, `rhythm_beats`.
- `texture` — `TEXTURE_STYLES`, `TEXTURE_ARITY`, `TARGET_BEATS`,
  `derived_arity`, `roles_for_slot`, `comping_arity`.
- `comp_line` — the comp's home band and walk/approach/opening/fill rules.
- `bass_rules` — `BASS_RULES`, `BASS_ROLE_*`, `BASS_STYLE_NONE`,
  `parse_bass_style`, `resolve_bass`.
- `bass_place` — `place_bass`, `bass_cost`, `is_shape_held`, `thumb_capacity`.
- `bass` — `walking_slots`, `Slot`, walking-bass thumb line.
- `bass_merge` — `carry_bass`, `attach_bass`, `next_resolution_melody`.
- `options` — `Request`, `ResolvedRequest`, `ArrangeOptions`, `resolve_request`,
  `DEFAULT_REQUEST`, `CHORD_NOTES`, `BASS_NOTES`, `CHORD_FILLS`.
- `resolution` — `resolve_knobs`, `resolve_policies`, `_Knobs`, `_Policies`.
- `decisions` — `melody_alone_case`, `is_bass_only`, `melody_is_ringing`,
  `is_repeated_step`, `holds_the_shape`, `hold_the_melody_string`,
  `leaving_room_for_the_bass`, `select_step_voicing`, `tie_ended_by_a_stab`,
  `palette_facts`, `dropped_for_the_bass`.
- `step_history` — `last_sounding_step`, `sounding_tops`.
- `comp_line_route` — what the comp line is told about a slot (band, state, fill).
- `melody_alone` — `get_melody_only_voicings`, `melody_alone_shape`,
  `rescue_melody_alone`, `demoted_to_melody_alone`, where a lone note is fretted.
- `routes` — `rest_step`, `_comping_choice`, `_comping_candidates`,
  `_emit_comping_step`, `_comping_harmony`, `no_chord_step`, `texture_fill_step`,
  `bass_alone_step`, `comping_step`.
- `slot_plan` — `slot_state`, `Carried`.
- `step_prepare` — `prepare_step`, candidate building for a single step.
- `harmonised_route` — the melody-bearing route: prepare, select, demote, emit.
- `route_dispatch` — `dispatch_step`, the five route entries:
  `no_upper_voices`, `texture_fill`, `no_chord`, `comping`, `melody_bearing`.
- `movement` — `arrange_progression`, the step loop; one progression in, one
  arrangement out.
- `steps` — `VoiceLeadingEngine`, the published facade; delegates to `movement`.
- `slots` — `arrange_slots`, the slot layer (triples to steps).
- `render` — `format_progression`, `step_annotation` output; pure renderers.
- `cli` — the shared argparse block and output dispatch.
- `demo` — `main()`, the printing front end.

## Grips

`GRIP_PREFERENCE = ("drop2", "closed", "drop3", "drop24", "drop2_6432", "shell", "duo")`
is both the generation order and the tie-break order for equal-cost shapes. No
criterion in `voicing_cost` names a family, so a tie that runs off the end of the
cost tuple falls to this order alone. A family's place only orders shapes of the
same arity against each other — it never decides how many notes a step sounds
(that is criterion 2, `missing = 4 - len(active)`).

| grip | voices | what it is |
|---|---|---|
| `drop2` | 4 | drop-2, four strings below soprano; generated per degree from `TONE_PRIORITY` |
| `closed` | 4 | close position, tightest four-note shape; offered second on tie-break |
| `drop3` | 4 | drop-3, derived from close stack under melody |
| `drop24` | 4 | drop-2 & 4, second and fourth voices down an octave |
| `drop2_6432` | 4 | 6-4-3-2 block; the only default set that reaches the low E |
| `shell` | 3 | `SHELL_DEGREES` (3rd & 7th) plus one more note |
| `duo` | 2 | guide tone (3rd, or 4th on sus) under any chord tone |

`drop3` and `drop24` matter because a melody that is not a chord tone leaves
drop-2 with no template and no shell — both derive from the close stack and keep
every *other* voice a chord tone. An `interval` (3rd/6th/10th below melody) is
texture, not harmony; it is excluded from `GRIP_PREFERENCE` and offered only for
fills.

## The cost tuple

`voicing_cost(voicing, criteria)` returns a 7-field `VoicingScore`, compared
lexicographically — never a weighted sum:

| index | field | meaning |
|---|---|---|
| 0 | `foreign` | notes outside the chord (melody excepted), counted |
| 1 | `outside` | frets outside `NECK_FRET_MIN`–`NECK_FRET_MAX`, counted (penalty, not filter) |
| 2 | `missing` | `4 - len(active)`; a complete chord wins over a shell over a duo |
| 3 | `span` | `max(frets) - min(frets)`; spans 0 and 1 bucketed together |
| 4 | `position` | distance in neck position from the previous shape |
| 5 | `movement` | total voice pitch movement, semitones |
| 6 | `bass` | 0 for root or 5th in the bass, 1 otherwise; unasked without a root |

`SelectionCriteria` carries `previous`, `fret_min`, `fret_max`,
`allowed_tones`, `root_pc`, `melody_pc`, `bass_pc`. A tie falls to generation
order: `top_strings` first, then `GRIP_PREFERENCE` within one string. `best_voicing`
is the stable argmin; `best_voicing_for` is the single argmin behind both spellings.
The field order is asserted once in
`tests/test_grip_selection.py::TestVoicingCost::test_the_field_order_is_the_rule`;
reordering is a musical decision, not a refactor.

The window (frets 2–13) is a **preference, never a filter**: a step with no
voicing inside the window is still played outside it. Losing a chord of the tune
is worse than a fret out of position.

## The request and the axes

A caller asks six questions; `options.Request` holds them as one value, spelled
twice: by `head`'s flags and by `Request(...)` on `arrange_progression`. `cli._REQUEST_DESTS`
binds the two spellings; `tests/test_request.py` asserts they match.

| question | flag | `Request(...)` | axis |
|---|---|---|---|
| who plays the tune? | `--no-melody` | `melody=False` | `parts` (melody dropped from selection) |
| when does the chord attack? | `--chord-on POSITIONS` | `chord_on="1and"` | chord layer's `Rhythm` |
| what does the chord state? | `--chord-notes full\|targets\|3\|2\|1` | `chord_notes="2"` | texture axis (`uniform`/`targets`/`chord3`/`chord2`/`chord1`) |
| what does it do in a melody rest? | `--chord-fills none\|hold\|comp` | `chord_fills="hold"` | chord slots in the tune's rests |
| when does the thumb attack? | `--bass-on POSITIONS` | `bass_on="every-beat"` | bass layer's `Rhythm` |
| what does each thumb note state? | `--bass-notes root\|root-5th\|walk\|rules` | `bass_notes="walk"` | bass axis (note rules) |

The axes are **derived** from the request, never spelled: `options=ArrangeOptions(...)`
carries knobs that are not a question about the music (`top_strings`, `fret_min`,
`fret_max`, non-chord-tone strategy). `request=` and `time_signature=` are input
facts beside `options=`, reconciled by `resolution.settle_input_fact`.

`resolve_request` → `resolution` runs once before any voicing work; a content
question about a layer the request leaves silent is refused with the reason.

## The step loop and routes

`arrange_progression` (in `movement.py`) resolves knobs and policies once, builds
one slot per progression entry, then walks the slots. Each slot gets a `SlotPlan`
from `slot_plan.slot_state`, and `route_dispatch.dispatch_step` sends it to one of
five routes:

| route | module | emits |
|---|---|---|
| `no_upper_voices` | `routes` | `bass_alone_step` or `rest_step` (nothing above the thumb) |
| `texture_fill` | `routes` | `texture_fill_step` (guitar sings, texture thinned) |
| `no_chord` | `routes` | `no_chord_step` (NC bar the guitar sings) |
| `comping` | `routes` | `comping_step` (guitar does not sing; comps under horn) |
| `melody_bearing` | `harmonised_route` | `harmonised_step` (guitar sings; pin tune, voice chord beneath) |

A route may claim a slot and decline it; the next entry is tried. The last entry
claims every slot, so exactly one step per slot is structural. The bass merge
(`bass_merge.carry_bass`) runs after selection, so a held thumb note cannot enter
the cost tuple.

## Adding a new chord quality

1. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT` — every
   grip family builds from it, so this is required for the quality to be voiced at
   all.
2. Add the quality's tones to `TONE_PRIORITY`, most defining first. Its first two
   entries are `SHELL_DEGREES`' pair; its tail ranks which tone a four-voice shape
   gives up when the chord has more tones than voices. `drop2_template_for`
   builds each shape from the row; `_drop2_palette` offers them per degree.
3. Add aliases to `ChordParser.QUALITY_ALIASES`.
4. For the `extension` strategy, add it to `NON_CHORD_TONE_EXTENSIONS`.
5. For MusicXML spelling, add the `kind-value` to `MUSICXML_KIND_QUALITIES` in
   `headxml.py`, plus any `<degree>` refinement in `_DEGREE_REFINEMENTS`.
6. Add tests: `tests/test_voicings.py` (drop-2 fingerings),
   `tests/test_grips.py` (other grips: exact fingerings, pitch classes subset of
   `get_chord_tones`, `fret_span() <= 5`, sounding strings a member of
   `supported_string_sets()`), `tests/test_non_chord_tones.py` (new extension
   route).

A quality with a tone set but no `TONE_PRIORITY` row gets no drop-2 shapes — `[]`,
not a guess.

## Known limitations

- Voicings use two to four strings, never all six; melody on high E, B or G only.
- Frets 0–18; max span 5 (4 for duo/interval); span is a distance
  (`max - min`), not a count of frets touched.
- Neck window is a preference, not a filter; melodies above `HIGH_FRET_LIMIT` are
  voiced an octave down (`step.melody` may differ from `step.original_melody`).
- Non-chord melody notes are routed only through
  `NON_CHORD_TONE_EXTENSIONS` plus the dim7 substitution; anything else sounds
  alone under its chord.
- No partial-harmonisation fallback that sounds a note outside the chord; a
  `targets` target with no playable complete shape demotes to melody alone.
- `sustain` is structural, not rhythmic: only `(note, name)` pairs, no passing
  tone detection.
- Slash bass is honoured as a preference (palette narrow), never a hard
  constraint.

## Where the reasoning lives

`AGENTS.md` is the module map and conventions. `dependency-dag.md` draws the
import graphs. `docs/history/` holds completed plans (parts, comping styles,
generated grips, fingering, voices axis). `docs/open-issues.md` is the issue
ledger (one open item: item 7). `docs/history/open-issues.md` records the six
closed issues, each with its measurement and re-measurement recipe. Measurements
in this document are tied to pinned tests; where a figure was measured during
development, it lives in `docs/history/`, not here.
