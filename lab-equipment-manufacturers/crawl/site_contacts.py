#!/usr/bin/env python3
"""Collect general contact details (phone, role e-mail, contact page) from each supplier's own website.

Reads  research/catalog_suppliers.json + research/enrich/resolved.json (+ overrides/prior for websites)
Writes research/enrich/site_contacts.json  {master_key: {website, phone, email, contact_url, address, source, note, status}}
Pages are fetched to a temporary directory and are not kept.

Usage: python site_contacts.py [--limit N] [--only-missing] [--workers 6] [--render-fallback]
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
MASTER = os.path.join(ROOT, "research", "catalog_suppliers.json")
RESOLVED = os.path.join(ROOT, "research", "enrich", "resolved.json")
PRIOR = os.path.join(ROOT, "research", "enrich", "prior_research.json")
OUT = os.path.join(ROOT, "research", "enrich", "site_contacts.json")

PHONE_RX = re.compile(r"(?<![\w/])(\+?\d{1,3}[\s.-]?)?(\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?![\w/])")
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ROLE_RX = re.compile(r"^(info|sales|office|contact|mail|support|service|customerservice|customer\.service|orders?|hello|enquiries|inquiries|inquiry|marketing|export|international)@", re.I)
CONTACT_LINK_RX = re.compile(r"contact|kontakt|contatt|contacto|get-in-touch|reach-us|about-us/contact", re.I)
BAD_EMAIL_RX = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|css|js)$|example\.|sentry|wixpress|@\d|noreply|no-reply|donotreply|privacy@|abuse@|webmaster@|dpo@|gdpr@|legal@|press@|media@|hr@|jobs@|careers@|recruit", re.I)


def get(url, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    if "charset" not in r.headers.get("content-type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"
    return r


def phones_from(html, text):
    out = []
    for m in re.finditer(r'href="tel:([^"]+)"', html, re.I):
        p = re.sub(r"[^\d+()\s.-]", "", m.group(1)).strip()
        if len(re.sub(r"\D", "", p)) >= 7:
            out.append(p)
    if not out:
        for m in PHONE_RX.finditer(text):
            s = m.group(0).strip()
            digits = re.sub(r"\D", "", s)
            if 8 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}[\s.-]?\d{4}", s):
                out.append(re.sub(r"\s+", " ", s))
    return list(dict.fromkeys(out))


def emails_from(html, text):
    found = re.findall(r'href="mailto:([^"?]+)', html, re.I) + EMAIL_RX.findall(text) + EMAIL_RX.findall(html)
    found = [e.strip().lower() for e in found]
    found = [e for e in found if not BAD_EMAIL_RX.search(e)]
    role = [e for e in found if ROLE_RX.match(e)]
    rest = [e for e in found if e not in role]
    # only role addresses are stored; personal-looking addresses are dropped
    return list(dict.fromkeys(role)), len(rest)


LAB_RX = re.compile(r"laborator|\blabs?\b|scientific|research|biotech|biolog|chemical|reagent|instrument|equipment|antibod|assay|pipet|microscop|diagnostic|medical|safety|glove|cleanroom|supplies|supply|industrial|manufactur|analytical|pharma|life science|consumable|sample|enzyme|protein|cell|genom|clinical|sterile|filtration|glassware|plastic|balance|weigh|incubator|centrifug|chromatograph|spectro|microbiolog|cryo|freezer|thermo", re.I)


def name_tokens(name):
    toks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3 and t not in ("inc", "ltd", "llc", "corp", "corporation", "company", "the", "and", "gmbh", "co", "usa", "international", "scientific", "products", "group", "laboratories", "laboratory", "sciences", "science", "bio", "lab", "labs")]
    return toks or [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]


def process(key, website, name=""):
    rec = {"website": website, "phone": None, "email": None, "contact_url": None, "address": None, "source": None, "note": None, "status": None,
           "name_match": None, "lab_relevance": None, "title": None}
    try:
        r = get(website)
    except Exception as e:
        rec["status"] = f"error: {type(e).__name__}"
        return rec
    rec["status"] = r.status_code
    if r.status_code >= 400:
        return rec
    html = r.text
    base = r.url
    text = html_to_text(html)
    mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    rec["title"] = re.sub(r"\s+", " ", mt.group(1)).strip()[:150] if mt else None
    low = (text[:20000] + " " + (rec["title"] or "") + " " + base).lower()
    toks = name_tokens(name) if name else []
    rec["name_match"] = bool(toks) and any(t in low for t in toks)
    rec["lab_relevance"] = len(set(m.group(0).lower() for m in LAB_RX.finditer(text[:30000])))
    phones = phones_from(html, text)
    emails, n_personal = emails_from(html, text)
    contact_url = None
    host = urlparse(base).netloc.lower().replace("www.", "")
    for l in extract_links(html, base):
        h = l["href"]
        if urlparse(h).netloc.lower().replace("www.", "") != host:
            continue
        if CONTACT_LINK_RX.search(h) or CONTACT_LINK_RX.search(l.get("text") or ""):
            contact_url = h
            break
    if contact_url:
        try:
            r2 = get(contact_url)
            if r2.status_code < 400:
                h2 = r2.text
                t2 = html_to_text(h2)
                phones = phones_from(h2, t2) + [p for p in phones if p not in phones_from(h2, t2)]
                e2, _ = emails_from(h2, t2)
                emails = e2 + [e for e in emails if e not in e2]
                rec["contact_url"] = r2.url
        except Exception:
            rec["contact_url"] = contact_url
    rec["phone"] = phones[0] if phones else None
    rec["phones"] = phones[:3]
    rec["email"] = emails[0] if emails else None
    rec["emails"] = emails[:3]
    rec["source"] = rec["contact_url"] or base
    rec["note"] = "from the company's own site (homepage / contact page); role addresses only" + (f"; {n_personal} personal address(es) omitted" if n_personal else "")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--unverified-only", action="store_true", help="only sites not yet checked for name_match/lab_relevance")
    args = ap.parse_args()
    master = json.load(open(MASTER, encoding="utf-8"))
    resolved = {x["key"]: x for x in json.load(open(RESOLVED, encoding="utf-8"))} if os.path.exists(RESOLVED) else {}
    prior = json.load(open(PRIOR, encoding="utf-8")) if os.path.exists(PRIOR) else {}
    cache = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = []
    for m in master:
        k = m["key"]
        if args.only_missing and k in cache:
            continue
        if args.unverified_only and k in cache and cache[k].get("name_match") is not None:
            continue
        web = (prior.get(k) or {}).get("website")
        res = resolved.get(k) or {}
        wd = res.get("wikidata") or {}
        cb = res.get("clearbit") or {}
        if not web:
            web = wd.get("website")
        if not web and cb.get("domain") and (cb.get("score") or 0) >= 0.8:
            web = "https://" + cb["domain"]
        if web:
            todo.append((k, web, m["name"]))
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} sites to check", flush=True)
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, k, w, nm): k for k, w, nm in todo}
        for fu in as_completed(futs):
            k = futs[fu]
            try:
                cache[k] = fu.result()
            except Exception as e:
                cache[k] = {"status": f"error: {type(e).__name__}: {e}"}
            done += 1
            if done % 25 == 0 or done == len(todo):
                ok = sum(1 for v in cache.values() if v.get("phone") or v.get("email"))
                print(f"[{done}/{len(todo)}] contacts found so far: {ok} ({time.time() - t0:.0f}s)", flush=True)
                json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done:", len(cache), "records; with phone:", sum(1 for v in cache.values() if v.get("phone")), "with email:", sum(1 for v in cache.values() if v.get("email")))


if __name__ == "__main__":
    main()
