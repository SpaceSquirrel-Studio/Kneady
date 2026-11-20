"""Kneady's operators and gizmos: the drag, the buttons, and editing
an object's region list."""

import math

import bmesh  # type: ignore
import bpy  # type: ignore
from bpy_extras import view3d_utils  # type: ignore
from mathutils import Quaternion, Vector  # type: ignore

from . import reg
from . import core, placed, props

FINE = 0.1                         # a drag's speed with Shift held


def _region_world_center(obj, rid, context):
    geometry = core.region_geometry(obj, context.evaluated_depsgraph_get()).get(rid)
    if geometry is None:
        return None
    _pts, lo, hi = geometry
    return obj.matrix_world @ ((lo + hi) * 0.5)


def commands_of(drag):
    """A drag direction's commands: its own, then any added - all moved by
    the same drag (Greg: "Can control drive multiple attributes?")."""
    return [drag] + list(drag.more) if drag.enabled else []


def select_driven_bones(context, channels, toggle=False):
    """Select the pose bones a button drives, on armatures in Pose mode, and
    return them. Every other bone is deselected first, unless `toggle`, which
    flips each driven bone's selection as Shift+click does. The last one
    becomes active if it ends up selected."""
    bones = []
    for commands in channels:
        for ch in commands:
            if ch.ok and ch.pb is not None and ch.obj.mode == "POSE" and ch.pb not in bones:
                bones.append(ch.pb)
    if not bones:
        return bones
    if not toggle:
        for obj in context.objects_in_mode:
            if obj.type == "ARMATURE" and obj.pose is not None:
                for pb in obj.pose.bones:
                    core.select_bone(pb, False)
    for pb in bones:
        core.select_bone(pb, not core.bone_selected(pb) if toggle else True)
    last = bones[-1]
    if core.bone_selected(last):
        last.id_data.data.bones.active = last.bone
    return bones


# The keys that type a number during a drag, as G / R / S accept one.
TYPED_KEYS = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5", "SIX": "6",
              "SEVEN": "7", "EIGHT": "8", "NINE": "9", "PERIOD": ".", "MINUS": "-",
              "NUMPAD_0": "0", "NUMPAD_1": "1", "NUMPAD_2": "2", "NUMPAD_3": "3", "NUMPAD_4": "4",
              "NUMPAD_5": "5", "NUMPAD_6": "6", "NUMPAD_7": "7", "NUMPAD_8": "8", "NUMPAD_9": "9",
              "NUMPAD_PERIOD": ".", "NUMPAD_MINUS": "-"}


def typed_value(text):
    """The number typed so far, or None while it is not one yet ("-", ".")."""
    try:
        return float(text)
    except ValueError:
        return None


