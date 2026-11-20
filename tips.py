"""A button's tip.

Greg asked for "Default generated messages that are all about the
interactions that have been built in. Followed by a blurb that the author
writes themselves. Format the generated action text so that it is consistent
between popovers so users get used to 'That shows me what I can do' so they
don't have to read an entire popover message."

Hovering a button for a moment shows, under its name:

- **A row per key**: Drag up / down, Drag left / right, Click, Shift+Click,
  and a program's own keys, each saying what it does there. The key always
  comes from the button's commands, never from the author. That is what
  keeps a tip true when the commands change. What the key does is worded by
  Kneady (rows), unless the author words it (the button's `tip_rows`,
  matched by what a row is about, not by its place). A key held during a
  drag is written after it, as Drag+Alt. With Maya-style navigation, Alt
  held before the press orbits the view, so it is pressed once the drag has
  begun. Greg: "with Maya controls you have to click alt and alt shift after
  drag".
- **The author's message**: what the button is for (`tip_text`).

The drags and the click show by default. These are hidden unless the author
shows them, because repeated on every tip they would be read past:

- the keys that work on every button: Ctrl to snap, Shift for fine steps,
  Alt to switch direction mid-drag
- Shift+Click to pin, except on a button that opens a menu

The status bar says them all, worded the same (hints.hover_items reads these
rows), so a tip and the status bar never disagree.

A tip shows after the mouse has rested on a button for TIP_DELAY, so it does
not flash while the mouse passes over.

**Help** sets how much Kneady says:

- Learn: every row of a tip, the keys that work on every button too, and
  the tutorials.
- Inform: the tips as described above.
- Quiet: no tips. The names and the status bar still show.

Greg: "I'm starting to think of it as 3 proficiencies". It is Quiet rather
than Expert, which would label the person. The level belongs to the person,
not the file. It is kept in Blender's config folder (FILE), so it follows
them into every file and whichever copy of Kneady runs, and a beginner
opening an expert's layout is not made Quiet by it. A factory-startup session
reads and writes no level file, the same way Blender leaves its own
preferences alone then."""

import json
import os
import re
import time

import bpy  # type: ignore

from . import reg
from . import core, errors, menus, placed, props

TIP_DELAY = 0.5                     # seconds on a button before its tip shows
GENERATED_MAX = 48                  # characters of Kneady's own wording before "and N more"
MENU_NAMES = 3                      # a menu's buttons named in its Click row
NAMES = {"ALT": "Alt", "SHIFT": "Shift", "CTRL": "Ctrl"}
UP, ACROSS = "↕", "↔"     # the arrows a drag row shows: up / down, left / right

_KIND_NAMES = {key: name for key, name, _tip in props.KINDS}
_AXIS_NAMES = {key: name for key, name, _tip in props.AXES}
_AXIS_TAIL = re.compile(r"^[+-]?[XYZ]$")
_SIDES = {"+X", "-X", "+Y", "-Y"}


# -- Kneady's own words ------------------------------------------------------------------

def _path_name(path):
    """A data path's last name, as a person reads it: show_wire -> Show
    Wire. For the value of something keyed in brackets, the key:
    key_blocks["Smile"].value -> Smile."""
    attrs = re.findall(r"\.?([A-Za-z_][A-Za-z0-9_]*)", re.sub(r"\[[^\]]*\]", "", path or ""))
    keys = re.findall(r"\[\s*[\"']([^\"']+)[\"']\s*\]", path or "")
    last = attrs[-1] if attrs else ""
    if (not last or last == "value") and keys:
        return keys[-1]
    return last.replace("_", " ").title() if last else (keys[-1] if keys else "")


