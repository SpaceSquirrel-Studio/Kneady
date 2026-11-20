"""Kneady's panel, and its toggle in the viewport header.

The panel shows one tree for the object (tree.py):

- its regions as the top rows
- each region's buttons under it
- the buttons in a button's menu under that button

+ and - and the arrows sit on its right, as Blender's own lists have them
(double-click a row to rename it). Under the tree are the settings of the
row selected: a region's faces, color, opacity and arrangement, or a
button's icon and what its drags drive."""

import bpy  # type: ignore

from . import reg
from . import core, placed, props, tips, tree, tutorials

ICON = "POSE_HLT"
DIRECTIONS = (("across", "Left / Right"), ("up", "Up / Down"))
# What an add-on built on Kneady can draw in this panel. Each list holds
# functions:
#   REGION_EXTRAS  - in a region's settings, above its Arrange.
#                    fn(layout, context, region)
#   REGION_BUTTONS - after Arrange, about the region's buttons.
#                    fn(layout, context, region)
#   BUTTON_ROWS    - in each button's row of the tree, beside its name.
#                    fn(layout, context, region, button)
#   BUTTON_LOOKS   - how a button shows, just under Drag / Toggle and before
#                    its icon. fn(layout, context, region, button)
#   BUTTON_EXTRAS  - in a button's settings, under its icon.
#                    fn(layout, context, region, button)
#   BUTTON_FOOTERS - at the end of a button's settings, after its commands.
#                    fn(layout, context, region, button)
#   EDIT_ITEMS     - in the menu beside the tree, and the one a right-click
#                    opens in Viewport Edit, after Kneady's own items.
#                    fn(layout, context, region, button), button None for a
#                    region
REGION_EXTRAS = []
REGION_BUTTONS = []
BUTTON_ROWS = []
BUTTON_LOOKS = []
BUTTON_EXTRAS = []
BUTTON_FOOTERS = []
EDIT_ITEMS = []


def draw_edit_items(layout, context, region, button=None, viewport=False):
    """What can be done to a region or a button, besides + and -. This fills
    the menu beside the tree and, in the viewport, the menu a right-click
    opens: copy and paste one button, its commands alone, or every button of
    the region with their menus, then what a program adds (EDIT_ITEMS)."""
    col = layout.column()
    if region is not None:
        col.context_pointer_set("kneady_region", region)
    if button is not None:
        col.context_pointer_set("kneady_button", button)
    if not viewport:
        # + adds buttons under the row selected, so a region is added here
        sub = col.column()
        sub.enabled = tree.can_add_region(tree.tree_object(context))
        sub.operator("kneady.tree_add", text="Add Region", icon="ADD").what = "REGION"
        col.separator()
    if button is not None:
        col.operator("kneady.copy", text="Copy Button", icon="COPYDOWN").scope = "BUTTON"
        paste = col.column()
        paste.enabled = core.copied(context, "button") is not None
        paste.operator("kneady.paste", text="Paste Button", icon="PASTEDOWN").scope = "BUTTON"
        col.operator("kneady.copy", text="Copy Commands", icon="COPYDOWN").scope = "COMMANDS"
        paste = col.column()
        paste.enabled = core.copied(context, "commands") is not None
        paste.operator("kneady.paste", text="Paste Commands", icon="PASTEDOWN").scope = "COMMANDS"
        col.separator()
    sub = col.column()
    sub.enabled = region is not None
    sub.operator("kneady.copy", text="Copy All Buttons", icon="COPYDOWN").scope = "REGION"
    paste = sub.column()
    paste.enabled = core.copied(context, "region") is not None
    paste.operator("kneady.paste", text="Paste All Buttons", icon="PASTEDOWN").scope = "REGION"
    for fn in EDIT_ITEMS:
        fn(col, context, region, button)


class KNEADY_MT_buttons(bpy.types.Menu):
    """Copy and paste the selected button, its commands, or every button of
    its region; add a region"""
    # Named for what it is mostly for. Greg: "instead of that dropdown being
    # named buttons name it 'Copy / Paste'"
    bl_label = "Copy / Paste"

    def draw(self, context):
        draw_edit_items(self.layout, context, getattr(context, "kneady_region", None),
                        getattr(context, "kneady_button", None))


