"""The clip's Pause and Loop, a clip held at its end, and the tutorial's QR
code, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_player_buttons.py

The probe plays the demo tutorial (tests/tutorials/demo) and checks:
- Pause and Loop show under the clip, and a phone button in the title row;
- Pause pauses the clip, and Play carries on from there;
- Loop, lit, plays the clip round again; off, it goes on to the next clip;
- the second clip, marked hold, stays on its last frame, and Play starts it
  over;
- the phone shows the playlist as a QR code (player_5_qr.png, to read with a
  phone), and a click on the code goes back.

Prints PASS or FAIL, saves screenshots in tests/output/screens, and quits."""

import importlib
import os
import sys

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import window as w  # noqa: E402
import rigs  # noqa: E402

LONG = 11.0                        # past the end of counting.mp4: 240 frames, 24 a second


def rects_now():
    o = rigs.module("overlay")
    win, area, view, _r = w.view()
    with bpy.context.temp_override(window=win, area=area, region=view):
        return o.current_layout(bpy.context) or {}


def press(win, view, name):
    rect = rects_now()[name]
    x, y = int(view.x + 0.5 * (rect[0] + rect[2])), int(view.y + 0.5 * (rect[1] + rect[3]))
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)


def steps():
    t, o = rigs.module("tutorials"), rigs.module("overlay")
    t.FOLDERS.append(os.path.join(HERE, "tutorials"))
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                     # click the splash away
    ov = {"window": win, "area": area, "region": view}
    with bpy.context.temp_override(**ov):
        t.begin(bpy.context, "demo")
    yield 0.6
    rects = rects_now()
    w.check("pause_and_loop_under_the_clip", "pause" in rects and "loop" in rects, str(sorted(rects)))
    w.check("phone_in_the_title_row", "phone" in rects, str(sorted(rects)))
    w.shot("player_1_buttons")

    yield from press(win, view, "pause")
    w.check("pause_pauses", t.S["playing"] is False)
    frame = o.P["frame"]
    yield 0.4
    w.check("paused_clip_stays", o.P["frame"] == frame, "%d -> %d" % (frame, o.P["frame"]))
    w.shot("player_2_paused")
    yield from press(win, view, "pause")
    w.check("play_goes_on", t.S["playing"] is True)

    yield from press(win, view, "loop")
    w.check("loop_lights", t.looping())
    o.P["t0"] -= LONG
    yield 0.4
    w.check("loop_takes_the_clip_round", t.S["clip"] == 0 and 1 <= o.P["frame"] < 60,
            "clip %d, frame %d" % (t.S["clip"], o.P["frame"]))
    w.shot("player_3_loop_lit")
    yield from press(win, view, "loop")
    w.check("loop_off", not t.looping())
    o.P["t0"] -= LONG
    yield 0.4
    w.check("loop_off_goes_on", t.S["clip"] == 1 and t.S["loop"] is None, "clip %d" % t.S["clip"])

    o.P["t0"] -= LONG
    yield 0.5
    w.check("held_on_its_last_frame", o.P["ended"] and o.P["frame"] == o.P["frames"] and t.S["clip"] == 1,
            "ended %s, frame %d of %d, clip %d" % (o.P["ended"], o.P["frame"], o.P["frames"], t.S["clip"]))
    yield 0.6
    w.check("held_stays", o.P["frame"] == o.P["frames"] and t.S["clip"] == 1)
    w.shot("player_4_held")
    yield from press(win, view, "pause")
    yield 0.3
    w.check("play_starts_it_over", not o.P["ended"] and o.P["frame"] < 30, "frame %d" % o.P["frame"])

    yield from press(win, view, "phone")
    yield 0.3
    rects = rects_now()
    w.check("phone_shows_the_qr_code", t.S["qr"] and "qr" in rects and "video" not in rects, str(sorted(rects)))
    w.shot("player_5_qr")
    yield from press(win, view, "qr")
    w.check("a_click_on_it_goes_back", t.S["qr"] is False)
    yield 0.3
    w.check("the_clip_plays_on", o.P["paused"] is None and t.S["playing"], str(o.P["paused"]))
    w.shot("player_6_back")
    with bpy.context.temp_override(**ov):
        t.end(bpy.context)


w.run(steps, "probe_player_buttons")
