"""Kneady's tests, without Digit or any other add-on.

    blender --background --factory-startup --python tests/run.py
    blender --background --factory-startup --python tests/run.py -- pose_mode

Loads Kneady from this repository as a package (so it is the code here that
is tested, not an installed copy), registers it, and runs every test in the
tests/test_*.py files - or those named after `--`. Each test is a function
`test_<name>()` that raises AssertionError with a message when it fails.
Prints one PASS / FAIL line per test and a summary.
"""

import importlib
import os
import sys
import traceback

import bpy  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
sys.path.insert(0, HERE)

kneady = importlib.import_module(os.path.basename(REPO))
kneady.register()
import rigs  # noqa: E402  (tests/rigs.py, after Kneady is loaded)


def tests():
    found = []
    for name in sorted(os.listdir(HERE)):
        if name.startswith("test_") and name.endswith(".py"):
            module = importlib.import_module(name[:-3])
            found += [(n[5:], getattr(module, n)) for n in dir(module)
                      if n.startswith("test_") and callable(getattr(module, n))]
    return found


def main():
    wanted = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    results = []
    for name, fn in tests():
        if wanted and name not in wanted:
            continue
        bpy.ops.wm.read_homefile(use_empty=True)
        try:
            fn()
            results.append((name, True, ""))
            print("PASS  %s" % name)
        except rigs.Skip as exc:
            results.append((name, True, "skipped"))
            print("SKIP  %s  %s" % (name, exc))
        except AssertionError as exc:
            results.append((name, False, str(exc)))
            print("FAIL  %s  %s" % (name, exc))
        except Exception:
            results.append((name, False, "crashed"))
            print("CRASH %s\n%s" % (name, traceback.format_exc()))
    passed = sum(1 for _n, ok, _d in results if ok)
    print("\n%d/%d passed" % (passed, len(results)))
    sys.stdout.flush()
    return passed == len(results)


# The exit code says how it went, for whatever runs the tests on its own - the
# GitHub Actions workflow (.github/workflows/tests.yml) fails a run on 1:
# 0 when every test passed or skipped, 1 when any failed or crashed.
os._exit(0 if main() else 1)
