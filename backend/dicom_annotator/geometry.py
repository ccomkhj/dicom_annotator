import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pydicom

logger = logging.getLogger("dicom_annotator")


class GeometryError(Exception):
    """Raised when reference geometry cannot be derived."""


@dataclass(frozen=True)
class ReferenceGeometry:
    shape: tuple[int, int, int]         # (depth, rows, cols)
    spacing: tuple[float, float, float] # (row_mm, col_mm, slice_mm)
    affine: np.ndarray                  # 4x4 NIfTI-style affine (RAS)
    slice_files: tuple[Path, ...]       # ordered by z; tuple so the lru_cache below
                                        # cannot leak a shared mutable list across callers


_DEFAULT_IOP = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@lru_cache(maxsize=256)
def affine_from_series(series_dir: Path) -> ReferenceGeometry:
    """Read all DICOMs in `series_dir`, order them, and build a reference affine.

    Prefers `ImagePositionPatient` ordering with the true `ImageOrientationPatient`.
    Falls back to `InstanceNumber` ordering with identity orientation when those
    spatial tags are missing — required for Secondary Capture series such as the
    ones produced by tcia-handler's dicom_mapper.

    Cached: assumes DICOM files on disk are write-once. If a series directory is
    rewritten in place, callers must clear `affine_from_series.cache_clear()`.
    """
    files = sorted(series_dir.glob("*.dcm"))
    if not files:
        raise GeometryError(f"No .dcm files in {series_dir}")

    slices = []
    for f in files:
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        slices.append((f, ds))

    # Any missing/invalid geometry tag becomes a GeometryError (surfaced as a
    # structured 4xx) rather than a raw AttributeError escaping as a 500.
    try:
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
            # Secondary Capture (no spatial tags): order by InstanceNumber.
            def order_key(item):
                return int(getattr(item[1], "InstanceNumber", 0))

        slices.sort(key=order_key)
        files_sorted = tuple(f for f, _ in slices)

        first_ds = slices[0][1]
        rows = int(first_ds.Rows)
        cols = int(first_ds.Columns)
        depth = len(slices)

        ps = first_ds.PixelSpacing
        row_mm = float(ps[0])
        col_mm = float(ps[1])

        if has_ipp and depth > 1:
            # Per-slice gaps along the normal (slices are already sorted by it).
            projs = np.array([
                float(np.dot(np.asarray(s[1].ImagePositionPatient, dtype=float), normal))
                for s in slices
            ])
            gaps = np.diff(projs)
            slice_mm = float(gaps.mean())  # == (proj[-1]-proj[0])/(depth-1) for uniform
            # The affine assumes uniform spacing; warn (don't fail) if it isn't,
            # e.g. gated/dynamic acquisitions — the saved mask would be distorted.
            if depth > 2:
                spread = float(gaps.max() - gaps.min())
                if spread > 1e-2 and abs(slice_mm) > 0 and spread > 0.01 * abs(slice_mm):
                    logger.warning(
                        "non-uniform slice spacing in %s: gaps min=%.3f max=%.3f mean=%.3f",
                        series_dir, float(gaps.min()), float(gaps.max()), slice_mm,
                    )
        else:
            # Single-slice or Secondary Capture: fall back lazily
            # SpacingBetweenSlices -> SliceThickness -> 1.0. (getattr args are
            # eager, so a one-liner crashes when SliceThickness is absent.)
            spacing = getattr(first_ds, "SpacingBetweenSlices", None)
            if spacing is None:
                spacing = getattr(first_ds, "SliceThickness", None)
            slice_mm = float(spacing) if spacing else 1.0

        origin = (
            np.asarray(first_ds.ImagePositionPatient, dtype=float)
            if has_ipp
            else np.zeros(3, dtype=float)
        )
    except (AttributeError, KeyError, ValueError, TypeError, IndexError) as e:
        raise GeometryError(f"missing/invalid DICOM geometry tag in {series_dir}: {e}") from e

    affine = np.eye(4, dtype=float)
    affine[:3, 0] = row_cosine * col_mm     # column direction
    affine[:3, 1] = col_cosine * row_mm     # row direction
    affine[:3, 2] = normal * slice_mm       # slice direction
    affine[:3, 3] = origin
    # DICOM patient coordinates are LPS; NIfTI/RAS negates the X (L->R) and
    # Y (P->A) physical axes. Apply diag(-1,-1,1,1) on the left (negate rows 0,1
    # including the translation) so exported masks open correctly in
    # Slicer/FSL/ITK. The write/read round-trip in mask_io is unaffected.
    affine[0, :] *= -1.0
    affine[1, :] *= -1.0

    return ReferenceGeometry(
        shape=(depth, rows, cols),
        spacing=(row_mm, col_mm, slice_mm),
        affine=affine,
        slice_files=files_sorted,
    )
