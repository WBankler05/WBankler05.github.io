"""Pre-commit privacy gate: scan every staged file before it can enter the public history."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from privacy import scan_tree  # noqa: E402

staged = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                        cwd=ROOT, capture_output=True, text=True).stdout.split("\0")
staged = [s for s in staged if s]
# code files legitimately contain the phone regex itself; scan published content only
scoped = [s for s in staged if s.startswith(("content/", "media/", "docs/", "static/"))]

problems = []
with tempfile.TemporaryDirectory() as tmp:
    for rel in scoped:
        blob = subprocess.run(["git", "show", f":{rel}"], cwd=ROOT, capture_output=True).stdout
        dest = Path(tmp) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    problems = [p.replace(tmp, "") for p in scan_tree(Path(tmp))]

if problems:
    print("COMMIT BLOCKED by the privacy check:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
