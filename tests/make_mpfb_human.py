"""Make the MPFB2 test characters, saved into the test assets (rigs.asset):

- mpfb_human.blend - a human with MPFB2's standard rig (137 bones) and
  MPFB2's shape keys (its body-shape targets: what load_face_shape_keys
  gives on a fresh human)
- mpfb_rigify_human.blend - the same human with a Rigify rig (930 bones)

    blender --background --factory-startup --python tests/make_mpfb_human.py

Needs MPFB2 (extensions.blender.org) installed in the Blender that runs it;
Rigify comes with Blender. Run once, or again to remake them; the tests open
the files rather than generating them each run.

MPFB2 adds its Rigify metarig hidden in the viewport, and Rigify will not
generate from a hidden armature ("Cannot edit hidden object"), so it is shown
first.
"""

import os
import sys

import addon_utils  # type: ignore
import bpy  # type: ignore


def _human():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.mpfb.create_human()
    body = bpy.context.active_object
    bpy.ops.mpfb.load_face_shape_keys()
    return body


def _report(path):
    rigs = [(o.name, len(o.data.bones)) for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [(o.name, len(o.data.vertices), [m.type for m in o.modifiers],
               len(o.data.shape_keys.key_blocks) if o.data.shape_keys else 0)
              for o in bpy.data.objects if o.type == "MESH"]
    print("MAKE %s: armatures %s, meshes %s" % (os.path.basename(path), rigs, meshes))


def main():
    root = os.environ.get("KNEADY_TEST_ASSETS") or os.path.join(os.path.expanduser("~"), "Documents",
                                                                "Kneady test assets")
    os.makedirs(root, exist_ok=True)
    for module in ("rigify", "bl_ext.blender_org.mpfb"):
        addon_utils.enable(module, default_set=True)

    _human()
    bpy.ops.mpfb.add_standard_rig()
    path = os.path.join(root, "mpfb_human.blend")
    _report(path)
    bpy.ops.wm.save_as_mainfile(filepath=path)

    _human()
    bpy.ops.mpfb.add_rigify_rig()
    metarig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    metarig.hide_viewport = False
    metarig.hide_set(False)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    metarig.select_set(True)
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.mpfb.generate_rigify_rig()
    path = os.path.join(root, "mpfb_rigify_human.blend")
    _report(path)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    sys.stdout.flush()


main()
os._exit(0)
