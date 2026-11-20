"""The tutorial's panel, drawn over the 3D view to Greg's design.

It sits at the view's left, where the toolbar is; the toolbar is hidden
while the panel shows and comes back when the panel folds. From the top:

- the clip;
- under the clip, never over it, its controls: an arrow on each side, a dot
  for each clip (the current one a pill) or a count past five, and Pause
  and Loop just inside the arrows;
- where to look;
- the step's text, with the clip's paragraph lit and scrolled into view;
- Back, Reset and Next.

Folded, the panel is a tab. A tutorial with a playlist has a phone button in
its title row, which shows the playlist as a QR code in place of the clip
and text (qrcodegen.py, by Project Nayuki, MIT license).

**The clip** plays through Blender's own FFmpeg. The movie is loaded as an
image and each frame is asked for as it comes due: gl_free, then
gl_load(frame=N), so that gpu.texture.from_image hands over frame N rather
than the first. Measured in windows of Blender 5.2 and 4.2: frame for frame,
under a millisecond a frame at 270 x 480, and 24 frames a second even with a
heavy scene. It is drawn by draw.image_shader, which turns the image's
scene-linear colors into the screen's, because Blender's IMAGE shader shows
them too dark in 5.2.

A step's clips and images play one after another, then round to the first;
an image is held for its seconds. A step without any of its own shows the
tutorial's shared set (tutorials.shares), which keeps its place from step to
step. At an item's end, tutorials.end_of says what comes: the same item
again, the next one, or its last frame held. A trimmed clip plays only its
kept frames (tutorials.trim_of).

**A program adds to it** (add_part): a strip of its own between the clip and
its controls, a button on the clip, words under it, or controls in the
clip's place for a while. These are drawn and clicked just as the panel's
own are.

**The mouse:** a flat gizmo covers the panel, and Blender tries flat gizmos
before any 3D one (Kneady's buttons, another add-on's handles). So a click
on the panel goes to the panel and never selects what is under it. The
panel's keymap gives the mouse wheel to the text. Kneady's hover lets go
while the mouse is over the panel (core.add_cover).
"""

import math
import os
import time

import blf  # type: ignore
import bpy  # type: ignore
import gpu  # type: ignore
from gpu_extras.batch import batch_for_shader  # type: ignore

from . import core, draw, errors, media, qrcodegen, reg, tutorials

# sizes in pixels at an interface scale of 1 (core.ui_scale)
MARGIN = 10.0                      # from the view's left
TOP = 58.0                         # from its top: under its header
BOTTOM = 44.0                      # from its bottom: room for Adjust Last Operation, which sits there
WIDTH = 250.0
PAD = 8.0
HEAD = 26.0                        # the title row
BAR = 26.0                         # the clip's controls
WHERE = 18.0                       # where to look
FOOT = 34.0                        # Back, Reset, Next
MIN_TEXT = 120.0                   # the least of the text kept when the clip shrinks
BUTTON_H = 22.0
ARROW = 24.0
DOTS_MAX = 5                       # past this many clips, a count
DOT, PILL, DOT_GAP = 6.0, 18.0, 8.0
TAB_W, TAB_H = 150.0, 26.0
ROUND = 6.0
TITLE_PX, BODY_PX, SMALL_PX = 13.0, 11.0, 10.0
LINE = 1.45                        # a line's height, in text sizes
PARA_GAP = 7.0
SCROLL_STEP = 40.0
QUIET = 4                          # the QR code's light border, in its squares (the standard's least)

CARD = (0.13, 0.13, 0.13, 0.95)
EDGE = (0.32, 0.32, 0.32, 1.0)
TEXT = (0.92, 0.92, 0.92, 1.0)
DIM = (0.62, 0.62, 0.62, 1.0)
ACCENT = (0.28, 0.52, 0.92, 1.0)   # Blender's selected blue
LIT = (0.28, 0.52, 0.92, 0.22)     # the clip's paragraph
DONE = (0.4, 0.8, 0.45, 1.0)
BUTTON = (0.25, 0.25, 0.25, 1.0)
HOVERED = (1.0, 1.0, 1.0, 0.12)
SCREEN = (0.05, 0.05, 0.05, 1.0)   # behind the clip
PAPER, INK = (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)     # a QR code's: dark on light, as a camera wants

IMAGE_NAME = ".Kneady Tutorial Clip"

# the player: the clip's image, its path, frame count and rate, when it began,
# whether it is held on its last frame
P = {"image": None, "path": None, "key": None, "failed": None, "frames": 0, "fps": 30.0, "t0": 0.0,
     "frame": 0, "paused": None, "still": False, "seconds": 4.0, "ended": False, "scrub": None}
HOVER = {"key": None, "at": None, "since": 0.0}  # since: when the mouse came onto the control
# The clip enlarges under the mouse. Greg: "Could the video enlarge on hover?
# It could overlap the text below but maybe hovering over it doubles it's size
# temporarily until moused off". It grows to ENLARGE times its size, from its
# top-left corner out over the text and the view, once the mouse has been on it
# for ENLARGE_AFTER seconds, so passing over it on the way elsewhere doesn't
# set it off. It stays grown only while the mouse is on the clip's own place,
# so the controls under it are a move away.
ENLARGE = 2.0
ENLARGE_AFTER = 0.2
# A new step flashes in. Greg: "Some kind of flash or quick fadeout/fadein
# effect would make it register more". The panel is washed in the accent color
# and its edge lit, fading over FLASH seconds, while the new step's text and
# clip fade in over the first half. FX["was"] is the (tutorial, step) last
# shown.
FLASH = 0.45
FX = {"was": None, "at": None}
FOLLOW = {"at": None}              # the (step, clip) last scrolled to
_FPS = {}
_WRAPS = {}
_QR = {}                           # text -> (size, dark runs per row), or None when too long


# -- What a program adds ---------------------------------------------------------------------

# The parts programs add to the panel (add_part). Each is a dict; every entry
# but "key" is left out when the part has none:
#   key        its name, which is also the key of its row and its button; its
#              own controls are keyed "<key>/<name>"
#   row        fn(context) -> a height in pixels at an interface scale of 1, for
#              a strip of its own between the clip and its controls; 0 for none
#   button     fn(context) -> "corner" (a small button in the clip's top right
#              corner), "low" (a wide one low in the clip) or None
#   busy       fn() -> whether it has taken over the panel now. While it has,
#              only its own controls answer the mouse, and it draws in the
#              clip's place
#   controls   fn(rects, s) -> {"<key>/<name>": rect}: its own, while busy
#   draw_clip  fn(rects, s): drawn in the clip's place, while busy
#   draw       fn(rects, s): drawn over the clip and its row, after them
#   note       fn() -> (words, color): shown under the clip, in place of where
#              to look; ("", None) for nothing
#   press      fn(context, key, rects, at): a click on its row, its button or
#              one of its controls, `at` in region pixels. Returns DRAG to be
#              told where the mouse goes until it is released, otherwise a
#              message or ""
#   drag       fn(x): the mouse at x, in region pixels, while pressed
#   release    fn(keep): the mouse released (keep True), or Esc or a
#              right-click (keep False)
#   draw_view  fn(context) -> whether it drew in this 3D view in place of the
#              panel - in a window of its own, for example
PARTS = []
DRAG = "<drag>"


def add_part(part):
    if all(p["key"] != part["key"] for p in PARTS):
        PARTS.append(part)


def remove_part(key):
    PARTS[:] = [p for p in PARTS if p["key"] != key]


