"""
Global Spectrum Unique Identifier (GSUID) utilities.

A GSUID is a deterministic, immutable SHA-1 hash that uniquely identifies a
physical spectral measurement independent of preprocessing, normalization, or
analysis layers.

    GSUID = SHA1(source_library + "|" + original_filename + "|" + mineral_name)

All inputs are normalized before hashing:
  * ``source_library`` → upper-case  (RELAB / USGS / RRUFF)
  * ``original_filename`` → basename only (path components stripped)
  * ``mineral_name`` → exact value from metadata_database.csv (unchanged)
"""

import hashlib
import os


def normalize_identity(source: str, filename: str, mineral: str) -> str:
    """Return the canonical identity string used as SHA-1 input.

    Parameters
    ----------
    source : str
        Source library (e.g. ``"relab"``, ``"USGS"``).
    filename : str
        Original filename, possibly including path components.
    mineral : str
        Mineral name exactly as recorded in ``metadata_database.csv``.

    Returns
    -------
    str
        ``"SOURCE|basename|mineral"`` with *source* upper-cased and *filename*
        reduced to its basename.
    """
    norm_source = str(source).strip().upper()
    norm_filename = os.path.basename(str(filename).strip())
    norm_mineral = str(mineral).strip()
    return f"{norm_source}|{norm_filename}|{norm_mineral}"


def generate_gsuid(source: str, filename: str, mineral: str) -> str:
    """Return a deterministic GSUID using SHA-1 hash of normalized identity string.

    Parameters
    ----------
    source : str
        Source library (e.g. ``"relab"``, ``"USGS"``).
    filename : str
        Original filename, possibly including path components.
    mineral : str
        Mineral name exactly as recorded in ``metadata_database.csv``.

    Returns
    -------
    str
        40-character lowercase hex SHA-1 digest.
    """
    identity = normalize_identity(source, filename, mineral)
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()
