#!/usr/bin/env python3
"""Import the verified research from the earlier top-100 manufacturers database (git history,
commit 89381ac) for suppliers that also appear in the new catalog master list.
Input: a manufacturers.json export of that database (path argument).
Output: research/enrich/prior_research.json keyed by the new master-list key."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_lists import norm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "research", "catalog_suppliers.json")
OUT = os.path.join(ROOT, "research", "enrich", "prior_research.json")

# manual aliases: old display name -> new master key
ALIASES = {
    "thermo fisher scientific": ["thermo scientific", "thermo fisher scientific", "fisher scientific", "fisherbrand", "thermo scientific lab supplies"],
    "merck kgaa / milliporesigma": ["merck", "milliporesigma", "millipore", "sigma aldrich", "merck millipore", "supelco"],
    "danaher": ["danaher"],
    "agilent technologies": ["agilent", "agilent technologies"],
    "bio rad laboratories": ["bio rad", "bio rad laboratories"],
    "becton dickinson": ["bd", "bd medical", "bd biosciences", "bd diagnostics", "becton dickinson"],
    "roche diagnostics": ["roche", "roche diagnostics"],
    "shimadzu": ["shimadzu", "shimadzu scientific instruments"],
    "waters": ["waters", "waters corporation"],
    "mettler toledo": ["mettler toledo", "mettler toledo rainin", "rainin"],
    "sartorius": ["sartorius", "sartorius stedim biotech"],
    "eppendorf": ["eppendorf", "eppendorf north america"],
    "perkinelmer / revvity": ["perkinelmer", "revvity"],
    "beckman coulter": ["beckman coulter", "beckman coulter life sciences"],
    "corning": ["corning", "corning life sciences", "corning gosselin", "pyrex"],
    "cytiva": ["cytiva", "whatman", "ge healthcare life sciences"],
    "avantor / vwr": ["avantor", "vwr", "vwr international", "j t baker"],
    "qiagen": ["qiagen"],
    "zeiss": ["zeiss", "carl zeiss", "carl zeiss microscopy"],
    "leica microsystems": ["leica", "leica microsystems", "leica biosystems"],
    "olympus / evident": ["olympus", "evident", "evident scientific"],
    "nikon": ["nikon", "nikon instruments"],
    "bruker": ["bruker"],
    "tecan": ["tecan"],
    "hamilton": ["hamilton", "hamilton company"],
    "gilson": ["gilson", "gilson co"],
    "ika": ["ika", "ika works"],
    "memmert": ["memmert"],
    "binder": ["binder"],
    "julabo": ["julabo"],
    "heidolph": ["heidolph", "heidolph instruments", "heidolph north america"],
    "ohaus": ["ohaus"],
    "a&d company": ["a and d", "a and d instruments", "a and d weighing", "a and d engineering"],
    "brand gmbh": ["brand", "brandtech", "brandtech scientific"],
    "greiner bio one": ["greiner bio one"],
    "sarstedt": ["sarstedt"],
    "starlab": ["starlab"],
    "integra biosciences": ["integra", "integra biosciences"],
    "esco": ["esco", "esco lifesciences", "esco technologies"],
    "labconco": ["labconco"],
    "nuaire": ["nuaire"],
    "panasonic / phc": ["phcbi", "phc", "phc corporation of north america", "panasonic"],
    "liebherr": ["liebherr"],
    "froilabo": ["froilabo"],
    "arctiko": ["arctiko"],
    "velp scientifica": ["velp", "velp scientifica"],
    "anton paar": ["anton paar"],
    "horiba": ["horiba", "horiba scientific"],
    "jeol": ["jeol"],
    "hitachi high tech": ["hitachi high tech", "hitachi", "hitachi high tech america"],
    "thermo fisher (fisherbrand)": ["fisherbrand"],
    "biotek / agilent": ["biotek"],
    "molecular devices": ["molecular devices"],
    "promega": ["promega"],
    "new england biolabs": ["new england biolabs", "neb"],
    "abcam": ["abcam"],
    "cell signaling technology": ["cell signaling technology"],
    "bio techne / r&d systems": ["r and d systems", "bio techne", "novus biologicals", "tocris"],
    "lonza": ["lonza"],
    "stemcell technologies": ["stemcell technologies"],
    "miltenyi biotec": ["miltenyi biotec"],
    "illumina": ["illumina"],
    "pacbio": ["pacific biosciences", "pacbio"],
    "oxford nanopore": ["oxford nanopore technologies"],
    "10x genomics": ["10x genomics"],
    "azenta": ["azenta", "azenta life sciences", "brooks"],
    "ssi / sorenson": ["sorenson bioscience", "ssi", "ssibio"],
    "axygen": ["axygen"],
    "celltreat": ["celltreat", "celltreat scientific products"],
    "nest": ["nest scientific", "nest biotechnology", "nest"],
    "biologix": ["biologix"],
    "wheaton / dwk": ["dwk life sciences", "wheaton", "kimble", "duran"],
    "schott": ["schott", "duran"],
    "ace glass": ["ace glass"],
    "chemglass": ["chemglass", "chemglass life sciences"],
    "kimble": ["kimble", "kimble chase"],
    "hirschmann": ["hirschmann", "hirschmann laborgerate"],
    "burkle": ["burkle"],
    "vitlab": ["vitlab"],
    "kartell": ["kartell"],
    "bel art / sp": ["bel art", "sp bel art", "sp scientific", "sp industries", "sp scienceware"],
    "heathrow scientific": ["heathrow scientific"],
    "dynalon": ["dynalon"],
    "nalgene": ["nalgene", "thermo scientific nalgene"],
    "vacuubrand": ["vacuubrand"],
    "welch": ["welch", "welch vacuum"],
    "buchi": ["buchi", "buchi corporation"],
    "lauda": ["lauda", "lauda brinkmann"],
    "huber": ["huber", "peter huber kaltemaschinenbau"],
    "polyscience": ["polyscience"],
    "grant instruments": ["grant instruments"],
    "benchmark scientific": ["benchmark", "benchmark scientific"],
    "scilogex": ["scilogex"],
    "dlab": ["dlab", "dlab scientific"],
    "ohaus (vwr)": ["ohaus"],
    "radwag": ["radwag"],
    "kern & sohn": ["kern", "kern and sohn"],
    "adam equipment": ["adam equipment"],
    "hanna instruments": ["hanna instruments"],
    "mettler (process)": ["mettler toledo"],
    "xylem / ysi / wtw": ["ysi", "wtw", "xylem", "oi analytical", "bellingham and stanley"],
    "thermo orion": ["thermo scientific orion"],
    "atago": ["atago"],
    "anton paar (density)": ["anton paar"],
    "brookfield / ametek": ["brookfield", "ametek brookfield"],
    "malvern panalytical": ["malvern panalytical"],
    "metrohm": ["metrohm"],
    "spectro analytical": ["spectro", "spectro analytical instruments"],
    "rigaku": ["rigaku"],
    "oxford instruments": ["oxford instruments"],
    "tescan": ["tescan"],
    "netzsch": ["netzsch"],
    "ta instruments": ["ta instruments"],
    "mindray": ["mindray"],
    "siemens healthineers": ["siemens healthineers"],
    "abbott": ["abbott", "abbott diagnostics"],
    "sysmex": ["sysmex"],
    "biomerieux": ["biomerieux"],
    "repligen": ["repligen"],
    "kewaunee": ["kewaunee", "kewaunee scientific"],
    "waldner": ["waldner"],
    "ats scientific products": ["ats scientific products", "sp scientific", "genevac", "hotpack", "virtis"],
    "tuttnauer": ["tuttnauer"],
    "yamato": ["yamato", "yamato scientific", "yamato scientific america"],
    "infors ht": ["infors", "infors ht", "infors usa"],
    "nabertherm": ["nabertherm"],
    "carbolite gero": ["carbolite gero", "carbolite", "verder scientific"],
    "retsch": ["retsch"],
    "fritsch": ["fritsch"],
    "elga labwater": ["elga", "elga labwater", "veolia"],
    "millipore water": ["milliporesigma"],
    "lab armor": ["lab armor"],
    "eppendorf (himac)": ["eppendorf himac", "himac"],
    "hettich": ["hettich", "andreas hettich", "hettich instruments"],
    "sigma laborzentrifugen": ["sigma laborzentrifugen"],
    "thermo (sorvall)": ["sorvall"],
    "whatman": ["whatman"],
    "pall": ["pall", "pall corporation", "pall laboratory"],
    "sartorius (filtration)": ["sartorius"],
    "millipore (filtration)": ["milliporesigma"],
    "advantec": ["advantec", "advantec mfs"],
    "ahlstrom": ["ahlstrom", "ahlstrom munksjo"],
    "macherey nagel": ["macherey nagel"],
    "phenomenex": ["phenomenex"],
    "restek": ["restek"],
    "supelco": ["supelco"],
    "hamilton (syringes)": ["hamilton"],
    "sge / trajan": ["trajan", "sge analytical science", "trajan scientific and medical"],
    "ansell": ["ansell"],
    "kimberly clark / kimtech": ["kimberly clark", "kimtech", "kimberly clark professional"],
    "honeywell safety": ["honeywell", "honeywell safety", "uvex by honeywell"],
    "3m": ["3m", "3m safety", "3m health care"],
    "justrite": ["justrite"],
    "eagle manufacturing": ["eagle manufacturing"],
    "asecos": ["asecos"],
    "dupont": ["dupont", "dupont personal protection", "tyvek"],
    "brady": ["brady"],
    "sharp": ["sharp"],
    "labnet": ["labnet", "labnet international"],
    "corning (axygen)": ["axygen"],
    "usa scientific": ["usa scientific"],
    "sorenson": ["sorenson bioscience"],
}


def main():
    src = sys.argv[1]
    old = json.load(open(src, encoding="utf-8"))
    rows = old.get("manufacturers") or old
    master = json.load(open(MASTER, encoding="utf-8"))
    keys = {r["key"]: r for r in master}
    # alias lookup: any of the alias keys -> old row
    out = {}
    matched_old = 0
    for r in rows:
        name = r.get("name") or ""
        cands = {norm(name)}
        for alt in (r.get("aliases") or []):
            cands.add(norm(alt))
        for oldname, als in ALIASES.items():
            if norm(oldname) == norm(name) or norm(name) in [norm(a) for a in als]:
                cands.update(norm(a) for a in als)
        hit = [k for k in cands if k in keys]
        if not hit:
            continue
        matched_old += 1
        rec = {
            "old_id": r.get("id"), "old_name": name, "country": r.get("country"), "category": r.get("category"),
            "website": r.get("website"), "hq": r.get("hq"), "parent": r.get("parent"),
            "employees": r.get("employees"), "employees_year": r.get("employees_year"), "employees_scope": r.get("employees_scope"), "employees_note": r.get("employees_note"),
            "revenue": r.get("revenue"), "revenue_currency": r.get("revenue_currency"), "revenue_year": r.get("revenue_year"), "revenue_scope": r.get("revenue_scope"), "revenue_note": r.get("revenue_note"),
            "size_basis": r.get("size_basis"), "products": r.get("products"),
            "israel_presence": r.get("israel_presence"), "israel_entities": r.get("israel_entities"), "israel_note": r.get("israel_note"),
            "israel_check": r.get("israel_check"), "israel_evidence_year": r.get("israel_evidence_year"), "israel_current": r.get("israel_current"),
            "contact": r.get("contact"), "sources": r.get("sources"), "verified_at": old.get("generated"),
        }
        for k in hit:
            out[k] = rec
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"old rows matched: {matched_old}/{len(rows)}; master keys covered: {len(out)}")
    print(sorted(out.keys()))


if __name__ == "__main__":
    main()
