from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pydicom


class GeometryError(Exception):
    """Raised when reference geometry cannot be derived."""


@dataclass(frozen=True)
class ReferenceGeometry:
    shape: tuple[int, int, int]         # (depth, rows, cols)
    spacing: tuple[float, float, float] # (row_mm, col_mm, slice_mm)
    affine: np.ndarray                  # 4x4 NIfTI-style affine (RAS)
    slice_files: list[Path]             # ordered by z


_DEFAULT_IOP = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@lru_cache(maxsize=256)
def affine_from_series(series_dir: Path) -> ReferenceGeometry:
    """Read all DICOMs in `series_dir`, order them, and build a reference affine.

    Prefers `ImagePositionPatient` ordering with the true `ImageOrientationPatient`.
    Falls back to `InstanceNumber` ordering with identity orientation when those
    spatial tags are missing — required for Secondary Capture series such as the
    ones produced by tcia-handler's dicom_mapper.
    """
    files = sorted(series_dir.glob("*.dcm"))
    if not files:
        raise GeometryError(f"No .dcm files in {series_dir}")

    slices = []
    for f in files:
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        slices.append((f, ds))

    probe = slices[0][1]
    has_iop = "ImageOrientationPatient" in probe
    has_ipp = "ImagePositionPatient" in probe

    iop = np.asarray(probe.ImageOrientationPatient if has_iop else _DEFAULT_IOP, dtype=float)
    row_cosine = iop[0:3]
    col_cosine = iop[3:6]
    normal = np.cross(row_cosine, col_cosine)

    if has_ipp:
        def order_key(item):
            ipp = np.asarray(item[1].ImagePositionPatient, dtype=float)
            return float(np.dot(ipp, normal))
    else:
        def order_key(item):
            return int(getattr(item[1], "InstanceNumber", 0))

    slices.sort(key=order_key)
    files_sorted = [f for f, _ in slices]

    first_ds = slices[0][1]
    last_ds = slices[-1][1]
    rows = int(first_ds.Rows)
    cols = int(first_ds.Columns)
    depth = len(slices)

    ps = first_ds.PixelSpacing
    row_mm = float(ps[0])
    col_mm = float(ps[1])

    if has_ipp and depth > 1:
        p_first = np.asarray(first_ds.ImagePositionPatient, dtype=float)
        p_last = np.asarray(last_ds.ImagePositionPatient, dtype=float)
        slice_mm = float(np.linalg.norm(p_last - p_first) / (depth - 1))
    else:
        slice_mm = float(
            getattr(first_ds, "SpacingBetweenSlices", None)
            or getattr(first_ds, "SliceThickness", None)
            or 1.0
        )

    origin = (
        np.asarray(first_ds.ImagePositionPatient, dtype=float)
        if has_ipp
        else np.zeros(3, dtype=float)
    )

    affine = np.eye(4, dtype=float)
    affine[:3, 0] = row_cosine * col_mm     # column direction
    affine[:3, 1] = col_cosine * row_mm     # row direction
    affine[:3, 2] = normal * slice_mm       # slice direction
    affine[:3, 3] = origin

    return ReferenceGeometry(
        shape=(depth, rows, cols),
        spacing=(row_mm, col_mm, slice_mm),
        affine=affine,
        slice_files=files_sorted,
    )
