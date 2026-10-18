#!/usr/bin/env python3
"""Resolve supplier names to companies: official website, country, HQ, employees, revenue.
Sources: Wikidata (wbsearchentities + wbgetentities) and the Clearbit autocomplete API (domain only).
Reads research/catalog_suppliers.json, writes research/enrich/resolved.json (cache; re-runnable).

Usage: python resolve_companies.py [--limit N] [--only-missing]
"""
import argparse
import json
import os
import re
import time
from difflib import SequenceMatcher

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "research", "catalog_suppliers.json")
OUT_DIR = os.path.join(ROOT, "research", "enrich")
OUT = os.path.join(OUT_DIR, "resolved.json")
UA = "lab-supplier-db/1.0 (research; contact via github.com/ditri12)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})

BUSINESS_CLASSES = {"Q4830453", "Q6881511", "Q783794", "Q187939", "Q43229", "Q431289", "Q1058914", "Q18388277",
                    "Q167037", "Q891723", "Q2659904", "Q1616075", "Q5225895", "Q655686", "Q22687", "Q1589009",
                    "Q134161", "Q219577", "Q1762059", "Q12047059", "Q7094076", "Q154954", "Q4671277", "Q17127659"}
# business, enterprise, company, manufacturer, organization, brand, software company, biotech company, corporation,
# public company, business group, conglomerate, subsidiary, commercial organization, bank(no), privately held co.,
# joint-stock co., holding co., trade name, medical device company, chemical company, pharmaceutical company,
# limited company, legal person(ish), scientific instrument manufacturer


def sim(a, b):
    a = re.sub(r"[^a-z0-9]+", " ", a.lower()).strip()
    b = re.sub(r"[^a-z0-9]+", " ", b.lower()).strip()
    return SequenceMatcher(None, a, b).ratio()


def wd_search(name, limit=6):
    r = S.get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": name,
              "language": "en", "type": "item", "limit": limit, "format": "json"}, timeout=30)
    r.raise_for_status()
    return r.json().get("search", [])


def wd_entities(ids):
    r = S.get("https://www.wikidata.org/w/api.php", params={"action": "wbgetentities", "ids": "|".join(ids),
              "props": "labels|descriptions|claims|sitelinks", "languages": "en|he|fr|de", "format": "json"}, timeout=60)
    r.raise_for_status()
    return r.json().get("entities", {})


def claim_vals(ent, pid):
    out = []
    for c in ent.get("claims", {}).get(pid, []):
        ms = c.get("mainsnak", {})
        dv = ms.get("datavalue", {}).get("value")
        if dv is None:
            continue
        quals = c.get("qualifiers", {})
        pit = None
        for q in quals.get("P585", []) + quals.get("P580", []):
            v = q.get("datavalue", {}).get("value", {})
            if isinstance(v, dict) and v.get("time"):
                pit = v["time"][1:5]
        unit = None
        if isinstance(dv, dict) and dv.get("unit") and dv["unit"] != "1":
            unit = dv["unit"].rsplit("/", 1)[-1]
        rank = c.get("rank")
        out.append({"value": dv, "time": pit, "unit": unit, "rank": rank})
    return out


def best_quantity(vals):
    """Pick the most recent (by qualifier time), prefer preferred rank."""
    cand = []
    for v in vals:
        q = v["value"]
        if isinstance(q, dict) and "amount" in q:
            try:
                amt = float(q["amount"])
            except Exception:
                continue
            cand.append((v["rank"] == "preferred", v["time"] or "", amt, v["unit"]))
    if not cand:
        return None
    cand.sort(reverse=True)
    pref, t, amt, unit = cand[0]
    return {"value": amt, "year": t or None, "unit": unit}


LABEL_CACHE = {}


def labels_for(ids):
    need = [i for i in ids if i not in LABEL_CACHE]
    for k in range(0, len(need), 50):
        chunk = need[k:k + 50]
        r = S.get("https://www.wikidata.org/w/api.php", params={"action": "wbgetentities", "ids": "|".join(chunk),
                  "props": "labels", "languages": "en", "format": "json"}, timeout=60)
        if r.ok:
            for qid, e in r.json().get("entities", {}).items():
                LABEL_CACHE[qid] = e.get("labels", {}).get("en", {}).get("value")
        time.sleep(0.2)
    return {i: LABEL_CACHE.get(i) for i in ids}


