"""What the mouse can do, shown in the status bar.

Greg found the gap on a menu of 3D handles: the Side boxes' Alt and Alt+Shift
drags (both sides of an axis, all four sides) showed nowhere on screen, and
the only sign that a button's click opened more handles was a small mark on
its outline. Blender teaches its own keys in the status bar, and Kneady does
the same:

- **Hovering** a region, a button or a 3D handle, the status bar says what a
  drag and a click do there, and which keys change them. Each key is drawn
  as Blender's own key icon, the way its tools show theirs (hover_items). A
  program's drag adds its own keys (the "hints" of add_command_kind's
  `drag`).
- **Holding a key** dims what it does not do, so the one it does stands out.
  The handles a drag would move along with the one under the mouse light up
  too (core.moves_with, and a program's `drag` "also"): for Digit's Side,
  Alt lights the other side of its axis. With Maya-style navigation, Alt
  before a click orbits instead. During the drag the status bar says the
  same, with the mode in effect lit (ops.KNEADY_OT_drag._status).

Blender gives no way to ask which keys are held. And a hint left in the
status bar after the mouse has gone to another editor would be wrong there.
So one small operator (KNEADY_OT_watch_keys) watches the modifier keys and the
mouse in every editor. It passes every event on and costs a few
microseconds."""

import bpy  # type: ignore

from . import reg
from . import core, errors

# a key's icon in the status bar, as Blender's own tools draw them
ICONS = {"DRAG": "MOUSE_LMB_DRAG", "LMB": "MOUSE_LMB", "ALT": "EVENT_ALT", "SHIFT": "EVENT_SHIFT",
         "CTRL": "EVENT_CTRL", "ESC": "EVENT_ESC"}
NAMES = {"DRAG": "Drag", "LMB": "Click", "ALT": "Alt", "SHIFT": "Shift", "CTRL": "Ctrl", "ESC": "Esc"}
# Room after a key icon that is wider than an icon's square, as a separator's
# factor, the way Blender's own status bar spaces its wide key icons
WIDE = {"ALT": 1.5, "CTRL": 1.5, "ESC": 1.5}
MODIFIERS = ("ALT", "SHIFT", "CTRL")
MODIFIER_EVENTS = {"LEFT_ALT", "RIGHT_ALT", "LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL"}

_SHOWN = {"items": [], "key": None, "on": False}


# -- What the status bar says ------------------------------------------------------------

def mark(items, held):
    """Items [(keys, text)] as [(keys, text, dim)]. With modifier keys
    `held`, what they do not do is dimmed. The item whose keys use the most
    of those held stands out, and items that need no modifier stay as they
    are."""
    held = set(held or ())
    if not held:
        return [(keys, text, False) for keys, text in items]
    mods = [set(k for k in keys if k in MODIFIERS) for keys, _t in items]
    fits = [m for m in mods if m and m <= held]
    best = max((len(m) for m in fits), default=0)
    return [(keys, text, bool(m) and not (m <= held and len(m) == best)) for (keys, text), m in zip(items, mods)]


def as_text(items):
    """The items as one line, as a test or the text status reads them."""
    out = []
    for keys, text, *_dim in items:
        out.append("%s: %s" % ("+".join(NAMES.get(k, k) for k in keys), text) if keys else text)
    return "      ".join(out)


def _draw(header, context):
    """The status bar while Kneady says something: its keys and what they do,
    then what Blender's own status bar shows on the right."""
    layout = header.layout
    row = layout.row(align=True)
    for keys, text, dim in _SHOWN["items"]:
        part = row.row(align=True)
        part.active = not dim
        for k in keys:
            part.label(text="", icon=ICONS.get(k, "NONE"))
            if WIDE.get(k):
                part.separator(factor=WIDE[k])
        part.label(text=text)
        row.separator(factor=2.5)
    layout.separator_spacer()
    layout.template_reports_banner()
    layout.template_running_jobs()
    layout.separator_spacer()
    layout.template_status_info()


def show(context, items):
    """Put `items` [(keys, text, dim)] in the status bar, with key icons."""
    _SHOWN["items"] = list(items)
    workspace = getattr(context, "workspace", None) or getattr(bpy.context, "workspace", None)
    if workspace is not None:
        workspace.status_text_set(_draw)
    _SHOWN["on"] = True


def let_go(context):
    """Give the status bar back: to what keeps the hover, if anything does
    (core.idle_status), else to Blender."""
    _SHOWN["items"], _SHOWN["key"], _SHOWN["on"] = [], None, False
    workspace = getattr(context, "workspace", None) or getattr(bpy.context, "workspace", None)
    if workspace is not None:
        workspace.status_text_set(core.idle_status())


def forget():
    """Something else set the status bar (a drag ended), so the next mouse
    move says it again."""
    _SHOWN["key"], _SHOWN["on"] = None, False


# -- What hovering says ------------------------------------------------------------------

def _drag_commands(button):
    if button is None or button.action != "DRAG":
        return []
    return [c for d in (button.across, button.up) if d.enabled for c in [d] + list(d.more)]


def program_hints(button):
    """What a button's program drags say about their own keys, as
    [(keys, text)]: a drag kind's "hints", or its "status" text as one
    line."""
    out = []
    for command in _drag_commands(button):
        drag = core.drag_kind(command)
        if not drag:
            continue
        try:
            if drag.get("hints"):
                found = [(tuple(k), t) for k, t in drag["hints"](command)]
            elif drag.get("status"):
                note = drag["status"](command)
                found = [((), note)] if note else []
            else:
                found = []
        except Exception:                     # a program's error must not stop the hover
            errors.caught("a program's hints")
            found = []
        out += [f for f in found if f not in out]
    return out


def taken(button):
    """The modifier keys a button's program drags read themselves."""
    keys = set()
    for command in _drag_commands(button):
        drag = core.drag_kind(command)
        if drag and drag.get("keys"):
            try:
                keys |= set(drag["keys"](command))
            except Exception:                 # a program's error must not stop the hover
                errors.caught("a program's keys")
    return keys


def hover_items(context, obj, region, index, handle=False):
    """What the status bar says with the mouse on `region` of `obj`, as
    [(keys, text)]. `index` is the button under the mouse, or None on the
    region's faces. `handle` (whether the button shows as a 3D handle) is
    now read from the button itself (placed.is_handle); the argument is kept
    for callers."""
    from . import menus
    used = core.buttons_of(region)
    items = []
    if index is None:
        first = core.first_drag_button(region, obj, shown=True)
        if first is not None:
            items.append((("DRAG",), used[first].name))
    elif 0 <= index < len(used):
        # Every row of the button's tip, whether the tip shows it or not,
        # worded as its author words them (tips.py). That way the status bar
        # and the tip never disagree.
        from . import tips
        for row in tips.worded(used[index], tips.rows(region, index, obj)):
            text = row["said"]
            if row["key"] in ("UP", "ACROSS") and row["label"].endswith((tips.UP, tips.ACROSS)):
                text = "%s %s" % (row["label"][-1], text)
            items.append((row["keys"], text))
    if obj is not None and region is not None and menus.opened(obj, region) is not None:
        items.append((("ESC",), "Close menu"))
    elif core.kept() is not None:
        items.append((("ESC",), "Let go"))
    return items


def _hover_key(keys):
    """What the hint depends on, plus the hovered object and region. The
    hint depends on the hover, whether the mouse is on the region's faces
    (rather than over empty space with the region kept hovered, as Viewport
    Edit or a pin does), the keys, the menu open and the pin."""
    from . import menus
    hover, button = core.STATE.get("hover"), core.STATE.get("button")
    obj = bpy.data.objects.get(hover[0]) if hover is not None else None
    region = core.find_region(obj, hover[1]) if obj is not None and hover[1] is not None else None
    opened = menus.opened(obj, region) if region is not None else None
    hit = core._HIT.get("result")
    on_faces = hit is not None and hover is not None and (hit[0], hit[1]) == (hover[0], hover[1])
    return (hover, button, core.STATE.get("block"), on_faces, keys, opened, core.kept(), core.kept_by()), \
        obj, region


