"""Tutorials: follow-along lessons in the 3D view, Greg's design, planned with
Desktop Claude. Each step shows:

- short vertical clips of the gesture, or still images, in a panel over the
  left side of the view (overlay.py);
- a paragraph of text tied to each clip;
- Kneady's own sidebar, highlighted live rather than recorded, so a lesson
  does not go stale when the panel changes.

A step can watch for what it asks the person to do and tick itself off.

**A tutorial is data, never a script.** It is a folder holding
tutorial.json, its clips and images and, if it has one, its practice scene.
That makes it easy to write and safe to take from someone else: whatever a
step checks or sets is a property named by a path, the way a driver names
one, and resolved through Blender's own path_resolve, never Python's eval.

    {"format": 1, "title": "Quick Start", "summary": "...", "order": 1,
     "practice": "practice.blend",
     "media": [...the shared set, for steps without their own...],
     "steps": [{
        "title": "Turn Kneady on",
        "text": ["A paragraph.", "Another - its clip's: Sidebar > Kneady."],
        "media": [{"file": "turn_on.mp4", "label": "In the viewport header",
                   "paragraph": 1, "recorded": {"blender": "5.2", "kneady": "1.0.0"},
                   "show_me": {"sidebar": "Kneady"}},
                  {"file": "where.png", "seconds": 4}],
        "highlight": ["scene.kneady_on"],
        "done_when": [{"path": "scene.kneady_on", "is": true}],
        "start": {"mode": "OBJECT", "select": ["Arm"], "active": "Arm",
                  "set": [{"path": "scene.kneady_on", "value": false}],
                  "view": {"location": [0, 0, 1], "rotation": [1, 0, 0, 0],
                           "distance": 6, "perspective": "PERSP"},
                  "sidebar": "Kneady"}}]}

**Media, a step's own or the tutorial's.** Greg: "Each page should be able
to have a selection of videos/images or all share a single set". A step's
`media` list is its own (`[]` for none). A step without the key shows the
tutorial's shared set. Moving between two steps that share the set keeps its
place, with the clip playing on, so one clip can run under several pages of
text. A shared item lights its `paragraph` on whichever step has that
paragraph. An image shows for its `seconds` before the next item.

**At an item's end.** Greg asked: "Can a video or gif stay on the final
frame when done?" A clip alone in its step plays again; a clip that is one
of several goes on to the next. `"hold": true` stays on the last frame
instead (or, for an image, stays on the image). The panel's Loop button
plays the item showing again and again, whatever the item says. Its Pause
button pauses it, and Play on an item held at its end starts it over. Both
apply to that item only: the next one starts as it says. `end_of` is the
rule.

**Trimmed.** Greg asked: "Could it be possible to trim the recorded video
without going into an editing app?" `"trim": [first, last]`, typed in the
editor, plays only frames first to last of a clip, counted from 1, with last
0 meaning the clip's end. `trim_of` reads it.

**On a phone.** Greg asked for "a button that shows a QR code for the entire
tutorial". The tutorial's `playlist` (a YouTube playlist of its clips, say)
shows as a QR code behind a phone button in the panel's title row.

A path starts at `scene`, `object` (the active object), `objects["Name"]`,
`window_manager` or `space` (the tutorial's 3D view). A condition is either
a path and one test, or a piece of state. The tests are `is`, `is_not`,
`at_least`, `at_most`, `changed` (since the step began) and
`count_at_least` (for a collection). The state checks are `mode`, `active`
and `selected`. Every condition of a step must hold.

**The practice scene** is opened as a copy in the temporary folder, through
Blender's own Open with its "save changes?" prompt, so the person's file is
never touched. Return to My File opens their file again. Opening a file
clears Blender's undo history, so their work is saved but not their undo. A
tutorial without a practice scene runs in the file that is open. Several
tutorials may share one scene: a practice path is read relative to the
tutorial's folder and may reach a sibling folder in the same tutorials folder
(`"../_scenes/arm.blend"`), never past it.

**Where tutorials come from.** Greg: "Right now the idea is that tut's come
along with addons. We also need the ability for tuts to be attached to a
file". The menu lists each source under its own heading (`listed`):

- **Kneady's own**: its `tutorials/`, and any folder a program adds
  (FOLDERS).
- **An add-on's**: a `kneady_tutorials/` folder in any enabled add-on's own
  folder (addon_folders). The add-on calls nothing of Kneady's, because
  extensions cannot depend on one another. So it works for any add-on, and
  for Digit, which carries its own Kneady.
- **In This File**: tutorials attached to an object, the item they teach,
  usually a rig (attached). The tutorial.json and every clip and image it
  names are stored on the object, so the tutorial travels wherever the
  object goes: saved in its file, appended or linked into another (an
  animator links a rig). It plays from a copy unpacked into a folder of its
  own, and runs in the file it is in, with no practice scene. A rigger writes
  one like any other tutorial, then uses Attach to Item in the editor. Like
  every tutorial it is data: a file from someone else that carries tutorials
  runs nothing.
- **Yours**: the folder tutorials are made in (author_folder).

A tutorial's id is its folder's name. An attached tutorial's id starts with
FILE_PREFIX. When two tutorials have the same name, the one from the later
source is listed.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

import bpy  # type: ignore
from mathutils import Quaternion  # type: ignore

from . import core, errors, media, reg

FORMAT = 1
HERE = os.path.dirname(os.path.abspath(__file__))
# where tutorials are found, each a folder holding tutorial.json: Kneady's
# own, then any a test or a program adds
FOLDERS = [os.path.join(HERE, "tutorials")]
ADDON_FOLDER = "kneady_tutorials"  # in an add-on's own folder: its tutorials, listed while it is enabled
ADDONS = None                      # the add-ons' module names looked in: None for those enabled (tests set a list)
ATTACHED = "_kneady_tutorials"     # on an object: the tutorials attached to it ("_": not shown in Custom Properties)
ATTACHED_CACHE = None              # where attached tutorials are unpacked: None for the temporary folder
FILE_PREFIX = "@"                  # an attached tutorial's id: "@<object>/<name>"
KNEADY_HEADING, FILE_HEADING, YOURS_HEADING = "Kneady", "In This File", "Yours"
CHECK_EVERY = 0.3                  # seconds between a step's checks
ADVANCE_AFTER = 0.5                # seconds a step shows done before the next comes on (advance);
                                   # 1.0 until Greg: "The delay felt about twice too long"

ROOT = re.compile(r'^(scene|object|window_manager|space|objects\["((?:[^"\\]|\\.)*)"\])(?:\.(.+))?$')
TESTS = ("is", "is_not", "at_least", "at_most", "changed", "count_at_least")
STATE_TESTS = ("mode", "active", "selected")
ACTION_KEYS = {"operator": ("operator", "with", "moved"), "hovered": ("hovered", "object")}
START_KEYS = ("mode", "select", "active", "set", "view", "sidebar")
SHOW_ME_KEYS = ("sidebar", "properties", "object", "modifier")
STEP_KEYS = ("title", "text", "media", "highlight", "done_when", "start")
MEDIA_KEYS = ("file", "label", "paragraph", "recorded", "show_me", "seconds", "hosted", "url", "sha256", "watch",
              "hold", "trim")
# what plays as a clip; anything else is a still image
VIDEO = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi")
STILL_SECONDS = 4.0                # how long an image shows before the next item, unless it says

# The tutorial playing now. It holds the tutorial (its id, folder and data),
# the step and the clip, which steps are done, what a step's `changed` tests
# compare with, whether the panel shows, and the file to go back to. It also
# holds whether the item showing is paused, whether it is looped (None: as the
# item says), whether the QR code shows, and done_at, when the person did the
# step (None: not done, or already done when the step began). It is kept in
# Python, so it outlives a file being opened, such as the practice scene.
S = {"id": None, "folder": None, "data": None, "number": None, "step": 0, "clip": 0, "done": set(), "baseline": {},
     "event_mark": 0, "done_at": None,
     "shown": True, "follow": True, "playing": True, "loop": None, "qr": False, "scroll": 0.0, "preview": False,
     "practice": None, "user_file": None, "pending": None, "area": None, "toolbar": {}}

_FOUND = {}                        # tutorial.json path -> (its modified time, its data)


# -- Finding and checking tutorials ------------------------------------------------------

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# -- Where tutorials are made ------------------------------------------------------------

CONFIG = None                      # where the folder is kept: None for Blender's config folder
_AUTHOR = {"folder": None, "read": False}
_KEPT = {"values": None}           # the author's settings, read once from the config file


def _config_file():
    if CONFIG is not None:
        return CONFIG
    if bpy.app.factory_startup:
        return None
    folder = bpy.utils.user_resource("CONFIG", path="kneady", create=False)
    return os.path.join(folder, "tutorials.json") if folder else None


def config(key, default=None):
    """One of the author's settings, such as the tutorials folder or the
    recording window's size. They are kept in Blender's config folder, as
    Help is, so they hold for every file."""
    target = _config_file()
    if _KEPT["values"] is None or _KEPT.get("file") != target:      # a test may point it elsewhere
        _KEPT.update(values={}, file=target)
        try:
            with open(target, encoding="utf-8") as f:
                found = json.load(f)
            if isinstance(found, dict):
                _KEPT["values"] = found
        except (TypeError, OSError, ValueError, AttributeError):
            pass
    return _KEPT["values"].get(key, default)


def keep(key, value):
    """Save one of the author's settings, leaving the others as they are."""
    config(key)
    _KEPT["values"][key] = value
    target = _config_file()
    if target is None:
        return
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(_KEPT["values"], f, indent=1)
    except OSError as exc:
        print("Kneady: could not keep %s: %s" % (key, exc))


