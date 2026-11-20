"""Kneady's model: which regions an object has, what is under the mouse,
and what a drag drives.

Self-contained - Blender's API only - so Kneady can stand alone. A program
built on it (Digit) adds regions an object does not carry itself through a
provider: `add_provider(fn)`, fn(obj) -> [regions]."""

import math
import re

import bpy  # type: ignore
import numpy as np
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Matrix, Vector  # type: ignore
from mathutils.bvhtree import BVHTree  # type: ignore

from . import errors, props

TAG = "kneady_region"            # face INT attribute: a region's id, 0 none
BUTTON_RADIUS = 14.0               # pixels, at Medium
BUTTON_SPACING = 34.0              # center to center, at Medium
BUTTON_BLOCK = 6.0                 # the band around the row that holds its region hovered
# Button Size, one setting for all of Kneady: the buttons' radius in pixels at
# Blender's normal interface size, with their spacing and band kept in
# Medium's proportion. It is a slider from small to large, where it was once
# four sizes (Small, Medium, Large, Extra Large). Greg: "I'd like to slide
# between small and large".
BUTTON_RADIUS_MIN, BUTTON_RADIUS_MAX = 10.0, 25.0
LOCK_PIXELS = 6.0                  # Drags Prefer Single Direction decides after this
AMBIGUOUS = 0.3                    # a turn moving the point less than this along the drag: no follow
PALETTE = ((1.0, 0.52, 0.12), (0.25, 0.6, 1.0), (0.3, 0.85, 0.42), (0.75, 0.45, 1.0),
           (1.0, 0.35, 0.45), (0.2, 0.85, 0.85), (0.95, 0.85, 0.25))

#   hover   - (object name, region id or None) under the mouse
#   button  - the hovered region's button under the mouse
#   block   - the mouse is in the band around the region's row of buttons
#   held    - where a click that changed the buttons (opened a menu, flipped a
#             toggle) landed. The region stays hovered there until the mouse
#             moves off, so the change doesn't hand the hover to a neighbor
#             (hold_click)
#   kept    - the region kept hovered (keep)
#   kept_by - who keeps it: "region" for a Shift+click on a button
#             (toggle_kept), otherwise the keeping program's own word
STATE = {"hover": None, "button": None, "block": False, "dragging": False, "pinned": None, "held": None,
         "kept": None, "kept_note": "", "kept_by": "", "click_shift": False, "edit": None}
_HIT = {"key": None, "result": None}
_TAGS = {}                         # object name -> each shown face's tag
_GEOMETRY = {}                     # object name -> {region id: (points, lo, hi)}
_PROVIDERS = []
_EDITORS = []
_REDIRECTS = []
_BVH = {}                          # object name -> (geometry dict, BVH of its regions, region id per triangle)
_EDGES = {}                        # object name -> (geometry dict, {region id: its edges, region_edges})
_WHOSE = {}                        # object name -> whose geometry the caches under it hold (_whose)
ON_ENABLE = []                     # callables(scene), when Kneady is turned on
FORGET_HOOKS = []                  # callables(name or None), when forget drops what is cached
# What the panel calls a control. A program using Kneady may rename it in its
# own terms (set_term): Digit says "Deform Hovered Digit", Greg's name for it
# (it was once "The One Dragged").
_DEFAULT_TERMS = {"dragged": "Deform Hovered Object", "group": "Group"}
TERMS = dict(_DEFAULT_TERMS)


def term(key):
    return TERMS.get(key, key)


# The modes Kneady works in: Object and Pose. In Pose mode an animator poses a
# rig: the armature is the one in Pose mode, and its mesh is hovered and
# dragged as in Object mode.
MODES = ("OBJECT", "POSE")


def working(context):
    """Whether Kneady is on and the mode is one it works in."""
    return getattr(context.scene, "kneady_on", False) and context.mode in MODES


def playing(context):
    """Whether the animation is playing. While it plays, the hovered region
    is not painted, because an animated character's paint would be rebuilt
    every frame (19 ms a frame for an 18,000-face body, a second for a
    million faces)."""
    screen = getattr(context, "screen", None)
    return bool(screen is not None and screen.is_animation_playing)


def bone_selected(pb):
    """A pose bone's selection: on the pose bone since Blender 5.0, on its
    bone before."""
    return pb.select if hasattr(pb, "select") else pb.bone.select


def select_bone(pb, value):
    if hasattr(pb, "select"):
        pb.select = value
    else:
        pb.bone.select = value


def set_term(key, text=None):
    """Name control `key` in the panel; None puts Kneady's own name back."""
    TERMS[key] = _DEFAULT_TERMS[key] if text is None else text


# -- Groups a command may drive ----------------------------------------------------------
#
# A program's own groups of objects, such as Digit's control groups. A command
# with Deform Hovered off may drive a group in place of one Target: it drives
# the one object of the group the drag is on, as the program picks it. So one
# set of buttons serves every finger, where a Target names one. Greg: "A drag
# should only reach any of the digits in the control group and it should
# affect only the hovered digit".

_GROUPS = {"names": None, "member": None}


def set_groups(names=None, member=None):
    """Set a program's groups. names(context) -> [name, ...] lists them.
    member(name, context, dragged, point) -> (object or None, why) gives the
    object a drag on `dragged` (a region's object) drives, pressed at
    `point` (world space). With `dragged` None - the panel asking, with no
    drag on - it gives one of the group's objects, to show what the group
    has. Called with no arguments, there are no groups."""
    _GROUPS.update(names=names, member=member)


def has_groups():
    return _GROUPS["names"] is not None


def group_names(context=None):
    fn = _GROUPS["names"]
    return list(fn(context or bpy.context)) if fn is not None else []


def group_member(name, context=None, dragged=None, point=None):
    """(object, why): the object of group `name` a drag drives (set_groups)."""
    fn = _GROUPS["member"]
    if fn is None:
        return None, "No groups here: %s" % name
    if dragged is not None and point is None:
        point = dragged.matrix_world.translation.copy()
    return fn(name, context or bpy.context, dragged, point)


def command_object(drag, region_obj, point=None, context=None):
    """(object, why): what a command drives. That is the object of its group
    the drag is on, else its Target, else - with Deform Hovered on -
    `region_obj`, the object dragged."""
    if props.grouped(drag):
        if not drag.target_group:
            return None, "Pick its %s" % term("group").lower()
        return group_member(drag.target_group, context, region_obj, point)
    if drag.target is not None:
        return drag.target, ""
    if drag.pick_target:
        return None, "Pick its target"
    return region_obj, ""


# -- Regions ---------------------------------------------------------------------------

def add_provider(fn):
    if fn not in _PROVIDERS:
        _PROVIDERS.append(fn)


def remove_provider(fn):
    if fn in _PROVIDERS:
        _PROVIDERS.remove(fn)


def add_editor(fn):
    """An editor for an object whose regions come from a provider. fn(obj)
    returns (label, region or None, header, regions) for the panel to edit
    in place of the object's own list, or None. header(layout, context)
    draws above the panel's tree, or is None. regions are the tree's top
    rows (tree.py); if left out, the tree shows the one region. The last two
    items may be left off."""
    if fn not in _EDITORS:
        _EDITORS.append(fn)


def remove_editor(fn):
    if fn in _EDITORS:
        _EDITORS.remove(fn)


def add_redirect(fn):
    """fn(command, object, region) says where a command on `object` (the one
    dragged, or its Target) acts instead, or returns None to leave it. It
    returns either (object, input name) or a dict of any of:
      "object"
      "bone"  - a pose bone of that armature
      "input"
      "kind"  - what the command becomes (an input's drag can scale a bone)
      "axis"  - a 3-vector in the new owner's own frame, for a turn, move or
                scale
    or "why" alone, when the command cannot act there."""
    if fn not in _REDIRECTS:
        _REDIRECTS.append(fn)


def remove_redirect(fn):
    if fn in _REDIRECTS:
        _REDIRECTS.remove(fn)


def editor_for(obj):
    for fn in _EDITORS:
        found = fn(obj)
        if found is not None:
            return found
    return None


def own_regions(obj):
    kn = getattr(obj, "kneady", None)
    return list(kn.regions) if kn is not None else []


def listed_regions(obj):
    """Every region the object has, its own and any a provider adds,
    whichever version of Kneady made them. Most code wants regions_of, which
    leaves out an object whose regions a newer Kneady made."""
    if obj is None or obj.type != "MESH":
        return []
    out = own_regions(obj)
    for fn in _PROVIDERS:
        out.extend(fn(obj) or ())
    return out


def regions_of(obj):
    """The object's regions, its own and any a provider adds - or none at all
    when a newer Kneady made one of them (newer_on).

    Why the whole object and not only that region: a newer Kneady may have
    changed what any of the object's data means, and its regions share one
    face attribute. If newer regions were left out one by one, their faces
    would be taken by a whole-object region and hovered as part of it. So
    the object is simply not Kneady's here: nothing is hovered, drawn or
    dragged on it, a click on it goes to Blender, and its data is left
    exactly as it was, ready for the Kneady that made it. Everything that
    hovers, draws, drags or places reads regions through here."""
    out = listed_regions(obj)
    if any(r.version > DATA_VERSION for r in out):
        return []
    return out


def find_region(obj, rid):
    return next((r for r in regions_of(obj) if r.id == rid), None)


def _view_of(context):
    """The 3D view `context` is in, or None (a script, a test)."""
    space = getattr(context, "space_data", None)
    return space if getattr(space, "type", "") == "VIEW_3D" else None


def shown_in(obj, context):
    """Whether `obj` can be seen where `context` is: visible in the view layer
    and, in a 3D view, in that view too - Local View (Numpad /) and a view's
    own collection visibility hide objects that are still visible to the
    view layer, and Blender's scene ray cast knows nothing of either."""
    if not obj.visible_get():
        return False
    space = _view_of(context)
    return space is None or obj.visible_in_viewport_get(space)


def objects_with_regions(context):
    return [o for o in context.scene.objects if o.type == "MESH" and shown_in(o, context) and regions_of(o)]


def ray(context, origin, direction, distance=None, depsgraph=None, tries=16):
    """Blender's scene ray cast, as `context.scene.ray_cast`, but only
    meeting what the 3D view shows: an object hidden in this view - outside
    Local View, say - is passed through, the ray cast again from just past
    it (and no further than `distance` in all, when given). Without this, a
    hidden object with regions took the hover, painted in empty space, and a
    drag there moved something nobody could see."""
    depsgraph = depsgraph or context.evaluated_depsgraph_get()
    limit = {} if distance is None else {"distance": distance}
    found = context.scene.ray_cast(depsgraph, origin, direction, **limit)
    if _view_of(context) is None:
        return found
    step = direction.normalized()
    start = origin.copy()
    for _k in range(tries):
        ok, point, _normal, _face, obj, _matrix = found
        if not ok or obj is None or shown_in(obj.original, context):
            return found
        # just past the hidden surface: far enough to leave it behind, near
        # enough not to step over a thin object right behind it
        origin = point + step * max(1e-5, 1e-6 * (point - start).length)
        if distance is not None:
            left = distance - (origin - start).length
            if left <= 0.0:
                return (False,) + tuple(found[1:])
            limit = {"distance": left}
        found = context.scene.ray_cast(depsgraph, origin, direction, **limit)
    return found


def buttons_of(region):
    """The buttons in use, in order."""
    return list(region.buttons)[:min(region.button_count, len(region.buttons))]


def button_of(region, index=0):
    """The region's button number `index` in use, or None. A drag on the
    region runs the first button, and a drag on a button's circle runs that
    button. Greg: "let them just click drag on the bottom buttons"."""
    used = buttons_of(region)
    return used[index] if 0 <= index < len(used) else None


def shown_buttons(region, obj=None):
    """The indices of the buttons shown as circles, leaving out those a
    program hides now (add_button_filter). A lone button shows too, since
    the circles carry the graphics. `obj` is the object hovered."""
    shown = [i for i, b in enumerate(buttons_of(region)) if b.show]
    for fn in _BUTTON_FILTERS:
        shown = fn(region, obj, shown)
    return shown


def first_drag_button(region, obj=None, shown=False):
    """The index of the region's first button that drags, or None. That is
    what a drag on the region itself runs, since a toggle has nothing to
    drag. With `shown`, only the buttons shown now count (shown_buttons)."""
    used = buttons_of(region)
    indices = shown_buttons(region, obj) if shown else range(len(used))
    return next((i for i in indices if used[i].action == "DRAG"), None)


def is_gap(button):
    """A button that only holds a place in its row or ring (Action: Gap)."""
    return button.action == "GAP"


# -- What a program changes about buttons --------------------------------------------------
#
# A program built on Kneady may show only some of a region's buttons at a time
# (a button shown while a switch is on, buttons opened from another), take a
# click on a button, or switch a toggle its own way (keeping a pose as it
# switches). Each hook is a list a program adds to and removes from.

_BUTTON_FILTERS = []               # fn(region, obj, indices) -> the indices shown
_CLICK_HOOKS = []                  # fn(context, obj, region, index) -> True if it took the click
_SWITCHERS = []                    # fn(context, button, obj, region, channels, on) -> True if it switched them
_HOVER_HOOKS = []                  # fn(before, after): the hover changed, each (object name, region id) or None


def add_button_filter(fn):
    if fn not in _BUTTON_FILTERS:
        _BUTTON_FILTERS.append(fn)


def remove_button_filter(fn):
    if fn in _BUTTON_FILTERS:
        _BUTTON_FILTERS.remove(fn)


def add_click_hook(fn):
    if fn not in _CLICK_HOOKS:
        _CLICK_HOOKS.append(fn)


def remove_click_hook(fn):
    if fn in _CLICK_HOOKS:
        _CLICK_HOOKS.remove(fn)


def add_switcher(fn):
    if fn not in _SWITCHERS:
        _SWITCHERS.append(fn)


def remove_switcher(fn):
    if fn in _SWITCHERS:
        _SWITCHERS.remove(fn)


# -- A program's own kind of command ---------------------------------------------------
#
# Greg, of Digit's handles: "it would be ideal for it to show up as a command
# option like 'rotate X' is or how a modifier is driven." So a program may add
# a kind of command a click switches, listed beside Modifier Input and
# Property in the Drives row, and read and written its own way. Digit's
# Handles is one: it shows a chosen set of handles on the digit clicked. Its
# settings are the command's `program_data`, text the program reads and
# writes. Kneady keeps, copies and pastes that text but never reads it.
#
#   read(obj, command)              -> whether it is on
#   write(context, obj, command, on)   switch it
#   why(obj, command)               -> "" or why it cannot run on `obj`
#   draw(layout, context, command)     its settings, under the Drives row
#   summary(command)                -> its folded header: what it does
#
# A kind may be dragged instead, or as well. It is then chosen beside Rotate,
# Move and the rest for a drag direction, and moves by what the drag gives it,
# written its own way. So a 3D handle can drive what only the program knows
# how to: Digit's Sides, with Alt for both sides of an axis and Alt+Shift for
# all four. Greg, of Digit's Sides handles: "the thing that was keeping me
# away from that was the sides drag modes". `drag` is a dict:
#
#   motion(obj, command, point)     -> which way a positive amount moves
#                                      `point`, in the world: ("MOVE",
#                                      direction) or ("ROTATE", axis, center),
#                                      or None. A 3D handle points along it,
#                                      and a drag along the handle follows the
#                                      mouse
#   begin(context, obj, command)    -> a state for the drag, or a string saying
#                                      why it cannot run on `obj`. It reads,
#                                      never writes
#   apply(context, state, amount, ctrl, keys)
#                                      write it `amount` from where it began:
#                                      scene units along its motion, radians
#                                      for a turn. `keys` are the modifier keys
#                                      held
#   restore(context, state)            put it back where it began
#   turns(command)                  -> whether it turns (its amount in radians,
#                                      its Speed that of a turn)
#   keys(command)                   -> which of ALT and SHIFT it reads itself.
#                                      Kneady leaves those alone: Alt does not
#                                      hand the drag over, Shift does not slow
#                                      it
#   status(command)                 -> what the status bar adds while it drags

_COMMAND_KINDS = {}


def add_command_kind(key, label, read=None, write=None, why=None, draw=None, summary=None, icon="NONE",
                     description="", drag=None):
    _COMMAND_KINDS[key] = dict(key=key, label=label, read=read, write=write, why=why, draw=draw,
                               summary=summary, icon=icon, description=description, drag=drag)


def remove_command_kind(key):
    _COMMAND_KINDS.pop(key, None)


def command_kinds(switch=None):
    """The kinds of command programs add, in the order added. With `switch`
    True, only those a click switches; with False, only those a drag
    drives."""
    kinds = list(_COMMAND_KINDS.values())
    if switch is True:
        return [k for k in kinds if k.get("read") is not None]
    if switch is False:
        return [k for k in kinds if k.get("drag") is not None]
    return kinds


def drag_kind(command):
    """The `drag` dict (add_command_kind) of a program's kind a drag drives,
    or None."""
    spec = command_kind(command)
    return spec.get("drag") if spec is not None else None


def program_motion(command, obj, point):
    """A program drag's motion (add_command_kind's `drag`) for `obj` at
    `point`, or None."""
    drag = drag_kind(command)
    if drag is None or drag.get("motion") is None or obj is None:
        return None
    try:
        return drag["motion"](obj, command, point)
    except Exception:                     # a program's error must not stop the drawing
        errors.caught("a program's motion")
        return None


# -- Anchors -------------------------------------------------------------------------------
#
# Greg: "How can we manage more general usage of handles? The ability to
# connect commands to a handle. How to place the handles ... I imagine they
# would be placed similarly to how buttons are placed." A placed button sits
# on its region's surface, or at an anchor. An anchor is a point that moves
# with what it is on, so a handle there follows it exactly:
#   - a bone's head or tail, or an object's origin (Kneady's own anchors, for
#     what the region's buttons drive)
#   - a point a program gives, such as Digit's ring sides, tip and pivots,
#     which move as the digit is shaped
# Placing snaps to them (Kneady Pro). An anchor is found by its key, so one
# set of buttons fits every object a region is shared by.
#
#   fn(obj, region, key=None) -> the anchors it gives `obj` on `region` (only
#                                the one `key` names, when given). Each is a
#                                dict: key, name, point (world), frame (world
#                                3x3, its axes) and normal (world, or None)

_ANCHORS = []


def add_anchors(fn):
    if fn not in _ANCHORS:
        _ANCHORS.append(fn)


def remove_anchors(fn):
    if fn in _ANCHORS:
        _ANCHORS.remove(fn)


ORIGIN = "origin"                  # the region's object's own origin


def _anchor(key, name, point, frame, normal=None):
    return dict(key=key, name=name, point=Vector(point), frame=frame.to_3x3().normalized(), normal=normal)


def _bone_anchors(rig, pb, want=None):
    m = rig.matrix_world @ pb.matrix
    out = []
    for end, name, local in (("HEAD", "head", pb.head), ("TAIL", "tail", pb.tail)):
        key = "bone|%s|%s|%s" % (rig.name, pb.name, end)
        if want is None or want == key:
            out.append(_anchor(key, "%s %s" % (pb.name, name), rig.matrix_world @ local, m,
                               m.to_3x3().col[1].normalized()))
    return out


def _own_anchors(obj, region, want=None):
    """Kneady's own anchors: the object's origin, plus the head and tail of
    each bone and the origin of each other object the region's buttons
    drive."""
    if want is not None:
        # by its key alone, without walking the region's commands
        if want == ORIGIN:
            return [_anchor(ORIGIN, "Origin", obj.matrix_world.translation, obj.matrix_world)]
        parts = want.split("|")
        if parts[0] == "bone" and len(parts) == 4:
            rig = bpy.data.objects.get(parts[1])
            pb = rig.pose.bones.get(parts[2]) if rig is not None and rig.pose is not None else None
            return _bone_anchors(rig, pb, want) if pb is not None else []
        if parts[0] == "object" and len(parts) == 2:
            other = bpy.data.objects.get(parts[1])
            return [_anchor(want, "%s origin" % other.name, other.matrix_world.translation,
                            other.matrix_world)] if other is not None else []
        return []
    out = [_anchor(ORIGIN, "Origin", obj.matrix_world.translation, obj.matrix_world)]
    seen = {ORIGIN}
    for button in buttons_of(region) if region is not None else ():
        for drag in (button.up, button.across):
            if not drag.enabled:
                continue
            for command in [drag] + list(drag.more):
                if getattr(command, "program", ""):
                    continue
                found = resolve(command, obj)
                if found is None:
                    continue
                target, pb = found
                if pb is not None:
                    for a in _bone_anchors(target, pb):
                        if a["key"] not in seen:
                            seen.add(a["key"])
                            out.append(a)
                elif target is not obj:
                    key = "object|%s" % target.name
                    if key not in seen:
                        seen.add(key)
                        out.append(_anchor(key, "%s origin" % target.name, target.matrix_world.translation,
                                           target.matrix_world))
    return out


# this frame's program anchors (_FRAME): (object name, region pointer) -> {key: anchor}
_PROGRAM_ANCHORS = {"frame": None, "by": {}}


def _program_anchors(obj, region):
    """The anchors the programs give `obj` on `region`, by key. The programs
    are asked once a frame (changed), however many handles look them up."""
    if _PROGRAM_ANCHORS["frame"] != _FRAME[0]:
        _PROGRAM_ANCHORS.update(frame=_FRAME[0], by={})
    by = _PROGRAM_ANCHORS["by"]
    cache_key = (obj.name, region.as_pointer() if region is not None else 0)
    found = by.get(cache_key)
    if found is not None:
        return found
    found = {}
    for fn in list(_ANCHORS):
        try:
            for anchor in fn(obj, region) or []:
                found.setdefault(anchor["key"], anchor)
        except Exception:                 # a program's error must not stop the drawing
            errors.caught("an anchor provider")
    by[cache_key] = found
    return found


def anchors_of(obj, region):
    """Every anchor `obj` has on `region`: a program's first, then Kneady's."""
    if obj is None:
        return []
    return list(_program_anchors(obj, region).values()) + _own_anchors(obj, region)


