# Lineage Data Inventory

**Project:** spectral-feature-engine
**Scope:** Inventory of all data sources available *within the repository* and assessment of what is required to construct a complete spectral data-lineage (provenance) system.
**Status:** Analysis only — no datasets were modified and no lineage tables were created.
**Generated:** 2026-06-21

---

## 1. Executive Summary

The repository contains the *derived* products of a spectral preprocessing pipeline — metadata tables, summary reports, and a single relational-build script — but **not** the underlying spectral data. The raw and cleaned spectra are held externally in Google Drive (`https://drive.google.com/drive/folders/1teRB8PcGcusi1vv0On_fIcETlsjSJ3fV`) and are explicitly excluded from version control (see `data/README.txt` and `data/config.py`).

Key findings:

- **A substantial portion of lineage can already be reconstructed from repository contents.** `metadata/metadata_database.csv` (1,803 accepted spectra, 30 columns) preserves the original raw filename, source library, and a composite cleaned identifier for every accepted spectrum. `metadata/mineral_metadata.csv` provides a clean mineral dimension table, and `reports/rejection_report.csv` documents all 47 rejected spectra with removal reasons.
- **The two spectrum identifier schemes in the repository do not share an explicit join key.** `metadata_database.csv` uses a composite ID (`{Mineral}_{rawstem}_{hash}`), while `metadata/spectrum_metadata.csv` uses a synthetic normalized ID (`ALB001`). They can currently only be linked *heuristically* (via `mineral_name` + `sample_name` ↔ `original_filename` stem), which succeeds for 1,354/1,354 normalized rows but is not authoritative.
- **Acquisition-level provenance is missing.** Fields such as `instrument`, `collection_date`, `grain_size`, `sample_origin`, and `reference_source` exist as columns in `metadata_database.csv` but are populated entirely with `unknown`/null placeholders.
- **Per-record deduplication lineage does not exist.** Reports record only aggregate duplicate counts (277 removed during cleaning; a further reduction from 1,803 → 1,354 during normalization). There is no record mapping which raw spectra were collapsed into which surviving record.
- **A complete lineage system requires the Google Drive dataset** to (a) recover acquisition metadata from raw file headers / source-library catalogs, and (b) authoritatively rebuild the cleaned-identifier ↔ raw-file mapping by re-scanning the `cleaned/` parquet files.

Overall: **basic file-level provenance (raw → cleaned → mineral → source) is recoverable today; acquisition metadata and authoritative deduplication lineage are not.**

---

## 2. Repository Data Sources

The repository as cloned contains the following data-bearing files. (Note: the actual on-disk layout differs slightly from the layout described in the task brief — `config.py` and `README.txt` live under `data/`, `build_spectrum_metadata.py` is at the repository root, and there is **no** `src/preprocessing/` directory.)

| Path | Type | Rows | Cols | Role |
|------|------|------|------|------|
| `metadata/mineral_metadata.csv` | CSV | 20 | 8 | Mineral dimension / reference table |
| `metadata/spectrum_metadata.csv` | CSV | 1,354 | 11 | Normalized, deduplicated spectrum table |
| `metadata/metadata_database.csv` | CSV | 1,803 | 30 | Full per-spectrum provenance/processing record (accepted spectra) |
| `reports/preprocessing_report.md` | Markdown | — | — | Human-readable preprocessing summary |
| `reports/rejection_report.csv` | CSV | 47 | 10 | Per-spectrum rejection log |
| `reports/summary_statistics.csv` | CSV | 29 | 2 | Key/value summary statistics |
| `features/spectral_features.csv` | CSV | **0 (empty)** | — | Feature output (placeholder, no data) |
| `features/complexity_features.csv` | CSV | **0 (empty)** | — | Feature output (placeholder, no data) |
| `features/symmetry_features.csv` | CSV | **0 (empty)** | — | Feature output (placeholder, no data) |
| `features/pysr_ready.csv` | CSV | **0 (empty)** | — | Feature output (placeholder, no data) |
| `build_spectrum_metadata.py` | Python | 284 | — | Script that builds `spectrum_metadata.csv` |
| `data/config.py` | Python | 21 | — | Path configuration (points `DATA_PATH` at Google Drive) |
| `data/README.txt` | Text | 35 | — | Documents external data location & expected structure |

**Important caveats**

- All four files under `features/` are **empty (0 bytes)** in the repository and carry no lineage value at present.
- The actual spectral arrays (`raw/`, `cleaned/`) referenced by `data/config.py` and `data/README.txt` are **not present**; `DATA_PATH` resolves to a Google Drive URL.
- The preprocessing pipeline source code referenced by `data/README.txt` ("scripts in `src/`") is **not present in the repository.** Only `build_spectrum_metadata.py` (the relational/metadata layer) is available; the code that actually produced `metadata_database.csv` and the cleaned parquet files is external.

