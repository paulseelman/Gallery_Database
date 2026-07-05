# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]
### Changed
- Improved JSON discovery during ingest to support collections where metadata files are not always named `item.json` (for example LoC item folders with numeric JSON basenames).
- Updated collection inference so `collection` uses the parent folder of each imageset rather than the source root folder.
- Normalized `json_path` keys relative to the nearest `Images` directory segment to keep upserts stable regardless of ingest root choice.
- Rebuilt the local metadata database from `/tank/media/Images` using the new rules.

## [0.1.0] - 2026-07-05
### Added
- Initial SQLite ingestion pipeline for Library of Congress item metadata JSON files.
- Normalized metadata schema with faceted term indexing for subjects, locations, tags, contributors, formats, languages, and notes.
- FTS5 search support across title and key metadata text fields.
- CLI commands for ingest, stats, and filtered query operations.
- Project documentation and usage examples.

[0.1.0]: https://github.com/paulseelman/Gallery_Database/releases/tag/v0.1.0
