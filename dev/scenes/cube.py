"""Asset 1, the cube: Blender's own default scene, with the cube, camera and
light everyone sees on starting Blender. It is for Quick Start and the
tutorials that begin as simply.

    blender --background --factory-startup --python dev/scenes/cube.py

Saved as tutorials/_scenes/cube.blend. Its names are Blender's: Cube,
Camera, Light.
"""

import os
import sys

import bpy  # type: ignore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

bpy.ops.wm.read_homefile(use_factory_startup=True)
assert sorted(o.name for o in bpy.data.objects) == ["Camera", "Cube", "Light"], [o.name for o in bpy.data.objects]
common.save("cube")
