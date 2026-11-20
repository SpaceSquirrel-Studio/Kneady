"""Buttons placed in 3D. Greg: "Buttons all start at the object center of
the item, each button has an x,y,z offset channel. This would allow buttons
to be placed at each corner of the base of a finger for instance. As the
user moves around the buttons maintain their location in 3D space. When
there's overlaps closer in 3D space has dominance. Each button does face
screen just from specific 3D location."

Each button is either static - in the region's row, column, grid or circle -
or placed in 3D (`placed`), so one region can mix the two. The row arranges
only the buttons left in it.

A placed button's position (`place`) is a point in the region's box: -1 to
1 across it on each axis, 0 at its middle. The box is in the frame of the
bone the region's first button turns, or of the object when it turns none.
If that bone is a control that deforms none of the region, the deform bone
weighting the region most is used instead (riding_bone). So the button
rides its bone as the character is posed, and one set of positions fits
every region it is copied to, a thick thumb and a thin little finger alike.

A button facing away from the view is hidden or shown faint, as the
region's Behind setting says (Hide Behind, Ghost Behind or Show Behind).
Where two overlap, the nearer is drawn over the other, the other is faint,
and the nearer takes the click (Overlap, below). The circles still face the
screen.

Kneady draws and hit-tests them like any buttons, through core.add_layout.
A program that places buttons by hand fills PLACING while it does: the
object and region, the button being dragged, and where it would land."""

import math

import numpy as np
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Matrix, Vector  # type: ignore

from . import core

FACING = 0.05                      # a button whose surface faces away from the view by more than this hides
_BOX = {}                          # (object name, region id) -> (key, (center, half))
# Filled by a program while it places a region's buttons by hand:
#   obj    - the object's name
#   rid    - the region's id
#   drag   - the index of the button being dragged, or None
#   target - where it would land, (world point, normal, kind), or None
#   mouse  - the mouse, in region pixels
PLACING = {}
# Layouts that take over a region while they apply, such as an open menu's
# ring: fn(context, obj, region, editing, dragged) -> what layout() returns,
# or None. `editing` is true while the region's buttons are placed by hand,
# and `dragged` is the button being dragged
OVER = []


# -- Where a button is ------------------------------------------------------------------

def region_bone(region):
    """(rig, pose bone) the region's first drag button turns or moves, else
    (None, None)."""
    index = core.first_drag_button(region)
    button = core.button_of(region, index if index is not None else 0)
    if button is None:
        return None, None
    for drag in (button.up, button.across):
        rig = drag.target
        if drag.enabled and rig is not None and rig.type == "ARMATURE" and rig.pose is not None \
                and drag.bone in rig.pose.bones:
            return rig, rig.pose.bones[drag.bone]
    return None, None


_RIDES = {}                        # (object name, region id) -> (key, deform bone name or "")


def _deform_rig(obj):
    """The armature that `obj`'s first shown Armature modifier deforms it
    by, or None."""
    for m in getattr(obj, "modifiers", ()):
        if m.type == "ARMATURE" and m.show_viewport and m.object is not None and m.object.type == "ARMATURE":
            return m.object
    return None


def _region_weights(obj, region):
    """{vertex group index: summed weight} over the vertices of the region's
    faces on the mesh as it is stored."""
    mesh = obj.data
    tags = core.region_tags(core.regions_of(obj), mesh)
    mine = tags == region.id if not region.whole else tags == 0
    if not mine.any():
        return {}
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    corners = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", corners)
    picked = np.zeros(len(mesh.loops), dtype=bool)
    for s, t in zip(starts[mine], totals[mine]):
        picked[s:s + t] = True
    out = {}
    verts = mesh.vertices
    for i in np.unique(corners[picked]):
        for g in verts[int(i)].groups:
            out[g.group] = out.get(g.group, 0.0) + g.weight
    return out


def riding_bone(obj, region):
    """(rig, pose bone) that a region's placed buttons ride. Usually that is
    the bone its first drag button turns or moves (region_bone). The
    exception is a bone that moves none of the region's faces while the
    item is skinned to its rig: a rig's control, which moves its deform
    bones, which move the mesh. Then it is the deform bone weighting the
    region's faces most.

    Why: Rigify's FK forearm stays still while the arm is in IK, and a
    button placed on the forearm rode it there, 3 to 4 cm off a 5 cm forearm
    once the IK hand moved. Riding the deform bone, it stays on the surface
    whichever bone moves the arm. A bone that deforms the region itself
    (Digit's, a simple rig's) is ridden as before, so placements made on it
    keep their meaning."""
    rig, pb = region_bone(region)
    if pb is None or obj is None or obj.type != "MESH" or _deform_rig(obj) is not rig:
        return rig, pb
    # worked out again when the mesh, the bone or the tagged faces change.
    # To keep it cheap, the tags are checked at most once a frame
    # (core.frame_count)
    mesh, frame = obj.data, core.frame_count()
    key = (mesh.as_pointer(), len(mesh.vertices), len(mesh.polygons), pb.name)
    cached = _RIDES.get((obj.name, region.id))
    if cached is not None and cached[0] == key and cached[3] != frame and cached[2] == _tag_print(obj):
        cached = _RIDES[(obj.name, region.id)] = cached[:3] + (frame,)
    if cached is None or cached[0] != key or cached[3] != frame:
        weights = _region_weights(obj, region)
        names = {g.index: g.name for g in obj.vertex_groups}
        best = ""
        if not any(w > 0.0 and names.get(i) == pb.name for i, w in weights.items()):
            bones = rig.data.bones
            ranked = sorted(((w, names[i]) for i, w in weights.items()
                             if w > 0.0 and i in names and names[i] in bones and bones[names[i]].use_deform),
                            reverse=True)
            best = ranked[0][1] if ranked else ""
        cached = _RIDES[(obj.name, region.id)] = (key, best, _tag_print(obj), frame)
    if cached[1] and cached[1] in rig.pose.bones:
        return rig, rig.pose.bones[cached[1]]
    return rig, pb


def _tag_print(obj):
    """The faces tagged by hand on `obj`'s mesh, hashed to one number, since
    retagging them can change the bone ridden."""
    tags = core.face_tags(obj.data)
    return hash(tags.tobytes()) if tags is not None else 0


