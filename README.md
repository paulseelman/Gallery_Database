# Gallery Metadata Database

This project builds a local SQLite database from downloaded image metadata files in your `Images` tree (for example, `Library of Congress`, `Metropolitan`, and other sources).

## What It Stores

- Core item metadata (`title`, `date`, URL, rights, collection, call number, etc.)
- Parsed year range for date queries
- Faceted terms in a normalized table:
  - `subject`
  - `location`
  - `tag`
  - `contributor`
  - `format`
  - `language`
  - `note`
- Full-text search index (FTS5) for title/subjects/contributors/notes/places/tags
- The original source JSON per item in `raw_json`

## Requirements

- Python 3.9+
- SQLite with FTS5 (included in most Python builds)

## Build Database

```bash
cd /tank/media/Projects/Gallery_Database
python3 loc_metadata_db.py ingest \
  --images-root "/tank/media/Images" \
  --db loc_metadata.db
```

For very large archives, ingestion is resumable and idempotent because rows are upserted by `json_path`.

## Ingest Rules

- Ingest scans for JSON metadata recursively.
- If a folder contains `item.json`, that file is preferred.
- For Library of Congress item folders named like `http_www.loc.gov_item_...`, a non-`item.json` metadata file is also accepted when `item.json` is absent (for example, `8a12358.json`).
- One metadata JSON is selected per imageset folder to avoid duplicates.

## Collection Naming Rules

Collection names are derived from the parent folder of each imageset, not from the source folder itself.

Examples:

- `Library of Congress/abdul-hamid-ii/http_www.loc.gov_item_.../item.json` -> collection `abdul-hamid-ii`
- `Metropolitan/some-collection/some-imageset/item.json` -> collection `some-collection`

Fallback behavior:

- If metadata is directly under `source/imageset/...`, the source folder is used as collection.

Path key stability:

- `json_path` is normalized relative to the nearest `Images` directory segment, so ingesting from `/tank/media/Images` or `/tank/media/Images/<source>` resolves to the same key.

## Quick Stats

```bash
python3 loc_metadata_db.py stats --db loc_metadata.db
```

## Query Examples

By collection and year range:

```bash
python3 loc_metadata_db.py query \
  --db loc_metadata.db \
  --collection "abdul-hamid-ii" \
  --year-from 1880 \
  --year-to 1890 \
  --limit 20
```

By subject and location:

```bash
python3 loc_metadata_db.py query \
  --db loc_metadata.db \
  --subject "waterfront" \
  --location "istanbul" \
  --limit 20
```

By tag and contributor:

```bash
python3 loc_metadata_db.py query \
  --db loc_metadata.db \
  --tag "abdul hamid ii collection" \
  --contributor "abdullah" \
  --limit 20
```

Using full-text search (`fts5 MATCH` syntax):

```bash
python3 loc_metadata_db.py query \
  --db loc_metadata.db \
  --fts '"golden horn" OR barracks' \
  --limit 20
```

## Optional: Direct SQL

```bash
sqlite3 loc_metadata.db
```

Example SQL:

```sql
SELECT collection, COUNT(*)
FROM items
GROUP BY collection
ORDER BY COUNT(*) DESC;

SELECT i.title, i.date_raw, i.collection
FROM items i
JOIN item_terms t ON t.item_id = i.id
WHERE t.term_type = 'subject' AND t.term_value LIKE '%istanbul%'
ORDER BY i.year_start
LIMIT 100;
```

## Notes

- JSON shape varies slightly by collection, so ingestion is defensive and normalizes lists/dicts.
- Date strings like `[between 1880 and 1893]` are parsed into `year_start=1880`, `year_end=1893`.
- Metadata JSON naming varies by source; ingestion supports both `item.json` and source-specific item JSON filenames in known item-folder patterns.

## Web Filter Manager

This project includes a network-accessible filter management web app for controlling and tracking an active database filter.

### Install

```bash
cd /tank/media/Projects/Gallery_Database
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### Run on Your Network

```bash
.venv/bin/python webapp.py --db loc_metadata.db --host 0.0.0.0 --port 8080
```

Open from any device on your LAN:

```text
http://<your-server-ip>:8080
```

### API Endpoints

- `GET /api/filter`: read current active filter
- `PUT /api/filter`: save active filter (JSON body)
- `POST /api/results`: run ad-hoc query for provided filter
- `GET /api/results`: run query using saved active filter
- `GET /api/collections`: collection list/counts for the collection dropdown
- `GET /api/facets`: top facet values for dropdown/suggestions
- `GET /api/active-selection`: saved filter + current matching items

`/api/active-selection` is designed to make Raspberry Pi integration simple: your Pi can poll this endpoint, shuffle/display the returned items, and stay synchronized with the UI-managed active filter.

### Performance Notes

- Results query performance was optimized by using index-friendly ordering and avoiding expensive always-on dedupe windowing.
- Free-text `any_term` matching is routed through FTS, which is significantly faster than wildcard scans over normalized term tables.
- The collection dropdown is loaded via `GET /api/collections` so it does not wait on broader facet aggregation.
- Facets are cached in-memory and warmed at startup (default UI limit is 120), which reduces first-interaction delays after the server is running.
