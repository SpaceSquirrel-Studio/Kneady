"""A tutorial plays in the 3D view it was started from, even in a second
window: a window probe.

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_tutorial_window.py

A second window opened (Window > New Window, as on a second monitor), the
tests' demo tutorial started from its 3D view: the tutorial's view
(tutorials.area) is that one, in that window, and stays so. Before, the
tutorial never kept the view it was started from and looked in the first
window only, so it always played in the main window. Then a tutorial started
from the main window plays there. Prints PASS or FAIL lines and quits."""

import importlib
import os
import sys

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import rigs  # noqa: E402
import window as w  # noqa: E402


def biggest_view(win):
    views = [a for a in win.screen.areas if a.type == "VIEW_3D"]
    return max(views, key=lambda a: a.width * a.height) if views else None


def steps():
    t = rigs.module("tutorials")
    t.FOLDERS.append(os.path.join(HERE, "tutorials"))
    t.ADVANCE_AFTER = 600.0
    bpy.context.preferences.view.show_tooltips = False    # clean screenshots; this session only
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 120, 600)                     # the splash away
    wm = bpy.context.window_manager
    with bpy.context.temp_override(window=win, area=area, region=view):
        bpy.ops.wm.window_new()
    yield 1.0
    w.check("second_window_open", len(wm.windows) == 2, "%d windows" % len(wm.windows))
    if len(wm.windows) < 2:
        return
    second = wm.windows[1]
    there = biggest_view(second)
    if there is None:                                     # its layout has no 3D view: make one
        there = max(second.screen.areas, key=lambda a: a.width * a.height)
        there.type = "VIEW_3D"
        yield 0.5
    w.check("second_window_has_a_3d_view", there is not None and there.type == "VIEW_3D")
    region = next(r for r in there.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=second, area=there, region=region):
        t.begin(bpy.context, "demo")
    yield 0.5
    plays = t.area()
    w.check("plays_in_the_second_window", plays is not None and plays == there,
            "plays in %s" % ("the main window" if plays is not None and plays == area else plays))
    yield 0.5
    plays = t.area()
    w.check("stays_in_the_second_window", plays is not None and plays == there)
    t.end()
    yield 0.3
    with bpy.context.temp_override(window=win, area=area, region=view):
        t.begin(bpy.context, "demo")
    yield 0.5
    plays = t.area()
    w.check("from_the_main_window_plays_there", plays is not None and plays == area)
    t.end()
    with bpy.context.temp_override(window=second):
        bpy.ops.wm.window_close()
    yield 0.5


w.run(steps, "tutorial_window")
