#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MetroPT3 Kaggle TPU Hybrid Benchmark
====================================

Notebook-ready script for Kaggle that:
1. Auto-detects the uploaded MetroPT3 CSVs.
2. Builds leakage-safe 2-hour pre-failure labels.
3. Engineers regime-aware rolling features on 1-minute data.
4. Trains a supervised XGBoost ranker.
5. Trains a TPU-friendly temporal autoencoder on normal sequences.
6. Blends both scores and applies alert smoothing.
7. Reports fold-wise and aggregate metrics.

Notes
-----
- This script is designed to be pasted into a Kaggle notebook or uploaded as a
  utility file. It is not executed here.
- TPU is used for the sequence autoencoder. XGBoost still runs on CPU.
- The default objective is balanced F1 with event recall and false alerts/day.
- Threshold selection is train-only, but for a stricter benchmark you can later
  replace it with an inner leave-one-event-out calibration stage.
"""

from __future__ import annotations

import gc
import json
import math
import os
import random
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import RobustScaler
from xgboost import XGBClassifier

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

warnings.filterwarnings("ignore")


SEED = 42
WARNING_HOURS = 2
VALIDATION_CONTEXT_DAYS = 7
WARMUP_ROWS = 60

CONTINUOUS_SENSORS = [
    "TP2",
    "TP3",
    "H1",
    "DV_pressure",
    "Reservoirs",
    "Oil_temperature",
    "Motor_current",
]

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

WINDOW_MINUTES = [3, 5, 15, 30, 60]


@dataclass
class Config:
    sensor_csv_name: str = "MetroPT3_AirCompressor.csv"
    events_csv_name: str = "failure_events.csv"
    resample_rule: str = "1min"
    output_dir: str = "/kaggle/working/metropt3_hybrid_outputs"
    sequence_length: int = 120
    train_sequence_stride: int = 5
    valid_sequence_stride: int = 1
    max_normal_sequences: int = 50000
    supervised_weight: float = 0.68
    anomaly_weight: float = 0.22
    isolation_weight: float = 0.10
    train_alert_budget_per_day: float = 8.0
    alert_persistence: int = 3
    alert_cooldown_minutes: int = 45
    xgb_estimators: int = 700
    xgb_max_depth: int = 6
    xgb_learning_rate: float = 0.03
    xgb_subsample: float = 0.85
    xgb_colsample: float = 0.80
    xgb_min_child_weight: float = 4.0
    xgb_reg_lambda: float = 2.0
    ae_epochs: int = 30
    ae_batch_size_per_replica: int = 64
    ae_learning_rate: float = 3e-4


@dataclass
class FoldResult:
    fold_name: str
    event_id: int
    threshold: float
    precision: float
    recall: float
    f1: float
    pr_auc: float
    event_recall: float
    false_alerts_per_day: float
    median_lead_time_minutes: Optional[float]
    caught_event: int


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def find_input_file(filename: str) -> Path:
    search_roots = [Path("/kaggle/input"), Path("/kaggle/working"), Path(".")]
    for root in search_roots:
        if not root.exists():
            continue
        matches = list(root.rglob(filename))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"Could not find {filename}. Make sure the Kaggle dataset is attached.")


def init_strategy() -> tf.distribute.Strategy:
    try:
        resolver = tf.distribute.cluster_resolver.TPUClusterResolver(tpu="local")
        tf.config.experimental_connect_to_cluster(resolver)
        tf.tpu.experimental.initialize_tpu_system(resolver)
        strategy = tf.distribute.TPUStrategy(resolver)
        keras.mixed_precision.set_global_policy("mixed_bfloat16")
        print(f"Connected to TPU with {strategy.num_replicas_in_sync} replicas")
        return strategy
    except Exception as exc:
        print(f"TPU not available, using default strategy instead. Reason: {exc}")
        return tf.distribute.get_strategy()


def load_data(cfg: Config) -> Tuple[pd.DataFrame, pd.DataFrame]:
    sensor_path = find_input_file(cfg.sensor_csv_name)
    events_path = find_input_file(cfg.events_csv_name)

    usecols = ["timestamp"] + CONTINUOUS_SENSORS + BINARY_SENSORS
    sensor_df = pd.read_csv(sensor_path, usecols=usecols, parse_dates=["timestamp"])
    sensor_df = sensor_df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    events_df = pd.read_csv(events_path, parse_dates=["Start Time", "End Time"])
    events_df = events_df.sort_values("Start Time").reset_index(drop=True)
    events_df["event_id"] = np.arange(1, len(events_df) + 1)

    if cfg.resample_rule.lower() != "none":
        agg = {col: "mean" for col in CONTINUOUS_SENSORS}
        agg.update({col: "last" for col in BINARY_SENSORS})
        sensor_df = (
            sensor_df.set_index("timestamp")
            .resample(cfg.resample_rule)
            .agg(agg)
            .dropna()
            .reset_index()
        )
        for col in BINARY_SENSORS:
            sensor_df[col] = sensor_df[col].round().clip(0, 1).astype("int8")

    return sensor_df, events_df


def infer_sampling_minutes(sensor_df: pd.DataFrame) -> int:
    deltas = sensor_df["timestamp"].diff().dt.total_seconds().dropna()
    if deltas.empty:
        return 1
    minutes = max(int(round(float(deltas.mode().iloc[0]) / 60.0)), 1)
    return minutes


def build_windows(sensor_df: pd.DataFrame) -> Dict[str, int]:
    sampling_minutes = infer_sampling_minutes(sensor_df)
    windows = {}
    for minutes in WINDOW_MINUTES:
        windows[f"{minutes}m"] = max(int(minutes / sampling_minutes), 1)
    return windows


def compute_run_length(values: np.ndarray) -> np.ndarray:
    out = np.zeros(len(values), dtype=np.int32)
    if len(values) == 0:
        return out
    out[0] = 1
    for idx in range(1, len(values)):
        out[idx] = out[idx - 1] + 1 if values[idx] == values[idx - 1] else 1
    return out


def compute_time_since_change(values: np.ndarray) -> np.ndarray:
    out = np.zeros(len(values), dtype=np.int32)
    last_change = 0
    for idx in range(1, len(values)):
        if values[idx] != values[idx - 1]:
            last_change = idx
        out[idx] = idx - last_change
    return out


def add_physics_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["tp2_tp3_gap"] = out["TP2"] - out["TP3"]
    out["h1_tp3_gap"] = out["H1"] - out["TP3"]
    out["pressure_reservoir_gap"] = out["DV_pressure"] - out["Reservoirs"]
    out["pressure_current_ratio"] = out["DV_pressure"] / (out["Motor_current"].abs() + 1e-3)
    out["temp_current_product"] = out["Oil_temperature"] * out["Motor_current"]
    out["compressor_efficiency"] = (out["TP2"] - out["TP3"]) / (out["Motor_current"].abs() + 1e-3)
    out["thermal_margin"] = out["Oil_temperature"] - out["Oil_temperature"].rolling(60, min_periods=1).median()
    out["pressure_drop_if_on"] = out["COMP"] * (out["TP3"] - out["TP2"])
    out["motor_if_on"] = out["COMP"] * out["Motor_current"]
    return out


def engineer_features(sensor_df: pd.DataFrame) -> pd.DataFrame:
    df = add_physics_features(sensor_df)
    windows = build_windows(sensor_df)

    continuous = CONTINUOUS_SENSORS + [
        "tp2_tp3_gap",
        "h1_tp3_gap",
        "pressure_reservoir_gap",
        "pressure_current_ratio",
        "temp_current_product",
        "compressor_efficiency",
        "thermal_margin",
        "pressure_drop_if_on",
        "motor_if_on",
    ]

    feature_map: Dict[str, pd.Series] = {"timestamp": df["timestamp"]}

    for col in continuous:
        feature_map[f"{col}_value"] = df[col]
        feature_map[f"{col}_delta_1"] = df[col].diff()
        feature_map[f"{col}_delta_5"] = df[col].diff(5)

    for window_name, window_steps in windows.items():
        for col in continuous:
            rolling = df[col].rolling(window=window_steps, min_periods=window_steps)
            feature_map[f"{col}_{window_name}_mean"] = rolling.mean()
            feature_map[f"{col}_{window_name}_std"] = rolling.std()
            feature_map[f"{col}_{window_name}_min"] = rolling.min()
            feature_map[f"{col}_{window_name}_max"] = rolling.max()
            feature_map[f"{col}_{window_name}_median"] = rolling.median()
            feature_map[f"{col}_{window_name}_range"] = rolling.max() - rolling.min()
            feature_map[f"{col}_{window_name}_zscore"] = (
                (df[col] - rolling.mean()) / (rolling.std() + 1e-6)
            )
            feature_map[f"{col}_{window_name}_slope"] = (
                df[col] - df[col].shift(window_steps - 1)
            ) / max(window_steps - 1, 1)

        for col in BINARY_SENSORS:
            transitions = df[col].diff().abs().fillna(0)
            feature_map[f"{col}_{window_name}_duty_cycle"] = (
                df[col].rolling(window_steps, min_periods=window_steps).mean()
            )
            feature_map[f"{col}_{window_name}_transition_count"] = (
                transitions.rolling(window_steps, min_periods=window_steps).sum()
            )

    for col in BINARY_SENSORS:
        values = df[col].fillna(0).astype("int8").to_numpy()
        feature_map[f"{col}_run_length"] = pd.Series(compute_run_length(values))
        feature_map[f"{col}_time_since_change"] = pd.Series(compute_time_since_change(values))

    minutes = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    angle = 2.0 * math.pi * minutes / (24.0 * 60.0)
    feature_map["hour_sin"] = np.sin(angle)
    feature_map["hour_cos"] = np.cos(angle)
    feature_map["is_night_shift"] = ((df["timestamp"].dt.hour < 6) | (df["timestamp"].dt.hour >= 22)).astype(int)
    feature_map["comp_active"] = df["COMP"].astype(int)
    feature_map["comp_and_mpg_agree"] = (df["COMP"].astype(int) == df["MPG"].astype(int)).astype(int)

    feat_df = pd.DataFrame(feature_map)
    feat_df = feat_df.replace([np.inf, -np.inf], np.nan)
    return feat_df


def create_labels(sensor_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    labels = pd.DataFrame(index=sensor_df.index)
    labels["timestamp"] = sensor_df["timestamp"]
    labels["target"] = 0
    labels["failure_active"] = 0
    labels["event_id"] = 0

    for _, row in events_df.iterrows():
        start_time = row["Start Time"]
        end_time = row["End Time"]
        event_id = int(row["event_id"])
        pre_start = start_time - pd.Timedelta(hours=WARNING_HOURS)

        pre_mask = (sensor_df["timestamp"] >= pre_start) & (sensor_df["timestamp"] < start_time)
        active_mask = (sensor_df["timestamp"] >= start_time) & (sensor_df["timestamp"] <= end_time)

        labels.loc[pre_mask, "target"] = 1
        labels.loc[pre_mask, "event_id"] = event_id
        labels.loc[active_mask, "failure_active"] = 1
        labels.loc[active_mask, "event_id"] = event_id

    return labels


def build_dataset(feature_df: pd.DataFrame, labels_df: pd.DataFrame) -> pd.DataFrame:
    dataset = feature_df.join(labels_df[["target", "failure_active", "event_id"]])
    dataset = dataset.iloc[WARMUP_ROWS:].reset_index(drop=True)
    dataset = dataset.fillna(0.0)
    return dataset


def feature_columns(dataset: pd.DataFrame) -> List[str]:
    excluded = {"timestamp", "target", "failure_active", "event_id"}
    return [col for col in dataset.columns if col not in excluded]


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


def fit_supervised_model(X_train: pd.DataFrame, y_train: pd.Series, cfg: Config) -> XGBClassifier:
    pos = int(y_train.sum())
    neg = max(len(y_train) - pos, 1)
    scale_pos_weight = max(neg / max(pos, 1), 1.0)

    model = XGBClassifier(
        n_estimators=cfg.xgb_estimators,
        max_depth=cfg.xgb_max_depth,
        learning_rate=cfg.xgb_learning_rate,
        subsample=cfg.xgb_subsample,
        colsample_bytree=cfg.xgb_colsample,
        min_child_weight=cfg.xgb_min_child_weight,
        reg_lambda=cfg.xgb_reg_lambda,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        random_state=SEED,
        tree_method="hist",
        n_jobs=4,
    )
    model.fit(X_train, y_train)
    return model


def fit_isolation_forest(X_train: pd.DataFrame, y_train: pd.Series) -> Tuple[RobustScaler, IsolationForest]:
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X_train)
    normal_mask = y_train.eq(0).to_numpy()
    iso = IsolationForest(
        n_estimators=300,
        contamination=0.01,
        random_state=SEED,
        n_jobs=4,
    )
    iso.fit(X_scaled[normal_mask])
    return scaler, iso


def sequence_feature_columns() -> List[str]:
    return CONTINUOUS_SENSORS + [
        "tp2_tp3_gap",
        "pressure_reservoir_gap",
        "pressure_current_ratio",
        "compressor_efficiency",
        "thermal_margin",
        "pressure_drop_if_on",
    ]


def prepare_sequence_frame(sensor_df: pd.DataFrame) -> pd.DataFrame:
    return add_physics_features(sensor_df)[["timestamp"] + sequence_feature_columns()].copy()


def build_sequence_tensor(
    frame: pd.DataFrame,
    labels: pd.DataFrame,
    scaler: RobustScaler,
    seq_len: int,
    stride: int,
    normal_only: bool = False,
    max_sequences: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    value_cols = [col for col in frame.columns if col != "timestamp"]
    values = scaler.transform(frame[value_cols]).astype("float32")
    targets = labels["target"].to_numpy(dtype=np.int32)
    active = labels["failure_active"].to_numpy(dtype=np.int32)
    timestamps = frame["timestamp"].to_numpy()

    sequences: List[np.ndarray] = []
    seq_targets: List[int] = []
    seq_timestamps: List[np.datetime64] = []

    for end_idx in range(seq_len - 1, len(frame), stride):
        start_idx = end_idx - seq_len + 1
        if active[start_idx : end_idx + 1].any():
            continue
        if normal_only and targets[start_idx : end_idx + 1].any():
            continue
        sequences.append(values[start_idx : end_idx + 1])
        seq_targets.append(int(targets[end_idx]))
        seq_timestamps.append(timestamps[end_idx])

    if not sequences:
        shape = (0, seq_len, len(value_cols))
        return np.empty(shape, dtype="float32"), np.empty((0,), dtype=np.int32), np.empty((0,), dtype="datetime64[ns]")

    X = np.stack(sequences).astype("float32")
    y = np.asarray(seq_targets, dtype=np.int32)
    ts = np.asarray(seq_timestamps)

    if max_sequences is not None and len(X) > max_sequences:
        rng = np.random.default_rng(SEED)
        keep = np.sort(rng.choice(len(X), size=max_sequences, replace=False))
        X, y, ts = X[keep], y[keep], ts[keep]

    return X, y, ts


def build_autoencoder(strategy: tf.distribute.Strategy, seq_len: int, n_features: int, cfg: Config) -> keras.Model:
    global_batch_size = cfg.ae_batch_size_per_replica * max(strategy.num_replicas_in_sync, 1)

    with strategy.scope():
        inputs = keras.Input(shape=(seq_len, n_features), dtype="float32")
        x = layers.Conv1D(64, 5, padding="same", activation="swish")(inputs)
        x = layers.LayerNormalization()(x)
        x = layers.AveragePooling1D(pool_size=2)(x)
        x = layers.Conv1D(128, 5, padding="same", activation="swish")(x)
        x = layers.LayerNormalization()(x)
        x = layers.AveragePooling1D(pool_size=2)(x)
        x = layers.Conv1D(128, 3, padding="same", activation="swish")(x)
        x = layers.Dropout(0.15)(x)
        x = layers.UpSampling1D(size=2)(x)
        x = layers.Conv1D(96, 5, padding="same", activation="swish")(x)
        x = layers.LayerNormalization()(x)
        x = layers.UpSampling1D(size=2)(x)
        x = layers.Conv1D(64, 3, padding="same", activation="swish")(x)
        outputs = layers.Conv1D(n_features, 1, padding="same", dtype="float32")(x)

        model = keras.Model(inputs, outputs, name="metropt3_temporal_autoencoder")
        optimizer = keras.optimizers.Adam(learning_rate=cfg.ae_learning_rate)
        model.compile(optimizer=optimizer, loss="mae")

    model.global_batch_size = global_batch_size
    return model


def train_autoencoder(
    strategy: tf.distribute.Strategy,
    X_train_normal: np.ndarray,
    cfg: Config,
) -> keras.Model:
    seq_len = X_train_normal.shape[1]
    n_features = X_train_normal.shape[2]
    model = build_autoencoder(strategy, seq_len, n_features, cfg)
    batch_size = model.global_batch_size

    split = max(int(len(X_train_normal) * 0.9), 1)
    X_fit = X_train_normal[:split]
    X_eval = X_train_normal[split:] if split < len(X_train_normal) else X_train_normal[: min(len(X_train_normal), 1024)]

    train_ds = tf.data.Dataset.from_tensor_slices((X_fit, X_fit)).shuffle(min(len(X_fit), 8192), seed=SEED)
    train_ds = train_ds.batch(batch_size, drop_remainder=False).prefetch(tf.data.AUTOTUNE)
    eval_ds = tf.data.Dataset.from_tensor_slices((X_eval, X_eval)).batch(batch_size).prefetch(tf.data.AUTOTUNE)

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=4,
            restore_best_weights=True,
            verbose=1,
        )
    ]

    model.fit(
        train_ds,
        validation_data=eval_ds,
        epochs=cfg.ae_epochs,
        verbose=1,
        callbacks=callbacks,
    )
    return model


def reconstruction_scores(model: keras.Model, X: np.ndarray, batch_size: int) -> np.ndarray:
    preds = model.predict(X, batch_size=batch_size, verbose=0)
    error = np.mean(np.abs(X - preds), axis=(1, 2))
    return error.astype("float32")


def robust_score(reference_errors: np.ndarray, errors: np.ndarray) -> np.ndarray:
    median = float(np.median(reference_errors))
    mad = float(np.median(np.abs(reference_errors - median)) + 1e-6)
    z = (errors - median) / (1.4826 * mad + 1e-6)
    z = np.clip(z, -10.0, 10.0)
    return 1.0 / (1.0 + np.exp(-z))


def align_sequence_scores(
    frame_timestamps: pd.Series,
    seq_timestamps: np.ndarray,
    seq_scores: np.ndarray,
) -> np.ndarray:
    score_map = pd.Series(seq_scores, index=pd.to_datetime(seq_timestamps))
    aligned = score_map.reindex(pd.to_datetime(frame_timestamps), fill_value=0.0)
    return aligned.to_numpy(dtype="float32")


def apply_alert_smoothing(
    timestamps: pd.Series,
    scores: np.ndarray,
    threshold: float,
    persistence: int,
    cooldown_minutes: int,
) -> np.ndarray:
    raw = (scores >= threshold).astype(np.int8)
    smoothed = np.zeros_like(raw)
    streak = 0
    cooldown_until: Optional[pd.Timestamp] = None

    for idx, flag in enumerate(raw):
        ts = timestamps.iloc[idx]
        if cooldown_until is not None and ts < cooldown_until:
            streak = 0
            continue
        streak = streak + 1 if flag else 0
        if streak >= persistence:
            smoothed[idx] = 1
            cooldown_until = ts + pd.Timedelta(minutes=cooldown_minutes)
            streak = 0
    return smoothed


def alert_episodes(pred_df: pd.DataFrame) -> pd.DataFrame:
    alerts = pred_df.loc[pred_df["alert"].eq(1)].copy()
    if alerts.empty:
        return pd.DataFrame(columns=["episode_id", "start", "end", "peak_risk"])

    gap = alerts["timestamp"].diff().dt.total_seconds().fillna(60)
    alerts["episode_id"] = (gap > 60).cumsum()
    episodes = (
        alerts.groupby("episode_id")
        .agg(start=("timestamp", "min"), end=("timestamp", "max"), peak_risk=("risk_score", "max"))
        .reset_index()
    )
    return episodes


def count_false_alert_episodes(
    timestamps: pd.Series,
    alerts: np.ndarray,
    positive_mask: np.ndarray,
) -> int:
    pred_df = pd.DataFrame(
        {
            "timestamp": timestamps.to_numpy(),
            "alert": alerts,
            "positive": positive_mask.astype(np.int8),
        }
    )
    episodes = alert_episodes(pred_df)
    if episodes.empty:
        return 0

    false_episodes = 0
    for row in episodes.itertuples(index=False):
        episode_mask = (pred_df["timestamp"] >= row.start) & (pred_df["timestamp"] <= row.end)
        if not pred_df.loc[episode_mask, "positive"].any():
            false_episodes += 1
    return false_episodes


def event_metrics(
    pred_df: pd.DataFrame,
    events_df: pd.DataFrame,
    held_out_event_id: int,
) -> Dict[str, Optional[float]]:
    episodes = alert_episodes(pred_df)
    event_row = events_df.loc[events_df["event_id"] == held_out_event_id].iloc[0]
    warning_start = event_row["Start Time"] - pd.Timedelta(hours=WARNING_HOURS)
    warning_end = event_row["Start Time"]

    caught = False
    lead_time = None

    if not episodes.empty:
        matching = episodes.loc[(episodes["start"] >= warning_start) & (episodes["start"] < warning_end)]
        if not matching.empty:
            caught = True
            lead_time = float((event_row["Start Time"] - matching["start"].min()).total_seconds() / 60.0)

    false_episodes = 0
    if not episodes.empty:
        for row in episodes.itertuples(index=False):
            if not (warning_start <= row.start < warning_end):
                false_episodes += 1

    total_days = max((pred_df["timestamp"].max() - pred_df["timestamp"].min()).total_seconds() / 86400.0, 1e-6)

    return {
        "event_recall": float(caught),
        "false_alerts_per_day": float(false_episodes / total_days),
        "median_lead_time_minutes": lead_time,
        "caught_event": int(caught),
    }


def row_metrics(y_true: np.ndarray, scores: np.ndarray, alerts: np.ndarray) -> Dict[str, float]:
    return {
        "precision": float(precision_score(y_true, alerts, zero_division=0)),
        "recall": float(recall_score(y_true, alerts, zero_division=0)),
        "f1": float(f1_score(y_true, alerts, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, scores)),
    }


def select_threshold_train_only(
    timestamps: pd.Series,
    y_true: np.ndarray,
    scores: np.ndarray,
    cfg: Config,
) -> float:
    candidates = np.unique(np.quantile(scores, np.linspace(0.75, 0.995, 120)))
    best_threshold = float(np.quantile(scores, 0.95))
    best_feasible = None
    best_fallback = None

    for threshold in candidates:
        alerts = apply_alert_smoothing(
            timestamps=timestamps.reset_index(drop=True),
            scores=scores,
            threshold=float(threshold),
            persistence=cfg.alert_persistence,
            cooldown_minutes=cfg.alert_cooldown_minutes,
        )
        f1 = f1_score(y_true, alerts, zero_division=0)
        pred_df = pd.DataFrame(
            {
                "timestamp": timestamps.to_numpy(),
                "target": y_true,
                "risk_score": scores,
                "alert": alerts,
            }
        )
        total_days = max((timestamps.max() - timestamps.min()).total_seconds() / 86400.0, 1e-6)
        false_episodes = count_false_alert_episodes(
            timestamps=timestamps.reset_index(drop=True),
            alerts=alerts,
            positive_mask=y_true.astype(bool),
        )
        false_per_day = float(false_episodes / total_days)

        candidate = (f1, -false_per_day, float(threshold))
        if false_per_day <= cfg.train_alert_budget_per_day:
            if best_feasible is None or candidate > best_feasible:
                best_feasible = candidate
                best_threshold = float(threshold)
        else:
            fallback = (-false_per_day, f1, float(threshold))
            if best_fallback is None or fallback > best_fallback:
                best_fallback = fallback
                best_threshold = float(threshold)

    return best_threshold


def aggregate_results(results: Sequence[FoldResult]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.DataFrame([asdict(item) for item in results])
    summary = (
        frame.agg(
            {
                "precision": "mean",
                "recall": "mean",
                "f1": "mean",
                "pr_auc": "mean",
                "event_recall": "mean",
                "false_alerts_per_day": "mean",
                "threshold": "mean",
            }
        )
        .to_frame()
        .T
    )
    summary["median_lead_time_minutes"] = frame["median_lead_time_minutes"].median()
    return frame, summary


def evaluate_fold(
    dataset: pd.DataFrame,
    sensor_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    events_df: pd.DataFrame,
    held_out_event_id: int,
    strategy: tf.distribute.Strategy,
    cfg: Config,
) -> Tuple[FoldResult, pd.DataFrame]:
    train_mask, valid_mask = prepare_fold_masks(dataset, events_df, held_out_event_id)
    cols = feature_columns(dataset)

    train_df = dataset.loc[train_mask].reset_index(drop=True)
    valid_df = dataset.loc[valid_mask].reset_index(drop=True)

    X_train = train_df[cols].fillna(0.0)
    y_train = train_df["target"].astype(int)
    X_valid = valid_df[cols].fillna(0.0)
    y_valid = valid_df["target"].astype(int).to_numpy()

    xgb = fit_supervised_model(X_train, y_train, cfg)
    xgb_train_scores = xgb.predict_proba(X_train)[:, 1]
    xgb_valid_scores = xgb.predict_proba(X_valid)[:, 1]

    iso_scaler, iso_model = fit_isolation_forest(X_train, y_train)
    iso_train_raw = -iso_model.score_samples(iso_scaler.transform(X_train))
    iso_valid_raw = -iso_model.score_samples(iso_scaler.transform(X_valid))
    iso_reference = iso_train_raw[y_train.eq(0).to_numpy()]
    iso_train_scores = robust_score(iso_reference, iso_train_raw)
    iso_valid_scores = robust_score(iso_reference, iso_valid_raw)

    seq_sensor_train = sensor_df.loc[train_mask.values, ["timestamp"] + CONTINUOUS_SENSORS + BINARY_SENSORS].reset_index(drop=True)
    seq_sensor_valid = sensor_df.loc[valid_mask.values, ["timestamp"] + CONTINUOUS_SENSORS + BINARY_SENSORS].reset_index(drop=True)
    seq_labels_train = labels_df.loc[train_mask.values].reset_index(drop=True)
    seq_labels_valid = labels_df.loc[valid_mask.values].reset_index(drop=True)

    seq_train_frame = prepare_sequence_frame(seq_sensor_train)
    seq_valid_frame = prepare_sequence_frame(seq_sensor_valid)

    seq_scaler = RobustScaler()
    normal_fit = seq_train_frame.loc[seq_labels_train["target"].eq(0), sequence_feature_columns()]
    seq_scaler.fit(normal_fit)

    X_train_seq, _, train_seq_ts = build_sequence_tensor(
        frame=seq_train_frame,
        labels=seq_labels_train,
        scaler=seq_scaler,
        seq_len=cfg.sequence_length,
        stride=cfg.train_sequence_stride,
        normal_only=True,
        max_sequences=cfg.max_normal_sequences,
    )

    X_valid_seq, _, valid_seq_ts = build_sequence_tensor(
        frame=seq_valid_frame,
        labels=seq_labels_valid,
        scaler=seq_scaler,
        seq_len=cfg.sequence_length,
        stride=cfg.valid_sequence_stride,
        normal_only=False,
        max_sequences=None,
    )

    ae_scores_train_aligned = np.zeros(len(train_df), dtype="float32")
    ae_scores_valid_aligned = np.zeros(len(valid_df), dtype="float32")

    if len(X_train_seq) >= 256 and len(X_valid_seq) > 0:
        autoencoder = train_autoencoder(strategy, X_train_seq, cfg)
        ae_batch_size = autoencoder.global_batch_size
        ref_errors = reconstruction_scores(autoencoder, X_train_seq[: min(len(X_train_seq), 8192)], ae_batch_size)
        train_errors = reconstruction_scores(autoencoder, X_train_seq, ae_batch_size)
        valid_errors = reconstruction_scores(autoencoder, X_valid_seq, ae_batch_size)
        train_seq_scores = robust_score(ref_errors, train_errors)
        valid_seq_scores = robust_score(ref_errors, valid_errors)
        ae_scores_train_aligned = align_sequence_scores(train_df["timestamp"], train_seq_ts, train_seq_scores)
        ae_scores_valid_aligned = align_sequence_scores(valid_df["timestamp"], valid_seq_ts, valid_seq_scores)
        del autoencoder
    else:
        print(f"Skipping autoencoder in fold {held_out_event_id}: not enough normal sequences.")

    train_scores = (
        cfg.supervised_weight * xgb_train_scores
        + cfg.anomaly_weight * ae_scores_train_aligned
        + cfg.isolation_weight * iso_train_scores
    )
    valid_scores = (
        cfg.supervised_weight * xgb_valid_scores
        + cfg.anomaly_weight * ae_scores_valid_aligned
        + cfg.isolation_weight * iso_valid_scores
    )

    threshold = select_threshold_train_only(train_df["timestamp"], y_train.to_numpy(), train_scores, cfg)
    alerts = apply_alert_smoothing(
        timestamps=valid_df["timestamp"],
        scores=valid_scores,
        threshold=threshold,
        persistence=cfg.alert_persistence,
        cooldown_minutes=cfg.alert_cooldown_minutes,
    )

    pred_df = valid_df[["timestamp", "target", "event_id"]].copy()
    pred_df["risk_score"] = valid_scores
    pred_df["alert"] = alerts

    rows = row_metrics(y_valid, valid_scores, alerts)
    events = event_metrics(pred_df, events_df, held_out_event_id)

    fold_result = FoldResult(
        fold_name=f"event_{held_out_event_id}",
        event_id=held_out_event_id,
        threshold=float(threshold),
        precision=rows["precision"],
        recall=rows["recall"],
        f1=rows["f1"],
        pr_auc=rows["pr_auc"],
        event_recall=events["event_recall"],
        false_alerts_per_day=events["false_alerts_per_day"],
        median_lead_time_minutes=events["median_lead_time_minutes"],
        caught_event=events["caught_event"],
    )

    tf.keras.backend.clear_session()
    gc.collect()
    return fold_result, pred_df


def main() -> None:
    set_seed(SEED)
    cfg = Config()
    os.makedirs(cfg.output_dir, exist_ok=True)

    print("Loading data...")
    sensor_df, events_df = load_data(cfg)

    print("Engineering features...")
    feature_df = engineer_features(sensor_df)
    labels_df = create_labels(sensor_df, events_df)
    dataset = build_dataset(feature_df, labels_df)

    aligned_sensor = sensor_df.iloc[WARMUP_ROWS:].reset_index(drop=True)
    aligned_labels = labels_df.iloc[WARMUP_ROWS:].reset_index(drop=True)
    aligned_dataset = dataset.reset_index(drop=True)

    strategy = init_strategy()

    fold_results: List[FoldResult] = []
    all_predictions: List[pd.DataFrame] = []

    for held_out_event_id in events_df["event_id"].tolist():
        print(f"\n===== Fold for event {held_out_event_id} =====")
        result, pred_df = evaluate_fold(
            dataset=aligned_dataset,
            sensor_df=aligned_sensor,
            labels_df=aligned_labels,
            events_df=events_df,
            held_out_event_id=int(held_out_event_id),
            strategy=strategy,
            cfg=cfg,
        )
        fold_results.append(result)
        all_predictions.append(pred_df.assign(fold_name=result.fold_name))
        print(asdict(result))

    fold_metrics, summary = aggregate_results(fold_results)
    predictions = pd.concat(all_predictions, ignore_index=True)

    fold_metrics.to_csv(Path(cfg.output_dir) / "fold_metrics.csv", index=False)
    summary.to_csv(Path(cfg.output_dir) / "summary.csv", index=False)
    predictions.to_csv(Path(cfg.output_dir) / "predictions.csv", index=False)

    payload = {
        "config": asdict(cfg),
        "summary": summary.to_dict(orient="records"),
        "folds": fold_metrics.to_dict(orient="records"),
    }
    with open(Path(cfg.output_dir) / "report.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print("\nDone.")
    print(summary.to_string(index=False))
    print(f"Outputs written to: {cfg.output_dir}")


if __name__ == "__main__":
    main()
