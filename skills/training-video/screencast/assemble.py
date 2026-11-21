#!/usr/bin/env python3
"""Builds a "by code" video from build/cards/, raw/<chapter>/ recordings and audio/, in the order of script.json.

Usage: assemble.py <video dir>
Writes final/<name>.mp4 (1920×1080, 30 fps, -16 LUFS) and timeline.json in the common format, so srt.py makes
the subtitles. A chapter with a title card and one line is the card alone (intro, end); every other chapter needs
its recording (record.cjs). Re-voicing without re-recording: copy the audio the footage was recorded with into
audio-recorded/ first — where a new line is longer, the last frame of its action is held.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tvlib  # noqa: E402

FPS = 30
SIZE = "1920:1080"
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1"]


def fade_in(d):
    """fade=in turns the first frame fully black, so every join showed a black frame; starting the fade one frame
    early leaves the first frame dim instead. The input must already be at FPS."""
    return f"setpts=PTS+1/{FPS}/TB,fade=in:st=0:d={d},setpts=PTS-STARTPTS"


def fade_out(end, d):
    return f"fade=out:st={end - d + 1 / FPS:.3f}:d={d}"


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(path)]))


class Video:
    def __init__(self, d):
        self.dir = Path(d).resolve()
        self.cfg = tvlib.video_config(self.dir)
        self.chapters = json.loads((self.dir / "script.json").read_text(encoding="utf-8"))["chapters"]
        self.work = self.dir / "build" / "assemble"
        self.work.mkdir(parents=True, exist_ok=True)
        self.old = self.dir / "audio-recorded"

    def wav(self, i):
        return self.dir / "audio" / f"{i}.wav"

    def adur(self, i):
        return dur(self.wav(i))

    def odur(self, i):
        """Length of the line the footage was recorded with (old voice), else the current one."""
        p = self.old / f"{i}.wav"
        return dur(p) if p.exists() else self.adur(i)


def has_card(ch):
    return ch.get("card") is not False


def card(v, ch, out, lead, tail):
    first = ch["beats"][0]["id"]
    length = lead + v.adur(first) + tail
    ms = int(lead * 1000)
    run(["-loop", "1", "-t", f"{length:.2f}", "-i", str(v.dir / "build" / "cards" / f"{ch['id']}.png"),
         "-i", str(v.wav(first)), "-filter_complex",
         f"[0:v]scale={SIZE},fps={FPS},{fade_in(0.4)},{fade_out(length, 0.4)}[v];"
         f"[1:a]adelay={ms}|{ms},apad,atrim=0:{length:.2f}[a]",
         "-map", "[v]", "-map", "[a]", *ENC, str(out)])
    return length, [(first, lead)]


def retimed(v, tl, bs, out):
    """Cuts the recording at line starts; holds the last frame of a line when its narration is longer than the
    recorded slot, so each line still starts with its action."""
    segs, offs, t = [], [], 0.0
    for k, b in enumerate(bs):
        s0 = b["t"] - (0.6 if k == 0 else 0.0)
        lead = b["t"] - s0
        if k + 1 < len(bs):
            e0 = bs[k + 1]["t"]
            need = lead + v.adur(b["id"]) + 0.9
        else:
            skipped = sum(c1 - c0 for c0, c1 in b.get("cuts", []))
            e0 = min(tl["end"] - 0.2, max(b["t"] + skipped + v.odur(b["id"]) + 2.2, b.get("done", 0) + 0.8))
            need = lead + v.adur(b["id"]) + 2.0
        # waits marked with h.skip() are cut out of the line's slot (the narration still starts with the line)
        cuts = sorted((max(s0, c0), min(e0, c1)) for c0, c1 in b.get("cuts", []) if c1 > s0 and c0 < e0)
        kept = sum(c1 - c0 for c0, c1 in cuts)
        ext = max(0.0, need - (e0 - s0 - kept))
        a = s0
        for c0, c1 in cuts:
            if c0 > a:
                segs.append((a, c0, 0.0))
            a = c1
        segs.append((a, e0, ext))
        offs.append((b["id"], t + lead))
        t += (e0 - s0 - kept) + ext
    n = len(segs)
    f = [f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n))]
    for i, (s0, e0, ext) in enumerate(segs):
        f.append(f"[s{i}]trim=start={s0:.3f}:end={e0:.3f},setpts=PTS-STARTPTS,scale={SIZE}:flags=lanczos,fps={FPS},"
                 f"tpad=stop_mode=clone:stop_duration={ext:.3f}[v{i}]")
    f.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,trim=end={t:.3f},"
             f"{fade_in(0.3)},{fade_out(t, 0.35)}[v]")
    inputs = []
    for k, (bid, off) in enumerate(offs):
        inputs += ["-i", str(v.wav(bid))]
        ms = int(off * 1000)
        f.append(f"[{k + 1}:a]adelay={ms}|{ms}[a{k}]")
    f.append("".join(f"[a{k}]" for k in range(len(offs))) + f"amix=inputs={len(offs)}:normalize=0,apad,atrim=0:{t:.2f}[a]")
    run(["-i", str(tl["video"]), *inputs, "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]", *ENC, str(out)])
    held = round(sum(x[2] for x in segs), 1)
    if held:
        print(f"  {out.name}: held frames {held}s (narration longer than the recorded action)")
    return t, offs


def concat_path(p):
    """A path for ffmpeg's concat list: forward slashes (C:\\… breaks it) and an escaped ' (a folder like „Ivan's“)."""
    return Path(p).resolve().as_posix().replace("'", "'\\''")


def concat(v, parts, out):
    lst = v.work / (out.stem + ".txt")
    lst.write_text("".join(f"file '{concat_path(p)}'\n" for p in parts), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])


