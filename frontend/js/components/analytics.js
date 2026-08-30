/**
 * Historical Analytics View Controller
 * Manages run selection, KPI aggregation, redirection analysis, and incident audit querying.
 */

import * as api from '../api.js';
import { showToast } from './toasts.js';

let selectedRunId = null;

export function setupAnalytics() {
  const btnTacticalTab = document.getElementById('nav-btn-tactical');
  const btnAnalyticsTab = document.getElementById('nav-btn-analytics');
  const commandWorkspace = document.getElementById('command-workspace');
  const intelDrawer = document.getElementById('intel-drawer');
  const analyticsWorkspace = document.getElementById('analytics-workspace');

  if (!btnTacticalTab || !btnAnalyticsTab || !analyticsWorkspace) return;

  // --- View Switcher ---
  btnTacticalTab.addEventListener('click', () => {
    btnTacticalTab.classList.add('active');
    btnAnalyticsTab.classList.remove('active');
    commandWorkspace.style.display = 'grid';
    if (intelDrawer) intelDrawer.style.display = 'flex';
    analyticsWorkspace.style.display = 'none';
  });

  btnAnalyticsTab.addEventListener('click', async () => {
    btnAnalyticsTab.classList.add('active');
    btnTacticalTab.classList.remove('active');
    commandWorkspace.style.display = 'none';
    if (intelDrawer) intelDrawer.style.display = 'none';
    analyticsWorkspace.style.display = 'flex';

    await loadRuns();
  });
}

async function loadRuns() {
  const runSelect = document.getElementById('select-analytics-run');
  const btnRefresh = document.getElementById('btn-refresh-analytics');
  if (!runSelect) return;

  try {
    const runs = await api.getRuns();
    if (!runs || runs.length === 0) {
      runSelect.innerHTML = '<option value="">No simulation runs recorded</option>';
      return;
    }

    const currentSelected = selectedRunId || runs[0].run_id;
    selectedRunId = currentSelected;

    runSelect.innerHTML = runs.map(r => `
      <option value="${r.run_id}" ${r.run_id === selectedRunId ? 'selected' : ''}>
        Run #${r.run_id} (${r.status}) - ${r.total_incidents} Incidents | ${r.total_redirections} Redirections
      </option>
    `).join('');

    runSelect.onchange = () => {
      selectedRunId = parseInt(runSelect.value, 10);
      loadAnalyticsData(selectedRunId);
    };

    if (btnRefresh) {
      btnRefresh.onclick = () => loadAnalyticsData(selectedRunId);
    }

    await loadAnalyticsData(selectedRunId);
  } catch (err) {
    showToast('Analytics Error', `Failed to load runs: ${err.message}`, 'danger');
  }
}

async function loadAnalyticsData(runId) {
  if (!runId) return;

  try {
    const [summary, incidents, decisions] = await Promise.all([
      api.getAnalyticsSummary(runId),
      api.getHistoricalIncidents(runId, 50, 0),
      api.getHistoricalDecisions(runId),
    ]);

    renderKPIs(summary);
    renderRedirectionIntelligence(summary, decisions);
    renderIncidentTable(incidents);
  } catch (err) {
    showToast('Analytics Error', err.message, 'danger');
  }
}

function renderKPIs(summary) {
  // Scorecard values
  document.getElementById('kpi-total-dispatches').textContent = summary.total_incidents;
  document.getElementById('kpi-avg-eta').textContent = `${summary.average_initial_eta.toFixed(1)}m`;
  document.getElementById('kpi-redir-rate').textContent = `${summary.redirections.redirection_rate_pct.toFixed(1)}%`;
  document.getElementById('kpi-eta-saved').textContent = `${summary.redirections.total_eta_saved.toFixed(1)}m`;
  document.getElementById('kpi-saturation-events').textContent = summary.hospital_saturation_events;
  document.getElementById('kpi-ml-confidence').textContent = `${(summary.average_ml_confidence * 100).toFixed(1)}%`;

  // Priority breakdown bar
  const pMap = summary.incidents_by_priority || {};
  const total = summary.total_incidents || 1;
  const p1Pct = ((pMap['P1'] || 0) / total) * 100;
  const p2Pct = ((pMap['P2'] || 0) / total) * 100;
  const p3Pct = ((pMap['P3'] || 0) / total) * 100;
  const p4Pct = ((pMap['P4'] || 0) / total) * 100;
  const p5Pct = ((pMap['P5'] || 0) / total) * 100;

  const bar = document.getElementById('kpi-priority-bar');
  if (bar) {
    bar.innerHTML = `
      <div style="width:${p1Pct}%; background:var(--p1-critical);" title="P1 Critical: ${pMap['P1'] || 0}"></div>
      <div style="width:${p2Pct}%; background:var(--p2-emergency);" title="P2 Emergency: ${pMap['P2'] || 0}"></div>
      <div style="width:${p3Pct}%; background:var(--p3-urgent);" title="P3 Urgent: ${pMap['P3'] || 0}"></div>
      <div style="width:${p4Pct}%; background:var(--p4-semi);" title="P4 Semi-Urgent: ${pMap['P4'] || 0}"></div>
      <div style="width:${p5Pct}%; background:var(--p5-non);" title="P5 Non-Urgent: ${pMap['P5'] || 0}"></div>
    `;
  }
}

