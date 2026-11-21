#!/usr/bin/env python3
"""Report over audio/*.log of a video: every line must have the same model, voice, language, style and temperature,
be clean by check.py and keep a similar pace. Prints what to generate again (REDO) and what the run cost.

Usage: voices.py <video dir>   — exit 1 when a line has to be generated again
"""
import re
import statistics
import sys
from pathlib import Path

import tvlib

PACE_TOLERANCE = 0.15  # ±15 % from the median seconds per character
SHORT = 40             # short titles pause more; left out of the pace median and the pace check
LINE = re.compile(r"model=(?P<model>\S+) backend=\S+ lang=(?P<lang>\S+) voice=(?P<voice>\S+) "
                  r"temperature=(?P<temp>\S+) style=(?P<style>.{30})… [\d.]+s audio, (?P<chars>\d+) chars, "
                  r"(?P<pace>[\d.]+)s/char.* tries=(?P<tries>\d+) audio_tokens=(?P<tokens>\d+) "
                  r"check_tokens=(?P<cin>\d+)/(?P<cout>\d+) voice_compared=(?P<vc>\S+) check=(?P<check>.*?), generated")


def report(video_dir):
    audio = Path(video_dir) / "audio"
    ids = sorted(p.stem for p in (audio / "txt").glob("*.txt"))
    rows, redo = [], []
    for i in ids:
        log = audio / f"{i}.log"
        m = LINE.search(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else None
        if not m:
            redo.append((i, "no result (not generated yet, or failed — see the log)"))
            continue
        rows.append({"id": i, **m.groupdict()})
    setups = {}
    for r in rows:
        setups.setdefault((r["model"], r["lang"], r["voice"], r["temp"], r["style"]), []).append(r["id"])
    if len(setups) > 1:
        common = max(setups, key=lambda s: len(setups[s]))
        for s, members in setups.items():
            if s != common:
                redo += [(i, f"different setup {s} — the voice would change between slides") for i in members]
    long = [float(r["pace"]) for r in rows if int(r["chars"]) >= SHORT]
    med = statistics.median(long) if long else 0
    for r in rows:
        if not r["check"].startswith("clean"):
            redo.append((r["id"], r["check"]))
        elif int(r["chars"]) >= SHORT and abs(float(r["pace"]) - med) > PACE_TOLERANCE * med:
            redo.append((r["id"], f"pace {float(r['pace']):.3f}s/char vs median {med:.3f}"))
    pr = tvlib.PRICES
    tts_tokens = sum(int(r["tokens"]) for r in rows)
    cin = sum(int(r["cin"]) for r in rows)
    cout = sum(int(r["cout"]) for r in rows)
    usd = tts_tokens * pr["tts_audio_out"] / 1e6 + cin * pr["check_in"] / 1e6 + cout * pr["check_out"] / 1e6
    ref = tvlib.video_config(video_dir).get("ref") or (ids[0] if ids else None)
    not_compared = [r["id"] for r in rows if r["vc"] != "True" and r["id"] != ref]
    print(f"{len(rows)}/{len(ids)} lines, setup {sorted(setups)}, median pace {med:.3f}s/char")
    print(f"cost of the lines as they are now: TTS {tts_tokens} audio tokens, check {cin}/{cout} tokens ≈ ${usd:.2f} "
          f"(retries that were overwritten are not counted; prices of {tvlib.PRICES_DATE})")
    if not_compared:
        print(f"voice not compared (safety filter or no ref): {' '.join(not_compared)}")
    for i, why in redo:
        print(f"REDO {i}: {why}")
    return redo


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(1 if report(sys.argv[1]) else 0)
