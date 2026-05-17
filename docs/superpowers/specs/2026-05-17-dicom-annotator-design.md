# dicom_annotator — design

**Status:** Approved (brainstorm). Pending implementation plan.
**Date:** 2026-05-17

## Goal

A CVAT-like, browser-based annotation tool for DICOM datasets and segmentation masks, scoped to a single local user. Targets the kind of multi-modal MRI data produced by the `tcia-handler` pipeline (T2, ADC, Calc + per-label binary masks). Supports two workflows:

- **Review & correct** existing masks (e.g., the PNG masks emitted by `tcia-handler`).
- **Annotate from scratch** on raw DICOM where no mask exists yet.

The canonical mask format produced by the tool is **NIfTI** (`.nii.gz`), one volume per label per case.

## Non-goals (v1)

- Multi-user, auth, role-based review workflow, task queues.
- Full 3D editing (three orthogonal views, 3D brush). Annotation is 2D-slice with thumbnail navigation and slice propagation.
- Smart segmentation (SAM, region grow, level sets). Tools v1: brush, eraser, polygon/lasso, slice propagation.
- Cross-modality alignment for raw DICOM. Raw mode shows one series at a time; aligned multi-modal view is for `aligned_v2`-style outputs.
- E2E browser tests, performance optimization, cross-browser support beyond latest Chrome/Firefox.
- DICOM-SEG output, COCO/YOLO export. NIfTI only; conversions are external scripts.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (one tab)                                           │
│    Frontend (TypeScript + Vite + Cornerstone3D)              │
│      · 3-pane synchronized viewport (T2 | ADC | Calc)        │
│      · Cornerstone tools: Brush, Eraser, PolygonScissor      │
│      · Cornerstone Segmentation state (in-memory labelmap)   │
│      · Custom widgets: slice scrubber, label panel,          │
│        propagate-from-previous-slice, save/dirty indicator   │
└──────────────────────▲────────────────────┬──────────────────┘
                       │ DICOM bytes        │ NIfTI labelmap
                       │ case metadata      │ shape envelope
                       ▼                    ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI backend (Python 3.11+, uvicorn, uv-managed)         │
│   modules:                                                   │
│   · case_index   scan project dir, cache case list           │
│   · readers      pydicom (raw), Pillow (PNG), nibabel (Nf)   │
│   · mask_io      PNG-stack ↔ NIfTI ↔ raw-bytes envelope      │
│   · geometry     DICOM headers → reference affine            │
│   · api          FastAPI routes (see § API surface)          │
└──────────────────────▲───────────────────────────────────────┘
                       │ filesystem only (no DB)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Project root (user-pointed)                                 │
│   project.yaml                                               │
│   data/...           sources, read-only                      │
│   annotations/       NEW — annotator writes here             │
└──────────────────────────────────────────────────────────────┘
```

### Key separations

- **Source data is read-only.** The annotator only ever writes under `<project_root>/annotations/`. It can safely point at an existing `tcia-handler` workspace.
- **Frontend owns interactive segmentation state**, backend owns persistence + image I/O. Cornerstone's labelmap volume lives in browser memory while editing; complete labels are flushed to disk on save.
- **No database.** Project shape lives in `project.yaml`. Case discovery is by filesystem scan into an in-memory index, rebuilt on backend start; `POST /api/refresh` rescans without a restart.
- **NIfTI on the wire** between server and browser uses a thin shape envelope (`{shape, dtype, data}`) rather than a fully-formed NIfTI from JS. The backend owns NIfTI construction with `nibabel` to avoid affine/endianness mistakes in the browser.

### Dependencies

- **Python (uv):** `fastapi`, `uvicorn`, `pydicom`, `nibabel`, `numpy`, `Pillow`, `pydantic`.
- **JS (pnpm/npm via Vite):** `@cornerstonejs/core`, `@cornerstonejs/tools`, `@cornerstonejs/dicom-image-loader`, `vite`, `typescript`.

## On-disk data model

### `project.yaml`

```yaml
name: prostate-mri-correction
labels:                          # order = display order; id = labelmap value
  - id: 1
    name: prostate
    color: "#4FC3F7"
  - id: 2
    name: target1
    color: "#FF7043"

sources:
  - kind: aligned                # multi-modal aligned per-case dirs
    root: data/aligned_v2_sample/sample
    case_glob: "case_*"
    modalities:                  # subdir name per modality
      t2: t2
      adc: adc
      calc: calc
    existing_masks:              # optional: pre-existing PNG masks to ingest
      prostate: mask_prostate
      target1: mask_target1

  - kind: raw_dicom              # raw DICOM series — flat series list
    root: data/nbia
    case_pattern: "*/study_*/series_*"
    modality_from_header: true   # derived from DICOM SeriesDescription
