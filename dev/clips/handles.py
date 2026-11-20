"""3D Handles' clips (tutorials/handles), one per step, played in turn on the
Rigify arm as Buttons on the Item leaves it (arm_on_item). The clips show:

- Reach made a 3D Handle;
- its Shape made a Quad Arrow, and its Size 2;
- the handle hauled along one of its arms;
- FK clicked on, and Bend made a 3D Handle, a Ring;
- the ring turned, bending the forearm.

    python dev/clips/make.py dev/clips/handles.py

Recorded close on the forearm with Region Overlap off (forearm.close_up).
Every spot is found where it is drawn now, and the handles where Kneady
draws them (forearm.handles), so the clips follow Kneady as it changes: run
this again and they match it."""

import os

from forearm import LOOKS, centered, close_up, forearm, handles, region, rest, select_row, world
from panel import choose, click_on, one_of, setting

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FOLDER = os.path.join(REPO, "tutorials")
TUTORIAL = "handles"
PRACTICE = os.path.join(FOLDER, "_scenes", "arm_on_item.blend")
SHAPES = ("ARROW", "BOX", "DOUBLE", "CROSS", "RING", "OBJECT")     # the Shape menu's order


def SETUP(c):
    yield from close_up(c)


def handle_shape(c, index, shape):
    yield from choose(c, "handle_shape", SHAPES, shape, "Shape", button=index, xs=(0.6,))
    yield from c.wait(0.4)


def handle(c):
    yield from c.wait(0.6)
    yield from select_row(c, region().buttons[1], "Reach's row")
    yield from one_of(c, LOOKS, 2, 3, "3D Handle", xs=(0.5,))  # In Row | On Item | 3D Handle
    yield from c.wait(0.5)
    yield from rest(c, 1.8)


def quad(c):
    yield from c.wait(0.5)
    yield from handle_shape(c, 1, "CROSS")
    # its Size: a click on the slider starts editing it, with its number
    # selected to type over
    test = setting("handle_size", 1)
    spot = yield from c.find_scrolling(test, xs=(0.25,))
    yield from click_on(c, spot, "Size", test)
    yield from c.wait(0.4)
    yield from c.type("2")
    yield from c.wait(0.2)
    yield from c.key("RET", "Enter")
    yield from c.wait(0.5)
    yield from rest(c, 1.8)


def along(c, part, out, seconds):
    """Press on a handle's arrow near its head, and haul `out` pixels
    further along it."""
    (ox, oy) = handles(c)[1]
    base, tip = part["base"], part["tip"]
    d = (tip - base).normalized()
    press = (ox + base.x + (tip - base).x * 0.8, oy + base.y + (tip - base).y * 0.8)
    yield from c.move(press)
    yield from c.wait(0.4)
    yield from c.press()
    yield from c.wait(0.1)
    yield from c.move((press[0] + d.x * out, press[1] + d.y * out), seconds)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.5)


def haul(c):
    yield from c.wait(0.4)
    yield from rest(c, 0.6)
    found, _corner = handles(c)
    arms = found[1]["arms"]
    # the arm that shows longest on screen, hauled out along itself
    part = max(arms.values(), key=lambda q: (q["tip"] - q["base"]).length)
    yield from along(c, part, 90, 1.0)
    yield from rest(c, 1.4)


def ring(c):
    yield from c.wait(0.4)
    yield from rest(c, 0.6)
    yield from c.move(c.kneady_button("Arm", 0, 2))     # FK, in the column
    yield from c.wait(0.4)
    yield from c.click()                                 # FK on: Bend shows, Reach doesn't
    yield from c.wait(0.8)
    yield from select_row(c, region().buttons[0], "Bend's row")
    yield from one_of(c, LOOKS, 2, 3, "3D Handle", xs=(0.5,))  # In Row | On Item | 3D Handle
    yield from c.wait(0.5)
    yield from handle_shape(c, 0, "RING")
    yield from rest(c, 1.8)


def turn(c):
    yield from c.wait(0.4)
    yield from rest(c, 0.6)
    found, (ox, oy) = handles(c)
    rim = found[0]["rim"]
    # press on its rim where it is farthest from the forearm's middle, then
    # drag a little way round it (a bend of about 35 degrees), a step at a time
    middle = c.kneady_button("Arm", 0, 2)
    start = max(range(48), key=lambda k: (ox + rim[k].x - middle[0]) ** 2 + (oy + rim[k].y - middle[1]) ** 2)
    yield from c.move((ox + rim[start].x, oy + rim[start].y))
    yield from c.wait(0.4)
    yield from c.press()
    yield from c.wait(0.1)
    for k in range(1, 6):
        p = rim[(start + k) % 48]
        yield from c.move((ox + p.x, oy + p.y), 0.16)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.5)
    yield from rest(c, 1.6)


def by_the_elbow(c):
    """The view for the turn clip: its middle nearer the elbow and a little
    further out, so the forearm stays in sight as it swings about the
    elbow."""
    rv3d = c.area().spaces.active.region_3d
    rv3d.view_location, rv3d.view_distance = world(forearm(0.35)), 0.7
    yield 0.3


CLIPS = {"01_handle": handle, "02_quad": quad, "03_haul": haul, "04_ring": ring, "05_turn": turn}
BEFORE = {"04_ring": centered, "05_turn": by_the_elbow}
