/**
 * Event Console & Injection Component
 */

import { store } from '../state.js';
import * as api from '../api.js';
import { openEventScheduleModal } from './event_modal.js';

export function setupEvents() {
  const container = document.getElementById('event-feed-container');
  const btnSchedule = document.getElementById('btn-schedule-event');

  // --- Dynamic Event Injection ---
  btnSchedule.addEventListener('click', () => {
    openEventScheduleModal();
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