def default_author_folder():
    """Where tutorials are made unless the person chooses otherwise:

    - in a checkout of Kneady's repository, its own tutorials/, so they ship
      with it;
    - when installed, the extension's user folder (Kneady's, or that of the
      add-on carrying it), which an update leaves alone."""
    if os.path.isdir(os.path.join(HERE, "dev")):
        return os.path.join(HERE, "tutorials")
    package = __package__ or ""
    if package.startswith("bl_ext."):
        try:
            return bpy.utils.extension_path_user(".".join(package.split(".")[:3]), path="tutorials", create=True)
        except (ValueError, AttributeError, OSError):
            pass
    return bpy.utils.user_resource("DATAFILES", path=os.path.join("kneady", "tutorials"), create=True)


def author_folder():
    """The folder tutorials are made and saved in: the person's choice
    (kept in Blender's config folder, as Help is), else the default."""
    if not _AUTHOR["read"]:
        _AUTHOR["read"] = True
        _AUTHOR["folder"] = config("folder")
    chosen = _AUTHOR["folder"]
    return chosen if chosen and os.path.isdir(chosen) else default_author_folder()


def set_author_folder(path):
    """Set the folder tutorials are made in; None or "" for the default."""
    _AUTHOR.update(folder=path or None, read=True)
    keep("folder", path or None)


_TITLES = {}                       # an add-on's module name -> the name it is listed under


def _inside(path, folder):
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _addon_title(name, module):
    """The name an add-on goes by in the Preferences, used as its tutorials'
    heading. It comes from the manifest or bl_info, else the module's name."""
    if name not in _TITLES:
        title = None
        try:
            import addon_utils  # type: ignore
            title = addon_utils.module_bl_info(module).get("name")
        except Exception:                       # a module the Preferences can't describe
            title = None
        _TITLES[name] = title or name.split(".")[-1].replace("_", " ").title()
    return _TITLES[name]


def addon_folders():
    """[(heading, folder)]: the kneady_tutorials/ folder of each enabled
    add-on that has one, under the add-on's name. It is looked for in the
    add-on's own folder, so the add-on needs nothing of Kneady's. That way
    Digit's tutorials stay Digit's, even though Digit carries its own
    Kneady."""
    if ADDONS is not None:
        names = list(ADDONS)
    else:
        try:
            names = list(bpy.context.preferences.addons.keys())
        except AttributeError:                  # no preferences yet, at startup
            names = []
    out = []
    for name in names:
        module = sys.modules.get(name)
        path = getattr(module, "__file__", None)
        if not path:
            continue
        folder = os.path.join(os.path.dirname(os.path.abspath(path)), ADDON_FOLDER)
        if os.path.isdir(folder):
            out.append((_addon_title(name, module), folder))
    return out


def sources():
    """[(heading, folder)]: where tutorials are found, in order. First
    Kneady's own and any a test or a program adds, then each add-on's, and
    last the one tutorials are made in. A folder that appears twice is
    listed only the first time."""
    out, seen = [], set()
    for heading, root in [(KNEADY_HEADING, f) for f in FOLDERS] + addon_folders() + [(YOURS_HEADING,
                                                                                      author_folder())]:
        key = os.path.normcase(os.path.abspath(root)) if root else None
        if key and key not in seen:
            seen.add(key)
            out.append((heading, root))
    return out


def folders():
    """Every folder tutorials are found in (sources)."""
    return [root for _heading, root in sources()]


def _by_order(entries):
    return sorted(entries, key=lambda t: (t[2].get("order", 100), str(t[2].get("title", t[0]))))


def listed():
    """[(heading, [(id, folder, data)])]: every tutorial found, under the
    heading of where it comes from (sources, with In This File before Yours).
    Each list is sorted by `order`, then title. When two have the same name,
    the later source's is listed, so a tutorial copied into the folder
    tutorials are made in, and changed there, is the one that shows. One
    that cannot be read is left out, with a note in the console."""
    found, headings = {}, []
    for heading, root in sources():
        if heading == YOURS_HEADING and FILE_HEADING not in headings:
            headings.append(FILE_HEADING)
        if heading not in headings:
            headings.append(heading)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if name.startswith(("_", ".")):          # _scenes and the like: shared, never a tutorial
                continue
            path = os.path.join(root, name, "tutorial.json")
            if not os.path.isfile(path):
                continue
            try:
                stamp = os.path.getmtime(path)
                if _FOUND.get(path, (None,))[0] != stamp:
                    _FOUND[path] = (stamp, load(path))
            except (OSError, ValueError) as exc:
                print("Kneady: cannot read the tutorial %s: %s" % (path, exc))
                continue
            data = _FOUND[path][1]
            if isinstance(data, dict):
                found[name] = (heading, (name, os.path.dirname(path), data))
    if FILE_HEADING not in headings:
        # no Yours of its own: in a checkout of Kneady's repository the folder
        # tutorials are made in is Kneady's own, listed once, under Kneady.
        # In This File still has to be there, or a tutorial attached to the
        # file is never listed (and find("@...") cannot find it)
        headings.append(FILE_HEADING)
    groups = {heading: [] for heading in headings}
    for heading, entry in found.values():
        groups[heading].append(entry)
    groups[FILE_HEADING] = attached()
    return [(heading, _by_order(groups[heading])) for heading in headings if groups[heading]]


def available():
    """[(id, folder, data)]: every tutorial found, in listed order."""
    return [entry for _heading, entries in listed() for entry in entries]


def first_number(entries):
    """The number a source's list of tutorials counts from. It is 0 when the
    first one comes before the course, at order 0, like Kneady's Learn,
    Inform and Quiet. Greg: "It would be the actual first tutorial but
    wouldn't be numbered 1. It would be numbered 0". Otherwise it is 1."""
    return 0 if entries and entries[0][2].get("order", 100) <= 0 else 1


def number_of(tutorial_id):
    """A tutorial's number, or None. It is the tutorial's place among its
    source's tutorials, as the menu numbers them, so Kneady's own read as a
    course to follow. Greg: "Tutorials should also be numbered"."""
    for _heading, entries in listed():
        for k, (tid, _folder, _data) in enumerate(entries):
            if tid == tutorial_id:
                return k + first_number(entries)
    return None


def titled(data, tutorial_id, number=None):
    """A tutorial's title as it shows: "2. Change the Default Controls"."""
    title = (data or {}).get("title") or tutorial_id or ""
    return "%d. %s" % (number, title) if number is not None else title


def find(tutorial_id):
    for tid, folder, data in available():
        if tid == tutorial_id:
            if tid in _ATTACHED:
                unpack(tid)
            return folder, data
    raise LookupError("No tutorial %r" % tutorial_id)


def id_of(folder):
    """The id of the tutorial in `folder`: its name, or an attached one's."""
    for tid, info in _ATTACHED.items():
        if _same_folder(info["folder"], folder):
            return tid
    return os.path.basename(os.path.normpath(folder))


