"""
RAAH Geographic Zone Coverage Engine
====================================

Defines the 6 strategic emergency operational zones for Jaipur metropolitan area,
assigns coordinates to zones, computes fleet coverage scores, identifies deficits
and surpluses, and generates advisory reposition recommendations (data only).
"""

from dataclasses import dataclass, field
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, List, Tuple, Optional


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Standard spherical Haversine formula in kilometers."""
    r1, o1 = radians(float(lat1)), radians(float(lon1))
    r2, o2 = radians(float(lat2)), radians(float(lon2))
    dlat = r2 - r1
    dlon = o2 - o1
    a = sin(dlat / 2.0) ** 2 + cos(r1) * cos(r2) * sin(dlon / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
    return round(6371.0 * c, 3)


@dataclass
class ZoneCoverage:
    """
    Real-time coverage metrics for an operational zone.
    """
    zone_id: str
    zone_name: str
    centroid: Tuple[float, float]
    staging_post: Tuple[float, float]
    target_capacity: int = 5
    available_ambulances: List[str] = field(default_factory=list)
    total_ambulances: int = 0
    demand_weight: float = 1.0
    coverage_score: float = 1.0
    status: str = "BALANCED"  # "DEFICIT", "BALANCED", "SURPLUS"


@dataclass
class RepositionAdvisory:
    """
    Recommended idle ambulance repositioning movement (DATA ONLY - not executed).
    """
    advisory_id: str
    ambulance_id: str
    origin_zone: str
    target_zone: str
    origin_coords: Tuple[float, float]
    target_staging_post: Tuple[float, float]
    reason: str
    priority: str = "NORMAL"  # "LOW", "NORMAL", "HIGH"


class CoverageEngine:
    """
    Evaluates citywide ambulance distribution across 6 strategic Jaipur sectors.
    """

    # 6 Strategic Jaipur Operational Zones
    ZONES: Dict[str, dict] = {
        "JAIPUR_CENTRAL": {
            "name": "Central / Walled City & SMS Corridor",
            "centroid": (26.9200, 75.8150),
            "staging_post": (26.9180, 75.8150),
            "target_capacity": 6,
            "description": "High-density historical center, commercial markets, SMS Medical College",
        },
        "JAIPUR_NORTH": {
            "name": "North / Vidhyadhar Nagar & Amer",
            "centroid": (26.9650, 75.7850),
            "staging_post": (26.9600, 75.7850),
            "target_capacity": 4,
            "description": "Northern residential sectors, tourist corridor, Sikar Highway axis",
        },
        "JAIPUR_WEST": {
            "name": "West / Vaishali Nagar & Civil Lines",
            "centroid": (26.9100, 75.7400),
            "staging_post": (26.9080, 75.7420),
            "target_capacity": 5,
            "description": "Western residential suburbs, commercial centers, Ajmer Road expressway",
        },
        "JAIPUR_SOUTH": {
            "name": "South / Mansarovar & Gopalpura",
            "centroid": (26.8550, 75.7700),
            "staging_post": (26.8520, 75.7750),
            "target_capacity": 6,
            "description": "Major southern residential hub, educational belt, New Sanganer Road",
        },
        "JAIPUR_EAST": {
            "name": "East / Malviya Nagar & Airport",
            "centroid": (26.8650, 75.8300),
            "staging_post": (26.8620, 75.8320),
            "target_capacity": 5,
            "description": "Eastern commercial district, JLN Marg corridor, Jaipur International Airport",
        },
        "JAIPUR_SUBURBAN": {
            "name": "Suburban / Sitapura & Jagatpura",
            "centroid": (26.7900, 75.8400),
            "staging_post": (26.7950, 75.8450),
            "target_capacity": 4,
            "description": "Industrial export zones, institutional campuses, southern Ring Road",
        },
    }

    DEFICIT_THRESHOLD: float = 0.60
    SURPLUS_THRESHOLD: float = 1.40

    def __init__(self, zones: Optional[Dict[str, dict]] = None):
        self.zones = zones or self.ZONES
        self._precomputed_centroids = []
        for zid, zdata in self.zones.items():
            c_lat, c_lon = zdata["centroid"]
            r2, o2 = radians(float(c_lat)), radians(float(c_lon))
            self._precomputed_centroids.append((zid, r2, o2, cos(r2)))

    def assign_zone(self, latitude: float, longitude: float) -> str:
        """
        Assign a coordinate pair to the nearest strategic zone centroid.
        Uses exact monotonic spherical haversine chord minimization.
        """
        r1, o1 = radians(float(latitude)), radians(float(longitude))
        cos_r1 = cos(r1)
        best_zone = "JAIPUR_CENTRAL"
        min_a = float("inf")

        for zone_id, r2, o2, cos_r2 in self._precomputed_centroids:
            dlat_half = (r2 - r1) * 0.5
            dlon_half = (o2 - o1) * 0.5
            a = sin(dlat_half) ** 2 + cos_r1 * cos_r2 * (sin(dlon_half) ** 2)
            if a < min_a:
                min_a = a
                best_zone = zone_id

        return best_zone

    def evaluate_coverage(
        self,
        ambulances: dict,
        recent_incident_coords: Optional[List[Tuple[float, float]]] = None,
    ) -> Dict[str, ZoneCoverage]:
        """
        Compute real-time coverage metrics across all 6 zones.
        `ambulances` is the state dictionary {ambulance_id: AmbulanceState}.
        """
        # Initialize zone metrics
        zone_metrics: Dict[str, ZoneCoverage] = {}
        for zid, zdata in self.zones.items():
            zone_metrics[zid] = ZoneCoverage(
                zone_id=zid,
                zone_name=zdata["name"],
                centroid=zdata["centroid"],
                staging_post=zdata["staging_post"],
                target_capacity=zdata["target_capacity"],
            )

        # Count ambulances in each zone
        for amb_id, amb in ambulances.items():
            z = self.assign_zone(float(amb.latitude), float(amb.longitude))
            if z in zone_metrics:
                zm = zone_metrics[z]
                zm.total_ambulances += 1
                # An ambulance is available for coverage if AVAILABLE or currently REPOSITIONING
                is_avail = str(getattr(amb, "status", "")).upper() in ("AVAILABLE", "REPOSITIONING")
                if is_avail and getattr(amb, "incident_id", None) is None:
                    zm.available_ambulances.append(str(amb_id))

        # Factor in recent incident demand weighting
        demand_counts: Dict[str, int] = {zid: 0 for zid in self.zones}
        if recent_incident_coords:
            for lat, lon in recent_incident_coords:
                z = self.assign_zone(lat, lon)
                demand_counts[z] = demand_counts.get(z, 0) + 1

        total_demand = sum(demand_counts.values()) or 1
        avg_demand_per_zone = total_demand / float(len(self.zones))

        for zid, zm in zone_metrics.items():
            # Demand multiplier: scaled between 0.8 and 2.0
            raw_weight = demand_counts[zid] / max(1.0, avg_demand_per_zone)
            zm.demand_weight = round(max(0.8, min(2.0, raw_weight)), 2)

            effective_target = max(1, zm.target_capacity * zm.demand_weight)
            score = len(zm.available_ambulances) / effective_target
            zm.coverage_score = round(score, 2)

            if zm.coverage_score < self.DEFICIT_THRESHOLD:
                zm.status = "DEFICIT"
            elif zm.coverage_score > self.SURPLUS_THRESHOLD:
                zm.status = "SURPLUS"
            else:
                zm.status = "BALANCED"

        return zone_metrics

    def get_reposition_recommendations(
        self,
        ambulances: dict,
        recent_incident_coords: Optional[List[Tuple[float, float]]] = None,
    ) -> List[RepositionAdvisory]:
        """
        Identify deficit zones and recommend candidate idle ambulances
        from nearby surplus zones to rebalance coverage (DATA ONLY).
        """
        coverage = self.evaluate_coverage(ambulances, recent_incident_coords)
        deficits = [zm for zm in coverage.values() if zm.status == "DEFICIT"]
        surpluses = [zm for zm in coverage.values() if zm.status == "SURPLUS"]

        if not deficits or not surpluses:
            return []

        # Sort deficits worst-first (lowest coverage score)
        deficits.sort(key=lambda zm: zm.coverage_score)
        # Sort surpluses highest-first
        surpluses.sort(key=lambda zm: zm.coverage_score, reverse=True)

        recommendations: List[RepositionAdvisory] = []
        assigned_units = set()

        for def_zm in deficits:
            for sur_zm in surpluses:
                # Find available idle units in surplus zone
                available_candidates = [
                    uid for uid in sur_zm.available_ambulances
                    if uid not in assigned_units
                ]
                if not available_candidates:
                    continue

                # Pick candidate closest to the deficit zone staging post
                best_amb_id = None
                best_dist = float("inf")
                target_post = def_zm.staging_post

                for uid in available_candidates:
                    amb = ambulances[uid]
                    # Double check unit is completely idle
                    if str(amb.status).upper() != "AVAILABLE" or amb.incident_id is not None:
                        continue
                    d = _haversine_distance_km(float(amb.latitude), float(amb.longitude), target_post[0], target_post[1])
                    if d < best_dist:
                        best_dist = d
                        best_amb_id = uid

                if best_amb_id:
                    assigned_units.add(best_amb_id)
                    amb_obj = ambulances[best_amb_id]
                    advisory = RepositionAdvisory(
                        advisory_id=f"ADV-{best_amb_id}-{def_zm.zone_id}",
                        ambulance_id=best_amb_id,
                        origin_zone=sur_zm.zone_id,
                        target_zone=def_zm.zone_id,
                        origin_coords=(float(amb_obj.latitude), float(amb_obj.longitude)),
                        target_staging_post=target_post,
                        reason=(
                            f"Rebalance coverage: {sur_zm.zone_name} (surplus score {sur_zm.coverage_score}) "
                            f"-> {def_zm.zone_name} (deficit score {def_zm.coverage_score})"
                        ),
                        priority="HIGH" if def_zm.coverage_score < 0.3 else "NORMAL",
                    )
                    recommendations.append(advisory)
                    break  # One recommendation per deficit zone per evaluation pass

        return recommendations
