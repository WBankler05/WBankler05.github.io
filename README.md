# William Bankler: Engineering Portfolio

Static portfolio site. GitHub Pages serves the `docs/` folder. There is no server, database, login, form, or third-party script, so the public site has nothing that can reach back to this computer.

## Updating the site

Double-click **`Edit Portfolio.bat`**. The editor opens in your browser and runs only on this computer.

| Tab | What it does |
|---|---|
| Projects | Add, edit, reorder, hide, or delete projects. Upload photos and CAD renders. |
| Profile and homepage | Headline, focus areas, homepage image, stats, email, and LinkedIn. |
| Skills and experience | Skill groups, roles, leadership, and coursework. |
| Resume | Upload your normal resume PDF. A web copy is made with the phone number and city removed. |
| Preview and publish | Build, preview, then publish with one click (commit and push). |

Close the black console window to stop the editor.

## Privacy safeguards

- **Photos**: every upload is re-encoded, which strips EXIF data (GPS location, phone model, and timestamps).
- **Resume**: the phone number and city are removed and the PDF metadata is wiped. The build fails if any phone number remains.
- **Build and commit gates**: `build.py` and the git pre-commit hook (`.githooks/`) scan everything public for phone numbers, image metadata, and unexpected file types, and refuse to continue if they find any.
- **Editor**: bound to `127.0.0.1` and protected by a random per-launch token, so other devices and other websites cannot use it.
- **Email**: the address is assembled by JavaScript so that simple scrapers do not harvest it.

The repo is public, and anything committed stays in its history. Never copy original files (with phone numbers or unedited photos) into this folder by hand. Use the editor.

## Layout

```
content/site.json          profile, skills, experience, contact
content/projects/*.json    one file per project (case study text, metrics, gallery)
media/                     cleaned images and the web resume
static/                    CSS, JS, favicon
build.py                   content -> docs/   (.venv\Scripts\python build.py)
editor/                    local editor (server.py + index.html)
tools/                     privacy.py, ingest.py, clean_media.py, precommit.py
docs/                      generated site; do not edit by hand
```

## Text formatting in case-study sections

- A blank line starts a new paragraph.
- Lines starting with `- ` become bullets.
- `**bold**` makes text bold.

## First-time setup on a new computer

```
py -m venv .venv
.venv\Scripts\python -m pip install pymupdf pillow
git config core.hooksPath .githooks
```
