import base64
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from PIL import Image

from dicom_annotator.geometry import ReferenceGeometry
from dicom_annotator.mask_io import (
    write_mask_nifti,
    load_mask_nifti,
    volume_to_envelope,
    envelope_to_volume,
    ShapeMismatch,
    ingest_png_stack,
    PngIngestResult,
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


def _write_png(path: Path, arr: np.ndarray) -> None:
    Image.fromarray(arr.astype(np.uint8) * 255, mode="L").save(path)


def test_ingest_png_stack_exact_match(tmp_path: Path):
    png_dir = tmp_path / "mask_prostate"
    png_dir.mkdir()
    for i in range(3):
        slice_arr = np.zeros((4, 5), dtype=np.uint8)
        slice_arr[i, i] = 1
        _write_png(png_dir / f"{i:04d}.png", slice_arr)

    geom = _make_geom((3, 4, 5))
    result = ingest_png_stack(png_dir, geom)

    assert isinstance(result, PngIngestResult)
    assert result.warnings == []
    assert result.volume.shape == (3, 4, 5)
    assert result.volume.dtype == np.uint8
    assert result.volume[0, 0, 0] == 1
    assert result.volume[1, 1, 1] == 1


def test_ingest_png_stack_pads_when_fewer_pngs(tmp_path: Path):
    png_dir = tmp_path / "mask_prostate"
    png_dir.mkdir()
    for i in range(2):  # geom expects 3, only 2 PNGs
        _write_png(png_dir / f"{i:04d}.png", np.ones((4, 5), dtype=np.uint8))

    geom = _make_geom((3, 4, 5))
    result = ingest_png_stack(png_dir, geom)

    assert result.volume.shape == (3, 4, 5)
    assert result.volume[0].sum() > 0
    assert result.volume[1].sum() > 0
    assert result.volume[2].sum() == 0  # padded slice is zero
    assert any("expected 3 slices, found 2" in w for w in result.warnings)


def test_ingest_png_stack_rejects_dim_mismatch(tmp_path: Path):
    png_dir = tmp_path / "mask_prostate"
    png_dir.mkdir()
    _write_png(png_dir / "0000.png", np.zeros((10, 10), dtype=np.uint8))  # wrong rows/cols

    geom = _make_geom((1, 4, 5))
    with pytest.raises(ShapeMismatch):
        ingest_png_stack(png_dir, geom)
