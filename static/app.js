const rawDefaults = window.APP_DEFAULTS.raw;
const featureDefaults = window.APP_DEFAULTS.features;
const orbitCircumference = 2 * Math.PI * 88;

const els = {
  predictButton: document.getElementById("predictButton"),
  batchButton: document.getElementById("batchButton"),
  heroAnalyze: document.getElementById("heroAnalyze"),
  heroBatch: document.getElementById("heroBatch"),
  timestamp: document.getElementById("timestamp"),
  scoreValue: document.getElementById("scoreValue"),
  confidenceValue: document.getElementById("confidenceValue"),
  failureModeValue: document.getElementById("failureModeValue"),
  actionValue: document.getElementById("actionValue"),
  statusBadge: document.getElementById("statusBadge"),
  componentBars: document.getElementById("componentBars"),
  signalsList: document.getElementById("signalsList"),
  csvInput: document.getElementById("csvInput"),
  batchSummary: document.getElementById("batchSummary"),
  batchPreview: document.getElementById("batchPreview"),
  heroScore: document.getElementById("heroScore"),
  heroLevel: document.getElementById("heroLevel"),
  heroMode: document.getElementById("heroMode"),
  heroConfidence: document.getElementById("heroConfidence"),
  orbitProgress: document.getElementById("orbitProgress"),
  tensionLabel: document.getElementById("tensionLabel"),
  signalCanvas: document.getElementById("signalCanvas"),
};

const presets = {
  calm: {
    raw: { ...rawDefaults },
    features: { ...featureDefaults },
  },
  stress: {
    raw: {
      ...rawDefaults,
      TP2: 8.6,
      TP3: 8.1,
      H1: 8.9,
      DV_pressure: 8.8,
      Reservoirs: 7.9,
      Oil_temperature: 78,
      Motor_current: 5.95,
      COMP: 1,
      MPG: 0,
      LPS: 0,
    },
    features: {
      ...featureDefaults,
      duty_cycle_5min: 0.98,
      pressure_variance_10min: 0.75,
      current_spike_freq: 0.66,
      comp_mpg_disagreement: 1,
      sensor_divergence: 4.2,
      pressure_diff: 0.5,
    },
  },
  leak: {
    raw: {
      ...rawDefaults,
      TP2: 8.4,
      TP3: 7.7,
      H1: 8.7,
      DV_pressure: 8.5,
      Reservoirs: 7.4,
      Oil_temperature: 68,
      Motor_current: 5.1,
      COMP: 1,
      MPG: 1,
      LPS: 0,
    },
    features: {
      ...featureDefaults,
      pressure_diff: 0.7,
      sensor_divergence: 3.6,
      pressure_variance_10min: 1.0,
      duty_cycle_5min: 0.93,
      comp_mpg_disagreement: 0,
    },
  },
};

function setTab(tabName) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === tabName);
  });
}

function collectInputs(group) {
  return Object.fromEntries(
    [...document.querySelectorAll(`[data-group="${group}"]`)].map((input) => [input.dataset.key, Number(input.value)])
  );
}

function setGroupValues(group, values) {
  document.querySelectorAll(`[data-group="${group}"]`).forEach((input) => {
    if (values[input.dataset.key] !== undefined) {
      input.value = values[input.dataset.key];
    }
  });
}

function formatScore(value) {
  return Number(value || 0).toFixed(3);
}

function colorForBand(band) {
  return {
    normal: "#64f1c1",
    warning: "#ffbf63",
    critical: "#ff6b88",
  }[band] || "#64f1c1";
}

function setStatus(level, band) {
  els.statusBadge.textContent = level;
  els.statusBadge.className = `status-badge ${band}`;
  els.heroLevel.textContent = level;
}

function setOrbit(score, band) {
  const offset = orbitCircumference * (1 - Math.max(0, Math.min(1, score)));
  const color = colorForBand(band);
  els.orbitProgress.style.strokeDasharray = String(orbitCircumference);
  els.orbitProgress.style.strokeDashoffset = String(offset);
  els.orbitProgress.style.stroke = color;
  els.heroScore.textContent = formatScore(score);
}

function renderBars(output) {
  const bars = [
    ["Physics", output.physics_score || 0],
    ["Temporal", output.temporal_score || 0],
    ["Statistical", output.statistical_score || 0],
  ];
  els.componentBars.innerHTML = bars.map(([label, value]) => `
    <div class="bar">
      <div class="bar-head"><span>${label}</span><strong>${formatScore(value)}</strong></div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, value * 100)}%"></div></div>
    </div>
  `).join("");
}

function renderSignals(signals) {
  if (!signals || signals.length === 0) {
    els.signalsList.className = "signal-list empty-panel";
    els.signalsList.textContent = "Top physics signals will appear here.";
    return;
  }
  els.signalsList.className = "signal-list";
  els.signalsList.innerHTML = signals.map((signal) => `
    <article class="signal-item">
      <header>
        <strong>${signal.name}</strong>
        <span class="tag">${signal.failure_mode}</span>
      </header>
      <div>${signal.description}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, (signal.score || 0) * 100)}%"></div></div>
    </article>
  `).join("");
}

