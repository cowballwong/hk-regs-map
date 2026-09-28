"""S4 step 3: extract text from every downloaded file to <work>/text/<doc_id>_<lang>.txt (pages split by \\f)
and write <work>/text/corpus.jsonl. Scanned = under 200 chars/page on average -> "ocr": "pending"."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, re, hashlib, pathlib, subprocess, sys, datetime
import fitz

ROOT = pathlib.Path(str(WORK / "raw/docs")); OUT = pathlib.Path(str(WORK / "text")); OUT.mkdir(parents=True, exist_ok=True)
man = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
MON = {m.lower(): i for i, m in enumerate("January February March April May June July August September October November December".split(), 1)}
MON.update({k[:3]: v for k, v in list(MON.items())}); MON["sept"] = 9
CN = {c: i for i, c in enumerate("〇一二三四五六七八九")}; CN["零"] = 0; CN["○"] = 0; CN["Ｏ"] = 0; CN["０"] = 0

def cnnum(s):
    if s.isdigit(): return int(s)
    if "十" in s:
        a, _, b = s.partition("十"); return (CN.get(a, 1) if a else 1) * 10 + (CN.get(b, 0) if b else 0)
    return int("".join(str(CN[c]) for c in s)) if all(c in CN for c in s) else None

MN = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
PATS = [
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + MN + r",?\s+((?:19|20)\d\d)\b", re.I), lambda m: (int(m[3]), MON[m[2].lower().rstrip('.')[:4] if m[2].lower().startswith('sept') else m[2].lower()[:3]], int(m[1]))),
    (re.compile(MN + r"\s+(\d{1,2}),\s+((?:19|20)\d\d)\b", re.I), lambda m: (int(m[3]), MON[m[1].lower()[:4] if m[1].lower().startswith('sept') else m[1].lower()[:3]], int(m[2]))),
    (re.compile(r"\b(\d{1,2})[./](\d{1,2})[./]((?:19|20)\d\d)\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"((?:19|20)\d\d|[二一][〇零○０一二三四五六七八九]{3})\s*年\s*([\d一二三四五六七八九十]{1,3})\s*月\s*([\d一二三四五六七八九十]{1,3})\s*日"), lambda m: (cnnum(m[1]), cnnum(m[2]), cnnum(m[3]))),
]
LABEL = re.compile(r"(date|dated|issued|日期)", re.I)

def first_page_date(t):
    """Return YYYY-MM-DD only if page 1 has one labelled date or exactly one distinct full date; else None."""
    found = []
    for rx, fn in PATS:
        for m in rx.finditer(t):
            try:
                y, mo, d = fn(m)
                dt = datetime.date(y, mo, d)
            except Exception:
                continue
            if 1950 <= y <= 2026 and dt <= datetime.date(2026, 9, 27):
                found.append((m.start(), dt))
    if not found: return None
    labelled = [dt for pos, dt in found if LABEL.search(t[max(0, pos - 25):pos])]
    if len(set(labelled)) == 1: return labelled[0].isoformat()
    if len({dt for _, dt in found}) == 1: return found[0][1].isoformat()
    return None

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()

def extract(path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        with fitz.open(path) as d:
            return [p.get_text("text").replace(chr(12), chr(10)) for p in d], "pymupdf"  # form feed kept for page breaks only
    if ext == ".rtf":
        from striprtf.striprtf import rtf_to_text
        raw = path.read_bytes().decode("cp1252", "replace")
        return [rtf_to_text(raw, errors="ignore")], "striprtf"
    if ext == ".doc":
        r = subprocess.run(["antiword", "-w", "0", str(path)], capture_output=True)
        return [r.stdout.decode("utf-8", "replace")], "antiword"
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        pages = []
        for ws in wb.worksheets:
            rows = ["\t".join("" if c is None else str(c) for c in row) for row in ws.iter_rows(values_only=True)]
            pages.append(f"[sheet {ws.title}]\n" + "\n".join(r for r in rows if r.strip()))
        return pages, "openpyxl"
    return None, None

recs, errors = [], []
for e in man["entries"]:
    for lang, f in e["files"].items():
        if f.get("state") != "ok": continue
        p = pathlib.Path(f["path"])
        try:
            pages, how = extract(p)
        except Exception as ex:
            errors.append((e["doc_id"], lang, repr(ex)[:200])); continue
        if pages is None:
            errors.append((e["doc_id"], lang, "no extractor for " + p.suffix)); continue
        text = "\f".join(pages)
        tp = OUT / f"{e['doc_id']}_{lang}.txt"; tp.write_text(text, encoding="utf-8")
        chars = len(re.sub(r"\s", "", text)); n = len(pages)
        rec = {"doc_id": e["doc_id"], "dept": e["dept"], "series": e["series"], "code": e["code"], "lang": lang,
               "pages": n if how in ("pymupdf",) else None, "chars": chars, "text_path": str(tp).replace("\\", "/"),
               "pdf_path": f["path"], "sha256": sha(p), "extractor": how}
        d = first_page_date(pages[0][:4000]) if pages else None
        rec["issue_date"] = d; rec["date_source"] = "pdf-first-page" if d else None
        if how == "pymupdf" and n and chars / n < 200:
            rec["scanned"] = True; rec["ocr"] = "pending"
        recs.append(rec)
with open(OUT / "corpus.jsonl", "w", encoding="utf-8") as fh:
    for r in recs: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
(OUT / "extract_errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=1), encoding="utf-8")
print("records", len(recs), "errors", len(errors), "scanned", sum(1 for r in recs if r.get("scanned")))
print("pages", sum(r["pages"] or 0 for r in recs), "chars", sum(r["chars"] for r in recs))
print("dated", sum(1 for r in recs if r["issue_date"]))
