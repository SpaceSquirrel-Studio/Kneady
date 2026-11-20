"""Asset 3 ready for Toggles and Show When: the Rigify arm with Kneady on and
a Forearm region (the faces mostly weighted to the forearm's deform bones).
The region has two buttons:

- Bend turns the FK forearm (forearm_fk.L);
- Reach moves the IK hand (hand_ik.L).

Each works in only one of the arm's modes. The arm starts in IK, as Rigify
makes it.

    blender --background --factory-startup --python dev/scenes/arm.py
    blender --background --factory-startup --python dev/scenes/arm_forearm.py

Saved as tutorials/_scenes/arm_forearm.blend. It starts from arm.blend as
that was last made, and uses Kneady's own functions.
"""

import importlib
import os
import sys

import bpy  # type: ignore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

sys.path.insert(0, os.path.dirname(common.REPO))
kneady = importlib.import_module(os.path.basename(common.REPO))
kneady.register()
core = kneady.core

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "arm.blend"), load_ui=False)
arm, rig = bpy.data.objects["Arm"], bpy.data.objects["Rig"]
region = core.new_region(arm, "Forearm")
faces = core.group_faces(arm, ["DEF-forearm.L", "DEF-forearm.L.001"])
core.tag_faces(arm.data, faces, region.id)
region.button_count = 2
bend, reach = region.buttons[0], region.buttons[1]
bend.name, reach.name = "Bend", "Reach"
for drag in (bend.up, bend.across, reach.up, reach.across):
    drag.enabled = False
    drag.target, drag.bone = None, ""
bend.up.enabled, bend.up.kind, bend.up.axis = True, "ROTATE", "X"
bend.up.target, bend.up.bone = rig, "forearm_fk.L"
for drag, axis in ((reach.across, "X"), (reach.up, "Z")):
    drag.enabled, drag.kind, drag.axis = True, "MOVE", axis
    drag.target, drag.bone = rig, "hand_ik.L"
bpy.context.scene.kneady_on = True
assert rig.pose.bones["upper_arm_parent.L"]["IK_FK"] < 0.5, "Rigify's arm starts in IK"
print("REGION %s (id %d): %d faces; %s, %s" % (region.name, region.id, len(faces), bend.name, reach.name))
common.save("arm_forearm")
