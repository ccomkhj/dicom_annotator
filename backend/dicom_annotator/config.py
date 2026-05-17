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
