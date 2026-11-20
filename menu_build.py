"""Building menus and Show When. Kneady Pro built these until the free
Kneady came to make every feature it plays. Greg: "Since IK changes
control, it would be ideal if buttons could appear and disappear based on
whether another button has toggled ... A button that exposes more options
would hide the other buttons that were present and display this next level
only ... It's sort of local pie menus."

Playing them - which buttons show, a click opening a menu, its ring, the
hover it holds, pinning, Esc - belongs to menus.py. This module builds
them:

- A menu's buttons are rows of the panel's tree under its button
  (kneady/tree.py), added with Add to Its Menu. They used to be a list of
  their own under the button's settings.
- Show When is set on a button.
- Move To sends a button, its menu with it, to the region's own Buttons or
  another menu.
- Copy Menu and Paste Menu carry a button's menu, its sub menus with it,
  into another button's menu or among a region's own buttons."""

import bpy  # type: ignore

from . import reg
from . import core
from . import props as kn_props
from . import tree as kn_tree
from . import ui as kn_ui
# Re-exported on purpose: these names live in menus.py, and are reached through
# this module too, so Kneady Pro and the tests can use either. The noqa
# marker tells linters they are not unused imports.
from .menus import (MAX_DEPTH, OPEN, PIN_NOTE, _clicked, _hovered, can_open, close,  # noqa: F401
                            depth_of, ensure_uid, home_of, index_of, key_of, inside, link_by_name, open_menu,
                            opened, parents, pin, pinned, ring_layout, showing, switch_on, uid_index)
from . import placement


def _height(up, index, seen=()):
    """How many levels of buttons hang below button `index`: 0 for none, 1
    if its menu holds buttons, 2 if one of those holds buttons of its own."""
    kids = [j for j, p in enumerate(up) if p == index and j not in seen]
    return max((1 + _height(up, k, set(seen) | {index}) for k in kids), default=0)



def open_for_placing(obj, region, uid):
    """Open the menu of the button with id `uid` for Place on Surface, with
    the menus around it too. Each opens at its button's point if placed,
    else in the middle of the region - or stays where it is already open, so
    starting from Viewport Edit's icon moves nothing on screen. Returns
    whether it opened."""
    used = core.buttons_of(region)
    j = uid_index(used, uid)
    if j is None or not used[j].opens_menu:
        return False
    up = parents(region)
    chain = []
    while j is not None and len(chain) <= MAX_DEPTH:
        chain.insert(0, j)
        j = up[j]
    key = key_of(obj, region)
    already = dict(OPEN.get(key) or ())
    OPEN[key] = [(ensure_uid(region, used[k]), already.get(used[k].uid) or (("placed", None) if used[k].placed
                                                                            else ("middle", None))) for k in chain]
    core.redraw()
    return True



# -- The panel ----------------------------------------------------------------------------

def draw_button(layout, context, region, button):
    """A button's Show When."""
    col = layout.column(align=True)
    row = col.row(align=True)
    row.prop(button, "show_when", text="Show")
    if button.show_when != "ALWAYS":
        row.prop_search(button, "when_toggle", region, "buttons", text="", icon="CHECKBOX_HLT")
        if not button.when_toggle:
            sub = col.row(align=True)
            sub.prop(button, "when_target", text="")
            sub.prop(button, "when_path", text="")



def menu_key(button):
    """The key of a button's menu among the panel's lists (core.button_list)."""
    return "menu_%d" % button.uid


def draw_menu(layout, context, region, button):
    """At the end of a button's settings: Opens Menu, and under it what its
    menu has of its own - Add to Its Menu, Stays Open, its one color, and
    where this button shows while the menu is open. The menu's buttons are
    rows of the panel's tree, under this one's. They used to be a list of
    their own here, with their settings under it. Place on Surface for them
    is at the top of the tab, with one of them selected."""
    index = index_of(region, button)
    if index is None:
        return
    up = parents(region)
    kids = [j for j, p in enumerate(up) if p == index]
    if not can_open(region, index, up) and not kids:
        return                                  # in a sub menu: no menu of its own (MAX_DEPTH)
    if not button.opens_menu and not kids:
        # nothing to fold away yet
        kn_ui.folded_row(layout).prop(button, "opens_menu", text="Opens Menu")
        return
    # a section that folds away (Greg: "Menu's should be collapsible too")
    header, box = layout.panel_prop(button, "menu_open")
    header.prop(button, "opens_menu", text="Opens Menu")
    if box is None:
        return
    if not button.opens_menu:
        box.label(text="Opens Menu is off: these never show", icon="INFO")
    elif not can_open(region, index, up):
        box.label(text="In a sub menu: it opens no menu", icon="INFO")
    if button.uid <= 0:
        box.label(text="Turn Opens Menu off and on to edit this menu", icon="INFO")
        return
    row = box.row(align=True)
    row.context_pointer_set("kneady_region", region)
    row.context_pointer_set("kneady_button", button)
    row.enabled = can_open(region, index, up)
    row.operator("kneady.add_to_menu", icon="ADD")
    if not kids:
        box.label(text="Empty: its buttons show under it in the tree", icon="INFO")
    # Stays Open: a click opens it pinned, and a click in empty space closes
    # it - for a menu of 3D handles
    box.prop(button, "menu_stays")
    kn_ui.draw_list_color(box, core.button_list(region, menu_key(button)))
    # Place on Surface for its buttons is at the top of the tab, with one of
    # them selected (placement.draw_toggle). It used to be here
    if button.back_placed:
        placement.draw_back(box, region, button)


