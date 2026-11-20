"""Drive More Than Bones' clips (tutorials/drive_more), one per step, played
in turn on the shape cube, the whole of it one region (shape_cube_region).
The clips show:

- Up / Down made a Property, the Sphere shape key;
- Left / Right made a Modifier Input, Twist;
- a haul each way, and Ctrl+Z twice;
- a second command on Up / Down, Scale on All;
- a haul up with Alt held part way, switching it to the twist.

    python dev/clips/make.py dev/clips/drive_more.py

Everything is found where it is drawn now, so the clips follow Kneady's
interface as it changes: run this again and they match it."""

import os

from panel import add_command, axis, drives, haul, open_command, suggestion

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "drive_more"
PRACTICE = os.path.join(FOLDER, "_scenes", "shape_cube_region.blend")
FRONT = (0.0, -1.0, 0.3)                             # on the cube's front: the whole cube is one region


def SETUP(c):
    import bpy  # type: ignore
    bpy.context.window_manager.kneady_help = "LEARN"    # as the person following it has it
    yield from c.sidebar("Kneady")
    yield 0.3
    c.frame(["Cube"], fill=0.32, at=(0.3, 0.45))         # whole, left of the sidebar, with room to grow
    yield 0.5


def shape_key(c):
    yield from c.wait(0.6)
    yield from open_command(c, "up")
    yield from drives(c, "up.kind", "PROPERTY")
    yield from suggestion(c, "up.data_path", "the Path field")
    yield from c.wait(1.3)


def modifier_input(c):
    yield from c.wait(0.4)
    yield from open_command(c, "across")
    yield from drives(c, "across.kind", "INPUT")
    yield from suggestion(c, "across.input", "the Input field")
    yield from c.wait(1.3)


def try_it(c):
    yield from c.wait(0.4)
    yield from haul(c, "Cube", FRONT, [(0, 120, 0.6), (0, 220, 0.6)])          # rounds into a sphere
    yield from haul(c, "Cube", FRONT, [(150, 0, 0.7), (-90, 0, 1.0), (60, 0, 0.5)])   # twists
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(0.5)
    yield from c.key("Z", "Z", ctrl=True)
    yield from c.wait(1.2)


def two_at_once(c):
    yield from c.wait(0.4)
    yield from add_command(c, "up")
    yield from drives(c, "up.more[0].kind", "SCALE")
    yield from axis(c, "up.more[0].axis", 3, 4)
    yield from c.wait(1.3)


def alt(c):
    yield from c.wait(0.4)
    yield from haul(c, "Cube", FRONT, [(0, 140, 0.8),                      # rounds and grows
                                       ("hold", "LEFT_ALT", "Alt"),
                                       (110, 140, 0.8),                    # Alt held: twists
                                       ("let_go", "LEFT_ALT"),
                                       (110, 200, 0.6)])                   # let go: rounds on
    yield from c.wait(1.5)


CLIPS = {"01_shape_key": shape_key, "02_modifier_input": modifier_input, "03_try": try_it,
         "04_two_at_once": two_at_once, "05_alt": alt}
