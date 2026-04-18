export async function getConfig() {
  const response = await fetch('/svc/config');
  if (!response.ok) {
    throw new Error('Failed to load API configuration');
  }
  return response.json();
}

export async function predictSingle(payload) {
  const response = await fetch('/svc/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Prediction failed');
  }
  return data;
}

export async function predictBatch(file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/svc/predict-batch', {
    method: 'POST',
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Batch prediction failed');
  }
  return data;
}

export async function explainPrediction(payload) {
  const response = await fetch('/svc/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'AI insight failed');
  }
  return data;
}

export async function explainBatch(payload) {
  const response = await fetch('/svc/explain-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Batch AI insight failed');
  }
  return data;
}
