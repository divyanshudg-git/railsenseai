import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { motion as Motion } from 'framer-motion';
import { z } from 'zod';
import { CheckCircle2, Gauge, History, TriangleAlert, Upload, WandSparkles } from 'lucide-react';
import { getConfig, predictBatch, predictSingle } from '../lib/api';
import { CinematicSection } from '../components/CinematicSection';
import { PageTransition } from '../components/PageTransition';

const FALLBACK_RAW = {
  TP2: 8.2,
  TP3: 8,
  H1: 8.1,
  DV_pressure: 8.3,
  Reservoirs: 8.1,
  Oil_temperature: 62,
  Motor_current: 4.2,
  COMP: 1,
  MPG: 1,
  LPS: 1,
};

const FALLBACK_FEATURES = {
  pressure_diff: 0.02,
  LPS_freq_10min: 0.02,
  sensor_divergence: 0.15,
  compressor_efficiency: 0.0045,
  duty_cycle_5min: 0.84,
  thermal_index: 0.48,
  reservoir_panel_ratio: 0.98,
  pressure_variance_10min: 3.8,
  motor_thermal_stress: 0.35,
  current_spike_freq: 0.08,
  load_cycle_regularity: 0.72,
  towers_switching_freq: 0.05,
  comp_mpg_disagreement: 0,
  TP2: 8.2,
  TP3: 8,
  H1: 8.1,
  DV_pressure: 8.3,
  Reservoirs: 8.1,
  Oil_temperature: 62,
  Motor_current: 4.2,
};

const HISTORY_STORAGE_KEY = 'railsense.prediction.history.v1';
const HISTORY_LIMIT = 48;

const signalNameMap = {
  P1_duty: 'Running continuously for too long',
  P2_temp: 'Temperature is unusually high',
  P3_motor: 'Motor effort is very high',
  P4_var: 'Pressure pattern feels unstable',
  P5_compound: 'Multiple stress signs appearing together',
  P6_pdiff: 'Pressure gap is unusual',
  P7_div: 'Sensor readings disagree more than normal',
  P8_valve: 'Valve behavior mismatch is detected',
};

const laymanSchema = z.object({
  timestamp: z.string().optional(),
  workload: z.number().min(0).max(100),
  heat: z.number().min(0).max(100),
  vibration: z.number().min(0).max(100),
  pressureInstability: z.number().min(0).max(100),
  startStopPattern: z.number().min(0).max(100),
  overdueMaintenanceWeeks: z.number().min(0).max(52),
  warningLight: z.boolean(),
  unusualSmell: z.boolean(),
  valveMismatch: z.boolean(),
  emergencySymptoms: z.boolean(),
});

const laymanDefaults = {
  timestamp: '',
  workload: 38,
  heat: 28,
  vibration: 22,
  pressureInstability: 18,
  startStopPattern: 25,
  overdueMaintenanceWeeks: 4,
  warningLight: false,
  unusualSmell: false,
  valveMismatch: false,
  emergencySymptoms: false,
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function scoreColor(level) {
  if (level === 'CRITICAL') return 'text-rose-200 border-rose-300/30 bg-rose-300/15';
  if (level === 'WARNING') return 'text-amber-100 border-amber-200/30 bg-amber-300/15';
  return 'text-emerald-100 border-emerald-200/30 bg-emerald-300/15';
}

function laymanScoreLabel(value) {
  if (value >= 80) return 'Very High';
  if (value >= 60) return 'High';
  if (value >= 35) return 'Moderate';
  if (value >= 15) return 'Low';
  return 'Very Low';
}

function riskMessage(level) {
  if (level === 'CRITICAL') {
    return 'High risk right now. Pause operation if possible and call maintenance immediately.';
  }
  if (level === 'WARNING') {
    return 'Medium risk. Keep running with caution and schedule inspection soon.';
  }
  return 'System looks stable at the moment. Continue monitoring as normal.';
}

function formatHistoryTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unknown time';
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

function historyTone(level) {
  if (level === 'CRITICAL') {
    return 'border-rose-300/30 bg-rose-300/10 text-rose-100';
  }
  if (level === 'WARNING') {
    return 'border-amber-300/30 bg-amber-300/10 text-amber-100';
  }
  return 'border-emerald-300/30 bg-emerald-300/10 text-emerald-100';
}

function historyDotTone(level) {
  if (level === 'CRITICAL') return 'bg-rose-300';
  if (level === 'WARNING') return 'bg-amber-300';
  return 'bg-emerald-300';
}

function createHistoryId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function nowIsoString() {
  return new Date().toISOString();
}

function readHistoryFromStorage() {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === 'object' && typeof item.id === 'string')
      .slice(0, HISTORY_LIMIT)
      .map((item) => ({
        id: item.id,
        createdAt: typeof item.createdAt === 'string' ? item.createdAt : nowIsoString(),
        alertLevel: item.alertLevel || 'NORMAL',
        score: Number(item.score || 0),
        confidence: Number(item.confidence || 0),
        recommendedAction: item.recommendedAction || 'No recommendation provided.',
        dominantFailureMode: item.dominantFailureMode || 'No dominant pattern',
        topSignalName: item.topSignalName || 'No strong signal',
        topSignalScore: Number(item.topSignalScore || 0),
        mode: item.mode || 'Guided',
        operatorSummary: item.operatorSummary || 'No operator summary',
        laymanSnapshot: item.laymanSnapshot || null,
      }));
  } catch {
    return [];
  }
}