def anchor_of(obj, region, key):
    """The anchor `key` names on `obj`, or None where `obj` has no such
    point (a digit with nothing on its End has no anchor for it)."""
    if obj is None or not key:
        return None
    if key == ORIGIN or key.startswith(("bone|", "object|")):
        found = _own_anchors(obj, region, key)
        return found[0] if found else None
    return _program_anchors(obj, region).get(key)


# -- Worked out once a frame -----------------------------------------------------------------
#
# Greg, of Kneady handles in a menu: "It doesn't register as fast as the
# standard handles ... I experienced many moments where the viewport would
# freeze for a bit." Every region's gizmo asks hit_at at each mouse move (46
# of them on his hand), and each one used to work out the hovered region's
# layout again. With a menu of 13 handles at Digit's anchors open, that cost
# 574 ms a move (Digit's own handles: 16 ms).
#
# Now a frame counter moves on whenever anything a layout or the hover
# depends on may have changed: a redraw asked for, the caches forgotten, a
# depsgraph update, a view drawn. Until it does, a region's layout (_layout),
# the hover at one position (hit_at) and a program's anchors are each worked
# out once.

_FRAME = [0]


def changed():
    """Something a layout or the hover depends on may have changed, so they
    are worked out again (_FRAME)."""
    _FRAME[0] += 1


def frame_count():
    return _FRAME[0]


def command_kind(command):
    """The program's kind of command this is, or None. Also None when its
    program is not running, though `command.program` still names it."""
    return _COMMAND_KINDS.get(getattr(command, "program", "")) if getattr(command, "program", "") else None


# -- A program's handles hold the hover ----------------------------------------------
#
# Greg: "when the handles are present they need to be treated as part of the
# menu. If the handles are overlaying another digit I should be able to mouse
# over to that area without activating the other digit." So a program says
# which object's handles are under the mouse. There the hover stays on that
# object's region with its menu open, and no other object is hovered, so
# another item's buttons cannot come up under the handle and take the press.
#
#   fn(context, at) -> the name of the object whose handles are at `at`
#                      (region pixels), or None

_HOLD_HOOKS = []


def add_hold_hook(fn):
    if fn not in _HOLD_HOOKS:
        _HOLD_HOOKS.append(fn)


def remove_hold_hook(fn):
    if fn in _HOLD_HOOKS:
        _HOLD_HOOKS.remove(fn)


def held_by_handles(context, at):
    """The object whose program handles are under `at`, or None."""
    for fn in list(_HOLD_HOOKS):
        try:
            name = fn(context, at)
        except Exception:                     # a hook's error must not stop the hover
            errors.caught("a hold hook")
            name = None
        if name:
            return name
    return None


# A program's own drag. While a hook says one of its drags is going, Kneady
# draws nothing and takes no press, as during a drag of its own. Greg, of
# Digit's handles: "It should hide while rotating or deforming the digit".
#
#   fn(context) -> whether the program is dragging

_BUSY_HOOKS = []


def add_busy_hook(fn):
    if fn not in _BUSY_HOOKS:
        _BUSY_HOOKS.append(fn)


def remove_busy_hook(fn):
    if fn in _BUSY_HOOKS:
        _BUSY_HOOKS.remove(fn)


def hauling():
    """Whether one of Kneady's own drags is going. A program's handles hide
    then, as Kneady's buttons do. Greg: "Handles also should hide when it is
    driving an action just like hauling on the buttons"."""
    return bool(STATE["dragging"])


def busy(context=None):
    """Whether a drag is going, Kneady's own (hauling) or a program's
    (add_busy_hook). Meanwhile Kneady draws nothing and takes no press."""
    if STATE["dragging"]:
        return True
    for fn in list(_BUSY_HOOKS):
        try:
            if fn(context if context is not None else bpy.context):
                return True
        except Exception:                     # a hook's error must not stop the drawing
            errors.caught("a busy hook")
    return False


# Something drawn over the view that the mouse is on, such as a tutorial's
# panel (overlay.py). No region is hovered through it, and a click there is
# not a click in empty space.
#
#   fn(context, at) -> whether `at` (region pixels) is covered

_COVERS = []


def add_cover(fn):
    if fn not in _COVERS:
        _COVERS.append(fn)


def remove_cover(fn):
    if fn in _COVERS:
        _COVERS.remove(fn)


def covered(context, at):
    for fn in list(_COVERS):
        try:
            if fn(context, at):
                return True
        except Exception:                     # a hook's error must not stop the hover
            errors.caught("a cover hook")
    return False


# The panel's tree and Viewport Edit (tree.py, pick.py) ask which list of
# buttons a button is in, and tell a program when the panel shows a region:
#   list_of  fn(region, index) -> the key of button `index`'s list
#            (button_list), or None to leave it to the next hook. "all" by
#            default
#   focus    fn(context, obj, region): the panel was made to show `region`
#            for `obj`, for a region a provider gives it
_LIST_OF = []
_FOCUS = []


def add_list_of(fn):
    if fn not in _LIST_OF:
        _LIST_OF.append(fn)


def remove_list_of(fn):
    if fn in _LIST_OF:
        _LIST_OF.remove(fn)


def list_of(region, index):
    """The key of the panel's list that button `index` is in."""
    for fn in list(_LIST_OF):
        found = fn(region, index)
        if found is not None:
            return found
    return "all"


def add_focus(fn):
    if fn not in _FOCUS:
        _FOCUS.append(fn)


def remove_focus(fn):
    if fn in _FOCUS:
        _FOCUS.remove(fn)


def focus(context, obj, region):
    """Have the panel show `region` for `obj`: its own list's selection, and
    whatever a program shows for one it gives (add_focus)."""
    own = getattr(obj, "kneady", None)
    if own is not None:
        for k, r in enumerate(own.regions):
            if r == region:
                own.index = k
    for fn in list(_FOCUS):
        fn(context, obj, region)


def picking(context=None):
    """Whether Viewport Edit is on (pick.py; once called Pick Buttons). While
    it is on:
      - a click on a button selects it in the panel too
      - the last region hovered stays hovered until another is
      - + and - beside its buttons add and remove them
      - a right-click on one copies and pastes"""
    wm = getattr(context or bpy.context, "window_manager", None)
    return bool(getattr(wm, "kneady_pick", False))


def add_hover_hook(fn):
    if fn not in _HOVER_HOOKS:
        _HOVER_HOOKS.append(fn)


def remove_hover_hook(fn):
    if fn in _HOVER_HOOKS:
        _HOVER_HOOKS.remove(fn)


# A mark on a button's outline, a small circle at its upper right, where a
# program says there is more behind it, such as a menu it opens. Greg:
# "Buttons with sub menus should have a little circle in the upper right of
# the button on it's outline". fn(region, button) returns True to mark it, or
# 2 for a strong mark (larger, filled light, with a ring around the button),
# which says what it opens is held open.
_BADGES = []


def add_badge(fn):
    if fn not in _BADGES:
        _BADGES.append(fn)


def remove_badge(fn):
    if fn in _BADGES:
        _BADGES.remove(fn)


def badged(region, button):
    """0 for no mark, 1 a mark, 2 a strong one (add_badge)."""
    return max((int(fn(region, button) or 0) for fn in list(_BADGES)), default=0)


# -- The panel's lists of buttons ------------------------------------------------------------
#
# A region's buttons are a list in the panel, as its regions are: added with
# +, removed with -, moved with the arrows, with the selected one's settings
# under it. Greg: "Buttons are added and removed with + and - on upper right
# of menu. No more changing the number of buttons". A program may split them
# into several lists (its sections, a menu's buttons), each named by a key;
# "all" is every button. fn(region, key) returns None to leave the key to the
# next hook, else a dict:
#   members  the indices in the list, in order
#   cap      how many it holds (None: as many as the region)
#   active   (data, property name) holding its selected button's index
#   add      fn(context, region, index): sets up a button just added to it
#   remove   fn(region, index): called before a button of it is removed.
#            Returns the indices of other buttons removed with it (the
#            buttons in its menu), or None
#   color    (owner, its Override Color property, its color property): the
#            list's one color, drawn under it (button_colors resolves it)
_LISTS = []
# fn(region, moved): buttons changed places, so whatever holds a button's
# index can follow. moved[old index] is the new index, or None for a button
# removed
_REINDEX = []


def add_lists(fn):
    if fn not in _LISTS:
        _LISTS.append(fn)


def remove_lists(fn):
    if fn in _LISTS:
        _LISTS.remove(fn)


def add_reindex(fn):
    if fn not in _REINDEX:
        _REINDEX.append(fn)


def remove_reindex(fn):
    if fn in _REINDEX:
        _REINDEX.remove(fn)


def button_list(region, key="all"):
    """The list `key` of a region's buttons (add_lists), as a dict of
    members, cap, active, add, remove and color. color is (owner, its
    Override Color, its color): the region's own buttons' color unless the
    list says otherwise."""
    out = dict(members=None, cap=None, active=(region, "button_index"), add=None, remove=None,
               color=(region, "use_button_color", "button_color"))
    for fn in list(_LISTS):
        found = fn(region, key)
        if found is not None:
            out.update(found)
            break
    if out["members"] is None:
        out["members"], out["cap"] = list(range(len(buttons_of(region)))), props.ROW_BUTTONS
    return out


def selected_button(region, key="all"):
    """The index of the list's selected button, or None if it has none."""
    found = button_list(region, key)
    data, prop = found["active"]
    index = getattr(data, prop, -1)
    return index if index in found["members"] else None


def can_add(region, key="all"):
    """Why a button cannot be added to the list, or "" if it can."""
    found = button_list(region, key)
    if min(region.button_count, len(region.buttons)) >= props.MAX_BUTTONS:
        return "A region holds %d buttons at most" % props.MAX_BUTTONS
    if found["cap"] is not None and len(found["members"]) >= found["cap"]:
        return "This list holds %d buttons at most" % found["cap"]
    return ""


def _reindexed(region, moved):
    if region.button_index in moved:
        new = moved[region.button_index]
        region.button_index = new if new is not None else max(region.button_index - 1, 0)
    for fn in list(_REINDEX):
        fn(region, moved)


def new_button(region):
    """Make a fresh button just after those in use, named Button n, and
    return its index. No list is told about it (add_button does that).
    Buttons kept past those in use stay, unless one must go to make room.
    The region must have room (can_add)."""
    count = min(region.button_count, len(region.buttons))
    names = {b.name for b in buttons_of(region)}
    while len(region.buttons) >= props.MAX_BUTTONS:
        region.buttons.remove(len(region.buttons) - 1)
    region.buttons.add()
    region.buttons.move(len(region.buttons) - 1, count)
    region.buttons[count].name = next("Button %d" % n for n in range(1, 2 * props.MAX_BUTTONS)
                                      if "Button %d" % n not in names)
    region.button_count = count + 1
    return count


# Which list a new button goes in (for the panel's tree). fn(region, parent)
# returns the key of the list (button_list) that holds the buttons directly
# under button `parent` (or under the region itself, for None), "" if none
# can be added there, or None to leave it to the next hook. The last hook
# added is asked first, so a program built on Kneady can take over from
# Kneady's own. "all" if none answers.
_LIST_KEYS = []


def add_list_key(fn):
    if fn not in _LIST_KEYS:
        _LIST_KEYS.append(fn)


def remove_list_key(fn):
    if fn in _LIST_KEYS:
        _LIST_KEYS.remove(fn)


def list_key_for(region, parent=None):
    """The key of the list a button added under button `parent` (None: the
    region's own) goes in, or "" where none can be."""
    for fn in reversed(list(_LIST_KEYS)):
        found = fn(region, parent)
        if found is not None:
            return found
    return "all"


# Adding a button under another. Greg: "Adding a button through the menu
# should add a button nested under the current selected entry". A program
# that builds menus gives two functions: why_not(region, index) -> "" or why,
# and add(context, region, index) -> (new index, why). The last pair added is
# asked. Without one, buttons go under their region only.
_CHILDREN = []
UNDER_REGION = "Buttons go under their region here, not under another button"


def add_children(why_not, add):
    if (why_not, add) not in _CHILDREN:
        _CHILDREN.append((why_not, add))


def remove_children(why_not, add):
    if (why_not, add) in _CHILDREN:
        _CHILDREN.remove((why_not, add))


def child_why_not(region, index):
    """Why no button can be added under button `index`, or ""."""
    if not _CHILDREN:
        return UNDER_REGION
    return _CHILDREN[-1][0](region, index)


def add_child(context, region, index):
    """Add a new button under button `index`, in its menu, and select it
    there. Returns (index, "") or (None, why not)."""
    why = child_why_not(region, index)
    if why:
        return None, why
    return _CHILDREN[-1][1](context, region, index)


def add_button(context, region, key="all"):
    """Add a new button at the end of the list `key` and select it. Returns
    (index, "") or (None, why not)."""
    why = can_add(region, key)
    if why:
        return None, why
    count = new_button(region)
    found = button_list(region, key)
    if found["add"] is not None:
        found["add"](context, region, count)
    data, prop = button_list(region, key)["active"]
    setattr(data, prop, count)
    STATE["button"] = None
    redraw()
    return count, ""


def removed_with(region, key, index):
    """Button `index` of the list `key`, and what goes with it when it is
    removed (the list's "remove": the buttons in its menu), as sorted
    indices."""
    found = button_list(region, key)
    more = found["remove"](region, index) if found["remove"] is not None else None
    return sorted({index, *(more or ())})


def remove_button(region, key="all", index=None):
    """Remove the list's selected button (or its button `index`) with
    whatever goes with it (removed_with), and select the next in the list.
    Returns why not, or ""."""
    if index is None:
        index = selected_button(region, key)
    elif index not in button_list(region, key)["members"]:
        index = None
    if index is None:
        return "Select a button in the list"
    if region.button_count <= 1:
        return "A region keeps one button"
    found = button_list(region, key)
    at = found["members"].index(index)
    gone = removed_with(region, key, index)
    count = region.button_count
    if count - len(gone) < 1:
        return "A region keeps one button"
    for k in reversed(gone):
        region.buttons.remove(k)
    region.button_count = count - len(gone)
    moved, shift = {}, 0
    for k in range(count):
        if k in gone:
            moved[k], shift = None, shift + 1
        elif shift:
            moved[k] = k - shift
    _reindexed(region, moved)
    members = button_list(region, key)["members"]
    if members:
        data, prop = button_list(region, key)["active"]
        setattr(data, prop, members[min(at, len(members) - 1)])
    STATE["button"] = None
    redraw()
    return ""


def move_in_list(region, key, direction, index=None):
    """Move the list's selected button (or its button `index`) up (-1) or
    down (1) among its members. Returns its new index, or None if it did not
    move."""
    if index is None:
        index = selected_button(region, key)
    members = button_list(region, key)["members"]
    if index is None or index not in members:
        return None
    k = members.index(index) + direction
    if not 0 <= k < len(members):
        return None
    swap_buttons(region, index, members[k])
    return members[k]


def button_home(button):
    """(region, index): the region holding a button and where it is among its
    buttons, read from its data path - or (None, None)."""
    try:
        path = button.path_from_id()
    except (ValueError, TypeError, AttributeError, ReferenceError):
        return None, None
    head, sep, tail = path.rpartition(".buttons[")
    if not sep or not head:
        return None, None
    try:
        return button.id_data.path_resolve(head), int(tail.rstrip("]"))
    except (ValueError, TypeError, AttributeError):
        return None, None


def swap_buttons(region, a, b):
    """Buttons `a` and `b` change places, and every other button stays where
    it is. That changes the order of the row, and which drag button is first
    (the one a drag on the region runs). Greg, of the Static Menu: it "needs
    to be able to be reordered"."""
    if a == b:
        return
    lo, hi = min(a, b), max(a, b)
    region.buttons.move(hi, lo)
    region.buttons.move(lo + 1, hi)
    _reindexed(region, {a: b, b: a})
    STATE["button"] = None
    redraw()


def clicked(context, obj, region, index, shift=False):
    """A click (no drag) on button `index`. Returns whether a program took
    it. With Shift and no program taking it, the region is pinned or let go
    (toggle_kept), and that counts as taken. A hook reads whether Shift was
    held with click_shift()."""
    STATE["click_shift"] = shift
    try:
        if any(fn(context, obj, region, index) for fn in list(_CLICK_HOOKS)):
            return True
        if shift:
            toggle_kept(context, obj, region)
            return True
        return False
    finally:
        STATE["click_shift"] = False


def click_shift():
    """Whether Shift was held for the click a click hook is taking."""
    return bool(STATE.get("click_shift"))


# -- Keeping the hover ---------------------------------------------------------------------
#
# A program may keep the hover on one region, wherever the mouse goes, until
# it lets go: its buttons stay shown and work, nothing else is hovered, and a
# click off its buttons and faces passes to Blender as ever. The status bar
# says what it is and how it ends, between drags too.

_RELEASE = [None]                  # what keep was handed to call when it is let go


def keep(context, obj_name, rid, note="", by="", release=None, click_off=False):
    """Keep the hover on region `rid` of object `obj_name` until let_go(),
    with `note` in the status bar meanwhile. `by` says who keeps it
    (kept_by). `release(context)`, if given, is called when it is let go (by
    Esc too), so what the program showed goes with it, such as Digit's
    handles. With `click_off`, a click in empty space lets go too (in_space;
    menus.py's KNEADY_OT_click_off). That suits a menu that Stays Open, or a
    program's handles."""
    STATE.update(kept=(obj_name, rid), kept_note=note, kept_by=by, hover=(obj_name, rid), held=None,
                 kept_click_off=bool(click_off))
    _RELEASE[0] = release
    _status(context, idle_status())
    redraw()


def kept_click_off():
    """Whether a click in empty space lets go of the hover kept (keep's
    `click_off`)."""
    return STATE.get("kept") is not None and bool(STATE.get("kept_click_off"))


def in_space(context, at):
    """Whether `at` (region pixels) is on nothing: no object under it, no
    program's handle (add_hold_hook), and no Kneady button, handle or icon.
    A click there is a click in empty space."""
    if covered(context, at) or held_by_handles(context, at) is not None:
        return False
    if STATE.get("button") is not None or STATE.get("edit"):
        return False
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return False
    hover = STATE.get("hover")
    obj = bpy.data.objects.get(hover[0]) if hover is not None and hover[1] is not None else None
    held = find_region(obj, hover[1]) if obj is not None else None
    if held is not None and buttons_under(context, obj, held, Vector(at))[1] is not None:
        return False
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, at)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, at)
    return not ray(context, origin, direction)[0]


def kept():
    """(object name, region id) the hover is kept on, or None."""
    return STATE.get("kept")


def kept_by():
    """Who keeps the hover (keep's `by`): "region" for a region pinned with
    Shift+click (toggle_kept), "" when nothing is kept."""
    return STATE.get("kept_by", "") if STATE.get("kept") else ""


def let_go(context=None):
    """Stop keeping the hover (keep), and call what keep was handed to call."""
    if STATE.get("kept") is None:
        return
    STATE.update(kept=None, kept_note="", kept_by="", kept_click_off=False)
    release, _RELEASE[0] = _RELEASE[0], None
    _status(context, None)
    redraw()
    if release is not None:
        try:
            release(context if context is not None else bpy.context)
        except Exception:                     # a program's error must not keep the hover
            errors.caught("letting go of a kept hover")


# Pinned with Shift+click. Greg: "I can't pin the Cap regions. I think it's
# because there's no sub menus." Pinning used to be a menu's alone, so a
# region without a menu could not be held - a cap, say, thin at its edges and
# mostly behind its neighbor. Now Shift+click on any of a region's buttons
# keeps the hover on it, with its buttons shown wherever the mouse goes,
# until another Shift+click on one of them or Esc. A Shift+click on the
# region's own faces still adds to the selection, as Blender's does.

KEPT_NOTE = "Kneady: %s pinned      Esc: let go      Shift+click one of its buttons: unpin"


def toggle_kept(context, obj, region):
    """Pin the region (keep), or let it go if it is the one pinned. If a
    program keeps it (its own `by`), it becomes the artist's pin and the
    program's release is dropped, so the pin outlasts what the program
    showed."""
    if kept() == (obj.name, region.id) and kept_by() in ("region", "menu"):
        let_go(context)
    else:
        _RELEASE[0] = None
        keep(context, obj.name, region.id, note=KEPT_NOTE % region.name, by="region")


def idle_status():
    """What the status bar says between drags: what keeps the hover, if
    anything does (keep)."""
    return (STATE.get("kept_note") or None) if STATE.get("kept") else None


def _status(context, text):
    workspace = getattr(context, "workspace", None) if context is not None else None
    if workspace is None:
        workspace = getattr(bpy.context, "workspace", None)
    if workspace is not None:
        workspace.status_text_set(text)


def reset_state(context=None, keep=False):
    """Clear everything hovered, held, kept or pinned, as when Kneady is
    turned off or a file is loaded. With `keep` (after an undo or redo), a
    region kept hovered (keep) stays kept and hovered while its object and
    region still exist."""
    was, note, by = STATE.get("kept"), STATE.get("kept_note"), STATE.get("kept_by", "")
    click_off = STATE.get("kept_click_off", False)
    release, _RELEASE[0] = _RELEASE[0], None
    STATE.update(hover=None, button=None, block=False, dragging=False, pinned=None, held=None, kept=None,
                 kept_note="", kept_by="", edit=None, kept_click_off=False)
    if keep and was is not None:
        obj = bpy.data.objects.get(was[0])
        if obj is not None and find_region(obj, was[1]) is not None:
            STATE.update(kept=was, kept_note=note, kept_by=by, hover=was, kept_click_off=click_off)
            _RELEASE[0] = release
            return
    if was is not None:
        try:
            _status(context, None)
        except (AttributeError, RuntimeError):
            pass


def _hovered(before, after):
    for fn in list(_HOVER_HOOKS):
        fn(before, after)


# What the person did with a region's button, for tutorials that watch for
# it: a drag or a click finished.
#   fn(kind, data) - kind is "kneady.drag". data holds target, region,
#                    region_name, button, button_name, and moved (true for a
#                    drag, false for a click)
_ACTION_HOOKS = []


def add_action_hook(fn):
    if fn not in _ACTION_HOOKS:
        _ACTION_HOOKS.append(fn)


def remove_action_hook(fn):
    if fn in _ACTION_HOOKS:
        _ACTION_HOOKS.remove(fn)


