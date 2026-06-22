"""Build the canonical Spectrum Metadata Table and GSUID mapping.

Constructs ``metadata/spectrum_metadata_table.csv`` from repository data only
(no Google Drive / external files):

    metadata/metadata_database.csv   -> authoritative accepted spectra (1,803 rows)
    metadata/spectrum_metadata.csv   -> normalized metadata (instrument, sample_name)
    metadata/mineral_metadata.csv    -> mineral dimension table (mineral_id)

Output schema (exact order):

    spectrum_id, GSUID, mineral_id, source, instrument, sample_name

Also generates ``metadata/spectrum_gsuid_map.csv`` containing the
``spectrum_id -> GSUID`` mapping for backward-compatible provenance.

The script never drops rows from ``metadata_database.csv`` and never modifies
the source files. It is fully reproducible: identical inputs yield identical
``spectrum_id`` and ``GSUID`` values.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from utils.gsuid import generate_gsuid

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "metadata"
REPORTS_DIR = BASE_DIR / "reports"

METADATA_DATABASE = METADATA_DIR / "metadata_database.csv"
SPECTRUM_METADATA = METADATA_DIR / "spectrum_metadata.csv"
MINERAL_METADATA = METADATA_DIR / "mineral_metadata.csv"

OUTPUT_TABLE = METADATA_DIR / "spectrum_metadata_table.csv"
OUTPUT_GSUID_MAP = METADATA_DIR / "spectrum_gsuid_map.csv"
OUTPUT_REPORT = REPORTS_DIR / "spectrum_metadata_table_report.md"

SCHEMA = ["spectrum_id", "GSUID", "mineral_id", "source", "instrument", "sample_name"]

SOURCE_NORMALIZATION = {
    "relab": "RELAB",
    "usgs": "USGS",
    "rruff": "RRUFF",
}

UNKNOWN_INSTRUMENT_VALUES = {"", "unknown", "nan", "none", "null"}


def normalize_source(value):
    """Normalize a raw source-library value to its canonical upper-case form."""
    if value is None:
        return None
    key = str(value).strip().lower()
    if key in ("", "nan", "none", "null"):
        return None
    return SOURCE_NORMALIZATION.get(key, str(value).strip().upper())


def strip_extension(filename):
    """Remove a trailing file extension (e.g. ``.tab``, ``.txt``, ``.parquet``)."""
    return os.path.splitext(str(filename))[0]


def standardize_underscores(text):
    """Collapse runs of underscores to a single one and trim leading/trailing ones."""
    text = re.sub(r"_+", "_", str(text))
    return text.strip("_")


def derive_sample_name_from_filename(filename, mineral_name):
    """Fallback sample name: strip extension and standardize underscores.

    Any leading ``<mineral_name>_`` prefix is removed first so the derived name
    refers to the sample rather than repeating the mineral.
    """
    base = strip_extension(filename)
    if mineral_name and base.startswith(f"{mineral_name}_"):
        base = base[len(mineral_name) + 1:]
    base = standardize_underscores(base)
    return base


def derive_join_sample_key(filename, mineral_name, source_library):
    """Derive the sample key used to link a database row to spectrum_metadata.

    This mirrors the sample-name extraction used to build
    ``spectrum_metadata.csv`` so rows can be matched per source family:
      * RELAB  -> filename without extension
      * RRUFF  -> the ``R#####`` sample id embedded in the filename
      * USGS   -> the catalog sample id (e.g. ``HS143.3B``, ``NMNHC5390``)
    Returns ``None`` when no key can be derived.
    """
    base = strip_extension(filename)
    if mineral_name and base.startswith(f"{mineral_name}_"):
        body = base[len(mineral_name) + 1:]
    else:
        body = base
    body = body.lstrip("_")

    src = (source_library or "").strip().lower()

    if src == "rruff":
        match = re.search(r"R\d+", body)
        if match:
            return match.group()
        parts = [p for p in body.split("_") if p]
        return parts[0] if parts else None

    if src == "usgs":
        parts = [p for p in body.split("_") if p]
        for index, part in enumerate(parts):
            if re.match(r"^[A-Z]{2}\d+\.?\d*[A-Z]*$", part) or re.match(r"^[A-Z]+\d+", part):
                return part
            if index > 0 and parts[index - 1] == mineral_name and re.search(r"\d", part):
                return part
        return body or None

    # RELAB and anything else: the filename base is the sample name.
    return strip_extension(filename) or None


def build_table():
    warnings = []
    notes = {"sample_fallback": 0, "no_sm_match": 0}

    database = pd.read_csv(METADATA_DATABASE, dtype=str).fillna("")
    spectrum_meta = pd.read_csv(SPECTRUM_METADATA, dtype=str).fillna("")
    mineral_meta = pd.read_csv(MINERAL_METADATA, dtype=str).fillna("")

    n_input = len(database)

    # --- 2. Mineral mapping --------------------------------------------------
    mineral_to_id = dict(zip(mineral_meta["mineral_name"], mineral_meta["mineral_id"]))

    def map_mineral_id(name):
        mineral_id = mineral_to_id.get(name)
        if mineral_id is None or str(mineral_id).strip() == "":
            warnings.append(f"mineral_name '{name}' not found in mineral_metadata.csv; mineral_id set to null")
            return None
        return int(mineral_id)

    database["mineral_id"] = database["mineral_name"].apply(map_mineral_id)

    # --- Build lookup from spectrum_metadata via (mineral_name, sample_name) --
    sm_lookup = {}
    for _, row in spectrum_meta.iterrows():
        sm_lookup[(row["mineral_name"], row["sample_name"])] = {
            "instrument": row.get("instrument", ""),
            "sample_name": row.get("sample_name", ""),
            "source": row.get("source", ""),
        }

    database["join_key"] = database.apply(
        lambda r: derive_join_sample_key(r["original_filename"], r["mineral_name"], r["source_library"]),
        axis=1,
    )

    def lookup_sm(row):
        return sm_lookup.get((row["mineral_name"], row["join_key"]))

    # --- 3. Source field -----------------------------------------------------
    def resolve_source(row):
        primary = normalize_source(row["source_library"])
        if primary is not None:
            return primary
        match = lookup_sm(row)
        if match is not None:
            fallback = normalize_source(match["source"])
            if fallback is not None:
                return fallback
        warnings.append(
            f"row '{row['spectrum_id']}' has no resolvable source; left as null"
        )
        return None

    database["source"] = database.apply(resolve_source, axis=1)

    # --- 4. Instrument field -------------------------------------------------
    def resolve_instrument(row):
        match = lookup_sm(row)
        candidates = []
        if match is not None:
            candidates.append(match["instrument"])
        candidates.append(row.get("instrument", ""))
        for candidate in candidates:
            value = str(candidate).strip()
            if value.lower() not in UNKNOWN_INSTRUMENT_VALUES:
                return value
        return "UNKNOWN"

    database["instrument"] = database.apply(resolve_instrument, axis=1)

    # --- 5. Sample name ------------------------------------------------------
    def resolve_sample_name(row):
        match = lookup_sm(row)
        if match is None:
            notes["no_sm_match"] += 1
        if match is not None:
            value = str(match["sample_name"]).strip()
            if value:
                return value
        notes["sample_fallback"] += 1
        derived = derive_sample_name_from_filename(row["original_filename"], row["mineral_name"])
        if derived:
            return derived
        return "UNKNOWN"

    database["sample_name"] = database.apply(resolve_sample_name, axis=1)

    # --- 6. spectrum_id generation ------------------------------------------
    # Sort by mineral_id -> source -> sample_name -> original_filename, then
    # assign sequential canonical IDs. Null mineral_id / source sort last.
    sort_frame = database.copy()
    sort_frame["_mineral_id_sort"] = sort_frame["mineral_id"].apply(
        lambda v: (1, 0) if v is None else (0, int(v))
    )
    sort_frame["_source_sort"] = sort_frame["source"].apply(
        lambda v: (1, "") if v is None else (0, v)
    )
    sort_frame = sort_frame.sort_values(
        by=["_mineral_id_sort", "_source_sort", "sample_name", "original_filename"],
        kind="mergesort",
    ).reset_index(drop=True)

    sort_frame["spectrum_id"] = [f"SPC-{i + 1:06d}" for i in range(len(sort_frame))]

    # --- 7. GSUID generation -------------------------------------------------
    sort_frame["GSUID"] = sort_frame.apply(
        lambda r: generate_gsuid(r["source_library"], r["original_filename"], r["mineral_name"]),
        axis=1,
    )

    result = sort_frame[SCHEMA].copy()
    gsuid_map = sort_frame[["spectrum_id", "GSUID"]].copy()

    return result, gsuid_map, n_input, warnings, notes


def print_validation(result, n_input):
    total = len(result)
    unique_minerals = result["mineral_id"].dropna().nunique()
    source_counts = result["source"].value_counts(dropna=False).to_dict()
    unknown_instruments = int((result["instrument"] == "UNKNOWN").sum())
    missing_mineral = int(result["mineral_id"].isna().sum())

    print("=" * 60)
    print("SPECTRUM METADATA TABLE — VALIDATION")
    print("=" * 60)
    print(f"Total rows: {total}")
    print(f"Unique minerals: {unique_minerals}")
    print("Source distribution:")
    for label in ("RELAB", "USGS", "RRUFF"):
        print(f"  {label}: {source_counts.get(label, 0)}")
    other = {k: v for k, v in source_counts.items() if k not in ("RELAB", "USGS", "RRUFF")}
    for k, v in other.items():
        print(f"  {k}: {v}")
    print(f"UNKNOWN instruments: {unknown_instruments}")
    print(f"Missing mineral_id values: {missing_mineral}")
    print("-" * 60)

    # Quality checks
    assert total == n_input, f"row count changed: {total} != {n_input} (rows must never be dropped)"
    assert result["spectrum_id"].is_unique, "duplicate spectrum_id values detected"
    expected_ids = [f"SPC-{i + 1:06d}" for i in range(total)]
    assert list(result["spectrum_id"]) == expected_ids, "spectrum_id values are not sequential"
    print("Quality checks passed: no dropped rows, unique & sequential spectrum_id.")

    # GSUID validation
    total_gsuids = result["GSUID"].notna().sum()
    unique_gsuids = result["GSUID"].nunique()
    collisions = total_gsuids - unique_gsuids
    missing_gsuids = int(result["GSUID"].isna().sum())

    print()
    print("=" * 60)
    print("GSUID VALIDATION")
    print("=" * 60)
    print(f"Total GSUIDs generated: {total_gsuids}")
    print(f"Unique GSUIDs: {unique_gsuids}")
    print(f"Collisions: {collisions}")
    print(f"Missing GSUIDs: {missing_gsuids}")
    print("-" * 60)

    assert collisions == 0, f"GSUID collisions detected: {collisions}"
    assert missing_gsuids == 0, f"Missing GSUID values: {missing_gsuids}"
    assert unique_gsuids == total, f"Unique GSUIDs ({unique_gsuids}) != row count ({total})"
    print("GSUID quality checks passed: unique, complete, zero collisions.")

    print()
    print("Sample GSUID mappings (first 10):")
    for _, row in result[["spectrum_id", "GSUID"]].head(10).iterrows():
        print(f"  {row['spectrum_id']} -> {row['GSUID']}")

    return {
        "total": total,
        "unique_minerals": unique_minerals,
        "source_counts": source_counts,
        "unknown_instruments": unknown_instruments,
        "missing_mineral": missing_mineral,
    }


def write_report(stats, warnings, notes, n_input):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    source_counts = stats["source_counts"]
    lines = []
    lines.append("# Spectrum Metadata Table Report")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "The canonical table `metadata/spectrum_metadata_table.csv` is derived "
        "exclusively from repository data (no Google Drive or external files). "
        "`metadata/metadata_database.csv` is the authoritative base: every one of "
        f"its {n_input} accepted-spectrum rows is preserved (no rows dropped)."
    )
    lines.append("")
    lines.append("Output schema (exact order): `spectrum_id, mineral_id, source, instrument, sample_name`.")
    lines.append("")
    lines.append("## Join strategy")
    lines.append("")
    lines.append("- **mineral_id**: `metadata_database.mineral_name` -> `mineral_metadata.mineral_name` -> `mineral_id`. Unmapped names are left null and logged.")
    lines.append("- **source**: priority `metadata_database.source_library`, fallback `spectrum_metadata.source`; normalized `relab->RELAB`, `usgs->USGS`, `rruff->RRUFF`.")
    lines.append("- **instrument**: priority `spectrum_metadata.instrument`, fallback `metadata_database.instrument`; unknown/empty -> `UNKNOWN`.")
    lines.append("- **sample_name**: priority `spectrum_metadata.sample_name`, fallback derived from `metadata_database.original_filename` (extension removed, underscores standardized); empty -> `UNKNOWN`.")
    lines.append("")
    lines.append(
        "Because `spectrum_metadata.csv` uses extracted sample identifiers, each "
        "database row is linked to it by deriving a per-source sample key from "
        "`original_filename` (RELAB: filename stem; RRUFF: embedded `R#####` id; "
        "USGS: catalog id such as `HS143.3B`) and matching on "
        "`(mineral_name, sample_key)`."
    )
    lines.append("")
    lines.append("## spectrum_id generation")
    lines.append("")
    lines.append(
        "Rows are sorted by `mineral_id -> source -> sample_name -> original_filename` "
        "and then assigned sequential canonical IDs `SPC-000001, SPC-000002, ...`. "
        "Existing IDs are never reused. The ordering is deterministic, so identical "
        "inputs always yield identical IDs."
    )
    lines.append("")
    lines.append("## Missing data summary")
    lines.append("")
    lines.append(f"- Total rows: {stats['total']}")
    lines.append(f"- Unique minerals: {stats['unique_minerals']}")
    lines.append(f"- RELAB / USGS / RRUFF: {source_counts.get('RELAB', 0)} / {source_counts.get('USGS', 0)} / {source_counts.get('RRUFF', 0)}")
    lines.append(f"- UNKNOWN instruments: {stats['unknown_instruments']}")
    lines.append(f"- Missing mineral_id values: {stats['missing_mineral']}")
    lines.append("")
    lines.append("## Inconsistencies found")
    lines.append("")
    lines.append(
        f"- {notes['no_sm_match']} database row(s) had no matching record in "
        "`spectrum_metadata.csv`; their `instrument` defaults to `UNKNOWN` and "
        "`sample_name` is derived from `original_filename`. These are RRUFF "
        "`X#####` Raman acquisitions that are absent from the normalized metadata."
    )
    lines.append(
        f"- {notes['sample_fallback']} row(s) used the filename-derived "
        "`sample_name` fallback."
    )
    if warnings:
        unique_warnings = sorted(set(warnings))
        lines.append(f"- {len(warnings)} warning(s) emitted ({len(unique_warnings)} unique):")
        for warning in unique_warnings[:50]:
            lines.append(f"  - {warning}")
        if len(unique_warnings) > 50:
            lines.append(f"  - ... and {len(unique_warnings) - 50} more")
    else:
        lines.append("- No mineral_id or source resolution failures; no rows were dropped.")
    lines.append("")
    OUTPUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    result, gsuid_map, n_input, warnings, notes = build_table()
    result.to_csv(OUTPUT_TABLE, index=False)
    print(f"Wrote {OUTPUT_TABLE} ({len(result)} rows)")
    gsuid_map.to_csv(OUTPUT_GSUID_MAP, index=False)
    print(f"Wrote {OUTPUT_GSUID_MAP} ({len(gsuid_map)} rows)")
    stats = print_validation(result, n_input)
    write_report(stats, warnings, notes, n_input)
    print(f"Wrote {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
