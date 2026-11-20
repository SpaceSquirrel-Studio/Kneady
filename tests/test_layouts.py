"""Layouts a file carries, played back:
- buttons placed on the item;
- menus;
- Show When;
- a toggle keeping the pose;
- an operator a click runs.
Kneady plays each of them from the settings alone. Here the settings are
written by hand, as a script or another tool would write them."""

import math
import sys

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

import rigs


def _module(name):
    core = rigs.kneady()
    return sys.modules[core.__name__.rsplit(".", 1)[0] + "." + name]


def _arm_region():
    """The test arm, with a property on its rig as its switch (ik, 0), and a
    whole-object region with these buttons:
    - FK Bend turns Lower, and shows while the switch is off;
    - IK / FK is a toggle of ik;
    - IK Move shows while the switch is on;
    - Elbow opens a menu, which holds Elbow X and Elbow Z."""
    core = rigs.kneady()
    menus = _module("menus")
    rig, mesh = rigs.arm_rig()
    rig["ik"] = 0.0
    region = core.new_region(mesh, "Arm", whole=True)
    region.button_count = 6
    for b, name in zip(region.buttons, ("FK Bend", "IK / FK", "IK Move", "Elbow", "Elbow X", "Elbow Z")):
        b.name = name
    fk, toggle, ik, elbow, ex, ez = region.buttons[:6]
    fk.up.enabled, fk.up.kind, fk.up.axis, fk.up.target, fk.up.bone = True, "ROTATE", "X", rig, "Lower"
    toggle.action = "TOGGLE"
    toggle.switch.enabled = True
    toggle.switch.kind, toggle.switch.target, toggle.switch.data_path = "PROPERTY", rig, '["ik"]'
    fk.show_when, fk.when_toggle = "OFF", "IK / FK"
    ik.up.enabled, ik.up.kind, ik.up.target, ik.up.bone = True, "MOVE", rig, "Upper"
    ik.show_when, ik.when_toggle = "ON", "IK / FK"
    elbow.opens_menu = True
    ex.menu_parent = ez.menu_parent = menus.ensure_uid(region, elbow)
    return rig, mesh, region


def _names(region, indices):
    return [region.buttons[i].name for i in indices]


def test_show_when_plays():
    """A button can show only while a toggle of its region is on, or off, or
    while a property reads on. A drag on the region runs the first drag
    button showing."""
    core = rigs.kneady()
    rig, mesh, region = _arm_region()
    shown = lambda: _names(region, core.shown_buttons(region, mesh))  # noqa: E731
    assert shown() == ["FK Bend", "IK / FK", "Elbow"], shown()
    assert core.first_drag_button(region, mesh, shown=True) == 0
    rig["ik"] = 1.0
    assert shown() == ["IK / FK", "IK Move", "Elbow"], shown()
    assert core.first_drag_button(region, mesh, shown=True) == 2
    # by a property's path instead of a toggle
    fk = region.buttons[0]
    fk.when_toggle, fk.when_target, fk.when_path = "", rig, '["ik"]'
    fk.show_when = "ON"
    assert "FK Bend" in shown()
    rig["ik"] = 0.0
    assert "FK Bend" not in shown()
    # a switch that cannot be read lets it show
    fk.when_path = '["no_such"]'
    assert "FK Bend" in shown()


