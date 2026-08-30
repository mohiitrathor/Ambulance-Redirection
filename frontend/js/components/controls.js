/**
 * Simulation Controls Component
 * Controls Play, Pause, Step, Reset, and Speed telemetry.
 */

import { store } from '../state.js';
import * as api from '../api.js';
import { showToast } from './toasts.js';
import { confirmModal } from './confirmation_modal.js';

export function setupControls() {
  const btnPlay = document.getElementById('btn-play');
  const btnPause = document.getElementById('btn-pause');
  const btnStep = document.getElementById('btn-step');
  const btnReset = document.getElementById('btn-reset');
  const speedSelector = document.getElementById('speed-selector');
  const simClock = document.getElementById('sim-clock');
  const statusPill = document.getElementById('sim-status-pill');
  const statusText = document.getElementById('sim-status-text');

  // --- Actions ---

  btnPlay.addEventListener('click', async () => {
    try {
      btnPlay.disabled = true;
      const speed = parseFloat(speedSelector.value) || 1.0;
      await api.startRealtime(speed, 1);
      const status = await api.getRealtimeStatus();
      store.updateRealtimeStatus(status);
      showToast('Simulation Started', `Running at 1 tick per ${speed}s (1 min/tick)`, 'success', 3000);
    } catch (err) {
      showToast('Simulation Error', err.message, 'danger');
    } finally {
      btnPlay.disabled = false;
    }
  });

  btnPause.addEventListener('click', async () => {
    try {
      btnPause.disabled = true;
      await api.stopRealtime();
      const status = await api.getRealtimeStatus();
      store.updateRealtimeStatus(status);
      showToast('Simulation Paused', `Clock halted at T+${store.state.simTime}m`, 'info', 3000);
    } catch (err) {
      showToast('Pause Error', err.message, 'danger');
    } finally {
      btnPause.disabled = false;
    }
  });

  btnStep.addEventListener('click', async () => {
    try {
      btnStep.disabled = true;
      const data = await api.simulationTick(1);
      store.updateFromDashboard(data);
    } catch (err) {
      showToast('Step Error', err.message, 'danger');
    } finally {
      btnStep.disabled = false;
    }
  });

  btnReset.addEventListener('click', async () => {
    const confirmed = await confirmModal({
      title: 'Reset Simulation',
      message: 'Are you sure you want to reset the simulation to time = 0? All active dispatches and telemetry will be cleared.',
      confirmText: 'Reset Simulation',
      cancelText: 'Cancel',
      danger: true,
    });
    if (!confirmed) return;

    try {
      btnReset.disabled = true;
      await api.simulationReset();
      const status = await api.getRealtimeStatus();
      store.updateRealtimeStatus(status);
      const dash = await api.getDashboard();
      store.updateFromDashboard(dash);
      const decisions = await api.getDecisions();
      store.setDecisions(decisions);
      showToast('Simulation Reset', 'System state reset to T=0 min.', 'info', 3000);
    } catch (err) {
      showToast('Reset Error', err.message, 'danger');
    } finally {
      btnReset.disabled = false;
    }
  });

  speedSelector.addEventListener('change', async () => {
    if (store.state.isRealtimeRunning) {
      const speed = parseFloat(speedSelector.value) || 1.0;
      await api.stopRealtime();
      await api.startRealtime(speed, 1);
      const status = await api.getRealtimeStatus();
      store.updateRealtimeStatus(status);
    }
  });

  // --- Reactive Render ---
  store.subscribe((state, changedKeys) => {
    // Clock
    simClock.textContent = `T+${state.simTime} min`;

    // Controls state
    const isRunning = state.isRealtimeRunning;
    btnPlay.disabled = isRunning;
    btnPause.disabled = !isRunning;
    btnStep.disabled = isRunning; // Manual tick rejected while running

    // Status Pill
    statusPill.className = `status-pill ${state.simStatus.toLowerCase()}`;
    statusText.textContent = state.simStatus;
  });
}
