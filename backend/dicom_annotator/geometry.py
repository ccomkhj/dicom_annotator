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


@lru_cache(maxsize=256)
def affine_from_series(series_dir: Path) -> ReferenceGeometry:
    """Read all DICOMs in `series_dir`, order by position-along-normal, build affine."""
    files = sorted(series_dir.glob("*.dcm"))
    if not files:
        raise GeometryError(f"No .dcm files in {series_dir}")

    slices = []
    for f in files:
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        slices.append((f, ds))

    iop = np.asarray(slices[0][1].ImageOrientationPatient, dtype=float)
    row_cosine = iop[0:3]
    col_cosine = iop[3:6]
    normal = np.cross(row_cosine, col_cosine)

    def along_normal(item):
        ipp = np.asarray(item[1].ImagePositionPatient, dtype=float)
        return float(np.dot(ipp, normal))

    slices.sort(key=along_normal)
    files_sorted = [f for f, _ in slices]

    first_ds = slices[0][1]
    last_ds = slices[-1][1]
    rows = int(first_ds.Rows)
    cols = int(first_ds.Columns)
    depth = len(slices)

    ps = first_ds.PixelSpacing
    row_mm = float(ps[0])
    col_mm = float(ps[1])

    if depth > 1:
        p_first = np.asarray(first_ds.ImagePositionPatient, dtype=float)
        p_last = np.asarray(last_ds.ImagePositionPatient, dtype=float)
        slice_mm = float(np.linalg.norm(p_last - p_first) / (depth - 1))
    else:
        slice_mm = float(getattr(first_ds, "SpacingBetweenSlices", first_ds.SliceThickness or 1.0))

    affine = np.eye(4, dtype=float)
    affine[:3, 0] = row_cosine * col_mm     # column direction
    affine[:3, 1] = col_cosine * row_mm     # row direction
    affine[:3, 2] = normal * slice_mm       # slice direction
    affine[:3, 3] = np.asarray(first_ds.ImagePositionPatient, dtype=float)

    return ReferenceGeometry(
        shape=(depth, rows, cols),
        spacing=(row_mm, col_mm, slice_mm),
        affine=affine,
        slice_files=files_sorted,
    )
