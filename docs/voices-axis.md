# `voices=` — a third axis: which voices the guitar plays

**Status: implemented and committed, awaiting QA.** The code is complete and the gate is
green; nobody has yet read a rendered part and asked whether it is *good*. That is the job
this document exists to hand over. Stage 1's QA landed three fixes off the §4 checklist,
and Stage 2 moved the melody-only claim onto this axis — `soprano` alone is the tune and
nothing else, and the `melody`/`melody_bass` textures are gone — see
[docs/one-fact.md](one-fact.md).

Deliberately **not** in `docs/history/` — that directory is for completed plans and is not
extended. This one is open, and the "Known limitations" section is the part most likely to
change after someone plays it.

Measured state at the time of writing: **938 tests OK (skipped=2)**, ruff 0 errors, pyright
**0 errors 0 warnings**. Baseline before this work was **883** — all 883 pass unchanged.
43 of the 938 are the original axis tests in `tests/test_comping.py`, and 12 more are the
bass-voice class added by §8a.

---

## 1. What was asked for, and what it is now

> separate out the bass voice … the soprano voice holds the melody note … the bass player
> will take on the bass voice, the sax player will take on the soprano voice — I'd like to
> render just the alto and tenor voices for the guitar part

That is **one flag**:

```bash
python -m arranger head tests/data/heres_that_rainy_day.musicxml \
    --bars 1-3 --voices alto,tenor --bass none --texture targets
```

```text
Gmaj9    D4   (shell - 3rd & 7th, partial) x-x-x-x-7-7
Gmaj9    D4   (shell - 3rd & 7th, partial) x-x-x-x-7-7
Gmaj9/F# D4   (shell - 3rd & 7th, partial) x-x-x-x-7-7
Bb7/F    D4   (shell - 3rd & 7th, partial) x-x-x-x-3-4
Bb7/F    F4   (shell - 3rd & 7th, partial) x-x-x-x-3-4
E7b5     Bb4  (shell - 3rd & 7th, partial) x-x-x-x-3-4
E7b5     D5   (shell - 3rd & 7th, partial) x-x-x-x-3-4
```

Two notes per step: one per voice named.

## 2. The three axes

| axis | question | values |
|---|---|---|
| `texture=` | where notes fall, how thick the left hand is | `uniform`, `targets`, `walking_bass` |
| `bass=` | the bass voice | `none`, `anchors`, `walk` *(pre-existing)* |
| `voices=` | which voices the guitar plays | any subset of `soprano`, `alto`, `tenor`, `bass`; `soprano` alone is the tune and nothing else *(new)* |

Orthogonal, deliberately. `bass="none"` was already there and already covers "I am next to a
bass player, so none of the 1s and 5s and none of the walking motion". `voices` is the
soprano half. Leave either alone and that voice stays the guitarist's job.

## 3. `--voices` enumerates the SATB quartet

A comma-separated list, **not** one choice out of a fixed set — the question a player asks
is never "how many notes" but *which voices am I playing*.

| `--voices` | notes | part |
|---|---|---|
| `auto` *(default)* | 4 | all four voices: the historical chord-melody |
| `soprano,alto,tenor,bass` | 4 | the same, said explicitly |
| `soprano` | 1 | the melody and nothing else — the old `--texture melody` *(Stage 2)* |
| `soprano,bass` | 2 | the tune with a walking thumb — the old `--texture melody_bass` *(Stage 2)* |
| `none` | 2 | shorthand for `alto,tenor` |
| `alto,tenor` | 2 | the two middle voices |
| `alto` | 1 | one voice |

- Order does not matter: `tenor,alto` and `alto,tenor` are **one** request, verified.
- Case and whitespace are forgiven.
- An unknown name is an **error**, not a silently dropped voice.
- `none` does **not** mean silence. Silence is not an arrangement; `none` is the ensemble
  answer — horn on the tune, bassist on the root, guitar in between.

```
$ python -m arranger head … --voices banjo
arranger head: error: Unknown voice 'banjo'; expected any of
('soprano', 'alto', 'tenor', 'bass'), 'none', or 'auto'
```

## 4. QA checklist

Each row is a command worth running. The first three are the claim; the rest are the edges.

| # | check | expected |
|---|---|---|
| 1 | `--voices alto,tenor` | 2 notes per step |
| 2 | `--voices alto` | 1 note per step |
| 2a | `--voices bass` | 1 note per step, **strings 4-6, root or 5th** — §8a |
| 3 | `--voices alto,tenor,bass` | 3 notes per step |
| 4 | no `--voices` | byte-identical to before this change |
| 5 | `--voices tenor,alto` | identical output to `alto,tenor` |
| 6 | `--voices banjo` | usage error, nothing printed |
| 7 | `--voices auto,alto` | usage error |
| 8 | `--voices alto,tenor` under any texture | comps — the old `--texture melody` refusal dissolved when the melody-only claim moved onto the selection |
| 9 | `--voices alto,tenor --tab staff --melody` | staff draws; no soprano string marked |
| 10 | `--voices alto,tenor --bass walk` | thumb walks *under* a 2-note shape, or refuses |
| 11 | a head containing an `NC` bar | warns once, skips the bar |
| 12 | `--voices alto,tenor --html out.html` | page renders, no melody on the tab |
| 13 | `--voices alto,tenor --musicxml x.musicxml --gp5 y.gp5` | both write without error |

