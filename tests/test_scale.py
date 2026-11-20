"""The interface scale: Blender's Resolution Scale times the display's own,
which is 2 on a Retina or 4K screen. Every size Kneady gives in pixels is
for a scale of 1 and is multiplied by it, and a drag's speed is divided by
it, so Kneady looks and feels the same on any screen."""

import contextlib

import bpy  # type: ignore

import rigs


@contextlib.contextmanager
def _resolution_scale(value):
    view = bpy.context.preferences.view
    saved = view.ui_scale
    view.ui_scale = value
    try:
        yield
    finally:
        view.ui_scale = saved


def test_sizes_follow_the_interface_scale():
    core = rigs.kneady()
    one = core.button_radius()
    with _resolution_scale(2.0):
        two = core.button_radius()
        assert abs(core.ui_scale() - 2.0) < 1e-6, "interface scale %.2f" % core.ui_scale()
    assert abs(two - 2.0 * one) < 1e-6, "radius %.1f at 2, %.1f at 1" % (two, one)
    # the band that holds a hover: twice as wide, so a point twice as far
    # out is in it, or not, as at 1
    from mathutils import Vector  # type: ignore
    circles = [(0, Vector((0.0, 0.0)))]
    inside = Vector((one + core.BUTTON_BLOCK * 0.5, 0.0))
    outside = Vector((one + core.BUTTON_BLOCK * 1.5, 0.0))
    assert core.in_block(circles, inside, one, 1.0) and not core.in_block(circles, outside, one, 1.0), \
        "the band at 1"
    assert core.in_block(circles, inside * 2.0, two, 2.0) and not core.in_block(circles, outside * 2.0, two, 2.0), \
        "the band at 2 is not the band at 1, doubled"
    # Drags Prefer Single Direction decides after twice the pixels
    assert core.lock_axis((8.0, 0.0), 1.0) == 0 and core.lock_axis((8.0, 0.0), 2.0) is None, \
        "the direction decided at 8 pixels: %s, %s" % (core.lock_axis((8.0, 0.0), 1.0),
                                                       core.lock_axis((8.0, 0.0), 2.0))


def test_a_drag_moves_alike_on_any_screen():
    """The same drag by hand covers twice the pixels at scale 2, and turns
    the bone as far."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=60.0)
    at_one = rigs.angle_of(rig.pose.bones["Lower"])
    rig.pose.bones["Lower"].rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    with _resolution_scale(2.0):
        bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=120.0)
    at_two = rigs.angle_of(rig.pose.bones["Lower"])
    assert at_one > 1.0 and abs(at_two - at_one) < 1e-4, "%.3f degrees at 1, %.3f at 2" % (at_one, at_two)


def test_button_size_slides_from_small_to_large():
    """Button Size is a slider (Greg: "I'd like to slide between small and
    large"): any radius from Small to Large, Medium by default, held within
    the ends."""
    core = rigs.kneady()
    scene = bpy.context.scene
    assert abs(core.button_radius() - core.BUTTON_RADIUS) < 1e-6, "default %.1f" % core.button_radius()
    scene.kneady_button_radius = 17.5
    assert abs(core.button_radius() - 17.5) < 1e-6, "slid to 17.5, got %.2f" % core.button_radius()
    scene.kneady_button_radius = 99.0
    assert abs(scene.kneady_button_radius - core.BUTTON_RADIUS_MAX) < 1e-6, "past Large: %.1f" % (
        scene.kneady_button_radius)
    scene.kneady_button_radius = 1.0
    assert abs(scene.kneady_button_radius - core.BUTTON_RADIUS_MIN) < 1e-6, "below Small: %.1f" % (
        scene.kneady_button_radius)
    scene.kneady_button_radius = core.BUTTON_RADIUS
