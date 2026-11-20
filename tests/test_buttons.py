"""Buttons: commands removed, toggles switched by a click, names under the
circles, and buttons copied and pasted between regions."""

import math

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

import rigs


def _region(mesh, name="R"):
    core = rigs.kneady()
    region = core.new_region(mesh, name, whole=True)
    return region


def _flag_modifier(mesh):
    """A Geometry Nodes modifier on `mesh` with a boolean input, Flag, and a
    float one, Amount."""
    ng = bpy.data.node_groups.new("Flags", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Flag", in_out="INPUT", socket_type="NodeSocketBool")
    ng.interface.new_socket("Amount", in_out="INPUT", socket_type="NodeSocketFloat")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n_in, n_out = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    ng.links.new(n_in.outputs[0], n_out.inputs[0])
    mod = mesh.modifiers.new("Flags", "NODES")
    mod.node_group = ng
    return mod


def _input(mod, name):
    item = next(i for i in mod.node_group.interface.items_tree
                if i.item_type == "SOCKET" and i.in_out == "INPUT" and i.name == name)
    return rigs.kneady().input_value(mod, item.identifier)


def test_remove_any_command():
    """Every command of a direction can be removed, the direction's own one
    too, and the next takes its place (Greg: "I can add command sections but
    I can't remove them")."""
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    up = region.buttons[0].up
    up.kind, up.data_path = "PROPERTY", '["a"]'
    with bpy.context.temp_override(kneady_drag=up):
        assert bpy.ops.kneady.command_add() == {"FINISHED"}
        assert bpy.ops.kneady.command_add() == {"FINISHED"}
    up.more[0].data_path, up.more[1].data_path = '["b"]', '["c"]'
    with bpy.context.temp_override(kneady_drag=up):
        assert bpy.ops.kneady.command_remove(index=0) == {"FINISHED"}
    paths = [up.data_path] + [c.data_path for c in up.more]
    assert paths == ['["b"]', '["c"]'], "after removing the first: %s" % paths
    with bpy.context.temp_override(kneady_drag=up):
        assert bpy.ops.kneady.command_remove(index=1) == {"FINISHED"}
    paths = [up.data_path] + [c.data_path for c in up.more]
    assert paths == ['["b"]'], "after removing the second: %s" % paths
    with bpy.context.temp_override(kneady_drag=up):
        # the last one left stays: the direction is switched off instead
        assert bpy.ops.kneady.command_remove(index=0) == {"CANCELLED"}


class _Layout:
    """A stand-in for a panel's layout that writes down what is drawn in it:
    ("prop", name), ("label", text, icon), ("op", idname). A section's header
    gets a log of its own, in `headers`; its body is drawn into this one, and
    only while it is open, as Blender's is."""

    def __init__(self, log=None, headers=None):
        self.log = [] if log is None else log
        self.headers = [] if headers is None else headers

    def _child(self, *_a, **_k):
        return _Layout(self.log, self.headers)

    row = column = box = split = _child

    def prop(self, _data, name, *_a, **_k):
        self.log.append(("prop", name))

    def prop_enum(self, _data, name, *_a, **_k):
        self.log.append(("prop", name))

    def prop_search(self, _data, name, *_a, **_k):
        self.log.append(("prop", name))

    def label(self, text="", icon="NONE", **_k):
        self.log.append(("label", text, icon))

    def operator(self, idname, **_k):
        self.log.append(("op", idname))
        return type("Op", (), {})()

    def context_pointer_set(self, *_a):
        pass

    def panel_prop(self, data, name):
        header = _Layout()
        self.headers.append((data, header.log))
        return header, (self if getattr(data, name) else None)


def test_commands_fold_to_what_they_drive():
    """Each command is a section that folds to what it drives, and starts
    folded (Greg: "When minimized it does show the input but everything else
    is tucked away. Default should be minimized"). A modifier input's field
    shows in the header, not again in the section; a turn shows in words. An
    added command opens. Removing the first carries the next one's open state
    up. A copy leaves out which sections are open."""
    core = rigs.kneady()
    ui = rigs.module("ui")
    rig, mesh = rigs.arm_rig()
    _flag_modifier(mesh)
    region = _region(mesh)
    bpy.context.view_layer.objects.active = mesh
    up = region.buttons[0].up
    up.enabled, up.kind, up.input = True, "INPUT", "Amount"
    turn = up.more.add()
    turn.kind, turn.axis, turn.target, turn.bone = "ROTATE", "Y", rig, "Lower"
    assert not up.command_open and not turn.command_open, "a command starts open"

    def drawn():
        layout = _Layout()
        ui._draw_commands(layout, bpy.context, up, region)
        return layout
    layout = drawn()
    assert [h[0] for h in layout.headers] == [up, turn], layout.headers
    first, second = layout.headers[0][1], layout.headers[1][1]
    assert ("prop", "input") in first and ("op", "kneady.command_remove") in first, first
    assert ("label", "Rotate Y on Lower", "CON_ROTLIKE") in second, second
    assert [e for e in layout.log if e[0] == "prop"] == [], "folded, a command shows %s" % layout.log
    up.command_open = True
    body = drawn().log
    assert ("prop", "modifier") in body and ("prop", "rate") in body, body
    assert ("prop", "input") not in body, "the Input field drawn twice"
    # one that cannot run says so while folded
    turn.target, turn.pick_target = None, True
    assert any(e[0] == "label" and e[2] == "ERROR" for e in drawn().headers[1][1]), "no mark on a broken command"
    turn.target = rig
    with bpy.context.temp_override(kneady_drag=up):
        assert bpy.ops.kneady.command_add() == {"FINISHED"}
    assert up.more[-1].command_open, "an added command is folded"
    assert "command_open" not in core.to_data(up) and "command_open" not in core.to_data(up)["more"][0]
    up.command_open, turn.command_open = False, True
    with bpy.context.temp_override(kneady_drag=up):
        assert bpy.ops.kneady.command_remove(index=0) == {"FINISHED"}
    assert up.kind == "ROTATE" and up.command_open, "the next did not move up as it was"


def _box(name, at):
    import bmesh  # type: ignore
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.5)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = at
    bpy.context.scene.collection.objects.link(obj)
    return obj


def test_a_command_drives_a_groups_object():
    """A command may drive a group a program gives (core.set_groups) in place
    of one Target. The program picks which of the group's objects the drag is
    on. For Digit's control groups that is the hovered digit (Greg: "A drag
    should only reach any of the digits in the control group and it should
    affect only the hovered digit"). The drag passes where it was pressed,
    kept for a redo, and the panel shows one of the group's inputs. Without
    the program, or with no group named, it says why."""
    core = rigs.kneady()
    props = rigs.module("props")
    ui = rigs.module("ui")
    _rig, mesh = rigs.arm_rig()
    a, b = _box("A", (5.0, 0.0, 0.0)), _box("B", (-5.0, 0.0, 0.0))
    for obj in (a, b):
        _flag_modifier(obj)
    bpy.context.view_layer.update()
    region = _region(mesh)
    up = region.buttons[0].up
    up.enabled, up.kind, up.input, up.rate = True, "INPUT", "Amount", 1.0
    region.buttons[0].across.enabled = False
    up.dragged = False
    assert not props.grouped(up)
    up.target_kind = "GROUP"
    assert props.grouped(up)
    assert core.Channel(up, mesh, region).why == "Pick its group"
    up.target_group = "Pair"
    assert not core.Channel(up, mesh, region).ok, "a group found with no program giving groups"

    def member(name, context, dragged, point):
        members = [a, b]
        if name != "Pair":
            return None, "No group %s" % name
        if dragged is None:
            return a, ""
        if dragged in members:
            return dragged, ""
        return min(members, key=lambda o: (o.matrix_world.translation - point).length), ""

    core.set_groups(lambda context: ["Pair"], member)
    try:
        assert core.term("group") == "Group" and core.group_names() == ["Pair"]
        assert core.Channel(up, mesh, region, Vector((4.0, 0.0, 0.0))).obj == a
        assert core.Channel(up, mesh, region, Vector((-4.0, 0.0, 0.0))).obj == b
        assert props.drag_object(up) == a and ui._command_problem(bpy.context, up, region) == "", \
            "the panel does not show one of the group's"
        bpy.context.view_layer.objects.active = mesh
        assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=50.0,
                                   point=(-4.0, 0.0, 0.0), point_set=True) == {"FINISHED"}
        assert _input(b.modifiers["Flags"], "Amount") > 0.1 and _input(a.modifiers["Flags"], "Amount") == 0.0, \
            "the drag did not drive B alone"
        moved = core.Channel(up, mesh, region, Vector((4.0, 0.0, 0.0)))
        assert moved.ok, moved.why
        other = region.buttons[0].up.more.add()
        props.copy_command(up, other)
        assert props.grouped(other) and other.target_group == "Pair", "a copy lost its group"
        other.kind, other.axis = "ROTATE", "X"
        assert ui.command_summary(other) == "Rotate X on Pair", ui.command_summary(other)
        data = core.to_data(up)
        assert data["target_kind"] == "GROUP" and data["target_group"] == "Pair"
        up.target_group = "Nothing"
        assert core.Channel(up, mesh, region, Vector((4.0, 0.0, 0.0))).why == "No group Nothing"
    finally:
        core.set_groups()
    assert not core.has_groups()


