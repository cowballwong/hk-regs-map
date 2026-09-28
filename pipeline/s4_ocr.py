"""S4 step 4a: OCR the scanned texts in corpus.jsonl with Gemini 2.5 Flash (REST generateContent), one page per call,
page images at 150 dpi. Faithful transcription only. Hard stop at US$6 running cost. Resumable via per-page cache."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, base64, pathlib, time, threading, re, sys
from concurrent.futures import ThreadPoolExecutor
import fitz, requests

KEY = os.environ.get("GOOGLE_AI_API_KEY") or sys.exit("Set the GOOGLE_AI_API_KEY environment variable (Google AI Studio key for Gemini OCR).")
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PRICE_IN, PRICE_OUT, CAP = 0.30e-6, 2.50e-6, 6.00
CORPUS = pathlib.Path(str(WORK / "text/corpus.jsonl")); CACHE = pathlib.Path(str(WORK / "ocr_cache"))
PROMPT = ("Transcribe all the text on this scanned page exactly as it appears, in its original language "
          "(English and/or Traditional Chinese). Keep the line breaks, headings, paragraph and clause numbers, and table contents "
          "(one table row per line, cells separated by tabs). Do not summarise, translate, correct, explain or add anything. "
          "Output only the transcription as plain text. If the page has no text, output nothing.")
lock = threading.Lock(); tot = {"prompt": 0, "output": 0, "thoughts": 0, "calls": 0, "cost": 0.0}; stop = [False]

PROMPT_JSON = ("Transcribe the text on this scanned page faithfully, in its original language. Output JSON: a list of objects "
               "{\"line\": <line number>, \"text\": <the exact text of that line>}. Tables: one row per object, cells separated by ' | '. "
               "Never pad with spaces. No summary, no translation, no commentary.")

def ocr_page(png, json_mode=False):
    gc = {"temperature": 0.4 if json_mode else 0, "thinkingConfig": {"thinkingBudget": 0}, "maxOutputTokens": 8192}
    if json_mode: gc["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
                                    {"text": PROMPT_JSON if json_mode else PROMPT}]}], "generationConfig": gc}
    err = None
    for attempt in range(3):
        try:
            r = requests.post(URL, params={"key": KEY}, json=body, timeout=180)
            if r.status_code == 200:
                j = r.json(); u = j.get("usageMetadata", {})
                c = j.get("candidates", [{}])[0]
                text = "".join(p.get("text", "") for p in c.get("content", {}).get("parts", []))
                return text, u, c.get("finishReason")
            err = f"HTTP {r.status_code} {r.text[:200]}"
            time.sleep(10 * (attempt + 1))
        except Exception as ex:
            err = repr(ex)[:200]; time.sleep(10)
    raise RuntimeError(err)

def do_page(rec, i):
    d = CACHE / f"{rec['doc_id']}_{rec['lang']}"; d.mkdir(parents=True, exist_ok=True)
    f = d / f"p{i + 1:03d}.json"
    res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    if res and (res.get("finish") == "STOP" or res.get("retry")): return res
    if stop[0]: return res
    with fitz.open(rec["pdf_path"]) as doc: png = doc[i].get_pixmap(dpi=150).tobytes("png")
    p = o = t = 0
    if res is None:
        try:
            text, u, fin = ocr_page(png)
        except Exception as ex:
            return {"text": "", "error": str(ex)}
        p, o, t = u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), u.get("thoughtsTokenCount", 0)
        res = {"text": text, "finish": fin, "prompt": p, "output": o, "thoughts": t}
    if res["finish"] != "STOP":  # RECITATION / MAX_TOKENS: retry once as JSON lines
        try:
            jt, u, fin2 = ocr_page(png, json_mode=True)
            p2, o2, t2 = u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), u.get("thoughtsTokenCount", 0)
            p += p2; o += o2; t += t2
            res["prompt"] += p2; res["output"] += o2; res["thoughts"] += t2
            res["retry"] = "json"; res["finish_retry"] = fin2
            if fin2 == "STOP":
                res["text"] = chr(10).join(str(x.get("text", "")) for x in json.loads(jt))
        except Exception as ex:
            res["retry"] = "json"; res["retry_error"] = repr(ex)[:200]
    with lock:
        tot["prompt"] += p; tot["output"] += o; tot["thoughts"] += t; tot["calls"] += 1
        tot["cost"] = tot["prompt"] * PRICE_IN + (tot["output"] + tot["thoughts"]) * PRICE_OUT
        if tot["cost"] >= CAP: stop[0] = True
    f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res

recs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
todo = [(r, i) for r in recs if (r.get("scanned") or r.get("garbled_font")) for i in range(r["pages"])]
print("pages to OCR", len(todo), flush=True)
for c in CACHE.glob("*/p*.json"):  # count spend already in the cache toward the cap
    d = json.loads(c.read_text(encoding="utf-8")); tot["prompt"] += d.get("prompt", 0); tot["output"] += d.get("output", 0); tot["thoughts"] += d.get("thoughts", 0)
tot["cost"] = tot["prompt"] * PRICE_IN + (tot["output"] + tot["thoughts"]) * PRICE_OUT
print("already spent", round(tot["cost"], 4), flush=True)
results = {}
with ThreadPoolExecutor(4) as ex:
    futs = {ex.submit(do_page, r, i): (r["doc_id"], r["lang"], i) for r, i in todo}
    for n, fu in enumerate(futs, 1):
        results[futs[fu]] = fu.result()
        if n % 50 == 0: print(n, tot, flush=True)
# totals including cached pages
agg = {"prompt": 0, "output": 0, "thoughts": 0, "pages_ok": 0, "pages_failed": 0, "finish_other": []}
for r in recs:
    if not (r.get("scanned") or r.get("garbled_font")): continue
    pages, fails, tok = [], 0, 0
    for i in range(r["pages"]):
        res = results.get((r["doc_id"], r["lang"], i))
        if not res or res.get("error"): fails += 1; pages.append(""); continue
        agg["prompt"] += res["prompt"]; agg["output"] += res["output"]; agg["thoughts"] += res["thoughts"]
        tok += res["prompt"] + res["output"] + res["thoughts"]
        if res.get("finish") not in ("STOP", None) and res.get("finish_retry") != "STOP": agg["finish_other"].append((r["doc_id"], r["lang"], i + 1, res["finish"]))
        pages.append(res["text"])
    agg["pages_ok"] += r["pages"] - fails; agg["pages_failed"] += fails
    agg["pages_retried_json"] = agg.get("pages_retried_json", 0) + sum(1 for i in range(r["pages"]) if (results.get((r["doc_id"], r["lang"], i)) or {}).get("retry"))
    if fails == r["pages"]: continue  # nothing usable, keep "pending"
    tp = pathlib.Path(r["text_path"])
    orig = tp.with_name(tp.stem + "_pymupdf.txt")
    if not orig.exists(): orig.write_text(tp.read_text(encoding="utf-8"), encoding="utf-8")
    text = "\f".join(pages); tp.write_text(text, encoding="utf-8")
    r["chars"] = len(re.sub(r"\s", "", text)); r["ocr"] = "gemini"; r["ocr_model"] = "gemini-2.5-flash"
    r["ocr_tokens"] = tok; r["ocr_pages_failed"] = fails
with open(CORPUS, "w", encoding="utf-8") as fh:
    for r in recs: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
agg["cost_usd"] = round(agg["prompt"] * PRICE_IN + (agg["output"] + agg["thoughts"]) * PRICE_OUT, 4)
agg["stopped_at_cap"] = stop[0]
pathlib.Path(str(WORK / "text/ocr_usage.json")).write_text(json.dumps(agg, ensure_ascii=False, indent=1), encoding="utf-8")
print("DONE", json.dumps(agg, ensure_ascii=False)[:1500])
