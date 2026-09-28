"""Pose layer system: mocap retargeting (CMU BVH -> MPFB cmu_mb rig) + procedural overrides.

A "pose" is a dict: {"root": Vector (hips world position), bone_name: Quaternion (world rotation)}.
Working in world rotations makes blending mocap with hand-authored overrides simple.
"""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector

BONES_SKIP = {"LeftHandFinger1", "RightHandFinger1", "LThumb", "RThumb", "LeftFingerBase", "RightFingerBase"}


class Skeleton:
    """Rest-pose info of the target (MPFB) rig."""

    def __init__(self, rig):
        self.rig = rig
        self.bones = [b for b in rig.data.bones]            # parents come before children
        self.rest = {b.name: b.matrix_local.copy() for b in self.bones}
        self.rest_rot = {n: m.to_quaternion() for n, m in self.rest.items()}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in self.bones}
        self.children = {b.name: [c.name for c in b.children] for b in self.bones}
        self.length = {b.name: b.length for b in self.bones}

    def rest_pose(self):
        p = {n: self.rest_rot[n].copy() for n in self.rest}
        p["root"] = self.rest["Hips"].translation.copy()
        return p

    def descendants(self, name):
        out, stack = [], [name]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(self.children[n])
        return out

    # ---- forward kinematics (armature space == world, rigs are placed via root yaw/offset) ----
    def fk(self, pose):
        heads, tails = {}, {}
        for b in self.bones:
            n = b.name
            p = self.parent[n]
            if p is None:
                heads[n] = pose["root"].copy()
            else:
                off = self.rest_rot[p].inverted() @ (self.rest[n].translation - self.rest[p].translation)
                heads[n] = heads[p] + pose[p] @ off
            tails[n] = heads[n] + pose[n] @ Vector((0, self.length[n], 0))
        return heads, tails

    # ---- write pose as keyframes ----
    def key(self, pose, frame):
        rig = self.rig
        for b in self.bones:
            n = b.name
            pb = rig.pose.bones[n]
            pb.rotation_mode = 'QUATERNION'
            p = self.parent[n]
            if p is None:
                basis = self.rest_rot[n].inverted() @ pose[n]
                loc = self.rest_rot[n].inverted() @ (pose["root"] - self.rest[n].translation)
                pb.location = loc
                pb.keyframe_insert("location", frame=frame, group=n)
            else:
                rel = self.rest_rot[n].inverted() @ self.rest_rot[p]
                basis = rel @ pose[p].inverted() @ pose[n]
            # keep quaternion continuity to avoid flips in interpolation
            prev = pb.get("_prevq")
            if prev is not None and Quaternion(prev).dot(basis) < 0:
                basis = -basis
            pb["_prevq"] = list(basis)
            pb.rotation_quaternion = basis
            pb.keyframe_insert("rotation_quaternion", frame=frame, group=n)


# ------------------------------------------------------------------ mocap source
class MocapClip:
    def __init__(self, path, name):
        bpy.ops.import_anim.bvh(filepath=path, global_scale=1.0, frame_start=1, use_fps_scale=False,
                                rotate_mode='NATIVE', axis_forward='-Z', axis_up='Y')
        self.obj = bpy.context.object
        self.obj.name = "mocap_" + name
        self.act = self.obj.animation_data.action
        self.f0, self.f1 = [int(x) for x in self.act.frame_range]
        self.f0 += 1  # frame 1 of the cgspeed CMU release is a T-pose calibration frame
        self.fps = 120.0
        self.duration = (self.f1 - self.f0) / self.fps
        self.samples = {}
        self._bake()
        self.obj.hide_render = True
        self.obj.hide_viewport = True

    def _bake(self):
        sc = bpy.context.scene
        mw = self.obj.matrix_world.copy()
        self.rest_rot = {b.name: (mw @ b.matrix_local).to_quaternion() for b in self.obj.data.bones}
        self.rest_dir = {b.name: ((mw @ b.matrix_local).to_3x3() @ Vector((0, 1, 0))).normalized()
                         for b in self.obj.data.bones}
        for f in range(self.f0, self.f1 + 1):
            sc.frame_set(f)
            d = {}
            for pb in self.obj.pose.bones:
                d[pb.name] = (mw @ pb.matrix).to_quaternion()
            d["root"] = mw @ self.obj.pose.bones["Hips"].head
            self.samples[f] = d

    def raw(self, t):
        """World rotations of the source skeleton at clip time t (seconds), interpolated."""
        x = self.f0 + max(0.0, min(t * self.fps, self.f1 - self.f0))
        a = int(math.floor(x)); b = min(a + 1, self.f1); u = x - a
        A, B = self.samples[a], self.samples[b]
        out = {}
        for k in A:
            out[k] = A[k].lerp(B[k], u) if k == "root" else A[k].slerp(B[k], u)
        return out