def chapter(v, ch, idx):
    parts, beats, length = [], [], 0.0
    edge = idx in (0, len(v.chapters) - 1)
    if has_card(ch):
        p = v.work / f"{ch['id']}-card.mp4"
        length, beats = card(v, ch, p, lead=0.6, tail=1.8 if edge else 1.2)
        parts.append(p)
    tl_path = v.dir / "raw" / ch["id"] / "timeline.json"
    if tl_path.exists() and (len(ch["beats"]) > 1 or not has_card(ch)):
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
        on_card = {beats[0][0]} if beats else set()
        p = v.work / f"{ch['id']}-video.mp4"
        vlen, offs = retimed(v, tl, [b for b in tl["beats"] if b["id"] not in on_card], p)
        parts.append(p)
        beats += [(bid, length + o) for bid, o in offs]
        length += vlen
    out = v.work / f"{idx:02d}-{ch['id']}.mp4"
    concat(v, parts, out)
    return out, dur(out), beats


def check_recordings(v):
    """record.cjs writes timeline.json even when a chapter stops early, so every line must be in it."""
    problems = []
    for ch in v.chapters:
        if has_card(ch) and len(ch["beats"]) < 2:
            continue
        tl_path = v.dir / "raw" / ch["id"] / "timeline.json"
        if not tl_path.exists():
            problems.append(f"{ch['id']}: not recorded (node record.cjs <video> {ch['id']})")
            continue
        recorded = {b["id"] for b in json.loads(tl_path.read_text(encoding="utf-8"))["beats"]}
        first = 1 if has_card(ch) else 0
        missing = [b["id"] for b in ch["beats"][first:] if b["id"] not in recorded]
        if missing:
            problems.append(f"{ch['id']}: the recording stopped before {missing} — record it again")
    if not (v.dir / "build" / "cards").exists() and any(has_card(c) for c in v.chapters):
        problems.append("no title cards — node cards.cjs <video> first")
    if problems:
        raise SystemExit("\n".join(problems))


def main(d):
    v = Video(d)
    check_recordings(v)
    files, offset, timeline = [], 0.0, []
    for i, ch in enumerate(v.chapters):
        f, d_, beats = chapter(v, ch, i)
        timeline.append({"id": ch["id"], "start": round(offset, 3), "end": round(offset + d_, 3),
                         "beats": [{"id": b, "start": round(offset + t, 3), "dur": round(v.adur(b), 3)} for b, t in beats]})
        files.append(f)
        print(f"{offset:7.2f} {d_:6.2f}  {ch['id']} {ch.get('title', '')}")
        offset += d_
    joined = v.work / "joined.mp4"
    concat(v, files, joined)
    (v.dir / "final").mkdir(exist_ok=True)
    out = v.dir / "final" / f"{v.cfg['name']}.mp4"
    run(["-i", str(joined), "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
    (v.dir / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {out} — {offset / 60:.1f} min")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
