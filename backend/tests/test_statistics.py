"""Statistics describe the current dataset and never change it."""

import json

import numpy as np
import pandas as pd
import pytest

from app.services.statistics import compute_statistics, infer_column_type


def test_numeric_summary_includes_sample_std_quartiles_and_missing() -> None:
    frame = pd.DataFrame({"age": [10, 20, 30, 40, None]})
    before = frame.copy(deep=True)
    result = compute_statistics(frame)
    column = result["columns"][0]
    assert column["type"] == "numeric"
    assert column["count"] == 4
    assert column["missing"] == 1
    assert column["unique"] == 4
    assert column["mean"] == 25
    assert column["median"] == 25
    assert column["std"] == pytest.approx(12.9099444874)
    assert column["min"] == 10
    assert column["max"] == 40
    assert column["q1"] == 17.5
    assert column["q3"] == 32.5
    pd.testing.assert_frame_equal(frame, before)


def test_text_frequency_counts_exclude_missing_values() -> None:
    result = compute_statistics(pd.DataFrame({"team": ["A", "B", "A", None]}))
    column = result["columns"][0]
    assert column["unique"] == 2
    assert column["count"] == 3
    assert column["missing"] == 1
    assert column["top_values"] == [{"value": "A", "count": 2}, {"value": "B", "count": 1}]
    assert column["mean"] is None


def test_top_value_list_is_bounded() -> None:
    result = compute_statistics(pd.DataFrame({"category": [f"c{i}" for i in range(30)]}))
    assert result["columns"][0]["unique"] == 30
    assert len(result["columns"][0]["top_values"]) == 10


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        (pd.Series([1, 2]), "numeric"),
        (pd.Series([1, None], dtype="Int64"), "numeric"),
        (pd.Series([True, False]), "boolean"),
        (pd.Series([True, None], dtype="boolean"), "boolean"),
        (pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02"])), "datetime"),
        (pd.Series(["2026-01-01", "2026-01-02"]), "text"),
        (pd.Series(["a", "b"]), "text"),
    ],
)
def test_type_inference_uses_actual_dtype(series: pd.Series, expected: str) -> None:
    assert infer_column_type(series) == expected


def test_recommendations_report_duplicates_missing_constant_and_outliers() -> None:
    frame = pd.DataFrame({
        "score": [1, 1, 1, 1, 100],
        "constant": ["same"] * 5,
        "sparse": [None, None, None, "a", "b"],
    })
    before = frame.copy(deep=True)
    result = compute_statistics(frame)
    assert result["duplicate_rows"] == 2
    assert result["columns"][0]["outlier_count"] == 1
    codes = {(warning["code"], warning.get("column")) for warning in result["warnings"]}
    assert ("duplicate_rows", None) in codes
    assert ("outliers", "score") in codes
    assert ("constant_column", "constant") in codes
    assert ("high_missing", "sparse") in codes
    pd.testing.assert_frame_equal(frame, before)


def test_nonfinite_and_small_numeric_samples_produce_valid_json() -> None:
    frame = pd.DataFrame({"value": [np.inf, -np.inf, np.nan, 7.0]})
    result = compute_statistics(frame)
    json.dumps(result, allow_nan=False)
    column = result["columns"][0]
    assert column["mean"] == 7
    assert column["std"] is None
    assert column["missing"] == 1
    assert column["count"] == 3
    assert any(warning["code"] == "non_finite_numeric" for warning in result["warnings"])


def test_extreme_finite_values_have_finite_descriptive_statistics() -> None:
    result = compute_statistics(pd.DataFrame({"value": [-1e308, 1e308]}))
    json.dumps(result, allow_nan=False)
    column = result["columns"][0]
    assert column["mean"] == 0
    assert column["median"] == 0
    assert column["std"] == pytest.approx(1.4142135623730951e308)
    assert column["q1"] == pytest.approx(-5e307)
    assert column["q3"] == pytest.approx(5e307)


def test_empty_and_all_missing_columns_are_safe() -> None:
    assert compute_statistics(pd.DataFrame()) == {"columns": [], "warnings": [], "duplicate_rows": 0}
    result = compute_statistics(pd.DataFrame({"value": [None, None]}))
    json.dumps(result, allow_nan=False)
    assert result["columns"][0]["count"] == 0
    assert result["columns"][0]["unique"] == 0
    assert result["columns"][0]["mean"] is None


def test_datetime_and_boolean_frequency_values_are_json_safe() -> None:
    result = compute_statistics(pd.DataFrame({
        "active": pd.Series([True, False, None], dtype="boolean"),
        "day": pd.to_datetime(["2026-01-01", "2026-01-01", None]),
    }))
    json.dumps(result, allow_nan=False)
    assert result["columns"][0]["type"] == "boolean"
    assert result["columns"][1]["top_values"] == [{"value": "2026-01-01T00:00:00", "count": 2}]
