/**
 * RAAH Stream Connection Status Component
 * Displays real-time SSE stream connectivity, sequence tracking, and gap recovery state.
 */

import { store } from '../state.js';

export function setupConnectionStatus() {
  const pill = document.getElementById('stream-status-pill');
  const text = document.getElementById('stream-status-text');
  const seqBadge = document.getElementById('stream-seq-badge');

  if (!pill || !text) return;

  function render(conn) {
    if (!conn) return;

    // Reset classes
    pill.classList.remove('stream-connected', 'stream-reconnecting', 'stream-syncing', 'stream-disconnected');

    const state = conn.state || 'disconnected';
    const seq = conn.sequence !== null && conn.sequence !== undefined ? conn.sequence : 0;
    const lastType = conn.lastEventType || 'NONE';
    const lastTime = conn.lastEventTime ? new Date(conn.lastEventTime).toLocaleTimeString() : 'N/A';

    switch (state) {
      case 'connected':
        pill.classList.add('stream-connected');
        text.textContent = 'LIVE STREAM';
        pill.title = `Connected to SSE stream. Sequence: #${seq}. Last event: ${lastType} at ${lastTime}`;
        break;
      case 'reconnecting':
        pill.classList.add('stream-reconnecting');
        text.textContent = `RECONNECTING (${conn.reconnectAttempts || 1})`;
        pill.title = `Attempting to re-establish SSE connection...`;
        break;
      case 'syncing':
        pill.classList.add('stream-syncing');
        text.textContent = 'SYNCING';
        pill.title = `Authoritative REST recovery in progress to reconcile sequence gap...`;
        break;
      case 'disconnected':
      default:
        pill.classList.add('stream-disconnected');
        text.textContent = 'DISCONNECTED';
        pill.title = `SSE stream disconnected. Initializing or offline.`;
        break;
    }

    if (seqBadge) {
      seqBadge.textContent = `#${seq}`;
    }
  }

  // Subscribe to streamConnection changes
  store.subscribe((state, changedKeys) => {
    if (changedKeys.includes('streamConnection')) {
      render(state.streamConnection);
    }
  });

  // Initial render
  render(store.state.streamConnection);
}
