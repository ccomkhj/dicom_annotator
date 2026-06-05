from pathlib import Path

import numpy as np

from dicom_annotator.geometry import (
    GeometryError,
    ReferenceGeometry,
    affine_from_series,
)
from tests.conftest import (
    write_dicom_series,
    write_dicom_slice,
    write_secondary_capture_series,
    write_secondary_capture_slice,
)


def test_affine_from_series_unit_spacing(tmp_path: Path):
    series_dir = write_dicom_series(tmp_path / "s", slices=4, base_z=0.0, dz=1.0)

    geom = affine_from_series(series_dir)

    assert isinstance(geom, ReferenceGeometry)
    assert geom.shape == (4, 8, 8)          # (depth, rows, cols)
    assert geom.spacing == (1.0, 1.0, 1.0)  # (row, col, slice)
    # DICOM is LPS; the affine is converted to RAS, flipping the X and Y axes.
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [-1.0, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, -1.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 2], [0.0, 0.0, 1.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 3], [0.0, 0.0, 0.0])


def test_affine_from_series_anisotropic_spacing(tmp_path: Path):
    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    for i in range(3):
        write_dicom_slice(
            series_dir / f"{i:04d}.dcm",
            image=np.zeros((4, 6), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(0.0, 0.0, i * 3.0),
            pixel_spacing=(0.5, 0.75),
            slice_thickness=3.0,
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    assert geom.shape == (3, 4, 6)
    assert geom.spacing == (0.5, 0.75, 3.0)


def test_affine_converts_lps_to_ras(tmp_path: Path):
    """DICOM patient coords are LPS; the affine must flip X and Y to RAS so
    exported NIfTI opens correctly in Slicer/FSL/ITK. The translation column
    (origin) is flipped along with the direction columns."""
    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    # Non-zero in-plane origin so the row-negation of the translation is exercised.
    for i in range(3):
        write_dicom_slice(
            series_dir / f"{i:04d}.dcm",
            image=np.zeros((4, 4), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(10.0, 20.0, float(i)),
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    # X and Y direction columns are negated; Z (slice) is unchanged.
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [-1.0, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, -1.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 2], [0.0, 0.0, 1.0])
    # Origin: LPS (10, 20, 0) -> RAS (-10, -20, 0).
    np.testing.assert_array_almost_equal(geom.affine[:3, 3], [-10.0, -20.0, 0.0])


def test_affine_non_axial_orientation(tmp_path: Path):
    """Lock the cross-product normal + RAS conversion for a non-axial (coronal)
    acquisition — the case where geometry bugs usually hide."""
    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    # Coronal: row along +X, column along -Z  => normal along +Y, slices step in Y.
    iop = (1, 0, 0, 0, 0, -1)
    for i in range(3):
        write_dicom_slice(
            series_dir / f"{i:04d}.dcm",
            image=np.zeros((4, 6), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(0.0, i * 2.0, 0.0),
            image_orientation_patient=iop,
            pixel_spacing=(0.5, 0.75),  # (row_mm, col_mm)
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    assert geom.spacing == (0.5, 0.75, 2.0)
    # Pre-RAS columns: col=row_cosine*col_mm, row=col_cosine*row_mm, slice=normal*slice_mm.
    # Then rows 0,1 are negated (LPS->RAS).
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [-0.75, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, 0.0, -0.5])
    np.testing.assert_array_almost_equal(geom.affine[:3, 2], [0.0, -2.0, 0.0])


def test_affine_orders_slices_by_z(tmp_path: Path):
    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    # Write in reverse order; InstanceNumber unrelated to filesystem order
    for fname, inst, z in [("a.dcm", 3, 2.0), ("b.dcm", 1, 0.0), ("c.dcm", 2, 1.0)]:
        write_dicom_slice(
            series_dir / fname,
            image=np.zeros((4, 4), dtype=np.uint16),
            instance_number=inst,
            image_position_patient=(0.0, 0.0, z),
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    assert geom.slice_files[0].name == "b.dcm"  # z=0.0
    assert geom.slice_files[1].name == "c.dcm"  # z=1.0
    assert geom.slice_files[2].name == "a.dcm"  # z=2.0


def test_non_uniform_spacing_warns(tmp_path: Path, caplog):
    """Gated/dynamic series with uneven inter-slice gaps still build an affine but
    must emit a warning (the affine assumes uniform spacing)."""
    import logging

    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    for i, z in enumerate([0.0, 1.0, 5.0]):  # gaps 1.0 then 4.0 — non-uniform
        write_dicom_slice(
            series_dir / f"{i:04d}.dcm",
            image=np.zeros((4, 4), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(0.0, 0.0, z),
            series_instance_uid=uid,
        )

    with caplog.at_level(logging.WARNING, logger="dicom_annotator"):
        affine_from_series(series_dir)
    assert any("non-uniform slice spacing" in r.message for r in caplog.records)


def test_affine_raises_on_empty_dir(tmp_path: Path):
    import pytest
    (tmp_path / "empty").mkdir()
    with pytest.raises(GeometryError):
        affine_from_series(tmp_path / "empty")


def test_affine_handles_secondary_capture_without_spatial_tags(tmp_path: Path):
    series_dir = write_secondary_capture_series(
        tmp_path / "sc", slices=5, pixel_spacing=(0.66, 0.66)
    )

    geom = affine_from_series(series_dir)

    assert geom.shape == (5, 8, 8)
    # Falls back to identity orientation + 1mm slice spacing. Identity IOP is
    # axis-aligned, so the LPS->RAS flip negates the X and Y direction columns.
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [-0.66, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, -0.66, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 2], [0.0, 0.0, 1.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 3], [0.0, 0.0, 0.0])
    assert geom.spacing == (0.66, 0.66, 1.0)


def test_affine_orders_secondary_capture_by_instance_number(tmp_path: Path):
    series_dir = tmp_path / "sc"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    # Filenames lex-sort to "a, b, c" but InstanceNumber order is b, c, a.
    for fname, inst in [("a.dcm", 3), ("b.dcm", 1), ("c.dcm", 2)]:
        write_secondary_capture_slice(
            series_dir / fname,
            image=np.zeros((4, 4), dtype=np.uint16),
            instance_number=inst,
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    assert [p.name for p in geom.slice_files] == ["b.dcm", "c.dcm", "a.dcm"]


def test_affine_raises_geometryerror_on_missing_pixel_spacing(tmp_path: Path):
    """A malformed DICOM (missing PixelSpacing) must raise GeometryError (a
    structured 4xx), not a raw AttributeError that escapes as a 500. (Missing
    orientation/position is handled by the Secondary-Capture fallback instead.)"""
    import pydicom
    import pytest

    series_dir = write_dicom_series(tmp_path / "s", slices=2)
    bad = series_dir / "0000.dcm"
    ds = pydicom.dcmread(bad)
    del ds.PixelSpacing
    ds.save_as(bad, enforce_file_format=True)

    with pytest.raises(GeometryError):
        affine_from_series(series_dir)


def test_affine_single_slice_without_slice_thickness(tmp_path: Path):
    """Single-slice series missing SliceThickness must not crash (eager-getattr
    regression) — it falls back to 1.0 mm slice spacing."""
    import pydicom

    series_dir = write_dicom_series(tmp_path / "s", slices=1)
    only = series_dir / "0000.dcm"
    ds = pydicom.dcmread(only)
    if "SpacingBetweenSlices" in ds:
        del ds.SpacingBetweenSlices
    if "SliceThickness" in ds:
        del ds.SliceThickness
    ds.save_as(only, enforce_file_format=True)

    geom = affine_from_series(series_dir)
    assert geom.shape == (1, 8, 8)
    assert geom.spacing[2] == 1.0
