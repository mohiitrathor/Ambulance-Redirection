"""
RAAH Disaster Drill Scenario Generators (M10 Phase 2)
=====================================================

Deterministic scenario generators producing ScenarioDefinition objects
with explicit random seeds and chronological event scheduling.
Never mutates or relies on global PRNG state.
"""

import random
from typing import Dict, List, Optional, Any

from Dispatch.scenarios.models import (
    ScenarioDefinition,
    ScenarioConfig,
    ScheduledIncident,
    ScheduledMCI,
    ScheduledReposition,
    ScheduledRedirection,
    ScheduledHospitalEvent,
)


def generate_pileup_scenario(
    seed: int = 42,
    casualty_count: int = 15,
    scenario_id: Optional[str] = None,
    duration_minutes: int = 15,
) -> ScenarioDefinition:
    """
    NH-48 / Jaipur Ring Road Multi-Vehicle Pileup.
    High-speed highway collision with mixed trauma severity, simultaneous
    fleet dispatch across zones, and hospital load dispersal.
    """
    rng = random.Random(seed)
    sid = scenario_id or f"DRILL_PILEUP_{seed}_{casualty_count}"

    # Highway interchange coordinates (NH-48 Ajmer Road / Ring Road)
    scene_lat = 26.8350
    scene_lon = 75.6650

    mci = ScheduledMCI(
        sim_time=1,
        mci_id=f"MCI_PILEUP_{seed}",
        name="NH-48 Multi-Vehicle Pileup",
        latitude=scene_lat,
        longitude=scene_lon,
        estimated_casualties=casualty_count,
        primary_condition="Trauma",
        notes="High-speed pileup involving heavy commercial trucks, buses, and passenger vehicles.",
    )

    # Add a proactive fleet repositioning to cover southern corridor at T=0
    reposition = ScheduledReposition(
        sim_time=0,
        ambulance_id="AMB_0002",
        target_lat=26.8500,
        target_lon=75.7200,
        reason="PROACTIVE_HIGHWAY_SURGE_COVERAGE",
    )

    # Initial ordinary incident occurring before the pileup
    initial_inc = ScheduledIncident(
        sim_time=0,
        incident_id=1,
        notes="Routine baseline intake before highway disaster",
    )

    config = ScenarioConfig(
        duration_minutes=duration_minutes,
        tick_minutes=1.0,
        snapshot_interval_ticks=2,
        deterministic_seed=seed,
    )

    return ScenarioDefinition(
        scenario_id=sid,
        name="NH-48 Multi-Vehicle Pileup",
        description="Mass-casualty collision on NH-48 with severe trauma casualties and multi-zone ambulance response.",
        config=config,
        scheduled_incidents=[initial_inc],
        scheduled_mcis=[mci],
        scheduled_repositions=[reposition],
        scheduled_redirections=[],
        scheduled_hospital_events=[],
        metadata={"drill_type": "NH48_MULTI_VEHICLE_PILEUP", "casualty_count": casualty_count, "seed": seed},
        created_at="2026-08-31T00:00:00+00:00",
    )


