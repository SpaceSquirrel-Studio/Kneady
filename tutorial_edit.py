"""Making tutorials in the Kneady tab. Greg asked: "how do I author my own
tutorials in this panel? Ideally it would be an "edit mode" button that when
selected allows me to edit a tutorial. Of course would need to be able to
create and delete new tutorials in this mode".

At Help's Learn, the pencil beside Start a Tutorial turns Edit mode on. In
it you can:

- pick a tutorial, make one or delete one;
- edit its title, practice scene and shared media;
- edit its steps: text, media, the fields a step lights, what ticks it off
  and what it starts with.

Each part can be caught from the scene as it is (Use Current), and a path
can be pasted from Blender's Copy Full Data Path. Problems show as you
type. Save writes tutorial.json; Try This Step plays the tutorial from that
step in this file.

The tutorial being edited is a copy, held in properties on the window
manager (KNEADY_PG_tutorial). It is made from its tutorial.json (to_props)
and written back (from_props), and the two keep everything the format
holds. It is saved into the folder tutorials are made in
(tutorials.author_folder). A tutorial from elsewhere, such as Kneady's own
in an installed copy, is copied there first, with its practice scene and
media. A deleted tutorial goes to the Recycle Bin on Windows.

**The panel shows the tutorial as it is written.** Greg: "When authoring
tutorials it's going to be important to be able to see the tutorial panel
updating while things are being edited in the n-panel. While in "Edit
Tutorials" you should be able to see the panels for that tutorial". While
Edit mode is on, the panel over the view previews the tutorial being edited,
unsaved, at the selected step. A timer hands the panel what the properties
hold five times a second (sync_preview). The step selected here and the
panel's step follow each other. The eye beside Save hides the preview. Try
This Step plays the tutorial for real, and the preview comes back when that
ends.

**A program can add to the editor**: its own rows under the folder
(DRAW_EDITOR), under a step's title (DRAW_STEP) and under a clip's trim
(DRAW_CLIP).

The editor is self-contained. It plugs into the tutorial panel
(tutorials.EDITORS), so tutorials play without it.
"""

import json
import os
import re
import shutil

import bpy  # type: ignore

from . import errors, media, reg, trim, tutorials

TEST_NAMES = (("is", "Is", "The value is this"), ("is_not", "Is Not", "The value is anything but this"),
              ("at_least", "At Least", "A number this or more"), ("at_most", "At Most", "A number this or less"),
              ("changed", "Changed", "The value differs from when the step began"),
              ("count_at_least", "Count At Least", "A collection holds this many or more"))
CHECK_KINDS = (("ACTION", "Action", "A Kneady button hauled or clicked, or another operator run, since the "
                "step began"),
               ("HOVER", "Hovered", "A region hovered since the step began"),
               ("PATH", "Property", "A property's value, by its path"),
               ("MODE", "Mode", "Blender is in this mode (OBJECT, POSE, EDIT_MESH, SCULPT...)"),
               ("ACTIVE", "Active Object", "This object is the active one"),
               ("SELECTED", "Selected", "These objects are selected, names split by commas"))
START_MODES = (("KEEP", "Leave the Mode", "The step leaves the mode as it is"),
               ("OBJECT", "Object Mode", ""), ("POSE", "Pose Mode", ""), ("EDIT", "Edit Mode", ""),
               ("SCULPT", "Sculpt Mode", ""), ("WEIGHT_PAINT", "Weight Paint", ""),
               ("VERTEX_PAINT", "Vertex Paint", ""), ("TEXTURE_PAINT", "Texture Paint", ""))
MEDIA_FROM = (("SHARED", "Shared", "The tutorial's shared media"), ("OWN", "Its Own", "Media of this step's own"),
              ("NONE", "None", "No media: text alone"))
SHOW_ME = (("NONE", "None", "No Show Me button"), ("SIDEBAR", "Sidebar Tab", "Open a tab of the 3D view's sidebar"),
           ("PROPERTIES", "Properties Tab", "Open a tab of the Properties editor"))
SOURCES = (("LOCAL", "Local", "The file ships in the tutorial's folder: it works offline, and is never "
              "downloaded"),
           ("HOSTED", "Hosted", "The file is downloaded from where it is hosted - the tutorial's Media URL and its "
            "name, or its own URL - while Allow Online Access is on"))
PROPERTIES_TABS = tuple((t, t.replace("_", " ").title(), "") for t in (
    "TOOL", "RENDER", "OUTPUT", "VIEW_LAYER", "SCENE", "WORLD", "OBJECT", "MODIFIER", "PARTICLES", "PHYSICS",
    "CONSTRAINT", "DATA", "BONE", "BONE_CONSTRAINT", "MATERIAL", "TEXTURE", "SHADERFX"))

_LOADED = {"data": None}           # the tutorial as last loaded or saved, to tell what changed
RECYCLE = os.name == "nt"          # send a deleted tutorial to the Recycle Bin (the tests delete for good)
# What a program draws in the editor:
#   DRAW_EDITOR - fn(layout, context), under the folder
#   DRAW_STEP   - fn(layout, pg, step), under a step's title
#   DRAW_CLIP   - fn(layout, pg, m, k, shared), under a clip's trim: m is the
#                 item, k its index, shared whether it is in the tutorial's
#                 shared set
DRAW_EDITOR, DRAW_STEP, DRAW_CLIP = [], [], []
PREVIEW_EVERY = 0.2                # seconds between the preview's looks at what is edited
_PREVIEW = {"key": None, "step": None}
_PICKS = []                        # the pick list's items, kept alive, as Blender requires for a dynamic list


# -- What is edited --------------------------------------------------------------------------

