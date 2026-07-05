# Library of Congress Metadata Database

This project builds a local SQLite database from downloaded Library of Congress item metadata (`item.json`) files.

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
  --images-root "/tank/media/Images/Library of Congress" \
  --db loc_metadata.db
```

For very large archives, ingestion is resumable and idempotent because rows are upserted by `json_path`.

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
- Only `item.json` files are ingested.
