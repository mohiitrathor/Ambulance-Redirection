from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path
import json


# ==============================================================
# DECISION RECORD
# ==============================================================

@dataclass
class RedirectionDecision:

    incident_id: int
    time: int

    decision: str
    reason: str

    original_hospital: Optional[str]
    new_hospital: Optional[str]

    eta_before: Optional[float]
    eta_after: Optional[float]

    eta_saved: Optional[float]
    eta_improvement_percent: Optional[float]

    severity: Optional[str] = None
    ambulance_id: Optional[str] = None


# ==============================================================
# DECISION LOGGER
# ==============================================================

class DecisionLogger:

    def __init__(self):

        self.decisions = []

    # ----------------------------------------------------------
    # GENERIC LOG
    # ----------------------------------------------------------

    def log(
        self,
        incident_id,
        current_time,
        decision,
        reason,
        original_hospital=None,
        new_hospital=None,
        eta_before=None,
        eta_after=None,
        severity=None,
        ambulance_id=None,
    ):

        eta_saved = None
        improvement_percent = None

        if (
            eta_before is not None
            and eta_after is not None
        ):

            eta_before = float(
                eta_before
            )

            eta_after = float(
                eta_after
            )

            eta_saved = (
                eta_before
                - eta_after
            )

            improvement_percent = (
                eta_saved
                / max(eta_before, 1.0)
            ) * 100

        record = RedirectionDecision(

            incident_id=int(
                incident_id
            ),

            time=int(
                current_time
            ),

            decision=str(
                decision
            ),

            reason=str(
                reason
            ),

            original_hospital=(
                str(original_hospital)
                if original_hospital is not None
                else None
            ),

            new_hospital=(
                str(new_hospital)
                if new_hospital is not None
                else None
            ),

            eta_before=(
                round(
                    float(eta_before),
                    2,
                )
                if eta_before is not None
                else None
            ),

            eta_after=(
                round(
                    float(eta_after),
                    2,
                )
                if eta_after is not None
                else None
            ),

            eta_saved=(
                round(
                    float(eta_saved),
                    2,
                )
                if eta_saved is not None
                else None
            ),

            eta_improvement_percent=(
                round(
                    float(improvement_percent),
                    2,
                )
                if improvement_percent is not None
                else None
            ),

            severity=(
                str(severity)
                if severity is not None
                else None
            ),

            ambulance_id=(
                str(ambulance_id)
                if ambulance_id is not None
                else None
            ),
        )

        self.decisions.append(
            record
        )

        return record

    # ----------------------------------------------------------
    # REDIRECTION
    # ----------------------------------------------------------

    def log_redirection(
        self,
        incident_id,
        current_time,
        reason,
        original_hospital,
        new_hospital,
        eta_before=None,
        eta_after=None,
        severity=None,
        ambulance_id=None,
    ):

        return self.log(

            incident_id=incident_id,

            current_time=current_time,

            decision="REDIRECTED",

            reason=reason,

            original_hospital=(
                original_hospital
            ),

            new_hospital=(
                new_hospital
            ),

            eta_before=(
                eta_before
            ),

            eta_after=(
                eta_after
            ),

            severity=severity,

            ambulance_id=ambulance_id,
        )

    # ----------------------------------------------------------
    # NO REDIRECTION
    # ----------------------------------------------------------

    def log_no_redirection(
        self,
        incident_id,
        current_time,
        reason,
        hospital_id=None,
        eta=None,
        severity=None,
        ambulance_id=None,
    ):

        return self.log(

            incident_id=incident_id,

            current_time=current_time,

            decision="NO_REDIRECTION",

            reason=reason,

            original_hospital=(
                hospital_id
            ),

            new_hospital=None,

            eta_before=eta,

            eta_after=None,

            severity=severity,

            ambulance_id=ambulance_id,
        )

    # ----------------------------------------------------------
    # GET ALL DECISIONS
    # ----------------------------------------------------------

    def get_decisions(self):

        return list(
            self.decisions
        )

    # ----------------------------------------------------------
    # INCIDENT HISTORY
    # ----------------------------------------------------------

    def get_incident_history(
        self,
        incident_id,
    ):

        incident_id = int(
            incident_id
        )

        return [
            decision
            for decision in self.decisions
            if decision.incident_id
            == incident_id
        ]

    # ----------------------------------------------------------
    # REDIRECTION COUNT
    # ----------------------------------------------------------

    def total_redirections(self):

        return sum(
            decision.decision
            == "REDIRECTED"
            for decision
            in self.decisions
        )

    # ----------------------------------------------------------
    # TOTAL ETA SAVED
    # ----------------------------------------------------------

    def total_eta_saved(self):

        values = [

            decision.eta_saved

            for decision
            in self.decisions

            if (
                decision.decision
                == "REDIRECTED"

                and decision.eta_saved
                is not None
            )
        ]

        return round(
            sum(values),
            2,
        )

    # ----------------------------------------------------------
    # AVERAGE ETA SAVED
    # ----------------------------------------------------------

    def average_eta_saved(self):

        values = [

            decision.eta_saved

            for decision
            in self.decisions

            if (
                decision.decision
                == "REDIRECTED"

                and decision.eta_saved
                is not None
            )
        ]

        if not values:
            return 0.0

        return round(
            sum(values)
            / len(values),
            2,
        )

    # ----------------------------------------------------------
    # REDIRECTION RATE
    # ----------------------------------------------------------

    def redirection_rate(self):

        if not self.decisions:
            return 0.0

        return round(
            (
                self.total_redirections()
                / len(self.decisions)
            ) * 100,
            2,
        )

    # ----------------------------------------------------------
    # EXPORT JSON
    # ----------------------------------------------------------

    def export_json(
        self,
        filepath,
    ):

        filepath = Path(
            filepath
        )

        filepath.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = [

            asdict(decision)

            for decision
            in self.decisions
        ]

        with open(
            filepath,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=4,
            )

        return filepath

    # ----------------------------------------------------------
    # CLEAR
    # ----------------------------------------------------------

    def clear(self):

        self.decisions.clear()

    # ----------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------

    def print_summary(self):

        print()
        print("=" * 70)
        print(
            "REDIRECTION DECISION SUMMARY"
        )
        print("=" * 70)

        print(
            f"Total decisions:    "
            f"{len(self.decisions)}"
        )

        print(
            f"Redirections:       "
            f"{self.total_redirections()}"
        )

        print(
            f"Redirection rate:   "
            f"{self.redirection_rate():.1f}%"
        )

        print(
            f"Total ETA saved:    "
            f"{self.total_eta_saved():.1f} min"
        )

        print(
            f"Average ETA saved:  "
            f"{self.average_eta_saved():.1f} min"
        )

        print("-" * 70)

        if not self.decisions:

            print(
                "No decisions recorded."
            )

        for decision in self.decisions:

            print(
                f"Incident #{decision.incident_id} "
                f"| {decision.decision} "
                f"| {decision.reason}"
            )

            if decision.original_hospital:

                print(
                    f"  Hospital: "
                    f"{decision.original_hospital}"
                    f" -> "
                    f"{decision.new_hospital or '-'}"
                )

            if (
                decision.eta_before is not None
                and decision.eta_after is not None
            ):

                print(
                    f"  ETA: "
                    f"{decision.eta_before:.1f}"
                    f" -> "
                    f"{decision.eta_after:.1f} min "
                    f"("
                    f"{decision.eta_saved:.1f}"
                    f" min saved, "
                    f"{decision.eta_improvement_percent:.1f}%"
                    f")"
                )

            if decision.severity:

                print(
                    f"  Severity: "
                    f"{decision.severity}"
                )

            if decision.ambulance_id:

                print(
                    f"  Ambulance: "
                    f"{decision.ambulance_id}"
                )

        print("=" * 70)


# ==============================================================
# BASIC LOGGER TEST
# ==============================================================

if __name__ == "__main__":

    logger = DecisionLogger()

    logger.log_redirection(

        incident_id=1,

        current_time=5,

        reason=(
            "Hospital became full."
        ),

        original_hospital=(
            "HOSP_182"
        ),

        new_hospital=(
            "HOSP_099"
        ),

        eta_before=29.5,

        eta_after=24.0,

        severity="Emergency",

        ambulance_id="AMB_0575",
    )

    logger.log_redirection(

        incident_id=2,

        current_time=10,

        reason=(
            "ETA deterioration caused "
            "by severe traffic."
        ),

        original_hospital=(
            "HOSP_279"
        ),

        new_hospital=(
            "HOSP_031"
        ),

        eta_before=40.0,

        eta_after=27.0,

        severity="Critical",

        ambulance_id="AMB_0690",
    )

    logger.log_no_redirection(

        incident_id=3,

        current_time=12,

        reason=(
            "Current hospital remains suitable."
        ),

        hospital_id="HOSP_031",

        eta=5.0,

        severity="Moderate",

        ambulance_id="AMB_0359",
    )

    logger.print_summary()