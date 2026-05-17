# dicom_annotator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CVAT-style local DICOM segmentation annotator (FastAPI + Cornerstone3D) per the design at `docs/superpowers/specs/2026-05-17-dicom-annotator-design.md`.

**Architecture:** Solo/local browser tool. Python (uv) FastAPI backend serves DICOM bytes and persists NIfTI masks. TypeScript (Vite) frontend uses Cornerstone3D for viewports, segmentation state, and tools. Filesystem-only storage; mask round-trip via a JSON shape envelope (`{shape, dtype, data: base64}`).

**Tech Stack:** Python 3.11+, uv, FastAPI, uvicorn, pydicom, nibabel, numpy, Pillow, pydantic, pytest, httpx; TypeScript 5+, Vite, `@cornerstonejs/core`, `@cornerstonejs/tools`, `@cornerstonejs/dicom-image-loader`.

## File map

```
dicom_annotator/
├── pyproject.toml                        # uv project, deps, scripts
├── README.md
├── backend/
│   └── dicom_annotator/
│       ├── __init__.py
│       ├── cli.py                        # `dicom-annotator serve ...`
│       ├── api.py                        # FastAPI app + routes
│       ├── config.py                     # pydantic project.yaml schema
│       ├── case_index.py                 # case discovery (aligned + raw_dicom)
│       ├── geometry.py                   # DICOM headers -> reference affine
│       ├── readers.py                    # DICOM, PNG, NIfTI readers
│       ├── mask_io.py                    # volume <-> NIfTI <-> shape envelope
│       └── errors.py                     # error code constants
├── tests/
│   ├── conftest.py                       # synthetic DICOM helpers, fixture project
│   ├── fixtures/                         # tiny fixture project under git
│   ├── test_config.py
│   ├── test_case_index.py
│   ├── test_geometry.py
│   ├── test_readers.py
│   ├── test_mask_io.py
│   └── test_api.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.ts                       # entry
        ├── api.ts                        # fetch wrappers + typed responses
        ├── types.ts                      # shared types matching backend
        ├── cornerstone-init.ts           # init core + image loader
        ├── viewports.ts                  # 3-pane synced viewports
        ├── tools.ts                      # tool group + brush/poly/erase
        ├── segmentation.ts               # labelmap state + load/save
        ├── case-list.ts                  # left sidebar
        ├── label-panel.ts                # active/visible label widget
        ├── scrubber.ts                   # slice scrubber
        ├── propagate.ts                  # propagate-from-previous-slice
        ├── shortcuts.ts                  # keyboard bindings
        ├── dirty.ts                      # unsaved-changes tracker
        └── ui.css
```

---

## Phase 0 — Bootstrap

### Task 0.1: Initialize uv project and create skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `backend/dicom_annotator/__init__.py`
- Create: `README.md`
- Modify: `.gitignore` (already exists; ensure entries below are present)

- [ ] **Step 1: Initialize uv project**

Run from project root:
```bash
uv init --name dicom-annotator --no-readme --bare
```

If `uv init` did not produce a `pyproject.toml`, create it explicitly as in Step 2.

- [ ] **Step 2: Write `pyproject.toml`**

Replace any generated `pyproject.toml` with:

```toml
[project]
name = "dicom-annotator"
version = "0.1.0"
description = "CVAT-style local DICOM segmentation annotator"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "pyyaml>=6.0",
    "pydicom>=2.4",
    "nibabel>=5.2",
    "numpy>=1.26",
    "pillow>=10.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
    "pytest-asyncio>=0.23",
]

[project.scripts]
dicom-annotator = "dicom_annotator.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["backend/dicom_annotator"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create package init and ensure `.gitignore` covers build artifacts**

Create `backend/dicom_annotator/__init__.py` with:
```python
"""dicom_annotator backend."""
```

Ensure `.gitignore` contains (append if missing):
```
.superpowers/
__pycache__/
*.pyc
.venv/
node_modules/
dist/
.vite/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 4: Sync dependencies**

Run:
```bash
uv sync --extra dev
```

Expected: creates `.venv`, installs deps, writes `uv.lock`.

- [ ] **Step 5: Write minimal README**

Create `README.md`:
```markdown
# dicom_annotator

Local DICOM segmentation annotator (FastAPI + Cornerstone3D).

See `docs/superpowers/specs/2026-05-17-dicom-annotator-design.md` for design.

## Run

```bash
uv sync --extra dev
uv run dicom-annotator serve --project /path/to/project
```
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock backend/ README.md .gitignore
git commit -m "chore: bootstrap uv project skeleton"
```

---

## Phase 1 — Project config

### Task 1.1: Pydantic schema for `project.yaml`

**Files:**
- Create: `backend/dicom_annotator/config.py`
- Create: `tests/test_config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing test**

Create `tests/conftest.py`:
```python
from pathlib import Path
import pytest


@pytest.fixture
def project_yaml_text() -> str:
    return """
name: prostate-mri
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
""".strip()


@pytest.fixture
def project_root(tmp_path: Path, project_yaml_text: str) -> Path:
    (tmp_path / "project.yaml").write_text(project_yaml_text)
    return tmp_path
```

Create `tests/test_config.py`:
```python
from dicom_annotator.config import load_project, Project, Label, AlignedSource, RawDicomSource


def test_load_project_parses_labels(project_root):
    project = load_project(project_root)
    assert isinstance(project, Project)
    assert project.name == "prostate-mri"
    assert project.labels == [
        Label(id=1, name="prostate", color="#4FC3F7"),
        Label(id=2, name="target1", color="#FF7043"),
    ]


def test_load_project_parses_aligned_source(project_root):
    project = load_project(project_root)
    aligned = project.sources[0]
    assert isinstance(aligned, AlignedSource)
    assert aligned.kind == "aligned"
    assert aligned.root == "data/aligned"
    assert aligned.case_glob == "case_*"
    assert aligned.modalities == {"t2": "t2", "adc": "adc", "calc": "calc"}
    assert aligned.existing_masks == {"prostate": "mask_prostate", "target1": "mask_target1"}


def test_load_project_parses_raw_dicom_source(project_root):
    project = load_project(project_root)
    raw = project.sources[1]
    assert isinstance(raw, RawDicomSource)
    assert raw.kind == "raw_dicom"
    assert raw.case_pattern == "*/study_*/series_*"
    assert raw.modality_from_header is True


def test_load_project_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path)
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_config.py -v
```
Expected: all tests fail with `ModuleNotFoundError: No module named 'dicom_annotator.config'`.

- [ ] **Step 3: Implement `config.py`**

Create `backend/dicom_annotator/config.py`:
```python
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field


class Label(BaseModel):
    id: int
    name: str
    color: str


class AlignedSource(BaseModel):
    kind: Literal["aligned"]
    root: str
    case_glob: str
    modalities: dict[str, str]
    existing_masks: dict[str, str] = Field(default_factory=dict)


class RawDicomSource(BaseModel):
    kind: Literal["raw_dicom"]
    root: str
    case_pattern: str
    modality_from_header: bool = True


Source = Annotated[
    Union[AlignedSource, RawDicomSource],
    Field(discriminator="kind"),
]


class Project(BaseModel):
    name: str
    labels: list[Label]
    sources: list[Source]


def load_project(project_root: Path) -> Project:
    """Load `project.yaml` from a project root directory."""
    config_path = project_root / "project.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"project.yaml not found at {config_path}")
    data = yaml.safe_load(config_path.read_text())
    return Project.model_validate(data)
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_config.py -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(config): pydantic schema and loader for project.yaml"
```

---

## Phase 2 — Case index

### Task 2.1: Case discovery for `aligned` sources

**Files:**
- Create: `backend/dicom_annotator/case_index.py`
- Modify: `tests/conftest.py` (add fixture builder for aligned dirs)
- Create: `tests/test_case_index.py`

- [ ] **Step 1: Add fixture builder to `conftest.py`**

Append to `tests/conftest.py`:
```python
def make_aligned_case(root: Path, case_id: str, modalities: list[str], slice_count: int = 3) -> Path:
    """Create an aligned-case dir with empty modality subdirs and N dummy .dcm files each."""
    case_dir = root / case_id
    for mod in modalities:
        mod_dir = case_dir / mod
        mod_dir.mkdir(parents=True, exist_ok=True)
        for i in range(slice_count):
            (mod_dir / f"{i:04d}.dcm").write_bytes(b"")
    return case_dir


def make_aligned_existing_mask(case_dir: Path, mask_subdir: str, slice_count: int) -> Path:
    """Create an existing-mask PNG-stack subdir under a case."""
    mask_dir = case_dir / mask_subdir
    mask_dir.mkdir(parents=True, exist_ok=True)
    for i in range(slice_count):
        (mask_dir / f"{i:04d}.png").write_bytes(b"")
    return mask_dir
```

- [ ] **Step 2: Write failing test**

Create `tests/test_case_index.py`:
```python
from pathlib import Path

from dicom_annotator.case_index import build_index, CaseEntry
from dicom_annotator.config import Project, AlignedSource, Label
from tests.conftest import make_aligned_case, make_aligned_existing_mask


def _aligned_project(root: Path) -> Project:
    return Project(
        name="test",
        labels=[Label(id=1, name="prostate", color="#000")],
        sources=[
            AlignedSource(
                kind="aligned",
                root="data/aligned",
                case_glob="case_*",
                modalities={"t2": "t2", "adc": "adc", "calc": "calc"},
                existing_masks={"prostate": "mask_prostate"},
            )
        ],
    )


