from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .database import connect, get_protocol, initialize_database
from .protocol import Protocol, TRIAL_PROTOCOL


SEVERITY_WEIGHTS = {"major": 20, "minor": 8, "administrative": 3}


def analyze_trial(path: Path | None = None, protocol: Protocol | None = None) -> dict[str, int]:
    protocol = protocol or get_protocol(path)
    initialize_database(path)
    with connect(path) as connection:
        connection.execute(
            "DELETE FROM deviations WHERE id NOT IN (SELECT deviation_id FROM capa_reports)"
        )
        _detect_visit_deviations(connection, protocol)
        _detect_dose_deviations(connection, protocol)
        _detect_medication_deviations(connection, protocol)
        _detect_assessment_deviations(connection, protocol)
        _score_sites(connection)
        total = connection.execute("SELECT COUNT(*) FROM deviations").fetchone()[0]
        major = connection.execute("SELECT COUNT(*) FROM deviations WHERE severity = 'major'").fetchone()[0]
        minor = connection.execute("SELECT COUNT(*) FROM deviations WHERE severity = 'minor'").fetchone()[0]
        administrative = connection.execute(
            "SELECT COUNT(*) FROM deviations WHERE severity = 'administrative'"
        ).fetchone()[0]
    return {"total": total, "major": major, "minor": minor, "administrative": administrative}


def _insert(connection, site_id: int, patient_id: int | None, deviation_type: str, severity: str, description: str, evidence: dict, category: str = "protocol") -> None:
    dataset_id = connection.execute("SELECT dataset_id FROM sites WHERE id = ?", (site_id,)).fetchone()[0]
    normalized_evidence = json.loads(json.dumps(evidence))
    existing = connection.execute(
        "SELECT evidence_json FROM deviations WHERE site_id = ? AND patient_id IS ? AND deviation_type = ?",
        (site_id, patient_id, deviation_type),
    )
    if any(json.loads(row["evidence_json"]) == normalized_evidence for row in existing):
        return
    connection.execute(
        """
        INSERT INTO deviations(site_id, patient_id, deviation_type, severity, category, description, evidence_json, dataset_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (site_id, patient_id, deviation_type, severity, category, description, json.dumps(evidence), dataset_id),
    )


def _detect_visit_deviations(connection, protocol: Protocol) -> None:
    patients = connection.execute("SELECT id, patient_code, site_id, dataset_id FROM patients")
    for patient in patients:
        visits = {
            row["visit_number"]: row
            for row in connection.execute(
                "SELECT * FROM visits WHERE patient_id = ? AND (dataset_id = ? OR dataset_id IS NULL)", (patient["id"], patient["dataset_id"])
            )
        }
        for visit_number, window in protocol.visit_windows.items():
            row = visits.get(visit_number)
            if row is None:
                _insert(
                    connection,
                    patient["site_id"],
                    patient["id"],
                    "missed_visit",
                    "major",
                    "Required visit was not recorded.",
                    {
                        "patient": patient["patient_code"],
                        "visit": visit_number,
                        "allowed_window": window,
                    },
                )
                continue
            _check_visit(connection, patient, row, window, protocol)

        for row in visits.values():
            if row["visit_number"] not in protocol.visit_windows:
                _insert(
                    connection,
                    patient["site_id"],
                    patient["id"],
                    "unexpected_visit",
                    "administrative",
                    "A visit number was recorded that is not defined by the protocol.",
                    {"patient": patient["patient_code"], "visit": row["visit_number"]},
                    "data_integrity",
                )


def _check_visit(connection, patient, row, window, protocol: Protocol) -> None:
    if row["actual_day"] is None:
        _insert(
            connection,
            patient["site_id"],
            patient["id"],
            "missed_visit",
            "major",
            "Required visit was not recorded.",
            {"patient": patient["patient_code"], "visit": row["visit_number"], "allowed_window": window},
        )
    elif not window[0] <= row["actual_day"] <= window[1]:
        _insert(
            connection,
            patient["site_id"],
            patient["id"],
            "visit_window",
            "major",
            "Visit occurred outside the protocol window.",
            {"patient": patient["patient_code"], "visit": row["visit_number"], "actual_day": row["actual_day"], "allowed_window": window},
        )
    if row["actual_day"] is not None and row["entered_at"] and row["occurred_at"]:
        from datetime import date

        delay = (date.fromisoformat(row["entered_at"]) - date.fromisoformat(row["occurred_at"])).days
        if delay > protocol.data_entry_deadline_days:
            _insert(
                connection,
                patient["site_id"],
                patient["id"],
                "late_data_entry",
                "administrative",
                "Visit data was entered after the protocol deadline.",
                {"patient": patient["patient_code"], "delay_days": delay, "deadline_days": protocol.data_entry_deadline_days},
                "data_integrity",
            )


def _detect_dose_deviations(connection, protocol: Protocol) -> None:
    rows = connection.execute("SELECT d.*, p.patient_code, p.site_id FROM doses d JOIN patients p ON p.id = d.patient_id")
    for row in rows:
        if row["dose_mg"] != protocol.dose_mg or row["frequency"] != protocol.dose_frequency:
            _insert(connection, row["site_id"], row["patient_id"], "incorrect_dose", "major", "Recorded dose does not match the protocol.", {"patient": row["patient_code"], "observed": {"dose_mg": row["dose_mg"], "frequency": row["frequency"]}, "expected": {"dose_mg": protocol.dose_mg, "frequency": protocol.dose_frequency}})


def _detect_medication_deviations(connection, protocol: Protocol) -> None:
    rows = connection.execute("SELECT m.*, p.patient_code, p.site_id FROM medications m JOIN patients p ON p.id = m.patient_id")
    banned = {name.lower() for name in protocol.prohibited_medications}
    for row in rows:
        if row["medication_name"].lower() in banned:
            _insert(connection, row["site_id"], row["patient_id"], "prohibited_medication", "major", "A prohibited concomitant medication was recorded.", {"patient": row["patient_code"], "medication": row["medication_name"], "prohibited_list": sorted(banned)})


def _detect_assessment_deviations(connection, protocol: Protocol) -> None:
    rows = connection.execute(
        """
        SELECT a.*, p.patient_code, p.site_id, v.visit_number
        FROM assessments a JOIN patients p ON p.id = a.patient_id JOIN visits v ON v.id = a.visit_id
        WHERE a.completed = 0
        """
    )
    required = set(protocol.required_assessments)
    for row in rows:
        if row["assessment_type"] in required:
            _insert(connection, row["site_id"], row["patient_id"], "missing_assessment", "minor", "A required assessment was not completed.", {"patient": row["patient_code"], "visit": row["visit_number"], "assessment": row["assessment_type"]})


def _score_sites(connection) -> None:
    rows = connection.execute("SELECT site_id, severity FROM deviations")
    scores = Counter()
    for row in rows:
        scores[row["site_id"]] += SEVERITY_WEIGHTS[row["severity"]]
    for site in connection.execute("SELECT id FROM sites"):
        score = min(100, scores[site["id"]])
        level = "Critical" if score >= 75 else "High" if score >= 50 else "Moderate" if score >= 25 else "Low"
        connection.execute("UPDATE sites SET risk_score = ?, risk_level = ? WHERE id = ?", (score, level, site["id"]))