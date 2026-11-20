"""Starting a tutorial with edits not saved yet, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_unsaved_start.py

The probe makes a tutorial in a folder of its own and edits its step's
title without saving. It checks:
- Start Tutorial, invoked as the menu does, asks first and starts nothing.
  It asks with a small menu: Save and Play, or Play Saved Version
  (tutorial_unsaved_1_asked.png);
- Esc closes that menu;
- Save and Play saves the edit and plays it.

Prints PASS or FAIL, saves screenshots in tests/output/screens, and quits."""

import importlib
import os
import shutil
import sys
import tempfile

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402


def steps():
    t, e = rigs.module("tutorials"), rigs.module("tutorial_edit")
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                     # click the splash away
    folder = tempfile.mkdtemp(prefix="kneady_probe_unsaved_")
    e.RECYCLE = False
    t.CONFIG = os.path.join(folder, "config.json")
    t.set_author_folder(folder)
    wm = bpy.context.window_manager
    ov = {"window": win, "area": area, "region": view}
    try:
        with bpy.context.temp_override(**ov):
            bpy.ops.kneady.tutorial_new(title="Unsaved")
        pg = wm.kneady_tutorial
        tid = pg.id
        pg.steps[0].title = "Edited, not saved"
        yield from w.move(win, 600, 500, 2)
        with bpy.context.temp_override(**ov):
            bpy.ops.kneady.tutorial_start("INVOKE_DEFAULT", tutorial=tid)
        yield 0.6
        w.check("asked_and_nothing_started", not t.active() and t.unsaved(tid))
        w.shot("tutorial_unsaved_1_asked")
        win.event_simulate("ESC", "PRESS", x=600, y=500)
        yield 0.1
        win.event_simulate("ESC", "RELEASE", x=600, y=500)
        yield 0.4
        w.check("esc_starts_nothing", not t.active())
        w.shot("tutorial_unsaved_2_closed")
        with bpy.context.temp_override(**ov):
            bpy.ops.kneady.tutorial_start("INVOKE_DEFAULT", tutorial=tid, unsaved="SAVE")
        yield 0.6
        w.check("save_and_play", t.active() and t.step()["title"] == "Edited, not saved" and not t.unsaved(tid),
                "active %s" % t.active())
        w.shot("tutorial_unsaved_3_playing")
    finally:
        t.end()
        shutil.rmtree(folder, ignore_errors=True)


w.run(steps, "probe_unsaved_start")
