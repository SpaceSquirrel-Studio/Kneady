"""Make a Rigify character from nothing, for the arm (dev/scenes/arm.py) and
the mannequin (dev/scenes/mannequin.py):

- Rigify's Human metarig, without its face, generated into a rig;
- a body made around the bones: the Skin modifier along the limbs, spine,
  neck and head, and box-modeled hands with fingers and a thumb;
- the body skinned to the rig's deform bones by automatic weights.

Rigify ships with Blender and everything else is made here, so the scene is
Kneady's to ship. Rigify's rig_ui.py is left out (common.save removes it),
so the scene runs no Python. The rig works without it: the IK/FK switch is
a property on upper_arm_parent.L, and its drivers are simple expressions.
"""

import addon_utils  # type: ignore
import bmesh  # type: ignore
import bpy  # type: ignore
from mathutils import Vector  # type: ignore

FINGERS = ("f_index", "f_middle", "f_ring", "f_pinky")
# the Skin modifier's radius in meters at each bone's (head, tail), by bone
# name without its side (upper_arm for upper_arm.L and upper_arm.R)
RADII = {
    "spine": (0.12, 0.13), "spine.001": (0.13, 0.12), "spine.002": (0.12, 0.14), "spine.003": (0.14, 0.07),
    "spine.004": (0.05, 0.045), "spine.005": (0.045, 0.05), "spine.006": (0.07, 0.08),
    "upper_arm": (0.055, 0.043), "forearm": (0.043, 0.03),
    "thigh": (0.085, 0.058), "shin": (0.058, 0.04), "foot": (0.04, 0.034), "toe": (0.034, 0.022),
}
HEAD_TOP = 0.015                      # how far the head's skin reaches past the top of its bone
PALM = (0.052, 0.072, 0.03, 0.026)    # wrist width, knuckle width, wrist thickness, knuckle thickness
FINGER = (0.0085, 0.0065, 0.0075, 0.006)   # half width, half thickness: at the knuckle, then at the tip
THUMB = (0.011, 0.0085, 0.0085, 0.0065)


def metarig(keep=None, offset=(0.0, 0.0, 0.0)):
    """Add Rigify's Human metarig to an empty scene, without its face (or
    breasts), and return the metarig object. When `keep` (a test on a bone
    name) is given, only the bones it passes are kept. Every bone is moved
    by -offset."""
    addon_utils.enable("rigify", default_set=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.active_object
    bpy.ops.object.mode_set(mode="EDIT")
    bones = meta.data.edit_bones
    face = bones.get("face")
    gone = set()
    if face is not None:
        gone |= {face.name} | {b.name for b in face.children_recursive}
    gone |= {b.name for b in bones if b.name.startswith("breast")}
    if keep is not None:
        gone |= {b.name for b in bones if not keep(b.name)}
    for name in gone:
        bones.remove(bones[name])
    # move every joint from where it was before any moved. A connected
    # child's head is its parent's tail, so moving bone by bone moved shared
    # joints twice
    shift = Vector(offset)
    was = {bone.name: (bone.head.copy(), bone.tail.copy()) for bone in bones}
    for bone in bones:
        bone.head, bone.tail = was[bone.name][0] - shift, was[bone.name][1] - shift
    bpy.ops.object.mode_set(mode="OBJECT")
    return meta


def joints(meta):
    """{bone name: (head, tail)} of the metarig, in world space."""
    m = meta.matrix_world
    return {b.name: (m @ b.head_local, m @ b.tail_local) for b in meta.data.bones}


def _radius(name, end, skip=()):
    base = name.split(".")[0] if not name.startswith("spine") else name
    found = None if base in skip else RADII.get(base)
    return None if found is None else found[0 if end == "head" else 1]


def skin_body(meta, name, skip=()):
    """Make a mesh object around the metarig's spine, neck, head, shoulders,
    arms (to the wrist) and legs with the Skin modifier, then apply it: one
    closed surface of quads. Bones without a radius in RADII (hands,
    fingers, heels, pelvis), and those named in `skip`, are left out."""
    pts, verts, rad, edges = joints(meta), [], [], []

    def point(p, r):
        for k, v in enumerate(verts):
            if (v - p).length < 0.012:
                rad[k] = max(rad[k], r)
                return k
        verts.append(p.copy())
        rad.append(r)
        return len(verts) - 1

    placed = {}                                       # bone name -> its head, middle and tail points
    for bone in meta.data.bones:                      # parents before children
        rh, rt = _radius(bone.name, "head", skip), _radius(bone.name, "tail", skip)
        if rh is None:
            continue
        head, tail = pts[bone.name]
        if bone.name == "spine.006":                      # the head: reaches past its bone's top
            tail = tail + (tail - head).normalized() * (HEAD_TOP - rt)
        a, b = point(head, rh), point(tail, rt)
        # a ring at the middle of every bone, so a joint bends over more of the skin
        middle = point((head + tail) / 2, (rh + rt) / 2)
        edges += [(a, middle), (middle, b)]
        placed[bone.name] = (a, middle, b)
        # a bone not connected to its parent (an upper arm, a thigh, the neck)
        # is joined to the nearest point of the nearest skinned bone above it,
        # so an arm joins the chest
        parent = bone.parent
        while parent is not None and parent.name not in placed:
            parent = parent.parent
        if parent is not None:
            near = min(placed[parent.name], key=lambda k: (verts[k] - head).length)
            if near != a and (near, a) not in edges and (a, near) not in edges:
                edges.append((near, a))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], edges, [])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    skin = obj.modifiers.new("Skin", "SKIN")
    skin.use_smooth_shade = True
    skin.branch_smoothing = 0.6
    layer = mesh.skin_vertices[0].data
    for k, item in enumerate(layer):                 # the root: the first bone's head (the pelvis)
        r = max(rad[k], 0.02)
        item.radius = (r, r)
        item.use_root = k == 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    made = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    obj.modifiers.clear()
    old = obj.data
    obj.data = made
    bpy.data.meshes.remove(old)
    made.name = name
    return obj


