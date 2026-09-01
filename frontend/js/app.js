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

  // 5. Start State-Driven Conditional Polling Loop (1000ms interval)
  startPollingLoop();
}

function startPollingLoop() {
  setInterval(async () => {
    if (isPolling) return;
    isPolling = true;
    pollCounter++;

    try {
      // High-Frequency Tier: Dashboard Telemetry (1 Hz, ~3.6ms CPU)
      const [rtStatus, dashboard] = await Promise.all([
        api.getRealtimeStatus(),
        api.getDashboard(),
      ]);

      store.updateRealtimeStatus(rtStatus);
      store.updateFromDashboard(dashboard);

      // Conditional Tier: Only poll /state/ambulances if active EN_ROUTE units exist
      if (dashboard.fleet && dashboard.fleet.en_route > 0) {
        const ambulances = await api.getAmbulances();
        store.setAmbulances(ambulances);
      }

      // Medium-Frequency Tier: Poll decisions every 3 seconds
      if (pollCounter % 3 === 0) {
        const decisions = await api.getDecisions();
        store.setDecisions(decisions);
      }
    } catch (err) {
      console.warn('Telemetry poll warning:', err.message);
    } finally {
      isPolling = false;
    }
  }, 1000);
}

// Start on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}