---

## 3. Metadata Inventory

### 3.1 `metadata/mineral_metadata.csv`

- **Row count:** 20 (one row per mineral)
- **Columns (8):** `mineral_id`, `mineral_name`, `formula`, `crystal_system`, `space_group`, `symmetry_rank`, `group`, `structure_class`
- **Primary identifier:** `mineral_id` (integer, 1–20). `mineral_name` is a secondary natural key (unique).
- **Relationships:**
  - `mineral_id` is the foreign-key target of `spectrum_metadata.mineral_id`.
  - `mineral_name` joins to `metadata_database.mineral_name` and `rejection_report.mineral`.
- **Usefulness for lineage:** High as a **dimension table**. It anchors every spectrum to a canonical mineral identity and its crystallographic attributes. It contains no spectrum-level provenance itself but is essential for normalizing mineral references across the other tables. All mineral names appearing in `spectrum_metadata.csv` and `metadata_database.csv` resolve cleanly to this table (no orphans).

### 3.2 `metadata/spectrum_metadata.csv`

- **Row count:** 1,354 (deduplicated; fewer than the 1,803 accepted spectra — see §4)
- **Columns (11):** `spectrum_id`, `mineral_id`, `mineral_name`, `source`, `instrument`, `sample_name`, `wavelength_range`, `resolution`, `preprocessing_version`, `signal_quality`, `is_valid`
- **Primary identifier:** `spectrum_id` — synthetic, format `{MIN}{NNN}` (e.g. `ALB001`), unique across all 1,354 rows.
- **Relationships:**
  - `mineral_id` → `mineral_metadata.mineral_id` (clean FK).
  - **No explicit key** to `metadata_database.csv`. Linkage is only possible heuristically via `mineral_name` + `sample_name` ↔ `metadata_database.original_filename` stem (see §4).
- **Field observations:**
  - `source`: RELAB 987, USGS 189, RRUFF 178.
  - `instrument`: `UNKNOWN` 1,001, `ASD` 189, `Raman` 164 (instrument is *inferred from filename patterns*, not measured).
  - `resolution`: empty for all rows.
  - `preprocessing_version`: constant `v1.0`.
  - `signal_quality`: constant `1.0`.
  - `is_valid`: `True` for all rows (the script never assigns `False`).
  - `wavelength_range`: constant `"400-2500"` (the interpolation grid, not a per-spectrum measured range).
- **Usefulness for lineage:** Medium. It is the cleanest normalized entry point (good FK to minerals, parsed `sample_name`), but several of its fields are constants/inferred placeholders, and its `spectrum_id` is disconnected from the raw-file-bearing identifier in `metadata_database.csv`.

### 3.3 `metadata/metadata_database.csv`

- **Row count:** 1,803 (matches "total accepted" in `preprocessing_report.md`)
- **Columns (30):** `spectrum_id`, `mineral_name`, `source_library`, `original_filename`, `measurement_type`, `instrument`, `collection_date`, `grain_size`, `sample_origin`, `reference_source`, `crystal_system`, `formula`, `space_group`, `space_group_number`, `wavelength_min`, `wavelength_max`, `num_points`, `processing_steps`, `smoothing_window`, `smoothing_polynomial_order`, `interpolation_method`, `normalization_method`, `quality_flag`, `coverage`, `interpolated_points`, `pre_variance`, `post_variance`, `negatives_clipped`, `outliers_adjusted`, `quality_score`
- **Primary identifier:** `spectrum_id` — composite, format `{Mineral}_{raw_stem}_{hash}` (e.g. `Albite_bir1jb587_4633e90c`), unique across all 1,803 rows. The trailing 8-character hash is unique per record (1,803/1,803), making this the most reliable per-spectrum key in the repository.
- **Relationships:**
  - `mineral_name` → `mineral_metadata.mineral_name`.
  - `original_filename` (e.g. `bir1jb587.tab`) embeds the raw identifier; the same stem is reproduced inside `spectrum_id`.
  - No FK to `spectrum_metadata.spectrum_id`.
