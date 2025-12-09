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
