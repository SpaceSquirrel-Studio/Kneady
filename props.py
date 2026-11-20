"""Kneady's data: an object's regions, each with its buttons (up to
MAX_BUTTONS), each button with a command for each drag direction and its
icon.

The data is stored on the object (`Object.kneady`), and a region's faces are
tagged on its mesh (core.TAG), so a mesh keeps its regions wherever it is
appended."""

import math

import bpy  # type: ignore

from . import reg

MAX_BUTTONS = 24                   # what a region can hold, shown a level at a time (a program may nest them)
# how many fit in one row. It was six until Greg asked: "Let's make the
# maximum number of buttons 8 instead of 6"
ROW_BUTTONS = 8

# When a button shows (menus.py), and what shows of a placed one behind the
# item (placed.py)
WHEN = (("ALWAYS", "Always", "The button always shows"),
        ("ON", "While On", "The button shows while the switch is on"),
        ("OFF", "While Off", "The button shows while the switch is off"))
BEHIND = (("NONE", "Show Behind", "Show a placed button as it is, whichever way its side of the item faces"),
          ("HIDE", "Hide Behind", "Hide a placed button whose side of the item faces away from the view"),
          ("GHOST", "Ghost Behind", "Show a placed button whose side of the item faces away from the view faint, "
           "so you can still see where it is"))


# A placed button as a 3D handle (placed.py, handles). "HANDLE" was briefly
# named "ARROW", with the same stored value. Each item carries its stored
# number, so adding a shape never changes what a saved one reads as.
HANDLES = (("BUTTON", "Screen Button", "A button facing the screen, its icon in a circle or a square, dragged "
            "across and up the screen", 0),
           ("HANDLE", "3D Handle", "A shape in the scene at the button's place on the item - an arrow, a ring, "
            "or a mesh of the file's - keeping its direction as the view turns: a drag goes along it, a Move or "
            "Rotate following the mouse. A toggle is always a screen button", 1))
# An arrow, or a box at the end for a scale. Greg: "we're going to need a
# scale type of handle with a box at the end instead of an arrow". Each is
# Short, Medium, Long or Extra Long, and starts at the button's place or is
# Centered on it (HANDLE_LENGTHS, handle_centered). Greg: "3 single arrow
# types that are short, medium and long shaft. Long shaft is centered on the
# center of the whole object", "a long arrow type with the center at the
# beginning of the arrow shaft as an addition", "I'd like the current long
# arrows to be called extra long and make a new size between medium and
# extra long called long. Also we need the same variants but for the box".
# For a few hours the lengths were shapes of their own, stored as 6
# (Medium), 7 (Long, centered) and 8 (Long). LEGACY_SHAPES turns them into an
# Arrow with its Length and Centered (core's data version 2).
HANDLE_SHAPES = (("ARROW", "Arrow", "An arrow from the button's place - or through it, Centered: drag along it, "
                  "either way", 0),
                 ("BOX", "Box", "A shaft with a box at its end, as a scale handle, from the button's place - or "
                  "through it, Centered: drag along it, either way", 5),
                 ("DOUBLE", "Double Arrow", "An arrow with a head at each end, through the button's place: drag "
                  "either way along it", 3),
                 ("CROSS", "Quad Arrow", "Two double arrows crossing at the button's place, one for each of its "
                  "directions - Up / Down along one, Left / Right along the other", 4),
                 ("RING", "Ring", "A ring about the axis a Rotate turns on: drag around it, as R turns - or, seen "
                  "edge on, along its rim, as you would turn a wheel", 2),
                 ("OBJECT", "Object", "A mesh object's shape, drawn in 3D: model it pointing along its +Y, as a "
                  "bone's custom shape is", 1))
HANDLE_LENGTHS = (("SHORT", "Short", "Its shaft as long as it always was", 0),
                  ("MEDIUM", "Medium", "Its shaft twice a short one's", 1),
                  ("LONG", "Long", "Its shaft three times a short one's", 2),
                  ("EXTRA_LONG", "Extra Long", "Its shaft nearly five times a short one's", 3))
# those short-lived length shapes, by their stored numbers (and, in copied
# or saved settings, by their names), as (shape, length, centered)
LEGACY_SHAPES = {6: ("ARROW", "MEDIUM", False), 7: ("ARROW", "EXTRA_LONG", True), 8: ("ARROW", "EXTRA_LONG", False)}
LEGACY_SHAPE_NAMES = {"ARROW_MEDIUM": 6, "ARROW_LONG_CENTERED": 7, "ARROW_LONG": 8}
HANDLE_AXES = (("AUTO", "From Its Command", "Along a Move's axis, the way a Rotate turns its place, or out from the "
                "surface for anything else - its Up / Down command's, else its Left / Right one's"),
               ("NORMAL", "Surface", "Out from the item's surface where the button is placed"),
               ("X", "X", "The X axis of the bone its region rides, or of the object"),
               ("Y", "Y", "The Y axis of the bone its region rides, or of the object"),
               ("Z", "Z", "The Z axis of the bone its region rides, or of the object"))


def _redraw(_self, _context):
    from . import core
    core.redraw()


# -- A list's color -----------------------------------------------------------------------
#
# Greg: "Button groups should always have the same color for buttons so per
# button color overrides aren't necessary." So each list of a region's
# buttons has one color. The lists are the region's own buttons, in its row
# or placed in 3D (`use_button_color`), and each menu's (`menu_use_color`, on
# the button that opens it). A list that does not override its color takes
# the color of what it hangs from (core.button_colors).

def _list_color_on(use, value, done, start):
    """The update for an Override Color. The first time it is switched on,
    the swatch starts at the color the list had, `start(owner)`. After that
    it keeps what was picked."""
    def update(owner, _context):
        from . import core
        if getattr(owner, use) and not getattr(owner, done):
            found = start(owner)
            if found is not None:
                setattr(owner, value, found)
            setattr(owner, done, True)
        core.redraw()
    return update


def _opener_color(button):
    """The color a menu's button is drawn in: its menu starts there."""
    from . import core
    region, index = core.button_home(button)
    if region is None or index is None or index >= len(core.buttons_of(region)):
        return None
    return core.button_colors(region)[index]


