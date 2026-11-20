"""What the clip scripts on the Rigify arm's Forearm region (on_item,
handles) share:

- where the forearm is, as posed;
- a spot on it clear of every button and handle, to rest the mouse on;
- the view close on it;
- its 3D handles as Kneady draws them.

This is not a tutorial's script (make.py skips it)."""

from panel import ROW, click_on, kneady


def LOOKS(name):
    """A test for Blender's name for the In Row, On Item and 3D Handle
    buttons. It also passes the icon in a button's row of the tree, which is
    further right."""
    return "kneady.button_placement" in name


def region():
    import bpy  # type: ignore
    return bpy.data.objects["Arm"].kneady.regions[0]


def forearm(along=0.5):
    """A point `along` the forearm (0 the elbow, 1 the wrist) as it is posed,
    in the rig's own space. It lies on the forearm's two deform bones (Rigify
    makes two, end to end), so it stays on the forearm however the arm is
    posed."""
    import bpy  # type: ignore
    bones = bpy.data.objects["Rig"].pose.bones
    elbow, wrist = bones["DEF-forearm.L"].head, bones["DEF-forearm.L.001"].tail
    return tuple(elbow + (wrist - elbow) * along)


def world(local):
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
    return bpy.data.objects["Rig"].matrix_world @ Vector(local)


def forearm_ring(c, along):
    """The forearm's outline on screen `along` it, as posed and shown: (left
    x, right x, middle y) of its mesh's points about that far along."""
    import bpy  # type: ignore
    from bpy_extras import view3d_utils  # type: ignore
    arm = bpy.data.objects["Arm"]
    bones = bpy.data.objects["Rig"].pose.bones
    elbow, wrist = world(bones["DEF-forearm.L"].head), world(bones["DEF-forearm.L.001"].tail)
    axis = wrist - elbow
    view, rv3d = c.region(), c.area().spaces.active.region_3d
    depsgraph = bpy.context.evaluated_depsgraph_get()
    shown = arm.evaluated_get(depsgraph)
    me = shown.to_mesh()
    near = [(abs((w - elbow).dot(axis) / axis.length_squared - along), w)
            for w in (arm.matrix_world @ v.co for v in me.vertices)]
    shown.to_mesh_clear()
    pts = []
    for band in (0.04, 0.08, 0.12, 0.2):                # its rings are sparse: widen until some are in the band
        for t, w in near:
            p = view3d_utils.location_3d_to_region_2d(view, rv3d, w) if t < band else None
            if p is not None:
                pts.append((view.x + p.x, view.y + p.y))
        if pts:
            break
    return min(x for x, _y in pts), max(x for x, _y in pts), sum(y for _x, y in pts) / len(pts)


def forearm_side(c, along, inset=0.3):
    """Where on screen the forearm's left side is, `along` it - `inset` of the
    way in from its outline toward its middle."""
    left, right, y = forearm_ring(c, along)
    return (left + inset * 0.5 * (right - left), y)


def handles(c):
    """The Forearm's 3D handles as Kneady draws them now ({button index:
    placed.handles_for's dict}), and the view's corner. Their points are in
    the view's pixels; add the corner to put them in the window's."""
    import bpy  # type: ignore
    core, placed = kneady(c, "core"), kneady(c, "placed")
    obj, view = bpy.data.objects["Arm"], c.region()
    with bpy.context.temp_override(window=c.win, area=c.area(), region=view):
        circles = core.button_layout(bpy.context, obj, region())
        found = placed.handles_for(bpy.context, obj, region(), circles)
    return found, (view.x, view.y)


def _avoid(c):
    """What a resting mouse should keep clear of: each button showing, and
    the points of each 3D handle - its arrows' ends, its ring's rim."""
    points = []
    for i in range(len(region().buttons)):
        try:
            points.append(c.kneady_button("Arm", 0, i))
        except KeyError:
            pass                                         # not showing: Bend in IK, Reach in FK
    found, (ox, oy) = handles(c)
    for h in found.values():
        for part in h.get("parts", []):
            points += [(ox + p.x, oy + p.y) for p in part.get("points", [])]
        points += [(ox + p.x, oy + p.y) for p in (h.get("rim") or [])[::4]]
    return points


def clear_spot(c):
    """A spot on the Forearm region (the forearm's wrist half), as far from
    every button and handle showing as it gets. The mouse resting there
    hovers the region, and neither a tip nor the cursor covers what the step
    did."""
    avoid = _avoid(c)
    best = None
    for k in range(11):
        along = 0.47 + 0.045 * k
        left, right, y = forearm_ring(c, along)
        for frac in (0.3, 0.5, 0.7):
            spot = (left + frac * (right - left), y)
            room = min((((spot[0] - bx) ** 2 + (spot[1] - by) ** 2) ** 0.5 for bx, by in avoid), default=1e9)
            if best is None or room > best[0]:
                best = (room, spot)
    return best[1]


def rest(c, seconds=1.4):
    yield from c.move(clear_spot(c))
    yield from c.wait(seconds)


def select_row(c, owner, what):
    row = yield from c.tree_row(owner)
    yield from click_on(c, row, what, ROW)
    yield from c.wait(0.4)


def close_up(c):
    """SETUP's view, set unseen:

    - Blender's Region Overlap off, so the view's middle is where it is
      seen, left of the sidebar rather than under its edge (these are
      factory settings, so nothing is saved);
    - the view close on the forearm, whose wrist half is the Forearm region
      (16 cm: about 550 px), with the view's middle - an orbit's pivot - on
      it."""
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    bpy.context.preferences.system.use_region_overlap = False
    yield from c.sidebar("Kneady")
    yield 0.5
    centered_now(c)
    c.area().spaces.active.region_3d.view_distance = 0.5
    yield 0.5


def centered_now(c):
    """The view's middle on the forearm, where it is posed now."""
    c.area().spaces.active.region_3d.view_location = world(forearm(0.69))


def centered(c):
    """A clip's BEFORE: the view's middle on the forearm, where the clip
    before left it."""
    centered_now(c)
    yield 0.3
