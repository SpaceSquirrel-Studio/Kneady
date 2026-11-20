"""Tutorials:
- a tutorial is data. Its steps' checks and starts are paths Blender
  resolves, never code that is run;
- its practice scene opens as a copy, and the person's own file comes back
  after;
- the panel over the view lays out in any size of view, and its clicks move
  through the steps and clips;
- Kneady's own panel lights the step's fields;
- clips and images hosted online are downloaded, checked and kept."""

import functools
import hashlib
import http.server
import json
import os
import shutil
import tempfile
import threading
import time

import bpy  # type: ignore

import rigs

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "output")
DEMO = os.path.join(HERE, "tutorials")


def _modules():
    t, o = rigs.module("tutorials"), rigs.module("overlay")
    if DEMO not in t.FOLDERS:
        t.FOLDERS.append(DEMO)
    t.end()
    return t, o


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _serve(folder):
    """A web server on this computer, serving `folder`."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=folder))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_media_download_from_where_they_are_hosted():
    """Downloading tutorial media:
    - a clip or image not on this computer is downloaded from the tutorial's
      media_url (or its own url) into Kneady's folder, and kept there;
    - one that is not there, or is not the file its sha256 says, fails and
      says why, and is tried again when asked;
    - a kept file changed since is fetched again;
    - nothing is downloaded with Online Access off, nor from anywhere but
      https (or this computer);
    - a checkout's dev/media folder is used before downloading."""
    t, _o = _modules()
    m = rigs.module("media")
    demo = os.path.join(DEMO, "demo")
    host, empty = tempfile.mkdtemp(), tempfile.mkdtemp()
    for name in ("still.png", "counting.mp4"):
        shutil.copy(os.path.join(demo, name), host)
    cache = os.path.join(OUTPUT, "media_cache")
    shutil.rmtree(cache, ignore_errors=True)
    server = _serve(host)
    base = "http://127.0.0.1:%d/" % server.server_address[1]
    with open(os.path.join(demo, "still.png"), "rb") as f:
        still = f.read()
    was = (m.CACHE, m.online, m.DEV_MEDIA)
    m.CACHE, m.online = cache, (lambda: True)
    m.forget()

    def settle(items, data):
        for _ in range(200):
            found = [m.find("x", empty, data, e)[1] for e in items]
            if m.DOWNLOADING not in found:
                return found
            time.sleep(0.05)
        raise AssertionError("still downloading: %s" % found)

    try:
        data = {"media_url": base}
        items = [{"file": "still.png", "hosted": True, "sha256": hashlib.sha256(still).hexdigest()},
                 {"file": "counting.mp4", "hosted": True}, {"file": "gone.mp4", "hosted": True},
                 {"file": "still.png", "url": base + "still.png?again", "sha256": "0" * 64}]
        # a local file (not marked hosted) is never downloaded, whatever the tutorial's media_url
        assert m.find("x", empty, data, {"file": "counting.mp4"}) == (None, m.MISSING, None) and not m._JOBS
        assert [m.find("x", empty, data, e)[1] for e in items] == [m.DOWNLOADING] * 4
        assert settle(items, data) == [m.READY, m.READY, m.FAILED, m.FAILED]
        path = m.find("x", empty, data, items[0])[0]
        with open(path, "rb") as f:
            assert f.read() == still and os.path.dirname(path) == cache, path
        assert "not found" in m.find("x", empty, data, items[2])[2]
        assert "not the file" in m.find("x", empty, data, items[3])[2]
        m.forget()
        assert m.find("x", empty, data, items[0]) == (path, m.READY, None), "a downloaded file was not kept"
        with open(path, "ab") as f:
            f.write(b"changed")
        m.forget()
        assert m.find("x", empty, data, items[0])[1] == m.DOWNLOADING, "a changed file was used"
        assert settle(items[:1], data) == [m.READY]
        m.retry(data, items[2])
        assert m.find("x", empty, data, items[2])[1] == m.DOWNLOADING, "a failed download was not tried again"
        settle(items, data)
        m.online = lambda: False
        m.forget()
        shutil.rmtree(cache)
        assert m.find("x", empty, data, items[1])[1] == m.OFFLINE and not m._JOBS, "downloaded while offline"
        assert m.url_ok("https://example.com/a.mp4") and not m.url_ok("http://example.com/a.mp4") \
            and not m.url_ok("file:///C:/a.mp4")
        found = "\n".join(t.problems({"format": 1, "title": "x", "media_url": "ftp://x/", "steps": [
            {"text": ["x"], "media": [{"file": "a.mp4", "url": "http://example.com/a.mp4", "sha256": "abc"}]}]}))
        for words in ("media_url is not an https address", "url is not an https address", "sha256 is not 64"):
            assert words in found, found
        found = "\n".join(t.problems({"format": 1, "title": "x", "steps": [
            {"text": ["x"], "media": [{"file": "a.mp4", "hosted": True, "watch": "http://youtube.com/x"}]}]}))
        assert "a.mp4 is hosted, but nowhere" in found and "watch is not an https address" in found, found
        # both certificate stores: the system's own and Blender's certifi
        import certifi  # type: ignore
        import ssl
        both = m._context().cert_store_stats()["x509_ca"]
        alone = ssl.create_default_context(cafile=certifi.where()).cert_store_stats()["x509_ca"]
        system = ssl.create_default_context().cert_store_stats()["x509_ca"]
        assert both >= alone and both >= system and both > 0, (both, alone, system)
        m.DEV_MEDIA = os.path.dirname(host)
        assert m.find(os.path.basename(host), empty, data, items[1]) == (os.path.join(host, "counting.mp4"),
                                                                          m.READY, None)
    finally:
        server.shutdown()
        m.CACHE, m.online, m.DEV_MEDIA = was
        m.forget()


def test_shared_scenes_are_as_named():
    """The practice scenes tutorials share (tutorials/_scenes, made by
    dev/scenes):
    - open;
    - hold what the tutorials name: the cube; the shape cube's Sphere key and
      Twist input; the arm's and the mannequin's rig with its IK/FK switch,
      and FK toggling it; the mannequin's Head and Chest;
    - carry no Python (no text, and every driver a simple expression);
    - were saved by the oldest Blender Kneady supports."""
    t, _o = _modules()
    scenes = os.path.join(os.path.dirname(t.FOLDERS[0]), "tutorials", "_scenes")
    wants = {"cube": ["Cube", "Camera", "Light"], "cube_region": ["Cube"], "shape_cube": ["Cube"],
             "shape_cube_region": ["Cube"], "shape_cube_controls": ["Cube"], "shape_cube_menu": ["Cube"],
             "arm": ["Arm", "Rig"], "arm_forearm": ["Arm", "Rig"], "arm_toggle": ["Arm", "Rig"],
             "arm_look": ["Arm", "Rig"], "arm_on_item": ["Arm", "Rig"], "mannequin": ["Mannequin", "Rig"],
             "mannequin_controls": ["Mannequin", "Rig"], "mannequin_edited": ["Mannequin", "Rig"],
             "mannequin_reused": ["Mannequin", "Rig"]}
    assert sorted(f[:-6] for f in os.listdir(scenes) if f.endswith(".blend")) == sorted(wants), os.listdir(scenes)
    for name, objects in wants.items():
        bpy.ops.wm.open_mainfile(filepath=os.path.join(scenes, name + ".blend"), load_ui=False, use_scripts=False)
        assert tuple(bpy.data.version[:2]) <= (4, 2), "%s saved by %s" % (name, bpy.data.version)
        missing = [o for o in objects if o not in bpy.data.objects]
        assert not missing, "%s lacks %s" % (name, missing)
        assert not bpy.data.texts, "%s carries %s" % (name, [x.name for x in bpy.data.texts])
        for obj in bpy.data.objects:
            for fc in (obj.animation_data.drivers if obj.animation_data else []):
                assert fc.driver.type != "SCRIPTED" or fc.driver.is_simple_expression, \
                    "%s: %s's driver %s runs Python" % (name, obj.name, fc.data_path)
        if name == "shape_cube_region":               # the shape cube, all of it one region
            cube = bpy.data.objects["Cube"]
            assert cube.kneady.regions[0].whole and bpy.context.scene.kneady_on
        if name == "shape_cube_controls":             # where Drive More Than Bones leaves off
            button = bpy.data.objects["Cube"].kneady.regions[0].buttons[0]
            assert (button.up.kind, button.up.more[0].kind, button.across.input) == ("PROPERTY", "SCALE", "Twist")
        if name == "shape_cube_menu":                 # Build a Menu's scene, its menu working
            used = bpy.data.objects["Cube"].kneady.regions[0].buttons
            assert [b.name for b in used[1:3]] == ["Round", "Twist"] and used[0].opens_menu
            assert used[1].menu_parent == used[0].uid and used[2].across.input == "Twist"
        if name in ("shape_cube", "shape_cube_region", "shape_cube_controls", "shape_cube_menu"):
            cube = bpy.data.objects["Cube"]
            assert "Sphere" in cube.data.shape_keys.key_blocks and "Twist" in cube.modifiers
            assert cube.modifiers["Twist"].node_group.interface.items_tree.get("Twist") is not None
        if name == "cube_region":                     # where Quick Start leaves off
            cube = bpy.data.objects["Cube"]
            region = cube.kneady.regions[0]
            assert region.name == "Region 1" and bpy.context.scene.kneady_on, region.name
            assert list(t.core.face_tags(cube.data)).count(region.id) == 1, "not one face tagged"
        if name == "arm_forearm":                     # Bend in FK, Reach in IK, the arm in IK
            used = bpy.data.objects["Arm"].kneady.regions[0].buttons
            assert (used[0].name, used[0].up.bone, used[1].name, used[1].up.bone) == (
                "Bend", "forearm_fk.L", "Reach", "hand_ik.L")
        if name == "arm_toggle":                      # where Toggles and Show When leaves off
            used = bpy.data.objects["Arm"].kneady.regions[0].buttons
            assert [b.name for b in used[:3]] == ["Bend", "Reach", "FK"] and used[2].action == "TOGGLE"
            assert used[2].switch.data_path.endswith('["IK_FK"]') and used[2].switch.target.name == "Rig"
            assert [(b.show_when, b.when_toggle) for b in used[:2]] == [("ON", "FK"), ("OFF", "FK")]
        if name == "arm_look":                        # where The Look of Your Buttons leaves off
            region = bpy.data.objects["Arm"].kneady.regions[0]
            used = region.buttons
            assert region.arrange == "COLUMN" and used[2].icon_type == "TEXT", region.arrange
            assert [b.shape for b in used[:2]] == ["SQUARE", "SQUARE"] and not any(b.placed for b in used)
        if name == "arm_on_item":                     # where Buttons on the Item leaves off
            region = bpy.data.objects["Arm"].kneady.regions[0]
            reach = region.buttons[1]
            assert reach.placed and reach.place_set and reach.handle == "BUTTON", reach.handle
            assert region.behind == "GHOST" and not region.buttons[0].placed, region.behind
        if name == "mannequin_controls":              # Viewport Edit's scene: Head and Chest, Spare a menu of two
            regions = bpy.data.objects["Mannequin"].kneady.regions
            head, chest = ([b.name for b in t.core.buttons_of(r)] for r in regions)
            assert [r.name for r in regions] == ["Head", "Chest"] and head == ["Nod", "Turn"], head
            assert chest == ["Bend", "Twist", "Spare", "Spare 1", "Spare 2"], chest
            spare = regions[1].buttons[2]
            assert spare.opens_menu and all(b.menu_parent == spare.uid for b in regions[1].buttons[3:5])
            assert [b.up.bone or b.across.bone for b in regions[0].buttons[:2]] == ["head", "head"]
            assert bpy.data.objects["Rig"].hide_get() and bpy.context.scene.kneady_on
        if name == "mannequin_edited":                # where Viewport Edit leaves off, and the Hips
            regions = bpy.data.objects["Mannequin"].kneady.regions
            shown = [[b.name for b in t.core.buttons_of(r)] for r in regions]
            assert [r.name for r in regions] == ["Head", "Chest", "Hips"], [r.name for r in regions]
            assert shown == [["Nod", "Tilt", "Turn"], ["Bend", "Twist"], ["Button 1"]], shown
            tilt, empty = regions[0].buttons[1], regions[2].buttons[0]
            assert not any(d.enabled for d in (tilt.up, tilt.across, empty.up, empty.across)), "drives something"
            assert bpy.data.objects["Rig"].hide_get() and bpy.context.scene.kneady_on
        if name == "mannequin_reused":                # where Copy and Reuse leaves off
            head, _chest, hips = bpy.data.objects["Mannequin"].kneady.regions
            nod, tilt, turn = head.buttons[:3]
            assert nod.opens_menu and tilt.menu_parent == nod.uid and not turn.menu_parent
            assert (tilt.across.axis, tilt.across.bone, turn.across.axis) == ("Z", "head", "Y"), tilt.across.axis
            assert [b.name for b in hips.buttons[:2]] == ["Bend", "Twist"], [b.name for b in hips.buttons[:2]]
            assert (hips.buttons[0].up.bone, hips.buttons[1].across.bone) == ("hips", "hips")
            assert not turn.tip_text and not len(turn.tip_rows), "Turn's tip is the tutorial's to write"
        if name in ("arm", "arm_forearm", "arm_toggle", "arm_look", "arm_on_item", "mannequin",
                    "mannequin_controls", "mannequin_edited", "mannequin_reused"):
            rig = bpy.data.objects["Rig"]
            assert "IK_FK" in rig.pose.bones["upper_arm_parent.L"], name
            body = bpy.data.objects[objects[0]]
            assert body.parent == rig and body.modifiers[0].type == "ARMATURE", name
    bpy.ops.wm.read_homefile(use_empty=True)


