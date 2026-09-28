"""Build the complete cricket scene: 'The Perfect Yorker'.

Run:  Blender -b --python scripts/build.py
Produces render/cricket.blend and render/shots.json (consumed by render.py).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(__file__))
import props as P
from anim import (WORLD_FPS, BowlerTrack, bowling_overrides, breathe, celebration_pose, lerp_keys, look_at,
                  place, stance_pose)
from characters import kit, make_human, remove_part
from posing import MocapClip, Skeleton, axis_rot, blend, copy_pose, point_bone, rotate_subtree, smoothstep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCAP = os.path.join(ROOT, "assets", "mocap")
OUT = os.path.join(ROOT, "render")
PREVIEW = "--preview" in sys.argv

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
sc = bpy.context.scene
sc.render.fps = WORLD_FPS
sc.unit_settings.system = 'METRIC'

# ============================================================== timeline (world seconds)
T_RUN = 7.0                    # bowler starts the run-up
CREASE_FRONT_FOOT_Y = 19.15    # front foot lands just behind the bowler's popping crease (18.90)
BOWLER_X = 0.42                # over the wicket, right-arm

# ============================================================== environment
P.setup_world("stadium_01", strength=1.0, rotation_deg=100)
sun = P.add_sun(energy=4.2, elev=52, azim=-40)
P.build_ground()
stumps, bails = P.build_wicket(0.0, "striker")
far_stumps, far_bails = P.build_wicket(P.BOWL_END_Y, "bowler")
far_mat = bpy.data.materials["LEDBail"].copy()
for b in far_bails:
    b.data.materials[0] = far_mat
ball = P.build_ball()

# ============================================================== characters
def human(name, **kw):
    rig, body = make_human(name, **kw)
    return rig

bowler = human("Bowler", skin="young_asian_male", hair="short02", height=0.72, muscle=0.75, weight=0.4)
kit(bowler, "male_casualsuit04", (0.008, 0.035, 0.22), (0.006, 0.02, 0.1))
batsman = human("Batsman", skin="young_caucasian_male", hair=None, height=0.6, muscle=0.65,
                race={"asian": 0.1, "caucasian": 0.8, "african": 0.1})
kit(batsman, "male_casualsuit04", (0.95, 0.72, 0.05), (0.9, 0.66, 0.04))
nonstriker = human("NonStriker", skin="young_african_male", hair=None, height=0.55,
                   race={"asian": 0.1, "caucasian": 0.1, "african": 0.8})
kit(nonstriker, "male_casualsuit04", (0.95, 0.72, 0.05), (0.9, 0.66, 0.04))
keeper = human("Keeper", skin="young_asian_male", hair="short04", height=0.45)
kit(keeper, "male_casualsuit04", (0.008, 0.035, 0.22), (0.006, 0.02, 0.1))
slip1 = human("Slip1", skin="young_caucasian_male2", hair="short01", height=0.55,
              race={"asian": 0.2, "caucasian": 0.7, "african": 0.1})
kit(slip1, "male_casualsuit04", (0.008, 0.035, 0.22), (0.006, 0.02, 0.1))
slip2 = human("Slip2", skin="young_african_male", hair="short03", height=0.6,
              race={"asian": 0.2, "caucasian": 0.1, "african": 0.7})
kit(slip2, "male_casualsuit04", (0.008, 0.035, 0.22), (0.006, 0.02, 0.1))
ring = []
for i, (nm, sk_, rc) in enumerate((("MidOff", "young_asian_male", {"asian": 0.8, "caucasian": 0.1, "african": 0.1}),
                                   ("MidOn", "young_caucasian_male", {"asian": 0.2, "caucasian": 0.7, "african": 0.1}),
                                   ("Point", "young_african_male", {"asian": 0.1, "caucasian": 0.1, "african": 0.8}),
                                   ("SquareLeg", "young_asian_male", {"asian": 0.7, "caucasian": 0.2, "african": 0.1}))):
    rr = human(nm, skin=sk_, hair=("short02", "short04", "short03", "short01")[i], height=0.5 + 0.05 * i, race=rc)
    kit(rr, "male_casualsuit04", (0.008, 0.035, 0.22), (0.006, 0.02, 0.1))
    ring.append(rr)
umpire = human("Umpire", skin="middleage_caucasian_male", hair="short02", height=0.5, muscle=0.4, weight=0.6,
               race={"asian": 0.1, "caucasian": 0.8, "african": 0.1}, clothes=("male_casualsuit01", "shoes02"))
kit(umpire, "male_casualsuit01", (0.08, 0.35, 0.75), (0.03, 0.03, 0.035), waist_z=1.0)

# protective gear
pad_mat = P.simple_mat("PadWhite", (0.85, 0.85, 0.83), rough=0.7)
P.noise_bump(pad_mat.node_tree, pad_mat.node_tree.nodes["Principled BSDF"], scale=300, strength=0.1)
glove_mat = P.simple_mat("GloveWhite", (0.88, 0.88, 0.86), rough=0.6)
keeper_glove = P.simple_mat("KeeperGlove", (0.9, 0.9, 0.88), rough=0.6)
helmet_mat = P.simple_mat("HelmetShell", (0.02, 0.2, 0.08), rough=0.3, coat=0.8)
grille_mat = P.simple_mat("Grille", (0.6, 0.6, 0.62), rough=0.3, metal=1.0)
for r in (batsman, nonstriker, keeper):
    for side in ("Left", "Right"):
        P.build_pad(f"{r.name}_pad{side}", r, side, pad_mat)
        P.build_glove(f"{r.name}_glove{side}", r, side, keeper_glove if r is keeper else glove_mat)
for r in (batsman, nonstriker):
    P.build_helmet(f"{r.name}_helmet", r, helmet_mat, grille_mat)

bat = P.build_bat("Bat")
ns_bat = P.build_bat("NSBat")

skels = {r.name: Skeleton(r) for r in [bowler, batsman, nonstriker, keeper, slip1, slip2, umpire] + ring}

# ============================================================== bowler performance
clipA = MocapClip(os.path.join(MOCAP, "16_55.bvh"), "start")
clipB = MocapClip(os.path.join(MOCAP, "09_01.bvh"), "loop")
bsk = skels["Bowler"]
track = BowlerTrack(bsk, clipA, clipB, t_run_start=T_RUN, run_rate=1.15)

# first pass (straight run) to find the delivery stride
track.build(T_RUN + 6.0, rate_fn=lambda t: 1.15, heading_fn=lambda t: 0.0, stop_fn=lambda t: 0.0)
lc = track.foot_contacts("Left", T_RUN + 3.3, T_RUN + 5.5)
T_REL = lc[0][0] if lc[0][0] > T_RUN + 3.8 else lc[1][0]
print("RELEASE at", T_REL)

T_CEL = T_REL + 1.35          # start of celebration
def rate_fn(t):
    return 1.15 - 0.4 * smoothstep(T_REL + 0.3, T_REL + 1.3, t)
def heading_fn(t):
    return 38 * smoothstep(T_REL + 0.2, T_REL + 1.6, t)
def stop_fn(t):
    return smoothstep(T_CEL - 0.1, T_CEL + 0.5, t)

T_END = T_REL + 11.0
track.build(T_END, rate_fn, heading_fn, stop_fn)
# place the run so the front foot lands behind the popping crease
_, pfoot = next((c for c in track.foot_contacts("Left", T_REL - 0.05, T_REL + 0.05)), (None, None))
h, _ = bsk.fk(track.raw[track.index(T_REL)])
shift = Vector((BOWLER_X - track.raw[track.index(T_REL)]["root"].x,
                CREASE_FRONT_FOOT_Y - h["LeftFoot"].y, 0))
for p in track.raw:
    p["root"] += shift

stand = copy_pose(track.raw[0])


def bowler_pose(t):
    i = track.index(t)
    p = bowling_overrides(bsk, track.raw[i], t, T_REL, T_RUN, T_RUN)
    if t > T_CEL - 0.4:
        w = smoothstep(T_CEL - 0.4, T_CEL + 0.4, t)
        base = copy_pose(stand)
        # stand where the bowler stopped, facing the heading direction
        rotate_subtree(bsk, base, "Hips", axis_rot((0, 0, 1), heading_fn(t)))
        base["root"] = Vector((p["root"].x, p["root"].y, stand["root"].z))
        cel = celebration_pose(bsk, base, t, T_CEL)
        p = blend(bsk, p, cel, w)
    return p


# ---- key the bowler; dense keys during the delivery
def key_times(t0, t1, segments):
    """segments: list of (ta, tb, step_frames). Returns world frames."""
    frames = set()
    f = int(t0 * WORLD_FPS)
    while f <= int(t1 * WORLD_FPS):
        step = 8
        for ta, tb, st in segments:
            if ta <= f / WORLD_FPS <= tb:
                step = min(step, st)
        frames.add(f)
        f += step
    return sorted(frames)


bowler_frames = key_times(0, T_END, [(T_RUN - 0.5, T_REL + 2.0, 2), (T_REL - 0.7, T_REL + 0.4, 1)])
hand_track = {}
for f in bowler_frames:
    t = f / WORLD_FPS
    p = bowler_pose(t)
    bsk.key(p, f)
    heads, tails = bsk.fk(p)
    hand_track[f] = (heads["RightHand"], tails["RightHand"], p["RightHand"])
print("bowler keyed", len(bowler_frames))

# ============================================================== ball trajectory
G = 9.81
f_rel = int(round(T_REL * WORLD_FPS))
hh, ht, hq = hand_track[f_rel]
P0 = ht + (ht - hh).normalized() * 0.01
SPEED = 39.0                          # ~140 km/h
BOUNCE_Y = 0.95                       # yorker: pitches right at the batsman's toes
STUMP_FRONT = P.STUMP_R + P.BALL_R
T1 = (P0.y - BOUNCE_Y) / SPEED
vz0 = (P.BALL_R - P0.z + 0.5 * G * T1 ** 2) / T1
vz_imp = vz0 - G * T1
V2Y = SPEED * 0.86
vz2 = -0.35 * vz_imp
T2 = (BOUNCE_Y - STUMP_FRONT) / V2Y
T_BOUNCE = T_REL + T1
T_HIT = T_BOUNCE + T2
X_REL, X_HIT = P0.x, 0.0
print(f"flight {T1:.3f}s, hit at {T_HIT:.3f}, release height {P0.z:.2f}")


def ball_pos(t):
    if t <= T_REL:
        f = int(round(t * WORLD_FPS))
        # closest keyed hand sample
        k = min(hand_track.keys(), key=lambda x: abs(x - f))
        hh, ht, hq = hand_track[k]
        palm = hq @ Vector((0, 0, 1))
        return ht - (ht - hh).normalized() * 0.02 + palm * 0.03
    if t <= T_BOUNCE:
        u = t - T_REL
        s = u / (T_HIT - T_REL)
        x = X_REL + (X_HIT - X_REL) * (s ** 1.8)        # late in-swing
        return Vector((x, P0.y - SPEED * u, P0.z + vz0 * u - 0.5 * G * u * u))
    if t <= T_HIT + 0.004:
        u = t - T_BOUNCE
        s = (t - T_REL) / (T_HIT - T_REL)
        x = X_REL + (X_HIT - X_REL) * (min(s, 1) ** 1.8)
        return Vector((x, BOUNCE_Y - V2Y * u, P.BALL_R + vz2 * u - 0.5 * G * u * u))
    # after smashing the stump: ball loses most of its pace, deflects to leg side and rolls away
    ph = ball_pos(T_HIT + 0.004)
    u = t - (T_HIT + 0.004)
    v = Vector((-4.0, -11.0, 1.5))
    decay = 1.2
    s = (1 - math.exp(-decay * u)) / decay
    pos = ph + Vector((v.x * s, v.y * s, 0))
    z = ph.z + v.z * u - 0.5 * G * u * u
    if z < P.BALL_R:                               # small bounces then roll
        tb = (v.z + math.sqrt(v.z ** 2 + 2 * G * (ph.z - P.BALL_R))) / G
        uu = u - tb
        z = P.BALL_R + max(0.0, 1.2 * math.sin(min(uu * 5, math.pi)) * 0.12 * math.exp(-uu))
    pos.z = z
    return pos


ball.rotation_mode = 'XYZ'
f_end = int(T_END * WORLD_FPS)
ball_frames = sorted(set([f for f in bowler_frames if f <= f_rel] +
                         list(range(f_rel, int((T_HIT + 1.5) * WORLD_FPS))) +
                         list(range(int((T_HIT + 1.5) * WORLD_FPS), f_end, 4))))
spin = 0.0
prev_t = None
for f in ball_frames:
    t = f / WORLD_FPS
    ball.location = ball_pos(t)
    if t > T_REL and prev_t is not None:
        rate = 2 * math.pi * (18 if t < T_HIT else 6 * math.exp(-(t - T_HIT)))   # backspin rev/s
        spin += rate * (t - prev_t)
    prev_t = t
    ball.rotation_euler = (spin, 0.25, 0)
    ball.keyframe_insert("location", frame=f)
    ball.keyframe_insert("rotation_euler", frame=f)

# ============================================================== batsman + bat
ssk = skels["Batsman"]
BAT_POS = Vector((-0.40, 0.92, 0))
stance = stance_pose(ssk, knee=22, lean=28, spread=10, head_yaw=78, head_pitch=5)


def bat_matrix(top, toe, face_dir=Vector((0, 1, 0))):
    d = (toe - top).normalized()          # local -Z
    z = -d
    y = -(face_dir - d * face_dir.dot(d)).normalized()   # local -Y is the face
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = top
    return m


def bat_state(t):
    """Returns (top, toe) of the bat in world space."""
    stance_top, stance_toe = Vector((-0.2, 0.98, 0.86)), Vector((0.0, 1.0, 0.02))
    tap = 0.0
    for tt in (2.0, 3.1, 4.3, 5.4, T_RUN + 1.5, T_RUN + 2.6):
        tap = max(tap, math.exp(-((t - tt) / 0.12) ** 2))
    toe = stance_toe + Vector((0, 0, 0.06 * tap))
    top = stance_top.copy()
    keys_top = [(T_REL - 0.45, stance_top), (T_REL - 0.05, Vector((-0.22, 0.82, 1.02))),
                (T_REL + 0.14, Vector((-0.2, 0.78, 1.08))), (T_HIT, Vector((-0.12, 0.98, 0.95))),
                (T_HIT + 0.10, Vector((-0.1, 1.1, 0.85))), (T_HIT + 1.2, Vector((-0.12, 1.08, 0.86))),
                (T_HIT + 2.2, Vector((-0.32, 1.0, 0.8)))]
    keys_toe = [(T_REL - 0.45, stance_toe), (T_REL - 0.05, Vector((-0.05, 0.25, 1.35))),
                (T_REL + 0.14, Vector((0.0, 0.05, 1.55))), (T_HIT - 0.012, Vector((0.02, 1.0, 0.18))),
                (T_HIT + 0.10, Vector((0.05, 1.35, 0.03))), (T_HIT + 1.2, Vector((0.05, 1.35, 0.03))),
                (T_HIT + 2.2, Vector((-0.3, 1.55, 0.04)))]
    if t >= T_REL - 0.45:
        top = lerp_keys(keys_top, t)
        toe = lerp_keys(keys_toe, t)
    # keep the bat length constant
    d = (toe - top).normalized()
    return top, top + d * 0.95


bat.rotation_mode = 'QUATERNION'
bat_frames = key_times(0, T_END, [(T_REL - 0.6, T_HIT + 0.4, 1)])
prevq = None
for f in bat_frames:
    t = f / WORLD_FPS
    top, toe = bat_state(t)
    m = bat_matrix(top, toe)
    q = m.to_quaternion()
    if prevq is not None and prevq.dot(q) < 0:
        q = -q
    prevq = q
    bat.location = m.translation
    bat.rotation_quaternion = q
    bat.keyframe_insert("location", frame=f)
    bat.keyframe_insert("rotation_quaternion", frame=f)


def ik(rig, bone, target, pole, pole_angle=0.0):
    c = rig.pose.bones[bone].constraints.new('IK')
    c.target = target
    c.pole_target = pole
    c.pole_angle = pole_angle
    c.chain_count = 2
    return c


def empty(name, parent=None, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    sc.collection.objects.link(e)
    e.empty_display_size = 0.05
    e.parent = parent
    e.location = loc
    return e


# grips on the handle (bat local: handle runs 0 .. -0.34 on Z)
gripL = empty("gripL", bat, (0.0, 0.035, -0.07))
gripR = empty("gripR", bat, (0.0, 0.035, -0.17))
poleL = empty("poleL", None, (BAT_POS.x + 0.6, BAT_POS.y + 0.9, 0.9))
poleR = empty("poleR", None, (BAT_POS.x + 0.5, BAT_POS.y - 0.7, 0.6))
ik(batsman, "LeftForeArm", gripL, poleL)
ik(batsman, "RightForeArm", gripR, poleR)


def batsman_pose(t):
    p = breathe(ssk, stance, t, amp=1.0)
    # backlift: small torso coil; after the dismissal: stand up, turn to look back at the wreckage
    coil = lerp_keys([(T_REL - 0.45, 0.0), (T_REL + 0.1, 1.0), (T_HIT, 0.4), (T_HIT + 0.2, 0.0)], t)
    rotate_subtree(ssk, p, "LowerBack", axis_rot((0, 0, 1), -8 * coil))
    rise = smoothstep(T_HIT + 0.9, T_HIT + 2.2, t)
    if rise > 0:
        up = stance_pose(ssk, knee=6, lean=10, spread=8, head_yaw=0, head_pitch=-5)
        p = blend(ssk, p, up, rise)
    pp = place(ssk, p, 90, BAT_POS.x, BAT_POS.y)
    look = lerp_keys([(0, 0.0), (T_HIT + 0.25, 0.0), (T_HIT + 0.6, 1.0), (T_HIT + 2.4, 1.0), (T_HIT + 3.4, 0.0)], t)
    if look > 0:
        look_at(ssk, pp, (0.0, -0.1, 0.35), look, pitch_limit=45)
    return pp


for f in key_times(0, T_END, [(T_REL - 0.6, T_HIT + 3.5, 4)]):
    ssk.key(batsman_pose(f / WORLD_FPS), f)

# ============================================================== non-striker, umpire, fielders
nsk = skels["NonStriker"]
ns_bat.parent = nonstriker
ns_bat.parent_type = 'BONE'
ns_bat.parent_bone = "RightHand"
ns_bat.rotation_euler = (math.radians(90), 0, 0)
ns_bat.location = (0, -0.06, 0.0)


def ns_pose(t):
    p = stance_pose(nsk, knee=8, lean=8, spread=7, head_yaw=-10,
                    arm_dirs={"RightArm": (-0.15, -0.35, -0.9), "RightForeArm": (-0.05, -0.8, -0.55),
                              "LeftArm": (0.15, 0.0, -0.98), "LeftForeArm": (0.1, -0.3, -0.9)})
    p = breathe(nsk, p, t, phase=0.3)
    # backs up a couple of steps as the ball is bowled (slides a little along the pitch)
    back = smoothstep(T_REL - 0.6, T_REL + 0.6, t) * 1.4
    pp = place(nsk, p, 0, -1.55, 18.55 - back)
    look_at(nsk, pp, ball_pos(min(t, T_HIT + 0.3)) if t > T_REL - 1.0 else Vector((0, 0, 1.2)), 0.8)
    return pp


usk = skels["Umpire"]


def umpire_pose(t):
    p = stance_pose(usk, knee=10, lean=22, spread=7,
                    arm_dirs={"LeftArm": (0.05, -0.35, -0.94), "RightArm": (-0.05, -0.35, -0.94),
                              "LeftForeArm": (-0.4, -0.85, -0.2), "RightForeArm": (0.4, -0.85, -0.2)})
    p = breathe(usk, p, t, phase=0.6)
    pp = place(usk, p, 0, -0.62, 22.35)
    look_at(usk, pp, ball_pos(min(max(t, T_REL - 0.2), T_HIT + 0.3)) if t > T_REL - 0.3 else Vector((0, 0, 0.8)), 0.9)
    return pp


def fielder_pose(sk, t, x, y, knee, lean, phase):
    crouch = stance_pose(sk, knee=knee, lean=lean, spread=16,
                         arm_dirs={"LeftArm": (0.12, -0.6, -0.8), "RightArm": (-0.12, -0.6, -0.8),
                                   "LeftForeArm": (-0.25, -0.75, -0.6), "RightForeArm": (0.25, -0.75, -0.6)})
    upright = stance_pose(sk, knee=4, lean=-6, spread=8,
                          arm_dirs={"LeftArm": (0.55, 0.0, 0.85), "RightArm": (-0.55, 0.0, 0.85),
                                    "LeftForeArm": (0.3, 0.0, 1.0), "RightForeArm": (-0.3, 0.0, 1.0)})
    # rise into the crouch as the bowler approaches, erupt after the wicket
    ready = smoothstep(T_REL - 1.8, T_REL - 1.0, t)
    idle = stance_pose(sk, knee=10, lean=18, spread=10,
                       arm_dirs={"LeftArm": (0.1, -0.4, -0.9), "RightArm": (-0.1, -0.4, -0.9)})
    p = blend(sk, idle, crouch, ready)
    joy = smoothstep(T_HIT + 0.35 + phase, T_HIT + 0.9 + phase, t)
    p = blend(sk, p, upright, joy)
    if joy > 0.5:
        p["root"].z += 0.12 * abs(math.sin((t - T_HIT - phase) * math.tau * 1.3)) * joy
    return place(sk, p, 180, x, y)


fielders = [(skels["Keeper"], 0.35, -15.5, 62, 30, 0.0), (skels["Slip1"], 2.2, -16.4, 30, 42, 0.12),
            (skels["Slip2"], 4.1, -16.0, 30, 42, 0.2)]
# ring fielders walk in as the bowler runs up, then celebrate
RING_POS = {"MidOff": (9.5, 27.0, 200), "MidOn": (-10.5, 26.0, 160), "Point": (24.0, 1.5, 250),
            "SquareLeg": (-23.0, -1.0, 110)}


def ring_pose(sk, t, name):
    x, y, _ = RING_POS[name]
    yaw = math.degrees(math.atan2(0 - x, -(5 - y)))       # face the striker's end
    walk = smoothstep(T_RUN, T_REL, t)
    ph = (len(name) % 7) / 10
    idle = stance_pose(sk, knee=6, lean=6, spread=7,
                       arm_dirs={"LeftArm": (0.15, -0.1, -0.98), "RightArm": (-0.15, -0.1, -0.98)})
    ready = stance_pose(sk, knee=22, lean=24, spread=12,
                        arm_dirs={"LeftArm": (0.2, -0.5, -0.8), "RightArm": (-0.2, -0.5, -0.8),
                                  "LeftForeArm": (0.0, -0.8, -0.5), "RightForeArm": (0.0, -0.8, -0.5)})
    joy = stance_pose(sk, knee=4, lean=-4, spread=8,
                      arm_dirs={"LeftArm": (0.5, 0.0, 0.86), "RightArm": (-0.5, 0.0, 0.86),
                                "LeftForeArm": (0.3, 0.0, 1.0), "RightForeArm": (-0.3, 0.0, 1.0)})
    p = blend(sk, idle, ready, smoothstep(T_REL - 0.8, T_REL - 0.2, t))
    p = blend(sk, p, joy, smoothstep(T_HIT + 0.4 + ph, T_HIT + 1.0 + ph, t))
    p = breathe(sk, p, t, phase=ph)
    d = Vector((0 - x, 10 - y, 0)).normalized()
    return place(sk, p, yaw, x + d.x * 3.0 * walk, y + d.y * 3.0 * walk)


static_frames = key_times(0, T_END, [(T_REL - 2.0, T_HIT + 3.0, 6)])
for f in static_frames:
    t = f / WORLD_FPS
    nsk.key(ns_pose(t), f)
    usk.key(umpire_pose(t), f)
    for sk, x, y, kn, le, ph in fielders:
        sk.key(fielder_pose(sk, t, x, y, kn, le, ph), f)
    if f % 12 == 0 or (T_REL - 1 < t < T_HIT + 2 and f % 6 == 0):
        for rr in ring:
            skels[rr.name].key(ring_pose(skels[rr.name], t, rr.name), f)
print("supporting cast keyed")

# ============================================================== stumps physics (Bullet), baked to keyframes
F_HIT = int(T_HIT * WORLD_FPS)
bpy.ops.rigidbody.world_add()
rbw = sc.rigidbody_world
rbw.substeps_per_frame = 4
rbw.solver_iterations = 30
rbw.point_cache.frame_start = F_HIT - 40
rbw.point_cache.frame_end = F_HIT + int(9.5 * WORLD_FPS)
rbw.time_scale = 1.0


def rb_add(obj, kind='ACTIVE', shape='CONVEX_HULL', mass=1.0, friction=0.5, bounce=0.2):
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        bpy.ops.rigidbody.object_add(type=kind)
    rb = obj.rigid_body
    rb.collision_shape = shape
    rb.mass = mass
    rb.friction = friction
    rb.restitution = bounce
    rb.use_margin = True
    rb.collision_margin = 0.0005
    rb.linear_damping = 0.15
    rb.angular_damping = 0.2
    return rb


def origin_to_center(obj):
    me = obj.data
    c = sum((v.co for v in me.vertices), Vector()) / len(me.vertices)
    for v in me.vertices:
        v.co -= c
    obj.location += c


for o in stumps + bails:
    origin_to_center(o)
for o in stumps:
    rb = rb_add(o, mass=0.4, friction=0.7, bounce=0.25)
    rb.use_deactivation = True
    rb.use_start_deactivated = True
for o in bails:
    rb = rb_add(o, mass=0.025, friction=0.5, bounce=0.35)
    rb.use_deactivation = True
    rb.use_start_deactivated = True
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.5))
floor = bpy.context.object
floor.name = "FloorCollider"
floor.scale = (40, 40, 1)
rb_add(floor, kind='PASSIVE', shape='BOX', friction=0.8, bounce=0.3)
floor.hide_render = True
rbb = rb_add(ball, kind='ACTIVE', shape='SPHERE', mass=0.16, bounce=0.3)
rbb.kinematic = True

sim = {o.name: {} for o in stumps + bails}
for f in range(rbw.point_cache.frame_start, rbw.point_cache.frame_end + 1):
    sc.frame_set(f)
    for o in stumps + bails:
        sim[o.name][f] = o.matrix_world.copy()
print("simulated stumps")
with bpy.context.temp_override(scene=sc):
    bpy.ops.rigidbody.world_remove()
for o in stumps + bails + [ball]:
    if o.rigid_body:
        with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
            bpy.ops.rigidbody.object_remove()
bpy.data.objects.remove(floor)
for o in stumps + bails:
    o.rotation_mode = 'QUATERNION'
    frames = sorted(sim[o.name])
    prev = None
    for f in frames:
        m = sim[o.name][f]
        if prev is not None and f < frames[-1] and (m.translation - prev.translation).length < 1e-6 and f > F_HIT + 20:
            continue
        loc, q, _ = m.decompose()
        o.location = loc
        o.rotation_quaternion = q
        o.keyframe_insert("location", frame=f)
        o.keyframe_insert("rotation_quaternion", frame=f)
        prev = m
    moved = (sim[o.name][frames[-1]].translation - sim[o.name][frames[0]].translation).length
    print("  ", o.name, "moved", round(moved, 3))

# LED bails flash red when dislodged
bmat = bpy.data.materials["LEDBail"]
em = bmat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
em.default_value = 0.0
em.keyframe_insert("default_value", frame=F_HIT - 1)
for k in range(0, 24):
    f = F_HIT + 1 + k * 12
    em.default_value = 25.0 if k % 2 == 0 else 2.0
    em.keyframe_insert("default_value", frame=f)
em.default_value = 25.0
em.keyframe_insert("default_value", frame=F_HIT + 1 + 24 * 12)
print("physics done; T_HIT", T_HIT)

# ============================================================== render settings
r = sc.render
r.engine = 'BLENDER_EEVEE'
r.resolution_x, r.resolution_y = (960, 540) if PREVIEW else (1920, 1080)
r.resolution_percentage = 100
r.use_motion_blur = True
r.film_transparent = False
ee = sc.eevee
ee.taa_render_samples = 32 if PREVIEW else 96
ee.use_raytracing = True
ee.use_shadows = True
ee.shadow_ray_count = 2
ee.shadow_step_count = 8
ee.use_fast_gi = True
ee.fast_gi_method = 'GLOBAL_ILLUMINATION'
ee.motion_blur_steps = 2
sc.view_settings.view_transform = 'AgX'
try:
    sc.view_settings.look = 'AgX - Medium High Contrast'
except TypeError:
    pass
sc.view_settings.exposure = 0.1

# ============================================================== cameras & shot list
def cam_obj(name, lens=50, fstop=2.8):
    c = bpy.data.cameras.new(name)
    c.lens = lens
    c.sensor_width = 36
    c.dof.use_dof = True
    c.dof.aperture_fstop = fstop
    c.clip_start = 0.03
    c.clip_end = 2000
    o = bpy.data.objects.new(name, c)
    sc.collection.objects.link(o)
    return o


def aim(cam, pos, target, roll=0.0):
    cam.location = pos
    d = (Vector(target) - Vector(pos))
    q = d.to_track_quat('-Z', 'Y')
    if roll:
        q = q @ Quaternion((0, 0, 1), math.radians(roll))
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = q
    return d.length


def bowler_root(t):
    return track.raw[track.index(t)]["root"]


def bowler_chest(t):
    h, _ = bsk.fk(bowler_pose(t))
    return h["Spine1"]


shots = []


def shot(name, w0, w1, speed, fn, lens=50, fstop=2.8, label=None, step=2):
    """fn(t) -> (cam_pos, target, focus_dist or None, lens or None)."""
    cam = cam_obj("CAM_" + name, lens, fstop)
    prevq = None
    f = int(w0 * WORLD_FPS) - 6
    while f <= int(w1 * WORLD_FPS) + 6:
        t = f / WORLD_FPS
        pos, tgt, focus, ln = fn(t)
        dist = aim(cam, pos, tgt)
        if prevq is not None and prevq.dot(cam.rotation_quaternion) < 0:
            cam.rotation_quaternion = -cam.rotation_quaternion
        prevq = cam.rotation_quaternion.copy()
        cam.data.dof.focus_distance = focus if focus else dist
        if ln:
            cam.data.lens = ln
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_quaternion", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        cam.data.dof.keyframe_insert("focus_distance", frame=f)
        f += step
    shots.append({"name": name, "camera": cam.name, "w0": w0, "w1": w1, "speed": speed, "label": label})
    return cam


def ease(a, b, u):
    u = max(0.0, min(1.0, u))
    u = u * u * (3 - 2 * u)
    return a + (b - a) * u


# S1: wide establishing crane, sweeping down from high behind the bowler's end
def s1(t):
    u = t / 4.0
    pos = ease(Vector((26, 62, 24)), Vector((12, 44, 7.5)), u)
    tgt = ease(Vector((0, 12, 0)), Vector((0, 8, 1.0)), u)
    return pos, tgt, None, None
shot("establish", 0.0, 4.0, 1.0, s1, lens=28, fstop=11, label="title")

# S2: bowler at the top of his mark, polishing the ball (85mm, slow arc)
b0 = bowler_root(4.0).copy()
def s2(t):
    u = (t - 4.0) / 2.5
    a = math.radians(ease(-35, -5, u))
    c = bowler_chest(t)
    pos = Vector((b0.x - 1.1 + 0.25 * u, b0.y + 2.3 - 0.35 * u, 1.72))
    tgt = Vector((c.x - 0.25, c.y - 6.0, 1.2))
    return pos, tgt, (c - pos).length, None
shot("polish", 4.0, 6.5, 1.0, s2, lens=38, fstop=2.0)

# S3: over the batsman's shoulder, rack focus from helmet to the bowler starting his run
def s3(t):
    pos = Vector((-0.9, -1.4, 1.6))
    tgt = Vector((0.9, 30, 1.25))
    near = 2.45
    far = (bowler_root(t) - pos).length
    focus = ease(near, far, (t - 6.9) / 0.9)
    return pos, tgt, focus, None
shot("over_shoulder", 6.5, 8.5, 1.0, s3, lens=65, fstop=2.2)

# S4a: side-on tracking dolly with the run-up (off side)
def s4a(t):
    rt = bowler_root(t)
    pos = Vector((rt.x + 6.5, rt.y - 1.2, 1.25))
    return pos, rt + Vector((0, -0.4, 0.2)), None, None
shot("run_track", 8.5, 9.9, 1.0, s4a, lens=45, fstop=2.8)

# S4b: classic long-lens TV angle from behind the striker's stumps
T4B_END = T_REL - 0.5
def s4b(t):
    pos = Vector((0.9, -9.0, 1.75))
    c = bowler_chest(t)
    return pos, c, None, ease(200, 170, (t - 9.9) / (T4B_END - 9.9))
shot("run_front", 9.9, T4B_END, 1.0, s4b, lens=200, fstop=4.0)

# S5: delivery stride in slow motion, low angle from the off side
def s5(t):
    c = bowler_chest(t)
    u = (t - (T_REL - 0.5)) / 0.62
    pos = Vector((BOWLER_X + ease(4.2, 3.4, u), ease(17.6, 16.9, u), 0.55))
    return pos, c + Vector((0, -0.3, 0.0)), None, None
shot("delivery", T_REL - 0.5, T_REL + 0.12, 0.3, s5, lens=22, fstop=2.8, step=1)

# S6: chase-cam behind the ball as it swings in towards the batsman
T6_END = T_HIT - 0.06
def s6(t):
    bp = ball_pos(max(t, T_REL))
    cy = max(bp.y + 2.6, 3.4)
    pos = Vector((bp.x * 0.5 + 0.35, cy, 0.35 + 0.5 * max(0, (bp.y - 3) / 16) + bp.z * 0.4))
    tgt = Vector((bp.x * 0.5, bp.y - 3.0, bp.z * 0.5 + 0.1)) if bp.y > 3.6 else Vector((0, 0.2, 0.35))
    return pos, tgt, (bp - pos).length, None
shot("ball_cam", T_REL, T6_END, 0.25, s6, lens=30, fstop=2.0, step=1)

# S7: ground-level super slow motion at the stumps
def s7(t):
    pos = Vector((1.45, 1.05, 0.14))
    return pos, Vector((0.0, 0.2, 0.28)), 1.6, None
shot("impact", T_HIT - 0.06, T_HIT + 0.3, 0.1, s7, lens=30, fstop=4.0, step=1)

# S8: replay end-on from behind the keeper
def s8(t):
    pos = Vector((0.45, -11.5, 2.3))
    return pos, Vector((0, 6.0, 0.7)), 12.0, ease(95, 125, (t - (T_REL - 0.3)) / 1.4)
shot("replay", T_REL - 0.3, T_HIT + 0.85, 0.5, s8, lens=95, fstop=5.6, label="replay", step=1)

# S9: the bowler's celebration, low hero angle in front of him
T9 = T_HIT + 0.9
cel_root = bowler_root(T_CEL + 0.5).copy()
def s9(t):
    rt = bowler_root(t)
    u = (t - T9) / 3.3
    fwd = axis_rot((0, 0, 1), heading_fn(t)) @ Vector((0, -1, 0))
    side = Vector((-fwd.y, fwd.x, 0))
    pos = rt + fwd * ease(3.8, 2.6, u) + side * 1.2
    pos.z = 0.8
    return pos, bowler_chest(t) + Vector((0, 0, 0.25)), None, None
shot("celebrate", T9, T9 + 3.3, 1.0, s9, lens=40, fstop=2.0)

# S10: finale crane rising from the shattered stumps
used = sum((s["w1"] - s["w0"]) / s["speed"] for s in shots)
dur10 = 30.0 - used
T10 = T9 + 3.3
def s10(t):
    u = (t - T10) / dur10
    pos = ease(Vector((2.5, 3.2, 0.5)), Vector((14, -12, 16)), u)
    tgt = ease(Vector((0, 0, 0.2)), Vector((0, 6, 0)), u)
    return pos, tgt, None, None
shot("finale", T10, T10 + dur10, 1.0, s10, lens=26, fstop=8, label="clean_bowled")
print("SHOTS", [(s["name"], round((s["w1"] - s["w0"]) / s["speed"], 2)) for s in shots])

sc.frame_start = 0
sc.frame_end = int((T10 + dur10 + 1) * WORLD_FPS)
sc.camera = bpy.data.objects["CAM_establish"]

meta = {"world_fps": WORLD_FPS, "out_fps": 24, "T_REL": T_REL, "T_HIT": T_HIT, "shots": shots}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "shots.json"), "w") as fh:
    json.dump(meta, fh, indent=1)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "cricket.blend"))
print("SAVED")
