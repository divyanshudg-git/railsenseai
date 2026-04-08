from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class PhysicsSignal:
    name: str
    score: float
    raw_value: float
    threshold: float
    description: str
    failure_mode: str


@dataclass
class PTADOutput:
    timestamp: Optional[str]
    railsense_score: float
    alert_level: str
    confidence: float
    physics_score: float
    temporal_score: float
    statistical_score: float
    top_physics_signals: List[PhysicsSignal]
    dominant_failure_mode: str
    recommended_action: str
    fusion_weights: Dict[str, float]
    score_components: Dict[str, float]


class PhysicsEngine:
    def __init__(self) -> None:
        self.thresholds = {
            "duty_warn": 0.92,
            "duty_crit": 0.99,
            "temp_warn": 72.0,
            "temp_crit": 78.0,
            "motor_warn": 5.50,
            "motor_crit": 5.90,
            "variance_low_warn": 2.0,
            "variance_low_crit": 0.8,
            "pdiff_warn": 0.015,
            "pdiff_crit": 0.025,
            "divergence_warn": 2.0,
            "divergence_crit": 4.0,
        }

    def _sigmoid(self, value: float, warn: float, crit: float, invert: bool = False) -> float:
        if invert:
            value, warn, crit = -value, -warn, -crit
        if value <= warn:
            return 0.0
        if value >= crit:
            return 1.0
        scaled = (value - warn) / (crit - warn + 1e-10)
        return float(3 * scaled**2 - 2 * scaled**3)

    def evaluate(self, features: Dict[str, float]) -> List[PhysicsSignal]:
        duty = features.get("duty_cycle_5min", 0)
        temp = features.get("Oil_temperature", 60)
        motor = features.get("Motor_current", 0)
        var = features.get("pressure_variance_10min", 5)
        eff = features.get("compressor_efficiency", 100)
        p_diff = abs(features.get("pressure_diff", 0))
        div = features.get("sensor_divergence", 0.5)
        mismatch = features.get("comp_mpg_disagreement", 0)
        motor_on = motor > 4.0
        compound = (eff < 3.0) and (duty > 0.90) and (motor > 5.0)
        return [
            PhysicsSignal("P1_duty", self._sigmoid(duty, 0.92, 0.99), duty, 0.92, f"Duty={duty:.3f}", "COMPRESSOR_OVERLOAD"),
            PhysicsSignal("P2_temp", self._sigmoid(temp, 72, 78), temp, 72, f"Oil={temp:.1f}C", "THERMAL_DEGRADATION"),
            PhysicsSignal("P3_motor", self._sigmoid(motor, 5.5, 5.9), motor, 5.5, f"Motor={motor:.2f}A", "COMPRESSOR_OVERLOAD"),
            PhysicsSignal("P4_var", self._sigmoid(var, 2.0, 0.8, invert=True) if motor_on else 0.0, var, 2.0, f"Var={var:.4f}", "AIR_LEAK_PRESSURE"),
            PhysicsSignal("P5_compound", 1.0 if compound else 0.0, eff, 3.0, f"Compound:eff={eff:.2f}", "EFFICIENCY_COLLAPSE"),
            PhysicsSignal("P6_pdiff", self._sigmoid(p_diff, 0.015, 0.025), p_diff, 0.015, f"pdiff={p_diff:.4f}", "AIR_LEAK_PRESSURE"),
            PhysicsSignal("P7_div", self._sigmoid(div, 2.0, 4.0), div, 2.0, f"div={div:.3f}", "AIR_LEAK_INSTAB"),
            PhysicsSignal("P8_valve", float(mismatch), mismatch, 0.5, "COMP/MPG", "VALVE_FAULT"),
        ]

    def aggregate(self, signals: List[PhysicsSignal]) -> float:
        scores = np.array([signal.score for signal in signals], dtype=float)
        weights = np.array([0.30, 0.20, 0.18, 0.12, 0.10, 0.02, 0.04, 0.04], dtype=float)
        weighted = float(np.dot(scores, weights))
        primary_flags = sum([scores[0] > 0.3, scores[1] > 0.3, scores[2] > 0.3])
        if primary_flags == 3:
            weighted = min(1.0, weighted * 1.5)
        elif primary_flags == 2:
            weighted = min(1.0, weighted * 1.2)
        return float(np.clip(weighted, 0, 1))


