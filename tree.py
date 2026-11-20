"""The panel's tree. Greg: "It seems to me that the Entry's could be
organized in one menu that is more like the outliner where entries are
hierarchical". And, on one list per region: "it's more one menu per item. A
menu containing the regions as the highest levels then you start nesting
buttons under it then nesting buttons under other buttons."

The tree is one list for the object the panel edits:

- its regions as the top rows
- each region's own buttons under it
- the buttons in a button's menu under that button, and a sub menu's one
  level deeper

A row with rows under it folds, and every one starts folded. Selecting a
button in the viewport (Viewport Edit, pick.py) unfolds the way to it. Under
the list are the settings of the row selected: a region's or a button's,
never both. So the panel no longer nests a list in every menu's settings.

Blender's list shows one collection, but regions and buttons are two. So the
tree is a list of rows on the window manager (never saved) that only point
at things. Each row points at its region by where it lives (its owner and
data path), and at a button by its index. Rows are made again whenever what
they point at changes (an add, a removal, a move, an undo), so a row that is
out of date for a moment finds nothing rather than the wrong button. The
panel notices a change as it draws. Blender forbids writing data while
drawing, so the rows are made in a timer straight after. Anything that
changes the buttons makes them at once (follow)."""

import bpy  # type: ignore

from . import reg
from . import core, errors

ROWS_MIN, ROWS_MAX = 3, 12         # how tall the list starts, and how tall it grows before it scrolls

# The tree's state:
#   obj     - the name of the object the rows are for
#   sig     - what the rows were made from (_signature)
#   pending - whether a remake is waiting in a timer
#   want    - the object a pending remake is for
#   picked  - the object Viewport Edit last picked on, for the panel when the
#             active object is not a mesh (Pose mode)
_TREE = {"obj": "", "sig": None, "pending": False, "want": "", "picked": ""}
_ID_DATA = {"OBJECT": "objects", "SCENE": "scenes", "MESH": "meshes", "ARMATURE": "armatures"}


class KNEADY_PG_row(bpy.types.PropertyGroup):
    """A row of the tree: a region, or one of its buttons."""
    owner_type: bpy.props.StringProperty()          # the region's owner's ID type: OBJECT, SCENE ...
    owner: bpy.props.StringProperty()                # its name
    library: bpy.props.StringProperty()              # its library's path, "" for one in this file
    path: bpy.props.StringProperty()                 # the region's data path from it
    rid: bpy.props.IntProperty()                     # the region's id, to be sure of it
    index: bpy.props.IntProperty(default=-1)         # the button's index; -1 for the region's own row
    depth: bpy.props.IntProperty()                   # 0 a region, 1 its own button, 2 in a menu, 3 a sub menu
    parent: bpy.props.IntProperty(default=-1)        # the row it hangs under
    kids: bpy.props.BoolProperty()                   # whether rows hang under it


# -- Which object, which regions -------------------------------------------------------------

def tree_object(context):
    """The object the panel's tree is for: the active object if it is a mesh,
    else the one Viewport Edit last picked on (in Pose mode the rig is
    active), else None."""
    obj = context.active_object
    if obj is not None and obj.type == "MESH":
        return obj
    picked = bpy.data.objects.get(_TREE.get("picked") or "")
    return picked if picked is not None and picked.type == "MESH" else None


def tree_regions(obj):
    """The tree's top rows: the object's own regions, or those a program
    gives it to edit in their place (core.add_editor)."""
    if obj is None or obj.type != "MESH":
        return []
    managed = core.editor_for(obj)
    if managed is None:
        return list(obj.kneady.regions)
    if len(managed) > 3 and managed[3] is not None:
        return [r for r in managed[3] if r is not None]
    return [managed[1]] if managed[1] is not None else []


def own_index(obj, region):
    """The region's place in the object's own list, or None for one a program
    gives it."""
    kn = getattr(obj, "kneady", None)
    if kn is None or region is None:
        return None
    pointer = region.as_pointer()
    return next((k for k, r in enumerate(kn.regions) if r.as_pointer() == pointer), None)


