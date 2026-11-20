"""Kneady: pose and shape anything by its own surface.

You hover over part of a model and drag it, and the drag poses or reshapes
whatever that part controls. Kneady is modeled on Modo's Rig Clay. Greg
wanted it because "This kit needs a slick method of interaction", and saw
that "Rig Clay could be useful for all sorts of people and projects". So
Kneady is self-contained: it uses only Blender's API and never imports
Digit. It ships as an extension of its own, and inside Kneady Pro and Digit.

The pieces:

- **Regions** are faces of a mesh (marked by a face attribute, core.TAG) or
  a whole object. Each object lists its own (`Object.kneady`, in props.py),
  with + and - buttons the way Blender's own lists have them. With Kneady on
  (`Scene.kneady_on`, a switch in the viewport header), hovering an object
  paints its regions. The one under the mouse brightens and shows its
  buttons. Dragging it drives what it controls, and the paint is hidden
  while the drag lasts.
- **Buttons** are sets of commands on a region. They show as a row of
  circles in the region's middle, or are placed on the item itself, drawn
  as 3D handles, or held in menus. Each carries its own graphic and works
  like a visual modifier key: drag from a circle to run its commands. A
  drag anywhere else on the region runs the first button.
- **Commands** are what a drag does. Each drag direction drives up to
  sixteen of them, each one of:
  - Rotate, Move or Scale of an object or bone about its own axis,
    following the mouse
  - a Geometry Nodes modifier input
  - any property, named by its data path the way a driver names one
- **Providers** let another program add regions that an object does not
  carry itself (core.add_provider). Digit uses one to give its digits
  shared regions.

**Kneady is one plain add-on.** It registers itself and knows of no other
copy of itself. The extensions.blender.org moderators set the rule: "Code of
the extension you submit should 100% be features that our platforms user
will get out of the box". So everything Kneady plays, it can also make:
buttons placed on the item, 3D handles, menus, Show When, Keep Pose and Run
Operator (placement.py, menu_build.py and snap_ui.py, once part of Kneady
Pro). An add-on that carries a copy of Kneady inside it is the one
responsible for keeping two copies from running at once.
"""

import bpy  # type: ignore

# Every module is imported here, even those this file never names (arrange),
# so the whole add-on is loaded together: the modules that use arrange import
# it only when they need it, and the tests and other add-ons find Kneady's
# modules among those already loaded. The noqa marker tells linters so.
from . import (arrange, core, draw, hints, media, menu_build, menus, ops, overlay, pick, placed,  # noqa: F401
               placement, props, snap_ui, switching, tips, tree, tutorial_edit, tutorials, ui)

# _PLAYERS play the layouts a file carries: buttons placed on the item,
# menus, Show When, a toggle keeping the pose. _MAKERS make them: placing
# buttons and 3D handles, building menus and Show When, setting a toggle's
# Keep Pose or Run Operator, and making tutorials.
_PLAYERS = (placed, menus, switching, pick, hints, tips, media, tutorials, overlay)
_MAKERS = (placement, menu_build, snap_ui, tutorial_edit)


def _forget(name=None):
    core.forget(name)
    draw.forget(name)


def _toggled(self, context):
    core.reset_state(context)
    _forget()
    if self.kneady_on:
        for fn in core.ON_ENABLE:
            fn(self)
    core.redraw()


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    # Anything evaluated again: layouts and anchors are worked out afresh
    core.changed()
    if not getattr(scene, "kneady_on", False):
        return
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object) and update.is_updated_geometry:
            _forget(update.id.original.name)
    core._HIT["key"] = None


@bpy.app.handlers.persistent
def _on_frame(scene, *_args):
    """The frame changed: playing, scrubbing, or a frame typed in. An
    animated region's shape moves with its rig, but a frame change sends no
    depsgraph update for the meshes it moves. Without this, the highlight,
    the row of buttons and Show Through's hit test would stay on the
    previous frame."""
    core.changed()
    if getattr(scene, "kneady_on", False):
        _forget()


@bpy.app.handlers.persistent
def _on_reload(*_args):
    """After a file loads. The caches are cleared because they are keyed by
    object name, and another file can reuse a name for other geometry."""
    core.reset_state()
    _forget()


@bpy.app.handlers.persistent
def _on_undo(*_args):
    """After an undo or redo. The caches are cleared, as when a file is loaded,
    because another undo step can reuse an object's name for different
    geometry. A pinned or kept region stays that way while it still exists:
    Greg found an undo dropped his pin along with the drag - "if I pin a button
    then haul then undo, the haul and the pin are undone ... people will undo
    frequently"."""
    core.reset_state(keep=True)
    _forget()


@bpy.app.handlers.persistent
def _on_load(*_args):
    """When a file opens. Its regions are brought up to this Kneady's data
    version (core.migrate_file). If a newer Kneady made some of them, the
    person is told (core.newer_note), and those regions are left exactly as
    they are, so a file saved by a beta opens safely in this release."""
    core.migrate_file()
    note = core.newer_note()
    if note:
        print("Kneady: " + note)
        if not bpy.app.background:
            bpy.app.timers.register(_tell_newer, first_interval=0.5)


