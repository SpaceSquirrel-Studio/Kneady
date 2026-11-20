"""Tips for Your Buttons' clips (tutorials/tips), one per step, played in
turn on the mannequin as Copy and Reuse leaves it (mannequin_reused). The
clips show Turn's tip read on the head, and its Tip settings opened from the
tree; its Drag row given words; a message written; and Help set to Inform,
making the tip shorter.

    python dev/clips/make.py dev/clips/button_tips.py

This file is named for the tutorial's subject rather than "tips.py",
because Kneady has a tips.py of its own. The clips are recorded with
Blender's Region Overlap off and the view close on the head. Everything is
found where it is drawn now, so the clips follow Kneady as it changes: run
this again and they match it."""

import os

from panel import ROW, choose, click_on, ending, setting, up_top

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "tips"
PRACTICE = os.path.join(FOLDER, "_scenes", "mannequin_reused.blend")
HEAD, TURN = 0, 2                                    # the head's region, and Turn among its buttons
LEVELS = ("LEARN", "INFORM", "QUIET")                # Help's menu order
TIP_BELOW = 1.4                                      # Turn's Tip header under its Opens Menu, in units (measured)


def region(index):
    import bpy  # type: ignore
    return bpy.data.objects["Mannequin"].kneady.regions[index]


def rest_on_turn(c, seconds=2.2):
    """The mouse on Turn, resting there past the tip's half second."""
    yield from c.move(c.kneady_button("Mannequin", HEAD, TURN))
    yield from c.wait(seconds)


def field(c, attr, what, text):
    """Click a text field in Turn's settings, type `text`, and press Enter."""
    test = setting(attr, TURN)
    spot = yield from c.find_scrolling(test, xs=(0.6,))
    yield from click_on(c, spot, what, test)
    yield from c.wait(0.4)
    yield from c.type(text)
    yield from c.wait(0.2)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.6)


def SETUP(c):
    """Set unseen: Help at Learn, as the person following the tutorial has
    it; Region Overlap off (these are factory settings, so nothing is
    saved); and the view close on the head, from the front and a little to
    the side."""
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"
    bpy.context.preferences.system.use_region_overlap = False
    yield from c.sidebar("Kneady")
    yield 0.5
    rv3d = c.area().spaces.active.region_3d
    rv3d.view_location = (0.0, 0.0, 1.74)
    rv3d.view_rotation = (0.74324, 0.64609, 0.11392, 0.13105)
    rv3d.view_distance = 0.6
    yield 0.5


def read(c):
    yield from c.wait(0.5)
    yield from rest_on_turn(c, 2.6)
    arrow = yield from c.tree_row(region(HEAD), arrow=True)
    yield from c.move(arrow)
    yield from c.wait(0.3)
    yield from c.click()                                   # Head unfolded
    yield from c.wait(0.5)
    row = yield from c.tree_row(region(HEAD).buttons[TURN])
    yield from click_on(c, row, "Turn's row", ROW)
    yield from c.wait(0.6)
    # Tip, last in its settings: under Opens Menu
    test = setting("opens_menu", TURN)
    spot = yield from c.find_scrolling(test, xs=(0.3,))
    x, y = c.must(spot, "Opens Menu")
    yield from c.move((x, y - TIP_BELOW * c.unit))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(1.4)


def words(c):
    yield from c.wait(0.5)
    yield from field(c, "tip_rows[0].text", "the Drag row's words", "Turn the head")
    yield from rest_on_turn(c)


def message(c):
    yield from c.wait(0.5)
    yield from field(c, "tip_text", "the message", "Looks left and right.")
    yield from rest_on_turn(c)


def help_level(c):
    yield from c.wait(0.5)
    test = ending("kneady_help")
    yield from up_top(c, test, "Help", xs=(0.85, 0.8))   # at the right of the tab's top row
    yield from choose(c, test, LEVELS, "INFORM", "Help", xs=(0.85, 0.8), titled=True)   # its menu headed Help
    yield from c.wait(0.4)
    yield from rest_on_turn(c, 2.4)


CLIPS = {"01_read": read, "02_words": words, "03_message": message, "04_help": help_level}
