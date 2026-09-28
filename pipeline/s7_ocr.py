"""S7: targeted Gemini OCR of garbled pages (same model, prompt and dpi as S4). Hard stop at US$1.
Replaces only the listed pages in <work>/text/<id>_<lang>.txt; the original is kept as <id>_<lang>_pre_s7.txt.
Page cache: <work>/ocr_cache/s7_<id>_<lang>_p<n>.json. Usage: <work>/s7/ocr_usage_s7.json."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, base64, pathlib, time, re, sys
import fitz, requests

KEY = os.environ.get("GOOGLE_AI_API_KEY") or sys.exit("Set the GOOGLE_AI_API_KEY environment variable (Google AI Studio key for Gemini OCR).")
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PRICE_IN, PRICE_OUT, CAP = 0.30e-6, 2.50e-6, 1.00
TEXT = pathlib.Path(str(WORK / "text")); CACHE = pathlib.Path(str(WORK / "ocr_cache"))
USAGE = pathlib.Path(str(WORK / "s7/ocr_usage_s7.json"))
PROMPT = ("Transcribe all the text on this scanned page exactly as it appears, in its original language "
          "(English and/or Traditional Chinese). Keep the line breaks, headings, paragraph and clause numbers, and table contents "
          "(one table row per line, cells separated by tabs). Do not summarise, translate, correct, explain or add anything. "
          "Output only the transcription as plain text. If the page has no text, output nothing.")
tot = json.loads(USAGE.read_text()) if USAGE.exists() else {"prompt": 0, "output": 0, "thoughts": 0, "calls": 0, "pages": [], "cost_usd": 0.0}


PROMPT_JSON = ("Transcribe the text on this scanned page faithfully, in its original language. Output JSON: a list of objects "
               "{\"line\": <line number>, \"text\": <the exact text of that line>}. Tables: one row per object, cells separated by ' | '. "
               "Never pad with spaces. No summary, no translation, no commentary.")
JSON_MODE = "--json" in sys.argv


def ocr_page(png):
    gc = {"temperature": 0.4 if JSON_MODE else 0, "thinkingConfig": {"thinkingBudget": 0}, "maxOutputTokens": 8192}
    if JSON_MODE: gc["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
                                    {"text": PROMPT_JSON if JSON_MODE else PROMPT}]}], "generationConfig": gc}
    for attempt in range(3):
        r = requests.post(URL, params={"key": KEY}, json=body, timeout=180)
        if r.status_code == 200:
            j = r.json(); c = j.get("candidates", [{}])[0]
            return "".join(p.get("text", "") for p in c.get("content", {}).get("parts", [])), j.get("usageMetadata", {}), c.get("finishReason")
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"HTTP {r.status_code} {r.text[:200]}")


def run(doc, lang, pdf, pages_1based):
    tp = TEXT / f"{doc}_{lang}.txt"
    pages = tp.read_text(encoding="utf-8").split("\f")
    backup = TEXT / f"{doc}_{lang}_pre_s7.txt"
    if not backup.exists():
        backup.write_text("\f".join(pages), encoding="utf-8")
    d = fitz.open(pdf)
    for n in pages_1based:
        c = CACHE / f"s7_{doc}_{lang}_p{n}.json"
        if c.exists():
            res = json.loads(c.read_text(encoding="utf-8"))
        else:
            if tot["cost_usd"] >= CAP:
                print("CAP reached, stopping"); return False
            png = d[n - 1].get_pixmap(dpi=150).tobytes("png")
            t, u, fin = ocr_page(png)
            if JSON_MODE and fin == "STOP":
                try: t = chr(10).join(str(o.get("text", "")) for o in json.loads(t))
                except Exception: fin = "BADJSON"
            res = {"text": t, "finish": fin, "prompt": u.get("promptTokenCount", 0), "output": u.get("candidatesTokenCount", 0),
                   "thoughts": u.get("thoughtsTokenCount", 0)}
            c.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            tot["prompt"] += res["prompt"]; tot["output"] += res["output"]; tot["thoughts"] += res["thoughts"]; tot["calls"] += 1
            tot["cost_usd"] = round(tot["prompt"] * PRICE_IN + (tot["output"] + tot["thoughts"]) * PRICE_OUT, 5)
            tot["pages"].append(f"{doc}_{lang}_p{n}")
            USAGE.write_text(json.dumps(tot, indent=1), encoding="utf-8")
            time.sleep(1)
        if res["finish"] not in ("STOP", None) or len(res["text"].strip()) < 20:
            print(f"  keep original {doc} {lang} p{n}: finish={res['finish']} len={len(res['text'])}"); continue
        pages[n - 1] = res["text"]
    tp.write_text("\f".join(pages), encoding="utf-8")
    print(doc, lang, "pages", pages_1based, "cost so far", tot["cost_usd"])
    return True


if __name__ == "__main__":
    jobs = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    for j in jobs:
        if not run(j["doc"], j["lang"], j["pdf"], j["pages"]): break
    print(json.dumps({k: v for k, v in tot.items() if k != "pages"}))
