"""Local portfolio editor. Runs ONLY on this computer; nothing here is ever published.

    Double-click "Edit Portfolio.bat"  (or: .venv\\Scripts\\python editor\\server.py)

Security model:
  * binds to 127.0.0.1, so other machines on the network cannot reach it
  * every API call needs a random per-launch token, so a web page you happen to
    have open in another tab cannot drive it (cross-site request forgery)
  * the Host header must be 127.0.0.1/localhost, which blocks DNS-rebinding tricks
  * file access is confined to this repo's content/, media/ and docs/ folders
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
from ingest import SLUG_RE, ingest_image, ingest_resume, RESUME_PATH  # noqa: E402

HOST, PORT = "127.0.0.1", 8770
TOKEN = secrets.token_urlsafe(24)
MAX_BODY = 60 * 1024 * 1024
CONTENT = ROOT / "content"
PROJECTS = CONTENT / "projects"
EDITOR_HTML = Path(__file__).with_name("index.html")


def git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def safe_under(base: Path, rel: str) -> Path | None:
    target = (base / rel).resolve()
    return target if target.is_file() and base.resolve() in target.parents else None


def state() -> dict:
    site = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
    projects = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(PROJECTS.glob("*.json"))]
    projects.sort(key=lambda p: (p.get("order", 99), p.get("title", "")))
    media = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "media").rglob("*") if p.is_file())
    _, remote = git("remote", "get-url", "origin")
    _, dirty = git("status", "--porcelain")
    return {
        "site": site,
        "projects": projects,
        "media": media,
        "resume": RESUME_PATH.relative_to(ROOT).as_posix() if RESUME_PATH.exists() else None,
        "git": {"remote": remote if "github.com" in remote else None, "changes": len(dirty.splitlines())},
    }


def validate_project(p: dict) -> None:
    if not SLUG_RE.match(p.get("slug", "")):
        raise ValueError("Slug must be lowercase letters, numbers, and dashes (e.g. robot-arm).")
    if not p.get("title"):
        raise ValueError("A project needs a title.")
    if p.get("status") not in ("featured", "in-progress", "hidden"):
        raise ValueError("Status must be featured, in-progress, or hidden.")


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "PortfolioEditor"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # ---------------------------------------------------------------- guards
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def _api_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return False
        return secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _file(self, path: Path | None) -> None:
        if not path:
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._send(200, EDITOR_HTML.read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/preview/"):
            rel = path[len("/preview/"):] or "index.html"
            if rel.endswith("/"):
                rel += "index.html"
            return self._file(safe_under(ROOT / "docs", rel))
        if path.startswith("/media/"):
            return self._file(safe_under(ROOT / "media", path[len("/media/"):]))
        if path == "/api/state":
            if not self._api_ok():
                return self._json(403, {"error": "bad token: close this tab and relaunch the editor"})
            return self._json(200, state())
        self._send(404, b"not found", "text/plain")

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        if not self._host_ok() or not self._api_ok():
            return self._json(403, {"error": "bad token: close this tab and relaunch the editor"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"error": "file too large (60 MB max)"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            route = urlparse(self.path).path
            handler = ROUTES.get(route)
            if not handler:
                return self._json(404, {"error": "unknown action"})
            return self._json(200, handler(body))
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:  # surface everything; this is a local tool
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


# -------------------------------------------------------------------- actions
def save_site(body):
    site = body["site"]
    for key in ("name", "contact"):
        if not site.get(key):
            raise ValueError(f"'{key}' cannot be empty")
    write_json(CONTENT / "site.json", site)
    return {"ok": True}


def save_project(body):
    p = body["project"]
    validate_project(p)
    old = body.get("old_slug")
    target = PROJECTS / f"{p['slug']}.json"
    if old and old != p["slug"]:
        if target.exists():
            raise ValueError(f"A project with slug '{p['slug']}' already exists.")
        (PROJECTS / f"{old}.json").unlink(missing_ok=True)
    elif not old and target.exists():
        raise ValueError(f"A project with slug '{p['slug']}' already exists.")
    write_json(target, p)
    return {"ok": True}


def delete_project(body):
    slug = body.get("slug", "")
    if not SLUG_RE.match(slug):
        raise ValueError("bad slug")
    (PROJECTS / f"{slug}.json").unlink(missing_ok=True)
    return {"ok": True}


def reorder(body):
    for i, slug in enumerate(body["order"], 1):
        f = PROJECTS / f"{slug}.json"
        if SLUG_RE.match(slug) and f.exists():
            p = json.loads(f.read_text(encoding="utf-8"))
            p["order"] = i
            write_json(f, p)
    return {"ok": True}


def upload(body):
    data = base64.b64decode(body["data"].split(",", 1)[-1])
    return {"path": ingest_image(body["folder"], body["filename"], data)}


def upload_resume(body):
    data = base64.b64decode(body["data"].split(",", 1)[-1])
    if not data.startswith(b"%PDF"):
        raise ValueError("That file is not a PDF.")
    return {"report": ingest_resume(data)}


def do_build(_body):
    problems = build.build()
    return {"ok": not problems, "problems": problems}


def publish(body):
    problems = build.build()
    if problems:
        return {"ok": False, "log": "Publish blocked by the privacy check:\n" + "\n".join(problems)}
    message = re.sub(r"\s+", " ", body.get("message") or "Update portfolio").strip()[:200]
    log = []
    git("add", "-A")
    code, out = git("commit", "-m", message)
    log.append(out)
    if code != 0 and "nothing to commit" not in out:
        return {"ok": False, "log": "\n".join(log)}
    _, remote = git("remote", "get-url", "origin")
    if "github.com" not in remote:
        log.append("\nSaved locally. No GitHub remote is set up yet, so nothing was pushed.")
        return {"ok": True, "log": "\n".join(log)}
    code, out = git("push", "origin", "HEAD")
    log.append(out)
    if code == 0:
        log.append("\nPublished. GitHub Pages usually updates within a minute or two.")
    return {"ok": code == 0, "log": "\n".join(log)}


ROUTES = {
    "/api/site": save_site,
    "/api/project": save_project,
    "/api/project/delete": delete_project,
    "/api/reorder": reorder,
    "/api/upload": upload,
    "/api/resume": upload_resume,
    "/api/build": do_build,
    "/api/publish": publish,
}


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/#t={TOKEN}"
    print("Portfolio editor running at", f"http://127.0.0.1:{PORT}/", flush=True)
    print("Close this window to stop the editor.", flush=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    else:
        print("open:", url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
