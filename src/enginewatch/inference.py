"""Artifact loading and predictions from one observed engine history."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from enginewatch.data import RAW_COLUMNS, validate_frame
from enginewatch.evaluation import intervals
from enginewatch.features import DISPLAY_SENSORS, SENSOR_COLUMNS, SENSOR_LABELS, make_features


class EngineWatchPredictor:
    """Load trusted local models once, then forecast any valid observed history.

    Never load a joblib file submitted by a user: pickle-based artifacts can
    execute code. This class only reads the repository's trusted model bundle.
    """

    def __init__(self, bundle: dict):
        self.bundle = bundle
        self.model = bundle["selected_model"]
        self.radius = float(bundle["conformal_radius"])
        self.feature_medians = pd.Series(bundle["feature_medians"])

    @classmethod
    def from_artifacts(cls, project_dir: str | Path | None = None) -> "EngineWatchPredictor":
        root = Path(project_dir) if project_dir is not None else Path(__file__).resolve().parents[2]
        return cls(joblib.load(root / "models" / "model.joblib"))

    def predict_features(self, features: pd.DataFrame) -> np.ndarray:
        # Large OpenMP pools are slower for small interactive requests.
        with threadpool_limits(limits=2):
            return np.maximum(0.0, self.model.predict(features))

    def explain_endpoint(self, features: pd.DataFrame) -> list[dict]:
        """Group substitution sensitivity, measured in cycles, not causal effects.

        Each comparison replaces all five features of one sensor by the medians
        of fit+validation histories. Sensors can be correlated; sensitivities
        are not additive and substituted combinations need not be realistic.
        Positive values mean the reference substitution raises estimated RUL.
        """
        terminal = features.iloc[[-1]].copy()
        original = float(self.predict_features(terminal)[0])
        explanations = []
        for sensor in SENSOR_COLUMNS:
            columns = [column for column in features.columns if column.startswith(sensor + "__")]
            reference = terminal.copy()
            reference.loc[:, columns] = self.feature_medians.loc[columns].to_numpy()
            effect = float(self.predict_features(reference)[0] - original)
            explanations.append({"sensor": sensor, "label": SENSOR_LABELS[sensor], "effect": round(effect, 3)})
        return sorted(explanations, key=lambda item: abs(item["effect"]), reverse=True)

    def predict_history(self, rows: list[dict] | pd.DataFrame) -> dict:
        frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        if set(frame.columns) != set(RAW_COLUMNS):
            missing = sorted(set(RAW_COLUMNS) - set(frame.columns))
            unexpected = sorted(set(frame.columns) - set(RAW_COLUMNS))
            raise ValueError(f"CSV needs exactly the 26 documented columns. Missing: {missing}; unexpected: {unexpected}.")
        try:
            frame = frame.loc[:, RAW_COLUMNS].apply(pd.to_numeric, errors="raise")
        except (ValueError, TypeError) as error:
            raise ValueError("All CSV measurements must be numeric.") from error
        validate_frame(frame)
        if frame.engine_id.nunique() != 1:
            raise ValueError("Upload exactly one engine's observed history.")
        features = make_features(frame, window=int(self.bundle["window"]))
        predicted = self.predict_features(features)
        lower, upper = intervals(predicted, self.radius)
        warnings = []
        if len(frame) < int(self.bundle["window"]):
            warnings.append("Short history: the trailing sensor window contains fewer than 20 cycles.")
        if len(frame) > 400:
            warnings.append("History is longer than typical FD001 training trajectories; prediction may extrapolate poorly.")
        # Compare uploaded sensor values with recorded fit+validation ranges.
        outside = [sensor for sensor in SENSOR_COLUMNS if (
            frame[sensor].min() < self.bundle["sensor_ranges"][sensor][0]
            or frame[sensor].max() > self.bundle["sensor_ranges"][sensor][1]
        )]
        if outside:
            warnings.append("Some sensor measurements fall outside the training range: " + ", ".join(outside) + ".")
        settings_outside = [setting for setting, limits in self.bundle.get("settings_ranges", {}).items() if (
            frame[setting].min() < limits[0] or frame[setting].max() > limits[1]
        )]
        if settings_outside:
            warnings.append("Operating settings fall outside the single-condition FD001 training range: "
                + ", ".join(settings_outside) + ". This model does not adjust for different operating conditions.")
        return {
            "id": int(frame.engine_id.iloc[0]),
            "cycles": frame.cycle.astype(int).tolist(),
            "predictions": np.round(predicted, 3).tolist(),
            "lower": np.round(lower, 3).tolist(),
            "upper": np.round(upper, 3).tolist(),
            "true_rul": None,
            "sensors": [
                {"id": sensor, "label": SENSOR_LABELS[sensor], "values": frame[sensor].astype(float).round(6).tolist()}
                for sensor in DISPLAY_SENSORS
            ],
            "contributions": self.explain_endpoint(features),
            "warnings": warnings,
        }


def load_demo(project_dir: str | Path | None = None) -> dict:
    root = Path(project_dir) if project_dir is not None else Path(__file__).resolve().parents[2]
    return json.loads((root / "artifacts" / "demo.json").read_text(encoding="utf-8"))
