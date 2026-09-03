"""
RAAH DispatchState Serialization & Deserialization Engine
=========================================================

Provides deterministic, schema-versioned serialization and validation for
authoritative DispatchState instances without altering protected state classes.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

from state import (
    DispatchState,
    IncidentState,
    AmbulanceState,
    HospitalState,
)
from api.persistence.interface import (
    IncompatibleSchemaError,
    CorruptStateError,
)

SCHEMA_VERSION: int = 1
SUPPORTED_SCHEMA_VERSIONS = {1}


# ======================================================================
# SERIALIZATION
# ======================================================================

def serialize_incident(inc: IncidentState) -> Dict[str, Any]:
    """Serialize a single IncidentState instance."""
    return {
        "incident_id": int(inc.incident_id),
        "condition": str(inc.condition),
        "severity": str(inc.severity),
        "priority": int(inc.priority),
        "status": str(inc.status),
        "ambulance_id": str(inc.ambulance_id) if inc.ambulance_id is not None else None,
        "hospital_id": str(inc.hospital_id) if inc.hospital_id is not None else None,
    }


def serialize_ambulance(amb: AmbulanceState) -> Dict[str, Any]:
    """Serialize a single AmbulanceState instance."""
    return {
        "ambulance_id": str(amb.ambulance_id),
        "ambulance_type": str(amb.ambulance_type),
        "latitude": float(amb.latitude),
        "longitude": float(amb.longitude),
        "status": str(amb.status),
        "incident_id": int(amb.incident_id) if amb.incident_id is not None else None,
        "hospital_id": str(amb.hospital_id) if amb.hospital_id is not None else None,
        "eta_minutes": float(amb.eta_minutes) if amb.eta_minutes is not None else None,
        "base_eta_minutes": float(amb.base_eta_minutes) if amb.base_eta_minutes is not None else None,
        "traffic_level": str(amb.traffic_level),
        "road_condition": str(amb.road_condition),
        "route_distance_km": float(amb.route_distance_km) if amb.route_distance_km is not None else None,
    }


def serialize_hospital(hosp: HospitalState) -> Dict[str, Any]:
    """Serialize a single HospitalState instance."""
    return {
        "hospital_id": str(hosp.hospital_id),
        "hospital_type": str(hosp.hospital_type),
        "latitude": float(hosp.latitude),
        "longitude": float(hosp.longitude),
        "capacity": int(hosp.capacity),
        "current_load": int(hosp.current_load),
        "icu_capacity": int(hosp.icu_capacity),
        "current_icu_load": int(hosp.current_icu_load),
    }


def serialize_dispatch_state(state: DispatchState) -> Dict[str, Any]:
    """
    Produce a canonical, versioned serialization dictionary from DispatchState.
    """
    serialized_incidents = {}
    for inc_id, inc in (state.incidents or {}).items():
        serialized_incidents[str(inc_id)] = serialize_incident(inc)

    serialized_ambulances = {}
    for amb_id, amb in (state.ambulances or {}).items():
        serialized_ambulances[str(amb_id)] = serialize_ambulance(amb)

    serialized_hospitals = {}
    for hosp_id, hosp in (state.hospitals or {}).items():
        serialized_hospitals[str(hosp_id)] = serialize_hospital(hosp)

    events_list = []
    for ev in (state.events or []):
        if isinstance(ev, dict):
            events_list.append({
                "time": int(ev.get("time", 0)),
                "message": str(ev.get("message", "")),
            })

    return {
        "schema_version": SCHEMA_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "simulation_time": int(state.current_time),
        "state": {
            "current_time": int(state.current_time),
            "incidents": serialized_incidents,
            "ambulances": serialized_ambulances,
            "hospitals": serialized_hospitals,
            "events": events_list,
        },
    }


# ======================================================================
# CHECKSUM
# ======================================================================

def compute_state_checksum(payload: Dict[str, Any]) -> str:
    """
    Compute cryptographic SHA-256 hash across canonical JSON representation.
    """
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# ======================================================================
# VALIDATION & DESERIALIZATION
# ======================================================================

def validate_state_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    """
    Verify top-level structure, schema version, and required fields.
    Returns (is_valid, error_message).
    """
    if not isinstance(payload, dict):
        return False, "Payload must be a dictionary."

    version = payload.get("schema_version")
    if version is None:
        return False, "Missing 'schema_version' field."
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        return False, f"Incompatible schema version '{version}'. Supported: {SUPPORTED_SCHEMA_VERSIONS}."

    if "simulation_time" not in payload:
        return False, "Missing 'simulation_time' in payload."

    state_dict = payload.get("state")
    if not isinstance(state_dict, dict):
        return False, "Missing or invalid 'state' block in payload."

    for key in ("incidents", "ambulances", "hospitals"):
        if key not in state_dict or not isinstance(state_dict[key], dict):
            return False, f"Missing or invalid '{key}' collection in state."

    return True, None


def deserialize_dispatch_state(payload: Dict[str, Any]) -> DispatchState:
    """
    Reconstruct an authoritative DispatchState instance from a serialized payload.
    Raises IncompatibleSchemaError or CorruptStateError on invalid data.
    """
    is_valid, error_msg = validate_state_payload(payload)
    if not is_valid:
        version = payload.get("schema_version") if isinstance(payload, dict) else None
        if version is not None and version not in SUPPORTED_SCHEMA_VERSIONS:
            raise IncompatibleSchemaError(error_msg)
        raise CorruptStateError(error_msg or "Invalid state payload.")

    state_dict = payload["state"]
    current_time = int(state_dict.get("current_time", payload.get("simulation_time", 0)))

    # Deserialized containers
    incidents: Dict[int, IncidentState] = {}
    ambulances: Dict[str, AmbulanceState] = {}
    hospitals: Dict[str, HospitalState] = {}
    events: list = []

    # 1. Incidents
    for inc_key, inc_data in state_dict.get("incidents", {}).items():
        if not isinstance(inc_data, dict):
            raise CorruptStateError(f"Malformed incident record under key '{inc_key}'.")
        try:
            inc_obj = IncidentState(
                incident_id=int(inc_data["incident_id"]),
                condition=str(inc_data["condition"]),
                severity=str(inc_data["severity"]),
                priority=int(inc_data["priority"]),
                status=str(inc_data.get("status", "WAITING")),
                ambulance_id=inc_data.get("ambulance_id"),
                hospital_id=inc_data.get("hospital_id"),
            )
            incidents[inc_obj.incident_id] = inc_obj
        except (KeyError, TypeError, ValueError) as err:
            raise CorruptStateError(f"Error parsing incident '{inc_key}': {err}")

    # 2. Ambulances
    for amb_key, amb_data in state_dict.get("ambulances", {}).items():
        if not isinstance(amb_data, dict):
            raise CorruptStateError(f"Malformed ambulance record under key '{amb_key}'.")
        try:
            amb_obj = AmbulanceState(
                ambulance_id=str(amb_data["ambulance_id"]),
                ambulance_type=str(amb_data["ambulance_type"]),
                latitude=float(amb_data["latitude"]),
                longitude=float(amb_data["longitude"]),
                status=str(amb_data.get("status", "AVAILABLE")),
                incident_id=int(amb_data["incident_id"]) if amb_data.get("incident_id") is not None else None,
                hospital_id=amb_data.get("hospital_id"),
                eta_minutes=float(amb_data["eta_minutes"]) if amb_data.get("eta_minutes") is not None else None,
                base_eta_minutes=float(amb_data["base_eta_minutes"]) if amb_data.get("base_eta_minutes") is not None else None,
                traffic_level=str(amb_data.get("traffic_level", "NORMAL")),
                road_condition=str(amb_data.get("road_condition", "GOOD")),
                route_distance_km=float(amb_data["route_distance_km"]) if amb_data.get("route_distance_km") is not None else None,
            )
            ambulances[amb_obj.ambulance_id] = amb_obj
        except (KeyError, TypeError, ValueError) as err:
            raise CorruptStateError(f"Error parsing ambulance '{amb_key}': {err}")

    # 3. Hospitals
    for hosp_key, hosp_data in state_dict.get("hospitals", {}).items():
        if not isinstance(hosp_data, dict):
            raise CorruptStateError(f"Malformed hospital record under key '{hosp_key}'.")
        try:
            hosp_obj = HospitalState(
                hospital_id=str(hosp_data["hospital_id"]),
                hospital_type=str(hosp_data["hospital_type"]),
                latitude=float(hosp_data["latitude"]),
                longitude=float(hosp_data["longitude"]),
                capacity=int(hosp_data["capacity"]),
                current_load=int(hosp_data["current_load"]),
                icu_capacity=int(hosp_data["icu_capacity"]),
                current_icu_load=int(hosp_data["current_icu_load"]),
            )
            hospitals[hosp_obj.hospital_id] = hosp_obj
        except (KeyError, TypeError, ValueError) as err:
            raise CorruptStateError(f"Error parsing hospital '{hosp_key}': {err}")

    # 4. Events
    for ev in state_dict.get("events", []):
        if isinstance(ev, dict) and "time" in ev and "message" in ev:
            events.append({
                "time": int(ev["time"]),
                "message": str(ev["message"]),
            })

    # Assemble DispatchState
    state = DispatchState(
        incidents=incidents,
        ambulances=ambulances,
        hospitals=hospitals,
        current_time=current_time,
        events=events,
    )
    return state