class TemporalEngine:
    TEMPORAL_COLS = [
        "T1_motor_overload_duration",
        "T2_oil_temp_slope_30min",
        "T3_lps_trend_1hr",
        "T4_pressure_instability_accel",
        "T5_efficiency_trend_1hr",
        "T6_divergence_accel",
    ]

    def __init__(self) -> None:
        self.baselines = {}
        self.fitted = False
        self.abs_thresholds = {
            "T1_motor_overload_duration": {"warn": 600, "crit": 1800},
            "T2_oil_temp_slope_30min": {"warn": 0.05, "crit": 0.20},
            "T3_lps_trend_1hr": {"warn": 0.01, "crit": 0.05},
            "T4_pressure_instability_accel": {"warn": 0.001, "crit": 0.005},
            "T5_efficiency_trend_1hr": {"warn": -1.0, "crit": -3.0},
            "T6_divergence_accel": {"warn": 0.001, "crit": 0.005},
        }

    def compute(self, df: pd.DataFrame, gap_col: str = "gap_flag") -> pd.DataFrame:
        frame = df.copy()
        if "timestamp" not in frame.columns:
            frame["timestamp"] = pd.date_range("2026-01-01", periods=len(frame), freq="min")
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        frame["_seg"] = frame[gap_col].cumsum() if gap_col in frame.columns else 0

        def safe_slope(values: np.ndarray) -> float:
            if len(values) < 10:
                return 0.0
            try:
                return float(np.polyfit(np.arange(len(values)), values, 1)[0])
            except Exception:
                return 0.0

        frame["_mh"] = (frame["Motor_current"] > 5.5).astype(float)
        groups = (frame["_mh"] != frame["_mh"].shift()).cumsum()
        frame["T1_motor_overload_duration"] = (frame.groupby(groups)["_mh"].transform("cumsum") * frame["_mh"]).astype("float32")

        for col, source, window, min_periods in [
            ("T2_oil_temp_slope_30min", "Oil_temperature", 1800, 60),
            ("T3_lps_trend_1hr", "LPS_freq_10min", 3600, 300),
            ("T5_efficiency_trend_1hr", "compressor_efficiency", 3600, 300),
            ("T6_divergence_accel", "sensor_divergence", 1800, 300),
        ]:
            frame[col] = (
                frame.groupby("_seg")[source]
                .transform(lambda x: x.rolling(window, min_periods=min_periods).apply(safe_slope, raw=True))
                .fillna(0)
                .astype("float32")
            )

        frame["_pv"] = (
            frame.groupby("_seg")["pressure_variance_10min"]
            .transform(lambda x: x.rolling(600, min_periods=60).mean())
            .fillna(0)
        )
        frame["T4_pressure_instability_accel"] = (
            frame.groupby("_seg")["_pv"]
            .transform(lambda x: x.rolling(1800, min_periods=300).apply(safe_slope, raw=True))
            .fillna(0)
            .astype("float32")
        )

        frame.drop(columns=["_mh", "_pv", "_seg"], inplace=True, errors="ignore")
        return frame

    def score_row(self, features: Dict[str, float]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        weights = {
            "T1_motor_overload_duration": 0.35,
            "T2_oil_temp_slope_30min": 0.25,
            "T3_lps_trend_1hr": 0.15,
            "T4_pressure_instability_accel": 0.10,
            "T5_efficiency_trend_1hr": 0.10,
            "T6_divergence_accel": 0.05,
        }
        for col in self.TEMPORAL_COLS:
            value = features.get(col, 0)
            if col not in self.abs_thresholds:
                scores[col] = 0.0
                continue
            thresholds = self.abs_thresholds[col]
            warn = thresholds["warn"]
            crit = thresholds["crit"]
            if col == "T5_efficiency_trend_1hr":
                value_abs = abs(min(value, 0))
                warn_abs = abs(warn)
                crit_abs = abs(crit)
                if value_abs <= warn_abs:
                    score = 0.0
                elif value_abs >= crit_abs:
                    score = 1.0
                else:
                    scaled = (value_abs - warn_abs) / (crit_abs - warn_abs + 1e-10)
                    score = float(3 * scaled**2 - 2 * scaled**3)
            elif col in {
                "T2_oil_temp_slope_30min",
                "T3_lps_trend_1hr",
                "T4_pressure_instability_accel",
                "T6_divergence_accel",
            }:
                value_pos = max(value, 0)
                if value_pos <= warn:
                    score = 0.0
                elif value_pos >= crit:
                    score = 1.0
                else:
                    scaled = (value_pos - warn) / (crit - warn + 1e-10)
                    score = float(3 * scaled**2 - 2 * scaled**3)
            else:
                if value <= warn:
                    score = 0.0
                elif value >= crit:
                    score = 1.0
                else:
                    scaled = (value - warn) / (crit - warn + 1e-10)
                    score = float(3 * scaled**2 - 2 * scaled**3)
            scores[col] = float(np.clip(score, 0, 1))
        aggregate = sum(scores.get(col, 0) * weight for col, weight in weights.items())
        scores["temporal_aggregate"] = float(np.clip(aggregate, 0, 1))
        return scores


class StatisticalEngine:
    def __init__(self) -> None:
        self.medians = {}
        self.mads = {}
        self.feature_cols = []
        self.fitted = False

    def score_row(self, features: Dict[str, float]) -> Dict[str, float]:
        z_scores = {}
        for col in self.feature_cols:
            value = features.get(col, self.medians.get(col, 0))
            mad = self.mads.get(col, 1) or 1
            median = self.medians.get(col, 0)
            z_scores[col] = float(0.6745 * abs(value - median) / mad)
        if not z_scores:
            return {"statistical_aggregate": 0.0}
        p90_z = np.percentile(list(z_scores.values()), 90)
        aggregate = float(np.clip((p90_z - 3.0) / 5.0, 0, 1))
        result = {f"z_{col}": float(np.clip(score / 8, 0, 1)) for col, score in z_scores.items()}
        result["statistical_aggregate"] = aggregate
        return result


class FusionLayer:
    def __init__(self) -> None:
        self.weights = {"physics": 0.55, "temporal": 0.15, "statistical": 0.30}
        self.threshold = 0.60
        self.fitted = False

    def fuse(self, physics_score: float, temporal_score: float, statistical_score: float) -> tuple[float, str, float]:
        weights = self.weights
        score = float(
            np.clip(
                weights["physics"] * physics_score
                + weights["temporal"] * temporal_score
                + weights["statistical"] * statistical_score,
                0,
                1,
            )
        )
        confidence = float(np.clip(abs(score - self.threshold) / 0.3, 0, 1))
        if score >= self.threshold * 1.25:
            level = "CRITICAL"
        elif score >= self.threshold:
            level = "WARNING"
        else:
            level = "NORMAL"
        return score, level, confidence


class AlertEngine:
    def recommended_action(self, level: str, mode: str) -> str:
        actions = {
            ("CRITICAL", "COMPRESSOR_OVERLOAD"): "IMMEDIATE: Remove train. Motor overloading.",
            ("CRITICAL", "THERMAL_DEGRADATION"): "IMMEDIATE: Check oil/cooling. Temp critical.",
            ("CRITICAL", "EFFICIENCY_COLLAPSE"): "IMMEDIATE: Compressor stuck. Inspect valves.",
            ("CRITICAL", "AIR_LEAK_PRESSURE"): "IMMEDIATE: Pressure divergence. Inspect pipes.",
            ("WARNING", "COMPRESSOR_OVERLOAD"): "SCHEDULE: Motor elevated. Check at depot.",
            ("WARNING", "THERMAL_DEGRADATION"): "MONITOR: Oil temp elevated.",
            ("NORMAL", ""): "No action required.",
        }
        return actions.get((level, mode), actions.get(("NORMAL", ""), "Monitor system."))


class PTADv2Runtime:
    VERSION = "2.4"

    def __init__(self) -> None:
        self.physics = PhysicsEngine()
        self.temporal = TemporalEngine()
        self.statistical = StatisticalEngine()
        self.fusion = FusionLayer()
        self.alert = AlertEngine()
        self.fitted = False
        self.feature_cols = []
        self.all_features = []

    @classmethod
    def from_legacy(cls, legacy_model: object) -> "PTADv2Runtime":
        model = cls()
        model.fitted = getattr(legacy_model, "fitted", False)
        model.feature_cols = list(getattr(legacy_model, "feature_cols", []))
        model.all_features = list(getattr(legacy_model, "all_features", []))

        for name in ["physics", "temporal", "statistical", "fusion", "alert"]:
            legacy_part = getattr(legacy_model, name, None)
            runtime_part = getattr(model, name)
            if legacy_part is not None and hasattr(legacy_part, "__dict__"):
                runtime_part.__dict__.update(dict(legacy_part.__dict__))
        return model

    def predict_single(self, features: Dict[str, float], timestamp: Optional[str] = None) -> PTADOutput:
        physics_signals = self.physics.evaluate(features)
        physics_score = self.physics.aggregate(physics_signals)
        temporal_score = self.temporal.score_row(features).get("temporal_aggregate", 0.0)
        statistical_score = self.statistical.score_row(features).get("statistical_aggregate", 0.0)
        score, level, confidence = self.fusion.fuse(physics_score, temporal_score, statistical_score)
        top_signals = sorted(physics_signals, key=lambda signal: signal.score, reverse=True)[:3]
        dominant_mode = top_signals[0].failure_mode if top_signals and top_signals[0].score > 0.1 else ""
        return PTADOutput(
            timestamp=timestamp,
            railsense_score=score,
            alert_level=level,
            confidence=confidence,
            physics_score=physics_score,
            temporal_score=temporal_score,
            statistical_score=statistical_score,
            top_physics_signals=top_signals,
            dominant_failure_mode=dominant_mode,
            recommended_action=self.alert.recommended_action(level, dominant_mode),
            fusion_weights=self.fusion.weights,
            score_components={
                "physics": self.fusion.weights["physics"] * physics_score,
                "temporal": self.fusion.weights["temporal"] * temporal_score,
                "statistical": self.fusion.weights["statistical"] * statistical_score,
            },
        )

    def predict_batch(self, df: pd.DataFrame) -> tuple[np.ndarray, List[str], List[PTADOutput]]:
        frame = self.temporal.compute(df)
        scores = []
        levels = []
        outputs: List[PTADOutput] = []
        for _, row in frame.iterrows():
            output = self.predict_single(row.to_dict(), str(row.get("timestamp", "")))
            scores.append(output.railsense_score)
            levels.append(output.alert_level)
            outputs.append(output)
        return np.asarray(scores, dtype=float), levels, outputs
