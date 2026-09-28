"""S6: turn graph/graph.json + graph/concepts.json into the site folder data.js (window.HKMAP), compact, no fetch needed.
Usage: python s6_build_data.py
Node fields (short keys): id, k kind, g group (dept or LEG/EXT), c display code, te/tz titles, se/sz summaries, dm domain
(documents: given; legislation: inferred from citing documents, marked dmi=1), sb subjects, dt date, sr series, st status,
u/uz urls, cf confidence, pa parent index, nt note, deg solid-citation degree, h hub rank (1..N for top hubs).
Edge: s,t indices; y type; q/qz quotes; p/pz pages; pin; f faint; b basis; ix index flag.
Bridge: s,t, re/rz reasons, es/et evidence, cf.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, re, collections as C
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "graph/graph_final.json" if (HERE / "graph/graph_final.json").exists() else HERE / "graph/graph.json"  # S7: merged graph
G = json.loads(SRC.read_text(encoding="utf-8"))
CO = json.loads((HERE / "graph/concepts.json").read_text(encoding="utf-8"))
OUT = SITE / "data.js"
OUT.parent.mkdir(parents=True, exist_ok=True)

nodes = G["nodes"]
idx = {n["id"]: i for i, n in enumerate(nodes)}
LEGK = {"ordinance", "regulation", "part", "division", "schedule", "section", "schedule_section"}
SERIES_SHORT = {"BD Circular Letter": "BD Circular", "FSD Circular Letter": "FSD Circular", "BD Code of Practice / Design Manual": "BD CoP",
                "BD Guideline": "BD Guideline", "TPB Planning Guideline": "TPB PG", "LAO Practice Note": "LAO PN"}


def group(n):
    if n["kind"] in LEGK:
        return "LEG"
    if n["kind"] == "external_ordinance":
        return "EXT"
    return n.get("dept") or "BD"


SHORT = {  # the names practitioners actually use for BD codes and guidelines that carry no reference number
    "BD_fs-code2011": "FS Code 2011", "BD_BFA2008-e": "Design Manual BFA 2008", "BD_MOE1996-e": "MOE Code 1996",
    "BD_MOA2004e": "MOA Code 2004", "BD_FRC1996-e": "FRC Code 1996", "BD_OTTV1995-e": "OTTV Code 1995",
    "BD_BWLE2020e": "Lifts & Escalators Code 2011", "BD_cop-on-access-for-external-maintenance-2021": "External Maintenance Code 2021",
    "BD_Demolition-e2004": "Demolition Code 2004", "BD_SS2009-e": "Site Supervision Code 2009", "BD_TMSS2009-e": "TM Supervision Plans 2009",
    "BD_DIL2011e": "Loads Code 2011", "BD_FoundationCode2017": "Foundations Code 2017", "BD_cppcc2016e": "Precast Concrete Code 2016",
    "BD_CoP-SUC2013e": "Concrete Code 2013", "BD_SUG2018e": "Glass Code 2018", "BD_SUOS2011": "Steel Code 2011",
    "BD_EMSUOS2011e": "Steel Code 2011 (EM)", "BD_WindEffects2019e": "Wind Code 2019", "BD_ExplanatoryNotesWindEffects2019e": "Wind Code 2019 (EN)",
    "BD_CoP-MBIS-MWISe": "MBIS / MWIS Code", "BD_Osi-1992": "Oil Storage Code 1992", "BD_Fsdfc-1994": "Caverns Fire Guide 1994",
    "BD_Guidelines-DCREERB2014e": "Residential EE Guidelines 2014", "BD_MWGGe": "Minor Works General Guidelines",
    "BD_MWTGc": "Minor Works Technical Guidelines", "BD_heritage-2021": "Heritage Buildings Guidebook", "BD_GDCBS": "Bamboo Scaffolds Guidelines",
    "BD_IG-ISDWe": "Default Works Surcharge Guidelines", "BD_dev0620cb1-2487-1-AnnexG-e": "UBW Prioritisation Guidelines",
    "BD_GWS-3": "Water Seepage Guidelines", "BD_GWS": "Water Seepage Guidelines 2005", "BD_Drainage-System-Guideline-Eng": "Drainage Maintenance Guidelines",
    "BD_Ad-Signs-E": "Advertising Signs Guide", "BD_Guide-signboards-e": "Abandoned Signboards Guide", "BD_BDG-ENG": "Building Maintenance Guidebook",
    "BD_IGG-e": "Greening Guide", "BD_index-statutory-submissions": "BIM GBP Guidelines 2019", "BD_index-statutory-submissions-2": "BIM Statutory Plans 2023",
    "FSD_TG-BS5839-1-eng": "FSD TG BS 5839-1", "FSD_Technical-Guidance-BS5266-2016-BSEN1838-2013": "FSD TG BS 5266-1",
    "FSD_Technical-Guidance-LPC-Rules-eng-20200911-153808": "FSD TG LPC Rules",
}


def code(n):
    k = n["kind"]
    if n.get("code"):
        return n["code"]
    if n["id"] in SHORT:
        return SHORT[n["id"]]
    if n.get("series") == "BD Circular Letter":
        return f"BD Circular {(n.get('date') or '')[:7]}".strip()
    if k == "part" or k == "division":
        return n["id"].replace(" > ", " ")
    if k == "schedule":
        return f"Cap {n.get('cap')} {n.get('num') or n['id']}"
    if k == "document":
        s = SERIES_SHORT.get(n.get("series"), n.get("series") or "Doc")
        return f"{s} {n.get('date') or ''}".strip()
    return n["id"]


# ---------- degree (solid citations, not the legislation tree) ----------
S, D = G["edges"]["solid"], G["edges"]["dashed"]
deg = C.Counter()
for e in S:
    w = 0.3 if e.get("faint") else 1
    deg[e["s"]] += w
    deg[e["t"]] += w

# ---------- infer a domain for non-document nodes from what cites them ----------
dom = {n["id"]: n.get("domain") for n in nodes if n.get("domain")}
votes = C.defaultdict(C.Counter)
for e in S:
    for a, b in ((e["s"], e["t"]), (e["t"], e["s"])):
        if a not in dom and b in dom:
            votes[a][dom[b]] += 1
inf = {k: v.most_common(1)[0][0] for k, v in votes.items()}
children = C.defaultdict(list)
for n in nodes:
    if n.get("parent"):
        children[n["parent"]].append(n["id"])
# up: parents take children's majority; then down: children without a vote inherit
for _ in range(4):
    for n in nodes:
        i = n["id"]
        if i in dom or i in inf:
            continue
        c = C.Counter(inf[x] for x in children.get(i, []) if x in inf)
        if c:
            inf[i] = c.most_common(1)[0][0]
for _ in range(6):
    for n in nodes:
        i = n["id"]
        if i not in dom and i not in inf and n.get("parent") in inf:
            inf[i] = inf[n["parent"]]

# ---------- nodes ----------
out_nodes = []
for n in nodes:
    k = n["kind"]
    o = {"id": n["id"], "k": k, "g": group(n), "c": code(n)}
    for src, dst in (("title_en", "te"), ("title_zh", "tz"), ("summary_en", "se"), ("summary_zh", "sz"), ("date", "dt"),
                     ("series", "sr"), ("status", "st"), ("url_en", "u"), ("url_zh", "uz"), ("confidence", "cf"), ("note", "nt"),
                     ("in_force_from", "iff"), ("version_date", "vd")):
        if n.get(src):
            o[dst] = n[src]
    if o.get("uz") == o.get("u"):
        o.pop("uz", None)
    if n.get("subjects"):
        o["sb"] = n["subjects"]
    if n.get("missing_lang"):
        o["ml"] = n["missing_lang"]
    if n.get("domain"):
        o["dm"] = n["domain"]
    elif n["id"] in inf:
        o["dm"] = inf[n["id"]]
        o["dmi"] = 1
    if n.get("parent") in idx:
        o["pa"] = idx[n["parent"]]
    o["deg"] = round(deg.get(n["id"], 0), 1)
    # ---- S7 fields: QA basis, superseded / duplicate / cancelled (drawn faded), language availability, series ----
    if n.get("qa") in ("no-source-text", "no-text-title-only") or n.get("title_only_stub") or (k == "document" and n.get("has_text") is False):
        o["qt"] = 1  # the panel shows "Summary from title only", so the summary's own sentence saying so is dropped
        for f, t in (("se", " No text was available, so this description is based on the title only."), ("sz", "由於沒有可用文本，此描述只根據標題撰寫。")):
            if o.get(f):
                o[f] = o[f].replace(t, "").strip()
    st = str(n.get("status") or "").lower()
    if st in ("superseded", "repealed", "obsolete", "omitted") or st.startswith("cancelled") or n.get("duplicate_of"):
        o["fd"] = 1
    for src, dst in (("superseded_by", "sby"), ("duplicate_of", "dup"), ("counterpart_of", "cpo"), ("chinese_version_of", "cvo"), ("attachment_of", "ato")):
        if n.get(src) in idx:
            o[dst] = idx[n[src]]
    for src, dst in (("status_date", "sdt"), ("legacy_scope", "lgs"), ("effective_date", "efd")):
        if n.get(src):
            o[dst] = n[src]
    if n.get("historic"):
        o["hi"] = 1
    if n.get("replaces_codes"):
        o["rpc"] = n["replaces_codes"]
    zv = n.get("zh_version")
    if zv is False:
        o["ml"] = sorted(set(o.get("ml") or []) | {"zh"})
    elif isinstance(zv, str):  # "partial" / "previous revision only": a Chinese text exists, so no "no Chinese version" notice
        o["zv"] = zv
        o["ml"] = [x for x in (o.get("ml") or []) if x != "zh"]
        if not o["ml"]:
            o.pop("ml")
    elif zv is True and o.get("ml"):
        o["ml"] = [x for x in o["ml"] if x != "zh"] or None
        if not o["ml"]:
            o.pop("ml")
    if n.get("series_group"):
        o["sg"] = n["series_group"]
    out_nodes.append(o)

# hubs: top ~40 by degree, at most a fair share per group so the labels spread across the map
rank = sorted(range(len(nodes)), key=lambda i: -out_nodes[i]["deg"])
per = C.Counter()
cap = {"BD": 16, "LEG": 9, "FSD": 6, "LandsD": 5, "PlanD": 4, "EXT": 4}
hubs = []
for i in rank:
    g = out_nodes[i]["g"]
    if out_nodes[i]["k"] in ("section", "schedule_section", "division", "part", "document_stub") or out_nodes[i].get("fd"):
        continue
    if per[g] >= cap.get(g, 3):
        continue
    per[g] += 1
    hubs.append(i)
    if len(hubs) >= 42:
        break
for r, i in enumerate(hubs, 1):
    out_nodes[i]["h"] = r

# ---------- edges ----------
TY = {"cites": "c", "refers_to_section": "r", "explains": "x", "amends": "a", "supersedes": "s", "implements": "i"}
out_s = []
for e in S:
    o = {"s": idx[e["s"]], "t": idx[e["t"]], "y": TY[e["type"]], "q": e["q"]}
    for src, dst in (("qz", "qz"), ("p", "p"), ("pz", "pz"), ("pin", "pin"), ("basis", "b"), ("ql", "ql")):
        if e.get(src) is not None:
            o[dst] = e[src]
    if e.get("faint"):
        o["f"] = 1
    if e.get("index"):
        o["ix"] = 1
    out_s.append(o)
out_d = [{"s": idx[e["s"]], "t": idx[e["t"]], "re": e["reason_en"], "rz": e["reason_zh"], "es": e.get("ev_s"), "et": e.get("ev_t"),
          "cf": e.get("conf")} for e in D if e["s"] in idx and e["t"] in idx]

concepts = [[c["id"], c["en"], c.get("zh") or "", [idx[d] for d in c["docs"] if d in idx], c.get("variants") or []] for c in CO["concepts"]]

tax = G["taxonomy"]
data = {
    "built": G["built"], "checked": "2026-09", "checked_en": "September 2026", "checked_zh": "2026年9月",
    "counts": {"nodes": len(out_nodes), "solid": len(out_s), "dashed": len(out_d), "concepts": len(concepts)},
    "groups": {
        "BD": {"en": "Buildings Department", "zh": "屋宇署", "color": "#c4763c"},
        "FSD": {"en": "Fire Services Department", "zh": "消防處", "color": "#a4473c"},
        "LandsD": {"en": "Lands Department", "zh": "地政總署", "color": "#5d7a64"},
        "PlanD": {"en": "Planning / TPB", "zh": "規劃署及城規會", "color": "#5f7390"},
        "LEG": {"en": "Cap 123 and regulations", "zh": "建築物條例及規例", "color": "#5a4c40"},
        "EXT": {"en": "Other ordinances", "zh": "其他條例", "color": "#8f8274"},
    },
    "domains": {d["id"]: {"en": d["name_en"], "zh": d["name_zh"]} for d in tax["domains"]},
    "subjects": {s["id"]: [s["name_en"], s["name_zh"], s["domain"]] for s in tax["subjects"]},
    "nodes": out_nodes, "solid": out_s, "dashed": out_d, "concepts": concepts,
}
data["counts"].update({"documents": sum(1 for n in out_nodes if n["k"] == "document"), "provisions": sum(1 for n in out_nodes if n["g"] == "LEG"),
                       "by_group": dict(C.Counter(n["g"] for n in out_nodes if n["k"] == "document")),
                       "by_series": dict(C.Counter(n.get("sr") for n in out_nodes if n["k"] == "document")),
                       "faded": sum(1 for n in out_nodes if n.get("fd")), "title_only": sum(1 for n in out_nodes if n.get("qt"))})
DCOL = {"D1": "#5f7390", "D2": "#b0463a", "D3": "#7a6a55", "D4": "#cf8a2e", "D5": "#4f8a86", "D6": "#8c6a9a", "D7": "#5d7a64", "D8": "#a88f5a"}
for k, v in data["domains"].items():
    v["color"] = DCOL.get(k, "#8b7355")

js = "/* HK Building Regulations Map data. Built by pipeline/s6_build_data.py from " + SRC.name + " " + G["built"] + " */\nwindow.HKMAP=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
OUT.write_text(js, encoding="utf-8")
print("wrote", OUT, round(len(js.encode("utf-8")) / 1e6, 2), "MB")
print("counts", data["counts"], "legislation nodes with inferred domain:", sum(1 for n in out_nodes if n.get("dmi")),
      "no domain:", sum(1 for n in out_nodes if not n.get("dm")))
print("hubs:", [out_nodes[i]["c"] for i in hubs])
