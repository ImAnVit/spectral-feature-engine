# Interim Lineage Crosswalk Report

**Project:** spectral-feature-engine
**Artifact produced:** `metadata/lineage_crosswalk.csv`
**Generator:** `build_lineage_crosswalk.py`
**Scope:** Repository-level only — built without access to the external Google Drive dataset.
**Status:** No existing files were modified.
**Generated:** 2026-06-21

---

## 1. Purpose

This report documents the construction of an interim accepted-spectrum **crosswalk** that links the four repository tables identified in `reports/lineage_data_inventory.md`:

1. `metadata/metadata_database.csv` — authoritative per-spectrum record for accepted spectra (composite IDs).
2. `metadata/spectrum_metadata.csv` — normalized, deduplicated table (synthetic `ALB001`-style IDs).
3. `metadata/mineral_metadata.csv` — mineral dimension table (`mineral_id`).
4. `reports/rejection_report.csv` — rejected spectra (excluded before normalization).

The inventory established that these tables share **no explicit join key** between the composite identifier space (`metadata_database`) and the normalized identifier space (`spectrum_metadata`). The crosswalk closes that gap as strongly as possible using only committed data, ahead of Google Drive access becoming available.

## 2. Output Schema

`metadata/lineage_crosswalk.csv` (1,850 rows, 8 columns):

| Column | Description |
|--------|-------------|
| `composite_spectrum_id` | Authoritative ID from `metadata_database.csv` (`{Mineral}_{raw_stem}_{hash}`). Empty for rejected spectra. |
| `normalized_spectrum_id` | Linked ID from `spectrum_metadata.csv` (e.g. `ALB001`). Empty when no normalized counterpart exists. |
| `mineral_id` | Resolved via `mineral_metadata.csv` (`mineral_name` → `mineral_id`). |
| `mineral_name` | Canonical mineral name. |
| `source` | Source library (`relab` / `usgs` / `rruff`), taken from the authoritative record. |
| `original_filename` | Raw filename (basename) from `metadata_database.original_filename` or `rejection_report.file_path`. |
| `sample_name` | Sample identifier parsed by the repository's own parser (see §3). Empty for rejected spectra. |
| `mapping_confidence` | `HIGH` / `MEDIUM` / `LOW` / `UNMATCHED` (see §4). |

## 3. Matching Methodology

### 3.1 Key insight — deterministic reproduction, not fuzzy guessing

The normalized table was produced by `build_spectrum_metadata.py::parse_spectrum_filename`, which derives `sample_name`, `source`, and `instrument` by parsing the **cleaned parquet basename**. That basename has the structure `{Mineral}_{raw_stem}_{hash}` — which is *exactly* the form of `composite_spectrum_id` in `metadata_database.csv`.

Therefore the crosswalk does **not** rely on approximate string similarity. It re-imports the repository's own `parse_spectrum_filename` and applies it to each `composite_spectrum_id`, deterministically reconstructing the `(mineral_name, sample_name)` key on which the normalized table was built. This reproduces the original normalization grouping precisely.

```
# pseudocode
parse = import_from("build_spectrum_metadata.py").parse_spectrum_filename
sample_name = parse(composite_spectrum_id, mineral_name)["sample_name"]
key = (mineral_name, sample_name)
normalized_id = lookup(spectrum_metadata, key)   # group key -> ALB001-style id
```

Validation: all 1,803 accepted records resolve to a `(mineral_name, sample_name)` key, and the number of **distinct** keys (1,354) equals the row count of `spectrum_metadata.csv` (1,354) exactly. Every one of the 1,354 normalized IDs is covered by the crosswalk (100%).

### 3.2 Fallback (heuristic) tier

For robustness, the generator retains a fuzzy fallback for any record whose reproduced key fails to match a normalized row: it looks for a normalized row in the same mineral whose `sample_name` equals, prefixes, or is contained in the raw filename stem. In the current data this path is **never needed** (the deterministic tier matches everything), so it contributes 0 rows — but it makes the methodology resilient if the upstream tables change.

### 3.3 Rejected spectra

The 47 rows in `rejection_report.csv` were rejected during parsing/cleaning and therefore never entered the normalized table. They are included in the crosswalk as `UNMATCHED` (with `composite_spectrum_id` and `normalized_spectrum_id` empty) so the crosswalk is a complete census of the 1,850 processed spectra. Their `UNMATCHED` status reflects *exclusion by design*, not a matching failure.

## 4. Confidence Definitions

| Level | Meaning | Count |
|-------|---------|-------|
| `HIGH` | Deterministic key match **and** the composite is the sole member of its `(mineral, sample_name)` group — an unambiguous 1:1 link in both directions. | 1,211 |
| `MEDIUM` | Deterministic key match, but **multiple** composite records collapse onto the same normalized ID (a deduplication group). The composite → normalized direction is certain; the reverse (which composite is the canonical survivor) is ambiguous. | 592 |
| `LOW` | Matched only via the fuzzy fallback (stem/substring), not via the reproduced key. | 0 |
| `UNMATCHED` | No normalized counterpart: rejected spectra (47), or any accepted record with no resolvable link (0). | 47 |

## 5. Statistics

```
Total crosswalk rows:        1850
  Accepted (metadata_db):    1803
  Rejected (rejection rpt):  47
Matched rows (have norm id): 1803
Unmatched rows:              47

Confidence distribution:
  HIGH      : 1211
  MEDIUM    : 592
  LOW       : 0
  UNMATCHED : 47

Distinct normalized ids covered: 1354 / 1354 (100%)
```

### 5.1 Confidence by source library

