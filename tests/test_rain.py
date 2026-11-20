"""Blender Studio's Rain (CloudRig, 2166 bones; CC-BY), a production
character, and the first rig tested that is not Kneady's own. The tests are
skipped where the asset is not on the machine (rigs.asset). Rain is opened
with its scripts off: its rig UI runs a script, and a test never runs code
it was handed.

What it brings that the small rigs do not:
- a body under Vertex Weight Mix, Mask, Armature and Subdivision;
- FK controls that follow IK by a Copy Transforms whose influence an IK / FK
  property drives;
- hinge bones locked on two axes;
- bones in every rotation order;
- a collection made to be linked and overridden."""

import os
import time

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

import rigs

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
RIG, BODY = "RIG-rain", "GEO-rain-body"
SWITCH = ("Properties_IKFK", "ik_arm_left")


def _open_rain():
    rigs.open_asset("Rain v3.3", "rain_v3.2.blend", newer_ok=True)
    return bpy.data.objects[RIG], bpy.data.objects[BODY]


def _forearm_region(body, rig):
    """A region on the body's left forearm, made of the faces wholly weighted
    to the forearm's deform bones. A drag up bends FK-Forearm.L (a hinge, X
    only), and a drag across switches the arm between IK and FK."""
    core = rigs.kneady()
    groups = {g.index for g in body.vertex_groups if g.name in ("DEF-Forearm1.L", "DEF-Forearm2.L")}
    on = set()
    for v in body.data.vertices:
        if sum(g.weight for g in v.groups if g.group in groups) > 0.5:
            on.add(v.index)
    faces = [p.index for p in body.data.polygons if all(i in on for i in p.vertices)]
    assert faces, "no forearm faces on the body"
    region = core.new_region(body, "Forearm.L")
    core.tag_faces(body.data, faces, region.id)
    button = region.buttons[0]
    button.up.enabled, button.up.kind, button.up.axis = True, "ROTATE", "X"
    button.up.target, button.up.bone = rig, "FK-Forearm.L"
    button.across.enabled, button.across.kind = True, "PROPERTY"
    button.across.target = rig
    button.across.data_path = 'pose.bones["%s"]["%s"]' % SWITCH
    button.single = True
    return region, len(faces)


def _hand_tip(body):
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    tip = max((ev.matrix_world @ v.co for v in me.vertices), key=lambda p: p.x)
    ev.to_mesh_clear()
    return tip


def test_rain_region_through_the_modifier_stack():
    """Faces tagged on the body's cage are the region on the body as shown,
    through Vertex Weight Mix, Mask, Armature and Subdivision."""
    core = rigs.kneady()
    rig, body = _open_rain()
    region, count = _forearm_region(body, rig)
    tags = core.evaluated_tags(body, bpy.context.evaluated_depsgraph_get())
    shown = int((tags == region.id).sum()) if tags is not None else 0
    assert shown >= count, "%d faces shown as the region, %d tagged on the cage" % (shown, count)


def test_rain_fk_under_ik_names_the_switch():
    """The arm starts in IK. FK-Forearm.L follows IK by a Copy Transforms, so
    a drag turns the FK control and nothing shows; the command names what
    holds it. Once switched to FK, the drag bends the arm. The switch is the
    property, dragged by the same button's other direction and kept within
    the property's 0 to 1 range."""
    core = rigs.kneady()
    rig, body = _open_rain()
    region, _count = _forearm_region(body, rig)
    up = core.Channel(region.buttons[0].up, body, region)
    assert up.ok and up.note and "ik_arm_left" in up.note, "under IK: ok %s, note %r" % (up.ok, up.note)
    # the switch, by a drag across: 1 (IK) down past 0 is held at 0, its own minimum
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, across=-400.0)
    owner = rig.pose.bones[SWITCH[0]]
    assert owner[SWITCH[1]] == 0.0, "the switch dragged to %r, not held at 0" % owner[SWITCH[1]]
    bpy.context.view_layer.update()
    up = core.Channel(region.buttons[0].up, body, region)
    assert up.ok and not up.note, "in FK: ok %s, note %r" % (up.ok, up.note)
    before = _hand_tip(body)
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0)
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "in FK the hand moved %.4f m" % moved


def test_rain_locked_axes_say_so():
    """FK-Forearm.L bends on X alone: a turn about Y says it is locked."""
    core = rigs.kneady()
    rig, body = _open_rain()
    region, _count = _forearm_region(body, rig)
    region.buttons[0].up.axis = "Y"
    ch = core.Channel(region.buttons[0].up, body, region)
    assert not ch.ok and "locked" in ch.why, "about Y: ok %s, %r" % (ch.ok, ch.why)


