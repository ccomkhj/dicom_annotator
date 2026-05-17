from pathlib import Path

from dicom_annotator.case_index import build_index, CaseEntry
from dicom_annotator.config import Project, AlignedSource, Label
from tests.conftest import make_aligned_case, make_aligned_existing_mask


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
    assert entry.labels_present == ["prostate"]


def test_index_marks_unannotated_when_no_dir(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2"])

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = index[0]
    assert entry.annotated is False
    assert entry.labels_present == []
