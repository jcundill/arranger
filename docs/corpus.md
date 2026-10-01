# Corpus integration: the Weimar Jazz Database

`wjazzd.py` reads the **Weimar Jazz Database** and turns the head of a
transcription into a chord-melody arrangement. It is a separate, optional module:
nothing in the `arranger` package imports it except the lazy `corpus` branch in
`main()`, so the library still works with no database present.

The measurements the design rests on are in
[history/corpus-plan.md](history/corpus-plan.md), and the issues found since are in
[open-issues.md](open-issues.md).

The database (`wjazzd.db`, 42 MB, from jazzomat.hfm-weimar.de) is **not
committed** — `.gitignore` excludes `*.db`. It is found beside the module by
default, overridable with the `WJAZZD_DB` environment variable or the `db_path`
argument on every entry point. `DEFAULT_DB` is the resolved `Path`.

**No new dependencies.** The module is stdlib `sqlite3` only, per the standing
rule that `musthe` is the only runtime dependency.

### Purpose: the head, not the solo

The default selection is the **head** — the tune — rather than a harmonised
transcription of someone's solo. A transcribed solo is fast, harmonically
unusual, and fights the changes; a head is the opposite. Solos remain one flag
away (`--section chorus:1`) but are not the point.

### The schema is not what the documentation claims

There is **no** `melopy_notes` or `composition_annotations` table, and notes
carry **no chord column**. The real tables are `solo_info`, `beats`, `melody`,
`sections` and `melody_type`; `melody_type` is SOLO-only with no `THEME` value at
all. `sections` has two categorical columns: `type` is the kind of span (CHORD,
IDEA, PHRASE, FORM, CHORUS) and `value` is what the span is.

**Bars can be negative.** 1,335 `beats` rows across 149 transcriptions sit below
bar 0, reaching bar −31 — that is the anacrusis. `bar` is therefore a signed
integer everywhere in the loader, spans are half-open `[start, end)`, and
`--bars` accepts negative bounds.

### Public surface

| name | purpose |
|---|---|
| `WEIMAR_QUALITY_ALIASES` | Weimar suffix → library quality, 108 entries |
| `parse_weimar_chord(symbol)` | → `(root, quality, bass)`; strips the slash; `NC` → `(None, None)` |
| `Section` / `NoteEvent` / `Solo` | the records, with **signed** bars throughout |
| `Skeleton` / `HeadSelection` / `HeadArrangement` | results, each carrying its own diagnostics |
| `list_solos` / `list_sections` / `parse_section_selector` / `matching_sections` | metadata and span selection |
| `load_solo` / `load_section` | notes with each note's chord forward-filled |
| `select_head(melid)` | the head, found on the chord progression |
| `skeleton_slots` / `skeleton` | the reduction, with and without each slot's timing |
| `build_skeleton` / `arrange_head` | reduction, register, voicings |
| `corpus_cli` / `parse_bar_range` | the `corpus` command and its `--bars` parsing |

### The chord is reconstructed by a forward fill

Notes have no chord, so each note's active chord is the last `beats` row for the
same `melid` with a non-empty chord at `(bar, beat) <= (note.bar, note.beat)`.
The comparison is on the `(bar, beat)` **tuple**, so negative bars order
correctly with no special case. Implemented as a binary search over the chord
onsets (`_forward_fill`), because it runs once per note.

Verified ground truth (`tests/test_wjazzd.py::TestChordForwardFill`): melid 1
gives `Bb6`/`G-7`/`F7` at the three checked positions, melid 218 gives `NC`,
`Eb7`, `C7`, and melid 266 resolves chords at bars −12…−1.

### The head is found on the chord progression, not the form label

`select_head` exists because the form label is unreliable. On all four "All the
Things You Are" transcriptions, `FORM A1` starts at the **second** statement and
the real 8-bar head lies inside the preceding `I` (intro) block. The algorithm:

1. **Seed** from the first `FORM` A-block, extended back over a contiguous `I`
   block (`_seed_span`).
2. **Anchor** on the chord progression at the seed's first chord bar.
3. **Trim** to the shortest span that then recurs, matched **modulo
   transposition** — earliest bar first, then shortest period (`_bar_grid`,
   `_is_transposed_repeat`).
