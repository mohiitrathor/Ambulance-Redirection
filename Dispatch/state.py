from dataclasses import dataclass, field
from typing import Optional, ClassVar
from math import radians, sin, cos, sqrt, atan2


# ==============================================================
# INCIDENT STATE
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
# AMBULANCE STATE
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

    # Current ETA to current destination.
    eta_minutes: Optional[float] = None

    # ETA before traffic/road adjustments.
    base_eta_minutes: Optional[float] = None

    traffic_level: str = "NORMAL"
    road_condition: str = "GOOD"

    route_distance_km: Optional[float] = None

    # ----------------------------------------------------------
    # Routing configuration
    # ----------------------------------------------------------

    TRAFFIC_MULTIPLIERS: ClassVar[dict] = {
        "LIGHT": 1.00,
        "NORMAL": 1.00,
        "MODERATE": 1.15,
        "HEAVY": 1.30,
        "SEVERE": 1.50,
    }

    ROAD_MULTIPLIERS: ClassVar[dict] = {
        "GOOD": 1.00,
        "AVERAGE": 1.10,
        "POOR": 1.25,
    }

    AMBULANCE_SPEEDS: ClassVar[dict] = {
        "BLS": 45.0,
        "ALS": 50.0,
        "ICU": 50.0,
        "TRAUMA": 55.0,
        "DEFAULT": 50.0,
    }

    # ----------------------------------------------------------
    # Get traffic multiplier
    # ----------------------------------------------------------

    def get_traffic_multiplier(self):

        return self.TRAFFIC_MULTIPLIERS.get(
            str(self.traffic_level).upper(),
            1.00,
        )

    # ----------------------------------------------------------
    # Get road multiplier
    # ----------------------------------------------------------

    def get_road_multiplier(self):

        return self.ROAD_MULTIPLIERS.get(
            str(self.road_condition).upper(),
            1.00,
        )

    # ----------------------------------------------------------
    # Get ambulance speed
    # ----------------------------------------------------------

    def get_speed_kmh(self):

        ambulance_type = (
            str(self.ambulance_type).upper()
        )

        return self.AMBULANCE_SPEEDS.get(
            ambulance_type,
            self.AMBULANCE_SPEEDS["DEFAULT"],
        )

    # ----------------------------------------------------------
    # Recalculate current route ETA
    #
    # This is used when traffic/road conditions change.
    # It does NOT calculate a new hospital route.
    # ----------------------------------------------------------

    def recalculate_eta(self):

        if self.base_eta_minutes is None:
            return None

        traffic_multiplier = (
            self.get_traffic_multiplier()
        )

        road_multiplier = (
            self.get_road_multiplier()
        )

        self.eta_minutes = round(
            max(
                0.0,
                self.base_eta_minutes
                * traffic_multiplier
                * road_multiplier,
            ),
            2,
        )

        return self.eta_minutes

    # ----------------------------------------------------------
    # Straight-line distance to hospital
    # ----------------------------------------------------------

    def distance_to_hospital(
        self,
        hospital,
    ):

        lat1 = radians(float(self.latitude))
        lon1 = radians(float(self.longitude))

        lat2 = radians(float(hospital.latitude))
        lon2 = radians(float(hospital.longitude))

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            sin(dlat / 2) ** 2
            +
            cos(lat1)
            * cos(lat2)
            * sin(dlon / 2) ** 2
        )

        a = min(
            1.0,
            max(0.0, a),
        )

        c = 2 * atan2(
            sqrt(a),
            sqrt(1 - a),
        )

        earth_radius_km = 6371.0

        return round(
            earth_radius_km * c,
            3,
        )

    # ----------------------------------------------------------
    # Estimate ETA to a specific hospital
    #
    # IMPORTANT:
    # This calculates ETA from the ambulance's CURRENT
    # position to the candidate hospital.
    #
    # Therefore this should be used when comparing alternative
    # hospitals during redirection.
    # ----------------------------------------------------------

    def estimate_eta_to_hospital(
        self,
        hospital,
    ):

        distance_km = (
            self.distance_to_hospital(
                hospital
            )
        )

        speed_kmh = self.get_speed_kmh()

        if speed_kmh <= 0:
            speed_kmh = 50.0

        base_eta = (
            distance_km
            / speed_kmh
            * 60.0
        )

        traffic_multiplier = (
            self.get_traffic_multiplier()
        )

        road_multiplier = (
            self.get_road_multiplier()
        )

        eta = (
            base_eta
            * traffic_multiplier
            * road_multiplier
        )

        return round(
            max(0.1, eta),
            2,
        )

    # ----------------------------------------------------------
    # Compatibility alias
    # ----------------------------------------------------------

    def calculate_eta_to_hospital(
        self,
        hospital,
    ):

        return self.estimate_eta_to_hospital(
            hospital
        )


