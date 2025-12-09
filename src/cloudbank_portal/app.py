from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Any, Optional, Tuple

from fasthtml.common import (
    A,
    Button,
    Div,
    FastHTML,
    Form,
    H1,
    H2,
    H3,
    Input,
    Main,
    P,
    Section,
    Textarea,
    Ul,
    Li,
    fast_app,
)
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
from netCDF4 import Dataset, num2date
from starlette.datastructures import UploadFile
from starlette.responses import JSONResponse

BASE_DATASETS: list[dict[str, Any]] = []


def _get_bucket_name() -> str | None:
    return os.environ.get("GCS_BUCKET")


def _save_upload_to_temp(file: UploadFile) -> str:
    """Persist the uploaded file to a temporary location for parsing and upload."""
    file.file.seek(0)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    file.file.seek(0)
    return temp_path


def upload_to_gcs(file: UploadFile, bucket_name: str, temp_path: str) -> tuple[storage.Bucket, storage.Blob]:
    """Upload the provided file to GCS and return the bucket and blob."""
    _validate_bucket_name(bucket_name)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    safe_name = file.filename or "upload.nc"
    blob_name = f"uploads/{uuid.uuid4()}_{safe_name}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(temp_path, content_type=file.content_type or "application/octet-stream")
    blob.reload()
    return bucket, blob


def _validate_bucket_name(bucket_name: str) -> None:
    """Raise a ValueError if the bucket name is not GCS-compliant."""
    # GCS rules (simplified): 3-63 chars, lowercase letters, numbers, hyphens; start/end with letter/number.
    pattern = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    if not pattern.match(bucket_name):
        raise ValueError("must use 3-63 chars, lowercase letters, numbers, and hyphens; start/end with a letter or number")


def _blob_to_metadata(blob: storage.Blob, bucket_name: str) -> dict[str, Any]:
    return {
        "id": blob.name,
        "title": blob.name.split("/")[-1] or blob.name,
        "format": blob.content_type or "application/octet-stream",
        "bytes": blob.size,
        "updated": blob.updated.isoformat() if isinstance(blob.updated, datetime) else None,
        "location": f"gs://{bucket_name}/{blob.name}",
        "source": "upload",
    }


def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except Exception:
        return None


def _extract_time_coverage(ds: Dataset) -> dict[str, Optional[str]]:
    temporal = {"start": None, "end": None}
    time_var = ds.variables.get("time")
    if time_var is None:
        return temporal
    try:
        dates = list(num2date(time_var[:], getattr(time_var, "units", None)))
        if len(dates) == 0:
            return temporal
        temporal["start"] = min(dates).isoformat()
        temporal["end"] = max(dates).isoformat()
    except Exception:
        return temporal
    return temporal


def _extract_netcdf_metadata(path: str, description: str) -> dict[str, Any]:
    """Pull a small Dublin Core-inspired subset from a NetCDF file."""
    meta: dict[str, Any] = {}
    with Dataset(path, "r") as ds:
        meta["title"] = getattr(ds, "title", None) or os.path.basename(path)
        meta["description"] = (
            getattr(ds, "summary", None)
            or getattr(ds, "description", None)
            or getattr(ds, "processing_notes", None)
            or description
        )
        meta["creator"] = getattr(ds, "creator_name", None) or getattr(ds, "author", None)
        meta["publisher"] = getattr(ds, "publisher_name", None)
        meta["contributor"] = getattr(ds, "contributor_name", None)

        subjects = set()
        keywords = getattr(ds, "keywords", "") or getattr(ds, "keywords_vocabulary", "")
        subjects.update(k.strip() for k in keywords.split(",") if k.strip())
        feature_type = getattr(ds, "featureType", None)
        if feature_type:
            subjects.add(feature_type)
        meta["subject"] = sorted(subjects)

        meta["type"] = "dataset"
        meta["format"] = getattr(ds, "file_format", None) or getattr(ds, "Convention", None) or "NetCDF"
        meta["source"] = getattr(ds, "source", None)
        meta["rights"] = getattr(ds, "license", None)
        meta["coverage"] = {
            "spatial": {
                "bbox": {
                    "lat_min": _safe_float(getattr(ds, "geospatial_lat_min", None)),
                    "lat_max": _safe_float(getattr(ds, "geospatial_lat_max", None)),
                    "lon_min": _safe_float(getattr(ds, "geospatial_lon_min", None)),
                    "lon_max": _safe_float(getattr(ds, "geospatial_lon_max", None)),
                },
                "crs": getattr(ds, "geospatial_bounds_crs", None),
            },
            "temporal": _extract_time_coverage(ds),
        }
        meta["date"] = getattr(ds, "date_created", None)
        meta["modified"] = getattr(ds, "date_modified", None)
        if "feature_id" in ds.dimensions:
            meta["extent"] = {"features": len(ds.dimensions["feature_id"])}
    return meta