function mapLaymanToModel(inputs, rawBase, featureBase) {
  const workload = inputs.workload / 100;
  const heat = inputs.heat / 100;
  const vibration = inputs.vibration / 100;
  const pressureInstability = inputs.pressureInstability / 100;
  const startStopPattern = inputs.startStopPattern / 100;
  const maintenanceOverdue = inputs.overdueMaintenanceWeeks / 52;
  const warningFlag = inputs.warningLight ? 1 : 0;
  const smellFlag = inputs.unusualSmell ? 1 : 0;
  const valveFlag = inputs.valveMismatch ? 1 : 0;
  const emergencyFlag = inputs.emergencySymptoms ? 1 : 0;

  const emergencyBoost = emergencyFlag ? 0.26 : 0;

  const raw = {
    ...rawBase,
    TP2: clamp((rawBase.TP2 ?? 8.2) + 0.5 * workload + 0.2 * pressureInstability + emergencyBoost, 7.2, 10.5),
    TP3: clamp((rawBase.TP3 ?? 8) - 0.18 * pressureInstability + 0.1 * workload - 0.1 * emergencyBoost, 6.8, 10.2),
    H1: clamp((rawBase.H1 ?? 8.1) + 0.42 * vibration + 0.12 * workload + 0.2 * emergencyBoost, 6.9, 10.8),
    DV_pressure: clamp((rawBase.DV_pressure ?? 8.3) + 0.25 * workload + 0.24 * pressureInstability + 0.35 * emergencyBoost, 7.1, 11.3),
    Reservoirs: clamp((rawBase.Reservoirs ?? 8.1) - 0.72 * pressureInstability + 0.1 * workload - 0.2 * emergencyBoost, 6.2, 10.2),
    Oil_temperature: clamp((rawBase.Oil_temperature ?? 62) + 16 * heat + 4.5 * smellFlag + 2.4 * maintenanceOverdue + 6 * emergencyBoost, 44, 95),
    Motor_current: clamp((rawBase.Motor_current ?? 4.2) + 1.35 * workload + 0.55 * heat + 0.3 * warningFlag + 0.7 * emergencyBoost, 2.2, 8.4),
    COMP: workload > 0.15 || emergencyFlag ? 1 : 0,
    MPG: valveFlag ? 0 : 1,
    LPS: pressureInstability > 0.55 || emergencyFlag ? 0 : 1,
  };

  const pressureDiff = Math.abs(raw.TP2 - raw.TP3);
  const sensorDivergence = Math.abs(raw.H1 - raw.TP3) + 1.6 * vibration + 0.9 * emergencyBoost;
  const compressorEfficiency = clamp(pressureDiff / (Math.abs(raw.Motor_current) + 1e-3), 0.001, 0.9);
  const thermalIndex = clamp((raw.Oil_temperature - 50) / 30, 0, 2);
  const reservoirPanelRatio = clamp(raw.Reservoirs / (raw.DV_pressure + 1e-3), 0.5, 1.2);
  const pressureVariance = clamp(4.4 - 3.0 * pressureInstability + 1.3 * startStopPattern + 0.7 * emergencyBoost, 0.2, 7.0);
  const motorThermalStress = clamp((raw.Motor_current / 6) * (raw.Oil_temperature / 80), 0, 2);
  const currentSpikeFreq = clamp(0.05 + 0.68 * startStopPattern + 0.2 * warningFlag + 0.1 * emergencyBoost, 0, 1);
  const loadCycleRegularity = clamp(1 - 0.64 * startStopPattern - 0.18 * vibration, 0, 1);
  const towersSwitchingFreq = clamp(0.03 + 0.58 * startStopPattern, 0, 1);
  const lpsFreq10Min = clamp(0.02 + 0.42 * startStopPattern + 0.14 * pressureInstability, 0, 1);
  const dutyCycle = clamp(0.46 + 0.48 * workload + 0.09 * warningFlag + 0.08 * emergencyBoost, 0, 1);

  const features = {
    ...featureBase,
    pressure_diff: pressureDiff,
    LPS_freq_10min: lpsFreq10Min,
    sensor_divergence: sensorDivergence,
    compressor_efficiency: compressorEfficiency,
    duty_cycle_5min: dutyCycle,
    thermal_index: thermalIndex,
    reservoir_panel_ratio: reservoirPanelRatio,
    pressure_variance_10min: pressureVariance,
    motor_thermal_stress: motorThermalStress,
    current_spike_freq: currentSpikeFreq,
    load_cycle_regularity: loadCycleRegularity,
    towers_switching_freq: towersSwitchingFreq,
    comp_mpg_disagreement: valveFlag ? 1 : 0,
    TP2: raw.TP2,
    TP3: raw.TP3,
    H1: raw.H1,
    DV_pressure: raw.DV_pressure,
    Reservoirs: raw.Reservoirs,
    Oil_temperature: raw.Oil_temperature,
    Motor_current: raw.Motor_current,
  };

  return { raw, features };
}