def _same_folder(a, b):
    return bool(a) and bool(b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# -- Attached to an object, in the file ------------------------------------------------------

_ATTACHED = {}                     # id -> {object, library, name, folder, sha}: as last listed
_PARSED = {}                       # an attached tutorial's sha -> its data
UNPACKED = ".packed"               # in an attached tutorial's folder: the sha of what it holds


def plain_name(name):
    """Whether `name` is a bare file name: no folder, and not hidden. Every
    clip and image a tutorial names must be one, so a tutorial from someone
    else's file is never written or read anywhere but its own folder."""
    return (isinstance(name, str) and bool(name.strip()) and name == os.path.basename(name)
            and "/" not in name and "\\" not in name and ":" not in name and not name.startswith(".")
            and name != "tutorial.json")


def _content_sha(text, files):
    h = hashlib.sha256(text.encode("utf-8"))
    for name in sorted(files):
        h.update(b"\0" + name.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(bytes(files[name])).digest())
    return h.hexdigest()


def attached_root():
    root = ATTACHED_CACHE or os.path.join(tempfile.gettempdir(), "Kneady Attached Tutorials")
    os.makedirs(root, exist_ok=True)
    return root


def _working_folder(obj, name):
    """Where the tutorial `name` attached to `obj` is unpacked: a folder of
    its own for this file, object and name, so editing it always happens in
    the same place."""
    key = "\0".join((bpy.data.filepath or "", obj.name_full, name))
    return os.path.join(attached_root(), hashlib.sha1(key.encode("utf-8")).hexdigest()[:16])


def _object(info):
    library = info["library"]
    try:
        return bpy.data.objects.get((info["object"], library))
    except (TypeError, KeyError):
        return None


def attached():
    """[(id, folder, data)]: the tutorials attached to the file's objects,
    linked ones included. Each is listed once, however many objects carry
    the same one (five copies of a rig in a shot). The folder is where it is
    unpacked to play (find)."""
    _ATTACHED.clear()
    out, seen = [], set()
    for obj in bpy.data.objects:
        group = obj.get(ATTACHED)
        if group is None or not hasattr(group, "keys"):
            continue
        for name in sorted(group.keys()):
            entry = group[name]
            if not hasattr(entry, "get"):
                continue
            sha, text = entry.get("sha"), entry.get("tutorial")
            if not isinstance(sha, str) or not isinstance(text, str) or sha in seen:
                continue
            if sha not in _PARSED:
                try:
                    data = json.loads(text)
                except ValueError as exc:
                    print("Kneady: cannot read the tutorial %s attached to %s: %s" % (name, obj.name_full, exc))
                    data = None
                if isinstance(data, dict):
                    data.pop("practice", None)        # it runs in the file it is in
                _PARSED[sha] = data
            data = _PARSED[sha]
            if not isinstance(data, dict):
                continue
            seen.add(sha)
            tid = "%s%s/%s" % (FILE_PREFIX, obj.name_full, name)
            folder = _working_folder(obj, name)
            _ATTACHED[tid] = {"object": obj.name, "library": obj.library.filepath if obj.library else None,
                              "name": name, "folder": folder, "sha": sha}
            out.append((tid, folder, data))
    return out


def attached_to(tutorial_id):
    """(object, name) the tutorial is attached to, or None for a tutorial in
    a folder."""
    info = _ATTACHED.get(tutorial_id)
    if info is None and isinstance(tutorial_id, str) and tutorial_id.startswith(FILE_PREFIX):
        attached()
        info = _ATTACHED.get(tutorial_id)
    if info is None:
        return None
    obj = _object(info)
    return (obj, info["name"]) if obj is not None else None


def editable(obj):
    """Why an attached tutorial on `obj` can't be changed here, or "". A
    linked object's tutorials belong to the file it is linked from."""
    if obj.library is not None or obj.override_library is not None:
        return "It is attached to %s, linked from another file: change it in that file" % obj.name
    return ""


def unpack(tutorial_id):
    """Write the attached tutorial out to its folder, as it is on its object,
    and return the folder. It is written only when the folder holds
    something else (UNPACKED). Every file is written under its own bare name
    in that folder alone (plain_name), whatever the file it came in says."""
    info = _ATTACHED[tutorial_id]
    folder = info["folder"]
    marker = os.path.join(folder, UNPACKED)
    try:
        with open(marker, encoding="utf-8") as f:
            if f.read().strip() == info["sha"]:
                return folder
    except OSError:
        pass
    obj = _object(info)
    if obj is None:
        raise LookupError("No tutorial %r" % tutorial_id)
    entry = obj[ATTACHED][info["name"]]
    if _inside(folder, attached_root()) and os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    data = _PARSED[info["sha"]]
    with open(os.path.join(folder, "tutorial.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    files = entry.get("files")
    for name in (files.keys() if hasattr(files, "keys") else []):
        if not plain_name(name):
            print("Kneady: %s names a file %r; it is left out" % (tutorial_id, name))
            continue
        with open(os.path.join(folder, name), "wb") as f:
            f.write(bytes(files[name]))
    with open(marker, "w", encoding="utf-8") as f:
        f.write(info["sha"])
    return folder


def attach(obj, folder, data, name):
    """Attach the tutorial (`data`, with its files in `folder`) to `obj`
    under `name`, replacing one of that name already there. What is stored:

    - its tutorial.json, without a practice scene, since it runs in the
      file it is in;
    - every clip and image it names that is in its folder. Hosted ones are
      left to download as usual.

    Returns (its id, the number of files it took, their total bytes)."""
    why = editable(obj)
    if why:
        raise OSError(why)
    data = {key: value for key, value in data.items() if key != "practice"}
    files = {}
    for entry in all_media(data):
        if media.hosted(entry) or not plain_name(entry["file"]):
            continue
        path = os.path.join(folder, entry["file"])
        if os.path.isfile(path):
            with open(path, "rb") as f:
                files[entry["file"]] = f.read()
    text = json.dumps(data, indent=2, ensure_ascii=False)
    sha = _content_sha(text, files)
    if obj.get(ATTACHED) is None or not hasattr(obj.get(ATTACHED), "keys"):
        obj[ATTACHED] = {}
    obj[ATTACHED][name] = {"tutorial": text, "files": files, "sha": sha}
    _PARSED.pop(sha, None)
    attached()
    tid = "%s%s/%s" % (FILE_PREFIX, obj.name_full, name)
    working = _ATTACHED.get(tid, {}).get("folder")
    if working and _same_folder(working, folder):
        # saved from its own unpacked folder, so the folder already holds
        # what is attached now
        with open(os.path.join(folder, UNPACKED), "w", encoding="utf-8") as f:
            f.write(sha)
    _changed()
    return tid, len(files), sum(len(b) for b in files.values())


def detach(tutorial_id):
    """Take the attached tutorial off its object."""
    found = attached_to(tutorial_id)
    if found is None:
        raise LookupError("No tutorial %r" % tutorial_id)
    obj, name = found
    why = editable(obj)
    if why:
        raise OSError(why)
    group = obj[ATTACHED]
    del group[name]
    if not group.keys():
        del obj[ATTACHED]
    attached()
    _changed()


def file_has_tutorials():
    """Whether an object in the open file carries a tutorial."""
    return any(obj.get(ATTACHED) is not None for obj in bpy.data.objects)


def practice_path(folder, practice):
    """The practice scene's file, read relative to the tutorial's folder, or
    None when it is not a .blend there. It is the tutorial's own
    practice.blend, or one shared from a sibling folder in the same
    tutorials folder ("../_scenes/arm.blend")."""
    if not isinstance(practice, str) or not practice.lower().endswith(".blend") or folder is None:
        return None
    path = os.path.normpath(os.path.join(os.path.abspath(folder), practice))
    return path if _inside(path, os.path.dirname(os.path.abspath(folder))) else None


def _path_ok(path):
    return isinstance(path, str) and ROOT.match(path) is not None


def _condition_problems(cond):
    if not isinstance(cond, dict):
        return ["a condition is not a {...}"]
    for key, allowed in ACTION_KEYS.items():
        if key in cond:
            extra = [k for k in cond if k not in allowed]
            if extra:
                return ["%s takes only %s, not %s" % (key, ", ".join(allowed), ", ".join(extra))]
            if not isinstance(cond[key], str) or not cond[key]:
                return ["%s needs a name" % key]
            if key == "operator" and "." not in cond[key]:
                return ["operator %r is not an operator's name, as kneady.drag" % cond[key]]
            if not isinstance(cond.get("with", {}), dict):
                return ["%s's with is not a {...}" % key]
            return []
    states = [k for k in STATE_TESTS if k in cond]
    if states:
        return [] if len(cond) == 1 else ["%s stands alone in its condition" % states[0]]
    if not _path_ok(cond.get("path")):
        return ["the path %r does not start with scene, object, objects[\"Name\"], window_manager or space"
                % cond.get("path")]
    tests = [k for k in cond if k != "path"]
    if len(tests) != 1 or tests[0] not in TESTS:
        return ["%s needs one test of %s" % (cond["path"], ", ".join(TESTS))]
    return []


def _media_problems(items, where, paragraphs=None):
    """What is wrong with a list of media. It is either a step's, whose
    number of `paragraphs` is known, or the shared set's, whose paragraph
    refers to whichever step is showing."""
    if not isinstance(items, list):
        return ["%s: media is not a list" % where]
    out = []
    for c, entry in enumerate(items):
        at = "%s, media %d" % (where, c + 1)
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            out.append("%s: no file" % at)
            continue
        if entry["file"] and not plain_name(entry["file"]):
            out.append("%s: %r is not a file's name in the tutorial's folder" % (at, entry["file"]))
        out += ["%s: unknown %s" % (at, key) for key in entry if key not in MEDIA_KEYS]
        para = entry.get("paragraph", 0)
        top = max(paragraphs, 1) if paragraphs is not None else None
        if not isinstance(para, int) or para < 0 or (top is not None and para >= top):
            out.append("%s: paragraph %r is not one of the step's" % (at, para))
        show = entry.get("show_me")
        if show is not None and (not isinstance(show, dict) or not show
                                 or any(key not in SHOW_ME_KEYS for key in show)):
            out.append("%s: show_me takes %s" % (at, ", ".join(SHOW_ME_KEYS)))
        seconds = entry.get("seconds")
        if seconds is not None and (not isinstance(seconds, (int, float)) or seconds <= 0):
            out.append("%s: seconds is not a number above 0" % at)
        if "url" in entry and not media.url_ok(entry["url"]):
            out.append("%s: url is not an https address" % at)
        if "watch" in entry and not (isinstance(entry["watch"], str) and entry["watch"].startswith("https://")):
            out.append("%s: watch is not an https address" % at)
        if "sha256" in entry and not (isinstance(entry["sha256"], str) and media.SHA256.match(entry["sha256"])):
            out.append("%s: sha256 is not 64 hex digits" % at)
        if "hold" in entry and not isinstance(entry["hold"], bool):
            out.append("%s: hold is not true or false" % at)
        if "trim" in entry and _trim_pair(entry["trim"]) is None:
            out.append("%s: trim is not [first, last]: frames from 1, last 0 or past first" % at)
    return out


def _trim_pair(trim):
    """(first, last) of a valid `trim`, or None."""
    if not (isinstance(trim, list) and len(trim) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in trim)):
        return None
    first, last = trim
    return (first, last) if first >= 1 and (last == 0 or last >= first) else None


def problems(data, folder=None):
    """What is wrong with a tutorial's data, in words, or [] when nothing is.
    Clips not recorded yet and images not added yet are not errors;
    missing_media lists them."""
    out = []
    if not isinstance(data, dict):
        return ["tutorial.json is not a {...}"]
    if "media" in data:
        out += _media_problems(data["media"], "the shared media")
    if "media_url" in data and not media.url_ok(data["media_url"]):
        out.append("media_url is not an https address")
    if "playlist" in data and not (isinstance(data["playlist"], str) and data["playlist"].startswith("https://")):
        out.append("playlist is not an https address")
    for entry in all_media(data):
        if media.hosted(entry) and not entry.get("url") and not data.get("media_url"):
            out.append("%s is hosted, but nowhere: give the tutorial a media URL, or the item its own"
                       % entry["file"])
    if data.get("format") != FORMAT:
        out.append("format is %r; this Kneady reads %d" % (data.get("format"), FORMAT))
    if not isinstance(data.get("title"), str) or not data.get("title"):
        out.append("no title")
    practice = data.get("practice")
    if practice is not None:
        if not isinstance(practice, str):
            out.append("practice is not a file name")
        elif folder is not None and practice_path(folder, practice) is None:
            out.append("practice %s is not a .blend in its tutorials folder" % practice)
        elif folder is not None and not os.path.isfile(practice_path(folder, practice)):
            out.append("no practice scene %s" % practice)
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return out + ["no steps"]
    for k, step in enumerate(steps):
        where = "step %d" % (k + 1)
        if not isinstance(step, dict):
            out.append("%s is not a {...}" % where)
            continue
        out += ["%s: unknown %s" % (where, key) for key in step if key not in STEP_KEYS]
        text = step.get("text")
        if not (isinstance(text, list) and text and all(isinstance(p, str) for p in text)):
            out.append("%s: text is not a list of paragraphs" % where)
            text = []
        if "media" in step:
            out += _media_problems(step["media"], where, len(text))
        for path in step.get("highlight", []):
            if not _path_ok(path):
                out.append("%s: cannot highlight %r" % (where, path))
        for cond in step.get("done_when", []):
            out += ["%s: %s" % (where, p) for p in _condition_problems(cond)]
        start = step.get("start", {})
        if not isinstance(start, dict):
            out.append("%s: start is not a {...}" % where)
            continue
        out += ["%s: start has unknown %s" % (where, key) for key in start if key not in START_KEYS]
        for item in start.get("set", []):
            if not isinstance(item, dict) or not _path_ok(item.get("path")) or "value" not in item:
                out.append("%s: start's set needs a path and a value each" % where)
        view = start.get("view")
        if view is not None and not (isinstance(view, dict) and len(view.get("rotation", ())) == 4
                                     and len(view.get("location", ())) == 3
                                     and isinstance(view.get("distance"), (int, float))):
            out.append("%s: view needs location (3), rotation (4) and distance" % where)
    return out


def all_media(data):
    """Every clip and image a tutorial names, the shared set's first, with
    each file listed once."""
    seen, out = set(), []
    lists = [data.get("media", [])] + [s.get("media", []) for s in data.get("steps", []) if isinstance(s, dict)]
    for items in lists:
        for entry in items if isinstance(items, list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("file"), str) and entry["file"] not in seen:
                seen.add(entry["file"])
                out.append(entry)
    return out


def is_video(entry):
    return bool(entry) and os.path.splitext(entry.get("file", ""))[1].lower() in VIDEO


def missing_media(data, folder, tutorial_id=None):
    """The clips and images a tutorial names that are not on this computer
    (in its folder or a checkout's dev/media), still to be recorded or
    added. One hosted online is listed too, because this is for writing
    tutorials."""
    return [e["file"] for e in all_media(data) if media.local(tutorial_id, folder, e) is None]


def kneady_version():
    """This Kneady's version, from its manifest. None for a copy carried
    inside another add-on, which has no manifest of its own."""
    try:
        with open(os.path.join(HERE, "blender_manifest.toml"), encoding="utf-8") as f:
            for line in f:
                found = re.match(r'^version\s*=\s*"([^"]+)"', line)
                if found:
                    return found.group(1)
    except OSError:
        pass
    return None


def stale_media(data, blender=None, kneady=None):
    """[(file, why)] for the clips and images whose `recorded` tag names a
    different Blender or Kneady than this one, and those with no tag. After
    an update, this finds the ones that may show an older interface."""
    blender = blender or "%d.%d" % tuple(bpy.app.version[:2])
    kneady = kneady if kneady is not None else kneady_version()
    out = []
    for entry in all_media(data):
        rec = entry.get("recorded")
        if not isinstance(rec, dict):
            out.append((entry["file"], "no recorded versions"))
            continue
        why = []
        if str(rec.get("blender")) != blender:
            why.append("Blender %s" % rec.get("blender"))
        if kneady is not None and str(rec.get("kneady")) != kneady:
            why.append("Kneady %s" % rec.get("kneady"))
        if why:
            out.append((entry["file"], "recorded in " + ", ".join(why)))
    return out


# -- What the person did ---------------------------------------------------------------------
# A log of actions, for a step to watch for and an editor to record:
# - a region hovered (core's hover hook);
# - a Kneady button dragged or clicked (core's action hook);
# - any other operator Blender keeps in its history (window_manager.operators,
#   which holds operators run from the interface, such as a panel's button).

EVENTS = []                        # (number, kind, data): the last few hundred
_COUNT = [0]
_SEEN_OPS = {"keys": None}         # the operators in Blender's history already logged


def note_event(kind, **data):
    _COUNT[0] += 1
    EVENTS.append((_COUNT[0], kind, data))
    del EVENTS[:-400]


def event_mark():
    return _COUNT[0]


def events_since(mark, kind=None):
    return [d for n, k, d in EVENTS if n > (mark or 0) and (kind is None or k == kind)]


def py_idname(idname):
    """KNEADY_OT_drag -> kneady.drag."""
    if "_OT_" in idname:
        module, name = idname.split("_OT_", 1)
        return "%s.%s" % (module.lower(), name)
    return idname


def op_values(op):
    """What an operator ran with, as plain data."""
    out = {}
    props = getattr(op, "properties", None)
    if props is None:
        return out
    for p in props.bl_rna.properties:
        if p.identifier == "rna_type" or p.type in ("POINTER", "COLLECTION"):
            continue
        try:
            out[p.identifier] = plain(getattr(props, p.identifier))
        except (AttributeError, TypeError):
            pass
    return out


def poll_operators(context=None):
    """Log the operators run since the last look, except Kneady's drag,
    which reports what it did itself (core.acted). The first look only
    learns what was already there."""
    try:
        ops = list((context or bpy.context).window_manager.operators)
    except (AttributeError, ReferenceError):
        return
    keys = [(op.as_pointer(), op.bl_idname) for op in ops]
    if _SEEN_OPS["keys"] is None:
        _SEEN_OPS["keys"] = set(keys)
        return
    for key, op in zip(keys, ops):
        if key in _SEEN_OPS["keys"]:
            continue
        _SEEN_OPS["keys"].add(key)
        name = py_idname(op.bl_idname)
        if name != "kneady.drag":
            note_event("operator", operator=name, values=op_values(op), label=getattr(op, "name", name))
    if len(_SEEN_OPS["keys"]) > 2000:
        _SEEN_OPS["keys"] = set(keys)


def _on_hover(_before, after):
    if after is None or after[1] is None:
        return
    obj = bpy.data.objects.get(after[0])
    region = core.find_region(obj, after[1]) if obj is not None else None
    note_event("hover", object=after[0], region=region.name if region is not None else str(after[1]))


def _on_action(kind, data):
    values = dict(data)
    note_event("operator", operator=kind, values=values,
               label="%s %s on %s" % ("Hauled" if data.get("moved") else "Clicked", data.get("button_name") or
                                     "button %d" % (data.get("button", 0) + 1), data.get("region_name") or "a region"))


# -- Paths: reading, writing, comparing ----------------------------------------------------

def started_in(context):
    """The 3D view a tutorial is started from, as begin() keeps it (S["area"]):
    the one whose sidebar's Kneady tab was clicked. None when started from
    anywhere else - a script, another editor."""
    a = getattr(context, "area", None) if context is not None else None
    return a.as_pointer() if a is not None and a.type == "VIEW_3D" else None


def area(context=None):
    """The 3D view the tutorial plays in: the one it was started in, in
    whichever window that is, while it still exists - else the biggest in the
    first window. None without a window.

    Looked for in every window: started from a second window (a second
    monitor, say), the tutorial plays there. It used to look in the first
    window only, and never kept the view it was started in, so it always
    played in the main window."""
    wm = (context or bpy.context).window_manager
    if S["area"]:
        for win in wm.windows:
            for a in win.screen.areas:
                if a.type == "VIEW_3D" and a.as_pointer() == S["area"]:
                    return a
    best = None
    for a in (wm.windows[0].screen.areas if wm.windows else ()):
        if a.type == "VIEW_3D" and (best is None or a.width * a.height > best.width * best.height):
            best = a
    if best is not None:
        S["area"] = best.as_pointer()
    return best


def _root(context, path):
    found = ROOT.match(path) if isinstance(path, str) else None
    if found is None:
        raise LookupError("%r does not start with scene, object, objects[\"Name\"], window_manager or space"
                          % path)
    name, quoted, rest = found.groups()
    if quoted is not None:
        owner = bpy.data.objects.get(quoted.replace('\\"', '"').replace("\\\\", "\\"))
    elif name == "scene":
        owner = context.scene
    elif name == "object":
        owner = context.view_layer.objects.active
    elif name == "window_manager":
        owner = context.window_manager
    else:
        a = area(context)
        owner = a.spaces.active if a is not None else None
    if owner is None:
        raise LookupError("nothing at %s" % path)
    return owner, rest


def resolve(context, path):
    """The value at `path`. LookupError when there is none."""
    owner, rest = _root(context, path)
    if not rest:
        return owner
    try:
        return owner.path_resolve(rest)
    except (ValueError, TypeError, AttributeError) as exc:
        raise LookupError("nothing at %s" % path) from exc


def _last_dot(rest):
    """Where the last part of a path begins (its last dot outside brackets
    and quotes), or -1."""
    depth, quote, last = 0, False, -1
    k = 0
    while k < len(rest):
        ch = rest[k]
        if quote:
            if ch == "\\":
                k += 1
            elif ch == '"':
                quote = False
        elif ch == '"':
            quote = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "." and depth == 0:
            last = k
        k += 1
    return last


def owner_and_name(context, path):
    """(what holds the property, its name, an index into it or None) for a
    path that ends on a property: scene.kneady_on, objects["Rig"].location[2]."""
    owner, rest = _root(context, path)
    if not rest:
        raise LookupError("%s is not a property" % path)
    cut = _last_dot(rest)
    head, last = (rest[:cut], rest[cut + 1:]) if cut >= 0 else ("", rest)
    index = None
    found = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$", last)
    if found is None:
        raise LookupError("%s does not end on a property" % path)
    name, index = found.group(1), (int(found.group(2)) if found.group(2) is not None else None)
    if head:
        try:
            owner = owner.path_resolve(head)
        except (ValueError, TypeError) as exc:
            raise LookupError("nothing at %s" % path) from exc
    if not hasattr(owner, "bl_rna") or name not in owner.bl_rna.properties:
        raise LookupError("%s has no %s" % (path, name))
    return owner, name, index


def write(context, path, value):
    owner, name, index = owner_and_name(context, path)
    if index is None:
        setattr(owner, name, value)
    else:
        getattr(owner, name)[index] = value


def plain(value):
    """A value as plain data to compare:

    - numbers, text, True and False as they are;
    - arrays and vectors as tuples;
    - a collection as its length;
    - a datablock as its name."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bpy.types.bpy_prop_collection):
        return len(value)
    if isinstance(value, bpy.types.ID):
        return value.name
    try:
        return tuple(plain(v) for v in value)
    except TypeError:
        return value.as_pointer() if hasattr(value, "as_pointer") else str(value)


def same(a, b, tol=1e-4):
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)) or len(a) != len(b):
            return False
        return all(same(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol * max(1.0, abs(b))
    return a == b


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def met(context, cond, baseline=None):
    """Whether one condition of a step holds. An action (an operator run, a
    region hovered) counts only if it happened since the step began."""
    if "operator" in cond:
        for data in events_since(S["event_mark"], "operator"):
            if data["operator"] != cond["operator"]:
                continue
            values = data.get("values", {})
            if any(not same(values.get(k), v) for k, v in cond.get("with", {}).items()):
                continue
            if "moved" in cond and bool(values.get("moved")) != bool(cond["moved"]):
                continue
            return True
        return False
    if "hovered" in cond:
        return any(d["region"] == cond["hovered"] and (not cond.get("object") or d["object"] == cond["object"])
                   for d in events_since(S["event_mark"], "hover"))
    if "mode" in cond:
        return context.mode == cond["mode"]
    if "active" in cond:
        obj = context.view_layer.objects.active
        return obj is not None and obj.name == cond["active"]
    if "selected" in cond:
        chosen = {o.name for o in context.view_layer.objects if o.select_get()}
        return set(cond["selected"]) <= chosen
    try:
        value = plain(resolve(context, cond["path"]))
    except LookupError:
        return False
    test = next(k for k in cond if k != "path")
    want = cond[test]
    if test == "is":
        return same(value, want)
    if test == "is_not":
        return not same(value, want)
    if test in ("at_least", "count_at_least"):
        return _number(value) and _number(want) and value >= want
    if test == "at_most":
        return _number(value) and _number(want) and value <= want
    if test == "changed":
        before = (baseline or {}).get(cond["path"], _MISSING)
        return (before is not _MISSING and not same(value, before, 1e-3)) == bool(want)
    return False


_MISSING = object()


def baseline_of(context, step):
    """What a step's `changed` tests compare with: each path's value as the
    step begins."""
    out = {}
    for cond in step.get("done_when", []):
        if "changed" in cond:
            try:
                out[cond["path"]] = plain(resolve(context, cond["path"]))
            except LookupError:
                pass
    return out


# -- The tutorial going on ----------------------------------------------------------------

def active():
    return S["data"] is not None


def step():
    return S["data"]["steps"][S["step"]] if active() else None


def steps():
    return S["data"]["steps"] if active() else []


def shares(k=None):
    """Whether step `k` (the current one by default) shows the tutorial's
    shared media, because it has none of its own."""
    if not active():
        return False
    k = S["step"] if k is None else k
    return "media" not in S["data"]["steps"][k] and bool(S["data"].get("media"))


def clips():
    """The clips and images the step shows: its own, or the shared set."""
    current = step()
    if current is None:
        return []
    media = current["media"] if "media" in current else S["data"].get("media", [])
    return [c for c in media if isinstance(c, dict)] if isinstance(media, list) else []


def clip():
    found = clips()
    return found[S["clip"] % len(found)] if found else None


def end_of(entry, items, loop=None):
    """What comes at the end of `entry`, one of a step's items (`items` is
    how many there are):

    - "again": it plays again;
    - "next": the step's next item comes on;
    - "hold": it stays on its last frame.

    `loop` is the panel's Loop button for this item, None while untouched.
    A clip plays again when Loop is on, or when Loop is untouched and the
    clip is alone in its step without `hold`. A clip that is one of several,
    without `hold`, goes on to the next. Anything else holds. An image never
    plays again: it goes on, or holds."""
    entry = entry or {}
    video = is_video(entry)
    if loop is None:
        loop = video and items <= 1 and not entry.get("hold")
    if loop and video:
        return "again"
    if loop or entry.get("hold") or items <= 1:
        return "hold"
    return "next"


def trim_of(entry, frames):
    """(first, last): which frames of `entry`, a clip of `frames` frames,
    play. Counted from 1 and kept inside the clip; an untrimmed clip plays
    all of them."""
    frames = max(int(frames), 1)
    pair = _trim_pair((entry or {}).get("trim"))
    if pair is None:
        return 1, frames
    first = min(pair[0], frames)
    return first, frames if pair[1] == 0 else min(max(pair[1], first), frames)


def looping():
    """Whether the item showing plays again at its end, which lights the
    panel's Loop button."""
    return end_of(clip(), len(clips()), S["loop"]) == "again"


def playlist():
    """The link for watching the whole tutorial on a phone, shown as its QR
    code, or ""."""
    link = S["data"].get("playlist", "") if active() else ""
    return link if isinstance(link, str) and link.startswith("https://") else ""


def clip_where(entry=None):
    """(path, status, detail) for `entry`, or the item showing: on this
    computer, downloading, offline, failed or missing (media.find)."""
    entry = entry if entry is not None else clip()
    if not entry or not S["folder"]:
        return None, media.MISSING, None
    if S["preview"] and not media.hosted(entry):
        # A tutorial being written. A local item's file comes from this
        # computer, or from an earlier download, and is never fetched. A
        # hosted item does download, so the author can check what was put
        # online.
        path = media.local(S["id"], S["folder"], entry) if entry.get("file") else None
        if path is None and entry.get("file"):
            found = media.find(S["id"], S["folder"], S["data"], entry, fetch=False)
            path = found[0] if found[1] == media.READY else None
        return (path, media.READY, None) if path else (None, media.MISSING, None)
    return media.find(S["id"], S["folder"], S["data"], entry)


def clip_path(entry=None):
    """The item's file, once it is on this computer; None until then."""
    return clip_where(entry)[0]


def done(k=None):
    return (S["step"] if k is None else k) in S["done"]


def can_check():
    """Whether the step watches for anything."""
    current = step()
    return bool(current and current.get("done_when"))


def _override(context=None):
    """The context override an operator run from here needs: the tutorial's
    window, its 3D view and that view's main region. {} without a window."""
    a = area(context)
    if a is None:
        return {}
    win = next((w for w in (context or bpy.context).window_manager.windows
                if any(x == a for x in w.screen.areas)), None)
    region = next((r for r in a.regions if r.type == "WINDOW"), None)
    return {"window": win, "area": a, "region": region} if win and region else {}


def _mode_set(context, mode):
    ov = _override(context)
    try:
        if ov:
            with context.temp_override(**ov):
                bpy.ops.object.mode_set(mode=mode)
        else:
            bpy.ops.object.mode_set(mode=mode)
    except (RuntimeError, TypeError) as exc:
        print("Kneady: the tutorial could not go into %s mode: %s" % (mode, exc))


def set_view(a, view):
    rv3d = a.spaces.active.region_3d if a is not None else None
    if rv3d is None:
        return
    rv3d.view_location = view["location"]
    rv3d.view_rotation = Quaternion(view["rotation"])
    rv3d.view_distance = view["distance"]
    rv3d.view_perspective = view.get("perspective", "PERSP")


def show_sidebar(a, category, tries=6):
    """Open the 3D view's sidebar on a tab. A sidebar learns its tabs as it
    draws, so a tab it doesn't know yet is tried again after a redraw."""
    if a is None:
        return
    a.spaces.active.show_region_ui = True
    ui = next((r for r in a.regions if r.type == "UI"), None)
    try:
        if ui is not None:
            ui.active_panel_category = category
            a.tag_redraw()
            return
    except (TypeError, ValueError, AttributeError):
        pass                        # read-only until the sidebar has drawn its tabs
    a.tag_redraw()
    if tries > 0:
        pointer = a.as_pointer()

        def again():
            for win in bpy.context.window_manager.windows:
                for x in win.screen.areas:
                    if x.as_pointer() == pointer:
                        show_sidebar(x, category, tries - 1)
            return None
        bpy.app.timers.register(again, first_interval=0.15)


def apply_start(context, start):
    """Apply a step's start: mode, selection, values, the view and the
    sidebar's tab."""
    layer = context.view_layer
    if any(k in start for k in ("select", "active", "mode")) and context.mode != "OBJECT":
        _mode_set(context, "OBJECT")
    if "select" in start:
        names = set(start["select"])
        for obj in layer.objects:
            obj.select_set(obj.name in names)
    if "active" in start:
        layer.objects.active = bpy.data.objects.get(start["active"])
    for item in start.get("set", []):
        try:
            write(context, item["path"], item["value"])
        except (LookupError, TypeError, ValueError, AttributeError) as exc:
            print("Kneady: the tutorial could not set %s: %s" % (item["path"], exc))
    if start.get("mode", "OBJECT") != "OBJECT":
        _mode_set(context, start["mode"])
    a = area(context)
    if "view" in start:
        set_view(a, start["view"])
    if "sidebar" in start:
        show_sidebar(a, start["sidebar"])


def show_me(context, target):
    """Open the part of Blender's own interface a clip shows: the sidebar's
    tab or a Properties editor's tab, with an object made active and a
    modifier opened. Returns a message when it cannot, or ""."""
    if "object" in target:
        obj = bpy.data.objects.get(target["object"])
        if obj is not None:
            context.view_layer.objects.active = obj
    if "sidebar" in target:
        show_sidebar(area(context), target["sidebar"])
    if "properties" in target:
        found = None
        for win in context.window_manager.windows:
            found = found or next((a for a in win.screen.areas if a.type == "PROPERTIES"), None)
        if found is None:
            return "Open a Properties editor, then press Show Me again"
        try:
            found.spaces.active.context = target["properties"]
        except TypeError:
            return "This object has no %s tab" % target["properties"].title()
        obj = context.view_layer.objects.active
        name = target.get("modifier")
        if name and obj is not None and name in obj.modifiers:
            mod = obj.modifiers[name]
            obj.modifiers.active = mod
            mod.show_expanded = True
        found.tag_redraw()
    return ""


def _undo_push(message):
    ov = _override()
    try:
        if ov:
            with bpy.context.temp_override(**ov):
                bpy.ops.ed.undo_push(message=message)
        else:
            bpy.ops.ed.undo_push(message=message)
    except RuntimeError:
        pass


def enter(context, k, apply=True):
    """Go to step `k` (counted from 0). Its start is applied as one undo
    step, and it shows its first clip with its text scrolled to the top.
    Going from one step that shows the shared media to another that does
    leaves the playing clip where it is."""
    k = max(0, min(k, len(steps()) - 1))
    keep = shares() and shares(k)
    S.update(step=k, scroll=0.0)
    if not keep:
        S.update(clip=0, playing=True, loop=None)
    S["done"].discard(k)
    current = step()
    if apply and current.get("start"):
        apply_start(context, current["start"])
        _undo_push("Tutorial: %s" % current.get("title", "Step %d" % (k + 1)))
    S["baseline"] = baseline_of(context, current)
    poll_operators(context)
    S["event_mark"] = event_mark()             # only actions from here on count toward the step
    _changed()
    check(context)
    S["done_at"] = None                         # already done as it began: ticked off, but never moved past


def set_clip(k):
    found = clips()
    if found:
        S["clip"] = k % len(found)
        S.update(playing=True, loop=None)
        _changed()


def check(context=None):
    """Check the step's conditions. The step is done the first time they
    all hold."""
    if not active() or done():
        return
    conds = step().get("done_when")
    if conds and all(met(context or bpy.context, c, S["baseline"]) for c in conds):
        S["done"].add(S["step"])
        S["done_at"] = time.perf_counter()
        _changed()


def advance(context=None, now=None):
    """Move to the next step a moment after the person did this one, and
    return whether it moved on. Greg: "I'd like to use that to move to the
    next step in a tutorial. User can select next or complete the actions
    that are specified". The moment is ADVANCE_AFTER, so the tick shows
    first. It never moves past the last step, in the editor's preview, or
    for a step that was already done as it began."""
    at = S["done_at"]
    if at is None or S["preview"] or not active() or not done() or S["step"] + 1 >= len(steps()):
        return False
    if (time.perf_counter() if now is None else now) - at < ADVANCE_AFTER:
        return False
    S["done_at"] = None
    next_step(context or bpy.context)
    return True


_LISTENERS = []                    # fn(), called when the step, the clip or what shows changes (overlay.py)


def _changed():
    for fn in list(_LISTENERS):
        fn()
    redraw_panels()


def redraw_panels():
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == "VIEW_3D":
                    a.tag_redraw()
    except AttributeError:
        pass


def _tick():
    if not active():
        return None
    try:
        poll_operators()
        check()
        advance()
    except Exception:                     # a check must never take the timer down
        errors.caught("a tutorial check")
    return _next_look()


def _next_look(now=None):
    """When to look again: after CHECK_EVERY as usual, or sooner when the
    next step is due before then. That way the next step comes on when
    ADVANCE_AFTER says, not at the look after."""
    at = S["done_at"]
    if at is None or S["preview"] or not done() or S["step"] + 1 >= len(steps()):
        return CHECK_EVERY
    left = at + ADVANCE_AFTER - (time.perf_counter() if now is None else now)
    return max(0.02, min(CHECK_EVERY, left))


def _timers(on):
    if on and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=CHECK_EVERY, persistent=True)
    elif not on and bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


