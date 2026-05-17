from pathlib import Path
import pytest


@pytest.fixture
def project_yaml_text() -> str:
    return """
name: prostate-mri
labels:
  - id: 1
    name: prostate
    color: "#4FC3F7"
  - id: 2
    name: target1
    color: "#FF7043"
sources:
  - kind: aligned
    root: data/aligned
    case_glob: "case_*"
    modalities:
      t2: t2
      adc: adc
      calc: calc
    existing_masks:
      prostate: mask_prostate
      target1: mask_target1
  - kind: raw_dicom
    root: data/nbia
    case_pattern: "*/study_*/series_*"
    modality_from_header: true
""".strip()


@pytest.fixture
def project_root(tmp_path: Path, project_yaml_text: str) -> Path:
    (tmp_path / "project.yaml").write_text(project_yaml_text)
    return tmp_path
