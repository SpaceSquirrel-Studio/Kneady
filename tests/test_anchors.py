"""Handles beyond one add-on. Greg asked: "How can we manage more general
usage of handles? The ability to connect commands to a handle. How to place
the handles ... I imagine they would be placed similarly to how buttons are
placed", then "the thing that was keeping me away from that was the sides
drag modes. Let's do it."

- Anchors: a placed button sits at a point that moves with what it is on (a
  bone's head or tail, an object's origin, or a point a program gives) and
  follows it exactly.
- A command kind from a program, driven by a drag: it is moved by what the
  drag gives it, writes its value its own way, and reads its own modifier
  keys.
- A menu that Stays Open: a click pins it, a click in empty space closes it.
- A Move along an object's Location channels."""

import math

import bpy  # type: ignore
from mathutils import Matrix, Vector  # type: ignore

import rigs

KEY = "test_slider"
TIP = "test:tip"


def _slider(core):
    """A program's drag kind. It raises `obj["slide"]` by the amount, moving
    along the object's own X, and goes twice as far with Alt held (a key it
    reads itself)."""
    def motion(obj, command, point):
        return ("MOVE", obj.matrix_world.to_3x3().col[0].normalized())

    def begin(context, obj, command):
        if obj.type != "MESH":
            return "A slider is a mesh's"
        return dict(obj=obj, start=float(obj.get("slide", 0.0)))

    def apply(context, state, amount, ctrl, keys):
        state["obj"]["slide"] = state["start"] + amount * (2.0 if "ALT" in keys else 1.0)

    def restore(context, state):
        state["obj"]["slide"] = state["start"]

    core.add_command_kind(KEY, "Slider", summary=lambda command: "Slide", icon="ARROW_LEFTRIGHT",
                          drag=dict(motion=motion, begin=begin, apply=apply, restore=restore,
                                    keys=lambda command: {"ALT"}, status=lambda command: "Alt: twice as far"))


def _tips(core):
    """A program's anchor: two units above each mesh's origin, along its Z."""
    def anchors(obj, region, key=None):
        if obj.type != "MESH" or key not in (None, TIP):
            return []
        m = obj.matrix_world
        return [dict(key=TIP, name="Tip", point=m @ Vector((0.0, 0.0, 2.0)), frame=m.to_3x3(),
                     normal=m.to_3x3().col[2].normalized())]
    core.add_anchors(anchors)
    return anchors


def test_a_program_drag_kind():
    """A drag direction driving a program's command kind. The kind is:

    - listed for drags, not for clicks
    - resolved for the object dragged, giving its own reason when it can't
      run
    - written by the drag's amount, with the keys it reads handed to it
    - put back on a cancel
    """
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    button = region.buttons[0]
    button.up.enabled, button.up.program = True, KEY
    _slider(core)
    try:
        assert KEY in [k["key"] for k in core.command_kinds(switch=False)]
        assert KEY not in [k["key"] for k in core.command_kinds(switch=True)], "a drag kind offered for a click"
        mesh["slide"] = 1.0
        ch = core.Channel(button.up, mesh, region)
        assert ch.ok and ch.dragging and ch.kind == "PROGRAM", ch.why
        assert ch.keys_taken() == {"ALT"}
        core.apply([ch], [0.25])
        assert abs(mesh["slide"] - 1.25) < 1e-9, mesh["slide"]
        core.apply([ch], [0.25], keys={"ALT"})
        assert abs(mesh["slide"] - 1.5) < 1e-9, "the keys it reads were not handed over"
        ch.restore()
        assert abs(mesh["slide"] - 1.0) < 1e-9, "a cancel left it"
        assert "Slide" in ch.label()
        # its speed off a handle: scene units per 100 pixels, as a Move's
        button.up.rate = 0.5
        assert abs(core.amount_for(ch, 100.0, 1.0) - 0.5) < 1e-9
        # along a handle, a pixel is what the handle says
        ch.handle_per_pixel = 0.01
        assert abs(core.amount_for(ch, 30.0, 1.0) - 0.3) < 1e-9
        # its own reason, on what it cannot run on
        button.up.dragged, button.up.target = False, rig
        ch = core.Channel(button.up, mesh, region)
        assert not ch.ok and ch.why == "A slider is a mesh's", ch.why
        # a click cannot switch a kind that is only dragged
        button.up.target, button.up.dragged = None, True
        ch = core.Channel(button.up, mesh, region, switch=True)
        assert not ch.ok and "click" in ch.why, ch.why
    finally:
        core.remove_command_kind(KEY)


