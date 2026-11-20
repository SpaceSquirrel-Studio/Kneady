"""Switching without a jump: the panel that sets it up. This was part of
Kneady Pro until it moved here.

An IK / FK toggle that only flips its switch makes the limb leap to wherever
the other chain was. Animators expect it to stay put, and the other chain to
take over from there. Greg chose to use each rig's own snapping, so a toggle
can do it two ways:

- Keep Pose: as the switch flips, each bone of a list takes its partner's
  pose. Switching to FK, the FK bones take the IK bones' poses. Switching to
  IK, the IK bones take the FK bones' poses, and then the pole is set where
  the elbow points. Bones on the Keep list stay where they are (for a parent
  switch). The lists are the rig's own snap maps: a CloudRig rig declares
  them for its panel (Rain's map_fk_to_ik, map_ik_to_fk and ik_pole), so a
  template copies them in.
- Run Operator: the rig's own operator, run with its arguments, for a rig
  whose snap operator runs on its own. Run Operator works on a drag button
  too: its click runs it.

Playing them is switching.py's job. This module is the panel that sets
them."""

from . import ui as kn_ui
# Re-exported on purpose: these names live in switching.py, and are reached through
# this module too, so Kneady Pro and the tests can use either. The noqa
# marker tells linters they are not unused imports.
from .switching import (keeps_pose, pole_point, rig_of, run_operator, switch_keeping_pose,  # noqa: F401
                                turn_between)


def draw_button(layout, context, region, button):
    """Draw a toggle's Keep Pose lists, and any button's operator."""
    if button.action == "TOGGLE":
        box = layout.box()
        box.label(text="Keep Pose on Switch", icon="CON_TRANSLIKE")
        col = box.column(align=True)
        col.prop(button, "snap_on", text="On")
        col.prop(button, "snap_off", text="Off")
        col.prop(button, "snap_keep", text="Keep")
        col.prop(button, "snap_pole", text="Pole")
    row = layout.row(align=True)
    row.prop(button, "run_operator", text="", icon="SCRIPTPLUGINS")
    if button.run_operator:
        row.prop(button, "run_operator_args", text="")


def register():
    kn_ui.BUTTON_EXTRAS.append(draw_button)


def unregister():
    if draw_button in kn_ui.BUTTON_EXTRAS:
        kn_ui.BUTTON_EXTRAS.remove(draw_button)
