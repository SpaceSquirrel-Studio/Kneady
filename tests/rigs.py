"""Small rigs for Kneady's tests, built from nothing: no files, no add-ons."""

import math
import sys

import bmesh  # type: ignore
import bpy  # type: ignore
from mathutils import Matrix  # type: ignore


class Skip(Exception):
    """Raised by a test that cannot run here - an asset not on this machine."""


def asset(*parts):
    """The path of a test asset, under KNEADY_TEST_ASSETS or ~/Documents/Kneady
    test assets. Raises Skip if it is not there."""
    import os
    root = os.environ.get("KNEADY_TEST_ASSETS") or os.path.join(os.path.expanduser("~"), "Documents",
                                                                "Kneady test assets")
    path = os.path.join(root, *parts)
    if not os.path.exists(path):
        raise Skip("no %s" % path)
    return path


def open_asset(*parts, newer_ok=False):
    """Open a test asset with its scripts off. Raises Skip where this Blender
    cannot read it as it was made. A file saved by a newer Blender either
    fails to open (4.2 with a 5.2 file) or opens without what is new in it
    (4.5 loses a custom property's range from a 5.2 file). With `newer_ok`,
    a newer file that opens is fine for this test."""
    path = asset(*parts)
    try:
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False, use_scripts=False)
    except RuntimeError as exc:
        raise Skip("cannot open %s here: %s" % (parts[-1], str(exc).splitlines()[0][:80]))
    if not newer_ok and tuple(bpy.data.version[:2]) > tuple(bpy.app.version[:2]):
        raise Skip("%s was saved by Blender %d.%d, newer than this one" % ((parts[-1],) + tuple(bpy.data.version[:2])))
    return path


def kneady():
    """Kneady's package as the test runner loaded it."""
    return next(m for name, m in sys.modules.items() if name.endswith(".core") and hasattr(m, "Channel")
                and name.split(".")[0] not in ("bl_ext",))


def module(name):
    """One of Kneady's modules - "pick", "ui" - as the test runner loaded it."""
    return sys.modules[kneady().__name__.rsplit(".", 1)[0] + "." + name]


def arm_rig(name="Arm"):
    """An armature of two bones along Z - Upper from 0 to 1, Lower from 1 to 2
    - and a cylinder skinned to it, each vertex wholly on the bone beside it.
    Returns (armature, mesh)."""
    arm_data = bpy.data.armatures.new(name + "Rig")
    rig = bpy.data.objects.new(name + "Rig", arm_data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    upper = arm_data.edit_bones.new("Upper")
    upper.head, upper.tail = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    lower = arm_data.edit_bones.new("Lower")
    lower.head, lower.tail = (0.0, 0.0, 1.0), (0.0, 0.0, 2.0)
    lower.parent = upper
    lower.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")

    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.2, radius2=0.2, depth=2.0,
                          matrix=Matrix.Translation((0.0, 0.0, 1.0)))
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1.0],
                              cuts=3)
    bm.to_mesh(me)
    bm.free()
    mesh = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(mesh)
    groups = {n: mesh.vertex_groups.new(name=n) for n in ("Upper", "Lower")}
    for v in me.vertices:
        groups["Upper" if v.co.z < 1.0 else "Lower"].add([v.index], 1.0, "REPLACE")
    mod = mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mesh.parent = rig
    bpy.context.view_layer.update()
    return rig, mesh


def turn_button(mesh, rig, bone, axis="X", name="Bend"):
    """A whole-object region on `mesh` whose first button turns `bone` of
    `rig` about `axis` when dragged up. Returns the region."""
    core = kneady()
    region = core.new_region(mesh, name, whole=True)
    button = region.buttons[0]
    button.name = name
    up = button.up
    up.enabled = True
    up.kind, up.axis, up.target, up.bone = "ROTATE", axis, rig, bone
    button.across.enabled = False
    return region


def pose_mode(rig):
    """Make `rig` active and put it in Pose mode."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")


def object_mode():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def angle_of(pb):
    """How far a pose bone is turned from its rest, in degrees."""
    m = pb.matrix_basis.to_3x3()
    return math.degrees(m.to_quaternion().angle)


def world_points(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return pts
