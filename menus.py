"""Show When and menus. Greg: "Since IK changes control, it would be ideal
if buttons could appear and disappear based on whether another button has
toggled ... A button that exposes more options would hide the other buttons
that were present and display this next level only ... It's sort of local
pie menus."

Show When: a button shows only while a switch is on, or only while it is
off. The switch is a toggle of its region, or any property. So a limb's FK
buttons show in FK and its IK buttons in IK, and a drag on the region runs
its first button that is showing.

Menus: a click on a button that Opens a Menu shows the buttons in its menu,
in a ring around it, and hides the region's other buttons. A drag on it
still runs its own commands (drag the Elbow to swing it, click it for its
axes). The menu closes:

- one level, when its button is clicked again,
- all the way, with Esc,
- when the mouse moves off the region and the area its buttons span,
  unless it was pinned with Shift+click (Pinned, below).

A menu holds at most one sub menu deep. What is open is not saved: a menu
is a place you are, not a setting. A button that opens a menu carries a
small circle on its outline (core.add_badge). The button itself may show
somewhere else while its menu is open - the way back out (back_placed) -
and the ring goes with it.

Both are a filter on the buttons Kneady shows (core.add_button_filter)."""

import math

import bpy  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Vector  # type: ignore

from . import reg
from . import core, errors, placed
from . import props as kn_props
from . import ui as kn_ui

# (object name, region id) -> [(menu button's uid, anchor)], outermost first;
# an anchor is ("placed", None), ("middle", None) or ("point", world point)
OPEN = {}


def key_of(obj, region):
    """The key OPEN keeps a region's menus under."""
    owner = obj if obj is not None else (region.id_data if isinstance(region.id_data, bpy.types.Object) else None)
    return (owner.name if owner is not None else "", region.id)


# -- Show When ----------------------------------------------------------------------------

def _read_switch(drag, obj):
    """Whether a switch command reads on - a property or a modifier input of
    its target, else the object hovered - or None if it cannot be read."""
    target = drag.target or obj
    if target is None:
        return None
    try:
        if drag.program:
            # a program's kind (core.add_command_kind): as the program reads it
            spec = core.command_kind(drag)
            if spec is None or (spec.get("why") and spec["why"](target, drag)):
                return None
            value = 1.0 if spec["read"](target, drag) else 0.0
        elif drag.kind == "PROPERTY":
            value = target.path_resolve(drag.data_path)
        elif drag.kind == "INPUT":
            mod = kn_props._gn_modifier(target, drag.modifier)
            if mod is None or mod.node_group is None:
                return None
            item = next((i for i in mod.node_group.interface.items_tree if i.item_type == "SOCKET"
                         and i.in_out == "INPUT" and i.name == drag.input), None)
            if item is None:
                return None             # the input renamed or gone: no state (the panel says why)
            value = core.input_value(mod, item.identifier)
        else:
            return None
        if getattr(drag, "sets_value", False):
            return abs(float(value) - drag.on_value) < 1e-4
        return (float(value) >= 0.5) != drag.invert
    except Exception:                   # a renamed path or a missing modifier: no state, not no drawing
        errors.caught("reading a toggle's state", trace=False)
        return None


def switch_on(region, button, obj):
    """The state Show When reads for a button: its toggle's (when_toggle, a
    toggle of the same region), else its property's - or None."""
    if button.when_toggle:
        toggle = next((b for b in core.buttons_of(region) if b.name == button.when_toggle
                       and b.action == "TOGGLE"), None)
        return _read_switch(toggle.switch, obj) if toggle is not None else None
    if button.when_path:
        target = button.when_target or obj
        try:
            value = target.path_resolve(button.when_path)
            return float(value) >= 0.5
        except Exception:               # a renamed path: no state, not no drawing
            errors.caught("reading Show When's property %s" % button.when_path, trace=False)
            return None
    return None


def showing(region, button, obj):
    """Whether Show When lets a button show now. A switch that cannot be
    read lets it show."""
    if button.show_when == "ALWAYS":
        return True
    on = switch_on(region, button, obj)
    return True if on is None else on == (button.show_when == "ON")


# -- Which menu a button is in ----------------------------------------------------------
#
# A button in a menu holds the id of the button whose menu it is in
# (menu_parent, that one's uid): a number, so renaming the menu's button or
# moving it keeps its menu.

