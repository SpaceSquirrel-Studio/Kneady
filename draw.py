"""Kneady's drawing:

- the hovered object's regions, painted on it with the scene's depth, so a
  region shows only where it is seen (a Show Through region shows over
  everything);
- over them, in screen pixels, the hovered region's buttons: a row of
  circles in its middle, each carrying its graphic;
- in Edit Mode, the regions on the cage being painted."""

import math

import bpy  # type: ignore
import gpu  # type: ignore
import numpy as np
from gpu_extras.batch import batch_for_shader  # type: ignore
from mathutils import Vector  # type: ignore

from . import core, errors, pick, tips

AWAY = 0.4                        # the share of its opacity the hovered object's other regions get
_BATCHES = {}                      # object name -> (geometry dict, {region id: batch})
_OUTLINES = {}                     # object name -> (geometry dict, view key, {(region id, through): batch or None})
_EDIT = {}                         # object name -> {region id: batch}, Edit Faces' paint
_SHAPES = {}                       # graphic object name -> (triangles, outline lines), in -1..1
_HANDLES = []


def _flat():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def _lines():
    return gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")


def forget(name=None):
    if name is None:
        _BATCHES.clear()
        _EDIT.clear()
        _SHAPES.clear()
        _OUTLINES.clear()
    else:
        _BATCHES.pop(name, None)
        _EDIT.pop(name, None)
        _SHAPES.pop(name, None)
        _OUTLINES.pop(name, None)


def _region_batches(obj, depsgraph):
    geometry = core.region_geometry(obj, depsgraph)
    cached = _BATCHES.get(obj.name)
    if cached is not None and cached[0] is geometry:
        return cached[1]
    # the float32 arrays are passed as they are: converting them to lists
    # first took another 0.6 s on a million faces
    batches = {rid: batch_for_shader(_flat(), "TRIS", {"pos": pts})
               for rid, (pts, _lo, _hi) in geometry.items()}
    _BATCHES[obj.name] = (geometry, batches)
    return batches


class _GPUState:
    def __enter__(self):
        self.saved = (gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get())
        return self

    def __exit__(self, *_exc):
        gpu.state.blend_set(self.saved[0])
        gpu.state.depth_test_set(self.saved[1])
        gpu.state.depth_mask_set(self.saved[2])
        gpu.state.face_culling_set("NONE")


# -- In the view: the paint ----------------------------------------------------------------

def _draw_edit_tags(context):
    """In Edit Mode, draw the object's tagged faces in their regions' colors,
    the active region's stronger, so painting them is not done blind. Front
    faces only, over everything, as the cage is drawn."""
    obj = context.edit_object
    if obj is None or obj.type != "MESH" or core.newer_on(obj):
        return                      # a newer Kneady's regions: not read here (core.regions_of)
    regions = {r.id: r for r in core.own_regions(obj) if not r.whole}
    if not regions:
        return
    kn = obj.kneady
    active = kn.regions[kn.index].id if 0 <= kn.index < len(kn.regions) else None
    by_tag = _edit_batches(obj, context.evaluated_depsgraph_get(), regions)
    shader = _flat()
    with _GPUState():
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_mask_set(False)
        gpu.state.depth_test_set("NONE")
        gpu.state.face_culling_set("BACK")
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(obj.matrix_world)
            for tag, batch in by_tag.items():
                r = regions.get(tag)
                if r is None:
                    continue
                shader.uniform_float("color", (*r.color, r.opacity * (1.0 if tag == active else 0.5)))
                batch.draw(shader)


def _edit_batches(obj, depsgraph, regions):
    """Edit Faces' paint: one batch per tagged region, built once per change
    of the mesh (forget drops it). Walking the edit mesh in Python on every
    redraw took 4 s on a million faces. The faces are read as arrays from
    the evaluated edit mesh, which carries the tags, with hidden faces left
    out."""
    cached = _EDIT.get(obj.name)
    if cached is not None:
        return cached
    out = {}
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        tags = core.face_tags(me)
        if tags is not None and len(me.polygons):
            co, tris, faces = core.mesh_triangles(me)
            shown = np.ones(len(me.polygons), dtype=bool)
            hide = me.attributes.get(".hide_poly")
            if hide is not None and hide.domain == "FACE":
                hidden = np.zeros(len(me.polygons), dtype=bool)
                hide.data.foreach_get("value", hidden)
                shown = ~hidden
            tri_tags = np.where(shown, tags, 0)[faces]
            for tag in regions:
                keep = tri_tags == tag
                if keep.any():
                    pts = np.ascontiguousarray(co[tris[keep]].reshape(-1, 3))
                    out[tag] = batch_for_shader(_flat(), "TRIS", {"pos": pts})
    finally:
        ev.to_mesh_clear()
    _EDIT[obj.name] = out
    return out


def painted(obj):
    """The hovered object's regions to paint: all of them, the hovered one
    stronger - or only the kept one, while a region is kept (core.keep, as
    when pinned). Greg: "Pinning the start leaves the end highlighted which
    it shouldn't. Only the pinned cap should be highlighted"."""
    regions = core.regions_of(obj)
    kept = core.kept()
    if kept is not None and kept[0] == obj.name:
        return [r for r in regions if r.id == kept[1]]
    return regions


def _draw_view():
    context = bpy.context
    scene = context.scene
    # A view is being drawn, so what is worked out once a frame (layouts, the
    # hover, a program's anchors) is worked out afresh (core.changed).
    core.changed()
    if scene is None or not getattr(scene, "kneady_on", False) or context.region_data is None:
        return
    if context.mode == "EDIT_MESH":
        _draw_edit_tags(context)
        return
    hover = core.STATE["hover"]
    if context.mode not in core.MODES or hover is None or core.busy(context) or core.playing(context):
        return
    obj = bpy.data.objects.get(hover[0])
    regions = painted(obj) if obj is not None else []
    if not regions:
        return
    if getattr(scene, "kneady_highlight", "FILL") == "OUTLINE":
        _draw_outlines(context, obj, regions, hover)
        return
    batches = _region_batches(obj, context.evaluated_depsgraph_get())
    shader = _flat()
    with _GPUState():
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(obj.matrix_world)
            # First the regions where they are seen, then the Show Through ones
            # over everything, front faces only - such as a digit's caps,
            # hidden inside the next digit or the palm.
            for through in (False, True):
                gpu.state.depth_test_set("NONE" if through else "LESS_EQUAL")
                gpu.state.face_culling_set("BACK" if through else "NONE")
                pinned = core.STATE.get("pinned")
                for r in regions:
                    batch = batches.get(r.id)
                    # a region held for editing (core.pin) is drawn through too
                    shown_through = bool(r.show_through and not r.whole) or (
                        pinned is not None and pinned == (obj.name, r.id))
                    if batch is None or shown_through != through:
                        continue
                    on = r.id == hover[1]
                    shader.uniform_float("color", (*r.color, r.opacity * (1.0 if on else AWAY)))
                    batch.draw(shader)


def _shown_through(obj, region):
    """Drawn over everything: a Show Through region, or one held for editing
    (core.pin)."""
    pinned = core.STATE.get("pinned")
    return bool(region.show_through and not region.whole) or (pinned is not None and pinned == (obj.name, region.id))


