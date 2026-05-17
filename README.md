# dicom_annotator

Local DICOM segmentation annotator. FastAPI backend + Cornerstone3D browser frontend.

See [design](docs/superpowers/specs/2026-05-17-dicom-annotator-design.md).

## UI

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ dicom_annotator — <project name>           [◀ Prev] [Next ▶] ●dirty  [Save]  │
├────────────┬───────────────────────────────────────────────┬─────────────────┤
│ Cases      │ ┌──────────────┬──────────────┬──────────────┐│ Tools           │
│ ✔ case_001 │ │              │              │              ││ ┌────┐ ┌─────┐  │
│ ○ case_002 │ │      T2      │     ADC      │     Calc     ││ │Brush│ │Erase│  │
│ ○ case_003 │ │              │              │              ││ ├────┤ ├─────┤  │
│ ✔ case_004 │ │              │              │              ││ │Rect│ │ Pan │  │
│ ✔ class1_  │ │              │              │              ││ └────┘ └─────┘  │
│   case_144 │ └──────────────┴──────────────┴──────────────┘│ Brush size: 6   │
│ …          │ [|━━━━●━━━━━━━━━━━━━━━━━━━━━] slice 24/60     │ ▬▬▬●▬▬▬▬        │
│            │                                                │ Labels          │
│            │                                                │ ■ prostate (1)  │
│            │                                                │ □ target1  (2)  │
└────────────┴───────────────────────────────────────────────┴─────────────────┘
```

Left rail: case list (✔ = annotated, ○ = pending). Center: three synchronized
viewports (T2 / ADC / Calc) over a slice scrubber. Right rail: tool buttons,
brush size, and the label palette. Topbar exposes Prev/Next, a dirty indicator,
and Save.

> **Note:** A live PNG capture of the running UI is pending — the frontend has
> a pre-existing Cornerstone3D init issue (UMD `@cornerstonejs/dicom-image-loader`
> needs `window.dicomParser` set before module evaluation, and `csCoreInit`
> doesn't fully initialise the core). Track that separately; it's not in scope
> for the dataset-support changes in this branch.

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

`case_glob` may include directory separators — e.g. `"class*/case_*"` discovers
cases under nested class subdirectories. The case ID then becomes the relative
path with `__` separators (`class1__case_0001`), which keeps IDs unique across
classes and is also the directory name used under `annotations/`.

`source.root` may be an absolute path; this lets you point a project at a
dataset that lives outside the project directory (e.g. a sibling tcia-handler
checkout).

Masks save to `<project_root>/annotations/<case_id>/<label_name>.nii.gz`.

## Running against the tcia-handler aligned_v2 dataset

The `tcia-handler` project (sibling repo) produces aligned multi-modal MRI
volumes at `data/aligned_v2/class{N}/case_{XXXX}/{t2,adc,calc}_aligned/` plus
PNG mask stacks at `mask_prostate/` and `mask_target1/`. Those `.dcm` files are
Secondary Capture (no `ImageOrientationPatient`/`ImagePositionPatient`); the
annotator falls back to `InstanceNumber`-ordered identity geometry, which is
correct for the resampled-to-T2 reference space the pipeline produces.

A ready-made project file is at
[`docs/examples/tcia-aligned-v2.project.yaml`](docs/examples/tcia-aligned-v2.project.yaml).
Copy it to any directory you want annotations written to and serve it:

```bash
mkdir -p ~/work/tcia-annotator
cp docs/examples/tcia-aligned-v2.project.yaml ~/work/tcia-annotator/project.yaml
uv run dicom-annotator serve --project ~/work/tcia-annotator
```

Edit the `root:` line in the copy if your `tcia-handler` checkout lives
elsewhere. Existing PNG masks under `mask_prostate/` / `mask_target1/` are
ingested on first load and re-saved as NIfTI on first save.

## Keyboard shortcuts

- `b` brush · `e` erase · `p` polygon · `1`–`9` switch label
- `[` / `]` adjust brush size
- `PageUp` / `PageDown` previous / next case
- `Ctrl+S` (or `Cmd+S` on macOS) save masks
