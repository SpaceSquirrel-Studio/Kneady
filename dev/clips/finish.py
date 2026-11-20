"""Make tutorial clips by script, stage two: put the frames record.py
captured at an even rate, draw the cursor on, and encode the clip as an
MP4.

    blender --background --factory-startup --python dev/clips/finish.py -- <frames folder> <clip.mp4> [fps]

record.py takes frames as fast as Blender draws them, each with the time it
was taken. Here each frame of the clip is the last one taken by its time,
so whatever moves by the clock - a hover's delay, a clip playing, a step
moving on - keeps its own pace.

The cursor is drawn here, not in the window, so it is smooth whatever the
capture's rate, and it sits over Blender's menus. It is an arrow following
the path record.py kept, its tip on the point, with a ring where it clicks.

The clip is encoded by Blender's own Video Sequencer (H.264 in MP4), with
the Standard view transform, so the frames' colors are the screen's."""

import json
import math
import os
import shutil
import sys

import bpy  # type: ignore
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
FPS = int(ARGS[2]) if len(ARGS) > 2 else 15      # 15, not 30: half the frames to ship (Greg's call)
CURSOR = 1.25                      # the arrow's size, relative to Windows' own at 100%
RING = 0.35                        # seconds a click's ring takes to fade


def _ease(p):
    return p * p * (3.0 - 2.0 * p)


def cursor_at(path, t):
    """Where the cursor is at `t`, along record.py's moves."""
    pos = path[0][2]
    for t0, t1, a, b in path:
        if t0 > t:
            break
        if t >= t1 or t1 <= t0:
            pos = b
        else:
            e = _ease((t - t0) / (t1 - t0))
            pos = (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e)
    return pos


