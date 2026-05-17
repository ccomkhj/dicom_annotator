from dicom_annotator.config import load_project, Project, Label, AlignedSource, RawDicomSource


def test_load_project_parses_labels(project_root):
    project = load_project(project_root)
    assert isinstance(project, Project)
    assert project.name == "prostate-mri"
    assert project.labels == [
        Label(id=1, name="prostate", color="#4FC3F7"),
        Label(id=2, name="target1", color="#FF7043"),
    ]


def test_load_project_parses_aligned_source(project_root):
    project = load_project(project_root)
    aligned = project.sources[0]
    assert isinstance(aligned, AlignedSource)
    assert aligned.kind == "aligned"
    assert aligned.root == "data/aligned"
    assert aligned.case_glob == "case_*"
    assert aligned.modalities == {"t2": "t2", "adc": "adc", "calc": "calc"}
    assert aligned.existing_masks == {"prostate": "mask_prostate", "target1": "mask_target1"}


def test_load_project_parses_raw_dicom_source(project_root):
    project = load_project(project_root)
    raw = project.sources[1]
    assert isinstance(raw, RawDicomSource)
    assert raw.kind == "raw_dicom"
    assert raw.case_pattern == "*/study_*/series_*"
    assert raw.modality_from_header is True


def test_load_project_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path)
