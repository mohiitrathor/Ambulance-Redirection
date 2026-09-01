/**
 * RAAH Tactical Leaflet Map Controller
 * Implements tiered situational-awareness rendering for Jaipur EMS.
 */

import { store } from './state.js';
import * as api from './api.js';
import { openIncidentDetail } from './components/detail_drawer.js';
import { showToast } from './components/toasts.js';

class TacticalMap {
  constructor() {
    this.map = null;
    this.hospitalsLayer = null;
    this.enRouteAmbulancesLayer = null;
    this.routePolylinesLayer = null;
    this.canvasIdleLayer = null;

    this.hospitalMarkers = new Map(); // id -> L.marker
    this.activeAmbulanceMarkers = new Map(); // id -> L.marker
    this.routeLines = new Map(); // incident_id -> L.polyline
  }

  initialize(elementId = 'leaflet-map') {
    if (this.map) return;

    // Jaipur City Center Coordinates
    const JAIPUR_CENTER = [26.9124, 75.7873];

    this.map = L.map(elementId, {
      center: JAIPUR_CENTER,
      zoom: 12,
      zoomControl: true,
      attributionControl: false,
    });

    // Dark Matter Tactical Base Tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 18,
      subdomains: 'abcd',
    }).addTo(this.map);

    // Layer groups for clean management
    this.hospitalsLayer = L.layerGroup().addTo(this.map);
    this.routePolylinesLayer = L.layerGroup().addTo(this.map);
    this.enRouteAmbulancesLayer = L.layerGroup().addTo(this.map);
    this.mciLayer = L.layerGroup().addTo(this.map);

    // Subscribe to state changes
    store.subscribe((state, changedKeys) => {
      if (changedKeys.includes('hospitals')) {
        this.renderHospitals(state.hospitals);
      }
      if (changedKeys.includes('activeIncidents') || changedKeys.includes('ambulances')) {
        this.renderActiveRoutesAndUnits(state);
      }
    });
  }

  // --- TIER 1: HOSPITALS (Always Visible) ---
  renderHospitals(hospitalsMap) {
    this.hospitalsLayer.clearLayers();
    this.hospitalMarkers.clear();

    for (const [id, hosp] of hospitalsMap.entries()) {
      const isSaturated = hosp.available_beds <= 0 || hosp.is_full;
      const isCriticalIcuFull = hosp.available_icu <= 0;

      const markerClass = `hospital-marker-pin ${isSaturated ? 'saturated' : ''}`;
      const color = isSaturated ? '#ef4444' : '#0ea5e9';

      const icon = L.divIcon({
        className: 'custom-hosp-icon',
        html: `
          <div class="${markerClass}" style="background: ${color}; width: 22px; height: 22px; border-radius: 4px; display:flex; align-items:center; justify-content:center; border: 1px solid #fff;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          </div>
        `,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
      });

      const marker = L.marker([hosp.latitude, hosp.longitude], { icon });

      marker.bindPopup(`
        <div style="font-family: var(--font-sans); min-width: 185px;">
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 4px; color: ${color};">
            ${hosp.hospital_id} (${hosp.hospital_type})
          </div>
          <div style="font-size: 11px; color: #94a3b8; font-family: var(--font-mono);">
            <div>Available Beds: <strong>${hosp.available_beds}</strong> / ${hosp.capacity}</div>
            <div>Available ICU: <strong>${hosp.available_icu}</strong> / ${hosp.icu_capacity}</div>
            <div style="margin-top: 4px; font-weight: 700; color: ${isSaturated ? '#ef4444' : '#10b981'};">
              ${isSaturated ? '⚠️ SATURATED (NO BEDS)' : '✓ CAPACITY AVAILABLE'}
            </div>
            <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid #334155;">
              <button class="btn-saturate-hosp" data-hosp="${hosp.hospital_id}" style="background:#ef4444; color:#fff; border:none; border-radius:3px; padding:4px 8px; font-size:10px; font-weight:700; cursor:pointer; width:100%; font-family:var(--font-sans);">
                ⚡ Simulate Saturation (Mark Full)
              </button>
            </div>
          </div>
        </div>
      `);

      marker.on('popupopen', (e) => {
        const popupNode = e.popup.getElement();
        if (!popupNode) return;
        const btn = popupNode.querySelector('.btn-saturate-hosp');
        if (btn) {
          btn.addEventListener('click', async () => {
            try {
              await api.scheduleEvent(store.state.simTime, 'HOSPITAL_FULL', { hospital_id: hosp.hospital_id });
              showToast('Hospital Saturated', `Simulated 100% capacity for ${hosp.hospital_id}`, 'warning');
              marker.closePopup();
            } catch (err) {
              showToast('Event Error', err.message, 'danger');
            }
          });
        }
      });

      this.hospitalMarkers.set(id, marker);
      this.hospitalsLayer.addLayer(marker);
    }
  }

  // --- TIER 2 & 3: EN_ROUTE AMBULANCES & DYNAMIC ROUTES ---
  renderActiveRoutesAndUnits(state) {
    this.enRouteAmbulancesLayer.clearLayers();
    this.routePolylinesLayer.clearLayers();
    this.activeAmbulanceMarkers.clear();
    this.routeLines.clear();

    const activeIncidents = state.activeIncidents;

    for (const incident of activeIncidents) {
      if (!incident.ambulance_id || !incident.hospital_id) continue;

      const ambulance = state.ambulances.get(String(incident.ambulance_id));
      const hospital = state.hospitals.get(String(incident.hospital_id));

      if (!ambulance || !hospital) continue;

      const isEnRoute = ambulance.status === 'EN_ROUTE';
      const isCritical = incident.severity === 'Critical';
      const unitColor = isCritical ? '#ef4444' : '#f59e0b';

      if (isEnRoute) {
        // 1. Prominent Vehicle Marker
        const icon = L.divIcon({
          className: 'custom-amb-icon',
          html: `
            <div class="ambulance-marker-pin" style="background: ${unitColor};">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1 .4-1 1v9"/>
                <circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>
              </svg>
            </div>
          `,
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        });

        const ambMarker = L.marker([ambulance.latitude, ambulance.longitude], { icon });

        const etaText = ambulance.eta_minutes !== null ? `${ambulance.eta_minutes.toFixed(1)} min` : 'Calculating';

        ambMarker.bindPopup(`
          <div style="font-family: var(--font-sans); min-width: 170px;">
            <div style="font-weight: 800; font-size: 13px; color: ${unitColor};">
              ${ambulance.ambulance_id} (${ambulance.ambulance_type})
            </div>
            <div style="font-size: 11px; margin-top: 4px; font-family: var(--font-mono); color: #cbd5e1;">
              <div>Status: <strong>${ambulance.status}</strong></div>
              <div>Destination: <strong>${hospital.hospital_id}</strong></div>
              <div>ETA: <strong style="color: #f59e0b;">${etaText}</strong></div>
              <div>Traffic: ${ambulance.traffic_level || 'NORMAL'}</div>
            </div>
          </div>
        `);

        ambMarker.bindTooltip(`${ambulance.ambulance_id} | ${etaText}`, {
          permanent: true,
          direction: 'top',
          offset: [0, -14],
          className: 'amb-tooltip',
        });

        ambMarker.on('click', () => {
          store.selectIncident(incident.incident_id);
          this.focusIncident(incident.incident_id);
          openIncidentDetail(incident.incident_id);
        });

        this.activeAmbulanceMarkers.set(ambulance.ambulance_id, ambMarker);
        this.enRouteAmbulancesLayer.addLayer(ambMarker);

        // 2. Multi-point tactical polyline route between Ambulance and Hospital
        const routePoints = (ambulance.route_waypoints && ambulance.route_waypoints.length > 1)
          ? ambulance.route_waypoints
          : [
              [ambulance.latitude, ambulance.longitude],
              [hospital.latitude, hospital.longitude],
            ];

        const routeLine = L.polyline(
          routePoints,
          {
            color: unitColor,
            weight: 3,
            dashArray: '6, 8',
            opacity: 0.85,
          }
        );

        routeLine.on('click', () => {
          store.selectIncident(incident.incident_id);
          this.focusIncident(incident.incident_id);
          openIncidentDetail(incident.incident_id);
        });

        this.routeLines.set(incident.incident_id, routeLine);
        this.routePolylinesLayer.addLayer(routeLine);
      }
    }

    // --- TIER 4: REPOSITIONING AMBULANCES (M9) ---
    if (state.ambulances) {
      const ambs = state.ambulances instanceof Map ? state.ambulances.values() : Object.values(state.ambulances);
      for (const ambulance of ambs) {
        if (ambulance.status === 'REPOSITIONING' || ambulance.is_repositioning) {
          const repoColor = '#06b6d4'; // Tactical Cyan

          // Repositioning Vehicle Pin
          const icon = L.divIcon({
            className: 'custom-amb-icon',
            html: `
              <div class="ambulance-marker-pin" style="background: ${repoColor}; box-shadow: 0 0 10px rgba(6, 182, 212, 0.6);">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M4 14l6-6 6 6"/>
                  <path d="M10 8v12"/>
                </svg>
              </div>
            `,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
          });

          const ambMarker = L.marker([ambulance.latitude, ambulance.longitude], { icon });
          const etaText = ambulance.eta_minutes !== null ? `${ambulance.eta_minutes.toFixed(1)} min` : 'Transit';

          ambMarker.bindPopup(`
            <div style="font-family: var(--font-sans); min-width: 180px;">
              <div style="font-weight: 800; font-size: 13px; color: ${repoColor};">
                ${ambulance.ambulance_id} [REPOSITIONING]
              </div>
              <div style="font-size: 11px; margin-top: 4px; font-family: var(--font-mono); color: #cbd5e1;">
                <div>Origin: <strong>${ambulance.reposition_origin_zone || 'Current'}</strong></div>
                <div>Target: <strong>${ambulance.reposition_target_zone || 'Staging'}</strong></div>
                <div>ETA: <strong style="color: ${repoColor};">${etaText}</strong></div>
              </div>
            </div>
          `);

          ambMarker.bindTooltip(`${ambulance.ambulance_id} | ${etaText}`, {
            permanent: true,
            direction: 'top',
            offset: [0, -14],
            className: 'amb-tooltip',
          });

          this.activeAmbulanceMarkers.set(ambulance.ambulance_id, ambMarker);
          this.enRouteAmbulancesLayer.addLayer(ambMarker);

          // Repositioning Route Polyline
          if (ambulance.route_waypoints && ambulance.route_waypoints.length > 1) {
            const routeLine = L.polyline(ambulance.route_waypoints, {
              color: repoColor,
              weight: 3,
              dashArray: '4, 6',
              opacity: 0.85,
            });
            this.routeLines.set(`repo_${ambulance.ambulance_id}`, routeLine);
            this.routePolylinesLayer.addLayer(routeLine);
          }
        }
      }
    }
  }

  focusIncident(incidentId) {
    const route = this.routeLines.get(incidentId);
    if (route) {
      this.map.fitBounds(route.getBounds(), { padding: [40, 40] });
    }
  }

  // --- TIER 4: MULTI-CASUALTY INCIDENTS (M9 Phase 4) ---
  renderMCIs(mcisList) {
    if (!this.mciLayer) return;
    this.mciLayer.clearLayers();

    if (!mcisList || mcisList.length === 0) return;

    for (const mci of mcisList) {
      if (mci.status === 'RESOLVED') continue;

      const isEvacuating = mci.status === 'EVACUATING';
      const statusColor = isEvacuating ? '#f59e0b' : '#ef4444';

      const icon = L.divIcon({
        className: 'custom-mci-icon',
        html: `
          <div style="position: relative; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center;">
            <div style="position: absolute; inset: 0; border-radius: 50%; background: rgba(239, 68, 68, 0.4); animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
            <div style="width: 26px; height: 26px; border-radius: 50%; background: #dc2626; border: 2px solid #fecaca; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 12px rgba(239, 68, 68, 0.8);">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
            </div>
          </div>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      });

      const marker = L.marker([mci.latitude, mci.longitude], { icon });

      const pCounts = mci.casualty_counts_by_priority || {};
      const pSummary = Object.entries(pCounts).map(([k, v]) => `${k}:${v}`).join(' | ') || 'Pending';

      marker.bindPopup(`
        <div style="font-family: var(--font-sans); min-width: 200px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-weight: 800; font-size: 13px; color: #f87171;">${mci.name}</span>
            <span style="font-size: 10px; background: rgba(239, 68, 68, 0.2); color: #fca5a5; padding: 1px 4px; border-radius: 3px; border: 1px solid #ef4444;">${mci.status}</span>
          </div>
          <div style="font-size: 11px; margin-top: 6px; font-family: var(--font-mono); color: #cbd5e1; line-height: 1.5;">
            <div>MCI ID: <strong style="color: #fff;">${mci.mci_id}</strong></div>
            <div>Total Casualties: <strong style="color: #f87171;">${mci.total_casualties}</strong></div>
            <div>Evacuated: <strong>${mci.evacuated_count} / ${mci.total_casualties}</strong></div>
            <div>Priority Breakdown: <strong style="color: #38bdf8;">${pSummary}</strong></div>
            <div>Assigned Fleet: <strong>${(mci.assigned_ambulance_ids || []).length} units</strong></div>
          </div>
        </div>
      `);

      this.mciLayer.addLayer(marker);
    }
  }

  focusMCI(mciId) {
    // Zoom in on MCI coordinates
  }
}

export const tacticalMap = new TacticalMap();