def _ask(part, name, *args, default=None):
    """Call a part's `name` function with `args`. Returns `default` when the
    part has none, or when it fails; a failure is reported in the console
    rather than taking the panel down."""
    fn = part.get(name)
    if fn is None:
        return default
    try:
        return fn(*args)
    except Exception:                   # an add-on's part must not stop the panel
        errors.caught("the tutorial panel's %s (%s)" % (part["key"], name))
        return default


def busy_part():
    """The part that has the panel now, or None."""
    return next((p for p in PARTS if _ask(p, "busy", default=False)), None)


def part_of(key):
    """The part that `key` (its row, its button or one of its own controls)
    belongs to, or None."""
    name = (key or "").split("/", 1)[0]
    return next((p for p in PARTS if p["key"] == name), None)


def shows_clip():
    """Whether a clip or an image is showing in the panel now."""
    return _image() is not None


# -- Where everything is -------------------------------------------------------------------

def layout(width, height, scale, n_clips=0, current=0, show_me=False, folded=False, left=0.0, watch=False,
           pause=False, loop=False, phone=False, qr=False, rows=(), buttons=(), busy=False):
    """The panel's parts as rectangles (x0, y0, x1, y1) in region pixels, for
    a view `width` by `height`: card, head, close, fold, phone, video, bar,
    prev, pause, loop, next_clip, dots or count, where, show_me, text, foot,
    back, reset and next.

    Folded, there is only the tab, low on the left and right of the toolbar
    (`left` pixels wide), which is back while folded. With the QR code
    showing (`qr`, with `phone`), qr takes the place of the clip and text.

    A program's parts: `rows` [(key, height)] go between the clip and its
    controls, and `buttons` [(key, "corner" or "low")] on the clip. With
    `busy`, a program has the clip's place and the Watch button gives way."""
    s = scale
    x0 = MARGIN * s
    x1 = x0 + WIDTH * s
    if x1 > width - MARGIN * s:                    # a narrow view: as wide as there is room
        x1 = max(x0 + 140 * s, width - MARGIN * s)
    top, bottom = height - TOP * s, BOTTOM * s
    if folded:
        tab = (left + x0, bottom, left + x0 + TAB_W * s, bottom + TAB_H * s)
        return {"card": tab, "tab": tab}
    out = {"card": (x0, bottom, x1, top)}
    head = (x0, top - HEAD * s, x1, top)
    out["head"] = head
    b = HEAD * s
    out["close"] = (x1 - b, head[1], x1, head[3])
    out["fold"] = (x1 - 2 * b, head[1], x1 - b, head[3])
    if phone:
        out["phone"] = (x1 - 3 * b, head[1], x1 - 2 * b, head[3])
    foot = (x0, bottom, x1, bottom + FOOT * s)
    out["foot"] = foot
    y = head[1]
    below = sum(h for _key, h in rows)
    room = y - foot[3] - (BAR + WHERE + MIN_TEXT + below) * s
    if qr and phone:
        out["qr"] = (x0, foot[3], x1, y)
    elif n_clips and room >= 60 * s:               # a view too small for the clip shows the text alone
        vw = x1 - x0 - 2 * PAD * s
        vh = vw * 16.0 / 9.0
        if vh > room:
            vh = room
            vw = vh * 9.0 / 16.0
        cx = 0.5 * (x0 + x1)
        out["video"] = (cx - 0.5 * vw, y - vh, cx + 0.5 * vw, y)
        y -= vh
        for key, h in rows:
            out[key] = (x0, y - h * s, x1, y)
            y -= h * s
        bar = (x0, y - BAR * s, x1, y)
        out["bar"] = bar
        a = ARROW * s
        out["prev"] = (x0 + PAD * s, bar[1], x0 + PAD * s + a, bar[3])
        out["next_clip"] = (x1 - PAD * s - a, bar[1], x1 - PAD * s, bar[3])
        if pause:
            out["pause"] = (out["prev"][2] + 2 * s, bar[1], out["prev"][2] + 2 * s + a, bar[3])
        if loop:
            out["loop"] = (out["next_clip"][0] - 2 * s - a, bar[1], out["next_clip"][0] - 2 * s, bar[3])
        if n_clips <= DOTS_MAX:
            slot = (PILL + DOT_GAP) * s
            left = cx - 0.5 * slot * n_clips
            out["dots"] = [(left + k * slot, bar[1], left + (k + 1) * slot, bar[3]) for k in range(n_clips)]
        else:
            out["count"] = (cx - 30 * s, bar[1], cx + 30 * s, bar[3])
        y = bar[1]
        where = (x0, y - WHERE * s, x1, y)
        out["where"] = where
        if show_me:
            out["show_me"] = (x1 - PAD * s - 64 * s, where[1] + 1 * s, x1 - PAD * s, where[3] - 1 * s)
        v = out["video"]
        bw = min(v[2] - v[0] - 2 * PAD * s, 132 * s)
        low = v[1] + 14 * s
        corner = v[2] - 6 * s
        for key, place in buttons:
            if place == "corner":
                c = 24 * s                             # small, in the clip's top right corner
                out[key] = (corner - c, v[3] - 6 * s - c, corner, v[3] - 6 * s)
                corner -= c + 4 * s
            elif place == "low":
                out[key] = (cx - 0.5 * bw, low, cx + 0.5 * bw, low + BUTTON_H * s)
                low += (BUTTON_H + 6) * s
        if watch and not busy:
            # the clip shown where it is hosted for all, in the browser,
            # when it cannot be shown here
            out["watch"] = (cx - 0.5 * bw, low, cx + 0.5 * bw, low + BUTTON_H * s)
        y = where[1]
    if "qr" not in out:
        out["text"] = (x0 + PAD * s, foot[3] + 2 * s, x1 - PAD * s, max(y - 4 * s, foot[3] + 2 * s))
    bh = BUTTON_H * s
    by0 = foot[1] + 0.5 * (FOOT * s - bh)
    out["back"] = (x0 + PAD * s, by0, x0 + PAD * s + 50 * s, by0 + bh)
    out["reset"] = (out["back"][2] + 4 * s, by0, out["back"][2] + 4 * s + 50 * s, by0 + bh)
    out["next"] = (x1 - PAD * s - 62 * s, by0, x1 - PAD * s, by0 + bh)
    return out


def _in_area(context):
    a = context.area
    return a is not None and tutorials.area(context) is not None and a.as_pointer() == tutorials.S["area"]


def current_layout(context):
    """The panel's layout in the view it plays in, or None."""
    if not tutorials.active() or context.region is None or not _in_area(context):
        return None
    clip = tutorials.clip()
    folded = not tutorials.S["shown"]
    left = 0.0
    if folded and context.space_data is not None and context.space_data.show_region_toolbar:
        tools = next((r for r in context.area.regions if r.type == "TOOLS"), None)
        left = tools.width if tools is not None else 0.0
    n = len(tutorials.clips())
    shown = _image() is not None
    video = tutorials.is_video(clip)
    rows, buttons = [], []
    for part in PARTS:
        h = _ask(part, "row", context, default=0)
        if h:
            rows.append((part["key"], float(h)))
        place = _ask(part, "button", context)
        if place in ("corner", "low"):
            buttons.append((part["key"], place))
    return layout(context.region.width, context.region.height, core.ui_scale(context), n,
                  tutorials.S["clip"], bool(clip and clip.get("show_me")), folded, left, watching(clip),
                  pause=shown and (video or n > 1), loop=shown and video, phone=bool(tutorials.playlist()),
                  qr=tutorials.S["qr"], rows=rows, buttons=buttons, busy=busy_part() is not None)


def watching(clip):
    """Whether the clip's Watch button shows: it has a link to watch it
    online, and it is not showing here - not recorded, downloading, offline,
    failed, or a Blender that cannot play it."""
    return bool(clip and clip.get("watch")) and _image() is None


