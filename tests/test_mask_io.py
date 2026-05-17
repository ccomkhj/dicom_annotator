import base64
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from dicom_annotator.geometry import ReferenceGeometry
from dicom_annotator.mask_io import (
    write_mask_nifti,
    load_mask_nifti,
    volume_to_envelope,
    envelope_to_volume,
    ShapeMismatch,
)


def _make_geom(shape=(3, 4, 5)) -> ReferenceGeometry:
    affine = np.eye(4, dtype=float)
    return ReferenceGeometry(
        shape=shape,
        spacing=(1.0, 1.0, 1.0),
        affine=affine,
        slice_files=[],
    )


def test_write_and_load_nifti_roundtrips_exactly(tmp_path: Path):
    geom = _make_geom((3, 4, 5))
    volume = (np.arange(60).reshape(3, 4, 5) % 2).astype(np.uint8)
    target = tmp_path / "label.nii.gz"

    write_mask_nifti(target, volume, geom)
    loaded = load_mask_nifti(target)

    np.testing.assert_array_equal(loaded.data, volume)
    np.testing.assert_array_almost_equal(loaded.affine, geom.affine)


def test_write_mask_atomic_temp_file_is_cleaned(tmp_path: Path):
    geom = _make_geom()
    volume = np.zeros((3, 4, 5), dtype=np.uint8)
    target = tmp_path / "label.nii.gz"
    write_mask_nifti(target, volume, geom)

    # No stray temp files
    leftovers = [p for p in tmp_path.iterdir() if p.name != "label.nii.gz"]
    assert leftovers == []


def test_envelope_encodes_and_decodes_exact_bytes():
    volume = np.array([[[0, 1, 0], [1, 1, 0]]], dtype=np.uint8)
    env = volume_to_envelope(volume)
    assert env["shape"] == [1, 2, 3]
    assert env["dtype"] == "uint8"
    decoded = envelope_to_volume(env)
    np.testing.assert_array_equal(decoded, volume)


def test_envelope_rejects_wrong_shape():
    env = {
        "shape": [1, 2, 3],
        "dtype": "uint8",
        "data": base64.b64encode(b"\x00" * 7).decode("ascii"),  # wrong size
    }
    with pytest.raises(ShapeMismatch):
        envelope_to_volume(env)
