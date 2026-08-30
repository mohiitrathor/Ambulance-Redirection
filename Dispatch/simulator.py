from pathlib import Path
import sys

import pandas as pd


# ==============================================================
# PATHS
# ==============================================================

ROOT = Path(__file__).resolve().parents[1]

DISPATCH_DIR = ROOT / "Dispatch"
DATASET_DIR = ROOT / "Dataset"

if str(DISPATCH_DIR) not in sys.path:
    sys.path.insert(0, str(DISPATCH_DIR))


# ==============================================================
# DISPATCH MODULES
# ==============================================================

from dispatch_engine import dispatch_incident
from redirection_engine import check_live_redirection
from events import EventEngine

from state import (
    DispatchState,
    IncidentState,
    AmbulanceState,
    HospitalState,
)

from decision_logger import DecisionLogger
from simulation_output import SimulationOutput


# ==============================================================
# SIMULATOR
# ==============================================================

class Simulator:

    ETA_CHANGE_THRESHOLD_PERCENT = 25.0
    ETA_CHANGE_THRESHOLD_MINUTES = 10.0

    MIN_REDIRECTION_IMPROVEMENT_MINUTES = 5.0
    MIN_REDIRECTION_IMPROVEMENT_PERCENT = 20.0

    def __init__(self):

        self.state = DispatchState()
        self.events = EventEngine()

        self.logger = DecisionLogger()
        self.output = SimulationOutput()

        # ------------------------------------------------------
        # DATASETS
        # ------------------------------------------------------

        self.patients = pd.read_csv(
            DATASET_DIR / "patient_incidents.csv"
        )

        self.ambulances = pd.read_csv(
            DATASET_DIR / "ambulances.csv"
        )

        self.hospitals = pd.read_csv(
            DATASET_DIR / "hospitals.csv"
        )

        # ------------------------------------------------------
        # RUNTIME TRACKING
        # ------------------------------------------------------

        self.redirect_history = {}
        self.last_known_eta = {}
        self.eta_recheck_required = set()

        # ------------------------------------------------------
        # INITIALIZE
        # ------------------------------------------------------

        self.load_state()
        self.register_event_handlers()

    # ==========================================================
    # STATE LOADING
    # ==========================================================

    def load_state(self):

        for _, row in self.ambulances.iterrows():

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
            )

            self.state.add_ambulance(
                ambulance
            )

        for _, row in self.hospitals.iterrows():

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

        self.events.schedule(
            time=5,
            event_type="HOSPITAL_FULL",
            data={
                "hospital_id": "HOSP_182"
            },
        )

        self.events.schedule(
            time=7,
            event_type="TRAFFIC_CHANGE",
            data={
                "ambulance_id": "AMB_0575",
                "level": "SEVERE",
            },
        )

        self.events.schedule(
            time=9,
            event_type="ICU_LOAD_CHANGE",
            data={
                "hospital_id": "HOSP_279",
                "increase": 10,
            },
        )

        self.events.schedule(
            time=11,
            event_type="HOSPITAL_LOAD_CHANGE",
            data={
                "hospital_id": "HOSP_099",
                "increase": 20,
            },
        )

    # ==========================================================
    # CREATE INCIDENT
    # ==========================================================

    def create_incident(
        self,
        incident_id,
    ):

        incident_id = int(
            incident_id
        )

        rows = self.patients[
            self.patients["Incident_ID"]
            == incident_id
        ]

        if rows.empty:
            raise ValueError(
                f"Incident {incident_id} not found."
            )

        row = rows.iloc[0]

        result = dispatch_incident(
            incident_id
        )

        patient_data = result.get(
            "patient",
            {},
        )

        ambulance_data = result.get(
            "ambulance"
        )

        hospital_data = result.get(
            "hospital"
        )

        severity = str(
            patient_data.get(
                "predicted_severity",
                "Unknown",
            )
        )

        priority_text = str(
            patient_data.get(
                "priority",
                "P5",
            )
        )

        try:

            priority = int(
                priority_text.replace(
                    "P",
                    "",
                )
            )

        except ValueError:

            priority = 5

        incident = IncidentState(
            incident_id=incident_id,

            condition=str(
                row["Condition"]
            ),

            severity=severity,

            priority=priority,

            status="DISPATCHED",
        )

        self.state.add_incident(
            incident
        )

        # ------------------------------------------------------
        # Ambulance
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

                ambulance.status = "EN_ROUTE"

                ambulance.incident_id = (
                    incident_id
                )

                ambulance.base_eta_minutes = (
                    float(
                        ambulance_data[
                            "eta_minutes"
                        ]
                    )
                )

                ambulance.traffic_level = str(
                    ambulance_data.get(
                        "traffic_level",
                        "NORMAL",
                    )
                ).upper()

                ambulance.road_condition = str(
                    ambulance_data.get(
                        "road_condition",
                        "GOOD",
                    )
                ).upper()

                ambulance.route_distance_km = (
                    ambulance_data.get(
                        "distance_km"
                    )
                )

                ambulance.recalculate_eta()

                incident.ambulance_id = (
                    ambulance_id
                )

                self.last_known_eta[
                    incident_id
                ] = ambulance.eta_minutes

        # ------------------------------------------------------
        # Hospital
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
        # Redirect history
        # ------------------------------------------------------

        self.redirect_history[
            incident_id
        ] = set()

        self.state.add_event(
            f"Incident {incident_id} dispatched."
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
            f"Hospital {hospital_id} became full."
        )

    # ==========================================================
    # HOSPITAL LOAD CHANGE
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
            hospital.current_load + increase,
        )

        self.state.add_event(
            f"Hospital {hospital_id} "
            f"load increased by {increase}."
        )

    # ==========================================================
    # ICU LOAD CHANGE
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
            hospital.current_icu_load + increase,
        )

        self.state.add_event(
            f"Hospital {hospital_id} "
            f"ICU load increased by {increase}."
        )

    # ==========================================================
    # TRAFFIC CHANGE
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

        if ambulance.status != "EN_ROUTE":

            self.state.add_event(
                f"Traffic event ignored for "
                f"{ambulance_id}; ambulance is "
                f"{ambulance.status}."
            )

            return

        old_eta = ambulance.eta_minutes

        ambulance.traffic_level = level

        ambulance.recalculate_eta()

        new_eta = ambulance.eta_minutes

        if old_eta is None or new_eta is None:
            return

        self.state.add_event(
            f"Traffic for ambulance "
            f"{ambulance_id} changed to "
            f"{level}. ETA changed from "
            f"{old_eta:.1f} to "
            f"{new_eta:.1f} min."
        )

        eta_increase = (
            new_eta - old_eta
        )

        if eta_increase <= 0:
            return

        percent_increase = (
            eta_increase
            / max(old_eta, 1)
        ) * 100

        if (
            percent_increase
            >= self.ETA_CHANGE_THRESHOLD_PERCENT
            or
            eta_increase
            >= self.ETA_CHANGE_THRESHOLD_MINUTES
        ):

            if ambulance.incident_id is not None:

                incident_id = int(
                    ambulance.incident_id
                )

                self.eta_recheck_required.add(
                    incident_id
                )

                self.state.add_event(
                    f"ETA deterioration detected "
                    f"for incident "
                    f"{incident_id}. "
                    f"Hospital destination will "
                    f"be re-evaluated."
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

        if incident_id in self.state.incidents:
            return

        self.create_incident(
            incident_id
        )

    # ==========================================================
    # AMBULANCE STATUS CHANGE
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
            f"Ambulance {ambulance_id} "
            f"status changed to {status}."
        )

    # ==========================================================
    # ADVANCE TIME
    # ==============================================================

    def advance_time(
        self,
        minutes=1,
    ):

        minutes = max(
            0,
            int(minutes),
        )

        self.state.advance_time(
            minutes
        )

        for ambulance in (
            self.state.ambulances.values()
        ):

            if ambulance.status != "EN_ROUTE":
                continue

            if ambulance.eta_minutes is None:
                continue

            ambulance.eta_minutes = max(
                0,
                ambulance.eta_minutes - minutes,
            )

            if ambulance.eta_minutes <= 0:

                ambulance.eta_minutes = 0

                ambulance.status = "ARRIVED"

                incident = (
                    self.state.incidents.get(
                        ambulance.incident_id
                    )
                )

                if incident:

                    incident.status = "ARRIVED"

                self.state.add_event(
                    f"Ambulance "
                    f"{ambulance.ambulance_id} "
                    f"arrived at "
                    f"{ambulance.hospital_id}."
                )

                continue

            if ambulance.incident_id is not None:

                self.last_known_eta[
                    ambulance.incident_id
                ] = ambulance.eta_minutes

    # ==========================================================
    # ETA RECHECK
    # ==========================================================

    def should_recheck_eta(
        self,
        incident,
    ):

        return (
            incident.incident_id
            in self.eta_recheck_required
        )

    # ==========================================================
    # CALCULATE ETA TO HOSPITAL
    # ==========================================================

    def calculate_hospital_eta(
        self,
        ambulance,
        hospital,
    ):

        try:

            return float(
                ambulance.estimate_eta_to_hospital(
                    hospital
                )
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ):

            try:

                return float(
                    ambulance.calculate_eta_to_hospital(
                        hospital
                    )
                )

            except (
                AttributeError,
                TypeError,
                ValueError,
            ):

                return None

    # ==========================================================
    # ETA-BASED REDIRECTION
    # ==========================================================

    def check_eta_redirection(
        self,
        incident,
    ):

        ambulance = (
            self.state.ambulances.get(
                incident.ambulance_id
            )
        )

        if ambulance is None:
            return False

        if ambulance.status != "EN_ROUTE":
            return False

        current_hospital = (
            self.state.hospitals.get(
                incident.hospital_id
            )
        )

        if current_hospital is None:
            return False

        current_eta = (
            ambulance.eta_minutes
        )

        if current_eta is None:
            return False

        candidates = []

        for hospital in (
            self.state.hospitals.values()
        ):

            if (
                hospital.hospital_id
                == current_hospital.hospital_id
            ):
                continue

            if hospital.available_beds <= 0:
                continue

            if (
                incident.severity == "Critical"
                and hospital.available_icu <= 0
            ):
                continue

            eta = self.calculate_hospital_eta(
                ambulance,
                hospital,
            )

            if eta is None:
                continue

            candidates.append(
                (
                    eta,
                    hospital,
                )
            )

        if not candidates:
            return False

        candidates.sort(
            key=lambda item: item[0]
        )

        best_eta, best_hospital = (
            candidates[0]
        )

        # ------------------------------------------------------
        # Never redirect to a slower hospital.
        # ------------------------------------------------------

        if best_eta >= current_eta:
            return False

        improvement = (
            current_eta - best_eta
        )

        improvement_percent = (
            improvement
            / max(current_eta, 1)
        ) * 100

        # ------------------------------------------------------
        # Require meaningful improvement.
        # ------------------------------------------------------

        if (
            improvement
            < self.MIN_REDIRECTION_IMPROVEMENT_MINUTES
            and
            improvement_percent
            < self.MIN_REDIRECTION_IMPROVEMENT_PERCENT
        ):
            return False

        old_hospital_id = str(
            incident.hospital_id
        )

        new_hospital_id = str(
            best_hospital.hospital_id
        )

        history = (
            self.redirect_history.setdefault(
                incident.incident_id,
                set(),
            )
        )

        if new_hospital_id in history:
            return False

        # ------------------------------------------------------
        # Record old destination.
        # ------------------------------------------------------

        history.add(
            old_hospital_id
        )

        # ------------------------------------------------------
        # Apply new destination.
        # ------------------------------------------------------

        incident.hospital_id = (
            new_hospital_id
        )

        incident.status = "REDIRECTED"

        ambulance.hospital_id = (
            new_hospital_id
        )

        ambulance.eta_minutes = (
            best_eta
        )

        # ------------------------------------------------------
        # Log.
        # ------------------------------------------------------

        self.logger.log_redirection(
            incident_id=incident.incident_id,

            current_time=self.state.current_time,

            reason=(
                "ETA deterioration caused by "
                f"{ambulance.traffic_level.lower()} "
                "traffic."
            ),

            original_hospital=(
                old_hospital_id
            ),

            new_hospital=(
                new_hospital_id
            ),

            eta_before=current_eta,

            eta_after=best_eta,

            severity=incident.severity,

            ambulance_id=ambulance.ambulance_id,
        )

        self.state.add_event(
            f"Incident "
            f"{incident.incident_id} "
            f"redirected from "
            f"{old_hospital_id} to "
            f"{new_hospital_id}. "
            f"ETA improved from "
            f"{current_eta:.1f} to "
            f"{best_eta:.1f} min."
        )

        return True

    # ==========================================================
    # HOSPITAL-FAILURE REDIRECTION
    # ==========================================================

    def check_hospital_redirection(
        self,
        incident,
    ):

        if incident.hospital_id is None:
            return False

        if incident.ambulance_id is None:
            return False

        ambulance = (
            self.state.ambulances.get(
                incident.ambulance_id
            )
        )

        if ambulance is None:
            return False

        if ambulance.status != "EN_ROUTE":
            return False

        current_hospital_id = str(
            incident.hospital_id
        )

        result = check_live_redirection(
            self.state,
            incident.incident_id,
        )

        if not isinstance(result, dict):
            return False

        if not result.get(
            "redirect",
            False,
        ):
            return False

        alternative = result.get(
            "alternative_hospital"
        )

        if not isinstance(
            alternative,
            dict,
        ):
            return False

        # ------------------------------------------------------
        # Accept both key styles.
        # ------------------------------------------------------

        new_hospital_id = (
            alternative.get(
                "Hospital_ID"
            )
        )

        if new_hospital_id is None:

            new_hospital_id = (
                alternative.get(
                    "hospital_id"
                )
            )

        if new_hospital_id is None:
            return False

        new_hospital_id = str(
            new_hospital_id
        )

        if (
            new_hospital_id
            == current_hospital_id
        ):
            return False

        history = (
            self.redirect_history.setdefault(
                incident.incident_id,
                set(),
            )
        )

        if new_hospital_id in history:
            return False

        new_hospital = (
            self.state.hospitals.get(
                new_hospital_id
            )
        )

        if new_hospital is None:
            return False

        # ------------------------------------------------------
        # Current remaining ETA.
        # ------------------------------------------------------

        eta_before = (
            ambulance.eta_minutes
        )

        # ------------------------------------------------------
        # Calculate ETA from CURRENT ambulance position.
        # ------------------------------------------------------

        eta_after = (
            self.calculate_hospital_eta(
                ambulance,
                new_hospital,
            )
        )

        if eta_after is None:

            # We can redirect because the hospital failed,
            # but we must not invent an ETA improvement.
            eta_after = eta_before

        # ------------------------------------------------------
        # Record old destination.
        # ------------------------------------------------------

        history.add(
            current_hospital_id
        )

        # ------------------------------------------------------
        # Apply redirection.
        # ------------------------------------------------------

        incident.hospital_id = (
            new_hospital_id
        )

        incident.status = "REDIRECTED"

        ambulance.hospital_id = (
            new_hospital_id
        )

        if eta_after is not None:

            ambulance.eta_minutes = (
                float(eta_after)
            )

        # ------------------------------------------------------
        # Reason.
        # ------------------------------------------------------

        reason = str(
            result.get(
                "reason",
                "Current hospital is no longer suitable.",
            )
        ).rstrip(".")

        # ------------------------------------------------------
        # Log decision.
        # ------------------------------------------------------

        self.logger.log_redirection(
            incident_id=incident.incident_id,

            current_time=self.state.current_time,

            reason=reason,

            original_hospital=(
                current_hospital_id
            ),

            new_hospital=(
                new_hospital_id
            ),

            eta_before=eta_before,

            eta_after=eta_after,

            severity=incident.severity,

            ambulance_id=ambulance.ambulance_id,
        )

        if (
            eta_before is not None
            and eta_after is not None
        ):

            eta_change = (
                float(eta_before)
                - float(eta_after)
            )

            if eta_change > 0:

                eta_message = (
                    f" ETA improved from "
                    f"{eta_before:.1f} to "
                    f"{eta_after:.1f} min."
                )

            elif eta_change < 0:

                eta_message = (
                    f" ETA changed from "
                    f"{eta_before:.1f} to "
                    f"{eta_after:.1f} min."
                )

            else:

                eta_message = (
                    f" ETA remains "
                    f"{eta_after:.1f} min."
                )

        else:

            eta_message = ""

        self.state.add_event(
            f"Incident "
            f"{incident.incident_id} "
            f"redirected from "
            f"{current_hospital_id} to "
            f"{new_hospital_id}. "
            f"Reason: {reason}."
            f"{eta_message}"
        )

        return True

    # ==========================================================
    # REDIRECTION PIPELINE
    # ==========================================================

    def check_redirections(self):

        for incident in list(
            self.state.get_active_incidents()
        ):

            if incident.hospital_id is None:
                continue

            if incident.ambulance_id is None:
                continue

            ambulance = (
                self.state.ambulances.get(
                    incident.ambulance_id
                )
            )

            if ambulance is None:
                continue

            if ambulance.status != "EN_ROUTE":
                continue

            # --------------------------------------------------
            # ETA deterioration gets priority.
            # --------------------------------------------------

            if self.should_recheck_eta(
                incident
            ):

                redirected = (
                    self.check_eta_redirection(
                        incident
                    )
                )

                self.eta_recheck_required.discard(
                    incident.incident_id
                )

                if redirected:
                    continue

            # --------------------------------------------------
            # Hospital failure/capacity.
            # --------------------------------------------------

            self.check_hospital_redirection(
                incident
            )

    # ==========================================================
    # PROCESS EVENTS
    # ==========================================================

    def process_events(self):

        return self.events.process(
            self.state.current_time
        )

    # ==========================================================
    # OUTPUT
    # ==========================================================

    def get_snapshot(self):

        return self.output.snapshot(
            self.state
        )

    def get_dashboard_snapshot(self):

        return self.output.dashboard_snapshot(
            self.state
        )

    def get_json(self):

        return self.output.to_json(
            self.state
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

        # ------------------------------------------------------
        # ACTIVE INCIDENTS
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # FLEET
        # ------------------------------------------------------

        print()
        print("FLEET")
        print("-" * 70)

        counts = {}

        for ambulance in (
            self.state.ambulances.values()
        ):

            status = str(
                ambulance.status
            ).upper()

            counts[status] = (
                counts.get(status, 0) + 1
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
            f"Busy:             "
            f"{counts.get('BUSY', 0)}"
        )

        print(
            f"Maintenance:      "
            f"{counts.get('MAINTENANCE', 0)}"
        )

        print(
            f"Arrived:          "
            f"{counts.get('ARRIVED', 0)}"
        )

        # ------------------------------------------------------
        # CURRENT INCIDENTS
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # EVENTS
        # ------------------------------------------------------

        print()
        print("LATEST EVENTS")
        print("-" * 70)

        for event in self.state.events[-8:]:

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

        # ------------------------------------------------------
        # Initial dispatch
        # ------------------------------------------------------

        for incident_id in incident_ids:

            try:

                self.create_incident(
                    incident_id
                )

            except Exception as error:

                self.state.add_event(
                    f"Failed to dispatch "
                    f"incident {incident_id}: "
                    f"{error}"
                )

        # ------------------------------------------------------
        # Schedule events
        # ------------------------------------------------------

        self.schedule_default_events()

        # ------------------------------------------------------
        # Initial dashboard
        # ------------------------------------------------------

        self.print_dashboard()

        # ------------------------------------------------------
        # Simulation
        # ------------------------------------------------------

        for _ in range(
            duration
        ):

            self.advance_time(
                1
            )

            self.process_events()

            self.check_redirections()

            if (
                self.state.current_time % 5 == 0
                or
                self.state.current_time == duration
            ):

                self.print_dashboard()

        # ------------------------------------------------------
        # Decision summary
        # ------------------------------------------------------

        self.logger.print_summary()

        return self.get_snapshot()


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