def draw_toggle(layout, context):
    """Draw Kneady on or off at the panel's full width, and Help under it
    (how much Kneady says, tips.py), laid out like the settings below it.
    Help used to sit beside the toggle. Greg: "The Kneady button at the top
    of the Kneady panel should span the entire width of the panel with the
    help section beneath it"."""
    layout.prop(context.scene, "kneady_on", text="Kneady", toggle=True, icon=ICON)
    if hasattr(context.window_manager, "kneady_help"):
        row = layout.row()
        row.label(text="Help")
        row.prop(context.window_manager, "kneady_help", text="")


def _wrapped(layout, text, icon="NONE", width=34):
    """A note over several lines, since the sidebar does not wrap labels
    itself."""
    import textwrap
    col = layout.column(align=True)
    for k, line in enumerate(textwrap.wrap(text, width)):
        col.label(text=line, icon=icon if k == 0 else "BLANK1")


def draw_list(layout, context, obj):
    """The object's own regions: the tree, and the selected row's settings."""
    kn = obj.kneady
    fixed = core.regions_fixed(obj)
    if fixed:
        icon = ("ERROR" if core.newer_on(obj) else
                "LIBRARY_DATA_OVERRIDE" if obj.override_library else "LINKED")
        _wrapped(layout, fixed, icon)
    elif not len(kn.regions):
        # where to begin, for someone without a program that sets it up
        col = layout.column(align=True)
        col.label(text="Add a region (+), then Edit Faces:", icon="INFO")
        col.label(text="select its faces and Assign. Its button")
        col.label(text="drives what you choose under it")
    loose = core.unlisted_tags(obj) if context.mode == "OBJECT" and not fixed else {}
    if loose:
        # what Join leaves of another object's regions (core.unlisted_tags)
        box = layout.box()
        _wrapped(box, "%d faces carry regions this object does not list - joined from another object?"
                 % sum(loose.values()), "ERROR")
        box.operator("kneady.region_unlisted", icon="ADD")
    if fixed:
        layout = layout.column()
        layout.enabled = False
    draw_tree(layout, context, obj)


def draw_tree(layout, context, obj):
    """The tree (tree.py), with + and -, the menu of what else can be done,
    and the arrows on its right. Then the settings of the row selected: a
    region's (its faces too, for one of the object's own) or a button's."""
    tree.ensure(context, obj)
    wm = context.window_manager
    _obj, region, index = tree.selection(context)
    button = core.button_of(region, index) if region is not None and index is not None else None
    row = layout.row()
    shown = tree.visible_count(context)
    row.template_list("KNEADY_UL_tree", "", wm, "kneady_rows", wm, "kneady_row",
                      rows=max(tree.ROWS_MIN, min(shown, tree.ROWS_MAX)), maxrows=tree.ROWS_MAX)
    col = row.column(align=True)
    if region is not None:
        col.context_pointer_set("kneady_region", region)
    if button is not None:
        col.context_pointer_set("kneady_button", button)
    sub = col.row(align=True)
    sub.enabled = region is not None or tree.can_add_region(obj)
    sub.operator("kneady.tree_add", icon="ADD", text="")
    sub = col.row(align=True)
    sub.enabled = region is not None and (index is not None or tree.own_index(obj, region) is not None)
    sub.operator("kneady.tree_remove", icon="REMOVE", text="")
    col.separator()
    col.menu("KNEADY_MT_buttons", icon="DOWNARROW_HLT", text="")
    col.separator()
    for icon, direction, step in (("TRIA_UP", "UP", -1), ("TRIA_DOWN", "DOWN", 1)):
        sub = col.row(align=True)
        sub.enabled = tree.can_move(context, step)
        sub.operator("kneady.tree_move", icon=icon, text="").direction = direction
    if region is None:
        return
    if button is None:
        if tree.own_index(obj, region) is not None:
            draw_faces(layout, context, obj, region)
        draw_region(layout, context, region)
    else:
        draw_button_settings(layout, context, region, index)


