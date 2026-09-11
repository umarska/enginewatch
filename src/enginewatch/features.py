"""Causal sensor features: every row uses only its engine's current/past data."""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = 20
# The standard 14 varying FD001 channels; settings are one operating condition.
# This fixed schema is chosen before validation/test inspection.
SENSOR_IDS = (2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21)
SENSOR_COLUMNS = tuple(f"sensor_{number}" for number in SENSOR_IDS)
FEATURE_SUFFIXES = ("last", "mean", "std", "trend", "baseline_delta")
FEATURE_COLUMNS = ["cycle"] + [
    f"{sensor}__{suffix}" for sensor in SENSOR_COLUMNS for suffix in FEATURE_SUFFIXES
]
DISPLAY_SENSORS = ("sensor_2", "sensor_7", "sensor_11", "sensor_12", "sensor_14", "sensor_15")
SENSOR_LABELS = {
    "sensor_2": "LPC outlet temperature (T24)",
    "sensor_3": "HPC outlet temperature (T30)",
    "sensor_4": "LPT outlet temperature (T50)",
    "sensor_7": "HPC outlet pressure (P30)",
    "sensor_8": "Fan speed (Nf)",
    "sensor_9": "Core speed (Nc)",
    "sensor_11": "Static HPC outlet pressure (Ps30)",
    "sensor_12": "Fuel flow / pressure ratio (phi)",
    "sensor_13": "Corrected fan speed (NRf)",
    "sensor_14": "Corrected core speed (NRc)",
    "sensor_15": "Bypass ratio (BPR)",
    "sensor_17": "Bleed enthalpy (htBleed)",
    "sensor_20": "HPT coolant bleed (W31)",
    "sensor_21": "LPT coolant bleed (W32)",
}


def feature_names() -> list[str]:
    return list(FEATURE_COLUMNS)


def make_features(frame: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Build features in supplied row order without target or future references.

    Trailing mean/std use at most 20 observations. Trend is the change from the
    oldest available window reading per cycle. Baseline is the mean of the
    first five readings *available at that cycle*, freezing after cycle five.
    """
    if window < 2:
        raise ValueError("Rolling window must be at least 2.")
    parts = []
    for _, history in frame.groupby("engine_id", sort=False):
        result = pd.DataFrame(index=history.index)
        result["cycle"] = history.cycle.astype(float)
        count = len(history)
        positions = np.arange(count)
        first_positions = np.maximum(0, positions - window + 1)
        span = np.maximum(1, positions - first_positions)
        for sensor in SENSOR_COLUMNS:
            values = history[sensor].astype(float)
            raw = values.to_numpy()
            prefix = f"{sensor}__"
            result[prefix + "last"] = raw
            result[prefix + "mean"] = values.rolling(window, min_periods=1).mean()
            result[prefix + "std"] = values.rolling(window, min_periods=1).std(ddof=0)
            result[prefix + "trend"] = (raw - raw[first_positions]) / span
            baseline = np.cumsum(raw[:5]) / np.arange(1, min(5, count) + 1)
            if count > 5:
                baseline = np.concatenate([baseline, np.repeat(baseline[-1], count - 5)])
            result[prefix + "baseline_delta"] = raw - baseline
        parts.append(result)
    if not parts:
        return pd.DataFrame(columns=FEATURE_COLUMNS, index=frame.index, dtype=float)
    return pd.concat(parts).reindex(frame.index).loc[:, FEATURE_COLUMNS]


def training_rul(frame: pd.DataFrame) -> pd.Series:
    """Uncapped run-to-failure target; final training cycle has RUL zero."""
    lifetimes = frame.groupby("engine_id").cycle.transform("max")
    return (lifetimes - frame.cycle).astype(float).rename("rul")


def sample_endpoints(frame: pd.DataFrame, engine_ids: list[int], seed: int) -> pd.DataFrame:
    """One reproducible truncated observation per independent held-out engine.

    The endpoint is uniform among cycles 30..min(250, lifetime-1). This explicit
    simulation approximates partial histories but does not exactly reproduce
    the publisher's unknown test truncation mechanism. No official test labels
    or test history distribution are used to select it.
    """
    rng = np.random.default_rng(seed)
    records = []
    for engine_id in sorted(engine_ids):
        lifetime = int(frame.loc[frame.engine_id == engine_id, "cycle"].max())
        low, high = min(30, lifetime - 1), min(250, lifetime - 1)
        cycle = int(rng.integers(low, high + 1))
        records.append({"engine_id": engine_id, "cycle": cycle, "true_rul": lifetime - cycle})
    return pd.DataFrame(records)
