from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
BINARY_MODEL_PATH = BASE_DIR / "live_binary_model.pkl"
BINARY_SUMMARY_PATH = BASE_DIR / "live_binary_summary.json"
GEMINI_KEY_PATH = BASE_DIR / "gemini_api_key.txt"
GEMINI_MODEL = "gemini-2.5-flash-lite"

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
BATCH_RAW_COLUMNS: List[str] = list(RAW_DEFAULTS.keys())


def load_binary_model() -> tuple[Any, dict[str, Any]]:
    with BINARY_MODEL_PATH.open("rb") as handle:
        model = pickle.load(handle)
    with BINARY_SUMMARY_PATH.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    return model, summary


def load_gemini_key() -> str:
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    if GEMINI_KEY_PATH.exists():
        return GEMINI_KEY_PATH.read_text(encoding="utf-8").strip()
    return ""


BINARY_MODEL, BINARY_SUMMARY = load_binary_model()
GEMINI_API_KEY = load_gemini_key()
TRAINED_BINARY_THRESHOLD = float(BINARY_SUMMARY.get("threshold", 0.95))
WARNING_THRESHOLD = 0.50
CRITICAL_THRESHOLD = TRAINED_BINARY_THRESHOLD


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

    feature_map = {
        "pressure_diff": abs(tp2 - tp3),
        "LPS_freq_10min": clamp(abs(1.0 - lps) * 0.2, 0.0, 1.0),
        "sensor_divergence": abs(h1 - tp3),
        "compressor_efficiency": abs(tp2 - tp3) / (abs(motor) + 1e-3),
        "duty_cycle_5min": overrides.get("duty_cycle_5min", FEATURE_DEFAULTS["duty_cycle_5min"]),
        "thermal_index": clamp((oil - 50.0) / 30.0, 0.0, 2.0),
        "reservoir_panel_ratio": reservoirs / (dv + 1e-3),
        "pressure_variance_10min": max(abs(dv - reservoirs) * 8.0, 0.05),
        "motor_thermal_stress": clamp((motor / 6.0) * (oil / 80.0), 0.0, 2.0),
        "current_spike_freq": clamp(max(motor - 4.5, 0.0) / 4.0, 0.0, 1.0),
        "load_cycle_regularity": clamp(1.0 - abs(comp - lps) * 0.5, 0.0, 1.0),
        "towers_switching_freq": overrides.get("towers_switching_freq", FEATURE_DEFAULTS["towers_switching_freq"]),
        "comp_mpg_disagreement": 1.0 if int(round(comp)) != int(round(mpg)) else 0.0,
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


def band_from_probability(probability: float) -> tuple[str, str]:
    if probability >= CRITICAL_THRESHOLD:
        return "CRITICAL", "critical"
    if probability >= WARNING_THRESHOLD:
        return "WARNING", "warning"
    return "NORMAL", "normal"


def confidence_from_probability(probability: float) -> float:
    pivot = WARNING_THRESHOLD if probability < CRITICAL_THRESHOLD else CRITICAL_THRESHOLD
    return float(clamp(abs(probability - pivot) / max(CRITICAL_THRESHOLD - WARNING_THRESHOLD, 1e-6), 0.0, 1.0))


def build_binary_feature_row(raw: Dict[str, float], features: Dict[str, float]) -> pd.DataFrame:
    base = {
        "TP2": raw["TP2"],
        "TP3": raw["TP3"],
        "H1": raw["H1"],
        "DV_pressure": raw["DV_pressure"],
        "Reservoirs": raw["Reservoirs"],
        "Oil_temperature": raw["Oil_temperature"],
        "Motor_current": raw["Motor_current"],
        "COMP": raw["COMP"],
        "MPG": raw["MPG"],
        "LPS": raw["LPS"],
        "pressure_diff": features["pressure_diff"],
        "sensor_divergence": features["sensor_divergence"],
        "compressor_efficiency": features["compressor_efficiency"],
        "thermal_index": features["thermal_index"],
        "pressure_variance_10min": features["pressure_variance_10min"],
        "motor_overload": float(raw["Motor_current"] > 5.5),
        "temp_slope_30min": 0.0,
        "reservoir_gap": abs(raw["Reservoirs"] - raw["DV_pressure"]),
        "binary_activity": raw["COMP"] + raw["MPG"] + raw["LPS"],
        "physics_score": (
            0.28 * features["thermal_index"]
            + 0.22 * float(raw["Motor_current"] > 5.5)
            + 0.22 * clamp(features["pressure_diff"] / 0.2, 0, 1)
            + 0.16 * clamp(features["sensor_divergence"] / 2.0, 0, 1)
            + 0.12 * features["comp_mpg_disagreement"]
        ),
        "temporal_score": 0.0,
        "statistical_score": clamp(
            0.34 * clamp(features["pressure_variance_10min"] / 12.0, 0, 1)
            + 0.33 * clamp(features["current_spike_freq"], 0, 1)
            + 0.33 * clamp(features["motor_thermal_stress"] / 1.2, 0, 1),
            0,
            1,
        ),
        "railsense_score": 0.0,
        "runtime_confidence": 0.0,
    }
    model_columns = list(BINARY_MODEL.named_steps["imputer"].feature_names_in_)
    row = {column: float(base.get(column, 0.0)) for column in model_columns}
    return pd.DataFrame([row], columns=model_columns)


def build_top_signals(raw: Dict[str, float], features: Dict[str, float]) -> list[dict[str, Any]]:
    candidates = [
        {
            "name": "temperature",
            "description": f"Oil temperature {raw['Oil_temperature']:.1f}C",
            "score": clamp((raw["Oil_temperature"] - 65.0) / 15.0, 0, 1),
            "failure_mode": "THERMAL_DEGRADATION",
            "threshold": 65.0,
            "raw_value": raw["Oil_temperature"],
        },
        {
            "name": "motor",
            "description": f"Motor current {raw['Motor_current']:.2f}A",
            "score": clamp((raw["Motor_current"] - 5.0) / 1.2, 0, 1),
            "failure_mode": "COMPRESSOR_OVERLOAD",
            "threshold": 5.0,
            "raw_value": raw["Motor_current"],
        },
        {
            "name": "pressure_gap",
            "description": f"Pressure difference {features['pressure_diff']:.3f}",
            "score": clamp(features["pressure_diff"] / 0.25, 0, 1),
            "failure_mode": "AIR_LEAK_PRESSURE",
            "threshold": 0.25,
            "raw_value": features["pressure_diff"],
        },
        {
            "name": "sensor_divergence",
            "description": f"Sensor divergence {features['sensor_divergence']:.3f}",
            "score": clamp(features["sensor_divergence"] / 2.0, 0, 1),
            "failure_mode": "SENSOR_DIVERGENCE",
            "threshold": 2.0,
            "raw_value": features["sensor_divergence"],
        },
        {
            "name": "valve_logic",
            "description": f"Valve mismatch {int(features['comp_mpg_disagreement'])}",
            "score": clamp(features["comp_mpg_disagreement"], 0, 1),
            "failure_mode": "VALVE_FAULT",
            "threshold": 1.0,
            "raw_value": features["comp_mpg_disagreement"],
        },
    ]
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:3]