def draw_faces(layout, context, obj, region):
    """Which faces are the region. Edit Faces goes into Edit Mode, then
    Assign, Remove, Select and Deselect work as they do for vertex groups.
    Or the region is the whole object."""
    box = layout.box()
    if context.mode == "EDIT_MESH" and context.edit_object is obj:
        # Faces from vertex groups: its bone's group (core.bone_groups), or one chosen
        if obj.vertex_groups:
            from . import ops
            rig, bone = ops.region_bone(region)
            if bone:
                op = box.operator("kneady.region_group", text="Select Faces of %s" % bone, icon="BONE_DATA")
                op.from_bone = True
            row = box.row(align=True)
            row.prop_search(obj.kneady, "faces_group", obj, "vertex_groups", text="")
            row.operator("kneady.region_group", icon="RESTRICT_SELECT_OFF").from_bone = False
        row = box.row(align=True)
        row.operator("kneady.region_faces", text="Assign").action = "ASSIGN"
        row.operator("kneady.region_faces", text="Remove").action = "REMOVE"
        row = box.row(align=True)
        row.operator("kneady.region_faces", text="Select").action = "SELECT"
        row.operator("kneady.region_faces", text="Deselect").action = "DESELECT"
        box.operator("kneady.region_edit", text="Done", icon="CHECKMARK")
        if not context.scene.kneady_on:
            box.label(text="Turn Kneady on to see the regions", icon="INFO")
        return
    row = box.row(align=True)
    sub = row.row(align=True)
    sub.enabled = not region.whole and not region.attribute
    sub.operator("kneady.region_edit", text="Edit Faces", icon="EDITMODE_HLT")
    row.prop(region, "whole", toggle=True)
    if region.whole:
        return
    row = box.row(align=True)
    row.prop(region, "attribute", icon="GEOMETRY_NODES")
    if region.attribute:
        row.prop(region, "value", text="")
        return
    tags = core.face_tags(obj.data)
    if tags is None or not (tags == region.id).any():
        box.label(text="No faces yet: Edit Faces, select some, Assign", icon="INFO")


def draw_region(layout, context, region):
    """A region's settings, shown when its row is selected in the tree: its
    look, what a program adds, how its buttons line up, what the program
    adds about them (Place in 3D), and their one color. Its buttons are rows
    of the tree, under it."""
    if region.version > core.DATA_VERSION:
        layout.label(text="Made with a newer Kneady: update Kneady before editing it", icon="ERROR")
    row = layout.row(align=True)
    row.prop(region, "color", text="")
    row.prop(region, "opacity")
    if not region.whole:
        layout.prop(region, "show_through")
    for fn in REGION_EXTRAS:
        fn(layout, context, region)
    box = layout.box()
    box.label(text="Its Buttons", icon="ALIGN_JUSTIFY")
    box.row(align=True).prop(region, "arrange", expand=True)
    for fn in REGION_BUTTONS:
        fn(box, context, region)
    draw_list_color(box, core.button_list(region, core.list_key_for(region, None)))


def draw_button_settings(layout, context, region, index):
    """The settings of button `index`: what it does, how it shows, and its
    commands. How it shows means its icon, or no icon for a 3D handle. Greg:
    "I have a button set to arrow but I still have the Icon section for
    screenspace"."""
    button = core.buttons_of(region)[index]
    body = layout.box()
    body.label(text=button.name, icon="PROPERTIES")
    body.row().prop(button, "action", expand=True)
    if core.is_gap(button):
        # nothing to show or drive: it holds its place (core._layout)
        _wrapped(body, "Holds its place in the row or ring and shows nothing there. Viewport Edit shows it "
                 "dashed, to pick and move.", "INFO")
        return
    for fn in BUTTON_LOOKS:
        fn(body, context, region, button)
    if not placed.is_handle(button):
        _draw_icon(body, button)
    elif not BUTTON_LOOKS:
        body.label(text="Shown as a 3D handle on the item", icon="EMPTY_SINGLE_ARROW")
    for fn in BUTTON_EXTRAS:
        fn(body, context, region, button)
    if button.action == "TOGGLE":
        _draw_switch(body, context, button, region)
    else:
        body.prop(button, "single")
        for attr, label in DIRECTIONS:
            _draw_drag(body, context, label, getattr(button, attr), region)
        _draw_click(body, context, button, region)
    for fn in BUTTON_FOOTERS:
        fn(body, context, region, button)
    # Its tip comes last, since it is about everything above it (tips.py)
    tips.draw_settings(body, context, region, index)


