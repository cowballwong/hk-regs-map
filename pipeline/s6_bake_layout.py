"""S6: bake the force layouts (3D + 2D, by department + by domain) into the site folder layout.js.
Runs the site's own forces (app.js ?bake) in headless Chromium, so the page loads settled and animates between layouts.
Re-run whenever data.js changes: python s6_build_data.py && python s6_bake_layout.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    t0 = time.time(); pg.goto((SITE / "index.html").as_uri() + "?bake")
    pg.wait_for_function("window.BAKED", timeout=600000)
    out = pg.evaluate("window.BAKED"); b.close()
js = "/* Baked force layouts for the HK Building Regulations Map. Made by pipeline/s6_bake_layout.py; do not edit. */\nwindow.HKLAYOUT=" + json.dumps(out, separators=(",", ":")) + ";\n"
(SITE / "layout.js").write_text(js, encoding="utf-8")
print("layout.js", round(len(js) / 1e3), "KB, bake", out.get("seconds"), "s in page,", round(time.time() - t0), "s total, errors:", errs)
