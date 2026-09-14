from __future__ import annotations

from contextlib import asynccontextmanager
import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import app_host, app_port, seed_demo_data_enabled
from .analysis import analyze_trial
from .database import connect, datasets, get_protocol, initialize_database, save_protocol, summary
from .seed import seed_demo_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    if seed_demo_data_enabled():
        seed_demo_data()
        analyze_trial()
    yield


app = FastAPI(
    title="TrialGuard API",
    description="Local-first clinical trial risk monitoring backend.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "trialguard-api"}


@app.get("/api/summary")
def trial_summary() -> dict[str, int]:
    return summary()


class TrialImport(BaseModel):
    dataset_name: str = "Imported trial dataset"
    source_filename: str | None = None
    protocol: dict[str, object] | None = None
    sites: list[dict[str, object]] = Field(default_factory=list)
    patients: list[dict[str, object]] = Field(default_factory=list)
    visits: list[dict[str, object]] = Field(default_factory=list)
    doses: list[dict[str, object]] = Field(default_factory=list)
    medications: list[dict[str, object]] = Field(default_factory=list)
    assessments: list[dict[str, object]] = Field(default_factory=list)


class CapaRequest(BaseModel):
    deviation_id: int
    owner: str = "Clinical Operations"
    due_date: str | None = None


class DeviationStatusRequest(BaseModel):
    status: str


@app.post("/api/import")
def import_trial_data(payload: TrialImport) -> dict[str, int]:
    if not payload.sites or not payload.patients:
        raise HTTPException(status_code=422, detail="Import requires sites and patients.")
    with connect() as connection:
        try:
            dataset_cursor = connection.execute(
                "INSERT INTO datasets(name, source_filename) VALUES (?, ?)",
                (payload.dataset_name.strip() or "Imported trial dataset", payload.source_filename),
            )
            dataset_id = dataset_cursor.lastrowid
            for site in payload.sites:
                connection.execute(
                    "INSERT INTO sites(site_code, name, country, dataset_id) VALUES (?, ?, ?, ?)",
                    (site["site_code"], site["name"], site.get("country", "Unknown"), dataset_id),
                )
            site_ids = {row["site_code"]: row["id"] for row in connection.execute("SELECT id, site_code FROM sites WHERE dataset_id = ?", (dataset_id,))}
            for patient in payload.patients:
                connection.execute(
                    "INSERT INTO patients(patient_code, site_id, status, dataset_id) VALUES (?, ?, ?, ?)",
                    (patient["patient_code"], site_ids[patient["site_code"]], patient.get("status", "active"), dataset_id),
                )
            patient_ids = {row["patient_code"]: row["id"] for row in connection.execute("SELECT id, patient_code FROM patients WHERE dataset_id = ?", (dataset_id,))}
            for visit in payload.visits:
                connection.execute(
                    "INSERT INTO visits(patient_id, visit_number, scheduled_day, actual_day, occurred_at, entered_at, dataset_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (patient_ids[visit["patient_code"]], visit["visit_number"], visit["scheduled_day"], visit.get("actual_day"), visit.get("occurred_at"), visit.get("entered_at"), dataset_id),
                )
            visit_ids = {(row["patient_id"], row["visit_number"]): row["id"] for row in connection.execute("SELECT id, patient_id, visit_number FROM visits WHERE dataset_id = ?", (dataset_id,))}
            for dose in payload.doses:
                connection.execute(
                    "INSERT INTO doses(patient_id, visit_id, dose_mg, frequency, recorded_at, dataset_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (patient_ids[dose["patient_code"]], visit_ids.get((patient_ids[dose["patient_code"]], dose["visit_number"])), dose["dose_mg"], dose["frequency"], dose["recorded_at"], dataset_id),
                )
            for medication in payload.medications:
                connection.execute(
                    "INSERT INTO medications(patient_id, medication_name, started_day, ended_day, recorded_at, dataset_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (patient_ids[medication["patient_code"]], medication["medication_name"], medication["started_day"], medication.get("ended_day"), medication["recorded_at"], dataset_id),
                )
            for assessment in payload.assessments:
                connection.execute(
                    "INSERT INTO assessments(patient_id, visit_id, assessment_type, completed, dataset_id) VALUES (?, ?, ?, ?, ?)",
                    (patient_ids[assessment["patient_code"]], visit_ids[(patient_ids[assessment["patient_code"]], assessment["visit_number"])], assessment["assessment_type"], int(assessment.get("completed", False)), dataset_id),
                )
        except sqlite3.IntegrityError as error:
            detail = str(error)
            if "sites.site_code" in detail:
                message = "A site code in this dataset is already loaded. Delete the existing dataset or use unique site codes."
            elif "patients.patient_code" in detail:
                message = "A patient code in this dataset is already loaded. Delete the existing dataset or use unique patient codes."
            else:
                message = f"Import conflicts with existing records: {detail}"
            raise HTTPException(status_code=422, detail=message) from error
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=f"Invalid import record: {error}") from error
    if payload.protocol is not None:
        from .protocol import Protocol

        try:
            save_protocol(Protocol.from_dict(payload.protocol))
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise HTTPException(status_code=422, detail=f"Invalid protocol: {error}") from error
    result = analyze_trial()
    result["dataset_id"] = dataset_id
    return result