def command_text(command):
    """One command in a few words: its modifier input, its property's name,
    a program's own summary, or the turn, move or scale and what it moves."""
    if command.program:
        spec = core.command_kind(command)
        if spec is None:
            return command.program
        try:
            return spec["summary"](command) if spec.get("summary") else spec["label"]
        except Exception:               # a program's error: its plain label instead
            errors.caught("a program's summary")
            return spec["label"]
    if command.kind == "INPUT":
        return command.input.strip()
    if command.kind == "PROPERTY":
        return _path_name(command.data_path)
    what = "%s %s" % (_KIND_NAMES.get(command.kind, command.kind.title()), _AXIS_NAMES.get(command.axis, command.axis))
    on = command.bone or (command.target_group if props.grouped(command)
                          else command.target.name if command.target is not None else "")
    return "%s on %s" % (what, on) if on else what


def merged(texts):
    """Several commands' words as one short phrase:

    - names that differ only by an axis or a side share their name
      (End Side +X/-X)
    - all four sides of one become its plural (End Sides)
    - names alike but for their first word share the rest (Start and End
      Sides)

    Past GENERATED_MAX characters, the phrase is the first and how many
    more."""
    groups = []
    for text in texts:
        if not text:
            continue
        head, _space, tail = text.rpartition(" ")
        if head and _AXIS_TAIL.match(tail):
            found = next((g for g in groups if g[0] == head and g[1] is not None), None)
            if found is None:
                groups.append([head, [tail]])
            elif tail not in found[1]:
                found[1].append(tail)
        elif not any(g[0] == text and g[1] is None for g in groups):
            groups.append([text, None])
    words = []
    for head, tails in groups:
        if tails is None:
            words.append(head)
        elif set(tails) == _SIDES:
            words.append(head + "s")
        elif len(tails) == 1:
            words.append("%s %s" % (head, tails[0]))
        else:
            words.append("%s %s" % (head, "/".join(tails)))
    words = list(dict.fromkeys(words))
    # Start Sides, End Sides -> Start and End Sides
    split = [w.split(" ", 1) for w in words]
    if len(words) > 1 and all(len(s) == 2 for s in split) and len({s[1] for s in split}) == 1:
        firsts = [s[0] for s in split]
        words = ["%s and %s %s" % (", ".join(firsts[:-1]), firsts[-1], split[0][1])]
    phrase = ", ".join(words)
    if len(phrase) > GENERATED_MAX and len(words) > 1:
        phrase = "%s and %d more" % (words[0], len(words) - 1)
    return phrase


def drag_text(drag):
    """What a drag direction drives, in Kneady's words."""
    return merged([command_text(c) for c in [drag] + list(drag.more)]) or "Nothing yet"


def _menu_text(region, index):
    """A menu button's Click: the buttons in its menu, the first few named."""
    up = menus.parents(region)
    used = core.buttons_of(region)
    names = [used[j].name for j, p in enumerate(up) if p == index and used[j].show and not core.is_gap(used[j])]
    if not names:
        return "Open its menu"
    more = ", ..." if len(names) > MENU_NAMES else ""
    return "More controls: %s%s" % (", ".join(names[:MENU_NAMES]), more)


def _switch_text(button):
    texts = [command_text(c) for c in [button.switch] + list(button.switch.more)]
    phrase = merged(texts)
    return "Switch %s on or off" % phrase if phrase else "Switch on or off"


def _operator_text(name):
    try:
        return getattr(getattr(bpy.ops, name.split(".")[0]), name.split(".")[1]).get_rna_type().name
    except Exception:                   # not an operator here (its add-on off): its id will do
        return name