def generate_dual_mci_scenario(
    seed: int = 42,
    casualties_per_mci: int = 12,
    scenario_id: Optional[str] = None,
    duration_minutes: int = 18,
) -> ScenarioDefinition:
    """
    Dual-MCI Earthquake / Structural Collapses.
    Two simultaneous catastrophic events in geographically opposite Jaipur zones
    (North: Old City / Amer Road vs South: Sitapura Industrial Area),
    competing directly for citywide available ambulances and ICU beds.
    """
    rng = random.Random(seed)
    total_cas = casualties_per_mci * 2
    sid = scenario_id or f"DRILL_DUAL_MCI_{seed}_{total_cas}"

    # Scene A: Northern Jaipur (Historic Old City / Amer Road)
    mci_north = ScheduledMCI(
        sim_time=1,
        mci_id=f"MCI_NORTH_{seed}",
        name="Old City Heritage Market Collapse",
        latitude=26.9550,
        longitude=75.8350,
        estimated_casualties=casualties_per_mci,
        primary_condition="Trauma",
        notes="Structural collapse of dense commercial marketplace following tremor.",
    )

    # Scene B: Southern Jaipur (Sitapura Industrial Zone)
    mci_south = ScheduledMCI(
        sim_time=2,
        mci_id=f"MCI_SOUTH_{seed}",
        name="Sitapura Industrial Warehouse Collapse",
        latitude=26.7850,
        longitude=75.8250,
        estimated_casualties=casualties_per_mci,
        primary_condition="Trauma",
        notes="Secondary industrial collapse competing for southern fleet and burn/trauma units.",
    )

    config = ScenarioConfig(
        duration_minutes=duration_minutes,
        tick_minutes=1.0,
        snapshot_interval_ticks=2,
        deterministic_seed=seed,
    )

    return ScenarioDefinition(
        scenario_id=sid,
        name="Dual-MCI Simultaneous Disaster",
        description="Two simultaneous catastrophic MCI scenes in North and South Jaipur competing for citywide EMS fleet.",
        config=config,
        scheduled_incidents=[],
        scheduled_mcis=[mci_north, mci_south],
        scheduled_repositions=[],
        scheduled_redirections=[],
        scheduled_hospital_events=[],
        metadata={"drill_type": "DUAL_MCI_EARTHQUAKE", "casualty_count": total_cas, "seed": seed},
        created_at="2026-08-31T00:00:00+00:00",
    )


def generate_hospital_saturation_scenario(
    seed: int = 42,
    incident_count: int = 15,
    scenario_id: Optional[str] = None,
    duration_minutes: int = 15,
) -> ScenarioDefinition:
    """
    Citywide Hospital Saturation & Epidemic Surge.
    Sequential waves of severe respiratory and cardiac emergencies coincide with
    abrupt capacity saturation at key tertiary medical centers.
    Tests HospitalBalancer avoidance of saturated facilities and ICU preservation.
    """
    rng = random.Random(seed)
    sid = scenario_id or f"DRILL_SATURATION_{seed}_{incident_count}"

    # Staggered saturation events for primary hospitals
    hospital_events = [
        ScheduledHospitalEvent(sim_time=1, hospital_id="HOSP_001", event_type="SET_SATURATED"),
        ScheduledHospitalEvent(sim_time=2, hospital_id="HOSP_084", event_type="SET_SATURATED"),
        ScheduledHospitalEvent(sim_time=4, hospital_id="HOSP_117", event_type="SET_SATURATED"),
        ScheduledHospitalEvent(sim_time=6, hospital_id="HOSP_001", event_type="RELEASE_SATURATED"),
    ]

    scheduled_incidents = []
    conditions = ["Cardiac", "Respiratory", "Trauma", "Infection"]

    for i in range(incident_count):
        # Disperse across sim minutes 0 to 6
        t = i % 7
        cond = conditions[i % len(conditions)]
        sev = "Critical" if (i % 3 == 0) else "Emergency"
        lat = 26.9100 + rng.uniform(-0.04, 0.04)
        lon = 75.7800 + rng.uniform(-0.04, 0.04)

        scheduled_incidents.append(
            ScheduledIncident(
                sim_time=t,
                condition=cond,
                severity=sev,
                latitude=round(lat, 5),
                longitude=round(lon, 5),
                notes=f"Surge casualty #{i+1} ({cond} - {sev})",
            )
        )

    # Sort chronologically
    scheduled_incidents.sort(key=lambda inc: inc.sim_time)

    config = ScenarioConfig(
        duration_minutes=duration_minutes,
        tick_minutes=1.0,
        snapshot_interval_ticks=2,
        deterministic_seed=seed,
    )

    return ScenarioDefinition(
        scenario_id=sid,
        name="Citywide Hospital Saturation Crisis",
        description="Emergency waves confronting progressive bed and ICU exhaustion across key tertiary hospitals.",
        config=config,
        scheduled_incidents=scheduled_incidents,
        scheduled_mcis=[],
        scheduled_repositions=[],
        scheduled_redirections=[],
        scheduled_hospital_events=hospital_events,
        metadata={"drill_type": "CITYWIDE_HOSPITAL_SATURATION", "incident_count": incident_count, "seed": seed},
        created_at="2026-08-31T00:00:00+00:00",
    )


