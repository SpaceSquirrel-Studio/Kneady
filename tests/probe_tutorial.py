"""The tutorial's panel, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_tutorial.py

First the demo tutorial (tests/tutorials/demo). The probe checks:
- its clip plays frame by frame;
- the arrow and a dot move between clips, and a click on the clip pauses it;
- the mouse wheel over the text scrolls the text, not the view;
- a click on the panel over an object never selects the object;
- the sidebar opens on Kneady's tab with the step's field lit;
- the panel folds to a tab and back, the toolbar following;
- Next, and close.

Then Getting Started, for real:
- its practice scene opens as a copy;
- the step's start sets the view and opens the sidebar;
- a step is done, and a drag on the forearm bends the elbow;
- close takes it back to the file it came from.

Prints PASS or FAIL lines, saves screenshots in tests/output/screens, and
quits."""

import importlib
import os
import sys
import traceback

import bpy  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Vector  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402
import test_data_life  # noqa: E402

OUTPUT = os.path.join(HERE, "output")


def at(name, view):
    """A panel part's middle, in window pixels."""
    o = rigs.module("overlay")
    win, area, _v, _r = w.view()
    with bpy.context.temp_override(window=win, area=area, region=view):
        rects = o.current_layout(bpy.context)
    if name.startswith("dot:"):
        rect = rects["dots"][int(name[4:])]
    else:
        rect = rects[name]
    return int(view.x + 0.5 * (rect[0] + rect[2])), int(view.y + 0.5 * (rect[1] + rect[3]))


def press(win, view, name):
    x, y = at(name, view)
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)


