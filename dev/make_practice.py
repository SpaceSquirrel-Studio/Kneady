"""Make the Getting Started tutorial's practice scene from nothing, at
tests/tutorials/getting_started/practice.blend. It holds an arm rig of two
bones and an arm mesh skinned to it, with two regions: Forearm turns the
Lower bone and Upper Arm turns the Upper bone. Kneady is left off.

Getting Started no longer ships, since Greg's Quick Start became the first
tutorial. It stays in tests/tutorials as the tests' own tutorial, and its
arm is the scene the tests run in.

Run it with the oldest Blender Kneady supports, so every supported version
can open the file:

    blender --background --factory-startup --python dev/make_practice.py

Keep the names as they are: the tutorial's checks and starts refer to
ArmRig, Arm, Lower and Upper by name.
"""

import importlib
import os
import sys

import bmesh  # type: ignore
import bpy  # type: ignore
from mathutils import Matrix  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "tests", "tutorials", "getting_started", "practice.blend")

sys.path.insert(0, os.path.dirname(REPO))
kneady = importlib.import_module(os.path.basename(REPO))
kneady.register()
core = kneady.core

bpy.ops.wm.read_homefile(use_empty=True)
scene = bpy.context.scene

# the rig: Upper from 0 to 1, Lower from 1 to 2, along Z
arm_data = bpy.data.armatures.new("ArmRig")
rig = bpy.data.objects.new("ArmRig", arm_data)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
upper = arm_data.edit_bones.new("Upper")
upper.head, upper.tail = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
lower = arm_data.edit_bones.new("Lower")
lower.head, lower.tail = (0.0, 0.0, 1.0), (0.0, 0.0, 2.0)
lower.parent, lower.use_connect = upper, True
bpy.ops.object.mode_set(mode="OBJECT")
arm_data.display_type = "STICK"

# the arm: a capped tube with a ring every 0.125, each vertex weighted to the
# bone beside it
me = bpy.data.meshes.new("Arm")
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.22, radius2=0.18, depth=2.0,
                      matrix=Matrix.Translation((0.0, 0.0, 1.0)))
bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1.0],
                          cuts=15, use_grid_fill=True)
bm.to_mesh(me)
bm.free()
for poly in me.polygons:
    poly.use_smooth = True
arm = bpy.data.objects.new("Arm", me)
scene.collection.objects.link(arm)
groups = {n: arm.vertex_groups.new(name=n) for n in ("Upper", "Lower")}
for v in me.vertices:
    # a soft elbow: the rings either side of it are shared by both bones
    w = min(max((v.co.z - 0.85) / 0.3, 0.0), 1.0)
    if w < 1.0:
        groups["Upper"].add([v.index], 1.0 - w, "REPLACE")
    if w > 0.0:
        groups["Lower"].add([v.index], w, "REPLACE")
mod = arm.modifiers.new("Armature", "ARMATURE")
mod.object = rig
arm.parent = rig
sub = arm.modifiers.new("Subdivision", "SUBSURF")
sub.levels = 1

# the regions: each half turns its bone - a drag up or down turns it about X,
# a drag across about Y
for name, bone, faces in (("Forearm", "Lower", [p.index for p in me.polygons if p.center.z > 1.0]),
                          ("Upper Arm", "Upper", [p.index for p in me.polygons if p.center.z <= 1.0])):
    region = core.new_region(arm, name)
    first = region.buttons[0]
    first.name = "Bend"
    for drag, axis in ((first.up, "X"), (first.across, "Y")):
        drag.enabled, drag.kind, drag.axis, drag.target, drag.bone = True, "ROTATE", axis, rig, bone
    core.tag_faces(me, faces, region.id)

for obj in (rig, arm):
    obj.select_set(False)
bpy.context.view_layer.objects.active = arm
scene.kneady_on = False
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True, relative_remap=False)
print("WROTE %s with Blender %s" % (OUT, bpy.app.version_string))
sys.stdout.flush()
os._exit(0)
