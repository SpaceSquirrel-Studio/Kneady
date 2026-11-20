"""What a program (another add-on, through Kneady's hooks) can change about
buttons:
- hide some of a region's buttons for now;
- take a click on one;
- switch a toggle its own way;
and room for more buttons than a row shows, a level at a time."""

import bpy  # type: ignore

import rigs


def _region(mesh, count=3):
    core = rigs.kneady()
    region = core.new_region(mesh, "R", whole=True)
    region.button_count = count
    return region


def test_a_filter_hides_buttons_for_now():
    """A filter decides which buttons show, and a drag on the region runs the
    first drag button showing. The panel's first button, used for placement
    and its header, is still the first of all."""
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    for b in region.buttons[:3]:
        b.up.enabled = True

    def hide_first(reg, obj, indices):
        return [i for i in indices if i != 0]

    core.add_button_filter(hide_first)
    try:
        assert core.shown_buttons(region, mesh) == [1, 2]
        assert core.first_drag_button(region, mesh, shown=True) == 1
        assert core.first_drag_button(region) == 0
    finally:
        core.remove_button_filter(hide_first)
    assert core.shown_buttons(region, mesh) == [0, 1, 2]


def test_a_program_takes_a_click():
    core = rigs.kneady()
    _rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    took = []

    def hook(context, obj, reg, index):
        took.append(index)
        return index == 1

    core.add_click_hook(hook)
    try:
        assert core.clicked(bpy.context, mesh, region, 1) and not core.clicked(bpy.context, mesh, region, 2)
        assert took == [1, 2]
    finally:
        core.remove_click_hook(hook)
    assert not core.clicked(bpy.context, mesh, region, 1)


def test_a_program_switches_a_toggle():
    """A switcher that takes a toggle switches it its own way. With no
    switcher, the toggle switches as usual."""
    core = rigs.kneady()
    rig, mesh = rigs.arm_rig()
    region = _region(mesh)
    rig["flag"] = 0.0
    toggle = region.buttons[0]
    toggle.action = "TOGGLE"
    toggle.switch.kind, toggle.switch.target, toggle.switch.data_path = "PROPERTY", rig, '["flag"]'
    seen = []

    def switcher(context, button, obj, reg, channels, on):
        seen.append(on)
        rig["flag"] = 0.5
        return True

    channels = core.switch_channels(toggle, mesh, region)
    core.add_switcher(switcher)
    try:
        core.switch_button(bpy.context, toggle, mesh, region, channels, True)
        assert seen == [True] and rig["flag"] == 0.5
    finally:
        core.remove_switcher(switcher)
    core.switch_button(bpy.context, toggle, mesh, region, core.switch_channels(toggle, mesh, region), True)
    assert rig["flag"] == 1.0


def test_room_for_more_buttons():
    """A region holds up to MAX_BUTTONS buttons, made as its count rises; a
    new region starts with a row's worth. A direction drives up to
    MAX_COMMANDS commands, enough for a fist's twelve finger bones."""
    core = rigs.kneady()
    props = core.props
    _rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "R", whole=True)
    assert len(region.buttons) == props.ROW_BUTTONS
    region.button_count = props.MAX_BUTTONS
    assert len(region.buttons) == props.MAX_BUTTONS and props.MAX_BUTTONS >= 14
    assert props.MAX_COMMANDS >= 12