def test_menus_play():
    """Menus:
    - a click on a button that opens a menu shows the menu's buttons alone,
      and a second click closes it;
    - Shift+click opens it pinned, its button strongly marked;
    - Esc closes the whole menu and the pin;
    - a menu's buttons are never shown at the top level;
    - removing a menu's button removes its buttons too."""
    core = rigs.kneady()
    menus = _module("menus")
    rig, mesh, region = _arm_region()
    elbow = region.buttons[3]
    elbow.placed = True                     # opens at its point, which needs no view
    key = (mesh.name, region.id)
    shown = lambda: _names(region, core.shown_buttons(region, mesh))  # noqa: E731
    assert "Elbow X" not in shown()
    assert core.badged(region, elbow) == 1 and not core.badged(region, region.buttons[0])
    try:
        assert core.clicked(bpy.context, mesh, region, 3), "the click on Elbow was not taken"
        assert shown() == ["Elbow", "Elbow X", "Elbow Z"], shown()
        assert core.clicked(bpy.context, mesh, region, 3)
        assert menus.opened(mesh, region) is None and "Elbow X" not in shown()
        # pinned
        assert core.clicked(bpy.context, mesh, region, 3, shift=True)
        assert menus.opened(mesh, region) is not None and core.kept() == key
        assert core.badged(region, elbow) == 2, "the pinned menu's button is not strongly marked"
        core.STATE["hover"] = key
        assert bpy.ops.kneady.close_menu() == {"FINISHED"}
        assert menus.opened(mesh, region) is None and core.kept() is None, "Esc left the menu or the pin"
        # a sub menu's buttons open no menu of their own (one sub menu at most)
        region.buttons[4].opens_menu = True
        region.button_count = 7
        region.buttons[6].name, region.buttons[6].menu_parent = "Deeper", menus.ensure_uid(region, region.buttons[4])
        region.buttons[6].opens_menu = True
        assert not menus.can_open(region, 6) and not core.badged(region, region.buttons[6])
        # Elbow removed: its menu goes with it, and Elbow X's sub menu too.
        # (They used to move up a level instead.)
        region.button_index = 3
        count = region.button_count
        assert core.remove_button(region, "all") == ""
        assert region.button_count == count - 4, _names(region, range(region.button_count))
        assert not {"Elbow", "Elbow X", "Elbow Z", "Deeper"} & set(_names(region, range(region.button_count)))
    finally:
        menus.OPEN.clear()
        core.let_go()
        core.STATE["hover"] = None


def test_shift_click_pins_any_region():
    """Shift+click on a button that opens no menu pins its region, and
    Shift+click on any of its buttons again lets it go. Greg found regions
    without menus could not be pinned: "I can't pin the Cap regions. I think
    it's because there's no sub menus". Also:
    - the region's pin outlasts a menu opened and closed in it, while a
      menu's own pin goes with the menu;
    - Esc lets it go;
    - a Run Operator button pins rather than runs."""
    core = rigs.kneady()
    menus = _module("menus")
    rig, mesh, region = _arm_region()
    region.buttons[3].placed = True          # Elbow's menu opens at its point, which needs no view
    key = (mesh.name, region.id)
    try:
        assert core.clicked(bpy.context, mesh, region, 0, shift=True), "Shift+click on FK Bend was not taken"
        assert core.kept() == key and core.kept_by() == "region", (core.kept(), core.kept_by())
        assert "pinned" in (core.idle_status() or ""), core.idle_status()
        # Shift+click on another of its buttons lets go
        assert core.clicked(bpy.context, mesh, region, 2, shift=True)
        assert core.kept() is None, "still pinned"
        # a menu opened and closed in a pinned region leaves it pinned
        core.clicked(bpy.context, mesh, region, 0, shift=True)
        assert core.clicked(bpy.context, mesh, region, 3) and menus.opened(mesh, region) is not None
        assert core.clicked(bpy.context, mesh, region, 3) and menus.opened(mesh, region) is None
        assert core.kept() == key, "closing a menu let go of the region's own pin"
        # Shift+click on a menu's button in it: the menu opens, the region's pin stays the region's
        assert core.clicked(bpy.context, mesh, region, 3, shift=True) and menus.opened(mesh, region) is not None
        assert core.kept_by() == "region", core.kept_by()
        menus.close(mesh, region, all_levels=True)
        assert core.kept() == key
        # Esc lets go, with no menu open
        assert bpy.ops.kneady.close_menu.poll(), "Esc does nothing for a pinned region"
        assert bpy.ops.kneady.close_menu() == {"FINISHED"} and core.kept() is None
        # a menu's own pin still goes with its menu
        assert core.clicked(bpy.context, mesh, region, 3, shift=True) and core.kept_by() == "menu"
        menus.close(mesh, region, all_levels=True)
        assert core.kept() is None, "a menu's pin outlived its menu"
        # Run Operator: Shift+click pins, it does not run
        fk = region.buttons[0]
        fk.run_operator = "object.select_all"
        fk.run_operator_args = "{'action': 'SELECT'}"
        for o in bpy.context.selected_objects:
            o.select_set(False)
        assert core.clicked(bpy.context, mesh, region, 0, shift=True) and core.kept() == key
        assert not mesh.select_get(), "the operator ran on Shift+click"
    finally:
        menus.OPEN.clear()
        core.let_go()
        core.STATE["hover"] = None


