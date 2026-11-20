"""Bugs found by a review of the code before release, each written as the
behavior it should have. Every one failed before its fix: stale shapes after
a frame change or a rename, region settings that did not refresh, a hover
that ignored the view, a missing node group, a player timer that died - and,
from the comment pass, attached tutorials missing from a checkout's list,
Run Operator blaming the rig, a renamed input logged as an error, and a
modeled handle head with no grab margin. One more guards a tooltip a
reviewer thought raised; it never did, but the line is easy to misread.
(Local View and a tutorial in a second window need a window:
tests/probe_local_view.py, tests/probe_tutorial_window.py.)"""

import math
import tempfile
import types

import bpy  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Matrix, Vector  # type: ignore

import rigs

DOWN, UP = Vector((0.0, 0.0, -1.0)), Vector((0.0, 0.0, 1.0))


def test_risk_frame_change_refreshes_geometry():
    """1. Playing or scrubbing to another frame: a region's shape as Kneady
    knows it (its paint, where its row of buttons sits, Show Through's hit
    test) has to be the new frame's. The caches are cleared by depsgraph
    updates only, and a frame change does not send one for the mesh."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    region.whole = False
    core.tag_faces(mesh.data, [p.index for p in mesh.data.polygons if p.center.z > 1.0], region.id)
    bone = rig.pose.bones["Lower"]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = (0.0, 0.0, 0.0)
    bone.keyframe_insert("rotation_euler", frame=1)
    bone.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    bone.keyframe_insert("rotation_euler", frame=10)
    scene = bpy.context.scene
    scene.frame_set(1)
    scene.kneady_on = True
    bpy.context.view_layer.update()
    core.region_geometry(mesh, bpy.context.evaluated_depsgraph_get())
    scene.frame_set(10)
    known = core.region_geometry(mesh, bpy.context.evaluated_depsgraph_get())[region.id][2].z
    core.forget()
    shown = core.region_geometry(mesh, bpy.context.evaluated_depsgraph_get())[region.id][2].z
    assert abs(known - shown) < 1e-4, ("at frame 10 the region's top is known at z %.3f, shown at %.3f: "
                                       "the frame before's shape" % (known, shown))


def _sphere(core, name, x, top):
    bpy.ops.mesh.primitive_uv_sphere_add(location=(x, 0.0, 0.0))
    obj = bpy.context.active_object
    obj.name = name
    region = core.new_region(obj, name)
    region.whole = False
    core.tag_faces(obj.data, [p.index for p in obj.data.polygons if (p.center.z > 0.0) == top], region.id)
    return obj, region


def test_risk_delete_then_rename_into_the_name():
    """2. A mesh replaced the usual way: delete Body, then rename Body.001 to
    Body. What Kneady has cached under "Body" must not be read for the
    renamed object, and a rename sends no geometry update."""
    core = rigs.kneady()
    body, _r = _sphere(core, "Body", 0.0, True)           # its top tagged
    other, mine = _sphere(core, "Other", 3.0, False)      # its bottom tagged
    bpy.context.scene.kneady_on = True
    bpy.context.view_layer.update()
    core.cast(bpy.context, Vector((0.0, 0.0, 5.0)), DOWN)  # Body's tags cached
    bpy.data.objects.remove(body)
    other.name = "Body"
    bpy.context.view_layer.update()
    found = core.cast(bpy.context, Vector((3.0, 0.0, -5.0)), UP)
    assert found is not None and found[1] == mine.id, "its tagged bottom reads as %s, not region %d" % (
        found and found[1], mine.id)


def test_risk_from_attribute_takes_at_once():
    """3a. A region's From Attribute typed in the panel: its faces hover at
    once. No update tells the caches."""
    core = rigs.kneady()
    bpy.ops.mesh.primitive_uv_sphere_add()
    obj = bpy.context.active_object
    region = core.new_region(obj, "R")
    region.whole = False
    mark = obj.data.attributes.new("mark", "BOOLEAN", "FACE")
    mark.data.foreach_set("value", [p.center.z > 0.0 for p in obj.data.polygons])
    bpy.context.scene.kneady_on = True
    bpy.context.view_layer.update()
    core.cast(bpy.context, Vector((0.0, 0.0, 5.0)), DOWN)
    region.attribute = "mark"
    region.value = 1
    bpy.context.view_layer.update()
    found = core.cast(bpy.context, Vector((0.0, 0.0, 5.0)), DOWN)
    assert found is not None and found[1] == region.id, "the marked top reads as %s" % (found and found[1],)


def test_risk_whole_object_repaints_at_once():
    """3b. Whole Object switched on: the region's paint covers every face at
    once, as its hover already does."""
    core = rigs.kneady()
    bpy.ops.mesh.primitive_uv_sphere_add()
    obj = bpy.context.active_object
    region = core.new_region(obj, "Top")
    region.whole = False
    core.tag_faces(obj.data, [p.index for p in obj.data.polygons if p.center.z > 0.0], region.id)
    bpy.context.scene.kneady_on = True
    bpy.context.view_layer.update()
    before = len(core.region_geometry(obj, bpy.context.evaluated_depsgraph_get())[region.id][0])
    region.whole = True
    bpy.context.view_layer.update()
    known = len(core.region_geometry(obj, bpy.context.evaluated_depsgraph_get())[region.id][0])
    core.forget()
    shown = len(core.region_geometry(obj, bpy.context.evaluated_depsgraph_get())[region.id][0])
    assert known == shown, "painted %d points, %d once refreshed (%d before Whole)" % (known, shown, before)


class _Region:
    """A 200 x 200 pixel stand-in for a 3D view's region."""
    width = height = 200

    def as_pointer(self):
        return 1234


