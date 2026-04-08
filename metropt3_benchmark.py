#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


WARNING_HOURS = 2
VALIDATION_CONTEXT_DAYS = 7
RANDOM_STATE = 42
CONTINUOUS_SENSORS = [
    "H1",
    "TP2",
    "Oil_temperature",
    "DV_pressure",
    "Motor_current",
]
ADDITIONAL_CONTINUOUS = ["TP3", "Reservoirs"]
BINARY_SENSORS = [
    "COMP",
    "DV_eletric",
    "Towers",
    "MPG",
    "LPS",
    "Pressure_switch",
    "Oil_level",
    "Caudal_impulses",
]
WINDOW_MINUTES = [1, 5, 15, 30, 60]


@dataclass
class FoldResult:
    fold_name: str
    event_id: int
    model_name: str
    threshold: float
    row_metrics: Dict[str, float]
    event_metrics: Dict[str, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Leakage-safe MetroPT3 benchmark pipeline")
    parser.add_argument(
        "--sensor-csv",
        default="MetroPT3_AirCompressor.csv",
        help="Path to MetroPT3 sensor data CSV",
    )
    parser.add_argument(
        "--events-csv",
        default="failure_events.csv",
        help="Path to failure events CSV",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory where metrics and alerts will be written",
    )
    parser.add_argument(
        "--resample-rule",
        default="1min",
        help="Optional pandas resample rule to speed up the benchmark, for example 1min. Use 'none' to disable.",
    )
    return parser.parse_args()


def sigmoid_scale(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    std = values.std()
    if std == 0 or np.isnan(std):
        return np.full_like(values, 0.5, dtype=float)
    z = (values - values.mean()) / std
    return 1.0 / (1.0 + np.exp(-z))


def load_data(sensor_path: Path, events_path: Path, resample_rule: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    usecols = ["timestamp"] + CONTINUOUS_SENSORS + ADDITIONAL_CONTINUOUS + BINARY_SENSORS
    sensor_df = pd.read_csv(sensor_path, usecols=usecols, parse_dates=["timestamp"])
    sensor_df = sensor_df.sort_values("timestamp").reset_index(drop=True)
    events_df = pd.read_csv(events_path, parse_dates=["Start Time", "End Time"])
    events_df = events_df.sort_values("Start Time").reset_index(drop=True)
    events_df["event_id"] = np.arange(1, len(events_df) + 1)
    if resample_rule.lower() != "none":
        aggregations = {col: "mean" for col in CONTINUOUS_SENSORS + ADDITIONAL_CONTINUOUS}
        aggregations.update({col: "last" for col in BINARY_SENSORS})
        sensor_df = (
            sensor_df.set_index("timestamp")
            .resample(resample_rule)
            .agg(aggregations)
            .dropna()
            .reset_index()
        )
    return sensor_df, events_df


def add_interactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["tp2_tp3_gap"] = df["TP2"] - df["TP3"]
    df["pressure_reservoir_gap"] = df["DV_pressure"] - df["Reservoirs"]
    df["pressure_current_ratio"] = df["DV_pressure"] / (df["Motor_current"].abs() + 1e-3)
    df["temp_current_product"] = df["Oil_temperature"] * df["Motor_current"]
    return df


def infer_sampling_seconds(df: pd.DataFrame) -> int:
    deltas = df["timestamp"].diff().dt.total_seconds().dropna()
    if deltas.empty:
        return 60
    return int(deltas.mode().iloc[0])


def build_windows(df: pd.DataFrame) -> Dict[str, int]:
    sampling_seconds = max(infer_sampling_seconds(df), 1)
    windows = {}
    for minutes in WINDOW_MINUTES:
        steps = max(int((minutes * 60) / sampling_seconds), 1)
        windows[f"{minutes}m"] = steps
    return windows


def compute_run_length(values: np.ndarray) -> np.ndarray:
    run = np.zeros(len(values), dtype=np.int32)
    if len(values) == 0:
        return run
    run[0] = 1
    for i in range(1, len(values)):
        run[i] = run[i - 1] + 1 if values[i] == values[i - 1] else 1
    return run


def compute_time_since_change(values: np.ndarray) -> np.ndarray:
    distance = np.zeros(len(values), dtype=np.int32)
    last_change = 0
    for i in range(1, len(values)):
        if values[i] != values[i - 1]:
            last_change = i
        distance[i] = i - last_change
    return distance


def engineer_features(sensor_df: pd.DataFrame) -> pd.DataFrame:
    df = add_interactions(sensor_df)
    windows = build_windows(df)
    feature_map: Dict[str, pd.Series] = {"timestamp": df["timestamp"]}

    continuous = CONTINUOUS_SENSORS + ADDITIONAL_CONTINUOUS + [
        "tp2_tp3_gap",
        "pressure_reservoir_gap",
        "pressure_current_ratio",
        "temp_current_product",
    ]

    for col in continuous:
        feature_map[f"{col}_value"] = df[col]

    for window_name, window_size in windows.items():
        for col in continuous:
            rolling = df[col].rolling(window=window_size, min_periods=window_size)
            feature_map[f"{col}_{window_name}_mean"] = rolling.mean()
            feature_map[f"{col}_{window_name}_std"] = rolling.std()
            feature_map[f"{col}_{window_name}_min"] = rolling.min()
            feature_map[f"{col}_{window_name}_max"] = rolling.max()
            if col in CONTINUOUS_SENSORS:
                feature_map[f"{col}_{window_name}_slope"] = (
                    df[col] - df[col].shift(window_size - 1)
                ) / max(window_size - 1, 1)
                feature_map[f"{col}_{window_name}_delta_mean"] = rolling.mean().diff(window_size)
                feature_map[f"{col}_{window_name}_ewm"] = (
                    df[col].ewm(span=window_size, adjust=False).mean()
                )

        for col in BINARY_SENSORS:
            transitions = df[col].diff().abs().fillna(0)
            feature_map[f"{col}_{window_name}_duty_cycle"] = (
                df[col].rolling(window=window_size, min_periods=window_size).mean()
            )
            feature_map[f"{col}_{window_name}_transition_count"] = (
                transitions.rolling(window=window_size, min_periods=window_size).sum()
            )

    for col in BINARY_SENSORS:
        values = df[col].to_numpy(dtype=np.int8)
        feature_map[f"{col}_run_length"] = pd.Series(compute_run_length(values))
        feature_map[f"{col}_time_since_change"] = pd.Series(compute_time_since_change(values))

    minutes = (
        df["timestamp"].dt.hour.astype(float) * 60.0 + df["timestamp"].dt.minute.astype(float)
    )
    angle = 2 * np.pi * minutes / (24.0 * 60.0)
    feature_map["hour_sin"] = pd.Series(np.sin(angle))
    feature_map["hour_cos"] = pd.Series(np.cos(angle))
    feature_map["compressor_active"] = df["COMP"].astype(int)
    feature_map["mode_stability_15m"] = (
        df["COMP"].rolling(window=windows["15m"], min_periods=windows["15m"]).mean()
    )

    return pd.DataFrame(feature_map)


def create_labels(df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    labels = pd.DataFrame(index=df.index)
    labels["timestamp"] = df["timestamp"]
    labels["target"] = 0
    labels["failure_active"] = 0
    labels["event_id"] = 0

    for _, row in events_df.iterrows():
        start_time = row["Start Time"]
        end_time = row["End Time"]
        pre_start = start_time - pd.Timedelta(hours=WARNING_HOURS)
        pre_mask = (df["timestamp"] >= pre_start) & (df["timestamp"] < start_time)
        active_mask = (df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)
        labels.loc[pre_mask, "target"] = 1
        labels.loc[pre_mask, "event_id"] = int(row["event_id"])
        labels.loc[active_mask, "failure_active"] = 1
        labels.loc[active_mask, "event_id"] = int(row["event_id"])

    return labels


def build_model_features(feature_df: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    merged = feature_df.join(labels[["target", "failure_active", "event_id"]])
    merged = merged.iloc[max(build_windows(feature_df).values()) :].reset_index(drop=True)
    return merged


def get_validation_mask(
    timestamps: pd.Series,
    event_start: pd.Timestamp,
    event_end: pd.Timestamp,
) -> pd.Series:
    start = event_start - pd.Timedelta(hours=WARNING_HOURS) - pd.Timedelta(days=VALIDATION_CONTEXT_DAYS)
    end = event_end + pd.Timedelta(days=VALIDATION_CONTEXT_DAYS)
    return (timestamps >= start) & (timestamps <= end)


def prepare_fold_masks(
    dataset: pd.DataFrame,
    events_df: pd.DataFrame,
    held_out_event_id: int,
) -> Tuple[pd.Series, pd.Series]:
    event_row = events_df.loc[events_df["event_id"] == held_out_event_id].iloc[0]
    validation_mask = get_validation_mask(dataset["timestamp"], event_row["Start Time"], event_row["End Time"])
    train_mask = ~validation_mask
    train_mask &= dataset["failure_active"].eq(0)
    validation_mask &= dataset["failure_active"].eq(0)
    return train_mask, validation_mask


def feature_columns(dataset: pd.DataFrame) -> List[str]:
    excluded = {"timestamp", "target", "failure_active", "event_id"}
    return [col for col in dataset.columns if col not in excluded]


def fit_supervised_models(
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> Dict[str, object]:
    pos = int(y_train.sum())
    neg = max(len(y_train) - pos, 1)
    scale_pos_weight = max(neg / max(pos, 1), 1.0)

    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=14,
        min_samples_leaf=8,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=1,
    )
    rf.fit(X_train, y_train)

    xgb = XGBClassifier(
        n_estimators=350,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.8,
        reg_lambda=1.5,
        min_child_weight=3,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE,
        n_jobs=1,
    )
    xgb.fit(X_train, y_train)

    return {"random_forest": rf, "xgboost": xgb}


def fit_anomaly_model(X_train: pd.DataFrame, y_train: pd.Series) -> Tuple[StandardScaler, IsolationForest]:
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    normal_mask = y_train.eq(0).to_numpy()
    iso = IsolationForest(
        n_estimators=250,
        contamination=0.01,
        random_state=RANDOM_STATE,
        n_jobs=1,
    )
    iso.fit(X_train_scaled[normal_mask])
    return scaler, iso


def find_best_threshold(y_true: np.ndarray, scores: np.ndarray) -> float:
    candidate_thresholds = np.unique(np.quantile(scores, np.linspace(0.80, 0.995, 80)))
    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in candidate_thresholds:
        preds = (scores >= threshold).astype(int)
        current_f1 = f1_score(y_true, preds, zero_division=0)
        if current_f1 > best_f1:
            best_f1 = current_f1
            best_threshold = float(threshold)
    return best_threshold


def row_metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> Dict[str, float]:
    preds = (scores >= threshold).astype(int)
    return {
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds, zero_division=0)),
        "f1": float(f1_score(y_true, preds, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, scores)),
    }


def alert_episodes(pred_df: pd.DataFrame) -> pd.DataFrame:
    alerts = pred_df.loc[pred_df["alert"].eq(1)].copy()
    if alerts.empty:
        return pd.DataFrame(columns=["episode_id", "start", "end", "peak_risk"])

    gap = alerts["timestamp"].diff().dt.total_seconds().fillna(10)
    alerts["episode_id"] = (gap > 10).cumsum()
    episodes = (
        alerts.groupby("episode_id")
        .agg(
            start=("timestamp", "min"),
            end=("timestamp", "max"),
            peak_risk=("risk_score", "max"),
        )
        .reset_index()
    )
    return episodes


def event_metrics(
    pred_df: pd.DataFrame,
    events_df: pd.DataFrame,
    held_out_event_id: int,
) -> Tuple[Dict[str, float], pd.DataFrame]:
    episodes = alert_episodes(pred_df)
    event_row = events_df.loc[events_df["event_id"] == held_out_event_id].iloc[0]
    warning_start = event_row["Start Time"] - pd.Timedelta(hours=WARNING_HOURS)
    warning_end = event_row["Start Time"]

    caught = False
    lead_time_minutes = np.nan
    if not episodes.empty:
        matching = episodes.loc[(episodes["start"] >= warning_start) & (episodes["start"] < warning_end)]
        if not matching.empty:
            caught = True
            lead_time_minutes = (
                event_row["Start Time"] - matching["start"].min()
            ).total_seconds() / 60.0

    false_episodes = 0
    if not episodes.empty:
        for row in episodes.itertuples(index=False):
            if not (warning_start <= row.start < warning_end):
                false_episodes += 1

    total_days = max(
        (pred_df["timestamp"].max() - pred_df["timestamp"].min()).total_seconds() / 86400.0,
        1e-6,
    )
    metrics = {
        "event_recall": float(caught),
        "median_lead_time_minutes": float(lead_time_minutes) if caught else None,
        "false_alerts_per_day": float(false_episodes / total_days),
        "caught_event": int(caught),
    }
    return metrics, episodes


def evaluate_fold(
    dataset: pd.DataFrame,
    events_df: pd.DataFrame,
    held_out_event_id: int,
    columns: List[str],
) -> Tuple[List[FoldResult], Dict[str, pd.DataFrame]]:
    train_mask, validation_mask = prepare_fold_masks(dataset, events_df, held_out_event_id)
    train_df = dataset.loc[train_mask].copy()
    valid_df = dataset.loc[validation_mask].copy()

    X_train = train_df[columns].fillna(0.0)
    y_train = train_df["target"].astype(int)
    X_valid = valid_df[columns].fillna(0.0)
    y_valid = valid_df["target"].astype(int).to_numpy()

    supervised_models = fit_supervised_models(X_train, y_train)
    scaler, anomaly_model = fit_anomaly_model(X_train, y_train)

    predictions: Dict[str, pd.DataFrame] = {}
    fold_results: List[FoldResult] = []

    rf_scores = supervised_models["random_forest"].predict_proba(X_valid)[:, 1]
    xgb_scores = supervised_models["xgboost"].predict_proba(X_valid)[:, 1]
    anomaly_raw = -anomaly_model.score_samples(scaler.transform(X_valid))
    anomaly_scores = sigmoid_scale(anomaly_raw)
    ensemble_scores = (0.50 * xgb_scores) + (0.25 * rf_scores) + (0.25 * anomaly_scores)

    score_map = {
        "random_forest": rf_scores,
        "xgboost": xgb_scores,
        "isolation_forest": anomaly_scores,
        "ensemble": ensemble_scores,
    }

    for model_name, scores in score_map.items():
        threshold = find_best_threshold(y_valid, scores)
        pred_df = valid_df[["timestamp", "target", "event_id"]].copy()
        pred_df["risk_score"] = scores
        pred_df["alert"] = (scores >= threshold).astype(int)
        row = row_metrics(y_valid, scores, threshold)
        event, episodes = event_metrics(pred_df, events_df, held_out_event_id)
        fold_results.append(
            FoldResult(
                fold_name=f"event_{held_out_event_id}",
                event_id=held_out_event_id,
                model_name=model_name,
                threshold=threshold,
                row_metrics=row,
                event_metrics=event,
            )
        )
        predictions[model_name] = pred_df

    return fold_results, predictions


def aggregate_results(results: Iterable[FoldResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        rows.append(
            {
                "fold_name": result.fold_name,
                "event_id": result.event_id,
                "model_name": result.model_name,
                "threshold": result.threshold,
                **result.row_metrics,
                **result.event_metrics,
            }
        )
    df = pd.DataFrame(rows)
    summary = (
        df.groupby("model_name")
        .agg(
            precision=("precision", "mean"),
            recall=("recall", "mean"),
            f1=("f1", "mean"),
            pr_auc=("pr_auc", "mean"),
            event_recall=("event_recall", "mean"),
            false_alerts_per_day=("false_alerts_per_day", "mean"),
            median_lead_time_minutes=("median_lead_time_minutes", "median"),
            mean_threshold=("threshold", "mean"),
        )
        .reset_index()
        .sort_values(["f1", "event_recall", "pr_auc"], ascending=False)
    )
    return df, summary


def write_outputs(
    output_dir: Path,
    feature_dataset: pd.DataFrame,
    fold_details: pd.DataFrame,
    summary: pd.DataFrame,
    predictions_by_model: Dict[str, List[pd.DataFrame]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_dataset.head(2000).to_csv(output_dir / "feature_sample.csv", index=False)
    fold_details.to_csv(output_dir / "fold_metrics.csv", index=False)
    summary.to_csv(output_dir / "model_summary.csv", index=False)
    for model_name, frames in predictions_by_model.items():
        pd.concat(frames, ignore_index=True).to_csv(output_dir / f"{model_name}_alerts.csv", index=False)
    payload = {
        "summary": summary.to_dict(orient="records"),
        "folds": fold_details.to_dict(orient="records"),
    }
    (output_dir / "benchmark_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    sensor_path = Path(args.sensor_csv)
    events_path = Path(args.events_csv)
    output_dir = Path(args.output_dir)

    sensor_df, events_df = load_data(sensor_path, events_path, args.resample_rule)
    feature_df = engineer_features(sensor_df)
    labels_df = create_labels(sensor_df[["timestamp"]], events_df)
    dataset = build_model_features(feature_df, labels_df)
    columns = feature_columns(dataset)

    all_fold_results: List[FoldResult] = []
    predictions_by_model: Dict[str, List[pd.DataFrame]] = {
        "random_forest": [],
        "xgboost": [],
        "isolation_forest": [],
        "ensemble": [],
    }

    for event_id in events_df["event_id"]:
        fold_results, predictions = evaluate_fold(dataset, events_df, int(event_id), columns)
        all_fold_results.extend(fold_results)
        for model_name, pred_df in predictions.items():
            pred_df["held_out_event_id"] = int(event_id)
            predictions_by_model[model_name].append(pred_df)

    fold_details, summary = aggregate_results(all_fold_results)
    write_outputs(output_dir, dataset, fold_details, summary, predictions_by_model)

    print("Benchmark complete.")
    print(summary.to_string(index=False))
    print(f"Outputs written to {output_dir.resolve()}")


if __name__ == "__main__":
    main()
