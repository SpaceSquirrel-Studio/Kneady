"""Asset 2 ready for controls: the shape cube (dev/scenes/shape_cube.py)
with Kneady on and the whole cube made one region, Region 1. Its first
button turns the cube as a new region's always does. It is for Drive More
Than Bones, which gives that button a shape key and a modifier input to
drive.

    blender --background --factory-startup --python dev/scenes/shape_cube.py
    blender --background --factory-startup --python dev/scenes/shape_cube_region.py

Saved as tutorials/_scenes/shape_cube_region.blend. It starts from
shape_cube.blend as that was last made, and uses Kneady's own functions
(core.new_region), so the button is exactly what + makes.
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

bpy.ops.wm.open_mainfile(filepath=os.path.join(common.SCENES, "shape_cube.blend"), load_ui=False)
cube = bpy.data.objects["Cube"]
region = core.new_region(cube, whole=True)
bpy.context.scene.kneady_on = True
first = region.buttons[0]
print("REGION %s (id %d), whole %s; %s: up %s %s, across %s %s" % (
    region.name, region.id, region.whole, first.name, first.up.kind, first.up.axis, first.across.kind,
    first.across.axis))
common.save("shape_cube_region")