def test_anchors_and_handles_at_them():
    """A placed button at an anchor sits on it and follows it, in its frame,
    as its object moves. It is hidden where the object has no such point. A
    3D handle there points along its program drag's motion. Kneady's own
    anchors are the object's origin, and the head and tail of each bone its
    buttons turn."""
    core = rigs.kneady()
    placed = rigs.module("placed")
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    region.button_count = 2
    handle = region.buttons[1]
    handle.up.enabled, handle.up.program = True, KEY
    handle.placed, handle.handle, handle.anchor = True, "HANDLE", TIP
    _slider(core)
    provider = _tips(core)
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        found = placed.button_point(mesh, region, handle, depsgraph)
        assert found is not None and (found[0] - mesh.matrix_world @ Vector((0, 0, 2))).length < 1e-6, found
        # it follows the object
        mesh.matrix_world = Matrix.Translation((1.0, 2.0, 3.0)) @ Matrix.Rotation(math.radians(30), 4, "Y")
        bpy.context.view_layer.update()
        point, normal = placed.button_point(mesh, region, handle, depsgraph)
        assert (point - mesh.matrix_world @ Vector((0, 0, 2))).length < 1e-6, point
        frame = placed.frame_of(mesh, region, handle)
        assert (frame.translation - point).length < 1e-6
        # a 3D handle there points along what it drives: the slider's X
        d, lever = placed.handle_direction(mesh, region, handle, point, normal)
        assert (d - mesh.matrix_world.to_3x3().col[0].normalized()).length < 1e-6 and lever is None, d
        # Points: Z, in the anchor's own frame
        handle.handle_axis = "Z"
        d, _lever = placed.handle_direction(mesh, region, handle, point, normal)
        assert (d - mesh.matrix_world.to_3x3().col[2].normalized()).length < 1e-6, d
        # an object without the point: not shown
        handle.anchor = "test:nowhere"
        assert placed.button_point(mesh, region, handle, depsgraph) is None
        # Kneady's own: the origin, and the bone the region's first button turns
        keys = [a["key"] for a in core.anchors_of(mesh, region)]
        head = "bone|%s|Lower|HEAD" % rig.name
        assert core.ORIGIN in keys and head in keys and TIP in keys, keys
        handle.anchor = head
        point, _normal = placed.button_point(mesh, region, handle, depsgraph)
        assert (point - rig.matrix_world @ rig.pose.bones["Lower"].head).length < 1e-6
        # the bone turned: its tail anchor follows
        handle.anchor = "bone|%s|Lower|TAIL" % rig.name
        rig.pose.bones["Lower"].rotation_mode = "XYZ"
        rig.pose.bones["Lower"].rotation_euler.x = math.radians(40)
        bpy.context.view_layer.update()
        point, _normal = placed.button_point(mesh, region, handle, depsgraph)
        tail = rig.matrix_world @ rig.pose.bones["Lower"].tail
        assert (point - tail).length < 1e-6, (point, tail)
    finally:
        core.remove_anchors(provider)
        core.remove_command_kind(KEY)