def list_of(region, index, up=None):
    """The key of the list button `index` is in: the region's own Buttons, in
    its row or placed in 3D, or a menu's."""
    up = parents(region) if up is None else up
    if up[index] is None:
        return "static"
    return menu_key(core.buttons_of(region)[up[index]])


def _lists(region, key):
    """The panel's lists (core.add_lists):

    - the region's own Buttons, eight at most in its row and the rest placed
      in 3D. These were two lists until Greg: "The split between menu's adds
      confusion".
    - each menu's buttons, likewise eight at most in its ring and the rest
      placed in 3D past that. A menu once held eight in all, too few for a
      finger's menu of thirteen 3D handles.

    Each list has one color (Greg: "Button groups should always have the
    same color for buttons"). A menu's is set on its button."""
    if key != "static" and not key.startswith("menu_"):
        return None
    used = core.buttons_of(region)
    up = parents(region)
    if key == "static":
        return dict(members=[i for i, p in enumerate(up) if p is None], cap=None, add=_add_own,
                    remove=inside)
    try:
        uid = int(key[5:])
    except ValueError:
        return dict(members=[], cap=0)
    j = uid_index(used, uid)
    if j is None:
        return dict(members=[], cap=0)
    def add(context, reg, i):
        reg.buttons[i].menu_parent = uid
        if ring_full(reg, j, i):
            _add_placed(context, reg, i)

    return dict(members=[i for i, p in enumerate(up) if p == j], cap=None,
                active=(used[j], "menu_index"), color=(used[j], "menu_use_color", "menu_color"),
                add=add, remove=inside)


def ring_count(region, opener, but=None):
    """How many of the buttons in button `opener`'s menu are in its ring, not
    placed in 3D - `but` left out."""
    used = core.buttons_of(region)
    return sum(1 for i, p in enumerate(parents(region)) if p == opener and not used[i].placed and i != but)


def ring_full(region, opener, but=None):
    """Whether button `opener`'s menu holds as many in its ring as it can
    (ROW_BUTTONS), `but` left out."""
    return opener is not None and ring_count(region, opener, but) >= kn_props.ROW_BUTTONS


RING_FULL = "The menu's ring holds %d buttons" % kn_props.ROW_BUTTONS


def row_count(region, but=None):
    """How many of the region's own buttons are in its row, not placed in 3D
    - `but` left out."""
    used = core.buttons_of(region)
    return sum(1 for i, p in enumerate(parents(region)) if p is None and not used[i].placed and i != but)


def row_full(region, but=None):
    """Whether the region's row holds as many as it can (ROW_BUTTONS), `but`
    left out."""
    return row_count(region, but) >= kn_props.ROW_BUTTONS


ROW_FULL = "The row holds %d buttons" % kn_props.ROW_BUTTONS


def _add_own(context, region, index):
    """A button added to the region's own: in its row while it has room, else
    placed in 3D, on the item's front."""
    if row_full(region, index):
        _add_placed(context, region, index)


def _add_placed(context, region, index):
    """Place button `index` in 3D, on the item's front, where Placed in 3D
    puts one."""
    obj = placement._region_object(region, context)
    if obj is not None and obj.type == "MESH":
        placement.default_positions(obj, region, placement._view_toward(context),
                                    context.evaluated_depsgraph_get(), [index])
    region.buttons[index].placed = True


