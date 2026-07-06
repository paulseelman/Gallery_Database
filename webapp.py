#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "loc_metadata.db"
DEFAULT_STATE_PATH = BASE_DIR / "filter_state.db"
DEFAULT_IMAGES_ROOT = Path("/tank/media/Images/Library of Congress")

FILTER_KEYS = {
    "collection",
    "year_from",
    "year_to",
    "any_term",
    "subject",
    "location",
    "tag",
    "contributor",
    "fts",
    "limit",
    "shuffle",
}


app = Flask(__name__)
app.config["DB_PATH"] = str(DEFAULT_DB_PATH)
app.config["STATE_DB_PATH"] = str(DEFAULT_STATE_PATH)
app.config["IMAGES_ROOT"] = str(DEFAULT_IMAGES_ROOT)

_FACETS_CACHE: Dict[str, Any] = {
    "db_mtime": None,
    "limit": None,
    "payload": None,
}

_COLLECTIONS_CACHE: Dict[str, Any] = {
    "db_mtime": None,
    "limit": None,
    "payload": None,
}


def get_or_build_facets_payload(db_path: Path, limit: int) -> Dict[str, Any]:
    db_mtime = db_path.stat().st_mtime
    cached = (
        _FACETS_CACHE.get("payload") is not None
        and _FACETS_CACHE.get("db_mtime") == db_mtime
        and _FACETS_CACHE.get("limit") == limit
    )
    if cached:
        return _FACETS_CACHE["payload"]

    with db_conn(db_path) as conn:
        facets = {
            "collections": collection_values(conn, limit=limit),
            "subjects": facet_values(conn, "subject", limit=limit),
            "locations": facet_values(conn, "location", limit=limit),
            "tags": facet_values(conn, "tag", limit=limit),
            "contributors": facet_values(conn, "contributor", limit=limit),
        }

    payload = {"facets": facets}
    _FACETS_CACHE["db_mtime"] = db_mtime
    _FACETS_CACHE["limit"] = limit
    _FACETS_CACHE["payload"] = payload
    return payload


def get_or_build_collections_payload(db_path: Path, limit: int) -> Dict[str, Any]:
    db_mtime = db_path.stat().st_mtime
    cached = (
        _COLLECTIONS_CACHE.get("payload") is not None
        and _COLLECTIONS_CACHE.get("db_mtime") == db_mtime
        and _COLLECTIONS_CACHE.get("limit") == limit
    )
    if cached:
        return _COLLECTIONS_CACHE["payload"]

    with db_conn(db_path) as conn:
        collections = collection_values(conn, limit=limit)

    payload = {"collections": collections}
    _COLLECTIONS_CACHE["db_mtime"] = db_mtime
    _COLLECTIONS_CACHE["limit"] = limit
    _COLLECTIONS_CACHE["payload"] = payload
    return payload


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_query_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_items_year_start_title ON items(year_start, title);
        CREATE INDEX IF NOT EXISTS idx_items_collection_year_title ON items(collection, year_start, title);
        """
    )
    conn.commit()


def init_state_db() -> None:
    state_path = Path(app.config["STATE_DB_PATH"])
    with db_conn(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_filter (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                filter_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def default_filter() -> Dict[str, Any]:
    return {
        "collection": "",
        "year_from": None,
        "year_to": None,
        "any_term": "",
        "subject": "",
        "location": "",
        "tag": "",
        "contributor": "",
        "fts": "",
        "limit": 60,
        "shuffle": False,
    }


def normalize_filter(data: Dict[str, Any]) -> Dict[str, Any]:
    out = default_filter()
    for key, value in data.items():
        if key not in FILTER_KEYS:
            continue
        if key in {"collection", "any_term", "subject", "location", "tag", "contributor", "fts"}:
            out[key] = str(value or "").strip()
        elif key in {"year_from", "year_to"}:
            if value in (None, ""):
                out[key] = None
            else:
                out[key] = int(value)
        elif key == "limit":
            limit = int(value or out["limit"])
            out[key] = max(1, min(limit, 500))
        elif key == "shuffle":
            out[key] = bool(value)
    return out


def load_active_filter() -> Dict[str, Any]:
    state_path = Path(app.config["STATE_DB_PATH"])
    with db_conn(state_path) as conn:
        row = conn.execute("SELECT filter_json, updated_at FROM active_filter WHERE id = 1").fetchone()
    if not row:
        return {"filter": default_filter(), "updated_at": None}

    try:
        parsed = json.loads(row["filter_json"])
    except json.JSONDecodeError:
        parsed = default_filter()
    return {"filter": normalize_filter(parsed), "updated_at": row["updated_at"]}


def save_active_filter(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_filter(payload)
    updated_at = utc_now_iso()

    state_path = Path(app.config["STATE_DB_PATH"])
    with db_conn(state_path) as conn:
        conn.execute(
            """
            INSERT INTO active_filter(id, filter_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              filter_json = excluded.filter_json,
              updated_at = excluded.updated_at
            """,
            (json.dumps(normalized, ensure_ascii=True), updated_at),
        )
        conn.commit()

    return {"filter": normalized, "updated_at": updated_at}


def extract_thumbnail(raw_json_text: str) -> str:
    if not raw_json_text:
        return ""

    try:
        payload = json.loads(raw_json_text)
    except json.JSONDecodeError:
        return ""

    item = payload.get("item") or {}
    service_low = item.get("service_low")
    if isinstance(service_low, str) and service_low.strip():
        return service_low.strip()

    image_url = payload.get("image_url")
    if isinstance(image_url, list):
        for entry in image_url:
            if not isinstance(entry, str):
                continue
            url = entry.split("#", 1)[0].strip()
            if url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                return url

    resources = payload.get("resources")
    if isinstance(resources, list):
        for entry in resources:
            if isinstance(entry, dict):
                image = entry.get("image")
                if isinstance(image, str) and image.strip():
                    return image.strip()

    return ""


def facet_values(conn: sqlite3.Connection, term_type: str, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT term_value, COUNT(*) AS c
        FROM item_terms
        WHERE term_type = ?
        GROUP BY term_value
        ORDER BY c DESC, term_value ASC
        LIMIT ?
        """,
        (term_type, limit),
    ).fetchall()
    return [{"value": r["term_value"], "count": r["c"]} for r in rows]


