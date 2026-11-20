"""Pinning a region with no menu, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_pin.py

Greg found: "I can't pin the Cap regions. I think it's because there's no
sub menus." The test region has two buttons and no menu: Bend (a drag) and
Wireframe (a toggle). With real clicks:

- a Shift+click on Bend pins the region. Nothing turns and the selection is
  left as it was. The region stays hovered with the mouse off it
- a Shift+click on Wireframe lets go, without switching the toggle
- a Shift+click on Wireframe pins it again, and Esc lets go
- a plain click on Wireframe switches it

Prints PASS or FAIL lines and quits."""

import importlib
import os
import sys

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402
import test_data_life  # noqa: E402


def circles(mesh, region):
    core = rigs.kneady()
    win, area, view, _rv3d = w.view()
    with bpy.context.temp_override(window=win, area=area, region=view):
        found = core.button_layout(bpy.context, mesh, region)
    return {i: (int(view.x + c.x), int(view.y + c.y)) for i, c in found}


def shift_click(win, x, y):
    win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y, shift=True)
    yield 0.1
    win.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y, shift=True)
    yield 0.3


def steps():
    core = rigs.kneady()
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 120, 600)                       # the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    rig, mesh, reg = test_data_life._arm()
    reg.button_count = 2
    reg.buttons[0].name = "Bend"
    toggle = reg.buttons[1]
    toggle.name, toggle.action, toggle.switch.data_path = "Wireframe", "TOGGLE", "show_wire"
    bpy.context.scene.kneady_on = True
    area.spaces.active.show_region_ui = False
    with bpy.context.temp_override(window=win, area=area, region=view):
        test_data_life._select_only(mesh)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
    yield 0.5
    key = (mesh.name, reg.id)
    yield from w.hover_region(win, mesh, reg.id)
    w.check("hover", core.STATE["hover"] == key, str(core.STATE["hover"]))
    spots = circles(mesh, reg)
    x, y = spots[0]
    yield from w.move(win, x, y, 3)
    yield from shift_click(win, x, y)
    w.check("shift_click_on_a_drag_pins", core.kept() == key and core.kept_by() == "region",
            "%s by %r" % (core.kept(), core.kept_by()))
    w.check("no_turn", rigs.angle_of(rig.pose.bones["Lower"]) < 1e-3)
    w.check("selection_left_alone", mesh.select_get())
    status = core.idle_status() or ""
    w.check("status_says_pinned", "pinned" in status and reg.name in status, status)
    # off the region, into empty space: still hovered, its buttons shown
    yield from w.move(win, view.x + 60, view.y + 60, 4)
    w.check("kept_off_the_region", core.STATE["hover"] == key, str(core.STATE["hover"]))
    w.shot("pin_kept_off_the_region")
    spots = circles(mesh, reg)
    w.check("buttons_still_shown", set(spots) == {0, 1}, str(spots))
    x, y = spots[1]
    yield from w.move(win, x, y, 3)
    yield from shift_click(win, x, y)
    w.check("shift_click_again_lets_go", core.kept() is None, str(core.kept()))
    w.check("toggle_not_switched", not mesh.show_wire)
    yield from w.hover_region(win, mesh, reg.id)
    x, y = circles(mesh, reg)[1]
    yield from w.move(win, x, y, 3)
    yield from shift_click(win, x, y)
    w.check("shift_click_on_a_toggle_pins", core.kept() == key and not mesh.show_wire,
            "%s, show_wire %s" % (core.kept(), mesh.show_wire))
    yield from w.move(win, view.x + 60, view.y + 60, 3)
    win.event_simulate("ESC", "PRESS", x=view.x + 60, y=view.y + 60)
    yield 0.2
    win.event_simulate("ESC", "RELEASE", x=view.x + 60, y=view.y + 60)
    yield 0.3
    w.check("esc_lets_go", core.kept() is None, str(core.kept()))
    yield from w.hover_region(win, mesh, reg.id)
    x, y = circles(mesh, reg)[1]
    yield from w.move(win, x, y, 3)
    yield from w.click(win, x, y)
    w.check("plain_click_still_switches", mesh.show_wire and core.kept() is None,
            "show_wire %s, kept %s" % (mesh.show_wire, core.kept()))


w.run(steps, "pin")
