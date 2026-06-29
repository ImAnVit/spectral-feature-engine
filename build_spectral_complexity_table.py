"""Build the GSUID-Safe Spectral Complexity Feature Table.

Produces ``features/spectral_complexity_table.csv`` with one row per GSUID
combining processed spectral features and crystallographic symmetry complexity.

Output schema (exact order):

    GSUID, spectrum_id, spectral_entropy, peak_density, fractal_complexity,
    variance_stability, symmetry_complexity_score, cross_modal_complexity,
    overall_complexity_index

Data sources (repository-local only):
    features/processed_feature_table.csv
    features/symmetry_feature_table.csv
    metadata/spectrum_gsuid_map.csv
    metadata/spectrum_metadata_table.csv

Peak density uses the standard interpolated spectrum length (2101 points),
matching the signal length used when computing processed features.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "metadata"
FEATURES_DIR = BASE_DIR / "features"

PROCESSED_TABLE = FEATURES_DIR / "processed_feature_table.csv"
SYMMETRY_TABLE = FEATURES_DIR / "symmetry_feature_table.csv"
GSUID_MAP = METADATA_DIR / "spectrum_gsuid_map.csv"
METADATA_TABLE = METADATA_DIR / "spectrum_metadata_table.csv"

OUTPUT = FEATURES_DIR / "spectral_complexity_table.csv"

EXPECTED_ROWS = 1803

SCHEMA = [
    "GSUID",
    "spectrum_id",
    "spectral_entropy",
    "peak_density",
    "fractal_complexity",
    "variance_stability",
    "symmetry_complexity_score",
    "cross_modal_complexity",
    "overall_complexity_index",
]

SIGNAL_LENGTH = 2101


def minmax_normalize(series: pd.Series) -> pd.Series:
    """Scale values to [0, 1] using dataset min-max bounds."""
    lo = series.min()
    hi = series.max()
    if hi == lo:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)


def impute_numeric_median(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Fill missing numeric values with column medians."""
    out = df.copy()
    for col in columns:
        if out[col].isna().any():
            out[col] = out[col].fillna(out[col].median())
    return out


def validate_gsuid_integrity(
    df: pd.DataFrame,
    reference_gsuids: set[str],
    label: str,
) -> None:
    """Abort with explicit missing GSUID report on mismatch."""
    output_gsuids = set(df["GSUID"])
    missing = reference_gsuids - output_gsuids
    extra = output_gsuids - reference_gsuids
    duplicates = int(df["GSUID"].duplicated().sum())

    if len(df) != EXPECTED_ROWS or missing or extra or duplicates:
        print(f"FATAL: GSUID integrity failure at {label}")
        print(f"  Expected rows: {EXPECTED_ROWS}, got: {len(df)}")
        print(f"  Duplicate GSUIDs: {duplicates}")
        if missing:
            print(f"  Missing GSUIDs ({len(missing)}):")
            for gsuid in sorted(missing)[:20]:
                print(f"    {gsuid}")
            if len(missing) > 20:
                print(f"    ... and {len(missing) - 20} more")
        if extra:
            print(f"  Unexpected GSUIDs ({len(extra)}):")
            for gsuid in sorted(extra)[:20]:
                print(f"    {gsuid}")
        sys.exit(1)


def print_histogram(series: pd.Series, bins: int = 10) -> None:
    """Print a simple text histogram for distribution summary."""
    counts, edges = np.histogram(series.dropna(), bins=bins)
    print(f"  Histogram ({bins} bins):")
    for i, count in enumerate(counts):
        left = edges[i]
        right = edges[i + 1]
        bar = "#" * int(count / max(counts.max(), 1) * 40)
        print(f"    [{left:.4f}, {right:.4f}): {count:4d} {bar}")


