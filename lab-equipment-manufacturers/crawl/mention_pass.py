#!/usr/bin/env python3
"""Inclusive pass: supplier names mentioned anywhere in the crawled Israeli distributor pages (word-boundary,
>=2 mentions, or 1 mention on a product/brand page). Lower confidence than match_israel.py; written to
research/enrich/israel_mentions.json for keys/sites not already matched."""
import json, re, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_lists import norm
from match_israel import GENERIC, SRC_DIRS
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {'genie', 'slice', 'sampling systems', 'molecular biology products', 'quality biological', 'sharp', 'marvel', 'apex', 'falcon', 'bemis',
        'mapa professional', 'precision', 'universal', 'crystal', 'eagle', 'prime', 'select', 'kango', 'spectrum', 'thomas', 'brand', 'corning gosselin'}
master = json.load(open(os.path.join(ROOT, 'research', 'catalog_suppliers.json')))
reg = json.load(open(os.path.join(ROOT, 'research', 'israel', 'distributors.json')))
existing = json.load(open(os.path.join(ROOT, 'research', 'enrich', 'israel_matches.json')))
corp = collections.defaultdict(list)
for d in SRC_DIRS:
    for e in json.load(open(os.path.join(d, 'index.json'))):
        if e.get('error') or not e.get('status') or e['status'] >= 400:
            continue
        root = e['id'].split('__')[0]
        p = os.path.join(d, e['id'] + '.txt')
        t = open(p, encoding='utf-8').read() if os.path.exists(p) else ''
        lj = os.path.join(d, e['id'] + '.links.json')
        if os.path.exists(lj):
            t += '\n' + '\n'.join((l.get('text') or '') + ' ' + (l.get('alt') or '') for l in json.load(open(lj)))
        site = (reg.get(root) or {}).get('site') or root
        corp[site].append((norm(t), e.get('final_url') or e['url'], t, root))
have = {k: {h['site'] for h in v} for k, v in existing.items()}
new = collections.defaultdict(list)
for m in master:
    key = m['key']; toks = key.split()
    if key in DROP or (len(toks) == 1 and (key in GENERIC or len(key) < 6)) or (len(toks) >= 2 and all(t in GENERIC for t in toks)):
        continue
    rx = re.compile(r'(?<![a-z0-9])' + re.escape(key) + r'(?![a-z0-9])')
    for site, lst in corp.items():
        if site in have.get(key, set()):
            continue
        hits = [(len(rx.findall(nt)), u, t, r) for nt, u, t, r in lst if key in nt]
        hits = [h for h in hits if h[0]]
        total = sum(h[0] for h in hits)
        if total >= 2 or (total == 1 and re.search(r'product|brand|supplier|manufactur|catalog|מוצר|מותג|ספק|יצרן', hits[0][1], re.I)):
            n, u, t, r = max(hits)
            ev = next((ln.strip() for ln in t.splitlines() if key in norm(ln)), '')[:120]
            new[key].append({"distributor": r, "site": site, "page_url": u, "evidence": ev, "confidence": "mention", "mentions": total, "evidence_year": 2026})
out = os.path.join(ROOT, 'research', 'enrich', 'israel_mentions.json')
json.dump(dict(new), open(out, 'w'), ensure_ascii=False, indent=1)
print('mention-level: suppliers', len(new), 'hits', sum(len(v) for v in new.values()))
