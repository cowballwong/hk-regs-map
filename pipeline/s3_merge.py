"""Merge per-department S3 files into S3_inventory.json (common schema)."""
import json, re, pathlib, collections, datetime
H = pathlib.Path(__file__).parent
MON = {m: i for i, m in enumerate("January February March April May June July August September October November December".split(), 1)}
bd = json.loads((H / "s3_bd.json").read_text(encoding="utf-8"))
ld = json.loads((H / "s3_landsd.json").read_text(encoding="utf-8"))
pl = json.loads((H / "s3_pland.json").read_text(encoding="utf-8"))
fs = json.loads((H / "s3_fsd.json").read_text(encoding="utf-8"))
recs = bd + ld["records"] + pl["records"] + fs
KEEP = ["department", "series", "code", "title_en", "title_zh", "latest_issue", "latest_issue_raw", "status", "url_en", "url_zh", "languages", "index_page"]
out = []
for r in recs:
    if r["department"] == "FSD" and r["series"] == "FSD Circular Letter" and not r["code"]:
        m = re.match(r"^(.{1,12}?)\s+-\s+(.*)$", r["title_en"])
        if m: r["code"] = f"FSD CL {m.group(1)} (old series)"; r["title_en"] = m.group(2)
    if r["department"] == "FSD" and r["series"] == "FSD Code of Practice":
        m = re.match(r"([A-Z][a-z]+) (\d{4})", r["latest_issue"]); r["latest_issue"] = f"{m.group(2)}-{MON[m.group(1)]:02d}" if m else r["latest_issue"]
    if r["department"] == "FSD" and r["series"] == "FSD Fire Protection Notice":
        r["title_en"] += " (title UNVERIFIED: index link has no subject text)"
    if r["department"] == "PlanD/TPB" and r["code"].endswith("13G"):
        r["latest_issue"] = "2024-03"; r["latest_issue_raw"] = "TPB notice 'Updated TPB PG-No. 13G (March 2024)'"
    o = {k: r.get(k, "") for k in KEEP}
    extra = {k: v for k, v in r.items() if k not in KEEP and k not in ("department",)}
    o["extra"] = extra
    out.append(o)
counts = collections.Counter((o["department"], o["series"]) for o in out)
doc = {"built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
       "method": "Department index pages only (EN + TC), fetched at >=2.5 s intervals with a normal browser User-Agent. No PDFs downloaded.",
       "counts": {f"{d} | {s}": n for (d, s), n in sorted(counts.items())}, "total": len(out),
       "not_inventoried": {"LandsD LACO Circular Memoranda (rows)": ld["not_inventoried_counts"]["laco"], "LandsD SMO Practice Notes": ld["not_inventoried_counts"]["smo"],
                           "LandsD Information Notes": ld["not_inventoried_counts"]["info-notes"], "TPB Guidelines, pre-1.9.2023 set": pl["old_set_count"]},
       "bd_pnap_bundle_zips": json.loads((H / "s3_bd_bundles.json").read_text()),
       "records": out}
(H / "S3_inventory.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(doc["total"]); [print(f"  {k}: {v}") for k, v in doc["counts"].items()]
print("zh titles missing:", collections.Counter(o["department"] for o in out if not o["title_zh"]))
print("no date:", collections.Counter(o["series"] for o in out if not o["latest_issue"]))
print("langs:", collections.Counter((o["department"], tuple(o["languages"])) for o in out))
