#!/usr/bin/env python3
"""script.json → audio/txt/<id>.txt, one file per line, in video order.

script.json: {"chapters": [{"id": "s01", "title": "…", "beats": [{"id": "s01_00", "text": "…", "say": "…"}]}]}
  text — what the subtitles show; say (optional) — what the voice says when the text reads badly aloud.
  Missing ids are filled in (s<chapter>_<beat>, zero-padded so that sorting keeps the video order) and saved back.
A line whose spoken text changed loses its old wav and log, so narrate.py generates it again; lines that no
longer exist are removed. Prints what changed.

Usage: lines.py <video dir>
"""
import json
import sys
from pathlib import Path


def sync(video):
    path = video / "script.json"
    script = json.loads(path.read_text(encoding="utf-8"))
    filled = False
    for ci, ch in enumerate(script["chapters"]):
        if not ch.get("id"):
            ch["id"], filled = f"s{ci:02d}", True
        for bi, b in enumerate(ch["beats"]):
            if not b.get("id"):
                b["id"], filled = f"{ch['id']}_{bi:02d}", True
    if filled:
        path.write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")
    beats = [b for ch in script["chapters"] for b in ch["beats"]]
    ids = [b["id"] for b in beats]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise SystemExit("line ids must be unique and sort in video order (e.g. s01_00, s01_01, s02_00)")
    txt = video / "audio" / "txt"
    txt.mkdir(parents=True, exist_ok=True)
    changed, new = [], []
    for b in beats:
        spoken = (b.get("say") or b["text"]).strip()
        f = txt / f"{b['id']}.txt"
        if f.exists() and f.read_text(encoding="utf-8").strip() == spoken:
            continue
        (changed if f.exists() else new).append(b["id"])
        f.write_text(spoken, encoding="utf-8")
        for old in (video / "audio" / f"{b['id']}.wav", video / "audio" / f"{b['id']}.log"):
            old.unlink(missing_ok=True)
    gone = [f.stem for f in txt.glob("*.txt") if f.stem not in ids]
    for i in gone:
        for old in (txt / f"{i}.txt", video / "audio" / f"{i}.wav", video / "audio" / f"{i}.log"):
            old.unlink(missing_ok=True)
    print(f"{len(ids)} lines; new {len(new)}, changed {len(changed)} {' '.join(changed)}, removed {len(gone)} {' '.join(gone)}")
    if changed and ids[0] in changed:
        print("the reference line changed: generate it first and listen, then narrate.py --force for a uniform voice")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sync(Path(sys.argv[1]).resolve())
