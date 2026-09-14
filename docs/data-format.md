# Trial Data Import Format

`POST /api/import` accepts one JSON object containing the source records below. Each import is stored as a separate named dataset and added to the active workspace; it does not replace existing datasets. IDs are not required; relationships use stable codes. Dates use ISO `YYYY-MM-DD` format and day values are relative to the trial baseline.

```json
{
  "dataset_name": "North America cohort",
  "source_filename": "north-america.json",
  "sites": [
    {"site_code": "SITE-001", "name": "Northstar Research", "country": "United States"}
  ],
  "patients": [
    {"patient_code": "P-001", "site_code": "SITE-001", "status": "active"}
  ],
  "visits": [
    {
      "patient_code": "P-001",
      "visit_number": 1,
      "scheduled_day": 0,
      "actual_day": 1,
      "occurred_at": "2026-01-02",
      "entered_at": "2026-01-04"
    }
  ],
  "doses": [
    {
      "patient_code": "P-001",
      "visit_number": 1,
      "dose_mg": 100,
      "frequency": "once_daily",
      "recorded_at": "2026-01-02"
    }
  ],
  "medications": [
    {
      "patient_code": "P-001",
      "medication_name": "warfarin",
      "started_day": 20,
      "ended_day": 30,
      "recorded_at": "2026-01-21"
    }
  ],
  "assessments": [
    {
      "patient_code": "P-001",
      "visit_number": 1,
      "assessment_type": "safety_labs",
      "completed": true
    }
  ]
}
```

The dashboard lists every imported dataset under **Loaded datasets**. Deleting a
dataset removes only its source records, deviations, and CAPA records, then
recalculates the aggregate trial view.

## Required Relationships

- Every patient must reference a site in the same payload or existing local database.
- Every visit must reference a patient.
- Dose and assessment records must reference an existing patient and visit number.
- `sites` and `patients` are required for an import.
- `actual_day: null` represents a missed visit.
- Existing source records are preserved; analysis findings are recalculated from source records each time.

## Active Protocol Rules

The current protocol is defined in `src/backend/protocol.py`:

- Visit 1: days 0–7
- Visit 2: days 21–35
- Visit 3: days 49–63
- Visit 4: days 77–91
- Dose: 100 mg once daily
- Prohibited medications: warfarin and phenytoin
- Required assessments: safety labs and imaging scan
- Data-entry deadline: 5 days after the visit
