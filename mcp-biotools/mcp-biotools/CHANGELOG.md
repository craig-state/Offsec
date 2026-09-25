# Changelog

All notable changes to the BioGenAI BioTools MCP Server.

## [2.4.1] - 2024-11-18

### Added
- `get_dataset_stats` tool for storage and usage statistics
- `search_across_datasets` tool for cross-dataset full-text search
- `list_running_experiments` and `get_experiment_details` tools for ML experiment tracking
- `server_info` tool for version and configuration summary
- Docker support with multi-stage build

### Changed
- Refactored server into modular package structure (`biotools/`)
- Improved query result simulation with deterministic hashing
- Added comprehensive column schema with types and descriptions

## [2.3.0] - 2024-09-12

### Added
- `get_dataset_schema` tool for inspecting column definitions
- Configuration management via environment variables
- Structured logging throughout

### Fixed
- Query timeout handling for large datasets

## [2.0.0] - 2024-06-01

### Changed
- Migrated from custom protocol to MCP (Model Context Protocol)
- Replaced REST API with stdio-based MCP transport

## [1.0.0] - 2024-01-15

### Added
- Initial release with `list_datasets` and `query_data` tools
- Basic dataset registry with 5 warehouse datasets
