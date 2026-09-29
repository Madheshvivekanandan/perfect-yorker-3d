"""Pose layer system: mocap retargeting (CMU BVH -> MPFB "default" MakeHuman rig) + procedural overrides.

A "pose" is a dict: {"_pos": Vector (hips world position), bone_name: Quaternion (world rotation)}.
Working in world rotations makes blending mocap with hand-authored overrides simple.

Animation code uses CMU-style bone names (Hips, LeftArm, Spine1, ...). ALIAS maps them onto the
MakeHuman default rig, which has proper 3-segment fingers for convincing hands.
"""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector

ALIAS = {"Hips": "root", "LowerBack": "spine05", "Spine": "spine03", "Spine1": "spine01",
         "Neck": "neck01", "Neck1": "neck02", "Head": "head"}
for _cmu, _mh in (("Left", ".L"), ("Right", ".R")):
    ALIAS.update({f"{_cmu}Shoulder": f"clavicle{_mh}", f"{_cmu}Arm": f"upperarm01{_mh}",
                  f"{_cmu}ForeArm": f"lowerarm01{_mh}", f"{_cmu}Hand": f"wrist{_mh}",
                  f"{_cmu}UpLeg": f"upperleg01{_mh}", f"{_cmu}Leg": f"lowerleg01{_mh}",
                  f"{_cmu}Foot": f"foot{_mh}", f"{_cmu}ToeBase": f"toe1-1{_mh}"})
ALIAS["LHipJoint"] = "pelvis.L"
ALIAS["RHipJoint"] = "pelvis.R"
REVERSE = {v: k for k, v in ALIAS.items()}


def bn(name):
    """Real rig bone name for a CMU-style (or already real) name."""
    return ALIAS.get(name, name)


class AliasDict(dict):
    """dict that accepts CMU-style bone names as aliases for the real rig names."""

    def __getitem__(self, k):
        return dict.__getitem__(self, ALIAS.get(k, k))

    def __setitem__(self, k, v):
        dict.__setitem__(self, ALIAS.get(k, k), v)

    def __contains__(self, k):
        return dict.__contains__(self, ALIAS.get(k, k))

    def get(self, k, d=None):
        return dict.get(self, ALIAS.get(k, k), d)


class Skeleton:
    """Rest-pose info of the target (MPFB) rig."""

    def __init__(self, rig):
        self.rig = rig
        # body bones only: facial bones below the head keep their rest pose (faster FK + keying)
        face = set()
        for c in rig.data.bones["head"].children_recursive:
            face.add(c.name)
        self.bones = [b for b in rig.data.bones if b.name not in face]   # parents come before children
        names = {b.name for b in self.bones}
        self.rest = AliasDict({b.name: b.matrix_local.copy() for b in self.bones})
        self.rest_rot = AliasDict({n: m.to_quaternion() for n, m in self.rest.items()})
        self.parent = AliasDict({b.name: (b.parent.name if b.parent else None) for b in self.bones})
        self.children = AliasDict({b.name: [c.name for c in b.children if c.name in names] for b in self.bones})
        self.length = AliasDict({b.name: b.length for b in self.bones})

    def rest_pose(self):
        p = AliasDict({n: self.rest_rot[n].copy() for n in self.rest})
        p["_pos"] = self.rest["Hips"].translation.copy()
        return p

    def descendants(self, name):
        out, stack = [], [bn(name)]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(self.children[n])
        return out

    # ---- forward kinematics (armature space == world, rigs are placed via root yaw/offset) ----
    def fk(self, pose):
        heads, tails = AliasDict(), AliasDict()
        for b in self.bones:
            n = b.name
            p = self.parent[n]
            if p is None:
                heads[n] = pose["_pos"].copy()
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
                loc = self.rest_rot[n].inverted() @ (pose["_pos"] - self.rest[n].translation)
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
            d["_pos"] = mw @ self.obj.pose.bones["Hips"].head
            self.samples[f] = d

    def raw(self, t):
        """World rotations of the source skeleton at clip time t (seconds), interpolated."""
        x = self.f0 + max(0.0, min(t * self.fps, self.f1 - self.f0))
        a = int(math.floor(x)); b = min(a + 1, self.f1); u = x - a
        A, B = self.samples[a], self.samples[b]
        out = {}
        for k in A:
            out[k] = A[k].lerp(B[k], u) if k == "_pos" else A[k].slerp(B[k], u)
        return out


