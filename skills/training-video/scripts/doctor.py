#!/usr/bin/env python3
"""Checks this computer before a video: tools, the Python command, the project's Gemini key, the state folder.
Prints one line per check (OK / ЛИПСВА + how to fix, for this operating system) in Bulgarian, for the agent to relay
or fix with the person's permission.

Usage: doctor.py [<project>] [--json]     — exit 1 when something required is missing
"""
import json
import os
import shutil
import subprocess
import sys

import keystore
import tvlib

# how to install a tool on this system: macOS Homebrew, Windows winget, Linux apt
PACKAGES = {
    "darwin": {"python": "python", "ffmpeg": "ffmpeg", "node": "node", "poppler": "poppler"},
    "win32": {"python": "Python.Python.3.12", "ffmpeg": "Gyan.FFmpeg", "node": "OpenJS.NodeJS.LTS",
              "poppler": "oschwald.Poppler"},
    "linux": {"python": "python3", "ffmpeg": "ffmpeg", "node": "nodejs", "poppler": "poppler-utils"},
}


def install(tool):
    pkg = PACKAGES.get(sys.platform, PACKAGES["linux"])[tool]
    if sys.platform == "darwin":
        cmd = f"brew install {pkg}"
        return cmd if shutil.which("brew") else f"инсталирайте Homebrew (brew.sh), после {cmd}"
    if sys.platform == "win32":
        return (f"winget install -e --id {pkg} (после рестартирайте Claude Code, за да види новия PATH)")
    return f"sudo apt-get install -y {pkg}"


def python_command():
    """The command that starts Python 3 here. On Windows "python3" is usually the Microsoft Store stub."""
    for cmd in (["python3"], ["python"], ["py", "-3"]):
        exe = shutil.which(cmd[0])
        if exe and "WindowsApps" not in exe:
            return " ".join(cmd)
    return None


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def checks(project_dir=None):
    out = []

    def add(name, ok, detail, fix="", required=True):
        out.append({"name": name, "ok": ok, "detail": detail, "fix": fix, "required": required})

    add("Python 3.9+", sys.version_info >= (3, 9), sys.version.split()[0], install("python"))
    py = python_command()
    add("Python команда", bool(py), py or "няма в PATH", install("python"))
    ok, txt = run(["ffmpeg", "-hide_banner", "-buildconf"])
    add("ffmpeg", ok and "libx264" in txt, "с libx264" if ok and "libx264" in txt else "няма или е без libx264",
        install("ffmpeg"))
    add("ffprobe", bool(shutil.which("ffprobe")), shutil.which("ffprobe") or "няма", install("ffmpeg"))
    ok, txt = run(["node", "--version"])
    major = int(txt.lstrip("v").split(".")[0]) if ok and txt.startswith("v") else 0
    add("Node.js 18+", major >= 18, txt if ok else "няма", install("node"))
    ok, txt = run(["node", "-e", "const p=require(require.resolve('playwright',{paths:[process.argv[1],process.argv[2]]}));"
                         "console.log(require('fs').existsSync(p.chromium.executablePath())?'chromium ok':'no chromium')",
                   str(tvlib.PLUGIN), str(tvlib.HOME)])
    add("Playwright (рендер)", ok, txt.splitlines()[0][:80] if ok else "няма", f"npm ci в {tvlib.PLUGIN}")
    if ok:
        add("Chromium за рендера", "chromium ok" in txt, txt.strip(), "npx playwright install chromium")
    add("poppler (PDF)", bool(shutil.which("pdftotext")), "има" if shutil.which("pdftotext") else "няма",
        install("poppler"), required=False)
    try:
        tvlib.HOME.mkdir(parents=True, exist_ok=True)
        add("Папка за състояние", True, str(tvlib.HOME))
    except OSError as e:
        add("Папка за състояние", False, str(e), "задайте TV_HOME към папка с права за запис")
    wizard = f"key.py setup {project_dir or '<папката на проекта>'}" if keystore.available() else \
        "задайте GEMINI_API_KEY в средата"
    if os.environ.get("GEMINI_API_KEY"):
        add("Gemini ключ", True, "GEMINI_API_KEY от средата — важи за всички проекти, вместо ключа на проекта")
    elif not project_dir:
        add("Gemini ключ", False, "не е проверен: кажете папката на проекта (doctor.py <проект>)", wizard)
    else:
        p = tvlib.read_project(project_dir)
        if not p:
            add("Gemini ключ", False, "папката още не е проект на training-video", wizard)
        elif keystore.get(p["id"]):
            add("Gemini ключ", True, f"проект „{p['name']}“, в {keystore.name()} (key.py check го проверява в Gemini)")
        else:
            add("Gemini ключ", False, f"проект „{p['name']}“ няма ключ на този компютър", wizard)
    return out


def main():
    args = [x for x in sys.argv[1:] if x != "--json"]
    res = checks(args[0] if args else None)
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for c in res:
            mark = "OK     " if c["ok"] else ("ЛИПСВА " if c["required"] else "по избор")
            print(f"{mark} {c['name']}: {c['detail']}" + ("" if c["ok"] else f"  → {c['fix']}"))
    sys.exit(0 if all(c["ok"] or not c["required"] for c in res) else 1)


if __name__ == "__main__":
    main()
