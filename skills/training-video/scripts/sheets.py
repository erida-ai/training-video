#!/usr/bin/env python3
"""Contact sheets of a finished video: one frame every N seconds, 4×5 per sheet, for the final visual check.

Usage: sheets.py <video.mp4> <out dir> [--every 10]
"""
import argparse
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("video")
p.add_argument("out")
p.add_argument("--every", type=float, default=10)
a = p.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
for old in out.glob("sheet_*.jpg"):
    old.unlink()
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", f"fps=1/{a.every},scale=480:-1,tile=4x5",
                str(out / "sheet_%02d.jpg")], check=True)
print("\n".join(str(x) for x in sorted(out.glob("sheet_*.jpg"))))
