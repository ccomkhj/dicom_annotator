import base64
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

from .geometry import ReferenceGeometry


class ShapeMismatch(ValueError):
    """Envelope data length does not match declared shape."""


@dataclass(frozen=True)
class LoadedMask:
    data: np.ndarray
    affine: np.ndarray


def write_mask_nifti(target: Path, volume: np.ndarray, geom: ReferenceGeometry) -> None:
    """Atomically write a uint8 volume to a gzipped NIfTI at `target`."""
    if volume.dtype != np.uint8:
        raise ValueError(f"expected uint8, got {volume.dtype}")
    if volume.shape != geom.shape:
        raise ShapeMismatch(f"volume shape {volume.shape} != geometry shape {geom.shape}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # nibabel expects (X, Y, Z) — our volume is (depth=Z, rows=Y, cols=X).
    # Transpose to (cols, rows, depth) = (X, Y, Z).
    xyz = np.transpose(volume, (2, 1, 0)).copy()
    img = nib.Nifti1Image(xyz, geom.affine)
    fd, tmp = tempfile.mkstemp(prefix=".", dir=str(target.parent), suffix=".nii.gz")
    os.close(fd)
    try:
        nib.save(img, tmp)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_mask_nifti(path: Path) -> LoadedMask:
    img = nib.load(str(path))
    xyz = np.asarray(img.dataobj).astype(np.uint8)
    # Transpose XYZ back to (depth, rows, cols)
    zyx = np.transpose(xyz, (2, 1, 0))
    return LoadedMask(data=zyx, affine=img.affine.copy())


def volume_to_envelope(volume: np.ndarray) -> dict:
    if volume.dtype != np.uint8:
        raise ValueError(f"expected uint8, got {volume.dtype}")
    if volume.ndim != 3:
        raise ValueError(f"expected 3D volume, got {volume.ndim}D")
    return {
        "shape": list(volume.shape),
        "dtype": "uint8",
        "data": base64.b64encode(volume.tobytes()).decode("ascii"),
    }


def envelope_to_volume(env: dict) -> np.ndarray:
    shape = tuple(env["shape"])
    dtype = env["dtype"]
    if dtype != "uint8":
        raise ValueError(f"unsupported dtype {dtype}")
    raw = base64.b64decode(env["data"])
    expected = int(np.prod(shape))
    if len(raw) != expected:
        raise ShapeMismatch(f"data length {len(raw)} != prod(shape) {expected}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(shape).copy()
