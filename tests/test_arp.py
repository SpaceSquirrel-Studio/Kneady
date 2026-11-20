"""Auto-Rig Pro. These tests use the MPFB2 human rigged with Auto-Rig Pro
Lite by tests/make_arp_human.py, from the test assets, and are skipped where
that file is missing. It is opened with scripts off and without Auto-Rig Pro
itself: the rig's bones, constraints and drivers (208, all simple
expressions) run in Blender alone.

What the rig brings:
- an FK forearm that turns about Z only (X and Y locked);
- the switch ik_fk_switch on c_hand_ik.l;
- an FK / IK blend made through helper bones and constraints at zero
  strength."""

import bpy  # type: ignore
from mathutils import Matrix  # type: ignore

import rigs


def _open():
    rigs.open_asset("arp_human.blend")
    return bpy.data.objects["rig"], bpy.data.objects["Human"]


def _forearm_region(body):
    core = rigs.kneady()
    wanted = {g.index for g in body.vertex_groups if g.name in ("forearm_stretch.l", "forearm_twist.l")}
    on = {v.index for v in body.data.vertices if sum(g.weight for g in v.groups if g.group in wanted) > 0.5}
    faces = [p.index for p in body.data.polygons if all(i in on for i in p.vertices)]
    assert faces, "no forearm faces"
    region = core.new_region(body, "Forearm.L")
    core.tag_faces(body.data, faces, region.id)
    return region


def _hand_tip(body):
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    tip = max((ev.matrix_world @ v.co for v in me.vertices), key=lambda p: p.x)
    ev.to_mesh_clear()
    return tip


def _switch_to(rig, value):
    rig.pose.bones["c_hand_ik.l"]["ik_fk_switch"] = value
    rig.update_tag()
    bpy.context.view_layer.update()


def _fk_end(rig, body):
    """Which end of ik_fk_switch is FK: where turning c_forearm_fk.l about Z
    moves the hand."""
    core = rigs.kneady()
    pb = rig.pose.bones["c_forearm_fk.l"]
    for end in (0.0, 1.0):
        _switch_to(rig, end)
        before = _hand_tip(body)
        saved = core.rotation_of(pb)
        core.write_rotation(pb, saved @ Matrix.Rotation(0.6, 3, "Z"))
        bpy.context.view_layer.update()
        moved = (_hand_tip(body) - before).length
        core.write_rotation(pb, saved)
        bpy.context.view_layer.update()
        if moved > 0.01:
            return end
    raise AssertionError("turning c_forearm_fk.l moves the hand at neither end of ik_fk_switch")


def test_arp_locked_axes_say_so():
    core = rigs.kneady()
    rig, body = _open()
    region = _forearm_region(body)
    up = region.buttons[0].up
    up.enabled, up.kind, up.axis, up.target, up.bone = True, "ROTATE", "X", rig, "c_forearm_fk.l"
    ch = core.Channel(up, body, region)
    assert not ch.ok and "locked" in ch.why, "about X: ok %s, %r" % (ch.ok, ch.why)


def test_arp_switch_fk_and_ik():
    """Dragging the switch past FK holds it at its FK end. In FK, a drag bends
    the forearm about Z. Back in IK, moving c_hand_ik.l moves the hand."""
    rig, body = _open()
    region = _forearm_region(body)
    button = region.buttons[0]
    button.up.enabled, button.up.kind, button.up.axis = True, "ROTATE", "Z"
    button.up.target, button.up.bone = rig, "c_forearm_fk.l"
    button.across.enabled, button.across.kind, button.across.target = True, "PROPERTY", rig
    button.across.data_path = 'pose.bones["c_hand_ik.l"]["ik_fk_switch"]'
    fk = _fk_end(rig, body)
    ik = 1.0 - fk
    _switch_to(rig, ik)
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, across=4000.0 * (1 if fk > ik else -1))
    value = rig.pose.bones["c_hand_ik.l"]["ik_fk_switch"]
    assert abs(value - fk) < 1e-6, "the switch dragged to %r, not %r" % (value, fk)
    bpy.context.view_layer.update()
    before = _hand_tip(body)
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0)
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "in FK the hand moved %.4f m" % moved
    _switch_to(rig, ik)
    button.across.enabled = False
    button.up.kind, button.up.axis, button.up.bone = "MOVE", "Y", "c_hand_ik.l"
    bpy.context.view_layer.update()
    before = _hand_tip(body)
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0)
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "moving c_hand_ik.l moved the hand %.4f m" % moved


def test_arp_nothing_moved_is_seen():
    """Auto-Rig Pro's FK forearm while the arm is in IK. No constraint on the
    forearm, or on what follows it, shows that turning it does nothing, so the
    drag has to look: the body sampled before and after shows nothing moved.
    In FK the same drag moves it."""
    core = rigs.kneady()
    rig, body = _open()
    region = _forearm_region(body)
    up = region.buttons[0].up
    up.enabled, up.kind, up.axis, up.target, up.bone = True, "ROTATE", "Z", rig, "c_forearm_fk.l"
    region.buttons[0].across.enabled = False
    fk = _fk_end(rig, body)
    for end, still in ((1.0 - fk, True), (fk, False)):
        _switch_to(rig, end)
        before = core.surface_sample(body, bpy.context.evaluated_depsgraph_get())
        bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0)
        moved = core.moved_since(before, core.surface_sample(body, bpy.context.evaluated_depsgraph_get()))
        assert (moved < 1e-6) == still, "switch at %.0f: the body moved %.5f m" % (end, moved)
        bpy.ops.ed.undo_push(message="test")
