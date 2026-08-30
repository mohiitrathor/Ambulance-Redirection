/**
 * Incident Detail Drawer & Operator Control Plane
 * Slide-out panel providing clinical vitals, ML confidence, fleet telemetry,
 * hospital capacity, decision history, and operator manual redirection controls.
 */

import * as api from '../api.js';
import { store } from '../state.js';
import { tacticalMap } from '../map.js';
import { showToast } from './toasts.js';
import { confirmModal } from './confirmation_modal.js';

let drawerElement = null;
let currentIncidentId = null;

export function setupDetailDrawer() {
  drawerElement = document.getElementById('drawer-incident-detail');
  if (!drawerElement) {
    drawerElement = document.createElement('aside');
    drawerElement.id = 'drawer-incident-detail';
    drawerElement.className = 'tactical-drawer';
    document.body.appendChild(drawerElement);
  }

  // Subscribe to store updates to keep drawer data fresh in real-time
  store.subscribe((state, changedKeys) => {
    if (!currentIncidentId || !drawerElement.classList.contains('open')) return;

    if (changedKeys.includes('activeIncidents') || changedKeys.includes('ambulances') || changedKeys.includes('hospitals')) {
      const incident = state.activeIncidents.find(i => i.incident_id === currentIncidentId);
      if (incident) {
        renderDrawerContent(incident);
      }
    }
  });
}

/**
 * Open detail drawer for a specific incident ID
 */
export async function openIncidentDetail(incidentId) {
  currentIncidentId = incidentId;
  setupDetailDrawer();

  // Find incident from store
  const incident = store.state.activeIncidents.find(i => i.incident_id === incidentId);
  if (!incident) {
    // Attempt to fetch from API
    try {
      const inc = await api.getIncident(incidentId);
      renderDrawerContent(inc);
      drawerElement.classList.add('open');
    } catch (err) {
      showToast('Incident Not Found', `ID #${incidentId} is not in active state.`, 'warning');
    }
    return;
  }

  renderDrawerContent(incident);
  drawerElement.classList.add('open');
}

export function closeIncidentDetail() {
  if (drawerElement) {
    drawerElement.classList.remove('open');
  }
  currentIncidentId = null;
}

