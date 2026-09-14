from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .database import connect, initialize_database


def seed_demo_data(path: Path | None = None, reset: bool = False) -> None:
    initialize_database(path)
    with connect(path) as connection:
        if reset:
            for table in (
                "capa_reports",
                "deviations",
                "assessments",
                "doses",
                "medications",
                "visits",
                "patients",
                "sites",
            ):
                connection.execute(f"DELETE FROM {table}")
        existing = connection.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        if existing:
            return

        sites = [
            ("SITE-001", "Northstar Research", "United States"),
            ("SITE-014", "Riverside Clinical Center", "United States"),
            ("SITE-027", "Harborview Medical", "Canada"),
        ]
        connection.executemany(
            "INSERT INTO sites(site_code, name, country) VALUES (?, ?, ?)", sites
        )
        site_ids = {
            row["site_code"]: row["id"]
            for row in connection.execute("SELECT id, site_code FROM sites")
        }
        patients = []
        for site_code, prefix in (("SITE-001", "N"), ("SITE-014", "R"), ("SITE-027", "H")):
            for index in range(1, 3):
                patients.append((f"{prefix}-{index:03d}", site_ids[site_code]))
        connection.executemany(
            "INSERT INTO patients(patient_code, site_id) VALUES (?, ?)", patients
        )

        base_date = date(2026, 1, 1)
        patient_rows = list(connection.execute("SELECT id, patient_code FROM patients"))
        for patient in patient_rows:
            for visit_number, scheduled_day in enumerate((0, 28, 56, 84), start=1):
                actual_day = scheduled_day
                entered_day = actual_day + 2
                if patient["patient_code"] == "R-001" and visit_number == 3:
                    actual_day = 72
                    entered_day = 82
                if patient["patient_code"] == "R-002" and visit_number == 2:
                    actual_day = None
                    entered_day = None
                occurred_at = (
                    (base_date + timedelta(days=actual_day)).isoformat()
                    if actual_day is not None
                    else None
                )
                entered_at = (
                    (base_date + timedelta(days=entered_day)).isoformat()
                    if entered_day is not None
                    else None
                )
                connection.execute(
                    """
                    INSERT INTO visits(patient_id, visit_number, scheduled_day, actual_day,
                                       occurred_at, entered_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (patient["id"], visit_number, scheduled_day, actual_day, occurred_at, entered_at),
                )

            visit_rows = list(
                connection.execute(
                    "SELECT id, visit_number, actual_day FROM visits WHERE patient_id = ?",
                    (patient["id"],),
                )
            )
            for visit in visit_rows:
                connection.execute(
                    "INSERT INTO doses(patient_id, visit_id, dose_mg, frequency, recorded_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        patient["id"],
                        visit["id"],
                        200 if patient["patient_code"] == "R-001" and visit["visit_number"] == 3 else 100,
                        "once_daily",
                        base_date.isoformat(),
                    ),
                )
                for assessment_type in ("safety_labs", "imaging_scan"):
                    completed = not (
                        patient["patient_code"] == "R-002"
                        and visit["visit_number"] == 4
                        and assessment_type == "imaging_scan"
                    )
                    connection.execute(
                        "INSERT INTO assessments(patient_id, visit_id, assessment_type, completed) VALUES (?, ?, ?, ?)",
                        (patient["id"], visit["id"], assessment_type, int(completed)),
                    )

        connection.execute(
            "INSERT INTO medications(patient_id, medication_name, started_day, ended_day, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (connection.execute("SELECT id FROM patients WHERE patient_code = 'R-001'").fetchone()[0], "warfarin", 56, 70, base_date.isoformat()),
        )