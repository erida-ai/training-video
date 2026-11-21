#!/usr/bin/env python3
"""Materials → text, images and page views the agent can read, under <video>/sources/extracted/<file>/.

  PDF   text.txt (pdftotext -layout), images/ (embedded pictures, pdfimages), pages/ (each page at 80 dpi, pdftoppm)
  DOCX  text.txt (textutil on macOS, else the document XML) + images/ (word/media)
  PPTX  text.txt (text of every slide, in order) + images/ (ppt/media)
  images, .txt, .md — copied as they are
PDF needs poppler (doctor.py says how to install it here); without it the agent can still read the PDF itself, page by page.

Usage: extract.py <video dir> [file …]     (default: every file in <video>/sources/ except extracted/)
"""
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MIN_SIDE = 200  # smaller embedded pictures are icons and bullets


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def image_size(f):
    """(width, height) of a PNG, GIF or JPEG from its header, else None — the same on every system."""
    try:
        with open(f, "rb") as fh:
            head = fh.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", head[6:10])
            if head[:2] == b"\xff\xd8":
                fh.seek(2)
                while True:
                    marker = fh.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                        continue
                    seg = struct.unpack(">H", fh.read(2))[0]
                    if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                        h, w = struct.unpack(">xHH", fh.read(5))
                        return w, h
                    fh.seek(seg - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def keep_large(folder):
    """Drops pictures smaller than MIN_SIDE on both sides; formats whose size is not read are kept."""
    for f in list(folder.glob("*")):
        size = image_size(f)
        if size and size[0] < MIN_SIDE and size[1] < MIN_SIDE:
            f.unlink()


def media(zip_path, prefix, out):
    imgs = out / "images"
    imgs.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.startswith(prefix) and Path(n).suffix.lower() in IMAGE | {".emf", ".wmf", ".tif", ".tiff"}:
                (imgs / Path(n).name).write_bytes(z.read(n))
    keep_large(imgs)


def pdf(src, out):
    if not shutil.which("pdftotext"):
        return "poppler is missing (doctor.py says how to install it) — read the PDF directly"
    run(["pdftotext", "-layout", str(src), str(out / "text.txt")])
    (out / "images").mkdir(exist_ok=True)
    run(["pdfimages", "-png", str(src), str(out / "images" / "img")])
    keep_large(out / "images")
    (out / "pages").mkdir(exist_ok=True)
    run(["pdftoppm", "-r", "80", "-png", str(src), str(out / "pages" / "page")])
    return None


def pptx(src, out):
    with zipfile.ZipFile(src) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        parts = []
        for i, n in enumerate(slides, 1):
            texts = re.findall(r"<a:t>([^<]*)</a:t>", z.read(n).decode("utf-8"))
            parts.append(f"--- слайд {i} ---\n" + "\n".join(t for t in texts if t.strip()))
    (out / "text.txt").write_text("\n\n".join(parts), encoding="utf-8")
    media(src, "ppt/media/", out)


def docx(src, out):
    if shutil.which("textutil"):
        run(["textutil", "-convert", "txt", "-output", str(out / "text.txt"), str(src)])
    else:
        with zipfile.ZipFile(src) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        paras = [re.sub(r"<[^>]+>", "", p) for p in re.split(r"</w:p>", xml)]
        (out / "text.txt").write_text("\n".join(p for p in paras if p.strip()), encoding="utf-8")
    media(src, "word/media/", out)


def extract(video, files):
    root = video / "sources" / "extracted"
    for src in files:
        out = root / src.stem
        out.mkdir(parents=True, exist_ok=True)
        ext = src.suffix.lower()
        note = None
        if ext == ".pdf":
            note = pdf(src, out)
        elif ext == ".pptx":
            pptx(src, out)
        elif ext == ".docx":
            docx(src, out)
        elif ext in IMAGE or ext in {".txt", ".md"}:
            shutil.copy2(src, out / src.name)
        else:
            note = f"unknown type {ext} — read it directly or convert it"
        made = sorted(str(p.relative_to(video)) for p in out.rglob("*") if p.is_file())
        print(f"{src.name}: {len(made)} files in {out.relative_to(video)}" + (f" — {note}" if note else ""))
        pages = [m for m in made if "/pages/" in m]
        imgs = [m for m in made if "/images/" in m]
        if (out / "text.txt").exists():
            print(f"  text: {(out / 'text.txt').stat().st_size // 1024} KB")
        if pages or imgs:
            print(f"  pages: {len(pages)}, pictures: {len(imgs)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    v = Path(sys.argv[1]).resolve()
    given = [Path(f).resolve() for f in sys.argv[2:]]
    found = [f for f in (v / "sources").glob("*") if f.is_file() and not f.name.startswith(".")]
    extract(v, given or found)
