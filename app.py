from __future__ import annotations

import json
import pickle
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from ptad_runtime import PTADv2Runtime


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "ptad_v2_4_tuned.pkl"
MODEL_STATE_PATH = BASE_DIR / "model_state.json"
FRONTEND_DIST = BASE_DIR / "public"
if not FRONTEND_DIST.exists():
    FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

RAW_DEFAULTS: Dict[str, float] = {
    "TP2": 8.2,
    "TP3": 8.0,
    "H1": 8.1,
    "DV_pressure": 8.3,
    "Reservoirs": 8.1,
    "Oil_temperature": 62.0,
    "Motor_current": 4.2,
    "COMP": 1.0,
    "MPG": 1.0,
    "LPS": 1.0,
}

FEATURE_DEFAULTS: Dict[str, float] = {
    "pressure_diff": 0.02,
    "LPS_freq_10min": 0.02,
    "sensor_divergence": 0.15,
    "compressor_efficiency": 0.0045,
    "duty_cycle_5min": 0.84,
    "thermal_index": 0.48,
    "reservoir_panel_ratio": 0.98,
    "pressure_variance_10min": 3.8,
    "motor_thermal_stress": 0.35,
    "current_spike_freq": 0.08,
    "load_cycle_regularity": 0.72,
    "towers_switching_freq": 0.05,
    "comp_mpg_disagreement": 0.0,
    "TP2": RAW_DEFAULTS["TP2"],
    "TP3": RAW_DEFAULTS["TP3"],
    "H1": RAW_DEFAULTS["H1"],
    "DV_pressure": RAW_DEFAULTS["DV_pressure"],
    "Reservoirs": RAW_DEFAULTS["Reservoirs"],
    "Oil_temperature": RAW_DEFAULTS["Oil_temperature"],
    "Motor_current": RAW_DEFAULTS["Motor_current"],
}

REQUIRED_COLUMNS: List[str] = list(FEATURE_DEFAULTS.keys())


def load_model() -> Any:
    runtime_model = PTADv2Runtime()
    if MODEL_STATE_PATH.exists():
        with MODEL_STATE_PATH.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        runtime_model.fitted = bool(state.get("fitted", runtime_model.fitted))
        runtime_model.feature_cols = list(state.get("feature_cols", runtime_model.feature_cols))
        runtime_model.all_features = list(state.get("all_features", runtime_model.all_features))
        for name in ["physics", "temporal", "statistical", "fusion", "alert"]:
            part = state.get(name)
            if isinstance(part, dict):
                getattr(runtime_model, name).__dict__.update(part)
        return runtime_model

    # Local fallback for legacy pickle loading.
    from joblib.externals import cloudpickle as bundled_cloudpickle
    from joblib.externals.cloudpickle import cloudpickle as bundled_cloudpickle_impl
    import sys as runtime_sys

    runtime_sys.modules["cloudpickle"] = bundled_cloudpickle
    runtime_sys.modules["cloudpickle.cloudpickle"] = bundled_cloudpickle_impl
    with MODEL_PATH.open("rb") as handle:
        legacy_model = pickle.load(handle)
    return PTADv2Runtime.from_legacy(legacy_model)


MODEL = load_model()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def derive_features(raw: Dict[str, float], overrides: Dict[str, float]) -> Dict[str, float]:
    tp2 = raw["TP2"]
    tp3 = raw["TP3"]
    h1 = raw["H1"]
    dv = raw["DV_pressure"]
    reservoirs = raw["Reservoirs"]
    oil = raw["Oil_temperature"]
    motor = raw["Motor_current"]
    comp = raw["COMP"]
    mpg = raw["MPG"]
    lps = raw["LPS"]

    pressure_diff = abs(tp2 - tp3)
    sensor_divergence = abs(h1 - tp3)
    compressor_efficiency = pressure_diff / (abs(motor) + 1e-3)
    thermal_index = clamp((oil - 50.0) / 30.0, 0.0, 2.0)
    reservoir_panel_ratio = reservoirs / (dv + 1e-3)
    pressure_variance_10min = max(abs(dv - reservoirs) * 8.0, 0.05)
    motor_thermal_stress = clamp((motor / 6.0) * (oil / 80.0), 0.0, 2.0)
    current_spike_freq = clamp(max(motor - 4.5, 0.0) / 4.0, 0.0, 1.0)
    load_cycle_regularity = clamp(1.0 - abs(comp - lps) * 0.5, 0.0, 1.0)
    towers_switching_freq = overrides.get("towers_switching_freq", FEATURE_DEFAULTS["towers_switching_freq"])
    lps_freq_10min = clamp(abs(1.0 - lps) * 0.2, 0.0, 1.0)
    duty_cycle_5min = overrides.get("duty_cycle_5min", FEATURE_DEFAULTS["duty_cycle_5min"])
    comp_mpg_disagreement = 1.0 if int(round(comp)) != int(round(mpg)) else 0.0

    feature_map = {
        "pressure_diff": pressure_diff,
        "LPS_freq_10min": lps_freq_10min,
        "sensor_divergence": sensor_divergence,
        "compressor_efficiency": compressor_efficiency,
        "duty_cycle_5min": duty_cycle_5min,
        "thermal_index": thermal_index,
        "reservoir_panel_ratio": reservoir_panel_ratio,
        "pressure_variance_10min": pressure_variance_10min,
        "motor_thermal_stress": motor_thermal_stress,
        "current_spike_freq": current_spike_freq,
        "load_cycle_regularity": load_cycle_regularity,
        "towers_switching_freq": towers_switching_freq,
        "comp_mpg_disagreement": comp_mpg_disagreement,
        "TP2": tp2,
        "TP3": tp3,
        "H1": h1,
        "DV_pressure": dv,
        "Reservoirs": reservoirs,
        "Oil_temperature": oil,
        "Motor_current": motor,
    }

    for key, value in overrides.items():
        if key in feature_map:
            feature_map[key] = value
    return feature_map