def test_rain_auto_keys_a_zyx_bone():
    """FK-Forearm.L turns in ZYX order: Auto Keying keys its Euler rotation."""
    rig, body = _open_rain()
    region, _count = _forearm_region(body, rig)
    ts, ed = bpy.context.scene.tool_settings, bpy.context.preferences.edit
    saved = ts.use_keyframe_insert_auto, ed.use_keyframe_insert_available
    ts.use_keyframe_insert_auto, ed.use_keyframe_insert_available = True, False
    try:
        bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=60.0)
    finally:
        ts.use_keyframe_insert_auto, ed.use_keyframe_insert_available = saved
    ad = rig.animation_data
    action = ad.action if ad is not None else None
    paths = set()
    if action is not None:
        if hasattr(action, "layers") and len(action.layers):
            paths = {fc.data_path for layer in action.layers for strip in layer.strips
                     for bag in strip.channelbags for fc in bag.fcurves}
        else:
            paths = {fc.data_path for fc in action.fcurves}
    assert 'pose.bones["FK-Forearm.L"].rotation_euler' in paths, "keyed: %s" % sorted(paths)[:8]


def test_rain_hover_is_quick():
    """What hovering costs on Rain's body: the ray cast, and reading the
    region tags as shown. Both are timed after the first call, which builds
    what is cached."""
    core = rigs.kneady()
    rig, body = _open_rain()
    region, _count = _forearm_region(body, rig)
    bpy.context.scene.kneady_on = True
    dg = bpy.context.evaluated_depsgraph_get()
    core.evaluated_tags(body, dg)
    t = time.perf_counter()
    for _ in range(10):
        core.forget(body.name)
        core.evaluated_tags(body, dg)
    tags_ms = (time.perf_counter() - t) * 100.0
    # rays from in front, at the body's middle, where her clothes cover it
    center = body.matrix_world @ (sum((Vector(c) for c in body.bound_box), Vector()) / 8.0)
    hits = 0
    t = time.perf_counter()
    for k in range(50):
        origin = center + Vector((0.002 * (k - 25), -3.0, 0.0))
        found = core.cast(bpy.context, origin, Vector((0.0, 1.0, 0.0)))
        hits += found is not None and found[0].startswith("GEO-rain")
    cast_ms = (time.perf_counter() - t) * 20.0
    assert hits > 25, "only %d of 50 rays met Rain" % hits
    print("      Rain: region tags %.1f ms after an edit, a hover's cast %.2f ms (%d of 50 on Rain: clothes cover the body)"
          % (tags_ms, cast_ms, hits))
    assert tags_ms < 100.0 and cast_ms < 20.0, "tags %.1f ms, cast %.2f ms" % (tags_ms, cast_ms)


def test_rain_linked_and_overridden():
    """The production case: regions are made in Rain's file, then the
    character is linked into a shot (its CH-rain collection) and overridden.
    There the region is present, its commands point at the override's rig,
    and the switch and the bend work."""
    rig, body = _open_rain()
    _forearm_region(body, rig)
    os.makedirs(OUTPUT, exist_ok=True)
    source = os.path.join(OUTPUT, "rain_with_regions.blend")
    bpy.ops.wm.save_as_mainfile(filepath=source, copy=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    with bpy.data.libraries.load(source, link=True) as (src, dst):
        dst.collections = ["CH-rain"]
    empty = bpy.data.objects.new("Rain", None)
    empty.instance_type, empty.instance_collection = "COLLECTION", dst.collections[0]
    bpy.context.scene.collection.objects.link(empty)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    empty.select_set(True)
    bpy.context.view_layer.objects.active = empty
    bpy.ops.object.make_override_library()
    rig = next(o for o in bpy.context.scene.objects if o.name == RIG and o.override_library is not None)
    body = next(o for o in bpy.context.scene.objects if o.name == BODY and o.override_library is not None)
    core = rigs.kneady()
    regions = core.regions_of(body)
    assert [r.name for r in regions] == ["Forearm.L"], "the override's regions: %s" % [r.name for r in regions]
    up = regions[0].buttons[0].up
    assert up.target == rig, "the command points at %s, not the override's rig" % (up.target.name_full
                                                                                    if up.target else None)
    bpy.ops.kneady.drag(target=body.name, region=regions[0].id, button=0, across=-400.0)
    bpy.context.view_layer.update()
    before = _hand_tip(body)
    bpy.ops.kneady.drag(target=body.name, region=regions[0].id, button=0, up=80.0)
    moved = (_hand_tip(body) - before).length
    assert moved > 0.01, "the overridden Rain's hand moved %.4f m" % moved
