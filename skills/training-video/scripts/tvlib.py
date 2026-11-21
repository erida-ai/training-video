"""Shared ground for the training-video scripts: folders, Gemini access, the two REST backends, prices.

Gemini access, in this order:
  1. GEMINI_API_KEY in the environment (CI, Linux — it then serves every project), or the key of the video's project,
     saved by key.py in this computer's Keychain / Credential Manager → Gemini API (backend "api");
  2. Vertex AI with Google credentials (gcloud ADC), only with GOOGLE_CLOUD_PROJECT or TV_BACKEND=vertex.
Otherwise a script stops and says to run the key wizard (key.py setup <project>) — never another project's key.
A project is the folder Claude Code works in (a product repo, a folder of documents), marked by
.training-video/project.json {id, name}; a video points at it with video.json "project" (or TV_PROJECT).
Only the Vertex backend needs the google-auth package.
"""
import base64
import json
import os
import random
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import keystore

# Windows consoles and pipes default to a legacy code page: every Cyrillic print would fail.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
THEMES = PLUGIN / "themes"
# Persistent state (browser, caches). Not inside the plugin folder: that one is replaced on every update.
HOME = Path(os.environ.get("TV_HOME") or Path.home() / ".training-video")
PROJECT_FILE = Path(".training-video") / "project.json"
REGISTRY = HOME / "projects.json"     # project id → name, folder (no keys): for key.py list

TTS_MODEL = "gemini-3.8-flash-tts"
# Listens to every line. On 15.10.2026 the only Flash model that told close male voices apart;
# gemini-2.5-* retire on 20.10.2026.
CHECK_MODEL = os.environ.get("CHECK_MODEL", "gemini-3.8-flash")
VERTEX_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
VERTEX_BASE = "https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models"

# USD per 1M tokens, standard tier, until 31.12.2026 (both roughly double from 01.01.2027).
PRICES = {
    "tts_text_in": 0.50, "tts_audio_out": 9.00,     # gemini-3.8-flash-tts
    "check_in": 0.75, "check_out": 3.75,            # gemini-3.8-flash (audio in = other input; thinking counts as out)
}
TTS_TOKENS_PER_SECOND = 25
PRICES_DATE = "15.10.2026"

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
TRIES = 6
TIMEOUT = 180


class Blocked(Exception):
    """The request was refused by the safety filter (promptFeedback.blockReason)."""


