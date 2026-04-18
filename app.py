from __future__ import annotations

import csv
import io
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
BINARY_SUMMARY_PATH = BASE_DIR / "live_binary_summary.json"
GEMINI_KEY_PATH = BASE_DIR / "gemini_api_key.txt"
GEMINI_MODEL = "gemini-2.5-flash-lite"
MAX_BATCH_ROWS = 100
MAX_BATCH_FILE_BYTES = 1_000_000

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


with BINARY_SUMMARY_PATH.open("r", encoding="utf-8") as handle:
    BINARY_SUMMARY = json.load(handle)

TRAINED_BINARY_THRESHOLD = float(BINARY_SUMMARY.get("threshold", 0.95))
WARNING_THRESHOLD = 0.50
CRITICAL_THRESHOLD = TRAINED_BINARY_THRESHOLD


def load_gemini_key() -> str:
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    if GEMINI_KEY_PATH.exists():
        return GEMINI_KEY_PATH.read_text(encoding="utf-8").strip()
    return ""


GEMINI_API_KEY = load_gemini_key()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def to_float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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
            feature_map[key] = float(value)
    return feature_map


def band_from_probability(probability: float) -> tuple[str, str]:
    if probability >= CRITICAL_THRESHOLD:
        return "CRITICAL", "critical"
    if probability >= WARNING_THRESHOLD:
        return "WARNING", "warning"
    return "NORMAL", "normal"


def confidence_from_probability(probability: float) -> float:
    if probability >= CRITICAL_THRESHOLD:
        return clamp(0.70 + (probability - CRITICAL_THRESHOLD) / 0.05, 0.70, 1.0)
    if probability >= WARNING_THRESHOLD:
        return clamp(0.45 + (probability - WARNING_THRESHOLD) / max(CRITICAL_THRESHOLD - WARNING_THRESHOLD, 1e-6) * 0.35, 0.45, 0.80)
    return clamp(0.55 + (WARNING_THRESHOLD - probability) * 0.4, 0.55, 0.95)


def compute_probability(raw: Dict[str, float], features: Dict[str, float]) -> tuple[float, Dict[str, float]]:
    pressure_gap = abs(raw["Reservoirs"] - raw["DV_pressure"])
    binary_off = 1.0 - ((raw["COMP"] + raw["MPG"] + raw["LPS"]) / 3.0)

    risk_components = {
        "temperature": clamp((raw["Oil_temperature"] - 68.0) / 12.0, 0.0, 1.0),
        "motor": clamp((raw["Motor_current"] - 5.15) / 1.1, 0.0, 1.0),
        "dv_pressure": clamp((4.2 - raw["DV_pressure"]) / 2.4, 0.0, 1.0),
        "pressure_gap": clamp((pressure_gap - 3.8) / 2.2, 0.0, 1.0),
        "pressure_diff": clamp((features["pressure_diff"] - 0.12) / 0.10, 0.0, 1.0),
        "pressure_variance": clamp((features["pressure_variance_10min"] - 14.0) / 12.0, 0.0, 1.0),
        "sensor_divergence": clamp((features["sensor_divergence"] - 6.5) / 2.5, 0.0, 1.0),
        "binary_off": clamp(binary_off, 0.0, 1.0),
        "valve_logic": clamp(features["comp_mpg_disagreement"], 0.0, 1.0),
    }

    weighted = (
        0.20 * risk_components["temperature"]
        + 0.16 * risk_components["motor"]
        + 0.14 * risk_components["dv_pressure"]
        + 0.12 * risk_components["pressure_gap"]
        + 0.08 * risk_components["pressure_diff"]
        + 0.10 * risk_components["pressure_variance"]
        + 0.10 * risk_components["sensor_divergence"]
        + 0.06 * risk_components["binary_off"]
        + 0.04 * risk_components["valve_logic"]
    )

    probability = weighted * 0.78

    if risk_components["temperature"] > 0.55 and risk_components["motor"] > 0.30:
        probability += 0.10
    if risk_components["dv_pressure"] > 0.55 and risk_components["pressure_gap"] > 0.55:
        probability += 0.12
    if risk_components["pressure_variance"] > 0.75 and risk_components["sensor_divergence"] > 0.75:
        probability += 0.06
    if raw["Oil_temperature"] >= 75.0 and raw["Motor_current"] >= 5.5:
        probability += 0.24

    return clamp(probability, 0.0, 0.999), risk_components