def watch_label(url):
    host = url.split("/")[2].lower() if url.count("/") >= 2 else ""
    return "Watch on YouTube" if "youtube" in host or "youtu.be" in host else "Watch Online"


# how a link is opened: the browser (the tests put their own here)
OPEN_URL = [lambda url: bpy.ops.wm.url_open(url=url)]


def _inside(rect, x, y):
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def control_at(context, at):
    """What part of the panel is at `at` (region pixels): a control's key,
    "card" for anywhere else on it, or None off it."""
    rects = current_layout(context)
    if rects is None:
        return None
    x, y = at[0], at[1]
    if not _inside(rects["card"], x, y):
        return None
    if "tab" in rects:
        return "tab"
    busy = busy_part()
    if busy is not None and "video" in rects:
        # a program has the panel: its own controls, nothing else
        for key, rect in (_ask(busy, "controls", rects, core.ui_scale(context)) or {}).items():
            if _inside(rect, x, y):
                return key
        return "card"
    keys = ["close", "fold", "phone", "prev", "pause", "loop", "next_clip", "show_me", "watch"]
    keys += [p["key"] for p in PARTS] + ["qr", "video", "next"]
    if tutorials.S["step"] > 0:
        keys.append("back")
    if tutorials.step().get("start"):
        keys.append("reset")
    for key in keys:
        if key in rects and _inside(rects[key], x, y):
            return key
    for k, rect in enumerate(rects.get("dots", [])):
        if _inside(rect, x, y):
            return "dot:%d" % k
    if _inside(rects["text"], x, y):
        return "text"
    return "card"


def covers(context, at):
    return control_at(context, at) is not None


# -- The step's text ------------------------------------------------------------------------

def wrap(text, size, width):
    """`text` in lines no wider than `width` pixels at `size`."""
    key = (text, round(size, 2), int(width))
    if key in _WRAPS:
        return _WRAPS[key]
    blf.size(0, size)
    lines = []
    for part in text.split("\n"):
        line = ""
        for word in part.split(" "):
            trial = word if not line else line + " " + word
            if blf.dimensions(0, trial)[0] <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    if len(_WRAPS) > 400:
        _WRAPS.clear()
    _WRAPS[key] = lines
    return lines


def text_items(step, width, scale):
    """The step's title and paragraphs laid out down the text: [{y: from the
    top, h, lines, size, color, para: the paragraph's index or None}], and the
    whole height."""
    items, y = [], 0.0
    title = step.get("title", "")
    if title:
        size = TITLE_PX * scale
        lines = wrap(title, size, width)
        h = len(lines) * size * LINE
        items.append({"y": y, "h": h, "lines": lines, "size": size, "color": TEXT, "para": None})
        y += h + PARA_GAP * scale
    for k, para in enumerate(step.get("text", [])):
        size = BODY_PX * scale
        lines = wrap(para, size, width - 8 * scale)
        h = len(lines) * size * LINE
        items.append({"y": y, "h": h, "lines": lines, "size": size, "color": TEXT, "para": k})
        y += h + PARA_GAP * scale
    return items, y


def max_scroll(context, rects=None):
    rects = rects or current_layout(context)
    if not rects or "text" not in rects:
        return 0.0
    t = rects["text"]
    _items, total = text_items(tutorials.step(), t[2] - t[0], core.ui_scale(context))
    return max(0.0, total - (t[3] - t[1]))


def scroll_by(context, delta):
    rects = current_layout(context)
    if not rects or "text" not in rects:
        return                                       # the QR code showing: no text to scroll
    tutorials.S["scroll"] = min(max(tutorials.S["scroll"] + delta, 0.0), max_scroll(context))
    if context.area is not None:
        context.area.tag_redraw()


def _follow(context, rects):
    """Scroll the clip's paragraph into view, once each time the clip or
    step changes, while Follow Video is on."""
    at = (tutorials.S["id"], tutorials.S["step"], tutorials.S["clip"])
    if FOLLOW["at"] == at:
        return
    FOLLOW["at"] = at
    clip = tutorials.clip()
    if not tutorials.S["follow"] or clip is None or "text" not in rects:
        return
    t = rects["text"]
    s = core.ui_scale(context)
    items, _total = text_items(tutorials.step(), t[2] - t[0], s)
    item = next((i for i in items if i["para"] == clip.get("paragraph", 0)), None)
    if item is None:
        return
    view = t[3] - t[1]
    scroll = tutorials.S["scroll"]
    if item["y"] < scroll or item["y"] + item["h"] > scroll + view:
        tutorials.S["scroll"] = min(max(item["y"] - 4 * s, 0.0), max_scroll(context, rects))


# -- The clip --------------------------------------------------------------------------------

def can_play():
    """Whether this Blender decodes video: some Linux distributions' builds
    come without FFmpeg."""
    return bool(getattr(bpy.app.build_options, "codec_ffmpeg", False))


def _image():
    img = P["image"]
    if img is None:
        return None
    try:
        img.name                   # a ReferenceError if freed with the file it was in
        return img
    except ReferenceError:
        P["image"] = None
        return None


def _fps(path):
    if path not in _FPS:
        rate = 30.0
        try:
            movie = bpy.data.movieclips.load(path)
            rate = movie.fps or rate
            bpy.data.movieclips.remove(movie)
        except (RuntimeError, ReferenceError):
            pass
        _FPS[path] = rate
    return _FPS[path]


def unload():
    img = _image()
    if img is not None:
        bpy.data.images.remove(img)
    P.update(image=None, path=None, key=None, frames=0, frame=0, paused=None, ended=False, scrub=None)


def _loadable(path):
    """Whether the file at `path` can be shown here: it exists, it has not
    failed to load before, and, for a clip, this Blender decodes video."""
    return (path is not None and os.path.isfile(path) and P["failed"] != path
            and (can_play() or not tutorials.is_video({"file": path})))


def load(path, entry=None):
    """Load the clip or image at `path`, ready to show from its start. Loads
    nothing when it is not there yet or cannot be shown here."""
    unload()
    P.update(path=path, t0=time.perf_counter(), frame=0, paused=None, still=False, ended=False,
             seconds=(entry or {}).get("seconds", tutorials.STILL_SECONDS))
    if not _loadable(path):
        return
    try:
        img = bpy.data.images.load(path, check_existing=False)
    except RuntimeError as exc:
        print("Kneady: cannot show %s: %s" % (path, exc))
        P["failed"] = path
        return
    img.name = IMAGE_NAME
    still = img.source != "MOVIE"
    P.update(image=img, still=still, frames=max(int(img.frame_duration), 1),
             fps=30.0 if still else _fps(path))
    # its clock starts now that it is loaded: opening it took a frame or two
    # in 4.x, and its first frames were skipped
    P["t0"] = time.perf_counter()


def _wanted():
    """(path, key) of what the panel should show now. The key names the
    item, not just its file: the same file twice in a row is two items, and
    a shared item stays one item from step to step (tutorials.shares)."""
    if not tutorials.S["shown"]:
        return None, None
    path = tutorials.clip_path()
    where = "shared" if tutorials.shares() else tutorials.S["step"]
    return path, (tutorials.S["id"], where, tutorials.S["clip"], path)


def _play():
    """The player's timer (_play_step), kept going through an error. Blender
    drops a timer that raises, so one clip that failed to load would stop the
    player for the rest of the step. Instead the error is reported once and
    the player tries again a second later."""
    try:
        return _play_step()
    except Exception:
        errors.caught("the tutorial player")
        return 1.0


