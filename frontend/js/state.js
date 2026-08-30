/**
 * RAAH Reactive Store & State Manager
 */

class Store {
  constructor() {
    this.state = {
      simTime: 0,
      simStatus: 'STOPPED',
      isRealtimeRunning: false,
      speedMultiplier: 60.0,
      tickInterval: 1.0,
      activeIncidents: [],
      fleet: {
        total: 1000,
        available: 0,
        en_route: 0,
        busy: 0,
        maintenance: 0,
        arrived: 0,
      },
      hospitals: new Map(), // hospital_id -> Hospital object
      ambulances: new Map(), // ambulance_id -> Ambulance object
      events: [],
      decisions: [],
      selectedIncidentId: null,
      lastRenderedTime: -1,
    };

    this.subscribers = new Set();
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  notify(changedKeys = []) {
    this.subscribers.forEach(cb => {
      try {
        cb(this.state, changedKeys);
      } catch (err) {
        console.error('Error in state subscriber:', err);
      }
    });
  }

  setHospitals(hospitalsList) {
    this.state.hospitals.clear();
    for (const h of hospitalsList) {
      this.state.hospitals.set(String(h.hospital_id), h);
    }
    this.notify(['hospitals']);
  }

  setAmbulances(ambulancesList) {
    this.state.ambulances.clear();
    for (const a of ambulancesList) {
      this.state.ambulances.set(String(a.ambulance_id), a);
    }
    this.notify(['ambulances']);
  }

  updateFromDashboard(dashboardData) {
    const prevTime = this.state.simTime;
    this.state.simTime = dashboardData.time;
    this.state.activeIncidents = dashboardData.active_incidents || [];
    this.state.fleet = dashboardData.fleet || this.state.fleet;
    this.state.events = dashboardData.events || [];

    const changed = ['dashboard', 'simTime', 'activeIncidents', 'fleet', 'events'];
    this.notify(changed);
  }

  updateRealtimeStatus(statusData) {
    this.state.simStatus = statusData.status;
    this.state.isRealtimeRunning = statusData.is_running;
    this.state.speedMultiplier = statusData.speed_multiplier;
    this.state.tickInterval = statusData.tick_interval_seconds;
    this.notify(['realtimeStatus']);
  }

  setDecisions(decisionsList) {
    this.state.decisions = decisionsList || [];
    this.notify(['decisions']);
  }

  selectIncident(incidentId) {
    this.state.selectedIncidentId = incidentId;
    this.notify(['selectedIncidentId']);
  }
}

export const store = new Store();
