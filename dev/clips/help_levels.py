"""Learn, Inform and Quiet's clips (tutorials/help_levels, tutorial 0), one
per step, played in turn on the cube where Quick Start leaves it
(cube_region). The clips show:

- the cube's button rested on at Learn, showing its whole tip;
- Help set from Learn to Inform: the tip shorter, and Start a Tutorial
  gone;
- Quiet: no tip;
- Learn again: Start a Tutorial back.

    python dev/clips/make.py dev/clips/help_levels.py

Start a Tutorial is in the Tutorials panel, which these clips show
(TUTORIALS_PANEL). Help is set unseen to Learn first, as Kneady starts. A
recording's settings are factory ones, so nothing is kept. Everything is
found where it is drawn now, so the clips follow Kneady as it changes: run
this again and they match it."""

import os

from panel import choose, ending, up_top

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "help_levels"
PRACTICE = os.path.join(FOLDER, "_scenes", "cube_region.blend")
TUTORIALS_PANEL = True                               # Start a Tutorial shown coming and going
TOP = (0.3, 0.3, 1.0)                                # on the cube's top face, its region
LEVELS = ("LEARN", "INFORM", "QUIET")                # Help's menu order
HELP = ending("kneady_help")
PENCIL = ending("kneady_tutorial_edit")              # Edit mode's pencil, at the end of Start a Tutorial's row
MENU_LEFT = 5.0                                      # how far left of the pencil Start a Tutorial's middle is, in units


def SETUP(c):
    """Set unseen: Help at Learn, as Kneady starts, and the whole cube in
    view, left of the sidebar."""
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Cube"], fill=0.4, at=(0.3, 0.47))
    yield 0.5


def rest_on_button(c, seconds=2.6):
    """Move onto the cube's top, then its button, and rest there past the
    tip's half-second delay."""
    yield from c.move(c.object("Cube", TOP))
    yield from c.wait(0.4)
    yield from c.move(c.kneady_button("Cube", 0, 0))
    yield from c.wait(seconds)


def start_a_tutorial(c, seconds=1.4):
    """Put the cursor on Start a Tutorial. It is a menu, which Blender names
    nothing by, so it is found left of the pencil at the end of its row."""
    spot = yield from up_top(c, PENCIL, "the pencil", xs=(0.83, 0.82))
    yield from c.move((spot[0] - MENU_LEFT * c.unit, spot[1]))
    yield from c.wait(seconds)


def set_help(c, level):
    yield from up_top(c, HELP, "Help", xs=(0.85, 0.8))
    yield from choose(c, HELP, LEVELS, level, "Help", xs=(0.85, 0.8), titled=True)   # its menu headed Help
    yield from c.wait(0.6)


def learn(c):
    yield from c.wait(0.5)
    yield from rest_on_button(c, 3.2)


def inform(c):
    yield from c.wait(0.5)
    spot = yield from up_top(c, HELP, "Help", xs=(0.85, 0.8))
    yield from c.move(spot)                              # at Learn, as Kneady starts
    yield from c.wait(0.8)
    yield from set_help(c, "INFORM")
    yield from rest_on_button(c, 2.8)


def quiet(c):
    yield from c.wait(0.5)
    yield from set_help(c, "QUIET")
    yield from rest_on_button(c, 2.4)


def back_to_learn(c):
    yield from c.wait(0.5)
    yield from set_help(c, "LEARN")
    yield from start_a_tutorial(c, 1.8)


CLIPS = {"01_learn": learn, "02_inform": inform, "03_quiet": quiet, "04_learn": back_to_learn}
