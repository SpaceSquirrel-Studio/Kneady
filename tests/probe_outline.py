"""Highlight: Outline in a window, on this computer:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_outline.py

The probe hovers the test arm with Highlight set to Outline and takes
screenshots of:
- the upper region outlined in full and the rest of the arm (a whole-object
  region) dimmer, from a three-quarter view so the contour shows;
- the same with a wider line;
- Fill, as it was before, to compare;
- the region set to Show Through, drawn over a box placed in front of it.

Screenshots go to $KNEADY_SHOTS, or tests/output/screens. Prints PASS or
FAIL lines and quits.
"""

import importlib
import math
import os
import sys

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as ps  # noqa: E402
import rigs  # noqa: E402
import test_data_life  # noqa: E402


def steps():
    core = rigs.kneady()
    bpy.context.preferences.view.show_tooltips = False    # clean screenshots; this session only
    win, area, view_region, _rv3d = ps.view()
    yield from ps.click(win, 120, 600)                    # click the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    _rig, mesh, reg = test_data_life._arm()
    rest = core.new_region(mesh, "Rest", whole=True)
    rest.color = (0.2, 0.6, 1.0)
    scene = bpy.context.scene
    scene.kneady_on = True
    scene.kneady_highlight = "OUTLINE"
    with bpy.context.temp_override(window=win, area=area, region=view_region):
        test_data_life._select_only(mesh)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_orbit(angle=math.radians(35), type="ORBITRIGHT")
        bpy.ops.view3d.view_orbit(angle=math.radians(20), type="ORBITUP")
        bpy.ops.view3d.view_selected()
    for o in bpy.context.selected_objects:
        o.select_set(False)                               # no selection outline in the shots
    yield 0.5
    yield from ps.hover_region(win, mesh, reg.id)
    ps.check("hover", core.STATE["hover"] == (mesh.name, reg.id), "hover: %s" % (core.STATE["hover"],))
    from mathutils import Vector  # type: ignore
    yield from ps.move(win, *ps.to_window(mesh.matrix_world @ Vector((0.0, 0.0, 1.9))), 3)
    ps.shot("outline_hover")
    scene.kneady_outline_width = 12.0
    yield 0.4
    ps.shot("outline_wide")
    scene.kneady_outline_width = 6.0
    scene.kneady_highlight = "FILL"
    yield 0.4
    ps.shot("fill_hover")
    # the rest hovered: its outline in full, the upper region's dimmer
    scene.kneady_highlight = "OUTLINE"
    yield from ps.move(win, 300, 300, 2)
    yield from ps.hover_point(win, mesh.matrix_world @ Vector((0.0, 0.0, 0.4)))
    ps.check("hover_rest", core.STATE["hover"] == (mesh.name, rest.id), "hover: %s" % (core.STATE["hover"],))
    ps.shot("outline_rest")
    # Show Through, behind a box: drawn over it, front side only
    reg.show_through = True
    bpy.ops.mesh.primitive_cube_add(size=0.6, location=mesh.matrix_world @ Vector((0.0, -0.9, 1.6)))
    box = bpy.context.active_object
    box.select_set(False)
    core.forget()
    yield from ps.move(win, 300, 300, 2)
    yield from ps.hover_point(win, mesh.matrix_world @ Vector((0.0, 0.0, 0.4)))
    yield from ps.move(win, *ps.to_window(mesh.matrix_world @ Vector((0.0, 0.0, 1.0))), 3)
    ps.shot("outline_through")
    ps.check("drawn", True)


ps.run(steps, "outline")
