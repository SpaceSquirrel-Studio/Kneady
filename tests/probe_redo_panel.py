"""The Adjust Last Operation panel after a real drag, which needs a window:

    blender --factory-startup --enable-event-simulate --python tests/probe_redo_panel.py

The probe drags a region with the mouse and opens the panel Blender shows
for the drag. It clicks the panel's field, types 45 and presses Enter, then
does the same with 30. The bone must end up at each angle.

This checks what the documentation promises - that you can type over a
drag's value afterward - the way a person does it. A test without a window
cannot reach that: the panel has to draw its field, and the redo has to
work from it, more than once. Prints PASS or FAIL and quits.
"""

import importlib
import math
import os
import sys
import traceback

import bpy  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Vector  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import rigs  # noqa: E402
import test_data_life  # noqa: E402


def view():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region, area.spaces.active.region_3d


def to_window(point):
    _win, _area, region, rv3d = view()
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, point)
    return int(region.x + p.x), int(region.y + p.y)


def move(win, x, y, wait=2):
    win.event_simulate("MOUSEMOVE", "NOTHING", x=x, y=y)
    for _ in range(wait):
        yield 0.15


def click(win, x, y):
    win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
    yield 0.1
    win.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y)
    yield 0.3


def key(win, name, text=None, **mods):
    win.event_simulate(name, "PRESS", unicode=text, **mods) if text else win.event_simulate(name, "PRESS", **mods)
    win.event_simulate(name, "RELEASE", **mods)


def steps():
    core = rigs.kneady()
    win, area, region, _rv3d = view()
    yield from click(win, 120, 600)                       # click the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    _rig, mesh, _region = test_data_life._arm()
    bpy.context.scene.kneady_on = True
    with bpy.context.temp_override(window=win, area=area, region=region):
        test_data_life._select_only(mesh)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
        # Leave the scene as a person's edits would: in the undo history,
        # which is what a redo steps back to
        bpy.ops.ed.undo_push(message="Set up")
    yield 0.5
    x, y = to_window(mesh.matrix_world @ Vector((0.0, 0.0, 1.6)))
    yield from move(win, x - 40, y, 2)
    yield from move(win, x, y, 4)
    win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
    yield 0.2
    for k in range(1, 9):
        yield from move(win, x, y + 8 * k, 1)
    win.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y + 64)
    for _ in range(4):
        yield 0.2
    hud = next((r for r in area.regions if r.type == "HUD" and r.width > 10), None)
    assert hud is not None, "no Adjust Last Operation panel after the drag"
    yield from click(win, hud.x + 30, hud.y + hud.height - 15)   # open it
    yield from move(win, 900, 600, 3)
    # Twice, because a redo replaces every object, so the panel's second
    # draw must not use what its first one read
    for typed, keys in ((45.0, ("FOUR", "FIVE")), (30.0, ("THREE", "ZERO"))):
        hud = next(r for r in area.regions if r.type == "HUD" and r.width > 10)
        fx, fy = hud.x + hud.width - 80, hud.y + 22
        yield from move(win, fx, fy, 2)
        yield from click(win, fx, fy)
        key(win, "A", ctrl=True)
        for name in keys:
            key(win, name, {"ZERO": "0", "THREE": "3", "FOUR": "4", "FIVE": "5"}[name])
        yield 0.1
        key(win, "RET")
        for _ in range(4):
            yield 0.2
        pb = bpy.data.objects["ArmRig"].pose.bones["Lower"]
        turned = math.degrees(core.rotation_of(pb).to_quaternion().angle)
        assert abs(turned - typed) < 0.01, "typed %g in the panel, the bone turned %.3f" % (typed, turned)


def run():
    gen = steps()

    def tick():
        try:
            return next(gen)
        except StopIteration:
            print("PASS  redo_panel_types_a_value")
        except AssertionError as exc:
            print("FAIL  redo_panel_types_a_value  %s" % exc)
        except Exception:
            print("CRASH redo_panel_types_a_value\n%s" % traceback.format_exc())
        sys.stdout.flush()
        os._exit(0)

    bpy.app.timers.register(tick, first_interval=0.1)


bpy.app.timers.register(lambda: run() or None, first_interval=1.0)