def collection_values(conn: sqlite3.Connection, limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT collection, COUNT(*) AS c
        FROM items
        GROUP BY collection
        ORDER BY c DESC, collection ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{"value": r["collection"], "count": r["c"]} for r in rows]


def build_results_sql(filters: Dict[str, Any]) -> tuple[str, List[Any]]:
    joins: List[str] = []
    join_args: List[Any] = []
    where: List[str] = []
    where_args: List[Any] = []

    if filters.get("collection"):
        where.append("i.collection = ?")
        where_args.append(filters["collection"])

    if filters.get("year_from") is not None:
        where.append("COALESCE(i.year_end, i.year_start, 9999) >= ?")
        where_args.append(filters["year_from"])

    if filters.get("year_to") is not None:
        where.append("COALESCE(i.year_start, i.year_end, 0) <= ?")
        where_args.append(filters["year_to"])

    def add_term(term_type: str, value: Optional[str]) -> None:
        if not value:
            return
        alias = f"t_{term_type}"
        joins.append(
            f"JOIN item_terms {alias} ON {alias}.item_id = i.id AND {alias}.term_type = ? AND {alias}.term_value LIKE ?"
        )
        join_args.append(term_type)
        join_args.append(f"%{value.lower()}%")

    add_term("subject", filters.get("subject"))
    add_term("location", filters.get("location"))
    add_term("tag", filters.get("tag"))
    add_term("contributor", filters.get("contributor"))

    fts_match_args: List[str] = []

    if filters.get("any_term"):
        # Fast path: map free-text any_term to FTS tokens instead of a
        # wildcard LIKE scan across item_terms.
        tokens = re.findall(r"[0-9A-Za-z_]+", filters["any_term"].lower())
        if tokens:
            fts_match_args.append(" AND ".join(tokens))

    if filters.get("fts"):
        fts_match_args.append(filters["fts"])

    if fts_match_args:
        joins.append("JOIN items_fts f ON f.rowid = i.id")
        for _ in fts_match_args:
            where.append("items_fts MATCH ?")
        where_args.extend(fts_match_args)

    where_sql = " AND ".join(where) if where else "1=1"
    joins_sql = "\n".join(joins)

    # Keep default ordering index-friendly to avoid full temp-table sorts.
    order_sql = "RANDOM()" if filters.get("shuffle") else "i.year_start, i.title"

    sql = f"""
        SELECT DISTINCT
            i.item_id,
            i.title,
            i.date_raw,
            i.year_start,
            i.year_end,
            i.collection,
            i.url,
            i.json_path,
            i.imageset_folder,
            i.raw_json
        FROM items i
        {joins_sql}
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ?
    """

    args = join_args + where_args + [filters["limit"]]
    return sql, args


