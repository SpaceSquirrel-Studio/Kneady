"""Viewport Edit (once called Pick Buttons). Greg asked for "a mode in the n
panel where the current pinned menu is exposed and a clicked on button in the
viewport is selected in the n panel. This should make modifying menu's easier
by letting the user select a visual reference of what they are modifying".
Then: "let's rename pick buttons to Viewport Edit. I think we could add some
things in that mode beyond just picking buttons. An icon appears in the
viewport for add and remove."

While it is on (a toggle at the top of Kneady's tab):

- A click on a button does what it always does (opens its menu, switches a
  toggle) and also selects the button's row in the panel's tree (tree.py),
  unfolding the rows above it. Ctrl+click selects the button and does
  nothing else, so a menu's button can be edited without opening its menu.
  A click on a region's faces selects the region's row.
- The last region hovered stays hovered, with its menu open, while the
  mouse crosses empty space to the panel, until another region is hovered
  (core.hit_at).
- The button selected in the tree is marked in the viewport (draw.py), so
  the one being edited stays in sight, whether it was selected there or in
  the panel.
- Icons sit at the corners of the square around the hovered region's
  buttons. Greg wanted them there: "if the region around the menu was shaped
  like a square, currently the plus minus are on the side in the middle. I'd
  rather it was in the corner". At the top right, + adds a button to those
  showing (the region's own, or the open menu's), and - removes the one
  selected, along with the buttons in its menu. At the top left, Rearrange
  (arrange.py) lets the buttons showing be dragged to new places. The whole
  square, out to the icons, holds the region hovered.
- A right-click on a button or a region opens what can be done to it: copy
  and paste a button, its commands, or every button of the region
  (ui.draw_edit_items).
"""

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

from . import reg
from . import core, tree

EDIT_SIZE = 0.62                   # an edit icon's radius, as a share of a button's
EDIT_GAP = 4.0                     # pixels between + and -
CORNER_OUT = 0.6                   # how far out from the square's corners the icons sit, in button spacings
SQUARE = "SQUARE"                  # edit_hit: in the square, on no icon


def pick(context, obj, region, index=None):
    """Select the row of `region`'s button `index` in the panel's tree (or
    the region's own row, with no `index`), unfolding the rows above it. In
    Object mode, `obj` also becomes the active object."""
    if context.mode == "OBJECT" and context.view_layer.objects.active != obj:
        try:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        except (RuntimeError, ReferenceError):
            pass
    tree._TREE["picked"] = obj.name
    core.focus(context, obj, region)
    if index is not None and core.button_of(region, index) is None:
        index = None
    tree.follow(context, region, index, obj)


def marked(region):
    """The button selected in the panel's tree, if it is one of `region`'s,
    else None. For a region several objects share, this holds on whichever
    object shows it."""
    _obj, selected, index = tree.selection(bpy.context)
    if selected is None or index is None or selected.as_pointer() != region.as_pointer():
        return None
    return index


def redraw_panels():
    tree.redraw_panels()


def _toggled(wm, _context):
    _FROZEN.update(key=None, corners=None)
    redraw_panels()
    core.redraw()


def _redrawn(wm, _context):
    redraw_panels()
    core.redraw()


# -- + and - beside the buttons ----------------------------------------------------------------

def shown_parent(obj, region):
    """The button whose open menu shows, or None for the region's own."""
    from . import menus
    found = menus.opened(obj, region)
    return found[0] if found is not None else None


def square(context, obj, region):
    """(x0, y0, x1, y1) in region pixels: the box around the buttons
    showing, their outlines included. Those are the row, or the open menu's
    ring, else the buttons placed on the item. The box also takes in every
    3D handle showing, its whole shape. Greg found the icons sitting inside
    the handles: "the in viewport icons for add and remove and reorder are
    sitting inside the handles that the button launches so those viewport
    buttons should sit outside of the space that includes the handles".
    With no buttons, the box is around the region's middle. None if it is
    not on screen."""
    from . import arrange
    placed, static, _faded, extra = core._layout(context, obj, region)
    used = core.buttons_of(region)
    handles = extra.get("handles", {})
    # the row, or an open menu's ring - else those placed on the item
    circles = arrange.in_line(context, obj, region) or static or \
        [(i, c) for i, c in placed if i not in handles]
    boxes = [h["bounds"] for h in handles.values() if h.get("bounds")]
    for i, c in circles:
        hw, hh = core.half_size(used[i], context)
        boxes.append((c.x - hw, c.y - hh, c.x + hw, c.y + hh))
    if boxes:
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))
    center = core.region_center(context, obj, region.id)
    if center is None:
        return None
    r = core.button_radius(context)
    return center.x - r, center.y - r, center.x + r, center.y + r


