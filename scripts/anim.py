"""Character animation: mocap run-up + procedural bowling action, batsman and fielders."""
import math
from mathutils import Quaternion, Vector
from posing import (Retargeter, axis_rot, blend, copy_pose, point_bone, rotate_all, rotate_subtree,
                    smoothstep)

WORLD_FPS = 240
LEG_BONES = ["LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
POSE_FEATURES = LEG_BONES + ["LeftArm", "RightArm", "LeftForeArm", "RightForeArm"]


def pose_dist(a, b, bones=POSE_FEATURES):
    return sum(1 - abs(a[n].dot(b[n])) for n in bones)


def lerp_keys(keys, t):
    """Piecewise smooth interpolation of [(t, value)] (value float or Vector)."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)
            return v0 + (v1 - v0) * u
    return keys[-1][1]


def look_at(skel, pose, target, weight=1.0, pitch_limit=35):
    heads, _ = skel.fk(pose)
    head = heads["Head"]
    fwd_rest = Vector((0, -1, 0))
    f = (pose["Head"] @ skel.rest_rot["Head"].inverted()) @ fwd_rest
    d = (Vector(target) - head).normalized()
    # limit pitch
    horiz = Vector((d.x, d.y, 0)).normalized()
    el = math.asin(max(-1, min(1, d.z)))
    el = max(-math.radians(pitch_limit), min(math.radians(pitch_limit), el))
    d = horiz * math.cos(el) + Vector((0, 0, math.sin(el)))
    q = f.rotation_difference(d)
    q = Quaternion().slerp(q, weight)
    half = Quaternion().slerp(q, 0.5)
    rotate_subtree(skel, pose, "Neck", half)
    rotate_subtree(skel, pose, "Head", half)


def fix_feet_to_ground(skel, pose, ground=0.0, margin=0.015):
    h, t = skel.fk(pose)
    low = min(h["LeftToeBase"].z, h["RightToeBase"].z, t["LeftToeBase"].z, t["RightToeBase"].z,
              h["LeftFoot"].z - 0.06, h["RightFoot"].z - 0.06)
    pose["root"].z += ground + margin - low


# =================================================================== bowler
class BowlerTrack:
    """Samples the bowler's full performance at WORLD_FPS and stores world-space poses."""

    def __init__(self, skel, clip_start, clip_loop, t_run_start=7.0, run_rate=1.15):
        self.skel = skel
        self.rA = Retargeter(skel, clip_start)
        self.rB = Retargeter(skel, clip_loop)
        self.T0 = t_run_start
        self.rate = run_rate
        self._find_loop()
        self._find_transition()

    # ---------- motion analysis
    def _find_loop(self):
        r = self.rB
        dur = r.clip.duration
        best = None
        for L in [x / 120 for x in range(66, 110)]:
            for c0 in [x / 120 for x in range(0, int((dur - L - 0.05) * 120), 2)]:
                d = pose_dist(r.pose(c0), r.pose(c0 + L)) + pose_dist(r.pose(c0 + 0.04), r.pose(c0 + L + 0.04))
                if best is None or d < best[0]:
                    best = (d, c0, L)
        self.loop_err, self.c0, self.L = best
        a, b = r.pose(self.c0)["root"], r.pose(self.c0 + self.L)["root"]
        self.cycle_disp = Vector((b.x - a.x, b.y - a.y, 0))
        print(f"LOOP c0={self.c0:.3f} L={self.L:.3f} err={self.loop_err:.3f} disp={self.cycle_disp.length:.2f}m")

    def _find_transition(self):
        best = None
        durA = self.rA.clip.duration
        for tA in [x / 120 for x in range(int(0.8 * 120), int((durA - 0.05) * 120), 2)]:
            pa = self.rA.pose(tA)
            pa2 = self.rA.pose(tA + 0.04)
            for k in range(0, int(self.L * 120), 2):
                tB = self.c0 + k / 120
                d = pose_dist(pa, self.rB.pose(tB)) + pose_dist(pa2, self.rB.pose(tB + 0.04 * self.rate))
                if best is None or d < best[0]:
                    best = (d, tA, tB)
        _, self.tA, self.tB = best
        print(f"TRANSITION tA={self.tA:.3f} tB={self.tB:.3f} err={best[0]:.3f}")

    def loop_time(self, s):
        """map unbounded loop-clip time to (clip time, cycle index)."""
        u = s - self.c0
        n = math.floor(u / self.L)
        return self.c0 + (u - n * self.L), n

    def loop_pose(self, s):
        """Pose from looping clip B; root carries accumulated cycle displacement. Crossfades the seam."""
        tb, n = self.loop_time(s)
        p = self.rB.pose(tb)
        p["root"] = p["root"] + self.cycle_disp * n
        fade = 0.06
        if tb > self.c0 + self.L - fade:            # blend toward the start of next cycle
            w = (tb - (self.c0 + self.L - fade)) / fade
            q = self.rB.pose(tb - self.L)
            q["root"] = q["root"] + self.cycle_disp * (n + 1)
            p = blend(self.skel, p, q, w)
        return p

    # ---------- raw locomotion (no overrides), before path placement
    def build(self, t_end, rate_fn, heading_fn, stop_fn):
        """Integrate root motion at WORLD_FPS. rate_fn(t): playback rate of loop, heading_fn(t): yaw deg,
        stop_fn(t): 0..1 blend to standing."""
        dt = 1 / WORLD_FPS
        self.times = []
        self.raw = []
        pos = Vector((0, 0, 0))
        prev_src_root = None
        s_loop = self.tB
        t = 0.0
        stand = self.rA.pose(0.0)
        fade_w = 0.2
        clip_state = "A"
        while t <= t_end + 1e-9:
            tt = t - self.T0
            if tt < 0:
                p = copy_pose(stand)
                src_root = p["root"].copy()
            elif tt < self.tA:
                p = self.rA.pose(tt)
                src_root = p["root"].copy()
            else:
                # loop clip with variable rate; crossfade from A in the first fade_w seconds
                p = self.loop_pose(s_loop)
                src_root = p["root"].copy()
                if clip_state == "A":
                    clip_state = "B"
                    prev_src_root = src_root.copy()
                if tt < self.tA + fade_w:
                    w = (tt - self.tA) / fade_w
                    pa = self.rA.pose(min(tt, self.rA.clip.duration))
                    pa["root"] = p["root"]
                    p = blend(self.skel, pa, p, smoothstep(0, 1, w))
                s_loop += dt * rate_fn(t)
            # root integration (horizontal displacement from source, rotated by heading)
            if prev_src_root is None:
                prev_src_root = src_root.copy()
            d = src_root - prev_src_root
            prev_src_root = src_root.copy()
            st = stop_fn(t)
            yaw = axis_rot((0, 0, 1), heading_fn(t))
            pos += (yaw @ Vector((d.x, d.y, 0))) * (1 - st)
            # orient pose by heading around its own root
            loc_root = p["root"].copy()
            rotate_all(self.skel, p, yaw, pivot=Vector((loc_root.x, loc_root.y, 0)))
            p["root"] = Vector((pos.x, pos.y, p["root"].z))
            self.times.append(t)
            self.raw.append(p)
            t += dt
        return self

    def index(self, t):
        return max(0, min(len(self.raw) - 1, int(round(t * WORLD_FPS))))

    def foot_contacts(self, foot, t0, t1):
        """times of mid-stance for a foot between t0..t1 (local minima of foot height with low speed)."""
        zs = []
        for i in range(self.index(t0), self.index(t1)):
            h, tl = self.skel.fk(self.raw[i])
            zs.append((self.times[i], h[f"{foot}Foot"].z, h[f"{foot}Foot"].copy()))
        mids, run = [], []
        thr = min(z for _, z, _ in zs) + 0.03
        for t, z, p in zs:
            if z < thr:
                run.append((t, p))
            elif run:
                mids.append(run[len(run) // 2]); run = []
        if run:
            mids.append(run[len(run) // 2])
        return mids


def bowling_overrides(skel, p, t, tr, idle_end, T0):
    """Layer the bowling action (upper body) onto a running pose. tr = release time."""
    out = copy_pose(p)
    # ---- idle: polishing the ball on the trouser, looking at the batsman
    w_idle = 1 - smoothstep(T0 - 0.35, T0 + 0.15, t)
    if w_idle > 0:
        q = copy_pose(out)
        osc = math.sin(t * math.tau * 2.2)
        # rubbing the ball on the front of the right thigh, wrist straight
        fore = Vector((0.05, -0.32 - 0.12 * osc, -0.94))
        point_bone(skel, q, "RightArm", (-0.1, -0.12, -0.99))
        point_bone(skel, q, "RightForeArm", fore)
        point_bone(skel, q, "RightHand", fore)
        point_bone(skel, q, "LeftArm", (0.18, 0.02, -0.98))
        point_bone(skel, q, "LeftForeArm", (0.05, -0.35, -0.9))
        look_at(skel, q, (0, 0, 1.4), 0.9)
        out = blend(skel, out, q, w_idle)

    # ---- delivery stride
    w = smoothstep(tr - 0.62, tr - 0.40, t) * (1 - smoothstep(tr + 0.45, tr + 0.95, t))
    if w <= 0:
        return out
    q = copy_pose(out)
    yaw = lerp_keys([(tr - 0.5, 0), (tr - 0.32, -75), (tr - 0.15, -70), (tr + 0.02, 5), (tr + 0.12, 30), (tr + 0.5, 15)], t)
    pitch = lerp_keys([(tr - 0.5, 0), (tr - 0.3, -12), (tr - 0.1, -8), (tr + 0.08, 30), (tr + 0.25, 42), (tr + 0.6, 20)], t)
    side = lerp_keys([(tr - 0.5, 0), (tr - 0.2, -12), (tr + 0.0, -18), (tr + 0.2, 0)], t)   # lean away (over the top)
    rq = axis_rot((1, 0, 0), pitch) @ axis_rot((0, 1, 0), side) @ axis_rot((0, 0, 1), yaw)
    half = Quaternion().slerp(rq, 0.5)
    rotate_subtree(skel, q, "LowerBack", half)
    rotate_subtree(skel, q, "Spine1", half)
    # bowling arm windmill (right arm): angle a measured from +Y (behind) through +Z (up) to -Y (towards batsman)
    a = lerp_keys([(tr - 0.5, -60), (tr - 0.36, -40), (tr - 0.22, 0), (tr - 0.1, 50), (tr, 102), (tr + 0.07, 165),
                   (tr + 0.16, 225), (tr + 0.32, 255), (tr + 0.6, 260)], t)
    across = lerp_keys([(tr + 0.05, 0.0), (tr + 0.3, 0.55), (tr + 0.6, 0.5)], t)
    ar = math.radians(a)
    arm_dir = Vector((-0.08 + across, math.cos(ar), math.sin(ar)))
    point_bone(skel, q, "RightArm", arm_dir)
    point_bone(skel, q, "RightForeArm", arm_dir)
    # wrist stays in line with the arm; small forward flick through release
    wr = math.radians(a + lerp_keys([(tr - 0.1, 0), (tr, 10), (tr + 0.1, 22)], t))
    point_bone(skel, q, "RightHand", Vector((across * 0.5, math.cos(wr), math.sin(wr))))
    # front (left) arm: high & pointing at the batsman at the gather, then pulled down hard
    la = lerp_keys([(tr - 0.5, Vector((0.3, -0.2, -0.9))), (tr - 0.32, Vector((0.25, -0.55, 0.8))),
                    (tr - 0.12, Vector((0.3, -0.7, 0.6))), (tr + 0.02, Vector((0.55, 0.2, -0.5))),
                    (tr + 0.2, Vector((0.35, 0.5, -0.75))), (tr + 0.6, Vector((0.3, 0.1, -0.9)))], t)
    lf = lerp_keys([(tr - 0.5, Vector((0.1, -0.6, -0.4))), (tr - 0.32, Vector((0.1, -0.6, 0.8))),
                    (tr - 0.12, Vector((0.05, -0.8, 0.5))), (tr + 0.02, Vector((0.2, 0.4, -0.2))),
                    (tr + 0.2, Vector((0.0, 0.7, 0.1))), (tr + 0.6, Vector((0.0, -0.4, -0.6)))], t)
    point_bone(skel, q, "LeftArm", la)
    point_bone(skel, q, "LeftForeArm", lf)
    look_at(skel, q, (0, 0, 0.5), 0.8)
    return blend(skel, out, q, w)


def celebration_pose(skel, base, t, tc):
    """Arms raised in a V, chest out, roaring to the sky; later fist pumps."""
    q = copy_pose(base)
    lt = t - tc
    pump = math.sin(lt * math.tau * 2.4) * smoothstep(0.2, 0.5, lt)
    rotate_subtree(skel, q, "Spine", axis_rot((1, 0, 0), -10 - 3 * pump))
    up = 1.0
    for side, sx in (("Left", 1), ("Right", -1)):
        arm_up = Vector((0.55 * sx, -0.05, 0.85 + 0.05 * pump))
        fore_up = Vector((0.25 * sx, -0.1, 1.0))
        arm_dn = Vector((0.35 * sx, -0.3, -0.6))
        fore_dn = Vector((0.1 * sx, -0.9, 0.4 + 0.3 * pump))
        point_bone(skel, q, f"{side}Arm", arm_up.lerp(arm_dn, 1 - up))
        point_bone(skel, q, f"{side}ForeArm", fore_up.lerp(fore_dn, 1 - up))
    rotate_subtree(skel, q, "Neck", axis_rot((1, 0, 0), -18 * up))
    return q


# =================================================================== static-ish characters
def stance_pose(skel, knee=20, lean=25, spread=9, head_yaw=0, head_pitch=0, arm_dirs=None):
    """Build a pose from the rest pose in the character's local frame (facing -Y, left = +X)."""
    p = skel.rest_pose()
    for side, s in (("Left", 1), ("Right", -1)):
        rotate_subtree(skel, p, f"{side}UpLeg", axis_rot((0, 1, 0), -s * spread))
        rotate_subtree(skel, p, f"{side}UpLeg", axis_rot((1, 0, 0), -knee))
        rotate_subtree(skel, p, f"{side}Leg", axis_rot((1, 0, 0), 2 * knee))
        rotate_subtree(skel, p, f"{side}Foot", axis_rot((1, 0, 0), -knee))
    rotate_subtree(skel, p, "LowerBack", axis_rot((1, 0, 0), lean * 0.6))
    rotate_subtree(skel, p, "Spine1", axis_rot((1, 0, 0), lean * 0.4))
    rotate_subtree(skel, p, "Neck", axis_rot((1, 0, 0), -lean * 0.6 + head_pitch))
    rotate_subtree(skel, p, "Neck", axis_rot((0, 0, 1), head_yaw * 0.5))
    rotate_subtree(skel, p, "Head", axis_rot((0, 0, 1), head_yaw * 0.5))
    for bone, d in (arm_dirs or {}).items():
        point_bone(skel, p, bone, d)
    fix_feet_to_ground(skel, p)
    return p


def place(skel, pose, yaw_deg, x, y):
    q = copy_pose(pose)
    rotate_all(skel, q, axis_rot((0, 0, 1), yaw_deg), pivot=Vector((q["root"].x, q["root"].y, 0)))
    q["root"] = Vector((x, y, q["root"].z))
    return q


def breathe(skel, pose, t, amp=1.5, rate=0.25, phase=0.0):
    q = copy_pose(pose)
    s = math.sin((t * rate + phase) * math.tau)
    rotate_subtree(skel, q, "Spine1", axis_rot((1, 0, 0), amp * s))
    return q