def query_results(filters: Dict[str, Any]) -> Dict[str, Any]:
    db_path = Path(app.config["DB_PATH"])
    if not db_path.exists():
        return {"count": 0, "items": [], "error": f"Database not found: {db_path}"}

    with db_conn(db_path) as conn:
        sql, args = build_results_sql(filters)
        rows = conn.execute(sql, args).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "item_id": row["item_id"],
                "title": row["title"],
                "date_raw": row["date_raw"],
                "year_start": row["year_start"],
                "year_end": row["year_end"],
                "collection": row["collection"],
                "url": row["url"],
                "json_path": row["json_path"],
                "imageset_folder": row["imageset_folder"],
                "thumbnail_url": extract_thumbnail(row["raw_json"]),
            }
        )

    return {"count": len(items), "items": items}


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/filter", methods=["GET", "PUT"])
def api_filter() -> Any:
    if request.method == "GET":
        return jsonify(load_active_filter())

    payload = request.get_json(silent=True) or {}
    return jsonify(save_active_filter(payload))


@app.route("/api/results", methods=["GET", "POST"])
def api_results() -> Any:
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        filters = normalize_filter(payload)
    else:
        active = load_active_filter()["filter"]
        filters = normalize_filter(active)

        override_limit = request.args.get("limit")
        if override_limit:
            filters["limit"] = max(1, min(int(override_limit), 500))

    data = query_results(filters)
    data["applied_filter"] = filters
    return jsonify(data)


@app.route("/api/facets", methods=["GET"])
def api_facets() -> Any:
    db_path = Path(app.config["DB_PATH"])
    if not db_path.exists():
        return jsonify({"error": f"Database not found: {db_path}", "facets": {}}), 404

    limit = max(5, min(int(request.args.get("limit", "50")), 200))
    return jsonify(get_or_build_facets_payload(db_path, limit))


@app.route("/api/collections", methods=["GET"])
def api_collections() -> Any:
    db_path = Path(app.config["DB_PATH"])
    if not db_path.exists():
        return jsonify({"error": f"Database not found: {db_path}", "collections": []}), 404

    limit = max(5, min(int(request.args.get("limit", "120")), 200))
    return jsonify(get_or_build_collections_payload(db_path, limit))


@app.route("/api/active-selection", methods=["GET"])
def api_active_selection() -> Any:
    active = load_active_filter()
    result = query_results(active["filter"])
    return jsonify({
        "active_filter": active["filter"],
        "updated_at": active["updated_at"],
        "count": result["count"],
        "items": result["items"],
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Network-accessible filter manager for loc_metadata.db")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("LOC_DB_PATH", DEFAULT_DB_PATH)))
    parser.add_argument("--state-db", type=Path, default=Path(os.environ.get("LOC_STATE_DB", DEFAULT_STATE_PATH)))
    parser.add_argument("--images-root", type=Path, default=Path(os.environ.get("LOC_IMAGES_ROOT", DEFAULT_IMAGES_ROOT)))
    parser.add_argument("--host", default=os.environ.get("LOC_WEB_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LOC_WEB_PORT", "8080")))
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    app.config["DB_PATH"] = str(args.db)
    app.config["STATE_DB_PATH"] = str(args.state_db)
    app.config["IMAGES_ROOT"] = str(args.images_root)

    init_state_db()

    db_path = Path(app.config["DB_PATH"])
    if db_path.exists():
        with db_conn(db_path) as conn:
            ensure_query_indexes(conn)
        # Warm the facets cache for the UI's default load path.
        get_or_build_facets_payload(db_path, limit=120)

    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
