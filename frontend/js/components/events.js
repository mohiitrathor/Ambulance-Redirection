/**
 * Event Console & Injection Component
 */

import { store } from '../state.js';
import * as api from '../api.js';

export function setupEvents() {
  const container = document.getElementById('event-feed-container');
  const btnSchedule = document.getElementById('btn-schedule-event');

  // --- Dynamic Event Injection ---
  btnSchedule.addEventListener('click', async () => {
    const hospId = prompt('Enter Hospital ID to mark FULL (e.g. HOSP_182):', 'HOSP_182');
    if (!hospId) return;

    const timeOffset = prompt('In how many simulation minutes should this trigger? (0 for immediately):', '1');
    if (timeOffset === null) return;

    const triggerTime = store.state.simTime + (parseInt(timeOffset, 10) || 0);

    try {
      await api.scheduleEvent(triggerTime, 'HOSPITAL_FULL', { hospital_id: hospId.trim() });
      alert(`Scheduled HOSPITAL_FULL for ${hospId.trim()} at T+${triggerTime} min.`);
    } catch (err) {
      alert(`Failed to schedule event: ${err.message}`);
    }
  });

  // --- Render Event Feed ---
  store.subscribe((state, changedKeys) => {
    if (!changedKeys.includes('events') && !changedKeys.includes('dashboard')) {
      return;
    }

    const events = state.events;
    if (!events || events.length === 0) {
      container.innerHTML = `<div class="empty-placeholder" style="padding: 10px;">Awaiting simulation events...</div>`;
      return;
    }

    // Display events (most recent first)
    const reversed = events.slice().reverse();

    container.innerHTML = reversed.map(ev => `
      <div class="event-entry">
        <span class="event-time-pill">[${ev.time}m]</span>
        <span class="event-msg">${ev.message}</span>
      </div>
    `).join('');
  });
}
