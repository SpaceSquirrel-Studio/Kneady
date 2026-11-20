"""A Gap: a button that only holds a place in its row or ring. Greg spaced a
menu's ring with buttons named "Empty" that drove nothing, and they drew as
blank circles. A gap keeps its slot and shows nothing, but in Viewport Edit
it stays, dashed, to be picked and moved."""

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

import rigs


def _row(core):
    rig, mesh = rigs.arm_rig()
    region = core.new_region(mesh, "Arm", whole=True)
    region.button_count = 3
    for b, name in zip(region.buttons, ("Bend", "Spacer", "Twist")):
        b.name = name
        b.up.enabled, b.up.kind, b.up.axis, b.up.target, b.up.bone = True, "ROTATE", "X", rig, "Lower"
    region.arrange = "ROW"
    return mesh, region


def test_gap_holds_its_place():
    core = rigs.kneady()
    mesh, region = _row(core)
    center = core.region_center
    core.region_center = lambda context, obj, rid: Vector((400.0, 300.0))
    wm = bpy.context.window_manager
    try:
        every = dict(core.button_layout(bpy.context, mesh, region))
        assert sorted(every) == [0, 1, 2], every
        region.buttons[1].action = "GAP"
        shown = dict(core.button_layout(bpy.context, mesh, region))
        assert sorted(shown) == [0, 2], "the gap is drawn or hit: %s" % sorted(shown)
        assert all((shown[i] - every[i]).length < 1e-6 for i in (0, 2)), \
            "the buttons beside the gap moved: %s, %s" % (shown, every)
        # Viewport Edit: there, to pick and move
        wm.kneady_pick = True
        assert sorted(dict(core.button_layout(bpy.context, mesh, region))) == [0, 1, 2], \
            "a gap is not there to pick in Viewport Edit"
        wm.kneady_pick = False
        # a drag on the region never runs a gap
        region.buttons[1].action = "DRAG"
        region.buttons[0].action = "GAP"
        assert core.first_drag_button(region) == 1, core.first_drag_button(region)
        assert core.is_gap(region.buttons[0]) and not core.is_gap(region.buttons[1])
    finally:
        core.region_center = center
        wm.kneady_pick = False


def test_layout_worked_out_once_a_frame():
    """A region's layout is worked out once a frame (core.changed), however
    many regions' gizmos ask. On Greg's hand 46 asked at once, which with a
    menu of handles open had cost 574 ms a mouse move. It is worked out again
    as soon as one of its buttons is edited, a frame passes, or anything is
    redrawn."""
    core = rigs.kneady()
    mesh, region = _row(core)
    center = core.region_center
    work = core._work_out_layout
    calls = []

    def counted(*args):
        calls.append(1)
        return work(*args)

    core.region_center = lambda context, obj, rid: Vector((400.0, 300.0))
    core._work_out_layout = counted
    try:
        core.changed()
        first = dict(core.button_layout(bpy.context, mesh, region))
        for _k in range(10):
            assert dict(core.button_layout(bpy.context, mesh, region)) == first
        assert len(calls) == 1, "worked out %d times in one frame" % len(calls)
        region.buttons[1].action = "GAP"                      # an edit with no redraw
        assert sorted(dict(core.button_layout(bpy.context, mesh, region))) == [0, 2]
        assert len(calls) == 2, "an edit not seen: %d" % len(calls)
        core.changed()
        core.button_layout(bpy.context, mesh, region)
        assert len(calls) == 3, "a new frame not worked out again"
        core.redraw()
        core.button_layout(bpy.context, mesh, region)
        assert len(calls) == 4, "a redraw not worked out again"
    finally:
        core.region_center = center
        core._work_out_layout = work