def test_a_menu_that_stays_open():
    """A click on a button whose menu Stays Open opens the menu pinned, and a
    click in empty space lets go of it (core.kept_click_off). Closing the
    menu also lets go. A menu without Stays Open is not pinned by a click."""
    core = rigs.kneady()
    menus = rigs.module("menus")
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    region.button_count = 2
    opener = region.buttons[0]
    opener.opens_menu = True
    menus.ensure_uid(region, opener)
    region.buttons[1].menu_parent = opener.uid
    menus.OPEN.clear()
    core.let_go()
    # no Stays Open: opened, not pinned
    menus.open_menu = _opener(menus)
    try:
        assert core.clicked(bpy.context, mesh, region, 0)
        assert menus.opened(mesh, region) is not None and core.kept() is None
        assert core.clicked(bpy.context, mesh, region, 0)          # closed again
        assert menus.opened(mesh, region) is None
        opener.menu_stays = True
        assert core.clicked(bpy.context, mesh, region, 0)
        assert menus.opened(mesh, region) is not None
        assert core.kept() == menus.key_of(mesh, region) and core.kept_click_off(), core.kept()
        # a click in space (close_kept): closed, let go
        menus.close_kept(bpy.context)
        assert menus.opened(mesh, region) is None and core.kept() is None
        # its button again: closed, let go
        assert core.clicked(bpy.context, mesh, region, 0) and core.kept_click_off()
        assert core.clicked(bpy.context, mesh, region, 0)
        assert menus.opened(mesh, region) is None and core.kept() is None and not core.kept_click_off()
        # a program's keep with click_off: let go, its release called
        released = []
        core.keep(bpy.context, mesh.name, region.id, by="test", release=lambda c: released.append(1),
                  click_off=True)
        assert core.kept_click_off()
        menus.close_kept(bpy.context)
        assert released == [1] and core.kept() is None
        # a Shift+click pin is not let go by a click in space
        core.toggle_kept(bpy.context, mesh, region)
        assert core.kept() is not None and not core.kept_click_off()
        core.let_go()
    finally:
        menus.open_menu = _ORIGINAL[0]
        menus.OPEN.clear()


_ORIGINAL = []


def _opener(menus):
    """open_menu without a view: anchored at the region's middle."""
    _ORIGINAL[:] = [menus.open_menu]

    def open_menu(context, obj, region, index):
        uid = menus.ensure_uid(region, rigs.kneady().buttons_of(region)[index])
        menus.OPEN.setdefault(menus.key_of(obj, region), []).append((uid, ("middle", None)))
        return True
    return open_menu


def test_move_along_location_channels():
    """A Move of a turned object along its Location channels changes one
    channel alone, as typing in the Item panel does. Without that setting, it
    goes along the object's own turned axis."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    mesh.parent = None
    mesh.rotation_euler = (0.0, 0.0, math.radians(90))
    mesh.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    region = core.new_region(mesh, "R", whole=True)
    up = region.buttons[0].up
    up.enabled, up.kind, up.axis = True, "MOVE", "X"
    ch = core.Channel(up, mesh, region)
    core.apply([ch], [1.0])
    assert abs(mesh.location.y - 1.0) < 1e-6 and abs(mesh.location.x) < 1e-6, tuple(mesh.location)
    ch.restore()
    up.along_parent = True
    ch = core.Channel(up, mesh, region)
    core.apply([ch], [1.0])
    assert abs(mesh.location.x - 1.0) < 1e-6 and abs(mesh.location.y) < 1e-6, tuple(mesh.location)
    # the handle points along the channel too
    placed = rigs.module("placed")
    d, _lever = placed._command_direction(mesh, up, mesh.matrix_world.translation)
    assert (d - Vector((1.0, 0.0, 0.0))).length < 1e-6, d


def test_nearest_handle_takes_the_press():
    """When several handles are hit at once, the press goes to the one whose
    shape is nearest the mouse (handle_distance), not the last in the list.
    The case is an arrow through a ring, as Digit's Move arrows and roll ring
    meet at a finger's knuckle: the ring used to take every press on the
    arrow's shaft inside it."""
    core = rigs.kneady()
    rim = [Vector((10.0 * math.cos(t), 10.0 * math.sin(t))) for t in (2 * math.pi * k / 24 for k in range(25))]
    ring = dict(rim=rim, reach=4.0, live=True)
    arrow = dict(parts=[dict(shaft=(Vector((0.0, 0.0)), Vector((0.0, 20.0))), heads=[], live=True)], reach=4.0,
                 live=True, base=Vector((0.0, 0.0)), tip=Vector((0.0, 20.0)))
    on_shaft = Vector((0.5, 8.0))                        # on the arrow, 2 px inside the rim
    assert core.handle_hit(ring, on_shaft) and core.handle_hit(arrow, on_shaft)
    assert core.handle_distance(arrow, on_shaft) < core.handle_distance(ring, on_shaft)
    on_rim = Vector((10.0, 0.0))
    assert core.handle_distance(ring, on_rim) < 1e-6 and not core.handle_hit(arrow, on_rim)