def test_toggle_switches_a_property():
    """A toggle's click switches a boolean property, a custom boolean, a 0-1
    number and a modifier's boolean input together. A redo switches it to the
    same value again. Invert switches the other way."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    mesh["ik_fk"] = 0.0
    mesh["flag"] = False
    mod = _flag_modifier(mesh)
    region = _region(mesh)
    region.button_count = 2
    toggle = region.buttons[1]
    toggle.name = "Switch"
    toggle.action = "TOGGLE"
    assert toggle.switch.kind == "PROPERTY" and toggle.switch.enabled, "a toggle starts on a property"
    toggle.switch.data_path = '["ik_fk"]'
    for kind, path, name in (("PROPERTY", '["flag"]', ""), ("PROPERTY", "show_wire", ""), ("INPUT", "", "Flag")):
        added = toggle.switch.more.add()
        added.kind, added.data_path, added.input = kind, path, name
    channels = core.switch_channels(toggle, mesh, region)
    assert all(ch.ok for ch in channels), [ch.why for ch in channels]
    assert core.switch_state(channels) is False
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=1) == {"FINISHED"}
    values = (mesh["ik_fk"], mesh["flag"], mesh.show_wire, bool(_input(mod, "Flag")))
    assert values == (1.0, True, True, True), "switched on: %s" % (values,)
    assert core.switch_state(core.switch_channels(toggle, mesh, region)) is True
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=1) == {"FINISHED"}
    values = (mesh["ik_fk"], mesh["flag"], mesh.show_wire, bool(_input(mod, "Flag")))
    assert values == (0.0, False, False, False), "switched off: %s" % (values,)
    # a redo: to what it was switched to, whatever it is now
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=1, switch_to=1) == {"FINISHED"}
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=1, switch_to=1) == {"FINISHED"}
    assert mesh["flag"] is True, "switch_to 1 twice left it off"
    toggle.switch.invert = True
    assert core.switch_state(core.switch_channels(toggle, mesh, region)) is False, "Invert: lit at 0"


def test_toggles_that_set_a_value():
    """A choice of several values (a CloudRig IK parent, Root 0 to Shoulder
    3) as toggles that each set a value of their own:

    - each is lit while the property holds its value
    - a click sets it, and an integer stays an integer
    - a click on the lit one changes nothing
    - Keep Pose keeps a bone where it is as the value changes
    """
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    mesh["parent"] = 0
    region = _region(mesh)
    region.button_count = 4
    buttons = list(region.buttons)[:4]
    for k, b in enumerate(buttons):
        b.name, b.action = ("Root", "Torso", "Chest", "Shoulder")[k], "TOGGLE"
        b.switch.data_path, b.switch.sets_value, b.switch.on_value = '["parent"]', True, float(k)

    def lit():
        return [bool(core.switch_state(core.switch_channels(b, mesh, region))) for b in buttons]
    assert lit() == [True, False, False, False], lit()
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=2) == {"FINISHED"}
    assert mesh["parent"] == 2 and isinstance(mesh["parent"], int), mesh["parent"]
    assert lit() == [False, False, True, False], lit()
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=2)
    assert mesh["parent"] == 2, "a click on the lit one changed it"
    assert not core.switch_click(bpy.context, region.buttons[2], mesh, region)
    # Keep Pose: the bone a parent switch would move stays put
    lower = rig.pose.bones["Lower"]
    lower.rotation_mode = "XYZ"
    lower.rotation_euler = (0.3, 0.1, 0.0)
    bpy.context.view_layer.update()
    before = lower.matrix.copy()
    region.buttons[3].snap_keep = repr(["Lower"])
    region.buttons[3].switch.target = rig
    rig["parent"] = 0
    assert core.switch_click(bpy.context, region.buttons[3], mesh, region)
    bpy.context.view_layer.update()
    assert rig["parent"] == 3, rig["parent"]
    assert (lower.matrix.translation - before.translation).length < 1e-5 and \
        lower.matrix.to_quaternion().rotation_difference(before.to_quaternion()).angle < 1e-4, "Lower moved"
    # a toggle of 0 and 1 is as it was
    buttons[0].switch.sets_value = False
    mesh["parent"] = 1
    assert lit()[0] is True, "an on / off toggle is lit from a half"
    mesh["parent"] = 0
    assert lit()[0] is False, "an on / off toggle is off under a half"


def test_keep_pose_past_a_constraint():
    """Keep Pose keeps a bone that its own constraint reparents. Rain's eye
    target, for one, follows Root, Pelvis or Head by its Armature
    constraint's weights. The bone stays where it was as the switch changes
    what the constraint does."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    bone = rig.pose.bones["Upper"]      # free to move, as an eye target is: no parent
    # a constraint that moves the bone after its pose, as a reparenting one
    # does: setting the bone's matrix alone leaves it out
    away = bpy.data.objects.new("Away", None)
    bpy.context.scene.collection.objects.link(away)
    away.location = (0.6, -0.4, 0.3)
    con = bone.constraints.new("COPY_LOCATION")
    con.target, con.use_offset, con.influence = away, True, 0.0
    bpy.context.view_layer.update()
    before = bone.matrix.copy()
    region = _region(mesh)
    toggle = region.buttons[0]
    toggle.action = "TOGGLE"
    toggle.switch.target = rig
    toggle.switch.data_path = 'pose.bones["Upper"].constraints["%s"].influence' % con.name
    toggle.snap_keep = repr(["Upper"])
    assert core.switch_click(bpy.context, toggle, mesh, region)
    bpy.context.view_layer.update()
    assert con.influence == 1.0, con.influence
    moved = (bone.matrix.translation - before.translation).length
    turned = bone.matrix.to_quaternion().rotation_difference(before.to_quaternion()).angle
    assert moved < 1e-4 and turned < 1e-4, "Upper jumped: %.5f m, %.5f rad" % (moved, turned)


def test_toggle_reasons():
    """A toggle with nothing it can switch says why and changes nothing."""
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    toggle = region.buttons[0]
    toggle.action = "TOGGLE"
    toggle.switch.data_path = '["missing"]'
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0) == {"CANCELLED"}


def test_region_press_runs_first_drag_button():
    """A drag on the region itself runs its first button that drags, past a
    toggle in front of it. With only toggles, it drives nothing."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 2
    first, second = region.buttons[0], region.buttons[1]
    first.action = "TOGGLE"
    first.switch.data_path = "show_wire"
    second.up.enabled = True
    second.up.kind, second.up.axis, second.up.target, second.up.bone = "ROTATE", "X", rig, "Lower"
    assert core.first_drag_button(region) == 1
    rigs.object_mode()
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, region_press=True, up=60.0)
    assert rigs.angle_of(rig.pose.bones["Lower"]) > 5.0, "the region's drag did not run the second button"
    assert not mesh.show_wire, "the region's drag switched the toggle"
    second.action = "TOGGLE"
    assert core.first_drag_button(region) is None
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, region_press=True,
                               up=60.0) == {"CANCELLED"}


def test_toggle_keys_with_auto_keying():
    """A toggle keys what it switched while Auto Keying is on."""
    _rig, mesh = rigs.arm_rig()
    mesh["flag"] = False
    region = _region(mesh)
    toggle = region.buttons[0]
    toggle.action = "TOGGLE"
    toggle.switch.data_path = '["flag"]'
    import test_auto_keying
    with test_auto_keying._Settings(auto=True):
        bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0)
    assert test_auto_keying._keys_on(mesh, '["flag"]'), "nothing keyed: %s" % test_auto_keying._curves(mesh)


def test_copy_and_paste_buttons():
    """A region's buttons pasted onto another region: that region takes the
    buttons, their number and arrangement, and keeps its own name, faces,
    color and id. One button can also be pasted over another, leaving that
    button's panel open or closed as it was."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    a = _region(mesh, "A")
    a.button_count, a.arrange = 3, "COLUMN"
    a.buttons[1].name = "Twist"
    a.buttons[1].across.enabled = True
    a.buttons[1].across.kind, a.buttons[1].across.target, a.buttons[1].across.bone = "ROTATE", rig, "Upper"
    a.buttons[2].action = "TOGGLE"
    a.buttons[2].switch.data_path = '["x"]'
    a.buttons[1].across.more.add().data_path = '["y"]'
    b = core.new_region(mesh, "B")
    b.color = (0.1, 0.2, 0.3)
    keep = (b.name, b.id, b.whole, tuple(b.color))
    with bpy.context.temp_override(kneady_region=a):
        assert bpy.ops.kneady.copy(scope="REGION") == {"FINISHED"}
    assert core.copied(bpy.context, "region") is not None, "nothing on the clipboard"
    assert core.copied(bpy.context, "button") is None, "a region read as a button"
    with bpy.context.temp_override(kneady_region=b):
        assert bpy.ops.kneady.paste(scope="REGION") == {"FINISHED"}
    assert (b.name, b.id, b.whole, tuple(b.color)) == keep, "the region's own settings changed"
    assert (b.button_count, b.arrange) == (3, "COLUMN"), (b.button_count, b.arrange)
    twist = b.buttons[1]
    assert twist.name == "Twist" and twist.across.target is rig and twist.across.bone == "Upper"
    assert [c.data_path for c in twist.across.more] == ['["y"]'], "added commands not pasted"
    assert b.buttons[2].action == "TOGGLE" and b.buttons[2].switch.data_path == '["x"]'
    # one button over another
    b.buttons[0].ui_open = False
    with bpy.context.temp_override(kneady_button=a.buttons[1]):
        assert bpy.ops.kneady.copy(scope="BUTTON") == {"FINISHED"}
    with bpy.context.temp_override(kneady_button=b.buttons[0]):
        assert bpy.ops.kneady.paste(scope="BUTTON") == {"FINISHED"}
    assert b.buttons[0].name == "Twist" and not b.buttons[0].ui_open
    # the copy is text: it pastes in another file, the target found by name
    text = core._CLIPBOARD["text"]
    bpy.ops.wm.read_homefile(use_empty=True)
    rig2, mesh2 = rigs.arm_rig()
    c = _region(mesh2, "C")
    core._CLIPBOARD["text"] = text
    with bpy.context.temp_override(kneady_button=c.buttons[0]):
        assert bpy.ops.kneady.paste(scope="BUTTON") == {"FINISHED"}
    assert c.buttons[0].across.target is rig2, "the target was not found by name in the other file"


