"""S3 BD inventory from BD index pages (EN + TC). Index pages only; no PDFs fetched."""
import re, json, pathlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fetch import get
OUT = pathlib.Path(__file__).with_name("s3_bd.json")
PN = "https://www.bd.gov.hk/{l}/resources/codes-and-references/practice-notes-and-circular-letters/{p}"
CD = "https://www.bd.gov.hk/{l}/resources/codes-and-references/codes-and-design-manuals/index.html"
MON = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

def clean(t): return re.sub(r"\s+", " ", t or "").strip()
def key(h):  # language-neutral key for a PDF href
    h = h.lower().replace("/doc/tc/", "/doc/xx/").replace("/doc/en/", "/doc/xx/")
    return re.sub(r"(_?)(e|c|eng|chi|_e|_c)(\.pdf)$", r"\3", h)
def iso(d):
    m = re.match(r"([A-Z][a-z]{2})\w*\s+(\d{4})", d or "")
    return f"{m.group(2)}-{MON[m.group(1)]:02d}" if m else (d or "")

def pn_rows(lang, page):
    u = PN.format(l=lang, p=page); s = BeautifulSoup(get(u), "lxml"); out = []
    for ti, t in enumerate(s.find_all("table")):
        for ri, tr in enumerate(tr for tr in t.find_all("tr") if tr.find("td", class_="notices_no") or "disable" in (tr.get("class") or [])):
            no = tr.find("td", class_="notices_no") or tr.find("td"); a = no.find("a")
            ttd = tr.find("td", class_="notices_title") or (tr.find_all("td") + [tr.find("td")])[1]
            det = ttd.find("div")
            title = clean("".join(x for x in ttd.find_all(string=True, recursive=False)))
            if not title:
                title = clean(ttd.get_text(" ").split("More detail")[0])
            detail = clean(det.get_text(" ")) if det else ""
            links = {clean(x.get_text()): urljoin(u, x["href"]) for x in (det.find_all("a", href=True) if det else [])}
            out.append({"code": clean(no.get_text()), "title": title, "date": clean((tr.find("td", class_="notices_date") or ttd).get_text()) if tr.find("td", class_="notices_date") else "",
                        "url": urljoin(u, a["href"]) if a else "", "detail": detail, "cancelled": "disable" in (tr.get("class") or []), "links": links, "pos": (ti, ri), "page": u})
    return out

recs = []
def add(**k): recs.append({"department": "BD", **k})

PAGES = [("index_pnap.html", None), ("index_pnrc.html", "PNRC"), ("index_joint.html", "JPN"), ("index_pnbi.html", "PNBI")]
for page, series in PAGES:
    en, tc = pn_rows("en", page), pn_rows("tc", page)
    tck = {key(r["url"]): r for r in tc if r["url"]}; tcp = {r["pos"]: r for r in tc}
    for r in en:
        z = tck.get(key(r["url"])) or tcp.get(r["pos"]) or {}
        code = r["code"]
        ser = series or ("PNAP " + code.split("-")[0])
        full = (f"PNAP {code}" if series is None else code)
        formerly = re.search(r"Formerly ([^|]+)", r["detail"])
        add(series=ser, code=full, title_en=r["title"], title_zh=z.get("title", ""), latest_issue=iso(r["date"]), latest_issue_raw=r["date"],
            url_en=r["url"], url_zh=z.get("url", ""), languages=[l for l, v in (("en", r["url"]), ("zh-Hant", z.get("url"))) if v],
            index_page=r["page"], formerly=clean(formerly.group(1)) if formerly else "",
            signed_copy=r["links"].get("Signed Copy", ""), obsolete_versions=r["links"].get("Obsolete Versions", ""),
            status="cancelled (listed without PDF)" if r["cancelled"] else "in force",
            zh_match="href" if r["url"] and key(r["url"]) in tck else ("position" if z else "none"))

# Circular letters
def circ(lang):
    u = PN.format(l=lang, p="index_circulars.html"); s = BeautifulSoup(get(u), "lxml"); out = []
    for t in s.find_all("table"):
        cap = clean(t.find("caption").get_text()) if t.find("caption") else ""
        group = "Circular Letters to Industry Stakeholders" if t.find("th") else "Circular Letters to AP/RSE/RGE/RC"
        for tr in t.find_all("tr"):
            tds = tr.find_all("td")
            if not tds: continue
            yr = re.search(r"(19|20)\d\d", cap)
            if len(tds) == 2 and re.fullmatch(r"\d{4}", clean(tds[0].get_text())): yr_s = clean(tds[0].get_text())
            else: yr_s = yr.group(0) if yr else ""
            for a in tr.find_all("a", href=True):
                out.append({"title": clean(a.get_text()), "url": urljoin(u, a["href"]), "year": yr_s, "group": group, "page": u})
    return out