class Retargeter:
    """Maps world-space rotation deltas from a BVH skeleton onto the MPFB rig."""

    def __init__(self, skel, clip):
        self.skel = skel
        self.clip = clip
        self.align = {}
        for n in skel.rest:
            if n not in clip.rest_rot:
                continue
            tdir = (skel.rest_rot[n] @ Vector((0, 1, 0))).normalized()
            self.align[n] = tdir.rotation_difference(clip.rest_dir[n])
        # scale from leg length
        bl = clip.obj.data.bones
        s_leg = (bl["LeftUpLeg"].head_local - bl["LeftFoot"].head_local).length
        t_leg = (skel.rest["LeftUpLeg"].translation - skel.rest["LeftFoot"].translation).length
        self.scale = t_leg / s_leg
        self.z_offset = 0.0
        # put the lowest foot point of the clip on the ground
        lows = []
        for f in range(clip.f0, clip.f1 + 1, 4):
            h, t = skel.fk(self.pose((f - clip.f0) / clip.fps))
            lows.append(min(t["LeftToeBase"].z, t["RightToeBase"].z, h["LeftToeBase"].z, h["RightToeBase"].z))
        lows.sort()
        self.z_offset = -lows[len(lows) // 10] + 0.02

    def pose(self, t):
        raw = self.clip.raw(t)
        pose = {}
        for n in self.skel.rest:
            if n in BONES_SKIP or n not in self.align:
                pose[n] = None
                continue
            delta = raw[n] @ self.clip.rest_rot[n].inverted()
            pose[n] = delta @ self.align[n] @ self.skel.rest_rot[n]
        # fingers follow the hand
        for n in self.skel.rest:
            if pose[n] is None:
                p = self.skel.parent[n]
                rel = self.skel.rest_rot[p].inverted() @ self.skel.rest_rot[n]
                pose[n] = pose[p] @ rel
        root = raw["root"]
        pose["root"] = root * self.scale + Vector((0, 0, self.z_offset))
        return pose


# ------------------------------------------------------------------ pose operations
def copy_pose(p):
    return {k: v.copy() for k, v in p.items()}


def rotate_subtree(skel, pose, bone, q):
    for n in skel.descendants(bone):
        pose[n] = q @ pose[n]


def rotate_all(skel, pose, q, pivot=None):
    rotate_subtree(skel, pose, "Hips", q)
    if pivot is None:
        pivot = Vector((pose["root"].x, pose["root"].y, 0))
    pose["root"] = pivot + q @ (pose["root"] - pivot)


def point_bone(skel, pose, bone, direction, carry_children=True):
    """Rotate bone so its axis points along direction (world); children follow if carry_children."""
    cur = (pose[bone] @ Vector((0, 1, 0))).normalized()
    q = cur.rotation_difference(Vector(direction).normalized())
    if carry_children:
        rotate_subtree(skel, pose, bone, q)
    else:
        pose[bone] = q @ pose[bone]


def blend(skel, a, b, w):
    if w <= 0:
        return copy_pose(a)
    if w >= 1:
        return copy_pose(b)
    out = {}
    for k in a:
        out[k] = a[k].lerp(b[k], w) if k == "root" else a[k].slerp(b[k], w)
    return out


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def axis_rot(axis, deg):
    return Quaternion(Vector(axis).normalized(), math.radians(deg))
