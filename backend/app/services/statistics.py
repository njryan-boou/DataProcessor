"""Describe datasets without modifying their contents."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

ColumnType = Literal["numeric", "text", "boolean", "datetime"]


def infer_column_type(series: pd.Series) -> ColumnType:
    """Use the dtype of the parsed or explicitly converted column."""
    if is_bool_dtype(series.dtype):
        return "boolean"
    if is_numeric_dtype(series.dtype):
        return "numeric"
    if is_datetime64_any_dtype(series.dtype):
        return "datetime"
    return "text"


def json_scalar(value: Any) -> Any:
    """Convert pandas/numpy scalar values to finite, JSON-compatible values."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, (bool, int, str)):
        return value
    return str(value)


def finite_numeric(series: pd.Series) -> pd.Series:
    """Keep finite numeric observations while preserving their original index."""
    values = series.astype(float)
    return values[np.isfinite(values)]


def outlier_mask(values: pd.Series) -> pd.Series:
    """Flag potential outliers using the conventional 1.5 × IQR rule."""
    if values.empty:
        return pd.Series(False, index=values.index, dtype=bool)
    scale = float(values.abs().max()) or 1.0
    normalized = values / scale
    q1, q3 = normalized.quantile([0.25, 0.75])
    iqr = q3 - q1
    return (normalized < q1 - 1.5 * iqr) | (normalized > q3 + 1.5 * iqr)


def compute_statistics(df: pd.DataFrame) -> dict[str, Any]:
    """Return column summaries and recommendations, preserving the dataset."""
    columns: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    row_count = len(df)
    duplicate_rows = int(df.duplicated().sum())

    for name in df.columns:
        series = df[name]
        column_name = str(name)
        column_type = infer_column_type(series)
        missing = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        summary: dict[str, Any] = {
            "name": column_name,
            "type": column_type,
            "count": int(series.count()),
            "missing": missing,
            "unique": unique,
            "mean": None,
            "median": None,
            "std": None,
            "min": None,
            "max": None,
            "q1": None,
            "q3": None,
            "top_values": [],
            "outlier_count": 0,
        }

        if column_type == "numeric":
            values = finite_numeric(series)
            if not values.empty:
                # Scale intermediate arithmetic so large finite inputs do not overflow.
                scale = float(values.abs().max()) or 1.0
                normalized = values / scale
                summary.update(
                    mean=json_scalar(float(normalized.mean()) * scale),
                    median=json_scalar(float(normalized.median()) * scale),
                    std=json_scalar(float(normalized.std(ddof=1)) * scale),
                    min=json_scalar(values.min()),
                    max=json_scalar(values.max()),
                    q1=json_scalar(float(normalized.quantile(0.25)) * scale),
                    q3=json_scalar(float(normalized.quantile(0.75)) * scale),
                    outlier_count=int(outlier_mask(values).sum()),
                )
            non_finite = int(series.count()) - len(values)
            if non_finite:
                warnings.append({
                    "code": "non_finite_numeric",
                    "column": column_name,
                    "message": f"{column_name}: {non_finite} infinite values were excluded from numeric summaries.",
                })
            if summary["outlier_count"]:
                warnings.append({
                    "code": "outliers",
                    "column": column_name,
                    "message": f"{column_name}: {summary['outlier_count']} potential outliers using the 1.5 × IQR rule.",
                })
        else:
            counts = series.value_counts(dropna=True).head(10)
            summary["top_values"] = [
                {"value": json_scalar(value), "count": int(count)}
                for value, count in counts.items()
            ]

        if row_count and missing / row_count > 0.3:
            warnings.append({
                "code": "high_missing",
                "column": column_name,
                "message": f"{column_name}: {missing / row_count:.0%} of values are missing.",
            })
        if unique == 1:
            warnings.append({
                "code": "constant_column",
                "column": column_name,
                "message": f"{column_name} has only one distinct non-missing value.",
            })
        columns.append(summary)

    if duplicate_rows:
        warnings.append({
            "code": "duplicate_rows",
            "message": f"{duplicate_rows} duplicate rows found. Review them before removing.",
        })
    return {"columns": columns, "warnings": warnings, "duplicate_rows": duplicate_rows}
