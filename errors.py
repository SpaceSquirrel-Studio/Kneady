"""Errors Kneady catches so the work can go on, told once.

Some of Kneady's code runs where an error must not stop what the person is
doing: drawing every frame, the hover test at each mouse move, timers, and
code another add-on hands Kneady (a hook). There Kneady catches the error and
carries on. But an error that is caught and never told is a bug nobody can
report, so each one is printed to Blender's console - with its traceback, the
list of calls that led to it, which is what a bug report needs - once per
distinct error. Drawing code would otherwise print the same error sixty times
a second; after the first time it is only counted.

On Windows the console is Window > Toggle System Console; on Linux and macOS,
the terminal Blender was started from.
"""

import sys
import traceback

# (where, error type, message, file, line) -> how many times it happened
_SEEN = {}


def caught(where, trace=True):
    """Print the error being handled, the first time it happens at `where`.
    Call this inside an `except` block. `where` is a few words on what
    Kneady was doing ("a hold hook", "the tutorial preview"). With `trace`
    False the message prints without the traceback, for errors that come
    from the person's data (a property path that no longer resolves) rather
    than from code. Returns whether it was printed."""
    kind, error, tb = sys.exc_info()
    if error is None:
        return False
    frames = traceback.extract_tb(tb)
    last = frames[-1] if frames else None
    key = (where, kind.__name__, str(error)[:200], last.filename if last else "", last.lineno if last else 0)
    times = _SEEN.get(key, 0)
    _SEEN[key] = times + 1
    if times:
        return False
    print("Kneady: %s failed - %s: %s (Kneady carried on; this is shown once)" % (where, kind.__name__, error))
    if trace:
        traceback.print_exception(kind, error, tb, file=sys.stdout)
    sys.stdout.flush()
    return True


def times(where):
    """How many times errors at `where` were caught, for tests."""
    return sum(n for key, n in _SEEN.items() if key[0] == where)


def forget():
    """Forget every error counted, so the next of each is told again."""
    _SEEN.clear()
