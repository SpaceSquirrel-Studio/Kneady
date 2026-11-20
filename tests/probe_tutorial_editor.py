"""The top of the Kneady tab at Learn, and the tutorial editor, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_tutorial_editor.py

With Help at Learn, the probe checks:
- the Start a Tutorial menu and the pencil sit at the top of the tab, under
  the Tutorials panel's header;
- real clicks on that header fold the panel away and open it again. Greg
  asked for this: "I need to be able to minimize the Kneady tutorial panel
  ... so that I can record the Kneady panel";
- the menu opens on a real click;
- then Edit mode on Getting Started (made in a folder of the probe's own),
  with a second screenshot of the step's sections open.

Prints PASS or FAIL, saves screenshots in tests/output/screens, and quits."""

import importlib
import os
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
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                       # click the splash away
    tips._LEVEL["value"] = "LEARN"
    folder = tempfile.mkdtemp(prefix="kneady_probe_authored_")
    if os.path.join(HERE, "tutorials") not in t.FOLDERS:     # Getting Started: the tests' own tutorial
        t.FOLDERS.append(os.path.join(HERE, "tutorials"))
    t.set_author_folder(folder)
    t.show_sidebar(area, "Kneady")
    yield 0.6
    ui = next(r for r in area.regions if r.type == "UI")
    w.check("kneady_tab_open", ui.active_panel_category == "Kneady", ui.active_panel_category)
    w.shot("editor_1_learn_top")
    # A click on the Tutorials header folds it (its draw is not called), and
    # a second click opens it again
    drawn = []
    was_draw = t.draw
    t.draw = lambda layout, context: drawn.append(1) or was_draw(layout, context)
    try:
        x, y = ui.x + 60, ui.y + ui.height - 22
        yield from w.move(win, x, y, 2)
        yield from w.click(win, x, y)
        yield 0.4
        drawn.clear()
        ui.tag_redraw()
        yield 0.4
        w.check("header_folds_the_tutorials", not drawn, "drawn %d times folded" % len(drawn))
        w.shot("editor_1b_folded")
        yield from w.click(win, x, y)
        yield 0.4
        drawn.clear()
        ui.tag_redraw()
        yield 0.4
        w.check("header_opens_them_again", drawn, "never drawn")
    finally:
        t.draw = was_draw
    # Open the menu by a real click on its button, which is under the header
    x, y = ui.x + 60, ui.y + ui.height - 55
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)
    yield 0.4
    w.shot("editor_2_menu_open")
    win.event_simulate("ESC", "PRESS", x=x, y=y)
    yield 0.3
    wm = bpy.context.window_manager
    wm.kneady_tutorial_edit = True
    wm.kneady_tutorial_pick = "getting_started"
    ui.tag_redraw()
    yield 0.4
    pg = wm.kneady_tutorial
    w.check("editor_loads_the_tutorial", pg.id == "getting_started" and len(pg.steps) == 5,
            "%s, %d steps" % (pg.id, len(pg.steps)))
    w.check("panel_previews_what_is_edited", t.previewing() and t.S["id"] == "getting_started",
            "previewing %s, id %s" % (t.previewing(), t.S["id"]))
    w.shot("editor_3_editing")
    pg.show_about = False
    pg.step_index = 2
    step = pg.steps[2]
    step.show_text = step.show_media = step.show_checks = step.show_start = True
    step.media[0].open = True
    ui.tag_redraw()
    yield 0.5
    w.check("panel_follows_the_step_selected", t.S["step"] == 2, "panel at step %d" % t.S["step"])
    step.title = "Bend the elbow, edited"
    step.text[0].text = "This paragraph was typed in the N-panel a moment ago."
    yield 0.5
    w.check("panel_shows_an_edit_at_once", t.step()["title"] == "Bend the elbow, edited"
            and t.step()["text"][0].startswith("This paragraph was typed"), t.step()["title"])
    w.shot("editor_4_step_open")
    o = rigs.module("overlay")
    with bpy.context.temp_override(window=win, area=area, region=view):
        rects = o.current_layout(bpy.context)
    r = rects["next"]
    x, y = int(view.x + 0.5 * (r[0] + r[2])), int(view.y + 0.5 * (r[1] + r[3]))
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)
    yield 0.5
    w.check("list_follows_the_panels_next", pg.step_index == 3 and t.S["step"] == 3,
            "list at %d, panel at %d" % (pg.step_index, t.S["step"]))
    w.shot("editor_5_next_from_the_panel")
    pg.step_index = 2
    step.show_text = False
    step.media[0].open = True
    ui.tag_redraw()
    yield 0.5
    w.shot("editor_6_media")


w.run(steps, "probe_tutorial_editor")