def frame_of(obj, region, button=None):
    """The frame a region's placed buttons ride, in the world: its bone's as
    posed (riding_bone), else its object's. For a `button` at an anchor (its
    `anchor` set), the anchor's own frame, at the anchor's point."""
    if button is not None and button.anchor:
        found = core.anchor_of(obj, region, button.anchor)
        if found is not None:
            return Matrix.Translation(found["point"]) @ found["frame"].to_4x4()
    rig, pb = riding_bone(obj, region)
    if pb is not None:
        return rig.matrix_world @ pb.matrix
    return obj.matrix_world.copy()


def region_box(obj, region, depsgraph, frame):
    """The region's box in `frame`: (center, half size), from its faces as
    shown - posed, after modifiers. None if it shows no faces. Cached until
    the faces or the frame change."""
    geometry = core.region_geometry(obj, depsgraph).get(region.id)
    if geometry is None:
        return None
    to_frame = frame.inverted_safe() @ obj.matrix_world
    key = (id(geometry), len(geometry[0]), tuple(round(v, 6) for row in to_frame for v in row))
    cached = _BOX.get((obj.name, region.id))
    if cached is not None and cached[0] == key:
        return cached[1]
    m = np.array(to_frame, dtype=np.float64)
    pts = np.asarray(geometry[0], dtype=np.float64) @ m[:3, :3].T + m[:3, 3]
    lo, hi = pts.min(0), pts.max(0)
    box = Vector(((lo + hi) * 0.5).tolist()), Vector(np.maximum((hi - lo) * 0.5, 1e-6).tolist())
    _BOX[(obj.name, region.id)] = (key, box)
    return box


def forget(name=None):
    if name is None:
        _BOX.clear()
        _RIDES.clear()
    else:
        for cache in (_BOX, _RIDES):
            for key in [k for k in cache if k[0] == name]:
                cache.pop(key, None)


def point_in_box(obj, region, place, normal, depsgraph):
    """(world point, world normal or None) for a position in the region's box."""
    frame = frame_of(obj, region)
    box = region_box(obj, region, depsgraph, frame)
    if box is None:
        return None
    center, half = box
    at = Vector(place)
    local = center + Vector((at.x * half.x, at.y * half.y, at.z * half.z))
    n = Vector(normal)
    out = None
    if n.length > 1e-9:
        out = (frame.to_3x3().inverted_safe().transposed() @ n).normalized()
    return frame @ local, out


def button_point(obj, region, button, depsgraph):
    """(world point, world normal or None) where a placed button is, or None.
    A button at an anchor (core.anchor_of) is there. On an object without
    that anchor it is None, so the button isn't shown where it would do
    nothing. Any other button is on its region's surface."""
    if button.anchor:
        found = core.anchor_of(obj, region, button.anchor)
        if found is None:
            return None
        normal = found.get("normal")
        return Vector(found["point"]), (Vector(normal).normalized() if normal is not None
                                        and Vector(normal).length > 1e-9 else None)
    return point_in_box(obj, region, button.place, button.place_normal, depsgraph)


def back_point(obj, region, button, depsgraph):
    """Where a menu's own button is while its menu is open, when it is
    placed for the menu (back_placed), or None."""
    return point_in_box(obj, region, button.back_place, button.back_normal, depsgraph)


def back_circle(context, obj, region, button):
    """(screen point, faint) of a menu's button placed for its open menu, or
    None. Behind the item it is faint (unless the region's Behind is No
    Hide/Ghost) but never hidden, because it is the way back out."""
    found = back_point(obj, region, button, context.evaluated_depsgraph_get())
    if found is None:
        return None
    view, rv3d = context.region, context.region_data
    world, normal = found
    p = view3d_utils.location_3d_to_region_2d(view, rv3d, world)
    if p is None:
        return None
    faint = False
    if region.behind != "NONE" and normal is not None and rv3d is not None:
        faint = normal.dot(view3d_utils.region_2d_to_vector_3d(view, rv3d, p)) > FACING
    return Vector(p), faint


def editing(obj, region):
    """Whether a program is placing this region's buttons by hand (PLACING)."""
    return PLACING.get("obj") == obj.name and PLACING.get("rid") == region.id


# A 3D handle behind the item (Greg: "Let's have the ghost behind option
# available for handles"). Unlike a button, a handle is not judged by which
# way the surface faces where it sits, because a handle often sits inside
# the item - a finger's at its knuckle, in the palm. It is judged by whether
# anything is in front of it, by a ray from the view. Each handle Ghosts,
# Hides or Shows behind (handle_behind), or does as its region's Behind says.
HANDLE_BEHIND = {"NONE": "SHOW", "HIDE": "HIDE", "GHOST": "GHOST"}


def handle_behind(region, button):
    """What a 3D handle does where something is in front of it: SHOW, GHOST
    or HIDE - its own, or its region's Behind."""
    own = getattr(button, "handle_behind", "REGION")
    return HANDLE_BEHIND.get(region.behind, "SHOW") if own == "REGION" else own


def occluded(context, world, depsgraph):
    """Whether anything in the scene is in front of `world`, seen from the
    view - a ray from the eye stopping short of it."""
    view, rv3d = context.region, context.region_data
    p = view3d_utils.location_3d_to_region_2d(view, rv3d, world)
    if p is None:
        return False
    origin = view3d_utils.region_2d_to_origin_3d(view, rv3d, p)
    toward = world - origin
    far = toward.length
    if far < 1e-9:
        return False
    # a point on the surface is not behind it: stop a hair short
    hit = core.ray(context, origin, toward / far, distance=far * (1.0 - 1e-3) - 1e-5, depsgraph=depsgraph)
    return bool(hit[0])