def _frame(pts, side):
    """The hand's axes: along (wrist to knuckles), across (pinky to index),
    up (the back of the hand), from the metarig's palm bones."""
    wrist = pts["hand" + side][0]
    knuckles = [pts["palm.0%d%s" % (k, side)][1] for k in range(1, 5)]
    along = (sum(knuckles, Vector()) / 4 - wrist).normalized()
    across = knuckles[0] - knuckles[3]
    across = (across - along * across.dot(along)).normalized()
    up = along.cross(across).normalized()
    return wrist, knuckles, along, across, up


def _ring(bm, centre, across, up, thick, xs):
    """Make a palm ring and return its vertices: a top row and a bottom row
    of points at the `xs` positions across the hand (the knuckle
    boundaries), the top row first left to right, then the bottom row back
    right to left."""
    top = [bm.verts.new(centre + across * x + up * thick / 2) for x in xs]
    bottom = [bm.verts.new(centre + across * x - up * thick / 2) for x in reversed(xs)]
    return top + bottom


def _bridge(bm, a, b):
    n = len(a)
    for k in range(n):
        bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))


def _digit(bm, corners, joints_, size):
    """Extrude a finger out of a quad of the palm, given as `corners` (the
    quad's vertices in order). It makes a ring of four vertices at each
    joint and one past the last, then a cap. Each ring is the quad's own
    shape, turned from the way the quad faces to the way its bone points
    (the shortest turn, so the rings never twist). The rings are sized from
    the knuckle (w0, t0) to the tip (w1, t1): w along the quad's first edge,
    t square to it."""
    centre = sum((v.co for v in corners), Vector()) / 4
    e1 = (corners[1].co - corners[0].co).normalized()
    facing = e1.cross(corners[3].co - corners[0].co).normalized()
    if facing.dot(joints_[1] - joints_[0]) < 0:
        facing = -facing
    e2 = facing.cross(e1).normalized()
    flat = [((v.co - centre).dot(e1), (v.co - centre).dot(e2)) for v in corners]
    sx = max(abs(x) for x, _y in flat) or 1.0
    sy = max(abs(y) for _x, y in flat) or 1.0
    w0, t0, w1, t1 = size
    spans = len(joints_) - 1
    prev = list(corners)
    for k in range(1, len(joints_) + 1):
        if k < len(joints_):
            centre_k, direction = joints_[k], (joints_[k] - joints_[k - 1]).normalized()
            f = k / spans
            w, t = w0 + (w1 - w0) * f, t0 + (t1 - t0) * f
        else:                                     # the tip, a little past the last joint
            direction = (joints_[-1] - joints_[-2]).normalized()
            centre_k = joints_[-1] + direction * t1
            w, t = w1 * 0.7, t1 * 0.7
        turn = facing.rotation_difference(direction)
        a, b = turn @ e1, turn @ e2
        ring = [bm.verts.new(centre_k + a * (x / sx * w) + b * (y / sy * t)) for x, y in flat]
        _bridge(bm, prev, ring)
        prev = ring
    bm.faces.new(prev)


