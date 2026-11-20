"""Numeric values. Greg asked for "a numeric control popping up after
hauling on Kneady controls ... so that you could see what's being modified
and enter a number in instead of continuing to haul". Each command shows
what the drag made of it in its own terms. A number typed for one command
works out the drag that gives it, and the direction's other commands follow
that drag."""

import math

import bpy  # type: ignore

import rigs


def _two_bone_button(mesh, rig):
    """A region whose drag up turns both bones about X: one direction with two
    commands, as in a curl."""
    region = rigs.turn_button(mesh, rig, "Upper")
    up = region.buttons[0].up
    more = up.more.add()
    more.kind, more.axis, more.target, more.bone = "ROTATE", "X", rig, "Lower"
    more.turn_rate = up.turn_rate * 0.5
    return region


def test_round_trips():
    """A value shown for a drag, and the drag worked out from that value,
    agree for a turn, a scale, an added value and a multiplied one."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    mesh["Bulge"] = 2.0
    up = region.buttons[0].up
    cases = []
    turn = core.Channel(up, mesh, region)
    cases.append(("turn", turn, 37.5))
    across = region.buttons[0].across
    across.enabled, across.kind, across.data_path, across.rate = True, "PROPERTY", '["Bulge"]', 0.5
    added = core.Channel(across, mesh, region)
    cases.append(("added", added, 3.25))
    across.multiply = True
    multiplied = core.Channel(across, mesh, region)
    cases.append(("multiplied", multiplied, 5.0))
    for name, ch, value in cases:
        assert ch.ok, "%s: %s" % (name, ch.why)
        for sign in (1.0, -1.0):
            px = core.pixels_for(ch, core.amount_from_display(ch, value), sign)
            shown = core.display_value(ch, core.amount_for(ch, px, sign))
            assert abs(shown - value) < 1e-6, "%s (sign %d): typed %.4f, shows %.4f" % (name, sign, value, shown)
    across.multiply = False


def test_redo_panel_value_works_out_the_drag():
    """Typing 45 degrees for the first of two commands on one direction turns
    it to 45, and the second, at half the speed, to 22.5. Both move by one
    drag, so they keep their relation."""
    rig, mesh = rigs.arm_rig()
    region = _two_bone_button(mesh, rig)
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=50.0)
    first, second = rigs.angle_of(rig.pose.bones["Upper"]), rigs.angle_of(rig.pose.bones["Lower"])
    assert abs(second - first / 2.0) < 1e-4, "dragged: %.3f and %.3f" % (first, second)
    for name in ("Upper", "Lower"):
        rig.pose.bones[name].rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    # as the redo panel does: the operator run again with what it showed, one
    # value typed over
    values = [0.0] * rigs.kneady().props.MAX_COMMANDS
    values[0], values[1] = first, second
    values[0] = 45.0
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=50.0, up_values=values, values_set=True)
    upper, lower = rigs.angle_of(rig.pose.bones["Upper"]), rigs.angle_of(rig.pose.bones["Lower"])
    assert abs(upper - 45.0) < 1e-3 and abs(lower - 22.5) < 1e-3, "typed 45: %.3f and %.3f" % (upper, lower)


def test_a_typed_property_value():
    """A property typed to 0.8 is 0.8."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    mesh["Bulge"] = 0.2
    region = core.new_region(mesh, "P", whole=True)
    up = region.buttons[0].up
    up.enabled, up.kind, up.data_path = True, "PROPERTY", '["Bulge"]'
    region.buttons[0].across.enabled = False
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=30.0)
    mesh["Bulge"] = 0.2
    values = [0.0] * rigs.kneady().props.MAX_COMMANDS
    values[0] = 0.8
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=30.0, up_values=values, values_set=True)
    assert abs(mesh["Bulge"] - 0.8) < 1e-6, "typed 0.8, got %.4f" % mesh["Bulge"]


def test_both_directions_drive_one_value():
    """A value on both directions of a button follows whichever is dragged,
    and both when both are. Greg put the same commands on left / right and
    up / down, to scale "either way". Before this, each direction wrote the
    value from its start, so the direction not being dragged put it back."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "P", whole=True)
    button = region.buttons[0]
    for d in (button.across, button.up):
        d.enabled, d.kind, d.data_path, d.rate, d.multiply = True, "PROPERTY", '["Bulge"]', 1.0, False
    for across, up, want in ((50.0, 0.0, 1.5), (0.0, 50.0, 1.5), (50.0, 20.0, 1.7)):
        mesh["Bulge"] = 1.0
        bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, across=across, up=up)
        assert abs(mesh["Bulge"] - want) < 1e-6, "added, across %g up %g: %.4f, not %.4f" % (
            across, up, mesh["Bulge"], want)
    for d in (button.across, button.up):
        d.multiply = True
    for across, up in ((50.0, 0.0), (0.0, 50.0), (50.0, 20.0)):
        mesh["Bulge"] = 2.0
        bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, across=across, up=up)
        want = 2.0 * math.exp((across + up) / 100.0)
        assert abs(mesh["Bulge"] - want) < 1e-5, "multiplied, across %g up %g: %.4f, not %.4f" % (
            across, up, mesh["Bulge"], want)
