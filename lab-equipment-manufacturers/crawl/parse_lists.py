#!/usr/bin/env python3
"""Parse the fetched catalog list pages into research/catalog_suppliers.json
(one record per distinct supplier/brand name, with the catalogs that list it)."""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "research", "sources")
OUT = os.path.join(ROOT, "research", "catalog_suppliers.json")

SUFFIX_RX = re.compile(r"[,\s]+(inc\.?|ltd\.?|llc|l\.l\.c\.|corp\.?|corporation|co\.?|company|gmbh|ag|sa|s\.a\.|sas|s\.a\.s\.|srl|s\.r\.l\.|bv|b\.v\.|plc|limited|kg|co\.\s*kg|gmbh\s*&\s*co\.?\s*kg|usa|america|international|intl\.?|group|holdings?)\.?$", re.I)


def norm(name):
    """Normalisation key for matching the same company across catalogs."""
    n = html.unescape(name).strip().lower()
    n = n.replace("&amp;", "&")
    n = re.sub(r"[®™©]", "", n)
    n = re.sub(r"\(.*?\)", " ", n)
    n = n.replace("&", " and ")
    prev = None
    while prev != n:
        prev = n
        n = SUFFIX_RX.sub("", n.strip())
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    n = re.sub(r"\s+", " ", n)
    return n


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def dutscher():
    out = []
    s = read(os.path.join(SRC, "lists", "dutscher_brands_en.html"))
    for m in re.finditer(r'<a href="(/search\?initialFilters=brand:[^"]*)" data-brand="([^"]*)"', s):
        out.append({"name": html.unescape(m.group(2)).strip(), "url": "https://www.dutscher.com" + html.unescape(m.group(1))})
    # Dutscher group / private-label brands
    s = read(os.path.join(SRC, "lists", "dutscher_private_label.html"))
    for m in re.finditer(r'images\.dutscher\.com/brand/([^"]+?)\.webp" alt="([^"]*)"', s):
        nm = html.unescape(m.group(1)).strip()
        out.append({"name": nm, "url": "https://www.dutscher.com/head-display/private-label?language=en", "own_brand": True})
    return out


def quartzy():
    t = read(os.path.join(SRC, "lists", "quartzy_suppliers.txt"))
    i = t.find("Become a Supplier\n\nA\n")
    j = t.find("support@quartzy.com")
    names = [x.strip() for x in t[i + len("Become a Supplier\n"):j].split("\n") if x.strip() and len(x.strip()) > 1]
    return [{"name": n, "url": "https://www.quartzy.com/suppliers"} for n in names]


def quartzy_new():
    t = read(os.path.join(SRC, "lists", "quartzy_new_suppliers.txt"))
    links = json.load(open(os.path.join(SRC, "lists", "quartzy_new_suppliers.links.json"), encoding="utf-8"))
    hrefs = [l["href"] for l in links if (l.get("text") or "").strip().lower() == "here"]
    out = []
    parts = re.split(r"\n\nCheck out (.+?) products on Quartzy\s*\n\s*here\s*\n\s*!\s*", t)
    # parts: [pre, name1, pre2, name2, ...]; the description of name_k is the tail of parts[2k]
    k = 0
    for idx in range(1, len(parts), 2):
        name = parts[idx].strip()
        pre = parts[idx - 1].strip()
        # description = text after the last blank line that starts with the name
        m = re.search(r"(?:^|\n\n)" + re.escape(name) + r"\s*\n\n(.+)$", pre, re.S)
        desc = m.group(1).strip() if m else pre.split("\n\n")[-1].strip()
        href = hrefs[k] if k < len(hrefs) else None
        k += 1
        out.append({"name": name, "url": "https://info.quartzy.com/new-suppliers", "description": re.sub(r"\s+", " ", desc)[:1500], "catalog_link": href})
    return out


THOMAS_OWN = {"labforce", "chemforce", "ce force", "thomas scientific", "thomas", "cleanforce", "safeforce"}


def thomassci():
    path = os.path.join(SRC, "thomas", "thomas_suppliers_parsed.json")
    if os.path.exists(path):
        items = json.load(open(path, encoding="utf-8"))
        for it in items:
            if norm(it["name"]) in THOMAS_OWN:
                it["own_brand"] = True
        return items
    return []


def main():
    catalogs = {"dutscher": dutscher(), "quartzy": quartzy(), "quartzy_new": quartzy_new(), "thomassci": thomassci()}
    recs = {}
    for cat, items in catalogs.items():
        for it in items:
            key = norm(it["name"])
            if not key:
                continue
            r = recs.setdefault(key, {"key": key, "name": it["name"], "names": [], "sources": {}})
            if it["name"] not in r["names"]:
                r["names"].append(it["name"])
            src = {k: v for k, v in it.items() if k != "name"}
            r["sources"].setdefault(cat, src)
    rows = sorted(recs.values(), key=lambda r: r["key"])
    for i, r in enumerate(rows, 1):
        r["id"] = i
        # prefer the longest display name among variants
        r["name"] = max(r["names"], key=len)
        r["n_catalogs"] = len(r["sources"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    counts = {c: len(v) for c, v in catalogs.items()}
    multi = sum(1 for r in rows if r["n_catalogs"] > 1)
    print(f"catalog items: {counts}; distinct suppliers: {len(rows)}; in >1 catalog: {multi}")


if __name__ == "__main__":
    main()