def test_placed_buttons_play():
    """A placed button sits at its point in the region's box, riding the bone
    the region's first button turns, and it leaves the row. Behind defaults
    to Hide Behind. A nearer button drawn over another fades the other."""
    core = rigs.kneady()
    placed = _module("placed")
    rig, mesh, region = _arm_region()
    assert region.behind == "HIDE"
    elbow = region.buttons[3]
    elbow.placed, elbow.place, elbow.place_normal, elbow.place_set = True, (0.0, 0.0, 1.0), (0.0, -1.0, 0.0), True
    owned = placed.layout(bpy.context, mesh, region)[0]
    assert list(owned) == [3], owned
    depsgraph = bpy.context.evaluated_depsgraph_get()
    _rig, pb = placed.region_bone(region)
    assert pb is not None and pb.name == "Lower", "the frame is not the first button's bone"
    lower = rig.pose.bones["Lower"]
    before, normal = placed.button_point(mesh, region, elbow, depsgraph)
    assert normal is not None
    local_before = (rig.matrix_world @ lower.matrix).inverted() @ before
    # Turn the whole arm at the shoulder. The region covers both bones, so it
    # turns rigidly, and the button goes with Lower, at the same place in its frame
    upper = rig.pose.bones["Upper"]
    upper.rotation_mode = "XYZ"
    upper.rotation_euler = (0.6, 0.0, 0.0)
    bpy.context.view_layer.update()
    core.forget()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    after, _normal = placed.button_point(mesh, region, elbow, depsgraph)
    assert (after - before).length > 1e-3, "the button stayed put as its bone turned"
    local_after = (rig.matrix_world @ lower.matrix).inverted() @ after
    # Within the small lift that keeps the paint off the surface
    # (core.region_geometry: 0.3% of the mesh's bounds, which grow as it turns)
    assert (local_after - local_before).length < 3e-3, (local_after, local_before)
    r = 14.0
    circle = (r, r, r)
    out = placed.covered([(0, Vector((0.0, 0.0))), (1, Vector((20.0, 0.0)))], [], {0: circle, 1: circle})
    assert out == {0}, out


