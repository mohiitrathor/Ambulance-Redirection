/**
 * RAAH Command Center API Client
 * Wraps all 17 FastAPI endpoints cleanly.
 */

const BASE_URL = '';

export async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch (_) {}
    throw new Error(errorDetail);
  }

  return response.json();
}

// --- Health ---
export const getHealth = () => request('/health');

// --- State Telemetry ---
export const getDashboard = () => request('/state/dashboard');
export const getSnapshot = () => request('/state/snapshot');
export const getHospitals = () => request('/state/hospitals');
export const getHospital = (id) => request(`/state/hospitals/${id}`);
export const getAmbulances = () => request('/state/ambulances');
export const getAmbulance = (id) => request(`/state/ambulances/${id}`);
export const getIncidents = () => request('/state/incidents');
export const getIncident = (id) => request(`/state/incidents/${id}`);

// --- Dispatch ---
export const dispatchIncident = (incidentId) => 
  request(`/dispatch/${incidentId}`, { method: 'POST' });

// --- Simulation Controls ---
export const getRealtimeStatus = () => request('/simulation/realtime/status');

export const startRealtime = (tickInterval = 1.0, minutesPerTick = 1) =>
  request('/simulation/realtime/start', {
    method: 'POST',
    body: JSON.stringify({
      tick_interval_seconds: tickInterval,
      minutes_per_tick: minutesPerTick,
    }),
  });

export const stopRealtime = () => 
  request('/simulation/realtime/stop', { method: 'POST' });

export const simulationTick = (minutes = 1) =>
  request(`/simulation/tick?minutes=${minutes}`, { method: 'POST' });

export const simulationReset = () => 
  request('/simulation/reset', { method: 'POST' });

// --- Redirection & Decisions ---
export const getDecisions = () => request('/redirect/decisions');
export const getIncidentDecisions = (id) => request(`/redirect/decisions/${id}`);
export const checkRedirection = (id) => request(`/redirect/check/${id}`, { method: 'POST' });

// --- Events ---
export const getPendingEvents = () => request('/events/pending');
export const scheduleEvent = (time, eventType, data = {}) =>
  request('/events', {
    method: 'POST',
    body: JSON.stringify({
      time: parseInt(time, 10),
      event_type: eventType,
      data: data,
    }),
  });