def placed_circles(context, obj, region, indices, editing_now):
    """Placed buttons `indices` on screen, back to front, as [(index,
    center)], and the set of those faded. A button facing away is hidden or
    faded, as the region's Behind says, and only ever faded while the region
    is being placed. A 3D handle is left to handles_for, which ghosts or
    hides it by whether anything is in front of its head (handle_behind)."""
    used = core.buttons_of(region)
    view, rv3d = context.region, context.region_data
    depsgraph = context.evaluated_depsgraph_get()
    out, faded = [], set()
    for i in indices:
        found = button_point(obj, region, used[i], depsgraph)
        if found is None:
            continue
        world, normal = found
        p = view3d_utils.location_3d_to_region_2d(view, rv3d, world)
        if p is None:
            continue
        if is_handle(used[i]):
            # a 3D handle: behind the item by its head, not its place
            # (handles_for, handle_behind)
            out.append(((rv3d.view_matrix @ world).z if rv3d is not None else 0.0, i, Vector(p)))
            continue
        behind = region.behind
        if behind != "NONE" and normal is not None and rv3d is not None:
            ray = view3d_utils.region_2d_to_vector_3d(view, rv3d, p)
            if normal.dot(ray) > FACING:
                if behind == "HIDE" and not editing_now:
                    continue
                faded.add(i)
        out.append(((rv3d.view_matrix @ world).z if rv3d is not None else 0.0, i, Vector(p)))
    out.sort(key=lambda item: item[0])          # the farthest first: the nearest drawn last, found first
    return [(i, p) for _depth, i, p in out], faded


def dragged_circle(view, rv3d):
    """(index, screen point) of the button a program placing buttons is
    dragging (PLACING), drawn on top: where it would land, else at the
    mouse."""
    target = PLACING.get("target")
    p = view3d_utils.location_3d_to_region_2d(view, rv3d, target[0]) if target is not None else None
    return PLACING["drag"], Vector(p) if p is not None else PLACING.get("mouse", Vector())


def layout(context, obj, region):
    """Kneady's layout for a region's placed buttons (core.add_layout). Each
    shown placed button's circle is where its point is on screen, back to
    front. Those facing away are hidden or faded (placed_circles), those
    another button covers are faded (covered), and the one being dragged is
    where it would land. None if no button is placed. An open menu lays out
    its own buttons (OVER)."""
    used = core.buttons_of(region)
    editing_now = editing(obj, region)
    dragged = PLACING.get("drag") if editing_now else None
    for fn in OVER:
        got = fn(context, obj, region, editing_now, dragged)
        if got is not None:
            return got
    owned = [i for i in core.shown_buttons(region, obj) if used[i].placed or i == dragged]
    if not owned:
        return None
    view, rv3d = context.region, context.region_data
    if view is None or rv3d is None:
        return owned, [], set()
    circles, faded = placed_circles(context, obj, region, [i for i in owned if i != dragged], editing_now)
    handles = {} if editing_now else handles_for(context, obj, region, circles)
    if dragged is not None:
        circles.append(dragged_circle(view, rv3d))
    if circles:
        # a button with another in front of it is faint (Overlap, below). A
        # 3D handle neither fades another nor is faded, since its shaft
        # reaches past them
        row = core._arranged_layout(context, obj, region, set(owned))
        flat = [(i, c) for i, c in circles if i not in handles]
        faded |= covered(flat, row, {i: core.outline_of(used[i], context) for i, _p in flat + row})
    return owned, circles, faded, dict(handles=handles)


# -- Overlap --------------------------------------------------------------------------------
#
# Placed buttons may overlap, because where a button sits says as much as its
# icon. Greg: "the placement of those buttons is as informative as the
# buttons icon. I think they should be allowed to overlap". A button covered
# by something in front of it is drawn faint, as Ghost Behind draws one, and
# the one in front takes the click. Greg: "make the buttons that are behind
# have increased opacity just like ghost does and prioritize the button that
# is on top ... the analogy for this is sculpting where you have to move
# around to get the right view". A region whose buttons must never overlap
# keeps them in its row.

def covered(circles, row, outlines):
    """Which of the placed `circles` ([(index, center)], back to front) a
    button drawn after them overlaps: a nearer placed one, or one of the
    region's `row`, which is drawn over them all. `outlines` is {index:
    outline_of}."""
    out = set()
    for m, (i, a) in enumerate(circles):
        if any(core.outlines_overlap(a, outlines[i], b, outlines[j]) for j, b in circles[m + 1:] + row):
            out.add(i)
    return out


# -- Handles: a placed button as a 3D arrow -------------------------------------------------
#
# Greg: "there are situations, particularly when a button has been placed on a
# surface, where the haul happening relative to world space is advantageous.
# More like grabbing an empty and dragging it in space ... The button would be
# 3D and wouldn't rotate with screenspace." A placed button shown as a 3D
# Handle is drawn as an arrow (or another shape) from its point. It keeps its
# direction in the scene as the view turns, and a drag goes along it on
# screen. A Move along the arrow, or a Rotate whose way the arrow shows,
# follows the mouse exactly, as grabbing an empty does. A value changes at
# its Speed along it.
#
# Where it points: by default, from its command (Greg, agreeing: "Good
# recommendation"). That is along a Move's axis, the way a Rotate turns the
# button's place, or out from the surface for anything else. It can also be
# chosen by hand: the surface, or an axis of the frame the button rides.
#
# An arrow pointing at the viewer has no way left to drag along. Below
# END_ON it takes no drag, and the press goes to the region (Greg: "it
# should just not be responsive"). It is drawn dimmed, still there to see
# (DIMMED). It is drawn in the screen's pass like any button, its 3D shape
# projected, so there is no other pass to draw.

# shorter and stumpier than the first ones (Greg: "I'd also like the 3D
# arrows to be shorter, stumpier"), then a little smaller again by default
# (Greg: "make the stock 3D arrows a little smaller by default")
ARROW_LENGTH = 2.0                 # an arrow's length on screen seen side-on, in handle radii
# Its shaft's width, in handle radii. It was 0.42 at first, then Greg asked
# for thinner shafts ("make the shafts thinner for the handles. About 20%
# thinner", "thinner again ... about 30%", "another 30% thinner"): 0.34, 0.24
# and 0.17, with an outline round it. Then it became one solid line with no
# outline ("the handle shafts solid colored"), half as wide as that one with
# its outline ("make the shafts 50% thinner"), then a quarter wider ("let's
# try 25% thicker for the the shafts"): about 2.8 px at the default Handle
# Size
ARROW_SHAFT = 0.20
ARROW_HEAD = 0.7                   # its head's radius, in handle radii
ARROW_HEAD_LENGTH = 0.87           # and length
# An arrow's or a box's shaft length, Short to Extra Long, measured in Short
# shafts. Greg: "3 single arrow types that are short, medium and long
# shaft", "the 3 axis arrows need to have longer shafts. At least twice the
# length", then "I'd like the current long arrows to be called extra long and
# make a new size between medium and extra long called long. Also we need the
# same variants but for the box". So Extra Long is as long as the old Long
# was: when Centered, its middle is as far ahead as a Medium's tip. A Box's
# box is BOX_SIZE along each edge, and its shaft is BOX_EXTRA longer than an
# arrow's (a Short Box is as long as the Box was).
SHORT_SHAFT = ARROW_LENGTH - ARROW_HEAD_LENGTH
SHAFTS = {"SHORT": 1.0, "MEDIUM": 2.0, "LONG": 3.0,
          "EXTRA_LONG": (2.0 * (ARROW_HEAD_LENGTH + 2.0 * SHORT_SHAFT) - ARROW_HEAD_LENGTH) / SHORT_SHAFT}
