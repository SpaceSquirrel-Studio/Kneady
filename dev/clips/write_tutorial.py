"""Write a Tutorial's clips (tutorials/write_tutorial), one per step, played
in turn on the cube where Quick Start leaves it (cube_region). The clips
show:

- Edit mode turned on;
- + clicked and a title given, Haul the Cube;
- its step's title and paragraph written;
- a Done When check added: a Kneady button hauled;
- Try: the new tutorial playing in this one's place, the cube hauled and
  its step ticked off.

    python dev/clips/make.py dev/clips/write_tutorial.py

The editor is in the Tutorials panel at the top of the Kneady tab, which the
clips show (TUTORIALS_PANEL). The tutorial written is saved in a folder of
the recording's own (AUTHOR), never in Kneady's tutorials. The clips show
that folder under the dropdown, so it is a public folder with no one's name
in it, and it is removed afterwards (TEARDOWN). Everything is found where it
is drawn now, so the clips follow Kneady as it changes: run this again and
they match it.

With CLIP_LOOK set to a folder, the moments marked by look() are
screenshotted there, to measure from when the panel changes."""

import os
import shutil

from panel import _snapshot, choose, click_on, ending, haul, kneady, one_of, up_top

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "write_tutorial"
PRACTICE = os.path.join(FOLDER, "_scenes", "cube_region.blend")
TUTORIALS_PANEL = True                               # the editor's panel shown in the clips
AUTHOR = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Kneady Tutorials")
TOP = (0.3, 0.3, 1.0)                                # on the cube's top face, its region
KINDS = ("ACTION", "HOVER", "PATH", "MODE", "ACTIVE", "SELECTED")    # a check's kinds, its menu's order
EDIT = ending("kneady_tutorial_edit")
FIELD_LEFT = 1.2                                     # the new tutorial's Title field, this far left of the mouse, in units
TITLE_ABOVE = 2.9                                    # a step's Title, this far above its first paragraph (below the list)
DONE_BELOW = 3.44                                    # Done When's header under Media's choices (measured)
OK_BLUE = (0.278, 0.447, 0.702)                      # a dialog's OK: a selected button's inner color (factory theme)
DEBUG = os.environ.get("CLIP_LOOK")                  # a folder: screenshots of moments, to measure by


def operator(name, *parts):
    """A test for a button running Kneady's operator `name`, with each of
    `parts` ("which='CHECKS'") among its settings."""
    return lambda n: ("kneady.%s(" % name) in n and all(p in n for p in parts)


def look(c, name):
    """Save a screenshot of the window as it is under DEBUG, unseen, for
    measuring."""
    if not DEBUG:
        return
    import bpy  # type: ignore
    with bpy.context.temp_override(window=c.win):
        bpy.ops.screen.screenshot(filepath=os.path.join(DEBUG, name + ".png"))


def ok_below(c, near):
    """Where a dialog's OK button is, found by looking, since a popup is no
    region a script can search. It is the widest run of the OK's blue in the
    rows just under `near` (the mouse, on the dialog's field). Looking only
    there leaves out the sidebar's blue buttons above it and its lit eye
    further down. A generator; (x, y)."""
    import numpy as np  # type: ignore
    pixels = yield from _snapshot(c)
    blue = np.abs(pixels[..., :3] - OK_BLUE).max(axis=2) < 0.06
    y = int(near[1])
    hits = []
    for row in range(max(y - int(3 * c.unit), 0), y - int(0.5 * c.unit)):
        cols = np.flatnonzero(blue[row])
        if not len(cols):
            continue
        breaks = np.flatnonzero(np.diff(cols) > 1)
        starts, ends = np.r_[cols[0], cols[breaks + 1]], np.r_[cols[breaks], cols[-1]]
        k = int(np.argmax(ends - starts))
        if ends[k] - starts[k] >= 4 * c.unit:
            hits.append((row, 0.5 * (starts[k] + ends[k])))
    if not hits:
        return None
    return (float(np.median([h[1] for h in hits])), 0.5 * (hits[0][0] + hits[-1][0]))


def SETUP(c):
    """Set unseen: the recording's own empty tutorials folder; Help at
    Learn, as the person following the tutorial has it; and the whole cube
    in view, left of the sidebar."""
    import bpy  # type: ignore
    shutil.rmtree(AUTHOR, ignore_errors=True)
    os.makedirs(AUTHOR)
    kneady(c, "tutorials").set_author_folder(AUTHOR)    # factory settings, so kept nowhere
    bpy.context.window_manager.kneady_help = "LEARN"
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Cube"], fill=0.4, at=(0.3, 0.47))
    yield 0.5


