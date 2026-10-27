"""Build the public site: content/ + media/ + static/  ->  docs/ (served by GitHub Pages).

    .venv\\Scripts\\python build.py

Nothing in here talks to the network. The output is plain HTML/CSS/JS with no
server, no database, no forms and no third-party scripts, and the build refuses
to finish if the privacy scan finds anything that should not be public.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from privacy import scan_tree  # noqa: E402

CONTENT = ROOT / "content"
OUT = ROOT / "docs"

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'none'")


# --------------------------------------------------------------------------- helpers
def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def inline(text: str) -> str:
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


def md(text: str) -> str:
    """Tiny, safe markdown: paragraphs, '- ' bullet lists, **bold**, `code`."""
    blocks = []
    for chunk in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l.rstrip() for l in chunk.splitlines() if l.strip()]
        if lines and all(l.lstrip().startswith("- ") for l in lines):
            items = "".join(f"<li>{inline(l.lstrip()[2:])}</li>" for l in lines)
            blocks.append(f"<ul>{items}</ul>")
        elif lines:
            blocks.append(f"<p>{inline(' '.join(lines))}</p>")
    return "\n".join(blocks)


def slug_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fingerprint(html_text: str, out: Path) -> str:
    """Append ?v=<content hash> to local asset links so browsers and GitHub Pages
    never serve a stale copy after an update (e.g. a new resume with the same name)."""
    import hashlib

    def repl(m):
        attr, prefix, rel = m.group(1), m.group(2), m.group(3)
        f = out / rel
        if not f.is_file():
            return m.group(0)
        digest = hashlib.sha1(f.read_bytes()).hexdigest()[:10]
        return f'{attr}="{prefix}{rel}?v={digest}"'

    return re.sub(r'(src|href|data-full)="((?:\.\./)?)((?:media|static)/[^"?#]+)"', repl, html_text)


def load():
    site = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
    projects = []
    for f in sorted((CONTENT / "projects").glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        if p.get("status", "featured") != "hidden":
            projects.append(p)
    projects.sort(key=lambda p: (p.get("order", 99), p["title"]))
    return site, projects


# --------------------------------------------------------------------------- shared chrome
def email_link(site, root, cls="") -> str:
    user, _, domain = site["contact"]["email"].partition("@")
    # assembled by site.js so the address is not sitting in the HTML for scrapers
    return (f'<a class="js-email {cls}" data-u="{esc(user)}" data-d="{esc(domain)}" href="{root}index.html#contact">'
            f'{esc(user)} [at] {esc(domain)}</a>')


def page(site, title, body, root, description, og_image="", active="", contact_links=True):
    name = esc(site["name"])
    url = site.get("site_url", "").rstrip("/")
    og = ""
    if url:
        og = (f'<meta property="og:title" content="{esc(title)}">'
              f'<meta property="og:description" content="{esc(description)}">'
              f'<meta property="og:type" content="website">'
              + (f'<meta property="og:image" content="{esc(url + "/" + og_image)}">' if og_image else ""))

    def nav(label, href, key):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a href="{root}{href}"{cur}>{label}</a>'

    resume = esc(site["contact"]["resume"])
    year = date.today().year
    # The homepage ends with the Connect card, so its footer is just the copyright line.
    # Every other page gets one line of contact links, since it has no Connect card.
    footer_links = "" if not contact_links else f"""<ul class="footer-links">
      <li>{email_link(site, root)}</li>
      <li><a href="{esc(site["contact"]["linkedin"])}" rel="noopener noreferrer" target="_blank">LinkedIn</a></li>
      <li><a href="{root}{resume}" download>Resume</a></li>
    </ul>"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{og}
<link rel="icon" href="{root}static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{root}static/style.css">
<script src="{root}static/site.js" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
  <div class="wrap topbar-inner">
    <a class="brand" href="{root}index.html"><span class="brand-mark" aria-hidden="true">WB</span>{name}</a>
    <nav class="nav" aria-label="Primary">
      {nav("Projects", "index.html#projects", "projects")}
      {nav("Experience", "index.html#experience", "experience")}
      {nav("Contact", "index.html#contact", "contact")}
      <a class="btn btn-small" href="{root}{resume}" download>Resume</a>
    </nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="footer">
  <div class="wrap footer-inner">
    <p class="fine">© {year} {name}</p>
    {footer_links}
  </div>
</footer>
<dialog class="lightbox" aria-label="Image viewer">
  <button class="lightbox-close" type="button" aria-label="Close">×</button>
  <figure><img alt=""><figcaption></figcaption></figure>
