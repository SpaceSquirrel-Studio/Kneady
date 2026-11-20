"""Regions under live modifiers. The hover reads a region from the mesh as
shown, so a modifier that carries face attributes keeps it, and one that
rebuilds the mesh from scratch loses it. What each modifier does is tested
here so the documentation can say it."""

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

import rigs
import test_data_life


def _hit(core, at):
    return core.cast(bpy.context, at + Vector((0.0, -5.0, 0.0)), Vector((0.0, 1.0, 0.0)))


def _region_under_modifier(kind, **settings):
    """The region hovered on the mesh's top half and nothing on its bottom,
    with a `kind` modifier added after the Armature."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    _rig, mesh, region = test_data_life._arm()
    mod = mesh.modifiers.new(kind.title(), kind)
    for key, value in settings.items():
        setattr(mod, key, value)
    bpy.context.scene.kneady_on = True
    bpy.context.view_layer.update()
    core.forget()
    top, bottom = _hit(core, Vector((0.0, 0.0, 1.6))), _hit(core, Vector((0.0, 0.0, 0.4)))
    return (top is not None and top[1] == region.id) and (bottom is not None and bottom[1] is None)


def test_carried_through():
    """Subdivision, Multires, Mirror, Solidify, Bevel and Triangulate keep
    each face's region."""
    kept = {
        "SUBSURF": dict(levels=2),
        "MULTIRES": {},
        "MIRROR": {},
        "SOLIDIFY": dict(thickness=0.05),
        "BEVEL": dict(width=0.02),
        "TRIANGULATE": {},
    }
    lost = [kind for kind, settings in kept.items() if not _region_under_modifier(kind, **settings)]
    assert not lost, "lost under %s" % lost


def test_decimate_moves_region_edges():
    """Decimate keeps the regions on the faces it keeps, but a face it merges
    across a region's edge takes one side's region: the edges shift."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    _rig, mesh, region = test_data_life._arm()
    for settings in (dict(ratio=0.5), dict(decimate_type="DISSOLVE")):
        mod = mesh.modifiers.new("Decimate", "DECIMATE")
        for key, value in settings.items():
            setattr(mod, key, value)
        ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        tags = core.face_tags(me)
        kept = 0 if tags is None else int((tags == region.id).sum())
        ev.to_mesh_clear()
        mesh.modifiers.remove(mod)
        assert kept, "Decimate %s lost the region" % settings


def test_remesh_loses_regions():
    """Remesh builds new faces with nothing carried over, so the regions are
    gone while it is on. The documentation says so."""
    assert not _region_under_modifier("REMESH", mode="VOXEL", voxel_size=0.05), "Remesh kept the region"
