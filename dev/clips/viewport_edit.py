"""Viewport Edit's clips (tutorials/viewport_edit), one per step, played in
turn on the mannequin with its Head and Chest controls (mannequin_controls).
The clips show:

- Viewport Edit turned on and Nod clicked, selecting its row;
- + clicked by the head, and the new button named Tilt;
- Rearrange turned on, Tilt dragged between Nod and Turn, and Rearrange
  turned off;
- Spare on the chest Ctrl+clicked and removed with -, its menu with it.

    python dev/clips/make.py dev/clips/viewport_edit.py

Recorded with Blender's Region Overlap off, so the view's middle is where it
is seen, left of the sidebar. Everything is found where it is drawn now -
the buttons, Viewport Edit's icons around them, the tree's rows - so the
clips follow Kneady as it changes: run this again and they match it."""

import os

from panel import ROW, click_on, kneady, setting

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "viewport_edit"
PRACTICE = os.path.join(FOLDER, "_scenes", "mannequin_controls.blend")
HEAD, CHEST = 0, 1                                   # the regions' places in the mannequin's list


def PICK(name):
    return name.endswith("kneady_pick")


def region(index):
    import bpy  # type: ignore
    return bpy.data.objects["Mannequin"].kneady.regions[index]


def button(c, index, which):
    """Where region `index`'s button `which` is drawn over the mannequin."""
    return c.kneady_button("Mannequin", index, which)


def icon(c, index, what):
    """Where Viewport Edit draws its icon `what` ("ADD", "REMOVE",
    "ARRANGE") around region `index`'s buttons, in the window's pixels."""
    import bpy  # type: ignore
    pick = kneady(c, "pick")
    obj, view = bpy.data.objects["Mannequin"], c.region()
    with bpy.context.temp_override(window=c.win, area=c.area(), region=view):
        found = pick.edit_icons(bpy.context, obj, region(index))
    if what not in found:
        raise LookupError("Viewport Edit shows no %s by %s" % (what, region(index).name))
    return (view.x + found[what].x, view.y + found[what].y)


def hover(c, index, which=0, up=1.6):
    """Move over region `index`, a little above its button `which`: onto its
    faces, clear of the buttons, so the region is hovered and its icons
    show."""
    x, y = button(c, index, which)
    yield from c.move((x, y + up * 14 * c.unit / 20))     # a button's radius is 14 px at 20 px a unit
    yield from c.wait(0.5)


CONFIRM = (-3.32, -1.48)  # a confirm's Remove button, from the window's middle, in units (measured, Blender 5.2)


def confirm(c):
    """Where a confirm's Remove button is. Blender opens a confirm in the
    middle of the window, wherever the click that asked for it was, with its
    own button on the left. A confirm is not a region Blender lets a script
    search, so the button is found by where Blender puts it. If that ever
    changes, the clip's step is reported not done."""
    return (0.5 * c.win.width + CONFIRM[0] * c.unit, 0.5 * c.win.height + CONFIRM[1] * c.unit)


def SETUP(c):
    """Set unseen: Help at Learn, as the person following the tutorial has
    it; Region Overlap off (these are factory settings, so nothing is
    saved); and the view on the head and chest, from the front and a little
    to the side."""
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"
    bpy.context.preferences.system.use_region_overlap = False
    yield from c.sidebar("Kneady")
    yield 0.5
    rv3d = c.area().spaces.active.region_3d
    rv3d.view_location = (0.0, 0.0, 1.6)
    rv3d.view_rotation = (0.74324, 0.64609, 0.11392, 0.13105)
    rv3d.view_distance = 0.85
    yield 0.5


def pick(c):
    yield from c.wait(0.6)
    spot = yield from c.find(PICK, xs=(0.5,))
    yield from click_on(c, spot, "Viewport Edit", PICK)
    yield from c.wait(0.6)
    yield from c.move(button(c, HEAD, 0))                # Nod
    yield from c.wait(0.5)
    yield from c.click()
    yield from c.wait(0.8)
    row = yield from c.tree_row(region(HEAD).buttons[0])
    yield from c.move(row)                               # onto its row, now selected
    yield from c.wait(1.8)


def add(c):
    yield from c.wait(0.5)
    yield from hover(c, HEAD)
    yield from c.move(icon(c, HEAD, "ADD"))
    yield from c.wait(0.4)
    yield from c.click()
    yield from c.wait(0.8)
    new = region(HEAD).buttons[2]
    row = yield from c.tree_row(new)
    yield from c.move(row)
    yield from c.wait(0.2)
    yield from c.settle(ROW, "the new button's row")
    yield from c.rename_click()
    yield from c.wait(0.3)
    yield from c.settle(setting("name", 2), "its name, being edited")
    yield from c.type("Tilt")
    yield from c.wait(0.15)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.6)
    yield from hover(c, HEAD, 1)
    yield from c.wait(1.2)


def arrange(c):
    yield from c.wait(0.5)
    yield from hover(c, HEAD, 1)
    grip = icon(c, HEAD, "ARRANGE")
    yield from c.move(grip)
    yield from c.wait(0.4)
    yield from c.click()                                 # Rearrange on
    yield from c.wait(0.6)
    yield from c.move(button(c, HEAD, 2))                # Tilt, last
    yield from c.wait(0.4)
    between = button(c, HEAD, 1)                         # where Turn is: Tilt takes its place
    yield from c.drag(between, 1.0)
    yield from c.wait(0.8)
    yield from c.move(icon(c, HEAD, "ARRANGE"))
    yield from c.wait(0.4)
    yield from c.click()                                 # and off
    yield from c.wait(0.5)
    yield from hover(c, HEAD, 1)
    yield from c.wait(1.0)


def remove(c):
    yield from c.wait(0.5)
    yield from hover(c, CHEST, 2)
    yield from c.move(button(c, CHEST, 2))               # Spare
    yield from c.wait(0.4)
    yield from c.hold("LEFT_CTRL", "Ctrl")
    yield from c.wait(0.15)
    yield from c.click(ctrl=True)                        # selected only: its menu stays closed
    yield from c.wait(0.15)
    yield from c.let_go("LEFT_CTRL")
    yield from c.wait(0.8)
    minus = icon(c, CHEST, "REMOVE")
    yield from c.move(minus)
    yield from c.wait(0.4)
    yield from c.click()
    yield from c.wait(0.7)
    yield from c.move(confirm(c))                        # Kneady asks first: onto Remove
    yield from c.wait(0.4)
    yield from c.click()
    yield from c.wait(0.8)
    yield from hover(c, CHEST, 1)
    yield from c.wait(1.2)


CLIPS = {"01_pick": pick, "02_add": add, "03_arrange": arrange, "04_remove": remove}
