# Spectral Data Location

This project uses large spectral datasets that are **not stored in this GitHub repository** due to size constraints.

## Data Location (Local / Cloud)

The full dataset is located at:

```
https://drive.google.com/drive/folders/1teRB8PcGcusi1vv0On_fIcETlsjSJ3fV
```

## Structure (expected)

```
data/
├── raw/        # original spectral datasets
├── cleaned/    # processed spectra
├── metadata/   # CSV tables describing samples
```

## Important Notes

* Raw and processed spectral data are NOT version-controlled in GitHub.
* Only code, metadata summaries, and analysis scripts are stored in the repository.
* Data must be downloaded or mounted before running pipelines.

## How to Use

1. Download or sync data from Google Drive.
2. Place it into a local `/data/` directory or mount path.
3. Run preprocessing scripts from `src/`.

## Reproducibility

All transformations from raw → cleaned data are reproducible via scripts in `src/`.