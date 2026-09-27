# Implementation Plan
## Overview
Add MusicXML output to the tab rendering options: a rhythmically faithful two-staff
guitar score (TAB staff plus an optional notation staff) with chord symbols and
per-note string/fret technicals, built with `music21` and wired into the corpus CLI
alongside `--html`.
Scope is one new renderer module, one **optional** dependency declared as an extra
(never a hard runtime dep), a CLI flag, tests and docs. It follows the existing
renderer contract exactly: a pure `format_*` that returns a string, a single
`write_*` that touches the filesystem, optional timing with a uniform-grid
fallback, and the same `repeated`/hold semantics as the ASCII and HTML renderers.
Two decisions are baked in and approved:
- **The notation staff is on by default but toggleable** (`show_notation`), so a
  caller who wants TAB alone gets a one-staff file.
- **The TAB staff XML is post-processed with `xml.etree.ElementTree`** after
  music21 serialises the score, because music21 does not export fret/string data
  for the notes *inside* a chord (cuthbertLab/music21#1534). Every note in a guitar
  tab staff has a fret, so without this pass notation software recomputes the
  position from pitch alone and puts the shape in the wrong place.
## Types
No engine types change. `ArrangementStep` and `Voicing` are read-only inputs, so
their dataclasses, `__getitem__` shims and defaults are untouched — which also keeps
`arranger.__all__` and the module-boundary tests stable apart from the two new names.
`pyproject.toml`:
- `[project.optional-dependencies]` gains `xml = ["music21>=9.1"]`.
- `dependencies` stays `["musthe>=1.0.0"]` — the standing "musthe is the only
  runtime dependency" rule is relaxed only for an opt-in extra, never for the base
  install.
- `[tool.setuptools] py-modules` gains `"tabxml"`.
## Files
- **New `tabxml.py`** — the MusicXML renderer. Imports `arranger` and (at call time)
  `tabstaff`; `music21` is imported *inside* the functions through `_music21()`,
  which turns a missing install into an actionable message.
- **Modify `tabstaff.py`** — add a lazy module-level `__getattr__` re-exporting
  `format_musicxml` / `write_musicxml`, and extend `__all__`. `tabxml` is *not*
  imported at the top, so `import tabstaff` stays cheap and cycle-free.
- **Modify `arranger.py`** — `_TABSTAFF_EXPORTS` becomes a `name -> module` mapping
  (it is a tuple today) so `arranger.format_musicxml` resolves through the same lazy
  `__getattr__`; add the two names to the `TYPE_CHECKING` import and to `__all__`
  (mandatory — `test_dunder_all_matches_the_public_surface` checks both directions).
- **Modify `wjazzd.py`** — a `--musicxml PATH` flag, rendered after the HTML block,
  reusing the same `provenance` notes and title/subtitle, reporting `wrote <path>`.
- **Modify `pyproject.toml`** — the extra and the new module.
- **Modify `README.md`, `AGENTS.md`** — a row in the renderer table, a CLI example,
  and the dependency note.
- **No files are deleted or moved.**
<!-- APPEND-2 -->

## Functions
New, in `tabxml.py`:
- `_music21() -> Any` — lazy import; converts `ImportError` into a message naming
  `pip install 'jazz-arranger[xml]'`.
- `_pitch(midi) -> Tuple[str, int]` — flat-preferring spelling plus octave, matching
  `arranger._note_name`'s convention.
- `_slot_onsets(steps, beats_per_bar, rhythm)` — **reuses** `tabstaff._staff_columns`,
  so the XML grid, the ASCII staff and the HTML page agree on where every chord
  falls by construction rather than by coincidence.
- `_durations(steps, beats_per_bar)` — quarterLength per slot from `step.duration`
  (whole notes) or the gap to the next onset; the last slot closes its bar. A slot
  whose shape is a *hold* continues as tied notes rather than a re-strike.
- `_xml_notes(step, quarter_length)` — a `Chord` (or a single `Note` for a
  repeated melody and for a melody-only step) with `FretIndication` and
  `StringIndication` on every note, string number `6 - string_index`.
- `_add_chord_symbols(part, steps)` — a `ChordSymbol` on each chord change only.
- `format_musicxml(steps, title=..., subtitle=..., composer=..., beats_per_bar=4,
  rhythm=True, collapse=True, show_notation=True, show_tab=True) -> str` — builds a
  `stream.Score` with a six-line `TabClef` part and a treble part, serialises through
  `musicxml.m21ToXml.GeneralObjectExporter`, then post-processes the XML to inject
  `<staff-details><staff-lines>6</staff-lines>` and the per-note `<technical>` fret
  and string elements.
- `write_musicxml(steps, path, **kwargs) -> str` — the only function in the module
  that touches the filesystem, mirroring `write_tab_html`.
Modified:
- `tabstaff.__getattr__` (new) — lazy re-export, same rationale as `arranger`'s.
- `arranger._TABSTAFF_EXPORTS` — becomes a dict so one `__getattr__` serves two
  renderer modules.
Removed: none.
## Classes
No classes are added or modified. music21's `stream.Score`, `note.Note`,
`chord.Chord`, `clef.TabClef`, `clef.TrebleClef`, `instrument.Guitar`,
`layout.StaffLayoutDetails` and `harmony.ChordSymbol` are constructed inside the
renderer and never leak into the library's public surface.
## Dependencies
- **New: `music21>=9.1`, optional extra only.** The library must import and render
  ASCII/HTML with it absent, so the import is lazy and the tests are `skipUnless`
  guarded exactly as the database-backed tests already are.
- **Dev:** `.venv/bin/pip install music21` for local verification; deliberately
  absent from the base `dependencies` list so it never reaches a plain install.
- `musthe` unchanged.
## Testing
- **New `tests/test_musicxml.py`**, guarded by
  `unittest.skipUnless(HAS_MUSIC21, "music21 not installed")`:
  - the output is well-formed XML and `<score-partwise>` parses;
  - the TAB staff carries `<staff-lines>6</staff-lines>` and a TAB clef;
  - the measure count and barline positions match `format_tab_staff`;
  - every sounding fret/string appears as `<fret>`/`<string>` on the right note;
  - chord symbols appear on changes only, not on every eighth;
  - a hand-written untimed progression still renders via the uniform-grid fallback;
  - a `repeated` step becomes one tied soprano note with no inner voices;
  - `write_musicxml` returns the path it wrote and the file re-parses;
  - empty steps return `""` (no partial document);
  - a missing music21 produces the actionable message rather than a raw traceback.
- **Modified `tests/test_tab_rendering.py::TestTabstaffModuleBoundary`** — the two
  new names join its lazy-export and `__all__` assertions.
- Validation: `.venv/bin/python -m unittest discover -s tests -v` must report `OK`;
  `.venv/bin/pyright arranger.py tabstaff.py tabxml.py wjazzd.py tests` must report
  `0 errors`; and a real head is round-tripped
  (`arranger.py corpus --melid 218 --musicxml /tmp/out.musicxml`, then
  `music21.converter.parse` on the result).
## Implementation Order
1. Install `music21` locally; add the `xml` extra and `tabxml` to `py-modules`.
2. Create `tabxml.py` with `_music21()`, `_pitch`, `_slot_onsets` and
   `_durations`; get a two-chord fixture producing a parseable score.
3. Add the TAB staff, the chord symbols and the ElementTree post-processing pass;
   verify against a real ATTYA head.
4. Add the optional notation staff and `write_musicxml`.
5. Wire the lazy re-exports: `tabstaff.__getattr__`, `arranger._TABSTAFF_EXPORTS`,
   the `TYPE_CHECKING` import and both `__all__` lists.
6. Add `--musicxml PATH` to `wjazzd.corpus_cli`, reusing the provenance notes.
7. Write `tests/test_musicxml.py`; update the boundary tests.
8. Run the full suite and pyright; round-trip an exported head.
9. Update `README.md` and `AGENTS.md`; bump `__version__` to `0.5.0`.
