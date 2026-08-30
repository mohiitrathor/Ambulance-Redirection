/**
 * Simulation Event Injector Modal
 * Replaces window.prompt() with a dedicated in-app modal form.
 */

import * as api from '../api.js';
import { store } from '../state.js';
import { showToast } from './toasts.js';

let eventModalElement = null;

export function openEventScheduleModal(defaultHospitalId = null) {
  if (eventModalElement) {
    document.body.removeChild(eventModalElement);
    eventModalElement = null;
  }

  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop visible';

  const dialog = document.createElement('div');
  dialog.className = 'modal-dialog tactical-event-dialog';

  // Build hospital options list from live state
  const hospitals = Array.from(store.state.hospitals.values());
  const hospOptions = hospitals.slice(0, 50).map(h => `
    <option value="${h.hospital_id}" ${h.hospital_id === defaultHospitalId ? 'selected' : ''}>
      ${h.hospital_id} (${h.hospital_type}) - Beds: ${h.available_beds}/${h.capacity}
    </option>
  `).join('');

  dialog.innerHTML = `
    <div class="modal-header">
      <div class="modal-title">
        <i data-lucide="zap" style="color: #f59e0b;"></i>
        <span>Inject Simulation Event</span>
      </div>
      <button class="modal-close-btn">&times;</button>
    </div>
    <form id="form-event-schedule" class="modal-body">
      <div class="form-group">
        <label>Event Type</label>
        <select id="event-type-select" class="tactical-select">
          <option value="HOSPITAL_FULL">HOSPITAL_FULL (Saturate All Beds)</option>
          <option value="HOSPITAL_LOAD_CHANGE">HOSPITAL_LOAD_CHANGE</option>
        </select>
      </div>

      <div class="form-group">
        <label>Target Facility (Hospital ID)</label>
        <input 
          type="text" 
          id="event-hospital-id" 
          class="tactical-input" 
          placeholder="e.g. HOSP_182" 
          value="${defaultHospitalId || (hospitals[0] ? hospitals[0].hospital_id : 'HOSP_182')}" 
          required
        />
        <small class="form-hint">Enter an existing hospital ID from the fleet.</small>
      </div>

      <div class="form-group">
        <label>Trigger Timing (Simulation Minutes)</label>
        <div class="input-with-addon">
          <span class="addon">T +</span>
          <input 
            type="number" 
            id="event-time-offset" 
            class="tactical-input" 
            min="0" 
            max="120" 
            value="0" 
            required
          />
          <span class="addon">min</span>
        </div>
        <small class="form-hint">0 triggers immediately at current sim time (${store.state.simTime}m).</small>
      </div>

      <div class="modal-footer">
        <button type="button" class="btn-cancel">Cancel</button>
        <button type="submit" class="btn-primary">Schedule Event</button>
      </div>
    </form>
  `;

  backdrop.appendChild(dialog);
  document.body.appendChild(backdrop);
  eventModalElement = backdrop;
  if (window.lucide) window.lucide.createIcons();

  function close() {
    backdrop.classList.remove('visible');
    setTimeout(() => {
      if (backdrop.parentElement) backdrop.parentElement.removeChild(backdrop);
      eventModalElement = null;
    }, 200);
  }

  dialog.querySelector('.modal-close-btn').addEventListener('click', close);
  dialog.querySelector('.btn-cancel').addEventListener('click', close);
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });

  const form = dialog.querySelector('#form-event-schedule');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const eventType = dialog.querySelector('#event-type-select').value;
    const hospId = dialog.querySelector('#event-hospital-id').value.trim().toUpperCase();
    const offset = parseInt(dialog.querySelector('#event-time-offset').value, 10) || 0;
    const triggerTime = store.state.simTime + offset;

    try {
      await api.scheduleEvent(triggerTime, eventType, { hospital_id: hospId });
      showToast(
        'Event Injected',
        `Scheduled ${eventType} for ${hospId} at T+${triggerTime}m`,
        'warning'
      );
      close();
    } catch (err) {
      showToast('Event Error', err.message, 'danger');
    }
  });
}
