/**
 * RAAH Tactical Leaflet Map Controller
 * Implements tiered situational-awareness rendering for Jaipur EMS.
 */

import { store } from './state.js';

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
        <div style="font-family: var(--font-sans); min-width: 180px;">
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 4px; color: ${color};">
            ${hosp.hospital_id} (${hosp.hospital_type})
          </div>
          <div style="font-size: 11px; color: #94a3b8; font-family: var(--font-mono);">
            <div>Available Beds: <strong>${hosp.available_beds}</strong> / ${hosp.capacity}</div>
            <div>Available ICU: <strong>${hosp.available_icu}</strong> / ${hosp.icu_capacity}</div>
            <div style="margin-top: 4px; font-weight: 700; color: ${isSaturated ? '#ef4444' : '#10b981'};">
              ${isSaturated ? '⚠️ SATURATED (NO BEDS)' : '✓ CAPACITY AVAILABLE'}
            </div>
          </div>
        </div>
      `);

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

        this.activeAmbulanceMarkers.set(ambulance.ambulance_id, ambMarker);
        this.enRouteAmbulancesLayer.addLayer(ambMarker);

        // 2. Direct Dashed Polyline Route between Ambulance and Hospital
        const routeLine = L.polyline(
          [
            [ambulance.latitude, ambulance.longitude],
            [hospital.latitude, hospital.longitude],
          ],
          {
            color: unitColor,
            weight: 3,
            dashArray: '6, 8',
            opacity: 0.85,
          }
        );

        this.routeLines.set(incident.incident_id, routeLine);
        this.routePolylinesLayer.addLayer(routeLine);
      }
    }
  }

  focusIncident(incidentId) {
    const route = this.routeLines.get(incidentId);
    if (route) {
      this.map.fitBounds(route.getBounds(), { padding: [40, 40] });
    }
  }
}

export const tacticalMap = new TacticalMap();
