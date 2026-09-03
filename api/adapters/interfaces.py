"""
RAAH External Provider Interfaces & Protocols
=============================================

Defines the abstract contracts for external CAD, GPS, Hospital status,
and Traffic telemetry integration providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from api.adapters.models import NormalizedEvent


class IncidentSource(ABC):
    """Abstract contract for CAD / 911 / 108 emergency incident intake sources."""

    @abstractmethod
    def fetch_pending_incidents(self) -> List[NormalizedEvent]:
        """Poll or batch-retrieve new pending incident events."""
        pass

    @abstractmethod
    def acknowledge_incident(self, source_event_id: str) -> bool:
        """Acknowledge successful receipt and dispatch of an incident."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Probe provider connectivity and status."""
        pass


class LocationSource(ABC):
    """Abstract contract for AVL / GPS vehicle location feeds."""

    @abstractmethod
    def fetch_locations(self) -> List[NormalizedEvent]:
        """Fetch latest GPS coordinate updates for the fleet."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Probe provider connectivity and status."""
        pass


class HospitalStatusSource(ABC):
    """Abstract contract for Hospital bed, ICU, and diversion telemetry."""

    @abstractmethod
    def fetch_hospital_statuses(self) -> List[NormalizedEvent]:
        """Fetch latest capacity and load telemetry from regional hospitals."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Probe provider connectivity and status."""
        pass


class TrafficSource(ABC):
    """Abstract contract for real-time traffic conditions and travel times."""

    @abstractmethod
    def fetch_traffic_updates(self) -> List[NormalizedEvent]:
        """Fetch real-time traffic congestion and road condition advisories."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Probe provider connectivity and status."""
        pass