def rows(region, index, obj=None):
    """The rows of button `index`'s tip, as Kneady words them. Each is a
    dict of:

      key      - what the row is about
      keys     - the keys, for the status bar's icons
      label    - the key as the tip shows it
      text
      default  - whether it shows unless the author says otherwise

    With `obj`, a click row reads what is open now (Back on an open menu's
    own button, Unpin on a pinned region)."""
    from . import hints
    used = core.buttons_of(region)
    if not 0 <= index < len(used):
        return []
    button = used[index]
    if core.is_gap(button):
        return []
    out = []

    def add(key, keys, label, text, default=True):
        out.append(dict(key=key, keys=tuple(keys), label=label, text=text, default=default))

    handle = placed.is_handle(button)
    if button.action == "TOGGLE":
        add("CLICK", ("LMB",), "Click", _switch_text(button))
    elif button.action == "DRAG":
        if handle and button.handle_shape != "CROSS":
            # a drag along the handle: the one direction it drives (placed.handle_drives)
            key = "UP" if placed.handle_drives(button) else "ACROSS"
            drag = button.up if key == "UP" else button.across
            if drag.enabled:
                add(key, ("DRAG",), "Drag around" if button.handle_shape == "RING" else "Drag", drag_text(drag))
        else:
            for key, drag, arrow in (("UP", button.up, UP), ("ACROSS", button.across, ACROSS)):
                if drag.enabled:
                    add(key, ("DRAG",), "Drag %s" % arrow, drag_text(drag))
        for keys, text in hints.program_hints(button):
            if keys:
                add("KEY:" + "+".join(keys), keys, "Drag+%s" % "+".join(NAMES.get(k, k) for k in keys), text)
        busy = hints.taken(button)
        if not handle and button.single and button.across.enabled and button.up.enabled and "ALT" not in busy:
            add("ALT", ("ALT",), "Drag+Alt", "Switch direction mid-drag", False)
        if "CTRL" not in busy:
            add("CTRL", ("CTRL",), "Drag+Ctrl", "Snap", False)
        if "SHIFT" not in busy:
            add("SHIFT", ("SHIFT",), "Drag+Shift", "Fine", False)
        if not handle:
            if button.opens_menu and menus.can_open(region, index):
                opened = menus.opened(obj, region) if obj is not None else None
                if opened is not None and opened[0] == index:
                    text = "Back" if menus.depth_of(region, index) else "Close these controls"
                else:
                    text = _menu_text(region, index)
                add("CLICK", ("LMB",), "Click", text)
            elif getattr(button, "click_on", False):
                add("CLICK", ("LMB",), "Click", _switch_text(button))
            elif button.run_operator:
                add("CLICK", ("LMB",), "Click", "Run %s" % _operator_text(button.run_operator))
    if not handle and button.action != "GAP":
        pinned = obj is not None and core.kept() == (obj.name, region.id)
        add("PIN", ("SHIFT", "LMB"), "Shift+Click", "Unpin" if pinned else "Keep these controls up",
            bool(button.opens_menu and menus.can_open(region, index)))
    return out


def worded(button, found):
    """`found` (from rows) as the author leaves them. Each row's text is
    theirs where they wrote one. `shown` is as they set it, else the row's
    default. `hidden` marks a row they hid themselves."""
    mine = {r.key: r for r in button.tip_rows}
    out = []
    for row in found:
        item = mine.get(row["key"])
        text = item.text.strip() if item is not None and item.text.strip() else row["text"]
        shown = row["default"] if item is None or item.show == "AUTO" else item.show == "SHOW"
        out.append(dict(row, said=text, shown=shown, hidden=item is not None and item.show == "HIDE"))
    return out


def tip(region, index, obj=None, at=None):
    """(rows shown [dict], message) for button `index`'s tip at Help level
    `at` (the person's own, level(), when None):

    - at Learn, every row except one its author hid
    - at Inform, the rows shown
    - at Quiet, none

    There is no tip at all where it would only say the button's name again
    (a handle named Move Y whose one drag is Move Y)."""
    at = at or level()
    used = core.buttons_of(region)
    if at == "QUIET" or not 0 <= index < len(used):
        return [], ""
    button = used[index]
    found = worded(button, rows(region, index, obj))
    shown = [r for r in found if (not r["hidden"] if at == "LEARN" else r["shown"])]
    message = button.tip_text.strip()
    if not message and len(shown) == 1 and shown[0]["said"].strip().lower() == button.name.strip().lower():
        return [], ""
    return shown, message


def wrap(text, width, measure):
    """`text` in lines no wider than `width`, by `measure` (a line's width)."""
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            trial = (line + " " + word) if line else word
            if line and measure(trial) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


# -- When a tip shows --------------------------------------------------------------------

