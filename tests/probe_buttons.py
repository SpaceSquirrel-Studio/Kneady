"""Kneady's buttons in a window, on this computer:

    blender --factory-startup --enable-event-simulate --python tests/probe_buttons.py

It checks:

- a toggle switched by a real click, lit while on and undone with Ctrl+Z
- with Labels: On Hover, the name of the button under the mouse shown under
  it; with Labels: Always, every name shown and the buttons spaced for them
- the panel drawn with a toggle, two commands in a direction and Copy / Paste
- a Show Through cap hidden in a box catching the hover as the mouse leaves
  its arm beside it, and holding it a little past its edge

Screenshots go into $KNEADY_SHOTS, or tests/output/screens. It prints PASS or
FAIL lines and quits.
"""

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

RESULTS = ps.RESULTS


def circles(mesh, region):
    """The region's circles in window pixels, {index: (x, y)}."""
    core = rigs.kneady()
    win, area, view_region, _rv3d = ps.view()
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        found = core.button_layout(bpy.context, mesh, region)
    return {i: (int(view_region.x + c.x), int(view_region.y + c.y)) for i, c in found}


def steps():
    core = rigs.kneady()
    bpy.context.preferences.view.show_tooltips = False    # clean screenshots; this session only
    win, area, view_region, _rv3d = ps.view()
    yield from ps.click(win, 120, 600)                    # the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    rig, mesh, reg = test_data_life._arm()
    reg.button_count = 3
    reg.buttons[0].name = "Bend"
    toggle = reg.buttons[1]
    toggle.name = "Wireframe"
    toggle.action = "TOGGLE"
    toggle.switch.data_path = "show_wire"
    twist = reg.buttons[2]
    twist.name = "Twist"
    twist.across.enabled = True
    twist.across.kind, twist.across.axis, twist.across.target, twist.across.bone = "ROTATE", "Y", rig, "Lower"
    twist.across.more.add().kind = "ROTATE"
    bpy.context.scene.kneady_on = True
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        test_data_life._select_only(mesh)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
    bpy.ops.ed.undo_push(message="set up")
    yield 0.5
    # the panel: the toggle, Command 1 and 2, Copy and Paste
    yield from ps.kneady_tab()
    reg_list = mesh.kneady
    reg_list.index = 0
    yield from ps.move(win, 300, 300, 3)
    ps.shot("buttons_panel")
    area.spaces.active.show_region_ui = False
    yield 0.3
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        bpy.ops.view3d.view_selected()
    yield 0.3
    yield from ps.hover_region(win, mesh, reg.id)
    ps.check("hover", core.STATE["hover"] == (mesh.name, reg.id), "hover: %s" % (core.STATE["hover"],))
    spots = circles(mesh, reg)
    # On Hover: the toggle's circle under the mouse, its name shown
    x, y = spots[1]
    yield from ps.move(win, x, y, 4)
    ps.check("toggle_under_the_mouse", core.STATE["button"] == 1, "button: %s" % core.STATE["button"])
    ps.shot("label_on_hover")
    yield from ps.click(win, x, y)
    yield from ps.move(win, x, y, 3)
    lit = core.switch_state(core.switch_channels(toggle, mesh, reg))
    ps.check("click_switches_the_toggle_on", mesh.show_wire and lit, "show_wire %s, lit %s" % (mesh.show_wire, lit))
    ps.check("click_turns_nothing", rigs.angle_of(rig.pose.bones["Lower"]) < 0.01)
    ps.shot("toggle_on")
    # off the circle, still on the region: lit in the region's own color
    from mathutils import Vector  # type: ignore
    yield from ps.hover_point(win, mesh.matrix_world @ Vector((0.0, 0.0, 1.15)))
    ps.check("still_on_the_region", core.STATE["hover"] == (mesh.name, reg.id) and core.STATE["button"] is None,
             "hover %s, button %s" % (core.STATE["hover"], core.STATE["button"]))
    ps.shot("toggle_lit")
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        bpy.ops.ed.undo()
    yield 0.5
    mesh = bpy.data.objects["Arm"]
    ps.check("undo_switches_it_back", not mesh.show_wire, "show_wire %s after undo" % mesh.show_wire)
    # Always: every name, the circles spaced for them
    reg = core.regions_of(mesh)[0]
    before = circles(mesh, reg)
    bpy.context.scene.kneady_labels = "ALWAYS"
    yield from ps.move(win, 300, 300, 2)
    yield from ps.hover_region(win, mesh, reg.id)
    after = circles(mesh, reg)
    wider = abs(after[2][0] - after[0][0]) >= abs(before[2][0] - before[0][0])
    ps.check("always_spaces_the_circles", wider, "%s -> %s" % (before, after))
    ps.shot("labels_always")
    bpy.context.scene.kneady_labels = "HOVER"
    yield from through_reach(win, area, view_region)


