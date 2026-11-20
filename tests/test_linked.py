"""Linked characters: in production a character is linked from its own file
and posed through a library override. The regions are made once, in the
character's file, and work wherever it is linked."""

import os

import bpy  # type: ignore

import rigs

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _character_file():
    """A character file: an arm rig and its mesh in a collection, the mesh
    carrying a region that turns the rig's Lower bone. Returns its path."""
    bpy.ops.wm.read_homefile(use_empty=True)
    rig, mesh = rigs.arm_rig("Arm")
    rigs.turn_button(mesh, rig, "Lower")
    char = bpy.data.collections.new("Character")
    bpy.context.scene.collection.children.link(char)
    for o in (rig, mesh):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        char.objects.link(o)
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, "character.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.read_homefile(use_empty=True)
    return path


def _link(path):
    """The character linked into this file as an instance of its collection.
    Returns the instancing empty."""
    with bpy.data.libraries.load(path, link=True) as (src, dst):
        dst.collections = ["Character"]
    char = dst.collections[0]
    empty = bpy.data.objects.new("Character", None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = char
    bpy.context.scene.collection.objects.link(empty)
    return empty


def _override(empty):
    """A library override of the linked character, as Object > Library
    Override > Make does. Returns (rig, mesh) of the override."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    empty.select_set(True)
    bpy.context.view_layer.objects.active = empty
    bpy.ops.object.make_override_library()
    rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE" and o.override_library is not None)
    mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH" and o.override_library is not None)
    return rig, mesh


def test_override_poses_by_its_regions():
    """The overridden character's mesh keeps the region made in its file. The
    region's command points at the override's rig, not the linked one, and a
    drag turns the override's bone."""
    core = rigs.kneady()
    path = _character_file()
    rig, mesh = _override(_link(path))
    regions = core.regions_of(mesh)
    assert [r.name for r in regions] == ["Bend"], "the override's regions: %s" % [r.name for r in regions]
    command = regions[0].buttons[0].up
    assert command.target == rig, "the command points at %s (library %s), not the override's rig" % (
        command.target.name if command.target else None,
        command.target.library.filepath if command.target and command.target.library else None)
    bpy.context.scene.kneady_on = True
    rigs.pose_mode(rig)
    result = bpy.ops.kneady.drag(target=mesh.name, region=regions[0].id, button=0, up=60.0)
    assert result == {"FINISHED"}, result
    turned = rigs.angle_of(rig.pose.bones["Lower"])
    assert turned > 1.0, "the override's Lower turned %.2f degrees" % turned
    rigs.object_mode()


def test_linked_without_override_says_why():
    """Linked but not overridden, nothing can be posed: the command says why
    instead of doing nothing."""
    core = rigs.kneady()
    path = _character_file()
    _link(path)
    linked = bpy.data.objects["Arm"]
    regions = core.regions_of(linked)
    assert regions, "the linked mesh has no regions"
    channel = core.Channel(regions[0].buttons[0].up, linked, regions[0])
    assert not channel.ok, "a linked rig's bone reported as movable"
    assert "override" in channel.why.lower(), "why: %r" % channel.why
