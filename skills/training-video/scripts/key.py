#!/usr/bin/env python3
"""The Gemini key of a project — the wizard the skill runs the first time it works in a project.

A project is the folder Claude Code works in (a product repo, a folder of documents). It is marked by
<project>/.training-video/project.json {id, name} — no secrets, fine in git, so the whole team shares the id.
The key itself stays on this computer only: Keychain (macOS) / Credential Manager (Windows), under the project id.
It never passes through the chat, the terminal output or a file.

Usage: key.py check <project>          — exit 0 when the project has a key Gemini accepts; otherwise says what is
                                         missing (exit 2: not a project yet, 3: no key, 4: key rejected)
       key.py setup <project> [--name ИМЕ] [--use-legacy] [--replace]
                                       — makes the project marker if missing, opens aistudio.google.com/apikey and a
                                         hidden-input window, checks the key with Gemini and saves it
                                         --use-legacy: take the single key saved before keys were per project
       key.py list                     — projects with a key on this computer (never the keys)
       key.py delete <project>
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path

import keystore
import tvlib

KEY_PAGE = "https://aistudio.google.com/apikey"
TITLE = "Обучително видео"


def prompt_text(name):
    return (f"Поставете Gemini API ключа за проект „{name}“ (от aistudio.google.com → Get API key).\n"
            f"Той се записва само в {keystore.name()} на този компютър.")


def ask_mac(name):
    q = prompt_text(name).replace("\\", "\\\\").replace('"', '\\"')
    dialog = (f'display dialog "{q}" default answer "" with hidden answer with title "{TITLE}" '
              'buttons {"Отказ", "Запиши"} default button "Запиши" cancel button "Отказ"')
    r = subprocess.run(["osascript", "-e", dialog, "-e", "text returned of result"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def ask_windows(name):
    q = prompt_text(name).replace("'", "''")
    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$f = New-Object Windows.Forms.Form
$f.Text = '{TITLE}'; $f.ClientSize = New-Object Drawing.Size(520, 150); $f.StartPosition = 'CenterScreen'
$f.TopMost = $true; $f.FormBorderStyle = 'FixedDialog'; $f.MaximizeBox = $false; $f.MinimizeBox = $false
$l = New-Object Windows.Forms.Label; $l.Text = '{q}'; $l.SetBounds(12, 12, 496, 48)
$t = New-Object Windows.Forms.TextBox; $t.UseSystemPasswordChar = $true; $t.SetBounds(12, 68, 496, 24)
$ok = New-Object Windows.Forms.Button; $ok.Text = 'Запиши'; $ok.DialogResult = 'OK'; $ok.SetBounds(332, 108, 85, 28)
$no = New-Object Windows.Forms.Button; $no.Text = 'Отказ'; $no.DialogResult = 'Cancel'; $no.SetBounds(423, 108, 85, 28)
$f.Controls.AddRange(@($l, $t, $ok, $no)); $f.AcceptButton = $ok; $f.CancelButton = $no
$f.Add_Shown({{ $f.Activate(); $t.Focus() }})
if ($f.ShowDialog() -eq 'OK') {{ [Console]::Out.Write($t.Text) }} else {{ exit 1 }}
"""
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    # Windows PowerShell 5.1 is on every Windows 10/11 and runs WinForms; -STA is required for the dialog
    r = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                       capture_output=True)
    return r.stdout.decode("utf-8", "ignore").strip() if r.returncode == 0 else None


def ask_key(name):
    if sys.platform == "darwin":
        key = ask_mac(name)
    elif sys.platform == "win32":
        key = ask_windows(name)
    else:
        raise SystemExit("тук няма прозорец и хранилище за ключове: задайте GEMINI_API_KEY в средата")
    if key is None:
        raise SystemExit("отказано — нищо не е записано")
    if not key:
        raise SystemExit("празен ключ — нищо не е записано")
    return key


def works(key):
    # a paste can bring Cyrillic, smart quotes or spaces: a header must be plain ASCII
    if not key.isascii() or not key.isprintable() or " " in key:
        return False, "ключът съдържа непозволени знаци (интервал, кирилица, кавички?) — копирайте го отново"
    req =urllib.request.Request(f"{tvlib.API_BASE}/models/{tvlib.CHECK_MODEL}", headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30, context=tvlib.tls()):
            return True, "ok"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, str(e.reason)


def registry():
    return tvlib.load_json(tvlib.REGISTRY, {}) or {}


