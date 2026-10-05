"""Bounded temporary storage; replace DatasetStore to add persistence later."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
import time
from typing import Any, Protocol
from uuid import uuid4

import pandas as pd

from app.config import Settings
from app.models.schemas import ColumnInfo, DatasetMetadata, DatasetPreview, HistoryEntry, Transformation
from app.services.statistics import infer_column_type
from app.utils.errors import DataFlowError


@dataclass
class Dataset:
    id: str
    filename: str
    file_size: int
    original: pd.DataFrame
    states: list[pd.DataFrame]
    history: list[HistoryEntry]
    version: int = 0
    touched: float = field(default_factory=time.monotonic)

    @property
    def current(self) -> pd.DataFrame:
        return self.states[-1]

    @property
    def memory_bytes(self) -> int:
        return sum(int(state.memory_usage(index=True, deep=True).sum()) for state in self.states)


class DatasetStore(Protocol):
    def create(self, filename: str, data: bytes, frame: pd.DataFrame) -> DatasetMetadata: ...
    def metadata(self, dataset_id: str) -> DatasetMetadata: ...
    def frame(self, dataset_id: str) -> pd.DataFrame: ...
    def transform(self, dataset_id: str, operations: list[Transformation]) -> DatasetMetadata: ...
    def undo(self, dataset_id: str) -> DatasetMetadata: ...


class InMemoryDatasetStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.datasets: dict[str, Dataset] = {}
        self.lock = RLock()

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.settings.dataset_ttl_seconds
        for key in [key for key, value in self.datasets.items() if value.touched < cutoff]:
            del self.datasets[key]

    def _get(self, dataset_id: str) -> Dataset:
        self._expire()
        value = self.datasets.get(dataset_id)
        if value is None:
            raise DataFlowError("Dataset not found or expired. Upload the file again.", 404, "dataset_not_found")
        value.touched = time.monotonic()
        return value

    def _ensure_memory(self, extra_bytes: int) -> None:
        used = sum(dataset.memory_bytes for dataset in self.datasets.values())
        if used + extra_bytes > self.settings.max_memory_mb * 1024 * 1024:
            raise DataFlowError("Temporary storage is full. Remove a dataset or upload a smaller file.", 413, "storage_limit")

    def create(self, filename: str, data: bytes, frame: pd.DataFrame) -> DatasetMetadata:
        with self.lock:
            self._expire()
            if len(self.datasets) >= self.settings.max_datasets:
                raise DataFlowError("Too many active datasets. Remove one before uploading another.", 413, "storage_limit")
            self._ensure_memory(int(frame.memory_usage(index=True, deep=True).sum()))
            identity = str(uuid4())
            original = frame.copy(deep=True)
            dataset = Dataset(identity, filename, len(data), original, [original], [HistoryEntry(
                id=str(uuid4()), operation="upload", parameters={}, description=f"Uploaded {filename}",
                created_at=datetime.now(timezone.utc),
            )])
            self.datasets[identity] = dataset
            return self._metadata(dataset)

    def _metadata(self, dataset: Dataset) -> DatasetMetadata:
        frame = dataset.current
        return DatasetMetadata(
            id=dataset.id, filename=dataset.filename, file_size=dataset.file_size,
            rows=len(frame), column_count=len(frame.columns),
            missing_values=int(frame.isna().sum().sum()), duplicate_rows=int(frame.duplicated().sum()),
            columns=[ColumnInfo(name=str(name), type=infer_column_type(frame[name]),
                                missing=int(frame[name].isna().sum()), unique=int(frame[name].nunique(dropna=True)))
                     for name in frame.columns], version=dataset.version, history=list(dataset.history),
        )

    def metadata(self, dataset_id: str) -> DatasetMetadata:
        with self.lock:
            return self._metadata(self._get(dataset_id))

    def frame(self, dataset_id: str) -> pd.DataFrame:
        with self.lock:
            return self._get(dataset_id).current.copy(deep=True)

    def preview(self, dataset_id: str, page: int, page_size: int) -> DatasetPreview:
        with self.lock:
            frame = self._get(dataset_id).current
            sample = frame.iloc[(page - 1) * page_size:page * page_size]
            # pandas JSON conversion normalizes missing values, dates and numpy scalars.
            import json
            records: list[dict[str, Any]] = json.loads(sample.to_json(orient="records", date_format="iso"))
            return DatasetPreview(columns=list(frame.columns), rows=records, total=len(frame), page=page, page_size=page_size)

    def transform(self, dataset_id: str, operations: list[Transformation]) -> DatasetMetadata:
        from app.services.transformations import apply_transformation
        with self.lock:
            dataset = self._get(dataset_id)
            if len(dataset.states) - 1 + len(operations) > self.settings.history_limit:
                raise DataFlowError(f"Undo history is limited to {self.settings.history_limit} steps. Export and re-upload to start a new pipeline.", 409, "history_limit")
            pending: list[pd.DataFrame] = []
            current = dataset.current
            for operation in operations:
                current = apply_transformation(current, operation).reset_index(drop=True)
                if len(current.columns) > self.settings.max_columns or len(current) > self.settings.max_rows:
                    raise DataFlowError("The result exceeds dataset limits.", 413, "oversized_dataset")
                pending.append(current)
                # Check every intermediate snapshot; no state is changed until all steps pass.
                self._ensure_memory(sum(int(state.memory_usage(index=True, deep=True).sum()) for state in pending))
            dataset.states.extend(pending)
            dataset.history.extend(HistoryEntry(
                id=str(uuid4()), operation=operation.operation, parameters=operation.parameters,
                description=describe_operation(operation), created_at=datetime.now(timezone.utc),
            ) for operation in operations)
            dataset.version += 1
            return self._metadata(dataset)

    def undo(self, dataset_id: str) -> DatasetMetadata:
        with self.lock:
            dataset = self._get(dataset_id)
            if len(dataset.states) == 1:
                raise DataFlowError("There are no transformations to undo.", 409, "nothing_to_undo")
            dataset.states.pop()
            dataset.history.pop()
            dataset.version += 1
            return self._metadata(dataset)

    def delete(self, dataset_id: str) -> None:
        with self.lock:
            self._get(dataset_id)
            del self.datasets[dataset_id]


def describe_operation(operation: Transformation) -> str:
    label = operation.operation.replace("_", " ").capitalize()
    values = operation.parameters
    if "column" in values:
        label += f" · {values['column']}"
    if operation.operation == "fill_missing":
        label += f" ({values.get('method', 'custom')})"
    if operation.operation == "filter":
        label += f" {values.get('operator', '')} {values.get('value', '')}".rstrip()
    return label