def _opens_changed(button, _context):
    """A button made to open a menu gets the id its menu's buttons find."""
    from . import core, menus
    region, _index = core.button_home(button)
    if region is not None:
        menus.ensure_uid(region, button)
    core.redraw()


# -- Search fields and undo ----------------------------------------------------------------
#
# Greg: "changing input then hauling to test it then undoing undoes the haul
# and setting the input. Makes testing this tedious." Blender gives a pick
# from a search field (a property with a search list, or prop_search) no
# undo step of its own. Checked in a window, Blender 5.2: with an input or a
# bone picked and then a drag made, Ctrl+Z took both back. A number typed in
# got its own step.
#
# So a pick made in the panel gets an undo step here, once Blender has
# finished applying it, when both of these hold:
#   - the change comes with a region (the panel's). A script run on its own
#     has none.
#   - no operator has finished since. One that sets a field (Regions from
#     Bones) records its own step, and a second would cost an extra Ctrl+Z.

_UNDO = {"pending": None, "last": 0}


def _last_operator(wm):
    """The last operator Blender recorded, as a number to compare, or 0."""
    try:
        return wm.operators[-1].as_pointer() if wm is not None and len(wm.operators) else 0
    except (AttributeError, IndexError, ReferenceError):
        return 0


def _push_undo():
    message, _UNDO["pending"] = _UNDO["pending"], None
    wm = bpy.context.window_manager
    if not message or _last_operator(wm) != _UNDO["last"]:
        return None                    # an operator finished since: its own step holds the change
    window = wm.windows[0] if wm is not None and wm.windows else None
    try:
        if window is not None:
            with bpy.context.temp_override(window=window):
                bpy.ops.ed.undo_push(message=message)
        else:
            bpy.ops.ed.undo_push(message=message)
    except (RuntimeError, TypeError):
        pass
    return None


def searched(name, then=None):
    """An update for a property picked from a search field. When the panel
    set it, it gets an undo step of its own, shown as `name` in the undo
    history. `then` is the property's own update, if it has one, run
    first."""
    def update(self, context):
        if then is not None:
            then(self, context)
        if getattr(context, "region", None) is None:
            return                     # a script's: it makes its own undo steps, or none
        if _UNDO["pending"] is None:
            _UNDO["last"] = _last_operator(context.window_manager)
            bpy.app.timers.register(_push_undo, first_interval=0.0)
        _UNDO["pending"] = name
    return update

KINDS = (
    ("ROTATE", "Rotate", "Turn the target about one of its own axes, following the mouse"),
    ("MOVE", "Move", "Move the target along one of its own axes, following the mouse"),
    ("SCALE", "Scale", "Scale the target on one of its own axes, or all three: right and up grow it"),
    ("INPUT", "Modifier Input", "A Geometry Nodes modifier input, by name: right and up raise it"),
    ("PROPERTY", "Property", "Any property, by its data path (right-click a field > Copy Data Path): right "
     "and up raise it"),
)
AXES = (("X", "X", "The target's own X"), ("Y", "Y", "The target's own Y"), ("Z", "Z", "The target's own Z"),
        ("ALL", "All", "All three axes (Scale only)"),
        ("VIEW", "View", "Across and up the view, whichever way the target faces: a Move follows the mouse, as G "
         "does; a Rotate turns it as if the mouse rolled it, as R pressed twice does (Move and Rotate only)"),
        ("DEPTH", "Depth", "Along the line of sight: a Move toward or away from you, a Rotate rolls it about the "
         "view's direction (Move and Rotate only)"))
GRAPHICS = (("ARROWS", "Arrows", "Arrows drawn from the drags: curved for a turn, straight otherwise"),
            ("IMAGE", "Image", "An image, facing the view"),
            ("OBJECT", "Object", "A mesh object's faces, facing the view: model it flat, in any view"),
            ("TEXT", "Text", "The button's name in a rounded box as tall as a circle, as wide as the name"))
# Which arrows an Arrows icon draws (Greg: "there's no way to choose which
# set of arrows you want. That seems to just be determined behind the
# scenes")
ARROW_SETS = (("AUTO", "From Drags", "An arrow for each direction the button drives: up and down, left and "
               "right, or both - curved where it turns something"),
              ("ACROSS", "Left and Right", "A straight arrow, left and right"),
              ("UP", "Up and Down", "A straight arrow, up and down"),
              ("BOTH", "Four Ways", "Straight arrows, up and down and left and right"),
              ("CURVED_ACROSS", "Curved Left and Right", "A curved arrow, left and right: a turn"),
              ("CURVED_UP", "Curved Up and Down", "A curved arrow, up and down: a turn"),
              ("CURVED_BOTH", "Curved Four Ways", "Curved arrows, up and down and left and right"),
              ("DIAGONAL", "Diagonal", "A straight arrow from corner to corner"),
              ("OUTWARD", "Outward", "Four arrows out to the corners: a growth"),
              ("SPIN", "Spin", "An arrow round in a circle: a twist"))


def _gn_modifier(obj, name):
    if obj is None:
        return None
    if name:
        mod = obj.modifiers.get(name)
        return mod if mod is not None and mod.type == "NODES" else None
    return next((m for m in obj.modifiers if m.type == "NODES" and m.node_group is not None), None)


def grouped(drag):
    """Whether a command drives one of a group's objects (core.set_groups)
    rather than one Target: Deform Hovered is off and Group is chosen."""
    return drag.target_kind == "GROUP" and (drag.target is not None or drag.pick_target)


def drag_object(drag, context=None):
    """The object a drag acts on, as the panel sees it: its target, else the
    object its region is on (the active one, for a region many objects
    share). For a group, one of the group's objects, to show what they
    have."""
    return command_target(drag, context)[0]


def command_target(drag, context=None):
    """(object, why): drag_object, and why there is none."""
    context = context or bpy.context
    if grouped(drag):
        from . import core
        return core.command_object(drag, None, None, context)
    if drag.target is not None:
        return drag.target, ""
    if drag.pick_target:
        return None, "Pick its target"
    owner = drag.id_data
    if isinstance(owner, bpy.types.Object):
        return owner, ""
    return getattr(context, "active_object", None), ""


