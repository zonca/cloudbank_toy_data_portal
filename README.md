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

## Google Cloud Storage upload
Set an environment variable with your bucket name before starting the app so uploads go to GCS:
```bash
export GCS_BUCKET="your-bucket-name"
uv run python -m cloudbank_portal
```
On GKE Autopilot, use Workload Identity or a service account that has `roles/storage.objectAdmin` on the bucket.

## Container build
The Dockerfile runs the app with uvicorn. The GitHub Actions workflow builds and pushes the image to GHCR (ghcr.io/<owner>/cloudbank_toy_data_portal).