def update(context, keys, in_view):
    """Say what the mouse can do where it is, only when that has changed.
    Off the 3D view, or off every region, say nothing."""
    if not in_view:
        if _SHOWN["on"]:
            let_go(context)
        return
    key, obj, region = _hover_key(keys)
    if key == _SHOWN["key"]:
        return
    _SHOWN["key"] = key
    items = []
    if region is not None and core.working(context):
        index = core.STATE.get("button")
        if index is not None or core.STATE.get("block") or key[3]:
            handles = core.layout_handles(context, obj, region) if index is not None else {}
            items = hover_items(context, obj, region, index, handle=index in handles)
    if items:
        show(context, mark(items, keys))
    elif _SHOWN["on"]:
        let_go(context)


# -- Watching the keys -------------------------------------------------------------------

def watch(context, event):
    """Runs on every mouse move and modifier key, in any editor. It records
    the keys held (core.STATE["keys"]), so the handles a drag would move
    with them light up (core.moves_with), and updates the status bar's
    hint."""
    keys = frozenset(k for k, on in (("ALT", event.alt), ("SHIFT", event.shift), ("CTRL", event.ctrl)) if on)
    if keys != core.STATE.get("keys", frozenset()):
        core.STATE["keys"] = keys
        if core.STATE.get("hover") is not None:
            core.redraw()
    window = context.window
    if window is not None and any(op.bl_idname.startswith(("KNEADY", "DIGIT")) for op in window.modal_operators):
        return                           # a Kneady mode or drag says its own
    if core.STATE.get("dragging"):
        return
    area, view = context.area, context.region
    in_view = area is not None and area.type == "VIEW_3D" and view is not None and view.type == "WINDOW"
    update(context, keys, in_view)


class KNEADY_OT_watch_keys(bpy.types.Operator):
    """Watch the modifier keys and where the mouse is, for the status bar's
    hints - every event passed on"""
    bl_idname = "kneady.watch_keys"
    bl_label = "Kneady Hints"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, "kneady_on", False) or _SHOWN["on"] or bool(core.STATE.get("keys"))

    def invoke(self, context, event):
        try:
            watch(context, event)
        except Exception:                 # never in the way of the event
            errors.caught("the status bar's hints")
        return {"PASS_THROUGH"}


_KEYMAPS = []


def register():
    bpy.utils.register_class(KNEADY_OT_watch_keys)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is not None:
        km = kc.keymaps.new(name="Window", space_type="EMPTY", region_type="WINDOW")
        _KEYMAPS.append((km, km.keymap_items.new(KNEADY_OT_watch_keys.bl_idname, "MOUSEMOVE", "ANY", any=True)))
        for key in sorted(MODIFIER_EVENTS):
            for value in ("PRESS", "RELEASE"):
                _KEYMAPS.append((km, km.keymap_items.new(KNEADY_OT_watch_keys.bl_idname, key, value, any=True)))


def unregister():
    for km, kmi in _KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _KEYMAPS.clear()
    # Give the status bar back to Blender if Kneady's hints are in it: the
    # workspace would otherwise keep calling _draw after Kneady is gone. (This
    # once put back a header draw function Kneady replaced; it no longer
    # replaces one - show() hands Blender _draw through status_text_set.)
    if _SHOWN["on"]:
        workspace = getattr(bpy.context, "workspace", None)
        try:
            if workspace is not None:
                workspace.status_text_set(None)
        except (AttributeError, RuntimeError, ReferenceError):
            pass                        # shutting down, the workspace already gone
    _SHOWN["items"], _SHOWN["key"], _SHOWN["on"] = [], None, False
    reg.unregister_class(KNEADY_OT_watch_keys)