BOX_SIZE = 1.0                      # a Box's box, edge to edge, in handle radii
BOX_EXTRA = 0.6
# an arrow's head is a flat triangle with some depth: HEAD_DEPTH is how deep,
# as a share of its width, and HEAD_TURN how far it is turned past facing the
# view
HEAD_DEPTH = 0.5
HEAD_TURN = math.radians(32.0)


def handle_length(shape, length):
    """An Arrow's or a Box's length end to end, in handle radii, at `length`
    (props.HANDLE_LENGTHS)."""
    total = ARROW_HEAD_LENGTH + SHAFTS.get(length, 1.0) * SHORT_SHAFT
    return total + BOX_EXTRA if shape == "BOX" else total
# a Double Arrow's length end to end, the same as each of a Quad Arrow's
# arms. Greg: "a double-headed arrow on a straight line to suggest 'go either
# way'", and "Double arrow also should have the same width as Two Arrows"
# (Two Arrows was the Quad Arrow's first name)
DOUBLE_LENGTH = 3.5
SHAPE_LENGTH = 3.0                 # how far a shape object reaches along its +Y
END_ON = 0.3                       # shorter on screen than this share of its length, it takes no drag
# and is drawn dimmed (DIMMED), never hidden (Greg: "They should
# become unable to haul but not disappear. It can cause confusion when the
# viewport is in that orientation and there's nothing suggesting any
# controllers are present")
DIMMED = 0.4


def is_handle(button):
    """Whether a button shows as a 3D handle: placed, and not a toggle."""
    return button.placed and button.handle == "HANDLE" and button.action != "TOGGLE"


def handle_drives(button):
    """Which of a handle's directions a drag along it runs: Up / Down (1)
    unless only Left / Right (0) drives something."""
    return 0 if button.across.enabled and not button.up.enabled else 1


def motion_direction(motion, point):
    """(direction, lever) for a program drag's motion (core's
    add_command_kind) at `point`. For a move, its direction. For a turn, the
    way it carries the point, with the point's distance from the axis as
    the lever. (None, None) when there is no motion."""
    if not motion:
        return None, None
    if motion[0] == "MOVE":
        d = Vector(motion[1])
        return (d.normalized(), None) if d.length > 1e-12 else (None, None)
    if motion[0] == "ROTATE" and point is not None:
        axis = Vector(motion[1]).normalized()
        turn = axis.cross(point - Vector(motion[2]))
        return (turn.normalized(), turn.length) if turn.length > 1e-9 else (None, None)
    return None, None


def _command_direction(obj, drag, point):
    """(direction, lever): the way a direction's command moves `point` in
    the world. That is a Move's axis, the way a Rotate turns the point (with
    its distance from the axis), or a program drag's motion. (None, None)
    for anything else."""
    if drag.enabled and drag.program:
        if core.drag_kind(drag) is None:
            return None, None
        target, _why = core.command_object(drag, obj)
        return motion_direction(core.program_motion(drag, target, point), point)
    if not drag.enabled or drag.axis in core.VIEW_AXES or drag.axis == "ALL" \
            or drag.kind not in ("MOVE", "ROTATE"):
        return None, None
    found = core.resolve(drag, obj)
    if found is None:
        return None, None
    target, pb = found
    if drag.kind == "MOVE":
        if pb is not None:
            space = (target.matrix_world @ pb.matrix @ pb.matrix_basis.inverted_safe()).to_3x3()
        else:
            parent = (target.parent.matrix_world @ target.matrix_parent_inverse).to_3x3() \
                if target.parent is not None else Matrix.Identity(3)
            space = parent if drag.along_parent else parent @ core.rotation_of(target)
        out = space @ core.axis_vector(drag.axis)
        return (out, None) if out.length > 1e-12 else (None, None)
    m = core.world_matrix(target, pb)
    axis = (m.to_3x3().normalized() @ core.axis_vector(drag.axis)).normalized()
    turn = axis.cross(point - m.translation)
    return (turn, turn.length) if turn.length > 1e-9 else (None, None)


def handle_direction(obj, region, button, point, normal):
    """(direction, lever) of a handle at `point` in the world. The direction
    is a unit vector. The lever, for a Rotate whose way the handle shows, is
    the point's distance from its axis, else None. `normal` is the surface's
    normal there, or None."""
    choice, drag = button.handle_axis, (button.up, button.across)[1 - handle_drives(button)]
    out, lever = None, None
    if choice == "AUTO":
        out, lever = _command_direction(obj, drag, point)
    elif choice in ("X", "Y", "Z"):
        out = frame_of(obj, region, button).to_3x3() @ core.axis_vector(choice)
    if out is None or out.length < 1e-12:
        out = normal if normal is not None and normal.length > 1e-9 else \
            frame_of(obj, region, button).to_3x3().col[2]
        lever = None
    out = out.normalized()
    return (-out if button.handle_flip else out), lever


