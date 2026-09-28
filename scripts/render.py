"""Render the shot list from render/cricket.blend into PNG frames (24 fps output).

Blender -b render/cricket.blend --python scripts/render.py -- [--stills] [--from N] [--to M] [--res 1920x1080] [--samples 96]
"""
import json
import math
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


meta = json.load(open(os.path.join(ROOT, "render", "shots.json")))
WF, OF = meta["world_fps"], meta["out_fps"]
sc = bpy.context.scene
if arg("--res"):
    w, h = arg("--res").split("x")
    sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
if arg("--samples"):
    sc.eevee.taa_render_samples = int(arg("--samples"))

# build the output frame -> (shot, world frame) table
table = []
for s in meta["shots"]:
    n = int(round((s["w1"] - s["w0"]) / s["speed"] * OF))
    for k in range(n):
        wt = s["w0"] + k / OF * s["speed"]
        table.append((s, wt * WF))
print("TOTAL OUTPUT FRAMES", len(table))
with open(os.path.join(ROOT, "render", "frame_table.json"), "w") as fh:
    json.dump([[s["name"], s.get("label"), wf] for s, wf in table], fh)

out_dir = os.path.join(ROOT, "render", arg("--out", "stills" if "--stills" in argv else "frames"))
os.makedirs(out_dir, exist_ok=True)

if "--stills" in argv:
    idx = []
    start = 0
    for s in meta["shots"]:
        n = int(round((s["w1"] - s["w0"]) / s["speed"] * OF))
        idx += [start + n // 4, start + (3 * n) // 4]
        start += n
else:
    idx = range(int(arg("--from", 0)), int(arg("--to", len(table))))

for i in idx:
    path = os.path.join(out_dir, f"{i:04d}.png")
    if os.path.exists(path) and "--overwrite" not in argv:
        continue
    s, wf = table[i]
    sc.camera = bpy.data.objects[s["camera"]]
    # 180-degree shutter in output time, expressed in world frames
    sc.render.motion_blur_shutter = 0.5 * (WF / OF) * s["speed"]
    fi = int(math.floor(wf))
    sc.frame_set(fi, subframe=wf - fi)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", i, s["name"], round(wf, 2), flush=True)