def acted(kind, **data):
    for fn in list(_ACTION_HOOKS):
        try:
            fn(kind, data)
        except Exception:                     # a hook's error must not stop the drag
            errors.caught("an action hook")


def next_id(obj):
    """A region id that no region in the file has and no face of the
    object's mesh still carries, so two objects' regions stay apart when
    they are joined. Each object used to count from 1, and a join merged
    their first regions into one."""
    used = [r.id for o in bpy.data.objects for r in own_regions(o)]
    if obj is not None and obj.type == "MESH" and obj.data is not None:
        tags = face_tags(obj.data)
        if tags is not None and len(tags):
            used.append(int(tags.max()))
    return max(used + [0]) + 1


_UNLISTED = {}                     # object name -> (key, {id: faces})


def unlisted_tags(obj):
    """Faces carrying a region the object does not list, as {id: number of
    faces}. An object joined into this one leaves these behind: Blender's
    Join keeps only the active object's regions, while the faces keep their
    tags."""
    if obj is None or obj.type != "MESH" or obj.data is None:
        return {}
    listed = {r.id for r in regions_of(obj)}
    key = (len(obj.data.polygons), tuple(sorted(listed)))
    _whose(obj)
    hit = _UNLISTED.get(obj.name)
    if hit is not None and hit[0] == key:
        return hit[1]
    tags = face_tags(obj.data)
    out = {}
    if tags is not None and len(tags):
        ids, counts = np.unique(tags, return_counts=True)
        out = {int(i): int(c) for i, c in zip(ids, counts) if i and int(i) not in listed}
    _UNLISTED[obj.name] = (key, out)
    return out


def regions_fixed(obj):
    """Why an object's region list cannot be changed here, or None. A linked
    object's regions belong to its own file, and so do an override's:
    Blender keeps an override's changed values, but not regions added to or
    removed from a list made in Python. Tested: an added region was gone
    once the file was saved and opened. And an object whose regions a newer
    Kneady made is that Kneady's to change (regions_of)."""
    version = newer_on(obj)
    if version:
        return ("Made with a newer Kneady (data version %d; this one reads up to %d). Update Kneady to use "
                "or change these regions: until then they are left exactly as they are" % (version, DATA_VERSION))
    lib = getattr(obj, "library", None)
    if lib is not None:
        return "Linked from %s: its regions are made in that file" % bpy.path.basename(lib.filepath)
    ol = getattr(obj, "override_library", None)
    ref = getattr(ol, "reference", None) if ol is not None else None
    if ref is not None and ref.library is not None:
        return ("An override of %s: its regions are made in that file, and changes here are not kept"
                % bpy.path.basename(ref.library.filepath))
    return None


# -- Data versions -------------------------------------------------------------------------
#
# Each region carries the data version it was made at (KNEADY_PG_region.
# version), so a later Kneady can bring a file saved by an earlier one up to
# date. That includes an object appended from an older file, which a version
# stored on the file would miss. A region made with no version (from before
# versions existed) is the first layout.
#
# On opening a file, every region older than DATA_VERSION gets the steps in
# between, in order, and is stamped. With no step to run nothing is written,
# so opening a file does not change it. A region from a newer Kneady is left
# alone and reported (newer_regions). A program that makes regions of its own
# (add_provider) stamps them with made().
DATA_VERSION = 2
# {version: step(region)}: what turns a region of that version into the next.
MIGRATIONS = {}


def legacy_shape(button, stored):
    """For a few hours, each length of 3D handle arrow was a shape of its
    own (props.LEGACY_SHAPES). A handle stored as one of those - by number,
    or by name in copied settings - is made an Arrow of that Length,
    Centered or not. Returns whether it was one."""
    if isinstance(stored, str):
        stored = props.LEGACY_SHAPE_NAMES.get(stored)
    found = props.LEGACY_SHAPES.get(stored)
    if found is None:
        return False
    shape, length, centered = found
    button.handle_shape, button.handle_length, button.handle_centered = shape, length, centered
    return True


def _lengths_from_shapes(region):
    """Version 1 -> 2. Medium and Long Arrows were shapes of their own; now
    an Arrow has a Length and may be Centered. Returns whether any button
    was one of those shapes."""
    changed = False
    for button in region.buttons:
        changed |= legacy_shape(button, button.get("handle_shape"))
    return changed


MIGRATIONS[1] = _lengths_from_shapes


def made(region):
    """Stamp a region just made with the current data version."""
    region.version = DATA_VERSION
    return region


def migrate(region):
    """Bring a region up to DATA_VERSION by the steps in between, and return
    whether it changed. A region from a newer Kneady is left alone. If every
    step says it changed nothing (returns False), nothing is written, not
    even the stamp, so opening a file with nothing to update leaves it as it
    was."""
    version = max(region.version, 1)
    if version >= DATA_VERSION:
        return False
    changed = False
    while version < DATA_VERSION:
        step = MIGRATIONS.get(version)
        if step is not None:
            changed |= step(region) is not False
        version += 1
    if changed:
        region.version = DATA_VERSION
    return changed


def all_regions():
    """Every region in the file, once each: each object's own and those
    programs give them (add_provider). It leaves out an object a newer
    Kneady made regions on (regions_of), because migrate_file and Kneady
    Pro's renames on load must leave its data exactly as it is."""
    seen, out = set(), []
    for obj in bpy.data.objects:
        for region in regions_of(obj):
            key = region.as_pointer()
            if key not in seen:
                seen.add(key)
                out.append(region)
    return out


def migrate_file():
    """Bring every region in the file up to date (migrate). Returns how many
    changed. A linked object's regions are read as they are."""
    changed = 0
    for region in all_regions():
        if getattr(region.id_data, "library", None) is None and migrate(region):
            changed += 1
    return changed


def newer_regions():
    """Regions from a newer Kneady than this one."""
    seen, out = set(), []
    for obj in bpy.data.objects:
        for region in listed_regions(obj):
            if region.version > DATA_VERSION and region.as_pointer() not in seen:
                seen.add(region.as_pointer())
                out.append(region)
    return out


def newer_on(obj):
    """The data version of the newest region on `obj` when a newer Kneady
    made it, else 0. Such an object is left to that Kneady (regions_of)."""
    top = max((r.version for r in listed_regions(obj)), default=0)
    return top if top > DATA_VERSION else 0


def newer_objects():
    """[(object name, data version)] for each object whose regions a newer
    Kneady made, by name."""
    found = [(o.name, newer_on(o)) for o in bpy.data.objects if o.type == "MESH"]
    return sorted((name, version) for name, version in found if version)


# What opening the last file found from a newer Kneady, said once (newer_note):
# the load handler shows it, and a test reads it
LOAD_NOTE = [""]


def newer_note(found=None):
    """What to tell the person when a file holds regions from a newer
    Kneady, or "". That happens with a file saved in a beta, say, then
    opened again in this release. Kneady leaves those regions exactly as
    they are and shows nothing on their objects. It says so here, since a
    character whose controls are simply gone would look broken. The note is
    kept in LOAD_NOTE."""
    found = newer_objects() if found is None else found
    if not found:
        LOAD_NOTE[0] = ""
        return ""
    names = [name for name, _version in found]
    shown = ", ".join(names[:4]) + (" and %d more" % (len(names) - 4) if len(names) > 4 else "")
    LOAD_NOTE[0] = ("Kneady controls on %s were made with a newer Kneady (data version %d; this one reads up "
                    "to %d). They are left exactly as they are and work again once Kneady is updated."
                    % (shown, max(v for _n, v in found), DATA_VERSION))
    return LOAD_NOTE[0]


def mesh_rig(obj):
    """The armature that deforms a mesh (its first Armature modifier's), or
    None."""
    for m in getattr(obj, "modifiers", ()):
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    return None


def active_bone(rig):
    """A rig's active bone's name - the bone last clicked in Pose mode - or "". """
    bone = rig.data.bones.active if rig is not None and rig.type == "ARMATURE" else None
    return bone.name if bone is not None else ""


def new_region(obj, name=None, whole=False, rid=None):
    """Add a region to the object's list, with its six buttons. The first
    button turns something about X when dragged up and down, and about Y
    when dragged left and right. On a mesh a rig deforms, that is the rig's
    active bone (the one last clicked in Pose mode), and the region is named
    after it, because turning a skinned mesh itself only pulls it off its
    rig. Otherwise it turns the object. The bone is used only when one is
    active: a click on a bone is what makes it a good guess, and with no
    bone the rig object would spin the whole character."""
    kn = obj.kneady
    rid = rid or next_id(obj)
    region = kn.regions.add()
    region.id = rid
    rig = mesh_rig(obj)
    bone = active_bone(rig)
    region.name = name or bone or "Region %d" % region.id
    region.whole = whole
    region.color = PALETTE[(region.id - 1) % len(PALETTE)]
    fill_buttons(region)
    first = region.buttons[0]
    first.up.enabled = first.across.enabled = True
    first.up.kind = first.across.kind = "ROTATE"
    first.up.axis, first.across.axis = "X", "Y"
    if bone:
        for d in (first.up, first.across):
            d.target, d.bone = rig, bone
    kn.index = len(kn.regions) - 1
    return made(region)


def group_faces(obj, groups, share=0.5):
    """The faces of a mesh mostly weighted to some vertex groups: those
    where every corner's weight in the groups, summed, is over `share`. The
    weights are summed so the faces where two segments of a limb share the
    weight are kept."""
    if isinstance(groups, str):
        groups = [groups]
    wanted = {g.index for g in obj.vertex_groups if g.name in set(groups)}
    if not wanted:
        return []
    on = {v.index for v in obj.data.vertices if sum(g.weight for g in v.groups if g.group in wanted) > share}
    return [p.index for p in obj.data.polygons if all(i in on for i in p.vertices)]


# A bone's name, parsed into a stem, a segment's number, a side, and a B-bone
# segment's .001. For example: FK-Index1.L, DEF-forearm.L.001, spine_fk.001
_BONE_NAME = re.compile(r"^(?P<stem>.*?)(?P<num>\d*)(?P<side>[._](?:[LRlrx]|Left|Right|left|right))?"
                        r"(?P<seg>\.\d{3})?$")
_CONTROL_PREFIXES = ("c_", "FK-", "IK-", "CTR-", "CTRL-")
_CONTROL_INFIXES = ("_fk", "_ik", "_FK", "_IK")


def _control_base(bone):
    """A control bone's name without what makes it a control. So
    forearm_fk.L becomes forearm.L, c_forearm_fk.l becomes forearm.l, and
    FK-Forearm.L becomes Forearm.L."""
    base = bone
    for cut in _CONTROL_INFIXES:
        base = base.replace(cut, "")
    stripped = True
    while stripped:
        stripped = False
        for prefix in _CONTROL_PREFIXES:
            if base.startswith(prefix) and len(base) > len(prefix):
                base, stripped = base[len(prefix):], True
    return base


def bone_groups(obj, bone, rig=None):
    """The vertex groups a bone most likely deforms the mesh by. This is a
    guess, by name: shown, never assumed.

    - A deform bone deforms by its own group.
    - A control deforms by its deform bones, found by name: DEF- and its
      stem, or Auto-Rig Pro's _stretch and _twist. When the control names
      the whole limb, that is the run of segments the limb is split into.
      Rigify's forearm_fk.L deforms by DEF-forearm.L and DEF-forearm.L.001,
      Rain's FK-Forearm.L by DEF-Forearm1.L and DEF-Forearm2.L, and
      Auto-Rig Pro's c_forearm_fk.l by forearm_stretch.l and
      forearm_twist.l.
    - A control that names one segment takes that one (FK-Index1.L).

    A run stops at a segment another control of `rig` names: Rigify's
    spine_fk stops before DEF-spine.001, which is spine_fk.001's."""
    if not bone:
        return []
    names = {g.name for g in obj.vertex_groups}
    if bone in names:
        return [bone]
    bones = set(rig.data.bones.keys()) if rig is not None and rig.type == "ARMATURE" else set()
    base = _control_base(bone)
    # one group by name, and its B-bone segments, .001 on
    for name in (base, "DEF-" + base, "DEF_" + base):
        if name in names:
            found = [name]
            if not _BONE_NAME.match(name).group("seg"):
                k = 1
                while name + ".%03d" % k in names and bone + ".%03d" % k not in bones:
                    found.append(name + ".%03d" % k)
                    k += 1
            return found
    parts, own = _BONE_NAME.match(base), _BONE_NAME.match(bone)
    stem, side = parts.group("stem"), parts.group("side") or ""
    # a limb split into numbered segments, 1 on, when the control is unnumbered
    if not parts.group("num") and not parts.group("seg"):
        for prefix in ("DEF-", "DEF_", ""):
            found, k = [], 1
            while ("%s%s%d%s" % (prefix, stem, k, side) in names
                   and "%s%d%s" % (own.group("stem"), k, own.group("side") or "") not in bones):
                found.append("%s%s%d%s" % (prefix, stem, k, side))
                k += 1
            if found:
                return found
    # Auto-Rig Pro: a limb's stretch and twist
    return [n for n in (stem + "_stretch" + side, stem + "_twist" + side) if n in names]


def fill_buttons(region):
    """Give a new region a row's worth of buttons. Raising its count adds
    more (props._fill_buttons), up to MAX_BUTTONS."""
    while len(region.buttons) < props.ROW_BUTTONS:
        b = region.buttons.add()
        b.name = "Button %d" % len(region.buttons)


def face_tags(mesh):
    a = mesh.attributes.get(TAG)
    if a is None or a.domain != "FACE" or a.data_type != "INT" or len(a.data) != len(mesh.polygons):
        return None
    out = np.empty(len(a.data), dtype=np.int32)
    a.data.foreach_get("value", out)
    return out


def region_tags(regions, mesh):
    """Each face's region id: the faces tagged by hand, then those a region
    reads from a face attribute (KNEADY_PG_region.attribute), 0 for none."""
    tags = face_tags(mesh)
    tags = tags.copy() if tags is not None else np.zeros(len(mesh.polygons), dtype=np.int32)
    for r in regions:
        if r.whole or not r.attribute:
            continue
        a = mesh.attributes.get(r.attribute)
        if a is None or a.domain != "FACE" or a.data_type not in {"INT", "BOOLEAN"} or len(a.data) != len(tags):
            continue
        values = np.empty(len(a.data), dtype=np.int32 if a.data_type == "INT" else bool)
        a.data.foreach_get("value", values)
        tags[values.astype(np.int32) == r.value] = r.id
    return tags


def tag_faces(mesh, faces, rid):
    """Write `rid` on the faces (indices), in Object mode."""
    a = mesh.attributes.get(TAG)
    if a is not None and (a.domain != "FACE" or a.data_type != "INT"):
        mesh.attributes.remove(a)
        a = None
    if a is None:
        a = mesh.attributes.new(TAG, "INT", "FACE")
    values = face_tags(mesh)
    values[list(faces)] = rid
    a.data.foreach_set("value", values.tolist())
    mesh.update()


def evaluated_tags(obj, depsgraph):
    """Each face's tag as the object is shown, after its modifiers and any
    Subdivision. It is read through to_mesh, which subdivides even where the
    viewport does that on the GPU. Cached until the object's geometry
    changes."""
    _whose(obj)
    cached = _TAGS.get(obj.name)
    if cached is not None:
        return cached
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        tags = region_tags(regions_of(obj), me)
    finally:
        ev.to_mesh_clear()
    _TAGS[obj.name] = tags
    return tags


def mesh_triangles(me):
    """A mesh's vertex positions (V, 3), its triangles' vertices (T, 3) and
    each triangle's face (T,), as arrays, by the quickest reads Blender has.
    Measured on a million faces: the position attribute reads in 4 ms
    against the vertices' 30, and the triangles' faces in 91 against 167."""
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    tris = np.empty(3 * n, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tris)
    faces = np.empty(n, dtype=np.int32)
    polys = getattr(me, "loop_triangle_polygons", None)
    if polys is not None:
        polys.foreach_get("value", faces)
    else:
        me.loop_triangles.foreach_get("polygon_index", faces)
    co = np.empty(3 * len(me.vertices), dtype=np.float32)
    pos = me.attributes.get("position")
    if pos is not None and pos.domain == "POINT" and pos.data_type == "FLOAT_VECTOR":
        pos.data.foreach_get("vector", co)
    else:
        me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3), tris.reshape(-1, 3), faces


# object name -> (geometry dict, points (V, 3), {region id: triangles (T, 3)},
# {region id: each triangle's face (T,)})
_SHARED = {}


def region_geometry(obj, depsgraph):
    """Each region of the object as its shown triangles, with their bounds:
    {region id: (points (n, 3), lo, hi)}. The points are in the object's own
    space, float32 and ready for a GPU batch as they are, lifted a hair
    along the normals so the paint lies on the surface. A whole region is
    every face no tagged region holds. Cached until the object's geometry
    changes."""
    _whose(obj)
    cached = _GEOMETRY.get(obj.name)
    if cached is not None:
        return cached
    out, tris_of, faces_of, co = {}, {}, {}, None
    regs = regions_of(obj)
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        if len(me.polygons) and len(me.vertices) and regs:
            co, tris, faces = mesh_triangles(me)
            normals = np.empty(3 * len(me.vertices), dtype=np.float32)
            me.vertex_normals.foreach_get("vector", normals)
            lift = np.float32(0.003 * float(np.linalg.norm(co.max(0) - co.min(0))))
            co = co + normals.reshape(-1, 3) * lift
            tri_tags = region_tags(regs, me)[faces]
            tagged = {r.id for r in regs if not r.whole}
            free = ~np.isin(tri_tags, list(tagged)) if tagged else np.ones(len(faces), dtype=bool)
            for r in regs:
                keep = free if r.whole else tri_tags == r.id
                if keep.any():
                    kept = tris[keep]
                    pts = np.ascontiguousarray(co[kept].reshape(-1, 3))
                    # the bounds from the vertices used, not every corner
                    used = np.zeros(len(co), dtype=bool)
                    used[kept.ravel()] = True
                    out[r.id] = (pts, Vector(co[used].min(0).tolist()), Vector(co[used].max(0).tolist()))
                    tris_of[r.id] = kept
                    faces_of[r.id] = faces[keep]
    finally:
        ev.to_mesh_clear()
    _GEOMETRY[obj.name] = out
    _SHARED[obj.name] = (out, co, tris_of, faces_of)
    return out


# -- A region's outline (Highlight: Outline) ----------------------------------
#
# Greg: "a hover-over outline instead of a hover over full overlay ... a clean
# outline of the object and regions"

def region_edges(obj, depsgraph):
    """Each region's edges, worked out once per change of its geometry, and
    the shared points (region_geometry's, lifted off the surface).

    Returns ({region id: (pairs, border, a, b, normals, centers)}, points):
      pairs    (E, 2), indices into the points
      border   (E,) bool
      a, b     (E,) each, the faces either side, as indices into normals and
               centers. b is -1 on a border
      normals  (P, 3)
      centers  (P, 3)

    A border edge has one triangle of the region: it is where the region
    meets another region, the rest of the object, or the mesh's own edge.
    An edge between two of the region's faces may be on the contour,
    depending on the view (outline_points). The diagonal a face is cut into
    triangles along is neither. Faces, not triangles, decide which way they
    face, so a contour runs along whole faces' edges."""
    geometry = region_geometry(obj, depsgraph)
    cached = _EDGES.get(obj.name)
    if cached is not None and cached[0] is geometry:
        return cached[1], cached[2]
    edges, co = {}, None
    shared = _SHARED.get(obj.name)
    if shared is not None and shared[0] is geometry and len(shared) > 3:
        _geometry, co, tris_of, faces_of = shared
        count = len(co)
        for rid, tris in tris_of.items():
            faces = faces_of[rid]
            if not len(tris):
                continue
            pairs = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
            owner = np.concatenate([faces, faces, faces])
            pairs.sort(axis=1)
            key = pairs[:, 0].astype(np.int64) * count + pairs[:, 1]
            order = np.argsort(key, kind="stable")
            _keys, start, uses = np.unique(key[order], return_index=True, return_counts=True)
            first = order[start]
            second = order[np.minimum(start + 1, len(order) - 1)]
            fa = owner[first]
            fb = np.where(uses >= 2, owner[second], -1)
            border = uses == 1
            shared_edge = (uses == 2) & (fa != fb)          # not a face's own diagonal
            keep = border | shared_edge
            # each face once: its normal (the sum of its triangles' areas
            # times their normals) and its middle
            p0, p1, p2 = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
            ids, of = np.unique(faces, return_inverse=True)
            normals = np.zeros((len(ids), 3), dtype=np.float64)
            centers = np.zeros((len(ids), 3), dtype=np.float64)
            np.add.at(normals, of, np.cross(p1 - p0, p2 - p0))
            np.add.at(centers, of, (p0 + p1 + p2) / 3.0)
            centers /= np.bincount(of, minlength=len(ids))[:, None]
            a = np.searchsorted(ids, fa[keep])
            b = np.where(border[keep], -1, np.searchsorted(ids, np.where(fb[keep] < 0, ids[0], fb[keep])))
            edges[rid] = (pairs[first][keep], border[keep], a, b, normals, centers)
    _EDGES[obj.name] = (geometry, edges, co)
    return edges, co


# How far outline points are pulled toward the eye, as a share of the object's
# size: enough to clear the surface they lie on (with the lift region_geometry
# gives), and well short of the thickness of anything they should stay hidden
# behind
OUTLINE_PULL = 0.003