**Row 4 is the important one.** If the default output moved, the change is not inert and
should not ship. `make demo` is the quickest read on it.

## 5. What the measurements actually showed

Corpus, three heads, `--voices alto,tenor` — **2,069 steps**, every figure counted:

```
notes per step          2          2069 of 2069
melody_voiced           False      2069 of 2069
supported string set    yes        2069 of 2069
over GRIP_MAX_SPAN      0
wrong notes             0
guide tone missing      0
unreadable chord        610        see below
```

**The 610 are not failures.** They are Weimar qualities the library cannot read at all
(`j7`, `+7`, `o7` have no entry in `CHORD_TONES_FROM_ROOT`), and the library's standing rule
is *not to judge a chord it could not read*. An earlier probe of mine reported them as 610
"wrong notes" because it compared a pitch set against an **empty** tone set; the engine does
not do that.

## 6. A claim that was wrong, and what the measurement did

The first version of the test suite asserted:

> no comping step *contains* the melody's pitch

It reads well and it is **false**: **409 of 2,069 steps do contain it.** Not a defect — a
chord tone in the shell often shares the melody's pitch class, which is unremarkable.

The generator cannot be reading the melody, and that is asserted the only conclusive way:
asking for `D5` and for `G3` under the same chord returns the **identical candidate set**,
eight melody notes and three chords deep. A generator that read the melody could not do
that.

So what the axis guarantees is:

- the shape was **chosen from the chord alone**; and
- `step.melody_voiced` is `False` — which is what the renderers read.

Both `docs/engine.md` and the test docstrings record the false claim and what corrected it.
If you would rather the weaker-but-true phrasing were the *only* wording anywhere, that is
worth a pass.

## 7. Two things deliberately not done

**Rhythmic patterns.** `voices=` names *which voices*, not how they are struck. Freddie
Green, Charleston and the rest are a **row in `MELODY_POLICIES`** and nothing else — the
table and the seam exist, the rows do not. This was the stated next step and is untouched.

**`step.melody` still holds the tune.** On a comping step that is the *written* note the
horn is playing, not something the guitar sounds. It is deliberate — it is what the band
lines the part up against — but if you would rather it were `None` or a new field, that is
a small change and a real decision.

## 8. Known limitations, written down rather than discovered

1. **A one-voice selection states the chord weakly.** Two notes can sound both guide tones;
   one cannot, so `--voices alto` keeps only the **first** guide tone (the 3rd, or the 4th
   on a sus chord). It is a `duo`-grade statement, not a shell. The alternative was to
   refuse, which measured worse: it warned on every step and handed the horn's line back
   to the guitarist. **`--voices bass` is the exception** and no longer reads this way — see
   §8a.
2. **The arity picks the grip family.** Two voices use the `duo` string sets, three use the
   `shell` sets. Truncating a shell set to two strings looks free and is not — it yields
   pairs the library has never measured (`(0,2)` skips the A string, `(5,3)` skips the B).
   Those pairs are **not** offered. A lone `--voices bass` is a third case and takes
   `BASS_VOICE_STRING_SETS` — §8a.
3. **A repeated melody holds the whole shape** rather than re-striking a soprano. Measured:
   **152 of 2,243** corpus steps carry `repeated`, and keeping the old rule rendered every
   one as a single moving note — a melody line on the guitar part, on exactly the beats
   where the tune had been given away. Stated in two places on purpose (`render` and
   `tabstaff`) so the renderers cannot disagree; a test asserts they agree.
4. **An `NC` bar is skipped, with a warning.** No chord means no guide tones, so the guitar
   is silent there while the horn is not.
5. **`--voices` is not validated by `argparse`.** It is a free string, so a bad value is
   reported as a usage error by the parser rather than by `choices=`. That was the price of
   accepting a comma list, and it means `--help` no longer lists the vocabulary.
6. **A `--voices` selection with the soprano *and an inner voice* in it does not change
   the shape.** The melody-bearing route is untouched by which of the other three voices
   you also name, so `--voices soprano,alto` currently arranges exactly like
   `--voices auto`. **Soprano alone is the exception, and it is Stage 2:** it is the
   melody and nothing else, the old `--texture melody` — see
   [docs/one-fact.md](one-fact.md). Stated because the distinction is a plausible
   reading of the flag that is only half implemented.

## 8a. `--voices bass` was not a bass voice, and now is

Found during QA, by asking the question §4 row 2 does not: *if I name one voice, which
one?* Before this fix `--voices bass`, `--voices alto` and `--voices tenor` produced
**byte-identical** arrangements.

Three defects, all measured on `tests/data/but_not_for_me.mxl` before the fix:

