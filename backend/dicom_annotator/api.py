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
        # Use first modality's directory for reference geometry.
        # For aligned cases the reference modality is t2 by convention; we pick
        # whichever modality is present and named "t2", else first-listed.
        ref_mod = "t2" if "t2" in c.modalities else c.modalities[0]
        ref_dir = c.case_dir / ref_mod if c.kind == "aligned" else c.case_dir
        try:
            geom = affine_from_series(ref_dir)
        except GeometryError as e:
            raise errors.geometry_error(str(e))
        return {
            "id": c.id,
            "kind": c.kind,
            "modalities": c.modalities,
            "slice_count": geom.shape[0],
            "reference_shape": list(geom.shape),
            "reference_affine": geom.affine.tolist(),
            "modality_files": {
                mod: [
                    str(p.relative_to(project_root))
                    for p in sorted((c.case_dir / mod).glob("*.dcm"))
                ]
                for mod in c.modalities
                if (c.case_dir / mod).is_dir()
            } if c.kind == "aligned" else {"series": [str(p.relative_to(project_root)) for p in sorted(c.case_dir.glob("*.dcm"))]},
        }

    @app.get("/api/health")
    def health():
        return {"ok": True, "project_root": str(project_root), "case_count": len(state["index"])}

    @app.post("/api/refresh")
    def refresh():
        state["index"] = build_index(project_root, project)
        return {"ok": True, "case_count": len(state["index"])}

    return app