def _view_in(obj, rv3d):
    """The view in the object's space, which a face's facing is measured
    against: (eye, None) for a perspective view, (None, the direction it
    looks) for an orthographic one."""
    inv = obj.matrix_world.inverted()
    if rv3d.is_perspective:
        return tuple(inv @ rv3d.view_matrix.inverted().translation), None
    toward = inv.to_3x3() @ (rv3d.view_matrix.inverted().to_3x3() @ Vector((0.0, 0.0, -1.0)))
    return None, tuple(toward.normalized())


SPLIT_OVERLAP = 0.5               # pixels each half of a shared line reaches across the edge, so no seam shows


def _outline_width(context):
    return getattr(context.scene, "kneady_outline_width", 6.0) * core.ui_scale(context)


_STROKE = []                       # the outline's shader, made once


def _stroke_shader():
    """Ribbons of triangles (core.stroke) in a color, their edges softened
    over a pixel by how far across the line each fragment is."""
    if not _STROKE:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant("MAT4", "mvp")
        info.push_constant("VEC4", "color")
        info.push_constant("FLOAT", "lo")
        info.push_constant("FLOAT", "hi")
        info.push_constant("BOOL", "srgbTarget")        # set by Blender, as for its own shaders
        info.vertex_in(0, "VEC3", "pos")
        info.vertex_in(1, "FLOAT", "across")
        iface = gpu.types.GPUStageInterfaceInfo("kneady_stroke")
        iface.smooth("FLOAT", "v_across")
        info.vertex_out(iface)
        info.fragment_out(0, "VEC4", "fragColor")
        info.vertex_source("void main() { gl_Position = mvp * vec4(pos, 1.0); v_across = across; }")
        # Drawn in the framebuffer's color space, as Blender's own shaders do.
        # The region colors are display colors, and a framebuffer that encodes
        # on write (srgbTarget) would make them pale.
        info.fragment_source(
            "void main() {\n"
            "  float a = clamp(min(v_across - lo, hi - v_across) + 0.5, 0.0, 1.0);\n"
            "  vec3 c = color.rgb;\n"
            "  if (srgbTarget) {\n"
            "    c = max(c, vec3(0.0));\n"
            "    c = mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));\n"
            "  }\n"
            "  fragColor = vec4(c, color.a * a);\n"
            "}\n")
        _STROKE.append((gpu.shader.create_from_info(info), iface))
    return _STROKE[0][0]


def _stroke_batch(points, pairs, matrix, size, width, inside=None):
    """A region's lines as a ribbon batch (core.stroke), with the range
    across the ribbon where it is solid: (batch, lo, hi), or None."""
    ends = {}
    for (a, b), (p, q) in zip(pairs.tolist(), points.reshape(-1, 2, 3)):
        ends[a], ends[b] = p, q
    made = core.stroke(ends, pairs, matrix, size, width, inside=inside, overlap=SPLIT_OVERLAP)
    if made is None:
        return None
    pos, across, lo, hi = made
    return batch_for_shader(_stroke_shader(), "TRIS", {"pos": pos, "across": across}), lo, hi


def _outline_batches(context, obj, regions):
    """Each region's outline (core.outline_parts) as ribbons (_stroke_batch):
    [(region, through, whole or None, half or None)]. They are made again
    only when the object's geometry, the view or the width changes, so
    hovering about costs nothing. A border shared by two of the drawn
    regions is one-sided, each region drawing the half on its own side
    (`half`); every other line is whole."""
    depsgraph = context.evaluated_depsgraph_get()
    geometry = core.region_geometry(obj, depsgraph)
    rv3d, region = context.region_data, context.region
    eye, toward = _view_in(obj, rv3d)
    width = _outline_width(context)
    matrix = rv3d.perspective_matrix @ obj.matrix_world
    key = (tuple(round(v, 6) for row in matrix for v in row), region.width, region.height, round(width, 3),
           tuple((r.id, _shown_through(obj, r)) for r in regions))
    cached = _OUTLINES.get(obj.name)
    if cached is not None and cached[0] is geometry and cached[1] == key:
        return cached[2]
    parts = [(r, _shown_through(obj, r)) for r in regions]
    parts = [(r, through, core.outline_parts(obj, depsgraph, r.id, eye=eye, toward=toward, front_only=through))
             for r, through in parts]
    borders = [p["keys"][p["border"]] for _r, _t, p in parts if p is not None]
    if borders:
        keys, uses = np.unique(np.concatenate(borders), return_counts=True)
        shared_keys = keys[uses >= 2]
    else:
        shared_keys = np.empty(0, dtype=np.int64)
    size = (region.width, region.height)
    out = []
    for r, through, p in parts:
        whole = half = None
        if p is not None:
            split = p["border"] & np.isin(p["keys"], shared_keys)
            pts = p["points"].reshape(-1, 2, 3)
            if (~split).any():
                whole = _stroke_batch(pts[~split], p["pairs"][~split], matrix, size, width)
            if split.any():
                half = _stroke_batch(pts[split], p["pairs"][split], matrix, size, width,
                                     inside=p["inside"][split])
        out.append((r, through, whole, half))
    _OUTLINES[obj.name] = (geometry, key, out)
    return out


def _draw_outlines(context, obj, regions, hover):
    """Highlight: Outline. Greg asked for "a hover-over outline instead of a
    hover over full overlay ... a clean outline of the object and regions".
    Each region's border and contour is drawn as ribbons (core.stroke) in
    its color and opacity, where it is seen: the hovered one at full
    opacity, the rest at AWAY and drawn under it, and a Show Through
    region's over everything. A border two regions share shows each one's
    color on its own side."""
    items = list(_outline_batches(context, obj, regions))
    items.sort(key=lambda item: item[0].id == hover[1])          # the hovered one last, on top
    shader = _stroke_shader()
    shader.uniform_float("mvp", context.region_data.perspective_matrix @ obj.matrix_world)
    with _GPUState():
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_mask_set(False)
        for through in (False, True):
            gpu.state.depth_test_set("NONE" if through else "LESS_EQUAL")
            for r, shown_through, whole, half in items:
                if shown_through != through:
                    continue
                on = r.id == hover[1]
                shader.uniform_float("color", (*r.color, r.opacity * (1.0 if on else AWAY)))
                for made in (whole, half):
                    if made is not None:
                        batch, lo, hi = made
                        shader.uniform_float("lo", lo)
                        shader.uniform_float("hi", hi)
                        batch.draw(shader)


# -- On the screen: the buttons and their graphics -------------------------------------------

# Each graphic is two layers, a dark edge under a bright body, each as
# (triangles, loops). The triangles fill it, and the loops - closed outlines,
# the first point repeated last - are drawn over its edges as smooth lines, so
# the edges are soft. A triangle's own edges are aliased; Greg, on the arrows:
# "The ideas behind them are good. But they are very aliased".

SHAFT = 0.15                       # an arrow's shaft, across the graphic's -1..1
HEAD = 0.46                        # its head's width
HEAD_LENGTH = 0.3                  # and length
EDGE = 0.085                       # how far the dark edge reaches past the body


class _Path:
    """A line through points, measured along its length: a point or the
    direction at any distance along it, straight on past either end."""

    def __init__(self, points):
        self.points = [Vector(p) for p in points]
        self.at = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.at.append(self.at[-1] + (b - a).length)
        self.length = self.at[-1]

    def point(self, s):
        pts, at = self.points, self.at
        if s <= 0.0:
            return pts[0] + (pts[1] - pts[0]).normalized() * s
        if s >= self.length:
            return pts[-1] + (pts[-1] - pts[-2]).normalized() * (s - self.length)
        k = next(i for i in range(1, len(at)) if at[i] >= s)
        f = (s - at[k - 1]) / max(at[k] - at[k - 1], 1e-12)
        return pts[k - 1].lerp(pts[k], f)

    def normal(self, s):
        e = self.length / 64.0
        d = (self.point(s + e) - self.point(s - e)).normalized()
        return Vector((-d.y, d.x))


