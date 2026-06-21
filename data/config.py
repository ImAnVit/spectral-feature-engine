from pathlib import Path

# Base path to spectral dataset

# For local Windows machine (Google Drive synced folder)

DATA_PATH = Path(r"https://drive.google.com/drive/folders/1teRB8PcGcusi1vv0On_fIcETlsjSJ3fV")

# Optional structured paths (recommended usage)

RAW_DATA_PATH = DATA_PATH / "raw"
CLEANED_DATA_PATH = DATA_PATH / "cleaned"
METADATA_PATH = DATA_PATH / "metadata"

# Output paths

REPORTS_PATH = Path("reports")
FIGURES_PATH = Path("figures")

# If running inside Linux (e.g., Devin Cloud), you may override:

# DATA_PATH = Path("/data/spectra")