def _play_step():
    """One tick of the player's timer:

    - a changed item is loaded (or started again, if it is the same file);
    - an item freed with its file is loaded again;
    - a clip's frames are asked for as they come due;
    - an image is held for its seconds."""
    if not tutorials.active():
        unload()
        return None
    path, key = _wanted()
    img = _image()
    if key != P.get("key"):
        if path is not None and path == P["path"] and img is not None:
            P.update(t0=time.perf_counter(), frame=0, paused=None, ended=False,
                     seconds=(tutorials.clip() or {}).get("seconds", tutorials.STILL_SECONDS))
        else:
            load(path, tutorials.clip())
            img = _image()
        P["key"] = key
    elif img is None and _loadable(path):
        load(path, tutorials.clip())              # freed with the file it was in
        P["key"] = key
        img = _image()
    if img is None:
        if path is None and tutorials.clip_where()[1] == media.DOWNLOADING:
            a = tutorials.area()
            if a is not None:
                a.tag_redraw()                       # to show how far it has got
        return 0.25
    if P["scrub"] is not None and not P["still"]:
        # a frame a program shows (show_frame)
        frame = min(max(int(P["scrub"]), 1), P["frames"])
        if frame != P["frame"]:
            P["frame"] = frame
            if not bpy.app.background:
                img.gl_free()
                img.gl_load(frame=frame)
                _redraw()
        return 0.03
    now = time.perf_counter()
    if not tutorials.S["playing"] or tutorials.S["qr"]:
        # paused - or out of sight behind the QR code, where it waits
        if P["paused"] is None:
            P["paused"] = now - P["t0"]
        return 0.1
    if P["paused"] is not None:
        P["t0"], P["paused"] = now - P["paused"], None
    t = now - P["t0"]
    n = len(tutorials.clips())
    if P["still"]:
        # an image: held for its seconds, then the step's next item, or kept
        if t >= P["seconds"] and tutorials.end_of(tutorials.clip(), n, tutorials.S["loop"]) == "next":
            tutorials.set_clip(tutorials.S["clip"] + 1)
            return 0.0
        return 0.1
    first, last = tutorials.trim_of(tutorials.clip(), P["frames"])
    span = last - first + 1
    f = int(t * P["fps"])
    if f >= span:
        # Played through: play it again, go to the step's next item (round to
        # the first), or hold its last frame until Loop or Play.
        then = tutorials.end_of(tutorials.clip(), n, tutorials.S["loop"])
        if then == "next":
            tutorials.set_clip(tutorials.S["clip"] + 1)
            return 0.0
        if then == "again":
            P["t0"], f, t = now, 0, 0.0
            P["ended"] = False
        else:
            f = span - 1
            if not P["ended"]:
                P["ended"] = True
                _redraw()                            # its button now reads Play
    frame = first + f
    if frame != P["frame"]:
        P["frame"] = frame
        if not bpy.app.background:
            img.gl_free()
            img.gl_load(frame=frame)
            _redraw()
    if P["ended"]:
        return 0.1
    return max(0.002, (f + 1) / P["fps"] - t + 0.0005)


def forget(path):
    """The file at `path` changed on disk (a clip made again). Let go of it,
    since on Windows a file held open can't be replaced, and read it again
    when it is next shown."""
    def same(other):
        return bool(other) and os.path.normcase(os.path.abspath(other)) == os.path.normcase(os.path.abspath(path))
    if same(P["path"]):
        unload()
    for known in [k for k in _FPS if same(k)]:
        del _FPS[known]
    if same(P["failed"]):
        P["failed"] = None


# -- A frame a program shows -------------------------------------------------------------------

def show_frame(frame):
    """Show `frame` of the current clip, counted from 1, in place of the
    frame due by the clock. A program uses it to show, say, the frame under
    a handle being dragged. None plays the clip on from its first kept
    frame."""
    if frame is None:
        if P["scrub"] is None:
            return
        P.update(scrub=None, t0=time.perf_counter(), paused=None, ended=False)
        tutorials.S["playing"] = True
    else:
        P["scrub"] = int(frame)
    _kick()


def _redraw():
    a = tutorials.area()
    if a is not None:
        a.tag_redraw()


def toggle_play():
    """Pause the item showing, or play it on. One held at its end plays from
    its start."""
    if P["ended"]:
        P.update(t0=time.perf_counter(), paused=None, ended=False)
        tutorials.S["playing"] = True
    else:
        tutorials.S["playing"] = not tutorials.S["playing"]


def qr_code(text):
    """`text` as a QR code: (its size in squares, each row's dark runs as
    (from, to), from the top) - None when it is too long for one."""
    if text not in _QR:
        if len(_QR) > 20:
            _QR.clear()
        try:
            code = qrcodegen.QrCode.encode_text(text, qrcodegen.QrCode.Ecc.LOW)    # Ecc raised if that costs nothing
        except ValueError:                                                         # DataTooLongError
            _QR[text] = None
        else:
            n = code.get_size()
            rows = []
            for y in range(n):
                runs, x = [], 0
                while x < n:
                    if code.get_module(x, y):
                        start = x
                        while x < n and code.get_module(x, y):
                            x += 1
                        runs.append((start, x))
                    else:
                        x += 1
                rows.append(runs)
            _QR[text] = (n, rows)
    return _QR[text]


def _kick():
    """Run the player's timer at once, because the clip, the step or what
    shows has changed. A new step is flashed in."""
    _flash_check()
    if bpy.app.timers.is_registered(_play):
        bpy.app.timers.unregister(_play)
    if tutorials.active():
        bpy.app.timers.register(_play, first_interval=0.0, persistent=True)
    else:
        unload()
    a = tutorials.area() if tutorials.active() else None
    if a is not None:
        a.tag_redraw()


# -- Drawing ---------------------------------------------------------------------------------

def _flat():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def _poly(points, color, kind="TRI_FAN"):
    gpu.state.blend_set("ALPHA")           # again each time: drawing text turns it off
    shader = _flat()
    shader.bind()
    shader.uniform_float("color", color)
    batch_for_shader(shader, kind, {"pos": points}).draw(shader)


def _rounded(rect, r):
    from .draw import _rounded as rounded
    x0, y0, x1, y1 = rect
    return rounded(x0, y0, x1, y1, r, steps=4)


def _box(rect, color, r=0.0):
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        return
    if r <= 0.0:
        x0, y0, x1, y1 = rect
        _poly(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), color)
        return
    pts = _rounded(rect, r)
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    _poly([(cx, cy)] + pts, color)


def _edge(rect, color, r, width=1.0):
    pts = _rounded(rect, r)
    gpu.state.blend_set("ALPHA")
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    shader.bind()
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINE_STRIP", {"pos": pts}).draw(shader)


def _lines(points, color, width):
    gpu.state.blend_set("ALPHA")
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    shader.bind()
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)


def _text(text, x, y, size, color, align="LEFT", clip=None):
    """`text` with its baseline at y; `align` LEFT from x, CENTER on it,
    RIGHT to it."""
    blf.size(0, size)
    w = blf.dimensions(0, text)[0]
    if align == "CENTER":
        x -= 0.5 * w
    elif align == "RIGHT":
        x -= w
    blf.color(0, *color)
    if clip is not None:
        blf.enable(0, blf.CLIPPING)
        blf.clipping(0, *clip)
    blf.position(0, x, y, 0.0)
    blf.draw(0, text)
    if clip is not None:
        blf.disable(0, blf.CLIPPING)
    return w


def _middle(rect, size):
    """The baseline that centers capitals of `size` on `rect`."""
    blf.size(0, size)
    return 0.5 * (rect[1] + rect[3]) - 0.5 * blf.dimensions(0, "H")[1]


