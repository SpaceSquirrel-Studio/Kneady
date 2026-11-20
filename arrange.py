"""Rearranging buttons in the viewport. Greg asked for it: "It would be
good if users could reorganze the list in the viewport. The list appears as a
ring, row or rows/columns. When viewport edit is on an additonal button
appears in the viewport similar to + and -. It's in the the left corner of
the square ... It let's users drag the visible buttons within their menu when
toggled on. So dragging one button above or below another button pushes the
other buttons up or down or around in the radial case."

With Rearrange on (Viewport Edit's icon at the top left of the square around
the buttons, pick.py), a drag that starts on a button picks it up instead of
running its commands. That works for a button showing in its row, column,
grid, circle or menu ring. The button follows the mouse, and the others move
to make room as it passes each one's place. That order is its list's order,
the same order as the panel's tree and its arrows. Release keeps the new
order as one undo step; Esc puts the button back.

A click still does what it always does, so a menu can be opened to rearrange
what is in it. Buttons placed on the item keep their places. The button a
menu opens from is not in its ring's list, so it stays in the middle. Moving
another drag button to the front makes it the one a drag on the region
runs."""

import bpy  # type: ignore
from mathutils import Vector  # type: ignore

from . import core


def in_line(context, obj, region):
    """[(index, center)] for the buttons showing in the row, or in an open
    menu's ring, which its layout places. Buttons placed on the item are left
    out. Each center is where the layout puts the button. A button being
    moved is given at its place in the list, not at the mouse."""
    was = core.STATE.get("arranging")
    core.STATE["arranging"] = None
    try:
        placed, static, _faded, _extra = core._layout(context, obj, region)
    finally:
        core.STATE["arranging"] = was
    used = core.buttons_of(region)
    return [(i, c) for i, c in placed + static if i < len(used) and not used[i].placed]


def slots(context, obj, region, key):
    """[(index, center)] for the buttons of the list `key` that show in the
    row or ring, in list order."""
    members = core.button_list(region, key)["members"]
    shown = dict(in_line(context, obj, region))
    return [(i, shown[i]) for i in members if i in shown]


def movable(context, obj, region, index):
    """Whether button `index` can be rearranged: showing in the row or ring,
    with another of its list there."""
    if index is None or core.button_of(region, index) is None:
        return False
    shown = slots(context, obj, region, core.list_of(region, index))
    return len(shown) >= 2 and any(i == index for i, _c in shown)


def can_arrange(context, obj, region):
    """Whether any list showing has two buttons or more to rearrange."""
    counts = {}
    for i, _c in in_line(context, obj, region):
        key = core.list_of(region, i)
        counts[key] = counts.get(key, 0) + 1
    return any(n >= 2 for n in counts.values())


class Session:
    """One button being rearranged: moved through its list as the mouse
    passes each place, so the others make room."""

    def __init__(self, context, obj, region, index, at):
        self.name, self.rid = obj.name, region.id
        self.key = core.list_of(region, index)
        self.index = index
        self.home = core.button_list(region, self.key)["members"].index(index)
        self.places = [c.copy() for _i, c in slots(context, obj, region, self.key)]
        core.STATE["arranging"] = (self.name, self.rid, self.index, (at[0], at[1]))
        core.redraw()

    def _region(self):
        obj = bpy.data.objects.get(self.name)
        return obj, (core.find_region(obj, self.rid) if obj is not None else None)

    def _to_member(self, region, position):
        """Move the button to `position` among its list's members."""
        members = core.button_list(region, self.key)["members"]
        steps = position - members.index(self.index)
        step = 1 if steps > 0 else -1
        for _k in range(abs(steps)):
            new = core.move_in_list(region, self.key, step, self.index)
            if new is None:
                break
            self.index = new

    def move(self, context, at):
        """The mouse is at `at` (region pixels). The button takes the place
        nearest it, and the others move to make room."""
        obj, region = self._region()
        if region is None:
            return
        at = Vector((at[0], at[1]))
        if self.places:
            k = min(range(len(self.places)), key=lambda n: (self.places[n] - at).length)
            order = [i for i, _c in slots(context, obj, region, self.key)]
            if self.index in order and k < len(order) and order[k] != self.index:
                members = core.button_list(region, self.key)["members"]
                self._to_member(region, members.index(order[k]))
        core.STATE["arranging"] = (self.name, self.rid, self.index, (at.x, at.y))
        core.redraw()

    def cancel(self):
        """Put the button back where it started."""
        _obj, region = self._region()
        if region is not None:
            self._to_member(region, self.home)
        self.done()

    def done(self):
        """Stop following the mouse. Returns whether the button moved."""
        core.STATE["arranging"] = None
        core.redraw()
        _obj, region = self._region()
        if region is None:
            return False
        return core.button_list(region, self.key)["members"].index(self.index) != self.home
