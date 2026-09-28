"""Polite fetcher: >=2.5 s between requests, normal UA, cached under <work>/raw/pages."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import time, hashlib, pathlib, sys, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
CACHE = pathlib.Path(str(WORK / "raw/pages")); CACHE.mkdir(parents=True, exist_ok=True)
_last = [0.0]
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9,zh-HK;q=0.8"})
def get(url, binary=False, cache=True):
    f = CACHE / hashlib.md5(url.encode()).hexdigest()
    if cache and f.exists():
        b = f.read_bytes(); return b if binary else b.decode("utf-8", "replace")
    wait = 2.5 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    r = S.get(url, timeout=60); _last[0] = time.time()
    print(f"[{r.status_code}] {url}", file=sys.stderr)
    r.raise_for_status()
    f.write_bytes(r.content)
    if binary: return r.content
    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower()=="iso-8859-1" else r.encoding
    return r.text
