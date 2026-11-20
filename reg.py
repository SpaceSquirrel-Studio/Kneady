"""Taking a class back out of Blender when Kneady stops, if it is still there.

A class that another add-on registers under the same name replaces Kneady's,
and Blender unregisters the first one without a word. Tested: an operator, a
panel and a gizmo group were each replaced; a property group was not. So one
of Kneady's classes may already be gone when Kneady stops, and stopping must
carry on past it rather than leave the rest of Kneady registered."""

import bpy  # type: ignore


def unregister_class(cls):
    """bpy.utils.unregister_class, passing over a class already gone."""
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass
