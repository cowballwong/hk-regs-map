"""S3 PlanD / TPB inventory: TPB Planning Guidelines (EN + TC index pages)."""
import re, json, pathlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fetch import get
OUT = pathlib.Path(__file__).with_name("s3_pland.json")
clean = lambda t: re.sub(r"\s+", " ", t or "").strip()
def rows(lang, page="index.html"):
    u = f"https://www.tpb.gov.hk/{lang}/resources/tpb_guidelines/{page}"; s = BeautifulSoup(get(u), "lxml"); out = {}
    for t in s.find_all("table"):
        for tr in t.find_all("tr"):
            td = tr.find_all("td")
            if len(td) < 3: continue
            code = clean(td[0].get_text()); links = [urljoin(u, a["href"]) for a in tr.find_all("a", href=True)]
            out[re.sub(r"\D*(\d+[A-Z]*)\D*$", r"\1", code.replace(" ", "")) or code] = {"code": code, "title": clean(td[1].get_text(" ")), "url": links[0] if links else "", "links": links, "page": u}
    return out, s
en, _ = rows("en"); tc, _ = rows("tc")
old, _ = rows("en", "old.html")
notice = BeautifulSoup(get("https://www.tpb.gov.hk/en/whats_new/Notices/TPB_Guidelines_Revised_or_Cancelled.html"), "lxml")
ntext = clean((notice.find("main") or notice.body).get_text(" "))
recs = []
for k, r in en.items():
    z = tc.get(k, {})
    recs.append({"department": "PlanD/TPB", "series": "TPB Planning Guideline", "code": r["code"].replace("PG-No.", "PG-No. ").replace("  ", " "),
                 "title_en": r["title"], "title_zh": z.get("title", ""), "latest_issue": "", "latest_issue_raw": "not on index page (UNVERIFIED; date is in the PDF)",
                 "url_en": r["url"], "url_zh": z.get("url", ""), "languages": [l for l, v in (("en", r["url"]), ("zh-Hant", z.get("url"))) if v],
                 "index_page": r["page"], "status": "current (applies to submissions from 1.9.2023)",
                 "mentioned_in_mar2026_notice": bool(re.search(r"\b" + re.escape(k) + r"\b", ntext))})
for r in recs:
    if re.search(r"No\.?\s*(16A|20A|35E)$", r["code"]):
        r["latest_issue"] = "2026-03-06"; r["latest_issue_raw"] = "promulgated 6 March 2026 (TPB notice, March 2026)"
OUT.write_text(json.dumps({"records": recs, "old_set_count": len(old), "old_set_page": "https://www.tpb.gov.hk/en/resources/tpb_guidelines/old.html",
                           "march_2026_notice": ntext[:3000]}, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(recs), "old", len(old), "no zh", sum(1 for r in recs if not r["title_zh"]))
print(ntext[:1500])