def serialize_output(output: Any) -> Dict[str, Any]:
    if is_dataclass(output):
        data = asdict(output)
    else:
        data = dict(output)
    data["top_physics_signals"] = [
        signal if isinstance(signal, dict) else asdict(signal) for signal in data.get("top_physics_signals", [])
    ]
    return data


def level_to_band(level: str) -> str:
    return {
        "CRITICAL": "critical",
        "WARNING": "warning",
        "NORMAL": "normal",
    }.get(level, "normal")


app = Flask(__name__)


@app.get("/api/config")
@app.get("/svc/config")
def config() -> Any:
    return jsonify(
        {
            "threshold": float(MODEL.fusion.threshold),
            "weights": MODEL.fusion.weights,
            "version": getattr(MODEL, "VERSION", "unknown"),
            "required_columns": REQUIRED_COLUMNS,
            "raw_defaults": RAW_DEFAULTS,
            "feature_defaults": FEATURE_DEFAULTS,
        }
    )


@app.post("/api/predict")
@app.post("/svc/predict")
def predict_single() -> Any:
    payload = request.get_json(silent=True) or {}
    raw = {key: float(payload.get("raw", {}).get(key, default)) for key, default in RAW_DEFAULTS.items()}
    overrides = {
        key: float(value)
        for key, value in payload.get("features", {}).items()
        if key in REQUIRED_COLUMNS and value is not None and value != ""
    }
    timestamp = payload.get("timestamp") or ""
    features = derive_features(raw, overrides)
    output = MODEL.predict_single(features, timestamp=timestamp)
    response = serialize_output(output)
    response["band"] = level_to_band(response["alert_level"])
    response["features"] = features
    response["threshold"] = float(MODEL.fusion.threshold)
    return jsonify(response)


@app.post("/api/predict-batch")
@app.post("/svc/predict-batch")
def predict_batch() -> Any:
    upload = request.files.get("file")
    if upload is None or upload.filename == "":
        return jsonify({"error": "Upload a CSV file first."}), 400

    df = pd.read_csv(upload)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        return jsonify({"error": f"CSV is missing required columns: {', '.join(missing)}"}), 400

    work = df.copy()
    if "timestamp" not in work.columns:
        work["timestamp"] = ""

    scores, levels, outputs = MODEL.predict_batch(work)
    summary = {
        "rows": int(len(work)),
        "average_score": float(pd.Series(scores).mean()),
        "max_score": float(pd.Series(scores).max()),
        "critical_count": int(sum(level == "CRITICAL" for level in levels)),
        "warning_count": int(sum(level == "WARNING" for level in levels)),
        "normal_count": int(sum(level == "NORMAL" for level in levels)),
    }

    preview_rows = []
    for idx, output in enumerate(outputs[:12]):
        data = serialize_output(output)
        data["row_index"] = idx
        data["band"] = level_to_band(data["alert_level"])
        preview_rows.append(data)

    return jsonify({"summary": summary, "preview": preview_rows})


@app.get("/assets/<path:asset_path>")
def serve_asset(asset_path: str):
    assets_dir = FRONTEND_DIST / "assets"
    return send_from_directory(assets_dir, asset_path)


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def serve_frontend(path: str):
    if not FRONTEND_DIST.exists():
        return (
            "Frontend build not found. Run `npm run build` from project root to generate the UI bundle.",
            503,
        )

    if path:
        candidate = FRONTEND_DIST / path
        if candidate.exists() and candidate.is_file():
            return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