def arranging(context=None):
    """Whether Rearrange is on, in Viewport Edit (arrange.py)."""
    wm = getattr(context or bpy.context, "window_manager", None)
    return core.picking(context) and bool(getattr(wm, "kneady_arrange", False))


# Icons a program adds at a corner of the square (add_corner_icon). Each is a
# dict of:
#   "key"
#   "corner"        - "TOP_LEFT" (beside Rearrange, and further out),
#                     "BOTTOM_LEFT" or "BOTTOM_RIGHT"
#   "operator"      - its idname. It gets `target` and `region`: the object's
#                     name and the region's id
#   "glyph"         - draw.py's name for its graphic, such as "PIN"
#   "shown", "lit"  - fn(context, obj, region) -> bool
# They still show while a region is pinned, since a program pins one to place
# its buttons. So does Rearrange, which that program switches to. + and - do
# not, as nothing can be added or removed then.
CORNER_ICONS = []
OWN_ICONS = (("ADD", "kneady.edit_add"), ("REMOVE", "kneady.edit_remove"), ("ARRANGE", "kneady.edit_arrange"))


def add_corner_icon(icon):
    remove_corner_icon(icon["key"])
    CORNER_ICONS.append(icon)


def remove_corner_icon(key):
    CORNER_ICONS[:] = [icon for icon in CORNER_ICONS if icon["key"] != key]


def icon_parts():
    """{key: (gizmo part, operator)} for every icon. Their parts come after
    the region's and its buttons' parts (ops.py)."""
    from . import props
    keys = list(OWN_ICONS) + [(icon["key"], icon["operator"]) for icon in CORNER_ICONS]
    return {key: (props.MAX_BUTTONS + 1 + k, op) for k, (key, op) in enumerate(keys)}


def icon_look(context, obj, region, key):
    """(glyph, lit) an icon is drawn with."""
    for icon in CORNER_ICONS:
        if icon["key"] == key:
            return icon["glyph"], bool(icon["lit"](context, obj, region))
    return key, key == "ARRANGE" and arranging(context)


# Where the icons are, relative to an anchor: the open menu's button, else
# the region's middle. This is kept while the same buttons show, so the icons
# stay put as buttons are added, removed or moved. They move out only when
# the buttons would reach one. Greg: "The viewport edit buttons shouldn't
# change their position as the menu is edited. + and - are moving when I add
# or remove buttons"
_FROZEN = {"key": None, "corners": None}


def _anchor(context, obj, region, parent):
    if parent is not None:
        placed, static, _faded, _extra = core._layout(context, obj, region)
        found = dict(placed + static).get(parent)
        if found is not None:
            return Vector(found)
    try:
        center = core.region_center(context, obj, region.id)
    except (AttributeError, TypeError, ValueError):
        center = None                               # no view
    return Vector(center) if center is not None else None


def _step(context):
    """From one icon's middle to the next's, side by side."""
    return 2.0 * EDIT_SIZE * core.button_radius(context) + EDIT_GAP * core.ui_scale(context)


def _reached(corners, box, context):
    """Whether buttons in `box` would reach an icon at `corners` (left,
    bottom, right, top)."""
    left, bottom, right, top = corners
    r = EDIT_SIZE * core.button_radius(context)
    reach = r + 2.0 * core.ui_scale(context)
    step = _step(context)
    points = ((right, top), (right + step, top), (left, top), (left - step, top), (left, bottom), (right, bottom))
    x0, y0, x1, y1 = box
    return any(x0 - reach <= x <= x1 + reach and y0 - reach <= y <= y1 + reach for x, y in points)


def corners(context, obj, region):
    """(left, bottom, right, top) in region pixels: where the icons go, out
    from the corners of the square around the buttons showing. They stay as
    they were while the same buttons show (_FROZEN). None off screen."""
    box = square(context, obj, region)
    if box is None:
        return None
    parent = shown_parent(obj, region)
    anchor = _anchor(context, obj, region, parent)
    if anchor is None:
        anchor = Vector((0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])))
    out_by = CORNER_OUT * core.button_spacing(context)
    rel = (box[0] - anchor.x, box[1] - anchor.y, box[2] - anchor.x, box[3] - anchor.y)
    key = (obj.name, region.id, parent)
    kept = _FROZEN["corners"] if _FROZEN["key"] == key else None
    if kept is None or _reached(kept, rel, context):
        kept = (rel[0] - out_by, rel[1] - out_by, rel[2] + out_by, rel[3] + out_by)
    _FROZEN.update(key=key, corners=kept)
    return anchor.x + kept[0], anchor.y + kept[1], anchor.x + kept[2], anchor.y + kept[3]