def test_paste_refuses_newer_data():
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    found = {"kneady": "region", "data_version": core.DATA_VERSION + 1, "data": {"button_count": 4}}
    assert core.paste_region(region, found), "pasted data from a newer Kneady"
    assert region.button_count == 1


def test_label_spacing_and_bands():
    """With names always shown, the circles are spaced out and the band
    reaches under the names. Circles a program spreads over the item are
    each their own band."""
    core = rigs.kneady()
    centers = core.arranged([0, 1, 2], Vector((100.0, 100.0)), "COLUMN", 40.0, 60.0)
    ys = [c.y for _i, c in centers]
    assert abs((ys[0] - ys[1]) - 60.0) < 1e-6, ys
    row = [(0, Vector((0.0, 0.0))), (1, Vector((60.0, 0.0)))]
    assert core.in_block(row, Vector((30.0, 0.0)), 14.0), "the gap in a row is the band's"
    assert not core.in_block(row, Vector((30.0, 0.0)), 14.0, spread=True), "a spread layout's gap held it"
    assert core.in_block(row, Vector((0.0, -18.0)), 14.0, spread=True)
    assert not core.in_block(row, Vector((0.0, -40.0)), 14.0)
    assert core.in_block(row, Vector((0.0, -40.0)), 14.0, below=25.0), "the names' line not in the band"
    assert core.label_width("Twist") > 0.0


def test_buttons_start_closed():
    """A new region's buttons start with their panels closed (Greg: "It's
    overwhelming seeing multiple open"), and a paste leaves each panel as it
    was: open or closed is where the panel was left, not a setting."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    a, b = _region(mesh, "A"), _region(mesh, "B")
    assert not any(button.ui_open for button in a.buttons), "a new region's buttons start open"
    a.buttons[0].ui_open = True
    assert "ui_open" not in core.to_data(a.buttons[0]), "the panel's state is copied"
    with bpy.context.temp_override(kneady_region=a):
        bpy.ops.kneady.copy(scope="REGION")
    with bpy.context.temp_override(kneady_region=b):
        bpy.ops.kneady.paste(scope="REGION")
    assert not b.buttons[0].ui_open, "the paste opened the panel"


def test_text_buttons():
    """A text button is as wide as its name, never narrower than a circle, and
    shorter than one. It is hit inside its box, and a row spaces it by its
    width."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 3
    long_name, circle = region.buttons[0], region.buttons[1]
    long_name.icon_type, long_name.name = "TEXT", "A Long Button Name"
    radius = core.button_radius()
    w, h = core.half_size(long_name)
    assert w > 2.0 * radius and h < radius, "text box %.1f x %.1f against radius %.1f" % (w, h, radius)
    assert core.half_size(circle) == (radius, radius)
    center = Vector((100.0, 100.0))
    assert core.near_button(Vector((100.0 + w - 1.0, 100.0)), center, (w, h), radius)
    assert not core.near_button(Vector((100.0, 100.0 + h + 2.0)), center, (w, h), radius), \
        "hit above the text box"
    widths = [w, radius, radius]
    out = dict(core.arranged([0, 1, 2], center, "ROW", 34.0, None, widths, 6.0))
    assert abs((out[1].x - out[0].x) - (w + 6.0 + radius)) < 1e-4, "the row did not make room for the name"