def _group_search(self, context, edit_text):
    """The groups a program gives (core.set_groups): all of them when the
    field is opened on its value, else those holding what is typed."""
    from . import core
    names = core.group_names(context)
    text = edit_text.strip().lower()
    if not text or edit_text == self.target_group:
        return names
    return [name for name in names if text in name.lower()]


TARGET_KINDS = (("OBJECT", "Object", "One object, its Target"),
                ("GROUP", "Group", "A group's objects: the one the drag is on, as the add-on giving the groups "
                 "picks it - Digit's control groups, the hovered digit"))


def number_inputs(mod, booleans=False):
    """A Geometry Nodes modifier's float and integer inputs, by name, in its
    panel's order. Only the inputs its panel shows, not those hidden from
    it. With `booleans`, its boolean inputs too (what a toggle switches)."""
    if mod is None or mod.node_group is None:
        return []
    kinds = ("NodeSocketFloat", "NodeSocketInt") + (("NodeSocketBool",) if booleans else ())
    return [item.name for item in mod.node_group.interface.items_tree
            if item.item_type == "SOCKET" and item.in_out == "INPUT"
            and item.socket_type.startswith(kinds)
            and not getattr(item, "hide_in_modifier", False)]


def is_switch_command(command):
    """Whether a command is a toggle button's (KNEADY_PG_button.switch) - one
    of what a click switches on and off - rather than a drag's."""
    try:
        return ".switch" in command.path_from_id()
    except (ValueError, TypeError, AttributeError):
        return False


def _input_search(self, context, edit_text):
    """The inputs to choose from: all of them when the field is opened on its
    current value, else those holding what is typed. Blender hands the
    search the text already in the field, and filtering by it listed just
    that one input - Greg: "My only input option is width"."""
    names = number_inputs(_gn_modifier(drag_object(self, context), self.modifier), is_switch_command(self))
    text = edit_text.strip().lower()
    if not text or edit_text == self.input:
        return names
    return [name for name in names if text in name.lower()]


def path_suggestions(obj, booleans=False):
    """Paths a Property command could drive on `obj`, written from it. First
    each shape key's value (except the Basis), then the number custom
    properties of the object, its data and, on a rig, its pose bones. With
    `booleans`, their true / false ones too (what a toggle switches). These
    are only suggestions: any path can be typed."""
    out = []
    if obj is None:
        return out
    data = getattr(obj, "data", None)
    keys = getattr(data, "shape_keys", None) if data is not None else None
    if keys is not None:
        for block in keys.key_blocks:
            if block != keys.reference_key:
                out.append('data.shape_keys.key_blocks["%s"].value' % block.name.replace('"', '\\"'))
    kinds = (int, float, bool) if booleans else (int, float)
    owners = [(obj, ""), (data, "data")]
    # a rig's switches live on its pose bones: an IK / FK switch (Rigify's
    # IK_FK on upper_arm_parent.L), a finger's curl
    pose = getattr(obj, "pose", None) if getattr(obj, "type", "") == "ARMATURE" else None
    for bone in (pose.bones if pose is not None else ()):
        owners.append((bone, 'pose.bones["%s"]' % bone.name.replace('"', '\\"')))
    for owner, prefix in owners:
        if owner is None or not hasattr(owner, "keys"):
            continue
        for key in owner.keys():
            try:
                value = owner[key]
            except (KeyError, TypeError):
                continue
            if key.startswith("_") or not isinstance(value, kinds) or (isinstance(value, bool) and not booleans):
                continue
            out.append('%s["%s"]' % (prefix, key.replace('"', '\\"')))
    return out


def _path_search(self, context, edit_text):
    """The Path's suggestions (path_suggestions): all of them when the field
    is opened on its value, else those holding what is typed. Anything else
    typed is taken as it is (the search is a suggestion)."""
    paths = path_suggestions(drag_object(self, context), is_switch_command(self))
    text = edit_text.strip().lower()
    if not text or edit_text == self.data_path:
        return paths
    return [path for path in paths if text in path.lower()]


def _fill_buttons(region):
    """Add buttons until a region has as many as it asks for. A region made
    when the most was five has five, so raising its count adds the rest."""
    while len(region.buttons) < min(region.button_count, MAX_BUTTONS):
        added = region.buttons.add()
        added.name = "Button %d" % len(region.buttons)


def _mesh_object(_self, obj):
    return obj.type == "MESH"


MAX_COMMANDS = 16                  # per drag direction, its own and the ones added: a fist curls 12 bones


def dragged_of(command):
    """Deform Hovered (called The One Dragged until Greg renamed it; Digit's
    panel says Deform Hovered Digit, core.term). On, the command drives the
    object dragged: the one hovered when the drag began, which on a region
    many objects share is whichever of them it is. Off, it drives its
    Target. Greg: "on by default and a user toggles it off when they want
    something specific". It is read from what is stored, so a command saved
    with a target before the toggle existed reads as off and keeps driving
    that target."""
    return command.target is None and not command.pick_target


def _set_dragged(command, value):
    if value:
        command.target = None
    command.pick_target = not value


