from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ColumnType = Literal["numeric", "text", "boolean", "datetime"]
OperationName = Literal[
    "remove_duplicates", "drop_missing", "fill_missing", "rename_column",
    "delete_columns", "filter", "sort", "convert_type", "trim_whitespace",
    "change_case", "detect_outliers", "select_columns",
]


class Transformation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: OperationName
    parameters: dict[str, Any] = Field(default_factory=dict)


class TransformationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operations: list[Transformation] = Field(min_length=1, max_length=20)


class ColumnInfo(BaseModel):
    name: str
    type: ColumnType
    missing: int
    unique: int


class HistoryEntry(BaseModel):
    id: str
    operation: str
    parameters: dict[str, Any]
    description: str
    created_at: datetime


class DatasetMetadata(BaseModel):
    id: str
    filename: str
    file_size: int
    rows: int
    column_count: int
    missing_values: int
    duplicate_rows: int
    columns: list[ColumnInfo]
    version: int
    history: list[HistoryEntry]


class DatasetPreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class Frequency(BaseModel):
    value: Any
    count: int


class ColumnStatistics(BaseModel):
    name: str
    type: ColumnType
    count: int
    missing: int
    unique: int
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    min: Any = None
    max: Any = None
    q1: float | None = None
    q3: float | None = None
    top_values: list[Frequency] = Field(default_factory=list)
    outlier_count: int = 0


class Recommendation(BaseModel):
    code: str
    message: str
    column: str | None = None


class DatasetStatistics(BaseModel):
    columns: list[ColumnStatistics]
    warnings: list[Recommendation]
    duplicate_rows: int


class ChartResponse(BaseModel):
    kind: str
    x: str
    y: str | None = None
    points: list[dict[str, Any]]
    omitted_rows: int = 0
    sampled: bool = False
    excluded_categories: int = 0


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=2000)


class AssistantPlan(BaseModel):
    operations: list[Transformation]
    provider: str
    explanation: str
