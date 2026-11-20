"""Buttons placed in 3D. They were made in Kneady Pro until the free Kneady
came to make every feature it plays. Greg described them: "Buttons all
start at the object center of the item, each button has an x,y,z offset
channel. This would allow buttons to be placed at each corner of the base of
a finger for instance. As the user moves around the buttons maintain their
location in 3D space. When there's overlaps closer in 3D space has dominance.
Each button does face screen just from specific 3D location."

Each button is either static - in the region's row, column, grid or circle -
or placed in 3D (`placed`), so one region can mix the two. Greg: "An artist
probably wants the ability to have some buttons auto arranged and others
placed in 3D". The row arranges only the buttons left in it.

A placed button's position is a point in the region's box: -1 to 1 across
it on each axis, 0 at its middle. The box is in the frame of the bone the
region's first button turns, or of the object when it turns none. So the
button rides its bone as the character is posed, and one set of positions
fits every region it is copied to, a thick thumb and a thin little finger
alike.

A button facing away from the view is hidden or shown faint, as the
region's Behind setting says (Hide Behind, Ghost Behind or Show Behind).
Where two overlap, the nearer is drawn over the other, the other is faint,
and the nearer takes the click (see Overlap in placed.py). The circles
still face the screen.

Place on Surface (once called Place in 3D) is a mode for one region. Greg:
"When a user clicks 'Place in 3D' ... those buttons persistent during the
placement workflow. Then I can click and drag on any of the buttons and drag
them to a desired location. Snapping will work with this ... Commands
attached to buttons are inactive during placement". While it runs:

- The region's buttons are held on screen (core.pin). Each is dragged onto
  the surface to place it, or onto the row to make it static again.
- Blender's snapping applies as the header's magnet sets it (Vertex, Edge,
  Edge Center, Face), with Ctrl flipping it as for G. It snaps to the
  surface as shown, not the cage. Greg: "cage could create too much space
  between" the item and its buttons.
- A button may hang off the edge, as long as its circle is still over the
  item. Greg: "There just needs to be some overlap to allow for hover
  transitions".
- Enter or Done keeps it all as one undo step. Esc puts every button back.

Where a placed button is, and how a region's buttons are laid out and drawn,
belong to placed.py. This module places them."""

import bpy  # type: ignore
import numpy as np
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Vector  # type: ignore

from . import reg
from . import core
from . import menus as kn_menus
from . import pick as kn_pick
from . import tree as kn_tree
from . import ui as kn_ui
from .placed import is_handle
# Re-exported on purpose: these names live in placed.py, and are reached through
# this module too, so Kneady Pro and the tests can use either. The noqa
# marker tells linters they are not unused imports.
from .placed import (FACING, OVER, back_circle, back_point, button_point, covered,  # noqa: F401
                             dragged_circle, forget, frame_of, layout, placed_circles, point_in_box, region_bone,
                             region_box)
# Place on Surface's state while it runs: the object and region, the button
# being dragged, the mouse, where the button would land, and the shown
# mesh's points and edges. It is placed.py's PLACING, which placed.py reads
# to lay out what is being placed
from .placed import PLACING as MODE

SPREAD = 0.6                       # default positions: this far toward each end of the region, on its front
SNAP_PIXELS = 14.0                 # how near the mouse a vertex or edge must be to snap to it


# -- Placing a button -------------------------------------------------------------------

def _box_place(obj, region, world, world_normal, depsgraph):
    """A point in the world, and the surface's normal there, as a position in
    the region's box - or None."""
    frame = frame_of(obj, region)
    box = region_box(obj, region, depsgraph, frame)
    if box is None:
        return None
    center, half = box
    local = frame.inverted_safe() @ world
    place = ((local.x - center.x) / half.x, (local.y - center.y) / half.y, (local.z - center.z) / half.z)
    if world_normal is not None and world_normal.length > 1e-9:
        return place, tuple((frame.to_3x3().transposed() @ world_normal).normalized())
    return place, (0.0, 0.0, 0.0)


def place_at(obj, region, button, world, world_normal, depsgraph, anchor=""):
    """Place a button at a point in the world, facing out along the
    surface's normal there. With `anchor` (an anchor's key, core.anchor_of)
    it sits at that anchor and follows it from then on. Without one, it
    sits on the surface."""
    found = _box_place(obj, region, world, world_normal, depsgraph)
    if found is None and not anchor:
        return False
    if found is not None:
        # a button at an anchor keeps a surface place too, where it goes if
        # the anchor is cleared
        button.place, button.place_normal = found
    button.anchor = anchor
    button.place_set = True
    button.placed = True
    return True


# -- Anchors --------------------------------------------------------------------------------
#
# A button dragged near an anchor snaps to it. An anchor is a bone's head or
# tail, an object's origin, or a point a program gives (Digit's ring sides,
# tip and pivots). While a button is dragged, the anchors are drawn as small
# rings. Dropped on one, the button sits at it and follows it from then on.
# Greg: "How to place the handles ... I imagine they would be placed
# similarly to how buttons are placed". Dropped anywhere else, it goes on
# the surface as before.

ANCHOR_PIXELS = 16.0               # how near the mouse an anchor must be to snap to it


def anchors_on_screen(context, view, rv3d, obj, region):
    """Each anchor `obj` has on `region` (core.anchors_of) that is on screen:
    [(screen point, anchor)]."""
    out = []
    for anchor in core.anchors_of(obj, region):
        p = view3d_utils.location_3d_to_region_2d(view, rv3d, anchor["point"])
        if p is not None:
            out.append((Vector(p), anchor))
    return out


def anchor_landing(context, view, rv3d, obj, region, at):
    """The anchor a drop at `at` (region pixels) snaps to: (world point, world
    normal, "ANCHOR", key, name), or None."""
    reach = ANCHOR_PIXELS * core.ui_scale(context)
    best = None
    for p, anchor in anchors_on_screen(context, view, rv3d, obj, region):
        d = (p - Vector(at)).length
        if d <= reach and (best is None or d < best[0]):
            best = (d, anchor)
    if best is None:
        return None
    anchor = best[1]
    normal = anchor.get("normal")
    return (Vector(anchor["point"]), Vector(normal) if normal is not None else None, "ANCHOR", anchor["key"],
            anchor["name"])


def place_back_at(obj, region, button, world, world_normal, depsgraph):
    """Place a menu's own button where it shows while its menu is open. That
    button is the way back out of the menu. Greg: "I'd like to be able to
    move and place the 'back' button that is left when you go to deeper
    level"."""
    found = _box_place(obj, region, world, world_normal, depsgraph)
    if found is None:
        return False
    button.back_place, button.back_normal = found
    button.back_placed = True
    return True


# -- Default positions --------------------------------------------------------------------

def _region_object(region, context):
    owner = region.id_data
    return owner if isinstance(owner, bpy.types.Object) else context.active_object


