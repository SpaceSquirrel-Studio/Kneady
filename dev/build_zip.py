"""Build the extension zip people install, from the last commit.

    blender --background --factory-startup --python dev/build_zip.py -- <output folder>

It exports the last commit (git archive), so what is built is exactly what is
committed, never a half-finished edit. Then Blender's own extension build
packs it, by the manifest's rules, and validates the zip.

**The tutorial clips live in Git LFS.** Git keeps a small text placeholder for
each (an LFS pointer, giving the clip's sha256 and size). With Git LFS set up
and the clips downloaded, git archive turns each placeholder back into its
clip as it exports. Where it can't (a clone made without LFS), the export
holds placeholders, and each is replaced by the clip on disk - but only if
that file's sha256 and size are the ones the placeholder names, which makes
it exactly the committed clip. A clip missing or different stops the build:
run `git lfs pull` in this folder first. Either way, no placeholder can end
up in the zip in place of a video.
"""

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
POINTER = b"version https://git-lfs.github.com/spec/v1"


def lfs_pointer(data):
    """(sha256, size) when `data` is an LFS pointer file, else None."""
    if not data.startswith(POINTER) or len(data) > 1024:
        return None
    fields = dict(line.split(" ", 1) for line in data.decode("ascii", "replace").splitlines() if " " in line)
    oid, size = fields.get("oid", ""), fields.get("size", "")
    if not oid.startswith("sha256:") or not size.isdigit():
        return None
    return oid[len("sha256:"):], int(size)


def committed_file(repo, path, data):
    """`data` as exported, or - for an LFS pointer - the clip on disk it
    names, checked to be exactly that one."""
    pointer = lfs_pointer(data)
    if pointer is None:
        return data
    sha, size = pointer
    on_disk = os.path.join(repo, path)
    if not os.path.isfile(on_disk):
        raise SystemExit("%s is missing from %s: run git lfs pull there first" % (path, repo))
    with open(on_disk, "rb") as f:
        real = f.read()
    if len(real) != size or hashlib.sha256(real).hexdigest() != sha:
        raise SystemExit("%s in %s is not the committed clip (an LFS placeholder, or changed since): "
                         "run git lfs pull there, or commit it" % (path, repo))
    return real


def export(repo, dest):
    """The last commit of `repo` into folder `dest`, LFS clips included.
    Returns how many clips came from LFS."""
    data = subprocess.run(["git", "-C", repo, "archive", "--format=tar", "HEAD"],
                          capture_output=True, check=True).stdout
    clips = 0
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            target = os.path.join(dest, member.name)
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            if not member.isfile():
                continue
            raw = tar.extractfile(member).read()
            content = committed_file(repo, member.name, raw)
            clips += content is not raw
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(content)
    return clips


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(args[0]) if args else os.path.join(os.path.expanduser("~"), "Documents", "Kneady builds")
    os.makedirs(out, exist_ok=True)
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    work = tempfile.mkdtemp(prefix="kneady_build_")
    try:
        clips = export(REPO, work)
        print("BUILD exported %s%s%s" % (head, " (uncommitted changes left out)" if dirty else "",
                                         ", %d LFS placeholders replaced by their clips" % clips if clips else ""))
        blender = bpy.app.binary_path
        subprocess.run([blender, "--factory-startup", "--command", "extension", "build",
                        "--source-dir", work, "--output-dir", out], check=True)
        zips = [os.path.join(out, name) for name in os.listdir(out) if name.startswith("kneady-") and
                name.endswith(".zip")]
        newest = max(zips, key=os.path.getmtime)
        subprocess.run([blender, "--factory-startup", "--command", "extension", "validate", newest], check=True)
        print("BUILD written and validated: %s" % newest)
    finally:
        shutil.rmtree(work, ignore_errors=True)


main()