def _there_or_added(t, context, path):
    """Whether a step's path is in its practice scene, or names an item of a
    collection that is there - an item the tutorial adds, such as Drive More
    Than Bones' second command on a drag, up.more[0]."""
    import re
    try:
        t.owner_and_name(context, path)
        return True
    except LookupError:
        pass
    for m in reversed(list(re.finditer(r"\[(\d+)\]", path))):
        try:
            owner, name, _index = t.owner_and_name(context, path[:m.start()])
        except LookupError:
            continue
        return isinstance(getattr(owner, name), bpy.types.bpy_prop_collection)
    return False


def test_shipped_tutorials_are_well_formed():
    """Every tutorial Kneady ships reads without a problem, and every path its
    steps check, set or light, and every object they select, is there in its
    practice scene."""
    t, _o = _modules()
    found = {tid: (folder, data) for tid, folder, data in t.available()}
    assert "getting_started" in found and "demo" in found, sorted(found)
    for tid, (folder, data) in found.items():
        assert t.problems(data, folder) == [], "%s: %s" % (tid, t.problems(data, folder))
    folder, data = found["getting_started"]
    assert t.missing_media(data, folder) == ["01_turn_on.mp4", "02_hover.mp4", "03_bend.mp4"], \
        t.missing_media(data, folder)
    for tid, (folder, data) in found.items():
        if not data.get("practice"):
            continue
        bpy.ops.wm.open_mainfile(filepath=t.practice_path(folder, data["practice"]), load_ui=False,
                                 use_scripts=False)
        context = bpy.context
        for k, step in enumerate(data["steps"]):
            paths = list(step.get("highlight", [])) + [c["path"] for c in step.get("done_when", []) if "path" in c]
            paths += [item["path"] for item in step.get("start", {}).get("set", [])]
            for path in paths:
                assert _there_or_added(t, context, path), "%s, step %d: %s is not there" % (tid, k + 1, path)
            for name in step.get("start", {}).get("select", []) + [step.get("start", {}).get("active")]:
                assert not name or name in bpy.data.objects, "%s, step %d names %s" % (tid, k + 1, name)
    bpy.ops.wm.read_homefile(use_empty=True)


def test_media_out_of_date_are_found():
    """A clip or image records the Blender and Kneady versions it was made
    in, so one that may show an older interface is found after an update.
    The shared set's files are checked too, each file once."""
    t, _o = _modules()
    data = {"media": [{"file": "s.png", "recorded": {"blender": "5.2", "kneady": "0.1.0"}}],
            "steps": [{"media": [{"file": "a.mp4", "recorded": {"blender": "5.2", "kneady": "0.1.0"}},
                                 {"file": "b.mp4", "recorded": {"blender": "4.2", "kneady": "0.1.0"}},
                                 {"file": "c.mp4"}]},
                      {"media": [{"file": "a.mp4", "recorded": {"blender": "4.2"}}]}]}
    assert t.stale_media(data, blender="5.2", kneady="0.1.0") == [
        ("b.mp4", "recorded in Blender 4.2"), ("c.mp4", "no recorded versions")], t.stale_media(data, "5.2", "0.1.0")
    assert [f for f, _w in t.stale_media(data, blender="5.2", kneady="0.2.0")] == ["s.png", "a.mp4", "b.mp4",
                                                                                    "c.mp4"]
    assert t.kneady_version() is not None, "no version read from the manifest"


def test_problems_are_named():
    t, _o = _modules()
    bad = {"format": 2, "media": [{"file": "s.png", "paragraph": -1}], "steps": [
        {"title": "x", "text": "not a list", "media": [{"label": "no file"}, {"file": "a.mp4", "paragraph": 3},
                                                      {"file": "b.png", "seconds": 0}],
         "done_when": [{"path": "bpy.app.binary_path", "is": "x"}, {"path": "scene.frame_current"},
                       {"mode": "POSE", "active": "Arm"}],
         "highlight": ["os.system"], "start": {"teleport": True, "view": {"rotation": [1, 0, 0]}},
         "surprise": 1}]}
    found = "\n".join(t.problems(bad))
    for words in ("format is 2", "no title", "text is not a list", "media 1: no file", "paragraph 3",
                  "the shared media, media 1: paragraph -1", "media 3: seconds",
                  "'bpy.app.binary_path' does not start", "scene.frame_current needs one test",
                  "mode stands alone", "cannot highlight 'os.system'", "unknown teleport", "unknown surprise",
                  "view needs"):
        assert words in found, "%r not in:\n%s" % (words, found)


def test_paths_are_resolved_never_run():
    """A path is walked by Blender's path_resolve from a known start: what
    is not a property is not found, and nothing in it runs."""
    t, _o = _modules()
    context = bpy.context
    rig, _mesh = rigs.arm_rig()
    assert t.resolve(context, "scene.kneady_on") is False
    assert t.resolve(context, 'objects["ArmRig"].pose.bones["Lower"].head')[2] == 1.0
    owner, name, index = t.owner_and_name(context, 'objects["ArmRig"].location[2]')
    assert (owner, name, index) == (rig, "location", 2), (owner, name, index)
    t.write(context, 'objects["ArmRig"].location[2]', 0.5)
    assert abs(rig.location.z - 0.5) < 1e-6
    for path in ('__import__("os").system("echo x")', "scene.__class__", 'scene.path_resolve("x")',
                 "bpy.data", 'objects["Nobody"].location', "scene.kneady_on.real"):
        try:
            t.resolve(context, path)
            t.owner_and_name(context, path)
        except LookupError:
            continue
        raise AssertionError("%s was found" % path)


def test_conditions():
    t, _o = _modules()
    context = bpy.context
    rig, mesh = rigs.arm_rig()
    lower = 'objects["ArmRig"].pose.bones["Lower"].rotation_quaternion'
    step = {"done_when": [{"path": lower, "changed": True}]}
    base = t.baseline_of(context, step)
    assert not t.met(context, step["done_when"][0], base)
    rig.pose.bones["Lower"].rotation_quaternion = (0.9, 0.3, 0.0, 0.0)
    assert t.met(context, step["done_when"][0], base)
    assert t.met(context, {"path": "scene.kneady_on", "is": False})
    assert t.met(context, {"path": "scene.kneady_on", "is_not": True})
    assert t.met(context, {"path": "scene.frame_end", "at_least": 250})
    assert not t.met(context, {"path": "scene.frame_end", "at_most": 10})
    assert t.met(context, {"path": "scene.objects", "count_at_least": 2})
    assert t.met(context, {"path": 'objects["ArmRig"].location', "is": [0, 0, 0]})
    assert not t.met(context, {"path": 'objects["Nobody"].location', "is": [0, 0, 0]})
    for o in context.view_layer.objects:
        o.select_set(o == mesh)
    context.view_layer.objects.active = mesh
    assert t.met(context, {"active": "Arm"}) and t.met(context, {"selected": ["Arm"]})
    assert not t.met(context, {"selected": ["Arm", "ArmRig"]})
    assert t.met(context, {"mode": "OBJECT"})


def test_practice_scene_and_back():
    """Start opens a copy of the practice scene with the first step's start
    applied. The steps tick off as they are done. Return to My File opens
    the person's own file again, untouched."""
    t, _o = _modules()
    os.makedirs(OUTPUT, exist_ok=True)
    mine = os.path.join(OUTPUT, "my_file.blend")
    bpy.data.objects.new("Mine", None)
    bpy.context.scene.collection.objects.link(bpy.data.objects["Mine"])
    bpy.ops.wm.save_as_mainfile(filepath=mine)
    try:
        assert bpy.ops.kneady.tutorial_start(tutorial="getting_started") == {"FINISHED"}
        assert t.active() and t.S["id"] == "getting_started", "the tutorial did not begin"
        folder, _data = t.find("getting_started")
        assert os.path.dirname(bpy.data.filepath) != folder and "Arm" in bpy.data.objects, bpy.data.filepath
        assert t.S["user_file"] == mine and t.can_return(), t.S["user_file"]
        context = bpy.context
        assert context.scene.kneady_on is False and context.view_layer.objects.active.name == "Arm"
        t.check(context)
        assert not t.done(), "done before it was done"
        context.scene.kneady_on = True
        t.check(context)
        assert t.done(), "turning Kneady on did not finish the first step"
        t.next_step(context)
        t.next_step(context)
        assert t.S["step"] == 2 and not t.done()
        bpy.data.objects["ArmRig"].pose.bones["Lower"].rotation_quaternion = (0.9, 0.3, 0.0, 0.0)
        t.check(context)
        assert t.done(), "bending the elbow did not finish its step"
        t.enter(context, 2)                                 # Reset: the step's start again
        assert tuple(bpy.data.objects["ArmRig"].pose.bones["Lower"].rotation_quaternion) == (1, 0, 0, 0)
        assert not t.done(), "a step reset stays done"
        assert bpy.ops.kneady.tutorial_return() == {"FINISHED"}
        assert not t.active() and bpy.data.filepath == mine and "Mine" in bpy.data.objects, bpy.data.filepath
    finally:
        t.end()
        t.S["pending"] = None


def test_another_file_ends_it():
    t, _o = _modules()
    assert bpy.ops.kneady.tutorial_start(tutorial="getting_started") == {"FINISHED"}
    assert t.active()
    bpy.ops.wm.read_homefile(use_empty=True)
    assert not t.active(), "the tutorial outlived its practice scene"