def show(context=None, on=True):
    """Show the panel over the view, or only its tab. While the panel shows,
    two things are hidden: the toolbar, because the panel sits where it is,
    and the view's own text at the top left, which would draw over it. Both
    are put back as they were when the panel goes."""
    S["shown"] = on
    a = area(context)
    if a is not None:
        space = a.spaces.active
        key = a.as_pointer()
        if on:
            S["toolbar"].setdefault(key, (space.show_region_toolbar, space.overlay.show_text))
            space.show_region_toolbar = False
            space.overlay.show_text = False
        elif key in S["toolbar"]:
            space.show_region_toolbar, space.overlay.show_text = S["toolbar"].pop(key)
    _changed()


def begin(context, tutorial_id, user_file=None, practice=None):
    """Start the tutorial at its first step."""
    folder, data = find(tutorial_id)
    found = problems(data, folder)
    if found:
        raise ValueError("The tutorial %s cannot run: %s" % (tutorial_id, "; ".join(found[:3])))
    S["number"] = number_of(tutorial_id)
    S.update(id=tutorial_id, folder=folder, data=data, step=0, clip=0, done=set(), baseline={},
             practice=practice, user_file=user_file, scroll=0.0, playing=True, loop=None, qr=False,
             area=started_in(context))
    show(context, True)
    _timers(True)
    enter(context, 0)
    # start every hosted item downloading while the first step is read
    media.prefetch(tutorial_id, folder, data, all_media(data))


