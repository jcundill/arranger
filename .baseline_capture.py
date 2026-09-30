"""Capture `arrange_slots`' output, so Phase 4 can prove it did not change.

Run before and after the rewrite; the two files must be byte-identical. This is
the safety net for delegating `arrange_slots` to `arrange_progression`: once it
delegates, "the two entry points agree" is true by construction and tests nothing,
so what has to be pinned is that the *output* is the same as it was while the
second loop still existed.

    python /tmp/capture_baseline.py /tmp/before.json
    python /tmp/capture_baseline.py /tmp/after.json
    diff /tmp/before.json /tmp/after.json

Not a test - a measurement. `tests/test_step_loop_equivalence.py` is the test.
"""

import json
import sys
import warnings

warnings.filterwarnings("ignore")

import wjazzd
from arranger import Diagnostics
from wjazzd import arrange_slots, build_skeleton, load_solo, select_head

FIELDS = (
    "chord", "melody", "grip", "partial", "repeated", "role", "metric_weight",
    "melody_only", "bass_role", "bass_only", "bass", "bar", "beat", "duration",
)


def fingerprint(steps):
    """Everything a caller can read off a step, plus its tab."""
    return [
        [getattr(s, f) for f in FIELDS] + [s.tab_line()]
        for s in steps
    ]


TRIPLES = [
    ("C5", "maj7", "Cmaj7"), ("B4", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7"),
    ("A4", "7", "G7"), ("F4", "m7", "Dm7"), ("C4", "m7b5", "Dm7b5"),
    ("G#4", "m7b5", "Dm7b5"), ("Eb5", "m7", "Cm7"), ("B4", "NC", "NC"),
]


def timings_for(count, beats_per_bar=4):
    return [(i // beats_per_bar, float(i % beats_per_bar) + 1.0, None) for i in range(count)]


def main(destination):
    out = {"hand": {}, "corpus": {}}

    for texture in ("uniform", "targets", "walking_bass"):
        for grips in (None, ("duo",), ("shell",), ("drop2",)):
            for timings in (timings_for(len(TRIPLES)), []):
                diagnostics = Diagnostics()
                steps, _rescued, _notes = arrange_slots(
                    TRIPLES,
                    timings=timings,
                    texture=texture,
                    grips=grips or wjazzd.GRIP_PREFERENCE,
                    diagnostics=diagnostics,
                )
                key = f"{texture}|{grips}|{'timed' if timings else 'untimed'}"
                out["hand"][key] = [fingerprint(steps), diagnostics.warnings]

    # The diminished retry rewrites a step's chord *inside* the loop, after the role
    # has been computed from the written chord. Delegating moves it to a pre-pass, so
    # this is the configuration where that reordering could show - under walking_bass,
    # whose role rule reads the harmony. Measured rather than reasoned about.
    for texture in ("uniform", "targets", "walking_bass"):
        for timings in (timings_for(len(TRIPLES)), []):
            diagnostics = Diagnostics()
            steps, rescued, notes = arrange_slots(
                TRIPLES,
                timings=timings,
                texture=texture,
                fallback="diminished",
                grips=wjazzd.GRIP_PREFERENCE,
                diagnostics=diagnostics,
            )
            key = f"fallback|{texture}|{'timed' if timings else 'untimed'}"
            out["hand"][key] = [
                fingerprint(steps),
                diagnostics.warnings,
                rescued,
                notes,
            ]

    for melid in (218, 266, 342, 328, 451):
        try:
            solo = load_solo(melid)
            head = select_head(melid)
            if head is None:
                out["corpus"][f"{melid}|no-head"] = None
                continue
            # `section` is the bar range; build_skeleton does its own head finding
            # when given None, so the head is selected to name the case, not to pass.
            section = (head.start, head.end) if head is not None else None
            skeleton = build_skeleton(
                solo, strategy="eighths", section=section, pick="first",
                lift="auto", non_chord_tone="extension",
            )
            for texture in ("uniform", "targets"):
                diagnostics = Diagnostics()
                steps, _rescued, _notes = arrange_slots(
                    list(skeleton.triples), timings=skeleton.timings,
                    texture=texture, diagnostics=diagnostics,
                )
                out["corpus"][f"{melid}|{texture}"] = [
                    fingerprint(steps), diagnostics.warnings
                ]
        except Exception as error:  # noqa: BLE001 - recorded, not raised
            out["corpus"][f"{melid}|ERROR"] = f"{type(error).__name__}: {error}"

    with open(destination, "w") as handle:
        json.dump(out, handle, indent=0, sort_keys=True)
    print(f"hand={len(out['hand'])} corpus={len(out['corpus'])} -> {destination}")


if __name__ == "__main__":
    main(sys.argv[1])
