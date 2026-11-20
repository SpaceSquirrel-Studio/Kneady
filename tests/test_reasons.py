"""Plain reasons. When a drag cannot move what a command drives (a driver
would put it straight back, say), the command says why instead of doing
nothing. When something else holds the result, the drag still writes the
channel and says what holds it."""

import bpy  # type: ignore

import rigs


def _channel(mesh, region, which="up"):
    core = rigs.kneady()
    return core.Channel(getattr(region.buttons[0], which), mesh, region)


def test_a_driven_bone_says_so():
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    fc = rig.pose.bones["Lower"].driver_add("rotation_quaternion", 1)
    fc.driver.expression = "0.0"
    ch = _channel(mesh, region)
    assert not ch.ok and "driver" in ch.why, "a driven bone: ok %s, %r" % (ch.ok, ch.why)
    fc.mute = True
    ch = _channel(mesh, region)
    assert ch.ok, "a muted driver still blocked it: %r" % ch.why


def test_a_driven_property_says_so():
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    mesh["Bulge"] = 0.0
    region = core.new_region(mesh, "P", whole=True)
    up = region.buttons[0].up
    up.enabled, up.kind, up.data_path = True, "PROPERTY", '["Bulge"]'
    mesh.driver_add('["Bulge"]').driver.expression = "1.0"
    ch = _channel(mesh, region)
    assert not ch.ok and "driver" in ch.why, "a driven property: ok %s, %r" % (ch.ok, ch.why)


def test_a_constraint_is_named_but_the_drag_writes():
    """A Copy Rotation on the bone holds the result. The drag still turns the
    channel (worth setting beneath the constraint) and names what holds
    it."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    c = rig.pose.bones["Lower"].constraints.new("COPY_ROTATION")
    c.target = rig
    c.subtarget = "Upper"
    ch = _channel(mesh, region)
    assert ch.ok and ch.note and c.name in ch.note, "ok %s, note %r" % (ch.ok, ch.note)
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=60.0)
    assert rigs.angle_of(rig.pose.bones["Lower"]) > 1.0, "the channel was not written"


def test_an_ik_chain_is_named():
    """A bone on an IK's chain: the IK holds its turn."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Upper")
    target = bpy.data.objects.new("Target", None)
    bpy.context.scene.collection.objects.link(target)
    ik = rig.pose.bones["Lower"].constraints.new("IK")
    ik.target = target
    ik.chain_count = 2
    ch = _channel(mesh, region)
    assert ch.ok and ch.note and ik.name in ch.note, "Upper under IK: ok %s, note %r" % (ch.ok, ch.note)
    ik.chain_count = 1
    ch = _channel(mesh, region)
    assert ch.ok and not ch.note, "Upper outside a one-bone chain still noted: %r" % ch.note