@app.get("/api/datasets")
def list_datasets() -> list[dict[str, object]]:
    return datasets()


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: int) -> dict[str, int]:
    with connect() as connection:
        if connection.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        connection.execute(
            "DELETE FROM capa_reports WHERE deviation_id IN (SELECT id FROM deviations WHERE dataset_id = ?)",
            (dataset_id,),
        )
        connection.execute("DELETE FROM capa_reports WHERE dataset_id = ?", (dataset_id,))
        for table in ("deviations", "assessments", "doses", "medications", "visits", "patients", "sites"):
            connection.execute(f"DELETE FROM {table} WHERE dataset_id = ?", (dataset_id,))
        connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    return analyze_trial()


@app.post("/api/analyze")
def analyze() -> dict[str, int]:
    return analyze_trial()


@app.get("/api/protocol")
def protocol() -> dict[str, object]:
    return get_protocol().as_dict()


@app.put("/api/protocol")
def update_protocol(payload: dict[str, object]) -> dict[str, object]:
    from .protocol import Protocol

    try:
        configured_protocol = Protocol.from_dict(payload)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise HTTPException(status_code=422, detail=f"Invalid protocol: {error}") from error
    save_protocol(configured_protocol)
    analyze_trial(protocol=configured_protocol)
    return configured_protocol.as_dict()


