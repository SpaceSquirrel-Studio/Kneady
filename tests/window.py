"""What Kneady's window probes share (tests/probe_*.py): the 3D view, the
mouse moved and clicked by Blender's event simulation, screenshots, the
sidebar's Kneady tab, and running a probe's steps from a timer.

A probe is started with

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_<name>.py

and its steps are a generator: each `yield` gives Blender that many seconds
to draw and handle the events sent before going on.

Be kind to the desktop it runs on: twice a probe window left Greg's taskbar
unable to take a click until Windows Explorer was restarted. The window
ignores the real mouse, so:

- give it a modest size clear of the taskbar (--window-geometry: its lower
  left corner, then width and height)
- open a .blend inside the probe without its UI (load_ui=False), not on the
  command line, where the file's own window size wins
- let run() quit Blender the ordinary way when the probe is done
"""

import os
import sys
import traceback

import bpy  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Vector  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.environ.get("KNEADY_SHOTS") or os.path.join(HERE, "output", "screens")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append("%s  %s%s" % ("PASS" if ok else "FAIL", name, "  " + detail if detail and not ok else ""))


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


def shot(name):
    os.makedirs(SHOTS, exist_ok=True)
    win, area, region, _rv3d = view()
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=os.path.join(SHOTS, name + ".png"))


def kneady_tab():
    """Open the sidebar on its Kneady tab by clicking down the tab strip, as
    a person would (the tab cannot be set from Python)."""
    win, area, _region, _rv3d = view()
    area.spaces.active.show_region_ui = True
    yield 0.3
    ui = next(r for r in area.regions if r.type == "UI")
    tx = ui.x + ui.width - 10
    for k in range(50):
        ty = area.y + area.height - 60 - 15 * k
        if ty < area.y:
            break
        yield from move(win, tx, ty, 1)
        yield from click(win, tx, ty)
        if ui.active_panel_category == "Kneady":
            break
    check("sidebar_has_a_kneady_tab", ui.active_panel_category == "Kneady", "tab: %s" % ui.active_panel_category)


def hover_point(win, point):
    """Move the mouse onto a point in the world, from a little to its left."""
    x, y = to_window(point)
    yield from move(win, x - 40, y, 2)
    yield from move(win, x, y, 5)
    return x, y


def hover_region(win, mesh, _region_id=None):
    """Move the mouse onto the test arm's upper half (test_data_life._arm's
    region)."""
    return (yield from hover_point(win, mesh.matrix_world @ Vector((0.0, 0.0, 1.6))))


def run(steps, name):
    """Run a probe's steps from a timer, then print its results and quit."""
    def start():
        gen = steps()

        def tick():
            try:
                return next(gen)
            except StopIteration:
                pass
            except AssertionError as exc:
                RESULTS.append("FAIL  %s  %s" % (name, exc))
            except Exception:
                RESULTS.append("CRASH %s\n%s" % (name, traceback.format_exc()))
            print("\n".join(RESULTS))
            print("INFO  screenshots in %s" % SHOTS)
            sys.stdout.flush()
            quit_blender()
            return None

        bpy.app.timers.register(tick, first_interval=0.1)

    bpy.app.timers.register(lambda: start() or None, first_interval=1.0)


def quit_blender():
    """Close Blender the ordinary way, taking its windows down as a person's
    quit does (os._exit left a dead window on Windows' taskbar). There is no
    Save prompt: it is turned off in this session's preferences only, which
    --factory-startup never saves. Falls back to os._exit only if that
    fails."""
    try:
        bpy.context.preferences.view.use_save_prompt = False
        win = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=win):
            bpy.ops.wm.quit_blender()
    except Exception:
        sys.stdout.flush()
        os._exit(0)
