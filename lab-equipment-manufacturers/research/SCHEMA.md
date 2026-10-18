# Schema – data/suppliers.json

```
{
  title, title_he, generated, count, catalogs{...}, israel_presence_values{...}, israel_check_values{...},
  suppliers: [ supplier ],
  israeli_entities_index: [ {key, name, name_he, type, website, phone, email, address, contact_url, count, suppliers[{id,name,status,evidence_year,match_basis}]} ]
}
supplier = {
  id, key (normalised name), name, names[], aka,
  catalogs: {dutscher|thomassci|quartzy|quartzy_new: {url, own_brand, description, catalog_link}}, n_catalogs, own_brand_of,
  website, website_source (prior|wikidata|clearbit|manual), website_candidate, website_candidate_score,
  country, country_he, hq, parent, ownership, inception, industry, description, wikidata, wikidata_score,
  employees: {value, year, scope (company|parent|estimate), source (prior|wikidata|manual), note} | null,
  revenue: {usd_m, original, year, scope, source, note} | null,
  size_basis (reported|mixed|estimate|unknown),
  products: [{name, desc, source (prior|catalog|manual), url, catalog}],
  israel_presence, israel_presence_he, israel_check, israel_check_he, israel_evidence_year, israel_current, israel_note,
  israel_entities: [{name, name_he, type (subsidiary|distributor|service|office), scope, website, phone, email, address, contact_url,
                     source, evidence_year, status (current|older_evidence|no_longer|new), match_basis, match_confidence, match_text}],
  contact: {phone, email, address, contact_url, source, note},
  sources[], prior_verified, prior_verified_at
}
```

CSV / SQL use the flattened columns listed in `build.py` (`CSV_COLUMNS`, `SCHEMA`).
