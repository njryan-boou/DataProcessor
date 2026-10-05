"""Chart data validates types, bounds output, and ignores unavailable rows."""

import json

import numpy as np
import pandas as pd
import pytest

from app.services.charts import chart_data
from app.utils.errors import DataFlowError


def test_histogram_counts_rows_and_omits_missing_or_infinite_values() -> None:
    frame = pd.DataFrame({"value": [0, 1, 2, 3, None, np.inf]})
    before = frame.copy(deep=True)
    result = chart_data(frame, "histogram", "value", bins=2)
    assert sum(point["count"] for point in result["points"]) == 4
    assert [point["count"] for point in result["points"]] == [2, 2]
    assert result["omitted_rows"] == 2
    assert result["sampled"] is False
    json.dumps(result, allow_nan=False)
    pd.testing.assert_frame_equal(frame, before)


def test_constant_histogram_does_not_fail() -> None:
    result = chart_data(pd.DataFrame({"value": [5] * 3}), "histogram", "value")
    assert sum(point["count"] for point in result["points"]) == 3


def test_histogram_handles_extreme_finite_numeric_ranges() -> None:
    result = chart_data(pd.DataFrame({"value": [-1e308, 0, 1e308]}), "histogram", "value", bins=3)
    json.dumps(result, allow_nan=False)
    assert sum(point["count"] for point in result["points"]) == 3


def test_bar_mean_does_not_overflow_for_finite_large_values() -> None:
    result = chart_data(pd.DataFrame({"team": ["A", "A"], "score": [1e308, 1e308]}), "bar", "team", "score")
    assert result["points"][0]["value"] == pytest.approx(1e308)
    json.dumps(result, allow_nan=False)


def test_bar_counts_categories_and_aggregates_mean_when_y_is_supplied() -> None:
    frame = pd.DataFrame({"team": ["A", "B", "A", None], "score": [10, 20, 30, 40]})
    counts = chart_data(frame, "bar", "team")
    assert counts["points"] == [
        {"label": "A", "value": 2, "count": 2},
        {"label": "B", "value": 1, "count": 1},
    ]
    means = chart_data(frame, "bar", "team", "score")
    assert means["points"] == [
        {"label": "A", "value": 20, "count": 2},
        {"label": "B", "value": 20, "count": 1},
    ]
    assert means["omitted_rows"] == 1


def test_bar_supports_numeric_categories_and_bounds_high_cardinality() -> None:
    frame = pd.DataFrame({"value": np.arange(80)})
    result = chart_data(frame, "bar", "value")
    assert len(result["points"]) == 30
    assert result["sampled"] is True
    assert result["excluded_categories"] == 50
    assert result["omitted_rows"] == 0


def test_bar_omits_missing_y_and_nonfinite_values() -> None:
    frame = pd.DataFrame({"team": ["A", "A", "B", "B"], "score": [1, None, np.inf, 4]})
    result = chart_data(frame, "bar", "team", "score")
    assert result["omitted_rows"] == 2
    assert result["points"] == [
        {"label": "A", "value": 1, "count": 1},
        {"label": "B", "value": 4, "count": 1},
    ]


def test_line_is_sorted_and_supports_datetimes() -> None:
    frame = pd.DataFrame({
        "day": pd.to_datetime(["2026-01-03", "2026-01-01", None]),
        "score": [3, 1, 7],
    })
    result = chart_data(frame, "line", "day", "score")
    assert result["points"] == [
        {"x": "2026-01-01T00:00:00", "y": 1},
        {"x": "2026-01-03T00:00:00", "y": 3},
    ]
    assert result["omitted_rows"] == 1
    assert result["sampled"] is False


@pytest.mark.parametrize("kind", ["line", "scatter"])
def test_large_numeric_charts_sample_deterministically_and_preserve_endpoints(kind: str) -> None:
    frame = pd.DataFrame({"x": np.arange(5000), "y": np.arange(5000) * 2})
    before = frame.copy(deep=True)
    result = chart_data(frame, kind, "x", "y")
    assert len(result["points"]) == 2000
    assert result["sampled"] is True
    assert result["points"][0] == {"x": 0, "y": 0}
    assert result["points"][-1] == {"x": 4999, "y": 9998}
    assert chart_data(frame, kind, "x", "y") == result
    pd.testing.assert_frame_equal(frame, before)


def test_scatter_drops_missing_pairs_and_allows_same_column_on_both_axes() -> None:
    frame = pd.DataFrame({"x": [1, 2, None], "y": [None, 2, 3]})
    result = chart_data(frame, "scatter", "x", "y")
    assert result["points"] == [{"x": 2, "y": 2}]
    assert result["omitted_rows"] == 2
    assert len(chart_data(frame, "scatter", "x", "x")["points"]) == 2


def test_box_reports_quartiles_and_iqr_outliers() -> None:
    result = chart_data(pd.DataFrame({"score": [1, 1, 1, 1, 100, None]}), "box", "score")
    assert result["points"] == [{
        "label": "score", "min": 1, "q1": 1, "median": 1, "q3": 1, "max": 1, "outliers": [100],
    }]
    assert result["omitted_rows"] == 1


@pytest.mark.parametrize(
    ("kind", "x", "y", "bins"),
    [
        ("pie", "number", None, 20),
        ("histogram", "missing", None, 20),
        ("histogram", "text", None, 20),
        ("histogram", "boolean", None, 20),
        ("histogram", "number", "number", 20),
        ("histogram", "number", None, 0),
        ("histogram", "number", None, 101),
        ("histogram", "number", None, True),
        ("histogram", "number", None, 1.5),
        ("line", "text", "number", 20),
        ("line", "number", "text", 20),
        ("line", "number", None, 20),
        ("scatter", "date", "number", 20),
        ("bar", "date", None, 20),
        ("bar", "text", "boolean", 20),
        ("box", "text", None, 20),
        ("box", "number", "number", 20),
    ],
)
def test_invalid_chart_combinations_raise_domain_error(kind: str, x: str, y: str | None, bins: int) -> None:
    frame = pd.DataFrame({
        "number": [1, 2], "text": ["a", "b"], "boolean": [True, False],
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
    })
    with pytest.raises(DataFlowError):
        chart_data(frame, kind, x, y, bins)


@pytest.mark.parametrize("kind", ["histogram", "box", "bar", "scatter", "line"])
def test_empty_valid_chart_data_has_clear_error(kind: str) -> None:
    frame = pd.DataFrame({"x": [np.nan], "y": [np.inf]})
    y = "y" if kind in {"scatter", "line"} else None
    with pytest.raises(DataFlowError):
        chart_data(frame, kind, "x", y)