def can_add_region(obj):
    """Whether the tree can add a region to the object: a mesh whose regions
    are its own, and not linked."""
    return obj is not None and obj.type == "MESH" and core.editor_for(obj) is None and not core.regions_fixed(obj)


def _kids(region):
    """{parent index or None: [indices under it]}, in order. The region's own
    buttons are under None, and a menu's buttons under its button."""
    from . import menus
    out = {}
    for i, p in enumerate(menus.parents(region)):
        out.setdefault(p, []).append(i)
    return out


def _signature(obj, regions=None):
    """What the rows are made from: the object, each region, its buttons and
    their menus. Names are left out, since rows read them as they draw."""
    if obj is None:
        return ("",)
    out = [obj.name]
    for region in (tree_regions(obj) if regions is None else regions):
        try:
            path = region.path_from_id()
        except (ValueError, TypeError, AttributeError):
            path = ""
        out.append((region.id_data.name, path, region.id,
                    tuple((b.uid, b.menu_parent, b.opens_menu) for b in core.buttons_of(region))))
    return tuple(out)


# -- Rows ----------------------------------------------------------------------------------

def _region_of(row):
    """The region a row points at, or None if it is gone."""
    where = _ID_DATA.get(row.owner_type)
    if where is None:
        return None
    owner = getattr(bpy.data, where).get((row.owner, row.library or None))
    if owner is None:
        return None
    try:
        region = owner.path_resolve(row.path)
    except (ValueError, TypeError, AttributeError):
        return None
    return region if getattr(region, "id", None) == row.rid else None


def resolve(row):
    """(region, button index or None) a row points at, or (None, None)."""
    region = _region_of(row)
    if region is None:
        return None, None
    if row.index < 0:
        return region, None
    return (region, row.index) if row.index < min(region.button_count, len(region.buttons)) else (None, None)


def owner_of(row):
    """What a row folds with: its region, or its button."""
    region, index = resolve(row)
    if region is None:
        return None
    return region if index is None else region.buttons[index]


def _identity(row):
    return (row.owner_type, row.owner, row.library, row.path, row.index)


def _region_identity(region):
    owner = region.id_data
    try:
        path = region.path_from_id()
    except (ValueError, TypeError, AttributeError):
        return None
    return (owner.id_type, owner.name, owner.library.filepath if owner.library else "", path)


def build(context, obj=None):
    """Make the rows again, for `obj` (the panel's object if None), keeping
    the row selected where it can."""
    wm = context.window_manager
    if obj is None:
        obj = tree_object(context)
    rows = wm.kneady_rows
    kept = _identity(rows[wm.kneady_row]) if 0 <= wm.kneady_row < len(rows) else None
    rows.clear()
    regions = tree_regions(obj)
    for region in regions:
        place = _region_identity(region)
        if place is None:
            continue
        kids = _kids(region)

        def add(index, depth, parent):
            row = rows.add()
            row.owner_type, row.owner, row.library, row.path = place
            row.rid, row.index, row.depth, row.parent = region.id, index, depth, parent
            row.kids = bool(kids.get(None if index < 0 else index))
            return len(rows) - 1

        def walk(i, depth, parent):
            me = add(i, depth, parent)
            for j in kids.get(i, ()):
                walk(j, depth + 1, me)

        top = add(-1, 0, -1)
        for i in kids.get(None, ()):
            walk(i, 1, top)
    _TREE.update(obj=obj.name if obj is not None else "", sig=_signature(obj, regions))
    found = -1
    if kept is not None:
        found = next((k for k, row in enumerate(rows) if _identity(row) == kept), -1)
        if found < 0:
            # The button is gone: select its region instead
            found = next((k for k, row in enumerate(rows) if _identity(row)[:4] == kept[:4] and row.index < 0), -1)
    if found < 0 and len(rows):
        found = min(max(wm.kneady_row, 0), len(rows) - 1)
    if wm.kneady_row != found:
        wm.kneady_row = found


