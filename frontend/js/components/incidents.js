/**
 * Incident Triage & Quick-Dispatch Component
 */

import { store } from '../state.js';
import * as api from '../api.js';
import { tacticalMap } from '../map.js';
import { showToast } from './toasts.js';
import { openEmergencyIntakeModal } from './intake_modal.js';
import { openIncidentDetail } from './detail_drawer.js';

export function setupIncidents() {
  const form = document.getElementById('form-quick-dispatch');
  const inputId = document.getElementById('input-incident-id');
  const container = document.getElementById('incidents-container');
  const countBadge = document.getElementById('active-incident-count');
  const btnOpenIntake = document.getElementById('btn-open-intake');

  // --- Live Emergency Call Intake Button ---
  if (btnOpenIntake) {
    btnOpenIntake.addEventListener('click', () => {
      openEmergencyIntakeModal();
    });
  }

  // --- Quick Dispatch Form Submit ---
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const incidentId = parseInt(inputId.value, 10);
    if (!incidentId || isNaN(incidentId)) return;

    try {
      const result = await api.dispatchIncident(incidentId);
      inputId.value = '';

      // Immediately refresh dashboard & state
      const dash = await api.getDashboard();
      store.updateFromDashboard(dash);

      // If active ambulance returned, refresh ambulances layer
      if (result.ambulance) {
        const ambulances = await api.getAmbulances();
        store.setAmbulances(ambulances);
      }

      showToast(
        'Incident Dispatched',
        `Incident #${result.incident_id}: ${result.ambulance ? result.ambulance.ambulance_id : 'Awaiting unit'} -> ${result.hospital ? result.hospital.hospital_id : 'Unassigned'}`,
        'success'
      );

      // Open detail drawer and focus map
      store.selectIncident(result.incident_id);
      tacticalMap.focusIncident(result.incident_id);
      openIncidentDetail(result.incident_id);
    } catch (err) {
      showToast('Dispatch Error', err.message, 'danger');
    }
  });

  // --- Reactive Render of Incident Cards ---
  store.subscribe((state, changedKeys) => {
    if (!changedKeys.includes('activeIncidents') && !changedKeys.includes('selectedIncidentId')) {
      return;
    }

    const incidents = state.activeIncidents;
    countBadge.textContent = `${incidents.length} Active`;

    if (!incidents || incidents.length === 0) {
      container.innerHTML = `
        <div class="empty-placeholder">
          <i data-lucide="inbox"></i>
          <span>No active incidents. Enter an Incident ID above to triage & dispatch.</span>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    container.innerHTML = incidents.map(inc => {
      const pClass = `p${inc.priority}`;
      const isSelected = state.selectedIncidentId === inc.incident_id;
      const etaText = inc.eta_minutes !== null ? `${inc.eta_minutes.toFixed(1)}m` : '—';

      return `
        <div class="incident-card ${pClass} ${isSelected ? 'selected' : ''}" data-id="${inc.incident_id}">
          <div class="card-header-row">
            <span class="incident-id-badge">#${inc.incident_id}</span>
            <span class="priority-pill ${pClass}">P${inc.priority} ${inc.severity}</span>
          </div>
          <div class="card-meta-row">
            <span class="card-detail-tag">
              <i data-lucide="truck" style="width: 13px; height: 13px;"></i>
              <span>${inc.ambulance_id || 'Awaiting Unit'}</span>
            </span>
            <span class="card-detail-tag">
              <i data-lucide="building-2" style="width: 13px; height: 13px;"></i>
              <span>${inc.hospital_id || 'Unassigned'}</span>
            </span>
            <span class="eta-tag">${etaText}</span>
          </div>
        </div>
      `;
    }).join('');

    // Attach click listeners to cards to focus on map & open detail drawer
    container.querySelectorAll('.incident-card').forEach(card => {
      card.addEventListener('click', () => {
        const id = parseInt(card.getAttribute('data-id'), 10);
        store.selectIncident(id);
        tacticalMap.focusIncident(id);
        openIncidentDetail(id);
      });
    });

    if (window.lucide) window.lucide.createIcons();
  });
}