def edit_icons(context, obj, region):
    """Viewport Edit's icons for the hovered region, as {what: center} in
    region pixels, out from the corners of the square around its buttons:

    - "ADD" at the top right, where a button can be added to those showing.
    - "REMOVE" beside it, while the button selected in the tree is one of
      them.
    - "ARRANGE" at the top left, where two or more can be rearranged.
    - A program's icons (CORNER_ICONS), beside Rearrange or at a bottom
      corner. Kneady Pro's Place on Surface is one. Greg: "Let's put "Place
      on surface" and "Rearrange" next to each other in the upper left
      corner of the square. Only one can be on at a time".

    Each keeps its own place whether the others show or not. While a region
    is pinned (a program placing its buttons), there is no + or -."""
    from . import arrange
    found = corners(context, obj, region)
    if found is None:
        return {}
    left, bottom, right, top = found
    step = _step(context)
    out = {}
    if not core.STATE.get("pinned"):
        if core.list_key_for(region, shown_parent(obj, region)):
            out["ADD"] = Vector((right, top))
        selected = marked(region)
        placed, static, _faded, _extra = core._layout(context, obj, region)
        if selected is not None and selected in {i for i, _c in placed + static}:
            out["REMOVE"] = Vector((right + step, top))
    if arrange.can_arrange(context, obj, region):
        out["ARRANGE"] = Vector((left, top))
    beside = 0
    for icon in CORNER_ICONS:
        corner = icon["corner"]
        if corner == "TOP_LEFT":
            beside += 1
        if icon["shown"](context, obj, region):
            out[icon["key"]] = Vector((left - beside * step, top) if corner == "TOP_LEFT" else
                                      (left if corner == "BOTTOM_LEFT" else right, bottom))
    return out


def edit_hit(context, hover, at):
    """Which of the hovered region's icons `at` (region pixels) is on:
    "ADD", "REMOVE", "ARRANGE" or a program's. SQUARE if it is in the square
    around the buttons, out to the icons, else None."""
    obj = bpy.data.objects.get(hover[0])
    region = core.find_region(obj, hover[1]) if obj is not None else None
    if region is None or core.STATE.get("dragging"):
        return None
    r = EDIT_SIZE * core.button_radius(context)
    reach = r + 2.0 * core.ui_scale(context)
    icons = edit_icons(context, obj, region)
    for what, center in icons.items():
        if (at - center).length <= reach:
            return what
    box = square(context, obj, region)
    if box is None:
        return None
    out_by = CORNER_OUT * core.button_spacing(context)
    x0, y0, x1, y1 = box
    xs = [x0 - out_by, x1 + out_by] + [c.x for c in icons.values()]
    ys = [y0 - out_by, y1 + out_by] + [c.y for c in icons.values()]
    if min(xs) - reach <= at.x <= max(xs) + reach and min(ys) - reach <= at.y <= max(ys) + reach:
        return SQUARE
    return None


def _target(op):
    obj = bpy.data.objects.get(op.target)
    region = core.find_region(obj, op.region) if obj is not None else None
    return obj, region


class KNEADY_OT_edit_add(bpy.types.Operator):
    """Add a button to those showing - the region's own, or the open menu's -
    and select it in the panel"""
    bl_idname = "kneady.edit_add"
    bl_label = "Add Button"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    target: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    region: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, _event):
        return self.execute(context)

    def execute(self, context):
        obj, region = _target(self)
        if region is None:
            return {"CANCELLED"}
        key = core.list_key_for(region, shown_parent(obj, region))
        if not key:
            self.report({"WARNING"}, "A button cannot be added here")
            return {"CANCELLED"}
        index, why = core.add_button(context, region, key)
        if index is None:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        pick(context, obj, region, index)
        core.forget(obj.name)
        return {"FINISHED"}


class KNEADY_OT_edit_remove(bpy.types.Operator):
    """Remove the button selected in the panel"""
    bl_idname = "kneady.edit_remove"
    bl_label = "Remove Button"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    target: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    region: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        _obj, region = _target(self)
        index = marked(region) if region is not None else None
        if index is not None:
            confirm = confirm_removal(context, self, event, region, index)
            if confirm is not None:
                return confirm
        return self.execute(context)

    def execute(self, context):
        obj, region = _target(self)
        index = marked(region) if region is not None else None
        if index is None:
            return {"CANCELLED"}
        key = core.list_of(region, index)
        why = core.remove_button(region, key, index)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        pick(context, obj, region, core.selected_button(region, key))
        core.forget(obj.name)
        return {"FINISHED"}