def ensure(context, obj):
    """Whether the rows are up to date for `obj`. If not, a timer makes them
    straight after this draw (drawing cannot write data)."""
    if _signature(obj) == _TREE["sig"] and _TREE["obj"] == (obj.name if obj is not None else ""):
        return True
    _TREE["want"] = obj.name if obj is not None else ""
    if not _TREE["pending"]:
        _TREE["pending"] = True
        bpy.app.timers.register(_remake, first_interval=0.0)
    return False


def _remake():
    _TREE["pending"] = False
    try:
        build(bpy.context, bpy.data.objects.get(_TREE.get("want") or ""))
    except Exception:                   # the panel still draws, from the rows it had
        errors.caught("making the panel's tree")
    redraw_panels()
    return None


def refresh(context):
    """Make the rows again now, for what the panel shows. For use after a
    change to the buttons that keeps the selection where it was."""
    build(context)
    redraw_panels()


def selection(context):
    """(object, region, button index or None) for the row selected, or
    (object, None, None) with no row selected."""
    wm = context.window_manager
    obj = bpy.data.objects.get(_TREE.get("obj") or "")
    rows = getattr(wm, "kneady_rows", None)
    if rows is None or not 0 <= wm.kneady_row < len(rows):
        return obj, None, None
    region, index = resolve(rows[wm.kneady_row])
    return obj, region, index


def select(context, region, index=None, unfold=True):
    """Select the row of `region`'s button `index` (or the region's own row),
    unfolding the rows above it. Returns whether the row was there."""
    place = _region_identity(region) if region is not None else None
    if place is None:
        return False
    if unfold and index is not None:
        from . import menus
        region.tree_open = True
        up = menus.parents(region)
        j = up[index] if index < len(up) else None
        while j is not None:
            region.buttons[j].tree_open = True
            j = up[j]
    wm = context.window_manager
    want = place + (-1 if index is None else index,)
    found = next((k for k, row in enumerate(wm.kneady_rows) if _identity(row) == want), -1)
    if found < 0:
        return False
    wm.kneady_row = found
    return True


def follow(context, region=None, index=None, obj=None):
    """After a change to the buttons: make the rows again for `obj` (the
    panel's object if None), then select the row of `region`'s button
    `index`, or the region's own row."""
    build(context, obj)
    if region is not None:
        select(context, region, index)
    redraw_panels()
    core.redraw()


def _chosen(wm, context):
    """A row was selected. A region of the object's own is selected in the
    object's list too (Edit Faces works on it), and a button in its list
    (core.button_list), so whatever reads those agrees."""
    obj, region, index = selection(context)
    if region is None:
        return
    k = own_index(obj, region)
    if k is not None and obj.kneady.index != k:
        obj.kneady.index = k
    if index is not None:
        data, prop = core.button_list(region, core.list_of(region, index))["active"]
        try:
            if getattr(data, prop, None) != index:
                setattr(data, prop, index)
        except (AttributeError, TypeError, ValueError):
            pass
    core.redraw()


def redraw_panels():
    wm = getattr(bpy.context, "window_manager", None)
    for win in (wm.windows if wm is not None else ()):
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                for r in area.regions:
                    if r.type == "UI":
                        r.tag_redraw()


# -- The list ------------------------------------------------------------------------------