def main() -> None:
    # --- Load required inputs ---
    processed = pd.read_csv(PROCESSED_TABLE, dtype={"GSUID": str, "spectrum_id": str})
    symmetry = pd.read_csv(SYMMETRY_TABLE, dtype={"GSUID": str, "spectrum_id": str})
    gsuid_map = pd.read_csv(GSUID_MAP, dtype={"GSUID": str, "spectrum_id": str})
    meta_table = pd.read_csv(METADATA_TABLE, dtype={"GSUID": str, "spectrum_id": str})

    print(f"Loaded processed feature table: {len(processed)} rows")
    print(f"Loaded symmetry feature table: {len(symmetry)} rows")
    print(f"Loaded GSUID map: {len(gsuid_map)} rows")
    print(f"Loaded metadata table: {len(meta_table)} rows")

    reference_gsuids = set(gsuid_map["GSUID"])

    # --- Pre-join integrity checks ---
    for name, table in [
        ("processed_feature_table", processed),
        ("symmetry_feature_table", symmetry),
        ("spectrum_gsuid_map", gsuid_map),
        ("spectrum_metadata_table", meta_table),
    ]:
        if table["GSUID"].isna().any():
            print(f"FATAL: null GSUIDs in {name}")
            sys.exit(1)
        dup_count = int(table["GSUID"].duplicated().sum())
        if dup_count:
            print(f"FATAL: {dup_count} duplicate GSUIDs in {name}")
            sys.exit(1)

    # --- Step 1: inner join processed <-> symmetry on GSUID ---
    merged = processed.merge(
        symmetry[["GSUID", "symmetry_complexity_score"]],
        on="GSUID",
        how="inner",
        validate="one_to_one",
    )

    if len(merged) != EXPECTED_ROWS:
        proc_gsuids = set(processed["GSUID"])
        sym_gsuids = set(symmetry["GSUID"])
        missing_in_sym = proc_gsuids - sym_gsuids
        missing_in_proc = sym_gsuids - proc_gsuids
        print(
            f"FATAL: processed/symmetry join mismatch: "
            f"{len(merged)} rows (expected {EXPECTED_ROWS})"
        )
        if missing_in_sym:
            print(f"  GSUIDs in processed but not symmetry: {len(missing_in_sym)}")
            for gsuid in sorted(missing_in_sym)[:20]:
                print(f"    {gsuid}")
        if missing_in_proc:
            print(f"  GSUIDs in symmetry but not processed: {len(missing_in_proc)}")
            for gsuid in sorted(missing_in_proc)[:20]:
                print(f"    {gsuid}")
        sys.exit(1)

    print(f"Inner join processed <-> symmetry: {len(merged)} rows (exact match)")

    # --- spectrum_id from processed table (GSUID-aligned) ---
    df = merged[["GSUID", "spectrum_id"]].copy()

    # --- Impute upstream numeric gaps before derivation ---
    numeric_source_cols = [
        "entropy",
        "peak_count",
        "fractal_dimension",
        "spectral_variance",
        "symmetry_complexity_score",
    ]
    merged = impute_numeric_median(merged, numeric_source_cols)

    # --- 4.1 spectral_entropy (rename only) ---
    df["spectral_entropy"] = merged["entropy"]

    # --- 4.2 peak_density ---
    # Allowed metadata sources lack per-spectrum num_points; use pipeline standard
    # interpolated length (2101), consistent with processed feature extraction.
    normalized_length = float(SIGNAL_LENGTH)
    df["peak_density"] = merged["peak_count"] / normalized_length

    # --- 4.3 fractal_complexity ---
    df["fractal_complexity"] = (merged["fractal_dimension"] - 1.0).clip(lower=0.0, upper=1.0)

    # --- 4.4 variance_stability ---
    df["variance_stability"] = 1.0 / (1.0 + np.log1p(merged["spectral_variance"]))

    # --- 4.5 symmetry_complexity_score (direct reuse) ---
    df["symmetry_complexity_score"] = merged["symmetry_complexity_score"]

    # --- Impute any remaining numeric gaps (median) ---
    derived_numeric_cols = [
        "spectral_entropy",
        "peak_density",
        "fractal_complexity",
        "variance_stability",
        "symmetry_complexity_score",
    ]
    df = impute_numeric_median(df, derived_numeric_cols)

    # --- 4.6 cross_modal_complexity ---
    cross_raw = (
        df["spectral_entropy"] * df["symmetry_complexity_score"]
        + df["fractal_complexity"]
    )
    cross_raw = cross_raw.fillna(0.0)
    df["cross_modal_complexity"] = minmax_normalize(cross_raw)

    # --- 4.7 overall_complexity_index ---
    overall_raw = (
        0.35 * df["spectral_entropy"]
        + 0.25 * df["fractal_complexity"]
        + 0.20 * df["symmetry_complexity_score"]
        + 0.20 * df["variance_stability"]
    )
    overall_raw = overall_raw.fillna(0.0)
    df["overall_complexity_index"] = minmax_normalize(overall_raw)

    # --- Final imputation for derived components (0 for any residual gaps) ---
    for col in ["cross_modal_complexity", "overall_complexity_index"]:
        df[col] = df[col].fillna(0.0)

    # --- Sort deterministically ---
    df = df.sort_values("GSUID", ascending=True).reset_index(drop=True)

    # --- GSUID integrity rule ---
    validate_gsuid_integrity(df, reference_gsuids, "final output")

    assert df["GSUID"].notna().all(), "Output contains null GSUIDs"
    assert df["GSUID"].is_unique, "Output contains duplicate GSUIDs"
    assert len(df) == EXPECTED_ROWS, f"Row count {len(df)} != {EXPECTED_ROWS}"

    # --- Write output ---
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    df[SCHEMA].to_csv(OUTPUT, index=False)
    print(f"\nWrote {OUTPUT} ({len(df)} rows)")

    # --- Validation output ---
    print("\n" + "=" * 60)
    print("SPECTRAL COMPLEXITY TABLE - VALIDATION")
    print("=" * 60)

    print("\nIdentity checks")
    print(f"  Total GSUID count: {df['GSUID'].nunique()}")
    print(f"  Duplicate GSUID check: {int(df['GSUID'].duplicated().sum())} (must be 0)")

    validation_features = [
        "spectral_entropy",
        "fractal_complexity",
        "variance_stability",
        "cross_modal_complexity",
        "overall_complexity_index",
    ]

    print("\nFeature validation (min / max)")
    for col in validation_features:
        print(f"  {col}: {df[col].min():.6f} / {df[col].max():.6f}")

    print("\nDistribution summary (mean / std)")
    for col in validation_features + ["peak_density", "symmetry_complexity_score"]:
        print(f"  {col}: mean={df[col].mean():.6f}, std={df[col].std():.6f}")

    print("\nHistogram bins (overall_complexity_index)")
    print_histogram(df["overall_complexity_index"])

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
