#!/usr/bin/env python3
"""Smoke test of the plugin on this computer: the whole path without Gemini and without cost.

  doctor.py → "by materials": two catalog slides, placeholder silence, stills, render, subtitles
            → "by code": a local page, recording as two roles (h.skip, continues), cards, assemble, subtitles
The videos are made in a temporary folder whose name has Cyrillic, a space and an apostrophe — the paths that break
first on Windows. Prints OK/FAIL per step and where the videos are.

Usage: <python> -B tests/smoke.py [--keep]     (from the plugin folder or anywhere)
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SKILL = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixture"
PY = [sys.executable, "-B"]
NODE = shutil.which("node") or "node"
results = []


def step(name, cmd, env=None, timeout=600):
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env={**os.environ, "PYTHONUTF8": "1", **(env or {})})
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as e:
        out, ok = str(e), False
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name} ({time.time() - t:.0f}s)")
    if not ok:
        print("     " + "\n     ".join(out.splitlines()[-12:]))
    return ok, out


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""))


def duration(f):
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", str(f)]))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0.0


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def materials(root):
    v = root / "по материали"
    (v / "slides").mkdir(parents=True)
    cat = SKILL / "deck" / "catalog"
    script = json.loads((cat / "script.json").read_text(encoding="utf-8"))
    script["chapters"] = script["chapters"][:2]
    (v / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in script["chapters"]:
        shutil.copy(cat / "slides" / f"{ch['id']}.html", v / "slides")
    (v / "video.json").write_text(json.dumps({"name": "смоук-материали", "lang": "bg", "theme": "neutral",
                                              "subtitles": ["bg"]}, ensure_ascii=False), encoding="utf-8")
    render = [NODE, str(SKILL / "deck" / "render.cjs"), str(v)]
    step("материали: lines.py", PY + [str(SKILL / "scripts" / "lines.py"), str(v)])
    step("материали: тишина вместо глас", render + ["silence"])
    ok, out = step("материали: кадри (stills)", render + ["stills", script["chapters"][1]["id"]])
    if ok:
        check("материали: без OVERFLOW", "OVERFLOW" not in out)
    step("материали: рендер", render + ["all"])
    step("материали: субтитри", PY + [str(SKILL / "scripts" / "srt.py"), str(v), "смоук-материали"])
    f = v / "final" / "смоук-материали.mp4"
    check("материали: видео", duration(f) > 5, f"{duration(f):.1f} s")
    check("материали: .srt", (v / "final" / "смоук-материали.bg.srt").exists())


def code(root):
    v = root / "по код"
    v.mkdir()
    for f in ("script.json", "chapters.cjs"):
        shutil.copy(FIX / "code" / f, v)
    port = free_port()
    (v / "video.json").write_text(json.dumps({
        "name": "смоук-код", "lang": "bg", "theme": "neutral", "mode": "code", "subtitles": ["bg"],
        "product": str(FIX / "product"), "role": "a", "app": {"SMOKE_PORT": str(port)}}, ensure_ascii=False),
        encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                               "--directory", str(FIX / "app")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        sc = SKILL / "screencast"
        step("код: тишина вместо глас", [NODE, str(SKILL / "deck" / "render.cjs"), str(v), "silence"])
        for ch in ("c1", "c2"):
            step(f"код: запис {ch}", [NODE, str(sc / "record.cjs"), str(v), ch])
        tl = json.loads((v / "raw" / "c1" / "timeline.json").read_text(encoding="utf-8")) \
            if (v / "raw" / "c1" / "timeline.json").exists() else {"beats": []}
        cut = sum(b - a for x in tl["beats"] for a, b in x.get("cuts", []))
        check("код: h.skip изряза чакането", cut > 3, f"{cut:.1f} s")
        step("код: карти", [NODE, str(sc / "cards.cjs"), str(v)])
        step("код: монтаж", PY + [str(sc / "assemble.py"), str(v)])
        step("код: субтитри", PY + [str(SKILL / "scripts" / "srt.py"), str(v), "смоук-код"])
        f = v / "final" / "смоук-код.mp4"
        check("код: видео", duration(f) > 10, f"{duration(f):.1f} s")
    finally:
        server.terminate()


def main():
    keep = "--keep" in sys.argv
    root = Path(tempfile.mkdtemp(prefix="tv-smoke-")) / "Обучение тест 'смоук'"
    root.mkdir()
    print(f"папка: {root}")
    # information only: a missing Gemini key is expected here, the smoke test never calls Gemini
    r = subprocess.run(PY + [str(SKILL / "scripts" / "doctor.py")], capture_output=True)
    print("doctor.py:\n     " + "\n     ".join((r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()))
    materials(root)
    code(root)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} OK" + (f"; FAIL: {', '.join(failed)}" if failed else ""))
    if keep or failed:
        print(f"видеата и логовете: {root}")
    else:
        shutil.rmtree(root.parent, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