def _arrow_shape(points, ends=(True, True), grow=0.0, shaft=SHAFT, head=HEAD, head_length=HEAD_LENGTH):
    """An arrow along a line through `points` (in -1..1), with a head at each
    end `ends` marks, made `grow` bigger all round for the dark edge under
    it. Returns (triangles, [loop])."""
    path = _Path(points)
    base0 = head_length + grow if ends[0] else -grow
    base1 = path.length - head_length - grow if ends[1] else path.length + grow
    half = 0.5 * shaft + grow
    steps = max(2, int(round(24 * (base1 - base0) / max(path.length, 1e-9))))
    side = [(path.point(s), path.normal(s)) for s in (base0 + (base1 - base0) * k / steps for k in range(steps + 1))]
    left = [p + n * half for p, n in side]
    right = [p - n * half for p, n in side]
    tris = []
    for k in range(steps):
        tris += [left[k], right[k], left[k + 1], right[k], right[k + 1], left[k + 1]]
    loop = list(left)
    if ends[1]:
        head_tris, (lb, ls, tip, rs, rb) = _head(path, path.length - head_length, 1.0, head, head_length, grow)
        tris += head_tris
        loop += [lb, ls, tip, rs, rb]
    loop += list(reversed(right))
    if ends[0]:
        head_tris, (lb, ls, tip, rs, rb) = _head(path, head_length, -1.0, head, head_length, grow)
        tris += head_tris
        loop += [rb, rs, tip, ls, lb]
    return tris, [loop + loop[:1]]


def _head(path, at, toward, head, length, grow):
    """An arrowhead whose base is `at` along the path, pointing toward the
    path's end (`toward` 1) or its start (-1). It is grown by `grow` all
    round: its sides and base each move out that far, and its back corners
    are beveled rather than drawn out to a spike. Returns (triangles, (left
    base, left side, tip, right side, right base))."""
    p, n = path.point(at), path.normal(at)
    d = (path.point(at + toward * 1e-3) - path.point(at - toward * 1e-3)).normalized()
    hw = 0.5 * head
    slant = math.hypot(length, hw)

    def point(u, v):
        return p + d * u + n * v

    tip = point(length + grow * slant / hw, 0.0)
    out_u, out_v = grow * hw / slant, hw + grow * length / slant
    lb, ls = point(-grow, hw), point(out_u, out_v)
    rb, rs = point(-grow, -hw), point(out_u, -out_v)
    return [tip, ls, lb, tip, lb, rb, tip, rb, rs], (lb, ls, tip, rs, rb)


SPAN = 0.86                        # a straight arrow's tips, with the dark edge just inside the graphic


def _line(vertical, bulge=0.0, steps=24):
    """A line across the graphic - up and down if vertical, else left and
    right - curved by `bulge`."""
    out = []
    for i in range(steps + 1):
        t = SPAN * (-1.0 + 2.0 * i / steps)
        b = bulge * (1.0 - (t / SPAN) ** 2)
        out.append((b, t) if vertical else (t, b))
    return out


CURVE = 0.28                       # how far a curved arrow bows