def default_positions(obj, region, toward=None, depsgraph=None, indices=None):
    """Put buttons `indices` on the region's front, spread along its length
    (its bone, or the box's longest side), the first at the top. With
    `indices` None, every shown button not placed yet. `toward` is the
    direction to the viewer in the world (the front view's, -Y, if None).
    Returns how many were put."""
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    used = core.buttons_of(region)
    unset = list(indices) if indices is not None else [i for i in core.shown_buttons(region) if not used[i].place_set]
    if not unset:
        return 0
    frame = frame_of(obj, region)
    box = region_box(obj, region, depsgraph, frame)
    if box is None:
        return 0
    _center, half = box
    rig, _pb = region_bone(region)
    long = 1 if rig is not None else max(range(3), key=lambda k: half[k])
    front = frame.to_3x3().transposed() @ (toward if toward is not None else Vector((0.0, -1.0, 0.0)))
    front[long] = 0.0
    if front.length < 1e-6:
        front = Vector((0.0, 0.0, 0.0))
        front[(long + 2) % 3] = 1.0
    side = max(range(3), key=lambda k: abs(front[k]))
    sign = 1.0 if front[side] >= 0.0 else -1.0
    # the top: the end of the long axis pointing most up in the world
    up = frame.to_3x3().transposed() @ Vector((0.0, 0.0, 1.0))
    top = 1.0 if up[long] >= 0.0 else -1.0
    n = len(unset)
    slots = [SPREAD - 2.0 * SPREAD * k / max(n - 1, 1) for k in range(n)] if n > 1 else [0.0]
    if n == 1:
        # one button joining those placed: the spot along the front farthest
        # from them, so it never lands on top of another
        taken = [Vector(b.place) for k, b in enumerate(used) if b.placed and k not in unset]
        if taken:
            def spot(t):
                at = Vector((0.0, 0.0, 0.0))
                at[side], at[long] = sign, top * t
                return at
            candidates = [SPREAD - 2.0 * SPREAD * k / 6.0 for k in range(7)]
            slots = [max(candidates, key=lambda t: min((spot(t) - p).length for p in taken))]
    for t, i in zip(slots, unset):
        at, normal = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        at[side], at[long] = sign, top * t
        normal[side] = sign
        used[i].place, used[i].place_normal, used[i].place_set = at, normal, True
    return n


def _view_toward(context):
    """The direction from the scene to the viewer, in the world, for the 3D
    view the panel is in - or None."""
    space = getattr(context, "space_data", None)
    rv3d = getattr(space, "region_3d", None) if space is not None and space.type == "VIEW_3D" else None
    if rv3d is None:
        return None
    return rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))


# -- Where a dragged button lands: the surface, snapping, hanging off the edge ----------

def _mesh(obj, depsgraph):
    """The object as shown, in the world: points (V, 3), their normals (V, 3),
    edges (E, 2), and face centers (F, 3) with their normals (F, 3). Read
    once per placing session and copied out, because an evaluated object
    has only one to_mesh slot."""
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        n, f = len(me.vertices), len(me.polygons)
        co = np.empty(3 * n, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        nor = np.empty(3 * n, dtype=np.float64)
        me.vertex_normals.foreach_get("vector", nor)
        edges = np.empty(2 * len(me.edges), dtype=np.int64)
        me.edges.foreach_get("vertices", edges)
        centers = np.empty(3 * f, dtype=np.float64)
        me.polygons.foreach_get("center", centers)
        face_nor = np.empty(3 * f, dtype=np.float64)
        me.polygon_normals.foreach_get("vector", face_nor) if hasattr(me, "polygon_normals") \
            else me.polygons.foreach_get("normal", face_nor)
    finally:
        ev.to_mesh_clear()
    m = np.array(obj.matrix_world, dtype=np.float64)
    nm = np.array(obj.matrix_world.to_3x3().inverted_safe().transposed(), dtype=np.float64)

    def points(a):
        return a.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]

    def normals(a):
        a = a.reshape(-1, 3) @ nm.T
        return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)

    return dict(co=points(co), nor=normals(nor), edges=edges.reshape(-1, 2), centers=points(centers),
                face_nor=normals(face_nor))


def _to_screen(view, rv3d, pts):
    """Project world points (N, 3). Returns their screen positions (N, 2),
    their depth along the view (N,), larger when farther in either kind of
    view, and whether each is in front of a perspective view's eye (N,).
    In an orthographic view every point is."""
    m = np.array(rv3d.perspective_matrix, dtype=np.float64)
    h = np.c_[pts, np.ones(len(pts))] @ m.T
    w = h[:, 3]
    safe = np.where(np.abs(w) < 1e-12, 1e-12, w)
    xy = (h[:, :2] / safe[:, None] * 0.5 + 0.5) * np.array([view.width, view.height])
    depth = -(np.c_[pts, np.ones(len(pts))] @ np.array(rv3d.view_matrix, dtype=np.float64).T)[:, 2]
    return xy, depth, w > 1e-9


def snap_elements(context, ctrl):
    """The elements a drag snaps to, as a set of VERTEX, EDGE, EDGE_MIDPOINT
    and FACE_MIDPOINT, read from the header's magnet and its targets. Ctrl
    flips the magnet, as for G. An empty set means the surface alone."""
    ts = context.scene.tool_settings
    if bool(ts.use_snap) == bool(ctrl):
        return set()
    elements = set(getattr(ts, "snap_elements", set()))
    out = set()
    if "VERTEX" in elements:
        out.add("VERTEX")
    if elements & {"EDGE", "EDGE_PERPENDICULAR"}:
        out.add("EDGE")
    if "EDGE_MIDPOINT" in elements:
        out.add("EDGE_MIDPOINT")
    if "FACE_MIDPOINT" in elements:        # Blender 5.0 on
        out.add("FACE_MIDPOINT")
    return out


SILHOUETTE = 0.35                  # how far past side-on a point may face and still be the edge a button hangs off


