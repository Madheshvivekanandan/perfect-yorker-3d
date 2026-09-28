"""Encode frames + overlays + soundtrack into the final MP4 with ffmpeg.

python3 scripts/assemble.py [frames_dir] [output.mp4]
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frames = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "render", "frames")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "cricket_yorker.mp4")
table = json.load(open(os.path.join(ROOT, "render", "frame_table.json")))
meta = json.load(open(os.path.join(ROOT, "render", "shots.json")))
OF = meta["out_fps"]
DUR = len(table) / OF


def span(shot):
    idx = [i for i, r in enumerate(table) if r[0] == shot]
    return idx[0] / OF, (idx[-1] + 1) / OF


FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
FONT2 = "/System/Library/Fonts/Supplemental/Impact.ttf"
H = "ih"


def fade_alpha(a, b, fin=0.35, fout=0.35):
    return (f"if(lt(t,{a}),0,if(lt(t,{a + fin}),(t-{a})/{fin},if(lt(t,{b - fout}),1,"
            f"if(lt(t,{b}),({b}-t)/{fout},0))))")


def text(txt, x, y, size, a, b, font=FONT, color="white", box=None, border=0, alpha=True):
    s = (f"drawtext=fontfile='{font}':text='{txt}':x={x}:y={y}:fontsize={size}:fontcolor={color}"
         f":enable='between(t,{a:.3f},{b:.3f})'")
    if alpha:
        s += f":alpha='{fade_alpha(a, b)}'"
    if box:
        s += f":box=1:boxcolor={box}:boxborderw={border}"
    return s


e0, e1 = span("establish")
r0, r1 = span("replay")
i0, i1 = span("impact")
f0, f1 = span("finale")
live_end = f0
filters = [
    # opening title
    text("THE PERFECT YORKER", "(w-text_w)/2", "h*0.36", "h*0.13", 0.5, e1 - 0.2, FONT2, "white@0.95",
         "black@0.0", 0),
    text("A 3D CRICKET SHORT", "(w-text_w)/2", "h*0.52", "h*0.045", 0.9, e1 - 0.2, FONT, "white@0.9"),
    # score strip (broadcast style) during live play
    text(" YELLOW  164-6   18.5 OV   TARGET 192 ", "w*0.04", "h*0.88", "h*0.042", e1, live_end,
         FONT, "white", "0x0a1a4a@0.85", 14),
    text(" LIVE ", "w*0.04", "h*0.83", "h*0.034", e1, live_end, FONT, "white", "0xd01818@0.9", 8),
    # speed gun during the impact
    text(" 140.4 KM/H ", "w*0.78", "h*0.10", "h*0.06", i0 + 0.4, i1, FONT, "white", "0xd01818@0.85", 14),
    # replay tag
    text(" REPLAY ", "w*0.83", "h*0.08", "h*0.05", r0 + 0.1, r1 - 0.05, FONT, "white", "0x0a1a4a@0.85", 12),
    # finale
    text("CLEAN BOWLED!", "(w-text_w)/2", "h*0.30", "h*0.16", f0 + 0.4, DUR - 0.3, FONT2, "white",
         None, 0),
    text("THE PERFECT YORKER", "(w-text_w)/2", "h*0.50", "h*0.05", f0 + 1.0, DUR - 0.3, FONT, "0xffd23a"),
    f"fade=t=in:st=0:d=0.6,fade=t=out:st={DUR - 0.8}:d=0.8",
]
vf = ",".join(filters)
audio = os.path.join(ROOT, "render", "soundtrack.wav")
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(OF), "-i", os.path.join(frames, "%04d.png")]
if os.path.exists(audio):
    cmd += ["-i", audio]
cmd += ["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow"]
if os.path.exists(audio):
    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
cmd += ["-movflags", "+faststart", out]
subprocess.run(cmd, check=True)
print("wrote", out)