def _command_fields():
    """What one command drives: the same fields for a direction's own command
    and each added one."""
    return {
        "kind": bpy.props.EnumProperty(name="Drives", items=KINDS, default="ROTATE"),
        "dragged": bpy.props.BoolProperty(
            name="Deform Hovered Object", get=dragged_of, set=_set_dragged,
            description="Drive the object hovered when the drag begins - on a region many objects share, "
                        "whichever of them it is. Off: drive the Target"),
        "pick_target": bpy.props.BoolProperty(
            options={"HIDDEN"}, description="Deform Hovered turned off before a target was picked"),
        "target": bpy.props.PointerProperty(
            name="Target", type=bpy.types.Object,
            description="What it drives when Deform Hovered is off"),
        "target_kind": bpy.props.EnumProperty(
            name="Drives", items=TARGET_KINDS, default="OBJECT",
            description="With Deform Hovered off: one object, or a group's - the one the drag is on"),
        "target_group": bpy.props.StringProperty(
            name="Group", search=_group_search, update=searched("Group"),
            description="The group whose objects it drives: the one the drag is on"),
        "bone": bpy.props.StringProperty(name="Bone", update=searched("Bone"),
                                         description="A bone of the target armature, to drive it"),
        "axis": bpy.props.EnumProperty(name="Axis", items=AXES, default="X"),
        "modifier": bpy.props.StringProperty(name="Modifier", update=searched("Modifier"),
                                             description="Empty: the target's first Geometry Nodes modifier"),
        "input": bpy.props.StringProperty(name="Input", description="The modifier input, by name",
                                          search=_input_search, update=searched("Input")),
        # suggested: the target's shape keys and custom properties. Before
        # Drive More Than Bones added them, a shape key's path from the
        # object (data.shape_keys.key_blocks["Sphere"].value) had to be
        # typed. Any other path typed is taken
        "data_path": bpy.props.StringProperty(
            name="Path", description="A data path from the target, as right-click > Copy Data Path gives it - "
            "its shape keys and custom properties are listed to pick",
            search=_path_search, search_options={"SUGGESTION"}, update=searched("Path")),
        # a Move of an object along its Location channels (its parent's
        # axes, as typing in the Item panel moves it), not its own turned
        # axes. Greg, of a finger's arrows: "I can go into the item n panel
        # and change those channels and this is what the move handles would
        # do". A bone's Move is along its channels already
        "along_parent": bpy.props.BoolProperty(
            name="Location Channels",
            description="Move an object along its Location channels - its parent's axes, as typing in the Item "
                        "panel does - not along its own turned axes"),
        # A kind of command a program adds (core.add_command_kind) - for what a
        # click switches, or for a drag: its key, and its settings as the
        # program keeps them (text). Set, it is what the command drives,
        # whatever `kind` says
        "program": bpy.props.StringProperty(name="Program Command", options={"HIDDEN"}),
        "program_data": bpy.props.StringProperty(name="Program Settings", options={"HIDDEN"}),
        "turn_rate": bpy.props.FloatProperty(name="Speed", subtype="ANGLE", default=math.radians(50.0),
                                             description="How far it turns for 100 pixels of drag"),
        "rate": bpy.props.FloatProperty(name="Speed", default=0.3, description="How far it goes for 100 pixels "
                                        "of drag (for Scale, as a growth: 0.3 is about a third)"),
        "turn_step": bpy.props.FloatProperty(name="Ctrl Step", subtype="ANGLE", default=math.radians(5.0),
                                             min=0.0, description="Ctrl snaps the turn to steps of this"),
        "step": bpy.props.FloatProperty(name="Ctrl Step", default=0.05, min=0.0,
                                        description="Ctrl snaps the value to steps of this"),
        "invert": bpy.props.BoolProperty(name="Invert", description="Drive it the other way"),
        # A toggle that sets a value of its own, one of a choice. It is lit
        # while the property holds the value, a click sets it, and a click
        # when lit does nothing. Why: a CloudRig rig's IK parent (Root, Torso,
        # Chest, Shoulder) is a number 0 to 3, which an on / off toggle
        # cannot reach
        "sets_value": bpy.props.BoolProperty(
            name="Sets a Value", description="A click sets the value beside it, and the button is lit while the "
            "property holds it - one button of several for a choice, as a parent switch's Root, Torso, Chest "
            "and Shoulder"),
        "on_value": bpy.props.FloatProperty(name="Value", default=1.0, description="The value a click sets"),
        # Off for commands that go their own ways at once - fingers spreading
        # fan apart, where following the mouse would send them all one way
        "follow": bpy.props.BoolProperty(
            name="Follow the Mouse", default=True,
            description="A Rotate or Move goes the way the mouse goes, whatever the view. Off: right and up turn "
                        "or move it the positive way, Invert the other - for commands that go different ways at "
                        "once, as fingers spreading apart do"),
        "multiply": bpy.props.BoolProperty(
            name="Multiply", description="Scale the value by the drag instead of adding to it, so values driven "
            "together keep their proportions: Speed 0.3 grows it by about a third over 100 pixels, and Ctrl "
            "snaps the factor to steps of Ctrl Step"),
    }


def copy_command(src, dst):
    """One command's settings onto another (a direction's own or an added
    one): what it drives, its target, speed and step. Deform Hovered is
    read from the target, so it comes with it."""
    for name in COMMAND_FIELDS:
        if name != "dragged":
            setattr(dst, name, getattr(src, name))


COMMAND_FIELDS = tuple(_command_fields())


def _command_open():
    """A command's section in the panel. It starts folded, showing only what
    the command drives - Greg: "When minimized it does show the input but
    everything else is tucked away. Default should be minimized". It is not
    a setting: core.SKIP_DATA leaves it out of a copy, a paste and a
    preset."""
    return bpy.props.BoolProperty(default=False)


class KNEADY_PG_command(bpy.types.PropertyGroup):
    """A command added to a drag direction: it moves with the direction's
    own, by its own target, speed and step (Greg: "Can control drive
    multiple attributes? ... 2 start slide parameters at once")."""
    __annotations__ = dict(command_open=_command_open(), **_command_fields())


class KNEADY_PG_drag(bpy.types.PropertyGroup):
    """What one drag direction drives: its own command, and any added."""
    __annotations__ = dict(
        enabled=bpy.props.BoolProperty(name="Enabled", description="Drag this way to drive something"),
        more=bpy.props.CollectionProperty(type=KNEADY_PG_command),
        # its section in the panel, open or folded whether it is on or not
        # (Greg: "collapsible sections so they can be hidden even when enabled")
        ui_open=bpy.props.BoolProperty(default=True),
        command_open=_command_open(),          # its own command's section
        **_command_fields())


SWITCH_KINDS = ("INPUT", "PROPERTY")      # what a toggle switches


def _action_changed(button, _context):
    """A toggle switches a modifier input or a property. So a button made a
    toggle gets its switch command turned on, set to Property if it was
    neither."""
    if button.action == "TOGGLE":
        button.switch.enabled = True
        if button.switch.kind not in SWITCH_KINDS:
            button.switch.kind = "PROPERTY"