4. **Report** the anchor chords and the trimmed length, so the caller can see
   what was chosen and override it.

Three details are load-bearing and were each forced by a measurement:

- **A per-bar grid, not a list of chord changes.** Chords routinely last two bars
  and transcriptions are inconsistent about it, so change lists never line up
  against each other. Each bar holds a *tuple* of chords, because two changes can
  share a bar (Sims's ATTYA puts `D-7` and `G7` both in bar 6).
- **A constant transposition interval is required.** Qualities alone let a blues
  — nearly all dominant sevenths — match itself at any offset; absolute roots
  fail because ATTYA's A section returns a tone higher.
- **`REPEAT_TOLERANCE = 1`.** Analysts do not enter every change a piece is
  usually written with; Konitz's ATTYA omits bar 6's `G7`, so an exact match
  fails on all four transcriptions. Two differences also match unrelated
  progressions, so the default stays at one.

**Known limitation.** The trim is a heuristic. It finds the 8-bar head on melids
266 and 342, but returns a 6-bar fragment on 328 and falls back to the whole
A-block on 451. Across the corpus 434 of 456 transcriptions yield a head and the
**median head length is 8 bars**. A user wanting a specific tune should pass an
explicit `--bars`. This is the open question in `CORPUS_PLAN.md` §12.

### Skeletons, and the register lift

One voicing is generated per *slot*; the strategy decides what a slot is:
`chords`, `beats`, `eighths`, `sixteenths`, `notes`. The grid is derived from
each note's own `tatum`/`division` rather than assumed to be 4/4, so triplet
transcriptions are handled.

`skeleton_slots` is the reduction that keeps each slot's `(bar, beat, duration)`;
`skeleton` is the same thing with the timing discarded, and is what most callers
want. `Skeleton.timings` carries the timings in step with `triples`, and
`arrange_head` stamps them onto the `ArrangementStep`s, which is the only way a
renderer can place a chord on its real beat rather than on an even grid. The two
lists stay the same length by construction — the lift transposes notes but never
drops or reorders a slot, and the diminished fallback acts per step — so
`arrange_head` still guards the index rather than trusting it.

**`eighths` is the default, by measurement.** Across 116 sampled heads the median
voiced-step rate is 85.9% for eighths against 85.6% for sixteenths and 85.7% for
beats — the extra density buys no extra playability, so there is no reason to pay
for it. `chords` voices everything but yields four steps for an eight-bar head,
which is a chord list rather than an arrangement.

`--lift auto` builds the head twice, as transcribed and an octave up, and keeps
whichever voices **strictly more** steps; ties go to the original, so music is
never moved without a gain. This is threshold-free, so a median sitting one
semitone above an arbitrary cut-off cannot defeat it. The whole head is
transposed at once, so no melodic interval can be distorted by construction.
`--lift per-note` is available and warns, because lifting single notes tears the
line apart.

### Slash chords: rules B and C, loader-only

95 distinct slash chords appear in the corpus. `parse_chord_name` glues a bass
onto the quality, so every one of them silently fails the table lookup — the
loader must strip the bass first.

- **Rule B** (`promote_slash_chord`) — a triad whose bass is its own seventh
  implies a seventh chord: `A-/G` → `m7`, `C-/Bb` → `m7`, `D/C` → `m7`.
- **Rule C** (`bass_cost`, `_arrange_step_with_bass`) — prefer the candidate
  whose lowest pitch is nearest the bass. This is **combined** with the engine's
  voice-leading rule, not applied after it: the candidates are partitioned by
  bass cost and the engine then decides within the best group, because sequencing
  them would let whichever ran last always override the other.

Both live in the loader, so the engine's public surface stays frozen and the
394 transcriptions without slash chords behave as if the symbols were stripped.

**The head path shares the engine's step logic.** Only the *selection* is the loader's
business. The candidates come from `VoiceLeadingEngine.prepare_step`, which is also
what `arrange_progression` uses, and the choice is still the engine's `_best_voicing`
with `allowed_tones` supplied. This was not true until it was fixed: the loader used to
build candidates itself and call `_best_voicing` with only two arguments, which skipped
the non-chord-tone strategies, the tone-purity criterion and the `HIGH_FRET_LIMIT`
octave-down rescue. Across 25 transcriptions that left **0** non-chord tones flagged
where the library flagged 2,610, and 41.6% of steps sounding an inner voice outside the
written chord against 23.0%. The clearest single case is ATTYA bar 62, where a held C4
over `Bb-7` was voiced `x-0-2-0-1-x` — A2, E3, G3, C4, an Am7 sharing no pitch class at
all with Bbm7. It is now `x-4-6-5-x-x`, flagged `harmonized_as='Bbm9'`.
`tests/test_wjazzd.py::test_head_path_agrees_with_the_library_on_a_non_chord_tone` is
the regression test; without it this shipped unnoticed.

### Non-chord tones and the dim7 retry

`extension` remains the default. Heads are **not** more chord-tone-rich than
solos — 58.7% at best corpus-wide, and 48.6–64.5% on real standard melodies — so
unresolved tensions are routine, not exceptional.

`--fallback diminished` retries them as Barry Harris dim7 substitutions. It works
mechanically, but it **replaces the written chord**, and on a 12-bar blues six of
the substitutions tend to land on the tonic. It is therefore **off by default**,
and the number of steps it *would* rescue is always reported, so the user can see
what they are missing without opting in.

### Conventions specific to `wjazzd.py`

- **Never guess a chord.** An untranslatable suffix returns `None` and is counted
  in `Solo.unmapped_suffixes`. The same applies to the engine: a quality the
  library cannot voice is left out of `WEIMAR_QUALITY_ALIASES` rather than folded
  into a near neighbour (`79#13` is a real 7♯13; the library voices 7♭13, so it
  is reported instead).
- **Bars are signed** in every signature, comparison and range parser.
- **Ranges are half-open** and may be negative. `parse_bar_range` uses a regex
  rather than splitting on a hyphen, which cannot tell a separator from a minus
  sign when both bounds are negative (`-8--1`).
- **Imports are lazy where they keep `arranger` clean** — `corpus_cli` imports
  `argparse` and `arranger.cli` inside the function, and `main()` imports
  `wjazzd` inside the branch. `headxml.head_cli` does the same, importing
  `argparse` *and* the shared CLI module, so `load_musicxml` costs nothing.
  `arranger.cli` in turn imports the renderers *inside* `render_and_write`, which
  is what keeps `tabstaff` — and therefore the package `__init__` — out of
  `import headxml`.
- **Both commands take the same sixteen flags**, built by one
  `add_common_arguments` in `arranger/cli.py`. Their `--help` prose differs on
  eleven of them, which is why that module carries a `CommonHelp` table per
  command; `tests/test_cli.py` asserts both that the semantics agree and that the
  wording still differs where it is meant to.
- **Tests are guarded** by `skipUnless(DEFAULT_DB.is_file())` so the suite passes
  on a fresh clone with no 42 MB download. Tests needing no database (the
  notation table, the record types, the selector and range parsers) always run.


## Known limitations

- **Corpus (`wjazzd.py`):**
  - The head selector is a heuristic. It finds the right 8-bar head on ATTYA
    melids 266 and 342, but returns a 6-bar fragment on 328 and falls back to the
    whole A-block on 451. 434 of 456 transcriptions yield a head (median 8 bars).
    Pass an explicit `--bars` when you know which bars you want.
  - `wjazzd.db` is not committed. Every database-backed test is skipped when the
    file is absent, so a fresh clone runs a reduced suite.
  - Heads are **not** harmonically simpler than solos (58.7% chord-tone rate at
    best; 48.6–64.5% on real standard melodies), so roughly half the steps need a
    non-chord-tone strategy and `--fallback diminished` is a live option — which
    replaces the written chord, so it stays opt-in.
  - `--lift auto` may transpose a head an octave, including Blue Train's. It
    reports the decision on every run. Transposing the whole head at once cannot
    distort an interval, but it does move the music.
  - A slash bass is honoured as a *preference* (rule C), not a hard constraint; a
    bass the voicings cannot supply falls back to the unslashed behaviour.
  - The corpus path assumes 4/4-style beat grids derived from `tatum`/`division`.
    Triplet divisions are handled, but no non-4/4 *time signature* has been tested.
