"""Highlight: Outline. Greg asked for "a hover-over outline instead of a
hover over full overlay. I still want the overlay this is just an alternate
visualization option ... a clean outline of the object and regions".

What the outline is made of:
- a region's border edges;
- of its edges between two faces, those with one face toward the view and
  the other away (the contour), never a face's own diagonal."""

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

import rigs


def _cube():
    core = rigs.kneady()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.active_object
    top = core.new_region(cube, "Top")
    rest = core.new_region(cube, "Rest", whole=True)
    core.tag_faces(cube.data, [p.index for p in cube.data.polygons if p.normal.z > 0.5], top.id)
    core.forget(cube.name)
    return core, cube, top, rest


def _segments(points):
    """The outline's segments, each as its two ends rounded to the cube's
    corners. (The points are lifted and pulled slightly off the corners.)"""
    out = set()
    for k in range(0, len(points), 2):
        ends = tuple(sorted(tuple(int(round(c)) for c in points[i]) for i in (k, k + 1)))
        out.add(ends)
    return out


def test_outline_is_border_and_contour():
    core, cube, top, rest = _cube()
    dg = bpy.context.evaluated_depsgraph_get()
    eye = (5.0, -5.0, 5.0)                       # in front, to the right, above
    top_corners = {(x, y, 1) for x in (-1, 1) for y in (-1, 1)}
    pts = core.outline_points(cube, dg, top.id, eye=eye)
    segs = _segments(pts)
    assert len(pts) == 8 and all(set(s) <= top_corners for s in segs), \
        "the top face: its four border edges, not %s" % sorted(segs)
    pts = core.outline_points(cube, dg, rest.id, eye=eye)
    segs = _segments(pts)
    contour = {((1, 1, -1), (1, 1, 1)), ((-1, -1, -1), (-1, -1, 1)),
               ((1, -1, -1), (1, 1, -1)), ((-1, -1, -1), (1, -1, -1))}
    border = {s for s in segs if set(s) <= top_corners}
    assert len(pts) == 16 and len(border) == 4 and segs - border == contour, \
        "the rest: the top's four edges and its contour, not %s" % sorted(segs - border)
    # For a Show Through region, only the front faces' borders: the top seen
    # from below shows nothing
    assert core.outline_points(cube, dg, top.id, eye=(0.0, 0.0, -5.0), front_only=True) is None, \
        "a Show Through region's far side drew"
    # orthographic, looking straight down: the top's four border edges
    pts = core.outline_points(cube, dg, top.id, toward=(0.0, 0.0, -1.0))
    assert len(pts) == 8, "orthographic: %d points" % len(pts)


def test_outline_keeps_its_place_on_screen():
    """Each point is pulled toward the eye along its own line of sight, so it
    stays where it is on screen and only comes off the surface."""
    core, cube, top, _rest = _cube()
    dg = bpy.context.evaluated_depsgraph_get()
    eye = Vector((5.0, -5.0, 5.0))
    edges, co = core.region_edges(cube, dg)
    pairs = edges[top.id][0]
    pts = core.outline_points(cube, dg, top.id, eye=eye)
    for k, p in enumerate(pts):
        orig = Vector(co[pairs.ravel()[k]].tolist())
        a, b = (Vector(p.tolist()) - eye).normalized(), (orig - eye).normalized()
        assert a.cross(b).length < 1e-5, "a point left its line of sight by %.1e" % a.cross(b).length
        assert (Vector(p.tolist()) - eye).length < (orig - eye).length, "a point was not pulled toward the eye"


def test_highlight_setting():
    """Highlight is Fill by default. Outline Width is 6 px by default, from 2
    to 16 - Greg: "Default outline width should be 6 so the maximum should be
    higher. Minimum should be 2"."""
    scene = bpy.context.scene
    assert scene.kneady_highlight == "FILL", "Fill is not the default"
    scene.kneady_highlight = "OUTLINE"
    prop = bpy.types.Scene.bl_rna.properties["kneady_outline_width"]
    assert (prop.default, prop.hard_min, prop.hard_max) == (6.0, 2.0, 16.0), \
        "Outline Width %s, %s to %s" % (prop.default, prop.hard_min, prop.hard_max)
    assert scene.kneady_outline_width == 6.0


def test_shared_border_is_known_by_both_regions():
    """A border two regions share is the same edges, with the same numbers,
    in both regions. That is how the drawing knows to split it. Each region's
    side of the border is on its own face."""
    core, cube, top, rest = _cube()
    dg = bpy.context.evaluated_depsgraph_get()
    eye = (5.0, -5.0, 5.0)
    a = core.outline_parts(cube, dg, top.id, eye=eye)
    b = core.outline_parts(cube, dg, rest.id, eye=eye)
    shared = set(a["keys"][a["border"]].tolist()) & set(b["keys"][b["border"]].tolist())
    assert len(shared) == 4, "%d shared border edges, not the top's 4" % len(shared)
    on_a = a["inside"][a["border"]]
    on_b = b["inside"][b["border"]]
    assert (on_a[:, 2] > 0.9).all(), "the top's side of its border is not the top face"
    assert (on_b[:, 2] < 0.5).all(), "the rest's side of the top's border is not a side face"


def _perspective(near=0.1, far=100.0):
    """A 90 degree perspective projection, looking down -Z."""
    import numpy as np
    return np.array([[1.0, 0.0, 0.0, 0.0],
                     [0.0, 1.0, 0.0, 0.0],
                     [0.0, 0.0, -(far + near) / (far - near), -2.0 * far * near / (far - near)],
                     [0.0, 0.0, -1.0, 0.0]])


SIZE = (400.0, 200.0)


