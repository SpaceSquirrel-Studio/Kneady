"""Asset 3 where Buttons on the Item leaves it: the Rigify arm's Forearm
region with Reach placed on the item, on the side of the forearm by the
wrist, and Behind set to Ghost Behind. It is for 3D Handles.

    blender --background --factory-startup --python dev/scenes/arm_look.py
    blender --background --factory-startup --python dev/scenes/arm_on_item.py

Saved as tutorials/_scenes/arm_on_item.blend, starting from arm_look.blend
as that was last made. Reach is placed where a person would drop it: a ray
from the tutorials' view finds the forearm's side, and Kneady's own
place_at puts the button there.
"""

import importlib
import os
import sys

import bpy  # type: ignore
from mathutils import Quaternion, Vector  # type: ignore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

sys.path.insert(0, os.path.dirname(common.REPO))
kneady = importlib.import_module(os.path.basename(common.REPO))
kneady.register()

VIEW = Quaternion((0.71238, 0.44106, 0.28736, 0.46412))    # the arm tutorials' view

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "arm_look.blend"), load_ui=False)
arm, rig = bpy.data.objects["Arm"], bpy.data.objects["Rig"]
region = arm.kneady.regions[0]
reach = region.buttons[1]
bones = rig.data.bones
elbow = rig.matrix_world @ bones["DEF-forearm.L"].head_local
wrist = rig.matrix_world @ bones["DEF-forearm.L.001"].tail_local
forward, left = VIEW @ Vector((0.0, 0.0, -1.0)), VIEW @ Vector((-1.0, 0.0, 0.0))
depsgraph = bpy.context.evaluated_depsgraph_get()
shown = arm.evaluated_get(depsgraph)
to_arm = arm.matrix_world.inverted()
# the forearm's side seen from the view: a ray down the view, a little in from
# its left outline, near the wrist
aim = elbow + (wrist - elbow) * 0.9 + left * 0.022
start = to_arm @ (aim - forward * 1.0)
hit, where, normal, _face = shown.ray_cast(start, to_arm.to_3x3() @ forward)
assert hit, "the ray missed the forearm"
world, world_normal = arm.matrix_world @ where, (arm.matrix_world.to_3x3() @ normal).normalized()
assert kneady.placement.place_at(arm, region, reach, world, world_normal, depsgraph)
region.behind = "GHOST"
print("ON ITEM %s at %s, facing %s" % (reach.name, tuple(round(v, 2) for v in reach.place),
                                       tuple(round(v, 2) for v in reach.place_normal)))
common.save("arm_on_item")
