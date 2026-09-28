"""S5 step 4: graph.json, concepts.json, bridge candidates, bridge merge.

Usage:
  python s5_final.py concepts     -> graph/concepts.json
  python s5_final.py graph        -> graph/graph.json (needs concepts.json; adds bridges if edges_bridges.json exists)
  python s5_final.py candidates   -> <work>/graph_work/bridge_candidates_*.json (with text snippets)
No paid APIs. Text lives at <work>/text/<id>_<lang>.txt
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK as WROOT, SITE
import json, glob, re, sys, math, collections, os, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, 'graph')
TEXT = str(WROOT / 'text')
WORK = str(WROOT / 'graph_work')


def load(p):
    return json.load(open(p, encoding='utf-8'))


def save(p, obj, compact=False):
    with open(p, 'w', encoding='utf-8') as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def tags_all():
    out = []
    for f in sorted(glob.glob(os.path.join(G, 'tags', 'batch_*_tags.json'))):
        out += load(f)
    return out


# ---------------------------------------------------------------- concepts
ACRO = {  # acronym -> canonical long form (HK usage)
    'eva': 'emergency vehicular access', 'gfa': 'gross floor area', 'fsi': 'fire service installations',
    'mic': 'modular integrated construction', 'sbd': 'sustainable building design', 'bfa': 'barrier free access',
    'rche': 'residential care home for the elderly', 'rchd': 'residential care home for persons with disabilities',
    'mwcs': 'minor works control system', 'mbis': 'mandatory building inspection scheme',
    'mwis': 'mandatory window inspection scheme', 'ubw': 'unauthorized building works',
    'ottv': 'overall thermal transfer value', 'rttv': 'residential thermal transfer value',
    'els': 'excavation and lateral support', 'bim': 'building information modelling', 'ozp': 'outline zoning plan',
    'ntеh': 'new territories exempted house', 'nteh': 'new territories exempted house',
    'stt': 'short term tenancy', 'ddh': 'design, disposition and height', 'vdf': 'vertical daylight factor',
    'frp': 'fire resistance period', 'acm': 'asbestos containing material', 'op': 'occupation permit',
    'top': 'temporary occupation permit', 'a&a': 'alteration and addition', 'frc': 'fire resisting construction',
    'moe': 'means of escape', 'moa': 'means of access', 'fsm': 'fire safety management', 'bhr': 'building height restriction',
    'gbp': 'general building plans', 'ap': 'authorized person', 'rse': 'registered structural engineer',
    'rge': 'registered geotechnical engineer', 'ri': 'registered inspector', 'rgbc': 'registered general building contractor',
    'rsc': 'registered specialist contractor', 'rmwc': 'registered minor works contractor', 'ttsa': 'technically competent person',
    'lmp': 'landscape master plan', 'scg': 'site coverage of greenery', 'pr': 'plot ratio', 'sc': 'site coverage',
    'cdz': 'comprehensive development area', 'cda': 'comprehensive development area', 'gic': 'government, institution or community',
    'tpb': 'town planning board', 'lao': 'lands administration office', 'dg': 'dangerous goods', 'lpg': 'liquefied petroleum gas',
}
ACRO.pop('ttsa')
STOP_SUFFIX = re.compile(r'\s*\((?:pnap|pnrc|jpn|lao|bo|b\(|cap|fs code|cop|section|s\.|reg)[^)]*\)\s*$', re.I)


def sing(w):
    if len(w) > 4 and w.endswith('ies'):
        return w[:-3] + 'y'
    if len(w) > 3 and w.endswith('s') and not w.endswith(('ss', 'us', 'is', "'s")):
        return w[:-1]
    return w


def norm_en(s):
    s = s.strip()
    s = STOP_SUFFIX.sub('', s)  # "overall cap on GFA concessions (PNAP APP-151)" -> base concept
    m = re.match(r'^(.*?)\s*\(([A-Za-z&]{2,6})\)$', s)  # "emergency vehicular access (EVA)"
    if m:
        s = m.group(1)
    s = s.lower().replace('&', ' and ').replace('authorised', 'authorized').replace('unauthorised', 'unauthorized')
    s = s.replace('barrier-free', 'barrier free').replace('re-use', 'reuse').replace('modelling', 'modeling')
    s = re.sub(r"[^\w\s/]", ' ', s)
    s = s.replace('/', ' ')
    toks = [t for t in s.split() if t not in ('the', 'a', 'an', 'of', 'for', 'and', 'on', 'in', 'to')]
    out = []
    for t in toks:  # expand HK acronyms in place so "GFA exemption" meets "exemption from gross floor area"
        if t in ACRO and t not in ('pr', 'sc', 'op', 'ap', 'ri'):
            out += [x for x in re.sub(r'[^\w\s]', ' ', ACRO[t]).split() if x not in ('the', 'of', 'for', 'and', 'or')]
        else:
            out.append(t)
    toks = sorted({sing(t) for t in out if t not in ('from', 'by', 'under', 'with', 'or', 'at')} )
    if not toks:
        return s.strip()
    return ' '.join(toks)


def norm_zh(s):
    if not s:
        return None
    s = re.sub(r'[\s（）()《》「」、，,．.·/／]', '', s)
    s = re.sub(r'[A-Za-z0-9\-]+$', '', s)
    return s or None


def build_concepts():
    tags = tags_all()
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    occ = []  # (doc, en, zh, key_en)
    for t in tags:
        for c in t['concepts']:
            en = (c.get('en') or '').strip()
            if not en:
                continue
            k = 'E:' + norm_en(en)
            find(k)
            occ.append((t['id'], en, c.get('zh'), k))
    # a shared specific Chinese term (4+ chars) merges two English keys only when their words overlap
    # by half or more (stops "qualified person" joining "competent person" through one zh rendering)
    byzh = collections.defaultdict(set)
    for d, en, zh, k in occ:
        z = norm_zh(zh)
        if z and len(z) >= 4:
            byzh[z].add(k)
    for z, ks in byzh.items():
        ks = sorted(ks)
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                ta, tb = set(a[2:].split()), set(b[2:].split())
                if ta and tb and len(ta & tb) / len(ta | tb) >= 0.5:
                    union(a, b)
    groups = collections.defaultdict(list)
    for d, en, zh, k in occ:
        groups[find(k)].append((d, en, zh))
    out = []
    for g, items in groups.items():
        docs = sorted({d for d, _, _ in items})
        ens = collections.Counter(en for _, en, _ in items)
        zhs = collections.Counter(zh for _, _, zh in items if zh)
        # prefer the most common non-acronym form; keep a trailing (ACR) if any variant carries one
        cand = sorted(ens.items(), key=lambda kv: (-kv[1], len(kv[0])))
        best = next((e for e, _ in cand if not re.fullmatch(r'[A-Z&]{2,6}', e)), cand[0][0])
        best = STOP_SUFFIX.sub('', best).strip() or best
        acr = next((m.group(1) for e in ens for m in [re.search(r'\(([A-Z][A-Za-z&]{1,5})\)$', e)] if m), None)
        if acr and acr not in best:
            best = f'{best} ({acr})'
        variants = sorted(set(ens) - {best})
        out.append({'en': best, 'zh': zhs.most_common(1)[0][0] if zhs else None, 'docs': docs, 'count': len(docs),
                    'variants': variants[:8]})

    def distinctive(c):
        e = c['en'] + ' ' + ' '.join(c['variants'])
        if re.search(r'\b[A-Z]{2,}\b|\d', e):
            return True  # acronym, code, standard or year
        caps = re.findall(r'\b[A-Z][a-z]+', c['en'])
        return len(caps) >= 2  # named scheme, ordinance, code or place
    kept = [c for c in out if c['count'] >= 2 or distinctive(c)]
    kept.sort(key=lambda c: (-c['count'], c['en'].lower()))
    for i, c in enumerate(kept):
        c['id'] = f'c{i:04d}'
    res = {'built': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'script': 'pipeline/s5_final.py concepts',
           'method': ['Concepts from the 907 tag records, normalised: case, plurals, punctuation, trailing citation '
                      'brackets, "X (ACR)" forms and a fixed HK acronym list (EVA, GFA, FSI, MiC, SBD, RCHE ...).',
                      'Variants that share the same specific Chinese term (4+ characters) are merged.',
                      'Kept: concepts in 2+ documents, plus single-document concepts that are distinctive '
                      '(an acronym, a code, a standard, a year, or a named scheme / ordinance / code).'],
           'counts': {'raw_strings': len({o[1] for o in occ}), 'merged': len(out), 'kept': len(kept),
                      'kept_multi_doc': sum(c['count'] >= 2 for c in kept),
                      'kept_single_distinctive': sum(c['count'] == 1 for c in kept),
                      'dropped_single': len(out) - len(kept)},
           'concepts': [{k: c[k] for k in ('id', 'en', 'zh', 'count', 'docs', 'variants') if c[k] or k == 'zh'} for c in kept]}
    save(os.path.join(G, 'concepts.json'), res)
    print(res['counts'])
    # concept id lookup per doc for other steps
    return res


# ---------------------------------------------------------------- graph
NODE_KEEP = ['id', 'kind', 'dept', 'series', 'code', 'title_en', 'title_zh', 'status', 'date', 'url_en', 'url_zh',
             'parent', 'cap', 'num', 'label', 'in_force_from', 'version_date', 'has_text', 'index_doc', 'missing_lang',
             'family', 'note']


def build_graph():
    nodes = load(os.path.join(G, 'nodes.json'))
    edges = load(os.path.join(G, 'edges_citations.json'))
    tax = load(os.path.join(G, 'taxonomy.json'))
    tags = {t['id']: t for t in tags_all()}
    conc = load(os.path.join(G, 'concepts.json'))
    doc_c = collections.defaultdict(list)
    for c in conc['concepts']:
        for d in c['docs']:
            doc_c[d].append(c['id'])
    ids = {n['id'] for n in nodes['nodes']}
    # parent ids of legislation cited by each document (instrument / section level)
    leg = collections.defaultdict(set)
    kind = {n['id']: n['kind'] for n in nodes['nodes']}
    for e in edges['edges']:
        if kind.get(e['target']) in ('ordinance', 'regulation', 'section', 'schedule_section', 'part', 'schedule',
                                     'division', 'external_ordinance'):
            leg[e['source']].add(e['target'])
    out_nodes = []
    for n in nodes['nodes']:
        o = {k: n[k] for k in NODE_KEEP if k in n and n[k] not in (None, '', [], {}, False)}
        if n['kind'] == 'document':
            if n.get('has_text') is False:
                o['has_text'] = False
            t = tags[n['id']]
            o.update({'domain': t['domain'], 'domains2': t.get('domains_secondary') or None, 'subjects': t['subjects'],
                      'stages': t['stages'], 'concepts': doc_c.get(n['id']) or None,
                      'summary_en': t['summary_en'], 'summary_zh': t['summary_zh'], 'confidence': t['confidence'],
                      'legislation': sorted(leg.get(n['id'], [])) or None})
            o = {k: v for k, v in o.items() if v not in (None, [], '')}
        out_nodes.append(o)
    solid = []
    for e in edges['edges']:
        # level is derivable from the target node kind; basis and ql are stored only when not the default
        s = {'s': e['source'], 't': e['target'], 'type': e['type'],
             'basis': e['basis'] if e['basis'] != 'text' else None,
             'q': e.get('quote'), 'ql': 'zh' if e.get('quote_lang') == 'zh' else None, 'p': e.get('page'), 'qz': e.get('quote_zh'),
             'pz': e.get('page_zh'), 'pin': e.get('pinpoints'),
             'index': True if e.get('from_index_doc') else None,
             'faint': True if e.get('covered_by_section_edge') else None}
        solid.append({k: v for k, v in s.items() if v not in (None, [], '')})
    bridges = []
    bp = os.path.join(G, 'edges_bridges.json')
    if os.path.exists(bp):
        for b in load(bp)['edges']:
            bridges.append({'s': b['source'], 't': b['target'], 'reason_en': b['reason_en'], 'reason_zh': b['reason_zh'],
                            'ev_s': b['evidence']['source'], 'ev_t': b['evidence']['target'], 'conf': b['confidence']})
    taxo = {'domains': [{k: d[k] for k in ('id', 'name_en', 'name_zh')} for d in tax['domains']],
            'subjects': [{k: s[k] for k in ('id', 'name_en', 'name_zh', 'domain')} for s in tax['subjects']]}
    g = {'built': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'script': 'pipeline/s5_final.py graph',
         'legend': {'solid': 'quotable citation; q = quoted sentence (English unless ql=zh), qz = Chinese quote, p/pz = page; basis omitted = text; index = from an index list; faint = instrument link already covered by a section link',
                    'dashed': 'AI suggestion with a written reason; ev_s / ev_t are short snippets from each document',
                    'parent': 'legislation tree (ordinance > regulation > Part/Schedule > Division > section); structure, not a line',
                    'topics': 'domain / subjects are regions and colours, never lines',
                    'concepts': 'ids into concepts.json'},
         'counts': {'nodes': len(out_nodes), 'solid': len(solid), 'dashed': len(bridges)},
         'taxonomy': taxo, 'nodes': out_nodes, 'edges': {'solid': solid, 'dashed': bridges}}
    p = os.path.join(G, 'graph.json')
    save(p, g, compact=True)
    print('graph.json', os.path.getsize(p), g['counts'])


# ---------------------------------------------------------------- candidates
DEPTS = ('BD', 'LandsD', 'PlanD', 'FSD')
GENERIC_SUBJ = {'plan-submission', 'registration', 'materials', 'maintenance'}


def text_of(did):
    out = {}
    for lang in ('en', 'zh'):
        p = os.path.join(TEXT, f'{did}_{lang}.txt')
        if os.path.exists(p):
            out[lang] = open(p, encoding='utf-8', errors='ignore').read()
    return out


def snippets(txt, terms, n=3, w=220):
    res, seen = [], []
    for term in terms:
        if not term or len(term) < 2:
            continue
        pat = re.escape(term) if not re.fullmatch(r'[A-Za-z &]+', term) else r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'
        for m in re.finditer(pat, txt, re.I):
            if any(abs(m.start() - s) < w for s in seen):
                continue
            seen.append(m.start())
            a = max(0, m.start() - w // 2)
            res.append(re.sub(r'\s+', ' ', txt[a:m.end() + w // 2]))
            break
        if len(res) >= n:
            break
    return res


def build_candidates():
    nodes = load(os.path.join(G, 'nodes.json'))
    edges = load(os.path.join(G, 'edges_citations.json'))
    tags = {t['id']: t for t in tags_all()}
    conc = load(os.path.join(G, 'concepts.json'))['concepts']
    docs = {n['id']: n for n in nodes['nodes'] if n['kind'] == 'document'}
    N = len(docs)
    dc = collections.defaultdict(set)
    cinfo = {c['id']: c for c in conc}
    for c in conc:
        for d in c['docs']:
            dc[d].add(c['id'])
    linked = set()
    anyedge = set()
    for e in edges['edges']:
        anyedge.add(e['source']); anyedge.add(e['target'])
        linked.add(frozenset((e['source'], e['target'])))
    isolated = {d for d in docs if d not in anyedge and docs[d].get('has_text')}
    subj_df = collections.Counter(s for t in tags.values() for s in t['subjects'])
    idf_s = {s: math.log(N / c) for s, c in subj_df.items()}
    idf_c = {c['id']: math.log(N / c['count']) for c in conc}
    ok = [d for d in docs if docs[d].get('has_text') and not docs[d].get('index_doc')]
    # summary-level similarity: the tag summaries and concepts use shared wording across departments
    from sklearn.feature_extraction.text import TfidfVectorizer
    corpus = [docs[d]['title_en'] + '. ' + tags[d]['summary_en'] + ' ' + ' ; '.join(cinfo[c]['en'] for c in dc[d]) for d in ok]
    X = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), min_df=2, sublinear_tf=True).fit_transform(corpus)
    S = (X @ X.T).toarray()

    def tj(x, y):
        wx, wy = set(re.findall(r'[a-z]{3,}', x.lower())), set(re.findall(r'[a-z]{3,}', y.lower()))
        return len(wx & wy) / max(1, len(wx | wy))
    cap131 = {e['source'] for e in edges['edges'] if e['target'] == 'Cap 131'}
    cands = []
    for i, a in enumerate(ok):
        for j in range(i + 1, len(ok)):
            b = ok[j]
            da, db = docs[a]['dept'], docs[b]['dept']
            cross = da != db
            iso = a in isolated or b in isolated
            if not (cross or iso) or frozenset((a, b)) in linked:
                continue
            if not cross:
                # same department: only to pull an isolated doc onto a non-isolated one, never annual re-issues of one letter
                if (a in isolated) == (b in isolated) or tj(docs[a]['title_en'], docs[b]['title_en']) >= 0.5:
                    continue
            sim = S[i, j]
            sc = dc[a] & dc[b]
            ss = (set(tags[a]['subjects']) & set(tags[b]['subjects'])) - GENERIC_SUBJ
            if not ss and not sc:
                continue
            plan = 'PlanD' in (da, db) and cross
            tpo = plan and (a in cap131 or b in cap131)
            if sim < (0.07 if plan else 0.12) and not (sc and sum(idf_c[c] for c in sc) > 9):
                continue
            score = 20 * sim + sum(idf_c[c] for c in sc) + 0.7 * sum(idf_s[s] for s in ss) + (5 if tpo else 0)
            cands.append((score, a, b, sorted(sc), sorted(ss), cross, iso))
    cands.sort(reverse=True)
    per_node = collections.Counter()
    per_pair = collections.Counter()
    quota = {('BD', 'LandsD'): 95, ('BD', 'PlanD'): 45, ('BD', 'FSD'): 85, ('LandsD', 'PlanD'): 55,
             ('FSD', 'LandsD'): 20, ('FSD', 'PlanD'): 12}
    sel = []
    for sc_, a, b, c_, s_, cross, iso in cands:
        pair = tuple(sorted((docs[a]['dept'], docs[b]['dept'])))
        q = quota.get(pair, 25)  # same-dept pairs only reach here via an isolated doc
        cap = 4 if cross else 2
        if per_node[a] >= cap or per_node[b] >= cap or per_pair[pair] >= q:
            continue
        per_node[a] += 1; per_node[b] += 1; per_pair[pair] += 1
        sel.append((sc_, a, b, c_, s_, cross, iso))
    print('pairs scored', len(cands), 'selected', len(sel), dict(per_pair))
    out = []
    tcache = {}
    for sc_, a, b, c_, s_, cross, iso in sel:
        rec = {'score': round(sc_, 2), 'source': a, 'target': b, 'cross_dept': cross, 'isolated_side': [x for x in (a, b) if x in isolated],
               'shared_concepts': [cinfo[c]['en'] for c in c_], 'shared_subjects': s_}
        for side in (a, b):
            if side not in tcache:
                tcache[side] = text_of(side)
            t = tcache[side]
            terms_en, terms_zh = [], []
            for c in c_:
                ci = cinfo[c]
                terms_en += [ci['en'].split(' (')[0]] + ci.get('variants', [])[:3]
                m = re.search(r'\(([A-Z][A-Za-z&]{1,5})\)', ci['en'])
                if m:
                    terms_en.append(m.group(1))
                if ci.get('zh'):
                    terms_zh.append(ci['zh'])
            sn = snippets(t.get('en', ''), terms_en) + snippets(t.get('zh', ''), terms_zh, n=2)
            n = docs[side]
            rec[('src' if side == a else 'tgt')] = {'id': side, 'dept': n['dept'], 'code': n.get('code'), 'title_en': n['title_en'],
                                                    'title_zh': n.get('title_zh'), 'date': n.get('date'),
                                                    'summary_en': tags[side]['summary_en'], 'snippets': sn[:5],
                                                    'text_files': [f'{TEXT}/{side}_{l}.txt' for l in t]}
        out.append(rec)
    os.makedirs(WORK, exist_ok=True)
    k = 5
    for i in range(k):
        save(os.path.join(WORK, f'bridge_candidates_{i + 1}.json'), out[i::k])
    save(os.path.join(WORK, 'bridge_candidates_all.json'), out)
    print('isolated docs', len(isolated))


# ---------------------------------------------------------------- merge verified bridges
def _flat(x):
    return re.sub(r'\s+', '', x or '')


def merge_bridges():
    nodes = load(os.path.join(G, 'nodes.json'))
    edges = load(os.path.join(G, 'edges_citations.json'))
    docs = {n['id']: n for n in nodes['nodes'] if n['kind'] == 'document'}
    linked = {frozenset((e['source'], e['target'])) for e in edges['edges']}
    kept, rejected, dropped = [], [], []
    seen = set()
    for f in sorted(glob.glob(os.path.join(WORK, 'bridges_verified_*.json'))):
        v = load(f)
        rejected += v.get('rejected', [])
        for b in v.get('kept', []):
            a, t = b['source'], b['target']
            why = None
            key = frozenset((a, t))
            if a not in docs or t not in docs:
                why = 'unknown id'
            elif key in linked:
                why = 'already a solid edge'
            elif key in seen:
                why = 'duplicate pair'
            elif re.search('[–—]', b['reason_en'] + b['reason_zh']):
                why = 'dash in reason'
            else:
                for side, did in (('source', a), ('target', t)):
                    txt = _flat(''.join(text_of(did).values()))
                    ev = _flat(b['evidence'][side])
                    if not ev or ev not in txt:
                        why = f'evidence not verbatim in {side}'
                        break
            if why:
                dropped.append({'source': a, 'target': t, 'why': why})
                continue
            seen.add(key)
            da, dt = docs[a]['dept'], docs[t]['dept']
            kept.append({'source': a, 'target': t, 'layer': 'dashed', 'dept_pair': '-'.join(sorted((da, dt))),
                         'relation': b.get('relation'), 'reason_en': b['reason_en'].strip(), 'reason_zh': b['reason_zh'].strip(),
                         'evidence': {'source': b['evidence']['source'].strip(), 'target': b['evidence']['target'].strip()},
                         'evidence_lang': b.get('evidence_lang'), 'confidence': b['confidence']})
    out = {'built': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'script': 'pipeline/s5_final.py bridges',
           'method': ['Candidates: document pairs with no citation between them, across departments or with one side '
                      'having no solid edge, scored by shared normalised concepts, shared specific subjects and '
                      'summary-level TF-IDF similarity; at most 4 per document (2 for same-department pairs).',
                      'Every candidate was read in both texts (<work>/text) by a verifier pass that kept only '
                      'concrete links and wrote the reasons; vague links were rejected.',
                      'Merge checks: both evidence snippets must occur verbatim in the texts (whitespace ignored), '
                      'no dashes, no pair that already has a solid edge.'],
           'counts': {'kept': len(kept), 'rejected_by_verifier': len(rejected), 'dropped_at_merge': len(dropped)},
           'dropped_at_merge': dropped, 'edges': kept}
    save(os.path.join(G, 'edges_bridges.json'), out)
    save(os.path.join(WORK, 'bridges_rejected.json'), rejected)
    print(out['counts'], collections.Counter(k['dept_pair'] for k in kept), collections.Counter(d['why'] for d in dropped))


if __name__ == '__main__':
    {'concepts': build_concepts, 'graph': build_graph, 'candidates': build_candidates, 'bridges': merge_bridges}[sys.argv[1]]()
