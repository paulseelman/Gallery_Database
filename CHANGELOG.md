# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [0.2.2] - 2026-07-05
### Changed
- Removed legacy compatibility directories `tools/filter_control` and `tools/client_viewer` after the merged web app transition.
- Simplified CI checks to only validate canonical entrypoints.
- Updated README structure and migration notes to reflect the final directory layout.

## [0.2.1] - 2026-07-05
### Changed
- Renamed the unified app module folder from `tools/filter_control` to `tools/gallery_webapp` for clearer ownership.
- Kept `tools/filter_control/webapp.py` as a compatibility wrapper so existing commands continue to work.
- Removed stale standalone viewer static/template assets from `tools/client_viewer` now that viewer rendering is fully unified.
- Updated wrappers, CI syntax checks, and README structure/commands to use the new canonical path.

## [0.2.0] - 2026-07-05
### Changed
- Improved JSON discovery during ingest to support collections where metadata files are not always named `item.json` (for example LoC item folders with numeric JSON basenames).
- Updated collection inference so `collection` uses the parent folder of each imageset rather than the source root folder.
- Normalized `json_path` keys relative to the nearest `Images` directory segment to keep upserts stable regardless of ingest root choice.
- Rebuilt the local metadata database from `/tank/media/Images` using the new rules.
- Optimized `/api/results` query planning and ordering for substantially lower filter latency.
- Switched `any_term` filtering to use FTS-backed matching for faster free-text lookups.
- Added startup index assurance and warm-cache behavior for UI facets.
- Added dedicated `GET /api/collections` endpoint so collection dropdown loading is independent from full facet aggregation.

## [0.1.0] - 2026-07-05
### Added
- Initial SQLite ingestion pipeline for Library of Congress item metadata JSON files.
- Normalized metadata schema with faceted term indexing for subjects, locations, tags, contributors, formats, languages, and notes.
- FTS5 search support across title and key metadata text fields.
- CLI commands for ingest, stats, and filtered query operations.
- Project documentation and usage examples.

[0.2.2]: https://github.com/paulseelman/Gallery_Manager/releases/tag/v0.2.2
[0.2.1]: https://github.com/paulseelman/Gallery_Manager/releases/tag/v0.2.1
[0.2.0]: https://github.com/paulseelman/Gallery_Manager/releases/tag/v0.2.0
[0.1.0]: https://github.com/paulseelman/Gallery_Manager/releases/tag/v0.1.0
