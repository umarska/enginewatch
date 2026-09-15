"""Train, calibrate, evaluate, and export EngineWatch's reproducible artifacts.

Usage: python -m enginewatch.train --project-dir .
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from enginewatch.data import download_dataset, file_digest, read_fd001
from enginewatch.evaluation import conformal_radius, intervals, regression_metrics
from enginewatch.features import FEATURE_COLUMNS, SENSOR_COLUMNS, SENSOR_LABELS, WINDOW, make_features, sample_endpoints, training_rul
from enginewatch.inference import EngineWatchPredictor
from enginewatch.models import AgeBaselineRegressor

SEED = 42
NOMINAL_COVERAGE = 0.9


def json_write(path: Path, content: dict) -> None:
    path.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def select_rows(frame: pd.DataFrame, features: pd.DataFrame, endpoints: pd.DataFrame) -> pd.DataFrame:
    lookup = pd.MultiIndex.from_frame(frame[["engine_id", "cycle"]])
    wanted = pd.MultiIndex.from_frame(endpoints[["engine_id", "cycle"]])
    positions = lookup.get_indexer(wanted)
    if (positions < 0).any():
        raise ValueError("Endpoint cycle is not in its engine's history.")
    return features.iloc[positions].reset_index(drop=True)


def engine_weights(frame: pd.DataFrame) -> np.ndarray:
    counts = frame.groupby("engine_id").cycle.transform("count").to_numpy(dtype=float)
    weights = 1.0 / counts
    return weights / weights.mean()


def fit_model(model, X, y, weights):
    if isinstance(model, Pipeline):
        model.fit(X, y, scaler__sample_weight=weights, regressor__sample_weight=weights)
    else:
        model.fit(X, y, sample_weight=weights)
    return model


def positive_prediction(model, features):
    return np.maximum(0.0, model.predict(features))


def model_candidates() -> dict:
    return {
        "Age baseline": [(AgeBaselineRegressor(), {"description": "Engine-weighted mean lifetime minus observed age"})],
        "Ridge regression": [
            (Pipeline([("scaler", StandardScaler()), ("regressor", Ridge(alpha=alpha))]), {"alpha": alpha})
            for alpha in (1.0, 100.0)
        ],
        "Gradient boosting": [
            (HistGradientBoostingRegressor(random_state=SEED, early_stopping=False, max_iter=iterations,
                 max_leaf_nodes=leaves, learning_rate=0.07, l2_regularization=l2, min_samples_leaf=25),
             {"max_iter": iterations, "max_leaf_nodes": leaves, "learning_rate": 0.07,
              "l2_regularization": l2, "min_samples_leaf": 25, "early_stopping": False})
            for iterations, leaves, l2 in ((180, 15, 5.0), (240, 31, 10.0), (240, 15, 30.0))
        ],
    }


def grouped_permutation_importance(model, X: pd.DataFrame, actual: np.ndarray) -> list[dict]:
    """Post-selection test diagnostic; grouped feature columns shuffled together.

    This uses test outcomes only to describe the frozen model; no feature/model
    selection follows. Correlation between sensors limits interpretation.
    """
    baseline = regression_metrics(actual, positive_prediction(model, X))["mae"]
    rng = np.random.default_rng(SEED + 4)
    output = []
    for sensor in SENSOR_COLUMNS:
        columns = [column for column in X.columns if column.startswith(sensor + "__")]
        changes = []
        for _ in range(8):
            shuffled = X.copy()
            shuffled.loc[:, columns] = X.iloc[rng.permutation(len(X))][columns].to_numpy()
            changes.append(regression_metrics(actual, positive_prediction(model, shuffled))["mae"] - baseline)
        output.append({"sensor": sensor, "label": SENSOR_LABELS[sensor],
            "importance": round(float(np.mean(changes)), 4), "std": round(float(np.std(changes)), 4)})
    return sorted(output, key=lambda item: item["importance"], reverse=True)


def plot_results(project_dir: Path, predictions: pd.DataFrame, table: list[dict], importance: list[dict], demo: dict):
    folder = project_dir / "artifacts" / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
        "font.size": 10, "axes.labelcolor": "#334155", "text.color": "#0f172a", "axes.titleweight": "bold"})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].errorbar(predictions.true_rul, predictions.predicted_rul,
        yerr=[predictions.predicted_rul - predictions.lower_rul, predictions.upper_rul - predictions.predicted_rul],
        fmt="o", markersize=3.5, color="#0891b2", ecolor="#cbd5e1", alpha=.8)
    max_value = max(predictions.true_rul.max(), predictions.upper_rul.max()) + 5
    axes[0].plot([0, max_value], [0, max_value], "--", color="#64748b", lw=1)
    axes[0].set(xlabel="Actual remaining cycles", ylabel="Predicted remaining cycles", title="Official test endpoints • 100 unseen engines")
    residual = predictions.predicted_rul - predictions.true_rul
    axes[1].hist(residual, bins=18, color="#0f766e", alpha=.85)
    axes[1].axvline(0, color="#64748b", linestyle="--", lw=1)
    axes[1].set(xlabel="Prediction − actual (cycles)", ylabel="Engines", title="Endpoint errors (positive = overprediction)")
    fig.savefig(folder / "evaluation.png", bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 4), constrained_layout=True)
    ax.barh([row["model"] for row in table][::-1], [row["mae"] for row in table][::-1], color=["#0891b2", "#0f766e", "#94a3b8"])
    ax.set(xlabel="Mean absolute error (cycles; lower is better)", title="All models evaluated on the same 100 test endpoints")
    fig.savefig(folder / "model_comparison.png", bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    top = importance[:10][::-1]
    ax.barh([item["sensor"].replace("_", " ") for item in top], [item["importance"] for item in top], color="#0891b2")
    ax.axvline(0, color="#64748b", lw=1)
    ax.set(xlabel="Increase in test MAE after group permutation (cycles)", title="Frozen-model sensor importance • correlated sensors can mask each other")
    fig.savefig(folder / "sensor_importance.png", bbox_inches="tight")
    plt.close(fig)
    # A fixed illustrative engine, selected by ID before inspecting its result.
    engine = demo["engines"]["1"]
    fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
    ax.fill_between(engine["cycles"], engine["lower"], engine["upper"], color="#67e8f9", alpha=.3, label="90% target endpoint interval")
    ax.plot(engine["cycles"], engine["predictions"], color="#0891b2", label="Predicted remaining life")
    ax.plot(engine["cycles"], engine["true_rul"], color="#334155", linestyle="--", label="Benchmark truth")
    ax.set(xlabel="Observed operating cycle", ylabel="Remaining cycles", title="Engine 1 replay • every prediction uses only data available at that cycle")
    ax.legend(frameon=False, loc="upper right")
    fig.savefig(folder / "engine_replay.png", bbox_inches="tight")
    plt.close(fig)


def train(project_dir: str | Path, skip_download: bool = False) -> dict:
    start = time.perf_counter()
    project_dir = Path(project_dir).resolve()
    data_dir = project_dir / "data" / "raw"
    artifacts = project_dir / "artifacts"
    models_dir = project_dir / "models"
    artifacts.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    if skip_download:
        provenance = json.loads((data_dir / "provenance.json").read_text(encoding="utf-8"))
        for filename, expected_digest in provenance["files_sha256"].items():
            if file_digest(data_dir / filename) != expected_digest:
                raise ValueError(f"Cached dataset checksum mismatch: {filename}. Download a fresh verified copy.")
    else:
        provenance = download_dataset(data_dir)
    train_frame, test_frame, official_truth = read_fd001(data_dir)
    train_features = make_features(train_frame)
    target = training_rul(train_frame)
    rng = np.random.default_rng(SEED)
    order = rng.permutation(np.sort(train_frame.engine_id.unique())).astype(int).tolist()
    fit_ids, validation_ids, calibration_ids = order[:60], order[60:80], order[80:]
    split = {"seed": SEED, "fit_engine_ids": sorted(fit_ids), "validation_engine_ids": sorted(validation_ids), "calibration_engine_ids": sorted(calibration_ids)}
    json_write(artifacts / "split.json", split)
    validation_endpoints = sample_endpoints(train_frame, validation_ids, SEED + 1)
    calibration_endpoints = sample_endpoints(train_frame, calibration_ids, SEED + 2)
    validation_endpoints.to_csv(artifacts / "validation_endpoints.csv", index=False)
    calibration_endpoints.to_csv(artifacts / "calibration_endpoints.csv", index=False)
    validation_X = select_rows(train_frame, train_features, validation_endpoints)
    validation_y = validation_endpoints.true_rul.to_numpy(dtype=float)
    fit_mask = train_frame.engine_id.isin(fit_ids)
    X_fit, y_fit = train_features.loc[fit_mask], target.loc[fit_mask]
    weights_fit = engine_weights(train_frame.loc[fit_mask])
    tuning = []
    chosen_by_family = {}
    chosen_params = {}
    chosen_validation = {}
    for family, candidates in model_candidates().items():
        best_mae = float("inf")
        for model, parameters in candidates:
            fit_model(model, X_fit, y_fit, weights_fit)
            metrics = regression_metrics(validation_y, positive_prediction(model, validation_X))
            tuning.append({"model": family, "parameters": parameters, "validation": metrics})
            print(f"{family} {parameters}: validation MAE {metrics['mae']:.3f}", flush=True)
            if metrics["mae"] < best_mae:
                best_mae = metrics["mae"]
                chosen_by_family[family] = model
                chosen_params[family] = parameters
                chosen_validation[family] = metrics
    selected_name = min(chosen_validation, key=lambda family: chosen_validation[family]["mae"])
    final_mask = train_frame.engine_id.isin(fit_ids + validation_ids)
    X_final, y_final = train_features.loc[final_mask], target.loc[final_mask]
    weights_final = engine_weights(train_frame.loc[final_mask])
    for model in chosen_by_family.values():
        fit_model(model, X_final, y_final, weights_final)
    selected_model = chosen_by_family[selected_name]
    calibration_X = select_rows(train_frame, train_features, calibration_endpoints)
    calibration_prediction = positive_prediction(selected_model, calibration_X)
    radius, quantile_rank = conformal_radius(calibration_endpoints.true_rul.to_numpy(), calibration_prediction, NOMINAL_COVERAGE)
    calibration_output = calibration_endpoints.copy()
    calibration_output["predicted_rul"] = calibration_prediction
    calibration_output["absolute_error"] = np.abs(calibration_output.predicted_rul - calibration_output.true_rul)
    calibration_output.to_csv(artifacts / "calibration_predictions.csv", index=False)
    # Official test labels are first used after all model fitting and calibration.
    test_features = make_features(test_frame)
    endpoints = test_frame.groupby("engine_id", sort=True).tail(1)[["engine_id", "cycle"]].sort_values("engine_id").reset_index(drop=True)
    test_X = select_rows(test_frame, test_features, endpoints)
    test_y = official_truth.reindex(endpoints.engine_id).to_numpy(dtype=float)
    output = endpoints.copy()
    output["true_rul"] = test_y
    column_map = {"Age baseline": "age_baseline_prediction", "Ridge regression": "ridge_prediction", "Gradient boosting": "gradient_boosting_prediction"}
    table = []
    for family, model in chosen_by_family.items():
        predicted = positive_prediction(model, test_X)
        output[column_map[family]] = predicted
        table.append({"model": family, **regression_metrics(test_y, predicted), "validation_mae": chosen_validation[family]["mae"], "parameters": chosen_params[family]})
    output["predicted_rul"] = output[column_map[selected_name]]
    lower, upper = intervals(output.predicted_rul.to_numpy(), radius)
    output["lower_rul"], output["upper_rul"] = lower, upper
    output.to_csv(artifacts / "test_predictions.csv", index=False)
    coverage = float(np.mean((test_y >= lower) & (test_y <= upper)))
    mean_width = float(np.mean(upper - lower))
    interval_details = {"nominal_coverage": NOMINAL_COVERAGE, "test_coverage": coverage,
        "mean_width": mean_width, "calibration_engines": len(calibration_ids), "radius": radius,
        "finite_sample_quantile_rank": quantile_rank,
        "guarantee_scope": "Marginal coverage under exchangeability of independent calibration/test endpoints, not a per-engine or simultaneous trajectory guarantee.",
        "distribution_shift_note": "Calibration endpoints are uniformly truncated from 30..min(250,lifetime-1); the official publisher's truncation mechanism may differ. Empirical test coverage is reported, not guaranteed."}
    bundle = {"schema_version": 1, "selected_model": selected_model, "selected_model_name": selected_name,
        "models": chosen_by_family, "parameters": chosen_params, "conformal_radius": radius,
        "nominal_coverage": NOMINAL_COVERAGE, "window": WINDOW, "feature_columns": FEATURE_COLUMNS,
        "feature_medians": X_final.median().to_dict(),
        "sensor_ranges": {sensor: [float(train_frame.loc[final_mask, sensor].min()), float(train_frame.loc[final_mask, sensor].max())] for sensor in SENSOR_COLUMNS},
        "settings_ranges": {f"setting_{number}": [float(train_frame.loc[final_mask, f"setting_{number}"].min()), float(train_frame.loc[final_mask, f"setting_{number}"].max())] for number in range(1, 4)},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__},
        "split": split}
    joblib.dump(bundle, models_dir / "model.joblib", compress=3)
    predictor = EngineWatchPredictor(bundle)
    importance = grouped_permutation_importance(selected_model, test_X, test_y)
    summary = {"dataset": "NASA C-MAPSS FD001", "selected_model": selected_name,
        "test_engines": 100, "train_engines": 100, "metrics": table,
        "interval": interval_details, "split": {"fit": 60, "validation": 20, "calibration": 20},
        "feature_count": len(FEATURE_COLUMNS), "window": WINDOW}
    demo = {"summary": summary, "fleet": [], "engines": {}, "feature_importance": importance}
    endpoint_lookup = output.set_index("engine_id")
    for engine_id, history in test_frame.groupby("engine_id", sort=True):
        engine = predictor.predict_history(history)
        endpoint = endpoint_lookup.loc[engine_id]
        engine["true_rul"] = (int(history.cycle.max()) - history.cycle + float(endpoint.true_rul)).astype(float).tolist()
        demo["engines"][str(engine_id)] = engine
        demo["fleet"].append({"id": int(engine_id), "cycles": int(endpoint.cycle),
            "predicted_rul": round(float(endpoint.predicted_rul), 3), "lower_rul": round(float(endpoint.lower_rul), 3),
            "upper_rul": round(float(endpoint.upper_rul), 3), "true_rul": float(endpoint.true_rul)})
    # Compact JSON keeps the offline demonstration small enough for GitHub.
    (artifacts / "demo.json").write_text(json.dumps(demo, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    examples_dir = project_dir / "data" / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    test_frame.loc[test_frame.engine_id == 1].to_csv(examples_dir / "sample.csv", index=False)
    plot_results(project_dir, output, table, importance, demo)
    results = {**summary, "schema_version": 1, "seed": SEED, "selected_parameters": chosen_params[selected_name],
        "tuning": tuning, "data": {"training_rows": len(train_frame), "test_rows": len(test_frame),
            "training_lifetime_min": int(train_frame.groupby("engine_id").cycle.max().min()),
            "training_lifetime_max": int(train_frame.groupby("engine_id").cycle.max().max()), "provenance": provenance},
        "split_ids": split, "feature_columns": FEATURE_COLUMNS, "target": "Uncapped lifetime minus cycle; nonnegative predictions.",
        "feature_recipe": "Cycle plus14 sensor groups: current reading, trailing20 mean/std, endpoint trend per cycle, deviation from first5 available mean. Only current/past observations.",
        "endpoint_sampling": {"validation_seed": SEED + 1, "calibration_seed": SEED + 2,
            "method": "One uniformly sampled cycle30..min(250,lifetime-1) per independent held-out engine; official test distribution not consulted."},
        "engine_weighting": "Each training engine has equal total weight regardless of trajectory length.",
        "model_selection": "Minimum validation endpoint MAE; family winners refit on80 fit+validation engines.20 calibration engines stay untouched.",
        "feature_importance": importance,
        "explanation_method": "Endpoint sensitivity = prediction after replacing one sensor group's5 features with fitted training medians minus original prediction. Non-additive and not causal.",
        "limitations": ["Simulation with one condition and one fault mode; no real-aircraft validation.",
            "Only20 calibration engines: coarse, wide intervals and sensitivity to truncation distribution.",
            "Intervals calibrated for endpoints; replay intervals have no simultaneous trajectory coverage guarantee.",
            "Uncapped early-life RUL has intrinsic uncertainty from unknown initial wear.",
            "Grouped permutation and substitution describe model behavior; sensor correlation prevents causal interpretation."],
        "versions": bundle["versions"], "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_seconds": round(time.perf_counter() - start, 3),
        "model_sha256": file_digest(models_dir / "model.joblib")}
    json_write(artifacts / "results.json", results)
    json_write(artifacts / "provenance.json", provenance)
    json_write(artifacts / "model_card.json", {"name": "EngineWatch", "intended_use": "Educational predictive-maintenance simulation and reproducible benchmark.", "excluded_use": "Operational aviation or maintenance decisions.", "results": summary, "limitations": results["limitations"], "data": provenance, "explanations": results["explanation_method"]})
    print(f"Selected {selected_name}; test MAE {regression_metrics(test_y, output.predicted_rul)['mae']:.3f}; coverage {coverage:.1%}; radius {radius:.3f}; {results['training_seconds']:.1f}s", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--skip-download", action="store_true", help="Use already verified cached FD001 data.")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        train(args.project_dir, skip_download=args.skip_download)


if __name__ == "__main__":
    main()
