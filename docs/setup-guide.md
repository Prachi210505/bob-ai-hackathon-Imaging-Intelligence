# Setup Guide

> **This file is read by the automated evaluation pipeline. Be precise and complete.**

## Prerequisites

Before you begin, install:

- Python 3.11 or newer
- Git

No external database server or Docker installation is required. TrialGuard uses
SQLite locally.

## Environment Variables

Copy the source configuration template to a root-level `.env` file:

```powershell
Copy-Item src/.env.example .env
```

| Variable | Description | Required |
|---|---|---|
| Variable | Description | Required |
|---|---|---|
| `DATABASE_PATH` | Local SQLite path, default `data/trialguard.db` | No |
| `APP_HOST` | Local API host, default `127.0.0.1` | No |
| `APP_PORT` | Local API port, default `8000` | No |
| `APP_ENV` | Runtime environment name | No |
| `BOB_API_URL` | IBM Bob integration URL when configured | No |
| `BOB_API_KEY` | IBM Bob integration key when configured | No |

## Installation

```powershell
# 1. Clone the repository
git clone https://github.com/Prachi210505/bob-ai-hackathon-Imaging-Intelligence.git
cd bob-ai-hackathon-Imaging-Intelligence

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install backend dependencies
python -m pip install -r src/requirements.txt

# 4. Configure local environment
Copy-Item src/.env.example .env
```

The first application start creates `data/trialguard.db` and its schema.

## Running the Application

```powershell
# Start the backend from the repository root
uvicorn backend.main:app --app-dir src --reload
```

The API is available at `http://127.0.0.1:8000`.

Verify it by opening:

- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/api/summary`
- `http://127.0.0.1:8000/docs`

## Running Tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests -v
```

## Quick Demo (Optional)

If you have a demo script or sample data to showcase the project quickly:

```powershell
uvicorn backend.main:app --app-dir src --reload
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | Activate `.venv` and run `python -m pip install -r src/requirements.txt`. |
| Database file is not visible | Start the API once; it creates `data/trialguard.db` automatically. |
| Port 8000 is busy | Set another `APP_PORT` in `.env` and start Uvicorn with that port. |
