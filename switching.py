"""Switching without a jump. An IK / FK toggle that only flips its switch
makes the limb leap to wherever the other chain was. Animators expect it to
stay put, and the other chain to take over from there. This uses each rig's
own snapping, in two ways:

- Keep Pose: as the switch flips, each bone of a list takes its partner's
  pose. Switching to FK, the FK bones take the IK bones' poses. Switching to
  IK, the IK bones take the FK bones' poses, and then the pole is set where
  the elbow points. Bones on the Keep list stay where they are (for a parent
  switch). The lists are the rig's own snap maps (a CloudRig rig declares
  them for its panel). Keep Pose needs no script from the rig, so it runs
  with the file's scripts off.
- Run Operator: the rig's own operator, run with its arguments, for a rig
  whose snap operator runs on its own. It works on a drag button too: its
  click runs it. An operator that opens, saves or runs files, or changes
  Blender's own settings, is never run from a file (UNSAFE).

Greg wanted this in the free Kneady: "Definitely Keep Pose playing in
free"."""

import ast
import math

import bpy  # type: ignore
from mathutils import Matrix  # type: ignore

from . import core, errors

# Operator groups a button never runs: those that open, save, load or run
# files and scripts, or change the preferences. A file names its buttons'
# operators, and a click should not do anything opening the file would not.
UNSAFE = {"wm", "script", "file", "preferences", "extensions", "text", "console", "screen", "info", "ui",
          "buttons", "image", "sound", "clip", "render", "sequencer", "outliner", "asset", "cachefile"}


def _pairs(text):
    """A list of (bone, partner) from its text, or []."""
    try:
        value = ast.literal_eval(text) if text else []
        return [(str(a), str(b)) for a, b in value]
    except (ValueError, SyntaxError, TypeError):
        return []


def _names(text):
    try:
        value = ast.literal_eval(text) if text else []
        return [str(v) for v in value]
    except (ValueError, SyntaxError, TypeError):
        return []


def rig_of(button, obj):
    """The armature a toggle switches on: its switch's target, else the one
    deforming the object hovered."""
    target = button.switch.target or obj
    if target is not None and target.type != "ARMATURE":
        target = core.mesh_rig(target)
    return target if target is not None and target.type == "ARMATURE" else None


def keeps_pose(button):
    return bool(button.snap_on or button.snap_off or button.snap_keep)


def pole_point(rig, chain, pole):
    """Where an IK pole goes so the limb bends as the chain does: out from
    the middle joint, away from the line between the chain's ends, as far
    as the chain is long. None for a chain too straight to say."""
    pb = rig.pose.bones
    if len(chain) < 3 or any(n not in pb for n in chain) or pole not in pb:
        return None
    a, b, c = (pb[n].head for n in chain[:3])
    line = c - a
    if line.length < 1e-9:
        return None
    foot = a + line * ((b - a).dot(line) / line.length_squared)
    out = b - foot
    if out.length < 1e-4 * line.length:
        return None
    return b + out.normalized() * ((b - a).length + (c - b).length)


def switch_keeping_pose(context, button, obj, channels, on):
    """Switch the toggle's channels. The bones of its Keep Pose lists take
    their partners' poses (or keep their own), and the pole is set after
    switching on. Returns whether it ran."""
    rig = rig_of(button, obj)
    if rig is None:
        return False
    pb = rig.pose.bones
    pairs = [(a, b) for a, b in _pairs(button.snap_on if on else button.snap_off) if a in pb and b in pb]
    pairs += [(a, a) for a in _names(button.snap_keep) if a in pb]
    context.view_layer.update()
    poses = [(a, pb[b].matrix.copy()) for a, b in pairs]
    pole = _names(button.snap_pole) if on else []
    point = pole_point(rig, pole[1:], pole[0]) if pole else None
    # The chain's joints as they are before the switch. A switch's own map
    # may move the FK chain (a hinge swapping with its parent), so these are
    # what the pole aims for.
    joints = [pb[n].head.copy() for n in pole[1:4]] if point is not None else None
    core.switch(channels, on)
    context.view_layer.update()
    for _round in range(2):
        # Twice, because a chain's children follow their parents' new poses
        for name, matrix in poses:
            pb[name].matrix = matrix
            context.view_layer.update()
    _past_constraints(context, pb, poses)
    if point is not None:
        m = pb[pole[0]].matrix.copy()
        m.translation = point
        pb[pole[0]].matrix = m
        context.view_layer.update()
        if len(pole) >= 5 and pole[4] in pb:
            _turn_pole(context, rig, pole, joints)
    return True


