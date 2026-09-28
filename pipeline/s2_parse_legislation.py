"""S2: parse Cap 123 + subsidiary e-Legislation XML (EN + zh-Hant) to one record per section / regulation / schedule."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import glob, json, re, pathlib
from lxml import etree
NS = "{http://www.xml.gov.hk/schemas/hklm/1.0}"
DC = "{http://purl.org/dc/elements/1.1/}"
RAW = pathlib.Path(str(WORK / "raw/legislation"))
OUT = pathlib.Path(__file__).with_name("S2_legislation_sections.json")
LN = lambda e: etree.QName(e).localname if isinstance(e.tag, str) else ""

def txt(e):
    return re.sub(r"\s+", " ", "".join(e.itertext())).strip() if e is not None else ""

def ancestors(e):
    out = []
    p = e.getparent()
    while p is not None and LN(p) != "main":
        if LN(p) in ("part", "division", "subdivision", "schedule"):
            out.append(f"{txt(p.find(NS+'num'))} {txt(p.find(NS+'heading'))}".strip())
        p = p.getparent()
    return list(reversed(out))

def load(cap, lang):
    f = glob.glob(str(RAW / f"cap_{cap}_{lang}_c" / "*.xml"))
    if not f: return None
    r = etree.parse(f[0]).getroot()
    main = r.find(NS + "main")
    meta = {"status": r.findtext(f"{NS}meta/{NS}docStatus"), "date": r.findtext(f"{NS}meta/{DC}date"),
            "title": (txt(main.find(f"{NS}docTitle")) or txt(main.find(f".//{NS}shortTitle"))) if main is not None else "",
            "longTitle": txt(main.find(f"{NS}longTitle/{NS}content")) if main is not None else ""}
    items = {}
    if main is None: return meta, items
    for e in main.iter(NS + "section", NS + "schedule"):
        kind = LN(e)
        # a section nested inside a schedule is a schedule paragraph; keep it but mark it
        in_sched = any(LN(a) == "schedule" for a in e.iterancestors())
        name = e.get("name") or e.get("temporalId") or e.get("id")
        anc_names = "/".join(a.get("name") or "" for a in reversed(list(e.iterancestors())) if LN(a) in ("part","division","subdivision","schedule"))
        key = (kind, name, anc_names if in_sched else "")
        rec = {"kind": ("schedule_section" if in_sched and kind == "section" else kind),
               "name": name, "num": txt(e.find(NS + "num")), "heading": txt(e.find(NS + "heading")),
               "status": e.get("status") or e.get("reason") or "", "xpid": e.get("id"), "role": e.get("role"),
               "startPeriod": e.get("startPeriod"), "endPeriod": e.get("endPeriod"),
               "context": ancestors(e)}
        # temporal versions: prefer the one without endPeriod
        if key in items and items[key]["endPeriod"] is None: continue
        items[key] = rec
    return meta, items

caps = sorted({pathlib.Path(p).name.split("_")[1] for p in glob.glob(str(RAW / "cap_123*_en_c"))},
              key=lambda c: (len(c), c))
records, instruments = [], []
for cap in caps:
    en = load(cap, "en"); zh = load(cap, "zh-Hant")
    (men, ien), (mzh, izh) = en, zh
    instruments.append({"cap": cap, "title_en": men["title"], "title_zh": mzh["title"], "status": men["status"],
                        "version_date": men["date"], "sections": len(ien),
                        "url_en": f"https://www.elegislation.gov.hk/hk/cap{cap}!en",
                        "url_zh": f"https://www.elegislation.gov.hk/hk/cap{cap}!zh-Hant-HK"})
    for key, r in ien.items():
        z = izh.get(key, {})
        records.append({
            "cap": cap, "id": (f"Cap {cap} {r['name']}" if r['kind'] != 'section' else f"Cap {cap} {'reg' if r['role']=='regulation' else 's'} {r['name'][1:] if r['name'].startswith('s') else r['name']}") + (f" [{key[2]}]" if r['kind']=='schedule_section' else ""),
            "kind": r["kind"], "name": r["name"], "num": r["num"],
            "title_en": r["heading"], "title_zh": z.get("heading", ""),
            "status": r["status"], "in_force_from": r["startPeriod"],
            "part_en": r["context"], "part_zh": z.get("context", []),
            "url_en": f"https://www.elegislation.gov.hk/hk/cap{cap}!en?xpid={r['xpid']}",
            "url_zh": f"https://www.elegislation.gov.hk/hk/cap{cap}!zh-Hant-HK?xpid={z.get('xpid', r['xpid'])}",
        })
out = {"source": "DoJ Hong Kong e-Legislation open data, data.gov.hk dataset hk-doj-hkel-legislation-current (zips dated 2026-09-21)",
       "parsed": "2026-09-27",
       "note": "Section deep links use the ?xpid= pattern. UNVERIFIED by script: elegislation.gov.hk sends scripted requests to a client-config check page. The instrument-level URLs are the standard e-Legislation form.",
       "instruments": instruments, "records": records}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(records), "records")
for i in instruments: print(i["cap"], i["status"], i["version_date"], i["sections"], i["title_en"], "|", i["title_zh"])
