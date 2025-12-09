from __future__ import annotations

import os

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
            H2("Upload (placeholder)"),
            P(
                "This page accepts your NetCDF upload and will pass it to the backend "
                "pipeline in later steps. For now it simply echoes your description."
            ),
            Form(
                P("File uploads and bucket integration arrive in the next tutorial step."),
                Textarea(name="notes", placeholder="Describe your dataset", rows=3),
                Div(Button("Submit notes", type="submit")),
                method="post",
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
    def post_notes(notes: str = ""):
        clean = notes.strip() or "No description provided."
        return Main(
            H2("Thanks!"),
            P("We recorded your description for the upcoming ingestion step:"),
            P(clean),
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
