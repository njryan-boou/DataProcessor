"""Transformation behavior, strict validation, and immutable-source guarantees."""

import math

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from app.models.schemas import Transformation
from app.services.transformations import apply_transformation
from app.utils.errors import DataFlowError


def transform(df: pd.DataFrame, name: str, **parameters) -> pd.DataFrame:
    return apply_transformation(df, Transformation(operation=name, parameters=parameters))


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame({"age": [20.0, 40.0, None, 40.0], "name": [" Ada ", "Bob", None, "Bob"]})


def test_remove_duplicates_and_source_is_unchanged(frame):
    original = frame.copy(deep=True)
    result = transform(frame, "remove_duplicates")
    assert len(result) == 3
    assert result.index.tolist() == [0, 1, 2]
    assert_frame_equal(frame, original)
    result.iloc[0, 0] = 99
    assert_frame_equal(frame, original)


def test_remove_duplicates_subset(frame):
    result = transform(frame, "remove_duplicates", subset=["name"])
    assert len(result) == 3


def test_drop_missing_all_or_selected_columns(frame):
    assert len(transform(frame, "drop_missing")) == 3
    frame.loc[0, "name"] = None
    assert len(transform(frame, "drop_missing", columns=["age"])) == 3
    assert len(transform(frame, "drop_missing")) == 2


@pytest.mark.parametrize("method,expected", [("mean", 100 / 3), ("median", 40), ("zero", 0)])
def test_fill_numeric_missing(frame, method, expected):
    result = transform(frame, "fill_missing", column="age", method=method)
    assert result.loc[2, "age"] == pytest.approx(expected)
    assert math.isnan(frame.loc[2, "age"])


def test_custom_numeric_and_text_filling(frame):
    numeric = transform(frame, "fill_missing", column="age", method="custom", value=25)
    text = transform(frame, "fill_missing", column="name", method="custom", value="Unknown")
    assert numeric.loc[2, "age"] == 25
    assert text.loc[2, "name"] == "Unknown"


def test_fractional_fill_widens_nullable_integer():
    source = pd.DataFrame({"number": pd.Series([1, 2, None], dtype="Int64")})
    result = transform(source, "fill_missing", column="number", method="mean")
    assert result.loc[2, "number"] == 1.5
    assert source["number"].dtype == "Int64"


def test_mean_of_all_missing_column_fails():
    source = pd.DataFrame({"number": pd.Series([None, None], dtype="float64")})
    with pytest.raises(DataFlowError, match="no numeric values"):
        transform(source, "fill_missing", column="number", method="mean")


@pytest.mark.parametrize("operator,value,expected", [
    (">", 20, [40, 40]), (">=", 40, [40, 40]), ("<", 40, [20]),
    ("<=", 20, [20]), ("==", 40, [40, 40]), ("!=", 40, [20]),
])
def test_numeric_filters_exclude_missing(frame, operator, value, expected):
    result = transform(frame, "filter", column="age", operator=operator, value=value)
    assert result["age"].tolist() == expected


def test_missing_filters(frame):
    assert len(transform(frame, "filter", column="age", operator="is_missing")) == 1
    assert len(transform(frame, "filter", column="age", operator="not_missing")) == 3


def test_contains_is_literal_and_excludes_missing():
    df = pd.DataFrame({"text": ["a.*b", "abc", None]})
    result = transform(df, "filter", column="text", operator="contains", value=".*")
    assert result["text"].tolist() == ["a.*b"]
    result = transform(df, "filter", column="text", operator="not_contains", value=".*")
    assert result["text"].tolist() == ["abc"]


def test_stable_sort_and_missing_last(frame):
    result = transform(frame, "sort", column="age", ascending=False)
    assert result["age"].iloc[:3].tolist() == [40, 40, 20]
    assert pd.isna(result["age"].iloc[-1])


def test_convert_numeric_keeps_missing():
    source = pd.DataFrame({"number": ["1", "2.5", None]})
    result = transform(source, "convert_type", column="number", type="numeric")
    assert result["number"].iloc[:2].tolist() == [1, 2.5]
    assert pd.isna(result.loc[2, "number"])


def test_invalid_numeric_conversion_is_atomic():
    source = pd.DataFrame({"number": ["1", "not-a-number"]})
    original = source.copy(deep=True)
    with pytest.raises(DataFlowError, match="cannot be converted to numeric"):
        transform(source, "convert_type", column="number", type="numeric")
    assert_frame_equal(source, original)


@pytest.mark.parametrize("infinite", ["inf", "-inf", "Infinity"])
def test_numeric_conversion_rejects_nonfinite(infinite):
    with pytest.raises(DataFlowError, match="non-finite"):
        transform(pd.DataFrame({"number": ["1", infinite]}), "convert_type", column="number", type="numeric")


def test_convert_boolean_uses_explicit_mapping():
    df = pd.DataFrame({"flag": ["false", "true", "NO", " yes ", "0", "1", None]})
    result = transform(df, "convert_type", column="flag", type="boolean")
    assert result["flag"].iloc[:6].tolist() == [False, True, False, True, False, True]
    assert pd.isna(result.loc[6, "flag"])
    with pytest.raises(DataFlowError, match="cannot be converted to boolean"):
        transform(pd.DataFrame({"flag": ["false", "anything"]}), "convert_type", column="flag", type="boolean")


