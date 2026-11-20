"""A finished tutorial step moves on to the next one by itself. Run it in a
window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_advance.py

Greg asked for this - "I'd like to use that to move to the next step in a
tutorial" - then found "The delay felt about twice too long", and added
"there Should also be acknowledgement that a tutorial is completed. Have it
say Completed!".

The probe writes a two-step tutorial into a folder of its own and checks:
- the first step, once done, is ticked off;
- the second step then comes on by itself, ADVANCE_AFTER later (measured);
- the second and last step, once done, says Completed!, clear of the Back
  and Reset buttons.

Prints PASS or FAIL, saves screenshots in tests/output/screens, and quits."""

import importlib
import json
import os
import sys
import tempfile
import time

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402


def steps():
    t, o = rigs.module("tutorials"), rigs.module("overlay")
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                       # click the splash away
    folder = tempfile.mkdtemp(prefix="kneady_probe_advance_")
    t.CONFIG = os.path.join(folder, "config.json")
    t.set_author_folder(folder)
    os.makedirs(os.path.join(folder, "moves_on"))
    with open(os.path.join(folder, "moves_on", "tutorial.json"), "w", encoding="utf-8") as f:
        json.dump({"format": t.FORMAT, "title": "Moves On", "steps": [
            {"title": "Labels always", "text": ["Set Labels to Always."],
             "done_when": [{"path": "scene.kneady_labels", "is": "ALWAYS"}]},
            {"title": "Then", "text": ["Set Labels to Off."],
             "start": {"set": [{"path": "scene.kneady_labels", "value": "ALWAYS"}]},
             "done_when": [{"path": "scene.kneady_labels", "is": "OFF"}]}]}, f)
    bpy.context.scene.kneady_labels = "HOVER"
    with bpy.context.temp_override(window=win, area=area, region=view):
        t.begin(bpy.context, "moves_on")
    yield 0.5
    bpy.context.scene.kneady_labels = "ALWAYS"
    ticked = moved = None
    for _ in range(60):
        yield 0.02
        now = time.perf_counter()
        if ticked is None and t.done() and t.S["step"] == 0:
            ticked = now
            w.shot("advance_1_done")
        if t.S["step"] == 1:
            moved = now
            break
    w.check("ticked_off_first", ticked is not None, "never seen done at step 1")
    w.check("moved_on_by_itself", moved is not None, "step %d" % t.S["step"])
    if ticked is not None and moved is not None:
        # From seeing the tick to the next step: ADVANCE_AFTER, give or take the
        # time between two looks
        w.check("after_half_a_second", 0.3 <= moved - ticked <= t.ADVANCE_AFTER + 0.15,
                "%.2f s" % (moved - ticked))
    w.shot("advance_2_next")
    bpy.context.scene.kneady_labels = "OFF"
    yield 0.8
    w.check("last_step_says_completed", t.done() and t.S["step"] == 1 and o.done_word() == "Completed!",
            "step %d done %s word %s" % (t.S["step"], t.done(), o.done_word()))
    w.shot("advance_3_completed")
    with bpy.context.temp_override(window=win, area=area, region=view):
        t.end(bpy.context)


w.run(steps, "probe_advance")