def cross_directions(obj, region, button, point, normal):
    """A Quad Arrow's arms: {1: (direction, lever), 0: ...}, for Up / Down
    and Left / Right. Each arm points along its own command's way, as a
    single arrow does. An arm whose command has no way lies flat on the
    surface, square to the other: the two are square to each other, with
    Left / Right to the right of Up / Down seen from outside. When neither
    command has a way, Up / Down runs up the frame the button rides. Points
    and Flip set the Up / Down arm."""
    frame = frame_of(obj, region, button).to_3x3()
    n = normal if normal is not None and normal.length > 1e-9 else frame.col[2]
    n = n.normalized()
    up, up_lever = None, None
    if button.handle_axis == "AUTO":
        up, up_lever = _command_direction(obj, button.up, point)
    elif button.handle_axis in ("X", "Y", "Z"):
        up = frame @ core.axis_vector(button.handle_axis)
    elif button.handle_axis == "NORMAL":
        up = n
    right, right_lever = _command_direction(obj, button.across, point)
    if up is None and right is None:
        f = frame
        for col in (f.col[2], f.col[1], f.col[0]):
            flat = col - n * col.dot(n)
            if flat.length > 1e-6:
                up = flat
                break
    if up is None:
        up = n.cross(right)
    if right is None:
        right = up.cross(n)
        if right.length < 1e-9:
            right = up.orthogonal()
    up, right = up.normalized(), right.normalized()
    if button.handle_flip:
        up = -up
    return {1: (up, up_lever), 0: (right, right_lever)}


def channel_motion(ch, point):
    """(direction, lever): the way a Move or Rotate channel (core.Channel),
    or a program's drag, moves `point` in the world, as a unit vector, and
    for a turn the point's distance from its axis. (None, None) for anything
    else, or when it doesn't move the point."""
    if getattr(ch, "dragging", False):
        return motion_direction(ch.motion(point), point)
    if ch.kind == "MOVE":
        if ch.pb is not None:
            space = (ch.obj.matrix_world @ ch.pb.matrix @ ch.pb.matrix_basis.inverted_safe()).to_3x3()
        else:
            parent = (ch.obj.parent.matrix_world @ ch.obj.matrix_parent_inverse).to_3x3() \
                if ch.obj.parent is not None else Matrix.Identity(3)
            space = parent @ getattr(ch, "frame", Matrix.Identity(3))
        d = space @ core.axis_of(ch)
        return (d.normalized(), None) if d.length > 1e-12 else (None, None)
    if ch.kind == "ROTATE":
        m = core.world_matrix(ch.obj, ch.pb)
        axis = (m.to_3x3().normalized() @ core.axis_of(ch)).normalized()
        turn = axis.cross(point - m.translation)
        return (turn.normalized(), turn.length) if turn.length > 1e-9 else (None, None)
    return None, None


def _arrow_part(view, rv3d, center3, direction, pixel, radius, double=False, full=None, shape="ARROW",
                side=None, length="SHORT", centered=False):
    """An arrow on screen, as a dict, or None.

    It runs from `center3` along `direction`, `length` long
    (props.HANDLE_LENGTHS), or through `center3` when `double` (a head at
    each end) or `centered` (one head). Its head is a flat triangle with
    some depth, or a box when `shape` is BOX: a scale handle, its faces
    square to `side` (a direction across `direction`) if given. The dict
    holds:

    - `base` (center3) and `tip` (the end it points to), on screen,
    - `shaft` and `heads`, their outlines,
    - `caps`, one per head, for a base facing the viewer (None now that
      heads are prisms or boxes, drawn by their faces),
    - `faces`, the heads' faces that face the viewer, each (outline, how
      lit),
    - `points`, every point it reaches,
    - `ratio`, how much of its side-on length shows,
    - `per`, the world length of a pixel along it."""
    box = shape == "BOX"
    full = (full or (DOUBLE_LENGTH if double else handle_length(shape, length))) * radius
    start3 = center3 - direction * (0.5 * full * pixel) if double or centered else center3
    end3 = start3 + direction * (full * pixel)
    base, start, end = (_project(view, rv3d, q) for q in (center3, start3, end3))
    if base is None or start is None or end is None:
        return None
    head_len = (BOX_SIZE if box else ARROW_HEAD_LENGTH) * radius * pixel
    e1 = side - direction * side.dot(direction) if side is not None else None
    e1 = e1.normalized() if e1 is not None and e1.length > 1e-6 else direction.orthogonal().normalized()
    e2 = direction.cross(e1).normalized()
    heads, caps, necks, points, faces = [], [], [], [start, end], []
    for tip3, d in [(end3, direction)] + ([(start3, -direction)] if double else []):
        neck3 = tip3 - d * head_len
        tip2, neck2 = _project(view, rv3d, tip3), _project(view, rv3d, neck3)
        if tip2 is None or neck2 is None:
            return None
        eye = view3d_utils.region_2d_to_origin_3d(view, rv3d, neck2)
        if box:
            # a cube from the neck to the tip, its silhouette the head
            half = 0.5 * head_len
            mid = tip3 - d * half
            axes = (d, e1, e2)
            corners = [mid + (d * a + e1 * b + e2 * c) * half for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]
            flat = [q for q in (_project(view, rv3d, p) for p in corners) if q is not None]
            if len(flat) < 8:
                return None
            heads.append(core.hull(flat))
            caps.append(None)
            toward = (rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))).normalized()
            for k, axis in enumerate(axes):
                for s in (-1.0, 1.0):
                    n = axis * s
                    center = mid + n * half
                    if n.dot(center - eye) >= 0.0:
                        continue                                  # facing away
                    u, v = axes[(k + 1) % 3], axes[(k + 2) % 3]
                    quad = [_project(view, rv3d, center + (u * a + v * b) * half)
                            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                    if all(q is not None for q in quad):
                        faces.append((quad, abs(n.dot(toward))))
            points += flat
        else:
            # a flat triangle with some depth, a prism (it was a cone before).
            # Greg: "I'd also like the arrow handle to look more geometric
            # like the box handle does. The arrow being formed by a flat
            # triangle with some depth". Its flat side is turned to the view
            # about the shaft, so it is never seen edge on as a sliver, then
            # HEAD_TURN further, so its depth shows
            toward = eye - neck3 if rv3d.is_perspective else rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
            n = toward - d * toward.dot(d)
            n = n.normalized() if n.length > 1e-9 else e2
            n = (n * math.cos(HEAD_TURN) + d.cross(n) * math.sin(HEAD_TURN)).normalized()
            w = d.cross(n).normalized()
            half_w = ARROW_HEAD * radius * pixel
            t = 0.5 * HEAD_DEPTH * half_w
            tri = (tip3, neck3 + w * half_w, neck3 - w * half_w)
            front, back = [p + n * t for p in tri], [p - n * t for p in tri]
            corners = front + back
            flat = [q for q in (_project(view, rv3d, p) for p in corners) if q is not None]
            if len(flat) < 6:
                return None
            heads.append(core.hull(flat))
            caps.append(None)
            view_dir = (rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))).normalized()
            # its faces: the two triangles, the base, and the two slanted sides
            polys = [(front, n), (back[::-1], -n), ([front[1], front[2], back[2], back[1]], -d)]
            for a, b in ((0, 1), (2, 0)):
                quad = [front[a], front[b], back[b], back[a]]
                out = (tri[a] + tri[b]) * 0.5 - (tri[0] + tri[1] + tri[2]) / 3.0
                polys.append((quad, out.normalized()))
            for poly, normal in polys:
                center = sum(poly, Vector()) / len(poly)
                if normal.dot(center - eye) >= 0.0:
                    continue                                      # facing away
                flat_poly = [_project(view, rv3d, p) for p in poly]
                if all(q is not None for q in flat_poly):
                    faces.append((flat_poly, abs(normal.dot(view_dir))))
            points += flat
        necks.append(neck2)
    shown = (end - start).length
    ratio = shown / max(full, 1e-9)
    return dict(base=base, tip=end, tip3=end3, shaft=(necks[1] if double else start, necks[0]), heads=heads,
                double=double, caps=caps, faces=faces, points=points, ratio=ratio, live=ratio >= END_ON,
                per=(full * pixel) / shown if shown > 1e-6 else None)