@app.get("/api/sites")
def sites() -> list[dict[str, object]]:
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT s.*, d.name AS dataset_name, d.source_filename,
                       COUNT(DISTINCT dv.id) AS deviation_count
                FROM sites s
                LEFT JOIN datasets d ON d.id = s.dataset_id
                LEFT JOIN deviations dv ON dv.site_id = s.id
                GROUP BY s.id
                ORDER BY s.risk_score DESC, s.site_code
                """
            )
        ]


@app.get("/api/deviations")
def deviations(severity: str | None = None) -> list[dict[str, object]]:
    with connect() as connection:
        query = "SELECT d.*, s.site_code, p.patient_code FROM deviations d JOIN sites s ON s.id = d.site_id LEFT JOIN patients p ON p.id = d.patient_id"
        params: tuple[str, ...] = ()
        if severity:
            query += " WHERE d.severity = ?"
            params = (severity.lower(),)
        query += " ORDER BY CASE d.severity WHEN 'major' THEN 1 WHEN 'minor' THEN 2 ELSE 3 END, d.id"
        rows = []
        for row in connection.execute(query, params):
            item = dict(row)
            item["evidence"] = __import__("json").loads(item.pop("evidence_json"))
            rows.append(item)
        return rows


@app.patch("/api/deviations/{deviation_id}/status")
def update_deviation_status(deviation_id: int, request: DeviationStatusRequest) -> dict[str, object]:
    allowed = {"open", "under_investigation", "capa_required", "resolved", "closed"}
    if request.status not in allowed:
        raise HTTPException(status_code=422, detail=f"Status must be one of: {', '.join(sorted(allowed))}.")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE deviations SET status = ? WHERE id = ?",
            (request.status, deviation_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Deviation not found.")
        row = connection.execute("SELECT * FROM deviations WHERE id = ?", (deviation_id,)).fetchone()
    item = dict(row)
    item["evidence"] = json.loads(item.pop("evidence_json"))
    return item


@app.get("/api/investigation/{site_code}")
def investigation_brief(site_code: str, variant: int = Query(0, ge=0)) -> dict[str, object]:
    with connect() as connection:
        site = connection.execute("SELECT * FROM sites WHERE site_code = ?", (site_code,)).fetchone()
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        rows = list(connection.execute(
            "SELECT deviation_type, severity, description, evidence_json FROM deviations WHERE site_id = ? ORDER BY id",
            (site["id"],),
        ))
    finding_types = {row["deviation_type"] for row in rows}
    questions = []
    question_variants = {
        "missed_visit": [
            "What caused the missed visit, and has the investigator assessed subject-safety impact?",
            "Which operational failure led to the missed visit, and what subject impact assessment is documented?",
        ],
        "visit_window": [
            "Why did the visit fall outside the protocol window, and is this a recurring site process failure?",
            "What caused the out-of-window visit, and what control will prevent another timing breach?",
        ],
        "incorrect_dose": [
            "Was the incorrect dose administered, and what medical review is required for the affected subject?",
            "How did the dose mismatch occur, and has the medical monitor assessed treatment and endpoint impact?",
        ],
        "prohibited_medication": [
            "When was the prohibited medication identified, and has endpoint impact been assessed by the medical monitor?",
            "What reconciliation gap allowed the prohibited medication, and what subject-impact review is complete?",
        ],
        "missing_assessment": [
            "Can the missing assessment be completed, and how will the resulting data gap be documented?",
            "Why was the required assessment incomplete, and what evidence will support the final data decision?",
        ],
        "late_data_entry": [
            "What caused the data-entry delay, and what site control will prevent another late submission?",
            "Which workflow step delayed the record, and how will timeliness be monitored going forward?",
        ],
    }
    for finding_type in sorted(finding_types):
        if finding_type in question_variants:
            questions.append(question_variants[finding_type][variant % len(question_variants[finding_type])])
    if not questions:
        questions = [
            "What evidence confirms this site is following the active protocol consistently?",
            "Which leading indicator should the monitoring team review next for this site?",
        ]
    closure_questions = [
        "What evidence will verify that the corrective action is effective and ready for closure?",
        "What objective evidence should the monitor review before closing this action?",
    ]
    questions.append(closure_questions[variant % len(closure_questions)])
    return {
        "site": dict(site),
        "findings": [{**dict(row), "evidence": json.loads(row["evidence_json"])} for row in rows],
        "questions": questions,
    }


@app.post("/api/capa")
def create_capa(request: CapaRequest) -> dict[str, object]:
    actions = {
        "missed_visit": ("Review the subject record and assess impact with the investigator.", "Retrain site staff and add visit-window alerts."),
        "incorrect_dose": ("Complete medical review of the dosing event and affected subject.", "Add dose verification at dispensing and reconciliation."),
        "prohibited_medication": ("Escalate to the medical monitor and assess endpoint impact.", "Add medication reconciliation before each treatment visit."),
        "missing_assessment": ("Determine whether the assessment can be completed or data impact mitigated.", "Add required-assessment completion checks before visit closeout."),
        "late_data_entry": ("Review source records and correct the delayed entry where appropriate.", "Retrain staff on the data-entry deadline and monitor timeliness."),
        "visit_window": ("Assess protocol and subject impact for the out-of-window visit.", "Add automated visit-window reminders and escalation."),
    }
    with connect() as connection:
        deviation = connection.execute(
            "SELECT d.*, s.site_code, s.name AS site_name, p.patient_code, ds.name AS dataset_name FROM deviations d JOIN sites s ON s.id = d.site_id LEFT JOIN patients p ON p.id = d.patient_id LEFT JOIN datasets ds ON ds.id = d.dataset_id WHERE d.id = ?",
            (request.deviation_id,),
        ).fetchone()
        if deviation is None:
            raise HTTPException(status_code=404, detail="Deviation not found.")
        corrective, preventive = actions.get(deviation["deviation_type"], ("Investigate the deviation and document impact.", "Update the site process and verify effectiveness."))
        root_causes = {
            "missed_visit": "Potential site scheduling or subject follow-up control failure.",
            "visit_window": "Potential visit scheduling, reminder, or escalation control failure.",
            "incorrect_dose": "Potential dispensing, administration, or dose-reconciliation control failure.",
            "prohibited_medication": "Potential medication-reconciliation or eligibility-review control failure.",
            "missing_assessment": "Potential visit closeout or required-assessment completion control failure.",
            "late_data_entry": "Potential site data-entry workflow or workload control failure.",
        }
        impact = f"Assess subject-safety impact and data-integrity impact for the {deviation['severity']} {deviation['deviation_type'].replace('_', ' ')} finding. Confirm whether other subjects or endpoints may be affected."
        verification = "Review the next monitoring cycle, confirm retraining or control evidence, and verify no repeat deviation for the defined observation period."
        cursor = connection.execute(
            "INSERT INTO capa_reports(deviation_id, corrective_action, preventive_action, root_cause, impact_assessment, verification_plan, owner, due_date, dataset_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request.deviation_id, corrective, preventive, root_causes.get(deviation["deviation_type"], "Process cause requires investigation."), impact, verification, request.owner, request.due_date, deviation["dataset_id"]),
        )
        connection.execute(
            "UPDATE deviations SET status = 'capa_required' WHERE id = ?",
            (request.deviation_id,),
        )
        report = _capa_report(connection, cursor.lastrowid)
    return report


def _capa_report(connection, report_id: int) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT c.*, d.deviation_type, d.severity, d.description, d.evidence_json,
               s.site_code, s.name AS site_name, p.patient_code, ds.name AS dataset_name
        FROM capa_reports c
        JOIN deviations d ON d.id = c.deviation_id
        JOIN sites s ON s.id = d.site_id
        LEFT JOIN patients p ON p.id = d.patient_id
        LEFT JOIN datasets ds ON ds.id = c.dataset_id
        WHERE c.id = ?
        """, (report_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="CAPA report not found.")
    report = dict(row)
    report["evidence"] = json.loads(report.pop("evidence_json"))
    return report