def _screen(m, p):
    import numpy as np
    c = np.asarray(m) @ np.r_[np.asarray(p, dtype=np.float64), 1.0]
    return (c[:2] / c[3] + 1.0) * 0.5 * np.asarray(SIZE), c[2] / c[3]


def _area(tris_px):
    a, b, c = tris_px[0::3], tris_px[1::3], tris_px[2::3]
    return float(sum(abs((b[k][0] - a[k][0]) * (c[k][1] - a[k][1]) - (c[k][0] - a[k][0]) * (b[k][1] - a[k][1]))
                     for k in range(len(a))) / 2.0)


def test_stroke_is_one_even_ribbon():
    """An outline is drawn as a ribbon of triangles (core.stroke):
    - a straight line is `width` pixels wide, plus a pixel each side for its
      soft edge. Its open ends reach on by half the width to meet what they
      end at;
    - a closed loop's corners are mitered, so its triangles cover the ribbon
      exactly once: their area is the ribbon's. Two square line ends left a
      notch at a corner, and anything drawn twice shows darker at a partial
      opacity;
    - every vertex stays at its own point's depth, in an orthographic view
      and in a perspective one."""
    import numpy as np
    core = rigs.kneady()
    w = 6.0
    for label, m, z in (("orthographic", np.eye(4), 0.0), ("perspective", _perspective(), -5.0)):
        pts = {0: np.array([-0.5, 0.0, z]), 1: np.array([0.5, 0.0, z])}
        pos, across, lo, hi = core.stroke(pts, np.array([[0, 1]]), m, SIZE, w)
        px = np.array([_screen(m, p)[0] for p in pos])
        depth = np.array([_screen(m, p)[1] for p in pos])
        a, b = _screen(m, pts[0])[0], _screen(m, pts[1])[0]
        assert (lo, hi) == (-0.5 * w, 0.5 * w), "%s: solid from %s to %s" % (label, lo, hi)
        assert abs(px[:, 1].max() - a[1] - (0.5 * w + 1.0)) < 1e-3 and abs(a[1] - px[:, 1].min() - (0.5 * w + 1.0)) < 1e-3, \
            "%s: the ribbon reaches %s px across" % (label, (px[:, 1].min() - a[1], px[:, 1].max() - a[1]))
        assert abs(px[:, 0].min() - (a[0] - 0.5 * w)) < 1e-3 and abs(px[:, 0].max() - (b[0] + 0.5 * w)) < 1e-3, \
            "%s: its ends at %s, the line's at %s" % (label, (px[:, 0].min(), px[:, 0].max()), (a[0], b[0]))
        assert np.abs(depth - _screen(m, pts[0])[1]).max() < 1e-6, "%s: the depth changed" % label
        # a closed square: mitered, each pixel once
        s = 0.3
        sq = {0: np.array([-s, -s, z]), 1: np.array([s, -s, z]), 2: np.array([s, s, z]), 3: np.array([-s, s, z])}
        pos, across, lo, hi = core.stroke(sq, np.array([[0, 1], [1, 2], [2, 3], [3, 0]]), m, SIZE, w)
        px = np.array([_screen(m, p)[0] for p in pos])
        corners = np.array([_screen(m, sq[k])[0] for k in range(4)])
        side_x, side_y = corners[1][0] - corners[0][0], corners[2][1] - corners[1][1]
        reach = 0.5 * w + 1.0
        ribbon = (side_x + 2 * reach) * (side_y + 2 * reach) - (side_x - 2 * reach) * (side_y - 2 * reach)
        assert abs(_area(px) - ribbon) < 1e-3 * ribbon, \
            "%s: the square's triangles cover %.1f px, the ribbon is %.1f" % (label, _area(px), ribbon)
        assert len(pos) == 4 * 6, "%s: %d vertices for a square" % (label, len(pos))


def test_stroke_one_sided():
    """A border two regions share is drawn one-sided. Each region's ribbon
    runs from half a pixel across the edge to half the width on its own side,
    so the line shows each color on its own side. Greg asked for this: "When
    2 colors share a line can one side of the line be one color and the
    other side be the other color"."""
    import numpy as np
    core = rigs.kneady()
    w, s = 6.0, 0.3
    m = np.eye(4)
    sq = {0: np.array([-s, -s, 0.0]), 1: np.array([s, -s, 0.0]), 2: np.array([s, s, 0.0]), 3: np.array([-s, s, 0.0])}
    pairs = np.array([[0, 1], [1, 2], [2, 3], [3, 0]])
    middle = _screen(m, (0.0, 0.0, 0.0))[0]
    half = _screen(m, (s, 0.0, 0.0))[0][0] - middle[0]
    for label, inside, toward_middle in (("inside the square", np.zeros((4, 3)), True),
                                         ("outside it", np.array([[0.0, -2.0, 0.0], [2.0, 0.0, 0.0],
                                                                  [0.0, 2.0, 0.0], [-2.0, 0.0, 0.0]]), False)):
        pos, across, lo, hi = core.stroke(sq, pairs, m, SIZE, w, inside=inside, overlap=0.5)
        assert (lo, hi) == (-0.5, 0.5 * w), "solid from %s to %s" % (lo, hi)
        px = np.array([_screen(m, p)[0] for p in pos])
        # how far inside the square's edge each vertex is (the nearer side)
        inward = half - np.max(np.abs(px - middle), axis=1)
        far = inward[across > 0] if toward_middle else -inward[across > 0]
        near = inward[across < 0] if toward_middle else -inward[across < 0]
        assert np.allclose(far, 0.5 * w + 1.0, atol=1e-3) and np.allclose(near, -1.5, atol=1e-3), \
            "%s: the ribbon runs %s to %s px from the edge" % (label, near.min(), far.max())