def _reindex(region, moved):
    """Buttons changed places (core.add_reindex): each menu's selection
    follows its button."""
    for b in region.buttons:
        if b.menu_index in moved:
            new = moved[b.menu_index]
            b.menu_index = -1 if new is None else new


def destinations(region, index):
    """Where button `index` can be moved, as [(key, label, here)]: the
    region's own Buttons, and every menu except its own, those inside it,
    and those that would take its own menus deeper than one sub menu
    (MAX_DEPTH). `here` marks the list it is in now."""
    used = core.buttons_of(region)
    up = parents(region)
    inside = {index}
    grew = True
    while grew:
        more = {j for j, p in enumerate(up) if p in inside} - inside
        inside |= more
        grew = bool(more)
    height = _height(up, index)
    here = list_of(region, index, up)
    out = [("static", "Buttons")]
    out += [(menu_key(b), "In %s" % b.name) for j, b in enumerate(used)
            if b.opens_menu and b.uid > 0 and j not in inside and can_open(region, j, up)
            and (depth_of(region, j, up) + 1 + height <= MAX_DEPTH or menu_key(b) == here)]
    return [(key, label, key == here) for key, label in out]


def move_to(context, region, index, dest):
    """Move button `index` to the list `dest`, with its own menu if it has
    one, and select it there. Into the region's own Buttons it stays placed
    as it was, or is placed in 3D if the row is full. Into a menu it goes in
    the ring, or is placed in 3D if the ring is full. Returns why not, or
    ""."""
    if dest == list_of(region, index):
        return ""
    if dest not in {key for key, _label, _here in destinations(region, index)}:
        return "It cannot go there: into its own menu, or with menus of its own into a sub menu"
    found = core.button_list(region, dest)
    if found["cap"] is not None and len(found["members"]) >= found["cap"]:
        return "That menu is full"
    button = core.buttons_of(region)[index]
    if dest == "static":
        button.menu_parent = 0
        if not button.placed and row_full(region, index):
            if not button.place_set:
                _add_placed(context, region, index)
            region.buttons[index].placed = True
    else:
        # into a menu's ring - placed in 3D, past its eight
        button.menu_parent = int(dest[5:])
        if ring_full(region, uid_index(core.buttons_of(region), button.menu_parent), index):
            if not button.place_set:
                _add_placed(context, region, index)
            region.buttons[index].placed = True
        else:
            button.placed = False
    data, prop = core.button_list(region, dest)["active"]
    setattr(data, prop, index)
    core.STATE["button"] = None
    kn_tree.follow(context, region, index)
    return ""


def _list_key(region, parent):
    """Where a button added goes (core.list_key_for): under the region, its
    own Buttons; under a button, that button's menu - none past a sub menu."""
    if parent is None:
        return "static"
    used = core.buttons_of(region)
    if not 0 <= parent < len(used) or used[parent].uid <= 0 or not can_open(region, parent):
        return ""
    return menu_key(used[parent])


def _child_why_not(region, index):
    """Why no button can go under button `index` (core.add_children): one in
    a sub menu opens no menu."""
    return "" if can_open(region, index) else "In a sub menu: it opens no menu"


def _add_child(context, region, index):
    """Add a new button to button `index`'s menu, turning Opens Menu on and
    unfolding the row over it. Returns (index, why)."""
    button = core.buttons_of(region)[index]
    ensure_uid(region, button)
    if not button.opens_menu:
        button.opens_menu = True
    new, why = core.add_button(context, region, menu_key(button))
    if new is not None:
        region.buttons[index].tree_open = True
    return new, why


def add_to_menu(context, region, index):
    """Add a new button to button `index`'s menu (turning Opens Menu on) and
    select it in the tree. Returns why not, or ""."""
    new, why = core.add_child(context, region, index)
    if new is None:
        return why
    kn_tree.follow(context, region, new)
    return ""


class KNEADY_OT_add_to_menu(bpy.types.Operator):
    """Add a button to this one's menu - it opens a menu from now on - and
    select it"""
    bl_idname = "kneady.add_to_menu"
    bl_label = "Add to Its Menu"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        button = getattr(context, "kneady_button", None)
        region, index = core.button_home(button) if button is not None else (None, None)
        if region is None or index >= region.button_count:
            return {"CANCELLED"}
        why = add_to_menu(context, region, index)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        return {"FINISHED"}


# -- Copying a menu ---------------------------------------------------------------------------
#
# Greg: "it would be very advantageous ... to copy a buttons nested menu's to
# another button or menu". A button's menu (the buttons in it, and those in
# their sub menus) goes on the clipboard as plain data. It is pasted into
# another button's menu, or among a region's own buttons, and is added to
# what is there, never put over it. Copy All Buttons carries a whole
# region's buttons.

