# Gallery Manager

Gallery Manager is a local toolkit for building and managing a metadata-driven image gallery workflow.

The project now uses a tool-oriented structure that supports three major components:

- Database creator and ingestor (current)
- Combined filter control + slideshow web app (current)

## Project Structure

```text
Gallery_Manager/
  tools/
    database_ingestor/
      loc_metadata_db.py
    filter_control/
      webapp.py
      static/
      templates/
    client_viewer/
      viewer.py
      templates/
      static/
      README.md
  loc_metadata_db.py          # compatibility wrapper
  webapp.py                   # compatibility wrapper
  requirements.txt
  loc_metadata.db
  filter_state.db
```

## What The Database Stores

- Core item metadata (`title`, `date`, URL, rights, collection, call number, etc.)
- Parsed year range for date queries
- Faceted terms in a normalized table: `subject`, `location`, `tag`, `contributor`, `format`, `language`, `note`
- Full-text search index (FTS5) for title/subjects/contributors/notes/places/tags
- Original source JSON per item in `raw_json`

## Requirements

- Python 3.9+
- SQLite with FTS5 (included in most Python builds)

## Setup

```bash
cd /path/to/Gallery_Manager
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Database Creator And Ingestor

Use either the root wrapper or the tool path directly.

```bash
# Wrapper entrypoint
.venv/bin/python loc_metadata_db.py ingest \
  --images-root "/path/to/Images" \
  --db loc_metadata.db

# Tool path entrypoint
.venv/bin/python tools/database_ingestor/loc_metadata_db.py ingest \
  --images-root "/path/to/Images" \
  --db loc_metadata.db
```

For very large archives, ingestion is resumable and idempotent because rows are upserted by `json_path`.

### Ingest Rules

- Scans JSON metadata recursively.
- Prefers `item.json` per folder when present.
- For LoC item folders named like `http_www.loc.gov_item_...`, accepts non-`item.json` metadata (for example, `8a12358.json`) when needed.
- Selects one metadata JSON per imageset folder to avoid duplicates.

### Collection Naming Rules

- Collection names are derived from the parent folder of each imageset.
- `Library of Congress/abdul-hamid-ii/http_www.loc.gov_item_.../item.json` -> `abdul-hamid-ii`
- `Metropolitan/some-collection/some-imageset/item.json` -> `some-collection`
- If metadata is directly under `source/imageset/...`, source folder is used as fallback.

`json_path` is normalized relative to the nearest `Images` segment, so ingesting from `/path/to/Images` or `/path/to/Images/<source>` resolves to the same key.

### Query Examples

```bash
.venv/bin/python loc_metadata_db.py stats --db loc_metadata.db

.venv/bin/python loc_metadata_db.py query \
  --db loc_metadata.db \
  --collection "abdul-hamid-ii" \
  --year-from 1880 \
  --year-to 1890 \
  --limit 20

.venv/bin/python loc_metadata_db.py query \
  --db loc_metadata.db \
  --subject "waterfront" \
  --location "istanbul" \
  --limit 20

.venv/bin/python loc_metadata_db.py query \
  --db loc_metadata.db \
  --fts '"golden horn" OR barracks' \
  --limit 20
```

## Filter Control Web App

Run the app (wrapper or tool path):

```bash
.venv/bin/python webapp.py --db loc_metadata.db --host 0.0.0.0 --port 8080
```

Open from any device on your LAN:

```text
http://<your-server-ip>:8080
```

Open the slideshow viewer from the same server:

```text
http://<your-server-ip>:8080/viewer
```

### API Endpoints

- `GET /api/filter`
- `PUT /api/filter`
- `POST /api/results`
- `GET /api/results`
- `GET /api/collections`
- `GET /api/facets`
- `GET /api/active-selection`
- `GET /api/selection`

### Filter Notes

- `Exclude portraits` removes items whose title or metadata terms contain `portrait`.
- `/api/active-selection` is suitable for polling clients (for example a Raspberry Pi display loop).

## Unified Viewer Notes

The viewer now runs inside the same Flask process as filter control.

- No second service is required.
- `/viewer` polls local selection APIs and cycles image-ready records.
- Use `--poll-seconds` and `--slide-seconds` on `webapp.py` to tune slideshow timing.
