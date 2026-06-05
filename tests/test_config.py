from dicom_annotator.config import AlignedSource, Label, Project, RawDicomSource, load_project


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


def test_duplicate_label_ids_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Project(
            name="dup",
            labels=[Label(id=1, name="a", color="#000"), Label(id=1, name="b", color="#111")],
            sources=[],
        )


def test_duplicate_label_names_rejected():
    import pytest
    from pydantic import ValidationError

    # Same name -> same <name>.nii.gz path -> one mask would overwrite the other.
    with pytest.raises(ValidationError):
        Project(
            name="dup",
            labels=[Label(id=1, name="prostate", color="#000"), Label(id=2, name="prostate", color="#111")],
            sources=[],
        )
