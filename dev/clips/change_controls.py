"""Change the Default Controls' clips (tutorials/change_controls), one per
step, played in turn where Quick Start leaves off (the cube_region scene).
The clips show Button 1 picked in the tree; Left / Right made a Move on Y;
Up / Down made a Scale on All at Speed 0.1; then a haul each way, and
Ctrl+Z twice.

    python dev/clips/make.py dev/clips/change_controls.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from panel import ROW, axis, click_on, drives, haul, open_command, setting

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "change_controls"
PRACTICE = os.path.join(FOLDER, "_scenes", "cube_region.blend")
TOP = (0.3, 0.3, 1.0)                                # on the cube's top face, its region


def region():
    import bpy  # type: ignore
    return bpy.data.objects["Cube"].kneady.regions[0]


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Cube"], fill=0.4, at=(0.3, 0.47))          # whole, left of the sidebar
    yield 0.5


def pick(c):
    yield from c.wait(0.6)
    arrow = yield from c.tree_row(region(), arrow=True)
    yield from click_on(c, arrow, "Region 1's arrow")      # Blender names nothing on the arrow itself
    yield from c.wait(0.5)
    row = yield from c.tree_row(region().buttons[0])
    yield from click_on(c, row, "Button 1's row", ROW)
    yield from c.wait(1.3)


def slide(c):
    yield from c.wait(0.4)
    yield from open_command(c, "across")
    yield from drives(c, "across.kind", "MOVE")
    yield from axis(c, "across.axis", 1, 3)              # Y: left to right in the default view
    yield from c.wait(1.3)


def grow(c):
    yield from c.wait(0.4)
    yield from open_command(c, "up")
    yield from drives(c, "up.kind", "SCALE")
    yield from axis(c, "up.axis", 3, 4)
    yield from c.wait(1.3)


def speed(c):
    yield from c.wait(0.4)
    test = setting("up.rate")
    spot = yield from c.find_scrolling(test, xs=(0.3, 0.25))
    yield from click_on(c, spot, "Speed", test)
    yield from c.wait(0.4)
    yield from c.type("0.1")
    yield from c.wait(0.2)
    yield from c.key("RET", "Enter")
    yield from c.wait(1.3)


def try_it(c):
    yield from c.wait(0.4)
    # slides right, then left past where it was; grows, then shrinks back part way
    yield from haul(c, "Cube", TOP, [(140, 0, 0.7), (-56, 0, 0.9)])
    yield from haul(c, "Cube", TOP, [(0, 150, 0.7), (0, 75, 0.9)])
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(0.5)
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(1.2)


CLIPS = {"01_pick": pick, "02_slide": slide, "03_grow": grow, "04_speed": speed, "05_try": try_it}