def recommended_action(level: str, dominant_mode: str) -> str:
    if level == "CRITICAL":
        return f"Immediate inspection advised. Failure risk is high{f' due to {dominant_mode.lower()}' if dominant_mode else ''}."
    if level == "WARNING":
        return "Risk is elevated. Monitor closely and schedule maintenance soon."
    return "System appears stable. Continue routine monitoring."


def build_gemini_prompt(prediction: Dict[str, Any]) -> str:
    features = prediction["features"]
    top_signals = prediction.get("top_physics_signals", [])
    signal_lines = []
    for signal in top_signals[:3]:
        signal_lines.append(
            f"- {signal['name']}: score {signal['score']:.2f}, detail {signal['description']}"
        )
    signal_text = "\n".join(signal_lines) if signal_lines else "- No dominant signals"
    return (
        "You are explaining an industrial failure-risk prediction to a non-technical rail operator.\n"
        "Write one short paragraph only.\n"
        "Maximum 65 words.\n"
        "Use plain language.\n"
        "Mention the risk meaning, the main unusual values, and the immediate action.\n"
        "Do not use bullet points.\n"
        "Do not invent values.\n\n"
        f"Alert level: {prediction['alert_level']}\n"
        f"Failure probability: {prediction['failure_probability']:.4f}\n"
        f"Confidence: {prediction['confidence']:.4f}\n"
        f"Dominant failure mode: {prediction['dominant_failure_mode'] or 'None'}\n"
        f"Recommended action: {prediction['recommended_action']}\n"
        "Important values:\n"
        f"- TP2: {features['TP2']:.3f}\n"
        f"- TP3: {features['TP3']:.3f}\n"
        f"- H1: {features['H1']:.3f}\n"
        f"- DV pressure: {features['DV_pressure']:.3f}\n"
        f"- Reservoirs: {features['Reservoirs']:.3f}\n"
        f"- Oil temperature: {features['Oil_temperature']:.3f}\n"
        f"- Motor current: {features['Motor_current']:.3f}\n"
        f"- Pressure difference: {features['pressure_diff']:.3f}\n"
        f"- Sensor divergence: {features['sensor_divergence']:.3f}\n"
        f"- Pressure variance: {features['pressure_variance_10min']:.3f}\n"
        "Top model signals:\n"
        f"{signal_text}"
    )


