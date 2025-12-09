from __future__ import annotations

import os
import uuid

from fasthtml.common import (
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
from starlette.datastructures import UploadFile


def _get_bucket_name() -> str | None:
    return os.environ.get("GCS_BUCKET")


def upload_to_gcs(file: UploadFile, bucket_name: str) -> str:
    """Upload the provided file to GCS and return the gs:// path."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    safe_name = file.filename or "upload.nc"
    blob_name = f"uploads/{uuid.uuid4()}_{safe_name}"
    blob = bucket.blob(blob_name)
    file.file.seek(0)
    blob.upload_from_file(file.file, content_type=file.content_type or "application/octet-stream")
    return f"gs://{bucket_name}/{blob_name}"


def build_app() -> FastHTML:
    """Create a small FastHTML demo app."""
    app, rt = fast_app()

    landing = Main(
        H1("Cloudbank Toy Data Portal"),
        P(
            "A minimal FastHTML app that will later connect to storage and metadata "
            "extraction for hydrology datasets."
        ),
        Section(
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
        ),
        Section(
            H3("Demo catalog"),
            Ul(
                Li("CAMELS USGS Streamflow (1980–2014) — NetCDF, CONUS coverage"),
                Li("NWM Routelink NetCDF (v2.2.0 domain) — NetCDF, CONUS coverage"),
            ),
        ),
    )

    @rt("/", methods=["GET"])
    def get_root():
        return landing

    @rt("/healthz")
    def get_health():
        return {"status": "ok"}

    @rt("/", methods=["POST"])
    async def post_notes(file: UploadFile | None = None, notes: str = ""):
        clean = notes.strip() or "No description provided."
        bucket = _get_bucket_name()
        upload_msg = ""

        if file and file.filename:
            if not bucket:
                upload_msg = "GCS_BUCKET is not set; file not stored."
            else:
                try:
                    path = upload_to_gcs(file, bucket)
                    upload_msg = f"Stored at {path}"
                except Exception as exc:  # pragma: no cover - safety net
                    upload_msg = f"Upload failed: {exc}"
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
