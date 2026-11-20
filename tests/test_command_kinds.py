"""A program's own kind of command, a drag button's click, and a program's
handles holding the hover. Greg, of Digit's handles: "it would be ideal for it
to show up as a command option like 'rotate X' is or how a modifier is
driven", "I might have the sides handles appear when I click on the Bend X /
Bend Y instead of hauling", and "when the handles are present they need to be
treated as part of the menu"."""

from types import SimpleNamespace

import bpy  # type: ignore

import rigs

KEY = "test_lamp"


def _region(mesh, count=3):
    core = rigs.kneady()
    region = core.new_region(mesh, "R", whole=True)
    region.button_count = count
    return region


def _lamp(core, lit):
    """A kind of command that switches a lamp per object. `lit` holds the
    names of the objects switched on. It runs only on meshes."""
    core.add_command_kind(
        KEY, "Lamp",
        read=lambda obj, command: obj.name in lit,
        write=lambda context, obj, command, on: lit.add(obj.name) if on else lit.discard(obj.name),
        why=lambda obj, command: "" if obj.type == "MESH" else "A lamp is a mesh's",
        summary=lambda command: "Lamp %s" % (command.program_data or "white"),
        icon="LIGHT")


def test_a_program_adds_a_kind_of_command():
    """A toggle switching a program's kind of command. It goes on and off as
    the program reads and writes it, and is lit from it. Its settings are the
    program's text, and its reason for not running is the program's own. A
    command whose program is not running says so."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    lit = set()
    _lamp(core, lit)
    try:
        assert [k["key"] for k in core.command_kinds()][-1] == KEY
        toggle = region.buttons[0]
        toggle.action = "TOGGLE"
        toggle.switch.program, toggle.switch.program_data = KEY, "red"
        channels = core.switch_channels(toggle, mesh, region)
        assert channels[0].ok and channels[0].kind == "PROGRAM" and core.switch_state(channels) is False
        assert core.switch_click(bpy.context, toggle, mesh, region) and mesh.name in lit
        assert core.switch_state(core.switch_channels(toggle, mesh, region)) is True
        assert not core.switch_click(bpy.context, toggle, mesh, region, on=True), "switched what was on already"
        assert core.switch_click(bpy.context, toggle, mesh, region, on=False) and mesh.name not in lit
        assert "Lamp red" in channels[0].label()
        # its own reason, on what it cannot run on
        toggle.switch.dragged = False
        toggle.switch.target = rig
        ch = core.switch_channels(toggle, mesh, region)[0]
        assert not ch.ok and ch.why == "A lamp is a mesh's"
        # Show When reads it the program's way
        toggle.switch.target = None
        toggle.switch.dragged = True
        menus = rigs.module("menus")
        lit.add(mesh.name)
        assert menus._read_switch(toggle.switch, mesh) is True
    finally:
        core.remove_command_kind(KEY)
    ch = core.switch_channels(toggle, mesh, region)[0]
    assert not ch.ok and KEY in ch.why, "a missing program's command looked runnable"


def test_a_drag_button_clicks():
    """A drag button with Click Switches: a click switches what it names and
    lights the button, leaving its drags unchanged. The setting is copied
    with its commands."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    rig["flag"] = 0.0
    button, other = region.buttons[0], region.buttons[1]
    button.up.enabled = True
    assert not core.has_click(button)
    button.click_on = True
    assert core.has_click(button) and button.switch.kind == "PROPERTY", "Click did not start as a property"
    button.switch.target, button.switch.data_path = rig, '["flag"]'
    button.switch.dragged = False
    assert core.switch_click(bpy.context, button, mesh, region) and rig["flag"] == 1.0
    assert core.switch_state(core.switch_channels(button, mesh, region)) is True
    assert button.switch in core.button_commands(button) and button.up in core.button_commands(button)
    assert "click_on" in core.COMMAND_DATA
    data = core.to_data(button)
    core.from_data(other, {k: data[k] for k in core.COMMAND_DATA if k in data})
    assert other.click_on and other.switch.data_path == '["flag"]'


