"""Undo through region edits, which needs a window (bpy.ops.ed.undo does not
run in the background):

    blender --factory-startup --python tests/probe_undo.py

Runs test_data_life.test_undo_through_region_edits in the window's 3D view,
prints PASS or FAIL, and quits.
"""

import importlib
import os
import sys
import traceback

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import test_data_life  # noqa: E402  (after Kneady is loaded, as run.py)


def start():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.app.timers.register(run, first_interval=0.5)


def run():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    try:
        with bpy.context.temp_override(window=win, area=area, region=region):
            test_data_life.test_undo_through_region_edits()
        print("PASS  undo_through_region_edits")
    except AssertionError as exc:
        print("FAIL  undo_through_region_edits  %s" % exc)
    except Exception:
        print("CRASH undo_through_region_edits\n%s" % traceback.format_exc())
    sys.stdout.flush()
    os._exit(0)


bpy.app.timers.register(start, first_interval=1.0)