def resolve_wikidata(name):
    hits = wd_search(name)
    if not hits:
        return None
    ents = wd_entities([h["id"] for h in hits])
    best = None
    for h in hits:
        e = ents.get(h["id"], {})
        inst = [v["value"].get("id") for v in claim_vals(e, "P31") if isinstance(v["value"], dict)]
        desc = e.get("descriptions", {}).get("en", {}).get("value", "")
        is_biz = bool(set(inst) & BUSINESS_CLASSES) or re.search(r"compan|manufactur|business|enterprise|brand|corporation|supplier|producer", desc, re.I)
        if not is_biz:
            continue
        label = e.get("labels", {}).get("en", {}).get("value", h.get("label", ""))
        aliases = [h.get("label", "")] + [a.get("value") for a in e.get("aliases", {}).get("en", [])] if e.get("aliases") else [h.get("label", "")]
        score = max(sim(name, x) for x in [label] + [a for a in aliases if a])
        if best is None or score > best[0]:
            best = (score, h["id"], e, inst, desc, label)
    if not best or best[0] < 0.72:
        return None
    score, qid, e, inst, desc, label = best
    web = [v["value"] for v in claim_vals(e, "P856") if isinstance(v["value"], str)]
    country = [v["value"]["id"] for v in claim_vals(e, "P17") if isinstance(v["value"], dict)]
    hq = [v["value"]["id"] for v in claim_vals(e, "P159") if isinstance(v["value"], dict)]
    parent = [v["value"]["id"] for v in claim_vals(e, "P749") if isinstance(v["value"], dict)]
    industry = [v["value"]["id"] for v in claim_vals(e, "P452") if isinstance(v["value"], dict)]
    inception = [v["value"].get("time", "")[1:5] for v in claim_vals(e, "P571") if isinstance(v["value"], dict)]
    emp = best_quantity(claim_vals(e, "P1128"))
    rev = best_quantity(claim_vals(e, "P2139"))
    ids = list(dict.fromkeys(country + hq + parent + industry + (([emp["unit"]] if emp and emp.get("unit") else [])) + (([rev["unit"]] if rev and rev.get("unit") else []))))
    lab = labels_for([i for i in ids if i and i.startswith("Q")]) if ids else {}
    return {"qid": qid, "label": label, "score": round(score, 3), "description": desc,
            "website": web[0] if web else None,
            "country": [lab.get(c) for c in country][:2], "hq": [lab.get(c) for c in hq][:2],
            "parent": [lab.get(c) for c in parent][:2], "industry": [lab.get(c) for c in industry][:3],
            "inception": inception[0] if inception else None,
            "employees": {"value": emp["value"], "year": emp["year"]} if emp else None,
            "revenue": {"value": rev["value"], "year": rev["year"], "currency": lab.get(rev["unit"]) if rev.get("unit") else None} if rev else None,
            "sitelinks": len(e.get("sitelinks", {}))}


def resolve_clearbit(name):
    try:
        r = S.get("https://autocomplete.clearbit.com/v1/companies/suggest", params={"query": name}, timeout=20)
        if not r.ok:
            return None
        hits = r.json()
    except Exception:
        return None
    best = None
    for h in hits[:5]:
        score = sim(name, h.get("name", ""))
        if best is None or score > best[0]:
            best = (score, h)
    if not best:
        return None
    return {"name": best[1].get("name"), "domain": best[1].get("domain"), "score": round(best[0], 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-missing", action="store_true")
    args = ap.parse_args()
    rows = json.load(open(IN, encoding="utf-8"))
    os.makedirs(OUT_DIR, exist_ok=True)
    cache = {}
    if os.path.exists(OUT):
        cache = {r["key"]: r for r in json.load(open(OUT, encoding="utf-8"))}
    todo = [r for r in rows if not (args.only_missing and r["key"] in cache)]
    if args.limit:
        todo = todo[:args.limit]
    t0 = time.time()
    for i, r in enumerate(todo, 1):
        name = r["name"]
        rec = {"key": r["key"], "name": name, "wikidata": None, "clearbit": None, "error": None}
        try:
            rec["wikidata"] = resolve_wikidata(name)
        except Exception as e:
            rec["error"] = f"wd: {type(e).__name__}: {e}"
        time.sleep(0.3)
        rec["clearbit"] = resolve_clearbit(name)
        time.sleep(0.2)
        cache[r["key"]] = rec
        if i % 20 == 0 or i == len(todo):
            print(f"[{i}/{len(todo)}] {name} -> wd={bool(rec['wikidata'])} cb={(rec['clearbit'] or {}).get('domain')} ({time.time()-t0:.0f}s)", flush=True)
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(list(cache.values()), f, ensure_ascii=False, indent=1)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(list(cache.values()), f, ensure_ascii=False, indent=1)
    n_wd = sum(1 for v in cache.values() if v.get("wikidata"))
    n_cb = sum(1 for v in cache.values() if (v.get("clearbit") or {}).get("domain"))
    print(f"done: {len(cache)} names, wikidata {n_wd}, clearbit domain {n_cb}")


if __name__ == "__main__":
    main()