def _draw_icon(layout, button):
    """What the button's circle shows: arrows (from its drags, or a set
    chosen), an image, a modeled shape or its name. Then its outline: a
    circle or a square (a text button is its name's box)."""
    row = layout.row(align=True)
    row.prop(button, "icon_type")
    if button.icon_type == "ARROWS" and button.action != "TOGGLE":
        row.prop(button, "arrows", text="")
    elif button.icon_type == "IMAGE":
        row.prop(button, "icon_image", text="")
    elif button.icon_type == "OBJECT":
        row.prop(button, "icon_object", text="")
    if button.icon_type != "TEXT":
        layout.row(align=True).prop(button, "shape", expand=True)


def draw_list_color(layout, found):
    """A list's Override Color (core.button_list's "color"), and its swatch
    once it is on: one color for every button in the list. Greg: "Button
    groups should always have the same color for buttons"."""
    if not found.get("color"):
        return
    owner, use, value = found["color"]
    row = layout.row(align=True)
    row.prop(owner, use)
    if getattr(owner, use):
        row.prop(owner, value, text="")


def _draw_commands(box, context, drag, region, switch=False):
    """A direction's or a toggle's commands. Each is a section that folds to
    what it drives, with a remove button on each once there are two, and
    Add Command under them. Greg: "When minimized it does show the input but
    everything else is tucked away. Default should be minimized"."""
    commands = [drag] + list(drag.more)
    for i, command in enumerate(commands):
        header, body = box.panel_prop(command, "command_open")
        _draw_command_header(header, context, command, region, switch)
        if len(commands) > 1:
            header.context_pointer_set("kneady_drag", drag)
            header.operator("kneady.command_remove", text="", icon="TRASH").index = i
        if body is not None:
            _draw_command(body.column(), context, command, region, switch)
    row = box.row()
    row.enabled = len(drag.more) + 1 < props.MAX_COMMANDS
    row.context_pointer_set("kneady_drag", drag)
    row.operator("kneady.command_add", icon="ADD")


def _draw_drag(layout, context, label, drag, region=None):
    """A drag direction: on or off in its header, and its commands (each
    moved by the same drag) in a section that folds away whether it is on or
    not. Greg: "collapsible sections so they can be hidden even when
    enabled"."""
    if not drag.enabled:
        # off: nothing to fold away
        folded_row(layout).prop(drag, "enabled", text=label)
        return
    header, body = layout.panel_prop(drag, "ui_open")
    header.prop(drag, "enabled", text=label)
    if body is not None:
        _draw_commands(body, context, drag, region)


def folded_row(layout):
    """A row lined up with the headers of sections that fold, for one with
    nothing in it to fold."""
    row = layout.row(align=True)
    row.label(text="", icon="BLANK1")
    return row


def _draw_switch(layout, context, button, region=None):
    """A toggle's commands: what a click switches on and off together, lit
    while the first is on. They sit in a section that folds away."""
    header, body = layout.panel_prop(button.switch, "ui_open")
    header.label(text="Click Switches", icon="CHECKBOX_HLT")
    if body is not None:
        _draw_commands(body, context, button.switch, region, switch=True)


def _draw_click(layout, context, button, region=None):
    """A drag button's click (click_on). Off, it is a row to turn it on. On,
    it shows what the click switches, as for a toggle, folding away like a
    direction."""
    if not button.click_on:
        folded_row(layout).prop(button, "click_on")
        return
    header, body = layout.panel_prop(button.switch, "ui_open")
    header.prop(button, "click_on")
    if body is not None:
        _draw_commands(body, context, button.switch, region, switch=True)


COMMAND_ICONS = {"ROTATE": "CON_ROTLIKE", "MOVE": "CON_LOCLIKE", "SCALE": "CON_SIZELIKE",
                 "INPUT": "MODIFIER", "PROPERTY": "RNA"}
_KIND_NAMES = {key: name for key, name, _tip in props.KINDS}
_AXIS_NAMES = {key: name for key, name, _tip in props.AXES}


