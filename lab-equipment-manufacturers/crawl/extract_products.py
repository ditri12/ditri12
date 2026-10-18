#!/usr/bin/env python3
"""Extract representative products, product counts, categories and descriptions from fetched
Thomas Scientific supplier pages (ids th_*) and Dutscher brand search pages (ids du_*).

Usage: python extract_products.py <pages_dir> [<pages_dir> ...]
Writes/merges research/enrich/catalog_products.json keyed by master key:
  {products:[{name,url,catalog}], product_count:{thomassci:N,dutscher:N}, categories:[...], applications:[...], description, category}
"""
import gzip
import html as htmlmod
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "enrich", "catalog_products.json")
MASTER = os.path.join(ROOT, "research", "catalog_suppliers.json")

DUTSCHER_CAT_HE = {
    "Consumables and small equipment": "מתכלים וציוד קטן", "Equipment": "ציוד", "Measuring instrument": "מכשירי מדידה",
    "Laboratory furniture": "ריהוט מעבדה", "Health and safety": "בטיחות", "Pipetting": "פיפטות", "Bioreactive": "ריאגנטים ביולוגיים", "Chemistry": "כימיה",
}
THOMAS_CAT_HE = {"laboratory-supplies": "מתכלים וכלי מעבדה", "chemicals": "כימיקלים", "equipment": "ציוד", "instruments": "מכשור", "safety-and-apparel": "בטיחות וביגוד", "furniture": "ריהוט"}


def read_html(d, pid):
    p = os.path.join(d, pid + ".html")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    p = os.path.join(d, pid + ".html.gz")
    if os.path.exists(p):
        return gzip.open(p, "rt", encoding="utf-8").read()
    return None


def read_text(d, pid):
    p = os.path.join(d, pid + ".txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def clean(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(s or "")).strip()


def thomas(h, t):
    out = {"products": [], "product_count": {}, "categories": [], "applications": [], "description": None}
    m = re.search(r"Products \((\d[\d,]*)\)", h)
    if m:
        out["product_count"]["thomassci"] = int(m.group(1).replace(",", ""))
    seen = set()
    for m in re.finditer(r'<h4 class="product-summary__name"><a href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
        url = m.group(1)
        if url.startswith("//"):
            url = "https:" + url
        name = clean(re.sub(r"<[^>]+>", " ", m.group(2)))
        name = re.sub(r"^(Select Supplier Best Seller|Top Deals|Best Seller|New)\s*", "", name).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out["products"].append({"name": name, "url": url, "catalog": "thomassci"})
        if len(out["products"]) >= 6:
            break
    md = re.search(r'<meta name="description" content="([^"]*)"', h, re.I)
    if md:
        d = clean(md.group(1))
        if d and not re.match(r"^(Products in|Shop|Browse)", d) and len(d) > 40:
            out["description"] = d[:600]
    # supplier intro text (if any) between the supplier heading and the facets
    mi = re.search(r'class="(?:category-description|supplier-description|brand-description)[^"]*"[^>]*>(.*?)</div>', h, re.S | re.I)
    if mi:
        d = clean(re.sub(r"<[^>]+>", " ", mi.group(1)))
        if len(d) > 40:
            out["description"] = d[:800]
    # category guess from the product URLs' category breadcrumbs is not available; use facet names as hints
    return out


def dutscher(h, t):
    out = {"products": [], "product_count": {}, "categories": [], "applications": [], "description": None}
    m = re.search(r"([\d][\d,\.\s]*)\s*items", t)
    if m:
        out["product_count"]["dutscher"] = int(re.sub(r"[^\d]", "", m.group(1)))
    def facet(header):
        """Values of one facet block: 'Header\nName\n(count)\nName\n(count)...' ending at the next header line."""
        j = t.find("\nBrand\n")
        i = t.rfind("\n" + header + "\n", 0, j) if header == "Categories" and j > 0 else t.find("\n" + header + "\n")
        if i < 0:
            return []
        lines = t[i + len(header) + 2:].split("\n")
        vals = []
        k = 0
        while k < len(lines) - 1:
            name, cnt = lines[k].strip(), lines[k + 1].strip()
            if name and re.fullmatch(r"\(\d+\)", cnt) and not re.fullmatch(r"\(\d+\)", name):
                vals.append({"name": name, "count": int(cnt.strip("()"))})
                k += 2
            else:
                break
        vals.sort(key=lambda c: -c["count"])
        return vals
    cats = facet("Categories")
    out["categories"] = [{"name": c["name"], "name_he": DUTSCHER_CAT_HE.get(c["name"], c["name"]), "count": c["count"]} for c in cats[:5]]
    out["applications"] = [a["name"] for a in facet("Application")[:5]]
    seen = set()
    for m in re.finditer(r'<a[^>]+href="(/article/[^"]+)"[^>]*>(.*?)</a>', h, re.S):
        name = clean(re.sub(r"<[^>]+>", " ", m.group(2)))
        name = re.sub(r"^[0-9A-Z]{4,8}\s*·\s*", "", name)
        if len(name) < 6 or name.lower() in seen:
            continue
        seen.add(name.lower())
        out["products"].append({"name": name[:140], "url": "https://www.dutscher.com" + m.group(1), "catalog": "dutscher"})
        if len(out["products"]) >= 6:
            break
    return out


def main():
    dirs = sys.argv[1:]
    master = json.load(open(MASTER, encoding="utf-8"))
    bykey = {r["key"]: r for r in master}
    idkey = {}
    for r in master:
        idkey["th_" + r["key"].replace(" ", "_")[:60]] = r["key"]
        idkey["du_" + r["key"].replace(" ", "_")[:60]] = r["key"]
    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    n = 0
    for d in dirs:
        idx_path = os.path.join(d, "index.json")
        if not os.path.exists(idx_path):
            continue
        for e in json.load(open(idx_path, encoding="utf-8")):
            pid = e["id"]
            key = idkey.get(pid)
            if not key or e.get("error") or not e.get("status") or e["status"] >= 400:
                continue
            h = read_html(d, pid)
            if not h:
                continue
            t = read_text(d, pid)
            res = thomas(h, t) if pid.startswith("th_") else dutscher(h, t)
            cur = data.setdefault(key, {"products": [], "product_count": {}, "categories": [], "applications": [], "description": None})
            # merge: keep products from both catalogs (dedupe by name), counts per catalog
            names = {p["name"].lower() for p in cur["products"]}
            for p in res["products"]:
                if p["name"].lower() not in names:
                    cur["products"].append(p)
                    names.add(p["name"].lower())
            cur["product_count"].update(res["product_count"])
            if res["categories"]:
                cur["categories"] = res["categories"]
            if res["applications"]:
                cur["applications"] = res["applications"]
            if res["description"] and not cur.get("description"):
                cur["description"] = res["description"]
            cur["source_pages"] = list(dict.fromkeys((cur.get("source_pages") or []) + [e.get("final_url") or e.get("url")]))
            n += 1
    for key, cur in data.items():
        cur["products"] = cur["products"][:6]
        if cur.get("categories"):
            cur["category"] = cur["categories"][0]["name_he"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"pages processed: {n}; suppliers with catalog data: {len(data)}; with products: {sum(1 for v in data.values() if v['products'])}")


if __name__ == "__main__":
    main()