def TEARDOWN():
    shutil.rmtree(AUTHOR, ignore_errors=True)


def edit(c):
    yield from c.wait(0.6)
    spot = yield from up_top(c, EDIT, "the pencil", xs=(0.83, 0.82))    # the tabs' strip further right
    yield from click_on(c, spot, "the pencil", EDIT)
    yield from c.wait(1.8)
    look(c, "01_on")


def new(c):
    yield from c.wait(0.5)
    test = operator("tutorial_new")
    spot = yield from c.find(test, xs=(0.78, 0.76, 0.8))
    yield from click_on(c, spot, "+", test)
    yield from c.wait(0.8)
    # Blender opens the dialog with its first field under the mouse: Title
    look(c, "02_dialog")
    yield from c.move((spot[0] - FIELD_LEFT * c.unit, spot[1]))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(0.4)
    yield from c.type("Haul the Cube")
    yield from c.wait(0.3)
    yield from c.key("RET", "Enter")                    # the title kept; the dialog stays
    yield from c.wait(0.5)
    ok = yield from ok_below(c, (spot[0], spot[1]))
    yield from c.move(c.must(ok, "the dialog's OK"))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(1.4)
    look(c, "02_made")


def write(c):
    yield from c.wait(0.5)
    para = ending("steps[0].text[0].text")
    spot = yield from c.find_scrolling(para, xs=(0.35,))
    _x, y = c.must(spot, "the paragraph")
    # the step's Title, under the list: the search starts below the list,
    # since its rows name their titles too
    title = ending("steps[0].title")
    found = yield from c.find(title, xs=(0.7,), start=y + TITLE_ABOVE * c.unit)
    yield from click_on(c, found, "the step's Title", title)
    yield from c.wait(0.4)
    yield from c.type("Haul the Cube")
    yield from c.wait(0.2)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.6)
    look(c, "03_title")
    spot = yield from c.find(para, xs=(0.35,))
    yield from click_on(c, spot, "the paragraph", para)
    yield from c.wait(0.4)
    yield from c.type("Haul the cube's top up and down.")
    yield from c.wait(0.2)
    yield from c.key("RET", "Enter")
    yield from c.wait(1.2)
    look(c, "03_done")


def done(c):
    yield from c.wait(0.5)
    # Done When's header names nothing: found under Media's row of choices
    shared = ending("steps[0].media_from")
    spot = yield from c.find_scrolling(shared, xs=(0.5,))
    _x, y = c.must(spot, "Media's row")
    yield from c.move((c.in_region(0.3, 0.5, "UI")[0], y - DONE_BELOW * c.unit))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(0.6)
    look(c, "04_open")
    add = operator("tutorial_list", "which='CHECKS'", "action='ADD'")
    spot = yield from c.find_scrolling(add, xs=(0.5,))
    yield from click_on(c, spot, "Add Check", add)
    yield from c.wait(0.6)
    yield from choose(c, ending("checks[0].kind"), KINDS, "ACTION", "the check's kind", xs=(0.4,), titled=True)
    yield from c.wait(0.4)
    look(c, "04_action")
    field = ending("checks[0].operator")
    spot = yield from c.find_scrolling(field, xs=(0.5,))
    yield from click_on(c, spot, "the operator's field", field)
    yield from c.wait(0.4)
    yield from c.type("kneady.drag")
    yield from c.wait(0.2)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.6)
    yield from one_of(c, ending("checks[0].moved"), 1, 3, "Hauled", xs=(0.5,))
    yield from c.wait(1.2)
    look(c, "04_done")


def try_it(c):
    yield from c.wait(0.5)
    # scroll the tab to its top, in sight: the tutorial playing shows there,
    # and becomes the one written (its panel over the view plays in the main
    # window)
    yield from c.scroll(-15, c.in_region(0.5, 0.5, "UI"))
    yield from c.wait(0.6)
    test = operator("tutorial_try")
    spot = yield from c.find(test, xs=(0.72,))
    yield from click_on(c, spot, "Try", test)
    yield from c.wait(1.6)
    look(c, "05_tried")
    yield from haul(c, "Cube", TOP, [(0, 110, 0.8), (0, 40, 0.6)])
    yield from c.wait(2.0)
    look(c, "05_done")


CLIPS = {"01_edit": edit, "02_new": new, "03_write": write, "04_done": done, "05_try": try_it}