def outline_parts(obj, depsgraph, rid, eye=None, toward=None, front_only=False):
    """A region's outline, or None: its border edges and, of its edges
    between two faces, those with one face toward the view and the other
    away - its contour. The view is `eye`, a perspective view's eye, or
    `toward`, an orthographic view's direction, in the object's space.
    `front_only` keeps only the border edges of faces toward the view (a
    Show Through region, drawn over everything, shows no far side). Each
    point is pulled a little toward the eye, which leaves it where it is on
    screen and keeps the surface from cutting the line.

    Returns a dict:
      points  (2n, 3) float64, each segment's two ends
      pairs   (n, 2), each segment's two point numbers
      keys    (n,) int64, each edge's own number in the object, the same in
              every region of it
      border  (n,) bool
      inside  (n, 3), the middle of the region's face beside each edge,
              which says which side of a border is this region's"""
    edges, co = region_edges(obj, depsgraph)
    data = edges.get(rid)
    if data is None:
        return None
    pairs, border, a, b, normals, centers = data
    if eye is not None:
        facing = np.einsum("ij,ij->i", normals, centers - np.asarray(eye, dtype=np.float64)) < 0.0
    else:
        facing = normals @ np.asarray(toward, dtype=np.float64) < 0.0
    contour = ~border & (facing[a] != facing[np.maximum(b, 0)])
    shown = contour | (border & facing[a] if front_only else border)
    if not shown.any():
        return None
    kept = pairs[shown]
    pts = co[kept].reshape(-1, 3).astype(np.float64)
    pull = OUTLINE_PULL * (float(np.linalg.norm(co.max(0) - co.min(0))) or 1.0)
    if eye is not None:
        to_eye = np.asarray(eye, dtype=np.float64) - pts
        pts += to_eye * (pull / np.maximum(np.linalg.norm(to_eye, axis=1), 1e-12))[:, None]
    else:
        to_eye = -np.asarray(toward, dtype=np.float64)
        pts += to_eye * (pull / (np.linalg.norm(to_eye) or 1.0))
    return {"points": pts, "pairs": kept, "keys": kept[:, 0].astype(np.int64) * len(co) + kept[:, 1],
            "border": border[shown], "inside": centers[a[shown]]}


def outline_points(obj, depsgraph, rid, eye=None, toward=None, front_only=False):
    """outline_parts' segments alone, (2n, 3) float32 ready for a LINES batch,
    or None."""
    parts = outline_parts(obj, depsgraph, rid, eye=eye, toward=toward, front_only=front_only)
    return None if parts is None else np.ascontiguousarray(parts["points"], dtype=np.float32)


def chains(pairs):
    """Segments (pairs of point numbers, (n, 2)) joined end to end, as
    [(points in order, closed)]. A run breaks wherever more or fewer than
    two segments meet. A loop is closed: its first point comes again last."""
    touching = {}
    for s, (a, b) in enumerate(pairs.tolist()):
        touching.setdefault(a, []).append(s)
        touching.setdefault(b, []).append(s)
    used = [False] * len(pairs)
    out = []

    def walk(v, s):
        run = [v]
        while True:
            used[s] = True
            a, b = pairs[s]
            v = int(b) if int(a) == v else int(a)
            run.append(v)
            here = touching[v]
            if len(here) != 2:
                return run
            s = here[0] if here[1] == s else here[1]
            if used[s]:
                return run
    for v, here in touching.items():
        if len(here) != 2:
            for s in here:
                if not used[s]:
                    out.append((walk(v, s), False))
    for s in range(len(pairs)):
        if not used[s]:
            run = walk(int(pairs[s][0]), s)
            out.append((run, run[0] == run[-1]))
    return out


MITER_LIMIT = 2.0                  # a corner's ribbon at most this much wider than the line; sharper is cut


def stroke(points, pairs, matrix, size, width, inside=None, overlap=0.5, smooth=1.0):
    """Build lines as one ribbon of triangles per run of joined segments, on
    screen, `width` pixels wide with mitered corners. That way no pixel is
    covered twice and a corner is as even as the rest at any opacity: two
    square line ends notch a corner, and anything drawn twice shows darker.

    `points` are each point's position by number ({number: (3,)} or an
    array), in the space `matrix` (4 x 4, to clip space) projects from.
    `pairs` are the segments, and `size` is the view in pixels. With
    `inside` ((n, 3), a point on the side each segment belongs to) the
    ribbon is one-sided: it runs from `overlap` pixels across the line to
    `width / 2` on that side. So two regions sharing a border each show
    their color on their own side. Greg: "When 2 colors share a line can one
    side of the line be one color and the other side be the other color
    instead of just overlaying them?" Each ribbon is `smooth` pixels wider
    for its soft edge. Each vertex is put back at its point's own depth.

    Returns (positions, across, lo, hi), or None:
      positions  (m, 3) float32, in that space
      across     (m,) float32, each vertex's distance across the line in
                 pixels
      lo, hi     where the line's solid part runs, for the shader's soft
                 edges"""
    pairs = np.asarray(pairs)
    if not len(pairs):
        return None
    m = np.asarray(matrix, dtype=np.float64)
    inv = np.linalg.inv(m)
    size = np.asarray(size, dtype=np.float64)
    if inside is not None:
        lo, hi = -overlap, 0.5 * width
        side_of = {}
        for s, (a, b) in enumerate(pairs.tolist()):
            side_of[(a, b)] = side_of[(b, a)] = s
    else:
        lo, hi = -0.5 * width, 0.5 * width
    reach = (lo - smooth, hi + smooth)

    def clip_of(p):
        return m @ np.r_[np.asarray(p, dtype=np.float64), 1.0]

    pos_out, across_out = [], []
    for run, closed in chains(pairs):
        clip = np.array([clip_of(points[v]) for v in run])
        if (clip[:, 3] <= 1e-9).any():
            continue
        px = (clip[:, :2] / clip[:, 3:4] + 1.0) * 0.5 * size
        if closed:
            px, clip, run = px[:-1], clip[:-1], run[:-1]
        k = len(px)
        if k < 2:
            continue
        nxt = np.roll(px, -1, axis=0) - px if closed else np.diff(px, axis=0)
        seg_len = np.linalg.norm(nxt, axis=1)
        if (seg_len < 1e-6).all():
            continue
        tangent = nxt / np.maximum(seg_len, 1e-9)[:, None]
        normal = np.c_[-tangent[:, 1], tangent[:, 0]]
        if closed:
            before, after = np.roll(normal, 1, axis=0), normal
        else:
            before = np.r_[normal[:1], normal]
            after = np.r_[normal, normal[-1:]]
        miter = before + after
        mlen = np.linalg.norm(miter, axis=1)
        miter = np.where(mlen[:, None] > 1e-9, miter / np.maximum(mlen, 1e-9)[:, None], after)
        scale = 1.0 / np.maximum(np.einsum("ij,ij->i", miter, after), 1.0 / MITER_LIMIT)
        sign = 1.0
        if inside is not None:
            s = side_of[(run[0], run[1])]
            inner = clip_of(inside[s])
            if inner[3] > 1e-9:
                ipx = (inner[:2] / inner[3] + 1.0) * 0.5 * size
                sign = 1.0 if np.dot(ipx - 0.5 * (px[0] + px[1]), normal[0]) >= 0.0 else -1.0
        # an open run's ends reach half the width past its end points, so it
        # meets whatever it ends at
        ends = px.copy()
        if not closed and inside is None:
            ends[0] -= tangent[0] * 0.5 * width
            ends[-1] += tangent[-1] * 0.5 * width
        rim = []
        for a in reach:
            off = ends + miter * (scale * a * sign)[:, None]
            ndc = off / size * 2.0 - 1.0
            c = clip.copy()
            c[:, :2] = ndc * c[:, 3:4]
            back = c @ inv.T
            rim.append(back[:, :3] / back[:, 3:4])
        inner_rim, outer_rim = rim
        idx = np.arange(k)
        j = (idx + 1) % k if closed else idx[1:]
        i = idx if closed else idx[:-1]
        quads = np.stack([inner_rim[i], outer_rim[i], outer_rim[j],
                          inner_rim[i], outer_rim[j], inner_rim[j]], axis=1).reshape(-1, 3)
        pos_out.append(quads)
        across_out.append(np.tile([reach[0], reach[1], reach[1], reach[0], reach[1], reach[0]], len(i)))
    if not pos_out:
        return None
    return (np.ascontiguousarray(np.concatenate(pos_out), dtype=np.float32),
            np.ascontiguousarray(np.concatenate(across_out), dtype=np.float32), lo, hi)


def forget(name=None):
    """Drop what is cached, for one object or all. That includes the last ray
    cast, so a pixel the mouse comes back to after the scene changed is
    looked at again."""
    _HIT["key"] = None
    changed()
    if name is None:
        _TAGS.clear()
        _GEOMETRY.clear()
        _BVH.clear()
        _UNLISTED.clear()
        _SHARED.clear()
        _EDGES.clear()
        _WHOSE.clear()
    else:
        _TAGS.pop(name, None)
        _GEOMETRY.pop(name, None)
        _BVH.pop(name, None)
        _UNLISTED.pop(name, None)
        _SHARED.pop(name, None)
        _EDGES.pop(name, None)
        _WHOSE.pop(name, None)
    for fn in FORGET_HOOKS:
        fn(name)
    _HIT["key"] = None


def _whose(obj):
    """Make sure what is cached under `obj`'s name was worked out for this
    object and this mesh, and drop it if not.

    The caches are kept by object name, and a name can pass to another
    object without any geometry update to say so: delete Body, then rename
    Body.001 to Body, and Body's tags and shapes would be read for the other
    mesh - hovering the wrong region, painting the deleted one. So each name
    remembers whose caches it holds: the object, its mesh, and the mesh's
    face count. Every cache that reads geometry by name calls this before it
    reads (unlisted_tags, evaluated_tags, region_geometry). The edges and the
    hit test's tree need no call: they are rebuilt from region_geometry when
    it changes."""
    data = obj.data
    polygons = getattr(data, "polygons", None)
    who = (obj.as_pointer(), data.as_pointer() if data is not None else 0,
           len(polygons) if polygons is not None else 0)
    if _WHOSE.get(obj.name) != who:
        if obj.name in _WHOSE:
            forget(obj.name)
        _WHOSE[obj.name] = who


def _view_key(rv3d):
    """The view as a cache key: its whole projection, so a zoom, an orbit or
    a jump to another view - with the mouse still - is a new key."""
    return tuple(round(v, 6) for row in rv3d.perspective_matrix for v in row)


# -- Under the mouse ---------------------------------------------------------------------

def cast(context, origin, direction):
    """What a ray meets first: (object name, region id or None, point), or
    None. A tagged face belongs to its region. Any other face of an object
    with a whole region belongs to the whole region."""
    depsgraph = context.evaluated_depsgraph_get()
    ok, point, _normal, face, obj, _matrix = ray(context, origin, direction)
    if not ok or obj is None:
        return None
    src = obj.original
    regs = regions_of(src)
    rid = None
    if regs:
        tagged = {r.id for r in regs if not r.whole}
        if tagged:
            tags = evaluated_tags(src, depsgraph)
            tag = int(tags[face]) if 0 <= face < len(tags) else 0
            rid = tag if tag in tagged else None
        if rid is None:
            rid = next((r.id for r in regs if r.whole), None)
    return src.name, rid, point.copy()


def _own_tree(obj, depsgraph):
    """The object's regions as one BVH in its own space, with each
    triangle's region id. Cached with the region geometry it is built from."""
    geometry = region_geometry(obj, depsgraph)
    cached = _BVH.get(obj.name)
    if cached is not None and cached[0] is geometry:
        return cached[1], cached[2]
    # Built from the mesh's own vertices, shared between triangles. Built from
    # every triangle's three corners instead, it took 1.2 s on a million
    # faces; this way takes 0.6.
    tree, owner = None, []
    shared = _SHARED.get(obj.name)
    if shared is not None and shared[0] is geometry and shared[2]:
        co, tris_of = shared[1], shared[2]
        ids = list(tris_of)
        every = np.concatenate([tris_of[i] for i in ids]).ravel()
        owner = np.concatenate([np.full(len(tris_of[i]), i, dtype=np.int64) for i in ids]).tolist()
        used, inverse = np.unique(every, return_inverse=True)
        tree = BVHTree.FromPolygons(co[used].tolist(), inverse.reshape(-1, 3).tolist(), all_triangles=True)
    _BVH[obj.name] = (geometry, tree, owner)
    return tree, owner


def through_hit(context, obj, origin, direction):
    """A Show Through region of `obj` under the mouse, seen as if nothing
    else were in front: (region id, world point), or None. It counts only
    where the object's own nearest face along the ray is in that region, so
    the object's body, when nearer, still wins. Greg: "user hovers over body
    of digit, then they can hover over either start or end and see it drawn
    on top"."""
    through = {r.id for r in regions_of(obj) if r.show_through and not r.whole}
    if not through:
        return None
    tree, owner = _own_tree(obj, context.evaluated_depsgraph_get())
    if tree is None:
        return None
    mw = obj.matrix_world
    inv = mw.inverted()
    local = inv.to_3x3() @ direction
    loc, _normal, index, _dist = tree.ray_cast(inv @ origin, local.normalized())
    if index is None or owner[index] not in through:
        return None
    return owner[index], mw @ loc


# Show Through regions are often thin where they show: a cap seen past its
# body is a crescent, a sliver at its sides. So such a region holds the hover
# until the mouse is this much of a button's radius past its edge, and catches
# the hover as the mouse leaves its object this near one. Entering one stays
# immediate. Greg: "I am having a little trouble sometimes transitioning from
# the main digit body to a cap"; "the caps are thin at the edges where I put
# some controllers ... I can pretty easily mouse off and the buttons
# disappear".
THROUGH_REACH = 0.75


def through_near(context, obj, location, reach, want=None):
    """A Show Through region of `obj` within `reach` pixels of `location`
    (region pixels), as (region id, world point), or None. Only region
    `want` counts, if given. Points on two rings around the mouse are tried,
    the inner ring first."""
    region, rv3d = context.region, context.region_data
    for frac in (0.5, 1.0):
        for k in range(8):
            a = 2.0 * math.pi * (k + 0.5 * frac) / 8.0
            at = (location[0] + reach * frac * math.cos(a), location[1] + reach * frac * math.sin(a))
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, at)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, at)
            found = through_hit(context, obj, origin, direction)
            if found is not None and (want is None or found[0] == want):
                return found
    return None


def region_center(context, obj, rid):
    """The middle of a region on screen, or None."""
    geometry = region_geometry(obj, context.evaluated_depsgraph_get()).get(rid)
    if geometry is None:
        return None
    _pts, lo, hi = geometry
    return view3d_utils.location_3d_to_region_2d(context.region, context.region_data,
                                                 obj.matrix_world @ ((lo + hi) * 0.5))


_LAYOUTS = []


def add_layout(fn):
    """A program may place some of a region's buttons itself, leaving the
    rest to the region's Arrange. fn(context, obj, region) returns None when
    it places none, else (owned, circles, faded):
      owned    the indices of the buttons it places, which Arrange leaves out
      circles  their circles on screen, [(index, center)], back to front,
               leaving out any it hides
      faded    the indices of those to draw faded
    Circles placed this way are each their own band (in_block), not one band
    around them all, since they may be spread over the item.

    A fourth item, a dict, may give:
      holds  discs on screen, [(center, radius)], where the region keeps the
             hover whatever lies under the mouse. That covers all of a
             menu's ring, gaps included. Greg: "I can mouse left and right
             and up and down on a 4 item menu but I can't mouse between, the
             menu disappears".
      areas  polygons on screen, each [point, ...], that hold the hover the
             same way (in_area)."""
    if fn not in _LAYOUTS:
        _LAYOUTS.append(fn)


def remove_layout(fn):
    if fn in _LAYOUTS:
        _LAYOUTS.remove(fn)


# this frame's layouts (_FRAME): key -> (placed, static, faded, extra)
_LAYOUTS_DONE = {"frame": None, "by": {}}


def _layout(context, obj, region):
    """(placed, static, faded, extra) of a region's buttons on screen. It is
    worked out once a frame for each view (changed), because every region's
    gizmo asks at each mouse move and a menu of 3D handles is not cheap."""
    view, rv3d = context.region, context.region_data
    if _LAYOUTS_DONE["frame"] != _FRAME[0]:
        _LAYOUTS_DONE.update(frame=_FRAME[0], by={})
    moving = STATE.get("arranging")
    key = (obj.name if obj is not None else "", region.as_pointer(), view.as_pointer() if view is not None else 0,
           tuple(tuple(row) for row in rv3d.perspective_matrix) if rv3d is not None else None,
           (view.width, view.height) if view is not None else None,
           tuple(moving[:3]) + (tuple(moving[3]),) if moving else None, picking(context),
           button_radius(context), handle_radius(context), labels_mode(context), _signature(region))
    found = _LAYOUTS_DONE["by"].get(key)
    if found is None:
        found = _LAYOUTS_DONE["by"][key] = _work_out_layout(context, obj, region)
    placed, static, faded, extra = found
    return list(placed), list(static), set(faded), dict(extra)


def _signature(region):
    """A cheap summary of the region's own settings and buttons that its
    layout reads. An edit in the panel (a button made a gap, placed, or put
    in a menu) may come with no redraw, and the layout kept for this frame
    must still see it."""
    return (region.arrange, region.behind, region.button_count, region.whole,
            tuple((b.name, b.action, b.show, b.placed, tuple(b.place), b.anchor, b.handle, b.handle_shape,
                   b.handle_axis, b.handle_flip, b.handle_size, b.handle_length, b.handle_centered,
                   b.handle_behind, b.opens_menu,
                   b.menu_parent, b.uid, b.show_when, b.shape,
                   b.icon_type, b.back_placed, tuple(b.back_place), b.up.enabled, b.across.enabled)
                  for b in buttons_of(region)))


def _work_out_layout(context, obj, region):
    owned, placed, faded, extra = set(), [], set(), {}
    for fn in _LAYOUTS:
        got = fn(context, obj, region)
        if got:
            owned, placed = set(got[0]), list(got[1])
            faded = set(got[2]) if len(got) > 2 else set()
            extra = dict(got[3]) if len(got) > 3 and got[3] else {}
            break
    static = _arranged_layout(context, obj, region, owned)
    moving = STATE.get("arranging")
    if moving and obj is not None and moving[0] == obj.name and moving[1] == region.id:
        # a button being rearranged (arrange.py) follows the mouse - in the row,
        # or in an open menu's ring, which its layout places - the others in
        # its places as they now are
        static = [(i, Vector(moving[3]) if i == moving[2] else c) for i, c in static]
        placed = [(i, Vector(moving[3]) if i == moving[2] else c) for i, c in placed]
    if not picking(context):
        # A gap has kept its place among the others and is now dropped:
        # nothing is drawn there and nothing is hit. In Viewport Edit it
        # stays, drawn dashed, so it can be picked and moved.
        used = buttons_of(region)
        static = [(i, c) for i, c in static if i >= len(used) or not is_gap(used[i])]
        placed = [(i, c) for i, c in placed if i >= len(used) or not is_gap(used[i])]
    return placed, static, faded, extra


def layout_parts(context, obj, region):
    """(placed, static, faded): the circles a program places (add_layout),
    back to front; the rest, arranged by the region's Arrange; and the
    indices to draw faded."""
    return _layout(context, obj, region)[:3]


def layout_holds(context, obj, region):
    """The discs where a region keeps the hover (add_layout's "holds")."""
    return list(_layout(context, obj, region)[3].get("holds", ()))


def layout_areas(context, obj, region):
    """The polygons where a region keeps the hover (add_layout's "areas")."""
    return list(_layout(context, obj, region)[3].get("areas", ()))