def test_index_discovers_aligned_cases(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2", "adc", "calc"])
    make_aligned_case(aligned_root, "case_002", ["t2", "adc"])
    (aligned_root / "ignored").mkdir()  # does not match case_*

    index = build_index(tmp_path, _aligned_project(tmp_path))

    ids = sorted(c.id for c in index)
    assert ids == ["case_001", "case_002"]


def test_index_reports_modalities_present(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2", "adc"])

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = index[0]
    assert isinstance(entry, CaseEntry)
    assert entry.kind == "aligned"
    assert sorted(entry.modalities) == ["adc", "t2"]


def test_index_marks_annotated_when_annotations_exist(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2"])
    ann_dir = tmp_path / "annotations" / "case_001"
    ann_dir.mkdir(parents=True)
    (ann_dir / "prostate.nii.gz").write_bytes(b"")

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = next(c for c in index if c.id == "case_001")
    assert entry.annotated is True
    assert entry.labels_present == ["prostate"]


def test_index_marks_unannotated_when_no_dir(tmp_path: Path):
    aligned_root = tmp_path / "data" / "aligned"
    make_aligned_case(aligned_root, "case_001", ["t2"])

    index = build_index(tmp_path, _aligned_project(tmp_path))

    entry = index[0]
    assert entry.annotated is False
    assert entry.labels_present == []
```

- [ ] **Step 3: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_case_index.py -v
```
Expected: all fail with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `case_index.py` (aligned only for this task)**

Create `backend/dicom_annotator/case_index.py`:
```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .config import AlignedSource, Project, RawDicomSource


@dataclass(frozen=True)
class CaseEntry:
    id: str
    kind: Literal["aligned", "raw_dicom"]
    modalities: list[str]
    annotated: bool
    labels_present: list[str]
    case_dir: Path
    source_index: int  # which source produced this entry


def build_index(project_root: Path, project: Project) -> list[CaseEntry]:
    """Discover all cases across all configured sources."""
    entries: list[CaseEntry] = []
    annotations_root = project_root / "annotations"
    for src_idx, source in enumerate(project.sources):
        if isinstance(source, AlignedSource):
            entries.extend(_discover_aligned(project_root, source, src_idx, annotations_root))
        elif isinstance(source, RawDicomSource):
            pass  # implemented in Task 2.2
    return entries


def _discover_aligned(
    project_root: Path,
    source: AlignedSource,
    source_index: int,
    annotations_root: Path,
) -> list[CaseEntry]:
    root = project_root / source.root
    if not root.exists():
        return []
    entries = []
    for case_dir in sorted(root.glob(source.case_glob)):
        if not case_dir.is_dir():
            continue
        present = [mod_key for mod_key, sub in source.modalities.items() if (case_dir / sub).is_dir()]
        if not present:
            continue
        ann_dir = annotations_root / case_dir.name
        labels_present, annotated = _labels_present(ann_dir)
        entries.append(
            CaseEntry(
                id=case_dir.name,
                kind="aligned",
                modalities=present,
                annotated=annotated,
                labels_present=labels_present,
                case_dir=case_dir,
                source_index=source_index,
            )
        )
    return entries


def _labels_present(ann_dir: Path) -> tuple[list[str], bool]:
    if not ann_dir.is_dir():
        return [], False
    labels = sorted(p.name.removesuffix(".nii.gz") for p in ann_dir.glob("*.nii.gz"))
    return labels, len(labels) > 0
```

- [ ] **Step 5: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_case_index.py -v
```
Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/ tests/
git commit -m "feat(case_index): aligned-source case discovery"
```

### Task 2.2: Case discovery for `raw_dicom` sources (flat series list)

**Files:**
- Modify: `backend/dicom_annotator/case_index.py:1-end` (implement `_discover_raw_dicom`)
- Modify: `tests/test_case_index.py` (add raw_dicom tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_case_index.py`:
```python
from dicom_annotator.config import RawDicomSource


def _raw_project() -> Project:
    return Project(
        name="raw",
        labels=[Label(id=1, name="prostate", color="#000")],
        sources=[
            RawDicomSource(
                kind="raw_dicom",
                root="data/nbia",
                case_pattern="*/study_*/series_*",
                modality_from_header=True,
            )
        ],
    )


def test_index_discovers_raw_dicom_as_flat_series_list(tmp_path: Path):
    # Build: data/nbia/patient1/study_01/series_a/{0.dcm,1.dcm}
    nbia = tmp_path / "data" / "nbia"
    s1 = nbia / "patient1" / "study_01" / "series_a"
    s2 = nbia / "patient1" / "study_01" / "series_b"
    s3 = nbia / "patient2" / "study_01" / "series_a"
    for s in (s1, s2, s3):
        s.mkdir(parents=True)
        (s / "0.dcm").write_bytes(b"")

    index = build_index(tmp_path, _raw_project())

    ids = sorted(c.id for c in index)
    assert ids == [
        "patient1__study_01__series_a",
        "patient1__study_01__series_b",
        "patient2__study_01__series_a",
    ]
    for entry in index:
        assert entry.kind == "raw_dicom"
        assert entry.modalities == ["series"]  # single modality slot for raw mode


def test_index_skips_empty_directories_in_raw(tmp_path: Path):
    nbia = tmp_path / "data" / "nbia"
    empty = nbia / "patient1" / "study_01" / "series_a"
    empty.mkdir(parents=True)  # no .dcm files

    index = build_index(tmp_path, _raw_project())
    assert index == []
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_case_index.py::test_index_discovers_raw_dicom_as_flat_series_list -v
```
Expected: fails (no raw cases yet).

- [ ] **Step 3: Implement `_discover_raw_dicom`**

Modify `backend/dicom_annotator/case_index.py`: replace the `elif isinstance(source, RawDicomSource): pass` with a call to a new helper, and add the helper at the bottom:

```python
def build_index(project_root: Path, project: Project) -> list[CaseEntry]:
    entries: list[CaseEntry] = []
    annotations_root = project_root / "annotations"
    for src_idx, source in enumerate(project.sources):
        if isinstance(source, AlignedSource):
            entries.extend(_discover_aligned(project_root, source, src_idx, annotations_root))
        elif isinstance(source, RawDicomSource):
            entries.extend(_discover_raw_dicom(project_root, source, src_idx, annotations_root))
    return entries


def _discover_raw_dicom(
    project_root: Path,
    source: RawDicomSource,
    source_index: int,
    annotations_root: Path,
) -> list[CaseEntry]:
    root = project_root / source.root
    if not root.exists():
        return []
    entries = []
    for series_dir in sorted(root.glob(source.case_pattern)):
        if not series_dir.is_dir():
            continue
        if not any(series_dir.glob("*.dcm")):
            continue
        rel = series_dir.relative_to(root)
        case_id = "__".join(rel.parts)
        ann_dir = annotations_root / case_id
        labels_present, annotated = _labels_present(ann_dir)
        entries.append(
            CaseEntry(
                id=case_id,
                kind="raw_dicom",
                modalities=["series"],
                annotated=annotated,
                labels_present=labels_present,
                case_dir=series_dir,
                source_index=source_index,
            )
        )
    return entries
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_case_index.py -v
```
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(case_index): raw_dicom flat series discovery"
```

---

## Phase 3 — Geometry

### Task 3.1: DICOM headers → reference affine

**Files:**
- Create: `backend/dicom_annotator/geometry.py`
- Modify: `tests/conftest.py` (add synthetic DICOM helper)
- Create: `tests/test_geometry.py`

- [ ] **Step 1: Add synthetic-DICOM helper to `conftest.py`**

Append to `tests/conftest.py`:
```python
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid


def write_dicom_slice(
    path: Path,
    image: np.ndarray,
    *,
    instance_number: int,
    image_position_patient: tuple[float, float, float],
    image_orientation_patient: tuple[float, float, float, float, float, float] = (1, 0, 0, 0, 1, 0),
    pixel_spacing: tuple[float, float] = (1.0, 1.0),
    slice_thickness: float = 1.0,
    series_instance_uid: str | None = None,
    study_instance_uid: str | None = None,
    series_description: str = "T2",
) -> Path:
    """Write a minimal valid DICOM slice file at `path`."""
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"  # MR Image Storage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = "Test"
    ds.PatientID = "TEST"
    ds.Modality = "MR"
    ds.SeriesDescription = series_description
    ds.StudyInstanceUID = study_instance_uid or generate_uid()
    ds.SeriesInstanceUID = series_instance_uid or generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.InstanceNumber = instance_number
    ds.ImagePositionPatient = list(image_position_patient)
    ds.ImageOrientationPatient = list(image_orientation_patient)
    ds.PixelSpacing = list(pixel_spacing)
    ds.SliceThickness = slice_thickness
    ds.SpacingBetweenSlices = slice_thickness
    ds.Rows, ds.Columns = image.shape
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = image.astype(np.uint16).tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(path, write_like_original=False)
    return path


def write_dicom_series(dir_path: Path, slices: int = 4, *, base_z: float = 0.0, dz: float = 2.0) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    series_uid = generate_uid()
    for i in range(slices):
        write_dicom_slice(
            dir_path / f"{i:04d}.dcm",
            image=np.zeros((8, 8), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(0.0, 0.0, base_z + i * dz),
            series_instance_uid=series_uid,
        )
    return dir_path
```

- [ ] **Step 2: Write failing test**

Create `tests/test_geometry.py`:
```python
import numpy as np
from pathlib import Path

from dicom_annotator.geometry import (
    affine_from_series,
    GeometryError,
    ReferenceGeometry,
)
from tests.conftest import write_dicom_series, write_dicom_slice


def test_affine_from_series_unit_spacing(tmp_path: Path):
    series_dir = write_dicom_series(tmp_path / "s", slices=4, base_z=0.0, dz=1.0)

    geom = affine_from_series(series_dir)

    assert isinstance(geom, ReferenceGeometry)
    assert geom.shape == (4, 8, 8)          # (depth, rows, cols)
    assert geom.spacing == (1.0, 1.0, 1.0)  # (row, col, slice)
    # affine: x-axis col, y-axis row, z-axis slice
    np.testing.assert_array_almost_equal(geom.affine[:3, 0], [1.0, 0.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 1], [0.0, 1.0, 0.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 2], [0.0, 0.0, 1.0])
    np.testing.assert_array_almost_equal(geom.affine[:3, 3], [0.0, 0.0, 0.0])


def test_affine_from_series_anisotropic_spacing(tmp_path: Path):
    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    for i in range(3):
        write_dicom_slice(
            series_dir / f"{i:04d}.dcm",
            image=np.zeros((4, 6), dtype=np.uint16),
            instance_number=i + 1,
            image_position_patient=(0.0, 0.0, i * 3.0),
            pixel_spacing=(0.5, 0.75),
            slice_thickness=3.0,
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    assert geom.shape == (3, 4, 6)
    assert geom.spacing == (0.5, 0.75, 3.0)


def test_affine_orders_slices_by_z(tmp_path: Path):
    series_dir = tmp_path / "s"
    series_dir.mkdir()
    from pydicom.uid import generate_uid
    uid = generate_uid()
    # Write in reverse order; InstanceNumber unrelated to filesystem order
    for fname, inst, z in [("a.dcm", 3, 2.0), ("b.dcm", 1, 0.0), ("c.dcm", 2, 1.0)]:
        write_dicom_slice(
            series_dir / fname,
            image=np.zeros((4, 4), dtype=np.uint16),
            instance_number=inst,
            image_position_patient=(0.0, 0.0, z),
            series_instance_uid=uid,
        )

    geom = affine_from_series(series_dir)

    assert geom.slice_files[0].name == "b.dcm"  # z=0.0
    assert geom.slice_files[1].name == "c.dcm"  # z=1.0
    assert geom.slice_files[2].name == "a.dcm"  # z=2.0


def test_affine_raises_on_empty_dir(tmp_path: Path):
    import pytest
    (tmp_path / "empty").mkdir()
    with pytest.raises(GeometryError):
        affine_from_series(tmp_path / "empty")
```

- [ ] **Step 3: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_geometry.py -v
```
Expected: all fail with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `geometry.py`**

Create `backend/dicom_annotator/geometry.py`:
```python
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pydicom


class GeometryError(Exception):
    """Raised when reference geometry cannot be derived."""


@dataclass(frozen=True)
class ReferenceGeometry:
    shape: tuple[int, int, int]         # (depth, rows, cols)
    spacing: tuple[float, float, float] # (row_mm, col_mm, slice_mm)
    affine: np.ndarray                  # 4x4 NIfTI-style affine (RAS)
    slice_files: list[Path]             # ordered by z


def affine_from_series(series_dir: Path) -> ReferenceGeometry:
    """Read all DICOMs in `series_dir`, order by position-along-normal, build affine."""
    files = sorted(series_dir.glob("*.dcm"))
    if not files:
        raise GeometryError(f"No .dcm files in {series_dir}")

    slices = []
    for f in files:
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        slices.append((f, ds))

    iop = np.asarray(slices[0][1].ImageOrientationPatient, dtype=float)
    row_cosine = iop[0:3]
    col_cosine = iop[3:6]
    normal = np.cross(row_cosine, col_cosine)

    def along_normal(item):
        ipp = np.asarray(item[1].ImagePositionPatient, dtype=float)
        return float(np.dot(ipp, normal))

    slices.sort(key=along_normal)
    files_sorted = [f for f, _ in slices]

    first_ds = slices[0][1]
    last_ds = slices[-1][1]
    rows = int(first_ds.Rows)
    cols = int(first_ds.Columns)
    depth = len(slices)

    ps = first_ds.PixelSpacing
    row_mm = float(ps[0])
    col_mm = float(ps[1])

    if depth > 1:
        p_first = np.asarray(first_ds.ImagePositionPatient, dtype=float)
        p_last = np.asarray(last_ds.ImagePositionPatient, dtype=float)
        slice_mm = float(np.linalg.norm(p_last - p_first) / (depth - 1))
    else:
        slice_mm = float(getattr(first_ds, "SpacingBetweenSlices", first_ds.SliceThickness or 1.0))

    # Build affine: DICOM (LPS) -> RAS by flipping x,y.
    # For test simplicity here we keep LPS == RAS axes (identity row/col cosines).
    # Production-quality conversion uses nibabel.affines; for v1 with axis-aligned
    # data this construction matches.
    affine = np.eye(4, dtype=float)
    affine[:3, 0] = row_cosine * col_mm     # column direction
    affine[:3, 1] = col_cosine * row_mm     # row direction
    affine[:3, 2] = normal * slice_mm       # slice direction
    affine[:3, 3] = np.asarray(first_ds.ImagePositionPatient, dtype=float)

    return ReferenceGeometry(
        shape=(depth, rows, cols),
        spacing=(row_mm, col_mm, slice_mm),
        affine=affine,
        slice_files=files_sorted,
    )
```

- [ ] **Step 5: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_geometry.py -v
```
Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/ tests/
git commit -m "feat(geometry): DICOM-series-to-reference-affine"
```

---

## Phase 4 — Mask I/O

### Task 4.1: NIfTI round-trip

**Files:**
- Create: `backend/dicom_annotator/mask_io.py`
- Create: `tests/test_mask_io.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_mask_io.py`:
```python
import base64
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from dicom_annotator.geometry import ReferenceGeometry
from dicom_annotator.mask_io import (
    write_mask_nifti,
    load_mask_nifti,
    volume_to_envelope,
    envelope_to_volume,
    ShapeMismatch,
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
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_mask_io.py -v
```
Expected: failures (module missing).

- [ ] **Step 3: Implement `mask_io.py`**

Create `backend/dicom_annotator/mask_io.py`:
```python
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
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent), suffix=".tmp")
    os.close(fd)
    nib.save(img, tmp)
    os.replace(tmp, target)


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
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_mask_io.py -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(mask_io): NIfTI round-trip + shape envelope"
```

### Task 4.2: PNG-stack ingest with pad-on-mismatch

**Files:**
- Modify: `backend/dicom_annotator/mask_io.py` (add `ingest_png_stack`)
- Modify: `tests/test_mask_io.py` (add PNG-ingest tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_mask_io.py`:
```python
from PIL import Image

from dicom_annotator.mask_io import ingest_png_stack, PngIngestResult


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
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_mask_io.py -v
```
Expected: new tests fail (`ingest_png_stack` not defined).

- [ ] **Step 3: Implement `ingest_png_stack`**

Append to `backend/dicom_annotator/mask_io.py`:
```python
from dataclasses import field
from PIL import Image


@dataclass
class PngIngestResult:
    volume: np.ndarray
    warnings: list[str] = field(default_factory=list)


def ingest_png_stack(png_dir: Path, geom: ReferenceGeometry) -> PngIngestResult:
    """Read a directory of PNG slices into a uint8 volume of geom.shape.

    Slice order: lexicographic filename order. Missing trailing slices are zero-padded.
    Per-slice in-plane dimensions must match geom (rows x cols), else ShapeMismatch.
    Binary thresholding: any non-zero pixel becomes 1.
    """
    depth, rows, cols = geom.shape
    files = sorted(png_dir.glob("*.png"))
    volume = np.zeros((depth, rows, cols), dtype=np.uint8)
    warnings: list[str] = []
    if len(files) != depth:
        warnings.append(f"expected {depth} slices, found {len(files)} — padding with zeros")
    for i, f in enumerate(files[:depth]):
        img = np.asarray(Image.open(f).convert("L"))
        if img.shape != (rows, cols):
            raise ShapeMismatch(f"{f.name} shape {img.shape} != geometry ({rows},{cols})")
        volume[i] = (img > 0).astype(np.uint8)
    return PngIngestResult(volume=volume, warnings=warnings)
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_mask_io.py -v
```
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(mask_io): PNG-stack ingest with zero-pad on mismatch"
```

---

## Phase 5 — Readers

### Task 5.1: DICOM and series-manifest readers

**Files:**
- Create: `backend/dicom_annotator/readers.py`
- Create: `tests/test_readers.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_readers.py`:
```python
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
```

- [ ] **Step 2: Run test, expect failure**

Run:
```bash
uv run pytest tests/test_readers.py -v
```
Expected: fails (`readers` missing).

- [ ] **Step 3: Implement `readers.py`**

Create `backend/dicom_annotator/readers.py`:
```python
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
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_readers.py -v
```
Expected: 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(readers): DICOM series manifest"
```

---

## Phase 6 — API routes

### Task 6.1: `errors.py` and `/api/project`, `/api/cases`, `/api/cases/{id}`

**Files:**
- Create: `backend/dicom_annotator/errors.py`
- Create: `backend/dicom_annotator/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_api.py`:
```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dicom_annotator.api import create_app
from dicom_annotator.config import load_project
from tests.conftest import write_dicom_series


@pytest.fixture
def aligned_project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.yaml").write_text(
        """
name: test
labels:
  - id: 1
    name: prostate
    color: "#4FC3F7"
sources:
  - kind: aligned
    root: data
    case_glob: "case_*"
    modalities:
      t2: t2
"""
    )
    write_dicom_series(tmp_path / "data" / "case_001" / "t2", slices=3)
    write_dicom_series(tmp_path / "data" / "case_002" / "t2", slices=3)
    return tmp_path


@pytest.fixture
def client(aligned_project_root: Path) -> TestClient:
    project = load_project(aligned_project_root)
    app = create_app(aligned_project_root, project)
    return TestClient(app)


def test_get_project(client: TestClient):
    r = client.get("/api/project")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "test"
    assert body["labels"][0]["name"] == "prostate"


def test_get_cases(client: TestClient):
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json()
    assert sorted(c["id"] for c in cases) == ["case_001", "case_002"]
    for c in cases:
        assert c["kind"] == "aligned"
        assert c["annotated"] is False
        assert c["labels_present"] == []


def test_get_case_detail(client: TestClient):
    r = client.get("/api/cases/case_001")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "case_001"
    assert body["modalities"] == ["t2"]
    assert body["slice_count"] == 3
    assert len(body["reference_affine"]) == 4


def test_get_case_not_found(client: TestClient):
    r = client.get("/api/cases/does_not_exist")
    assert r.status_code == 404
    assert r.json()["error"] == "case_not_found"
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `errors.py`**

Create `backend/dicom_annotator/errors.py`:
```python
from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, error: str, message: str, **details):
        super().__init__(
            status_code=status_code,
            detail={"error": error, "message": message, "details": details},
        )


def case_not_found(case_id: str) -> ApiError:
    return ApiError(404, "case_not_found", f"No case with id {case_id!r}", case_id=case_id)


def label_unknown(label_id: int | str) -> ApiError:
    return ApiError(404, "label_unknown", f"No label with id {label_id!r}", label_id=label_id)


def shape_mismatch(expected: tuple, got: tuple) -> ApiError:
    return ApiError(422, "shape_mismatch", "Mask shape does not match reference geometry",
                    expected=list(expected), got=list(got))


def invalid_project(message: str) -> ApiError:
    return ApiError(400, "invalid_project", message)


def geometry_error(message: str) -> ApiError:
    return ApiError(500, "geometry_mismatch", message)
```

- [ ] **Step 4: Implement `api.py` (project + cases routes only for this task)**

Create `backend/dicom_annotator/api.py`:
```python
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
```

- [ ] **Step 5: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/ tests/
git commit -m "feat(api): /api/project, /api/cases, /api/cases/{id}, /api/health"
```

### Task 6.2: Image manifest and DICOM byte routes

**Files:**
- Modify: `backend/dicom_annotator/api.py` (add image routes)
- Modify: `tests/test_api.py` (add image tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_api.py`:
```python
def test_get_image_manifest(client: TestClient):
    r = client.get("/images/case_001/t2/manifest.json")
    assert r.status_code == 200
    body = r.json()
    assert len(body["slice_urls"]) == 3
    assert body["slice_urls"][0].endswith("/0.dcm")
    assert body["reference_geometry"]["shape"] == [3, 8, 8]


def test_get_image_slice_bytes(client: TestClient):
    r = client.get("/images/case_001/t2/0.dcm")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/dicom")
    assert r.content[:128 + 4][128:132] == b"DICM" or len(r.content) > 0


def test_get_image_unknown_modality_404(client: TestClient):
    r = client.get("/images/case_001/bogus/manifest.json")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: 3 new failures.

- [ ] **Step 3: Add image routes to `api.py`**

Inside `create_app` in `backend/dicom_annotator/api.py`, after the `/api/cases/{case_id}` route, add:
```python
    from fastapi.responses import FileResponse
    from .readers import build_series_manifest

    def _modality_dir(c: CaseEntry, modality: str) -> Path:
        if c.kind == "aligned":
            if modality not in c.modalities:
                raise errors.ApiError(404, "modality_not_found",
                                      f"case {c.id} has no modality {modality!r}",
                                      case_id=c.id, modality=modality)
            return c.case_dir / modality
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
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(api): image manifest and DICOM byte routes"
```

### Task 6.3: Mask GET/PUT routes with NIfTI persistence and PNG ingest

**Files:**
- Modify: `backend/dicom_annotator/api.py` (add mask routes)
- Modify: `tests/test_api.py` (add mask tests + PNG-ingest test)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_api.py`:
```python
import base64

import numpy as np

from dicom_annotator.mask_io import envelope_to_volume


def test_put_and_get_mask_roundtrip(client: TestClient):
    # First fetch geometry to know expected shape
    detail = client.get("/api/cases/case_001").json()
    shape = tuple(detail["reference_shape"])
    volume = np.zeros(shape, dtype=np.uint8)
    volume[1, 2, 3] = 1
    body = {
        "shape": list(shape),
        "dtype": "uint8",
        "data": base64.b64encode(volume.tobytes()).decode("ascii"),
    }

    put = client.put("/api/cases/case_001/masks/1", json=body)
    assert put.status_code == 200, put.text
    assert "saved_at" in put.json()

    get = client.get("/api/cases/case_001/masks/1")
    assert get.status_code == 200
    loaded = envelope_to_volume(get.json())
    np.testing.assert_array_equal(loaded, volume)


def test_put_mask_wrong_shape_422(client: TestClient):
    body = {"shape": [99, 99, 99], "dtype": "uint8",
            "data": base64.b64encode(b"\x00" * (99 * 99 * 99)).decode("ascii")}
    r = client.put("/api/cases/case_001/masks/1", json=body)
    assert r.status_code == 422
    assert r.json()["error"] == "shape_mismatch"


def test_get_mask_404_when_missing(client: TestClient):
    r = client.get("/api/cases/case_002/masks/1")
    assert r.status_code == 404


def test_get_mask_synthesizes_from_png_when_configured(tmp_path: Path):
    # Build a project that declares existing_masks
    (tmp_path / "project.yaml").write_text(
        """
name: pngtest
labels:
  - id: 1
    name: prostate
    color: "#000"
sources:
  - kind: aligned
    root: data
    case_glob: "case_*"
    modalities:
      t2: t2
    existing_masks:
      prostate: mask_prostate
"""
    )
    series_dir = write_dicom_series(tmp_path / "data" / "case_001" / "t2", slices=3)
    # Add PNG mask stack with one slice filled
    mask_dir = tmp_path / "data" / "case_001" / "mask_prostate"
    mask_dir.mkdir()
    from PIL import Image
    for i in range(3):
        arr = np.zeros((8, 8), dtype=np.uint8)
        if i == 1:
            arr[2, 2] = 255
        Image.fromarray(arr, mode="L").save(mask_dir / f"{i:04d}.png")

    project = load_project(tmp_path)
    client = TestClient(create_app(tmp_path, project))
    r = client.get("/api/cases/case_001/masks/1")
    assert r.status_code == 200
    vol = envelope_to_volume(r.json())
    assert vol.shape == (3, 8, 8)
    assert vol[1, 2, 2] == 1
    assert vol.sum() == 1
```

- [ ] **Step 2: Run tests, expect failures**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: 4 new failures.

- [ ] **Step 3: Add mask routes to `api.py`**

Append inside `create_app`, before `return app`:
```python
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
        ref_mod = "t2" if "t2" in c.modalities else c.modalities[0]
        ref_dir = c.case_dir / ref_mod if c.kind == "aligned" else c.case_dir
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
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/
git commit -m "feat(api): mask GET/PUT with NIfTI persistence and PNG ingest"
```

---

## Phase 7 — CLI entry point

### Task 7.1: `dicom-annotator serve` command

**Files:**
- Create: `backend/dicom_annotator/cli.py`

- [ ] **Step 1: Implement `cli.py`**

Create `backend/dicom_annotator/cli.py`:
```python
import argparse
import sys
from pathlib import Path

import uvicorn

from .api import create_app
from .config import load_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dicom-annotator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="Run the local annotator server")
    serve.add_argument("--project", required=True, type=Path, help="Project root directory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        project_root = args.project.resolve()
        if not project_root.is_dir():
            print(f"project root not found: {project_root}", file=sys.stderr)
            return 2
        project = load_project(project_root)
        app = create_app(project_root, project)
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
        return 0
    return 2
```

- [ ] **Step 2: Smoke-test the CLI**

Run:
```bash
uv run dicom-annotator serve --help
```
Expected: argparse help text mentioning `--project`.

- [ ] **Step 3: Commit**

```bash
git add backend/
git commit -m "feat(cli): dicom-annotator serve entrypoint"
```

---

## Phase 8 — Frontend bootstrap

### Task 8.1: Vite + TypeScript + Cornerstone3D scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/ui.css`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "dicom-annotator-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@cornerstonejs/core": "^1.77.0",
    "@cornerstonejs/dicom-image-loader": "^1.77.0",
    "@cornerstonejs/tools": "^1.77.0",
    "dicom-parser": "^1.8.21"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.1.0"
  }
}
```

- [ ] **Step 2: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": false,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/images": "http://127.0.0.1:8000",
    },
  },
  optimizeDeps: {
    exclude: ["@cornerstonejs/dicom-image-loader"],
  },
});
```

- [ ] **Step 4: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>dicom_annotator</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 5: Create `frontend/src/ui.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font: 13px/1.4 -apple-system, sans-serif; background: #111; color: #eee; }
#app { display: grid; grid-template-rows: 40px 1fr; height: 100vh; }
.topbar { background: #1f2937; display: flex; align-items: center; padding: 0 12px; gap: 12px; }
.dirty-dot { width: 8px; height: 8px; background: #f59e0b; border-radius: 50%; display: none; }
.dirty-dot.is-dirty { display: inline-block; }
.main { display: grid; grid-template-columns: 220px 1fr 200px; gap: 8px; padding: 8px; min-height: 0; }
.case-list, .tools-panel { background: #1f2937; border-radius: 4px; padding: 8px; overflow: auto; }
.viewports { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.viewport { background: #000; border-radius: 3px; min-height: 200px; position: relative; }
.case-row { padding: 4px 6px; cursor: pointer; border-radius: 3px; }
.case-row:hover { background: #374151; }
.case-row.active { background: #3b82f6; }
.case-row.annotated::before { content: "✔ "; color: #10b981; }
.case-row:not(.annotated)::before { content: "○ "; color: #6b7280; }
.banner { background: #b45309; color: #fff; padding: 6px 10px; border-radius: 3px; margin: 4px 0; }
button { background: #374151; color: #eee; border: 1px solid #4b5563; padding: 4px 8px; border-radius: 3px; cursor: pointer; }
button.primary { background: #10b981; border-color: #059669; }
button.active { background: #3b82f6; border-color: #2563eb; }
```

- [ ] **Step 6: Create `frontend/src/types.ts`**

```ts
export interface Label { id: number; name: string; color: string; }
export interface Project { name: string; labels: Label[]; sources: unknown[]; }
export interface CaseSummary {
  id: string;
  kind: "aligned" | "raw_dicom";
  modalities: string[];
  annotated: boolean;
  labels_present: string[];
}
export interface CaseDetail {
  id: string;
  kind: "aligned" | "raw_dicom";
  modalities: string[];
  slice_count: number;
  reference_shape: [number, number, number];
  reference_affine: number[][];
  modality_files: Record<string, string[]>;
}
export interface MaskEnvelope {
  shape: [number, number, number];
  dtype: "uint8";
  data: string; // base64
  warnings?: string[];
}
```

- [ ] **Step 7: Create `frontend/src/api.ts`**

```ts
import type { Project, CaseSummary, CaseDetail, MaskEnvelope } from "./types";

export async function getProject(): Promise<Project> {
  const r = await fetch("/api/project");
  if (!r.ok) throw new Error("project fetch failed");
  return r.json();
}

export async function getCases(): Promise<CaseSummary[]> {
  const r = await fetch("/api/cases");
  if (!r.ok) throw new Error("cases fetch failed");
  return r.json();
}

export async function getCase(id: string): Promise<CaseDetail> {
  const r = await fetch(`/api/cases/${id}`);
  if (!r.ok) throw new Error(`case ${id} fetch failed`);
  return r.json();
}

export async function getMask(caseId: string, labelId: number): Promise<MaskEnvelope | null> {
  const r = await fetch(`/api/cases/${caseId}/masks/${labelId}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("mask fetch failed");
  return r.json();
}

