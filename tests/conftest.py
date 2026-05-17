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


def make_aligned_case(root: Path, case_id: str, modalities: list[str], slice_count: int = 3) -> Path:
    """Create an aligned-case dir with empty modality subdirs and N dummy .dcm files each."""
    case_dir = root / case_id
    for mod in modalities:
        mod_dir = case_dir / mod
        mod_dir.mkdir(parents=True, exist_ok=True)
        for i in range(slice_count):
            (mod_dir / f"{i:04d}.dcm").write_bytes(b"")
    return case_dir


def make_aligned_existing_mask(case_dir: Path, mask_subdir: str, slice_count: int) -> Path:
    """Create an existing-mask PNG-stack subdir under a case."""
    mask_dir = case_dir / mask_subdir
    mask_dir.mkdir(parents=True, exist_ok=True)
    for i in range(slice_count):
        (mask_dir / f"{i:04d}.png").write_bytes(b"")
    return mask_dir
