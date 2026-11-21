#!/usr/bin/env python3
"""Listens to a generated line and compares it with the script: fillers, missing or changed words, a cut end,
and — with a reference line — whether the voice still sounds the same.

Usage: check.py <in.txt> <in.wav> [ref.wav] [--lang bg] [--project <project>]   — JSON verdict, exit 1 when the line is not clean
Used by tts.py after every generation; the model is tvlib.CHECK_MODEL.
"""
import argparse
import json
import sys
from pathlib import Path

import tvlib

PROMPT = """You are checking a {name} text-to-speech recording against its script.
Script:
<<<{text}>>>

Listen to the audio carefully and report, without cleaning anything up:
- fillers: every hesitation or filler sound the speaker adds that is not in the script, written as heard
  (for {name}: {fillers}; a false start or a repeated word). Breaths are not fillers.
- diffs: script words that are missing, replaced or clearly mispronounced, and words that were added,
  as "expected -> heard". NOT differences: {not_differences}, punctuation and capitalisation.
- cut: true when the recording stops before the last word of the script is finished.
- delivery: three to six English words on the tone (e.g. "calm neutral corporate narrator").
- same_voice: {ref_rule}
ok is true only when fillers and diffs are empty, cut is false and same_voice is true."""
# Worded as a check of one synthetic preset: "same narrator / same speaker" got requests blocked
# (promptFeedback.blockReason SAFETY, 15.10.2026), probably read as identifying a person by voice.
REF_RULE = ("both recordings are synthetic text-to-speech output of the same preset voice, made for one training video; "
            "the FIRST is the approved reference line, the SECOND is the line to check. true when the second keeps the "
            "same audio character as the reference: pitch, timbre, pace, energy and tone. false when it drifts noticeably.")
NO_REF_RULE = "always true (there is no reference)."
SCHEMA = {"type": "OBJECT", "properties": {
    "ok": {"type": "BOOLEAN"},
    "fillers": {"type": "ARRAY", "items": {"type": "STRING"}},
    "diffs": {"type": "ARRAY", "items": {"type": "STRING"}},
    "cut": {"type": "BOOLEAN"},
    "delivery": {"type": "STRING"},
    "same_voice": {"type": "BOOLEAN"}},
    "required": ["ok", "fillers", "diffs", "cut", "delivery", "same_voice"]}


def check(text, wav, lang, ref=None):
    """Returns {ok, fillers, diffs, cut, delivery, same_voice, voice_compared, problems, tokens_in, tokens_out}.
    A comparison blocked by the safety filter is asked again without ref: the words are still checked,
    voice_compared is false (the voice is then kept the same only by identical settings)."""
    fields = {**lang, "text": text, "ref_rule": REF_RULE if ref else NO_REF_RULE}
    prompt = PROMPT
    for k, val in fields.items():
        prompt = prompt.replace("{" + k + "}", str(val))
    parts = ([tvlib.audio_part(ref)] if ref else []) + [tvlib.audio_part(wav), {"text": prompt}]
    try:
        v, tin, tout = tvlib.ask_json(parts, SCHEMA)
    except tvlib.Blocked as e:
        if not ref:
            raise SystemExit(f"check blocked even without a reference: {e}")
        print(f"check blocked, words only: {e}", file=sys.stderr)
        v = check(text, wav, lang)
        v["voice_compared"] = False
        return v
    v.update(tokens_in=tin, tokens_out=tout, voice_compared=bool(ref))
    v["problems"] = len(v["fillers"]) + len(v["diffs"]) + (3 if v["cut"] else 0) + (0 if v["same_voice"] else 2)
    v["ok"] = v["problems"] == 0
    return v


def dumps(v):
    return json.dumps(v, ensure_ascii=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("txt")
    p.add_argument("wav")
    p.add_argument("ref", nargs="?")
    p.add_argument("--lang", default="bg")
    p.add_argument("--project", help="the project whose Gemini key pays (else TV_PROJECT)")
    a = p.parse_args()
    if a.project:
        tvlib.use_project(a.project)
    v = check(Path(a.txt).read_text(encoding="utf-8").strip(), a.wav, tvlib.language(a.lang), a.ref)
    print(dumps(v))
    sys.exit(0 if v["ok"] else 1)


if __name__ == "__main__":
    main()
