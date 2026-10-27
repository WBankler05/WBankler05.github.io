"""Privacy guards shared by the build, the local editor and the pre-commit hook.

Everything that reaches the public site passes through here:
  * images are re-encoded, which drops EXIF (GPS location, phone model, timestamps)
  * the resume PDF gets its phone number / street-level location removed and its
    metadata scrubbed
  * scan_tree() refuses to let a build or commit through if a phone number,
    an un-stripped image or an unexpected file type is found
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageOps

# (210) 290-1272 / 210-290-1272 / 210.290.1272 / +1 210 290 1272
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
# "Nashville, TN" style city/state token, only ever stripped from the contact line
CITY_STATE_RE = re.compile(r"^[A-Z][A-Za-z.\s]+,\s*[A-Z]{2}$")

PUBLIC_SUFFIXES = {".html", ".css", ".js", ".jpg", ".jpeg", ".png", ".webp", ".svg", ".pdf", ".ico", ".txt", ".xml", ".json", ""}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_EDGE = 1800


# --------------------------------------------------------------------------- images
def clean_image(data: bytes) -> bytes:
    """Return a web-ready JPEG with all metadata removed and orientation baked in."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # keep phone photos the right way up
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, "white")
        img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
    out = io.BytesIO()
    # no exif= / icc_profile= arguments: Pillow writes a bare JPEG
    img.save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue()


def image_has_metadata(path: Path) -> bool:
    with Image.open(path) as img:
        return bool(img.getexif()) or "exif" in img.info or "xmp" in img.info


# --------------------------------------------------------------------------- resume
def redact_resume(data: bytes, linkedin_url: str = "", email: str = "") -> tuple[bytes, list[str]]:
    """Strip phone numbers and the city/state token from a resume PDF.

    The contact line (the line holding the phone number) is removed and redrawn,
    centred, with only the segments that are safe to publish. Every other phone
    number anywhere in the document is blacked out. Links that sat on the contact
    line are dropped and re-added for the surviving email / LinkedIn segments, which
    also removes stray template links. Returns (pdf_bytes, report_lines).
    """
    import pymupdf

    report: list[str] = []
    doc = pymupdf.open(stream=data, filetype="pdf")

    for page in doc:
        page_dict = page.get_text("dict")
        for block in page_dict["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"])
                if not PHONE_RE.search(text):
                    continue
                parts = [p.strip() for p in text.split("|")]
                keep = [p for p in parts if p and not PHONE_RE.search(p) and not CITY_STATE_RE.match(p)]
                dropped = [p for p in parts if p and p not in keep]
                bbox = pymupdf.Rect(line["bbox"])
                span = line["spans"][0]
                size = span["size"]
                # drop every link touching this line (template leftovers included)
                for link in page.get_links():
                    if pymupdf.Rect(link["from"]).intersects(bbox):
                        report.append(f"removed link on contact line: {link.get('uri', '?')}")
                        page.delete_link(link)
                page.add_redact_annot(bbox, fill=(1, 1, 1))
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
                report.append("removed from contact line: " + ", ".join(dropped))
                if keep:
                    font = "Times-Roman" if "Times" in span["font"] else "Helvetica"
                    sep = " | "
                    new_text = sep.join(keep)
                    width = pymupdf.get_text_length(new_text, fontname=font, fontsize=size)
                    x = (page.rect.width - width) / 2
                    y = span["origin"][1]
                    page.insert_text((x, y), new_text, fontname=font, fontsize=size)
                    # re-link the surviving segments
                    cursor = x
                    for i, seg in enumerate(keep):
                        w = pymupdf.get_text_length(seg, fontname=font, fontsize=size)
                        uri = None
                        if "@" in seg:
                            uri = "mailto:" + (email or seg)
                        elif "linkedin.com" in seg:
                            uri = linkedin_url or ("https://" + seg.removeprefix("https://").removeprefix("http://"))
                        if uri:
                            page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(cursor, bbox.y0, cursor + w, bbox.y1), "uri": uri})
                        cursor += w + pymupdf.get_text_length(sep, fontname=font, fontsize=size)
        # any phone number left anywhere else on the page
        for m in set(PHONE_RE.findall(page.get_text())):
            for r in page.search_for(m):
                page.add_redact_annot(r, fill=(1, 1, 1))
                report.append(f"blanked phone number elsewhere on page {page.number + 1}")
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

    doc.set_metadata({"title": "William Bankler - Resume", "author": "William Bankler", "subject": "", "keywords": "",
                      "creator": "", "producer": ""})
    doc.del_xml_metadata()
    out = doc.tobytes(garbage=4, deflate=True, clean=True)

    check = pymupdf.open(stream=out, filetype="pdf")
    leftover = [m for p in check for m in PHONE_RE.findall(p.get_text())]
    if leftover:
        raise ValueError(f"phone number still present after redaction: {leftover}")
    report.append("verified: no phone numbers remain; metadata scrubbed")
    return out, report


def pdf_problems(path: Path) -> list[str]:
    import pymupdf

    doc = pymupdf.open(path)
    probs = []
    if any(PHONE_RE.search(p.get_text()) for p in doc):
        probs.append(f"{path}: contains a phone number")
    return probs


# --------------------------------------------------------------------------- scanning
def scan_text(text: str, where: str) -> list[str]:
    return [f"{where}: phone number '{m}'" for m in PHONE_RE.findall(text)]


def scan_tree(root: Path) -> list[str]:
    """Problems that must block a publish. Empty list == safe."""
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in PUBLIC_SUFFIXES:
            problems.append(f"{path}: file type {suffix} is not allowed on the public site")
        elif suffix in IMAGE_SUFFIXES:
            if image_has_metadata(path):
                problems.append(f"{path}: image still carries EXIF/XMP metadata")
        elif suffix == ".pdf":
            problems += pdf_problems(path)
        elif suffix in {".html", ".js", ".json", ".txt", ".xml", ".css"}:
            problems += scan_text(path.read_text(encoding="utf-8", errors="ignore"), str(path))
    return problems