def uid_index(used, uid):
    """The index among buttons `used` of the one whose id is `uid`, or None."""
    if uid <= 0:
        return None
    return next((i for i, b in enumerate(used) if b.uid == uid), None)


def _parent_of(used, i):
    j = uid_index(used, used[i].menu_parent) if used[i].menu_parent > 0 else None
    return None if j == i else j


def parents(region):
    """For each button in use, the index of the button whose menu it is in,
    or None for the region's own. A button whose menu's button is gone
    counts as the region's own, so nothing is out of reach. So do the
    buttons of menus that would hold each other round in a circle."""
    used = core.buttons_of(region)
    up = [_parent_of(used, i) for i in range(len(used))]
    out = []
    for i in range(len(used)):
        seen, j = {i}, up[i]
        while j is not None and j not in seen:
            seen.add(j)
            j = up[j]
        out.append(up[i] if j is None else None)
    return out


def index_of(region, button):
    return next((i for i, b in enumerate(core.buttons_of(region)) if b == button), None)


# A menu, and one sub menu in it, and no more (Greg: "access to one more sub
# menu and no more"). The region's own buttons are at depth 0, a menu's at
# 1, and a sub menu's at 2, which open no menu.
MAX_DEPTH = 2


def depth_of(region, index, up=None):
    """How many menus deep button `index` is: 0 for the region's own."""
    up = parents(region) if up is None else up
    depth, j = 0, up[index]
    while j is not None and depth <= len(up):
        depth, j = depth + 1, up[j]
    return depth


def can_open(region, index, up=None):
    """Whether button `index` may open a menu: not one in a sub menu."""
    return depth_of(region, index, up) < MAX_DEPTH


def ensure_uid(region, button):
    """The button's id. It is given a new one if it has none, or if it shares
    its id with a button before it - that one keeps the id its menu's
    buttons find."""
    every = list(region.buttons)
    mine = next((k for k, b in enumerate(every) if b == button), None)
    taken = button.uid > 0 and any(b.uid == button.uid for b in every[:mine or 0])
    if button.uid <= 0 or taken:
        button.uid = max((b.uid for b in every), default=0) + 1
    return button.uid


def link_by_name(region, names):
    """Link buttons held in a menu by the name of the menu's button
    (`names`, {index: name}, from before buttons had ids) to that button by
    its id instead. Returns how many were linked."""
    used = core.buttons_of(region)
    for b in used:
        if b.opens_menu and b.uid <= 0:
            ensure_uid(region, b)
    n = 0
    for i, name in names.items():
        if not name or not 0 <= i < len(used) or used[i].menu_parent > 0:
            continue
        j = next((j for j, o in enumerate(used) if o.opens_menu and o.name == name), None)
        if j is None or j == i:
            continue
        used[i].menu_parent = ensure_uid(region, used[j])
        n += 1
    return n


def inside(region, index):
    """The buttons in button `index`'s menu and in their sub menus, as
    indices. They are removed along with it (core.remove_button: a list's
    "remove"). They used to move up a level instead - Greg: "if a user
    deletes a button that has children the children are delted too. Having
    them come up a level is kind of chaotic"."""
    up = parents(region)
    out, frontier = set(), {index}
    while frontier:
        frontier = {j for j, p in enumerate(up) if p in frontier} - out - {index}
        out |= frontier
    return sorted(out)


# -- Menus --------------------------------------------------------------------------------

def opened(obj, region):
    """(index, anchor) of the open menu's button, or None. The anchor is
    where the button is: ("placed", its index), ("middle", None) or
    ("point", a world point). The path holds ids, so a button added, removed
    or moved while a menu is open leaves the menu open."""
    key = key_of(obj, region)
    path = OPEN.get(key)
    if not path:
        return None
    used = core.buttons_of(region)
    uid, anchor = path[-1]
    index = uid_index(used, uid)
    if index is None:
        OPEN.pop(key, None)
        _shut(key)
        return None
    if anchor[0] == "placed":
        return index, ("placed", index)
    return index, anchor


def _filter(region, obj, indices):
    used = core.buttons_of(region)
    top = opened(obj, region)
    up = parents(region)
    out = []
    for i in indices:
        if top is not None:
            if i != top[0] and up[i] != top[0]:
                continue
        elif up[i] is not None:
            continue
        if not showing(region, used[i], obj):
            continue
        out.append(i)
    if top is not None and top[0] not in out:
        # the open menu's button hidden by its own Show When: back out of it
        close(obj, region, all_levels=True)
        return _filter(region, obj, indices)
    return out