def _click_changed(button, _context):
    """A drag button's Click turned on: what it switches starts as a
    property, as a toggle's does."""
    if button.click_on and button.switch.kind not in SWITCH_KINDS and not button.switch.program:
        button.switch.kind = "PROPERTY"


# A row of a button's tip, as its author words it (tips.py). Each is kept by
# what it is about (a drag direction, the click, a key), not by its place,
# so reordering or adding a command keeps it. One whose row is gone stays
# stored, and comes back when the row does.
TIP_SHOW = (("AUTO", "Auto", "Shown or not as Kneady decides: the drags and the click shown, keys that work "
                             "on every button hidden"),
            ("SHOW", "Show", "Always in the tip"),
            ("HIDE", "Hide", "Never in the tip; the status bar still says it"))


class KNEADY_PG_tip_row(bpy.types.PropertyGroup):
    """What one row of a button's tip says the key does, and whether it is
    shown. The key itself is never the author's: it comes from the
    button's commands, so it cannot go stale."""
    key: bpy.props.StringProperty(options={"HIDDEN"})
    text: bpy.props.StringProperty(
        name="Says", update=_redraw,
        description="What this row says the key does. Empty: Kneady's own words, from the button's commands")
    show: bpy.props.EnumProperty(name="Show", items=TIP_SHOW, default="AUTO", update=_redraw)


