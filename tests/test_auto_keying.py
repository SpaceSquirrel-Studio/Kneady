"""Auto Keying. When Auto Keying is on, a drag keys what it changed,
following the same settings Blender's own transforms follow. So a pose made
with Kneady is kept just as one made with G or R would be."""

import bpy  # type: ignore

import rigs


def _fcurves(id_block):
    """Every F-Curve on an ID's action: from the layered actions of Blender
    4.4 and later, or from the flat list in earlier versions."""
    ad = id_block.animation_data
    if ad is None or ad.action is None:
        return []
    action = ad.action
    if hasattr(action, "layers") and len(action.layers):
        return [fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags
                for fc in bag.fcurves]
    return list(getattr(action, "fcurves", []))


def _curves(id_block):
    """(data path, index) of every F-Curve on an ID's action."""
    return [(fc.data_path, fc.array_index) for fc in _fcurves(id_block)]


def _keys_on(id_block, path):
    return [c for c in _curves(id_block) if c[0] == path]


class _Settings:
    """Set Auto Keying's settings for a test and put them back after."""

    def __init__(self, auto=True, available=False, needed=False, mode="ADD_REPLACE_KEYS", keying_set=False):
        self.wanted = dict(auto=auto, available=available, needed=needed, mode=mode, keying_set=keying_set)

    def __enter__(self):
        ts, ed = bpy.context.scene.tool_settings, bpy.context.preferences.edit
        self.saved = (ts.use_keyframe_insert_auto, ed.use_keyframe_insert_available,
                      ed.use_auto_keyframe_insert_needed, ts.auto_keying_mode, ts.use_keyframe_insert_keyingset)
        w = self.wanted
        ts.use_keyframe_insert_auto = w["auto"]
        ed.use_keyframe_insert_available = w["available"]
        ed.use_auto_keyframe_insert_needed = w["needed"]
        ts.auto_keying_mode = w["mode"]
        ts.use_keyframe_insert_keyingset = w["keying_set"]
        return self

    def __exit__(self, *exc):
        ts, ed = bpy.context.scene.tool_settings, bpy.context.preferences.edit
        (ts.use_keyframe_insert_auto, ed.use_keyframe_insert_available, ed.use_auto_keyframe_insert_needed,
         ts.auto_keying_mode, ts.use_keyframe_insert_keyingset) = self.saved
        return False


def _drag(mesh, region, up=60.0):
    return bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=up)


LOWER_ROTATION = 'pose.bones["Lower"].rotation_quaternion'


def test_off_keys_nothing():
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    rigs.pose_mode(rig)
    with _Settings(auto=False):
        _drag(mesh, region)
    assert not _curves(rig), "keyed with Auto Keying off: %s" % _curves(rig)
    rigs.object_mode()


def test_on_keys_the_driven_bone():
    """With Auto Keying on and Only Insert Available off, the drag keys the
    bone it turned (all four quaternion channels, in the bone's group) and
    nothing else."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    rigs.pose_mode(rig)
    with _Settings(available=False):
        _drag(mesh, region)
    keyed = _keys_on(rig, LOWER_ROTATION)
    assert len(keyed) == 4, "Lower's rotation keyed on %s" % keyed
    assert not [c for c in _curves(rig) if "Upper" in c[0]], "Upper keyed too"
    rigs.object_mode()


def test_only_insert_available_as_blender():
    """Only Insert Available, Blender 5.2's factory setting. A bone not yet
    animated is not keyed, just as Blender's own G keys nothing there. Once
    the bone has a key, the drag keys it."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    rigs.pose_mode(rig)
    with _Settings(available=True):
        _drag(mesh, region)
        assert not _curves(rig), "keyed a bone not yet animated: %s" % _curves(rig)
        rig.pose.bones["Lower"].keyframe_insert("rotation_quaternion", frame=1)
        bpy.context.scene.frame_set(5)
        _drag(mesh, region)
    fcurve_frames = set()
    for fc in _fcurves(rig):
        if fc.data_path == LOWER_ROTATION:
            fcurve_frames |= {round(k.co.x) for k in fc.keyframe_points}
    assert fcurve_frames == {1, 5}, "keys on frames %s, not 1 and 5" % sorted(fcurve_frames)
    rigs.object_mode()


def test_replace_mode_keys_only_existing():
    """Auto Keying's Replace mode: a frame with no key gets none."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    rigs.pose_mode(rig)
    with _Settings(mode="REPLACE_KEYS"):
        _drag(mesh, region)
    assert not _curves(rig), "Replace mode added keys: %s" % _curves(rig)
    rigs.object_mode()


def test_only_active_keying_set():
    """Only Active Keying Set: a bone outside the set is not keyed."""
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower")
    scene = bpy.context.scene
    ks = scene.keying_sets.new(idname="KneadyTest", name="Upper only")
    ks.paths.add(rig, 'pose.bones["Upper"].rotation_quaternion', index=-1)
    scene.keying_sets.active_index = len(scene.keying_sets) - 1
    rigs.pose_mode(rig)
    with _Settings(keying_set=True):
        _drag(mesh, region)
    assert not _keys_on(rig, LOWER_ROTATION), "keyed Lower, outside the active keying set"
    rigs.object_mode()


def test_property_and_object_keys():
    """A property command and an object's own rotation are keyed too."""
    rig, mesh = rigs.arm_rig()
    core = rigs.kneady()
    mesh["Bulge"] = 0.0
    region = core.new_region(mesh, "Both", whole=True)
    button = region.buttons[0]
    button.up.enabled, button.up.kind, button.up.data_path = True, "PROPERTY", '["Bulge"]'
    button.across.enabled, button.across.kind, button.across.axis = True, "ROTATE", "Z"
    button.single = False
    with _Settings():
        bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=40.0, across=40.0)
    paths = {c[0] for c in _curves(mesh)}
    assert '["Bulge"]' in paths, "the property not keyed: %s" % paths
    assert {"rotation_euler"} <= paths, "the object's rotation not keyed: %s" % paths