def generate_casualty_surge(
    casualty_count: int = 50,
    seed: int = 42,
    mci_count: int = 1,
    scenario_id: Optional[str] = None,
    duration_minutes: int = 15,
    hospital_surge: bool = False,
) -> ScenarioDefinition:
    """
    Generalized Parameterized Casualty Surge Stress Scenario.
    Supports arbitrary casualty loads (25, 50, 100, etc.) partitioned across
    1 or more concurrent or staggered MCI scenes.
    """
    rng = random.Random(seed)
    sid = scenario_id or f"DRILL_SURGE_{casualty_count}_CAS_{seed}"

    mcis = []
    per_mci = max(1, casualty_count // max(1, mci_count))
    remainder = casualty_count % max(1, mci_count)

    # Anchor locations in different sectors of Jaipur
    anchors = [
        ("Central Metro Station", 26.9180, 75.7920),
        ("Sanganer Flyover Collapse", 26.8150, 75.8050),
        ("Mansarovar Commercial Fire", 26.8650, 75.7600),
        ("VKI Industrial Chemical Spill", 26.9850, 75.7700),
    ]

    for m_idx in range(mci_count):
        cas = per_mci + (remainder if m_idx == 0 else 0)
        anchor_name, base_lat, base_lon = anchors[m_idx % len(anchors)]
        t = (m_idx * 2) % 6

        mcis.append(
            ScheduledMCI(
                sim_time=t,
                mci_id=f"MCI_SURGE_{seed}_{m_idx+1}",
                name=f"Mass Surge: {anchor_name}",
                latitude=round(base_lat + rng.uniform(-0.005, 0.005), 5),
                longitude=round(base_lon + rng.uniform(-0.005, 0.005), 5),
                estimated_casualties=cas,
                primary_condition="Trauma" if m_idx % 2 == 0 else "Respiratory",
                notes=f"Surge cluster #{m_idx+1} carrying {cas} casualties.",
            )
        )

    # Sort MCIs chronologically
    mcis.sort(key=lambda m: m.sim_time)

    # Optional hospital saturation events under heavy load
    hosp_events = []
    if hospital_surge:
        hosp_events.append(ScheduledHospitalEvent(sim_time=2, hospital_id="HOSP_001", event_type="SET_SATURATED"))
        hosp_events.append(ScheduledHospitalEvent(sim_time=3, hospital_id="HOSP_084", event_type="SET_SATURATED"))

    config = ScenarioConfig(
        duration_minutes=duration_minutes,
        tick_minutes=1.0,
        snapshot_interval_ticks=2,
        deterministic_seed=seed,
    )

    return ScenarioDefinition(
        scenario_id=sid,
        name=f"Casualty Surge ({casualty_count} Patients)",
        description=f"High-volume stress scenario injecting {casualty_count} emergency casualties across {mci_count} incident sites.",
        config=config,
        scheduled_incidents=[],
        scheduled_mcis=mcis,
        scheduled_repositions=[],
        scheduled_redirections=[],
        scheduled_hospital_events=hosp_events,
        metadata={
            "drill_type": "CASUALTY_SURGE",
            "casualty_count": casualty_count,
            "mci_count": mci_count,
            "seed": seed,
        },
        created_at="2026-08-31T00:00:00+00:00",
    )