class KNEADY_PG_tut_line(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty(name="Text")


class KNEADY_PG_tut_value(bpy.types.PropertyGroup):
    path: bpy.props.StringProperty(name="Path", description="Where the value is: scene.kneady_on, "
                                   "objects[\"Arm\"].location - paste one from Copy Full Data Path")
    value: bpy.props.StringProperty(name="Value", description="As JSON: true, 0.5, [1, 0, 0, 0], \"TEXT\"")


class KNEADY_PG_tut_check(bpy.types.PropertyGroup):
    kind: bpy.props.EnumProperty(name="Kind", items=CHECK_KINDS, default="PATH")
    path: bpy.props.StringProperty(name="Path", description="Where the value is: scene.kneady_on - paste one "
                                   "from Copy Full Data Path")
    test: bpy.props.EnumProperty(name="Test", items=TEST_NAMES, default="is")
    value: bpy.props.StringProperty(name="Value", description="For a property, as JSON: true, 0.5, [1, 0, 0, 0]; "
                                    "otherwise the mode, the object's name, or names split by commas")
    operator: bpy.props.StringProperty(name="Operator", description="The operator run: kneady.drag for a Kneady "
                                       "button, or any other by its name, as object.mode_set")
    with_values: bpy.props.StringProperty(name="With", description="What it ran with, as JSON - only these are "
                                          "checked: {\"target\": \"Arm\", \"region\": 1, \"button\": 0}")
    moved: bpy.props.EnumProperty(name="How", items=(("ANY", "Hauled or Clicked", ""), ("HAUL", "Hauled", ""),
                                                     ("CLICK", "Clicked", "")), default="ANY")
    region: bpy.props.StringProperty(name="Region", description="The region's name")
    object: bpy.props.StringProperty(name="Object", description="Only on this object, if given")


class KNEADY_PG_tut_media(bpy.types.PropertyGroup):
    file: bpy.props.StringProperty(name="File", description="The clip's or image's file name")
    label: bpy.props.StringProperty(name="Where to Look", description="Under the clip: In the viewport, "
                                    "Properties > Modifiers")
    paragraph: bpy.props.IntProperty(name="Paragraph", min=0, description="The paragraph it goes with, from 0")
    seconds: bpy.props.FloatProperty(name="Seconds", min=0.0, description="An image's time up, 0 for 4 seconds")
    hold: bpy.props.BoolProperty(name="Hold at End", description="When it has played, stay on its last frame - an "
                                 "image, on it - rather than playing again or going on to the step's next item. "
                                 "The panel's Loop button still plays it again")
    trim_first: bpy.props.IntProperty(name="Trim Start", min=0, description="The first frame that plays, "
                                      "counted from 1 - 0 for its start")
    trim_last: bpy.props.IntProperty(name="Trim End", min=0, description="The last frame that plays - 0 for its "
                                     "end")
    source: bpy.props.EnumProperty(name="Source", items=SOURCES, default="LOCAL")
    url: bpy.props.StringProperty(name="URL", description="Where it is hosted, if not at the tutorial's Media URL")
    watch: bpy.props.StringProperty(name="Watch Link", description="Where to watch it online - a YouTube Short, say: "
                                    "a button in its place opens it when it can't be shown here")
    sha256: bpy.props.StringProperty(name="Fingerprint", description="Written by dev/publish_media.py")
    recorded_blender: bpy.props.StringProperty(name="Blender", description="The Blender it was made in")
    recorded_kneady: bpy.props.StringProperty(name="Kneady", description="The Kneady it was made in")
    show_me: bpy.props.EnumProperty(name="Show Me", items=SHOW_ME, default="NONE")
    show_sidebar: bpy.props.StringProperty(name="Tab", default="Kneady")
    show_properties: bpy.props.EnumProperty(name="Tab", items=PROPERTIES_TABS, default="MODIFIER")
    show_object: bpy.props.StringProperty(name="Object", description="Made active first, if given")
    show_modifier: bpy.props.StringProperty(name="Modifier", description="Opened, if given")
    open: bpy.props.BoolProperty(name="Open", default=True)


class KNEADY_PG_tut_step(bpy.types.PropertyGroup):
    title: bpy.props.StringProperty(name="Title")
    text: bpy.props.CollectionProperty(type=KNEADY_PG_tut_line)
    media_from: bpy.props.EnumProperty(name="Media", items=MEDIA_FROM, default="SHARED")
    media: bpy.props.CollectionProperty(type=KNEADY_PG_tut_media)
    highlight: bpy.props.CollectionProperty(type=KNEADY_PG_tut_line)
    checks: bpy.props.CollectionProperty(type=KNEADY_PG_tut_check)
    start_mode: bpy.props.EnumProperty(name="Mode", items=START_MODES, default="KEEP")
    use_select: bpy.props.BoolProperty(name="Selection", description="The step selects these objects, and "
                                       "only these")
    select: bpy.props.StringProperty(name="Select", description="Object names, split by commas")
    active: bpy.props.StringProperty(name="Active", description="The object made active, if given")
    sets: bpy.props.CollectionProperty(type=KNEADY_PG_tut_value)
    view: bpy.props.StringProperty(name="View", description="The 3D view the step starts in, as JSON")
    sidebar: bpy.props.StringProperty(name="Sidebar Tab", description="A sidebar tab opened, if given")
    show_text: bpy.props.BoolProperty(name="Text", default=True)
    show_media: bpy.props.BoolProperty(name="Media", default=True)
    show_highlight: bpy.props.BoolProperty(name="Highlight", default=False)
    show_checks: bpy.props.BoolProperty(name="Done When", default=False)
    show_start: bpy.props.BoolProperty(name="Start", default=False)


class KNEADY_PG_tutorial(bpy.types.PropertyGroup):
    id: bpy.props.StringProperty(name="Name")
    folder: bpy.props.StringProperty(name="Folder")
    title: bpy.props.StringProperty(name="Title")
    summary: bpy.props.StringProperty(name="Summary", description="What it teaches, in a line: its tooltip")
    order: bpy.props.IntProperty(name="Order", default=100, description="Lower comes first in the menu")
    practice: bpy.props.StringProperty(name="Practice Scene", description="The .blend it runs in, in its folder")
    media_url: bpy.props.StringProperty(name="Media URL", description="Where its clips and images are hosted, "
                                        "https; each file at this address followed by its name")
    playlist: bpy.props.StringProperty(name="Playlist", description="Where the whole tutorial is watched on a "
                                       "phone - a YouTube playlist of its clips, say, https. The panel's phone "
                                       "button shows it as a QR code")
    media: bpy.props.CollectionProperty(type=KNEADY_PG_tut_media)
    steps: bpy.props.CollectionProperty(type=KNEADY_PG_tut_step)
    step_index: bpy.props.IntProperty(name="Step")
    show_about: bpy.props.BoolProperty(name="Tutorial", default=True)
    show_shared: bpy.props.BoolProperty(name="Shared Media", default=False)


# -- tutorial.json <-> the properties ---------------------------------------------------------

def _dumps(value):
    return json.dumps(value)


def _loads(text):
    """A value typed as JSON, or the text itself when it isn't."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def _names(text):
    return [n.strip() for n in text.split(",") if n.strip()]


def _media_in(collection, items):
    collection.clear()
    for entry in items or []:
        if not isinstance(entry, dict):
            continue
        m = collection.add()
        m.file, m.label = entry.get("file", ""), entry.get("label", "")
        m.paragraph, m.seconds = int(entry.get("paragraph", 0)), float(entry.get("seconds") or 0.0)
        m.url, m.sha256 = entry.get("url", ""), entry.get("sha256", "")
        m.source = "HOSTED" if media.hosted(entry) else "LOCAL"
        m.watch = entry.get("watch", "")
        m.hold = entry.get("hold") is True
        pair = tutorials._trim_pair(entry.get("trim"))
        m.trim_first, m.trim_last = pair if pair else (0, 0)
        rec = entry.get("recorded") or {}
        m.recorded_blender, m.recorded_kneady = str(rec.get("blender", "")), str(rec.get("kneady", ""))
        show = entry.get("show_me") or {}
        if "properties" in show:
            m.show_me = "PROPERTIES"
            if show["properties"] in {t for t, _n, _d in PROPERTIES_TABS}:
                m.show_properties = show["properties"]
            m.show_object, m.show_modifier = show.get("object", ""), show.get("modifier", "")
        elif "sidebar" in show:
            m.show_me, m.show_sidebar = "SIDEBAR", show["sidebar"]
        m.open = False


def to_props(data, pg):
    """Copy a tutorial's data into the properties being edited."""
    pg.title, pg.summary = data.get("title", ""), data.get("summary", "")
    pg.order = int(data.get("order", 100))
    pg.practice, pg.media_url = data.get("practice", ""), data.get("media_url", "")
    pg.playlist = data.get("playlist", "")
    _media_in(pg.media, data.get("media"))
    pg.steps.clear()
    for s in data.get("steps", []):
        step = pg.steps.add()
        step.title = s.get("title", "")
        for para in s.get("text", []):
            step.text.add().text = para
        if "media" not in s:
            step.media_from = "SHARED"
        else:
            step.media_from = "OWN" if s["media"] else "NONE"
            _media_in(step.media, s["media"])
        for path in s.get("highlight", []):
            step.highlight.add().text = path
        for cond in s.get("done_when", []):
            c = step.checks.add()
            if "operator" in cond:
                c.kind, c.operator = "ACTION", cond["operator"]
                c.with_values = _dumps(cond["with"]) if cond.get("with") else ""
                c.moved = "ANY" if "moved" not in cond else ("HAUL" if cond["moved"] else "CLICK")
            elif "hovered" in cond:
                c.kind, c.region, c.object = "HOVER", cond["hovered"], cond.get("object", "")
            elif "mode" in cond:
                c.kind, c.value = "MODE", cond["mode"]
            elif "active" in cond:
                c.kind, c.value = "ACTIVE", cond["active"]
            elif "selected" in cond:
                c.kind, c.value = "SELECTED", ", ".join(cond["selected"])
            else:
                c.kind, c.path = "PATH", cond.get("path", "")
                test = next((k for k in cond if k != "path"), "is")
                if test in {t for t, _n, _d in TEST_NAMES}:
                    c.test, c.value = test, _dumps(cond[test])
        start = s.get("start", {})
        step.start_mode = start.get("mode", "KEEP") if start.get("mode") in {m for m, _n, _d in START_MODES} \
            else "KEEP"
        step.use_select = "select" in start
        step.select = ", ".join(start.get("select", []))
        step.active = start.get("active") or ""
        for item in start.get("set", []):
            v = step.sets.add()
            v.path, v.value = item.get("path", ""), _dumps(item.get("value"))
        step.view = _dumps(start["view"]) if "view" in start else ""
        step.sidebar = start.get("sidebar", "")
    pg.step_index = 0


def _media_out(collection):
    out = []
    for m in collection:
        entry = {"file": m.file}
        if m.label:
            entry["label"] = m.label
        entry["paragraph"] = m.paragraph
        if m.seconds > 0:
            entry["seconds"] = round(m.seconds, 3)
        if m.hold:
            entry["hold"] = True
        if m.trim_first or m.trim_last:
            entry["trim"] = [max(m.trim_first, 1), m.trim_last]
        if m.source == "HOSTED":
            entry["hosted"] = True
            if m.url:
                entry["url"] = m.url
            if m.sha256:
                entry["sha256"] = m.sha256
        if m.watch:
            entry["watch"] = m.watch
        if m.recorded_blender or m.recorded_kneady:
            entry["recorded"] = {"blender": m.recorded_blender, "kneady": m.recorded_kneady}
        if m.show_me == "SIDEBAR":
            entry["show_me"] = {"sidebar": m.show_sidebar}
        elif m.show_me == "PROPERTIES":
            show = {"properties": m.show_properties}
            if m.show_object:
                show["object"] = m.show_object
            if m.show_modifier:
                show["modifier"] = m.show_modifier
            entry["show_me"] = show
        out.append(entry)
    return out


def from_props(pg):
    """The properties being edited, as a tutorial's data, in the form
    canonical gives."""
    data = {"format": tutorials.FORMAT, "title": pg.title}
    if pg.summary:
        data["summary"] = pg.summary
    data["order"] = pg.order
    if pg.practice:
        data["practice"] = pg.practice
    if pg.media_url:
        data["media_url"] = pg.media_url
    if pg.playlist:
        data["playlist"] = pg.playlist
    if len(pg.media):
        data["media"] = _media_out(pg.media)
    steps = []
    for step in pg.steps:
        s = {"title": step.title, "text": [line.text for line in step.text]}
        if step.media_from == "OWN":
            s["media"] = _media_out(step.media)
        elif step.media_from == "NONE":
            s["media"] = []
        highlight = [line.text for line in step.highlight if line.text]
        if highlight:
            s["highlight"] = highlight
        checks = []
        for c in step.checks:
            if c.kind == "ACTION":
                cond = {"operator": c.operator}
                found = _loads(c.with_values) if c.with_values else {}
                if isinstance(found, dict) and found:
                    cond["with"] = found
                if c.moved != "ANY":
                    cond["moved"] = c.moved == "HAUL"
                checks.append(cond)
            elif c.kind == "HOVER":
                cond = {"hovered": c.region}
                if c.object:
                    cond["object"] = c.object
                checks.append(cond)
            elif c.kind == "MODE":
                checks.append({"mode": c.value})
            elif c.kind == "ACTIVE":
                checks.append({"active": c.value})
            elif c.kind == "SELECTED":
                checks.append({"selected": _names(c.value)})
            else:
                checks.append({"path": c.path, c.test: _loads(c.value)})
        if checks:
            s["done_when"] = checks
        start = {}
        if step.start_mode != "KEEP":
            start["mode"] = step.start_mode
        if step.use_select:
            start["select"] = _names(step.select)
        if step.active:
            start["active"] = step.active
        sets = [{"path": v.path, "value": _loads(v.value)} for v in step.sets]
        if sets:
            start["set"] = sets
        if step.view:
            start["view"] = _loads(step.view)
        if step.sidebar:
            start["sidebar"] = step.sidebar
        if start:
            s["start"] = start
        steps.append(s)
    data["steps"] = steps
    return data


def from_check(c):
    """One of the editor's Done When checks as tutorial data (for its
    label)."""
    cond = {"operator": c.operator}
    found = _loads(c.with_values) if c.with_values else {}
    if isinstance(found, dict) and found:
        cond["with"] = found
    if c.moved != "ANY":
        cond["moved"] = c.moved == "HAUL"
    return cond


def _canonical_check(c):
    if "operator" in c:
        out = {"operator": c["operator"]}
        if c.get("with"):
            out["with"] = dict(c["with"])
        if "moved" in c:
            out["moved"] = bool(c["moved"])
        return out
    if "hovered" in c:
        return {"hovered": c["hovered"], **({"object": c["object"]} if c.get("object") else {})}
    return dict(c)


def canonical(data):
    """A tutorial's data in the form from_props writes, with defaults filled
    in and empty values dropped, so two versions can be compared."""
    def listed(items):
        out = []
        for e in items:
            entry = {"file": e.get("file", "")}
            if e.get("label"):
                entry["label"] = e["label"]
            entry["paragraph"] = int(e.get("paragraph", 0))
            if e.get("seconds"):
                entry["seconds"] = round(float(e["seconds"]), 3)
            if e.get("hold") is True:
                entry["hold"] = True
            if tutorials._trim_pair(e.get("trim")):
                entry["trim"] = list(e["trim"])
            if media.hosted(e):
                entry["hosted"] = True
                for key in ("url", "sha256"):
                    if e.get(key):
                        entry[key] = e[key]
            if e.get("watch"):
                entry["watch"] = e["watch"]
            rec = e.get("recorded") or {}
            if rec.get("blender") or rec.get("kneady"):
                entry["recorded"] = {"blender": str(rec.get("blender", "")), "kneady": str(rec.get("kneady", ""))}
            if e.get("show_me"):
                entry["show_me"] = dict(e["show_me"])
            out.append(entry)
        return out
    out = {"format": data.get("format", tutorials.FORMAT), "title": data.get("title", "")}
    if data.get("summary"):
        out["summary"] = data["summary"]
    out["order"] = int(data.get("order", 100))
    for key in ("practice", "media_url", "playlist"):
        if data.get(key):
            out[key] = data[key]
    if data.get("media"):
        out["media"] = listed(data["media"])
    steps = []
    for s in data.get("steps", []):
        step = {"title": s.get("title", ""), "text": list(s.get("text", []))}
        if "media" in s:
            step["media"] = listed(s["media"])
        if [h for h in s.get("highlight", []) if h]:
            step["highlight"] = [h for h in s["highlight"] if h]
        if s.get("done_when"):
            step["done_when"] = [_canonical_check(c) for c in s["done_when"]]
        start = {k: v for k, v in (s.get("start") or {}).items()
                 if not (k == "mode" and v == "KEEP") and v not in ("", None) and not (k == "set" and not v)}
        if start:
            step["start"] = start
        steps.append(step)
    out["steps"] = steps
    return out


# -- Picking, making, deleting, saving --------------------------------------------------------

def editing(context=None):
    wm = (context or bpy.context).window_manager
    return getattr(wm, "kneady_tutorial", None)


def _step(pg):
    return pg.steps[pg.step_index] if 0 <= pg.step_index < len(pg.steps) else None


def load(context, tutorial_id):
    """Load the tutorial into the editor."""
    folder, data = tutorials.find(tutorial_id)
    pg = editing(context)
    to_props(data, pg)
    pg.id, pg.folder = tutorial_id, folder
    _LOADED["data"] = canonical(data)
    _PREVIEW.update(key=None, step=None)
    _start_preview()


def sync_preview(context=None):
    """Have the panel over the view show the tutorial being edited, as it is
    now, at the selected step. Whichever of the two steps (the editor's or
    the panel's) moved since last time, the other follows. The preview ends
    when Edit mode or its eye is off, and a tutorial being played comes
    first. Returns whether there is a preview to keep up."""
    context = context or bpy.context
    wm = context.window_manager
    pg = getattr(wm, "kneady_tutorial", None)
    if pg is None or not wm.kneady_tutorial_edit or not wm.kneady_tutorial_preview or not pg.id:
        if tutorials.previewing():
            tutorials.end(context)
        _PREVIEW.update(key=None, step=None)
        return False
    if tutorials.active() and not tutorials.previewing():
        return True
    if tutorials.previewing() and _PREVIEW["step"] is not None and pg.step_index == _PREVIEW["step"] \
        and tutorials.S["step"] != _PREVIEW["step"] and 0 <= tutorials.S["step"] < len(pg.steps):
        pg.step_index = tutorials.S["step"]            # Next or Back was pressed in the panel, so the list follows
    data = from_props(pg)
    key = (pg.id, pg.folder, json.dumps(data, sort_keys=True), pg.step_index)
    if key != _PREVIEW["key"] or not tutorials.previewing():
        tutorials.preview(context, data, pg.folder, pg.id, pg.step_index)
        _PREVIEW["key"] = key
    _PREVIEW["step"] = pg.step_index
    return True


def _preview_tick():
    try:
        tutorials.poll_operators()
        going = sync_preview()
    except Exception:                             # the preview must never take the timer down
        errors.caught("the tutorial preview")
        going = True
    return PREVIEW_EVERY if going else None


def _start_preview():
    if not bpy.app.timers.is_registered(_preview_tick):
        bpy.app.timers.register(_preview_tick, first_interval=0.0, persistent=True)


def changed(pg):
    return bool(pg.id) and _LOADED["data"] is not None and canonical(from_props(pg)) != _LOADED["data"]


def _inside(path, folder):
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _free_name(folder, name):
    base, k, out = name, 2, name
    while os.path.exists(os.path.join(folder, out)):
        out, k = "%s_%d" % (base, k), k + 1
    return out


COPY_SKIPS = shutil.ignore_patterns("Autosaves", "*.blend1", "__pycache__", tutorials.UNPACKED)


def _undo_step(message):
    """Push an undo step for a change to the file's data made by an operator
    that has no undo step of its own: an attached tutorial saved, attached
    or taken off."""
    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:                       # no window to push it in (a test, a script)
        pass


def copy_tutorial(source, author, name, practice):
    """Copy a tutorial's folder into `author` under a free name, with its
    practice scene. A practice scene shared from a sibling folder
    ("../_scenes/arm.blend") is copied in beside it. Returns (the new
    folder, the practice scene's name in it)."""
    os.makedirs(author, exist_ok=True)
    target = os.path.join(author, _free_name(author, name))
    shutil.copytree(source, target, ignore=COPY_SKIPS)
    if practice and os.path.basename(practice) != practice:
        shared = tutorials.practice_path(source, practice)
        if shared is not None and os.path.isfile(shared):
            shutil.copyfile(shared, os.path.join(target, os.path.basename(shared)))
            practice = os.path.basename(shared)
    return target, practice


def _owned(pg):
    """The tutorial's folder inside the folder tutorials are made in. When
    the tutorial is somewhere else (Kneady's own, in an installed copy), it
    is copied there first, with its practice scene and media. An attached
    tutorial keeps its own folder, because it is saved into its item."""
    author = tutorials.author_folder()
    if _inside(pg.folder, author) or tutorials.attached_to(pg.id) is not None:
        return pg.folder
    pg.folder, pg.practice = copy_tutorial(pg.folder, author, pg.id, pg.practice)
    return pg.folder


def save(pg):
    """Write the tutorial to its tutorial.json. An attached tutorial is also
    written into its item, which saving the file keeps. Raises OSError when
    it can't be saved."""
    found = tutorials.attached_to(pg.id)
    if found is not None and tutorials.editable(found[0]):
        raise OSError(tutorials.editable(found[0]))
    folder = _owned(pg)
    data = from_props(pg)
    with open(os.path.join(folder, "tutorial.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if found is not None:
        pg.id = tutorials.attach(found[0], folder, data, found[1])[0]
        _undo_step("Save Attached Tutorial")
    else:
        pg.id = os.path.basename(folder)
    _LOADED["data"] = canonical(data)
    return folder


def slug(title):
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "tutorial"


def new_tutorial(title):
    """Make a tutorial with one step in the folder tutorials are made in,
    and return its name (its folder's name)."""
    author = tutorials.author_folder()
    os.makedirs(author, exist_ok=True)
    name = _free_name(author, slug(title))
    os.makedirs(os.path.join(author, name))
    data = {"format": tutorials.FORMAT, "title": title, "order": 100,
            "steps": [{"title": "First step", "text": ["Say what to do here."]}]}
    with open(os.path.join(author, name, "tutorial.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return name


def shown_where(pg):
    """(shared, step, clip): where in the editor the clip the preview shows
    is (in the tutorial's shared media or a step's own), or None."""
    S = tutorials.S
    if pg is None or not tutorials.previewing() or pg.id != S["id"] or not 0 <= S["step"] < len(pg.steps):
        return None
    step = pg.steps[S["step"]]
    shared = step.media_from == "SHARED"
    items = pg.media if shared else step.media
    return (shared, S["step"], S["clip"] % len(items)) if len(items) else None


def item_at(pg, where):
    """The editor's clip at `where` (as shown_where gives it), or None."""
    if pg is None or where is None:
        return None
    shared, k, c = where
    if shared:
        items = pg.media
    elif 0 <= k < len(pg.steps):
        items = pg.steps[k].media
    else:
        return None
    return items[c] if 0 <= c < len(items) else None


def stamp_versions(m):
    """Mark the clip as made in this Blender and this Kneady."""
    m.recorded_blender = "%d.%d" % tuple(bpy.app.version[:2])
    m.recorded_kneady = tutorials.kneady_version() or ""


def _clip_file(pg, m):
    """The clip's file on this computer, or None. It is looked for first
    where its kind keeps it (a local clip in the tutorial's folder, a hosted
    clip's copy in its separate copies folder), then wherever else it is
    found."""
    if not m.file:
        return None
    path = os.path.join(media_folder(pg, m), m.file)
    return path if os.path.isfile(path) else media.local(pg.id, pg.folder, {"file": m.file})


def _trim_words(pg, m, drawing=False):
    """What the clip's trim keeps, in words, or "" when the clip can't be
    read. With `drawing`, it is also "" while the clip isn't known yet: a
    panel's draw may not load the clip, so it is read on a timer and the
    panel is drawn again."""
    path = _clip_file(pg, m)
    if path is None:
        return ""
    found = trim.known(path) if drawing else trim.info(path)
    if found is None:
        if drawing:
            trim.learn_later(path, tutorials.redraw_panels)
        return ""
    frames, fps = found[0], found[1]
    first, last = tutorials.trim_of(_media_out([m])[0], frames)
    if (first, last) == (1, frames):
        return "%.1f s, not trimmed" % (frames / fps)
    return "Keeps %.1f of %.1f s" % ((last - first + 1) / fps, frames / fps)


def _recycle(path):
    """Send `path` to the Windows Recycle Bin (SHFileOperation, with undo
    allowed and no dialogs). Raises OSError if it cannot."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", ctypes.c_void_p), ("pTo", ctypes.c_void_p),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_void_p)]

    text = os.path.abspath(path) + "\0\0"
    names = (ctypes.c_wchar * len(text))(*text)
    op = SHFILEOPSTRUCTW(None, 3, ctypes.cast(names, ctypes.c_void_p), None, 0x4 | 0x10 | 0x40 | 0x400,
                         False, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code != 0 or op.fAnyOperationsAborted or os.path.exists(path):
        raise OSError(code or 1, "the Recycle Bin refused it (%d)" % code, path)


def delete_tutorial(folder):
    """Delete a tutorial's folder: to the Recycle Bin on Windows, for good
    elsewhere. Only a tutorial in the folder tutorials are made in can be
    deleted."""
    if not _inside(folder, tutorials.author_folder()):
        raise OSError("only a tutorial in your tutorials folder can be deleted")
    if RECYCLE:
        _recycle(folder)
    else:
        shutil.rmtree(folder)


# -- Paths and the scene as it is ------------------------------------------------------------

def normalize(path):
    """Turn a path as Blender's Copy Full Data Path gives it
    (Ctrl+Shift+Alt+C on a field) into the form a tutorial writes:

        bpy.data.objects["Arm"].location -> objects["Arm"].location
        bpy.context.scene.kneady_on      -> scene.kneady_on"""
    p = (path or "").strip()
    p = re.sub(r"\['((?:[^'\\]|\\.)*)'\]", r'["\1"]', p)
    for pattern, root in ((r"^bpy\.context\.(?:scene)\b", "scene"),
                          (r"^bpy\.context\.(?:active_object|object)\b", "object"),
                          (r"^bpy\.context\.window_manager\b", "window_manager"),
                          (r"^bpy\.context\.space_data\b", "space"),
                          (r'^bpy\.data\.scenes\["(?:[^"\\]|\\.)*"\]', "scene"),
                          (r'^bpy\.data\.window_managers\["(?:[^"\\]|\\.)*"\]', "window_manager"),
                          (r"^bpy\.data\.objects\[", "objects[")):
        p = re.sub(pattern, root, p)
    return p


def current_start(context):
    """The scene as it is now, as a step's start: mode, selection, active
    object, the tutorial's 3D view and the sidebar's tab."""
    layer = context.view_layer
    mode = context.mode
    mode = "EDIT" if mode.startswith("EDIT") else ("WEIGHT_PAINT" if mode == "PAINT_WEIGHT" else
                                                  "VERTEX_PAINT" if mode == "PAINT_VERTEX" else
                                                  "TEXTURE_PAINT" if mode == "PAINT_TEXTURE" else mode)
    out = {"mode": mode if mode in {m for m, _n, _d in START_MODES} else "OBJECT",
           "select": sorted(o.name for o in layer.objects if o.select_get()),
           "active": layer.objects.active.name if layer.objects.active is not None else ""}
    a = context.area if context.area is not None and context.area.type == "VIEW_3D" else tutorials.area(context)
    if a is not None:
        rv3d = a.spaces.active.region_3d
        out["view"] = {"location": [round(v, 4) for v in rv3d.view_location],
                       "rotation": [round(v, 5) for v in rv3d.view_rotation],
                       "distance": round(rv3d.view_distance, 4), "perspective": rv3d.view_perspective}
        ui = next((r for r in a.regions if r.type == "UI"), None)
        out["sidebar"] = ui.active_panel_category if a.spaces.active.show_region_ui and ui is not None \
            and ui.active_panel_category else ""
    return out


# -- Operators --------------------------------------------------------------------------------

def pick_items(context=None):
    """The editor's dropdown: every tutorial by its title. The one being
    edited shows its title as typed, saved or not. Greg: "I can change it's
    title but that doesn't change its name in the dropdown list" - it showed
    the saved title until the next save."""
    pg = editing(context)
    return [(tid, _title(pg, tid, data), data.get("summary", "")) for tid, _f, data in tutorials.available()]


def _title(pg, tid, data):
    if pg is not None and pg.id == tid and pg.title.strip():
        return pg.title.strip()
    return data.get("title", tid)


SOURCE_ICONS = {tutorials.KNEADY_HEADING: "PRESET", tutorials.FILE_HEADING: "FILE_BLEND",
                tutorials.YOURS_HEADING: "USER"}


def _pick_items(_self, context):
    # pick_items, with a separator between sources, each with its source's icon
    pg, out, k = editing(context), [], 0
    for g, (heading, entries) in enumerate(tutorials.listed()):
        if g:
            out.append(None)
        for n, (tid, _f, data) in enumerate(entries, tutorials.first_number(entries)):
            out.append((tid, "%d. %s" % (n, _title(pg, tid, data)),
                        "%s. %s" % (heading, data.get("summary", "")) if data.get("summary") else heading,
                        SOURCE_ICONS.get(heading, "PLUGIN"), k))
            k += 1
    _PICKS[:] = out                             # kept alive: Blender reads the strings after this returns
    return _PICKS or [("", "No tutorials yet", "")]


def _picked(self, context):
    if self.kneady_tutorial_pick:
        try:
            load(context, self.kneady_tutorial_pick)
        except LookupError:
            pass


def _preview_toggled(_self, context):
    sync_preview(context)
    _start_preview()


def _edit_toggled(self, context):
    if not self.kneady_tutorial_edit:
        sync_preview(context)                      # the preview goes with Edit mode
        return
    _start_preview()
    pg = self.kneady_tutorial
    if self.kneady_tutorial_edit and not pg.id:
        found = tutorials.available()
        if found:
            pick = self.kneady_tutorial_pick if self.kneady_tutorial_pick else found[0][0]
            try:
                load(context, pick)
            except LookupError:
                pass


class KNEADY_OT_tutorial_new(bpy.types.Operator):
    """Make a tutorial, in your tutorials folder"""
    bl_idname = "kneady.tutorial_new"
    bl_label = "New Tutorial"
    bl_options = {"INTERNAL"}

    title: bpy.props.StringProperty(name="Title", default="My Tutorial", options={"SKIP_SAVE"})

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        if not self.title.strip():
            self.report({"WARNING"}, "A tutorial needs a title")
            return {"CANCELLED"}
        try:
            name = new_tutorial(self.title.strip())
        except OSError as exc:
            self.report({"ERROR"}, "Could not make it: %s" % exc)
            return {"CANCELLED"}
        context.window_manager.kneady_tutorial_pick = name
        load(context, name)
        return {"FINISHED"}


class KNEADY_OT_tutorial_delete(bpy.types.Operator):
    """Delete the tutorial being edited - to the Recycle Bin on Windows"""
    bl_idname = "kneady.tutorial_delete"
    bl_label = "Delete Tutorial"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        pg = editing(context)
        if pg is None or not pg.id:
            return False
        found = tutorials.attached_to(pg.id)
        if found is not None:
            return not tutorials.editable(found[0])
        return _inside(pg.folder, tutorials.author_folder())

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=360, title="Delete %s?" % editing(context).title,
                                                          confirm_text="Delete") \
            if bpy.app.version >= (4, 1, 0) else context.window_manager.invoke_confirm(self, _event)

    def draw(self, context):
        pg = editing(context)
        found = tutorials.attached_to(pg.id)
        if found is not None:
            self.layout.label(text="Taken off %s, its clips and images with it" % found[0].name)
            self.layout.label(text="Ctrl+Z puts it back; saving the file makes it final")
            return
        self.layout.label(text=pg.folder)
        self.layout.label(text="Its practice scene and media go with it" + (", to the Recycle Bin" if RECYCLE
                                                                            else ", for good"))

    def execute(self, context):
        pg = editing(context)
        try:
            if tutorials.attached_to(pg.id) is not None:
                tutorials.detach(pg.id)
                _undo_step("Delete Attached Tutorial")
            else:
                delete_tutorial(pg.folder)
        except (OSError, LookupError) as exc:
            self.report({"ERROR"}, "Could not delete it: %s" % exc)
            return {"CANCELLED"}
        pg.id = pg.folder = ""
        pg.steps.clear()
        pg.media.clear()
        _LOADED["data"] = None
        return {"FINISHED"}


class KNEADY_OT_tutorial_save(bpy.types.Operator):
    """Write the tutorial to its tutorial.json, in your tutorials folder"""
    bl_idname = "kneady.tutorial_save"
    bl_label = "Save Tutorial"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        pg = editing(context)
        if not pg.id:
            return {"CANCELLED"}
        try:
            folder = save(pg)
        except OSError as exc:
            self.report({"ERROR"}, "Could not save it: %s" % exc)
            return {"CANCELLED"}
        # Set the dropdown only when it changed. Setting it loads the tutorial,
        # even when it is set to the value it already had, and a load after a
        # save put the editor back at step 1 (and dropped anything a program
        # kept on the steps).
        wm = context.window_manager
        if wm.kneady_tutorial_pick != pg.id:
            wm.kneady_tutorial_pick = pg.id
        found = tutorials.attached_to(pg.id)
        if found is not None:
            self.report({"INFO"}, "Saved into %s: save the file to keep it" % found[0].name)
        else:
            self.report({"INFO"}, "Saved to %s" % os.path.join(folder, "tutorial.json"))
        return {"FINISHED"}


class KNEADY_OT_tutorial_revert(bpy.types.Operator):
    """Put the tutorial back as it was last saved"""
    bl_idname = "kneady.tutorial_revert"
    bl_label = "Revert"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        pg = editing(context)
        if pg.id:
            load(context, pg.id)
        return {"FINISHED"}


class KNEADY_OT_tutorial_try(bpy.types.Operator):
    """Save, then play the tutorial from the step selected, in this file - its starts change this file's
    scene, which Ctrl+Z puts back"""
    bl_idname = "kneady.tutorial_try"
    bl_label = "Try This Step"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        pg = editing(context)
        if not pg.id:
            return {"CANCELLED"}
        # When this is tried from inside a tutorial played in its practice
        # scene (Write a Tutorial), the way back to the person's own file is
        # passed on to this one. Otherwise Finish left them in the practice
        # scene's copy.
        kept = (tutorials.S["user_file"], tutorials.S["practice"]) if tutorials.can_return() else (None, None)
        try:
            folder = save(pg)
            tutorials.end(context)
            tutorials.begin(context, tutorials.id_of(folder), *kept)
            if pg.step_index:
                tutorials.enter(context, pg.step_index)
        except (OSError, LookupError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class KNEADY_OT_tutorial_folder(bpy.types.Operator):
    """Choose the folder tutorials are made and saved in"""
    bl_idname = "kneady.tutorial_folder"
    bl_label = "Tutorials Folder"
    bl_options = {"INTERNAL"}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")
    default: bpy.props.BoolProperty(name="Default", options={"SKIP_SAVE"})

    def invoke(self, context, _event):
        if self.default:
            return self.execute(context)
        self.directory = tutorials.author_folder()
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        tutorials.set_author_folder(None if self.default else bpy.path.abspath(self.directory))
        return {"FINISHED"}


class KNEADY_OT_tutorial_practice(bpy.types.Operator):
    """Make this file the tutorial's practice scene: a copy of it saved into the tutorial's folder, as
    practice.blend"""
    bl_idname = "kneady.tutorial_practice"
    bl_label = "Use This File"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        pg = editing(context)
        if not pg.id:
            return {"CANCELLED"}
        try:
            folder = _owned(pg)
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, "practice.blend"), copy=True, compress=True,
                                        relative_remap=False)
        except (OSError, RuntimeError) as exc:
            self.report({"ERROR"}, "Could not save it: %s" % exc)
            return {"CANCELLED"}
        pg.practice = "practice.blend"
        self.report({"INFO"}, "Saved by Blender %s: an older Blender may not open it" %
                    bpy.app.version_string.split()[0])
        return {"FINISHED"}

    @classmethod
    def poll(cls, context):
        pg = editing(context)
        return pg is not None and bool(pg.id) and tutorials.attached_to(pg.id) is None


def _size(n):
    return "%.1f MB" % (n / 1048576.0) if n >= 104858 else "%d KB" % max(1, round(n / 1024.0))


class KNEADY_OT_tutorial_attach(bpy.types.Operator):
    """Attach the tutorial, as it is here, to the active object - its clips and images with it - so it
    travels in this file and into any file the object is linked or appended to. It runs in the file it is in,
    with no practice scene. Save the file to keep it"""
    bl_idname = "kneady.tutorial_attach"
    bl_label = "Attach to Item"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        pg, obj = editing(context), context.active_object
        if pg is None or not pg.id or obj is None or tutorials.attached_to(pg.id) is not None:
            return False
        why = tutorials.editable(obj)
        if why:
            cls.poll_message_set(why)
        return not why

    def execute(self, context):
        pg, obj = editing(context), context.active_object
        name = os.path.basename(os.path.normpath(pg.folder)) or slug(pg.title)
        try:
            tid, count, size = tutorials.attach(obj, pg.folder, from_props(pg), name)
        except OSError as exc:
            self.report({"ERROR"}, "Could not attach it: %s" % exc)
            return {"CANCELLED"}
        _undo_step("Attach Tutorial")
        load(context, tid)
        context.window_manager.kneady_tutorial_pick = tid
        self.report({"INFO"}, "Attached to %s with %d clip%s and image%s, %s: save the file to keep it"
                    % (obj.name, count, "s" if count != 1 else "", "s" if count != 1 else "", _size(size)))
        return {"FINISHED"}


class KNEADY_OT_tutorial_to_folder(bpy.types.Operator):
    """Save a copy of this attached tutorial, as it is here, into your tutorials folder - a tutorial of its
    own, its clips and images with it. The one attached stays"""
    bl_idname = "kneady.tutorial_to_folder"
    bl_label = "Save to Folder"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        pg = editing(context)
        return pg is not None and bool(pg.id) and tutorials.attached_to(pg.id) is not None

    def execute(self, context):
        pg = editing(context)
        _obj, name = tutorials.attached_to(pg.id)
        try:
            target, _practice = copy_tutorial(pg.folder, tutorials.author_folder(), name, None)
            with open(os.path.join(target, "tutorial.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(from_props(pg), f, indent=2, ensure_ascii=False)
                f.write("\n")
        except OSError as exc:
            self.report({"ERROR"}, "Could not save it: %s" % exc)
            return {"CANCELLED"}
        self.report({"INFO"}, "Saved a copy to %s" % target)
        return {"FINISHED"}


LISTS = (("STEPS", "Steps", ""), ("TEXT", "Text", ""), ("MEDIA", "Media", ""), ("HIGHLIGHT", "Highlight", ""),
         ("CHECKS", "Done When", ""), ("SETS", "Values", ""))


def _collection(pg, which, shared):
    if which == "STEPS":
        return pg.steps
    if which == "MEDIA" and shared:
        return pg.media
    step = _step(pg)
    if step is None:
        return None
    return {"TEXT": step.text, "MEDIA": step.media, "HIGHLIGHT": step.highlight, "CHECKS": step.checks,
            "SETS": step.sets}[which]


class KNEADY_OT_tutorial_list(bpy.types.Operator):
    """Add, remove or move one of the tutorial's items"""
    bl_idname = "kneady.tutorial_list"
    bl_label = "Tutorial Item"
    bl_options = {"INTERNAL"}

    which: bpy.props.EnumProperty(items=LISTS, options={"SKIP_SAVE"})
    action: bpy.props.EnumProperty(items=(("ADD", "Add", ""), ("REMOVE", "Remove", ""), ("UP", "Up", ""),
                                          ("DOWN", "Down", "")), options={"SKIP_SAVE"})
    index: bpy.props.IntProperty(default=-1, options={"SKIP_SAVE"})
    shared: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, _context, props):
        return {"ADD": "Add one", "REMOVE": "Remove it", "UP": "Move it up", "DOWN": "Move it down"}[props.action]

    def execute(self, context):
        pg = editing(context)
        items = _collection(pg, self.which, self.shared)
        if items is None:
            return {"CANCELLED"}
        k = self.index if self.index >= 0 else (pg.step_index if self.which == "STEPS" else len(items) - 1)
        if self.action == "ADD":
            item = items.add()
            if self.which == "STEPS":
                item.title = "New step"
                item.text.add().text = "Say what to do here."
                items.move(len(items) - 1, min(k + 1, len(items) - 1))
                pg.step_index = min(k + 1, len(items) - 1)
            elif self.which == "TEXT":
                item.text = "Another paragraph."
            elif self.which == "MEDIA":
                item.label = "In the viewport"
                item.source = "HOSTED" if pg.media_url else "LOCAL"
                step = _step(pg)
                if not self.shared and step is not None:
                    step.media_from = "OWN"
            elif self.which == "SETS":
                item.value = "true"
            elif self.which == "CHECKS":
                item.value = "true"
        elif 0 <= k < len(items):
            if self.action == "REMOVE":
                if self.which == "STEPS" and len(items) == 1:
                    self.report({"WARNING"}, "A tutorial needs a step")
                    return {"CANCELLED"}
                items.remove(k)
                if self.which == "STEPS":
                    pg.step_index = max(0, min(pg.step_index, len(items) - 1))
            else:
                to = k - 1 if self.action == "UP" else k + 1
                if 0 <= to < len(items):
                    items.move(k, to)
                    if self.which == "STEPS":
                        pg.step_index = to
        return {"FINISHED"}


class KNEADY_OT_tutorial_capture(bpy.types.Operator):
    """Take this from the scene as it is now"""
    bl_idname = "kneady.tutorial_capture"
    bl_label = "Use Current"
    bl_options = {"INTERNAL"}

    what: bpy.props.EnumProperty(items=(("MODE", "Mode", ""), ("SELECTION", "Selection", ""), ("VIEW", "View", ""),
                                        ("SIDEBAR", "Sidebar", ""), ("SET", "Value", ""), ("CHECK", "Value", ""),
                                        ("VERSIONS", "Versions", "")), options={"SKIP_SAVE"})
    index: bpy.props.IntProperty(default=-1, options={"SKIP_SAVE"})
    shared: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, _context, props):
        return {"MODE": "The mode Blender is in now", "SELECTION": "What is selected and active now",
                "VIEW": "The 3D view as it is now", "SIDEBAR": "The sidebar's tab open now",
                "SET": "The value at the path, now", "CHECK": "The value at the path, now",
                "VERSIONS": "This Blender's and this Kneady's versions"}[props.what]

    def execute(self, context):
        pg = editing(context)
        step = _step(pg)
        if self.what == "VERSIONS":
            items = _collection(pg, "MEDIA", self.shared)
            if items is None or not 0 <= self.index < len(items):
                return {"CANCELLED"}
            stamp_versions(items[self.index])
            return {"FINISHED"}
        if step is None:
            return {"CANCELLED"}
        now = current_start(context)
        if self.what == "MODE":
            step.start_mode = now["mode"]
        elif self.what == "SELECTION":
            step.use_select, step.select, step.active = True, ", ".join(now["select"]), now["active"]
        elif self.what == "VIEW":
            if "view" not in now:
                self.report({"WARNING"}, "No 3D view to take it from")
                return {"CANCELLED"}
            step.view = _dumps(now["view"])
        elif self.what == "SIDEBAR":
            step.sidebar = now.get("sidebar", "")
        else:
            items = step.sets if self.what == "SET" else step.checks
            if not 0 <= self.index < len(items):
                return {"CANCELLED"}
            item = items[self.index]
            try:
                item.value = _dumps(tutorials.plain(tutorials.resolve(context, item.path)))
            except LookupError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
        return {"FINISHED"}


class KNEADY_OT_tutorial_paste(bpy.types.Operator):
    """Paste a path copied with Copy Full Data Path (Ctrl+Shift+Alt+C over a field)"""
    bl_idname = "kneady.tutorial_paste"
    bl_label = "Paste Path"
    bl_options = {"INTERNAL"}

    which: bpy.props.EnumProperty(items=LISTS, options={"SKIP_SAVE"})
    index: bpy.props.IntProperty(default=-1, options={"SKIP_SAVE"})

    def execute(self, context):
        pg = editing(context)
        items = _collection(pg, self.which, False)
        if items is None or not 0 <= self.index < len(items):
            return {"CANCELLED"}
        path = normalize(context.window_manager.clipboard)
        if not tutorials.ROOT.match(path):
            self.report({"WARNING"}, "Not a full data path: copy one with Ctrl+Shift+Alt+C over a field")
            return {"CANCELLED"}
        item = items[self.index]
        if self.which == "HIGHLIGHT":
            item.text = path
        else:
            item.path = path
        return {"FINISHED"}


# -- In the Kneady tab ------------------------------------------------------------------------

def _toggle(layout, context):
    layout.prop(context.window_manager, "kneady_tutorial_edit", text="", icon="GREASEPENCIL")


def _list_ops(row, which, index, shared=False):
    for action, icon in (("UP", "TRIA_UP"), ("DOWN", "TRIA_DOWN"), ("REMOVE", "X")):
        op = row.operator("kneady.tutorial_list", text="", icon=icon, emboss=False)
        op.which, op.action, op.index, op.shared = which, action, index, shared


def _add(layout, which, text, shared=False):
    op = layout.operator("kneady.tutorial_list", text=text, icon="ADD")
    op.which, op.action, op.shared = which, "ADD", shared


def _draw_media(layout, items, shared, paragraphs):
    for k, m in enumerate(items):
        box = layout.box()
        header, body = box.panel_prop(m, "open")
        row = header.row(align=True)
        row.label(text=m.file or "(no file)", icon="FILE_MOVIE" if tutorials.is_video({"file": m.file})
                  else "FILE_IMAGE")
        _list_ops(row, "MEDIA", k, shared)
        if body is None:
            continue
        col = body.column()
        col.use_property_split, col.use_property_decorate = True, False
        col.row().prop(m, "source", expand=True)
        row = col.row(align=True)
        row.prop(m, "file")
        op = row.operator("kneady.tutorial_media_file", text="", icon="FILEBROWSER")
        op.index, op.shared = k, shared
        text, icon = where_it_is(editing(bpy.context), m)
        col.label(text=text, icon=icon)
        col.prop(m, "label")
        if paragraphs is None or paragraphs > 1:
            col.prop(m, "paragraph")
        if not tutorials.is_video({"file": m.file}):
            col.prop(m, "seconds")
        col.prop(m, "hold")
        if tutorials.is_video({"file": m.file}) or not m.file:
            pg = editing(bpy.context)
            if m.file and _clip_file(pg, m):
                row = col.row(align=True)
                row.prop(m, "trim_first", text="Trim")
                row.prop(m, "trim_last", text="")
                words = _trim_words(pg, m, drawing=True)
                if words:
                    col.label(text=words)
            for fn in DRAW_CLIP:
                fn(col, pg, m, k, shared)
        col.prop(m, "show_me")
        if m.show_me == "SIDEBAR":
            col.prop(m, "show_sidebar")
        elif m.show_me == "PROPERTIES":
            col.prop(m, "show_properties")
            col.prop(m, "show_object")
            col.prop(m, "show_modifier")
        if m.source == "HOSTED":
            col.prop(m, "url")
        col.prop(m, "watch")
        row = col.row(align=True)
        row.prop(m, "recorded_blender")
        row.prop(m, "recorded_kneady")
        op = row.operator("kneady.tutorial_capture", text="", icon="FILE_REFRESH")
        op.what, op.index, op.shared = "VERSIONS", k, shared
        if m.sha256 and m.source == "HOSTED":
            col.label(text="Fingerprint %s..." % m.sha256[:12], icon="LOCKED")
    _add(layout, "MEDIA", "Add Clip or Image", shared)


def _draw_step(layout, pg, step):
    col = layout.column()
    col.use_property_split, col.use_property_decorate = True, False
    col.prop(step, "title")
    for fn in DRAW_STEP:
        fn(layout, pg, step)
    header, body = layout.panel_prop(step, "show_text")
    header.label(text="Text (%d)" % len(step.text))
    if body is not None:
        for k, line in enumerate(step.text):
            row = body.row(align=True)
            row.prop(line, "text", text="")
            row.operator("kneady.tutorial_text", text="", icon="GREASEPENCIL").index = k
            _list_ops(row, "TEXT", k)
        _add(body, "TEXT", "Add Paragraph")
    header, body = layout.panel_prop(step, "show_media")
    header.label(text="Media: %s" % dict((k, n) for k, n, _d in MEDIA_FROM)[step.media_from])
    if body is not None:
        body.row().prop(step, "media_from", expand=True)
        if step.media_from == "OWN":
            _draw_media(body, step.media, False, len(step.text))
        elif step.media_from == "SHARED":
            body.label(text="%d shared, above" % len(pg.media), icon="LINKED")
    header, body = layout.panel_prop(step, "show_highlight")
    header.label(text="Highlight (%d)" % len(step.highlight))
    if body is not None:
        for k, line in enumerate(step.highlight):
            row = body.row(align=True)
            row.prop(line, "text", text="")
            op = row.operator("kneady.tutorial_paste", text="", icon="PASTEDOWN")
            op.which, op.index = "HIGHLIGHT", k
            _list_ops(row, "HIGHLIGHT", k)
        _add(body, "HIGHLIGHT", "Add Field")
    header, body = layout.panel_prop(step, "show_checks")
    header.label(text="Done When (%d)" % len(step.checks))
    if body is not None:
        for k, c in enumerate(step.checks):
            box = body.box()
            row = box.row(align=True)
            row.prop(c, "kind", text="")
            _list_ops(row, "CHECKS", k)
            if c.kind == "ACTION":
                box.label(text=action_label(json.loads(_dumps(from_check(c)))), icon="HAND")
                box.prop(c, "operator", text="")
                box.prop(c, "with_values", text="")
                if c.operator == "kneady.drag":
                    box.row().prop(c, "moved", expand=True)
                continue
            if c.kind == "HOVER":
                row = box.row(align=True)
                row.prop(c, "region", text="")
                row.prop(c, "object", text="")
                continue
            if c.kind == "PATH":
                row = box.row(align=True)
                row.prop(c, "path", text="")
                op = row.operator("kneady.tutorial_paste", text="", icon="PASTEDOWN")
                op.which, op.index = "CHECKS", k
                row = box.row(align=True)
                row.prop(c, "test", text="")
            else:
                row = box.row(align=True)
            row.prop(c, "value", text="")
            if c.kind == "PATH":
                op = row.operator("kneady.tutorial_capture", text="", icon="EYEDROPPER")
                op.what, op.index = "CHECK", k
        _add(body, "CHECKS", "Add Check")
    header, body = layout.panel_prop(step, "show_start")
    header.label(text="Start")
    if body is not None:
        row = body.row(align=True)
        row.prop(step, "start_mode", text="")
        row.operator("kneady.tutorial_capture", text="", icon="EYEDROPPER").what = "MODE"
        row = body.row(align=True)
        row.prop(step, "use_select")
        row.operator("kneady.tutorial_capture", text="Use Current", icon="EYEDROPPER").what = "SELECTION"
        if step.use_select:
            body.prop(step, "select")
        body.prop(step, "active")
        row = body.row(align=True)
        row.label(text="View: set" if step.view else "View: as it is", icon="VIEW3D")
        row.operator("kneady.tutorial_capture", text="Use Current", icon="EYEDROPPER").what = "VIEW"
        if step.view:
            row.operator("kneady.tutorial_clear_view", text="", icon="X")
        row = body.row(align=True)
        row.prop(step, "sidebar")
        row.operator("kneady.tutorial_capture", text="", icon="EYEDROPPER").what = "SIDEBAR"
        body.label(text="Values set:")
        for k, v in enumerate(step.sets):
            box = body.box()
            row = box.row(align=True)
            row.prop(v, "path", text="")
            op = row.operator("kneady.tutorial_paste", text="", icon="PASTEDOWN")
            op.which, op.index = "SETS", k
            _list_ops(row, "SETS", k)
            row = box.row(align=True)
            row.prop(v, "value", text="")
            op = row.operator("kneady.tutorial_capture", text="", icon="EYEDROPPER")
            op.what, op.index = "SET", k
        _add(body, "SETS", "Add Value")


def media_folder(pg, m):
    """Where a clip or image's file belongs on this computer:

    - a local one in the tutorial's folder, which ships;
    - a hosted one's copy where hosted copies are kept
      (media.copies_folder), to upload and to play while writing."""
    if m.source == "LOCAL":
        return pg.folder
    return media.copies_folder(pg.folder, pg.id)


def where_it_is(pg, m):
    """(text, icon): where a clip or image's file is, and whether it ships."""
    if not m.file:
        return "No file yet: choose one", "INFO"
    found = media.local(pg.id, pg.folder, {"file": m.file})
    in_folder = found is not None and os.path.dirname(os.path.abspath(found)) == os.path.abspath(pg.folder)
    if m.source == "LOCAL":
        if in_folder:
            return "In the tutorial's folder: it ships with it", "CHECKMARK"
        if found:
            return "Not in the tutorial's folder: it ships once it's there", "ERROR"
        return "Not on this computer yet", "INFO"
    if in_folder:
        return "In the tutorial's folder, so it ships too", "INFO"
    if found:
        return "Here to play and to upload", "CHECKMARK"
    return "Online only: downloaded when played", "URL"


class KNEADY_OT_tutorial_media_file(bpy.types.Operator):
    """Choose the clip or image's file: a copy goes where it belongs - into the tutorial's folder for a local one;
    for a hosted one, where its copy is kept to upload (dev/media in Kneady's repository)"""
    bl_idname = "kneady.tutorial_media_file"
    bl_label = "Choose File"
    bl_options = {"INTERNAL"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_movie: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})
    filter_image: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})
    index: bpy.props.IntProperty(options={"SKIP_SAVE"})
    shared: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    def _item(self, context):
        items = _collection(editing(context), "MEDIA", self.shared)
        return items[self.index] if items is not None and 0 <= self.index < len(items) else None

    def invoke(self, context, _event):
        if self._item(context) is None:
            return {"CANCELLED"}
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        pg, m = editing(context), self._item(context)
        source = bpy.path.abspath(self.filepath)
        if m is None or not os.path.isfile(source):
            self.report({"WARNING"}, "Choose a clip or an image")
            return {"CANCELLED"}
        try:
            _owned(pg)
            folder = media_folder(pg, m)
            os.makedirs(folder, exist_ok=True)
            target = os.path.join(folder, os.path.basename(source))
            if os.path.normcase(os.path.abspath(source)) != os.path.normcase(os.path.abspath(target)):
                shutil.copyfile(source, target)
        except OSError as exc:
            self.report({"ERROR"}, "Could not copy it: %s" % exc)
            return {"CANCELLED"}
        m.file = os.path.basename(source)
        self.report({"INFO"}, "Copied to %s" % target)
        return {"FINISHED"}