def generate_gemini_insight(prediction: Dict[str, Any]) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": "Explain machine-risk predictions simply, accurately, and without hype."
                }
            ]
        },
        "contents": [
            {
                "parts": [
                    {
                        "text": build_gemini_prompt(prediction)
                    }
                ]
            }
        ]
    }
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error: {detail or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Gemini network error: {exc.reason}") from exc

    candidates = body.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    if not text.strip():
        raise RuntimeError("Gemini returned an empty explanation.")
    return text.strip()


def predict_from_payload(raw: Dict[str, float], overrides: Dict[str, float], timestamp: str = "") -> Dict[str, Any]:
    features = derive_features(raw, overrides)
    model_input = build_binary_feature_row(raw, features)
    probability = float(BINARY_MODEL.predict_proba(model_input)[0, 1])
    alert_level, band = band_from_probability(probability)
    confidence = confidence_from_probability(probability)

    top_signals = build_top_signals(raw, features)
    dominant_mode = top_signals[0]["failure_mode"] if top_signals and top_signals[0]["score"] > 0.1 else ""
    physics_score = float(model_input.iloc[0]["physics_score"])
    statistical_score = float(model_input.iloc[0]["statistical_score"])
    temporal_score = 0.0

    return {
        "timestamp": timestamp or None,
        "railsense_score": probability,
        "failure_probability": probability,
        "alert_level": alert_level,
        "band": band,
        "confidence": confidence,
        "physics_score": physics_score,
        "temporal_score": temporal_score,
        "statistical_score": statistical_score,
        "top_physics_signals": top_signals,
        "dominant_failure_mode": dominant_mode,
        "recommended_action": recommended_action(alert_level, dominant_mode),
        "fusion_weights": {"binary_model": 1.0},
        "score_components": {
            "binary_failure_probability": probability,
            "physics_explainer": physics_score,
            "temporal_explainer": temporal_score,
            "statistical_explainer": statistical_score,
        },
        "threshold": CRITICAL_THRESHOLD,
        "warning_threshold": WARNING_THRESHOLD,
        "trained_threshold": TRAINED_BINARY_THRESHOLD,
        "features": features,
    }


app = Flask(__name__)


def get_frontend_dist() -> Path:
    return BASE_DIR / "public"


@app.get("/api/config")
@app.get("/svc/config")
def config() -> Any:
    return jsonify(
        {
            "threshold": CRITICAL_THRESHOLD,
            "trained_threshold": TRAINED_BINARY_THRESHOLD,
            "warning_threshold": WARNING_THRESHOLD,
            "weights": {"binary_model": 1.0},
            "version": "RailSense Sentinel Live",
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
    return jsonify(predict_from_payload(raw, overrides, timestamp))


@app.post("/api/explain")
@app.post("/svc/explain")
def explain_prediction() -> Any:
    payload = request.get_json(silent=True) or {}
    prediction = payload.get("prediction")
    if not isinstance(prediction, dict):
        raw = {key: float(payload.get("raw", {}).get(key, default)) for key, default in RAW_DEFAULTS.items()}
        overrides = {
            key: float(value)
            for key, value in payload.get("features", {}).items()
            if key in REQUIRED_COLUMNS and value is not None and value != ""
        }
        prediction = predict_from_payload(raw, overrides, payload.get("timestamp") or "")
    try:
        insight = generate_gemini_insight(prediction)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"insight": insight, "model": GEMINI_MODEL})


@app.post("/api/predict-batch")
@app.post("/svc/predict-batch")
def predict_batch() -> Any:
    upload = request.files.get("file")
    if upload is None or upload.filename == "":
        return jsonify({"error": "Upload a CSV file first."}), 400

    df = pd.read_csv(upload)
    missing = [col for col in BATCH_RAW_COLUMNS if col not in df.columns]
    if missing:
        return jsonify({"error": f"CSV is missing required raw columns: {', '.join(missing)}"}), 400

    work = df.copy()
    if "timestamp" not in work.columns:
        work["timestamp"] = ""

    outputs = []
    for idx, row in work.iterrows():
        raw = {key: float(row.get(key, RAW_DEFAULTS[key])) for key in RAW_DEFAULTS}
        data = predict_from_payload(raw, {}, str(row.get("timestamp", "")))
        data["row_index"] = int(idx)
        outputs.append(data)

    levels = [item["alert_level"] for item in outputs]
    scores = [item["railsense_score"] for item in outputs]
    summary = {
        "rows": int(len(work)),
        "average_score": float(pd.Series(scores).mean()),
        "max_score": float(pd.Series(scores).max()),
        "critical_count": int(sum(level == "CRITICAL" for level in levels)),
        "warning_count": int(sum(level == "WARNING" for level in levels)),
        "normal_count": int(sum(level == "NORMAL" for level in levels)),
    }
    return jsonify({"summary": summary, "preview": outputs[:12]})


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def serve_frontend(path: str):
    frontend_dist = get_frontend_dist()
    if not frontend_dist.exists():
        return ("Frontend files not found.", 503)
    if path:
        candidate = frontend_dist / path
        if candidate.exists() and candidate.is_file():
            return send_from_directory(frontend_dist, path)
    return send_from_directory(frontend_dist, "index.html")


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=5000)
