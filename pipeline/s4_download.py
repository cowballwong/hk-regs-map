"""S4 step 1+2: download every document in S3_inventory.json to <work>/raw/docs/<dept>/<series>/.
Polite: one thread per host, >=2.5 s between requests to that host, normal UA, max 2 retries.
PNAPs come from BD's official bundle zips (EN + TC). Resumable: files already on disk are kept.
Writes <work>/raw/docs/manifest.json (one entry per doc per language)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, re, time, pathlib, threading, datetime, zipfile, urllib.parse as up, subprocess, sys
import requests

H = pathlib.Path(__file__).parent
ROOT = pathlib.Path(str(WORK / "raw/docs")); ROOT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
GAP = 2.5
inv = json.loads((H / "S3_inventory.json").read_text(encoding="utf-8"))
DEPT = {"BD": "BD", "LandsD": "LandsD", "PlanD/TPB": "PlanD", "FSD": "FSD"}
BDDOC = "https://www.bd.gov.hk/doc/{l}/resources/codes-and-references/"
OVERRIDE = {  # BD Guideline rows that point at an HTML page anchor, resolved 2026-09-27
    "#BIMGBPS": (BDDOC.format(l="en") + "code-and-design-manuals/BIMGBPS_e.pdf", ""),  # TC page links the EN pdf only
    "#BIMPSPS": (BDDOC.format(l="en") + "code-and-design-manuals/BIMPSPS_e.pdf", BDDOC.format(l="tc") + "code-and-design-manuals/BIMPSPS_c.pdf"),  # guessed; not linked on page
}
BUNDLES = [b["url"] for b in inv["bd_pnap_bundle_zips"]]
BUNDLES += [u.replace("/doc/en/", "/doc/tc/").replace("_e.zip", "_c.zip") for u in BUNDLES]

def slug(s): return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")

def now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def progress(done, status, cur):
    print(f"[S4 {done}] {status}: {cur}", flush=True)

# ---------- build job list ----------
jobs, ids, entries = [], set(), []
for r in inv["records"]:
    dept = DEPT[r["department"]]
    base = r["code"] or pathlib.PurePosixPath(up.urlparse(r["url_en"]).path).stem or slug(r["title_en"])[:40]
    did = f"{dept}_{slug(base)}"
    k = 2
    while did in ids: did = f"{dept}_{slug(base)}-{k}"; k += 1
    ids.add(did)
    e = {"doc_id": did, "dept": dept, "series": r["series"], "code": r["code"], "title_en": r["title_en"], "title_zh": r["title_zh"],
         "status": r["status"], "files": {}}
    ue, uz = r["url_en"], r["url_zh"]
    for key, (a, b) in OVERRIDE.items():
        if ue.endswith(key): ue, uz = a, b
    if r["extra"].get("duplicate_of"):
        e["skip"] = f"duplicate of {r['extra']['duplicate_of']}"
    elif not ue and not uz:
        e["skip"] = "no PDF on index (" + r["status"] + ")"
    else:
        for lang, u in (("en", ue), ("zh", uz)):
            if not u: continue
            if lang == "zh" and u == ue: continue  # same file listed for both languages
            ext = pathlib.PurePosixPath(up.urlparse(u).path).suffix.lower() or ".bin"
            dest = ROOT / dept / slug(r["series"]) / f"{did}_{lang}{ext}"
            f = {"url": u, "path": str(dest).replace("\\", "/"), "state": "todo"}
            e["files"][lang] = f
            jobs.append((up.urlparse(u).netloc, f, r))
    entries.append(e)

# ---------- PNAP bundles ----------
bundle_dir = ROOT / "BD" / "_bundles"; bundle_dir.mkdir(parents=True, exist_ok=True)
from requests.adapters import HTTPAdapter
from urllib3 import HttpVersion
class H11Adapter(HTTPAdapter):  # BD resets HTTP/2 streams on big files; force HTTP/1.1
    def init_poolmanager(self, *a, **kw):
        kw["disabled_svn"] = {HttpVersion.h2, HttpVersion.h3}
        return super().init_poolmanager(*a, **kw)
S = requests.Session(); S.mount("https://", H11Adapter()); S.mount("http://", H11Adapter()); S.headers.update({"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9,zh-HK;q=0.8"})
last = {}; lock = threading.Lock(); stats = {"ok": 0, "cached": 0, "failed": 0, "blocked": 0, "bundle": 0}

def polite_get(host, url, stream=False):
    err = None
    for attempt in range(3):
        wait = GAP - (time.time() - last.get(host, 0))
        if wait > 0: time.sleep(wait)
        try:
            r = S.get(url, timeout=180, stream=stream)
            last[host] = time.time()
            if r.status_code in (404, 410): return r
            if r.status_code >= 500 or r.status_code == 429: err = f"HTTP {r.status_code}"; time.sleep(5); continue
            return r
        except Exception as ex:
            last[host] = time.time(); err = repr(ex)[:200]; time.sleep(5)
    raise RuntimeError(err)

BUNDLE_FAIL = []
def fetch_bundles():
    names = {}
    for u in BUNDLES:
        z = bundle_dir / u.rsplit("/", 1)[1]
        for attempt in range(3):
            if z.exists() and z.stat().st_size > 1000: break
            try:
                r = polite_get("www.bd.gov.hk", u, stream=True)
                print(f"[{r.status_code}] {u}", flush=True)
                if r.status_code != 200: break
                tmp = z.with_suffix(".part")
                with open(tmp, "wb") as fh:
                    for ch in r.iter_content(1 << 20): fh.write(ch)
                zipfile.ZipFile(tmp).close()  # validates the archive
                tmp.replace(z)
            except Exception as ex:
                print("bundle retry", attempt, u, repr(ex)[:120], flush=True); time.sleep(10)
        if not z.exists(): BUNDLE_FAIL.append(u); continue
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                lang = "tc" if z.stem.endswith("_c") else "en"
                if n.lower().endswith(".pdf"): names[(lang, pathlib.PurePosixPath(n).name.lower())] = (z, n)
    return names

def looks_blocked(b, ctype):
    t = b[:20000].decode("utf-8", "ignore").lower()
    return ("captcha" in t or "cf-chl" in t or "checking your browser" in t or "just a moment" in t
            or "access denied" in t or "request rejected" in t)

def do_file(host, f, bundle_names):
    dest = pathlib.Path(f["path"])
    if dest.exists() and dest.stat().st_size > 0:
        f["state"] = f.get("state_ok", "ok"); f["bytes"] = dest.stat().st_size
        with lock: stats["cached"] += 1
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    name = up.unquote(f["url"].rsplit("/", 1)[1]).lower()
    key = ("tc" if "/doc/tc/" in f["url"] else "en", name)
    if "/pnap/" in f["url"] and key in bundle_names:
        z, n = bundle_names[key]
        with zipfile.ZipFile(z) as zf: dest.write_bytes(zf.read(n))
        f["state"] = f["state_ok"] = "ok"; f["source"] = "bundle:" + z.name; f["bytes"] = dest.stat().st_size
        with lock: stats["bundle"] += 1
        return
    try:
        r = polite_get(host, f["url"])
    except Exception as ex:
        f["state"] = "failed"; f["error"] = str(ex)
        with lock: stats["failed"] += 1
        return
    b = r.content; ctype = r.headers.get("Content-Type", "")
    if r.status_code != 200:
        f["state"] = "failed"; f["error"] = f"HTTP {r.status_code}"
        with lock: stats["failed"] += 1
        return
    is_pdf_url = f["url"].lower().endswith(".pdf")
    if is_pdf_url and not b[:1024].lstrip().startswith(b"%PDF"):
        if looks_blocked(b, ctype):
            f["state"] = "blocked"; f["error"] = "browser-check / block page"
            with lock: stats["blocked"] += 1
        else:
            f["state"] = "failed"; f["error"] = f"not a PDF ({ctype}, {len(b)} bytes)"
            with lock: stats["failed"] += 1
        return
    dest.write_bytes(b)
    f["state"] = f["state_ok"] = "ok"; f["source"] = "direct"; f["bytes"] = len(b)
    with lock: stats["ok"] += 1

def save_manifest():
    with lock:
        (ROOT / "manifest.json").write_text(json.dumps({"updated": now(), "entries": entries}, ensure_ascii=False, indent=1), encoding="utf-8")

def host_worker(host, hjobs, bundle_names, counter):
    for i, (h, f, r) in enumerate(hjobs, 1):
        do_file(host, f, bundle_names)
        counter[host] = i
        if i % 25 == 0: save_manifest()

if __name__ == "__main__":
    by_host = {}
    for h, f, r in jobs: by_host.setdefault(h, []).append((h, f, r))
    print({h: len(v) for h, v in by_host.items()}, flush=True)
    counter = {h: 0 for h in by_host}
    bd_total = len(by_host.get("www.bd.gov.hk", []))
    other_total = sum(len(v) for h, v in by_host.items() if h != "www.bd.gov.hk")
    steps = [0]

    # non-BD hosts start at once; BD starts after bundles
    threads = {}
    for h, v in by_host.items():
        if h == "www.bd.gov.hk": continue
        t = threading.Thread(target=host_worker, args=(h, v, {}, counter)); t.start(); threads[h] = t
    def bd_run():
        names = fetch_bundles()
        print("bundle pdfs:", len(names), flush=True)
        host_worker("www.bd.gov.hk", by_host["www.bd.gov.hk"], names, counter)
    tb = threading.Thread(target=bd_run); tb.start()

    last_report = time.time(); bd_marked = other_marked = False
    while True:
        time.sleep(15)
        bd_done = not tb.is_alive(); other_done = all(not t.is_alive() for t in threads.values())
        if bd_done and not bd_marked:
            bd_marked = True; steps[0] += 1; save_manifest()
            ok = sum(1 for e in entries if e["dept"] == "BD" and any(f["state"] == "ok" for f in e["files"].values()))
            sk = sum(1 for e in entries if e["dept"] == "BD" and e.get("skip"))
            progress(steps[0], "running", f"屋宇署 {ok} 份文件下載完，跳過 {sk} 份冇 PDF")
        if other_done and not other_marked:
            other_marked = True; steps[0] += 1; save_manifest()
            n = sum(1 for e in entries if e["dept"] != "BD" and any(f["state"] == "ok" for f in e["files"].values()))
            progress(steps[0], "running", f"地政總署、規劃署、消防處共 {n} 份文件下載完")
        if bd_done and other_done: break
        if time.time() - last_report > 600:
            last_report = time.time(); save_manifest()
            bdn = counter.get("www.bd.gov.hk", 0); on = sum(v for h, v in counter.items() if h != "www.bd.gov.hk")
            progress(steps[0], "running", f"下載緊：屋宇署 {bdn}/{bd_total} 個檔，其他部門 {on}/{other_total} 個檔")
        print(now(), counter, stats, flush=True)
    save_manifest()
    print("DONE", stats, flush=True)
