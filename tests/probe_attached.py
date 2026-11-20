"""Tutorials attached to an item in the file. Run it in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_attached.py

Greg asked for this: "We also need the ability for tuts to be attached to a
file". The probe attaches a tutorial to an object in the file and checks:
- at Learn, Start a Tutorial lists it under In This File, the menu opened
  by a real click;
- the editor, on that tutorial, says where it is saved and offers Save to
  Folder;
- the editor, on a folder tutorial with the object active, offers Attach to
  <object>;
- at Inform, the top of the tab shows Tutorials in This File alone, its
  menu opened by a real click.

Prints PASS or FAIL, saves screenshots in tests/output/screens, and quits."""

import importlib
import os
import shutil
import sys
import tempfile

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402


def steps():
    t, tips = rigs.module("tutorials"), rigs.module("tips")
    bpy.context.preferences.view.show_tooltips = False
    win, area, _view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                       # click the splash away
    tips._LEVEL["value"] = "LEARN"
    work = tempfile.mkdtemp(prefix="kneady_probe_attached_")
    t.set_author_folder(os.path.join(work, "mine"))
    os.makedirs(os.path.join(work, "mine"))
    t.ATTACHED_CACHE = os.path.join(work, "cache")
    demo = os.path.join(HERE, "tutorials", "demo")
    if os.path.join(HERE, "tutorials") not in t.FOLDERS:
        t.FOLDERS.append(os.path.join(HERE, "tutorials"))
    source = os.path.join(work, "rig_basics")
    shutil.copytree(demo, source)
    data = t.load(os.path.join(source, "tutorial.json"))
    data["title"] = "Rig Basics"
    rig = bpy.data.objects.new("Rig", None)
    bpy.context.scene.collection.objects.link(rig)
    tid, count, _size = t.attach(rig, source, data, "rig_basics")
    w.check("attached_with_its_media", count >= 1, "%d files" % count)
    layer = bpy.context.view_layer
    for obj in layer.objects:
        obj.select_set(obj == rig)
    layer.objects.active = rig
    t.show_sidebar(area, "Kneady")
    yield 0.6
    ui = next(r for r in area.regions if r.type == "UI")
    w.shot("attached_1_learn_top")
    x, y = ui.x + 60, ui.y + ui.height - 55
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)
    yield 0.4
    w.shot("attached_2_menu_with_in_this_file")
    win.event_simulate("ESC", "PRESS", x=x, y=y)
    yield 0.3
    wm = bpy.context.window_manager
    wm.kneady_tutorial_edit = True
    wm.kneady_tutorial_pick = tid
    ui.tag_redraw()
    yield 0.5
    pg = wm.kneady_tutorial
    w.check("editor_loads_the_attached_one", pg.id == tid, pg.id)
    w.shot("attached_3_editor_on_attached")
    wm.kneady_tutorial_pick = "demo"
    ui.tag_redraw()
    yield 0.5
    e = rigs.module("tutorial_edit")
    with bpy.context.temp_override(window=win, area=area, region=ui):
        w.check("attach_offered_with_an_item_active", e.KNEADY_OT_tutorial_attach.poll(bpy.context))
    w.shot("attached_4_editor_offers_attach")
    wm.kneady_tutorial_edit = False
    tips._LEVEL["value"] = "INFORM"
    ui.tag_redraw()
    yield 0.5
    w.check("inform_shows_the_files_own", t.KNEADY_PT_tutorials.poll(bpy.context))
    w.shot("attached_5_inform_top")
    x, y = ui.x + 60, ui.y + ui.height - 55
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)
    yield 0.4
    w.shot("attached_6_inform_menu")
    win.event_simulate("ESC", "PRESS", x=x, y=y)
    yield 0.3
    tips._LEVEL["value"] = "QUIET"
    w.check("quiet_shows_none", not t.KNEADY_PT_tutorials.poll(bpy.context))
    tips._LEVEL["value"] = "INFORM"
    t.ATTACHED_CACHE = None
    shutil.rmtree(work, ignore_errors=True)


w.run(steps, "probe_attached")
