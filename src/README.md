# Source Code

TrialGuard source code is organized as a local-first web application.

```text
src/
  backend/       FastAPI application and SQLite services
  frontend/      Web interface served by FastAPI
  requirements.txt
  .env.example
```

The SQLite database is created at `data/trialguard.db` when the backend starts.
The `data/` directory is ignored by Git, so local records and credentials are
not committed.

## Development commands

From the repository root:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r src/requirements.txt
uvicorn backend.main:app --app-dir src --reload
```

The API is available at `http://127.0.0.1:8000`, with interactive docs at
`http://127.0.0.1:8000/docs`.

## Structure Guidelines

Organize your code logically. Here are common patterns — use whatever fits
your project:

### Web Application
```
src/
  backend/        ← API server code
  frontend/       ← UI code
  shared/         ← Shared utilities/types
```

### Data / AI Project
```
src/
  data/           ← Data ingestion / preprocessing
  models/         ← ML model code
  api/            ← Serving layer
  notebooks/      ← Jupyter notebooks (exploration)
```

### CLI / Script-based Tool
```
src/
  cli/            ← CLI entry points
  lib/            ← Core logic
  utils/          ← Helpers
```

## Important Files to Include

- `requirements.txt` or `package.json` — dependency manifest
- `.env.example` — template for environment variables (NEVER commit `.env`)
- Any database migration files
- Configuration files

## What NOT to Include in src/

- `.env` files with real secrets
- Large binary files (use Git LFS or link externally)
- `node_modules/` or `venv/` (these are in `.gitignore`)
- Build artifacts (`dist/`, `build/`, `__pycache__/`)
