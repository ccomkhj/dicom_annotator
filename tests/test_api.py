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


def test_image_slice_out_of_range_404(client: TestClient):
    r = client.get("/images/case_001/t2/99.dcm")
    assert r.status_code == 404
    assert r.json()["error"] == "slice_out_of_range"


def test_get_mask_unknown_label_404(client: TestClient):
    r = client.get("/api/cases/case_001/masks/999")
    assert r.status_code == 404
    assert r.json()["error"] == "label_unknown"


def test_put_mask_unknown_label_404(client: TestClient):
    body = {"shape": [3, 8, 8], "dtype": "uint8",
            "data": base64.b64encode(b"\x00" * (3 * 8 * 8)).decode("ascii")}
    r = client.put("/api/cases/case_001/masks/999", json=body)
    assert r.status_code == 404
    assert r.json()["error"] == "label_unknown"


def test_raw_dicom_case_end_to_end(tmp_path: Path):
    """The raw_dicom source path (flat series, single 'series' modality) was
    entirely untested through HTTP."""
    (tmp_path / "project.yaml").write_text(
        """
name: rawtest
labels:
  - id: 1
    name: lesion
    color: "#f00"
sources:
  - kind: raw_dicom
    root: nbia
    case_pattern: "patient_*/study_*/series_*"
"""
    )
    series = tmp_path / "nbia" / "patient_a" / "study_1" / "series_1"
    write_dicom_series(series, slices=4)
    project = load_project(tmp_path)
    client = TestClient(create_app(tmp_path, project))

    cases = client.get("/api/cases").json()
    assert len(cases) == 1
    case_id = cases[0]["id"]
    assert cases[0]["kind"] == "raw_dicom"
    assert cases[0]["modalities"] == ["series"]

    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["slice_count"] == 4

    manifest = client.get(f"/images/{case_id}/series/manifest.json")
    assert manifest.status_code == 200
    assert len(manifest.json()["slice_urls"]) == 4

    slice0 = client.get(f"/images/{case_id}/series/0.dcm")
    assert slice0.status_code == 200


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["case_count"] == 2


def test_refresh_picks_up_new_case(client: TestClient, aligned_project_root: Path):
    """POST /api/refresh rescans the filesystem so a newly-added case appears."""
    write_dicom_series(aligned_project_root / "data" / "case_003" / "t2", slices=3)

    before = {c["id"] for c in client.get("/api/cases").json()}
    assert "case_003" not in before

    r = client.post("/api/refresh")
    assert r.status_code == 200
    assert r.json()["case_count"] == 3

    after = {c["id"] for c in client.get("/api/cases").json()}
    assert "case_003" in after


import base64

import numpy as np

from dicom_annotator.mask_io import envelope_to_volume


def test_put_and_get_mask_roundtrip(client: TestClient):
    # First fetch geometry to know expected shape
    detail = client.get("/api/cases/case_001").json()
    shape = tuple(detail["reference_shape"])
    volume = np.zeros(shape, dtype=np.uint8)
    volume[1, 2, 3] = 1
    body = {
        "shape": list(shape),
        "dtype": "uint8",
        "data": base64.b64encode(volume.tobytes()).decode("ascii"),
    }

    put = client.put("/api/cases/case_001/masks/1", json=body)
    assert put.status_code == 200, put.text
    assert "saved_at" in put.json()

    get = client.get("/api/cases/case_001/masks/1")
    assert get.status_code == 200
    loaded = envelope_to_volume(get.json())
    np.testing.assert_array_equal(loaded, volume)


def test_put_mask_recovers_from_corrupt_meta(client: TestClient, aligned_project_root: Path):
    """A truncated/corrupt meta.json (e.g. from a crash mid-write) must not break
    the next save: put_mask treats unreadable JSON as empty and writes valid JSON."""
    import json

    detail = client.get("/api/cases/case_001").json()
    shape = tuple(detail["reference_shape"])
    volume = np.zeros(shape, dtype=np.uint8)
    body = {
        "shape": list(shape),
        "dtype": "uint8",
        "data": base64.b64encode(volume.tobytes()).decode("ascii"),
    }

    # Plant a corrupt meta.json where the save will land.
    meta_path = aligned_project_root / "annotations" / "case_001" / "meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text('{"labels": {"prostate": ')  # truncated JSON

    put = client.put("/api/cases/case_001/masks/1", json=body)
    assert put.status_code == 200, put.text
    # meta.json is now valid JSON again and records the saved label.
    meta = json.loads(meta_path.read_text())
    assert "prostate" in meta["labels"]


def test_put_mask_wrong_shape_422(client: TestClient):
    body = {"shape": [99, 99, 99], "dtype": "uint8",
            "data": base64.b64encode(b"\x00" * (99 * 99 * 99)).decode("ascii")}
    r = client.put("/api/cases/case_001/masks/1", json=body)
    assert r.status_code == 422
    assert r.json()["error"] == "shape_mismatch"


def test_put_mask_invalid_envelope_data_length(client: TestClient):
    """When envelope data length doesn't match declared shape, return 422 invalid_envelope."""
    body = {
        "shape": [3, 8, 8],     # declares 192 bytes
        "dtype": "uint8",
        "data": base64.b64encode(b"\x00" * 10).decode("ascii"),  # but only 10 bytes
    }
    r = client.put("/api/cases/case_001/masks/1", json=body)
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_envelope"


def test_get_mask_warns_on_geometry_drift(client: TestClient, aligned_project_root: Path):
    """A stored mask whose shape no longer matches the reference geometry must be
    returned with a warning (DICOM was reprocessed under it), not silently."""
    import nibabel as nib

    ann = aligned_project_root / "annotations" / "case_001"
    ann.mkdir(parents=True)
    # Reference is (3, 8, 8); write a (5, 5, 5) mask (stored XYZ, so transpose).
    wrong = np.zeros((5, 5, 5), dtype=np.uint8)
    nib.save(nib.Nifti1Image(np.transpose(wrong, (2, 1, 0)), np.eye(4)), ann / "prostate.nii.gz")

    r = client.get("/api/cases/case_001/masks/1")
    assert r.status_code == 200
    body = r.json()
    assert body["shape"] == [5, 5, 5]
    assert "warnings" in body and body["warnings"]


def test_get_mask_404_when_missing(client: TestClient):
    r = client.get("/api/cases/case_002/masks/1")
    assert r.status_code == 404


def test_get_mask_synthesizes_from_png_when_configured(tmp_path: Path):
    # Build a project that declares existing_masks
    (tmp_path / "project.yaml").write_text(
        """
name: pngtest
labels:
  - id: 1
    name: prostate
    color: "#000"
sources:
  - kind: aligned
    root: data
    case_glob: "case_*"
    modalities:
      t2: t2
    existing_masks:
      prostate: mask_prostate
"""
    )
    write_dicom_series(tmp_path / "data" / "case_001" / "t2", slices=3)
    # Add PNG mask stack with one slice filled
    mask_dir = tmp_path / "data" / "case_001" / "mask_prostate"
    mask_dir.mkdir()
    from PIL import Image
    for i in range(3):
        arr = np.zeros((8, 8), dtype=np.uint8)
        if i == 1:
            arr[2, 2] = 255
        Image.fromarray(arr, mode="L").save(mask_dir / f"{i:04d}.png")

    project = load_project(tmp_path)
    client = TestClient(create_app(tmp_path, project))
    r = client.get("/api/cases/case_001/masks/1")
    assert r.status_code == 200
    vol = envelope_to_volume(r.json())
    assert vol.shape == (3, 8, 8)
    assert vol[1, 2, 2] == 1
    assert vol.sum() == 1