def confirm_removal(context, op, event, region, index):
    """Ask before removing a button whose menu goes with it. Returns the
    confirm's result, or None for a button without a menu."""
    more = len(core.removed_with(region, core.list_of(region, index), index)) - 1
    if more <= 0:
        return None
    name = core.buttons_of(region)[index].name
    message = "Remove %s and the %d button%s in its menu?" % (name, more, "" if more == 1 else "s")
    try:
        return context.window_manager.invoke_confirm(op, event, title="Remove Button", message=message,
                                                     confirm_text="Remove")
    except TypeError:
        return context.window_manager.invoke_confirm(op, event)


class KNEADY_OT_edit_arrange(bpy.types.Operator):
    """Rearrange: drag the buttons showing to new places in their row, column
    or ring - the others make room. A click still does what it does"""
    bl_idname = "kneady.edit_arrange"
    bl_label = "Rearrange"
    bl_options = {"INTERNAL"}

    target: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    region: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, _event):
        return self.execute(context)

    def execute(self, context):
        wm = context.window_manager
        wm.kneady_arrange = not wm.kneady_arrange
        return {"FINISHED"}


# What a program adds to the panel under Rearrange, as fn(layout, context):
# Kneady Pro's Place on Surface. Greg: "move "Place on Surface" right below
# "Rearrange" in the n-panel"
PANEL_TOGGLES = []


# -- A right-click ----------------------------------------------------------------------------

def _draw_edit_menu(menu, context):
    from . import ui
    _obj, region, index = tree.selection(context)
    button = core.button_of(region, index) if region is not None and index is not None else None
    ui.draw_edit_items(menu.layout, context, region, button, viewport=True)


class KNEADY_OT_edit_menu(bpy.types.Operator):
    """Viewport Edit: what can be done to the button or region under the
    mouse - copy and paste"""
    bl_idname = "kneady.edit_menu"
    bl_label = "Kneady Edit"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return core.picking(context) and core.working(context)

    def invoke(self, context, event):
        if context.region is None or context.region.type != "WINDOW" or context.region_data is None:
            return {"PASS_THROUGH"}
        at = (event.mouse_region_x, event.mouse_region_y)
        result = core.hit_at(context, at)
        hover = core.STATE["hover"]
        if hover is None or hover[1] is None:
            return {"PASS_THROUGH"}
        index = core.STATE["button"]
        on_faces = result is not None and (result[0], result[1]) == tuple(hover)
        if index is None and not on_faces:
            # off the region and its buttons: Blender's own right-click
            return {"PASS_THROUGH"}
        obj = bpy.data.objects.get(hover[0])
        region = core.find_region(obj, hover[1]) if obj is not None else None
        if region is None:
            return {"PASS_THROUGH"}
        pick(context, obj, region, index)
        title = core.buttons_of(region)[index].name if index is not None else region.name
        context.window_manager.popup_menu(_draw_edit_menu, title=title, icon="RESTRICT_SELECT_OFF")
        return {"FINISHED"}


_classes = (KNEADY_OT_edit_add, KNEADY_OT_edit_remove, KNEADY_OT_edit_arrange, KNEADY_OT_edit_menu)
_KEYMAPS = []
# where a right-click goes: the modes' own keymaps come before the 3D View's
_RIGHT_CLICK = (("Object Mode", "EMPTY"), ("Pose", "EMPTY"), ("3D View", "VIEW_3D"))


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kneady_pick = bpy.props.BoolProperty(
        name="Viewport Edit", default=False, update=_toggled,
        description="Edit the buttons in the viewport: a click on one selects it in this panel too (Ctrl+click "
                    "only selects it), + and - beside them add and remove one, and a right-click copies and "
                    "pastes. The last region hovered stays, its menu open, while you work here")
    bpy.types.WindowManager.kneady_arrange = bpy.props.BoolProperty(
        name="Rearrange", default=False, update=_redrawn,
        description="In Viewport Edit, drag the buttons showing to new places in their row, column or ring - "
                    "the others make room. A click still does what it does")
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is not None:
        for name, space in _RIGHT_CLICK:
            km = kc.keymaps.new(name=name, space_type=space)
            _KEYMAPS.append((km, km.keymap_items.new(KNEADY_OT_edit_menu.bl_idname, "RIGHTMOUSE", "PRESS")))


def unregister():
    for km, kmi in _KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _KEYMAPS.clear()
    for name in ("kneady_arrange", "kneady_pick"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