def _anchor_of(context, obj, region, index):
    """Where a menu opens: its button's point on the item when placed in 3D,
    else under its circle, at the depth of the region's middle."""
    used = core.buttons_of(region)
    if used[index].placed:
        return ("placed", None)
    view, rv3d = context.region, context.region_data
    circles = dict(core.button_layout(context, obj, region))
    at = circles.get(index)
    middle = core.region_geometry(obj, context.evaluated_depsgraph_get()).get(region.id)
    if at is None or view is None or rv3d is None or middle is None:
        return None
    depth = obj.matrix_world @ ((middle[1] + middle[2]) * 0.5)
    return ("point", view3d_utils.region_2d_to_location_3d(view, rv3d, at, depth))


def open_menu(context, obj, region, index):
    anchor = _anchor_of(context, obj, region, index)
    if anchor is None:
        return False
    uid = ensure_uid(region, core.buttons_of(region)[index])
    OPEN.setdefault(key_of(obj, region), []).append((uid, anchor))
    core.redraw()
    return True


def close(obj, region, all_levels=False):
    key = key_of(obj, region)
    path = OPEN.get(key)
    if not path:
        return False
    if all_levels:
        OPEN.pop(key, None)
    else:
        path.pop()
        if not path:
            OPEN.pop(key, None)
    _shut(key)
    core.redraw()
    return True


# -- Pinned ---------------------------------------------------------------------------------
#
# Greg: "How about a keybind that keeps the current menu open and won't drop
# until the keybind is hit again?" It was made Shift+click, since a click
# opens a menu anyway. Shift+click on a button that opens a menu opens it
# pinned. The region then keeps the hover wherever the mouse goes
# (core.keep), orbiting or crossing other items, and the menu stays open
# through its levels, down into a sub menu and back, until it is closed all
# the way out or with Esc.
#
# Shift+click on the open menu's own button pins it where it is, or lets go
# and leaves it open. Its button wears a strong mark (_badge), and the status
# bar says how it ends. Shift+click on any other button pins its region the
# same way (core.toggle_kept), and that pin outlasts a menu opened and closed
# in it.

PIN_NOTE = "Kneady menu pinned      Esc: close it      Shift+click the menu's button: unpin"

# Stays Open: a menu whose button has Stays Open is pinned by a plain click,
# as Shift+click pins one, and a click in empty space closes it too
# (KNEADY_OT_click_off). It is for a menu of 3D handles, which the mouse
# reaches across other items, as it does Digit's handles. Greg: "Clicking in
# space should drop the handles ... the hover it came from should stay active
# and not switch".
STAYS_NOTE = "Kneady: %s open      Click in empty space or Esc: close it      Click its button: close it"


def pinned(obj, region):
    """Whether the menu open on this object's region is pinned."""
    return core.kept() == key_of(obj, region)


def pin(context, obj, region, on=True, stays=None):
    """Pin the menu open on the region, or let it go. `stays` is the name of
    the menu's button, for a menu that Stays Open, which a click in empty
    space closes too."""
    if on:
        # a region pinned already (core.toggle_kept) stays pinned when its
        # menu closes: only a pin the menu made goes with it (_shut)
        if core.kept() != key_of(obj, region):
            if stays is not None:
                core.keep(context, *key_of(obj, region), note=STAYS_NOTE % stays, by="menu", click_off=True)
            else:
                core.keep(context, *key_of(obj, region), note=PIN_NOTE, by="menu")
    elif pinned(obj, region):
        core.let_go(context)
    core.redraw()


def _shut(key):
    """After a menu has closed all the way out, its pin goes with it. A
    region's own pin, made with Shift+click on a button that opens no menu,
    stays."""
    if key not in OPEN and core.kept() == key and core.kept_by() == "menu":
        core.let_go()


def _clicked(context, obj, region, index):
    """A click on a button that Opens a Menu opens its menu (pinned, if it
    Stays Open), or closes it if it is the one open. A button in a sub menu
    opens nothing (MAX_DEPTH). With Shift, the click opens the menu pinned,
    or pins or unpins the open one where it is."""
    used = core.buttons_of(region)
    if not (0 <= index < len(used)) or not used[index].opens_menu or not can_open(region, index):
        return False
    top = opened(obj, region)
    if core.click_shift():
        if top is not None and top[0] == index:
            pin(context, obj, region, not pinned(obj, region))
        elif open_menu(context, obj, region, index):
            pin(context, obj, region)
        return True
    if top is not None and top[0] == index:
        close(obj, region)
    elif open_menu(context, obj, region, index) and used[index].menu_stays:
        pin(context, obj, region, stays=used[index].name)
    return True


