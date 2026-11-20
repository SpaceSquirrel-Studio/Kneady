"""A button's tip (tips.py): a row per key, worded by Kneady from the
button's commands unless its author words it, then the author's message.
The status bar says the same rows."""

import bpy  # type: ignore

import rigs


def _region(count=3):
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    region.button_count = count
    return core, mesh, region, core.buttons_of(region)


def _inputs(drag, *names):
    drag.enabled, drag.program = True, ""
    drag.kind, drag.input = "INPUT", names[0]
    drag.more.clear()
    for name in names[1:]:
        command = drag.more.add()
        command.kind, command.input = "INPUT", name


def test_tip_rows_say_what_each_key_does():
    """A drag button's tip: Drag up / down and left / right, each saying what
    it drives in a few words. Four sides of one end are its Sides, and both
    ends' are Start and End Sides. The keys that work on every button are
    hidden, and Shift+Click shows only on a button that opens a menu."""
    tips = rigs.module("tips")
    _core, mesh, region, used = _region()
    b = used[0]
    b.name = "Lengthen / Scale"
    _inputs(b.up, "Length")
    _inputs(b.across, "End Side +X", "End Side -X", "End Side +Y", "End Side -Y")
    rows = {r["key"]: r for r in tips.rows(region, 0, mesh)}
    assert rows["UP"]["label"] == "Drag ↕" and rows["UP"]["text"] == "Length", rows["UP"]
    assert rows["ACROSS"]["label"] == "Drag ↔" and rows["ACROSS"]["text"] == "End Sides", rows["ACROSS"]
    assert rows["ALT"]["default"] is False and rows["CTRL"]["default"] is False
    # a key held during a drag comes after it: with Maya-style navigation Alt
    # before the press orbits the view
    assert (rows["ALT"]["label"], rows["CTRL"]["label"], rows["SHIFT"]["label"]) == (
        "Drag+Alt", "Drag+Ctrl", "Drag+Shift"), [rows[k]["label"] for k in ("ALT", "CTRL", "SHIFT")]
    assert rows["SHIFT"]["default"] is False and rows["PIN"]["default"] is False, rows["PIN"]
    shown, message = tips.tip(region, 0, mesh, "INFORM")
    assert [r["key"] for r in shown] == ["UP", "ACROSS"] and message == "", shown
    # Kneady's own words for several commands
    assert tips.merged(["Start Side +X", "Start Side -X", "Start Side +Y", "Start Side -Y",
                        "End Side +X", "End Side -X", "End Side +Y", "End Side -Y"]) == "Start and End Sides"
    assert tips.merged(["Start Side +Y", "Start Side -Y", "Hub Scale Y"]) == "Start Side +Y/-Y, Hub Scale Y"
    assert tips.merged(["Length"]) == "Length"
    assert tips.merged(["Start Side +X", "End Side +X"]) == "Start and End Side +X"
    assert tips.merged(["Rotate X", "Rotate X"]) == "Rotate X"
    long = tips.merged(["Alpha Input", "Beta Input Value", "Gamma Input Value", "Delta Input Value"])
    assert long == "Alpha Input and 3 more", long
    assert tips._path_name('modifiers["GN"].show_viewport') == "Show Viewport"
    assert tips._path_name('data.shape_keys.key_blocks["Smile"].value') == "Smile"
    # a turn names its axis, and what it turns when it has a target of its own
    b.up.kind, b.up.axis = "ROTATE", "X"
    b.up.more.clear()
    assert tips.drag_text(b.up) == "Rotate X"
    # a toggle says what it switches
    t = used[1]
    t.action = "TOGGLE"
    t.switch.kind, t.switch.data_path = "PROPERTY", "show_wire"
    rows = {r["key"]: r for r in tips.rows(region, 1, mesh)}
    assert rows["CLICK"]["text"] == "Switch Show Wire on or off", rows["CLICK"]
    assert "UP" not in rows and "ACROSS" not in rows


def test_tip_names_a_menu_and_pins_it():
    """A button that opens a menu: its Click names the first buttons in it,
    and its Shift+Click (keep these controls up) shows by default."""
    tips = rigs.module("tips")
    menus = rigs.module("menus")
    _core, mesh, region, used = _region(6)
    top = used[0]
    top.name, top.opens_menu = "Curl / Spread", True
    uid = menus.ensure_uid(region, top)
    for b, name in zip(used[1:], ("Length", "Start +X", "Start -X", "Twist", "Move Z")):
        b.name, b.menu_parent = name, uid
    used[5].show = False                    # a hidden one is not named
    rows = {r["key"]: r for r in tips.rows(region, 0, mesh)}
    assert rows["CLICK"]["text"] == "More controls: Length, Start +X, Start -X, ...", rows["CLICK"]
    assert rows["PIN"]["default"] is True and rows["PIN"]["text"] == "Keep these controls up"
    used[4].show = False
    rows = {r["key"]: r for r in tips.rows(region, 0, mesh)}
    assert rows["CLICK"]["text"] == "More controls: Length, Start +X, Start -X", rows["CLICK"]


