"""Kneady in Pose mode: an animator poses a rig in Pose mode, so Kneady works
there as in Object mode. The mesh is hovered and dragged while the armature
is the one in Pose mode."""

import bpy  # type: ignore

import rigs


def _gizmo_poll():
    core = rigs.kneady()
    ops = __import__(core.__name__.rsplit(".", 1)[0] + ".ops", fromlist=["ops"])
    return ops.KNEADY_GGT_regions.poll(bpy.context)


def test_works_in_object_and_pose_mode():
    """On in Object mode and in Pose mode, off in Edit mode."""
    rig, mesh = rigs.arm_rig()
    rigs.turn_button(mesh, rig, "Lower")
    bpy.context.scene.kneady_on = True
    bpy.context.view_layer.objects.active = mesh
    assert _gizmo_poll(), "not on in Object mode"
    rigs.pose_mode(rig)
    assert bpy.context.mode == "POSE", bpy.context.mode
    assert _gizmo_poll(), "not on in Pose mode"
    rigs.object_mode()
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.mode_set(mode="EDIT")
    assert not _gizmo_poll(), "on in Edit mode"
    rigs.object_mode()


def test_drag_turns_a_bone_in_pose_mode():
    """A drag on the mesh's region, with its rig in Pose mode, turns the bone
    the button drives, and the mesh follows it. The other bone stays."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    bpy.context.scene.kneady_on = True
    rigs.pose_mode(rig)
    tip = max(rigs.world_points(mesh), key=lambda p: p.z)
    result = bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=60.0)
    assert result == {"FINISHED"}, result
    lower, upper = rig.pose.bones["Lower"], rig.pose.bones["Upper"]
    assert rigs.angle_of(lower) > 1.0, "Lower turned %.2f degrees" % rigs.angle_of(lower)
    assert rigs.angle_of(upper) < 1e-6, "Upper turned too"
    moved = max(rigs.world_points(mesh), key=lambda p: p.z)
    assert (moved - tip).length > 1e-3, "the mesh did not follow the bone"
    rigs.object_mode()


def test_click_selects_the_driven_bones():
    """A click without a drag, in Pose mode, selects the bones the button
    drives, makes the last one active and deselects the rest, so the region
    works as a picker for the rig's controls. Shift toggles them."""
    core = rigs.kneady()
    ops = __import__(core.__name__.rsplit(".", 1)[0] + ".ops", fromlist=["ops"])
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    rigs.pose_mode(rig)
    upper, lower = rig.pose.bones["Upper"], rig.pose.bones["Lower"]
    core.select_bone(upper, True)
    button = region.buttons[0]
    channels = [[core.Channel(c, mesh, region) for c in [d] + list(d.more)] for d in (button.across, button.up)]
    picked = ops.select_driven_bones(bpy.context, channels)
    assert [pb.name for pb in picked] == ["Lower"], [pb.name for pb in picked]
    assert core.bone_selected(lower) and not core.bone_selected(upper), "selection %s / %s" % (
        core.bone_selected(upper), core.bone_selected(lower))
    assert rig.data.bones.active == lower.bone, rig.data.bones.active
    ops.select_driven_bones(bpy.context, channels, toggle=True)
    assert not core.bone_selected(lower), "Shift did not toggle it off"
    rigs.object_mode()