# a shaft's falloff (Greg: "I'm curious how a gradient falloff would look for
# the shafts", "along it's length, starting at middle"). It fades in this
# many steps from where the fade begins to its root, eased, so no line shows
# where the fade begins
SHAFT_FADE_STEPS = 8
# where along the shaft, from its root, the fade begins: its middle at first,
# then nearer the head. Greg: "I like where the falloff ends at the beginning
# of the shaft. I'd like the beginning of the falloff to be a bit closer to
# the end of the shaft. so that the falloff is little more obvious on the
# long shaft types"
SHAFT_FADE_FROM = 0.75


def shaft_fade(root, head, falloff, double=False, steps=SHAFT_FADE_STEPS):
    """A shaft from `root` to `head`, as strips of (point, how much of it
    shows). With no `falloff`, all 1. Otherwise 1 from the head back to
    SHAFT_FADE_FROM of the way along, then easing down to 1 - falloff at the
    root. A `double` shaft has a head at each end, so each half fades the
    same way toward the shaft's middle."""
    if falloff <= 0.0:
        return [[(root, 1.0), (head, 1.0)]]
    if double:
        mid = (root + head) * 0.5
        return shaft_fade(mid, head, falloff, False, steps) + shaft_fade(mid, root, falloff, False, steps)
    begins = root.lerp(head, SHAFT_FADE_FROM)
    strip = []
    for k in range(steps + 1):
        t = k / steps                                  # 0 at the root, 1 where the fade begins
        strip.append((root.lerp(begins, t), 1.0 - falloff * (1.0 - t * t * (3.0 - 2.0 * t))))
    strip.append((head, 1.0))
    return [strip]


# which part of a faded shaft takes a press (Greg agreed to "when falloff is
# on, only the visible part of the shaft should grab"): where at least this
# much of it shows. The faded end near the root, drawn faint or not at all,
# lets a press through to the surface under it
SHAFT_GRAB_SHOWS = 0.3
# how far past a head's outline (an arrowhead, a box) a press still takes it,
# in pixels at Blender's normal interface size (Greg: "Go for it on target
# size"). It gives a few more pixels to aim at, with the handle drawn as it
# was
HEAD_REACH = 4.0


def shaft_grab(root, head, falloff, double=False, shows=SHAFT_GRAB_SHOWS):
    """The parts of a shaft from `root` to `head` that take a press, as
    [(from, to)]: where at least `shows` of it is drawn (shaft_fade), or all
    of it with no falloff. A `double` shaft's halves each lose their faint
    end at its middle."""
    if falloff <= 1.0 - shows:
        return [(root, head)]                          # never fainter than that
    if double:
        mid = (root + head) * 0.5
        return shaft_grab(mid, head, falloff, False, shows) + shaft_grab(mid, root, falloff, False, shows)
    # 1 - falloff (1 - s(t)) >= shows, s the fade's ease (3t^2 - 2t^3), whose
    # inverse is 1/2 - sin(asin(1 - 2s) / 3)
    least = 1.0 - (1.0 - shows) / falloff
    t = 0.5 - math.sin(math.asin(max(-1.0, min(1.0, 1.0 - 2.0 * least))) / 3.0)
    begins = root.lerp(head, SHAFT_FADE_FROM)
    return [(root.lerp(begins, t), head)]


def _project(view, rv3d, p):
    q = view3d_utils.location_3d_to_region_2d(view, rv3d, p)
    return Vector(q) if q is not None else None


_SHAPES = {}                       # mesh pointer -> (polygons, loops, triangles (T, 3))


