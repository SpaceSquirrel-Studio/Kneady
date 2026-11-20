"""The easy start: someone with a rigged character and no program that sets
Kneady up for them.

- A new region on a mesh a rig deforms starts out turning that rig's active
  bone (the one last clicked in Pose mode), not the mesh, which would only
  pull it off its rig.
- Edit Faces selects the faces that bone deforms in one click (its vertex
  groups found by name).
- Use Rig and Use Active Bone point a command in one click each."""

import bpy  # type: ignore

import rigs


def test_a_new_region_on_a_rigged_mesh_turns_the_active_bone():
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    rig.data.bones.active = rig.data.bones["Lower"]
    region = core.new_region(mesh)
    up, across = region.buttons[0].up, region.buttons[0].across
    assert (up.target, up.bone, across.target, across.bone) == (rig, "Lower", rig, "Lower"), \
        "turns %s:%s / %s:%s" % (up.target, up.bone, across.target, across.bone)
    assert not up.dragged and region.name == "Lower", "dragged %s, named %r" % (up.dragged, region.name)


def test_a_new_region_turns_the_object_without_a_bone():
    """A plain mesh, and a rigged one with no bone clicked yet: the object."""
    core = rigs.kneady()
    mesh = bpy.data.objects.new("Plain", bpy.data.meshes.new("Plain"))
    bpy.context.scene.collection.objects.link(mesh)
    _rig, skinned = rigs.arm_rig()
    for obj in (mesh, skinned):
        up = core.new_region(obj).buttons[0].up
        assert up.target is None and up.dragged, "%s's region points at %s" % (obj.name, up.target)


def test_from_bone_to_drag():
    """The whole start: the bone clicked, the region added, Edit Faces, the
    bone's faces selected and assigned, the drag turning the bone."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    rig.data.bones.active = rig.data.bones["Lower"]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.kneady.region_add() == {"FINISHED"}
    region = mesh.kneady.regions[mesh.kneady.index]
    bpy.ops.kneady.region_edit()
    assert bpy.context.mode == "EDIT_MESH", bpy.context.mode
    bpy.ops.mesh.select_all(action="DESELECT")
    assert bpy.ops.kneady.region_group(from_bone=True) == {"FINISHED"}
    bpy.ops.kneady.region_faces(action="ASSIGN")
    bpy.ops.kneady.region_edit()
    want = set(core.group_faces(mesh, "Lower"))
    got = {i for i, t in enumerate(core.face_tags(mesh.data)) if t == region.id}
    assert got == want and want, "assigned %d faces, the group has %d" % (len(got), len(want))
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=60.0)
    assert rigs.angle_of(rig.pose.bones["Lower"]) > 1.0, "the bone did not turn"


def test_use_rig_and_use_active_bone():
    """A command pointed in two clicks: Use Rig fills the armature that
    deforms the mesh, Use Active Bone its active bone."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    up = region.buttons[0].up
    up.target, up.bone = None, ""
    up.dragged = False
    bpy.context.view_layer.objects.active = mesh
    with bpy.context.temp_override(kneady_command=up):
        bpy.ops.kneady.command_rig()
    assert up.target == rig, "Use Rig: %s" % up.target
    rig.data.bones.active = rig.data.bones["Upper"]
    with bpy.context.temp_override(kneady_command=up):
        bpy.ops.kneady.command_bone()
    assert up.bone == "Upper", "Use Active Bone: %r" % up.bone


def test_groups_for_a_control_bone():
    """The vertex groups a control bone deforms by, with the names used by
    the rigs tested:

    - every segment of a limb, for a control that names the limb whole
    - one segment, for a control that names one
    - a run of segments, stopped by another control's segment
    """
    core = rigs.kneady()
    mesh = bpy.data.objects.new("G", bpy.data.meshes.new("G"))
    bpy.context.scene.collection.objects.link(mesh)
    for name in ("DEF-forearm.L", "DEF-forearm.L.001", "forearm_stretch.l", "forearm_twist.l", "hand.l",
                 "DEF-Forearm1.L", "DEF-Forearm2.L", "DEF-Index1.L", "DEF-Index2.L",
                 "DEF-spine", "DEF-spine.001", "DEF-spine.002", "Spine"):
        mesh.vertex_groups.new(name=name)
    rig = bpy.data.objects.new("Controls", bpy.data.armatures.new("Controls"))
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name in ("spine_fk", "spine_fk.001", "spine_fk.002"):
        rig.data.edit_bones.new(name).tail = (0.0, 0.0, 1.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    cases = {
        "forearm_fk.L": ["DEF-forearm.L", "DEF-forearm.L.001"],              # Rigify
        "c_forearm_fk.l": ["forearm_stretch.l", "forearm_twist.l"],          # Auto-Rig Pro
        "c_hand_fk.l": ["hand.l"],
        "FK-Forearm.L": ["DEF-Forearm1.L", "DEF-Forearm2.L"],                # Rain
        "FK-Index1.L": ["DEF-Index1.L"],
        "spine_fk": ["DEF-spine"],                                           # spine_fk.001 has the next
        "spine_fk.001": ["DEF-spine.001"],
        "Spine": ["Spine"],                                                  # a deform bone
        "nothing.L": [],
    }
    for bone, want in cases.items():
        got = core.bone_groups(mesh, bone, rig)
        assert got == want, "%s: %r, not %r" % (bone, got, want)


def _skinned(body):
    return rigs.kneady().mesh_rig(body)


def test_rain_forearm_faces():
    """Rain (CloudRig): FK-Forearm.L deforms by both forearm segments, and the
    seam they share is kept."""
    import test_rain
    core = rigs.kneady()
    rig, body = test_rain._open_rain()
    groups = core.bone_groups(body, "FK-Forearm.L", rig)
    assert groups == ["DEF-Forearm1.L", "DEF-Forearm2.L"], groups
    both = len(core.group_faces(body, groups))
    apart = sum(len(core.group_faces(body, g)) for g in groups)
    assert both > apart, "both segments %d faces, apart %d" % (both, apart)


def test_rigify_forearm_faces():
    core = rigs.kneady()
    rigs.open_asset("mpfb_rigify_human.blend", newer_ok=True)
    body = bpy.data.objects["Human"]
    rig = _skinned(body)
    for bone, want in (("forearm_fk.L", ["DEF-forearm.L", "DEF-forearm.L.001"]), ("spine_fk", ["DEF-spine"]),
                       ("spine_fk.002", ["DEF-spine.002"]), ("f_index.01.L", ["DEF-f_index.01.L"])):
        got = core.bone_groups(body, bone, rig)
        assert got == want, "%s: %r" % (bone, got)


def test_arp_forearm_faces():
    """Auto-Rig Pro: c_forearm_fk.l's faces are the ones test_arp picks by hand."""
    import test_arp
    core = rigs.kneady()
    rig, body = test_arp._open()
    groups = core.bone_groups(body, "c_forearm_fk.l", rig)
    assert groups == ["forearm_stretch.l", "forearm_twist.l"], groups
    region = test_arp._forearm_region(body)
    by_hand = {i for i, t in enumerate(core.face_tags(body.data)) if t == region.id}
    assert set(core.group_faces(body, groups)) == by_hand, "not the forearm test_arp uses"
