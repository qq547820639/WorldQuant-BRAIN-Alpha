"""Data schemas matching official WorldQuant BRAIN API JSON structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DatasetRef:
    """Nested dataset reference inside official_fields.json records."""
    id: str
    name: str


@dataclass
class OfficialField:
    """Single field record from official_fields.json."""
    id: str
    description: str = ""
    dataset: Optional[DatasetRef] = None
    category: str = ""
    region: str = "USA"
    delay: int = 1
    universe: str = "TOP3000"
    type: str = "MATRIX"
    coverage: float = 0.0
    userCount: int = 0
    alphaCount: int = 0


@dataclass
class OfficialOperator:
    """Single operator record from official_operators.json."""
    name: str
    category: str = ""
    definition: str = ""
    description: str = ""


@dataclass
class OfficialDataset:
    """Single dataset record from official_datasets.json."""
    id: str
    name: str
    field_count: int = 0
