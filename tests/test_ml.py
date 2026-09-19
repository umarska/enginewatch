"""Checks of leakage, calibration, and independently recomputed evidence."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from enginewatch.data import RAW_COLUMNS, validate_frame
from enginewatch.evaluation import conformal_radius, nasa_score
from enginewatch.features import make_features

ROOT = Path(__file__).resolve().parents[1]


def history(count=30, engine_id=1):
    rows = []
    for cycle in range(1, count + 1):
        rows.append([engine_id, cycle, 0.0, 0.0, 100.0] + [sensor * 10 + cycle for sensor in range(1, 22)])
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


def test_features_are_causal_and_grouped_by_engine():
    first = history()
    prefix = make_features(first.iloc[:8])
    full = make_features(first)
    pd.testing.assert_frame_equal(prefix, full.iloc[:8])
    changed = first.copy()
    changed.loc[8:, "sensor_2"] = 1_000_000
    pd.testing.assert_frame_equal(prefix, make_features(changed).iloc[:8])
    second = history(engine_id=2)
    second.loc[:, "sensor_2"] += 10_000
    combined = pd.concat([first, second], ignore_index=True)
    np.testing.assert_allclose(make_features(combined).iloc[:30], full)
    features = make_features(first)
    assert features.iloc[0]["sensor_2__mean"] == 21
    assert features.iloc[1]["sensor_2__mean"] == 21.5
    assert features.iloc[0]["sensor_2__baseline_delta"] == 0


@pytest.mark.parametrize("mutate", [
    lambda frame: frame.assign(cycle=frame.cycle + 1),
    lambda frame: frame.iloc[[0, 2, 3]],
    lambda frame: pd.concat([frame.iloc[:2], frame.iloc[:1]], ignore_index=True),
    lambda frame: frame.assign(sensor_2=np.nan),
])
def test_broken_histories_do_not_reach_model(mutate):
    with pytest.raises(ValueError):
        validate_frame(mutate(history()))


def test_asymmetric_score_penalizes_late_forecasts_more():
    actual = np.array([30.0])
    early = nasa_score(actual, np.array([20.0]))
    late = nasa_score(actual, np.array([40.0]))
    assert late > early
    assert late == pytest.approx(math.expm1(1))
    assert early == pytest.approx(math.expm1(10 / 13))


def test_conformal_uses_finite_sample_order_statistic():
    radius, rank = conformal_radius(np.arange(1.0, 21.0), np.zeros(20), coverage=0.9)
    assert (radius, rank) == (19.0, 19)
    radius, _ = conformal_radius(np.array([1.0]), np.zeros(1), coverage=0.9)
    assert math.isinf(radius)


def test_independent_engine_splits():
    split = json.loads((ROOT / "artifacts" / "split.json").read_text())
    fit, validation, calibration = (set(split[key]) for key in ("fit_engine_ids", "validation_engine_ids", "calibration_engine_ids"))
    assert (len(fit), len(validation), len(calibration)) == (60, 20, 20)
    assert not (fit & validation or fit & calibration or validation & calibration)
    assert fit | validation | calibration == set(range(1, 101))
    endpoints = pd.read_csv(ROOT / "artifacts" / "calibration_predictions.csv")
    assert endpoints.engine_id.is_unique
    assert set(endpoints.engine_id) == calibration


def test_metrics_and_intervals_recompute_from_saved_predictions():
    results = json.loads((ROOT / "artifacts" / "results.json").read_text())
    predictions = pd.read_csv(ROOT / "artifacts" / "test_predictions.csv")
    assert len(predictions) == 100 and predictions.engine_id.is_unique
    columns = {"Age baseline": "age_baseline_prediction", "Ridge regression": "ridge_prediction", "Gradient boosting": "gradient_boosting_prediction"}
    for model in results["metrics"]:
        error = predictions[columns[model["model"]]].to_numpy() - predictions.true_rul.to_numpy()
        assert model["mae"] == pytest.approx(np.mean(np.abs(error)))
        assert model["rmse"] == pytest.approx(np.sqrt(np.mean(error ** 2)))
        score = sum(math.expm1(-delta / 13) if delta < 0 else math.expm1(delta / 10) for delta in error)
        assert model["nasa_score"] == pytest.approx(score)
    contained = (predictions.true_rul >= predictions.lower_rul) & (predictions.true_rul <= predictions.upper_rul)
    assert results["interval"]["test_coverage"] == pytest.approx(contained.mean())
    assert results["interval"]["mean_width"] == pytest.approx((predictions.upper_rul - predictions.lower_rul).mean())
    calibration = pd.read_csv(ROOT / "artifacts" / "calibration_predictions.csv")
    residuals = sorted(abs(calibration.true_rul - calibration.predicted_rul))
    assert results["interval"]["radius"] == pytest.approx(residuals[18])
