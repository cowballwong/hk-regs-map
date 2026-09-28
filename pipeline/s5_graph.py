"""S5 part A, step 1: nodes.json (documents + legislation tree + external ordinances) and
edges_citations.json (the SOLID layer: every edge carries the quoted sentence and page).

Deterministic, no paid APIs. Reads <work>/text (S4) and the S2/S3 JSON in pipeline.
Writes pipeline/graph/nodes.json, edges_citations.json; heavy intermediates in <work>/graph_work.
Builds on an earlier citation-regex prototype (same code families, extended: quotes, pages, Chinese forms,
spaced digits, BD circular letters cited by date, old PNAP numbers, title links, external ordinances).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK as WROOT, SITE
import json, re, collections, sys, unicodedata, bisect, pathlib, datetime
sys.stdout.reconfigure(encoding='utf-8')
SB = PIPE
OUT = SB / 'graph'; OUT.mkdir(exist_ok=True)
WORK = pathlib.Path(str(WROOT / 'graph_work')); WORK.mkdir(parents=True, exist_ok=True)
TX = str(WROOT / 'text') + '/'

inv = json.load(open(SB / 'S3_inventory.json', encoding='utf-8'))['records']
man = json.load(open(str(WROOT / 'raw/docs/manifest.json'), encoding='utf-8'))['entries']
assert len(inv) == len(man) and all(a['code'] == b['code'] for a, b in zip(inv, man))
leg = json.load(open(SB / 'S2_legislation_sections.json', encoding='utf-8'))
rows = [json.loads(l) for l in open(TX + 'corpus.jsonl', encoding='utf-8')]
byid = collections.defaultdict(dict)
for r in rows: byid[r['doc_id']][r['lang']] = r

def read(p):
    try: return open(p, encoding='utf-8', errors='ignore').read()
    except Exception: return ''

def cjk_ratio(t):
    n = len(re.findall(r'[\u4e00-\u9fff]', t)); m = len(re.sub(r'\s', '', t)) or 1
    return n / m

# ------------------------------------------------------------------ text normalisation
FW = {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)}   # full-width ASCII -> ASCII, 1:1
CJK = '\u2e80-\u9fff\u3000-\u303f\uff00-\uffef\u300a\u300b'
JOIN = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789()./-')

def norm_page(p, zh):
    """Return (O, T): O keeps original glyphs for quoting, T is the ASCII-folded twin for matching.
    Same length, same offsets. Chinese: letter-spaced tokens are re-joined ("1 9 9 4 年" -> "1994年")
    and spaces next to CJK are dropped (they are line-break artefacts)."""
    p = re.sub(r'[\uf000-\uf8ff\x00-\x08\x0b-\x1f\u3000]', ' ', p)
    p = re.sub(r'\s+', ' ', p).strip()
    T = p.translate(FW)
    if not zh: return p, T
    drop = set(); n = len(T)
    for i, c in enumerate(T):
        if c != ' ' or i == 0 or i == n - 1: continue
        a, b = T[i - 1], T[i + 1]
        if re.match(f'[{CJK}]', a) or re.match(f'[{CJK}]', b): drop.add(i); continue
        if a in JOIN and b in JOIN and (i < 2 or T[i - 2] == ' ' or T[i - 2] not in JOIN or not T[i-2].isalnum()) \
                and (i + 2 >= n or T[i + 2] == ' ' or T[i + 2] not in JOIN or not T[i+2].isalnum()):
            drop.add(i)
    O2 = ''.join(ch for i, ch in enumerate(p) if i not in drop)
    T2 = ''.join(ch for i, ch in enumerate(T) if i not in drop)
    return O2, T2

ABBRV = {'no', 'nos', 'cap', 'reg', 'regs', 'para', 'paras', 's', 'ss', 'e.g', 'i.e', 'etc', 'mr', 'ms', 'dr', 'st', 'fig',
         'vol', 'cl', 'sec', 'art', 'p', 'pp', 'ch', 'approx', 'ref', 'co', 'ltd', 'sch', 'figs', 'nd', 'viz', 'cf', 'op', 'al'}
RB = re.compile(r'[.!?;](?=\s+[(\[A-Z0-9"\u201c\u2018])|[\u3002\uff1b\uff01\uff1f]|(?<=[\u4e00-\u9fff])[;](?=\S)')

def boundaries(T):
    b = [0]
    for m in RB.finditer(T):
        if m.group() == '.':
            w = re.search(r'([A-Za-z][A-Za-z.]*)\.$', T[max(0, m.start() - 10):m.end()])
            if w and (w.group(1).lower() in ABBRV or len(w.group(1)) == 1): continue
        b.append(m.end())
    b.append(len(T))
    return b

def quote_of(O, B, s, e, lim=300):
    i = bisect.bisect_right(B, s) - 1
    a = B[max(i, 0)]; z = B[bisect.bisect_left(B, e)] if bisect.bisect_left(B, e) < len(B) else len(O)
    if z < e: z = len(O)
    q = O[a:z].strip()
    if len(q) <= lim: return q
    mid = (s + e) // 2; a2 = max(a, mid - lim // 2); z2 = min(z, a2 + lim)
    a2 = max(a, z2 - lim)
    return ('\u2026' if a2 > a else '') + O[a2:z2].strip() + ('\u2026' if z2 < z else '')

# ------------------------------------------------------------------ document nodes
MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                          'september', 'october', 'november', 'december'])}
MON = '|'.join(m.capitalize() for m in MONTHS)
INDEX_DOCS = {'BD_PNAP-ADM-1', 'BD_PNRC-1', 'BD_PNBI-1'}   # "Practice Notes in Force" lists, not arguments

def iso(y, m=None, d=None):
    return f'{int(y):04d}' + (f'-{int(m):02d}' if m else '') + (f'-{int(d):02d}' if d else '')

def last_page_date(t):
    """PNAP/PNRC/PNBI print 'First issue ... This revision Month YYYY' at the end."""
    ms = list(re.finditer(r'This\s+revision\s*:?\s*(?:\d{1,2}\s+)?(' + MON + r')\.?,?\s+(\d{4})', t))
    if not ms: ms = list(re.finditer(r'First\s+issue\s*:?\s*(?:\d{1,2}\s+)?(' + MON + r')\.?,?\s+(\d{4})', t))
    if ms: m = ms[-1]; return iso(m.group(2), MONTHS[m.group(1).lower()])
    return None

def first_page_full_date(t, year=None):
    p1 = re.sub(r'\s+', ' ', t.split('\f')[0])
    for m in re.finditer(r'\b(\d{1,2})\s+(' + MON + r')\s*,?\s+((?:19|20)\d\d)\b|\b(' + MON + r')\s+(\d{1,2}),?\s+((?:19|20)\d\d)\b', p1):
        if m.group(1): d, mo, y = m.group(1), m.group(2), m.group(3)
        else: mo, d, y = m.group(4), m.group(5), m.group(6)
        if year and y != year: continue
        if 1 <= int(d) <= 31: return iso(y, MONTHS[mo.lower()], d)
    return None

nodes = {}          # id -> node
alias = {}          # duplicate doc_id -> canonical doc_id
texts = {}          # doc_id -> {'en': str, 'zh': str}
sha_seen = {}
for r, m in zip(inv, man):
    did = m['doc_id']
    if r['extra'].get('duplicate_of'):
        alias[did] = r['extra']['duplicate_of']   # resolved to a doc_id below (BD JPN copy)
        continue
    tv = byid.get(did, {})
    key = tuple(sorted(x['sha256'] for x in tv.values()))
    if key and key in sha_seen:
        alias[did] = sha_seen[key]; nodes[sha_seen[key]]['aliases'].append(did); continue
    if key: sha_seen[key] = did
    ver = {}; tx = {}
    for lang in ('en', 'zh'):
        if lang not in tv: continue
        x = tv[lang]
        t = read(x['text_path']); ratio = cjk_ratio(t)
        real = 'zh' if ratio > 0.15 else 'en'
        if len(re.sub(r'\s', '', t)) < 100: continue
        if real in ver:                       # e.g. an English file served in the Chinese slot
            ver[real]['duplicate_slot'] = lang; continue
        ver[real] = {'slot': lang, 'pages': x.get('pages'), 'chars': x.get('chars'),
                     'ocr': x.get('ocr') == 'gemini', 'text_path': x['text_path']}
        tx[real] = t
    texts[did] = tx
    cands = []
    if r.get('latest_issue'): cands.append((r['latest_issue'], 'inventory'))
    for x in tv.values():
        if x.get('issue_date'): cands.append((x['issue_date'], 'pdf-first-page'))
    if 'en' in tx and r['series'].startswith(('PNAP', 'PNRC', 'PNBI')):
        d = last_page_date(tx['en'])
        if d: cands.append((d, 'pdf-last-page (This revision)'))
    if r['series'] == 'BD Circular Letter' and 'en' in tx:
        d = first_page_full_date(tx['en'], (r.get('latest_issue') or '')[:4] or None)
        if d: cands.append((d, 'pdf-first-page (loose: first full date on page 1) [uncertain]'))
    date, dsrc = (None, None)
    if cands: date, dsrc = max(cands, key=lambda c: len(c[0]))
    missing = [l for l in ('en', 'zh') if l not in ver]
    nodes[did] = {
        'id': did, 'kind': 'document', 'dept': m['dept'], 'series': r['series'], 'code': r['code'],
        'title_en': r['title_en'], 'title_zh': r['title_zh'] or None, 'status': r['status'],
        'date': date, 'date_source': dsrc, 'url_en': r['url_en'] or None, 'url_zh': r['url_zh'] or None,
        'lang_versions': sorted(ver), 'missing_lang': missing or None,
        'pages': {l: v['pages'] for l, v in ver.items()}, 'ocr': sorted(l for l, v in ver.items() if v['ocr']) or None,
        'has_text': bool(ver), 'index_doc': did in INDEX_DOCS, 'aliases': [],
    }
    if not ver:
        nodes[did]['no_text_reason'] = m.get('skip') or 'download failed (see S4_report.md)'
    if 'zh' in tv and 'zh' not in ver and 'en' in ver:
        nodes[did]['note'] = 'Chinese slot holds an English file (or no usable text); no Chinese version counted'
for k, v in list(alias.items()):
    if isinstance(v, str) and v.startswith('BD JPN'):
        tgt = next((n for n in nodes.values() if n['code'] == v[3:] and n['dept'] == 'BD'), None)
        alias[k] = tgt['id'] if tgt else None
        if tgt: tgt['aliases'].append(k)
DOCS = set(nodes)
print('document nodes', len(DOCS), 'with text', sum(nodes[d]['has_text'] for d in DOCS), 'aliases', len(alias))

# ------------------------------------------------------------------ legislation tree
INSTR = {i['cap']: i for i in leg['instruments']}
for cap, i in INSTR.items():
    nid = f'Cap {cap}'; eo = '\u53ea\u6709\u82f1\u6587' in i['title_zh']
    nodes[nid] = {'id': nid, 'kind': 'ordinance' if cap == '123' else 'regulation', 'cap': cap,
                  'parent': None if cap == '123' else 'Cap 123', 'title_en': i['title_en'],
                  'title_zh': None if eo else i['title_zh'], 'status': i['status'], 'version_date': i.get('version_date'),
                  'url_en': i['url_en'], 'url_zh': i['url_zh'], 'missing_lang': ['zh'] if eo else None}
LBL = re.compile(r'^((?:Part|Division|Subdivision)\s+[0-9IVXLC]+[A-Z]?|(?:[A-Z][a-z]+\s+)?Schedule(?:\s+\d+[A-Z]?)?)\s*(.*)$')
schedule_by_label = {(r['cap'], r['num'].strip()): r['id'] for r in leg['records'] if r['kind'] == 'schedule'}
secs = {}
for r in leg['records']:
    cap = r['cap']; parent = f'Cap {cap}'; path = []
    for k, pe in enumerate(r['part_en']):
        mm = LBL.match(pe.strip()); lab, ttl = (mm.group(1), mm.group(2)) if mm else (pe.strip(), '')
        path.append(lab)
        gid = schedule_by_label.get((cap, lab)) if k == 0 else None
        gid = gid or (f'Cap {cap} > ' + ' > '.join(path))
        if gid not in nodes:
            pz = r['part_zh'][k] if k < len(r['part_zh']) else None
            nodes[gid] = {'id': gid, 'kind': 'part' if lab.startswith('Part') else ('schedule' if 'Schedule' in lab else 'division'),
                          'cap': cap, 'parent': parent, 'label': lab, 'title_en': ttl or lab, 'title_zh': pz}
        parent = gid
    nid = r['id']
    base = {'id': nid, 'kind': r['kind'], 'cap': cap, 'num': r['num'], 'title_en': r['title_en'] or r['num'],
            'title_zh': r['title_zh'] or None, 'status': r['status'] or None, 'in_force_from': r['in_force_from'],
            'url_en': r['url_en'], 'url_zh': r['url_zh']}
    if nid in nodes:        # schedule record created earlier as a group node
        nodes[nid].update({k: v for k, v in base.items() if k not in ('title_en',) or v != r['num']}); nodes[nid]['parent'] = f'Cap {cap}'
        continue
    base['parent'] = parent if parent != nid else f'Cap {cap}'
    nodes[nid] = base
    if r['kind'] == 'section': secs[(cap, r['name'][1:])] = nid
part_index = {}
for n in nodes.values():
    if n['kind'] == 'part' and n.get('parent') == f"Cap {n['cap']}":
        part_index[(n['cap'], n['label'].split()[1])] = n['id']
print('legislation nodes', sum(1 for n in nodes.values() if n.get('cap')), 'sections', len(secs), 'parts', len(part_index))

# ------------------------------------------------------------------ code -> document maps
code2doc = {}
for did in DOCS:
    n = nodes[did]; c = n['code'] or ''
    if (m := re.match(r'PNAP (ADM|APP|ADV)-(\d+)', c)): code2doc[('PNAP', m.group(1), int(m.group(2)))] = did
    if (m := re.match(r'JPN (\d+)', c)) and n['dept'] == 'BD': code2doc[('JPN', int(m.group(1)))] = did
    if (m := re.match(r'LAO PN (\d+)/(\d{4})\(?([A-Z]?)\)?', c)):
        code2doc[('LAO', int(m.group(1)), m.group(2), m.group(3))] = did
    if (m := re.match(r'FSD CL (V |AC )?(\d+)/(\d{2,4})', c)):
        y = m.group(3); y = y if len(y) == 4 else ('19' + y if int(y) > 30 else '20' + y)
        code2doc[('FSDCL', (m.group(1) or '').strip(), int(m.group(2)), y)] = did
    if (m := re.match(r'TPB PG-No\. (\d+)', c)): code2doc[('PG', int(m.group(1)))] = did
    if (m := re.match(r'PNRC (\d+)', c)): code2doc[('PNRC', int(m.group(1)))] = did
    if (m := re.match(r'PNBI-(\d+)', c)): code2doc[('PNBI', int(m.group(1)))] = did
    if (m := re.match(r'FPN No\. (\d+)', c)): code2doc[('FPN', int(m.group(1)))] = did
lao_latest = {}
for k, v in code2doc.items():
    if k[0] == 'LAO' and k[3] >= lao_latest.get(k[1:3], ('', None))[0]: lao_latest[k[1:3]] = (k[3], v)
for (n, y), (suf, v) in lao_latest.items():
    code2doc.setdefault(('LAO', n, y, ''), v)   # "PN 3/2020" with no base doc -> the latest lettered version
for r, mm in zip(inv, man):            # old (pre-2009) PNAP numbers: "formerly PNAP 166"
    f = r['extra'].get('formerly') or ''
    if (m := re.match(r'PNAP (\d+)$', f)) and mm['doc_id'] in DOCS: code2doc[('OLDPNAP', int(m.group(1)))] = mm['doc_id']
MAXN = collections.defaultdict(int)
for k in code2doc:
    if k[0] == 'PNAP': MAXN[k[1]] = max(MAXN[k[1]], k[2])
    if k[0] in ('PNRC', 'PNBI', 'PG', 'OLDPNAP'): MAXN[k[0]] = max(MAXN[k[0]], k[1])
# BD circular letters by date (they carry no number and are cited by date)
cl_by_date = collections.defaultdict(list)
for did in DOCS:
    n = nodes[did]
    if n['series'] == 'BD Circular Letter' and n['date'] and len(n['date']) == 10: cl_by_date[n['date']].append(did)

# Codes of Practice / manuals / guidelines matched by title: (doc_id, EN regex, ZH regex)
COPS = [
    ('BD_fs-code2011', r'\bFS Code\b|Code of Practice for Fire Safety in Buildings', r'消防安全守則'),
    ('BD_SS2009-e', r'Code of Practice for Site Supervision|\bCoP\s*SS\b', r'地盤監督作業守則'),
    ('BD_TMSS2009-e', r'Technical Memorandum for Supervision Plans', r'監工計劃書的技術備忘錄'),
    ('BD_CoP-SUC2013e', r'Code of Practice for (?:the )?Structural Use of Concrete|\bConcrete Code\b', r'(?<!預製)混凝土結構作業守則'),
    ('BD_SUOS2011', r'(?<!Explanatory Materials to )(?<!Explanatory Materials to the )Code of Practice for (?:the )?Structural Use of Steel|\bSteel Code\b', r'鋼結構作業守則(?![\s\d年]*說明資料)'),
    ('BD_EMSUOS2011e', r'Explanatory Materials to (?:the )?Code of Practice for (?:the )?Structural Use of Steel', r'鋼結構作業守則[\s\d年]*說明資料'),
    ('BD_SUG2018e', r'Code of Practice for (?:the )?Structural Use of Glass', r'玻璃結構作業守則'),
    ('BD_cppcc2016e', r'Code of Practice for Precast Concrete Construction', r'預製混凝土結構作業守則'),
    ('BD_FoundationCode2017', r'Code of Practice for Foundations|\bFoundation Code\b', r'基礎作業守則'),
    ('BD_WindEffects2019e', r'(?<!Explanatory Notes to the )Code of Practice on Wind Effects|\bWind Code\b', r'風力效應作業守則(?![-\s\d年]*說明資料)'),
    ('BD_ExplanatoryNotesWindEffects2019e', r'Explanatory Notes to the Code of Practice on Wind Effects', r'風力效應作業守則[-\s\d年]*說明資料'),
    ('BD_DIL2011e', r'Code of Practice for Dead and Imposed Loads|Dead and Imposed Loads Code', r'恆載及外加荷載作業守則'),
    ('BD_Demolition-e2004', r'Code of Practice for (?:the )?Demolition of Buildings', r'拆卸作業守則'),
    ('BD_BFA2008-e', r'Design Manual\s*[:\-–]?\s*Barrier Free Access|Barrier Free Access 2008|\bBFA Manual\b|\bBFA 2008\b', r'設計手冊[:：]?\s*暢通無阻的通道'),
    ('BD_cop-on-access-for-external-maintenance-2021', r'Code of Practice on Access for External Maintenance', r'外部維修通道作業守則'),
    ('BD_BWLE2020e', r'Code of Practice for Building Works for Lifts and Escalators', r'升降機及自動梯建築工程守則'),
    ('BD_OTTV1995-e', r'Code of Practice for Overall Thermal Transfer Value|\bOTTV Code\b', r'總熱傳送值守則'),
    ('BD_MOE1996-e', r'\bMOE Code\b|Code of Practice for (?:the )?Provision of Means of Escape in Case of Fire', r'提供火警逃生途徑守則'),
    ('BD_MOA2004e', r'\bMOA Code\b|Code of Practice for (?:the )?Provision of Means of Access for Fire\s?fighting and Rescue', r'消防和救援進出途徑守則'),
    ('BD_FRC1996-e', r'\bFRC Code\b|Code of Practice for Fire Resisting Construction', r'耐火結構守則'),
    ('FSD_CoP-Minimum-FSI-E', r'Codes? of Practice for Minimum Fire Service Installations|\bFSI Code\b|\bCoP for (?:Minimum )?FSI', r'最低限度之消防裝置及設備'),
    ('BD_CoP-MBIS-MWISe', r'Code of Practice for (?:the )?Mandatory Building Inspection Scheme', r'強制驗樓計劃及強制驗窗計劃作業守則'),
    ('BD_Osi-1992', r'Code of Practice for Oil Storage Installations', None),
    ('BD_Fsdfc-1994', r'Guide to Fire Safety Design for Caverns', r'岩洞的消防安全設計指南'),
    ('BD_Guidelines-DCREERB2014e', r'Guidelines on Design and Construction Requirements for Energy Efficiency of Residential Buildings', r'住宅樓宇能源效益設計和建造規定指引'),
    ('BD_MWGGe', r'General Guidelines on (?:the )?Minor Works Control System', r'小型工程監管制度之一般指引'),
    ('BD_MWTGc', r'Technical Guidelines on (?:the )?Minor Works Control System', r'小型工程監管制度之技術指引'),
    ('BD_heritage-2021', r'Practice Guidebook for Adaptive Re-?use', r'活化再用和改動及加建工程實用手冊'),
    ('BD_GDCBS', r'Guidelines on (?:the )?Design and Construction of Bamboo Scaffolds', r'竹棚架設計及搭建指引'),
    ('BD_GWS-3', r'Guidelines on (?:the )?Prevention of Water Seepage', r'防止新建樓宇出現滲水情況的指引'),
    ('BD_Drainage-System-Guideline-Eng', r'Guidelines on Maintenance and Repair of Drainage System', r'保養及維修排水系統及衞生設備指引'),
    ('BD_Ad-Signs-E', r'Guide on Erection (?:&|and) Maintenance of Advertising Signs', r'安裝及維修廣告招牌指引'),
    ('BD_Guide-signboards-e', r'Guidelines for Identification of Abandoned or Dangerous Signboards', r'舉報棄置或危險招牌指引'),
    ('BD_BDG-ENG', r'Building Maintenance Guidebook', r'樓宇維修全書'),
    ('BD_IGG-e', r'Introductory Guide on Greening in Buildings', r'樓宇綠化簡易指引'),
    ('BD_index-statutory-submissions', r'Guidelines for Using Building Information Modelling in General Building Plans? Submissions?', r'應用建築信息模擬技術呈交一般建築圖則指引'),
    ('BD_index-statutory-submissions-2', r'Guidelines for Using Building Information Modelling in Statutory Plan Submissions', r'應用建築信息模擬技術呈交法定圖則指引'),
]
COPS = [(d, re.compile(e, re.I if False else 0), re.compile(z) if z else None) for d, e, z in COPS if d in DOCS]
missing_cops = [d for d, *_ in COPS if d not in DOCS]

# ------------------------------------------------------------------ legislation regexes (from research, extended)
ABBR = {'B(A)R': '123A', 'B(C)R': '123Q', 'B(DW)R': '123C', 'B(P)R': '123F', 'B(PSAR)R': '123G',
        'B(RSMRCRC)R': '123H', 'B(RSRC)R': '123H', 'B(SSFPDWL)R': '123I', 'B(SSFPDW&L)R': '123I', 'B(VS)R': '123J',
        'B(OSI)R': '123K', 'B(EE)R': '123M', 'B(MW)R': '123N', 'B(MW)(F)R': '123O', 'B(IR)R': '123P', 'B(I&R)R': '123P',
        'B(Appeal)R': '123L', 'B(A)Rs': '123A', 'B(P)Rs': '123F'}
FULL = {'Building (Administration) Regulation': '123A', 'Building (Construction) Regulation': '123Q',
        'Building (Demolition Works) Regulation': '123C', 'Building (Planning) Regulation': '123F',
        'Building (Private Streets and Access Roads) Regulation': '123G',
        'Building (Refuse Storage and Material Recovery Chambers and Refuse Chutes) Regulation': '123H',
        'Building (Standards of Sanitary Fitments, Plumbing, Drainage Works and Latrines) Regulation': '123I',
        'Building (Ventilating Systems) Regulation': '123J', 'Building (Oil Storage Installations) Regulation': '123K',
        'Building (Appeal) Regulation': '123L', 'Building (Energy Efficiency) Regulation': '123M',
        'Building (Minor Works) (Fees) Regulation': '123O', 'Building (Minor Works) Regulation': '123N',
        'Building (Inspection and Repair) Regulation': '123P'}
BO = {'Buildings Ordinance': '123', 'BO': '123'}
abbr_re = '|'.join(re.escape(a) for a in sorted(ABBR, key=len, reverse=True))
full_re = '|'.join(re.escape(a) + 's?' for a in sorted(FULL, key=len, reverse=True))
NUM = r'(\d{1,3}[A-Z]{0,2})((?:\s?\([0-9a-z]{1,4}\))*)'
TAIL = r'((?:\s*(?:,|and|&|to|-)\s*(?:\d{1,3}[A-Z]{0,2})(?:\s?\([0-9a-z]{1,4}\))*(?![\d/]))*)'
R_ABBR = re.compile(r'(' + abbr_re + r')\s*(?:reg(?:ulation)?s?\.?\s*|r\.?\s*|s\.?\s*)?' + NUM + r'(?![\d/])' + TAIL)
R_FULLN = re.compile(r'(' + full_re + r')\s*(?:\(Cap\.?\s*123[A-Z]\)\s*)?,?\s*(?:[Rr]egulations?\s*|[Ss]ections?\s*|[Rr]eg\.\s*)?' + NUM + r'(?![\d/])' + TAIL)
R_NOF = re.compile(r'\b(?:[Rr]egulations?|[Rr]egs?\.|[Ss]ections?|[Ss]s?\.)\s*' + NUM + TAIL +
                   r'\s*(?:of|under|in)\s+(?:the\s+)?(' + abbr_re + '|' + full_re + r'|Buildings Ordinance|BO(?![A-Za-z]))')
R_BOS = re.compile(r'\bBO\s*,?\s*(?:s(?:ection)?s?\.?\s*)' + NUM + TAIL)
R_PART = re.compile(r'\bPart\s+([IVX]{1,5}|\d{1,2}[A-Z]?)\s+(?:of|under)\s+(?:the\s+)?(' + abbr_re + '|' + full_re + r'|Buildings Ordinance|BO(?![A-Za-z]))')
R_INSTR = re.compile(r'(' + abbr_re + '|' + full_re + r'|Buildings Ordinance|\bBO(?![A-Za-z(]))')
ZH_INSTR = {}
for cap, i in INSTR.items():
    t = (i['title_zh'] or '').strip('《》')
    if t and '只有英文' not in t and i['status'] != 'Repealed': ZH_INSTR[t] = cap
ZH_INSTR['建築物(衛生設備標準、水管裝置、排水工程及廁所)規例'] = '123I'
zh_re = '|'.join(re.escape(k) for k in sorted(ZH_INSTR, key=len, reverse=True))
ZNUM = r'(\d{1,3}[A-Z]{0,2})((?:\([0-9a-z]{1,4}\))*)'
ZTAIL = r'((?:\s*(?:、|,|及|和|或|與|至)\s*(?:第\s*)?\d{1,3}[A-Z]{0,2}(?:\([0-9a-z]{1,4}\))*)*)'
R_ZH = re.compile(r'《?(' + zh_re + r')》?\s*(?:\(第\s*123[A-Z]?\s*章\))?\s*(?:的)?第\s*' + ZNUM + ZTAIL + r'\s*(?:條|款|段|項)')
R_ZHI = re.compile(r'《(' + zh_re + r')》')
R_CAP = re.compile(r'\bCap\.?\s*(\d{1,4}[A-Z]{0,3})\b|\bChapter\s*(\d{1,4}[A-Z]{0,3})\s*(?:of the|,)\s*Laws of Hong Kong|(?:香港法例|[》>]\s*\(?)\s*第\s*(\d{1,4}[A-Z]{0,3})\s*章')

def cap_of(name):
    if name in ABBR: return ABBR[name]
    if name in BO or name == 'BO': return '123'
    n2 = name[:-1] if name.endswith('s') and name[:-1] in FULL else name
    return FULL.get(n2)

def sec_id(cap, n):
    sid = secs.get((cap, n))
    if not sid and cap == '123Q': sid = secs.get(('123B', n))     # old B(C)R numbering, repealed 2021
    return sid

# ------------------------------------------------------------------ doc-code regexes
R_PNAP = re.compile(r'(?<![A-Za-z])(ADM|APP|ADV)\s?-\s?(\d{1,4})')
R_OLDPNAP = re.compile(r'\bPNAP\s*(?:No\.?\s*)?(\d{1,3})(?![\d\-/])')
R_PNRC = re.compile(r'(?:\bPNRC|Practice Notes? for Registered Contractors|註冊承建商作業備考)\s*(?:No\.?\s*|第\s*)?-?\s*(\d{1,3})(?![\d/])')
R_PNBI = re.compile(r'\bPNBI\s*(?:No\.?\s*)?-?\s*(\d{1,2})(?!\d)')
R_JPN = re.compile(r'(?:Joint Practice Notes?|\bJPNs?|聯合作業備考)\s*(?:No(?:s)?\.?\s*|第\s*)?(\d)(?!\d)((?:\s*(?:,|and|&|及|和|、|至|to)\s*(?:No\.?\s*|第\s*)?\d(?!\d))*)')
R_LAO = re.compile(r'(?:Practice Notes?|\bPN)\s*(?:\(PN\)\s*)?(?:Issue\s*)?(?:No\.?\s*)?(\d{1,2})\s*/\s*((?:19|20)\d\d)(?:\s?\(?([A-C])\)?(?![A-Za-z]))?')
R_LAOZH = re.compile(r'地政總署作業備考\s*(?:第)?\s*(\d{1,2})\s*/\s*((?:19|20)\d\d)([A-C]?)')
R_FSDCL = re.compile(r'Circular Letters?\s*(?:No\.?\s*)?(\d{1,2})\s*/\s*((?:19|20)?\d\d)(?!\d)|通函(?:第)?\s*(\d{1,2})\s*/\s*((?:19|20)?\d\d)(?!\d)')
R_PG = re.compile(r'(?:TPB\s*PG[- ]?No\.?|PG[- ]No\.?|Town Planning Board Guidelines?\s*No\.?|規劃指引編號)\s*(\d{1,2})([A-H]?)(?![\d])')
R_FPN = re.compile(r'Fire Protection Notice\s*No\.?\s*(\d{1,2})(?!\d)')
R_CLDATE = re.compile(r'[Cc]ircular [Ll]etters?\s*(?:to [A-Za-z/ ]{2,40}?)?\s*(?:dated|of|issued on|on)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(' + MON + r'),?\s+((?:19|20)\d\d)'
                      r'|[Cc]ircular [Ll]etters?\s*(?:to [A-Za-z/ ]{2,40}?)?\s*(?:dated|of|issued on|on)\s+(\d{1,2})\.(\d{1,2})\.((?:19|20)\d\d)'
                      r'|(?:於|日期為)\s*((?:19|20)\d\d)年(\d{1,2})月(\d{1,2})日(?:發出)?的?通函')

# ------------------------------------------------------------------ cue words for edge type (rule-based, marked as such)
CUE = [
    ('supersedes', re.compile(r'supersed(?:e|es|ing)\b|is superseded(?! by)|are superseded(?! by)|hereby (?:cancel|withdraw)|(?:is|are|has been|have been) (?:cancelled|withdrawn)|in (?:substitution|place) of|replac(?:e|es|ing)\b|取代|代替|廢除|撤銷|撤回', re.I)),
    ('amends', re.compile(r'\bamend(?:s|ing|ments?)? (?:to|of)\b|\b(?:is|are|has been|have been|was|were) (?:amended|revised|supplemented|updated)\b|\bsupplement(?:s|ing)?\b|\bamendments?\b|修訂|修改|補充', re.I)),
]
CUE_IMPL = re.compile(r'(?:issued|made|promulgated|approved|published|prepared)\s+(?:by the (?:Building Authority|BA|Director[^,.]{0,30})\s+)?(?:under|pursuant to)|pursuant to|根據[^。]{0,25}(?:發出|訂立|制定|發表)', re.I)
CUE_EXPL = re.compile(r'explain|clarif|elaborat|interpret|guidance on|guidelines? (?:on|for)|sets? out (?:the )?(?:requirements|criteria|guidelines|practice)|how the Building Authority|闡釋|解釋|闡述|詳述|說明|指引', re.I)
SUP_PRE = re.compile(r'\b(?:supersed(?:e|es|ing)|in (?:substitution|place) of|replac(?:e|es|ing)|cancel(?:s|ling)?|withdraw(?:s|ing)?|revok(?:e|es|ing))\b[^.;]{0,50}$', re.I)
SUP_POST = re.compile(r'^[^.;]{0,60}?\b(?:is|are|has been|have been|was|were|will be|shall be)\s+(?:hereby\s+|now\s+|also\s+)?(?:superseded|cancell?ed|withdrawn|replaced|revoked|deleted)(?:\s+by\s+(?:this|the present|these)\b|(?!\s+by))', re.I)
AMD_PRE = re.compile(r'(?:\b(?:amendments?|revisions?|supplements?)\s+(?:to|of)\b|\b(?:amend(?:s|ing)?|supplement(?:s|ing)?|revis(?:e|es|ing)|updat(?:e|es|ing))\b)[^.;]{0,50}$', re.I)
AMD_POST = re.compile(r'^[^.;]{0,60}?\b(?:is|are|has been|have been|was|were|will be|shall be)\s+(?:hereby\s+)?(?:amended|revised|supplemented|updated)\b', re.I)
ZH_SUP = re.compile(r'取代|代替|廢除|撤銷|撤回|取消')
ZH_AMD = re.compile(r'修訂|修改|補充')

def doc_type(T, s, e, lang):
    pre, post = T[max(0, s - 90):s], T[e:e + 90]
    if lang == 'zh':
        zp = re.sub(r'\(修訂\)|修訂(?:版|本)', '', T[max(0, s - 14):s]); zq = re.sub(r'\(修訂\)|修訂(?:版|本)', '', T[e:e + 16])
        if (m := re.search(r'(?:取代|代替|取消|撤銷|廢除|撤回)[^。，,;；]{0,6}$', zp)): return 'supersedes', m.group()
        if (m := re.match(r'^[^。，,;；]{0,8}?(?:現予|予以|即時|亦|已)?(?:取消|撤銷|廢除|撤回)', zq)) and '由' not in m.group(): return 'supersedes', m.group()
        if (m := re.match(r'^[^。]{0,10}?(?:由|被)本(?:通函|作業備考|守則)(?:所)?取代', zq)): return 'supersedes', m.group()
        if (m := re.search(r'(?:修訂|修改|補充)[^。，,;；()]{0,6}$', zp)): return 'amends', m.group()
        if (m := re.match(r'^[^。，,;；]{0,10}?(?:已|經|予以|現|作出)?(?:修訂|修改|補充)', zq)) and '由' not in m.group(): return 'amends', m.group()
        return 'cites', None
    if (m := SUP_PRE.search(pre)): return 'supersedes', m.group().split()[0]
    if (m := SUP_POST.search(post)): return 'supersedes', m.group().strip()[-30:]
    if (m := AMD_PRE.search(pre)): return 'amends', m.group().split()[0]
    if (m := AMD_POST.search(post)): return 'amends', m.group().strip()[-30:]
    return 'cites', None

IMPL_END = re.compile(r'\b(?:this|the present|these)\s+(?:Codes? of Practice|Code|Practice Notes?|PNAP|PNRC|Technical Memorandum|Memorandum|Guidelines?|Manual|Circular Letter|Circular|letter|Guide|document)\b[^.;]{0,120}?(?:(?:is|are|has been|have been|was)\s+)?(?:issued|made|promulgated|approved|published|prepared)\s+(?:by the [A-Za-z ]{2,40}?\s+)?(?:under|pursuant to|in accordance with)\s+(?:the\s+)?(?:provisions? of\s+(?:the\s+)?)?$', re.I)
EXPL_NEAR = re.compile(r'(?:explain\w*|clarif\w*|elaborat\w*|interpret\w*|guidance on|guidelines? on|requirements? (?:of|under|in)|compliance with)\s+(?:the\s+)?(?:requirements? (?:of|under|in)\s+(?:the\s+)?)?$', re.I)

def leg_type(T, s, e, section_level):
    """Type toward legislation, only when the wording sits right against the citation."""
    pre = T[max(0, s - 200):s]
    if (m := IMPL_END.search(pre)): return 'implements', m.group().strip()
    if s < 300 and (m := re.search(r'(?:^|\s)Issued\s+by\s+(?:the\s+)?[A-Za-z ]{2,50}?\s+under\s+(?:the\s+)?$', T[:s])):
        return 'implements', m.group().strip()
    if re.search(r'本(?:守則|作業備考|通函|備忘錄|技術備忘錄|指引|手冊)[^。]{0,30}?根據\s*《?$', T[max(0, s - 40):s]) and re.match(r'^[^。，,]{0,25}?(?:發出|訂立|制定|發表)', T[e:e + 30]):
        return 'implements', '根據…發出'
    if (m := EXPL_NEAR.search(pre[-70:])) and 'compliance' not in m.group().lower() and 'requirement' not in m.group().lower():
        return 'explains', m.group().strip()
    return ('refers_to_section' if section_level else 'cites'), None

# ------------------------------------------------------------------ external ordinances: mine names from the corpus
NAME = r"((?:[A-Z][\w()&,'’\-]*|of|and|the|for|to|in|on|(?:\([A-Z][\w ]*\)))(?:\s+(?:[A-Z(][\w()&,'’\-]*|of|and|the|for|to|in|on)){0,12}\s+(?:Ordinance|Regulations?))"
R_MINE = re.compile(NAME + r"\s*[,(]?\s*\(?\s*Cap(?:ter)?\.?\s*(\d{1,4}[A-Z]{0,3})\b")
R_MINEZH = re.compile(r'《([^《》]{2,40}?(?:條例|規例))》\s*\(?\s*(?:\()?第\s*(\d{1,4}[A-Z]{0,3})\s*章')
LEAD = {'Under', 'Of', 'The', 'In', 'And', 'For', 'To', 'By', 'With', 'Section', 'Sections', 'Regulation', 'Part', 'Schedule',
        'the', 'of', 'and', 'under', 'Under', 'Accordance', 'Relevant', 'Provisions', 'Requirements', 'See', 'Also', 'As'}
mine_en = collections.defaultdict(collections.Counter); mine_zh = collections.defaultdict(collections.Counter)
for did, tx in texts.items():
    for lang, t in tx.items():
        t1 = re.sub(r'\s+', ' ', t).translate(FW)
        if lang == 'en':
            for m in R_MINE.finditer(t1):
                w = m.group(1).split()
                while w and (w[0] in LEAD or w[0][0].islower() or w[0][0] in '(,'): w = w[1:]
                nm = ' '.join(w)
                if len(w) >= 2 and not re.search(r'(?:Date|Title|Issue|Ref|Item|Table|Appendix|Annex)', nm): mine_en[m.group(2)][nm] += 1
        else:
            t2 = re.sub(r'\s+', '', t1)
            for m in R_MINEZH.finditer(t2): mine_zh[m.group(2)][m.group(1)] += 1
# titles verified from our own corpus (most frequent "X Ordinance (Cap N)" phrasing); fallbacks marked unverified
EXT_FALLBACK = {'95': 'Fire Services Ordinance', '131': 'Town Planning Ordinance', '610': 'Buildings Energy Efficiency Ordinance',
                '572': 'Fire Safety (Buildings) Ordinance', '502': 'Fire Safety (Commercial Premises) Ordinance',
                '121': 'Buildings Ordinance (Application to the New Territories) Ordinance', '344': 'Building Management Ordinance'}
EXT_FALLBACK.update({'1': 'Interpretation and General Clauses Ordinance', '486': 'Personal Data (Privacy) Ordinance',
                     '59': 'Factories and Industrial Undertakings Ordinance', '95B': 'Fire Service (Installations and Equipment) Regulations',
                     '95A': 'Fire Service (Installation Contractors) Regulations', '354': 'Waste Disposal Ordinance',
                     '358': 'Water Pollution Control Ordinance', '311': 'Air Pollution Control Ordinance', '400': 'Noise Control Ordinance',
                     '499': 'Environmental Impact Assessment Ordinance', '53': 'Antiquities and Monuments Ordinance',
                     '208': 'Country Parks Ordinance', '301': 'Hong Kong Airport (Control of Obstructions) Ordinance',
                     '519': 'Railways Ordinance', '509': 'Occupational Safety and Health Ordinance', '201': 'Prevention of Bribery Ordinance',
                     '622': 'Companies Ordinance', '473': 'Land Survey Ordinance', '409': 'Engineers Registration Ordinance',
                     '636': 'Fire Safety (Industrial Buildings) Ordinance', '374': 'Road Traffic Ordinance', '279': 'Education Ordinance'})
EXT_MEMORY = set(EXT_FALLBACK)   # titles typed from memory or S2: cross-checked against corpus phrasing below
for r in leg['related_ordinances_not_downloaded']:
    if 'UNVERIFIED' not in r['title_en']: EXT_FALLBACK.setdefault(r['cap'], r['title_en'])
ext_name = {}
for cap, c in mine_en.items():
    if cap.startswith('123'): continue
    nm, k = c.most_common(1)[0]
    ext_name[cap] = (nm, k)
name2cap = {}
for cap, c in mine_en.items():
    if cap.startswith('123'): continue
    for nm, k in c.items():
        if k >= 2 and nm.endswith('Ordinance') and len(nm) > 12: name2cap.setdefault(nm, cap)
for cap, nm in EXT_FALLBACK.items(): name2cap.setdefault(nm, cap)
for bad in [n for n in name2cap if n.startswith('Buildings Ordinance') and name2cap[n] != '121']: name2cap.pop(bad)
zh2cap = {}
for cap, c in mine_zh.items():
    if cap.startswith('123'): continue
    for nm, k in c.items():
        if k >= 2: zh2cap.setdefault(nm, cap)
extn_re = '|'.join(re.escape(n) for n in sorted(name2cap, key=len, reverse=True))
R_EXTNAME = re.compile(r'(?:[Ss]ections?\s+(\d+[A-Z]?(?:\s?\([0-9a-zA-Z]{1,4}\))*)\s+(?:of|under)\s+(?:the\s+)?)?(' + extn_re + r')(?!\s*\(?\s*Cap)')
zhn_re = '|'.join(re.escape(n) for n in sorted(zh2cap, key=len, reverse=True))
R_EXTZH = re.compile(r'《(' + zhn_re + r')》(?!\s*\(?\s*第\s*\d)(?:\s*第\s*(\d+[A-Z]?(?:\(\w{1,4}\))*)\s*條)?') if zhn_re else None

def ext_node(cap):
    nid = f'Cap {cap}'
    if nid not in nodes:
        nm = ext_name.get(cap); fb = EXT_FALLBACK.get(cap)
        zh = mine_zh.get(cap).most_common(1)[0][0] if mine_zh.get(cap) else None
        base = re.match(r'(\d+)', cap).group(1)
        nodes[nid] = {'id': nid, 'kind': 'external_ordinance', 'cap': cap,
                      'parent': f'Cap {base}' if base != cap else None,
                      'title_en': fb or (nm[0] if nm else f'Cap. {cap} (title not found in corpus)'),
                      'title_zh': f'《{zh}》' if zh else None,
                      'title_source': ('S2 list / known title' + (' (corpus agrees)' if nm and fb and fb.lower() in ' '.join(x for x in mine_en[cap]).lower() else ' [not seen in corpus phrasing: unverified]')) if fb
                                      else (f'corpus phrasing, most frequent ({nm[1]}x) [unverified]' if nm else 'none'),
                      'url_en': f'https://www.elegislation.gov.hk/hk/cap{cap}!en',
                      'url_zh': f'https://www.elegislation.gov.hk/hk/cap{cap}!zh-Hant-HK'}
    return nid

# ------------------------------------------------------------------ stubs for codes we do not hold
def stub(label, family, dept):
    nid = 'missing:' + label
    if nid not in nodes:
        nodes[nid] = {'id': nid, 'kind': 'document_stub', 'code': label, 'family': family, 'dept': dept,
                      'title_en': None, 'title_zh': None,
                      'note': 'Cited in the corpus but not in our inventory (withdrawn, superseded or out of scope) [unverified which]'}
    return nid

# ------------------------------------------------------------------ extraction
junk = collections.Counter()

def extract(T, src, lang):
    """Yield (target_id, start, end, pinpoint, family, kind) for every citation in normalised text T."""
    me = nodes[src]; own = me.get('code') or ''
    ownp = re.match(r'PNAP (ADM|APP|ADV)-(\d+)', own)
    npages = max([v for v in (me.get('pages') or {}).values() if v] or [0])
    for m in R_PNAP.finditer(T):
        s_, n = m.group(1), m.group(2)
        pre = T[max(0, m.start() - 16):m.start()]
        if '註冊承建商作業備考' in pre or 'Registered Contractors' in pre:     # "(註冊承建商作業備考 APP-77)" = PNRC 77
            k = ('PNRC', int(n))
            if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'PNRC', 'doc'
            continue
        if ownp and s_ == ownp.group(1) and n.startswith(ownp.group(2)) and n != ownp.group(2) and len(n) - len(ownp.group(2)) <= 2 \
                and int(n[len(ownp.group(2)):] or 0) <= max(npages, 1) + 1:
            continue                                                  # own footer code + page number
        hit = code2doc.get(('PNAP', s_, int(n)))
        if not hit:
            for k in range(len(n) - 1, 0, -1):
                if int(n[k:]) <= 99 and ('PNAP', s_, int(n[:k])) in code2doc: hit = code2doc[('PNAP', s_, int(n[:k]))]; break
        if hit: yield hit, m.start(), m.end(), None, 'PNAP', 'doc'
        elif int(n) <= MAXN[s_] + 3 and len(n) <= 3: yield stub(f'PNAP {s_}-{int(n)}', 'PNAP', 'BD'), m.start(), m.end(), None, 'PNAP', 'doc'
        else: junk[f'PNAP {s_}-{n}'] += 1
    for m in R_OLDPNAP.finditer(T):
        k = ('OLDPNAP', int(m.group(1)))
        if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'PNAP (old number)', 'doc'
        elif int(m.group(1)) <= 330: yield stub(f'PNAP {int(m.group(1))} (old series)', 'PNAP', 'BD'), m.start(), m.end(), None, 'PNAP (old number)', 'doc'
    for m in R_PNRC.finditer(T):
        k = ('PNRC', int(m.group(1)))
        if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'PNRC', 'doc'
        elif int(m.group(1)) <= MAXN['PNRC'] + 3: yield stub(f'PNRC {int(m.group(1))}', 'PNRC', 'BD'), m.start(), m.end(), None, 'PNRC', 'doc'
    for m in R_PNBI.finditer(T):
        k = ('PNBI', int(m.group(1)))
        if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'PNBI', 'doc'
    for m in R_JPN.finditer(T):
        for x in [m.group(1)] + re.findall(r'(\d)(?!\d)', m.group(2) or ''):
            k = ('JPN', int(x))
            if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'JPN', 'doc'
    for m in list(R_LAO.finditer(T)) + list(R_LAOZH.finditer(T)):
        n, y, suf = int(m.group(1)), m.group(2), (m.group(3) or '')
        hit = code2doc.get(('LAO', n, y, suf))
        if hit: yield hit, m.start(), m.end(), None, 'LAO PN', 'doc'
        elif me['dept'] == 'LandsD' or 'Lands' in T[max(0, m.start() - 80):m.start()] or '地政' in T[max(0, m.start() - 40):m.start()]:
            yield stub(f'LAO PN {n}/{y}{suf}', 'LAO PN', 'LandsD'), m.start(), m.end(), None, 'LAO PN', 'doc'
        else: junk[f'PN {n}/{y}'] += 1
    for m in R_FSDCL.finditer(T):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        y = b if len(b) == 4 else ('19' + b if int(b) > 30 else '20' + b)
        hit = code2doc.get(('FSDCL', '', int(a), y))
        if hit: yield hit, m.start(), m.end(), None, 'FSD CL', 'doc'
        elif me['dept'] == 'FSD' or re.search(r'Fire Services|FSD|消防', T[max(0, m.start() - 80):m.end() + 40]):
            yield stub(f'FSD CL {int(a)}/{y}', 'FSD CL', 'FSD'), m.start(), m.end(), None, 'FSD CL', 'doc'
        else: junk[f'CL {a}/{b}'] += 1
    for m in R_PG.finditer(T):
        k = ('PG', int(m.group(1)))
        if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'TPB PG', 'doc'
        else: yield stub(f'TPB PG-No. {int(m.group(1))}{m.group(2)}', 'TPB PG', 'PlanD/TPB'), m.start(), m.end(), None, 'TPB PG', 'doc'
    for m in R_FPN.finditer(T):
        k = ('FPN', int(m.group(1)))
        if k in code2doc: yield code2doc[k], m.start(), m.end(), None, 'FPN', 'doc'
        else: yield stub(f'FPN No. {int(m.group(1))}', 'FPN', 'FSD'), m.start(), m.end(), None, 'FPN', 'doc'
    for m in R_CLDATE.finditer(T):
        if m.group(1): d = iso(m.group(3), MONTHS[m.group(2).lower()], m.group(1))
        elif m.group(4): d = iso(m.group(6), m.group(5), m.group(4))
        else: d = iso(m.group(7), m.group(8), m.group(9))
        hits = cl_by_date.get(d, [])
        if len(hits) == 1: yield hits[0], m.start(), m.end(), None, 'BD CL (by date)', 'doc'
        elif not hits: yield stub(f'BD CL dated {d}', 'BD CL', 'BD'), m.start(), m.end(), None, 'BD CL (by date)', 'doc'
        else: junk[f'CL date ambiguous {d}'] += 1
    for did, rx, rz in COPS:
        for m in (rz.finditer(T) if lang == 'zh' and rz else rx.finditer(T) if lang != 'zh' else []):
            yield did, m.start(), m.end(), None, 'CoP/manual (title)', 'doc'
    # ---- legislation
    seen = set()
    def legs(cap, n, sub, s, e):
        sid = sec_id(cap, n)
        if sid:
            if (sid, s) not in seen: seen.add((sid, s)); return (sid, s, e, (n + (sub or '').replace(' ', '')), 'Cap 123 family', 'section')
        else: junk[f'Cap {cap} s{n}'] += 1
        return None
    for rx in (R_ABBR, R_FULLN):
        for m in rx.finditer(T):
            cap = cap_of(m.group(1))
            if not cap: continue
            for x in [(m.group(2), m.group(3))] + re.findall(r'(\d{1,3}[A-Z]{0,2})((?:\s?\([0-9a-z]{1,4}\))*)', m.group(4) or ''):
                if (r := legs(cap, x[0], x[1], m.start(), m.end())): yield r
    for m in R_NOF.finditer(T):
        cap = cap_of(m.group(4)) or '123'
        for x in [(m.group(1), m.group(2))] + re.findall(r'(\d{1,3}[A-Z]{0,2})((?:\s?\([0-9a-z]{1,4}\))*)', m.group(3) or ''):
            if (r := legs(cap, x[0], x[1], m.start(), m.end())): yield r
    for m in R_BOS.finditer(T):
        for x in [(m.group(1), m.group(2))] + re.findall(r'(\d{1,3}[A-Z]{0,2})((?:\s?\([0-9a-z]{1,4}\))*)', m.group(3) or ''):
            if (r := legs('123', x[0], x[1], m.start(), m.end())): yield r
    for m in R_ZH.finditer(T):
        cap = ZH_INSTR.get(m.group(1))
        if not cap: continue
        for x in [(m.group(2), m.group(3))] + re.findall(r'(\d{1,3}[A-Z]{0,2})((?:\([0-9a-z]{1,4}\))*)', m.group(4) or ''):
            if (r := legs(cap, x[0], x[1], m.start(), m.end())): yield r
    for m in R_PART.finditer(T):
        cap = cap_of(m.group(2)) or '123'
        pid = part_index.get((cap, m.group(1)))
        if pid: yield pid, m.start(), m.end(), 'Part ' + m.group(1), 'Cap 123 family', 'section'
    for m in (R_INSTR.finditer(T) if lang != 'zh' else R_ZHI.finditer(T)):
        cap = cap_of(m.group(1)) if lang != 'zh' else ZH_INSTR.get(m.group(1))
        if cap: yield f'Cap {cap}', m.start(), m.end(), None, 'Cap 123 family', 'instrument'
    for m in R_CAP.finditer(T):
        c = m.group(1) or m.group(2) or m.group(3)
        if m.group(1):
            bad = re.search(r'(?:Overall|GFA|the|a)\s*$', T[max(0, m.start() - 10):m.start()], re.I)
            ok = T[m.start():m.end()].startswith('Cap.') or re.search(r'Ordinance|Regulation|Laws|Rules|[(,]', T[max(0, m.start() - 40):m.start()])
            if bad or not ok: junk['Cap without legislation context'] += 1; continue
        if c.startswith('123'):
            if f'Cap {c}' in nodes: yield f'Cap {c}', m.start(), m.end(), None, 'Cap 123 family', 'instrument'
        elif re.match(r'\d', c) and int(re.match(r'\d+', c).group()) < 1200:
            yield ext_node(c), m.start(), m.end(), None, 'other ordinance', 'external'
    if lang != 'zh' and extn_re:
        for m in R_EXTNAME.finditer(T):
            yield ext_node(name2cap[m.group(2)]), m.start(), m.end(), ('s' + m.group(1).replace(' ', '')) if m.group(1) else None, 'other ordinance', 'external'
    if lang == 'zh' and R_EXTZH:
        for m in R_EXTZH.finditer(T):
            yield ext_node(zh2cap[m.group(1)]), m.start(), m.end(), ('s' + m.group(2)) if m.group(2) else None, 'other ordinance', 'external'

# ------------------------------------------------------------------ run over every page of every text
PREC = {'supersedes': 6, 'amends': 5, 'implements': 4, 'explains': 3, 'refers_to_section': 2, 'cites': 1}
COPDOCS = {d for d, *_ in COPS}
ment = collections.defaultdict(list)
for did in sorted(texts):
    for lang, t in texts[did].items():
        for pi, page in enumerate(t.split('\f'), 1):
            O, T = norm_page(page, lang == 'zh')
            if not T: continue
            B = None; seen_q = set()
            for tgt, s, e, pin, fam, kind in extract(T, did, lang):
                tgt = alias.get(tgt, tgt)
                if not tgt or tgt == did: continue
                if B is None: B = boundaries(T)
                if kind == 'doc':
                    typ, cue = ('cites', None) if nodes[did]['index_doc'] else doc_type(T, s, e, lang)
                else:
                    typ, cue = leg_type(T, s, e, kind == 'section')
                q = quote_of(O, B, s, e)
                if (tgt, q) in seen_q and typ == 'cites': continue
                seen_q.add((tgt, q))
                ment[(did, tgt)].append({'lang': lang, 'page': pi, 'quote': q, 'type': typ, 'cue': cue, 'pin': pin,
                                         'fam': fam, 'kind': kind, 'basis': 'text'})
# title-based links
for did in sorted(DOCS):
    n = nodes[did]
    for lang, title in (('en', n['title_en']), ('zh', n['title_zh'])):
        if not title or 'UNVERIFIED' in title: continue
        O, T = norm_page(title, lang == 'zh')
        for tgt, s, e, pin, fam, kind in extract(T, did, lang):
            tgt = alias.get(tgt, tgt)
            if not tgt or tgt == did: continue
            if kind != 'doc': typ = 'explains'
            elif re.search(r'^(?:Deletion|Cancellation|Withdrawal) of|刪除|撤銷', title): typ = 'supersedes'
            elif re.search(r'Amendment|修訂', title): typ = 'amends'
            elif n['series'].startswith('PNAP') and tgt in COPDOCS: typ = 'explains'
            else: typ = 'cites'
            ment[(did, tgt)].append({'lang': lang, 'page': None, 'quote': title, 'type': typ, 'cue': 'title', 'pin': pin,
                                     'fam': fam, 'kind': kind, 'basis': 'title'})

LEVEL = {'doc': 'document', 'section': 'section', 'instrument': 'instrument', 'external': 'external_ordinance'}
edges = []
for (src, tgt), ms in ment.items():
    best = max(PREC[x['type']] for x in ms); btype = next(k for k, v in PREC.items() if v == best)
    def pick(lang):
        c = [x for x in ms if x['lang'] == lang]
        c.sort(key=lambda x: (x['type'] != btype, x['basis'] == 'title', x['page'] or 0))
        return c[0] if c else None
    en, zh = pick('en'), pick('zh')
    pr = en if en and (en['type'] == btype or not zh or zh['type'] != btype) else (zh or en)
    bases = {x['basis'] for x in ms}
    tb = next((x for x in ms if x['type'] == btype), pr)
    e = {'source': src, 'target': tgt, 'type': btype, 'layer': 'solid',
         'basis': 'text+title' if len(bases) == 2 else bases.pop(), 'level': LEVEL[pr['kind']],
         'quote': pr['quote'], 'quote_lang': pr['lang'], 'page': pr['page'],
         'quote_zh': zh['quote'] if zh and pr is not zh else None, 'page_zh': zh['page'] if zh and pr is not zh else None,
         'pinpoints': sorted({x['pin'] for x in ms if x['pin']}) or None,
         'mentions': dict(collections.Counter(x['lang'] for x in ms if x['basis'] == 'text')),
         'type_basis': ('title wording' if tb['cue'] == 'title' else f"rule: cue '{tb['cue']}' near the citation") if tb['cue'] else
                       ('rule: index document lists it' if nodes[src].get('index_doc') and pr['kind'] == 'doc' else 'default'),
         'family': pr['fam']}
    if nodes[tgt]['kind'] == 'document_stub': e['target_missing'] = True
    if nodes[src].get('index_doc'): e['from_index_doc'] = True
    edges.append(e)
# instrument-level edges made redundant by a section edge into the same instrument (draw faint / hide)
sec_caps = collections.defaultdict(set)
for e in edges:
    if e['level'] == 'section': sec_caps[e['source']].add(nodes[e['target']]['cap'])
for e in edges:
    if e['level'] == 'instrument' and nodes[e['target']]['cap'] in sec_caps[e['source']]: e['covered_by_section_edge'] = True
edges.sort(key=lambda e: (e['source'], e['level'], e['target']))
print('edges', len(edges), collections.Counter(e['type'] for e in edges), 'junk', sum(junk.values()))

# ------------------------------------------------------------------ write
now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
kinds = collections.Counter(n['kind'] for n in nodes.values())
json.dump({'built': now, 'script': 'pipeline/s5_graph.py',
           'notes': ['Documents: one node per unique document (S3 inventory minus 9 LandsD copies of BD JPNs and 3 duplicate BD circular-letter listings, kept as aliases).',
                     'has_text=false: 13 items BD lists without a PDF (cancelled PNAPs, PNRC 55) and 2 whole-document download failures.',
                     'Legislation tree: parent ids give ordinance > regulation > Part/Schedule > Division > section.',
                     'missing_lang lists languages we do not hold as text (an English file in the Chinese slot does not count as Chinese).',
                     'date: the most precise of inventory date, first-page date, or last-page "This revision"; see date_source.',
                     'document_stub nodes are codes cited in the corpus that are not in our inventory.'],
           'counts': dict(kinds), 'nodes': list(nodes.values())},
          open(OUT / 'nodes.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
json.dump({'built': now, 'script': 'pipeline/s5_graph.py',
           'method': ['Regex over every page of every English and Chinese text (OCR texts included); pages from \\f breaks.',
                      'Chinese letter-spaced tokens re-joined before matching ("1 9 9 4 年" -> "1994年"); full-width ASCII folded.',
                      'quote = the sentence holding the citation, whitespace collapsed, cut to ~300 characters around the citation.',
                      'type is rule-based from wording next to the citation (see type_basis); default cites, or refers_to_section for a section. Part B may re-type.',
                      'One edge per (source, target); English quote preferred, Chinese kept as quote_zh.',
                      'basis=title: the link comes from the document title; quote is the title.'],
           'counts': {'edges': len(edges), 'by_type': dict(collections.Counter(e['type'] for e in edges)),
                      'by_level': dict(collections.Counter(e['level'] for e in edges))},
           'edges': edges}, open(OUT / 'edges_citations.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
json.dump({'junk': junk.most_common(), 'mine_en': {k: v.most_common(5) for k, v in mine_en.items()},
           'mine_zh': {k: v.most_common(3) for k, v in mine_zh.items()}, 'missing_cops': missing_cops},
          open(WORK / 'extract_debug.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('written', OUT)