def _past_constraints(context, pb, poses, rounds=4):
    """Put each bone where it was meant to go, even when a constraint of its
    own moves it after its pose. Setting a bone's matrix leaves its
    constraints out, so a bone that a switch reparents through an Armature or
    Child Of constraint jumped. Found on CloudRig's eye target, whose parent
    is set by a constraint's four weights. So the pose is corrected for what
    the constraints added: each round, the pose is followed by the difference
    between where the bone is and where it should be, until it is there."""
    for _round in range(rounds):
        off = False
        for name, matrix in poses:
            bone = pb[name]
            now = bone.matrix
            if (now.translation - matrix.translation).length < 1e-6 and \
                    now.to_quaternion().rotation_difference(matrix.to_quaternion()).angle < 1e-5:
                continue
            try:
                bone.matrix_basis = bone.matrix_basis @ now.inverted() @ matrix
            except ValueError:          # a matrix that cannot be inverted: left as it is
                continue
            off = True
            context.view_layer.update()
        if not off:
            return


def turn_between(a, c, now, wanted):
    """The signed angle about the line from `a` to `c` that takes `now` to
    `wanted`, each seen square on to the line."""
    u = (c - a).normalized()
    x = (now - a) - u * (now - a).dot(u)
    y = (wanted - a) - u * (wanted - a).dot(u)
    if x.length < 1e-9 or y.length < 1e-9:
        return 0.0
    return math.atan2(u.dot(x.cross(y)), x.dot(y))


def _turn_pole(context, rig, pole, joints):
    """Turn the pole until the IK chain bends where the FK chain did. An IK
    chain may aim its bend at the pole at an angle (its Pole Angle), so the
    pole is turned about the limb's line until the IK chain's middle joint
    (its first bone's tail) is where the FK chain's was before the switch
    (`joints`). Each round turns it by the angle between them about that
    line, until they meet."""
    pb = rig.pose.bones
    pole_bone, ik_first = pb[pole[0]], pb[pole[4]]
    a, b, c = joints
    if (c - a).length < 1e-9:
        return
    for _round in range(6):
        context.view_layer.update()
        angle = turn_between(a, c, ik_first.tail.copy(), b)
        if abs(angle) < 1e-5:
            break
        m = pole_bone.matrix.copy()
        m.translation = a + Matrix.Rotation(angle, 3, c - a) @ (m.translation - a)
        pole_bone.matrix = m
    context.view_layer.update()


def operator_problem(idname):
    """Why a button may not run the operator `idname`, or ""."""
    idname = idname.strip()
    if "." not in idname:
        return "No operator"
    group = idname.split(".", 1)[0]
    if group in UNSAFE or group.startswith(("import", "export")):
        return "%s is not run from a button: it works on files, scripts or Blender's own settings" % idname
    return ""


def run_operator(context, button, obj):
    """Run a button's operator (run_operator) with its arguments, on its rig
    (or the object hovered) as the active object. Returns (ran, why)."""
    idname = button.run_operator.strip()
    why = operator_problem(idname)
    if why:
        return False, why
    group, name = idname.split(".", 1)
    op = getattr(getattr(bpy.ops, group, None), name, None)
    if op is None:
        return False, "No operator %s" % idname
    try:
        kwargs = ast.literal_eval(button.run_operator_args) if button.run_operator_args.strip() else {}
    except (ValueError, SyntaxError):
        return False, "Its arguments are not a Python dictionary"
    if not isinstance(kwargs, dict):
        return False, "Its arguments are not a Python dictionary"
    target = rig_of(button, obj) or obj
    if target is None:
        # said plainly here: inside the try below it would read as the rig's
        # operator failing
        return False, "Nothing to run %s on: no rig is set, and no object is hovered" % idname
    try:
        with context.temp_override(active_object=target, object=target):
            if not op.poll():
                return False, "%s cannot run here%s" % (idname, " (it may need Pose mode)" if
                                                         target.mode != "POSE" else "")
            result = op("EXEC_DEFAULT", **kwargs)
    except Exception as exc:            # the rig's operator failed: told on the button, traced once
        errors.caught("Run Operator %s" % idname)
        return False, str(exc).strip().splitlines()[-1] if str(exc).strip() else type(exc).__name__
    return "FINISHED" in result, "" if "FINISHED" in result else "%s did nothing" % idname


def _switcher(context, button, obj, region, channels, on):
    if button.run_operator.strip():
        ran, why = run_operator(context, button, obj)
        if ran:
            return True
        print("Kneady: %s: %s; switched without it" % (button.name, why))
    if keeps_pose(button):
        return switch_keeping_pose(context, button, obj, channels, on)
    return False


def _clicked(context, obj, region, index):
    used = core.buttons_of(region)
    if not (0 <= index < len(used)):
        return False
    button = used[index]
    if button.action == "TOGGLE" or not button.run_operator.strip() or button.opens_menu:
        return False
    if core.click_shift():
        return False                       # Shift+click pins the region (core.toggle_kept)
    ran, why = run_operator(context, button, obj)
    if not ran:
        print("Kneady: %s: %s" % (button.name, why))
    core.redraw()
    return True


def register():
    core.add_switcher(_switcher)
    core.add_click_hook(_clicked)


def unregister():
    core.remove_click_hook(_clicked)
    core.remove_switcher(_switcher)