# ==============================================================
# HOSPITAL STATE
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

    # ----------------------------------------------------------
    # Available beds
    # ----------------------------------------------------------

    @property
    def available_beds(self):

        return max(
            0,
            int(self.capacity)
            - int(self.current_load),
        )

    # ----------------------------------------------------------
    # Available ICU beds
    # ----------------------------------------------------------

    @property
    def available_icu(self):

        return max(
            0,
            int(self.icu_capacity)
            - int(self.current_icu_load),
        )

    # ----------------------------------------------------------
    # Hospital full
    # ----------------------------------------------------------

    @property
    def is_full(self):

        return self.available_beds <= 0

    # ----------------------------------------------------------
    # ICU availability
    # ----------------------------------------------------------

    @property
    def icu_available(self):

        return self.available_icu > 0


# ==============================================================
# DISPATCH STATE
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
    # Add incident
    # ----------------------------------------------------------

    def add_incident(
        self,
        incident,
    ):

        self.incidents[
            incident.incident_id
        ] = incident

    # ----------------------------------------------------------
    # Add ambulance
    # ----------------------------------------------------------

    def add_ambulance(
        self,
        ambulance,
    ):

        self.ambulances[
            ambulance.ambulance_id
        ] = ambulance

    # ----------------------------------------------------------
    # Add hospital
    # ----------------------------------------------------------

    def add_hospital(
        self,
        hospital,
    ):

        self.hospitals[
            hospital.hospital_id
        ] = hospital

    # ----------------------------------------------------------
    # Add event
    # ----------------------------------------------------------

    def add_event(
        self,
        message,
    ):

        self.events.append({
            "time": self.current_time,
            "message": str(message),
        })

    # ----------------------------------------------------------
    # Available ambulances
    # ----------------------------------------------------------

    def get_available_ambulances(self):

        return [
            ambulance
            for ambulance
            in self.ambulances.values()
            if str(ambulance.status).upper()
            == "AVAILABLE"
        ]

    # ----------------------------------------------------------
    # Active incidents
    # ----------------------------------------------------------

    def get_active_incidents(self):

        active_statuses = {
            "DISPATCHED",
            "EN_ROUTE",
            "REDIRECTED",
        }

        return [
            incident
            for incident
            in self.incidents.values()
            if str(incident.status).upper()
            in active_statuses
        ]

    # ----------------------------------------------------------
    # Advance simulation time
    # ----------------------------------------------------------

    def advance_time(
        self,
        minutes=1,
    ):

        minutes = int(minutes)

        if minutes < 0:
            raise ValueError(
                "Time cannot move backwards."
            )

        self.current_time += minutes


# ==============================================================
# BASIC STATE TEST
# ==============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("DISPATCH STATE TEST")
    print("=" * 70)

    ambulance = AmbulanceState(
        ambulance_id="AMB_TEST",
        ambulance_type="ALS",
        latitude=26.9124,
        longitude=75.7873,
    )

    hospital = HospitalState(
        hospital_id="HOSP_TEST",
        hospital_type="General",
        latitude=26.9200,
        longitude=75.8000,
        capacity=300,
        current_load=240,
        icu_capacity=50,
        current_icu_load=35,
    )

    eta = ambulance.estimate_eta_to_hospital(
        hospital
    )

    print()
    print(
        f"Distance:        "
        f"{ambulance.distance_to_hospital(hospital):.2f} km"
    )

    print(
        f"Estimated ETA:   "
        f"{eta:.2f} min"
    )

    print(
        f"Available beds:  "
        f"{hospital.available_beds}"
    )

    print(
        f"Available ICU:   "
        f"{hospital.available_icu}"
    )

    print(
        f"Hospital full:   "
        f"{hospital.is_full}"
    )

    print(
        f"ICU available:   "
        f"{hospital.icu_available}"
    )

    print()
    print("=" * 70)
    print("STATE TEST COMPLETE")
    print("=" * 70)