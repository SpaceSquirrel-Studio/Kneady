"""Buttons on the Item's clips (tutorials/on_item), one per step, played in
turn on the Rigify arm as The Look of Your Buttons leaves it (arm_look).
The clips show:

- Reach put On Item;
- Place on Surface, with Reach dragged to the forearm's side by the wrist;
- Reach hauled, riding the forearm;
- Behind set to Ghost Behind, and the view orbited round to see Reach
  through the arm.

    python dev/clips/make.py dev/clips/on_item.py

Recorded with Blender's Region Overlap off, so the view's middle is where it
is seen, left of the sidebar, and an orbit about the forearm keeps it there.
Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from forearm import LOOKS, centered, close_up, forearm_side, region, rest, select_row
from panel import choose, click_on, ending, one_of

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "on_item"
PRACTICE = os.path.join(FOLDER, "_scenes", "arm_look.blend")
BEHIND = ("NONE", "HIDE", "GHOST")                    # Behind's menu order


def PICK(name):
    return name.endswith("kneady_pick")


def PLACE(name):
    return "kneady.place_mode" in name


def SETUP(c):
    yield from close_up(c)


def on_item(c):
    yield from c.wait(0.6)
    yield from select_row(c, region().buttons[1], "Reach's row")
    yield from one_of(c, LOOKS, 1, 3, "On Item", xs=(0.5,))     # In Row | On Item | 3D Handle
    yield from c.wait(0.5)
    yield from rest(c, 1.8)


def place(c):
    yield from c.wait(0.5)
    spot = yield from c.find(PICK, xs=(0.5,))
    yield from click_on(c, spot, "Viewport Edit", PICK)
    yield from c.wait(0.5)
    spot = yield from c.find(PLACE, xs=(0.5,))
    yield from click_on(c, spot, "Place on Surface", PLACE)
    yield from c.wait(0.8)
    # press Reach where FK, in the column, doesn't cover it: its edge away from FK
    (rx, ry), (fx, fy) = c.kneady_button("Arm", 0, 1), c.kneady_button("Arm", 0, 2)
    away = max(((rx - fx) ** 2 + (ry - fy) ** 2) ** 0.5, 1e-6)
    reach = 0.6 * 14 * c.unit / 20                        # most of a button's radius (14 px at 20 px a unit)
    yield from c.move((rx + (rx - fx) / away * reach, ry + (ry - fy) / away * reach))
    yield from c.wait(0.4)
    yield from c.drag(forearm_side(c, 0.9, 0.15), 1.0)   # its side by the wrist, past the column
    yield from c.wait(0.6)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.6)
    spot = yield from c.find(PICK, xs=(0.5,))
    yield from click_on(c, spot, "Viewport Edit", PICK)
    yield from c.wait(0.5)
    yield from rest(c, 1.4)


def ride(c):
    yield from c.wait(0.4)
    yield from rest(c, 0.6)
    yield from c.move(c.kneady_button("Arm", 0, 1))
    yield from c.wait(0.4)
    x, y = c.pos
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((x - 70, y + 25), 1.0)             # Reach moves the IK hand, and the forearm with it
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.5)
    yield from rest(c, 1.6)                              # Reach still on the forearm


def behind(c):
    yield from c.wait(0.5)
    yield from select_row(c, region(), "Forearm's row")
    yield from choose(c, ending("regions[0].behind"), BEHIND, "GHOST", "Behind", xs=(0.6,))
    yield from c.wait(0.4)
    # orbit round until Reach's side of the forearm faces away: a
    # middle-mouse drag from empty space beside the arm
    view = c.region()
    start = (view.x + 0.75 * view.width, view.y + 0.25 * view.height)
    yield from c.move(start)
    yield from c.wait(0.3)
    yield from c.drag((start[0] - 0.45 * view.width, start[1]), 1.4, button="MIDDLEMOUSE")
    yield from c.wait(0.4)
    yield from rest(c, 1.8)


CLIPS = {"01_on_item": on_item, "02_place": place, "03_ride": ride, "04_behind": behind}
BEFORE = {"04_behind": centered}
