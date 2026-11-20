"""Kneady makes what it plays. extensions.blender.org's moderators: "Code of
the extension you submit should 100% be features that our platforms user will
get out of the box". So with Kneady alone (no other add-on), a button can be
placed on the item, made a 3D handle and given a menu, and its Show When,
Keep Pose and Run Operator settings are in the panel. Kneady is also one
plain add-on: it knows of no other copy, and stops cleanly even where another
add-on has registered a class of the same name over one of its own."""

import sys

import bpy  # type: ignore

import rigs


def _package():
    return sys.modules[rigs.kneady().__name__.rsplit(".", 1)[0]]


def test_makes_what_it_plays():
    ui, placement = rigs.module("ui"), rigs.module("placement")
    menu_build, snap_ui, pick = rigs.module("menu_build"), rigs.module("snap_ui"), rigs.module("pick")
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    region.button_count = 3
    on_item, handle = region.buttons[1], region.buttons[2]
    with bpy.context.temp_override(kneady_region=region, kneady_button=on_item):
        assert bpy.ops.kneady.button_placement(look="ITEM") == {"FINISHED"}
    assert on_item.placed and on_item.place_set and on_item.handle == "BUTTON", "not placed on the item"
    with bpy.context.temp_override(kneady_region=region, kneady_button=handle):
        assert bpy.ops.kneady.button_placement(look="HANDLE") == {"FINISHED"}
    assert handle.placed and handle.handle == "HANDLE", "not made a 3D handle"
    first = region.buttons[0]
    with bpy.context.temp_override(kneady_region=region, kneady_button=first):
        assert bpy.ops.kneady.add_to_menu() == {"FINISHED"}
    # look it up again: adding to a collection can move its items, and a
    # Python reference from before then reads freed memory (this failed in 4.5)
    first = region.buttons[0]
    assert first.opens_menu, "Add to Its Menu did not give the button a menu"
    assert any(b.menu_parent == first.uid for b in region.buttons), "nothing went into the menu"
    # the settings that make the rest, in the panel
    assert placement.draw_button in ui.BUTTON_LOOKS, "no In Row / On Item / 3D Handle choice"
    assert menu_build.draw_button in ui.BUTTON_EXTRAS, "no Show When settings"
    assert snap_ui.draw_button in ui.BUTTON_EXTRAS, "no Keep Pose / Run Operator settings"
    assert any(icon["key"] == placement.ICON_KEY for icon in pick.CORNER_ICONS), "no Place on Surface icon"
    assert hasattr(bpy.types, "KNEADY_OT_place_mode"), "no Place on Surface"


def test_no_two_operators_share_a_name():
    """Blender lets a second class registered under an operator's name
    replace the first without a word. Kneady Pro's Record once took Record
    What You Do's name, and Record What You Do stopped working. So every
    Kneady class with a bl_idname must have a name of its own."""
    prefix = _package().__name__ + "."
    seen = {}
    for name, module in list(sys.modules.items()):
        if not name.startswith(prefix) or module is None:
            continue
        for value in vars(module).values():
            idname = getattr(value, "bl_idname", None) if isinstance(value, type) else None
            if not isinstance(idname, str) or getattr(value, "__module__", None) != name:
                continue
            other = seen.setdefault(idname, value)
            assert other is value, "%s and %s are both %s" % (other.__qualname__, value.__qualname__, idname)
    assert "kneady.tutorial_start" in seen and "kneady.tutorial_new" in seen, sorted(seen)[:5]


def test_one_plain_add_on():
    package = _package()
    for name in ("RANK", "EDITION", "CARRIED", "active_edition"):
        assert not hasattr(package, name), "Kneady still has %s, for other copies" % name
    assert "_kneady_copies" not in sys.modules, "a registry of copies in sys.modules"


def test_stops_past_a_replaced_class():
    """Another add-on registering an operator of the same name replaces
    Kneady's (Blender unregisters the first without a word). Kneady still
    stops cleanly, leaving nothing behind, and starts again."""
    package = _package()

    class Other(bpy.types.Operator):
        bl_idname = "kneady.add_to_menu"
        bl_label = "Another add-on's"

        def execute(self, context):
            return {"FINISHED"}

    def handlers():
        return [h for h in bpy.app.handlers.depsgraph_update_post if h.__name__ == "_on_depsgraph"
                and "kneady" in (h.__module__ or "").lower()]

    bpy.utils.register_class(Other)
    try:
        package.unregister()
        assert not hasattr(bpy.types.Scene, "kneady_on"), "Kneady's settings stayed"
        assert not handlers(), "Kneady's depsgraph handler stayed"
        assert not hasattr(bpy.types, "KNEADY_OT_drag"), "Kneady's drag stayed"
    finally:
        bpy.utils.unregister_class(Other)
        package.register()
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=40.0) == {"FINISHED"}
    assert rigs.angle_of(rig.pose.bones["Lower"]) > 1.0, "Kneady does not drag after starting again"
    assert hasattr(bpy.types, "KNEADY_OT_add_to_menu"), "Kneady's own Add to Its Menu did not come back"
