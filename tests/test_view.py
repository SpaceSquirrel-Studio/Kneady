"""View and Depth: a Move or Rotate along the view, not the target's own
axes. A View move follows the mouse across and up the screen as G does, and a
View turn rolls the target as pressing R twice does. Depth moves it toward or
away from you, or rolls it about the line of sight. Blender's transform locks
hold."""

import math

import bpy  # type: ignore
from mathutils import Euler, Vector  # type: ignore

import rigs

# the Front view: right is +X, up +Z, the viewer at -Y looking toward +Y
FRONT = Euler((math.radians(90.0), 0.0, 0.0)).to_quaternion()


def _command(button, kind, axis, rig, bone, direction="up"):
    drag = getattr(button, direction)
    drag.enabled, drag.kind, drag.axis, drag.target, drag.bone = True, kind, axis, rig, bone
    return drag


def _rig():
    """The arm rig turned and its Upper bone posed, so the bone's own axes
    are nothing like the view's."""
    rig, mesh = rigs.arm_rig()
    rig.rotation_euler = (0.3, 0.0, 0.7)
    upper = rig.pose.bones["Upper"]
    upper.rotation_mode = "XYZ"
    upper.rotation_euler = (0.4, 0.2, -0.3)
    bpy.context.view_layer.update()
    return rig, mesh, upper


def _head(rig, pb):
    bpy.context.view_layer.update()
    return (rig.matrix_world @ pb.matrix).translation.copy()


def _channel(drag, mesh, screen_axis, per_pixel=None):
    core = rigs.kneady()
    ch = core.Channel(drag, mesh)
    assert ch.ok, ch.why
    ch.use_view(screen_axis, FRONT, per_pixel)
    return ch


def test_view_move_follows_the_screen():
    """A View move goes right for a drag across and up for a drag up, in the
    world, whatever way the bone faces. It follows the mouse, moving a
    pixel's worth of scene units for each pixel, whatever its Speed."""
    core = rigs.kneady()
    rig, mesh, upper = _rig()
    region = core.new_region(mesh, "R", whole=True)
    button = region.buttons[0]
    for direction, screen_axis, world in (("up", 1, Vector((0, 0, 1))), ("across", 0, Vector((1, 0, 0)))):
        drag = _command(button, "MOVE", "VIEW", rig, "Upper", direction)
        drag.rate = 5.0                                   # ignored: it follows the mouse
        start = _head(rig, upper)
        ch = _channel(drag, mesh, screen_axis, per_pixel=0.002)
        core.apply([ch], [core.amount_for(ch, 100.0, core.sign_for(ch, screen_axis, None, None, None))])
        moved = _head(rig, upper) - start
        assert (moved - world * 0.2).length < 1e-4, "%s: moved %s, not %s" % (direction, moved, world * 0.2)
        ch.restore()


def test_depth_move_goes_away_from_you():
    core = rigs.kneady()
    rig, mesh, upper = _rig()
    region = core.new_region(mesh, "R", whole=True)
    drag = _command(region.buttons[0], "MOVE", "DEPTH", rig, "Upper")
    start = _head(rig, upper)
    ch = _channel(drag, mesh, 1, per_pixel=0.001)
    core.apply([ch], [core.amount_for(ch, 50.0, 1.0)])
    moved = _head(rig, upper) - start
    assert (moved - Vector((0.0, 0.05, 0.0))).length < 1e-4, "moved %s" % moved


def test_view_turn_rolls_the_front_with_the_mouse():
    """A View turn across swings the bone about the view's up (its tail goes
    right), and a View turn up swings it about the view's right (its tail
    goes up). Depth rolls it about the line of sight. Each turns by the angle
    asked, in the world."""
    core = rigs.kneady()
    rig, mesh, upper = _rig()
    region = core.new_region(mesh, "R", whole=True)
    button = region.buttons[0]
    for axis, screen_axis, about in (("VIEW", 0, Vector((0, 0, 1))), ("VIEW", 1, Vector((-1, 0, 0))),
                                     ("DEPTH", 0, Vector((0, 1, 0)))):
        drag = _command(button, "ROTATE", axis, rig, "Upper")
        bpy.context.view_layer.update()
        before = (rig.matrix_world @ upper.matrix).to_3x3().normalized()
        ch = _channel(drag, mesh, screen_axis)
        core.apply([ch], [math.radians(30.0)])
        bpy.context.view_layer.update()
        after = (rig.matrix_world @ upper.matrix).to_3x3().normalized()
        turn = (after @ before.inverted()).to_quaternion()
        got_axis, got_angle = turn.to_axis_angle()
        assert abs(math.degrees(got_angle) - 30.0) < 0.05 and (got_axis - about).length < 1e-3, \
            "%s %d: turned %.2f degrees about %s, not 30 about %s" % (axis, screen_axis, math.degrees(got_angle),
                                                                   got_axis, about)
        ch.restore()


def test_view_move_holds_locked_axes():
    """A View move crosses every axis of the bone's own. A locked axis stays
    where it was, as Blender's tools leave it, and a move with all three
    locked is refused."""
    core = rigs.kneady()
    rig, mesh, upper = _rig()
    region = core.new_region(mesh, "R", whole=True)
    drag = _command(region.buttons[0], "MOVE", "VIEW", rig, "Upper")
    upper.lock_location = (False, True, False)
    ch = _channel(drag, mesh, 1, per_pixel=0.002)
    core.apply([ch], [0.2])
    assert abs(upper.location.y) < 1e-9 and upper.location.length > 1e-3, tuple(upper.location)
    ch.restore()
    upper.lock_location = (True, True, True)
    assert not core.Channel(drag, mesh).ok, "a move with every axis locked ran"


def test_view_labels():
    core = rigs.kneady()
    rig, mesh, _upper = _rig()
    region = core.new_region(mesh, "R", whole=True)
    drag = _command(region.buttons[0], "MOVE", "VIEW", rig, "Upper")
    assert "in the view" in core.Channel(drag, mesh).label()
    drag.kind, drag.axis = "ROTATE", "DEPTH"
    assert core.Channel(drag, mesh).label().startswith("roll")
