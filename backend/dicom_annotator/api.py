from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import errors
from .case_index import CaseEntry, build_index
from .config import Project
from .geometry import affine_from_series, GeometryError


def create_app(project_root: Path, project: Project) -> FastAPI:
    app = FastAPI(title="dicom_annotator")
    state: dict = {"index": build_index(project_root, project)}

    def find_case(case_id: str) -> CaseEntry:
        for c in state["index"]:
            if c.id == case_id:
                return c
        raise errors.case_not_found(case_id)

    @app.exception_handler(errors.ApiError)
    async def _api_error_handler(request: Request, exc: errors.ApiError):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    @app.get("/api/project")
    def get_project():
        return project.model_dump()

    @app.get("/api/cases")
    def get_cases():
        return [
            {
                "id": c.id,
                "kind": c.kind,
                "modalities": c.modalities,
                "annotated": c.annotated,
                "labels_present": c.labels_present,
            }
            for c in state["index"]
        ]

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str):
        c = find_case(case_id)
        source = project.sources[c.source_index]
        # Resolve modality key -> subdir name for aligned sources.
        # For raw_dicom, the "modality" is always "series" and the case_dir IS the series.
        if c.kind == "aligned":
            mod_to_subdir = source.modalities  # dict[str, str]
            ref_mod = "t2" if "t2" in c.modalities else c.modalities[0]
            ref_dir = c.case_dir / mod_to_subdir[ref_mod]
        else:
            ref_dir = c.case_dir

        try:
            geom = affine_from_series(ref_dir)
        except GeometryError as e:
            raise errors.geometry_error(str(e))

        if c.kind == "aligned":
            modality_files = {
                mod: [
                    str(p.relative_to(project_root))
                    for p in sorted((c.case_dir / mod_to_subdir[mod]).glob("*.dcm"))
                ]
                for mod in c.modalities
                if (c.case_dir / mod_to_subdir[mod]).is_dir()
            }
        else:
            modality_files = {
                "series": [str(p.relative_to(project_root)) for p in sorted(c.case_dir.glob("*.dcm"))]
            }

        return {
            "id": c.id,
            "kind": c.kind,
            "modalities": c.modalities,
            "slice_count": geom.shape[0],
            "reference_shape": list(geom.shape),
            "reference_affine": geom.affine.tolist(),
            "modality_files": modality_files,
        }

    from fastapi.responses import FileResponse
    from .readers import build_series_manifest

    def _modality_dir(c: CaseEntry, modality: str) -> Path:
        if c.kind == "aligned":
            if modality not in c.modalities:
                raise errors.ApiError(404, "modality_not_found",
                                      f"case {c.id} has no modality {modality!r}",
                                      case_id=c.id, modality=modality)
            source = project.sources[c.source_index]
            return c.case_dir / source.modalities[modality]
        # raw_dicom: only "series" modality
        if modality != "series":
            raise errors.ApiError(404, "modality_not_found",
                                  f"raw case {c.id} only exposes 'series'",
                                  case_id=c.id, modality=modality)
        return c.case_dir

    @app.get("/images/{case_id}/{modality}/manifest.json")
    def image_manifest(case_id: str, modality: str):
        c = find_case(case_id)
        mod_dir = _modality_dir(c, modality)
        try:
            return build_series_manifest(mod_dir, slice_url_prefix=f"/images/{case_id}/{modality}")
        except GeometryError as e:
            raise errors.geometry_error(str(e))

    @app.get("/images/{case_id}/{modality}/{slice_idx}.dcm")
    def image_slice(case_id: str, modality: str, slice_idx: int):
        c = find_case(case_id)
        mod_dir = _modality_dir(c, modality)
        try:
            geom = affine_from_series(mod_dir)
        except GeometryError as e:
            raise errors.geometry_error(str(e))
        if slice_idx < 0 or slice_idx >= len(geom.slice_files):
            raise errors.ApiError(404, "slice_out_of_range",
                                  f"slice {slice_idx} out of range [0,{len(geom.slice_files)})",
                                  slice_idx=slice_idx)
        return FileResponse(geom.slice_files[slice_idx], media_type="application/dicom")

    @app.get("/api/health")
    def health():
        return {"ok": True, "project_root": str(project_root), "case_count": len(state["index"])}

    @app.post("/api/refresh")
    def refresh():
        state["index"] = build_index(project_root, project)
        return {"ok": True, "case_count": len(state["index"])}

    from pydantic import BaseModel
    from .config import AlignedSource
    from .mask_io import (
        write_mask_nifti,
        load_mask_nifti,
        volume_to_envelope,
        envelope_to_volume,
        ingest_png_stack,
        ShapeMismatch,
    )
    import hashlib, json, time

    class MaskEnvelope(BaseModel):
        shape: list[int]
        dtype: str
        data: str

    def _annotations_path(case_id: str, label_name: str) -> Path:
        return project_root / "annotations" / case_id / f"{label_name}.nii.gz"

    def _label_by_id(label_id: int):
        for lbl in project.labels:
            if lbl.id == label_id:
                return lbl
        raise errors.label_unknown(label_id)

    def _ref_geom_for(c: CaseEntry):
        if c.kind == "aligned":
            source = project.sources[c.source_index]
            ref_mod = "t2" if "t2" in c.modalities else c.modalities[0]
            ref_dir = c.case_dir / source.modalities[ref_mod]
        else:
            ref_dir = c.case_dir
        return affine_from_series(ref_dir)

    @app.get("/api/cases/{case_id}/masks/{label_id}")
    def get_mask(case_id: str, label_id: int):
        c = find_case(case_id)
        label = _label_by_id(label_id)
        nifti_path = _annotations_path(case_id, label.name)
        if nifti_path.exists():
            loaded = load_mask_nifti(nifti_path)
            return volume_to_envelope(loaded.data)

        # Try PNG-stack ingest if source is aligned + existing_masks configured
        source = project.sources[c.source_index]
        if isinstance(source, AlignedSource) and label.name in source.existing_masks:
            png_dir = c.case_dir / source.existing_masks[label.name]
            if png_dir.is_dir() and any(png_dir.glob("*.png")):
                geom = _ref_geom_for(c)
                result = ingest_png_stack(png_dir, geom)
                return volume_to_envelope(result.volume) | {"warnings": result.warnings}

        raise errors.ApiError(404, "mask_not_found",
                              f"no mask for {case_id}/{label.name}",
                              case_id=case_id, label=label.name)

    @app.put("/api/cases/{case_id}/masks/{label_id}")
    def put_mask(case_id: str, label_id: int, env: MaskEnvelope):
        c = find_case(case_id)
        label = _label_by_id(label_id)
        try:
            volume = envelope_to_volume(env.model_dump())
        except ShapeMismatch as e:
            raise errors.shape_mismatch(env.shape, env.shape)
        try:
            geom = _ref_geom_for(c)
        except GeometryError as e:
            raise errors.geometry_error(str(e))
        if volume.shape != geom.shape:
            raise errors.shape_mismatch(geom.shape, volume.shape)
        target = _annotations_path(case_id, label.name)
        write_mask_nifti(target, volume, geom)
        sha = hashlib.sha256(target.read_bytes()).hexdigest()
        meta_path = target.parent / "meta.json"
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        meta.setdefault("labels", {})[label.name] = {
            "last_modified": time.time(),
            "sha256": sha,
        }
        meta["reference_shape"] = list(geom.shape)
        meta_path.write_text(json.dumps(meta, indent=2))
        # Refresh case index entry for annotated state.
        state["index"] = build_index(project_root, project)
        return {"saved_at": meta["labels"][label.name]["last_modified"],
                "bytes": target.stat().st_size,
                "sha256": sha}

    return app
