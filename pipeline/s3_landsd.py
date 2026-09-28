"""S3 LandsD inventory: LAO Practice Notes + JPN (EN + TC index pages). Other note series counted only."""
import re, json, pathlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from fetch import get
OUT = pathlib.Path(__file__).with_name("s3_landsd.json")
B = "https://www.landsd.gov.hk/{l}/resources/practice-notes/{p}.html"
clean = lambda t: re.sub(r"\s+", " ", t or "").strip()
fix = lambda base, h: urljoin(base, quote(h, safe="/:%#?=&")) if h else ""

def lao(lang):
    u = B.format(l=lang, p="lao"); s = BeautifulSoup(get(u), "lxml"); out = {}
    for tr in s.find("table").find_all("tr")[1:]:
        td = tr.find_all("td")
        if len(td) < 4: continue
        no = clean(td[0].get_text()); dl = td[2].find("a", href=True)
        subj = clean(re.sub(r"\((Accessible version|無障礙版本)\)", "", td[3].get_text(" ")))
        apps = [clean(a.get_text()) for a in td[4].find_all("a")] if len(td) > 4 else []
        out[no] = {"no": no, "old": clean(td[1].get_text()), "url": fix(u, dl["href"]) if dl else "", "title": subj,
                   "remarks": clean(td[4].get_text(" ")) if len(td) > 4 else "", "appendices": apps, "page": u}
    return out
en, tc = lao("en"), lao("tc")
recs = []
for no, r in en.items():
    z = tc.get(no, {})
    yr = re.search(r"/(\d{4})", no)
    recs.append({"department": "LandsD", "series": "LAO Practice Note", "code": f"LAO PN {no}", "title_en": r["title"], "title_zh": z.get("title", ""),
                 "latest_issue": yr.group(1) if yr else "", "latest_issue_raw": "year from PN number; exact issue date is in the PDF (UNVERIFIED)",
                 "former_number": r["old"], "remarks": r["remarks"], "url_en": r["url"], "url_zh": z.get("url", ""),
                 "languages": [l for l, v in (("en", r["url"]), ("zh-Hant", z.get("url"))) if v], "index_page": r["page"], "status": "listed"})

def jpn(lang):
    u = B.format(l=lang, p="jpn"); s = BeautifulSoup(get(u), "lxml"); out = {}
    for tr in s.find("table").find_all("tr")[1:]:
        td = tr.find_all("td"); a = td[1].find("a", href=True)
        out[clean(td[0].get_text())] = {"title": clean(td[1].get_text(" ")), "url": fix(u, a["href"]) if a else "", "page": u}
    return out
en, tc = jpn("en"), jpn("tc")
for no, r in en.items():
    z = tc.get(no, {})
    recs.append({"department": "LandsD", "series": "JPN (LandsD copy)", "code": f"JPN {no}", "title_en": r["title"], "title_zh": z.get("title", ""),
                 "latest_issue": "", "latest_issue_raw": "not on LandsD index; see BD JPN record", "url_en": r["url"], "url_zh": z.get("url", ""),
                 "languages": [l for l, v in (("en", r["url"]), ("zh-Hant", z.get("url"))) if v], "index_page": r["page"],
                 "duplicate_of": f"BD JPN {no}", "status": "listed"})

counts = {}
for p in ("laco", "smo", "info-notes"):
    s = BeautifulSoup(get(B.format(l="en", p=p)), "lxml")
    counts[p] = sum(len(t.find_all("tr")) - 1 for t in s.find_all("table"))
for r in recs:
    r["title_zh"] = clean(re.sub(r"[（(]無障礙(瀏覽)?版本[）)]", "", r["title_zh"]))
    if not re.search(r"[一-鿿]", r["title_zh"]): r["title_zh"] = ""
    zh = bool(r["url_zh"]) and "/doc/tc/" in r["url_zh"]
    r["languages"] = (["en"] if r["url_en"] else []) + (["zh-Hant"] if zh else [])
    if not zh: r["url_zh"] = ""
OUT.write_text(json.dumps({"records": recs, "not_inventoried_counts": counts}, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(recs), counts, sum(1 for r in recs if not r["title_zh"]), [r for r in recs][:1])
