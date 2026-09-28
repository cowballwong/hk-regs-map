"""S3 FSD inventory: CoP for Minimum FSI&E (edition history), circular letters (current + obsolete + old), technical guidance, fire protection notices."""
import re, json, pathlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fetch import get
OUT = pathlib.Path(__file__).with_name("s3_fsd.json")
B = "https://www.hkfsd.gov.hk/{l}/fire_protection/notices/{p}"
clean = lambda t: re.sub(r"\s+", " ", (t or "").replace("", "–")).strip()
def dmy(d):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", d or ""); return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else d

def divrows(lang, page):
    u = B.format(l=lang, p=page); s = BeautifulSoup(get(u), "lxml"); out = []
    for c in s.select("div.content div.row"):
        cols = c.find_all("div", recursive=False)
        if len(cols) < 2: continue
        a = c.find("a", href=True)
        out.append({"cols": [clean(x.get_text(" ")) for x in cols], "url": urljoin(u, a["href"]) if a else "", "page": u})
    return out

recs = []
def add(**k): recs.append({"department": "FSD", **k})
def langs(en, zh): return [l for l, v in (("en", en), ("zh-Hant", zh)) if v]

for page, status in (("circular.html", "current"), ("circular_obs.html", "obsolete"), ("circular_old.html", "old (archive list)")):
    en, tc = divrows("eng", page), divrows("chi", page)
    def num(r):
        m = re.match(r"(\d+/\d{2,4})", r["cols"][1] if len(r["cols"]) > 2 else r["cols"][0]); return m.group(1) if m else None
    tcn = {num(r): r for r in tc if num(r)}
    for r in en:
        if len(r["cols"]) < 3 or not r["url"]: continue
        n = num(r); z = tcn.get(n, {})
        subj = re.sub(r"^\d+/\d{2,4}\s*-\s*", "", r["cols"][1])
        zsubj = re.sub(r"^\d+/\d{2,4}\s*-\s*", "", z["cols"][1]) if z else ""
        add(series="FSD Circular Letter", code=f"FSD CL {n}" if n else "", title_en=subj, title_zh=zsubj,
            latest_issue=dmy(r["cols"][0]), latest_issue_raw=r["cols"][0], url_en=r["url"], url_zh=z.get("url", ""),
            languages=langs(r["url"], z.get("url")), index_page=r["page"], status=status)

for page, series in (("guidance.html", "FSD Technical Guidance"),):
    en, tc = divrows("eng", page), divrows("chi", page)
    en = [r for r in en if r["url"]]; tc = [r for r in tc if r["url"]]
    for i, r in enumerate(en):
        z = tc[i] if i < len(tc) else {}
        add(series=series, code="", title_en=r["cols"][0], title_zh=z.get("cols", [""])[0], latest_issue="", latest_issue_raw="not on index (UNVERIFIED)",
            url_en=r["url"], url_zh=z.get("url", ""), languages=langs(r["url"], z.get("url")), index_page=r["page"], zh_match="position", status="current")

def cop(lang):
    u = B.format(l=lang, p="code.html"); s = BeautifulSoup(get(u), "lxml")
    body = clean((s.find("main") or s.body).get_text(" "))
    m = re.search(r"(Codes of Practice for Minimum .*?Equipment|最低限度之消防裝置及設備.*?保養)\s*\[", body)
    h1 = m.group(1) if m else ""
    rows = [(clean(tr.find_all("td")[0].get_text()), clean(tr.find_all("td")[1].get_text()), urljoin(u, tr.find("a")["href"]) if tr.find("a") else "")
            for tr in s.find("table").find_all("tr") if len(tr.find_all("td")) >= 2]
    return h1, rows, u
h_en, en, u = cop("eng"); h_zh, zh, _ = cop("chi")
latest = en[-1]; zl = zh[-1] if zh else ("", "", "")
add(series="FSD Code of Practice", code="CoP Minimum FSI&E", title_en=h_en, title_zh=h_zh, latest_issue=latest[0], latest_issue_raw=f"{latest[0]} ({latest[1]})",
    url_en=latest[2], url_zh=zl[2], languages=langs(latest[2], zl[2]), index_page=u, status="current",
    editions=[{"date": d, "version": v, "url": h} for d, v, h in en])

# Fire Protection Notices and other PDFs linked from the notices hub
u = B.format(l="eng", p=""); s = BeautifulSoup(get(u), "lxml")
for a in s.find_all("a", href=True):
    h = urljoin(u, a["href"])
    if re.search(r"Fire_Protection_Notice_No_(\d+)", h):
        n = re.search(r"No_(\d+)", h).group(1)
        add(series="FSD Fire Protection Notice", code=f"FPN No. {n}", title_en=clean(a.get_text(" ")) or f"Fire Protection Notice No. {n}", title_zh="",
            latest_issue="", latest_issue_raw="not on index (UNVERIFIED)", url_en=h, url_zh="", languages=["en"], index_page=u, status="current")
OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
import collections
print(len(recs), collections.Counter((r["series"], r["status"]) for r in recs))
print("no zh", collections.Counter(r["series"] for r in recs if not r["title_zh"]))
print(recs[0]); print([r for r in recs if r["series"]=="FSD Code of Practice"][0]["title_en"], "|", [r for r in recs if r["series"]=="FSD Code of Practice"][0]["title_zh"])