def _fit(text, size, width):
    """`text` cut with an ellipsis to fit `width`."""
    blf.size(0, size)
    if blf.dimensions(0, text)[0] <= width:
        return text
    while text and blf.dimensions(0, text + "...")[0] > width:
        text = text[:-1]
    return text.rstrip() + "..."


def _button(rect, label, s, key, primary=False, enabled=True, color=None):
    lit = HOVER["key"] == key
    color = color or (ACCENT if primary else BUTTON)
    if not enabled:
        color = (color[0], color[1], color[2], 0.45)
    _box(rect, color, 4 * s)
    if lit and enabled:
        _box(rect, HOVERED, 4 * s)
    size = SMALL_PX * s
    _text(label, 0.5 * (rect[0] + rect[2]), _middle(rect, size), size, TEXT if enabled else DIM, "CENTER")


def _chevron(rect, s, toward, color):
    """A small arrow head in `rect`, pointing "LEFT", "RIGHT" or "UP"."""
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    d = 4.5 * s
    if toward == "LEFT":
        pts = [(cx + 0.5 * d, cy + d), (cx - 0.5 * d, cy), (cx - 0.5 * d, cy), (cx + 0.5 * d, cy - d)]
    elif toward == "RIGHT":
        pts = [(cx - 0.5 * d, cy + d), (cx + 0.5 * d, cy), (cx + 0.5 * d, cy), (cx - 0.5 * d, cy - d)]
    else:
        pts = [(cx - d, cy - 0.5 * d), (cx, cy + 0.5 * d), (cx, cy + 0.5 * d), (cx + d, cy - 0.5 * d)]
    _lines(pts, color, 1.6 * s)


def _cross(rect, s, color):
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    d = 4.0 * s
    _lines([(cx - d, cy - d), (cx + d, cy + d), (cx - d, cy + d), (cx + d, cy - d)], color, 1.6 * s)


def _bars(rect, s, color):
    """Pause: two bars."""
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    for dx in (-4.5 * s, 1.5 * s):
        _box((cx + dx, cy - 5.5 * s, cx + dx + 3 * s, cy + 5.5 * s), color)


def _triangle(rect, s, color):
    """Play: a triangle pointing right."""
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    _poly([(cx - 3.5 * s, cy - 6 * s), (cx + 5.5 * s, cy), (cx - 3.5 * s, cy + 6 * s)], color, "TRIS")


def _loop_arrow(rect, s, color):
    """Loop: a circle round to an arrow head."""
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    r, a0, a1, steps = 5.5 * s, math.radians(60.0), math.radians(360.0), 14
    pts = [(cx + r * math.cos(a0 + (a1 - a0) * k / steps), cy + r * math.sin(a0 + (a1 - a0) * k / steps))
           for k in range(steps + 1)]
    _lines([p for a, b in zip(pts, pts[1:]) for p in (a, b)], color, 1.6 * s)
    # the head at the end, pointing on round, counterclockwise
    ex, ey = pts[-1]
    h = 3.2 * s
    _poly([(ex - h, ey), (ex + h, ey), (ex, ey + 1.4 * h)], color, "TRIS")


def _phone(rect, s, color):
    """A phone: a rounded outline and a line for its button."""
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    body = (cx - 4.5 * s, cy - 7 * s, cx + 4.5 * s, cy + 7 * s)
    _edge(body, color, 2 * s, 1.5 * s)
    _lines([(cx - 1.5 * s, body[1] + 2.5 * s), (cx + 1.5 * s, body[1] + 2.5 * s)], color, 1.5 * s)


def _check(x, y, s, color):
    """A check mark with its foot at (x, y)."""
    _lines([(x - 4 * s, y + 4 * s), (x, y), (x, y), (x + 7 * s, y + 8 * s)], color, 2.0 * s)


def _draw_picture(rect, s, img):
    """The clip's frame or the image, fitted into `rect`, and the pause sign
    while paused."""
    try:
        tex = gpu.texture.from_image(img)
    except Exception:                   # no picture this frame, not no panel
        errors.caught("showing the clip or image %s" % img.name)
        tex = None
    if tex is not None:
        w, h = img.size if img.size[0] and img.size[1] else (9, 16)
        rw, rh = rect[2] - rect[0], rect[3] - rect[1]
        k = min(rw / w, rh / h)
        cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
        x0, x1, y0, y1 = cx - 0.5 * w * k, cx + 0.5 * w * k, cy - 0.5 * h * k, cy + 0.5 * h * k
        draw.draw_texture(tex, x0, y0, x1, y1)        # in the screen's colors (draw.image_shader)
    if not tutorials.S["playing"]:
        # paused: two bars in the middle
        cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
        _box((cx - 22 * s, cy - 22 * s, cx + 22 * s, cy + 22 * s), (0.0, 0.0, 0.0, 0.5), 22 * s)
        for dx in (-6 * s, 3 * s):
            _box((cx + dx, cy - 9 * s, cx + dx + 4 * s, cy + 9 * s), TEXT)


def enlarged_rect(video, region_w, s):
    """The clip at `video` grown to ENLARGE times its size from its top-left
    corner, but shrunk if need be to stay inside the view (its width, and
    BOTTOM's room at the foot). None when it would hardly grow."""
    x0, y0, x1, y1 = video
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    k = min(ENLARGE, (region_w - MARGIN * s - x0) / w, (y1 - BOTTOM * s) / h)
    return (x0, y1 - h * k, x0 + w * k, y1) if k > 1.05 else None


def enlarged(rects, region_w, s, now=None):
    """Where the clip shows enlarged now, or None. It is enlarged when the
    mouse has been on it for ENLARGE_AFTER seconds, a clip or image is
    showing, and nothing else has its place: not the QR code, not a program
    that has taken over the panel, and not the panel folded."""
    if HOVER["key"] != "video" or "video" not in rects or "qr" in rects or "tab" in rects:
        return None
    if busy_part() is not None or _image() is None:
        return None
    if (time.perf_counter() if now is None else now) - HOVER["since"] < ENLARGE_AFTER:
        return None
    return enlarged_rect(rects["video"], region_w, s)


def flash_progress(now=None):
    """How far the new step's flash has got, 0 to 1, or None when no flash
    is playing."""
    if FX["at"] is None:
        return None
    p = ((time.perf_counter() if now is None else now) - FX["at"]) / FLASH
    if p >= 1.0:
        FX["at"] = None
        return None
    return max(0.0, p)


def _flash_check(now=None):
    """Start a flash when the step changed within the tutorial shown, but
    not when a tutorial begins or ends. Returns whether one began."""
    key = (tutorials.S["id"], tutorials.S["step"]) if tutorials.active() else None
    was, FX["was"] = FX["was"], key
    if key is None or was is None or key == was or key[0] != was[0]:
        return False
    FX["at"] = time.perf_counter() if now is None else now
    if not bpy.app.timers.is_registered(_animate):
        bpy.app.timers.register(_animate, first_interval=0.0, persistent=True)
    return True


def _animate():
    """Redraw the view while the flash plays, and once after."""
    a = tutorials.area() if tutorials.active() else None
    if a is not None:
        a.tag_redraw()
    return 1.0 / 60.0 if flash_progress() is not None else None


def _grown():
    """Redraw the view once the clip under the mouse is due to grow."""
    a = tutorials.area() if tutorials.active() else None
    if a is not None:
        a.tag_redraw()
    return None


