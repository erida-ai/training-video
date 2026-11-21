#!/usr/bin/env python3
"""Voices a whole video: audio/txt/<id>.txt → audio/<id>.wav (+ .log), then voices.py.

The reference line (video.json "ref", else the first id) is generated first; every other line is checked against it.
Lines whose log already says check=clean with the current setup are skipped unless --force.

Usage: narrate.py <video dir> [--only id …] [--sample N] [--force] [--jobs 6]
  --sample N   only the reference and the next N-1 lines — the voice sample for approval
  --only       just these lines (e.g. the REDO list of voices.py), against the same reference
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tvlib
import voices

HERE = Path(__file__).resolve().parent


def run(video, i, ref):
    audio = video / "audio"
    cmd = [sys.executable, "-B", str(HERE / "tts.py"), str(audio / "txt" / f"{i}.txt"), str(audio / f"{i}.wav")]
    if ref and ref != i:
        cmd += ["--ref", str(audio / f"{ref}.wav")]
    with open(audio / f"{i}.log", "w", encoding="utf-8") as log:
        # the child writes Cyrillic into the log; TV_PROJECT (set by video_config) carries the project's key
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUTF8": "1"})
    tail = (audio / f"{i}.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:] or [""]
    status = "ok" if r.returncode == 0 else "FAIL"
    print(f"{status} {i}: {tail[0][-160:]}", flush=True)
    return r.returncode == 0


def clean(video, i):
    log = video / "audio" / f"{i}.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    return voices.LINE.search(text) and "check=clean" in text


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--only", nargs="+")
    p.add_argument("--sample", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--jobs", type=int, default=6)
    a = p.parse_args()
    video = Path(a.video).resolve()
    cfg = tvlib.video_config(video)
    ids = sorted(x.stem for x in (video / "audio" / "txt").glob("*.txt"))
    if not ids:
        raise SystemExit(f"no lines in {video}/audio/txt — write the script first")
    ref = cfg.get("ref") or ids[0]
    print(f"access: {tvlib.describe_access()}; lang={cfg['lang']} voice={cfg['voice']} ref={ref}", flush=True)
    todo = a.only or ([ref] + [i for i in ids if i != ref][: (a.sample - 1)] if a.sample else ids)
    if not a.force and not a.only:
        todo = [i for i in todo if not clean(video, i)]
    if ref in todo or not (video / "audio" / f"{ref}.wav").exists():
        if not run(video, ref, None):
            raise SystemExit("the reference line failed — fix it first (see its log)")
        todo = [i for i in todo if i != ref]
    with ThreadPoolExecutor(a.jobs) as pool:
        list(pool.map(lambda i: run(video, i, ref), todo))
    if a.sample:
        print(f"sample ready: {' '.join(str(video / 'audio' / f'{i}.wav') for i in [ref] + todo)}")
        return
    sys.exit(1 if voices.report(video) else 0)


if __name__ == "__main__":
    main()
