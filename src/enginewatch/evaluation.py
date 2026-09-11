"""Independent-engine errors and finite-sample split conformal intervals."""

from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error


def nasa_score(actual: np.ndarray, predicted: np.ndarray) -> float:
    """PHM asymmetric sum: late-life overprediction is penalized more strongly."""
    difference = np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float)
    return float(np.sum(np.where(difference < 0, np.expm1(-difference / 13.0), np.expm1(difference / 10.0))))


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "nasa_score": nasa_score(actual, predicted),
    }


def conformal_radius(actual: np.ndarray, predicted: np.ndarray, coverage: float = 0.9) -> tuple[float, int]:
    """The ceil((n+1)*coverage)-th order statistic of calibration errors.

    Each calibration item is one endpoint from a different held-out engine.
    Returns infinity if sample size cannot support the requested coverage.
    """
    errors = np.abs(np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float))
    if errors.size == 0 or not (0 < coverage < 1) or not np.isfinite(errors).all():
        raise ValueError("Calibration errors must be finite and non-empty; coverage must be between zero and one.")
    rank = math.ceil((len(errors) + 1) * coverage)
    if rank > len(errors):
        return float("inf"), rank
    return float(np.sort(errors)[rank - 1]), rank


def intervals(predicted: np.ndarray, radius: float) -> tuple[np.ndarray, np.ndarray]:
    predicted = np.asarray(predicted, dtype=float)
    # Truncate the lower endpoint to the known RUL domain; no valid nonnegative
    # true RUL is lost by this operation.
    return np.maximum(0, predicted - radius), predicted + radius