def _draw_fx(context, rects, s):
    """Over everything: the new step's flash, then the clip enlarged."""
    p = flash_progress()
    if p is not None:
        fade = 1.0 - p
        target = rects["tab"] if "tab" in rects else rects["card"]
        if "tab" not in rects:
            # the new step fades in, over the first half
            veil = max(0.0, 1.0 - 2.0 * p)
            card, head = rects["card"], rects["head"]
            if veil > 0.0:
                _box((card[0] + 1, card[1] + 1, card[2] - 1, head[1]), (CARD[0], CARD[1], CARD[2], 0.9 * veil))
        _box(target, (ACCENT[0], ACCENT[1], ACCENT[2], 0.28 * fade * fade), ROUND * s)
        _edge(target, (ACCENT[0], ACCENT[1], ACCENT[2], fade), ROUND * s, 2.0 * s)
    big = enlarged(rects, context.region.width, s)
    if big is not None:
        _box((big[0] + 5 * s, big[1] - 5 * s, big[2] + 5 * s, big[3] - 5 * s), (0.0, 0.0, 0.0, 0.35), 4 * s)
        _box(big, SCREEN)
        _draw_picture(big, s, _image())
        _edge(big, EDGE, 0.0)


HINT = "Hover to Expand"


def hover_hint(rects, region_w, s):
    """Whether the clip shows its hint that it grows under the mouse. Greg
    asked for "a small overlay at the bottom of the video window that says
    'Hover to Expand'". It shows on a clip or image that would grow (the
    view has room) but is not grown now, and not while a program has taken
    the clip's place."""
    if "video" not in rects or "qr" in rects or "tab" in rects or busy_part() is not None or _image() is None:
        return False
    return HOVER["key"] != "video" and enlarged_rect(rects["video"], region_w, s) is not None


def _draw_video(rects, s):
    rect = rects["video"]
    _box(rect, SCREEN)
    img = _image()
    if img is not None:
        _draw_picture(rect, s, img)
        region = bpy.context.region
        if region is not None and hover_hint(rects, region.width, s):
            size = SMALL_PX * s
            blf.size(0, size)
            tw = blf.dimensions(0, HINT)[0]
            cx, y0 = 0.5 * (rect[0] + rect[2]), rect[1] + 6 * s
            _box((cx - 0.5 * tw - 7 * s, y0, cx + 0.5 * tw + 7 * s, y0 + size + 9 * s), (0.0, 0.0, 0.0, 0.55),
                 0.5 * size + 4.5 * s)
            _text(HINT, cx, y0 + 4.5 * s + 0.15 * size, size, (1.0, 1.0, 1.0, 0.85), "CENTER")
        return
    clip = tutorials.clip()
    _path, status, detail = tutorials.clip_where()
    video = tutorials.is_video(clip)
    if video and not can_play():
        lines = ["This Blender cannot play video"]
    elif status == media.DOWNLOADING:
        lines = ["Downloading" + (" %d%%" % round(100 * detail) if detail is not None else "...")]
    elif status == media.OFFLINE:
        # an extension may download only with Blender's permission
        lines = ["To see this, turn on", "Allow Online Access", "Click to open Preferences"]
    elif status == media.FAILED:
        lines = ["Couldn't download it:", detail or "", "Click to try again"]
    else:
        lines = ["Clip not recorded yet" if video or not (clip or {}).get("file") else "Image not added yet"]
    if clip is not None:
        lines.append(clip.get("file", ""))
    size = SMALL_PX * s
    width = rect[2] - rect[0] - 10 * s
    shown = [part for line in lines if line for part in wrap(line, size, width)]
    step = size * LINE
    cx, top = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3]) + 0.5 * step * len(shown)
    for k, line in enumerate(shown):
        _text(_fit(line, size, width), cx, top - (k + 1) * step + 0.3 * step, size,
              DIM if k < len(shown) - 1 or clip is None else (0.45, 0.45, 0.45, 1.0), "CENTER")
    if "watch" in rects:
        _button(rects["watch"], watch_label(clip["watch"]), s, "watch", primary=True)


def _note():
    """(words, color): what a program says under the clip, or ("", None)."""
    for part in PARTS:
        words, color = _ask(part, "note", default=None) or ("", None)
        if words:
            return words, color
    return "", None


def _draw_bar(rects, s):
    n = len(tutorials.clips())
    k = tutorials.S["clip"] % max(n, 1)
    for key, toward in (("prev", "LEFT"), ("next_clip", "RIGHT")):
        rect = rects[key]
        if HOVER["key"] == key:
            _box(rect, HOVERED, 4 * s)
        _chevron(rect, s, toward, TEXT if n > 1 else DIM)
    if "pause" in rects:
        rect = rects["pause"]
        if HOVER["key"] == "pause":
            _box(rect, HOVERED, 4 * s)
        if tutorials.S["playing"] and not P["ended"]:
            _bars(rect, s, TEXT)
        else:
            _triangle(rect, s, TEXT)
    if "loop" in rects:
        rect = rects["loop"]
        on = tutorials.looping()
        if on:
            _box(rect, LIT, 4 * s)
        if HOVER["key"] == "loop":
            _box(rect, HOVERED, 4 * s)
        _loop_arrow(rect, s, ACCENT if on else DIM)
    if "dots" in rects:
        for j, rect in enumerate(rects["dots"]):
            cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
            if j == k:
                _box((cx - 0.5 * PILL * s, cy - 0.5 * DOT * s, cx + 0.5 * PILL * s, cy + 0.5 * DOT * s), TEXT,
                     0.5 * DOT * s)
            else:
                lit = HOVER["key"] == "dot:%d" % j
                _box((cx - 0.5 * DOT * s, cy - 0.5 * DOT * s, cx + 0.5 * DOT * s, cy + 0.5 * DOT * s),
                     TEXT if lit else DIM, 0.5 * DOT * s)
    else:
        rect = rects["count"]
        size = SMALL_PX * s
        _text("%d / %d" % (k + 1, n), 0.5 * (rect[0] + rect[2]), _middle(rect, size), size, TEXT, "CENTER")
    where = rects["where"]
    clip = tutorials.clip() or {}
    size = SMALL_PX * s
    right = rects["show_me"][0] - 4 * s if "show_me" in rects else where[2] - PAD * s
    words, color = _note()
    label = _fit(words or clip.get("label", ""), size, right - where[0] - PAD * s)
    _text(label, where[0] + PAD * s, _middle(where, size), size, color or DIM)
    if "show_me" in rects:
        _button(rects["show_me"], "Show Me", s, "show_me")


