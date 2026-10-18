#!/usr/bin/env python3
"""Match the supplier master list against the crawled Israeli distributor sites.

Reads  research/sources/israel/{index.json,*.txt,*.links.json,*.html.gz}
       research/catalog_suppliers.json
       research/israel/distributor_contacts_seed.json (contacts known from earlier research)
Writes research/enrich/israel_matches.json   {master_key: [{distributor, site, page_url, evidence, confidence, evidence_year}]}
       research/israel/distributors.json      {distributor_id: {name, name_he, website, phone, email, address, contact_url, pages}}
"""
import gzip
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "crawl"))
from parse_lists import norm  # noqa: E402

SRC = os.path.join(ROOT, "research", "sources", "israel")
MASTER = os.path.join(ROOT, "research", "catalog_suppliers.json")
SEED = os.path.join(ROOT, "research", "israel", "distributor_contacts_seed.json")
OUT_MATCHES = os.path.join(ROOT, "research", "enrich", "israel_matches.json")
OUT_REG = os.path.join(ROOT, "research", "israel", "distributors.json")

# names too generic to match as a substring; they need an exact line / link-text match
GENERIC = set("""brand brady sharp eagle crystal apex alpha omega delta spectrum precision universal national general global standard premier
cardinal grant pro nest star sun moon ace action advance advanced american atlas best blue bright central classic clear club comfort core
direct dynamic elite express first focus future gold green ideal impact key liberty life light link master max micro mini modern new north
one open optimum pacific peak perfect plus point power prime pure quality rapid ready safe select simple smart solid source south summit
superior supreme total true ultra united value victory vision west world zero tools lab labs medical science scientific products supply
supplies systems technologies technology instruments industries international solutions company group corporation health safety home
office school paper plastic glass metal water air fire ice heat cold bio chem gen cell dna rna""".split())


def tokens(s):
    return [t for t in norm(s).split() if t]


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def phone_email(text):
    phones = re.findall(r"(?:\+972[-\s]?|0)(?:[23489]|5\d|7\d)[-\s]?\d{3}[-\s]?\d{4}", text)
    phones = [re.sub(r"\s+", "-", p.strip()) for p in phones]
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    emails = [e for e in emails if not re.search(r"\.(png|jpg|gif|svg|webp)$", e, re.I) and "example" not in e and "sentry" not in e and "wixpress" not in e]
    pref = [e for e in emails if re.match(r"(info|sales|office|contact|mail|support|service|orders?)@", e, re.I)]
    return list(dict.fromkeys(phones))[:3], list(dict.fromkeys(pref + emails))[:3]


def main():
    master = json.load(open(MASTER, encoding="utf-8"))
    index = {e["id"]: e for e in json.load(open(os.path.join(SRC, "index.json"), encoding="utf-8"))}
    seed = {s["key"]: s for s in json.load(open(SEED, encoding="utf-8"))} if os.path.exists(SEED) else {}
    names_he_path = os.path.join(ROOT, "research", "israel", "distributor_names_he.json")
    names_he = json.load(open(names_he_path, encoding="utf-8")) if os.path.exists(names_he_path) else {}
    # group pages by distributor (root id = part before '__')
    pages = defaultdict(list)
    for pid, e in index.items():
        if e.get("error") or not e.get("status") or e["status"] >= 400:
            continue
        root = pid.split("__")[0]
        pages[root].append(e)
    # build per-distributor corpus: lines from txt + link texts/alt/title
    corpora = {}
    registry = {}
    for root, plist in pages.items():
        lines = []
        for e in plist:
            txt = os.path.join(SRC, e["id"] + ".txt")
            if os.path.exists(txt):
                for ln in read_text(txt).splitlines():
                    ln = ln.strip()
                    if ln and len(ln) <= 120:
                        lines.append((ln, e["final_url"] or e["url"]))
            lj = os.path.join(SRC, e["id"] + ".links.json")
            if os.path.exists(lj):
                for l in json.load(open(lj, encoding="utf-8")):
                    for t in (l.get("text"), l.get("alt"), l.get("title")):
                        if t and len(t) <= 120:
                            lines.append((t.strip(), e["final_url"] or e["url"]))
        corpora[root] = lines
        home = index.get(root, {})
        site = re.sub(r"^https?://(www\.)?", "", home.get("url", "")).strip("/")
        txt_all = "\n".join(l for l, _ in lines)
        phones, emails = phone_email(txt_all)
        key = site.split(".")[0]
        sd = seed.get(key) or next((s for k, s in seed.items() if site and (site.split(".")[0] in (s.get("website") or ""))), {})
        registry[root] = {"id": root, "site": site, "name": sd.get("name") or (home.get("title") or site).split("|")[0].split(" - ")[0].strip()[:80],
                          "name_he": sd.get("name_he") or names_he.get(site), "website": sd.get("website") or home.get("url"),
                          "phone": sd.get("phone") or (phones[0] if phones else None), "email": sd.get("email") or (emails[0] if emails else None),
                          "address": sd.get("address"), "contact_url": sd.get("contact_url"), "note": sd.get("note"),
                          "phones_found": phones, "emails_found": emails,
                          "pages": [e["final_url"] or e["url"] for e in plist], "n_pages": len(plist), "n_lines": len(lines)}
    # match
    matches = defaultdict(list)
    for m in master:
        variants = {norm(n) for n in m.get("names", [m["name"]])} | {m["key"]}
        variants = {v for v in variants if v}
        for root, lines in corpora.items():
            best = None
            for ln, url in lines:
                nl = norm(ln)
                if not nl:
                    continue
                for v in variants:
                    toks = v.split()
                    if nl == v:
                        conf = "exact"
                    elif len(v) >= 5 and (len(toks) >= 2 or v not in GENERIC) and re.search(r"(?:^|\s)" + re.escape(v) + r"(?:\s|$)", nl) and len(nl) <= 60:
                        conf = "contained"
                    else:
                        continue
                    if best is None or (conf == "exact" and best[0] != "exact"):
                        best = (conf, ln, url)
                    if conf == "exact":
                        break
                if best and best[0] == "exact":
                    break
            if best:
                matches[m["key"]].append({"distributor": root, "site": registry[root]["site"], "page_url": best[2], "evidence": best[1][:120],
                                          "confidence": best[0], "evidence_year": 2026})
    os.makedirs(os.path.dirname(OUT_MATCHES), exist_ok=True)
    json.dump(dict(matches), open(OUT_MATCHES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(registry, open(OUT_REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_exact = sum(1 for v in matches.values() for h in v if h["confidence"] == "exact")
    n_cont = sum(1 for v in matches.values() for h in v if h["confidence"] == "contained")
    print(f"distributors crawled: {len(pages)}; suppliers matched: {len(matches)} (exact hits {n_exact}, contained hits {n_cont})")
    for root, reg in sorted(registry.items(), key=lambda kv: -kv[1]["n_lines"]):
        hits = sum(1 for v in matches.values() for h in v if h["distributor"] == root)
        print(f"  {root:28s} pages={reg['n_pages']:2d} lines={reg['n_lines']:5d} hits={hits:3d} phone={reg['phone']} email={reg['email']}")


if __name__ == "__main__":
    main()