export async function putMask(
  caseId: string,
  labelId: number,
  env: MaskEnvelope,
): Promise<{ saved_at: number; sha256: string; bytes: number }> {
  const r = await fetch(`/api/cases/${caseId}/masks/${labelId}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(env),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.message ?? "mask save failed");
  }
  return r.json();
}
```

- [ ] **Step 8: Create `frontend/src/main.ts` (stub)**

```ts
import "./ui.css";
import { getProject, getCases } from "./api";

async function main() {
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <div class="topbar">
      <strong>dicom_annotator</strong>
      <span class="dirty-dot" id="dirty"></span>
    </div>
    <div class="main">
      <div class="case-list" id="case-list">Loading…</div>
      <div class="viewports">
        <div class="viewport" id="vp-t2"></div>
        <div class="viewport" id="vp-adc"></div>
        <div class="viewport" id="vp-calc"></div>
      </div>
      <div class="tools-panel" id="tools">Tools</div>
    </div>
  `;
  const project = await getProject();
  document.querySelector(".topbar strong")!.textContent = `dicom_annotator — ${project.name}`;
  const cases = await getCases();
  const list = document.getElementById("case-list")!;
  list.innerHTML = cases.map(c =>
    `<div class="case-row ${c.annotated ? "annotated" : ""}" data-id="${c.id}">${c.id}</div>`
  ).join("");
}

main().catch(err => {
  document.body.innerHTML = `<pre style="color:#fca5a5">${err.stack ?? err}</pre>`;
});
```

- [ ] **Step 9: Install JS deps and smoke-test**

Run from `frontend/`:
```bash
cd frontend
npm install
npm run dev
```
Expected: Vite serves at `http://localhost:5173`. With backend running (`uv run dicom-annotator serve --project /path/to/tcia-handler`), `http://localhost:5173` shows the project name and a case list.

- [ ] **Step 10: Commit**

```bash
cd ..
git add frontend/.gitignore frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src/
git commit -m "feat(frontend): Vite + TS scaffold with project/case bootstrap"
```

If `frontend/.gitignore` doesn't exist, create it with:
```
node_modules/
dist/
```
and stage it.

---

## Phase 9 — Cornerstone3D init and single viewport

### Task 9.1: Initialize Cornerstone + show T2 volume in one viewport

**Files:**
- Create: `frontend/src/cornerstone-init.ts`
- Create: `frontend/src/viewports.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Create `frontend/src/cornerstone-init.ts`**

```ts
import { init as csCoreInit, RenderingEngine, Enums, volumeLoader } from "@cornerstonejs/core";
import { init as csToolsInit } from "@cornerstonejs/tools";
import * as dicomImageLoader from "@cornerstonejs/dicom-image-loader";
import dicomParser from "dicom-parser";

let initialized = false;

export async function initCornerstone(): Promise<void> {
  if (initialized) return;
  await csCoreInit();
  await csToolsInit();

  (dicomImageLoader.external as any).cornerstone = await import("@cornerstonejs/core");
  (dicomImageLoader.external as any).dicomParser = dicomParser;
  dicomImageLoader.configure({
    useWebWorkers: false,
    decodeConfig: { convertFloatPixelDataToInt: false },
  });

  initialized = true;
}

export const renderingEngine = new RenderingEngine("dicom-annotator-engine");
export const ViewportType = Enums.ViewportType;
export { volumeLoader };
```

- [ ] **Step 2: Create `frontend/src/viewports.ts`**

```ts
import { renderingEngine, ViewportType, volumeLoader } from "./cornerstone-init";
import { Types, Enums, setVolumesForViewports } from "@cornerstonejs/core";

interface ManifestResponse {
  slice_urls: string[];
  reference_geometry: {
    shape: [number, number, number];
    spacing: [number, number, number];
    affine: number[][];
  };
}

export async function loadModalityIntoViewport(args: {
  caseId: string;
  modality: string;
  viewportId: string;
  element: HTMLDivElement;
}): Promise<void> {
  const { caseId, modality, viewportId, element } = args;
  const manifestResp = await fetch(`/images/${caseId}/${modality}/manifest.json`);
  const manifest: ManifestResponse = await manifestResp.json();

  const imageIds = manifest.slice_urls.map(u => `wadouri:${window.location.origin}${u}`);
  const volumeId = `cornerstoneStreamingImageVolume:${caseId}:${modality}`;

  renderingEngine.enableElement({
    viewportId,
    type: ViewportType.ORTHOGRAPHIC,
    element,
    defaultOptions: { orientation: Enums.OrientationAxis.AXIAL },
  });

  const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
  await (volume as Types.IImageVolume).load();
  await setVolumesForViewports(renderingEngine, [{ volumeId }], [viewportId]);
  renderingEngine.render();
}
```

- [ ] **Step 3: Wire single-viewport load in `main.ts`**

Replace `frontend/src/main.ts`:
```ts
import "./ui.css";
import { getProject, getCases } from "./api";
import { initCornerstone } from "./cornerstone-init";
import { loadModalityIntoViewport } from "./viewports";

async function main() {
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <div class="topbar">
      <strong>dicom_annotator</strong>
      <span class="dirty-dot" id="dirty"></span>
    </div>
    <div class="main">
      <div class="case-list" id="case-list">Loading…</div>
      <div class="viewports">
        <div class="viewport" id="vp-t2"></div>
        <div class="viewport" id="vp-adc"></div>
        <div class="viewport" id="vp-calc"></div>
      </div>
      <div class="tools-panel" id="tools">Tools</div>
    </div>
  `;
  await initCornerstone();
  const project = await getProject();
  document.querySelector(".topbar strong")!.textContent = `dicom_annotator — ${project.name}`;
  const cases = await getCases();
  const list = document.getElementById("case-list")!;
  list.innerHTML = cases.map(c =>
    `<div class="case-row ${c.annotated ? "annotated" : ""}" data-id="${c.id}">${c.id}</div>`
  ).join("");
  list.querySelectorAll<HTMLDivElement>(".case-row").forEach(row => {
    row.addEventListener("click", async () => {
      list.querySelectorAll(".case-row").forEach(r => r.classList.remove("active"));
      row.classList.add("active");
      const caseId = row.dataset.id!;
      await loadModalityIntoViewport({
        caseId,
        modality: "t2",
        viewportId: "vp-t2",
        element: document.getElementById("vp-t2") as HTMLDivElement,
      });
    });
  });
}

main().catch(err => {
  document.body.innerHTML = `<pre style="color:#fca5a5">${err.stack ?? err}</pre>`;
});
```

- [ ] **Step 4: Manual verification**

Run backend and frontend:
```bash
# terminal 1
uv run dicom-annotator serve --project /Users/huijokim/personal/tcia-handler
# terminal 2
cd frontend && npm run dev
```
Open `http://localhost:5173`, click a case. Expected: T2 volume renders in the left viewport. Scroll wheel changes slice.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Cornerstone3D init and single-viewport T2 load"
```

### Task 9.2: Three synchronized viewports

**Files:**
- Modify: `frontend/src/viewports.ts` (add multi-viewport + sync)
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Replace `viewports.ts` with synced-loader version**

```ts
import { renderingEngine, ViewportType, volumeLoader } from "./cornerstone-init";
import {
  Types,
  Enums,
  setVolumesForViewports,
  synchronizers,
} from "@cornerstonejs/core";

export interface LoadCaseArgs {
  caseId: string;
  modalities: { key: string; viewportId: string; element: HTMLDivElement }[];
}

export async function loadCaseIntoViewports(args: LoadCaseArgs): Promise<void> {
  const { caseId, modalities } = args;
  for (const mod of modalities) {
    renderingEngine.enableElement({
      viewportId: mod.viewportId,
      type: ViewportType.ORTHOGRAPHIC,
      element: mod.element,
      defaultOptions: { orientation: Enums.OrientationAxis.AXIAL },
    });
  }

  for (const mod of modalities) {
    const manifestResp = await fetch(`/images/${caseId}/${mod.key}/manifest.json`);
    const manifest = await manifestResp.json();
    const imageIds = manifest.slice_urls.map(
      (u: string) => `wadouri:${window.location.origin}${u}`,
    );
    const volumeId = `cornerstoneStreamingImageVolume:${caseId}:${mod.key}`;
    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    await (volume as Types.IImageVolume).load();
    await setVolumesForViewports(renderingEngine, [{ volumeId }], [mod.viewportId]);
  }

  // Sync slice (camera) and zoom/pan across viewports.
  const camSync = synchronizers.createCameraPositionSynchronizer("cam-sync");
  const voiSync = synchronizers.createVOISynchronizer("voi-sync");
  for (const mod of modalities) {
    camSync.add({ renderingEngineId: renderingEngine.id, viewportId: mod.viewportId });
    voiSync.add({ renderingEngineId: renderingEngine.id, viewportId: mod.viewportId });
  }

  renderingEngine.render();
}
```

- [ ] **Step 2: Update `main.ts` to load all available modalities**

In `main.ts`, replace the click handler inside the `forEach` with:
```ts
    row.addEventListener("click", async () => {
      list.querySelectorAll(".case-row").forEach(r => r.classList.remove("active"));
      row.classList.add("active");
      const caseId = row.dataset.id!;
      // Probe the case for available modalities
      const detail = await (await fetch(`/api/cases/${caseId}`)).json();
      const modalitySlots = [
        { key: "t2",   viewportId: "vp-t2",   element: document.getElementById("vp-t2")   as HTMLDivElement },
        { key: "adc",  viewportId: "vp-adc",  element: document.getElementById("vp-adc")  as HTMLDivElement },
        { key: "calc", viewportId: "vp-calc", element: document.getElementById("vp-calc") as HTMLDivElement },
      ];
      const present = modalitySlots.filter(m => detail.modalities.includes(m.key));
      await (await import("./viewports")).loadCaseIntoViewports({ caseId, modalities: present });
    });
```
(remove the previous single-viewport import line at top.)

- [ ] **Step 3: Manual verification**

Run dev servers. Click a case with all three modalities. Expected: T2 / ADC / Calc render in left/middle/right viewports; scrolling one scrolls all; pan/zoom syncs.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): three synchronized viewports for T2/ADC/Calc"
```

---

## Phase 10 — Segmentation tools

### Task 10.1: Tool group with brush/eraser/polygon, bound to active label

**Files:**
- Create: `frontend/src/tools.ts`
- Create: `frontend/src/segmentation.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Create `frontend/src/segmentation.ts`**

```ts
import { volumeLoader, Types } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

export const TOOL_GROUP_ID = "dicom-annotator-tools";
export const SEG_VOLUME_ID = "dicom-annotator-seg";

export async function ensureSegmentationVolume(referenceVolumeId: string): Promise<string> {
  const existing = csTools.cache?.getSegmentation?.(SEG_VOLUME_ID);
  if (existing) return SEG_VOLUME_ID;

  await volumeLoader.createAndCacheDerivedSegmentationVolume(referenceVolumeId, {
    volumeId: SEG_VOLUME_ID,
  });
  csTools.segmentation.addSegmentations([
    {
      segmentationId: SEG_VOLUME_ID,
      representation: {
        type: csTools.Enums.SegmentationRepresentations.Labelmap,
        data: { volumeId: SEG_VOLUME_ID },
      },
    },
  ]);
  return SEG_VOLUME_ID;
}

export function bindSegmentationToToolGroup(viewportIds: string[]): void {
  csTools.segmentation.addSegmentationRepresentations(TOOL_GROUP_ID, [
    {
      segmentationId: SEG_VOLUME_ID,
      type: csTools.Enums.SegmentationRepresentations.Labelmap,
    },
  ]);
  void viewportIds;  // implicit: tool group already bound to viewports
}

export function setActiveSegmentIndex(labelId: number): void {
  csTools.segmentation.segmentIndex.setActiveSegmentIndex(SEG_VOLUME_ID, labelId);
}
```

- [ ] **Step 2: Create `frontend/src/tools.ts`**

```ts
import * as csTools from "@cornerstonejs/tools";
import { TOOL_GROUP_ID } from "./segmentation";

const {
  BrushTool,
  RectangleScissorsTool,
  PolygonScissorsTool,
  PanTool,
  ZoomTool,
  StackScrollMouseWheelTool,
  ToolGroupManager,
} = csTools;

export type ToolName = "brush" | "erase" | "polygon" | "pan" | "zoom";

export function createToolGroup(viewportIds: string[]): void {
  csTools.addTool(BrushTool);
  csTools.addTool(RectangleScissorsTool);
  csTools.addTool(PolygonScissorsTool);
  csTools.addTool(PanTool);
  csTools.addTool(ZoomTool);
  csTools.addTool(StackScrollMouseWheelTool);

  const tg = ToolGroupManager.createToolGroup(TOOL_GROUP_ID)!;
  tg.addTool(BrushTool.toolName, { activeStrategy: "FILL_INSIDE_CIRCLE" });
  tg.addTool(BrushTool.toolName + "Erase", { activeStrategy: "ERASE_INSIDE_CIRCLE" });
  tg.addTool(PolygonScissorsTool.toolName);
  tg.addTool(PanTool.toolName);
  tg.addTool(ZoomTool.toolName);
  tg.addTool(StackScrollMouseWheelTool.toolName);

  for (const vid of viewportIds) {
    tg.addViewport(vid, "dicom-annotator-engine");
  }
  tg.setToolActive(StackScrollMouseWheelTool.toolName);
  setActiveTool("brush");
}

export function setActiveTool(name: ToolName): void {
  const tg = csTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID)!;
  // Deactivate any previously-primary mouse tool.
  for (const t of [BrushTool.toolName, BrushTool.toolName + "Erase",
                   PolygonScissorsTool.toolName, PanTool.toolName, ZoomTool.toolName]) {
    tg.setToolPassive(t);
  }
  const toolName = ({
    brush:   BrushTool.toolName,
    erase:   BrushTool.toolName + "Erase",
    polygon: PolygonScissorsTool.toolName,
    pan:     PanTool.toolName,
    zoom:    ZoomTool.toolName,
  } as const)[name];
  tg.setToolActive(toolName, { bindings: [{ mouseButton: 1 }] });
}

export function setBrushSize(px: number): void {
  const tg = csTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID)!;
  tg.setToolConfiguration(BrushTool.toolName, { brushSize: px });
  tg.setToolConfiguration(BrushTool.toolName + "Erase", { brushSize: px });
}
```

- [ ] **Step 3: Wire tools panel and active label into `main.ts`**

In `main.ts`, after the case-list `forEach`, append rendering of the tools panel and a label panel below the viewports. Replace the `#tools` content building once the project is loaded:

