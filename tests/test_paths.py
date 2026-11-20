"""A Property command's path, made for the Drive More Than Bones tutorial.
Its field suggests what the item has: shape keys and custom properties. A
path copied with Copy Data Path from a shape key or the mesh is read from
where it was copied, just as one copied from the object is."""

import os

import bpy  # type: ignore

import rigs

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPE_CUBE = os.path.join(os.path.dirname(HERE), "tutorials", "_scenes", "shape_cube.blend")
SPHERE = 'data.shape_keys.key_blocks["Sphere"].value'


def _cube():
    bpy.ops.wm.open_mainfile(filepath=SHAPE_CUBE, load_ui=False, use_scripts=False)
    cube = bpy.data.objects["Cube"]
    region = rigs.kneady().new_region(cube, "Cube", whole=True)
    return cube, region


def test_path_suggests_shape_keys_and_custom_properties():
    """The suggestions are:
    - each shape key except the Basis;
    - the object's and its mesh's number custom properties (for a toggle,
      its true / false ones as well);
    - never one starting with _.
    They are filtered by what is typed."""
    props = rigs.module("props")
    cube, region = _cube()
    cube["Stretch"] = 0.5
    cube["Flag"] = True
    cube["_hidden"] = 1.0
    cube.data["Bulge"] = 2
    found = props.path_suggestions(cube)
    assert found == [SPHERE, '["Stretch"]', 'data["Bulge"]'], found
    assert '["Flag"]' in props.path_suggestions(cube, booleans=True)
    command = region.buttons[0].up
    command.kind = "PROPERTY"
    assert props._path_search(command, bpy.context, "sph") == [SPHERE]
    assert len(props._path_search(command, bpy.context, "")) == 3


def test_copied_paths_read_where_they_were_copied():
    """Paths as Copy Data Path gives them drive just as the paths from the
    object do, and a drag up raises them:
    - a shape key's value, copied from its Key (key_blocks["Sphere"].value);
    - a mesh's custom property, copied from the mesh (["Bulge"])."""
    core = rigs.kneady()
    cube, region = _cube()
    cube.data["Bulge"] = 1.0
    keys = cube.data.shape_keys.key_blocks
    for path, read in ((SPHERE, lambda: keys["Sphere"].value),
                       ('key_blocks["Sphere"].value', lambda: keys["Sphere"].value),
                       ('["Bulge"]', lambda: cube.data["Bulge"])):
        command = region.buttons[0].up
        command.enabled, command.kind, command.data_path = True, "PROPERTY", path
        channel = core.Channel(command, cube, region)
        assert channel.ok, "%s: %s" % (path, channel.why)
        before = read()
        bpy.ops.kneady.drag(target=cube.name, region=region.id, button=0, up=100.0)
        assert read() > before + 0.1, "%s: %.3f, was %.3f" % (path, read(), before)
    command.data_path = 'key_blocks["Nothing"].value'
    channel = core.Channel(command, cube, region)
    assert not channel.ok and "Set its Path again" in channel.why, channel.why


def test_path_suggests_a_rigs_pose_bone_switches():
    """On a rig, the suggestions include its pose bones' custom properties,
    which is where an IK / FK switch lives (the arm scene's Rigify IK_FK)."""
    props = rigs.module("props")
    arm = os.path.join(os.path.dirname(HERE), "tutorials", "_scenes", "arm.blend")
    bpy.ops.wm.open_mainfile(filepath=arm, load_ui=False, use_scripts=False)
    found = props.path_suggestions(bpy.data.objects["Rig"])
    switch = 'pose.bones["upper_arm_parent.L"]["IK_FK"]'
    assert switch in found, found[:20]
    assert all("rigify_type" not in p for p in found), "a text property suggested"
