"""S8: full-text concept index for the site search (search.js, window.HKSEARCH).

For every concept in data.js (English label, Chinese label, English aliases) it counts how often each
document or legislation provision mentions the term in its FULL TEXT, English and Chinese, and keeps
the node index and the count. Full texts are never shipped: search.js holds only numbers.

Sources (read from HKMAP_WORK, see _paths.py):
  text/corpus.jsonl, text/corpus_s7.jsonl  extracted PDF text per document and language
  raw/legislation/cap_123*_{en,zh-Hant}_c/*.xml  e-Legislation XML, matched to provisions by xpid
Nodes with no source text (stubs, title-only documents) are counted on their titles and summaries.

Matching:
  English: word tokens with light plural folding (balconies = balcony, floors = floor), whole-phrase match.
  Chinese: substring count with all whitespace removed (PDF line breaks split Chinese words).
  A document's count is the highest count in any one of its text files (EN and ZH versions are
  translations of each other, so they are not added together).

Usage: python s8_search_index.py        writes SITE/search.js
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import WORK, SITE
import json, re, glob, collections, time
from pathlib import Path
from lxml import etree

TEXT = WORK / "text"
LEGX = WORK / "raw" / "legislation"
MAX_PER_CONCEPT = 400          # keep the file compact; the top-ranked documents are what a reader scans
LEGK = {"ordinance", "regulation", "part", "division", "schedule", "section", "schedule_section"}
t0 = time.time()

# ---------- data.js ----------
s = (SITE / "data.js").read_text(encoding="utf-8")
D = json.loads(s[s.index("=") + 1: s.rindex("}") + 1])
N, CON = D["nodes"], D["concepts"]
BYID = {n["id"]: i for i, n in enumerate(N)}

# ---------- texts per node ----------
texts = collections.defaultdict(list)          # node index -> [text, ...]
for f in ("corpus.jsonl", "corpus_s7.jsonl"):
    p = TEXT / f
    if not p.exists():
        continue
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        i = BYID.get(r["doc_id"])
        tp = TEXT / Path(r.get("text_path", "")).name       # stored paths are absolute on the build machine
        if i is None or not tp.exists():
            continue
        texts[i].append(tp.read_text(encoding="utf-8", errors="ignore"))

NS = "{http://www.xml.gov.hk/schemas/hklm/1.0}"
xp = {}                                         # xpid -> text (current version preferred)
for f in glob.glob(str(LEGX / "cap_123*_c" / "*.xml")):
    root = etree.parse(f).getroot()
    for e in root.iter(NS + "section", NS + "schedule"):
        pid = e.get("id")
        if not pid:
            continue
        if pid in xp and e.get("endPeriod"):
            continue
        xp[pid] = " ".join(e.itertext())
XP = re.compile(r"[?&]xpid=([^&#]+)")
for i, n in enumerate(N):
    if n["k"] not in ("section", "schedule_section"):
        continue
    for u in (n.get("u"), n.get("uz")):
        m = XP.search(u or "")
        if m and m.group(1) in xp:
            texts[i].append(xp[m.group(1)])

# nodes without source text: titles and summaries stand in
for i, n in enumerate(N):
    if i not in texts and n["k"] in ("document", "document_stub"):
        texts[i].append(" ".join(n.get(k, "") or "" for k in ("te", "tz", "se", "sz")))
# every node also carries its own titles (a short provision may only name the topic in its heading)
for i, n in enumerate(N):
    if n["k"] in ("section", "schedule_section", "document", "document_stub"):
        texts[i].append(" ".join(n.get(k, "") or "" for k in ("te", "tz")))
print(f"texts for {len(texts)} of {len(N)} nodes ({time.time() - t0:.0f}s)")

# ---------- term tables ----------
def fold(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w

TOK = re.compile(r"[a-z0-9]+")
toks = lambda t: [fold(w) for w in TOK.findall(t.lower())]
CJK = re.compile(r"[㐀-鿿]")

en_terms = collections.defaultdict(set)         # first token -> {(tuple, concept)}
zh_terms = []                                   # (term, concept)
for ci, c in enumerate(CON):
    seen = set()
    for t in [c[1]] + list(c[4] or []):
        tt = tuple(toks(t))
        if not tt or tt in seen or (len(tt) == 1 and len(tt[0]) < 3):
            continue
        seen.add(tt)
        en_terms[tt[0]].add((tt, ci))
    z = re.sub(r"\s+", "", c[2] or "")
    if len(z) >= 2 and CJK.search(z):
        zh_terms.append((z, ci))

# ---------- count ----------
count = collections.defaultdict(dict)           # concept -> {node: count}
for i, lst in texts.items():
    best = collections.Counter()
    for t in lst:
        cnt = collections.Counter()
        w = toks(t)
        for k, first in enumerate(w):
            cand = en_terms.get(first)
            if not cand:
                continue
            for tt, ci in cand:
                if tuple(w[k:k + len(tt)]) == tt:
                    cnt[ci] += 1
        if CJK.search(t):
            z = re.sub(r"\s+", "", t)
            for term, ci in zh_terms:
                if term in z:
                    cnt[ci] += z.count(term)
        for ci, v in cnt.items():
            if v > best[ci]:
                best[ci] = v
    for ci, v in best.items():
        count[ci][i] = v
print(f"counted ({time.time() - t0:.0f}s)")

# ---------- write ----------
out, pairs = [], 0
for ci, c in enumerate(CON):
    m = dict(count.get(ci, {}))
    for i in c[3]:                              # AI-tagged documents stay in, even with no literal mention
        m.setdefault(i, 0)
    rows = sorted(m.items(), key=lambda kv: (-kv[1], -(N[kv[0]].get("deg") or 0)))[:MAX_PER_CONCEPT]
    flat = [x for kv in rows for x in kv]
    pairs += len(rows)
    out.append(flat)
js = ("/* HK Building Regulations Map full-text concept index. Built by pipeline/s8_search_index.py. "
      "For each concept (same order as HKMAP.concepts): flat [node index, mentions, ...], most mentions first. */\n"
      "window.HKSEARCH=" + json.dumps({"built": D.get("built"), "nodes": len(N), "c": out}, separators=(",", ":")) + ";\n")
(SITE / "search.js").write_text(js, encoding="utf-8")
print(f"search.js {len(js) / 1024:.0f} KB, {pairs} concept-document pairs ({time.time() - t0:.0f}s)")
for name in ("balcony", "refuge floor", "gross floor area"):
    ci = next((k for k, c in enumerate(CON) if c[1] == name), None)
    if ci is None:
        continue
    f = out[ci]
    by = collections.Counter(N[f[k]]["g"] for k in range(0, len(f), 2))
    print(name, len(f) // 2, dict(by), [(N[f[k]]["c"], f[k + 1]) for k in range(0, min(len(f), 16), 2)])
