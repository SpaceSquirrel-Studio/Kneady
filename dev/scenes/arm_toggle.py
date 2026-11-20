"""Asset 3 where Toggles and Show When leaves it: the Rigify arm's Forearm
region with three buttons:

- Bend, turning the FK forearm, shown only while FK is on (While On);
- Reach, moving the IK hand, shown only while FK is off (While Off);
- FK, a toggle switching Rigify's IK_FK on the rig.

It is for The Look of Your Buttons.

    blender --background --factory-startup --python dev/scenes/arm_forearm.py
    blender --background --factory-startup --python dev/scenes/arm_toggle.py

Saved as tutorials/_scenes/arm_toggle.blend, starting from
arm_forearm.blend as that was last made.
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

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "arm_forearm.blend"), load_ui=False)
arm, rig = bpy.data.objects["Arm"], bpy.data.objects["Rig"]
region = arm.kneady.regions[0]
region.button_count = 3
bend, reach, fk = region.buttons[0], region.buttons[1], region.buttons[2]
fk.name = "FK"
fk.action = "TOGGLE"                   # this makes its switch a Property command (props._action_changed)
fk.switch.target = rig
fk.switch.data_path = 'pose.bones["upper_arm_parent.L"]["IK_FK"]'
bend.show_when, bend.when_toggle = "ON", "FK"
reach.show_when, reach.when_toggle = "OFF", "FK"
channel = kneady.core.Channel(fk.switch, arm, region, switch=True)
assert channel.ok, channel.why
print("BUTTONS %s" % [(b.name, b.action, b.show_when) for b in region.buttons[:3]])
common.save("arm_toggle")
