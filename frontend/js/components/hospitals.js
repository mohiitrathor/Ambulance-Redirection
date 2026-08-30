/**
 * Hospital Capacity & Saturation Monitor Component
 */

import { store } from '../state.js';

export function setupHospitals() {
  const container = document.getElementById('hospitals-container');

  store.subscribe((state, changedKeys) => {
    if (!changedKeys.includes('hospitals') && !changedKeys.includes('dashboard')) {
      return;
    }

    const hospitals = Array.from(state.hospitals.values());
    if (hospitals.length === 0) return;

    // Show top 25 hospitals sorted by highest occupancy percentage or saturation first
    const sorted = hospitals.slice().sort((a, b) => {
      const aSat = a.available_beds <= 0 ? 1 : 0;
      const bSat = b.available_beds <= 0 ? 1 : 0;
      if (aSat !== bSat) return bSat - aSat; // saturated first

      const aOcc = a.capacity > 0 ? a.current_load / a.capacity : 0;
      const bOcc = b.capacity > 0 ? b.current_load / b.capacity : 0;
      return bOcc - aOcc;
    }).slice(0, 20);

    container.innerHTML = sorted.map(h => {
      const isSaturated = h.available_beds <= 0 || h.is_full;
      const occupancy = h.capacity > 0 ? Math.min(100, Math.round((h.current_load / h.capacity) * 100)) : 0;

      let fillClass = 'safe';
      if (occupancy >= 80) fillClass = 'warn';
      if (isSaturated || occupancy >= 95) fillClass = 'danger';

      return `
        <div class="hospital-card ${isSaturated ? 'saturated' : ''}">
          <div class="hosp-title-row">
            <span style="font-family: var(--font-mono); font-size: 12px; color: ${isSaturated ? '#ef4444' : '#38bdf8'};">
              ${h.hospital_id}
            </span>
            <span style="font-size: 10px; color: ${isSaturated ? '#ef4444' : 'var(--text-muted)'}; font-weight: 700;">
              ${isSaturated ? 'FULL' : `${occupancy}% LOAD`}
            </span>
          </div>
          <div class="capacity-bar-track">
            <div class="capacity-bar-fill ${fillClass}" style="width: ${occupancy}%;"></div>
          </div>
          <div class="hosp-metrics-row">
            <span>Beds: <strong>${h.available_beds}</strong> / ${h.capacity}</span>
            <span>ICU: <strong>${h.available_icu}</strong> / ${h.icu_capacity}</span>
          </div>
        </div>
      `;
    }).join('');
  });
}
