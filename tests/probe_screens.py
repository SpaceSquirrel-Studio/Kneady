"""What Kneady looks like on this computer, in a window:

    blender --factory-startup --enable-event-simulate --python tests/probe_screens.py

Takes screenshots of the hover paint and its buttons, the sidebar panel and
Edit Faces, at the normal interface size and at twice that size (as a
high-resolution screen shows it). They go to $KNEADY_SHOTS, or
tests/output/screens. Checks that hovering finds the region and that Select
Faces of <bone> selects faces. Prints the graphics card, a PASS or FAIL line
per check, and quits. The preferences it changes last only as long as this
Blender is open (factory startup saves none).
"""

import importlib
import os
import sys

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import rigs  # noqa: E402
import test_data_life  # noqa: E402
from window import check, click, hover_region, kneady_tab, move, run, shot, view  # noqa: E402


def steps():
    core = rigs.kneady()
    import gpu  # type: ignore
    platform = gpu.platform
    backend = platform.backend_type_get() if hasattr(platform, "backend_type_get") else "?"
    print("INFO  blender %s, %s, gpu: %s / %s / %s" % (bpy.app.version_string, backend, platform.vendor_get(),
                                                       platform.renderer_get(), platform.version_get()))
    bpy.context.preferences.view.show_tooltips = False    # clean screenshots; this session only
    win, area, region, _rv3d = view()
    yield from click(win, 120, 600)                       # click the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    rig, mesh, reg = test_data_life._arm()
    reg.button_count = 3
    bpy.context.scene.kneady_on = True
    with bpy.context.temp_override(window=win, area=area, region=region):
        test_data_life._select_only(mesh)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
    yield 0.5
    yield from kneady_tab()
    for scale in (1.0, 2.0):
        bpy.context.preferences.view.ui_scale = scale
        yield 0.6
        win, area, region, _rv3d = view()
        # The panel first, then the paint with the sidebar closed, since at
        # twice the size the panel would cover the mesh
        shot("panel_scale_%g" % scale)
        area.spaces.active.show_region_ui = False
        yield 0.3
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.view3d.view_selected()
        yield 0.3
        yield from move(win, 300, 300, 2)
        yield from hover_region(win, mesh, reg.id)
        hovered = core.STATE["hover"] == (mesh.name, reg.id)
        check("hover_finds_the_region_at_scale_%g" % scale, hovered, "hover: %s" % (core.STATE["hover"],))
        shot("hover_scale_%g" % scale)
        area.spaces.active.show_region_ui = True
    bpy.context.preferences.view.ui_scale = 1.0
    yield 0.5
    # Edit Faces: select the faces of the bone the region turns
    rig.data.bones.active = rig.data.bones["Lower"]
    win, area, region, _rv3d = view()
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.kneady.region_edit()
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.kneady.region_group(from_bone=True)
    yield from move(win, 300, 300, 3)
    import bmesh  # type: ignore
    bm = bmesh.from_edit_mesh(mesh.data)
    selected = sum(1 for f in bm.faces if f.select)
    check("select_faces_of_the_bone", selected > 0, "%d faces selected" % selected)
    shot("edit_faces")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.kneady.region_edit()


run(steps, "screens")
