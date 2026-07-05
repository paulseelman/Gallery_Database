#!/usr/bin/env python3
"""
Build and query a SQLite metadata database for Library of Congress image sets.

Usage examples:
  python3 loc_metadata_db.py ingest --images-root "/tank/media/Images/Library of Congress" --db loc_metadata.db
  python3 loc_metadata_db.py stats --db loc_metadata.db
  python3 loc_metadata_db.py query --db loc_metadata.db --collection "abdul-hamid-ii" --year-from 1885 --year-to 1890 --subject istanbul --limit 20
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            item_id TEXT,
            url TEXT,
            title TEXT,
            date_raw TEXT,
            year_start INTEGER,
            year_end INTEGER,
            collection TEXT,
            imageset_folder TEXT,
            json_path TEXT UNIQUE,
            has_jpg INTEGER DEFAULT 0,
            has_tif INTEGER DEFAULT 0,
            unrestricted INTEGER,
            rights_advisory TEXT,
            language_text TEXT,
            repository TEXT,
            call_number TEXT,
            shelf_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS item_terms (
            item_id INTEGER NOT NULL,
            term_type TEXT NOT NULL,
            term_value TEXT NOT NULL,
            UNIQUE(item_id, term_type, term_value),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_items_collection ON items(collection);
        CREATE INDEX IF NOT EXISTS idx_items_year_start ON items(year_start);
        CREATE INDEX IF NOT EXISTS idx_items_year_end ON items(year_end);
        CREATE INDEX IF NOT EXISTS idx_terms_type_value ON item_terms(term_type, term_value);

        CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
            title,
            subjects,
            contributors,
            notes,
            places,
            tags,
            content=''
        );
        """
    )


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def flatten_list(values: Any) -> List[str]:
    out: List[str] = []

    def _walk(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.append(s)
            return
        if isinstance(v, dict):
            for key in ("title", "name", "label", "value"):
                if key in v and isinstance(v[key], str) and v[key].strip():
                    out.append(v[key].strip())
                    return
            for nested in v.values():
                _walk(nested)
            return
        if isinstance(v, list):
            for nested in v:
                _walk(nested)
            return
        s = str(v).strip()
        if s:
            out.append(s)

    _walk(values)
    # Preserve order while de-duping.
    return list(dict.fromkeys(out))


def parse_year_range(date_raw: str) -> Tuple[Optional[int], Optional[int]]:
    if not date_raw:
        return None, None

    years = [int(x) for x in re.findall(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)", date_raw)]
    if not years:
        return None, None
    if len(years) == 1:
        return years[0], years[0]
    return min(years), max(years)


def has_media_files(imageset_dir: Path) -> Tuple[int, int]:
    has_jpg = 0
    has_tif = 0
    try:
        for p in imageset_dir.iterdir():
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                has_jpg = 1
            elif suffix in (".tif", ".tiff"):
                has_tif = 1
            if has_jpg and has_tif:
                break
    except OSError:
        pass
    return has_jpg, has_tif


def collect_terms(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    item = payload.get("item") or {}

    terms = {
        "subject": flatten_list(payload.get("subject")) + flatten_list(item.get("subjects")) + flatten_list(item.get("subject_headings")),
        "location": flatten_list(payload.get("location")) + flatten_list(item.get("location")) + flatten_list(item.get("place")),
        "tag": flatten_list(payload.get("partof")) + flatten_list(payload.get("group")) + flatten_list(payload.get("site")),
        "contributor": flatten_list(payload.get("contributor")) + flatten_list(item.get("contributors")) + flatten_list(item.get("creators")),
        "format": flatten_list(payload.get("original_format")) + flatten_list(payload.get("online_format")) + flatten_list(item.get("format")) + flatten_list(item.get("formats")) + flatten_list(item.get("genre")),
        "language": flatten_list(payload.get("language")) + flatten_list(item.get("language")),
        "note": flatten_list(item.get("notes")) + flatten_list(payload.get("description")),
    }

    # Normalize, lowercase for faceted matching, de-dupe.
    normalized: Dict[str, List[str]] = {}
    for k, vals in terms.items():
        cleaned = []
        for v in vals:
            s = normalize_text(v)
            if s:
                cleaned.append(s.lower())
        normalized[k] = list(dict.fromkeys(cleaned))
    return normalized


def upsert_item(conn: sqlite3.Connection, json_path: Path, images_root: Path) -> None:
    raw = json_path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    item = payload.get("item") or {}

    item_id = normalize_text(item.get("id") or payload.get("id") or payload.get("url") or json_path.parent.name)
    title = normalize_text(payload.get("title") or item.get("title"))
    date_raw = normalize_text(payload.get("date") or item.get("date") or item.get("created_published_date") or item.get("created_published"))
    year_start, year_end = parse_year_range(date_raw)

    rel = json_path.relative_to(images_root)
    parts = rel.parts
    collection = parts[0] if len(parts) > 1 else "unknown"
    imageset_folder = str(rel.parent)

    has_jpg, has_tif = has_media_files(json_path.parent)

    unrestricted = 1 if bool(payload.get("unrestricted")) else 0
    rights_advisory = normalize_text(item.get("rights_advisory") or item.get("rights_information"))
    language_text = ", ".join(flatten_list(payload.get("language")))
    repository = normalize_text(item.get("repository"))
    call_number = normalize_text(item.get("call_number"))
    shelf_id = normalize_text(payload.get("shelf_id"))
    now = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    conn.execute(
        """
        INSERT INTO items (
            item_id, url, title, date_raw, year_start, year_end,
            collection, imageset_folder, json_path,
            has_jpg, has_tif, unrestricted,
            rights_advisory, language_text, repository,
            call_number, shelf_id, created_at, updated_at, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(json_path) DO UPDATE SET
            item_id=excluded.item_id,
            url=excluded.url,
            title=excluded.title,
            date_raw=excluded.date_raw,
            year_start=excluded.year_start,
            year_end=excluded.year_end,
            collection=excluded.collection,
            imageset_folder=excluded.imageset_folder,
            has_jpg=excluded.has_jpg,
            has_tif=excluded.has_tif,
            unrestricted=excluded.unrestricted,
            rights_advisory=excluded.rights_advisory,
            language_text=excluded.language_text,
            repository=excluded.repository,
            call_number=excluded.call_number,
            shelf_id=excluded.shelf_id,
            updated_at=excluded.updated_at,
            raw_json=excluded.raw_json
        """,
        (
            item_id,
            normalize_text(payload.get("url") or item.get("link")),
            title,
            date_raw,
            year_start,
            year_end,
            collection,
            imageset_folder,
            str(rel),
            has_jpg,
            has_tif,
            unrestricted,
            rights_advisory,
            language_text,
            repository,
            call_number,
            shelf_id,
            now,
            now,
            raw,
        ),
    )

    row = conn.execute("SELECT id FROM items WHERE json_path = ?", (str(rel),)).fetchone()
    if not row:
        return
    db_item_id = int(row[0])

    terms = collect_terms(payload)

    conn.execute("DELETE FROM item_terms WHERE item_id = ?", (db_item_id,))
    for term_type, values in terms.items():
        conn.executemany(
            "INSERT OR IGNORE INTO item_terms(item_id, term_type, term_value) VALUES (?, ?, ?)",
            [(db_item_id, term_type, v) for v in values],
        )

    fts_values = {
        "title": title.lower(),
        "subjects": " ".join(terms.get("subject", [])),
        "contributors": " ".join(terms.get("contributor", [])),
        "notes": " ".join(terms.get("note", [])),
        "places": " ".join(terms.get("location", [])),
        "tags": " ".join(terms.get("tag", [])),
    }
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (db_item_id,))
    conn.execute(
        "INSERT INTO items_fts(rowid, title, subjects, contributors, notes, places, tags) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            db_item_id,
            fts_values["title"],
            fts_values["subjects"],
            fts_values["contributors"],
            fts_values["notes"],
            fts_values["places"],
            fts_values["tags"],
        ),
    )


def iter_json_files(images_root: Path) -> Iterable[Path]:
    for p in images_root.rglob("*.json"):
        if p.name.lower() == "item.json":
            yield p


def ingest(images_root: Path, db_path: Path, commit_every: int = 1000) -> None:
    conn = connect(db_path)
    create_schema(conn)

    total = 0
    errors = 0

    try:
        for idx, json_path in enumerate(iter_json_files(images_root), start=1):
            try:
                upsert_item(conn, json_path, images_root)
                total += 1
            except Exception as exc:
                errors += 1
                print(f"[warn] failed to ingest {json_path}: {exc}", file=sys.stderr)

            if idx % commit_every == 0:
                conn.commit()
                print(f"[info] processed={idx} ingested={total} errors={errors}")

        conn.commit()
    finally:
        conn.close()

    print(f"[done] ingested={total} errors={errors} db={db_path}")


def print_stats(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    by_collection = conn.execute(
        "SELECT collection, COUNT(*) AS c FROM items GROUP BY collection ORDER BY c DESC LIMIT 20"
    ).fetchall()
    years = conn.execute("SELECT MIN(year_start), MAX(year_end) FROM items").fetchone()

    print(f"items: {total}")
    print(f"year-range: {years[0]}..{years[1]}")
    print("top collections:")
    for row in by_collection:
        print(f"  {row[0]}: {row[1]}")


def run_query(
    conn: sqlite3.Connection,
    collection: Optional[str],
    year_from: Optional[int],
    year_to: Optional[int],
    subject: Optional[str],
    location: Optional[str],
    tag: Optional[str],
    contributor: Optional[str],
    fts: Optional[str],
    limit: int,
) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row

    where: List[str] = []
    where_args: List[Any] = []
    join_args: List[Any] = []
    joins: List[str] = []

    if collection:
        where.append("i.collection = ?")
        where_args.append(collection)

    if year_from is not None:
        where.append("COALESCE(i.year_end, i.year_start, 9999) >= ?")
        where_args.append(year_from)

    if year_to is not None:
        where.append("COALESCE(i.year_start, i.year_end, 0) <= ?")
        where_args.append(year_to)

    def add_term_filter(term_type: str, value: Optional[str]) -> None:
        if not value:
            return
        alias = f"t_{term_type}"
        joins.append(f"JOIN item_terms {alias} ON {alias}.item_id = i.id AND {alias}.term_type = ? AND {alias}.term_value LIKE ?")
        join_args.append(term_type)
        join_args.append(f"%{value.lower()}%")

    add_term_filter("subject", subject)
    add_term_filter("location", location)
    add_term_filter("tag", tag)
    add_term_filter("contributor", contributor)

    if fts:
        joins.append("JOIN items_fts f ON f.rowid = i.id")
        where.append("items_fts MATCH ?")
        where_args.append(fts)

    where_sql = " AND ".join(where) if where else "1=1"
    join_sql = "\n".join(joins)

    sql = f"""
        SELECT DISTINCT
            i.item_id,
            i.title,
            i.date_raw,
            i.year_start,
            i.year_end,
            i.collection,
            i.url,
            i.json_path
        FROM items i
        {join_sql}
        WHERE {where_sql}
        ORDER BY COALESCE(i.year_start, 9999), i.title
        LIMIT ?
    """
    args: List[Any] = join_args + where_args + [limit]
    return conn.execute(sql, args).fetchall()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="LoC metadata database builder and query tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest all item.json files into SQLite")
    p_ingest.add_argument("--images-root", required=True, type=Path, help="Path to collection root (e.g. /tank/media/Images/Library of Congress)")
    p_ingest.add_argument("--db", default=Path("loc_metadata.db"), type=Path, help="SQLite DB path")
    p_ingest.add_argument("--commit-every", type=int, default=1000)

    p_stats = sub.add_parser("stats", help="Show database summary")
    p_stats.add_argument("--db", default=Path("loc_metadata.db"), type=Path)

    p_query = sub.add_parser("query", help="Run a metadata query")
    p_query.add_argument("--db", default=Path("loc_metadata.db"), type=Path)
    p_query.add_argument("--collection")
    p_query.add_argument("--year-from", type=int)
    p_query.add_argument("--year-to", type=int)
    p_query.add_argument("--subject")
    p_query.add_argument("--location")
    p_query.add_argument("--tag")
    p_query.add_argument("--contributor")
    p_query.add_argument("--fts", help="FTS5 query over title/subjects/contributors/notes/places/tags")
    p_query.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        ingest(args.images_root, args.db, args.commit_every)
        return 0

    conn = connect(args.db)
    try:
        if args.cmd == "stats":
            print_stats(conn)
            return 0

        rows = run_query(
            conn=conn,
            collection=args.collection,
            year_from=args.year_from,
            year_to=args.year_to,
            subject=args.subject,
            location=args.location,
            tag=args.tag,
            contributor=args.contributor,
            fts=args.fts,
            limit=args.limit,
        )
        for r in rows:
            print(json.dumps(dict(r), ensure_ascii=True))
        print(f"rows={len(rows)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