def _write_metadata(bucket: storage.Bucket, blob: storage.Blob, description: str, extracted: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "id": blob.name,
        "identifier": f"gs://{bucket.name}/{blob.name}",
        "title": extracted.get("title") or (blob.name.split("/")[-1] or blob.name),
        "description": extracted.get("description") or description,
        "creator": extracted.get("creator"),
        "publisher": extracted.get("publisher"),
        "contributor": extracted.get("contributor"),
        "subject": extracted.get("subject") or [],
        "type": extracted.get("type") or "dataset",
        "format": extracted.get("format") or blob.content_type or "application/octet-stream",
        "bytes": blob.size,
        "updated": blob.updated.isoformat() if isinstance(blob.updated, datetime) else None,
        "location": f"gs://{bucket.name}/{blob.name}",
        "source": extracted.get("source") or "upload",
        "rights": extracted.get("rights"),
        "coverage": extracted.get("coverage") or {},
        "date": extracted.get("date"),
        "modified": extracted.get("modified"),
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    meta_blob = bucket.blob(f"metadata/{blob.name}.json")
    meta_blob.upload_from_string(json.dumps(metadata), content_type="application/json")
    return metadata


def list_datasets(bucket_name: str | None) -> list[dict[str, Any]]:
    datasets: list[dict[str, Any]] = list(BASE_DATASETS)
    if not bucket_name:
        return datasets

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        metadata_map: dict[str, dict[str, Any]] = {}
        for meta_blob in bucket.list_blobs(prefix="metadata/"):
            if not meta_blob.name.endswith(".json"):
                continue
            try:
                data = json.loads(meta_blob.download_as_text())
                if "id" in data:
                    metadata_map[data["id"]] = data
            except Exception:
                continue

        blobs = bucket.list_blobs(prefix="uploads/")
        for blob in blobs:
            if blob.name in metadata_map:
                datasets.append(metadata_map[blob.name])
            else:
                datasets.append(_blob_to_metadata(blob, bucket_name))
        # include any metadata entries that do not have a matching upload (unlikely but harmless)
        for ds_id, meta in metadata_map.items():
            if not any(d.get("id") == ds_id for d in datasets):
                datasets.append(meta)
    except GoogleCloudError:
        return datasets

    return datasets


def get_dataset_metadata(dataset_id: str, bucket_name: str | None) -> dict[str, Any] | None:
    for ds in BASE_DATASETS:
        if ds["id"] == dataset_id:
            return ds

    if not bucket_name:
        return None

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        meta_blob = bucket.blob(f"metadata/{dataset_id}.json")
        if meta_blob.exists():
            try:
                return json.loads(meta_blob.download_as_text())
            except Exception:
                pass
        blob = bucket.blob(dataset_id)
        if blob.exists():
            blob.reload()
            return _blob_to_metadata(blob, bucket_name)
        return None
    except GoogleCloudError:
        return None


def _upload_section() -> Section:
    return Section(
        H2("Upload to Google Cloud Storage"),
        P(
            "Upload a NetCDF file; the app stores it in the configured GCS bucket "
            "and echoes your description. Set the env var GCS_BUCKET for uploads."
        ),
        Form(
            P("Pick a NetCDF file and add an optional description:"),
            Input(type="file", name="file", accept=".nc,.netcdf"),
            Textarea(name="notes", placeholder="Describe your dataset", rows=3),
            Div(Button("Upload", type="submit")),
            method="post",
            enctype="multipart/form-data",
        ),
    )


def _datasets_section(datasets: list[dict[str, Any]]) -> Section:
    items = []
    for ds in datasets:
        title = ds.get("title") or ds.get("id")
        fmt = ds.get("format", "")
        location = ds.get("location", "")
        size_text = ""
        try:
            size_bytes = int(ds.get("bytes", 0))
            size_text = f" • {size_bytes / (1024 * 1024):.1f} MiB"
        except Exception:
            size_text = ""
        items.append(
            Li(
                A(f"{title} ({fmt}{size_text})", href=f"/datasets/{ds.get('id')}"),
                P(location),
            )
        )
    return Section(H3("Available datasets"), Ul(*items))


def _metadata_section(meta: dict[str, Any], size_text: str) -> Section:
    rows = []
    def add(label: str, value: Any):
        if value is None or value == "" or value == []:
            return
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v)
        rows.append(Li(f"{label}: {value}"))

    add("Identifier", meta.get("identifier") or meta.get("location"))
    add("Description", meta.get("description"))
    add("Creator", meta.get("creator"))
    add("Publisher", meta.get("publisher"))
    add("Contributor", meta.get("contributor"))
    add("Subjects", meta.get("subject"))
    add("Type", meta.get("type"))
    add("Format", meta.get("format"))
    add("Source", meta.get("source"))
    add("Rights", meta.get("rights"))
    add("Size", size_text)
    add("Date created", meta.get("date"))
    add("Date modified", meta.get("modified"))
    add("Uploaded at", meta.get("uploaded_at"))
    coverage = meta.get("coverage", {}) or {}
    spatial = coverage.get("spatial") or {}
    bbox = spatial.get("bbox") or {}
    bbox_parts = [f"{k}={v}" for k, v in bbox.items() if v is not None]
    if bbox_parts:
        add("Spatial coverage (bbox)", "; ".join(bbox_parts))
    if spatial.get("crs"):
        add("Spatial CRS", spatial.get("crs"))
    temporal = coverage.get("temporal") or {}
    if temporal.get("start") or temporal.get("end"):
        add("Temporal coverage", f"{temporal.get('start')} to {temporal.get('end')}")
    extent = meta.get("extent") or {}
    if extent.get("features"):
        add("Feature count", extent.get("features"))
    return Section(H3("Metadata"), Ul(*rows))