def test_layout_fits_any_view():
    """The panel's layout, in any size of view:
    - every part sits inside the panel, and the panel inside the view;
    - the clip is 9:16 and shrinks before the text does;
    - there is a dot for each clip up to five, and a count past that;
    - folded, the panel is a tab."""
    _t, o = _modules()
    for width, height, scale in ((1400, 860, 1.0), (1400, 860, 1.25), (900, 520, 1.0), (300, 400, 2.0)):
        for n in (0, 1, 3, 7):
            r = o.layout(width, height, scale, n, 0, True)
            card = r["card"]
            assert 0 <= card[0] < card[2] <= width and 0 <= card[1] < card[3] <= height, (width, height, card)
            for key, rect in r.items():
                rects = rect if key == "dots" else [rect]
                for x0, y0, x1, y1 in rects:
                    assert card[0] - 1 <= x0 <= x1 <= card[2] + 1 and card[1] - 1 <= y0 <= y1 <= card[3] + 1, \
                        (key, rect, card)
            if n and height / scale < 300:
                assert "video" not in r, "a clip in a view too small for it"
            elif n:
                v = r["video"]
                assert abs((v[3] - v[1]) / (v[2] - v[0]) - 16.0 / 9.0) < 1e-6
                assert ("dots" in r) == (n <= o.DOTS_MAX) and ("count" in r) == (n > o.DOTS_MAX)
                if height * 1.0 / scale >= 800:
                    text = r["text"]
                    assert text[3] - text[1] >= o.MIN_TEXT * scale - 1, (width, height, scale, text)
            else:
                assert "video" not in r and "bar" not in r
    folded = o.layout(1400, 860, 1.0, 3, 0, True, folded=True)
    assert set(folded) == {"card", "tab"}
    # Pause and Loop inside the arrows, clear of five dots; the phone in the
    # title row; the QR code in place of the clip and the text
    for scale in (1.0, 1.25, 2.0):
        r = o.layout(1400 * scale, 860 * scale, scale, 5, 0, False, pause=True, loop=True, phone=True)
        bar, dots, head = r["bar"], r["dots"], r["head"]
        assert r["prev"][2] < r["pause"][0] < r["pause"][2] < dots[0][0], (r["pause"], dots[0])
        assert dots[-1][2] < r["loop"][0] < r["loop"][2] < r["next_clip"][0], (r["loop"], dots[-1])
        assert r["pause"][1] == bar[1] and r["loop"][3] == bar[3]
        assert head[1] == r["phone"][1] and r["phone"][2] <= r["fold"][0], (r["phone"], r["fold"])
        q = o.layout(1400 * scale, 860 * scale, scale, 5, 0, False, pause=True, loop=True, phone=True, qr=True)
        assert "qr" in q and not {"video", "bar", "text", "dots"} & set(q), sorted(q)
        assert q["qr"][3] == head[1] and q["qr"][1] == q["foot"][3]
        # A program's parts. Its strips go between the clip and its controls,
        # in order. Its buttons sit small in the clip's corner, side by side,
        # or wide and low in it, with the Watch button above them. Watch is
        # gone while the program is busy.
        e = o.layout(1400 * scale, 860 * scale, scale, 5, 0, False, pause=True, loop=True,
                     rows=[("one", 32), ("two", 20)])
        assert e["one"][3] == e["video"][1] and e["one"][1] == e["two"][3] and e["two"][1] == e["bar"][3], \
            (e["one"], e["two"], e["video"], e["bar"])
        assert e["one"][0] == e["card"][0] and e["one"][2] == e["card"][2]
        assert abs(e["one"][3] - e["one"][1] - 32 * scale) < 1e-6 and abs(e["two"][3] - e["two"][1] - 20 * scale) < 1e-6
        c = o.layout(1400 * scale, 860 * scale, scale, 5, 0, False, pause=True,
                     buttons=[("first", "corner"), ("second", "corner")])
        v, a, b = c["video"], c["first"], c["second"]
        assert v[0] < b[0] < b[2] < a[0] < a[2] <= v[2] and v[1] < a[1] < a[3] <= v[3] and a[2] - a[0] < 30 * scale, \
            (v, a, b)
        w = o.layout(1400 * scale, 860 * scale, scale, 5, 0, False, watch=True, buttons=[("wide", "low")])
        assert w["wide"][2] - w["wide"][0] > 60 * scale and w["watch"][1] > w["wide"][3], (w["wide"], w["watch"])
        r = o.layout(1400 * scale, 860 * scale, scale, 5, 0, False, pause=True, watch=True, busy=True)
        assert "watch" not in r and "video" in r
    assert "qr" not in o.layout(1400, 860, 1.0, 5, 0, False, qr=True), "a QR code without a playlist"


def test_a_program_adds_to_the_panel():
    """A program's part of the panel (overlay.add_part):
    - a click on its key, or on one of its controls ("<key>/<name>"), is its
      press;
    - a press that asks to follow the mouse, with no mouse to follow, is let
      go at once;
    - while busy, it has the panel;
    - its note is shown under the clip;
    - a part that fails is reported in the console, and never takes the
      panel down."""
    t, o = _modules()
    context = bpy.context
    log = []
    busy = [False]

    def press(_context, key, rects, at):
        log.append(("press", key, rects, at))
        return o.DRAG if key == "strip" else ("pressed " + key)

    part = {"key": "strip", "row": lambda _c: 30, "busy": lambda: busy[0], "press": press,
            "release": lambda keep: log.append(("release", keep)), "note": lambda: ("Said", o.DONE)}
    broken = {"key": "broken", "note": lambda: 1 / 0, "busy": lambda: 1 / 0}
    o.add_part(part)
    o.add_part(dict(part))                                    # the same key again: not added twice
    o.add_part(broken)
    t.begin(context, "demo")
    try:
        assert [p["key"] for p in o.PARTS].count("strip") == 1
        assert o.part_of("strip") is part and o.part_of("strip/stop") is part and o.part_of("next") is None
        assert o.act(context, "strip") == "" and log == [("press", "strip", {}, None), ("release", True)], log
        assert o.act(context, "strip/stop") == "pressed strip/stop" and log[-1][1] == "strip/stop"
        assert o._note() == ("Said", o.DONE), o._note()
        assert o.busy_part() is None
        busy[0] = True
        assert o.busy_part() is part
        clip = t.S["clip"]
        o.act(context, "next_clip")                           # the panel's own parts still answer a script
        assert t.S["clip"] != clip
    finally:
        o.remove_part("strip")
        o.remove_part("broken")
        t.end()
    assert not o.PARTS and o.part_of("strip") is None


def test_text_wraps_and_scrolls():
    _t, o = _modules()
    words = "Breadcrumbs read like this: Properties > Modifiers > Kneady > Speed. " * 6
    lines = o.wrap(words, 11.0, 200.0)
    assert len(lines) > 3 and " ".join(lines).split() == words.split(), lines
    import blf  # type: ignore
    blf.size(0, 11.0)
    assert all(blf.dimensions(0, line)[0] <= 200.0 for line in lines if " " in line)
    items, total = o.text_items({"title": "A title", "text": [words, "Short."]}, 200.0, 1.0)
    assert [i["para"] for i in items] == [None, 0, 1] and total > items[2]["y"] > items[1]["y"]


def test_panel_clicks_and_highlight():
    """The panel's clicks: Next and Back through the steps (Back starts its
    step again), a clip's dot, pause, fold and its tab, and close. Kneady's
    panel lights the field the step is about, and nothing else."""
    t, o = _modules()
    context = bpy.context
    context.scene.kneady_on = True
    t.begin(context, "demo")
    try:
        assert t.S["step"] == 0 and context.scene.kneady_on is False, "the start was not applied"

        class _Layout:
            def __init__(self, log):
                self.log, self.alert = log, False

            def row(self, **_k):
                child = _Layout(self.log)
                child.alert = self.alert
                return child

            column = box = row

            def prop(self, data, name, **_k):
                self.log.append((name, self.alert))

        log = []
        lit = t.emphasize(_Layout(log), context)
        lit.row().prop(context.scene, "kneady_on")
        lit.column().prop(context.scene, "kneady_labels")
        assert log == [("kneady_on", True), ("kneady_labels", False)], log
        o.act(context, "dot:1")
        assert t.S["clip"] == 1 and t.clip()["paragraph"] == 1
        for _ in range(3):
            o.act(context, "next_clip")
        assert t.S["clip"] == 0, "the clips do not go round"
        o.act(context, "video")
        assert t.S["playing"] is False
        o.act(context, "next")
        assert t.S["step"] == 1 and t.clips() == []
        context.scene.kneady_on = True
        o.act(context, "back")
        assert t.S["step"] == 0 and context.scene.kneady_on is False, "Back did not start its step again"
        o.act(context, "fold")
        assert t.S["shown"] is False and set(o.layout(800, 600, 1.0, 3, 0, False, folded=True)) == {"card", "tab"}
        o.act(context, "tab")
        assert t.S["shown"] is True
        o.act(context, "close")
        assert not t.active()
    finally:
        t.end()


def test_own_media_or_the_shared_set():
    """Greg asked for this: "Each page should be able to have a selection of
    videos/images or all share a single set". A step has its own media, none
    (`[]`), or, with no media key at all, the tutorial's shared set. The
    shared set keeps its place from one sharing step to the next, and starts
    over when coming from a step with media of its own. The same file twice
    in a row is two items. An image is held for its seconds, then the next
    item plays."""
    t, o = _modules()
    context = bpy.context
    t.begin(context, "demo")
    try:
        assert [m["file"] for m in t.clips()] == ["counting.mp4", "counting.mp4", "not_recorded.mp4", "still.png"]
        assert not t.shares()
        t.enter(context, 1)
        assert t.clips() == [] and not t.shares(), "an empty list is no media, not the shared set"
        t.enter(context, 2)
        assert t.shares() and [m["file"] for m in t.clips()] == ["counting.mp4", "still.png"]
        assert t.S["clip"] == 0, "come from a step of its own, the shared set starts over"
        t.set_clip(1)
        key = o._wanted()[1]
        t.next_step(context)
        assert t.S["step"] == 3 and t.S["clip"] == 1 and o._wanted()[1] == key, \
            "the shared set lost its place from one sharing step to the next"
        t.back_step(context)
        assert t.S["step"] == 2 and t.S["clip"] == 1
        t.back_step(context)
        t.next_step(context)
        assert t.S["clip"] == 0, "come back from a step of its own, the shared set starts over"
        # the same file twice in a row: two items, the second started over
        t.enter(context, 0)
        first = o._wanted()[1]
        t.set_clip(1)
        assert o._wanted()[0] == t.clip_path() and o._wanted()[1] != first
        # an image: shown still, held its seconds, then the next item
        t.enter(context, 2)
        t.set_clip(1)
        o._play()
        assert o.P["image"] is not None and o.P["still"] and o.P["seconds"] == 2, (o.P["image"], o.P["still"])
        assert not t.is_video(t.clip()) and t.is_video({"file": "x.MP4"})
        o._play()
        assert t.S["clip"] == 1, "an image moved on before its seconds"
        o.P["t0"] -= 3.0
        o._play()
        assert t.S["clip"] == 0, "an image held past its seconds"
    finally:
        t.end()


