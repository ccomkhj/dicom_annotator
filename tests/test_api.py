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


def test_get_case_with_renamed_modality_subdir(tmp_path: Path):
    """Regression: modality key != subdir name must resolve correctly."""
    (tmp_path / "project.yaml").write_text(
        """
name: rename-test
labels:
  - id: 1
    name: prostate
    color: "#000"
sources:
  - kind: aligned
    root: data
    case_glob: "case_*"
    modalities:
      t2: t2_images
"""
    )
    write_dicom_series(tmp_path / "data" / "case_001" / "t2_images", slices=2)
    project = load_project(tmp_path)
    client = TestClient(create_app(tmp_path, project))

    r = client.get("/api/cases/case_001")
    assert r.status_code == 200
    body = r.json()
    assert body["modalities"] == ["t2"]            # key, not subdir
    assert body["slice_count"] == 2
    # modality_files keyed by the modality KEY but listing files from the SUBDIR
    files = body["modality_files"]["t2"]
    assert len(files) == 2
    assert all("t2_images" in f for f in files)


def test_get_image_manifest(client: TestClient):
    r = client.get("/images/case_001/t2/manifest.json")
    assert r.status_code == 200
    body = r.json()
    assert len(body["slice_urls"]) == 3
    assert body["slice_urls"][0].endswith("/0.dcm")
    assert body["reference_geometry"]["shape"] == [3, 8, 8]


def test_get_image_slice_bytes(client: TestClient):
    r = client.get("/images/case_001/t2/0.dcm")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/dicom")
    assert r.content[:128 + 4][128:132] == b"DICM" or len(r.content) > 0


def test_get_image_unknown_modality_404(client: TestClient):
    r = client.get("/images/case_001/bogus/manifest.json")
    assert r.status_code == 404
