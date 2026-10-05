"""Prepare bounded, type-safe chart data for the frontend."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.statistics import finite_numeric, infer_column_type, json_scalar, outlier_mask
from app.utils.errors import DataFlowError

MAX_POINTS = 2000
MAX_CATEGORIES = 30
CHART_KINDS = {"histogram", "bar", "line", "scatter", "box"}


def _invalid(message: str) -> DataFlowError:
    return DataFlowError(message, status_code=400, code="invalid_chart")


def _numeric_column(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in df.columns:
        raise _invalid(f"Column {column!r} does not exist.")
    series = df[column]
    if infer_column_type(series) != "numeric":
        raise _invalid(f"Column {column!r} must be numeric for this chart.")
    return series


def _sample(frame: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if len(frame) <= MAX_POINTS:
        return frame, False
    indices = np.linspace(0, len(frame) - 1, MAX_POINTS, dtype=int)
    return frame.iloc[indices], True


def chart_data(
    df: pd.DataFrame,
    kind: str,
    x: str,
    y: str | None = None,
    bins: int = 20,
) -> dict[str, Any]:
    """Validate chart semantics and return finite JSON with bounded points."""
    if kind not in CHART_KINDS:
        raise _invalid(f"Unsupported chart type: {kind!r}.")
    if x not in df.columns:
        raise _invalid(f"Column {x!r} does not exist.")
    if kind in {"histogram", "box"} and y is not None:
        raise _invalid(f"A {kind} uses only one numeric column.")

    result: dict[str, Any] = {
        "kind": kind,
        "x": x,
        "y": y,
        "points": [],
        "omitted_rows": 0,
        "sampled": False,
    }

    if kind in {"histogram", "box"}:
        values = finite_numeric(_numeric_column(df, x))
        if values.empty:
            raise _invalid(f"Column {x!r} has no finite numeric values to plot.")
        result["omitted_rows"] = len(df) - len(values)
        if kind == "histogram":
            if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= 100:
                raise _invalid("Histogram bins must be an integer between 1 and 100.")
            # Normalization prevents overflow when finite values span a huge range.
            scale = float(values.abs().max()) or 1.0
            if values.min() == values.max():
                counts = np.array([len(values)])
                edges = np.array([values.iloc[0], values.iloc[0]])
            else:
                try:
                    counts, edges = np.histogram(values.to_numpy() / scale, bins=bins)
                    edges *= scale
                except (ValueError, IndexError, OverflowError) as exc:
                    raise _invalid("This numeric range cannot be divided into the requested bins. Try fewer bins.") from exc
            result["points"] = [
                {
                    "label": f"{edges[i]:.4g} – {edges[i + 1]:.4g}",
                    "start": json_scalar(edges[i]),
                    "end": json_scalar(edges[i + 1]),
                    "count": int(count),
                }
                for i, count in enumerate(counts)
            ]
        else:
            mask = outlier_mask(values)
            outliers = values[mask]
            whiskers = values[~mask]
            scale = float(values.abs().max()) or 1.0
            normalized = values / scale
            outlier_frame, sampled = _sample(outliers.to_frame())
            result["sampled"] = sampled
            result["points"] = [{
                "label": x,
                "min": json_scalar(whiskers.min()),
                "q1": json_scalar(float(normalized.quantile(0.25)) * scale),
                "median": json_scalar(float(normalized.median()) * scale),
                "q3": json_scalar(float(normalized.quantile(0.75)) * scale),
                "max": json_scalar(whiskers.max()),
                "outliers": [json_scalar(value) for value in outlier_frame.iloc[:, 0]],
            }]
        return result

    if kind == "bar":
        if infer_column_type(df[x]) == "datetime":
            raise _invalid("Use a line chart for a datetime X column.")
        valid = df[x].notna()
        if infer_column_type(df[x]) == "numeric":
            valid &= np.isfinite(df[x].astype(float))
        if y is not None:
            valid &= np.isfinite(_numeric_column(df, y).astype(float))
        frame = df.loc[valid]
        if frame.empty:
            raise _invalid("There are no complete, finite rows to plot.")
        result["omitted_rows"] = len(df) - len(frame)
        counts = frame[x].value_counts(dropna=True)
        categories = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        result["sampled"] = len(categories) > MAX_CATEGORIES
        result["excluded_categories"] = max(0, len(categories) - MAX_CATEGORIES)
        selected = categories[:MAX_CATEGORIES]
        means = None
        if y is not None:
            scale = float(frame[y].abs().max()) or 1.0
            means = (frame[y] / scale).groupby(frame[x], observed=True).mean() * scale
        result["points"] = [
            {
                "label": str(json_scalar(category)),
                "value": json_scalar(means.loc[category]) if means is not None else int(count),
                "count": int(count),
            }
            for category, count in selected
        ]
        return result

    y_series = _numeric_column(df, y)
    x_type = infer_column_type(df[x])
    if kind == "scatter" and x_type != "numeric":
        raise _invalid("A scatter plot requires numeric X and Y columns.")
    if kind == "line" and x_type not in {"numeric", "datetime"}:
        raise _invalid("A line chart requires a numeric or datetime X column and a numeric Y column.")
    valid = np.isfinite(y_series.astype(float))
    valid &= df[x].notna() if x_type == "datetime" else np.isfinite(df[x].astype(float))
    # Named intermediate columns also support plotting the same column on both axes.
    frame = pd.DataFrame({"x": df[x], "y": y_series}).loc[valid]
    if frame.empty:
        raise _invalid("There are no complete, finite rows to plot.")
    result["omitted_rows"] = len(df) - len(frame)
    if kind == "line":
        frame = frame.sort_values("x", kind="stable")
    frame, result["sampled"] = _sample(frame)
    result["points"] = [
        {"x": json_scalar(x_value), "y": json_scalar(y_value)}
        for x_value, y_value in frame.itertuples(index=False, name=None)
    ]
    return result
