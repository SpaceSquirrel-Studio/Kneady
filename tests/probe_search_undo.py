"""A pick from a search field gets its own undo step, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_search_undo.py

Greg found that "changing input then hauling to test it then undoing undoes
the haul and setting the input. Makes testing this tedious." Blender gives a
pick from a search field no undo step of its own; props.searched gives it
one.

The probe runs twice in the real sidebar: once picking a command's Input
from its search, then once picking its Bone. Each time it finds the field by
hovering down the sidebar, picks by typing and pressing Enter, drags on the
item, then presses Ctrl+Z. The drag must be undone and the pick must stay.
Prints PASS or FAIL lines and quits."""

import importlib
import os
import sys

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import rigs  # noqa: E402
import window as w  # noqa: E402


def key(win, name, x, y, **mods):
    win.event_simulate(name, "PRESS", x=x, y=y, **mods)
    yield 0.05
    win.event_simulate(name, "RELEASE", x=x, y=y, **mods)
    yield 0.1


def named(win, area, ui, x, y, wait):
    """Move the mouse to (x, y) and return the data path of the field under
    it."""
    win.event_simulate("MOUSEMOVE", "NOTHING", x=x, y=y)
    yield wait
    wm = bpy.context.window_manager
    wm.clipboard = ""
    try:
        with bpy.context.temp_override(window=win, area=area, region=ui):
            bpy.ops.ui.copy_data_path_button(full_path=False)
    except RuntimeError:
        return ""
    return wm.clipboard