def _region_name(target, rid):
    from . import core
    obj = bpy.data.objects.get(target or "")
    region = core.find_region(obj, rid) if obj is not None else None
    return region.name if region is not None else "region %s" % rid


def action_label(cond):
    """A Done When action in words."""
    with_values = cond.get("with", {})
    if cond.get("operator") == "kneady.drag":
        how = {True: "Hauled", False: "Clicked"}.get(cond.get("moved"), "Hauled or clicked")
        button = with_values.get("button")
        target = with_values.get("target")
        where = _region_name(target, with_values["region"]) if "region" in with_values else "any region"
        return "%s %s on %s%s" % (how, "button %d" % (button + 1) if isinstance(button, int) else "a button",
                                  where, " (%s)" % target if target else "")
    return "Ran %s" % cond.get("operator", "")


class KNEADY_OT_tutorial_text(bpy.types.Operator):
    """Write this paragraph in a wide box"""
    bl_idname = "kneady.tutorial_text"
    bl_label = "Paragraph"
    bl_options = {"INTERNAL"}

    index: bpy.props.IntProperty(options={"SKIP_SAVE"})
    text: bpy.props.StringProperty(name="", options={"SKIP_SAVE"})

    def _line(self, context):
        step = _step(editing(context))
        return step.text[self.index] if step is not None and 0 <= self.index < len(step.text) else None

    def invoke(self, context, _event):
        line = self._line(context)
        if line is None:
            return {"CANCELLED"}
        self.text = line.text
        return context.window_manager.invoke_props_dialog(self, width=720)

    def draw(self, _context):
        self.layout.prop(self, "text")

    def execute(self, context):
        line = self._line(context)
        if line is not None:
            line.text = self.text
        return {"FINISHED"}


