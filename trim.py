"""What trimming a clip needs to know about it: its frame count and frame
rate, read through Blender's own FFmpeg. The editor uses them to say what a
typed trim keeps ("Keeps 2.0 of 10.0 s").

A clip's trim marks (`"trim": [first, last]` in tutorial.json) are played by
the panel (overlay.py), which plays only the frames between them."""

import os

import bpy  # type: ignore

_INFO = {}                         # path -> ((size, modified), (frames, fps, width, height))


def info(path):
    """(frames, fps, width, height) of the clip at `path`, or None when it
    cannot be read. The answer is cached until the file changes."""
    try:
        stamp = (os.path.getsize(path), os.path.getmtime(path))
    except OSError:
        return None
    found = _INFO.get(path)
    if found is not None and found[0] == stamp:
        return found[1]
    try:
        clip = bpy.data.movieclips.load(path, check_existing=False)
    except RuntimeError:
        return None
    try:
        out = (int(clip.frame_duration), float(clip.fps or 0.0) or 30.0, int(clip.size[0]), int(clip.size[1]))
    finally:
        bpy.data.movieclips.remove(clip)
    if out[0] < 1:
        return None
    if len(_INFO) > 64:
        _INFO.clear()
    _INFO[path] = (stamp, out)
    return out


def known(path):
    """info(path) if it is already cached, without ever reading the file.
    This is for a panel's draw, which may not load data."""
    try:
        stamp = (os.path.getsize(path), os.path.getmtime(path))
    except OSError:
        return None
    found = _INFO.get(path)
    return found[1] if found is not None and found[0] == stamp else None


_PENDING = set()


def learn_later(path, then=None):
    """Work out info(path) on a timer, outside any draw, then call `then()`."""
    if path in _PENDING:
        return

    def run():
        _PENDING.discard(path)
        info(path)
        if then is not None:
            then()
        return None
    _PENDING.add(path)
    bpy.app.timers.register(run, first_interval=0.0)
