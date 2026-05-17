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


import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid


def write_dicom_slice(
    path: Path,
    image: np.ndarray,
    *,
    instance_number: int,
    image_position_patient: tuple[float, float, float],
    image_orientation_patient: tuple[float, float, float, float, float, float] = (1, 0, 0, 0, 1, 0),
    pixel_spacing: tuple[float, float] = (1.0, 1.0),
    slice_thickness: float = 1.0,
    series_instance_uid: str | None = None,
    study_instance_uid: str | None = None,
    series_description: str = "T2",
) -> Path:
    """Write a minimal valid DICOM slice file at `path`."""
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"  # MR Image Storage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = "Test"
    ds.PatientID = "TEST"
    ds.Modality = "MR"
    ds.SeriesDescription = series_description
    ds.StudyInstanceUID = study_instance_uid or generate_uid()
    ds.SeriesInstanceUID = series_instance_uid or generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.InstanceNumber = instance_number
    ds.ImagePositionPatient = list(image_position_patient)
    ds.ImageOrientationPatient = list(image_orientation_patient)
    ds.PixelSpacing = list(pixel_spacing)
    ds.SliceThickness = slice_thickness
    ds.SpacingBetweenSlices = slice_thickness
    ds.Rows, ds.Columns = image.shape
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = image.astype(np.uint16).tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(path, write_like_original=False)
    return path


def write_dicom_series(dir_path: Path, slices: int = 4, *, base_z: float = 0.0, dz: float = 2.0) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    series_uid = generate_uid()
    for i in range(slices):
        write_dicom_slice(
            dir_path / f"{i:04d}.dcm",
            image=np.zeros((8, 8), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(0.0, 0.0, base_z + i * dz),
            series_instance_uid=series_uid,
        )
    return dir_path
