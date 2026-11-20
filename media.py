"""Where a tutorial's clips and images come from. Greg asked for hosting from
the start - "Let's make self hosted work. Good for that to just be set up
from the start" - and then "make it so authoring allows you to author local
or from hosted videos". Each item is one or the other:

- **Local** (the default): its file is in the tutorial's folder and ships
  with it. It is never downloaded, so a first tutorial works offline,
  without Allow Online Access.
- **Hosted** (`"hosted": true`, or an item with its own `url`): downloaded
  into Kneady's user folder and kept there. It comes from the item's own
  `url`, or else from the tutorial's `media_url` plus the item's file name.
  In a checkout of Kneady's repository, dev/media/<tutorial>/ holds the
  copies recorded before they are put online, and they play from there.
  (dev/ is left out of the extension.)

**Downloading** happens in the background, two files at a time, and only
while Blender's Allow Online Access is on (Preferences > System), as an
extension must. When it is off, the panel says so. Safety rules:

- Only https is used, or a server on this computer (for the tests).
- A file larger than MAX_BYTES is refused.
- When the tutorial gives the item's `sha256`, a file that does not match
  it is refused, so a host that was changed or broken cannot hand Blender's
  video decoder something else.
- Kneady sends nothing but the request: no name, and none of the person's
  files.
- Certificates are checked against both the system's own store (Windows' on
  Windows) and Blender's bundled ones. The system store matters because an
  office network that inspects secure traffic puts its own certificate
  there.

The download threads touch no Blender data. They write the file, and their
progress into _JOBS under _LOCK, and the player's timer reads it (find).
"""

import hashlib
import os
import re
import ssl
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
DEV_MEDIA = os.path.join(HERE, "dev", "media")   # in a checkout of Kneady's repository only
MAX_BYTES = 64 * 1024 * 1024
TIMEOUT = 20.0
WORKERS = 2
CHUNK = 64 * 1024
LOCAL = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?/")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")

READY, DOWNLOADING, OFFLINE, FAILED, MISSING = "READY", "DOWNLOADING", "OFFLINE", "FAILED", "MISSING"

_LOCK = threading.Lock()
_JOBS = {}                         # url -> {status, got, total, error, path}
_QUEUE = []                        # (url, path, sha256) waiting
_THREADS = []
_STOP = threading.Event()
_CHECKED = {}                      # (path, sha256) -> whether the cached file is that file
CACHE = None                       # the folder downloads go to: None for Kneady's user folder (tests set one)


def url_ok(url):
    """Whether Kneady downloads from `url`: https, or this computer."""
    return isinstance(url, str) and (url.startswith("https://") or LOCAL.match(url) is not None)


def hosted(entry):
    """Whether an item is downloaded, not shipped in the tutorial's folder."""
    return bool(entry.get("hosted") or entry.get("url"))


def url_of(data, entry):
    """Where a hosted item is online, or None: its own `url`, else the
    tutorial's `media_url` plus its file name. A local item has no URL."""
    if not hosted(entry):
        return None
    if entry.get("url"):
        return entry["url"]
    base = data.get("media_url")
    if base:
        return base.rstrip("/") + "/" + urllib.parse.quote(entry["file"])
    return None


def online():
    """Whether Blender's Allow Online Access is on, which the command line's
    --online-mode and --offline-mode also set."""
    return bool(getattr(bpy.app, "online_access", True))


def cache_dir():
    if CACHE is not None:
        os.makedirs(CACHE, exist_ok=True)
        return CACHE
    package = __package__ or ""
    if package.startswith("bl_ext."):
        # the extension's own user folder - Kneady's, or the add-on carrying it
        try:
            return bpy.utils.extension_path_user(".".join(package.split(".")[:3]), path="tutorial_media",
                                                 create=True)
        except (ValueError, AttributeError, OSError):
            pass
    path = os.path.join(tempfile.gettempdir(), "Kneady Tutorial Media")
    os.makedirs(path, exist_ok=True)
    return path


def cached_path(url, entry):
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir(), "%s_%s" % (key, os.path.basename(entry["file"])))


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _checked(path, sha):
    """Whether a file downloaded before is the one the tutorial expects.
    Checked once a session; a file that does not match is deleted."""
    if not sha:
        return True
    key = (path, sha.lower())
    if key not in _CHECKED:
        ok = _digest(path) == sha.lower()
        if not ok:
            try:
                os.remove(path)
            except OSError:
                pass
        _CHECKED[key] = ok
    return _CHECKED[key]


HOSTED_COPIES = ".hosted"          # in a tutorials folder: hosted items' copies, never shipped


def copies_folder(folder, tutorial_id):
    """Where a hosted item's copy is kept on the author's computer, to play
    while writing and to upload from:

    - in a checkout of Kneady's repository, dev/media/<tutorial>/, beside
      its tutorials/;
    - in any other tutorials folder, its own .hosted/<tutorial>/.

    Neither ships."""
    tutorials_folder = os.path.dirname(os.path.abspath(folder))
    root = os.path.dirname(tutorials_folder)
    if os.path.isdir(os.path.join(root, "dev")):
        return os.path.join(root, "dev", "media", tutorial_id or "")
    return os.path.join(tutorials_folder, HOSTED_COPIES, tutorial_id or "")