def register(p):
    reg = registry()
    reg[p["id"]] = {"name": p["name"], "path": p["path"]}
    tvlib.HOME.mkdir(parents=True, exist_ok=True)
    tvlib.REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def unregister(pid):
    reg = registry()
    if reg.pop(pid, None) is not None:
        tvlib.REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def make_project(folder, name):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise SystemExit(f"{folder}: няма такава папка")
    f = folder / tvlib.PROJECT_FILE
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps({"id": str(uuid.uuid4()), "name": name or folder.name}, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8")
    print(f"създаден {f} (без тайни; може да влезе в git, за да има проектът един id за целия екип)")
    return tvlib.read_project(folder)


def env_note():
    if os.environ.get("GEMINI_API_KEY"):
        print("внимание: GEMINI_API_KEY е зададен в средата — той се ползва вместо ключа на проекта, за всички проекти")


def check(folder):
    p = tvlib.read_project(folder)
    if not p:
        print(f"НЯМА ПРОЕКТ: {Path(folder).resolve()} още не е проект (няма .training-video/project.json)")
        return 2
    key = keystore.get(p["id"])
    if not key:
        print(f"НЯМА КЛЮЧ: проект „{p['name']}“ няма Gemini ключ на този компютър")
        if keystore.legacy():
            print("на компютъра има стар общ ключ — може да се ползва за проекта: key.py setup <проект> --use-legacy")
        env_note()
        return 3
    ok, why = works(key)
    if not ok:
        print(f"ОТХВЪРЛЕН: Gemini не приема ключа на проект „{p['name']}“ ({why}) — key.py setup <проект> --replace")
        return 4
    print(f"OK: проект „{p['name']}“, ключът е в {keystore.name()} и Gemini го приема")
    env_note()
    return 0


def setup(folder, name=None, use_legacy=False, replace=False):
    if not keystore.available():
        raise SystemExit("тук няма хранилище за ключове: задайте GEMINI_API_KEY в средата")
    p = tvlib.read_project(folder) or make_project(folder, name)
    old = keystore.get(p["id"])
    if old and not replace:
        ok, why = works(old)
        if ok:
            register(p)
            print(f"OK: проект „{p['name']}“ вече има ключ и Gemini го приема — нищо не е променено")
            return
        print(f"ключът на проекта не работи ({why}) — въведете нов")
    if use_legacy:
        key = keystore.legacy()
        if not key:
            raise SystemExit("на този компютър няма стар общ ключ")
    else:
        print(f"Отварям {KEY_PAGE}: създайте ключ (Create API key) в Google акаунта или Google Cloud проекта, "
              "от който ще се плаща гласът за този проект, и го копирайте. После ще се появи прозорец за поставяне.")
        webbrowser.open(KEY_PAGE)
        key = ask_key(p["name"])
    ok, why = works(key)
    if not ok:
        raise SystemExit(f"Gemini не прие ключа ({why}) — нищо не е записано")
    keystore.put(p["id"], key)
    register(p)
    print(f"OK: ключът е записан за проект „{p['name']}“ в {keystore.name()} и Gemini го приема")
    env_note()


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("cmd", choices=["check", "setup", "list", "delete"])
    ap.add_argument("project", nargs="?")
    ap.add_argument("--name")
    ap.add_argument("--use-legacy", action="store_true")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    if a.cmd != "list" and not a.project:
        raise SystemExit("кажете папката на проекта: key.py " + a.cmd + " <папка>")
    if a.cmd == "check":
        sys.exit(check(a.project))
    if a.cmd == "setup":
        setup(a.project, a.name, a.use_legacy, a.replace)
    elif a.cmd == "list":
        reg = registry()
        rows = [(pid, r) for pid, r in reg.items() if keystore.get(pid)]
        for pid, r in rows:
            print(f"{r['name']}  {r['path']}  ({pid})")
        if not rows:
            print("няма проекти с ключ на този компютър")
        if keystore.legacy():
            print("+ стар общ ключ (отпреди ключовете да са по проекти)")
    elif a.cmd == "delete":
        p = tvlib.read_project(a.project)
        if not p:
            raise SystemExit(f"{a.project}: не е проект")
        keystore.delete(p["id"])
        unregister(p["id"])
        print(f"ключът на проект „{p['name']}“ е изтрит от този компютър")


if __name__ == "__main__":
    main()