def test_learn_starts_tutorials_from_the_top():
    """Greg asked for this: "I want to be able to start a tutorial from the
    top of the Kneady pane when in Learn mode. Not present outside of learn
    mode. A dropdown or menu to select from available tutorials."
    - at Learn the top panel shows the menu and the editor's switch;
    - at Inform there is no panel at all;
    - while a tutorial runs, its step and Return or End show, at any level.
    The menu lists every tutorial."""
    t, _o = _modules()
    tips = rigs.module("tips")
    context = bpy.context

    class _Layout:
        def __init__(self, log):
            self.log = log

        def _child(self, **_k):
            return _Layout(self.log)

        row = column = box = _child

        def label(self, text="", **_k):
            self.log.append(("label", text))

        def operator(self, idname, text="", **_k):
            self.log.append(("op", idname, text))
            return type("Op", (), {})()

        def menu(self, idname, text="", **_k):
            self.log.append(("menu", idname, text))

        def prop(self, _data, name, *_a, **_k):
            self.log.append(("prop", name))

    was = tips.level()
    try:
        for level, shows in (("LEARN", True), ("INFORM", False)):
            tips._LEVEL["value"] = level
            assert t.KNEADY_PT_tutorials.poll(context) == shows, level
            log = []
            t.draw(_Layout(log), context)
            assert (("menu", "KNEADY_MT_tutorials", "Start a Tutorial") in log) == shows, (level, log)
            assert (("prop", "kneady_tutorial_edit") in log) == shows, (level, log)
        menu = _Layout([])
        t.KNEADY_MT_tutorials.draw(type("M", (), {"layout": menu})(), context)
        titles = [e[2] for e in menu.log if e[:2] == ("op", "kneady.tutorial_start")]
        number = t.number_of("demo")
        assert "%d. Demo of the Player" % number in titles and any(x.endswith(". Getting Started") for x in titles), \
            titles
        first = t.first_number(t.listed()[0][1])         # 0 when tutorial 0 (Learn, Inform and Quiet) is first
        assert [x.split(".")[0] for x in titles] == [str(k) for k in range(first, first + len(titles))], titles
        t.begin(context, "demo")
        tips._LEVEL["value"] = "INFORM"
        assert t.KNEADY_PT_tutorials.poll(context), "a tutorial going is hidden outside Learn"
        log = []
        t.draw(_Layout(log), context)
        assert ("label", "%d. Demo of the Player, 1 of 4" % number) in log and \
            any(e[:2] == ("op", "kneady.tutorial_end") for e in log), log
    finally:
        tips._LEVEL["value"] = was
        t.end()


def _editor_folder():
    """A folder of its own to make tutorials in, for a test - never Kneady's
    own tutorials/."""
    t = rigs.module("tutorials")
    folder = tempfile.mkdtemp(prefix="kneady_authored_")
    rigs.module("tutorial_edit").RECYCLE = False             # never into the person's Recycle Bin
    was = (t._AUTHOR["folder"], t._AUTHOR["read"], t.CONFIG)
    t.CONFIG = os.path.join(folder, "config.json")
    t.set_author_folder(folder)
    return folder, was


def _editor_folder_back(was):
    t = rigs.module("tutorials")
    t._AUTHOR["folder"], t._AUTHOR["read"], t.CONFIG = was