class KNEADY_UL_tree(bpy.types.UIList):
    """The tree: each row indented by its depth, a triangle where rows hang
    under it; a region its color and name, a button what kind it is, its name
    (double-click to rename), its marks and its eye."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        region, i = resolve(item)
        row = layout.row(align=True)
        if region is None:
            row.label(text="")
            return
        for _k in range(item.depth):
            row.label(text="", icon="BLANK1")
        owner = region if i is None else region.buttons[i]
        if item.kids:
            row.prop(owner, "tree_open", text="", emboss=False,
                     icon="DISCLOSURE_TRI_DOWN" if owner.tree_open else "DISCLOSURE_TRI_RIGHT")
        else:
            row.label(text="", icon="BLANK1")
        if i is None:
            swatch = row.row()
            swatch.scale_x = 0.3
            swatch.prop(region, "color", text="")
            row.prop(region, "name", text="", emboss=False)
            if region.whole:
                row.label(text="", icon="OBJECT_DATA")
            return
        from . import ui
        button = owner
        # The pointer icon marks the button a drag on the region runs. There
        # is no word beside it, since the rows are narrower for their indent.
        kind = "CHECKBOX_HLT" if button.action == "TOGGLE" else "DOT" if core.is_gap(button) \
            else "RESTRICT_SELECT_OFF" if i == core.first_drag_button(region) and region.button_count > 1 \
            else "BLANK1"
        row.prop(button, "name", text="", emboss=False, icon=kind)
        for fn in ui.BUTTON_ROWS:
            fn(row, context, region, button)
        row.prop(button, "show", text="", emboss=False, icon="HIDE_OFF" if button.show else "HIDE_ON")

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        shown = []
        for k, row in enumerate(rows):
            if row.parent < 0 or row.parent >= k:
                shown.append(True)
                continue
            above = rows[row.parent]
            owner = owner_of(above)
            shown.append(shown[row.parent] and owner is not None and owner.tree_open)
        return [self.bitflag_filter_item if s else 0 for s in shown], []


def visible_count(context):
    """How many rows show, folded ones left out."""
    rows = context.window_manager.kneady_rows
    shown = []
    for k, row in enumerate(rows):
        if row.parent < 0 or row.parent >= k:
            shown.append(True)
        else:
            owner = owner_of(rows[row.parent])
            shown.append(shown[row.parent] and owner is not None and owner.tree_open)
    return sum(shown)


# -- Adding, removing, moving ----------------------------------------------------------------

def _sibling_key(region, index):
    """The list a button added beside button `index` goes in. With `index`
    None, the region's own list."""
    return core.list_key_for(region, None) if index is None else core.list_of(region, index)


def add_beside(context, what="AUTO"):
    """+ in the panel. It adds a button under the row selected: among the
    region's own buttons, or in the selected button's menu. Greg: "When I
    click start cap the "offset / scale" in the menu then press plus it
    doesn't create a new entry nested under "Offset / Scale" and it should".
    Where the selected button can hold none (in a sub menu, or with no
    program that builds menus), the new button goes beside it instead. With
    no row selected, it adds a region. With `what` "REGION" (Add Region, in
    the menu beside the tree), it adds a region, where the object's regions
    are its own. Returns why not, or ""."""
    obj, region, index = selection(context)
    obj = tree_object(context) if obj is None else obj
    if obj is None:
        return "Select a mesh"
    if what == "REGION" or region is None:
        if not can_add_region(obj):
            return core.regions_fixed(obj) or "These regions come with the object: none can be added here"
        made = core.new_region(obj)
        core.forget(obj.name)
        follow(context, made, None, obj)
        return ""
    if index is not None and not core.child_why_not(region, index):
        new, why = core.add_child(context, region, index)
        if new is None:
            return why
        follow(context, region, new, obj)
        return ""
    key = _sibling_key(region, index)
    if not key:
        return "A button cannot be added there"
    new, why = core.add_button(context, region, key)
    if new is None:
        return why
    follow(context, region, new, obj)
    return ""


def remove_selected(context):
    """- in the panel. It removes the button selected, or the region selected
    (one of the object's own) with its buttons and its faces' tag. Returns
    why not, or ""."""
    obj, region, index = selection(context)
    if region is None:
        return "Select a region or a button"
    if index is not None:
        key = core.list_of(region, index)
        why = core.remove_button(region, key, index)
        if why:
            return why
        follow(context, region, core.selected_button(region, key), obj)
        return ""
    k = own_index(obj, region)
    if k is None:
        return "These regions come with the object: they cannot be removed here"
    fixed = core.regions_fixed(obj)
    if fixed:
        return fixed
    from . import ops
    ops._clear_faces(obj, region.id)
    kn = obj.kneady
    kn.regions.remove(k)
    kn.index = max(min(k, len(kn.regions) - 1), 0)
    core.forget(obj.name)
    follow(context, kn.regions[kn.index] if len(kn.regions) else None, None, obj)
    return ""