</dialog>
</body>
</html>
"""


def label(num, text):
    return f'<p class="eyebrow"><span>{num}</span> {esc(text)}</p>'


def tags(items):
    return "".join(f'<li>{esc(t)}</li>' for t in items)


def project_card(p, root, small=False):
    status = '<span class="badge">In progress</span>' if p.get("status") == "in-progress" else ""
    metric = ""
    if p.get("metrics") and not small:
        m = p["metrics"][0]
        metric = f'<p class="card-metric"><strong>{esc(m["value"])}</strong> {esc(m["label"])}</p>'
    return f"""<a class="card{' card-small' if small else ''}" href="{root}projects/{esc(p['slug'])}.html">
  <div class="card-img"><img src="{root}{esc(p['cover'])}" alt="{esc(p['title'])}" loading="lazy"></div>
  <div class="card-body">
    {status}
    <h3>{esc(p['title'])}</h3>
    <p class="muted">{esc(p['tagline'])}</p>
    {metric}
    <ul class="tags">{tags(p.get('tags', [])[:4])}</ul>
  </div>
</a>"""


# --------------------------------------------------------------------------- home page
def build_home(site, projects):
    root = ""
    featured = [p for p in projects if p.get("status") == "featured"]
    building = [p for p in projects if p.get("status") == "in-progress"]
    resume = esc(site["contact"]["resume"])

    focus = "".join(f"<li>{esc(f)}</li>" for f in site["focus_areas"])
    stats = "".join(f'<div class="stat"><strong>{esc(h["value"])}</strong><span>{esc(h["label"])}</span></div>'
                    for h in site["highlights"])
    cards = "\n".join(project_card(p, root) for p in featured)
    building_html = ""
    if building:
        building_html = f"""<div class="subhead"><h3>Currently building</h3></div>
<div class="grid {'grid-2' if len(building) > 1 else 'grid-1'}">{''.join(project_card(p, root, small=True) for p in building)}</div>"""

    skills = "".join(f"""<div class="skill">
  <h3>{esc(s['group'])}</h3>
  <ul>{''.join(f'<li>{esc(i)}</li>' for i in s['items'])}</ul>
</div>""" for s in site["skills"])

    exp = "".join(f"""<li class="tl-item">
  <div class="tl-when">{esc(e['dates'])}</div>
  <div class="tl-what">
    <h3>{esc(e['title'])}</h3>
    <p class="tl-org">{esc(e['org'])} · {esc(e.get('place', ''))}</p>
    <ul>{''.join(f'<li>{esc(pt)}</li>' for pt in e.get('points', []))}</ul>
  </div>
</li>""" for e in site["experience"])

    lead = "".join(f"""<li>
  <h3>{esc(l['title'])}, {esc(l['org'])}</h3>
  <p class="tl-org">{esc(l['dates'])}</p>
  <p>{esc(l['detail'])}</p>
</li>""" for l in site["leadership"])

    course = "".join(f"<li>{esc(c)}</li>" for c in site.get("coursework", []))
    aff = ", ".join(esc(a) for a in site.get("affiliations", []))

    body = f"""
<section class="hero">
  <div class="wrap hero-grid">
    <div class="hero-text">
      <p class="kicker">{esc(site['university'])} · {esc(site['graduation'])}</p>
      <h1>{esc(site['name'])}</h1>
      <p class="degree">{esc(site['degree'])}</p>
      {f'<p class="lede">{esc(site["headline"])}</p>' if site.get("headline") else ''}
      {f'<p class="mission"><span>Mission</span>{esc(site["intro"])}</p>' if site.get("intro") else ''}
      <div class="seeking">
        <p><span class="dot" aria-hidden="true"></span>{esc(site['seeking'])}</p>
        <ul class="focus">{focus}</ul>
      </div>
      <div class="actions">
        <a class="btn" href="#projects">View projects</a>
        <a class="btn btn-ghost" href="{resume}" download>Download resume</a>
        <a class="btn btn-ghost" href="#contact">Contact</a>
      </div>
    </div>
    <figure class="hero-portrait">
      <img src="{esc(site['headshot'])}" alt="Portrait of {esc(site['name'])}">
    </figure>
  </div>
  <div class="wrap"><div class="stats">{stats}</div></div>
</section>

<section id="projects" class="section">
  <div class="wrap">
    {label("01", "Engineering projects")}
    <div class="section-head">
      <h2>Designed, built, and tested</h2>
    </div>
    <div class="grid grid-2">{cards}</div>
    {building_html}
  </div>
</section>

