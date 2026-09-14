# TrialGuard

TrialGuard is a local-first clinical trial risk monitor for detecting protocol deviations before they become audit findings. It compares patient records with the active protocol, ranks sites using explainable risk signals, and persists CAPA-ready corrective and preventive actions.

## Team

| Field | Value |
|---|---|
| Team Name | Imaging Intelligence |
| Track | AI |
| Team Lead | To be provided; see `submission.yaml` |
| Members | To be provided; see `submission.yaml` |

## Problem

Clinical trial risk managers oversee thousands of visits across many sites, but missed visits, wrong dosing, prohibited medications, and late data entry are often found only during reconciliation or regulatory inspection. TrialGuard provides an evidence trail for identifying the sites and subjects that need attention while there is still time to investigate and correct the issue.

## Solution

TrialGuard imports structured, de-identified trial records into SQLite, evaluates them against explicit protocol rules, classifies deviations as major, minor, or administrative, and computes an explainable site risk score. Investigators can review evidence, generate grounded investigation questions, and create a persisted CAPA report without changing the underlying source records.

## Key Features

- Protocol comparison for visit windows, doses, prohibited medications, required assessments, and data-entry deadlines.
- Evidence-backed deviation findings with expected rules and observed values.
- Severity-weighted site risk ranking with Critical, High, Moderate, and Low levels.
- Local JSON record import and on-demand re-analysis using SQLite.
- Persisted CAPA reports linked to their source deviations.

## Tech Stack

| Category | Technologies |
|---|---|
| Languages | Python, JavaScript, HTML, CSS |
| Frameworks | FastAPI, Uvicorn |
| IBM Technologies | IBM Bob adapter boundary for grounded assistant deployment |
| Database | SQLite for local runtime |
| Other | GitHub Actions, JSON data import |

## Repository Structure

```text
src/backend/       API, protocol engine, analyzer, SQLite services
src/frontend/      Browser dashboard
docs/              Problem, solution, architecture, setup, and data format
	demo/              Demo artifacts, including five dashboard screenshots
presentation/      Slide deck location
submission.yaml    Structured submission metadata
```

## Run Locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r src/requirements.txt
Copy-Item src/.env.example .env
uvicorn backend.main:app --app-dir src --reload
```

Open `http://127.0.0.1:8000`. For the complete import format and validation steps, see [`docs/setup-guide.md`](docs/setup-guide.md) and [`docs/data-format.md`](docs/data-format.md).

## Demo Artifacts

- Video: add the final 3–5 minute recording URL to [`demo/demo-video-link.txt`](demo/demo-video-link.txt) before submission.
- Live URL: [`demo/live-demo-url.txt`](demo/live-demo-url.txt) currently records the local-only status.
- Screenshots: five populated dashboard views are available in [`demo/screenshots/`](demo/screenshots/): home dashboard, loaded datasets, risk radar, deviation inbox, and CAPA response.
- Presentation: add the final PDF or PPTX deck to [`presentation/`](presentation/).

## Known Limitations

- IBM Bob credentials and the final Bob adapter contract are not configured in this repository; the current evidence brief is generated only from stored records and is deliberately not presented as an AI decision.
- Authentication and authorization are not yet enabled; use only with de-identified local development data.
- SQLite is appropriate for local development and judging; a deployed environment should use a managed database and secret store.

## What We Are Most Proud Of

The strongest part is the traceable path from an imported record to a specific protocol rule, severity classification, site risk score, and persisted CAPA action. A reviewer can inspect the evidence rather than trusting an opaque score.
