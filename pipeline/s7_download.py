"""S7: resumable, chunked HTTP Range downloads for the missing documents. HTTP/1.1, polite (>=2.5 s/request)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import time, pathlib, json, sys, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
BD = "https://www.bd.gov.hk/doc"
R = str(WORK / "raw/docs/BD")
JOBS = [
 ("BD_index-statutory-submissions-2", "en", f"{BD}/en/resources/codes-and-references/code-and-design-manuals/BIMSPS_e.pdf", f"{R}/BD-Guideline/BD_index-statutory-submissions-2_en.pdf"),
 ("BD_PNRC-83", "zh", f"{BD}/tc/resources/codes-and-references/practice-notes-and-circular-letters/pnrc/Pnrc83_c.pdf", f"{R}/PNRC/BD_PNRC-83_zh.pdf"),
 ("BD_CL-SC2001Amend2016e", "zh", f"{BD}/tc/resources/codes-and-references/practice-notes-and-circular-letters/circular/CL_SC2001Amend2016c.pdf", f"{R}/BD-Circular-Letter/BD_CL-SC2001Amend2016e_zh.pdf"),
 ("BD_MOA2004e", "zh", f"{BD}/tc/resources/codes-and-references/code-and-design-manuals/MOA2004c.pdf", f"{R}/BD-Code-of-Practice-Design-Manual/BD_MOA2004e_zh.pdf"),
 ("BD_MWTGc", "zh", f"{BD}/tc/resources/codes-and-references/code-and-design-manuals/MW/MWTGc.pdf", f"{R}/BD-Guideline/BD_MWTGc_zh.pdf"),
]
FSDN = "https://www.hkfsd.gov.hk/chi/source/notices"
F = str(WORK / "raw/docs/FSD")
JOBS += [(f"FSD_FPN-No-{n}", "zh", f"{FSDN}/Fire_Protection_Notice_No_{n}.pdf", f"{F}/FSD-Fire-Protection-Notice/FSD_FPN-No-{n}_zh.pdf") for n in (9, 11, 16)]
LD = "https://www.landsd.gov.hk/doc/en/practice-note/lpn"
L = str(WORK / "raw/docs/LandsD/LAO-Practice-Note")
for _id, _f in [("1-2017", "PN%201_2017_text.pdf"), ("6-2026", "PN%206_2026_text.pdf"), ("8-2023", "PN%208_2023_text.pdf"),
                ("9-2025", "PN%209_2025_text.pdf"), ("5-2026", "PN%205_2026_text.pdf"), ("6-2022", "PN%206_2022_text.pdf"),
                ("1-2016", "PN%201-2016_text.pdf"), ("1-2022", "PN%201_2022_text.pdf"), ("10-2023", "PN%2010_2023_text.pdf")]:
    JOBS.append((f"LandsD_LAO-PN-{_id}", "en-access", f"{LD}/{_f}", f"{L}/LandsD_LAO-PN-{_id}_en_accessible.pdf"))
CHUNK = 4 * 1024 * 1024
S = requests.Session(); S.headers.update({"User-Agent": UA})
last = [0.0]
def polite():
    w = 2.5 - (time.time() - last[0])
    if w > 0: time.sleep(w)
    last[0] = time.time()
LOG = pathlib.Path(str(WORK / "s7/download_log.json"))
log = json.loads(LOG.read_text()) if LOG.exists() else {}
def fetch(doc, lang, url, path):
    p = pathlib.Path(path); part = p.with_suffix(p.suffix + ".part")
    if p.exists() and p.stat().st_size > 0: return "exists", p.stat().st_size
    polite(); h = S.head(url, timeout=60, allow_redirects=True)
    print(doc, lang, h.status_code, h.headers.get("Content-Length"), h.headers.get("Accept-Ranges"), flush=True)
    if h.status_code != 200: return f"http {h.status_code}", None
    total = int(h.headers.get("Content-Length", 0))
    have = part.stat().st_size if part.exists() else 0
    fails = 0
    while total == 0 or have < total:
        end = min(have + CHUNK, total) - 1 if total else ""
        polite()
        try:
            r = S.get(url, headers={"Range": f"bytes={have}-{end}"}, timeout=120, stream=True)
            if r.status_code not in (206, 200): raise RuntimeError(f"status {r.status_code}")
            if r.status_code == 200 and have: raise RuntimeError("server ignored Range")
            with open(part, "ab") as f:
                for b in r.iter_content(65536):
                    f.write(b); have += len(b)
            fails = 0
            if total == 0: break
            print(f"  {doc} {have}/{total} ({100*have//max(1,total)}%)", flush=True)
        except Exception as e:
            fails += 1; have = part.stat().st_size if part.exists() else 0
            print(f"  retry {fails}: {e!r}", flush=True)
            if fails > 8: return f"failed at {have}/{total}: {e!r}", have
            time.sleep(5 * fails)
    part.replace(p)
    return "ok", p.stat().st_size
for doc, lang, url, path in JOBS:
    if len(sys.argv) > 1 and doc not in sys.argv[1:]: continue
    st, size = fetch(doc, lang, url, path)
    log[f"{doc}_{lang}"] = {"url": url, "path": path, "state": st, "bytes": size, "at": time.strftime("%Y-%m-%d %H:%M")}
    LOG.write_text(json.dumps(log, indent=1)); print(doc, lang, st, size, flush=True)
