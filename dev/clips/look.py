"""The Look of Your Buttons' clips (tutorials/look), one per step, played in
turn on the Rigify arm as Toggles and Show When leaves it (arm_toggle). The
clips show, each seen on the forearm:

- the Forearm's buttons arranged in a Column;
- Labels set to Always;
- FK made a text button;
- Bend and Reach made square;
- Highlight set to Outline.

    python dev/clips/make.py dev/clips/look.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from panel import ROW, choose, click_on, ending, one_of

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "look"
PRACTICE = os.path.join(FOLDER, "_scenes", "arm_toggle.blend")
ICONS = ("ARROWS", "IMAGE", "OBJECT", "TEXT")        # the Icon menu's order


def region():
    import bpy  # type: ignore
    return bpy.data.objects["Arm"].kneady.regions[0]


def forearm(along=0.5):
    """A point `along` the forearm (0 the elbow, 1 the wrist) at rest, in the
    arm's own space. It lies on the forearm's two deform bones (Rigify makes
    two, end to end)."""
    import bpy  # type: ignore
    bones = bpy.data.objects["Rig"].data.bones
    elbow, wrist = bones["DEF-forearm.L"].head_local, bones["DEF-forearm.L.001"].tail_local
    return tuple(elbow + (wrist - elbow) * along)


def look_at_forearm(c, seconds=1.6):
    """Move the mouse onto the forearm by the wrist and rest there, to show
    its buttons. They show in the region's middle, clear of the mouse, so no
    button's tip covers them."""
    yield from c.move(c.object("Arm", forearm(0.9)))
    yield from c.wait(seconds)


def select_row(c, owner, what):
    row = yield from c.tree_row(owner)
    yield from click_on(c, row, what, ROW)
    yield from c.wait(0.4)


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Arm"], fill=0.62, at=(0.27, 0.5))          # the arm large, left of the sidebar
    yield 0.5


def column(c):
    yield from c.wait(0.6)
    yield from select_row(c, region(), "Forearm's row")
    yield from one_of(c, ending("regions[0].arrange"), 1, 4, "Column")      # Row | Column | Row + Column | Circle
    yield from c.wait(0.4)
    yield from look_at_forearm(c)


def labels(c):
    yield from c.wait(0.5)
    yield from one_of(c, ending("kneady_labels"), 2, 3, "Labels", xs=(0.6,), top=True)   # Off | On Hover | Always
    yield from c.wait(0.4)
    yield from look_at_forearm(c)


def text(c):
    yield from c.wait(0.5)
    arrow = yield from c.tree_row(region(), arrow=True)
    yield from click_on(c, arrow, "Forearm's arrow")     # Blender names nothing on the arrow itself
    yield from c.wait(0.5)
    yield from select_row(c, region().buttons[2], "FK's row")
    yield from choose(c, "icon_type", ICONS, "TEXT", "the Icon dropdown", button=2, xs=(0.36, 0.3, 0.42))
    yield from c.wait(0.4)
    yield from look_at_forearm(c, 1.2)


def square(c):
    yield from c.wait(0.5)
    for index, name in ((0, "Bend"), (1, "Reach")):
        yield from select_row(c, region().buttons[index], "%s's row" % name)
        yield from one_of(c, "shape", 1, 2, "Square", button=index, xs=(0.7,))   # Circle | Square
        yield from c.wait(0.4)
    yield from look_at_forearm(c, 1.2)


def outline(c):
    yield from c.wait(0.5)
    yield from one_of(c, ending("kneady_highlight"), 1, 2, "Highlight", xs=(0.6,), top=True)   # Fill | Outline
    yield from c.wait(0.4)
    yield from look_at_forearm(c, 2.0)


CLIPS = {"01_column": column, "02_labels": labels, "03_text": text, "04_square": square, "05_outline": outline}