def test_handle_shapes_sizes_and_colors():
    """Handle shapes, sizes and colors:

    - an Arrow or a Box, Short, Medium, Long or Extra Long, starting from its
      place or Centered on it. Greg asked for "3 single arrow types that are
      short, medium and long shaft", then for "the current long arrows to be
      called extra long and make a new size between medium and extra long
      called long. Also we need the same variants but for the box"
    - a handle's own Size and color
    - the scene's Handle Size, set apart from Button Size
    """
    core = rigs.kneady()
    placed = rigs.module("placed")
    props = rigs.module("props")
    shapes = {key for key, _n, _d, _k in props.HANDLE_SHAPES}
    assert {"ARROW", "BOX"} <= shapes and not shapes & set(props.LEGACY_SHAPE_NAMES), shapes
    numbers = [k for _key, _n, _d, k in props.HANDLE_SHAPES]
    assert len(set(numbers)) == len(numbers) and not set(numbers) & set(props.LEGACY_SHAPES), numbers
    head = placed.ARROW_HEAD_LENGTH
    short, medium, long_, extra = (placed.handle_length("ARROW", k) for k in ("SHORT", "MEDIUM", "LONG",
                                                                              "EXTRA_LONG"))
    assert abs(short - placed.ARROW_LENGTH) < 1e-9, "a Short arrow is not as it was"
    assert abs((medium - head) - 2.0 * (short - head)) < 1e-9, "the Medium's shaft is not twice the Short's"
    assert medium < long_ < extra, (medium, long_, extra)
    assert abs(0.5 * extra - medium) < 1e-9, "Extra Long, centered, does not reach a Medium's tip"
    for k in ("SHORT", "MEDIUM", "LONG", "EXTRA_LONG"):
        assert abs(placed.handle_length("BOX", k) - placed.handle_length("ARROW", k) - placed.BOX_EXTRA) < 1e-9
    assert abs(placed.handle_length("BOX", "SHORT") - 2.6) < 1e-9, "a Short Box is not as the Box was"
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    b = region.buttons[0]
    assert b.handle_size == 1.0 and not b.handle_use_color and b.handle_length == "SHORT" and not b.handle_centered
    scene = bpy.context.scene
    scene.kneady_button_radius = 14.0
    scene.kneady_handle_radius = 28.0
    assert core.handle_radius(bpy.context) == 2.0 * core.button_radius(bpy.context)
    scene.kneady_handle_radius = core.BUTTON_RADIUS