function renderRedirectionIntelligence(summary, decisions) {
  const r = summary.redirections;
  const totalR = r.total || 0;
  const aiPct = totalR > 0 ? ((r.ai_autonomous / totalR) * 100).toFixed(0) : '0';
  const opPct = totalR > 0 ? ((r.operator_manual / totalR) * 100).toFixed(0) : '0';

  const statsContainer = document.getElementById('analytics-redir-stats');
  if (statsContainer) {
    statsContainer.innerHTML = `
      <div class="analytics-stat-row">
        <span>AI Autonomous Redirections:</span>
        <strong class="text-cyan">${r.ai_autonomous} (${aiPct}%)</strong>
      </div>
      <div class="analytics-stat-row">
        <span>Operator Manual Overrides:</span>
        <strong style="color:#f59e0b;">${r.operator_manual} (${opPct}%)</strong>
      </div>
      <div class="analytics-stat-row">
        <span>Mean Time Saved / Redirection:</span>
        <strong class="text-success">${r.avg_eta_saved.toFixed(2)} min</strong>
      </div>
      <div class="analytics-stat-row">
        <span>Total Fleet Time Saved:</span>
        <strong class="text-success">${r.total_eta_saved.toFixed(1)} min</strong>
      </div>
    `;
  }

  // Decisions list
  const listContainer = document.getElementById('analytics-decisions-list');
  if (listContainer) {
    if (!decisions || decisions.length === 0) {
      listContainer.innerHTML = '<div class="empty-placeholder" style="padding:15px;">No redirection decisions recorded in this run session.</div>';
      return;
    }

    listContainer.innerHTML = decisions.map(d => `
      <div class="decision-mini-item">
        <div class="decision-mini-header">
          <span class="decision-pill ${d.trigger_type === 'OPERATOR_MANUAL' ? 'pill-operator' : 'pill-ai'}">
            ${d.trigger_type === 'OPERATOR_MANUAL' ? 'OPERATOR' : 'AI AUTO'}
          </span>
          <span class="decision-time">T+${d.sim_time}m</span>
        </div>
        <div class="decision-route">
          <span>${d.original_hospital_id || 'Initial'}</span>
          <i data-lucide="arrow-right" style="width: 12px; height: 12px;"></i>
          <strong>${d.new_hospital_id}</strong>
        </div>
        <div class="decision-reason">${d.reason}</div>
        ${d.eta_saved !== null ? `
          <div class="decision-delta">ETA Saved: <strong>${d.eta_saved.toFixed(1)}m</strong> (${d.eta_before}m -> ${d.eta_after}m)</div>
        ` : ''}
      </div>
    `).join('');
    if (window.lucide) window.lucide.createIcons();
  }
}

function renderIncidentTable(incidents) {
  const tbody = document.getElementById('analytics-incidents-tbody');
  if (!tbody) return;

  if (!incidents || incidents.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-placeholder" style="padding:20px;">No incidents dispatched in this simulation run.</td></tr>';
    return;
  }

  tbody.innerHTML = incidents.map(inc => `
    <tr>
      <td>#${inc.incident_id}</td>
      <td><span class="priority-pill p${inc.priority}">P${inc.priority} ${inc.predicted_severity}</span></td>
      <td>${inc.condition}</td>
      <td class="font-mono text-cyan">${inc.ambulance_id || '—'}</td>
      <td class="font-mono">${inc.final_hospital_id || inc.initial_hospital_id || '—'}</td>
      <td class="font-mono">${inc.initial_eta_minutes !== null ? `${inc.initial_eta_minutes.toFixed(1)}m` : '—'}</td>
      <td><span class="status-pill status-${(inc.dispatch_status || 'en_route').toLowerCase()}">${inc.dispatch_status || 'EN_ROUTE'}</span></td>
    </tr>
  `).join('');
}
