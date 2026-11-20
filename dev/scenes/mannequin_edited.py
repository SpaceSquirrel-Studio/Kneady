"""Asset 4 where Viewport Edit leaves it, for Copy and Reuse. Kneady is on,
the rig is hidden, and the mannequin has:

- the head's buttons Nod, Tilt (added, and driving nothing yet) and Turn;
- the chest's Bend and Twist, with its Spare menu gone;
- a Hips region (the waist and pelvis) with one button that drives
  nothing, to paste onto.

    blender --background --factory-startup --python dev/scenes/mannequin_controls.py
    blender --background --factory-startup --python dev/scenes/mannequin_edited.py

Saved as tutorials/_scenes/mannequin_edited.blend, starting from
mannequin_controls.blend as that was last made. It uses Kneady's own
functions - the ones Viewport Edit's +, Rearrange and - call.
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

HIPS = (1.0, 1.2, 0.2)               # the hips' faces: from, to (meters up), how far out to the side

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "mannequin_controls.blend"), load_ui=False)
man = bpy.data.objects["Mannequin"]
head, chest = man.kneady.regions[0], man.kneady.regions[1]

# Viewport Edit's steps: Tilt added and put second, Spare removed with its menu
index, why = core.add_button(bpy.context, head)
assert index == 2, why
head.buttons[index].name = "Tilt"
core.swap_buttons(head, 2, 1)
spare = [b.name for b in core.buttons_of(chest)].index("Spare")
why = core.remove_button(chest, core.list_of(chest, spare), spare)
assert not why, why

# the Hips, to paste the chest's buttons onto
centers = {p.index: man.matrix_world @ p.center for p in man.data.polygons}
faces = [i for i, c in centers.items() if HIPS[0] < c.z < HIPS[1] and abs(c.x) < HIPS[2]]
hips = core.new_region(man, "Hips")
core.tag_faces(man.data, faces, hips.id)
hips.button_count = 1
first = hips.buttons[0]
first.up.enabled = first.across.enabled = False            # a new region's first button turns the mannequin itself
for region in man.kneady.regions:
    print("REGION %s (id %d): %s" % (region.name, region.id, [b.name for b in core.buttons_of(region)]))
print("HIPS %d faces" % len(faces))
bpy.context.scene.kneady_on = True
common.save("mannequin_edited")
