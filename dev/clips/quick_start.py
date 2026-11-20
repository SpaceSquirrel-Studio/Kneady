"""Quick Start's clips (tutorials/quick_start), one per step, played in turn
in Blender's default scene. Quick Start is Greg's tutorial and the first one
Kneady ships; these clips remake his recording. Greg: "make that Quick Start
video the first video and plan on redoing it yourself for future updates".

The clips show: select the cube; N and the Kneady tab; + for a region; Edit
Faces, a face, Assign, Done; Kneady on; then a haul each way on its button,
and Ctrl+Z twice.

    python dev/clips/make.py dev/clips/quick_start.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "quick_start"
PRACTICE = os.path.join(FOLDER, "_scenes", "cube.blend")


def click_on(c, where, what, expect=None):
    """Move the cursor to what was found, wait until Blender is sure it is
    there (`expect`, what Blender names there), and click."""
    xy = c.must(where, what)
    yield from c.move(xy)
    yield from c.wait(0.12 if expect is not None else 0.3)
    if expect is not None:
        yield from c.settle(expect, what)
    yield from c.click()


def ADD(name):
    return "kneady.tree_add" in name


def EDIT(name):
    return "kneady.region_edit" in name


def ASSIGN(name):
    return "kneady.region_faces" in name and "ASSIGN" in name


def KNEADY_ON(name):
    return name.endswith("kneady_on")


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    c.area().spaces.active.show_region_ui = False        # the sidebar shut: step 2 opens it
    c.frame(["Cube"], fill=0.4, at=(0.3, 0.47))          # whole, left of where the sidebar will open
    yield 0.5


def select(c):
    yield from c.wait(0.6)
    yield from c.move(c.object("Cube"))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(1.3)


def region(c):
    yield from c.wait(0.4)
    yield from c.move(c.in_region(0.35, 0.6))
    yield from c.wait(0.2)
    yield from c.key("N")
    yield from c.wait(0.8)
    tab = yield from c.tab("Kneady")
    yield from c.move(c.must(tab, "the Kneady tab"))
    yield from c.wait(0.3)
    yield from c.click_tab("Kneady")
    yield from c.wait(0.8)
    plus = yield from c.find_scrolling(ADD, xs=(0.9, 0.86, 0.93))
    yield from click_on(c, plus, "+", ADD)
    yield from c.wait(1.4)


def assign(c):
    yield from c.wait(0.5)
    spot = yield from c.find_scrolling(EDIT, xs=(0.3, 0.2))
    yield from click_on(c, spot, "Edit Faces", EDIT)
    yield from c.wait(0.7)
    # click the cube's top face in Edit Mode, selecting it
    yield from c.move(c.object("Cube", (0.0, 0.0, 1.0)))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(0.6)
    spot = yield from c.find_scrolling(ASSIGN, xs=(0.3, 0.2))
    yield from click_on(c, spot, "Assign", ASSIGN)
    yield from c.wait(0.6)
    spot = yield from c.find_scrolling(EDIT, xs=(0.5, 0.3))
    yield from click_on(c, spot, "Done", EDIT)
    yield from c.wait(0.6)
    spot = yield from c.find_scrolling(KNEADY_ON, xs=(0.15, 0.1, 0.2))
    yield from click_on(c, spot, "the Kneady switch", KNEADY_ON)
    yield from c.wait(1.3)


def haul(c):
    yield from c.wait(0.4)
    # onto the region - the top face - and its button
    yield from c.move(c.object("Cube", (0.3, 0.3, 1.0)))
    yield from c.wait(0.7)
    x, y = c.kneady_button("Cube", 0, 0)
    yield from c.move((x, y))
    yield from c.wait(0.4)
    # left and right
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((x + 130, y), 0.7)
    yield from c.move((x - 60, y), 0.9)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.7)
    # up and down, from the button where it is now
    yield from c.move(c.object("Cube", (0.3, 0.3, 1.0)))
    yield from c.wait(0.5)
    x, y = c.kneady_button("Cube", 0, 0)
    yield from c.move((x, y))
    yield from c.wait(0.4)
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((x, y + 120), 0.7)
    yield from c.move((x, y - 50), 0.9)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.8)
    # both undone
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(0.5)
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(1.2)


CLIPS = {"01_select": select, "02_region": region, "03_assign": assign, "04_haul": haul}
