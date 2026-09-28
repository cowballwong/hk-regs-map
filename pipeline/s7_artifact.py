"""S7 step 4b: make the claude.ai Artifact copy of the site in the site folder artifact/ and check it.
The platform wraps the page in its own skeleton, so index.html has no doctype / html / head / body tags:
it starts with <title> and <style>, then the markup, then the scripts (data.js, layout.js, app.js, relative).
Usage: python s7_artifact.py   (re-run after any change to the site files)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import re, shutil
from pathlib import Path

ART = SITE / "artifact"; ART.mkdir(exist_ok=True)
src = (SITE / "index.html").read_text(encoding="utf-8")

style = re.search(r"<style>.*?</style>", src, re.S).group(0)
body = re.search(r"<body>(.*)</body>", src, re.S).group(1).strip()
page = "<title>香港建築規例關係地圖</title>\n" + style + "\n" + body + "\n"
(ART / "index.html").write_text(page, encoding="utf-8")
for f in ("app.js", "data.js", "layout.js"):
    shutil.copyfile(SITE / f, ART / f)

# ---------------- checks ----------------
fails = []
low = page.lower()
for m in re.finditer(r"<!doctype|</?(html|head|body)[\s>]", low):
    fails.append("forbidden tag " + m.group(0))
if "<title>香港建築規例關係地圖</title>" not in page.encode("utf-8")[:8192].decode("utf-8", "ignore"):
    fails.append("title not in first 8 KB")
if not page.startswith("<title>"):
    fails.append("page does not start with <title>")
if not re.search(r"html,body\{[^}]*height:100%[^}]*background:#[0-9a-f]{6}", page):
    fails.append("html/body lack height:100% + explicit background")
if re.search(r"\d+(\.\d+)?d?vh\b|\d+(\.\d+)?vw\b", page):
    fails.append("viewport units present: " + ", ".join(set(re.findall(r"\d+d?v[hw]\b", page))))
if "safe-area-inset" not in page:
    fails.append("no safe-area padding")
code = page + (ART / "app.js").read_text(encoding="utf-8")
for m in re.finditer(r"\b(alert|confirm|prompt)\s*\(", code):
    fails.append("dialog call: " + m.group(0))
ALLOW = ("https://cdn.jsdelivr.net/npm/", "https://cdnjs.cloudflare.com/", "https://fonts.googleapis.com/", "https://fonts.gstatic.com/")
# every URL in the page markup and app code must be an allowed CDN (data.js URLs are plain <a> links out, checked below)
for m in re.finditer(r"https?://[^\s'\"`)<>]+", code):
    u = m.group(0)
    if not u.startswith(ALLOW):
        fails.append("non-allowed URL in page/app: " + u)
for m in re.finditer(r"cdn\.jsdelivr\.net/npm/([^/'\"`]+)", code):
    if not re.search(r"@\d+\.\d+\.\d+$", m.group(1)):
        fails.append("unpinned package: " + m.group(1))
for m in re.finditer(r"<script[^>]*src=\"([^\"]+)\"", page):
    if m.group(1) not in ("data.js", "layout.js", "app.js"):
        fails.append("script src " + m.group(1))
for m in re.finditer(r"<a [^>]*href=[^>]*>", code):
    if 'target="_blank"' not in m.group(0) or 'rel="noopener"' not in m.group(0):
        fails.append("link without target/rel: " + m.group(0)[:80])
for m in re.finditer(r"\bfetch\(|XMLHttpRequest|new WebSocket|navigator\.sendBeacon", code):
    fails.append("network call: " + m.group(0))

sizes = {f.name: f.stat().st_size for f in sorted(ART.iterdir()) if f.is_file()}
total = sum(sizes.values())
if total >= 16 * 1024 * 1024:
    fails.append(f"total {total} bytes >= 16 MB")
for k, v in sizes.items():
    print(f"  {k:12s} {v / 1024:9.1f} KB")
print(f"  total        {total / 1024 / 1024:9.2f} MB (limit 16 MB)")
print("CHECKS:", "all passed" if not fails else "\n  " + "\n  ".join(fails))
