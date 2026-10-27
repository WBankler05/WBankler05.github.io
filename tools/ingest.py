"""Bring files into the site safely. Used by the editor; also runnable by hand:

    .venv\\Scripts\\python tools\\ingest.py resume  "C:\\path\\to\\Resume.pdf"
    .venv\\Scripts\\python tools\\ingest.py image   electric-vehicle "C:\\path\\photo.jpg"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from privacy import clean_image, redact_resume  # noqa: E402

RESUME_PATH = ROOT / "media" / "resume" / "William-Bankler-Resume.pdf"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def ingest_resume(data: bytes) -> list[str]:
    site = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    contact = site.get("contact", {})
    out, report = redact_resume(data, linkedin_url=contact.get("linkedin", ""), email=contact.get("email", ""))
    RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESUME_PATH.write_bytes(out)
    return report


def ingest_image(folder: str, filename: str, data: bytes) -> str:
    """Save a cleaned image under media/<folder>/ and return its site-relative path."""
    if folder != "profile" and not SLUG_RE.match(folder):
        raise ValueError(f"bad folder name: {folder!r}")
    target_dir = ROOT / "media" / ("profile" if folder == "profile" else f"projects/{folder}")
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(filename).stem)
    target = target_dir / f"{stem}.jpg"
    n = 2
    while target.exists():
        target = target_dir / f"{stem}-{n}.jpg"
        n += 1
    target.write_bytes(clean_image(data))
    return target.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    kind = sys.argv[1]
    if kind == "resume":
        for line in ingest_resume(Path(sys.argv[2]).read_bytes()):
            print(line)
        print("saved", RESUME_PATH)
    elif kind == "image":
        print(ingest_image(sys.argv[2], Path(sys.argv[3]).name, Path(sys.argv[3]).read_bytes()))
    else:
        sys.exit("usage: ingest.py resume <pdf> | image <project-slug|profile> <file>")