def test_lengths_that_were_shapes():
    """For a few hours the lengths were shapes of their own, stored as 6
    (Medium), 7 (Long, centered) and 8 (Long). A region saved then is made an
    Arrow of that Length on load (data version 2), the Long ones becoming
    Extra Long. Copied settings that name those shapes are read the same
    way."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    region.button_count = 4
    for b, stored in zip(region.buttons, (6, 7, 8, 5)):
        b["handle_shape"] = stored
    region.version = 1
    assert core.migrate(region)
    got = [(b.handle_shape, b.handle_length, b.handle_centered) for b in region.buttons[:4]]
    assert got == [("ARROW", "MEDIUM", False), ("ARROW", "EXTRA_LONG", True), ("ARROW", "EXTRA_LONG", False),
                   ("BOX", "SHORT", False)], got
    assert region.version == core.DATA_VERSION == 2
    b = region.buttons[0]
    data = core.to_data(b)
    data["handle_shape"] = "ARROW_LONG_CENTERED"
    data.pop("handle_length")
    data.pop("handle_centered")
    core.from_data(region.buttons[3], data)
    b3 = region.buttons[3]
    assert (b3.handle_shape, b3.handle_length, b3.handle_centered) == ("ARROW", "EXTRA_LONG", True)


def test_handle_interior_color():
    """A handle's interior color (Greg: "need interior color for the
    handles"). It is dark unless set. Once set, it is that color, brighter
    under the mouse."""
    rigs.kneady()
    draw = rigs.module("draw")
    edge = (1.0, 0.2, 0.3)
    body, _edge = draw._colors(edge, False, False, 1.0)
    assert max(body[:3]) < 0.1, body
    body, _edge = draw._colors(edge, False, False, 1.0, (0.2, 0.4, 0.9))
    assert tuple(round(v, 6) for v in body[:3]) == (0.2, 0.4, 0.9), body
    under, white = draw._colors(edge, True, False, 1.0, (0.2, 0.4, 0.9))
    assert under[2] > 0.9 and under[0] > 0.2 and white[:3] == (1.0, 1.0, 1.0), (under, white)
    _rig, mesh = rigs.arm_rig()
    region = rigs.kneady().new_region(mesh, "R", whole=True)
    assert not region.buttons[0].handle_use_fill


def test_handle_opacity_and_thinner_shafts():
    """A handle's own Opacity (Greg: "Opacity would be an additional useful
    setting for the handles"), fully opaque by default. Shafts are a fifth
    thinner than they were (Greg: "make the shafts thinner for the handles.
    About 20% thinner")."""
    core = rigs.kneady()
    placed = rigs.module("placed")
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    assert region.buttons[0].handle_opacity == 1.0
    # then thinner by about 30% twice ("Make the shafts thinner again",
    # "another 30% thinner"); then a solid line half as wide as that shaft
    # with its 2 px outline at the default size ("make the shafts 50%
    # thinner"); then a quarter wider ("let's try 25% thicker")
    was = 0.7 * 0.7 * 0.8 * 0.42 + 2.0 / core.BUTTON_RADIUS
    assert abs(placed.ARROW_SHAFT - 1.25 * 0.5 * was) < 0.01, placed.ARROW_SHAFT


def test_handle_shaft_falloff():
    """A handle's Shaft Falloff (Greg: "I'm curious how a gradient falloff
    would look for the shafts", "along it's length, starting at middle").
    None by default. With it, the shaft is solid near the head and eases down
    toward the root; on a double arrow, each half fades toward the middle.
    The fade begins three quarters of the way along (Greg: "a bit closer to
    the end of the shaft")."""
    from mathutils import Vector
    core = rigs.kneady()
    placed = rigs.module("placed")
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    b = region.buttons[0]
    assert b.handle_shaft_falloff == 0.0
    assert "handle_shaft_falloff" in core.to_data(b)            # copied and in presets, as the rest
    root, head = Vector((0.0, 0.0)), Vector((100.0, 0.0))
    assert placed.shaft_fade(root, head, 0.0) == [[(root, 1.0), (head, 1.0)]]
    for falloff in (0.5, 1.0):
        (strip,) = placed.shaft_fade(root, head, falloff)
        at = [(p.x, k) for p, k in strip]
        assert at[0] == (0.0, 1.0 - falloff) and at[-1] == (100.0, 1.0), at
        assert placed.SHAFT_FADE_FROM == 0.75
        assert all(k == 1.0 for x, k in at if x >= 75.0), at
        assert any(k < 1.0 for x, k in at if x >= 50.0), at        # no longer solid from the middle
        ks = [k for _x, k in at]
        assert ks == sorted(ks), at                                 # never brighter toward the root
    halves = placed.shaft_fade(root, head, 1.0, double=True)
    assert len(halves) == 2
    for strip in halves:
        assert strip[0][0] == Vector((50.0, 0.0)) and strip[0][1] == 0.0, strip[0]
        assert strip[-1][1] == 1.0 and strip[-1][0] in (root, head), strip[-1]


def test_handle_behind():
    """A handle's own Behind setting (Greg: "Let's have the ghost behind
    option available for handles"), or its region's: what the handle does
    where anything is in front of it."""
    core = rigs.kneady()
    placed = rigs.module("placed")
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    b = region.buttons[0]
    assert b.handle_behind == "REGION"
    for behind, mode in (("NONE", "SHOW"), ("HIDE", "HIDE"), ("GHOST", "GHOST")):
        region.behind = behind
        assert placed.handle_behind(region, b) == mode, (behind, placed.handle_behind(region, b))
    b.handle_behind = "GHOST"
    region.behind = "HIDE"
    assert placed.handle_behind(region, b) == "GHOST"


def test_handle_interior_transparent():
    """A handle's Interior Opacity (Greg: "Could there be an option for the
    interior to be transparent?"). At 0 its interior is gone and its edge is
    as it was, whether the interior is its own color or the dark one,
    hovered or not."""
    core = rigs.kneady()
    draw = rigs.module("draw")
    edge_color = (1.0, 0.2, 0.3)
    for fill in (None, (0.2, 0.4, 0.9)):
        for under in (False, True):
            full, edge = draw._colors(edge_color, under, False, 1.0, fill)
            clear, edge0 = draw._colors(edge_color, under, False, 1.0, fill, 0.0)
            half, _e = draw._colors(edge_color, under, False, 1.0, fill, 0.5)
            assert clear[3] == 0.0 and edge0 == edge and full[3] > 0.9, (fill, under, clear, edge0, edge)
            assert abs(half[3] - 0.5 * full[3]) < 1e-9
    _rig, mesh = rigs.arm_rig()
    assert core.new_region(mesh, "R", whole=True).buttons[0].handle_fill_alpha == 1.0


def test_handle_hover_color():
    """A handle's own Hover Color (Greg: "I'd like to be able to change the
    hover color for handles"):

    - under the mouse, the handle is filled with it and edged a lighter
      shade, and keeps that edge even with a transparent interior
    - not under the mouse, it looks as it did
    - without a Hover Color, a hovered handle is brighter and white-edged
    """
    core = rigs.kneady()
    draw = rigs.module("draw")
    edge_color, hover = (1.0, 0.2, 0.3), (0.2, 0.5, 1.0)
    body, edge = draw._colors(edge_color, True, False, 1.0, None, 1.0, hover)
    assert tuple(round(v, 6) for v in body[:3]) == hover and edge[:3] != (1.0, 1.0, 1.0), (body, edge)
    assert edge[2] >= hover[2] and edge[0] > hover[0], edge
    clear, edge0 = draw._colors(edge_color, True, False, 1.0, None, 0.0, hover)
    assert clear[3] == 0.0 and edge0 == edge, "a transparent interior lost the hover edge"
    calm = draw._colors(edge_color, False, False, 1.0, None, 1.0, hover)
    assert calm == draw._colors(edge_color, False, False, 1.0), "the hover color showed off the mouse"
    _body, white = draw._colors(edge_color, True, False, 1.0)
    assert white[:3] == (1.0, 1.0, 1.0)
    _rig, mesh = rigs.arm_rig()
    assert not core.new_region(mesh, "R", whole=True).buttons[0].handle_use_hover


def test_faded_shaft_and_bigger_heads_take_the_press():
    """A faded shaft takes a press only where it shows (Greg agreed to "when
    falloff is on, only the visible part of the shaft should grab"). It grabs
    from where it is drawn at SHAFT_GRAB_SHOWS opacity up to the head. If it
    never fades that far, the whole shaft grabs. On a double arrow, each half
    stops short of the middle. A head also takes a press a few pixels past
    its outline (Greg: "Go for it on target size"), while it is drawn as it
    was."""
    core = rigs.kneady()
    placed = rigs.module("placed")
    root, head = Vector((0.0, 0.0)), Vector((100.0, 0.0))
    assert placed.shaft_grab(root, head, 0.0) == [(root, head)]
    assert placed.shaft_grab(root, head, 1.0 - placed.SHAFT_GRAB_SHOWS) == [(root, head)]
    ((a, b),) = placed.shaft_grab(root, head, 1.0)
    assert b == head and 0.0 < a.x < 100.0 * placed.SHAFT_FADE_FROM, a
    # where it starts is drawn at SHAFT_GRAB_SHOWS, as the fade has it
    (strip,) = placed.shaft_fade(root, head, 1.0, steps=2000)
    shows = min(strip, key=lambda pk: abs(pk[0].x - a.x))[1]
    assert abs(shows - placed.SHAFT_GRAB_SHOWS) < 1e-3, shows
    halves = placed.shaft_grab(root, head, 1.0, double=True)
    assert len(halves) == 2 and all(abs(p.x - 50.0) > 1.0 for p, _q in halves), halves
    box = [Vector((96.0, -4.0)), Vector((104.0, -4.0)), Vector((104.0, 4.0)), Vector((96.0, 4.0))]
    handle = dict(parts=[dict(shaft=(root, head), grab=placed.shaft_grab(root, head, 1.0), heads=[box], live=True)],
                  reach=3.0, head_reach=placed.HEAD_REACH, live=True, base=root, tip=head)
    assert not core.handle_hit(handle, Vector((5.0, 1.0))), "the faded root took the press"
    assert core.handle_hit(handle, Vector((80.0, 1.0)))
    assert core.handle_hit(handle, Vector((107.0, 6.0))), "a few pixels off the box missed"
    assert not core.handle_hit(handle, Vector((112.0, 12.0)))
    assert core.handle_distance(handle, Vector((5.0, 0.0))) > 10.0


def test_handle_theme_axis_color():
    """A handle's own color can come from Blender's theme (Greg: "I like the
    idea of adopting from Blenders theme"): the X, Y or Z axis color the
    navigation gizmo shows. Otherwise it is the color set, or the list's
    color without Own Color."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    b = core.new_region(mesh, "R", whole=True).buttons[0]
    theme = bpy.context.preferences.themes[0].user_interface
    assert b.handle_color_from == "OWN"
    assert core.handle_color(b, (0.1, 0.2, 0.3)) == (0.1, 0.2, 0.3)
    b.handle_use_color, b.handle_color = True, (0.5, 0.25, 0.75)
    assert core.handle_color(b, None) == tuple(b.handle_color)
    for key, name in (("AXIS_X", "axis_x"), ("AXIS_Y", "axis_y"), ("AXIS_Z", "axis_z")):
        b.handle_color_from = key
        assert core.handle_color(b, None) == tuple(getattr(theme, name))[:3], key
    assert core.to_data(b)["handle_color_from"] == "AXIS_Z"
    # drawn as Blender's own gizmos draw them (Greg: "they don't look like the
    # default handles. They look lighter colored"): the color itself, not a
    # shade brighter, at THEME_ALPHA at rest and fully opaque under the mouse
    draw = rigs.module("draw")
    assert core.themed(b) and core.THEME_ALPHA == 0.6
    assert core.theme_alpha(b) == 0.6 and core.theme_alpha(b, under=True) == 1.0
    color = core.handle_color(b, None)
    _body, edge = draw._colors(color, False, False, 0.6, None, 1.0, None, exact=True)
    assert edge == (*color, 0.6), edge
    _body, brighter = draw._colors(color, False, False, 1.0)
    assert brighter[:3] != color, "an own color's edge is no longer a shade brighter"
    b.handle_color_from = "OWN"
    assert not core.themed(b) and core.theme_alpha(b) == 1.0
    b.handle_use_color = False
    b.handle_color_from = "AXIS_X"
    assert not core.themed(b), "a theme choice counted without Own Color"


def test_handle_halo():
    """A thin dark edge round the handles' lines (Greg: "Contrast against
    wireframe is a good idea"). Off by default; when on, HALO pixels wide on
    each side."""
    core = rigs.kneady()
    draw = rigs.module("draw")
    scene = bpy.context.scene
    assert not scene.kneady_handle_halo and core.handle_halo(bpy.context) == 0.0
    scene.kneady_handle_halo = True
    try:
        assert abs(core.handle_halo(bpy.context) - core.HALO * core.ui_scale(bpy.context)) < 1e-9
        assert draw._halo_of((1.0, 0.0, 0.0, 0.5))[:3] == (0.0, 0.0, 0.0)
        assert abs(draw._halo_of((1.0, 0.0, 0.0, 0.5))[3] - core.HALO_ALPHA * 0.5) < 1e-9
    finally:
        scene.kneady_handle_halo = False


SIDE_KEY = "test_side"


def _sides(core):
    """A program's drag for a ring's four sides, like Digit's: Alt moves both
    sides of an axis, Alt+Shift all four. It reports those keys (hints) and
    which other commands move with it (also)."""
    def begin(context, obj, command):
        return dict(obj=obj)

    def also(command, other, keys):
        if "ALT" not in keys:
            return False
        return "SHIFT" in keys or command.program_data[1] == other.program_data[1]

    core.add_command_kind(SIDE_KEY, "Side", summary=lambda command: "Side " + command.program_data,
                          drag=dict(motion=lambda obj, command, point: None, begin=begin,
                                    apply=lambda *a: None, restore=lambda *a: None,
                                    keys=lambda command: {"ALT", "SHIFT"},
                                    hints=lambda command: [(("ALT",), "Both sides"), (("ALT", "SHIFT"), "All four")],
                                    also=also))


def test_status_bar_hints_and_what_moves_with_a_drag():
    """The status bar shows what the mouse can do, with Blender's key icons:

    - on the region, a drag runs its first button
    - on a button, its drag, its click (opening a menu or going back from
      one) and Shift+click to pin
    - a program's own keys

    With keys held, the items they don't apply to dim and the one they put
    in effect stands out (hints.mark). The handles a drag would move with
    those keys light up along with the one under the mouse
    (core.moves_with): with Alt the other side of an axis, with Alt+Shift
    all four. Greg agreed to "With Alt held over a Side box, light its
    partner box as well; with Alt+Shift, light all four"."""
    core = rigs.kneady()
    hints = rigs.module("hints")
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    region.button_count = 5
    used = core.buttons_of(region)
    used[0].name = "Bend"
    _sides(core)
    try:
        for b, side in zip(used[1:], ("+X", "-X", "+Y", "-Y")):
            b.name = "Side " + side
            b.up.enabled, b.up.program, b.up.program_data = True, SIDE_KEY, side
            # 3D handles: a drag along them, no click (the status bar now
            # reads this from the button, as its tip does)
            b.placed, b.handle = True, "HANDLE"
        # on the faces: a drag runs the first button
        items = hints.hover_items(bpy.context, mesh, region, None)
        assert (("DRAG",), "Bend") in items, items
        # a 3D handle: its drag and its program's keys, Shift and Alt its own
        items = hints.hover_items(bpy.context, mesh, region, 1, handle=True)
        assert items[0] == (("DRAG",), "Side +X") and (("ALT",), "Both sides") in items, items
        assert (("ALT", "SHIFT"), "All four") in items and (("SHIFT",), "Fine") not in items, items
        assert (("CTRL",), "Snap") in items
        # a button in the row: Shift+click pins (worded as its tip words it)
        assert (("SHIFT", "LMB"), "Keep these controls up") in hints.hover_items(bpy.context, mesh, region, 0)
        # what stands out with keys held
        marked = dict(((k, t), dim) for k, t, dim in hints.mark(items, {"ALT"}))
        assert not marked[(("DRAG",), "Side +X")] and not marked[(("ALT",), "Both sides")]
        assert marked[(("ALT", "SHIFT"), "All four")] and marked[(("CTRL",), "Snap")]
        marked = dict(((k, t), dim) for k, t, dim in hints.mark(items, {"ALT", "SHIFT"}))
        assert marked[(("ALT",), "Both sides")] and not marked[(("ALT", "SHIFT"), "All four")]
        assert not any(dim for _k, _t, dim in hints.mark(items, set()))
        assert "Alt: Both sides" in hints.as_text(hints.mark(items, set()))
        # what moves with the drag
        assert core.moves_with(mesh, region, 1, set()) == frozenset()
        assert core.moves_with(mesh, region, 1, {"ALT"}) == {2}
        assert core.moves_with(mesh, region, 3, {"ALT"}) == {4}
        assert core.moves_with(mesh, region, 1, {"ALT", "SHIFT"}) == {2, 3, 4}
        assert core.moves_with(mesh, region, 0, {"ALT"}) == frozenset(), "a button with no program's drag"
    finally:
        core.remove_command_kind(SIDE_KEY)