def _capa_markdown(report: dict[str, object]) -> str:
    return f"""# CAPA Report CAPA-{report['id']}

## Report Control

- Status: {report['status']}
- Owner: {report.get('owner') or 'Unassigned'}
- Due date: {report.get('due_date') or 'Not assigned'}
- Dataset: {report.get('dataset_name') or 'Unknown'}
- Generated: {report['created_at']}

## Deviation Summary

- Site: {report['site_code']} ({report['site_name']})
- Patient: {report.get('patient_code') or 'Site-level'}
- Type: {report['deviation_type'].replace('_', ' ')}
- Severity: {report['severity']}
- Description: {report['description']}

## Evidence

```json
{json.dumps(report['evidence'], indent=2)}
```

## Impact Assessment

{report['impact_assessment']}

## Root-Cause Hypothesis

{report['root_cause']}

## Corrective Action

{report['corrective_action']}

## Preventive Action

{report['preventive_action']}

## Effectiveness Verification

{report['verification_plan']}

> Draft for qualified clinical operations review. This report does not replace medical or regulatory judgment.
"""


@app.get("/api/capa")
def capa_reports() -> list[dict[str, object]]:
    with connect() as connection:
        ids = [row[0] for row in connection.execute("SELECT id FROM capa_reports ORDER BY id DESC")]
        return [_capa_report(connection, report_id) for report_id in ids]


@app.get("/api/capa/{report_id}")
def capa_report(report_id: int) -> dict[str, object]:
    with connect() as connection:
        return _capa_report(connection, report_id)


@app.get("/api/capa/{report_id}/download", response_class=PlainTextResponse)
def download_capa(report_id: int) -> PlainTextResponse:
    with connect() as connection:
        report = _capa_report(connection, report_id)
    return PlainTextResponse(
        _capa_markdown(report),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=CAPA-{report_id}.md"},
    )


FRONTEND_DIRECTORY = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIRECTORY, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=app_host(), port=app_port(), reload=True)