MENU_CLIPBOARD = "menu"


def menu_data(region, index):
    """The buttons in button `index`'s menu and their sub menus, as plain
    data, with the menu's one color. Each button is {"data", "parent"}: its
    parent is an earlier entry's place in the list, or -1 for one straight
    in the menu."""
    used = core.buttons_of(region)
    up = parents(region)
    out = []

    def walk(i, parent):
        for j in [k for k, p in enumerate(up) if p == i]:
            out.append({"data": core.to_data(used[j]), "parent": parent})
            walk(j, len(out) - 1)

    walk(index, -1)
    opener = used[index]
    return {"buttons": out, "use_color": opener.menu_use_color, "color": list(opener.menu_color)}


def _levels(items):
    """How deep each copied button sits below the menu it was copied from: 0
    straight in it."""
    out = []
    for item in items:
        p = item.get("parent", -1)
        out.append(0 if not 0 <= p < len(out) else out[p] + 1)
    return out


def paste_menu(context, region, found, into=None):
    """Add copied menu buttons (menu_data), with their sub menus, to button
    `into`'s menu, or with `into` None, among the region's own buttons. Each
    gets a new id. Returns (indices added, why not)."""
    if found.get("data_version", 0) > core.DATA_VERSION:
        return [], "Copied from a newer Kneady: update Kneady to paste it"
    data = found.get("data") or {}
    items = [item for item in data.get("buttons", ()) if isinstance(item, dict) and isinstance(item.get("data"), dict)]
    if not items:
        return [], "The menu copied is empty"
    used = core.buttons_of(region)
    up = parents(region)
    if into is not None and not can_open(region, into, up):
        return [], "In a sub menu: it opens no menu"
    base = 0 if into is None else depth_of(region, into, up) + 1
    if base + max(_levels(items)) > MAX_DEPTH:
        return [], "Its sub menus would go deeper than one sub menu"
    if len(used) + len(items) > kn_props.MAX_BUTTONS:
        return [], "A region holds %d buttons at most" % kn_props.MAX_BUTTONS
    # a button without a menu yet gets its id first: its menu's list is found by it
    opener_uid = ensure_uid(region, used[into]) if into is not None else 0
    key = "static" if into is None else menu_key(used[into])
    found_list = core.button_list(region, key)
    direct = sum(1 for item in items if item.get("parent", -1) < 0)
    if found_list["cap"] is not None and len(found_list["members"]) + direct > found_list["cap"]:
        return [], "That menu holds %d buttons at most" % found_list["cap"]
    added, uids = [], []
    for item in items:
        p = item.get("parent", -1)
        k = core.new_button(region)
        b = region.buttons[k]
        core.from_data(b, item["data"], skip=core.BUTTON_OWN)
        b.uid = 0
        b.menu_parent = uids[p] if 0 <= p < len(uids) else opener_uid
        uids.append(ensure_uid(region, b))
        added.append(k)
        if p < 0 and into is None and found_list["add"] is not None and not b.placed:
            found_list["add"](context, region, k)
    if into is not None:
        opener = region.buttons[into]
        opener.opens_menu = True
        if data.get("use_color") and not opener.menu_use_color:
            opener.menu_use_color = True
            opener.menu_color = data.get("color", opener.menu_color)
        opener.tree_open = True
    core.STATE["button"] = None
    core.redraw()
    return added, ""


class KNEADY_OT_copy_menu(bpy.types.Operator):
    """Copy this button's menu - the buttons in it and their sub menus - to
    paste into another button's menu, or among a region's own buttons"""
    bl_idname = "kneady.copy_menu"
    bl_label = "Copy Menu"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        button = getattr(context, "kneady_button", None)
        region, index = core.button_home(button) if button is not None else (None, None)
        if region is None or index >= region.button_count:
            return {"CANCELLED"}
        data = menu_data(region, index)
        if not data["buttons"]:
            self.report({"WARNING"}, "%s's menu is empty" % button.name)
            return {"CANCELLED"}
        core.copy_data(context, MENU_CLIPBOARD, data)
        self.report({"INFO"}, "Copied %s's menu: %d button%s" % (
            button.name, len(data["buttons"]), "" if len(data["buttons"]) == 1 else "s"))
        return {"FINISHED"}


