"""Data life: regions and their commands, through what happens to data in a
real file:
- saved and opened, and appended;
- duplicated (Shift+D and Alt+D), and joined;
- renamed;
- modifiers applied;
- undone;
- a character linked from a file that has no regions, then overridden:
  Blender keeps no region added to an override, so + says where regions
  are made instead."""

import os

import bpy  # type: ignore

import rigs
import test_linked

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _tagged(core, obj, rid):
    return {i for i, t in enumerate(core.face_tags(obj.data)) if t == rid}


def _arm(name="Arm"):
    """An arm rig, its mesh, and a region on the mesh's top half that turns
    Lower. Returns (rig, mesh, region)."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig(name)
    region = rigs.turn_button(mesh, rig, "Lower")
    region.whole = False
    top = [p.index for p in mesh.data.polygons if p.center.z > 1.0]
    core.tag_faces(mesh.data, top, region.id)
    return rig, mesh, region


def _select_only(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def _turned(rig):
    return rigs.angle_of(rig.pose.bones["Lower"])


def test_saved_and_opened():
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    rig, mesh, region = _arm()
    faces = _tagged(core, mesh, region.id)
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, "saved.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    mesh, rig = bpy.data.objects["Arm"], bpy.data.objects["ArmRig"]
    region = core.regions_of(mesh)[0]
    assert _tagged(core, mesh, region.id) == faces, "the faces changed"
    bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=60.0)
    assert _turned(rig) > 1.0, "the bone did not turn"


def test_appended():
    """Appended into another file, the mesh brings its region and the command
    still turns the rig appended with it."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    _arm()
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, "to_append.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.read_homefile(use_empty=True)
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        data_to.objects = ["Arm", "ArmRig"]
    for o in data_to.objects:
        bpy.context.scene.collection.objects.link(o)
    mesh, rig = bpy.data.objects["Arm"], bpy.data.objects["ArmRig"]
    regions = core.regions_of(mesh)
    assert len(regions) == 1 and regions[0].buttons[0].up.target == rig, "regions %s" % regions
    bpy.ops.kneady.drag(target=mesh.name, region=regions[0].id, button=0, up=60.0)
    assert _turned(rig) > 1.0, "the bone did not turn"


def test_duplicated():
    """Shift+D copies the mesh with its faces' tags, and Alt+D shares it.
    Either copy keeps the regions, and a command on the object dragged turns
    the copy, not the original."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    mesh = bpy.data.objects.new("Box", bpy.data.meshes.new("Box"))
    import bmesh  # type: ignore
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh.data)
    bm.free()
    bpy.context.scene.collection.objects.link(mesh)
    region = core.new_region(mesh, "Top")
    core.tag_faces(mesh.data, [p.index for p in mesh.data.polygons if p.normal.z > 0.5], region.id)
    for linked in (False, True):
        _select_only(mesh)
        bpy.ops.object.duplicate(linked=linked)
        copy = bpy.context.active_object
        assert copy is not mesh and (copy.data is mesh.data) == linked, "linked %s" % linked
        regions = core.regions_of(copy)
        assert [r.name for r in regions] == ["Top"], regions
        assert _tagged(core, copy, regions[0].id) == _tagged(core, mesh, region.id), "the copy's faces"
        before = mesh.rotation_euler.copy()
        bpy.ops.kneady.drag(target=copy.name, region=regions[0].id, button=0, up=60.0)
        assert abs(copy.rotation_euler.x) > 0.01, "the copy did not turn (linked %s)" % linked
        assert mesh.rotation_euler == before, "the original turned (linked %s)" % linked


def test_joined():
    """Two objects, each with regions of its own, are joined. The faces the
    other object tagged stay apart from the active object's region, and Keep
    Joined Faces makes them a region of their own."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    rig, a, ra = _arm("A")
    _rig_b, b, rb = _arm("B")
    a_faces, b_count = len(_tagged(core, a, ra.id)), len(_tagged(core, b, rb.id))
    assert ra.id != rb.id, "two objects' regions share id %d" % ra.id
    b_id = rb.id                 # the join frees rb along with B: never read it after
    del rb
    _select_only(a, b)
    bpy.ops.object.join()
    joined = bpy.context.active_object
    assert [r.name for r in core.regions_of(joined)] == ["Bend"], core.regions_of(joined)
    assert len(_tagged(core, joined, ra.id)) == a_faces, "the active region took the joined faces"
    loose = core.unlisted_tags(joined)
    assert loose == {b_id: b_count}, "unlisted %s" % loose
    _select_only(joined)
    assert bpy.ops.kneady.region_unlisted() == {"FINISHED"}
    names = [r.name for r in core.regions_of(joined)]
    assert len(names) == 2, names
    assert not core.unlisted_tags(joined), "still unlisted"


