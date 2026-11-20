"""Build a Menu's clips (tutorials/build_a_menu), one per step, played in
turn on the shape cube where Drive More Than Bones leaves it
(shape_cube_controls). The clips show Button 1 picked and given a menu; two
buttons added to it, named Round and Twist, and shown as text; the menu made
one color; then the menu opened on the cube and closed.

Greg picked this tutorial as the test case for scripted clips: "The test
tutorial for you to do is adding and formatting buttons on a menu". It was
made first on the old arm, then remade on the shape cube when the tutorials
took their four shared scenes.

    python dev/clips/make.py dev/clips/build_a_menu.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from panel import MENU_FIRST, MENU_STEP, ROW, click_on, setting, with_room_below

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "build_a_menu"
PRACTICE = os.path.join(FOLDER, "_scenes", "shape_cube_controls.blend")
FRONT = (0.0, -1.0, 0.3)                             # on the cube's front: the whole cube is one region
ICONS = ("ARROWS", "IMAGE", "OBJECT", "TEXT")       # the Icon menu's order


def ADD(name):
    return "kneady.add_to_menu" in name


def region():
    import bpy  # type: ignore
    return bpy.data.objects["Cube"].kneady.regions[0]


def select_row(c, index, what):
    """Click a button's row in the tree, picking the button."""
    row = yield from c.tree_row(region().buttons[index])
    yield from click_on(c, row, what, ROW)


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Cube"], fill=0.32, at=(0.3, 0.45))         # whole, left of the sidebar
    yield 0.5


def pick(c):
    yield from c.wait(0.6)
    arrow = yield from c.tree_row(region(), arrow=True)
    yield from click_on(c, arrow, "Region 1's arrow")      # Blender names nothing on the arrow itself
    yield from c.wait(0.5)
    yield from select_row(c, 0, "Button 1's row")
    yield from c.wait(1.3)


def opens_menu(c):
    yield from c.wait(0.5)
    test = setting("opens_menu")
    box = yield from c.find_scrolling(test)
    yield from click_on(c, box, "Opens Menu", test)
    yield from c.wait(1.3)


def add(c):
    yield from c.wait(0.5)
    spot = yield from c.find_scrolling(ADD)
    yield from click_on(c, spot, "Add to Its Menu", ADD)
    yield from c.wait(0.8)
    # the new button is picked now, so pick Button 1 again for the second
    yield from select_row(c, 0, "Button 1's row")
    yield from c.wait(0.5)
    spot = yield from c.find_scrolling(ADD)
    yield from click_on(c, spot, "Add to Its Menu", ADD)
    yield from c.wait(1.3)


def name(c):
    yield from c.wait(0.5)
    for index, word in ((1, "Round"), (2, "Twist")):
        row = yield from c.tree_row(region().buttons[index])
        yield from c.move(row)
        yield from c.wait(0.2)
        yield from c.settle(ROW, "button %d's row" % index)
        yield from c.rename_click()
        yield from c.wait(0.3)
        # once the name is being edited, Blender names the name field there,
        # not the list's row. Typing before then would send the letters to the
        # view as shortcuts
        yield from c.settle(setting("name", index), "button %d's name, being edited" % index)
        yield from c.type(word)
        yield from c.wait(0.15)
        yield from c.key("RET", "Enter")
        yield from c.wait(0.4)
        yield from c.settle(ROW, "button %d's row, renamed" % index)
        yield from c.wait(0.2)
    yield from c.wait(0.8)


def text_icons(c):
    yield from c.wait(0.5)
    for index in (1, 2):
        yield from select_row(c, index, "button %d's row" % index)
        yield from c.wait(0.4)
        test = setting("icon_type", index)
        box = yield from with_room_below(c, test, "the Icon dropdown", xs=(0.36, 0.3, 0.42))
        yield from click_on(c, box, "the Icon dropdown", test)
        yield from c.wait(0.45)
        below = MENU_FIRST + ICONS.index("TEXT") * MENU_STEP
        yield from c.move((box[0] - 0.6 * c.unit, box[1] - below * c.unit))
        yield from c.wait(0.2)
        yield from c.click()
        yield from c.wait(0.6)
    yield from c.wait(0.8)


def color(c):
    yield from c.wait(0.5)
    yield from select_row(c, 0, "Button 1's row")
    yield from c.wait(0.4)
    test = setting("menu_use_color")
    box = yield from c.find_scrolling(test)
    yield from click_on(c, box, "Override Color", test)
    yield from c.wait(0.5)
    swatch = yield from c.find(setting("menu_color"), along=c.must(box, "Override Color")[1])
    yield from click_on(c, swatch, "the color swatch", setting("menu_color"))
    yield from c.wait(0.6)
    # the picker opens above the swatch: a blue-violet on its wheel (measured from the swatch)
    yield from c.move((swatch[0] - 0.52 * c.unit, swatch[1] + 15.0 * c.unit))
    yield from c.wait(0.2)
    yield from c.click()
    yield from c.wait(0.7)
    # a click away, in an empty part of the view, closes it (moving the mouse
    # off it closes it for a person, but not under Blender's event simulation)
    yield from c.move(c.point(0.2, 0.8))
    yield from c.wait(0.2)
    yield from c.click()
    yield from c.wait(1.0)


def open_menu(c):
    yield from c.wait(0.4)
    yield from c.move(c.object("Cube", FRONT))
    yield from c.wait(0.7)
    yield from c.move(c.kneady_button("Cube", 0, 0))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(1.8)
    yield from c.key("ESC", "Esc")
    yield from c.wait(0.8)


CLIPS = {"01_pick": pick, "02_opens_menu": opens_menu, "03_add": add, "04_name": name, "05_text": text_icons,
         "06_color": color, "07_open": open_menu}