def close_kept(context):
    """Close whatever keeps the hover and let go of it, as Esc does. For a
    menu that Stays Open, that closes every level and switches off what its
    buttons switched on as they opened. A program's keep is let go (its
    release called)."""
    held = core.kept()
    if held is None:
        return
    obj = bpy.data.objects.get(held[0])
    region = core.find_region(obj, held[1]) if obj is not None else None
    if region is not None and key_of(obj, region) in OPEN:
        switch_off_path(context, obj, region)
        close(obj, region, all_levels=True)
    core.let_go(context)


def _heard(operator):
    """Tell a tutorial watching for it about an operator the window
    manager's list never sees: an internal one, as Esc's and a click in
    space's are. The Menus in Use tutorial asks for Esc and for a click in
    space to close a menu. Called only when the operator did something."""
    try:
        from . import tutorials
    except ImportError:
        return
    tutorials.note_event("operator", operator=operator, values={}, label=operator)


class KNEADY_OT_click_off(bpy.types.Operator):
    """A click in empty space closes a menu that Stays Open, and lets go of
    what a program keeps hovered with its handles shown"""
    bl_idname = "kneady.click_off"
    bl_label = "Close on a Click in Space"
    bl_options = {"INTERNAL"}

    # Run by the left button's release in the 3D view (register). A drag (a
    # box select, a handle's, a Kneady drag) keeps its release for itself,
    # so a release that arrives here is a click. Blender's own select has
    # the press. The event is passed on whatever this does.

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return scene is not None and getattr(scene, "kneady_on", False) and core.kept_click_off()

    def invoke(self, context, event):
        region = context.region
        if region is not None and region.type == "WINDOW" and context.region_data is not None:
            if core.in_space(context, (event.mouse_region_x, event.mouse_region_y)):
                close_kept(context)
                _heard("kneady.click_off")
        return {"PASS_THROUGH"}


def _hovered(before, after):
    """When the mouse moves off the region a menu is open on, the menu
    closes."""
    if before is None or before == after:
        return
    for key in [k for k in OPEN if k == (before[0], before[1])]:
        OPEN.pop(key, None)
        _shut(key)


def _over(context, obj, region, editing=False, dragged=None):
    top = opened(obj, region)
    return ring_layout(context, obj, region, top, editing, dragged) if top is not None else None


def home_of(context, obj, region, top):
    """Where the open menu's button is on screen when it is not placed for its
    menu: its point on the item if it is placed in 3D, else where its circle
    was clicked, or the region's middle while its menu's buttons are placed
    by hand. None if that is off screen."""
    _index, anchor = top
    view, rv3d = context.region, context.region_data
    if anchor[0] == "placed":
        found = placed.button_point(obj, region, core.buttons_of(region)[anchor[1]],
                                    context.evaluated_depsgraph_get())
        center = view3d_utils.location_3d_to_region_2d(view, rv3d, found[0]) if found is not None else None
    elif anchor[0] == "middle":
        center = core.region_center(context, obj, region.id)
    else:
        center = view3d_utils.location_3d_to_region_2d(view, rv3d, anchor[1])
    return Vector(center) if center is not None else None


