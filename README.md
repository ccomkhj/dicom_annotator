# dicom_annotator

Local DICOM segmentation annotator. FastAPI backend + Cornerstone3D browser frontend.

See [design](docs/superpowers/specs/2026-05-17-dicom-annotator-design.md).

## Run

### Backend

```bash
uv sync --extra dev
uv run dicom-annotator serve --project /path/to/project_root
```

The project root must contain a `project.yaml` (see below) and source data directories.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` and `/images` to the backend on port 8000.

## Tests

```bash
uv run pytest
```

## Layout

- `backend/dicom_annotator/` — FastAPI app, readers, mask I/O
- `frontend/src/` — TypeScript + Cornerstone3D viewer
- `docs/superpowers/specs/` — design
- `docs/superpowers/plans/` — implementation plan

## Project file

Example `project.yaml`:

```yaml
name: my-project
labels:
  - id: 1
    name: prostate
    color: "#4FC3F7"
  - id: 2
    name: target1
    color: "#FF7043"
sources:
  - kind: aligned
    root: data/aligned
    case_glob: "case_*"
    modalities:
      t2: t2
      adc: adc
      calc: calc
    existing_masks:
      prostate: mask_prostate
      target1: mask_target1
  - kind: raw_dicom
    root: data/nbia
    case_pattern: "*/study_*/series_*"
    modality_from_header: true
```

Masks save to `<project_root>/annotations/<case_id>/<label_name>.nii.gz`.

## Keyboard shortcuts

- `b` brush · `e` erase · `p` polygon · `1`–`9` switch label
- `[` / `]` adjust brush size
- `PageUp` / `PageDown` previous / next case
- `Ctrl+S` (or `Cmd+S` on macOS) save masks