def local(tutorial_id, folder, entry):
    """The item's file if it is already on this computer, or None. It is
    looked for in the tutorial's folder, where hosted items' copies are
    kept (copies_folder), and Kneady's own dev/media."""
    tutorials_folder = os.path.dirname(os.path.abspath(folder))
    root = os.path.dirname(tutorials_folder)
    for base in (folder, os.path.join(root, "dev", "media", tutorial_id or ""),
                 os.path.join(tutorials_folder, HOSTED_COPIES, tutorial_id or ""),
                 os.path.join(DEV_MEDIA, tutorial_id or "")):
        path = os.path.join(base, entry["file"])
        if os.path.isfile(path):
            return path
    return None


def find(tutorial_id, folder, data, entry, fetch=True):
    """(path, status, detail) for an item. The status is one of:

    - READY, with its path: in the tutorial's folder, a checkout's
      dev/media, or downloaded before;
    - DOWNLOADING, with how much is done (0 to 1, or None when the size is
      not known);
    - OFFLINE;
    - FAILED, with why;
    - MISSING, when there is nowhere to get it.

    A download is started here when one is needed, unless `fetch` is off."""
    if not entry.get("file"):
        return None, MISSING, None                    # an item being written, its file not named yet
    path = local(tutorial_id, folder, entry)
    if path is not None:
        return path, READY, None
    url = url_of(data, entry)
    if url is None or not url_ok(url):
        return None, MISSING, None
    path = cached_path(url, entry)
    with _LOCK:
        job = dict(_JOBS.get(url) or {})
    if job.get("status") == "done" or (not job and os.path.isfile(path) and _checked(path, entry.get("sha256"))):
        return path, READY, None
    if job.get("status") == "failed":
        return None, FAILED, job.get("error")
    if not online():
        return None, OFFLINE, None
    if not job:
        if not fetch:
            return None, MISSING, None
        start(url, path, entry.get("sha256"))
    with _LOCK:
        job = dict(_JOBS.get(url) or {})
    total = job.get("total") or 0
    return None, DOWNLOADING, (job.get("got", 0) / total if total else None)


def prefetch(tutorial_id, folder, data, entries):
    """Start downloads, in order, for every item not on this computer, so
    the next step's clip is there when it is needed."""
    for entry in entries:
        find(tutorial_id, folder, data, entry)


def retry(data, entry):
    """Forget a failed download so it is tried again."""
    url = url_of(data, entry)
    with _LOCK:
        if url in _JOBS and _JOBS[url].get("status") == "failed":
            del _JOBS[url]


def start(url, path, sha=None):
    with _LOCK:
        if url in _JOBS:
            return
        _JOBS[url] = {"status": "queued", "got": 0, "total": 0, "error": None, "path": path}
        _QUEUE.append((url, path, sha))
        _THREADS[:] = [t for t in _THREADS if t.is_alive()]
        if len(_THREADS) < WORKERS:
            thread = threading.Thread(target=_work, name="Kneady tutorial media", daemon=True)
            _THREADS.append(thread)
            thread.start()


def _note(url, **values):
    """Record a download's progress, unless the download was forgotten
    meanwhile (forget), which leaves the thread nothing to write to."""
    with _LOCK:
        job = _JOBS.get(url)
        if job is not None:
            job.update(values)


def _work():
    while not _STOP.is_set():
        with _LOCK:
            if not _QUEUE:
                return
            url, path, sha = _QUEUE.pop(0)
            if url in _JOBS:
                _JOBS[url]["status"] = "downloading"
        try:
            _download(url, path, sha)
            _note(url, status="done")
        except Exception as exc:              # each download's failure is its own
            _note(url, status="failed", error=_why(exc))


def _context():
    """An SSL context that trusts certificates from both sources:

    - the system's own store (Windows' on Windows), where an office that
      inspects secure traffic puts its own certificate;
    - Blender's bundled certifi, for a system whose store is thin."""
    context = ssl.create_default_context()
    try:
        import certifi  # type: ignore
        context.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        pass
    return context


def _download(url, path, sha):
    part = path + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": "Kneady"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=_context()) as response:
            if not url_ok(response.geturl()):
                raise ValueError("it was sent somewhere that is not https")
            total = int(response.headers.get("Content-Length") or 0)
            if total > MAX_BYTES:
                raise ValueError("it is larger than %d MB" % (MAX_BYTES // (1024 * 1024)))
            _note(url, total=total)
            h, got = hashlib.sha256(), 0
            with open(part, "wb") as f:
                while True:
                    if _STOP.is_set():
                        raise RuntimeError("Kneady was turned off")
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_BYTES:
                        raise ValueError("it is larger than %d MB" % (MAX_BYTES // (1024 * 1024)))
                    h.update(chunk)
                    f.write(chunk)
                    _note(url, got=got)
        if sha and h.hexdigest() != sha.lower():
            raise ValueError("it is not the file the tutorial expects")
        os.replace(part, path)
        if sha:
            _CHECKED[(path, sha.lower())] = True
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass


def _why(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "not found where it is hosted" if exc.code == 404 else "the host answered %d" % exc.code
    if isinstance(exc, urllib.error.URLError):
        return "no connection (%s)" % getattr(exc, "reason", exc)
    if isinstance(exc, TimeoutError):
        return "the host took too long"
    return str(exc) or exc.__class__.__name__


def forget():
    """Drop every download's state, for the tests. The files stay."""
    with _LOCK:
        _JOBS.clear()
        _QUEUE.clear()
    _CHECKED.clear()


def register():
    _STOP.clear()


def unregister():
    _STOP.set()
    with _LOCK:
        _QUEUE.clear()