- **Field observations (provenance-critical):**
  - **Populated & meaningful:** `original_filename` (1,719 distinct values; 84 filenames recur across *different minerals*, so the filename alone is not globally unique — the hash disambiguates), `source_library` (relab 1,001 / usgs 614 / rruff 188), processing parameters (`processing_steps`, `smoothing_window=11`, `smoothing_polynomial_order=3`, `interpolation_method=linear`, `normalization_method=minmax`), and per-spectrum cleaning metrics (`num_points`, `coverage`, `pre_variance`, `post_variance`, `negatives_clipped`, `outliers_adjusted`, `interpolated_points`).
  - **Placeholder / unusable:** `measurement_type` = `reflectance` (constant), `instrument` = `unknown` (all rows), `collection_date` = `unknown` (all rows), `grain_size` = `unknown` (all rows), `sample_origin` = `unknown` (all rows), `reference_source` = null (all rows), `quality_flag` = `OK` (constant), `quality_score` = empty, and the crystallographic columns (`crystal_system`, `formula`, `space_group`, `space_group_number`) are empty here (they are instead available via the `mineral_metadata.csv` join).
- **Usefulness for lineage:** **Highest in the repository.** This is the de-facto provenance ledger: it links each accepted cleaned spectrum to its raw filename, source library, and processing parameters. Its main limitations are (a) the missing acquisition fields above and (b) the absence of a key to the normalized `spectrum_metadata.csv`.

### 3.4 Cross-table relationship summary

```
mineral_metadata (20)
   ^ mineral_id            ^ mineral_name              ^ mineral_name / mineral
   |                       |                           |
spectrum_metadata (1,354)  metadata_database (1,803)   rejection_report (47)
   normalized ID              composite ID  ───────────►  raw file_path
   (ALB001)                   (Mineral_stem_hash)         (data\raw\...)
        \__ heuristic link via mineral_name + sample_name ↔ original_filename stem __/
```

- `mineral_metadata` is the shared dimension; every other table resolves to it cleanly.
- `metadata_database` (accepted) and `rejection_report` (rejected) are mutually exclusive partitions of the processed corpus, both keyed off raw filenames.
- `spectrum_metadata` is a normalized **subset/rollup** of the accepted spectra with its own ID space and no authoritative key back to the raw filename.

---

## 4. Existing Provenance Information

### 4.1 Acceptance / rejection accounting

From `reports/preprocessing_report.md`:

| Metric | Value |
|--------|-------|
| Total spectra processed | 1,850 |
| Total spectra accepted | 1,803 |
| Total spectra rejected | 47 |
| Acceptance rate | 97.5% |

`metadata_database.csv` row count (1,803) is consistent with "accepted". `rejection_report.csv` row count (47) is consistent with "rejected".

> **Inconsistency flag:** `reports/summary_statistics.csv` reports `spectra_rejected = 0` and `spectra_accepted = 1803`, which contradicts the 47 rejections in `preprocessing_report.md` and `rejection_report.csv`. `summary_statistics.csv` also reports physically implausible global wavelength bounds (`wavelength_min_overall = -984028`, `wavelength_max_overall = 120414`), indicating it was computed over raw, pre-cleaning values. **`summary_statistics.csv` should be treated as stale/unreliable for provenance purposes.**

### 4.2 Source (library) distribution

| Library | Accepted (`preprocessing_report` / `metadata_database`) | Processed (per-library cleaning table) |
|---------|--------------------------------------------------------|----------------------------------------|
| relab | 1,001 | 1,017 |
| usgs | 614 | 637 (table) / 645 (acceptance-rate section) |
| rruff | 188 | 188 |

> **Inconsistency flag:** The per-library "processed" counts inside `preprocessing_report.md` are internally inconsistent (e.g. USGS appears as both 637 and 645), and they sum to more than the 1,850 headline total. Source attribution at the *aggregate* level is reliable; exact per-library *processed* denominators are not.

### 4.3 Rejections (provenance of removed spectra)

`reports/rejection_report.csv` — 47 rows, columns: `file_path`, `library`, `stage`, `reason`, `n_points`, `wavelength_min`, `wavelength_max`, `missing_count`, `quality_score`, `mineral`.

- **`file_path`** preserves the full raw path (e.g. `data\raw\RELAB\Diopside\capp108.tab`), encoding source library, mineral, and raw filename — strong lineage for rejected items.
- **Rejection by stage:** cleaning 39, parsing 8.
- **Rejection by library:** usgs 31, relab 16 (rruff 0).
- **Dominant reasons:** "Insufficient valid points (< 50)", wavelength/reflectance "Length mismatch", and parse errors ("Insufficient points: 8", largely USGS `errorbars_for_*` files).
- `quality_score` is empty throughout this file.

### 4.4 Quality / distortion statistics

