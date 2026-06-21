# Spectrum Metadata Table Report

## Methodology

The canonical table `metadata/spectrum_metadata_table.csv` is derived exclusively from repository data (no Google Drive or external files). `metadata/metadata_database.csv` is the authoritative base: every one of its 1803 accepted-spectrum rows is preserved (no rows dropped).

Output schema (exact order): `spectrum_id, mineral_id, source, instrument, sample_name`.

## Join strategy

- **mineral_id**: `metadata_database.mineral_name` -> `mineral_metadata.mineral_name` -> `mineral_id`. Unmapped names are left null and logged.
- **source**: priority `metadata_database.source_library`, fallback `spectrum_metadata.source`; normalized `relab->RELAB`, `usgs->USGS`, `rruff->RRUFF`.
- **instrument**: priority `spectrum_metadata.instrument`, fallback `metadata_database.instrument`; unknown/empty -> `UNKNOWN`.
- **sample_name**: priority `spectrum_metadata.sample_name`, fallback derived from `metadata_database.original_filename` (extension removed, underscores standardized); empty -> `UNKNOWN`.

Because `spectrum_metadata.csv` uses extracted sample identifiers, each database row is linked to it by deriving a per-source sample key from `original_filename` (RELAB: filename stem; RRUFF: embedded `R#####` id; USGS: catalog id such as `HS143.3B`) and matching on `(mineral_name, sample_key)`.

## spectrum_id generation

Rows are sorted by `mineral_id -> source -> sample_name -> original_filename` and then assigned sequential canonical IDs `SPC-000001, SPC-000002, ...`. Existing IDs are never reused. The ordering is deterministic, so identical inputs always yield identical IDs.

## Missing data summary

- Total rows: 1803
- Unique minerals: 20
- RELAB / USGS / RRUFF: 1001 / 614 / 188
- UNKNOWN instruments: 1028
- Missing mineral_id values: 0

## Inconsistencies found

- 27 database row(s) had no matching record in `spectrum_metadata.csv`; their `instrument` defaults to `UNKNOWN` and `sample_name` is derived from `original_filename`. These are RRUFF `X#####` Raman acquisitions that are absent from the normalized metadata.
- 27 row(s) used the filename-derived `sample_name` fallback.
- No mineral_id or source resolution failures; no rows were dropped.
