"""Another add-on's handles over a region take the mouse before the region's
surface, but never before its buttons. Greg, of Digit's own handles: "the
stock Digit widget controls are actually quite good functionality wise.
Kneady is good for managing a menu to get to them".

Blender asks gizmo groups in the order they were registered and takes the
first hit. So a region's surface is a gizmo group of its own,
KNEADY_GGT_surface, registered after every other add-on's. The buttons'
gizmo answers only on a button, and the surface's only off one. Checked
with Digit's handles in a window (Digit's probe_handle_switches)."""

from types import SimpleNamespace

import rigs


def _ops():
    core = rigs.kneady()
    ops = __import__(core.__name__.rsplit(".", 1)[0] + ".ops", fromlist=["ops"])
    return ops, core


def test_surface_is_a_gizmo_group_of_its_own():
    ops, _core = _ops()
    assert ops._SURFACE_ON[0], "KNEADY_GGT_surface is not registered"
    assert ops.KNEADY_GGT_surface.SURFACE and not ops.KNEADY_GGT_regions.SURFACE


def test_buttons_and_surface_answer_apart():
    ops, core = _ops()
    keys = ("dragging", "pinned", "hover", "button", "block", "edit")
    saved = {k: core.STATE.get(k) for k in keys}
    hit_at = core.hit_at
    test = ops.KNEADY_GT_region._test
    buttons = SimpleNamespace(target="M", region=1, surface=False, _icon=lambda: None)
    surface = SimpleNamespace(target="M", region=1, surface=True, _icon=lambda: None)
    try:
        core.hit_at = lambda _context, _location: ("M", 1)
        core.STATE.update(dragging=False, pinned=None, hover=("M", 1), button=None, block=False, edit=None)
        assert test(buttons, None, (0, 0)) == -1, "the buttons' gizmo took the region's surface"
        assert test(surface, None, (0, 0)) == 0, "the surface's gizmo missed the region"
        core.STATE["button"] = 2
        assert test(buttons, None, (0, 0)) == 3, "the buttons' gizmo missed button 2"
        assert test(surface, None, (0, 0)) == -1, "the surface's gizmo took a button"
        core.STATE.update(button=None, block=True)
        core.hit_at = lambda _context, _location: None
        assert test(surface, None, (0, 0)) == 0, "the band around the row is not the surface's"
        core.STATE.update(block=False, hover=("Other", 1))
        assert test(surface, None, (0, 0)) == -1, "a region not hovered answered"
    finally:
        core.hit_at = hit_at
        core.STATE.update(saved)


def test_blender_tooltip_only_on_viewport_edit_icons():
    """Blender's own tooltip (the drag operator's description) is off on the
    region and its buttons, whose tooltip is Kneady's tip, and on for
    Viewport Edit's icons (Greg: "The default hover-over tooltips are
    displaying in addition to the ones we've made"). Seen in a window:
    tests/probe_tooltips.py."""
    ops, _core = _ops()
    icon = rigs.module("props").MAX_BUTTONS + 1
    assert not _tooltip_for(ops, -1) and not _tooltip_for(ops, 0) and not _tooltip_for(ops, 3)
    assert _tooltip_for(ops, icon) and _tooltip_for(ops, icon + 2)


def _tooltip_for(ops, part):
    gz = SimpleNamespace(use_tooltip=True, _test=lambda _context, _location: part)
    assert ops.KNEADY_GT_region.test_select(gz, None, (0, 0)) == part
    return gz.use_tooltip
