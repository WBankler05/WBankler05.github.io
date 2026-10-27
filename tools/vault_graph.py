r"""Render the BanklerBot vault knowledge graph (no note titles, so nothing private).

    .venv\Scripts\python tools\vault_graph.py <path-to-vault> out.jpg

Then upload out.jpg through the editor.
"""
import re, sys, math
from pathlib import Path
import networkx as nx
from PIL import Image, ImageDraw
V, OUT = Path(sys.argv[1]), sys.argv[2]
SKIP = {".git", ".obsidian", ".trash", "node_modules", "_attachments", "_outbox", ".claude", ".venv"}
notes = [p for p in V.rglob("*.md") if not any(x in SKIP for x in p.relative_to(V).parts)]
names = {p.stem.lower(): p for p in notes}
link_re = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
G = nx.Graph(); G.add_nodes_from(notes)
for p in notes:
    for m in link_re.finditer(p.read_text(encoding="utf-8", errors="ignore")):
        t = names.get(Path(m.group(1).strip()).name.lower())
        if t and t != p: G.add_edge(p, t)
G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
# ForceAtlas2 with gravity pulls everything into one cohesive cloud (Obsidian-style)
pos = nx.forceatlas2_layout(G, max_iter=1500, gravity=1.0, scaling_ratio=2.0, strong_gravity=True, seed=7)
W, H, SS = 1600, 820, 2
BG = (14, 17, 22)
img = Image.new("RGB", (W * SS, H * SS), BG); d = ImageDraw.Draw(img, "RGBA")
xs = sorted(v[0] for v in pos.values()); ys = sorted(v[1] for v in pos.values())
lo_x, hi_x = xs[int(len(xs) * .01)], xs[int(len(xs) * .99)]; lo_y, hi_y = ys[int(len(ys) * .01)], ys[int(len(ys) * .99)]
span = max(hi_x - lo_x, hi_y - lo_y)
cx, cy = (lo_x + hi_x) / 2, (lo_y + hi_y) / 2
scale = (H * SS * 0.86) / span
def tx(v): return (W * SS / 2 + (v[0] - cx) * scale, H * SS / 2 + (v[1] - cy) * scale)
for a, b in G.edges():
    d.line([tx(pos[a]), tx(pos[b])], fill=(175, 190, 215, 60), width=SS)
maxdeg = max(dict(G.degree).values())
for n in sorted(G.nodes, key=G.degree):
    x, y = tx(pos[n]); deg = G.degree(n)
    r = (2.6 + 1.3 * math.sqrt(min(deg, 50))) * SS
    t = min(1, math.sqrt(deg / maxdeg) * 1.6)          # hubs read brighter
    col = tuple(int(150 + (235 - 150) * t) for _ in range(3))
    d.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,))
img = img.resize((W, H), Image.LANCZOS)
img.save(OUT, "JPEG", quality=90, optimize=True, progressive=True)
print(G.number_of_nodes(), "nodes", G.number_of_edges(), "edges")