```

Two `kind` values cover the `tcia-handler` layout. `raw_dicom` cases display one series at a time (no cross-modality view).

### Annotation output

```
<project_root>/annotations/
├── <case_id>/
│   ├── <label_name>.nii.gz      one binary mask volume per label
│   └── meta.json                geometry source, sha256, last_modified
```

- Binary masks, `uint8` (0 or 1), one NIfTI per label per case.
- The reference affine is derived from the **reference modality** (T2 for aligned cases; the chosen series for raw cases) and stamped into both the NIfTI header and `meta.json`.

### Case state — implicit

No status field. A case is "annotated" iff any file exists under `annotations/<case_id>/`. The UI shows ✔ / ○ based on file existence. Per-label presence is read from which `<label>.nii.gz` files are there.

### PNG-to-NIfTI ingest

When opening a case with no NIfTI for a given label but `existing_masks` configured in the source, the backend assembles the PNG stack into a volume aligned to the reference geometry and returns it as the initial labelmap. The original PNGs are never modified; after the user saves, the NIfTI under `annotations/` is the source of truth.

**Slice-count mismatch handling:** if the PNG stack has fewer slices than the reference, pad missing slices with zeros and surface a warning banner in the UI. The backend never silently truncates.

## UI layout

Three-column shell:

- **Left (200 px):** case list with ✔/○ markers and a filter input.
- **Centre (flex):** top row of three equal-sized synchronized viewports (T2 / ADC / Calc) with windowing, zoom, pan synced; slice scrubber below with current-slice indicator and a "Propagate from slice N-1" button; horizontal label panel below the scrubber showing label color, name, id, visibility, and active-label state.
- **Right (180 px):** tool palette (Brush, Eraser, Polygon, Lasso, Pan, Zoom), brush size slider, W/L readout, keyboard shortcut cheat-sheet.

Top bar: project name, current case with position counter (e.g., `12 / 47`), Prev/Save/Next buttons, dirty-state dot indicating unsaved changes.

### Interaction expectations

- Synchronized scroll/zoom/pan across the three viewports.
- Active label highlighted in the label panel; brush paints that label's value into the Cornerstone labelmap.
- Slice propagation is frontend-only: copies the active label's labelmap slice from `z = current-1` to `z = current`.
- Save (`Ctrl+S` or button): for each label, send the current labelmap volume to `PUT /api/cases/{id}/masks/{label_id}`. Show toast on success/failure. Clear dirty dot on success.
- Navigating away with unsaved changes triggers a browser confirmation.
- No autosave in v1.

## HTTP API surface

All JSON unless noted. Project root is passed as a CLI arg (`uv run dicom-annotator serve --project /path/to/tcia-handler`), so it never appears in URLs.

### Project / cases

```
GET  /api/project
  → { name, labels: [{id,name,color}], sources: [...] }

GET  /api/cases
  → [
      { id: "case_siemens_prisma_3t",
        kind: "aligned",
        modalities: ["t2","adc","calc"],
        annotated: true,
        labels_present: ["prostate"]
      }, ...
    ]

GET  /api/cases/{case_id}
  → { id, kind, modalities, slice_count, reference_affine, reference_shape,
      modality_files: { t2: [...], adc: [...], calc: [...] } }
```

### Image bytes

Served as raw DICOM; Cornerstone3D parses client-side.

```
GET  /images/{case_id}/{modality}/manifest.json
  → { slice_urls: [...], reference_geometry: {...} }

GET  /images/{case_id}/{modality}/{slice_idx}.dcm
  → raw DICOM bytes
```

### Masks

Wire format is a **shape envelope** in `application/json`: `{ shape: [d,h,w], dtype: "uint8", data: "<base64>" }`. The backend always owns NIfTI construction; the browser never handles `.nii.gz` bytes directly. Mask sizes are small (~2 MB raw, ~3 MB base64); compactness is not a v1 concern.

```
GET  /api/cases/{case_id}/masks/{label_id}
  → 200 application/json
       { shape: [d,h,w], dtype: "uint8", data: "<base64>" }
       Loads from NIfTI if exists; else synthesises from PNG stack if
       existing_masks is configured; else 404.

PUT  /api/cases/{case_id}/masks/{label_id}
  body: application/json
       { shape: [d,h,w], dtype: "uint8", data: "<base64>" }
  → builds Nifti1Image(data, reference_affine), atomic write
    annotations/{case_id}/{label_id}.nii.gz, updates meta.json
  → 200 { saved_at, bytes, sha256 }
