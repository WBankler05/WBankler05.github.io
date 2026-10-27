"""Re-encode every image under media/ in place, removing any metadata.

    .venv\\Scripts\\python tools\\clean_media.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from privacy import IMAGE_SUFFIXES, clean_image, image_has_metadata  # noqa: E402

for path in sorted((ROOT / "media").rglob("*")):
    if path.suffix.lower() in IMAGE_SUFFIXES and image_has_metadata(path):
        cleaned = clean_image(path.read_bytes())
        target = path.with_suffix(".jpg")
        target.write_bytes(cleaned)
        if target != path:
            path.unlink()
        print("cleaned", target.relative_to(ROOT))
