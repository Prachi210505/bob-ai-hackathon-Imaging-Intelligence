from __future__ import annotations

import sqlite3
import json
from pathlib import Path

from .config import database_path


SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_filename TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    risk_score REAL NOT NULL DEFAULT 0,
    risk_level TEXT NOT NULL DEFAULT 'Low'
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_code TEXT NOT NULL UNIQUE,
    site_id INTEGER NOT NULL REFERENCES sites(id),
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS deviations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id),
    patient_id INTEGER REFERENCES patients(id),
    deviation_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'protocol',
    status TEXT NOT NULL DEFAULT 'open',
    description TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    visit_number INTEGER NOT NULL,
    scheduled_day INTEGER NOT NULL,
    actual_day INTEGER,
    occurred_at TEXT,
    entered_at TEXT,
    UNIQUE(patient_id, visit_number)
);

CREATE TABLE IF NOT EXISTS doses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    visit_id INTEGER REFERENCES visits(id),
    dose_mg REAL NOT NULL,
    frequency TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    medication_name TEXT NOT NULL,
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    visit_id INTEGER NOT NULL REFERENCES visits(id),
    assessment_type TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS capa_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deviation_id INTEGER NOT NULL REFERENCES deviations(id),
    corrective_action TEXT NOT NULL,
    preventive_action TEXT NOT NULL,
    owner TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS protocol_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path | None = None) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(deviations)")
        }
        if "category" not in columns:
            connection.execute(
                "ALTER TABLE deviations ADD COLUMN category TEXT NOT NULL DEFAULT 'protocol'"
            )
        if "evidence_json" not in columns:
            connection.execute(
                "ALTER TABLE deviations ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}'"
            )
        for table in ("sites", "patients", "visits", "doses", "medications", "assessments", "deviations", "capa_reports"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if "dataset_id" not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN dataset_id INTEGER REFERENCES datasets(id)")
        capa_columns = {row[1] for row in connection.execute("PRAGMA table_info(capa_reports)")}
        for column in ("root_cause", "impact_assessment", "verification_plan"):
            if column not in capa_columns:
                connection.execute(f"ALTER TABLE capa_reports ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        legacy_rows = connection.execute(
            "SELECT COUNT(*) FROM sites WHERE dataset_id IS NULL"
        ).fetchone()[0]
        if legacy_rows:
            legacy = connection.execute(
                "SELECT id FROM datasets WHERE name = 'Legacy workspace' ORDER BY id LIMIT 1"
            ).fetchone()
            legacy_id = legacy[0] if legacy else connection.execute(
                "INSERT INTO datasets(name, source_filename) VALUES ('Legacy workspace', 'pre-dataset migration')"
            ).lastrowid
            for table in ("sites", "patients", "visits", "doses", "medications", "assessments", "deviations", "capa_reports"):
                connection.execute(f"UPDATE {table} SET dataset_id = ? WHERE dataset_id IS NULL", (legacy_id,))


def get_protocol(path: Path | None = None):
    from .protocol import Protocol, TRIAL_PROTOCOL

    with connect(path) as connection:
        row = connection.execute("SELECT payload_json FROM protocol_config WHERE id = 1").fetchone()
    return Protocol.from_dict(json.loads(row["payload_json"])) if row else TRIAL_PROTOCOL


def save_protocol(protocol, path: Path | None = None) -> None:
    with connect(path) as connection:
        connection.execute(
            "INSERT INTO protocol_config(id, payload_json) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json, updated_at = CURRENT_TIMESTAMP",
            (json.dumps(protocol.as_dict()),),
        )


def summary(path: Path | None = None) -> dict[str, int]:
    with connect(path) as connection:
        site_count = connection.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        patient_count = connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        deviation_count = connection.execute("SELECT COUNT(*) FROM deviations").fetchone()[0]
        open_deviation_count = connection.execute(
            "SELECT COUNT(*) FROM deviations WHERE status = 'open'"
        ).fetchone()[0]
        capa_count = connection.execute("SELECT COUNT(*) FROM capa_reports").fetchone()[0]
        dataset_count = connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
    return {
        "sites": site_count,
        "patients": patient_count,
        "deviations": deviation_count,
        "open_deviations": open_deviation_count,
        "capa_reports": capa_count,
        "datasets": dataset_count,
    }


def datasets(path: Path | None = None) -> list[dict[str, object]]:
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.name, d.source_filename, d.imported_at,
                   COUNT(DISTINCT s.id) AS sites,
                   COUNT(DISTINCT p.id) AS patients,
                   COUNT(DISTINCT dv.id) AS deviations
            FROM datasets d
            LEFT JOIN sites s ON s.dataset_id = d.id
            LEFT JOIN patients p ON p.dataset_id = d.id
            LEFT JOIN deviations dv ON dv.dataset_id = d.id
            GROUP BY d.id
            ORDER BY d.imported_at DESC, d.id DESC
            """
        )
        return [dict(row) for row in rows]