def move_selected(context, direction):
    """The arrows in the panel. They move the region or button selected up
    (-1) or down (1) among its own: a region among the object's regions, a
    button among the buttons of its list. Returns whether it moved."""
    obj, region, index = selection(context)
    if region is None:
        return False
    if index is not None:
        new = core.move_in_list(region, core.list_of(region, index), direction, index)
        if new is None:
            return False
        follow(context, region, new, obj)
        return True
    k = own_index(obj, region)
    if k is None:
        return False
    kn = obj.kneady
    to = k + direction
    if not 0 <= to < len(kn.regions):
        return False
    kn.regions.move(k, to)
    kn.index = to
    follow(context, kn.regions[to], None, obj)
    return True


def can_move(context, direction):
    """Whether the row selected can move that way."""
    obj, region, index = selection(context)
    if region is None:
        return False
    if index is not None:
        members = core.button_list(region, core.list_of(region, index))["members"]
        at = members.index(index) if index in members else -1
        return at >= 0 and 0 <= at + direction < len(members)
    k = own_index(obj, region)
    return k is not None and 0 <= k + direction < len(obj.kneady.regions)


class KNEADY_OT_tree_add(bpy.types.Operator):
    """Add a button under the row selected: among the region's buttons, or in
    the selected button's menu - beside it, where it can hold none"""
    bl_idname = "kneady.tree_add"
    bl_label = "Add"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    what: bpy.props.EnumProperty(
        items=(("AUTO", "Add", "A button under the row selected"),
               ("REGION", "Add Region", "A region of the object's own")),
        default="AUTO", options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def description(cls, context, properties):
        if properties.what == "REGION":
            return "Add a region to the object: Edit Faces then gives it its faces"
        return cls.__doc__

    def execute(self, context):
        why = add_beside(context, self.what)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        return {"FINISHED"}


class KNEADY_OT_tree_remove(bpy.types.Operator):
    """Remove the row selected: a button, with the buttons in its menu, or a
    region with its buttons"""
    bl_idname = "kneady.tree_remove"
    bl_label = "Remove"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def invoke(self, context, event):
        _obj, region, index = selection(context)
        if region is not None and index is not None:
            # A button takes the buttons in its menu with it, so ask first
            from . import pick
            confirm = pick.confirm_removal(context, self, event, region, index)
            if confirm is not None:
                return confirm
        if region is not None and index is None:
            # A region takes its buttons with it, so ask first
            try:
                return context.window_manager.invoke_confirm(
                    self, event, title="Remove Region", confirm_text="Remove",
                    message="Remove %s, its buttons and its faces' tag?" % region.name)
            except TypeError:
                return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        why = remove_selected(context)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        return {"FINISHED"}


class KNEADY_OT_tree_move(bpy.types.Operator):
    """Move the row selected up or down among its own: a region among the
    object's regions, a button among those of its list - its place in the
    row, column, circle or ring"""
    bl_idname = "kneady.tree_move"
    bl_label = "Move"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    direction: bpy.props.EnumProperty(items=(("UP", "Up", "Earlier"), ("DOWN", "Down", "Later")))

    def execute(self, context):
        if not move_selected(context, -1 if self.direction == "UP" else 1):
            return {"CANCELLED"}
        return {"FINISHED"}


_classes = (KNEADY_PG_row, KNEADY_UL_tree, KNEADY_OT_tree_add, KNEADY_OT_tree_remove, KNEADY_OT_tree_move)


@bpy.app.handlers.persistent
def _on_load(*_args):
    """When a file opens: rows made for another file point at nothing."""
    _TREE.update(obj="", sig=None, picked="")


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kneady_rows = bpy.props.CollectionProperty(type=KNEADY_PG_row)
    bpy.types.WindowManager.kneady_row = bpy.props.IntProperty(name="Selected", default=-1, update=_chosen)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if bpy.app.timers.is_registered(_remake):
        bpy.app.timers.unregister(_remake)
    _TREE.update(obj="", sig=None, pending=False, picked="")
    for name in ("kneady_row", "kneady_rows"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
