import json
from pathlib import Path

from dicom_annotator.readers import build_series_manifest
from tests.conftest import write_dicom_series


def test_build_series_manifest_lists_slices_in_order(tmp_path: Path):
    series_dir = write_dicom_series(tmp_path / "s", slices=4, base_z=0.0, dz=1.0)

    manifest = build_series_manifest(series_dir, slice_url_prefix="/images/case/t2")

    assert manifest["slice_urls"] == [
        "/images/case/t2/0.dcm",
        "/images/case/t2/1.dcm",
        "/images/case/t2/2.dcm",
        "/images/case/t2/3.dcm",
    ]
    geom = manifest["reference_geometry"]
    assert geom["shape"] == [4, 8, 8]
    assert geom["spacing"] == [1.0, 1.0, 1.0]
    assert len(geom["affine"]) == 4 and len(geom["affine"][0]) == 4
