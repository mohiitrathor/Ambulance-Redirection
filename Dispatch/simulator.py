from pathlib import Path
import sys

import pandas as pd


ROOT = Path(
    __file__
).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "Dispatch"),
)


from dispatch_engine import (
    dispatch_incident,
)

from redirection_engine import (
    evaluate_redirection,
)

from events import (
    EventEngine,
)

from decision_logger import (
    DecisionLogger,
)

from state import (
    DispatchState,
    IncidentState,
    AmbulanceState,
    HospitalState,
)


# ==============================================================
# PATHS
# ==============================================================

DATASET_DIR = (
    ROOT / "Dataset"
)

PATIENTS_PATH = (
    DATASET_DIR
    / "patient_incidents.csv"
)

AMBULANCES_PATH = (
    DATASET_DIR
    / "ambulances.csv"
)

HOSPITALS_PATH = (
    DATASET_DIR
    / "hospitals.csv"
)


# ==============================================================
# SIMULATOR
# ==============================================================

class Simulator:

    ETA_CHANGE_THRESHOLD_PERCENT = 25
    ETA_CHANGE_THRESHOLD_MINUTES = 10

    def __init__(self):

        self.state = DispatchState()

        self.events = EventEngine()

        self.decision_logger = (
            DecisionLogger()
        )

        self.patients = pd.read_csv(
            PATIENTS_PATH
        )

        self.ambulances = pd.read_csv(
            AMBULANCES_PATH
        )

        self.hospitals = pd.read_csv(
            HOSPITALS_PATH
        )

        # Each incident keeps track of
        # hospitals it has already visited.
        self.redirect_history = {}

        # Incidents requiring an ETA review.
        self.eta_recheck_required = set()

        self.load_state()

        self.register_event_handlers()

    # ==========================================================
    # LOAD STATE
    # ==========================================================

    def load_state(self):

        for _, row in (
            self.ambulances.iterrows()
        ):

            ambulance = AmbulanceState(

                ambulance_id=str(
                    row["Ambulance_ID"]
                ),

                ambulance_type=str(
                    row["Ambulance_Type"]
                ),

                latitude=float(
                    row["Latitude"]
                ),

                longitude=float(
                    row["Longitude"]
                ),

                status=str(
                    row["Availability"]
                ).upper(),

                traffic_level=str(
                    row.get(
                        "Traffic_Level",
                        "NORMAL",
                    )
                ).upper(),

                road_condition=str(
                    row.get(
                        "Road_Condition",
                        "GOOD",
                    )
                ).upper(),
            )

            self.state.add_ambulance(
                ambulance
            )

        for _, row in (
            self.hospitals.iterrows()
        ):

            hospital = HospitalState(

                hospital_id=str(
                    row["Hospital_ID"]
                ),

                hospital_type=str(
                    row["Hospital_Type"]
                ),

                latitude=float(
                    row["Latitude"]
                ),

                longitude=float(
                    row["Longitude"]
                ),

                capacity=int(
                    row["Hospital_Capacity"]
                ),

                current_load=int(
                    row["Current_Load"]
                ),

                icu_capacity=int(
                    row["ICU_Capacity"]
                ),

                current_icu_load=int(
                    row["Current_ICU_Load"]
                ),
            )

            self.state.add_hospital(
                hospital
            )

    # ==========================================================
    # EVENT HANDLERS
    # ==========================================================

    def register_event_handlers(self):

        self.events.register_handler(
            "HOSPITAL_FULL",
            self.handle_hospital_full,
        )

        self.events.register_handler(
            "HOSPITAL_LOAD_CHANGE",
            self.handle_hospital_load_change,
        )

        self.events.register_handler(
            "ICU_LOAD_CHANGE",
            self.handle_icu_load_change,
        )

        self.events.register_handler(
            "TRAFFIC_CHANGE",
            self.handle_traffic_change,
        )

        self.events.register_handler(
            "ROAD_CONDITION_CHANGE",
            self.handle_road_condition_change,
        )

        self.events.register_handler(
            "NEW_INCIDENT",
            self.handle_new_incident,
        )

        self.events.register_handler(
            "AMBULANCE_STATUS_CHANGE",
            self.handle_ambulance_status_change,
        )

    # ==========================================================
    # DEFAULT EVENTS
    # ==========================================================

    def schedule_default_events(self):

        # Hospital becomes full.
        self.events.schedule(
            time=5,
            event_type="HOSPITAL_FULL",
            data={
                "hospital_id":
                    "HOSP_182"
            },
        )

        # Major traffic deterioration.
        self.events.schedule(
            time=7,
            event_type="TRAFFIC_CHANGE",
            data={
                "ambulance_id":
                    "AMB_0575",

                "level":
                    "SEVERE",
            },
        )

        # ICU availability changes.
        self.events.schedule(
            time=9,
            event_type="ICU_LOAD_CHANGE",
            data={
                "hospital_id":
                    "HOSP_279",

                "increase":
                    10,
            },
        )

        # Hospital load changes.
        self.events.schedule(
            time=11,
            event_type="HOSPITAL_LOAD_CHANGE",
            data={
                "hospital_id":
                    "HOSP_099",

                "increase":
                    20,
            },
        )

    # ==========================================================
    # CREATE INCIDENT
    # ==========================================================

    def create_incident(
        self,
        incident_id,
    ):

        rows = self.patients[
            self.patients[
                "Incident_ID"
            ]
            == incident_id
        ]

        if rows.empty:

            raise ValueError(
                f"Incident "
                f"{incident_id} "
                f"not found."
            )

        row = rows.iloc[0]

        result = dispatch_incident(
            incident_id
        )

        patient = result.get(
            "patient",
            {},
        )

        ambulance_data = result.get(
            "ambulance"
        )

        hospital_data = result.get(
            "hospital"
        )

        severity = patient.get(
            "predicted_severity",
            "Unknown",
        )

        priority = int(
            str(
                patient.get(
                    "priority",
                    "P5",
                )
            ).replace(
                "P",
                "",
            )
        )

        incident = IncidentState(

            incident_id=int(
                incident_id
            ),

            condition=str(
                row["Condition"]
            ),

            severity=severity,

            priority=priority,

            status=(
                "DISPATCHED"
                if ambulance_data
                else "WAITING"
            ),
        )

        self.state.add_incident(
            incident
        )

        # ------------------------------------------------------
        # AMBULANCE
        # ------------------------------------------------------

        if ambulance_data:

            ambulance_id = str(
                ambulance_data[
                    "ambulance_id"
                ]
            )

            ambulance = (
                self.state.ambulances.get(
                    ambulance_id
                )
            )

            if ambulance:

                ambulance.status = (
                    "EN_ROUTE"
                )

                ambulance.incident_id = (
                    int(incident_id)
                )

                ambulance.base_eta_minutes = (
                    float(
                        ambulance_data[
                            "eta_minutes"
                        ]
                    )
                )

                ambulance.traffic_level = (
                    str(
                        ambulance_data.get(
                            "traffic",
                            "NORMAL",
                        )
                    ).upper()
                )

                ambulance.road_condition = (
                    str(
                        ambulance_data.get(
                            "road_condition",
                            "GOOD",
                        )
                    ).upper()
                )

                ambulance.recalculate_eta()

                incident.ambulance_id = (
                    ambulance_id
                )

        # ------------------------------------------------------
        # HOSPITAL
        # ------------------------------------------------------

        if hospital_data:

            hospital_id = str(
                hospital_data[
                    "hospital_id"
                ]
            )

            incident.hospital_id = (
                hospital_id
            )

            ambulance = (
                self.state.ambulances.get(
                    incident.ambulance_id
                )
            )

            if ambulance:

                ambulance.hospital_id = (
                    hospital_id
                )

        # ------------------------------------------------------
        # HISTORY
        # ------------------------------------------------------

        self.redirect_history[
            int(incident_id)
        ] = {
            str(incident.hospital_id)
        }

        self.state.add_event(
            f"Incident "
            f"{incident_id} "
            f"dispatched."
        )

        return result

    # ==========================================================
    # HOSPITAL FULL
    # ==========================================================

    def handle_hospital_full(
        self,
        data,
    ):

        hospital_id = str(
            data["hospital_id"]
        )

        hospital = (
            self.state.hospitals.get(
                hospital_id
            )
        )

        if hospital is None:
            return

        hospital.current_load = (
            hospital.capacity
        )

        self.state.add_event(
            f"Hospital "
            f"{hospital_id} "
            f"became full."
        )

    # ==========================================================
    # HOSPITAL LOAD
    # ==========================================================

    def handle_hospital_load_change(
        self,
        data,
    ):

        hospital_id = str(
            data["hospital_id"]
        )

        hospital = (
            self.state.hospitals.get(
                hospital_id
            )
        )

        if hospital is None:
            return

        increase = int(
            data.get(
                "increase",
                0,
            )
        )

        hospital.current_load = min(
            hospital.capacity,
            hospital.current_load
            + increase,
        )

        self.state.add_event(
            f"Hospital "
            f"{hospital_id} "
            f"load increased by "
            f"{increase}."
        )

    # ==========================================================
    # ICU LOAD
    # ==========================================================

    def handle_icu_load_change(
        self,
        data,
    ):

        hospital_id = str(
            data["hospital_id"]
        )

        hospital = (
            self.state.hospitals.get(
                hospital_id
            )
        )

        if hospital is None:
            return

        increase = int(
            data.get(
                "increase",
                0,
            )
        )

        hospital.current_icu_load = min(
            hospital.icu_capacity,
            hospital.current_icu_load
            + increase,
        )

        self.state.add_event(
            f"Hospital "
            f"{hospital_id} "
            f"ICU load increased by "
            f"{increase}."
        )

    # ==========================================================
    # TRAFFIC
    # ==========================================================

    def handle_traffic_change(
        self,
        data,
    ):

        ambulance_id = str(
            data["ambulance_id"]
        )

        level = str(
            data["level"]
        ).upper()

        ambulance = (
            self.state.ambulances.get(
                ambulance_id
            )
        )

        if ambulance is None:
            return

        old_eta = (
            ambulance.eta_minutes
        )

        ambulance.traffic_level = (
            level
        )

        ambulance.recalculate_eta()

        new_eta = (
            ambulance.eta_minutes
        )

        self.state.add_event(
            f"Traffic for ambulance "
            f"{ambulance_id} changed to "
            f"{level}. ETA changed from "
            f"{old_eta:.1f} to "
            f"{new_eta:.1f} min."
        )

        if (
            old_eta is None
            or new_eta is None
        ):
            return

        increase = (
            new_eta - old_eta
        )

        percentage = (
            increase
            / max(old_eta, 1)
        ) * 100

        if (
            increase
            >= self.ETA_CHANGE_THRESHOLD_MINUTES
            or
            percentage
            >= self.ETA_CHANGE_THRESHOLD_PERCENT
        ):

            if (
                ambulance.incident_id
                is not None
            ):

                self.eta_recheck_required.add(
                    ambulance.incident_id
                )

                self.state.add_event(
                    f"ETA deterioration "
                    f"detected for incident "
                    f"{ambulance.incident_id}. "
                    f"Hospital destination "
                    f"will be re-evaluated."
                )

    # ==========================================================
    # ROAD CONDITION
    # ==========================================================

    def handle_road_condition_change(
        self,
        data,
    ):

        ambulance_id = str(
            data["ambulance_id"]
        )

        condition = str(
            data["condition"]
        ).upper()

        ambulance = (
            self.state.ambulances.get(
                ambulance_id
            )
        )

        if ambulance is None:
            return

        old_eta = (
            ambulance.eta_minutes
        )

        ambulance.road_condition = (
            condition
        )

        ambulance.recalculate_eta()

        new_eta = (
            ambulance.eta_minutes
        )

        self.state.add_event(
            f"Road condition for "
            f"{ambulance_id} changed to "
            f"{condition}. ETA changed from "
            f"{old_eta:.1f} to "
            f"{new_eta:.1f} min."
        )

        if (
            old_eta is None
            or new_eta is None
        ):
            return

        increase = (
            new_eta - old_eta
        )

        percentage = (
            increase
            / max(old_eta, 1)
        ) * 100

        if (
            increase
            >= self.ETA_CHANGE_THRESHOLD_MINUTES
            or
            percentage
            >= self.ETA_CHANGE_THRESHOLD_PERCENT
        ):

            if (
                ambulance.incident_id
                is not None
            ):

                self.eta_recheck_required.add(
                    ambulance.incident_id
                )

    # ==========================================================
    # NEW INCIDENT
    # ==========================================================

    def handle_new_incident(
        self,
        data,
    ):

        incident_id = int(
            data["incident_id"]
        )

        if incident_id in (
            self.state.incidents
        ):
            return

        self.create_incident(
            incident_id
        )

    # ==========================================================
    # AMBULANCE STATUS
    # ==========================================================

    def handle_ambulance_status_change(
        self,
        data,
    ):

        ambulance_id = str(
            data["ambulance_id"]
        )

        status = str(
            data["status"]
        ).upper()

        ambulance = (
            self.state.ambulances.get(
                ambulance_id
            )
        )

        if ambulance is None:
            return

        ambulance.status = status

        self.state.add_event(
            f"Ambulance "
            f"{ambulance_id} "
            f"status changed to "
            f"{status}."
        )

    # ==========================================================
    # TIME
    # ==========================================================

    def advance_time(
        self,
        minutes=1,
    ):

        self.state.advance_time(
            minutes
        )

        for ambulance in (
            self.state.ambulances.values()
        ):

            if (
                ambulance.status
                != "EN_ROUTE"
            ):
                continue

            if (
                ambulance.eta_minutes
                is None
            ):
                continue

            ambulance.eta_minutes = max(
                0,
                ambulance.eta_minutes
                - minutes,
            )

            if (
                ambulance.eta_minutes
                <= 0
            ):

                ambulance.status = (
                    "ARRIVED"
                )

                incident = (
                    self.state.incidents.get(
                        ambulance.incident_id
                    )
                )

                if incident:

                    incident.status = (
                        "ARRIVED"
                    )

                self.state.add_event(
                    f"Ambulance "
                    f"{ambulance.ambulance_id} "
                    f"arrived at "
                    f"{ambulance.hospital_id}."
                )

    # ==========================================================
    # APPLY REDIRECTION
    # ==========================================================

    def apply_redirection(
        self,
        incident,
        decision,
    ):

        alternative = (
            decision.get(
                "alternative_hospital"
            )
        )

        if alternative is None:
            return False

        new_hospital_id = str(
            alternative[
                "hospital_id"
            ]
        )

        old_hospital_id = str(
            incident.hospital_id
        )

        # Never redirect to the same hospital.
        if (
            new_hospital_id
            == old_hospital_id
        ):
            return False

        # Prevent loops.
        history = (
            self.redirect_history.setdefault(
                incident.incident_id,
                set(),
            )
        )

        if new_hospital_id in history:

            self.state.add_event(
                f"Redirection skipped for "
                f"incident "
                f"{incident.incident_id}: "
                f"{new_hospital_id} was "
                f"already visited."
            )

            return False

        ambulance = (
            self.state.ambulances.get(
                incident.ambulance_id
            )
        )

        eta_before = decision.get(
            "eta_before"
        )

        eta_after = decision.get(
            "eta_after"
        )

        # ------------------------------------------------------
        # APPLY
        # ------------------------------------------------------

        incident.hospital_id = (
            new_hospital_id
        )

        incident.status = (
            "REDIRECTED"
        )

        if ambulance:

            ambulance.hospital_id = (
                new_hospital_id
            )

            if eta_after is not None:

                ambulance.eta_minutes = (
                    float(eta_after)
                )

        history.add(
            new_hospital_id
        )

        # ------------------------------------------------------
        # LOG
        # ------------------------------------------------------

        self.decision_logger.log_redirection(

            incident_id=(
                incident.incident_id
            ),

            current_time=(
                self.state.current_time
            ),

            reason=decision.get(
                "reason",
                "Dynamic redirection.",
            ),

            original_hospital=(
                old_hospital_id
            ),

            new_hospital=(
                new_hospital_id
            ),

            eta_before=eta_before,

            eta_after=eta_after,

            severity=(
                incident.severity
            ),

            ambulance_id=(
                incident.ambulance_id
            ),
        )

        # ------------------------------------------------------
        # EVENT
        # ------------------------------------------------------

        if (
            eta_before is not None
            and eta_after is not None
        ):

            saved = (
                eta_before - eta_after
            )

            self.state.add_event(
                f"Incident "
                f"{incident.incident_id} "
                f"redirected from "
                f"{old_hospital_id} to "
                f"{new_hospital_id}. "
                f"ETA "
                f"{eta_before:.1f} -> "
                f"{eta_after:.1f} min "
                f"({saved:.1f} min saved)."
            )

        else:

            self.state.add_event(
                f"Incident "
                f"{incident.incident_id} "
                f"redirected from "
                f"{old_hospital_id} to "
                f"{new_hospital_id}."
            )

        return True

    # ==========================================================
    # REDIRECTION CHECK
    # ==========================================================

    def check_redirections(self):

        for incident in list(
            self.state.get_active_incidents()
        ):

            if (
                incident.hospital_id
                is None
            ):
                continue

            if (
                incident.ambulance_id
                is None
            ):
                continue

            trigger = None

            if (
                incident.incident_id
                in self.eta_recheck_required
            ):

                trigger = (
                    "ETA_DETERIORATION"
                )

            decision = evaluate_redirection(

                self.state,

                incident.incident_id,

                trigger_reason=trigger,
            )

            # This incident has now been
            # evaluated for this event.
            self.eta_recheck_required.discard(
                incident.incident_id
            )

            if not decision.get(
                "redirect",
                False,
            ):
                continue

            self.apply_redirection(
                incident,
                decision,
            )

    # ==========================================================
    # PROCESS EVENTS
    # ==========================================================

    def process_events(self):

        return self.events.process(
            self.state.current_time
        )

    # ==========================================================
    # DASHBOARD
    # ==========================================================

    def print_dashboard(self):

        print()
        print("=" * 70)
        print(
            "EMERGENCY DISPATCH COMMAND CENTER"
        )
        print("=" * 70)

        print(
            f"TIME: "
            f"{self.state.current_time} min"
        )

        print()
        print("ACTIVE INCIDENTS")
        print("-" * 70)

        print(
            f"{'ID':<7}"
            f"{'PRI':<6}"
            f"{'SEVERITY':<15}"
            f"{'STATUS':<13}"
            f"{'AMBULANCE':<13}"
            f"HOSPITAL"
        )

        for incident in (
            self.state.get_active_incidents()
        ):

            print(
                f"#{incident.incident_id:<6}"
                f"P{incident.priority:<5}"
                f"{incident.severity:<15}"
                f"{incident.status:<13}"
                f"{str(incident.ambulance_id or '-'): <13}"
                f"{incident.hospital_id or '-'}"
            )

        print()
        print("FLEET")
        print("-" * 70)

        counts = {}

        for ambulance in (
            self.state.ambulances.values()
        ):

            counts[
                ambulance.status
            ] = (
                counts.get(
                    ambulance.status,
                    0,
                ) + 1
            )

        print(
            f"Available:       "
            f"{counts.get('AVAILABLE', 0)}"
        )

        print(
            f"En Route:        "
            f"{counts.get('EN_ROUTE', 0)}"
        )

        print(
            f"Busy:            "
            f"{counts.get('BUSY', 0)}"
        )

        print(
            f"Maintenance:     "
            f"{counts.get('MAINTENANCE', 0)}"
        )

        print(
            f"Arrived:         "
            f"{counts.get('ARRIVED', 0)}"
        )

        print()
        print("CURRENT INCIDENTS")
        print("-" * 70)

        for incident in (
            self.state.get_active_incidents()
        ):

            ambulance = (
                self.state.ambulances.get(
                    incident.ambulance_id
                )
            )

            if (
                ambulance
                and ambulance.eta_minutes
                is not None
            ):

                eta = (
                    f"{ambulance.eta_minutes:.1f}"
                    f" min"
                )

            else:

                eta = "-"

            print(
                f"#{incident.incident_id} "
                f"P{incident.priority} "
                f"{incident.severity} | "
                f"AMB "
                f"{incident.ambulance_id or '-'} | "
                f"ETA {eta} | "
                f"HOSP "
                f"{incident.hospital_id or '-'}"
            )

        print()
        print("LATEST EVENTS")
        print("-" * 70)

        for event in (
            self.state.events[-8:]
        ):

            print(
                f"[{event['time']:>3} min] "
                f"{event['message']}"
            )

        print("=" * 70)

    # ==========================================================
    # RUN
    # ==========================================================

    def run(
        self,
        incident_ids,
        duration=15,
    ):

        print("=" * 70)
        print(
            "STARTING DISPATCH SIMULATION"
        )
        print("=" * 70)

        for incident_id in incident_ids:

            try:

                self.create_incident(
                    incident_id
                )

            except Exception as error:

                self.state.add_event(
                    f"Failed to dispatch "
                    f"incident "
                    f"{incident_id}: "
                    f"{error}"
                )

        self.schedule_default_events()

        self.print_dashboard()

        for _ in range(
            duration
        ):

            self.advance_time(
                1
            )

            # Events modify the world first.
            self.process_events()

            # Then the dispatch system
            # reacts to the new world state.
            self.check_redirections()

            if (
                self.state.current_time
                % 5
                == 0
                or
                self.state.current_time
                == duration
            ):

                self.print_dashboard()

        print()

        self.decision_logger.print_summary()


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":

    simulator = Simulator()

    simulator.run(
        incident_ids=[
            1,
            2,
            3,
            4,
            5,
        ],
        duration=15,
    )