| | before | after |
|---|---|---|
| strings used | `{1: 41, 2: 27, 3: 12}` | `{4: 53, 5: 5, 6: 22}` |
| sounding MIDI | 59–74 | 46–55 |
| note sounded | the 3rd (`Bb7` → `D`) | the root, else the 5th — **80 of 80** |

1. **The voice identity was discarded.** `steps` passed `notes=len(voices)`, and arity
   cannot tell a bass from a tenor: all three ask for one note.
2. **The low register was unreachable.** `_comping_string_sets(1)` offered only the *top*
   string of each `duo` pair — indices 5, 4, 3. Re-ranking cannot fix an unavailable
   position, so the string sets themselves had to change.
3. **The note was the 3rd.** A low 3rd is still not a bass note: it sounds like the wrong
   chord, which is what `BASS_DEGREES_6432` says in its own comment. **Register and
   degree had to move together** — fixing only the register would have produced a low 3rd
   and looked like a fix on a tab.

A lone bass now takes `BASS_VOICE_STRING_SETS` (low E, A, D) and its note from
`BASS_DEGREES_6432` — **read from that table, not written out again**. The inner voices
are untouched: `alto` and `tenor` keep the guide tone on the top of a duo pair, because
they are guide tones under somebody else's melody and that is where a player puts one.

**Two limits, stated rather than discovered:**

- **`bass` is only special when it is named *alone*.** `tenor,bass` and
  `alto,tenor,bass` are unchanged: their lowest note belongs to the duo's or shell's own
  string set, and re-deciding that would be re-deciding a shape that is already correct.
- **A lone bass note states nothing about the chord's *quality*.** A root names the chord;
  a single 3rd or 7th is what tells the ear major from minor. `--voices bass` on its own
  is a bass line, not a comping part — it reads `BASS_DEGREES_6432`, not `SHELL_DEGREES`,
  deliberately. If you want the quality stated, name an inner voice too.

**A fourth defect, pre-existing and not about `voices=` at all:**
`supported_string_sets()` listed **no singletons**, so every one-note shape the library
could produce — `alto`, `tenor`, `bass`, a melody-only part, an `NC` bar — violated the
invariant *"the sounding strings are exactly one `supported_string_sets()` entry"*, and
nothing caught it because the per-shape assertions never generated one.
`SINGLE_NOTE_STRING_SETS` fixes it rather than excusing it: one note on one string has no
span to exceed and no second voice to clash with. `tests/test_texture.py`'s solo-note test
was **inverted, not deleted** — it had asserted `assertNotIn`, pinning the gap.

## 9. Where the code is

| file | what changed |
|---|---|
| `arranger/textures.py` | `VOICE_NAMES`, `VOICES_NONE`/`VOICES_ALL`, `parse_voices`, `resolve_voices`, `melody_allowed`, the soprano predicate |
| `arranger/grips.py` | `get_comping_voicings` (+ `notes` arity, `bass_voice`), `_shell_voicing`, `_comping_string_sets`, `_frets_in_span`, `SINGLE_NOTE_STRING_SETS`, `BASS_VOICE_STRING_SETS`, `supported_string_sets()` |
| `arranger/movement.py` | `_resolve_melody`, the comping route, `notes=len(voices)` + `bass_voice=voices == (MELODY_BASS,)` |
| `arranger/decisions.py` | `melody_alone_case` guard — a texture fill must not sing |
| `arranger/tuning.py` | `ArrangementStep.melody_voiced` |
| `arranger/options.py` | `ArrangeOptions.melody` |
| `arranger/render.py`, `tabstaff.py` | the repeated-step hold, in both, deliberately |
| `arranger/cli.py` | `--voices` |
| `headxml.py` | threaded through the `head` entry point |
| `tests/test_comping.py` | **new**, 43 tests in 7 classes |
| `tests/test_cli.py` | shared-flag count 17 → 18, `voices` named as identically-worded |

**One trap worth knowing about**, because it cost a real bug: in the since-removed
`wjazzd.arrange_slots`, a loop variable named `melody` shadowed the new `melody` **policy**
parameter, so the diminished-retry path passed a note name where a policy belonged —
`Unknown melody policy 'D4'`, raised only when a retry had something to rescue, so it looked
like a corpus bug. Renamed to `note`. `AGENTS.md` still records the trap, in its "Five axes"
section, where it applies to any new axis rather than to that one entry point.

## 10. For the record: what did **not** change

- `voicing_cost`'s 8-element tuple, and its order. `melody_pc` was already `Optional`.
  The register fix is in the **generator's string sets and degree rule**, deliberately: a
  register preference belongs in the cost function only if it is a general preference, and
  "the bass voice goes low" is a fact about one voice rather than about every shape.
- The drop-2 tables, `SHELL_DEGREES`, `GRIP_STRING_SETS`, `DUO_DEGREES`.
- `BASS_DEGREES_6432` — **read** by the new branch, not rewritten. One table, one rule.
- Every other grip family, texture, and the `bass=` axis.
- `make demo` output, and all 883 pre-existing tests.
- `supported_string_sets()` gained the six singletons and **lost nothing** — §8a. Every
  set it listed before is still listed.

