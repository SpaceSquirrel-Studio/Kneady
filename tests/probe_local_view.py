"""In Local View (Numpad /), objects outside it are hidden, and Kneady must
not meet them: a window probe.

    blender --factory-startup --enable-event-simulate --window-geometry 120 160 1400 860 \\
        --python tests/probe_local_view.py

A Character with a region; in front of it a Wall with none, and beside it a
Ghost with a region of its own. Local View on the Character alone. Hovering
the Character finds it (the hidden Wall not in the way), and hovering where
the hidden Ghost stands finds nothing: before core.ray, the Ghost took the
hover there, painted in empty space with its button floating, and a drag
would have moved what nobody could see. Blender's scene ray cast knows
nothing of Local View, so only a real 3D view shows this. Prints PASS or
FAIL lines and quits."""

import importlib
import os
import sys

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)
importlib.import_module(os.path.basename(REPO)).register()
import rigs  # noqa: E402
import window as w  # noqa: E402


def cube(name, location, size=1.0):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def steps():
    core = rigs.kneady()
    bpy.context.preferences.view.show_tooltips = False    # clean screenshots; this session only
    win, area, view, _rv3d = w.view()
    yield from w.click(win, 120, 600)                     # the splash away
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    character = cube("Character", (0.0, 0.0, 0.0), 2.0)
    core.new_region(character, "Body", whole=True)
    cube("Wall", (0.0, -3.0, 0.0), 1.0)                   # between the front view and the Character
    ghost = cube("Ghost", (3.0, 0.0, 0.0), 1.0)
    core.new_region(ghost, "Ghost", whole=True)
    for o in bpy.data.objects:
        o.select_set(o is character)
    bpy.context.view_layer.objects.active = character
    with bpy.context.temp_override(window=win, area=area, region=view):
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.localview()
    yield 0.5
    rv3d = area.spaces.active.region_3d
    rv3d.view_location = (1.5, 0.0, 0.0)                  # the Ghost's place in sight too
    rv3d.view_distance = 12.0
    bpy.context.scene.kneady_on = True
    yield 0.5
    space = area.spaces.active
    w.check("in_local_view", space.local_view is not None)
    # asked of the evaluated objects: Blender 4.2 and 4.5 answer "not in this
    # view" for every original object (core.shown_in)
    dg = bpy.context.evaluated_depsgraph_get()
    seen = {o.name: o.evaluated_get(dg).visible_in_viewport_get(space) for o in bpy.data.objects}
    w.check("only_the_character_shown_here", seen == {"Character": True, "Wall": False, "Ghost": False}, str(seen))
    yield from w.hover_point(win, Vector((0.0, -1.0, 0.0)))
    hover = core.STATE["hover"]
    w.check("character_hovered_past_the_hidden_wall", bool(hover) and hover[0] == "Character", str(hover))
    w.shot("local_view_character")
    yield from w.hover_point(win, Vector((3.0, -0.5, 0.0)))
    hover = core.STATE["hover"]
    w.check("hidden_ghost_not_hovered", not hover or hover[0] != "Ghost", str(hover))
    w.shot("local_view_ghost")


w.run(steps, "local_view")