def _shape(obj):
    """A shape object's points (V, 3) and triangles (T, 3), in its own space,
    or None for a mesh with no faces."""
    me = obj.data
    key = me.as_pointer()
    found = _SHAPES.get(key)
    if found is None or found[0] != len(me.polygons) or found[1] != len(me.loops):
        me.calc_loop_triangles()
        tris = np.empty(3 * len(me.loop_triangles), dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
        found = _SHAPES[key] = (len(me.polygons), len(me.loops), tris.reshape(-1, 3))
    if not len(found[2]) or not len(me.vertices):
        return None
    co = np.empty(3 * len(me.vertices), dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3), found[2]


def _shape_on_screen(view, rv3d, button, frame, world, direction, length, light):
    """A shape object drawn at a handle, as (triangles, points), or None.
    The shape's +Y lies along `direction`, its X as near the frame's X as it
    can be, and it is sized so its reach along +Y is the handle's `length`.
    The triangles are on screen, back to front, each with how lit it is (1
    when facing the viewer)."""
    found = _shape(button.handle_object) if button.handle_object is not None else None
    if found is None:
        return None
    co, tris = found
    reach = float(co[:, 1].max())
    if reach < 1e-6:
        reach = float(np.abs(co).max())
    if reach < 1e-9:
        return None
    side = frame.to_3x3().col[0]
    x = side - direction * side.dot(direction)
    x = x.normalized() if x.length > 1e-6 else direction.orthogonal().normalized()
    z = x.cross(direction).normalized()
    m = np.array([x, direction, z], dtype=np.float64).T * (length / reach)
    pts = co @ m.T + np.array(world)
    view_m = np.array(rv3d.view_matrix, dtype=np.float64)
    depth = (np.c_[pts, np.ones(len(pts))] @ view_m.T)[:, 2]
    flat = [_project(view, rv3d, Vector(p)) for p in pts]
    out = []
    for a, b, c in tris:
        if flat[a] is None or flat[b] is None or flat[c] is None:
            continue
        n = Vector(np.cross(pts[b] - pts[a], pts[c] - pts[a]).tolist())
        lit = abs(n.normalized().dot(light)) if n.length > 1e-12 else 0.0
        out.append(((depth[a] + depth[b] + depth[c]) / 3.0, (flat[a], flat[b], flat[c]), lit))
    out.sort(key=lambda item: item[0])               # the farthest first
    return [(tri, lit) for _d, tri, lit in out], [p for p in flat if p is not None]


# A ring lies about the axis a Rotate turns on, at the button's place, as
# wide on screen as an arrow is long. A drag sweeps around its middle on
# screen and turns by the angle swept, as R does. Seen nearly edge on (its
# axis less than RING_EDGE from the screen's plane, as a share), a drag goes
# along its rim where it was grabbed instead, as a wheel is turned by its
# edge, so it never stops answering. Either way a pixel along the rim turns
# it by 1 / r_px radians (r_px, its radius on screen), so the turn follows
# the mouse.
RING_RADIUS = 1.7                  # its radius on screen, in button radii
RING_WIDTH = 0.28                  # how thick it is drawn and hit, in button radii
RING_EDGE = 0.25


def ring_axis(obj, region, button, point, normal):
    """The axis a ring lies about, in the world. When the handle points From
    Its Command, that is the axis of the Rotate the handle shows. Otherwise
    it is the way an arrow would point."""
    drag = (button.up, button.across)[1 - handle_drives(button)]
    if button.handle_axis == "AUTO" and drag.enabled and drag.program:
        # a program's drag that turns: about its motion's axis
        target, _why = core.command_object(drag, obj)
        motion = core.program_motion(drag, target, point)
        if motion and motion[0] == "ROTATE" and Vector(motion[1]).length > 1e-9:
            axis = Vector(motion[1]).normalized()
            return -axis if button.handle_flip else axis
    elif button.handle_axis == "AUTO" and drag.enabled and drag.kind == "ROTATE" \
            and drag.axis not in core.VIEW_AXES and drag.axis != "ALL":
        found = core.resolve(drag, obj)
        if found is not None:
            m = core.world_matrix(*found)
            axis = m.to_3x3().normalized() @ core.axis_vector(drag.axis)
            if axis.length > 1e-9:
                axis = axis.normalized()
                return -axis if button.handle_flip else axis
    return handle_direction(obj, region, button, point, normal)[0]


def channel_axis(ch):
    """The axis a turning channel turns about, in the world - a Rotate's, or
    a program drag's that turns - or None."""
    if getattr(ch, "dragging", False):
        motion = ch.motion(None)
        if motion and motion[0] == "ROTATE":
            axis = Vector(motion[1])
            return axis.normalized() if axis.length > 1e-9 else None
        return None
    if ch.kind != "ROTATE":
        return None
    own = core.world_matrix(ch.obj, ch.pb).to_3x3().normalized() @ core.axis_of(ch)
    return own.normalized() if own.length > 1e-9 else None


def _ring(view, rv3d, obj, region, button, world, normal, pixel, radius, base):
    """A ring handle's dict (handles_for): its rim on screen (`rim`, closed),
    its middle (`base`), its radius on screen (`r_px`), its axis and whether
    that points at the viewer (`facing`, +1 or -1), and how nearly face on it
    is (`face_on`, 0 edge on to 1)."""
    axis = ring_axis(obj, region, button, world, normal)
    r_world = RING_RADIUS * radius * pixel
    e1 = axis.orthogonal().normalized()
    e2 = axis.cross(e1).normalized()
    rim3 = [world + (e1 * math.cos(t) + e2 * math.sin(t)) * r_world
            for t in (2.0 * math.pi * k / 48.0 for k in range(48))]
    rim = [_project(view, rv3d, p) for p in rim3]
    if any(p is None for p in rim):
        return None
    # the band drawn: a rim inside and one outside, as thick as RING_WIDTH
    half = 0.5 * RING_WIDTH * radius * pixel
    band = [[_project(view, rv3d, world + (p - world) * ((r_world + s) / r_world)) for p in rim3]
            for s in (-half, half)]
    if any(p is None for side in band for p in side):
        band = None
    eye = view3d_utils.region_2d_to_origin_3d(view, rv3d, Vector(base))
    toward = (eye - world).normalized() if rv3d.is_perspective else \
        (rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))).normalized()
    face_on = abs(axis.dot(toward))
    xs, ys = [p.x for p in rim], [p.y for p in rim]
    return dict(world=world, direction=axis, axis=axis, base=Vector(base), tip=rim[0], rim=rim + rim[:1],
                rim3=rim3, r_world=r_world, r_px=RING_RADIUS * radius, pixel=pixel,
                facing=1.0 if axis.dot(toward) >= 0.0 else -1.0, face_on=face_on, ratio=1.0, live=True,
                reach=RING_WIDTH * radius, head=[], cap=None, tris=None, lever=None, per=pixel, band=band,
                bounds=(min(xs), min(ys), max(xs), max(ys)))