def in_area(at, polygon):
    """Whether `at` is inside `polygon`, [point, ...] on screen - any shape,
    by the even-odd rule."""
    inside = False
    n = len(polygon)
    for k in range(n):
        a, b = polygon[k], polygon[k - 1]
        if (a[1] > at[1]) != (b[1] > at[1]):
            x = a[0] + (at[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if at[0] < x:
                inside = not inside
    return inside


def hull(points):
    """The convex hull of points on screen, counterclockwise: [point, ...]."""
    pts = sorted(set((float(p[0]), float(p[1])) for p in points))
    if len(pts) < 3:
        return [Vector(p) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    return [Vector(p) for p in lower[:-1] + upper[:-1]]


def button_layout(context, obj, region):
    """The region's button circles on screen, [(index, center)], back to
    front: those a program places (add_layout), then the rest in a row in
    the middle of the region, over the item itself. Greg found that with the
    row under the item, the buttons hovered over other items and the hover
    switched to them."""
    placed, static, _faded = layout_parts(context, obj, region)
    return placed + static


def _arranged_layout(context, obj, region, leave=()):
    used = buttons_of(region)
    shown = [i for i in shown_buttons(region, obj) if i not in leave]
    center = region_center(context, obj, region.id) if shown else None
    if center is None:
        return []
    radius, scale = button_radius(context), ui_scale(context)
    down = button_spacing(context)
    widths = [half_width(used[i], context) for i in shown]
    if labels_mode(context) == "ALWAYS":
        # room for every name under its circle (a text button is its name)
        widths = [w if used[i].icon_type == "TEXT"
                  else max(w, 0.5 * (label_width(used[i].name, context) + LABEL_GAP * scale))
                  for w, i in zip(widths, shown)]
        if region.arrange != "COLUMN":
            # a column's names go beside it (label_places), so no room under each
            down += label_height(context)
    return arranged(shown, center, region.arrange, button_spacing(context), down, widths,
                    button_spacing(context) - 2.0 * radius)


# -- Text buttons ---------------------------------------------------------------------------
#
# Greg: "an option for text-only. This would make the text field a little
# larger so that the text field takes up similar space as the icons." A
# button's Icon may be Text: its name in a rounded box as wide as the name and
# only as tall as its letters need. Greg: "It can be shorter vertically
# though". It is set per button, so a region can mix icons and words.

TEXT_PAD = 7.0                     # between a text button's name and its sides
TEXT_PAD_UP = 5.0                  # and above and below it (Greg: "less empty space within the button")
TEXT_ROUND = 0.6                   # a text box's corners, as a share of its half height
BADGE = 0.22                       # a badge's radius, as a share of a circle's (add_badge)


def text_size(context=None):
    """A text button's letters, in pixels: in proportion to Button Size."""
    return max(int(round(button_radius(context) * 0.8)), 1)


def half_size(button, context=None):
    """(half width, half height) of a button on screen: a circle's radius
    both ways, or a text button's box - as wide as its name, never narrower
    than a circle, and only as tall as its letters need."""
    radius = button_radius(context)
    if button.icon_type != "TEXT":
        return radius, radius
    import blf  # type: ignore
    scale = ui_scale(context)
    blf.size(0, text_size(context))
    width = max(radius, 0.5 * blf.dimensions(0, button.name or " ")[0] + TEXT_PAD * scale)
    height = min(radius, 0.5 * blf.dimensions(0, "H")[1] + TEXT_PAD_UP * scale)
    return width, height


def half_width(button, context=None):
    return half_size(button, context)[0]


# -- Square buttons ------------------------------------------------------------------------
#
# Greg: "options for square buttons vs. round ... the ability to create visual
# distinction"; "Squares have rounded corners like the text boxes for sure".
# A button's Shape is a circle, or a square of the same size with its corners
# rounded as a text box's are. Every outline is a box with round corners (a
# circle's corners are its radius), so one test hits, overlaps and avoids all
# three.

def boxed(button):
    """Whether a button is a box on screen - a text button, or a square -
    rather than a circle."""
    return button.icon_type == "TEXT" or getattr(button, "shape", "CIRCLE") == "SQUARE"


def button_colors(region):
    """The color each button in use is drawn in, as buttons_of lists them.
    A button takes its list's color. Greg: "Button groups should always have
    the same color for buttons so per button color overrides aren't
    necessary". A list that overrides it has its own color: the region's own
    buttons (in its row or placed in 3D), or a menu (its button's
    menu_color). A list that does not takes the color of what it hangs from.
    The region's own buttons take the region's color (Greg: "The default of
    adopting the color is fine"), and a menu takes the color of the button
    that opens it."""
    from . import menus
    used = buttons_of(region)
    up = menus.parents(region)
    own = tuple(region.button_color) if region.use_button_color else tuple(region.color)
    out = [None] * len(used)

    def color(i):
        if out[i] is None:
            j = up[i]
            if j is None:
                out[i] = own
            else:
                opener = used[j]
                out[i] = tuple(opener.menu_color) if opener.menu_use_color else color(j)
        return out[i]

    return [color(i) for i in range(len(used))]


def button_color(region, button):
    """The color one button is drawn in (button_colors)."""
    used = buttons_of(region)
    index = next((i for i, b in enumerate(used) if b == button), None)
    return button_colors(region)[index] if index is not None else tuple(region.color)


def outline_of(button, context=None):
    """(half width, half height, corner) of a button's outline on screen: a
    circle is a box whose corners are its radius."""
    half, tall = half_size(button, context)
    return (half, tall, tall * TEXT_ROUND) if boxed(button) else (half, tall, half)


def outline_distance(offset, outline):
    """How far `offset` (from a button's center) is outside its outline (half
    width, half height, corner) - negative inside."""
    w, h, corner = outline
    corner = min(corner, w, h)
    qx, qy = abs(offset.x) - (w - corner), abs(offset.y) - (h - corner)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - corner


def outlines_overlap(a, oa, b, ob):
    """Whether two outlines (half width, half height, corner) about centers
    `a` and `b` overlap. They do when their boxes, shrunk by the corners,
    are closer than the two corners' radii added together."""
    ca, cb = min(oa[2], oa[0], oa[1]), min(ob[2], ob[0], ob[1])
    dx = max(abs(b.x - a.x) - (oa[0] - ca) - (ob[0] - cb), 0.0)
    dy = max(abs(b.y - a.y) - (oa[1] - ca) - (ob[1] - cb), 0.0)
    return math.hypot(dx, dy) < ca + cb


def badge_at(button, center, context=None):
    """(center, radius) of a button's badge (add_badge): a small circle on its
    outline at the upper right - a circle's at 45 degrees, a text box's or a
    square's on its rounded corner."""
    radius = button_radius(context)
    size = max(BADGE * radius, 3.0 * ui_scale(context))
    lean = math.sqrt(0.5)
    if not boxed(button):
        return Vector((center.x + radius * lean, center.y + radius * lean)), size
    half, tall, round_ = outline_of(button, context)
    return Vector((center.x + half - round_ * (1.0 - lean), center.y + tall - round_ * (1.0 - lean))), size


def near_button(at, center, half, radius, slack=0.0):
    """Whether `at` is on a button: within a circle of `radius`, a box `half`
    (half width, half height, or a half width alone) about its center, or an
    outline (half width, half height, corner; outline_of)."""
    if not isinstance(half, tuple):
        half = (half, radius)
    if len(half) == 3:
        return outline_distance(at - center, half) <= slack
    if half[0] <= radius + 1e-6 and half[1] >= radius - 1e-6:
        return (at - center).length <= radius + slack
    return abs(at.x - center.x) <= half[0] + slack and abs(at.y - center.y) <= half[1] + slack


# -- Labels --------------------------------------------------------------------------------
#
# A button's name under its circle. Greg: "Text label under each button ...
# Could be good. Could also be noisy". So names show on hover by default (the
# circle under the mouse shows its name, and nothing else moves), or always,
# with the buttons spaced to make room, or never (Scene.kneady_labels).

LABEL_POINTS = 11.0                # the text's size at an interface scale of 1
LABEL_GAP = 6.0                    # between a circle and its name, and between names
LABEL_PAD = 3.5                    # between a name and its box, above and below


def labels_mode(context=None):
    return getattr((context or bpy.context).scene, "kneady_labels", "HOVER")


def label_size(context=None):
    return max(int(round(LABEL_POINTS * ui_scale(context))), 1)


def label_width(text, context=None):
    """How wide a button's name is drawn, in pixels."""
    import blf  # type: ignore
    blf.size(0, label_size(context))
    return blf.dimensions(0, text)[0]


def label_box(center, width, radius, context=None, avoid=()):
    """Where a name `width` pixels wide goes under a circle at `center`:
    (x0, y0, x1, y1) its box, and (x, y) where its text starts, on the
    baseline. The text is centered on the capitals' height, as a text
    button's name is (Greg: "a little more space beneath the text than
    above"), so a descender dips into the room below.

    `avoid` is the other buttons showing, each (center, half width, half
    height, round). A name never covers one where it can help it. Where it
    would cover one under its circle, it goes beside it: on the right, else
    the left, else above. Greg: "Instead of omitting it just put it to the
    side of the button. I'd prefer to have the label". With buttons all
    round (a menu's opener in its ring), it goes over the lower half of its
    own button, so the buttons stay close. Greg: "when I hover over that
    button the label should appear over the lower half of that button". A
    column's names go together (label_places)."""
    choices = _label_choices(center, width, radius, context)
    n = _best_place([sum(1 for other in avoid if _covers(choice[0], other)) for choice in choices])
    return _settled(choices[n], center, avoid, context) if n == 4 else choices[n]


LABEL_TOUCH = 2.0                  # pixels between a name over its button and the button just under it


def _settled(choice, center, others, context=None):
    """Bring a name over its own button (OVER) down until it all but touches
    the button under it, if there is one; never up. Greg: "Bring that label
    down to where it almost touches the button below when surrounded by 4
    buttons". `others` are the other buttons, each (center, half width, half
    height, corner)."""
    (x0, y0, x1, y1), (x, y) = choice
    floor = None
    for c, half_w, half_h, _corner in others:
        # under the name: lower than its button, and across from the name
        if c.y >= center.y or c.x + half_w <= x0 or c.x - half_w >= x1:
            continue
        floor = c.y + half_h if floor is None else max(floor, c.y + half_h)
    if floor is None:
        return choice
    drop = y0 - (floor + LABEL_TOUCH * ui_scale(context))
    if drop <= 0.0:
        return choice
    return (x0, y0 - drop, x1, y1 - drop), (x, y - drop)


def _best_place(covered, wanted=0):
    """Which of _label_choices a name takes, by how many buttons each place
    covers. It takes `wanted` if that covers no more than any other place
    outside the button, else the outside place covering the fewest. With a
    button at every side, it goes over the lower half of its own (OVER)."""
    outside = covered[:4]
    if wanted == 4 or min(outside) > 0:
        return 4
    return wanted if outside[wanted] <= min(outside) else outside.index(min(outside))


def _label_choices(center, width, radius, context=None):
    """The places a name may go about its button, in label_box's order -
    under it, on its right, its left, above it, over its lower half - each
    ((x0, y0, x1, y1), (x, y))."""
    import blf  # type: ignore
    scale = ui_scale(context)
    blf.size(0, label_size(context))
    cap = blf.dimensions(0, "H")[1]
    pad = LABEL_PAD * scale
    gap = LABEL_GAP * scale
    x = center.x - 0.5 * width
    top = center.y - radius - gap
    y = top - pad - cap
    below = (x - pad - scale, y - pad, x + width + pad + scale, top), (x, y)
    # beside it: level with the circle's middle, as the name centers on the capitals
    side_y = center.y - 0.5 * cap
    right_x = center.x + radius + gap + pad + scale
    right = (right_x - pad - scale, side_y - pad, right_x + width + pad + scale, side_y + cap + pad), (right_x, side_y)
    left_x = center.x - radius - gap - pad - scale - width
    left = (left_x - pad - scale, side_y - pad, left_x + width + pad + scale, side_y + cap + pad), (left_x, side_y)
    bottom = center.y + radius + gap
    above = (below[0][0], bottom, below[0][2], bottom + 2.0 * pad + cap), (x, bottom + pad)
    # over its own lower half: the box centered half way down the circle
    mid = center.y - 0.5 * radius
    over = (below[0][0], mid - 0.5 * cap - pad, below[0][2], mid + 0.5 * cap + pad), (x, mid - 0.5 * cap)
    return below, right, left, above, over


LABEL_PLACES = ("BELOW", "RIGHT", "LEFT", "ABOVE", "OVER")      # _label_choices' order
# and one place only a program asks for (add_layout's "labels"): no name at
# all. It is for an open menu's own button, with its ring all round it. Greg:
# "Let's not show the center button label". Before that, the name went past
# the ring's lower right corner for a day, and over its own lower half before
# that.
NO_NAME = "NONE"


def label_places(buttons, widths, radius, context=None, prefer=None):
    """Where each button's name goes, {key: (box, at)} for the keys of
    `widths` (each name's width in pixels). `buttons` is every button
    showing, named or not, each (key, center, half width, half height,
    corner), as outline_of gives.

    Each name goes where label_box puts it, but a stack's names go together.
    A stack is buttons one under another, close enough that a name under one
    would cover the next. The top one's name goes above it, the bottom one's
    below, and those between beside them, all on one side. Greg: "For
    vertical menu's the top button should have the label above, bottom
    button should have it below. Between buttons show on the side" (before
    that, every name in a stack went on the side). So a column's middle
    names go to its right, and Row + Column's to the outside of each column.
    The side is the one that covers the fewest buttons over the stack's
    middle. A name that would cover a button where it is meant to go goes
    to another place instead, if that place covers fewer.

    `prefer`, {key: (place, fixed)} with a place from LABEL_PLACES, is where
    a program would have a name go (add_layout's "labels"): a menu's
    buttons' names away from its middle, its own button's over its lower
    half. A fixed one goes there whatever it covers, and the other names
    keep off it as off a button."""
    outlines = {k: (c, half_w, half_h, corner) for k, c, half_w, half_h, corner in buttons}
    choices = {k: _label_choices(c, widths.get(k, 0.0), radius, context) for k, c, *_rest in buttons}
    prefer = {k: v for k, v in (prefer or {}).items() if k in choices and k in widths}
    def chosen(k, n):
        """Place n of k's name, OVER brought down to the button under it."""
        if n != 4:
            return choices[k][n]
        return _settled(choices[k][4], outlines[k][0], [o for j, o in outlines.items() if j != k], context)

    unnamed = {k for k, (place, _fixed) in prefer.items() if place == NO_NAME}
    fixed = {k: chosen(k, LABEL_PLACES.index(place)) for k, (place, is_fixed) in prefer.items()
             if is_fixed and place in LABEL_PLACES}
    # a fixed name is in the way of the others, as a button is
    obstacles = dict(outlines)
    for k, ((x0, y0, x1, y1), _at) in fixed.items():
        obstacles[("label", k)] = (Vector((0.5 * (x0 + x1), 0.5 * (y0 + y1))), 0.5 * (x1 - x0), 0.5 * (y1 - y0), 0.0)
    # A stack joins each button to any button under it, roughly in line with
    # it, that its name would cover. Text buttons count too: they show no
    # name but are in the column.
    stack = {k: k for k in choices}

    def root(k):
        while stack[k] != k:
            k = stack[k]
        return k

    for k, (c, *_o) in outlines.items():
        under_k = choices[k][0][0]
        for j, other in outlines.items():
            if j != k and abs(other[0].x - c.x) < radius and other[0].y < c.y and _covers(under_k, other):
                stack[root(j)] = root(k)
    named = [k for k in choices if k in widths and k not in fixed and k not in unnamed]
    covered = {k: [sum(1 for j, other in obstacles.items() if j != k and j != ("label", k)
                       and _covers(choice[0], other))
                   for choice in choices[k]] for k in named}
    stacks = {}
    for k in choices:
        stacks.setdefault(root(k), []).append(k)
    out = dict(fixed)

    def place(k, n):
        out[k] = chosen(k, _best_place(covered[k], n))

    for keys in stacks.values():
        mine = [k for k in keys if k in covered]
        if len(keys) < 2:
            for k in mine:
                n = LABEL_PLACES.index(prefer[k][0]) if k in prefer and prefer[k][0] in LABEL_PLACES else 0
                place(k, n)
            continue
        # top to bottom, every button of the stack - a text button too, which
        # shows no name but is the top or the bottom
        order = sorted(keys, key=lambda k: -outlines[k][0].y)
        middle = [k for k in mine if k not in (order[0], order[-1])]
        sides = [sum(covered[k][n] for k in middle) for n in (1, 2)]
        side = 1 if sides[0] <= sides[1] else 2
        for k in mine:
            if k in prefer and prefer[k][0] in LABEL_PLACES:
                place(k, LABEL_PLACES.index(prefer[k][0]))
            else:
                place(k, 3 if k == order[0] else 0 if k == order[-1] else side)
    return out


def _covers(box, other):
    """Whether a name's box (x0, y0, x1, y1) covers a button. `other` is the
    button's (center, half width, half height, corner), as outline_of gives,
    or the older form (center, half width, half height, round), with round
    True for a circle."""
    center, half_w, half_h, corner = other
    if isinstance(corner, bool):
        corner = half_w if corner else 0.0
    corner = min(corner, half_w, half_h)
    x0, y0, x1, y1 = box
    # the gap between the name's box and the button's box less its corners
    dx = max(x0 - (center.x + half_w - corner), 0.0, (center.x - half_w + corner) - x1)
    dy = max(y0 - (center.y + half_h - corner), 0.0, (center.y - half_h + corner) - y1)
    if corner > 0.0:
        return dx * dx + dy * dy < corner * corner
    return x0 < center.x + half_w and x1 > center.x - half_w and y0 < center.y + half_h and y1 > center.y - half_h


label_choices = _label_choices
covers = _covers


def label_height(context=None):
    """The height of the line a name takes under its circle: its box (the
    capitals' height, with LABEL_PAD above and below) plus the gap above
    it."""
    import blf  # type: ignore
    blf.size(0, label_size(context))
    return blf.dimensions(0, "H")[1] + (2.0 * LABEL_PAD + LABEL_GAP) * ui_scale(context)


def ui_scale(context=None):
    """Blender's interface scale: the Resolution Scale preference times the
    display's own (2 for a Retina or 4K screen). It keeps the buttons, their
    band and a drag's speed looking and feeling the same on any screen.
    Every size Kneady gives in pixels is at a scale of 1 and multiplied by
    this. Without a window (a background run) the display's part reads 0,
    so the preference is used alone."""
    if FIXED_SCALE is not None:
        return FIXED_SCALE
    prefs = (context or bpy.context).preferences
    return getattr(prefs.system, "ui_scale", 0.0) or getattr(prefs.view, "ui_scale", 1.0) or 1.0


# A scale to use instead of Blender's, or None. It is for tests and scripts
# run with someone's own preferences, which must not change those preferences
# to get a scale of 1. (A Resolution Scale of 1.25 made every drag move 0.8 as
# far.)
FIXED_SCALE = None


def button_radius(context=None):
    """The buttons' radius in pixels, by the scene's Button Size and the
    interface scale (ui_scale)."""
    radius = getattr((context or bpy.context).scene, "kneady_button_radius", BUTTON_RADIUS)
    return min(max(radius, BUTTON_RADIUS_MIN), BUTTON_RADIUS_MAX) * ui_scale(context)


HANDLE_RADIUS_MIN, HANDLE_RADIUS_MAX = 6.0, 40.0


def handle_radius(context=None):
    """The 3D handles' radius in pixels, which measures an arrow and a ring.
    It comes from the scene's Handle Size (separate from Button Size) and
    the interface scale. A handle's own Size multiplies it."""
    radius = getattr((context or bpy.context).scene, "kneady_handle_radius", BUTTON_RADIUS)
    return min(max(radius, HANDLE_RADIUS_MIN), HANDLE_RADIUS_MAX) * ui_scale(context)


def button_spacing(context=None):
    return button_radius(context) * BUTTON_SPACING / BUTTON_RADIUS


def grid_rows(count, arrange):
    """The buttons' rows, top to bottom, as positions in their order. That
    is one row, one column, or Row + Column, which from four buttons on
    makes two columns. Greg: "At 4, it creates 2 rows and 2 columns. At 5, 2
    rows and 2 columns with the 5th centered above in between columns. At 6,
    3 rows 2 columns"."""
    order = list(range(count))
    if arrange == "COLUMN":
        return [[k] for k in order]
    if arrange != "GRID" or count <= 3:
        return [order]
    # Rows of two, with an odd last one centered above them. This covers
    # seven and eight buttons too, since the row holds eight.
    even = count - count % 2
    pairs = [order[k:k + 2] for k in range(0, even, 2)]
    return ([[count - 1]] if count % 2 else []) + pairs


def arranged(indices, center, arrange="ROW", spacing=BUTTON_SPACING, spacing_up=None, half_widths=None,
             gap=None):
    """Circles for buttons `indices` centered on `center`, by grid_rows.
    Each row is centered across and the rows are centered up and down,
    `spacing` apart across and `spacing_up` (or the same) up and down. Greg:
    "the option to arrange the buttons vertically or horizontally". Or a
    ring (Greg: "arranging the buttons into a circle"), the first at the top
    and the rest clockwise, with neighbors `spacing` apart; a lone button
    sits in the middle. With `half_widths` (one per index) the buttons sit
    side by side `gap` apart, each as wide as it is, since text buttons are
    wider than circles."""
    if half_widths is None:
        half_widths = [0.5 * spacing - 0.5 * (gap or 0.0)] * len(indices)
        gap = gap or 0.0
        uniform = True
    else:
        uniform = False
        gap = spacing - 2.0 * min(half_widths) if gap is None else gap
    if arrange == "CIRCLE" and len(indices) > 1:
        n = len(indices)
        chord = spacing if uniform else 2.0 * max(half_widths) + gap
        radius = chord / (2.0 * math.sin(math.pi / n))
        return [(i, Vector((center.x + radius * math.cos(math.pi / 2 - 2 * math.pi * k / n),
                            center.y + radius * math.sin(math.pi / 2 - 2 * math.pi * k / n))))
                for k, i in enumerate(indices)]
    rows = grid_rows(len(indices), arrange)
    out = []
    up = spacing if spacing_up is None else spacing_up
    for r, row in enumerate(rows):
        y = center.y + (0.5 * (len(rows) - 1) - r) * up
        if uniform:
            for k, slot in enumerate(row):
                x = center.x + (k - 0.5 * (len(row) - 1)) * spacing
                out.append((indices[slot], Vector((x, y))))
            continue
        total = sum(2.0 * half_widths[s] for s in row) + gap * (len(row) - 1)
        x = center.x - 0.5 * total
        for slot in row:
            out.append((indices[slot], Vector((x + half_widths[slot], y))))
            x += 2.0 * half_widths[slot] + gap
    return sorted(out, key=lambda item: indices.index(item[0]))


def in_block(circles, at, radius=BUTTON_RADIUS, scale=1.0, spread=False, below=0.0, widths=None):
    """Whether `at` is in the narrow band around a row or column of circles,
    gaps included. The band is `scale` times its width at a scale of 1
    (ui_scale), and reaches `below` further down for the names under the
    circles. Circles `spread` over the item (add_layout) each have their own
    band. `widths` is {index: half width, or (half width, half height)} for
    buttons that are not circles (text buttons)."""
    if not circles:
        return False
    band = BUTTON_BLOCK * scale
    widths = widths or {}

    def half(i):
        found = widths.get(i, radius)
        return found if isinstance(found, tuple) else (found, radius)

    if spread:
        return any(near_button(at, c, half(i), radius, band) for i, c in circles)
    reach = radius + band
    left = min(c.x - half(i)[0] for i, c in circles) - band
    right = max(c.x + half(i)[0] for i, c in circles) + band
    ys = [c.y for _i, c in circles]
    return left <= at.x <= right and min(ys) - reach - below <= at.y <= max(ys) + reach


def pin(obj_name, rid):
    """Hold a region's buttons on screen, hovered or not, for a program
    editing them (placing them by hand). Its paint is drawn through whatever
    covers it, its buttons are shown, and the hover is held on it. unpin()
    lets go."""
    STATE["pinned"] = (obj_name, rid)
    STATE.update(hover=(obj_name, rid), button=None, block=False, held=None)
    redraw()


def unpin():
    STATE["pinned"] = None
    STATE.update(hover=None, button=None, block=False, held=None)
    redraw()


# -- The spot clicked ----------------------------------------------------------------------
#
# A click can change the buttons under the mouse: a toggle hides some and
# shows others, and a program's click (add_click_hook) opens more. Where the
# clicked button was, there may now be no button, and the hover used to go to
# whatever lay under it - another region, which took the hover from the one
# clicked. Greg: "In that moment of switching, kneady ends up catching the
# adjacent region ... maybe when switching menus, selection is blocked until
# the new menu is present". So the spot clicked holds its region hovered, as
# the band around a row does, until the mouse moves off it.

def hold_click(context, obj, region, at, index=None):
    """Hold `region` hovered at `at` (region pixels), where a click on
    button `index` landed, until the mouse leaves the spot. The spot is a
    circle as wide as the button plus the band around it."""
    used = buttons_of(region)
    half = max(half_size(used[index], context)) if index is not None and 0 <= index < len(used) \
        else button_radius(context)
    view = context.region
    STATE["held"] = (obj.name, region.id, view.as_pointer() if view is not None else 0,
                     Vector((at[0], at[1])), half + BUTTON_BLOCK * ui_scale(context))


def held_at(hover, at, view):
    """Whether the spot clicked (hold_click) holds `hover` with the mouse at
    `at` in `view`. Off the spot, or once something else is hovered, it lets
    go for good."""
    held = STATE.get("held")
    if held is None or view is None or held[2] != view.as_pointer():
        return False
    if hover is None or (hover[0], hover[1]) != (held[0], held[1]) or (at - held[3]).length > held[4]:
        STATE["held"] = None
        return False
    return True


def buttons_under(context, obj, region, at):
    """(block, button): whether `at` (region pixels) is in the band around a
    region's buttons, and the index of the button under it (the front one
    where two overlap), or None. A button a program draws as a 3D handle
    (add_layout's "handles") is hit along its shape, and not at all while it
    points at the viewer."""
    placed, static, _faded, extra = _layout(context, obj, region)
    used = buttons_of(region)
    radius, scale = button_radius(context), ui_scale(context)
    handles = extra.get("handles", {})
    flat = [(i, c) for i, c in placed if i not in handles]
    widths = {i: outline_of(used[i], context) for i, _c in flat + static}
    below = label_height(context) if labels_mode(context) == "ALWAYS" else 0.0
    band = BUTTON_BLOCK * scale
    block = in_block(static, at, radius, scale, False, below, widths) \
        or in_block(flat, at, radius, scale, True, 0.0, widths) \
        or any(handle_hit(h, at, band) for h in handles.values()) \
        or any((at - Vector(c)).length <= r for c, r in extra.get("holds", ())) \
        or any(in_area(at, polygon) for polygon in extra.get("areas", ()))
    if not block:
        return False, None
    # the front first: the arranged row is drawn over the placed buttons, and
    # the placed run back to front
    for i, c in reversed(placed + static):
        if i in handles:
            if handle_hit(handles[i], at, 2.0 * scale):
                # Handles hit together, such as an arrow through a ring at one
                # point (Digit's Move arrows and roll ring at a finger's
                # knuckle): the press goes to the one whose shape is nearest
                # the mouse, not the last in the list.
                hits = [j for j, h in handles.items() if handle_hit(h, at, 2.0 * scale)]
                return True, min(hits, key=lambda j: (handle_distance(handles[j], at), j != i))
        elif near_button(at, c, widths[i], radius, 2.0 * scale):
            return True, i
    return True, None


def area_distance(at, polygon):
    """How far screen point `at` is from a closed polygon's outline."""
    pts = list(polygon)
    return min(segment_distance(at, a, b) for a, b in zip(pts, pts[1:] + pts[:1]))


def near_area(at, polygon, reach):
    """Whether `at` is in a polygon (3 points or more), or within `reach`
    pixels of its outline."""
    if len(polygon) < 3:
        return False
    return in_area(at, polygon) or (reach > 0.0 and area_distance(at, polygon) <= reach)


def segment_distance(at, a, b):
    """How far screen point `at` is from the segment `a`-`b`."""
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-12 else max(0.0, min(1.0, (at - a).dot(ab) / ab.length_squared))
    return (at - (a + ab * t)).length


def handle_hit(handle, at, slack=0.0):
    """Whether screen point `at` is on a 3D handle (add_layout's "handles":
    base, tip, reach, head, live) that takes a drag: its shaft, as wide as its
    reach, or its head's outline."""
    if not handle.get("live", True):
        return False
    rim = handle.get("rim")
    if rim:
        # a ring: on its rim, not across its middle, which stays the item's
        return any(segment_distance(at, a, b) <= handle["reach"] + slack for a, b in zip(rim, rim[1:]))
    parts = handle.get("parts")
    if parts:
        # each of its arrows that takes a drag (two crossing arrows each count
        # on their own)
        for part in parts:
            if not part.get("live", True):
                continue
            # only where a faded shaft shows (placed.shaft_grab)
            if any(segment_distance(at, a, b) <= handle["reach"] + slack
                   for a, b in part.get("grab") or [part["shaft"]]):
                return True
            # a head, and a few pixels round it (placed.HEAD_REACH)
            if any(near_area(at, head, handle.get("head_reach", 0.0) + slack) for head in part["heads"]):
                return True
        return False
    if segment_distance(at, handle["base"], handle["tip"]) <= handle["reach"] + slack:
        return True
    # a head of another shape (a modeled one): the same few pixels round it
    # as an arrow's head gets, so every kind of head is as easy to grab
    head = handle.get("head") or ()
    return near_area(at, head, handle.get("head_reach", 0.0) + slack)


def handle_distance(handle, at):
    """How far screen point `at` is from a 3D handle's shape: its rim, or its
    arrows' shafts and heads (0 inside a head). Used to choose between
    handles hit together (buttons_under)."""
    rim = handle.get("rim")
    if rim:
        return min(segment_distance(at, a, b) for a, b in zip(rim, rim[1:]))
    best = math.inf
    for part in handle.get("parts") or ():
        if not part.get("live", True):
            continue
        if any(len(head) >= 3 and in_area(at, head) for head in part["heads"]):
            return 0.0
        for head in part["heads"]:
            if len(head) >= 3:
                best = min(best, area_distance(at, head))
        for a, b in part.get("grab") or [part["shaft"]]:
            best = min(best, segment_distance(at, a, b))
    if best < math.inf:
        return best
    return segment_distance(at, handle["base"], handle["tip"])


def layout_handles(context, obj, region):
    """The buttons a program draws as 3D handles (add_layout's "handles"):
    {index: handle}."""
    return dict(_layout(context, obj, region)[3].get("handles", {}))


_HOVER_DONE = {"key": None, "state": None, "result": None}


def _hover_state():
    return (STATE.get("hover"), STATE.get("button"), STATE.get("block"), STATE.get("edit"), STATE.get("kept"),
            STATE.get("pinned"), STATE.get("held"))


def hit_at(context, location):
    """What is under the mouse at `location` (region pixels), and the
    hovered region's button under it. There is one ray cast per position,
    shared by every region's gizmo. In the narrow band around a region's row
    of circles the region stays hovered, whatever is under the mouse, so a
    row wider than the item reaches past it. Greg: "that row of buttons
    should block switching to another item". Off the band the hover follows
    the mouse again.

    The answer is worked out once a position, because every region's gizmo
    asks. Once an answer leaves the hover as it found it (nothing changed,
    and the frame is the same - see changed), the others asking at that
    position get it as it is. An answer that changes the hover is worked out
    again by the next to ask, so a region the mouse has just come onto still
    counts its own row at once."""
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return None
    key = (int(location[0]), int(location[1]), region.as_pointer(), _FRAME[0], picking(context))
    state = _hover_state()
    if _HOVER_DONE["key"] == key and _HOVER_DONE["state"] == state:
        return _HOVER_DONE["result"]
    result = _work_out_hover(context, location)
    if _hover_state() == state and _FRAME[0] == key[3]:
        _HOVER_DONE.update(key=key, state=state, result=result)
    else:
        _HOVER_DONE["key"] = None
    return result


def _work_out_hover(context, location):
    region, rv3d = context.region, context.region_data
    if covered(context, location):
        # Under a panel drawn over the view (add_cover), nothing is hovered
        # through it. But a region held on screen, kept or picked stays.
        before = STATE["hover"]
        hover = STATE.get("pinned") or STATE.get("kept") or (before if picking(context) else None)
        if hover != before or STATE["button"] is not None or STATE["block"] or STATE.get("edit"):
            STATE.update(hover=hover, button=None, block=False, edit=None)
            if hover != before:
                _hovered(before, hover)
            redraw()
        return None
    # The ray is cast once per position and view, but the hover is worked out
    # every time, since it also depends on what was hovered before. The view
    # is part of the key: zoom or move the view with the mouse still, and
    # something else is under it.
    key = (int(location[0]), int(location[1]), region.as_pointer(), _view_key(rv3d))
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, location)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, location)
    if _HIT["key"] == key:
        result = _HIT["result"]
    else:
        result = cast(context, origin, direction)
        _HIT["key"], _HIT["result"] = key, result
    at = Vector((location[0], location[1]))

    def on_row(hover):
        """(block, button) for the mouse against a hovered region's row."""
        obj = bpy.data.objects.get(hover[0]) if hover is not None and hover[1] is not None else None
        held = find_region(obj, hover[1]) if obj is not None else None
        return buttons_under(context, obj, held, at) if held is not None else (False, None)

    if STATE.get("pinned"):
        # a region held on screen (pin): the hover stays on it
        pinned = STATE["pinned"]
        block, button = on_row(pinned)
        if pinned != STATE["hover"] or button != STATE["button"]:
            STATE.update(hover=pinned, button=button, block=block, edit=None)
            redraw()
        return result

    prev = before = STATE["hover"]
    block, button = on_row(prev)
    if not block:
        # where a click that changed the buttons landed (hold_click)
        block = held_at(prev, at, region)
    holding = STATE.get("kept")
    if holding is not None:
        obj = bpy.data.objects.get(holding[0])
        if obj is None or find_region(obj, holding[1]) is None:
            let_go(context)                 # its object or region is gone
            holding = None
        elif prev != holding:
            prev = holding
            block, button = on_row(prev)
    edit = None
    if button is None and prev is not None and prev[1] is not None and picking(context):
        # Viewport Edit's icons sit at the corners of the square around the
        # hovered region's buttons (pick.py). They are drawn over its band and
        # an open menu's ring, so they take the mouse first. The whole square,
        # out to the icons, holds the region hovered as its band does.
        from . import pick
        edit = pick.edit_hit(context, prev, at)
        if edit is not None:
            block = True
            if edit == pick.SQUARE:
                edit = None
    handles = None
    if not block and holding is None:
        # A program's handles under the mouse (add_hold_hook) are part of the
        # menu of the object they are on. That object stays hovered over them
        # with its menu open, and no other object takes the hover from under
        # them.
        handles = held_by_handles(context, at)
        if handles is not None and prev is not None and prev[0] == handles:
            block = True
    if holding is not None:
        # a region a program keeps hovered (keep), wherever the mouse is
        hover = prev
    else:
        hover = prev if block else (None if result is None else (result[0], result[1]))
    if handles is not None and not block:
        # the mouse came onto another object's handles: nothing under them is
        # hovered
        hover, result = None, None
    if not block and prev is not None and holding is None and handles is None:
        # The hovered object's Show Through regions are found past whatever
        # covers them, and they hold the object hovered, as the band does.
        held = bpy.data.objects.get(prev[0])
        through = through_hit(context, held, origin, direction) if held is not None else None
        if through is None and held is not None and hover != prev:
            # A Show Through region holds the hover a little past its edge
            # (THROUGH_REACH), and catches it as the mouse leaves its object.
            reach = THROUGH_REACH * button_radius(context)
            was = find_region(held, prev[1]) if prev[1] is not None else None
            if was is not None and was.show_through and not was.whole:
                through = through_near(context, held, location, reach, prev[1])
            if through is None and (hover is None or hover[0] != prev[0]):
                through = through_near(context, held, location, reach)
        if through is not None:
            hover = (prev[0], through[0])
            result = (prev[0], through[0], through[1])
    if hover is None and prev is not None and holding is None and picking(context):
        # Viewport Edit: the last region hovered - and its open menu - stays
        # while the mouse crosses empty space to the panel, until another
        # region is hovered
        hover = prev
    if not block and hover != prev:
        # On a region the mouse has just come onto, its own row counts at
        # once, so a press that follows a jump lands on the circle under it.
        block, button = on_row(hover)
    if hover != before or button != STATE["button"] or block != STATE["block"] or edit != STATE.get("edit"):
        STATE.update(hover=hover, button=button, block=block, edit=edit)
        if hover != before:
            _hovered(before, hover)
        redraw()
    return result


def redraw():
    """Redraw every 3D view in every window; this works from a handler or a
    timer too. A gizmo group is only set up when its view draws. Whatever
    was worked out once a frame is worked out again (changed)."""
    changed()
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


# -- What a drag drives ------------------------------------------------------------------

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}
TURNING = ("ROTATE", "MOVE")       # follow the mouse
VIEW_AXES = ("VIEW", "DEPTH")      # a Move or Rotate along the view, not the target's own axes


