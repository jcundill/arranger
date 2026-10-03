# Reharmonisation proposals: tritone substitution and chromatic approach chords

Two mechanisms from [history/Arranging_Guide.md](history/Arranging_Guide.md) §1 that
the engine does not yet have:

- **Tritone Substitutions** — "Replace a dominant chord (e.g. G7) with a dominant
  chord a tritone away (Db7) when the melody note aligns with the sub's extensions."
- **Chromatic Approach Chords** — "Move your primary chord shape up or down a
  half-step into the target chord."

This records what was measured, what was built, and what was deliberately **not**
built — so the decision can be reviewed rather than re-derived. Measurements are over
the first 40 heads of `wjazzd.db`, `eighths` skeleton (2,995 steps, 1,405 non-chord
tones).

**Status:** tritone substitution **shipped**, as a table row
(`arranger/chords.py`, `NON_CHORD_TONE_EXTENSIONS["7"][1] = "7b9"`). Chromatic
approach **not built** — see [Chromatic approach chords](#chromatic-approach-chords).

---

## The finding that reframes both

Before either was designed, the corpus was measured for how much work was actually
left to do:

| measurement | value |
|---|---|
| steps examined | 2,995 |
| non-chord tones | 1,405 (47%) |
| unresolved by `extension` | 771 |
| **rescued by `diminished`** | **771 (100%)** |

**There is no coverage gap.** `diminished` (Barry Harris 6/dim7) already resolves
every single note that `extension` leaves open — measured over 40 heads, zero
exceptions. So neither mechanism is a bug fix. Both are *stylistic alternatives* to a
strategy that is already complete.

That matters because of an existing decision: `wjazzd.py` keeps the diminished retry
**off by default** because "it replaces the written chord." Any mechanism that
rewrites the harmony inherits that same status. Neither was made a default.

---

## Tritone substitution: shipped as a table row

### Why it is not a strategy

A tritone sub is fully determined by the root — there is no decision to make about
*which* chord to use, only about whether to use it. Measured over all 12 roots, the
melody degrees a sub absorbs that the original cannot are **identical every time**:

```
G7  -> Db7 : exclusive [1, 6]
C7  -> F#7 : exclusive [1, 6]
F7  -> B7  : exclusive [1, 6]
Bb7 -> E7  : exclusive [1, 6]
G9  -> Db9 : exclusive [1, 6, 8]
G13 -> Db13: exclusive [1, 3, 6, 8]
```

Degree 6 (the ♯11, the sub's ♭5) is **already routed** by `extension` → `7#11`. The
only degree with no existing route is **1, the ♭9** — and `7b9` was already a
voiceable quality (`CHORD_TONES_FROM_ROOT`, `DROP2_INTERVAL_SETS`, `SHELL_DEGREES`).
So the whole mechanism reduced to **one table entry**, and no new flag, strategy,
pass, or lookahead.

This also matches the repository's own rule. `AGENTS.md` and the notation tables
follow "never guess a chord" — `WEIMAR_QUALITY_ALIASES` and `MUSICXML_KIND_QUALITIES`
resolve an unknown spelling to `None` and *count it* rather than guessing. A second
spelling of a route the table already expresses is the thing that rule exists to
prevent.

### What shipped

`arranger/chords.py`, one row:

```python
"7": {1: "7b9", 2: "9", 5: "7sus4", 6: "7#11", 8: "7b13", 9: "13"},
```

**Measured effect: unresolved steps 771 → 717. Exactly 54 newly resolved**, which
matches the independent estimate made before implementing (54, by direct simulation of
the sub's tone set). Every one is voiceable by the grips; none was rescued on paper
only.

### The important distinction: this is not literally a tritone substitution

`G7 → G7b9` **keeps the root**. A true tritone sub, `G7 → Db7`, **moves** it. Both
make `Ab` a chord tone — it is the ♭9 of one and the 3rd of the other — but they are
different claims:

| | root | bass | resolves to |
|---|---|---|---|
| `G7 → G7b9` (shipped) | G, unchanged | G | as written |
| `G7 → Db7` (true sub) | G → Db | Db | the subV of the same target |

The shipped route is the narrower claim: it harmonises the note the melody states
without re-basing the chord. **A true tritone sub is therefore still not built**, and
the table row should not be read as having implemented one.

### One trap this exposed, deliberately not fixed

`arranger/steps.py` passes `root_pc=cls._chord_context(chord_type, name)[1]` to
`select_step_voicing`. Per `StepPreparation`'s docstring, `chord_type`/`chord_name`
stay the **written** chord even when `harmonized_as` names a substitute — so that
`root_pc` is the written root. `allowed_tones` (five lines above) correctly follows the
substitute; `root_pc` does not.

This is **correct today** and was verified rather than assumed: the new route does not
move the root, so the written root is the right one. It becomes wrong only for a
root-moving substitution — i.e. precisely a true tritone sub. Left alone, because
fixing it speculatively would change the selection of every existing step. It is
recorded here as a precondition for that work.

---

## Reproducing

```bash
.venv/bin/python - <<'PY'
import wjazzd
from musthe import Note
from arranger import VoiceLeadingEngine as E
from arranger.tuning import NO_CHORD

unresolved = 0
for row in wjazzd.list_solos()[:40]:
---

## Chromatic approach chords: not built

### What it needs that the engine lacks

The guide's formulation is defined relative to the **target** chord — "move your
shape a half-step *into* it". So it needs to see the next harmony.

The step loop has exactly one lookahead today, and it is a **melody** lookahead:
`_next_resolution_melody` (`arranger/steps.py`) scans forward for the next *chord
tone in the melody*, not the next chord. There is no chord-lookahead anywhere in the
engine. That helper is the whole of the new machinery the mechanism requires: one
function, parallel to the existing one, returning the first following step whose
*chord* differs.

### Why it was not built

Measured viability was good — of the 771 unresolved steps, **402** have a melody that
is genuinely a chord tone of a dominant built a semitone from the next chord's root,
and **369** of those are actually voiceable by the grips. So it would work often.

It was still declined, for reasons the measurements support:

1. **It buys no coverage.** `diminished` already reaches 771/771. Chromatic approach
   reaches 369 of the same notes by a different route. It is a second correct answer
   to a question that already has one — not a new capability.
2. **It requires a new lookahead dimension.** The one phrase-level pass in the
   library, the walking bass, is documented at length in
   [history/walking-bass.md](history/walking-bass.md) precisely because a lookahead
   changes what the *pass* can decide. Adding a second is a design step, not a table
   row.
3. **It contradicts a stated principle.** `AGENTS.md` records "no key model, by
   construction," and the arranging guide's chromatic approach is a functional,
   key-directed device. Reaching for it would be the first mechanism to want a key.
4. **It is not a default either way.** Per `wjazzd.py`'s diminished precedent it
   would ship opt-in. So the honest summary is "a stylistic alternative to a strategy
   that is already complete" — a weaker case than "a gap".

### If it is built later

- Add `"chromatic"` to `NON_CHORD_TONE_STRATEGIES`, **default off**, validated by the
  existing `NON_CHORD_TONE_STRATEGIES` check in `arrange_progression`.
- Add the next-*chord* lookahead helper. `prepare_step` already receives `progression`
  and `index`, so it needs no new plumbing.
- Route it through the existing `resolve_non_chord_tone` → `get_all_grip_voicings` →
  `harmonized_as` path. Rendering, annotation and the CLI's shared flag block all work
  unchanged.
- Read `history/walking-bass.md` first: it records what a lookahead costs, and the
  union/lookahead trap that produced the `_Slot` design.
- Tests belong beside the new route in `tests/test_non_chord_tones.py`, which holds
  `TestExtendedExtensionMappings` and its table invariant — the invariant there
  (substitute must contain the degree, and offer an inversion that tops it) applies to
  any new strategy unchanged.

    solo = wjazzd.load_solo(row.melid)
    sel = wjazzd.select_head(row.melid)
    triples = wjazzd.skeleton(solo, "eighths", (sel.section.start, sel.section.end))
    for note, quality, name in triples:
        if quality == NO_CHORD or not name:
            continue
        melody = Note(note)
        if E.is_chord_tone(melody, quality, name):
            continue
        if E.resolve_non_chord_tone(melody, quality, name, "extension") is None:
            unresolved += 1
print(unresolved)   # 717 with the b9 route, 771 without
PY
```

Requires `wjazzd.db` (42 MB, gitignored). CI does **not** run this — see `AGENTS.md`;
the `corpus` job covers it on manual dispatch.