`preprocessing_report.md` provides corpus-level cleaning and distortion metrics, including: duplicates removed = 277, negatives clipped = 8,243, outlier adjustments = 324,220, significantly-altered spectra = 1,418, plus SAM-angle, cosine-similarity, distortion-score and variance-ratio distributions (overall and per library). Per-spectrum equivalents of several of these (`pre_variance`, `post_variance`, `negatives_clipped`, `outliers_adjusted`, `coverage`, `num_points`) are available in `metadata_database.csv`.

### 4.5 Deduplication signal

- `preprocessing_report.md`: **277 duplicates removed** during cleaning (RELAB only, per the per-library table).
- A *second*, separate reduction occurs in `build_spectrum_metadata.py`: the 1,803 accepted spectra are deduplicated by `(mineral_name, sample_name)` down to the **1,354** rows in `spectrum_metadata.csv` (449 records dropped).
- **No per-record deduplication map exists** in either case: there is no table recording which raw/cleaned spectra were treated as duplicates of which survivor.

---

## 5. Missing Provenance Information

The following lineage requirements were assessed against repository contents. "Available" means recoverable today from committed files; "Partially Available" means derivable but heuristic/incomplete; "Missing" means not recoverable from the repository alone.

| Field | Available | Partially Available | Missing |
|-------|-----------|---------------------|---------|
| `raw_id` (original raw identifier) | ✅ `metadata_database.original_filename` (accepted) and `rejection_report.file_path` (rejected); also embedded in `metadata_database.spectrum_id`. Caveat: filename not globally unique (84 collide across minerals) — needs `mineral_name` + hash to disambiguate. | | |
| `cleaned_id` (cleaned-spectrum identifier) | ✅ `metadata_database.spectrum_id` (`Mineral_stem_hash`) for accepted spectra; `spectrum_metadata.spectrum_id` (`ALB001`) as a normalized ID. | | |
| `source` (library) | ✅ `metadata_database.source_library`, `spectrum_metadata.source`, `rejection_report.library`. Aggregate counts reliable. | | |
| `mineral_id` | ✅ Direct in `spectrum_metadata`; resolvable in the other tables via `mineral_name` → `mineral_metadata`. | | |
| `sample_name` | ✅ `spectrum_metadata.sample_name` (parsed); derivable from `original_filename`. | (Note: for ~74% of normalized rows `instrument` could not be inferred, but `sample_name` itself is populated.) | |
| `original_file` (full source path) | ✅ `rejection_report.file_path` (full path) and `metadata_database.original_filename` (basename). | Full source-relative path for *accepted* spectra is only basename + library, not the complete `raw/<LIB>/<Mineral>/...` path. | |
| `deduplication_status` | | ⚠️ Only aggregate counts (277 cleaning-stage; 1,803→1,354 normalization). | ❌ Per-record "duplicate-of" mapping does not exist. |
| `removal_reason` | ✅ `rejection_report.reason` + `stage` for all 47 rejected spectra. | | (Not applicable to accepted spectra.) |
| `instrument` (measured) | | ⚠️ `spectrum_metadata.instrument` is *inferred from filename* (1,001/1,354 `UNKNOWN`). | ❌ True measured instrument absent (`metadata_database.instrument` = `unknown` everywhere). |
| `collection_date` | | | ❌ `unknown` for all 1,803 rows. |
| `grain_size` | | | ❌ `unknown` for all 1,803 rows. |
| `sample_origin` | | | ❌ `unknown` for all 1,803 rows. |
| `reference_source` | | | ❌ Null for all 1,803 rows. |
| `resolution` / measured `wavelength_range` | | ⚠️ Interpolation grid known (`400–2500 nm`, 1 nm step); per-spectrum native `num_points`/`wavelength_min`/`max` available in `metadata_database`. | ❌ Native instrument spectral resolution not recorded. |
| `normalized_id ↔ cleaned_id` crosswalk | | ⚠️ Heuristic link via `mineral_name` + `sample_name` ↔ `original_filename` stem (matched 1,354/1,354). | ❌ No authoritative stored key. |

**Summary of gaps:**
1. **Acquisition metadata** (`instrument`, `collection_date`, `grain_size`, `sample_origin`, `reference_source`, native resolution) is entirely placeholder.
2. **Per-record deduplication lineage** is absent (only counts exist).
3. **Authoritative ID crosswalk** between the normalized (`ALB001`) and composite (`Mineral_stem_hash`) identifier spaces is absent (only a heuristic bridge exists).

---

## 6. Google Drive Dependency Analysis

**Conclusion: Yes — building a *complete* lineage system requires access to the Google Drive dataset.** Basic file-level lineage can be assembled from the repository, but the gaps in §5 cannot be closed without the external data.

### 6.1 What is needed from Google Drive

