"""3D handles in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_handles.py

Greg asked for handles "More like grabbing an empty and dragging it in space
... The button would be 3D and wouldn't rotate with screenspace."

The test arm has five placed buttons drawn as handles, each pointing from
what it drives:

- Slide moves Upper along its own Y, up the arm (Lower is connected to
  Upper, so it cannot move itself). A drag along Slide's arrow carries the
  arrow with it, under the mouse, as grabbing an empty does. Slide is a
  Double Arrow (Greg: "a double-headed arrow on a straight line to suggest
  'go either way'").
- Turn turns Lower about its Z, across the view. A drag along its arrow
  turns the bone so the arrow's point follows the mouse.
- Nudge moves Upper along its X and takes the shape of a cone modeled along
  +Y (Greg: "3D buttons would have an option for arrows or 3D file"). It is
  drawn as the cone in 3D, and follows the mouse as the arrows do.
- Dial turns Lower about its Z and shows as a ring. Face on, a quarter turn
  swept about its middle turns the bone a quarter turn the way swept. Seen
  edge on from the side, a drag along its rim turns it as far as the rim
  went, like a wheel turned by its edge.
- Shift is a Quad Arrow: Up / Down moves Upper up the arm, Left / Right
  across it. A drag on the slant carries it on the slant, under the mouse.

Seen end on - from above, with Slide pointing at the viewer - an arrow fades
and takes no press. Each handle's name goes under it (Greg: "the label
should go underneath an arrow").

Prints PASS or FAIL lines and quits; screenshots go in tests/output."""

import importlib
import os
import sys

import math

import bmesh  # type: ignore
import bpy  # type: ignore
from mathutils import Matrix, Vector  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import rigs  # noqa: E402
import window as w  # noqa: E402