def landing(context, view, rv3d, obj, at, snaps, mesh):
    """Where a button dragged to `at` (region pixels) lands: (world point,
    world normal, kind), or None. Kind is SURFACE, VERTEX, EDGE,
    EDGE_MIDPOINT, FACE_MIDPOINT or EDGE_HANG (off the edge, its circle
    still over the item). In order of preference:

    - the nearest snap element within SNAP_PIXELS that faces the view,
    - else the surface under the mouse,
    - else, within a button's radius of the item, the mouse's line at the
      depth of the item's nearest point there."""
    origin = view3d_utils.region_2d_to_origin_3d(view, rv3d, at)
    direction = view3d_utils.region_2d_to_vector_3d(view, rv3d, at).normalized()
    depsgraph = context.evaluated_depsgraph_get()
    inv = obj.matrix_world.inverted_safe()
    hit, loc, normal, _face = obj.ray_cast(inv @ origin, (inv.to_3x3() @ direction).normalized(),
                                           depsgraph=depsgraph)
    hit_world = obj.matrix_world @ loc if hit else None
    hit_normal = (obj.matrix_world.to_3x3().inverted_safe().transposed() @ normal).normalized() if hit else None
    co, nor, edges = mesh["co"], mesh["nor"], mesh["edges"]
    if not len(co):
        return (hit_world, hit_normal, "SURFACE") if hit else None
    scale = core.ui_scale(context)
    xy, depth, ahead = _to_screen(view, rv3d, co)
    mouse = np.array([at[0], at[1]])
    d = np.array(direction, dtype=np.float64)
    facing = nor @ d
    size = max(max(obj.dimensions), 1e-6)
    hit_depth = -(rv3d.view_matrix @ hit_world).z if hit else None

    def seen(facing_values, depths, aheads, limit=0.0):
        """Facing the view, ahead of it, and not behind the surface under the
        mouse."""
        ok = (facing_values < limit) & aheads
        if hit_depth is not None:
            ok &= depths <= hit_depth + 0.02 * size
        return ok

    front = seen(facing, depth, ahead)
    best = None                                   # (pixels, point, normal, kind)
    reach = SNAP_PIXELS * scale

    def offer(pixels, point, normal_vec, kind):
        nonlocal best
        if pixels <= reach and (best is None or pixels < best[0]):
            best = (pixels, point, normal_vec, kind)

    def nearest_on_edges(e):
        """For edges `e`: the index of the one nearest the mouse on screen,
        its distance in pixels and the point along it (0 to 1)."""
        a, b = xy[e[:, 0]], xy[e[:, 1]]
        ab = b - a
        t = np.clip(np.einsum("ij,ij->i", mouse - a, ab) / np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-12), 0.0, 1.0)
        dist = np.linalg.norm(a + ab * t[:, None] - mouse, axis=1)
        k = int(np.argmin(dist))
        return k, float(dist[k]), float(t[k])

    if "VERTEX" in snaps:
        ok = np.flatnonzero(front)
        if len(ok):
            dist = np.linalg.norm(xy[ok] - mouse, axis=1)
            k = ok[int(np.argmin(dist))]
            offer(float(dist.min()), co[k], nor[k], "VERTEX")
    if snaps & {"EDGE", "EDGE_MIDPOINT"} and len(edges):
        e = edges[front[edges[:, 0]] & front[edges[:, 1]]]
        if len(e):
            if "EDGE_MIDPOINT" in snaps:
                dist = np.linalg.norm((xy[e[:, 0]] + xy[e[:, 1]]) * 0.5 - mouse, axis=1)
                k = int(np.argmin(dist))
                offer(float(dist[k]), (co[e[k, 0]] + co[e[k, 1]]) * 0.5, nor[e[k, 0]] + nor[e[k, 1]],
                      "EDGE_MIDPOINT")
            if "EDGE" in snaps:
                k, dist, t = nearest_on_edges(e)
                pa, pb = co[e[k, 0]], co[e[k, 1]]
                offer(dist, pa + (pb - pa) * t, nor[e[k, 0]] + nor[e[k, 1]], "EDGE")
    if "FACE_MIDPOINT" in snaps and len(mesh["centers"]):
        cxy, cdepth, cahead = _to_screen(view, rv3d, mesh["centers"])
        ok = np.flatnonzero(seen(mesh["face_nor"] @ d, cdepth, cahead))
        if len(ok):
            dist = np.linalg.norm(cxy[ok] - mouse, axis=1)
            k = ok[int(np.argmin(dist))]
            offer(float(dist.min()), mesh["centers"][k], mesh["face_nor"][k], "FACE_MIDPOINT")
    if best is not None:
        n = Vector(best[2].tolist())
        return Vector(best[1].tolist()), (n.normalized() if n.length > 1e-12 else hit_normal), best[3]
    if hit:
        return hit_world, hit_normal, "SURFACE"
    # off the item: hang off its edge, the nearest edge along its outline
    # (where the surface is side-on), while the button's circle still covers it
    rim = seen(facing, depth, ahead, SILHOUETTE)
    e = edges[rim[edges[:, 0]] & rim[edges[:, 1]]] if len(edges) else edges
    if not len(e):
        return None
    k, dist, t = nearest_on_edges(e)
    if dist > core.button_radius(context):
        return None
    pa, pb = co[e[k, 0]], co[e[k, 1]]
    on_edge = Vector((pa + (pb - pa) * t).tolist())
    point = view3d_utils.region_2d_to_location_3d(view, rv3d, at, on_edge)
    n = Vector((nor[e[k, 0]] + nor[e[k, 1]]).tolist())
    return point, (n.normalized() if n.length > 1e-12 else None), "EDGE_HANG"


# -- Place on Surface: the mode -----------------------------------------------------------

def _inside(r, x, y):
    return r.width > 1 and r.height > 1 and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height


def _view_under(context, x, y):
    """(area, region, region_3d) of the 3D view under window pixel (x, y), or
    (None, None, None). It is None too over the view's header, toolbar or
    sidebar, which the main region runs underneath. Without that, the
    header's snapping menu never got its click - Greg: "I can't define what
    I want to snap to"."""
    for area in context.window.screen.areas:
        if area.type != "VIEW_3D":
            continue
        view = next((r for r in area.regions if r.type == "WINDOW" and _inside(r, x, y)), None)
        if view is None:
            continue
        if any(r.type != "WINDOW" and _inside(r, x, y) for r in area.regions):
            return None, None, None
        return area, view, area.spaces.active.region_3d
    return None, None, None


def sharing(region, context):
    """How many objects show the region: one, or every one a program shares
    it between (Digit's digits)."""
    key = region.as_pointer()
    return sum(1 for o in context.scene.objects
               if o.type == "MESH" and any(r.as_pointer() == key for r in core.regions_of(o)))


def sharing_names(region, context, obj):
    """The names of the objects a drag can land on: every object in sight
    that shows the region, with `obj` always among them. On a region Digit
    shares between fingers, that is every finger. Otherwise it is `obj`
    alone."""
    key = region.as_pointer()
    names = [o.name for o in context.scene.objects
             if o.type == "MESH" and core.shown_in(o, context)
             and any(r.as_pointer() == key for r in core.regions_of(o))]
    if obj.name not in names:
        names.append(obj.name)
    return names


