"""Make tutorial clips by script, stage one: play the clips in a window and
capture their frames. Scripted clips can be made again automatically
whenever the interface changes - Greg: "having you do all of them so that
they can automatically be updated with UI changes is pretty huge".

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1000 700 \\
        --python dev/clips/record.py -- <script.py> <out folder> [clip ...]

Use make.py, which runs this and then finish.py for each clip. The clip
script names the tutorial, its practice scene and its clips, in order (see
dev/clips/README.md). This script:

- loads Kneady from this repository;
- opens the practice scene without its UI;
- opens the Recording Window, a window of the clips' size holding a copy
  of the 3D view, and sizes it through Windows;
- runs the clip script's setup unseen;
- plays each clip in turn with Blender's event simulation, each carrying
  on from the last as a person following the tutorial would. Every pass
  the window is screenshotted and the time kept, into <out folder>/<clip>/.

The tutorial itself plays in the main window, out of the clips' sight, so
each clip shows its step ticking off and moving on (or says it didn't).

The real mouse is ignored. The cursor is drawn on afterwards (finish.py),
from the path kept here. What the mouse buttons and keys do shows live, as
Screencast Keys shows it: a mouse in the lower left with its button lit,
and the key's name beside it.

Finding a button or field in the sidebar stops the clip's clock, so none of
the search is in the clip. It works by hovering down the sidebar and asking
Blender what is under the mouse (Copy Data Path / Copy Python Command),
which uses the clipboard; the clipboard is put back at the end."""

import ctypes
import importlib.util
import json
import math
import os
import sys
import time
import traceback

import bpy  # type: ignore
import gpu  # type: ignore
import blf  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from gpu_extras.batch import batch_for_shader  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)                  # clip scripts import their helpers (panel.py) from here
KNEADY = importlib.import_module(os.path.basename(REPO))
KNEADY.register()

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SIZE = (720, 1280)
KEY_SHOWN = 1.1                    # seconds a key's name shows after it is pressed
MOUSE_LIT = 0.25                   # and a mouse button stays lit after it is let go
LOOK = 0.035                       # seconds the mouse rests on a spot while finding things
# the key event a typed character sends, where its name isn't the character
KEY_NAMES = dict({" ": "SPACE", ".": "PERIOD", "-": "MINUS", ",": "COMMA", "[": "LEFT_BRACKET",
                  "]": "RIGHT_BRACKET", "/": "SLASH", "=": "EQUAL", "'": "QUOTE", ";": "SEMI_COLON"},
                 **{str(d): w for d, w in enumerate(("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
                                                     "EIGHT", "NINE"))})
# and the characters typed with Shift: the key to press with Shift held
SHIFTED = {"_": "MINUS", '"': "QUOTE", "(": "NINE", ")": "ZERO", "+": "EQUAL", ":": "SEMI_COLON"}


def _load_script(path):
    spec = importlib.util.spec_from_file_location("clip_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kneady(name):
    """One of Kneady's modules, as loaded here."""
    return sys.modules["%s.%s" % (KNEADY.__name__, name)]


# -- The window, through Windows ---------------------------------------------------------------

_U = {}


def _user32():
    if "u" in _U:
        return _U["u"]
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    H, B, I, D = wintypes.HWND, wintypes.BOOL, ctypes.c_int, wintypes.DWORD
    rect = ctypes.POINTER(wintypes.RECT)
    enum = ctypes.WINFUNCTYPE(B, H, wintypes.LPARAM)
    for name, args, result in (
            ("EnumWindows", (enum, wintypes.LPARAM), B),
            ("GetWindowThreadProcessId", (H, ctypes.POINTER(D)), D),
            ("IsWindowVisible", (H,), B), ("GetClassNameW", (H, wintypes.LPWSTR, I), I),
            ("SetWindowTextW", (H, wintypes.LPCWSTR), B),
            ("GetWindowRect", (H, rect), B), ("GetClientRect", (H, rect), B),
            ("SetWindowPos", (H, H, I, I, I, I, wintypes.UINT), B)):
        f = getattr(u, name)
        f.argtypes, f.restype = args, result
    _U.update(u=u, enum=enum, wt=wintypes)
    return u


def _blender_windows():
    u, wt = _user32(), _U["wt"]
    out = []

    def each(hwnd, _lparam):
        owner = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        buf = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, buf, 64)
        if owner.value == os.getpid() and u.IsWindowVisible(hwnd) and buf.value == "GHOST_WindowClass":
            out.append(hwnd)
        return True

    u.EnumWindows(_U["enum"](each), 0)
    return out


def _fit(hwnd, width, height, left=140, top=40):
    """Make the window's inside `width` x `height`, its top left at (left, top)."""
    u, wt = _user32(), _U["wt"]
    outer, inner = wt.RECT(), wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(outer))
    u.GetClientRect(hwnd, ctypes.byref(inner))
    fw = (outer.right - outer.left) - inner.right
    fh = (outer.bottom - outer.top) - inner.bottom
    u.SetWindowPos(hwnd, None, left, top, width + fw, height + fh, 0x0004 | 0x0010)