class KNEADY_PG_button(bpy.types.PropertyGroup):
    """A button: one set of commands for a region's drags, shown as a circle
    in the region's middle when it is hovered. Or a toggle, switched by a
    click and lit while on - Greg: "Boolean Buttons that when clicked simply
    stay highlighted for boolean properties"."""
    name: bpy.props.StringProperty(name="Name", default="Button")
    show: bpy.props.BoolProperty(name="Show", default=True, description="Show this button in the viewport")
    action: bpy.props.EnumProperty(
        name="Button", default="DRAG", update=_action_changed,
        items=(("DRAG", "Drag", "Drag from the button to run its commands, one set for each direction"),
               ("TOGGLE", "Toggle", "Click the button to switch what it drives on or off: a boolean, or a number "
                "between 0 and 1 (a rig's IK / FK switch). It stays lit while on"),
               # Greg's "Empty" buttons, for spacing a menu's ring
               ("GAP", "Gap", "Hold a place in the row or the ring and show nothing there, to space the buttons "
                "around it. Seen only while Viewport Edit is on, dashed")),
        description="What the button does: drag it, click it to switch something on and off, or hold a place")
    # A toggle's commands: what a click switches, each a modifier input or a
    # property; the first's value is what lights the button
    switch: bpy.props.PointerProperty(type=KNEADY_PG_drag)
    # A drag button's click, working as a toggle's. Greg, of Digit's handles:
    # "I might have the sides handles appear when I click on the Bend X /
    # Bend Y instead of hauling". A drag still runs its directions, while a
    # click switches `switch` instead of selecting, the button lit while on.
    # On a button that opens a menu, opening the menu switches it on, and
    # closing the menu with its button or Esc switches it off
    click_on: bpy.props.BoolProperty(
        name="Click Switches", update=_click_changed,
        description="A click switches something on and off, as a toggle's does, and the button stays lit while "
                    "it is on; a drag still runs the button's directions. On a button that opens a menu, opening "
                    "the menu switches it on, closing it with the button or Esc switches it off")
    single: bpy.props.BoolProperty(
        name="Drags Prefer Single Direction", default=True,
        description="Once a drag sets off, it drives only the direction it set off in, so one thing changes "
                    "at a time. Holding Alt during the drag hands it to the other direction and releasing "
                    "Alt hands it back, each keeping what the other did")
    across: bpy.props.PointerProperty(type=KNEADY_PG_drag)          # left and right
    up: bpy.props.PointerProperty(type=KNEADY_PG_drag)              # up and down
    # The button's graphic, in its circle on the hovered region - the only
    # graphic (Greg: "the buttons will carry the graphics")
    icon_type: bpy.props.EnumProperty(name="Icon", items=GRAPHICS, default="ARROWS",
                                      description="What the button's circle shows")
    arrows: bpy.props.EnumProperty(name="Arrows", items=ARROW_SETS, default="AUTO",
                                   description="Which arrows the circle shows")
    icon_image: bpy.props.PointerProperty(name="Icon Image", type=bpy.types.Image)
    icon_object: bpy.props.PointerProperty(name="Icon Object", type=bpy.types.Object, poll=_mesh_object)
    # its outline (Greg: "options for square buttons vs.
    # round ... the ability to create visual distinction"; "Squares have
    # rounded corners like the text boxes for sure")
    shape: bpy.props.EnumProperty(
        name="Shape", default="CIRCLE",
        items=(("CIRCLE", "Circle", "A round button"),
               ("SQUARE", "Square", "A square button, its corners rounded as a text button's are")),
        description="The button's outline, to tell kinds of button apart at a glance (a text button is "
                    "always its name's box)")
    # its settings' panel, closed to start (Greg: "It's overwhelming seeing
    # multiple open. Closed it's clear what needs to be done and that there's
    # organization")
    ui_open: bpy.props.BoolProperty(default=False)

    # -- Layouts a file carries --
    # Where a button sits on the item (placed.py), the menu it opens or is in
    # and when it shows (menus.py), and how a toggle keeps the pose as it
    # switches (switching.py). Kneady plays every one. They are ordinary
    # data, which a script may write as well.
    placed: bpy.props.BoolProperty(
        name="Placed on Surface", update=_redraw,
        description="Shown at its own point on the item, not in the region's row")
    place: bpy.props.FloatVectorProperty(
        name="Position", size=3, subtype="XYZ", soft_min=-1.5, soft_max=1.5, step=5, update=_redraw,
        description="Where the button is in the region's box, -1 to 1 across it on each axis, in the frame of "
                    "the bone the region's first button turns (or the object)")
    place_normal: bpy.props.FloatVectorProperty(size=3, options={"HIDDEN"},
                                                description="The item's surface there, facing out")
    place_set: bpy.props.BoolProperty(options={"HIDDEN"}, description="Whether its position has been set")
    # Where a placed button sits, if not on its region's surface: an anchor
    # (core.add_anchors), by its key. An anchor is a bone's head or tail, an
    # object's origin, or a point a program gives (Digit: a ring's sides, its
    # tip). Stored by key, the button follows that point exactly, and one
    # setting fits every object a region is shared by. Greg: "How to place
    # the handles ... I imagine they would be placed similarly to how
    # buttons are placed". Empty: on the surface, at `place`
    anchor: bpy.props.StringProperty(
        name="Sits At", update=_redraw,
        description="The point the button sits at and follows - a bone's head or tail, an object's origin, or "
                    "a point an add-on gives. Empty: on the surface, where it was placed")
    # where a button that opens a menu shows while its menu is open, if not
    # where it was clicked: the way back out
    back_placed: bpy.props.BoolProperty(
        name="Placed While Open", update=_redraw,
        description="While its menu is open, the button shows at its own point, not where it was clicked")
    back_place: bpy.props.FloatVectorProperty(
        name="Position While Open", size=3, subtype="XYZ", soft_min=-1.5, soft_max=1.5, step=5, update=_redraw,
        description="Where the button shows while its menu is open, in the region's box, -1 to 1 across it on "
                    "each axis")
    back_normal: bpy.props.FloatVectorProperty(size=3, options={"HIDDEN"})
    # A placed button as a 3D handle (Greg: "situations,
    # particularly when a button has been placed on a surface, where the haul
    # happening relative to world space is advantageous. More like grabbing
    # an empty and dragging it in space"): it keeps its direction in the scene
    # as the view turns, and a drag goes along it
    handle: bpy.props.EnumProperty(
        name="Shows As", items=HANDLES, default="BUTTON", update=_redraw,
        description="How a placed button shows and drags: a button facing the screen, or a 3D handle on the "
                    "item")
    handle_shape: bpy.props.EnumProperty(
        name="Shape", items=HANDLE_SHAPES, default="ARROW", update=_redraw,
        description="What the 3D handle looks like")
    handle_length: bpy.props.EnumProperty(
        name="Length", items=HANDLE_LENGTHS, default="SHORT", update=_redraw,
        description="How long an arrow's or a box's shaft is")
    handle_centered: bpy.props.BoolProperty(
        name="Centered", update=_redraw,
        description="Through the button's place, its middle there - not from it")
    handle_object: bpy.props.PointerProperty(
        name="Shape Object", type=bpy.types.Object, poll=lambda _self, o: o.type == "MESH", update=_redraw,
        description="The mesh whose shape the 3D handle takes, pointing along its +Y")
    handle_axis: bpy.props.EnumProperty(
        name="Points", items=HANDLE_AXES, default="AUTO", update=_redraw,
        description="Which way the 3D handle points")
    handle_flip: bpy.props.BoolProperty(name="Flip", update=_redraw,
                                        description="Point the 3D handle the other way")
    # A 3D handle's own size and color (Greg: "we're going to need the
    # ability to color a handle", "the rotate needs to be much larger").
    # Unlike a button, a handle is not one of a list of buttons sharing a
    # color: an axis's handle is drawn in its axis's color, and a ring as
    # large as its turn
    handle_size: bpy.props.FloatProperty(
        name="Size", default=1.0, min=0.25, max=10.0, soft_min=0.5, soft_max=4.0, update=_redraw,
        description="How big this 3D handle is, against the scene's Handle Size: a ring 2.5 times as wide, an "
                    "arrow's shaft and head 2.5 times as long and thick")
    # how much of it shows (Greg: "Opacity would be an additional useful
    # setting for the handles")
    handle_opacity: bpy.props.FloatProperty(
        name="Opacity", subtype="FACTOR", default=1.0, min=0.05, max=1.0, update=_redraw,
        description="How much of this 3D handle shows: its fill and edge alike. It takes the mouse as ever")
    # its shaft fading toward its root (Greg: "I'm curious how a gradient
    # falloff would look for the shafts", "along it's length, starting at
    # middle")
    handle_shaft_falloff: bpy.props.FloatProperty(
        name="Shaft Falloff", subtype="FACTOR", default=0.0, min=0.0, max=1.0, update=_redraw,
        description="How much this 3D handle's shaft fades along its length: solid near the head, then fading "
                    "over the rest toward its root - at 1, gone there. A double arrow's two halves each fade "
                    "toward its middle")
    # how it shows where anything is in front of it (Greg: "Let's have the
    # ghost behind option available for handles")
    handle_behind: bpy.props.EnumProperty(
        name="Behind", default="REGION", update=_redraw,
        items=(("REGION", "As Region", "As the region's Behind says: hidden, faint or as it is, where anything is "
                "in front of it", 0),
               ("SHOW", "Show Behind", "As it is, whatever is in front of it", 1),
               ("GHOST", "Ghost Behind", "Faint where anything is in front of it, so you can still see where it is "
                "- and grab it", 2),
               ("HIDE", "Hide Behind", "Hidden where anything is in front of it", 3)),
        description="What shows of this 3D handle where anything is in front of it - inside the item, or on its "
                    "far side")
    handle_use_color: bpy.props.BoolProperty(
        name="Own Color", update=_redraw,
        description="Draw this 3D handle in a color of its own, not its list's")
    handle_color: bpy.props.FloatVectorProperty(
        name="Handle Color", subtype="COLOR", size=3, min=0.0, max=1.0, default=(1.0, 0.3, 0.3), update=_redraw,
        description="This 3D handle's color: its edge, and its fill under the mouse")
    # or Blender's own axis colors (Greg: "I like the idea of adopting from
    # Blenders theme"): the navigation gizmo's, and an artist's own if their
    # theme sets them - for red-green color blindness, say
    handle_color_from: bpy.props.EnumProperty(
        name="Color From", default="OWN", update=_redraw,
        items=(("OWN", "Own", "The color set here", 0),
               ("AXIS_X", "Theme X", "The theme's X axis color (Preferences > Themes > User Interface), as "
                "Blender's navigation gizmo shows it", 1),
               ("AXIS_Y", "Theme Y", "The theme's Y axis color (Preferences > Themes > User Interface), as "
                "Blender's navigation gizmo shows it", 2),
               ("AXIS_Z", "Theme Z", "The theme's Z axis color (Preferences > Themes > User Interface), as "
                "Blender's navigation gizmo shows it", 3)),
        description="Where this 3D handle's own color comes from: the one set here, or an axis color of "
                    "Blender's theme - so the handles match the navigation gizmo, and follow a theme an artist "
                    "has made easier to see")
    # its interior (Greg: "And need interior color for the handles"). Before
    # this it was always dark, whatever its edge
    handle_use_fill: bpy.props.BoolProperty(
        name="Interior", update=_redraw,
        description="Fill this 3D handle with a color of its own, not dark")
    handle_fill: bpy.props.FloatVectorProperty(
        name="Interior Color", subtype="COLOR", size=3, min=0.0, max=1.0, default=(0.35, 0.35, 0.38),
        update=_redraw, description="This 3D handle's interior: brighter under the mouse")
    # how much of its interior shows (Greg: "Could there be an option for the
    # interior to be transparent?"). At 0, only its edges show
    handle_fill_alpha: bpy.props.FloatProperty(
        name="Interior Opacity", subtype="FACTOR", default=1.0, min=0.0, max=1.0, update=_redraw,
        description="How much of this 3D handle's interior shows - its own color, or the dark one: at 0 it is "
                    "transparent, its edges alone drawn")
    # its color under the mouse (Greg: "I'd like to be able to change the
    # hover color for handles"): filled with it and edged a lighter shade.
    # Without it, the handle is drawn brighter and white-edged
    handle_use_hover: bpy.props.BoolProperty(
        name="Hover Color", update=_redraw,
        description="Under the mouse, draw this 3D handle in a color of its own - filled with it, its edge a "
                    "lighter shade - not brighter and white-edged")
    handle_hover: bpy.props.FloatVectorProperty(
        name="Hover Color", subtype="COLOR", size=3, min=0.0, max=1.0, default=(1.0, 0.8, 0.2), update=_redraw,
        description="This 3D handle's color under the mouse")
    show_when: bpy.props.EnumProperty(
        name="Show When", items=WHEN, default="ALWAYS", update=_redraw,
        description="Show the button always, or only while a switch is on or off - a toggle of this region, "
                    "or any property")
    when_toggle: bpy.props.StringProperty(
        name="Toggle", update=searched("Show When Toggle", _redraw),
        description="The toggle of this region whose state shows the button")
    when_target: bpy.props.PointerProperty(
        name="Target", type=bpy.types.Object, update=_redraw,
        description="Whose property it reads (empty: the object hovered)")
    when_path: bpy.props.StringProperty(
        name="Path", update=_redraw,
        description="A property, as right-click > Copy Data Path gives it, on at a half or more")
    opens_menu: bpy.props.BoolProperty(
        name="Opens Menu", update=_opens_changed,
        description="A click shows the buttons in this one's menu, in a ring around it, and hides the rest; "
                    "click it again, press Esc or move off the region to close it. A drag still runs its own "
                    "commands")
    # A menu that stays open once clicked, for a menu of 3D handles, which
    # the mouse reaches across other items. Its region keeps the hover until
    # a click in empty space, Esc, or its button again. Greg, of Digit's
    # handles: "Clicking in space should drop the handles ... the hover it
    # came from should stay active and not switch"
    menu_stays: bpy.props.BoolProperty(
        name="Stays Open", update=_redraw,
        description="A click opens the menu and keeps it open - its region keeps the hover wherever the mouse "
                    "goes - until a click in empty space, Esc, or a click on this button")
    menu_use_color: bpy.props.BoolProperty(
        name="Override Color",
        update=_list_color_on("menu_use_color", "menu_color", "menu_color_set", _opener_color),
        description="Draw the buttons in this one's menu in a color of their own, not this button's")
    menu_color: bpy.props.FloatVectorProperty(
        name="Menu Color", subtype="COLOR", size=3, min=0.0, max=1.0, default=(1.0, 1.0, 1.0), update=_redraw,
        description="The color of the buttons in this one's menu: their outlines, arrows and names' borders")
    menu_color_set: bpy.props.BoolProperty(options={"HIDDEN"})
    uid: bpy.props.IntProperty(options={"HIDDEN"}, description="The button's id in its region")
    menu_parent: bpy.props.IntProperty(
        options={"HIDDEN"}, description="The id of the button whose menu this one is in (0: the region's own)")
    menu_index: bpy.props.IntProperty(
        default=-1, options={"HIDDEN"}, description="The button selected in this one's menu, in the panel")
    menu_open: bpy.props.BoolProperty(default=True, options={"HIDDEN"})
    # whether the panel's tree shows the buttons in its menu (tree.py), folded to start
    tree_open: bpy.props.BoolProperty(default=False, options={"HIDDEN"})
    # a toggle that keeps the pose as it switches: (bone, partner) pairs as
    # Python lists, read with ast.literal_eval
    snap_on: bpy.props.StringProperty(
        name="Snap On", description="Switching on, each bone takes its partner's pose: a Python list of "
        "(bone, partner) pairs - for an IK switch, the IK bones and the FK bones they take over from")
    snap_off: bpy.props.StringProperty(
        name="Snap Off", description="Switching off, each bone takes its partner's pose: (bone, partner) pairs")
    snap_keep: bpy.props.StringProperty(
        name="Keep", description="Bones that stay where they are as the switch flips: a Python list of names "
        "(a parent switch)")
    snap_pole: bpy.props.StringProperty(
        name="Pole", description="Switching on, an IK pole set where the limb's middle joint points: a Python "
        "list - the pole, then the FK chain's first, middle and last bones, and the IK chain's first, which "
        "the pole is turned until it lies as the FK chain's first does")
    run_operator: bpy.props.StringProperty(
        name="Operator", description="An operator a click runs, by its Python name (pose.cloudrig_snap_bake); "
        "for a toggle, in place of switching")
    run_operator_args: bpy.props.StringProperty(
        name="Arguments", description="The operator's arguments, as a Python dictionary")
    # Its tip (tips.py). Greg: "Default generated messages that are all about
    # the interactions that have been built in. Followed by a blurb that the
    # author writes themselves". So: a row per key, each worded by Kneady
    # unless the author words it, then the author's own message
    tip_rows: bpy.props.CollectionProperty(type=KNEADY_PG_tip_row)
    tip_text: bpy.props.StringProperty(
        name="Message", update=_redraw,
        description="What this button is for, in a sentence or two, under the rows of keys in its tip")
    tip_open: bpy.props.BoolProperty(default=False, options={"HIDDEN"})