def end(context=None):
    """End the tutorial: its panel goes and the toolbar comes back."""
    if not active():
        return
    show(context, False)
    S.update(id=None, folder=None, data=None, number=None, step=0, clip=0, done=set(), baseline={}, practice=None,
             user_file=None, area=None, preview=False, loop=None, qr=False)
    S["toolbar"].clear()
    _timers(False)
    _changed()


def previewing():
    """Whether the panel shows a tutorial being edited (tutorial_edit.py)
    rather than one being played."""
    return active() and S["preview"]


def preview(context, data, folder, tutorial_id, k):
    """Show a tutorial in the panel while it is being edited: `data` as it
    stands, unsaved, at step `k`. Greg: "When authoring tutorials it's going
    to be important to be able to see the tutorial panel updating while
    things are being edited in the n-panel". Steps are entered without
    applying their starts, because editing never moves the scene; Reset
    sets a start up on purpose. A tutorial being played comes first, so
    there is no preview over it."""
    if active() and not S["preview"]:
        return
    first = not active()
    n = len(data.get("steps", []))
    k = max(0, min(k, n - 1)) if n else 0
    moved = first or k != S["step"] or tutorial_id != S["id"]
    if tutorial_id != S["id"] or first:
        S["number"] = number_of(tutorial_id)
    S.update(id=tutorial_id, folder=folder, data=data, preview=True, practice=None, user_file=None)
    if not n:
        S["step"] = 0
        _changed()
        return
    if first:
        S.update(step=0, clip=0, done=set(), baseline={}, scroll=0.0, playing=True, loop=None, qr=False,
                 area=started_in(context))
        show(context, True)
        _timers(True)
    if moved:
        enter(context, k, apply=False)
    else:
        found = clips()
        S["clip"] = S["clip"] % len(found) if found else 0
        _changed()


