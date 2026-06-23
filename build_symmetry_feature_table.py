"""Build the GSUID-Safe Symmetry Feature Table.

Produces ``features/symmetry_feature_table.csv`` with one row per GSUID
containing crystallographic symmetry features derived from mineral structure
metadata.

Output schema (exact order):

    GSUID, spectrum_id, crystal_system, space_group,
    symmetry_rank, symmetry_index, symmetry_complexity_score

Data sources (repository-local only):
    metadata/spectrum_gsuid_map.csv       -> primary identity anchor (GSUID <-> spectrum_id)
    metadata/spectrum_metadata_table.csv  -> spectrum_id -> mineral_id mapping
    metadata/mineral_metadata.csv         -> mineral_id -> crystallographic properties
    metadata/metadata_database.csv        -> fallback validation only

Feature definitions:
    crystal_system       : categorical from mineral_metadata; "UNKNOWN" if missing
    space_group          : categorical from mineral_metadata; "UNKNOWN" if missing
    symmetry_rank        : ordinal 1-7 mapped from crystal_system; 0 if unknown
    symmetry_index       : symmetry_rank / 7  (range 0-1)
    symmetry_complexity_score : 1 - symmetry_index  (high = low symmetry = complex)

Scientific intent:
    Enable structure-spectrum relationship modelling, symbolic regression
    (PySR compatibility), and multimodal feature fusion with spectral features.
"""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "metadata"
FEATURES_DIR = BASE_DIR / "features"

GSUID_MAP = METADATA_DIR / "spectrum_gsuid_map.csv"
METADATA_TABLE = METADATA_DIR / "spectrum_metadata_table.csv"
MINERAL_METADATA = METADATA_DIR / "mineral_metadata.csv"
METADATA_DATABASE = METADATA_DIR / "metadata_database.csv"

OUTPUT = FEATURES_DIR / "symmetry_feature_table.csv"

SCHEMA = [
    "GSUID",
    "spectrum_id",
    "crystal_system",
    "space_group",
    "symmetry_rank",
    "symmetry_index",
    "symmetry_complexity_score",
]

CRYSTAL_SYSTEM_RANK = {
    "Triclinic": 1,
    "Monoclinic": 2,
    "Orthorhombic": 3,
    "Tetragonal": 4,
    "Trigonal": 5,
    "Hexagonal": 6,
    "Cubic": 7,
}