def build_app() -> FastHTML:
    """Create a small FastHTML demo app."""
    app, rt = fast_app()

    @rt("/", methods=["GET"])
    def get_root():
        bucket = _get_bucket_name()
        datasets = list_datasets(bucket)
        page = Main(
            H1("Cloudbank Toy Data Portal"),
            P(
                "A minimal FastHTML app that will later connect to storage and metadata "
                "extraction for hydrology datasets."
            ),
            _upload_section(),
            _datasets_section(datasets),
        )
        page.title = "Cloudbank Toy Data Portal"
        return page

    @rt("/healthz")
    def get_health():
        return {"status": "ok"}

    @rt("/api/datasets")
    def api_list_datasets():
        bucket = _get_bucket_name()
        payload = {"datasets": list_datasets(bucket)}
        return JSONResponse(payload)

    @rt("/api/datasets/{dataset_id}")
    def api_get_dataset(dataset_id: str):
        bucket = _get_bucket_name()
        meta = get_dataset_metadata(dataset_id, bucket)
        if not meta:
            return JSONResponse({"detail": "Dataset not found"}, status_code=404)
        return JSONResponse(meta)

    @rt("/datasets/{dataset_id:path}")
    def get_dataset_page(dataset_id: str):
        bucket = _get_bucket_name()
        meta = get_dataset_metadata(dataset_id, bucket)
        if not meta:
            return JSONResponse({"detail": "Dataset not found"}, status_code=404)
        size_text = "unknown"
        try:
            size_bytes = int(meta.get("bytes", 0))
            size_text = f"{size_bytes / (1024 * 1024):.1f} MiB"
        except Exception:
            pass
        return Main(
            H2(meta.get("title", dataset_id)),
            P(f"Location: {meta.get('location', 'N/A')}"),
            _metadata_section(meta, size_text),
            Form(Button("Back", type="submit"), method="get", action="/"),
        )

    @rt("/", methods=["POST"])
    async def post_notes(file: UploadFile | None = None, notes: str = ""):
        clean = notes.strip() or "No description provided."
        bucket = _get_bucket_name()
        upload_msg = ""

        if file and file.filename:
            if not bucket:
                upload_msg = "GCS_BUCKET is not set; file not stored."
            else:
                temp_path = None
                try:
                    temp_path = _save_upload_to_temp(file)
                    extracted_meta: dict[str, Any] = {}
                    try:
                        extracted_meta = _extract_netcdf_metadata(temp_path, clean)
                    except Exception:
                        extracted_meta = {}
                    bucket_obj, blob = upload_to_gcs(file, bucket, temp_path)
                    meta = _write_metadata(bucket_obj, blob, clean, extracted_meta)
                    upload_msg = f"Stored at {meta['location']}"
                except ValueError as exc:
                    upload_msg = f"Invalid bucket name: {exc}"
                except Exception as exc:  # pragma: no cover - safety net
                    upload_msg = f"Upload failed: {exc}"
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
        else:
            upload_msg = "No file uploaded."

        return Main(
            H2("Thanks!"),
            P("We recorded your description for the upcoming ingestion step:"),
            P(clean),
            P(upload_msg),
            P("Use Back to return to the landing page."),
            Form(Button("Back", type="submit"), method="get", action="/"),
        )

    return app


def run() -> None:
    """Run the app with uvicorn."""
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
