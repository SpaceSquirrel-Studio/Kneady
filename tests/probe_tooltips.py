"""Blender's own tooltip in a window. Greg found: "The default hover-over
tooltips are displaying in addition to the ones we've made":

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_tooltips.py

A button's tooltip is Kneady's tip alone. Blender's tooltip (the drag
operator's description) no longer shows beside it. Viewport Edit's icons
keep Blender's tooltip, which says what they do. Blender's tooltips stay on
(the preference), as a person has them. Screenshots of the whole window go
into $KNEADY_SHOTS, or tests/output/screens. Prints PASS or FAIL lines and
quits.
"""

import gc
import importlib
import os
import sys

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as ps  # noqa: E402
import rigs  # noqa: E402
import test_data_life  # noqa: E402


def whole_shot(name):
    os.makedirs(ps.SHOTS, exist_ok=True)
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.screen.screenshot(filepath=os.path.join(ps.SHOTS, name + ".png"))


def gizmos(mesh):
    """The gizmos of Kneady's buttons on `mesh` (not its surface's). Memory
    can hold a gizmo object that was never set up, or one left from a group
    already gone. Blender 4.2 had one with no `target`, so each attribute is
    read with a default."""
    ops = rigs.module("ops")
    return [g for g in gc.get_objects()
            if isinstance(g, ops.KNEADY_GT_region) and getattr(g, "target", None) == mesh.name
            and not getattr(g, "surface", False)]


def steps():
    core = rigs.kneady()
    pick = rigs.module("pick")
    bpy.context.preferences.use_preferences_save = False
    win, area, view, _rv3d = ps.view()
    ps.check("blender_tooltips_on", bpy.context.preferences.view.show_tooltips)
    yield from ps.click(win, 120, 600)                    # the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    _rig, mesh, reg = test_data_life._arm()
    reg.button_count = 2
    reg.buttons[0].name = "Bend"
    reg.buttons[1].name = "Twist"
    reg.buttons[0].tip_text = "Bends the arm at the elbow."
    bpy.context.scene.kneady_on = True
    with bpy.context.temp_override(window=win, area=area, region=view):
        test_data_life._select_only(mesh)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
    yield 0.5
    # a button: Kneady's tip, not Blender's
    yield from ps.hover_region(win, mesh, reg.id)
    with bpy.context.temp_override(window=win, area=area, region=view):
        spots = dict(core.button_layout(bpy.context, mesh, reg))
    x, y = int(view.x + spots[0].x), int(view.y + spots[0].y)
    yield from ps.move(win, x + 2, y, 2)
    yield from ps.move(win, x, y, 2)
    ps.check("on_the_button", core.STATE["button"] == 0, "button: %s" % core.STATE["button"])
    yield 1.8                                            # past both tooltips' delays
    found = gizmos(mesh)
    ps.check("a_button_has_no_blender_tooltip", found and not any(g.use_tooltip for g in found),
             "use_tooltip: %s" % [g.use_tooltip for g in found])
    whole_shot("tooltip_a_button")
    # Viewport Edit's + icon: Blender's tooltip, which says what it does
    bpy.context.window_manager.kneady_pick = True
    yield from ps.move(win, x + 4, y + 2, 3)
    with bpy.context.temp_override(window=win, area=area, region=view):
        icons = pick.edit_icons(bpy.context, mesh, reg)
    plus = icons.get("ADD")
    ps.check("plus_shown", plus is not None, str(sorted(icons)))
    if plus is not None:
        px, py = int(view.x + plus.x), int(view.y + plus.y)
        yield from ps.move(win, px + 2, py, 2)
        yield from ps.move(win, px, py, 2)
        ps.check("on_the_plus", core.STATE.get("edit") == "ADD", str(core.STATE.get("edit")))
        yield 1.8
        ps.check("the_plus_keeps_its_tooltip", any(g.use_tooltip for g in gizmos(mesh)),
                 "use_tooltip: %s" % [g.use_tooltip for g in gizmos(mesh)])
        whole_shot("tooltip_the_plus")
    bpy.context.window_manager.kneady_pick = False


ps.run(steps, "tooltips")