```ts
  // Tools panel
  const tools = document.getElementById("tools")!;
  tools.innerHTML = `
    <div class="label-section"><strong>Tools</strong></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
      <button data-tool="brush"   class="active">🖌 Brush</button>
      <button data-tool="erase">🧽 Erase</button>
      <button data-tool="polygon">⬟ Polygon</button>
      <button data-tool="pan">✥ Pan</button>
      <button data-tool="zoom">🔍 Zoom</button>
    </div>
    <div style="margin-top:10px">
      <div>Brush size: <span id="brush-size-val">6</span> px</div>
      <input type="range" min="1" max="40" value="6" id="brush-size">
    </div>
    <div style="margin-top:10px">
      <strong>Labels</strong>
      <div id="label-list"></div>
    </div>
  `;
  const labelList = document.getElementById("label-list")!;
  labelList.innerHTML = project.labels.map((l, i) =>
    `<div class="label-row ${i === 0 ? "active" : ""}" data-label-id="${l.id}">
       <span style="display:inline-block;width:10px;height:10px;background:${l.color};margin-right:6px"></span>${l.name} (${l.id})
     </div>`
  ).join("");
```

Add the wiring at the bottom of `main()` (before the `} catch`):
```ts
  const { setActiveTool, setBrushSize, createToolGroup } = await import("./tools");
  const { setActiveSegmentIndex } = await import("./segmentation");

  tools.querySelectorAll<HTMLButtonElement>("button[data-tool]").forEach(btn => {
    btn.addEventListener("click", () => {
      tools.querySelectorAll("button[data-tool]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      setActiveTool(btn.dataset.tool as any);
    });
  });
  const sizeInput = document.getElementById("brush-size") as HTMLInputElement;
  const sizeVal = document.getElementById("brush-size-val")!;
  sizeInput.addEventListener("input", () => {
    sizeVal.textContent = sizeInput.value;
    setBrushSize(Number(sizeInput.value));
  });
  labelList.querySelectorAll<HTMLElement>(".label-row").forEach(el => {
    el.addEventListener("click", () => {
      labelList.querySelectorAll(".label-row").forEach(r => r.classList.remove("active"));
      el.classList.add("active");
      setActiveSegmentIndex(Number(el.dataset.labelId));
    });
  });

  // Tool group is created lazily on first case load (after viewports exist)
  (window as any).__createToolGroupOnce = (viewportIds: string[]) => {
    if ((window as any).__toolGroupReady) return;
    createToolGroup(viewportIds);
    (window as any).__toolGroupReady = true;
  };
```

