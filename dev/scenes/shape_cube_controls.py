"""Asset 2 where Drive More Than Bones leaves it: the shape cube, the whole
of it Region 1. Its Button 1 rounds and grows the cube when dragged up and
down (the Sphere shape key, and a Scale on All), and twists it when dragged
left and right (the Twist modifier input). It is for Build a Menu, which
gives that button a menu.

    blender --background --factory-startup --python dev/scenes/shape_cube_region.py
    blender --background --factory-startup --python dev/scenes/shape_cube_controls.py

Saved as tutorials/_scenes/shape_cube_controls.blend, from
shape_cube_region.blend as it was last made.
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

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "shape_cube_region.blend"), load_ui=False)
cube = bpy.data.objects["Cube"]
button = cube.kneady.regions[0].buttons[0]
button.up.kind = "PROPERTY"
button.up.data_path = 'data.shape_keys.key_blocks["Sphere"].value'
grow = button.up.more.add()
grow.kind, grow.axis = "SCALE", "ALL"
button.across.kind = "INPUT"
button.across.input = "Twist"
for command in (button.up, grow, button.across):
    channel = kneady.core.Channel(command, cube, cube.kneady.regions[0])
    assert channel.ok, channel.why
print("BUTTON %s: up %s %s + %s %s, across %s %s" % (button.name, button.up.kind, button.up.data_path, grow.kind,
                                                    grow.axis, button.across.kind, button.across.input))
common.save("shape_cube_controls")
