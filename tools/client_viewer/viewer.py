#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, render_template


BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)
app.config["FILTER_API_BASE"] = "http://127.0.0.1:8080"
app.config["POLL_SECONDS"] = 20
app.config["SLIDE_SECONDS"] = 8
app.config["REQUEST_TIMEOUT_SECONDS"] = 8
app.config["LAST_SELECTION"] = {
    "source": "none",
    "fetched_at": None,
    "count": 0,
    "updated_at": None,
    "items": [],
    "active_filter": {},
}


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_remote_selection(base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    clean_base = base_url.rstrip("/")
    target = urllib.parse.urljoin(f"{clean_base}/", "api/active-selection")
    req = urllib.request.Request(target, headers={"Accept": "application/json"})

    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read().decode("utf-8")

    payload = json.loads(body)
    return {
        "source": "remote",
        "fetched_at": utc_now_iso(),
        "count": int(payload.get("count") or 0),
        "updated_at": payload.get("updated_at"),
        "items": payload.get("items") or [],
        "active_filter": payload.get("active_filter") or {},
    }


def get_selection_with_cache() -> Dict[str, Any]:
    base = str(app.config["FILTER_API_BASE"])
    timeout_seconds = int(app.config["REQUEST_TIMEOUT_SECONDS"])
    cached = dict(app.config["LAST_SELECTION"])

    try:
        fresh = fetch_remote_selection(base, timeout_seconds)
        app.config["LAST_SELECTION"] = fresh
        return fresh
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        fallback = dict(cached)
        fallback["source"] = "cache"
        fallback["error"] = str(exc)
        if fallback.get("fetched_at") is None:
            fallback["fetched_at"] = utc_now_iso()
        return fallback


@app.route("/")
def index() -> str:
    viewer_config = {
        "pollSeconds": int(app.config["POLL_SECONDS"]),
        "slideSeconds": int(app.config["SLIDE_SECONDS"]),
        "filterApiBase": str(app.config["FILTER_API_BASE"]),
    }
    return render_template("index.html", viewer_config=json.dumps(viewer_config, ensure_ascii=True))


@app.route("/api/selection")
def api_selection() -> Any:
    payload = get_selection_with_cache()
    return jsonify(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gallery Manager client viewer")
    parser.add_argument("--filter-api-base", default="http://127.0.0.1:8080", help="Filter control API base URL")
    parser.add_argument("--poll-seconds", type=int, default=20, help="Seconds between active-selection polls")
    parser.add_argument("--slide-seconds", type=int, default=8, help="Seconds between slide transitions")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    app.config["FILTER_API_BASE"] = args.filter_api_base
    app.config["POLL_SECONDS"] = max(5, args.poll_seconds)
    app.config["SLIDE_SECONDS"] = max(2, args.slide_seconds)

    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())