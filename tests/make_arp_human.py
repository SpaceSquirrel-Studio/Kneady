"""Make the Auto-Rig Pro test character: the MPFB2 human (mpfb_human.blend,
made by make_mpfb_human.py) rigged with Auto-Rig Pro, saved into the test
assets (rigs.asset) as arp_human.blend.

    blender --factory-startup --window-geometry 0 0 1600 900 --python tests/make_arp_human.py

Run it in a window, not with --background: Auto-Rig Pro's operators set the
3D view's overlays as they go, so they need one.

It needs Auto-Rig Pro installed in the Blender that runs it. Lite is enough
(Greg's copy is from Superhive). Factory startup does not know about it, so
the folder it is installed in is added as a local repository for this
session only.

Lite has no Smart (the automatic fit), so the reference bones are fitted
here. Each main one goes onto the MPFB2 skeleton's matching joint; the rest
(fingers, face, the foot's banks) move with their nearest fitted parent.
Then it runs Match to Rig, removes MPFB2's own skeleton and binds the body
to the new rig. It quits when done.
"""

import os
import sys

import addon_utils  # type: ignore
import bpy  # type: ignore
from mathutils import Vector  # type: ignore

ROOT = os.environ.get("KNEADY_TEST_ASSETS") or os.path.join(os.path.expanduser("~"), "Documents",
                                                            "Kneady test assets")
SOURCE = os.path.join(ROOT, "mpfb_human.blend")
OUT = os.path.join(ROOT, "arp_human.blend")
REPOSITORY = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender",
                          "%d.%d" % bpy.app.version[:2], "extensions", "superhivemarket_com")


def _joints(rig):
    out = {}
    for b in rig.data.bones:
        out[b.name] = (rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local)
    return out


def fit(j, side):
    """{reference bone: (head, tail)} from the MPFB2 joints `j`, for side "l"
    (MPFB2's .L) or "r"."""
    s = side.upper()

    def h(name):
        return j[name][0]

    def t(name):
        return j[name][1]

    ball = t("foot." + s)
    out = {
        "shoulder_ref." + side: (h("clavicle." + s), h("upperarm01." + s)),
        "arm_ref." + side: (h("upperarm01." + s), h("lowerarm01." + s)),
        "forearm_ref." + side: (h("lowerarm01." + s), h("wrist." + s)),
        "hand_ref." + side: (h("wrist." + s), t("metacarpal3." + s)),
        "thigh_ref." + side: (h("upperleg01." + s), h("lowerleg01." + s)),
        "leg_ref." + side: (h("lowerleg01." + s), h("foot." + s)),
        "foot_ref." + side: (h("foot." + s), ball),
        "toes_ref." + side: (ball, ball + Vector((0.0, -0.06, 0.0))),
    }
    return out


def fit_spine(j):
    top = j["head"][0] + (j["head"][1] - j["head"][0]) * 1.6
    return {
        "root_ref.x": (j["spine05"][0], j["spine03"][0]),
        "spine_01_ref.x": (j["spine03"][0], j["spine01"][0]),
        "spine_02_ref.x": (j["spine01"][0], j["neck01"][0]),
        "neck_ref.x": (j["neck01"][0], j["head"][0]),
        "head_ref.x": (j["head"][0], top),
    }


def view():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region


def run(op, **kw):
    win, area, region = view()
    with bpy.context.temp_override(window=win, area=area, region=region):
        return op(**kw)


def select_only(objs, active):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def steps():
    log = []
    try:
        bpy.ops.preferences.extension_repo_add(name="superhivemarket_com", type="LOCAL",
                                               custom_directory=REPOSITORY, use_custom_directory=True)
        addon_utils.enable("bl_ext.superhivemarket_com.auto_rig_pro", default_set=True)
        yield 0.5
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        with bpy.data.libraries.load(SOURCE, link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            bpy.context.scene.collection.objects.link(o)
        body = bpy.data.objects["Human"]
        mpfb = bpy.data.objects["Human.rig"]
        joints = _joints(mpfb)
        log.append("MPFB2 human appended: %d joints" % len(joints))
        yield 0.3

        log.append("append_arp %s" % run(bpy.ops.arp.append_arp, rig_preset="human"))
        ref = bpy.data.objects["rig"]
        yield 0.3
        wanted = fit_spine(joints)
        wanted.update(fit(joints, "l"))
        wanted.update(fit(joints, "r"))
        select_only([ref], ref)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = ref.data.edit_bones
        to_ref = ref.matrix_world.inverted()
        moved = {}
        for name, (head, tail) in wanted.items():
            b = eb.get(name)
            if b is None:
                log.append("no reference bone %s" % name)
                continue
            moved[name] = (to_ref @ head) - b.head
            b.head, b.tail = to_ref @ head, to_ref @ tail
        # everything not fitted follows its nearest fitted parent's head
        for b in eb:
            if b.name in wanted:
                continue
            p = b.parent
            while p is not None and p.name not in moved:
                p = p.parent
            if p is not None:
                d = moved[p.name]
                b.head, b.tail = b.head + d, b.tail + d
        bpy.ops.object.mode_set(mode="OBJECT")
        log.append("fitted %d reference bones" % len(moved))
        yield 0.3

        select_only([ref], ref)
        log.append("match_to_rig %s" % run(bpy.ops.arp.match_to_rig))
        yield 0.5
        for m in list(body.modifiers):
            if m.type == "ARMATURE":
                body.modifiers.remove(m)
        body.parent = None
        bpy.data.objects.remove(mpfb, do_unlink=True)
        rig = bpy.data.objects["rig"]
        select_only([body, rig], rig)
        log.append("bind_to_rig %s" % run(bpy.ops.arp.bind_to_rig))
        yield 0.5
        log.append("body modifiers %s" % [(m.type, getattr(m, "object", None) and m.object.name)
                                         for m in body.modifiers])
        names = {b.name for b in rig.data.bones}
        log.append("controls %s" % [n for n in ("c_arm_fk.l", "c_forearm_fk.l", "c_hand_fk.l", "c_hand_ik.l",
                                                "c_traj", "c_pos") if n in names])
        switches = [(pb.name, [(k, pb[k]) for k in pb.keys() if "ik" in k.lower() or "fk" in k.lower()])
                    for pb in rig.pose.bones]
        log.append("switches %s" % [s for s in switches if s[1]][:6])
        bpy.ops.wm.save_as_mainfile(filepath=OUT)
        log.append("saved %s" % OUT)
    except Exception:
        import traceback
        log.append("ERROR " + traceback.format_exc())
    print("\n".join("MAKE " + line for line in log))
    sys.stdout.flush()
    os._exit(0)


_gen = steps()


def tick():
    try:
        return next(_gen)
    except StopIteration:
        return None


bpy.app.timers.register(tick, first_interval=1.5)