def _place(placed, mesh, region, button, world, normal):
    """A button placed at a world point, as placing it by hand would."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    frame = placed.frame_of(mesh, region)
    center, half = placed.region_box(mesh, region, depsgraph, frame)
    local = frame.inverted_safe() @ world
    button.place = ((local.x - center.x) / half.x, (local.y - center.y) / half.y, (local.z - center.z) / half.z)
    button.place_normal = (frame.to_3x3().transposed() @ normal).normalized()
    button.placed = button.place_set = True
    button.handle = "HANDLE"


def steps():
    core = rigs.kneady()
    package = core.__name__.rsplit(".", 1)[0]
    placed = sys.modules[package + ".placed"]
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 120, 600)                     # the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    rig, mesh = rigs.arm_rig()
    # the forearm's faces, as a rig's region per bone has them
    region = core.new_region(mesh, "Forearm")
    core.tag_faces(mesh.data, core.group_faces(mesh, ["Lower"]), region.id)
    region.button_count = 5
    # Turn goes first. Placed buttons ride the bone of their region's first
    # drag button, so both arrows ride the forearm: the bone Turn turns, and
    # the child of the one Slide moves
    turn, slide = region.buttons[0], region.buttons[1]
    SLIDE, TURN = 1, 0
    slide.name, turn.name = "Slide", "Turn"
    slide.up.enabled, slide.up.kind, slide.up.axis, slide.up.target, slide.up.bone = True, "MOVE", "Y", rig, "Upper"
    slide.across.enabled = False
    turn.up.enabled, turn.up.kind, turn.up.axis, turn.up.target, turn.up.bone = True, "ROTATE", "Z", rig, "Lower"
    turn.across.enabled = False
    # Nudge: a cone modeled along +Y for its shape
    NUDGE = 2
    nudge = region.buttons[NUDGE]
    nudge.name = "Nudge"
    nudge.up.enabled, nudge.up.kind, nudge.up.axis, nudge.up.target, nudge.up.bone = True, "MOVE", "X", rig, "Upper"
    nudge.across.enabled = False
    me = bpy.data.meshes.new("HandleCone")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.3, radius2=0.0, depth=1.0,
                          matrix=Matrix.Translation((0.0, 0.5, 0.0)) @ Matrix.Rotation(-1.5707963, 4, "X"))
    bm.to_mesh(me)
    bm.free()
    cone = bpy.data.objects.new("HandleCone", me)              # in the file, not in the scene
    DIAL = 3
    dial = region.buttons[DIAL]
    dial.name = "Dial"
    dial.up.enabled, dial.up.kind, dial.up.axis, dial.up.target, dial.up.bone = True, "ROTATE", "Z", rig, "Lower"
    dial.across.enabled = False
    SHIFT = 4
    shift = region.buttons[SHIFT]
    shift.name = "Shift"
    shift.up.enabled, shift.up.kind, shift.up.axis, shift.up.target, shift.up.bone = True, "MOVE", "Y", rig, "Upper"
    shift.across.enabled = True
    shift.across.kind, shift.across.axis, shift.across.target, shift.across.bone = "MOVE", "X", rig, "Upper"
    shift.single = False                                       # both arms at once, for the slant
    bpy.context.view_layer.update()
    _place(placed, mesh, region, slide, Vector((-0.05, -0.12, 1.3)), Vector((0.0, -1.0, 0.0)))
    _place(placed, mesh, region, turn, Vector((0.1, -0.2, 1.75)), Vector((0.0, -1.0, 0.0)))
    _place(placed, mesh, region, nudge, Vector((0.12, -0.2, 1.5)), Vector((0.0, -1.0, 0.0)))
    nudge.handle_shape, nudge.handle_object = "OBJECT", cone
    _place(placed, mesh, region, dial, Vector((-0.08, -0.2, 1.95)), Vector((0.0, -1.0, 0.0)))
    dial.handle_shape = "RING"
    slide.handle_shape = "DOUBLE"
    _place(placed, mesh, region, shift, Vector((0.08, -0.2, 1.12)), Vector((0.0, -1.0, 0.0)))
    shift.handle_shape = "CROSS"
    bpy.context.scene.kneady_on = True
    area.spaces.active.show_region_ui = False
    with bpy.context.temp_override(window=win, area=area, region=view):
        for o in bpy.context.selected_objects:
            o.select_set(False)
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
    yield 0.5
    lower, upper = rig.pose.bones["Lower"], rig.pose.bones["Upper"]

    def handles():
        with bpy.context.temp_override(window=win, area=area, region=view):
            return core.layout_handles(bpy.context, mesh, region)

    yield from w.hover_point(win, mesh.matrix_world @ Vector((0.0, -0.2, 1.5)))
    found = handles()
    w.check("arrows_drawn", sorted(found) == [TURN, SLIDE, NUDGE, DIAL, SHIFT]
            and all(h["live"] for h in found.values()),
            "handles %s" % {i: round(h["ratio"], 2) for i, h in found.items()})
    if SLIDE in found:
        up = (found[SLIDE]["tip"] - found[SLIDE]["base"]).normalized()
        w.check("slide_points_up_the_arm", up.y > 0.95, str(tuple(up)))
    if NUDGE in found:
        h = found[NUDGE]
        right = (h["tip"] - h["base"]).normalized()
        w.check("shape_drawn_in_3d", bool(h["tris"]) and right.x > 0.95,
                "%d triangles, pointing %s" % (len(h["tris"] or ()), tuple(round(v, 2) for v in right)))
    if SLIDE in found:
        w.check("double_arrow_has_two_heads", len(found[SLIDE]["parts"][0]["heads"]) == 2)
    if SHIFT in found:
        arms = found[SHIFT].get("arms", {})
        up = (arms[1]["tip"] - arms[1]["base"]).normalized() if 1 in arms else Vector()
        right = (arms[0]["tip"] - arms[0]["base"]).normalized() if 0 in arms else Vector()
        w.check("quad_arrow_drawn", sorted(arms) == [0, 1] and up.y > 0.95 and right.x > 0.95,
                "arms %s: up %s, right %s" % (sorted(arms), tuple(round(v, 2) for v in up),
                                              tuple(round(v, 2) for v in right)))
    draw = sys.modules[package + ".draw"]
    if SLIDE in found:
        h = found[SLIDE]
        at = draw._arrow_label_at(h, slide, bpy.context, core.button_radius(bpy.context), 1.0)
        # _draw_labels puts the box a radius under `at`: under the arrow's lowest point
        w.check("label_under_the_arrow", at.y - core.button_radius(bpy.context) <= h["bounds"][1] + 1e-3
                and h["bounds"][0] - 1 <= at.x <= h["bounds"][2] + 1, "%s, bounds %s" % (tuple(at), h["bounds"]))
    w.shot("handles_front")
    # Slide: pressed on its shaft, dragged 72 px along it
    if SLIDE in found:
        h = found[SLIDE]
        grab = h["base"] + (h["tip"] - h["base"]) * 0.5
        x, y = int(view.x + grab.x), int(view.y + grab.y)
        yield from w.move(win, x, y, 3)
        w.check("slide_under_the_mouse", core.STATE["button"] == SLIDE, "button %s" % core.STATE["button"])
        before = h["base"].copy()
        start = upper.location.copy()
        win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        yield 0.15
        for k in range(1, 7):
            yield from w.move(win, x, y + 12 * k, 1)
        # hidden while dragged, as every button is (Greg: "the geo buttons
        # needs to disappear while hauling like the screenspace buttons do")
        w.check("arrow_hidden_while_dragged", core.STATE["dragging"], "not dragging")
        w.shot("handles_slide_dragged")
        win.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y + 72)
        yield 0.4
        yield from w.move(win, x, y + 72, 2)
        after = handles().get(SLIDE)
        moved = (upper.location - start).length
        carried = (after["base"] - before) if after is not None else Vector((0.0, 0.0))
        w.check("slide_follows_the_mouse", abs(carried.y - 72.0) < 3.0 and abs(carried.x) < 3.0 and moved > 1e-3,
                "the arrow moved %s px for the mouse's 72; the bone %.4f" % (tuple(round(v, 1) for v in carried),
                                                                              moved))
        upper.location = start
        bpy.context.view_layer.update()
        core.forget()
        yield 0.3
    # Nudge: the cone dragged 50 px along it, following the mouse
    found = handles()
    if NUDGE in found:
        h = found[NUDGE]
        grab = h["base"] + (h["tip"] - h["base"]) * 0.5
        x, y = int(view.x + grab.x), int(view.y + grab.y)
        yield from w.move(win, x, y, 3)
        w.check("shape_under_the_mouse", core.STATE["button"] == NUDGE, "button %s" % core.STATE["button"])
        before = h["base"].copy()
        start = upper.location.copy()
        win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        yield 0.15
        for k in range(1, 6):
            yield from w.move(win, x + 10 * k, y, 1)
        win.event_simulate("LEFTMOUSE", "RELEASE", x=x + 50, y=y)
        yield 0.4
        yield from w.move(win, x + 50, y, 2)
        after = handles().get(NUDGE)
        carried = (after["base"] - before) if after is not None else Vector((0.0, 0.0))
        w.check("shape_follows_the_mouse", abs(carried.x - 50.0) < 3.0 and abs(carried.y) < 3.0,
                "the shape moved %s px for the mouse's 50" % (tuple(round(v, 1) for v in carried),))
        upper.location = start
        bpy.context.view_layer.update()
        core.forget()
        yield 0.3
    # Shift: dragged 30 px right and 30 px up, the cross going with the mouse
    found = handles()
    if SHIFT in found:
        h = found[SHIFT]
        arm = h["arms"][1]
        grab = arm["base"] + (arm["tip"] - arm["base"]) * 0.6
        x, y = int(view.x + grab.x), int(view.y + grab.y)
        yield from w.move(win, x, y - 4, 2)
        yield from w.move(win, x, y, 3)
        w.check("quad_arrow_under_the_mouse", core.STATE["button"] == SHIFT, "button %s" % core.STATE["button"])
        before = h["base"].copy()
        start = upper.location.copy()
        win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        yield 0.15
        for k in range(1, 7):
            yield from w.move(win, x + 5 * k, y + 5 * k, 1)
        win.event_simulate("LEFTMOUSE", "RELEASE", x=x + 30, y=y + 30)
        yield 0.4
        yield from w.move(win, x + 30, y + 30, 2)
        after = handles().get(SHIFT)
        carried = (after["base"] - before) if after is not None else Vector((0.0, 0.0))
        w.check("quad_arrow_follows_the_mouse", abs(carried.x - 30.0) < 3.0 and abs(carried.y - 30.0) < 3.0,
                "the cross moved %s px for the mouse's (30, 30)" % (tuple(round(v, 1) for v in carried),))
        upper.location = start
        bpy.context.view_layer.update()
        core.forget()
        yield 0.3
    # Turn: dragged 40 px along it, its point going the way of the mouse
    found = handles()
    if TURN in found:
        h = found[TURN]
        grab = h["base"] + (h["tip"] - h["base"]) * 0.5
        x, y = int(view.x + grab.x), int(view.y + grab.y)
        u = (h["tip"] - h["base"]).normalized()
        yield from w.move(win, x, y, 3)
        w.check("turn_under_the_mouse", core.STATE["button"] == TURN, "button %s" % core.STATE["button"])
        before = h["base"].copy()
        win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        yield 0.15
        for k in range(1, 5):
            yield from w.move(win, int(x + u.x * 10 * k), int(y + u.y * 10 * k), 1)
        win.event_simulate("LEFTMOUSE", "RELEASE", x=int(x + u.x * 40), y=int(y + u.y * 40))
        yield 0.4
        yield from w.move(win, int(x + u.x * 40), int(y + u.y * 40), 2)
        after = handles().get(TURN)
        went = (after["base"] - before) if after is not None else Vector((0.0, 0.0))
        along = went.dot(u)
        w.check("turn_follows_the_mouse", 34.0 < along < 46.0,
                "its point went %.1f px along the arrow for the mouse's 40 (%s)" % (along, tuple(round(v, 1)
                                                                                             for v in went)))
        w.shot("handles_turned")
        lower.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        lower.rotation_euler = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        core.forget()
    # Dial: face on, a quarter turn swept counterclockwise about its middle
    lower.rotation_mode = "XYZ"
    found = handles()
    h = found.get(DIAL)
    w.check("ring_drawn", h is not None and bool(h.get("rim")) and h["face_on"] > 0.9,
            "face on %s" % (round(h["face_on"], 3) if h else None))
    if h is not None:
        c, r = h["base"], h["r_px"]
        at = lambda a: (int(view.x + c.x + r * math.cos(a)), int(view.y + c.y + r * math.sin(a)))  # noqa
        x, y = at(0.0)
        yield from w.move(win, x - 3, y, 2)
        yield from w.move(win, x, y, 3)
        w.check("ring_under_the_mouse", core.STATE["button"] == DIAL, "button %s" % core.STATE["button"])
        win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        yield 0.15
        for k in range(1, 10):
            yield from w.move(win, *at(math.pi / 2.0 * k / 9.0), 1)
        win.event_simulate("LEFTMOUSE", "RELEASE", x=at(math.pi / 2.0)[0], y=at(math.pi / 2.0)[1])
        yield 0.4
        angle = math.degrees(lower.matrix_basis.to_quaternion().angle)
        tail = rig.matrix_world @ lower.tail
        w.check("ring_turns_as_far_as_swept", abs(angle - 90.0) < 6.0, "%.1f degrees for a quarter turn" % angle)
        # counterclockwise on screen: the forearm's end goes left
        w.check("ring_turns_the_way_swept", tail.x < -0.5, "the forearm's end at x %.3f" % tail.x)
        w.shot("handles_ring_turned")
        lower.rotation_euler = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        core.forget()
        yield 0.3
    # from the side the ring is edge on: a drag along its rim turns it by the rim's travel
    with bpy.context.temp_override(window=win, area=area, region=view):
        bpy.ops.view3d.view_axis(type="RIGHT")
    yield 0.5
    # hover the forearm first (from here the ring sits at its edge), then the ring
    yield from w.hover_point(win, mesh.matrix_world @ Vector((0.0, 0.0, 1.9)))
    found = handles()
    h = found.get(DIAL)
    w.check("ring_edge_on", h is not None and h["face_on"] < placed.RING_EDGE,
            "face on %s" % (round(h["face_on"], 3) if h else None))
    if h is not None:
        x, y = int(view.x + h["base"].x), int(view.y + h["base"].y)
        for k in range(1, 5):
            yield from w.move(win, x + (4 - k) * 3, y, 1)
        hit = core.STATE["button"] == DIAL
        w.check("ring_edge_on_under_the_mouse", hit, "button %s" % core.STATE["button"])
        if hit:
            win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
            yield 0.15
            for k in range(1, 5):
                yield from w.move(win, x, y + 5 * k, 1)
            win.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y + 20)
            yield 0.4
            angle = lower.matrix_basis.to_quaternion().angle
            want = 20.0 / h["r_px"]
            w.check("ring_edge_on_turns_by_the_rim", abs(angle - want) < 0.25 * want,
                    "%.3f radians for 20 px along a rim %.1f px round (%.3f)" % (angle, h["r_px"], want))
            lower.rotation_euler = (0.0, 0.0, 0.0)
            bpy.context.view_layer.update()
            core.forget()
            yield 0.3
    # from above: Slide points at the viewer, faint, and takes no press
    with bpy.context.temp_override(window=win, area=area, region=view):
        bpy.ops.view3d.view_axis(type="TOP")
    yield 0.5
    point = placed.button_point(mesh, region, slide, bpy.context.evaluated_depsgraph_get())[0]
    yield from w.hover_point(win, point)
    found = handles()
    h = found.get(SLIDE)
    # dimmed, still drawn (Greg: "unable to haul but not disappear")
    w.check("end_on_dims_but_shows", h is not None and not h["live"] and 0.0 < placed.handle_alpha(h) < 1.0,
            "ratio %s" % (round(h["ratio"], 3) if h else None))
    # the forearm hovered (its end, seen from above), the arrow there, end on
    w.check("end_on_takes_no_press", core.STATE["hover"] == (mesh.name, region.id)
            and core.STATE["button"] != SLIDE, "hover %s, button %s" % (core.STATE["hover"], core.STATE["button"]))
    w.shot("handles_end_on")


w.run(steps, "handles")