def _command_problem(context, command, region=None, switch=False):
    """Why a command cannot run as it is set, or "". This is what its section
    shows in red, and what its header marks while folded. `switch` is True
    for what a click switches, False for a drag."""
    obj, why = props.command_target(command, context)
    if obj is None and why:
        return why
    if obj is not None and obj.type == "MESH":
        channel = core.Channel(command, obj, region, switch=switch)
        if not channel.ok:
            return channel.why
    return ""


def command_summary(command):
    """A turn, move or scale in a few words, for its folded header: "Rotate X
    on Upper". It names its bone, else its target, else nothing (the object
    dragged)."""
    what = "%s %s" % (_KIND_NAMES.get(command.kind, command.kind), _AXIS_NAMES.get(command.axis, command.axis))
    on = command.bone or (command.target_group if props.grouped(command)
                          else command.target.name if command.target is not None else "")
    return "%s on %s" % (what, on) if on else what


def _draw_command_header(header, context, command, region=None, switch=False):
    """A command's header, which stays when it is folded. It shows what the
    command drives: a modifier input's or a property's field, to change
    there, or the turn, move or scale and its bone. It also shows a mark
    when the command cannot run."""
    icon = COMMAND_ICONS.get(command.kind, "BLANK1")
    if command.program:
        spec = core.command_kind(command)
        text = (spec["summary"](command) if spec is not None and spec.get("summary")
                else spec["label"] if spec is not None else command.program)
        header.label(text=text, icon=spec["icon"] if spec is not None else "ERROR")
    elif command.kind == "INPUT":
        header.prop(command, "input", text="", icon=icon, placeholder="Input")
    elif command.kind == "PROPERTY":
        header.prop(command, "data_path", text="", icon=icon, placeholder="Path")
    else:
        header.label(text=command_summary(command), icon=icon)
    if _command_problem(context, command, region, switch):
        header.label(text="", icon="ERROR")


