# Research record schema

Each `batch_NN.json` is a JSON array of manufacturer records (10 per batch, ids 1–100). `build.py` merges them.

| key | type | meaning |
|---|---|---|
| `id` | int | 1–100, stable row number |
| `name` | str | official company / business name |
| `aka` | str | brands, former names ("" if none) |
| `hq_city`, `hq_country` | str | headquarters |
| `parent` | str | parent / owner if a subsidiary, else "" |
| `ownership` | str | `Public (EXCH: TICKER)`, `Private`, `Private (family-owned)`, `Subsidiary of X (...)`, `Private equity (owner)` |
| `founded` | int or null | founding year |
| `website` | str | official site |
| `category` | str | one of the fixed category labels (see `build.py` / viewer map) |
| `employees`, `employees_year` | int or null | latest headcount and its year |
| `employees_note` | str | scope caveats (e.g. parent-level figure) |
| `revenue_original` | str | latest fiscal-year revenue in original currency, e.g. `EUR 3.38 billion` |
| `revenue_usd_m` | number or null | same figure in USD millions (approx. 2025 FX: EUR 1.10, GBP 1.30, CHF 1.17, JPY 0.0067, CNY 0.139, SEK 0.098, SGD 0.76) |
| `revenue_year` | str | e.g. `FY2025`, `FY ending Mar-2026` |
| `revenue_scope` | str | `company` / `segment` / `parent` / `estimate` |
| `revenue_note` | str | source / scope caveats |
| `size_basis` | str | `reported` / `estimate` / `mixed` |
| `top_products` | list of 3 `{name, desc}` | flagship products / product lines |
| `israel_presence` | str | `subsidiary` (manufacturer's own Israeli entity), `distributor` (independent Israeli distributor(s)), `parent_subsidiary` (sold by the parent group's Israeli subsidiary), `none_found` (searched, no public evidence), `unclear` |
| `israel_entities` | list of `{name, name_he, type, scope, website, source}` | every Israeli entity found; `type` is `subsidiary` / `distributor` / `service` |
| `israel_note` | str | how the Israeli channel was established, caveats |
| `sources` | list of str | URLs relied on |
| `confidence` | str | `high` / `medium` / `low` |
| `confidence_note` | str | why |
