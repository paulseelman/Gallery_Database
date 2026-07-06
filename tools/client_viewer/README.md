# Client Viewer

This is the initial Gallery Manager client viewer scaffold.

It runs a local web app that:

- Polls the filter control API active selection.
- Builds a slideshow from image-ready items (`thumbnail_url` present).
- Rotates through current items on a fixed interval.
- Falls back to last cached payload when the filter service is temporarily unavailable.

## Run

```bash
cd /path/to/Gallery_Manager
.venv/bin/python tools/client_viewer/viewer.py \
	--filter-api-base http://127.0.0.1:8080 \
	--host 0.0.0.0 \
	--port 8090
```

Open:

```text
http://<your-server-ip>:8090
```

## Options

- `--filter-api-base`: base URL for filter control service.
- `--poll-seconds`: how often viewer polls `/api/active-selection`.
- `--slide-seconds`: per-image display interval.
- `--host`: bind address.
- `--port`: viewer port.
- `--debug`: Flask debug mode.