/**
 * Redirection Decisions Audit Stream Component
 */

import { store } from '../state.js';

export function setupDecisions() {
  const tbody = document.getElementById('decisions-tbody');
  const countBadge = document.getElementById('redirection-count');

  store.subscribe((state, changedKeys) => {
    if (!changedKeys.includes('decisions')) {
      return;
    }

    const decisions = state.decisions;
    countBadge.textContent = `${decisions.length} Redirection${decisions.length === 1 ? '' : 's'}`;

    if (!decisions || decisions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="empty-placeholder" style="padding: 10px;">
            No redirection decisions recorded yet.
          </td>
        </tr>
      `;
      return;
    }

    // Display most recent decisions first
    const reversed = decisions.slice().reverse();

    tbody.innerHTML = reversed.map(d => {
      const isRedirect = d.decision === 'REDIRECTED';
      const etaSaved = d.eta_saved !== null && d.eta_saved !== undefined 
        ? `${d.eta_saved.toFixed(1)}m` 
        : '—';

      return `
        <tr>
          <td style="color: var(--text-cyan);">T+${d.time}m</td>
          <td><strong style="color: #fff;">#${d.incident_id}</strong></td>
          <td style="color: #f87171;">${d.original_hospital || '—'}</td>
          <td style="color: #34d399; font-weight: 700;">${d.new_hospital || '—'}</td>
          <td style="color: var(--status-enroute); font-weight: 700;">${etaSaved}</td>
          <td style="color: var(--text-secondary); max-width: 250px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${d.reason}">
            ${d.reason}
          </td>
        </tr>
      `;
    }).join('');
  });
}
