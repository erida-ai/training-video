#!/usr/bin/env python3
"""Subtitles from the timeline of the finished video, one .srt per language, with identical timings.

Usage: srt.py <video dir> <name>
  timeline.json   [{"id": slide, "beats": [{"id", "start", "dur"}]}] — written by the render
  script.json     the script (lines.py); "text" of every beat is the subtitle of the video's own language
  subs/<lang>.json  {"<line id>": "translation"} — one per extra language in video.json "subtitles"
Writes final/<name>.<lang>.srt for every language and fails when a translation misses a line.
"""
import json
import sys
from pathlib import Path

import tvlib


def ts(x):
    ms = round(x * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def write(video, name):
    cfg = tvlib.video_config(video)
    beats = [b for s in json.loads((video / "timeline.json").read_text(encoding="utf-8")) for b in s["beats"]]
    script = json.loads((video / "script.json").read_text(encoding="utf-8"))
    texts = {cfg["lang"]: {b["id"]: b["text"] for ch in script["chapters"] for b in ch["beats"]}}
    for code in cfg["subtitles"]:
        if code != cfg["lang"]:
            texts[code] = json.loads((video / "subs" / f"{code}.json").read_text(encoding="utf-8"))
    (video / "final").mkdir(exist_ok=True)
    for code in cfg["subtitles"]:
        t = texts[code]
        missing = [b["id"] for b in beats if not t.get(b["id"])]
        if missing:
            raise SystemExit(f"{code}: no text for {' '.join(missing)}")
        cues = [f"{n}\n{ts(b['start'])} --> {ts(b['start'] + b['dur'])}\n{t[b['id']]}\n" for n, b in enumerate(beats, 1)]
        path = video / "final" / f"{name}.{code}.srt"
        path.write_text("\n".join(cues), encoding="utf-8")
        print(f"{path}: {len(cues)} subtitles")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    write(Path(sys.argv[1]).resolve(), sys.argv[2])
