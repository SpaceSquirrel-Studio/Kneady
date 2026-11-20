"""Asset 3 where The Look of Your Buttons leaves it: the Rigify arm's
Forearm region with its buttons in a Column (Bend and Reach square, FK a
text button), Labels set to Always and Highlight to Outline. It is for
Buttons on the Item.

    blender --background --factory-startup --python dev/scenes/arm_toggle.py
    blender --background --factory-startup --python dev/scenes/arm_look.py

Saved as tutorials/_scenes/arm_look.blend, starting from arm_toggle.blend
as that was last made.
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

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "arm_toggle.blend"), load_ui=False)
scene = bpy.context.scene
region = bpy.data.objects["Arm"].kneady.regions[0]
bend, reach, fk = region.buttons[0], region.buttons[1], region.buttons[2]
region.arrange = "COLUMN"
scene.kneady_labels = "ALWAYS"
scene.kneady_highlight = "OUTLINE"
fk.icon_type = "TEXT"
bend.shape = reach.shape = "SQUARE"
assert not any(b.placed for b in region.buttons), "a button starts on the item"
print("LOOK %s; %s" % (region.arrange, [(b.name, b.shape, b.icon_type) for b in region.buttons[:3]]))
common.save("arm_look")