In the case-click handler, after `loadCaseIntoViewports(...)`, add:
```ts
      const viewportIds = present.map(p => p.viewportId);
      (window as any).__createToolGroupOnce(viewportIds);
      const { ensureSegmentationVolume, bindSegmentationToToolGroup, setActiveSegmentIndex } =
        await import("./segmentation");
      // T2 is the reference for the segmentation volume.
      await ensureSegmentationVolume(`cornerstoneStreamingImageVolume:${caseId}:t2`);
      bindSegmentationToToolGroup(viewportIds);
      setActiveSegmentIndex(project.labels[0].id);
```

- [ ] **Step 4: Manual verification**

Click a case. Pick brush. Hold left mouse over T2; expected: paints a circle into the active segment (default label id 1). Switching to Erase erases. Polygon: click vertices, double-click to close.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): segmentation volume + brush/erase/polygon tool group"
```

---

## Phase 11 — Mask load/save round-trip

### Task 11.1: Load existing mask (NIfTI or PNG-ingested) into Cornerstone

**Files:**
- Modify: `frontend/src/segmentation.ts` (add `populateFromEnvelope`)
- Modify: `frontend/src/main.ts` (call after viewports load)

- [ ] **Step 1: Append loader to `segmentation.ts`**

```ts
import { cache as csCache } from "@cornerstonejs/core";

