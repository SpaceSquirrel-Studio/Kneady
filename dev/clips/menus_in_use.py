"""Menus in Use's clips (tutorials/menus_in_use), one per step, played in
turn on the shape cube whose Button 1 opens a working menu
(shape_cube_menu). The clips show:

- Round and Twist hauled in the menu;
- the menu pinned with Shift+click, hauled from off the cube, and closed
  with Esc;
- Stays Open turned on, and the menu closed by a click in space;
- Twist given a menu of its own, opened inside Button 1's, and back.

    python dev/clips/make.py dev/clips/menus_in_use.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from panel import ROW, click_on, setting

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "menus_in_use"
PRACTICE = os.path.join(FOLDER, "_scenes", "shape_cube_menu.blend")
FRONT = (0.0, -1.0, 0.3)                             # on the cube's front: the whole cube is one region
SPACE = (0.2, 0.8)                                   # empty view, above the cube (window fractions)


def ADD(name):
    return "kneady.add_to_menu" in name


def region():
    import bpy  # type: ignore
    return bpy.data.objects["Cube"].kneady.regions[0]


def onto(c, index):
    """Move the cursor onto button `index`, where Kneady draws it now."""
    yield from c.move(c.kneady_button("Cube", 0, index))
    yield from c.wait(0.3)


def open_menu(c, shift=False):
    """Move onto the cube and Button 1, and click - or Shift+click, to pin."""
    yield from c.move(c.object("Cube", FRONT))
    yield from c.wait(0.6)
    yield from onto(c, 0)
    if shift:
        c.keys.append([c.now(), "Shift+Click"])
    yield from c.click(shift=shift)
    yield from c.wait(0.8)


def haul(c, index, dx, dy, back):
    """Haul button `index` out by (dx, dy), then back to `back` of the way
    out (a negative `back` goes past where it started)."""
    yield from onto(c, index)
    x, y = c.pos
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((x + dx, y + dy), 0.6)
    yield from c.move((x + dx * back, y + dy * back), 0.7)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.5)


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Cube"], fill=0.32, at=(0.3, 0.45))         # whole, left of the sidebar
    yield 0.5


def haul_in_menu(c):
    yield from c.wait(0.5)
    yield from open_menu(c)
    yield from haul(c, 1, 0, 110, 0.4)                   # Round: up, rounds
    yield from haul(c, 2, 120, 0, -0.3)                  # Twist: across, twists
    yield from c.move(c.point(*SPACE))                   # off the cube: the menu closes
    yield from c.wait(1.0)
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(0.4)
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(1.0)


def pin(c):
    yield from c.wait(0.5)
    yield from open_menu(c, shift=True)
    yield from c.move(c.point(*SPACE))                   # off the cube: pinned, the menu stays
    yield from c.wait(1.2)
    yield from haul(c, 1, 0, 90, 0.5)                    # still hauls
    yield from c.move(c.point(*SPACE))
    yield from c.wait(0.4)
    yield from c.key("ESC", "Esc")
    yield from c.wait(1.0)


def stays_open(c):
    yield from c.wait(0.5)
    arrow = yield from c.tree_row(region(), arrow=True)
    yield from click_on(c, arrow, "Region 1's arrow")      # Blender names nothing on the arrow itself
    yield from c.wait(0.4)
    row = yield from c.tree_row(region().buttons[0])
    yield from click_on(c, row, "Button 1's row", ROW)
    yield from c.wait(0.5)
    test = setting("menu_stays")
    box = yield from c.find_scrolling(test)
    yield from click_on(c, box, "Stays Open", test)
    yield from c.wait(0.6)
    yield from open_menu(c)                              # stays, with no Shift
    yield from c.move(c.point(*SPACE))
    yield from c.wait(1.0)
    yield from c.click()                                 # a click in space closes it
    yield from c.wait(1.0)


def sub_menu(c):
    yield from c.wait(0.5)
    row = yield from c.tree_row(region().buttons[2])
    yield from click_on(c, row, "Twist's row", ROW)
    yield from c.wait(0.5)
    test = setting("opens_menu", 2)
    box = yield from c.find_scrolling(test)
    yield from click_on(c, box, "Twist's Opens Menu", test)
    yield from c.wait(0.5)
    spot = yield from c.find_scrolling(ADD)
    yield from click_on(c, spot, "Add to Its Menu", ADD)
    yield from c.wait(0.8)
    yield from open_menu(c)
    yield from onto(c, 2)
    yield from c.click()                                 # Twist: opens its own menu
    yield from c.wait(1.4)
    yield from onto(c, 2)
    yield from c.click()                                 # Twist again: back a level
    yield from c.wait(1.0)
    yield from c.key("ESC", "Esc")
    yield from c.wait(1.0)


CLIPS = {"01_haul": haul_in_menu, "02_pin": pin, "03_stays_open": stays_open, "04_sub_menu": sub_menu}
