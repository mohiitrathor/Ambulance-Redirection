"""
RAAH External Adapter Registry
==============================

Manages provider registration, lifecycle, and health diagnostics for
external telemetry ingestion adapters.
"""

import logging
from typing import Dict, Any, Optional

from api.settings import settings
from api.adapters.interfaces import (
    IncidentSource,
    LocationSource,
    HospitalStatusSource,
    TrafficSource,
)
from api.adapters.mock_providers import (
    MockCADProvider,
    MockGPSProvider,
    MockHospitalProvider,
    MockTrafficProvider,
)

logger = logging.getLogger("raah.adapters.registry")


class AdapterRegistry:
    """
    Central registry for active external telemetry and CAD providers.
    """

    def __init__(self):
        self._cad_provider: Optional[IncidentSource] = None
        self._gps_provider: Optional[LocationSource] = None
        self._hospital_provider: Optional[HospitalStatusSource] = None
        self._traffic_provider: Optional[TrafficSource] = None

        self._initialize_default_providers()

    def _initialize_default_providers(self):
        """Initialize active providers based on configuration settings."""
        # CAD
        if settings.cad_provider == "mock":
            self._cad_provider = MockCADProvider(provider_id="CAD_911_MOCK")
        else:
            self._cad_provider = MockCADProvider(provider_id=f"CAD_{settings.cad_provider.upper()}")

        # GPS
        if settings.gps_provider == "mock":
            self._gps_provider = MockGPSProvider(provider_id="AVLS_GPS_MOCK")
        else:
            self._gps_provider = MockGPSProvider(provider_id=f"GPS_{settings.gps_provider.upper()}")

        # Hospital
        if settings.hospital_provider == "mock":
            self._hospital_provider = MockHospitalProvider(provider_id="HOSP_FEED_MOCK")
        else:
            self._hospital_provider = MockHospitalProvider(provider_id=f"HOSP_{settings.hospital_provider.upper()}")

        # Traffic
        if settings.traffic_provider == "mock":
            self._traffic_provider = MockTrafficProvider(provider_id="TRAFFIC_FEED_MOCK")
        else:
            self._traffic_provider = MockTrafficProvider(provider_id=f"TRAFFIC_{settings.traffic_provider.upper()}")

        logger.info(
            "AdapterRegistry initialized with providers: CAD=%s, GPS=%s, HOSP=%s, TRAFFIC=%s",
            settings.cad_provider,
            settings.gps_provider,
            settings.hospital_provider,
            settings.traffic_provider,
        )

    # ------------------------------------------------------------------
    # PROVIDER ACCESSORS & REGISTRATION
    # ------------------------------------------------------------------

    def get_cad_provider(self) -> IncidentSource:
        return self._cad_provider

    def set_cad_provider(self, provider: IncidentSource):
        self._cad_provider = provider

    def get_gps_provider(self) -> LocationSource:
        return self._gps_provider

    def set_gps_provider(self, provider: LocationSource):
        self._gps_provider = provider

    def get_hospital_provider(self) -> HospitalStatusSource:
        return self._hospital_provider

    def set_hospital_provider(self, provider: HospitalStatusSource):
        self._hospital_provider = provider

    def get_traffic_provider(self) -> TrafficSource:
        return self._traffic_provider

    def set_traffic_provider(self, provider: TrafficSource):
        self._traffic_provider = provider

    # ------------------------------------------------------------------
    # HEALTH CHECK
    # ------------------------------------------------------------------

    def health_check_all(self) -> Dict[str, Any]:
        """Probe all active providers and return diagnostic status dictionary."""
        checks = {}
        for name, provider in [
            ("cad", self._cad_provider),
            ("gps", self._gps_provider),
            ("hospital", self._hospital_provider),
            ("traffic", self._traffic_provider),
        ]:
            if provider is not None:
                try:
                    checks[name] = provider.health_check()
                except Exception as ex:
                    checks[name] = {"healthy": False, "error": str(ex)}
            else:
                checks[name] = {"healthy": False, "error": "Provider not configured"}

        overall_healthy = all(c.get("healthy", False) for c in checks.values())
        return {
            "healthy": overall_healthy,
            "providers": checks,
        }


# Global singleton instance
adapter_registry = AdapterRegistry()
