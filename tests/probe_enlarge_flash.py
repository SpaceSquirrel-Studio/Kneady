"""The clip enlarged under the mouse, and a new step's flash, in a window:

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_enlarge_flash.py

Greg asked: "Could the video enlarge on hover? It could overlap the text
below but maybe hovering over it doubles it's size temporarily until moused
off", and "Some kind of flash or quick fadeout/fadein effect would make it
register more".

On the demo tutorial it checks:

- the clip shows Hover to Expand (Greg: "a small overlay at the bottom of
  the video window")
- with the mouse on the clip, it does not grow at once. After ENLARGE_AFTER
  it grows to twice its size from its top-left corner, and a click on it
  still pauses
- with the mouse down on the bar under it, the clip is back to its size and
  the bar's buttons are there to press
- after Next, the panel flashes, and the flash is gone after FLASH

It prints PASS or FAIL, puts screenshots in tests/output/screens, and
quits."""

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


def at(name, view):
    """The middle of a panel part, in window pixels (as in probe_tutorial)."""
    o = rigs.module("overlay")
    win, area, _v, _r = w.view()
    with bpy.context.temp_override(window=win, area=area, region=view):
        rect = o.current_layout(bpy.context)[name]
    return int(view.x + 0.5 * (rect[0] + rect[2])), int(view.y + 0.5 * (rect[1] + rect[3]))


def press(win, view, name):
    x, y = at(name, view)
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)


def steps():
    t, o = rigs.module("tutorials"), rigs.module("overlay")
    t.FOLDERS.append(os.path.join(HERE, "tutorials"))
    t.ADVANCE_AFTER = 600.0                                  # Next pressed by hand here
    bpy.context.preferences.view.show_tooltips = False
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 1300, 800)                       # the splash away
    with bpy.context.temp_override(window=win, area=area, region=view):
        t.begin(bpy.context, "demo")
    yield 1.0
    w.check("clip_showing", o._image() is not None, "no clip loaded")

    def grown(now=None):
        with bpy.context.temp_override(window=win, area=area, region=view):
            rects = o.current_layout(bpy.context)
            return o.enlarged(rects, view.width, rigs.kneady().ui_scale(bpy.context), now=now)

    def hint():
        with bpy.context.temp_override(window=win, area=area, region=view):
            rects = o.current_layout(bpy.context)
            return o.hover_hint(rects, view.width, rigs.kneady().ui_scale(bpy.context))

    w.check("says_hover_to_expand", hint())
    w.shot("enlarge_0_hint")
    x, y = at("video", view)
    yield from w.move(win, x, y, 3)
    w.check("not_grown_at_once", o.HOVER["key"] == "video" and grown(now=o.HOVER["since"] + 0.05) is None,
            str(o.HOVER["key"]))
    yield 0.4
    big = grown()
    with bpy.context.temp_override(window=win, area=area, region=view):
        video = o.current_layout(bpy.context)["video"]
    # twice its size, or as much as the view's height allows (this window is short), from its top-left corner
    k = (big[2] - big[0]) / (video[2] - video[0]) if big is not None else 0.0
    w.check("grown_from_its_corner", big is not None and 1.5 <= k <= 2.0001
            and abs((big[3] - big[1]) - k * (video[3] - video[1])) < 1
            and abs(big[3] - video[3]) < 1 and abs(big[0] - video[0]) < 1, "%s from %s" % (big, video))
    print("INFO  grown %.2f times" % k)
    w.check("no_hint_while_grown", not hint())
    w.shot("enlarge_1_grown")
    yield from w.click(win, x, y)
    yield 0.2
    w.check("a_click_on_it_still_pauses", t.S["playing"] is False)
    yield from w.click(win, x, y)
    yield 0.2
    bx, by = at("pause", view)
    yield from w.move(win, bx, by, 3)
    yield 0.4
    w.check("off_it_back_to_its_size", grown() is None and o.HOVER["key"] == "pause", str(o.HOVER["key"]))
    w.shot("enlarge_2_back")
    # Next: the flash
    seen = []
    x, y = at("next", view)
    yield from w.move(win, x, y, 2)
    yield from w.click(win, x, y)
    for _ in range(40):
        progress = o.flash_progress()
        if progress is not None:
            seen.append(progress)
            if len(seen) == 1:
                w.shot("flash_1_during")
        elif seen:
            break
        yield 0.02
    w.check("next_flashes", seen and t.S["step"] == 1, "seen %s, step %d" % (["%.2f" % v for v in seen],
                                                                            t.S["step"]))
    yield o.FLASH + 0.2
    w.check("flash_gone_after", o.flash_progress() is None)
    w.shot("flash_2_after")
    with bpy.context.temp_override(window=win, area=area, region=view):
        t.end(bpy.context)


w.run(steps, "probe_enlarge_flash")