def test_a_program_places_some_buttons():
    """A layout hook that places some buttons leaves the rest to Arrange,
    which arranges only them."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 3

    def hook(context, obj, reg):
        return [1], [(1, Vector((5.0, 5.0)))], set()

    core.add_layout(hook)
    try:
        calls = []
        real = core._arranged_layout
        core._arranged_layout = lambda context, obj, reg, leave=(): calls.append(set(leave)) or []
        placed, static, faded = core.layout_parts(bpy.context, mesh, region)
    finally:
        core._arranged_layout = real
        core.remove_layout(hook)
    assert placed == [(1, Vector((5.0, 5.0)))] and calls == [{1}], (placed, calls)


def _draw():
    core = rigs.kneady()
    import sys
    return sys.modules[core.__name__.rsplit(".", 1)[0] + ".draw"]


def test_arrow_sets():
    """A button's Arrows can be chosen (Greg: "there's no way to choose which
    set of arrows you want"). Every set draws, and From Drags follows the
    drags. Each graphic comes with closed loops round its edges, drawn
    smooth (Greg: "they are very aliased"), and the dark edge reaches past
    the body."""
    core = rigs.kneady()
    draw = _draw()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    button = region.buttons[0]
    sets = [item.identifier for item in button.bl_rna.properties["arrows"].enum_items]
    assert button.arrows == "AUTO" and len(sets) >= 10, sets
    counts = {}
    for choice in sets:
        button.arrows = choice
        (edge_tris, edge_loops), (body_tris, body_loops) = draw.arrows(button)
        assert body_tris and edge_tris and body_loops, "%s draws nothing" % choice
        for loop in edge_loops + body_loops:
            assert (loop[0] - loop[-1]).length < 1e-6 and len(loop) > 3, "%s: a loop that does not close" % choice
        extent = lambda tris: max(max(abs(p.x), abs(p.y)) for p in tris)  # noqa: E731
        assert extent(edge_tris) > extent(body_tris) and extent(edge_tris) <= 1.0 + 1e-6, \
            "%s: the edge %.2f against the body %.2f" % (choice, extent(edge_tris), extent(body_tris))
        assert extent(body_tris) <= 1.0 + 1e-6, "%s reaches past the graphic" % choice
        counts[choice] = len(draw.arrow_lines(choice, button))
    assert counts["BOTH"] == 2 and counts["ACROSS"] == 1 and counts["OUTWARD"] == 4 and counts["SPIN"] == 1, counts
    # From Drags: the first button drives both ways, a turn each - two curved
    button.arrows = "AUTO"
    lines = draw.arrow_lines("AUTO", button)
    assert len(lines) == 2 and all(abs(p[0][0]) > 0.1 or abs(p[0][1]) > 0.1 for p, _e in lines), lines
    button.across.enabled = False
    assert len(draw.arrow_lines("AUTO", button)) == 1
    # a toggle keeps its ring, whatever the set
    button.action = "TOGGLE"
    button.arrows = "SPIN"
    (_t, loops), _body = draw.arrows(button)
    assert len(loops) == 2, "a toggle's ring is two circles"
    assert "arrows" in core.to_data(button), "the choice is not copied"


def test_label_box_is_centered():
    """A name's box under its circle has as much room above the capitals as
    below them (Greg: "a little more space beneath the text than above").
    The line the names take is as tall as the box plus its gap."""
    import blf  # type: ignore
    core = rigs.kneady()
    blf.size(0, core.label_size())
    cap = blf.dimensions(0, "H")[1]
    center, radius = Vector((200.0, 300.0)), 14.0
    (x0, y0, x1, y1), (x, y) = core.label_box(center, 40.0, radius)
    above, below = y1 - (y + cap), y - y0
    assert abs(above - below) < 1e-6 and above > 0.0, "%.2f above the capitals, %.2f below" % (above, below)
    assert y1 < center.y - radius, "the box over the circle"
    assert x0 < x and x1 > x + 40.0 and abs((x0 + x1) * 0.5 - center.x) < 1e-6, "the box off the name"
    assert abs(core.label_height() - (y1 - y0 + core.LABEL_GAP * core.ui_scale())) < 1e-6, \
        "the line the names take is not the box and its gap"


def test_a_label_never_covers_a_button():
    """A name goes under its circle. With a button there, it goes beside it:
    on the right, else the left, else above (Greg: "Instead of omitting it
    just put it to the side of the button. I'd prefer to have the label"). A
    column's names go where label_places puts them. With buttons all round,
    as for a menu's opener in its ring, the name goes over the lower half of
    its own button, as Greg asked. A button off to the side moves nothing."""
    core = rigs.kneady()
    center, radius = Vector((200.0, 300.0)), 14.0
    step = 2.0 * radius + 12.0
    far = (center + Vector((3.0 * step, 3.0 * step)), radius, radius, True)
    below = (center - Vector((0.0, step)), radius, radius, True)
    above = (center + Vector((0.0, step)), radius, radius, True)
    right = (center + Vector((step, 0.0)), radius, radius, True)
    left = (center - Vector((step, 0.0)), radius, radius, True)
    plain = core.label_box(center, 60.0, radius)
    assert core.label_box(center, 60.0, radius, avoid=[far]) == plain, "a button well away moved it"
    for avoid, where in (([below, above], "right"), ([below], "right"), ([below, right], "left"),
                         ([below, right, left], "above")):
        (x0, y0, x1, y1), (x, y) = core.label_box(center, 60.0, radius, avoid=avoid)
        others = [o for o in avoid if core._covers((x0, y0, x1, y1), o)]
        assert not others, "%s: over a button" % where
        at = {"right": x0 >= center.x + radius and y0 < center.y < y1,
              "left": x1 <= center.x - radius and y0 < center.y < y1,
              "above": y0 >= center.y + radius}[where]
        assert at, "%s expected: box %s" % (where, (x0, y0, x1, y1))
        assert x0 < x and x1 > x + 60.0 and y0 < y < y1, "%s: the text out of its box" % where
    ring = [below, above, right, left]
    placed = core.label_box(center, 60.0, radius, avoid=ring)
    assert placed is not None, "a name left out in a ring"
    over = core.label_choices(center, 60.0, radius)[core.LABEL_PLACES.index("OVER")]
    touch = core.LABEL_TOUCH * core.ui_scale()
    assert placed[0][0] == over[0][0] and placed[0][2] == over[0][2], "a ring: not over its own button"
    assert abs(placed[0][1] - (below[0].y + radius + touch)) < 1e-6, \
        "a ring: not brought down to the button under it: %s" % (placed[0],)
    wide = (center - Vector((0.0, step)), 50.0, 8.0, False)
    box, _at = core.label_box(center, 60.0, radius, avoid=[wide])
    assert box[1] > center.y - radius, "a text button below did not count"


def test_a_column_names_go_together():
    """Buttons one under another: the top one's name goes above it, the
    bottom one's below, and those between to one side (Greg: "For vertical
    menu's the top button should have the label above, bottom button should
    have it below. Between buttons show on the side"). A row's names stay
    under it, Row + Column's middle ones go to the outside of each column,
    and a button beside the column sends them to the other side."""
    core = rigs.kneady()
    r, step = core.button_radius(), core.button_spacing()
    o = Vector((300.0, 300.0))

    def places(centers, named=None, width=50.0):
        buttons = [(k, c, r, r, r) for k, c in centers.items()]
        widths = {k: width for k in (named if named is not None else centers)}
        return core.label_places(buttons, widths, r)

    def side(box, c):
        x0, y0, x1, y1 = box
        if x0 >= c.x + r and y0 < c.y < y1:
            return "right"
        if x1 <= c.x - r and y0 < c.y < y1:
            return "left"
        return "below" if y1 <= c.y - r else "above" if y0 >= c.y + r else "over"

    def sides(centers, **kw):
        out = places(centers, **kw)
        for k, (box, _at) in out.items():
            covered = [j for j, c in centers.items() if j != k and core._covers(box, (c, r, r, r))]
            assert not covered, "%s's name over %s" % (k, covered)
        return {k: side(box, centers[k]) for k, (box, _at) in out.items()}

    column = {k: o - Vector((0.0, k * step)) for k in range(3)}
    assert sides(column) == {0: "above", 1: "right", 2: "below"}, sides(column)
    four = {k: o - Vector((0.0, k * step)) for k in range(4)}
    assert sides(four) == {0: "above", 1: "right", 2: "right", 3: "below"}, sides(four)
    row = {k: o + Vector((k * step, 0.0)) for k in range(3)}
    assert set(sides(row).values()) == {"below"}, sides(row)
    grid = {0: o, 1: o + Vector((step, 0.0)), 2: o - Vector((0.0, step)), 3: o + Vector((step, -step))}
    assert sides(grid) == {0: "above", 1: "above", 2: "below", 3: "below"}, sides(grid)
    tall = {0: o, 1: o + Vector((step, 0.0)), 2: o - Vector((0.0, step)), 3: o + Vector((step, -step)),
            4: o - Vector((0.0, 2.0 * step)), 5: o + Vector((step, -2.0 * step))}
    got = sides(tall)
    assert got == {0: "above", 1: "above", 2: "left", 3: "right", 4: "below", 5: "below"}, got
    # a text button at a column's top shows no name, but is its top
    assert sides(column, named=(1, 2)) == {1: "right", 2: "below"}, sides(column, named=(1, 2))
    # something to the right of the middle one: it goes on the left
    crowded = dict(column, side=column[1] + Vector((step, 0.0)))
    got = sides(crowded, named=(0, 1, 2))
    assert got == {0: "above", 1: "left", 2: "below"}, got
    # a lone button, and two far apart, as label_box puts them
    assert sides({0: o}) == {0: "below"}
    apart = {0: o, 1: o - Vector((0.0, 6.0 * step))}
    assert sides(apart) == {0: "below", 1: "below"}, sides(apart)


def test_a_menu_names_its_own_button():
    """An open menu's own button, surrounded by its ring, shows no name (Greg:
    "Let's not show the center button label"). The ring's names go away from
    the middle as before. A button with buttons all round that no menu places
    still has its name over its lower half."""
    import math
    core = rigs.kneady()
    r, step = core.button_radius(), core.button_spacing()
    o = Vector((400.0, 400.0))
    kids = [1, 2, 3, 4]
    at = {i: o + step * Vector((math.cos(a), math.sin(a)))
          for i, a in zip(kids, [math.pi / 2.0 - 2.0 * math.pi * k / 4 for k in range(4)])}
    width = core.label_width("A Menu")
    prefer = {0: (core.NO_NAME, True), 1: ("ABOVE", False), 2: ("RIGHT", False), 3: ("BELOW", False),
              4: ("LEFT", False)}
    buttons = [(0, o, r, r, r)] + [(i, c, r, r, r) for i, c in at.items()]
    places = core.label_places(buttons, {i: width for i in range(5)}, r, prefer=prefer)
    assert 0 not in places, "the menu's own button has a name: %s" % (places.get(0),)
    for i, (place, _fixed) in prefer.items():
        if i:
            n = core.LABEL_PLACES.index(place)
            assert places[i] == core.label_choices(at[i], width, r)[n], "%d's name not %s" % (i, place)
    # anywhere else a button has buttons all round, its name goes over its lower half
    alone = core.label_box(o, width, r, avoid=[(c, r, r, r) for c in at.values()])
    over = core.label_choices(o, width, r)[core.LABEL_PLACES.index("OVER")]
    assert abs(0.5 * (alone[0][0] + alone[0][2]) - o.x) < 1e-6 and alone[0][1] < over[0][1] + 1e-6, \
        "a button with buttons all round: its name not over its lower half"


def test_no_name_only_for_a_surrounded_menu_button():
    """The ring layout leaves out its button's name only where it is
    surrounded: three or more in its ring."""
    core = rigs.kneady()
    menus = rigs.module("menus")
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 5
    opener = region.buttons[0]
    opener.opens_menu, opener.uid = True, 3
    for b in region.buttons[1:4]:
        b.menu_parent = 3
    menus.OPEN[menus.key_of(mesh, region)] = [(3, ("middle", None))]
    real = core.region_center
    core.region_center = lambda *_a: Vector((300.0, 300.0))
    try:
        got = menus.ring_layout(bpy.context, mesh, region, menus.opened(mesh, region))
        labels = (got[3] if len(got) > 3 else {}).get("labels", {})
        assert labels.get(0) == (core.NO_NAME, True), labels
        region.buttons[3].menu_parent = 0                  # two in its ring
        got = menus.ring_layout(bpy.context, mesh, region, menus.opened(mesh, region))
        labels = (got[3] if len(got) > 3 else {}).get("labels", {})
        assert 0 not in labels, labels
    finally:
        core.region_center = real
        menus.OPEN.clear()


def test_list_colors():
    """A list of buttons has one color; a single button has none of its own
    (Greg: "Button groups should always have the same color for buttons so
    per button color overrides aren't necessary").

    - The region's own buttons take the region's color (Greg: "The default
      of adopting the color is fine") until Override Color gives them one.
      The override starts at the region's color and is kept through off and
      on. It covers the region's buttons placed in 3D as well as those in
      its row, which are one list now.
    - A menu takes its button's color until it overrides it.
    - A button whose menu's button is gone counts as the region's own.
    - The colors are copied with the region and with the button.
    """
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.color = (0.2, 0.4, 0.9)
    region.button_count = 5
    opener, plain, inside, deeper, placed = (region.buttons[k] for k in range(5))
    opener.opens_menu = True
    inside.opens_menu = True
    inside.menu_parent = opener.uid
    deeper.menu_parent = inside.uid
    placed.placed = True
    assert opener.uid > 0 and inside.uid > 0, "no ids for the menus"
    near = lambda x, y: all(abs(p - q) < 1e-5 for p, q in zip(x, y))    # noqa: E731

    def colors():
        return core.button_colors(region)

    blue, pink, green = tuple(region.color), (1.0, 0.5, 0.7), (0.1, 0.9, 0.2)
    assert all(near(c, blue) for c in colors()), "not the region's color by default"
    assert not hasattr(opener, "use_color"), "a button still has a color of its own"
    region.use_button_color = True
    assert near(region.button_color, blue), "the override does not start at the region's color"
    region.button_color = pink
    assert all(near(c, pink) for c in colors()), "the region's buttons not all in its override: %s" % colors()
    assert not hasattr(region, "use_placed_color"), "Placed in 3D still has a color of its own"
    inside.menu_use_color = True
    assert near(inside.menu_color, pink), "a menu's override does not start at its button's color"
    inside.menu_color = green
    got = colors()
    assert near(got[3], green), "the menu's button not in its menu's color: %s" % got
    assert near(got[2], pink) and near(got[0], pink) and near(got[1], pink), "the menu's color reached past it"
    opener.menu_use_color = True
    opener.menu_color = (0.9, 0.9, 0.1)
    got = colors()
    assert near(got[2], (0.9, 0.9, 0.1)) and near(got[3], green), "a menu inside a menu: %s" % got
    opener.menu_use_color = False
    region.use_button_color = False
    got = colors()
    assert near(got[0], blue) and near(got[2], blue) and near(got[3], green), "off: %s" % got
    region.use_button_color = True
    assert near(colors()[0], pink), "the picked color lost through off and on"
    assert near(core.button_color(region, deeper), green), "one button's color"
    deeper.menu_parent = 999
    assert near(colors()[3], pink), "a button whose menu's button is gone is not the region's own"
    other = core.new_region(mesh, "Copy", whole=True)
    core.from_data(other, core.to_data(region))
    assert other.use_button_color and near(other.button_color, pink), "not copied with the region"
    other.button_count = 1
    core.from_data(other.buttons[0], core.to_data(inside))
    assert other.buttons[0].menu_use_color and near(other.buttons[0].menu_color, green), \
        "a menu's color not copied with its button"


def _tree_mesh():
    """The arm's mesh, made active, with two regions and the panel's tree
    made for it. The regions are Other, and R holding three buttons: the
    first opens a menu holding the third."""
    core = rigs.kneady()
    tree = rigs.module("tree")
    _rig, mesh = rigs.arm_rig()
    bpy.context.view_layer.objects.active = mesh
    _region(mesh, "Other")
    _region(mesh, "R")
    other, region = mesh.kneady.regions[0], mesh.kneady.regions[1]  # the second added can move the first
    region.button_count = 3
    for b, name in zip(region.buttons, ("Opener", "Plain", "Inside")):
        b.name = name
    opener = region.buttons[0]
    opener.opens_menu = True
    opener.uid = 7
    region.buttons[2].menu_parent = 7
    tree.build(bpy.context, mesh)
    return core, tree, mesh, other, region


def _rows(tree):
    """(name, depth) of every row of the tree, folded or not."""
    out = []
    for row in bpy.context.window_manager.kneady_rows:
        region, index = tree.resolve(row)
        out.append((region.name if index is None else region.buttons[index].name, row.depth))
    return out


def test_tree_holds_regions_buttons_and_menus():
    """The panel's tree (Greg: "A menu containing the regions as the highest
    levels then you start nesting buttons under it then nesting buttons under
    other buttons"). It is one list for the object: its regions are the top
    rows, a region's own buttons sit under it, and a menu's buttons under
    the button that opens it. Every row starts folded. Selecting a row
    selects its region in the object's list and its button in its own
    list."""
    core, tree, mesh, other, region = _tree_mesh()
    assert _rows(tree) == [("Other", 0), (other.buttons[0].name, 1), ("R", 0), ("Opener", 1),
                           ("Inside", 2), ("Plain", 1)], _rows(tree)
    assert tree.visible_count(bpy.context) == 2, "not folded to start"
    region.tree_open = True
    assert tree.visible_count(bpy.context) == 4, "a region unfolded shows its own buttons, not its menus'"
    region.buttons[0].tree_open = True
    assert tree.visible_count(bpy.context) == 5
    region.tree_open = False
    assert tree.visible_count(bpy.context) == 2, "a menu shows with its region folded"
    region.buttons[0].tree_open = region.tree_open = False
    assert tree.select(bpy.context, region, 2), "no row for a button in a menu"
    assert region.tree_open and region.buttons[0].tree_open, "selecting did not unfold the way to it"
    obj, sel, index = tree.selection(bpy.context)
    assert obj == mesh and sel == region and index == 2, (obj, sel, index)
    assert mesh.kneady.regions[mesh.kneady.index] == region, "its region not selected in the object's list"
    assert core.selected_button(region, core.list_of(region, 2)) == 2, "not selected in its list"
    assert tree.select(bpy.context, other) and tree.selection(bpy.context)[2] is None, "a region's own row"
    # a button renamed needs no remake: rows read names as they draw
    sig = tree._TREE["sig"]
    region.buttons[1].name = "Renamed"
    assert tree.ensure(bpy.context, mesh) and tree._TREE["sig"] == sig
    region.button_count = 2                      # Inside gone: the tree is out of date
    assert not tree.ensure(bpy.context, mesh), "a button gone, and the rows still current"
    tree.build(bpy.context, mesh)
    assert [n for n, _d in _rows(tree)] == ["Other", "Button 1", "R", "Opener", "Renamed"]


def test_tree_adds_removes_and_moves():
    """+ adds a button under the row selected: among a region's buttons, or,
    under a button, in its menu. Add Region adds a region. - removes the row
    selected, and a button takes its menu with it. The arrows move a row
    among its own. Each change keeps the new row selected."""
    core, tree, mesh, _other, _region_r = _tree_mesh()
    regions = mesh.kneady.regions

    def named(name):
        # looked up afresh: adding, moving or removing a region moves the others in memory
        return next(r for r in regions if r.name == name)

    def picked():
        _obj, sel, index = tree.selection(bpy.context)
        return (sel.name if sel is not None else None), index

    tree.select(bpy.context, named("Other"))
    assert tree.add_beside(bpy.context, "REGION") == "" and len(regions) == 3, "Add Region added none"
    assert picked() == (regions[2].name, None), picked()
    tree.select(bpy.context, named("R"))
    assert tree.add_beside(bpy.context) == "" and named("R").button_count == 4, "+ on a region added no button"
    assert picked() == ("R", 3) and named("R").buttons[3].menu_parent == 0, "not added to the region's own"
    assert len(regions) == 3, "+ on a region added a region"
    # + on a button goes under it, into its menu (Greg: "press plus it
    # doesn't create a new entry nested under "Offset / Scale" and it
    # should"). The free Kneady builds menus now (menu_build.py, which was in
    # Kneady Pro until it moved here)
    tree.select(bpy.context, named("R"), 1)
    assert tree.add_beside(bpy.context) == "" and named("R").button_count == 5, "+ on a button added none"
    uid = named("R").buttons[1].uid                 # given one as its menu is made
    assert picked() == ("R", 4) and uid and named("R").buttons[4].menu_parent == uid, "not added under the button"
    assert named("R").buttons[1].opens_menu, "the button does not open its menu"
    tree.select(bpy.context, named("R"), 1)
    assert tree.can_move(bpy.context, -1) and tree.move_selected(bpy.context, -1)
    assert named("R").buttons[0].name == "Plain" and picked() == ("R", 0), "not moved, or not followed"
    assert not tree.can_move(bpy.context, -1), "the first can move up"
    count = named("R").button_count
    # a removed button takes its menu with it
    assert tree.remove_selected(bpy.context) == "" and named("R").button_count == count - 2, \
        "removing a button left its menu"
    assert picked()[0] == "R", "the selection left the region"
    tree.select(bpy.context, named("Other"))
    assert tree.can_move(bpy.context, 1) and not tree.can_move(bpy.context, -1)
    assert tree.move_selected(bpy.context, 1) and [r.name for r in regions][:2] == ["R", "Other"]
    assert picked() == ("Other", None), "the region moved, the selection did not follow"
    assert tree.remove_selected(bpy.context) == "" and "Other" not in [r.name for r in regions]


def test_viewport_edit():
    """Viewport Edit (once called Pick Buttons, until Greg renamed it):

    - picking a button selects its row in the tree, unfolding the way to it,
      and marks it while it is the one selected, whether selected there or in
      the panel. A region picked alone marks nothing
    - + adds a button to those showing and selects it; - removes the one
      selected. They sit at the top right corner of the square round the
      buttons showing, and - shows only while the selected button shows
    """
    core, tree, mesh, other, region = _tree_mesh()
    pick = rigs.module("pick")
    wm = bpy.context.window_manager
    assert not core.picking(), "Viewport Edit on to start"
    assert bpy.types.WindowManager.bl_rna.properties["kneady_pick"].name == "Viewport Edit"
    wm.kneady_pick = True
    try:
        assert core.picking()
        pick.pick(bpy.context, mesh, region, 2)
        assert region.tree_open and region.buttons[0].tree_open, "the way to it not unfolded"
        assert tree.selection(bpy.context)[1:] == (region, 2), "not selected in the tree"
        assert pick.marked(region) == 2 and pick.marked(other) is None, "not marked"
        tree.select(bpy.context, region, 1)              # chosen in the panel instead
        assert pick.marked(region) == 1, "the panel's choice not marked"
        pick.pick(bpy.context, mesh, region)
        assert pick.marked(region) is None, "a region picked alone marks a button"
        bpy.ops.kneady.edit_add(target=mesh.name, region=region.id)
        assert region.button_count == 4 and pick.marked(region) == 3, "+ did not add and select one"
        bpy.ops.kneady.edit_remove(target=mesh.name, region=region.id)
        assert region.button_count == 3, "- did not remove the one selected"
        # where they sit: out from the corners of the square round the
        # buttons showing (Greg: "I'd rather it was in the corner"). + and -
        # are at the top right, - only with the selected one among them, and
        # Rearrange is at the top left
        real, real_center = core._layout, core.region_center
        row = [(0, Vector((100.0, 50.0))), (1, Vector((134.0, 50.0)))]
        core._layout = lambda *_a: ([], list(row), set(), {})
        core.region_center = lambda *_a: Vector((117.0, 50.0))          # the row's middle
        try:
            tree.select(bpy.context, region, 1)
            icons = pick.edit_icons(bpy.context, mesh, region)
            assert set(icons) == {"ADD", "REMOVE", "ARRANGE", "PLACE"}, icons
            r = core.button_radius()
            out = pick.CORNER_OUT * core.button_spacing()
            corner = Vector((134.0 + r + out, 50.0 + r + out))
            assert (icons["ADD"] - corner).length < 1e-6, (icons["ADD"], corner)
            assert icons["REMOVE"].y == icons["ADD"].y and icons["REMOVE"].x > icons["ADD"].x + r, icons
            assert (icons["ARRANGE"] - Vector((100.0 - r - out, 50.0 + r + out))).length < 1e-6, icons
            # they stay put as buttons come and go (Greg: "The viewport edit
            # buttons shouldn't change their position as the menu is
            # edited"): a third button in the row, then one fewer
            row[:] = [(0, Vector((83.0, 50.0))), (1, Vector((117.0, 50.0))), (2, Vector((151.0, 50.0)))]
            moved = pick.edit_icons(bpy.context, mesh, region)
            assert (moved["ADD"] - icons["ADD"]).length < 1e-6 and (moved["ARRANGE"] - icons["ARRANGE"]).length < 1e-6, \
                "an added button moved them: %s -> %s" % (icons["ADD"], moved["ADD"])
            row[:] = [(0, Vector((117.0, 50.0)))]
            assert abs(pick.corners(bpy.context, mesh, region)[2] - (134.0 + r + out)) < 1e-6, \
                "a removed one pulled them in"
            # a column inside the row's width never reaches them, diagonally out
            row[:] = [(0, Vector((117.0, 50.0 + 34.0 * k))) for k in range(4)]
            assert abs(pick.corners(bpy.context, mesh, region)[3] - (50.0 + r + out)) < 1e-6, "a column moved them"
            # moved out only when the buttons would reach one: a grid over the + at the top right
            row[:] = [(0, Vector((80.0, 50.0))), (1, Vector((154.0, 50.0))), (2, Vector((80.0, 84.0))),
                      (3, Vector((154.0, 84.0)))]
            assert pick.corners(bpy.context, mesh, region)[3] > 84.0 + r, "the buttons reached them, and they stayed"
            row[:] = [(0, Vector((100.0, 50.0))), (1, Vector((134.0, 50.0)))]
            pick._FROZEN.update(key=None, corners=None)
            tree.select(bpy.context, region, 2)          # in the menu, not showing
            assert set(pick.edit_icons(bpy.context, mesh, region)) == {"ADD", "ARRANGE", "PLACE"}
            hover = (mesh.name, region.id)
            assert pick.edit_hit(bpy.context, hover, icons["ADD"]) == "ADD"
            assert pick.edit_hit(bpy.context, hover, icons["ARRANGE"]) == "ARRANGE"
            # the whole square, out to the icons, holds the region; past it, nothing
            assert pick.edit_hit(bpy.context, hover, Vector((117.0, 50.0 - r - out))) == pick.SQUARE
            assert pick.edit_hit(bpy.context, hover, Vector((117.0, 50.0 - r - out - 3.0 * r))) is None
            # Place on Surface beside Rearrange at the top left (part of the
            # free Kneady now), and a program's icon beside that, further out
            step = 2.0 * pick.EDIT_SIZE * r + pick.EDIT_GAP * core.ui_scale()
            assert (icons["PLACE"] - (icons["ARRANGE"] - Vector((step, 0.0)))).length < 1e-3, \
                "Place on Surface not beside Rearrange: %s" % icons
            pick.add_corner_icon(dict(key="TEST", corner="TOP_LEFT", operator="kneady.edit_arrange", glyph="PIN",
                                      shown=lambda *_a: True, lit=lambda *_a: False))
            try:
                icons = pick.edit_icons(bpy.context, mesh, region)
                assert (icons["TEST"] - (icons["PLACE"] - Vector((step, 0.0)))).length < 1e-3, \
                    "not beside Place on Surface, further out: %s" % icons
                assert "TEST" in pick.icon_parts() and pick.icon_look(bpy.context, mesh, region, "TEST") == ("PIN", False)
            finally:
                pick.remove_corner_icon("TEST")
        finally:
            core._layout, core.region_center = real, real_center
            pick._FROZEN.update(key=None, corners=None)
    finally:
        wm.kneady_pick = False


def test_removing_a_button_removes_its_menu():
    """A removed button takes the buttons in its menu with it, and theirs
    (Greg: "if a user deletes a button that has children the children are
    delted too. Having them come up a level is kind of chaotic"). A button
    without a menu goes alone. Nothing goes that would leave the region
    without a button."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 6
    names = ("Keep", "Opener", "In", "Sub", "Deep", "Also Keep")
    for b, name in zip(region.buttons, names):
        b.name = name
    region.buttons[1].opens_menu, region.buttons[1].uid = True, 1
    region.buttons[2].menu_parent = 1
    region.buttons[3].opens_menu, region.buttons[3].uid, region.buttons[3].menu_parent = True, 2, 1
    region.buttons[4].menu_parent = 2
    assert core.removed_with(region, "all", 1) == [1, 2, 3, 4]
    assert core.remove_button(region, "all", 1) == ""
    assert [b.name for b in core.buttons_of(region)] == ["Keep", "Also Keep"], [b.name for b in core.buttons_of(region)]
    assert core.remove_button(region, "all", 0) == "" and [b.name for b in core.buttons_of(region)] == ["Also Keep"]
    # an opener whose menu holds every other button cannot take them all
    region.button_count = 2
    region.buttons[0].opens_menu, region.buttons[0].uid = True, 9
    region.buttons[1].menu_parent = 9
    assert core.remove_button(region, "all", 0) == "A region keeps one button" and region.button_count == 2


def test_rearrange_in_the_viewport():
    """Rearrange (Greg: "dragging one button above or below another button
    pushes the other buttons up or down or around"). A button picked up moves
    through its list as the mouse passes each place, and the others make
    room. Esc puts it back. A list of one has nothing to rearrange."""
    core = rigs.kneady()
    arrange = rigs.module("arrange")
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 4
    for b, name in zip(region.buttons, "ABCD"):
        b.name = name
    step = 34.0

    def layout(*_a):
        # the row as the layout draws it: in list order, left to right
        return [], [(i, Vector((100.0 + step * k, 50.0))) for k, i in enumerate(range(region.button_count))], set(), {}

    def order():
        return "".join(b.name for b in core.buttons_of(region))

    real = core._layout
    core._layout = layout
    try:
        assert arrange.movable(bpy.context, mesh, region, 0) and arrange.can_arrange(bpy.context, mesh, region)
        session = arrange.Session(bpy.context, mesh, region, 0, (100.0, 50.0))
        session.move(bpy.context, (100.0 + 2 * step + 3.0, 52.0))
        assert order() == "BCAD" and session.index == 2, order()
        moving = core.STATE["arranging"]
        assert moving[2] == 2 and abs(moving[3][0] - (100.0 + 2 * step + 3.0)) < 1e-6, "it does not follow the mouse"
        session.move(bpy.context, (100.0 + 3 * step, 50.0))
        assert order() == "BCDA", order()
        assert session.done(), "moved, and not said so"
        assert core.STATE["arranging"] is None
        session = arrange.Session(bpy.context, mesh, region, 1, (134.0, 50.0))      # C
        session.move(bpy.context, (100.0, 50.0))
        assert order() == "CBDA", order()
        session.cancel()
        assert order() == "BCDA", "Esc did not put it back: %s" % order()
        region.button_count = 1
        assert not arrange.movable(bpy.context, mesh, region, 0) and not arrange.can_arrange(bpy.context, mesh, region)
    finally:
        core._layout = real
        core.STATE["arranging"] = None


def test_copy_commands():
    """Copy Commands (Greg: "copy the set of commands from one button to
    another"): what one button drives is pasted onto another, which keeps its
    own name, look, place and menu."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 2
    a, b = region.buttons[0], region.buttons[1]
    a.name, b.name = "A", "B"
    a.up.enabled, a.up.kind, a.up.target, a.up.bone, a.up.axis = True, "ROTATE", rig, "Upper", "Z"
    a.single = False
    b.icon_type, b.shape, b.placed, b.uid, b.menu_parent = "TEXT", "SQUARE", True, 4, 9
    core.copy_data(bpy.context, "commands", core.commands_data(a))
    found = core.copied(bpy.context, "commands")
    assert found is not None and "name" not in found["data"], "copied more than the commands"
    assert core.paste_commands(b, found) is None
    assert b.up.enabled and b.up.kind == "ROTATE" and b.up.bone == "Upper" and b.up.axis == "Z" and not b.single
    assert (b.name, b.icon_type, b.shape, b.placed, b.uid, b.menu_parent) == ("B", "TEXT", "SQUARE", True, 4, 9), \
        "the button lost its own"


def test_pinned_region_paints_alone():
    """While a region is kept (pinned), it is the only one of its object's
    regions painted (Greg: "Pinning the start leaves the end highlighted
    which it shouldn't. Only the pinned cap should be highlighted"). Once
    let go, every region is painted again."""
    core = rigs.kneady()
    draw = _draw()
    _rig, mesh = rigs.arm_rig()
    for name in ("Body", "Start", "End"):
        core.new_region(mesh, name)
    ids = [r.id for r in mesh.kneady.regions]
    try:
        assert [r.id for r in draw.painted(mesh)] == ids, "not every region painted"
        core.keep(bpy.context, mesh.name, ids[1])
        assert [r.id for r in draw.painted(mesh)] == [ids[1]], \
            "pinned: %s painted" % [r.name for r in draw.painted(mesh)]
        core.let_go(bpy.context)
        assert [r.id for r in draw.painted(mesh)] == ids, "let go: not every region painted"
    finally:
        core.let_go(bpy.context)


def test_button_list():
    """A region's buttons are a list (Greg: "Buttons are added and removed
    with + and - on upper right of menu. No more changing the number of
    buttons"):

    - + adds a fresh one at the end, selected
    - the arrows move the selected one: two change places and the rest stay,
      each keeping its settings
    - - removes it, and the next is selected

    The row holds eight; a region keeps one."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    names = lambda: [b.name for b in core.buttons_of(region)]  # noqa: E731
    region.buttons[0].name = "B0"
    # a button kept past the count, from before the list: left as it was
    region.buttons.add().name = "Kept"
    with bpy.context.temp_override(kneady_region=region):
        for k in range(3):
            assert bpy.ops.kneady.button_add() == {"FINISHED"}
            assert region.button_index == k + 1, "the new one is not selected"
    assert names() == ["B0", "Button 1", "Button 2", "Button 3"], names()
    assert "Kept" in [b.name for b in list(region.buttons)[region.button_count:]]
    assert not region.buttons[2].up.enabled and region.buttons[2].show, "a new button is not fresh"
    for k, b in enumerate(core.buttons_of(region)):
        b.name, b.up.enabled, b.up.rate = "B%d" % k, True, 0.1 * (k + 1)
    region.buttons[0].action = "TOGGLE"
    assert core.button_home(region.buttons[2]) == (region, 2), core.button_home(region.buttons[2])
    with bpy.context.temp_override(kneady_region=region):
        assert bpy.ops.kneady.button_move(direction="UP") == {"FINISHED"}
        assert names() == ["B0", "B1", "B3", "B2"] and region.button_index == 2, (names(), region.button_index)
        assert abs(region.buttons[2].up.rate - 0.4) < 1e-6, "the settings did not move with the button"
        assert bpy.ops.kneady.button_move(direction="UP") == {"FINISHED"}
        assert names() == ["B0", "B3", "B1", "B2"], names()
        assert core.first_drag_button(region) == 1, "the region drag runs another"
        assert bpy.ops.kneady.button_move(direction="UP") == {"FINISHED"}
        assert bpy.ops.kneady.button_move(direction="UP") == {"CANCELLED"}, "the top went further"
        # - removes the selected one, the next taking its place in the selection
        assert names() == ["B3", "B0", "B1", "B2"] and region.button_index == 0
        assert bpy.ops.kneady.button_remove() == {"FINISHED"}
        assert names() == ["B0", "B1", "B2"] and region.button_index == 0, (names(), region.button_index)
        region.button_index = 2
        assert bpy.ops.kneady.button_remove() == {"FINISHED"}
        assert names() == ["B0", "B1"] and region.button_index == 1, (names(), region.button_index)
        # the row holds eight (Greg: "Let's make the maximum number of buttons 8
        # instead of 6")
        for _k in range(6):
            assert bpy.ops.kneady.button_add() == {"FINISHED"}
        assert region.button_count == 8 and core.can_add(region)
        assert bpy.ops.kneady.button_add() == {"CANCELLED"}
        # and a region keeps one
        for _k in range(7):
            assert bpy.ops.kneady.button_remove() == {"FINISHED"}
        assert region.button_count == 1
        assert bpy.ops.kneady.button_remove() == {"CANCELLED"}
    # two far apart change places, the ones between staying
    region.button_count = 4
    for k, b in enumerate(core.buttons_of(region)):
        b.name = "B%d" % k
    core.swap_buttons(region, 0, 3)
    assert names() == ["B3", "B1", "B2", "B0"], names()


def test_badge_on_the_outline():
    """A program may mark a button (one that opens a menu, say) with a small
    circle on its outline at the upper right (Greg: "a little circle in the
    upper right of the button on it's outline")."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 2
    circle, text = region.buttons[0], region.buttons[1]
    text.icon_type, text.name = "TEXT", "Elbow Axes"
    mark = lambda reg, button: button.name == "Elbow Axes"  # noqa: E731
    assert not core.badged(region, text)
    core.add_badge(mark)
    try:
        assert core.badged(region, text) and not core.badged(region, circle)
    finally:
        core.remove_badge(mark)
    r = core.button_radius()
    c = Vector((100.0, 100.0))
    at, size = core.badge_at(circle, c)
    assert abs((at - c).length - r) < 1e-4 and at.x > c.x and abs((at.x - c.x) - (at.y - c.y)) < 1e-4, at
    assert 0.0 < size < 0.5 * r, size
    at, _size = core.badge_at(text, c)
    half, tall = core.half_size(text)
    assert c.x + half * 0.8 < at.x <= c.x + half and c.y + tall * 0.6 < at.y <= c.y + tall, (at, half, tall)


def test_square_buttons():
    """A button's Shape: a circle, or a square of the same size with corners
    rounded as a text box's are (Greg: "options for square buttons vs. round
    ... visual distinction"; "Squares have rounded corners like the text
    boxes for sure"). A square is hit, overlapped, avoided by names and
    badged by its own outline, and the shape is copied with the button."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 3
    circle, square, text = region.buttons[0], region.buttons[1], region.buttons[2]
    assert circle.shape == "CIRCLE", "a new button is not a circle"
    square.shape = "SQUARE"
    text.icon_type, text.name, text.shape = "TEXT", "Words", "SQUARE"
    r = core.button_radius()
    assert core.outline_of(circle) == (r, r, r)
    w, h, corner = core.outline_of(square)
    assert (w, h) == (r, r) and abs(corner - r * core.TEXT_ROUND) < 1e-6, (w, h, corner)
    tw, th = core.half_size(text)
    assert core.outline_of(text) == (tw, th, th * core.TEXT_ROUND), "a text button is its name's box"
    assert core.boxed(square) and core.boxed(text) and not core.boxed(circle)
    # its corner is the square's, not the circle's
    c = Vector((100.0, 100.0))
    corner_in = c + Vector((0.8 * r, 0.8 * r))
    assert core.near_button(corner_in, c, core.outline_of(square), r), "the square's corner missed"
    assert not core.near_button(corner_in, c, core.outline_of(circle), r), "a circle hit at a square's corner"
    assert not core.near_button(c + Vector((0.9 * r, 0.9 * r)), c, core.outline_of(square), r), \
        "hit past the rounded corner"
    assert core.near_button(c + Vector((r - 0.5, 0.0)), c, core.outline_of(square), r)
    assert not core.near_button(c + Vector((r + 0.5, 0.0)), c, core.outline_of(square), r)
    # two side by side, then corner to corner
    sq, ci = core.outline_of(square), core.outline_of(circle)
    assert core.outlines_overlap(c, sq, c + Vector((2.0 * r - 1.0, 0.0)), sq)
    assert not core.outlines_overlap(c, sq, c + Vector((2.0 * r + 1.0, 0.0)), sq)
    diagonal = c + Vector((1.6 * r, 1.6 * r))
    assert core.outlines_overlap(c, sq, diagonal, sq), "two squares' corners did not meet"
    assert not core.outlines_overlap(c, ci, diagonal, ci), "two circles met where only squares do"
    # a button diagonally off the name's corner: a circle there clears it, a
    # square's corner reaches it, and the name moves above
    plain = core.label_box(c, 30.0, r)
    (_x0, y0, x1, _y1), _at = plain
    off = Vector((x1 + 0.764 * r, y0 - 0.764 * r))
    assert core.label_box(c, 30.0, r, avoid=[(off, *ci)]) == plain, "a circle clear of the name moved it"
    assert core.label_box(c, 30.0, r, avoid=[(off, *sq)]) != plain, "a name over a square's corner"
    # its badge sits on its corner
    at, _size = core.badge_at(square, c)
    lean = math.sqrt(0.5)
    expect = r - corner * (1.0 - lean)
    assert abs(at.x - c.x - expect) < 1e-4 and abs(at.y - c.y - expect) < 1e-4, (at, expect)
    assert core.to_data(square)["shape"] == "SQUARE", "copy and paste lose the shape"


def test_rows_of_eight():
    """Row + Column lays out up to eight in rows of two, an odd last one
    centered above them (Greg, for five: "the 5th centered above in between
    columns"). A row holds eight, none overlapping."""
    core = rigs.kneady()
    assert core.grid_rows(4, "GRID") == [[0, 1], [2, 3]]
    assert core.grid_rows(5, "GRID") == [[4], [0, 1], [2, 3]]
    assert core.grid_rows(6, "GRID") == [[0, 1], [2, 3], [4, 5]]
    assert core.grid_rows(7, "GRID") == [[6], [0, 1], [2, 3], [4, 5]]
    assert core.grid_rows(8, "GRID") == [[0, 1], [2, 3], [4, 5], [6, 7]]
    assert core.grid_rows(8, "ROW") == [list(range(8))]
    r = core.button_radius()
    for arrange in ("ROW", "COLUMN", "GRID", "CIRCLE"):
        pts = [c for _i, c in core.arranged(list(range(8)), Vector((400.0, 400.0)), arrange)]
        assert len(pts) == 8
        for m, a in enumerate(pts):
            for b in pts[m + 1:]:
                assert (a - b).length >= 2.0 * r - 1e-4, "%s: two circles overlap" % arrange


def test_drag_sections_fold():
    """A drag direction's section folds away whether it is on or not (Greg:
    "collapsible sections so they can be hidden even when enabled"). It
    starts open, and whether it is left open is not copied with the
    button."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    button = region.buttons[0]
    assert button.up.ui_open and button.across.ui_open and button.switch.ui_open
    button.up.ui_open = False
    data = core.to_data(button)
    assert "ui_open" not in data["up"], "the section's state is copied"


def test_click_holds_its_spot():
    """A click that changes the buttons (a toggle, or a click a program takes)
    holds its region hovered at the spot clicked until the mouse moves off it
    (Greg: "In that moment of switching, kneady ends up catching the
    adjacent region ... maybe when switching menus, selection is blocked
    until the new menu is present")."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    view = type("View", (), {"as_pointer": lambda self: 0})()
    other = type("View", (), {"as_pointer": lambda self: 1})()
    hover = (mesh.name, region.id)
    reach = core.button_radius() + core.BUTTON_BLOCK
    try:
        core.hold_click(bpy.context, mesh, region, (100.0, 100.0), 0)
        assert core.held_at(hover, Vector((100.0 + reach - 0.5, 100.0)), view), "the spot clicked lets go"
        assert not core.held_at(hover, Vector((100.0, 100.0)), other), "another view's mouse held it"
        assert core.STATE["held"] is not None, "another view's mouse let it go"
        assert not core.held_at((mesh.name, region.id + 1), Vector((100.0, 100.0)), view), "held another region"
        assert core.STATE["held"] is None, "still held once another region was hovered"
        core.hold_click(bpy.context, mesh, region, (100.0, 100.0), 0)
        assert not core.held_at(hover, Vector((100.0 + reach + 0.5, 100.0)), view), "held off the spot"
        assert not core.held_at(hover, Vector((100.0, 100.0)), view), "held again, coming back to it"
    finally:
        core.STATE["held"] = None


def test_areas_hold_the_hover():
    """A program's layout may hold the hover over an area on screen (its
    "areas"), which can be any polygon. A menu uses it for the span of its
    buttons, so the mouse can go between them over whatever lies there."""
    core = rigs.kneady()
    square = [Vector((0.0, 0.0)), Vector((10.0, 0.0)), Vector((10.0, 10.0)), Vector((0.0, 10.0))]
    assert core.in_area(Vector((5.0, 5.0)), square) and not core.in_area(Vector((11.0, 5.0)), square)
    ell = [Vector(p) for p in ((0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10))]
    assert core.in_area(Vector((2.0, 8.0)), ell) and not core.in_area(Vector((8.0, 8.0)), ell), "not any shape"
    pts = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 5), (3, 7)]
    got = core.hull(pts)
    assert sorted((round(p.x), round(p.y)) for p in got) == [(0, 0), (0, 10), (10, 0), (10, 10)], got
    assert core.in_area(Vector((5.0, 9.0)), got) and not core.in_area(Vector((5.0, 11.0)), got)


def test_click_hooks_read_shift():
    """A click hook reads whether Shift was held (click_shift): Shift+click
    pins a menu where a plain click opens it."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    seen = []

    def hook(_context, _obj, _region, _index):
        seen.append(core.click_shift())
        return True

    core.add_click_hook(hook)
    try:
        assert core.clicked(bpy.context, mesh, region, 0, True) and core.clicked(bpy.context, mesh, region, 0)
    finally:
        core.remove_click_hook(hook)
    assert seen == [True, False] and not core.click_shift(), seen


def test_keep_the_hover():
    """A program may keep the hover on a region until it lets go, showing a
    note in the status bar meanwhile, between drags too (idle_status).
    Turning Kneady off lets go too."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    try:
        core.keep(bpy.context, mesh.name, region.id, note="Held")
        assert core.kept() == (mesh.name, region.id) and core.STATE["hover"] == (mesh.name, region.id)
        assert core.idle_status() == "Held"
        core.let_go(bpy.context)
        assert core.kept() is None and core.idle_status() is None
        core.keep(bpy.context, mesh.name, region.id, note="Held")
        bpy.context.scene.kneady_on = not bpy.context.scene.kneady_on
        assert core.kept() is None, "still kept with Kneady turned off and on"
        # an undo or a redo keeps it (Greg: "people will undo frequently");
        # loading a file, or the region going, lets go
        undo = [fn for fn in bpy.app.handlers.undo_post if fn.__module__ == core.__package__]
        load = [fn for fn in bpy.app.handlers.load_post if fn.__name__ == "_on_reload"
                and fn.__module__ == core.__package__]
        assert undo and load, "Kneady's undo and load handlers are not registered"
        core.keep(bpy.context, mesh.name, region.id, note="Held")
        for fn in undo:
            fn(bpy.context.scene, None)
        assert core.kept() == (mesh.name, region.id) and core.idle_status() == "Held", "an undo let go"
        assert core.STATE["hover"] == (mesh.name, region.id)
        for fn in load:
            fn(None)
        assert core.kept() is None, "a file loaded kept it"
        core.keep(bpy.context, mesh.name, region.id, note="Held")
        core.reset_state(keep=True)
        assert core.kept() is not None
        mesh.kneady.regions.remove(next(k for k, r in enumerate(mesh.kneady.regions) if r.id == region.id))
        core.reset_state(keep=True)
        assert core.kept() is None, "kept after its region went"
    finally:
        core.let_go(bpy.context)


def test_strong_badge():
    """A mark may be strong (2): what the button opens is held open."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    region.button_count = 2
    weak = lambda _r, b: b == region.buttons[0] or b == region.buttons[1]  # noqa: E731
    strong = lambda _r, b: 2 if b == region.buttons[1] else False  # noqa: E731
    core.add_badge(weak)
    core.add_badge(strong)
    try:
        assert core.badged(region, region.buttons[0]) == 1 and core.badged(region, region.buttons[1]) == 2
    finally:
        core.remove_badge(weak)
        core.remove_badge(strong)