_SINCE = {"key": None, "t": 0.0}


def on(context=None):
    """Whether tips show at all: at every Help level but Quiet."""
    return level() != "QUIET"


def ready(obj, region, index):
    """Whether the mouse has rested on button `index` for TIP_DELAY. If not
    yet, a timer draws again when it has."""
    key = (obj.name, region.id, index)
    now = time.monotonic()
    if _SINCE["key"] != key:
        _SINCE["key"], _SINCE["t"] = key, now
    if now - _SINCE["t"] >= TIP_DELAY:
        return True
    if not bpy.app.timers.is_registered(_wake):
        bpy.app.timers.register(_wake, first_interval=TIP_DELAY - (now - _SINCE["t"]) + 0.02)
    return False


def gone():
    """The mouse is off every button, so the next one starts its wait
    afresh."""
    _SINCE["key"] = None


def _wake():
    try:
        if _SINCE["key"] is None:
            return None
        left = TIP_DELAY - (time.monotonic() - _SINCE["t"])
        if left > 0.01:
            return left
        core.redraw()
    except Exception:                   # the tip waits for the next hover instead
        errors.caught("the tip's timer")
    return None


# -- The panel ---------------------------------------------------------------------------

_FILL = {"want": None}


def _fill_later(region, index):
    """Add rows for the author to word, straight after this draw (a draw
    cannot write). There is one per row the button's tip has, each empty, so
    Kneady's words show as the field's placeholder."""
    owner = region.id_data
    try:
        path = region.path_from_id()
    except Exception:                   # a region a program gives, with no path to it: no rows to fill
        return
    _FILL["want"] = (type(owner).__name__, owner.name, path, index)
    if not bpy.app.timers.is_registered(_fill):
        bpy.app.timers.register(_fill, first_interval=0.0)


def _fill():
    want, _FILL["want"] = _FILL["want"], None
    if want is None:
        return None
    try:
        kind, name, path, index = want
        owner = (bpy.data.scenes if kind == "Scene" else bpy.data.objects).get(name)
        region = owner.path_resolve(path) if owner is not None else None
        used = core.buttons_of(region) if region is not None else []
        if 0 <= index < len(used):
            button = used[index]
            have = {r.key for r in button.tip_rows}
            for row in rows(region, index):
                if row["key"] not in have:
                    button.tip_rows.add().key = row["key"]
        from . import tree
        tree.redraw_panels()
    except Exception:
        errors.caught("filling a tip's rows")
    return None


def draw_settings(layout, context, region, index):
    """Draw a button's Tip section in its settings, folded to start. Each
    row per key shows the key as it is, a field for what it does (holding
    Kneady's words until the author writes their own), and whether it
    shows. Then comes the author's message."""
    used = core.buttons_of(region)
    if not 0 <= index < len(used) or core.is_gap(used[index]):
        return
    button = used[index]
    header, box = layout.panel_prop(button, "tip_open")
    header.label(text="Tip", icon="QUESTION")
    if box is None:
        return
    found = rows(region, index)
    mine = {r.key: r for r in button.tip_rows}
    if any(r["key"] not in mine for r in found):
        _fill_later(region, index)
    col = box.column(align=True)
    for row in worded(button, found):
        line = col.row(align=True)
        line.context_pointer_set("kneady_button", button)
        split = line.split(factor=0.36, align=True)
        sub = split.row(align=True)
        sub.active = row["shown"]
        sub.label(text=row["label"])
        item = mine.get(row["key"])
        field = split.row(align=True)
        field.active = row["shown"]
        if item is not None:
            field.prop(item, "text", text="", placeholder=row["text"])
        else:
            field.label(text=row["text"])
        op = line.operator("kneady.tip_row_show", text="", emboss=False,
                           icon="HIDE_OFF" if row["shown"] else "HIDE_ON")
        op.key, op.show, op.default = row["key"], not row["shown"], row["default"]
    box.prop(button, "tip_text", text="", placeholder="What this button is for")
    if not found and not button.tip_text:
        box.label(text="Nothing to say yet: give it a command", icon="INFO")


