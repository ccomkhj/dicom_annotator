from pathlib import Path

from dicom_annotator.case_index import build_index, CaseEntry
from dicom_annotator.config import Project, AlignedSource, Label, RawDicomSource
from tests.conftest import make_aligned_case


def _aligned_project(root: Path) -> Project:
    return Project(
        name="test",
        labels=[Label(id=1, name="prostate", color="#000")],
        sources=[
            AlignedSource(
                kind="aligned",
                root="data/aligned",
                case_glob="case_*",
                modalities={"t2": "t2", "adc": "adc", "calc": "calc"},
                existing_masks={"prostate": "mask_prostate"},
            )
        ],
    )


def test_index_discovers_aligned_cases(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2", "adc", "calc"])
    make_aligned_case(aligned_root, "case_002", ["t2", "adc"])
    (aligned_root / "ignored").mkdir()  # does not match case_*

    index = build_index(tmp_path, _aligned_project(tmp_path))

    ids = sorted(c.id for c in index)
    assert ids == ["case_001", "case_002"]


def test_index_reports_modalities_present(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2", "adc"])

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = index[0]
    assert isinstance(entry, CaseEntry)
    assert entry.kind == "aligned"
    assert sorted(entry.modalities) == ["adc", "t2"]


def test_index_marks_annotated_when_annotations_exist(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2"])
    ann_dir = tmp_path / "annotations" / "case_001"
    ann_dir.mkdir(parents=True)
    (ann_dir / "prostate.nii.gz").write_bytes(b"")

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = next(c for c in index if c.id == "case_001")
    assert entry.annotated is True
    assert entry.labels_present == ("prostate",)


def test_index_marks_unannotated_when_no_dir(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2"])

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = index[0]
    assert entry.annotated is False
    assert entry.labels_present == ()


def _raw_project() -> Project:
    return Project(
        name="raw",
        labels=[Label(id=1, name="prostate", color="#000")],
        sources=[
            RawDicomSource(
                kind="raw_dicom",
                root="data/nbia",
                case_pattern="*/study_*/series_*",
                modality_from_header=True,
            )
        ],
    )


def test_index_discovers_raw_dicom_as_flat_series_list(tmp_path: Path):
    # Build: data/nbia/patient1/study_01/series_a/{0.dcm,1.dcm}
    nbia = tmp_path / "data" / "nbia"
    s1 = nbia / "patient1" / "study_01" / "series_a"
    s2 = nbia / "patient1" / "study_01" / "series_b"
    s3 = nbia / "patient2" / "study_01" / "series_a"
    for s in (s1, s2, s3):
        s.mkdir(parents=True)
        (s / "0.dcm").write_bytes(b"")

    index = build_index(tmp_path, _raw_project())

    ids = sorted(c.id for c in index)
    assert ids == [
        "patient1__study_01__series_a",
        "patient1__study_01__series_b",
        "patient2__study_01__series_a",
    ]
    for entry in index:
        assert entry.kind == "raw_dicom"
        assert entry.modalities == ("series",)  # single modality slot for raw mode


def test_index_skips_empty_directories_in_raw(tmp_path: Path):
    nbia = tmp_path / "data" / "nbia"
    empty = nbia / "patient1" / "study_01" / "series_a"
    empty.mkdir(parents=True)  # no .dcm files

    index = build_index(tmp_path, _raw_project())
    assert index == []
