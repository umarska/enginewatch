# Validation record

The delivered experiment was checked on 5 October 2026 using Windows, Python 3.12, scikit-learn 1.9.1, and the versions in `requirements-lock.txt`.

## Executed checks

- **25 automated checks passed.** These cover causal feature invariance when future readings are appended, independent engine splits, calibration rank correction, the asymmetric NASA score, malformed uploads, numerical overflow, model/artifact consistency, prediction exports, and application routes.
- The official test labels and terminal cycles were independently reconciled against all 100 exported prediction rows.
- MAE, RMSE, NASA score, interval radius, coverage, and mean width were independently recalculated from the committed artifacts.
- Training completed twice after the final model/provenance changes with unchanged reported metrics. The final run used two CPU threads and completed in approximately 50 seconds in the tested environment.
- The analysis notebook executed from top to bottom: 12 code cells, no execution errors. Its four exported plots were visually inspected.
- The JavaScript syntax check passed.

## Browser verification

The Flask app ran at `http://127.0.0.1:5050` and was exercised in Chromium through the Codex browser.

- Fleet search isolated engine 003 from the 100-engine test fleet.
- Engine replay updated the forecast, interval, chart marker, and revealed benchmark truth at earlier cycles. Sensor selection changed the measured sensor chart. Play and pause controls worked.
- Terminal sensor sensitivity stayed tied to the labeled terminal observation during replay.
- The benchmark view showed all three models, the Ridge NASA-score tradeoff, and the broad interval width alongside measured coverage.
- Invalid pasted input produced an explanatory validation message.
- Uploading `data/examples/sample.csv` through the file chooser produced a 31-cycle engine history and a terminal prediction of approximately 176 cycles with a 120–232 cycle interval. Benchmark truth was unavailable for uploaded data.
- Desktop layout at 1440 pixels and a narrow layout at approximately 412 pixels were inspected. The narrow document had no horizontal overflow.
- No browser console errors or warnings were captured during these checks.

The [application preview](app-preview.jpg) shows engine 003 at replay cycle 90, while its sensitivity panel explicitly refers to terminal cycle 126.

## Execution limits

The Dockerfile is supplied and its commands were reviewed, but Docker was unavailable in the local environment and the container was **not executed**. Other operating systems and Python versions were not locally tested. GitHub Actions provides the additional clean-environment test run; consult the repository's Actions page for its actual status.

This record verifies the supplied software and experiment. It does not establish performance on physical engines, operational safety, coverage for individual engines, or generalization beyond the simulated FD001 regime.