def _inside(poly, xs, ys):
    """Whether each point is inside the polygon (even-odd)."""
    inside = np.zeros(xs.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        crosses = ((y1 > ys) != (y2 > ys)) & (xs < (x2 - x1) * (ys - y1) / ((y2 - y1) or 1e-9) + x1)
        inside ^= crosses
    return inside


def arrow_sprite(scale):
    """An arrow cursor as RGBA rows, top down, its tip at (pad, pad): white,
    with a dark edge and a soft shadow."""
    shape = [(0, 0), (0, 17), (4, 13.5), (7, 20), (9.6, 19), (6.6, 12.5), (12, 12.5)]
    pad, ss = 4, 4
    w, h = int(13 * scale) + 2 * pad + 4, int(21 * scale) + 2 * pad + 4
    ys, xs = np.mgrid[0:h * ss, 0:w * ss]
    xs = (xs + 0.5) / ss - pad
    ys = (ys + 0.5) / ss - pad
    poly = [(x * scale, y * scale) for x, y in shape]
    fill = _inside(poly, xs, ys).reshape(h, ss, w, ss).mean(axis=(1, 3))
    # the edge: the fill grown by about a pixel and a half
    grown = fill.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dx * dx + dy * dy <= 4:
                grown = np.maximum(grown, np.roll(np.roll(fill, dy, 0), dx, 1))
    shadow = np.roll(np.roll(grown, 2, 0), 1, 1) * 0.3
    rgba = np.zeros((h, w, 4), dtype=np.float32)
    # layered bottom to top: shadow, edge, fill
    for alpha, color in ((shadow, (0, 0, 0)), (grown, (0.05, 0.05, 0.05)), (fill, (1, 1, 1))):
        a = alpha[..., None]
        rgba[..., :3] = rgba[..., :3] * (1 - a) + np.array(color, dtype=np.float32) * a
        rgba[..., 3:] = rgba[..., 3:] * (1 - a) + a
    return rgba, pad


def _blend(img, sprite, x, y):
    """Lay `sprite` (RGBA, rows top down) over `img` (rows bottom up), with
    its top left at window pixel (x, y)."""
    h, w = img.shape[:2]
    sh, sw = sprite.shape[:2]
    for row in range(sh):
        iy = int(round(y)) - row
        if not 0 <= iy < h:
            continue
        x0 = int(round(x))
        a0, a1 = max(0, -x0), min(sw, w - x0)
        if a0 >= a1:
            continue
        src = sprite[row, a0:a1]
        dst = img[iy, x0 + a0:x0 + a1]
        a = src[:, 3:]
        dst[:, :3] = dst[:, :3] * (1 - a) + src[:, :3] * a


def _ring(img, cx, cy, radius, alpha, width=2.5):
    h, w = img.shape[:2]
    r = int(radius + width + 3)
    x0, x1 = max(0, int(cx) - r), min(w, int(cx) + r + 1)
    y0, y1 = max(0, int(cy) - r), min(h, int(cy) + r + 1)
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    d = np.abs(np.hypot(xs + 0.5 - cx, ys + 0.5 - cy) - radius)
    for edge, color, a_scale in ((width + 1.5, (0.05, 0.05, 0.05), 0.6), (width * 0.5, (1.0, 1.0, 1.0), 1.0)):
        a = (np.clip(edge - d, 0.0, 1.0) * alpha * a_scale)[..., None]
        patch = img[y0:y1, x0:x1]
        patch[..., :3] = patch[..., :3] * (1 - a) + np.array(color) * a


def _load(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)


def _save(arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new("clip_frame", w, h, alpha=False)
    img.pixels.foreach_set(np.ascontiguousarray(arr, dtype=np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def frames_for(times, fps):
    """For each frame of the clip, which captured frame shows: the last taken
    by its time."""
    out, i = [], 0
    n = int(math.floor(times[-1] * fps)) + 1
    for k in range(n):
        t = k / fps
        while i + 1 < len(times) and times[i + 1] <= t:
            i += 1
        out.append(i)
    return out


def encode(files, fps, size, target):
    """Encode the frames as an H.264 MP4 with the Video Sequencer."""
    scene = bpy.data.scenes.new("Clip")
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = fps, 1.0
    scene.frame_start, scene.frame_end = 1, len(files)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    ed = scene.sequence_editor_create()
    strips = ed.strips if hasattr(ed, "strips") else ed.sequences
    strip = strips.new_image("frames", files[0], channel=1, frame_start=1)
    for f in files[1:]:
        strip.elements.append(os.path.basename(f))
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "VIDEO"
    settings.file_format = "FFMPEG"
    ff = scene.render.ffmpeg
    ff.format, ff.codec = "MPEG4", "H264"
    ff.constant_rate_factor = "HIGH"
    ff.ffmpeg_preset = "GOOD"
    ff.audio_codec = "NONE"
    out_dir = os.path.join(os.path.dirname(files[0]), "_video")
    os.makedirs(out_dir, exist_ok=True)
    scene.render.filepath = os.path.join(out_dir, "clip")
    with bpy.context.temp_override(scene=scene):
        bpy.ops.render.render(animation=True, scene=scene.name)
    made = [os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.lower().endswith(".mp4")]
    if not made:
        raise RuntimeError("the Video Sequencer made no MP4 in %s" % out_dir)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.move(max(made, key=os.path.getmtime), target)
    shutil.rmtree(out_dir, ignore_errors=True)


def main():
    folder, target = ARGS[0], ARGS[1]
    with open(os.path.join(folder, "timeline.json"), encoding="utf-8") as f:
        tl = json.load(f)
    names = [n for n, _t in tl["frames"]]
    times = [t for _n, t in tl["frames"]]
    picks = frames_for(times, FPS)
    sprite, pad = arrow_sprite(CURSOR)
    done = os.path.join(folder, "_done")
    shutil.rmtree(done, ignore_errors=True)
    os.makedirs(done)
    files, cache = [], {}
    for k, i in enumerate(picks):
        t = k / FPS
        if i not in cache:
            cache.clear()
            cache[i] = _load(os.path.join(folder, names[i]))
        img = cache[i].copy()
        for ct, cx, cy in tl["clicks"]:
            p = (t - ct) / RING
            if 0.0 <= p < 1.0:
                _ring(img, cx, cy, 7.0 + 16.0 * p, 1.0 - p)
        x, y = cursor_at(tl["path"], t)
        _blend(img, sprite, x - pad, y + pad)
        path = os.path.join(done, "%05d.png" % k)
        _save(img, path)
        files.append(path)
    encode(files, FPS, tuple(tl["size"]), target)
    shutil.rmtree(done, ignore_errors=True)
    print("FINISHED %s: %d frames, %.2f s at %d fps" % (target, len(files), len(files) / FPS, FPS))


try:
    main()
except Exception:
    import traceback
    print("FINISH FAILED\n" + traceback.format_exc())
sys.stdout.flush()
