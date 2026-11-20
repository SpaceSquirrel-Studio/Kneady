"""Prepare a tutorial's hosted clips and images for putting online.

    python dev/publish_media.py quick_start
    (or: blender --background --factory-startup --python dev/publish_media.py -- quick_start)

Each of a tutorial's media items is either local (kept in its folder and
shipped with it) or hosted (`"hosted": true`, downloaded when played).
Record a hosted one into dev/media/<tutorial>/. Kneady run from this
repository plays it from there, and dev/ is left out of the extension, so
the file never ships inside it. This script then:

- writes each hosted file's sha256 into tutorials/<tutorial>/tutorial.json,
  so Kneady refuses anything else served in its place;
- lists the files to upload, and the address each must be found at (the
  tutorial's media_url plus the file's name, or the item's own url);
- says which items are not recorded yet, which hosted ones sit in the
  tutorial's own folder (they would ship too), and which local ones are
  only in dev/media (they won't ship until they are in the tutorial's
  folder).

It changes nothing else in tutorial.json: each fingerprint goes in beside
its file's name, and the rest of the file keeps its layout.
"""

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main(tutorial_id):
    folder = os.path.join(REPO, "tutorials", tutorial_id)
    source = os.path.join(HERE, "media", tutorial_id)
    path = os.path.join(folder, "tutorial.json")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    data = json.loads(text)
    base = data.get("media_url", "")
    entries = list(data.get("media", [])) + [e for s in data.get("steps", []) for e in s.get("media", [])]
    upload, missing, shipped, unshipped, seen = [], [], [], [], set()
    for entry in entries:
        name = entry.get("file")
        if not name or name in seen:
            continue
        seen.add(name)
        found = next((p for p in (os.path.join(folder, name), os.path.join(source, name)) if os.path.isfile(p)),
                     None)
        if found is None:
            missing.append(name)
            continue
        in_folder = os.path.dirname(found) == folder
        if not (entry.get("hosted") or entry.get("url")):
            if not in_folder:
                unshipped.append(name)
            continue
        # beside every `"file": "<name>"`, add a fingerprint or correct the
        # one already there
        pattern = r'("file":\s*%s)(\s*,\s*"sha256":\s*"[^"]*")?' % re.escape(json.dumps(name))
        text = re.sub(pattern, lambda m, d=digest(found): '%s, "sha256": "%s"' % (m.group(1), d), text)
        if in_folder:
            shipped.append(name)
        url = entry.get("url") or (base.rstrip("/") + "/" + name if base else "(no media_url)")
        upload.append((found, url))
    json.loads(text)                          # the edit left valid JSON
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("Fingerprints written to %s" % path if upload else "No hosted clips or images: nothing to upload")
    if upload:
        print("\nUpload these, each to the address beside it:")
        for found, url in upload:
            print("  %s  (%.0f KB)\n      -> %s" % (found, os.path.getsize(found) / 1024, url))
    if missing:
        print("\nNot recorded yet: %s" % ", ".join(missing))
    if shipped:
        print("\nHosted, but in the tutorial's own folder, so they ship inside the extension too: %s"
              % ", ".join(shipped))
    if unshipped:
        print("\nKept in the tutorial, but only in dev/media - copy them into %s to ship them: %s"
              % (folder, ", ".join(unshipped)))
    sys.stdout.flush()


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
    else:
        main(args[0])