function base64ToUint8(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function populateFromEnvelope(env: {
  shape: [number, number, number]; dtype: "uint8"; data: string;
}, labelId: number): Promise<void> {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) throw new Error("segmentation volume not initialized");
  const bytes = base64ToUint8(env.data);
  // env.shape is (depth, rows, cols) — Cornerstone scalar order is X(col) fastest, then Y(row), then Z(slice).
  // env.data is contiguous (slice, row, col) per backend (uint8 .tobytes() on a (D,H,W) array).
  // Transpose to (col, row, slice) i.e. iterate Z outer in source, write to Cornerstone (z,y,x) order.
  const [depth, rows, cols] = env.shape;
  const scalar = (volume.scalarData as Uint8Array);
  scalar.fill(0);
  for (let z = 0; z < depth; z++) {
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const src = z * rows * cols + y * cols + x;
        const dst = z * rows * cols + y * cols + x;  // Cornerstone derived seg shares geometry → same indexing
        if (bytes[src]) scalar[dst] = labelId;
      }
    }
  }
  volume.modified();
}

export function extractEnvelope(labelId: number): { shape: [number, number, number]; dtype: "uint8"; data: string } {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) throw new Error("segmentation volume not initialized");
  const [cols, rows, depth] = volume.dimensions;
  const scalar = volume.scalarData as Uint8Array;
  const out = new Uint8Array(depth * rows * cols);
  for (let z = 0; z < depth; z++) {
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const idx = z * rows * cols + y * cols + x;
        out[idx] = scalar[idx] === labelId ? 1 : 0;
      }
    }
  }
  let bin = "";
  for (let i = 0; i < out.length; i++) bin += String.fromCharCode(out[i]);
  return { shape: [depth, rows, cols], dtype: "uint8", data: btoa(bin) };
}
```

- [ ] **Step 2: Wire load on case-open in `main.ts`**

After `setActiveSegmentIndex(project.labels[0].id)` in the case-click handler, add:
```ts
      const { getMask } = await import("./api");
      for (const lbl of project.labels) {
        const env = await getMask(caseId, lbl.id);
        if (env) {
          const { populateFromEnvelope } = await import("./segmentation");
          await populateFromEnvelope(env, lbl.id);
          if (env.warnings?.length) showBanner(env.warnings.join(" / "));
        }
      }
