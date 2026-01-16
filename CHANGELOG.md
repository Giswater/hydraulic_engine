# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-01-16

### Added

- This CHANGELOG.md file
- Package folder structure
- Database connection files
- SWMM runner file
- SWMM inp, rpt and out handler files
- Parameter management to the SWMM simulation
- SWMM models file
- EPANET runner file
- EPANET inp, rpt and out handler files
- Parameter management to the EPANET simulation
- EPANET models file
- **FROST-Server / SensorThings API integration**
  - `tools_api.py`: Abstract API client framework with FROST-Server implementation
  - `tools_sensorthings.py`: High-level helper functions for SensorThings API operations
  - `create_frost_connection()`: Global API client connection management
  - `export_to_frost()`: Export SWMM/EPANET simulation results to FROST-Server
  - Support for batch operations to efficiently create/update Things, Datastreams, and Observations
  - Integration with existing export framework (`ExportDataSource.FROST`)

[unreleased]: https://github.com/Giswater/hydraulic_engine/compare/v0.1.0...main
[0.1.0]: https://github.com/Giswater/hydraulic_engine/releases/tag/v0.1.0