def arrow_lines(choice, button=None):
    """The arrows a set draws (props.ARROW_SETS), as [(points, ends)]. From
    Drags ("AUTO") reads `button`'s drags."""
    if choice == "AUTO":
        out = []
        if button is not None:
            for vertical, drag in ((True, button.up), (False, button.across)):
                if drag.enabled:
                    out.append((_line(vertical, CURVE if drag.kind == "ROTATE" else 0.0), (True, True)))
        return out
    if choice in ("ACROSS", "UP", "BOTH", "CURVED_ACROSS", "CURVED_UP", "CURVED_BOTH"):
        bulge = CURVE if choice.startswith("CURVED") else 0.0
        kinds = (False, True) if choice.endswith("BOTH") else (choice.endswith("UP"),)
        return [(_line(vertical, bulge), (True, True)) for vertical in kinds]
    if choice == "DIAGONAL":
        return [([(-0.66, -0.66), (0.66, 0.66)], (True, True))]
    if choice == "OUTWARD":
        return [([(0.16 * x, 0.16 * y), (0.74 * x, 0.74 * y)], (False, True))
                for x, y in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    if choice == "SPIN":
        a0, sweep, r, steps = math.radians(115.0), math.radians(-300.0), 0.56, 32
        return [([(r * math.cos(a0 + sweep * k / steps), r * math.sin(a0 + sweep * k / steps))
                  for k in range(steps + 1)], (False, True))]
    return []


def _circle_loop(radius, steps=32):
    pts = [Vector((radius * math.cos(2 * math.pi * i / steps), radius * math.sin(2 * math.pi * i / steps)))
           for i in range(steps)]
    return pts + pts[:1]


def _disc(radius, steps=32):
    loop = _circle_loop(radius, steps)
    return [p for a, b in zip(loop, loop[1:]) for p in (Vector(), a, b)], [loop]


def _ring(inner, outer, steps=32):
    tris = []
    for i in range(steps):
        a0, a1 = 2 * math.pi * i / steps, 2 * math.pi * (i + 1) / steps
        p = [Vector((r * math.cos(a), r * math.sin(a))) for r, a in ((inner, a0), (outer, a0), (outer, a1),
                                                                     (inner, a1))]
        tris += [p[0], p[1], p[2], p[0], p[2], p[3]]
    return tris, [_circle_loop(outer, steps), _circle_loop(inner, steps)]


def _join(*layers):
    tris, loops = [], []
    for t, lp in layers:
        tris += t
        loops += lp
    return tris, loops


def switch_glyph(on):
    """A toggle's default graphic, (edge, body) layers: a ring, with a dot in
    it while on."""
    edge, body = _ring(0.42, 0.78), _ring(0.5, 0.7)
    if on:
        edge, body = _join(edge, _disc(0.34)), _join(body, _disc(0.26))
    return edge, body


def arrows(button, lit=False):
    """A button's Arrows graphic, as (edge, body) layers: the set it chose
    (button.arrows), or, for From Drags, an arrow for each direction it
    drives, curved where it turns something. A toggle gets its ring instead
    (switch_glyph), `lit` while on."""
    if button.action == "TOGGLE":
        return switch_glyph(lit)
    choice = getattr(button, "arrows", "AUTO")
    lines = arrow_lines(choice, button)
    # Outward's four short arrows a little slighter, so they fit
    small = dict(head=0.4, head_length=0.24) if choice == "OUTWARD" else {}
    edge = _join(*(_arrow_shape(p, ends, EDGE, **small) for p, ends in lines))
    body = _join(*(_arrow_shape(p, ends, 0.0, **small) for p, ends in lines))
    return edge, body


def shape(obj):
    """A mesh object as a flat graphic: its faces and outline in (u, v) from
    -1 to 1, on the plane it was modeled in (its thinnest axis dropped)."""
    cached = _SHAPES.get(obj.name)
    if cached is not None:
        return cached
    me = obj.data
    if not len(me.vertices):
        return None
    co = np.empty(3 * len(me.vertices), dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(0), co.max(0)
    extent = hi - lo
    keep = [i for i in range(3) if i != int(np.argmin(extent))]
    uv = (co[:, keep] - 0.5 * (lo + hi)[keep]) / max(float(extent[keep].max()) * 0.5, 1e-9)
    me.calc_loop_triangles()
    tris = np.empty(3 * len(me.loop_triangles), dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tris)
    count = {}
    for p in me.polygons:
        for key in p.edge_keys:
            count[key] = count.get(key, 0) + 1
    edges = [k for k, n in count.items() if n == 1] if me.polygons else [tuple(e.vertices) for e in me.edges]
    lines = [tuple(uv[i]) for key in edges for i in key]
    out = ([tuple(p) for p in uv[tris]], lines)
    _SHAPES[obj.name] = out
    return out


def _to_screen(points, center, size):
    return [(center.x + p[0] * size, center.y + p[1] * size) for p in points]


def _brighter(color):
    return tuple(min(c + 0.25, 1.0) for c in color)


def _draw_lines(points, rgba, width):
    if not points:
        return
    shader = _lines()
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", rgba)
    batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)


def _draw_smooth_lines(points, colors, width):
    """Lines with a color at each point, blended along them."""
    if not points:
        return
    shader = gpu.shader.from_builtin("POLYLINE_SMOOTH_COLOR")
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", width)
    batch_for_shader(shader, "LINES", {"pos": points, "color": colors}).draw(shader)


_IMAGE = []                        # the image shader, made once


def image_shader():
    """A shader that draws an image's colors as the screen shows them.

    gpu.texture.from_image hands over scene-linear colors. Blender's IMAGE
    shader drew them unconverted: right in 4.2, but too dark in 5.x (a
    clip's 40, 106, 205 showed as 13, 42, 154), and 4.2 has no converting
    shader of its own. This one encodes to sRGB unless the framebuffer does
    so as it writes (srgbTarget, which Blender sets), so it is right in
    both."""
    if not _IMAGE:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant("MAT4", "ModelViewProjectionMatrix")
        info.push_constant("BOOL", "srgbTarget")
        info.sampler(0, "FLOAT_2D", "image")
        info.vertex_in(0, "VEC2", "pos")
        info.vertex_in(1, "VEC2", "texCoord")
        iface = gpu.types.GPUStageInterfaceInfo("kneady_image")
        iface.smooth("VEC2", "uv")
        info.vertex_out(iface)
        info.fragment_out(0, "VEC4", "fragColor")
        info.vertex_source("void main() { uv = texCoord; "
                           "gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0); }")
        info.fragment_source(
            "void main() {\n"
            "  vec4 c = texture(image, uv);\n"
            "  if (!srgbTarget) {\n"
            "    vec3 l = max(c.rgb, vec3(0.0));\n"
            "    c.rgb = mix(l * 12.92, 1.055 * pow(l, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), l));\n"
            "  }\n"
            "  fragColor = c;\n"
            "}\n")
        _IMAGE.append((gpu.shader.create_from_info(info), iface))
    return _IMAGE[0][0]


def draw_texture(texture, x0, y0, x1, y1):
    """An image's texture over the rectangle, in the screen's colors."""
    gpu.state.blend_set("ALPHA")
    shader = image_shader()
    shader.bind()
    shader.uniform_sampler("image", texture)
    batch_for_shader(shader, "TRI_FAN", {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                                         "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1))}).draw(shader)


def _draw_image(image, center, size):
    try:
        texture = gpu.texture.from_image(image)
    except Exception:                       # a missing or unreadable file: no icon, not no drawing
        errors.caught("loading the icon image %s" % image.name, trace=False)
        return
    w, h = image.size if image.size[0] and image.size[1] else (1, 1)
    sx, sy = (size, size * h / w) if w >= h else (size * w / h, size)
    draw_texture(texture, center.x - sx, center.y - sy, center.x + sx, center.y + sy)


def _draw_shape(obj, center, size, fill, outline):
    found = shape(obj)
    if found is None:
        return
    tris, lines = found
    shader = _flat()
    shader.uniform_float("color", fill)
    if tris:
        batch_for_shader(shader, "TRIS", {"pos": _to_screen(tris, center, size)}).draw(shader)
    line = outline if tris else fill
    if line is not None:
        _draw_lines(_to_screen(lines, center, size), line, 1.5 * core.ui_scale())
    elif tris:
        # no outline: its edges softened in its own color
        _draw_lines(_to_screen(lines, center, size), fill, SOFT_EDGE * core.ui_scale())


def draw_graphic(kind, image, obj, button, center, size, fill, outline=None, lit=False):
    """Draw a button's graphic centered on `center` (pixels), `size` being
    its half span: its image, its modeled shape, or arrows for its drags (a
    toggle's ring, `lit` while on). `fill` is the color of a shape or the
    arrows, and `outline` the color of their outline, or None."""
    if kind == "IMAGE" and image is not None:
        _draw_image(image, center, size)
    elif kind == "OBJECT" and obj is not None and obj.type == "MESH":
        _draw_shape(obj, center, size, fill, outline)
    elif button is not None:
        for (tris, loops), rgba in zip(arrows(button, lit), (outline, fill)):
            if tris and rgba is not None:
                _draw_smooth(tris, loops, center, size, rgba)


SOFT_EDGE = 1.0                    # pixels: the smooth line along a filled graphic's edges


def _draw_smooth(tris, loops, center, size, rgba):
    """Triangles filled, then their outline loops drawn over the edges as
    smooth lines, so the edges are soft."""
    shader = _flat()
    shader.uniform_float("color", rgba)
    batch_for_shader(shader, "TRIS", {"pos": _to_screen(tris, center, size)}).draw(shader)
    _draw_lines([p for loop in loops for a, b in zip(loop, loop[1:]) for p in _to_screen((a, b), center, size)],
                rgba, SOFT_EDGE * core.ui_scale())


def _circle(center, radius, steps=24):
    return [(center.x + radius * math.cos(2 * math.pi * i / steps), center.y + radius * math.sin(2 * math.pi * i / steps))
            for i in range(steps + 1)]


def _corner_steps(r):
    """Enough points on a rounded corner `r` pixels round to read as round."""
    return max(4, min(10, int(round(r / 1.5))))


def _rounded(x0, y0, x1, y1, r, steps=4):
    """A rounded rectangle's outline, its corners `r` round, as points
    counterclockwise, the first repeated at the end."""
    r = max(min(r, 0.5 * (x1 - x0), 0.5 * (y1 - y0)), 0.0)
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90.0), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0),
                       (x0 + r, y0 + r, 180.0)):
        for k in range(steps + 1):
            a = math.radians(a0 + 90.0 * k / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts + pts[:1]


def _fill_and_outline(outline, fill, edge, width):
    """A closed outline (first point repeated last) filled - unless `fill`
    is None - then drawn."""
    if fill is not None:
        shader = _flat()
        cx = sum(p[0] for p in outline[:-1]) / (len(outline) - 1)
        cy = sum(p[1] for p in outline[:-1]) / (len(outline) - 1)
        shader.uniform_float("color", fill)
        batch_for_shader(shader, "TRI_FAN", {"pos": [(cx, cy)] + list(outline)}).draw(shader)
    if edge is not None:
        _draw_lines([p for a, b in zip(outline, outline[1:]) for p in (a, b)], edge, width)


def _faded(rgba, faded):
    return rgba if not faded or rgba is None else (*rgba[:3], rgba[3] * FADED)


FADED = 0.35                       # how much of a faded button shows (a placed one facing away, while editing)


def _draw_buttons(context, obj, region):
    """Draw the hovered region's buttons.

    - They are a row of circles in its middle, or wherever a program places
      them (core.add_layout), drawn back to front.
    - Each carries its icon, the only graphic (Greg: "the buttons will carry
      the graphics"). A text button is its name in a rounded box.
    - Each is in its list's color (core.button_colors). The one under the
      mouse fills with it, since a drag from it runs its commands. A toggle
      that is on is filled too, and brighter under the mouse.
    - A button a program draws as a 3D handle (add_layout's "handles") is an
      arrow, with its name and mark at its tip."""
    placed, static, faded, extra = core._layout(context, obj, region)
    circles = placed + static
    if not circles:
        return
    handles = extra.get("handles", {})
    used = core.buttons_of(region)
    dark = (0.05, 0.05, 0.06, 0.95)
    radius = core.button_radius(context)
    scale = core.ui_scale(context)
    colors = core.button_colors(region)
    # Viewport Edit: the one selected in the panel, marked (pick.py)
    picked = pick.marked(region) if core.picking(context) else None
    # the handles that a drag from the one under the mouse would also move,
    # with the keys held (core.moves_with), lit as that one is
    also = core.moves_with(obj, region, core.STATE.get("button"), core.STATE.get("keys")) if handles else ()
    halo = core.handle_halo(context) if handles else 0.0
    for i, c in circles:
        b = used[i]
        color = colors[i]
        dim = i in faded
        under = i == core.STATE["button"] or (i in handles and i in also)
        # a toggle, or a drag button's own click (click_on), while it is on
        lit = core.has_click(b) and bool(core.switch_state(core.switch_channels(b, obj, region)))
        if i == picked:
            ring = (_circle(handles[i]["tip"], 0.8 * radius, 36) if i in handles
                    else _around(b, c, context, radius, PICK_GAP * scale))
            _draw_dashed(ring, PICK_MARK, 2.0 * scale, PICK_DASH * scale)
        if core.is_gap(b):
            # a gap, shown only in Viewport Edit (core._layout drops gaps
            # otherwise): its place drawn dashed, to pick and move
            _draw_dashed(_circle(c, radius, 36), (*color, 0.7), 1.5 * scale, PICK_DASH * scale)
            continue
        if i in handles and handles[i].get("hidden"):
            continue                        # hidden behind the item (placed.handle_behind)
        if i in handles:
            # behind the item, faint (placed.handle_behind)
            dim = dim or bool(handles[i].get("ghost"))
            # a handle's own color, if it has one (Greg: "we're going to need the
            # ability to color a handle"), and its own size (handles_for)
            color = core.handle_color(b, color)
            _draw_arrow(handles[i], color, under, lit, dim, handles[i].get("radius", radius), scale,
                        tuple(b.handle_fill) if b.handle_use_fill else None,
                        b.handle_opacity * core.theme_alpha(b, under),
                        b.handle_fill_alpha, tuple(b.handle_hover) if b.handle_use_hover else None,
                        falloff=b.handle_shaft_falloff, halo=halo, exact=core.themed(b))
            mark = core.badged(region, b)
            if mark:
                light = (1.0, 1.0, 1.0, 1.0) if mark > 1 else (*_brighter(color), 1.0)
                size = max(core.BADGE * radius, 3.0 * scale) * (1.4 if mark > 1 else 1.0)
                _fill_and_outline(_circle(handles[i]["tip"], size, 12), _faded(light, dim), _faded(dark, dim), scale)
            continue
        filled = under or lit
        fill = ((*_brighter(color), 1.0) if under else (*color, 1.0) if lit
                else (0.08, 0.08, 0.09, 0.8))
        edge = (1.0, 1.0, 1.0, 0.9) if under and lit else (*_brighter(color), 1.0) if filled \
            else (*color, 0.95)
        width = (2.5 if under and lit else 1.5) * scale
        ink = dark if filled else (*_brighter(color), 1.0)
        if core.boxed(b):
            half, tall, corner = core.outline_of(b, context)
            outline = _rounded(c.x - half, c.y - tall, c.x + half, c.y + tall, corner, _corner_steps(corner))
        else:
            outline = _circle(c, radius, 24 if radius < 18 else 36)
        _fill_and_outline(outline, _faded(fill, dim), _faded(edge, dim), width)
        if b.icon_type == "TEXT":
            _draw_text(b.name, c, core.text_size(context), _faded(ink, dim))
        else:
            draw_graphic(b.icon_type, b.icon_image, b.icon_object, b, c, radius * 0.78,
                         _faded(ink, dim), None if filled else _faded(dark, dim), lit)
        mark = core.badged(region, b)
        if mark:
            # A badge for more behind it (a menu it opens): a small circle on
            # its outline. Held open (mark 2), it is larger and light, with a
            # ring around the button.
            at, size = core.badge_at(b, c, context)
            light = (1.0, 1.0, 1.0, 1.0) if mark > 1 else (*_brighter(color), 1.0)
            if mark > 1:
                _fill_and_outline(_around(b, c, context, radius, 3.5 * scale), None, _faded(light, dim), 1.5 * scale)
                size *= 1.4
            _fill_and_outline(_circle(at, size, 12), _faded(light, dim), _faded(dark, dim), scale)
    named = [(i, _arrow_label_at(handles[i], used[i], context, radius, scale)) if i in handles else (i, c)
             for i, c in circles if not core.is_gap(used[i]) and not (i in handles and handles[i].get("hidden"))]
    boxes = _draw_labels(context, named, used, radius, colors, extra.get("labels"))
    # The hovered button's tip, under its name, once the mouse has rested
    # there (tips.py). None while a button is being rearranged: then it is
    # being moved, not read about.
    under = core.STATE.get("button")
    at = dict(named).get(under) if under is not None else None
    if at is None or not tips.on(context) or core.STATE.get("arranging") is not None:
        tips.gone()
    elif tips.ready(obj, region, under):
        if under in handles:
            b = handles[under]["bounds"]
            near = (b[0], b[1], b[2], b[3])
        else:
            half, tall, _corner = core.outline_of(used[under], context)
            near = (at.x - half, at.y - tall, at.x + half, at.y + tall)
        _draw_tip(context, obj, region, under, boxes.get(under), near, colors[under])


PICK_MARK = (1.0, 1.0, 1.0, 0.95)  # the dashed ring round the button selected in the panel (Viewport Edit)
PICK_GAP = 6.0                      # pixels between it and the button's outline
PICK_DASH = 4.0                     # pixels of each dash, and of each gap


ICON_ON = (0.28, 0.52, 0.92, 1.0)  # an icon whose mode is on: Blender's selected blue


def _draw_edit_icons(context, obj, region):
    """Draw Viewport Edit's icons, just out from the corners of the square
    round the hovered region's buttons (pick.py). They are small dark
    circles, white under the mouse and blue while what they turn on is on:

    - + and - at the top right;
    - Rearrange's grip of six dots (drag to reorder) at the top left;
    - a program's at the corner it asks for (pick.add_corner_icon). Place
      on Surface's pin, beside Rearrange, is an arrow down onto a
      surface."""
    icons = pick.edit_icons(context, obj, region)
    if not icons:
        return
    scale = core.ui_scale(context)
    r = pick.EDIT_SIZE * core.button_radius(context)
    for what, c in icons.items():
        glyph, on = pick.icon_look(context, obj, region, what)
        under = core.STATE.get("edit") == what
        fill = (0.92, 0.92, 0.94, 1.0) if under else ICON_ON if on else (0.08, 0.08, 0.09, 0.85)
        ink = (0.05, 0.05, 0.06, 1.0) if under else (1.0, 1.0, 1.0, 0.95)
        _fill_and_outline(_circle(c, r, 24), fill, (1.0, 1.0, 1.0, 0.9), 1.5 * scale)
        if glyph == "ARRANGE":
            dot = max(1.1 * scale, 0.12 * r)
            for dx in (-0.22, 0.22):
                for dy in (-0.4, 0.0, 0.4):
                    _fill_and_outline(_circle(Vector((c.x + dx * r, c.y + dy * r)), dot, 8), ink, None, 1.0)
            continue
        if glyph == "PIN":
            # an arrow down onto a surface
            top, tip, base, head = c.y + 0.5 * r, c.y - 0.2 * r, c.y - 0.45 * r, 0.28 * r
            _draw_lines([(c.x, top), (c.x, tip), (c.x - head, tip + head), (c.x, tip), (c.x + head, tip + head),
                         (c.x, tip), (c.x - 0.5 * r, base), (c.x + 0.5 * r, base)], ink, 2.0 * scale)
            continue
        arm = 0.5 * r
        lines = [(c.x - arm, c.y), (c.x + arm, c.y)]
        if glyph == "ADD":
            lines += [(c.x, c.y - arm), (c.x, c.y + arm)]
        _draw_lines(lines, ink, 2.0 * scale)


def _around(button, center, context, radius, gap):
    """A button's outline grown by `gap` pixels all round."""
    if core.boxed(button):
        half, tall, corner = core.outline_of(button, context)
        return _rounded(center.x - half - gap, center.y - tall - gap, center.x + half + gap, center.y + tall + gap,
                        corner + gap, _corner_steps(corner + gap))
    return _circle(center, radius + gap, 36)


def _draw_dashed(outline, rgba, width, dash):
    """An outline (points, the first repeated last) drawn as dashes `dash`
    pixels long with as much between them."""
    segments, on, left = [], True, dash
    for a, b in zip(outline, outline[1:]):
        a, b = Vector(a), Vector(b)
        length, at = (b - a).length, 0.0
        while length - at > 1e-6:
            step = min(left, length - at)
            if on:
                segments += [tuple(a.lerp(b, at / length)), tuple(a.lerp(b, (at + step) / length))]
            at += step
            left -= step
            if left <= 1e-6:
                on, left = not on, dash
    _draw_lines(segments, rgba, width)


def _arrow_label_at(handle, button, context, radius, scale):
    """Where a 3D handle's name goes: under it, as a button's name goes under
    its circle (Greg: "the label should go underneath an arrow instead of
    next to it"). Returns a stand-in center for _draw_labels, which puts a
    name under a button's circle: centered on the handle's box on screen
    and `radius` above its bottom, so the name lands just under the box."""
    x0, y0, x1, _y1 = handle["bounds"]
    return Vector((0.5 * (x0 + x1), y0 + radius))


# A 3D handle's outline widths, in pixels at an interface scale of 1: a
# head's, a box's, a ring's and a shape's, and the edges between a box's or a
# head's faces. They were thicker for a moment, then put back - Greg: "Forget
# about thicker. It's thick enough".
HANDLE_EDGE = 2.0
HANDLE_RING_EDGE = 1.5
HANDLE_FACE_EDGE = 1.2


def _colors(color, under, lit, fade, fill=None, inside=1.0, hover=None, exact=False):
    """The (body, edge) colors of a 3D handle, drawn as a button is.

    - At rest: a dark body, or its own interior color `fill` (Greg: "need
      interior color for the handles"), with an edge in the region's color.
    - Under the mouse: filled brighter and white-edged - or, with its own
      `hover` color, filled in that and edged a lighter shade.
    - While a toggle is on: filled in its color.

    `fade` is its opacity, and `inside` how much of its interior shows
    (Interior Opacity; at 0, only its edges). An edge is a shade brighter
    than its color, as a button's is over its region's paint. With `exact`
    (a theme axis color, core.themed) the edge is the color itself, as
    Blender's own gizmos draw it. Greg, of the brighter edges: "They look
    lighter colored"."""
    if under and hover is not None:
        body, edge = (*hover, 0.95 * fade), (*_brighter(hover), 0.95 * fade)
    elif under:
        body, edge = (*_brighter(fill if fill is not None else color), 0.95 * fade), (1.0, 1.0, 1.0, 0.95 * fade)
    elif lit:
        body, edge = (*color, 0.95 * fade), (*_brighter(color), fade)
    else:
        # nearly opaque: where a Quad Arrow's shafts cross, no darker square
        body = (*fill, 0.97 * fade) if fill is not None else (0.08, 0.08, 0.09, 0.97 * fade)
        edge = (*color, fade) if exact else (*_brighter(color), 0.95 * fade)
    return (*body[:3], body[3] * inside), edge


def _draw_arrow(handle, color, under=False, lit=False, dim=False, radius=None, scale=1.0, fill=None,
                opacity=1.0, inside=1.0, hover=None, falloff=0.0, halo=0.0, exact=False):
    """Draw a 3D handle (placed.handles_for) on screen: each of its arrows (a
    shaft, a cone for each head, and a head's base showing when it points
    away), or its shape's triangles, or its ring. No dot is drawn where it
    sits - Greg: "I'm not liking the circle at the root of the 3D buttons".

    - Brighter under the mouse, and filled while a toggle is on.
    - Faint behind the item, and each arrow fading as it turns to point at
      the viewer.
    - All of it at the handle's own `opacity`, with a shaft fading toward
      its root by `falloff` (placed.shaft_fade).
    - With a `halo` (pixels each side, core.handle_halo), a thin dark edge
      is drawn round every line first."""
    from . import placed
    radius = radius or core.button_radius()
    dim_k = (FADED if dim else 1.0) * opacity
    if handle.get("rim"):
        body, edge = _colors(color, under, lit, dim_k, fill, inside, hover, exact)
        _draw_ring(handle, body, edge, radius, scale, under, halo)
        return
    if handle.get("tris"):
        fade = placed.handle_alpha(handle) * dim_k
        if fade > 0.01:
            body, edge = _colors(color, under, lit, fade, fill, inside, hover, exact)
            _draw_shape_handle(handle, body, edge, scale, halo)
        return
    # Every outline first, then every body over them, so where a Quad
    # Arrow's arms cross they read as one shape with one outline, not a
    # lattice of edges.
    pieces = []                          # (outline, body, edge, darker)
    boxes = []                           # a Box's faces toward the viewer: (outline, body, edge, how lit)
    shafts = []                          # (from, to, color)
    for part in handle.get("parts", ()):
        fade = placed.handle_alpha(part) * dim_k
        if fade <= 0.01:
            continue
        body, edge = _colors(color, under, lit, fade, fill, inside, hover, exact)
        a, b = part["shaft"]
        if (b - a).length > 1e-6:
            # A shaft is one solid line in the edge's color, ARROW_SHAFT of a
            # handle radius wide, with no outline and no interior. Greg: "the
            # handle shafts solid colored, no interior in the shafts".
            shafts.append((a, b, edge, part.get("double", False)))
        for head, cap in zip(part["heads"], part["caps"] or [None] * len(part["heads"])):
            head = list(head)
            if len(head) >= 3:
                pieces.append((head + head[:1], body, edge, False))
            if cap and len(cap) >= 3:
                pieces.append((list(cap) + [cap[0]], body, edge, True))
        boxes += [(list(quad) + [quad[0]], body, edge, lit_k) for quad, lit_k in part.get("faces", ())]
    width = max(placed.ARROW_SHAFT * radius, 1.0 * scale)
    if halo > 0.0:
        # under everything: each line a little wider in a dark shade, so it
        # reads over a light surface or a wireframe
        for a, b, edge, double in shafts:
            for strip in placed.shaft_fade(a, b, falloff, double):
                pairs = list(zip(strip, strip[1:]))
                _draw_smooth_lines([p for q, r in pairs for p in (q[0], r[0])],
                                   [_halo_of(edge, k) for q, r in pairs for k in (q[1], r[1])], width + 2.0 * halo)
        for outline, _body, edge, _darker in pieces:
            _draw_lines(_segments(outline), _halo_of(edge), HANDLE_EDGE * scale + 2.0 * halo)
        for outline, _body, edge, _lit in boxes:
            _draw_lines(_segments(outline), _halo_of(edge), HANDLE_FACE_EDGE * scale + 2.0 * halo)
    for a, b, edge, double in shafts:
        if falloff <= 0.0:
            _draw_lines([a, b], edge, width)
            continue
        # Solid from the head back to where the fade begins, then fading toward
        # the root (placed.shaft_fade). Greg first asked for it "along it's
        # length, starting at middle"; the fade now begins nearer the head
        # (placed.SHAFT_FADE_FROM).
        for strip in placed.shaft_fade(a, b, falloff, double):
            pairs = list(zip(strip, strip[1:]))
            _draw_smooth_lines([p for q, r in pairs for p in (q[0], r[0])],
                               [(*edge[:3], edge[3] * k) for q, r in pairs for k in (q[1], r[1])], width)
    for outline, _body, edge, _darker in pieces:
        _fill_and_outline(outline, None, edge, HANDLE_EDGE * scale)
    for outline, body, _edge, darker in pieces:
        _fill_and_outline(outline, (*(c * 0.7 for c in body[:3]), body[3]) if darker else body, None, scale)
    # The bodies' own edges, drawn as smooth lines in their color. A filled
    # shape's edge is drawn a pixel at a time and cut its outline jaggedly -
    # Greg: "the drawing of the arrows right now looks very aliased on the
    # white border".
    for outline, body, _edge, darker in pieces:
        fill = (*(c * 0.7 for c in body[:3]), body[3]) if darker else body
        _draw_lines([p for q, r in zip(outline, outline[1:]) for p in (q, r)], fill, SOFT_EDGE * scale)
    # a Box: each face toward the viewer shaded as it faces it, its edges in
    # the handle's edge color, so it reads as a box
    for outline, body, edge, lit_k in boxes:
        shade = (*(min(1.0, c + 0.18 * lit_k) for c in body[:3]), body[3])
        _fill_and_outline(outline, shade, None, scale)
        _draw_lines([p for q, r in zip(outline, outline[1:]) for p in (q, r)], (*edge[:3], edge[3] * 0.8),
                    HANDLE_FACE_EDGE * scale)


def _halo_of(rgba, k=1.0):
    """The dark edge round a line of color `rgba` (core.HALO_ALPHA of it)."""
    return (0.0, 0.0, 0.0, core.HALO_ALPHA * rgba[3] * k)


def _segments(outline):
    """A closed outline's edges as line pairs."""
    return [p for q, r in zip(outline, outline[1:]) for p in (q, r)]


def _draw_ring(handle, body, edge, radius, scale, under=False, halo=0.0):
    """Draw a ring handle (placed.handles_for, "rim"): its rim as a band,
    dark with an edge in the region's color as a button is, and brighter
    under the mouse. There is no longer a tick showing the way it turns
    positive - Greg: "Remove the arrow from the rotate handle"."""
    from . import placed
    rim = list(handle["rim"])
    band = handle.get("band")
    if band:
        inner, outer = list(band[0]), list(band[1])
        tris = []
        for k in range(len(inner)):
            a, b, c, d = inner[k], inner[k - 1], outer[k - 1], outer[k]
            tris += [tuple(a), tuple(b), tuple(c), tuple(a), tuple(c), tuple(d)]
        if halo > 0.0:
            for side in (inner, outer):
                _draw_lines(_segments(side + side[:1]), _halo_of(edge), HANDLE_RING_EDGE * scale + 2.0 * halo)
        shader = _flat()
        shader.uniform_float("color", body)
        batch_for_shader(shader, "TRIS", {"pos": tris}).draw(shader)
        for side in (inner, outer):
            loop = side + side[:1]
            _draw_lines([p for a, b in zip(loop, loop[1:]) for p in (a, b)], edge, HANDLE_RING_EDGE * scale)
    else:
        width = placed.RING_WIDTH * radius
        if halo > 0.0:
            _draw_lines(_segments(rim), _halo_of(edge), width + 3.0 * scale + 2.0 * halo)
        _draw_lines([p for a, b in zip(rim, rim[1:]) for p in (a, b)], edge, width + 3.0 * scale)
        _draw_lines([p for a, b in zip(rim, rim[1:]) for p in (a, b)], body, max(width - 1.0 * scale, 1.0))


def _draw_shape_handle(handle, body, edge, scale, halo=0.0):
    """Draw a 3D handle shaped by a mesh object (placed.handles_for, "tris"):
    its triangles back to front in the body's color, each lit by how it
    faces the viewer, then its outline in the edge's color. A dark body is
    shaded toward lighter, a filled one within its own color."""
    base = body[:3]
    light = sum(base) / 3.0 < 0.3                   # a dark body shades up toward grey, a bright one down
    pos, colors = [], []
    for (a, b, c), lit in handle["tris"]:
        rgb = tuple(min(1.0, v + 0.25 * lit) for v in base) if light else tuple(v * (0.55 + 0.45 * lit)
                                                                                for v in base)
        pos += [tuple(a), tuple(b), tuple(c)]
        colors += [(*rgb, body[3])] * 3
    if pos:
        shader = gpu.shader.from_builtin("SMOOTH_COLOR")
        batch_for_shader(shader, "TRIS", {"pos": pos, "color": colors}).draw(shader)
    head = list(handle["parts"][0]["heads"][0]) if handle.get("parts") else []
    if len(head) >= 3:
        if halo > 0.0:
            _draw_lines(_segments(head + head[:1]), _halo_of(edge), HANDLE_RING_EDGE * scale + 2.0 * halo)
        _fill_and_outline(head + head[:1], None, edge, HANDLE_RING_EDGE * scale)


def _draw_text(text, center, size, rgba):
    """`text` centered on `center` (pixels)."""
    import blf  # type: ignore
    blf.size(0, size)
    w, _h = blf.dimensions(0, text)
    # centered on the capitals' height, so a name with descenders sits level
    cap = blf.dimensions(0, "H")[1]
    blf.color(0, *rgba)
    blf.position(0, center.x - 0.5 * w, center.y - 0.5 * cap, 0.0)
    blf.draw(0, text)


def _draw_labels(context, circles, used, radius, colors, prefer=None):
    """Draw the buttons' names under their circles (core.labels_mode): only
    the one under the mouse, or every one. Each sits on a dark box with a
    thin, slightly rounded border in the button's color, so it reads over
    whatever is behind it - Greg: "a small border, same color as the button
    with rounded corners". A text button already shows its name.

    A name that would land on another button goes beside its own button
    instead, and a column's names go above, beside and below it
    (core.label_places). Places are worked out for every button, shown or
    not, so a name stays put whichever button is hovered. `prefer` is where
    a program would have them go (add_layout's "labels"), such as an open
    menu's own button's name over its lower half, drawn over it.

    Returns {index: (x0, y0, x1, y1)}, the box of each name drawn."""
    mode = core.labels_mode(context)
    if mode == "OFF":
        return {}
    shown = [(i, c) for i, c in circles if (mode == "ALWAYS" or i == core.STATE["button"])
             and used[i].icon_type != "TEXT" and used[i].name]
    if not shown:
        return {}
    import blf  # type: ignore
    size = core.label_size(context)
    scale = core.ui_scale(context)
    blf.size(0, size)
    widths = {i: blf.dimensions(0, used[i].name)[0] for i, _c in circles
              if used[i].icon_type != "TEXT" and used[i].name}
    places = core.label_places([(i, c, *core.outline_of(used[i], context)) for i, c in circles], widths,
                               radius, context, prefer)
    drawn = {}
    for i, c in shown:
        text = used[i].name
        placed = places.get(i)
        if placed is None:
            continue
        (x0, y0, x1, y1), (x, y) = placed
        drawn[i] = (x0, y0, x1, y1)
        color = colors[i]
        under = i == core.STATE["button"]
        outline = _rounded(x0, y0, x1, y1, 3.0 * scale)
        _fill_and_outline(outline, (0.05, 0.05, 0.06, 0.8),
                          (*(_brighter(color) if under else color), 0.95), scale)
        blf.size(0, size)
        blf.color(0, 1.0, 1.0, 1.0, 1.0)
        blf.position(0, x, y, 0.0)
        blf.draw(0, text)
    return drawn


# A button's tip (tips.py): a row per key, the key in the left column and what
# it does in the right, then the author's message. Every button uses the same
# layout, so the left column is learned once and read at a glance (Greg: "users
# get used to 'That shows me what I can do'"). The tip has its own text size,
# smaller than the names' (LABEL_POINTS).
TIP_POINTS = 9.0                   # the text's size, at an interface scale of 1
TIP_LINE = 1.4                     # a row's height, in text sizes
TIP_RULE = 0.6                     # the space the line over the message takes, in rows
TIP_PAD = 4.0                      # inside the tip's box, at an interface scale of 1
TIP_GAP = 3.0                      # between the tip and its button and name
TIP_COLUMN = 10.0                  # between a key and what it does
TIP_WRAP = 200.0                   # a message wraps at least this wide
TIP_CORNER = 3.0
TIP_KEY = (0.62, 0.66, 0.72, 1.0)  # the keys: quieter than what they do
TIP_SAID = (1.0, 1.0, 1.0, 1.0)
TIP_NOTE = (0.85, 0.85, 0.87, 1.0)  # the author's message
TIP_FILL = (0.05, 0.05, 0.06, 0.92)


def _draw_tip(context, obj, region, index, label, near, color):
    """Draw button `index`'s tip (tips.tip) under its name and the button
    itself, or above them where there is no room below, but never over
    either. `label` and `near` are their boxes on screen, (x0, y0, x1, y1).
    `label` is None when the name is not drawn, and then the tip carries
    the name."""
    found, message = tips.tip(region, index, obj)
    if not found and not message:
        return
    import blf  # type: ignore
    button = core.buttons_of(region)[index]
    view = context.region
    scale = core.ui_scale(context)
    size = max(int(round(TIP_POINTS * scale)), 1)
    blf.size(0, size)
    line = round(size * TIP_LINE)
    cap = blf.dimensions(0, "H")[1]
    pad, column = TIP_PAD * scale, TIP_COLUMN * scale
    title = button.name if label is None and button.icon_type != "TEXT" and button.name else ""
    keys_w = max((blf.dimensions(0, r["label"])[0] for r in found), default=0.0)
    said_w = max((blf.dimensions(0, r["said"])[0] for r in found), default=0.0)
    width = keys_w + column + said_w if found else 0.0
    if title:
        width = max(width, blf.dimensions(0, title)[0])
    lines = tips.wrap(message, max(width, TIP_WRAP * scale), lambda t: blf.dimensions(0, t)[0]) if message else []
    width = max([width] + [blf.dimensions(0, t)[0] for t in lines])
    rule = TIP_RULE * line if lines and (found or title) else 0.0
    height = 2.0 * pad + line * ((1 if title else 0) + len(found) + len(lines)) + rule
    # below the name and the button, else above them
    boxes = [near] + ([label] if label is not None else [])
    left = label[0] if label is not None else near[0]
    low = min(b[1] for b in boxes) - TIP_GAP * scale
    high = max(b[3] for b in boxes) + TIP_GAP * scale
    w = width + 2.0 * pad
    top = low if low - height >= 4.0 * scale else high + height
    x0 = min(max(left, 4.0 * scale), max(view.width - w - 4.0 * scale, 4.0 * scale))
    _fill_and_outline(_rounded(x0, top - height, x0 + w, top, TIP_CORNER * scale), TIP_FILL, (*color, 0.95), scale)

    def text_at(text, x, k, rgba):
        y = top - pad - k * line - 0.5 * (line + cap)
        blf.color(0, *rgba)
        blf.position(0, x, y, 0.0)
        blf.draw(0, text)

    blf.size(0, size)
    k = 0.0
    if title:
        text_at(title, x0 + pad, k, TIP_SAID)
        k += 1
    for row in found:
        text_at(row["label"], x0 + pad, k, TIP_KEY)
        text_at(row["said"], x0 + pad + keys_w + column, k, TIP_SAID)
        k += 1
    if lines:
        if rule:
            y = top - pad - k * line - 0.5 * rule
            _draw_lines([(x0 + pad, y), (x0 + w - pad, y)], (*color, 0.5), scale)
            k += rule / line
        for text in lines:
            text_at(text, x0 + pad, k, TIP_NOTE)
            k += 1


def _draw_pixel():
    context = bpy.context
    scene = context.scene
    hover = core.STATE["hover"]
    # Nothing is drawn while a drag runs, a 3D arrow included - Greg: "the geo
    # buttons needs to disappear while hauling like the screenspace buttons
    # do" - nor while a program's own drag runs (core.busy: Digit's handles).
    if (scene is None or not getattr(scene, "kneady_on", False) or context.mode not in core.MODES
            or hover is None or hover[1] is None or context.region_data is None
            or core.busy(context) or core.playing(context)):
        if hover is None or core.busy(context):
            tips.gone()                 # off every button: the next one waits afresh
        return
    obj = bpy.data.objects.get(hover[0])
    region = core.find_region(obj, hover[1]) if obj is not None else None
    if region is None:
        return
    with _GPUState():
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        _draw_buttons(context, obj, region)
        if core.picking(context):
            _draw_edit_icons(context, obj, region)


def register():
    if forget not in core.FORGET_HOOKS:
        core.FORGET_HOOKS.append(forget)
    _HANDLES.append((bpy.types.SpaceView3D.draw_handler_add(_draw_view, (), "WINDOW", "POST_VIEW"), "WINDOW"))
    _HANDLES.append((bpy.types.SpaceView3D.draw_handler_add(_draw_pixel, (), "WINDOW", "POST_PIXEL"), "WINDOW"))


def unregister():
    if forget in core.FORGET_HOOKS:
        core.FORGET_HOOKS.remove(forget)
    while _HANDLES:
        handle, kind = _HANDLES.pop()
        bpy.types.SpaceView3D.draw_handler_remove(handle, kind)