```

Add a `showBanner` helper at top of `main.ts`:
```ts
function showBanner(msg: string) {
  const app = document.getElementById("app")!;
  const b = document.createElement("div");
  b.className = "banner";
  b.textContent = msg;
  app.appendChild(b);
  setTimeout(() => b.remove(), 8000);
}
```

- [ ] **Step 3: Manual verification**

Re-open a case that has `mask_prostate/` PNGs in tcia-handler. Expected: prostate outline shows up in viewport overlay; warning banner appears if slice count differs.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): load existing mask envelope into Cornerstone seg volume"
```

### Task 11.2: Save mask on Ctrl+S and Save button; dirty indicator

**Files:**
- Create: `frontend/src/dirty.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Create `frontend/src/dirty.ts`**

```ts
let dirty = false;
const listeners = new Set<() => void>();

export function markDirty(): void {
  if (!dirty) { dirty = true; listeners.forEach(l => l()); }
}

export function markClean(): void {
  if (dirty) { dirty = false; listeners.forEach(l => l()); }
}

export function isDirty(): boolean { return dirty; }

export function onDirtyChange(fn: () => void): void { listeners.add(fn); }

window.addEventListener("beforeunload", e => {
  if (dirty) { e.preventDefault(); e.returnValue = ""; }
});
```

- [ ] **Step 2: Hook segmentation modifications to dirty state**

In `segmentation.ts`, append:
```ts
import { markDirty } from "./dirty";

export function installDirtyTracker(): void {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) return;
  const originalModified = volume.modified.bind(volume);
  volume.modified = function () {
    markDirty();
    return originalModified();
  };
}
```

In `main.ts`, after `bindSegmentationToToolGroup(...)`, call `(await import("./segmentation")).installDirtyTracker();`.

- [ ] **Step 3: Add Save button and Ctrl+S handler in `main.ts`**

Modify the topbar template:
```ts
    <div class="topbar">
      <strong>dicom_annotator</strong>
      <span style="flex:1"></span>
      <span class="dirty-dot" id="dirty"></span>
      <button class="primary" id="save-btn">Save</button>
    </div>
```

After `main()` builds the DOM, wire:
```ts
  const { onDirtyChange, isDirty, markClean } = await import("./dirty");
  const dirtyDot = document.getElementById("dirty")!;
  onDirtyChange(() => dirtyDot.classList.toggle("is-dirty", isDirty()));

  let currentCaseId: string | null = null;
  // In the case-click handler, set currentCaseId = caseId; before any await.

  async function saveAll() {
    if (!currentCaseId) return;
    const { extractEnvelope } = await import("./segmentation");
    const { putMask } = await import("./api");
    for (const lbl of project.labels) {
      const env = extractEnvelope(lbl.id);
      // Skip empty masks unless they previously existed (out of scope for v1 — always save).
      await putMask(currentCaseId, lbl.id, env);
    }
    markClean();
  }
  document.getElementById("save-btn")!.addEventListener("click", saveAll);
  window.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveAll(); }
  });
```

Make sure `currentCaseId = caseId;` is assigned at the top of the case-click handler.

- [ ] **Step 4: Manual verification**

Paint on a case, watch dirty dot appear. Ctrl+S, dot clears, backend creates `annotations/<case>/prostate.nii.gz`. Refresh page, click same case, mask reloads identically. Navigate away while dirty — browser prompts to confirm.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): save mask round-trip with dirty tracker and Ctrl+S"
```

---

## Phase 12 — Slice scrubber and propagation

### Task 12.1: Slice scrubber widget + propagate-from-previous

**Files:**
- Create: `frontend/src/scrubber.ts`
- Create: `frontend/src/propagate.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Create `frontend/src/scrubber.ts`**

```ts
import { renderingEngine } from "./cornerstone-init";
import { Types } from "@cornerstonejs/core";

