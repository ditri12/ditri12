#!/usr/bin/env python3
"""Batched Wikidata SPARQL resolution by exact English label / alias for suppliers that still lack a
Wikidata match in research/enrich/resolved.json (fills the same 'wikidata' structure).
~50 names per query, so the whole master list needs about 30 requests."""
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "research", "catalog_suppliers.json")
OUT = os.path.join(ROOT, "research", "enrich", "resolved.json")
UA = "lab-supplier-db/1.0 (research; github.com/ditri12) python-requests"
ENDPOINT = "https://query.wikidata.org/sparql"
BUSINESS = {"Q4830453", "Q6881511", "Q783794", "Q187939", "Q43229", "Q431289", "Q1058914", "Q18388277", "Q167037", "Q891723",
            "Q2659904", "Q1616075", "Q5225895", "Q655686", "Q22687", "Q1589009", "Q134161", "Q219577", "Q1762059", "Q12047059",
            "Q7094076", "Q154954", "Q4671277", "Q17127659", "Q3918409", "Q1137109", "Q2995256", "Q1335012", "Q19295990"}

QUERY = """
SELECT ?name ?item ?itemLabel ?itemDescription ?class ?website ?countryLabel ?hqLabel ?parentLabel ?inception ?emp ?empDate ?rev ?revDate ?revUnitLabel ?sitelinks WHERE {
  VALUES ?name { %s }
  { ?item rdfs:label ?name } UNION { ?item skos:altLabel ?name }
  ?item wdt:P31 ?class .
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P17 ?country }
  OPTIONAL { ?item wdt:P159 ?hq }
  OPTIONAL { ?item wdt:P749 ?parent }
  OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL { ?item p:P1128 ?es . ?es ps:P1128 ?emp . OPTIONAL { ?es pq:P585 ?empDate } }
  OPTIONAL { ?item p:P2139 ?rs . ?rs ps:P2139 ?rev . OPTIONAL { ?rs pq:P585 ?revDate } OPTIONAL { ?rs psv:P2139 ?rv . ?rv wikibase:quantityUnit ?revUnit } }
  OPTIONAL { ?item wikibase:sitelinks ?sitelinks }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def run(names):
    vals = " ".join('"%s"@en' % n.replace('"', '\\"') for n in names)
    for attempt in range(6):
        r = requests.get(ENDPOINT, params={"query": QUERY % vals, "format": "json"},
                         headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}, timeout=120)
        if r.status_code in (429, 503, 500, 502):
            ra = r.headers.get("Retry-After")
            time.sleep(float(ra) if ra and ra.isdigit() else 10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["results"]["bindings"]
    r.raise_for_status()
    return []


def v(b, k):
    return b[k]["value"] if k in b else None


def main():
    master = json.load(open(MASTER, encoding="utf-8"))
    res = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else []
    byk = {r["key"]: r for r in res}
    todo = [m for m in master if not (byk.get(m["key"]) or {}).get("wikidata")]
    print(f"{len(todo)} suppliers without a Wikidata match", flush=True)
    found = 0
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        name_to_key = {}
        for m in chunk:
            for n in set([m["name"]] + (m.get("names") or [])):
                name_to_key[n] = m["key"]
        try:
            rows = run(list(name_to_key))
        except Exception as e:
            print("batch failed:", e, flush=True)
            time.sleep(15)
            continue
        per = {}
        for b in rows:
            name = v(b, "name")
            key = name_to_key.get(name)
            if not key:
                continue
            cls = (v(b, "class") or "").rsplit("/", 1)[-1]
            desc = v(b, "itemDescription") or ""
            if cls not in BUSINESS and not re.search(r"compan|manufactur|business|enterprise|brand|corporation|supplier|producer", desc, re.I):
                continue
            qid = v(b, "item").rsplit("/", 1)[-1]
            e = per.setdefault(key, {}).setdefault(qid, {"qid": qid, "label": v(b, "itemLabel"), "score": 1.0, "description": desc, "website": None,
                                                        "country": [], "hq": [], "parent": [], "industry": [], "inception": None,
                                                        "employees": None, "revenue": None, "sitelinks": int(float(v(b, "sitelinks") or 0)), "_emp": [], "_rev": []})
            e["website"] = e["website"] or v(b, "website")
            for fld, k2 in (("country", "countryLabel"), ("hq", "hqLabel"), ("parent", "parentLabel")):
                val = v(b, k2)
                if val and val not in e[fld] and not re.match(r"^Q\d+$", val):
                    e[fld].append(val)
            if v(b, "inception") and not e["inception"]:
                e["inception"] = v(b, "inception")[:4]
            if v(b, "emp"):
                e["_emp"].append((v(b, "empDate") or "", float(v(b, "emp"))))
            if v(b, "rev"):
                e["_rev"].append((v(b, "revDate") or "", float(v(b, "rev")), v(b, "revUnitLabel")))
        for key, cands in per.items():
            # prefer the entity with most sitelinks, then with size data
            best = max(cands.values(), key=lambda e: ((e["sitelinks"] or 0), bool(e["_emp"]) + bool(e["_rev"])))
            if best["_emp"]:
                d, n = max(best["_emp"])
                best["employees"] = {"value": n, "year": d[:4] if d else None}
            if best["_rev"]:
                d, n, u = max(best["_rev"])
                best["revenue"] = {"value": n, "year": d[:4] if d else None, "currency": u}
            best.pop("_emp"); best.pop("_rev")
            rec = byk.get(key)
            if rec is None:
                rec = {"key": key, "name": next(m["name"] for m in chunk if m["key"] == key), "wikidata": None, "clearbit": None, "error": None}
                res.append(rec); byk[key] = rec
            rec["wikidata"] = best
            rec["error"] = None
            found += 1
        print(f"[{min(i + 40, len(todo))}/{len(todo)}] matched so far: {found}", flush=True)
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(4)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done; new matches:", found)


if __name__ == "__main__":
    main()
