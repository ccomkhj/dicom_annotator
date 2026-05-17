from pathlib import Path

from .geometry import affine_from_series


def build_series_manifest(series_dir: Path, slice_url_prefix: str) -> dict:
    """Build the manifest the frontend feeds to Cornerstone's volume loader.

    `slice_url_prefix` is the URL prefix the client will use to fetch slice bytes;
    actual byte serving happens via the FastAPI image route.
    """
    geom = affine_from_series(series_dir)
    slice_urls = [f"{slice_url_prefix}/{i}.dcm" for i in range(len(geom.slice_files))]
    return {
        "slice_urls": slice_urls,
        "reference_geometry": {
            "shape": list(geom.shape),
            "spacing": list(geom.spacing),
            "affine": geom.affine.tolist(),
        },
    }
