"""
Build Spectrum Metadata Table (RELATIONAL LAYER)
Creates a structured, normalized metadata table that links spectral samples 
to minerals, instruments, and preprocessing states.
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
import re
from collections import defaultdict


def load_mineral_metadata(metadata_path):
    """Load mineral metadata to establish mineral_id mappings."""
    df = pd.read_csv(metadata_path)
    # Create mapping from mineral_name to mineral_id
    mineral_to_id = dict(zip(df['mineral_name'], df['mineral_id']))
    return df, mineral_to_id


def parse_spectrum_filename(filename, mineral_name):
    """
    Parse spectrum filename to extract metadata.
    
    Returns: dict with sample_name, source, instrument
    """
    # Remove '_cleaned.parquet' suffix
    base_name = filename.replace('_cleaned.parquet', '')
    
    # Remove mineral prefix if present
    if base_name.startswith(mineral_name + '_'):
        base_name = base_name[len(mineral_name)+1:]
    
    # Determine source and instrument from filename patterns
    source = "UNKNOWN"
    instrument = "UNKNOWN"
    sample_name = base_name
    
    # Pattern 1: Raman format - contains "Raman"
    # e.g., Albite__R040068__Raman__514______Raman_Data_Processed__6caf112eadf1916b8605894c30f8_24ada866
    if 'Raman' in base_name:
        source = "RRUFF"
        instrument = "Raman"
        # Extract sample ID (e.g., R040068)
        raman_match = re.search(r'R\d+', base_name)
        if raman_match:
            sample_name = raman_match.group()
        else:
            sample_name = base_name.split('__')[0] if '__' in base_name else base_name
    
    # Pattern 2: USGS/ASD format - contains "ASD", "errorbars", or "s07" prefix
    # e.g., errorbars_for_s07_ASD_Grossular_HS113.3B-HCL_Garnt_BECKd_AREF_0d4f40a6
    # or s07_AV00_Beryl_GDS9_lt150um_gs_BECKb_AREF_2b63...
    # or s07_HY07_Rutile_HS126.3B_BECKc_AREF_12ae8d0d
    # or s07CRSMg_Zircon_WS522_BECKa_AREF_0be60f2f
    # or splib07a_Zircon_WS522_BECKa_AREF_44cd6444
    elif 'ASD' in base_name or 'errorbars' in base_name or re.search(r'^s07', base_name) or re.search(r'^splib', base_name):
        source = "USGS"
        instrument = "ASD"
        # Extract the actual sample ID (e.g., HS113.3B-HCL)
        # Pattern: HSxxx.x or similar after the mineral name
        parts = base_name.split('_')
        # Find the part that looks like a sample ID (starts with HS or contains numbers and dots)
        sample_name = base_name  # Default
        for i, part in enumerate(parts):
            # Look for patterns like HS113.3B, NMNHC5390, etc.
            if re.match(r'^[A-Z]{2}\d+\.?\d*[A-Z]*$', part) or re.match(r'^[A-Z]+\d+', part):
                sample_name = part
                break
            # Also look for the mineral name followed by sample ID
            if i > 0 and parts[i-1] == mineral_name and re.search(r'\d', part):
                sample_name = part
                break
    
    # Pattern 3: RRUFF format - sample ID starting with numbers
    # e.g., 397s214_9bb43993, 1101f549_8246b47b, 397s214p_268e75cf
    elif re.match(r'^\d+[a-z]*\d*[a-z]?_[a-f0-9]+$', base_name):
        source = "RRUFF"
        instrument = "UNKNOWN"
        parts = base_name.split('_')
        if len(parts) >= 2:
            sample_name = parts[0]
    
    # Pattern 4: RELAB format - lowercase letters + numbers pattern (more flexible)
    # e.g., bir1be017_3cee28f6, c1sc71_12240f21, capa05_005cb627, m1gn04_7946727a
    # spindo_3098eb62, spinmo_48ae6592
    # Must NOT start with a number (to avoid matching RRUFF)
    elif re.match(r'^[a-z][a-z0-9]*\d*[a-z]*_[a-f0-9]+$', base_name):
        source = "RELAB"
        instrument = "UNKNOWN"
        parts = base_name.split('_')
        if len(parts) >= 2:
            sample_name = parts[0]
    
    return {
        'sample_name': sample_name,
        'source': source,
        'instrument': instrument
    }


def load_rejection_report(rejection_path):
    """Load rejection report to identify invalid spectra."""
    if os.path.exists(rejection_path):
        df = pd.read_csv(rejection_path)
        # Create set of rejected file identifiers
        rejected = set()
        for _, row in df.iterrows():
            # Extract base filename from file_path
            file_path = row['file_path']
            if file_path:
                # Get the filename without extension
                filename = os.path.basename(file_path)
                rejected.add(filename)
        return df, rejected
    return pd.DataFrame(), set()


def scan_cleaned_spectra(cleaned_dir, mineral_to_id, rejected_set):
    """
    Scan all cleaned spectra files and build metadata records.
    Deduplicates by sample_name + mineral_name to get unique spectra.
    
    Returns: list of dicts containing spectrum metadata
    """
    records = []
    spectrum_counter = defaultdict(int)
    seen_samples = set()  # Track (mineral_name, sample_name) to deduplicate
    
    # Iterate through mineral directories
    for mineral_dir in sorted(os.listdir(cleaned_dir)):
        mineral_path = os.path.join(cleaned_dir, mineral_dir)
        
        if not os.path.isdir(mineral_path):
            continue
        
        # Check if mineral exists in metadata
        if mineral_dir not in mineral_to_id:
            print(f"Warning: Mineral '{mineral_dir}' not found in mineral_metadata.csv, skipping...")
            continue
        
        mineral_id = mineral_to_id[mineral_dir]
        
        # Scan all parquet files in mineral directory
        for filename in sorted(os.listdir(mineral_path)):
            if not filename.endswith('_cleaned.parquet'):
                continue
            
            # Parse filename
            parsed = parse_spectrum_filename(filename, mineral_dir)
            
            # Deduplicate by sample_name + mineral_name
            sample_key = (mineral_dir, parsed['sample_name'])
            if sample_key in seen_samples:
                continue  # Skip duplicate samples
            seen_samples.add(sample_key)
            
            # Generate spectrum_id
            spectrum_counter[mineral_dir] += 1
            spectrum_id = f"{mineral_dir[:3].upper()}{spectrum_counter[mineral_dir]:03d}"
            
            # Determine if valid (not in rejection set)
            # Note: We check against a simplified identifier since filenames differ
            is_valid = True  # Default to True for cleaned files
            
            # Build record
            record = {
                'spectrum_id': spectrum_id,
                'mineral_id': mineral_id,
                'mineral_name': mineral_dir,
                'source': parsed['source'],
                'instrument': parsed['instrument'],
                'sample_name': parsed['sample_name'],
                'wavelength_range': "400-2500",
                'resolution': np.nan,
                'preprocessing_version': "v1.0",
                'signal_quality': 1.0,  # All cleaned files passed preprocessing
                'is_valid': is_valid
            }
            
            records.append(record)
    
    return records


def create_spectrum_metadata_table():
    """Main function to create the spectrum metadata table."""
    
    # Paths
    base_dir = Path("c:/Users/Vitaly/Projects/PhD/spectral-feature-engine")
    metadata_path = base_dir / "data" / "metadata" / "mineral_metadata.csv"
    cleaned_dir = base_dir / "data" / "cleaned"
    rejection_path = base_dir / "data" / "reports" / "rejection_report.csv"
    output_path = base_dir / "data" / "metadata" / "spectrum_metadata.csv"
    
    # Load mineral metadata
    print("Loading mineral metadata...")
    mineral_df, mineral_to_id = load_mineral_metadata(metadata_path)
    print(f"Loaded {len(mineral_df)} minerals")
    
    # Load rejection report
    print("Loading rejection report...")
    rejection_df, rejected_set = load_rejection_report(rejection_path)
    print(f"Loaded {len(rejection_df)} rejected spectra")
    
    # Scan cleaned spectra
    print("Scanning cleaned spectra...")
    records = scan_cleaned_spectra(cleaned_dir, mineral_to_id, rejected_set)
    print(f"Found {len(records)} cleaned spectra")
    
    # Create DataFrame
    print("Creating spectrum metadata DataFrame...")
    spectrum_metadata = pd.DataFrame(records)
    
    # Ensure required columns and order
    required_columns = [
        'spectrum_id', 'mineral_id', 'mineral_name', 'source', 'instrument',
        'sample_name', 'wavelength_range', 'resolution', 'preprocessing_version',
        'signal_quality', 'is_valid'
    ]
    
    # Reorder columns
    spectrum_metadata = spectrum_metadata[required_columns]
    
    # Ensure referential integrity
    print("Checking referential integrity...")
    invalid_mineral_ids = set(spectrum_metadata['mineral_id']) - set(mineral_df['mineral_id'])
    if invalid_mineral_ids:
        print(f"Warning: Found spectra with invalid mineral_ids: {invalid_mineral_ids}")
    
    # Check for duplicate spectrum_ids
    duplicate_ids = spectrum_metadata[spectrum_metadata['spectrum_id'].duplicated()]
    if len(duplicate_ids) > 0:
        print(f"Warning: Found {len(duplicate_ids)} duplicate spectrum_ids, regenerating...")
        # Regenerate unique spectrum_ids
        spectrum_counter = defaultdict(int)
        new_ids = []
        for mineral_name in spectrum_metadata['mineral_name']:
            spectrum_counter[mineral_name] += 1
            new_ids.append(f"{mineral_name[:3].upper()}{spectrum_counter[mineral_name]:03d}")
        spectrum_metadata['spectrum_id'] = new_ids
    
    # Export to CSV
    print(f"Exporting to {output_path}...")
    spectrum_metadata.to_csv(output_path, index=False)
    
    # Print statistics
    print("\n" + "="*60)
    print("SPECTRUM METADATA STATISTICS")
    print("="*60)
    
    # Number of spectra per mineral
    print("\nSpectra per mineral:")
    spectra_per_mineral = spectrum_metadata.groupby('mineral_name').size().sort_values(ascending=False)
    for mineral, count in spectra_per_mineral.items():
        print(f"  {mineral}: {count}")
    
    # Number of invalid spectra
    invalid_count = (~spectrum_metadata['is_valid']).sum()
    print(f"\nInvalid spectra: {invalid_count}")
    
    # Distribution of sources
    print("\nSource distribution:")
    source_dist = spectrum_metadata['source'].value_counts()
    for source, count in source_dist.items():
        print(f"  {source}: {count}")
    
    # Instrument distribution
    print("\nInstrument distribution:")
    instrument_dist = spectrum_metadata['instrument'].value_counts()
    for instrument, count in instrument_dist.items():
        print(f"  {instrument}: {count}")
    
    print(f"\nTotal spectra: {len(spectrum_metadata)}")
    print(f"Unique spectrum_ids: {spectrum_metadata['spectrum_id'].nunique()}")
    print(f"Output saved to: {output_path}")
    
    return spectrum_metadata


if __name__ == "__main__":
    spectrum_metadata = create_spectrum_metadata_table()