def _looking_down_at(x):
    rv = types.SimpleNamespace()
    view = Matrix.Translation((-x, 0.0, -10.0))
    rv.view_matrix = view
    rv.is_perspective = False
    rv.perspective_matrix = Matrix.Diagonal((0.2, 0.2, -0.01, 1.0)) @ view
    rv.view_perspective = "ORTHO"
    return rv


def test_risk_hover_follows_the_view():
    """4. The view moves (zoom, numpad, View Selected, a 3D mouse) while the
    mouse stays still: what is under the mouse is worked out again. The
    cached hit is keyed by mouse position and region only."""
    core = rigs.kneady()
    for name, x in (("Left", -3.0), ("Right", 3.0)):
        bpy.ops.mesh.primitive_cube_add(location=(x, 0.0, 0.0))
        bpy.context.active_object.name = name
        core.new_region(bpy.context.active_object, name, whole=True)
    bpy.context.scene.kneady_on = True
    bpy.context.view_layer.update()
    region = _Region()
    context = types.SimpleNamespace(
        region=region, region_data=_looking_down_at(-3.0), scene=bpy.context.scene,
        window_manager=bpy.context.window_manager, view_layer=bpy.context.view_layer,
        evaluated_depsgraph_get=bpy.context.evaluated_depsgraph_get, mode="OBJECT",
        preferences=bpy.context.preferences, area=None, space_data=None, window=None, screen=None,
        workspace=None)
    assert view3d_utils.region_2d_to_origin_3d(region, context.region_data, (100, 100)).x < 0.0
    core.hit_at(context, (100, 100))
    core.changed()                                       # the redraw a view change brings
    context.region_data = _looking_down_at(3.0)
    core.hit_at(context, (100, 100))
    known = core.STATE["hover"]
    core._HIT["key"] = None
    core.hit_at(context, (100, 100))
    shown = core.STATE["hover"]
    assert known == shown, "after the view moved the hover is %s; under the mouse is %s" % (known, shown)


def test_risk_input_command_without_a_node_group():
    """6. A Modifier Input command naming a Geometry Nodes modifier whose node
    group was cleared. The drag says why it cannot run, the panel says what
    is wrong, and neither raises an error."""
    core, ui = rigs.kneady(), rigs.module("ui")
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.modifiers.new("GN", "NODES")
    region = core.new_region(obj, "R", whole=True)
    drag = region.buttons[0].up
    drag.kind, drag.modifier, drag.input = "INPUT", "GN", "Width"
    problems = []
    try:
        channel = core.Channel(drag, obj, region)
        if channel.ok or not channel.why:
            problems.append("the drag runs with no node group (why: %r)" % channel.why)
    except Exception as exc:
        problems.append("the drag raised %s: %s" % (type(exc).__name__, exc))
    try:
        said = ui._command_problem(bpy.context, drag, region)
        if not said:
            problems.append("the panel says nothing is wrong")
    except Exception as exc:
        problems.append("the panel raised %s: %s" % (type(exc).__name__, exc))
    assert not problems, "; ".join(problems)