class KNEADY_OT_drag(bpy.types.Operator):
    """Drag a Kneady region to drive what it controls"""
    bl_idname = "kneady.drag"
    bl_label = "Kneady"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    target: bpy.props.StringProperty(options={"SKIP_SAVE", "HIDDEN"})
    region: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})
    button: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"},
                                  description="The button whose commands run, or the toggle a click switches")
    # True when pressed on the region itself, not on a button's circle. The
    # region's first drag button then runs (core.first_drag_button), since
    # a toggle has nothing to drag.
    region_press: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # What a toggle was switched to, for a redo: 1 on, 0 off. -1 flips it
    # from its current state.
    switch_to: bpy.props.IntProperty(default=-1, min=-1, max=1, options={"SKIP_SAVE", "HIDDEN"})
    # What the drag did: how far it went each way, in pixels, and the signs
    # that made each command follow the mouse. One distance serves every
    # command a direction drives, each at its own speed. A drag sets these;
    # the redo panel or a script types them in.
    across: bpy.props.FloatProperty(name="Left / Right", description="How far the drag went across, in pixels",
                                    options={"SKIP_SAVE"})
    up: bpy.props.FloatProperty(name="Up / Down", description="How far the drag went up, in pixels",
                                options={"SKIP_SAVE"})
    signs: bpy.props.FloatVectorProperty(size=2 * props.MAX_COMMANDS, default=[1.0] * (2 * props.MAX_COMMANDS),
                                         options={"SKIP_SAVE", "HIDDEN"})
    # The value each command reached (core.display_value), for the redo
    # panel. Type one in and the drag that gives it is worked out (_solve);
    # the direction's other commands follow.
    across_values: bpy.props.FloatVectorProperty(size=props.MAX_COMMANDS, options={"SKIP_SAVE"},
                                                 name="Left / Right")
    up_values: bpy.props.FloatVectorProperty(size=props.MAX_COMMANDS, options={"SKIP_SAVE"}, name="Up / Down")
    values_set: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # The view a View or Depth command was aimed at, so a redo moves the same
    # way: the view's rotation, and each command's scene units per pixel.
    view_rotation: bpy.props.FloatVectorProperty(size=4, default=(1.0, 0.0, 0.0, 0.0),
                                                 options={"SKIP_SAVE", "HIDDEN"})
    view_scale: bpy.props.FloatVectorProperty(size=2 * props.MAX_COMMANDS, options={"SKIP_SAVE", "HIDDEN"})
    view_set: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # For a drag along a 3D handle (placed.py): each Move's or Rotate's
    # amount per pixel along the handle, so it follows the mouse. Kept for a
    # redo; 0 for a command that goes at its Speed.
    handle_scale: bpy.props.FloatVectorProperty(size=2 * props.MAX_COMMANDS, options={"SKIP_SAVE", "HIDDEN"})
    handle_set: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # Where the drag was pressed, in world space: the point on the region,
    # or for a press on a button, the middle of its region. It picks which
    # object of a control group is driven (core.command_object). Kept for a
    # redo.
    point: bpy.props.FloatVectorProperty(size=3, options={"SKIP_SAVE", "HIDDEN"})
    point_set: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # The modifier keys held as the drag ended, kept for a redo. A program's
    # own kind of drag reads them (core.add_command_kind) - Digit's Sides,
    # for one, takes Alt to move both sides of an axis.
    keys: bpy.props.StringProperty(options={"SKIP_SAVE", "HIDDEN"})

    # No description method: Blender's tooltip, which showed one beside a
    # button, is turned off there (KNEADY_GT_region.test_select). Kneady's
    # own tip says what the button does.

    def _begin(self):
        obj = bpy.data.objects.get(self.target)
        region = core.find_region(obj, self.region) if obj is not None else None
        if region is None:
            return False
        index = core.first_drag_button(region, obj, shown=True) if self.region_press else self.button
        # index is None when the region has only toggles. A press on the
        # region still selects, so it takes the first button.
        button = core.button_of(region, 0 if index is None else index)
        if button is None:
            return False
        self._obj, self._region, self._button = obj, region, button
        self._index = None if self.region_press else index
        self._toggle = button.action == "TOGGLE" and not self.region_press
        point = Vector(self.point) if self.point_set else None
        self._switches = core.switch_channels(button, obj, region, point) if self._toggle else []
        self._channels = [[core.Channel(c, obj, region, point) for c in commands_of(drag)[:props.MAX_COMMANDS]]
                          for drag in (button.across, button.up)] if button.action != "TOGGLE" else [[], []]
        # modifier keys a program's drag reads itself, which Kneady leaves alone
        self._taken = set()
        for commands in self._channels:
            for ch in commands:
                if ch.ok:
                    self._taken |= ch.keys_taken()
        self._keys = set(k for k in self.keys.split(",") if k)
        # a region driving nothing yet still takes a click, to select
        return True

    def _toggle_now(self, context, on=None):
        """Switch the toggle on, off, or (None) from what it is now, and key
        it if Auto Keying is on."""
        if not any(ch.ok for ch in self._switches):
            why = next((ch.why for ch in self._switches), "Nothing set to switch yet")
            self.report({"WARNING"}, "%s: %s" % (self._button.name, why))
            return {"CANCELLED"}
        if on is None:
            on = not core.switch_state(self._switches)
        core.switch_button(context, self._button, self._obj, self._region, self._switches, on)
        self.switch_to = int(on)
        self._key(context)
        core.redraw()
        self._acted(False)
        return {"FINISHED"}

    def _acted(self, moved):
        """Report what was done - a drag (`moved`) or a click - to whoever is
        watching through core.add_action_hook, such as a tutorial."""
        region, button = getattr(self, "_region", None), getattr(self, "_button", None)
        core.acted("kneady.drag", target=self.target, region=self.region, region_name=getattr(region, "name", ""),
                   button=self.button, button_name=getattr(button, "name", ""), moved=bool(moved))

    def _usable(self):
        return [any(ch.ok for ch in chans) for chans in self._channels]

    def _scale_handle(self):
        """For a redo of a drag along a 3D handle: give each command the
        amount per pixel the original drag had."""
        if not self.handle_set:
            return
        for axis, commands in enumerate(self._channels):
            for k, ch in enumerate(commands):
                per = self.handle_scale[axis * props.MAX_COMMANDS + k]
                ch.handle_per_pixel = per if per else None

    def _aim_handle(self, context, here):
        """Set up a press on a 3D handle button (placed.handles_for).

        On an arrow (or an object shape), the drag goes along it on screen
        for the direction it shows (`drives`) and across it for the other.
        A ring is dragged around (_aim_ring), and a Quad Arrow along its arms
        (_aim_cross). A Move or Rotate follows the mouse, positive the way
        the handle points. Returns None for any other press."""
        if self._index is None or self.region_press:
            return None
        found = core.layout_handles(context, self._obj, self._region).get(self._index)
        if found is None or not found.get("live"):
            return None
        drives = placed.handle_drives(self._button)
        if found.get("rim"):
            return self._aim_ring(found, drives, here)
        if found.get("arms"):
            return self._aim_cross(found)
        if not found.get("per"):
            return None
        along = found["tip"] - found["base"]
        if along.length < 1e-6:
            return None
        signs, scales = list(self.signs), [0.0] * (2 * props.MAX_COMMANDS)
        for axis, commands in enumerate(self._channels):
            for k, ch in enumerate(commands):
                slot = axis * props.MAX_COMMANDS + k
                signs[slot] = 1.0
                if axis != drives or not ch.ok or ch.view_mode or not core.follows_handle(ch):
                    continue
                motion, lever = placed.channel_motion(ch, found["world"])
                if motion is None:
                    continue
                dot = motion.dot(found["direction"])
                signs[slot] = -1.0 if dot < -0.05 else 1.0
                per = found["per"] * self._scale
                if ch.kind == "ROTATE" or getattr(ch, "turning", False):
                    per = per / lever if lever and lever > 1e-9 else 0.0
                scales[slot] = per
                ch.handle_per_pixel = per or None
        self.signs, self.handle_scale, self.handle_set = signs, scales, True
        return dict(drives=drives, along=along.normalized())

    def _aim_cross(self, found):
        """Set up a press on a Quad Arrow. Each arm carries one drag
        direction: Up / Down along one, Left / Right along the other. A Move
        or Rotate follows the mouse along its arm, as on a single arrow. An
        arm pointing at the viewer carries nothing (_handle_axes)."""
        signs, scales = list(self.signs), [0.0] * (2 * props.MAX_COMMANDS)
        alongs = {}
        for axis, commands in enumerate(self._channels):
            for k in range(len(commands)):
                signs[axis * props.MAX_COMMANDS + k] = 1.0
            arm = found["arms"].get(axis)
            if arm is None or not arm["live"] or not arm["per"] or (arm["tip"] - arm["base"]).length < 1e-6:
                continue
            alongs[axis] = (arm["tip"] - arm["base"]).normalized()
            for k, ch in enumerate(commands):
                if not ch.ok or ch.view_mode or not core.follows_handle(ch):
                    continue
                motion, lever = placed.channel_motion(ch, found["world"])
                if motion is None:
                    continue
                slot = axis * props.MAX_COMMANDS + k
                signs[slot] = -1.0 if motion.dot(arm["direction"]) < -0.05 else 1.0
                per = arm["per"] * self._scale
                if ch.kind == "ROTATE" or getattr(ch, "turning", False):
                    per = per / lever if lever and lever > 1e-9 else 0.0
                scales[slot] = per
                ch.handle_per_pixel = per or None
        if not alongs:
            return None
        self.signs, self.handle_scale, self.handle_set = signs, scales, True
        return dict(cross=True, alongs=alongs, drives=1 if 1 in alongs else 0)

    def _aim_ring(self, found, drives, here):
        """Set up a press on a ring.

        Normally the drag sweeps around the ring's middle on screen and
        turns about its axis by the angle swept; counterclockwise on screen
        is positive when the axis points at the viewer. With the ring nearly
        edge on, the drag instead goes along its rim where it was grabbed,
        positive the way the ring turns. Either way, a pixel along the rim
        is 1 / r_px radians.

        A Rotate about the ring's axis turns by exactly that, so it follows
        the mouse. Anything else goes at its Speed along the rim."""
        rim, tangent = found["rim"], None
        if found["face_on"] < placed.RING_EDGE:
            k = min(range(len(rim) - 1), key=lambda j: (rim[j] - here).length)
            along = rim[(k + 1) % (len(rim) - 1)] - rim[k - 1]
            if along.length > 0.4 * (2.0 * found["r_px"] * 2.0 * math.pi / (len(rim) - 1)):
                tangent = along.normalized()
        view_sign = 1.0 if tangent is not None else found["facing"]
        signs, scales = list(self.signs), [0.0] * (2 * props.MAX_COMMANDS)
        for axis, commands in enumerate(self._channels):
            for k, ch in enumerate(commands):
                slot = axis * props.MAX_COMMANDS + k
                signs[slot] = 1.0 if axis != drives else view_sign
                if axis != drives or not ch.ok or ch.view_mode:
                    continue
                own = placed.channel_axis(ch)           # a Rotate's axis, or a turning program drag's
                if own is None:
                    continue
                dot = own.dot(found["axis"])
                signs[slot] = view_sign * (-1.0 if dot < 0.0 else 1.0)
                scales[slot] = self._scale / max(found["r_px"], 1e-6)
                ch.handle_per_pixel = scales[slot]
        self.signs, self.handle_scale, self.handle_set = signs, scales, True
        return dict(drives=drives, ring=True, center=found["base"], tangent=tangent, r_px=found["r_px"],
                    total=0.0)

    def _ring_axes(self, before, here, k):
        """One move of a drag around a ring, as [across, up], and the total
        so far. The distance is how far the mouse went along the rim, in
        pixels: the angle swept about the middle times the radius, or the
        distance along the rim where grabbed. It goes to the direction the
        ring drives."""
        h = self._handle
        if h["tangent"] is not None:
            arc = (here - before).dot(h["tangent"])
        else:
            a, b = before - h["center"], here - h["center"]
            if a.length < 2.0 or b.length < 2.0:
                arc = 0.0                       # too near its middle to say which way it turns
            else:
                arc = math.atan2(a.x * b.y - a.y * b.x, a.dot(b)) * h["r_px"]
        arc *= k
        h["total"] += arc
        d = Vector((0.0, arc)) if h["drives"] == 1 else Vector((arc, 0.0))
        travel = Vector((0.0, h["total"])) if h["drives"] == 1 else Vector((h["total"], 0.0))
        return d, travel

    def _handle_axes(self, d):
        """A move on screen, as [across, up], for a drag along a 3D handle.
        The part along the arrow goes to the direction it drives, and the
        part across it (to its right) to the other. On a Quad Arrow the move
        is split between its arms as they lie on screen."""
        if self._handle.get("cross"):
            al = self._handle["alongs"]
            if 0 in al and 1 in al:
                u, v = al[1], al[0]
                det = v.x * u.y - v.y * u.x
                if abs(det) > 0.25:
                    # d = across * v + up * u
                    return Vector(((d.x * u.y - d.y * u.x) / det, (v.x * d.y - v.y * d.x) / det))
                # the arms nearly one line on screen: whichever the move runs
                # along more
                return Vector((0.0, d.dot(u))) if abs(d.dot(u)) >= abs(d.dot(v)) else Vector((d.dot(v), 0.0))
            return Vector((0.0, d.dot(al[1]))) if 1 in al else Vector((d.dot(al[0]), 0.0))
        u = self._handle["along"]
        right = Vector((u.y, -u.x))
        along, across = d.dot(u), d.dot(right)
        return Vector((across, along)) if self._handle["drives"] == 1 else Vector((along, -across))

    def _aim(self, context=None):
        """Aim the View and Depth commands at a view. That is the one the drag
        begins in, whose rotation and per-command scale are kept for a redo,
        or, for a redo with no view, the one kept."""
        region, rv3d = (context.region, context.region_data) if context is not None else (None, None)
        live = rv3d is not None and region is not None
        if live:
            self.view_rotation = tuple(rv3d.view_rotation)
        elif not self.view_set:
            return
        rotation = Quaternion(self.view_rotation)
        scales = list(self.view_scale)
        for axis, commands in enumerate(self._channels):
            for k, ch in enumerate(commands):
                if not ch.ok or ch.view_mode is None:
                    continue
                slot = axis * props.MAX_COMMANDS + k
                if live:
                    # a pixel at the target's depth, in scene units, at this
                    # interface's scale (the drag counts pixels at a scale of 1)
                    point = core.world_matrix(ch.obj, ch.pb).translation
                    at = view3d_utils.location_3d_to_region_2d(region, rv3d, point)
                    if at is None:
                        per = rv3d.view_distance / max(region.height, 1)
                    else:
                        a = view3d_utils.region_2d_to_location_3d(region, rv3d, at, point)
                        b = view3d_utils.region_2d_to_location_3d(region, rv3d, at + Vector((1.0, 0.0)), point)
                        per = (b - a).length
                    scales[slot] = per * self._scale
                ch.use_view(axis, rotation, scales[slot])
        if live:
            self.view_scale = scales
            self.view_set = True

    def _write(self, pixels, ctrl=False):
        """Apply every command at its amount for a drag of `pixels` ([across,
        up]), and record the value each reached, for the redo panel."""
        chans, amounts = [], []
        for axis, commands in enumerate(self._channels):
            shown = self.up_values if axis else self.across_values
            for k, ch in enumerate(commands):
                if ch.ok:
                    chans.append(ch)
                    # a pixel at the interface's scale, so a drag the same
                    # length by hand does the same on a 4K screen (core.ui_scale)
                    amount = core.amount_for(ch, pixels[axis] / self._scale,
                                             self.signs[axis * props.MAX_COMMANDS + k])
                    amounts.append(amount)
                    shown[k] = core.display_value(ch, amount)
        self.values_set = True
        keys = getattr(self, "_keys", set())
        self.keys = ",".join(sorted(keys))
        core.apply(chans, amounts, ctrl, keys)

    def _pixels_giving(self, axis, k, value):
        """The drag along `axis`, in this screen's pixels, that brings its
        command `k` to `value` - None if none can."""
        ch = self._channels[axis][k]
        px = core.pixels_for(ch, core.amount_from_display(ch, value), self.signs[axis * props.MAX_COMMANDS + k])
        return None if px is None else px * self._scale

    def _solve(self):
        """For a value typed in the redo panel, work out the drag that gives
        it. The other commands of that direction follow."""
        if not self.values_set:
            return
        for axis, commands in enumerate(self._channels):
            shown = self.up_values if axis else self.across_values
            px = self.up if axis else self.across
            for k, ch in enumerate(commands):
                if not ch.ok:
                    continue
                implied = core.display_value(ch, core.amount_for(
                    ch, px / self._scale, self.signs[axis * props.MAX_COMMANDS + k]))
                if abs(shown[k] - implied) > 1e-5 * max(1.0, abs(implied)):
                    solved = self._pixels_giving(axis, k, shown[k])
                    if solved is not None:
                        if axis:
                            self.up = solved
                        else:
                            self.across = solved
                    break

    def _restore(self):
        for commands in self._channels:
            for ch in commands:
                ch.restore()

    def execute(self, context):
        self._scale = core.ui_scale(context)
        if not self._begin():
            return {"CANCELLED"}
        if self._toggle:
            return self._toggle_now(context, None if self.switch_to < 0 else bool(self.switch_to))
        if not any(self._usable()):
            return {"CANCELLED"}
        self._aim()
        self._scale_handle()
        self._solve()
        self._write((self.across, self.up))
        self._key(context)
        self._acted(abs(self.across) + abs(self.up) > 0.5)
        return {"FINISHED"}

    def _key(self, context):
        """Key what the drag changed when Auto Keying is on (core.auto_key),
        and say so when the settings let nothing be keyed - as Blender does
        for its own transforms."""
        keyed, missed = core.auto_key(context, [ch for commands in self._channels for ch in commands]
                                      + self._switches)
        if missed and not keyed:
            why = ("Replace keys only where there is a key" if context.scene.tool_settings.auto_keying_mode
                   == "REPLACE_KEYS" else "Only Insert Available (Preferences > Animation) keys only what is "
                   "animated already")
            self.report({"WARNING"}, "Auto Keying keyed nothing: %s" % why)

    def draw(self, context):
        """The redo panel: the value each command reached, to type over. The
        drag's distances in pixels are left out; they are for scripts."""
        layout = self.layout
        if getattr(self, "_toggle", False):
            layout.label(text="%s: switched %s" % (self._button.name, "on" if self.switch_to == 1 else "off"))
            return
        channels = getattr(self, "_channels", [[], []])
        for label, prop, commands in (("Left / Right", "across_values", channels[0]),
                                      ("Up / Down", "up_values", channels[1])):
            if not any(ch.ok for ch in commands):
                continue
            col = layout.column(align=True)
            col.label(text=label)
            for k, ch in enumerate(commands):
                if ch.ok:
                    unit = " (%s)" % core.UNITS[ch.kind] if ch.kind in core.UNITS else ""
                    col.prop(self, prop, index=k, text=ch.label() + unit)

    def _press_point(self, context, here):
        """Record where the drag was pressed, in world space: the point on its
        region under the mouse, or, for a press on a button, the middle of
        its region."""
        obj = bpy.data.objects.get(self.target)
        if obj is None:
            return
        point = None
        if self.region_press:
            hit = core.hit_at(context, here)
            point = hit[2] if hit is not None and hit[0] == self.target and len(hit) > 2 else None
            if point is None:
                # a Show Through region seen past what covers it: the point on
                # the region itself
                origin = view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, here)
                direction = view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, here)
                through = core.through_hit(context, obj, origin, direction)
                if through is not None and through[0] == self.region:
                    point = through[1]
        if point is None:
            point = _region_world_center(obj, self.region, context)
        if point is None:
            point = obj.matrix_world.translation
        self.point, self.point_set = tuple(point), True

    def invoke(self, context, event):
        self._scale = core.ui_scale(context)
        if context.region_data is None:
            return {"CANCELLED"}
        self._press_point(context, Vector((event.mouse_region_x, event.mouse_region_y)))
        if not self._begin():
            return {"CANCELLED"}
        if event.ctrl and core.picking(context):
            # Viewport Edit: Ctrl+click selects the button in the panel and does
            # nothing else, so a menu's button can be edited without opening
            # its menu (pick.py). Ctrl pressed once a drag is under way still
            # snaps.
            from . import pick
            pick.pick(context, self._obj, self._region, self._index)
            return {"CANCELLED"}
        # Rearrange (arrange.py): a drag from a button, once past the drag
        # threshold, moves the button within its row or ring instead of
        # running its commands. A click still does what it always does.
        from . import arrange, pick
        self._arrange = None
        self._arrangeable = (not self.region_press and self._index is not None and pick.arranging(context)
                             and arrange.movable(context, self._obj, self._region, self._index))
        here = Vector((event.mouse_region_x, event.mouse_region_y))
        if self._toggle:
            # switched on the release, as a button is, if the mouse stayed put
            self._press, self._travel = here, 0.0
            what = " + ".join(ch.label() for ch in self._switches if ch.ok) or "nothing yet"
            context.workspace.status_text_set("%s - %s:      release to switch %s %s      Esc: cancel" % (
                self._region.name, self._button.name, what,
                "off" if core.switch_state(self._switches) else "on"))
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        self._aim(context)
        hit = core.hit_at(context, here)
        grabbed = hit[2] if hit is not None and hit[0] == self.target else None
        anchor = _region_world_center(self._obj, self.region, context)
        region, rv3d = context.region, context.region_data

        def project(p):
            return view3d_utils.location_3d_to_region_2d(region, rv3d, p)

        signs = [1.0] * (2 * props.MAX_COMMANDS)
        for axis, commands in enumerate(self._channels):
            for k, ch in enumerate(commands):
                if ch.ok:
                    signs[axis * props.MAX_COMMANDS + k] = core.sign_for(ch, axis, project, anchor, grabbed)
        self.signs = signs
        self._handle = self._aim_handle(context, here)
        self._last = self._press = here
        self._travel = 0.0
        self._pixels = [0.0, 0.0]
        self._lock = None
        self._alt_held = False             # an Alt press switched; its release switches back
        self._typed = ""                   # a number typed during the drag
        self._typed_axis = None
        # Whether the drag visibly moves anything (core.surface_sample).
        # Checked once it has gone some distance, and only for commands that
        # move a bone or an object.
        self._looked = not any(ch.ok and ch.kind in ("ROTATE", "MOVE", "SCALE")
                               for commands in self._channels for ch in commands)
        self._still = False
        self._sample = None if self._looked else core.surface_sample(self._obj, context.evaluated_depsgraph_get())
        # The buttons hide while a drag runs. With Rearrange on, nothing runs
        # until the press turns out to be a click or picks the button up, so
        # they stay drawn until then, as for a toggle's press. Hidden, they
        # blinked out for a moment before each pickup.
        core.STATE["dragging"] = not self._arrangeable
        core.redraw()
        self._status(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _status(self, context):
        """Fill the status bar during the drag.

        It shows what the drag drives now (with one direction at a time, the
        live one and what Alt switches to) and the keys that change it, as
        Blender's own key icons. The mode the held keys put in effect stands
        out and the rest are dimmed (hints.mark). This matters with
        Maya-style navigation: Alt before a click orbits, so an Alt mode is
        pressed mid-drag, and the status bar is where it shows."""
        from . import hints
        names = ("Left / Right", "Up / Down")
        labels = [" + ".join(ch.label() + (" (%s)" % ch.note if getattr(ch, "note", None) else "")
                             for ch in commands if ch.ok) or None for commands in self._channels]
        lead = [((), "%s - %s" % (self._region.name, self._button.name))]
        items = []
        alt_free = "ALT" not in self._taken
        if self._button.single and self._lock is not None:
            items.append(((), "%s: %s" % (names[self._lock], labels[self._lock])))
            other = 1 - self._lock
            if labels[other] and alt_free:
                items.append((("ALT",), "%s %s: %s" % ("Release: back to" if self._alt_held else "Switch to",
                                                     names[other], labels[other])))
        else:
            items += [((), "%s: %s" % (n, l)) for n, l in zip(names, labels) if l]
            if self._button.single and all(labels) and alt_free:
                items.append((("ALT",), "One direction at a time: the other"))
        # what a program's drag says of its own keys (Digit's Sides: Alt for
        # both sides of the axis, Alt+Shift all four)
        for commands in self._channels:
            for ch in commands:
                if not (ch.ok and getattr(ch, "dragging", False)):
                    continue
                drag = ch.spec["drag"]
                if drag.get("hints"):
                    found = [(tuple(k), t) for k, t in drag["hints"](ch.drag)]
                elif drag.get("status"):
                    note = drag["status"](ch.drag)
                    found = [((), note)] if note else []
                else:
                    found = []
                items += [f for f in found if f not in items]
        if self._typed:
            axis = self._typed_axis
            ch = next(c for c in self._channels[axis] if c.ok)
            unit = core.UNITS.get(ch.kind, "")
            context.workspace.status_text_set("%s - %s:      %s: %s = %s%s      Enter: confirm      "
                                              "Backspace: edit      Esc: cancel" % (
                                                  self._region.name, self._button.name, names[axis],
                                                  ch.label(), self._typed, unit))
            return
        items += [((), "Type a number")] + ([(("SHIFT",), "Fine")] if "SHIFT" not in self._taken else []) + \
            [(("CTRL",), "Snap"), (("ESC",), "Cancel")]
        if getattr(self, "_still", False):
            lead.append(((), "Nothing has moved: an IK / FK switch or a constraint may be holding it"))
        marked = hints.mark(lead + items, getattr(self, "_keys", ()))
        core.STATE["status"] = hints.as_text(marked)
        self._shown_keys = set(getattr(self, "_keys", ()))
        hints.show(context, marked)

    def _switch(self, context):
        """Hand the drag to the other direction if it can take it. Returns
        whether it did."""
        lock = core.switched(self._lock, self._usable())
        if lock == self._lock:
            return False
        self._lock = lock
        self._status(context)
        return True

    def _update(self, ctrl):
        # Each direction is written at what it has done so far. With one
        # direction at a time, the one not live keeps its amount, so drags
        # stack across an Alt switch.
        self.across, self.up = self._pixels
        self._write(self._pixels, ctrl)

    def _finish(self, context):
        from . import hints
        core.STATE["dragging"] = False
        core.forget()
        hints.forget()                      # shown again at the next mouse move
        context.workspace.status_text_set(core.idle_status())
        core.redraw()

    def _click(self, context, toggle):
        """A click, not a drag: select the object, as a click does with Kneady
        off. The region's gizmo takes the press, so nothing else would select
        it. Shift toggles the selection, as Blender's own click does. In Pose
        mode it selects the bones the button drives instead, so the region
        works as a picker for its rig's controls, ready for Blender's own
        tools."""
        if context.mode == "POSE":
            select_driven_bones(context, self._channels, toggle)
            return
        obj = self._obj
        if toggle:
            obj.select_set(not obj.select_get())
        else:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
        if obj.select_get():
            context.view_layer.objects.active = obj

    def _menu_open(self):
        """Whether the menu this button opens is the one open now."""
        from . import menus
        top = menus.opened(self._obj, self._region)
        return top is not None and top[0] == self._index

    def _click_switch(self, context, was_open, shift):
        """Switch what a drag button's own click drives (click_on), after any
        program has had the click.

        - On a button that opens a menu: on as its menu opens, off as it
          closes.
        - On any other button: flipped from its current state - but not with
          Shift, which pinned the region instead (core.clicked).

        Keyed as a toggle is. Returns whether it switched."""
        if self._button.opens_menu:
            now = self._menu_open()
            if now == was_open:
                return False
            on = now
        elif shift:
            return False
        else:
            on = None
        point = Vector(self.point) if self.point_set else None
        channels = core.switch_channels(self._button, self._obj, self._region, point)
        if not any(ch.ok for ch in channels):
            why = next((ch.why for ch in channels), "Nothing set to switch yet")
            self.report({"WARNING"}, "%s: %s" % (self._button.name, why))
            return False
        state = core.switch_state(channels)
        if on is None:
            on = not state
        elif state == on:
            return False
        core.switch_button(context, self._button, self._obj, self._region, channels, on)
        core.auto_key(context, channels)
        core.redraw()
        return True

    def _picked(self, context):
        """Viewport Edit: after a click does its usual work, it also selects
        what it was on in the panel - the button, or the region (pick.py)."""
        if core.picking(context):
            from . import pick
            pick.pick(context, self._obj, self._region, self._index)

    def _type(self, context, event):
        """Handle a key toward a number typed during the drag. The live
        direction's first command takes the number as its value, in its own
        terms, as the redo panel shows them. The drag that gives that value
        is worked out, and the direction's other commands follow. Returns
        whether the key was taken."""
        if event.value != "PRESS":
            return event.type in TYPED_KEYS or event.type == "BACK_SPACE"
        if event.type == "BACK_SPACE":
            if not self._typed:
                return False
            self._typed = self._typed[:-1]
        elif event.type in TYPED_KEYS:
            ch = TYPED_KEYS[event.type]
            if not self._typed:
                usable = self._usable()
                axis = self._lock
                if axis is None or not usable[axis]:
                    # the direction moved most, else Up / Down, else Left / Right
                    order = sorted((1, 0), key=lambda a: -abs(self._pixels[a]))
                    axis = next((a for a in order if usable[a]), None)
                if axis is None:
                    return True
                self._typed_axis = axis
                self._mouse_pixels = list(self._pixels)
            if ch == "-":
                self._typed = self._typed[1:] if self._typed.startswith("-") else "-" + self._typed
            elif ch != "." or "." not in self._typed:
                self._typed += ch
        else:
            return False
        if not self._typed:
            # everything typed erased: back to the mouse's drag
            self._pixels = self._mouse_pixels
        else:
            value = typed_value(self._typed)
            axis = self._typed_axis
            k = next(i for i, c in enumerate(self._channels[axis]) if c.ok)
            px = self._pixels_giving(axis, k, value) if value is not None else None
            if px is not None:
                self._pixels[axis] = px
        self._update(False)
        self._status(context)
        core.redraw()
        return True

    def _confirm(self, context):
        self._key(context)
        self._finish(context)
        self._acted(True)
        return {"FINISHED"}

    def _start_arrange(self, context, here):
        """Past the drag threshold with Rearrange on: pick the button up
        (arrange.py). It stays drawn while it moves."""
        from . import arrange
        self._arrange = arrange.Session(context, self._obj, self._region, self._index, here)
        core.STATE["dragging"] = False
        context.workspace.status_text_set("Rearrange %s:      drag it to a new place      Release: keep      "
                                          "Esc: cancel" % self._button.name)

    def _arrange_modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._arrange.cancel()
            self._finish(context)
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            self._arrange.move(context, (event.mouse_region_x, event.mouse_region_y))
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            moved = self._arrange.done()
            self._finish(context)
            if moved:
                # its own undo step, named for what it did - not the drag's
                from . import tree
                tree.follow(context, self._arrange._region()[1], self._arrange.index)
                bpy.ops.ed.undo_push(message="Rearrange Buttons")
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def _toggle_modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            context.workspace.status_text_set(core.idle_status())
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            here = Vector((event.mouse_region_x, event.mouse_region_y))
            self._travel = max(self._travel, (here - self._press).length)
            if self._arrangeable and self._travel >= context.preferences.inputs.drag_threshold_mouse:
                self._start_arrange(context, here)
                return {"RUNNING_MODAL"}
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            context.workspace.status_text_set(core.idle_status())
            if self._travel >= context.preferences.inputs.drag_threshold_mouse:
                return {"CANCELLED"}               # dragged off it: nothing, as a button
            if event.shift:
                # Shift+click pins the region, as on any button (core.toggle_kept)
                core.toggle_kept(context, self._obj, self._region)
                self._picked(context)
                return {"CANCELLED"}
            done = self._toggle_now(context)
            if done == {"FINISHED"}:
                # what it switched may show other buttons, so the spot clicked
                # holds its region (core.hold_click)
                core.hold_click(context, self._obj, self._region, (event.mouse_region_x, event.mouse_region_y),
                                self._index)
            self._picked(context)
            return done
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if self._arrange is not None:
            return self._arrange_modal(context, event)
        if self._toggle:
            return self._toggle_modal(context, event)
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._restore()
            self._finish(context)
            return {"CANCELLED"}
        if self._arrangeable and event.type != "LEFTMOUSE":
            # Rearrange on: nothing runs until it is a click or the button is
            # picked up
            if event.type == "MOUSEMOVE":
                here = Vector((event.mouse_region_x, event.mouse_region_y))
                self._travel = max(self._travel, (here - self._press).length)
                if self._travel >= context.preferences.inputs.drag_threshold_mouse:
                    self._start_arrange(context, here)
            return {"RUNNING_MODAL"}
        if event.type in TYPED_KEYS or event.type == "BACK_SPACE":
            self._type(context, event)
            return {"RUNNING_MODAL"}
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS" and self._typed:
            return self._confirm(context)
        if self._typed and event.type == "LEFTMOUSE" and event.value == "RELEASE":
            return self._confirm(context)
        if self._typed and event.type in {"MOUSEMOVE", "LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL",
                                          "LEFT_ALT", "RIGHT_ALT"}:
            return {"RUNNING_MODAL"}          # a typed number holds until confirmed or erased
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._travel < context.preferences.inputs.drag_threshold_mouse:
                self._restore()
                self.across = self.up = 0.0
                # A click. A program may take it on a button (one that opens
                # more buttons, or runs an operator); the spot clicked then
                # holds its region while the buttons change (core.hold_click).
                # A button's own click may also switch something (click_on).
                # Otherwise the click selects.
                clicks = self._index is not None and core.has_click(self._button)
                was_open = self._menu_open() if clicks else False
                spot = (event.mouse_region_x, event.mouse_region_y)
                took = self._index is not None and core.clicked(context, self._obj, self._region, self._index,
                                                                event.shift)
                if took:
                    core.hold_click(context, self._obj, self._region, spot, self._index)
                if clicks:
                    if self._click_switch(context, was_open, event.shift):
                        core.hold_click(context, self._obj, self._region, spot, self._index)
                elif not took:
                    self._click(context, event.shift)
                self._picked(context)
            else:
                self._key(context)
            self._finish(context)
            self._acted(self._travel >= context.preferences.inputs.drag_threshold_mouse)
            return {"FINISHED"}
        # the modifier keys held, which a program's drag reads (core.apply)
        self._keys = {k for k, on in (("ALT", event.alt), ("SHIFT", event.shift), ("CTRL", event.ctrl)) if on}
        if self._keys != getattr(self, "_shown_keys", None) and not self._typed:
            self._status(context)            # the mode in effect stands out in the status bar
        if event.type in {"LEFT_ALT", "RIGHT_ALT"}:
            # Holding Alt hands a one-direction drag to the other direction,
            # and releasing it hands the drag back, each keeping what the
            # other did. So pressing and releasing goes on switching as the
            # artist tweaks. Greg: "releasing should return to the pre alt
            # behavior". Read here, Alt never reaches navigation. A program's
            # drag that reads Alt itself (Digit's Sides) gets it instead: the
            # drag is written again as Alt is pressed or released.
            if "ALT" in self._taken:
                if not event.is_repeat:
                    self._update(event.ctrl)
                    core.redraw()
                return {"RUNNING_MODAL"}
            if not event.is_repeat and self._button.single:
                if event.value == "PRESS" and not self._alt_held:
                    self._alt_held = True          # so the status bar reads "Release Alt"
                    self._alt_held = self._switch(context)
                elif event.value == "RELEASE" and self._alt_held:
                    self._alt_held = False
                    self._switch(context)
            return {"RUNNING_MODAL"}
        if event.type in {"MOUSEMOVE", "LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL"}:
            # a move adds to what came before at its own speed, so Shift slows
            # what follows without jumping back
            here = Vector((event.mouse_region_x, event.mouse_region_y))
            before = self._last
            # Shift slows the drag - not one whose program reads Shift itself
            fine = FINE if event.shift and "SHIFT" not in self._taken else 1.0
            d = (here - before) * fine
            self._last = here
            self._travel = max(self._travel, (here - self._press).length)
            was = self._lock
            travel = here - self._press
            if self._handle is not None and self._handle.get("ring"):
                # around the ring, not across and up the screen
                d, travel = self._ring_axes(before, here, fine)
            elif self._handle is not None:
                # along the arrow and across it, not across and up the screen
                d, travel = self._handle_axes(d), self._handle_axes(travel)
            self._pixels, self._lock = core.accumulate(self._pixels, self._lock, d, travel,
                                                       self._button.single, self._scale)
            if self._lock != was:
                self._status(context)
            self._update(event.ctrl)
            if not self._looked and self._travel > core.STILL_PIXELS * self._scale:
                self._looked = True
                moved = core.moved_since(self._sample, core.surface_sample(self._obj,
                                                                           context.evaluated_depsgraph_get()))
                self._still = moved is not None and moved < 1e-6
                if self._still:
                    self._status(context)
            core.redraw()
        return {"RUNNING_MODAL"}


# -- Gizmos: hit testing and the click ----------------------------------------------------

# Each region has two gizmos (see the docstring below) so that another
# add-on's handles can sit over a region's surface and still be grabbed.
# Greg wanted Digit's own handles usable with Kneady on: "the stock Digit
# widget controls are actually quite good functionality wise. Kneady is good
# for managing a menu to get to them".
class KNEADY_GT_region(bpy.types.Gizmo):
    """One region: nothing of its own to draw (the draw handlers paint), hit by
    the shared ray cast. Part 0 is the region, which drags its first button's
    commands; the next its buttons' circles, each dragging its own; then
    Viewport Edit's icons at the corners of the square round them, each with
    its own operator (pick.icon_parts). The band around the row is part 0
    too, whatever lies under it.

    A region has two of these: one for its buttons and icons, in
    KNEADY_GGT_regions, and one for its surface - part 0 - in
    KNEADY_GGT_surface. Blender asks gizmo groups in
    the order they were registered and takes the first hit, so another
    add-on's handles lying over a region are found before its surface, which
    is registered after them, but never before its buttons."""
    bl_idname = "KNEADY_GT_region"
    __slots__ = ("target", "region", "surface")

    def setup(self):
        self.target, self.region, self.surface = "", 0, False

    def draw(self, context):
        pass

    def test_select(self, context, location):
        part = self._test(context, location)
        # Blender's own tooltip is on only for Viewport Edit's icons, which
        # have no other way to say what they do. A button's tip is Kneady's
        # (tips.py). Blender's showed beside it too, the drag's description in
        # a sentence - Greg: "The default hover-over tooltips are displaying
        # in addition to the ones we've made". Set here, before Blender
        # highlights the part and starts its tooltip's timer.
        tooltip = part > props.MAX_BUTTONS
        if self.use_tooltip != tooltip:
            self.use_tooltip = tooltip
        return part

    def _test(self, context, location):
        if core.busy(context):
            return -1
        if core.STATE.get("pinned"):
            # a region held on screen for editing (core.pin): its buttons are
            # being moved, so nothing runs
            core.hit_at(context, location)
            return -1
        hit = core.hit_at(context, location)
        if core.STATE["hover"] != (self.target, self.region):
            return -1
        icon = self._icon() if core.STATE.get("edit") else None
        if not self.surface:
            # Viewport Edit's icons (pick.py), then the buttons
            if icon is not None:
                return icon[0]
            if core.STATE["button"] is not None:
                return core.STATE["button"] + 1
            return -1
        if icon is not None or core.STATE["button"] is not None:
            return -1
        # the band around the row is the region's, whatever lies under it
        on_region = hit is not None and hit[0] == self.target and hit[1] == self.region
        return 0 if on_region or core.STATE["block"] else -1

    @staticmethod
    def _icon():
        from . import pick
        return pick.icon_parts().get(core.STATE["edit"])


class _RegionGizmos:
    """What KNEADY_GGT_regions and KNEADY_GGT_surface share: a gizmo each
    region, while Kneady is on in Object or Pose mode (core.MODES)."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}
    SURFACE = False

    @classmethod
    def poll(cls, context):
        return core.working(context)

    def setup(self, context):
        self.keys = []
        self._sync(context)

    def refresh(self, context):
        self._sync(context)

    def draw_prepare(self, context):
        self._sync(context)

    def _sync(self, context):
        from . import pick
        parts = {} if self.SURFACE else pick.icon_parts()
        found = [(o.name, r.id) for o in core.objects_with_regions(context) for r in core.regions_of(o)]
        found.append(tuple(sorted(parts.items())))          # an icon a program adds: new gizmos
        if found == self.keys:
            return
        for gz in list(self.gizmos):
            self.gizmos.remove(gz)
        for name, rid in found[:-1]:
            gz = self.gizmos.new(KNEADY_GT_region.bl_idname)
            gz.target, gz.region, gz.surface = name, rid, self.SURFACE
            for part in ((0,) if self.SURFACE else range(props.MAX_BUTTONS + 1)):
                drag = gz.target_set_operator("kneady.drag", index=part)
                drag.target, drag.region, drag.button = name, rid, max(part - 1, 0)
                drag.region_press = part == 0
            for part, op in parts.values():
                try:
                    edit = gz.target_set_operator(op, index=part)
                    edit.target, edit.region = name, rid
                except (AttributeError, KeyError, RuntimeError, TypeError):
                    pass                                    # an operator gone with its program
        self.keys = found


class KNEADY_GGT_regions(_RegionGizmos, bpy.types.GizmoGroup):
    """Kneady's regions' buttons and Viewport Edit's icons. Their surfaces
    are KNEADY_GGT_surface's."""
    bl_idname = "KNEADY_GGT_regions"
    bl_label = "Kneady"


class KNEADY_GGT_surface(_RegionGizmos, bpy.types.GizmoGroup):
    """Kneady's regions' surfaces - a drag on one runs its first button -
    registered after the other add-ons' gizmo groups (register_surface), so
    their handles lying over a region take the mouse before it does."""
    bl_idname = "KNEADY_GGT_surface"
    bl_label = "Kneady Surfaces"
    SURFACE = True


_SURFACE_ON = [False]


def register_surface():
    """Register KNEADY_GGT_surface once every add-on enabled with this one
    has registered its own gizmo groups. A timer runs it straight after; in
    the background it runs at once, since a timer would wait for the
    script to end."""
    if not _SURFACE_ON[0]:
        bpy.utils.register_class(KNEADY_GGT_surface)
        _SURFACE_ON[0] = True
    return None


def _unregister_surface():
    if bpy.app.timers.is_registered(register_surface):
        bpy.app.timers.unregister(register_surface)
    if _SURFACE_ON[0]:
        reg.unregister_class(KNEADY_GGT_surface)
        _SURFACE_ON[0] = False


# -- The region list ----------------------------------------------------------------------

def _active_list(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None, None, None
    kn = obj.kneady
    region = kn.regions[kn.index] if 0 <= kn.index < len(kn.regions) else None
    return obj, kn, region


def _clear_faces(obj, rid):
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.faces.layers.int.get(core.TAG)
        if layer is not None:
            for f in bm.faces:
                if f[layer] == rid:
                    f[layer] = 0
            bmesh.update_edit_mesh(obj.data)
        return
    tags = core.face_tags(obj.data)
    if tags is not None:
        faces = [i for i, t in enumerate(tags) if t == rid]
        if faces:
            core.tag_faces(obj.data, faces, 0)


class KNEADY_OT_region_add(bpy.types.Operator):
    """Add a Kneady region to the active object"""
    bl_idname = "kneady.region_add"
    bl_label = "Add Region"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_list(context)[0] is not None

    def execute(self, context):
        obj = context.active_object
        fixed = core.regions_fixed(obj)
        if fixed:
            self.report({"WARNING"}, fixed)
            return {"CANCELLED"}
        core.new_region(obj)
        core.forget(obj.name)
        core.redraw()
        return {"FINISHED"}


class KNEADY_OT_region_unlisted(bpy.types.Operator):
    """Make a region of each set of faces that carries a region this object
    does not list - what Join leaves of the other objects' regions. Set up
    what their buttons drive again"""
    bl_idname = "kneady.region_unlisted"
    bl_label = "Make Them Regions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and context.mode == "OBJECT" and bool(core.unlisted_tags(obj))

    def execute(self, context):
        obj = context.active_object
        fixed = core.regions_fixed(obj)
        if fixed:
            self.report({"WARNING"}, fixed)
            return {"CANCELLED"}
        made = []
        for rid in sorted(core.unlisted_tags(obj)):
            made.append(core.new_region(obj, "Joined %d" % rid, rid=rid).name)
        core.forget(obj.name)
        core.redraw()
        self.report({"INFO"}, "Made %s: set up what their buttons drive" % ", ".join(made))
        return {"FINISHED"}


class KNEADY_OT_region_remove(bpy.types.Operator):
    """Remove the active Kneady region, and its tag from its faces"""
    bl_idname = "kneady.region_remove"
    bl_label = "Remove Region"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_list(context)[2] is not None

    def execute(self, context):
        obj, kn, region = _active_list(context)
        fixed = core.regions_fixed(obj)
        if fixed:
            self.report({"WARNING"}, fixed)
            return {"CANCELLED"}
        _clear_faces(obj, region.id)
        kn.regions.remove(kn.index)
        kn.index = min(kn.index, len(kn.regions) - 1)
        core.forget(obj.name)
        core.redraw()
        return {"FINISHED"}


class KNEADY_OT_region_move(bpy.types.Operator):
    """Move the active Kneady region up or down the list"""
    bl_idname = "kneady.region_move"
    bl_label = "Move Region"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", "")))

    @classmethod
    def poll(cls, context):
        return _active_list(context)[2] is not None

    def execute(self, context):
        _obj, kn, _region = _active_list(context)
        to = kn.index + (-1 if self.direction == "UP" else 1)
        if 0 <= to < len(kn.regions):
            kn.regions.move(kn.index, to)
            kn.index = to
        return {"FINISHED"}


class KNEADY_OT_region_edit(bpy.types.Operator):
    """Edit the active region's faces: into Edit Mode, faces selectable - or
    back out of it"""
    bl_idname = "kneady.region_edit"
    bl_label = "Edit Faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_list(context)[2] is not None

    def execute(self, context):
        obj = context.active_object
        if obj.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
        else:
            bpy.ops.object.mode_set(mode="EDIT")
            context.tool_settings.mesh_select_mode = (False, False, True)
        core.forget(obj.name)
        return {"FINISHED"}


class KNEADY_OT_region_faces(bpy.types.Operator):
    """Assign the selected faces to the active region, remove them from it, or
    select or deselect its faces"""
    bl_idname = "kneady.region_faces"
    bl_label = "Region Faces"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(items=(
        ("ASSIGN", "Assign", "Make the selected faces part of the active region"),
        ("REMOVE", "Remove", "Take the selected faces out of the active region"),
        ("SELECT", "Select", "Select the active region's faces"),
        ("DESELECT", "Deselect", "Deselect the active region's faces")))

    @classmethod
    def description(cls, context, properties):
        return dict((i.identifier, i.description) for i in
                    cls.bl_rna.properties["action"].enum_items)[properties.action]

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and _active_list(context)[2] is not None

    def execute(self, context):
        obj, _rc, region = _active_list(context)
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.faces.layers.int.get(core.TAG) or bm.faces.layers.int.new(core.TAG)
        n = 0
        for f in bm.faces:
            if self.action == "ASSIGN" and f.select:
                f[layer] = region.id
                n += 1
            elif self.action == "REMOVE" and f.select and f[layer] == region.id:
                f[layer] = 0
                n += 1
            elif self.action in {"SELECT", "DESELECT"} and f[layer] == region.id:
                f.select_set(self.action == "SELECT")
                n += 1
        if self.action in {"SELECT", "DESELECT"}:
            bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        core.forget(obj.name)
        core.redraw()
        self.report({"INFO"}, "%s: %d faces" % (self.action.title(), n))
        return {"FINISHED"}


def region_bone(region):
    """The rig and bone a region's first button turns, or (None, "")."""
    if region is None or not len(region.buttons):
        return None, ""
    up = region.buttons[0].up
    if up.target is None or up.target.type != "ARMATURE" or not up.bone:
        return None, ""
    return up.target, up.bone


class KNEADY_OT_region_group(bpy.types.Operator):
    """Select the faces mostly weighted to the chosen vertex group - then Assign
    makes them the region's"""
    bl_idname = "kneady.region_group"
    bl_label = "Select Faces"
    bl_options = {"REGISTER", "UNDO"}

    from_bone: bpy.props.BoolProperty(
        name="From Bone", options={"HIDDEN", "SKIP_SAVE"},
        description="The groups the region's bone deforms by, guessed by name, instead of the chosen one")

    @classmethod
    def description(cls, context, properties):
        if properties.from_bone:
            return ("Select the faces the region's bone deforms - its vertex groups found by name, every "
                    "segment of a limb - then Assign makes them the region's")
        return cls.__doc__

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and context.edit_object is not None

    def execute(self, context):
        obj = context.edit_object
        if self.from_bone:
            rig, bone = region_bone(_active_list(context)[2])
            groups = core.bone_groups(obj, bone, rig)
            if not groups:
                self.report({"WARNING"}, "No vertex group found for %s: choose one below" % bone)
                return {"CANCELLED"}
        else:
            if obj.vertex_groups.get(obj.kneady.faces_group) is None:
                self.report({"WARNING"}, "Choose a vertex group")
                return {"CANCELLED"}
            groups = [obj.kneady.faces_group]
        bm = bmesh.from_edit_mesh(obj.data)
        deform = bm.verts.layers.deform.active
        if deform is None:
            self.report({"WARNING"}, "The mesh has no vertex weights")
            return {"CANCELLED"}
        wanted = [g.index for g in obj.vertex_groups if g.name in set(groups)]
        # summed, as core.group_faces: a limb's segments share their seam
        on = {v for v in bm.verts if sum(v[deform].get(i, 0.0) for i in wanted) > 0.5}
        n = 0
        for f in bm.faces:
            if all(v in on for v in f.verts):
                f.select_set(True)
                n += 1
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, "%d faces of %s selected: Assign makes them the region's" % (n, " and ".join(groups)))
        return {"FINISHED"}


class KNEADY_OT_command_rig(bpy.types.Operator):
    """Drive the armature that deforms this mesh"""
    bl_idname = "kneady.command_rig"
    bl_label = "Use Rig"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        command = getattr(context, "kneady_command", None)
        obj = context.active_object
        rig = core.mesh_rig(obj)
        if command is None or rig is None:
            return {"CANCELLED"}
        command.target = rig
        if not command.bone:
            command.bone = core.active_bone(rig)
        return {"FINISHED"}


class KNEADY_OT_command_bone(bpy.types.Operator):
    """Drive the armature's active bone - the one last clicked in Pose mode"""
    bl_idname = "kneady.command_bone"
    bl_label = "Use Active Bone"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        command = getattr(context, "kneady_command", None)
        bone = core.active_bone(command.target) if command is not None else ""
        if not bone:
            return {"CANCELLED"}
        command.bone = bone
        return {"FINISHED"}


class KNEADY_OT_switch_kind(bpy.types.Operator):
    """What a click switches: a modifier input, a property, or what an add-on
    gives (core.add_command_kind)"""
    bl_idname = "kneady.switch_kind"
    bl_label = "Drives"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    kind: bpy.props.StringProperty(options={"SKIP_SAVE"})
    program: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        if properties.program:
            spec = core._COMMAND_KINDS.get(properties.program)
            return (spec["description"] or spec["label"]) if spec is not None else properties.program
        return next((tip for key, _name, tip in props.KINDS if key == properties.kind), "")

    def execute(self, context):
        command = getattr(context, "kneady_command", None)
        if command is None or self.kind not in props.SWITCH_KINDS:
            return {"CANCELLED"}
        command.kind = self.kind
        if command.program != self.program:
            command.program = self.program
            command.program_data = ""
        core.redraw()
        return {"FINISHED"}


class KNEADY_OT_drag_kind(bpy.types.Operator):
    """Drive what an add-on gives for a drag (core.add_command_kind's drag),
    or - clicked again - go back to the kind above"""
    bl_idname = "kneady.drag_kind"
    bl_label = "Drives"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    program: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        spec = core._COMMAND_KINDS.get(properties.program)
        return (spec["description"] or spec["label"]) if spec is not None else properties.program

    def execute(self, context):
        command = getattr(context, "kneady_command", None)
        if command is None:
            return {"CANCELLED"}
        program = "" if command.program == self.program else self.program
        if command.program != program:
            command.program = program
            command.program_data = ""
        core.redraw()
        return {"FINISHED"}


class KNEADY_OT_command_add(bpy.types.Operator):
    """Add a command to this drag direction: it moves with the others, by
    its own target, speed and step"""
    bl_idname = "kneady.command_add"
    bl_label = "Add Command"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        drag = getattr(context, "kneady_drag", None)
        if drag is None or len(drag.more) + 1 >= props.MAX_COMMANDS:
            return {"CANCELLED"}
        added = drag.more.add()
        # like the one before it, so a second slide or a second input is a
        # change of name, not a set-up from scratch
        before = drag.more[-2] if len(drag.more) > 1 else drag
        props.copy_command(before, added)
        added.command_open = True          # added to be set up: open, where the others stay folded
        return {"FINISHED"}


class KNEADY_OT_command_remove(bpy.types.Operator):
    """Remove this command; the others go on as they were"""
    bl_idname = "kneady.command_remove"
    bl_label = "Remove Command"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    # its place among the direction's commands: 0 is the direction's own,
    # 1 and up the added ones
    index: bpy.props.IntProperty()

    def execute(self, context):
        drag = getattr(context, "kneady_drag", None)
        if drag is None or not len(drag.more) or not 0 <= self.index <= len(drag.more):
            return {"CANCELLED"}
        if self.index == 0:
            # the direction's own command: the next takes its place. Greg: "I
            # can add command sections but I can't remove them"
            props.copy_command(drag.more[0], drag)
            drag.command_open = drag.more[0].command_open
            drag.more.remove(0)
        else:
            drag.more.remove(self.index - 1)
        return {"FINISHED"}


# Which of the panel's lists of buttons an operator acts on, by its key
# (core.button_list)
def _list_key():
    return bpy.props.StringProperty(default="all", options={"HIDDEN", "SKIP_SAVE"})


class KNEADY_OT_button_add(bpy.types.Operator):
    """Add a button to this list"""
    bl_idname = "kneady.button_add"
    bl_label = "Add Button"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    key: _list_key()

    def execute(self, context):
        region = getattr(context, "kneady_region", None)
        if region is None:
            return {"CANCELLED"}
        index, why = core.add_button(context, region, self.key)
        if index is None:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        from . import tree
        tree.follow(context, region, index)
        return {"FINISHED"}


class KNEADY_OT_button_remove(bpy.types.Operator):
    """Remove the selected button"""
    bl_idname = "kneady.button_remove"
    bl_label = "Remove Button"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    key: _list_key()

    def execute(self, context):
        region = getattr(context, "kneady_region", None)
        if region is None:
            return {"CANCELLED"}
        why = core.remove_button(region, self.key)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        from . import tree
        tree.follow(context, region, core.selected_button(region, self.key))
        return {"FINISHED"}


class KNEADY_OT_button_move(bpy.types.Operator):
    """Move the selected button up or down the list: its place in the row,
    column or circle. The first button that drags is the one a drag on the
    region runs"""
    bl_idname = "kneady.button_move"
    bl_label = "Move Button"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    key: _list_key()
    direction: bpy.props.EnumProperty(items=(("UP", "Up", "Earlier"), ("DOWN", "Down", "Later")))

    @classmethod
    def description(cls, context, properties):
        return "Move the selected button %s the list: %s in the row, column or circle" % (
            ("up", "earlier") if properties.direction == "UP" else ("down", "later"))

    def execute(self, context):
        region = getattr(context, "kneady_region", None)
        moved = None if region is None else core.move_in_list(region, self.key,
                                                               -1 if self.direction == "UP" else 1)
        if moved is None:
            return {"CANCELLED"}
        from . import tree
        tree.follow(context, region, moved)
        return {"FINISHED"}


def _clipboard_target(context, scope):
    """The region or button the panel's copy or paste is for."""
    return getattr(context, "kneady_region" if scope == "REGION" else "kneady_button", None)


_SCOPES = (("REGION", "Region", "The region's buttons, with their menus, number and arrangement"),
           ("BUTTON", "Button", "One button"),
           ("COMMANDS", "Commands", "One button's commands: what its drags or its click drive"))


class KNEADY_OT_copy(bpy.types.Operator):
    """Copy the buttons - every one, with their menus, number and arrangement
    - to paste onto another region, in this file or another"""
    bl_idname = "kneady.copy"
    bl_label = "Copy Buttons"
    bl_options = {"REGISTER", "INTERNAL"}

    scope: bpy.props.EnumProperty(items=_SCOPES, default="REGION")

    @classmethod
    def description(cls, context, properties):
        if properties.scope == "BUTTON":
            return "Copy this button, to paste over another"
        if properties.scope == "COMMANDS":
            return "Copy what this button drives - its drags' commands, or a toggle's - to paste onto another"
        return cls.__doc__

    def execute(self, context):
        target = _clipboard_target(context, self.scope)
        if target is None:
            return {"CANCELLED"}
        data = core.commands_data(target) if self.scope == "COMMANDS" else core.to_data(target)
        core.copy_data(context, self.scope.lower(), data)
        self.report({"INFO"}, "Copied %s" % (
            "the buttons of " + target.name if self.scope == "REGION"
            else "the commands of " + target.name if self.scope == "COMMANDS" else target.name))
        return {"FINISHED"}


class KNEADY_OT_paste(bpy.types.Operator):
    """Paste copied buttons over this region's: the region keeps its name,
    faces and look"""
    bl_idname = "kneady.paste"
    bl_label = "Paste Buttons"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    scope: bpy.props.EnumProperty(items=_SCOPES, default="REGION")

    @classmethod
    def description(cls, context, properties):
        if properties.scope == "BUTTON":
            return "Paste a copied button over this one"
        if properties.scope == "COMMANDS":
            return "Paste copied commands onto this button: it keeps its name, look, place and menu"
        return cls.__doc__

    @classmethod
    def poll(cls, context):
        # which scope is not known here; the button greys when nothing is
        # copied (ui.py asks copied() itself)
        return True

    def execute(self, context):
        target = _clipboard_target(context, self.scope)
        found = core.copied(context, self.scope.lower())
        if target is None or found is None:
            self.report({"WARNING"}, "Nothing copied: Copy %s first" % (
                "a button's commands" if self.scope == "COMMANDS" else "a " + self.scope.lower()))
            return {"CANCELLED"}
        why = {"REGION": core.paste_region, "BUTTON": core.paste_button,
               "COMMANDS": core.paste_commands}[self.scope](target, found)
        if why:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        core.forget()
        core.redraw()
        from . import tree
        tree.refresh(context)
        return {"FINISHED"}


_classes = (KNEADY_OT_drag, KNEADY_GT_region, KNEADY_GGT_regions,
            KNEADY_OT_region_add, KNEADY_OT_region_unlisted, KNEADY_OT_region_remove, KNEADY_OT_region_move,
            KNEADY_OT_region_edit, KNEADY_OT_region_faces, KNEADY_OT_region_group, KNEADY_OT_command_rig,
            KNEADY_OT_command_bone, KNEADY_OT_switch_kind, KNEADY_OT_drag_kind, KNEADY_OT_command_add,
            KNEADY_OT_command_remove, KNEADY_OT_button_add,
            KNEADY_OT_button_remove, KNEADY_OT_button_move, KNEADY_OT_copy, KNEADY_OT_paste)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    if bpy.app.background:
        register_surface()
    else:
        bpy.app.timers.register(register_surface, first_interval=0.0)


def unregister():
    _unregister_surface()
    for cls in reversed(_classes):
        reg.unregister_class(cls)
