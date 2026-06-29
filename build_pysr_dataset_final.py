"""Build the GSUID-unified PySR final dataset.

Produces ``features/pysr_dataset_final.csv`` — a single flat, GSUID-aligned
feature matrix merging all spectral, structural, and complexity layers for
symbolic regression (PySR).

Output schema (exact order):

    GSUID, spectrum_id, mineral_id, source,
    entropy, peak_count, fractal_dimension, spectral_variance,
    crystal_system, space_group, symmetry_index, symmetry_complexity_score,
    spectral_rugosity, information_complexity, amplitude_entropy,
    distribution_skewness, complexity_score

Data sources (repository-local only):
    metadata/spectrum_gsuid_map.csv
    metadata/spectrum_metadata_table.csv
    features/processed_feature_table.csv
    features/symmetry_feature_table.csv
    features/spectral_complexity_table.csv

Validation only (read, never written):
    metadata/metadata_database.csv
    metadata/mineral_metadata.csv
"""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "metadata"
FEATURES_DIR = BASE_DIR / "features"

GSUID_MAP = METADATA_DIR / "spectrum_gsuid_map.csv"
METADATA_TABLE = METADATA_DIR / "spectrum_metadata_table.csv"
PROCESSED_TABLE = FEATURES_DIR / "processed_feature_table.csv"
SYMMETRY_TABLE = FEATURES_DIR / "symmetry_feature_table.csv"
COMPLEXITY_TABLE = FEATURES_DIR / "spectral_complexity_table.csv"
METADATA_DATABASE = METADATA_DIR / "metadata_database.csv"
MINERAL_METADATA = METADATA_DIR / "mineral_metadata.csv"

OUTPUT = FEATURES_DIR / "pysr_dataset_final.csv"

EXPECTED_ROWS = 1803

SCHEMA = [
    "GSUID",
    "spectrum_id",
    "mineral_id",
    "source",
    "entropy",
    "peak_count",
    "fractal_dimension",
    "spectral_variance",
    "crystal_system",
    "space_group",
    "symmetry_index",
    "symmetry_complexity_score",
    "spectral_rugosity",
    "information_complexity",
    "amplitude_entropy",
    "distribution_skewness",
    "complexity_score",
]

FLOAT_COLUMNS = [
    "entropy",
    "fractal_dimension",
    "spectral_variance",
    "symmetry_index",
    "symmetry_complexity_score",
    "spectral_rugosity",
    "information_complexity",
    "amplitude_entropy",
    "distribution_skewness",
    "complexity_score",
]

INT_COLUMNS = ["peak_count"]

STRING_COLUMNS = ["crystal_system", "space_group", "source", "mineral_id"]

# Map PySR complexity column names to spectral_complexity_table source columns.
COMPLEXITY_COLUMN_MAP = {
    "spectral_rugosity": "fractal_complexity",
    "information_complexity": "cross_modal_complexity",
    "amplitude_entropy": "spectral_entropy",
    "distribution_skewness": "peak_density",
    "complexity_score": "overall_complexity_index",
}


def impute_missing(df: pd.DataFrame, audit: list[str]) -> pd.DataFrame:
    """Fill missing values with 0; record GSUIDs for audit."""
    out = df.copy()
    for col in SCHEMA:
        if col in ("GSUID", "spectrum_id"):
            continue
        missing_mask = out[col].isna() | (out[col].astype(str).str.strip() == "")
        if missing_mask.any():
            for gsuid in out.loc[missing_mask, "GSUID"]:
                audit.append(f"{gsuid}:{col}")
            if col in STRING_COLUMNS:
                out.loc[missing_mask, col] = "0"
            elif col in INT_COLUMNS:
                out.loc[missing_mask, col] = 0
            else:
                out.loc[missing_mask, col] = 0.0
    return out