def _tell_newer():
    """Show the note about a newer Kneady's regions in a popup over the
    first window. This runs from a timer because a load handler runs before
    the window is ready to show anything."""
    note = core.LOAD_NOTE[0]
    wm = bpy.context.window_manager
    if not note or wm is None or not wm.windows:
        return None
    import textwrap

    def draw(menu, _context):
        for line in textwrap.wrap(note, 70):
            menu.layout.label(text=line)

    with bpy.context.temp_override(window=wm.windows[0]):
        wm.popup_menu(draw, title="Made with a newer Kneady", icon="ERROR")
    return None


_RELOADS = (("load_post", _on_reload), ("undo_post", _on_undo), ("redo_post", _on_undo))

_ACTIVE = False                    # True between register() and unregister()


def register():
    global _ACTIVE
    _ACTIVE = True
    props.register()
    ops.register()
    tree.register()
    ui.register()
    draw.register()
    for module in _PLAYERS + _MAKERS:
        module.register()
    bpy.types.Scene.kneady_on = bpy.props.BoolProperty(
        name="Kneady",
        description=("Pose and shape by the surface: hover an object to see its regions, drag one to drive "
                     "what it controls. A click still selects"),
        default=False, update=_toggled)
    # A slider, under a new property name: Button Size was once a choice of
    # four sizes, and a file's stored choice would read as a number here
    bpy.types.Scene.kneady_button_radius = bpy.props.FloatProperty(
        name="Button Size", subtype="PIXEL", default=core.BUTTON_RADIUS,
        min=core.BUTTON_RADIUS_MIN, max=core.BUTTON_RADIUS_MAX, precision=0,
        description="How big every region's buttons are, from small to large: their radius in pixels at "
                    "Blender's normal interface size (they grow with its Resolution Scale)",
        update=lambda _self, _context: core.redraw())
    # The 3D handles' own size. Greg: "We also need to be able to change the
    # size of the handles separately from the standard buttons"
    bpy.types.Scene.kneady_handle_radius = bpy.props.FloatProperty(
        name="Handle Size", subtype="PIXEL", default=core.BUTTON_RADIUS,
        min=core.HANDLE_RADIUS_MIN, max=core.HANDLE_RADIUS_MAX, precision=0,
        description="How big every 3D handle is, apart from the buttons: an arrow's thickness and length, a "
                    "ring's radius, at Blender's normal interface size. Each handle can be larger or smaller "
                    "again by its own Size",
        update=lambda _self, _context: core.redraw())
    # A thin dark edge round the handles' lines. Greg: "Contrast against
    # wireframe is a good idea"
    bpy.types.Scene.kneady_handle_halo = bpy.props.BoolProperty(
        name="Halo", default=False,
        description="A thin dark edge round every 3D handle's lines, so they read over a light surface or a "
                    "wireframe",
        update=lambda _self, _context: core.redraw())
    bpy.types.Scene.kneady_labels = bpy.props.EnumProperty(
        name="Labels", default="HOVER",
        items=(("OFF", "Off", "No names under the buttons"),
               ("HOVER", "On Hover", "The name of the button under the mouse, under it"),
               ("ALWAYS", "Always", "Every button's name under it, the buttons spaced to make room")),
        description="Button names under their circles",
        update=lambda _self, _context: core.redraw())
    # Whether a button's tip shows is set by Help (tips.py). Help belongs to
    # the person, not the file, so it lives on the window manager. A file's
    # own Tips switch, which existed for a day, is left unread.
    # Highlight: Fill or Outline. Greg asked for the outline as an option: "a
    # hover-over outline instead of a hover over full overlay. I still want
    # the overlay this is just an alternate visualization option"
    bpy.types.Scene.kneady_highlight = bpy.props.EnumProperty(
        name="Highlight", default="FILL",
        items=(("FILL", "Fill", "The hovered object's regions painted over it in their colors"),
               ("OUTLINE", "Outline", "The hovered object's regions outlined in their colors: each one's "
                                      "border and its edge against the view")),
        description="How the hovered object's regions are shown: painted over, or outlined",
        update=lambda _self, _context: core.redraw())
    bpy.types.Scene.kneady_outline_width = bpy.props.FloatProperty(
        name="Outline Width", subtype="PIXEL", default=6.0, min=2.0, max=16.0, precision=1,
        description="How thick the outlines are, in pixels at Blender's normal interface size",
        update=lambda _self, _context: core.redraw())
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    for name, fn in _RELOADS:
        handlers = getattr(bpy.app.handlers, name)
        if fn not in handlers:
            handlers.append(fn)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    if _on_frame not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_on_frame)


def unregister():
    global _ACTIVE
    if not _ACTIVE:
        return
    _ACTIVE = False
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _on_frame in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_on_frame)
    for name, fn in _RELOADS:
        handlers = getattr(bpy.app.handlers, name)
        if fn in handlers:
            handlers.remove(fn)
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for name in ("kneady_on", "kneady_button_radius", "kneady_handle_radius", "kneady_handle_halo",
                 "kneady_labels", "kneady_highlight", "kneady_outline_width"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for module in reversed(_PLAYERS + _MAKERS):
        module.unregister()
    draw.unregister()
    ui.unregister()
    tree.unregister()
    ops.unregister()
    props.unregister()
