from fastapi.testclient import TestClient
from pathlib import Path

from backend.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "trialguard-api"}


def test_summary_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json().keys() == {
        "sites",
        "patients",
        "deviations",
        "open_deviations",
        "capa_reports",
        "datasets",
    }


def test_import_analysis_and_capa_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "sites": [{"site_code": "S-1", "name": "Test Site", "country": "US"}],
        "patients": [{"patient_code": "P-1", "site_code": "S-1"}],
        "visits": [],
        "doses": [],
        "medications": [],
        "assessments": [],
    }

    with TestClient(app) as client:
        import_response = client.post("/api/import", json=payload)
        deviations = client.get("/api/deviations").json()
        capa_response = client.post("/api/capa", json={"deviation_id": deviations[0]["id"]})

    assert import_response.status_code == 200
    assert import_response.json()["major"] == 4
    assert capa_response.status_code == 200
    assert capa_response.json()["deviation_id"] == deviations[0]["id"]


def test_deviation_status_can_be_dispositioned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "sites": [{"site_code": "S-1", "name": "Test Site", "country": "US"}],
        "patients": [{"patient_code": "P-1", "site_code": "S-1"}],
    }

    with TestClient(app) as client:
        client.post("/api/import", json=payload)
        deviation = client.get("/api/deviations").json()[0]
        response = client.patch(
            f"/api/deviations/{deviation['id']}/status",
            json={"status": "under_investigation"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "under_investigation"


def test_datasets_append_and_delete_independently(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    first = {"dataset_name": "North cohort", "sites": [{"site_code": "N-1", "name": "North", "country": "US"}], "patients": [{"patient_code": "N-P1", "site_code": "N-1"}]}
    second = {"dataset_name": "South cohort", "sites": [{"site_code": "S-1", "name": "South", "country": "US"}], "patients": [{"patient_code": "S-P1", "site_code": "S-1"}]}

    with TestClient(app) as client:
        first_id = client.post("/api/import", json=first).json()["dataset_id"]
        second_id = client.post("/api/import", json=second).json()["dataset_id"]
        assert client.get("/api/summary").json()["datasets"] == 2
        assert {item["name"] for item in client.get("/api/datasets").json()} == {"North cohort", "South cohort"}
        client.delete(f"/api/datasets/{first_id}")
        remaining = client.get("/api/datasets").json()

    assert len(remaining) == 1
    assert remaining[0]["id"] == second_id
    assert remaining[0]["name"] == "South cohort"


def test_duplicate_dataset_import_returns_validation_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "dataset_name": "North cohort",
        "sites": [{"site_code": "N-1", "name": "North", "country": "US"}],
        "patients": [{"patient_code": "N-P1", "site_code": "N-1"}],
    }

    with TestClient(app) as client:
        first = client.post("/api/import", json=payload)
        second = client.post("/api/import", json=payload)

    assert first.status_code == 200
    assert second.status_code == 422
    assert "site code" in second.json()["detail"]


def test_dataset_delete_removes_capa_linked_by_deviation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "dataset_name": "North cohort",
        "sites": [{"site_code": "N-1", "name": "North", "country": "US"}],
        "patients": [{"patient_code": "N-P1", "site_code": "N-1"}],
    }

    with TestClient(app) as client:
        dataset_id = client.post("/api/import", json=payload).json()["dataset_id"]
        deviation_id = client.get("/api/deviations").json()[0]["id"]
        client.post("/api/capa", json={"deviation_id": deviation_id})

        response = client.delete(f"/api/datasets/{dataset_id}")
        remaining = client.get("/api/datasets").json()

    assert response.status_code == 200
    assert remaining == []


def test_reanalysis_preserves_capa_backed_findings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "dataset_name": "North cohort",
        "sites": [{"site_code": "N-1", "name": "North", "country": "US"}],
        "patients": [{"patient_code": "N-P1", "site_code": "N-1"}],
    }

    with TestClient(app) as client:
        client.post("/api/import", json=payload)
        deviation = client.get("/api/deviations").json()[0]
        client.post("/api/capa", json={"deviation_id": deviation["id"]})
        response = client.post("/api/analyze")
        deviations = client.get("/api/deviations").json()
        reports = client.get("/api/capa").json()

    assert response.status_code == 200
    assert len(deviations) == 4
    assert len(reports) == 1


def test_investigation_returns_findings_and_dynamic_questions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "sites": [{"site_code": "S-1", "name": "Risk Site", "country": "US"}],
        "patients": [{"patient_code": "P-1", "site_code": "S-1"}],
        "visits": [{"patient_code": "P-1", "visit_number": 1, "scheduled_day": 0, "actual_day": 20}],
    }

    with TestClient(app) as client:
        client.post("/api/import", json=payload)
        response = client.get("/api/investigation/S-1")

    assert response.status_code == 200
    assert response.json()["findings"]
    assert any("visit" in question.lower() for question in response.json()["questions"])


def test_investigation_question_variants_change_wording(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "trialguard.db"))
    payload = {
        "sites": [{"site_code": "S-1", "name": "Risk Site", "country": "US"}],
        "patients": [{"patient_code": "P-1", "site_code": "S-1"}],
        "visits": [{"patient_code": "P-1", "visit_number": 1, "scheduled_day": 0, "actual_day": 20}],
    }

    with TestClient(app) as client:
        client.post("/api/import", json=payload)
        first = client.get("/api/investigation/S-1?variant=0").json()["questions"]
        second = client.get("/api/investigation/S-1?variant=1").json()["questions"]

    assert first != second