def test_placed_buttons_ride_the_surface():
    """A region's first button may drive a control: a bone that deforms none
    of the region's faces, like Rigify's FK forearm while the arm is in IK. A
    button placed on that region rides the deform bone that weights the
    region most, so it stays on the surface as that bone moves and the
    control stays still. A region whose button drives a bone that deforms it
    rides that bone."""
    core = rigs.kneady()
    placed = _module("placed")
    rig, mesh = rigs.arm_rig()
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    ctrl = rig.data.edit_bones.new("Lower_ctrl")
    ctrl.head, ctrl.tail = (0.5, 0.0, 1.0), (0.5, 0.0, 2.0)
    ctrl.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    region = core.new_region(mesh, "Forearm")
    lower = [p.index for p in mesh.data.polygons if p.center.z > 1.05]
    core.tag_faces(mesh.data, lower, region.id)
    region.button_count = 1
    bend = region.buttons[0]
    bend.up.enabled, bend.up.kind, bend.up.axis, bend.up.target, bend.up.bone = True, "ROTATE", "X", rig, "Lower_ctrl"
    _rig, pb = placed.riding_bone(mesh, region)
    assert pb is not None and pb.name == "Lower", "rides %s, not the deform bone" % (pb and pb.name)
    assert placed.region_bone(region)[1].name == "Lower_ctrl", "the region's own bone changed"
    bend.placed, bend.place, bend.place_normal, bend.place_set = True, (1.0, 0.0, 0.0), (1.0, 0.0, 0.0), True
    depsgraph = bpy.context.evaluated_depsgraph_get()
    before, _n = placed.button_point(mesh, region, bend, depsgraph)
    deform = rig.pose.bones["Lower"]
    local_before = (rig.matrix_world @ deform.matrix).inverted() @ before
    deform.rotation_mode = "XYZ"
    deform.rotation_euler = (0.8, 0.0, 0.0)            # the forearm bends, its control left where it was
    bpy.context.view_layer.update()
    core.forget()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    after, _n = placed.button_point(mesh, region, bend, depsgraph)
    assert (after - before).length > 0.1, "the button stayed put as the forearm bent"
    local_after = (rig.matrix_world @ deform.matrix).inverted() @ after
    assert (local_after - local_before).length < 3e-3, (local_after, local_before)
    # a button driving the deform bone itself: that bone, as ever
    bend.up.bone = "Lower"
    assert placed.riding_bone(mesh, region)[1].name == "Lower"
    # a mesh not skinned to the control's rig: the control's bone, as ever
    bend.up.bone = "Lower_ctrl"
    mesh.modifiers["Armature"].object = None
    placed.forget()
    assert placed.riding_bone(mesh, region)[1].name == "Lower_ctrl"


def test_keep_pose_plays():
    """A toggle with Keep Pose: as it switches, each bone takes its partner's
    pose."""
    core = rigs.kneady()
    rig, mesh, region = _arm_region()
    toggle = region.buttons[1]
    upper, lower = rig.pose.bones["Upper"], rig.pose.bones["Lower"]
    upper.rotation_mode = lower.rotation_mode = "XYZ"
    upper.rotation_euler = (0.4, 0.2, -0.3)
    bpy.context.view_layer.update()
    toggle.snap_on = repr([("Lower", "Upper")])
    channels = core.switch_channels(toggle, mesh, region)
    assert core.switch_button(bpy.context, toggle, mesh, region, channels, True)
    bpy.context.view_layer.update()
    assert rig["ik"] == 1.0, "not switched"
    turn = lower.matrix.to_quaternion().rotation_difference(upper.matrix.to_quaternion()).angle
    assert turn < 1e-4, "Lower did not take Upper's pose: %.5f" % turn


def test_run_operator_plays():
    """A click runs a button's operator with its arguments. An operator that
    works on files, scripts or Blender's settings is never run from a
    button."""
    core = rigs.kneady()
    switching = _module("switching")
    for unsafe in ("wm.quit_blender", "script.python_file_run", "wm.open_mainfile", "import_scene.fbx",
                   "export_scene.gltf", "preferences.addon_install", "console.execute", "text.run_script"):
        assert switching.operator_problem(unsafe), "%s would run from a button" % unsafe
    assert not switching.operator_problem("pose.select_all")

    class KNEADY_TEST_OT_mark(bpy.types.Operator):
        bl_idname = "kneady_test.mark"
        bl_label = "Mark"
        value: bpy.props.IntProperty()

        def execute(self, context):
            context.active_object["marked"] = self.value
            return {"FINISHED"}

    bpy.utils.register_class(KNEADY_TEST_OT_mark)
    try:
        rig, mesh, region = _arm_region()
        fk = region.buttons[0]
        fk.run_operator, fk.run_operator_args = "kneady_test.mark", "{'value': 7}"
        assert core.clicked(bpy.context, mesh, region, 0), "the click was not taken"
        assert rig.get("marked") == 7 or mesh.get("marked") == 7, "the operator did not run"
        fk.run_operator = "wm.quit_blender"
        ran, why = switching.run_operator(bpy.context, fk, mesh)
        assert not ran and why, "an unsafe operator ran"
    finally:
        bpy.utils.unregister_class(KNEADY_TEST_OT_mark)