def _draw_qr(rects, s):
    """Draw the tutorial's playlist as a QR code, each square a whole number
    of pixels, with a light border round it. What to do goes above it; the
    address and the way back go below."""
    x0, y0, x1, y1 = rects["qr"]
    link = tutorials.playlist()
    found = qr_code(link)
    size = SMALL_PX * s
    line = size * LINE
    pad = PAD * s
    cx = 0.5 * (x0 + x1)
    if found is None:
        _text("This link is too long for a QR code", cx, 0.5 * (y0 + y1), size, DIM, "CENTER")
        return
    n, rows = found
    cells = n + 2 * QUIET
    gap = 6 * s
    room = min(x1 - x0 - 2 * pad, y1 - y0 - 2 * pad - 3 * line - 2 * gap)
    m = max(1, int(room // cells))                  # pixels per square
    side = m * cells
    tall = line + gap + side + gap + 2 * line
    top = 0.5 * (y0 + y1) + 0.5 * tall
    _text("Watch on your phone", cx, top - 0.7 * line, TITLE_PX * s * 0.92, TEXT, "CENTER")
    left = int(round(cx - 0.5 * side))
    qtop = int(round(top - line - gap))
    _box((left, qtop - side, left + side, qtop), PAPER)
    tris = []
    for y, runs in enumerate(rows):
        ty = qtop - (QUIET + y) * m
        for a, b in runs:
            ax, bx = left + (QUIET + a) * m, left + (QUIET + b) * m
            tris += [(ax, ty - m), (bx, ty - m), (bx, ty), (ax, ty - m), (bx, ty), (ax, ty)]
    if tris:
        _poly(tris, INK, "TRIS")
    shown = link.split("://", 1)[-1]
    shown = shown[4:] if shown.startswith("www.") else shown
    below = qtop - side - gap
    _text(_fit(shown, size, x1 - x0 - 2 * pad), cx, below - 0.75 * line, size, DIM, "CENTER")
    _text("Click to go back", cx, below - 1.75 * line, size, DIM, "CENTER")


def _draw_text(context, rects, s):
    t = rects["text"]
    _follow(context, rects)
    scroll = tutorials.S["scroll"] = min(tutorials.S["scroll"], max_scroll(context, rects))
    items, total = text_items(tutorials.step(), t[2] - t[0], s)
    clip = tutorials.clip()
    lit_para = clip.get("paragraph", 0) if clip is not None else None
    clip_box = (int(t[0]) - 4, int(t[1]), int(t[2]) + 4, int(t[3]))
    for item in items:
        top = t[3] + scroll - item["y"]
        if top - item["h"] > t[3] or top < t[1]:
            continue
        if item["para"] is not None and item["para"] == lit_para and len(tutorials.clips()):
            y0, y1 = max(top - item["h"] - 2 * s, t[1]), min(top + 2 * s, t[3])
            if y1 > y0:
                _box((t[0] - 4 * s, y0, t[2] + 2 * s, y1), LIT, 3 * s)
                _box((t[0] - 4 * s, y0, t[0] - 1 * s, y1), ACCENT)
        indent = 4 * s if item["para"] is not None else 0.0
        line_h = item["size"] * LINE
        for k, line in enumerate(item["lines"]):
            base = top - (k + 1) * line_h + 0.33 * line_h
            if base > t[3] or base + item["size"] < t[1]:
                continue
            _text(line, t[0] + indent, base, item["size"], item["color"], clip=clip_box)
    if total > t[3] - t[1]:
        # a thin bar showing how far down
        view = t[3] - t[1]
        h = max(view * view / total, 16 * s)
        y1 = t[3] - (view - h) * scroll / max(total - view, 1.0)
        _box((t[2] + 3 * s, y1 - h, t[2] + 5 * s, y1), (1.0, 1.0, 1.0, 0.25), 1 * s)


def _draw_foot(rects, s):
    k, n = tutorials.S["step"], len(tutorials.steps())
    if k > 0:
        _button(rects["back"], "Back", s, "back")
    if tutorials.step().get("start"):
        _button(rects["reset"], "Reset", s, "reset")
    finished = tutorials.done()
    ready = finished or not tutorials.can_check()
    if tutorials.previewing() and k + 1 >= n:
        _button(rects["next"], "Next", s, "next", enabled=False)     # a tutorial being written: nothing to finish
    else:
        _button(rects["next"], "Finish" if k + 1 >= n else "Next", s, "next", primary=ready)
    if finished:
        # the last step done is the tutorial done. Greg: "there Should also be
        # acknowledgement that a tutorial is completed. Have it say Completed!"
        size = SMALL_PX * s
        right = rects["next"][0] - 6 * s
        # Kept clear of Back and Reset. As the panel narrows, the tick is left
        # out first, then Done replaces Completed!
        left = max([rects["back"][0]] + [rects[key][2] + 4 * s for key, shown in
                                                  (("back", k > 0), ("reset", bool(tutorials.step().get("start"))))
                                                  if shown])
        word = done_word()
        blf.size(0, size)
        if right - blf.dimensions(0, word)[0] < left:
            word = "Done"
        w = _text(word, right, _middle(rects["next"], size), size, DONE, "RIGHT")
        if right - w - 16 * s >= left:
            _check(right - w - 12 * s, _middle(rects["next"], size), s, DONE)


def done_word():
    """What the panel says beside Next when the step is done: "Completed!" on
    the last step, when the tutorial is over, and "Done" before that, for the
    moment before the next step comes on."""
    return "Completed!" if tutorials.S["step"] + 1 >= len(tutorials.steps()) else "Done"


def _draw():
    context = bpy.context
    for part in PARTS:
        if part.get("draw_view") is not None and _ask(part, "draw_view", context, default=False):
            return
    rects = current_layout(context)
    if rects is None:
        return
    s = core.ui_scale(context)
    gpu.state.blend_set("ALPHA")
    if "tab" in rects:
        tab = rects["tab"]
        _box(tab, CARD, ROUND * s)
        if HOVER["key"] == "tab":
            _box(tab, HOVERED, ROUND * s)
        _edge(tab, EDGE, ROUND * s)
        size = SMALL_PX * s
        _chevron((tab[0], tab[1], tab[0] + TAB_H * s, tab[3]), s, "RIGHT", TEXT)
        _text("Tutorial  %d / %d" % (tutorials.S["step"] + 1, len(tutorials.steps())), tab[0] + TAB_H * s,
              _middle(tab, size), size, TEXT)
        _draw_fx(context, rects, s)
        gpu.state.blend_set("NONE")
        return
    card = rects["card"]
    _box(card, CARD, ROUND * s)
    _edge(card, EDGE, ROUND * s)
    head = rects["head"]
    size = SMALL_PX * s
    counter = "%d / %d" % (tutorials.S["step"] + 1, len(tutorials.steps()))
    blf.size(0, size)
    cw = blf.dimensions(0, counter)[0]
    right = rects["phone" if "phone" in rects else "fold"][0] - 4 * s
    _text(counter, right, _middle(head, size), size, DIM, "RIGHT")
    title = tutorials.titled(tutorials.S["data"], tutorials.S["id"], tutorials.S.get("number"))
    if tutorials.previewing():
        title = "Editing: " + title                  # not a tutorial being played
    title = _fit(title, size, right - cw - 8 * s - head[0] - PAD * s)
    _text(title, head[0] + PAD * s, _middle(head, size), size, TEXT)
    for key in ("fold", "close"):
        if HOVER["key"] == key:
            _box(rects[key], HOVERED, 4 * s)
    _chevron(rects["fold"], s, "UP", TEXT)
    _cross(rects["close"], s, TEXT)
    if "phone" in rects:
        qr = tutorials.S["qr"]
        if qr:
            _box(rects["phone"], LIT, 4 * s)
        if HOVER["key"] == "phone":
            _box(rects["phone"], HOVERED, 4 * s)
        _phone(rects["phone"], s, ACCENT if qr else TEXT)
    if "qr" in rects:
        _draw_qr(rects, s)
    else:
        if "video" in rects:
            busy = busy_part()
            if busy is not None and busy.get("draw_clip") is not None:
                _box(rects["video"], SCREEN)
                _ask(busy, "draw_clip", rects, s)
            else:
                _draw_video(rects, s)
            for part in PARTS:
                _ask(part, "draw", rects, s)
            _draw_bar(rects, s)
        _draw_text(context, rects, s)
    _draw_foot(rects, s)
    _draw_fx(context, rects, s)
    gpu.state.blend_set("NONE")


# -- The mouse -------------------------------------------------------------------------------

class KNEADY_GT_tutorial(bpy.types.Gizmo):
    """The panel, for the mouse: hit wherever the panel is, drawing nothing
    (the draw handler does)."""
    bl_idname = "KNEADY_GT_tutorial"

    def setup(self):
        pass

    def draw(self, _context):
        pass

    def test_select(self, context, location):
        key = control_at(context, location)
        HOVER["at"] = (location[0], location[1])
        if key != HOVER["key"]:
            HOVER["key"] = key
            HOVER["since"] = time.perf_counter()
            if key == "video":
                if bpy.app.timers.is_registered(_grown):          # an earlier hover's timer, now too soon
                    bpy.app.timers.unregister(_grown)
                bpy.app.timers.register(_grown, first_interval=ENLARGE_AFTER + 0.01)
            if context.area is not None:
                context.area.tag_redraw()
        if key is None:
            return -1
        if self.use_tooltip:
            self.use_tooltip = False
        if core.working(context):
            # Kneady's own gizmos are not asked while this one is hit: its
            # hover lets go here (core.add_cover)
            core.hit_at(context, location)
        return 0


class KNEADY_GGT_tutorial(bpy.types.GizmoGroup):
    """The tutorial's panel: a flat gizmo group, which Blender asks before
    any 3D one"""
    bl_idname = "KNEADY_GGT_tutorial"
    bl_label = "Kneady Tutorial"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT"}

    @classmethod
    def poll(cls, context):
        return tutorials.active() and _in_area(context)

    @classmethod
    def setup_keymap(cls, keyconfig):
        """The panel's keymap. A click on the panel belongs to the panel, with
        Ctrl or Shift held too; Alt is left to navigation, since an Alt+drag
        orbits with Maya's keys. The mouse wheel and a trackpad scroll its
        text, and a right-click does nothing."""
        km = keyconfig.keymaps.new(name="Kneady Tutorial", space_type="EMPTY", region_type="WINDOW")
        for mods in ({}, {"shift": True}, {"ctrl": True}):
            km.keymap_items.new("gizmogroup.gizmo_tweak", "LEFTMOUSE", "PRESS", **mods)
        for kind, lines in (("WHEELUPMOUSE", -1), ("WHEELDOWNMOUSE", 1)):
            km.keymap_items.new("kneady.tutorial_scroll", kind, "PRESS").properties.lines = lines
        km.keymap_items.new("kneady.tutorial_scroll", "TRACKPADPAN", "ANY").properties.lines = 0
        km.keymap_items.new("kneady.tutorial_scroll", "RIGHTMOUSE", "PRESS").properties.lines = 0
        return km

    def setup(self, _context):
        gz = self.gizmos.new(KNEADY_GT_tutorial.bl_idname)
        gz.target_set_operator("kneady.tutorial_click")
        gz.use_tooltip = False


def _later(fn):
    """Run `fn` once the click is done: a file opened from inside the gizmo's
    operator would free the gizmo under it."""
    def run():
        fn(bpy.context)
        return None
    bpy.app.timers.register(run, first_interval=0.01)


def act(context, key, at=None):
    """Do what a click on the panel's `key` does. `at` (region pixels) is
    where it landed, for a program's part. Returns a message, or ""."""
    S = tutorials.S
    part = part_of(key)
    if part is not None:
        result = _ask(part, "press", context, key, current_layout(context) or {}, at, default="")
        if result == DRAG:
            _ask(part, "release", True)              # no mouse to follow: let go at once
            result = ""
        tutorials.redraw_panels()
        return result or ""
    if key == "tab":
        tutorials.show(context, True)
    elif key == "fold":
        tutorials.show(context, False)
    elif key == "close" and tutorials.previewing():
        # a preview is hidden; the editor's eye shows it again
        wm = context.window_manager
        if hasattr(wm, "kneady_tutorial_preview"):
            wm.kneady_tutorial_preview = False
        tutorials.end(context)
    elif key == "close":
        if tutorials.can_return():
            _later(tutorials.return_to_file)
        else:
            tutorials.end(context)
    elif key in ("prev", "next_clip"):
        tutorials.set_clip(S["clip"] + (-1 if key == "prev" else 1))
    elif key and key.startswith("dot:"):
        tutorials.set_clip(int(key[4:]))
    elif key == "video":
        status = tutorials.clip_where()[1]
        if status == media.FAILED:
            media.retry(S["data"], tutorials.clip())     # a failed download: try it again
        elif status == media.OFFLINE:
            # where Allow Online Access is: the person turns it on, never Kneady
            try:
                bpy.ops.screen.userpref_show(section="SYSTEM")
            except (RuntimeError, TypeError):
                return "Turn on Allow Online Access in Preferences > System"
        else:
            toggle_play()
        tutorials._changed()
    elif key == "pause":
        toggle_play()
        tutorials._changed()
    elif key == "loop":
        S["loop"] = not tutorials.looping()
        tutorials._changed()
    elif key == "phone":
        S["qr"] = not S["qr"]
        tutorials._changed()
    elif key == "qr":
        S["qr"] = False
        tutorials._changed()
    elif key == "watch":
        clip = tutorials.clip()
        if clip and clip.get("watch", "").startswith("https://"):
            OPEN_URL[0](clip["watch"])
    elif key == "show_me":
        clip = tutorials.clip()
        if clip and clip.get("show_me"):
            return tutorials.show_me(context, clip["show_me"])
    elif key == "back":
        tutorials.back_step(context)
    elif key == "reset":
        tutorials.enter(context, S["step"])
    elif key == "next":
        if S["step"] + 1 < len(tutorials.steps()):
            tutorials.next_step(context)
        elif tutorials.previewing():
            pass                                         # the last step of one being written: nothing to finish
        elif tutorials.can_return():
            _later(tutorials.return_to_file)
        else:
            tutorials.end(context)
    return ""


class KNEADY_OT_tutorial_click(bpy.types.Operator):
    """The tutorial's panel"""
    bl_idname = "kneady.tutorial_click"
    bl_label = "Tutorial"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        at = (event.mouse_region_x, event.mouse_region_y)
        key = control_at(context, at)
        part = part_of(key)
        if part is not None:
            # a program's part: if it asks, it is dragged until the mouse
            # button is released
            result = _ask(part, "press", context, key, current_layout(context) or {}, at, default="")
            tutorials.redraw_panels()
            if result == DRAG:
                self._left, self._part = context.region.x, part["key"]
                context.window_manager.modal_handler_add(self)
                return {"RUNNING_MODAL"}
            if result:
                self.report({"WARNING"}, result)
            return {"FINISHED"}
        message = act(context, key)
        if message:
            self.report({"WARNING"}, message)
        return {"FINISHED"}

    def modal(self, _context, event):
        part = part_of(self._part)
        if part is None:
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            _ask(part, "drag", event.mouse_x - self._left)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            _ask(part, "release", True)
            return {"FINISHED"}
        elif event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            _ask(part, "release", False)
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


class KNEADY_OT_tutorial_scroll(bpy.types.Operator):
    """Scroll the tutorial's text"""
    bl_idname = "kneady.tutorial_scroll"
    bl_label = "Scroll Tutorial"
    bl_options = {"INTERNAL"}

    lines: bpy.props.IntProperty(default=1, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        if event.type == "TRACKPADPAN":
            delta = event.mouse_prev_y - event.mouse_y
            if getattr(context.preferences.inputs, "use_trackpad_natural", False):
                delta = -delta
            scroll_by(context, delta)
        elif self.lines:
            scroll_by(context, self.lines * SCROLL_STEP * core.ui_scale(context))
        return {"FINISHED"}


_HANDLE = []
_classes = (KNEADY_GT_tutorial, KNEADY_GGT_tutorial, KNEADY_OT_tutorial_click, KNEADY_OT_tutorial_scroll)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    _HANDLE.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL"))
    core.add_cover(covers)
    tutorials._LISTENERS.append(_kick)


def unregister():
    if _kick in tutorials._LISTENERS:
        tutorials._LISTENERS.remove(_kick)
    core.remove_cover(covers)
    for fn in (_play, _animate, _grown):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    try:
        unload()
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    for handle in _HANDLE:
        bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
    _HANDLE.clear()
    for cls in reversed(_classes):
        reg.unregister_class(cls)