<section id="experience" class="section section-alt">
  <div class="wrap">
    {label("02", "Skills and experience")}
    <div class="section-head">
      <h2>Technical skills</h2>
    </div>
    <div class="skills">{skills}</div>

    <div class="two-col">
      <div>
        <h2 class="h2-sub">Experience</h2>
        <ol class="timeline">{exp}</ol>
      </div>
      <div>
        <h2 class="h2-sub">Leadership</h2>
        <ul class="lead-list">{lead}</ul>
        <h2 class="h2-sub">Education</h2>
        <div class="edu">
          <h3>{esc(site['university'])}</h3>
          <p class="tl-org">{esc(site['degree'])} · {esc(site['graduation'])}</p>
          <p class="edu-label">Relevant coursework</p>
          <ul class="chips">{course}</ul>
          {f'<p class="muted small">Member of {aff}.</p>' if aff else ''}
        </div>
      </div>
    </div>
  </div>
</section>

<section id="contact" class="section">
  <div class="wrap">
    {label("03", "Resume and contact")}
    <div class="contact">
      <div>
        <h2>Connect</h2>
        <p class="muted">I am looking for Summer 2027 internships in {esc(', '.join(site['focus_areas'][:-1]).lower())}, and {esc(site['focus_areas'][-1].lower())}. The fastest way to reach me is by email.</p>
      </div>
      <div class="contact-links">
        <div class="contact-row"><span>Email</span>{email_link(site, root)}</div>
        <div class="contact-row"><span>LinkedIn</span><a href="{esc(site['contact']['linkedin'])}" rel="noopener noreferrer" target="_blank">{esc(site['contact']['linkedin'].split('//')[-1].removeprefix('www.'))}</a></div>        <a class="btn js-mailto" href="#contact">Email me</a>
      </div>
    </div>
  </div>
</section>
"""
    desc = f"{site['name']}, {site['degree']}, {site['university']}. {site['seeking']}."
    og_image = featured[0]["cover"] if featured else site.get("headshot", "")
    return page(site, f"{site['name']} | Engineering Portfolio", body, root, desc, og_image, contact_links=False)


# --------------------------------------------------------------------------- project page
def chart_svg(chart) -> str:
    """Dot plot. Dots (not bars) because the axis does not start at zero."""
    bars = chart["bars"]
    lo, hi = chart.get("min", 0), chart.get("max", 100)
    w, row, left, right, top = 640, 44, 56, 64, 28
    h = top + row * len(bars) + 24
    span = w - left - right

    def x(v):
        return left + (v - lo) / (hi - lo) * span

    grid = ""
    step = 5 if hi - lo <= 30 else 10
    for t in range(int(lo), int(hi) + 1, step):
        grid += (f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 8}" y2="{h - 20}" class="c-grid"/>'
                 f'<text x="{x(t):.1f}" y="{h - 4}" class="c-tick" text-anchor="middle">{t}{esc(chart.get("unit", ""))}</text>')
    rows = ""
    avg = sum(b["value"] for b in bars) / len(bars)
    for i, b in enumerate(bars):
        y = top + row * i + row / 2
        rows += (f'<text x="{left - 12}" y="{y + 4:.1f}" class="c-label" text-anchor="end">{esc(b["label"])}</text>'
                 f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" class="c-track"/>'
                 f'<circle cx="{x(b["value"]):.1f}" cy="{y:.1f}" r="7" class="c-dot"/>'
                 f'<text x="{x(b["value"]) + 14:.1f}" y="{y + 4:.1f}" class="c-val">{b["value"]:g}{esc(chart.get("unit", ""))}</text>')
    avg_line = (f'<line x1="{x(avg):.1f}" x2="{x(avg):.1f}" y1="{top - 8}" y2="{h - 20}" class="c-avg"/>'
                f'<text x="{x(avg):.1f}" y="{top - 14}" class="c-avg-label" text-anchor="middle">average {avg:.1f}{esc(chart.get("unit", ""))}</text>')
    return f"""<figure class="chart">
  <figcaption>{esc(chart['title'])}</figcaption>
  <svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(chart['title'])}: {', '.join(f"{b['label']} {b['value']:g}" for b in bars)}">
    {grid}{avg_line}{rows}
  </svg>