def test_tip_as_its_author_words_it():
    """The author words a row, hides one, shows one Kneady hides, and writes
    the message. The status bar says every row, shown in the tip or not, in
    the author's words, with an arrow before a drag's. The Show switch goes
    back to Auto where that is what Auto would do."""
    tips = rigs.module("tips")
    hints = rigs.module("hints")
    _core, mesh, region, used = _region()
    b = used[0]
    _inputs(b.up, "Length")
    _inputs(b.across, "End Side +X", "End Side -X", "End Side +Y", "End Side -Y")
    for key, text, show in (("UP", "Lengthen", "AUTO"), ("ACROSS", "", "HIDE"), ("CTRL", "", "SHOW")):
        item = b.tip_rows.add()
        item.key, item.text, item.show = key, text, show
    b.tip_text = "Lengthens the fingertip. The finger behind it follows."
    shown, message = tips.tip(region, 0, mesh, "INFORM")
    assert [(r["key"], r["said"]) for r in shown] == [("UP", "Lengthen"), ("CTRL", "Snap")], shown
    assert message == "Lengthens the fingertip. The finger behind it follows."
    items = hints.hover_items(bpy.context, mesh, region, 0)
    assert (("DRAG",), "↕ Lengthen") in items and (("DRAG",), "↔ End Sides") in items, items
    assert (("CTRL",), "Snap") in items and (("SHIFT", "LMB"), "Keep these controls up") in items, items
    # the eye in the panel: shown again is Auto (the default), hidden is Hide
    with bpy.context.temp_override(kneady_button=b):
        bpy.ops.kneady.tip_row_show(key="ACROSS", show=True, default=True)
        bpy.ops.kneady.tip_row_show(key="ALT", show=True, default=False)
    found = {r.key: r.show for r in b.tip_rows}
    assert found["ACROSS"] == "AUTO" and found["ALT"] == "SHOW", found
    # an edit is kept by what its row is about: with the command gone the row
    # goes, and with it back the author's word is back
    b.up.enabled = False
    assert "UP" not in {r["key"] for r in tips.rows(region, 0, mesh)}
    b.up.enabled = True
    assert tips.tip(region, 0, mesh, "INFORM")[0][0]["said"] == "Lengthen"
    # a long message wraps
    lines = tips.wrap(b.tip_text, 100, lambda t: 6 * len(t))
    assert all(6 * len(t) <= 100 for t in lines) and " ".join(lines) == b.tip_text, lines
    # it waits for the mouse to rest: not at once, then after TIP_DELAY; off
    # the button and back, it waits again
    tips.gone()
    assert not tips.ready(mesh, region, 0)
    tips._SINCE["t"] -= tips.TIP_DELAY + 0.01
    assert tips.ready(mesh, region, 0)
    assert not tips.ready(mesh, region, 1), "another button waits afresh"
    tips.gone()
    assert not tips.ready(mesh, region, 0)
    tips.gone()


def test_help_levels():
    """Help levels (Greg: "Learn, inform and expert", with Quiet later taking
    Expert's place):

    - Learn shows every row of a tip except any its author hid
    - Inform shows only the rows marked shown
    - Quiet shows none

    At every level the status bar says every row. The level is the
    person's, never the scene's: it is kept in a file of theirs (tips.FILE)
    and read on the window manager. A factory-startup session, as these
    tests run, reads and writes none."""
    import json
    import os
    import tempfile
    tips = rigs.module("tips")
    hints = rigs.module("hints")
    _core, mesh, region, used = _region()
    b = used[0]
    _inputs(b.up, "Length")
    _inputs(b.across, "Width")
    item = b.tip_rows.add()
    item.key, item.show = "SHIFT", "HIDE"

    def keys(at=None):
        return [r["key"] for r in tips.tip(region, 0, mesh, at)[0]]
    assert keys("INFORM") == ["UP", "ACROSS"], keys("INFORM")
    assert keys("LEARN") == ["UP", "ACROSS", "ALT", "CTRL", "PIN"], keys("LEARN")
    assert tips.tip(region, 0, mesh, "QUIET") == ([], "")
    assert bpy.app.factory_startup and tips._file() is None
    saved, saved_file = tips._LEVEL["value"], tips.FILE
    folder = tempfile.mkdtemp()
    wm = bpy.context.window_manager
    try:
        tips.FILE = os.path.join(folder, "kneady", "help.json")
        tips._LEVEL["value"] = None
        assert tips.level() == "LEARN" and wm.kneady_help == "LEARN", "no file yet: Learn, as Kneady starts"
        wm.kneady_help = "QUIET"
        assert tips.level() == "QUIET" and not tips.on()
        with open(tips.FILE, encoding="utf-8") as f:
            assert json.load(f) == {"help": "QUIET"}
        tips._LEVEL["value"] = None                    # a new session reads it back
        assert wm.kneady_help == "QUIET"
        assert keys() == [] and hints.hover_items(bpy.context, mesh, region, 0), "Quiet keeps the status bar"
        wm.kneady_help = "LEARN"
        assert keys() == ["UP", "ACROSS", "ALT", "CTRL", "PIN"]
        assert "kneady_help" not in bpy.context.scene and not hasattr(bpy.context.scene, "kneady_tips")
        wm.kneady_help = "INFORM"
        with open(tips.FILE, "w", encoding="utf-8") as f:
            f.write("not json")
        tips._LEVEL["value"] = None
        assert tips.level() == "LEARN", "a file that cannot be read: the default, Learn"
    finally:
        tips.FILE = saved_file
        tips._LEVEL["value"] = saved


