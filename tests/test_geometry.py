import numpy as np
from pathlib import Path

from dicom_annotator.geometry import (
    affine_from_series,
    GeometryError,
    ReferenceGeometry,
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
    # affine: x-axis col, y-axis row, z-axis slice
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [1.0, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, 1.0, 0.0])
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
    # Falls back to identity orientation + 1mm slice spacing.
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [0.66, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, 0.66, 0.0])
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