def find_field(win, area, field):
    """Hover down the sidebar to the field named `field` (by the data path
    Blender copies for it), and leave the mouse on it. It must stay there
    because a click goes to the button under the last mouse move, wherever
    the click itself is. Returns (x, y), or None."""
    ui = next(r for r in area.regions if r.type == "UI")
    middle = (ui.x + ui.width // 2, ui.y + ui.height // 2)
    for wheel, times in (("WHEELUPMOUSE", 40), ("WHEELDOWNMOUSE", 12)):   # the top, then the command
        for _k in range(times):
            win.event_simulate(wheel, "PRESS", x=middle[0], y=middle[1])
            yield 0.03
    yield 0.3
    # the whole sidebar, at the interface's scale: a Retina screen draws it at
    # twice the pixels, and a fixed 120 steps of 8 stopped short of the field
    scale = getattr(bpy.context.preferences.system, "ui_scale", 0.0) or 1.0
    top, step = ui.y + ui.height - int(30 * scale), max(1, int(8 * scale))
    for fx in (0.75, 0.5):
        x = int(ui.x + ui.width * fx)
        hits = []
        for y in range(top, ui.y - 1, -step):
            path = yield from named(win, area, ui, x, y, 0.04)
            if path.endswith("." + field):
                hits.append(y)
            elif hits:
                break
        # try its middle first, then each spot that named it, letting the
        # mouse settle on each. A quick pass can name the row it has just left
        for y in [(hits[0] + hits[-1]) // 2] + hits if hits else []:
            path = yield from named(win, area, ui, x, y, 0.3)
            if path.endswith("." + field):
                print("INFO  %s field at %d, %d (%d-%d), scale %.2f" % (field, x, y, hits[-1], hits[0], scale))
                return x, y
    return None


def pick(win, x, y, text):
    """Click a search field, type `text` and press Enter, taking its first
    match."""
    yield from key(win, "LEFTMOUSE", x, y)
    yield 0.3
    for ch in text:
        win.event_simulate(ch.upper(), "PRESS", x=x, y=y, unicode=ch)
        yield 0.05
        win.event_simulate(ch.upper(), "RELEASE", x=x, y=y)
        yield 0.05
    yield 0.2
    yield from key(win, "RET", x, y)
    yield 0.4


def haul(win, mesh):
    p = w.to_window(mesh.matrix_world @ Vector((0.0, -0.2, 1.5)))
    yield from w.move(win, p[0] - 30, p[1], 2)
    yield from w.move(win, p[0], p[1], 3)
    win.event_simulate("LEFTMOUSE", "PRESS", x=p[0], y=p[1])
    yield 0.1
    for k in range(1, 7):
        yield from w.move(win, p[0], p[1] + 10 * k, 1)
    win.event_simulate("LEFTMOUSE", "RELEASE", x=p[0], y=p[1] + 60)
    yield 0.5


def steps():
    core = rigs.kneady()
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 120, 600)                      # the splash away
    for field, before, picked in (("input", "Other", "Amount"), ("bone", "Lower", "Upper")):
        # a clean scene - not a new file, which would stop this probe's timer
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.node_groups):
            for item in list(coll):
                coll.remove(item)
        yield 0.3
        win, area, view, _rv3d = w.view()
        rig, mesh = rigs.arm_rig()
        region = core.new_region(mesh, "Arm", whole=True)
        b = region.buttons[0]
        if field == "input":
            ng = bpy.data.node_groups.new("Inputs", "GeometryNodeTree")
            ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
            for name in ("Amount", "Other"):
                ng.interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
            ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
            n_in, n_out = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
            ng.links.new(n_in.outputs[0], n_out.inputs[0])
            mesh.modifiers.new("Inputs", "NODES").node_group = ng
            b.up.enabled, b.up.kind, b.up.input = True, "INPUT", before
        else:
            b.up.enabled, b.up.kind, b.up.axis, b.up.target, b.up.bone = True, "ROTATE", "X", rig, before
        b.across.enabled = False
        b.ui_open = True
        b.up.command_open = True           # the Bone field is in its folded part
        bpy.context.scene.kneady_on = True
        with bpy.context.temp_override(window=win, area=area, region=view):
            for o in bpy.context.selected_objects:
                o.select_set(False)
            mesh.select_set(True)
            bpy.context.view_layer.objects.active = mesh
            bpy.ops.view3d.view_axis(type="FRONT")
            bpy.ops.view3d.view_selected()
            # select its row in the tree, as a person would. Since the panel
            # became a tree, it shows a button's settings only for that row
            rigs.module("tree").follow(bpy.context, region, 0, obj=mesh)
            bpy.ops.ed.undo_push(message="Set up")
        yield 0.5
        ui = next(r for r in area.regions if r.type == "UI")
        if not area.spaces.active.show_region_ui or ui.active_panel_category != "Kneady":
            yield from w.kneady_tab()
        yield from key(win, "ESC", 500, 380)                # any popup a click opened
        yield 0.4
        win, area, view, _rv3d = w.view()
        at = yield from find_field(win, area, field)
        w.check("%s_field_found" % field, at is not None)
        if at is None:
            w.shot("search_undo_%s_not_found" % field)
            continue
        yield from pick(win, at[0], at[1], picked)
        names = (rig.name, mesh.name)

        def command():
            m = bpy.data.objects[names[1]]
            return core.own_regions(m)[0].buttons[0].up

        w.check("%s_picked" % field, getattr(command(), field) == picked, repr(getattr(command(), field)))
        yield from haul(win, bpy.data.objects[names[1]])
        if field == "input":
            mod = bpy.data.objects[names[1]].modifiers["Inputs"]
            ident = next(i.identifier for i in mod.node_group.interface.items_tree
                         if getattr(i, "in_out", "") == "INPUT" and i.name == "Amount")
            moved = lambda: abs(core.input_value(bpy.data.objects[names[1]].modifiers["Inputs"], ident))  # noqa
        else:
            moved = lambda: bpy.data.objects[names[0]].pose.bones["Upper"].rotation_quaternion.angle  # noqa
        w.check("%s_hauled" % field, moved() > 1e-3, "%.4f" % moved())
        yield from key(win, "Z", 500, 380, ctrl=True)
        yield 0.6
        w.check("%s_undo_takes_the_haul" % field, moved() < 1e-5, "%.5f" % moved())
        w.check("%s_undo_keeps_the_pick" % field, getattr(command(), field) == picked,
                repr(getattr(command(), field)))


w.run(steps, "search_undo")
