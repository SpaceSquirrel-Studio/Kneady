"""Asset 2 where Build a Menu leaves it, with the menu made to work. The
shape cube's Button 1 opens a menu of two text buttons in one color:

- Round, hauled up and down, rounds the cube (the Sphere shape key);
- Twist, hauled left and right, twists it (the Twist modifier input).

It is for Menus in Use.

    blender --background --factory-startup --python dev/scenes/shape_cube_controls.py
    blender --background --factory-startup --python dev/scenes/shape_cube_menu.py

Saved as tutorials/_scenes/shape_cube_menu.blend. It starts from
shape_cube_controls.blend as that was last made, and the menu is built by
Kneady's own Add to Its Menu.
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
menu_build = importlib.import_module(kneady.__name__ + ".menu_build")

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "shape_cube_controls.blend"), load_ui=False)
cube = bpy.data.objects["Cube"]
region = cube.kneady.regions[0]
for _ in range(2):
    why = menu_build.add_to_menu(bpy.context, region, 0)
    assert not why, why
first, round_, twist = region.buttons[0], region.buttons[1], region.buttons[2]
first.menu_use_color, first.menu_color = True, (0.016, 0.115, 1.0)       # the blue Build a Menu picked
round_.name, twist.name = "Round", "Twist"
for button in (round_, twist):
    button.icon_type = "TEXT"
round_.up.enabled, round_.up.kind = True, "PROPERTY"
round_.up.data_path = 'data.shape_keys.key_blocks["Sphere"].value'
twist.across.enabled, twist.across.kind, twist.across.input = True, "INPUT", "Twist"
for command in (round_.up, twist.across):
    channel = kneady.core.Channel(command, cube, region)
    assert channel.ok, channel.why
print("MENU on %s: %s" % (first.name, [(b.name, b.menu_parent == first.uid) for b in region.buttons[1:3]]))
common.save("shape_cube_menu")
