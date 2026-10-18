#!/usr/bin/env python3
"""Manufacturer-side check: open each supplier's own site, find its distributor / where-to-buy / contact pages,
and look for an Israel entry. Writes research/enrich/mfr_israel.json:
  {key: {website, pages_checked[], hits[{url, snippet, name, phone, email, known_distributor}], status}}
Usage: python mfr_israel.py [--workers 8] [--limit N] [--only-missing]
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch import HEADERS, extract_links, html_to_text  # noqa: E402

import requests  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUPPLIERS = os.path.join(ROOT, "data", "suppliers.json")
REGISTRY = os.path.join(ROOT, "research", "israel", "distributors.json")
OUT = os.path.join(ROOT, "research", "enrich", "mfr_israel.json")

LINK_RX = re.compile(r"distribut|dealer|where.?to.?buy|how.?to.?buy|reseller|representativ|sales.?network|sales.?partner|international|worldwide|countr|find.?a|locations?|partner|agents?|contact|global|region", re.I)
PRIO_RX = re.compile(r"distribut|dealer|where.?to.?buy|how.?to.?buy|reseller|representativ|sales.?network|international|worldwide|countr|find.?a", re.I)
GUESSES = ["/distributors", "/distributor", "/where-to-buy", "/international-distributors", "/dealers", "/find-a-distributor", "/partners/distributors",
           "/en/distributors", "/distributors/", "/international", "/sales-network", "/contact/distributors", "/global-distributors", "/resellers", "/where-to-buy/"]
ISRAEL_RX = re.compile(r"\bIsrael\b|ישראל", re.I)
KNOWN = {
    "labotal": "Labotal Scientific Equipment Ltd.", "medent": "Medent Scientific Instruments", "agentek": "Agentek (1987) Ltd.", "lifegene": "Lifegene Ltd.",
    "danyel": "Danyel Biotech Ltd.", "bargal": "Bargal Analytical Instruments Ltd.", "rhenium": "Rhenium Ltd.", "ilex": "Ilex Medical Ltd.", "getter": "Getter Group",
    "lumitron": "Lumitron Ltd.", "gamidor": "Gamidor Diagnostics", "eldan": "Eldan Electronic Instruments Ltd.", "almog": "Y.A. Almog Diagnostic & Medical Equipment Ltd.",
    "zotal": "Zotal Ltd.", "eisenberg": "Eisenberg Bros. Ltd.", "ophir": "Ophir Analytical Ltd.", "spectro israel": "Spectro (Israel) Ltd.", "citrine": "Citrine Solutions",
    "moran": "S.L. Moran Ltd.", "mrc": "MRC Laboratory Equipment & Instruments", "tamar": "Tamar Laboratory Supplies Ltd.", "mercury": "Mercury Scientific & Industrial Products Ltd.",
    "lapidot": "Lapidot Medical", "enco": "Enco Scientific Services Ltd.", "israel scientific instruments": "Israel Scientific Instruments Ltd. (ISI)", "beit haemek": "IM Beit HaEmek",
    "bemek": "IM Beit HaEmek", "ornat": "Ornat BioChemicals & Lab Equipment Ltd.", "tarom": "Tarom Applied Technologies Ltd.", "picotech": "PicoTech Ltd.",
    "yarden": "Yarden Biotec", "jordan biotech": "Yarden Biotec", "agrolan": "Agrolan Ltd.", "new-road": "New-Road Agencies Ltd.", "new road": "New-Road Agencies Ltd.",
    "golik": "Dr. Golik Scientific Solutions", "prime lab": "Prime Lab Scientific Instruments Ltd.", "primelab": "Prime Lab Scientific Instruments Ltd.", "modotec": "Modotec Ltd.",
    "bioanalytics": "BioAnalytics", "dyn diagnostics": "Dyn Diagnostics", "dover": "Dover Medical & Scientific Equipment", "bepex": "Bepex", "avni": "Avni & Son",
    "master-cold": "Master-Cold", "master cold": "Master-Cold", "ormir": "Ormir Lab Equipment", "ex-lab": "Ex-Lab", "exlab": "Ex-Lab", "hylabs": "HyLabs (Hy Laboratories Ltd.)",
    "hy laboratories": "HyLabs (Hy Laboratories Ltd.)", "bdl": "BDL", "electrotherm": "Electrotherm Marketing 1978 Ltd.", "newtech": "Newtech Ayalon Ltd.", "medtechnica": "Medtechnica",
    "bio-lab": "Bio-Lab Ltd.", "tivan": "Tivan Biotech", "nano instruments": "Nano Instruments Ltd.", "advanced technological solutions": "Advanced Technological Solutions Ltd. (ATSL)",
    "doron": "Doron Scientific", "yair": "Yair Technologies", "nbt": "New Biotechnology Ltd. (NBT)", "new biotechnology": "New Biotechnology Ltd. (NBT)", "origolab": "Origolab Ltd.",
    "syntezza": "Syntezza Bioscience Ltd.", "sigma-aldrich israel": "Sigma-Aldrich Israel Ltd.", "merck israel": "Merck Israel", "bio-rad israel": "Bio-Rad Israel",
    "thermo fisher scientific israel": "Thermo Fisher Scientific Israel", "rhenium bio": "Rhenium Ltd.", "gamida": "Danyel Biotech Ltd. (Gamida for Life group)",
    "alpha-omega": "Alpha Omega", "ravin": "Ravin Lab", "mediterranean": "Mediterranean Scientific", "gadot": "Gadot group (Mercury)", "danyel biotech": "Danyel Biotech Ltd.",
}
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(r"(?:\+\s?972|\(972\)|00972|\b0)[\s\-\.]?\(?\d{1,2}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}")
COMPANY_RX = re.compile(r"\b(ltd|inc|llc|gmbh|scientific|lab|labs|laborator|tech|bio|medical|diagnost|instrument|equipment|group|systems|solutions|industries|trading|agencies|engineering|supply|supplies|co\b|company|sons?|bros)\b", re.I)


def get(url, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    if "charset" not in r.headers.get("content-type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"
    return r


def snippets(text, url):
    out = []
    for m in ISRAEL_RX.finditer(text):
        a, b = max(0, m.start() - 260), min(len(text), m.end() + 320)
        snip = text[a:b]
        out.append(snip)
        if len(out) >= 4:
            break
    return [{"url": url, "snippet": re.sub(r"[ \t]+", " ", s).strip()} for s in out]


def interpret(hit):
    """Pull a distributor name / contact out of the snippet around 'Israel'."""
    s = hit["snippet"]
    low = s.lower()
    known = next((v for k, v in KNOWN.items() if k in low), None)
    emails = [e for e in EMAIL_RX.findall(s) if re.match(r"(info|sales|office|contact|mail|support|service|orders?|lab|marketing|export)@", e, re.I)]
    phones = [re.sub(r"\s+", " ", p).strip() for p in PHONE_RX.findall(s)]
    name = known
    if not name:
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
        idx = next((i for i, ln in enumerate(lines) if ISRAEL_RX.search(ln)), None)
        if idx is not None:
            cands = []
            for j in (idx, idx + 1, idx - 1, idx + 2):
                if 0 <= j < len(lines):
                    ln = re.sub(r"\bIsrael\b[:\-–]*", "", lines[j]).strip(" :-–,|")
                    if 3 <= len(ln) <= 70 and COMPANY_RX.search(ln) and not re.search(r"@|www\.|http|\d{5,}|tel|phone|fax|email", ln, re.I):
                        cands.append(ln)
            if cands:
                name = cands[0]
    hit["name"] = name
    hit["known_distributor"] = bool(known)
    hit["email"] = emails[0] if emails else None
    hit["phone"] = phones[0] if phones else None
    return hit


def process(key, website):
    rec = {"website": website, "pages_checked": [], "hits": [], "status": None}
    try:
        r = get(website)
    except Exception as e:
        rec["status"] = f"error: {type(e).__name__}"
        return rec
    rec["status"] = r.status_code
    if r.status_code >= 400:
        return rec
    base = r.url
    host = urlparse(base).netloc.lower().replace("www.", "")
    text = html_to_text(r.text)
    rec["pages_checked"].append(base)
    rec["hits"] += snippets(text, base)
    links = []
    for l in extract_links(r.text, base):
        h = l["href"]
        if urlparse(h).netloc.lower().replace("www.", "") != host:
            continue
        t = (l.get("text") or "") + " " + h
        if LINK_RX.search(t):
            links.append((0 if PRIO_RX.search(t) else 1, h))
    seen = set()
    ordered = [h for _, h in sorted(links, key=lambda x: x[0]) if not (h in seen or seen.add(h))][:6]
    if not any(PRIO_RX.search(h) for h in ordered):
        ordered += [urljoin(base, g) for g in GUESSES[:6]]
    for h in ordered:
        if len(rec["hits"]) >= 6:
            break
        try:
            r2 = get(h, timeout=20)
            if r2.status_code >= 400 or "html" not in r2.headers.get("content-type", "").lower():
                continue
            rec["pages_checked"].append(r2.url)
            rec["hits"] += snippets(html_to_text(r2.text), r2.url)
        except Exception:
            continue
        time.sleep(0.2)
    rec["hits"] = [interpret(h) for h in rec["hits"][:6]]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-missing", action="store_true")
    args = ap.parse_args()
    rows = json.load(open(SUPPLIERS, encoding="utf-8"))["suppliers"]
    cache = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = [(r["key"], r["website"]) for r in rows if r.get("website") and not (args.only_missing and r["key"] in cache)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} supplier sites to check", flush=True)
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, k, w): k for k, w in todo}
        for fu in as_completed(futs):
            k = futs[fu]
            try:
                cache[k] = fu.result()
            except Exception as e:
                cache[k] = {"status": f"error: {type(e).__name__}: {e}", "hits": [], "pages_checked": []}
            done += 1
            if done % 25 == 0 or done == len(todo):
                n_hit = sum(1 for v in cache.values() if v.get("hits"))
                print(f"[{done}/{len(todo)}] sites with an Israel mention: {n_hit} ({time.time() - t0:.0f}s)", flush=True)
                json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done:", len(cache), "checked; with Israel mention:", sum(1 for v in cache.values() if v.get("hits")), "; with a recognised distributor:", sum(1 for v in cache.values() if any(h.get("known_distributor") for h in v.get("hits", []))))


if __name__ == "__main__":
    main()
