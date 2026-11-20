"""Mixamo characters imported from FBX, skipped where they are not in the
test assets. FBX brings the armature at a scale of 0.01 and turned 90
degrees, every bone in quaternions with Mixamo's rolls, and an action already
on it. Ch15_nonPBR is one clothed mesh. Walking is Mixamo's Beta mannequin
(two meshes, a surface and its joints) with a walk keyed."""

import bpy  # type: ignore

import rigs


def _import(name):
    path = rigs.asset(name)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.fbx(filepath=path)
    return bpy.data.objects["Armature"]


def _region(mesh, rig, groups=None, name="R"):
    core = rigs.kneady()
    if groups is None:
        region = core.new_region(mesh, name, whole=True)
    else:
        wanted = {g.index for g in mesh.vertex_groups if g.name in groups}
        on = {v.index for v in mesh.data.vertices if sum(g.weight for g in v.groups if g.group in wanted) > 0.5}
        faces = [p.index for p in mesh.data.polygons if all(i in on for i in p.vertices)]
        assert faces, "no faces on %s" % (groups,)
        region = core.new_region(mesh, name)
        core.tag_faces(mesh.data, faces, region.id)
    region.buttons[0].across.enabled = False
    return region


def _tip(mesh, axis=0, low=False):
    ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return (min if low else max)(pts, key=lambda p: p[axis])


def test_mixamo_move_is_in_scene_units():
    """A Move's Speed is in scene units: on the 0.01-scale rig, 100 pixels at
    0.3 moves the hips 0.3 m. Before, it moved them 3 mm."""
    rig = _import("Ch15_nonPBR.fbx")
    body = bpy.data.objects["Ch15"]
    region = _region(body, rig)
    up = region.buttons[0].up
    up.enabled, up.kind, up.axis, up.target, up.bone = True, "MOVE", "Y", rig, "mixamorig:Hips"
    pb = rig.pose.bones["mixamorig:Hips"]
    before = (rig.matrix_world @ pb.head).copy()
    bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=100.0)
    bpy.context.view_layer.update()
    moved = (rig.matrix_world @ pb.head - before).length
    assert abs(moved - up.rate) < 1e-3, "100 px at Speed %.2f moved the hips %.4f m" % (up.rate, moved)


def test_mixamo_forearm_bends():
    rig = _import("Ch15_nonPBR.fbx")
    body = bpy.data.objects["Ch15"]
    region = _region(body, rig, ("mixamorig:LeftForeArm",), "Forearm.L")
    up = region.buttons[0].up
    up.enabled, up.kind, up.axis, up.target, up.bone = True, "ROTATE", "X", rig, "mixamorig:LeftForeArm"
    before = _tip(body)
    assert bpy.ops.kneady.drag(target=body.name, region=region.id, button=0, up=80.0) == {"FINISHED"}
    moved = (_tip(body) - before).length
    assert moved > 0.02, "the left hand moved %.4f m" % moved


def test_mixamo_animated_bone_keys_where_dragged():
    """The walk is keyed. With Auto Keying on, a drag at frame 12 keys frame
    12. Blender's own settings apply, Only Insert Available included, which
    keys this bone because it is animated."""
    rig = _import("Walking.fbx")
    surface = bpy.data.objects["Beta_Surface"]
    region = _region(surface, rig)
    up = region.buttons[0].up
    bone = "mixamorig:LeftForeArm"
    up.enabled, up.kind, up.axis, up.target, up.bone = True, "ROTATE", "X", rig, bone
    scene = bpy.context.scene
    scene.frame_set(12)
    ts = scene.tool_settings
    saved = ts.use_keyframe_insert_auto
    ts.use_keyframe_insert_auto = True
    try:
        bpy.ops.kneady.drag(target=surface.name, region=region.id, button=0, up=60.0)
    finally:
        ts.use_keyframe_insert_auto = saved
    action = rig.animation_data.action
    path = 'pose.bones["%s"].rotation_quaternion' % bone
    if hasattr(action, "layers") and len(action.layers):
        curves = [fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags
                  for fc in bag.fcurves if fc.data_path == path]
    else:
        curves = [fc for fc in action.fcurves if fc.data_path == path]
    assert curves, "the forearm has no rotation curves"
    keyed = [any(abs(k.co.x - 12.0) < 1e-3 for k in fc.keyframe_points) for fc in curves]
    assert all(keyed), "frame 12 keyed on %d of %d curves" % (sum(keyed), len(keyed))


def test_mixamo_two_meshes_one_rig():
    """The mannequin's surface and joints are two meshes on one rig. Each has
    its own region and is found under the mouse as itself, and both turn the
    same bone."""
    core = rigs.kneady()
    rig = _import("Walking.fbx")
    surface, joints = bpy.data.objects["Beta_Surface"], bpy.data.objects["Beta_Joints"]
    for mesh in (surface, joints):
        region = _region(mesh, rig, name=mesh.name)
        up = region.buttons[0].up
        up.enabled, up.kind, up.axis, up.target, up.bone = True, "ROTATE", "X", rig, "mixamorig:Spine"
    bpy.context.scene.kneady_on = True
    found = {o.name for o in core.objects_with_regions(bpy.context)}
    assert {surface.name, joints.name} <= found, "with regions: %s" % sorted(found)
    pb = rig.pose.bones["mixamorig:Spine"]
    for mesh in (surface, joints):
        start = pb.rotation_quaternion.copy()
        bpy.ops.kneady.drag(target=mesh.name, region=core.regions_of(mesh)[0].id, button=0, up=40.0)
        assert pb.rotation_quaternion != start, "dragging %s did not turn the spine" % mesh.name