def test_risk_tutorial_player_survives_a_bad_clip():
    """7a. A clip that fails to load in the tutorial player: the player's
    timer carries on (and tries again), as every other timer of Kneady's
    does. A timer function that raises is dropped by Blender."""
    overlay = rigs.module("overlay")
    saved = overlay.tutorials.active, overlay.tutorials.clip, overlay._wanted, overlay._image, overlay.load
    overlay.tutorials.active = lambda: True
    overlay.tutorials.clip = lambda: {"file": "broken.mp4"}
    overlay._wanted = lambda: ("broken.mp4", "a step")
    overlay._image = lambda: None

    def load(_path, _clip):
        raise RuntimeError("cannot read broken.mp4")

    overlay.load = load
    try:
        overlay.P["key"] = None
        try:
            again = overlay._play()
        except Exception as exc:
            raise AssertionError("the player's timer raised %s (%s), so Blender drops it" % (type(exc).__name__, exc))
        assert again is not None, "the player's timer stopped"
    finally:
        (overlay.tutorials.active, overlay.tutorials.clip, overlay._wanted, overlay._image,
         overlay.load) = saved


def test_review_switch_kind_tooltip_without_its_program():
    """A click command of a kind another add-on gives, in a file opened
    without that add-on: the Drives button's tooltip names the kind. (Its
    line, `a or b if spec is not None else c`, groups as `(a or b) if ...`,
    so it never raised; a review read it the other way, and the brackets
    added since say which.)"""
    ops = rigs.module("ops")
    properties = types.SimpleNamespace(program="an_add_on_not_loaded", kind="PROPERTY")
    said = ops.KNEADY_OT_switch_kind.description(bpy.context, properties)
    assert said == "an_add_on_not_loaded", said


def test_review_attached_tutorials_listed_in_a_checkout():
    """In a checkout of Kneady's repository the folder tutorials are made in
    is Kneady's own, so it is listed once, under Kneady, with no Yours of its
    own. In This File must still be listed, or a tutorial attached to the
    file can't be found."""
    t = rigs.module("tutorials")
    folder = tempfile.mkdtemp()
    entry = ("%sArm/attached" % t.FILE_PREFIX, folder, {"format": 1, "title": "Attached", "steps": []})
    saved = t.author_folder, t.attached
    t.author_folder = lambda: t.FOLDERS[0]
    t.attached = lambda: [entry]
    try:
        headings = [heading for heading, _entries in t.listed()]
        assert t.FILE_HEADING in headings and t.YOURS_HEADING not in headings, headings
        assert t.find(entry[0]) == (folder, entry[2]), "the attached tutorial can't be found"
    finally:
        t.author_folder, t.attached = saved


def test_review_run_operator_with_nothing_to_run_on():
    """Run Operator with no rig set and nothing hovered: it says so, rather
    than reporting the rig's operator as failed."""
    core, switching = rigs.kneady(), rigs.module("switching")
    mesh = bpy.data.objects.new("M", bpy.data.meshes.new("M"))
    bpy.context.scene.collection.objects.link(mesh)
    button = core.new_region(mesh, "R", whole=True).buttons[0]
    button.run_operator = "pose.select_all"
    ran, why = switching.run_operator(bpy.context, button, None)
    assert not ran and why.startswith("Nothing to run pose.select_all on"), why


def test_review_toggle_on_a_renamed_input_is_quiet():
    """A toggle switching a Geometry Nodes input that was renamed: it has no
    state, said in the panel, and nothing is logged as an error."""
    core, menus, errors = rigs.kneady(), rigs.module("menus"), rigs.module("errors")
    errors.forget()
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    group = bpy.data.node_groups.new("Inputs", "GeometryNodeTree")
    group.interface.new_socket("Amount", in_out="INPUT", socket_type="NodeSocketFloat")
    obj.modifiers.new("GN", "NODES").node_group = group
    switch = core.new_region(obj, "R", whole=True).buttons[0].switch
    switch.kind, switch.target, switch.modifier, switch.input = "INPUT", obj, "GN", "Renamed Since"
    assert menus._read_switch(switch, obj) is None
    assert errors.times("reading a toggle's state") == 0, "a renamed input was logged as an error"


def test_review_every_handle_head_has_a_grab_margin():
    """A 3D handle whose head is a modeled shape takes a press a few pixels
    past its outline, as an arrow's head does."""
    core = rigs.kneady()
    square = [Vector((10.0, 10.0)), Vector((20.0, 10.0)), Vector((20.0, 20.0)), Vector((10.0, 20.0))]
    handle = {"base": Vector((-100.0, -100.0)), "tip": Vector((-100.0, -100.0)), "reach": 0.0,
              "head": square, "head_reach": 4.0}
    assert core.handle_hit(handle, Vector((22.0, 15.0))), "2 px past the head's edge"
    assert not core.handle_hit(handle, Vector((30.0, 15.0))), "10 px past the head's edge"
