"""Asset 4, the mannequin: a whole figure rigged with Rigify's Human (no
face), with the spine, neck and head, arms with hands and fingers, and
legs. It is for the tutorials on Viewport Edit, copying controls between
limbs, and tips.

    blender --background --factory-startup --python dev/scenes/mannequin.py

Saved as tutorials/_scenes/mannequin.blend: the mesh Mannequin, skinned to
the rig Rig, standing on the ground at the origin. The bones have Rigify's
names, on both sides (.L, .R). Each arm's IK/FK switch is IK_FK on
upper_arm_parent.L / .R, and each leg's is on thigh_parent.L / .R.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import rigify_body as rb  # noqa: E402

meta = rb.metarig()
body = rb.skin_body(meta, "Body", skip={"shoulder"})
hands = rb.hands_object(meta, "Hands", [".L", ".R"])
man = rb.join([body, hands], "Mannequin")
rig = rb.generate(meta, "Rig")
unweighted = rb.skin_to(man, rig)
print("MANNEQUIN %d vertices, %d faces; deform bones with no vertices: %s" % (
    len(man.data.vertices), len(man.data.polygons), unweighted or "none"))
common.save("mannequin")
