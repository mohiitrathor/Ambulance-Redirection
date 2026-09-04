/**
 * RAAH Command Center Application Bootstrapper
 * Orchestrates conditional polling, state updates, and component lifecycles.
 */

import { store } from './state.js';
import * as api from './api.js';
import { tacticalMap } from './map.js';

import { setupControls } from './components/controls.js';
import { setupIncidents } from './components/incidents.js';
import { setupFleet } from './components/fleet.js';
import { setupHospitals } from './components/hospitals.js';
import { setupEvents } from './components/events.js';
import { setupDecisions } from './components/decisions.js';
import { setupDetailDrawer } from './components/detail_drawer.js';
import { setupAnalytics } from './components/analytics.js';
import { coordinationComponent } from './components/coordination.js';
import { DrillsController } from './components/drills.js';
import { ReplayController } from './components/replay.js';
import { ScenarioAnalysisController } from './components/scenario_analysis.js';
import { PIRController } from './components/pir.js';
import { RegressionController } from './components/regression.js';
import { OptimizationController } from './components/optimization.js';
import { showToast } from './components/toasts.js';

let pollCounter = 0;
let isPolling = false;

async function bootstrap() {
  console.log('🚀 Initializing RAAH Tactical Command Center...');

  // 1. Initialize Map
  tacticalMap.initialize('leaflet-map');

  // 2. Setup Components
  setupControls();
  setupIncidents();
  setupFleet();
  setupHospitals();
  setupEvents();
  setupDecisions();
  setupDetailDrawer();
  setupAnalytics();
  coordinationComponent.init();
  new DrillsController();

  const replayCtrl = new ReplayController();
  replayCtrl.init();
  const analysisCtrl = new ScenarioAnalysisController(replayCtrl);
  analysisCtrl.init();

  const pirCtrl = new PIRController();
  pirCtrl.init();
  const regCtrl = new RegressionController();
  regCtrl.init();

  const optCtrl = new OptimizationController();
  optCtrl.init();
  document.getElementById('nav-btn-optimization')?.addEventListener('click', () => {
    optCtrl.loadOptimizationData();
  });

  // 3. Initial Lucide Icons Render
  if (window.lucide) {
    window.lucide.createIcons();
  }

  // 4. Initial Real API Data Fetch (Validating contract on day one)
  try {
    const [health, dashboard, hospitals, rtStatus, decisions] = await Promise.all([
      api.getHealth(),
      api.getDashboard(),
      api.getHospitals(),
      api.getRealtimeStatus(),
      api.getDecisions(),
    ]);

    console.log('✓ Initial backend sync completed. Sim time:', health.time);

    store.setHospitals(hospitals);
    store.updateRealtimeStatus(rtStatus);
    store.updateFromDashboard(dashboard);
    store.setDecisions(decisions);

    // If initial active incidents exist, fetch ambulances immediately
    if (dashboard.fleet && dashboard.fleet.en_route > 0) {
      const ambulances = await api.getAmbulances();
      store.setAmbulances(ambulances);
    }
  } catch (err) {
    console.error('Initial backend connection failed:', err);
  }

  // 5. Establish Real-Time SSE Stream (Replaces 1-second polling loop)
  initRealtimeStream();
}

let streamHandle = null;
let lastSequence = null;
let isRecovering = false;

async function triggerAuthoritativeRecovery(reason = '') {
  if (isRecovering) return;
  isRecovering = true;
  console.log(`[Realtime] Triggering authoritative REST recovery (${reason})...`);
  try {
    const dashboard = await api.getDashboard();
    store.updateFromDashboard(dashboard);
    if (dashboard.fleet && dashboard.fleet.en_route > 0) {
      const ambulances = await api.getAmbulances();
      store.setAmbulances(ambulances);
    }
    if (streamHandle) {
      lastSequence = streamHandle.getCurrentSequence();
    }
  } catch (err) {
    console.warn('[Realtime] Snapshot recovery failed:', err.message);
  } finally {
    isRecovering = false;
  }
}

function initRealtimeStream() {
  if (streamHandle) {
    console.warn('[Realtime] Stream already active. Skipping duplicate connection.');
    return;
  }

  streamHandle = api.connectEventStream({
    onOpen: () => {
      console.log('✓ Real-time SSE command center stream active.');
    },
    onSnapshot: (event) => {
      if (event.payload && event.payload.dashboard) {
        store.updateFromDashboard(event.payload.dashboard);
      }
      lastSequence = event.sequence;
    },
    onGap: () => {
      triggerAuthoritativeRecovery('gap_detected_in_stream');
    },
    onEvent: (event) => {
      // Check sequence monotonicity & gap
      if (lastSequence !== null && event.sequence > lastSequence + 1 && event.event_type !== 'STATE_SNAPSHOT') {
        triggerAuthoritativeRecovery(`sequence_gap_${lastSequence}_to_${event.sequence}`);
      }
      lastSequence = event.sequence;

      switch (event.event_type) {
        case 'TICK':
          if (event.payload) {
            store.updateRealtimeStatus({
              status: event.payload.status,
              is_running: event.payload.status === 'RUNNING',
              current_time: event.payload.current_time,
              speed_multiplier: event.payload.speed_multiplier,
            });
            store.updateFromDashboard(event.payload);
            if (event.payload.moving_ambulances && event.payload.moving_ambulances.length > 0) {
              store.setAmbulances(event.payload.moving_ambulances);
            }
          }
          break;

        case 'INCIDENT_DISPATCHED':
          if (event.payload) {
            store.updateFromDashboard({ active_incidents: [event.payload] });
            showToast('Incident Dispatched', `Ambulance ${event.payload.ambulance_id || 'unit'} assigned to incident #${event.payload.incident_id}`, 'info');
          }
          break;

        case 'AMBULANCE_UPDATE':
          if (event.payload) {
            store.setAmbulances([event.payload]);
          }
          break;

        case 'REDIRECTION_EXECUTED':
          if (event.payload) {
            showToast('Hospital Redirection', `Diverted to hospital ${event.payload.new_hospital_id} (saved ${event.payload.eta_saved || 0}m)`, 'warning');
          }
          break;

        case 'MCI_ALERT':
          if (event.payload) {
            const mciName = event.payload.mci ? event.payload.mci.name : 'Emergency';
            showToast('MCI Coordination Alert', `${event.payload.action}: ${mciName}`, 'danger');
          }
          break;

        case 'HOSPITAL_UPDATE':
          break;

        case 'HEARTBEAT':
          break;
      }
    },
    onError: (err) => {
      console.warn('[Realtime] Stream disconnected:', err.message);
    },
  });
}

// Start on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}