def build_top_signals(raw: Dict[str, float], features: Dict[str, float], risk_components: Dict[str, float]) -> list[dict[str, Any]]:
    candidates = [
        {
            "name": "oil_temperature",
            "description": f"Oil temperature {raw['Oil_temperature']:.1f}C",
            "score": risk_components["temperature"],
            "failure_mode": "THERMAL_DEGRADATION",
            "threshold": 68.0,
            "raw_value": raw["Oil_temperature"],
        },
        {
            "name": "motor_current",
            "description": f"Motor current {raw['Motor_current']:.2f}A",
            "score": risk_components["motor"],
            "failure_mode": "COMPRESSOR_OVERLOAD",
            "threshold": 5.15,
            "raw_value": raw["Motor_current"],
        },
        {
            "name": "dv_pressure",
            "description": f"DV pressure {raw['DV_pressure']:.3f}",
            "score": risk_components["dv_pressure"],
            "failure_mode": "PRESSURE_COLLAPSE",
            "threshold": 4.2,
            "raw_value": raw["DV_pressure"],
        },
        {
            "name": "pressure_diff",
            "description": f"Pressure difference {features['pressure_diff']:.3f}",
            "score": risk_components["pressure_diff"],
            "failure_mode": "AIR_LEAK_PRESSURE",
            "threshold": 0.12,
            "raw_value": features["pressure_diff"],
        },
        {
            "name": "sensor_divergence",
            "description": f"Sensor divergence {features['sensor_divergence']:.3f}",
            "score": risk_components["sensor_divergence"],
            "failure_mode": "SENSOR_DIVERGENCE",
            "threshold": 6.5,
            "raw_value": features["sensor_divergence"],
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
        signal_lines.append(f"- {signal['name']}: score {signal['score']:.2f}, detail {signal['description']}")
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


def build_batch_gemini_prompt(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    top_rows = sorted(rows, key=lambda item: item.get("risk_score", 0.0), reverse=True)[:3]
    top_lines = []
    for row in top_rows:
        top_lines.append(
            f"- row {row['row_index'] + 1}: {row['label']} with risk {row['risk_score']:.3f}"
        )
    top_text = "\n".join(top_lines) if top_lines else "- No rows found"
    return (
        "You are explaining a batch machine-risk prediction result to a non-technical operator.\n"
        "Write one short paragraph only.\n"
        "Maximum 75 words.\n"
        "Use plain language.\n"
        "Mention how many rows are normal, warning, and critical, and what action is recommended.\n"
        "Do not use bullet points.\n\n"
        f"Total rows: {summary['rows']}\n"
        f"Normal rows: {summary['normal_count']}\n"
        f"Warning rows: {summary['warning_count']}\n"
        f"Critical rows: {summary['critical_count']}\n"
        f"Average risk score: {summary['average_score']:.3f}\n"
        f"Maximum risk score: {summary['max_score']:.3f}\n"
        "Top risky rows:\n"
        f"{top_text}"
    )


def generate_gemini_insight(prediction: Dict[str, Any]) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "system_instruction": {
            "parts": [
                {"text": "Explain machine-risk predictions simply, accurately, and without hype."}
            ]
        },
        "contents": [{"parts": [{"text": build_gemini_prompt(prediction)}]}],
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as response:
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


def generate_batch_gemini_insight(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "system_instruction": {
            "parts": [{"text": "Explain batch machine-risk predictions simply, accurately, and without hype."}]
        },
        "contents": [{"parts": [{"text": build_batch_gemini_prompt(summary, rows)}]}],
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as response:
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
    probability, risk_components = compute_probability(raw, features)
    alert_level, band = band_from_probability(probability)
    confidence = confidence_from_probability(probability)
    top_signals = build_top_signals(raw, features, risk_components)
    dominant_mode = top_signals[0]["failure_mode"] if top_signals and top_signals[0]["score"] > 0.1 else ""

    physics_score = clamp(
        0.34 * risk_components["temperature"]
        + 0.24 * risk_components["motor"]
        + 0.18 * risk_components["pressure_diff"]
        + 0.12 * risk_components["sensor_divergence"]
        + 0.12 * risk_components["valve_logic"],
        0.0,
        1.0,
    )
    temporal_score = clamp(0.6 * risk_components["pressure_variance"] + 0.4 * risk_components["binary_off"], 0.0, 1.0)
    statistical_score = clamp(0.5 * risk_components["dv_pressure"] + 0.5 * risk_components["pressure_gap"], 0.0, 1.0)

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
        "fusion_weights": {"heuristic_live_model": 1.0},
        "score_components": {
            "heuristic_live_probability": probability,
            "physics_explainer": physics_score,
            "temporal_explainer": temporal_score,
            "statistical_explainer": statistical_score,
        },
        "threshold": CRITICAL_THRESHOLD,
        "warning_threshold": WARNING_THRESHOLD,
        "trained_threshold": TRAINED_BINARY_THRESHOLD,
        "features": features,
    }


def sort_batch_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key_fn(row: Dict[str, Any]) -> tuple[int, str, int]:
        timestamp = str(row.get("timestamp") or "").strip()
        if timestamp:
            return (0, timestamp, int(row.get("row_index", 0)))
        return (1, "", int(row.get("row_index", 0)))

    return sorted(rows, key=key_fn)


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
            "weights": {"heuristic_live_model": 1.0},
            "version": "RailSense Sentinel Live",
            "required_columns": REQUIRED_COLUMNS,
            "raw_defaults": RAW_DEFAULTS,
            "feature_defaults": FEATURE_DEFAULTS,
            "batch_limits": {
                "max_rows": MAX_BATCH_ROWS,
                "max_file_bytes": MAX_BATCH_FILE_BYTES,
            },
        }
    )


@app.post("/api/predict")
@app.post("/svc/predict")
def predict_single() -> Any:
    payload = request.get_json(silent=True) or {}
    raw = {key: to_float(payload.get("raw", {}).get(key, default), default) for key, default in RAW_DEFAULTS.items()}
    overrides = {
        key: to_float(value, FEATURE_DEFAULTS[key])
        for key, value in payload.get("features", {}).items()
        if key in REQUIRED_COLUMNS and value is not None and value != ""
    }
    timestamp = str(payload.get("timestamp") or "")
    return jsonify(predict_from_payload(raw, overrides, timestamp))


@app.post("/api/explain")
@app.post("/svc/explain")
def explain_prediction() -> Any:
    payload = request.get_json(silent=True) or {}
    prediction = payload.get("prediction")
    if not isinstance(prediction, dict):
        raw = {key: to_float(payload.get("raw", {}).get(key, default), default) for key, default in RAW_DEFAULTS.items()}
        overrides = {
            key: to_float(value, FEATURE_DEFAULTS[key])
            for key, value in payload.get("features", {}).items()
            if key in REQUIRED_COLUMNS and value is not None and value != ""
        }
        prediction = predict_from_payload(raw, overrides, str(payload.get("timestamp") or ""))
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

    raw_bytes = upload.stream.read()
    if len(raw_bytes) > MAX_BATCH_FILE_BYTES:
        return jsonify({"error": f"CSV file must be under {MAX_BATCH_FILE_BYTES // 1000} KB."}), 400

    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return jsonify({"error": "CSV must include a header row."}), 400

    missing = [col for col in BATCH_RAW_COLUMNS if col not in reader.fieldnames]
    if missing:
        return jsonify({"error": f"CSV is missing required raw columns: {', '.join(missing)}"}), 400

    outputs = []
    for idx, row in enumerate(reader):
        if idx >= MAX_BATCH_ROWS:
            return jsonify({"error": f"CSV can contain at most {MAX_BATCH_ROWS} data rows."}), 400
        raw = {key: to_float(row.get(key), RAW_DEFAULTS[key]) for key in RAW_DEFAULTS}
        data = predict_from_payload(raw, {}, str(row.get("timestamp", "")))
        outputs.append(
            {
                "row_index": idx,
                "timestamp": str(row.get("timestamp", "")),
                **raw,
                "label": data["alert_level"],
                "risk_score": data["railsense_score"],
                "confidence": data["confidence"],
            }
        )

    if not outputs:
        return jsonify({"error": "CSV has no data rows."}), 400

    outputs = sort_batch_rows(outputs)
    scores = [item["risk_score"] for item in outputs]
    levels = [item["label"] for item in outputs]
    summary = {
        "rows": len(outputs),
        "average_score": sum(scores) / len(scores),
        "max_score": max(scores),
        "critical_count": sum(level == "CRITICAL" for level in levels),
        "warning_count": sum(level == "WARNING" for level in levels),
        "normal_count": sum(level == "NORMAL" for level in levels),
    }
    return jsonify({"summary": summary, "rows": outputs})


@app.post("/api/explain-batch")
@app.post("/svc/explain-batch")
def explain_batch() -> Any:
    payload = request.get_json(silent=True) or {}
    summary = payload.get("summary")
    rows = payload.get("rows")
    if not isinstance(summary, dict) or not isinstance(rows, list):
        return jsonify({"error": "Batch summary and rows are required."}), 400
    try:
        insight = generate_batch_gemini_insight(summary, rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"insight": insight, "model": GEMINI_MODEL})


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