def test_convert_datetime_and_text():
    df = pd.DataFrame({"date": ["2025-01-01", None], "number": [1.5, None]})
    dates = transform(df, "convert_type", column="date", type="datetime")
    assert dates.loc[0, "date"] == pd.Timestamp("2025-01-01", tz="UTC")
    assert pd.isna(dates.loc[1, "date"])
    text = transform(df, "convert_type", column="number", type="text")
    assert text.loc[0, "number"] == "1.5"
    assert pd.isna(text.loc[1, "number"])
    with pytest.raises(DataFlowError, match="cannot be converted to datetime"):
        transform(pd.DataFrame({"date": ["invalid"]}), "convert_type", column="date", type="datetime")


def test_rename_delete_and_column_selection(frame):
    renamed = transform(frame, "rename_column", column="age", new_name="years")
    assert renamed.columns.tolist() == ["years", "name"]
    selected = transform(renamed, "select_columns", columns=["name", "years"])
    assert selected.columns.tolist() == ["name", "years"]
    deleted = transform(selected, "delete_columns", columns=["years"])
    assert deleted.columns.tolist() == ["name"]
    assert frame.columns.tolist() == ["age", "name"]


def test_trim_and_change_case(frame):
    trimmed = transform(frame, "trim_whitespace")
    assert trimmed.loc[0, "name"] == "Ada"
    assert trimmed.loc[0, "age"] == 20
    assert pd.isna(trimmed.loc[2, "name"])
    upper = transform(trimmed, "change_case", column="name", case="upper")
    lower = transform(upper, "change_case", column="name", case="lower")
    assert upper.loc[0, "name"] == "ADA"
    assert lower.loc[0, "name"] == "ada"


def test_outliers_are_flagged_without_removing_rows():
    df = pd.DataFrame({"value": [1, 2, 2, 3, 4, 100, None]})
    result = transform(df, "detect_outliers", column="value")
    assert len(result) == len(df)
    assert result["value_outlier"].tolist() == [False, False, False, False, False, True, False]
    assert df.columns.tolist() == ["value"]
    with pytest.raises(DataFlowError, match="already exists"):
        transform(result, "detect_outliers", column="value")


@pytest.mark.parametrize("name,params", [
    ("remove_duplicates", {"unused": True}),
    ("remove_duplicates", {"subset": []}),
    ("drop_missing", {"columns": []}),
    ("drop_missing", {"columns": ["missing"]}),
    ("fill_missing", {"column": "age", "method": "custom"}),
    ("fill_missing", {"column": "age", "method": "mean", "value": 1}),
    ("fill_missing", {"column": "age", "method": "custom", "value": "1"}),
    ("fill_missing", {"column": "name", "method": "custom", "value": 1}),
    ("fill_missing", {"column": "name", "method": "mean"}),
    ("rename_column", {"column": "age", "new_name": "name"}),
    ("rename_column", {"column": "age", "new_name": " "}),
    ("delete_columns", {"columns": ["age", "name"]}),
    ("filter", {"column": "age", "operator": ">"}),
    ("filter", {"column": "age", "operator": ">", "value": "20"}),
    ("filter", {"column": "age", "operator": "is_missing", "value": None}),
    ("filter", {"column": "age", "operator": "contains", "value": "2"}),
    ("filter", {"column": "name", "operator": "==", "value": 2}),
    ("sort", {"column": "age", "ascending": "false"}),
    ("sort", {"column": "missing"}),
    ("convert_type", {"column": "age", "type": "anything"}),
    ("trim_whitespace", {"columns": ["age"]}),
    ("change_case", {"column": "age", "case": "upper"}),
    ("detect_outliers", {"column": "name"}),
    ("select_columns", {"columns": []}),
    ("select_columns", {"columns": ["age", "age"]}),
    ("select_columns", {"columns": "age"}),
])
def test_invalid_operations_leave_source_unchanged(frame, name, params):
    original = frame.copy(deep=True)
    with pytest.raises(DataFlowError):
        transform(frame, name, **params)
    assert_frame_equal(frame, original)


def test_engine_rejects_unknown_operation_even_without_api_validation(frame):
    operation = Transformation.model_construct(operation="execute_python", parameters={"code": "print('no')"})
    with pytest.raises(DataFlowError, match="Unknown transformation"):
        apply_transformation(frame, operation)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True, {"expression": "x"}])
def test_invalid_numeric_fill_values(frame, value):
    with pytest.raises(DataFlowError):
        transform(frame, "fill_missing", column="age", method="custom", value=value)


def test_datetime_filter():
    df = pd.DataFrame({"date": pd.to_datetime(["2025-01-01", "2025-02-01", None], utc=True)})
    result = transform(df, "filter", column="date", operator=">", value="2025-01-15")
    assert len(result) == 1
    assert result.loc[0, "date"].month == 2


def test_boolean_filter_and_fill():
    df = pd.DataFrame({"flag": pd.Series([True, False, None], dtype="boolean")})
    filtered = transform(df, "filter", column="flag", operator="==", value=False)
    assert filtered["flag"].tolist() == [False]
    filled = transform(df, "fill_missing", column="flag", method="custom", value=False)
    assert filled["flag"].tolist() == [True, False, False]
    with pytest.raises(DataFlowError):
        transform(df, "filter", column="flag", operator=">", value=True)