def axis_vector(name):
    v = Vector((0.0, 0.0, 0.0))
    v[AXIS_INDEX.get(name, 0)] = 1.0
    return v


def rotation_of(owner):
    """An object's or pose bone's rotation channels, as a 3x3."""
    if owner.rotation_mode == "QUATERNION":
        return owner.rotation_quaternion.normalized().to_matrix()
    if owner.rotation_mode == "AXIS_ANGLE":
        a, x, y, z = owner.rotation_axis_angle
        return Matrix.Rotation(a, 3, Vector((x, y, z)))
    return owner.rotation_euler.to_matrix()


def write_rotation(owner, m):
    if owner.rotation_mode == "QUATERNION":
        q = m.to_quaternion()
        owner.rotation_quaternion = q if q.dot(owner.rotation_quaternion) >= 0.0 else -q
    elif owner.rotation_mode == "AXIS_ANGLE":
        axis, a = m.to_quaternion().to_axis_angle()
        owner.rotation_axis_angle = (a, *axis)
    else:
        owner.rotation_euler = m.to_euler(owner.rotation_mode, owner.rotation_euler)


def resolve(drag, region_obj, point=None):
    """(object, pose bone or None) a drag acts on, or None: its target, its
    group's object (command_object), or the object dragged while Deform
    Hovered is on (props.dragged_of)."""
    return resolve_on(command_object(drag, region_obj, point)[0], drag.bone)


def resolve_on(obj, bone):
    """(object, pose bone or None) for an object and a bone name, or None."""
    if obj is None:
        return None
    if bone:
        if obj.type != "ARMATURE" or obj.pose is None:
            return None
        pb = obj.pose.bones.get(bone)
        return (obj, pb) if pb is not None else None
    return obj, None


def dominant_axis(v):
    """The index of a vector's largest component, by size."""
    return max(range(3), key=lambda i: abs(v[i]))


def axis_of(channel):
    """A channel's axis in its owner's frame: Channel.axis, or its command's
    for anything else shaped like a channel."""
    axis = getattr(channel, "axis", None)
    return axis if axis is not None else axis_vector(channel.drag.axis)


def scales_all(channel):
    return getattr(channel, "scale_all", channel.drag.axis == "ALL")


def world_matrix(obj, pb):
    return obj.matrix_world @ pb.matrix if pb is not None else obj.matrix_world


def _top_level(path):
    """Positions of the top-level '.' and '[' in a data path, outside quotes
    and brackets: (dots, brackets)."""
    depth, quote, dots, brackets = 0, None, [], []
    for i, ch in enumerate(path):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "[":
            if depth == 0:
                brackets.append(i)
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "." and depth == 0:
            dots.append(i)
    return dots, brackets


def property_bases(obj):
    """What a Property command's path is read from, in turn: the object, then
    its data, then its data's shape keys. So a path copied with Copy Data
    Path from a shape key's value (key_blocks["Sphere"].value, from its Key)
    or from the mesh works as one from the object does."""
    data = getattr(obj, "data", None)
    keys = getattr(data, "shape_keys", None) if data is not None else None
    return [base for base in (obj, data, keys) if base is not None]


def split_path(path):
    """A data path cut into (owner path, attribute, index or None). The
    attribute is a name or a ["key"] (a custom property), and the index is
    an array element's. 'pose.bones["B"].location[1]' -> ('pose.bones["B"]',
    'location', 1); 'data["prop"]' -> ('data', '["prop"]', None)."""
    path = path.strip()
    index = None
    m = re.match(r"^(.+)\[(\d+)\]$", path)
    if m:
        path, index = m.group(1), int(m.group(2))
    dots, brackets = _top_level(path)
    if re.search(r"\[[\"'].*[\"']\]$", path) and brackets:
        start = brackets[-1]
        return path[:start], path[start:], index
    if dots:
        return path[:dots[-1]], path[dots[-1] + 1:], index
    return "", path, index


def uneditable(obj):
    """Why `obj` cannot be changed here, or None. A character linked from its
    own file is posed through a library override (Object > Library Override
    > Make). A system override (one the override made for its own sake)
    first has to be made editable, as Blender's own tools require."""
    if not getattr(obj, "is_editable", True):
        where = bpy.path.basename(obj.library.filepath) if obj.library is not None else "another file"
        return "%s is linked from %s: make a library override to change it" % (obj.name, where)
    ol = getattr(obj, "override_library", None)
    if ol is not None and getattr(ol, "is_system_override", False):
        return "%s is a system override: make it editable (Object > Library Override > Make Editable)" % obj.name
    return None


def driven(owner, path, index=-1):
    """Whether a driver sets `path` on `owner` (one index of it, or any). A
    drag there would be put straight back."""
    ad = getattr(owner.id_data, "animation_data", None)
    if ad is None or not len(ad.drivers):
        return False
    try:
        full = owner.path_from_id(path)
    except (ValueError, TypeError):
        full = path
    return any(fc.data_path == full and (index < 0 or fc.array_index == index) and not fc.mute
               for fc in ad.drivers)


# Constraints that set a turn outright, so a turned channel changes beneath
# them but nothing moves while they hold.
TURN_OVERRIDES = {"COPY_ROTATION", "COPY_TRANSFORMS", "TRACK_TO", "DAMPED_TRACK", "LOCKED_TRACK",
                  "TRANSFORM", "ACTION", "CHILD_OF"}


def overridden_by(owner, kind):
    """The first constraint that takes a turn, move or scale out of the
    channel's hands, else None. For a turn, that is one of TURN_OVERRIDES,
    or an IK whose chain the bone is on. A drag still writes the channel (an
    FK value under IK is worth setting), and says so."""
    for c in getattr(owner, "constraints", ()):
        if c.mute or c.influence <= 0.0:
            continue
        if kind == "ROTATE" and c.type in TURN_OVERRIDES:
            return c
        if kind == "MOVE" and c.type in {"COPY_LOCATION", "COPY_TRANSFORMS", "CHILD_OF", "LIMIT_DISTANCE"}:
            return c
    pb = owner if isinstance(owner, bpy.types.PoseBone) else None
    if pb is not None and kind == "ROTATE":
        # an IK further down whose chain reaches this bone
        for other in pb.id_data.pose.bones:
            for c in other.constraints:
                if c.type != "IK" or c.mute or c.influence <= 0.0:
                    continue
                link, depth = other, 0
                while link is not None and (c.chain_count == 0 or depth < c.chain_count):
                    if link == pb:
                        return c
                    link, depth = link.parent, depth + 1
    if pb is not None:
        return _followers_overridden(pb, kind)
    return None


# What copies a whole transform, or the part a command drives, over what came
# before it on the same bone.
_COPIES = {"ROTATE": {"COPY_TRANSFORMS", "COPY_ROTATION"},
           "MOVE": {"COPY_TRANSFORMS", "COPY_LOCATION"},
           "SCALE": {"COPY_TRANSFORMS", "COPY_SCALE"}}


def _followers_overridden(pb, kind):
    """Spots a control whose effect nothing shows while a switch says so.
    That is when every bone that follows `pb` (by a constraint aiming at it)
    has a later copy at full strength over it, aimed at something else.
    Rigify's FK controls in IK are like this: their blend is on the ORG
    bones, so ORG-forearm.L copies forearm_fk.L, then MCH-forearm_ik.L at
    the IK_FK switch's strength. Returns that later copy, or None if any
    follower still reaches the result or there are no followers."""
    rig = pb.id_data
    copies = _COPIES.get(kind, set())
    overridden = None
    followed = False
    for other in rig.pose.bones:
        cons = list(other.constraints)
        for i, c in enumerate(cons):
            if getattr(c, "target", None) != rig or getattr(c, "subtarget", "") != pb.name or c.mute \
                    or c.influence <= 0.0:
                continue
            followed = True
            later = next((d for d in cons[i + 1:] if d.type in copies and not d.mute and d.influence >= 0.999
                          and getattr(d, "subtarget", "") != pb.name), None)
            if later is None:
                return None
            overridden = overridden or later
    return overridden if followed else None


def move_scale(obj, pb, frame, axis):
    """How much of a channel's own location one scene unit along `axis` is.
    A move's Speed is in scene units, and its owner's location may not be: a
    rig imported from FBX is scaled 0.01, so Speed 0.3 moved its hips 3 mm
    (found on a Mixamo rig)."""
    if pb is not None:
        space = obj.matrix_world.to_3x3() @ pb.bone.matrix_local.to_3x3()
    else:
        parent = obj.parent.matrix_world.to_3x3() if obj.parent is not None else Matrix.Identity(3)
        space = parent @ obj.matrix_parent_inverse.to_3x3() @ frame
    length = (space @ Vector(axis)).length
    return 1.0 / length if length > 1e-12 else 1.0


LOCKS = {"ROTATE": ("lock_rotation", "rotation"), "MOVE": ("lock_location", "location"),
         "SCALE": ("lock_scale", "scale")}


