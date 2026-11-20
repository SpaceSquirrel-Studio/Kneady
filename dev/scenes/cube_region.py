"""Asset 1 where Quick Start leaves it: Blender's default scene with Kneady
on and the cube's top face made a region, Region 1. Its first button turns
the cube as a new region's always does: up and down about X, left and right
about Y. It is for the tutorials that start from there, Change the Default
Controls first.

    blender --background --factory-startup --python dev/scenes/cube_region.py

Saved as tutorials/_scenes/cube_region.blend. It is made by Kneady's own
functions (core.new_region, core.tag_faces), so the button is exactly what
+ makes.
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

bpy.ops.wm.read_homefile(use_factory_startup=True)
cube = bpy.data.objects["Cube"]
region = core.new_region(cube)
top = [f.index for f in cube.data.polygons if f.normal.z > 0.99]
assert len(top) == 1, top
core.tag_faces(cube.data, top, region.id)
bpy.context.scene.kneady_on = True
first = region.buttons[0]
print("REGION %s (id %d), %d button(s); %s: up %s %s, across %s %s" % (
    region.name, region.id, len(region.buttons), first.name, first.up.kind, first.up.axis,
    first.across.kind, first.across.axis))
common.save("cube_region")
