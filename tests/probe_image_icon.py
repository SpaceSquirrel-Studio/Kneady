"""A button's Image icon is drawn in the image's own colors. Run it in a
window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_image_icon.py

Blender's IMAGE shader drew an image's scene-linear texture as it was, which
came out too dark in Blender 5.x. draw.image_shader converts it to the
screen's colors instead. The probe puts a solid orange image on a region's
first button, hovers the region, and reads the screen at the middle of the
button. Prints PASS or FAIL and quits."""

import importlib
import os
import sys

import bpy  # type: ignore
import numpy as np  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402
import test_data_life  # noqa: E402

ORANGE = (0.9, 0.45, 0.1)                  # the image's own bytes: 230, 115, 26


def steps():
    core = rigs.kneady()
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                       # click the splash away
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    _rig, mesh, region = test_data_life._arm()
    image = bpy.data.images.new("Orange", 32, 32)
    image.pixels.foreach_set(np.tile(np.array(ORANGE + (1.0,), dtype=np.float32), 32 * 32))
    button = region.buttons[0]
    button.icon_type, button.icon_image = "IMAGE", image
    bpy.context.scene.kneady_on = True
    area.spaces.active.show_region_ui = False
    yield 0.3
    yield from w.hover_region(win, mesh)
    yield 0.5
    with bpy.context.temp_override(window=win, area=area, region=view):
        circles = dict(core.button_layout(bpy.context, mesh, region))
    center = circles[0]
    w.shot("image_icon")
    shot = bpy.data.images.load(os.path.join(w.SHOTS, "image_icon.png"))
    width, height = shot.size
    px = np.empty(width * height * 4, dtype=np.float32)
    shot.pixels.foreach_get(px)
    px = px.reshape(height, width, 4)
    x, y = int(view.x - area.x + center.x), int(view.y - area.y + center.y)
    got = np.round(px[y - 1:y + 2, x - 1:x + 2, :3].reshape(-1, 3).mean(0) * 255).tolist()
    want = [round(c * 255) for c in ORANGE]
    w.check("image_icon_in_its_own_colors", all(abs(g - c) <= 8 for g, c in zip(got, want)),
            "screen %s, image %s (Blender %s)" % (got, want, bpy.app.version_string))
    print("INFO  screen %s, image %s" % (got, want))


w.run(steps, "probe_image_icon")