def test_renamed_object_and_reused_name():
    """The hover remembers each object's regions. A renamed object keeps
    them, and another object given the old name is not mistaken for it."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    from mathutils import Vector  # type: ignore
    _rig, mesh, region = _arm()
    bpy.context.scene.kneady_on = True
    depsgraph = bpy.context.evaluated_depsgraph_get()
    down = Vector((0.0, -1.0, 0.0))
    hit = core.cast(bpy.context, Vector((0.0, 5.0, 1.5)), down)
    assert hit and hit[1] == region.id, "before: %s" % (hit,)
    mesh.name = "Renamed"
    bpy.context.view_layer.update()
    hit = core.cast(bpy.context, Vector((0.0, 5.0, 1.5)), down)
    assert hit and hit[0] == "Renamed" and hit[1] == region.id, "renamed: %s" % (hit,)
    # another object beside it, under the old name, with a whole-object
    # region of its own
    other = bpy.data.objects.new("Arm", mesh.data.copy())
    other.location.x = 3.0
    bpy.context.scene.collection.objects.link(other)
    core.tag_faces(other.data, range(len(other.data.polygons)), 0)
    core.new_region(other, "Whole", whole=True)
    bpy.context.view_layer.update()
    del depsgraph
    hit = core.cast(bpy.context, Vector((3.0, 5.0, 1.5)), down)
    want = core.regions_of(other)[0].id
    assert hit and hit[0] == "Arm" and hit[1] == want, "the new Arm: %s, want region %d" % (hit, want)


def test_renamed_bone_says_so():
    """A command naming a bone since renamed says which bone it is missing."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    rig, mesh, region = _arm()
    rig.data.bones["Lower"].name = "Forearm"
    ch = core.Channel(region.buttons[0].up, mesh, region)
    assert not ch.ok and "Lower" in ch.why, "ok %s, %r" % (ch.ok, ch.why)


def test_modifiers_applied():
    """Applying a Subdivision keeps each face's region on the faces made from
    it, and applying the Armature keeps them all."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    rig, mesh, region = _arm()
    quads = sum(1 for p in mesh.data.polygons if p.index in _tagged(core, mesh, region.id) and len(p.vertices) == 4)
    sub = mesh.modifiers.new("Sub", "SUBSURF")
    sub.levels = 1
    _select_only(mesh)
    bpy.ops.object.modifier_apply(modifier="Sub")
    got = len(_tagged(core, mesh, region.id))
    assert got >= 4 * quads, "after Subdivision %d faces, at least %d" % (got, 4 * quads)
    bpy.ops.object.modifier_apply(modifier="Armature")
    assert len(_tagged(core, mesh, region.id)) == got, "the Armature lost faces"


def test_undo_through_region_edits():
    """Adding a region and assigning its faces undo and redo step by step.
    Undo needs a window: tests/probe_undo.py runs this in one."""
    if bpy.app.background:
        raise rigs.Skip("undo needs a window - run tests/probe_undo.py")
    import bmesh  # type: ignore
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    _select_only(mesh)
    faces = len(mesh.data.polygons)
    bpy.ops.ed.undo_push(message="start")
    # Call them as the panel does, with undo: a call from Python pushes no
    # undo step unless asked to
    bpy.ops.kneady.region_add("EXEC_DEFAULT", True)
    bpy.ops.kneady.region_edit("EXEC_DEFAULT", True)
    bpy.ops.mesh.select_all("EXEC_DEFAULT", True, action="SELECT")
    bpy.ops.kneady.region_faces("EXEC_DEFAULT", True, action="ASSIGN")
    bpy.ops.kneady.region_edit("EXEC_DEFAULT", True)

    def state():
        """(regions, tagged faces). In Edit mode the faces are read from the
        edit mesh."""
        obj = bpy.data.objects["Arm"]
        if obj.mode == "EDIT":
            bm = bmesh.from_edit_mesh(obj.data)
            layer = bm.faces.layers.int.get(core.TAG)
            tagged = sum(1 for f in bm.faces if layer is not None and f[layer] != 0)
        else:
            tags = core.face_tags(obj.data)
            tagged = int((tags != 0).sum()) if tags is not None else 0
        return len(core.regions_of(obj)), tagged

    states = [state()]
    assert states[0] == (1, faces), "after the edits: %s" % (states[0],)
    for _ in range(12):
        if not bpy.ops.ed.undo.poll() or states[-1][0] == 0:
            break
        bpy.ops.ed.undo()
        states.append(state())
    order = [s for k, s in enumerate(states) if k == 0 or s != states[k - 1]]
    assert order == [(1, faces), (1, 0), (0, 0)], "undo went %s" % states
    while bpy.ops.ed.redo.poll():
        bpy.ops.ed.redo()
    assert state() == (1, faces) and bpy.data.objects["Arm"].mode == "OBJECT", "redone to %s" % (state(),)


def test_override_of_a_character_without_regions():
    """A character linked from a file without Kneady, then overridden.
    Blender would not keep a region added to the override: an added list
    item is gone once the file is saved and opened. So + says where regions
    are made instead."""
    core = rigs.kneady()
    bpy.ops.wm.read_homefile(use_empty=True)
    rig, mesh = rigs.arm_rig("Arm")
    char = bpy.data.collections.new("Character")
    bpy.context.scene.collection.children.link(char)
    for o in (rig, mesh):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        char.objects.link(o)
    os.makedirs(OUTPUT, exist_ok=True)
    source = os.path.join(OUTPUT, "plain_character.blend")
    bpy.ops.wm.save_as_mainfile(filepath=source)
    bpy.ops.wm.read_homefile(use_empty=True)
    _rig, mesh = test_linked._override(test_linked._link(source))
    mesh.override_library.is_system_override = False
    why = core.regions_fixed(mesh)
    assert why and "plain_character.blend" in why, "why: %r" % why
    _select_only(mesh)
    assert bpy.ops.kneady.region_add() == {"CANCELLED"}, "a region added to an override"
    assert not core.regions_of(mesh)