def hand(bm, meta, side):
    """Box-model a hand on the metarig's hand bones for `side` (".L" or
    ".R"). The palm is three rings - wrist, middle, knuckles - and its
    knuckle end is four quads, one per finger, each extruded along its
    finger's bones. The thumb comes out of the palm's side by the wrist."""
    pts = joints(meta)
    wrist, knuckles, along, across, up = _frame(pts, side)
    # where the four fingers part across the knuckles, and how far along the
    # hand each finger's knuckle reaches
    xs_k = [(k - wrist).dot(across) for k in knuckles]
    bounds = [xs_k[0] + (xs_k[0] - xs_k[1]) / 2] + [(xs_k[i] + xs_k[i + 1]) / 2 for i in range(3)] \
        + [xs_k[3] + (xs_k[3] - xs_k[2]) / 2]
    reach = [(k - wrist).dot(along) for k in knuckles]
    centre_x = (bounds[0] + bounds[-1]) / 2
    wrist_w, knuckle_w, wrist_t, knuckle_t = PALM
    span = bounds[0] - bounds[-1]
    xs_w = [centre_x + (b - centre_x) * wrist_w / span for b in bounds]
    xs_m = [centre_x + (b - centre_x) * (wrist_w + knuckle_w) / 2 / span for b in bounds]
    xs_n = [centre_x + (b - centre_x) * knuckle_w / span for b in bounds]
    r0 = _ring(bm, wrist - along * 0.012, across, up, wrist_t, xs_w)
    mid = sum(reach) / 4 * 0.5
    r1 = _ring(bm, wrist + along * mid, across, up, (wrist_t + knuckle_t) / 2, xs_m)
    # the knuckle ring: each boundary as far along as the fingers beside it
    # reach
    reach_b = [reach[0]] + [(reach[i] + reach[i + 1]) / 2 for i in range(3)] + [reach[3]]
    top = [bm.verts.new(wrist + along * reach_b[i] + across * xs_n[i] + up * knuckle_t / 2) for i in range(5)]
    bottom = [bm.verts.new(wrist + along * reach_b[i] + across * xs_n[i] - up * knuckle_t / 2)
              for i in reversed(range(5))]
    r2 = top + bottom
    bm.faces.new(list(reversed(r0)))                 # the wrist end, inside the forearm
    _bridge(bm, r0, r1)
    _bridge(bm, r1, r2)
    # the fingers, from the knuckle end's four quads: top i, top i+1, bottom i+1, bottom i
    for i, finger in enumerate(FINGERS):
        quad = [top[i], top[i + 1], bottom[4 - (i + 1)], bottom[4 - i]]
        chain = [pts["%s.01%s" % (finger, side)][0]] + [pts["%s.0%d%s" % (finger, k, side)][1] for k in (1, 2, 3)]
        _digit(bm, quad, chain, FINGER)
    # the thumb, from the palm's side face on the index side, by the wrist
    side_face = next(f for f in bm.faces if set(f.verts) == {r0[0], r1[0], r1[-1], r0[-1]})
    corners = list(side_face.verts)
    bm.faces.remove(side_face)
    chain = [pts["thumb.01" + side][0]] + [pts["thumb.0%d%s" % (k, side)][1] for k in (1, 2, 3)]
    _digit(bm, corners, chain, THUMB)


def hands_object(meta, name, sides):
    bm = bmesh.new()
    for side in sides:
        hand(bm, meta, side)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def generate(meta, name):
    """Generate the metarig into a rig named `name`, remove the metarig, and
    return the rig."""
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = meta
    meta.select_set(True)
    bpy.ops.pose.rigify_generate()
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o is not meta)
    rig.name = name
    data = meta.data
    bpy.data.objects.remove(meta)
    bpy.data.armatures.remove(data)
    bpy.context.view_layer.update()
    return rig


def _select_only(objects, active):
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def skin_to(obj, rig, levels=1):
    """Deform `obj` by `rig`'s deform bones, with Blender's automatic
    weights, and add a Subdivision after the Armature, so the bones move the
    cage. Returns the names of the deform groups no vertex is in."""
    _select_only([obj, rig], rig)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    sub = obj.modifiers.new("Subdivision", "SUBSURF")
    sub.levels, sub.render_levels = levels, 2
    empty = [g.name for g in obj.vertex_groups if g.name.startswith("DEF-")
             and not any(g.index in [x.group for x in v.groups] for v in obj.data.vertices)]
    return empty


def join(objects, name):
    """Join the mesh objects into the first, name it `name`, and return it."""
    _select_only(objects, objects[0])
    bpy.ops.object.join()
    objects[0].name = objects[0].data.name = name
    return objects[0]