def _draw_command(col, context, command, region=None, switch=False):
    """What one command drives (for a toggle, a modifier input or a property
    to switch). The field its header shows (_draw_command_header) is not
    drawn again."""
    if switch:
        # Modifier Input, Property and a program's own kinds
        # (core.add_command_kind) are one choice, drawn as buttons that set
        # it, so a program's kind is one of them
        row = col.row(align=True)
        row.context_pointer_set("kneady_command", command)
        for kind in props.SWITCH_KINDS:
            op = row.operator("kneady.switch_kind", text=_KIND_NAMES[kind],
                              depress=not command.program and command.kind == kind)
            op.kind, op.program = kind, ""
        for spec in core.command_kinds(switch=True):
            op = row.operator("kneady.switch_kind", text=spec["label"], icon=spec["icon"],
                              depress=command.program == spec["key"])
            op.kind, op.program = "PROPERTY", spec["key"]
        spec = core.command_kind(command)
        if command.program and spec is None:
            col.label(text="Made by an add-on that is not running: %s" % command.program, icon="ERROR")
        elif spec is not None and spec.get("draw"):
            spec["draw"](col, context, command)
    else:
        # Rotate, Move, Scale, Modifier Input, Property, then what a program
        # gives a drag (core.add_command_kind's drag) as a button each. The
        # one chosen is depressed; clicked again, it goes back to the kind
        # above.
        sub = col.row()
        sub.active = not command.program
        sub.prop(command, "kind")
        kinds = core.command_kinds(switch=False)
        if kinds:
            row = col.row(align=True)
            row.context_pointer_set("kneady_command", command)
            for spec in kinds:
                row.operator("kneady.drag_kind", text=spec["label"], icon=spec["icon"],
                             depress=command.program == spec["key"]).program = spec["key"]
        spec = core.command_kind(command)
        if command.program and spec is None:
            col.label(text="Made by an add-on that is not running: %s" % command.program, icon="ERROR")
        elif spec is not None and spec.get("draw"):
            spec["draw"](col, context, command)
    col.prop(command, "dragged", text=core.term("dragged"))
    obj = props.drag_object(command, context)
    grouped = props.grouped(command)
    if not command.dragged:
        if core.has_groups() or grouped:
            # A program's groups (core.set_groups): one object, or a group's
            # object, the one the drag is on, as Greg asked
            row = col.row(align=True)
            row.prop_enum(command, "target_kind", "OBJECT")
            row.prop_enum(command, "target_kind", "GROUP", text=core.term("group"))
        if grouped:
            col.prop(command, "target_group", text="Group")       # the switch above names it in full
        else:
            col.prop(command, "target")
        # A region shared by many objects lives on no one object (Digit's lives
        # on the scene), so a target there is the same object whichever one is
        # dragged. Greg: "all the other digits drive that defined digit".
        if not grouped and command.target is not None and not isinstance(command.id_data, bpy.types.Object):
            col.label(text="Dragging any of them drives %s" % command.target.name, icon="INFO")
    if command.program:
        # A program's kind: its settings are its own (drawn above). A drag
        # also gets its Speed, for use off a 3D handle (along one, it follows
        # the mouse).
        drag = core.drag_kind(command)
        if not switch and drag is not None:
            turn = bool(drag["turns"](command)) if drag.get("turns") else False
            row = col.row(align=True)
            row.prop(command, "turn_rate" if turn else "rate")
            row.prop(command, "turn_step" if turn else "step")
            col.prop(command, "invert")
        problem = _command_problem(context, command, region, switch)
        if problem:
            col.label(text=problem, icon="ERROR")
        return
    if obj is not None and obj.type == "ARMATURE":
        col.prop_search(command, "bone", obj.data, "bones")
    # One click each: use the rig that deforms the hovered mesh, or the
    # target's active bone
    region_obj = context.active_object
    rig = core.mesh_rig(region_obj)
    if not command.dragged and not grouped and command.kind in {"ROTATE", "MOVE", "SCALE"}:
        row = col.row(align=True)
        row.context_pointer_set("kneady_command", command)
        if rig is not None and command.target is not rig:
            row.operator("kneady.command_rig", text="Use %s" % rig.name, icon="ARMATURE_DATA")
        active = core.active_bone(command.target) if command.target is not None else ""
        if active and active != command.bone:
            row.operator("kneady.command_bone", text="Use %s" % active, icon="BONE_DATA")
    if command.kind in {"ROTATE", "MOVE", "SCALE"}:
        row = col.row(align=True)
        for axis in ("X", "Y", "Z") + (("ALL",) if command.kind == "SCALE" else ()):
            row.prop_enum(command, "axis", axis)
        if command.kind == "MOVE" and command.axis not in core.VIEW_AXES and not command.bone \
                and not (obj is not None and obj.type == "ARMATURE"):
            # an object's Location channels, or its own turned axes
            col.prop(command, "along_parent")
    elif command.kind == "INPUT" and obj is not None:
        col.prop_search(command, "modifier", obj, "modifiers")
    if switch:
        row = col.row(align=True)
        row.prop(command, "sets_value")
        if command.sets_value:
            row.prop(command, "on_value", text="")
        else:
            col.prop(command, "invert", text="Invert: Lit at 0")
    else:
        row = col.row(align=True)
        turn = command.kind == "ROTATE"
        row.prop(command, "turn_rate" if turn else "rate")
        row.prop(command, "turn_step" if turn else "step")
        row = col.row()
        row.prop(command, "invert")
        if command.kind in {"INPUT", "PROPERTY"}:
            row.prop(command, "multiply")
        elif command.kind in core.TURNING and command.axis not in core.VIEW_AXES:
            row.prop(command, "follow")
    problem = _command_problem(context, command, region, switch)
    if problem:
        col.label(text=problem, icon="ERROR")


def _header(self, context):
    """The toggle in the viewport header, with a dropdown arrow beside it as
    Blender's Overlays have. The popover holds Kneady on or off, and Help.
    Greg wanted Help "also accessible somehow from the kneady button above
    the viewport. All you can do there is turn Kneady off and on and choose
    its proficiency"."""
    if context.mode in core.MODES:
        row = tutorials.emphasize(self.layout, context).row(align=True)
        row.prop(context.scene, "kneady_on", text="", icon=ICON)
        row.popover(panel="KNEADY_PT_header", text="")