class Channel:
    """One command, resolved for a drag: what it writes and where it
    started. Where it cannot run, `ok` is False and `why` says why."""

    def __init__(self, drag, region_obj, region=None, point=None, switch=False):
        self.drag, self.kind = drag, drag.kind
        self.input = drag.input
        # the axis it turns about, moves along or scales on, in its owner's own
        # frame: the command's axis, unless a redirect turns it onto a bone
        self.axis = axis_vector(drag.axis)
        self.scale_all = drag.axis == "ALL"
        # View or Depth: the axis is the view's, set as the drag begins (use_view)
        self.view_mode = drag.axis if drag.axis in VIEW_AXES and drag.kind in TURNING else None
        self.integer = self.boolean = False
        self.ok = False
        # a program's kind a drag drives (add_command_kind's `drag`), and
        # whether it turns
        self.dragging = self.turning = False
        # `point`: where the drag was pressed, which picks a group's object
        obj, why = command_object(drag, region_obj, point)
        self.why = why or "Not found: check its target and what it drives"
        bone = drag.bone
        if getattr(drag, "program", ""):
            # a program's own kind (add_command_kind), read and written its way:
            # switched by a click (`switch`), else dragged
            self._init_program(drag, obj, switch)
            return
        if region is not None and obj is not None:
            # A program may send a command elsewhere (add_redirect). Digit
            # sends a child's Start Cap to its parent's End, and a frozen
            # digit's turns to its bone.
            for fn in _REDIRECTS:
                sent = fn(drag, obj, region)
                if sent is None:
                    continue
                if not isinstance(sent, dict):
                    sent = {"object": sent[0], "input": sent[1]}
                if sent.get("why"):
                    self.why = sent["why"]
                    return
                obj = sent.get("object", obj)
                bone = sent.get("bone", bone)
                self.kind = sent.get("kind", self.kind)
                self.input = sent.get("input", self.input)
                if sent.get("axis") is not None:
                    self.axis = Vector(sent["axis"]).normalized()
                    self.scale_all = False
                break
        found = resolve_on(obj, bone)
        if found is None:
            # what is missing, by name - a bone, input or property renamed
            # since the command was set leaves it pointing at nothing
            if obj is not None and bone and obj.type == "ARMATURE" and obj.pose is not None \
                    and bone not in obj.pose.bones:
                self.why = "%s has no bone %s: renamed? Choose it again" % (obj.name, bone)
            return
        self.obj, self.pb = found
        locked = uneditable(self.obj)
        if locked:
            self.why = locked
            return
        self.owner = self.pb if self.pb is not None else self.obj
        self.note = None
        self.key = (self.obj.name, self.pb.name if self.pb is not None else "")
        if self.kind in LOCKS:
            # Blender's own transform locks hold, as its tools hold them. A
            # digit's scale is locked, for one, since its sockets size it.
            attr, what = LOCKS[self.kind]
            locks = tuple(getattr(self.owner, attr))
            axes = range(3) if (self.kind == "SCALE" and self.scale_all) or self.view_mode \
                else (dominant_axis(self.axis),)
            if all(locks[i] for i in axes):
                self.why = "Its %s is locked" % what
                return
        if self.kind == "ROTATE":
            self.start = rotation_of(self.owner)
        elif self.kind == "MOVE":
            self.start = self.owner.location.copy()
            # along an object's own turned axes, or its Location channels
            # (along_parent); a bone always moves along its channels
            self.frame = rotation_of(self.owner) if self.pb is None and not getattr(drag, "along_parent", False) \
                else Matrix.Identity(3)
            self.move_scale = move_scale(self.obj, self.pb, self.frame, self.axis)
        elif self.kind == "SCALE":
            self.start = self.owner.scale.copy()
        elif self.kind == "INPUT":
            self.mod = props._gn_modifier(self.obj, drag.modifier)
            item = None
            if self.mod is not None and self.mod.node_group is not None and self.input:
                item = next((i for i in self.mod.node_group.interface.items_tree
                             if i.item_type == "SOCKET" and i.in_out == "INPUT" and i.name == self.input), None)
            if item is None:
                if self.mod is None:
                    self.why = "%s has no Geometry Nodes modifier%s" % (
                        self.obj.name, " %s" % drag.modifier if drag.modifier else "")
                elif self.mod.node_group is None:
                    self.why = "The modifier %s has no node group: choose one in its panel" % self.mod.name
                elif self.input:
                    self.why = "%s has no input %s: renamed? Choose it again" % (self.mod.name, self.input)
                else:
                    self.why = "Choose the input it drives"
                return
            self.ident = item.identifier
            self.integer = item.socket_type.startswith("NodeSocketInt")
            self.boolean = item.socket_type.startswith("NodeSocketBool")
            self.limits = (getattr(item, "min_value", -math.inf), getattr(item, "max_value", math.inf))
            self.start = float(input_value(self.mod, self.ident))
        elif self.kind == "PROPERTY":
            found = False
            owner_path, attr, index = split_path(drag.data_path)
            for base in property_bases(self.obj):
                try:
                    self.target_owner = base.path_resolve(owner_path) if owner_path else base
                    self.attr, self.index = attr, index
                    self.start = float(self._get())
                    found = True
                    break
                except Exception:             # not on this base: the next is tried, and
                    continue                  # none at all is said below (self.why)
            if not found:
                self.why = ("%s has no %s: renamed? Set its Path again" % (self.obj.name, drag.data_path)
                            if drag.data_path else "Set the Path it drives")
                return
            prop = (self.target_owner.bl_rna.properties.get(attr)
                    if attr and not attr.startswith("[") and hasattr(self.target_owner, "bl_rna") else None)
            self.limits = ((getattr(prop, "hard_min", -math.inf), getattr(prop, "hard_max", math.inf))
                           if prop is not None and prop.type in {"FLOAT", "INT"} else (-math.inf, math.inf))
            self.integer = prop is not None and prop.type == "INT"
            self.boolean = prop is not None and prop.type == "BOOLEAN"
            key = self._key_of()
            if key is not None:
                # A custom property keeps its own range and kind. A rig's IK /
                # FK switch, for one, is 0 to 1 (Rain's ik_arm_left).
                try:
                    ui = self.target_owner.id_properties_ui(key).as_dict()
                except (TypeError, AttributeError, KeyError):
                    ui = {}
                self.limits = (ui.get("min", -math.inf), ui.get("max", math.inf))
                stored = self.target_owner[key]
                self.boolean = isinstance(stored, bool)
                self.integer = isinstance(stored, int) and not self.boolean
        # a driver puts a drag straight back; a constraint holds the result
        # while the channel changes beneath it
        for owner, path, index, _group in _key_targets(self):
            if driven(owner, path, index):
                who = self.obj.name + (":" + self.pb.name if self.pb is not None else "")
                self.why = "%s's %s is set by a driver" % (who, self.input if self.kind == "INPUT" else path)
                return
        if self.kind in ("ROTATE", "MOVE", "SCALE"):
            holds = overridden_by(self.owner, self.kind)
            if holds is not None:
                self.note = "%s holds it" % holds.name
        self.ok = True

    def _init_program(self, drag, obj, switch=False):
        """Set up a program's kind of command (add_command_kind) on `obj`:
        the object hovered, or its target or group's object, as for any
        command. For a click (`switch`), it starts on or off as the program
        reads it. For a drag, it starts where the program's drag begins (its
        `drag`'s begin)."""
        self.kind = "PROGRAM"
        self.view_mode = None
        spec = _COMMAND_KINDS.get(drag.program)
        if spec is None:
            self.why = "Needs the add-on that made it (%s)" % drag.program
            return
        if obj is None:
            return
        dragged = spec.get("drag")
        if (switch or dragged is None) and spec.get("read") is None:
            self.why = "%s is not something a click switches" % spec["label"]
            return
        if not switch and dragged is None:
            self.why = "%s is not something a drag drives: a click switches it" % spec["label"]
            return
        why = spec["why"](obj, drag) if spec.get("why") else ""
        if why:
            self.why = why
            return
        self.spec, self.obj, self.pb, self.owner = spec, obj, None, obj
        self.note = None
        if not switch:
            try:
                state = dragged["begin"](bpy.context, obj, drag)
            except Exception as exc:          # a program's error must not stop the drag
                errors.caught("a program's drag start (%s)" % spec["label"])
                state = "%s failed: %s" % (spec["label"], exc)
            if state is None or isinstance(state, str):
                self.why = state or "%s cannot run on %s" % (spec["label"], obj.name)
                return
            self.state, self.dragging = state, True
            self.turning = bool(dragged["turns"](drag)) if dragged.get("turns") else False
            # its own key, so two on one object each write their own way
            self.key = (obj.name, "program", drag.program, id(self))
            self.start, self.limits = 0.0, (-math.inf, math.inf)
            self.ok = True
            return
        self.key, self.boolean = (obj.name, ""), True
        self.limits = (0.0, 1.0)
        self.start = 1.0 if spec["read"](obj, drag) else 0.0
        self.ok = True

    def motion(self, point):
        """A program drag's motion at `point` (add_command_kind's `drag`), or
        None."""
        if not self.dragging:
            return None
        return program_motion(self.drag, self.obj, point)

    def keys_taken(self):
        """The modifier keys a program drag reads itself (its `drag`'s keys)."""
        if not self.dragging or not self.spec["drag"].get("keys"):
            return set()
        try:
            return set(self.spec["drag"]["keys"](self.drag))
        except Exception:                     # a program's error must not stop the drag
            errors.caught("a program's keys")
            return set()

    def _key_of(self):
        m = re.match(r"^\[[\"'](.*)[\"']\]$", self.attr)
        return m.group(1) if m else None

    def _get(self):
        key = self._key_of()
        value = self.target_owner[key] if key is not None else getattr(self.target_owner, self.attr)
        return value[self.index] if self.index is not None else value

    def _set(self, value):
        key = self._key_of()
        if self.index is not None:
            seq = self.target_owner[key] if key is not None else getattr(self.target_owner, self.attr)
            seq[self.index] = value
        elif key is not None:
            self.target_owner[key] = value
        else:
            setattr(self.target_owner, self.attr, value)

    @property
    def turns(self):
        return self.kind in TURNING

    def use_view(self, screen_axis, view_rotation, per_pixel=None):
        """Aim a View or Depth command at a view (given by its rotation). Its
        axis becomes the view's, in its owner's own frame: across
        (`screen_axis` 0) or up (1) for View, or the line of sight for Depth.
        A Move then follows the mouse at `per_pixel` scene units a pixel."""
        if not self.ok or self.view_mode is None:
            return
        m = view_rotation.to_matrix()
        right, up, away = m.col[0], m.col[1], -m.col[2]
        obj, pb = self.obj, self.pb
        if self.kind == "MOVE":
            world = (right if screen_axis == 0 else up) if self.view_mode == "VIEW" else away
            if pb is not None:
                space = (obj.matrix_world @ pb.matrix @ pb.matrix_basis.inverted_safe()).to_3x3()
            elif obj.parent is not None:
                space = (obj.parent.matrix_world @ obj.matrix_parent_inverse).to_3x3()
            else:
                space = Matrix.Identity(3)
            local = space.inverted_safe() @ world
            self.axis = local.normalized() if local.length > 1e-12 else axis_vector("X")
            self.move_scale = local.length
            self.frame = Matrix.Identity(3)
            if per_pixel:
                self.per_pixel = per_pixel
        else:
            # As if the mouse rolled it: a drag across turns it about the
            # view's up, and a drag up turns it about the view's right, so its
            # front follows the mouse. Depth rolls it about the line of sight,
            # clockwise as you see it for a drag right or up.
            world = (up if screen_axis == 0 else -right) if self.view_mode == "VIEW" else away
            frame = world_matrix(obj, pb).to_3x3().normalized()
            local = frame.inverted_safe() @ world
            self.axis = local.normalized() if local.length > 1e-12 else axis_vector("X")

    def label(self):
        d = self.drag
        what = self.obj.name + (":" + self.pb.name if self.pb is not None else "") if self.ok else "?"
        if self.kind == "PROGRAM":
            spec = _COMMAND_KINDS.get(d.program)
            text = spec["summary"](d) if spec is not None and spec.get("summary") else d.program
            return text if not self.ok else "%s on %s" % (text, what)
        if self.view_mode and self.kind in TURNING:
            return {("MOVE", "VIEW"): "move %s in the view", ("MOVE", "DEPTH"): "move %s in depth",
                    ("ROTATE", "VIEW"): "turn %s with the view", ("ROTATE", "DEPTH"): "roll %s"}[
                (self.kind, self.view_mode)] % what
        i = dominant_axis(self.axis)
        axis = ("-" if self.axis[i] < 0.0 else "") + "XYZ"[i]
        if self.kind == "ROTATE":
            return "turn %s about %s" % (what, axis)
        if self.kind == "MOVE":
            return "move %s along %s" % (what, axis)
        if self.kind == "SCALE":
            return "scale %s%s" % (what, "" if self.scale_all else " on " + axis.lstrip("-"))
        if self.kind == "INPUT":
            if not self.input:
                return "an input"
            # sent elsewhere (add_redirect): say where
            return "%s of %s" % (self.input, self.obj.name) if self.ok and self.input != d.input else self.input
        return d.data_path or "a property"

    def value_at(self, amount, ctrl, base=None):
        """A value channel's value for `amount` from its start, or from
        `base` (what another command on the same value made of it; see
        apply). It is stepped when Ctrl is held, and kept within its
        limits."""
        d = self.drag
        if self.kind == "SCALE":
            return amount
        base = self.start if base is None else base
        if d.multiply:
            # a growth, as Scale's: values driven together keep their
            # proportions, and Ctrl steps the factor, not each value
            factor = math.exp(amount)
            if ctrl and d.step > 0.0:
                factor = max(round(factor / d.step) * d.step, 0.0)
            value = base * factor
        else:
            value = base + amount
            if ctrl and d.step > 0.0:
                value = round(value / d.step) * d.step
        low, high = self.limits
        value = min(max(value, low), high)
        return int(round(value)) if self.integer else value

    def restore(self):
        if not self.ok:
            return
        if self.dragging:
            try:
                self.spec["drag"]["restore"](bpy.context, self.state)
            except Exception:                 # a program's error must not stop the cancel
                errors.caught("a program's restore")
            redraw()
        elif self.kind == "ROTATE":
            write_rotation(self.owner, self.start)
        elif self.kind == "MOVE":
            self.owner.location = self.start
        elif self.kind == "SCALE":
            self.owner.scale = self.start
        else:
            self.write_value(self.start)

    def write_value(self, value):
        # written in the value's own kind: an integer property refuses a float,
        # and a boolean is on from 0.5 up
        if self.boolean:
            value = bool(value >= 0.5)
        elif self.integer:
            value = int(round(value))
        if self.kind == "PROGRAM":
            # the program's own way; it tells Blender what changed
            self.spec["write"](bpy.context, self.obj, self.drag, bool(value))
            redraw()
            return
        if self.kind == "INPUT":
            set_input_value(self.mod, self.ident, value)
        else:
            self._set(value)
        # a modifier input or a property written from Python does not tell
        # the depsgraph
        self.obj.update_tag()


def _hold_locked_rotation(ch):
    """Put an Euler rotation's locked channels back where they started,
    since a View turn crosses every axis."""
    owner = ch.owner
    if owner.rotation_mode in ("QUATERNION", "AXIS_ANGLE") or not any(owner.lock_rotation):
        return
    start = ch.start.to_euler(owner.rotation_mode, owner.rotation_euler)
    euler = owner.rotation_euler.copy()
    for i, locked in enumerate(owner.lock_rotation):
        if locked:
            euler[i] = start[i]
    owner.rotation_euler = euler


def input_value(mod, ident):
    """A Geometry Nodes modifier input's value. Since Blender 5.0 it is
    under the modifier's properties; before that it is an ID property of the
    modifier. Blender 4.2 and 4.5 have no `properties`, so no input could be
    read there until this read both ways."""
    inputs = getattr(getattr(mod, "properties", None), "inputs", None)
    if inputs is not None:
        return getattr(inputs, ident).value
    return mod[ident]


def set_input_value(mod, ident, value):
    inputs = getattr(getattr(mod, "properties", None), "inputs", None)
    if inputs is not None:
        getattr(inputs, ident).value = value
    else:
        mod[ident] = value


def follow_sign(project, pivot, point, axis, screen_axis, default=1.0):
    """+1 or -1: the sign of a turn about `axis` (world, through `pivot`)
    that moves `point` the way the mouse moves along `screen_axis` (0
    across, 1 up), by `project` (world to screen). Where that turn barely
    moves the point that way, it gives `default`: a curl seen from above
    moves a finger's tip across the screen, not up."""
    a = project(point)
    b = project(point + axis.cross(point - pivot) * 0.01)
    return _sign(a, b, screen_axis, default)


def move_sign(project, pivot, direction, screen_axis, default=1.0):
    """+1 or -1: the sign of a move along `direction` (world) that follows
    the mouse along `screen_axis`."""
    scale = max((direction.length, 1e-9))
    return _sign(project(pivot), project(pivot + direction / scale * 0.01), screen_axis, default)


def _sign(a, b, screen_axis, default):
    if a is None or b is None:
        return default
    d = Vector(b) - Vector(a)
    if d.length < 1e-9 or abs(d[screen_axis]) < AMBIGUOUS * d.length:
        return default
    return 1.0 if d[screen_axis] > 0.0 else -1.0


def lever_point(channel, anchor, grabbed):
    """A point a turn of the channel's target visibly moves: a bone's tail,
    a mesh's middle, else the region's middle, else the point grabbed."""
    obj, pb = channel.obj, channel.pb
    pivot = world_matrix(obj, pb).translation
    candidates = []
    if pb is not None:
        candidates.append(obj.matrix_world @ pb.tail)
    elif obj.type == "MESH" and max(obj.dimensions) > 1e-9:
        candidates.append(obj.matrix_world @ (sum((Vector(c) for c in obj.bound_box), Vector()) / 8.0))
    candidates += [p for p in (anchor, grabbed) if p is not None]
    size = max(max(obj.dimensions), 1e-6)
    for p in candidates:
        if (p - pivot).length > 0.05 * size:
            return p
    return pivot + world_matrix(obj, pb).to_3x3().normalized().col[2] * size


def sign_for(channel, screen_axis, project, anchor, grabbed):
    """The sign that makes a turning channel follow the mouse in the view the
    drag began in, or +1."""
    if not channel.turns or project is None or getattr(channel, "view_mode", None) \
            or not getattr(channel.drag, "follow", True):
        # a View or Depth command is aimed at the view already (use_view); one
        # not following the mouse goes the positive way
        return 1.0
    m = world_matrix(channel.obj, channel.pb)
    axis = (m.to_3x3().normalized() @ axis_of(channel)).normalized()
    pivot = m.translation.copy()
    if channel.kind == "MOVE":
        return move_sign(project, pivot, axis, screen_axis)
    return follow_sign(project, pivot, lever_point(channel, anchor, grabbed), axis, screen_axis)


def amount_for(channel, pixels, sign):
    """A channel's amount for a drag of `pixels` along its direction, with
    `sign` its follow-the-mouse sign. Invert flips it here, so a redo or a
    script, which have no view, invert too."""
    d = channel.drag
    per = _per_pixel(channel)
    if per is not None:
        return pixels * per * sign * (-1.0 if d.invert else 1.0)
    rate = d.turn_rate if channel.kind == "ROTATE" or getattr(channel, "turning", False) else d.rate
    return pixels * rate / 100.0 * sign * (-1.0 if d.invert else 1.0)


def follows_handle(channel):
    """Whether a channel follows the mouse along a 3D handle: a Move or a
    Rotate, or a program's drag (add_command_kind's `drag`), which moves by
    its motion."""
    return channel.kind in TURNING or getattr(channel, "dragging", False)


def _per_pixel(channel):
    """How much a pixel moves a command that follows the mouse, whatever its
    Speed, or None. That is scene units for a View or Depth Move, or, along
    a 3D handle (handle_per_pixel), scene units or radians for a Move, a
    Rotate or a program's drag."""
    handle = getattr(channel, "handle_per_pixel", None)
    if handle and follows_handle(channel):
        return handle
    per = getattr(channel, "per_pixel", None)
    return per if per and channel.kind == "MOVE" else None


# -- Nothing moved -------------------------------------------------------------------------
#
# Whether a drag shows. The constraints Kneady can read name what holds a
# control (overridden_by), but a rig can switch FK and IK in ways no rule
# reads: Auto-Rig Pro blends through helper bones and constraints at zero
# strength. So a drag also looks. The hovered mesh is sampled as the drag
# starts and again once it has gone a way, and if no point has moved, the
# drag says so. That costs two reads of the mesh per drag.

STILL_PIXELS = 30.0                # how far a drag goes before it looks
STILL_SAMPLES = 32