def _faces_changed(region, _context):
    """Which faces belong to a region changed (From Attribute, Value or
    Whole Object), so forget what Kneady worked out from the old faces: its
    hover, its paint, where its row of buttons sits. A geometry edit is
    followed by the depsgraph, but these are settings of the region, and
    nothing else would report the change."""
    from . import core
    owner = region.id_data
    core.forget(owner.name if isinstance(owner, bpy.types.Object) else None)


class KNEADY_PG_region(bpy.types.PropertyGroup):
    """A region: faces of the object (or all of it) that drive something."""
    name: bpy.props.StringProperty(name="Name", default="Region")
    id: bpy.props.IntProperty(name="Id", description="Its faces' tag; unique on the object")
    whole: bpy.props.BoolProperty(name="Whole Object", description="The whole object is the region, not "
                                  "tagged faces", update=_faces_changed)
    # Faces a face attribute marks, for a mesh Geometry Nodes makes, whose
    # faces cannot be assigned by hand (Digit's caps: digit_cap 1 and 2)
    attribute: bpy.props.StringProperty(
        name="From Attribute", description="A face attribute (integer or boolean) marking the region's faces "
        "where it holds Value - for a mesh Geometry Nodes makes. Empty: the faces assigned in Edit Mode",
        update=_faces_changed)
    value: bpy.props.IntProperty(name="Value", default=1, description="The attribute's value on the region's faces",
                                 update=_faces_changed)
    # Reached and drawn through whatever covers it, once its object is
    # hovered (Greg: a digit's caps, hidden in the next digit or the palm -
    # "user hovers over body of digit, then they can hover over either start
    # or end and see it drawn on top")
    show_through: bpy.props.BoolProperty(
        name="Show Through", description="Once its object is hovered, this region can be hovered and is drawn "
        "through whatever covers it, until the mouse moves onto something else")
    color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                         default=(1.0, 0.52, 0.12))
    opacity: bpy.props.FloatProperty(name="Opacity", subtype="FACTOR", min=0.0, max=1.0, default=0.55,
                                     description="How solid the overlay is under the mouse; the object's "
                                     "other regions show at less")
    # How many of `buttons` are in use - the panel adds and removes them with
    # + and - (core.add_button); a program may set it
    button_count: bpy.props.IntProperty(name="Buttons", min=1, max=MAX_BUTTONS, soft_max=ROW_BUTTONS, default=1,
                                        update=lambda self, _context: _fill_buttons(self),
                                        description="Sets of commands, as circles in the middle of the region "
                                        "when it is hovered: drag on one to run its commands, or click a "
                                        "toggle. The rest of the region runs the first that drags")
    button_index: bpy.props.IntProperty(name="Selected Button", min=0,
                                        description="The button selected in the panel's list, its settings "
                                        "under it")
    arrange: bpy.props.EnumProperty(
        name="Arrange", default="ROW",
        items=(("ROW", "Row", "The buttons side by side, left to right"),
               ("COLUMN", "Column", "The buttons one above another, top to bottom"),
               ("GRID", "Row + Column", "Two columns from four buttons, in rows of two, an odd one centered "
                "above them: five is the fifth over two rows, eight is four rows. Three or fewer stay in a "
                "row"),
               ("CIRCLE", "Circle", "The buttons around a ring, the first at the top, the rest clockwise")),
        description="How the buttons line up in the middle of the region")
    buttons: bpy.props.CollectionProperty(type=KNEADY_PG_button)
    behind: bpy.props.EnumProperty(
        name="Behind", items=BEHIND, default="HIDE", update=_redraw,
        description="What shows of a placed button whose side of the item faces away from the view: one "
                    "setting for all of the region's placed buttons, in its menus too")
    # its buttons' colors, a list at a time (core.button_colors)
    use_button_color: bpy.props.BoolProperty(
        name="Override Color",
        update=_list_color_on("use_button_color", "button_color", "button_color_set", lambda r: tuple(r.color)),
        description="Draw the region's buttons - in its row and placed on the surface - in a color of their own, not "
                    "the region's")
    button_color: bpy.props.FloatVectorProperty(
        name="Button Color", subtype="COLOR", size=3, min=0.0, max=1.0, default=(1.0, 1.0, 1.0), update=_redraw,
        description="The color of the region's buttons: their outlines, arrows and names' borders")
    button_color_set: bpy.props.BoolProperty(options={"HIDDEN"})
    # whether the panel's tree shows its buttons (tree.py), folded to start
    tree_open: bpy.props.BoolProperty(default=False, options={"HIDDEN"})
    # The Kneady data version it was made at or last updated to
    # (core.DATA_VERSION), or 0 if it was made before versions began
    version: bpy.props.IntProperty(options={"HIDDEN"},
                                   description="The Kneady data version this region was made at or updated to")


class KNEADY_PG_object(bpy.types.PropertyGroup):
    regions: bpy.props.CollectionProperty(type=KNEADY_PG_region)
    index: bpy.props.IntProperty(name="Active Region")
    # Edit Faces: the vertex group whose faces Select Faces picks
    faces_group: bpy.props.StringProperty(
        name="Vertex Group", update=searched("Vertex Group"),
        description="Select the faces mostly weighted to this vertex group, to Assign them to the region")


_classes = (KNEADY_PG_command, KNEADY_PG_drag, KNEADY_PG_tip_row, KNEADY_PG_button, KNEADY_PG_region,
            KNEADY_PG_object)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.kneady = bpy.props.PointerProperty(type=KNEADY_PG_object)


def unregister():
    if hasattr(bpy.types.Object, "kneady"):
        del bpy.types.Object.kneady
    for cls in reversed(_classes):
        reg.unregister_class(cls)