class KNEADY_PT_header(bpy.types.Panel):
    """Kneady on or off, and how much it says"""
    bl_label = "Kneady"
    bl_idname = "KNEADY_PT_header"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 9

    def draw(self, context):
        layout = tutorials.emphasize(self.layout, context)
        layout.label(text="Kneady")
        layout.prop(context.scene, "kneady_on", text="On")
        if hasattr(context.window_manager, "kneady_help"):
            layout.separator()
            layout.label(text="Help")
            layout.column(align=True).prop(context.window_manager, "kneady_help", expand=True)


class KNEADY_PT_regions(bpy.types.Panel):
    """Kneady's own tab in the sidebar, the same whether it comes with
    another add-on or alone.
    Another add-on adds to it the way Blender's own panels are extended -
    KNEADY_PT_regions.append(draw_fn) - and, for objects whose regions it
    gives them, edits a region in place of the list (core.add_editor)."""
    # The same tab either way, so nothing changes for someone who starts with
    # Kneady alone. Greg: "Say a user gets kneady uses it then gets digit, this
    # would ensure they use kneady exactly as they had before"
    bl_label = "Kneady"
    bl_idname = "KNEADY_PT_regions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kneady"
    bl_order = 1                       # room above it for an add-on's own panel

    def draw(self, context):
        # The tutorial's current step lights the fields it is about
        # (tutorials.py). The tutorials themselves are the panel above
        # (KNEADY_PT_tutorials).
        layout = tutorials.emphasize(self.layout, context)
        draw_toggle(layout, context)
        row = layout.row()
        row.label(text="Button Size")
        row.prop(context.scene, "kneady_button_radius", text="", slider=True)
        # The 3D handles' own size. Greg: "change the size of the handles
        # separately from the standard buttons"
        row = layout.row()
        row.label(text="Handle Size")
        sub = row.row(align=True)
        sub.prop(context.scene, "kneady_handle_radius", text="", slider=True)
        # A thin dark edge round the handles' lines. Greg: "Contrast against
        # wireframe is a good idea"
        sub.prop(context.scene, "kneady_handle_halo", text="Halo", toggle=True)
        row = layout.row()
        row.label(text="Labels")
        row.prop(context.scene, "kneady_labels", expand=True)
        row = layout.row()
        row.label(text="Highlight")
        row.prop(context.scene, "kneady_highlight", expand=True)
        if context.scene.kneady_highlight == "OUTLINE":
            row = layout.row()
            row.label(text="Outline Width")
            row.prop(context.scene, "kneady_outline_width", text="", slider=True)
        if hasattr(context.window_manager, "kneady_pick"):
            # Viewport Edit (pick.py), once called Pick Buttons. Greg renamed
            # it: "I think we could add some things in that mode beyond just
            # picking buttons"
            layout.prop(context.window_manager, "kneady_pick", toggle=True, icon="RESTRICT_SELECT_OFF")
            if core.picking(context):
                layout.prop(context.window_manager, "kneady_arrange", toggle=True, icon="ARROW_LEFTRIGHT")
                from . import pick
                for fn in pick.PANEL_TOGGLES:
                    fn(layout, context)
                _wrapped(layout, "Click a button to edit it here (Ctrl+click only selects). At the corners of "
                         "its buttons: + and - add and remove, the dots turn Rearrange on. Right-click copies "
                         "and pastes.", "INFO")
        obj = tree.tree_object(context)
        if obj is None:
            layout.label(text="Select a mesh to give it regions", icon="INFO")
            return
        managed = core.editor_for(obj)
        if managed is None:
            draw_list(layout, context, obj)
            return
        # `managed` is (label, region[, header[, regions]]), from
        # core.add_editor. header(layout, context) draws above the tree, and
        # regions are the tree's top rows.
        label, _region, *rest = managed
        box = layout.box()
        box.label(text=label, icon="OBJECT_DATA")
        if rest and rest[0] is not None:
            rest[0](box, context)
        if tree.tree_regions(obj):
            draw_tree(box, context, obj)


_classes = (KNEADY_MT_buttons, KNEADY_PT_header, KNEADY_PT_regions)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_HT_header.append(_header)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(_header)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