class KNEADY_OT_tip_row_show(bpy.types.Operator):
    """Show this row in the button's tip, or hide it (the status bar still
    says it)"""
    bl_idname = "kneady.tip_row_show"
    bl_label = "Show in Tip"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    key: bpy.props.StringProperty(options={"SKIP_SAVE"})
    show: bpy.props.BoolProperty(options={"SKIP_SAVE"})
    default: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        button = getattr(context, "kneady_button", None)
        if button is None or not self.key:
            return {"CANCELLED"}
        item = next((r for r in button.tip_rows if r.key == self.key), None)
        if item is None:
            item = button.tip_rows.add()
            item.key = self.key
        # Back to Auto where that is what Auto would do, so a later change to
        # Kneady's default still reaches the row
        item.show = "AUTO" if self.show == self.default else ("SHOW" if self.show else "HIDE")
        core.redraw()
        return {"FINISHED"}


# -- Help: how much Kneady says ----------------------------------------------------------

LEVELS = (("LEARN", "Learn", "The tutorials, at the top of the Kneady tab, and every tip complete: each drag "
                             "and click, and the keys that work on every button - Ctrl, Shift, Alt, Shift+Click"),
          ("INFORM", "Inform", "Tips with what each drag and click does, and what the button is for; the keys "
                               "that work on every button are left to the status bar. No tutorials offered, but "
                               "a file's own"),
          ("QUIET", "Quiet", "No tips and no tutorials. Names and the status bar still show"))
# Learn until the person chooses. Greg: "Kneady should start in Learn mode as
# a default so that tutorials are enabled and visible". Kneady's tutorial 0,
# "Learn, Inform and Quiet", shows how to make it say less.
DEFAULT_LEVEL = "LEARN"
FILE = None                     # where the person's level is kept: None for Blender's config folder
_LEVEL = {"value": None}


def _file():
    if FILE is not None:
        return FILE
    if bpy.app.factory_startup:
        return None
    folder = bpy.utils.user_resource("CONFIG", path="kneady", create=False)
    return os.path.join(folder, "help.json") if folder else None


def _read():
    path = _file()
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f).get("help")
    except (TypeError, OSError, ValueError, AttributeError):
        return DEFAULT_LEVEL
    return value if value in {key for key, _n, _d in LEVELS} else DEFAULT_LEVEL


def _write(value):
    path = _file()
    if path is None:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"help": value}, f)
    except OSError as exc:              # a read-only folder: this session keeps it
        print("Kneady: could not keep the Help level: %s" % exc)


def level():
    """The person's Help level: LEARN, INFORM or QUIET."""
    if _LEVEL["value"] is None:
        _LEVEL["value"] = _read()
    return _LEVEL["value"]


def set_level(value):
    if value not in {key for key, _n, _d in LEVELS}:
        raise ValueError("Help is one of %s" % ", ".join(key for key, _n, _d in LEVELS))
    if value != level():
        _LEVEL["value"] = value
        _write(value)
    gone()
    core.redraw()


def _get_level(_self):
    return [key for key, _n, _d in LEVELS].index(level())


def _set_level(_self, index):
    set_level(LEVELS[index][0])


def register():
    bpy.utils.register_class(KNEADY_OT_tip_row_show)
    # On the window manager, which a file does not keep. The value is the
    # person's, read and written through FILE.
    bpy.types.WindowManager.kneady_help = bpy.props.EnumProperty(
        name="Help", items=LEVELS, get=_get_level, set=_set_level,
        description="How much Kneady says as you work - yours, kept for every file")
    _LEVEL["value"] = None              # read afresh: another copy may have changed it


def unregister():
    for fn in (_wake, _fill):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    _SINCE["key"], _FILL["want"] = None, None
    if hasattr(bpy.types.WindowManager, "kneady_help"):
        del bpy.types.WindowManager.kneady_help
    reg.unregister_class(KNEADY_OT_tip_row_show)
