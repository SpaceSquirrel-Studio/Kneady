"""What the practice-scene scripts (dev/scenes/*.py) share: where the scenes
go, and how one is saved. They go in tutorials/_scenes/, shared by every
tutorial that names one as "../_scenes/<name>.blend".

Run every scene script with the oldest Blender Kneady supports (4.2), so
every supported Blender can open what it saves:

    blender --background --factory-startup --python dev/scenes/<scene>.py

Each scene is made from nothing every time, so it can be made again
whenever Kneady or Blender changes. Use only what is made here or ships
with Blender (such as Rigify), because a scene ships with Kneady, under
Kneady's license.
"""

import os

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCENES = os.path.join(REPO, "tutorials", "_scenes")
OLDEST = (4, 2)


def save(name):
    """Save the open file as tutorials/_scenes/<name>.blend, compressed, with
    nothing packed or linked from elsewhere. Returns its path."""
    os.makedirs(SCENES, exist_ok=True)
    path = os.path.join(SCENES, name + ".blend")
    for text in list(bpy.data.texts):            # a scene runs no Python (Rigify's rig_ui.py included)
        bpy.data.texts.remove(text)
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 left beside it
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True, relative_remap=False)
    version = tuple(bpy.app.version[:2])
    note = "" if version <= OLDEST else "  NOTE: saved by %d.%d - Blender %d.%d may not open it" % (
        version + OLDEST)
    print("SAVED %s (%d KB)%s" % (path, os.path.getsize(path) // 1024, note))
    return path