class KNEADY_OT_tutorial_clear_view(bpy.types.Operator):
    """The step leaves the view as it is"""
    bl_idname = "kneady.tutorial_clear_view"
    bl_label = "Clear View"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        step = _step(editing(context))
        if step is not None:
            step.view = ""
        return {"FINISHED"}


class KNEADY_UL_tutorial_steps(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active, _propname, index=0):
        layout.prop(item, "title", text="", emboss=False, icon="CHECKBOX_DEHLT" if not item.checks else
                    "CHECKMARK")


def _draw(layout, context):
    wm = context.window_manager
    if not wm.kneady_tutorial_edit:
        return
    pg = wm.kneady_tutorial
    box = layout.box()
    row = box.row(align=True)
    row.prop(wm, "kneady_tutorial_pick", text="")
    row.operator("kneady.tutorial_new", text="", icon="ADD")
    row.operator("kneady.tutorial_delete", text="", icon="TRASH")
    row = box.row(align=True)
    folder = tutorials.author_folder()
    row.label(text="Saved in %s" % folder, icon="FILE_FOLDER")
    row.operator("kneady.tutorial_folder", text="", icon="FILEBROWSER")
    for fn in DRAW_EDITOR:
        fn(box, context)
    if not pg.id:
        box.label(text="Pick a tutorial, or make one with +", icon="INFO")
        return
    held = tutorials.attached_to(pg.id)        # (object, name) for one attached to an item
    if held is not None:
        why = tutorials.editable(held[0])
        box.label(text=why or "Attached to %s: saved with this file" % held[0].name,
                  icon="ERROR" if why else "FILE_BLEND")
    elif not _inside(pg.folder, folder):
        box.label(text="Saving copies it to your folder", icon="INFO")
    row = box.row(align=True)
    if held is not None:
        row.operator("kneady.tutorial_to_folder", icon="FILE_FOLDER")
    else:
        obj = context.active_object
        row.operator("kneady.tutorial_attach", icon="FILE_BLEND",
                     text="Attach to %s" % obj.name if obj is not None else "Attach to Item")
    row = box.row(align=True)
    unsaved = changed(pg)
    row.operator("kneady.tutorial_save", text="Save" + (" *" if unsaved else ""), icon="FILE_TICK",
                 depress=unsaved)
    row.operator("kneady.tutorial_revert", text="", icon="LOOP_BACK")
    row.prop(wm, "kneady_tutorial_preview", text="", icon="HIDE_OFF" if wm.kneady_tutorial_preview else "HIDE_ON")
    row.operator("kneady.tutorial_try", text="Try", icon="PLAY")
    found = tutorials.problems(from_props(pg), pg.folder)
    for problem in found[:6]:
        box.label(text=problem, icon="ERROR")
    data = from_props(pg)
    missing = tutorials.missing_media(data, pg.folder, pg.id)
    stale = [f for f, _why in tutorials.stale_media(data) if f not in missing]
    if missing:
        box.label(text="%d clip%s or image%s to record" % ((len(missing),) + ("s",) * 2 if len(missing) > 1
                                                           else (1, "", "")), icon="SEQUENCE")
    if stale:
        box.label(text="%d made in another version, or not tagged" % len(stale), icon="SEQUENCE")
    header, body = box.panel_prop(pg, "show_about")
    header.label(text="Tutorial")
    if body is not None:
        col = body.column()
        col.use_property_split, col.use_property_decorate = True, False
        col.prop(pg, "title")
        col.prop(pg, "summary")
        col.prop(pg, "order")
        if held is not None:
            col.label(text="Runs in the file it is in", icon="FILE_BLEND")
        else:
            row = col.row(align=True)
            row.prop(pg, "practice")
            row.operator("kneady.tutorial_practice", text="", icon="FILE_BLEND")
        col.prop(pg, "media_url")
        col.prop(pg, "playlist")
    header, body = box.panel_prop(pg, "show_shared")
    header.label(text="Shared Media (%d)" % len(pg.media))
    if body is not None:
        _draw_media(body, pg.media, True, None)
    box.label(text="Steps")
    row = box.row()
    row.template_list("KNEADY_UL_tutorial_steps", "", pg, "steps", pg, "step_index", rows=4)
    col = row.column(align=True)
    for action, icon in (("ADD", "ADD"), ("REMOVE", "REMOVE"), ("UP", "TRIA_UP"), ("DOWN", "TRIA_DOWN")):
        op = col.operator("kneady.tutorial_list", text="", icon=icon)
        op.which, op.action = "STEPS", action
    step = _step(pg)
    if step is not None:
        _draw_step(box.column(), pg, step)