def steps():
    t, o = rigs.module("tutorials"), rigs.module("overlay")
    t.FOLDERS.append(os.path.join(HERE, "tutorials"))
    # Next is pressed by hand throughout, so a finished step is kept from
    # moving on by itself. probe_advance checks that part.
    t.ADVANCE_AFTER = 600.0
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, rv3d = w.view()
    yield from w.click(win, 1300, 800)                     # click the splash away
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    rig, mesh, _region = test_data_life._arm()
    bpy.context.scene.kneady_on = True
    ov = {"window": win, "area": area, "region": view}
    # a cube under the panel, which a click on the panel must not select
    with bpy.context.temp_override(**ov):
        under = view3d_utils.region_2d_to_location_3d(view, rv3d, (140, view.height * 0.35), Vector((0, 0, 0)))
    cube = bpy.data.objects.new("Under", bpy.data.meshes.new("Under"))
    import bmesh  # type: ignore
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.5)
    bm.to_mesh(cube.data)
    bm.free()
    cube.location = under
    bpy.context.scene.collection.objects.link(cube)
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = mesh
    yield 0.3

    # -- the demo, in this file ----------------------------------------------
    toolbar_was = area.spaces.active.show_region_toolbar
    with bpy.context.temp_override(**ov):
        t.begin(bpy.context, "demo")
    yield 0.5
    w.check("toolbar_hidden_while_it_shows", not area.spaces.active.show_region_toolbar)
    w.check("demo_start_applied", bpy.context.scene.kneady_on is False)
    first = o.P["frame"]
    yield 0.6
    w.check("clip_plays", o.P["image"] is not None and o.P["frame"] != first,
            "frame %s then %s, image %s" % (first, o.P["frame"], o.P["image"]))
    w.shot("tutorial_1_demo")
    t.show_sidebar(area, "Kneady")
    yield 0.5
    yield 0.5
    ui = next(r for r in area.regions if r.type == "UI")
    w.check("sidebar_opens_on_kneady", ui.active_panel_category == "Kneady", "tab %r" % ui.active_panel_category)
    w.shot("tutorial_2_sidebar_lit")

    yield from press(win, view, "next_clip")
    w.check("arrow_moves_to_the_next_clip", t.S["clip"] == 1, "clip %d" % t.S["clip"])
    yield 0.4
    w.shot("tutorial_3_second_clip")
    props = next((a for a in win.screen.areas if a.type == "PROPERTIES"), None)
    with bpy.context.temp_override(**ov):
        bpy.context.view_layer.objects.active = mesh
    if props is not None:
        props.spaces.active.context = "OBJECT"
    yield from press(win, view, "show_me")
    yield 0.3
    w.check("show_me_opens_the_properties_tab", props is not None and props.spaces.active.context == "MODIFIER",
            "context %s" % (props.spaces.active.context if props else "no Properties editor"))
    yield from press(win, view, "dot:2")
    w.check("dot_picks_its_clip", t.S["clip"] == 2, "clip %d" % t.S["clip"])
    yield 0.4
    w.shot("tutorial_4_not_recorded")
    opened = []
    was_open = o.OPEN_URL[0]
    o.OPEN_URL[0] = opened.append                          # a probe opens no browser
    yield from press(win, view, "watch")
    o.OPEN_URL[0] = was_open
    w.check("watch_opens_the_clip_online", opened == ["https://www.youtube.com/shorts/example"], str(opened))
    yield from press(win, view, "dot:3")
    yield 0.4
    w.check("image_shows_still", t.S["clip"] == 3 and o.P["image"] is not None and o.P["still"],
            "clip %d, image %s, still %s" % (t.S["clip"], o.P["image"], o.P["still"]))
    w.shot("tutorial_4b_image")
    yield 2.2
    w.check("image_moves_on_after_its_seconds", t.S["clip"] == 0, "clip %d" % t.S["clip"])
    yield from press(win, view, "dot:0")

    distance = rv3d.view_distance
    x, y = at("text", view)
    yield from w.move(win, x, y, 2)
    for _ in range(3):
        win.event_simulate("WHEELDOWNMOUSE", "PRESS", x=x, y=y)
        yield 0.15
    w.check("wheel_scrolls_the_text", t.S["scroll"] > 0, "scroll %.1f" % t.S["scroll"])
    w.check("wheel_leaves_the_view", abs(rv3d.view_distance - distance) < 1e-6,
            "distance %.3f -> %.3f" % (distance, rv3d.view_distance))
    w.shot("tutorial_5_scrolled")

    # a click on the panel over the cube goes to the panel, not the cube
    cx, cy = int(view.x + 140), int(view.y + view.height * 0.35)
    yield from w.move(win, cx, cy, 2)
    yield from w.click(win, cx, cy)
    w.check("click_on_the_panel_selects_nothing_under_it",
            not cube.select_get() and bpy.context.view_layer.objects.active == mesh,
            "cube selected %s, active %s" % (cube.select_get(), bpy.context.view_layer.objects.active))

    yield from press(win, view, "video")
    w.check("click_on_the_clip_pauses_it", t.S["playing"] is False)
    paused = o.P["frame"]
    yield 0.5
    w.check("paused_clip_stays", o.P["frame"] == paused, "%d -> %d" % (paused, o.P["frame"]))
    yield from press(win, view, "video")

    yield from press(win, view, "fold")
    w.check("fold_hides_it_and_brings_the_toolbar", t.S["shown"] is False
            and area.spaces.active.show_region_toolbar == toolbar_was)
    w.shot("tutorial_6_folded")
    yield from press(win, view, "tab")
    w.check("tab_shows_it_again", t.S["shown"] is True and not area.spaces.active.show_region_toolbar)

    bpy.context.scene.kneady_on = True
    yield 0.6
    w.check("step_ticks_itself_off", t.done())
    w.shot("tutorial_7_done")
    yield from press(win, view, "next")
    w.check("next_goes_on", t.S["step"] == 1)
    yield 0.3
    w.shot("tutorial_8_no_clips")
    yield from press(win, view, "next")
    w.check("a_step_without_media_shows_the_shared_set", t.S["step"] == 2 and t.shares() and len(t.clips()) == 2)
    yield 1.0
    frame = o.P["frame"]
    yield from press(win, view, "next")
    yield 0.2
    w.check("the_shared_clip_plays_on_into_the_next_step", t.S["step"] == 3 and t.S["clip"] == 0
            and o.P["frame"] > frame > 1, "step %d, clip %d, frame %d -> %d" % (t.S["step"], t.S["clip"], frame,
                                                                                 o.P["frame"]))
    w.shot("tutorial_8b_shared")
    yield from press(win, view, "close")
    w.check("close_ends_it", not t.active() and area.spaces.active.show_region_toolbar == toolbar_was)

    # -- Getting Started, in its practice scene -------------------------------
    os.makedirs(OUTPUT, exist_ok=True)
    mine = os.path.join(OUTPUT, "probe_mine.blend")
    with bpy.context.temp_override(**ov):
        bpy.ops.wm.save_as_mainfile(filepath=mine)
    yield 0.3
    with bpy.context.temp_override(**ov):
        bpy.ops.kneady.tutorial_start("INVOKE_DEFAULT", tutorial="getting_started")
    for _ in range(10):
        yield 0.2
        if t.active():
            break
    w.check("practice_scene_opens", t.active() and t.S["id"] == "getting_started"
            and "Arm" in bpy.data.objects and bpy.data.filepath != mine, bpy.data.filepath)
    win, area, view, rv3d = w.view()
    yield 0.6
    w.check("start_sets_the_view", abs(rv3d.view_distance - 5.5) < 1e-3, "distance %.3f" % rv3d.view_distance)
    ui = next(r for r in area.regions if r.type == "UI")
    w.check("start_opens_the_sidebar_tab", area.spaces.active.show_region_ui and ui.active_panel_category == "Kneady",
            "tab %r" % ui.active_panel_category)
    w.shot("tutorial_9_getting_started")
    bpy.context.scene.kneady_on = True
    yield 0.6
    yield from press(win, view, "next")
    yield from press(win, view, "next")
    yield 0.3
    w.check("third_step", t.S["step"] == 2, "step %d" % t.S["step"])
    arm = bpy.data.objects["Arm"]
    x, y = w.to_window(arm.matrix_world @ Vector((0.0, 0.0, 1.6)))
    yield from w.move(win, x - 30, y, 2)
    yield from w.move(win, x, y, 4)
    win.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
    yield 0.1
    for k in range(1, 9):
        win.event_simulate("MOUSEMOVE", "NOTHING", x=x, y=y + 8 * k)
        yield 0.05
    win.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y + 64)
    yield 0.6
    turned = rigs.angle_of(bpy.data.objects["ArmRig"].pose.bones["Lower"])
    w.check("drag_bends_the_elbow_and_ticks_the_step", t.done() and turned > 5.0,
            "done %s, turned %.1f" % (t.done(), turned))
    w.shot("tutorial_10_bent")
    yield from press(win, view, "next")
    yield 0.3
    w.check("fourth_step_not_done_while_bent", t.S["step"] == 3 and not t.done())
    x, y = at("text", view)
    yield from w.move(win, x + 400, y, 2)                   # over the view, off the panel
    win.event_simulate("Z", "PRESS", x=x + 400, y=y, ctrl=True)
    yield 0.1
    win.event_simulate("Z", "RELEASE", x=x + 400, y=y, ctrl=True)
    yield 0.8
    turned = rigs.angle_of(bpy.data.objects["ArmRig"].pose.bones["Lower"])
    w.check("ctrl_z_undoes_the_drag_to_the_steps_start", turned < 0.01 and t.done() and t.active(),
            "turned %.2f, done %s, active %s" % (turned, t.done(), t.active()))
    yield from press(win, view, "close")
    for _ in range(10):
        yield 0.2
        if bpy.data.filepath == mine:
            break
    w.check("close_goes_back_to_my_file", not t.active() and bpy.data.filepath == mine
            and "Under" in bpy.data.objects, bpy.data.filepath)


def run():
    """The same as w.run, but with persistent timers, because opening the
    practice scene drops timers that are not persistent."""
    def start():
        gen = steps()

        def tick():
            try:
                return next(gen)
            except StopIteration:
                pass
            except AssertionError as exc:
                w.RESULTS.append("FAIL  probe_tutorial  %s" % exc)
            except Exception:
                w.RESULTS.append("CRASH probe_tutorial\n%s" % traceback.format_exc())
            print("\n".join(w.RESULTS))
            print("INFO  screenshots in %s" % w.SHOTS)
            sys.stdout.flush()
            w.quit_blender()
            return None

        bpy.app.timers.register(tick, first_interval=0.1, persistent=True)
        return None

    bpy.app.timers.register(start, first_interval=1.0, persistent=True)


run()
