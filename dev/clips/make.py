"""Make tutorial clips by script, start to end: record.py plays a tutorial's
clips in a window, then finish.py makes each one an MP4 in the tutorial's
folder, named for its clip.

    python dev/clips/make.py dev/clips/build_a_menu.py [clip ...]
    python dev/clips/make.py all            every tutorial's, in its order


Any Python runs it (Blender's own will do). The environment variable
BLENDER, if set, names the Blender to use; otherwise it is Blender 5.2 in
its usual place. A small window opens on the desktop while the clips play,
and closes when they are done. It ignores the real mouse, so the desktop
stays usable. What each clip's step did is reported: a step not done means
the clip does not do what the tutorial asks. Its MP4 is made all the same,
so you can see why."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BLENDER = os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"


def _script(path):
    spec = importlib.util.spec_from_file_location("clip_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stamp(folder, made, blender):
    """Mark each clip made, in its tutorial.json, as made in this Blender
    and this Kneady (its `recorded`), so the tutorial editor knows which
    clips an update may have left behind."""
    path = os.path.join(folder, "tutorial.json")
    with open(os.path.join(REPO, "blender_manifest.toml"), encoding="utf-8") as f:
        kneady = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M).group(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    names = {os.path.basename(m) for m in made}
    items = list(data.get("media", [])) + [m for step in data.get("steps", []) for m in step.get("media", [])]
    for item in items:
        if item.get("file") in names:
            item["recorded"] = {"blender": blender, "kneady": kneady}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


SKIP = {"record.py", "finish.py", "make.py", "panel.py", "forearm.py"}   # the tools, not tutorials' scripts


def scripts():
    """Every tutorial's clip script here, in its tutorial's order (as the menu
    numbers them): [(order, title, path)]."""
    out = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".py") or name in SKIP:
            continue
        path = os.path.join(HERE, name)
        script = _script(path)
        if not hasattr(script, "CLIPS"):
            continue
        with open(os.path.join(script.FOLDER, script.TUTORIAL, "tutorial.json"), encoding="utf-8") as f:
            data = json.load(f)
        out.append((data.get("order", 100), data.get("title", script.TUTORIAL), path))
    return sorted(out)


def make_all():
    """Make every tutorial's clips again, one tutorial after another, then
    print a summary: whether each was made in full with every step done."""
    results = []
    for order, title, path in scripts():
        print("\n== %d. %s" % (order, title))
        results.append((order, title, make(path, [])))
    print("\nSummary:")
    for order, title, code in results:
        print("  %s %d. %s" % ("ok  " if code == 0 else "FAIL", order, title))
    return 0 if all(code == 0 for _o, _t, code in results) else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] == "all":
        return make_all()
    return make(os.path.abspath(sys.argv[1]), sys.argv[2:])


def make(path, names):
    """Record and make one tutorial's clips - those in `names`, or all of
    them. Returns 0 when every clip was made and every step done."""
    script = _script(path)
    names = names or list(script.CLIPS)
    folder = os.path.join(script.FOLDER, script.TUTORIAL)
    work = tempfile.mkdtemp(prefix="kneady_clips_")
    try:
        print("Recording %d clip(s) of %s in a window..." % (len(names), script.TUTORIAL))
        rec = subprocess.run([BLENDER, "--factory-startup", "--enable-event-simulate",
                              "--window-geometry", "120", "160", "1000", "700",
                              "--python", os.path.join(HERE, "record.py"), "--", path, work] + names,
                             capture_output=True, text=True)
        lines = rec.stdout.splitlines()
        for line in lines:
            if line.startswith(("RECORDED", "FIND")):
                print("  " + line)
        if any(line.startswith("RECORD FAILED") for line in lines):
            start = next(k for k, line in enumerate(lines) if line.startswith("RECORD FAILED"))
            print("\n".join(lines[start:]))
            return 1
        made = []
        for name in names:
            frames = os.path.join(work, name)
            if not os.path.isfile(os.path.join(frames, "timeline.json")):
                print("  %s: not recorded" % name)
                continue
            target = os.path.join(folder, name + ".mp4")
            fin = subprocess.run([BLENDER, "--background", "--factory-startup",
                                  "--python", os.path.join(HERE, "finish.py"), "--", frames, target],
                                 capture_output=True, text=True)
            done = [line for line in fin.stdout.splitlines() if line.startswith(("FINISHED", "FINISH FAILED"))]
            print("  " + (done[0] if done else "%s: finish.py said nothing\n%s" % (name, fin.stdout[-2000:])))
            if done and done[0].startswith("FINISHED"):
                made.append(target)
        blender = next((line.split()[1] for line in lines if line.startswith("BLENDER ")), None)
        if made and blender:
            stamp(folder, made, blender)
        missed = [line for line in lines if "NOT DONE" in line]
        print("Made %d of %d clip(s) in %s%s" % (len(made), len(names), folder,
                                                  "; steps not done: %d" % len(missed) if missed else ""))
        return 0 if len(made) == len(names) and not missed else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