class KNEADY_OT_place_mode(bpy.types.Operator):
    """Place this region's buttons on the item's surface: they stay on
    screen, and you drag each onto the item to place it, or onto the row to
    make it static again. Blender's snapping works as for G (Ctrl flips it).
    Commands don't run meanwhile. Enter or Done keeps it; Esc puts every
    button back"""
    bl_idname = "kneady.place_mode"
    # once called Place in 3D (Greg: "let's rename Place in 3D to Place on
    # Surface")
    bl_label = "Place on Surface"
    bl_options = {"REGISTER", "UNDO"}

    # which buttons to place: a menu's (the id of the button that opens it),
    # opened while they are placed, or 0 for the region's own
    menu: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"})
    # set by Viewport Edit's icon at the square's top left (kn_pick): the
    # object and region whose showing buttons are placed - a menu's, if one
    # is open
    target: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    region: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return not MODE

    def invoke(self, context, event):
        from . import menu_build as menus
        region = getattr(context, "kneady_region", None)
        if region is None and self.target:
            obj = bpy.data.objects.get(self.target)
            region = core.find_region(obj, self.region) if obj is not None else None
            if region is not None:
                parent = kn_pick.shown_parent(obj, region)
                self.menu = core.buttons_of(region)[parent].uid if parent is not None else 0
        if region is None:
            return {"CANCELLED"}
        obj = _region_object(region, context)
        if obj is None or obj.type != "MESH" or core.find_region(obj, region.id) is None:
            self.report({"WARNING"}, "Select the object the region is on")
            return {"CANCELLED"}
        if not context.scene.kneady_on:
            context.scene.kneady_on = True
        # Greg asked for only one of the two at a time: Rearrange goes off
        if getattr(context.window_manager, "kneady_arrange", False):
            context.window_manager.kneady_arrange = False
        if self.menu and not menus.open_for_placing(obj, region, self.menu):
            return {"CANCELLED"}
        if not self.menu:
            menus.close(obj, region, all_levels=True)
        self._owner, self._path = region.id_data, region.path_from_id()
        self._before = core.to_data(region)
        MODE.clear()
        MODE.update(obj=obj.name, rid=region.id, key=region.as_pointer(), drag=None, mouse=None, target=None,
                    done=False, mesh=None, shared=sharing(region, context), menu=self.menu,
                    sharers=sharing_names(region, context, obj), meshes={}, target_obj=None)
        core.pin(obj.name, region.id)
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        self._draw = bpy.types.SpaceView3D.draw_handler_add(_draw_marks, (), "WINDOW", "POST_PIXEL")
        self._status(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _region(self):
        try:
            return self._owner.path_resolve(self._path)
        except (ValueError, AttributeError, ReferenceError):
            return None

    def _status(self, context, note=""):
        region = self._region()
        ctrl = getattr(self, "_ctrl", False)
        snaps = snap_elements(context, ctrl)
        names = {"VERTEX": "Vertex", "EDGE": "Edge", "EDGE_MIDPOINT": "Edge Center", "FACE_MIDPOINT": "Face Center"}
        snapping = ("snapping to %s" % ", ".join(names[s] for s in sorted(snaps))) if snaps else "no snapping"
        shared = " (all %d sharing them)" % MODE["shared"] if MODE.get("shared", 1) > 1 else ""
        whose, back = (region.name if region is not None else "?"), "the row to make it static"
        menu = self._menu_button(region)
        if menu is not None:
            whose, back = "%s's menu" % menu.name, "the ring to put it back in it - %s too, onto its mark" % menu.name
        context.workspace.status_text_set(
            "%sPlacing %s's buttons%s: drag one onto the item to place it, onto %s      "
            "%s (Ctrl flips it)      Enter: done      Esc: cancel" % (
                note, whose, shared, back, snapping.capitalize()))

    def _menu_button(self, region):
        from . import menu_build as menus
        if region is None or not MODE.get("menu"):
            return None
        used = core.buttons_of(region)
        j = menus.uid_index(used, MODE["menu"])
        return used[j] if j is not None else None

    def _end(self, context, keep):
        from . import menu_build as menus
        region = self._region()
        obj = bpy.data.objects.get(MODE.get("obj", ""))
        if MODE.get("menu") and region is not None and obj is not None:
            menus.close(obj, region, all_levels=True)
        if not keep and region is not None:
            core.from_data(region, self._before, skip=core.REGION_OWN)
        context.window_manager.event_timer_remove(self._timer)
        bpy.types.SpaceView3D.draw_handler_remove(self._draw, "WINDOW")
        MODE.clear()
        core.unpin()
        context.workspace.status_text_set(None)
        core.forget()
        return {"FINISHED"} if keep else {"CANCELLED"}

    def _view(self, context, event):
        area, view, rv3d = _view_under(context, event.mouse_x, event.mouse_y)
        if view is None:
            return None
        return area, view, rv3d, Vector((event.mouse_x - view.x, event.mouse_y - view.y))

    def modal(self, context, event):
        region = self._region()
        obj = bpy.data.objects.get(MODE.get("obj", ""))
        if region is None or obj is None or not context.scene.kneady_on:
            return self._end(context, False)
        if MODE.get("done") or (event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS"):
            return self._end(context, True)
        if kn_pick.arranging(context):
            return self._end(context, True)          # Rearrange turned on in the panel: one at a time
        if event.type == "ESC" and event.value == "PRESS":
            if MODE.get("drag") is not None:
                return self._drop(context, None)
            return self._end(context, False)
        if event.type in {"LEFT_CTRL", "RIGHT_CTRL"}:
            self._ctrl = event.value == "PRESS"
            self._status(context)
        if event.type == "TIMER":
            # snapping changed in the header: say so
            snaps = snap_elements(context, getattr(self, "_ctrl", False))
            if snaps != getattr(self, "_snaps", None):
                self._snaps = snaps
                self._status(context)
            return {"PASS_THROUGH"}
        found = self._view(context, event)
        dragging = MODE.get("drag") is not None
        if event.type == "RIGHTMOUSE" and event.value == "PRESS" and dragging:
            return self._drop(context, None)          # this drag only, back where it was
        if event.type == "MOUSEMOVE" and dragging:
            if found is not None:
                area, view, rv3d, at = found
                with context.temp_override(area=area, region=view):
                    self._follow(context, view, rv3d, obj, at, event.ctrl)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if found is None:
                return {"PASS_THROUGH"}             # the header's snapping, the sidebar's Done
            area, view, rv3d, at = found
            with context.temp_override(area=area, region=view):
                _block, button = core.buttons_under(context, obj, region, at)
                icons = kn_pick.edit_icons(context, obj, region) if core.picking(context) else {}
            reach = kn_pick.EDIT_SIZE * core.button_radius(context) + 2.0
            if ICON_KEY in icons and (at - icons[ICON_KEY]).length <= reach:
                return self._end(context, True)     # its icon again: done (Greg: a toggle, like Rearrange's)
            if "ARRANGE" in icons and (at - icons["ARRANGE"]).length <= reach:
                done = self._end(context, True)     # Rearrange's: done, and Rearrange on - one at a time
                context.window_manager.kneady_arrange = True
                return done
            if button is None:
                return {"PASS_THROUGH"}             # anything but a button: Blender's, as ever
            if not self._placing(region, button):
                return {"RUNNING_MODAL"}            # a button of another level
            used = core.buttons_of(region)
            b = used[button]
            back = self._is_back(region, button)
            was = ((b.back_placed, tuple(b.back_place), tuple(b.back_normal)) if back else
                   (b.placed, tuple(b.place), tuple(b.place_normal), b.place_set, b.anchor))
            MODE.update(drag=button, mouse=at, target=None, back=back, was=was)
            with context.temp_override(area=area, region=view):
                self._follow(context, view, rv3d, obj, at, event.ctrl)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and dragging:
            return self._drop(context, found)
        return {"PASS_THROUGH"}                     # orbit, zoom, the sidebar

    def _follow(self, context, view, rv3d, obj, at, ctrl):
        """Work out where on the item the dragged button would land, as the
        mouse moves. On a region several objects share, it lands on
        whichever of them is under the mouse and nearest the eye, and hangs
        off an edge only where none is. It once landed only on the active
        object: Greg's Thicken End menu, on a region all five fingers share,
        landed only on the active finger, and a drop on another finger went
        back where it was."""
        depsgraph = context.evaluated_depsgraph_get()
        meshes = MODE.setdefault("meshes", {})
        snaps = snap_elements(context, ctrl)
        region = self._region()
        best = None
        # an anchor near the mouse first (anchor_landing): the nearest on
        # screen, of whichever object sharing the region it is on
        anchored = None
        if region is not None and not MODE.get("back"):
            for name in MODE.get("sharers") or [obj.name]:
                o = bpy.data.objects.get(name)
                got = anchor_landing(context, view, rv3d, o, region, at) if o is not None else None
                if got is None:
                    continue
                p = view3d_utils.location_3d_to_region_2d(view, rv3d, got[0])
                d = (Vector(p) - Vector(at)).length if p is not None else 1e9
                if anchored is None or d < anchored[0]:
                    anchored = (d, name, got)
        for name in ((MODE.get("sharers") or [obj.name]) if anchored is None else ()):
            o = bpy.data.objects.get(name)
            if o is None:
                continue
            if name not in meshes:
                meshes[name] = _mesh(o, depsgraph)
            found = landing(context, view, rv3d, o, at, snaps, meshes[name])
            if found is None:
                continue
            rank = (found[2] == "EDGE_HANG", -(rv3d.view_matrix @ found[0]).z)
            if best is None or rank < best[0]:
                best = (rank, name, found)
        if anchored is not None:
            _d, name, got = anchored
            best = (None, name, got[:3])
        MODE["anchor"] = (anchored[2][3], anchored[2][4]) if anchored is not None else None
        MODE["mouse"] = at
        MODE["target"] = best[2] if best is not None else None
        MODE["target_obj"] = best[1] if best is not None else None
        over = self._over_home if MODE.get("back") else self._over_row
        MODE["to_static"] = region is not None and over(context, obj, region, at)
        core.redraw()

    def _land_on(self, obj, region):
        """Return the object a drop landed on (MODE's target_obj), and move
        the placing to it: its buttons, and an open menu with them, now show
        there, where the artist is working. A position is measured against
        the box of the object it lands on. That suits a shared region, since
        each object shows the position against its own box."""
        name = MODE.get("target_obj") or obj.name
        landed = bpy.data.objects.get(name) or obj
        core.forget(landed.name)
        if landed.name != obj.name:
            from . import menus as kn_menus
            path = kn_menus.OPEN.pop(kn_menus.key_of(obj, region), None)
            if path is not None:
                kn_menus.OPEN[kn_menus.key_of(landed, region)] = path
            MODE["obj"] = landed.name
            core.pin(landed.name, region.id)
        return landed

    def _placing(self, region, index):
        """Whether button `index` is one this placing is for: a button in the
        menu being placed (the menu's own button, the way back, included),
        or with no menu, one of the region's own."""
        from . import menu_build as menus
        up = menus.parents(region)
        if not 0 <= index < len(up):
            return False
        if not MODE.get("menu"):
            return up[index] is None
        return self._is_back(region, index) or (
            up[index] is not None and core.buttons_of(region)[up[index]].uid == MODE["menu"])

    def _is_back(self, region, index):
        """Whether button `index` is the one whose menu is being placed."""
        return bool(MODE.get("menu")) and core.buttons_of(region)[index].uid == MODE["menu"]

    def _over_home(self, context, obj, region, at):
        """Whether `at` is within the circle of the menu button's own place,
        where it shows when it is not placed for its menu."""
        from . import menu_build as menus
        top = menus.opened(obj, region)
        home = menus.home_of(context, obj, region, top) if top is not None else None
        return home is not None and (at - home).length <= core.button_radius(context)

    def _over_row(self, context, obj, region, at):
        """Whether `at` is on the static row, or on the region's middle
        (where the row would be) when no button is left in it. For a menu's
        buttons, whether it is on the ring: on the menu's button or one in
        the ring, not the gaps, so a button can still be placed near it."""
        radius, scale = core.button_radius(context), core.ui_scale(context)
        if MODE.get("menu"):
            from . import menu_build as menus
            used = core.buttons_of(region)
            j = menus.uid_index(used, MODE["menu"])
            shown, _static, _faded = core.layout_parts(context, obj, region)
            ring = [(i, c) for i, c in shown if i != MODE.get("drag") and (i == j or not used[i].placed)]
            widths = {i: core.half_size(used[i], context) for i, _c in ring}
            return core.in_block(ring, at, radius, scale, True, 0.0, widths)
        _placed, static, _faded = core.layout_parts(context, obj, region)
        if static:
            used = core.buttons_of(region)
            widths = {i: core.half_width(used[i], context) for i, _c in static}
            return core.in_block(static, at, radius, scale, False, 0.0, widths)
        center = core.region_center(context, obj, region.id)
        return center is not None and (at - center).length <= 2.0 * radius

    def _drop(self, context, found):
        """Let go of the dragged button. Onto the row, it becomes static.
        Onto the item (or just off its edge), it is placed there. Anywhere
        else, or when cancelled, it goes back where it was."""
        region, obj = self._region(), bpy.data.objects.get(MODE["obj"])
        button = core.buttons_of(region)[MODE["drag"]]
        to_static = found is not None and MODE.get("to_static")
        if MODE.get("back"):
            # the menu's own button: placed where it shows while its menu is
            # open, or, dropped on its mark, back to its own place
            if to_static:
                button.back_placed = False
            elif found is not None and MODE.get("target") is not None:
                world, world_normal, _kind = MODE["target"]
                obj = self._land_on(obj, region)
                place_back_at(obj, region, button, world, world_normal, context.evaluated_depsgraph_get())
            else:
                button.back_placed, button.back_place, button.back_normal = MODE["was"]
            MODE.update(drag=None, mouse=None, target=None, to_static=False, back=False)
            self._status(context)
            core.redraw()
            return {"RUNNING_MODAL"}
        placed, place, normal, was_set = MODE["was"][:4]
        note = ""
        if to_static and placed:
            # a placed one back to a full row - or a menu's full ring: it stays placed
            from . import menu_build as menus
            if not MODE.get("menu") and menus.row_full(region, MODE["drag"]):
                note = "%s.  " % menus.ROW_FULL
            elif MODE.get("menu"):
                opener = menus.uid_index(core.buttons_of(region), MODE["menu"])
                if menus.ring_full(region, opener, MODE["drag"]):
                    note = "%s.  " % menus.RING_FULL
        if to_static and not note:
            button.placed = False
            button.anchor = ""
        elif found is not None and MODE.get("target") is not None and not to_static:
            world, world_normal, _kind = MODE["target"]
            obj = self._land_on(obj, region)
            anchor = MODE.get("anchor")
            place_at(obj, region, button, world, world_normal, context.evaluated_depsgraph_get(),
                     anchor=anchor[0] if anchor else "")
            if anchor:
                note = "%s at %s.  " % (button.name, anchor[1])
        else:
            button.placed, button.place, button.place_normal, button.place_set = placed, place, normal, was_set
            button.anchor = MODE["was"][4] if len(MODE["was"]) > 4 else button.anchor
        MODE.update(drag=None, mouse=None, target=None, to_static=False, anchor=None)
        self._status(context, note)
        core.redraw()
        return {"RUNNING_MODAL"}


def _draw_marks():
    """While placing, draw where the dragged button would snap, and where the
    row is once every button has left it."""
    context = bpy.context
    if not MODE or context.region_data is None:
        return
    obj = bpy.data.objects.get(MODE.get("obj", ""))
    region = core.find_region(obj, MODE.get("rid")) if obj is not None else None
    if region is None:
        return
    import gpu  # type: ignore
    from gpu_extras.batch import batch_for_shader  # type: ignore
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", 1.5 * core.ui_scale(context))
    radius = core.button_radius(context)

    def ring(center, r, rgba, steps=32):
        import math
        pts = [(center.x + r * math.cos(2 * math.pi * k / steps), center.y + r * math.sin(2 * math.pi * k / steps))
               for k in range(steps + 1)]
        shader.uniform_float("color", rgba)
        batch_for_shader(shader, "LINES", {"pos": [p for a, b in zip(pts, pts[1:]) for p in (a, b)]}).draw(shader)

    gpu.state.blend_set("ALPHA")
    if MODE.get("drag") is not None:
        _placed, static, _faded = core.layout_parts(context, obj, region)
        if MODE.get("back"):
            # the menu's button's own place: drop it here to put it back
            from . import menu_build as menus
            top = menus.opened(obj, region)
            home = menus.home_of(context, obj, region, top) if top is not None else None
            if home is not None:
                ring(home, radius, (*region.color, 0.9 if MODE.get("to_static") else 0.45))
        elif not static and not MODE.get("menu"):
            # where the row is when no button is left in it: drop here to return one
            center = core.region_center(context, obj, region.id)
            if center is not None:
                ring(center, radius, (*region.color, 0.9 if MODE.get("to_static") else 0.45))
        target = MODE.get("target")
        if target is not None and target[2] in ("VERTEX", "EDGE", "EDGE_MIDPOINT", "FACE_MIDPOINT", "ANCHOR"):
            p = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, target[0])
            if p is not None:
                big = 7.0 if target[2] == "ANCHOR" else 4.0
                ring(Vector(p), big * core.ui_scale(context), (1.0, 1.0, 1.0, 0.95), 12)
        if not MODE.get("back"):
            # the anchors a button snaps to: a small ring each, on the object
            # under the mouse (or the one being placed)
            on = bpy.data.objects.get(MODE.get("target_obj") or "") or obj
            for p, _anchor in anchors_on_screen(context, context.region, context.region_data, on, region):
                ring(p, 3.0 * core.ui_scale(context), (*region.color, 0.85), 10)
    gpu.state.blend_set("NONE")


class KNEADY_OT_place_done(bpy.types.Operator):
    """Finish placing: keep where the buttons are"""
    bl_idname = "kneady.place_done"
    bl_label = "Done"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        MODE["done"] = True
        return {"FINISHED"}


# Where a button is and how it shows, as one choice of three: in the row (in
# a menu, its ring), on the item as a button facing the screen, or on the
# item as a 3D handle. It replaced a Placed in 3D checkbox with a Shows As
# under it. Greg: "It's kind of a strange design ... Maybe the placed in 3D
# button is now redundant?"
LOOKS = (("ROW", "In Row", "In the region's row - in a menu, in the ring around its button"),
         ("ITEM", "On Item", "On the item: a button facing the screen at its own point, staying there as you orbit "
          "and pose. Place on Surface drags it where it goes"),
         ("HANDLE", "3D Handle", "On the item as a 3D handle - an arrow, a ring or a mesh's shape - keeping its "
          "direction in the scene; a drag goes along it. Place on Surface drags it where it goes"))


def look_of(button):
    """The button's LOOKS key."""
    if not button.placed:
        return "ROW"
    return "HANDLE" if is_handle(button) else "ITEM"


class KNEADY_OT_button_placement(bpy.types.Operator):
    """Move this button between the region's row and its place in 3D"""
    bl_idname = "kneady.button_placement"
    bl_label = "Placement"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    placed: bpy.props.BoolProperty(options={"SKIP_SAVE"})
    # one of LOOKS, which sets placed too. Empty: `placed` alone (the list row's toggle)
    look: bpy.props.StringProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def description(cls, context, properties):
        found = next((d for key, _n, d in LOOKS if key == properties.look), None)
        if found:
            return found
        if properties.placed:
            return ("On the surface: put this button on the item, on the region's front - then Place on Surface to "
                    "drag it where it goes")
        return "Off the surface: return this button to the region's row - in a menu, to its ring"

    def execute(self, context):
        region = getattr(context, "kneady_region", None)
        button = getattr(context, "kneady_button", None)
        if region is None or button is None:
            return {"CANCELLED"}
        if self.look:
            if self.look not in {key for key, _n, _d in LOOKS}:
                return {"CANCELLED"}
            if self.look == "HANDLE" and button.action == "TOGGLE":
                self.report({"WARNING"}, "A toggle is always a button facing the screen")
                return {"CANCELLED"}
            self.placed = self.look != "ROW"
        from . import menu_build as menus
        index = menus.index_of(region, button)
        if not self.placed and index is not None and menus.parents(region)[index] is None:
            # back to the row, if it has room
            if menus.row_full(region, index):
                self.report({"WARNING"}, menus.ROW_FULL)
                return {"CANCELLED"}
        elif not self.placed and index is not None:
            # back to its menu's ring, if it has room
            if menus.ring_full(region, menus.parents(region)[index], index):
                self.report({"WARNING"}, menus.RING_FULL)
                return {"CANCELLED"}
        if self.placed and not button.place_set:
            obj = _region_object(region, context)
            if obj is None or obj.type != "MESH":
                return {"CANCELLED"}
            index = next(i for i, b in enumerate(region.buttons) if b == button)
            default_positions(obj, region, _view_toward(context), context.evaluated_depsgraph_get(), [index])
        button.placed = self.placed
        if self.look in ("ITEM", "HANDLE"):
            button.handle = "HANDLE" if self.look == "HANDLE" else "BUTTON"
        core.redraw()
        return {"FINISHED"}


class KNEADY_OT_back_return(bpy.types.Operator):
    """While its menu is open, show this button where it opens the menu again"""
    bl_idname = "kneady.back_return"
    bl_label = "Return"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        button = getattr(context, "kneady_button", None)
        if button is None:
            return {"CANCELLED"}
        button.back_placed = False
        core.redraw()
        return {"FINISHED"}


# -- The panel --------------------------------------------------------------------------

def draw_back(layout, region, button):
    """In a menu's Opens Menu section, once its button is placed for its
    open menu: where it sits, and Return."""
    row = layout.row(align=True)
    row.context_pointer_set("kneady_button", button)
    row.label(text="While Open", icon="LOOP_BACK")
    row.prop(button, "back_place", text="")
    row.operator("kneady.back_return", icon="ALIGN_JUSTIFY")


def draw_behind(layout, context, region):
    """What shows of a placed button behind the item. It is a dropdown -
    Greg: "even when off, No Hide/Ghost informs what the dropdown does".
    One setting covers the whole region. It shows in the region's settings
    while any of its buttons is placed, in a menu too, or placed for its
    open menu. It once showed under the region's own list only, and Greg
    couldn't find it - "I can't seem to find where to assign a button placed
    in 3D to ghost instead of hide"; his placed buttons were all in menus.
    Then it showed under each menu's list as well, until the tree gave the
    region one place for its settings."""
    if behind_shown(region):
        layout.prop(region, "behind", text="Behind")


def behind_shown(region):
    """Whether any of the region's buttons is placed in 3D - or placed for
    its open menu - so Behind has something to do."""
    return any(b.placed or b.back_placed for b in core.buttons_of(region))


def draw_region(layout, context, region):
    """Draw Behind in a region's settings, in the part about its buttons
    (kn_ui.REGION_BUTTONS). Place on Surface is at the top of the tab,
    under Rearrange (draw_toggle). It used to be in the region's settings
    and each menu's."""
    draw_behind(layout, context, region)


def placing_list(context):
    """The list that Place on Surface in the panel places, as (region,
    menu): the list holding the row selected in the tree. menu is 0 for the
    region's own buttons, or the id of the button whose menu holds the
    selected button. (None, 0) when nothing is selected."""
    from . import menu_build as menus
    _obj, region, index = kn_tree.selection(context)
    if region is None:
        return None, 0
    up = menus.parents(region)[index] if index is not None else None
    return region, (core.buttons_of(region)[up].uid if up is not None else 0)


def draw_toggle(layout, context):
    """Draw Place on Surface under Rearrange at the top of the tab
    (kn_pick.PANEL_TOGGLES), for the list of the row selected in the tree,
    or Done while placing. Greg: "move "Place on Surface" right below
    "Rearrange" in the n-panel". Only one of the two is on at a time."""
    if MODE:
        layout.operator("kneady.place_done", text="Done Placing", icon="CHECKMARK")
        return
    region, menu = placing_list(context)
    row = layout.row(align=True)
    if region is None:
        row.enabled = False
        row.operator("kneady.place_mode", icon="IMPORT")
        return
    row.context_pointer_set("kneady_region", region)
    row.operator("kneady.place_mode", icon="IMPORT").menu = menu


def draw_row(layout, context, region, button):
    """In a button's row of a list: a Placed in 3D toggle, lit while placed
    and drawn as an arrow for a 3D handle, then a mark if it opens a menu.
    It replaces kn_menus.draw_row's marks (see register)."""
    index = kn_menus.index_of(region, button)
    if index is None:
        return
    sub = layout.row(align=True)
    sub.active = button.placed
    sub.context_pointer_set("kneady_region", region)
    sub.context_pointer_set("kneady_button", button)
    sub.operator("kneady.button_placement", text="", emboss=False,
                 icon="EMPTY_SINGLE_ARROW" if is_handle(button) else "ORIENTATION_GIMBAL").placed = not button.placed
    if button.opens_menu and kn_menus.can_open(region, index):
        layout.label(text="", icon="COLLAPSEMENU")


def draw_button(layout, context, region, button):
    """Where a button is and how it shows, just under Drag / Toggle
    (kn_ui.BUTTON_LOOKS). First, one choice of three (LOOKS): In Row (In
    Ring in a menu), On Item, or 3D Handle. A toggle is never a 3D Handle -
    Greg: "Toggles can't be 3D Handles". The look is picked in one place,
    not by a Placed in 3D checkbox with a Shows As under it - Greg: "Maybe
    the placed in 3D button is now redundant?".

    On the item, its position follows. A 3D Handle also gets its shape - an
    Arrow, a Ring, an Object's (Greg: "3D buttons would have an option for
    arrows or 3D file") - and which way it points. A 3D Handle's settings
    show none of a screen button's: no icon, no Circle or Square (kn_ui
    leaves its icon out). Greg: "once a user has selected 3D Handle then
    they shouldn't see the 2D button options"."""
    from . import menu_build as menus
    index = menus.index_of(region, button)
    in_menu = index is not None and menus.parents(region)[index] is not None
    current = look_of(button)
    row = layout.row(align=True)
    row.context_pointer_set("kneady_region", region)
    row.context_pointer_set("kneady_button", button)
    for key, text, _d in LOOKS:
        if key == "HANDLE" and button.action == "TOGGLE":
            continue
        row.operator("kneady.button_placement", text="In Ring" if key == "ROW" and in_menu else text,
                     depress=key == current).look = key
    if not button.placed:
        return
    # where it sits: at an anchor it follows, or on the surface at its place
    row = layout.row(align=True)
    row.context_pointer_set("kneady_region", region)
    row.context_pointer_set("kneady_button", button)
    if button.anchor:
        obj = _region_object(region, context)
        found = core.anchor_of(obj, region, button.anchor) if obj is not None else None
        name = found["name"] if found is not None else button.anchor
        row.menu("KNEADY_MT_anchors", text="At %s" % name, icon="PIVOT_CURSOR")
        row.operator("kneady.button_anchor", text="", icon="X").key = ""
        if found is None and obj is not None:
            layout.label(text="%s has no such point: hidden on it" % obj.name, icon="INFO")
    else:
        row.prop(button, "place", text="")
        layout.menu("KNEADY_MT_anchors", text="Sits At: Surface", icon="PIVOT_CURSOR")
    if current != "HANDLE":
        return
    col = layout.column(align=True)
    col.prop(button, "handle_shape", text="Shape")
    if button.handle_shape == "OBJECT":
        col.prop(button, "handle_object", text="")
    if button.handle_shape in ("ARROW", "BOX"):
        # Short to Extra Long, starting at its place or centered on it
        row = layout.row(align=True)
        row.prop(button, "handle_length", text="")
        row.prop(button, "handle_centered", toggle=True)
    sub = layout.row(align=True)
    sub.prop(button, "handle_axis", text="Points")
    sub.prop(button, "handle_flip", text="", icon="ARROW_LEFTRIGHT", toggle=True)
    # its own size, against the scene's Handle Size (Greg: "the rotate needs
    # to be much larger"), and below, its own color (Greg: "we're going to
    # need the ability to color a handle")
    row = layout.row(align=True)
    row.prop(button, "handle_size", slider=True)
    # how much of it shows (Greg: "Opacity would be an additional useful
    # setting for the handles")
    row.prop(button, "handle_opacity", slider=True)
    # its shaft fading along its length from the middle (Greg: "I'm curious
    # how a gradient falloff would look for the shafts")
    if button.handle_shape not in ("RING", "OBJECT"):
        layout.prop(button, "handle_shaft_falloff", slider=True)
    # how it shows where anything is in front of it (Greg: "Let's have the
    # ghost behind option available for handles")
    layout.prop(button, "handle_behind")
    row = layout.row(align=True)
    row.prop(button, "handle_use_color", text="Own Color")
    sub = row.row(align=True)
    sub.active = button.handle_use_color
    # the color set here, or one of the axis colors of Blender's theme (Greg:
    # "I like the idea of adopting from Blenders theme")
    sub.prop(button, "handle_color_from", text="")
    if button.handle_color_from == "OWN":
        sub.prop(button, "handle_color", text="")
    # its interior (Greg: "need interior color for the handles")
    row = layout.row(align=True)
    row.prop(button, "handle_use_fill", text="Interior")
    sub = row.row(align=True)
    sub.active = button.handle_use_fill
    sub.prop(button, "handle_fill", text="")
    # how much of the interior shows, in its own color or the dark one. At 0
    # only its edges show (Greg: "Could there be an option for the interior
    # to be transparent?")
    layout.prop(button, "handle_fill_alpha", slider=True)
    # its color under the mouse (Greg: "I'd like to be able to change the hover
    # color for handles")
    row = layout.row(align=True)
    row.prop(button, "handle_use_hover", text="Hover Color")
    sub = row.row(align=True)
    sub.active = button.handle_use_hover
    sub.prop(button, "handle_hover", text="")


class KNEADY_OT_button_anchor(bpy.types.Operator):
    """Sit this button at a point it follows - or, with none, on the surface,
    where it was placed"""
    bl_idname = "kneady.button_anchor"
    bl_label = "Sits At"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    key: bpy.props.StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        button = getattr(context, "kneady_button", None)
        if button is None:
            return {"CANCELLED"}
        button.anchor = self.key
        button.placed = True
        core.redraw()
        return {"FINISHED"}


class KNEADY_MT_anchors(bpy.types.Menu):
    """The points a placed button can sit at and follow: the surface, and the
    anchors of the region's object - a program's (Digit's ring sides, tip and
    pivots) and Kneady's own (its origin, and the bones its buttons turn)"""
    bl_idname = "KNEADY_MT_anchors"
    bl_label = "Sits At"

    def draw(self, context):
        layout = self.layout
        region = getattr(context, "kneady_region", None)
        button = getattr(context, "kneady_button", None)
        if region is None or button is None:
            layout.label(text="Pick a button in the tree")
            return
        layout.context_pointer_set("kneady_region", region)
        layout.context_pointer_set("kneady_button", button)
        layout.operator("kneady.button_anchor", text="Surface", icon="SURFACE_DATA",
                        depress=not button.anchor).key = ""
        obj = _region_object(region, context)
        anchors = core.anchors_of(obj, region) if obj is not None else []
        if not anchors:
            layout.label(text="Select an object the region is on")
            return
        layout.separator()
        for anchor in anchors:
            op = layout.operator("kneady.button_anchor", text=anchor["name"], icon="PIVOT_CURSOR",
                                 depress=button.anchor == anchor["key"])
            op.key = anchor["key"]


_classes = (KNEADY_OT_place_mode, KNEADY_OT_place_done, KNEADY_OT_button_placement,
            KNEADY_OT_back_return, KNEADY_OT_button_anchor, KNEADY_MT_anchors)


# Viewport Edit's icon at the top left of the square around the buttons
# showing, beside Rearrange's. Greg: "Let's put "Place on surface" and
# "Rearrange" next to each other in the upper left corner of the square.
# Only one can be on at a time" (it briefly sat at the lower left before).
# It starts Place on Surface for those buttons - a menu's, if one is open -
# and is lit while it runs. A click on it again is Done, and a click on
# Rearrange's is Done with Rearrange on
ICON_KEY = "PLACE"


def _icon_lit(context, obj, region):
    return bool(MODE) and MODE.get("key") == region.as_pointer()


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    kn_pick.add_corner_icon(dict(key=ICON_KEY, corner="TOP_LEFT", operator=KNEADY_OT_place_mode.bl_idname,
                                 glyph="PIN", shown=lambda _context, _obj, _region: True, lit=_icon_lit))
    if draw_toggle not in kn_pick.PANEL_TOGGLES:
        kn_pick.PANEL_TOGGLES.append(draw_toggle)
    kn_ui.BUTTON_LOOKS.append(draw_button)
    kn_ui.REGION_BUTTONS.append(draw_region)
    rows = kn_ui.BUTTON_ROWS
    if kn_menus.draw_row in rows:
        rows[rows.index(kn_menus.draw_row)] = draw_row
    elif draw_row not in rows:
        rows.append(draw_row)


def unregister():
    rows = kn_ui.BUTTON_ROWS
    if draw_row in rows:
        rows[rows.index(draw_row)] = kn_menus.draw_row
    for hooks, fn in ((kn_ui.REGION_BUTTONS, draw_region), (kn_ui.BUTTON_LOOKS, draw_button)):
        if fn in hooks:
            hooks.remove(fn)
    kn_pick.remove_corner_icon(ICON_KEY)
    if draw_toggle in kn_pick.PANEL_TOGGLES:
        kn_pick.PANEL_TOGGLES.remove(draw_toggle)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
