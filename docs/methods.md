# How EngineWatch measures remaining useful life

EngineWatch is a reproducible experiment on NASA's C-MAPSS FD001 benchmark. It asks: **given an engine's sensor history up to the current cycle, how many cycles remain before its simulated failure?** The application turns that experiment into an interactive fleet and engine-history viewer.

The benchmark uses simulated trajectories. These results describe the supplied benchmark and do not establish accuracy on physical aircraft.

## Data and prediction target

FD001 supplies 100 complete training trajectories and 100 truncated test trajectories. It contains one operating condition and one failure mode: high-pressure compressor degradation. Each observation has an engine identifier, an operating cycle, three operating settings, and 21 sensor measurements. [NASA dataset description](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data)

For complete training engine \(i\), the target at cycle \(t\) is:

\[
RUL_{i,t} = T_i - t,
\]

where \(T_i\) is that engine's final cycle. At a test endpoint, the supplied `RUL_FD001.txt` value is the truth. Earlier test-history labels, used only for retrospective replay, add the number of cycles between the selected cycle and the endpoint. Labels are **not capped**. Every reported metric uses raw cycles.

The data downloader uses the [NASA-attributed Zenodo archive](https://doi.org/10.5281/zenodo.15346912), records source checksums, and caches extracted files locally. Its archive integrity check, parser validation, and model training can run without paid services. The archive's [Zenodo metadata](https://zenodo.org/api/records/15346912) lists CC BY 4.0; code and data terms are documented separately in `DATA_LICENSE.md`.

## Split by engine, before training

Rows from the same engine are correlated. A random row split would let one engine's late-life history inform predictions for that same engine in evaluation. Instead, a seeded shuffle of the 100 complete engines assigns whole engines to three roles:

| Role | Engines | Used for |
|---|---:|---|
| Fit | 60 | Learning model parameters |
| Validation | 20 | Selecting a model/configuration |
| Calibration | 20 | Estimating the prediction-interval width |
| Official test | 100 | Final independent benchmark measurements |

The seed is 42. Engine membership and actual configurations are saved in `artifacts/results.json`. The chosen model is refit on the 80 fit and validation engines. The 20 calibration engines remain independent of that final fit. The official test labels do not choose the model, its hyperparameters, or interval width.

Validation and calibration use one reproducibly sampled truncated endpoint per engine, rather than counting hundreds of strongly correlated cycle rows as independent calibration observations. Endpoints are sampled uniformly from cycle 30 through `min(250, lifetime - 1)`, using seeds 43 and 44 respectively. This creates an endpoint-oriented comparison with the official truncated test histories without consulting the official test truncation distribution. The exact implementation is in `src/enginewatch/train.py` and the sampled endpoints are recorded in the saved results.

## Features use information available at the prediction cycle

The pipeline uses operating age and 14 fixed FD001 sensor channels: 2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, and 21. Each channel contributes five features:

1. Current reading.
2. Trailing mean over at most 20 cycles.
3. Trailing standard deviation, with population denominator (`ddof=0`).
4. Change from the oldest available reading in the trailing window, divided by its cycle span.
5. Deviation from the mean of the first five available readings; this reference is frozen once five readings exist.

Together with operating age, this gives **71 features**. The channels are fixed by the FD001 recipe before any test evaluation. Operating settings are not predictors in this single-regime experiment. Features at cycle \(t\) use observations at or before \(t\); early windows contain only the history that exists. An engine's final lifetime never enters the feature matrix.

Any learned preprocessing parameters are fit on the designated fitting engines. Engine IDs are grouping keys, not predictors. The feature names and selected training configuration are included with the saved model and results.

## Three models, a common evaluation

- **Age baseline:** predicts equal-engine mean lifetime minus observed age, clipped at zero. It establishes the error attainable without interpreting sensor history.
- **Ridge regression:** combines sensor and trend features linearly, with regularization and learned feature scaling.
- **Histogram gradient boosting:** learns nonlinear interactions between features using a small bounded search over CPU-friendly configurations.

Validation MAE determines the selected configuration. All three comparison models are evaluated on the same 100 official test endpoints. Negative lifetime estimates are clipped at zero, since negative remaining lifetime has no meaning here. This is not a claim that model predictions must decrease monotonically over time; noisy observations can make replay estimates increase between cycles.

Every fitting engine contributes the same total sample weight; per-cycle weights are inversely proportional to the engine's trajectory length and normalized to mean one. The Ridge scaler and estimator both receive these weights. This prevents long-lived engines from contributing more total loss merely because their histories have more observations.

The selected histogram gradient booster uses 240 iterations, up to 31 leaves, learning rate 0.07, L2 regularization 10, and minimum leaf size 25. Automatic early stopping is disabled to keep the declared validation population in control of selection. Its validation MAE is 27.07 cycles, versus 27.34 for Ridge. On the official test endpoints it achieves MAE 14.83 and RMSE 21.48 cycles. Ridge has the better asymmetric NASA score (2,151.19 versus 2,439.53), a reminder that the best model depends on the evaluation objective.

## Metric definitions

Let \(e_i=\widehat{RUL}_i-RUL_i\) for each official test endpoint, with \(n=100\).

\[
MAE = \frac{1}{n}\sum_i |e_i|,
\qquad
RMSE = \sqrt{\frac{1}{n}\sum_i e_i^2}.
\]

Both are reported in operating cycles. MAE is the average absolute miss; RMSE gives more weight to large misses. The asymmetric PHM/NASA score is:

\[
S=\sum_i
\begin{cases}
\exp(-e_i/13)-1,&e_i<0\\
\exp(e_i/10)-1,&e_i\geq0.
\end{cases}
\]

The score is dimensionless, summed over the fleet, and lower is better. Overestimating remaining life receives a steeper penalty than underestimating it. It is a comparison metric, not an economic cost or certified maintenance policy. The originating benchmark is described by Saxena et al., *Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation* (PHM 2008), cited in the [NASA catalogue](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data).

The companion notebook independently recomputes these metrics from the exported test predictions, then compares them with the saved results. A summary JSON alone is not treated as verification.

## A prediction interval with a visible empirical check

The selected model predicts one endpoint from each of 20 withheld calibration engines. Absolute calibration residuals determine a split-conformal half-width. For nominal coverage \(1-\alpha=0.90\), the finite-sample rank is:

\[
k=\lceil(n_{cal}+1)(1-\alpha)\rceil.
\]

With 20 calibration observations, \(k=19\). The width is the 19th ordered absolute residual. Each prediction uses \([\max(0,\widehat{RUL}-q),\widehat{RUL}+q]\). Clipping the lower bound at zero reflects the nonnegative target.

The application reports **nominal coverage, measured test-endpoint coverage, and mean interval width**. The prediction interval refers to possible RUL values; it is not a confidence interval for the model's average error.

In the shipped run, the radius is **56.14 cycles**, actual endpoint coverage is **97/100**, and mean displayed width is **101.69 cycles**. The intervals are broad and conservative on this test set. This is evidence of measured coverage alongside limited precision, not an exceptionally tight forecast.

The distribution-free coverage argument requires exchangeability of calibration and future observations. Randomly truncated training engines and official test engines may differ. With only 20 calibration engines, the width is also coarse and sensitive to individual residuals. Measured test coverage is therefore shown prominently, and a replay-wide or per-engine guarantee is not asserted. Repeated cycles from a selected engine are not 100 independent tests.

## Explanations are sensor sensitivity

At each test engine's terminal available cycle, the application replaces a sensor's feature group with the fitting-data medians and compares the resulting prediction with the original prediction. The change is displayed in cycles. The view asks: **how does this endpoint prediction change when this sensor group is replaced with a typical training value?** The view labels that endpoint cycle and remains fixed while the historical replay moves through earlier cycles.

These are perturbation sensitivities, not causal effects or SHAP values. Sensors are correlated; independent substitutions can create combinations that were rare in training. Effects do not necessarily sum to the prediction. The model may respond to several sensors that measure related conditions, and a large sensitivity does not prove a physical fault mechanism.

## Application and artifact boundaries

The app loads a precomputed, versioned demo artifact. It shows the same fitted model's predictions, intervals, and sensor histories at every available test cycle, alongside a separate terminal-cycle sensitivity view. The official endpoint leaderboard remains separate from this retrospective replay. Threshold categories are illustrative display rules; the app does not optimize a maintenance schedule.

`models/model.joblib` contains the fitted Python estimator. Only load trusted model files: the underlying joblib/pickle format can execute code when loaded. Ordinary app browsing reads the JSON demo artifact and does not require retraining.

## Reproduce and extend

Run `python -m enginewatch.train` from the repository after installing it. The default run downloads or reuses FD001, regenerates the trained model and evaluation artifacts, and writes the dashboard data. See the README for environment setup, tests, and the executed notebook.

A useful next experiment would evaluate FD002/FD004 operating-regime variation, compare several engine-level seeds, and report calibration sensitivity before adding model complexity. Any real-equipment study would need a different validation protocol, representative failure data, and operational review.
