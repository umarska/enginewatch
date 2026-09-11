"""Download, verify, and read the public NASA C-MAPSS FD001 benchmark."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zipfile

import numpy as np
import pandas as pd

DATA_URL = "https://zenodo.org/records/15346912/files/CMAPSSData.zip?download=1"
DATA_MD5 = "79a22f36e80606c69d0e9e4da5bb2b7a"
DATA_CITATION = (
    "A. Saxena, K. Goebel, D. Simon, and N. Eklund, Damage Propagation "
    "Modeling for Aircraft Engine Run-to-Failure Simulation, PHM 2008."
)
RAW_COLUMNS = ["engine_id", "cycle"] + [f"setting_{i}" for i in range(1, 4)] + [
    f"sensor_{i}" for i in range(1, 22)
]
REQUIRED_FILES = ("train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt")


def file_digest(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_dataset(data_dir: str | Path) -> dict:
    """Download only once, verify the publisher's MD5, extract named files safely.

    MD5 checks published-file identity; SHA-256 is also recorded for provenance.
    Raw data is intentionally excluded from source control.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / "CMAPSSData.zip"
    if not archive.exists():
        temporary = archive.with_suffix(".zip.part")
        request = urllib.request.Request(DATA_URL, headers={"User-Agent": "EngineWatch/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    actual_md5 = file_digest(archive, "md5")
    if actual_md5 != DATA_MD5:
        raise ValueError(f"Dataset archive checksum mismatch: {actual_md5}; expected {DATA_MD5}")
    with zipfile.ZipFile(archive) as source:
        for name in REQUIRED_FILES:
            matches = [entry for entry in source.namelist() if Path(entry).name == name]
            if len(matches) != 1:
                raise ValueError(f"Archive must contain exactly one {name}")
            # Explicit basenames avoid extracting arbitrary archive paths.
            (data_dir / name).write_bytes(source.read(matches[0]))
    provenance = {
        "source": DATA_URL,
        "dataset": "NASA C-MAPSS FD001",
        "zenodo_record": "https://zenodo.org/records/15346912",
        "nasa_catalog": "https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data",
        "archive_md5": actual_md5,
        "archive_sha256": file_digest(archive),
        "archive_size_bytes": archive.stat().st_size,
        "files_sha256": {name: file_digest(data_dir / name) for name in REQUIRED_FILES},
        "citation": DATA_CITATION,
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_source": "https://zenodo.org/api/records/15346912 (metadata.license.id = cc-by-4.0)",
        "license_note": "The rendered NASA/Zenodo pages omit a license, but the Zenodo record API explicitly declares CC BY 4.0. NASA attribution is preserved; full raw data is downloaded separately.",
    }
    (data_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


def validate_frame(frame: pd.DataFrame, *, expected_engines: int | None = None) -> None:
    """Reject missing/invalid measurements, duplicate rows, and broken histories."""
    if list(frame.columns) != RAW_COLUMNS:
        raise ValueError("Each history must have exactly the 26 documented columns in order.")
    if frame.empty or not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Measurements must be non-empty, numeric, and finite.")
    for column in ("engine_id", "cycle"):
        values = frame[column].to_numpy(dtype=float)
        if (values < 1).any() or not np.equal(values, np.floor(values)).all():
            raise ValueError(f"{column} must contain positive integers.")
    if frame.duplicated(["engine_id", "cycle"]).any():
        raise ValueError("Duplicate engine/cycle pairs are not allowed.")
    if expected_engines is not None and frame.engine_id.nunique() != expected_engines:
        raise ValueError(f"Expected {expected_engines} independent engines.")
    # Validate supplied order, rather than quietly correcting it.
    for engine_id, group in frame.groupby("engine_id", sort=False):
        cycles = group.cycle.to_numpy(dtype=int)
        if cycles[0] != 1 or not np.equal(np.diff(cycles), 1).all():
            raise ValueError(f"Engine {engine_id} must have consecutive increasing cycles starting at 1.")


def read_fd001(data_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    data_dir = Path(data_dir)
    frames = []
    for name in REQUIRED_FILES[:2]:
        frame = pd.read_csv(data_dir / name, sep=r"\s+", header=None)
        if frame.shape[1] != len(RAW_COLUMNS):
            raise ValueError(f"{name} has {frame.shape[1]} columns; expected 26.")
        frame.columns = RAW_COLUMNS
        validate_frame(frame, expected_engines=100)
        frame[["engine_id", "cycle"]] = frame[["engine_id", "cycle"]].astype(int)
        frames.append(frame)
    truth = pd.read_csv(data_dir / "RUL_FD001.txt", sep=r"\s+", header=None).iloc[:, 0]
    if len(truth) != 100 or not np.isfinite(truth).all() or (truth < 0).any():
        raise ValueError("Official test labels must have 100 finite nonnegative RUL values.")
    truth.index = pd.Index(range(1, 101), name="engine_id")
    truth.name = "true_rul"
    return frames[0], frames[1], truth