def test_tip_travels_with_its_button():
    """A copied button takes its tip, rows and message. Copy Commands takes
    the rows, since they word the commands, but not the message. Whether the
    panel's tip section is folded is not a setting. The panel's rows are
    added after it draws (tips._fill), each empty so Kneady's words show as
    the field's placeholder."""
    core = rigs.kneady()
    tips = rigs.module("tips")
    _core, mesh, region, used = _region(3)
    a, b, c = used
    _inputs(a.up, "Length")
    item = a.tip_rows.add()
    item.key, item.text = "UP", "Lengthen"
    a.tip_text, a.tip_open = "What it is for", True
    data = core.to_data(a)
    assert "tip_open" not in data and data["tip_text"] == "What it is for"
    core.from_data(b, data)
    assert [(r.key, r.text) for r in b.tip_rows] == [("UP", "Lengthen")] and b.tip_text == "What it is for"
    assert not b.tip_open
    for name in core.COMMAND_DATA:
        if name in data:
            core.from_data(c, {name: data[name]})
    assert [(r.key, r.text) for r in c.tip_rows] == [("UP", "Lengthen")] and c.tip_text == ""
    # the panel's rows, filled straight after a draw
    fresh = used[2]
    fresh.tip_rows.clear()
    _inputs(fresh.across, "Width")
    tips._fill_later(region, 2)
    tips._fill()
    keys = {r.key for r in fresh.tip_rows}
    assert {"ACROSS", "PIN", "CTRL", "SHIFT"} <= keys and all(r.text == "" for r in fresh.tip_rows), keys


def test_tip_of_a_handle():
    """A 3D handle's tip: its one drag, along it, with no arrow, no click and
    no Shift+Click, which a handle does not take. A program's own keys are
    shown, worded by the program."""
    core = rigs.kneady()
    tips = rigs.module("tips")
    _core, mesh, region, used = _region(2)
    h = used[1]
    h.placed, h.handle, h.handle_shape = True, "HANDLE", "BOX"
    _inputs(h.up, "End Side +X")
    rows = [r["key"] for r in tips.rows(region, 1, mesh)]
    assert rows[0] == "UP" and "PIN" not in rows and "CLICK" not in rows, rows
    assert tips.rows(region, 1, mesh)[0]["label"] == "Drag"
    # a tip that would only say its name again is none
    h.name = "End Side +X"
    assert tips.tip(region, 1, mesh, "INFORM") == ([], ""), tips.tip(region, 1, mesh, "INFORM")
    h.tip_text = "Widens the tip on its outer side."
    assert len(tips.tip(region, 1, mesh, "INFORM")[0]) == 1
    h.tip_text = ""
    h.handle_shape = "RING"
    assert tips.rows(region, 1, mesh)[0]["label"] == "Drag around"
    # only Left / Right on: the handle drives that
    h.handle_shape = "ARROW"
    h.up.enabled = False
    _inputs(h.across, "Twist")
    assert [r["key"] for r in tips.rows(region, 1, mesh)][0] == "ACROSS"
    assert core.buttons_of(region)[1].tip_text == ""
    # a program's own keys, as Digit's Side box gives them: Drag first, the
    # keys after (Greg: "with Maya controls you have to click alt and alt
    # shift after drag"), and shown
    key = "test_tip_keys"
    core.add_command_kind(key, "Sides", drag=dict(
        motion=lambda obj, command, point: None, begin=lambda context, obj, command: {},
        apply=lambda *a: None, restore=lambda *a: None,
        keys=lambda command: ("ALT", "SHIFT"),
        hints=lambda command: [(("ALT",), "Both X sides"), (("ALT", "SHIFT"), "All four sides")]))
    try:
        h.across.program = key
        found = {r["key"]: r for r in tips.rows(region, 1, mesh)}
        assert found["KEY:ALT"]["label"] == "Drag+Alt" and found["KEY:ALT+SHIFT"]["label"] == "Drag+Alt+Shift", found
        assert found["KEY:ALT+SHIFT"]["text"] == "All four sides" and found["KEY:ALT"]["default"] is True
        assert "ALT" not in found and "SHIFT" not in found, "the program reads Alt and Shift itself"
    finally:
        h.across.program = ""
        core.remove_command_kind(key)
