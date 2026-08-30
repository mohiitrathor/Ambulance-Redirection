from dataclasses import dataclass, field
from typing import Optional
import math


# ==============================================================
# INCIDENT
# ==============================================================

@dataclass
class IncidentState:
    incident_id: int
    condition: str
    severity: str
    priority: int

    status: str = "WAITING"

    ambulance_id: Optional[str] = None
    hospital_id: Optional[str] = None


# ==============================================================
# AMBULANCE
# ==============================================================

@dataclass
class AmbulanceState:
    ambulance_id: str
    ambulance_type: str

    latitude: float
    longitude: float

    status: str = "AVAILABLE"

    incident_id: Optional[int] = None
    hospital_id: Optional[str] = None

    eta_minutes: Optional[float] = None
    base_eta_minutes: Optional[float] = None

    traffic_level: str = "NORMAL"
    road_condition: str = "GOOD"

    # ----------------------------------------------------------
    # ETA
    # ----------------------------------------------------------

    TRAFFIC_MULTIPLIERS = {
        "LIGHT": 1.00,
        "NORMAL": 1.00,
        "MODERATE": 1.15,
        "HEAVY": 1.30,
        "SEVERE": 1.50,
    }

    ROAD_MULTIPLIERS = {
        "GOOD": 1.00,
        "AVERAGE": 1.10,
        "POOR": 1.25,
    }

    def apply_route_conditions(self, base_eta):

        traffic = self.TRAFFIC_MULTIPLIERS.get(
            self.traffic_level.upper(),
            1.00,
        )

        road = self.ROAD_MULTIPLIERS.get(
            self.road_condition.upper(),
            1.00,
        )

        return float(base_eta) * traffic * road

    def recalculate_eta(self):

        if self.base_eta_minutes is None:
            self.eta_minutes = None
            return None

        self.eta_minutes = round(
            self.apply_route_conditions(
                self.base_eta_minutes
            ),
            2,
        )

        return self.eta_minutes

    # ----------------------------------------------------------
    # DISTANCE
    # ----------------------------------------------------------

    @staticmethod
    def calculate_distance(
        lat1,
        lon1,
        lat2,
        lon2,
    ):

        radius_km = 6371.0

        lat1 = math.radians(float(lat1))
        lat2 = math.radians(float(lat2))

        delta_lat = math.radians(
            float(lat2) - float(lat1)
        )

        delta_lon = math.radians(
            float(lon2) - float(lon1)
        )

        a = (
            math.sin(delta_lat / 2) ** 2
            +
            math.cos(lat1)
            * math.cos(lat2)
            * math.sin(delta_lon / 2) ** 2
        )

        c = 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )

        return radius_km * c

    # ----------------------------------------------------------
    # ETA TO SPECIFIC HOSPITAL
    # ----------------------------------------------------------

    def estimate_eta_to_hospital(
        self,
        hospital,
    ):

        distance_km = self.calculate_distance(
            self.latitude,
            self.longitude,
            hospital.latitude,
            hospital.longitude,
        )

        # Simulation speed.
        # Replace with routing API later.
        speed_kmh = 40.0

        base_eta = (
            distance_km / speed_kmh
        ) * 60

        return round(
            self.apply_route_conditions(
                base_eta
            ),
            2,
        )


# ==============================================================
# HOSPITAL
# ==============================================================

@dataclass
class HospitalState:
    hospital_id: str
    hospital_type: str

    latitude: float
    longitude: float

    capacity: int
    current_load: int

    icu_capacity: int
    current_icu_load: int

    @property
    def available_beds(self):

        return max(
            0,
            self.capacity - self.current_load,
        )

    @property
    def available_icu(self):

        return max(
            0,
            self.icu_capacity
            - self.current_icu_load,
        )

    @property
    def is_full(self):

        return self.available_beds <= 0

    @property
    def icu_available(self):

        return self.available_icu > 0


# ==============================================================
# GLOBAL DISPATCH STATE
# ==============================================================

@dataclass
class DispatchState:

    incidents: dict = field(
        default_factory=dict
    )

    ambulances: dict = field(
        default_factory=dict
    )

    hospitals: dict = field(
        default_factory=dict
    )

    current_time: int = 0

    events: list = field(
        default_factory=list
    )

    # ----------------------------------------------------------
    # ADD
    # ----------------------------------------------------------

    def add_incident(self, incident):

        self.incidents[
            incident.incident_id
        ] = incident

    def add_ambulance(self, ambulance):

        self.ambulances[
            ambulance.ambulance_id
        ] = ambulance

    def add_hospital(self, hospital):

        self.hospitals[
            hospital.hospital_id
        ] = hospital

    # ----------------------------------------------------------
    # EVENTS
    # ----------------------------------------------------------

    def add_event(self, message):

        self.events.append({
            "time": self.current_time,
            "message": str(message),
        })

    # ----------------------------------------------------------
    # QUERIES
    # ----------------------------------------------------------

    def get_available_ambulances(self):

        return [
            ambulance
            for ambulance in self.ambulances.values()
            if ambulance.status == "AVAILABLE"
        ]

    def get_active_incidents(self):

        return [
            incident
            for incident in self.incidents.values()
            if incident.status in {
                "DISPATCHED",
                "EN_ROUTE",
                "REDIRECTED",
            }
        ]

    # ----------------------------------------------------------
    # TIME
    # ----------------------------------------------------------

    def advance_time(self, minutes=1):

        self.current_time += int(minutes)