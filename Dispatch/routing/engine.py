"""
RAAH RoutingEngine Abstraction
==============================

Provides an isolated, pluggable interface for distance computation,
ETA estimation, route polyline generation, and vehicle kinematic interpolation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class RouteGeometry:
    """
    Represents a planned route between two coordinates.
    """
    origin: Tuple[float, float]
    destination: Tuple[float, float]
    straight_line_distance_km: float
    route_distance_km: float
    initial_eta_minutes: float
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    routing_engine: str = "LOCAL_APPROX"
    total_duration_minutes: float = 0.0
    elapsed_minutes: float = 0.0


class RouterBase(ABC):
    """
    Abstract base interface for all routing backends.
    """

    @abstractmethod
    def calculate_straight_line_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> float:
        """Calculate direct geometric distance between two points in km."""
        pass

    @abstractmethod
    def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> float:
        """Calculate realistic road or circuity-adjusted route distance in km."""
        pass

    @abstractmethod
    def calculate_eta(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        vehicle_type: str = "DEFAULT",
        traffic_level: str = "NORMAL",
        road_condition: str = "GOOD",
    ) -> float:
        """Calculate trip duration in minutes given vehicle capabilities and conditions."""
        pass

    @abstractmethod
    def generate_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        vehicle_type: str = "DEFAULT",
        traffic_level: str = "NORMAL",
        road_condition: str = "GOOD",
    ) -> RouteGeometry:
        """Generate a complete route with intermediate waypoints."""
        pass

    @abstractmethod
    def interpolate_position(
        self,
        route: RouteGeometry,
        elapsed_minutes: float,
    ) -> Tuple[float, float]:
        """Calculate the live vehicle position along the route waypoints at elapsed time."""
        pass


class RoutingEngine:
    """
    Central dispatcher facade for RAAH routing operations.
    Decouples simulation and dispatch from specific routing implementations.
    """

    def __init__(self, router: RouterBase):
        self._router = router

    @property
    def router(self) -> RouterBase:
        return self._router

    @router.setter
    def router(self, new_router: RouterBase):
        if not isinstance(new_router, RouterBase):
            raise TypeError("router must implement RouterBase interface")
        self._router = new_router

    def calculate_straight_line_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> float:
        return self._router.calculate_straight_line_distance(origin, destination)

    def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> float:
        return self._router.calculate_distance(origin, destination)

    def calculate_eta(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        vehicle_type: str = "DEFAULT",
        traffic_level: str = "NORMAL",
        road_condition: str = "GOOD",
    ) -> float:
        return self._router.calculate_eta(
            origin,
            destination,
            vehicle_type=vehicle_type,
            traffic_level=traffic_level,
            road_condition=road_condition,
        )

    def generate_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        vehicle_type: str = "DEFAULT",
        traffic_level: str = "NORMAL",
        road_condition: str = "GOOD",
    ) -> RouteGeometry:
        return self._router.generate_route(
            origin,
            destination,
            vehicle_type=vehicle_type,
            traffic_level=traffic_level,
            road_condition=road_condition,
        )

    def interpolate_position(
        self,
        route: RouteGeometry,
        elapsed_minutes: float,
    ) -> Tuple[float, float]:
        return self._router.interpolate_position(route, elapsed_minutes)