def test_layout_settings_copy_and_paste():
    """The settings travel with a copied button, but a button pasted over
    keeps its own place among the others: the menu it is in, and its own id.
    It never takes its source's id, so its menu's buttons find it alone."""
    core = rigs.kneady()
    rig, mesh, region = _arm_region()
    elbow, ex = region.buttons[3], region.buttons[4]
    data = core.to_data(elbow)
    assert data["opens_menu"] is True and "menu_open" not in data, sorted(data)
    parent = ex.menu_parent
    core.from_data(ex, data, skip=core.BUTTON_OWN)
    assert ex.opens_menu and ex.menu_parent == parent, (ex.opens_menu, ex.menu_parent, parent)
    assert ex.uid > 0 and ex.uid != elbow.uid, (ex.uid, elbow.uid)


def test_handle_points_from_its_command():
    """A placed button drawn as a 3D arrow points, by default, along what it
    drives (Greg agreed: "Good recommendation"):
    - for a Move, along its axis;
    - for a Rotate, the way it turns the arrow's place, with the lever its
      distance from the axis;
    - for a value, out from the surface.
    It can instead point along an axis of the frame it rides, or the
    surface, chosen by hand. Flip turns it round."""
    placed = _module("placed")
    rig, mesh, region = _arm_region()
    fk = region.buttons[0]                                 # Rotate X of Lower
    fk.placed, fk.handle = True, "HANDLE"
    assert placed.is_handle(fk)
    # a toggle is always a screen button (Greg: "Toggles can't be 3D Handles")
    fk.action = "TOGGLE"
    assert not placed.is_handle(fk), "a toggle shown as a 3D handle"
    fk.action = "DRAG"
    fk.placed = False
    assert not placed.is_handle(fk), "a button in the row shown as a 3D handle"
    fk.placed = True
    lower = rig.pose.bones["Lower"]
    m = rig.matrix_world @ lower.matrix
    point = m @ Vector((0.0, 0.5, 0.2))                    # beside the bone, half way up it
    normal = Vector((0.0, -1.0, 0.0))
    d, lever = placed.handle_direction(mesh, region, fk, point, normal)
    axis = m.to_3x3().normalized() @ Vector((1.0, 0.0, 0.0))
    expect = axis.cross(point - m.translation)
    assert (d - expect.normalized()).length < 1e-5, (d, expect)
    assert abs(lever - expect.length) < 1e-5, (lever, expect.length)
    # a Move along the bone's Y: along the bone, up the arm
    fk.up.kind, fk.up.axis = "MOVE", "Y"
    d, lever = placed.handle_direction(mesh, region, fk, point, normal)
    assert (d - (m.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()).length < 1e-5 and lever is None, d
    # a value: out from the surface
    fk.up.kind = "PROPERTY"
    d, _lever = placed.handle_direction(mesh, region, fk, point, normal)
    assert (d - normal).length < 1e-6, d
    # by hand: the frame's Z, flipped
    fk.handle_axis, fk.handle_flip = "Z", True
    d, _lever = placed.handle_direction(mesh, region, fk, point, normal)
    frame = placed.frame_of(mesh, region)
    assert (d + (frame.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()).length < 1e-5, d
    # a Left / Right command when Up / Down drives nothing
    fk.handle_axis, fk.handle_flip = "AUTO", False
    fk.up.enabled = False
    fk.across.enabled, fk.across.kind, fk.across.axis = True, "MOVE", "X"
    fk.across.target, fk.across.bone = rig, "Lower"
    assert placed.handle_drives(fk) == 0
    d, _lever = placed.handle_direction(mesh, region, fk, point, normal)
    assert (d - (m.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()).length < 1e-5, d


def test_handle_hit_and_end_on():
    """An arrow is hit along its shaft and head. Pointing at the viewer
    (below END_ON), it takes no drag - Greg: "it should just not be
    responsive" - and is drawn dimmed, never hidden - Greg: "They should
    become unable to haul but not disappear"."""
    core = rigs.kneady()
    placed = _module("placed")
    h = dict(base=Vector((100.0, 100.0)), tip=Vector((100.0, 160.0)), reach=8.0, live=True, ratio=1.0,
             head=[Vector((92.0, 145.0)), Vector((108.0, 145.0)), Vector((100.0, 160.0))])
    assert core.handle_hit(h, Vector((105.0, 130.0)))                  # on the shaft
    assert not core.handle_hit(h, Vector((120.0, 130.0)))              # beside it
    assert core.handle_hit(h, Vector((100.0, 166.0)), slack=7.0)       # just past the tip, in the band
    assert not core.handle_hit(h, Vector((100.0, 175.0)))
    assert abs(core.segment_distance(Vector((0.0, 5.0)), Vector((0.0, 0.0)), Vector((10.0, 0.0))) - 5.0) < 1e-9
    end_on = dict(h, ratio=0.2, live=0.2 >= placed.END_ON)
    assert not core.handle_hit(end_on, Vector((100.0, 120.0))), "an arrow end on took the drag"
    assert 0.0 < placed.handle_alpha(end_on) < placed.handle_alpha(h) == 1.0
    assert placed.handle_alpha(dict(h, ratio=0.0, live=False)) == placed.DIMMED > 0.0, "an arrow end on vanished"


def test_handle_drag_follows():
    """Along an arrow, a Move or Rotate goes by the world distance the mouse
    covers, so it follows the mouse. Each pixel moves a pixel's worth along
    the arrow, and a Rotate turns by that distance over its lever. A value
    keeps its Speed. A typed value is worked back to pixels the same way."""
    core = rigs.kneady()
    rig, mesh, region = _arm_region()
    fk = region.buttons[0]
    fk.up.kind, fk.up.axis = "MOVE", "Y"
    ch = core.Channel(fk.up, mesh, region)
    assert ch.ok, ch.why
    ch.handle_per_pixel = 0.01                             # a pixel along the arrow is 1 cm
    assert abs(core.amount_for(ch, 50.0, 1.0) - 0.5) < 1e-9
    assert abs(core.pixels_for(ch, 0.5, 1.0) - 50.0) < 1e-6
    fk.up.kind, fk.up.axis = "ROTATE", "X"
    ch = core.Channel(fk.up, mesh, region)
    ch.handle_per_pixel = 0.01 / 0.5                       # the same over a 50 cm lever: radians
    assert abs(core.amount_for(ch, 50.0, -1.0) + 1.0) < 1e-9
    fk.up.kind, fk.up.data_path = "PROPERTY", '["ik"]'
    ch = core.Channel(fk.up, mesh, region)
    ch.handle_per_pixel = 0.01                             # a value is not a Move or Rotate: its Speed
    assert abs(core.amount_for(ch, 100.0, 1.0) - fk.up.rate) < 1e-9


def test_ring_lies_about_its_rotate():
    """A ring handle lies around the axis its Rotate turns on (Flip turns it
    round), and for anything else around the way an arrow would point. It is
    hit on its rim, never across its middle, which stays the item's."""
    core = rigs.kneady()
    placed = _module("placed")
    rig, mesh, region = _arm_region()
    fk = region.buttons[0]                                 # Rotate X of Lower
    fk.placed, fk.handle, fk.handle_shape = True, "HANDLE", "RING"
    lower = rig.pose.bones["Lower"]
    m = rig.matrix_world @ lower.matrix
    point, normal = m @ Vector((0.0, 0.5, 0.2)), Vector((0.0, -1.0, 0.0))
    axis = placed.ring_axis(mesh, region, fk, point, normal)
    want = (m.to_3x3().normalized() @ Vector((1.0, 0.0, 0.0))).normalized()
    assert (axis - want).length < 1e-5, (axis, want)
    fk.handle_flip = True
    assert (placed.ring_axis(mesh, region, fk, point, normal) + want).length < 1e-5
    fk.handle_flip = False
    fk.up.kind = "PROPERTY"                                # a value: about the surface's normal
    assert (placed.ring_axis(mesh, region, fk, point, normal) - normal).length < 1e-6
    rim = [Vector((100.0 + 30.0 * math.cos(t), 100.0 + 30.0 * math.sin(t)))
           for t in (2.0 * math.pi * k / 48.0 for k in range(49))]
    ring = dict(base=Vector((100.0, 100.0)), tip=rim[0], rim=rim, reach=4.0, live=True)
    assert core.handle_hit(ring, Vector((130.0, 100.0))), "the rim missed"
    assert core.handle_hit(ring, Vector((100.0, 128.0)))
    assert not core.handle_hit(ring, Vector((100.0, 100.0))), "its middle took the press"
    assert not core.handle_hit(ring, Vector((145.0, 100.0)))


def test_quad_arrow_arms_point_their_own_ways():
    """A Quad Arrow:
    - the Up / Down arm points along its command's way, and the Left / Right
      arm along its own;
    - an arm whose command has no way lies flat on the surface, square to
      the other arm, with Left / Right to the right of Up / Down as seen from
      outside;
    - when neither command has a way, Up / Down runs up the frame.
    Flip turns Up / Down round."""
    placed = _module("placed")
    rig, mesh, region = _arm_region()
    b = region.buttons[0]
    b.placed, b.handle, b.handle_shape = True, "HANDLE", "CROSS"
    b.up.kind, b.up.axis = "MOVE", "Y"                      # along Lower, up the arm
    b.across.enabled, b.across.kind, b.across.axis = True, "MOVE", "X"
    b.across.target, b.across.bone = rig, "Lower"
    m = (rig.matrix_world @ rig.pose.bones["Lower"].matrix).to_3x3()
    point, normal = Vector((0.0, -0.2, 1.5)), Vector((0.0, -1.0, 0.0))
    arms = placed.cross_directions(mesh, region, b, point, normal)
    assert (arms[1][0] - (m @ Vector((0.0, 1.0, 0.0))).normalized()).length < 1e-5, arms[1]
    assert (arms[0][0] - (m @ Vector((1.0, 0.0, 0.0))).normalized()).length < 1e-5, arms[0]
    # Left / Right a value: flat on the surface, square to Up / Down, to its right
    b.across.kind = "PROPERTY"
    arms = placed.cross_directions(mesh, region, b, point, normal)
    up, right = arms[1][0], arms[0][0]
    assert abs(up.dot(right)) < 1e-6 and abs(right.dot(normal)) < 1e-6, (up, right)
    assert right.x > 0.99, "Left / Right not to the right seen from the front: %s" % (right,)
    # both values: Up / Down up the frame, flat on the surface
    b.up.kind = "PROPERTY"
    arms = placed.cross_directions(mesh, region, b, point, normal)
    up, right = arms[1][0], arms[0][0]
    assert abs(up.dot(normal)) < 1e-6 and abs(right.dot(normal)) < 1e-6 and abs(up.dot(right)) < 1e-6
    b.handle_flip = True
    assert (placed.cross_directions(mesh, region, b, point, normal)[1][0] + up).length < 1e-6