def test_editor_keeps_everything_a_tutorial_holds():
    """Loaded into the editor and written back, every tutorial is what it was:
    steps, text, a step's own media or none or the shared set, highlights,
    every kind of check, starts with views and values."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    pg = bpy.context.window_manager.kneady_tutorial
    for tid, _folder, data in t.available():
        e.to_props(data, pg)
        back = e.from_props(pg)
        assert back == e.canonical(data), "%s changed going through the editor:\n%s\n%s" % (tid, back,
                                                                                             e.canonical(data))
        assert e.canonical(back) == back, "%s: what the editor writes is not in canonical form" % tid
    every = {"format": 1, "title": "All", "order": 3, "playlist": "https://www.youtube.com/playlist?list=PLx",
             "media": [{"file": "s.png", "paragraph": 0, "seconds": 2, "hold": True}],
             "steps": [{"title": "a", "text": ["x", "y"],
                        "media": [{"file": "a.mp4", "label": "L", "paragraph": 1, "url": "https://h/a.mp4",
                                   "hold": True, "trim": [3, 0],
                                   "watch": "https://youtube.com/shorts/abc",
                                   "sha256": "0" * 64, "recorded": {"blender": "5.2", "kneady": "0.1.0"},
                                   "show_me": {"properties": "MODIFIER", "object": "Arm", "modifier": "GN"}}],
                        "highlight": ["scene.kneady_on"],
                        "done_when": [{"path": "scene.kneady_on", "is": True}, {"mode": "POSE"},
                                      {"operator": "kneady.drag", "with": {"target": "Arm", "region": 1, "button": 0},
                                       "moved": True},
                                      {"operator": "object.mode_set"}, {"hovered": "Forearm", "object": "Arm"},
                                      {"hovered": "Upper Arm"},
                                      {"active": "Arm"}, {"selected": ["Arm", "Rig"]},
                                      {"path": 'objects["Rig"].location', "changed": True}],
                        "start": {"mode": "POSE", "select": [], "active": "Rig",
                                  "set": [{"path": "scene.frame_current", "value": 4}],
                                  "view": {"location": [0, 0, 1], "rotation": [1, 0, 0, 0], "distance": 6,
                                           "perspective": "ORTHO"}, "sidebar": "Kneady"}},
                       {"title": "b", "text": ["z"], "media": []},
                       {"title": "c", "text": ["w"]}]}
    e.to_props(every, pg)
    assert e.from_props(pg) == e.canonical(every), (e.from_props(pg), e.canonical(every))


def test_editor_paths_from_copy_full_data_path():
    e = rigs.module("tutorial_edit")
    for copied, path in (("bpy.data.scenes[\"Scene\"].kneady_on", "scene.kneady_on"),
                         ("bpy.context.scene.kneady_on", "scene.kneady_on"),
                         ("bpy.data.objects[\"Arm\"].location[2]", 'objects["Arm"].location[2]'),
                         ("bpy.data.objects['Arm'].modifiers['GN']", 'objects["Arm"].modifiers["GN"]'),
                         ("bpy.data.window_managers[\"WinMan\"].kneady_help", "window_manager.kneady_help"),
                         ("bpy.context.object.location", "object.location"),
                         ("  scene.frame_end ", "scene.frame_end")):
        assert e.normalize(copied) == path, (copied, e.normalize(copied))


def test_editor_makes_saves_and_deletes_tutorials():
    """The editor's New, Save, Try and Delete:
    - New makes a tutorial in the folder tutorials are made in, and the menu
      lists it at once;
    - an edit, once saved, is in its tutorial.json;
    - Try This Step plays it from the step picked;
    - one of Kneady's own tutorials, edited, is saved as a copy in that
      folder with its practice scene, the original untouched;
    - Delete takes a tutorial away, and refuses one outside the folder."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    context = bpy.context
    wm = context.window_manager
    folder, was = _editor_folder()
    try:
        assert t.author_folder() == folder
        assert bpy.ops.kneady.tutorial_new(title="My First One") == {"FINISHED"}
        pg = wm.kneady_tutorial
        assert pg.id == "my_first_one" and os.path.isdir(os.path.join(folder, "my_first_one"))
        assert "my_first_one" in [tid for tid, _f, _d in t.available()]
        assert t.problems(e.from_props(pg), pg.folder) == []
        pg.title = "Renamed"
        assert e.changed(pg)
        bpy.ops.kneady.tutorial_list(which="STEPS", action="ADD")
        pg.steps[1].title = "Second"
        pg.steps[1].checks.add()
        pg.steps[1].checks[0].path, pg.steps[1].checks[0].value = "scene.kneady_on", "true"
        assert bpy.ops.kneady.tutorial_save() == {"FINISHED"} and not e.changed(pg)
        saved = t.load(os.path.join(folder, "my_first_one", "tutorial.json"))
        assert saved["title"] == "Renamed" and saved["steps"][1]["done_when"] == [
            {"path": "scene.kneady_on", "is": True}], saved
        pg.step_index = 1
        assert bpy.ops.kneady.tutorial_try() == {"FINISHED"}
        assert t.active() and t.S["id"] == "my_first_one" and t.S["step"] == 1
        t.end()
        # Kneady's own tutorial, edited: a copy in the folder, the original untouched
        own_folder, own = t.find("getting_started")
        before = t.load(os.path.join(own_folder, "tutorial.json"))
        e.load(context, "getting_started")
        if own_folder != os.path.join(folder, "getting_started"):
            pg.summary = "Changed in a test"
            assert bpy.ops.kneady.tutorial_save() == {"FINISHED"}
            copy = os.path.join(folder, "getting_started")
            assert os.path.isfile(os.path.join(copy, "practice.blend")), "the practice scene was left behind"
            assert t.load(os.path.join(own_folder, "tutorial.json")) == before, "Kneady's own was changed"
            assert t.find("getting_started")[0] == copy, "the copy is not the one listed"
        e.load(context, "my_first_one")
        assert bpy.ops.kneady.tutorial_delete() == {"FINISHED"}
        assert not os.path.exists(os.path.join(folder, "my_first_one"))
        assert "my_first_one" not in [tid for tid, _f, _d in t.available()]
        e.load(context, "demo")
        assert not e.KNEADY_OT_tutorial_delete.poll(context), "one outside the folder could be deleted"
    finally:
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_try_inside_a_practice_scene_keeps_the_way_back():
    """Try, pressed while a tutorial plays in its practice scene (Write a
    Tutorial does just that), plays the tutorial being written in its place.
    It also keeps Return to My File, which opens the person's own file
    again. Before this was fixed, its Finish left them in the practice
    scene's copy."""
    t, _o = _modules()
    os.makedirs(OUTPUT, exist_ok=True)
    mine = os.path.join(OUTPUT, "my_file.blend")
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.data.objects.new("Mine", None)
    bpy.context.scene.collection.objects.link(bpy.data.objects["Mine"])
    bpy.ops.wm.save_as_mainfile(filepath=mine)
    folder, was = _editor_folder()
    try:
        assert bpy.ops.kneady.tutorial_start(tutorial="getting_started") == {"FINISHED"}
        assert t.can_return() and t.S["user_file"] == mine
        wm = bpy.context.window_manager
        assert bpy.ops.kneady.tutorial_new(title="Written Inside") == {"FINISHED"}
        assert bpy.ops.kneady.tutorial_try() == {"FINISHED"}
        assert t.active() and t.S["id"] == "written_inside", t.S["id"]
        assert t.can_return() and t.S["user_file"] == mine, "Try lost the way back to the person's file"
        assert bpy.ops.kneady.tutorial_return() == {"FINISHED"}
        assert not t.active() and bpy.data.filepath == mine and "Mine" in bpy.data.objects, bpy.data.filepath
        # tried in the person's own file, no practice scene: nothing to go back to
        e = rigs.module("tutorial_edit")
        e.load(bpy.context, "written_inside")
        assert bpy.ops.kneady.tutorial_try() == {"FINISHED"}
        assert t.active() and not t.can_return() and wm.kneady_tutorial.id == "written_inside"
    finally:
        t.end()
        t.S["pending"] = None
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_editor_takes_the_start_from_the_scene():
    """Use Current takes from the scene the mode, what is selected and
    active, a value at its path, and the versions a clip was made in."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    context = bpy.context
    rig, mesh = rigs.arm_rig()
    folder, was = _editor_folder()
    try:
        bpy.ops.kneady.tutorial_new(title="Capture")
        pg = context.window_manager.kneady_tutorial
        for o in context.view_layer.objects:
            o.select_set(o == mesh)
        context.view_layer.objects.active = mesh
        assert bpy.ops.kneady.tutorial_capture(what="SELECTION") == {"FINISHED"}
        step = pg.steps[0]
        assert step.use_select and step.select == "Arm" and step.active == "Arm", (step.select, step.active)
        assert bpy.ops.kneady.tutorial_capture(what="MODE") == {"FINISHED"} and step.start_mode == "OBJECT"
        rig.location.z = 0.25
        bpy.ops.kneady.tutorial_list(which="SETS", action="ADD")
        step.sets[0].path = 'objects["ArmRig"].location'
        assert bpy.ops.kneady.tutorial_capture(what="SET", index=0) == {"FINISHED"}
        assert json.loads(step.sets[0].value) == [0.0, 0.0, 0.25], step.sets[0].value
        bpy.ops.kneady.tutorial_list(which="MEDIA", action="ADD", shared=True)
        assert bpy.ops.kneady.tutorial_capture(what="VERSIONS", index=0, shared=True) == {"FINISHED"}
        assert pg.media[0].recorded_blender == "%d.%d" % tuple(bpy.app.version[:2])
        data = e.from_props(pg)
        assert data["steps"][0]["start"]["select"] == ["Arm"] and data["steps"][0]["start"]["set"] == [
            {"path": 'objects["ArmRig"].location', "value": [0.0, 0.0, 0.25]}], data["steps"][0]["start"]
    finally:
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_editor_previews_as_it_is_written():
    """Greg asked for this: "When authoring tutorials it's going to be
    important to be able to see the tutorial panel updating while things are
    being edited in the n-panel." In Edit mode:
    - the panel shows the tutorial being edited, unsaved, at the step
      selected;
    - an edit shows at once;
    - the list's step and the panel's step follow each other;
    - going from step to step sets nothing up, but Reset does;
    - the eye hides the preview;
    - Try This Step plays it for real, and the preview is back after;
    - turning Edit mode off ends it."""
    t, o = _modules()
    e = rigs.module("tutorial_edit")
    context = bpy.context
    wm = context.window_manager
    folder, was = _editor_folder()
    try:
        wm.kneady_tutorial_edit = True
        wm.kneady_tutorial_preview = True
        e.load(context, "demo")
        pg = wm.kneady_tutorial
        assert e.sync_preview(context) and t.previewing() and t.S["id"] == "demo" and t.S["step"] == 0
        context.scene.kneady_on = True
        pg.steps[0].title = "Written just now"
        pg.steps[0].text[0].text = "A paragraph being written."
        e.sync_preview(context)
        assert t.step()["title"] == "Written just now" and t.step()["text"][0] == "A paragraph being written."
        assert context.scene.kneady_on is True, "an edit set the step up"
        pg.step_index = 2
        e.sync_preview(context)
        assert t.S["step"] == 2 and t.shares(), "the panel did not follow the list"
        o.act(context, "next")
        e.sync_preview(context)
        assert t.S["step"] == 3 and pg.step_index == 3, "the list did not follow the panel"
        o.act(context, "back")
        o.act(context, "back")
        o.act(context, "back")
        e.sync_preview(context)
        assert t.S["step"] == 0 and pg.step_index == 0 and context.scene.kneady_on is True, \
            "going back to a step set it up"
        o.act(context, "reset")
        assert context.scene.kneady_on is False, "Reset did not set the step up"
        pg.steps.add().title = "Added"
        pg.steps[-1].text.add().text = "x"
        e.sync_preview(context)
        assert len(t.steps()) == 5
        wm.kneady_tutorial_preview = False
        assert not t.active(), "the eye did not hide the preview"
        wm.kneady_tutorial_preview = True
        assert t.previewing()
        assert bpy.ops.kneady.tutorial_try() == {"FINISHED"}
        assert t.active() and not t.previewing(), "Try This Step did not play it for real"
        e.sync_preview(context)
        assert not t.previewing(), "the preview took over a tutorial being played"
        t.end(context)
        e.sync_preview(context)
        assert t.previewing(), "the preview did not come back after the tutorial played"
        e.load(context, "getting_started")
        e.sync_preview(context)
        m = rigs.module("media")
        assert t.previewing() and t.clip_where()[1] == m.MISSING and not m._JOBS, \
            "a preview asked to go online for a clip not recorded"
        wm.kneady_tutorial_edit = False
        assert not t.active(), "the preview outlived Edit mode"
    finally:
        wm.kneady_tutorial_edit = False
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_local_or_hosted_and_a_watch_link():
    """Greg asked to "make it so authoring allows you to author local or from
    hosted videos". In the editor each clip is either:
    - Local: its file is in the tutorial's folder and ships with it; or
    - Hosted: its copy is kept to upload, and it is downloaded when played.
    Choose File copies the file picked to where it belongs. A preview
    downloads a hosted clip, never a local one. A clip that can't be shown
    has a Watch button when it has a watch link, which opens it in the
    browser."""
    t, o = _modules()
    e = rigs.module("tutorial_edit")
    m = rigs.module("media")
    context = bpy.context
    wm = context.window_manager
    folder, was = _editor_folder()
    clip = os.path.join(DEMO, "demo", "counting.mp4")
    opened = []
    was_open, was_online = o.OPEN_URL[0], m.online
    o.OPEN_URL[0] = opened.append
    server = _serve(tempfile.mkdtemp())                  # this computer: nothing goes out to the internet
    try:
        bpy.ops.kneady.tutorial_new(title="Media")
        pg = wm.kneady_tutorial
        step = pg.steps[0]
        bpy.ops.kneady.tutorial_list(which="MEDIA", action="ADD")
        bpy.ops.kneady.tutorial_list(which="MEDIA", action="ADD")
        local, hosted = step.media[0], step.media[1]
        assert local.source == "LOCAL", "with no media URL, a new clip is kept in the tutorial"
        hosted.source = "HOSTED"
        assert bpy.ops.kneady.tutorial_media_file(filepath=clip, index=0) == {"FINISHED"}
        still = os.path.join(DEMO, "demo", "still.png")
        assert bpy.ops.kneady.tutorial_media_file(filepath=still, index=1) == {"FINISHED"}
        assert os.path.isfile(os.path.join(pg.folder, "counting.mp4")), "a local clip did not go into its folder"
        copy = os.path.join(os.path.dirname(pg.folder), ".hosted", pg.id, "still.png")
        assert os.path.isfile(copy), "a hosted clip's copy did not go into the folder's .hosted"
        assert m.copies_folder(os.path.join(rigs.module("tutorials").HERE, "tutorials", "x"), "x").endswith(
            os.path.join("dev", "media", "x")), "in Kneady's repository, hosted copies are not in dev/media"
        assert e.where_it_is(pg, local)[1] == "CHECKMARK" and e.where_it_is(pg, hosted)[1] == "CHECKMARK"
        data = e.from_props(pg)
        assert "hosted" not in data["steps"][0]["media"][0] and data["steps"][0]["media"][1]["hosted"] is True
        pg.media_url = "http://127.0.0.1:%d/" % server.server_address[1]
        bpy.ops.kneady.tutorial_list(which="MEDIA", action="ADD")
        assert step.media[2].source == "HOSTED", "with a media URL, a new clip is hosted"
        # a preview: a hosted clip not on this computer downloads, a local one never
        m.online = lambda: True
        step.media[2].file = "only_online.mp4"
        wm.kneady_tutorial_edit = True
        wm.kneady_tutorial_preview = True
        e.sync_preview(context)
        t.set_clip(2)
        assert t.clip_where()[1] in (m.DOWNLOADING, m.FAILED), "a preview did not fetch a hosted clip"
        step.media[0].file = "not_here.mp4"
        e.sync_preview(context)
        t.set_clip(0)
        assert t.clip_where()[1] == m.MISSING, "a preview fetched a local clip"
        # the Watch button, while the clip isn't showing
        step.media[0].watch = "https://youtube.com/shorts/abc"
        e.sync_preview(context)
        o.unload()
        assert o.watching(t.clip()) and o.watch_label(t.clip()["watch"]) == "Watch on YouTube"
        o.act(context, "watch")
        assert opened == ["https://youtube.com/shorts/abc"], opened
        assert o.watch_label("https://vimeo.com/1") == "Watch Online"
        r = o.layout(1400, 860, 1.0, 3, 0, False, watch=True)
        assert r["video"][0] <= r["watch"][0] < r["watch"][2] <= r["video"][2] and r["watch"][1] >= r["video"][1]
    finally:
        server.shutdown()
        o.OPEN_URL[0], m.online = was_open, was_online
        m.forget()
        wm.kneady_tutorial_edit = False
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_actions_tick_steps_off():
    """A step can watch for an action done since it began:
    - a Kneady button dragged or clicked, naming which object, region and
      button, and whether it was dragged or clicked;
    - any other operator run;
    - a region hovered, on a given object or on any."""
    t, _o = _modules()
    core = rigs.kneady()
    context = bpy.context
    rig, mesh = rigs.arm_rig()
    region = rigs.turn_button(mesh, rig, "Lower", name="Forearm")
    t.S["event_mark"] = t.event_mark()
    haul = {"operator": "kneady.drag", "with": {"target": "Arm", "region": region.id, "button": 0}, "moved": True}
    assert not t.met(context, haul), "done before anything was done"
    assert bpy.ops.kneady.drag(target=mesh.name, region=region.id, button=0, up=40.0) == {"FINISHED"}
    assert t.met(context, haul), "a haul on the button did not count"
    assert not t.met(context, dict(haul, moved=False)), "a haul counted as a click"
    assert not t.met(context, dict(haul, **{"with": {"target": "Arm", "region": region.id, "button": 1}}))
    assert t.met(context, {"operator": "kneady.drag"}), "any haul did not count"
    core.acted("kneady.drag", target="Arm", region=region.id, button=0, moved=False)
    assert t.met(context, dict(haul, moved=False)), "a click did not count"
    t.note_event("operator", operator="object.mode_set", values={"mode": "POSE"})
    assert t.met(context, {"operator": "object.mode_set", "with": {"mode": "POSE"}})
    assert not t.met(context, {"operator": "object.mode_set", "with": {"mode": "EDIT"}})
    core._hovered(None, (mesh.name, region.id))
    assert t.met(context, {"hovered": "Forearm"}) and t.met(context, {"hovered": "Forearm", "object": "Arm"})
    assert not t.met(context, {"hovered": "Forearm", "object": "Other"}) and not t.met(context, {"hovered": "Hand"})
    t.S["event_mark"] = t.event_mark()
    assert not t.met(context, haul) and not t.met(context, {"hovered": "Forearm"}), \
        "an action from before the step began counted"
    assert t.py_idname("KNEADY_OT_drag") == "kneady.drag" and t.py_idname("OBJECT_OT_mode_set") == "object.mode_set"
    found = "\n".join(t.problems({"format": 1, "title": "x", "steps": [{"text": ["x"], "done_when": [
        {"operator": "drag"}, {"hovered": "", "object": "Arm"}, {"operator": "kneady.drag", "speed": 3}]}]}))
    for words in ("not an operator's name", "hovered needs a name", "takes only operator, with, moved"):
        assert words in found, found


def _clip_at(folder, fps, frames):
    """An MP4 of `frames` frames at `fps`, made by Blender's own FFmpeg."""
    scene = bpy.data.scenes.new("kneady_clip_%d" % fps)
    camera = bpy.data.objects.new("kneady_clip_camera", bpy.data.cameras.new("kneady_clip_camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    try:
        r = scene.render
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x, r.resolution_y, r.resolution_percentage = 72, 128, 100
        r.fps, r.fps_base = fps, 1.0
        scene.frame_start, scene.frame_end = 1, frames
        settings = r.image_settings
        if hasattr(settings, "media_type"):                    # Blender 5: a video is a media type
            settings.media_type = "VIDEO"
        settings.file_format = "FFMPEG"
        r.ffmpeg.format, r.ffmpeg.codec = "MPEG4", "H264"
        r.use_file_extension = False
        r.filepath = os.path.join(folder, "clip_%d.mp4" % fps)
        with bpy.context.temp_override(scene=scene):
            bpy.ops.render.render(animation=True, scene=scene.name)
        return r.filepath
    finally:
        data = camera.data
        bpy.data.objects.remove(camera)
        bpy.data.cameras.remove(data)
        bpy.data.scenes.remove(scene)


def test_clips_play_at_their_own_rate():
    """Greg asked: "Will there be any trouble playing back videos that have
    different fps? Most of the videos I make will likely be 15 fps to reduce
    their size." The player reads each clip's own rate and frame count, and
    shows the frame due by the clock (overlay._play: the seconds since it
    began times the rate). So a 15 fps clip of 30 frames lasts two seconds,
    and a 30 fps one lasts one second."""
    _t, o = _modules()
    if not o.can_play():
        return                                                  # a Blender without FFmpeg
    folder = tempfile.mkdtemp(prefix="kneady_rates_")
    try:
        for fps in (15, 24, 30):
            path = _clip_at(folder, fps, 30)
            o.load(path)
            try:
                assert o.P["image"] is not None, "the %d fps clip did not load" % fps
                assert abs(o.P["fps"] - fps) < 1e-3, "a %d fps clip read as %s" % (fps, o.P["fps"])
                assert o.P["frames"] == 30, "a %d fps clip of 30 frames read as %d" % (fps, o.P["frames"])
            finally:
                o.unload()
    finally:
        o.unload()
        shutil.rmtree(folder, ignore_errors=True)


def test_an_items_end_its_pause_and_its_loop():
    """Greg asked: "Can a video or gif stay on the final frame when done?
    Also, maybe we should have a set of control buttons right below the
    video player for loop and pause. This only affects the active video".
    At its end (tutorials.end_of):
    - a clip on its own plays again;
    - one of several goes on to the next;
    - one marked hold stays on its last frame.
    Loop plays the item showing again, whatever it says. Pause pauses it.
    Play on an item held at its end starts it over. The next item then
    starts as it says."""
    t, o = _modules()
    clip, image, held = {"file": "a.mp4"}, {"file": "a.png"}, {"file": "a.mp4", "hold": True}
    for entry, items, loop, then in (
            (clip, 1, None, "again"), (clip, 3, None, "next"), (held, 1, None, "hold"), (held, 3, None, "hold"),
            (clip, 1, False, "hold"), (clip, 3, False, "next"), (held, 3, True, "again"), (clip, 3, True, "again"),
            (image, 1, None, "hold"), (image, 3, None, "next"), (dict(image, hold=True), 3, None, "hold"),
            (image, 3, True, "hold")):
        assert t.end_of(entry, items, loop) == then, (entry, items, loop, t.end_of(entry, items, loop))
    found = "\n".join(t.problems({"format": 1, "title": "x", "playlist": "http://youtube.com/p",
                                  "steps": [{"title": "a", "text": ["x"], "media": [{"file": "a.mp4", "hold": 1}]}]}))
    assert "hold is not true or false" in found and "playlist is not an https address" in found, found
    if not o.can_play():
        return                                                  # a Blender without FFmpeg
    context = bpy.context
    root = tempfile.mkdtemp(prefix="kneady_ends_")
    folder = os.path.join(root, "ends")
    os.makedirs(folder)
    t.FOLDERS.append(root)
    try:
        for name in ("a", "b"):
            os.replace(_clip_at(folder, 30, 6), os.path.join(folder, name + ".mp4"))     # a fifth of a second
        link = "https://www.youtube.com/playlist?list=PLkneadyTestsKneadyTestsKneadyTes"
        with open(os.path.join(folder, "tutorial.json"), "w", encoding="utf-8") as f:
            json.dump({"format": 1, "title": "Ends", "playlist": link, "steps": [
                {"title": "Alone", "text": ["x"], "media": [{"file": "a.mp4"}]},
                {"title": "Held", "text": ["x"], "media": [{"file": "a.mp4", "hold": True}]},
                {"title": "Two", "text": ["x", "y"], "media": [{"file": "a.mp4"}, {"file": "b.mp4", "paragraph": 1}]},
                {"title": "First held", "text": ["x", "y"],
                 "media": [{"file": "a.mp4", "hold": True}, {"file": "b.mp4", "paragraph": 1}]}]}, f)
        t.begin(context, "ends")

        def to_its_end():
            o._play()
            assert o.P["image"] is not None and o.P["frames"] == 6, (o.P["image"], o.P["frames"])
            o.P["t0"] -= 1.0                                    # a second on: past its end
            o._play()

        # a clip alone plays again, Loop lit; Pause pauses it
        to_its_end()
        assert o.P["frame"] == 1 and not o.P["ended"] and t.looping(), (o.P["frame"], o.P["ended"])
        o.act(context, "pause")
        o._play()
        assert t.S["playing"] is False and o.P["paused"] is not None
        o.act(context, "pause")
        assert t.S["playing"] is True
        # Loop off: held on its last frame; Play starts it over
        o.act(context, "loop")
        assert t.S["loop"] is False and not t.looping()
        to_its_end()
        assert o.P["ended"] and o.P["frame"] == 6 and t.S["clip"] == 0, (o.P["ended"], o.P["frame"])
        o._play()
        assert o.P["frame"] == 6, "a held clip moved on"
        o.act(context, "pause")
        o._play()
        assert not o.P["ended"] and o.P["frame"] == 1 and t.S["playing"], (o.P["ended"], o.P["frame"])
        # held, then Loop on: plays again at once
        o.P["t0"] -= 1.0
        o._play()
        assert o.P["ended"]
        o.act(context, "loop")
        o._play()
        assert t.looping() and not o.P["ended"] and o.P["frame"] == 1
        # marked hold: stays at its end, Loop off to start with
        t.enter(context, 1)
        assert t.S["loop"] is None and not t.looping(), "the Loop of the step before carried over"
        to_its_end()
        assert o.P["ended"] and o.P["frame"] == 6
        # one of two: Loop keeps it going round. Off, it goes on to the next,
        # which starts as it says
        t.enter(context, 2)
        o.act(context, "loop")
        to_its_end()
        assert t.S["clip"] == 0 and o.P["frame"] == 1, "Loop on, it went on"
        o.act(context, "loop")
        o.act(context, "pause")
        to_its_end()
        assert t.S["clip"] == 0 and o.P["paused"] is not None, "paused, it went on"
        o.act(context, "pause")
        to_its_end()
        assert t.S["clip"] == 1 and t.S["loop"] is None and t.S["playing"], (t.S["clip"], t.S["loop"])
        o.act(context, "pause")
        o.act(context, "prev")
        assert t.S["playing"], "a paused item left the next paused"
        # the first of two marked hold: it stays, and the arrow goes on
        t.enter(context, 3)
        to_its_end()
        assert t.S["clip"] == 0 and o.P["ended"]
        o.act(context, "next_clip")
        o._play()
        assert t.S["clip"] == 1 and not o.P["ended"]
        # the QR code: the phone shows it, the clip waits behind it, a click on it goes back
        assert t.playlist() == link
        o.act(context, "phone")
        assert t.S["qr"] is True
        o._play()
        assert o.P["paused"] is not None, "the clip played on behind the QR code"
        o.act(context, "qr")
        assert t.S["qr"] is False
        o._play()
        assert o.P["paused"] is None
        o.act(context, "phone")
        t.end()
        assert t.S["qr"] is False and t.S["loop"] is None
    finally:
        t.end()
        o.unload()
        t.FOLDERS.remove(root)
        shutil.rmtree(root, ignore_errors=True)


def test_a_playlist_as_a_qr_code():
    """The QR code of a tutorial's playlist (overlay.qr_code, using Project
    Nayuki's encoder). It is square, with its three finder patterns where a
    camera looks for them and none at the fourth corner, and its top row
    first. A link too long for a code gives None."""
    _t, o = _modules()
    link = "https://www.youtube.com/playlist?list=PLkneadyTestsKneadyTestsKneadyTes"
    n, rows = o.qr_code(link)
    assert n in (29, 33, 37) and len(rows) == n, n
    dark = {(x, y) for y, runs in enumerate(rows) for a, b in runs for x in range(a, b)}
    finder = ["1111111", "1000001", "1011101", "1011101", "1011101", "1000001", "1111111"]

    def corner(left, top):
        return ["".join("1" if (left + x, top + y) in dark else "0" for x in range(7)) for y in range(7)]

    for left, top in ((0, 0), (n - 7, 0), (0, n - 7)):
        assert corner(left, top) == finder, "no finder at %d, %d: %s" % (left, top, corner(left, top))
    assert corner(n - 7, n - 7) != finder, "a finder at the fourth corner: the code is upside down"
    assert o.qr_code(link) is o.qr_code(link), "worked out again"
    assert o.qr_code("https://x/" + "a" * 3000) is None


def test_a_trim_is_the_frames_that_play():
    """Greg asked: "Could it be possible to trim the recorded video without
    going into an editing app?" A clip's `trim` is its first and last frames,
    counted from 1, with a last of 0 meaning its end. The trim is what plays:
    the clip starts on the first frame, goes round to it, and holds on the
    last."""
    t, o = _modules()
    for trim, frames, pair in ((None, 10, (1, 10)), ([3, 8], 10, (3, 8)), ([3, 0], 10, (3, 10)),
                               ([3, 40], 10, (3, 10)), ([40, 50], 10, (10, 10)), ([True, 4], 10, (1, 10)),
                               ([0, 4], 10, (1, 10)), ([5, 2], 10, (1, 10))):
        entry = {"file": "a.mp4"} if trim is None else {"file": "a.mp4", "trim": trim}
        assert t.trim_of(entry, frames) == pair, (trim, t.trim_of(entry, frames))
    found = "\n".join(t.problems({"format": 1, "title": "x", "steps": [
        {"title": "a", "text": ["x"], "media": [{"file": "a.mp4", "trim": [5, 2]}, {"file": "b.mp4", "trim": 3}]}]}))
    assert found.count("trim is not [first, last]") == 2, found
    if not o.can_play():
        return
    context = bpy.context
    root = tempfile.mkdtemp(prefix="kneady_trimmed_")
    folder = os.path.join(root, "trimmed")
    os.makedirs(folder)
    t.FOLDERS.append(root)
    try:
        os.replace(_clip_at(folder, 30, 12), os.path.join(folder, "a.mp4"))
        with open(os.path.join(folder, "tutorial.json"), "w", encoding="utf-8") as f:
            json.dump({"format": 1, "title": "Trimmed", "steps": [
                {"title": "Round", "text": ["x"], "media": [{"file": "a.mp4", "trim": [3, 8]}]},
                {"title": "Held", "text": ["x"], "media": [{"file": "a.mp4", "trim": [3, 8], "hold": True}]}]}, f)
        t.begin(context, "trimmed")
        o._play()
        assert o.P["frames"] == 12 and o.P["frame"] == 3, "it did not start on its first frame: %d" % o.P["frame"]
        o.P["t0"] = time.perf_counter() - 5.5 / 30.0          # five and a half frames on: its last
        o._play()
        assert o.P["frame"] == 8, "five frames on, it showed %d" % o.P["frame"]
        o.P["t0"] = time.perf_counter() - 6.5 / 30.0          # one more: past its last
        o._play()
        assert o.P["frame"] == 3, "past its last it did not go round to its first: %d" % o.P["frame"]
        t.enter(context, 1)
        o._play()
        o.P["t0"] -= 1.0
        o._play()
        assert o.P["ended"] and o.P["frame"] == 8, "held on %d, not its last kept frame" % o.P["frame"]
    finally:
        t.end()
        o.unload()
        t.FOLDERS.remove(root)
        shutil.rmtree(root, ignore_errors=True)


def test_a_trim_typed_in_the_editor():
    """The editor's Trim fields are the clip's trim (0 for its start or its
    end), and they say what they keep, read from the clip itself."""
    t, o = _modules()
    if not o.can_play():
        return
    e = rigs.module("tutorial_edit")
    wm = bpy.context.window_manager
    folder, was = _editor_folder()
    source = os.path.join(DEMO, "demo", "counting.mp4")              # 240 frames, 24 a second
    try:
        bpy.ops.kneady.tutorial_new(title="Typed")
        pg = wm.kneady_tutorial
        step = pg.steps[0]
        bpy.ops.kneady.tutorial_list(which="MEDIA", action="ADD")
        assert bpy.ops.kneady.tutorial_media_file(filepath=source, index=0) == {"FINISHED"}
        step.media_from = "OWN"
        m = step.media[0]
        assert "trim" not in e.from_props(pg)["steps"][0]["media"][0]
        assert e._trim_words(pg, m) == "10.0 s, not trimmed", e._trim_words(pg, m)
        m.trim_first, m.trim_last = 101, 148
        assert e.from_props(pg)["steps"][0]["media"][0]["trim"] == [101, 148]
        assert e._trim_words(pg, m) == "Keeps 2.0 of 10.0 s", e._trim_words(pg, m)
        m.trim_first, m.trim_last = 0, 48
        assert e.from_props(pg)["steps"][0]["media"][0]["trim"] == [1, 48]
        assert e._trim_words(pg, m) == "Keeps 2.0 of 10.0 s"
    finally:
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_unsaved_edits_asked_before_playing():
    """Greg found clips he had added "show when I'm editing the tutorial but
    not when I play it back". The tutorial wasn't saved, and Start a Tutorial
    played it as saved. Now a tutorial with edits not saved yet asks, when
    started: Save and Play, or Play Saved Version."""
    t, _o = _modules()
    context = bpy.context
    wm = context.window_manager
    folder, was = _editor_folder()
    try:
        bpy.ops.kneady.tutorial_new(title="Unsaved")
        pg = wm.kneady_tutorial
        tid = pg.id
        assert not t.unsaved(tid), "a tutorial just made reads as unsaved"
        pg.steps[0].title = "Edited, not saved"
        assert t.unsaved(tid) and not t.unsaved("demo")
        # It asks, and nothing starts until a choice is made. The operator's
        # invoke asks, but a script's bpy.ops call runs execute, so this calls
        # asks_first itself. probe_unsaved_start checks the menu in a window.
        asked = []
        was_ask = t.ask_unsaved
        t.ask_unsaved = lambda _context, tutorial_id: asked.append(tutorial_id)
        try:
            assert t.asks_first(context, tid) and not t.asks_first(context, "demo")
        finally:
            t.ask_unsaved = was_ask
        assert asked == [tid] and not t.active(), asked
        # Play Saved Version: the edit not in it, still unsaved
        assert bpy.ops.kneady.tutorial_start(tutorial=tid, unsaved="SAVED") == {"FINISHED"}
        assert t.active() and t.step()["title"] == "First step" and t.unsaved(tid), t.step()["title"]
        t.end()
        # Save and Play: saved, then played with the edit
        assert bpy.ops.kneady.tutorial_start(tutorial=tid, unsaved="SAVE") == {"FINISHED"}
        assert t.step()["title"] == "Edited, not saved" and not t.unsaved(tid)
        with open(os.path.join(pg.folder, "tutorial.json"), encoding="utf-8") as f:
            assert json.load(f)["steps"][0]["title"] == "Edited, not saved"
    finally:
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_dropdown_follows_the_title_typed():
    """Greg found: "I can change it's title but that doesn't change its name
    in the dropdown list". It showed the saved title until a save. Now the
    tutorial being edited is listed by its title as typed. The others, and
    Start a Tutorial's menu (which plays what is saved), list their saved
    titles."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    wm = bpy.context.window_manager
    folder, was = _editor_folder()
    try:
        bpy.ops.kneady.tutorial_new(title="First Name")
        pg = wm.kneady_tutorial
        tid = pg.id
        titles = dict((i, n) for i, n, _d in e.pick_items())
        assert titles[tid] == "First Name", titles
        pg.title = "Second Name"
        titles = dict((i, n) for i, n, _d in e.pick_items())
        assert titles[tid] == "Second Name", titles
        assert dict((i, d.get("title")) for i, _f, d in t.available())[tid] == "First Name", "saved without a Save"
        assert titles.get("getting_started") == "Getting Started", titles
        pg.title = "   "
        assert dict((i, n) for i, n, _d in e.pick_items())[tid] == "First Name", "a blank title listed"
    finally:
        wm.kneady_tutorial_edit = False
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_saving_keeps_the_step_selected():
    """Saving put the editor back at step 1 - Greg hit this while recording
    a step's actions at step 3. A save set the dropdown to the tutorial
    saved, and that loaded the tutorial again, even though the dropdown
    already held it. Now the dropdown is set only when it changes, so a save
    leaves the editor as it is."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    wm = bpy.context.window_manager
    folder, was = _editor_folder()
    loads = []
    was_load = e.load
    try:
        bpy.ops.kneady.tutorial_new(title="Kept Place")
        pg = wm.kneady_tutorial
        for _ in range(2):
            bpy.ops.kneady.tutorial_list(which="STEPS", action="ADD")
        pg.step_index = 2
        pg.steps[2].title = "Third"
        e.load = lambda *a, **k: loads.append(a[1]) or was_load(*a, **k)
        assert bpy.ops.kneady.tutorial_save() == {"FINISHED"}
        assert pg.step_index == 2 and not loads, (pg.step_index, loads)
        assert not t.unsaved(pg.id), "saved, but said unsaved"
        assert [s["title"] for s in e.from_props(pg)["steps"]][2] == "Third"
    finally:
        e.load = was_load
        wm.kneady_tutorial_edit = False
        t.end()
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_the_editor_survives_a_practice_scene():
    """Greg reported: "The tutorial action recording still seems to get lost
    after I leave edit mode. I am saving before I leave." With no file of his
    own saved, Return to My File made a new file with its UI - a new window
    manager - and the editor came back empty. Gone were the tutorial being
    written, its unsaved edits, and what Kneady Pro keeps on its steps (each
    step's recording). Now the new file keeps the windows, just as opening
    the practice scene did, so everything the editor held is still there."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    wm = bpy.context.window_manager
    folder, was = _editor_folder()
    e.KNEADY_PG_tut_step.kneady_test_kept = bpy.props.StringProperty()   # as a program keeps on a step
    try:
        assert bpy.data.filepath == ""
        bpy.ops.kneady.tutorial_new(title="Being Written")
        bpy.ops.kneady.tutorial_list(which="STEPS", action="ADD")
        pg = wm.kneady_tutorial
        pg.step_index = 1
        pg.steps[1].title = "Not saved yet"
        pg.steps[1].kneady_test_kept = "a recording"
        assert bpy.ops.kneady.tutorial_start(tutorial="getting_started") == {"FINISHED"}
        assert t.active() and t.S["practice"], "the practice scene did not open"
        assert bpy.ops.kneady.tutorial_return() == {"FINISHED"}
        assert not t.active() and bpy.data.filepath == ""
        pg = bpy.context.window_manager.kneady_tutorial
        assert pg.id == "being_written" and len(pg.steps) == 2 and pg.step_index == 1, (pg.id, len(pg.steps))
        assert pg.steps[1].title == "Not saved yet" and t.unsaved(pg.id), "the edits not saved went"
        assert pg.steps[1].kneady_test_kept == "a recording", "what a program kept on a step went"
    finally:
        t.end()
        t.S["pending"] = None
        del e.KNEADY_PG_tut_step.kneady_test_kept
        bpy.context.window_manager.kneady_tutorial_edit = False
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_a_step_done_moves_on():
    """Greg asked: "I'd like to use that to move to the next step in a
    tutorial. User can select next or complete the actions that are
    specified." A step the person finishes moves on to the next a moment
    later (ADVANCE_AFTER, with the tick shown first). These do not move on:
    - a step already done as it began;
    - the last step;
    - a step in the editor's preview."""
    t, _o = _modules()
    context = bpy.context
    folder, was = _editor_folder()
    data = {"format": t.FORMAT, "title": "Moves On", "order": 100, "steps": [
        {"title": "Labels always", "text": ["Set Labels to Always."],
         "done_when": [{"path": "scene.kneady_labels", "is": "ALWAYS"}]},
        {"title": "Labels off", "text": ["Set Labels to Off."],
         "done_when": [{"path": "scene.kneady_labels", "is": "OFF"}]},
        {"title": "Last", "text": ["The end."], "done_when": [{"path": "scene.kneady_labels", "is": "HOVER"}]}]}
    os.makedirs(os.path.join(folder, "moves_on"))
    with open(os.path.join(folder, "moves_on", "tutorial.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    try:
        context.scene.kneady_labels = "HOVER"
        t.begin(context, "moves_on")
        assert t.S["step"] == 0 and not t.done() and not t.advance(), "moved on before it was done"
        context.scene.kneady_labels = "ALWAYS"
        t.check(context)
        at = t.S["done_at"]
        assert t.done() and at is not None
        assert t.ADVANCE_AFTER == 0.5, "Greg: \"The delay felt about twice too long\" (it was 1.0)"
        # the timer looks again when the next step is due, not at its next look after
        assert abs(t._next_look(now=at + 0.4) - 0.1) < 1e-6 and t._next_look(now=at) == t.CHECK_EVERY
        assert _o.done_word() == "Done", "a step before the last says Completed!"
        assert not t.advance(now=at + t.ADVANCE_AFTER * 0.5) and t.S["step"] == 0, "moved on before the tick showed"
        assert t.advance(now=at + t.ADVANCE_AFTER + 0.01) and t.S["step"] == 1, t.S["step"]
        # Back to a step already done as it began: ticked off, never moved past
        t.back_step(context)
        assert t.S["step"] == 0 and t.done() and t.S["done_at"] is None
        assert not t.advance(now=time.perf_counter() + 10), "skipped a step done as it began"
        t.next_step(context)
        context.scene.kneady_labels = "OFF"
        t.check(context)
        assert t.advance(now=t.S["done_at"] + t.ADVANCE_AFTER + 0.01) and t.S["step"] == 2
        # the last step: done, and it stays there, saying Completed! Greg: "there Should also be
        # acknowledgement that a tutorial is completed. Have it say Completed! instead of done"
        context.scene.kneady_labels = "HOVER"
        t.check(context)
        assert t.done() and not t.advance(now=t.S["done_at"] + 10) and t.S["step"] == 2
        assert _o.done_word() == "Completed!" and t._next_look() == t.CHECK_EVERY
        # the editor's preview never moves on
        t.enter(context, 0)
        t.S["preview"] = True
        context.scene.kneady_labels = "ALWAYS"
        t.check(context)
        assert t.done() and not t.advance(now=t.S["done_at"] + 10) and t.S["step"] == 0
    finally:
        t.S["preview"] = False
        t.end()
        context.scene.kneady_labels = "HOVER"
        _editor_folder_back(was)
        shutil.rmtree(folder, ignore_errors=True)


def test_a_new_step_flashes_and_the_clip_grows():
    """Greg asked: "Could the video enlarge on hover? ... doubles it's size
    temporarily until moused off", and "Some kind of flash or quick
    fadeout/fadein effect would make it register more". The clip grows
    ENLARGE times from its top-left corner, kept inside the view. A step
    changing within a tutorial flashes for FLASH seconds; a tutorial
    beginning or ending doesn't."""
    t, o = _modules()
    context = bpy.context
    # 140 x 249 at (18, 400): twice, from its top-left corner
    assert o.enlarged_rect((18, 400, 158, 649), 1000, 1.0) == (18, 649 - 2 * 249, 18 + 2 * 140, 649)
    big = o.enlarged_rect((18, 400, 158, 649), 300, 1.0)      # a narrow view: as wide as fits
    assert big is not None and abs(big[2] - (300 - o.MARGIN)) < 1e-6, big
    assert o.enlarged_rect((18, 50, 158, 299), 1000, 1.0) is None, "grew past the foot of the view"
    o.HOVER.update(key="video", since=time.perf_counter())
    assert o.enlarged({"video": (18, 400, 158, 649)}, 1000, 1.0) is None, "grew before ENLARGE_AFTER"
    o.HOVER.update(key=None, since=0.0)
    # the flash: a step changed, not a tutorial begun
    t.begin(context, "demo")
    assert o.FX["was"] == ("demo", 0) and o.flash_progress() is None, "a tutorial beginning flashed"
    t.next_step(context)
    at = o.FX["at"]
    assert at is not None and o.FX["was"] == ("demo", 1), o.FX
    assert abs(o.flash_progress(now=at + 0.1) - 0.1 / o.FLASH) < 1e-6
    assert o.flash_progress(now=at + o.FLASH + 0.01) is None and o.FX["at"] is None
    t.set_clip(1)
    assert o.FX["at"] is None, "a clip changing flashed"
    t.back_step(context)
    assert o.FX["at"] is not None, "Back did not flash"
    o.FX["at"] = None
    t.end()
    assert o.FX["was"] is None and o.FX["at"] is None, "a tutorial ending flashed"


def _write_tutorial(folder, name, data):
    os.makedirs(os.path.join(folder, name), exist_ok=True)
    with open(os.path.join(folder, name, "tutorial.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return os.path.join(folder, name)


def test_tutorials_from_an_addon_and_shared_scenes():
    """Tutorials from another add-on, and shared practice scenes:
    - an enabled add-on's kneady_tutorials/ folder is listed under the
      add-on's name, without the add-on calling anything of Kneady's;
    - a practice scene may be shared from a sibling folder (_scenes, never
      listed as a tutorial), but not from anywhere past the tutorials folder;
    - a clip or image is a file's name, never a path;
    - a shared scene comes along when the tutorial is copied to be edited."""
    import sys
    import types
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    root = tempfile.mkdtemp(prefix="kneady_addon_")
    folder, was = _editor_folder()
    name = "kneady_test_addon_tuts"
    module = types.ModuleType(name)
    module.__file__ = os.path.join(root, "__init__.py")
    sys.modules[name] = module
    was_addons = t.ADDONS
    t.ADDONS = [name]
    try:
        tuts = os.path.join(root, t.ADDON_FOLDER)
        os.makedirs(os.path.join(tuts, "_scenes"))
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(tuts, "_scenes", "shared.blend"), copy=True)
        step = {"title": "One", "text": ["Do it."]}
        _write_tutorial(tuts, "from_addon", {"format": 1, "title": "From an Add-on",
                                              "practice": "../_scenes/shared.blend", "steps": [step]})
        groups = dict(t.listed())
        heading = t._addon_title(name, module)
        assert heading in groups and [tid for tid, _f, _d in groups[heading]] == ["from_addon"], groups.keys()
        assert "_scenes" not in [tid for tid, _f, _d in t.available()], "_scenes listed as a tutorial"
        here, data = t.find("from_addon")
        assert t.problems(data, here) == [], t.problems(data, here)
        assert os.path.isfile(t.practice_copy(here, data))
        for practice in ("../../outside.blend", "../_scenes/shared.txt"):
            found = t.problems(dict(data, practice=practice), here)
            assert any("not a .blend in its tutorials folder" in p for p in found), (practice, found)
        for bad in ("../x.png", "sub/x.png", "C:\\x.png", ".hidden.png"):
            found = t.problems(dict(data, media=[{"file": bad}]), here)
            assert any("is not a file's name" in p for p in found), (bad, found)
        # once edited, it is copied to your folder, with the shared scene beside it
        e.load(bpy.context, "from_addon")
        pg = bpy.context.window_manager.kneady_tutorial
        pg.summary = "Edited"
        e.save(pg)
        assert e._inside(pg.folder, folder) and pg.practice == "shared.blend", (pg.folder, pg.practice)
        assert os.path.isfile(os.path.join(pg.folder, "shared.blend")), "the shared scene was left behind"
        assert t.problems(e.from_props(pg), pg.folder) == []
        assert dict(t.listed())[t.YOURS_HEADING][0][0] == "from_addon", "the copy is not the one listed"
    finally:
        t.ADDONS = was_addons
        sys.modules.pop(name, None)
        _editor_folder_back(was)
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(folder, ignore_errors=True)


def test_tutorials_attached_to_an_item():
    """A tutorial attached to an object carries its clips and images in the
    file:
    - it is listed In This File, and played from a copy unpacked to a folder
      of its own, in the file it is in;
    - it comes along when the file is saved and opened again, and when the
      object is appended or linked into another file. It is listed once,
      however many copies there are;
    - a linked one can't be changed;
    - edited, it is saved into its object;
    - a file naming a path for a clip writes nothing outside its folder;
    - taken off, it is gone."""
    t, _o = _modules()
    e = rigs.module("tutorial_edit")
    context = bpy.context
    work = tempfile.mkdtemp(prefix="kneady_attached_")
    folder, was = _editor_folder()
    was_cache = t.ATTACHED_CACHE
    t.ATTACHED_CACHE = os.path.join(work, "cache")
    try:
        bpy.ops.wm.read_homefile(use_empty=True)
        rig = bpy.data.objects.new("Rig", None)
        context.scene.collection.objects.link(rig)
        source = _write_tutorial(work, "rig_basics", {
            "format": 1, "title": "Rig Basics", "practice": "practice.blend",
            "steps": [{"title": "Look", "text": ["Watch."], "media": [{"file": "counting.mp4"}]},
                      {"title": "And", "text": ["See."], "media": [{"file": "still.png", "seconds": 1}]}]})
        for name in ("counting.mp4", "still.png"):
            shutil.copy(os.path.join(DEMO, "demo", name), source)
        with open(os.path.join(source, "counting.mp4"), "rb") as f:
            clip = f.read()
        tid, count, size = t.attach(rig, source, t.load(os.path.join(source, "tutorial.json")), "rig_basics")
        assert tid == "@Rig/rig_basics" and count == 2 and size > len(clip), (tid, count, size)
        assert t.file_has_tutorials()
        assert [x[0] for x in dict(t.listed()).get(t.FILE_HEADING, [])] == [tid], t.listed()

        def clip_in(tutorial_id):
            here, _data = t.find(tutorial_id)
            with open(os.path.join(here, "counting.mp4"), "rb") as f:
                return f.read()

        here, data = t.find(tid)
        assert "practice" not in data and t.problems(data, here) == [], t.problems(data, here)
        assert clip_in(tid) == clip, "the clip came back changed"
        assert t.prepare(tid) is None, "an attached tutorial opened a practice scene"
        t.begin(context, tid)
        assert t.active() and t.S["id"] == tid
        t.end()
        # saved and opened again, with the folder it was unpacked to deleted in between
        saved = os.path.join(work, "rig.blend")
        bpy.ops.wm.save_as_mainfile(filepath=saved)
        shutil.rmtree(t.ATTACHED_CACHE)
        bpy.ops.wm.open_mainfile(filepath=saved)
        assert clip_in(tid) == clip, "lost in the file"
        # edited, and saved into its object
        e.load(context, tid)
        pg = context.window_manager.kneady_tutorial
        pg.title = "Rig Basics, Changed"
        e.save(pg)
        stored = json.loads(bpy.data.objects["Rig"][t.ATTACHED]["rig_basics"]["tutorial"])
        assert stored["title"] == "Rig Basics, Changed" and pg.id == tid, (stored["title"], pg.id)
        here, data = t.find(tid)
        assert data["title"] == "Rig Basics, Changed" and not t.missing_media(data, here), "a save lost its clips"
        bpy.ops.wm.save_mainfile()
        # appended and linked into another file: listed once
        bpy.ops.wm.read_homefile(use_empty=True)
        assert not t.file_has_tutorials()
        with bpy.data.libraries.load(saved, link=False) as (_src, dst):
            dst.objects = ["Rig"]
        with bpy.data.libraries.load(saved, link=True) as (_src, dst):
            dst.objects = ["Rig"]
        assert len(bpy.data.objects) == 2, [o.name_full for o in bpy.data.objects]
        assert len(dict(t.listed()).get(t.FILE_HEADING, [])) == 1, t.listed()
        # the linked one alone: listed, played, never changed here
        bpy.data.objects.remove(next(o for o in bpy.data.objects if o.library is None))
        linked = bpy.data.objects[0]
        found = [x[0] for x in dict(t.listed()).get(t.FILE_HEADING, [])]
        assert found == ["%s%s/rig_basics" % (t.FILE_PREFIX, linked.name_full)], found
        assert clip_in(found[0]) == clip, "the linked one's clip"
        # editable() gives the reason a tutorial can't be changed, "" if it can
        assert t.editable(linked), "a linked object's tutorial could be changed"
        try:
            t.attach(linked, source, {"format": 1, "title": "x", "steps": []}, "x")
            raise AssertionError("attached to a linked object")
        except OSError:
            pass
        e.load(context, found[0])
        try:
            e.save(context.window_manager.kneady_tutorial)
            raise AssertionError("a linked object's tutorial was saved")
        except OSError:
            pass
        # someone else's file naming a path for a clip: nothing written outside its folder
        bpy.ops.wm.read_homefile(use_empty=True)
        evil = bpy.data.objects.new("Evil", None)
        text = json.dumps({"format": 1, "title": "Evil", "steps": [
            {"title": "x", "text": ["y"], "media": [{"file": "../escaped.txt"}]}]})
        evil[t.ATTACHED] = {"evil": {"tutorial": text, "files": {"../escaped.txt": b"x"}, "sha": "e" * 64}}
        here, data = t.find("@Evil/evil")
        assert not os.path.exists(os.path.join(os.path.dirname(here), "escaped.txt")), "a file was written outside"
        assert any("is not a file's name" in p for p in t.problems(data, here)), t.problems(data, here)
        # taken off
        t.detach("@Evil/evil")
        assert t.ATTACHED not in evil and not t.file_has_tutorials()
        assert t.FILE_HEADING not in dict(t.listed())
    finally:
        t.end()
        t.ATTACHED_CACHE = was_cache
        _editor_folder_back(was)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(folder, ignore_errors=True)


def test_tutorials_are_numbered_quick_start_first():
    """Kneady's own tutorials, as it ships them, are numbered in their order
    for the menu, the editor's dropdown and the panel's title. Learn, Inform
    and Quiet comes first, as 0 (its order is 0, before the course), then
    Greg's Quick Start as 1. Getting Started is the tests' own and no longer
    ships."""
    t, _o = _modules()
    was = list(t.FOLDERS)
    try:
        t.FOLDERS[:] = was[:1]                       # Kneady's own alone, as it ships
        ids = [tid for tid, _f, _d in dict(t.listed())[t.KNEADY_HEADING]]
        assert ids[:4] == ["help_levels", "quick_start", "change_controls", "drive_more"], ids
        assert "getting_started" not in ids, "Getting Started still ships"
        # Learn, Inform and Quiet comes before the course: order 0, numbered 0
        assert t.number_of("help_levels") == 0 and t.number_of("quick_start") == 1
        assert t.number_of("drive_more") == 3
        _folder, data = t.find("help_levels")
        assert t.titled(data, "help_levels", 0) == "0. Learn, Inform and Quiet"
        _folder, data = t.find("change_controls")
        assert t.titled(data, "change_controls", 2) == "2. Change the Default Controls"
        assert t.titled(data, "change_controls") == "Change the Default Controls"
        e = rigs.module("tutorial_edit")
        shown = [item[1] for item in e._pick_items(None, bpy.context) if item]
        assert shown[:2] == ["0. Learn, Inform and Quiet", "1. Quick Start"], shown
        menu = []
        layout = type("L", (), {"label": lambda self, **_k: None, "separator": lambda self: None,
                                "operator": lambda self, _i, text="", **_k: menu.append(text) or
                                type("Op", (), {})()})()
        t.KNEADY_MT_tutorials.draw(type("M", (), {"layout": layout})(), bpy.context)
        assert menu[:2] == ["0. Learn, Inform and Quiet", "1. Quick Start"], menu
        # a list that doesn't start with an order 0 counts from 1, as before
        assert t.first_number([("x", "", {"order": 5})]) == 1 and t.first_number([]) == 1
    finally:
        t.FOLDERS[:] = was


def test_menu_closing_tells_the_tutorial():
    """Esc and a click in empty space never show in the window manager's
    list of operators, so they tell a tutorial themselves (menus._heard). A
    step that asks for kneady.close_menu or kneady.click_off is done by
    them."""
    t, _o = _modules()
    menus = rigs.module("menus")
    t.S["event_mark"] = t.event_mark()
    assert not t.met(bpy.context, {"operator": "kneady.close_menu"})
    menus._heard("kneady.close_menu")
    assert t.met(bpy.context, {"operator": "kneady.close_menu"})
    assert not t.met(bpy.context, {"operator": "kneady.click_off"})