| Drive artifact | Why it is needed | What it unlocks |
|----------------|------------------|-----------------|
| `raw/<LIB>/<Mineral>/*` (original spectral files + headers) | The acquisition fields (`instrument`, `collection_date`, `grain_size`, `sample_origin`, `reference_source`, native resolution) are `unknown`/null in `metadata_database.csv`. These values live in the raw file headers and the source-library catalogs (RRUFF/USGS splib/RELAB), not in any committed file. | Populates the currently-empty acquisition provenance fields; recovers full `raw/<LIB>/<Mineral>/...` source paths for accepted spectra. |
| `cleaned/<Mineral>/*_cleaned.parquet` | `build_spectrum_metadata.py` derives the normalized `ALB001` IDs *by scanning these parquet filenames* and parsing `sample_name`/`source`/`instrument` from them. The cleaned filenames are the only authoritative bridge between the normalized IDs and the composite/raw IDs. | Builds an **authoritative** `cleaned_id ↔ raw_id ↔ normalized_id` crosswalk (replacing the heuristic link), and lets the dedup logic be re-run to capture per-record deduplication decisions. |
| `metadata/` on Drive (if it contains richer source catalogs) | The repo's `data/README.txt` lists a `metadata/` folder in the expected Drive structure; it may hold source-library catalog files with the acquisition fields above. | Could directly supply `collection_date`, `grain_size`, `sample_origin`, `reference_source` without re-parsing raw headers. |

### 6.2 What *cannot* be reconstructed from repository metadata alone

- **Acquisition provenance** (`instrument`, `collection_date`, `grain_size`, `sample_origin`, `reference_source`, native resolution) — no committed file contains non-placeholder values.
- **Per-record deduplication mapping** — neither the 277 cleaning-stage duplicates nor the 449 normalization-stage collapses are traceable to specific record pairs without re-running the pipeline against the cleaned files.
- **Authoritative normalized↔composite ID crosswalk** — only a heuristic (mineral + sample-name) link is possible from the repo; the definitive mapping requires the cleaned parquet filenames the build script consumes.
- **Verification/repair of the inconsistent aggregates** in `summary_statistics.csv` and the per-library "processed" counts — these require recomputation over the actual spectra.

### 6.3 Access note

Per the task brief and `data/README.txt`, direct Google Drive access may not be permitted in this environment, and `data/config.py` hard-codes Windows/Drive paths (`c:/Users/Vitaly/...` in `build_spectrum_metadata.py`). If Drive access is unavailable, the lineage system can only be built to the "file-level" tier described in §5 (raw_id / cleaned_id / source / mineral_id / sample_name / removal_reason), with acquisition and deduplication tiers deferred.

---

## 7. Recommendations for Next Steps

1. **Build the recoverable tier first (no Drive needed).** A file-level lineage table can be assembled today from `metadata_database.csv` (accepted) + `rejection_report.csv` (rejected), keyed by the composite `spectrum_id`/hash, joined to `mineral_metadata.csv`. This already yields `raw_id`, `cleaned_id`, `source`, `mineral_id`, `sample_name`, `original_file`, and `removal_reason`.
2. **Establish the normalized↔composite ID crosswalk explicitly.** Persist the heuristic `mineral_name` + `sample_name` ↔ `original_filename` mapping (currently 1,354/1,354) as an interim crosswalk, clearly labelled as *heuristic*, pending authoritative reconstruction from the cleaned parquet filenames.
3. **Request / mount the Google Drive dataset** to close the acquisition-metadata and deduplication-lineage gaps. Prioritize the `cleaned/` parquet directory (authoritative IDs + dedup) and raw file headers / source catalogs (acquisition fields).
4. **Capture deduplication decisions going forward.** Modify the preprocessing and `build_spectrum_metadata.py` steps to emit a per-record "duplicate-of" / "survivor" mapping rather than only aggregate counts.
5. **Reconcile or regenerate `summary_statistics.csv`.** It currently disagrees with the other reports (0 vs 47 rejected) and contains raw, un-cleaned wavelength extrema; it should be regenerated from the cleaned corpus or marked deprecated.
6. **Parameterize `data/config.py` paths.** The hard-coded Windows/Drive paths in `build_spectrum_metadata.py` should read from `data/config.py` (and support a Linux/mount override) so lineage rebuilds are reproducible across environments.
7. **Populate the empty `features/` outputs** (currently 0 bytes) before treating them as lineage endpoints; downstream feature → spectrum lineage cannot be established until these contain data and a spectrum key.

---

*Prepared as a data-availability inventory only. No datasets were modified and no lineage tables were created.*
