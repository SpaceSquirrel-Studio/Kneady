"""Toggles and Show When's clips (tutorials/toggles), one per step, played in
turn on the Rigify arm with its Forearm region (arm_forearm). The clips
show:

- a button added, named FK and made a toggle;
- the toggle pointed at Rigify's IK_FK switch on the rig;
- FK clicked on and off on the forearm;
- Bend shown While On, and Reach While Off;
- Reach hauled in IK, FK clicked, and Bend hauled.

    python dev/clips/make.py dev/clips/toggles.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from panel import ROW, choose, click_on, one_of, search_pick, setting

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "toggles"
PRACTICE = os.path.join(FOLDER, "_scenes", "arm_forearm.blend")
WHEN = ("ALWAYS", "ON", "OFF")                      # Show's menu order


def TREE_ADD(name):
    return "kneady.tree_add" in name


def region():
    import bpy  # type: ignore
    return bpy.data.objects["Arm"].kneady.regions[0]


def forearm():
    """A spot on the forearm at rest, in the arm's own space: the middle of
    its first deform bone."""
    import bpy  # type: ignore
    bone = bpy.data.objects["Rig"].data.bones["DEF-forearm.L"]
    return tuple((bone.head_local + bone.tail_local) / 2)


def onto(c, index):
    yield from c.move(c.kneady_button("Arm", 0, index))
    yield from c.wait(0.3)


def hover_forearm(c):
    yield from c.move(c.object("Arm", forearm()))
    yield from c.wait(0.7)


def haul(c, index, dx, dy):
    yield from onto(c, index)
    x, y = c.pos
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((x + dx, y + dy), 0.8)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.6)


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Arm"], fill=0.45, at=(0.28, 0.5))          # the arm left of the sidebar
    yield 0.5


def add(c):
    yield from c.wait(0.6)
    row = yield from c.tree_row(region())
    yield from click_on(c, row, "Forearm's row", ROW)
    yield from c.wait(0.4)
    plus = yield from c.find_scrolling(TREE_ADD, xs=(0.9, 0.86, 0.93))
    yield from click_on(c, plus, "+", TREE_ADD)
    yield from c.wait(0.6)
    row = yield from c.tree_row(region().buttons[2])
    yield from c.move(row)
    yield from c.wait(0.2)
    yield from c.settle(ROW, "the new button's row")
    yield from c.rename_click()
    yield from c.wait(0.3)
    yield from c.settle(setting("name", 2), "its name, being edited")
    yield from c.type("FK")
    yield from c.wait(0.15)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.5)
    yield from one_of(c, "action", 1, 3, "Toggle", button=2)    # Drag | Toggle | Gap
    yield from c.wait(1.3)


def switch(c):
    yield from c.wait(0.5)
    # the command's header holds its Path field; the arrow left of it opens it
    test = setting("switch.data_path", 2)
    spot = yield from c.find_scrolling(test, xs=(0.5,))
    _x, y = c.must(spot, "the Path field")
    ends = yield from c.span(test, y)
    left, _right = c.must(ends, "the Path field's ends")
    yield from c.move((left - 0.9 * c.unit, y))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(0.5)
    test = setting("switch.dragged", 2)
    box = yield from c.find_scrolling(test, xs=(0.3,))
    yield from click_on(c, box, "Deform Hovered Object", test)
    yield from c.wait(0.5)
    yield from search_pick(c, "switch.target", "Target", "Rig", button=2, xs=(0.6,), enter=True)
    yield from search_pick(c, "switch.data_path", "the Path field", "IK_FK", button=2)
    yield from c.wait(1.3)


def click(c):
    yield from c.wait(0.4)
    yield from hover_forearm(c)
    yield from onto(c, 2)
    yield from c.click()                                 # FK on
    yield from c.wait(1.4)
    yield from onto(c, 2)
    yield from c.click()                                 # and off: IK again
    yield from c.wait(1.2)


def bend_on(c):
    yield from c.wait(0.5)
    row = yield from c.tree_row(region().buttons[0])
    yield from click_on(c, row, "Bend's row", ROW)
    yield from c.wait(0.4)
    yield from choose(c, "show_when", WHEN, "ON", "Show", button=0, xs=(0.4,))
    yield from search_pick(c, "when_toggle", "the toggle field", "FK", button=0, xs=(0.8,))
    yield from c.wait(1.2)


def reach_off(c):
    yield from c.wait(0.5)
    row = yield from c.tree_row(region().buttons[1])
    yield from click_on(c, row, "Reach's row", ROW)
    yield from c.wait(0.4)
    yield from choose(c, "show_when", WHEN, "OFF", "Show", button=1, xs=(0.4,))
    yield from search_pick(c, "when_toggle", "the toggle field", "FK", button=1, xs=(0.8,))
    yield from c.wait(1.2)


def try_it(c):
    yield from c.wait(0.4)
    yield from hover_forearm(c)
    yield from haul(c, 1, -60, 70)                       # Reach: the hand moves, in IK
    yield from hover_forearm(c)
    yield from onto(c, 2)
    yield from c.click()                                 # FK: Bend shows
    yield from c.wait(1.0)
    yield from haul(c, 0, 0, 120)                        # Bend: the elbow bends
    yield from c.wait(1.2)


CLIPS = {"01_add": add, "02_switch": switch, "03_click": click, "04_bend_on": bend_on, "05_reach_off": reach_off,
         "06_try": try_it}