_classes = (KNEADY_PG_tut_line, KNEADY_PG_tut_value, KNEADY_PG_tut_check, KNEADY_PG_tut_media, KNEADY_PG_tut_step,
            KNEADY_PG_tutorial, KNEADY_OT_tutorial_new, KNEADY_OT_tutorial_delete, KNEADY_OT_tutorial_save,
            KNEADY_OT_tutorial_revert, KNEADY_OT_tutorial_try, KNEADY_OT_tutorial_folder,
            KNEADY_OT_tutorial_practice, KNEADY_OT_tutorial_attach, KNEADY_OT_tutorial_to_folder,
            KNEADY_OT_tutorial_list, KNEADY_OT_tutorial_capture,
            KNEADY_OT_tutorial_paste, KNEADY_OT_tutorial_media_file, KNEADY_OT_tutorial_text,
            KNEADY_OT_tutorial_clear_view, KNEADY_UL_tutorial_steps)


def _unsaved(tutorial_id):
    """Whether the editor holds edits to the tutorial not saved yet."""
    pg = editing()
    return bool(pg is not None and pg.id and pg.id == tutorial_id and changed(pg))


def _save_for_play(tutorial_id):
    """Save the editor's edits before the tutorial plays. Returns (the id it
    is saved under, why not or ""). Kneady's own tutorials are copied to
    your folder first, so the id may change."""
    pg = editing()
    if pg is None or pg.id != tutorial_id:
        return tutorial_id, ""
    try:
        folder = save(pg)
    except OSError as exc:
        return tutorial_id, "Could not save it: %s" % exc
    return tutorials.id_of(folder), ""