function drawSignalCanvas(output) {
  const canvas = els.signalCanvas;
  const ctx = canvas.getContext("2d");
  const values = [
    output.physics_score || 0,
    output.temporal_score || 0,
    output.statistical_score || 0,
    output.confidence || 0,
    output.railsense_score || 0,
  ];
  const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
  gradient.addColorStop(0, "#7bc9ff");
  gradient.addColorStop(0.5, "#64f1c1");
  gradient.addColorStop(1, "#ffbf63");

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i += 1) {
    const y = (canvas.height / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }

  const points = values.map((value, index) => ({
    x: 24 + index * ((canvas.width - 48) / (values.length - 1)),
    y: canvas.height - 18 - value * (canvas.height - 36),
  }));

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach((point, index) => {
    const prev = points[index];
    const midX = (prev.x + point.x) / 2;
    ctx.quadraticCurveTo(midX, prev.y, point.x, point.y);
  });
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 4;
  ctx.stroke();

  points.forEach((point) => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#f3f7ff";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(point.x, point.y, 10, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(100,241,193,0.14)";
    ctx.fill();
  });

  els.tensionLabel.textContent = output.alert_level || "Idle";
}

function renderPrediction(output) {
  els.scoreValue.textContent = formatScore(output.railsense_score);
  els.confidenceValue.textContent = `${Math.round((output.confidence || 0) * 100)}%`;
  els.failureModeValue.textContent = output.dominant_failure_mode || "None";
  els.actionValue.textContent = output.recommended_action || "No action suggested.";
  els.heroMode.textContent = output.dominant_failure_mode || "None";
  els.heroConfidence.textContent = `${Math.round((output.confidence || 0) * 100)}%`;
  setStatus(output.alert_level || "NORMAL", output.band || "normal");
  setOrbit(output.railsense_score || 0, output.band || "normal");
  renderBars(output);
  renderSignals(output.top_physics_signals || []);
  drawSignalCanvas(output);
}

async function runPrediction() {
  els.predictButton.disabled = true;
  els.predictButton.textContent = "Analyzing...";
  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        timestamp: els.timestamp.value,
        raw: collectInputs("raw"),
        features: collectInputs("feature"),
      }),
    });
    const data = await response.json();
    renderPrediction(data);
  } catch (error) {
    alert(`Prediction failed: ${error.message}`);
  } finally {
    els.predictButton.disabled = false;
    els.predictButton.textContent = "Analyze Case";
  }
}

function renderBatchSummary(summary) {
  els.batchSummary.className = "batch-summary";
  els.batchSummary.innerHTML = `
    <div class="info-grid">
      <div class="info-card"><span>Rows</span><strong>${summary.rows}</strong></div>
      <div class="info-card"><span>Average score</span><strong>${formatScore(summary.average_score)}</strong></div>
      <div class="info-card"><span>Critical</span><strong>${summary.critical_count}</strong></div>
      <div class="info-card"><span>Warning</span><strong>${summary.warning_count}</strong></div>
    </div>
  `;
}

function renderBatchPreview(rows) {
  if (!rows || rows.length === 0) {
    els.batchPreview.innerHTML = "";
    return;
  }
  els.batchPreview.innerHTML = rows.map((row) => `
    <article class="batch-card">
      <header>
        <strong>Row ${row.row_index}</strong>
        <span class="status-badge ${row.band}">${row.alert_level}</span>
      </header>
      <div>Score: <strong>${formatScore(row.railsense_score)}</strong></div>
      <div>Mode: <strong>${row.dominant_failure_mode || "None"}</strong></div>
      <div>${row.recommended_action || "No action suggested."}</div>
    </article>
  `).join("");
}

async function runBatchPrediction() {
  const file = els.csvInput.files[0];
  if (!file) {
    alert("Choose a CSV file first.");
    return;
  }
  els.batchButton.disabled = true;
  els.batchButton.textContent = "Scoring...";
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/predict-batch", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Batch scoring failed.");
    }
    renderBatchSummary(data.summary);
    renderBatchPreview(data.preview);
  } catch (error) {
    alert(error.message);
  } finally {
    els.batchButton.disabled = false;
    els.batchButton.textContent = "Run Batch Scoring";
  }
}

function applyPreset(name) {
  const preset = presets[name];
  if (!preset) return;
  setGroupValues("raw", preset.raw);
  setGroupValues("feature", preset.features);
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setTab(button.dataset.tab));
});

document.querySelectorAll(".scenario-button").forEach((button) => {
  button.addEventListener("click", () => applyPreset(button.dataset.preset));
});

els.predictButton.addEventListener("click", runPrediction);
els.batchButton.addEventListener("click", runBatchPrediction);
els.heroAnalyze.addEventListener("click", () => {
  setTab("manual");
  runPrediction();
});
els.heroBatch.addEventListener("click", () => setTab("batch"));

setOrbit(0, "normal");
drawSignalCanvas({
  physics_score: 0,
  temporal_score: 0,
  statistical_score: 0,
  confidence: 0,
  railsense_score: 0,
  alert_level: "Idle",
});
