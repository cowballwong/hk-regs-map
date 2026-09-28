"""S7: extract text for files fetched in S7 -> <work>/text/<id>_<lang>.txt and text/corpus_s7.jsonl.
corpus.jsonl is NOT rewritten (S4 note: rebuilding it drops OCR fields); corpus_s7.jsonl holds new or overriding
records in the same schema. Usage: python s7_extract.py <doc_id> <lang> <pdf_path> [...]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, pathlib, re, sys, hashlib, fitz
TEXT = pathlib.Path(str(WORK / "text")); OUT = TEXT / "corpus_s7.jsonl"
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()
recs = {}
if OUT.exists():
    for l in OUT.read_text(encoding="utf-8").splitlines():
        r = json.loads(l); recs[(r["doc_id"], r["lang"])] = r
args = sys.argv[1:]
for doc, lang, pdf in zip(args[0::3], args[1::3], args[2::3]):
    with fitz.open(pdf) as d:
        pages = [p.get_text("text").replace(chr(12), chr(10)) for p in d]
    txt = "\f".join(pages)
    tp = TEXT / f"{doc}_{lang}.txt"
    chars = len(re.sub(r"\s", "", txt))
    low = [i for i, p in enumerate(pages) if len(re.sub(r"\s", "", p)) < 200]
    scanned = chars / max(1, len(pages)) < 200
    if tp.exists() and not (TEXT / f"{doc}_{lang}_pre_s7.txt").exists():
        tp.replace(TEXT / f"{doc}_{lang}_pre_s7.txt")   # keep the old (wrong) text for audit
    tp.write_text(txt, encoding="utf-8")
    cjk = len(re.findall(r"[\u4e00-\u9fff]", txt)) / max(1, chars)
    recs[(doc, lang)] = {"doc_id": doc, "lang": lang, "pages": len(pages), "chars": chars, "text_path": str(tp).replace("\\", "/"),
        "pdf_path": pdf, "sha256": sha(pdf), "extractor": "pymupdf", "scanned": scanned, "low_text_pages": len(low),
        "cjk_ratio": round(cjk, 3), "source": "s7"}
    print(doc, lang, len(pages), "pages", chars, "chars", "scanned" if scanned else "", f"low pages {len(low)}", f"cjk {cjk:.2f}")
OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs.values()) + "\n", encoding="utf-8")