def load_json(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def language(code):
    """languages/<code>.json — voice, style and check rules of one language."""
    data = load_json(SKILL / "languages" / f"{code}.json")
    if data is None:
        known = ", ".join(sorted(p.stem for p in (SKILL / "languages").glob("*.json")))
        raise SystemExit(f"no languages/{code}.json (known: {known}); copy en.json and adapt it")
    return data


def video_config(video_dir):
    """video.json of a video folder: name, lang, voice, subtitles, theme. Missing keys get defaults."""
    cfg = load_json(Path(video_dir) / "video.json", {}) or {}
    if cfg.get("project"):
        use_project(Path(video_dir) / cfg["project"])     # relative to the video folder, or absolute
    cfg.setdefault("lang", "bg")
    cfg.setdefault("subtitles", [cfg["lang"]])
    cfg.setdefault("theme", "neutral")
    cfg.setdefault("voice", language(cfg["lang"])["voice"])
    return cfg


# ---------- projects ----------

_project = {}


def read_project(folder):
    """{id, name, path} of the project in this folder, or None."""
    folder = Path(folder).resolve()
    data = load_json(folder / PROJECT_FILE)
    return {**data, "path": str(folder)} if data and data.get("id") else None


def use_project(folder):
    """The project whose key the Gemini calls use. Children (tts.py from narrate.py) inherit it via TV_PROJECT."""
    p = read_project(folder)
    if not p:
        raise SystemExit(f"{folder}: няма .training-video/project.json — пуснете key.py setup <папката на проекта>")
    _project.clear()
    _project.update(p)
    os.environ["TV_PROJECT"] = p["path"]
    return p


def project():
    if not _project and os.environ.get("TV_PROJECT"):
        use_project(os.environ["TV_PROJECT"])
    return _project or None


# ---------- access ----------

_keys = {}


def api_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    p = project()
    if not p:
        return None
    if p["id"] not in _keys:          # one lookup per process: the store is a subprocess call on macOS
        _keys[p["id"]] = keystore.get(p["id"])
    return _keys[p["id"]]


def no_key():
    p = project()
    if not p:
        return ("няма Gemini ключ: видеото не е свързано с проект (video.json \"project\") — "
                "пуснете key.py setup <папката на проекта>")
    return f"проект „{p['name']}“ няма Gemini ключ на този компютър — пуснете key.py setup {p['path']}"


def backend():
    forced = os.environ.get("TV_BACKEND")
    if forced in ("api", "vertex"):
        return forced
    if api_key():
        return "api"
    if VERTEX_PROJECT:
        return "vertex"
    raise SystemExit(no_key())


_vertex = {}


def vertex_token():
    """A Vertex access token from user ADC or a service account; the project from the credentials or GOOGLE_CLOUD_PROJECT."""
    if "creds" not in _vertex:
        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError:
            raise SystemExit("Vertex needs google-auth (pip install google-auth), or save a Gemini API key: key.py set")
        creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        _vertex.update(creds=creds, project=VERTEX_PROJECT or project, req=google.auth.transport.requests.Request())
        if not _vertex["project"]:
            raise SystemExit("set GOOGLE_CLOUD_PROJECT for Vertex")
    c = _vertex["creds"]
    if not c.valid:
        c.refresh(_vertex["req"])
    return c.token


def describe_access():
    b = backend()
    if b == "api":
        if os.environ.get("GEMINI_API_KEY"):
            return "Gemini API (GEMINI_API_KEY — the same key for every project)"
        return f"Gemini API (key of project „{project()['name']}“ from {keystore.name()})"
    vertex_token()
    who = getattr(_vertex["creds"], "service_account_email", None) or "user ADC"
    return f"Vertex AI, project {_vertex['project']}, {who}"


# ---------- REST ----------

def tls():
    """A TLS context that verifies: the system's CAs, else certifi, else macOS's bundle.
    Python from python.org has no CAs until "Install Certificates" is run — every request would fail."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats()["x509_ca"]:
        return ctx
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ctx


def post(url, body, headers):
    """POST JSON with retries on transient errors. Returns the parsed answer."""
    err = ""
    for i in range(TRIES):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=tls()) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            err = f"{e.code}: {e.read()[:300].decode(errors='replace')}"
            if e.code not in RETRY_STATUS:
                raise SystemExit(f"Gemini {err}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
        if i < TRIES - 1:
            wait = 3 * 2 ** i + random.random()
            print(f"retry {i + 1} after {wait:.0f}s: {err}", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"Gemini failed after {TRIES} tries: {err}")


def _model_url(model, method="generateContent"):
    if backend() == "api":
        return f"{API_BASE}/models/{model}:{method}", {"x-goog-api-key": api_key()}
    token = vertex_token()
    return (VERTEX_BASE.format(project=_vertex["project"]) + f"/{model}:{method}",
            {"Authorization": f"Bearer {token}"})


def speak(text, voice, style, temperature):
    """One TTS call. Returns (audio bytes, mime type, audio tokens). The style is metadata, never read aloud."""
    if backend() == "api":
        # gemini-3.8-flash-tts on the Gemini API: Interactions API; style as a speech_metadata annotation.
        body = {"model": TTS_MODEL,
                "input": [{"type": "user_input", "content": [{
                    "type": "text", "text": text,
                    "annotations": [{"type": "speech_metadata", "style": style}]}]}],
                "response_format": {"type": "audio", "mime_type": "audio/wav"},
                "generation_config": {"speech_config": [{"voice": voice}], "temperature": temperature}}
        answer = post(f"{API_BASE}/interactions", body, {"x-goog-api-key": api_key()})
        audio = next((c for s in answer.get("steps", []) for c in s.get("content", []) if c.get("data")), None)
        if audio is None:
            raise SystemExit(f"no audio in the answer: {json.dumps(answer)[:300]}")
        usage = answer.get("usage", {}) or answer.get("usageMetadata", {})
        # Interactions API: usage.total_output_tokens (all audio for a TTS model)
        tokens = usage.get("total_output_tokens") or usage.get("candidatesTokenCount") or 0
        return base64.b64decode(audio["data"]), audio.get("mime_type", "audio/wav"), tokens
    url, headers = _model_url(TTS_MODEL)
    body = {"contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": style}}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "temperature": temperature,
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    answer = post(url, body, headers)
    inline = answer["candidates"][0]["content"]["parts"][0]["inlineData"]
    if not inline.get("data"):
        raise SystemExit("no audio in the answer")
    return (base64.b64decode(inline["data"]), str(inline.get("mimeType", "")),
            answer.get("usageMetadata", {}).get("candidatesTokenCount", 0))


def ask_json(parts, schema, model=CHECK_MODEL):
    """generateContent with a JSON schema. Returns (dict, tokens_in, tokens_out); raises Blocked on a safety block."""
    url, headers = _model_url(model)
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": schema}}
    for i in range(3):
        answer = post(url, body, headers)
        if "candidates" not in answer:
            if answer.get("promptFeedback", {}).get("blockReason"):
                raise Blocked(str(answer["promptFeedback"]))
            continue
        try:
            v = json.loads(answer["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, ValueError):
            continue
        u = answer.get("usageMetadata", {})
        return v, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    raise SystemExit(f"{model}: no usable answer after 3 tries")


def audio_part(path):
    return {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(Path(path).read_bytes()).decode()}}
