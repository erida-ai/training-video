#!/usr/bin/env python3
"""Cost estimate of voicing a video, before anything is generated — the table the person approves.

Usage: cost.py <video dir>        (reads audio/txt/*.txt and video.json)
Prints a Markdown table in Bulgarian: typical run (1.3 generations per line) and worst case (3 per line).
"""
import sys
from pathlib import Path

import tvlib

TYPICAL_TRIES = 1.3
MAX_TRIES = 3
STYLE_TOKENS = 60          # the style travels with every TTS request
CHECK_IN_TEXT = 650        # check prompt + script, tokens
CHECK_IN_PER_SECOND = 32   # audio input of the check model; the reference line is sent with every check
CHECK_OUT = 450            # verdict + thinking, measured 280–880 on 15.10.2026


def estimate(video_dir):
    video = Path(video_dir)
    cfg = tvlib.video_config(video)
    lang = tvlib.language(cfg["lang"])
    texts = [p.read_text(encoding="utf-8").strip() for p in sorted((video / "audio" / "txt").glob("*.txt"))]
    if not texts:
        raise SystemExit("no lines in audio/txt")
    chars = sum(len(t) for t in texts)
    seconds = chars * lang["pace"]
    ref_seconds = len(texts[0]) * lang["pace"]
    pr = tvlib.PRICES

    def run(tries):
        calls = len(texts) * tries
        tts_audio = seconds * tries * tvlib.TTS_TOKENS_PER_SECOND
        tts_text = (chars / 3.5 + STYLE_TOKENS * len(texts)) * tries
        check_in = calls * CHECK_IN_TEXT + (seconds + ref_seconds * len(texts)) * tries * CHECK_IN_PER_SECOND
        check_out = calls * CHECK_OUT
        return {"tts": tts_audio * pr["tts_audio_out"] / 1e6 + tts_text * pr["tts_text_in"] / 1e6,
                "check": check_in * pr["check_in"] / 1e6 + check_out * pr["check_out"] / 1e6,
                "audio_tokens": tts_audio, "calls": calls}

    t, w = run(TYPICAL_TRIES), run(MAX_TRIES)
    rows = [("Глас (TTS)", f"около {t['audio_tokens']:,.0f} аудио токена", f"${t['tts']:.2f}", f"${w['tts']:.2f}"),
            ("Проверка на всяка реплика", f"{t['calls']:.0f} проверки", f"${t['check']:.2f}", f"${w['check']:.2f}"),
            ("Картина и монтаж", "на този компютър", "$0", "$0"),
            ("**Общо**", "", f"**${t['tts'] + t['check']:.2f}**", f"**${w['tts'] + w['check']:.2f}**")]
    out = [f"Видео: {len(texts)} реплики, около {seconds / 60:.1f} мин. глас ({lang['native_name']}, глас {cfg['voice']}).",
           "", "| Част | Обем | Обикновено | Най-много |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    out += ["", f"Цени на Google към {tvlib.PRICES_DATE}; от 01.01.2027 около двойно. "
                f"„Най-много“ е, ако всяка реплика се генерира {MAX_TRIES} пъти."]
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(estimate(sys.argv[1]))