_EDITOR = {"toggle": _toggle, "draw": _draw, "unsaved": _unsaved, "save": _save_for_play}


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kneady_tutorial = bpy.props.PointerProperty(type=KNEADY_PG_tutorial)
    bpy.types.WindowManager.kneady_tutorial_edit = bpy.props.BoolProperty(
        name="Edit Tutorials", description="Make, change and delete tutorials here", update=_edit_toggled)
    bpy.types.WindowManager.kneady_tutorial_pick = bpy.props.EnumProperty(
        name="Tutorial", description="The tutorial to edit", items=_pick_items, update=_picked)
    bpy.types.WindowManager.kneady_tutorial_preview = bpy.props.BoolProperty(
        name="Show Panel", default=True, update=_preview_toggled,
        description="Show the tutorial in its panel over the view while you edit it, as it is now - its "
                    "steps gone to without their starts (Reset sets one up)")
    if _EDITOR not in tutorials.EDITORS:
        tutorials.EDITORS.append(_EDITOR)


def unregister():
    if bpy.app.timers.is_registered(_preview_tick):
        bpy.app.timers.unregister(_preview_tick)
    if tutorials.previewing():
        tutorials.end()
    if _EDITOR in tutorials.EDITORS:
        tutorials.EDITORS.remove(_EDITOR)
    for name in ("kneady_tutorial_preview", "kneady_tutorial_pick", "kneady_tutorial_edit", "kneady_tutorial"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
    _LOADED["data"] = None
