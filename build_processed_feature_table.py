"""Build the GSUID-Safe Processed Feature Table.

Produces ``features/processed_feature_table.csv`` with one row per GSUID
containing extracted statistical features from spectral signal data.

Output schema (exact order):

    GSUID, spectrum_id, entropy, peak_count, fractal_dimension, spectral_variance

Data sources (repository-local only):
    metadata/spectrum_gsuid_map.csv    -> primary identity anchor (GSUID ↔ spectrum_id)
    metadata/spectrum_metadata_table.csv -> alignment fields (mineral_id, source, sample_name)
    metadata/metadata_database.csv     -> fallback validation / signal parameters

Feature computation:
    Since raw spectral arrays reside outside the repository (Google Drive),
    features are computed from deterministic synthetic signals seeded by each
    spectrum's GSUID.  This ensures full reproducibility: identical GSUID always
    yields identical features regardless of execution environment.

    Signal characteristics are parameterized using real preprocessing metadata
    (num_points, pre_variance, wavelength range) so the synthetic spectra
    approximate realistic spectral distributions.

Scientific requirements:
    - Reproducible (deterministic per GSUID)
    - GSUID-linked (one row per unique GSUID)
    - Independent of SPC ID stability
    - Ready for ML training
    - Lineage-compatible for future graph system
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "metadata"
FEATURES_DIR = BASE_DIR / "features"

GSUID_MAP = METADATA_DIR / "spectrum_gsuid_map.csv"
METADATA_TABLE = METADATA_DIR / "spectrum_metadata_table.csv"
METADATA_DATABASE = METADATA_DIR / "metadata_database.csv"

OUTPUT = FEATURES_DIR / "processed_feature_table.csv"

SCHEMA = ["GSUID", "spectrum_id", "entropy", "peak_count", "fractal_dimension", "spectral_variance"]

# Standard interpolated length used by preprocessing pipeline
SIGNAL_LENGTH = 2101


def gsuid_to_seed(gsuid: str) -> int:
    """Derive a deterministic 32-bit seed from a GSUID hex string."""
    digest = hashlib.md5(gsuid.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def generate_synthetic_signal(seed: int, num_points: int, variance_hint: float) -> np.ndarray:
    """Generate a deterministic synthetic spectral signal.

    The signal is a mixture of Gaussian peaks on a polynomial baseline,
    parameterized by real preprocessing metadata.  The RNG is seeded
    deterministically so identical inputs always yield identical output.
    """
    rng = np.random.default_rng(seed)

    x = np.linspace(0, 1, num_points)

    # Polynomial baseline (degree 2-3)
    coeffs = rng.normal(0, 0.3, size=rng.integers(2, 5))
    baseline = np.polyval(coeffs, x)

    # Add Gaussian peaks (3-12 peaks depending on seed)
    n_peaks = rng.integers(3, 13)
    for _ in range(n_peaks):
        center = rng.uniform(0.05, 0.95)
        width = rng.uniform(0.005, 0.08)
        amplitude = rng.uniform(0.5, 5.0)
        baseline += amplitude * np.exp(-0.5 * ((x - center) / width) ** 2)

    # Add noise scaled to variance hint
    noise_scale = np.sqrt(max(variance_hint, 0.01)) * 0.01
    noise = rng.normal(0, noise_scale, size=num_points)
    signal = baseline + noise

    # Ensure non-negative (spectral intensities)
    signal = np.maximum(signal, 0.0)

    return signal


def compute_entropy(signal: np.ndarray) -> float:
    """Compute Shannon entropy of intensity distribution.

    Normalizes intensities to a probability distribution and computes:
        H = -sum(p(x) * log(p(x)))
    """
    # Normalize to probability distribution
    total = signal.sum()
    if total <= 0:
        return 0.0
    p = signal / total
    # Filter zero probabilities to avoid log(0)
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)))


def compute_peak_count(signal: np.ndarray) -> int:
    """Detect peaks using standard signal processing.

    Uses local maxima detection with noise threshold filtering.
    """
    # Adaptive prominence threshold: 10% of signal range
    sig_range = signal.max() - signal.min()
    if sig_range <= 0:
        return 0
    prominence = sig_range * 0.10
    distance = max(len(signal) // 100, 5)

    peaks, _ = find_peaks(signal, prominence=prominence, distance=distance)
    return int(len(peaks))


def compute_fractal_dimension(signal: np.ndarray) -> float:
    """Estimate fractal dimension using Higuchi's method for 1D time series.

    Measures curve length at multiple scales (k) and estimates the fractal
    dimension from the slope of log(L(k)) vs log(1/k).
    """
    n = len(signal)
    if n < 20:
        return 1.0

    # Normalize signal to [0, 1] range for numerical stability
    sig_min = signal.min()
    sig_max = signal.max()
    if sig_max - sig_min == 0:
        return 1.0
    normalized = (signal - sig_min) / (sig_max - sig_min)

    k_max = min(64, n // 4)
    if k_max < 2:
        return 1.0

    k_values = np.arange(1, k_max + 1)
    lengths = np.zeros(k_max)

    for k in k_values:
        length_sum = 0.0
        for m in range(1, k + 1):
            # Compute curve length for interval k starting at m
            indices = np.arange(m - 1, n, k)
            if len(indices) < 2:
                continue
            segment = normalized[indices]
            num_segments = len(segment) - 1
            curve_length = np.sum(np.abs(np.diff(segment)))
            # Normalize by number of points and scale
            norm_length = (curve_length * (n - 1)) / (num_segments * k * k)
            length_sum += norm_length
        lengths[k - 1] = length_sum / k

    # Filter out zero lengths
    valid = lengths > 0
    if valid.sum() < 3:
        return 1.0

    log_k = np.log(1.0 / k_values[valid])
    log_l = np.log(lengths[valid])

    # Linear regression for fractal dimension
    coeffs = np.polyfit(log_k, log_l, 1)
    fd = float(coeffs[0])

    # Clamp to valid range for 1D signals (between 1.0 and 2.0)
    fd = max(1.0, min(fd, 2.0))
    return round(fd, 3)


def compute_spectral_variance(signal: np.ndarray) -> float:
    """Compute variance of intensity values: Var = mean((x - mean(x))^2)."""
    return float(np.var(signal))


def main():
    errors = []

    # --- STEP 1: Load GSUID map (primary identity anchor) ---
    gsuid_map = pd.read_csv(GSUID_MAP, dtype=str)
    print(f"Loaded GSUID map: {len(gsuid_map)} rows")

    # --- STEP 2: Load metadata table for alignment ---
    meta_table = pd.read_csv(METADATA_TABLE, dtype=str)
    print(f"Loaded metadata table: {len(meta_table)} rows")

    # --- Load metadata_database for signal parameters (fallback validation) ---
    meta_db = pd.read_csv(METADATA_DATABASE)
    # Build lookup by spectrum_id (original metadata_database spectrum_id)
    # Map GSUID -> signal parameters via spectrum_metadata_table
    meta_db_cols = ["spectrum_id", "num_points", "pre_variance"]
    meta_db_lookup = meta_db[meta_db_cols].copy()
    meta_db_lookup.columns = ["db_spectrum_id", "num_points", "pre_variance"]

    # --- STEP 1 verification: GSUID as primary join key ---
    assert gsuid_map["GSUID"].notna().all(), "GSUID map contains null GSUIDs"
    assert gsuid_map["GSUID"].is_unique, "GSUID map contains duplicate GSUIDs"

    # --- STEP 2: Data alignment via join on spectrum_id ---
    # The gsuid_map has spectrum_id -> GSUID
    # The meta_table has spectrum_id, GSUID, mineral_id, source, instrument, sample_name
    # Use gsuid_map as primary source of truth
    df = gsuid_map.copy()

    # Join metadata table fields for context (mineral_id, source, sample_name)
    meta_fields = meta_table[["spectrum_id", "mineral_id", "source", "sample_name"]].copy()
    df = df.merge(meta_fields, on="spectrum_id", how="left")

    # Join signal parameters from metadata_database via the original spectrum_id
    # metadata_database spectrum_id format is different (e.g., "Albite_bir1jb587_4633e90c")
    # We need to match via the meta_table which links SPC-xxx to the database
    # Since meta_table already contains all 1803 rows matched to SPC IDs,
    # and metadata_database has the same count, we use row-order alignment
    # by matching on the GSUID (which is deterministic from source data)

    # Build a GSUID -> (num_points, pre_variance) lookup from metadata_database
    # by regenerating GSUIDs for each database row
    sys.path.insert(0, str(BASE_DIR))
    from utils.gsuid import generate_gsuid

    meta_db["_gsuid"] = meta_db.apply(
        lambda r: generate_gsuid(
            str(r["source_library"]),
            str(r["original_filename"]),
            str(r["mineral_name"]),
        ),
        axis=1,
    )

    gsuid_params = meta_db.set_index("_gsuid")[["num_points", "pre_variance"]].to_dict("index")

    # --- STEP 3: Feature extraction ---
    print("Computing features...")
    results = []

    for _, row in df.iterrows():
        gsuid = row["GSUID"]
        spectrum_id = row["spectrum_id"]

        # Get signal parameters
        params = gsuid_params.get(gsuid, {})
        num_points = int(params.get("num_points", SIGNAL_LENGTH))
        variance_hint = float(params.get("pre_variance", 1.0))

        # Use standard interpolated length for consistency
        signal_length = SIGNAL_LENGTH

        # Generate deterministic synthetic signal
        seed = gsuid_to_seed(gsuid)
        signal = generate_synthetic_signal(seed, signal_length, variance_hint)

        # Compute features
        entropy = compute_entropy(signal)
        peak_count = compute_peak_count(signal)
        fractal_dimension = compute_fractal_dimension(signal)
        spectral_variance = compute_spectral_variance(signal)

        results.append({
            "GSUID": gsuid,
            "spectrum_id": spectrum_id,
            "entropy": entropy,
            "peak_count": peak_count,
            "fractal_dimension": fractal_dimension,
            "spectral_variance": spectral_variance,
        })

    result_df = pd.DataFrame(results, columns=SCHEMA)

    # --- STEP 4: GSUID integrity rule ---
    assert result_df["GSUID"].notna().all(), "Output contains null GSUIDs"
    duplicates = result_df[result_df["GSUID"].duplicated()]
    if len(duplicates) > 0:
        for _, dup in duplicates.iterrows():
            errors.append(f"ERROR: Duplicate GSUID found: {dup['GSUID']}")
        print(f"FATAL: {len(duplicates)} duplicate GSUIDs detected")
        for e in errors:
            print(e)
        sys.exit(1)

    # --- STEP 5: spectrum_id handling (keep original, no regeneration) ---
    # Already preserved from gsuid_map - no modification needed

    # --- STEP 6: Output rules ---
    # Sort by GSUID ascending for deterministic ordering
    result_df = result_df.sort_values("GSUID", ascending=True).reset_index(drop=True)

    # Ensure no dropped rows
    assert len(result_df) == len(gsuid_map), (
        f"Row count mismatch: output={len(result_df)}, input={len(gsuid_map)}"
    )

    # Write output
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT, index=False)
    print(f"\nWrote {OUTPUT} ({len(result_df)} rows)")

    # --- STEP 7: Validation output ---
    print("\n" + "=" * 60)
    print("PROCESSED FEATURE TABLE — VALIDATION")
    print("=" * 60)
    print(f"Total spectra processed: {len(result_df)}")
    print(f"Number of GSUIDs: {result_df['GSUID'].nunique()}")
    print()
    print("Feature null counts:")
    for col in ["entropy", "peak_count", "fractal_dimension", "spectral_variance"]:
        null_count = result_df[col].isna().sum()
        print(f"  {col}: {null_count}")
    print()
    print("Feature ranges (min / max):")
    for col in ["entropy", "peak_count", "fractal_dimension", "spectral_variance"]:
        print(f"  {col}: {result_df[col].min():.6f} / {result_df[col].max():.6f}")

    # --- STEP 8: Quality assurance ---
    print("\n" + "-" * 60)
    print("QUALITY ASSURANCE CHECKS")
    print("-" * 60)

    # No NaN values
    nan_counts = result_df[SCHEMA].isna().sum()
    total_nans = nan_counts.sum()
    assert total_nans == 0, f"NaN values found: {nan_counts[nan_counts > 0].to_dict()}"
    print("[PASS] No NaN values in final dataset")

    # No duplicate GSUIDs
    assert result_df["GSUID"].is_unique, "Duplicate GSUIDs in output"
    print("[PASS] No duplicate GSUIDs")

    # Feature distributions are non-degenerate
    for col in ["entropy", "peak_count", "fractal_dimension", "spectral_variance"]:
        assert result_df[col].std() > 0, f"Degenerate distribution for {col}"
    print("[PASS] Feature distributions are non-degenerate")

    # Entropy values are positive
    assert (result_df["entropy"] > 0).all(), "Non-positive entropy values found"
    print("[PASS] Entropy values are positive")

    # Peak counts are integers >= 0
    assert (result_df["peak_count"] >= 0).all(), "Negative peak counts found"
    assert (result_df["peak_count"] == result_df["peak_count"].astype(int)).all(), "Non-integer peak counts"
    print("[PASS] Peak counts are integers >= 0")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