class Retargeter:
    """Maps world-space rotation deltas from a BVH skeleton onto the MPFB rig."""

    def __init__(self, skel, clip):
        self.skel = skel
        self.clip = clip
        self.align = {}
        for n in skel.rest:
            src = REVERSE.get(n)
            if src is None or src not in clip.rest_rot:
                continue
            tdir = (skel.rest_rot[n] @ Vector((0, 1, 0))).normalized()
            self.align[n] = tdir.rotation_difference(clip.rest_dir[src])
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
        pose = AliasDict()
        for n in self.skel.rest:
            if n not in self.align:
                pose[n] = None
                continue
            src = REVERSE[n]
            delta = raw[src] @ self.clip.rest_rot[src].inverted()
            pose[n] = delta @ self.align[n] @ self.skel.rest_rot[n]
        # unmapped bones (twist segments, fingers, toes, clavicle ends) follow their parent rigidly
        for b in self.skel.bones:
            n = b.name
            if pose[n] is None:
                p = self.skel.parent[n]
                rel = self.skel.rest_rot[p].inverted() @ self.skel.rest_rot[n]
                pose[n] = pose[p] @ rel
        root = raw["_pos"]
        pose["_pos"] = root * self.scale + Vector((0, 0, self.z_offset))
        return pose


# ------------------------------------------------------------------ pose operations
def copy_pose(p):
    return AliasDict({k: v.copy() for k, v in p.items()})


def rotate_subtree(skel, pose, bone, q):
    for n in skel.descendants(bone):
        pose[n] = q @ pose[n]


def rotate_all(skel, pose, q, pivot=None):
    rotate_subtree(skel, pose, "Hips", q)
    if pivot is None:
        pivot = Vector((pose["_pos"].x, pose["_pos"].y, 0))
    pose["_pos"] = pivot + q @ (pose["_pos"] - pivot)


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
    out = AliasDict()
    for k in a:
        out[k] = a[k].lerp(b[k], w) if k == "_pos" else a[k].slerp(b[k], w)
    return out


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def axis_rot(axis, deg):
    return Quaternion(Vector(axis).normalized(), math.radians(deg))


# ------------------------------------------------------------------ hands
# per-finger flexion (degrees) for segments 1..3; finger1 = thumb. Flexion is the bone's local +X axis.
HAND_SHAPES = {
    "open":    {1: (0, 0, 0), 2: (0, 0, 0), 3: (0, 0, 0), 4: (0, 0, 0), 5: (0, 0, 0)},
    "relaxed": {1: (8, 10, 8), 2: (18, 25, 15), 3: (22, 30, 18), 4: (26, 34, 20), 5: (30, 38, 22)},
    "fist":    {1: (30, 35, 30), 2: (80, 95, 60), 3: (85, 95, 60), 4: (88, 95, 60), 5: (90, 95, 60)},
    # cricket grip: index & middle along the top of the ball, ring/little tucked, thumb underneath
    "ball":    {1: (38, 20, 15), 2: (28, 38, 22), 3: (28, 38, 22), 4: (60, 70, 45), 5: (70, 75, 50)},
    "grip":    {1: (35, 30, 20), 2: (65, 75, 50), 3: (70, 78, 50), 4: (72, 80, 50), 5: (75, 80, 50)},
}


def hand_shape(skel, pose, side, shape, weight=1.0):
    """Curl the fingers of one hand ('Left'/'Right') into a named shape (or a blend toward it)."""
    s = ".L" if side == "Left" else ".R"
    table = HAND_SHAPES[shape] if isinstance(shape, str) else shape
    for f, segs in table.items():
        for i, deg in enumerate(segs, start=1):
            b = f"finger{f}-{i}{s}"
            if b not in pose or not deg:
                continue
            q = pose[b] @ Quaternion((1, 0, 0), math.radians(deg * weight)) @ pose[b].inverted()
            rotate_subtree(skel, pose, b, q)


def palm_frame(skel, pose, side):
    """(palm centre, palm normal, finger direction) in world space for placing a held ball."""
    s = ".L" if side == "Left" else ".R"
    heads, tails = skel.fk(pose)
    base = heads[f"finger3-1{s}"]
    wrist = heads[f"wrist{s}"]
    fdir = (base - wrist).normalized()
    normal = (pose[f"metacarpal2{s}"] @ Vector((0, 0, 1))).normalized()
    return wrist.lerp(base, 0.75), normal, fdir
