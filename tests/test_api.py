from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dicom_annotator.api import create_app
from dicom_annotator.config import load_project
from tests.conftest import write_dicom_series


@pytest.fixture
def aligned_project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.yaml").write_text(
        """
name: test
labels:
  - id: 1
    name: prostate
    color: "#4FC3F7"
sources:
  - kind: aligned
    root: data
    case_glob: "case_*"
    modalities:
      t2: t2
"""
    )
    write_dicom_series(tmp_path / "data" / "case_001" / "t2", slices=3)
    write_dicom_series(tmp_path / "data" / "case_002" / "t2", slices=3)
    return tmp_path


@pytest.fixture
def client(aligned_project_root: Path) -> TestClient:
    project = load_project(aligned_project_root)
    app = create_app(aligned_project_root, project)
    return TestClient(app)


def test_get_project(client: TestClient):
    r = client.get("/api/project")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "test"
    assert body["labels"][0]["name"] == "prostate"


def test_get_cases(client: TestClient):
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json()
    assert sorted(c["id"] for c in cases) == ["case_001", "case_002"]
    for c in cases:
        assert c["kind"] == "aligned"
        assert c["annotated"] is False
        assert c["labels_present"] == []


def test_get_case_detail(client: TestClient):
    r = client.get("/api/cases/case_001")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "case_001"
    assert body["modalities"] == ["t2"]
    assert body["slice_count"] == 3
    assert len(body["reference_affine"]) == 4


def test_get_case_not_found(client: TestClient):
    r = client.get("/api/cases/does_not_exist")
    assert r.status_code == 404
    assert r.json()["error"] == "case_not_found"
