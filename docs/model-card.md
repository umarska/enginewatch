# EngineWatch model card

## Model purpose

EngineWatch estimates remaining useful life (RUL) in operating cycles from simulated turbofan sensor histories. It is a portfolio and research application designed to make a machine-learning experiment inspectable: source data, engineered features, model selection, predictions, errors, and uncertainty are available together.

The current model identifier, training configurations, split membership, and measured metrics are recorded in [`artifacts/results.json`](../artifacts/results.json). The README provides the headline results, and the executed notebook independently recalculates them from test predictions.

The shipped model is a histogram gradient booster selected by validation MAE. Its official endpoint MAE is **14.83 cycles**, RMSE **21.48 cycles**, and asymmetric NASA score **2,439.53**. Ridge has the lower NASA score (**2,151.19**) despite higher MAE and RMSE; the selected model does not dominate all objectives. Nominal 90% prediction intervals cover **97/100** test endpoints, with a broad mean width of **101.69 cycles**.

## Intended use

- Learn about prognostics, time-series feature engineering, and engine-level evaluation.
- Inspect model behavior through a fleet view and historical replay.
- Reproduce and extend a CPU-friendly benchmark experiment.

## Excluded uses

This model has not been validated on real aircraft. It cannot establish airworthiness, authorize operation, determine an actual maintenance interval, or replace qualified engineering judgment. The dashboard's priority categories are demonstration rules.

## Training data and evaluation population

The project uses NASA C-MAPSS FD001. Its 100 complete training trajectories are split into 60 fitting, 20 validation, and 20 calibration engines using seed 42. After selection on validation MAE, the chosen configuration is fit on 80 engines; interval calibration uses the remaining 20. The official final benchmark contains 100 truncated test-engine endpoints.

FD001 describes a single simulated operating regime and high-pressure compressor degradation. It does not represent the variety of operating regimes, sensor failures, maintenance interventions, fleet types, and failure modes present in deployed aircraft. Data sources and rights are listed in [`DATA_LICENSE.md`](../DATA_LICENSE.md).

## Inputs and outputs

Inputs are the available cycle history and sensor readings. The 71 features contain operating age and five causal statistics from each of 14 fixed FD001 sensor channels, with a maximum 20-cycle trailing window. Engine identifiers, operating settings, and final lifetime are excluded from model inputs.

Outputs are a nonnegative point estimate, a nominal 90% split-conformal prediction interval, and sensor-group perturbation sensitivities at each engine's final available cycle. The sensitivity view remains fixed during historical replay and labels its endpoint. Prediction intervals are calibrated across endpoint observations; their nominal level is not a guarantee for a particular selected engine or across its replay history.

## Evaluation

Every model is evaluated at the same official test endpoints. MAE and RMSE are in cycles. The asymmetric NASA score penalizes overestimated lifetime more steeply; lower values are better for all three metrics. Interval coverage is the fraction of endpoint truths inside the displayed bounds, and mean width is in cycles. See [`docs/methods.md`](methods.md) for formulas and the precise protocol.

The age-only and Ridge baselines make it possible to judge whether sensor history and nonlinear modeling add useful accuracy. Test performance is reported without using the test labels for model selection. One run of one engine-level split does not establish robustness across seeds or benchmark variants.

## Limitations and known failure modes

- Early-life sensor readings may contain weak failure information; uncapped long RUL targets can be difficult to estimate.
- Sensor noise can produce predictions that rise temporarily despite advancing operating age. The model does not enforce monotonicity.
- A 20-engine calibration set produces a coarse, dataset-dependent interval width. Exchangeability with official test endpoints is an assumption to check, not a physical law.
- Sensor sensitivities can reflect correlation and implausible substitutions. They do not identify causes and are not additive attribution scores.
- Generalization outside FD001, to other failure modes, to new operating regimes, or to real sensors has not been measured.
- Aggregate endpoint error can hide poor performance for a specific engine or RUL range. The notebook exposes prediction scatter, residual spread, and engine-level rows to support inspection.

## Reproducibility and maintenance

The project provides cached prediction artifacts, a fitted estimator, deterministic training commands, source integrity validation, and an executed notebook. The downloaded raw archive is excluded from Git. The README explains how to regenerate artifacts and run focused tests.

Model artifacts should be regenerated together; mixing the model from one experiment with metrics or dashboard data from another can misrepresent results. Changes to data, features, split rules, target definitions, or libraries require a new evaluation. The application is a local research demonstration; no production monitoring or retraining policy is claimed.
