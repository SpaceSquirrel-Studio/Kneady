"""Asset 4 ready for Viewport Edit: the mannequin with Kneady on, the rig
hidden (its widgets with it), and two regions:

- Head (the head, down to the top of its neck), with Nod turning the head
  control up and down, and Turn turning it left and right;
- Chest (the torso from the waist to under the arms), with Bend and Twist
  on the chest control, and Spare - a menu left over from an earlier
  layout, holding two buttons that drive nothing.

    blender --background --factory-startup --python dev/scenes/mannequin.py
    blender --background --factory-startup --python dev/scenes/mannequin_controls.py

Saved as tutorials/_scenes/mannequin_controls.blend, starting from
mannequin.blend as that was last made, by Kneady's own functions. Each
region's faces are picked by where they sit at rest, not by weight, because
a skinned mesh's weights blur across the neck and waist.
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

HEAD_FROM = 1.72                      # meters up: the head's faces start a little under its jaw
CHEST = (1.2, 1.56, 0.19)             # the chest's faces: from, to, and how far out to the side

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "mannequin.blend"), load_ui=False)
man, rig = bpy.data.objects["Mannequin"], bpy.data.objects["Rig"]
centers = {p.index: man.matrix_world @ p.center for p in man.data.polygons}
parts = {
    "Head": [i for i, c in centers.items() if c.z > HEAD_FROM],
    "Chest": [i for i, c in centers.items() if CHEST[0] < c.z < CHEST[1] and abs(c.x) < CHEST[2]],
}
# each button: name, bone, drag direction, axis. Up the spine is the chest
# control's Z but the head's Y; X bends both forward and back
BUTTONS = {
    "Head": (("Nod", "head", "up", "X"), ("Turn", "head", "across", "Y")),
    "Chest": (("Bend", "chest", "up", "X"), ("Twist", "chest", "across", "Z")),
}
for name, faces in parts.items():
    region = core.new_region(man, name)
    core.tag_faces(man.data, faces, region.id)
    region.button_count = len(BUTTONS[name])
    for button, (label, bone, direction, axis) in zip(region.buttons, BUTTONS[name]):
        button.name = label
        for drag in (button.up, button.across):
            drag.enabled, drag.target, drag.bone = False, None, ""
        drag = getattr(button, direction)
        drag.enabled, drag.kind, drag.axis = True, "ROTATE", axis
        drag.target, drag.bone = rig, bone
        channel = core.Channel(drag, man, region)
        assert channel.ok, channel.why
    print("REGION %s (id %d): %d faces; %s" % (name, region.id, len(faces), [b.name for b in core.buttons_of(region)]))

# the chest's Spare: a menu of two buttons that drive nothing, there for the
# tutorial to remove
chest = man.kneady.regions[1]
index, why = core.add_button(bpy.context, chest)
assert index is not None, why
spare = chest.buttons[index]
spare.name = "Spare"
for k in range(2):
    why = menu_build.add_to_menu(bpy.context, chest, index)
    assert not why, why
inside = [b for b in core.buttons_of(chest) if b.menu_parent == spare.uid]
for k, button in enumerate(inside):
    button.name = "Spare %d" % (k + 1)
print("MENU %s: %s" % (spare.name, [b.name for b in inside]))
# hide Rigify's widgets: they ring every limb, and these controls pose by the
# surface instead (a hidden rig still poses its mesh)
rig.hide_set(True)
bpy.context.scene.kneady_on = True
common.save("mannequin_controls")