en, tc = circ("en"), circ("tc"); tck = {key(r["url"]): r for r in tc}
for r in en:
    z = tck.get(key(r["url"]), {})
    add(series="BD Circular Letter", code="", title_en=r["title"], title_zh=z.get("title", ""), latest_issue=r["year"], latest_issue_raw=r["year"] + " (year only on index; exact date in PDF)",
        url_en=r["url"], url_zh=z.get("url", ""), languages=[l for l, v in (("en", r["url"]), ("zh-Hant", z.get("url"))) if v],
        index_page=r["page"], group=r["group"], zh_match="href" if z else "none")

# Codes of practice, design manuals, guidelines
def codes(lang):
    u = CD.format(l=lang); s = BeautifulSoup(get(u), "lxml"); out = []
    for pane, series in (("pane-A", "BD Code of Practice / Design Manual"), ("pane-B", "BD Guideline")):
        p = s.find("div", id=pane)
        for ti, t in enumerate(p.find_all("table")):
            cap = clean(t.find("caption").get_text()) if t.find("caption") else ""
            for ri, tr in enumerate(tr for tr in t.find_all("tr") if tr.find("td")):
                links = [(clean(a.get_text()), urljoin(u, a["href"])) for a in tr.find_all("a", href=True)]
                if not links: continue
                title, url = links[0]
                amend = [x for x in links[1:] if re.search(r"Amendment|修訂", x[0])]
                out.append({"title": title, "url": url, "series": series, "group": cap, "amend": amend, "pos": (pane, ti, ri),
                            "other": [x for x in links[1:] if x not in amend], "page": u})
    return out
en, tc = codes("en"), codes("tc"); tck = {key(r["url"]): r for r in tc}; tcp = {r["pos"]: r for r in tc}
for r in en:
    z = tck.get(key(r["url"])) or tcp.get(r["pos"]) or {}
    yrs = re.findall(r"\b(19\d\d|20\d\d)\b", r["title"])
    am = []
    for t, _ in r["amend"]:
        m = re.search(r"\(([A-Z][a-z]+)\s+(\d{4})\)", t)
        if m: am.append(f"{m.group(2)}-{MON[m.group(1)[:3]]:02d}")
    latest = max(am) if am else (max(yrs) if yrs else "")
    add(series=r["series"], group=r["group"], code="", title_en=r["title"], title_zh=z.get("title", ""), latest_issue=latest,
        latest_issue_raw=("latest amendment " + max(am)) if am else ("edition year in title" if yrs else "UNVERIFIED (no date on index)"),
        url_en=r["url"], url_zh=z.get("url", ""), languages=[l for l, v in (("en", r["url"]), ("zh-Hant", z.get("url"))) if v],
        amendments=[{"title": t, "url": h} for t, h in r["amend"]], index_page=r["page"],
        zh_match="href" if key(r["url"]) in tck else ("position" if z else "none"))

def zh_ok(r):
    u, t = r.get("url_zh", ""), r.get("title_zh", "")
    if not u or "/doc/en/" in u or u == r.get("url_en"): return False
    if "暫提供英文" in t or "只有英文" in t: return False
    return True
for r in recs:
    r["languages"] = (["en"] if r["url_en"] and "/doc/tc/" not in r["url_en"] else []) + (["zh-Hant"] if zh_ok(r) or "/doc/tc/" in r["url_en"] else [])
    if r["url_en"] and "/doc/tc/" in r["url_en"]: r["note"] = "BD English page links the Chinese PDF only"
    if r["title_zh"] and not re.search(r"[一-鿿]", r["title_zh"]): r["title_zh"] = ""
    r.setdefault("status", "in force")
bundles = [{"part": "ADM", "url": "https://www.bd.gov.hk/doc/en/resources/codes-and-references/practice-notes-and-circular-letters/pnap/ADM/PNAP_ADM_e.zip", "size": "14.5MB"},
           {"part": "APP-1 to 100", "url": "https://www.bd.gov.hk/doc/en/resources/codes-and-references/practice-notes-and-circular-letters/pnap/APP/PNAP_APPa_e.zip", "size": "22.3MB"},
           {"part": "APP-101 to 175", "url": "https://www.bd.gov.hk/doc/en/resources/codes-and-references/practice-notes-and-circular-letters/pnap/APP/PNAP_APPb_e.zip", "size": "75.2MB"},
           {"part": "ADV", "url": "https://www.bd.gov.hk/doc/en/resources/codes-and-references/practice-notes-and-circular-letters/pnap/ADV/PNAP_ADV_e.zip", "size": "71.1MB"}]
pathlib.Path(__file__).with_name("s3_bd_bundles.json").write_text(json.dumps(bundles, indent=1), encoding="utf-8")
OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
import collections
print(len(recs), collections.Counter(r["series"] for r in recs))
print("zh match", collections.Counter(r["zh_match"] for r in recs))