def main() -> None:
    errors: list[str] = []

    # --- STEP 1: Load GSUID map (primary identity anchor) ---
    gsuid_map = pd.read_csv(GSUID_MAP, dtype=str)
    print(f"Loaded GSUID map: {len(gsuid_map)} rows")

    assert gsuid_map["GSUID"].notna().all(), "GSUID map contains null GSUIDs"
    assert gsuid_map["GSUID"].is_unique, "GSUID map contains duplicate GSUIDs"

    # --- STEP 2: Load spectrum metadata table (spectrum_id -> mineral_id) ---
    meta_table = pd.read_csv(METADATA_TABLE, dtype=str)
    print(f"Loaded metadata table: {len(meta_table)} rows")

    # --- STEP 3: Load mineral metadata (mineral_id -> crystallography) ---
    mineral_meta = pd.read_csv(MINERAL_METADATA, dtype=str)
    print(f"Loaded mineral metadata: {len(mineral_meta)} rows")

    # --- STEP 4: Join pipeline ---
    # GSUID -> spectrum_id (already in gsuid_map)
    df = gsuid_map.copy()

    # spectrum_id -> mineral_id
    df = df.merge(
        meta_table[["spectrum_id", "mineral_id"]],
        on="spectrum_id",
        how="left",
    )

    # mineral_id -> crystal_system, space_group
    df = df.merge(
        mineral_meta[["mineral_id", "crystal_system", "space_group"]],
        on="mineral_id",
        how="left",
    )

    # --- STEP 5: Compute features ---
    df["crystal_system"] = df["crystal_system"].fillna("UNKNOWN")
    df["space_group"] = df["space_group"].fillna("UNKNOWN")

    df["symmetry_rank"] = df["crystal_system"].map(CRYSTAL_SYSTEM_RANK).fillna(0).astype(int)

    df["symmetry_index"] = df["symmetry_rank"] / 7.0

    df["symmetry_complexity_score"] = 1.0 - df["symmetry_index"]

    # --- STEP 6: Integrity checks ---
    duplicates = df[df["GSUID"].duplicated()]
    if len(duplicates) > 0:
        for _, dup in duplicates.iterrows():
            errors.append(f"ERROR: Duplicate GSUID found: {dup['GSUID']}")
        print(f"FATAL: {len(duplicates)} duplicate GSUIDs detected")
        for e in errors:
            print(e)
        sys.exit(1)

    assert len(df) == len(gsuid_map), (
        f"Row count mismatch: output={len(df)}, input={len(gsuid_map)}"
    )

    # --- STEP 7: Select and order columns, sort by GSUID ---
    result_df = df[SCHEMA].sort_values("GSUID", ascending=True).reset_index(drop=True)

    # --- STEP 8: Write output ---
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT, index=False)
    print(f"\nWrote {OUTPUT} ({len(result_df)} rows)")

    # --- STEP 9: Validation output ---
    print("\n" + "=" * 60)
    print("SYMMETRY FEATURE TABLE — VALIDATION")
    print("=" * 60)
    print(f"Total spectra processed: {len(result_df)}")
    print(f"Unique GSUID count: {result_df['GSUID'].nunique()}")
    print()

    print("Distribution of crystal systems:")
    dist = result_df["crystal_system"].value_counts()
    for system, count in dist.items():
        print(f"  {system}: {count}")
    print()

    unknown_count = (result_df["crystal_system"] == "UNKNOWN").sum()
    print(f"Count of UNKNOWN entries: {unknown_count}")
    print()

    print(f"symmetry_index  min: {result_df['symmetry_index'].min():.6f}")
    print(f"symmetry_index  max: {result_df['symmetry_index'].max():.6f}")
    print(f"symmetry_complexity_score  min: {result_df['symmetry_complexity_score'].min():.6f}")
    print(f"symmetry_complexity_score  max: {result_df['symmetry_complexity_score'].max():.6f}")

    # --- STEP 10: Quality assurance checks ---
    print("\n" + "-" * 60)
    print("QUALITY ASSURANCE CHECKS")
    print("-" * 60)

    assert result_df["GSUID"].is_unique, "Duplicate GSUIDs in output"
    print("[PASS] No duplicate GSUIDs")

    assert result_df["GSUID"].notna().all(), "Null GSUIDs in output"
    print("[PASS] No null GSUIDs")

    known_mask = result_df["crystal_system"] != "UNKNOWN"
    if known_mask.any():
        assert result_df.loc[known_mask, "symmetry_rank"].gt(0).all(), (
            "Known minerals have zero symmetry_rank"
        )
        print("[PASS] All known minerals have non-zero symmetry_rank")

    assert result_df["symmetry_index"].between(0, 1).all(), "symmetry_index out of [0,1]"
    print("[PASS] symmetry_index in [0, 1]")

    assert result_df["symmetry_complexity_score"].between(0, 1).all(), (
        "symmetry_complexity_score out of [0,1]"
    )
    print("[PASS] symmetry_complexity_score in [0, 1]")

    # Cross-check with processed_feature_table.csv GSUID alignment
    pft_path = FEATURES_DIR / "processed_feature_table.csv"
    if pft_path.exists():
        pft = pd.read_csv(pft_path, dtype=str, usecols=["GSUID"])
        sym_set = set(result_df["GSUID"])
        pft_set = set(pft["GSUID"])
        if sym_set == pft_set:
            print("[PASS] GSUIDs match processed_feature_table.csv exactly")
        else:
            only_sym = sym_set - pft_set
            only_pft = pft_set - sym_set
            print(f"[WARN] GSUID mismatch with processed_feature_table.csv: "
                  f"{len(only_sym)} only in symmetry, {len(only_pft)} only in processed")
    else:
        print("[INFO] processed_feature_table.csv not found — skipping cross-check")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
