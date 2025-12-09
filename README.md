# Cloudbank Toy Data Portal (FastHTML demo)

Minimal FastHTML app that will back the toy hydrology data portal tutorial. It renders a landing page, a placeholder upload form, and a simple health check endpoint.

## Local development
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .[dev]
uv run python -m cloudbank_portal
```
The app listens on `http://127.0.0.1:8000/`.

Run tests:
```bash
uv run pytest
```

## Container build
The Dockerfile runs the app with uvicorn. The GitHub Actions workflow builds and pushes the image to GHCR (ghcr.io/<owner>/cloudbank_toy_data_portal).