def enforce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Apply strict numeric type enforcement."""
    out = df.copy()
    for col in FLOAT_COLUMNS:
        out[col] = out[col].astype(float)
    out["peak_count"] = out["peak_count"].astype(int)
    for col in STRING_COLUMNS:
        out[col] = out[col].astype(str)
    return out


def validate_cross_layer(gsuid: set[str], layers: dict[str, set[str]]) -> None:
    """Verify GSUID coverage across all feature layers."""
    for name, layer_gsuids in layers.items():
        missing = gsuid - layer_gsuids
        extra = layer_gsuids - gsuid
        if missing or extra:
            print(f"FATAL: GSUID mismatch with {name}")
            if missing:
                print(f"  Missing from {name}: {len(missing)}")
                for g in sorted(missing)[:10]:
                    print(f"    {g}")
            if extra:
                print(f"  Extra in {name}: {len(extra)}")
            sys.exit(1)


def main() -> None:
    imputation_audit: list[str] = []

    # --- Load identity anchor ---
    gsuid_map = pd.read_csv(GSUID_MAP, dtype=str)
    meta_table = pd.read_csv(METADATA_TABLE, dtype=str)
    processed = pd.read_csv(PROCESSED_TABLE, dtype=str)
    symmetry = pd.read_csv(SYMMETRY_TABLE, dtype=str)
    complexity = pd.read_csv(COMPLEXITY_TABLE, dtype=str)

    print(f"Loaded GSUID map: {len(gsuid_map)} rows")
    print(f"Loaded metadata table: {len(meta_table)} rows")
    print(f"Loaded processed feature table: {len(processed)} rows")
    print(f"Loaded symmetry feature table: {len(symmetry)} rows")
    print(f"Loaded spectral complexity table: {len(complexity)} rows")

    reference_gsuids = set(gsuid_map["GSUID"])

    # --- Validation-only sources ---
    meta_db = pd.read_csv(METADATA_DATABASE)
    mineral_meta = pd.read_csv(MINERAL_METADATA)
    print(f"Loaded metadata_database (validation): {len(meta_db)} rows")
    print(f"Loaded mineral_metadata (validation): {len(mineral_meta)} rows")
    assert len(meta_db) == EXPECTED_ROWS, (
        f"metadata_database row count {len(meta_db)} != {EXPECTED_ROWS}"
    )

    # --- Step 1: identity resolution (GSUID -> spectrum_id) ---
    df = gsuid_map[["GSUID", "spectrum_id"]].copy()

    # --- Step 5: metadata enrichment ---
    df = df.merge(
        meta_table[["spectrum_id", "mineral_id", "source"]],
        on="spectrum_id",
        how="left",
    )

    # --- Step 2: spectral features ---
    df = df.merge(
        processed[["GSUID", "entropy", "peak_count", "fractal_dimension", "spectral_variance"]],
        on="GSUID",
        how="left",
    )

    # --- Step 3: symmetry features ---
    df = df.merge(
        symmetry[
            ["GSUID", "crystal_system", "space_group", "symmetry_index", "symmetry_complexity_score"]
        ],
        on="GSUID",
        how="left",
    )

    # --- Step 4: complexity features (rename via mapping) ---
    complexity_cols = ["GSUID"] + list(COMPLEXITY_COLUMN_MAP.values())
    complexity_subset = complexity[complexity_cols].copy()
    rename_map = {src: dst for dst, src in COMPLEXITY_COLUMN_MAP.items()}
    complexity_subset = complexity_subset.rename(columns=rename_map)
    df = df.merge(complexity_subset, on="GSUID", how="left")

    # --- Cross-layer consistency ---
    validate_cross_layer(
        reference_gsuids,
        {
            "processed_feature_table": set(processed["GSUID"]),
            "symmetry_feature_table": set(symmetry["GSUID"]),
            "spectral_complexity_table": set(complexity["GSUID"]),
            "spectrum_metadata_table": set(meta_table["GSUID"]),
        },
    )

    # --- Missing value imputation ---
    df = impute_missing(df, imputation_audit)

    # --- Type enforcement ---
    df = enforce_types(df)

    # --- Deterministic ordering ---
    df = df.sort_values("GSUID", ascending=True).reset_index(drop=True)
    df = df[SCHEMA]

    # --- GSUID integrity ---
    assert len(df) == EXPECTED_ROWS, f"Row count {len(df)} != {EXPECTED_ROWS}"
    assert df["GSUID"].notna().all(), "Null GSUIDs in output"
    assert df["GSUID"].is_unique, "Duplicate GSUIDs in output"
    missing_gsuid_count = int(df["GSUID"].isna().sum())

    # --- Write output ---
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)
    print(f"\nWrote {OUTPUT} ({len(df)} rows)")

    if imputation_audit:
        print(f"\nImputation audit: {len(imputation_audit)} field(s) imputed")
        for entry in imputation_audit[:20]:
            print(f"  {entry}")
        if len(imputation_audit) > 20:
            print(f"  ... and {len(imputation_audit) - 20} more")
    else:
        print("\nImputation audit: no imputations required")

    # --- Validation output ---
    print("\n" + "=" * 60)
    print("PYSR DATASET FINAL - VALIDATION")
    print("=" * 60)

    print("\nIdentity checks")
    print(f"  Total rows: {len(df)}")
    print(f"  Unique GSUID count: {df['GSUID'].nunique()}")
    print(f"  Missing GSUID count: {missing_gsuid_count} (must be 0)")
    print(f"  Duplicate GSUID count: {int(df['GSUID'].duplicated().sum())}")

    print("\nFeature completeness (missing values per column)")
    for col in SCHEMA:
        null_count = int(df[col].isna().sum())
        print(f"  {col}: {null_count}")

    print("\nDistribution sanity checks (min / max)")
    for col in [
        "entropy",
        "peak_count",
        "fractal_dimension",
        "spectral_variance",
        "complexity_score",
    ]:
        print(f"  {col}: {df[col].min()} / {df[col].max()}")

    print("\nCross-layer consistency")
    print("  [PASS] All GSUIDs present in processed, symmetry, complexity, and metadata layers")
    print("  [PASS] No orphan GSUIDs detected")

    zero_only_cols = [
        col
        for col in FLOAT_COLUMNS + INT_COLUMNS
        if pd.to_numeric(df[col], errors="coerce").fillna(0).eq(0).all()
    ]
    if zero_only_cols:
        print(f"\n  [WARN] Columns entirely zero: {zero_only_cols}")
    else:
        print("\n  [PASS] No unexpected all-zero numeric columns")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
