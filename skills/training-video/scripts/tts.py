#!/usr/bin/env python3
"""One narration line: Gemini TTS → check.py listens → generated again until clean → levelled → wav.

The voice, language, style and temperature come from the video (video.json next to audio/), so every line of a
video sounds the same. --voice/--lang override them only together with --probe (voice samples outside a video).

Usage: tts.py <in.txt> <out.wav> [--ref approved.wav] [--tries N] [--no-check]
       tts.py --probe --project <project> --lang bg --voice Charon <in.txt> <out.wav>
The last log line has the verdict and the audio tokens (cost); voices.py reads it.
"""
import argparse
import io
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import check
import tvlib

RATE = 24000
TEMPERATURE = 0.5   # default 1.0 improvises more: fillers, uneven intonation
TRIES_CLEAN = 3
LEVEL = -20         # LUFS of every line; the whole mix gets loudnorm -16 at the end
# „warm/friendly/conversational“ made the voice sound like a children's programme and invited fillers;
# words the style names, even negated („not a teacher“), pull the delivery towards them — so no negations.
STYLE = ("Native {name} ({locale}) speaker. Professional corporate training narrator addressing adult colleagues: "
         "calm, confident, neutral and businesslike, steady moderate pace, even intonation, natural {name} stress. "
         "Read the script exactly as written, word for word, with no filler sounds, hesitations or extra words.")


def style_for(lang):
    return STYLE.format(**lang)


def resample(data, src_args):
    return subprocess.run(["ffmpeg", "-v", "error", *src_args, "-i", "pipe:0", "-f", "s16le", "-ar", str(RATE),
                           "-ac", "1", "pipe:1"], input=data, capture_output=True, check=True).stdout


def to_pcm(data, mime):
    """24 kHz mono 16-bit samples from a wav or from raw L16 (rate in the mime type)."""
    if "wav" in mime or data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2):
                return w.readframes(w.getnframes())
        return resample(data, [])
    rate = re.search(r"rate=(\d+)", mime)
    if rate and int(rate.group(1)) != RATE:
        return resample(data, ["-f", "s16le", "-ar", rate.group(1), "-ac", "1"])
    return data


def level(pcm):
    """Same loudness for every line (LEVEL LUFS, linear gain, peaks at most -1 dBFS). Returns (pcm, gain dB)."""
    src = ["-f", "s16le", "-ar", str(RATE), "-ac", "1"]
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *src, "-i", "pipe:0", "-af", "ebur128=peak=sample",
                          "-f", "null", "-"], input=pcm, capture_output=True, check=True).stderr.decode()
    summary = err[err.rfind("Summary:"):]
    i, peak = (float(re.search(rf"{k}:\s+(-?[\d.]+|-inf)", summary).group(1)) for k in ("I", "Peak"))
    if i < -60:
        return pcm, 0.0
    gain = round(min(LEVEL - i, -1 - peak), 2)
    out = subprocess.run(["ffmpeg", "-v", "error", *src, "-i", "pipe:0", "-af", f"volume={gain}dB", *src, "pipe:1"],
                         input=pcm, capture_output=True, check=True).stdout
    return out, gain


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return len(pcm) / 2 / RATE


def main():
    p = argparse.ArgumentParser()
    p.add_argument("infile")
    p.add_argument("outfile")
    p.add_argument("--ref", help="approved first line of the video; check.py compares the voice with it")
    p.add_argument("--tries", type=int, default=TRIES_CLEAN)
    p.add_argument("--no-check", action="store_true", help="one generation, nobody listens (silent drafts only)")
    p.add_argument("--probe", action="store_true", help="voice sample outside a video: --lang/--voice allowed")
    p.add_argument("--lang")
    p.add_argument("--voice")
    p.add_argument("--project", help="with --probe: the project whose Gemini key pays (else TV_PROJECT)")
    a = p.parse_args()

    out = Path(a.outfile)
    video_dir = out.resolve().parent.parent
    if (a.lang or a.voice) and not a.probe:
        raise SystemExit("--lang/--voice change the voice of one line only: set them in video.json, or use --probe")
    if a.project:
        tvlib.use_project(a.project)
    cfg = tvlib.video_config(video_dir) if not a.probe else {}
    lang_code = a.lang or cfg.get("lang", "bg")
    lang = tvlib.language(lang_code)
    voice = a.voice or cfg.get("voice") or lang["voice"]
    style = style_for(lang)
    text = Path(a.infile).read_text(encoding="utf-8").strip()
    print(f"access: {tvlib.describe_access()}", file=sys.stderr)

    t = time.time()
    best, tokens, tries, check_in, check_out = None, 0, 0, 0, 0
    for tries in range(1, (1 if a.no_check else max(1, a.tries)) + 1):
        audio, mime, n = tvlib.speak(text, voice, style, TEMPERATURE)
        tokens += n
        pcm = to_pcm(audio, mime)
        if a.no_check:
            best = (pcm, None)
            break
        write_wav(out, pcm)
        v = check.check(text, out, lang, a.ref)
        check_in += v["tokens_in"]
        check_out += v["tokens_out"]
        print(f"try {tries}: {check.dumps(v)}", file=sys.stderr)
        if best is None or v["problems"] < best[1]["problems"]:
            best = (pcm, v)
        if v["ok"]:
            break
    pcm, gain = level(best[0])
    d = write_wav(out, pcm)
    v = best[1]
    verdict = "unchecked" if v is None else ("clean" if v["ok"] else
                                             f"NOT CLEAN fillers={v['fillers']} diffs={v['diffs']} cut={v['cut']} "
                                             f"same_voice={v['same_voice']}")
    print(f"{out}: model={tvlib.TTS_MODEL} backend={tvlib.backend()} lang={lang_code} voice={voice} "
          f"temperature={TEMPERATURE} style={style[:30]}… {d:.2f}s audio, {len(text)} chars, "
          f"{d / max(1, len(text)):.3f}s/char, gain={gain:+.1f}dB, tries={tries} audio_tokens={tokens} "
          f"check_tokens={check_in}/{check_out} voice_compared={v is not None and v['voice_compared']} "
          f"check={verdict}, generated in {time.time() - t:.1f}s")


if __name__ == "__main__":
    main()
