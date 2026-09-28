"""S7 step 3: merge graph.json + fixes.json + the QA'd v2 tags into graph/graph_final.json, and rebuild concepts.json.

Usage: python s7_merge.py
  1. concepts.json is rebuilt from tags/batch_*_tags_v2.json (same method as s5_final.py concepts; old file kept as concepts_s5.json)
  2. every document node takes its v2 tags (domain, subjects, stages, concepts, summaries, confidence, notes, qa)
  3. fixes.json field fixes are applied (value None removes the field); edges_remove / edges_add applied to the solid layer
  4. superseded / repealed docs without an explicit superseded_by take the unique source of an incoming 'supersedes' edge
Then run: python s6_build_data.py && python s6_bake_layout.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, os, glob, shutil, datetime, collections as C
import s5_final

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, 'graph')
load, save = s5_final.load, s5_final.save


def tags_v2():
    out = []
    for f in sorted(glob.glob(os.path.join(G, 'tags', 'batch_*_tags_v2.json'))):
        out += load(f)
    return out


def main():
    graph = load(os.path.join(G, 'graph.json'))
    fixes = load(os.path.join(G, 'fixes.json'))
    tags = {t['id']: t for t in tags_v2()}

    # ---- 1. concepts from the v2 tags ----
    old = os.path.join(G, 'concepts.json')
    if not os.path.exists(os.path.join(G, 'concepts_s5.json')):
        shutil.copy(old, os.path.join(G, 'concepts_s5.json'))
    s5_final.tags_all = tags_v2          # build_concepts reads tags through this module-level function
    conc = s5_final.build_concepts()      # writes graph/concepts.json
    conc['script'] = 'pipeline/s7_merge.py (s5_final.build_concepts over batch_*_tags_v2.json)'
    save(old, conc)
    doc_c = C.defaultdict(list)
    for c in conc['concepts']:
        for d in c['docs']:
            doc_c[d].append(c['id'])

    nodes = graph['nodes']
    byid = {n['id']: n for n in nodes}
    docs = [n for n in nodes if n['kind'] == 'document']
    missing_tags = [n['id'] for n in docs if n['id'] not in tags]
    extra_tags = [t for t in tags if t not in byid]
    assert not missing_tags and not extra_tags, (missing_tags[:5], extra_tags[:5])

    # ---- 2. v2 tags ----
    for n in docs:
        t = tags[n['id']]
        n.update({'domain': t['domain'], 'domains2': t.get('domains_secondary') or None, 'subjects': t['subjects'],
                  'stages': t['stages'], 'concepts': doc_c.get(n['id']) or None, 'summary_en': t['summary_en'],
                  'summary_zh': t['summary_zh'], 'confidence': t['confidence'], 'notes': t.get('notes') or None,
                  'qa': t['qa'], 'qa_changed': t.get('qa_changed'), 'qa_note': t.get('qa_note') or None})
        for k in [k for k, v in n.items() if v is None or v == []]:
            n.pop(k)

    # ---- 3. field fixes ----
    applied = C.Counter()
    for did, fs in fixes['fixes'].items():
        n = byid[did]
        for field, fx in fs.items():
            v = fx['value']
            if v is None or v == []:
                n.pop(field, None)
            else:
                n[field] = v
            applied[field] += 1
    for did, items in fixes['unresolved'].items():
        byid[did]['unresolved'] = [i['reason'] for i in items]

    # ---- edges ----
    solid = graph['edges']['solid']
    rm = {(e['s'], e['t'], e['type']) for e in fixes['edges_remove']}
    before = len(solid)
    solid = [e for e in solid if (e['s'], e['t'], e['type']) not in rm]
    removed = before - len(solid)
    have = {(e['s'], e['t'], e['type']) for e in solid}
    added = 0
    for e in fixes['edges_add']:
        k = (e['s'], e['t'], e['type'])
        if k in have:
            continue
        o = {'s': e['s'], 't': e['t'], 'type': e['type'], 'q': e['q'], 'basis': 'fix'}
        if e.get('ql') == 'zh':
            o['ql'] = 'zh'
        if e.get('note'):
            o['note'] = e['note']
        solid.append(o); have.add(k); added += 1
    graph['edges']['solid'] = solid

    # ---- 3b. manual overrides found in the S7 visual QA ----
    # FSD CL 3/2020: FSD publishes no file for it; the stored text was CL 1/2024, so the v2 summary described the wrong
    # document ("Stored text is not this letter ..."). Rewritten from the title and FSD's obsolete list (fixes.json evidence).
    n = byid['FSD_FSD-CL-3-2020']
    n.update({'summary_en': 'Set out facilitation measures for applications for approval of portable equipment and for the acceptance of '
                            'fire service installations and equipment and fire safety products. FSD lists it as obsolete: FSD CL 1/2024 '
                            'cancelled and replaced it from 1 April 2024.',
              'summary_zh': '關於申請認可手提設備及接納消防裝置及設備和消防安全產品的便利措施。消防處已將本通函列為過時通函：'
                            '消防處通函第1/2024號自2024年4月1日起取消並取代本通函。',
              'qa': 'no-source-text', 'confidence': 'medium',
              'qa_note': 'S7 merge override: no published file; summary from the title and the FSD obsolete list'})
    applied['override_summary'] += 1

    # ---- 4. superseded_by from supersedes edges where the patch gave none ----
    inc = C.defaultdict(set)
    for e in solid:
        if e['type'] == 'supersedes':
            inc[e['t']].add(e['s'])
    inferred = 0
    for n in docs:
        if n.get('status') in ('superseded', 'repealed') and not n.get('superseded_by') and len(inc.get(n['id'], ())) == 1:
            n['superseded_by'] = next(iter(inc[n['id']])); n['superseded_by_src'] = 'edge'; inferred += 1

    # ---- stats ----
    dashed = graph['edges']['dashed']
    touch_s, touch_b = set(), set()
    for e in solid:
        touch_s.update((e['s'], e['t']))
    for b in dashed:
        touch_b.update((b['s'], b['t']))
    ids = {n['id'] for n in docs}
    iso_solid = [d for d in ids if d not in touch_s]
    iso_all = [d for d in iso_solid if d not in touch_b]
    faded = [n for n in docs if n.get('status') in ('superseded', 'repealed', 'obsolete') or str(n.get('status', '')).startswith('cancelled') or n.get('duplicate_of')]
    stats = {'nodes': len(nodes), 'documents': len(docs), 'solid': len(solid), 'dashed': len(dashed),
             'edges_removed': removed, 'edges_added': added, 'superseded_by_inferred': inferred,
             'docs_without_solid_edge': len(iso_solid), 'docs_isolated': len(iso_all),
             'isolated_share': round(len(iso_all) / len(docs), 4), 'no_solid_share': round(len(iso_solid) / len(docs), 4),
             'faded_docs': len(faded), 'title_only_summaries': sum(1 for n in docs if n.get('qa') != 'full-text-checked'),
             'concepts': len(conc['concepts']), 'field_fixes_applied': sum(applied.values())}

    graph['built'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    graph['script'] = 'pipeline/s7_merge.py (graph.json + fixes.json + tags v2)'
    graph['counts'] = {'nodes': len(nodes), 'solid': len(solid), 'dashed': len(dashed)}
    graph['legend']['fixes'] = ('fields from fixes.json (evidence there): date, title_zh, zh_version (false = no Chinese text published), '
                                'duplicate_of, counterpart_of, series_group, status, superseded_by, historic, legacy_scope ...; '
                                'solid edges with basis=fix came from fixes.json edges_add')
    graph['legend']['qa'] = "tag QA: full-text-checked, or no-source-text / no-text-title-only (summary written from the title only)"
    graph['merge'] = {'stats': stats, 'fields_applied': dict(applied), 'fixes_built': fixes['meta']['built']}
    save(os.path.join(G, 'graph_final.json'), graph, compact=True)
    print(json.dumps(stats, indent=1))
    print('fields applied', dict(applied.most_common()))


if __name__ == '__main__':
    main()