```

### Health / dev

```
GET  /api/health      → { ok, project_root, case_count }
POST /api/refresh     → rescans project dir, rebuilds case index
```

### Error response shape

```
4xx/5xx → { error: "<machine_code>", message: "<human>", details: {...} }
```

Machine codes used: `case_not_found`, `label_unknown`, `geometry_mismatch`, `shape_mismatch`, `invalid_project`.

## Mask save/load flow

### Reference geometry

Computed server-side, once per case, on first load. Derived from the reference modality's DICOM headers:

- `ImagePositionPatient`, `ImageOrientationPatient`, `PixelSpacing`, `SliceThickness`/`SpacingBetweenSlices` → standard DICOM-to-NIfTI affine (LPS→RAS handled by `nibabel`).

Stamped into both the saved NIfTI header and `meta.json`.

### Save

1. User clicks Save (or `Ctrl+S`).
2. Frontend pulls Cornerstone segmentation state for each dirty label → `Uint8Array` shaped `[depth, height, width]`, base64-encodes the bytes.
3. Frontend `PUT`s shape envelope (`application/json`, `{shape, dtype, data}`) to `/api/cases/{id}/masks/{label_id}`.
4. Backend looks up reference affine, validates shape matches reference (422 `shape_mismatch` on failure), builds `Nifti1Image(data, affine)`, gzip-writes to a temp file next to the target, `fsync`, atomic rename to `<label>.nii.gz`.
5. Updates `meta.json` (last_modified, sha256, per-label entry).
6. Returns `{ saved_at, bytes, sha256 }`.

### Load

1. Frontend `GET`s `/api/cases/{id}/masks/{label_id}`.
2. Backend tries, in order:
   a. NIfTI at `annotations/<case>/<label>.nii.gz` — `nibabel.load`, verify affine matches current reference (non-fatal warning logged + surfaced as UI banner if drifted).
   b. PNG stack from `existing_masks` — assemble Uint8 volume in slice order, pad missing slices with zeros (warn), attach reference affine. **Do not auto-write NIfTI**; wait for user save.
   c. Else 404 — frontend treats as empty labelmap.
3. Returns shape envelope.

### Slice propagation

Frontend-only. Copies labelmap slice `z = N-1` → `z = N` for the active label. No backend involvement until save.

### Edge cases

- **PNG ingest slice-count mismatch:** pad with zero slices, surface warning banner. Never truncate.
- **Geometry drift on reload:** non-fatal banner ("saved geometry differs from current reference"), display as-is.
- **Concurrent writes:** assumed impossible (solo tool). Save is last-writer-wins; atomicity is at the single-file rename.

## Error handling

- **Backend startup failures** (bad YAML, missing source roots): log to stderr, exit non-zero.
- **Per-case load failures** (corrupt DICOM, undecidable geometry): mark case as `error` in case list with tooltip; clicking shows error in the main pane.
- **Per-request errors:** structured `{error, message, details}` shape (above). Frontend shows toast.
- **No backup/versioning in v1.** Atomic save covers crash-mid-write. `annotations/` lives in git if the user wants history.

### Logging

Stdlib `logging`, INFO to stdout. Per-request line: method + path + status + duration. No rotation; this runs in a terminal you're watching.

## Testing approach

Three tiers, weighted toward I/O correctness where bugs hide.

1. **Unit (pytest) — I/O layer**
   - `geometry.py`: DICOM-to-affine for representative series (Siemens, Philips, non-zero `SliceLocation` ordering). Round-trip affine through NIfTI; equality.
   - `mask_io.py`: round-trip uint8 volume → NIfTI → load → exact-equal bytes. PNG-stack ingest with mismatched slice count produces padded volume + warning. Geometry mismatch raises.
   - `case_index.py`: discover `aligned` and `raw_dicom` shapes from fixtures.
2. **Integration (pytest + httpx) — FastAPI in-process** against a fixture project committed to the repo.
   - `GET /api/cases` matches expected case list.
   - `GET /api/cases/{id}/masks/{label}` returns synthesised NIfTI when only PNGs exist.
   - `PUT` then `GET` round-trip preserves bytes and affine.
   - Bad shape on `PUT` → 422 with `shape_mismatch`.
3. **Frontend** — no formal harness in v1. Cornerstone3D has its own coverage; our glue is small. Manual testing for brush/polygon/slice nav. If the JS glue grows, add Vitest later.

### Explicitly skipped in v1

- E2E browser tests, performance benchmarks, cross-browser support beyond Chrome/Firefox latest.

## Open items for the implementation plan

- Choice of TS bundler config (Vite defaults expected to suffice).
- Choice of frontend state container (Cornerstone state + a tiny custom store; no Redux/Zustand expected for v1 scope).
- Whether to support reading DICOMDIR indices or only flat series directories under `raw_dicom`.
- Whether the brush should snap to integer pixel circles (Cornerstone default) or anti-aliased (probably default).

These do not block writing the implementation plan and can be decided there.
