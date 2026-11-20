"""Data versions. Each region carries the data version it was made at, so a
later Kneady can bring a file saved by an earlier one up to date. Opening a
file with nothing to update writes nothing."""

import contextlib
import os

import bpy  # type: ignore

import rigs

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


@contextlib.contextmanager
def _a_later_kneady(step):
    """Kneady as if at data version 2, with `step` turning version 1 into 2."""
    core = rigs.kneady()
    saved = core.DATA_VERSION, dict(core.MIGRATIONS)
    core.DATA_VERSION = 2
    core.MIGRATIONS[1] = step
    try:
        yield core
    finally:
        core.DATA_VERSION = saved[0]
        core.MIGRATIONS.clear()
        core.MIGRATIONS.update(saved[1])


def test_new_regions_are_stamped():
    core = rigs.kneady()
    mesh = bpy.data.objects.new("M", bpy.data.meshes.new("M"))
    bpy.context.scene.collection.objects.link(mesh)
    region = core.new_region(mesh, "R", whole=True)
    assert region.version == core.DATA_VERSION, "made at version %d, not %d" % (region.version, core.DATA_VERSION)


def test_nothing_to_update_writes_nothing():
    """A region from before data versions existed (version 0), with no step
    to run, is left as it is."""
    core = rigs.kneady()
    mesh = bpy.data.objects.new("M", bpy.data.meshes.new("M"))
    bpy.context.scene.collection.objects.link(mesh)
    region = core.new_region(mesh, "R", whole=True)
    region.version = 0
    assert core.migrate_file() == 0, "updated a region with nothing to update"
    assert region.version == 0, "stamped %d with nothing to update" % region.version


def test_steps_run_in_order_on_open():
    """A later Kneady opens an older file. On opening, the load handler:
    - gives every older region the step once and stamps it;
    - leaves a current region alone;
    - leaves and reports a region from a newer Kneady. That region is on an
      object of its own, which is then left whole (see test_newer_object_*)."""
    core = rigs.kneady()
    mesh = bpy.data.objects.new("M", bpy.data.meshes.new("M"))
    bpy.context.scene.collection.objects.link(mesh)
    for name, version in (("before", 0), ("one", 1), ("two", 2)):
        core.new_region(mesh, name, whole=True).version = version
    other = bpy.data.objects.new("N", bpy.data.meshes.new("N"))
    bpy.context.scene.collection.objects.link(other)
    core.new_region(other, "three", whole=True).version = 3
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, "versions.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)

    def step(region):
        region.name += " +step"

    with _a_later_kneady(step):
        bpy.ops.wm.open_mainfile(filepath=path)
        mesh = bpy.data.objects["M"]
        got = {r.name: r.version for r in mesh.kneady.regions}
        assert got == {"before +step": 2, "one +step": 2, "two": 2}, got
        got = {r.name: r.version for r in bpy.data.objects["N"].kneady.regions}
        assert got == {"three": 3}, got
        newer = [r.name for r in core.newer_regions()]
        assert newer == ["three"], "newer regions: %s" % newer


def _two_cubes(core, later):
    """Two cubes:
    - FromBeta has a region this Kneady made (version 0, from before data
      versions) beside one a newer Kneady made at `later`. The newer one has
      tagged faces and a setting this Kneady has no property for.
    - Plain has a region this Kneady made."""
    bpy.ops.mesh.primitive_cube_add()
    newer = bpy.context.active_object
    newer.name = "FromBeta"
    core.new_region(newer, "Old").version = 0
    beta = core.new_region(newer, "Beta")
    beta.version = later
    beta["only_a_beta_knows"] = 7
    core.tag_faces(newer.data, [0, 1], beta.id)
    bpy.ops.mesh.primitive_cube_add(location=(3.0, 0.0, 0.0))
    plain = bpy.context.active_object
    plain.name = "Plain"
    core.new_region(plain, "Arm", whole=True)
    return beta.id


def test_newer_object_left_exactly_as_it_is():
    """Phase 1, item 4: a file saved by a newer Kneady (the Pro beta, say) is
    opened again in this release. An object with a region from the newer
    Kneady is not this Kneady's to change:
    - none of its regions is updated, not even the older one beside the
      newer;
    - what this Kneady has no property for is kept through a save;
    - opening the file writes nothing at all.
    Rolling back from a beta has to be safe, and this is the only release
    that can promise it."""
    core = rigs.kneady()

    def step(region):
        region.name += " +step"

    os.makedirs(OUTPUT, exist_ok=True)
    # Blender 4.2 marks every file as changed when it opens (measured, in the
    # background). So whether opening changed a file can only be checked where
    # a plain file opens clean.
    plain_path = os.path.join(OUTPUT, "plain.blend")
    bpy.ops.wm.save_as_mainfile(filepath=plain_path)
    bpy.ops.wm.open_mainfile(filepath=plain_path)
    opens_clean = not bpy.data.is_dirty
    bpy.ops.wm.read_homefile(use_empty=True)
    with _a_later_kneady(step):
        later = core.DATA_VERSION + 1
        rid = _two_cubes(core, later)
        path = os.path.join(OUTPUT, "from_a_beta.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        for _round in range(2):                 # opened, then saved here and opened again
            bpy.ops.wm.open_mainfile(filepath=path)
            assert not (opens_clean and bpy.data.is_dirty), "opening the file changed it"
            newer = bpy.data.objects["FromBeta"]
            got = [(r.name, r.version) for r in newer.kneady.regions]
            assert got == [("Old", 0), ("Beta", later)], got
            assert newer.kneady.regions[1].get("only_a_beta_knows") == 7, "a newer Kneady's setting was lost"
            tags = core.face_tags(newer.data)
            assert tags is not None and list(tags[:2]) == [rid, rid], "face tags %s" % (tags[:2],)
            bpy.ops.wm.save_as_mainfile(filepath=path)


def test_newer_object_is_not_used_or_changed():
    """The same newer object, while the file is open:
    - nothing on it is hovered, drawn, dragged or placed (each of these
      reads regions_of);
    - its regions cannot be added to, removed or changed in the panel
      (regions_fixed, which says why);
    - opening the file tells the person once, naming the object.
    The object beside it works as before."""
    core = rigs.kneady()
    tree = rigs.module("tree")
    later = core.DATA_VERSION + 1
    rid = _two_cubes(core, later)
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, "from_a_beta.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    newer, plain = bpy.data.objects["FromBeta"], bpy.data.objects["Plain"]
    assert core.regions_of(newer) == [], "a newer Kneady's object still has regions here"
    assert len(core.listed_regions(newer)) == 2, "its regions are not all still listed"
    assert core.find_region(newer, rid) is None, "its newer region can be found to drive"
    assert [r.name for r in core.regions_of(plain)] == ["Arm"], "the object beside it lost its region"
    hovered = [o.name for o in core.objects_with_regions(bpy.context)]
    assert hovered == ["Plain"], "objects Kneady works on: %s" % hovered
    assert core.newer_on(newer) == later and core.newer_on(plain) == 0
    why = core.regions_fixed(newer) or ""
    assert why.startswith("Made with a newer Kneady"), "the panel says %r" % why
    assert not tree.can_add_region(newer), "a region can be added to it"
    assert core.regions_fixed(plain) is None, "the object beside it is locked too"
    note = core.LOAD_NOTE[0]
    assert "FromBeta" in note and "data version %d" % later in note and "Plain" not in note, note
    bpy.ops.wm.read_homefile(use_empty=True)
    assert core.LOAD_NOTE[0] == "", "the note outlived its file: %r" % core.LOAD_NOTE[0]