class KNEADY_OT_paste_menu(bpy.types.Operator):
    """Paste a copied menu into this button's menu - it opens a menu from now
    on - added to what is there"""
    bl_idname = "kneady.paste_menu"
    bl_label = "Paste Menu"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def description(cls, context, properties):
        if getattr(context, "kneady_button", None) is None:
            return "Paste a copied menu's buttons among this region's own, added to what is there"
        return cls.__doc__

    def execute(self, context):
        found = core.copied(context, MENU_CLIPBOARD)
        if found is None:
            self.report({"WARNING"}, "Nothing copied: Copy Menu on a button first")
            return {"CANCELLED"}
        button = getattr(context, "kneady_button", None)
        if button is not None:
            region, into = core.button_home(button)
        else:
            region, into = getattr(context, "kneady_region", None), None
        if region is None:
            return {"CANCELLED"}
        added, why = paste_menu(context, region, found, into)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        core.forget()
        kn_tree.follow(context, region, added[0] if into is None else into)
        return {"FINISHED"}


class KNEADY_OT_button_move_to(bpy.types.Operator):
    """Move the selected button to another list - the region's own Buttons,
    or a menu - with its own menu if it has one"""
    bl_idname = "kneady.button_move_to"
    bl_label = "Move To"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    dest: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        button = getattr(context, "kneady_button", None)
        region, index = core.button_home(button) if button is not None else (None, None)
        if region is None or index >= region.button_count:
            return {"CANCELLED"}
        was = region.buttons[index].placed
        why = move_to(context, region, index, self.dest)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        if self.dest == "static" and region.buttons[index].placed and not was:
            self.report({"INFO"}, "%s: placed on the surface" % ROW_FULL)
        return {"FINISHED"}


class KNEADY_MT_move_to(bpy.types.Menu):
    """Where the selected button can go"""
    bl_label = "Move To"

    def draw(self, context):
        layout = self.layout
        button = getattr(context, "kneady_button", None)
        region, index = core.button_home(button) if button is not None else (None, None)
        if region is None:
            layout.label(text="Select a button")
            return
        layout.context_pointer_set("kneady_button", button)
        icons = {"static": "ALIGN_JUSTIFY"}
        for key, label, here in destinations(region, index):
            row = layout.row()
            row.enabled = not here
            row.operator("kneady.button_move_to", text=label,
                         icon="CHECKMARK" if here else icons.get(key, "COLLAPSEMENU")).dest = key


def draw_edit_items(layout, context, region, button):
    """In the menu beside the tree and the one a right-click opens
    (kn_ui.EDIT_ITEMS): Copy Menu, Paste Menu and Move To. That menu's Add
    Button puts a button under the one selected, in its menu, through
    core.add_children. (Add to Its Menu used to be here too.)"""
    layout.separator()
    index = index_of(region, button) if region is not None and button is not None else None
    if index is not None:
        sub = layout.column()
        sub.enabled = any(p == index for p in parents(region))
        sub.operator("kneady.copy_menu", icon="COPYDOWN")
    sub = layout.column()
    sub.enabled = region is not None and core.copied(context, MENU_CLIPBOARD) is not None \
        and (index is None or can_open(region, index))
    sub.operator("kneady.paste_menu", icon="PASTEDOWN",
                 text="Paste Menu" if button is not None else "Paste Menu Into Region")
    if button is not None:
        layout.separator()
        layout.menu("KNEADY_MT_move_to", icon="FORWARD")


def _list_of(region, index):
    return list_of(region, index)


_classes = (KNEADY_OT_button_move_to, KNEADY_MT_move_to, KNEADY_OT_add_to_menu,
            KNEADY_OT_copy_menu, KNEADY_OT_paste_menu)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    core.add_lists(_lists)
    core.add_reindex(_reindex)
    core.add_list_of(_list_of)
    core.add_list_key(_list_key)
    core.add_children(_child_why_not, _add_child)
    kn_ui.BUTTON_EXTRAS.append(draw_button)
    kn_ui.BUTTON_FOOTERS.append(draw_menu)
    kn_ui.EDIT_ITEMS.append(draw_edit_items)


def unregister():
    for hooks, fn in ((kn_ui.EDIT_ITEMS, draw_edit_items), (kn_ui.BUTTON_FOOTERS, draw_menu),
                      (kn_ui.BUTTON_EXTRAS, draw_button)):
        if fn in hooks:
            hooks.remove(fn)
    core.remove_children(_child_why_not, _add_child)
    core.remove_list_key(_list_key)
    core.remove_list_of(_list_of)
    core.remove_reindex(_reindex)
    core.remove_lists(_lists)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