def surface_sample(obj, depsgraph):
    """A few of `obj`'s points as shown, in the world, spread over the mesh."""
    if obj is None or obj.type != "MESH":
        return None
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    n = len(me.vertices)
    step = max(n // STILL_SAMPLES, 1)
    pts = [ev.matrix_world @ me.vertices[i].co for i in range(0, n, step)]
    ev.to_mesh_clear()
    return pts


def moved_since(before, after):
    """How far the sampled points moved at most, or None if they cannot be
    compared (another number of points: the mesh's shape changed)."""
    if before is None or after is None or len(before) != len(after):
        return None
    return max(((a - b).length for a, b in zip(before, after)), default=0.0)


# -- Numeric values ------------------------------------------------------------------------
#
# Greg: "a numeric control popping up after hauling on Kneady controls. It
# would pop up the modified channel/s or properties so that you could see
# what's being modified and enter a number in instead of continuing to
# haul." Each channel shows what the drag made of it, in its own terms: a
# turn in degrees, a scale as a factor, an input or property as its value. A
# number typed for one works out the drag that gives it. Every command a
# direction drives moves by that one drag, so the others follow and keep
# their relation: a Taper's four Sides stay a taper.

UNITS = {"ROTATE": "\u00b0", "SCALE": "\u00d7"}


def display_value(channel, amount):
    """What a channel shows for `amount` (amount_for): degrees turned, the
    distance moved, the factor scaled, or the input's or property's value.
    A program's drag shows how far it went, in degrees for a turn."""
    if channel.kind == "ROTATE" or getattr(channel, "turning", False):
        return math.degrees(amount)
    if channel.kind in ("MOVE", "PROGRAM"):
        return amount
    if channel.kind == "SCALE":
        return math.exp(amount)
    return channel.value_at(amount, False)


def amount_from_display(channel, value):
    """The amount that makes a channel show `value`, or None where none can
    (a factor of 0 or less; a multiplied value of another sign)."""
    if channel.kind == "ROTATE" or getattr(channel, "turning", False):
        return math.radians(value)
    if channel.kind in ("MOVE", "PROGRAM"):
        return value
    if channel.kind == "SCALE":
        return math.log(value) if value > 0.0 else None
    if channel.drag.multiply:
        ratio = value / channel.start if channel.start else 0.0
        return math.log(ratio) if ratio > 0.0 else None
    return value - channel.start


def pixels_for(channel, amount, sign):
    """The drag, in pixels at an interface scale of 1, that gives `amount`
    (amount_for in reverse), or None for a command with no speed."""
    if amount is None:
        return None
    d = channel.drag
    per = _per_pixel(channel)
    rate = per * 100.0 if per is not None else d.turn_rate \
        if channel.kind == "ROTATE" or getattr(channel, "turning", False) else d.rate
    k = rate / 100.0 * sign * (-1.0 if d.invert else 1.0)
    return None if abs(k) < 1e-12 else amount / k


def value_key(channel):
    """What a modifier input or property command writes, so that two
    commands on one value (the same input on both directions of a button)
    write it once, together (apply)."""
    ch = channel
    if ch.kind == "INPUT":
        return (ch.obj.as_pointer(), "INPUT", ch.mod.name, ch.ident)
    owner = ch.target_owner
    return (ch.obj.as_pointer(), "PROPERTY",
            owner.as_pointer() if hasattr(owner, "as_pointer") else id(owner), ch.attr, ch.index)


def apply(channels, amounts, ctrl=False, keys=None):
    """Write every channel at its amount from where it started. Turns of one
    target combine into one rotation: two axes at once become a single
    tilt, so no roll comes of them. Moves and scales combine the same way,
    and so do commands on one value: each adds or multiplies onto what the
    one before made of it, in order, so a value both directions drive
    follows both. Greg put the four Sides on left / right and up / down, to
    make it "easy to scale uniformly with that button either way". Each
    command used to write the value from its start, so the direction not
    dragged put it back. A program's drag writes its own way, told `keys`,
    the modifier keys held."""
    turns, moves, scales, values, programs = {}, {}, {}, {}, []
    for ch, amount in zip(channels, amounts):
        if not ch.ok:
            continue
        d = ch.drag
        if getattr(ch, "dragging", False):
            programs.append((ch, amount))
        elif ch.kind == "ROTATE":
            if ctrl and d.turn_step > 0.0:
                amount = round(amount / d.turn_step) * d.turn_step
            entry = turns.setdefault(ch.key, [ch, Vector()])
            entry[1] += axis_of(ch) * amount
        elif ch.kind == "MOVE":
            if ctrl and d.step > 0.0:
                amount = round(amount / d.step) * d.step
            entry = moves.setdefault(ch.key, [ch, Vector()])
            entry[1] += axis_of(ch) * amount * getattr(ch, "move_scale", 1.0)
        elif ch.kind == "SCALE":
            entry = scales.setdefault(ch.key, [ch, Vector((0.0, 0.0, 0.0))])
            if scales_all(ch):
                entry[1] += Vector((amount, amount, amount))
            else:
                entry[1][dominant_axis(axis_of(ch))] += amount
        else:
            key = value_key(ch)
            was = values.get(key)
            values[key] = (ch, ch.value_at(amount, ctrl, None if was is None else was[1]))
    for ch, value in values.values():
        ch.write_value(value)
    for ch, amount in programs:
        try:
            ch.spec["drag"]["apply"](bpy.context, ch.state, amount, ctrl, set(keys or ()))
        except Exception:                     # a program's error must not stop the drag
            errors.caught("a program's drag")
    if programs:
        redraw()
    for ch, v in turns.values():
        angle = v.length
        swing = Matrix.Rotation(angle, 3, v / angle) if angle > 1e-12 else Matrix.Identity(3)
        write_rotation(ch.owner, ch.start @ swing)
        _hold_locked_rotation(ch)
    for ch, v in moves.values():
        location = ch.start + ch.frame @ v
        # Blender's transform locks hold, as its tools hold them: a View move
        # crosses every axis, and leaves a locked one where it was
        for i, locked in enumerate(ch.owner.lock_location):
            if locked:
                location[i] = ch.start[i]
        ch.owner.location = location
    for ch, v in scales.values():
        step = ch.drag.step if ctrl else 0.0
        locked = tuple(ch.owner.lock_scale)
        out = []
        for i in range(3):
            if locked[i]:
                out.append(ch.start[i])             # All scales only the free axes
                continue
            s = ch.start[i] * math.exp(v[i])
            out.append(round(s / step) * step if step > 0.0 and v[i] != 0.0 else s)
        ch.owner.scale = out


# -- Auto Keying ---------------------------------------------------------------------------
#
# When Auto Keying is on, a drag keys what it changed, by the settings
# Blender's own transforms follow: the scene's Auto Keying mode, Only Active
# Keying Set, Cycle-Aware Keying and keyframe type, and the preferences' Only
# Insert Available, Only Insert Needed and Visual Keying. So a pose made with
# Kneady is kept as one made with G or R would be. Blender 5.2's factory
# settings key only what is animated already: its own G on an object with no
# animation keys nothing and reports it, and so does this.

ROTATION_PATHS = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}


def _key_targets(channel):
    """(owner, data path, index, group) for each property a channel writes."""
    ch = channel
    if getattr(ch, "dragging", False):
        # a program's drag: what it says it writes (its `drag`'s key_targets,
        # fn(state) -> the same tuples), if anything
        fn = ch.spec["drag"].get("key_targets")
        return list(fn(ch.state)) if fn is not None else []
    group = ch.pb.name if ch.pb is not None else ""
    if ch.kind == "ROTATE":
        return [(ch.owner, ROTATION_PATHS.get(ch.owner.rotation_mode, "rotation_euler"), -1, group)]
    if ch.kind == "MOVE":
        return [(ch.owner, "location", -1, group)]
    if ch.kind == "SCALE":
        return [(ch.owner, "scale", -1, group)]
    if ch.kind == "INPUT":
        inputs = getattr(getattr(ch.mod, "properties", None), "inputs", None)
        if inputs is not None:
            return [(getattr(inputs, ch.ident), "value", -1, "")]
        return [(ch.obj, 'modifiers["%s"]["%s"]' % (ch.mod.name, ch.ident), -1, "")]
    if ch.kind == "PROPERTY":
        return [(ch.target_owner, ch.attr, -1 if ch.index is None else ch.index, "")]
    return []


def _full_path(owner, path):
    try:
        return owner.path_from_id(path)
    except (ValueError, TypeError):
        return path


def auto_key(context, channels):
    """Key what `channels` wrote, if Auto Keying is on. Returns (keyed, missed):
    how many properties were keyed, and how many could not be by the
    settings (Only Insert Available on a property not yet animated, Replace
    with no key to replace)."""
    scene = context.scene
    ts = scene.tool_settings
    if not ts.use_keyframe_insert_auto:
        return 0, 0
    prefs = context.preferences.edit
    options = set()
    if getattr(prefs, "use_keyframe_insert_available", False):
        options.add("INSERTKEY_AVAILABLE")
    if getattr(prefs, "use_auto_keyframe_insert_needed", False):
        options.add("INSERTKEY_NEEDED")
    if getattr(prefs, "use_visual_keying", False):
        options.add("INSERTKEY_VISUAL")
    if ts.auto_keying_mode == "REPLACE_KEYS":
        options.add("INSERTKEY_REPLACE")
    if getattr(ts, "use_keyframe_cycle_aware", False):
        options.add("INSERTKEY_CYCLE_AWARE")
    only = None
    keying_set = scene.keying_sets.active if ts.use_keyframe_insert_keyingset else None
    if keying_set is not None:
        only = {(p.id, p.data_path) for p in keying_set.paths}
    seen, keyed, missed = set(), 0, 0
    for ch in channels:
        if not getattr(ch, "ok", False):
            continue
        for owner, path, index, group in _key_targets(ch):
            key = (owner.as_pointer(), path, index)
            if key in seen:
                continue
            seen.add(key)
            if only is not None and (owner.id_data, _full_path(owner, path)) not in only:
                continue
            try:
                done = owner.keyframe_insert(path, index=index, group=group, options=options,
                                             keytype=ts.keyframe_type)
            except (RuntimeError, TypeError):
                done = False
            if done:
                keyed += 1
            else:
                missed += 1
    return keyed, missed


def lock_axis(pixels, scale=1.0):
    """For Drags Prefer Single Direction: the direction a drag set off in, 0
    across or 1 up, once it has gone far enough, else None."""
    if math.hypot(pixels[0], pixels[1]) < LOCK_PIXELS * scale:
        return None
    return 0 if abs(pixels[0]) >= abs(pixels[1]) else 1


def accumulate(pixels, lock, delta, travel, single, scale=1.0):
    """A drag's pixels, [across, up], and its live direction after a move of
    `delta` (`travel` is how far it has gone from where it was pressed).
    With Drags Prefer Single Direction, it sets off in both directions until
    lock_axis decides, then drops the other direction's jitter. After that
    only the live direction moves, and the other keeps what it did. Alt
    switches between them (switched)."""
    pixels = list(pixels)
    if not single:
        return [pixels[0] + delta[0], pixels[1] + delta[1]], lock
    if lock is None:
        pixels = [pixels[0] + delta[0], pixels[1] + delta[1]]
        lock = lock_axis(travel, scale)
        if lock is not None:
            pixels[1 - lock] = 0.0
        return pixels, lock
    pixels[lock] += delta[lock]
    return pixels, lock


def switched(lock, usable):
    """Alt during a single-direction drag switches to the other direction,
    once the drag has set off and if the other direction drives something.
    So deformations stack in one drag. Greg: "pressing alt keeps the
    previous transform and enables dragging left right to be the desired
    deformation"."""
    if lock is None or not usable[1 - lock]:
        return lock
    return 1 - lock


# -- Toggles -------------------------------------------------------------------------------
#
# Greg: "Boolean Buttons that when clicked simply stay highlighted for boolean
# properties." A toggle button (KNEADY_PG_button.action) switches its
# commands (modifier inputs or properties) on or off with a click. A boolean
# becomes True or False, and a number 1 or 0 (a rig's IK / FK switch is a
# number from 0 to 1); Invert switches the other way round. The button is lit
# while its first command that can run is on, read from the object hovered,
# so on a region many objects share it shows each one's own state.

def switch_commands(button):
    """A toggle's commands: its own, then any added."""
    return [button.switch] + list(button.switch.more)


def button_commands(button):
    """Every command a button runs: a toggle's, else those of its directions
    that are on, plus what its click switches, if it has one (has_click)."""
    if button.action == "TOGGLE":
        return switch_commands(button)
    drags = [c for d in (button.across, button.up) if d.enabled for c in [d] + list(d.more)]
    return drags + (switch_commands(button) if has_click(button) else [])


def drag_commands(button):
    """A drag button's commands, both directions, each with any added."""
    if button is None or button.action != "DRAG":
        return []
    return [c for d in (button.across, button.up) if d.enabled for c in [d] + list(d.more)]


def moves_with(obj, region, index, keys):
    """The other shown buttons whose commands a drag from button `index`
    also moves with the modifier `keys` held, as a frozenset of indices.
    Its program's drag says which (add_command_kind's `drag` "also":
    fn(command, other, keys) -> bool), so they light up with it. Greg agreed
    to "With Alt held over a Side box, light its partner box as well; with
    Alt+Shift, light all four"."""
    if index is None or not keys or region is None:
        return frozenset()
    used = buttons_of(region)
    if not 0 <= index < len(used):
        return frozenset()
    mine = [(c, drag_kind(c)) for c in drag_commands(used[index])]
    mine = [(c, d) for c, d in mine if d and d.get("also")]
    if not mine:
        return frozenset()
    out = set()
    for j in shown_buttons(region, obj):
        if j == index:
            continue
        others = drag_commands(used[j])
        for c, d in mine:
            try:
                if any(drag_kind(o) is d and d["also"](c, o, set(keys)) for o in others):
                    out.add(j)
                    break
            except Exception:                 # a program's error must not stop the drawing
                errors.caught("a program's also")
    return frozenset(out)


THEME_AXES = {"AXIS_X": "axis_x", "AXIS_Y": "axis_y", "AXIS_Z": "axis_z"}
# A thin dark edge around every 3D handle's lines: this many pixels each side
# at Blender's normal interface size, and this dark. Greg: "Contrast against
# wireframe is a good idea".
HALO = 1.0
HALO_ALPHA = 0.6


def handle_halo(context=None):
    """The halo's width each side of a handle's lines, in pixels, or 0 with
    Halo off (Scene.kneady_handle_halo)."""
    scene = getattr(context or bpy.context, "scene", None)
    return HALO * ui_scale(context) if getattr(scene, "kneady_handle_halo", False) else 0.0


# How much of a theme axis color shows at rest. Blender's transform gizmo draws
# its axes at 0.6 of their color, and whole under the mouse
# (transform_gizmo_3d.cc, gizmo_get_axis_color: alpha 0.6, alpha_hi 1.0).
# Drawn whole, the handles looked lighter than Blender's own. Greg: "I set the
# handles to theme defaults but they don't look like the default handles. They
# look lighter colored".
THEME_ALPHA = 0.6


def themed(button):
    """Whether a handle's color is one of the theme's axis colors
    (handle_color_from). Those are drawn as Blender's own gizmos draw them:
    the exact color, not a shade brighter, at THEME_ALPHA at rest
    (theme_alpha)."""
    return bool(button.handle_use_color and button.handle_color_from in THEME_AXES)


def theme_alpha(button, under=False):
    """What a handle colored from the theme is drawn at, as Blender's own
    gizmos draw those colors: THEME_ALPHA at rest, and fully under the
    mouse. Any other color is drawn at 1."""
    return THEME_ALPHA if themed(button) and not under else 1.0


def handle_color(button, otherwise):
    """A 3D handle's color: its own (handle_use_color), which is the one set
    or an axis color of Blender's theme (handle_color_from), else
    `otherwise`."""
    if not button.handle_use_color:
        return otherwise
    name = THEME_AXES.get(button.handle_color_from)
    if name is not None:
        try:
            return tuple(getattr(bpy.context.preferences.themes[0].user_interface, name))[:3]
        except (AttributeError, IndexError):
            pass
    return tuple(button.handle_color)


def has_click(button):
    """Whether a click on the button switches something: a toggle, or a drag
    button with Click Switches on (KNEADY_PG_button.click_on) - lit while on."""
    return button.action == "TOGGLE" or (button.action == "DRAG" and getattr(button, "click_on", False))


def switch_click(context, button, obj, region, on=None, point=None):
    """Switch what a click on `button` switches - on, off, or (None) the other
    way from now - on `obj`. Returns whether anything was switched."""
    channels = switch_channels(button, obj, region, point)
    if not any(ch.ok for ch in channels):
        return False
    state = switch_state(channels)
    if on is None:
        if state and sets_value(channels):
            return False                   # one of a choice, chosen already: nothing to turn it off to
        on = not state
    elif state == on:
        return False
    return switch_button(context, button, obj, region, channels, on)


def switch_channels(button, obj, region=None, point=None):
    """A toggle's commands resolved for `obj`, the object hovered (`point`
    where it was clicked, for a group's object)."""
    return [Channel(c, obj, region, point, switch=True) for c in switch_commands(button)[:props.MAX_COMMANDS]]


def channel_on(channel):
    """Whether a toggle's command reads on: its value is 0.5 or more, or
    under 0.5 with Invert. A command that sets a value of its own reads on
    while the property holds that value."""
    if getattr(channel.drag, "sets_value", False):
        return abs(float(channel.start) - channel.drag.on_value) < 1e-4
    return (channel.start >= 0.5) != channel.drag.invert


def switch_state(channels):
    """Whether a toggle is on - by its first command that can run - or None
    if none can."""
    first = next((ch for ch in channels if ch.ok), None)
    return None if first is None else channel_on(first)


def sets_value(channels):
    """Whether a toggle sets a value of its own (one of a choice): by its first
    command that can run."""
    first = next((ch for ch in channels if ch.ok), None)
    return bool(first is not None and getattr(first.drag, "sets_value", False))


def switch_button(context, button, obj, region, channels, on):
    """Switch a toggle: a program's own way, if one takes it (add_switcher;
    for example, keeping the limb where it is as an IK / FK switch flips),
    else by switch(). A toggle that sets a value of its own is never
    switched off, since another button of its choice sets another value."""
    if not on and sets_value(channels):
        return False
    for fn in list(_SWITCHERS):
        if fn(context, button, obj, region, channels, on):
            return True
    return switch(channels, on) > 0


def switch(channels, on):
    """Switch a toggle's commands on or off together. Returns how many were
    written."""
    n = 0
    for ch in channels:
        if ch.ok:
            if getattr(ch.drag, "sets_value", False):
                if not on:
                    continue               # one of a choice: another button sets another value
                ch.write_value(ch.drag.on_value)
            else:
                ch.write_value(1.0 if on != ch.drag.invert else 0.0)
            n += 1
    return n


# -- Copy and paste ------------------------------------------------------------------------
#
# A region's buttons, or one button, copied and pasted onto another, even in
# another file, through the system clipboard as text. Greg asked for this for
# a control group's settings: "copy and paste settings between each other".
# What makes a region itself stays as it is where it is pasted: its name,
# faces, look and id. Targets are written by name, and pasted onto whatever
# has that name there.

# dragged is read from the target. ui_open, command_open, menu_open, tree_open
# and tip_open record where the panel is left open, not a setting, so a paste
# keeps the destination's
SKIP_DATA = {"rna_type", "dragged", "ui_open", "command_open", "menu_open", "tree_open", "tip_open"}
REGION_OWN = {"name", "id", "whole", "attribute", "value", "show_through", "color", "opacity", "version"}
# What a button pasted over keeps of its own: where its panel is left open,
# and where the button sits among the others (its id, the menu it is in, and
# the button selected in its own menu). Those are not settings to carry.
BUTTON_OWN = {"ui_open", "uid", "menu_parent", "menu_index"}
# A button's commands, copied alone onto another. Greg: "it would be very
# advantageous to copy the set of commands from one button to another". That
# is whether it drags or toggles, what each direction and a click drive, and
# an operator a click runs - not its name, look, place or menu. The tip's rows
# go with them, since they word what the commands do (a drag named Curl); the
# tip's message, what the button is for, stays.
COMMAND_DATA = ("action", "single", "across", "up", "switch", "click_on", "run_operator", "run_operator_args",
                "tip_rows")
_ID_DATA = {"Object": "objects", "Image": "images"}
_CLIPBOARD = {"text": None}


def to_data(group):
    """A Kneady property group as plain data (numbers, strings, lists,
    dicts): every property its class has, including any a program added. An
    object or image is stored by name."""
    out = {}
    for prop in group.bl_rna.properties:
        name = prop.identifier
        if name in SKIP_DATA:
            continue
        value = getattr(group, name)
        if prop.type == "POINTER":
            if isinstance(value, bpy.types.PropertyGroup):
                out[name] = to_data(value)
            else:
                out[name] = value.name if value is not None else None
        elif prop.type == "COLLECTION":
            out[name] = [to_data(item) for item in value]
        elif prop.is_readonly:
            continue
        elif prop.type == "ENUM" and prop.is_enum_flag:
            out[name] = sorted(value)
        elif not isinstance(value, (str, bool, int, float)):
            out[name] = list(value)
        else:
            out[name] = value
    return out


def from_data(group, data, skip=()):
    """Write plain data (to_data) back onto a property group, except the
    names in `skip`. Anything the group has no property for, or will not
    take, is left out."""
    for prop in group.bl_rna.properties:
        name = prop.identifier
        if name in SKIP_DATA or name in skip or name not in data:
            continue
        value = data[name]
        if name == "handle_shape" and legacy_shape(group, value):
            continue                      # copied while lengths were shapes: an Arrow of that Length
        current = getattr(group, name)
        if prop.type == "POINTER":
            if isinstance(current, bpy.types.PropertyGroup):
                if isinstance(value, dict):
                    from_data(current, value)
                continue
            where = _ID_DATA.get(getattr(prop.fixed_type, "identifier", ""))
            found = getattr(bpy.data, where).get(value) if where and value else None
            try:
                setattr(group, name, found)
            except (TypeError, AttributeError, ValueError):
                pass
        elif prop.type == "COLLECTION":
            if isinstance(value, list):
                current.clear()
                for item in value:
                    from_data(current.add(), item)
        elif not prop.is_readonly:
            try:
                setattr(group, name, set(value) if prop.type == "ENUM" and prop.is_enum_flag else value)
            except (TypeError, AttributeError, ValueError):
                pass


def copy_data(context, kind, data):
    """Put `data` of `kind` ("region" or "button") on the clipboard - the
    system's, as text, and this session's."""
    import json
    text = json.dumps({"kneady": kind, "data_version": DATA_VERSION, "data": data})
    _CLIPBOARD["text"] = text
    try:
        context.window_manager.clipboard = text
    except (AttributeError, RuntimeError, TypeError):
        pass


def copied(context, kind):
    """What was copied of `kind`: the system clipboard's if it holds Kneady's,
    else this session's last copy; None if neither does."""
    import json
    try:
        system = context.window_manager.clipboard
    except (AttributeError, RuntimeError):
        system = ""
    for text in (system, _CLIPBOARD["text"]):
        if not text or not text.lstrip().startswith('{"kneady"'):
            continue
        try:
            found = json.loads(text)
        except ValueError:
            continue
        if isinstance(found, dict) and found.get("kneady") == kind and isinstance(found.get("data"), dict):
            return found
    return None


def paste_region(region, found):
    """Paste copied buttons (copied, "region") onto `region`: its buttons,
    their count and arrangement. The region keeps its name, faces, look and
    id. Returns why it could not, or None."""
    if found.get("data_version", 0) > DATA_VERSION:
        return "Copied from a newer Kneady: update Kneady to paste it"
    from_data(region, found["data"], skip=REGION_OWN)
    return None


def paste_button(button, found):
    """Paste a copied button (copied, "button") onto `button`. It keeps what
    BUTTON_OWN lists: whether its panel is open, and where it sits among the
    others. Returns why it could not, or None."""
    if found.get("data_version", 0) > DATA_VERSION:
        return "Copied from a newer Kneady: update Kneady to paste it"
    from_data(button, found["data"], skip=BUTTON_OWN)
    return None


def commands_data(button):
    """A button's commands as plain data (COMMAND_DATA), for "commands" on
    the clipboard."""
    data = to_data(button)
    return {name: data[name] for name in COMMAND_DATA if name in data}


def paste_commands(button, found):
    """Paste copied commands (copied, "commands") onto `button`. What it
    drives changes; its name, look, place and menu are kept. Returns why it
    could not, or None."""
    if found.get("data_version", 0) > DATA_VERSION:
        return "Copied from a newer Kneady: update Kneady to paste it"
    from_data(button, {k: v for k, v in found["data"].items() if k in COMMAND_DATA})
    return None
