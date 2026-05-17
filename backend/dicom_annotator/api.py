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

    return app