def next_step(context):
    if S["step"] + 1 < len(steps()):
        enter(context, S["step"] + 1, apply=not S["preview"])


def back_step(context):
    if S["step"] > 0:
        enter(context, S["step"] - 1, apply=not S["preview"])


# -- The practice scene --------------------------------------------------------------------

def _same_file(a, b):
    return bool(a) and bool(b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def practice_copy(folder, data):
    """Copy the practice scene into the temporary folder, where saving it
    harms nothing, and return the copy's path."""
    target = os.path.join(tempfile.gettempdir(), "Kneady Practice")
    os.makedirs(target, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|]+', "", data.get("title", "Practice")).strip() or "Practice"
    path = os.path.join(target, name + ".blend")
    source = practice_path(folder, data["practice"])
    if source is None:
        raise ValueError("The practice scene %s is not in its tutorials folder" % data["practice"])
    shutil.copyfile(source, path)
    return path


def prepare(tutorial_id):
    """Get a tutorial ready to start. Returns the practice scene's copy to
    open, or None for a tutorial that runs in the file that is open. Raises
    when the tutorial cannot run."""
    folder, data = find(tutorial_id)
    found = problems(data, folder)
    if found:
        raise ValueError("The tutorial cannot run: %s" % "; ".join(found[:3]))
    if not data.get("practice"):
        return None
    copy = practice_copy(folder, data)
    S["pending"] = {"id": tutorial_id, "copy": copy, "user_file": bpy.data.filepath}
    return copy


def can_return():
    return active() and S["practice"] is not None


@bpy.app.handlers.persistent
def _on_save(*_args):
    # saved from the "save changes?" prompt on the way to the practice scene,
    # so this is the file to go back to
    if S["pending"] is not None:
        S["pending"]["user_file"] = bpy.data.filepath


@bpy.app.handlers.persistent
def _on_load(*_args):
    pending = S["pending"]
    if pending is not None and _same_file(bpy.data.filepath, pending["copy"]):
        S["pending"] = None
        if bpy.app.background:
            begin(bpy.context, pending["id"], pending["user_file"], pending["copy"])
        else:
            # start a moment later, once the window has its new file
            bpy.app.timers.register(lambda: _begin_later(pending), first_interval=0.05)
        return
    if active() and not _same_file(bpy.data.filepath, S["practice"]):
        end()                       # another file was opened, so the tutorial is over (a preview comes back)


def _begin_later(pending):
    try:
        begin(bpy.context, pending["id"], pending["user_file"], pending["copy"])
    except (LookupError, ValueError) as exc:
        print("Kneady: %s" % exc)
    return None


def return_to_file(context):
    """End the tutorial and open the person's own file again, or a new file
    when they had none saved. Changes made in the practice scene stay there.

    Either file is opened without its UI, as the practice scene was. So the
    windows stay as they are, and so does the window manager, with the
    tutorial being written and anything else kept on it. Greg found the
    recording lost - "The tutorial action recording still seems to get
    lost" - because a new file opened with its UI made a new window
    manager, leaving the editor empty."""
    target = S["user_file"]
    end(context)
    if target and os.path.isfile(target):
        bpy.ops.wm.open_mainfile(filepath=target, load_ui=False)
    else:
        bpy.ops.wm.read_homefile(load_ui=False)


# -- Highlighting Kneady's own panel --------------------------------------------------------

def _targets(context):
    out = set()
    current = step()
    if current is None:
        return out
    for path in current.get("highlight", []):
        try:
            owner, name, _index = owner_and_name(context, path)
        except LookupError:
            continue
        out.add((owner.as_pointer(), name))
    return out


class _Emphasis:
    """A panel's layout, unchanged except that the fields the tutorial's
    step points at are drawn in Blender's alert color. Every layout made
    from it is wrapped the same way, so the panel's own drawing code needs
    no change."""
    __slots__ = ("_layout", "_targets")
    _MAKE = {"row", "column", "box", "split", "grid_flow", "column_flow"}

    def __init__(self, layout, targets):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_targets", targets)

    def _wrap(self, made):
        if isinstance(made, tuple):
            return tuple(self._wrap(m) for m in made)
        if made is None or isinstance(made, _Emphasis) or not hasattr(made, "prop"):
            return made
        return _Emphasis(made, self._targets)

    def __getattr__(self, name):
        attr = getattr(self._layout, name)
        if name in self._MAKE or name in ("panel_prop", "panel"):
            return lambda *a, **k: self._wrap(attr(*a, **k))
        return attr

    def __setattr__(self, name, value):
        setattr(self._layout, name, value)

    def prop(self, data, name, *args, **kwargs):
        pointer = data.as_pointer() if hasattr(data, "as_pointer") else None
        if (pointer, name) in self._targets:
            row = self._layout.row(align=True)
            row.alert = True
            return row.prop(data, name, *args, **kwargs)
        return self._layout.prop(data, name, *args, **kwargs)


def emphasize(layout, context):
    """The layout to draw Kneady's panel into, with the tutorial's targets
    lit."""
    if not active():
        return layout
    targets = _targets(context)
    return _Emphasis(layout, targets) if targets else layout


# -- In Kneady's tab ------------------------------------------------------------------------

# An editor of tutorials (tutorial_edit.py) plugs in here as a dict:
#   "toggle"  - fn(layout, context), draws its switch beside Start a Tutorial
#   "draw"    - fn(layout, context), draws the editor under it
# and optionally:
#   "unsaved" - fn(tutorial id) -> whether it holds edits to that tutorial
#               not saved yet
#   "save"    - fn(tutorial id) -> (the id it is saved under, why not or "")
EDITORS = []


def unsaved(tutorial_id):
    """Whether an editor holds edits to the tutorial not saved yet."""
    return any(editor.get("unsaved", lambda _tid: False)(tutorial_id) for editor in EDITORS)


def save_edits(tutorial_id):
    """Save the editor's edits to the tutorial. Returns (the id it is saved
    under, why not or "")."""
    for editor in EDITORS:
        if editor.get("unsaved", lambda _tid: False)(tutorial_id) and "save" in editor:
            return editor["save"](tutorial_id)
    return tutorial_id, ""


def draw(layout, context):
    """Draw the top of the Kneady tab. Greg: "I want to be able to start a
    tutorial from the top of the Kneady pane when in Learn mode. Not present
    outside of learn mode. A dropdown or menu to select from available
    tutorials". It shows the tutorial playing, whatever Help is set to. At
    Learn it also shows the menu of tutorials, with an editor's switch
    beside it."""
    if active() and not S["preview"]:
        box = layout.box()
        current = step()
        box.label(text="%s, %d of %d" % (titled(S["data"], S["id"], S["number"]), S["step"] + 1, len(steps())),
                  icon="HELP")
        box.label(text=current.get("title", ""), icon="CHECKMARK" if done() else "DOT")
        row = box.row(align=True)
        row.operator("kneady.tutorial_show", text="Hide Panel" if S["shown"] else "Show Panel",
                     icon="HIDE_OFF" if S["shown"] else "HIDE_ON").on = not S["shown"]
        row.operator("kneady.tutorial_follow", text="Follow Video", icon="CHECKBOX_HLT" if S["follow"]
                     else "CHECKBOX_DEHLT", depress=S["follow"])
        row = box.row(align=True)
        if can_return():
            row.operator("kneady.tutorial_return", icon="LOOP_BACK")
        else:
            row.operator("kneady.tutorial_end", icon="X")
    from . import tips
    if tips.level() != "LEARN":
        # a rig's own tutorials, what a rigger wrote for it, show at Inform too
        if tips.level() != "QUIET" and file_has_tutorials():
            layout.menu("KNEADY_MT_tutorials_file", text="Tutorials in This File", icon="PLAY")
        return
    row = layout.row(align=True)
    row.menu("KNEADY_MT_tutorials", text="Start a Tutorial", icon="PLAY")
    for editor in EDITORS:
        editor["toggle"](row, context)
    for editor in EDITORS:
        editor["draw"](layout, context)


class KNEADY_MT_tutorials(bpy.types.Menu):
    """Every tutorial there is, to start one"""
    bl_label = "Tutorials"
    bl_idname = "KNEADY_MT_tutorials"

    def draw(self, _context):
        groups = listed()
        if not groups:
            self.layout.label(text="No tutorials yet")
        for k, (heading, entries) in enumerate(groups):
            if k:
                self.layout.separator()
            if len(groups) > 1:
                self.layout.label(text=heading, icon="FILE_BLEND" if heading == FILE_HEADING else "NONE")
            for n, (tid, _folder, data) in enumerate(entries, first_number(entries)):
                self.layout.operator("kneady.tutorial_start", text=titled(data, tid, n),
                                     icon="PLAY").tutorial = tid


class KNEADY_MT_tutorials_file(bpy.types.Menu):
    """The tutorials that came with this file, attached to its items"""
    bl_label = "Tutorials in This File"
    bl_idname = "KNEADY_MT_tutorials_file"

    def draw(self, _context):
        found = attached()
        if not found:
            self.layout.label(text="No tutorials in this file")
        found = _by_order(found)
        for n, (tid, _folder, data) in enumerate(found, first_number(found)):
            self.layout.operator("kneady.tutorial_start", text=titled(data, tid, n), icon="PLAY").tutorial = tid


class KNEADY_PT_tutorials(bpy.types.Panel):
    """The top of the Kneady tab: the tutorial going, and at Help's Learn the
    menu of tutorials. Nothing at all otherwise. Its header folds it away, as
    any of Blender's panels: folded in one window, open in another -
    the Recording Window's sidebar folded while the tutorial is written in
    the main one's."""
    # The header was added for Greg, who needed to fold this panel away to
    # record Kneady's own panel under it: "I need to be able to minimize the
    # Kneady tutorial panel ... so that I can record the Kneady panel". It
    # had no header until then.
    bl_label = "Tutorials"
    bl_idname = "KNEADY_PT_tutorials"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kneady"
    bl_order = 0                       # above Kneady's own panel (bl_order 1)

    @classmethod
    def poll(cls, _context):
        from . import tips
        level = tips.level()
        return active() or level == "LEARN" or (level != "QUIET" and file_has_tutorials())

    def draw(self, context):
        draw(emphasize(self.layout, context), context)       # a step may light the editor's fields too


# -- Operators -------------------------------------------------------------------------------

class KNEADY_OT_tutorial_start(bpy.types.Operator):
    """Start the tutorial. One with a practice scene opens it - your file is asked to be saved first and
    is not changed"""
    bl_idname = "kneady.tutorial_start"
    bl_label = "Start Tutorial"
    bl_options = {"INTERNAL"}

    tutorial: bpy.props.StringProperty(options={"SKIP_SAVE"})
    # What to do with a tutorial being written that has edits not saved yet:
    # ask, save first, or play it as it was last saved. Greg found clips he
    # had added showed while editing "but not when I play it back", because
    # the saved tutorial had none.
    unsaved: bpy.props.EnumProperty(
        items=(("ASK", "Ask", "Ask what to do when it has edits not saved yet"),
               ("SAVE", "Save and Play", "Save your edits, then play it"),
               ("SAVED", "Play Saved Version", "Play it as it was last saved, without your edits")),
        default="ASK", options={"SKIP_SAVE"})

    @classmethod
    def description(cls, _context, props):
        # the menu's tooltip: what the tutorial teaches
        try:
            summary = find(props.tutorial)[1].get("summary")
        except LookupError:
            summary = None
        return summary or cls.__doc__

    def invoke(self, context, _event):
        if self.unsaved == "ASK" and asks_first(context, self.tutorial):
            return {"CANCELLED"}
        return self._run(context, prompt=True)

    def execute(self, context):
        return self._run(context, prompt=False)

    def _run(self, context, prompt):
        if self.unsaved == "SAVE":
            self.tutorial, why = save_edits(self.tutorial)
            if why:
                self.report({"ERROR"}, why)
                return {"CANCELLED"}
        if active():
            end(context)
        try:
            copy = prepare(self.tutorial)
            if copy is None:
                begin(context, self.tutorial)
                return {"FINISHED"}
        except (LookupError, ValueError, OSError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if prompt and not bpy.app.background:
            # Blender's own Open, with its "save changes?" prompt, no file browser
            bpy.ops.wm.open_mainfile("INVOKE_DEFAULT", filepath=copy, load_ui=False, use_scripts=False,
                                     display_file_selector=False)
        else:
            bpy.ops.wm.open_mainfile(filepath=copy, load_ui=False, use_scripts=False)
        return {"FINISHED"}


def asks_first(context, tutorial_id):
    """Whether starting the tutorial waits on a question. If it has edits
    not saved yet, the menu asking what to do is opened and this is True."""
    if not unsaved(tutorial_id):
        return False
    ask_unsaved(context, tutorial_id)
    return True


def ask_unsaved(context, tutorial_id):
    """A small menu saying the tutorial has edits not saved yet, offering
    Save and Play or Play Saved Version. Moving off or Esc does neither."""
    try:
        title = find(tutorial_id)[1].get("title") or tutorial_id
    except LookupError:
        title = tutorial_id

    def draw(menu, _context):
        layout = menu.layout
        layout.operator_context = "INVOKE_DEFAULT"
        for choice, icon in (("SAVE", "FILE_TICK"), ("SAVED", "PLAY")):
            op = layout.operator(KNEADY_OT_tutorial_start.bl_idname, icon=icon,
                                 text="Save and Play" if choice == "SAVE" else "Play Saved Version")
            op.tutorial, op.unsaved = tutorial_id, choice
    context.window_manager.popup_menu(draw, title="%s has edits not saved yet" % title, icon="QUESTION")


class KNEADY_OT_tutorial_return(bpy.types.Operator):
    """End the tutorial and open your own file again. What you did in the practice scene is not kept"""
    bl_idname = "kneady.tutorial_return"
    bl_label = "Return to My File"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return can_return()

    def execute(self, context):
        return_to_file(context)
        return {"FINISHED"}


class KNEADY_OT_tutorial_end(bpy.types.Operator):
    """End the tutorial"""
    bl_idname = "kneady.tutorial_end"
    bl_label = "End Tutorial"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        end(context)
        return {"FINISHED"}


class KNEADY_OT_tutorial_show(bpy.types.Operator):
    """Show or hide the tutorial's panel over the view - the toolbar comes back while it is hidden"""
    bl_idname = "kneady.tutorial_show"
    bl_label = "Show Tutorial"
    bl_options = {"INTERNAL"}

    on: bpy.props.BoolProperty(default=True, options={"SKIP_SAVE"})

    def execute(self, context):
        if active():
            show(context, self.on)
        return {"FINISHED"}


class KNEADY_OT_tutorial_follow(bpy.types.Operator):
    """While a clip plays, scroll its paragraph into view"""
    bl_idname = "kneady.tutorial_follow"
    bl_label = "Follow Video"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        S["follow"] = not S["follow"]
        _changed()
        return {"FINISHED"}


_classes = (KNEADY_OT_tutorial_start, KNEADY_OT_tutorial_return, KNEADY_OT_tutorial_end,
            KNEADY_OT_tutorial_show, KNEADY_OT_tutorial_follow, KNEADY_MT_tutorials, KNEADY_MT_tutorials_file,
            KNEADY_PT_tutorials)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    core.add_hover_hook(_on_hover)
    core.add_action_hook(_on_action)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    if _on_save not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(_on_save)


def unregister():
    end()
    core.remove_action_hook(_on_action)
    core.remove_hover_hook(_on_hover)
    S["pending"] = None
    _timers(False)
    if _on_save in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(_on_save)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    for cls in reversed(_classes):
        reg.unregister_class(cls)
