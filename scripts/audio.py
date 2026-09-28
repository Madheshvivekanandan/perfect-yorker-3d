"""Synthesize the soundtrack (crowd, whoosh, stumps crash, roar, heartbeat) with numpy -> render/soundtrack.wav"""
import json
import os
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
meta = json.load(open(os.path.join(ROOT, "render", "shots.json")))
table = json.load(open(os.path.join(ROOT, "render", "frame_table.json")))
WF, OF = meta["world_fps"], meta["out_fps"]
T_REL, T_HIT = meta["T_REL"] * WF, meta["T_HIT"] * WF
DUR = len(table) / OF
N = int(DUR * SR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)


def first(shot, cond):
    for i, (name, label, wf) in enumerate(table):
        if name == shot and cond(wf):
            return i / OF
    return None


def shot_span(shot):
    idx = [i for i, row in enumerate(table) if row[0] == shot]
    return idx[0] / OF, (idx[-1] + 1) / OF


ev_release = first("delivery", lambda wf: wf >= T_REL)
ev_hit_slow = first("impact", lambda wf: wf >= T_HIT)
ev_hit_replay = first("replay", lambda wf: wf >= T_HIT)
slow0 = shot_span("delivery")[0]
slow1 = shot_span("impact")[1]
print("events", ev_release, ev_hit_slow, ev_hit_replay, slow0, slow1)


def lowpass(x, cutoff):
    """one-pole low-pass, cutoff may be an array (time-varying)"""
    a = np.exp(-2 * np.pi * np.broadcast_to(cutoff, x.shape) / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):             # vectorised enough for 30 s
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def fast_lowpass(x, cutoff):
    # FFT brick-ish low-pass for constant cutoff
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= (1 / (1 + (lo / np.maximum(f, 1)) ** 4)) * (1 / (1 + (f / hi) ** 4))
    return np.fft.irfft(X, len(x))


def env(points):
    xs, ys = zip(*points)
    return np.interp(t, xs, ys)


# ---------------- crowd: many voices ~ band-limited noise with slow random swells
crowd = band(rng.standard_normal(N), 250, 3500)
swell = fast_lowpass(rng.standard_normal(N), 0.6)
swell = 1 + 0.35 * swell / np.abs(swell).max()
crowd *= swell
crowd /= np.abs(crowd).max()
# murmur -> anticipation rising in the run-up -> muffled in slow motion -> huge roar
crowd_level = env([(0, 0.18), (8, 0.22), (slow0 - 0.2, 0.42), (slow0 + 0.3, 0.12), (ev_hit_slow, 0.1),
                   (ev_hit_slow + 0.25, 0.9), (DUR - 2.0, 0.75), (DUR, 0.0)])
muffle = env([(0, 0), (slow0, 0), (slow0 + 0.3, 1), (ev_hit_slow, 1), (ev_hit_slow + 0.4, 0), (DUR, 0)])
crowd_dull = fast_lowpass(crowd, 500)
crowd_mix = (crowd * (1 - muffle) + crowd_dull * muffle * 1.6) * crowd_level

# roar "ooh-AAH": formant-like tonal swell on top of the noise after the wicket
roar = band(rng.standard_normal(N), 400, 1800) * env([(0, 0), (ev_hit_slow, 0), (ev_hit_slow + 0.5, 0.6),
                                                        (ev_hit_slow + 3.0, 0.45), (DUR, 0.0)])
roar /= max(1e-9, np.abs(roar).max()) / 0.5

# ---------------- heartbeat / deep drum during the slow-motion build-up
drum = np.zeros(N)
beat = 0.78
bt = slow0
while bt < ev_hit_slow - 0.1:
    for off, amp in ((0, 1.0), (0.18, 0.6)):
        i0 = int((bt + off) * SR)
        n = int(0.35 * SR)
        tt = np.arange(n) / SR
        k = amp * np.sin(2 * np.pi * (55 - 25 * tt) * tt) * np.exp(-tt * 11)
        drum[i0:i0 + n] += k[: max(0, min(n, N - i0))]
    bt += beat

# ---------------- whoosh as the ball is released (slowed, so deep and long)
def whoosh(at, length, f0, f1, amp):
    out = np.zeros(N)
    i0 = int(at * SR)
    n = int(length * SR)
    seg = rng.standard_normal(n)
    cut = np.linspace(f0, f1, n)
    seg = lowpass(seg, cut)
    shape = np.sin(np.linspace(0, np.pi, n)) ** 2
    out[i0:i0 + n] = (seg * shape)[: max(0, min(n, N - i0))]
    return out / max(1e-9, np.abs(out).max()) * amp


fx = whoosh(ev_release - 0.1, 1.6, 300, 2200, 0.35)
fx += whoosh(shot_span("ball_cam")[0], shot_span("ball_cam")[1] - shot_span("ball_cam")[0], 200, 900, 0.25)


# ---------------- stumps crash: woody clack (modal synthesis) + bails rattle + sub boom
def clack(at, pitch=1.0, amp=1.0, boom=False):
    out = np.zeros(N)
    i0 = int(at * SR)
    n = int(1.5 * SR)
    tt = np.arange(n) / SR
    s = np.zeros(n)
    for f, d, a in ((820, 28, 1.0), (1650, 40, 0.6), (2400, 55, 0.4), (3900, 70, 0.25), (560, 20, 0.5)):
        s += a * np.sin(2 * np.pi * f * pitch * tt + rng.uniform(0, 6)) * np.exp(-tt * d * pitch)
    s += 0.5 * rng.standard_normal(n) * np.exp(-tt * 90 * pitch)
    for k in range(6):                     # bails & stumps rattling
        dt = 0.05 + k * 0.07 * (1 / pitch) + rng.uniform(0, 0.03)
        j = int(dt * SR)
        m = n - j
        s[j:] += 0.3 * np.exp(-k * 0.4) * np.sin(2 * np.pi * rng.uniform(2500, 4200) * pitch * tt[:m]) * np.exp(-tt[:m] * 120 * pitch)
    if boom:
        s += 1.6 * np.sin(2 * np.pi * (48 - 18 * tt) * tt) * np.exp(-tt * 2.2)
    out[i0:i0 + n] = s[: max(0, min(n, N - i0))]
    return out / max(1e-9, np.abs(out).max()) * amp


fx += clack(ev_hit_slow, pitch=0.45, amp=0.95, boom=True)
fx += clack(ev_hit_replay, pitch=0.7, amp=0.55)
# light footsteps during the run-up shots (real speed)
for name in ("run_track", "run_front"):
    a, b = shot_span(name)
    step = 0.733 / 1.15 / 2
    x = a
    while x < b:
        i0 = int(x * SR); n = int(0.08 * SR); tt = np.arange(n) / SR
        thud = 0.25 * np.sin(2 * np.pi * 90 * tt) * np.exp(-tt * 45) + 0.06 * rng.standard_normal(n) * np.exp(-tt * 80)
        fx[i0:i0 + n] += thud[: max(0, min(n, N - i0))]
        x += step

mix = 0.55 * crowd_mix + 0.35 * roar + 0.5 * drum + fx
mix *= env([(0, 0), (0.6, 1), (DUR - 1.2, 1), (DUR, 0)])
mix = np.tanh(mix * 1.1) * 0.9
stereo = np.stack([mix, np.roll(mix, 23) * 0.97], axis=1)     # slight width
pcm = (stereo * 32767).astype(np.int16)
with wave.open(os.path.join(ROOT, "render", "soundtrack.wav"), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote soundtrack", DUR, "s")
