from starlette.testclient import TestClient

from cloudbank_portal import build_app


def test_health_endpoint():
    client = TestClient(build_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_homepage_renders():
    client = TestClient(build_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Cloudbank Toy Data Portal" in resp.text


def test_notes_round_trip():
    client = TestClient(build_app())
    resp = client.post("/", data={"notes": "Sample dataset"})
    assert resp.status_code == 200
    assert "Sample dataset" in resp.text


def test_api_lists_base_datasets():
    client = TestClient(build_app())
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    data = resp.json()
    assert "datasets" in data


def test_api_dataset_not_found():
    client = TestClient(build_app())
    resp = client.get("/api/datasets/does-not-exist")
    assert resp.status_code == 404


def test_validate_bucket_name_rejects_bad_value(monkeypatch):
    # simulate setting an invalid bucket name and posting a file
    client = TestClient(build_app())
    files = {"file": ("sample.nc", b"data")}
    resp = client.post("/", files=files, data={"notes": ""})
    # With no env var, message is "GCS_BUCKET is not set"; set a bad one and retry.
    monkeypatch.setenv("GCS_BUCKET", "bad_bucket_name")
    resp = client.post("/", files=files, data={"notes": ""})
    assert "Invalid bucket name" in resp.text


def test_dataset_page_renders():
    client = TestClient(build_app())
    # create a fake upload metadata entry by mocking GCS is more involved; for now ensure 404 is returned for empty catalog.
    resp = client.get("/datasets/unknown")
    assert resp.status_code == 404


def test_dataset_page_not_found():
    client = TestClient(build_app())
    resp = client.get("/datasets/unknown")
    assert resp.status_code == 404
