from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import AlignedSource, Project, RawDicomSource


@dataclass(frozen=True)
class CaseEntry:
    id: str
    kind: Literal["aligned", "raw_dicom"]
    modalities: tuple[str, ...]
    annotated: bool
    labels_present: tuple[str, ...]
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
            entries.extend(_discover_raw_dicom(project_root, source, src_idx, annotations_root))
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
        case_id = "__".join(case_dir.relative_to(root).parts)
        ann_dir = annotations_root / case_id
        labels_present, annotated = _labels_present(ann_dir)
        entries.append(
            CaseEntry(
                id=case_id,
                kind="aligned",
                modalities=tuple(present),
                annotated=annotated,
                labels_present=tuple(labels_present),
                case_dir=case_dir,
                source_index=source_index,
            )
        )
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
                modalities=("series",),
                annotated=annotated,
                labels_present=labels_present,
                case_dir=series_dir,
                source_index=source_index,
            )
        )
    return entries


def _labels_present(ann_dir: Path) -> tuple[tuple[str, ...], bool]:
    if not ann_dir.is_dir():
        return (), False
    labels = tuple(sorted(p.name.removesuffix(".nii.gz") for p in ann_dir.glob("*.nii.gz")))
    return labels, len(labels) > 0