function RangeField({ control, name, label, description }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <label className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-semibold text-slate-100">{label}</span>
            <span className="rounded-full border border-white/15 bg-white/5 px-2 py-1 text-xs text-slate-200">
              {laymanScoreLabel(field.value)}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">{description}</p>
          <input
            type="range"
            min={0}
            max={100}
            value={field.value}
            onChange={(event) => field.onChange(Number(event.target.value))}
            className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/15 accent-cyan-300"
          />
          <div className="mt-1 flex justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500">
            <span>Low</span>
            <span>{field.value}</span>
            <span>High</span>
          </div>
        </label>
      )}
    />
  );
}

export function PredictionPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [batchResult, setBatchResult] = useState(null);
  const [expertMode, setExpertMode] = useState(false);
  const [rawInputs, setRawInputs] = useState(FALLBACK_RAW);
  const [featureInputs, setFeatureInputs] = useState(FALLBACK_FEATURES);
  const [historyEntries, setHistoryEntries] = useState(readHistoryFromStorage);
  const [historyFilter, setHistoryFilter] = useState('ALL');
  const [selectedHistoryId, setSelectedHistoryId] = useState(null);

  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(laymanSchema),
    defaultValues: laymanDefaults,
    mode: 'onChange',
  });

  const watched = useWatch({ control });

  const configQuery = useQuery({
    queryKey: ['api-config'],
    queryFn: getConfig,
  });

  const singleMutation = useMutation({
    mutationFn: predictSingle,
  });

  const batchMutation = useMutation({
    mutationFn: predictBatch,
    onSuccess: (data) => {
      setBatchResult(data);
    },
  });

  const topSignals = prediction?.top_physics_signals || [];
  const normalizedScore = useMemo(() => {
    if (!prediction) return 0;
    return Math.max(0, Math.min(1, prediction.railsense_score ?? 0));
  }, [prediction]);

  const historyCounts = useMemo(() => {
    const counts = {
      ALL: historyEntries.length,
      CRITICAL: 0,
      WARNING: 0,
      NORMAL: 0,
    };
    historyEntries.forEach((entry) => {
      if (entry.alertLevel === 'CRITICAL') counts.CRITICAL += 1;
      else if (entry.alertLevel === 'WARNING') counts.WARNING += 1;
      else counts.NORMAL += 1;
    });
    return counts;
  }, [historyEntries]);

  const filteredHistory = useMemo(() => {
    if (historyFilter === 'ALL') return historyEntries;
    return historyEntries.filter((entry) => entry.alertLevel === historyFilter);
  }, [historyEntries, historyFilter]);

  const selectedHistory = useMemo(() => {
    return filteredHistory.find((entry) => entry.id === selectedHistoryId) || filteredHistory[0] || null;
  }, [filteredHistory, selectedHistoryId]);

  useEffect(() => {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(historyEntries));
  }, [historyEntries]);

  function updateRaw(key, value) {
    setRawInputs((prev) => ({ ...prev, [key]: Number(value) }));
  }

  function updateFeature(key, value) {
    setFeatureInputs((prev) => ({ ...prev, [key]: Number(value) }));
  }

  function applyLaymanDefaults() {
    reset(laymanDefaults);
  }

  function applyStressPreset() {
    reset({
      ...laymanDefaults,
      workload: 89,
      heat: 90,
      vibration: 78,
      pressureInstability: 72,
      startStopPattern: 68,
      overdueMaintenanceWeeks: 18,
      warningLight: true,
      unusualSmell: true,
      valveMismatch: true,
      emergencySymptoms: true,
    });
  }

  function applyApiDefaultsToExpert() {
    if (!configQuery.data) return;
    if (configQuery.data.raw_defaults) setRawInputs(configQuery.data.raw_defaults);
    if (configQuery.data.feature_defaults) setFeatureInputs(configQuery.data.feature_defaults);
  }

  function appendToHistory(data, values, usedExpertMode) {
    const topSignal = data?.top_physics_signals?.[0];
    const entry = {
      id: createHistoryId(),
      createdAt: nowIsoString(),
      alertLevel: data?.alert_level || 'NORMAL',
      score: Number(data?.railsense_score || 0),
      confidence: Number(data?.confidence || 0),
      recommendedAction: data?.recommended_action || 'No recommendation provided.',
      dominantFailureMode: data?.dominant_failure_mode || 'No dominant pattern',
      topSignalName: topSignal ? signalNameMap[topSignal.name] || topSignal.name : 'No strong signal',
      topSignalScore: Number(topSignal?.score || 0),
      mode: usedExpertMode ? 'Expert' : 'Guided',
      operatorSummary: usedExpertMode
        ? 'Prediction used technical expert values.'
        : `Load ${laymanScoreLabel(values.workload)} | Heat ${laymanScoreLabel(values.heat)} | Vibration ${laymanScoreLabel(values.vibration)}`,
      laymanSnapshot: usedExpertMode ? null : values,
    };

    setHistoryEntries((prev) => [entry, ...prev].slice(0, HISTORY_LIMIT));
    setSelectedHistoryId(entry.id);
  }

  function clearHistory() {
    setHistoryEntries([]);
    setSelectedHistoryId(null);
  }

  function restoreGuidedSnapshot(entry) {
    if (!entry?.laymanSnapshot) return;
    setExpertMode(false);
    reset({
      ...laymanDefaults,
      ...entry.laymanSnapshot,
    });
  }

  function submitPrediction(values) {
    const rawBase = configQuery.data?.raw_defaults ?? FALLBACK_RAW;
    const featureBase = configQuery.data?.feature_defaults ?? FALLBACK_FEATURES;
    const mapped = mapLaymanToModel(values, rawBase, featureBase);
    const payload = {
      timestamp: values.timestamp || '',
      raw: expertMode ? rawInputs : mapped.raw,
      features: expertMode ? featureInputs : mapped.features,
    };

    if (!expertMode) {
      setRawInputs(mapped.raw);
      setFeatureInputs(mapped.features);
    }

    singleMutation.mutate(payload, {
      onSuccess: (data) => {
        setPrediction(data);
        appendToHistory(data, values, expertMode);
      },
    });
  }

  function submitBatch(event) {
    event.preventDefault();
    if (!selectedFile) return;
    batchMutation.mutate(selectedFile);
  }

  return (
    <PageTransition>
      <CinematicSection className="mx-auto w-full max-w-7xl px-6 pt-14 md:px-10">
        <div className="rounded-[2rem] border border-white/10 bg-white/[0.04] p-8 md:p-10">
          <p className="text-xs uppercase tracking-[0.3em] text-cyan-200">Prediction Console</p>
          <h1 className="mt-4 max-w-4xl font-display text-4xl tracking-tight text-slate-50 md:text-5xl">
            Simple machine health check for everyone, not only engineers.
          </h1>
          <p className="mt-5 max-w-3xl text-slate-300">
            Tell us what you observe in plain language. We convert that into model inputs automatically and return a clear
            risk verdict with easy actions.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={applyStressPreset}
              className="inline-flex items-center gap-2 rounded-full border border-cyan-200/25 bg-cyan-300/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-300/20"
            >
              <WandSparkles className="h-4 w-4" />
              Demo: Risky Situation
            </button>
            <button
              type="button"
              onClick={applyLaymanDefaults}
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Reset Inputs
            </button>
            {configQuery.data?.threshold ? (
              <span className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-slate-200">
                System threshold: <strong>{Number(configQuery.data.threshold).toFixed(3)}</strong>
              </span>
            ) : null}
          </div>
        </div>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-10 grid w-full max-w-7xl gap-6 px-6 md:grid-cols-[1.2fr_0.8fr] md:px-10">
        <form
          onSubmit={handleSubmit(submitPrediction)}
          className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 md:p-8"
        >
          <h2 className="font-display text-2xl text-slate-50">Tell us what you observe</h2>
          <p className="mt-2 text-sm text-slate-300">
            No technical terms needed. Move sliders based on what operators are seeing or hearing.
          </p>

          <label className="mt-5 block">
            <span className="text-xs uppercase tracking-[0.2em] text-slate-400">Optional time note</span>
            <input
              {...register('timestamp')}
              placeholder="Example: today morning shift"
              className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-300/40"
            />
          </label>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <RangeField
              control={control}
              name="workload"
              label="How hard is the machine working?"
              description="Low means easy load, high means heavy or continuous load."
            />
            <RangeField
              control={control}
              name="heat"
              label="How hot does it feel?"
              description="Estimate from touch-safe surfaces, sensors, or operator feeling."
            />
            <RangeField
              control={control}
              name="vibration"
              label="Any unusual vibration or noise?"
              description="Low is smooth behavior, high is shaking, rattling, or odd sounds."
            />
            <RangeField
              control={control}
              name="pressureInstability"
              label="How unstable is pressure behavior?"
              description="High means pressure fluctuations are irregular or hard to control."
            />
            <RangeField
              control={control}
              name="startStopPattern"
              label="How frequent are starts/stops?"
              description="High means cycling too often in a short period."
            />
            <Controller
              control={control}
              name="overdueMaintenanceWeeks"
              render={({ field }) => (
                <label className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-slate-100">Maintenance delay (weeks)</span>
                    <span className="rounded-full border border-white/15 bg-white/5 px-2 py-1 text-xs text-slate-200">
                      {field.value}w
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={52}
                    value={field.value}
                    onChange={(event) => field.onChange(Number(event.target.value))}
                    className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/15 accent-amber-300"
                  />
                  <div className="mt-1 flex justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500">
                    <span>On time</span>
                    <span>Overdue</span>
                  </div>
                </label>
              )}
            />
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {[
              { name: 'warningLight', label: 'Warning light is active' },
              { name: 'unusualSmell', label: 'Burning or unusual smell noticed' },
              { name: 'valveMismatch', label: 'Valve behavior seems inconsistent' },
              { name: 'emergencySymptoms', label: 'Emergency-like symptoms observed' },
            ].map((item) => (
              <label
                key={item.name}
                className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/10 bg-slate-900/55 px-4 py-3 text-sm text-slate-200"
              >
                <input type="checkbox" {...register(item.name)} className="h-4 w-4 accent-cyan-300" />
                {item.label}
              </label>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={singleMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-300 to-emerald-200 px-6 py-3 text-sm font-bold text-slate-950 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Gauge className="h-4 w-4" />
              {singleMutation.isPending ? 'Checking health...' : 'Check Machine Health'}
            </button>
            <button
              type="button"
              onClick={() => setExpertMode((prev) => !prev)}
              className="rounded-full border border-white/20 bg-white/5 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              {expertMode ? 'Exit Expert Mode' : 'Expert Mode'}
            </button>
          </div>

          {errors.root ? <p className="mt-3 text-sm text-rose-200">{errors.root.message}</p> : null}
          {singleMutation.isError ? <p className="mt-3 text-sm text-rose-200">{singleMutation.error.message}</p> : null}

          {expertMode ? (
            <details open className="mt-6 rounded-2xl border border-amber-300/25 bg-amber-300/5 p-4">
              <summary className="cursor-pointer text-sm font-semibold text-amber-100">
                Expert input panel (technical values)
              </summary>
              <p className="mt-2 text-xs text-amber-50/80">
                This panel is optional. If edited, these values are sent directly to the model.
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={applyApiDefaultsToExpert}
                  className="rounded-full border border-white/20 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-100"
                >
                  Apply API defaults
                </button>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-300">Raw</p>
                  {Object.entries(rawInputs).map(([key, value]) => (
                    <label key={key} className="grid gap-1">
                      <span className="text-[11px] text-slate-400">{key}</span>
                      <input
                        type="number"
                        step="0.001"
                        value={value}
                        onChange={(event) => updateRaw(key, event.target.value)}
                        className="rounded-lg border border-white/10 bg-slate-950/70 px-3 py-2 text-xs text-slate-100 outline-none focus:border-cyan-300/35"
                      />
                    </label>
                  ))}
                </div>
                <div className="max-h-[26rem] space-y-2 overflow-auto pr-1">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-300">Features</p>
                  {Object.entries(featureInputs).map(([key, value]) => (
                    <label key={key} className="grid gap-1">
                      <span className="text-[11px] text-slate-400">{key}</span>
                      <input
                        type="number"
                        step="0.001"
                        value={value}
                        onChange={(event) => updateFeature(key, event.target.value)}
                        className="rounded-lg border border-white/10 bg-slate-950/70 px-3 py-2 text-xs text-slate-100 outline-none focus:border-cyan-300/35"
                      />
                    </label>
                  ))}
                </div>
              </div>
            </details>
          ) : null}
        </form>

        <aside className="space-y-6">
          <Motion.div layout className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Health Result</p>
            {prediction ? (
              <>
                <div className="mt-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm text-slate-400">Risk score</p>
                    <p className="font-display text-5xl text-slate-50">{prediction.railsense_score.toFixed(3)}</p>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${scoreColor(prediction.alert_level)}`}
                  >
                    {prediction.alert_level}
                  </span>
                </div>
                <div className="mt-5 h-3 rounded-full bg-white/10">
                  <div
                    className="h-3 rounded-full bg-gradient-to-r from-cyan-300 via-emerald-200 to-amber-300"
                    style={{ width: `${Math.round(normalizedScore * 100)}%` }}
                  />
                </div>
                <p className="mt-4 rounded-xl border border-white/10 bg-slate-900/60 p-3 text-sm text-slate-100">
                  {riskMessage(prediction.alert_level)}
                </p>
                <p className="mt-3 text-sm text-slate-300">
                  <strong>Suggested action:</strong> {prediction.recommended_action}
                </p>
                <p className="mt-2 text-xs text-slate-400">
                  Confidence: {Math.round((prediction.confidence || 0) * 100)}%
                  {' | '}
                  Main pattern: {prediction.dominant_failure_mode || 'No dominant pattern'}
                </p>
              </>
            ) : (
              <p className="mt-4 text-sm text-slate-300">Submit observations to receive an easy-to-understand health result.</p>
            )}
          </Motion.div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">What you reported</p>
            <div className="mt-3 grid gap-2 text-sm text-slate-300">
              <p>Workload: {laymanScoreLabel(watched.workload || 0)}</p>
              <p>Heat: {laymanScoreLabel(watched.heat || 0)}</p>
              <p>Vibration/Noise: {laymanScoreLabel(watched.vibration || 0)}</p>
              <p>Pressure behavior: {laymanScoreLabel(watched.pressureInstability || 0)}</p>
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Why this result?</p>
            <div className="mt-4 space-y-3">
              {topSignals.length ? (
                topSignals.map((signal) => (
                  <article key={signal.name} className="rounded-2xl border border-white/10 bg-slate-900/70 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-slate-100">{signalNameMap[signal.name] || signal.name}</p>
                      <span className="text-xs uppercase text-slate-400">{Math.round((signal.score || 0) * 100)}%</span>
                    </div>
                    <div className="mt-2 h-2 rounded-full bg-white/10">
                      <div
                        className="h-2 rounded-full bg-cyan-300"
                        style={{ width: `${Math.round((signal.score || 0) * 100)}%` }}
                      />
                    </div>
                  </article>
                ))
              ) : (
                <p className="text-sm text-slate-300">Key reasons will appear after prediction.</p>
              )}
            </div>
          </div>
        </aside>
      </CinematicSection>

      <CinematicSection
        className="mx-auto mt-10 w-full max-w-7xl px-6 md:px-10"
        glowClass="from-cyan-300/14 via-transparent to-emerald-300/14"
      >
        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 md:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-cyan-200">Prediction History</p>
              <h2 className="mt-2 flex items-center gap-2 font-display text-2xl text-slate-50">
                <History className="h-5 w-5 text-cyan-200" />
                Timeline View
              </h2>
              <p className="mt-1 text-sm text-slate-300">
                Review past checks in time order and open any entry for full context.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {[
                { id: 'ALL', label: 'All' },
                { id: 'CRITICAL', label: 'Critical' },
                { id: 'WARNING', label: 'Warning' },
                { id: 'NORMAL', label: 'Normal' },
              ].map((filter) => (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => setHistoryFilter(filter.id)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] transition ${
                    historyFilter === filter.id
                      ? 'border-cyan-200/35 bg-cyan-300/15 text-cyan-100'
                      : 'border-white/15 bg-white/5 text-slate-300 hover:bg-white/10'
                  }`}
                >
                  {filter.label} ({historyCounts[filter.id]})
                </button>
              ))}
              <button
                type="button"
                onClick={clearHistory}
                disabled={!historyEntries.length}
                className="rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_1.08fr]">
            <div className="relative rounded-2xl border border-white/10 bg-slate-900/55 p-4">
              <div className="pointer-events-none absolute left-[18px] top-6 h-[calc(100%-3rem)] w-px bg-white/10" />
              <div className="max-h-[25rem] space-y-3 overflow-auto pr-1">
                {filteredHistory.length ? (
                  filteredHistory.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => setSelectedHistoryId(entry.id)}
                      className={`relative w-full rounded-2xl border px-4 py-3 pl-9 text-left transition ${
                        selectedHistory?.id === entry.id
                          ? `${historyTone(entry.alertLevel)} shadow-lg shadow-cyan-950/25`
                          : 'border-white/10 bg-white/[0.02] text-slate-100 hover:bg-white/[0.05]'
                      }`}
                    >
                      <span className={`absolute left-[14px] top-[20px] h-2.5 w-2.5 rounded-full ${historyDotTone(entry.alertLevel)}`} />
                      <p className="text-[11px] uppercase tracking-[0.2em] text-slate-400">{formatHistoryTime(entry.createdAt)}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold">{entry.alertLevel}</span>
                        <span className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-slate-300">
                          {entry.mode}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-300">{entry.operatorSummary}</p>
                    </button>
                  ))
                ) : (
                  <p className="rounded-xl border border-dashed border-white/15 bg-white/[0.02] p-5 text-sm text-slate-300">
                    No predictions in this filter yet. Run a health check to start building timeline history.
                  </p>
                )}
              </div>
            </div>

            <Motion.div layout className="rounded-2xl border border-white/10 bg-slate-900/55 p-5">
              {selectedHistory ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Selected event</p>
                      <p className="mt-1 text-sm text-slate-200">{formatHistoryTime(selectedHistory.createdAt)}</p>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${scoreColor(selectedHistory.alertLevel)}`}>
                      {selectedHistory.alertLevel}
                    </span>
                  </div>
                  <div className="mt-5">
                    <p className="text-sm text-slate-400">Risk score</p>
                    <p className="font-display text-5xl text-slate-50">{selectedHistory.score.toFixed(3)}</p>
                    <div className="mt-3 h-2 rounded-full bg-white/10">
                      <div
                        className="h-2 rounded-full bg-gradient-to-r from-cyan-300 via-emerald-200 to-amber-300"
                        style={{ width: `${Math.round(Math.min(1, Math.max(0, selectedHistory.score)) * 100)}%` }}
                      />
                    </div>
                  </div>
                  <div className="mt-4 rounded-xl border border-white/10 bg-slate-950/50 p-3 text-sm text-slate-100">
                    {selectedHistory.recommendedAction}
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Dominant pattern</p>
                      <p className="mt-1 text-sm text-slate-100">{selectedHistory.dominantFailureMode}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Top signal</p>
                      <p className="mt-1 text-sm text-slate-100">{selectedHistory.topSignalName}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        Signal influence: {Math.round(selectedHistory.topSignalScore * 100)}%
                      </p>
                    </div>
                  </div>
                  <p className="mt-4 text-xs text-slate-400">
                    Confidence: {Math.round(selectedHistory.confidence * 100)}% | Mode: {selectedHistory.mode}
                  </p>
                  {selectedHistory.laymanSnapshot ? (
                    <button
                      type="button"
                      onClick={() => restoreGuidedSnapshot(selectedHistory)}
                      className="mt-4 rounded-full border border-cyan-200/30 bg-cyan-300/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100 transition hover:bg-cyan-300/20"
                    >
                      Reuse this guided input
                    </button>
                  ) : null}
                </>
              ) : (
                <p className="text-sm text-slate-300">Select a timeline event to view detailed prediction context.</p>
              )}
            </Motion.div>
          </div>
        </div>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-10 w-full max-w-7xl px-6 pb-8 md:px-10">
        <form onSubmit={submitBatch} className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 md:p-8">
          <h2 className="font-display text-2xl text-slate-50">Batch prediction</h2>
          <p className="mt-2 text-sm text-slate-300">
            Upload a CSV to score many rows at once. This section is intended for technical or data teams.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-4">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-white/20 bg-white/5 px-4 py-2 text-sm text-slate-100 transition hover:bg-white/10">
              <Upload className="h-4 w-4" />
              <span>{selectedFile?.name || 'Choose CSV file'}</span>
              <input
                type="file"
                accept=".csv"
                onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                className="hidden"
              />
            </label>
            <button
              type="submit"
              disabled={!selectedFile || batchMutation.isPending}
              className="rounded-full bg-gradient-to-r from-amber-300 to-orange-200 px-5 py-2 text-sm font-bold text-slate-950 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {batchMutation.isPending ? 'Scoring...' : 'Run Batch'}
            </button>
          </div>

          {batchMutation.isError ? <p className="mt-3 text-sm text-rose-200">{batchMutation.error.message}</p> : null}

          {batchResult?.summary ? (
            <div className="mt-6 grid gap-4 md:grid-cols-4">
              <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                <p className="text-xs uppercase text-slate-400">Rows</p>
                <p className="mt-1 text-2xl font-semibold text-slate-100">{batchResult.summary.rows}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                <p className="text-xs uppercase text-slate-400">Critical</p>
                <p className="mt-1 text-2xl font-semibold text-rose-200">{batchResult.summary.critical_count}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                <p className="text-xs uppercase text-slate-400">Warning</p>
                <p className="mt-1 text-2xl font-semibold text-amber-200">{batchResult.summary.warning_count}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                <p className="text-xs uppercase text-slate-400">Normal</p>
                <p className="mt-1 text-2xl font-semibold text-emerald-200">{batchResult.summary.normal_count}</p>
              </div>
            </div>
          ) : null}
        </form>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-4 w-full max-w-7xl px-6 pb-16 md:px-10">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-300">
            <div className="mb-2 inline-flex rounded-xl bg-emerald-300/15 p-2 text-emerald-200">
              <CheckCircle2 className="h-4 w-4" />
            </div>
            Layman inputs are translated into model-ready data automatically, so operators do not need technical sensor terms.
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-300">
            <div className="mb-2 inline-flex rounded-xl bg-cyan-300/15 p-2 text-cyan-200">
              <WandSparkles className="h-4 w-4" />
            </div>
            Powered by React Hook Form + Zod validation + Framer Motion + Lenis smooth interactions.
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-300">
            <div className="mb-2 inline-flex rounded-xl bg-amber-300/15 p-2 text-amber-200">
              <TriangleAlert className="h-4 w-4" />
            </div>
            Expert Mode remains available for advanced users who want to override raw and engineered model values directly.
          </div>
        </div>
      </CinematicSection>
    </PageTransition>
  );
}
