# Cloudbank Toy Data Portal

Small Python web app (FastHTML + Starlette + Uvicorn) that backs the Cloudbank hydrology tutorial. It serves a landing page, handles uploads to Google Cloud Storage, and exposes a health endpoint. The container image is built and published automatically to the GitHub Container Registry.

## What it does
- Renders a landing page with an upload form and a live list of datasets.
- Accepts a NetCDF file upload and an optional description.
- Stores uploads in a Google Cloud Storage (GCS) bucket whose name comes from the `GCS_BUCKET` environment variable.
- Writes a JSON sidecar for each upload to `metadata/<upload-key>.json` so the catalog can be reconstructed from storage alone.
- Shows each dataset discovered in the bucket on the home page with links to per-dataset pages.
- Returns a confirmation page that echoes the description and where the file was stored.
- Provides a lightweight health endpoint at `/healthz` that returns `{"status": "ok"}`.
- Exposes simple JSON APIs to list datasets and fetch metadata for a single dataset.

## How it is built
- FastHTML components compose the page; Starlette routing comes from `fast_app()`.
- Upload handling lives in `upload_to_gcs()` (see `src/cloudbank_portal/app.py`). It:
  - Reads the bucket name from `GCS_BUCKET`.
  - Uses `google-cloud-storage` to create a blob under `uploads/<uuid>_<filename>`.
  - Streams the file with the provided content type and returns the `gs://` path.
- `cloudbank_portal.run()` runs the app with Uvicorn; `PORT` defaults to `8000`.
- Dataset APIs use a small in-app catalog plus any uploaded objects in the bucket (if present).

## Configuration
- `GCS_BUCKET` (required for uploads): target Google Cloud Storage bucket name. If unset, uploads are rejected with a friendly message.
- `PORT` (optional): listening port; defaults to `8000`.
- The app requires credentials that can write to the bucket:
  - In Kubernetes, prefer Workload Identity or a service account with the `roles/storage.objectAdmin` role on the bucket.
  - Locally, set `GOOGLE_APPLICATION_CREDENTIALS` to a JSON key with that role, or use `gcloud auth application-default login`.
- Bucket naming rules (simplified): 3-63 characters; only lowercase letters, numbers, and hyphens; must start and end with a letter or number. Example used in the tutorial: `${USER}-toy-portal`.

## API endpoints
- `GET /api/datasets` — returns JSON with a `datasets` list. If `GCS_BUCKET` is set and readable, it includes any uploads found under the `uploads/` prefix (and any sidecar metadata under `metadata/`) with size, content type, update time, and `gs://` path.
- `GET /api/datasets/{dataset_id}` — returns JSON metadata for the matching dataset. Looks for a sidecar in `metadata/` first, then tries to find a matching object in the bucket (by object name). Returns `404` if not found or if the bucket is not available.

Examples:
```bash
curl http://127.0.0.1:8000/api/datasets
curl http://127.0.0.1:8000/api/datasets/camels-usgs-streamflow
```

## Local development
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .[dev]
export GCS_BUCKET="your-bucket-name"
uv run python -m cloudbank_portal
```
The app listens on `http://127.0.0.1:8000/`.

Run tests:
```bash
uv run pytest
```

## Container image
- Dockerfile runs `python -m cloudbank_portal` under Uvicorn.
- GitHub Actions builds and pushes `ghcr.io/<owner>/cloudbank_toy_data_portal:latest` and a commit-sha tag on every push to `main`.
- The registry entry is public, so no image pull secret is needed.

Quick test of the image:
```bash
docker run --rm -p 8000:8000 \
  -e GCS_BUCKET="your-bucket-name" \
  ghcr.io/zonca/cloudbank_toy_data_portal:latest
curl http://127.0.0.1:8000/healthz
```

## Deployment notes
- Designed for Google Kubernetes Engine Autopilot; the tutorial in `2_deploy_portal.md` shows how to deploy it.
- Create the bucket in the same region as the cluster and grant the service account write access.
- The app is stateless; scaling to multiple replicas is safe. Storage and metadata are handled via Google Cloud Storage.
- No database is required: the app reads metadata from a small built-in catalog, per-upload JSON sidecars under `metadata/`, and objects discovered in the bucket.