# -- The clip: where the mouse is, what it does ------------------------------------------------

def _ease(p):
    return p * p * (3.0 - 2.0 * p)


class Clip:
    """What a clip script drives: the mouse and keys in the window, and where
    things are, in window pixels from its lower left. Its actions are
    generators: each `yield` is one pass, with a frame taken, and a number
    yielded waits that many seconds."""

    def __init__(self, win):
        self.win = win
        self.pos = (win.width * 0.8, win.height * 0.3)
        self.restart()

    def restart(self):
        """Start a new clip: its clock starts now, its path and marks empty."""
        self.t0 = time.perf_counter()
        self.paused_at = None
        self.path = [[0.0, 0.0, self.pos, self.pos]]
        self.clicks = []          # [t, x, y]
        self.buttons = {}         # button -> time it was let go, or None while held
        self.keys = []            # [t, caption]
        self.held = {}            # a key held down (hold) -> its caption, shown while held

    # time: the clip's own, stopped while things are found
    def now(self):
        end = self.paused_at if self.paused_at is not None else time.perf_counter()
        return end - self.t0

    def pause(self):
        if self.paused_at is None:
            self.paused_at = time.perf_counter()

    def resume(self):
        if self.paused_at is not None:
            self.t0 += time.perf_counter() - self.paused_at
            self.paused_at = None

    @property
    def paused(self):
        return self.paused_at is not None

    @property
    def unit(self):
        """Blender's interface unit in pixels: a list's row, a button's height."""
        return 20.0 * kneady("core").ui_scale(bpy.context)

    # where things are
    def area(self, kind="VIEW_3D"):
        return next(a for a in self.win.screen.areas if a.type == kind)

    def region(self, kind="WINDOW", area="VIEW_3D"):
        return next(r for r in self.area(area).regions if r.type == kind)

    def point(self, fx, fy):
        """A point by fractions of the window, from its lower left."""
        return (self.win.width * fx, self.win.height * fy)

    def in_region(self, fx, fy, kind="WINDOW"):
        """A point by fractions of one of the 3D view's regions."""
        r = self.region(kind)
        return (r.x + r.width * fx, r.y + r.height * fy)

    def object(self, name, local=(0.0, 0.0, 0.0)):
        """An object's point - its origin, or `local` in its own space - on screen."""
        from mathutils import Vector  # type: ignore
        obj = bpy.data.objects[name]
        region = self.region()
        rv3d = self.area().spaces.active.region_3d
        p = view3d_utils.location_3d_to_region_2d(region, rv3d, obj.matrix_world @ Vector(local))
        return (region.x + p.x, region.y + p.y)

    def frame(self, names, fill=0.7, at=None):
        """Frame the named objects in the view, filling `fill` of it. Given
        `at` (fractions of the window - beside the sidebar, say), their
        middle is put there. Their selection is left as it was."""
        from mathutils import Vector  # type: ignore
        area, region = self.area(), self.region()
        rv3d = area.spaces.active.region_3d
        was = {o.name: o.select_get() for o in bpy.context.view_layer.objects}
        for obj in bpy.context.view_layer.objects:
            obj.select_set(obj.name in names)
        with bpy.context.temp_override(window=self.win, area=area, region=region):
            bpy.ops.view3d.view_selected()
        rv3d.view_distance /= max(fill, 0.05) / 0.7
        for obj in bpy.context.view_layer.objects:
            obj.select_set(was.get(obj.name, False))
        if at is not None:
            rv3d.update()
            middle = sum((Vector(c) for n in names for c in (bpy.data.objects[n].matrix_world @ Vector(b)
                                                              for b in bpy.data.objects[n].bound_box)),
                         Vector()) / (8 * len(names))
            now = view3d_utils.location_3d_to_region_2d(region, rv3d, middle)
            want = (self.win.width * at[0] - region.x, self.win.height * at[1] - region.y)
            a = view3d_utils.region_2d_to_location_3d(region, rv3d, now, middle)
            b = view3d_utils.region_2d_to_location_3d(region, rv3d, want, middle)
            rv3d.view_location += a - b

    def _named(self, region, x, y, wait=LOOK):
        """What Blender names under the mouse at (x, y): a field's full data
        path, a button's Python command, or "". Blender notices where the
        mouse is a moment late, so the first spot of a run is given longer,
        and what is found is confirmed afterwards (_confirm)."""
        self.win.event_simulate("MOUSEMOVE", "NOTHING", x=int(x), y=int(y))
        yield wait
        wm = bpy.context.window_manager
        area = next(a for a in self.win.screen.areas if any(r == region for r in a.regions))
        for op, kw in ((bpy.ops.ui.copy_data_path_button, {"full_path": True}),
                       (bpy.ops.ui.copy_python_command_button, {})):
            wm.clipboard = ""
            try:
                with bpy.context.temp_override(window=self.win, area=area, region=region):
                    op(**kw)
            except RuntimeError:
                continue
            if wm.clipboard:
                return wm.clipboard
        return ""

    def find(self, test, kind="UI", xs=(0.55,), step=7, along=None, look=LOOK, start=None):
        """Find where Blender names something `test` passes, in one of the 3D
        view's regions, and return the middle of that spot. It hovers down
        the region at each of `xs` (fractions of its width) from its top, or
        from `start` (a y) to find the one below something. Given `along`
        (a y), it hovers across the region instead. The clip's clock stops
        meanwhile. A generator; returns (x, y) or None."""
        if isinstance(test, str):
            suffix = test
            test = lambda name: name.endswith(suffix)  # noqa: E731
        self.pause()
        region = self.region(kind)
        found = None
        seen = []
        self.more_below = False                  # something named at the region's foot: more below
        if along is not None:
            hits = []
            for x in range(int(region.x + 4), int(region.x + region.width - 4), max(3, step // 2)):
                name = yield from self._named(region, x, along, wait=0.2 if x == int(region.x + 4) else look)
                if name and name not in seen:
                    seen.append(name)
                if test(name):
                    hits.append(x)
                elif hits:
                    break
            found = (0.5 * (hits[0] + hits[-1]), along) if hits else None
        else:
            for fx in xs:
                x = region.x + region.width * fx
                hits = []
                top = int(start if start is not None else region.y + region.height - 6)
                for y in range(top, int(region.y), -step):
                    name = yield from self._named(region, x, y, wait=0.2 if y == top else look)
                    if name and name not in seen:
                        seen.append(name)
                    if name and y < region.y + 40:
                        self.more_below = True
                    if test(name):
                        hits.append(y)
                    elif hits:
                        break
                if hits:
                    found = (x, 0.5 * (hits[0] + hits[-1]))
                    break
        if found is not None:
            found = yield from self._confirm(region, test, found, hits, along is not None)
        if found is None:
            print("FIND saw, in %s %s: %s" % (kind, "across" if along is not None else "down",
                                              "; ".join(seen) or "nothing"))
        # put the mouse back where the clip has it, before the clock goes on
        self._send("MOUSEMOVE", "NOTHING")
        yield 0.15
        self.resume()
        return found

    def settle(self, test, what, tries=8):
        """Wait until Blender is sure the mouse is on what is sought - it names
        it under the cursor - before a click there. A click before Blender
        has caught up goes to whatever it last saw, and a rename that never
        started sends its letters to the view as shortcuts (an N hid the
        sidebar). The clip's clock stops meanwhile. A generator; raises
        LookupError if Blender never names it."""
        if isinstance(test, str):
            suffix = test
            test = lambda name: name.endswith(suffix)  # noqa: E731
        self.pause()
        x, y = self.pos
        area = self.area()
        # try the sidebar first: where it lies over the view, the view's own
        # region is under the mouse too
        region = next((r for kind in ("UI", "WINDOW") for r in area.regions if r.type == kind
                       and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height), self.region())
        name = ""
        for k in range(tries):
            # nudge a pixel either side in turn: a move to where the mouse
            # already is is no move, and Blender only looks again when it moves
            name = yield from self._named(region, x + (k % 3 - 1), y, wait=0.12)
            if test(name):
                break
        if not test(name):
            around = []
            for dy in (-30, -20, -10, 0, 10, 20, 30):
                seen = yield from self._named(region, x, y + dy, wait=0.15)
                around.append("%+d: %s" % (dy, seen.rsplit(".", 1)[-1] if seen else "-"))
            print("SETTLE around (%d, %d) in %s: %s" % (x, y, region.type, "; ".join(around)))
        self._send("MOUSEMOVE", "NOTHING")
        yield 0.1
        self.resume()
        if not test(name):
            raise LookupError("the mouse is not on %s (Blender names %r there)" % (what, name))

    def must(self, found, what):
        if found is None:
            raise LookupError("could not find %s" % what)
        return found

    def _confirm(self, region, test, found, hits, across):
        """Return `found` (the middle of `hits`) if Blender, with the mouse
        settled there, names what was sought; else the first of the hits
        that does; else None."""
        spots = [found] + [((h, found[1]) if across else (found[0], h)) for h in hits]
        for x, y in spots:
            name = yield from self._named(region, x, y, wait=0.2)
            if test(name):
                return (x, y)
        return None

    def extent(self, test, kind="UI", x=0.55, step=2, first=False):
        """Hover down one of the 3D view's regions at `x` (a fraction of its
        width), and return the top and bottom, in window pixels, of the first
        run of spots where Blender names something `test` passes. With
        `first`, only the first such spot - (top, top). The clip's clock
        stops meanwhile. A generator; (top, bottom) or None."""
        if isinstance(test, str):
            suffix = test
            test = lambda name: name.endswith(suffix)  # noqa: E731
        self.pause()
        region = self.region(kind)
        px = region.x + region.width * x
        hits = []
        top = int(region.y + region.height - 4)
        for y in range(top, int(region.y), -step):
            name = yield from self._named(region, px, y, wait=0.25 if y == top else LOOK)
            if test(name) and first and not hits:
                # confirm it with the mouse settled there: what a quick pass
                # names can be what the mouse has just left
                again = yield from self._named(region, px + 1, y, wait=0.15)
                if not test(again):
                    continue
            if test(name):
                hits.append(y)
                if first:
                    break
            elif hits:
                break
        self._send("MOUSEMOVE", "NOTHING")
        yield 0.15
        self.resume()
        return (hits[0], hits[-1]) if hits else None

    def middle(self, test, xy, kind="UI", reach=1.2, step=3, look=0.1):
        """The true middle, up and down, of the thing near `xy` that Blender
        names and `test` passes. It is hovered slowly, so Blender has caught
        up at each spot. A quick find's middle sits low: Blender names what
        the mouse has just left, so a run reads on past its foot. That
        doesn't matter to a click on it, but is too much for something
        measured from it (a search list's first item). The clip's clock
        stops meanwhile. A generator; (x, y)."""
        if isinstance(test, str):
            suffix = test
            test = lambda name: name.endswith(suffix)  # noqa: E731
        self.pause()
        region = self.region(kind)
        x, y0 = xy
        hits = []
        top = int(y0 + reach * self.unit)
        for y in range(top, int(y0 - reach * self.unit), -step):
            name = yield from self._named(region, x, y, wait=0.25 if y == top else look)
            if test(name):
                hits.append(y)
        self._send("MOUSEMOVE", "NOTHING")
        yield 0.15
        self.resume()
        return (x, 0.5 * (hits[0] + hits[-1])) if hits else xy

    def span(self, test, y, kind="UI", step=4):
        """Hover across one of the 3D view's regions at height `y`, and return
        the left and right ends, in window pixels, of the first run where
        Blender names something `test` passes - a row of buttons for one
        setting, say, as X, Y, Z and All set one axis. The clip's clock stops
        meanwhile. A generator; (left, right) or None."""
        if isinstance(test, str):
            suffix = test
            test = lambda name: name.endswith(suffix)  # noqa: E731
        self.pause()
        region = self.region(kind)
        hits = []
        first = int(region.x + 4)
        for x in range(first, int(region.x + region.width - 4), step):
            name = yield from self._named(region, x, y, wait=0.25 if x == first else LOOK)
            if test(name):
                hits.append(x)
            elif hits:
                break
        self._send("MOUSEMOVE", "NOTHING")
        yield 0.15
        self.resume()
        return (hits[0], hits[-1]) if hits else None

    def tree_row(self, owner, x=0.45, arrow=False):
        """Where Kneady's tree shows `owner`'s row (a region or a button), on
        its name. Blender names every row of a list by the list's selection
        (kneady_row), so a row can't be found by its name. Instead the list's
        top is found by hovering, and the rows are counted down from it:
        only the rows shown, leaving out folded ones (as tree's filter_items
        does), each Blender's unit high. With `arrow`, the spot is on the
        arrow that folds the row instead: 1.72 units in from the sidebar
        region's edge (measured), and a unit further for each level it is
        indented. A generator; (x, y)."""
        tree = kneady("tree")
        rows = bpy.context.window_manager.kneady_rows
        shown, order = [], []
        for k, row in enumerate(rows):
            if row.parent < 0 or row.parent >= k:
                on = True
            else:
                above = tree.owner_of(rows[row.parent])
                on = shown[row.parent] and above is not None and above.tree_open
            shown.append(on)
            if on:
                order.append(k)
        mine = [k for k in order if tree.owner_of(rows[k]) is not None
                and tree.owner_of(rows[k]).as_pointer() == owner.as_pointer()]
        if not mine:
            raise LookupError("%s has no row shown in the tree" % getattr(owner, "name", owner))
        # the list's top: its first row, found hovering down at its left (icons
        # further in name themselves, which would break the run). Its rows are
        # Blender's unit apart
        span = yield from self.extent(lambda n: n.endswith("kneady_row"), x=0.3, step=2, first=True)
        if span is None:
            raise LookupError("the tree is not in the sidebar")
        top = span[0]
        unit = 20.0 * kneady("core").ui_scale(bpy.context)
        y = top + 1.0 - (order.index(mine[0]) + 0.5) * unit
        if arrow:
            return (self.region("UI").x + (1.72 + rows[mine[0]].depth) * unit, y)
        return (self.in_region(x, 0, "UI")[0], y)

    def find_scrolling(self, test, lines=4, tries=8, **kw):
        """`find`, scrolling the sidebar down a few lines at a time until it
        shows. The scrolling is seen in the clip, as a person scrolls. A
        generator; (x, y) or None."""
        found = yield from self.find(test, **kw)
        if found is None:
            # again at a slower pace: Blender may not have caught up with the mouse
            found = yield from self.find(test, look=0.1, **kw)
        for _ in range(tries):
            if found is not None or not self.more_below:
                # stop if found, or if the sidebar ends above its foot: then it
                # can't scroll, and the wheel would pass to the view behind it
                # and zoom
                return found
            yield from self.scroll(lines, self.in_region(0.5, 0.45, "UI"))
            yield from self.wait(0.25)
            found = yield from self.find(test, **kw)
        return found

    def sidebar(self, category):
        """Open the window's sidebar on a tab. A generator, giving it a moment
        to draw."""
        kneady("tutorials").show_sidebar(self.area(), category)
        yield 0.4

    def _pixels(self):
        """The window as it shows now: an array of rows (from its foot) of RGBA."""
        import numpy as np  # type: ignore
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "kneady_clip_look.png")
        with bpy.context.temp_override(window=self.win):
            bpy.ops.screen.screenshot(filepath=path)
        img = bpy.data.images.load(path)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        os.remove(path)
        return px.reshape(h, w, 4)

    def tab(self, category):
        """Where the open sidebar's tab for `category` is, on its edge. Tabs
        are drawn, not buttons Blender can name, and a simulated click
        doesn't open one (clicking down the tab strip crashed Blender 5.2),
        so the tab is found by looking:

        - the tab is opened by script and the window screenshotted;
        - the tab open before is put back and the window screenshotted again;
        - the stretch of the edge that lights up between the two is the tab.

        The clip's clock stops meanwhile. A generator; (x, y), or None."""
        area, ui = self.area(), self.region("UI")
        was = ui.active_panel_category
        self.pause()
        shots = []
        for name in (category, was):
            ui.active_panel_category = name
            area.tag_redraw()
            yield 0.4
            shots.append(self._pixels())
        self.resume()
        x = int(ui.x + ui.width - 0.5 * self.unit)
        lit, dim = (s[:, x, :3].mean(axis=1) for s in shots)
        runs, run = [], []
        for y in range(ui.y, ui.y + ui.height):
            if lit[y] - dim[y] > 0.02:
                run.append(y)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        if not runs:
            print("TAB %s: nothing lit on the sidebar's edge at x %d" % (category, x))
            return None
        best = max(runs, key=len)
        return (x, 0.5 * (best[0] + best[-1]))

    def shown_click(self, then=None):
        """Show a click in the clip - the press lit, the cursor ringed -
        without sending one. It is for what Blender's event simulation can't
        click (a sidebar tab, a search list's item): `then()` does the
        click's work while the press shows instead. A generator."""
        self.buttons["LEFTMOUSE"] = None
        self.clicks.append([self.now(), self.pos[0], self.pos[1]])
        yield
        yield from self.wait(0.08)
        if then is not None:
            then()
        self.buttons["LEFTMOUSE"] = self.now()
        yield

    def click_tab(self, category):
        """A click on a sidebar tab as a person makes it, the tab opened by
        script at that moment, since a simulated click opens none (see
        tab). A generator."""
        def opened():
            self.region("UI").active_panel_category = category
            self.area().tag_redraw()
        yield from self.shown_click(opened)

    def silent_key(self, kind):
        """Press and release a key with nothing shown in the clip, to do what
        a shown click stands for (shown_click) - Enter picking a search
        list's item, say."""
        self._send(kind, "PRESS")
        yield
        self._send(kind, "RELEASE")
        yield

    def kneady_button(self, obj_name, region_index, button_index=0):
        """Where Kneady draws a region's button over the item, now."""
        core = kneady("core")
        obj = bpy.data.objects[obj_name]
        region = obj.kneady.regions[region_index]
        view = self.region()
        with bpy.context.temp_override(window=self.win, area=self.area(), region=view):
            found = dict(core.button_layout(bpy.context, obj, region))
        x, y = found[button_index]
        return (view.x + x, view.y + y)

    # the mouse and keys
    def _send(self, kind, value, **kw):
        x, y = self.pos
        for name, flag in (("ALT", "alt"), ("SHIFT", "shift"), ("CTRL", "ctrl")):
            if flag not in kw and any(k.endswith(name) for k in self.held):
                kw[flag] = True                  # sent with the keys held, as a person's would be
        self.win.event_simulate(kind, value, x=int(round(x)), y=int(round(y)), **kw)

    def place(self, xy):
        """Put the cursor at `xy` at once."""
        self.pos = (float(xy[0]), float(xy[1]))
        t = self.now()
        self.path.append([t, t, self.pos, self.pos])
        self._send("MOUSEMOVE", "NOTHING")
        yield

    def move(self, xy, seconds=None):
        """Ease the cursor to `xy` over `seconds`, else over a time set by the distance."""
        start, end = self.pos, (float(xy[0]), float(xy[1]))
        dist = math.hypot(end[0] - start[0], end[1] - start[1])
        seconds = seconds if seconds is not None else min(0.9, max(0.3, 0.25 + dist / 1500.0))
        t0 = self.now()
        self.path.append([t0, t0 + seconds, start, end])
        while True:
            p = min(1.0, (self.now() - t0) / seconds)
            e = _ease(p)
            self.pos = (start[0] + (end[0] - start[0]) * e, start[1] + (end[1] - start[1]) * e)
            self._send("MOUSEMOVE", "NOTHING")
            yield
            if p >= 1.0:
                return

    def wait(self, seconds):
        t1 = self.now() + seconds
        while self.now() < t1:
            yield

    def press(self, button="LEFTMOUSE", **mods):
        self.buttons[button] = None
        if button == "LEFTMOUSE":
            self.clicks.append([self.now(), self.pos[0], self.pos[1]])
        self._send(button, "PRESS", **mods)
        yield

    def release(self, button="LEFTMOUSE", **mods):
        self.buttons[button] = self.now()
        self._send(button, "RELEASE", **mods)
        yield

    def click(self, button="LEFTMOUSE", hold=0.08, **mods):
        yield from self.press(button, **mods)
        yield from self.wait(hold)
        yield from self.release(button, **mods)

    def rename_click(self):
        """Ctrl+click, to rename a list's row. Blender's event simulation
        sends no double-click, the other way to start a rename."""
        self.keys.append([self.now(), "Ctrl+Click"])
        yield from self.click(ctrl=True)

    def drag(self, xy, seconds=None, button="LEFTMOUSE", **mods):
        yield from self.press(button, **mods)
        yield from self.wait(0.08)
        yield from self.move(xy, seconds)
        yield from self.wait(0.08)
        yield from self.release(button, **mods)

    def key(self, kind, caption=None, **mods):
        """A key pressed and let go - its name shown, as Screencast Keys shows it."""
        names = [n.title() for n, on in (("ctrl", mods.get("ctrl")), ("shift", mods.get("shift")),
                                          ("alt", mods.get("alt"))) if on]
        self.keys.append([self.now(), "+".join(names + [caption or kind.title()])])
        self._send(kind, "PRESS", **mods)
        yield
        self._send(kind, "RELEASE", **mods)
        yield

    def hold(self, kind, caption=None):
        """Press and hold a key - Alt mid-drag, say. Its name shows until it
        is let go (let_go), and every event meanwhile is sent with it held."""
        self.held[kind] = caption or kind.replace("LEFT_", "").title()
        self._send(kind, "PRESS")
        yield

    def let_go(self, kind):
        """Let go of a key held by hold."""
        self.held.pop(kind, None)
        self._send(kind, "RELEASE")
        yield

    def type(self, text, per_key=0.07):
        """Type text into the field being edited, a key at a time. The clip
        shows it as the word, not letter by letter."""
        self.keys.append([self.now(), text])
        for ch in text:
            kind = SHIFTED.get(ch) or KEY_NAMES.get(ch, ch.upper())
            shift = ch in SHIFTED or ch.isupper()
            self._send(kind, "PRESS", unicode=ch, shift=shift)
            yield
            self._send(kind, "RELEASE", shift=shift)
            yield from self.wait(per_key)

    def scroll(self, lines, where=None):
        """Turn the mouse wheel over `where` (the cursor's spot unless
        given): down for lines > 0."""
        if where is not None:
            yield from self.move(where)
        kind = "WHEELDOWNMOUSE" if lines > 0 else "WHEELUPMOUSE"
        for _ in range(abs(lines)):
            self._send(kind, "PRESS")
            yield from self.wait(0.05)


# -- What the mouse and keys do, drawn live in the window --------------------------------------

def _poly(points, color, kind="TRI_FAN", width=3.0):
    if kind in ("LINES", "LINE_STRIP"):
        sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        batch = batch_for_shader(sh, kind, {"pos": points})
        sh.bind()
        sh.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        sh.uniform_float("lineWidth", width)
    else:
        sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        batch = batch_for_shader(sh, kind, {"pos": points})
        sh.bind()
    sh.uniform_float("color", color)
    batch.draw(sh)


def _rounded(x0, y0, x1, y1, r, n=6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _draw_live(state, win_pointer):
    clip = state.get("clip")
    if clip is None or bpy.context.window is None or bpy.context.window.as_pointer() != win_pointer:
        return
    region = bpy.context.region
    now = clip.now()
    ox, oy = -region.x, -region.y              # window pixels to this region's
    x0, y0, w, h = 55 + ox, 30 + oy, 112, 150
    gpu.state.blend_set("ALPHA")
    white = (0.85, 0.85, 0.85, 1.0)
    # light each mouse button while it is held, and a moment after: the part
    # of the mouse's top between its dividers, under its rounded edge
    r, split, top = 26.0, y0 + h * 0.62, y0 + h

    def edge(x):
        dx = max(x0 + r - x, x - (x0 + w - r), 0.0)
        return top - r + math.sqrt(max(0.0, r * r - dx * dx))

    for button, (bx0, bx1) in (("LEFTMOUSE", (x0, x0 + w * 0.36)), ("MIDDLEMOUSE", (x0 + w * 0.36, x0 + w * 0.64)),
                               ("RIGHTMOUSE", (x0 + w * 0.64, x0 + w))):
        held = clip.buttons.get(button, -1.0)
        if held is None or (held >= 0 and now - held < MOUSE_LIT):
            xs = [bx0 + (bx1 - bx0) * k / 12.0 for k in range(13)]
            pts = [(bx0, split)] + [(x, edge(x)) for x in xs] + [(bx1, split)]
            cx, cy = 0.5 * (bx0 + bx1), 0.5 * (split + top)
            _poly([(cx, cy)] + pts + [pts[0]], (0.85, 0.85, 0.85, 0.9))
    outline = _rounded(x0, y0, x0 + w, y0 + h, r)
    _poly(outline + [outline[0]], white, "LINE_STRIP")
    _poly([(x0, split), (x0 + w, split)], white, "LINES")
    _poly([(x0 + w * 0.36, split), (x0 + w * 0.36, top)], white, "LINES")
    _poly([(x0 + w * 0.64, split), (x0 + w * 0.64, top)], white, "LINES")
    # beside it, the keys held, or else the key last pressed
    shown = [k for k in clip.keys if 0.0 <= now - k[0] < KEY_SHOWN]
    if clip.held or shown:
        if clip.held:
            caption, fade = "+".join(clip.held.values()), 1.0
        else:
            t, caption = shown[-1]
            fade = min(1.0, (KEY_SHOWN - (now - t)) / 0.25)
        blf.size(0, 40)
        tw, th = blf.dimensions(0, caption)
        bx, by = x0 + w + 22, y0 + 0.5 * h - 0.5 * th - 14
        _poly(_rounded(bx, by, bx + tw + 32, by + th + 28, 10), (0.08, 0.08, 0.08, 0.75 * fade))
        blf.color(0, 0.95, 0.95, 0.95, fade)
        blf.position(0, bx + 16, by + 14, 0)
        blf.draw(0, caption)
    gpu.state.blend_set("NONE")


# -- The run ------------------------------------------------------------------------------------

def run():
    print("BLENDER %d.%d" % tuple(bpy.app.version[:2]))     # for make.py's tags on the clips
    script_path, out_root = ARGS[0], ARGS[1]
    script = _load_script(script_path)
    names = ARGS[2:] or list(script.CLIPS)
    size = tuple(getattr(script, "SIZE", SIZE))
    state = {"clip": None, "handles": [], "clipboard": bpy.context.window_manager.clipboard, "report": []}

    def steps():
        prefs = bpy.context.preferences
        prefs.view.use_save_prompt = False
        prefs.view.show_tooltips = False
        t = kneady("tutorials")
        folder = getattr(script, "FOLDER", None)
        if folder and folder not in t.FOLDERS:
            t.FOLDERS.append(folder)
        practice = getattr(script, "PRACTICE", None)
        if practice:
            bpy.ops.wm.open_mainfile(filepath=practice, load_ui=False)
            yield 1.0
        main = bpy.context.window_manager.windows[0]
        area = next(a for a in main.screen.areas if a.type == "VIEW_3D")
        region = next(r for r in area.regions if r.type == "WINDOW")
        # start the tutorial in the main window, out of the clips' sight
        tutorial = getattr(script, "TUTORIAL", None)
        if tutorial:
            with bpy.context.temp_override(window=main, area=area, region=region):
                t.begin(bpy.context, tutorial)
            yield 0.5
        before = set(_blender_windows())
        pointers = {w.as_pointer() for w in bpy.context.window_manager.windows}
        with bpy.context.temp_override(window=main, area=area, region=region):
            bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
        yield 0.5
        rec = next(w for w in bpy.context.window_manager.windows if w.as_pointer() not in pointers)
        if tutorial and not getattr(script, "TUTORIALS_PANEL", False):
            # keep the tutorial's own panel out of the clips' sidebar, since it plays in the main
            # window - unless the tutorial is about that panel (Write a Tutorial, about its editor,
            # sets TUTORIALS_PANEL)
            panel, rec_pointer = t.KNEADY_PT_tutorials, rec.as_pointer()
            was_poll = panel.poll.__func__

            def poll(cls, context):
                if context.window is not None and context.window.as_pointer() == rec_pointer:
                    return False
                return was_poll(cls, context)

            panel.poll = classmethod(poll)
        hwnd = next(iter(set(_blender_windows()) - before), None)
        for _ in range(4):
            if hwnd is not None:
                _fit(hwnd, *size)
                _user32().SetWindowTextW(hwnd, "Kneady Clip")
            yield 0.3
        if (rec.width, rec.height) != size:
            raise RuntimeError("the window is %d x %d, not %d x %d" % (rec.width, rec.height, *size))
        clip = Clip(rec)
        clip.pause()
        state["clip"] = clip
        for kind in ("WINDOW", "UI", "HEADER", "TOOLS", "TOOL_HEADER"):
            state["handles"].append((kind, bpy.types.SpaceView3D.draw_handler_add(
                _draw_live, (state, rec.as_pointer()), kind, "POST_PIXEL")))
        # unseen: prime the mouse with a first press (simulated moves reach
        # gizmos only after one), then run the script's setup
        rv = clip.area()
        corner = (rv.x + rv.width * 0.3, rv.y + 60)
        for _ in clip.place(corner):
            pass
        yield 0.1
        layer = bpy.context.view_layer
        chosen = [o.name for o in layer.objects if o.select_get()]
        active = layer.objects.active
        rec.event_simulate("LEFTMOUSE", "PRESS", x=int(corner[0]), y=int(corner[1]))
        rec.event_simulate("LEFTMOUSE", "RELEASE", x=int(corner[0]), y=int(corner[1]))
        yield 0.3
        for o in layer.objects:                   # the click in empty space deselected: reselect
            o.select_set(o.name in chosen)
        layer.objects.active = active
        setup = getattr(script, "SETUP", None)
        if setup is not None:
            for wait in setup(clip):
                yield wait if wait is not None else 0.05
        yield 0.5
        # the clips: a frame taken each pass, the tutorial's step watched
        for name in names:
            out = os.path.join(out_root, name)
            os.makedirs(out, exist_ok=True)
            for old in os.listdir(out):
                if old.endswith(".png") or old == "timeline.json":
                    os.remove(os.path.join(out, old))
            step_before = t.S["step"] if t.active() else None
            # unseen, before the clip starts: set up what it begins from
            # (BEFORE, by clip name) - the view centered again on what moved in
            # the last clip, say
            ready = getattr(script, "BEFORE", {}).get(name)
            if ready is not None:
                clip.pause()
                for wait in ready(clip):
                    yield wait if wait is not None else 0.05
            frames = []
            clip.restart()
            gen = script.CLIPS[name](clip)
            while True:
                if not clip.paused:
                    _screenshot(rec, out, frames, clip)
                try:
                    wait = next(gen)
                except StopIteration:
                    break
                for a in rec.screen.areas:        # drawn again each pass: the live mouse and keys,
                    a.tag_redraw()                # and nothing shown stale
                yield wait if wait is not None else 0.0
            _screenshot(rec, out, frames, clip)
            with open(os.path.join(out, "timeline.json"), "w", encoding="utf-8") as f:
                json.dump({"size": list(size), "frames": frames, "path": clip.path, "clicks": clip.clicks,
                           "clip": name}, f, indent=1)
            line = "RECORDED %s: %d frames over %.2f s" % (name, len(frames), clip.now())
            if step_before is not None:
                yield 1.0                          # time for the step to tick off and move on
                moved = t.S["step"] != step_before or t.done()
                line += ", step %d %s" % (step_before + 1, "done" if moved else "NOT DONE")
            print(line)
            state["report"].append(line)
            sys.stdout.flush()

    gen = steps()

    def tick():
        try:
            wait = next(gen)
            return wait if wait is not None else 0.0
        except StopIteration:
            pass
        except Exception:
            print("RECORD FAILED\n" + traceback.format_exc())
        teardown = getattr(script, "TEARDOWN", None)      # removes what the clips made outside Blender
        if teardown is not None:
            try:
                teardown()
            except Exception:
                print("TEARDOWN FAILED\n" + traceback.format_exc())
        for kind, handle in state["handles"]:
            bpy.types.SpaceView3D.draw_handler_remove(handle, kind)
        bpy.context.window_manager.clipboard = state["clipboard"]
        sys.stdout.flush()
        try:
            win = bpy.context.window_manager.windows[0]
            with bpy.context.temp_override(window=win):
                bpy.ops.wm.quit_blender()
        except Exception:
            os._exit(0)
        return None

    bpy.app.timers.register(tick, first_interval=1.0, persistent=True)


def _screenshot(win, out, frames, clip):
    path = os.path.join(out, "%05d.png" % len(frames))
    with bpy.context.temp_override(window=win):
        bpy.ops.screen.screenshot(filepath=path)
    frames.append([os.path.basename(path), clip.now()])


run()