def ring_layout(context, obj, region, top, editing=False, dragged=None):
    """The open menu's circles:

    - its button, the way back, where it was, or where it is placed for its
      menu (back_placed),
    - the buttons in it, in a ring around it: the first at the top, the rest
      clockwise, a circle's spacing from it and from each other. Those
      placed in 3D are at their points instead.
    - while they are placed by hand (`editing`), the one `dragged` where it
      would land, the ring following its button as that is dragged.

    It also gives where the region holds the hover: the disc the ring fills
    (Greg: "clicking off of it would need to be blocked within a range that
    encapsulates the new menu"), and the area every button of the menu spans
    (_spanned)."""
    index, _anchor = top
    view, rv3d = context.region, context.region_data
    shown = core.shown_buttons(region, obj)
    used = core.buttons_of(region)
    center, faint = None, False
    if dragged == index and view is not None and rv3d is not None:
        center = placed.dragged_circle(view, rv3d)[1]
    elif used[index].back_placed:
        found = placed.back_circle(context, obj, region, used[index])
        if found is not None:
            center, faint = found
    if center is None:
        center = home_of(context, obj, region, top)
    if center is None:
        return shown, [], set()
    children = [i for i in shown if i != index and i != dragged]
    ring_kids = [i for i in children if not used[i].placed]
    radius = core.button_radius(context)
    spacing = core.button_spacing(context)
    scale = core.ui_scale(context)
    circles, faded = placed.placed_circles(context, obj, region, [i for i in children if used[i].placed],
                                           editing)
    if dragged != index:
        circles.append((index, center))
        if faint:
            faded.add(index)
    halves = [core.half_size(used[i], context)[0] for i in ring_kids]
    ring = 0.0
    labels = {}
    if dragged != index and len(ring_kids) >= 3:
        # surrounded: no name, and the ring as close as ever. Greg: "The
        # offset center button label is way too far of an offset. Let's not
        # show the center button label". Before that the name sat past the
        # ring's lower right corner, and before that over the button's own
        # lower half, with a brief try under it that widened the ring
        labels[index] = (core.NO_NAME, True)
    if ring_kids:
        n = len(ring_kids)
        chord = 2.0 * max(halves) + spacing - 2.0 * radius
        ring = max(spacing + max(halves) - radius, chord / (2.0 * math.sin(math.pi / n)) if n > 1 else 0.0)
        angles = [math.pi / 2.0 - 2.0 * math.pi * k / n for k in range(n)]
        for i, a in zip(ring_kids, angles):
            circles.append((i, Vector((center.x + ring * math.cos(a), center.y + ring * math.sin(a)))))
            # its name away from the middle: the top one's above, the bottom
            # one's below, those at the sides beside them
            dx, dy = math.cos(a), math.sin(a)
            labels[i] = ("ABOVE" if dy > 0.0 else "BELOW", False) if abs(dy) > abs(dx) + 1e-6 \
                else ("RIGHT" if dx > 0.0 else "LEFT", False)
    handles = {} if editing else placed.handles_for(context, obj, region,
                                                    [(i, c) for i, c in circles if i != index])
    if dragged is not None:
        circles.append(placed.dragged_circle(view, rv3d))
    flat = [(i, c) for i, c in circles if i not in handles]
    faded |= placed.covered(flat, [], {i: core.outline_of(used[i], context) for i, _p in flat})
    reach = ring + max(halves + [core.half_size(used[index], context)[0]]) + core.BUTTON_BLOCK * scale
    spans = circles + [(i, h["tip"]) for i, h in handles.items()]
    return shown, circles, faded, dict(holds=[(center, reach)], areas=_spanned(context, spans, used, scale),
                                       handles=handles, labels=labels)


def _spanned(context, circles, used, scale):
    """The area the open menu's buttons span on screen (its own button, those
    in its ring and those placed in 3D), with the band around them. The
    region keeps the hover anywhere in it, so the mouse can go from one of
    its buttons to another over whatever lies between. Without it, with a
    menu's buttons at a digit's edge, the start cap between them took the
    hover."""
    if len(circles) < 2:
        return []
    band = core.BUTTON_BLOCK * scale
    points = []
    for i, c in circles:
        half, tall = core.half_size(used[i], context)
        if not core.boxed(used[i]):
            r = half + band
            points += [(c.x + r * math.cos(a), c.y + r * math.sin(a))
                       for a in (2.0 * math.pi * k / 16.0 for k in range(16))]
        else:
            points += [(c.x + sx * (half + band), c.y + sy * (tall + band)) for sx in (-1.0, 1.0)
                       for sy in (-1.0, 1.0)]
    return [core.hull(points)]