| Source | HIGH | MEDIUM | Accepted total |
|--------|------|--------|----------------|
| relab | 1,001 | 0 | 1,001 |
| usgs | 53 | 561 | 614 |
| rruff | 157 | 31 | 188 |

RELAB records are entirely `HIGH`: their raw filenames yield unique, full-stem sample names, so no collapse occurs. Ambiguity is concentrated in USGS (and a little in RRUFF), where the parser extracts coarse tokens (see §7).

### 5.2 Deduplication-group structure (MEDIUM rows)

- 592 `MEDIUM` records belong to **143** deduplication groups (normalized IDs with >1 composite).
- Group sizes range from **2 to 17** composites (mean 4.14).
- Size distribution (group size → number of normalized IDs): `{2:37, 3:38, 4:4, 5:31, 6:26, 9:4, 10:1, 14:1, 17:1}`.

## 6. Assumptions

1. **`metadata_database.csv` is the authoritative accepted-spectrum source** (per the task and the inventory). All accepted crosswalk rows derive their composite ID, source, and raw filename from it.
2. **`composite_spectrum_id` equals the cleaned parquet basename** (mineral prefix + raw stem + hash). This is what makes deterministic reproduction valid; it is strongly supported by the observed structure (the embedded raw stem matches `original_filename`, and re-parsing yields a key set identical in size to the normalized table).
3. **The normalization grouping is `(mineral_name, sample_name)`**, as implemented in `build_spectrum_metadata.py`. The crosswalk reproduces this grouping rather than inventing its own.
4. **Mineral resolution is exact**: every `mineral_name` in all four tables resolves to a `mineral_id` in `mineral_metadata.csv` (no orphans).
5. **The trailing hash in the composite ID is irrelevant to sample-name parsing** — both the composite ID and the cleaned filename satisfy the parser's `_[a-f0-9]+$` tail, and sample-name extraction does not depend on the hash value.

## 7. Limitations

1. **`MEDIUM` rows cannot be resolved to a single canonical survivor without the cleaned parquet files.** The crosswalk records that a composite belongs to a deduplication group and shares its normalized ID, but the original build kept the first file in directory-sort order — which cannot be reconstructed from committed metadata alone.
2. **The ambiguity is inherited from over-aggressive parsing in `build_spectrum_metadata.py`, not introduced here.** For USGS files the parser extracts a coarse token (e.g. `AV00`, `HS143.3B`) that is *not unique per sample*, so genuinely distinct samples were collapsed into one normalized record. The crosswalk surfaces this as `MEDIUM` rather than hiding it.
3. **No acquisition metadata is added** (`instrument`, `collection_date`, `grain_size`, `sample_origin`, `reference_source` remain unavailable — see the inventory). The crosswalk is a *linkage* artifact only.
4. **Rejected spectra have no composite/normalized IDs**; only their raw filename, source, and mineral are available.
5. **Authoritative verification requires the Google Drive `cleaned/` directory.** The deterministic match is exact against the repository, but a definitive composite↔normalized↔raw mapping (and survivor selection) should be confirmed against the actual cleaned filenames when access is available.

## 8. Examples of Ambiguous Mappings

### 8.1 USGS collapse — normalized ID `MUS082` (17 composites → 1 normalized ID)

Seventeen distinct Muscovite USGS measurements all parse to `sample_name = AV00` because the parser keys on the `s07_AV00_...` token rather than the true sample (`GDS107`, `GDS108`, `HS146.3B`, …). They are correctly all linked to `MUS082`, but they are *not* the same physical sample — hence `MEDIUM`:

| composite_spectrum_id | sample_name | normalized_spectrum_id |
|-----------------------|-------------|------------------------|
| `Muscovite_errorbars_for_s07_AV00_Muscovite_GDS107_BECKa_AREF_5b235e2a` | AV00 | MUS082 |
| `Muscovite_errorbars_for_s07_AV00_Muscovite_GDS108_BECKb_AREF_0cc37b40` | AV00 | MUS082 |
| `Muscovite_errorbars_for_s07_AV00_Muscovite_HS146.3B_BECKa_AREF_98c7f4fd` | AV00 | MUS082 |
| … (14 more) | AV00 | MUS082 |

This is the single largest collapse; `ZIR013` (14) and `BER026` (10) are analogous USGS cases.

### 8.2 Clean RELAB case — `HIGH`

RELAB filenames yield unique full-stem sample names, producing unambiguous 1:1 links:

| composite_spectrum_id | sample_name | normalized_spectrum_id | confidence |
|-----------------------|-------------|------------------------|------------|
| `Albite_bir1jb587_4633e90c` | bir1jb587 | ALB010 | HIGH |
| `Albite_bir1sr047_6427af6c` | bir1sr047 | ALB011 | HIGH |

### 8.3 Rejected — `UNMATCHED`

| original_filename | source | mineral_name | confidence |
|-------------------|--------|--------------|------------|
| `c1ja02a.tab` | relab | Calcite | UNMATCHED |
| `capp108.tab` | relab | Diopside | UNMATCHED |

## 9. Recommendations

1. **Use `HIGH` rows (1,211) as a trusted 1:1 crosswalk immediately.**
2. **Treat `MEDIUM` rows (592) as group memberships, not 1:1 links** until the cleaned parquet filenames are available to pick survivors.
3. **When Google Drive access is granted**, re-run against the `cleaned/` directory to (a) confirm the deterministic mapping, (b) resolve `MEDIUM` survivors, and (c) consider repairing the USGS sample-name parser so distinct samples are no longer collapsed.
4. **Regenerate** with `python build_lineage_crosswalk.py` whenever the source tables change; the script reads only committed data and writes only `metadata/lineage_crosswalk.csv`.

---

*Interim crosswalk built from repository contents only. No existing datasets were modified.*
