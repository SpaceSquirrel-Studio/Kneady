"""View Clipboard: copy a 3D view's position and paste it into another view,
scene, file or Blender session, for recording clips from the same angle.

Greg, 22 November 2026: "Is there a way to save the current viewport position
then in a new scene move the viewport to that same position? It would help
with recording these videos."

A recording helper, not part of Kneady: it lives in dev/, which the extension
build leaves out. Install it on its own (Edit > Preferences > Add-ons, the
arrow at the top right, Install from Disk, this file). It adds Copy View and
Paste View to the 3D View's View menu.

Why the clipboard: a view belongs to the 3D view's area, not to a scene or an
object, so nothing in a file carries it to another file. The clipboard does,
and its text (one line of JSON) can be pasted into a note to keep a view for
later and copied back to use it again.
"""

import json

import bpy
from mathutils import Quaternion

bl_info = {
    "name": "View Clipboard",
    "author": "Space Squirrel Studio",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > View > Copy View / Paste View",
    "description": "Copy the 3D view's position and paste it into another view, scene or file",
    "category": "3D View",
}

# The first key of the copied text, so Paste View knows a copied view from
# whatever else is on the clipboard.
KIND = "blender_view"


def view_of(context):
    """The 3D view the menu was opened in: its space and its view (region_3d).
    A view split into four (Ctrl+Alt+Q) has one per quarter; the one under the
    mouse is region_data."""
    space = context.space_data
    if space is None or space.type != 'VIEW_3D':
        return None, None
    return space, context.region_data or space.region_3d


class VIEW3D_OT_copy_view_clipboard(bpy.types.Operator):
    """Copy where this 3D view looks from, to paste into another view, scene or file"""
    bl_idname = "view3d.copy_view_clipboard"
    bl_label = "Copy View"

    @classmethod
    def poll(cls, context):
        return view_of(context)[1] is not None

    def execute(self, context):
        space, rv3d = view_of(context)
        # In camera view the camera decides what is seen, not the view's own
        # values, which still hold where the view was before entering it.
        # Copying those would paste a view nobody saw.
        if rv3d.view_perspective == 'CAMERA':
            self.report({'WARNING'}, "This is the camera's view: orbit out of it first, "
                                     "or copy the camera itself")
            return {'CANCELLED'}
        # The lens and the clipping are the space's, not the view's, but a
        # different lens frames the same spot differently, so they come along.
        view = {KIND: 1,
                "location": [round(v, 6) for v in rv3d.view_location],
                "rotation": [round(v, 7) for v in rv3d.view_rotation],
                "distance": round(rv3d.view_distance, 6),
                "perspective": rv3d.view_perspective,
                "lens": round(space.lens, 4),
                "clip_start": space.clip_start,
                "clip_end": space.clip_end}
        context.window_manager.clipboard = json.dumps(view)
        self.report({'INFO'}, "View copied")
        return {'FINISHED'}


class VIEW3D_OT_paste_view_clipboard(bpy.types.Operator):
    """Move this 3D view to the view Copy View put on the clipboard"""
    bl_idname = "view3d.paste_view_clipboard"
    bl_label = "Paste View"
    # The view's position is not undone by Ctrl+Z, so this records no undo step.

    @classmethod
    def poll(cls, context):
        return view_of(context)[1] is not None

    def execute(self, context):
        space, rv3d = view_of(context)
        try:
            view = json.loads(context.window_manager.clipboard)
            if not isinstance(view, dict) or KIND not in view:
                raise ValueError
            location, rotation = view["location"], Quaternion(view["rotation"])
            distance = float(view["distance"])
        except (ValueError, KeyError, TypeError):
            self.report({'WARNING'}, "The clipboard holds no copied view: Copy View first")
            return {'CANCELLED'}
        # Setting the perspective first also leaves camera view, if the view
        # is in it, so the values below are the ones seen.
        rv3d.view_perspective = view.get("perspective", 'PERSP')
        rv3d.view_location = location
        rv3d.view_rotation = rotation
        rv3d.view_distance = distance
        if "lens" in view:
            space.lens = view["lens"]
        if "clip_start" in view and "clip_end" in view:
            space.clip_start, space.clip_end = view["clip_start"], view["clip_end"]
        self.report({'INFO'}, "View pasted")
        return {'FINISHED'}


def draw_menu(self, _context):
    layout = self.layout
    layout.separator()
    layout.operator(VIEW3D_OT_copy_view_clipboard.bl_idname, icon='COPYDOWN')
    layout.operator(VIEW3D_OT_paste_view_clipboard.bl_idname, icon='PASTEDOWN')


CLASSES = (VIEW3D_OT_copy_view_clipboard, VIEW3D_OT_paste_view_clipboard)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_view.append(draw_menu)


def unregister():
    bpy.types.VIEW3D_MT_view.remove(draw_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
