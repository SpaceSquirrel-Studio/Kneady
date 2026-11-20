"""Copy and Reuse's clips (tutorials/copy_reuse), one per step, played in
turn on the mannequin as Viewport Edit leaves it, with a Hips region
(mannequin_edited). The clips show:

- Turn's commands copied onto Tilt with a right-click;
- Tilt's axis made Z, and Tilt hauled;
- Nod made to open a menu, and Tilt moved into it;
- the chest's buttons copied onto the hips;
- their bone made the hips, and Bend hauled there.

    python dev/clips/make.py dev/clips/copy_reuse.py

Recorded with Blender's Region Overlap off, so the view's middle is where it
is seen, left of the sidebar. A right-click's menu is found by looking where
Blender opened it (panel.popup_rows); everything else is found where it is
drawn now. Run this again and the clips match Kneady as it is."""

import os

from panel import axis, click_on, open_command, popup_rows, search_pick, setting

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "copy_reuse"
PRACTICE = os.path.join(FOLDER, "_scenes", "mannequin_edited.blend")
HEAD, CHEST, HIPS = 0, 1, 2                          # the regions' places in the mannequin's list
NOD, TILT, TURN = 0, 1, 2                            # the head's buttons
# a right-click menu's items, in order under its title (ui.draw_edit_items's,
# then menu_build's): on a button, and on a region's faces
ON_BUTTON = ("Copy Button", "Paste Button", "Copy Commands", "Paste Commands", "Copy All Buttons",
             "Paste All Buttons", "Copy Menu", "Paste Menu", "Move To")
ON_REGION = ("Copy All Buttons", "Paste All Buttons", "Paste Menu Into Region")
MOVE_TO = ("Buttons", "In Nod")                      # Move To's menu for Tilt, once Nod opens one


def region(index):
    import bpy  # type: ignore
    return bpy.data.objects["Mannequin"].kneady.regions[index]


def button(c, index, which):
    """Where region `index`'s button `which` is drawn over the mannequin."""
    return c.kneady_button("Mannequin", index, which)


def faces(c, index, up=2.2):
    """A spot on region `index`'s faces: above its buttons, clear of them."""
    x, y = button(c, index, 0)
    return (x, y + up * 14 * c.unit / 20)                # a button's radius is 14 px at 20 px a unit


def onto(c, near, items, item, titled=True):
    """Move the mouse onto `item` in the popup menu open at `near`, `items`
    being the menu's order. A generator; returns the menu's box."""
    x, rows, box = yield from popup_rows(c, near)
    k = items.index(item) + (1 if titled else 0)
    if x is None or len(rows) != len(items) + (1 if titled else 0):
        raise LookupError("the menu at %s shows %d rows, not %s" % (near, len(rows), items))
    yield from c.move((x, rows[k]))
    yield from c.wait(0.3)
    return box


def right_click(c, where, items, item, click=True):
    """Right-click at `where` (a button or a region's faces, in Viewport
    Edit) and click `item` in the menu it opens - or, without `click`, only
    point at it. A generator; returns the menu's box."""
    yield from c.move(where)
    yield from c.wait(0.5)
    yield from c.click("RIGHTMOUSE")
    yield from c.wait(0.7)
    box = yield from onto(c, c.pos, items, item)
    if click:
        yield from c.click()
        yield from c.wait(0.6)
    return box


def to_sidebar(c):
    """Move straight across into the sidebar from where the mouse is.
    Viewport Edit keeps the last region hovered while the mouse crosses
    empty space, so a path down over the chest would leave the chest
    hovered."""
    ui = c.region("UI")
    yield from c.move((ui.x + 0.2 * ui.width, c.pos[1]))
    yield from c.wait(0.2)


def haul(c, index, which, dx, dy, seconds=1.0):
    yield from c.move(button(c, index, which))
    yield from c.wait(0.4)
    x, y = c.pos
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((x + dx, y + dy), seconds)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.6)


def SETUP(c):
    """Set unseen: Help at Learn, as the person following the tutorial has
    it; Region Overlap off (these are factory settings, so nothing is
    saved); and the view on the head, chest and hips, from the front and a
    little to the side."""
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"
    bpy.context.preferences.system.use_region_overlap = False
    yield from c.sidebar("Kneady")
    yield 0.5
    rv3d = c.area().spaces.active.region_3d
    rv3d.view_location = (0.0, 0.0, 1.45)
    rv3d.view_rotation = (0.74324, 0.64609, 0.11392, 0.13105)
    rv3d.view_distance = 1.1
    yield 0.5


def copy(c):
    yield from c.wait(0.6)
    yield from right_click(c, button(c, HEAD, TURN), ON_BUTTON, "Copy Commands")
    yield from right_click(c, button(c, HEAD, TILT), ON_BUTTON, "Paste Commands")
    yield from c.move(faces(c, HEAD))
    yield from c.wait(1.6)


def tilt(c):
    yield from c.wait(0.5)
    yield from to_sidebar(c)
    yield from open_command(c, "across", TILT)
    yield from axis(c, "across.axis", 2, 3, button=TILT)   # X | Y | Z
    yield from c.wait(0.6)
    yield from haul(c, HEAD, TILT, 70, 0)                  # the head tilts to the side
    yield from c.move(faces(c, HEAD))
    yield from c.wait(1.2)


def move(c):
    yield from c.wait(0.5)
    yield from c.move(button(c, HEAD, NOD))
    yield from c.wait(0.4)
    yield from c.click()                                   # Nod selected
    yield from c.wait(0.6)
    yield from to_sidebar(c)
    test = setting("opens_menu", NOD)
    spot = yield from c.find_scrolling(test, xs=(0.3,))
    yield from click_on(c, spot, "Opens Menu", test)
    yield from c.wait(0.6)
    box = yield from right_click(c, button(c, HEAD, TILT), ON_BUTTON, "Move To", click=False)
    yield from c.wait(0.7)                                 # its own menu opens beside it
    yield from onto(c, (box[2] + 3.0 * c.unit, c.pos[1]), MOVE_TO, "In Nod", titled=False)
    yield from c.click()
    yield from c.wait(0.8)
    yield from c.move(button(c, HEAD, NOD))
    yield from c.wait(0.4)
    yield from c.click()                                   # its menu opens, Tilt in it
    yield from c.wait(1.8)


def copy_all(c):
    yield from c.wait(0.5)
    yield from c.move(faces(c, CHEST))
    yield from c.wait(0.6)
    yield from right_click(c, faces(c, CHEST), ON_REGION, "Copy All Buttons")
    yield from c.move(faces(c, HIPS, up=-1.6))
    yield from c.wait(0.6)
    yield from right_click(c, faces(c, HIPS, up=-1.6), ON_REGION, "Paste All Buttons")
    yield from c.wait(1.4)


def to_hips(c):
    yield from c.wait(0.5)
    for which, direction in ((0, "up"), (1, "across")):   # Bend, Twist
        yield from c.move(button(c, HIPS, which))
        yield from c.wait(0.4)
        yield from c.click()                               # selected
        yield from c.wait(0.6)
        yield from to_sidebar(c)
        yield from open_command(c, direction, which)
        yield from search_pick(c, direction + ".bone", "Bone", "hips", button=which, enter=True)
        yield from c.wait(0.5)
    yield from haul(c, HIPS, 0, 0, 60)                    # Bend: the hips bend
    yield from c.wait(1.2)


CLIPS = {"01_copy": copy, "02_tilt": tilt, "03_move": move, "04_copy_all": copy_all, "05_hips": to_hips}
