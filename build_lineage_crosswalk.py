"""
Build Interim Lineage Crosswalk (REPOSITORY-LEVEL, NO EXTERNAL DATA)

Produces the strongest possible accepted-spectrum crosswalk linking:
    metadata/metadata_database.csv   (authoritative accepted spectra)
    metadata/spectrum_metadata.csv   (normalized, deduplicated table)
    metadata/mineral_metadata.csv    (mineral dimension table)
    reports/rejection_report.csv     (rejected spectra)

without requiring access to the external Google Drive dataset.

Method: the normalized table's `sample_name`/`source`/`instrument` are produced by
`build_spectrum_metadata.py::parse_spectrum_filename`, which parses the cleaned
parquet basename. The composite `spectrum_id` in metadata_database.csv IS that
basename (mineral prefix + raw stem + hash). Re-applying the exact same parser to
each composite id therefore deterministically reproduces the (mineral_name,
sample_name) key the normalized table was built on, giving an authoritative
composite -> normalized link without re-reading any spectra.

Outputs (does NOT modify any existing file):
    metadata/lineage_crosswalk.csv
"""

import os
import importlib.util
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(BASE, "metadata", "metadata_database.csv")
SM_PATH = os.path.join(BASE, "metadata", "spectrum_metadata.csv")
MIN_PATH = os.path.join(BASE, "metadata", "mineral_metadata.csv")
REJ_PATH = os.path.join(BASE, "reports", "rejection_report.csv")
OUT_PATH = os.path.join(BASE, "metadata", "lineage_crosswalk.csv")

COLUMNS = [
    "composite_spectrum_id",
    "normalized_spectrum_id",
    "mineral_id",
    "mineral_name",
    "source",
    "original_filename",
    "sample_name",
    "mapping_confidence",
]


def _load_repo_parser():
    """Import parse_spectrum_filename from the repo build script (functions only)."""
    spec = importlib.util.spec_from_file_location(
        "build_spectrum_metadata", os.path.join(BASE, "build_spectrum_metadata.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_spectrum_filename


def _stem(filename):
    """Filename without its final extension (e.g. 'bir1jb587.tab' -> 'bir1jb587')."""
    if not isinstance(filename, str):
        return ""
    base = os.path.basename(filename.replace("\\", "/"))
    return os.path.splitext(base)[0]


def build_crosswalk():
    parse = _load_repo_parser()

    md = pd.read_csv(MD_PATH)
    sm = pd.read_csv(SM_PATH)
    minerals = pd.read_csv(MIN_PATH)
    rej = pd.read_csv(REJ_PATH)

    name_to_id = dict(zip(minerals["mineral_name"], minerals["mineral_id"]))

    # Normalized lookup: (mineral_name, sample_name) -> list of normalized ids
    sm_key = (
        sm.groupby(["mineral_name", "sample_name"])["spectrum_id"]
        .apply(list)
        .to_dict()
    )
    # Per-mineral list of (sample_name, normalized_id) for fuzzy fallback
    sm_by_mineral = {}
    for _, r in sm.iterrows():
        sm_by_mineral.setdefault(r["mineral_name"], []).append(
            (str(r["sample_name"]), r["spectrum_id"])
        )

    # Size of each (mineral, sample_name) dedup group on the authoritative side
    md_parsed = md.apply(
        lambda r: parse(r["spectrum_id"], r["mineral_name"])["sample_name"], axis=1
    )
    md = md.assign(_derived_sample_name=md_parsed)
    group_size = md.groupby(["mineral_name", "_derived_sample_name"]).size().to_dict()

    rows = []
    for _, r in md.iterrows():
        mineral = r["mineral_name"]
        sample_name = r["_derived_sample_name"]
        key = (mineral, sample_name)
        norm_id = ""
        confidence = "UNMATCHED"

        if key in sm_key:
            ids = sm_key[key]
            norm_id = ids[0]
            # Exact reproduced-key match. HIGH when this composite is the sole
            # member of its dedup group (unambiguous 1:1); MEDIUM when several
            # composites collapse onto the same normalized id (the link is
            # certain, but which composite is the canonical survivor is not).
            confidence = "HIGH" if group_size.get(key, 1) == 1 else "MEDIUM"
        else:
            # Fuzzy fallback: stem/substring match within the same mineral.
            stem = _stem(r["original_filename"])
            cands = [
                nid
                for (sn, nid) in sm_by_mineral.get(mineral, [])
                if sn and (sn == stem or stem.startswith(sn) or sn in stem)
            ]
            if cands:
                norm_id = cands[0]
                confidence = "LOW"

        rows.append(
            {
                "composite_spectrum_id": r["spectrum_id"],
                "normalized_spectrum_id": norm_id,
                "mineral_id": name_to_id.get(mineral, ""),
                "mineral_name": mineral,
                "source": r["source_library"],
                "original_filename": r["original_filename"],
                "sample_name": sample_name,
                "mapping_confidence": confidence,
            }
        )

    # Rejected spectra: present in the corpus but excluded before normalization,
    # so they have no normalized counterpart by design -> UNMATCHED.
    for _, r in rej.iterrows():
        mineral = r["mineral"]
        rows.append(
            {
                "composite_spectrum_id": "",
                "normalized_spectrum_id": "",
                "mineral_id": name_to_id.get(mineral, ""),
                "mineral_name": mineral,
                "source": r["library"],
                "original_filename": os.path.basename(
                    str(r["file_path"]).replace("\\", "/")
                ),
                "sample_name": "",
                "mapping_confidence": "UNMATCHED",
            }
        )

    out = pd.DataFrame(rows, columns=COLUMNS)
    out.to_csv(OUT_PATH, index=False)

    # ---- Statistics ----
    accepted = out[out["composite_spectrum_id"] != ""]
    matched = accepted[accepted["normalized_spectrum_id"] != ""]
    print("=" * 60)
    print("LINEAGE CROSSWALK STATISTICS")
    print("=" * 60)
    print(f"Total crosswalk rows:        {len(out)}")
    print(f"  Accepted (metadata_db):    {len(accepted)}")
    print(f"  Rejected (rejection rpt):  {len(out) - len(accepted)}")
    print(f"Matched rows (have norm id): {len(matched)}")
    print(f"Unmatched rows:              {len(out) - len(matched)}")
    print("\nConfidence distribution:")
    for level in ["HIGH", "MEDIUM", "LOW", "UNMATCHED"]:
        print(f"  {level:<10}: {(out['mapping_confidence'] == level).sum()}")
    print(
        f"\nDistinct normalized ids covered: "
        f"{matched['normalized_spectrum_id'].nunique()} / {len(sm)}"
    )
    print(f"Output written to: {OUT_PATH}")
    return out


if __name__ == "__main__":
    build_crosswalk()