class KNEADY_OT_close_menu(bpy.types.Operator):
    """Close the open Kneady menu, and let go of a pinned region"""
    bl_idname = "kneady.close_menu"
    bl_label = "Close Menu"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        hover = core.STATE.get("hover")
        return core.kept() is not None or (bool(OPEN) and hover is not None and (hover[0], hover[1]) in OPEN)

    def execute(self, context):
        _heard("kneady.close_menu")
        if not (OPEN and core.STATE.get("hover") is not None and tuple(core.STATE["hover"][:2]) in OPEN):
            core.let_go(context)           # a region pinned without a menu open (core.toggle_kept)
            return {"FINISHED"}
        hover = core.STATE["hover"]
        obj = bpy.data.objects.get(hover[0])
        region = core.find_region(obj, hover[1]) if obj is not None else None
        if region is None:
            OPEN.clear()
            core.let_go(context)
            core.redraw()
            return {"FINISHED"}
        # close the whole menu, every level, with its pin and a region's own
        # pin too (Greg: "Esc should close the whole menu"), and switch off
        # what the click on each of its buttons switched on as it opened
        # (click_on)
        switch_off_path(context, obj, region)
        close(obj, region, all_levels=True)
        core.let_go(context)
        return {"FINISHED"}


def switch_off_path(context, obj, region):
    """Switch off what each open level's button switched on as its menu
    opened (a drag button's Click Switches), for a menu closing with Esc."""
    used = core.buttons_of(region)
    for uid, _anchor in reversed(OPEN.get(key_of(obj, region)) or []):
        index = uid_index(used, uid)
        if index is not None and used[index].action == "DRAG" and core.has_click(used[index]):
            core.switch_click(context, used[index], obj, region, on=False)


def _badge(region, button):
    """A button's mark (core.add_badge). A button that opens a menu is
    marked, and the open menu's own button is marked strongly (2) while the
    menu is pinned."""
    if not button.opens_menu:
        return False
    index = index_of(region, button)
    if index is None or not can_open(region, index):
        return False
    held = core.kept()
    if held is not None and held[1] == region.id:
        path = OPEN.get(held)
        if path and path[-1][0] == button.uid:
            return 2
    return True


def _lists(region, key):
    """The list of every button (the panel's): removing one removes the
    buttons in its menu too (inside)."""
    return dict(remove=inside) if key == "all" else None


def _list_key(region, parent):
    """This module plays menus but builds none. menu_build.py builds them,
    and its list key, added later, is asked first (core.list_key_for). On
    this one alone, a button added goes in the region's own list, never in
    a menu's."""
    return "" if parent is not None else None


def draw_row(layout, context, region, button):
    """In a button's row of the list: a mark if it is placed in 3D - an arrow
    for a 3D handle - and one if it opens a menu."""
    index = index_of(region, button)
    if index is None:
        return
    if button.placed:
        layout.label(text="", icon="EMPTY_SINGLE_ARROW" if placed.is_handle(button) else "ORIENTATION_GIMBAL")
    if button.opens_menu and can_open(region, index):
        layout.label(text="", icon="COLLAPSEMENU")


@bpy.app.handlers.persistent
def _on_load(*_args):
    """After a file is opened, no menu is open in it: a menu is a place you
    are, and another file can reuse an object's name."""
    OPEN.clear()


_KEYMAPS = []


def register():
    bpy.utils.register_class(KNEADY_OT_close_menu)
    bpy.utils.register_class(KNEADY_OT_click_off)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    core.add_button_filter(_filter)
    core.add_click_hook(_clicked)
    core.add_hover_hook(_hovered)
    core.add_badge(_badge)
    core.add_lists(_lists)
    core.add_list_key(_list_key)
    placed.OVER.append(_over)
    kn_ui.BUTTON_ROWS.append(draw_row)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is not None:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        _KEYMAPS.append((km, km.keymap_items.new(KNEADY_OT_close_menu.bl_idname, "ESC", "PRESS")))
        # a click in empty space: the left button's release, which Blender's
        # own select lets through - a drag keeps it (KNEADY_OT_click_off)
        _KEYMAPS.append((km, km.keymap_items.new(KNEADY_OT_click_off.bl_idname, "LEFTMOUSE", "RELEASE")))


def unregister():
    for km, kmi in _KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _KEYMAPS.clear()
    for hooks, fn in ((kn_ui.BUTTON_ROWS, draw_row), (placed.OVER, _over)):
        if fn in hooks:
            hooks.remove(fn)
    core.remove_list_key(_list_key)
    core.remove_lists(_lists)
    core.remove_badge(_badge)
    core.remove_hover_hook(_hovered)
    core.remove_click_hook(_clicked)
    core.remove_button_filter(_filter)
    if core.kept() is not None and core.kept() in OPEN:
        core.let_go()
    OPEN.clear()
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    reg.unregister_class(KNEADY_OT_click_off)
    reg.unregister_class(KNEADY_OT_close_menu)