async function renderDrawerContent(incident) {
  const ambulance = store.state.ambulances.get(String(incident.ambulance_id));
  const hospital = store.state.hospitals.get(String(incident.hospital_id));

  // Fetch incident-specific decisions history
  let decisions = [];
  try {
    decisions = await api.getIncidentDecisions(incident.incident_id);
  } catch (_) {}

  const pClass = `p${incident.priority}`;
  const etaDisplay = incident.eta_minutes !== null ? `${incident.eta_minutes.toFixed(1)} min` : '—';
  const isEnRoute = ambulance && ambulance.status === 'EN_ROUTE';

  drawerElement.innerHTML = `
    <div class="drawer-header">
      <div class="drawer-title-group">
        <span class="incident-id-badge">#${incident.incident_id}</span>
        <span class="priority-pill ${pClass}">P${incident.priority} ${incident.severity}</span>
        <span class="status-pill status-${(incident.status || 'dispatched').toLowerCase()}">${incident.status || 'DISPATCHED'}</span>
      </div>
      <button class="drawer-close-btn" title="Close Drawer">&times;</button>
    </div>

    <div class="drawer-body">
      <!-- Section 1: Clinical Triage & ML Confidence -->
      <div class="drawer-section">
        <div class="section-title">
          <i data-lucide="activity"></i>
          <span>Clinical Triage & ML Evaluation</span>
        </div>
        <div class="detail-grid">
          <div class="detail-cell">
            <span class="label">Condition</span>
            <span class="value">${incident.condition || 'General Emergency'}</span>
          </div>
          <div class="detail-cell">
            <span class="label">Priority Level</span>
            <span class="value">${incident.priority ? `P${incident.priority}` : 'P3'}</span>
          </div>
          <div class="detail-cell">
            <span class="label">Severity</span>
            <span class="value ${incident.severity === 'Critical' ? 'text-danger' : 'text-warning'}">${incident.severity}</span>
          </div>
          <div class="detail-cell">
            <span class="label">Lifecycle Status</span>
            <span class="value">${incident.status}</span>
          </div>
        </div>
      </div>

      <!-- Section 2: Fleet Unit Assignment -->
      <div class="drawer-section">
        <div class="section-title">
          <i data-lucide="truck"></i>
          <span>Assigned Emergency Vehicle</span>
        </div>
        ${ambulance ? `
          <div class="detail-grid">
            <div class="detail-cell">
              <span class="label">Unit ID</span>
              <span class="value font-mono highlight">${ambulance.ambulance_id}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Capability Type</span>
              <span class="value">${ambulance.ambulance_type}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Operational Status</span>
              <span class="value status-text-${ambulance.status.toLowerCase()}">${ambulance.status}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Remaining Route ETA</span>
              <span class="value font-mono highlight text-accent">${etaDisplay}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Route Distance</span>
              <span class="value font-mono">${ambulance.route_distance_km ? `${ambulance.route_distance_km.toFixed(1)} km` : '—'}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Traffic / Road</span>
              <span class="value font-mono">${ambulance.traffic_level || 'NORMAL'} / ${ambulance.road_condition || 'GOOD'}</span>
            </div>
          </div>
        ` : `
          <div class="empty-placeholder">No ambulance assigned to this incident.</div>
        `}
      </div>

      <!-- Section 3: Destination Hospital -->
      <div class="drawer-section">
        <div class="section-title">
          <i data-lucide="building-2"></i>
          <span>Destination Medical Center</span>
        </div>
        ${hospital ? `
          <div class="detail-grid">
            <div class="detail-cell">
              <span class="label">Facility ID</span>
              <span class="value font-mono highlight">${hospital.hospital_id}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Classification</span>
              <span class="value">${hospital.hospital_type}</span>
            </div>
            <div class="detail-cell">
              <span class="label">Available General Beds</span>
              <span class="value font-mono ${hospital.is_full ? 'text-danger' : 'text-success'}">
                ${hospital.available_beds} / ${hospital.capacity}
              </span>
            </div>
            <div class="detail-cell">
              <span class="label">Available ICU Beds</span>
              <span class="value font-mono ${hospital.available_icu <= 0 ? 'text-danger' : 'text-success'}">
                ${hospital.available_icu} / ${hospital.icu_capacity}
              </span>
            </div>
          </div>
          ${hospital.is_full ? `
            <div class="alert-banner danger" style="margin-top: 8px;">
              <i data-lucide="alert-octagon"></i>
              <span>CRITICAL: Hospital reached 100% saturation! Redirection recommended.</span>
            </div>
          ` : ''}
        ` : `
          <div class="empty-placeholder">No destination hospital assigned.</div>
        `}
      </div>

      <!-- Section 4: Redirection & Decision Audit Trail -->
      <div class="drawer-section">
        <div class="section-title">
          <i data-lucide="git-merge"></i>
          <span>Redirection Audit Trail (${decisions.length})</span>
        </div>
        ${decisions.length > 0 ? `
          <div class="decision-mini-list">
            ${decisions.map(d => `
              <div class="decision-mini-item">
                <div class="decision-mini-header">
                  <span class="decision-pill ${d.reason.includes('[OPERATOR]') ? 'pill-operator' : 'pill-ai'}">
                    ${d.reason.includes('[OPERATOR]') ? 'OPERATOR' : 'AI AUTO'}
                  </span>
                  <span class="decision-time">T+${d.time}m</span>
                </div>
                <div class="decision-route">
                  <span>${d.original_hospital}</span>
                  <i data-lucide="arrow-right" style="width: 12px; height: 12px;"></i>
                  <strong>${d.new_hospital}</strong>
                </div>
                <div class="decision-reason">${d.reason}</div>
                ${d.eta_saved !== null ? `
                  <div class="decision-delta">ETA Saved: <strong>${d.eta_saved}m</strong> (${d.eta_before}m -> ${d.eta_after}m)</div>
                ` : ''}
              </div>
            `).join('')}
          </div>
        ` : `
          <div class="empty-placeholder" style="padding: 6px 0;">No redirection decisions for this incident. Initial dispatch route active.</div>
        `}
      </div>

      <!-- Section 5: Operator Control Actions -->
      <div class="drawer-section operator-action-section">
        <div class="section-title">
          <i data-lucide="shield-alert"></i>
          <span>Operator Override Controls</span>
        </div>
        <div class="operator-btn-row">
          <button class="btn-tactical btn-evaluate" id="btn-eval-reroute" ${!isEnRoute ? 'disabled' : ''}>
            <i data-lucide="search"></i> Evaluate Reroute
          </button>
          <button class="btn-tactical btn-execute" id="btn-exec-reroute" ${!isEnRoute ? 'disabled' : ''}>
            <i data-lucide="corner-up-right"></i> Execute Reroute
          </button>
        </div>
        <div id="eval-result-card" class="eval-result-card" style="display: none;"></div>
      </div>
    </div>
  `;

  if (window.lucide) window.lucide.createIcons();

  // Bind close button
  drawerElement.querySelector('.drawer-close-btn').addEventListener('click', closeIncidentDetail);

  // Bind Evaluate Reroute
  const btnEval = drawerElement.querySelector('#btn-eval-reroute');
  const evalCard = drawerElement.querySelector('#eval-result-card');

  btnEval.addEventListener('click', async () => {
    btnEval.disabled = true;
    evalCard.style.display = 'none';

    try {
      const evalRes = await api.checkRedirection(incident.incident_id);
      evalCard.style.display = 'block';

      if (evalRes.redirect && evalRes.alternative_hospital) {
        const alt = evalRes.alternative_hospital;
        evalCard.className = 'eval-result-card recommended';
        evalCard.innerHTML = `
          <div class="eval-header text-warning">
            <i data-lucide="alert-circle" style="width: 15px; height: 15px;"></i>
            <strong>Redirection Recommended</strong>
          </div>
          <div class="eval-detail">
            <div>Recommended Facility: <strong>${alt.hospital_id}</strong> (${alt.hospital_type})</div>
            <div>Available Beds: <strong>${alt.available_beds}</strong> | ICU: <strong>${alt.available_icu}</strong></div>
            <div>Trigger Reason: <em>${evalRes.reason}</em></div>
            ${evalRes.eta_saved !== null ? `<div>Estimated Time Saved: <strong class="text-success">${evalRes.eta_saved} min</strong></div>` : ''}
          </div>
        `;
      } else {
        evalCard.className = 'eval-result-card not-recommended';
        evalCard.innerHTML = `
          <div class="eval-header text-success">
            <i data-lucide="check-circle" style="width: 15px; height: 15px;"></i>
            <strong>Current Destination Optimal</strong>
          </div>
          <div class="eval-detail">
            <div>Reason: ${evalRes.reason || 'Current route remains fastest compatible facility.'}</div>
          </div>
        `;
      }
      if (window.lucide) window.lucide.createIcons();
    } catch (err) {
      evalCard.style.display = 'block';
      evalCard.className = 'eval-result-card not-recommended';
      evalCard.innerHTML = `<div class="text-danger">Evaluation failed: ${err.message}</div>`;
    } finally {
      btnEval.disabled = false;
    }
  });

  // Bind Execute Reroute
  const btnExec = drawerElement.querySelector('#btn-exec-reroute');
  btnExec.addEventListener('click', async () => {
    // Open in-app tactical confirmation modal (zero window.confirm)
    const confirmed = await confirmModal({
      title: `Reroute Incident #${incident.incident_id}`,
      message: `Are you sure you want to reroute Ambulance ${ambulance ? ambulance.ambulance_id : ''} to an alternative hospital? This will update the operational destination and log an operator override decision.`,
      confirmText: 'Execute Reroute',
      cancelText: 'Cancel',
      danger: true,
    });

    if (!confirmed) return;

    btnExec.disabled = true;

    try {
      const decision = await api.applyRedirection(incident.incident_id, null, 'Dispatcher initiated reroute');

      // Refresh live telemetry
      const dash = await api.getDashboard();
      store.updateFromDashboard(dash);

      const ambulances = await api.getAmbulances();
      store.setAmbulances(ambulances);

      showToast(
        'Reroute Executed',
        `Incident #${incident.incident_id} redirected to ${decision.new_hospital}. ETA: ${decision.eta_after}m`,
        'warning',
        5000
      );

      // Re-render drawer with updated state
      openIncidentDetail(incident.incident_id);
    } catch (err) {
      showToast('Reroute Error', err.message, 'danger');
      btnExec.disabled = false;
    }
  });
}
