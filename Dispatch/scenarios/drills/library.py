"""
RAAH Curated Disaster Drill Catalog (M10 Phase 2)
=================================================

Central catalog of named disaster drills, parameters, and metadata.
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict

from Dispatch.scenarios.models import ScenarioDefinition
from .generators import (
    generate_pileup_scenario,
    generate_dual_mci_scenario,
    generate_hospital_saturation_scenario,
    generate_casualty_surge,
)


@dataclass
class DrillMetadata:
    """Metadata describing a curated disaster drill."""
    name: str
    title: str
    description: str
    category: str
    default_parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DrillLibrary:
    """Catalog of operational disaster drills and stress scenarios."""

    _REGISTRY: Dict[str, Dict[str, Any]] = {
        "NH48_MULTI_VEHICLE_PILEUP": {
            "title": "NH-48 Highway Pileup",
            "description": "Major highway mass-casualty pileup on NH-48 with severe trauma victims and multi-zone ambulance response.",
            "category": "HIGHWAY_TRAUMA",
            "default_parameters": {
                "casualty_count": 15,
                "seed": 42,
                "duration_minutes": 15,
            },
            "generator": generate_pileup_scenario,
        },
        "DUAL_MCI_EARTHQUAKE": {
            "title": "Dual-MCI Simultaneous Seismic Disaster",
            "description": "Two simultaneous catastrophic collapses in North and South Jaipur competing for available fleet and ICU capacity.",
            "category": "MULTI_ZONE_DISASTER",
            "default_parameters": {
                "casualties_per_mci": 12,
                "seed": 42,
                "duration_minutes": 18,
            },
            "generator": generate_dual_mci_scenario,
        },
        "CITYWIDE_HOSPITAL_SATURATION": {
            "title": "Citywide Hospital Saturation Crisis",
            "description": "Sequential waves of acute emergencies confronting sudden bed and ICU exhaustion across key medical centers.",
            "category": "HOSPITAL_CAPACITY",
            "default_parameters": {
                "incident_count": 15,
                "seed": 42,
                "duration_minutes": 15,
            },
            "generator": generate_hospital_saturation_scenario,
        },
        "CASUALTY_SURGE": {
            "title": "Parameterized Casualty Surge",
            "description": "High-volume stress test injecting 25, 50, 100, or arbitrary casualties across multiple incident clusters.",
            "category": "STRESS_SURGE",
            "default_parameters": {
                "casualty_count": 50,
                "mci_count": 2,
                "seed": 42,
                "duration_minutes": 15,
                "hospital_surge": False,
            },
            "generator": generate_casualty_surge,
        },
    }

    @classmethod
    def list_drills(cls) -> List[Dict[str, Any]]:
        """Return catalog of all available drills."""
        out = []
        for name, meta in cls._REGISTRY.items():
            out.append({
                "name": name,
                "title": meta["title"],
                "description": meta["description"],
                "category": meta["category"],
                "default_parameters": dict(meta["default_parameters"]),
            })
        return out

    @classmethod
    def get_drill(cls, name: str) -> Optional[Dict[str, Any]]:
        """Return details for a specific drill."""
        meta = cls._REGISTRY.get(name)
        if not meta:
            return None
        return {
            "name": name,
            "title": meta["title"],
            "description": meta["description"],
            "category": meta["category"],
            "default_parameters": dict(meta["default_parameters"]),
        }

    @classmethod
    def generate(cls, name: str, **kwargs) -> ScenarioDefinition:
        """Instantiate a ScenarioDefinition for the specified drill with parameters."""
        meta = cls._REGISTRY.get(name)
        if not meta:
            raise ValueError(f"Unknown drill name '{name}'. Available: {list(cls._REGISTRY.keys())}")

        params = dict(meta["default_parameters"])
        params.update(kwargs)
        gen_fn: Callable = meta["generator"]
        return gen_fn(**params)