def through_reach(win, area, view_region):
    """A cap hidden in a box, as a finger's start cap is hidden in its palm.
    Greg had "trouble sometimes transitioning from the main digit body to a
    cap", and found "the caps are thin at the edges ... I can pretty easily
    mouse off". Checked:

    - leaving the arm just past the cap's edge, the cap catches the hover
    - a little past its edge, the cap holds the hover
    - further off, it lets go
    - moving onto the cap from the body takes the hover at once
    """
    import bmesh  # type: ignore
    from mathutils import Matrix, Vector  # type: ignore
    from bpy_extras import view3d_utils  # type: ignore
    core = rigs.kneady()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    _rig, arm = rigs.arm_rig("Finger")
    body = core.new_region(arm, "Body", whole=True)
    cap = core.new_region(arm, "Cap")
    cap.show_through = True
    core.tag_faces(arm.data, [p.index for p in arm.data.polygons if p.center.z < 0.5], cap.id)
    rv3d = area.spaces.active.region_3d
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        test_data_life._select_only(arm)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
    yield 0.4

    def screen(z, x=0.0):
        return view3d_utils.location_3d_to_region_2d(view_region, rv3d, arm.matrix_world @ Vector((x, 0.0, z)))

    with bpy.context.temp_override(window=win, area=area, region=view_region):
        reach = core.THROUGH_REACH * core.button_radius(bpy.context)
    per_unit = (screen(1.0) - screen(0.0)).length
    # a palm covering the cap and a strip of the body above it, the strip 40%
    # of the reach. There the scene's ray meets the palm, while a ray against
    # the arm alone meets its body
    top = 0.5 + 0.4 * reach / per_unit
    me = bpy.data.meshes.new("Palm")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0.0, 0.0, 0.5)) @ Matrix.Diagonal((2.0, 2.0, 1.0, 1.0)))
    for v in bm.verts:
        v.co.z = top if v.co.z > 0.5 else -1.0
    bm.to_mesh(me)
    bm.free()
    palm = bpy.data.objects.new("Palm", me)
    bpy.context.scene.collection.objects.link(palm)
    palm_region = core.new_region(palm, "Palm", whole=True)
    core.forget()
    bpy.context.view_layer.update()
    yield 0.3

    def hover_at(z, prev, pixels=0.0, x=0.0):
        """The hover with the mouse at height z (plus `pixels` up), coming
        from `prev`."""
        core.STATE.update(hover=prev, button=None, block=False)
        core._HIT["key"] = None
        p = screen(z, x) + Vector((0.0, pixels))
        with bpy.context.temp_override(window=win, area=area, region=view_region):
            core.hit_at(bpy.context, (p.x, p.y))
        return core.STATE["hover"]

    on_body, on_cap = (arm.name, body.id), (arm.name, cap.id)
    strip = 0.5 + 0.2 * reach / per_unit
    ps.check("cap_entered_from_the_body_at_once", hover_at(0.25, on_body) == on_cap)
    ps.check("cap_catches_the_mouse_leaving_its_object", hover_at(strip, on_body) == on_cap,
             "hover %s" % (hover_at(strip, on_body),))
    ps.check("cap_holds_a_little_past_its_edge", hover_at(0.5, on_cap, 0.7 * reach) == on_cap,
             "hover %s" % (hover_at(0.5, on_cap, 0.7 * reach),))
    ps.check("cap_lets_go_further_off", hover_at(0.5, on_cap, 1.6 * reach) == on_body,
             "hover %s" % (hover_at(0.5, on_cap, 1.6 * reach),))
    ps.check("cap_lets_go_to_the_palm", hover_at(0.0, on_cap, -1.6 * reach) == (palm.name, palm_region.id),
             "hover %s" % (hover_at(0.0, on_cap, -1.6 * reach),))
    on_palm = (palm.name, palm_region.id)
    ps.check("body_leaves_for_the_palm_away_from_the_cap", hover_at(0.3, on_body, 0.0, 0.6) == on_palm,
             "hover %s" % (hover_at(0.3, on_body, 0.0, 0.6),))
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        bpy.ops.view3d.view_axis(type="FRONT")
    ps.shot("through_reach")


ps.run(steps, "buttons")