</figure>"""


def build_project(site, p, prev_p, next_p):
    root = "../"
    meta_rows = [(k.title(), v) for k, v in p.get("meta", {}).items() if v]
    meta = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in meta_rows)
    metrics = "".join(f'<div class="stat"><strong>{esc(m["value"])}</strong><span>{esc(m["label"])}</span></div>'
                      for m in p.get("metrics", []))
    toc = "".join(f'<li><a href="#{slug_id(s["heading"])}">{esc(s["heading"])}</a></li>' for s in p.get("sections", []))
    sections = ""
    for i, s in enumerate(p.get("sections", [])):
        figure = ""
        if s.get("image"):
            figure = (f'<figure class="cs-figure"><button type="button" class="shot-btn" data-full="{root}{esc(s["image"])}" '
                      f'data-caption="{esc(s.get("image_caption", ""))}"><img src="{root}{esc(s["image"])}" '
                      f'alt="{esc(s.get("image_caption", s["heading"]))}" loading="lazy"></button>'
                      f'<figcaption>{esc(s.get("image_caption", ""))}</figcaption></figure>')
        sections += (f'<section id="{slug_id(s["heading"])}" class="cs-section"><h2>{esc(s["heading"])}</h2>'
                     f'{md(s["body"])}{figure}</section>')
        # put the results chart right after the section that discusses results
        if p.get("chart") and i == len(p["sections"]) - 1:
            sections += chart_svg(p["chart"])
    gallery = "".join(f"""<figure class="shot">
  <button type="button" class="shot-btn" data-full="{root}{esc(g['src'])}" data-caption="{esc(g.get('caption', ''))}">
    <img src="{root}{esc(g['src'])}" alt="{esc(g.get('caption', p['title']))}" loading="lazy">
  </button>
  <figcaption>{esc(g.get('caption', ''))}</figcaption>
</figure>""" for g in p.get("gallery", []))
    status = '<span class="badge">In progress</span>' if p.get("status") == "in-progress" else ""

    def pn(q, rel):
        if not q:
            return "<span></span>"
        return (f'<a class="pn pn-{rel}" href="{esc(q["slug"])}.html"><span class="muted small">'
                f'{"Previous" if rel == "prev" else "Next"} project</span><strong>{esc(q["title"])}</strong></a>')

    body = f"""
<article class="case">
  <header class="case-head">
    <div class="wrap">
      <p class="crumb"><a href="{root}index.html#projects">Projects</a> <span aria-hidden="true">/</span> {esc(p['title'])}</p>
      {status}
      <h1>{esc(p['title'])}</h1>
      <p class="lede">{esc(p['tagline'])}</p>
      <p class="case-summary">{esc(p['summary'])}</p>
      {f'<dl class="meta">{meta}</dl>' if meta else ''}
      {f'<div class="stats stats-case">{metrics}</div>' if metrics else ''}
    </div>
  </header>
  <div class="wrap">
    <figure class="case-cover"><img src="{root}{esc(p['cover'])}" alt="{esc(p['title'])}"></figure>
    <div class="case-body">
      <aside class="toc" aria-label="On this page"><p class="eyebrow">On this page</p><ol>{toc}<li><a href="#gallery">Gallery</a></li></ol></aside>
      <div class="prose">{sections}</div>
    </div>
    <section id="gallery" class="gallery-wrap">
      <h2>Gallery</h2>
      <div class="gallery">{gallery}</div>
    </section>
    <nav class="prevnext" aria-label="More projects">{pn(prev_p, 'prev')}{pn(next_p, 'next')}</nav>
  </div>
</article>
"""
    return page(site, f"{p['title']} | {site['name']}", body, root, p["summary"], p["cover"], active="projects")


def build_404(site):
    body = """<section class="section"><div class="wrap narrow">
<h1>Page not found</h1><p class="muted">That page does not exist. Head back to the <a href="index.html">portfolio home page</a>.</p>
</div></section>"""
    return page(site, f"Not found | {site['name']}", body, "", "Page not found")


# --------------------------------------------------------------------------- main
def build(out: Path = OUT) -> list[str]:
    site, projects = load()
    if out.exists():
        shutil.rmtree(out)
    (out / "projects").mkdir(parents=True)
    shutil.copytree(ROOT / "static", out / "static")

    (out / "index.html").write_text(build_home(site, projects), encoding="utf-8")
    for i, p in enumerate(projects):
        prev_p = projects[i - 1] if i > 0 else None
        next_p = projects[i + 1] if i + 1 < len(projects) else None
        (out / "projects" / f"{p['slug']}.html").write_text(build_project(site, p, prev_p, next_p), encoding="utf-8")
    (out / "404.html").write_text(build_404(site), encoding="utf-8")

    # Publish only the media the pages actually use. Hidden projects and unused
    # uploads stay in media/ (so they can come back) but are not put on the web.
    problems = []
    for f in out.rglob("*.html"):
        for ref in set(re.findall(r'(?:src|href|data-full)="(?:\.\./)?(media/[^"#?]+)', f.read_text(encoding="utf-8"))):
            src = ROOT / ref
            if not src.is_file():
                problems.append(f"{f.relative_to(out)}: missing file {ref}")
                continue
            (out / ref).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out / ref)

    for f in out.rglob("*.html"):
        f.write_text(fingerprint(f.read_text(encoding="utf-8"), out), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    problems += scan_tree(out)
    return problems


if __name__ == "__main__":
    issues = build()
    if issues:
        print("BUILD BLOCKED:")
        for i in issues:
            print("  -", i)
        sys.exit(1)
    print(f"built {OUT}")
