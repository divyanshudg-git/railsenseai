# MetroPT3 Leakage-Safe Benchmark

This workspace now includes a reproducible benchmark script for the MetroPT3 air-compressor dataset.

## What it does

- Generates 2-hour pre-failure labels
- Excludes active failure intervals from train/eval
- Builds engineered rolling-window features
- Runs leave-one-event-out validation over the 4 failures
- Benchmarks:
  - Random Forest
  - XGBoost
  - Isolation Forest anomaly baseline
  - A weighted ensemble
- Reports:
  - precision / recall / F1 / PR-AUC
  - event recall
  - false alerts per day
  - median lead time

## Run

```bash
python metropt3_benchmark.py
```

Outputs are written to `outputs/`.

The default run resamples the 10-second stream to `1min` before feature engineering so the benchmark finishes in a practical amount of time. To disable that and run on raw cadence:

```bash
python metropt3_benchmark.py --resample-rule none
```

## Notes

- The anomaly stage uses `IsolationForest` on engineered features because TensorFlow/PyTorch are not installed in this environment.
- The validation logic intentionally avoids random row-wise splits because that setup leaks future event structure and inflates results on this dataset.
