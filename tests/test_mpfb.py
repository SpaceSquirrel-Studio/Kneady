"""MPFB2 humans, made by tests/make_mpfb_human.py into the test assets. The
tests are skipped where the assets are missing. There are two rigs:
- MPFB2's own standard rig (137 bones, Euler XYZ);
- a Rigify rig (930 bones), since Rigify is the rig most Blender animators
  use.
Both bodies carry shape keys and an Armature and Mask modifier stack."""

import bpy  # type: ignore

import rigs


def _open(name):
    rigs.open_asset(name, newer_ok=True)
    body = bpy.data.objects["Human"]
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "metarig" not in o.name)
    return rig, body


def _region_on(body, groups, name):
    """A region of the body's faces weighted mostly to `groups`."""
    core = rigs.kneady()
    wanted = {g.index for g in body.vertex_groups if g.name in groups}
    on = {v.index for v in body.data.vertices if sum(g.weight for g in v.groups if g.group in wanted) > 0.5}
    faces = [p.index for p in body.data.polygons if all(i in on for i in p.vertices)]
    assert faces, "no faces on %s" % (groups,)
    region = core.new_region(body, name)
    core.tag_faces(body.data, faces, region.id)
    for d in (region.buttons[0].up, region.buttons[0].across):
        d.enabled = False
    return region


def _set(drag, kind, target=None, bone="", axis="X", data_path=""):
    drag.enabled, drag.kind, drag.axis = True, kind, axis
    drag.target, drag.bone, drag.data_path = target, bone, data_path


def _hand_tip(body):
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    tip = max((ev.matrix_world @ v.co for v in me.vertices), key=lambda p: p.x)
    ev.to_mesh_clear()
    return tip


def test_mpfb_standard_rig_bends_the_arm():
    rig, body = _open("mpfb_human.blend")
    region = _region_on(body, ("lowerarm01.L", "lowerarm02.L"), "Forearm.L")
    _set(region.buttons[0].up, "ROTATE", rig, "lowerarm01.L", "X")
    before = _hand_tip(body)
    assert bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0) == {"FINISHED"}
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "the hand moved %.4f m" % moved


def test_mpfb_shape_key_within_its_range():
    """A property command on a shape key: a long drag stops at the key's own
    slider maximum, 1."""
    rig, body = _open("mpfb_human.blend")
    keys = body.data.shape_keys.key_blocks
    name = next(k.name for k in keys if k.name != "Basis")
    region = _region_on(body, ("lowerarm01.L", "lowerarm02.L"), "Shape")
    path = 'data.shape_keys.key_blocks["%s"].value' % name
    _set(region.buttons[0].up, "PROPERTY", data_path=path)
    keys[name].value = 0.2
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=3000.0)
    value = keys[name].value
    assert abs(value - keys[name].slider_max) < 1e-6, "the key went to %.3f, its maximum %.3f" % (
        value, keys[name].slider_max)


def _switch_to(rig, switch, value):
    """Set Rigify's IK_FK switch the way a person's edit would. A custom
    property written from Python does not tell the depsgraph by itself, so
    its drivers would not run again. This is the same trap Kneady's own
    writes guard against."""
    switch["IK_FK"] = value
    rig.update_tag()
    bpy.context.view_layer.update()


def _fk_end(rig, body, switch):
    """Which end of Rigify's IK_FK is FK: where turning forearm_fk.L moves the
    hand."""
    from mathutils import Matrix  # type: ignore
    core = rigs.kneady()
    pb = rig.pose.bones["forearm_fk.L"]
    for end in (0.0, 1.0):
        _switch_to(rig, switch, end)
        before = _hand_tip(body)
        saved = core.rotation_of(pb)
        core.write_rotation(pb, saved @ Matrix.Rotation(0.6, 3, "X"))
        bpy.context.view_layer.update()
        moved = (_hand_tip(body) - before).length
        core.write_rotation(pb, saved)
        bpy.context.view_layer.update()
        if moved > 0.01:
            return end
    raise AssertionError("turning forearm_fk.L moves the hand at neither end of IK_FK")


def test_rigify_fk_ik_switch_and_both_controls():
    """Rigify's arm, driven by Kneady:
    - the IK_FK switch is dragged to FK and held at the property's end,
      within its 0 to 1 range;
    - the FK forearm then bends the arm;
    - back in IK, moving the IK hand control moves the hand.
    Unlike Rain's, Rigify's FK controls carry no constraint: the blend is on
    the ORG bones further down. So under IK the FK forearm is named as held
    by the ORG bone's later copy (core._followers_overridden), and in FK it
    is free."""
    rig, body = _open("mpfb_rigify_human.blend")
    region = _region_on(body, ("DEF-forearm.L", "DEF-forearm.L.001"), "Forearm.L")
    _set(region.buttons[0].up, "ROTATE", rig, "forearm_fk.L", "X")
    _set(region.buttons[0].across, "PROPERTY", rig, data_path='pose.bones["upper_arm_parent.L"]["IK_FK"]')
    switch = rig.pose.bones["upper_arm_parent.L"]
    fk = _fk_end(rig, body, switch)
    ik = 1.0 - fk
    _switch_to(rig, switch, ik)
    # under IK, the FK forearm is named as held by the ORG bone's later copy
    core = rigs.kneady()
    held = core.Channel(region.buttons[0].up, body, region)
    assert held.ok and held.note, "under IK the FK forearm is not named as held"
    _switch_to(rig, switch, fk)
    free = core.Channel(region.buttons[0].up, body, region)
    assert free.ok and not free.note, "in FK the FK forearm is still named as held: %r" % free.note
    _switch_to(rig, switch, ik)
    # the switch, dragged toward FK and past it: held at the property's end
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, across=4000.0 * (1 if fk > ik else -1))
    assert abs(switch["IK_FK"] - fk) < 1e-6, "the switch dragged to %r, not %r" % (switch["IK_FK"], fk)
    bpy.context.view_layer.update()
    before = _hand_tip(body)
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0)
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "in FK the hand moved %.4f m" % moved
    # back in IK, the IK hand control moved
    _switch_to(rig, switch, ik)
    region.buttons[0].across.enabled = False
    _set(region.buttons[0].up, "MOVE", rig, "hand_ik.L", "Y")
    bpy.context.view_layer.update()
    before = _hand_tip(body)
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0)
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "moving hand_ik.L moved the hand %.4f m" % moved
