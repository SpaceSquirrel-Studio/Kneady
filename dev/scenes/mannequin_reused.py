"""Asset 4 where Copy and Reuse leaves it, for Tips for Your Buttons. Kneady
is on, the rig is hidden, and the mannequin has:

- the head's Nod, which opens a menu holding Tilt (Turn's commands, but
  about the head's Z), and Turn beside it;
- the chest's Bend and Twist;
- the hips' own Bend and Twist, on the hips bone.

    blender --background --factory-startup --python dev/scenes/mannequin_edited.py
    blender --background --factory-startup --python dev/scenes/mannequin_reused.py

Saved as tutorials/_scenes/mannequin_reused.blend, starting from
mannequin_edited.blend as that was last made. It uses the functions that
Copy and Reuse's Paste Commands, Move To and Paste All Buttons call.
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
menu_build = importlib.import_module(kneady.__name__ + ".menu_build")

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "mannequin_edited.blend"), load_ui=False)
man = bpy.data.objects["Mannequin"]
head, chest, hips = man.kneady.regions
nod, tilt, turn = head.buttons[0], head.buttons[1], head.buttons[2]

# Turn's commands on Tilt, about Z; Tilt in Nod's menu
assert core.paste_commands(tilt, {"data": core.commands_data(turn)}) is None
tilt.across.axis = "Z"
nod.opens_menu = True
why = menu_build.move_to(bpy.context, head, 1, menu_build.menu_key(nod))
assert not why, why

# the chest's buttons on the hips, turning the hips
assert core.paste_region(hips, {"data": core.to_data(chest)}) is None
hips.buttons[0].up.bone = hips.buttons[1].across.bone = "hips"
for region in (head, chest, hips):
    for b in core.buttons_of(region):
        for d in (b.up, b.across):
            if d.enabled:
                channel = core.Channel(d, man, region)
                assert channel.ok, channel.why
    print("REGION %s: %s" % (region.name, [(b.name, b.menu_parent) for b in core.buttons_of(region)]))
bpy.context.scene.kneady_on = True
common.save("mannequin_reused")
