# Client Viewer

The standalone client viewer has been merged into the filter-control app.

Use the primary app:

```bash
cd /path/to/Gallery_Manager
.venv/bin/python webapp.py --db loc_metadata.db --host 0.0.0.0 --port 8080
```

Open viewer:

```text
http://<your-server-ip>:8080/viewer
```

## Compatibility Wrapper

`tools/client_viewer/viewer.py` now forwards to the unified filter-control app entrypoint.