def test_a_menu_buttons_click_follows_its_menu():
    """On a drag button that opens a menu, its click switches on as the menu
    opens and off as it closes, whether by its button or by Esc for the whole
    menu. A Shift+click on a plain button pins the region and switches
    nothing."""
    core = rigs.kneady()
    ops, menus = rigs.module("ops"), rigs.module("menus")
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    lit = set()
    _lamp(core, lit)
    try:
        opener, plain = region.buttons[0], region.buttons[1]
        for b in (opener, plain):
            b.up.enabled = True
            b.click_on = True
            b.switch.program = KEY
        opener.opens_menu = True
        menus.ensure_uid(region, opener)
        state = {"open": False}
        stub = SimpleNamespace(_button=opener, _obj=mesh, _region=region, _index=0, point_set=False,
                               point=(0.0, 0.0, 0.0), report=lambda *_a: None,
                               _menu_open=lambda: state["open"])
        click = ops.KNEADY_OT_drag._click_switch
        state["open"] = True                              # the click opened its menu
        assert click(stub, bpy.context, False, False) and mesh.name in lit
        assert not click(stub, bpy.context, True, False), "a click leaving the menu open switched"
        state["open"] = False                             # its button closed it
        assert click(stub, bpy.context, True, False) and mesh.name not in lit
        # Esc: the clicks along the open menu's path switch off
        state["open"] = True
        click(stub, bpy.context, False, False)
        key = menus.key_of(mesh, region)
        menus.OPEN[key] = [(opener.uid, ("middle", None))]
        try:
            menus.switch_off_path(bpy.context, mesh, region)
        finally:
            menus.OPEN.pop(key, None)
        assert mesh.name not in lit, "Esc left the menu's click on"
        # a plain one: each click switches it the other way, a Shift+click not
        stub._button, stub._index = plain, 1
        assert not click(stub, bpy.context, False, True) and mesh.name not in lit
        assert click(stub, bpy.context, False, False) and mesh.name in lit
        assert click(stub, bpy.context, False, False) and mesh.name not in lit
    finally:
        core.remove_command_kind(KEY)


def test_a_hold_hook_names_the_object_under_its_handles():
    """A program's hold hook names the object whose handles are under the
    mouse; one that fails does not stop the hover."""
    core = rigs.kneady()

    def broken(_context, _at):
        raise RuntimeError("no view")

    def handles(_context, at):
        return "Arm" if at[0] < 10 else None

    core.add_hold_hook(broken)
    core.add_hold_hook(handles)
    try:
        assert core.held_by_handles(bpy.context, (5, 5)) == "Arm"
        assert core.held_by_handles(bpy.context, (50, 5)) is None
    finally:
        core.remove_hold_hook(broken)
        core.remove_hold_hook(handles)
    assert core.held_by_handles(bpy.context, (5, 5)) is None


def test_a_busy_hook_hides_kneady():
    """A program's drag (add_busy_hook): while the hook says so, Kneady is
    busy. It draws nothing and takes no press, as during a drag of its own. A
    hook that fails does not count. core.hauling() is true only for Kneady's
    own drags."""
    core = rigs.kneady()
    going = [False]

    def broken(_context):
        raise RuntimeError("no window")

    def handles(_context):
        return going[0]

    core.add_busy_hook(broken)
    core.add_busy_hook(handles)
    try:
        assert not core.busy(bpy.context)
        going[0] = True
        assert core.busy(bpy.context) and not core.hauling()
        going[0] = False
        core.STATE["dragging"] = True
        assert core.busy(bpy.context) and core.hauling()
    finally:
        core.STATE["dragging"] = False
        core.remove_busy_hook(broken)
        core.remove_busy_hook(handles)
    going[0] = True
    assert not core.busy(bpy.context)


def test_letting_go_calls_the_keepers_release():
    """keep's release is called once when the hover is let go (by Esc too).
    It is kept through an undo and dropped by a file load. A Shift+click pin
    on a region a program keeps makes the pin the artist's, and the release
    is dropped."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    released = []

    def release(_context):
        released.append(core.kept())

    core.keep(bpy.context, mesh.name, region.id, note="handles", by="handles", release=release)
    assert core.kept_by() == "handles"
    core.let_go(bpy.context)
    assert released == [None] and core.kept() is None, released
    core.let_go(bpy.context)
    assert released == [None]
    # an undo keeps it, a file load drops it
    core.keep(bpy.context, mesh.name, region.id, by="handles", release=release)
    core.reset_state(bpy.context, keep=True)
    assert core.kept() == (mesh.name, region.id)
    core.let_go(bpy.context)
    assert len(released) == 2
    core.keep(bpy.context, mesh.name, region.id, by="handles", release=release)
    core.reset_state(bpy.context)
    core.let_go(bpy.context)
    assert len(released) == 2 and core.kept() is None
    # a Shift+click pin takes it over: the program's release dropped
    core.keep(bpy.context, mesh.name, region.id, by="handles", release=release)
    core.toggle_kept(bpy.context, mesh, region)
    assert core.kept_by() == "region"
    core.let_go(bpy.context)
    assert len(released) == 2 and core.kept() is None