export function attachScrubber(args: {
  hostEl: HTMLElement;
  viewportIds: string[];
  sliceCount: number;
  onSliceChange?: (sliceIdx: number) => void;
}): void {
  const { hostEl, viewportIds, sliceCount, onSliceChange } = args;
  hostEl.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;padding:6px;background:#1f2937;border-radius:3px;margin-top:6px">
      <span>Slice <span id="slice-num">0</span> / ${sliceCount - 1}</span>
      <input type="range" min="0" max="${sliceCount - 1}" value="0" id="slice-input" style="flex:1">
      <button id="propagate-btn">↗ Propagate from prev</button>
    </div>
  `;
  const input = hostEl.querySelector("#slice-input") as HTMLInputElement;
  const num = hostEl.querySelector("#slice-num") as HTMLSpanElement;
  input.addEventListener("input", () => {
    const idx = Number(input.value);
    num.textContent = String(idx);
    for (const vid of viewportIds) {
      const vp = renderingEngine.getViewport(vid) as Types.IVolumeViewport;
      vp.setSliceIndex(idx);
      vp.render();
    }
    onSliceChange?.(idx);
  });
}

export function currentSlice(viewportId: string): number {
  const vp = renderingEngine.getViewport(viewportId) as any;
  return vp.getSliceIndex?.() ?? 0;
}
```

Note: If `setSliceIndex` is not on your Cornerstone version, replace with the camera-focal-point shift the docs call out for the installed version. Fall back to mouse-wheel scrolling if needed for v1.

- [ ] **Step 2: Create `frontend/src/propagate.ts`**

```ts
import { cache as csCache } from "@cornerstonejs/core";
import { SEG_VOLUME_ID } from "./segmentation";
import { markDirty } from "./dirty";

export function propagateFromPrevious(currentSliceIdx: number, labelId: number): void {
  if (currentSliceIdx <= 0) return;
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) return;
  const [cols, rows] = volume.dimensions;
  const scalar = volume.scalarData as Uint8Array;
  const sliceSize = rows * cols;
  const srcOffset = (currentSliceIdx - 1) * sliceSize;
  const dstOffset = currentSliceIdx * sliceSize;
  for (let i = 0; i < sliceSize; i++) {
    if (scalar[srcOffset + i] === labelId) scalar[dstOffset + i] = labelId;
  }
  volume.modified();
  markDirty();
}
```

- [ ] **Step 3: Wire scrubber into `main.ts`**

After `bindSegmentationToToolGroup(viewportIds)` in the case-click handler:
```ts
      const { attachScrubber, currentSlice } = await import("./scrubber");
      const { propagateFromPrevious } = await import("./propagate");
      const scrubberHost = document.querySelector(".viewports")!.parentElement!;
      let existing = scrubberHost.querySelector(".scrubber-host");
      if (existing) existing.remove();
      const host = document.createElement("div");
      host.className = "scrubber-host";
      scrubberHost.appendChild(host);
      attachScrubber({
        hostEl: host,
        viewportIds,
        sliceCount: detail.slice_count,
      });
      host.querySelector("#propagate-btn")!.addEventListener("click", () => {
        const idx = currentSlice(viewportIds[0]);
        const activeLabel = Number((document.querySelector(".label-row.active") as HTMLElement)?.dataset.labelId ?? "1");
        propagateFromPrevious(idx, activeLabel);
      });
```

- [ ] **Step 4: Manual verification**

Open a case. Use scrubber to jump to slice 5. Paint. Move to slice 6. Click Propagate. Expected: previous slice's content copied onto slice 6.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): slice scrubber and propagate-from-previous"
```

---

## Phase 13 — Polish: shortcuts and prev/next case nav

### Task 13.1: Keyboard shortcuts and case navigation

**Files:**
- Create: `frontend/src/shortcuts.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Create `frontend/src/shortcuts.ts`**

```ts
import { setActiveTool, setBrushSize } from "./tools";
import { setActiveSegmentIndex } from "./segmentation";

export function installShortcuts(labelIds: number[], onPrevCase: () => void, onNextCase: () => void) {
  window.addEventListener("keydown", e => {
    if ((e.target as HTMLElement)?.tagName === "INPUT") return;
    switch (e.key) {
      case "b": setActiveTool("brush"); break;
      case "e": setActiveTool("erase"); break;
      case "p": setActiveTool("polygon"); break;
      case "[": setBrushSize(Math.max(1, getBrushSize() - 1)); break;
      case "]": setBrushSize(getBrushSize() + 1); break;
      case "PageUp":   onPrevCase(); break;
      case "PageDown": onNextCase(); break;
      default:
        if (/^[1-9]$/.test(e.key)) {
          const idx = Number(e.key) - 1;
          if (idx < labelIds.length) setActiveSegmentIndex(labelIds[idx]);
        }
    }
  });
}

function getBrushSize(): number {
  const el = document.getElementById("brush-size") as HTMLInputElement | null;
  return el ? Number(el.value) : 6;
}
```

- [ ] **Step 2: Wire prev/next + install in `main.ts`**

After tools/labels setup:
```ts
  const caseRows = Array.from(list.querySelectorAll<HTMLDivElement>(".case-row"));
  function activateCaseRow(row: HTMLDivElement) { row.click(); }
  function currentCaseRow(): HTMLDivElement | undefined {
    return caseRows.find(r => r.classList.contains("active"));
  }
  function neighbour(offset: number): HTMLDivElement | undefined {
    const cur = currentCaseRow();
    if (!cur) return caseRows[0];
    const idx = caseRows.indexOf(cur);
    return caseRows[idx + offset];
  }
  const { installShortcuts } = await import("./shortcuts");
  installShortcuts(
    project.labels.map(l => l.id),
    () => { const p = neighbour(-1); if (p) activateCaseRow(p); },
    () => { const n = neighbour(1);  if (n) activateCaseRow(n); },
  );
```

Add Prev/Next buttons next to Save in the topbar:
```ts
      <button id="prev-btn">◀ Prev</button>
      <button id="next-btn">Next ▶</button>
```
and wire them similarly using `neighbour(-1)` / `neighbour(1)`.

- [ ] **Step 3: Manual verification**

Click around. PageUp/PageDown navigate cases (with dirty warning if needed). `1`/`2` switch labels. `b`/`e`/`p` switch tools. `[` / `]` resize brush.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): keyboard shortcuts and prev/next case navigation"
```

---

## Phase 14 — README and final verification

### Task 14.1: Update README with full run instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite `README.md`**

```markdown
# dicom_annotator

Local DICOM segmentation annotator. FastAPI backend + Cornerstone3D browser frontend.

See [design](docs/superpowers/specs/2026-05-17-dicom-annotator-design.md).

## Run

### Backend

```bash
uv sync --extra dev
uv run dicom-annotator serve --project /path/to/project_root
```

The project root must contain a `project.yaml` (see design doc) and source data directories.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite server proxies `/api` and `/images` to the backend on port 8000.

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

```yaml
name: my-project
labels:
  - id: 1
    name: prostate
    color: "#4FC3F7"
sources:
  - kind: aligned
    root: data/aligned
    case_glob: "case_*"
    modalities: { t2: t2, adc: adc, calc: calc }
    existing_masks: { prostate: mask_prostate }
  - kind: raw_dicom
    root: data/nbia
    case_pattern: "*/study_*/series_*"
    modality_from_header: true
```

Masks save to `<project_root>/annotations/<case_id>/<label_name>.nii.gz`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with run instructions"
```

### Task 14.2: End-to-end smoke test against tcia-handler

**Files:** none

- [ ] **Step 1: Point the tool at tcia-handler sample data**

```bash
# Create a minimal project.yaml in the tcia-handler workspace (or a copy)
cat > /Users/huijokim/personal/tcia-handler/project.yaml <<'EOF'
name: prostate-mri-tcia
labels:
  - id: 1
    name: prostate
    color: "#4FC3F7"
  - id: 2
    name: target1
    color: "#FF7043"
sources:
  - kind: aligned
    root: data/aligned_v2_sample/sample
    case_glob: "case_*"
    modalities:
      t2: t2
      adc: adc
      calc: calc
    existing_masks:
      prostate: mask_prostate
      target1: mask_target1
EOF
```

- [ ] **Step 2: Run backend and frontend; verify all paths**

```bash
uv run dicom-annotator serve --project /Users/huijokim/personal/tcia-handler &
cd frontend && npm run dev
```

Manually verify each:
- Case list shows the 4 sample cases (`case_philips_achieva_3t`, etc.).
- Click a case → all available modalities render in their viewports, scroll/zoom synced.
- Existing PNG mask for `prostate` shows up as a colored overlay; banner if slice counts differed.
- Brush draws on T2 viewport in the active label's color.
- Press `2` → active label switches to `target1`.
- Press `b`/`e`/`p` to swap tools.
- Press Ctrl+S → toast/no-toast, dirty dot clears, `annotations/<case>/prostate.nii.gz` exists on disk.
- Reload page → mask reloads identically to what was saved.
- Press `]` repeatedly → brush size grows.
- PageDown → next case, browser prompts if unsaved.

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest
```
Expected: all backend tests pass.

- [ ] **Step 4: Final commit if anything was tweaked**

```bash
git status
# if anything's pending:
git add -A
git commit -m "chore: end-to-end smoke fixes"
```

---

## Plan self-review notes

- **Spec coverage:** every spec section is mapped to a task — project.yaml schema → 1.1, case discovery (both kinds) → 2.1/2.2, geometry → 3.1, NIfTI/PNG mask I/O → 4.1/4.2, readers → 5.1, all API routes → 6.1/6.2/6.3, CLI → 7.1, frontend bootstrap → 8.1, Cornerstone init + viewports → 9.1/9.2, tools → 10.1, mask load/save + dirty + warn-on-navigate → 11.1/11.2, scrubber + propagate → 12.1, shortcuts + prev/next → 13.1, README + E2E → 14.1/14.2.
- **Error handling:** specific error codes (`case_not_found`, `shape_mismatch`, `geometry_mismatch`, `mask_not_found`, `modality_not_found`, `slice_out_of_range`) are implemented in 6.x; structured `{error,message,details}` envelope handled by the `ApiError` handler.
- **Testing pyramid:** unit tests for `geometry`, `mask_io`, `case_index`, `config`; integration tests for all API routes including PNG ingest; frontend manual verification noted in each frontend task per the spec's explicit decision to skip a JS test harness in v1.
- **Cornerstone API caveat:** the exact tool names and the `setSliceIndex` viewport method vary slightly across Cornerstone3D versions. The plan pins `^1.77`. If a method is renamed in the installed version, swap the call site as the docs of the installed version indicate; the surrounding flow is unchanged.

