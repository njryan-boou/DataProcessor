"""File format registry. Additional parsers can be registered without changing routes."""
import csv
import io
import re
from pathlib import PurePosixPath
from typing import Protocol

import numpy as np
import pandas as pd

from app.config import Settings
from app.utils.errors import DataFlowError


class DatasetParser(Protocol):
    def parse(self, data: bytes, settings: Settings) -> pd.DataFrame: ...


def sanitize_filename(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = re.sub(r"[^\w. -]", "_", name).strip(" .")[:180]
    return name or "dataset.csv"


class CSVParser:
    def parse(self, data: bytes, settings: Settings) -> pd.DataFrame:
        if not data or not data.strip():
            raise DataFlowError("The file is empty.", code="empty_dataset")
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise DataFlowError("The file exceeds the upload limit.", 413, "oversized_upload")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DataFlowError("CSV files must use UTF-8 encoding.", code="invalid_csv") from exc
        if "\x00" in text:
            raise DataFlowError("The file contains invalid binary content.", code="invalid_csv")
        try:
            reader = csv.reader(io.StringIO(text), strict=True)
            header = next(reader)
            if not header or any(not name.strip() for name in header):
                raise DataFlowError("Every column must have a nonempty name.", code="invalid_csv")
            if len(header) != len(set(header)):
                raise DataFlowError("Column names must be unique.", code="invalid_csv")
            if len(header) > settings.max_columns:
                raise DataFlowError("The CSV has too many columns.", code="oversized_dataset")
            count = 0
            for row in reader:
                if not row:  # blank physical lines are ignored consistently by pandas
                    continue
                if len(row) != len(header):
                    raise DataFlowError(f"CSV row {reader.line_num} has {len(row)} fields; expected {len(header)}.", code="invalid_csv")
                count += 1
                if count > settings.max_rows:
                    raise DataFlowError("The CSV exceeds the row limit.", 413, "oversized_dataset")
            if count == 0:
                raise DataFlowError("The CSV has column names but no data rows.", code="empty_dataset")
            frame = pd.read_csv(io.StringIO(text), dtype_backend="numpy_nullable", skip_blank_lines=True)
        except (csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError, StopIteration, ValueError) as exc:
            raise DataFlowError("The file is not a valid CSV. Check its delimiters and quoting.", code="invalid_csv") from exc
        numeric = frame.select_dtypes(include="number")
        if not numeric.empty and np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
            raise DataFlowError("Numeric values must be finite; replace infinity before uploading.", code="invalid_csv")
        return frame


PARSERS: dict[str, DatasetParser] = {".csv": CSVParser()}


def parse_upload(filename: str, data: bytes, settings: Settings) -> tuple[str, pd.DataFrame]:
    safe_name = sanitize_filename(filename)
    extension = PurePosixPath(safe_name).suffix.lower()
    parser = PARSERS.get(extension)
    if parser is None:
        raise DataFlowError("Only CSV files are supported in this version.", 415, "unsupported_file")
    return safe_name, parser.parse(data, settings)