def handles_for(context, obj, region, circles):
    """The 3D handles among a region's placed buttons on screen, as {index:
    dict}. Each dict holds:

    - `world` and `direction`, its point and direction in the world,
    - `base` and `tip`, on screen,
    - `per`, the world length of a pixel along it there,
    - `ratio`, how much of its side-on length shows, and `live`, whether it
      takes a drag,
    - `parts`, an arrow each (_arrow_part: shaft, heads, the heads' bases
      facing the viewer): one, or two for a Quad Arrow, which also keeps
      them by the direction each drives (`arms`),
    - a shape's triangles (`tris`) or a ring's rim (`rim`, _ring),
    - `bounds`, its box on screen (lowest x, lowest y, highest x, highest
      y), which its name goes under."""
    view, rv3d = context.region, context.region_data
    used = core.buttons_of(region)
    if view is None or rv3d is None:
        return {}
    depsgraph = context.evaluated_depsgraph_get()
    # the handles' own measure (the scene's Handle Size), each by its own Size
    unit = core.handle_radius(context)
    out = {}
    for i, base in circles:
        if not (0 <= i < len(used)) or not is_handle(used[i]):
            continue
        button = used[i]
        found = button_point(obj, region, button, depsgraph)
        if found is None:
            continue
        radius = unit * button.handle_size
        world, normal = found
        direction, lever = handle_direction(obj, region, button, world, normal)
        a = view3d_utils.region_2d_to_location_3d(view, rv3d, base, world)
        b = view3d_utils.region_2d_to_location_3d(view, rv3d, base + Vector((1.0, 0.0)), world)
        pixel = max((b - a).length, 1e-12)               # a pixel at the handle's depth, in the world
        mode = handle_behind(region, button)
        if button.handle_shape == "RING":
            ring = _ring(view, rv3d, obj, region, button, world, normal, pixel, radius, base)
            if ring is not None:
                ring["radius"] = radius
                # behind the item by its middle
                out[i] = _behind(context, ring, world, mode, depsgraph)
            continue
        shape = button.handle_shape
        handle = dict(world=world, direction=direction, lever=lever, base=Vector(base), reach=ARROW_HEAD * radius,
                      tris=None, rim=None, radius=radius)
        if shape == "OBJECT":
            length = SHAPE_LENGTH * radius * pixel
            tip = _project(view, rv3d, world + direction * length)
            light = (rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))).normalized()
            drawn = _shape_on_screen(view, rv3d, button, frame_of(obj, region, button), world, direction, length,
                                     light)
            if tip is not None and drawn is not None:
                shown = (tip - base).length
                ratio = shown / max(SHAPE_LENGTH * radius, 1e-9)
                handle["tris"], points = drawn
                part = dict(base=Vector(base), tip=tip, shaft=(Vector(base), tip),
                            heads=[core.hull(points + [Vector(base), tip])], caps=[], points=points + [tip],
                            ratio=ratio, live=ratio >= END_ON, per=length / shown if shown > 1e-6 else None)
                handle["parts"] = [part]
            else:
                shape = "ARROW"                      # no shape to draw: an arrow, till there is
        if shape == "CROSS":
            arms = cross_directions(obj, region, button, world, normal)
            parts = {}
            for drives, (d, arm_lever) in arms.items():
                part = _arrow_part(view, rv3d, world, d, pixel, radius, double=True)
                if part is not None:
                    part.update(direction=d, lever=arm_lever, drives=drives)
                    parts[drives] = part
            if not parts:
                continue
            handle["parts"] = list(parts.values())
            handle["arms"] = parts
            handle["direction"], handle["lever"] = arms[1]
        elif shape in ("ARROW", "BOX", "DOUBLE"):
            side = None
            if shape == "BOX":
                # the box square to the frame it rides, a flat side down the
                # item, not a corner (Greg: "For the box styles, rotate it 45
                # degrees. I want a flat side of the box pointing down").
                # Across it goes the first of the frame's Z, Y and X that is
                # square enough to the shaft, else the most square
                f = frame_of(obj, region, button).to_3x3().normalized()
                axes = (f.col[2], f.col[1], f.col[0])
                side = next((c for c in axes if abs(c.dot(direction)) < 0.7),
                            min(axes, key=lambda c: abs(c.dot(direction))))
            part = _arrow_part(view, rv3d, world, direction, pixel, radius, double=shape == "DOUBLE", shape=shape,
                               side=side, length=button.handle_length, centered=button.handle_centered)
            if part is None:
                continue
            handle["parts"] = [part]
        first = handle["parts"][0] if "arms" not in handle else handle["arms"].get(1, handle["parts"][0])
        handle.update(tip=first["tip"], per=first["per"], ratio=max(q["ratio"] for q in handle["parts"]),
                      live=any(q["live"] for q in handle["parts"]),
                      head_reach=HEAD_REACH * core.ui_scale(context))
        if shape != "OBJECT":
            # a faded shaft takes a press only where it shows (shaft_grab)
            for part in handle["parts"]:
                part["grab"] = shaft_grab(*part["shaft"], button.handle_shaft_falloff, part.get("double", False))
        points = [Vector(base)] + [q for part in handle["parts"] for q in part["points"]]
        handle["bounds"] = (min(q.x for q in points), min(q.y for q in points),
                            max(q.x for q in points), max(q.y for q in points))
        # behind the item by its head, the end grabbed - a Length arrow from a
        # tip inside its cap still shows where it sticks out
        tip3 = first.get("tip3", world + direction * (SHAPE_LENGTH * radius * pixel))
        out[i] = _behind(context, handle, tip3, mode, depsgraph)
    return out


def _behind(context, handle, at, mode, depsgraph):
    """Mark what shows of a handle behind the item (handle_behind), by
    whether anything is in front of `at`: faint (`ghost`), or hidden and out
    of reach (`hidden`, and not `live`). Returns the handle."""
    if mode != "SHOW" and occluded(context, at, depsgraph):
        # (never while its buttons are placed by hand: handles_for is not asked)
        if mode == "HIDE":
            handle.update(hidden=True, live=False)
            for part in handle.get("parts", ()):
                part["live"] = False
        else:
            handle["ghost"] = True
    return handle


def handle_alpha(handle):
    """How much of a handle (or one arrow of it) shows: all of it, or, while
    it points too nearly at the viewer to take a drag, dimmed - never none."""
    return 1.0 if handle.get("live", True) else DIMMED


def register():
    core.add_layout(layout)
    if forget not in core.FORGET_HOOKS:
        core.FORGET_HOOKS.append(forget)


def unregister():
    if forget in core.FORGET_HOOKS:
        core.FORGET_HOOKS.remove(forget)
    core.remove_layout(layout)
    PLACING.clear()
