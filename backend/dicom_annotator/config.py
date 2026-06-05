from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


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
    AlignedSource | RawDicomSource,
    Field(discriminator="kind"),
]


class Project(BaseModel):
    name: str
    labels: list[Label]
    sources: list[Source]

    @model_validator(mode="after")
    def _labels_unique(self) -> "Project":
        ids = [lbl.id for lbl in self.labels]
        names = [lbl.name for lbl in self.labels]
        if len(set(ids)) != len(ids):
            raise ValueError("label ids must be unique")
        # Names map to mask filenames (<name>.nii.gz); duplicates would overwrite.
        if len(set(names)) != len(names):
            raise ValueError("label names must be unique")
        return self


def load_project(project_root: Path) -> Project:
    """Load `project.yaml` from a project root directory."""
    config_path = project_root / "project.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"project.yaml not found at {config_path}")
    data = yaml.safe_load(config_path.read_text())
    return Project.model_validate(data)
