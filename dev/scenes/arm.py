"""Asset 3, the arm: a left arm and hand rigged with Rigify, with the upper
arm, the forearm, a hand with four fingers and a thumb, and the IK/FK
switch Rigify gives an arm. It is for the tutorials on toggles, the look of
buttons, buttons placed on the item, and 3D handles.

    blender --background --factory-startup --python dev/scenes/arm.py

Saved as tutorials/_scenes/arm.blend: the mesh Arm, skinned to the rig Rig.
The bones have Rigify's names (upper_arm_fk.L, forearm_fk.L, hand_ik.L, the
fingers' f_index.01.L ...), and the IK/FK switch is the property IK_FK on
upper_arm_parent.L. The arm stands as it does in Rigify's Human, moved so
its middle is near the world's origin.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import rigify_body as rb  # noqa: E402

PARTS = {"shoulder", "upper_arm", "forearm", "hand", "palm", "thumb"} | set(rb.FINGERS)
OFFSET = (0.49, 0.03, 1.37)           # the arm's middle in Rigify's Human, moved to the origin


def keep(name):
    return name.endswith(".L") and name.split(".")[0] in PARTS


meta = rb.metarig(keep, OFFSET)
skin = rb.skin_body(meta, "ArmSkin", skip={"shoulder"})
hand = rb.hands_object(meta, "Hand", [".L"])
arm = rb.join([skin, hand], "Arm")
rig = rb.generate(meta, "Rig")
unweighted = rb.skin_to(arm, rig)
print("ARM %d vertices, %d faces; deform bones with no vertices: %s" % (
    len(arm.data.vertices), len(arm.data.polygons), unweighted or "none"))
common.save("arm")
